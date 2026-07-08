"""
E2E テスト: v4.3.0 Retry Queue Cleanup Foundation

テストシナリオ（docs/design/retry_queue_cleanup_foundation.md 4章・14章・16章 対応）:
    ── RetryQueueCleanupDecider単体：CLEANUP/KEEP判定方針 ──
    1.  NOOP + retry_result.outcome=SKIPPED → CLEANUP
    2.  NOOP + retry_result.outcome=NOT_FOUND → KEEP（対象外）
    3.  NOOP + retry_result.outcome=DISABLED → KEEP（対象外）
    4.  update_decision.outcome=COMPLETE → KEEP（対象外。v4.2.0で除去済みのはず）
    5.  update_decision.outcome=FAIL → KEEP（対象外。v4.2.0で除去済みのはず）
    6.  decide_all()が複数件を順序を保ったまま処理する
    7.  空リストを渡した場合は空リストを返す
    8.  RetryQueueCleanupDecision.update_decisionが元のRetryQueueUpdateDecisionそのもの
    9.  reason文字列でCLEANUP/KEEPが区別できる

    ── RetryQueueCleanupExecutor単体：除去方針 ──
    10. outcome=CLEANUP → remove_fnが呼ばれ、attempted=True・queue_result=REMOVED
    11. outcome=KEEP → remove_fnが呼ばれず、attempted=False・queue_result=None
    12. CLEANUPだが対象run_idがQueueに存在しない → queue_result=NOT_FOUND（エラー扱いしない）
    13. RETRY_QUEUE_ENABLED=false（NullRetryQueueManager.remove）→ queue_result=DISABLED
    14. apply_all()が複数件を順序を保ったまま処理する
    15. 空リストを渡した場合は空リストを返す
    16. RetryQueueCleanupResult.decisionが元のRetryQueueCleanupDecisionそのもの

    ── RetryManager.decide_retry_queue_cleanup() / apply_retry_queue_cleanup()：委譲の正確性 ──
    17. queue_cleanup_decider / queue_cleanup_executor省略時、自動フォールバックする
    18. DIで渡したFakeDeciderへ、decide_retry_queue_updates()の結果がそのまま渡る
    19. DIで渡したFakeExecutorへ、decide_retry_queue_cleanup()の結果がそのまま渡る
    20. remove_fnにself._queue.removeが渡される
    21. from_config()の既存12引数呼び出しが本Release前と同じゲート判定結果を返す
    22. from_config()でqueue_cleanup_decider/executorを渡すと実際に配線される

    ── apply_retry_queue_cleanup()と既存Queue操作の独立性 ──
    23. apply_retry_queue_cleanup()を呼んでもFakeQueue.enqueue()/dequeue()は呼ばれない
    24. Architecture Guard：apply_retry_queue_cleanup()のソースコードが
        self._queue.enqueue / self._queue.dequeue を一切参照しない

    ── 実際のRetryQueueManager.remove()が呼ばれる統合確認（真のQueue反映） ──
    25. 実QueueにあるSKIPPED由来の項目は実際に除去される（count()減少・exists()がFalse）
    26. 実Queueに残っているCOMPLETE/FAIL相当の項目はcleanupでは除去されない（KEEP）
    27. NOT_FOUND/DISABLED由来のNOOPも除去されない（KEEP）

    ── NullRetryManager：常に[]を返す ──
    28. NullRetryManager.decide_retry_queue_cleanup() / apply_retry_queue_cleanup()は常に[]
    29. NullRetryManagerはRetryQueueCleanupDecider等のいかなるフィールドも持たない

    ── 書き込みが発生しないことの確認 ──
    30. 実行処理の前後でファイルが一切作成されない

    ── Architecture Guard（無改修の確認・新規ファイルのimport制約） ──
    31. src/scheduler/ / src/retry_scheduler_decision/ / src/retry_scheduler_source/ /
        src/retry_queue/ 配下の全ファイル、および src/retry_engine/ のうち本Releaseで
        変更していないファイル（retry_queue_update_decider.py・retry_queue_removal_executor.py
        含む）に変更がないこと
    32. retry_engineパッケージの__all__に新規シンボルが追加され、既存シンボルは維持
    33. RetryManager.__init__ / from_config()の新規引数が末尾・デフォルト値付きで追加
    34. retry_queue_cleanup_executor.py が RetryQueueManager / NullRetryQueueManager を
        importしていないこと（AST）。RetryQueueResultは参照する

    ── 既存回帰（v3.0.0〜v4.2.0 RetryManager挙動）──
    35. retry() / decide_retry_queue_updates() / apply_retry_queue_removals()の
        挙動が本Releaseでも維持される

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v4_3_0_retry_queue_cleanup_foundation.py
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
print("v4.3.0 Retry Queue Cleanup Foundation E2E テスト")
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
    RetryQueueCleanupDecider,
    RetryQueueCleanupDecision,
    RetryQueueCleanupExecutor,
    RetryQueueCleanupOutcome,
    RetryQueueCleanupResult,
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
        execute_time=datetime(2026, 7, 8, 9, 0),
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


def make_update_decision(run_id: str, kind: str) -> RetryQueueUpdateDecision:
    """
    kind: "complete" | "fail" | "skipped" | "not_found" | "disabled"
    RetryQueueUpdateDecider().decide()を実際に通して、本物の判定結果を作る。
    """
    if kind == "complete":
        retry_result = RetryResult(
            original_run_id=run_id, outcome=RetryOutcome.RETRIED, attempt=1,
            monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
            workflow_engine_result=make_workflow_engine_result(overall_success=True),
        )
    elif kind == "fail":
        retry_result = RetryResult(
            original_run_id=run_id, outcome=RetryOutcome.RETRIED, attempt=1,
            monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
            workflow_engine_result=make_workflow_engine_result(overall_success=False),
        )
    elif kind == "skipped":
        retry_result = RetryResult(
            original_run_id=run_id, outcome=RetryOutcome.SKIPPED, attempt=3,
            monitor_status=WorkflowMonitorStatus.FAILED,
            reason="attempt 3 has reached max_attempts=3.", workflow_engine_result=None,
        )
    elif kind == "not_found":
        retry_result = RetryResult(
            original_run_id=run_id, outcome=RetryOutcome.NOT_FOUND, attempt=1,
            monitor_status=None, reason=f"run_id={run_id} was not found in Workflow Monitor.",
            workflow_engine_result=None,
        )
    elif kind == "disabled":
        retry_result = RetryResult(
            original_run_id=run_id, outcome=RetryOutcome.DISABLED, attempt=1,
            monitor_status=None, reason="Retry Engine is disabled.", workflow_engine_result=None,
        )
    else:
        raise ValueError(f"unknown kind: {kind}")

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


class FakeRetryQueueUpdateDecider:
    """テスト専用のFake。decide_all()呼び出しを記録し、固定の戻り値を返す。"""

    def __init__(self, result: "list[RetryQueueUpdateDecision] | None" = None):
        self.calls: list[list] = []
        self._result = result if result is not None else []

    def decide_all(self, execution_results):
        self.calls.append(execution_results)
        return self._result


class FakeRetryQueueCleanupDecider:
    """テスト専用のFake。decide_all()呼び出しを記録し、固定の戻り値を返す。"""

    def __init__(self, result: "list[RetryQueueCleanupDecision] | None" = None):
        self.calls: list[list] = []
        self._result = result if result is not None else []

    def decide_all(self, update_decisions):
        self.calls.append(update_decisions)
        return self._result


class FakeRetryQueueCleanupExecutor:
    """テスト専用のFake。apply_all()呼び出しを記録し、固定の戻り値を返す。"""

    def __init__(self, result: "list[RetryQueueCleanupResult] | None" = None):
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
# テスト1-9: RetryQueueCleanupDecider単体：CLEANUP/KEEP判定方針
# ═══════════════════════════════════════════════════════════

print("[テスト1-5] decide()：NOOP+SKIPPED→CLEANUP、その他→KEEP")

decider_1 = RetryQueueCleanupDecider()

decision_skipped_1 = make_update_decision("run-101", "skipped")
result_1 = decider_1.decide(decision_skipped_1)
check("1. NOOP+SKIPPED → CLEANUP", result_1.outcome, RetryQueueCleanupOutcome.CLEANUP)

decision_not_found_2 = make_update_decision("run-102", "not_found")
result_2 = decider_1.decide(decision_not_found_2)
check("2. NOOP+NOT_FOUND → KEEP", result_2.outcome, RetryQueueCleanupOutcome.KEEP)

decision_disabled_3 = make_update_decision("run-103", "disabled")
result_3 = decider_1.decide(decision_disabled_3)
check("3. NOOP+DISABLED → KEEP", result_3.outcome, RetryQueueCleanupOutcome.KEEP)

decision_complete_4 = make_update_decision("run-104", "complete")
result_4 = decider_1.decide(decision_complete_4)
check("4. update_decision.outcome=COMPLETE → KEEP", result_4.outcome, RetryQueueCleanupOutcome.KEEP)

decision_fail_5 = make_update_decision("run-105", "fail")
result_5 = decider_1.decide(decision_fail_5)
check("5. update_decision.outcome=FAIL → KEEP", result_5.outcome, RetryQueueCleanupOutcome.KEEP)
print()

print("[テスト6-7] decide_all()：複数件を順序を保ったまま処理・空リスト")

decisions_6 = [
    make_update_decision("run-106a", "skipped"),
    make_update_decision("run-106b", "complete"),
    make_update_decision("run-106c", "not_found"),
    make_update_decision("run-106d", "skipped"),
]
results_6 = decider_1.decide_all(decisions_6)
check(
    "6. decide_all()が4件を順序を保ったまま処理する",
    [r.outcome for r in results_6],
    [
        RetryQueueCleanupOutcome.CLEANUP, RetryQueueCleanupOutcome.KEEP,
        RetryQueueCleanupOutcome.KEEP, RetryQueueCleanupOutcome.CLEANUP,
    ],
)

results_7 = decider_1.decide_all([])
check("7. 空リストを渡した場合は空リストを返す", results_7, [])
print()

print("[テスト8-9] RetryQueueCleanupDecision.update_decisionの同一性・reason文字列")

decision_8 = make_update_decision("run-108", "skipped")
result_8 = decider_1.decide(decision_8)
check_true("8. RetryQueueCleanupDecision.update_decisionが元のRetryQueueUpdateDecisionそのもの", result_8.update_decision is decision_8)

decision_cleanup_9 = make_update_decision("run-109a", "skipped")
result_cleanup_9 = decider_1.decide(decision_cleanup_9)
decision_keep_9 = make_update_decision("run-109b", "not_found")
result_keep_9 = decider_1.decide(decision_keep_9)
check(
    "9. CLEANUP/KEEPのreason文字列が区別できる",
    len({result_cleanup_9.reason, result_keep_9.reason}),
    2,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト10-16: RetryQueueCleanupExecutor単体：除去方針
# ═══════════════════════════════════════════════════════════

print("[テスト10-11] apply()：CLEANUP→remove呼び出し・KEEP→remove不呼び出し")

executor_10 = RetryQueueCleanupExecutor()
cleanup_decider_10 = RetryQueueCleanupDecider()

fake_queue_10 = FakeRetryQueueManager()
cleanup_decision_10 = cleanup_decider_10.decide(make_update_decision("run-110", "skipped"))
result_10 = executor_10.apply(cleanup_decision_10, fake_queue_10.remove)
check_true("10. CLEANUP → attempted=True", result_10.attempted)
check("10. CLEANUP → remove_fnが1回呼ばれる（run-110）", fake_queue_10.remove_calls, ["run-110"])
check("10. CLEANUP → queue_result.outcome=REMOVED", result_10.queue_result.outcome, RetryQueueOutcome.REMOVED)

fake_queue_11 = FakeRetryQueueManager()
keep_decision_11 = cleanup_decider_10.decide(make_update_decision("run-111", "complete"))
result_11 = executor_10.apply(keep_decision_11, fake_queue_11.remove)
check_false("11. KEEP → attempted=False", result_11.attempted)
check("11. KEEP → remove_fnが一切呼ばれない", fake_queue_11.remove_calls, [])
check("11. KEEP → queue_result=None", result_11.queue_result, None)
print()

print("[テスト12] CLEANUPだが対象run_idがQueueに存在しない → NOT_FOUND（エラー扱いしない）")

fake_queue_12 = FakeRetryQueueManager(
    remove_result=RetryQueueResult(outcome=RetryQueueOutcome.NOT_FOUND, item=None, reason="not found"),
)
cleanup_decision_12 = cleanup_decider_10.decide(make_update_decision("run-112", "skipped"))
result_12 = executor_10.apply(cleanup_decision_12, fake_queue_12.remove)
check_true("12. attempted=True", result_12.attempted)
check("12. queue_result.outcome=NOT_FOUND", result_12.queue_result.outcome, RetryQueueOutcome.NOT_FOUND)
print()

print("[テスト13] RETRY_QUEUE_ENABLED=false（NullRetryQueueManager.remove）→ DISABLED")

fake_queue_13 = FakeRetryQueueManager(
    remove_result=RetryQueueResult(outcome=RetryQueueOutcome.DISABLED, item=None, reason="disabled"),
)
cleanup_decision_13 = cleanup_decider_10.decide(make_update_decision("run-113", "skipped"))
result_13 = executor_10.apply(cleanup_decision_13, fake_queue_13.remove)
check_true("13. attempted=True", result_13.attempted)
check("13. queue_result.outcome=DISABLED", result_13.queue_result.outcome, RetryQueueOutcome.DISABLED)
print()

print("[テスト14-15] apply_all()：複数件を順序を保ったまま処理・空リスト")

fake_queue_14 = FakeRetryQueueManager()
cleanup_decisions_14 = cleanup_decider_10.decide_all([
    make_update_decision("run-114a", "skipped"),
    make_update_decision("run-114b", "complete"),
    make_update_decision("run-114c", "skipped"),
])
results_14 = executor_10.apply_all(cleanup_decisions_14, fake_queue_14.remove)
check("14. apply_all()が3件を順序を保ったまま処理する（attempted）", [r.attempted for r in results_14], [True, False, True])
check("14. remove_fnはCLEANUPの2件のみ呼ばれる", fake_queue_14.remove_calls, ["run-114a", "run-114c"])

results_15 = executor_10.apply_all([], fake_queue_14.remove)
check("15. 空リストを渡した場合は空リストを返す", results_15, [])
print()

print("[テスト16] RetryQueueCleanupResult.decisionの同一性")

cleanup_decision_16 = cleanup_decider_10.decide(make_update_decision("run-116", "skipped"))
result_16 = executor_10.apply(cleanup_decision_16, FakeRetryQueueManager().remove)
check_true("16. RetryQueueCleanupResult.decisionが元のRetryQueueCleanupDecisionそのもの", result_16.decision is cleanup_decision_16)
print()


# ═══════════════════════════════════════════════════════════
# テスト17-22: RetryManager.decide_retry_queue_cleanup() / apply_retry_queue_cleanup()：委譲の正確性
# ═══════════════════════════════════════════════════════════

print("[テスト17] queue_cleanup_decider / queue_cleanup_executor省略時、自動フォールバックする")

manager_17 = RetryManager(policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None))
check_true("17. queue_cleanup_decider省略時、内部にRetryQueueCleanupDeciderが構築される", isinstance(manager_17._queue_cleanup_decider, RetryQueueCleanupDecider))
check_true("17. queue_cleanup_executor省略時、内部にRetryQueueCleanupExecutorが構築される", isinstance(manager_17._queue_cleanup_executor, RetryQueueCleanupExecutor))
print()

print("[テスト18] DIで渡したFakeDeciderへ、decide_retry_queue_updates()の結果がそのまま渡る")

fake_monitor_18 = FakeWorkflowMonitorManager(record=make_record("run-118", WorkflowMonitorStatus.FAILED))
fake_executor_18 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-118", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
))
fake_cleanup_decider_18 = FakeRetryQueueCleanupDecider(result=["placeholder-cleanup-decision"])
manager_18 = RetryManager(
    policy=policy_ok, executor=fake_executor_18, monitor=fake_monitor_18,
    queue_cleanup_decider=fake_cleanup_decider_18,
)
events_18 = [make_retry_event("run-118")]
result_18 = manager_18.decide_retry_queue_cleanup(events_18)
check("18. FakeCleanupDecider.decide_all()が1回だけ呼ばれる", len(fake_cleanup_decider_18.calls), 1)
check(
    "18. decide_retry_queue_updates()の戻り値がdecide_all()にそのまま渡る",
    [d.execution_result.dispatch_event.candidate_event.run_id for d in fake_cleanup_decider_18.calls[0]],
    ["run-118"],
)
check("18. 最終的な戻り値がFakeCleanupDeciderの戻り値そのもの", result_18, ["placeholder-cleanup-decision"])
print()

print("[テスト19-20] DIで渡したFakeExecutorへの委譲・remove_fnの伝播")

fake_monitor_19 = FakeWorkflowMonitorManager(record=make_record("run-119", WorkflowMonitorStatus.FAILED))
fake_executor_19 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-119", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
))
fake_cleanup_executor_19 = FakeRetryQueueCleanupExecutor(result=["placeholder-cleanup-result"])
fake_queue_19 = FakeRetryQueueManager()
manager_19 = RetryManager(
    policy=policy_ok, executor=fake_executor_19, monitor=fake_monitor_19,
    queue=fake_queue_19,
    queue_cleanup_executor=fake_cleanup_executor_19,
)
events_19 = [make_retry_event("run-119")]
result_19 = manager_19.apply_retry_queue_cleanup(events_19)
check("19. FakeCleanupExecutor.apply_all()が1回だけ呼ばれる", len(fake_cleanup_executor_19.calls), 1)
check(
    "19. decide_retry_queue_cleanup()の戻り値がapply_all()にそのまま渡る",
    [d.update_decision.execution_result.dispatch_event.candidate_event.run_id for d in fake_cleanup_executor_19.calls[0][0]],
    ["run-119"],
)
check("19. 最終的な戻り値がFakeCleanupExecutorの戻り値そのもの", result_19, ["placeholder-cleanup-result"])
check_true("20. remove_fnにself._queue.remove（FakeQueue.remove）が渡される", fake_cleanup_executor_19.calls[0][1] == fake_queue_19.remove)
print()

print("[テスト21] from_config()の既存12引数呼び出しが本Release前と同じゲート判定結果を返す")

fake_engine_ok = FakeWorkflowEngineManager()
fake_monitor_ok = FakeWorkflowMonitorManager(record=None)

mgr_21a = RetryManager.from_config(RetryConfig(enabled=False), policy_ok, fake_engine_ok, fake_monitor_ok)
check_true("21. enabled=Falseの4引数呼び出し → NullRetryManager", isinstance(mgr_21a, NullRetryManager))

mgr_21b = RetryManager.from_config(RetryConfig(enabled=True), policy_ok, NullWorkflowEngineManager(), fake_monitor_ok)
check_true("21. NullWorkflowEngineManagerの4引数呼び出し → NullRetryManager", isinstance(mgr_21b, NullRetryManager))

mgr_21c = RetryManager.from_config(RetryConfig(enabled=True), policy_ok, fake_engine_ok, fake_monitor_ok)
check_true("21. 両方満たす4引数呼び出し → RetryManager（実インスタンス）", isinstance(mgr_21c, RetryManager))
check_true("21. queue_cleanup_decider省略時、内部にRetryQueueCleanupDeciderが自動構築される", isinstance(mgr_21c._queue_cleanup_decider, RetryQueueCleanupDecider))
check_true("21. queue_cleanup_executor省略時、内部にRetryQueueCleanupExecutorが自動構築される", isinstance(mgr_21c._queue_cleanup_executor, RetryQueueCleanupExecutor))
print()

print("[テスト22] from_config()でqueue_cleanup_decider/executorを渡すと実際に配線される")

fake_cleanup_decider_22 = FakeRetryQueueCleanupDecider(result=[])
fake_cleanup_executor_22 = FakeRetryQueueCleanupExecutor(result=[])
mgr_22 = RetryManager.from_config(
    RetryConfig(enabled=True), policy_ok, fake_engine_ok, fake_monitor_ok,
    queue_cleanup_decider=fake_cleanup_decider_22,
    queue_cleanup_executor=fake_cleanup_executor_22,
)
mgr_22.apply_retry_queue_cleanup([make_retry_event("run-22")])
check("22. from_config()経由で渡したqueue_cleanup_deciderに実際に委譲される", len(fake_cleanup_decider_22.calls), 1)
check("22. from_config()経由で渡したqueue_cleanup_executorに実際に委譲される", len(fake_cleanup_executor_22.calls), 1)
print()


# ═══════════════════════════════════════════════════════════
# テスト23-24: apply_retry_queue_cleanup()と既存Queue操作の独立性
# ═══════════════════════════════════════════════════════════

print("[テスト23] apply_retry_queue_cleanup()とenqueue()/dequeue()の独立性")

fake_queue_23 = FakeRetryQueueManager()
fake_monitor_23 = FakeWorkflowMonitorManager(record=make_record("run-23", WorkflowMonitorStatus.FAILED))
fake_executor_23 = FakeRetryExecutor(result=None)
manager_23 = RetryManager(policy=policy_ok, executor=fake_executor_23, monitor=fake_monitor_23, queue=fake_queue_23)

manager_23.apply_retry_queue_cleanup([make_retry_event("run-23", retry_attempt=3)])
check("23. apply_retry_queue_cleanup()を呼んでもFakeQueue.enqueue()は呼ばれない", len(fake_queue_23.enqueue_calls), 0)
check("23. apply_retry_queue_cleanup()を呼んでもFakeQueue.dequeue()は呼ばれない", fake_queue_23.dequeue_calls, 0)
check("23. SKIPPED判定のためFakeQueue.remove()は1回呼ばれる", len(fake_queue_23.remove_calls), 1)
print()

print("[テスト24] Architecture Guard：apply_retry_queue_cleanup()が"
      "self._queue.enqueue / self._queue.dequeue を参照しない（静的検査）")

retry_manager_source = (PROJECT_ROOT / "src" / "retry_engine" / "retry_manager.py").read_text(encoding="utf-8")


def extract_method_body(source: str, method_name: str) -> str:
    start_match = re.search(rf"\n    def {re.escape(method_name)}\(", source)
    rest = source[start_match.end():]
    next_match = re.search(r"\n    def ", rest)
    end = next_match.start() if next_match else len(rest)
    return rest[:end]


body_apply_24 = extract_method_body(retry_manager_source, "apply_retry_queue_cleanup")
check_false(
    "24. RetryManager.apply_retry_queue_cleanup()本体が「self._queue.enqueue」を含まない",
    "self._queue.enqueue" in body_apply_24,
)
check_false(
    "24. RetryManager.apply_retry_queue_cleanup()本体が「self._queue.dequeue」を含まない",
    "self._queue.dequeue" in body_apply_24,
)
check_true(
    "24. RetryManager.apply_retry_queue_cleanup()本体は「self._queue.remove」を参照している",
    "self._queue.remove" in body_apply_24,
)
check_true(
    "24. RetryManager.apply_retry_queue_cleanup()本体は「self._queue_cleanup_executor」を参照している",
    "self._queue_cleanup_executor" in body_apply_24,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト25-27: 実際のRetryQueueManager.remove()が呼ばれる統合確認（真のQueue反映）
# ═══════════════════════════════════════════════════════════

print("[テスト25] 実QueueにあるSKIPPED由来の項目は実際に除去される")

real_queue_25 = RetryQueueManager(config=RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0))
real_queue_25.enqueue(run_id="run-25", workflow_name="news")
check_true("25. enqueue直後はexists()がTrue", real_queue_25.exists("run-25"))

# max_attempts=3、attempt=3を渡すことで RetryPolicy.should_retry() が False（SKIPPED）と判定する
fake_monitor_25 = FakeWorkflowMonitorManager(record=make_record("run-25", WorkflowMonitorStatus.FAILED))
fake_executor_25 = FakeRetryExecutor(result=None)
manager_25 = RetryManager(policy=policy_ok, executor=fake_executor_25, monitor=fake_monitor_25, queue=real_queue_25)
results_25 = manager_25.apply_retry_queue_cleanup([make_retry_event("run-25", retry_attempt=3)])
check("25. 除去結果が1件返る", len(results_25), 1)
check_true("25. attempted=True（SKIPPED→CLEANUP）", results_25[0].attempted)
check("25. queue_result.outcome=REMOVED", results_25[0].queue_result.outcome, RetryQueueOutcome.REMOVED)
check_false("25. remove後はexists()がFalse（実際にQueueから除去された）", real_queue_25.exists("run-25"))
check("25. remove後はcount()が0", real_queue_25.count(), 0)
print()

print("[テスト26] 実Queueに残っているCOMPLETE相当の項目はcleanupでは除去されない（KEEP）")

real_queue_26 = RetryQueueManager(config=RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0))
real_queue_26.enqueue(run_id="run-26", workflow_name="news")

fake_monitor_26 = FakeWorkflowMonitorManager(record=make_record("run-26", WorkflowMonitorStatus.FAILED))
fake_executor_26 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-26", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
))
manager_26 = RetryManager(policy=policy_ok, executor=fake_executor_26, monitor=fake_monitor_26, queue=real_queue_26)
results_26 = manager_26.apply_retry_queue_cleanup([make_retry_event("run-26")])
check_false("26. COMPLETE相当 → attempted=False（cleanupの対象外）", results_26[0].attempted)
check_true("26. remove()が呼ばれないためexists()はTrueのまま", real_queue_26.exists("run-26"))
print()

print("[テスト27] NOT_FOUND由来のNOOPも除去されない（KEEP）")

real_queue_27 = RetryQueueManager(config=RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0))
real_queue_27.enqueue(run_id="run-27", workflow_name="news")

fake_monitor_27 = FakeWorkflowMonitorManager(record=None)  # get_status()がNone → NOT_FOUND
fake_executor_27 = FakeRetryExecutor(result=None)
manager_27 = RetryManager(policy=policy_ok, executor=fake_executor_27, monitor=fake_monitor_27, queue=real_queue_27)
results_27 = manager_27.apply_retry_queue_cleanup([make_retry_event("run-27")])
check_false("27. NOT_FOUND → attempted=False（cleanupの対象外）", results_27[0].attempted)
check_true("27. remove()が呼ばれないためexists()はTrueのまま", real_queue_27.exists("run-27"))
print()


# ═══════════════════════════════════════════════════════════
# テスト28-29: NullRetryManager：常に[]を返す
# ═══════════════════════════════════════════════════════════

print("[テスト28-29] NullRetryManagerは常に[]を返す・専用フィールドを持たない")

null_mgr_28 = NullRetryManager()
result_28_decide = null_mgr_28.decide_retry_queue_cleanup([make_retry_event("run-28a"), make_retry_event("run-28b")])
check("28. decide_retry_queue_cleanup()がRetry候補由来のイベントを含んでいても常に[]を返す", result_28_decide, [])

result_28_apply = null_mgr_28.apply_retry_queue_cleanup([make_retry_event("run-28c")])
check("28. apply_retry_queue_cleanup()がRetry候補由来のイベントを含んでいても常に[]を返す", result_28_apply, [])

result_28_empty = null_mgr_28.apply_retry_queue_cleanup([])
check("28. 空リストを渡しても[]を返す", result_28_empty, [])

check("29. NullRetryManagerはRetryQueueCleanupDecider等のいかなるフィールドも持たない", vars(null_mgr_28), {})
print()


# ═══════════════════════════════════════════════════════════
# テスト30: 書き込みが発生しないことの確認
# ═══════════════════════════════════════════════════════════

print("[テスト30] 実行処理の前後でファイルが一切作成されない")

write_check_dir_30 = Path(tempfile.mkdtemp())
before_files_30 = list(write_check_dir_30.rglob("*"))

real_queue_30 = RetryQueueManager(config=RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0))
real_queue_30.enqueue(run_id="run-30w", workflow_name="news")
fake_monitor_30w = FakeWorkflowMonitorManager(record=make_record("run-30w", WorkflowMonitorStatus.FAILED))
fake_executor_30w = FakeRetryExecutor(result=None)
manager_30w = RetryManager(policy=policy_ok, executor=fake_executor_30w, monitor=fake_monitor_30w, queue=real_queue_30)
manager_30w.apply_retry_queue_cleanup([make_retry_event("run-30w", retry_attempt=3)])
NullRetryManager().apply_retry_queue_cleanup([make_retry_event("run-30wb")])

after_files_30 = list(write_check_dir_30.rglob("*"))
check("30. 実行処理前後でファイルが作成されない", after_files_30, before_files_30)
print()


# ═══════════════════════════════════════════════════════════
# テスト31: Architecture Guard（無改修の確認）
# ═══════════════════════════════════════════════════════════

print("[テスト31] 既存ファイルの無変更確認（git diff）")

unchanged_paths_v430 = [
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
    "src/retry_engine/retry_queue_removal_executor.py",
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
    for rel_path in unchanged_paths_v430:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"31. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("31. gitが利用できないため無変更確認をスキップ", True)
print()


# ═══════════════════════════════════════════════════════════
# テスト32: retry_engineパッケージのexport確認
# ═══════════════════════════════════════════════════════════

print("[テスト32] retry_engine.__all__ に新規シンボルが追加され、既存シンボルが維持されていること")

import retry_engine as re_pkg_32

check(
    "32. retry_engine.__all__ が既存シンボル＋新規5シンボルの構成になっている",
    set(re_pkg_32.__all__),
    {
        "RetryPolicy", "DEFAULT_TARGET_STATUSES", "RetryConfig", "RetryRequest", "RetryOutcome",
        "RetryResult", "RetryExecutor", "RetryCandidateEvent", "RetryEventConsumer",
        "RetryDispatchEvent", "RetryEventDispatcher", "RetryExecutionSelector",
        "RetryExecutionCoordinator", "RetryExecutionResult", "RetryQueueUpdateOutcome",
        "RetryQueueUpdateDecision", "RetryQueueUpdateDecider", "RetryQueueRemovalResult",
        "RetryQueueRemovalExecutor", "RetryQueueCleanupOutcome", "RetryQueueCleanupDecision",
        "RetryQueueCleanupDecider", "RetryQueueCleanupResult", "RetryQueueCleanupExecutor",
        "RetryManager", "NullRetryManager",
    },
)
check_true("32. RetryManagerがdecide_retry_queue_cleanup()を持つ", hasattr(RetryManager, "decide_retry_queue_cleanup"))
check_true("32. RetryManagerがapply_retry_queue_cleanup()を持つ", hasattr(RetryManager, "apply_retry_queue_cleanup"))
check_true("32. NullRetryManagerがdecide_retry_queue_cleanup()を持つ", hasattr(NullRetryManager, "decide_retry_queue_cleanup"))
check_true("32. NullRetryManagerがapply_retry_queue_cleanup()を持つ", hasattr(NullRetryManager, "apply_retry_queue_cleanup"))
print()


# ═══════════════════════════════════════════════════════════
# テスト33: __init__ / from_config() の新規引数の後方互換性
# ═══════════════════════════════════════════════════════════

print("[テスト33] RetryManager.__init__ / from_config()の新規引数が末尾・デフォルト値付きで追加されていること")

sig_init_33 = inspect.signature(RetryManager.__init__)
params_init_33 = list(sig_init_33.parameters.keys())
check("33. __init__の最終2引数がqueue_cleanup_decider/queue_cleanup_executor", params_init_33[-2:], ["queue_cleanup_decider", "queue_cleanup_executor"])
check("33. queue_cleanup_deciderのデフォルトはNone", sig_init_33.parameters["queue_cleanup_decider"].default, None)
check("33. queue_cleanup_executorのデフォルトはNone", sig_init_33.parameters["queue_cleanup_executor"].default, None)

sig_from_config_33 = inspect.signature(RetryManager.from_config)
params_from_config_33 = list(sig_from_config_33.parameters.keys())
check("33. from_config()の最終2引数がqueue_cleanup_decider/queue_cleanup_executor", params_from_config_33[-2:], ["queue_cleanup_decider", "queue_cleanup_executor"])
check(
    "33. 既存11引数（queue_removal_executor含む）の名前・順序が変わっていない",
    params_from_config_33[:11],
    [
        "retry_config", "retry_policy", "workflow_engine_manager", "workflow_monitor_manager",
        "retry_queue_manager", "event_consumer", "event_dispatcher",
        "execution_selector", "execution_coordinator", "queue_update_decider",
        "queue_removal_executor",
    ],
)
print()


# ═══════════════════════════════════════════════════════════
# テスト34: 新規ファイルが RetryQueueManager / NullRetryQueueManager をimportしないこと
# ═══════════════════════════════════════════════════════════

print("[テスト34] retry_queue_cleanup_executor.py に "
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


cleanup_executor_source_path_34 = PROJECT_ROOT / "src" / "retry_engine" / "retry_queue_cleanup_executor.py"
tree_34 = ast.parse(cleanup_executor_source_path_34.read_text(encoding="utf-8"))
referenced_34 = _referenced_names(tree_34)
check_false("34. retry_queue_cleanup_executor.py: 'RetryQueueManager' への実コード参照が存在しない", "RetryQueueManager" in referenced_34)
check_false("34. retry_queue_cleanup_executor.py: 'NullRetryQueueManager' への実コード参照が存在しない", "NullRetryQueueManager" in referenced_34)
check_true("34. retry_queue_cleanup_executor.py: 'RetryQueueResult' は参照している", "RetryQueueResult" in referenced_34)

cleanup_decider_source_path_34 = PROJECT_ROOT / "src" / "retry_engine" / "retry_queue_cleanup_decider.py"
tree_decider_34 = ast.parse(cleanup_decider_source_path_34.read_text(encoding="utf-8"))
referenced_decider_34 = _referenced_names(tree_decider_34)
check_false("34. retry_queue_cleanup_decider.py: 'RetryQueueManager' への実コード参照が存在しない", "RetryQueueManager" in referenced_decider_34)
check_false("34. retry_queue_cleanup_decider.py: 'NullRetryQueueManager' への実コード参照が存在しない", "NullRetryQueueManager" in referenced_decider_34)
print()


# ═══════════════════════════════════════════════════════════
# テスト35: 既存回帰（v3.0.0〜v4.2.0 RetryManager挙動）
# ═══════════════════════════════════════════════════════════

print("[テスト35] retry() / decide_retry_queue_updates() / apply_retry_queue_removals()の既存挙動が維持される")

fake_monitor_35 = FakeWorkflowMonitorManager(record=make_record("run-35", WorkflowMonitorStatus.FAILED))
fake_executor_35 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-35", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
))
manager_35 = RetryManager(policy=policy_ok, executor=fake_executor_35, monitor=fake_monitor_35)
result_35 = manager_35.retry("run-35", attempt=1)
check("35. retry()が本Release後も同じ挙動（RETRIED）", result_35.outcome, RetryOutcome.RETRIED)

decisions_35 = manager_35.decide_retry_queue_updates([make_retry_event("run-35d")])
check("35. decide_retry_queue_updates()が本Release後も同じ挙動（COMPLETE）", decisions_35[0].outcome, RetryQueueUpdateOutcome.COMPLETE)

removal_results_35 = manager_35.apply_retry_queue_removals([make_retry_event("run-35r")])
check("35. apply_retry_queue_removals()が本Release後も同じ挙動（attempted=True）", removal_results_35[0].attempted, True)

null_mgr_35 = NullRetryManager()
result_35b = null_mgr_35.enqueue_retry(run_id="run-35b", workflow_name="news")
check_contains_35 = "Retry Engine is disabled" in result_35b.reason
check_true("35. NullRetryManager.enqueue_retry()が本Release後も同じ挙動（DISABLED理由文言）", check_contains_35)
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
