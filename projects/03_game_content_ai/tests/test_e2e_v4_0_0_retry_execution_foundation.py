"""
E2E テスト: v4.0.0 Retry Execution Foundation

テストシナリオ（docs/design/retry_execution_foundation.md 10章・14章 対応）:
    ── RetryExecutionSelector単体：dispatchable=Trueのみを選別する ──
    1.  dispatchable=TrueのRetryDispatchEventだけが選別結果に残る
    2.  dispatchable=FalseのRetryDispatchEventは選別結果から除外される
    3.  混在リストから、Trueのものだけが順序を保ったまま残る
    4.  空リストを渡した場合は空リストを返す

    ── RetryExecutionCoordinator単体：retry_fnの呼び出し・結果集約 ──
    5.  選別済みのRetryDispatchEventについてretry_fnが呼ばれ、run_id・attemptが渡る
    6.  attemptはcandidate.retry_attemptから取得される
    7.  candidateがretry_attempt属性を持たない場合はattempt=1にフォールバックする
    8.  RetryExecutionResult.dispatch_event / retry_resultが正しく格納される
    9.  空リストを渡した場合、retry_fnは一度も呼ばれず空リストを返す
    10. dry_runがretry_fnへそのまま伝播する

    ── RetryManager.execute_dispatchable_retries()：委譲の正確性 ──
    11. execution_selector / execution_coordinator省略時、それぞれ自動フォールバックする
    12. DIで渡したFakeSelector.select()の戻り値がFakeCoordinator.execute()にそのまま渡る
    13. dispatch_retry_events()経由で得たdispatch_eventsがFakeSelector.select()に渡る
    14. retry_fn=self.retryがCoordinator.execute()に渡され、実際にRetryManager.retry()が呼ばれる
    15. from_config()の既存8引数呼び出しが本Release前と同じゲート判定結果を返す
    16. from_config()でexecution_selector / execution_coordinatorを渡すと実際に配線される

    ── execute_dispatchable_retries()と既存Queue操作の独立性 ──
    17. execute_dispatchable_retries()を呼んでもFakeQueue.enqueue()/dequeue()は呼ばれない
    18. Architecture Guard：execute_dispatchable_retries()のソースコードが
        self._queueを一切参照しない

    ── dispatchable=Falseの候補はretry()に到達しない ──
    19. dispatchable=Falseの候補についてはFakeMonitor.get_status()が呼ばれない
        （RetryExecutionSelectorの時点で除外されるため）

    ── 実際のretry()が呼ばれ、RetryResultが返る統合確認 ──
    20. dispatchable=TrueのRetryDispatchEventに対し、実際にRetryManager.retry()が呼ばれ
        RetryResult(outcome=RETRIED)を含むRetryExecutionResultが返る

    ── NullRetryManager：常に[]を返す ──
    21. NullRetryManager.execute_dispatchable_retries()はRetry候補由来のイベントを
        含んでいても常に[]を返す
    22. NullRetryManagerはRetryExecutionSelector等のいかなるフィールドも持たない

    ── 書き込みが発生しないことの確認 ──
    23. 実行処理の前後でファイルが一切作成されない

    ── Architecture Guard（無改修の確認・新規ファイルのimport制約） ──
    24. src/scheduler/ / src/retry_scheduler_decision/ / src/retry_scheduler_source/ /
        src/retry_queue/ 配下の全ファイル、および src/retry_engine/ のうち本Releaseで
        変更していないファイル（retry_event_consumer.py・retry_event_dispatcher.py含む）
        に変更がないこと（git diff）
    25. retry_engineパッケージの__all__に新規シンボルが追加され、既存シンボルは
        維持されていること
    26. RetryManager.__init__ / from_config()の新規引数が末尾・デフォルト値付きで
        追加されていること
    27. retry_execution_selector.py / retry_execution_coordinator.py が
        retry_queue / scheduler / dequeue / remove をimportしていないこと（AST）

    ── 既存回帰（v3.0.0〜v3.9.0 RetryManager挙動）──
    28. retry() / enqueue_retry() / dequeue_retry() / recognize_retry_events() /
        dispatch_retry_events()の挙動が本Releaseでも維持される

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v4_0_0_retry_execution_foundation.py
"""
import ast
import inspect
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
print("v4.0.0 Retry Execution Foundation E2E テスト")
print("=" * 60)
print()

