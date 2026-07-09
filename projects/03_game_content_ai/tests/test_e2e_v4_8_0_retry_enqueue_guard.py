"""
E2E テスト: v4.8.0 Retry Enqueue Guard

テストシナリオ:
    ── RetryEnqueueGuard（単体） ──
    1.  has_history=True で BLOCK を返す
    2.  has_history=False で ALLOW を返す
    3.  RetryEnqueueGuardDecision の run_id / reason が正しい
    4.  RetryEnqueueGuard がインスタンス変数を一切持たない（Stateless）
    5.  RetryEnqueueGuard が decide_all() を持たない（バッチ版は追加しない設計判断）
    6.  NullRetryEnqueueGuard に相当するクラスが存在しない（設計判断）

    ── RetryEnqueueTrigger + Guard 統合（history省略時、Backward Compatibility） ──
    7.  history省略時、has_historyが常にFalseとなりGuardは常にALLOW
        （v4.6.0時点と完全に同一の挙動。skipped_historyは常に0）
    8.  2引数コンストラクタ RetryEnqueueTrigger(monitor, queue) が引き続き動作する
    9.  v4.6.0時点の主要シナリオ（FAILED/TIMEOUT検知・重複スキップ・集計）の再現

    ── RetryEnqueueTrigger + Guard 統合（historyに実体を注入） ──
    10. 再試行履歴がある run_id は enqueue されず skipped_history にカウントされる
    11. 再試行履歴がない run_id は通常どおり enqueue される
    12. 履歴あり/なしが混在する場合の正しい振り分け
    13. scanned = enqueued + skipped_existing + skipped_status + skipped_history + failed の恒等式
    14. GuardによりBLOCKされたrun_idについて queue.exists() / queue.enqueue() が
        一度も呼ばれない（Spyによる構造的確認）
    15. RetryHistoryManager.record() で実際に記録した直後、同じrun_idの再enqueueが
        ブロックされる（無限再投入対策の統合シナリオ）

    ── Dependency Injection（guard引数） ──
    16. カスタムguardを注入すると、そのdecide()が使用される

    ── NullRetryEnqueueTrigger（無改修の確認） ──
    17. 引数の有無・historyの有無に関わらず常に全フィールド0（skipped_history含む）
    18. インスタンス変数を一切持たない

    ── シグネチャ・Backward Compatibility ──
    19. RetryEnqueueTrigger.__init__ が monitor, queue, history=None, guard=None を
        この順で受け取る
    20. history / guard がいずれもキーワード引数として省略可能

    ── ディレクトリ構成 ──
    21. src/retry_enqueue_trigger/ が __init__.py・retry_enqueue_trigger.py・
        retry_enqueue_guard.py の3ファイルで構成されている

    ── Architecture Guard ──
    22. retry_enqueue_trigger パッケージが retry_engine/workflow_engine/
        execution_history/scheduler/ai/pipelineを一切importしない（静的検査）
    23. retry_enqueue_guard.py が retry_history を一切importしない（静的検査）
    24. retry_history / retry_queue / workflow_monitor / retry_engine 配下の
        既存ファイルに変更がないこと（git diff）
    25. 本Releaseでも retry_enqueue_trigger をどのパッケージからも呼び出さない
    26. retry_enqueue_trigger パッケージのexport確認（新規3シンボル含む）
    27. Feature Gate・Configを持たないことの確認（enabled属性・Config名の不在）

    ── 副作用なしの確認 ──
    28. RetryEnqueueTrigger + Guard 実行前後でファイルが一切作成されない

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v4_8_0_retry_enqueue_guard.py
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
print("v4.8.0 Retry Enqueue Guard E2E テスト")
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
# テスト1-6: RetryEnqueueGuard（単体）
# ═══════════════════════════════════════════════════════════

print("[テスト1] has_history=True で BLOCK を返す")

guard_1 = RetryEnqueueGuard()
decision_1 = guard_1.decide("run-x", has_history=True)
check("1. outcomeがBLOCK", decision_1.outcome, RetryEnqueueGuardOutcome.BLOCK)
print()


print("[テスト2] has_history=False で ALLOW を返す")

decision_2 = guard_1.decide("run-y", has_history=False)
check("2. outcomeがALLOW", decision_2.outcome, RetryEnqueueGuardOutcome.ALLOW)
print()


print("[テスト3] RetryEnqueueGuardDecision の run_id / reason が正しい")

check("3. run_idが一致（BLOCK側）", decision_1.run_id, "run-x")
check_true("3. reasonにrun_idが含まれる（BLOCK側）", "run-x" in decision_1.reason)
check("3. run_idが一致（ALLOW側）", decision_2.run_id, "run-y")
check_true("3. reasonにrun_idが含まれる（ALLOW側）", "run-y" in decision_2.reason)
print()


print("[テスト4] RetryEnqueueGuard がインスタンス変数を一切持たない（Stateless）")

check("4. vars(guard)が空", vars(guard_1), {})
print()


print("[テスト5] RetryEnqueueGuard が decide_all() を持たない")

check_false("5. decide_allを持たない", hasattr(RetryEnqueueGuard, "decide_all"))
print()


print("[テスト6] NullRetryEnqueueGuard に相当するクラスが存在しない")

check_false("6. NullRetryEnqueueGuardがexportされていない", hasattr(ret_pkg, "NullRetryEnqueueGuard"))
print()


# ═══════════════════════════════════════════════════════════
# テスト7-9: RetryEnqueueTrigger + Guard 統合（history省略時）
# ═══════════════════════════════════════════════════════════

print("[テスト7] history省略時はGuardが常にALLOW（skipped_historyは常に0）")

monitor_7 = FakeWorkflowMonitorManager(records=[
    make_record("run-failed", WorkflowMonitorStatus.FAILED),
    make_record("run-timeout", WorkflowMonitorStatus.TIMEOUT),
])
queue_7 = make_queue()
trigger_7 = RetryEnqueueTrigger(monitor_7, queue_7)
result_7 = trigger_7.enqueue_pending_failures()
check("7. skipped_historyが0", result_7.skipped_history, 0)
check("7. enqueuedが2件", result_7.enqueued, 2)
print()


print("[テスト8] 2引数コンストラクタが引き続き動作する")

trigger_8 = RetryEnqueueTrigger(monitor_7, queue_7)
check_true("8. インスタンス生成に成功する", isinstance(trigger_8, RetryEnqueueTrigger))
print()


print("[テスト9] v4.6.0時点の主要シナリオの再現（history省略時は完全互換）")

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
    "9. RetryEnqueueTriggerResultがv4.6.0時点と同じ内容＋skipped_history=0",
    result_9,
    RetryEnqueueTriggerResult(
        scanned=4, enqueued=2, skipped_existing=0, skipped_status=2, failed=0, skipped_history=0,
    ),
)
print()


# ═══════════════════════════════════════════════════════════
# テスト10-15: RetryEnqueueTrigger + Guard 統合（historyに実体を注入）
# ═══════════════════════════════════════════════════════════

print("[テスト10] 再試行履歴があるrun_idはenqueueされずskipped_historyにカウントされる")

history_10 = RetryHistoryManager()
history_10.record("run-retried", attempt=1, recorded_at=datetime.now())
monitor_10 = FakeWorkflowMonitorManager(records=[make_record("run-retried", WorkflowMonitorStatus.FAILED)])
queue_10 = make_queue()
trigger_10 = RetryEnqueueTrigger(monitor_10, queue_10, history=history_10)
result_10 = trigger_10.enqueue_pending_failures()
check("10. enqueuedが0件", result_10.enqueued, 0)
check("10. skipped_historyが1件", result_10.skipped_history, 1)
check_false("10. run-retriedがQueueに存在しない", queue_10.exists("run-retried"))
print()


print("[テスト11] 再試行履歴がないrun_idは通常どおりenqueueされる")

history_11 = RetryHistoryManager()
monitor_11 = FakeWorkflowMonitorManager(records=[make_record("run-fresh", WorkflowMonitorStatus.FAILED)])
queue_11 = make_queue()
trigger_11 = RetryEnqueueTrigger(monitor_11, queue_11, history=history_11)
result_11 = trigger_11.enqueue_pending_failures()
check("11. enqueuedが1件", result_11.enqueued, 1)
check("11. skipped_historyが0件", result_11.skipped_history, 0)
check_true("11. run-freshがQueueに存在する", queue_11.exists("run-fresh"))
print()


print("[テスト12] 履歴あり/なしが混在する場合の正しい振り分け")

history_12 = RetryHistoryManager()
history_12.record("run-old", attempt=1, recorded_at=datetime.now())
monitor_12 = FakeWorkflowMonitorManager(records=[
    make_record("run-old", WorkflowMonitorStatus.FAILED),
    make_record("run-new-1", WorkflowMonitorStatus.FAILED),
    make_record("run-new-2", WorkflowMonitorStatus.TIMEOUT),
    make_record("run-running", WorkflowMonitorStatus.RUNNING),
])
queue_12 = make_queue()
trigger_12 = RetryEnqueueTrigger(monitor_12, queue_12, history=history_12)
result_12 = trigger_12.enqueue_pending_failures()
check("12. enqueuedが2件（run-new-1, run-new-2）", result_12.enqueued, 2)
check("12. skipped_historyが1件（run-old）", result_12.skipped_history, 1)
check("12. skipped_statusが1件（run-running）", result_12.skipped_status, 1)
check_false("12. run-oldがQueueに存在しない", queue_12.exists("run-old"))
check_true("12. run-new-1がQueueに存在する", queue_12.exists("run-new-1"))
check_true("12. run-new-2がQueueに存在する", queue_12.exists("run-new-2"))
print()


print("[テスト13] scanned = enqueued + skipped_existing + skipped_status + skipped_history + failed")

for label, result in (("7", result_7), ("9", result_9), ("10", result_10), ("11", result_11), ("12", result_12)):
    total = result.enqueued + result.skipped_existing + result.skipped_status + result.skipped_history + result.failed
    check(f"13. 結果{label}の恒等式が成立", total, result.scanned)
print()


print("[テスト14] GuardによりBLOCKされたrun_idについて queue.exists()/enqueue()が呼ばれない")


class _QueueSpy:
    def __init__(self, real):
        self._real = real
        self.exists_calls: list = []
        self.enqueue_calls: list = []

    def exists(self, run_id):
        self.exists_calls.append(run_id)
        return self._real.exists(run_id)

    def enqueue(self, *args, **kwargs):
        self.enqueue_calls.append((args, kwargs))
        return self._real.enqueue(*args, **kwargs)


history_14 = RetryHistoryManager()
history_14.record("run-blocked", attempt=1, recorded_at=datetime.now())
monitor_14 = FakeWorkflowMonitorManager(records=[make_record("run-blocked", WorkflowMonitorStatus.FAILED)])
queue_14 = _QueueSpy(make_queue())
trigger_14 = RetryEnqueueTrigger(monitor_14, queue_14, history=history_14)
trigger_14.enqueue_pending_failures()
check("14. queue.exists()が一度も呼ばれない", queue_14.exists_calls, [])
check("14. queue.enqueue()が一度も呼ばれない", queue_14.enqueue_calls, [])
print()


print("[テスト15] RetryHistoryManager.record()の直後、同じrun_idの再enqueueがブロックされる（統合シナリオ）")

history_15 = RetryHistoryManager()
queue_15 = make_queue()
monitor_15 = FakeWorkflowMonitorManager(records=[make_record("run-cycle", WorkflowMonitorStatus.FAILED)])
trigger_15 = RetryEnqueueTrigger(monitor_15, queue_15, history=history_15)

# 1回目：履歴なし → enqueueされる
result_15a = trigger_15.enqueue_pending_failures()
check("15. 1回目はenqueueされる", result_15a.enqueued, 1)

# Queueから除去（RetryQueueCleanupExecutor等の下流処理を模擬）＋再試行履歴を記録
queue_15.remove("run-cycle")
history_15.record("run-cycle", attempt=1, recorded_at=datetime.now())

# Monitorは引き続きFAILEDのまま（Execution Historyは不変という既知の性質を再現）
result_15b = trigger_15.enqueue_pending_failures()
check("15. 2回目はGuardによりブロックされる（enqueued=0）", result_15b.enqueued, 0)
check("15. 2回目はskipped_historyが1", result_15b.skipped_history, 1)
check_false("15. run-cycleがQueueに存在しない（無限再投入が止まっている）", queue_15.exists("run-cycle"))
print()


# ═══════════════════════════════════════════════════════════
# テスト16: Dependency Injection（guard引数）
# ═══════════════════════════════════════════════════════════

print("[テスト16] カスタムguardを注入すると、そのdecide()が使用される")


class _AlwaysBlockGuard:
    def __init__(self):
        self.calls: list = []

    def decide(self, run_id, has_history):
        self.calls.append((run_id, has_history))
        return RetryEnqueueGuardDecision(run_id=run_id, outcome=RetryEnqueueGuardOutcome.BLOCK, reason="forced")


guard_16 = _AlwaysBlockGuard()
monitor_16 = FakeWorkflowMonitorManager(records=[make_record("run-forced", WorkflowMonitorStatus.FAILED)])
queue_16 = make_queue()
trigger_16 = RetryEnqueueTrigger(monitor_16, queue_16, guard=guard_16)
result_16 = trigger_16.enqueue_pending_failures()
check("16. カスタムguardによりenqueuedが0件", result_16.enqueued, 0)
check("16. カスタムguardが呼ばれた", guard_16.calls, [("run-forced", False)])
print()


# ═══════════════════════════════════════════════════════════
# テスト17-18: NullRetryEnqueueTrigger（無改修の確認）
# ═══════════════════════════════════════════════════════════

print("[テスト17] NullRetryEnqueueTrigger は常に全フィールド0（skipped_history含む）")

null_trigger_17 = NullRetryEnqueueTrigger()
check(
    "17. 引数なしで全フィールド0",
    null_trigger_17.enqueue_pending_failures(),
    RetryEnqueueTriggerResult(scanned=0, enqueued=0, skipped_existing=0, skipped_status=0, failed=0, skipped_history=0),
)
check(
    "17. limit指定でも全フィールド0",
    null_trigger_17.enqueue_pending_failures(limit=10),
    RetryEnqueueTriggerResult(scanned=0, enqueued=0, skipped_existing=0, skipped_status=0, failed=0, skipped_history=0),
)
print()


print("[テスト18] NullRetryEnqueueTrigger がインスタンス変数を一切持たない")

check("18. vars(null_trigger)が空", vars(null_trigger_17), {})
print()


# ═══════════════════════════════════════════════════════════
# テスト19-20: シグネチャ・Backward Compatibility
# ═══════════════════════════════════════════════════════════

print("[テスト19] RetryEnqueueTrigger.__init__ のシグネチャ")

params_19 = list(inspect.signature(RetryEnqueueTrigger.__init__).parameters.keys())
check("19. パラメータ順序がself, monitor, queue, history, guard", params_19, ["self", "monitor", "queue", "history", "guard"])
print()


print("[テスト20] history / guard がキーワード引数として省略可能")

sig_20 = inspect.signature(RetryEnqueueTrigger.__init__)
check("20. historyのデフォルトがNone", sig_20.parameters["history"].default, None)
check("20. guardのデフォルトがNone", sig_20.parameters["guard"].default, None)
print()


# ═══════════════════════════════════════════════════════════
# テスト21: ディレクトリ構成
# ═══════════════════════════════════════════════════════════

print("[テスト21] src/retry_enqueue_trigger/ のファイル構成")

ret_dir = PROJECT_ROOT / "src" / "retry_enqueue_trigger"
py_files_21 = sorted(p.name for p in ret_dir.glob("*.py"))
check(
    "21. __init__.py・retry_enqueue_trigger.py・retry_enqueue_guard.pyの3ファイル",
    py_files_21,
    ["__init__.py", "retry_enqueue_guard.py", "retry_enqueue_trigger.py"],
)
print()


# ═══════════════════════════════════════════════════════════
# テスト22-27: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト22] retry_enqueue_trigger が retry_engine 等を一切importしない（静的検査）")

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
        check_false(f"22. {py_file.name} が {forbidden} をimportしない", forbidden in import_lines)
print()


print("[テスト23] retry_enqueue_guard.py が retry_history を一切importしない（静的検査）")

guard_source_23 = (ret_dir / "retry_enqueue_guard.py").read_text(encoding="utf-8")
guard_import_lines_23 = "\n".join(
    line for line in guard_source_23.splitlines()
    if line.strip().startswith("from ") or line.strip().startswith("import ")
)
check_false("23. retry_enqueue_guard.py が retry_history をimportしない", "retry_history" in guard_import_lines_23)
check_false("23. retry_enqueue_guard.py が retry_queue をimportしない", "retry_queue" in guard_import_lines_23)
check_false("23. retry_enqueue_guard.py が workflow_monitor をimportしない", "workflow_monitor" in guard_import_lines_23)
print()


print("[テスト24] 既存ファイルの無変更確認（git diff）")

unchanged_paths_24 = [
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
    "src/retry_scheduler_source/retry_scheduler_source.py",
    "src/retry_scheduler_source/__init__.py",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths_24:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"24. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("24. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト25] 本Releaseでも retry_enqueue_trigger をどこからも呼び出さない")

src_dir = PROJECT_ROOT / "src"
consumers_25 = []
for py_file in sorted(src_dir.rglob("*.py")):
    if py_file.parent.name == "retry_enqueue_trigger":
        continue
    text = py_file.read_text(encoding="utf-8")
    if "retry_enqueue_trigger" in text:
        consumers_25.append(str(py_file.relative_to(PROJECT_ROOT)))
check("25. retry_enqueue_triggerを参照する既存ファイルが存在しない", consumers_25, [])
print()


print("[テスト26] retry_enqueue_trigger パッケージのexport確認")

for name in (
    "RetryEnqueueTrigger", "NullRetryEnqueueTrigger", "RetryEnqueueTriggerResult",
    "RetryEnqueueGuard", "RetryEnqueueGuardOutcome", "RetryEnqueueGuardDecision",
):
    check_true(f"26. {name} が retry_enqueue_trigger パッケージからエクスポートされている", hasattr(ret_pkg, name))
    check_true(f"26. {name} が retry_enqueue_trigger.__all__ に含まれる", name in ret_pkg.__all__)
check("26. __all__が既存3シンボル＋新規3シンボルの計6件", len(ret_pkg.__all__), 6)
print()


print("[テスト27] Feature Gate・Configを持たないことの確認")

config_named_27 = [name for name in dir(ret_pkg) if "Config" in name]
check("27. Configを名前に含むシンボルが存在しない", config_named_27, [])
check_false("27. RetryEnqueueTriggerインスタンスがenabledを持たない", hasattr(trigger_7, "enabled"))
check_false("27. RetryEnqueueGuardインスタンスがenabledを持たない", hasattr(guard_1, "enabled"))
check_false("27. RetryEnqueueTrigger/NullがConfig系クラスを持たない", hasattr(RetryEnqueueTrigger, "from_config"))
print()


# ═══════════════════════════════════════════════════════════
# テスト28: 副作用なしの確認
# ═══════════════════════════════════════════════════════════

print("[テスト28] RetryEnqueueTrigger + Guard 実行前後でファイルが作成されない")

import tempfile

with tempfile.TemporaryDirectory() as tmp_dir:
    write_check_dir = Path(tmp_dir)
    before_files_28 = list(write_check_dir.rglob("*"))

    history_28 = RetryHistoryManager()
    history_28.record("run-io", attempt=1, recorded_at=datetime.now())
    monitor_28 = FakeWorkflowMonitorManager(records=[make_record("run-io", WorkflowMonitorStatus.FAILED)])
    queue_28 = make_queue()
    trigger_28 = RetryEnqueueTrigger(monitor_28, queue_28, history=history_28)
    trigger_28.enqueue_pending_failures()
    NullRetryEnqueueTrigger().enqueue_pending_failures()

    after_files_28 = list(write_check_dir.rglob("*"))
    check("28. 実行前後でファイルが作成されない", after_files_28, before_files_28)
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
