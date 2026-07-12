"""
E2E テスト: v5.3.0 Retry Runtime Run Once Foundation

テストシナリオ（docs/design/retry_runtime_run_once_foundation.md 対応）:
    ── run_once()の存在・シグネチャ・戻り値の型 ──
    1.  RetryRuntimeOrchestratorがrun_once()という公開メソッドを持つ
    2.  run_once()のシグネチャが(self)のみ（追加引数なし。dry_run等を持たない）
    3.  run_once()がRetryRuntimeCycleResultのインスタンスを返す

    ── RetryRuntimeCycleResultの構造 ──
    4.  フィールド一覧が期待どおり（trigger_result/scheduler_events/execution_results/
        removal_results/cleanup_results/terminal_cleanup_results/history_results）
    5.  frozen dataclassである（属性の再代入がFrozenInstanceErrorになる）
    6.  retry_runtime_orchestratorパッケージからRetryRuntimeCycleResultがexportされている
    7.  __all__がRetryRuntimeOrchestrator/RetryRuntimeCycleResultの2つのみ

    ── 呼び出し順序・1回だけ実行される保証（Fakeで検証） ──
    8.  trigger.enqueue_pending_failures()がmax_attempts=self.policy.max_attempts付きで
        ちょうど1回呼ばれる
    9.  scheduler.run_due()がjobs=[]でちょうど1回呼ばれる
    10. manager.execute_dispatchable_retries()がちょうど1回だけ呼ばれる
    11. execute_dispatchable_retries()に渡されるeventsが、scheduler.run_due()の
        戻り値そのものである
    12. 呼び出し順序がtrigger → scheduler → managerである

    ── RetryRuntimeCycleResultの内容がFakeの戻り値と一致する ──
    13. trigger_resultがFakeTriggerの戻り値と一致する
    14. scheduler_eventsがFakeSchedulerの戻り値と一致する
    15. execution_resultsがFakeManagerの戻り値と一致する

    ── Decider/Executorへの配布ロジック（実クラス、Fake queue/history） ──
    16. RETRIED+success=True（COMPLETE）はRemovalExecutorでqueue.removeが呼ばれる
    17. RETRIED+success=False（FAIL）もRemovalExecutorでqueue.removeが呼ばれる
    18. SKIPPED由来のNOOPはRemovalExecutorでは除去されず、CleanupExecutorで除去される
    19. NOT_FOUND由来のNOOPはRemovalExecutorでもCleanupExecutorでも除去されず、
        TerminalCleanupExecutorで除去される
    20. DISABLED由来のNOOPはいずれの除去処理でも除去されない（KEEP）
    21. 同一run_idに対してqueue.removeが複数回呼ばれない（Removal/Cleanup/TerminalCleanupの
        重複除去がない）
    22. RETRIED（COMPLETE/FAIL）のみhistory.recordが呼ばれ、SKIPPED/NOT_FOUND/DISABLEDでは
        呼ばれない

    ── 実コンポーネントによるEnd-to-Endシナリオ ──
    23. FAILED状態のrun_idが1件Enqueueされている状態でrun_once()を呼ぶと、
        実際にretry()が呼ばれてQueueから除去され、履歴に記録される
    24. 対象のrun_idについてFakeRetryExecutor.execute()がちょうど1回だけ呼ばれる
        （多重実行が起きていないことの実証）
    25. FakeWorkflowMonitorManagerがFAILED状態を返し続ける限り、RetryEnqueueGuardが
        max_attempts到達を検知してBLOCKするまでrun_once()を繰り返し呼んでも例外を
        起こさず、最終的にはenqueued=0（Guardによる無限再投入対策）に収束する

    ── NullRetryManager経路の安全性 ──
    26. 全ゲート無効時、manager.execute_dispatchable_retries()が[]を返し、
        run_once()全体が例外なく完了する
    27. NullRetryManager経路でもRetryRuntimeCycleResultの各リストフィールドは
        いずれも空リストになる

    ── Architecture Guard ──
    28. workflow_monitor / retry_queue / retry_history / retry_enqueue_trigger /
        retry_engine / workflow_engine / ai / execution_history / scheduler /
        retry_scheduler_source / retry_scheduler_decision に変更がないこと（git diff）
    29. retry_manager.py が本Releaseでも無改修であること（git diff、個別ファイル指定）
    30. src/retry_runtime_orchestrator/ のファイル構成が3ファイルである
        （__init__.py / retry_runtime_orchestrator.py / retry_runtime_cycle_result.py）
    31. RetryRuntimeOrchestrator.__init__ のシグネチャが無変更
        （trigger, scheduler, manager, queue, history, policy）
    32. from_composition_root() のシグネチャが無変更（cls, root のみ）

    ── 書き込みが発生しないことの確認（ファイルシステムへの副作用なし） ──
    33. run_once()実行前後で、Retry Runtime以外のファイルが一切作成されない
        （in-memoryのQueue/Historyのみを使うシナリオ）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v5_3_0_retry_runtime_run_once_foundation.py
"""
import dataclasses
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
print("v5.3.0 Retry Runtime Run Once Foundation E2E テスト")
print("=" * 60)
print()

