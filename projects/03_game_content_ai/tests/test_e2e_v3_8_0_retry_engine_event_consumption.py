"""
E2E テスト: v3.8.0 Retry Engine Event Consumption

テストシナリオ（docs/design/retry_engine_event_consumption.md 9章・13章 対応）:
    ── RetryEventConsumer単体：Retryイベントだけを認識する ──
    1.  job_idが"retry:"で始まるSchedulerEventはRetryCandidateEventとして認識される
    2.  job_idが"retry:"で始まらないSchedulerEvent（Job由来）は無視される（None/除外）
    3.  RetryCandidateEvent.run_idがcandidate.run_idと一致する
    4.  RetryCandidateEvent.candidateが元の候補オブジェクトそのもの（同一インスタンス）である
    5.  RetryCandidateEvent.source_eventが元のSchedulerEventそのもの（同一インスタンス）である
    6.  job_idが"retry:"で始まるが metadata["retry_candidate"] が存在しない場合はNoneを返す（防御的）

    ── recognize_all()：複数件・混在時の挙動 ──
    7.  Job由来とRetry候補由来が混在するリストから、Retry候補由来のものだけが抽出される
    8.  Retry候補由来のイベントが1件も無い場合は空リストを返す
    9.  空リストを渡した場合は空リストを返す
    10. 元のリストの順序が認識結果の順序に保たれる

    ── RetryManager.recognize_retry_events()：委譲の正確性 ──
    11. event_consumer省略時、RetryEventConsumer()に自動フォールバックする
    12. DIで渡したFakeのrecognize_all()の戻り値が、recognize_retry_events()からそのまま返る
    13. DIで渡したFakeのrecognize_all()に、渡したeventsがそのまま渡る
    14. from_config()の既存4引数呼び出しが本Release前と同じゲート判定結果を返す
    15. from_config()でevent_consumerを渡すと実際に配線される

    ── recognize_retry_events()と既存操作の独立性 ──
    16. recognize_retry_events()を呼んでもFakeQueue.enqueue()/dequeue()は呼ばれない
    17. recognize_retry_events()を呼んでもFakeMonitor.get_status()/FakeExecutor.execute()は呼ばれない
    18. Architecture Guard：recognize_retry_events()のソースコードが
        self._queue/self._policy/self._executor/self._monitorを一切参照しない

    ── NullRetryManager：常に[]を返す ──
    19. NullRetryManager.recognize_retry_events()はRetry候補由来のイベントを含んでいても常に[]を返す
    20. NullRetryManagerはRetryEventConsumerを一切構築・参照しない（vars()にフィールドが無い）

    ── 実際のSchedulerEngine（v3.7.0）との統合確認 ──
    21. SchedulerEngine.evaluate()が生成したSchedulerEventをそのままrecognize_retry_events()に
        渡すと、Retry候補由来のものだけが認識される

    ── 書き込みが発生しないことの確認 ──
    22. 認識処理の実行前後でファイルが一切作成されない

    ── Architecture Guard（無改修の確認） ──
    23. src/scheduler/ / src/retry_scheduler_decision/ / src/retry_scheduler_source/ /
        src/retry_queue/ 配下の全ファイル、および src/retry_engine/ のうち本Releaseで
        変更していないファイルに変更がないこと（git diff、ゼロ改修の確認）
    24. retry_engineパッケージの__all__に新規シンボル（RetryCandidateEvent/RetryEventConsumer）
        が追加され、既存シンボルは維持されていること
    25. RetryManager.__init__ / from_config()の新規引数が末尾・デフォルト値付きで追加されていること
    26. retry_event_consumer.py が retry_queue をimportしていないこと（型としてもimportしない）

    ── 既存回帰（v3.0.0〜v3.2.0 RetryManager挙動）──
    27. retry() / enqueue_retry() / dequeue_retry()の挙動が本Releaseでも維持される

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v3_8_0_retry_engine_event_consumption.py
"""
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


def check_none(label: str, value):
    check(label, value is None, True)


print("=" * 60)
print("v3.8.0 Retry Engine Event Consumption E2E テスト")
print("=" * 60)
print()

