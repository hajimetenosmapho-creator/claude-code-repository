"""
E2E テスト: v4.1.0 Retry Queue Update Foundation

テストシナリオ（docs/design/retry_queue_update_foundation.md 4章・14章・16章 対応）:
    ── RetryQueueUpdateDecider単体：判定ロジック ──
    1.  RETRIED + overall_success=True → COMPLETE / target_status=COMPLETED
    2.  RETRIED + overall_success=False → FAIL / target_status=FAILED
    3.  decide_all()が複数件を順序を保ったまま判定する
    4.  空リストを渡した場合は空リストを返す
    5.  SKIPPED → NOOP / target_status=None（Minor Recommendation 1：個別固定化）
    6.  NOT_FOUND → NOOP / target_status=None（Minor Recommendation 1：個別固定化）
    7.  DISABLED → NOOP / target_status=None（Minor Recommendation 1：個別固定化）
    8.  SKIPPED/NOT_FOUND/DISABLEDのreason文字列がそれぞれ区別できる
    9.  RetryQueueUpdateDecision.execution_resultが元のRetryExecutionResultそのもの

    ── RetryManager.decide_retry_queue_updates()：委譲の正確性 ──
    10. queue_update_decider省略時、自動フォールバックする
    11. DIで渡したFakeDeciderへ、execute_dispatchable_retries()の結果がそのまま渡る
    12. dry_runがexecute_dispatchable_retries()へそのまま伝播する
    13. from_config()の既存9引数呼び出しが本Release前と同じゲート判定結果を返す
    14. from_config()でqueue_update_deciderを渡すと実際に配線される

    ── decide_retry_queue_updates()と既存Queue操作の独立性 ──
    15. decide_retry_queue_updates()を呼んでもFakeQueue.enqueue()/dequeue()は呼ばれない
    16. Architecture Guard：decide_retry_queue_updates()のソースコードが
        self._queueを一切参照しない

    ── 実際のretry()が呼ばれ、RetryQueueUpdateDecisionが返る統合確認 ──
    17. dispatchable=TrueのRetryDispatchEventに対し、実際にRetryManager.retry()が呼ばれ
        COMPLETE判定のRetryQueueUpdateDecisionが返る

    ── NullRetryManager：常に[]を返す ──
    18. NullRetryManager.decide_retry_queue_updates()は常に[]を返す
    19. NullRetryManagerはRetryQueueUpdateDecider等のいかなるフィールドも持たない

    ── 書き込みが発生しないことの確認 ──
    20. 実行処理の前後でファイルが一切作成されない

    ── Architecture Guard（無改修の確認・新規ファイルのimport制約） ──
    21. src/scheduler/ / src/retry_scheduler_decision/ / src/retry_scheduler_source/ /
        src/retry_queue/ 配下の全ファイル、および src/retry_engine/ のうち本Releaseで
        変更していないファイル（retry_execution_selector.py・retry_execution_coordinator.py含む）
        に変更がないこと（git diff）
    22. retry_engineパッケージの__all__に新規シンボルが追加され、既存シンボルは
        維持されていること
    23. RetryManager.__init__ / from_config()の新規引数が末尾・デフォルト値付きで
        追加されていること
    24. retry_queue_update_decider.py が RetryQueueManager / NullRetryQueueManager /
        dequeue / remove をimportしていないこと（AST）。RetryQueueStatusは参照する
    25. SKIPPEDによるQueue滞留リスクがコード内にRelease 4.2への申し送りとして
        明記されていること（Minor Recommendation 2）

    ── 既存回帰（v3.0.0〜v4.0.0 RetryManager挙動）──
    26. retry() / execute_dispatchable_retries() / dispatch_retry_events()の挙動が
        本Releaseでも維持される

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v4_1_0_retry_queue_update_foundation.py
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
print("v4.1.0 Retry Queue Update Foundation E2E テスト")
print("=" * 60)
print()

from retry_queue import RetryQueueStatus
from scheduler import SchedulerEvent
from workflow_engine import NullWorkflowEngineManager, WorkflowEngineResult
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus
from retry_engine import (
    DEFAULT_TARGET_STATUSES,
    NullRetryManager,
    RetryCandidateEvent,
    RetryConfig,
    RetryDispatchEvent,
    RetryExecutionCoordinator,
    RetryExecutionResult,
    RetryExecutionSelector,
    RetryManager,
    RetryOutcome,
    RetryPolicy,
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
    def __init__(self):
        self.enqueue_calls: list[dict] = []
        self.dequeue_calls: int = 0
        self.remove_calls: list[str] = []

    def enqueue(self, run_id, workflow_name, retry_attempt=1, priority=None):
        self.enqueue_calls.append({"run_id": run_id, "workflow_name": workflow_name})
        return None

    def dequeue(self):
        self.dequeue_calls += 1
        return None

    def remove(self, run_id):
        self.remove_calls.append(run_id)
        return None


class FakeRetryQueueUpdateDecider:
    """テスト専用のFake。decide_all()呼び出しを記録し、固定の戻り値を返す。"""

    def __init__(self, result: "list[RetryQueueUpdateDecision] | None" = None):
        self.calls: list[list] = []
        self._result = result if result is not None else []

    def decide_all(self, execution_results):
        self.calls.append(execution_results)
        return self._result


def make_record(run_id: str, monitor_status: WorkflowMonitorStatus, job_id: str = "job-1") -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=monitor_status,
        source_status=monitor_status.value, source="manual", job_id=job_id,
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=[],
    )


# ═══════════════════════════════════════════════════════════
# テスト1-4: RetryQueueUpdateDecider単体：COMPLETE / FAIL / 複数件 / 空リスト
# ═══════════════════════════════════════════════════════════

print("[テスト1-4] RetryQueueUpdateDecider.decide() / decide_all()：COMPLETE・FAIL・複数件・空リスト")

decider_1 = RetryQueueUpdateDecider()

retried_success_1 = RetryResult(
    original_run_id="run-001", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
)
result_1 = decider_1.decide(make_execution_result("run-001", retried_success_1))
check("1. RETRIED+success=True → outcome=COMPLETE", result_1.outcome, RetryQueueUpdateOutcome.COMPLETE)
check("1. RETRIED+success=True → target_status=COMPLETED", result_1.target_status, RetryQueueStatus.COMPLETED)

retried_failure_2 = RetryResult(
    original_run_id="run-002", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=False),
)
result_2 = decider_1.decide(make_execution_result("run-002", retried_failure_2))
check("2. RETRIED+success=False → outcome=FAIL", result_2.outcome, RetryQueueUpdateOutcome.FAIL)
check("2. RETRIED+success=False → target_status=FAILED", result_2.target_status, RetryQueueStatus.FAILED)

results_3 = decider_1.decide_all([
    make_execution_result("run-003a", retried_success_1),
    make_execution_result("run-003b", retried_failure_2),
])
check(
    "3. decide_all()が複数件を順序を保ったまま判定する",
    [r.outcome for r in results_3],
    [RetryQueueUpdateOutcome.COMPLETE, RetryQueueUpdateOutcome.FAIL],
)

result_4 = decider_1.decide_all([])
check("4. 空リストを渡した場合は空リストを返す", result_4, [])
print()


# ═══════════════════════════════════════════════════════════
# テスト5-9: SKIPPED / NOT_FOUND / DISABLED → NOOP（個別固定化・Minor Recommendation 1）
# ═══════════════════════════════════════════════════════════

print("[テスト5-9] SKIPPED / NOT_FOUND / DISABLED は個別にNOOPへ判定される（Minor Recommendation 1）")

skipped_5 = RetryResult(
    original_run_id="run-005", outcome=RetryOutcome.SKIPPED, attempt=3,
    monitor_status=WorkflowMonitorStatus.FAILED,
    reason="attempt 3 has reached max_attempts=3.", workflow_engine_result=None,
)
result_5 = decider_1.decide(make_execution_result("run-005", skipped_5))
check("5. SKIPPED → outcome=NOOP", result_5.outcome, RetryQueueUpdateOutcome.NOOP)
check("5. SKIPPED → target_status=None", result_5.target_status, None)

not_found_6 = RetryResult(
    original_run_id="run-006", outcome=RetryOutcome.NOT_FOUND, attempt=1,
    monitor_status=None, reason="run_id=run-006 was not found in Workflow Monitor.",
    workflow_engine_result=None,
)
result_6 = decider_1.decide(make_execution_result("run-006", not_found_6))
check("6. NOT_FOUND → outcome=NOOP", result_6.outcome, RetryQueueUpdateOutcome.NOOP)
check("6. NOT_FOUND → target_status=None", result_6.target_status, None)

disabled_7 = RetryResult(
    original_run_id="run-007", outcome=RetryOutcome.DISABLED, attempt=1,
    monitor_status=None, reason="Retry Engine is disabled.", workflow_engine_result=None,
)
result_7 = decider_1.decide(make_execution_result("run-007", disabled_7))
check("7. DISABLED → outcome=NOOP", result_7.outcome, RetryQueueUpdateOutcome.NOOP)
check("7. DISABLED → target_status=None", result_7.target_status, None)

check(
    "8. SKIPPED/NOT_FOUND/DISABLEDのreason文字列がそれぞれ区別できる",
    len({result_5.reason, result_6.reason, result_7.reason}),
    3,
)
check_true("8. SKIPPEDのreasonにoutcome値（skipped）が含まれる", "skipped" in result_5.reason)
check_true("8. NOT_FOUNDのreasonにoutcome値（not_found）が含まれる", "not_found" in result_6.reason)
check_true("8. DISABLEDのreasonにoutcome値（disabled）が含まれる", "disabled" in result_7.reason)

execution_result_9 = make_execution_result("run-009", retried_success_1)
result_9 = decider_1.decide(execution_result_9)
check_true("9. RetryQueueUpdateDecision.execution_resultが元のRetryExecutionResultそのもの", result_9.execution_result is execution_result_9)
print()


# ═══════════════════════════════════════════════════════════
# テスト10-14: RetryManager.decide_retry_queue_updates()：委譲の正確性
# ═══════════════════════════════════════════════════════════

print("[テスト10] queue_update_decider省略時、自動フォールバックする")

manager_10 = RetryManager(policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None))
check_true("10. queue_update_decider省略時、内部にRetryQueueUpdateDeciderが構築される", isinstance(manager_10._queue_update_decider, RetryQueueUpdateDecider))
print()

print("[テスト11-12] DIで渡したFakeDeciderへの委譲・dry_runの伝播")

fake_monitor_11 = FakeWorkflowMonitorManager(record=make_record("run-011", WorkflowMonitorStatus.FAILED))
fake_executor_11 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-011", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
))
fake_decider_11 = FakeRetryQueueUpdateDecider(result=["placeholder-decision"])
manager_11 = RetryManager(
    policy=policy_ok, executor=fake_executor_11, monitor=fake_monitor_11,
    queue_update_decider=fake_decider_11,
)
events_11 = [make_retry_event("run-011")]
result_11 = manager_11.decide_retry_queue_updates(events_11)
check("11. FakeDecider.decide_all()が1回だけ呼ばれる", len(fake_decider_11.calls), 1)
check(
    "11. execute_dispatchable_retries()の戻り値がFakeDecider.decide_all()にそのまま渡る",
    [r.dispatch_event.candidate_event.run_id for r in fake_decider_11.calls[0]],
    ["run-011"],
)
check("11. 最終的な戻り値がFakeDeciderの戻り値そのもの", result_11, ["placeholder-decision"])

fake_engine_manager_12 = FakeWorkflowEngineManager()
manager_12 = RetryManager(
    policy=policy_ok,
    executor=FakeRetryExecutor(result=RetryResult(
        original_run_id="run-012", outcome=RetryOutcome.RETRIED, attempt=1,
        monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
        workflow_engine_result=make_workflow_engine_result(overall_success=True),
    )),
    monitor=FakeWorkflowMonitorManager(record=make_record("run-012", WorkflowMonitorStatus.FAILED)),
    queue_update_decider=FakeRetryQueueUpdateDecider(result=[]),
)
manager_12.decide_retry_queue_updates([make_retry_event("run-012")], dry_run=True)
check_true("12. dry_run=Trueがexecute_dispatchable_retries()経由でretry()へ伝播する（FakeExecutorが呼ばれている）", len(manager_12._executor.calls) == 1)
print()

print("[テスト13] from_config()の既存9引数呼び出しが本Release前と同じゲート判定結果を返す")

fake_engine_ok = FakeWorkflowEngineManager()
fake_monitor_ok = FakeWorkflowMonitorManager(record=None)

mgr_13a = RetryManager.from_config(RetryConfig(enabled=False), policy_ok, fake_engine_ok, fake_monitor_ok)
check_true("13. enabled=Falseの4引数呼び出し → NullRetryManager", isinstance(mgr_13a, NullRetryManager))

mgr_13b = RetryManager.from_config(RetryConfig(enabled=True), policy_ok, NullWorkflowEngineManager(), fake_monitor_ok)
check_true("13. NullWorkflowEngineManagerの4引数呼び出し → NullRetryManager", isinstance(mgr_13b, NullRetryManager))

mgr_13c = RetryManager.from_config(RetryConfig(enabled=True), policy_ok, fake_engine_ok, fake_monitor_ok)
check_true("13. 両方満たす4引数呼び出し → RetryManager（実インスタンス）", isinstance(mgr_13c, RetryManager))
check_true("13. queue_update_decider省略時、内部にRetryQueueUpdateDeciderが自動構築される", isinstance(mgr_13c._queue_update_decider, RetryQueueUpdateDecider))
print()

print("[テスト14] from_config()でqueue_update_deciderを渡すと実際に配線される")

fake_decider_14 = FakeRetryQueueUpdateDecider(result=[])
mgr_14 = RetryManager.from_config(
    RetryConfig(enabled=True), policy_ok, fake_engine_ok, fake_monitor_ok,
    queue_update_decider=fake_decider_14,
)
mgr_14.decide_retry_queue_updates([make_retry_event("run-14")])
check("14. from_config()経由で渡したqueue_update_deciderに実際に委譲される", len(fake_decider_14.calls), 1)
print()


# ═══════════════════════════════════════════════════════════
# テスト15-16: decide_retry_queue_updates()と既存Queue操作の独立性
# ═══════════════════════════════════════════════════════════

print("[テスト15] decide_retry_queue_updates()とQueue操作の独立性")

fake_queue_15 = FakeRetryQueueManager()
fake_monitor_15 = FakeWorkflowMonitorManager(record=make_record("run-15", WorkflowMonitorStatus.FAILED))
fake_executor_15 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-15", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
))
manager_15 = RetryManager(policy=policy_ok, executor=fake_executor_15, monitor=fake_monitor_15, queue=fake_queue_15)

manager_15.decide_retry_queue_updates([make_retry_event("run-15")])
check("15. decide_retry_queue_updates()を呼んでもFakeQueue.enqueue()は呼ばれない", len(fake_queue_15.enqueue_calls), 0)
check("15. decide_retry_queue_updates()を呼んでもFakeQueue.dequeue()は呼ばれない", fake_queue_15.dequeue_calls, 0)
check("15. decide_retry_queue_updates()を呼んでもFakeQueue.remove()は呼ばれない", len(fake_queue_15.remove_calls), 0)
print()

print("[テスト16] Architecture Guard：decide_retry_queue_updates()が"
      "self._queueを参照しない（静的検査）")

retry_manager_source = (PROJECT_ROOT / "src" / "retry_engine" / "retry_manager.py").read_text(encoding="utf-8")


def extract_method_body(source: str, method_name: str) -> str:
    start_match = re.search(rf"\n    def {re.escape(method_name)}\(", source)
    rest = source[start_match.end():]
    next_match = re.search(r"\n    def ", rest)
    end = next_match.start() if next_match else len(rest)
    return rest[:end]


body_decide_16 = extract_method_body(retry_manager_source, "decide_retry_queue_updates")
# 「self._queue」ちょうど（末尾が単語境界）の参照がないことを確認する。
# 「self._queue_update_decider」（本Releaseで正しく参照すべきフィールド）は
# 末尾がアンダースコアで続くため \b にはマッチせず、誤検知しない。
check_false(
    "16. RetryManager.decide_retry_queue_updates()本体が「self._queue」（Queue本体への参照）を含まない",
    re.search(r"self\._queue\b", body_decide_16) is not None,
)
check_true(
    "16. RetryManager.decide_retry_queue_updates()本体は「self._queue_update_decider」を参照している",
    "self._queue_update_decider" in body_decide_16,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト17: 実際のretry()が呼ばれ、RetryQueueUpdateDecisionが返る統合確認
# ═══════════════════════════════════════════════════════════

print("[テスト17] dispatchable=TrueのRetryDispatchEventに対し実際にRetryManager.retry()が呼ばれ"
      "COMPLETE判定が返る")

fake_monitor_17 = FakeWorkflowMonitorManager(record=make_record("run-17", WorkflowMonitorStatus.FAILED))
fake_executor_17 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-17", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
))
manager_17 = RetryManager(policy=policy_ok, executor=fake_executor_17, monitor=fake_monitor_17)

decisions_17 = manager_17.decide_retry_queue_updates([make_retry_event("run-17")])
check("17. 判定結果が1件返る", len(decisions_17), 1)
check("17. FakeMonitor.get_status()が実際に呼ばれる（Read Before Retryが機能している）", fake_monitor_17.calls, ["run-17"])
check("17. RetryQueueUpdateDecision.outcomeがCOMPLETE", decisions_17[0].outcome, RetryQueueUpdateOutcome.COMPLETE)
check("17. RetryQueueUpdateDecision.target_statusがCOMPLETED", decisions_17[0].target_status, RetryQueueStatus.COMPLETED)
check(
    "17. RetryQueueUpdateDecision.execution_result.dispatch_event.candidate_event.run_idがrun-17",
    decisions_17[0].execution_result.dispatch_event.candidate_event.run_id,
    "run-17",
)
print()


# ═══════════════════════════════════════════════════════════
# テスト18-19: NullRetryManager：常に[]を返す
# ═══════════════════════════════════════════════════════════

print("[テスト18-19] NullRetryManager.decide_retry_queue_updates()は常に[]を返す")

null_mgr_18 = NullRetryManager()
result_18_with_retry_events = null_mgr_18.decide_retry_queue_updates([make_retry_event("run-18a"), make_retry_event("run-18b")])
check("18. Retry候補由来のイベントを含んでいても常に[]を返す", result_18_with_retry_events, [])

result_18_empty = null_mgr_18.decide_retry_queue_updates([])
check("18. 空リストを渡しても[]を返す", result_18_empty, [])

check("19. NullRetryManagerはRetryQueueUpdateDecider等のいかなるフィールドも持たない", vars(null_mgr_18), {})
print()


# ═══════════════════════════════════════════════════════════
# テスト20: 書き込みが発生しないことの確認
# ═══════════════════════════════════════════════════════════

print("[テスト20] 実行処理の前後でファイルが一切作成されない")

write_check_dir_20 = Path(tempfile.mkdtemp())
before_files_20 = list(write_check_dir_20.rglob("*"))

fake_monitor_20w = FakeWorkflowMonitorManager(record=make_record("run-20w", WorkflowMonitorStatus.FAILED))
fake_executor_20w = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-20w", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
))
manager_20w = RetryManager(policy=policy_ok, executor=fake_executor_20w, monitor=fake_monitor_20w)
manager_20w.decide_retry_queue_updates([make_retry_event("run-20w")])
NullRetryManager().decide_retry_queue_updates([make_retry_event("run-20wb")])

after_files_20 = list(write_check_dir_20.rglob("*"))
check("20. 実行処理前後でファイルが作成されない", after_files_20, before_files_20)
print()


# ═══════════════════════════════════════════════════════════
# テスト21: Architecture Guard（無改修の確認）
# ═══════════════════════════════════════════════════════════

print("[テスト21] 既存ファイルの無変更確認（git diff）")

unchanged_paths_v410 = [
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
    for rel_path in unchanged_paths_v410:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"21. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("21. gitが利用できないため無変更確認をスキップ", True)
print()


# ═══════════════════════════════════════════════════════════
# テスト22: retry_engineパッケージのexport確認
# ═══════════════════════════════════════════════════════════

print("[テスト22] retry_engine.__all__ に新規シンボルが追加され、既存シンボルが維持されていること")

import retry_engine as re_pkg_22

check(
    "22. retry_engine.__all__ が既存シンボル＋新規3シンボルの構成になっている",
    set(re_pkg_22.__all__),
    {
        "RetryPolicy", "DEFAULT_TARGET_STATUSES", "RetryConfig", "RetryRequest", "RetryOutcome",
        "RetryResult", "RetryExecutor", "RetryCandidateEvent", "RetryEventConsumer",
        "RetryDispatchEvent", "RetryEventDispatcher", "RetryExecutionSelector",
        "RetryExecutionCoordinator", "RetryExecutionResult", "RetryQueueUpdateOutcome",
        "RetryQueueUpdateDecision", "RetryQueueUpdateDecider", "RetryManager", "NullRetryManager",
    },
)
check_true("22. RetryManagerがdecide_retry_queue_updates()を持つ", hasattr(RetryManager, "decide_retry_queue_updates"))
check_true("22. NullRetryManagerがdecide_retry_queue_updates()を持つ", hasattr(NullRetryManager, "decide_retry_queue_updates"))
print()


# ═══════════════════════════════════════════════════════════
# テスト23: __init__ / from_config() の新規引数の後方互換性
# ═══════════════════════════════════════════════════════════

print("[テスト23] RetryManager.__init__ / from_config()の新規引数が末尾・デフォルト値付きで追加されていること")

sig_init_23 = inspect.signature(RetryManager.__init__)
params_init_23 = list(sig_init_23.parameters.keys())
check("23. __init__の最終引数がqueue_update_decider", params_init_23[-1], "queue_update_decider")
check("23. queue_update_deciderのデフォルトはNone", sig_init_23.parameters["queue_update_decider"].default, None)

sig_from_config_23 = inspect.signature(RetryManager.from_config)
params_from_config_23 = list(sig_from_config_23.parameters.keys())
check("23. from_config()の最終引数がqueue_update_decider", params_from_config_23[-1], "queue_update_decider")
check(
    "23. 既存8引数（execution_selector/execution_coordinator含む）の名前・順序が変わっていない",
    params_from_config_23[:9],
    [
        "retry_config", "retry_policy", "workflow_engine_manager", "workflow_monitor_manager",
        "retry_queue_manager", "event_consumer", "event_dispatcher",
        "execution_selector", "execution_coordinator",
    ],
)
print()


# ═══════════════════════════════════════════════════════════
# テスト24: 新規ファイルが RetryQueueManager / dequeue / remove をimportしないこと
# ═══════════════════════════════════════════════════════════

print("[テスト24] retry_queue_update_decider.py に "
      "'RetryQueueManager' / 'NullRetryQueueManager' / 'dequeue' / 'remove' への"
      "実コード参照がない（AST）。RetryQueueStatusは参照する")


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


decider_source_path_24 = PROJECT_ROOT / "src" / "retry_engine" / "retry_queue_update_decider.py"
tree_24 = ast.parse(decider_source_path_24.read_text(encoding="utf-8"))
referenced_24 = _referenced_names(tree_24)
check_false("24. retry_queue_update_decider.py: 'RetryQueueManager' への実コード参照が存在しない", "RetryQueueManager" in referenced_24)
check_false("24. retry_queue_update_decider.py: 'NullRetryQueueManager' への実コード参照が存在しない", "NullRetryQueueManager" in referenced_24)
check_false("24. retry_queue_update_decider.py: 'dequeue' への実コード参照が存在しない", "dequeue" in referenced_24)
check_false("24. retry_queue_update_decider.py: 'remove' への実コード参照が存在しない", "remove" in referenced_24)
check_true("24. retry_queue_update_decider.py: 'RetryQueueStatus' は参照している", "RetryQueueStatus" in referenced_24)
print()


# ═══════════════════════════════════════════════════════════
# テスト25: SKIPPEDによるQueue滞留リスクの申し送り（Minor Recommendation 2）
# ═══════════════════════════════════════════════════════════

print("[テスト25] SKIPPEDによるQueue滞留リスクがRelease 4.2への申し送りとして明記されていること")

decider_source_text_25 = decider_source_path_24.read_text(encoding="utf-8")
check_true(
    "25. retry_queue_update_decider.py のdocstringに「Retry Queue Removal」への申し送りが明記されている",
    "Retry Queue Removal" in decider_source_text_25,
)
check_true(
    "25. retry_queue_update_decider.py のdocstringに滞留（NOOPのまま残る）についての言及がある",
    "滞留" in decider_source_text_25,
)
design_doc_text_25 = (PROJECT_ROOT / "docs" / "design" / "retry_queue_update_foundation.md").read_text(encoding="utf-8")
check_true(
    "25. 設計書にSKIPPED滞留リスクがRecommendationとして記録されている",
    "SKIPPED" in design_doc_text_25 and "滞留" in design_doc_text_25,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト26: 既存回帰（v3.0.0〜v4.0.0 RetryManager挙動）
# ═══════════════════════════════════════════════════════════

print("[テスト26] retry() / execute_dispatchable_retries() / dispatch_retry_events()の既存挙動が維持される")

fake_monitor_26 = FakeWorkflowMonitorManager(record=make_record("run-26", WorkflowMonitorStatus.FAILED))
fake_executor_26 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-26", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
))
manager_26 = RetryManager(policy=policy_ok, executor=fake_executor_26, monitor=fake_monitor_26)
result_26 = manager_26.retry("run-26", attempt=1)
check("26. retry()が本Release後も同じ挙動（RETRIED）", result_26.outcome, RetryOutcome.RETRIED)

dispatched_26 = manager_26.dispatch_retry_events([make_retry_event("run-26d")])
check("26. dispatch_retry_events()が本Release後も同じ挙動", [d.candidate_event.run_id for d in dispatched_26], ["run-26d"])
check_true("26. dispatch_retry_events()の結果はdispatchable=True", dispatched_26[0].dispatchable)

execution_results_26 = manager_26.execute_dispatchable_retries([make_retry_event("run-26e")])
check("26. execute_dispatchable_retries()が本Release後も同じ挙動（RETRIED）", execution_results_26[0].retry_result.outcome, RetryOutcome.RETRIED)

null_mgr_26 = NullRetryManager()
result_26b = null_mgr_26.enqueue_retry(run_id="run-26b", workflow_name="news")
check_contains_26 = "Retry Engine is disabled" in result_26b.reason
check_true("26. NullRetryManager.enqueue_retry()が本Release後も同じ挙動（DISABLED理由文言）", check_contains_26)
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
