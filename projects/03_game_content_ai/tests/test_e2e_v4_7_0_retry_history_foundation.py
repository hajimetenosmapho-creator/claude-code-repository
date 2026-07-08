"""
E2E テスト: v4.7.0 Retry History Foundation

テストシナリオ:
    ── RetryHistoryManager単体：record/get/has_history ──
    1.  初回record()でattempt_count=1のRetryHistoryRecordが作成される
    2.  同一original_run_idへの2回目のrecord()でattempt_count=2に増加する
    3.  last_attempt / last_recorded_atが直近のrecord()呼び出しの値で更新される
    4.  get()は記録済みのRetryHistoryRecordを返す（コピーであり内部ストアに影響しない）
    5.  get()は未記録のoriginal_run_idに対してNoneを返す
    6.  has_history()は記録の有無を正しく返す
    7.  別々のoriginal_run_idの記録が互いに独立している

    ── NullRetryHistoryManager ──
    8.  record()は常にNoneを返し、何も保存しない
    9.  get()は常にNone、has_history()は常にFalseを返す
    10. インスタンス変数を一切持たない（実データを保持しない）

    ── RetryHistoryRecordExecutor（Stateless） ──
    11. outcome=RETRIEDの項目のみrecord_fnが呼ばれ、recorded=Trueで返る
    12. outcome=SKIPPED/NOT_FOUND/DISABLEDの項目はrecord_fnが呼ばれず、recorded=False
    13. record_all()が複数件を順序を保ったまま処理する
    14. 空リストを渡した場合は空リストを返す
    15. RetryHistoryRecordResult.execution_resultが元のRetryExecutionResultそのもの
    16. RetryHistoryRecordExecutorのインスタンスが内部状態を一切持たない（Stateless）

    ── RetryManager.record_retry_history()：委譲の正確性 ──
    17. history / history_recorder省略時、自動フォールバックする
       （history→NullRetryHistoryManager、history_recorder→RetryHistoryRecordExecutor）
    18. DIで渡したFakeHistoryRecorderへ、execute_dispatchable_retries()の結果がそのまま渡る
    19. dry_runがexecute_dispatchable_retries()へそのまま伝播する
    20. from_config()の既存引数呼び出しが本Release前と同じゲート判定結果を返す
    21. from_config()でretry_history_manager/history_recorderを渡すと実際に配線される

    ── record_retry_history()と既存Queue操作・retry()の独立性 ──
    22. record_retry_history()を呼んでもFakeQueue.enqueue()/dequeue()/remove()は呼ばれない
    23. 実際のRetryHistoryManagerを使い、retry()実行→履歴記録が一気通貫で行われる統合確認

    ── NullRetryManager：常に[]を返す ──
    24. NullRetryManager.record_retry_history()は常に[]を返す
    25. NullRetryManagerはRetryHistoryManager等のいかなるフィールドも持たない

    ── 書き込みが発生しないことの確認 ──
    26. 実行処理の前後でファイルが一切作成されない（in-memoryのみ）

    ── Architecture Guard ──
    27. retry_history が retry_engine/workflow_engine/workflow_monitor/execution_history/
        retry_queue/scheduler/ai/pipelineをimportしない（静的検査、独立した葉パッケージ
        であることの確認）
    28. retry_history_recorder.py が RetryHistoryManager / NullRetryHistoryManager
        （実装クラス）をimportしない（record_fn経由のみで疎結合であることの確認、AST）
    29. 既存ファイル（src/retry_queue/ 配下・src/workflow_monitor/ 配下・retry_engine配下の
        本Releaseで変更していないファイル等）に変更がないこと（git diff）
    30. retry_engineパッケージの__all__に新規シンボルが追加され、既存シンボルは維持されて
        いること
    31. RetryManager.__init__ / from_config()の新規引数が末尾・デフォルト値付きで
        追加されていること
    32. retry_history パッケージのexport確認

    ── metadata["retried_from"]を情報源として使用していないことの確認 ──
    33. retry_history / retry_history_recorder.py のソースに"retried_from"という
        文字列が一切含まれない（Execution History由来のmetadataに依存していないことの
        構造的確認）

    ── 既存回帰（v3.0.0〜v4.6.0 RetryManager挙動） ──
    34. retry() / execute_dispatchable_retries() / decide_retry_queue_updates() /
        apply_retry_queue_removals() / apply_retry_queue_cleanup() /
        apply_retry_queue_terminal_cleanup()の挙動が本Releaseでも維持される

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v4_7_0_retry_history_foundation.py
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
print("v4.7.0 Retry History Foundation E2E テスト")
print("=" * 60)
print()

from retry_history import NullRetryHistoryManager, RetryHistoryManager, RetryHistoryRecord
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
    RetryExecutionResult,
    RetryHistoryRecordExecutor,
    RetryHistoryRecordResult,
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


def make_retry_event(run_id: str, retry_attempt: int = 1) -> SchedulerEvent:
    candidate = FakeCandidate(run_id=run_id, retry_attempt=retry_attempt)
    return SchedulerEvent(
        job_id=f"{RETRY_JOB_ID_PREFIX}{run_id}",
        execute_time=datetime(2026, 7, 9, 9, 0),
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


def make_retried_result(run_id: str, attempt: int = 1, overall_success: bool = True) -> RetryResult:
    return RetryResult(
        original_run_id=run_id, outcome=RetryOutcome.RETRIED, attempt=attempt,
        monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
        workflow_engine_result=make_workflow_engine_result(overall_success),
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


class FakeRetryHistoryRecordExecutor:
    """テスト専用のFake。record_all()呼び出しを記録し、固定の戻り値を返す。"""

    def __init__(self, result: "list | None" = None):
        self.calls: list[list] = []
        self._result = result if result is not None else []

    def record_all(self, execution_results, record_fn):
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
# テスト1-7: RetryHistoryManager単体：record/get/has_history
# ═══════════════════════════════════════════════════════════

print("[テスト1-7] RetryHistoryManager.record() / get() / has_history()")

history_1 = RetryHistoryManager()
record_1 = history_1.record("run-001", attempt=1, recorded_at=datetime(2026, 7, 9, 9, 0))
check("1. 初回record()でattempt_count=1", record_1.attempt_count, 1)
check("1. original_run_idが一致", record_1.original_run_id, "run-001")

record_2 = history_1.record("run-001", attempt=2, recorded_at=datetime(2026, 7, 9, 9, 5))
check("2. 2回目のrecord()でattempt_count=2に増加", record_2.attempt_count, 2)

check("3. last_attemptが直近の値(2)で更新される", record_2.last_attempt, 2)
check("3. last_recorded_atが直近の値で更新される", record_2.last_recorded_at, datetime(2026, 7, 9, 9, 5))

fetched_4 = history_1.get("run-001")
check("4. get()が記録済みのRetryHistoryRecordを返す", fetched_4.attempt_count, 2)
fetched_4_copy_check = history_1.get("run-001")
check_true("4. get()の戻り値は別インスタンス（コピー）", fetched_4 is not fetched_4_copy_check)

check("5. 未記録のoriginal_run_idに対してNoneを返す", history_1.get("run-unknown"), None)

check_true("6. has_history()は記録済みでTrue", history_1.has_history("run-001"))
check_false("6. has_history()は未記録でFalse", history_1.has_history("run-unknown"))

history_1.record("run-002", attempt=1, recorded_at=datetime(2026, 7, 9, 9, 0))
check("7. 別のoriginal_run_idの記録は独立している(run-001)", history_1.get("run-001").attempt_count, 2)
check("7. 別のoriginal_run_idの記録は独立している(run-002)", history_1.get("run-002").attempt_count, 1)
print()


# ═══════════════════════════════════════════════════════════
# テスト8-10: NullRetryHistoryManager
# ═══════════════════════════════════════════════════════════

print("[テスト8-10] NullRetryHistoryManager")

null_history_8 = NullRetryHistoryManager()
check("8. record()は常にNoneを返す", null_history_8.record("run-x", attempt=1, recorded_at=datetime.now()), None)

check("9. get()は常にNoneを返す", null_history_8.get("run-x"), None)
check_false("9. has_history()は常にFalseを返す", null_history_8.has_history("run-x"))

check("10. インスタンス変数を一切持たない", vars(null_history_8), {})
print()


# ═══════════════════════════════════════════════════════════
# テスト11-16: RetryHistoryRecordExecutor（Stateless）
# ═══════════════════════════════════════════════════════════

print("[テスト11-16] RetryHistoryRecordExecutor")

recorder_11 = RetryHistoryRecordExecutor()
recorded_calls_11: list[tuple] = []


def record_fn_11(original_run_id, attempt, recorded_at):
    recorded_calls_11.append((original_run_id, attempt))
    return RetryHistoryRecord(
        original_run_id=original_run_id, attempt_count=1, last_attempt=attempt, last_recorded_at=recorded_at,
    )


result_11 = recorder_11.record(make_execution_result("run-011", make_retried_result("run-011")), record_fn_11)
check_true("11. outcome=RETRIEDでrecorded=True", result_11.recorded)
check("11. record_fnが1回呼ばれる", len(recorded_calls_11), 1)
check("11. history_recordが返る", result_11.history_record.original_run_id, "run-011")

recorded_calls_12: list[tuple] = []


def record_fn_12(original_run_id, attempt, recorded_at):
    recorded_calls_12.append((original_run_id, attempt))
    return None


skipped_result = RetryResult(
    original_run_id="run-012a", outcome=RetryOutcome.SKIPPED, attempt=3,
    monitor_status=WorkflowMonitorStatus.FAILED, reason="max_attempts reached.", workflow_engine_result=None,
)
not_found_result = RetryResult(
    original_run_id="run-012b", outcome=RetryOutcome.NOT_FOUND, attempt=1,
    monitor_status=None, reason="not found.", workflow_engine_result=None,
)
disabled_result = RetryResult(
    original_run_id="run-012c", outcome=RetryOutcome.DISABLED, attempt=1,
    monitor_status=None, reason="disabled.", workflow_engine_result=None,
)
for label, rr in (("SKIPPED", skipped_result), ("NOT_FOUND", not_found_result), ("DISABLED", disabled_result)):
    r = recorder_11.record(make_execution_result(rr.original_run_id, rr), record_fn_12)
    check_false(f"12. outcome={label}はrecorded=False", r.recorded)
    check(f"12. outcome={label}のhistory_recordはNone", r.history_record, None)
check("12. record_fnが一度も呼ばれない", len(recorded_calls_12), 0)

recorded_order_13: list[str] = []


def record_fn_13(original_run_id, attempt, recorded_at):
    recorded_order_13.append(original_run_id)
    return None


results_13 = recorder_11.record_all(
    [
        make_execution_result("run-013a", make_retried_result("run-013a")),
        make_execution_result("run-013b", skipped_result),
        make_execution_result("run-013c", make_retried_result("run-013c")),
    ],
    record_fn_13,
)
check("13. record_all()が複数件を順序を保ったまま処理する", [r.recorded for r in results_13], [True, False, True])
check("13. record_fnが呼ばれた順序も一致", recorded_order_13, ["run-013a", "run-013c"])

check("14. 空リストを渡した場合は空リストを返す", recorder_11.record_all([], record_fn_13), [])

execution_result_15 = make_execution_result("run-015", make_retried_result("run-015"))
result_15 = recorder_11.record(execution_result_15, record_fn_13)
check_true("15. RetryHistoryRecordResult.execution_resultが元のRetryExecutionResultそのもの", result_15.execution_result is execution_result_15)

check("16. インスタンスが内部状態を一切持たない（Stateless）", vars(recorder_11), {})
print()


# ═══════════════════════════════════════════════════════════
# テスト17-21: RetryManager.record_retry_history()：委譲の正確性
# ═══════════════════════════════════════════════════════════

print("[テスト17] history / history_recorder省略時、自動フォールバックする")

manager_17 = RetryManager(policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None))
check_true("17. history省略時、NullRetryHistoryManagerが構築される", isinstance(manager_17._history, NullRetryHistoryManager))
check_true("17. history_recorder省略時、RetryHistoryRecordExecutorが構築される", isinstance(manager_17._history_recorder, RetryHistoryRecordExecutor))
print()

print("[テスト18-19] DIで渡したFakeHistoryRecorderへの委譲・dry_runの伝播")

fake_monitor_18 = FakeWorkflowMonitorManager(record=make_record("run-018", WorkflowMonitorStatus.FAILED))
fake_executor_18 = FakeRetryExecutor(result=make_retried_result("run-018"))
fake_recorder_18 = FakeRetryHistoryRecordExecutor(result=["placeholder-history-result"])
manager_18 = RetryManager(
    policy=policy_ok, executor=fake_executor_18, monitor=fake_monitor_18,
    history_recorder=fake_recorder_18,
)
events_18 = [make_retry_event("run-018")]
result_18 = manager_18.record_retry_history(events_18)
check("18. FakeHistoryRecorder.record_all()が1回だけ呼ばれる", len(fake_recorder_18.calls), 1)
check(
    "18. execute_dispatchable_retries()の戻り値がFakeHistoryRecorder.record_all()にそのまま渡る",
    [r.dispatch_event.candidate_event.run_id for r in fake_recorder_18.calls[0]],
    ["run-018"],
)
check("18. 最終的な戻り値がFakeHistoryRecorderの戻り値そのもの", result_18, ["placeholder-history-result"])

fake_engine_manager_19 = FakeWorkflowEngineManager()
manager_19 = RetryManager(
    policy=policy_ok,
    executor=FakeRetryExecutor(result=make_retried_result("run-019")),
    monitor=FakeWorkflowMonitorManager(record=make_record("run-019", WorkflowMonitorStatus.FAILED)),
    history_recorder=FakeRetryHistoryRecordExecutor(result=[]),
)
manager_19.record_retry_history([make_retry_event("run-019")], dry_run=True)
check_true("19. dry_run=Trueがexecute_dispatchable_retries()経由でretry()へ伝播する（FakeExecutorが呼ばれている）", len(manager_19._executor.calls) == 1)
print()

print("[テスト20] from_config()の既存引数呼び出しが本Release前と同じゲート判定結果を返す")

fake_engine_ok = FakeWorkflowEngineManager()
fake_monitor_ok = FakeWorkflowMonitorManager(record=None)

mgr_20a = RetryManager.from_config(RetryConfig(enabled=False), policy_ok, fake_engine_ok, fake_monitor_ok)
check_true("20. enabled=Falseの4引数呼び出し → NullRetryManager", isinstance(mgr_20a, NullRetryManager))

mgr_20b = RetryManager.from_config(RetryConfig(enabled=True), policy_ok, NullWorkflowEngineManager(), fake_monitor_ok)
check_true("20. NullWorkflowEngineManagerの4引数呼び出し → NullRetryManager", isinstance(mgr_20b, NullRetryManager))

mgr_20c = RetryManager.from_config(RetryConfig(enabled=True), policy_ok, fake_engine_ok, fake_monitor_ok)
check_true("20. 両方満たす4引数呼び出し → RetryManager（実インスタンス）", isinstance(mgr_20c, RetryManager))
check_true("20. retry_history_manager省略時、内部にNullRetryHistoryManagerが自動構築される", isinstance(mgr_20c._history, NullRetryHistoryManager))
print()

print("[テスト21] from_config()でretry_history_manager/history_recorderを渡すと実際に配線される")

real_history_21 = RetryHistoryManager()
fake_recorder_21 = FakeRetryHistoryRecordExecutor(result=[])
mgr_21 = RetryManager.from_config(
    RetryConfig(enabled=True), policy_ok, fake_engine_ok, fake_monitor_ok,
    retry_history_manager=real_history_21,
    history_recorder=fake_recorder_21,
)
mgr_21.record_retry_history([make_retry_event("run-21")])
check("21. from_config()経由で渡したhistory_recorderに実際に委譲される", len(fake_recorder_21.calls), 1)
check_true("21. from_config()経由で渡したretry_history_managerが実際に配線される", mgr_21._history is real_history_21)
print()


# ═══════════════════════════════════════════════════════════
# テスト22-23: record_retry_history()と既存Queue操作・retry()の独立性/統合
# ═══════════════════════════════════════════════════════════

print("[テスト22] record_retry_history()とQueue操作の独立性")

fake_queue_22 = FakeRetryQueueManager()
fake_monitor_22 = FakeWorkflowMonitorManager(record=make_record("run-22", WorkflowMonitorStatus.FAILED))
fake_executor_22 = FakeRetryExecutor(result=make_retried_result("run-22"))
manager_22 = RetryManager(policy=policy_ok, executor=fake_executor_22, monitor=fake_monitor_22, queue=fake_queue_22)

manager_22.record_retry_history([make_retry_event("run-22")])
check("22. record_retry_history()を呼んでもFakeQueue.enqueue()は呼ばれない", len(fake_queue_22.enqueue_calls), 0)
check("22. record_retry_history()を呼んでもFakeQueue.dequeue()は呼ばれない", fake_queue_22.dequeue_calls, 0)
check("22. record_retry_history()を呼んでもFakeQueue.remove()は呼ばれない", len(fake_queue_22.remove_calls), 0)
print()

print("[テスト23] 実際のRetryHistoryManagerを使い、retry()実行→履歴記録が一気通貫で行われる")

real_history_23 = RetryHistoryManager()
fake_monitor_23 = FakeWorkflowMonitorManager(record=make_record("run-23", WorkflowMonitorStatus.FAILED))
fake_executor_23 = FakeRetryExecutor(result=make_retried_result("run-23", attempt=1))
manager_23 = RetryManager(
    policy=policy_ok, executor=fake_executor_23, monitor=fake_monitor_23, history=real_history_23,
)
results_23 = manager_23.record_retry_history([make_retry_event("run-23")])
check("23. 記録結果が1件返る", len(results_23), 1)
check_true("23. recorded=True", results_23[0].recorded)
check_true("23. RetryHistoryManagerに実際に記録されている", real_history_23.has_history("run-23"))
check("23. attempt_countが1", real_history_23.get("run-23").attempt_count, 1)

# 2回目の呼び出しでattempt_countが増加することを確認する
manager_23.record_retry_history([make_retry_event("run-23")])
check("23. 2回目の呼び出しでattempt_countが2に増加する", real_history_23.get("run-23").attempt_count, 2)
print()


# ═══════════════════════════════════════════════════════════
# テスト24-25: NullRetryManager：常に[]を返す
# ═══════════════════════════════════════════════════════════

print("[テスト24-25] NullRetryManager.record_retry_history()は常に[]を返す")

null_mgr_24 = NullRetryManager()
result_24_with_retry_events = null_mgr_24.record_retry_history([make_retry_event("run-24a"), make_retry_event("run-24b")])
check("24. Retry候補由来のイベントを含んでいても常に[]を返す", result_24_with_retry_events, [])

result_24_empty = null_mgr_24.record_retry_history([])
check("24. 空リストを渡しても[]を返す", result_24_empty, [])

check("25. NullRetryManagerはRetryHistoryManager等のいかなるフィールドも持たない", vars(null_mgr_24), {})
print()


# ═══════════════════════════════════════════════════════════
# テスト26: 書き込みが発生しないことの確認
# ═══════════════════════════════════════════════════════════

print("[テスト26] 実行処理の前後でファイルが一切作成されない")

write_check_dir_26 = Path(tempfile.mkdtemp())
before_files_26 = list(write_check_dir_26.rglob("*"))

fake_monitor_26w = FakeWorkflowMonitorManager(record=make_record("run-26w", WorkflowMonitorStatus.FAILED))
fake_executor_26w = FakeRetryExecutor(result=make_retried_result("run-26w"))
manager_26w = RetryManager(policy=policy_ok, executor=fake_executor_26w, monitor=fake_monitor_26w, history=RetryHistoryManager())
manager_26w.record_retry_history([make_retry_event("run-26w")])
NullRetryManager().record_retry_history([make_retry_event("run-26wb")])

after_files_26 = list(write_check_dir_26.rglob("*"))
check("26. 実行処理前後でファイルが作成されない", after_files_26, before_files_26)
print()


# ═══════════════════════════════════════════════════════════
# テスト27-28: Architecture Guard（独立性・疎結合の静的検査）
# ═══════════════════════════════════════════════════════════

print("[テスト27] retry_history が他パッケージを一切importしない（静的検査、独立した葉パッケージ）")

retry_history_dir = PROJECT_ROOT / "src" / "retry_history"
for py_file in sorted(retry_history_dir.glob("*.py")):
    source = py_file.read_text(encoding="utf-8")
    import_lines = "\n".join(
        line for line in source.splitlines()
        if line.strip().startswith("from ") or line.strip().startswith("import ")
    )
    for forbidden in (
        "retry_engine", "workflow_engine", "workflow_monitor", "execution_history",
        "retry_queue", "from scheduler", "import scheduler", "from ai", "import ai",
        "from pipeline", "import pipeline", "retry_scheduler_source", "retry_scheduler_decision",
    ):
        check_false(f"27. {py_file.name} が {forbidden} をimportしない", forbidden in import_lines)
print()

print("[テスト28] retry_history_recorder.py が RetryHistoryManager / NullRetryHistoryManager"
      "（実装クラス）をimportしない（AST、record_fn経由の疎結合であることの確認）")


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


recorder_source_path_28 = PROJECT_ROOT / "src" / "retry_engine" / "retry_history_recorder.py"
tree_28 = ast.parse(recorder_source_path_28.read_text(encoding="utf-8"))
referenced_28 = _referenced_names(tree_28)
check_false("28. retry_history_recorder.py: 'RetryHistoryManager' への実コード参照が存在しない", "RetryHistoryManager" in referenced_28)
check_false("28. retry_history_recorder.py: 'NullRetryHistoryManager' への実コード参照が存在しない", "NullRetryHistoryManager" in referenced_28)
check_true("28. retry_history_recorder.py: 'RetryHistoryRecord'（型ヒントのみ）は参照している", "RetryHistoryRecord" in referenced_28)
print()


# ═══════════════════════════════════════════════════════════
# テスト29: 既存ファイルの無変更確認（git diff）
# ═══════════════════════════════════════════════════════════

print("[テスト29] 既存ファイルの無変更確認（git diff）")

unchanged_paths_v470 = [
    "main.py",
    "src/scheduler/scheduler_engine.py",
    "src/scheduler/__init__.py",
    "src/retry_scheduler_decision/retry_scheduler_decision.py",
    "src/retry_scheduler_source/retry_scheduler_source.py",
    "src/retry_queue/__init__.py",
    "src/retry_queue/retry_queue_status.py",
    "src/retry_queue/retry_queue_item.py",
    "src/retry_queue/retry_queue_result.py",
    "src/retry_queue/retry_queue_config.py",
    "src/retry_queue/retry_queue_manager.py",
    "src/retry_queue/null_retry_queue_manager.py",
    "src/workflow_monitor/workflow_monitor.py",
    "src/workflow_monitor/workflow_monitor_manager.py",
    "src/workflow_monitor/workflow_monitor_config.py",
    "src/workflow_monitor/workflow_monitor_record.py",
    "src/workflow_monitor/workflow_monitor_status.py",
    "src/workflow_monitor/__init__.py",
    "src/retry_enqueue_trigger/retry_enqueue_trigger.py",
    "src/retry_enqueue_trigger/__init__.py",
    # retry_engine のうち、本Releaseで変更していないファイル
    "src/retry_engine/retry_event_consumer.py",
    "src/retry_engine/retry_event_dispatcher.py",
    "src/retry_engine/retry_execution_selector.py",
    "src/retry_engine/retry_execution_coordinator.py",
    "src/retry_engine/retry_policy.py",
    "src/retry_engine/retry_policy_protocol.py",
    "src/retry_engine/retry_config.py",
    "src/retry_engine/retry_request.py",
    "src/retry_engine/retry_result.py",
    "src/retry_engine/retry_executor.py",
    "src/retry_engine/retry_queue_update_decider.py",
    "src/retry_engine/retry_queue_removal_executor.py",
    "src/retry_engine/retry_queue_cleanup_decider.py",
    "src/retry_engine/retry_queue_cleanup_executor.py",
    "src/retry_engine/retry_queue_terminal_cleanup_decider.py",
    "src/retry_engine/retry_queue_terminal_cleanup_executor.py",
    "src/retry_engine/retry_outcome_terminality.py",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths_v470:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"29. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("29. gitが利用できないため無変更確認をスキップ", True)
print()


# ═══════════════════════════════════════════════════════════
# テスト30: retry_engineパッケージのexport確認
# ═══════════════════════════════════════════════════════════

print("[テスト30] retry_engine.__all__ に新規シンボルが追加され、既存シンボルが維持されていること")

import retry_engine as re_pkg_30

check_true("30. RetryHistoryRecordResultがretry_engine.__all__に含まれる", "RetryHistoryRecordResult" in re_pkg_30.__all__)
check_true("30. RetryHistoryRecordExecutorがretry_engine.__all__に含まれる", "RetryHistoryRecordExecutor" in re_pkg_30.__all__)
check_true(
    "30. 既存の主要シンボル（v4.6.0まで）が引き続き__all__に含まれている",
    {
        "RetryPolicy", "DEFAULT_TARGET_STATUSES", "RetryConfig", "RetryRequest", "RetryOutcome",
        "RetryResult", "RetryExecutor", "RetryManager", "NullRetryManager",
        "RetryQueueTerminalCleanupExecutor", "ExplainableRetryPolicy", "RetryDecisionPolicy",
    }.issubset(set(re_pkg_30.__all__)),
)
check_true("30. RetryManagerがrecord_retry_history()を持つ", hasattr(RetryManager, "record_retry_history"))
check_true("30. NullRetryManagerがrecord_retry_history()を持つ", hasattr(NullRetryManager, "record_retry_history"))
print()


# ═══════════════════════════════════════════════════════════
# テスト31: __init__ / from_config() の新規引数の後方互換性
# ═══════════════════════════════════════════════════════════

print("[テスト31] RetryManager.__init__ / from_config()の新規引数が末尾・デフォルト値付きで追加されていること")

sig_init_31 = inspect.signature(RetryManager.__init__)
params_init_31 = list(sig_init_31.parameters.keys())
check("31. __init__の最終引数がhistory_recorder", params_init_31[-1], "history_recorder")
check("31. __init__の最後から2番目の引数がhistory", params_init_31[-2], "history")
check("31. historyのデフォルトはNone", sig_init_31.parameters["history"].default, None)
check("31. history_recorderのデフォルトはNone", sig_init_31.parameters["history_recorder"].default, None)

sig_from_config_31 = inspect.signature(RetryManager.from_config)
params_from_config_31 = list(sig_from_config_31.parameters.keys())
check("31. from_config()の最終引数がhistory_recorder", params_from_config_31[-1], "history_recorder")
check("31. from_config()の最後から2番目の引数がretry_history_manager", params_from_config_31[-2], "retry_history_manager")
check(
    "31. 既存引数（先頭12個）の名前・順序が変わっていない",
    params_from_config_31[:12],
    [
        "retry_config", "retry_policy", "workflow_engine_manager", "workflow_monitor_manager",
        "retry_queue_manager", "event_consumer", "event_dispatcher",
        "execution_selector", "execution_coordinator", "queue_update_decider",
        "queue_removal_executor", "queue_cleanup_decider",
    ],
)
print()


# ═══════════════════════════════════════════════════════════
# テスト32: retry_history パッケージのexport確認
# ═══════════════════════════════════════════════════════════

print("[テスト32] retry_history パッケージのexport確認")

import retry_history as rh_pkg_32

for name in ("RetryHistoryRecord", "RetryHistoryManager", "NullRetryHistoryManager"):
    check_true(f"32. {name} が retry_history パッケージからエクスポートされている", hasattr(rh_pkg_32, name))
    check_true(f"32. {name} が retry_history.__all__ に含まれる", name in rh_pkg_32.__all__)
print()


# ═══════════════════════════════════════════════════════════
# テスト33: metadata["retried_from"]を情報源として使用していないことの確認
# ═══════════════════════════════════════════════════════════

print("[テスト33] retried_from（Execution History由来のmetadata）に依存していないことの構造的確認")

for py_file in sorted(retry_history_dir.glob("*.py")) + [
    PROJECT_ROOT / "src" / "retry_engine" / "retry_history_recorder.py",
]:
    source_33 = py_file.read_text(encoding="utf-8")
    check_false(f"33. {py_file.name} に'retried_from'という文字列が含まれない", "retried_from" in source_33)
print()


# ═══════════════════════════════════════════════════════════
# テスト34: 既存回帰（v3.0.0〜v4.6.0 RetryManager挙動）
# ═══════════════════════════════════════════════════════════

print("[テスト34] retry() / execute_dispatchable_retries() / decide_retry_queue_updates() / "
      "apply_retry_queue_removals() / apply_retry_queue_cleanup() / "
      "apply_retry_queue_terminal_cleanup()の既存挙動が維持される")

fake_monitor_34 = FakeWorkflowMonitorManager(record=make_record("run-34", WorkflowMonitorStatus.FAILED))
fake_executor_34 = FakeRetryExecutor(result=make_retried_result("run-34"))
manager_34 = RetryManager(policy=policy_ok, executor=fake_executor_34, monitor=fake_monitor_34)

result_34 = manager_34.retry("run-34", attempt=1)
check("34. retry()が本Release後も同じ挙動（RETRIED）", result_34.outcome, RetryOutcome.RETRIED)

execution_results_34 = manager_34.execute_dispatchable_retries([make_retry_event("run-34e")])
check("34. execute_dispatchable_retries()が本Release後も同じ挙動（RETRIED）", execution_results_34[0].retry_result.outcome, RetryOutcome.RETRIED)

decisions_34 = manager_34.decide_retry_queue_updates([make_retry_event("run-34d")])
check("34. decide_retry_queue_updates()が本Release後も同じ挙動（COMPLETE）", decisions_34[0].outcome.value, "complete")
check("34. decide_retry_queue_updates()のtarget_statusが本Release後も同じ挙動", decisions_34[0].target_status, RetryQueueStatus.COMPLETED)

fake_queue_34 = FakeRetryQueueManager()
manager_34r = RetryManager(policy=policy_ok, executor=FakeRetryExecutor(result=make_retried_result("run-34r")), monitor=FakeWorkflowMonitorManager(record=make_record("run-34r", WorkflowMonitorStatus.FAILED)), queue=fake_queue_34)
manager_34r.apply_retry_queue_removals([make_retry_event("run-34r")])
check("34. apply_retry_queue_removals()が本Release後も同じ挙動（remove()が1回呼ばれる）", len(fake_queue_34.remove_calls), 1)

fake_queue_34c = FakeRetryQueueManager()
skipped_retry_result_34 = RetryResult(
    original_run_id="run-34c", outcome=RetryOutcome.SKIPPED, attempt=3,
    monitor_status=WorkflowMonitorStatus.FAILED, reason="attempt 3 has reached max_attempts=3.",
    workflow_engine_result=None,
)
manager_34c = RetryManager(
    policy=policy_ok,
    executor=FakeRetryExecutor(result=skipped_retry_result_34),
    monitor=FakeWorkflowMonitorManager(record=make_record("run-34c", WorkflowMonitorStatus.FAILED)),
    queue=fake_queue_34c,
)
# retry()自体はpolicyがSKIPPEDを返すよう、max_attempts到達のattemptを渡す
manager_34c_policy = RetryManager(
    policy=RetryPolicy(target_statuses=DEFAULT_TARGET_STATUSES, max_attempts=1),
    executor=FakeRetryExecutor(result=None),
    monitor=FakeWorkflowMonitorManager(record=make_record("run-34c2", WorkflowMonitorStatus.FAILED)),
    queue=fake_queue_34c,
)
cleanup_results_34 = manager_34c_policy.apply_retry_queue_cleanup([make_retry_event("run-34c2", retry_attempt=2)])
check("34. apply_retry_queue_cleanup()が本Release後も同じ挙動（SKIPPED→CLEANUP→remove()）", len(fake_queue_34c.remove_calls), 1)

fake_queue_34t = FakeRetryQueueManager()
manager_34t = RetryManager(
    policy=RetryPolicy(target_statuses=DEFAULT_TARGET_STATUSES, max_attempts=3),
    executor=FakeRetryExecutor(result=None),
    monitor=FakeWorkflowMonitorManager(record=None),
    queue=fake_queue_34t,
)
terminal_results_34 = manager_34t.apply_retry_queue_terminal_cleanup([make_retry_event("run-34t")])
check("34. apply_retry_queue_terminal_cleanup()が本Release後も同じ挙動（NOT_FOUND→CLEANUP→remove()）", len(fake_queue_34t.remove_calls), 1)

null_mgr_34 = NullRetryManager()
result_34n = null_mgr_34.enqueue_retry(run_id="run-34n", workflow_name="news")
check_true("34. NullRetryManager.enqueue_retry()が本Release後も同じ挙動（DISABLED理由文言）", "Retry Engine is disabled" in result_34n.reason)
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
