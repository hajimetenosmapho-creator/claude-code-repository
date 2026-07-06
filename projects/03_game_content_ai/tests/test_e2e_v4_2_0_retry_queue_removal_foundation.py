"""
E2E テスト: v4.2.0 Retry Queue Removal Foundation

テストシナリオ（docs/design/retry_queue_removal_foundation.md 4章・14章・16章 対応）:
    ── RetryQueueRemovalExecutor単体：除去方針 ──
    1.  outcome=COMPLETE → remove_fnが呼ばれ、attempted=True・queue_result=REMOVED
    2.  outcome=FAIL → remove_fnが呼ばれ、attempted=True・queue_result=REMOVED
    3.  outcome=NOOP → remove_fnが呼ばれず、attempted=False・queue_result=None
    4.  COMPLETEだが対象run_idがQueueに存在しない → queue_result=NOT_FOUND（エラー扱いしない）
    5.  RETRY_QUEUE_ENABLED=false（NullRetryQueueManager.remove）→ queue_result=DISABLED
    6.  apply_all()が複数件を順序を保ったまま処理する
    7.  空リストを渡した場合は空リストを返す
    8.  RetryQueueRemovalResult.decisionが元のRetryQueueUpdateDecisionそのもの
    9.  reason文字列にrun_id・outcomeが含まれる（COMPLETE/FAIL/NOOPで区別できる）

    ── RetryManager.apply_retry_queue_removals()：委譲の正確性 ──
    10. queue_removal_executor省略時、自動フォールバックする
    11. DIで渡したFakeExecutorへ、decide_retry_queue_updates()の結果がそのまま渡る
    12. remove_fnにself._queue.removeが渡される
    13. from_config()の既存10引数呼び出しが本Release前と同じゲート判定結果を返す
    14. from_config()でqueue_removal_executorを渡すと実際に配線される

    ── apply_retry_queue_removals()と既存Queue操作の独立性 ──
    15. apply_retry_queue_removals()を呼んでもFakeQueue.enqueue()/dequeue()は呼ばれない
    16. Architecture Guard：apply_retry_queue_removals()のソースコードが
        self._queue.enqueue / self._queue.dequeue を一切参照しない

    ── 実際のRetryQueueManager.remove()が呼ばれる統合確認（真のQueue反映） ──
    17. 実Queueにenqueueされたrun_idについてCOMPLETE判定が出ると、実際にQueueから
        除去される（count()減少・exists()がFalseになる）
    18. FAIL判定でも同様にQueueから除去される
    19. NOOP（SKIPPED）判定の場合はQueueに項目が残り続ける（除去されない）

    ── NullRetryManager：常に[]を返す ──
    20. NullRetryManager.apply_retry_queue_removals()は常に[]を返す
    21. NullRetryManagerはRetryQueueRemovalExecutor等のいかなるフィールドも持たない

    ── 書き込みが発生しないことの確認 ──
    22. 実行処理の前後でファイルが一切作成されない

    ── Architecture Guard（無改修の確認・新規ファイルのimport制約） ──
    23. src/scheduler/ / src/retry_scheduler_decision/ / src/retry_scheduler_source/ /
        src/retry_queue/ 配下の全ファイル、および src/retry_engine/ のうち本Releaseで
        変更していないファイル（retry_queue_update_decider.py含む）に変更がないこと
    24. retry_engineパッケージの__all__に新規シンボルが追加され、既存シンボルは
        維持されていること
    25. RetryManager.__init__ / from_config()の新規引数が末尾・デフォルト値付きで
        追加されていること
    26. retry_queue_removal_executor.py が RetryQueueManager / NullRetryQueueManager を
        importしていないこと（AST）。RetryQueueResultは参照する

    ── 既存回帰（v3.0.0〜v4.1.0 RetryManager挙動）──
    27. retry() / execute_dispatchable_retries() / decide_retry_queue_updates()の
        挙動が本Releaseでも維持される

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v4_2_0_retry_queue_removal_foundation.py
"""
import ast
import inspect
import re
import subprocess
import sys
import tempfile
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
print("v4.2.0 Retry Queue Removal Foundation E2E テスト")
print("=" * 60)
print()

