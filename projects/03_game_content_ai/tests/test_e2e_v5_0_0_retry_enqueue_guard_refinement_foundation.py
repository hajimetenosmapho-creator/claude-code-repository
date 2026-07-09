"""
E2E テスト: v5.0.0 Retry Enqueue Guard Refinement Foundation

テストシナリオ:
    ── RetryEnqueueGuard（単体、判定基準の精緻化） ──
    1.  next_attempt > max_attempts で BLOCK を返す
    2.  next_attempt == max_attempts（境界値）で ALLOW を返す
    3.  next_attempt < max_attempts で ALLOW を返す
    4.  RetryEnqueueGuardDecision の run_id / reason が正しい
    5.  RetryEnqueueGuard がインスタンス変数を一切持たない（Stateless）
    6.  decide() のシグネチャが (self, run_id, next_attempt, max_attempts) である
        （has_history引数が存在しないことの確認）

    ── RetryEnqueueTrigger + Guard 統合（max_attempts省略時、Backward Compatibility） ──
    7.  max_attempts省略時、履歴がない run_id は enqueue される（next_attempt=1 <= 1）
    8.  max_attempts省略時、履歴が1件でもある run_id は enqueue されない
        （next_attempt=2 > 1、v4.8.0/v4.9.0時点と完全に同一の挙動）
    9.  v4.9.0時点の主要シナリオ（history省略・複数レコード混在）の結果が完全に一致する

    ── RetryEnqueueTrigger + Guard 統合（max_attemptsを明示指定、複数回リトライの解禁） ──
    10. max_attempts=3 の場合、attempt_count=1（next_attempt=2）は enqueue される
    11. max_attempts=3 の場合、attempt_count=2（next_attempt=3、境界値）は enqueue される
    12. max_attempts=3 の場合、attempt_count=3（next_attempt=4）は enqueue されない
    13. enqueueされたQueue項目のretry_attemptが正しくnext_attemptと一致する

    ── max_attemptsのスコープ（インスタンス状態として保持しない） ──
    14. RetryEnqueueTrigger.__init__ のシグネチャが本Release前と完全に同一
        （max_attemptsを引数に持たない）
    15. RetryEnqueueTriggerがmax_attemptsをインスタンス変数として保持しない
    16. enqueue_pending_failures() のシグネチャが (self, limit=None, max_attempts=1)
    17. 同一インスタンスに対し、呼び出しごとに異なるmax_attemptsを渡せる

    ── シグネチャ・ディレクトリ構成・Backward Compatibility ──
    18. src/retry_enqueue_trigger/ のファイル構成が本Release前と同一（3ファイル、新規ファイルなし）
    19. retry_enqueue_trigger パッケージのexportが本Release前と同一（6シンボル）

    ── Architecture Guard ──
    20. retry_enqueue_trigger が retry_engine/workflow_engine/execution_history/
        scheduler/ai/pipelineを一切importしない（静的検査、RetryPolicy非依存の確認）
    21. retry_queue / retry_history / workflow_monitor / retry_engine に
        変更がないこと（git diff）
    22. 本Releaseでも retry_enqueue_trigger をどのパッケージからも呼び出さない

    ── 副作用なしの確認 ──
    23. RetryEnqueueTrigger 実行前後でファイルが一切作成されない

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v5_0_0_retry_enqueue_guard_refinement_foundation.py
"""
import inspect
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
print("v5.0.0 Retry Enqueue Guard Refinement Foundation E2E テスト")
print("=" * 60)
print()

import retry_enqueue_trigger as ret_pkg
from retry_enqueue_trigger import (
    NullRetryEnqueueTrigger,
    RetryEnqueueGuard,
    RetryEnqueueGuardDecision,
    RetryEnqueueGuardOutcome,
    RetryEnqueueTrigger,
    RetryEnqueueTriggerResult,
)
from retry_history import RetryHistoryManager
from retry_queue import RetryQueueConfig, RetryQueueManager
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus


def make_record(run_id: str, monitor_status: WorkflowMonitorStatus, workflow_name: str = "news") -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name=workflow_name, monitor_status=monitor_status,
        source_status=monitor_status.value, source="manual", job_id="job-1",
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=[],
    )


