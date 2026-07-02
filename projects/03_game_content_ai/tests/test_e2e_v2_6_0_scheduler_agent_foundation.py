"""
E2E テスト: v2.6.0 Scheduler Agent Foundation

テストシナリオ:
    ── SchedulerJob / TriggerType ──
    1.  SchedulerJobの生成（enabled/metadataのデフォルト値）
    2.  SchedulerJobの生成（全フィールド明示指定）
    3.  TriggerType Enumのメンバー（DAILY/INTERVAL/ONCEの3種類のみ）
    4.  TriggerType.valueが文字列である

    ── SchedulerRepository（抽象化） ──
    5.  SchedulerRepositoryは直接インスタンス化できない（ABC）
    6.  InMemorySchedulerRepositoryがSchedulerRepositoryのサブクラスである
    7.  add() → get() で同一Jobが取得できる
    8.  add() で重複job_idを登録するとDuplicateSchedulerJobError
    9.  get() で未登録job_idはNoneを返す
    10. remove() で削除したJobはget()でNoneになる
    11. remove() で未登録job_idはSchedulerJobNotFoundError
    12. list_all() が登録済み全Jobを返す
    13. update() で未登録job_idはSchedulerJobNotFoundError
    14. update() で既存Jobの内容が置き換わる

    ── SchedulerManager ──
    15. register_job() → get_job() で取得できる
    16. register_job() で重複job_idはDuplicateSchedulerJobError
    17. remove_job() で削除される
    18. remove_job() で未登録job_idはSchedulerJobNotFoundError
    19. list_jobs() が登録済み全Jobを返す
    20. enable_job() でenabled=Trueになる（元がFalseから）
    21. disable_job() でenabled=Falseになる（元がTrueから）
    22. enable_job()/disable_job() は新しいSchedulerJobインスタンスを返す（不変性）
    23. enable_job() で未登録job_idはSchedulerJobNotFoundError

    ── SchedulerEngine.evaluate()（判定、副作用なし） ──
    24. DAILY: schedule一致 → 対象になる
    25. DAILY: schedule不一致 → 対象にならない
    26. INTERVAL: 経過分数が倍数 → 対象になる
    27. INTERVAL: 経過分数が倍数でない → 対象にならない
    28. ONCE: 分単位一致 → 対象になる
    29. ONCE: 分単位不一致 → 対象にならない
    30. disabled Jobは対象にならない（DAILY一致条件でも）
    31. 複数Job（一致・不一致・disabled混在）を同時判定できる
    32. 不正なschedule文字列（INTERVAL）は例外を投げず対象外になる
    33. 不正なschedule文字列（ONCE）は例外を投げず対象外になる
    34. evaluate()はjobsリストを変更しない（純粋関数）
    35. evaluate()を同じ引数で2回呼んでも同じ結果になる（冪等性）

    ── SchedulerEvent ──
    36. SchedulerEvent生成（フィールドの値確認）
    37. evaluate()が返すSchedulerEventのjob_idが対象Jobと一致する
    38. evaluate()が返すSchedulerEventのmetadataがJob.metadataを引き継ぐ
    39. evaluate()が返すSchedulerEventのexecute_timeがnow引数と一致する

    ── SchedulerEngine.run_due()（ClockProvider経由） ──
    40. 固定時刻を返すFakeClockProviderで run_due() が evaluate() と同じ結果になる

    ── SchedulerConfig ──
    41. from_env()のデフォルト値（enabled=False、is_ready()=False）
    42. SCHEDULER_ENABLED=true の環境変数上書き

    ── Architecture Guard ──
    43. src/ai/・src/pipeline/に変更がないこと（git diff）
    44. scheduler パッケージの各ファイルが src/ai または src/pipeline をimportしないこと（静的検査）
    45. src/scheduler/__init__.py からの全シンボルexport確認

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v2_6_0_scheduler_agent_foundation.py
"""
import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ─── テスト用ユーティリティ ───

results_log = []


def check(label: str, actual, expected, exact: bool = True):
    ok = (actual == expected) if exact else (expected in str(actual))
    status = "PASS" if ok else "FAIL"
    results_log.append((status, label))
    mark = "OK" if ok else "NG"
    print(f"  [{mark}] {label}")
    if not ok:
        print(f"       期待値: {expected!r}")
        print(f"       実際値: {actual!r}")