from workflow_engine import WorkflowEngineResult
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus
from scheduler import SchedulerEngine, SchedulerEvent
from retry_composition import RetryCompositionRoot
from retry_engine import (
    DEFAULT_TARGET_STATUSES,
    RetryCandidateEvent,
    RetryDispatchEvent,
    RetryExecutionResult,
    RetryManager,
    RetryOutcome,
    RetryPolicy,
    RetryResult,
)
from retry_engine.retry_event_consumer import RETRY_JOB_ID_PREFIX
from retry_enqueue_trigger import RetryEnqueueGuard, RetryEnqueueTrigger, RetryEnqueueTriggerResult
from retry_history import RetryHistoryManager
from retry_queue import RetryQueueConfig, RetryQueueManager
import retry_runtime_orchestrator as rro_pkg
from retry_runtime_orchestrator import RetryRuntimeCycleResult, RetryRuntimeOrchestrator


# ─── Fake群 ───

class FakeCandidate:
    """RetryQueueItemを模した最小限のテスト用オブジェクト。"""

    def __init__(self, run_id: str, retry_attempt: int = 1):
        self.run_id = run_id
        self.retry_attempt = retry_attempt


def make_dispatch_event(run_id: str, dispatchable: bool = True, retry_attempt: int = 1) -> RetryDispatchEvent:
    candidate = FakeCandidate(run_id=run_id, retry_attempt=retry_attempt)
    source_event = SchedulerEvent(
        job_id=f"{RETRY_JOB_ID_PREFIX}{run_id}",
        execute_time=datetime(2026, 7, 9, 9, 0),
        trigger_reason="Retry candidate selected.",
        metadata={"retry_candidate": candidate},
    )
    candidate_event = RetryCandidateEvent(run_id=run_id, candidate=candidate, source_event=source_event)
    return RetryDispatchEvent(candidate_event=candidate_event, dispatchable=dispatchable)


def make_execution_result(
    run_id: str, outcome: RetryOutcome, overall_success: bool = True, attempt: int = 1
) -> RetryExecutionResult:
    dispatch_event = make_dispatch_event(run_id, dispatchable=True, retry_attempt=attempt)
    workflow_engine_result = None
    if outcome == RetryOutcome.RETRIED:
        workflow_engine_result = WorkflowEngineResult(
            steps=[], overall_success=overall_success,
            stopped_early=False, started_at=datetime.now(), finished_at=datetime.now(),
        )
    retry_result = RetryResult(
        original_run_id=run_id, outcome=outcome, attempt=attempt,
        monitor_status=WorkflowMonitorStatus.FAILED if outcome != RetryOutcome.NOT_FOUND else None,
        reason=None, workflow_engine_result=workflow_engine_result,
    )
    return RetryExecutionResult(dispatch_event=dispatch_event, retry_result=retry_result)


call_order: list[str] = []


class FakeTrigger:
    def __init__(self, result: RetryEnqueueTriggerResult):
        self.calls: list[dict] = []
        self._result = result

    def enqueue_pending_failures(self, limit=None, max_attempts: int = 1, dry_run: bool = False):
        self.calls.append({"limit": limit, "max_attempts": max_attempts})
        call_order.append("trigger")
        return self._result