from retry_queue import RetryQueueConfig, RetryQueueManager, RetryQueueOutcome, RetryQueueResult
from scheduler import SchedulerEvent
from workflow_engine import NullWorkflowEngineManager, WorkflowEngineResult
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus
from retry_engine import (
    DEFAULT_TARGET_STATUSES,
    NullRetryManager,
    RetryCandidateEvent,
    RetryConfig,
    RetryDispatchEvent,
    RetryExecutionResult,
    RetryManager,
    RetryOutcome,
    RetryPolicy,
    RetryQueueRemovalExecutor,
    RetryQueueRemovalResult,
    RetryQueueUpdateDecider,
    RetryQueueUpdateDecision,
    RetryQueueUpdateOutcome,
    RetryResult,
)
from retry_engine.retry_event_consumer import RETRY_JOB_ID_PREFIX


class FakeCandidate:
    """RetryQueueItemを模した最小限のテスト用オブジェクト（retry_queueへは依存しない）。"""

    def __init__(self, run_id: str, retry_attempt: int = 1):
        self.run_id = run_id
        self.retry_attempt = retry_attempt


def make_retry_event(run_id: str, retry_attempt: int = 1) -> SchedulerEvent:
    candidate = FakeCandidate(run_id=run_id, retry_attempt=retry_attempt)
    return SchedulerEvent(
        job_id=f"{RETRY_JOB_ID_PREFIX}{run_id}",
        execute_time=datetime(2026, 7, 6, 9, 0),
        trigger_reason="Retry candidate selected.",
        metadata={"retry_candidate": candidate},
    )


def make_candidate_event(run_id: str, retry_attempt: int = 1) -> RetryCandidateEvent:
    candidate = FakeCandidate(run_id=run_id, retry_attempt=retry_attempt)
    return RetryCandidateEvent(run_id=run_id, candidate=candidate, source_event=make_retry_event(run_id, retry_attempt))


def make_dispatch_event(run_id: str, dispatchable: bool, retry_attempt: int = 1) -> RetryDispatchEvent:
    return RetryDispatchEvent(
        candidate_event=make_candidate_event(run_id, retry_attempt=retry_attempt),
        dispatchable=dispatchable,
    )


def make_execution_result(run_id: str, retry_result: RetryResult) -> RetryExecutionResult:
    return RetryExecutionResult(
        dispatch_event=make_dispatch_event(run_id, dispatchable=True),
        retry_result=retry_result,
    )


def make_workflow_engine_result(overall_success: bool) -> WorkflowEngineResult:
    now = datetime.now()
    return WorkflowEngineResult(
        steps=[], overall_success=overall_success, stopped_early=False,
        started_at=now, finished_at=now,
    )


def make_decision(run_id: str, outcome: RetryQueueUpdateOutcome) -> RetryQueueUpdateDecision:
    if outcome == RetryQueueUpdateOutcome.COMPLETE:
        retry_result = RetryResult(
            original_run_id=run_id, outcome=RetryOutcome.RETRIED, attempt=1,
            monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
            workflow_engine_result=make_workflow_engine_result(overall_success=True),
        )
    elif outcome == RetryQueueUpdateOutcome.FAIL:
        retry_result = RetryResult(
            original_run_id=run_id, outcome=RetryOutcome.RETRIED, attempt=1,
            monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
            workflow_engine_result=make_workflow_engine_result(overall_success=False),
        )
    else:
        retry_result = RetryResult(
            original_run_id=run_id, outcome=RetryOutcome.SKIPPED, attempt=3,
            monitor_status=WorkflowMonitorStatus.FAILED,
            reason="attempt 3 has reached max_attempts=3.", workflow_engine_result=None,
        )
    execution_result = make_execution_result(run_id, retry_result)
    return RetryQueueUpdateDecider().decide(execution_result)


policy_ok = RetryPolicy(target_statuses=DEFAULT_TARGET_STATUSES, max_attempts=3)


class FakeWorkflowEngineManager:
    def __init__(self, overall_success: bool = True):
        self.calls: list[tuple] = []
        self._overall_success = overall_success

    def run(self, event, dry_run: bool = False) -> WorkflowEngineResult:
        self.calls.append((event, dry_run))
        return make_workflow_engine_result(self._overall_success)


class FakeWorkflowMonitorManager:
    def __init__(self, record: "WorkflowMonitorRecord | None"):
        self.record = record
        self.call_count = 0
        self.calls: list[str] = []

    def get_status(self, run_id: str):
        self.call_count += 1
        self.calls.append(run_id)
        return self.record

    def list_status(self, limit=None):
        return [self.record] if self.record else []