def check_true(label: str, value: bool):
    check(label, value, True)


def check_false(label: str, value: bool):
    check(label, value, False)


def check_none(label: str, value):
    check(label, value is None, True)


def check_not_none(label: str, value):
    check(label, value is not None, True)


print("=" * 60)
print("v2.6.0 Scheduler Agent Foundation E2E テスト")
print("=" * 60)
print()

from scheduler import (
    TriggerType,
    SchedulerJob,
    SchedulerEvent,
    SchedulerRepository,
    InMemorySchedulerRepository,
    SchedulerManager,
    ClockProvider,
    SystemClockProvider,
    SchedulerEngine,
    SchedulerConfig,
    SchedulerError,
    SchedulerJobNotFoundError,
    DuplicateSchedulerJobError,
)
from scheduler.scheduler_engine import (
    REASON_DAILY_MATCHED,
    REASON_INTERVAL_MATCHED,
    REASON_ONCE_MATCHED,
)


# ═══════════════════════════════════════════════════════════
# テスト1-4: SchedulerJob / TriggerType
# ═══════════════════════════════════════════════════════════

print("[テスト1-4] SchedulerJob / TriggerType")

job1 = SchedulerJob(
    job_id="job-1", name="テストJob", trigger_type=TriggerType.DAILY, schedule="09:00"
)
check("1. job_id", job1.job_id, "job-1")
check_true("1. デフォルト enabled=True", job1.enabled)
check("1. デフォルト metadata={}", job1.metadata, {})

job2 = SchedulerJob(
    job_id="job-2", name="全指定Job", trigger_type=TriggerType.INTERVAL,
    schedule="30", enabled=False, metadata={"article_id": "sample"},
)
check_false("2. enabled=False を明示指定", job2.enabled)
check("2. metadata を明示指定", job2.metadata, {"article_id": "sample"})

check(
    "3. TriggerTypeのメンバーがDAILY/INTERVAL/ONCEの3種類のみ",
    {t.name for t in TriggerType},
    {"DAILY", "INTERVAL", "ONCE"},
)
check("4. TriggerType.DAILY.value が文字列", TriggerType.DAILY.value, "daily")
check("4. TriggerType.INTERVAL.value が文字列", TriggerType.INTERVAL.value, "interval")
check("4. TriggerType.ONCE.value が文字列", TriggerType.ONCE.value, "once")
print()


# ═══════════════════════════════════════════════════════════
# テスト5-14: SchedulerRepository（抽象化）
# ═══════════════════════════════════════════════════════════

print("[テスト5-14] SchedulerRepository")

try:
    SchedulerRepository()
    check_true("5. SchedulerRepositoryは直接インスタンス化できない", False)
except TypeError:
    check_true("5. SchedulerRepositoryは直接インスタンス化できない", True)

repo = InMemorySchedulerRepository()
check_true("6. InMemorySchedulerRepositoryがSchedulerRepositoryのサブクラス", isinstance(repo, SchedulerRepository))

job_a = SchedulerJob(job_id="a", name="A", trigger_type=TriggerType.DAILY, schedule="09:00")
repo.add(job_a)
check("7. add() → get() で同一Jobが取得できる", repo.get("a"), job_a)

try:
    repo.add(job_a)
    check_true("8. 重複job_id登録はDuplicateSchedulerJobError", False)
except DuplicateSchedulerJobError:
    check_true("8. 重複job_id登録はDuplicateSchedulerJobError", True)

check_none("9. 未登録job_idのget()はNone", repo.get("not-exist"))

job_b = SchedulerJob(job_id="b", name="B", trigger_type=TriggerType.INTERVAL, schedule="15")
repo.add(job_b)
repo.remove("b")
check_none("10. remove() 後はget()でNone", repo.get("b"))

try:
    repo.remove("not-exist")
    check_true("11. 未登録job_idのremove()はSchedulerJobNotFoundError", False)
except SchedulerJobNotFoundError:
    check_true("11. 未登録job_idのremove()はSchedulerJobNotFoundError", True)

check("12. list_all() が登録済み全Jobを返す", {j.job_id for j in repo.list_all()}, {"a"})

try:
    repo.update(SchedulerJob(job_id="not-exist", name="X", trigger_type=TriggerType.ONCE, schedule="2026-07-10T09:00"))
    check_true("13. 未登録job_idのupdate()はSchedulerJobNotFoundError", False)