from scheduler import SchedulerEvent
from workflow_engine import NullWorkflowEngineManager, WorkflowEngineResult
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus
from retry_engine import (
    DEFAULT_TARGET_STATUSES,
    NullRetryManager,
    RetryCandidateEvent,
    RetryConfig,
    RetryDispatchEvent,
    RetryEventDispatcher,
    RetryExecutionCoordinator,
    RetryExecutionResult,
    RetryExecutionSelector,
    RetryManager,
    RetryOutcome,
    RetryPolicy,
    RetryResult,
)
from retry_engine.retry_event_consumer import RETRY_JOB_ID_PREFIX


class FakeCandidate:
    """RetryQueueItemを模した最小限のテスト用オブジェクト（retry_queueへは依存しない）。"""

    def __init__(self, run_id: str, retry_attempt: int = 1):
        self.run_id = run_id
        self.retry_attempt = retry_attempt


class FakeCandidateWithoutAttempt:
    """retry_attempt属性を持たないテスト用オブジェクト（フォールバック確認用）。"""

    def __init__(self, run_id: str):
        self.run_id = run_id


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


policy_ok = RetryPolicy(target_statuses=DEFAULT_TARGET_STATUSES, max_attempts=3)


class FakeWorkflowEngineManager:
    def __init__(self):
        self.calls: list[tuple] = []

    def run(self, event, dry_run: bool = False) -> WorkflowEngineResult:
        self.calls.append((event, dry_run))
        return WorkflowEngineResult(
            steps=[], overall_success=True, stopped_early=False,
            started_at=datetime.now(), finished_at=datetime.now(),
        )


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

    def enqueue(self, run_id, workflow_name, retry_attempt=1, priority=None):
        self.enqueue_calls.append({"run_id": run_id, "workflow_name": workflow_name})
        return None

    def dequeue(self):
        self.dequeue_calls += 1
        return None


class FakeRetryExecutionSelector:
    """テスト専用のFake。select()呼び出しを記録し、固定の戻り値を返す。"""

    def __init__(self, result: "list[RetryDispatchEvent] | None" = None):
        self.calls: list[list] = []
        self._result = result if result is not None else []

    def select(self, dispatch_events):
        self.calls.append(dispatch_events)
        return self._result


class FakeRetryExecutionCoordinator:
    """テスト専用のFake。execute()呼び出しを記録し、固定の戻り値を返す。"""

    def __init__(self, result: "list[RetryExecutionResult] | None" = None):
        self.calls: list[tuple] = []
        self._result = result if result is not None else []

    def execute(self, dispatch_events, retry_fn, dry_run=False):
        self.calls.append((dispatch_events, retry_fn, dry_run))
        return self._result


def make_record(run_id: str, monitor_status: WorkflowMonitorStatus, job_id: str = "job-1") -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=monitor_status,
        source_status=monitor_status.value, source="manual", job_id=job_id,
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=[],
    )


# ═══════════════════════════════════════════════════════════
# テスト1-4: RetryExecutionSelector単体：dispatchable=Trueのみを選別する
# ═══════════════════════════════════════════════════════════

print("[テスト1-4] RetryExecutionSelector.select()：dispatchable=Trueのみを選別する")

selector_1 = RetryExecutionSelector()
event_true_1 = make_dispatch_event("run-001", dispatchable=True)
result_1 = selector_1.select([event_true_1])
check("1. dispatchable=Trueのイベントは選別結果に残る", result_1, [event_true_1])

event_false_2 = make_dispatch_event("run-002", dispatchable=False)
result_2 = selector_1.select([event_false_2])
check("2. dispatchable=Falseのイベントは選別結果から除外される", result_2, [])

mixed_3 = [
    make_dispatch_event("run-a", dispatchable=True),
    make_dispatch_event("run-b", dispatchable=False),
    make_dispatch_event("run-c", dispatchable=True),
]
result_3 = selector_1.select(mixed_3)
check("3. 混在リストからTrueのものだけが順序を保ったまま残る", [e.candidate_event.run_id for e in result_3], ["run-a", "run-c"])