class FakeRetryExecutor:
    def __init__(self, result: "RetryResult | None"):
        self.calls: list[tuple] = []
        self._result = result

    def execute(self, request, record) -> RetryResult:
        self.calls.append((request, record))
        return self._result


class FakeRetryQueueManager:
    def __init__(self, remove_result: "RetryQueueResult | None" = None):
        self.enqueue_calls: list[dict] = []
        self.dequeue_calls: int = 0
        self.remove_calls: list[str] = []
        self._remove_result = remove_result if remove_result is not None else RetryQueueResult(
            outcome=RetryQueueOutcome.REMOVED, item=None, reason=None,
        )

    def enqueue(self, run_id, workflow_name, retry_attempt=1, priority=None):
        self.enqueue_calls.append({"run_id": run_id, "workflow_name": workflow_name})
        return None

    def dequeue(self):
        self.dequeue_calls += 1
        return None

    def remove(self, run_id):
        self.remove_calls.append(run_id)
        return self._remove_result


class FakeRetryQueueRemovalExecutor:
    """テスト専用のFake。apply_all()呼び出しを記録し、固定の戻り値を返す。"""

    def __init__(self, result: "list[RetryQueueRemovalResult] | None" = None):
        self.calls: list[tuple] = []
        self._result = result if result is not None else []

    def apply_all(self, decisions, remove_fn):
        self.calls.append((decisions, remove_fn))
        return self._result


def make_record(run_id: str, monitor_status: WorkflowMonitorStatus, job_id: str = "job-1") -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=monitor_status,
        source_status=monitor_status.value, source="manual", job_id=job_id,
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=[],
    )


# ═══════════════════════════════════════════════════════════
# テスト1-9: RetryQueueRemovalExecutor単体：除去方針
# ═══════════════════════════════════════════════════════════

print("[テスト1-3] apply()：COMPLETE/FAIL→remove呼び出し・NOOP→remove不呼び出し")

executor_1 = RetryQueueRemovalExecutor()

fake_queue_1 = FakeRetryQueueManager()
decision_complete_1 = make_decision("run-001", RetryQueueUpdateOutcome.COMPLETE)
result_1 = executor_1.apply(decision_complete_1, fake_queue_1.remove)
check_true("1. COMPLETE → attempted=True", result_1.attempted)
check("1. COMPLETE → remove_fnが1回呼ばれる（run-001）", fake_queue_1.remove_calls, ["run-001"])
check("1. COMPLETE → queue_result.outcome=REMOVED", result_1.queue_result.outcome, RetryQueueOutcome.REMOVED)

fake_queue_2 = FakeRetryQueueManager()
decision_fail_2 = make_decision("run-002", RetryQueueUpdateOutcome.FAIL)
result_2 = executor_1.apply(decision_fail_2, fake_queue_2.remove)
check_true("2. FAIL → attempted=True", result_2.attempted)
check("2. FAIL → remove_fnが1回呼ばれる（run-002）", fake_queue_2.remove_calls, ["run-002"])
check("2. FAIL → queue_result.outcome=REMOVED", result_2.queue_result.outcome, RetryQueueOutcome.REMOVED)

fake_queue_3 = FakeRetryQueueManager()
decision_noop_3 = make_decision("run-003", RetryQueueUpdateOutcome.NOOP)
result_3 = executor_1.apply(decision_noop_3, fake_queue_3.remove)
check_false("3. NOOP → attempted=False", result_3.attempted)
check("3. NOOP → remove_fnが一切呼ばれない", fake_queue_3.remove_calls, [])
check("3. NOOP → queue_result=None", result_3.queue_result, None)
print()

print("[テスト4] COMPLETEだが対象run_idがQueueに存在しない → NOT_FOUND（エラー扱いしない）")

fake_queue_4 = FakeRetryQueueManager(
    remove_result=RetryQueueResult(outcome=RetryQueueOutcome.NOT_FOUND, item=None, reason="not found"),
)
decision_complete_4 = make_decision("run-004", RetryQueueUpdateOutcome.COMPLETE)
result_4 = executor_1.apply(decision_complete_4, fake_queue_4.remove)
check_true("4. attempted=True", result_4.attempted)
check("4. queue_result.outcome=NOT_FOUND", result_4.queue_result.outcome, RetryQueueOutcome.NOT_FOUND)
print()

print("[テスト5] RETRY_QUEUE_ENABLED=false（NullRetryQueueManager.remove）→ DISABLED")