except SchedulerJobNotFoundError:
    check_true("13. 未登録job_idのupdate()はSchedulerJobNotFoundError", True)

updated_a = SchedulerJob(job_id="a", name="A更新済み", trigger_type=TriggerType.DAILY, schedule="10:00")
repo.update(updated_a)
check("14. update() で既存Jobの内容が置き換わる", repo.get("a").name, "A更新済み")
print()


# ═══════════════════════════════════════════════════════════
# テスト15-23: SchedulerManager
# ═══════════════════════════════════════════════════════════

print("[テスト15-23] SchedulerManager")

manager = SchedulerManager(repository=InMemorySchedulerRepository())

job15 = SchedulerJob(job_id="m1", name="Manager Job1", trigger_type=TriggerType.DAILY, schedule="09:00")
manager.register_job(job15)
check("15. register_job() → get_job() で取得できる", manager.get_job("m1"), job15)

try:
    manager.register_job(job15)
    check_true("16. 重複job_idはDuplicateSchedulerJobError", False)
except DuplicateSchedulerJobError:
    check_true("16. 重複job_idはDuplicateSchedulerJobError", True)

job17 = SchedulerJob(job_id="m2", name="Manager Job2", trigger_type=TriggerType.INTERVAL, schedule="60")
manager.register_job(job17)
manager.remove_job("m2")
check_none("17. remove_job() で削除される", manager.get_job("m2"))

try:
    manager.remove_job("not-exist")
    check_true("18. 未登録job_idのremove_job()はSchedulerJobNotFoundError", False)
except SchedulerJobNotFoundError:
    check_true("18. 未登録job_idのremove_job()はSchedulerJobNotFoundError", True)

check("19. list_jobs() が登録済み全Jobを返す", {j.job_id for j in manager.list_jobs()}, {"m1"})

job20 = SchedulerJob(job_id="m3", name="Manager Job3", trigger_type=TriggerType.ONCE, schedule="2026-07-10T09:00", enabled=False)
manager.register_job(job20)
enabled_job20 = manager.enable_job("m3")
check_true("20. enable_job() でenabled=Trueになる", enabled_job20.enabled)
check_true("20. Repository側にも反映される", manager.get_job("m3").enabled)

disabled_job20 = manager.disable_job("m3")
check_false("21. disable_job() でenabled=Falseになる", disabled_job20.enabled)

check_true(
    "22. enable_job()/disable_job() は新しいインスタンスを返す（不変性）",
    disabled_job20 is not job20,
)

try:
    manager.enable_job("not-exist")
    check_true("23. 未登録job_idのenable_job()はSchedulerJobNotFoundError", False)
except SchedulerJobNotFoundError:
    check_true("23. 未登録job_idのenable_job()はSchedulerJobNotFoundError", True)
print()


# ═══════════════════════════════════════════════════════════
# テスト24-35: SchedulerEngine.evaluate()
# ═══════════════════════════════════════════════════════════

print("[テスト24-35] SchedulerEngine.evaluate()")

engine = SchedulerEngine()

# テスト24-25: DAILY
daily_job = SchedulerJob(job_id="daily-1", name="Daily", trigger_type=TriggerType.DAILY, schedule="09:00")
events24 = engine.evaluate([daily_job], now=datetime(2026, 7, 2, 9, 0))
check("24. DAILY一致 → 対象になる", [e.job_id for e in events24], ["daily-1"])
check("24. reasonが固定文言", events24[0].trigger_reason, REASON_DAILY_MATCHED)

events25 = engine.evaluate([daily_job], now=datetime(2026, 7, 2, 9, 1))
check("25. DAILY不一致 → 対象にならない", events25, [])

# テスト26-27: INTERVAL（1970-01-01 00:00からの経過分数で判定）
interval_job = SchedulerJob(job_id="interval-1", name="Interval", trigger_type=TriggerType.INTERVAL, schedule="30")
events26 = engine.evaluate([interval_job], now=datetime(1970, 1, 1, 1, 0))  # 経過60分 → 30の倍数
check("26. INTERVAL一致（経過分数が倍数） → 対象になる", [e.job_id for e in events26], ["interval-1"])
check("26. reasonが固定文言", events26[0].trigger_reason, REASON_INTERVAL_MATCHED)

