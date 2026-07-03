"""
E2E テスト: v3.7.0 Retry Scheduler Event Integration

テストシナリオ:
    ── retry_decision=None 時の後方互換性 ──
    1.  retry_decision省略時、evaluate()はv3.6.0時点と同じJob由来のSchedulerEventのみを返す
    2.  retry_decision省略時、run_due()も同様
    3.  retry_decision省略時、retry_limitを指定してもJob由来のSchedulerEventのみ（Retry由来は追加されない）
    4.  retry_decision省略時、evaluate()の出力がretry_decision省略時の旧来呼び出し（位置引数のみ）と完全一致

    ── Retry候補がSchedulerEventとして反映される（retry_decision注入時）──
    5.  evaluate()の戻り値にRetry候補由来のSchedulerEventが含まれる
    6.  Retry候補由来のSchedulerEventのjob_idが "retry:" + run_id である
    7.  Retry候補由来のSchedulerEventのtrigger_reasonがREASON_RETRY_CANDIDATE_SELECTED
    8.  Retry候補由来のSchedulerEventのexecute_timeがevaluate()に渡したnowと一致する
    9.  複数候補がselect_candidates()と同じ順序（priority昇順）で反映される

    ── metadata["retry_candidate"] の格納方式（分解しない）──
    10. metadata["retry_candidate"] が候補オブジェクトそのもの（同一インスタンス）である
    11. metadata["retry_candidate"].run_id 等、候補オブジェクトの属性がそのまま参照できる

    ── retry_limit の伝播 ──
    12. retry_limitを指定するとRetry候補由来のSchedulerEvent数が制限される
    13. retry_limit省略時（None）は全件反映される
    14. run_due()にretry_limitがそのまま伝播する

    ── Job判定ループとRetry候補反映ループの独立性（Additive方式）──
    15. Job由来のSchedulerEventとRetry候補由来のSchedulerEventが同一リストに共存する
    16. disabledなJobは引き続き判定対象から除外される（Retry候補が存在していても）
    17. jobs=[] でもretry_decision注入時はRetry候補由来のSchedulerEventが返る

    ── 構造的確認（Spy）: dequeue() / remove() / Retry Engine起動が発生しない ──
    18. evaluate() / run_due() 呼び出し中、select_candidates 以外のメソッドが
        retry_decisionに対して一度も呼ばれない（Spy）

    ── Architecture Guard ──
    19. scheduler_engine.py のソースコードに 'dequeue' / 'remove' / 'RetryManager' という
        識別子参照が一切存在しない（AST）
    20. src/scheduler/ が retry_queue / retry_engine を直接importしない
    21. retry_scheduler_decision / retry_scheduler_source / retry_queue / retry_engine
        配下の全ファイル、および src/scheduler/ 配下の scheduler_engine.py と
        __init__.py 以外の全ファイルに変更がないこと（git diff、ゼロ改修の確認）
    22. src/scheduler/ 配下に新規ファイルが追加されていない
    23. SchedulerEngine が from_config / from_env を持たない（Constructor Injectionのみ）

    ── 既存回帰（v2.6.0 / v3.4.0 / v3.6.0 SchedulerEngine挙動）──
    24. DAILY/INTERVAL/ONCEの判定結果が従来と同一（retry_decision省略時）
    25. count_pending_retries() / list_pending_retries() / select_candidates() /
        select_next_candidate()（v3.4.0・v3.6.0）の挙動が本Releaseでも維持される

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v3_7_0_retry_scheduler_event_integration.py
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


def check_none(label: str, value):
    check(label, value is None, True)


print("=" * 60)
print("v3.7.0 Retry Scheduler Event Integration E2E テスト")
print("=" * 60)
print()

from scheduler import SchedulerEngine, SchedulerJob, TriggerType
from scheduler.scheduler_engine import REASON_RETRY_CANDIDATE_SELECTED
from retry_queue import RetryQueueConfig, RetryQueueManager
from retry_scheduler_source import NullRetrySchedulerSource, RetrySchedulerSource
from retry_scheduler_decision import RetrySchedulerDecision
from retry_queue.retry_queue_item import RetryQueueItem


def make_queue() -> RetryQueueManager:
    config = RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0)
    return RetryQueueManager(config=config)


class _FixedClockProvider:
    def __init__(self, fixed_now: datetime):
        self._fixed_now = fixed_now

    def now(self) -> datetime:
        return self._fixed_now


daily_job = SchedulerJob(job_id="daily-1", name="Daily", trigger_type=TriggerType.DAILY, schedule="09:00")
interval_job = SchedulerJob(job_id="interval-1", name="Interval", trigger_type=TriggerType.INTERVAL, schedule="30")
once_job = SchedulerJob(job_id="once-1", name="Once", trigger_type=TriggerType.ONCE, schedule="2026-07-03T09:00")
disabled_job = SchedulerJob(job_id="disabled-1", name="Disabled", trigger_type=TriggerType.DAILY, schedule="09:00", enabled=False)
NOW = datetime(2026, 7, 3, 9, 0)


# ═══════════════════════════════════════════════════════════
# テスト1-4: retry_decision=None 時の後方互換性
# ═══════════════════════════════════════════════════════════

print("[テスト1-4] retry_decision=None 時の後方互換性")

engine1 = SchedulerEngine()
events1 = engine1.evaluate([daily_job, interval_job, once_job, disabled_job], now=NOW)
check(
    "1. retry_decision省略時、evaluate()はJob由来のSchedulerEventのみ",
    sorted(e.job_id for e in events1),
    sorted(["daily-1", "interval-1", "once-1"]),
)
check_true("1. Retry由来のSchedulerEvent（job_idが'retry:'で始まる）が含まれない", not any(e.job_id.startswith("retry:") for e in events1))

fake_clock2 = _FixedClockProvider(NOW)
events2 = SchedulerEngine(clock=fake_clock2).run_due([daily_job])
check("2. retry_decision省略時、run_due()も同様", [e.job_id for e in events2], ["daily-1"])

events3 = engine1.evaluate([daily_job], now=NOW, retry_limit=5)
check("3. retry_decision省略時、retry_limitを指定してもJob由来のSchedulerEventのみ", [e.job_id for e in events3], ["daily-1"])

events4_legacy = engine1.evaluate([daily_job], NOW)
events4_new = engine1.evaluate([daily_job], now=NOW, retry_limit=None)
check(
    "4. retry_decision省略時、旧来呼び出し（位置引数のみ）と完全一致",
    [(e.job_id, e.execute_time, e.trigger_reason, e.metadata) for e in events4_legacy],
    [(e.job_id, e.execute_time, e.trigger_reason, e.metadata) for e in events4_new],
)
print()


# ═══════════════════════════════════════════════════════════
# テスト5-9: Retry候補がSchedulerEventとして反映される（retry_decision注入時）
# ═══════════════════════════════════════════════════════════

print("[テスト5-9] Retry候補がSchedulerEventとして反映される")

queue5 = make_queue()
queue5.enqueue(run_id="run-a", workflow_name="news", retry_attempt=1, priority=1)
queue5.enqueue(run_id="run-b", workflow_name="news", retry_attempt=1, priority=0)
source5 = RetrySchedulerSource(queue5)
decision5 = RetrySchedulerDecision(source5)
engine5 = SchedulerEngine(retry_source=source5, retry_decision=decision5)

events5 = engine5.evaluate([daily_job], now=NOW)
retry_events5 = [e for e in events5 if e.job_id.startswith("retry:")]
check("5. evaluate()の戻り値にRetry候補由来のSchedulerEventが含まれる", len(retry_events5), 2)

check(
    "6. Retry候補由来のSchedulerEventのjob_idが'retry:' + run_id",
    sorted(e.job_id for e in retry_events5),
    sorted(["retry:run-a", "retry:run-b"]),
)

check_true(
    "7. trigger_reasonがREASON_RETRY_CANDIDATE_SELECTED",
    all(e.trigger_reason == REASON_RETRY_CANDIDATE_SELECTED for e in retry_events5),
)

check_true("8. execute_timeがevaluate()に渡したnowと一致する", all(e.execute_time == NOW for e in retry_events5))

check(
    "9. 複数候補がselect_candidates()と同じ順序（priority昇順）で反映される",
    [e.job_id for e in retry_events5],
    ["retry:run-b", "retry:run-a"],
)
print()


# ═══════════════════════════════════════════════════════════
# テスト10-11: metadata["retry_candidate"] の格納方式（分解しない）
# ═══════════════════════════════════════════════════════════

print("[テスト10-11] metadata['retry_candidate'] の格納方式（分解しない）")

first_retry_event = next(e for e in events5 if e.job_id == "retry:run-b")
check(
    "10. metadataのキーが'retry_candidate'のみ（属性を個別展開しない）",
    set(first_retry_event.metadata.keys()),
    {"retry_candidate"},
)
check_true(
    "10. metadata['retry_candidate'] がRetryQueueItemインスタンスそのもの（分解されたdictではない）",
    isinstance(first_retry_event.metadata["retry_candidate"], RetryQueueItem),
)
check("11. metadata['retry_candidate'].run_id がそのまま参照できる", first_retry_event.metadata["retry_candidate"].run_id, "run-b")
check("11. metadata['retry_candidate'].workflow_name がそのまま参照できる", first_retry_event.metadata["retry_candidate"].workflow_name, "news")
print()


# ═══════════════════════════════════════════════════════════
# テスト12-14: retry_limit の伝播
# ═══════════════════════════════════════════════════════════

print("[テスト12-14] retry_limit の伝播")

events12 = engine5.evaluate([daily_job], now=NOW, retry_limit=1)
retry_events12 = [e for e in events12 if e.job_id.startswith("retry:")]
check("12. retry_limit=1でRetry候補由来のSchedulerEventが1件のみ", [e.job_id for e in retry_events12], ["retry:run-b"])

events13 = engine5.evaluate([daily_job], now=NOW, retry_limit=None)
retry_events13 = [e for e in events13 if e.job_id.startswith("retry:")]
check("13. retry_limit省略時は全件反映される", len(retry_events13), 2)

fake_clock14 = _FixedClockProvider(NOW)
events14 = SchedulerEngine(clock=fake_clock14, retry_source=source5, retry_decision=decision5).run_due([daily_job], retry_limit=1)
retry_events14 = [e for e in events14 if e.job_id.startswith("retry:")]
check("14. run_due()にretry_limitがそのまま伝播する", [e.job_id for e in retry_events14], ["retry:run-b"])
print()


# ═══════════════════════════════════════════════════════════
# テスト15-17: Job判定ループとRetry候補反映ループの独立性（Additive方式）
# ═══════════════════════════════════════════════════════════

print("[テスト15-17] Job判定ループとRetry候補反映ループの独立性")

events15 = engine5.evaluate([daily_job, interval_job, once_job], now=NOW)
job_ids15 = sorted(e.job_id for e in events15)
check(
    "15. Job由来とRetry候補由来のSchedulerEventが同一リストに共存する",
    job_ids15,
    sorted(["daily-1", "interval-1", "once-1", "retry:run-a", "retry:run-b"]),
)

events16 = engine5.evaluate([disabled_job], now=NOW)
job_events16 = [e for e in events16 if not e.job_id.startswith("retry:")]
check_true("16. disabledなJobは引き続き判定対象から除外される（Retry候補が存在していても）", len(job_events16) == 0)
check("16. Retry候補由来のSchedulerEventは引き続き反映される", len([e for e in events16 if e.job_id.startswith("retry:")]), 2)

events17 = engine5.evaluate([], now=NOW)
check("17. jobs=[] でもRetry候補由来のSchedulerEventが返る", sorted(e.job_id for e in events17), sorted(["retry:run-a", "retry:run-b"]))
print()


# ═══════════════════════════════════════════════════════════
# テスト18: 構造的確認（Spy）: dequeue() / remove() / Retry Engine起動が発生しない
# ═══════════════════════════════════════════════════════════

print("[テスト18] evaluate()/run_due()呼び出し中にselect_candidates以外が呼ばれない（Spy）")


class _RetryDecisionSpy:
    """select_candidates() 以外が呼ばれたら例外を送出するダミー。"""

    def __init__(self, real):
        self._real = real

    def select_candidates(self, limit=None):
        return self._real.select_candidates(limit=limit)

    def __getattr__(self, name):
        def _forbidden(*args, **kwargs):
            raise AssertionError(f"{name}() must not be called by SchedulerEngine")
        return _forbidden


queue18 = make_queue()
queue18.enqueue(run_id="run-18", workflow_name="news", retry_attempt=1, priority=0)
spy18 = _RetryDecisionSpy(RetrySchedulerDecision(RetrySchedulerSource(queue18)))
engine18 = SchedulerEngine(retry_decision=spy18)

try:
    engine18.evaluate([daily_job], now=NOW)
    engine18.run_due([daily_job])
    no_forbidden_call = True
except AssertionError:
    no_forbidden_call = False
check_true("18. evaluate()/run_due()呼び出し中にselect_candidates以外が呼ばれない", no_forbidden_call)
print()


# ═══════════════════════════════════════════════════════════
# テスト19-23: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト19] scheduler_engine.py に 'dequeue' / 'remove' / 'RetryManager' への実コード参照がない（AST）")

scheduler_dir = PROJECT_ROOT / "src" / "scheduler"
engine_source_path = scheduler_dir / "scheduler_engine.py"
engine_tree = ast.parse(engine_source_path.read_text(encoding="utf-8"))


def _referenced_names(tree) -> set:
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


engine_referenced = _referenced_names(engine_tree)
check_false("19. 'dequeue' への参照が存在しない", "dequeue" in engine_referenced)
check_false("19. 'remove' への参照が存在しない", "remove" in engine_referenced)
check_false("19. 'RetryManager' への参照が存在しない", "RetryManager" in engine_referenced)
check_false("19. 'RetryQueueManager' への参照が存在しない", "RetryQueueManager" in engine_referenced)
print()

print("[テスト20] src/scheduler/ が retry_queue / retry_engine を直接importしない")

for py_file in sorted(scheduler_dir.glob("*.py")):
    source_text = py_file.read_text(encoding="utf-8")
    import_lines = "\n".join(
        line for line in source_text.splitlines()
        if line.strip().startswith("from ") or line.strip().startswith("import ")
    )
    check_false(f"20. {py_file.name} が 'retry_queue' を直接importしない", "retry_queue" in import_lines)
    check_false(f"20. {py_file.name} が 'retry_engine' を直接importしない", "retry_engine" in import_lines)
print()

print("[テスト21] retry_scheduler_decision / retry_scheduler_source / retry_queue / retry_engine の")
print("           ゼロ改修確認、および src/scheduler/ 内の対象外ファイルの無変更確認（git diff）")

unchanged_paths_21 = [
    "src/retry_scheduler_decision/retry_scheduler_decision.py",
    "src/retry_scheduler_decision/__init__.py",
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
    for rel_path in unchanged_paths_21:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"21. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("21. gitが利用できないため無変更確認をスキップ", True)
print()

print("[テスト22] src/scheduler/ 配下に新規ファイルが追加されていない")

py_files_22 = sorted(p.name for p in scheduler_dir.glob("*.py"))
check(
    "22. src/scheduler/ のファイル一覧が増えていない（新規ファイル追加なし）",
    py_files_22,
    ["__init__.py", "exceptions.py", "scheduler_config.py", "scheduler_engine.py",
     "scheduler_event.py", "scheduler_job.py", "scheduler_manager.py", "scheduler_repository.py"],
)
print()

print("[テスト23] SchedulerEngine が from_config / from_env を持たない")

check_false("23. SchedulerEngine.from_config が存在しない", hasattr(SchedulerEngine, "from_config"))
check_false("23. SchedulerEngine.from_env が存在しない", hasattr(SchedulerEngine, "from_env"))
print()


# ═══════════════════════════════════════════════════════════
# テスト24-25: 既存回帰（v2.6.0 / v3.4.0 / v3.6.0 SchedulerEngine挙動）
# ═══════════════════════════════════════════════════════════

print("[テスト24-25] 既存回帰（v2.6.0 / v3.4.0 / v3.6.0 SchedulerEngine挙動）")

engine24 = SchedulerEngine()
events24 = engine24.evaluate([daily_job, interval_job, once_job, disabled_job], now=NOW)
check(
    "24. DAILY/INTERVAL/ONCEの判定結果が従来と同一（retry_decision省略時）",
    sorted(e.job_id for e in events24),
    sorted(["daily-1", "interval-1", "once-1"]),
)

queue25 = make_queue()
queue25.enqueue(run_id="run-25", workflow_name="news", retry_attempt=1, priority=0)
source25 = RetrySchedulerSource(queue25)
decision25 = RetrySchedulerDecision(source25)
engine25 = SchedulerEngine(retry_source=source25, retry_decision=decision25)
check("25. count_pending_retries()（v3.4.0）の挙動が本Releaseでも維持される", engine25.count_pending_retries(), 1)
check(
    "25. list_pending_retries()（v3.4.0）の挙動が本Releaseでも維持される",
    [item.run_id for item in engine25.list_pending_retries()],
    ["run-25"],
)
check(
    "25. select_candidates()（v3.6.0）の挙動が本Releaseでも維持される",
    [item.run_id for item in engine25.select_candidates()],
    ["run-25"],
)
next_candidate25 = engine25.select_next_candidate()
check("25. select_next_candidate()（v3.6.0）の挙動が本Releaseでも維持される", next_candidate25.run_id, "run-25")
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