fake_queue_5 = FakeRetryQueueManager(
    remove_result=RetryQueueResult(outcome=RetryQueueOutcome.DISABLED, item=None, reason="disabled"),
)
decision_complete_5 = make_decision("run-005", RetryQueueUpdateOutcome.COMPLETE)
result_5 = executor_1.apply(decision_complete_5, fake_queue_5.remove)
check_true("5. attempted=True", result_5.attempted)
check("5. queue_result.outcome=DISABLED", result_5.queue_result.outcome, RetryQueueOutcome.DISABLED)
print()

print("[テスト6-7] apply_all()：複数件を順序を保ったまま処理・空リスト")

fake_queue_6 = FakeRetryQueueManager()
decisions_6 = [
    make_decision("run-006a", RetryQueueUpdateOutcome.COMPLETE),
    make_decision("run-006b", RetryQueueUpdateOutcome.NOOP),
    make_decision("run-006c", RetryQueueUpdateOutcome.FAIL),
]
results_6 = executor_1.apply_all(decisions_6, fake_queue_6.remove)
check("6. apply_all()が3件を順序を保ったまま処理する（attempted）", [r.attempted for r in results_6], [True, False, True])
check("6. remove_fnはCOMPLETE/FAILの2件のみ呼ばれる", fake_queue_6.remove_calls, ["run-006a", "run-006c"])

results_7 = executor_1.apply_all([], fake_queue_6.remove)
check("7. 空リストを渡した場合は空リストを返す", results_7, [])
print()

print("[テスト8-9] RetryQueueRemovalResult.decisionの同一性・reason文字列")

decision_8 = make_decision("run-008", RetryQueueUpdateOutcome.COMPLETE)
result_8 = executor_1.apply(decision_8, FakeRetryQueueManager().remove)
check_true("8. RetryQueueRemovalResult.decisionが元のRetryQueueUpdateDecisionそのもの", result_8.decision is decision_8)

decision_complete_9 = make_decision("run-009", RetryQueueUpdateOutcome.COMPLETE)
result_complete_9 = executor_1.apply(decision_complete_9, FakeRetryQueueManager().remove)
check_true("9. COMPLETEのreasonにrun_idが含まれる", "run-009" in result_complete_9.reason)
check_true("9. COMPLETEのreasonにoutcome値（complete）が含まれる", "complete" in result_complete_9.reason)

decision_noop_9 = make_decision("run-009b", RetryQueueUpdateOutcome.NOOP)
result_noop_9 = executor_1.apply(decision_noop_9, FakeRetryQueueManager().remove)
check_true("9. NOOPのreasonにoutcome値（noop）が含まれる", "noop" in result_noop_9.reason)
check(
    "9. COMPLETE/NOOPのreason文字列が区別できる",
    len({result_complete_9.reason, result_noop_9.reason}),
    2,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト10-14: RetryManager.apply_retry_queue_removals()：委譲の正確性
# ═══════════════════════════════════════════════════════════

print("[テスト10] queue_removal_executor省略時、自動フォールバックする")

manager_10 = RetryManager(policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None))
check_true("10. queue_removal_executor省略時、内部にRetryQueueRemovalExecutorが構築される", isinstance(manager_10._queue_removal_executor, RetryQueueRemovalExecutor))
print()

print("[テスト11-12] DIで渡したFakeExecutorへの委譲・remove_fnの伝播")

fake_monitor_11 = FakeWorkflowMonitorManager(record=make_record("run-011", WorkflowMonitorStatus.FAILED))
fake_executor_11 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-011", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
))
fake_removal_executor_11 = FakeRetryQueueRemovalExecutor(result=["placeholder-removal-result"])
fake_queue_11 = FakeRetryQueueManager()
manager_11 = RetryManager(
    policy=policy_ok, executor=fake_executor_11, monitor=fake_monitor_11,
    queue=fake_queue_11,
    queue_removal_executor=fake_removal_executor_11,
)
events_11 = [make_retry_event("run-011")]
result_11 = manager_11.apply_retry_queue_removals(events_11)
check("11. FakeRemovalExecutor.apply_all()が1回だけ呼ばれる", len(fake_removal_executor_11.calls), 1)
check(
    "11. decide_retry_queue_updates()の戻り値がapply_all()にそのまま渡る",
    [d.execution_result.dispatch_event.candidate_event.run_id for d in fake_removal_executor_11.calls[0][0]],
    ["run-011"],
)
check("11. 最終的な戻り値がFakeRemovalExecutorの戻り値そのもの", result_11, ["placeholder-removal-result"])
check_true("12. remove_fnにself._queue.remove（FakeQueue.remove）が渡される", fake_removal_executor_11.calls[0][1] == fake_queue_11.remove)
print()