events27 = engine.evaluate([interval_job], now=datetime(1970, 1, 1, 0, 45))  # 経過45分 → 30の倍数でない
check("27. INTERVAL不一致 → 対象にならない", events27, [])

# テスト28-29: ONCE
once_job = SchedulerJob(job_id="once-1", name="Once", trigger_type=TriggerType.ONCE, schedule="2026-07-10T09:00")
events28 = engine.evaluate([once_job], now=datetime(2026, 7, 10, 9, 0))
check("28. ONCE一致（分単位） → 対象になる", [e.job_id for e in events28], ["once-1"])
check("28. reasonが固定文言", events28[0].trigger_reason, REASON_ONCE_MATCHED)

events29 = engine.evaluate([once_job], now=datetime(2026, 7, 10, 9, 1))
check("29. ONCE不一致 → 対象にならない", events29, [])

# テスト30: disabled Job
disabled_daily_job = SchedulerJob(
    job_id="daily-disabled", name="Daily Disabled", trigger_type=TriggerType.DAILY,
    schedule="09:00", enabled=False,
)
events30 = engine.evaluate([disabled_daily_job], now=datetime(2026, 7, 2, 9, 0))
check("30. disabled Jobは一致条件でも対象にならない", events30, [])

# テスト31: 複数Job混在（interval_not_matching_jobは2026-07-02 09:00時点で
# 経過分数%7==1のため一致しないことを事前に確認済み）
interval_not_matching_job = SchedulerJob(
    job_id="interval-not-matching", name="Interval Not Matching",
    trigger_type=TriggerType.INTERVAL, schedule="7",
)
mixed_jobs = [daily_job, disabled_daily_job, interval_not_matching_job]
events31 = engine.evaluate(mixed_jobs, now=datetime(2026, 7, 2, 9, 0))
check(
    "31. 複数Job（一致・不一致・disabled混在）を同時判定できる",
    {e.job_id for e in events31},
    {"daily-1"},
)

# テスト32-33: 不正なschedule文字列
bad_interval_job = SchedulerJob(job_id="bad-interval", name="Bad Interval", trigger_type=TriggerType.INTERVAL, schedule="not-a-number")
events32 = engine.evaluate([bad_interval_job], now=datetime(2026, 7, 2, 9, 0))
check("32. 不正なINTERVAL scheduleは例外を投げず対象外になる", events32, [])

bad_once_job = SchedulerJob(job_id="bad-once", name="Bad Once", trigger_type=TriggerType.ONCE, schedule="not-a-datetime")
events33 = engine.evaluate([bad_once_job], now=datetime(2026, 7, 2, 9, 0))
check("33. 不正なONCE scheduleは例外を投げず対象外になる", events33, [])

# テスト34: jobsリストを変更しない
jobs_snapshot = list(mixed_jobs)
engine.evaluate(mixed_jobs, now=datetime(2026, 7, 2, 9, 0))
check("34. evaluate()はjobsリストを変更しない", mixed_jobs, jobs_snapshot)

# テスト35: 冪等性
events35a = engine.evaluate(mixed_jobs, now=datetime(2026, 7, 2, 9, 0))
events35b = engine.evaluate(mixed_jobs, now=datetime(2026, 7, 2, 9, 0))
check(
    "35. evaluate()を同じ引数で2回呼んでも同じ結果になる",
    [e.job_id for e in events35a],
    [e.job_id for e in events35b],
)
print()


# ═══════════════════════════════════════════════════════════
# テスト36-39: SchedulerEvent
# ═══════════════════════════════════════════════════════════

print("[テスト36-39] SchedulerEvent")

now36 = datetime(2026, 7, 2, 9, 0)
event36 = SchedulerEvent(job_id="job-x", execute_time=now36, trigger_reason="test reason")
check("36. job_id", event36.job_id, "job-x")
check("36. execute_time", event36.execute_time, now36)
check("36. trigger_reason", event36.trigger_reason, "test reason")
check("36. デフォルト metadata={}", event36.metadata, {})

metadata_job = SchedulerJob(
    job_id="meta-job", name="Meta", trigger_type=TriggerType.DAILY, schedule="09:00",
    metadata={"article_id": "sample-article"},
)
events37 = engine.evaluate([metadata_job], now=datetime(2026, 7, 2, 9, 0))
check("37. SchedulerEventのjob_idが対象Jobと一致する", events37[0].job_id, "meta-job")
check("38. SchedulerEventのmetadataがJob.metadataを引き継ぐ", events37[0].metadata, {"article_id": "sample-article"})
check("39. SchedulerEventのexecute_timeがnow引数と一致する", events37[0].execute_time, datetime(2026, 7, 2, 9, 0))
print()