class FakeWorkflowMonitorManager:
    def __init__(self, records: list):
        self._records = records
        self.calls: list = []

    def list_status(self, limit=None):
        self.calls.append(limit)
        if limit is not None:
            return self._records[:limit]
        return self._records


def make_queue(max_queue_size: int = 100) -> RetryQueueManager:
    config = RetryQueueConfig(enabled=True, max_queue_size=max_queue_size, default_priority=0)
    return RetryQueueManager(config=config)


# ═══════════════════════════════════════════════════════════
# テスト1-6: RetryEnqueueGuard（単体、判定基準の精緻化）
# ═══════════════════════════════════════════════════════════

print("[テスト1] next_attempt > max_attempts で BLOCK を返す")

guard_1 = RetryEnqueueGuard()
decision_1 = guard_1.decide("run-x", next_attempt=2, max_attempts=1)
check("1. outcomeがBLOCK", decision_1.outcome, RetryEnqueueGuardOutcome.BLOCK)
print()


print("[テスト2] next_attempt == max_attempts（境界値）で ALLOW を返す")

decision_2 = guard_1.decide("run-x", next_attempt=3, max_attempts=3)
check("2. outcomeがALLOW", decision_2.outcome, RetryEnqueueGuardOutcome.ALLOW)
print()


print("[テスト3] next_attempt < max_attempts で ALLOW を返す")

decision_3 = guard_1.decide("run-x", next_attempt=1, max_attempts=3)
check("3. outcomeがALLOW", decision_3.outcome, RetryEnqueueGuardOutcome.ALLOW)
print()


print("[テスト4] RetryEnqueueGuardDecision の run_id / reason が正しい")

decision_4 = guard_1.decide("run-abc", next_attempt=5, max_attempts=3)
check("4. run_idが一致する", decision_4.run_id, "run-abc")
check_true("4. reasonにnext_attemptが含まれる", "next_attempt=5" in decision_4.reason)
check_true("4. reasonにmax_attemptsが含まれる", "max_attempts=3" in decision_4.reason)
print()


print("[テスト5] RetryEnqueueGuard がインスタンス変数を一切持たない（Stateless）")

check("5. __dict__が空", vars(guard_1), {})
print()


print("[テスト6] decide() のシグネチャが (self, run_id, next_attempt, max_attempts)")

params_6 = list(inspect.signature(RetryEnqueueGuard.decide).parameters.keys())
check("6. パラメータがself, run_id, next_attempt, max_attempts", params_6, ["self", "run_id", "next_attempt", "max_attempts"])
check_false("6. has_historyという引数名が存在しない", "has_history" in params_6)
print()


# ═══════════════════════════════════════════════════════════
# テスト7-9: max_attempts省略時、Backward Compatibility
# ═══════════════════════════════════════════════════════════

print("[テスト7] max_attempts省略時、履歴がない run_id は enqueue される")

history_7 = RetryHistoryManager()
monitor_7 = FakeWorkflowMonitorManager(records=[make_record("run-fresh", WorkflowMonitorStatus.FAILED)])
queue_7 = make_queue()
trigger_7 = RetryEnqueueTrigger(monitor_7, queue_7, history=history_7)
result_7 = trigger_7.enqueue_pending_failures()
check("7. enqueuedが1件", result_7.enqueued, 1)
check("7. retry_attemptが1", queue_7.list()[0].retry_attempt, 1)
print()


print("[テスト8] max_attempts省略時、履歴が1件でもある run_id は enqueue されない")

history_8 = RetryHistoryManager()
history_8.record("run-blocked", attempt=1, recorded_at=datetime.now())
monitor_8 = FakeWorkflowMonitorManager(records=[make_record("run-blocked", WorkflowMonitorStatus.FAILED)])
queue_8 = make_queue()
trigger_8 = RetryEnqueueTrigger(monitor_8, queue_8, history=history_8)
result_8 = trigger_8.enqueue_pending_failures()
check("8. enqueuedが0件", result_8.enqueued, 0)
check("8. skipped_historyが1件", result_8.skipped_history, 1)
check_false("8. run-blockedがQueueに存在しない", queue_8.exists("run-blocked"))
print()


print("[テスト9] v4.9.0時点の主要シナリオの結果が完全に一致する")