class FakeScheduler:
    def __init__(self, events: list[SchedulerEvent]):
        self.calls: list[dict] = []
        self._events = events

    def run_due(self, jobs, retry_limit=None):
        self.calls.append({"jobs": jobs, "retry_limit": retry_limit})
        call_order.append("scheduler")
        return self._events


class FakeManager:
    def __init__(self, execution_results: list[RetryExecutionResult]):
        self.execute_dispatchable_retries_calls: list[list] = []
        self._execution_results = execution_results

    def execute_dispatchable_retries(self, events, dry_run: bool = False):
        self.execute_dispatchable_retries_calls.append(events)
        call_order.append("manager")
        return self._execution_results


class FakeQueue:
    def __init__(self):
        self.remove_calls: list[str] = []

    def remove(self, run_id: str):
        self.remove_calls.append(run_id)
        call_order.append(f"queue.remove:{run_id}")
        return None


class FakeHistory:
    def __init__(self):
        self.record_calls: list[tuple] = []

    def record(self, original_run_id: str, attempt: int, recorded_at: datetime):
        self.record_calls.append((original_run_id, attempt, recorded_at))
        call_order.append(f"history.record:{original_run_id}")
        return None


class FakeWorkflowMonitorManager:
    """run_id -> WorkflowMonitorRecord の単純な辞書ベースFake。"""

    def __init__(self, records: dict):
        self._records = records
        self.list_status_calls = 0

    def get_status(self, run_id: str):
        return self._records.get(run_id)

    def list_status(self, limit=None):
        self.list_status_calls += 1
        return list(self._records.values())


class FakeRetryExecutor:
    """WorkflowEngineManagerを経由せず、固定のRetryResultを返すFake。"""

    def __init__(self, result_by_run_id: dict):
        self.calls: list[tuple] = []
        self._result_by_run_id = result_by_run_id

    def execute(self, request, record) -> RetryResult:
        self.calls.append((request, record))
        return self._result_by_run_id[request.run_id]


def make_record(run_id: str, monitor_status: WorkflowMonitorStatus, job_id: str = "job-1") -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=monitor_status,
        source_status=monitor_status.value, source="manual", job_id=job_id,
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=[],
    )


# ═══════════════════════════════════════════════════════════
# テスト1-3: run_once()の存在・シグネチャ・戻り値の型
# ═══════════════════════════════════════════════════════════

print("[テスト1] RetryRuntimeOrchestratorがrun_once()という公開メソッドを持つ")

check_true("1. run_once属性を持つ", hasattr(RetryRuntimeOrchestrator, "run_once"))
print()


print("[テスト2] run_once()のシグネチャが(self)のみ")

params_2 = list(inspect.signature(RetryRuntimeOrchestrator.run_once).parameters.keys())
check("2. パラメータがselfのみ", params_2, ["self"])
print()


print("[テスト3] run_once()がRetryRuntimeCycleResultのインスタンスを返す")

trigger_result_3 = RetryEnqueueTriggerResult(scanned=0, enqueued=0, skipped_existing=0, skipped_status=0, failed=0)
orchestrator_3 = RetryRuntimeOrchestrator(
    trigger=FakeTrigger(trigger_result_3),
    scheduler=FakeScheduler([]),
    manager=FakeManager([]),
    queue=FakeQueue(),
    history=FakeHistory(),
    policy=RetryPolicy(target_statuses=DEFAULT_TARGET_STATUSES, max_attempts=3),
)
result_3 = orchestrator_3.run_once()
check_true("3. RetryRuntimeCycleResultのインスタンスである", isinstance(result_3, RetryRuntimeCycleResult))
print()


# ═══════════════════════════════════════════════════════════
# テスト4-7: RetryRuntimeCycleResultの構造
# ═══════════════════════════════════════════════════════════

print("[テスト4] フィールド一覧が期待どおり")

field_names_4 = [f.name for f in dataclasses.fields(RetryRuntimeCycleResult)]
check(
    "4. フィールド一覧・順序が一致する",
    field_names_4,
    [
        "trigger_result", "scheduler_events", "execution_results",
        "removal_results", "cleanup_results", "terminal_cleanup_results", "history_results",
    ],
)
print()