# ═══════════════════════════════════════════════════════════
# テスト40: SchedulerEngine.run_due()（ClockProvider経由）
# ═══════════════════════════════════════════════════════════

print("[テスト40] SchedulerEngine.run_due()")


class FakeClockProvider(ClockProvider):
    def __init__(self, fixed_now: datetime):
        self._fixed_now = fixed_now

    def now(self) -> datetime:
        return self._fixed_now


fake_clock = FakeClockProvider(datetime(2026, 7, 2, 9, 0))
engine_with_fake_clock = SchedulerEngine(clock=fake_clock)
run_due_events = engine_with_fake_clock.run_due([daily_job])
evaluate_events = engine.evaluate([daily_job], now=datetime(2026, 7, 2, 9, 0))
check(
    "40. 固定時刻ClockProviderでrun_due()がevaluate()と同じ結果になる",
    [e.job_id for e in run_due_events],
    [e.job_id for e in evaluate_events],
)
check_true("40. SystemClockProviderもClockProviderのサブクラス", isinstance(SystemClockProvider(), ClockProvider))
print()


# ═══════════════════════════════════════════════════════════
# テスト41-42: SchedulerConfig
# ═══════════════════════════════════════════════════════════

print("[テスト41-42] SchedulerConfig")

os.environ.pop("SCHEDULER_ENABLED", None)
cfg41 = SchedulerConfig.from_env()
check_false("41. デフォルト enabled=False", cfg41.enabled)
check_false("41. デフォルト is_ready()=False", cfg41.is_ready())

os.environ["SCHEDULER_ENABLED"] = "true"
cfg42 = SchedulerConfig.from_env()
check_true("42. SCHEDULER_ENABLED=true で enabled=True", cfg42.enabled)
check_true("42. is_ready()=True", cfg42.is_ready())
os.environ.pop("SCHEDULER_ENABLED", None)
print()


# ═══════════════════════════════════════════════════════════
# テスト43-45: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト43] 既存ファイルの無変更確認（git diff）")

unchanged_paths = [
    "src/ai",
    "src/pipeline",
    "main.py",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            timeout=10,
        )
        check_true(f"43. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("43. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト44] scheduler パッケージの禁止import静的検査")

scheduler_dir = PROJECT_ROOT / "src" / "scheduler"
for py_file in sorted(scheduler_dir.glob("*.py")):
    source = py_file.read_text(encoding="utf-8")
    import_lines = "\n".join(
        line for line in source.splitlines()
        if line.strip().startswith("from ") or line.strip().startswith("import ")
    )
    check_false(f"44. {py_file.name} が 'from ai' をimportしない", "from ai" in import_lines or "from ai." in import_lines)
    check_false(f"44. {py_file.name} が 'import ai' をimportしない", "import ai" in import_lines)
    check_false(f"44. {py_file.name} が 'from pipeline' をimportしない", "from pipeline" in import_lines or "from pipeline." in import_lines)
    check_false(f"44. {py_file.name} が 'import pipeline' をimportしない", "import pipeline" in import_lines)
print()


print("[テスト45] import確認")

import scheduler as scheduler_pkg
for name in (
    "SchedulerError", "SchedulerJobNotFoundError", "DuplicateSchedulerJobError",
    "TriggerType", "SchedulerJob", "SchedulerEvent",
    "SchedulerRepository", "InMemorySchedulerRepository", "SchedulerManager",
    "ClockProvider", "SystemClockProvider", "SchedulerEngine", "SchedulerConfig",
):
    check_true(f"45. {name} が scheduler パッケージからエクスポートされている", hasattr(scheduler_pkg, name))
    check_true(f"45. {name} が scheduler.__all__ に含まれる", name in scheduler_pkg.__all__)
print()


# ─── 結果サマリー ───
print("=" * 60)
total = len(results_log)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = total - passed
print(f"合計: {passed}/{total} PASS  /  {failed} FAIL")
print("=" * 60)

if failed > 0:
    print()
    print("FAILしたテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
else:
    print("全テスト PASS")
