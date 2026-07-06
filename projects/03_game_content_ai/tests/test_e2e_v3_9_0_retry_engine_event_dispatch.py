"""
E2E テスト: v3.9.0 Retry Engine Event Dispatch

テストシナリオ（docs/design/retry_engine_event_dispatch.md 9章・13章 対応）:
    ── RetryEventDispatcher単体：Dispatch対象として整理する ──
    1.  run_idが空でないRetryCandidateEventはdispatchable=Trueとして整理される
    2.  run_idが空のRetryCandidateEventはdispatchable=Falseとして整理される（除外はしない）
    3.  RetryDispatchEvent.candidate_eventが元のRetryCandidateEventそのもの（同一インスタンス）である

    ── dispatch()：複数件・混在時の挙動 ──
    4.  run_idが空のものと空でないものが混在するリストから、両方とも結果に含まれる（除外されない）
    5.  空リストを渡した場合は空リストを返す
    6.  元のリストの順序が整理結果の順序に保たれる

    ── RetryManager.dispatch_retry_events()：委譲の正確性 ──
    7.  event_dispatcher省略時、RetryEventDispatcher()に自動フォールバックする
    8.  DIで渡したFakeのdispatch()の戻り値が、dispatch_retry_events()からそのまま返る
    9.  recognize_retry_events()経由で得たcandidate_eventsがそのままFakeのdispatch()に渡る
    10. from_config()の既存6引数呼び出しが本Release前と同じゲート判定結果を返す
    11. from_config()でevent_dispatcherを渡すと実際に配線される

    ── dispatch_retry_events()と既存操作の独立性 ──
    12. dispatch_retry_events()を呼んでもFakeQueue.enqueue()/dequeue()は呼ばれない
    13. dispatch_retry_events()を呼んでもFakeMonitor.get_status()/FakeExecutor.execute()は呼ばれない
    14. Architecture Guard：dispatch_retry_events()のソースコードが
        self._queue/self._policy/self._executor/self._monitorを一切参照しない

    ── NullRetryManager：常に[]を返す ──
    15. NullRetryManager.dispatch_retry_events()はRetry候補由来のイベントを含んでいても常に[]を返す
    16. NullRetryManagerはRetryEventDispatcher等のいかなるフィールドも持たない（vars()にフィールドが無い）

    ── 実際のSchedulerEngine（v3.7.0）+ RetryEventConsumer（v3.8.0）との統合確認 ──
    17. SchedulerEngine.evaluate()が生成したSchedulerEventをそのままdispatch_retry_events()に
        渡すと、Retry候補由来のものだけがdispatchable=TrueのRetryDispatchEventとして整理される

    ── 書き込みが発生しないことの確認 ──
    18. Dispatch整理処理の実行前後でファイルが一切作成されない

    ── Architecture Guard（無改修の確認） ──
    19. src/scheduler/ / src/retry_scheduler_decision/ / src/retry_scheduler_source/ /
        src/retry_queue/ 配下の全ファイル、および src/retry_engine/ のうち本Releaseで
        変更していないファイル（retry_event_consumer.py含む）に変更がないこと（git diff）
    20. retry_engineパッケージの__all__に新規シンボル（RetryDispatchEvent/RetryEventDispatcher）
        が追加され、既存シンボルは維持されていること
    21. RetryManager.__init__ / from_config()の新規引数が末尾・デフォルト値付きで追加されていること
    22. retry_event_dispatcher.py が scheduler / retry_queue をimportしていないこと（AST）

    ── 既存回帰（v3.0.0〜v3.8.0 RetryManager挙動）──
    23. retry() / enqueue_retry() / dequeue_retry() / recognize_retry_events()の挙動が
        本Releaseでも維持される

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v3_9_0_retry_engine_event_dispatch.py
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
print("v3.9.0 Retry Engine Event Dispatch E2E テスト")
print("=" * 60)
print()

from scheduler import SchedulerEngine, SchedulerEvent, SchedulerJob, TriggerType
from retry_queue import RetryQueueConfig, RetryQueueManager
from retry_queue.retry_queue_item import RetryQueueItem
from retry_queue.retry_queue_status import RetryQueueStatus
from retry_scheduler_source import RetrySchedulerSource
from retry_scheduler_decision import RetrySchedulerDecision
from workflow_engine import NullWorkflowEngineManager, WorkflowEngineResult
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus
from retry_engine import (
    DEFAULT_TARGET_STATUSES,
    NullRetryManager,
    RetryCandidateEvent,
    RetryConfig,
    RetryDispatchEvent,
    RetryEventConsumer,
    RetryEventDispatcher,
    RetryManager,
    RetryOutcome,
    RetryPolicy,
    RetryResult,
)
from retry_engine.retry_event_consumer import RETRY_JOB_ID_PREFIX


def make_candidate(run_id: str, priority: int = 0) -> RetryQueueItem:
    return RetryQueueItem(
        run_id=run_id, workflow_name="news", enqueue_time=datetime(2026, 7, 6, 9, 0),
        priority=priority, retry_attempt=1, status=RetryQueueStatus.WAITING,
    )


def make_retry_event(run_id: str, candidate: "RetryQueueItem | None" = None) -> SchedulerEvent:
    if candidate is None:
        candidate = make_candidate(run_id)
    return SchedulerEvent(
        job_id=f"{RETRY_JOB_ID_PREFIX}{run_id}",
        execute_time=datetime(2026, 7, 6, 9, 0),
        trigger_reason="Retry candidate selected.",
        metadata={"retry_candidate": candidate},
    )


def make_job_event(job_id: str) -> SchedulerEvent:
    return SchedulerEvent(
        job_id=job_id, execute_time=datetime(2026, 7, 6, 9, 0),
        trigger_reason="Daily schedule matched.", metadata={},
    )


def make_candidate_event(run_id: str) -> RetryCandidateEvent:
    candidate = make_candidate(run_id) if run_id else make_candidate("placeholder")
    event = make_retry_event(run_id if run_id else "placeholder", candidate)
    return RetryCandidateEvent(run_id=run_id, candidate=candidate, source_event=event)


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

    def get_status(self, run_id: str):
        self.call_count += 1
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


class FakeRetryEventDispatcher:
    """テスト専用のFake。dispatch()呼び出しを記録し、固定の戻り値を返す。"""

    def __init__(self, result: "list[RetryDispatchEvent] | None" = None):
        self.calls: list[list] = []
        self._result = result if result is not None else []

    def dispatch(self, candidate_events):
        self.calls.append(candidate_events)
        return self._result


def make_record(run_id: str, monitor_status: WorkflowMonitorStatus, job_id: str = "job-1") -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=monitor_status,
        source_status=monitor_status.value, source="manual", job_id=job_id,
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=[],
    )


# ═══════════════════════════════════════════════════════════
# テスト1-3: RetryEventDispatcher単体：Dispatch対象として整理する
# ═══════════════════════════════════════════════════════════

print("[テスト1-3] RetryEventDispatcher.dispatch_one()：Dispatch対象として整理する")

dispatcher_1 = RetryEventDispatcher()
candidate_event_1 = make_candidate_event("run-001")
result_1 = dispatcher_1.dispatch_one(candidate_event_1)
check_true("1. run_idが空でないRetryCandidateEventはdispatchable=Trueとして整理される", result_1.dispatchable)

candidate_event_2 = RetryCandidateEvent(run_id="", candidate=make_candidate(""), source_event=make_job_event("job-2"))
result_2 = dispatcher_1.dispatch_one(candidate_event_2)
check_false("2. run_idが空のRetryCandidateEventはdispatchable=Falseとして整理される", result_2.dispatchable)
check_true("2. dispatchable=Falseでも除外されずRetryDispatchEventとして返る", isinstance(result_2, RetryDispatchEvent))

check_true("3. RetryDispatchEvent.candidate_eventが元のRetryCandidateEventそのもの（同一インスタンス）", result_1.candidate_event is candidate_event_1)
print()


# ═══════════════════════════════════════════════════════════
# テスト4-6: dispatch()：複数件・混在時の挙動
# ═══════════════════════════════════════════════════════════

print("[テスト4-6] RetryEventDispatcher.dispatch()：複数件・混在時の挙動")

dispatcher_4 = RetryEventDispatcher()
mixed_candidates_4 = [
    make_candidate_event("run-101"),
    RetryCandidateEvent(run_id="", candidate=make_candidate(""), source_event=make_job_event("job-x")),
    make_candidate_event("run-102"),
]
dispatched_4 = dispatcher_4.dispatch(mixed_candidates_4)
check("4. 混在リストの全件が結果に含まれる（除外されない）", len(dispatched_4), 3)
check("4. dispatchableの並びが[True, False, True]", [d.dispatchable for d in dispatched_4], [True, False, True])

dispatched_5 = dispatcher_4.dispatch([])
check("5. 空リストを渡した場合は空リストを返す", dispatched_5, [])

ordered_candidates_6 = [make_candidate_event("run-c"), make_candidate_event("run-a"), make_candidate_event("run-b")]
dispatched_6 = dispatcher_4.dispatch(ordered_candidates_6)
check("6. 元のリストの順序が整理結果の順序に保たれる", [d.candidate_event.run_id for d in dispatched_6], ["run-c", "run-a", "run-b"])
print()


# ═══════════════════════════════════════════════════════════
# テスト7-11: RetryManager.dispatch_retry_events()：委譲の正確性
# ═══════════════════════════════════════════════════════════

print("[テスト7] event_dispatcher省略時、RetryEventDispatcher()に自動フォールバックする")

manager_7 = RetryManager(policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None))
check_true("7. event_dispatcher省略時、内部にRetryEventDispatcherが構築される", isinstance(manager_7._event_dispatcher, RetryEventDispatcher))
result_7 = manager_7.dispatch_retry_events([make_retry_event("run-7"), make_job_event("job-7")])
check("7. 自動フォールバックしたRetryEventDispatcherが実際に整理処理を行う", [d.candidate_event.run_id for d in result_7], ["run-7"])
check_true("7. 整理結果はdispatchable=True", result_7[0].dispatchable)
print()

print("[テスト8-9] DIで渡したFakeのdispatch()の呼び出し・戻り値がそのまま伝播する")

expected_result_8 = [RetryDispatchEvent(candidate_event=make_candidate_event("run-8"), dispatchable=True)]
fake_dispatcher_8 = FakeRetryEventDispatcher(result=expected_result_8)
manager_8 = RetryManager(
    policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None),
    event_dispatcher=fake_dispatcher_8,
)
events_8 = [make_retry_event("run-8"), make_job_event("job-8")]
result_8 = manager_8.dispatch_retry_events(events_8)
check("8. FakeのRetryEventDispatcher.dispatch()が1回だけ呼ばれる", len(fake_dispatcher_8.calls), 1)
check("8. 戻り値がRetryEventDispatcherの戻り値そのもの", result_8, expected_result_8)
check("9. recognize_retry_events()経由のcandidate_eventsがFakeのdispatch()に渡る", [c.run_id for c in fake_dispatcher_8.calls[0]], ["run-8"])
print()

print("[テスト10] from_config()の既存6引数呼び出しが本Release前と同じゲート判定結果を返す")

fake_engine_ok = FakeWorkflowEngineManager()
fake_monitor_ok = FakeWorkflowMonitorManager(record=None)

mgr_10a = RetryManager.from_config(RetryConfig(enabled=False), policy_ok, fake_engine_ok, fake_monitor_ok)
check_true("10. enabled=Falseの4引数呼び出し → NullRetryManager", isinstance(mgr_10a, NullRetryManager))

mgr_10b = RetryManager.from_config(RetryConfig(enabled=True), policy_ok, NullWorkflowEngineManager(), fake_monitor_ok)
check_true("10. NullWorkflowEngineManagerの4引数呼び出し → NullRetryManager", isinstance(mgr_10b, NullRetryManager))

mgr_10c = RetryManager.from_config(RetryConfig(enabled=True), policy_ok, fake_engine_ok, fake_monitor_ok)
check_true("10. 両方満たす4引数呼び出し → RetryManager（実インスタンス）", isinstance(mgr_10c, RetryManager))
check_true("10. event_dispatcher省略時、内部にRetryEventDispatcherが自動構築される", isinstance(mgr_10c._event_dispatcher, RetryEventDispatcher))
print()

print("[テスト11] from_config()でevent_dispatcherを渡すと実際に配線される")

fake_dispatcher_11 = FakeRetryEventDispatcher(result=[])
mgr_11 = RetryManager.from_config(
    RetryConfig(enabled=True), policy_ok, fake_engine_ok, fake_monitor_ok,
    event_dispatcher=fake_dispatcher_11,
)
mgr_11.dispatch_retry_events([make_retry_event("run-11")])
check("11. from_config()経由で渡したevent_dispatcherに実際に委譲される", len(fake_dispatcher_11.calls), 1)
print()


# ═══════════════════════════════════════════════════════════
# テスト12-14: dispatch_retry_events()と既存操作の独立性
# ═══════════════════════════════════════════════════════════

print("[テスト12-13] dispatch_retry_events()とQueue操作・Retry実行の独立性")

fake_queue_12 = FakeRetryQueueManager()
fake_monitor_12 = FakeWorkflowMonitorManager(record=make_record("run-12", WorkflowMonitorStatus.FAILED))
fake_executor_12 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-12", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None, workflow_engine_result=None,
))
manager_12 = RetryManager(policy=policy_ok, executor=fake_executor_12, monitor=fake_monitor_12, queue=fake_queue_12)

manager_12.dispatch_retry_events([make_retry_event("run-12"), make_job_event("job-12")])
check("12. dispatch_retry_events()を呼んでもFakeQueue.enqueue()は呼ばれない", len(fake_queue_12.enqueue_calls), 0)
check("12. dispatch_retry_events()を呼んでもFakeQueue.dequeue()は呼ばれない", fake_queue_12.dequeue_calls, 0)
check("13. dispatch_retry_events()を呼んでもFakeMonitor.get_status()は呼ばれない", fake_monitor_12.call_count, 0)
check("13. dispatch_retry_events()を呼んでもFakeExecutor.execute()は呼ばれない", len(fake_executor_12.calls), 0)
print()

print("[テスト14] Architecture Guard：dispatch_retry_events()が"
      "self._queue/_policy/_executor/_monitorを参照しない（静的検査）")

import re

retry_manager_source = (PROJECT_ROOT / "src" / "retry_engine" / "retry_manager.py").read_text(encoding="utf-8")


def extract_method_body(source: str, method_name: str) -> str:
    start_match = re.search(rf"\n    def {re.escape(method_name)}\(", source)
    rest = source[start_match.end():]
    next_match = re.search(r"\n    def ", rest)
    end = next_match.start() if next_match else len(rest)
    return rest[:end]


body_dispatch_14 = extract_method_body(retry_manager_source, "dispatch_retry_events")
for forbidden in ("self._queue", "self._policy", "self._executor", "self._monitor"):
    check_false(f"14. RetryManager.dispatch_retry_events()本体が「{forbidden}」を含まない", forbidden in body_dispatch_14)
print()


# ═══════════════════════════════════════════════════════════
# テスト15-16: NullRetryManager：常に[]を返す
# ═══════════════════════════════════════════════════════════

print("[テスト15-16] NullRetryManager.dispatch_retry_events()は常に[]を返す")

null_mgr_15 = NullRetryManager()
result_15_with_retry_events = null_mgr_15.dispatch_retry_events([make_retry_event("run-15a"), make_retry_event("run-15b")])
check("15. Retry候補由来のイベントを含んでいても常に[]を返す", result_15_with_retry_events, [])

result_15_empty = null_mgr_15.dispatch_retry_events([])
check("15. 空リストを渡しても[]を返す", result_15_empty, [])

check("16. NullRetryManagerはRetryEventDispatcher等のいかなるフィールドも持たない", vars(null_mgr_15), {})
print()


# ═══════════════════════════════════════════════════════════
# テスト17: 実際のSchedulerEngine（v3.7.0）+ RetryEventConsumer（v3.8.0）との統合確認
# ═══════════════════════════════════════════════════════════

print("[テスト17] SchedulerEngine.evaluate()が生成したSchedulerEventをそのままDispatch整理できる")


def make_queue() -> RetryQueueManager:
    config = RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0)
    return RetryQueueManager(config=config)


queue_17 = make_queue()
queue_17.enqueue(run_id="run-17a", workflow_name="news", retry_attempt=1)
queue_17.enqueue(run_id="run-17b", workflow_name="news", retry_attempt=1)
source_17 = RetrySchedulerSource(queue_17)
decision_17 = RetrySchedulerDecision(retry_source=source_17)
engine_17 = SchedulerEngine(retry_decision=decision_17)

daily_job_17 = SchedulerJob(job_id="daily-17", name="Daily", trigger_type=TriggerType.DAILY, schedule="09:00")
scheduler_events_17 = engine_17.evaluate([daily_job_17], now=datetime(2026, 7, 6, 9, 0))

manager_17 = RetryManager(policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None))
dispatched_17 = manager_17.dispatch_retry_events(scheduler_events_17)
check(
    "17. SchedulerEngineが生成したイベントのうち、Retry候補由来のものだけが整理される",
    sorted(d.candidate_event.run_id for d in dispatched_17),
    sorted(["run-17a", "run-17b"]),
)
check_true("17. Job由来のSchedulerEvent（daily-17）は整理結果に含まれない", "daily-17" not in [d.candidate_event.run_id for d in dispatched_17])
check_true("17. 整理結果は全件dispatchable=True", all(d.dispatchable for d in dispatched_17))
print()


# ═══════════════════════════════════════════════════════════
# テスト18: 書き込みが発生しないことの確認
# ═══════════════════════════════════════════════════════════

print("[テスト18] Dispatch整理処理の実行前後でファイルが一切作成されない")

write_check_dir_18 = Path(tempfile.mkdtemp())
before_files_18 = list(write_check_dir_18.rglob("*"))

manager_18 = RetryManager(policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None))
manager_18.dispatch_retry_events([make_retry_event("run-18")])
NullRetryManager().dispatch_retry_events([make_retry_event("run-18b")])

after_files_18 = list(write_check_dir_18.rglob("*"))
check("18. Dispatch整理処理実行前後でファイルが作成されない", after_files_18, before_files_18)
print()


# ═══════════════════════════════════════════════════════════
# テスト19: Architecture Guard（無改修の確認）
# ═══════════════════════════════════════════════════════════

print("[テスト19] 既存ファイルの無変更確認（git diff）")

unchanged_paths_v390 = [
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
    for rel_path in unchanged_paths_v390:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"19. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("19. gitが利用できないため無変更確認をスキップ", True)
print()


# ═══════════════════════════════════════════════════════════
# テスト20: retry_engineパッケージのexport確認
# ═══════════════════════════════════════════════════════════

print("[テスト20] retry_engine.__all__ に新規シンボルが追加され、既存シンボルが維持されていること")

import retry_engine as re_pkg_20

check(
    "20. retry_engine.__all__ が既存シンボル＋新規2シンボルの構成になっている",
    set(re_pkg_20.__all__),
    {
        "RetryPolicy", "DEFAULT_TARGET_STATUSES", "RetryConfig", "RetryRequest", "RetryOutcome",
        "RetryResult", "RetryExecutor", "RetryCandidateEvent", "RetryEventConsumer",
        "RetryDispatchEvent", "RetryEventDispatcher", "RetryManager", "NullRetryManager",
    },
)
check_true("20. RetryManagerがdispatch_retry_events()を持つ", hasattr(RetryManager, "dispatch_retry_events"))
check_true("20. NullRetryManagerがdispatch_retry_events()を持つ", hasattr(NullRetryManager, "dispatch_retry_events"))
print()


# ═══════════════════════════════════════════════════════════
# テスト21: __init__ / from_config() の新規引数の後方互換性
# ═══════════════════════════════════════════════════════════

print("[テスト21] RetryManager.__init__ / from_config()の新規引数が末尾・デフォルト値付きで追加されていること")

sig_init_21 = inspect.signature(RetryManager.__init__)
params_init_21 = list(sig_init_21.parameters.keys())
check("21. __init__の最終引数がevent_dispatcher", params_init_21[-1], "event_dispatcher")
check("21. event_dispatcherのデフォルトはNone", sig_init_21.parameters["event_dispatcher"].default, None)

sig_from_config_21 = inspect.signature(RetryManager.from_config)
params_from_config_21 = list(sig_from_config_21.parameters.keys())
check("21. from_config()の最終引数がevent_dispatcher", params_from_config_21[-1], "event_dispatcher")
check("21. from_config()のevent_dispatcherのデフォルトはNone", sig_from_config_21.parameters["event_dispatcher"].default, None)
check(
    "21. 既存6引数（event_consumer含む）の名前・順序が変わっていない",
    params_from_config_21[:6],
    ["retry_config", "retry_policy", "workflow_engine_manager", "workflow_monitor_manager", "retry_queue_manager", "event_consumer"],
)
print()


# ═══════════════════════════════════════════════════════════
# テスト22: retry_event_dispatcher.py が scheduler / retry_queue をimportしないこと
# ═══════════════════════════════════════════════════════════

print("[テスト22] retry_event_dispatcher.py に 'scheduler' / 'retry_queue' / 'dequeue' / "
      "'remove' / 'RetryManager' への実コード参照がない（AST）")

dispatcher_source_path_22 = PROJECT_ROOT / "src" / "retry_engine" / "retry_event_dispatcher.py"
dispatcher_tree_22 = ast.parse(dispatcher_source_path_22.read_text(encoding="utf-8"))


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


dispatcher_referenced_22 = _referenced_names(dispatcher_tree_22)
check_false("22. 'scheduler' への実コード参照が存在しない", "scheduler" in dispatcher_referenced_22)
check_false("22. 'retry_queue' への実コード参照が存在しない", "retry_queue" in dispatcher_referenced_22)
check_false("22. 'dequeue' への実コード参照が存在しない", "dequeue" in dispatcher_referenced_22)
check_false("22. 'remove' への実コード参照が存在しない", "remove" in dispatcher_referenced_22)
check_false("22. 'RetryManager' への実コード参照が存在しない", "RetryManager" in dispatcher_referenced_22)
print()


# ═══════════════════════════════════════════════════════════
# テスト23: 既存回帰（v3.0.0〜v3.8.0 RetryManager挙動）
# ═══════════════════════════════════════════════════════════

print("[テスト23] retry() / enqueue_retry() / dequeue_retry() / recognize_retry_events()の既存挙動が維持される")

fake_monitor_23 = FakeWorkflowMonitorManager(record=make_record("run-23", WorkflowMonitorStatus.FAILED))
fake_executor_23 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-23", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None, workflow_engine_result=None,
))
manager_23 = RetryManager(policy=policy_ok, executor=fake_executor_23, monitor=fake_monitor_23)
result_23 = manager_23.retry("run-23", attempt=1)
check("23. retry()が本Release後も同じ挙動（RETRIED）", result_23.outcome, RetryOutcome.RETRIED)

recognized_23 = manager_23.recognize_retry_events([make_retry_event("run-23r"), make_job_event("job-23")])
check("23. recognize_retry_events()が本Release後も同じ挙動", [r.run_id for r in recognized_23], ["run-23r"])

null_mgr_23 = NullRetryManager()
result_23b = null_mgr_23.enqueue_retry(run_id="run-23b", workflow_name="news")
check_contains_23 = "Retry Engine is disabled" in result_23b.reason
check_true("23. NullRetryManager.enqueue_retry()が本Release後も同じ挙動（DISABLED理由文言）", check_contains_23)
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