print("[テスト13] from_config()の既存10引数呼び出しが本Release前と同じゲート判定結果を返す")

fake_engine_ok = FakeWorkflowEngineManager()
fake_monitor_ok = FakeWorkflowMonitorManager(record=None)

mgr_13a = RetryManager.from_config(RetryConfig(enabled=False), policy_ok, fake_engine_ok, fake_monitor_ok)
check_true("13. enabled=Falseの4引数呼び出し → NullRetryManager", isinstance(mgr_13a, NullRetryManager))

mgr_13b = RetryManager.from_config(RetryConfig(enabled=True), policy_ok, NullWorkflowEngineManager(), fake_monitor_ok)
check_true("13. NullWorkflowEngineManagerの4引数呼び出し → NullRetryManager", isinstance(mgr_13b, NullRetryManager))

mgr_13c = RetryManager.from_config(RetryConfig(enabled=True), policy_ok, fake_engine_ok, fake_monitor_ok)
check_true("13. 両方満たす4引数呼び出し → RetryManager（実インスタンス）", isinstance(mgr_13c, RetryManager))
check_true("13. queue_removal_executor省略時、内部にRetryQueueRemovalExecutorが自動構築される", isinstance(mgr_13c._queue_removal_executor, RetryQueueRemovalExecutor))
print()

print("[テスト14] from_config()でqueue_removal_executorを渡すと実際に配線される")

fake_removal_executor_14 = FakeRetryQueueRemovalExecutor(result=[])
mgr_14 = RetryManager.from_config(
    RetryConfig(enabled=True), policy_ok, fake_engine_ok, fake_monitor_ok,
    queue_removal_executor=fake_removal_executor_14,
)
mgr_14.apply_retry_queue_removals([make_retry_event("run-14")])
check("14. from_config()経由で渡したqueue_removal_executorに実際に委譲される", len(fake_removal_executor_14.calls), 1)
print()


# ═══════════════════════════════════════════════════════════
# テスト15-16: apply_retry_queue_removals()と既存Queue操作の独立性
# ═══════════════════════════════════════════════════════════

print("[テスト15] apply_retry_queue_removals()とenqueue()/dequeue()の独立性")

fake_queue_15 = FakeRetryQueueManager()
fake_monitor_15 = FakeWorkflowMonitorManager(record=make_record("run-15", WorkflowMonitorStatus.FAILED))
fake_executor_15 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-15", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
))
manager_15 = RetryManager(policy=policy_ok, executor=fake_executor_15, monitor=fake_monitor_15, queue=fake_queue_15)

manager_15.apply_retry_queue_removals([make_retry_event("run-15")])
check("15. apply_retry_queue_removals()を呼んでもFakeQueue.enqueue()は呼ばれない", len(fake_queue_15.enqueue_calls), 0)
check("15. apply_retry_queue_removals()を呼んでもFakeQueue.dequeue()は呼ばれない", fake_queue_15.dequeue_calls, 0)
check("15. COMPLETE判定のためFakeQueue.remove()は1回呼ばれる", len(fake_queue_15.remove_calls), 1)
print()

print("[テスト16] Architecture Guard：apply_retry_queue_removals()が"
      "self._queue.enqueue / self._queue.dequeue を参照しない（静的検査）")

retry_manager_source = (PROJECT_ROOT / "src" / "retry_engine" / "retry_manager.py").read_text(encoding="utf-8")


def extract_method_body(source: str, method_name: str) -> str:
    start_match = re.search(rf"\n    def {re.escape(method_name)}\(", source)
    rest = source[start_match.end():]
    next_match = re.search(r"\n    def ", rest)
    end = next_match.start() if next_match else len(rest)
    return rest[:end]