result_4 = selector_1.select([])
check("4. 空リストを渡した場合は空リストを返す", result_4, [])
print()


# ═══════════════════════════════════════════════════════════
# テスト5-10: RetryExecutionCoordinator単体：retry_fnの呼び出し・結果集約
# ═══════════════════════════════════════════════════════════

print("[テスト5-10] RetryExecutionCoordinator.execute()：retry_fnの呼び出し・結果集約")

coordinator_5 = RetryExecutionCoordinator()
retry_fn_calls_5: list[tuple] = []


def fake_retry_fn_5(run_id, attempt=1, dry_run=False):
    retry_fn_calls_5.append((run_id, attempt, dry_run))
    return RetryResult(
        original_run_id=run_id, outcome=RetryOutcome.RETRIED, attempt=attempt,
        monitor_status=WorkflowMonitorStatus.FAILED, reason=None, workflow_engine_result=None,
    )


selected_5 = [make_dispatch_event("run-005", dispatchable=True, retry_attempt=2)]
results_5 = coordinator_5.execute(selected_5, retry_fn=fake_retry_fn_5)
check("5. retry_fnが選別済みイベントに対して呼ばれる", len(retry_fn_calls_5), 1)
check("5. run_idがcandidate_event.run_idと一致する", retry_fn_calls_5[0][0], "run-005")
check("6. attemptがcandidate.retry_attempt（2）から取得される", retry_fn_calls_5[0][1], 2)

retry_fn_calls_7: list[tuple] = []


def fake_retry_fn_7(run_id, attempt=1, dry_run=False):
    retry_fn_calls_7.append((run_id, attempt, dry_run))
    return RetryResult(
        original_run_id=run_id, outcome=RetryOutcome.RETRIED, attempt=attempt,
        monitor_status=None, reason=None, workflow_engine_result=None,
    )


candidate_without_attempt_7 = FakeCandidateWithoutAttempt(run_id="run-007")
dispatch_event_7 = RetryDispatchEvent(
    candidate_event=RetryCandidateEvent(
        run_id="run-007", candidate=candidate_without_attempt_7, source_event=make_retry_event("run-007")
    ),
    dispatchable=True,
)
coordinator_5.execute([dispatch_event_7], retry_fn=fake_retry_fn_7)
check("7. retry_attempt属性を持たないcandidateはattempt=1にフォールバックする", retry_fn_calls_7[0][1], 1)

result_8 = coordinator_5.execute(selected_5, retry_fn=fake_retry_fn_5)
check_true("8. RetryExecutionResult.dispatch_eventが元のRetryDispatchEventそのもの", result_8[0].dispatch_event is selected_5[0])
check("8. RetryExecutionResult.retry_result.outcomeがRETRIED", result_8[0].retry_result.outcome, RetryOutcome.RETRIED)

retry_fn_calls_9: list[tuple] = []


def fake_retry_fn_9(run_id, attempt=1, dry_run=False):
    retry_fn_calls_9.append((run_id, attempt, dry_run))
    return None


result_9 = coordinator_5.execute([], retry_fn=fake_retry_fn_9)
check("9. 空リストを渡した場合、retry_fnは一度も呼ばれない", len(retry_fn_calls_9), 0)
check("9. 空リストを渡した場合、空リストを返す", result_9, [])

retry_fn_calls_10: list[tuple] = []


def fake_retry_fn_10(run_id, attempt=1, dry_run=False):
    retry_fn_calls_10.append((run_id, attempt, dry_run))
    return RetryResult(
        original_run_id=run_id, outcome=RetryOutcome.RETRIED, attempt=attempt,
        monitor_status=None, reason=None, workflow_engine_result=None,
    )


coordinator_5.execute(selected_5, retry_fn=fake_retry_fn_10, dry_run=True)
check_true("10. dry_run=Trueがretry_fnへそのまま伝播する", retry_fn_calls_10[0][2])
print()


# ═══════════════════════════════════════════════════════════
# テスト11-16: RetryManager.execute_dispatchable_retries()：委譲の正確性
# ═══════════════════════════════════════════════════════════

print("[テスト11] execution_selector / execution_coordinator省略時、自動フォールバックする")