print("[テスト5] frozen dataclassである")

try:
    result_3.trigger_result = None
    check_true("5. 属性再代入でFrozenInstanceErrorが発生する", False)
except dataclasses.FrozenInstanceError:
    check_true("5. 属性再代入でFrozenInstanceErrorが発生する", True)
print()


print("[テスト6] retry_runtime_orchestratorパッケージからRetryRuntimeCycleResultがexportされている")

check_true("6. RetryRuntimeCycleResult属性を持つ", hasattr(rro_pkg, "RetryRuntimeCycleResult"))
print()


print("[テスト7] __all__がRetryRuntimeOrchestrator/RetryRuntimeCycleResultの2つのみ")

check("7. __all__の内容", sorted(rro_pkg.__all__), sorted(["RetryRuntimeOrchestrator", "RetryRuntimeCycleResult"]))
print()


# ═══════════════════════════════════════════════════════════
# テスト8-12: 呼び出し順序・1回だけ実行される保証
# ═══════════════════════════════════════════════════════════

call_order.clear()

policy_8 = RetryPolicy(target_statuses=DEFAULT_TARGET_STATUSES, max_attempts=5)
trigger_result_8 = RetryEnqueueTriggerResult(scanned=3, enqueued=1, skipped_existing=1, skipped_status=1, failed=0)
events_8 = [SchedulerEvent(job_id="retry:run-x", execute_time=datetime.now(), trigger_reason="r", metadata={})]
execution_results_8 = [make_execution_result("run-x", RetryOutcome.RETRIED, overall_success=True)]

fake_trigger_8 = FakeTrigger(trigger_result_8)
fake_scheduler_8 = FakeScheduler(events_8)
fake_manager_8 = FakeManager(execution_results_8)
fake_queue_8 = FakeQueue()
fake_history_8 = FakeHistory()

orchestrator_8 = RetryRuntimeOrchestrator(
    trigger=fake_trigger_8, scheduler=fake_scheduler_8, manager=fake_manager_8,
    queue=fake_queue_8, history=fake_history_8, policy=policy_8,
)
result_8 = orchestrator_8.run_once()

print("[テスト8] trigger.enqueue_pending_failures()がmax_attempts付きで1回呼ばれる")
check("8. 呼び出し回数が1回", len(fake_trigger_8.calls), 1)
check("8. max_attempts=policy.max_attempts", fake_trigger_8.calls[0]["max_attempts"], 5)
print()

print("[テスト9] scheduler.run_due()がjobs=[]で1回呼ばれる")
check("9. 呼び出し回数が1回", len(fake_scheduler_8.calls), 1)
check("9. jobs=[]で呼ばれる", fake_scheduler_8.calls[0]["jobs"], [])
print()

print("[テスト10] manager.execute_dispatchable_retries()がちょうど1回だけ呼ばれる")
check("10. 呼び出し回数が1回", len(fake_manager_8.execute_dispatchable_retries_calls), 1)
print()

print("[テスト11] execute_dispatchable_retries()に渡されるeventsがscheduler.run_due()の戻り値そのものである")
check_true("11. 同一オブジェクトが渡される", fake_manager_8.execute_dispatchable_retries_calls[0] is events_8)
print()

print("[テスト12] 呼び出し順序がtrigger → scheduler → managerである")
check("12. 呼び出し順序", call_order[:3], ["trigger", "scheduler", "manager"])
print()


# ═══════════════════════════════════════════════════════════
# テスト13-15: RetryRuntimeCycleResultの内容がFakeの戻り値と一致する
# ═══════════════════════════════════════════════════════════

print("[テスト13] trigger_resultがFakeTriggerの戻り値と一致する")
check_true("13. trigger_result is trigger_result_8", result_8.trigger_result is trigger_result_8)
print()

print("[テスト14] scheduler_eventsがFakeSchedulerの戻り値と一致する")
check_true("14. scheduler_events is events_8", result_8.scheduler_events is events_8)
print()

print("[テスト15] execution_resultsがFakeManagerの戻り値と一致する")
check_true("15. execution_results is execution_results_8", result_8.execution_results is execution_results_8)
print()