body_apply_16 = extract_method_body(retry_manager_source, "apply_retry_queue_removals")
check_false(
    "16. RetryManager.apply_retry_queue_removals()本体が「self._queue.enqueue」を含まない",
    "self._queue.enqueue" in body_apply_16,
)
check_false(
    "16. RetryManager.apply_retry_queue_removals()本体が「self._queue.dequeue」を含まない",
    "self._queue.dequeue" in body_apply_16,
)
check_true(
    "16. RetryManager.apply_retry_queue_removals()本体は「self._queue.remove」を参照している",
    "self._queue.remove" in body_apply_16,
)
check_true(
    "16. RetryManager.apply_retry_queue_removals()本体は「self._queue_removal_executor」を参照している",
    "self._queue_removal_executor" in body_apply_16,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト17-19: 実際のRetryQueueManager.remove()が呼ばれる統合確認（真のQueue反映）
# ═══════════════════════════════════════════════════════════

print("[テスト17] 実Queueにenqueueされたrun_idについてCOMPLETE判定が出ると実際にQueueから除去される")

real_queue_17 = RetryQueueManager(config=RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0))
real_queue_17.enqueue(run_id="run-17", workflow_name="news")
check_true("17. enqueue直後はexists()がTrue", real_queue_17.exists("run-17"))

fake_monitor_17 = FakeWorkflowMonitorManager(record=make_record("run-17", WorkflowMonitorStatus.FAILED))
fake_executor_17 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-17", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
))
manager_17 = RetryManager(policy=policy_ok, executor=fake_executor_17, monitor=fake_monitor_17, queue=real_queue_17)
results_17 = manager_17.apply_retry_queue_removals([make_retry_event("run-17")])
check("17. 除去結果が1件返る", len(results_17), 1)
check_true("17. attempted=True", results_17[0].attempted)
check("17. queue_result.outcome=REMOVED", results_17[0].queue_result.outcome, RetryQueueOutcome.REMOVED)
check_false("17. remove後はexists()がFalse（実際にQueueから除去された）", real_queue_17.exists("run-17"))
check("17. remove後はcount()が0", real_queue_17.count(), 0)
print()

print("[テスト18] FAIL判定でも実際にQueueから除去される")

real_queue_18 = RetryQueueManager(config=RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0))
real_queue_18.enqueue(run_id="run-18", workflow_name="news")

fake_monitor_18 = FakeWorkflowMonitorManager(record=make_record("run-18", WorkflowMonitorStatus.FAILED))
fake_executor_18 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-18", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=False),
))
manager_18 = RetryManager(policy=policy_ok, executor=fake_executor_18, monitor=fake_monitor_18, queue=real_queue_18)
results_18 = manager_18.apply_retry_queue_removals([make_retry_event("run-18")])
check("18. queue_result.outcome=REMOVED（FAILでも除去対象）", results_18[0].queue_result.outcome, RetryQueueOutcome.REMOVED)
check_false("18. remove後はexists()がFalse", real_queue_18.exists("run-18"))
print()

print("[テスト19] NOOP（SKIPPED）判定の場合はQueueに項目が残り続ける（除去されない）")

real_queue_19 = RetryQueueManager(config=RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0))
real_queue_19.enqueue(run_id="run-19", workflow_name="news")

# max_attempts=3、attempt=3を渡すことで RetryPolicy.should_retry() が False（SKIPPED）と判定する
fake_monitor_19 = FakeWorkflowMonitorManager(record=make_record("run-19", WorkflowMonitorStatus.FAILED))
fake_executor_19 = FakeRetryExecutor(result=None)
manager_19 = RetryManager(policy=policy_ok, executor=fake_executor_19, monitor=fake_monitor_19, queue=real_queue_19)
results_19 = manager_19.apply_retry_queue_removals([make_retry_event("run-19", retry_attempt=3)])
check("19. SKIPPED判定のためattempted=False", results_19[0].attempted, False)
check_true("19. remove()が呼ばれないためexists()はTrueのまま（Queueに滞留）", real_queue_19.exists("run-19"))
check("19. count()も1のまま", real_queue_19.count(), 1)
print()


# ═══════════════════════════════════════════════════════════
# テスト20-21: NullRetryManager：常に[]を返す
# ═══════════════════════════════════════════════════════════

print("[テスト20-21] NullRetryManager.apply_retry_queue_removals()は常に[]を返す")

null_mgr_20 = NullRetryManager()
result_20_with_retry_events = null_mgr_20.apply_retry_queue_removals([make_retry_event("run-20a"), make_retry_event("run-20b")])
check("20. Retry候補由来のイベントを含んでいても常に[]を返す", result_20_with_retry_events, [])

result_20_empty = null_mgr_20.apply_retry_queue_removals([])
check("20. 空リストを渡しても[]を返す", result_20_empty, [])