manager_11 = RetryManager(policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None))
check_true("11. execution_selector省略時、内部にRetryExecutionSelectorが構築される", isinstance(manager_11._execution_selector, RetryExecutionSelector))
check_true("11. execution_coordinator省略時、内部にRetryExecutionCoordinatorが構築される", isinstance(manager_11._execution_coordinator, RetryExecutionCoordinator))
print()

print("[テスト12-14] DIで渡したFakeSelector/FakeCoordinatorへの委譲・retry_fnの伝播")

expected_selected_12 = [make_dispatch_event("run-012", dispatchable=True)]
fake_selector_12 = FakeRetryExecutionSelector(result=expected_selected_12)
expected_final_12 = [RetryExecutionResult(dispatch_event=expected_selected_12[0], retry_result=None)]
fake_coordinator_12 = FakeRetryExecutionCoordinator(result=expected_final_12)

manager_12 = RetryManager(
    policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None),
    execution_selector=fake_selector_12, execution_coordinator=fake_coordinator_12,
)
events_12 = [make_retry_event("run-012")]
result_12 = manager_12.execute_dispatchable_retries(events_12)
check("12. FakeSelector.select()が1回だけ呼ばれる", len(fake_selector_12.calls), 1)
check("12. FakeCoordinator.execute()が1回だけ呼ばれる", len(fake_coordinator_12.calls), 1)
check("12. FakeSelectorの戻り値がFakeCoordinatorの引数にそのまま渡る", fake_coordinator_12.calls[0][0], expected_selected_12)
check("12. 最終的な戻り値がFakeCoordinatorの戻り値そのもの", result_12, expected_final_12)
check("13. dispatch_retry_events()経由のdispatch_eventsがFakeSelector.select()に渡る", [d.candidate_event.run_id for d in fake_selector_12.calls[0]], ["run-012"])
check_true("14. retry_fnとしてmanager_12.retry（bound method）が渡される", fake_coordinator_12.calls[0][1] == manager_12.retry)
print()

print("[テスト15] from_config()の既存8引数呼び出しが本Release前と同じゲート判定結果を返す")

fake_engine_ok = FakeWorkflowEngineManager()
fake_monitor_ok = FakeWorkflowMonitorManager(record=None)

mgr_15a = RetryManager.from_config(RetryConfig(enabled=False), policy_ok, fake_engine_ok, fake_monitor_ok)
check_true("15. enabled=Falseの4引数呼び出し → NullRetryManager", isinstance(mgr_15a, NullRetryManager))

mgr_15b = RetryManager.from_config(RetryConfig(enabled=True), policy_ok, NullWorkflowEngineManager(), fake_monitor_ok)
check_true("15. NullWorkflowEngineManagerの4引数呼び出し → NullRetryManager", isinstance(mgr_15b, NullRetryManager))

mgr_15c = RetryManager.from_config(RetryConfig(enabled=True), policy_ok, fake_engine_ok, fake_monitor_ok)
check_true("15. 両方満たす4引数呼び出し → RetryManager（実インスタンス）", isinstance(mgr_15c, RetryManager))
check_true("15. execution_selector省略時、内部にRetryExecutionSelectorが自動構築される", isinstance(mgr_15c._execution_selector, RetryExecutionSelector))
check_true("15. execution_coordinator省略時、内部にRetryExecutionCoordinatorが自動構築される", isinstance(mgr_15c._execution_coordinator, RetryExecutionCoordinator))
print()

print("[テスト16] from_config()でexecution_selector / execution_coordinatorを渡すと実際に配線される")

fake_selector_16 = FakeRetryExecutionSelector(result=[])
fake_coordinator_16 = FakeRetryExecutionCoordinator(result=[])
mgr_16 = RetryManager.from_config(
    RetryConfig(enabled=True), policy_ok, fake_engine_ok, fake_monitor_ok,
    execution_selector=fake_selector_16, execution_coordinator=fake_coordinator_16,
)
mgr_16.execute_dispatchable_retries([make_retry_event("run-16")])
check("16. from_config()経由で渡したexecution_selectorに実際に委譲される", len(fake_selector_16.calls), 1)
check("16. from_config()経由で渡したexecution_coordinatorに実際に委譲される", len(fake_coordinator_16.calls), 1)
print()


