"""
E2E テスト: v4.4.0 NOT_FOUND / DISABLED Cleanup Foundation

テストシナリオ（docs/design/retry_queue_notfound_disabled_cleanup_foundation.md
3章・5章・6章・12章 対応）:
    ── RetryOutcomeTerminality：Terminal/Transient分類表 ──
    1.  classify_terminality(NOT_FOUND) → TERMINAL
    2.  classify_terminality(DISABLED) → TRANSIENT
    3.  classify_terminality(COMPLETE/FAIL/SKIPPED) → いずれもTERMINAL（参考値）
    4.  classify_reason()がRetryQueueUpdateDecisionから正しい起源を導出する（5パターン）

    ── 整合性ガードテスト（Architecture Review 12.1節 Recommendation 1） ──
    5.  COMPLETE/FAILについてclassify_terminality()の結果（TERMINAL）と、
        実際にRetryQueueRemovalExecutor（v4.2.0）がremoveを実行する範囲が一致する
    6.  SKIPPEDについてclassify_terminality()の結果（TERMINAL）と、
        実際にRetryQueueCleanupDecider（v4.3.0）がCLEANUPと判定する範囲が一致する

    ── RetryQueueTerminalCleanupDecider単体：CLEANUP/KEEP判定方針 ──
    7.  NOOP + retry_result.outcome=NOT_FOUND → CLEANUP（Terminal）
    8.  NOOP + retry_result.outcome=DISABLED → KEEP（Transient）
    9.  NOOP + retry_result.outcome=SKIPPED → KEEP（対象外。v4.3.0の責務）
    10. update_decision.outcome=COMPLETE → KEEP（対象外。v4.2.0の責務）
    11. update_decision.outcome=FAIL → KEEP（対象外。v4.2.0の責務）
    12. decide_all()が複数件を順序を保ったまま処理する
    13. 空リストを渡した場合は空リストを返す
    14. RetryQueueTerminalCleanupDecision.update_decisionが元のRetryQueueUpdateDecisionそのもの
    15. reason文字列でCLEANUP/KEEPが区別できる

    ── RetryQueueTerminalCleanupExecutor単体：除去方針 ──
    16. outcome=CLEANUP → remove_fnが呼ばれ、attempted=True・queue_result=REMOVED
    17. outcome=KEEP → remove_fnが呼ばれず、attempted=False・queue_result=None
    18. CLEANUPだが対象run_idがQueueに存在しない → queue_result=NOT_FOUND（エラー扱いしない）
    19. RETRY_QUEUE_ENABLED=false（NullRetryQueueManager.remove）→ queue_result=DISABLED
    20. apply_all()が複数件を順序を保ったまま処理する
    21. 空リストを渡した場合は空リストを返す
    22. RetryQueueTerminalCleanupResult.decisionが元のRetryQueueTerminalCleanupDecisionそのもの

    ── RetryManager.decide_retry_queue_terminal_cleanup() / apply_retry_queue_terminal_cleanup()：委譲の正確性 ──
    23. terminal_cleanup_decider / terminal_cleanup_executor省略時、自動フォールバックする
    24. DIで渡したFakeDeciderへ、decide_retry_queue_updates()の結果がそのまま渡る
    25. DIで渡したFakeExecutorへ、decide_retry_queue_terminal_cleanup()の結果がそのまま渡る
    26. remove_fnにself._queue.removeが渡される
    27. from_config()の既存14引数呼び出しが本Release前と同じゲート判定結果を返す
    28. from_config()でterminal_cleanup_decider/executorを渡すと実際に配線される

    ── apply_retry_queue_terminal_cleanup()と既存Queue操作の独立性 ──
    29. apply_retry_queue_terminal_cleanup()を呼んでもFakeQueue.enqueue()/dequeue()は呼ばれない
    30. Architecture Guard：apply_retry_queue_terminal_cleanup()のソースコードが
        self._queue.enqueue / self._queue.dequeue を一切参照しない

    ── 実際のRetryQueueManager.remove()が呼ばれる統合確認（真のQueue反映） ──
    31. 実QueueにあるNOT_FOUND由来の項目は実際に除去される（count()減少・exists()がFalse）
    32. 実Queueに残っているDISABLED由来の項目はterminal cleanupでは除去されない（Keep）
    33. 実Queueに残っているSKIPPED由来の項目もterminal cleanupでは除去されない（v4.3.0の責務）

    ── NullRetryManager：常に[]を返す ──
    34. NullRetryManager.decide_retry_queue_terminal_cleanup() / apply_retry_queue_terminal_cleanup()は常に[]
    35. NullRetryManagerはRetryQueueTerminalCleanupDecider等のいかなるフィールドも持たない

    ── 書き込みが発生しないことの確認 ──
    36. 実行処理の前後でファイルが一切作成されない

    ── Architecture Guard（無改修の確認・新規ファイルのimport制約） ──
    37. src/scheduler/ / src/retry_scheduler_decision/ / src/retry_scheduler_source/ /
        src/retry_queue/ 配下の全ファイル、および src/retry_engine/ のうち本Releaseで
        変更していないファイル（retry_queue_update_decider.py・retry_queue_removal_executor.py・
        retry_queue_cleanup_decider.py・retry_queue_cleanup_executor.py含む）に変更がないこと
    38. retry_engineパッケージの__all__に新規シンボルが追加され、既存シンボルは維持
    39. RetryManager.__init__ / from_config()の新規引数が末尾・デフォルト値付きで追加
    40. retry_queue_terminal_cleanup_executor.py が RetryQueueManager / NullRetryQueueManager を
        importしていないこと（AST）。RetryQueueResultは参照する

    ── 既存回帰（v3.0.0〜v4.3.0 RetryManager挙動）──
    41. retry() / decide_retry_queue_updates() / apply_retry_queue_removals() /
        apply_retry_queue_cleanup()の挙動が本Releaseでも維持される

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v4_4_0_retry_queue_notfound_disabled_cleanup_foundation.py
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
print("v4.4.0 NOT_FOUND / DISABLED Cleanup Foundation E2E テスト")
print("=" * 60)
print()

from retry_queue import RetryQueueConfig, RetryQueueManager, RetryQueueOutcome, RetryQueueResult
from scheduler import SchedulerEvent
from workflow_engine import NullWorkflowEngineManager, WorkflowEngineResult
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus
from retry_engine import (
    DEFAULT_TARGET_STATUSES,
    RETRY_OUTCOME_TERMINALITY,
    NullRetryManager,
    RetryCandidateEvent,
    RetryCleanupReason,
    RetryConfig,
    RetryDispatchEvent,
    RetryExecutionResult,
    RetryManager,
    RetryOutcome,
    RetryOutcomeTerminality,
    RetryPolicy,
    RetryQueueCleanupDecider,
    RetryQueueCleanupOutcome,
    RetryQueueRemovalExecutor,
    RetryQueueTerminalCleanupDecider,
    RetryQueueTerminalCleanupDecision,
    RetryQueueTerminalCleanupExecutor,
    RetryQueueTerminalCleanupResult,
    RetryQueueUpdateDecider,
    RetryQueueUpdateDecision,
    RetryQueueUpdateOutcome,
    RetryResult,
    classify_reason,
    classify_terminality,
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


class FakeRetryQueueTerminalCleanupDecider:
    """テスト専用のFake。decide_all()呼び出しを記録し、固定の戻り値を返す。"""

    def __init__(self, result: "list[RetryQueueTerminalCleanupDecision] | None" = None):
        self.calls: list[list] = []
        self._result = result if result is not None else []

    def decide_all(self, update_decisions):
        self.calls.append(update_decisions)
        return self._result


class FakeRetryQueueTerminalCleanupExecutor:
    """テスト専用のFake。apply_all()呼び出しを記録し、固定の戻り値を返す。"""

    def __init__(self, result: "list[RetryQueueTerminalCleanupResult] | None" = None):
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
# テスト1-4: RetryOutcomeTerminality：Terminal/Transient分類表
# ═══════════════════════════════════════════════════════════

print("[テスト1-3] classify_terminality()：各Reasonの分類")

check("1. classify_terminality(NOT_FOUND) → TERMINAL", classify_terminality(RetryCleanupReason.NOT_FOUND), RetryOutcomeTerminality.TERMINAL)
check("2. classify_terminality(DISABLED) → TRANSIENT", classify_terminality(RetryCleanupReason.DISABLED), RetryOutcomeTerminality.TRANSIENT)
check(
    "3. classify_terminality(COMPLETE/FAIL/SKIPPED) → いずれもTERMINAL（参考値）",
    [
        classify_terminality(RetryCleanupReason.COMPLETE),
        classify_terminality(RetryCleanupReason.FAIL),
        classify_terminality(RetryCleanupReason.SKIPPED),
    ],
    [RetryOutcomeTerminality.TERMINAL, RetryOutcomeTerminality.TERMINAL, RetryOutcomeTerminality.TERMINAL],
)
print()

print("[テスト4] classify_reason()：RetryQueueUpdateDecisionから正しい起源を導出する")

check("4. complete → RetryCleanupReason.COMPLETE", classify_reason(make_update_decision("run-4a", "complete")), RetryCleanupReason.COMPLETE)
check("4. fail → RetryCleanupReason.FAIL", classify_reason(make_update_decision("run-4b", "fail")), RetryCleanupReason.FAIL)
check("4. skipped → RetryCleanupReason.SKIPPED", classify_reason(make_update_decision("run-4c", "skipped")), RetryCleanupReason.SKIPPED)
check("4. not_found → RetryCleanupReason.NOT_FOUND", classify_reason(make_update_decision("run-4d", "not_found")), RetryCleanupReason.NOT_FOUND)
check("4. disabled → RetryCleanupReason.DISABLED", classify_reason(make_update_decision("run-4e", "disabled")), RetryCleanupReason.DISABLED)
print()


# ═══════════════════════════════════════════════════════════
# テスト5-6: 整合性ガードテスト（Architecture Review 12.1節 Recommendation 1）
# ═══════════════════════════════════════════════════════════

print("[テスト5] COMPLETE/FAILの分類（TERMINAL）と、v4.2.0 RetryQueueRemovalExecutorの実際の除去範囲が一致する")

removal_executor_5 = RetryQueueRemovalExecutor()
fake_queue_5 = FakeRetryQueueManager()

complete_decision_5 = make_update_decision("run-5a", "complete")
removal_result_5a = removal_executor_5.apply(complete_decision_5, fake_queue_5.remove)
terminality_5a = classify_terminality(classify_reason(complete_decision_5))
check(
    "5. COMPLETE: classify_terminality()=TERMINAL と RetryQueueRemovalExecutorが実際にremoveを実行すること(attempted=True)が一致",
    (terminality_5a == RetryOutcomeTerminality.TERMINAL, removal_result_5a.attempted),
    (True, True),
)

fail_decision_5 = make_update_decision("run-5b", "fail")
removal_result_5b = removal_executor_5.apply(fail_decision_5, fake_queue_5.remove)
terminality_5b = classify_terminality(classify_reason(fail_decision_5))
check(
    "5. FAIL: classify_terminality()=TERMINAL と RetryQueueRemovalExecutorが実際にremoveを実行すること(attempted=True)が一致",
    (terminality_5b == RetryOutcomeTerminality.TERMINAL, removal_result_5b.attempted),
    (True, True),
)
print()

print("[テスト6] SKIPPEDの分類（TERMINAL）と、v4.3.0 RetryQueueCleanupDeciderの実際のCLEANUP判定が一致する")

cleanup_decider_6 = RetryQueueCleanupDecider()
skipped_decision_6 = make_update_decision("run-6", "skipped")
cleanup_result_6 = cleanup_decider_6.decide(skipped_decision_6)
terminality_6 = classify_terminality(classify_reason(skipped_decision_6))
check(
    "6. SKIPPED: classify_terminality()=TERMINAL と RetryQueueCleanupDeciderの判定(CLEANUP)が一致",
    (terminality_6 == RetryOutcomeTerminality.TERMINAL, cleanup_result_6.outcome == RetryQueueCleanupOutcome.CLEANUP),
    (True, True),
)
print()


# ═══════════════════════════════════════════════════════════
# テスト7-15: RetryQueueTerminalCleanupDecider単体：CLEANUP/KEEP判定方針
# ═══════════════════════════════════════════════════════════

print("[テスト7-11] decide()：NOOP+NOT_FOUND→CLEANUP、NOOP+DISABLED→KEEP、その他→KEEP（対象外）")

decider_7 = RetryQueueTerminalCleanupDecider()

decision_not_found_7 = make_update_decision("run-107", "not_found")
result_7 = decider_7.decide(decision_not_found_7)
check("7. NOOP+NOT_FOUND → CLEANUP", result_7.outcome, RetryQueueCleanupOutcome.CLEANUP)

decision_disabled_8 = make_update_decision("run-108", "disabled")
result_8 = decider_7.decide(decision_disabled_8)
check("8. NOOP+DISABLED → KEEP", result_8.outcome, RetryQueueCleanupOutcome.KEEP)

decision_skipped_9 = make_update_decision("run-109", "skipped")
result_9 = decider_7.decide(decision_skipped_9)
check("9. NOOP+SKIPPED → KEEP（対象外。v4.3.0の責務）", result_9.outcome, RetryQueueCleanupOutcome.KEEP)

decision_complete_10 = make_update_decision("run-110", "complete")
result_10 = decider_7.decide(decision_complete_10)
check("10. update_decision.outcome=COMPLETE → KEEP（対象外。v4.2.0の責務）", result_10.outcome, RetryQueueCleanupOutcome.KEEP)

decision_fail_11 = make_update_decision("run-111", "fail")
result_11 = decider_7.decide(decision_fail_11)
check("11. update_decision.outcome=FAIL → KEEP（対象外。v4.2.0の責務）", result_11.outcome, RetryQueueCleanupOutcome.KEEP)
print()

print("[テスト12-13] decide_all()：複数件を順序を保ったまま処理・空リスト")

decisions_12 = [
    make_update_decision("run-112a", "not_found"),
    make_update_decision("run-112b", "disabled"),
    make_update_decision("run-112c", "skipped"),
    make_update_decision("run-112d", "not_found"),
]
results_12 = decider_7.decide_all(decisions_12)
check(
    "12. decide_all()が4件を順序を保ったまま処理する",
    [r.outcome for r in results_12],
    [
        RetryQueueCleanupOutcome.CLEANUP, RetryQueueCleanupOutcome.KEEP,
        RetryQueueCleanupOutcome.KEEP, RetryQueueCleanupOutcome.CLEANUP,
    ],
)

results_13 = decider_7.decide_all([])
check("13. 空リストを渡した場合は空リストを返す", results_13, [])
print()

print("[テスト14-15] RetryQueueTerminalCleanupDecision.update_decisionの同一性・reason文字列")

decision_14 = make_update_decision("run-114", "not_found")
result_14 = decider_7.decide(decision_14)
check_true("14. RetryQueueTerminalCleanupDecision.update_decisionが元のRetryQueueUpdateDecisionそのもの", result_14.update_decision is decision_14)

decision_cleanup_15 = make_update_decision("run-115a", "not_found")
result_cleanup_15 = decider_7.decide(decision_cleanup_15)
decision_keep_15 = make_update_decision("run-115b", "disabled")
result_keep_15 = decider_7.decide(decision_keep_15)
check(
    "15. CLEANUP/KEEPのreason文字列が区別できる",
    len({result_cleanup_15.reason, result_keep_15.reason}),
    2,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト16-22: RetryQueueTerminalCleanupExecutor単体：除去方針
# ═══════════════════════════════════════════════════════════

print("[テスト16-17] apply()：CLEANUP→remove呼び出し・KEEP→remove不呼び出し")

executor_16 = RetryQueueTerminalCleanupExecutor()
terminal_decider_16 = RetryQueueTerminalCleanupDecider()

fake_queue_16 = FakeRetryQueueManager()
cleanup_decision_16 = terminal_decider_16.decide(make_update_decision("run-116", "not_found"))
result_16 = executor_16.apply(cleanup_decision_16, fake_queue_16.remove)
check_true("16. CLEANUP → attempted=True", result_16.attempted)
check("16. CLEANUP → remove_fnが1回呼ばれる（run-116）", fake_queue_16.remove_calls, ["run-116"])
check("16. CLEANUP → queue_result.outcome=REMOVED", result_16.queue_result.outcome, RetryQueueOutcome.REMOVED)

fake_queue_17 = FakeRetryQueueManager()
keep_decision_17 = terminal_decider_16.decide(make_update_decision("run-117", "disabled"))
result_17 = executor_16.apply(keep_decision_17, fake_queue_17.remove)
check_false("17. KEEP → attempted=False", result_17.attempted)
check("17. KEEP → remove_fnが一切呼ばれない", fake_queue_17.remove_calls, [])
check("17. KEEP → queue_result=None", result_17.queue_result, None)
print()

print("[テスト18] CLEANUPだが対象run_idがQueueに存在しない → NOT_FOUND（エラー扱いしない）")

fake_queue_18 = FakeRetryQueueManager(
    remove_result=RetryQueueResult(outcome=RetryQueueOutcome.NOT_FOUND, item=None, reason="not found"),
)
cleanup_decision_18 = terminal_decider_16.decide(make_update_decision("run-118", "not_found"))
result_18 = executor_16.apply(cleanup_decision_18, fake_queue_18.remove)
check_true("18. attempted=True", result_18.attempted)
check("18. queue_result.outcome=NOT_FOUND", result_18.queue_result.outcome, RetryQueueOutcome.NOT_FOUND)
print()

print("[テスト19] RETRY_QUEUE_ENABLED=false（NullRetryQueueManager.remove）→ DISABLED")

fake_queue_19 = FakeRetryQueueManager(
    remove_result=RetryQueueResult(outcome=RetryQueueOutcome.DISABLED, item=None, reason="disabled"),
)
cleanup_decision_19 = terminal_decider_16.decide(make_update_decision("run-119", "not_found"))
result_19 = executor_16.apply(cleanup_decision_19, fake_queue_19.remove)
check_true("19. attempted=True", result_19.attempted)
check("19. queue_result.outcome=DISABLED", result_19.queue_result.outcome, RetryQueueOutcome.DISABLED)
print()

print("[テスト20-21] apply_all()：複数件を順序を保ったまま処理・空リスト")

fake_queue_20 = FakeRetryQueueManager()
cleanup_decisions_20 = terminal_decider_16.decide_all([
    make_update_decision("run-120a", "not_found"),
    make_update_decision("run-120b", "disabled"),
    make_update_decision("run-120c", "not_found"),
])
results_20 = executor_16.apply_all(cleanup_decisions_20, fake_queue_20.remove)
check("20. apply_all()が3件を順序を保ったまま処理する（attempted）", [r.attempted for r in results_20], [True, False, True])
check("20. remove_fnはCLEANUPの2件のみ呼ばれる", fake_queue_20.remove_calls, ["run-120a", "run-120c"])

results_21 = executor_16.apply_all([], fake_queue_20.remove)
check("21. 空リストを渡した場合は空リストを返す", results_21, [])
print()

print("[テスト22] RetryQueueTerminalCleanupResult.decisionの同一性")

cleanup_decision_22 = terminal_decider_16.decide(make_update_decision("run-122", "not_found"))
result_22 = executor_16.apply(cleanup_decision_22, FakeRetryQueueManager().remove)
check_true("22. RetryQueueTerminalCleanupResult.decisionが元のRetryQueueTerminalCleanupDecisionそのもの", result_22.decision is cleanup_decision_22)
print()


# ═══════════════════════════════════════════════════════════
# テスト23-28: RetryManager.decide_retry_queue_terminal_cleanup() / apply_retry_queue_terminal_cleanup()：委譲の正確性
# ═══════════════════════════════════════════════════════════

print("[テスト23] terminal_cleanup_decider / terminal_cleanup_executor省略時、自動フォールバックする")

manager_23 = RetryManager(policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None))
check_true("23. terminal_cleanup_decider省略時、内部にRetryQueueTerminalCleanupDeciderが構築される", isinstance(manager_23._terminal_cleanup_decider, RetryQueueTerminalCleanupDecider))
check_true("23. terminal_cleanup_executor省略時、内部にRetryQueueTerminalCleanupExecutorが構築される", isinstance(manager_23._terminal_cleanup_executor, RetryQueueTerminalCleanupExecutor))
print()

print("[テスト24] DIで渡したFakeDeciderへ、decide_retry_queue_updates()の結果がそのまま渡る")

fake_monitor_24 = FakeWorkflowMonitorManager(record=make_record("run-124", WorkflowMonitorStatus.FAILED))
fake_executor_24 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-124", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
))
fake_terminal_decider_24 = FakeRetryQueueTerminalCleanupDecider(result=["placeholder-terminal-decision"])
manager_24 = RetryManager(
    policy=policy_ok, executor=fake_executor_24, monitor=fake_monitor_24,
    terminal_cleanup_decider=fake_terminal_decider_24,
)
events_24 = [make_retry_event("run-124")]
result_24 = manager_24.decide_retry_queue_terminal_cleanup(events_24)
check("24. FakeTerminalCleanupDecider.decide_all()が1回だけ呼ばれる", len(fake_terminal_decider_24.calls), 1)
check(
    "24. decide_retry_queue_updates()の戻り値がdecide_all()にそのまま渡る",
    [d.execution_result.dispatch_event.candidate_event.run_id for d in fake_terminal_decider_24.calls[0]],
    ["run-124"],
)
check("24. 最終的な戻り値がFakeTerminalCleanupDeciderの戻り値そのもの", result_24, ["placeholder-terminal-decision"])
print()

print("[テスト25-26] DIで渡したFakeExecutorへの委譲・remove_fnの伝播")

fake_monitor_25 = FakeWorkflowMonitorManager(record=make_record("run-125", WorkflowMonitorStatus.FAILED))
fake_executor_25 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-125", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
))
fake_terminal_executor_25 = FakeRetryQueueTerminalCleanupExecutor(result=["placeholder-terminal-result"])
fake_queue_25 = FakeRetryQueueManager()
manager_25 = RetryManager(
    policy=policy_ok, executor=fake_executor_25, monitor=fake_monitor_25,
    queue=fake_queue_25,
    terminal_cleanup_executor=fake_terminal_executor_25,
)
events_25 = [make_retry_event("run-125")]
result_25 = manager_25.apply_retry_queue_terminal_cleanup(events_25)
check("25. FakeTerminalCleanupExecutor.apply_all()が1回だけ呼ばれる", len(fake_terminal_executor_25.calls), 1)
check(
    "25. decide_retry_queue_terminal_cleanup()の戻り値がapply_all()にそのまま渡る",
    [d.update_decision.execution_result.dispatch_event.candidate_event.run_id for d in fake_terminal_executor_25.calls[0][0]],
    ["run-125"],
)
check("25. 最終的な戻り値がFakeTerminalCleanupExecutorの戻り値そのもの", result_25, ["placeholder-terminal-result"])
check_true("26. remove_fnにself._queue.remove（FakeQueue.remove）が渡される", fake_terminal_executor_25.calls[0][1] == fake_queue_25.remove)
print()

print("[テスト27] from_config()の既存14引数呼び出しが本Release前と同じゲート判定結果を返す")

fake_engine_ok = FakeWorkflowEngineManager()
fake_monitor_ok = FakeWorkflowMonitorManager(record=None)

mgr_27a = RetryManager.from_config(RetryConfig(enabled=False), policy_ok, fake_engine_ok, fake_monitor_ok)
check_true("27. enabled=Falseの4引数呼び出し → NullRetryManager", isinstance(mgr_27a, NullRetryManager))

mgr_27b = RetryManager.from_config(RetryConfig(enabled=True), policy_ok, NullWorkflowEngineManager(), fake_monitor_ok)
check_true("27. NullWorkflowEngineManagerの4引数呼び出し → NullRetryManager", isinstance(mgr_27b, NullRetryManager))

mgr_27c = RetryManager.from_config(RetryConfig(enabled=True), policy_ok, fake_engine_ok, fake_monitor_ok)
check_true("27. 両方満たす4引数呼び出し → RetryManager（実インスタンス）", isinstance(mgr_27c, RetryManager))
check_true("27. terminal_cleanup_decider省略時、内部にRetryQueueTerminalCleanupDeciderが自動構築される", isinstance(mgr_27c._terminal_cleanup_decider, RetryQueueTerminalCleanupDecider))
check_true("27. terminal_cleanup_executor省略時、内部にRetryQueueTerminalCleanupExecutorが自動構築される", isinstance(mgr_27c._terminal_cleanup_executor, RetryQueueTerminalCleanupExecutor))
print()

print("[テスト28] from_config()でterminal_cleanup_decider/executorを渡すと実際に配線される")

fake_terminal_decider_28 = FakeRetryQueueTerminalCleanupDecider(result=[])
fake_terminal_executor_28 = FakeRetryQueueTerminalCleanupExecutor(result=[])
mgr_28 = RetryManager.from_config(
    RetryConfig(enabled=True), policy_ok, fake_engine_ok, fake_monitor_ok,
    terminal_cleanup_decider=fake_terminal_decider_28,
    terminal_cleanup_executor=fake_terminal_executor_28,
)
mgr_28.apply_retry_queue_terminal_cleanup([make_retry_event("run-28")])
check("28. from_config()経由で渡したterminal_cleanup_deciderに実際に委譲される", len(fake_terminal_decider_28.calls), 1)
check("28. from_config()経由で渡したterminal_cleanup_executorに実際に委譲される", len(fake_terminal_executor_28.calls), 1)
print()


# ═══════════════════════════════════════════════════════════
# テスト29-30: apply_retry_queue_terminal_cleanup()と既存Queue操作の独立性
# ═══════════════════════════════════════════════════════════

print("[テスト29] apply_retry_queue_terminal_cleanup()とenqueue()/dequeue()の独立性")

fake_queue_29 = FakeRetryQueueManager()
fake_monitor_29 = FakeWorkflowMonitorManager(record=None)  # NOT_FOUND
fake_executor_29 = FakeRetryExecutor(result=None)
manager_29 = RetryManager(policy=policy_ok, executor=fake_executor_29, monitor=fake_monitor_29, queue=fake_queue_29)

manager_29.apply_retry_queue_terminal_cleanup([make_retry_event("run-29")])
check("29. apply_retry_queue_terminal_cleanup()を呼んでもFakeQueue.enqueue()は呼ばれない", len(fake_queue_29.enqueue_calls), 0)
check("29. apply_retry_queue_terminal_cleanup()を呼んでもFakeQueue.dequeue()は呼ばれない", fake_queue_29.dequeue_calls, 0)
check("29. NOT_FOUND判定のためFakeQueue.remove()は1回呼ばれる", len(fake_queue_29.remove_calls), 1)
print()

print("[テスト30] Architecture Guard：apply_retry_queue_terminal_cleanup()が"
      "self._queue.enqueue / self._queue.dequeue を参照しない（静的検査）")

retry_manager_source = (PROJECT_ROOT / "src" / "retry_engine" / "retry_manager.py").read_text(encoding="utf-8")


def extract_method_body(source: str, method_name: str) -> str:
    start_match = re.search(rf"\n    def {re.escape(method_name)}\(", source)
    rest = source[start_match.end():]
    next_match = re.search(r"\n    def ", rest)
    end = next_match.start() if next_match else len(rest)
    return rest[:end]


body_apply_30 = extract_method_body(retry_manager_source, "apply_retry_queue_terminal_cleanup")
check_false(
    "30. RetryManager.apply_retry_queue_terminal_cleanup()本体が「self._queue.enqueue」を含まない",
    "self._queue.enqueue" in body_apply_30,
)
check_false(
    "30. RetryManager.apply_retry_queue_terminal_cleanup()本体が「self._queue.dequeue」を含まない",
    "self._queue.dequeue" in body_apply_30,
)
check_true(
    "30. RetryManager.apply_retry_queue_terminal_cleanup()本体は「self._queue.remove」を参照している",
    "self._queue.remove" in body_apply_30,
)
check_true(
    "30. RetryManager.apply_retry_queue_terminal_cleanup()本体は「self._terminal_cleanup_executor」を参照している",
    "self._terminal_cleanup_executor" in body_apply_30,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト31-33: 実際のRetryQueueManager.remove()が呼ばれる統合確認（真のQueue反映）
# ═══════════════════════════════════════════════════════════

print("[テスト31] 実QueueにあるNOT_FOUND由来の項目は実際に除去される")

real_queue_31 = RetryQueueManager(config=RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0))
real_queue_31.enqueue(run_id="run-31", workflow_name="news")
check_true("31. enqueue直後はexists()がTrue", real_queue_31.exists("run-31"))

fake_monitor_31 = FakeWorkflowMonitorManager(record=None)  # get_status()がNone → NOT_FOUND
fake_executor_31 = FakeRetryExecutor(result=None)
manager_31 = RetryManager(policy=policy_ok, executor=fake_executor_31, monitor=fake_monitor_31, queue=real_queue_31)
results_31 = manager_31.apply_retry_queue_terminal_cleanup([make_retry_event("run-31")])
check("31. 除去結果が1件返る", len(results_31), 1)
check_true("31. attempted=True（NOT_FOUND→CLEANUP）", results_31[0].attempted)
check("31. queue_result.outcome=REMOVED", results_31[0].queue_result.outcome, RetryQueueOutcome.REMOVED)
check_false("31. remove後はexists()がFalse（実際にQueueから除去された）", real_queue_31.exists("run-31"))
check("31. remove後はcount()が0", real_queue_31.count(), 0)
print()

print("[テスト32] 実Queueに残っているDISABLED由来の項目はterminal cleanupでは除去されない（Keep）")

real_queue_32 = RetryQueueManager(config=RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0))
real_queue_32.enqueue(run_id="run-32", workflow_name="news")

# RETRY_ENGINE_ENABLED=falseのNullRetryManagerと同じ理由でDISABLEDが生じるケースを
# RetryExecutionCoordinator経由で再現するため、RetryPolicyのtarget_statusesを
# 空集合にしてもDISABLEDにはならないため、ここではRetryOutcome.DISABLEDを
# 直接生成するmake_update_decisionのヘルパーパスと同じ構造をmanager経由でも
# 再現できないため、Decider/Executor単体の振る舞いはテスト7-8で確認済み。
# 本テストでは「実Queueに対してKEEP判定の項目はremove()が呼ばれない」ことを
# NullRetryManager経由のDISABLED相当リクエストではなく、SKIPPED（v4.3.0の責務、
# 本Releaseでは対象外＝KEEP）で確認する。
fake_monitor_32 = FakeWorkflowMonitorManager(record=make_record("run-32", WorkflowMonitorStatus.FAILED))
fake_executor_32 = FakeRetryExecutor(result=None)
manager_32 = RetryManager(policy=policy_ok, executor=fake_executor_32, monitor=fake_monitor_32, queue=real_queue_32)
results_32 = manager_32.apply_retry_queue_terminal_cleanup([make_retry_event("run-32", retry_attempt=3)])
check_false("32. SKIPPED相当 → attempted=False（terminal cleanupの対象外。v4.3.0の責務）", results_32[0].attempted)
check_true("32. remove()が呼ばれないためexists()はTrueのまま", real_queue_32.exists("run-32"))
print()

print("[テスト33] Decider単体でのDISABLED判定と実Queueへの非反映の整合性確認")

real_queue_33 = RetryQueueManager(config=RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0))
real_queue_33.enqueue(run_id="run-33", workflow_name="news")
disabled_decision_33 = terminal_decider_16.decide(make_update_decision("run-33", "disabled"))
check("33. DISABLED由来のNOOP → Decider単体でもKEEP", disabled_decision_33.outcome, RetryQueueCleanupOutcome.KEEP)
executor_result_33 = executor_16.apply(disabled_decision_33, real_queue_33.remove)
check_false("33. KEEP判定のためremove()は呼ばれない（attempted=False）", executor_result_33.attempted)
check_true("33. 実Queueにはrun-33が残ったまま", real_queue_33.exists("run-33"))
print()


# ═══════════════════════════════════════════════════════════
# テスト34-35: NullRetryManager：常に[]を返す
# ═══════════════════════════════════════════════════════════

print("[テスト34-35] NullRetryManagerは常に[]を返す・専用フィールドを持たない")

null_mgr_34 = NullRetryManager()
result_34_decide = null_mgr_34.decide_retry_queue_terminal_cleanup([make_retry_event("run-34a"), make_retry_event("run-34b")])
check("34. decide_retry_queue_terminal_cleanup()がRetry候補由来のイベントを含んでいても常に[]を返す", result_34_decide, [])

result_34_apply = null_mgr_34.apply_retry_queue_terminal_cleanup([make_retry_event("run-34c")])
check("34. apply_retry_queue_terminal_cleanup()がRetry候補由来のイベントを含んでいても常に[]を返す", result_34_apply, [])

result_34_empty = null_mgr_34.apply_retry_queue_terminal_cleanup([])
check("34. 空リストを渡しても[]を返す", result_34_empty, [])

check("35. NullRetryManagerはRetryQueueTerminalCleanupDecider等のいかなるフィールドも持たない", vars(null_mgr_34), {})
print()


# ═══════════════════════════════════════════════════════════
# テスト36: 書き込みが発生しないことの確認
# ═══════════════════════════════════════════════════════════

print("[テスト36] 実行処理の前後でファイルが一切作成されない")

write_check_dir_36 = Path(tempfile.mkdtemp())
before_files_36 = list(write_check_dir_36.rglob("*"))

real_queue_36 = RetryQueueManager(config=RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0))
real_queue_36.enqueue(run_id="run-36w", workflow_name="news")
fake_monitor_36w = FakeWorkflowMonitorManager(record=None)
fake_executor_36w = FakeRetryExecutor(result=None)
manager_36w = RetryManager(policy=policy_ok, executor=fake_executor_36w, monitor=fake_monitor_36w, queue=real_queue_36)
manager_36w.apply_retry_queue_terminal_cleanup([make_retry_event("run-36w")])
NullRetryManager().apply_retry_queue_terminal_cleanup([make_retry_event("run-36wb")])

after_files_36 = list(write_check_dir_36.rglob("*"))
check("36. 実行処理前後でファイルが作成されない", after_files_36, before_files_36)
print()


# ═══════════════════════════════════════════════════════════
# テスト37: Architecture Guard（無改修の確認）
# ═══════════════════════════════════════════════════════════

print("[テスト37] 既存ファイルの無変更確認（git diff）")

unchanged_paths_v440 = [
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
    "src/retry_engine/retry_queue_cleanup_decider.py",
    "src/retry_engine/retry_queue_cleanup_executor.py",
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
    for rel_path in unchanged_paths_v440:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"37. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("37. gitが利用できないため無変更確認をスキップ", True)
print()


# ═══════════════════════════════════════════════════════════
# テスト38: retry_engineパッケージのexport確認
# ═══════════════════════════════════════════════════════════

print("[テスト38] retry_engine.__all__ に新規シンボルが追加され、既存シンボルが維持されていること")

import retry_engine as re_pkg_38

check(
    "38. retry_engine.__all__ が既存シンボル＋新規シンボルの構成になっている",
    set(re_pkg_38.__all__),
    {
        "RetryPolicy", "DEFAULT_TARGET_STATUSES", "RetryConfig", "RetryRequest", "RetryOutcome",
        "RetryResult", "RetryExecutor", "RetryCandidateEvent", "RetryEventConsumer",
        "RetryDispatchEvent", "RetryEventDispatcher", "RetryExecutionSelector",
        "RetryExecutionCoordinator", "RetryExecutionResult", "RetryQueueUpdateOutcome",
        "RetryQueueUpdateDecision", "RetryQueueUpdateDecider", "RetryQueueRemovalResult",
        "RetryQueueRemovalExecutor", "RetryQueueCleanupOutcome", "RetryQueueCleanupDecision",
        "RetryQueueCleanupDecider", "RetryQueueCleanupResult", "RetryQueueCleanupExecutor",
        "RetryOutcomeTerminality", "RetryCleanupReason", "RETRY_OUTCOME_TERMINALITY",
        "classify_reason", "classify_terminality",
        "RetryQueueTerminalCleanupDecision", "RetryQueueTerminalCleanupDecider",
        "RetryQueueTerminalCleanupResult", "RetryQueueTerminalCleanupExecutor",
        "RetryManager", "NullRetryManager",
    },
)
check_true("38. RetryManagerがdecide_retry_queue_terminal_cleanup()を持つ", hasattr(RetryManager, "decide_retry_queue_terminal_cleanup"))
check_true("38. RetryManagerがapply_retry_queue_terminal_cleanup()を持つ", hasattr(RetryManager, "apply_retry_queue_terminal_cleanup"))
check_true("38. NullRetryManagerがdecide_retry_queue_terminal_cleanup()を持つ", hasattr(NullRetryManager, "decide_retry_queue_terminal_cleanup"))
check_true("38. NullRetryManagerがapply_retry_queue_terminal_cleanup()を持つ", hasattr(NullRetryManager, "apply_retry_queue_terminal_cleanup"))
print()


# ═══════════════════════════════════════════════════════════
# テスト39: __init__ / from_config() の新規引数の後方互換性
# ═══════════════════════════════════════════════════════════

print("[テスト39] RetryManager.__init__ / from_config()の新規引数が末尾・デフォルト値付きで追加されていること")

sig_init_39 = inspect.signature(RetryManager.__init__)
params_init_39 = list(sig_init_39.parameters.keys())
check("39. __init__の最終2引数がterminal_cleanup_decider/terminal_cleanup_executor", params_init_39[-2:], ["terminal_cleanup_decider", "terminal_cleanup_executor"])
check("39. terminal_cleanup_deciderのデフォルトはNone", sig_init_39.parameters["terminal_cleanup_decider"].default, None)
check("39. terminal_cleanup_executorのデフォルトはNone", sig_init_39.parameters["terminal_cleanup_executor"].default, None)

sig_from_config_39 = inspect.signature(RetryManager.from_config)
params_from_config_39 = list(sig_from_config_39.parameters.keys())
check("39. from_config()の最終2引数がterminal_cleanup_decider/terminal_cleanup_executor", params_from_config_39[-2:], ["terminal_cleanup_decider", "terminal_cleanup_executor"])
check(
    "39. 既存13引数（queue_cleanup_executor含む）の名前・順序が変わっていない",
    params_from_config_39[:13],
    [
        "retry_config", "retry_policy", "workflow_engine_manager", "workflow_monitor_manager",
        "retry_queue_manager", "event_consumer", "event_dispatcher",
        "execution_selector", "execution_coordinator", "queue_update_decider",
        "queue_removal_executor", "queue_cleanup_decider", "queue_cleanup_executor",
    ],
)
print()


# ═══════════════════════════════════════════════════════════
# テスト40: 新規ファイルが RetryQueueManager / NullRetryQueueManager をimportしないこと
# ═══════════════════════════════════════════════════════════

print("[テスト40] retry_queue_terminal_cleanup_executor.py に "
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


terminal_executor_source_path_40 = PROJECT_ROOT / "src" / "retry_engine" / "retry_queue_terminal_cleanup_executor.py"
tree_40 = ast.parse(terminal_executor_source_path_40.read_text(encoding="utf-8"))
referenced_40 = _referenced_names(tree_40)
check_false("40. retry_queue_terminal_cleanup_executor.py: 'RetryQueueManager' への実コード参照が存在しない", "RetryQueueManager" in referenced_40)
check_false("40. retry_queue_terminal_cleanup_executor.py: 'NullRetryQueueManager' への実コード参照が存在しない", "NullRetryQueueManager" in referenced_40)
check_true("40. retry_queue_terminal_cleanup_executor.py: 'RetryQueueResult' は参照している", "RetryQueueResult" in referenced_40)

terminal_decider_source_path_40 = PROJECT_ROOT / "src" / "retry_engine" / "retry_queue_terminal_cleanup_decider.py"
tree_decider_40 = ast.parse(terminal_decider_source_path_40.read_text(encoding="utf-8"))
referenced_decider_40 = _referenced_names(tree_decider_40)
check_false("40. retry_queue_terminal_cleanup_decider.py: 'RetryQueueManager' への実コード参照が存在しない", "RetryQueueManager" in referenced_decider_40)
check_false("40. retry_queue_terminal_cleanup_decider.py: 'NullRetryQueueManager' への実コード参照が存在しない", "NullRetryQueueManager" in referenced_decider_40)
print()


# ═══════════════════════════════════════════════════════════
# テスト41: 既存回帰（v3.0.0〜v4.3.0 RetryManager挙動）
# ═══════════════════════════════════════════════════════════

print("[テスト41] retry() / decide_retry_queue_updates() / apply_retry_queue_removals() / apply_retry_queue_cleanup()の既存挙動が維持される")

fake_monitor_41 = FakeWorkflowMonitorManager(record=make_record("run-41", WorkflowMonitorStatus.FAILED))
fake_executor_41 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-41", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
))
manager_41 = RetryManager(policy=policy_ok, executor=fake_executor_41, monitor=fake_monitor_41)
result_41 = manager_41.retry("run-41", attempt=1)
check("41. retry()が本Release後も同じ挙動（RETRIED）", result_41.outcome, RetryOutcome.RETRIED)

decisions_41 = manager_41.decide_retry_queue_updates([make_retry_event("run-41d")])
check("41. decide_retry_queue_updates()が本Release後も同じ挙動（COMPLETE）", decisions_41[0].outcome, RetryQueueUpdateOutcome.COMPLETE)

removal_results_41 = manager_41.apply_retry_queue_removals([make_retry_event("run-41r")])
check("41. apply_retry_queue_removals()が本Release後も同じ挙動（attempted=True）", removal_results_41[0].attempted, True)

fake_monitor_41b = FakeWorkflowMonitorManager(record=make_record("run-41b", WorkflowMonitorStatus.FAILED))
fake_executor_41b = FakeRetryExecutor(result=None)
manager_41b = RetryManager(policy=policy_ok, executor=fake_executor_41b, monitor=fake_monitor_41b)
cleanup_results_41 = manager_41b.apply_retry_queue_cleanup([make_retry_event("run-41c", retry_attempt=3)])
check("41. apply_retry_queue_cleanup()が本Release後も同じ挙動（attempted=True、SKIPPED由来）", cleanup_results_41[0].attempted, True)

null_mgr_41 = NullRetryManager()
result_41c = null_mgr_41.enqueue_retry(run_id="run-41e", workflow_name="news")
check_contains_41 = "Retry Engine is disabled" in result_41c.reason
check_true("41. NullRetryManager.enqueue_retry()が本Release後も同じ挙動（DISABLED理由文言）", check_contains_41)
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