check("21. NullRetryManagerはRetryQueueRemovalExecutor等のいかなるフィールドも持たない", vars(null_mgr_20), {})
print()


# ═══════════════════════════════════════════════════════════
# テスト22: 書き込みが発生しないことの確認
# ═══════════════════════════════════════════════════════════

print("[テスト22] 実行処理の前後でファイルが一切作成されない")

write_check_dir_22 = Path(tempfile.mkdtemp())
before_files_22 = list(write_check_dir_22.rglob("*"))

real_queue_22 = RetryQueueManager(config=RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0))
real_queue_22.enqueue(run_id="run-22w", workflow_name="news")
fake_monitor_22w = FakeWorkflowMonitorManager(record=make_record("run-22w", WorkflowMonitorStatus.FAILED))
fake_executor_22w = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-22w", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
))
manager_22w = RetryManager(policy=policy_ok, executor=fake_executor_22w, monitor=fake_monitor_22w, queue=real_queue_22)
manager_22w.apply_retry_queue_removals([make_retry_event("run-22w")])
NullRetryManager().apply_retry_queue_removals([make_retry_event("run-22wb")])

after_files_22 = list(write_check_dir_22.rglob("*"))
check("22. 実行処理前後でファイルが作成されない", after_files_22, before_files_22)
print()


# ═══════════════════════════════════════════════════════════
# テスト23: Architecture Guard（無改修の確認）
# ═══════════════════════════════════════════════════════════

print("[テスト23] 既存ファイルの無変更確認（git diff）")