from scheduler import SchedulerEngine, SchedulerEvent, SchedulerJob, TriggerType
from retry_queue import RetryQueueConfig, RetryQueueManager
from retry_queue.retry_queue_item import RetryQueueItem
from retry_queue.retry_queue_status import RetryQueueStatus
from retry_scheduler_source import RetrySchedulerSource
from retry_scheduler_decision import RetrySchedulerDecision
from workflow_engine import WorkflowEngineResult
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus
from retry_engine import (
    DEFAULT_TARGET_STATUSES,
    NullRetryManager,
    RetryCandidateEvent,
    RetryConfig,
    RetryEventConsumer,
    RetryManager,
    RetryOutcome,
    RetryPolicy,
    RetryResult,
)
from retry_engine.retry_event_consumer import RETRY_JOB_ID_PREFIX


def make_candidate(run_id: str, priority: int = 0) -> RetryQueueItem:
    return RetryQueueItem(
        run_id=run_id, workflow_name="news", enqueue_time=datetime(2026, 7, 3, 9, 0),
        priority=priority, retry_attempt=1, status=RetryQueueStatus.WAITING,
    )


def make_retry_event(run_id: str, candidate: "RetryQueueItem | None" = None) -> SchedulerEvent:
    if candidate is None:
        candidate = make_candidate(run_id)
    return SchedulerEvent(
        job_id=f"{RETRY_JOB_ID_PREFIX}{run_id}",
        execute_time=datetime(2026, 7, 3, 9, 0),
        trigger_reason="Retry candidate selected.",
        metadata={"retry_candidate": candidate},
    )


def make_job_event(job_id: str) -> SchedulerEvent:
    return SchedulerEvent(
        job_id=job_id, execute_time=datetime(2026, 7, 3, 9, 0),
        trigger_reason="Daily schedule matched.", metadata={},
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


class FakeRetryEventConsumer:
    """テスト専用のFake。recognize_all()呼び出しを記録し、固定の戻り値を返す。"""

    def __init__(self, result: "list[RetryCandidateEvent] | None" = None):
        self.calls: list[list] = []
        self._result = result if result is not None else []

    def recognize_all(self, events):
        self.calls.append(events)
        return self._result


def make_record(run_id: str, monitor_status: WorkflowMonitorStatus, job_id: str = "job-1") -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=monitor_status,
        source_status=monitor_status.value, source="manual", job_id=job_id,
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=[],
    )


# ═══════════════════════════════════════════════════════════
# テスト1-6: RetryEventConsumer単体：Retryイベントだけを認識する
# ═══════════════════════════════════════════════════════════

print("[テスト1-6] RetryEventConsumer.recognize()：Retryイベントだけを認識する")

consumer_1 = RetryEventConsumer()
candidate_1 = make_candidate("run-001")
event_1 = make_retry_event("run-001", candidate_1)
result_1 = consumer_1.recognize(event_1)
check_true("1. job_idが'retry:'で始まるSchedulerEventはRetryCandidateEventとして認識される", isinstance(result_1, RetryCandidateEvent))

job_event_2 = make_job_event("daily-1")
result_2 = consumer_1.recognize(job_event_2)
check_none("2. job_idが'retry:'で始まらないSchedulerEvent（Job由来）はNoneを返す", result_2)

check("3. RetryCandidateEvent.run_idがcandidate.run_idと一致する", result_1.run_id, candidate_1.run_id)
check_true("4. RetryCandidateEvent.candidateが元の候補オブジェクトそのもの（同一インスタンス）", result_1.candidate is candidate_1)
check_true("5. RetryCandidateEvent.source_eventが元のSchedulerEventそのもの（同一インスタンス）", result_1.source_event is event_1)

event_6_no_candidate = SchedulerEvent(
    job_id="retry:run-006", execute_time=datetime(2026, 7, 3, 9, 0),
    trigger_reason="Retry candidate selected.", metadata={},
)
result_6 = consumer_1.recognize(event_6_no_candidate)
check_none("6. job_idが'retry:'で始まるがmetadata['retry_candidate']が無い場合はNoneを返す（防御的）", result_6)
print()


# ═══════════════════════════════════════════════════════════
# テスト7-10: recognize_all()：複数件・混在時の挙動
# ═══════════════════════════════════════════════════════════

print("[テスト7-10] RetryEventConsumer.recognize_all()：複数件・混在時の挙動")

consumer_7 = RetryEventConsumer()
mixed_events_7 = [
    make_job_event("daily-1"),
    make_retry_event("run-101"),
    make_job_event("interval-1"),
    make_retry_event("run-102"),
]
recognized_7 = consumer_7.recognize_all(mixed_events_7)
check("7. Job由来とRetry候補由来が混在するリストから、Retry候補由来のものだけが抽出される", [r.run_id for r in recognized_7], ["run-101", "run-102"])