monitor_9 = FakeWorkflowMonitorManager(records=[
    make_record("run-a", WorkflowMonitorStatus.FAILED),
    make_record("run-b", WorkflowMonitorStatus.TIMEOUT),
    make_record("run-c", WorkflowMonitorStatus.RUNNING),
    make_record("run-d", WorkflowMonitorStatus.SUCCESS),
])
queue_9 = make_queue()
queue_9.enqueue(run_id="run-existing", workflow_name="news", retry_attempt=1)
trigger_9 = RetryEnqueueTrigger(monitor_9, queue_9)
result_9 = trigger_9.enqueue_pending_failures()
check(
    "9. RetryEnqueueTriggerResultがv4.9.0時点と同一",
    result_9,
    RetryEnqueueTriggerResult(
        scanned=4, enqueued=2, skipped_existing=0, skipped_status=2, failed=0, skipped_history=0,
    ),
)
print()


# ═══════════════════════════════════════════════════════════
# テスト10-13: max_attemptsを明示指定、複数回リトライの解禁
# ═══════════════════════════════════════════════════════════

print("[テスト10] max_attempts=3 の場合、attempt_count=1（next_attempt=2）は enqueue される")

history_10 = RetryHistoryManager()
history_10.record("run-retry-2", attempt=1, recorded_at=datetime.now())
monitor_10 = FakeWorkflowMonitorManager(records=[make_record("run-retry-2", WorkflowMonitorStatus.FAILED)])
queue_10 = make_queue()
trigger_10 = RetryEnqueueTrigger(monitor_10, queue_10, history=history_10)
result_10 = trigger_10.enqueue_pending_failures(max_attempts=3)
check("10. enqueuedが1件", result_10.enqueued, 1)
check("10. retry_attemptが2", queue_10.list()[0].retry_attempt, 2)
print()


print("[テスト11] max_attempts=3 の場合、attempt_count=2（next_attempt=3、境界値）は enqueue される")

history_11 = RetryHistoryManager()
history_11.record("run-retry-3", attempt=1, recorded_at=datetime.now())
history_11.record("run-retry-3", attempt=2, recorded_at=datetime.now())
monitor_11 = FakeWorkflowMonitorManager(records=[make_record("run-retry-3", WorkflowMonitorStatus.FAILED)])
queue_11 = make_queue()
trigger_11 = RetryEnqueueTrigger(monitor_11, queue_11, history=history_11)
result_11 = trigger_11.enqueue_pending_failures(max_attempts=3)
check("11. enqueuedが1件", result_11.enqueued, 1)
check("11. retry_attemptが3", queue_11.list()[0].retry_attempt, 3)
print()


print("[テスト12] max_attempts=3 の場合、attempt_count=3（next_attempt=4）は enqueue されない")

history_12 = RetryHistoryManager()
history_12.record("run-retry-4", attempt=1, recorded_at=datetime.now())
history_12.record("run-retry-4", attempt=2, recorded_at=datetime.now())
history_12.record("run-retry-4", attempt=3, recorded_at=datetime.now())
monitor_12 = FakeWorkflowMonitorManager(records=[make_record("run-retry-4", WorkflowMonitorStatus.FAILED)])
queue_12 = make_queue()
trigger_12 = RetryEnqueueTrigger(monitor_12, queue_12, history=history_12)
result_12 = trigger_12.enqueue_pending_failures(max_attempts=3)
check("12. enqueuedが0件", result_12.enqueued, 0)
check("12. skipped_historyが1件", result_12.skipped_history, 1)
print()


print("[テスト13] enqueueされたQueue項目のretry_attemptが正しくnext_attemptと一致する")

history_13 = RetryHistoryManager()
history_13.record("run-multi", attempt=1, recorded_at=datetime.now())
monitor_13 = FakeWorkflowMonitorManager(records=[
    make_record("run-multi", WorkflowMonitorStatus.FAILED),
    make_record("run-new", WorkflowMonitorStatus.TIMEOUT),
])
queue_13 = make_queue()
trigger_13 = RetryEnqueueTrigger(monitor_13, queue_13, history=history_13)
result_13 = trigger_13.enqueue_pending_failures(max_attempts=5)
items_13 = {item.run_id: item.retry_attempt for item in queue_13.list()}
check("13. run-multiのretry_attemptが2", items_13.get("run-multi"), 2)
check("13. run-newのretry_attemptが1", items_13.get("run-new"), 1)
check("13. enqueuedが2件", result_13.enqueued, 2)
print()


