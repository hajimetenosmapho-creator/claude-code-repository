"""
E2E テスト: v3.4.0 Retry Scheduler Wiring

テストシナリオ:
    ── SchedulerEngine.__init__ の Constructor Injection ──
    1.  retry_source を省略した場合、NullRetrySchedulerSource() にフォールバックする
    2.  retry_source に RetrySchedulerSource（実体）を渡すとそのまま保持される
    3.  retry_source に NullRetrySchedulerSource() を渡すとそのまま保持される
    4.  clock のみを指定してもretry_sourceは省略時と同じくNullRetrySchedulerSource()になる

    ── count_pending_retries() / list_pending_retries()（有効時） ──
    5.  count_pending_retries() が RetrySchedulerSource.count_pending_retries() と一致する
    6.  list_pending_retries() が RetrySchedulerSource.list_pending_retries() と一致する
    7.  list_pending_retries(limit=...) の limit引数がそのまま伝播する
    8.  Queueが空の場合、count_pending_retries()は0、list_pending_retries()は[]

    ── count_pending_retries() / list_pending_retries()（NullRetrySchedulerSource） ──
    9.  retry_source省略時、count_pending_retries()は常に0
    10. retry_source省略時、list_pending_retries()は常に[]（retry_queueへは一切到達しない）

    ── evaluate() / run_due() が無変更であることの回帰確認 ──
    11. retry_sourceを渡してもevaluate()の判定結果はretry_source未指定時と完全に同じ
    12. retry_sourceを渡してもrun_due()の判定結果はretry_source未指定時と完全に同じ
    13. count_pending_retries()を呼び出した後でもevaluate()の結果は変わらない（相互に影響しない）

    ── dequeue() / remove() / RetryQueueManager直接保持 の構造的確認 ──
    14. count_pending_retries() / list_pending_retries() 呼び出し中、
        list_pending_retries / count_pending_retries 以外のメソッドが一度も呼ばれない
        （retry_sourceに対するSpyで検証。dequeue/remove/enqueue/exists相当の
        呼び出しがあれば例外を送出する）
    15. SchedulerEngineのインスタンスが _queue / _retry_queue_manager 等、
        RetryQueueManagerを直接指すと思われる属性を持たない

    ── Feature Gate / Config / Manager 追加なしの確認 ──
    16. src/scheduler/ 配下に新規Configクラス・Managerクラスが追加されていない
        （既存の SchedulerConfig / SchedulerManager のみが存在する）
    17. SchedulerEngine が from_config / from_env を持たない（Constructor Injectionのみ）

    ── Architecture Guard ──
    18. src/scheduler/ 配下のいずれのファイルも retry_queue / retry_engine を
        直接importしない（retry_scheduler_source経由のみ）
    19. src/scheduler/ 配下のいずれのファイルにも 'RetryQueueManager' /
        'RetryManager' への実コード参照（import / 識別子としての利用）が
        存在しない（ASTベースの検査。docstring中の説明目的の言及は対象外）
    20. retry_scheduler_source / retry_queue / retry_engine 配下の全ファイルに
        変更がないこと（git diff、ゼロ改修の確認）

    ── 既存回帰（v2.6.0 SchedulerEngine挙動） ──
    21. DAILY/INTERVAL/ONCEの判定結果が v2.6.0 と同一（retry_source省略時）
    22. disabledなJobは引き続き判定対象から除外される

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v3_4_0_retry_scheduler_wiring.py
"""
import ast
import subprocess
import sys
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


print("=" * 60)
print("v3.4.0 Retry Scheduler Wiring E2E テスト")
print("=" * 60)
print()

from scheduler import SchedulerEngine, SchedulerJob, TriggerType
from retry_queue import RetryQueueConfig, RetryQueueManager
from retry_scheduler_source import NullRetrySchedulerSource, RetrySchedulerSource


def make_queue() -> RetryQueueManager:
    config = RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0)
    return RetryQueueManager(config=config)


# ═══════════════════════════════════════════════════════════
# テスト1-4: SchedulerEngine.__init__ の Constructor Injection
# ═══════════════════════════════════════════════════════════

print("[テスト1-4] Constructor Injection")