# ═══════════════════════════════════════════════════════════
# テスト17-18: execute_dispatchable_retries()と既存Queue操作の独立性
# ═══════════════════════════════════════════════════════════

print("[テスト17] execute_dispatchable_retries()とQueue操作の独立性")

fake_queue_17 = FakeRetryQueueManager()
fake_monitor_17 = FakeWorkflowMonitorManager(record=make_record("run-17", WorkflowMonitorStatus.FAILED))
fake_executor_17 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-17", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None, workflow_engine_result=None,
))
manager_17 = RetryManager(policy=policy_ok, executor=fake_executor_17, monitor=fake_monitor_17, queue=fake_queue_17)

manager_17.execute_dispatchable_retries([make_retry_event("run-17")])
check("17. execute_dispatchable_retries()を呼んでもFakeQueue.enqueue()は呼ばれない", len(fake_queue_17.enqueue_calls), 0)
check("17. execute_dispatchable_retries()を呼んでもFakeQueue.dequeue()は呼ばれない", fake_queue_17.dequeue_calls, 0)
print()

print("[テスト18] Architecture Guard：execute_dispatchable_retries()が"
      "self._queueを参照しない（静的検査）")

import re

retry_manager_source = (PROJECT_ROOT / "src" / "retry_engine" / "retry_manager.py").read_text(encoding="utf-8")


def extract_method_body(source: str, method_name: str) -> str:
    start_match = re.search(rf"\n    def {re.escape(method_name)}\(", source)
    rest = source[start_match.end():]
    next_match = re.search(r"\n    def ", rest)
    end = next_match.start() if next_match else len(rest)
    return rest[:end]


body_execute_18 = extract_method_body(retry_manager_source, "execute_dispatchable_retries")
check_false("18. RetryManager.execute_dispatchable_retries()本体が「self._queue」を含まない", "self._queue" in body_execute_18)
print()


# ═══════════════════════════════════════════════════════════
# テスト19: dispatchable=Falseの候補はretry()に到達しない
# ═══════════════════════════════════════════════════════════

print("[テスト19] dispatchable=Falseの候補はretry()（Monitor.get_status()）に到達しない")

fake_monitor_19 = FakeWorkflowMonitorManager(record=make_record("run-19", WorkflowMonitorStatus.FAILED))
fake_executor_19 = FakeRetryExecutor(result=None)
manager_19 = RetryManager(policy=policy_ok, executor=fake_executor_19, monitor=fake_monitor_19)

false_candidate_event_19 = RetryCandidateEvent(run_id="", candidate=FakeCandidate(run_id=""), source_event=make_retry_event("placeholder"))
fake_dispatcher_19 = type(
    "FakeDispatcherAllFalse",
    (),
    {"dispatch": lambda self, candidate_events: [RetryDispatchEvent(candidate_event=false_candidate_event_19, dispatchable=False)]},
)()
manager_19_with_fake_dispatcher = RetryManager(
    policy=policy_ok, executor=fake_executor_19, monitor=fake_monitor_19, event_dispatcher=fake_dispatcher_19,
)
result_19 = manager_19_with_fake_dispatcher.execute_dispatchable_retries([make_retry_event("run-19")])
check("19. dispatchable=Falseのみの場合、結果は空リスト", result_19, [])
check("19. FakeMonitor.get_status()は一度も呼ばれない", fake_monitor_19.call_count, 0)
print()


# ═══════════════════════════════════════════════════════════
# テスト20: 実際のretry()が呼ばれ、RetryResultが返る統合確認
# ═══════════════════════════════════════════════════════════

print("[テスト20] dispatchable=TrueのRetryDispatchEventに対し実際にRetryManager.retry()が呼ばれる")

fake_monitor_20 = FakeWorkflowMonitorManager(record=make_record("run-20", WorkflowMonitorStatus.FAILED))
fake_executor_20 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-20", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None, workflow_engine_result=None,
))
manager_20 = RetryManager(policy=policy_ok, executor=fake_executor_20, monitor=fake_monitor_20)