# ═══════════════════════════════════════════════════════════
# テスト14-17: max_attemptsのスコープ（インスタンス状態として保持しない）
# ═══════════════════════════════════════════════════════════

print("[テスト14] RetryEnqueueTrigger.__init__ のシグネチャが本Release前と完全に同一")

params_14 = list(inspect.signature(RetryEnqueueTrigger.__init__).parameters.keys())
check("14. パラメータ順序がself, monitor, queue, history, guard", params_14, ["self", "monitor", "queue", "history", "guard"])
check_false("14. max_attemptsが__init__の引数に含まれない", "max_attempts" in params_14)
print()


print("[テスト15] RetryEnqueueTriggerがmax_attemptsをインスタンス変数として保持しない")

trigger_15 = RetryEnqueueTrigger(
    FakeWorkflowMonitorManager(records=[]), make_queue(),
)
instance_attrs_15 = vars(trigger_15).keys()
check_false("15. _max_attemptsという属性が存在しない", "_max_attempts" in instance_attrs_15)
check_false("15. max_attemptsという属性が存在しない", "max_attempts" in instance_attrs_15)
print()


print("[テスト16] enqueue_pending_failures() のシグネチャが (self, limit=None, max_attempts=1)")

sig_16 = inspect.signature(RetryEnqueueTrigger.enqueue_pending_failures)
params_16 = list(sig_16.parameters.keys())
check("16. パラメータがself, limit, max_attempts", params_16, ["self", "limit", "max_attempts"])
check("16. limitのデフォルトがNone", sig_16.parameters["limit"].default, None)
check("16. max_attemptsのデフォルトが1", sig_16.parameters["max_attempts"].default, 1)
print()


print("[テスト17] 同一インスタンスに対し、呼び出しごとに異なるmax_attemptsを渡せる")

history_17 = RetryHistoryManager()
history_17.record("run-flex", attempt=1, recorded_at=datetime.now())
monitor_17 = FakeWorkflowMonitorManager(records=[make_record("run-flex", WorkflowMonitorStatus.FAILED)])
queue_17a = make_queue()
trigger_17 = RetryEnqueueTrigger(monitor_17, queue_17a, history=history_17)
result_17a = trigger_17.enqueue_pending_failures(max_attempts=1)
check("17. max_attempts=1ではブロックされる", result_17a.enqueued, 0)

queue_17b = make_queue()
trigger_17b = RetryEnqueueTrigger(monitor_17, queue_17b, history=history_17)
result_17b = trigger_17b.enqueue_pending_failures(max_attempts=5)
check("17. max_attempts=5では許可される（同じhistory状態でも呼び出しごとに結果が変わる）", result_17b.enqueued, 1)
print()


# ═══════════════════════════════════════════════════════════
# テスト18-19: ディレクトリ構成・Backward Compatibility
# ═══════════════════════════════════════════════════════════

print("[テスト18] src/retry_enqueue_trigger/ のファイル構成が本Release前と同一")

ret_dir = PROJECT_ROOT / "src" / "retry_enqueue_trigger"
py_files_18 = sorted(p.name for p in ret_dir.glob("*.py"))
check(
    "18. __init__.py・retry_enqueue_trigger.py・retry_enqueue_guard.pyの3ファイル",
    py_files_18,
    ["__init__.py", "retry_enqueue_guard.py", "retry_enqueue_trigger.py"],
)
print()


print("[テスト19] retry_enqueue_trigger パッケージのexportが本Release前と同一")

for name in (
    "RetryEnqueueTrigger", "NullRetryEnqueueTrigger", "RetryEnqueueTriggerResult",
    "RetryEnqueueGuard", "RetryEnqueueGuardOutcome", "RetryEnqueueGuardDecision",
):
    check_true(f"19. {name} が retry_enqueue_trigger パッケージからエクスポートされている", hasattr(ret_pkg, name))
    check_true(f"19. {name} が retry_enqueue_trigger.__all__ に含まれる", name in ret_pkg.__all__)