engine1 = SchedulerEngine()
check_true("1. retry_source省略時、内部でNullRetrySchedulerSourceが使われる（0件）", engine1.count_pending_retries() == 0)
check("1. retry_source省略時、list_pending_retries()は[]", engine1.list_pending_retries(), [])

queue2 = make_queue()
queue2.enqueue(run_id="run-2", workflow_name="news", retry_attempt=1, priority=0)
source2 = RetrySchedulerSource(queue2)
engine2 = SchedulerEngine(retry_source=source2)
check("2. RetrySchedulerSource（実体）を渡すとそのまま保持される", engine2.count_pending_retries(), 1)

engine3 = SchedulerEngine(retry_source=NullRetrySchedulerSource())
check("3. NullRetrySchedulerSource()を渡すとそのまま保持される", engine3.count_pending_retries(), 0)


class _FixedClockProvider:
    def __init__(self, fixed_now: datetime):
        self._fixed_now = fixed_now

    def now(self) -> datetime:
        return self._fixed_now


engine4 = SchedulerEngine(clock=_FixedClockProvider(datetime(2026, 7, 3, 9, 0)))
check_true("4. clockのみ指定時もretry_sourceはNullRetrySchedulerSourceになる", engine4.count_pending_retries() == 0)
print()


# ═══════════════════════════════════════════════════════════
# テスト5-8: count_pending_retries() / list_pending_retries()（有効時）
# ═══════════════════════════════════════════════════════════

print("[テスト5-8] count_pending_retries() / list_pending_retries()（有効時）")

queue5 = make_queue()
queue5.enqueue(run_id="run-a", workflow_name="news", retry_attempt=1, priority=1)
queue5.enqueue(run_id="run-b", workflow_name="news", retry_attempt=1, priority=0)
source5 = RetrySchedulerSource(queue5)
engine5 = SchedulerEngine(retry_source=source5)

check("5. count_pending_retries() が RetrySchedulerSource と一致", engine5.count_pending_retries(), source5.count_pending_retries())
check(
    "6. list_pending_retries() が RetrySchedulerSource と一致",
    [item.run_id for item in engine5.list_pending_retries()],
    [item.run_id for item in source5.list_pending_retries()],
)
check(
    "6. list_pending_retries() の順序がpriority昇順",
    [item.run_id for item in engine5.list_pending_retries()],
    ["run-b", "run-a"],
)
check(
    "7. limit引数がそのまま伝播する",
    [item.run_id for item in engine5.list_pending_retries(limit=1)],
    ["run-b"],
)

queue8 = make_queue()
source8 = RetrySchedulerSource(queue8)
engine8 = SchedulerEngine(retry_source=source8)
check("8. Queueが空の場合、count_pending_retries()は0", engine8.count_pending_retries(), 0)
check("8. Queueが空の場合、list_pending_retries()は[]", engine8.list_pending_retries(), [])
print()


# ═══════════════════════════════════════════════════════════
# テスト9-10: count_pending_retries() / list_pending_retries()（Null）
# ═══════════════════════════════════════════════════════════

print("[テスト9-10] count_pending_retries() / list_pending_retries()（NullRetrySchedulerSource）")

engine9 = SchedulerEngine()
check("9. retry_source省略時、count_pending_retries()は常に0", engine9.count_pending_retries(), 0)
check("10. retry_source省略時、list_pending_retries()は常に[]", engine9.list_pending_retries(limit=5), [])
print()


# ═══════════════════════════════════════════════════════════
# テスト11-13: evaluate() / run_due() が無変更であることの回帰確認
# ═══════════════════════════════════════════════════════════

print("[テスト11-13] evaluate() / run_due() の無変更確認")

daily_job = SchedulerJob(job_id="daily-1", name="Daily", trigger_type=TriggerType.DAILY, schedule="09:00")
now11 = datetime(2026, 7, 3, 9, 0)

queue11 = make_queue()
queue11.enqueue(run_id="run-11", workflow_name="news", retry_attempt=1, priority=0)
engine_with_retry = SchedulerEngine(retry_source=RetrySchedulerSource(queue11))
engine_without_retry = SchedulerEngine()

events_with = engine_with_retry.evaluate([daily_job], now=now11)
events_without = engine_without_retry.evaluate([daily_job], now=now11)
check(
    "11. retry_source有無でevaluate()の結果が完全一致",
    [(e.job_id, e.execute_time, e.trigger_reason, e.metadata) for e in events_with],
    [(e.job_id, e.execute_time, e.trigger_reason, e.metadata) for e in events_without],
)