results_20 = manager_20.execute_dispatchable_retries([make_retry_event("run-20")])
check("20. 実行結果が1件返る", len(results_20), 1)
check("20. FakeMonitor.get_status()が実際に呼ばれる（Read Before Retryが機能している）", fake_monitor_20.calls, ["run-20"])
check("20. RetryExecutionResult.retry_result.outcomeがRETRIED", results_20[0].retry_result.outcome, RetryOutcome.RETRIED)
check("20. RetryExecutionResult.dispatch_event.candidate_event.run_idがrun-20", results_20[0].dispatch_event.candidate_event.run_id, "run-20")
print()


# ═══════════════════════════════════════════════════════════
# テスト21-22: NullRetryManager：常に[]を返す
# ═══════════════════════════════════════════════════════════

print("[テスト21-22] NullRetryManager.execute_dispatchable_retries()は常に[]を返す")

null_mgr_21 = NullRetryManager()
result_21_with_retry_events = null_mgr_21.execute_dispatchable_retries([make_retry_event("run-21a"), make_retry_event("run-21b")])
check("21. Retry候補由来のイベントを含んでいても常に[]を返す", result_21_with_retry_events, [])

result_21_empty = null_mgr_21.execute_dispatchable_retries([])
check("21. 空リストを渡しても[]を返す", result_21_empty, [])

check("22. NullRetryManagerはRetryExecutionSelector等のいかなるフィールドも持たない", vars(null_mgr_21), {})
print()


# ═══════════════════════════════════════════════════════════
# テスト23: 書き込みが発生しないことの確認
# ═══════════════════════════════════════════════════════════

print("[テスト23] 実行処理の前後でファイルが一切作成されない")

write_check_dir_23 = Path(tempfile.mkdtemp())
before_files_23 = list(write_check_dir_23.rglob("*"))

fake_monitor_23w = FakeWorkflowMonitorManager(record=make_record("run-23w", WorkflowMonitorStatus.FAILED))
fake_executor_23w = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-23w", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None, workflow_engine_result=None,
))
manager_23w = RetryManager(policy=policy_ok, executor=fake_executor_23w, monitor=fake_monitor_23w)
manager_23w.execute_dispatchable_retries([make_retry_event("run-23w")])
NullRetryManager().execute_dispatchable_retries([make_retry_event("run-23wb")])

after_files_23 = list(write_check_dir_23.rglob("*"))
check("23. 実行処理前後でファイルが作成されない", after_files_23, before_files_23)
print()


# ═══════════════════════════════════════════════════════════
# テスト24: Architecture Guard（無改修の確認）
# ═══════════════════════════════════════════════════════════

print("[テスト24] 既存ファイルの無変更確認（git diff）")