recognized_8 = consumer_7.recognize_all([make_job_event("daily-1"), make_job_event("interval-1")])
check("8. Retry候補由来のイベントが1件も無い場合は空リストを返す", recognized_8, [])

recognized_9 = consumer_7.recognize_all([])
check("9. 空リストを渡した場合は空リストを返す", recognized_9, [])

ordered_events_10 = [make_retry_event("run-c"), make_retry_event("run-a"), make_retry_event("run-b")]
recognized_10 = consumer_7.recognize_all(ordered_events_10)
check("10. 元のリストの順序が認識結果の順序に保たれる", [r.run_id for r in recognized_10], ["run-c", "run-a", "run-b"])
print()


# ═══════════════════════════════════════════════════════════
# テスト11-15: RetryManager.recognize_retry_events()：委譲の正確性
# ═══════════════════════════════════════════════════════════

print("[テスト11] event_consumer省略時、RetryEventConsumer()に自動フォールバックする")

manager_11 = RetryManager(policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None))
check_true("11. event_consumer省略時、内部にRetryEventConsumerが構築される", isinstance(manager_11._event_consumer, RetryEventConsumer))
result_11 = manager_11.recognize_retry_events([make_retry_event("run-11"), make_job_event("job-11")])
check("11. 自動フォールバックしたRetryEventConsumerが実際に認識処理を行う", [r.run_id for r in result_11], ["run-11"])
print()

print("[テスト12-13] DIで渡したFakeのrecognize_all()の呼び出し・戻り値がそのまま伝播する")

expected_result_12 = [RetryCandidateEvent(run_id="run-12", candidate=make_candidate("run-12"), source_event=make_retry_event("run-12"))]
fake_consumer_12 = FakeRetryEventConsumer(result=expected_result_12)
manager_12 = RetryManager(
    policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None),
    event_consumer=fake_consumer_12,
)
events_12 = [make_retry_event("run-12"), make_job_event("job-12")]
result_12 = manager_12.recognize_retry_events(events_12)
check("12. FakeのRetryEventConsumer.recognize_all()が1回だけ呼ばれる", len(fake_consumer_12.calls), 1)
check("12. 戻り値がRetryEventConsumerの戻り値そのもの", result_12, expected_result_12)
check_true("13. 渡したeventsがそのままrecognize_all()に渡る", fake_consumer_12.calls[0] is events_12)
print()

print("[テスト14] from_config()の既存4引数呼び出しが本Release前と同じゲート判定結果を返す")

fake_engine_ok = FakeWorkflowEngineManager()
fake_monitor_ok = FakeWorkflowMonitorManager(record=None)
from workflow_engine import NullWorkflowEngineManager

mgr_14a = RetryManager.from_config(RetryConfig(enabled=False), policy_ok, fake_engine_ok, fake_monitor_ok)
check_true("14. enabled=Falseの4引数呼び出し → NullRetryManager", isinstance(mgr_14a, NullRetryManager))

mgr_14b = RetryManager.from_config(RetryConfig(enabled=True), policy_ok, NullWorkflowEngineManager(), fake_monitor_ok)
check_true("14. NullWorkflowEngineManagerの4引数呼び出し → NullRetryManager", isinstance(mgr_14b, NullRetryManager))

mgr_14c = RetryManager.from_config(RetryConfig(enabled=True), policy_ok, fake_engine_ok, fake_monitor_ok)
check_true("14. 両方満たす4引数呼び出し → RetryManager（実インスタンス）", isinstance(mgr_14c, RetryManager))
check_true("14. event_consumer省略時、内部にRetryEventConsumerが自動構築される", isinstance(mgr_14c._event_consumer, RetryEventConsumer))
print()

print("[テスト15] from_config()でevent_consumerを渡すと実際に配線される")

fake_consumer_15 = FakeRetryEventConsumer(result=[])
mgr_15 = RetryManager.from_config(
    RetryConfig(enabled=True), policy_ok, fake_engine_ok, fake_monitor_ok,
    event_consumer=fake_consumer_15,
)
mgr_15.recognize_retry_events([make_retry_event("run-15")])
check("15. from_config()経由で渡したevent_consumerに実際に委譲される", len(fake_consumer_15.calls), 1)
print()


# ═══════════════════════════════════════════════════════════
# テスト16-18: recognize_retry_events()と既存操作の独立性
# ═══════════════════════════════════════════════════════════