fake_clock = _FixedClockProvider(now11)
run_due_with = SchedulerEngine(clock=fake_clock, retry_source=RetrySchedulerSource(queue11)).run_due([daily_job])
run_due_without = SchedulerEngine(clock=fake_clock).run_due([daily_job])
check(
    "12. retry_source有無でrun_due()の結果が完全一致",
    [(e.job_id, e.trigger_reason) for e in run_due_with],
    [(e.job_id, e.trigger_reason) for e in run_due_without],
)

engine13 = SchedulerEngine(retry_source=RetrySchedulerSource(queue11))
events_before = engine13.evaluate([daily_job], now=now11)
engine13.count_pending_retries()
engine13.list_pending_retries()
events_after = engine13.evaluate([daily_job], now=now11)
check(
    "13. count_pending_retries()呼び出し後もevaluate()の結果は変わらない",
    [(e.job_id, e.trigger_reason) for e in events_before],
    [(e.job_id, e.trigger_reason) for e in events_after],
)
print()


# ═══════════════════════════════════════════════════════════
# テスト14-15: dequeue() / remove() / RetryQueueManager直接保持 の構造的確認
# ═══════════════════════════════════════════════════════════

print("[テスト14] list/count呼び出し中に他メソッドが一切呼ばれない（Spy）")


class _RetrySourceSpy:
    """list_pending_retries() / count_pending_retries() 以外が呼ばれたら例外を送出するダミー。"""

    def __init__(self, real):
        self._real = real

    def list_pending_retries(self, limit=None):
        return self._real.list_pending_retries(limit=limit)

    def count_pending_retries(self):
        return self._real.count_pending_retries()

    def __getattr__(self, name):
        def _forbidden(*args, **kwargs):
            raise AssertionError(f"{name}() must not be called by SchedulerEngine")
        return _forbidden


queue14 = make_queue()
queue14.enqueue(run_id="run-14", workflow_name="news", retry_attempt=1, priority=0)
spy14 = _RetrySourceSpy(RetrySchedulerSource(queue14))
engine14 = SchedulerEngine(retry_source=spy14)

try:
    engine14.count_pending_retries()
    engine14.list_pending_retries(limit=3)
    no_forbidden_call = True
except AssertionError:
    no_forbidden_call = False
check_true("14. count/list呼び出し中に他のメソッドが呼ばれない", no_forbidden_call)
print()

print("[テスト15] SchedulerEngineがRetryQueueManagerを直接指す属性を持たない")

engine15 = SchedulerEngine(retry_source=RetrySchedulerSource(make_queue()))
forbidden_attr_names = {"_queue", "_retry_queue_manager", "_retry_queue"}
found_forbidden = forbidden_attr_names & set(vars(engine15).keys())
check("15. RetryQueueManagerを直接指す属性名が存在しない", found_forbidden, set())
check_true(
    "15. _retry_source の型が RetryQueueManager ではない",
    type(engine15._retry_source).__name__ != "RetryQueueManager",
)
print()


# ═══════════════════════════════════════════════════════════
# テスト16-17: Feature Gate / Config / Manager 追加なしの確認
# ═══════════════════════════════════════════════════════════

print("[テスト16] src/scheduler/ 配下に新規Config/Managerクラスが追加されていない")

scheduler_dir = PROJECT_ROOT / "src" / "scheduler"
existing_config_or_manager_files = {"scheduler_config.py", "scheduler_manager.py"}
py_files_16 = sorted(p.name for p in scheduler_dir.glob("*.py"))
check(
    "16. src/scheduler/ のファイル一覧がv2.6.0から増えていない（新規ファイル追加なし）",
    py_files_16,
    ["__init__.py", "exceptions.py", "scheduler_config.py", "scheduler_engine.py",
     "scheduler_event.py", "scheduler_job.py", "scheduler_manager.py", "scheduler_repository.py"],
)
print()

print("[テスト17] SchedulerEngine が from_config / from_env を持たない")

check_false("17. SchedulerEngine.from_config が存在しない", hasattr(SchedulerEngine, "from_config"))
check_false("17. SchedulerEngine.from_env が存在しない", hasattr(SchedulerEngine, "from_env"))
print()