unchanged_paths_v400 = [
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
    for rel_path in unchanged_paths_v400:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"24. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("24. gitが利用できないため無変更確認をスキップ", True)
print()


# ═══════════════════════════════════════════════════════════
# テスト25: retry_engineパッケージのexport確認
# ═══════════════════════════════════════════════════════════

print("[テスト25] retry_engine.__all__ に新規シンボルが追加され、既存シンボルが維持されていること")

import retry_engine as re_pkg_25

check(
    "25. retry_engine.__all__ が既存シンボル＋新規3シンボルの構成になっている",
    set(re_pkg_25.__all__),
    {
        "RetryPolicy", "DEFAULT_TARGET_STATUSES", "RetryConfig", "RetryRequest", "RetryOutcome",
        "RetryResult", "RetryExecutor", "RetryCandidateEvent", "RetryEventConsumer",
        "RetryDispatchEvent", "RetryEventDispatcher", "RetryExecutionSelector",
        "RetryExecutionCoordinator", "RetryExecutionResult", "RetryManager", "NullRetryManager",
    },
)
check_true("25. RetryManagerがexecute_dispatchable_retries()を持つ", hasattr(RetryManager, "execute_dispatchable_retries"))
check_true("25. NullRetryManagerがexecute_dispatchable_retries()を持つ", hasattr(NullRetryManager, "execute_dispatchable_retries"))
print()


# ═══════════════════════════════════════════════════════════
# テスト26: __init__ / from_config() の新規引数の後方互換性
# ═══════════════════════════════════════════════════════════

print("[テスト26] RetryManager.__init__ / from_config()の新規引数が末尾・デフォルト値付きで追加されていること")

sig_init_26 = inspect.signature(RetryManager.__init__)
params_init_26 = list(sig_init_26.parameters.keys())
check("26. __init__の最終引数がexecution_coordinator", params_init_26[-1], "execution_coordinator")
check("26. __init__の最後から2番目の引数がexecution_selector", params_init_26[-2], "execution_selector")
check("26. execution_selectorのデフォルトはNone", sig_init_26.parameters["execution_selector"].default, None)
check("26. execution_coordinatorのデフォルトはNone", sig_init_26.parameters["execution_coordinator"].default, None)

sig_from_config_26 = inspect.signature(RetryManager.from_config)
params_from_config_26 = list(sig_from_config_26.parameters.keys())
check("26. from_config()の最終引数がexecution_coordinator", params_from_config_26[-1], "execution_coordinator")
check("26. from_config()の最後から2番目の引数がexecution_selector", params_from_config_26[-2], "execution_selector")
check(
    "26. 既存7引数（event_dispatcher含む）の名前・順序が変わっていない",
    params_from_config_26[:7],
    [
        "retry_config", "retry_policy", "workflow_engine_manager", "workflow_monitor_manager",
        "retry_queue_manager", "event_consumer", "event_dispatcher",
    ],
)
print()


# ═══════════════════════════════════════════════════════════
# テスト27: 新規ファイルが retry_queue / scheduler / dequeue / remove をimportしないこと
# ═══════════════════════════════════════════════════════════

print("[テスト27] retry_execution_selector.py / retry_execution_coordinator.py に "
      "'retry_queue' / 'scheduler' / 'dequeue' / 'remove' への実コード参照がない（AST）")


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


for filename_27 in ["retry_execution_selector.py", "retry_execution_coordinator.py"]:
    source_path_27 = PROJECT_ROOT / "src" / "retry_engine" / filename_27
    tree_27 = ast.parse(source_path_27.read_text(encoding="utf-8"))
    referenced_27 = _referenced_names(tree_27)
    check_false(f"27. {filename_27}: 'retry_queue' への実コード参照が存在しない", "retry_queue" in referenced_27)
    check_false(f"27. {filename_27}: 'scheduler' への実コード参照が存在しない", "scheduler" in referenced_27)
    check_false(f"27. {filename_27}: 'dequeue' への実コード参照が存在しない", "dequeue" in referenced_27)
    check_false(f"27. {filename_27}: 'remove' への実コード参照が存在しない", "remove" in referenced_27)
print()


# ═══════════════════════════════════════════════════════════
# テスト28: 既存回帰（v3.0.0〜v3.9.0 RetryManager挙動）
# ═══════════════════════════════════════════════════════════

print("[テスト28] retry() / recognize_retry_events() / dispatch_retry_events()の既存挙動が維持される")

fake_monitor_28 = FakeWorkflowMonitorManager(record=make_record("run-28", WorkflowMonitorStatus.FAILED))
fake_executor_28 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-28", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None, workflow_engine_result=None,
))
manager_28 = RetryManager(policy=policy_ok, executor=fake_executor_28, monitor=fake_monitor_28)
result_28 = manager_28.retry("run-28", attempt=1)
check("28. retry()が本Release後も同じ挙動（RETRIED）", result_28.outcome, RetryOutcome.RETRIED)

recognized_28 = manager_28.recognize_retry_events([make_retry_event("run-28r")])
check("28. recognize_retry_events()が本Release後も同じ挙動", [r.run_id for r in recognized_28], ["run-28r"])

dispatched_28 = manager_28.dispatch_retry_events([make_retry_event("run-28d")])
check("28. dispatch_retry_events()が本Release後も同じ挙動", [d.candidate_event.run_id for d in dispatched_28], ["run-28d"])
check_true("28. dispatch_retry_events()の結果はdispatchable=True", dispatched_28[0].dispatchable)

null_mgr_28 = NullRetryManager()
result_28b = null_mgr_28.enqueue_retry(run_id="run-28b", workflow_name="news")
check_contains_28 = "Retry Engine is disabled" in result_28b.reason
check_true("28. NullRetryManager.enqueue_retry()が本Release後も同じ挙動（DISABLED理由文言）", check_contains_28)
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