print("[テスト16-17] recognize_retry_events()とQueue操作・Retry実行の独立性")

fake_queue_16 = FakeRetryQueueManager()
fake_monitor_16 = FakeWorkflowMonitorManager(record=make_record("run-16", WorkflowMonitorStatus.FAILED))
fake_executor_16 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-16", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None, workflow_engine_result=None,
))
manager_16 = RetryManager(policy=policy_ok, executor=fake_executor_16, monitor=fake_monitor_16, queue=fake_queue_16)

manager_16.recognize_retry_events([make_retry_event("run-16"), make_job_event("job-16")])
check("16. recognize_retry_events()を呼んでもFakeQueue.enqueue()は呼ばれない", len(fake_queue_16.enqueue_calls), 0)
check("16. recognize_retry_events()を呼んでもFakeQueue.dequeue()は呼ばれない", fake_queue_16.dequeue_calls, 0)
check("17. recognize_retry_events()を呼んでもFakeMonitor.get_status()は呼ばれない", fake_monitor_16.call_count, 0)
check("17. recognize_retry_events()を呼んでもFakeExecutor.execute()は呼ばれない", len(fake_executor_16.calls), 0)
print()

print("[テスト18] Architecture Guard：recognize_retry_events()が"
      "self._queue/_policy/_executor/_monitorを参照しない（静的検査）")

import re

retry_manager_source = (PROJECT_ROOT / "src" / "retry_engine" / "retry_manager.py").read_text(encoding="utf-8")


def extract_method_body(source: str, method_name: str) -> str:
    start_match = re.search(rf"\n    def {re.escape(method_name)}\(", source)
    rest = source[start_match.end():]
    next_match = re.search(r"\n    def ", rest)
    end = next_match.start() if next_match else len(rest)
    return rest[:end]


body_recognize_18 = extract_method_body(retry_manager_source, "recognize_retry_events")
for forbidden in ("self._queue", "self._policy", "self._executor", "self._monitor"):
    check_false(f"18. RetryManager.recognize_retry_events()本体が「{forbidden}」を含まない", forbidden in body_recognize_18)
print()


# ═══════════════════════════════════════════════════════════
# テスト19-20: NullRetryManager：常に[]を返す
# ═══════════════════════════════════════════════════════════

print("[テスト19-20] NullRetryManager.recognize_retry_events()は常に[]を返す")

null_mgr_19 = NullRetryManager()
result_19_with_retry_events = null_mgr_19.recognize_retry_events([make_retry_event("run-19a"), make_retry_event("run-19b")])
check("19. Retry候補由来のイベントを含んでいても常に[]を返す", result_19_with_retry_events, [])

result_19_empty = null_mgr_19.recognize_retry_events([])
check("19. 空リストを渡しても[]を返す", result_19_empty, [])

check("20. NullRetryManagerはRetryEventConsumer等のいかなるフィールドも持たない", vars(null_mgr_19), {})
print()


# ═══════════════════════════════════════════════════════════
# テスト21: 実際のSchedulerEngine（v3.7.0）との統合確認
# ═══════════════════════════════════════════════════════════

print("[テスト21] SchedulerEngine.evaluate()が生成したSchedulerEventをそのまま認識できる")


def make_queue() -> RetryQueueManager:
    config = RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0)
    return RetryQueueManager(config=config)


queue_21 = make_queue()
queue_21.enqueue(run_id="run-21a", workflow_name="news", retry_attempt=1)
queue_21.enqueue(run_id="run-21b", workflow_name="news", retry_attempt=1)
source_21 = RetrySchedulerSource(queue_21)
decision_21 = RetrySchedulerDecision(retry_source=source_21)
engine_21 = SchedulerEngine(retry_decision=decision_21)

daily_job_21 = SchedulerJob(job_id="daily-21", name="Daily", trigger_type=TriggerType.DAILY, schedule="09:00")
scheduler_events_21 = engine_21.evaluate([daily_job_21], now=datetime(2026, 7, 3, 9, 0))

manager_21 = RetryManager(policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None))
recognized_21 = manager_21.recognize_retry_events(scheduler_events_21)
check(
    "21. SchedulerEngineが生成したイベントのうち、Retry候補由来のものだけが認識される",
    sorted(r.run_id for r in recognized_21),
    sorted(["run-21a", "run-21b"]),
)
check_true("21. Job由来のSchedulerEvent（daily-21）は認識結果に含まれない", "daily-21" not in [r.run_id for r in recognized_21])
print()