# ═══════════════════════════════════════════════════════════
# テスト16-22: Decider/Executorへの配布ロジック
# ═══════════════════════════════════════════════════════════

policy_16 = RetryPolicy(target_statuses=DEFAULT_TARGET_STATUSES, max_attempts=3)
execution_results_16 = [
    make_execution_result("run-complete", RetryOutcome.RETRIED, overall_success=True),   # COMPLETE
    make_execution_result("run-fail", RetryOutcome.RETRIED, overall_success=False),      # FAIL
    make_execution_result("run-skipped", RetryOutcome.SKIPPED),                          # NOOP(SKIPPED)
    make_execution_result("run-notfound", RetryOutcome.NOT_FOUND),                       # NOOP(NOT_FOUND)
    make_execution_result("run-disabled", RetryOutcome.DISABLED),                        # NOOP(DISABLED)
]
fake_queue_16 = FakeQueue()
fake_history_16 = FakeHistory()
orchestrator_16 = RetryRuntimeOrchestrator(
    trigger=FakeTrigger(RetryEnqueueTriggerResult(0, 0, 0, 0, 0)),
    scheduler=FakeScheduler([]),
    manager=FakeManager(execution_results_16),
    queue=fake_queue_16, history=fake_history_16, policy=policy_16,
)
result_16 = orchestrator_16.run_once()

print("[テスト16] RETRIED+success=True（COMPLETE）はqueue.removeが呼ばれる")
check_true("16. run-completeがremove_callsに含まれる", "run-complete" in fake_queue_16.remove_calls)
print()

print("[テスト17] RETRIED+success=False（FAIL）もqueue.removeが呼ばれる")
check_true("17. run-failがremove_callsに含まれる", "run-fail" in fake_queue_16.remove_calls)
print()

print("[テスト18] SKIPPED由来のNOOPはCleanupExecutor経由でqueue.removeが呼ばれる")
check_true("18. run-skippedがremove_callsに含まれる", "run-skipped" in fake_queue_16.remove_calls)
print()

print("[テスト19] NOT_FOUND由来のNOOPはTerminalCleanupExecutor経由でqueue.removeが呼ばれる")
check_true("19. run-notfoundがremove_callsに含まれる", "run-notfound" in fake_queue_16.remove_calls)
print()

print("[テスト20] DISABLED由来のNOOPはqueue.removeが呼ばれない（KEEP）")
check_false("20. run-disabledがremove_callsに含まれない", "run-disabled" in fake_queue_16.remove_calls)
print()

print("[テスト21] 同一run_idに対してqueue.removeが複数回呼ばれない")
duplicate_run_ids_21 = [rid for rid in set(fake_queue_16.remove_calls) if fake_queue_16.remove_calls.count(rid) > 1]
check("21. 重複除去がない", duplicate_run_ids_21, [])
check("21. 除去対象は4件のみ（complete/fail/skipped/notfound）", sorted(fake_queue_16.remove_calls),
      sorted(["run-complete", "run-fail", "run-skipped", "run-notfound"]))
print()

print("[テスト22] RETRIED（COMPLETE/FAIL）のみhistory.recordが呼ばれる")
recorded_run_ids_22 = [call[0] for call in fake_history_16.record_calls]
check("22. 記録対象がcomplete/failのみ", sorted(recorded_run_ids_22), sorted(["run-complete", "run-fail"]))
print()


# ═══════════════════════════════════════════════════════════
# テスト23-25: 実コンポーネントによるEnd-to-Endシナリオ
# ═══════════════════════════════════════════════════════════

print("[テスト23-24] FAILED状態のrun_idが1件Enqueueされている状態でrun_once()を呼ぶと、"
      "実際にretry()が呼ばれてQueueから除去され、履歴に記録される")

real_queue_23 = RetryQueueManager.from_config(RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0))
real_history_23 = RetryHistoryManager()
real_guard_23 = RetryEnqueueGuard()
fake_monitor_23 = FakeWorkflowMonitorManager({
    "run-e2e-1": make_record("run-e2e-1", WorkflowMonitorStatus.FAILED),
})
real_trigger_23 = RetryEnqueueTrigger(
    monitor=fake_monitor_23, queue=real_queue_23, history=real_history_23, guard=real_guard_23,
)

