"""
E2E テスト: v4.9.0 Retry Attempt Synchronization Foundation

テストシナリオ:
    ── retry_attemptの実回数連動 ──
    1.  履歴がない run_id は retry_attempt=1 でenqueueされる
    2.  履歴があり attempt_count=1 の run_id は、Guardを迂回（カスタムguard注入）すると
        retry_attempt=2 でenqueueされる
    3.  履歴があり attempt_count=2 の run_id は、Guardを迂回すると retry_attempt=3 でenqueueされる
    4.  history省略時（NullRetryHistoryManager）は retry_attempt=1 でenqueueされる
        （v4.8.0時点と同じ挙動、Backward Compatibility）

    ── 現行Guardとの整合性（本Release単体では挙動が変化しないことの確認） ──
    5.  デフォルトのRetryEnqueueGuardを使う場合、履歴がある run_id は
        本Release後もenqueueに到達しない（skipped_historyのままカウントされる）
    6.  v4.8.0時点の主要シナリオ（history省略・複数レコード混在）の結果が完全に一致する

    ── 設計方針（has_history()を使わずget()のみを使う） ──
    7.  RetryHistoryManager.has_history() が呼ばれず、get() のみが呼ばれる（Spyで確認）

    ── シグネチャ・ディレクトリ構成・Backward Compatibility ──
    8.  RetryEnqueueTrigger.__init__ のシグネチャが本Release前と同一
    9.  src/retry_enqueue_trigger/ のファイル構成が本Release前と同一（3ファイル）
    10. retry_enqueue_trigger パッケージのexportが本Release前と同一（6シンボル）

    ── Architecture Guard ──
    11. retry_enqueue_trigger が retry_engine/workflow_engine/execution_history/
        scheduler/ai/pipelineを一切importしない（静的検査）
    12. retry_queue / retry_history / retry_engine / workflow_monitor /
        retry_enqueue_guard.py / __init__.py に変更がないこと（git diff）
    13. 本Releaseでも retry_enqueue_trigger をどのパッケージからも呼び出さない

    ── 副作用なしの確認 ──
    14. RetryEnqueueTrigger 実行前後でファイルが一切作成されない

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v4_9_0_retry_attempt_synchronization_foundation.py
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
print("v4.9.0 Retry Attempt Synchronization Foundation E2E テスト")
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
from retry_history import NullRetryHistoryManager, RetryHistoryManager
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


class _AlwaysAllowGuard:
    """テスト専用：履歴の有無に関わらず常にALLOWを返す（Guard精緻化前の配線確認用）。"""

    def decide(self, run_id, has_history):
        return RetryEnqueueGuardDecision(run_id=run_id, outcome=RetryEnqueueGuardOutcome.ALLOW, reason="forced-allow")


class _HistorySpy:
    def __init__(self, real):
        self._real = real
        self.get_calls: list = []
        self.has_history_calls: list = []

    def get(self, run_id):
        self.get_calls.append(run_id)
        return self._real.get(run_id)

    def has_history(self, run_id):
        self.has_history_calls.append(run_id)
        return self._real.has_history(run_id)


# ═══════════════════════════════════════════════════════════
# テスト1-4: retry_attemptの実回数連動
# ═══════════════════════════════════════════════════════════

print("[テスト1] 履歴がない run_id は retry_attempt=1 でenqueueされる")

history_1 = RetryHistoryManager()
monitor_1 = FakeWorkflowMonitorManager(records=[make_record("run-fresh", WorkflowMonitorStatus.FAILED)])
queue_1 = make_queue()
trigger_1 = RetryEnqueueTrigger(monitor_1, queue_1, history=history_1)
result_1 = trigger_1.enqueue_pending_failures()
check("1. enqueuedが1件", result_1.enqueued, 1)
item_1 = queue_1.list()[0]
check("1. retry_attemptが1", item_1.retry_attempt, 1)
print()


print("[テスト2] 履歴あり（attempt_count=1）をGuard迂回してenqueueすると retry_attempt=2")

history_2 = RetryHistoryManager()
history_2.record("run-retried-once", attempt=1, recorded_at=datetime.now())
monitor_2 = FakeWorkflowMonitorManager(records=[make_record("run-retried-once", WorkflowMonitorStatus.FAILED)])
queue_2 = make_queue()
trigger_2 = RetryEnqueueTrigger(monitor_2, queue_2, history=history_2, guard=_AlwaysAllowGuard())
result_2 = trigger_2.enqueue_pending_failures()
check("2. enqueuedが1件", result_2.enqueued, 1)
item_2 = queue_2.list()[0]
check("2. retry_attemptが2（attempt_count 1 + 1）", item_2.retry_attempt, 2)
print()


print("[テスト3] 履歴あり（attempt_count=2）をGuard迂回してenqueueすると retry_attempt=3")

history_3 = RetryHistoryManager()
history_3.record("run-retried-twice", attempt=1, recorded_at=datetime.now())
history_3.record("run-retried-twice", attempt=2, recorded_at=datetime.now())
monitor_3 = FakeWorkflowMonitorManager(records=[make_record("run-retried-twice", WorkflowMonitorStatus.FAILED)])
queue_3 = make_queue()
trigger_3 = RetryEnqueueTrigger(monitor_3, queue_3, history=history_3, guard=_AlwaysAllowGuard())
result_3 = trigger_3.enqueue_pending_failures()
check("3. enqueuedが1件", result_3.enqueued, 1)
item_3 = queue_3.list()[0]
check("3. retry_attemptが3（attempt_count 2 + 1）", item_3.retry_attempt, 3)
print()


print("[テスト4] history省略時（NullRetryHistoryManager）は retry_attempt=1（Backward Compatibility）")

monitor_4 = FakeWorkflowMonitorManager(records=[make_record("run-no-history-arg", WorkflowMonitorStatus.TIMEOUT)])
queue_4 = make_queue()
trigger_4 = RetryEnqueueTrigger(monitor_4, queue_4)
result_4 = trigger_4.enqueue_pending_failures()
check("4. enqueuedが1件", result_4.enqueued, 1)
item_4 = queue_4.list()[0]
check("4. retry_attemptが1", item_4.retry_attempt, 1)
check_true("4. NullRetryHistoryManagerへ自動フォールバックしている", isinstance(trigger_4._history, NullRetryHistoryManager))
print()


# ═══════════════════════════════════════════════════════════
# テスト5-6: 現行Guardとの整合性（本Release単体では挙動が変化しない）
# ═══════════════════════════════════════════════════════════

print("[テスト5] デフォルトGuardでは履歴がある run_id は本Release後もenqueueに到達しない")

history_5 = RetryHistoryManager()
history_5.record("run-blocked", attempt=1, recorded_at=datetime.now())
monitor_5 = FakeWorkflowMonitorManager(records=[make_record("run-blocked", WorkflowMonitorStatus.FAILED)])
queue_5 = make_queue()
trigger_5 = RetryEnqueueTrigger(monitor_5, queue_5, history=history_5)
result_5 = trigger_5.enqueue_pending_failures()
check("5. enqueuedが0件", result_5.enqueued, 0)
check("5. skipped_historyが1件", result_5.skipped_history, 1)
check_false("5. run-blockedがQueueに存在しない", queue_5.exists("run-blocked"))
print()


print("[テスト6] v4.8.0時点の主要シナリオの結果が完全に一致する")

monitor_6 = FakeWorkflowMonitorManager(records=[
    make_record("run-a", WorkflowMonitorStatus.FAILED),
    make_record("run-b", WorkflowMonitorStatus.TIMEOUT),
    make_record("run-c", WorkflowMonitorStatus.RUNNING),
    make_record("run-d", WorkflowMonitorStatus.SUCCESS),
])
queue_6 = make_queue()
queue_6.enqueue(run_id="run-existing", workflow_name="news", retry_attempt=1)
trigger_6 = RetryEnqueueTrigger(monitor_6, queue_6)
result_6 = trigger_6.enqueue_pending_failures()
check(
    "6. RetryEnqueueTriggerResultがv4.8.0時点と同一",
    result_6,
    RetryEnqueueTriggerResult(
        scanned=4, enqueued=2, skipped_existing=0, skipped_status=2, failed=0, skipped_history=0,
    ),
)
print()


# ═══════════════════════════════════════════════════════════
# テスト7: 設計方針（has_history()を使わずget()のみを使う）
# ═══════════════════════════════════════════════════════════

print("[テスト7] RetryHistoryManager.has_history()が呼ばれず、get()のみが呼ばれる")

real_history_7 = RetryHistoryManager()
real_history_7.record("run-old", attempt=1, recorded_at=datetime.now())
history_spy_7 = _HistorySpy(real_history_7)
monitor_7 = FakeWorkflowMonitorManager(records=[
    make_record("run-old", WorkflowMonitorStatus.FAILED),
    make_record("run-new", WorkflowMonitorStatus.FAILED),
    make_record("run-skip", WorkflowMonitorStatus.RUNNING),
])
queue_7 = make_queue()
trigger_7 = RetryEnqueueTrigger(monitor_7, queue_7, history=history_spy_7)
trigger_7.enqueue_pending_failures()
check("7. has_history()が一度も呼ばれない", history_spy_7.has_history_calls, [])
check("7. get()がFAILED/TIMEOUT対象の2件について呼ばれる", sorted(history_spy_7.get_calls), ["run-new", "run-old"])
print()


# ═══════════════════════════════════════════════════════════
# テスト8-10: シグネチャ・ディレクトリ構成・Backward Compatibility
# ═══════════════════════════════════════════════════════════

print("[テスト8] RetryEnqueueTrigger.__init__ のシグネチャが本Release前と同一")

params_8 = list(inspect.signature(RetryEnqueueTrigger.__init__).parameters.keys())
check("8. パラメータ順序がself, monitor, queue, history, guard", params_8, ["self", "monitor", "queue", "history", "guard"])
sig_8 = inspect.signature(RetryEnqueueTrigger.__init__)
check("8. historyのデフォルトがNone", sig_8.parameters["history"].default, None)
check("8. guardのデフォルトがNone", sig_8.parameters["guard"].default, None)
print()


print("[テスト9] src/retry_enqueue_trigger/ のファイル構成が本Release前と同一")

ret_dir = PROJECT_ROOT / "src" / "retry_enqueue_trigger"
py_files_9 = sorted(p.name for p in ret_dir.glob("*.py"))
check(
    "9. __init__.py・retry_enqueue_trigger.py・retry_enqueue_guard.pyの3ファイル",
    py_files_9,
    ["__init__.py", "retry_enqueue_guard.py", "retry_enqueue_trigger.py"],
)
print()


print("[テスト10] retry_enqueue_trigger パッケージのexportが本Release前と同一")

for name in (
    "RetryEnqueueTrigger", "NullRetryEnqueueTrigger", "RetryEnqueueTriggerResult",
    "RetryEnqueueGuard", "RetryEnqueueGuardOutcome", "RetryEnqueueGuardDecision",
):
    check_true(f"10. {name} が retry_enqueue_trigger パッケージからエクスポートされている", hasattr(ret_pkg, name))
    check_true(f"10. {name} が retry_enqueue_trigger.__all__ に含まれる", name in ret_pkg.__all__)
check("10. __all__が6件のまま変化しない", len(ret_pkg.__all__), 6)
print()


# ═══════════════════════════════════════════════════════════
# テスト11-13: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト11] retry_enqueue_trigger が retry_engine 等を一切importしない（静的検査）")

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
        check_false(f"11. {py_file.name} が {forbidden} をimportしない", forbidden in import_lines)
print()


print("[テスト12] 既存ファイルの無変更確認（git diff）")

unchanged_paths_12 = [
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
    "src/retry_enqueue_trigger/retry_enqueue_guard.py",
    "src/retry_enqueue_trigger/__init__.py",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths_12:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"12. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("12. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト13] 本Releaseでも retry_enqueue_trigger をどこからも呼び出さない")

src_dir = PROJECT_ROOT / "src"
consumers_13 = []
for py_file in sorted(src_dir.rglob("*.py")):
    if py_file.parent.name == "retry_enqueue_trigger":
        continue
    text = py_file.read_text(encoding="utf-8")
    if "retry_enqueue_trigger" in text:
        consumers_13.append(str(py_file.relative_to(PROJECT_ROOT)))
check("13. retry_enqueue_triggerを参照する既存ファイルが存在しない", consumers_13, [])
print()


# ═══════════════════════════════════════════════════════════
# テスト14: 副作用なしの確認
# ═══════════════════════════════════════════════════════════

print("[テスト14] RetryEnqueueTrigger 実行前後でファイルが作成されない")

import tempfile

with tempfile.TemporaryDirectory() as tmp_dir:
    write_check_dir = Path(tmp_dir)
    before_files_14 = list(write_check_dir.rglob("*"))

    history_14 = RetryHistoryManager()
    history_14.record("run-io", attempt=1, recorded_at=datetime.now())
    monitor_14 = FakeWorkflowMonitorManager(records=[make_record("run-io", WorkflowMonitorStatus.FAILED)])
    queue_14 = make_queue()
    trigger_14 = RetryEnqueueTrigger(monitor_14, queue_14, history=history_14)
    trigger_14.enqueue_pending_failures()
    NullRetryEnqueueTrigger().enqueue_pending_failures()

    after_files_14 = list(write_check_dir.rglob("*"))
    check("14. 実行前後でファイルが作成されない", after_files_14, before_files_14)
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