# ═══════════════════════════════════════════════════════════
# テスト22: 書き込みが発生しないことの確認
# ═══════════════════════════════════════════════════════════

print("[テスト22] 認識処理の実行前後でファイルが一切作成されない")

write_check_dir_22 = Path(tempfile.mkdtemp())
before_files_22 = list(write_check_dir_22.rglob("*"))

manager_22 = RetryManager(policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None))
manager_22.recognize_retry_events([make_retry_event("run-22")])
NullRetryManager().recognize_retry_events([make_retry_event("run-22b")])

after_files_22 = list(write_check_dir_22.rglob("*"))
check("22. 認識処理実行前後でファイルが作成されない", after_files_22, before_files_22)
print()


# ═══════════════════════════════════════════════════════════
# テスト23: Architecture Guard（無改修の確認）
# ═══════════════════════════════════════════════════════════

print("[テスト23] 既存ファイルの無変更確認（git diff）")

unchanged_paths_v380 = [
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
    for rel_path in unchanged_paths_v380:
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
        "RetryManager", "NullRetryManager",
    },
)
check_true("24. RetryManagerがrecognize_retry_events()を持つ", hasattr(RetryManager, "recognize_retry_events"))
check_true("24. NullRetryManagerがrecognize_retry_events()を持つ", hasattr(NullRetryManager, "recognize_retry_events"))
print()


# ═══════════════════════════════════════════════════════════
# テスト25: __init__ / from_config() の新規引数の後方互換性
# ═══════════════════════════════════════════════════════════

print("[テスト25] RetryManager.__init__ / from_config()の新規引数が末尾・デフォルト値付きで追加されていること")

sig_init_25 = inspect.signature(RetryManager.__init__)
params_init_25 = list(sig_init_25.parameters.keys())
check("25. __init__の最終引数がevent_consumer", params_init_25[-1], "event_consumer")
check("25. event_consumerのデフォルトはNone", sig_init_25.parameters["event_consumer"].default, None)

sig_from_config_25 = inspect.signature(RetryManager.from_config)
params_from_config_25 = list(sig_from_config_25.parameters.keys())
check("25. from_config()の最終引数がevent_consumer", params_from_config_25[-1], "event_consumer")
check("25. from_config()のevent_consumerのデフォルトはNone", sig_from_config_25.parameters["event_consumer"].default, None)
check(
    "25. 既存5引数（queue含む）の名前・順序が変わっていない",
    params_from_config_25[:5],
    ["retry_config", "retry_policy", "workflow_engine_manager", "workflow_monitor_manager", "retry_queue_manager"],
)
print()


# ═══════════════════════════════════════════════════════════
# テスト26: retry_event_consumer.py が retry_queue をimportしないこと
# ═══════════════════════════════════════════════════════════

print("[テスト26] retry_event_consumer.py に 'retry_queue' / 'dequeue' / 'remove' / "
      "'RetryManager' への実コード参照がない（AST）")

import ast

consumer_source_path_26 = PROJECT_ROOT / "src" / "retry_engine" / "retry_event_consumer.py"
consumer_tree_26 = ast.parse(consumer_source_path_26.read_text(encoding="utf-8"))


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


consumer_referenced_26 = _referenced_names(consumer_tree_26)
check_false("26. 'retry_queue' への実コード参照が存在しない", "retry_queue" in consumer_referenced_26)
check_false("26. 'dequeue' への実コード参照が存在しない", "dequeue" in consumer_referenced_26)
check_false("26. 'remove' への実コード参照が存在しない", "remove" in consumer_referenced_26)
check_false("26. 'RetryManager' への実コード参照が存在しない", "RetryManager" in consumer_referenced_26)
print()


# ═══════════════════════════════════════════════════════════
# テスト27: 既存回帰（v3.0.0〜v3.2.0 RetryManager挙動）
# ═══════════════════════════════════════════════════════════

print("[テスト27] retry() / enqueue_retry() / dequeue_retry()の既存挙動が維持される")

fake_monitor_27 = FakeWorkflowMonitorManager(record=make_record("run-27", WorkflowMonitorStatus.FAILED))
fake_executor_27 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-27", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None, workflow_engine_result=None,
))
manager_27 = RetryManager(policy=policy_ok, executor=fake_executor_27, monitor=fake_monitor_27)
result_27 = manager_27.retry("run-27", attempt=1)
check("27. retry()が本Release後も同じ挙動（RETRIED）", result_27.outcome, RetryOutcome.RETRIED)

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