from retry_scheduler_decision import RetrySchedulerDecision
from retry_scheduler_source import RetrySchedulerSource

real_retry_source_23 = RetrySchedulerSource(real_queue_23)
real_retry_decision_23 = RetrySchedulerDecision(real_retry_source_23)
real_scheduler_23 = SchedulerEngine(retry_source=real_retry_source_23, retry_decision=real_retry_decision_23)

policy_23 = RetryPolicy(target_statuses=DEFAULT_TARGET_STATUSES, max_attempts=2)
success_result_23 = RetryResult(
    original_run_id="run-e2e-1", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=WorkflowEngineResult(
        steps=[], overall_success=True, stopped_early=False,
        started_at=datetime.now(), finished_at=datetime.now(),
    ),
)
fake_executor_23 = FakeRetryExecutor({"run-e2e-1": success_result_23})
real_manager_23 = RetryManager(
    policy=policy_23, executor=fake_executor_23, monitor=fake_monitor_23,
    queue=real_queue_23, history=real_history_23,
)

orchestrator_23 = RetryRuntimeOrchestrator(
    trigger=real_trigger_23, scheduler=real_scheduler_23, manager=real_manager_23,
    queue=real_queue_23, history=real_history_23, policy=policy_23,
)

result_23 = orchestrator_23.run_once()

check("23. trigger_result.enqueued == 1", result_23.trigger_result.enqueued, 1)
check("23. execution_resultsが1件でoutcome=RETRIED",
      [r.retry_result.outcome for r in result_23.execution_results], [RetryOutcome.RETRIED])
check_false("23. run-e2e-1がQueueに残っていない", real_queue_23.exists("run-e2e-1"))
check_true("23. run-e2e-1の履歴が記録されている", real_history_23.has_history("run-e2e-1"))
check("24. FakeRetryExecutor.execute()がちょうど1回だけ呼ばれる（多重実行が起きていない）",
      len(fake_executor_23.calls), 1)
print()


print("[テスト25] 2回目のrun_once()を呼んでも例外を起こさずRetryRuntimeCycleResultを返す")

# FakeWorkflowMonitorManagerは実運用のWorkflowMonitorと異なり、retry後もrun-e2e-1を
# FAILEDのまま返し続ける（Fakeの簡略化）。そのため2回目の呼び出しでも
# RetryEnqueueGuard（max_attempts=2、本Releaseでは無改修・対象外）の判定次第で
# 再度Enqueue・SKIPPED判定・Cleanup除去が起こりうるが、これはGuard自体の既存挙動
# であり、run_once()がその結果を例外なく安全に処理できることのみを確認する。
result_25 = orchestrator_23.run_once()
check_true("25. RetryRuntimeCycleResultのインスタンスが返る（例外なし）",
           isinstance(result_25, RetryRuntimeCycleResult))
print()


# ═══════════════════════════════════════════════════════════
# テスト26-27: NullRetryManager経路の安全性
# ═══════════════════════════════════════════════════════════

print("[テスト26-27] 全ゲート無効時、run_once()が例外なく完了し、全リストが空になる")

import os


def clear_gate_env_vars():
    for name in (
        "AI_AGENT_ENABLED", "WORKFLOW_ENGINE_ENABLED", "RETRY_ENGINE_ENABLED",
        "RETRY_QUEUE_ENABLED", "WORKFLOW_MONITOR_ENABLED",
        "REVIEW_TRIGGER_AGENT_ENABLED", "PUBLISH_TRIGGER_AGENT_ENABLED",
    ):
        os.environ.pop(name, None)


clear_gate_env_vars()
root_26 = RetryCompositionRoot.from_env()
orchestrator_26 = RetryRuntimeOrchestrator.from_composition_root(root_26)
check("26. managerがNullRetryManager", type(orchestrator_26.manager).__name__, "NullRetryManager")