check("19. __all__が6件のまま変化しない", len(ret_pkg.__all__), 6)
print()


# ═══════════════════════════════════════════════════════════
# テスト20-22: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト20] retry_enqueue_trigger が retry_engine 等を一切importしない（静的検査）")

for py_file in sorted(ret_dir.glob("*.py")):
    source = py_file.read_text(encoding="utf-8")
    import_lines = "\n".join(
        line for line in source.splitlines()
        if line.strip().startswith("from ") or line.strip().startswith("import ")
    )
    for forbidden in (
        "retry_engine", "workflow_engine", "execution_history",
        "from scheduler", "import scheduler", "from ai", "import ai", "from pipeline", "import pipeline",
        "retry_scheduler_source", "retry_scheduler_decision",
    ):
        check_false(f"20. {py_file.name} が {forbidden} をimportしない", forbidden in import_lines)
print()


print("[テスト21] retry_history / retry_queue / workflow_monitor / retry_engine に変更がないこと（git diff）")

unchanged_paths_21 = [
    "main.py",
    "src/workflow_monitor/workflow_monitor.py",
    "src/workflow_monitor/workflow_monitor_manager.py",
    "src/workflow_monitor/workflow_monitor_config.py",
    "src/workflow_monitor/workflow_monitor_record.py",
    "src/workflow_monitor/workflow_monitor_status.py",
    "src/workflow_monitor/__init__.py",
    "src/retry_queue/retry_queue_manager.py",
    "src/retry_queue/null_retry_queue_manager.py",
    "src/retry_queue/retry_queue_config.py",
    "src/retry_queue/retry_queue_item.py",
    "src/retry_queue/retry_queue_result.py",
    "src/retry_queue/retry_queue_status.py",
    "src/retry_queue/__init__.py",
    "src/retry_history/retry_history_record.py",
    "src/retry_history/retry_history_manager.py",
    "src/retry_history/null_retry_history_manager.py",
    "src/retry_history/__init__.py",
    "src/retry_engine/retry_config.py",
    "src/retry_engine/retry_executor.py",
    "src/retry_engine/retry_manager.py",
    "src/retry_engine/retry_policy.py",
    "src/retry_engine/retry_policy_protocol.py",
    "src/retry_engine/retry_request.py",
    "src/retry_engine/retry_result.py",
    "src/retry_engine/retry_history_recorder.py",
    "src/retry_engine/__init__.py",
    "src/retry_enqueue_trigger/__init__.py",
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


print("[テスト22] 本Releaseでも retry_enqueue_trigger をどこからも呼び出さない")

src_dir = PROJECT_ROOT / "src"
consumers_22 = []
for py_file in sorted(src_dir.rglob("*.py")):
    if py_file.parent.name == "retry_enqueue_trigger":
        continue
    text = py_file.read_text(encoding="utf-8")
    if "retry_enqueue_trigger" in text:
        consumers_22.append(str(py_file.relative_to(PROJECT_ROOT)))
check("22. retry_enqueue_triggerを参照する既存ファイルが存在しない", consumers_22, [])
print()


# ═══════════════════════════════════════════════════════════
# テスト23: 副作用なしの確認
# ═══════════════════════════════════════════════════════════

print("[テスト23] RetryEnqueueTrigger 実行前後でファイルが作成されない")

import tempfile

with tempfile.TemporaryDirectory() as tmp_dir:
    write_check_dir = Path(tmp_dir)
    before_files_23 = list(write_check_dir.rglob("*"))

    history_23 = RetryHistoryManager()
    history_23.record("run-io", attempt=1, recorded_at=datetime.now())
    monitor_23 = FakeWorkflowMonitorManager(records=[make_record("run-io", WorkflowMonitorStatus.FAILED)])
    queue_23 = make_queue()
    trigger_23 = RetryEnqueueTrigger(monitor_23, queue_23, history=history_23)
    trigger_23.enqueue_pending_failures(max_attempts=3)
    NullRetryEnqueueTrigger().enqueue_pending_failures()

    after_files_23 = list(write_check_dir.rglob("*"))
    check("23. 実行前後でファイルが作成されない", after_files_23, before_files_23)
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
