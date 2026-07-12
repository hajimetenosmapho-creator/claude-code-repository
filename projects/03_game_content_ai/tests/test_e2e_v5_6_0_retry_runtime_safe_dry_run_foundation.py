"""
E2E テスト: v5.6.0 Retry Runtime Safe Dry Run Foundation

テストシナリオ（docs/design/retry_runtime_safe_dry_run_foundation.md 対応）:
    ── RetryOutcome.DRY_RUNの追加 ──
    1.  RetryOutcomeにDRY_RUNメンバーが存在する
    2.  RetryOutcome.DRY_RUN.value == "dry_run"

    ── RetryExecutor.execute()のdry_run分岐（単体） ──
    3.  dry_run=Trueの場合、outcome=RetryOutcome.DRY_RUNが返る
    4.  dry_run=Falseの場合、outcome=RetryOutcome.RETRIED が返る（既存動作維持）
    5.  dry_run=Trueの場合でもWorkflowEngineManager.run()は呼び出される
    6.  WorkflowEngineManager.run()にdry_run=Trueがそのまま伝播する
    7.  dry_run=TrueでもworkflowEngineResultが保持される（可視化のため）

    ── Decider/Executor群がDRY_RUNを無改修のまま安全側に倒すこと（単体） ──
    8.  RetryQueueUpdateDeciderがDRY_RUNをNOOPと判定する
    9.  RetryQueueRemovalExecutorがDRY_RUN由来のNOOPでqueue.removeを呼ばない
    10. RetryHistoryRecordExecutorがDRY_RUNでrecord_fnを呼ばない
    11. RetryQueueCleanupDecider（v4.3.0、SKIPPED専用）がDRY_RUN由来のNOOPをKEEPと判定する
    12. classify_reason()がDRY_RUN由来のNOOPに対してRetryCleanupReason.DRY_RUNを返す
        （例外が発生しないこと自体が本Releaseの核心）
    13. classify_terminality(DRY_RUN) が TRANSIENT を返す
    14. RetryQueueTerminalCleanupDeciderがDRY_RUN由来のNOOPをKEEPと判定し、例外を出さない

    ── 未知のRetryOutcomeに対するfail-fast動作が維持されていること ──
    15. classify_reason()は、SKIPPED/NOT_FOUND/DISABLED/DRY_RUN以外の未知の値に対しては
        引き続きValueErrorを送出する

    ── RetryRuntimeOrchestrator.run_once(dry_run=...)の実End-to-Endシナリオ ──
    16. run_once(dry_run=True)：Queueが除去されず残ったままであること
    17. run_once(dry_run=True)：Historyに記録されないこと
    18. run_once(dry_run=True)：execution_results[0].outcome が DRY_RUN であること
    19. run_once(dry_run=True)：WorkflowEngineManager.run()にdry_run=Trueが伝播すること
    20. run_once(dry_run=True)：trigger.enqueue_pending_failures()は通常どおり実行され
        Queueへの新規登録自体は行われること（Enqueue側は対象外という設計どおり）
    21. run_once(dry_run=False)：既存動作が完全に維持されること（Queue除去・History記録）
    22. run_once()：dry_run省略時のデフォルトがFalseであること（後方互換性）

    ── Architecture Guard ──
    23. workflow_monitor / retry_queue / retry_history / retry_enqueue_trigger /
        workflow_engine / ai / execution_history / scheduler / retry_scheduler_source /
        retry_scheduler_decision / retry_composition に変更がないこと（git diff）
    24. retry_manager.py / retry_execution_coordinator.py / retry_queue_update_decider.py /
        retry_history_recorder.py / retry_queue_removal_executor.py /
        retry_queue_cleanup_decider.py / retry_queue_cleanup_executor.py /
        retry_queue_terminal_cleanup_executor.py が本Releaseでも無改修であること
    25. scripts/run_retry_runtime.py が本Releaseでも無改修であること（CLI変更は対象外）
    26. run_once()のシグネチャが (self, dry_run=False) であること

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v5_6_0_retry_runtime_safe_dry_run_foundation.py
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


def check(label: str, actual, expected):
    ok = actual == expected
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
print("v5.6.0 Retry Runtime Safe Dry Run Foundation E2E テスト")
print("=" * 60)
print()

from workflow_engine import WorkflowEngineResult
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus
from scheduler import SchedulerEngine
from retry_engine import (
    DEFAULT_TARGET_STATUSES,
    RETRY_OUTCOME_TERMINALITY,
    RetryCleanupReason,
    RetryExecutionResult,
    RetryExecutor,
    RetryHistoryRecordExecutor,
    RetryManager,
    RetryOutcome,
    RetryOutcomeTerminality,
    RetryPolicy,
    RetryQueueCleanupDecider,
    RetryQueueCleanupOutcome,
    RetryQueueRemovalExecutor,
    RetryQueueTerminalCleanupDecider,
    RetryQueueUpdateDecider,
    RetryQueueUpdateOutcome,
    RetryRequest,
    classify_reason,
    classify_terminality,
)
from retry_enqueue_trigger import RetryEnqueueGuard, RetryEnqueueTrigger
from retry_history import RetryHistoryManager
from retry_queue import RetryQueueConfig, RetryQueueManager
from retry_scheduler_decision import RetrySchedulerDecision
from retry_scheduler_source import RetrySchedulerSource
from retry_runtime_orchestrator import RetryRuntimeOrchestrator


# ─── Fake群 ───

class FakeWorkflowEngineManager:
    """WorkflowEngineManagerを模した最小限のFake。run()呼び出しを記録する。"""

    def __init__(self, result: WorkflowEngineResult):
        self.calls: list[dict] = []
        self._result = result

    def run(self, event, dry_run: bool = False) -> WorkflowEngineResult:
        self.calls.append({"event": event, "dry_run": dry_run})
        return self._result


class FakeWorkflowMonitorManager:
    def __init__(self, records: dict):
        self._records = records

    def get_status(self, run_id: str):
        return self._records.get(run_id)

    def list_status(self, limit=None):
        return list(self._records.values())


def make_record(run_id: str, monitor_status: WorkflowMonitorStatus, job_id: str = "job-1") -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=monitor_status,
        source_status=monitor_status.value, source="manual", job_id=job_id,
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=[],
    )


def make_success_engine_result() -> WorkflowEngineResult:
    return WorkflowEngineResult(
        steps=[], overall_success=True, stopped_early=False,
        started_at=datetime.now(), finished_at=datetime.now(),
    )


class FakeCandidate:
    def __init__(self, run_id: str, retry_attempt: int = 1):
        self.run_id = run_id
        self.retry_attempt = retry_attempt


def make_execution_result(run_id: str, outcome: RetryOutcome, overall_success: bool = True) -> RetryExecutionResult:
    """RetryQueueUpdateDecider等の単体テスト用に、最小限のRetryExecutionResultを組み立てる。"""
    from retry_engine.retry_event_dispatcher import RetryDispatchEvent
    from retry_engine.retry_event_consumer import RetryCandidateEvent
    from retry_engine.retry_result import RetryResult

    candidate = FakeCandidate(run_id=run_id)
    candidate_event = RetryCandidateEvent(run_id=run_id, candidate=candidate, source_event=None)
    dispatch_event = RetryDispatchEvent(candidate_event=candidate_event, dispatchable=True)

    workflow_engine_result = None
    if outcome in (RetryOutcome.RETRIED, RetryOutcome.DRY_RUN):
        workflow_engine_result = WorkflowEngineResult(
            steps=[], overall_success=overall_success, stopped_early=False,
            started_at=datetime.now(), finished_at=datetime.now(),
        )
    retry_result = RetryResult(
        original_run_id=run_id, outcome=outcome, attempt=1,
        monitor_status=WorkflowMonitorStatus.FAILED if outcome != RetryOutcome.NOT_FOUND else None,
        reason=None, workflow_engine_result=workflow_engine_result,
    )
    return RetryExecutionResult(dispatch_event=dispatch_event, retry_result=retry_result)


# ═══════════════════════════════════════════════════════════
# テスト1-2: RetryOutcome.DRY_RUNの追加
# ═══════════════════════════════════════════════════════════

print("[テスト1-2] RetryOutcome.DRY_RUNの追加")
check_true("1. RetryOutcomeにDRY_RUNメンバーが存在する", hasattr(RetryOutcome, "DRY_RUN"))
check("2. RetryOutcome.DRY_RUN.value == 'dry_run'", RetryOutcome.DRY_RUN.value, "dry_run")
print()


# ═══════════════════════════════════════════════════════════
# テスト3-7: RetryExecutor.execute()のdry_run分岐（単体）
# ═══════════════════════════════════════════════════════════

print("[テスト3-7] RetryExecutor.execute()のdry_run分岐")

engine_result_37 = make_success_engine_result()
fake_engine_37 = FakeWorkflowEngineManager(engine_result_37)
executor_37 = RetryExecutor(workflow_engine_manager=fake_engine_37)
record_37 = make_record("run-dry", WorkflowMonitorStatus.FAILED)

request_dry = RetryRequest(run_id="run-dry", attempt=1, requested_at=datetime.now(), dry_run=True)
result_dry = executor_37.execute(request_dry, record_37)

check("3. dry_run=Trueでoutcome=DRY_RUN", result_dry.outcome, RetryOutcome.DRY_RUN)

request_real = RetryRequest(run_id="run-real", attempt=1, requested_at=datetime.now(), dry_run=False)
record_real = make_record("run-real", WorkflowMonitorStatus.FAILED)
result_real = executor_37.execute(request_real, record_real)

check("4. dry_run=Falseでoutcome=RETRIED（既存動作維持）", result_real.outcome, RetryOutcome.RETRIED)
check("5. WorkflowEngineManager.run()が2回呼ばれている", len(fake_engine_37.calls), 2)
check_true("6. dry_run=Trueの呼び出しでdry_run=Trueが伝播している", fake_engine_37.calls[0]["dry_run"] is True)
check_true("7. dry_run=Trueでもworkflow_engine_resultが保持される", result_dry.workflow_engine_result is engine_result_37)
print()


# ═══════════════════════════════════════════════════════════
# テスト8-14: Decider/Executor群がDRY_RUNを安全側に倒すこと（単体）
# ═══════════════════════════════════════════════════════════

print("[テスト8-14] Decider/Executor群の安全性（単体）")

dry_run_execution_result = make_execution_result("run-dry-unit", RetryOutcome.DRY_RUN)

decision_8 = RetryQueueUpdateDecider().decide(dry_run_execution_result)
check("8. RetryQueueUpdateDeciderがNOOPと判定する", decision_8.outcome, RetryQueueUpdateOutcome.NOOP)

removal_calls_9: list[str] = []
removal_result_9 = RetryQueueRemovalExecutor().apply(decision_8, remove_fn=lambda run_id: removal_calls_9.append(run_id))
check("9. RetryQueueRemovalExecutorがqueue.removeを呼ばない", removal_calls_9, [])
check_false("9. attempted=False", removal_result_9.attempted)

history_calls_10: list[tuple] = []
history_result_10 = RetryHistoryRecordExecutor().record(
    dry_run_execution_result, record_fn=lambda rid, attempt, at: history_calls_10.append((rid, attempt, at))
)
check("10. RetryHistoryRecordExecutorがrecord_fnを呼ばない", history_calls_10, [])
check_false("10. recorded=False", history_result_10.recorded)

cleanup_decision_11 = RetryQueueCleanupDecider().decide(decision_8)
check("11. RetryQueueCleanupDecider（SKIPPED専用）がKEEPと判定する", cleanup_decision_11.outcome, RetryQueueCleanupOutcome.KEEP)

reason_12 = classify_reason(decision_8)
check("12. classify_reason()がRetryCleanupReason.DRY_RUNを返す（例外なし）", reason_12, RetryCleanupReason.DRY_RUN)

terminality_13 = classify_terminality(reason_12)
check("13. classify_terminality(DRY_RUN)がTRANSIENTを返す", terminality_13, RetryOutcomeTerminality.TRANSIENT)

terminal_decision_14 = RetryQueueTerminalCleanupDecider().decide(decision_8)
check("14. RetryQueueTerminalCleanupDeciderがKEEPと判定し例外を出さない", terminal_decision_14.outcome, RetryQueueCleanupOutcome.KEEP)
print()


# ═══════════════════════════════════════════════════════════
# テスト15: 未知のRetryOutcomeに対するfail-fast動作の維持
# ═══════════════════════════════════════════════════════════

print("[テスト15] 未知のRetryOutcomeに対するclassify_reason()のfail-fast動作")


class _FakeExecutionResult:
    """retry_result.outcome属性のみを持つ、RetryExecutionResultを模したダミー。"""

    def __init__(self, outcome):
        class _R:
            pass
        self.retry_result = _R()
        self.retry_result.outcome = outcome


class _UnknownOutcome:
    """既存のRetryOutcomeいずれとも一致しないダミー値。"""

    value = "unknown"


fake_decision_15 = type(decision_8)(
    execution_result=_FakeExecutionResult(_UnknownOutcome()),
    outcome=RetryQueueUpdateOutcome.NOOP,
    target_status=None,
    reason="synthetic unknown outcome for fail-fast test",
)
try:
    classify_reason(fake_decision_15)
    check_true("15. 未知の値でValueErrorが送出される", False)
except ValueError:
    check_true("15. 未知の値でValueErrorが送出される", True)
print()


# ═══════════════════════════════════════════════════════════
# テスト16-22: RetryRuntimeOrchestrator.run_once(dry_run=...)の実E2E
# ═══════════════════════════════════════════════════════════

def build_orchestrator(run_id: str, max_attempts: int = 5):
    engine_result = make_success_engine_result()
    fake_engine = FakeWorkflowEngineManager(engine_result)
    real_executor = RetryExecutor(workflow_engine_manager=fake_engine)

    real_queue = RetryQueueManager.from_config(RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0))
    real_history = RetryHistoryManager()
    real_guard = RetryEnqueueGuard()
    fake_monitor = FakeWorkflowMonitorManager({run_id: make_record(run_id, WorkflowMonitorStatus.FAILED)})
    real_trigger = RetryEnqueueTrigger(monitor=fake_monitor, queue=real_queue, history=real_history, guard=real_guard)

    real_source = RetrySchedulerSource(real_queue)
    real_decision = RetrySchedulerDecision(real_source)
    real_scheduler = SchedulerEngine(retry_source=real_source, retry_decision=real_decision)

    policy = RetryPolicy(target_statuses=DEFAULT_TARGET_STATUSES, max_attempts=max_attempts)
    real_manager = RetryManager(
        policy=policy, executor=real_executor, monitor=fake_monitor,
        queue=real_queue, history=real_history,
    )

    orchestrator = RetryRuntimeOrchestrator(
        trigger=real_trigger, scheduler=real_scheduler, manager=real_manager,
        queue=real_queue, history=real_history, policy=policy,
    )
    return orchestrator, real_queue, real_history, fake_engine


print("[テスト16-20] run_once(dry_run=True)の実E2Eシナリオ")

orchestrator_16, queue_16, history_16, fake_engine_16 = build_orchestrator("run-e2e-dry")
result_16 = orchestrator_16.run_once(dry_run=True)

check_true("16. run_once(dry_run=True)後もQueueにrun-e2e-dryが残っている", queue_16.exists("run-e2e-dry"))
check_false("17. run_once(dry_run=True)後もHistoryに記録されていない", history_16.has_history("run-e2e-dry"))
check(
    "18. execution_results[0].retry_result.outcomeがDRY_RUN",
    [r.retry_result.outcome for r in result_16.execution_results],
    [RetryOutcome.DRY_RUN],
)
check_true(
    "19. WorkflowEngineManager.run()にdry_run=Trueが伝播している",
    len(fake_engine_16.calls) == 1 and fake_engine_16.calls[0]["dry_run"] is True,
)
check("20. trigger.enqueue_pending_failuresは通常どおり実行されQueueへ登録される", result_16.trigger_result.enqueued, 1)
print()


print("[テスト21] run_once(dry_run=False)：既存動作が完全に維持される")

orchestrator_21, queue_21, history_21, fake_engine_21 = build_orchestrator("run-e2e-real")
result_21 = orchestrator_21.run_once(dry_run=False)

check_false("21. run_once(dry_run=False)後、Queueからrun-e2e-realが除去されている", queue_21.exists("run-e2e-real"))
check_true("21. run_once(dry_run=False)後、Historyに記録されている", history_21.has_history("run-e2e-real"))
check(
    "21. execution_results[0].retry_result.outcomeがRETRIED",
    [r.retry_result.outcome for r in result_21.execution_results],
    [RetryOutcome.RETRIED],
)
print()


print("[テスト22] run_once()のdry_run省略時のデフォルトがFalse（後方互換性）")

orchestrator_22, queue_22, history_22, fake_engine_22 = build_orchestrator("run-e2e-default")
result_22 = orchestrator_22.run_once()  # dry_run省略

check_false("22. dry_run省略時、Queueからrun-e2e-defaultが除去されている", queue_22.exists("run-e2e-default"))
check_true("22. dry_run省略時、Historyに記録されている", history_22.has_history("run-e2e-default"))
print()


# ═══════════════════════════════════════════════════════════
# テスト23-26: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト23] 既存パッケージに変更がないこと（git diff）")

unchanged_dirs_23 = [
    "src/workflow_monitor",
    "src/retry_queue",
    "src/retry_history",
    "src/retry_enqueue_trigger",
    "src/workflow_engine",
    "src/ai",
    "src/execution_history",
    "src/scheduler",
    "src/retry_scheduler_source",
    "src/retry_scheduler_decision",
    "src/retry_composition",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_dirs_23:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"23. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("23. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト24] 個別ファイルが本Releaseでも無改修であること")

unchanged_files_24 = [
    "src/retry_engine/retry_manager.py",
    "src/retry_engine/retry_execution_coordinator.py",
    "src/retry_engine/retry_queue_update_decider.py",
    "src/retry_engine/retry_history_recorder.py",
    "src/retry_engine/retry_queue_removal_executor.py",
    "src/retry_engine/retry_queue_cleanup_decider.py",
    "src/retry_engine/retry_queue_cleanup_executor.py",
    "src/retry_engine/retry_queue_terminal_cleanup_executor.py",
]

if git_available:
    for rel_path in unchanged_files_24:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"24. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("24. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト25] scripts/run_retry_runtime.py が本Releaseでも無改修であること（CLI変更は対象外）")

if git_available:
    completed_25 = subprocess.run(
        ["git", "diff", "--quiet", "--", "scripts/run_retry_runtime.py"],
        cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
    )
    check_true("25. scripts/run_retry_runtime.pyに変更がない（git diff）", completed_25.returncode == 0)
else:
    check_true("25. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト26] run_once()のシグネチャが (self, dry_run=False) であること")

sig_26 = inspect.signature(RetryRuntimeOrchestrator.run_once)
params_26 = list(sig_26.parameters.keys())
check("26. パラメータがself, dry_run", params_26, ["self", "dry_run"])
check("26. dry_runのデフォルト値がFalse", sig_26.parameters["dry_run"].default, False)
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