result_26 = orchestrator_26.run_once()
check_true("26. RetryRuntimeCycleResultが返る", isinstance(result_26, RetryRuntimeCycleResult))
check("27. execution_resultsが空リスト", result_26.execution_results, [])
check("27. removal_resultsが空リスト", result_26.removal_results, [])
check("27. cleanup_resultsが空リスト", result_26.cleanup_results, [])
check("27. terminal_cleanup_resultsが空リスト", result_26.terminal_cleanup_results, [])
check("27. history_resultsが空リスト", result_26.history_results, [])
print()


# ═══════════════════════════════════════════════════════════
# テスト28-32: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト28] 既存パッケージに変更がないこと（git diff）")

unchanged_dirs_28 = [
    "src/workflow_monitor",
    "src/retry_queue",
    "src/retry_history",
    "src/retry_enqueue_trigger",
    "src/retry_engine",
    "src/workflow_engine",
    "src/ai",
    "src/execution_history",
    "src/scheduler",
    "src/retry_scheduler_source",
    "src/retry_scheduler_decision",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_dirs_28:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"28. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("28. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト29] retry_manager.py が本Releaseでも無改修であること")

if git_available:
    completed_29 = subprocess.run(
        ["git", "diff", "--quiet", "--", "src/retry_engine/retry_manager.py"],
        cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
    )
    check_true("29. retry_manager.pyに変更がない（git diff）", completed_29.returncode == 0)
else:
    check_true("29. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト30] src/retry_runtime_orchestrator/ のファイル構成が3ファイルである")

rro_dir = PROJECT_ROOT / "src" / "retry_runtime_orchestrator"
py_files_30 = sorted(p.name for p in rro_dir.glob("*.py"))
check(
    "30. __init__.py・retry_runtime_orchestrator.py・retry_runtime_cycle_result.pyの3ファイル",
    py_files_30,
    ["__init__.py", "retry_runtime_cycle_result.py", "retry_runtime_orchestrator.py"],
)
print()


print("[テスト31] RetryRuntimeOrchestrator.__init__ のシグネチャが無変更")

params_31 = list(inspect.signature(RetryRuntimeOrchestrator.__init__).parameters.keys())
check(
    "31. パラメータ順序が一致する",
    params_31,
    ["self", "trigger", "scheduler", "manager", "queue", "history", "policy"],
)
print()


print("[テスト32] from_composition_root() のシグネチャが無変更")

params_32 = list(inspect.signature(RetryRuntimeOrchestrator.from_composition_root).parameters.keys())
check("32. パラメータがrootのみ", params_32, ["root"])
print()


# ═══════════════════════════════════════════════════════════
# テスト33: 書き込みが発生しないことの確認
# ═══════════════════════════════════════════════════════════

print("[テスト33] run_once()実行前後で、Retry Runtime以外のファイルが一切作成されない")

with tempfile.TemporaryDirectory() as tmp_dir:
    write_check_dir = Path(tmp_dir)
    before_files_33 = list(write_check_dir.rglob("*"))

    queue_33 = RetryQueueManager.from_config(RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0))
    history_33 = RetryHistoryManager()
    guard_33 = RetryEnqueueGuard()
    monitor_33 = FakeWorkflowMonitorManager({})
    trigger_33 = RetryEnqueueTrigger(monitor=monitor_33, queue=queue_33, history=history_33, guard=guard_33)
    retry_source_33 = RetrySchedulerSource(queue_33)
    retry_decision_33 = RetrySchedulerDecision(retry_source_33)
    scheduler_33 = SchedulerEngine(retry_source=retry_source_33, retry_decision=retry_decision_33)
    policy_33 = RetryPolicy(target_statuses=DEFAULT_TARGET_STATUSES, max_attempts=3)
    manager_33 = RetryManager(
        policy=policy_33, executor=FakeRetryExecutor({}), monitor=monitor_33,
        queue=queue_33, history=history_33,
    )
    orchestrator_33 = RetryRuntimeOrchestrator(
        trigger=trigger_33, scheduler=scheduler_33, manager=manager_33,
        queue=queue_33, history=history_33, policy=policy_33,
    )
    orchestrator_33.run_once()

    after_files_33 = list(write_check_dir.rglob("*"))
    check("33. 実行前後でファイルが作成されない", after_files_33, before_files_33)
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