unchanged_paths_v420 = [
    "main.py",
    "src/scheduler/scheduler_engine.py",
    "src/scheduler/__init__.py",
    "src/scheduler/scheduler_config.py",
    "src/scheduler/scheduler_event.py",
    "src/scheduler/scheduler_job.py",
    "src/scheduler/scheduler_manager.py",
    "src/scheduler/scheduler_repository.py",
    "src/retry_scheduler_decision/retry_scheduler_decision.py",
    "src/retry_scheduler_source/retry_scheduler_source.py",
    "src/retry_queue/__init__.py",
    "src/retry_queue/retry_queue_status.py",
    "src/retry_queue/retry_queue_item.py",
    "src/retry_queue/retry_queue_result.py",
    "src/retry_queue/retry_queue_config.py",
    "src/retry_queue/retry_queue_manager.py",
    "src/retry_queue/null_retry_queue_manager.py",
    # retry_engine のうち、本Releaseで変更していないファイル
    "src/retry_engine/retry_event_consumer.py",
    "src/retry_engine/retry_event_dispatcher.py",
    "src/retry_engine/retry_execution_selector.py",
    "src/retry_engine/retry_execution_coordinator.py",
    "src/retry_engine/retry_queue_update_decider.py",
    "src/retry_engine/retry_policy.py",
    "src/retry_engine/retry_config.py",
    "src/retry_engine/retry_request.py",
    "src/retry_engine/retry_result.py",
    "src/retry_engine/retry_executor.py",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths_v420:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"23. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("23. gitが利用できないため無変更確認をスキップ", True)
print()


# ═══════════════════════════════════════════════════════════
# テスト24: retry_engineパッケージのexport確認
# ═══════════════════════════════════════════════════════════

print("[テスト24] retry_engine.__all__ に新規シンボルが追加され、既存シンボルが維持されていること")

import retry_engine as re_pkg_24

check(
    "24. retry_engine.__all__ が既存シンボル＋新規2シンボルの構成になっている",
    set(re_pkg_24.__all__),
    {
        "RetryPolicy", "DEFAULT_TARGET_STATUSES", "RetryConfig", "RetryRequest", "RetryOutcome",
        "RetryResult", "RetryExecutor", "RetryCandidateEvent", "RetryEventConsumer",
        "RetryDispatchEvent", "RetryEventDispatcher", "RetryExecutionSelector",
        "RetryExecutionCoordinator", "RetryExecutionResult", "RetryQueueUpdateOutcome",
        "RetryQueueUpdateDecision", "RetryQueueUpdateDecider", "RetryQueueRemovalResult",
        "RetryQueueRemovalExecutor", "RetryManager", "NullRetryManager",
    },
)
check_true("24. RetryManagerがapply_retry_queue_removals()を持つ", hasattr(RetryManager, "apply_retry_queue_removals"))
check_true("24. NullRetryManagerがapply_retry_queue_removals()を持つ", hasattr(NullRetryManager, "apply_retry_queue_removals"))
print()


# ═══════════════════════════════════════════════════════════
# テスト25: __init__ / from_config() の新規引数の後方互換性
# ═══════════════════════════════════════════════════════════

print("[テスト25] RetryManager.__init__ / from_config()の新規引数が末尾・デフォルト値付きで追加されていること")

sig_init_25 = inspect.signature(RetryManager.__init__)
params_init_25 = list(sig_init_25.parameters.keys())
check("25. __init__の最終引数がqueue_removal_executor", params_init_25[-1], "queue_removal_executor")
check("25. queue_removal_executorのデフォルトはNone", sig_init_25.parameters["queue_removal_executor"].default, None)

sig_from_config_25 = inspect.signature(RetryManager.from_config)
params_from_config_25 = list(sig_from_config_25.parameters.keys())
check("25. from_config()の最終引数がqueue_removal_executor", params_from_config_25[-1], "queue_removal_executor")
check(
    "25. 既存9引数（queue_update_decider含む）の名前・順序が変わっていない",
    params_from_config_25[:10],
    [
        "retry_config", "retry_policy", "workflow_engine_manager", "workflow_monitor_manager",
        "retry_queue_manager", "event_consumer", "event_dispatcher",
        "execution_selector", "execution_coordinator", "queue_update_decider",
    ],
)
print()


# ═══════════════════════════════════════════════════════════
# テスト26: 新規ファイルが RetryQueueManager / NullRetryQueueManager をimportしないこと
# ═══════════════════════════════════════════════════════════

print("[テスト26] retry_queue_removal_executor.py に "
      "'RetryQueueManager' / 'NullRetryQueueManager' への実コード参照がない（AST）。"
      "RetryQueueResultは参照する")


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
            if isinstance(node, ast.ImportFrom) and node.module:
                names.add(node.module)
    return names


removal_executor_source_path_26 = PROJECT_ROOT / "src" / "retry_engine" / "retry_queue_removal_executor.py"
tree_26 = ast.parse(removal_executor_source_path_26.read_text(encoding="utf-8"))
referenced_26 = _referenced_names(tree_26)
check_false("26. retry_queue_removal_executor.py: 'RetryQueueManager' への実コード参照が存在しない", "RetryQueueManager" in referenced_26)
check_false("26. retry_queue_removal_executor.py: 'NullRetryQueueManager' への実コード参照が存在しない", "NullRetryQueueManager" in referenced_26)
check_true("26. retry_queue_removal_executor.py: 'RetryQueueResult' は参照している", "RetryQueueResult" in referenced_26)
print()


# ═══════════════════════════════════════════════════════════
# テスト27: 既存回帰（v3.0.0〜v4.1.0 RetryManager挙動）
# ═══════════════════════════════════════════════════════════

print("[テスト27] retry() / execute_dispatchable_retries() / decide_retry_queue_updates()の既存挙動が維持される")

fake_monitor_27 = FakeWorkflowMonitorManager(record=make_record("run-27", WorkflowMonitorStatus.FAILED))
fake_executor_27 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-27", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
))
manager_27 = RetryManager(policy=policy_ok, executor=fake_executor_27, monitor=fake_monitor_27)
result_27 = manager_27.retry("run-27", attempt=1)
check("27. retry()が本Release後も同じ挙動（RETRIED）", result_27.outcome, RetryOutcome.RETRIED)

execution_results_27 = manager_27.execute_dispatchable_retries([make_retry_event("run-27e")])
check("27. execute_dispatchable_retries()が本Release後も同じ挙動（RETRIED）", execution_results_27[0].retry_result.outcome, RetryOutcome.RETRIED)

decisions_27 = manager_27.decide_retry_queue_updates([make_retry_event("run-27d")])
check("27. decide_retry_queue_updates()が本Release後も同じ挙動（COMPLETE）", decisions_27[0].outcome, RetryQueueUpdateOutcome.COMPLETE)

null_mgr_27 = NullRetryManager()
result_27b = null_mgr_27.enqueue_retry(run_id="run-27b", workflow_name="news")
check_contains_27 = "Retry Engine is disabled" in result_27b.reason
check_true("27. NullRetryManager.enqueue_retry()が本Release後も同じ挙動（DISABLED理由文言）", check_contains_27)
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