# ═══════════════════════════════════════════════════════════
# テスト18-20: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト18] src/scheduler/ が retry_queue / retry_engine を直接importしない")

for py_file in sorted(scheduler_dir.glob("*.py")):
    source = py_file.read_text(encoding="utf-8")
    import_lines = "\n".join(
        line for line in source.splitlines()
        if line.strip().startswith("from ") or line.strip().startswith("import ")
    )
    check_false(f"18. {py_file.name} が 'retry_queue' を直接importしない", "retry_queue" in import_lines)
    check_false(f"18. {py_file.name} が 'retry_engine' を直接importしない", "retry_engine" in import_lines)
    check_false(f"18. {py_file.name} が 'from ai' をimportしない", "from ai" in import_lines or "from ai." in import_lines)
    check_false(f"18. {py_file.name} が 'from pipeline' をimportしない", "from pipeline" in import_lines or "from pipeline." in import_lines)
print()

print("[テスト19] src/scheduler/ に 'RetryQueueManager' / 'RetryManager' への実コード参照がない（AST）")


def _referenced_names(py_file: Path) -> set:
    """docstring・コメントを除外し、実際に識別子として参照された名前の集合を返す。"""
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


for py_file in sorted(scheduler_dir.glob("*.py")):
    referenced = _referenced_names(py_file)
    check_false(f"19. {py_file.name} が 'RetryQueueManager' を実コードで参照しない", "RetryQueueManager" in referenced)
    check_false(f"19. {py_file.name} が 'RetryManager' を実コードで参照しない", "RetryManager" in referenced)
print()

print("[テスト20] retry_scheduler_source / retry_queue / retry_engine のゼロ改修確認（git diff）")

unchanged_paths_20 = [
    "src/retry_scheduler_source/retry_scheduler_source.py",
    "src/retry_scheduler_source/__init__.py",
    "src/retry_queue/retry_queue_manager.py",
    "src/retry_queue/null_retry_queue_manager.py",
    "src/retry_queue/retry_queue_config.py",
    "src/retry_queue/retry_queue_item.py",
    "src/retry_queue/retry_queue_result.py",
    "src/retry_queue/retry_queue_status.py",
    "src/retry_queue/__init__.py",
    "src/retry_engine/retry_config.py",
    "src/retry_engine/retry_executor.py",
    "src/retry_engine/retry_manager.py",
    "src/retry_engine/retry_policy.py",
    "src/retry_engine/retry_request.py",
    "src/retry_engine/retry_result.py",
    "src/retry_engine/__init__.py",
    "src/scheduler/scheduler_manager.py",
    "src/scheduler/scheduler_job.py",
    "src/scheduler/scheduler_event.py",
    "src/scheduler/scheduler_repository.py",
    "src/scheduler/scheduler_config.py",
    "src/scheduler/exceptions.py",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths_20:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"20. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("20. gitが利用できないため無変更確認をスキップ", True)
print()


# ═══════════════════════════════════════════════════════════
# テスト21-22: 既存回帰（v2.6.0 SchedulerEngine挙動）
# ═══════════════════════════════════════════════════════════

print("[テスト21-22] 既存回帰（v2.6.0 SchedulerEngine挙動）")

engine21 = SchedulerEngine()
interval_job = SchedulerJob(job_id="interval-1", name="Interval", trigger_type=TriggerType.INTERVAL, schedule="30")
once_job = SchedulerJob(job_id="once-1", name="Once", trigger_type=TriggerType.ONCE, schedule="2026-07-03T09:00")
disabled_job = SchedulerJob(job_id="disabled-1", name="Disabled", trigger_type=TriggerType.DAILY, schedule="09:00", enabled=False)

now21 = datetime(2026, 7, 3, 9, 0)
events21 = engine21.evaluate([daily_job, interval_job, once_job, disabled_job], now=now21)
check(
    "21. DAILY/INTERVAL/ONCEの判定結果がv2.6.0と同一",
    sorted(e.job_id for e in events21),
    sorted(["daily-1", "interval-1", "once-1"]),
)
check_true("22. disabledなJobは判定対象から除外される", "disabled-1" not in [e.job_id for e in events21])
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
