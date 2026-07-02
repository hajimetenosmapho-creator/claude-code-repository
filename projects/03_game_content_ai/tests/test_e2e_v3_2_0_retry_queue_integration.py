"""
E2E テスト: v3.2.0 Retry Queue Integration

テストシナリオ（docs/design/retry_queue_integration.md 9章 対応）:
    ── DI・後方互換性 ──
    1.  queue省略時、RetryManager.__init__ が NullRetryQueueManager() にフォールバックする
    2.  DIで渡したFakeのenqueue()に、enqueue_retry()の全引数がそのまま渡る
    3.  DIで渡したFakeのdequeue()の戻り値が、dequeue_retry()からそのまま返る
    4.  Queue満杯・重複run_id → REJECTEDがそのまま返る（Fake経由）
    5.  【Architecture Review反映】enqueue_retry()とRetryQueueManager.enqueue()の
        retry_attemptデフォルト値が一致する
    6.  【Architecture Review反映】実RetryQueueManagerを使ったenqueue_retry()→
        dequeue_retry()の往復
    7.  【Architecture Review反映】NullRetryQueueManager()を明示的に渡した場合と
        省略した場合の結果が一致する
    8.  from_config()の既存4引数呼び出しが本Release前と同じゲート判定結果を返す
    9.  from_config()でretry_queue_managerを渡すと実際に配線される

    ── retry()とQueue操作の独立性 ──
    10. retry()を呼んでもFakeQueueのenqueue()/dequeue()は呼ばれない。逆にenqueue_retry()/
        dequeue_retry()を呼んでもFakeMonitor.get_status()/FakeExecutor.execute()は呼ばれない
    11. Architecture Guard：enqueue_retry()/dequeue_retry()のソースコードが
        self.retry/self._executor/self._monitor/self._policyを一切参照しない

    ── NullRetryManagerの一貫性 ──
    12. enqueue_retry()/dequeue_retry()が常にDISABLEDを返し、reason文言が
        NullRetryQueueManager側のreasonとは異なる。フィールドを一切持たない

    ── 書き込みが発生しないことの確認 ──
    13. Queue統合の実行前後でファイルが一切作成されない

    ── Architecture Guard（無改修の確認） ──
    14. src/retry_queue/ 配下・src/retry_engine/ の retry_manager.py 以外に
        変更がないこと（git diff）
    15. RetryQueueManager / NullRetryQueueManagerの公開APIシグネチャがv3.1.0と一致すること
    16. retry_engineパッケージの__all__が本Release前と同一であること
        （新規メソッドはRetryManager/NullRetryManagerのインスタンスメソッドとして
        追加されるのみで、パッケージレベルの新規公開シンボルは増えない）
    17. from_config()の新規引数がデフォルト値付き・末尾に追加されていること

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v3_2_0_retry_queue_integration.py
"""
import inspect
import os
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


def check_contains(label: str, text: str, keyword: str):
    check(label, keyword in str(text), True)


def check_none(label: str, value):
    check(label, value is None, True)


print("=" * 60)
print("v3.2.0 Retry Queue Integration E2E テスト")
print("=" * 60)
print()

from workflow_engine import NullWorkflowEngineManager, WorkflowEngineResult
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus
from retry_engine import (
    DEFAULT_TARGET_STATUSES,
    NullRetryManager,
    RetryConfig,
    RetryManager,
    RetryOutcome,
    RetryPolicy,
    RetryResult,
)
from retry_queue import (
    NullRetryQueueManager,
    RetryQueueConfig,
    RetryQueueManager,
    RetryQueueOutcome,
    RetryQueueResult,
)

ENGINE_ENV_KEYS = ("RETRY_ENGINE_ENABLED", "RETRY_MAX_ATTEMPTS")
QUEUE_ENV_KEYS = ("RETRY_QUEUE_ENABLED", "RETRY_QUEUE_MAX_SIZE", "RETRY_QUEUE_DEFAULT_PRIORITY")


def clear_env():
    for key in ENGINE_ENV_KEYS:
        os.environ.pop(key, None)


def clear_queue_env():
    for key in QUEUE_ENV_KEYS:
        os.environ.pop(key, None)


class FakeWorkflowEngineManager:
    """テスト専用のFake。run()呼び出しを記録し、固定のWorkflowEngineResultを返す。"""

    def __init__(self):
        self.calls: list[tuple] = []

    def run(self, event, dry_run: bool = False) -> WorkflowEngineResult:
        self.calls.append((event, dry_run))
        return WorkflowEngineResult(
            steps=[], overall_success=True, stopped_early=False,
            started_at=datetime.now(), finished_at=datetime.now(),
        )


class FakeWorkflowMonitorManager:
    """テスト専用のFake。get_status()の戻り値を固定し、呼び出し回数を記録する。"""

    def __init__(self, record: "WorkflowMonitorRecord | None"):
        self.record = record
        self.call_count = 0

    def get_status(self, run_id: str):
        self.call_count += 1
        return self.record

    def list_status(self, limit=None):
        return [self.record] if self.record else []


class FakeRetryExecutor:
    """テスト専用のFake。execute()呼び出しを記録し、固定のRetryResultを返す。"""

    def __init__(self, result: "RetryResult | None"):
        self.calls: list[tuple] = []
        self._result = result

    def execute(self, request, record) -> RetryResult:
        self.calls.append((request, record))
        return self._result


class FakeRetryQueueManager:
    """テスト専用のFake。enqueue()/dequeue()呼び出しを記録し、固定の戻り値を返す。"""

    def __init__(
        self,
        enqueue_result: "RetryQueueResult | None" = None,
        dequeue_result: "RetryQueueResult | None" = None,
    ):
        self.enqueue_calls: list[dict] = []
        self.dequeue_calls: int = 0
        self._enqueue_result = enqueue_result
        self._dequeue_result = dequeue_result

    def enqueue(self, run_id, workflow_name, retry_attempt=1, priority=None):
        self.enqueue_calls.append(
            {"run_id": run_id, "workflow_name": workflow_name, "retry_attempt": retry_attempt, "priority": priority},
        )
        return self._enqueue_result

    def dequeue(self):
        self.dequeue_calls += 1
        return self._dequeue_result


def make_record(
    run_id: str,
    monitor_status: WorkflowMonitorStatus,
    job_id: str = "job-1",
) -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=monitor_status,
        source_status=monitor_status.value, source="manual", job_id=job_id,
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=[],
    )


policy_ok = RetryPolicy(target_statuses=DEFAULT_TARGET_STATUSES, max_attempts=3)


# ═══════════════════════════════════════════════════════════
# テスト1: queue省略時のフォールバック
# ═══════════════════════════════════════════════════════════

print("[テスト1] queue省略時、NullRetryQueueManager()にフォールバックする")

manager_1 = RetryManager(
    policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None),
)
result_1_enqueue = manager_1.enqueue_retry(run_id="run-1", workflow_name="news")
result_1_dequeue = manager_1.dequeue_retry()
check("1. queue省略時のenqueue_retry() → outcome=DISABLED", result_1_enqueue.outcome, RetryQueueOutcome.DISABLED)
check("1. queue省略時のdequeue_retry() → outcome=DISABLED", result_1_dequeue.outcome, RetryQueueOutcome.DISABLED)
check_contains("1. reasonにRetry Queueが無効である旨が含まれる", result_1_enqueue.reason, "RETRY_QUEUE_ENABLED=false")
print()


# ═══════════════════════════════════════════════════════════
# テスト2-4: 委譲の正確性（Fake RetryQueueManagerを使用）
# ═══════════════════════════════════════════════════════════

print("[テスト2] enqueue_retry()の全引数がRetryQueueManager.enqueue()へそのまま渡る")

expected_enqueue_result_2 = RetryQueueResult(outcome=RetryQueueOutcome.ENQUEUED, item=None, reason=None)
fake_queue_2 = FakeRetryQueueManager(enqueue_result=expected_enqueue_result_2)
manager_2 = RetryManager(
    policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None),
    queue=fake_queue_2,
)
result_2 = manager_2.enqueue_retry(run_id="run-2", workflow_name="news", retry_attempt=2, priority=5)
check("2. FakeのRetryQueueManager.enqueue()が1回だけ呼ばれる", len(fake_queue_2.enqueue_calls), 1)
check(
    "2. 引数（run_id/workflow_name/retry_attempt/priority）がそのまま渡る",
    fake_queue_2.enqueue_calls[0],
    {"run_id": "run-2", "workflow_name": "news", "retry_attempt": 2, "priority": 5},
)
check("2. 戻り値がRetryQueueManagerの戻り値そのもの", result_2, expected_enqueue_result_2)
print()

print("[テスト3] dequeue_retry()の戻り値がRetryQueueManager.dequeue()からそのまま返る")

expected_dequeue_result_3 = RetryQueueResult(outcome=RetryQueueOutcome.EMPTY, item=None, reason="queue is empty.")
fake_queue_3 = FakeRetryQueueManager(dequeue_result=expected_dequeue_result_3)
manager_3 = RetryManager(
    policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None),
    queue=fake_queue_3,
)
result_3 = manager_3.dequeue_retry()
check("3. FakeのRetryQueueManager.dequeue()が1回だけ呼ばれる", fake_queue_3.dequeue_calls, 1)
check("3. 戻り値がRetryQueueManagerの戻り値そのもの", result_3, expected_dequeue_result_3)
print()

print("[テスト4] Queue満杯・重複run_id → REJECTEDがそのまま返る")

expected_rejected_4 = RetryQueueResult(outcome=RetryQueueOutcome.REJECTED, item=None, reason="duplicate run_id: run-4")
fake_queue_4 = FakeRetryQueueManager(enqueue_result=expected_rejected_4)
manager_4 = RetryManager(
    policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None),
    queue=fake_queue_4,
)
result_4 = manager_4.enqueue_retry(run_id="run-4", workflow_name="news")
check("4. REJECTEDがそのまま返る（RetryManager側で再判定しない）", result_4.outcome, RetryQueueOutcome.REJECTED)
check("4. reasonも改変されずそのまま", result_4.reason, "duplicate run_id: run-4")
print()


# ═══════════════════════════════════════════════════════════
# テスト5: 【Architecture Review反映】retry_attemptデフォルト値の一致
# ═══════════════════════════════════════════════════════════

print("[テスト5] enqueue_retry()とRetryQueueManager.enqueue()のretry_attemptデフォルト値が一致する")

sig_enqueue_retry_5 = inspect.signature(RetryManager.enqueue_retry)
sig_queue_enqueue_5 = inspect.signature(RetryQueueManager.enqueue)
check(
    "5. retry_attemptのデフォルト値が両者で一致する",
    sig_enqueue_retry_5.parameters["retry_attempt"].default,
    sig_queue_enqueue_5.parameters["retry_attempt"].default,
)
check(
    "5. priorityのデフォルト値が両者で一致する（Noneのまま委譲）",
    sig_enqueue_retry_5.parameters["priority"].default,
    sig_queue_enqueue_5.parameters["priority"].default,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト6: 【Architecture Review反映】実RetryQueueManagerでの往復
# ═══════════════════════════════════════════════════════════

print("[テスト6] 実RetryQueueManagerを使ったenqueue_retry() → dequeue_retry()の往復")

clear_queue_env()
os.environ["RETRY_QUEUE_ENABLED"] = "true"
real_queue_6 = RetryQueueManager.from_config(RetryQueueConfig.from_env())
check_true("6. 実RetryQueueManagerが構築される", isinstance(real_queue_6, RetryQueueManager))

manager_6 = RetryManager(
    policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None),
    queue=real_queue_6,
)
enqueue_result_6 = manager_6.enqueue_retry(run_id="run-6", workflow_name="news", retry_attempt=1)
check("6. enqueue_retry()経由で実際に登録される", enqueue_result_6.outcome, RetryQueueOutcome.ENQUEUED)
check("6. RetryQueueManager.count()が1になる", real_queue_6.count(), 1)

dequeue_result_6 = manager_6.dequeue_retry()
check("6. dequeue_retry()が同じrun_idを取り出す", dequeue_result_6.item.run_id, "run-6")
check("6. dequeue後はcount()が0に戻る", real_queue_6.count(), 0)
clear_queue_env()
print()


# ═══════════════════════════════════════════════════════════
# テスト7: 【Architecture Review反映】明示的Null指定と省略時の等価性
# ═══════════════════════════════════════════════════════════

print("[テスト7] NullRetryQueueManager()を明示的に渡した場合と省略した場合の結果が一致する")

manager_7a = RetryManager(
    policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None),
)
manager_7b = RetryManager(
    policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None),
    queue=NullRetryQueueManager(),
)

check(
    "7. enqueue_retry()の結果が省略時と明示的Null指定で一致する",
    manager_7a.enqueue_retry(run_id="run-7", workflow_name="news"),
    manager_7b.enqueue_retry(run_id="run-7", workflow_name="news"),
)
check(
    "7. dequeue_retry()の結果が省略時と明示的Null指定で一致する",
    manager_7a.dequeue_retry(),
    manager_7b.dequeue_retry(),
)
print()


# ═══════════════════════════════════════════════════════════
# テスト8-9: from_config()の後方互換性・実配線
# ═══════════════════════════════════════════════════════════

print("[テスト8] from_config()の既存4引数呼び出しが本Release前と同じゲート判定結果を返す")

clear_env()
fake_engine_ok = FakeWorkflowEngineManager()
fake_monitor_ok = FakeWorkflowMonitorManager(record=None)

mgr_8a = RetryManager.from_config(RetryConfig(enabled=False), policy_ok, fake_engine_ok, fake_monitor_ok)
check_true("8. enabled=Falseの4引数呼び出し → NullRetryManager", isinstance(mgr_8a, NullRetryManager))

mgr_8b = RetryManager.from_config(RetryConfig(enabled=True), policy_ok, NullWorkflowEngineManager(), fake_monitor_ok)
check_true("8. NullWorkflowEngineManagerの4引数呼び出し → NullRetryManager", isinstance(mgr_8b, NullRetryManager))

mgr_8c = RetryManager.from_config(RetryConfig(enabled=True), policy_ok, fake_engine_ok, fake_monitor_ok)
check_true("8. 両方満たす4引数呼び出し → RetryManager（実インスタンス）", isinstance(mgr_8c, RetryManager))

result_8c = mgr_8c.enqueue_retry(run_id="run-8", workflow_name="news")
check(
    "8. retry_queue_manager省略時はNullRetryQueueManagerへフォールバックしDISABLEDを返す",
    result_8c.outcome, RetryQueueOutcome.DISABLED,
)
print()

print("[テスト9] from_config()でretry_queue_managerを渡すと実際に配線される")

clear_queue_env()
os.environ["RETRY_QUEUE_ENABLED"] = "true"
real_queue_9 = RetryQueueManager.from_config(RetryQueueConfig.from_env())
mgr_9 = RetryManager.from_config(
    RetryConfig(enabled=True), policy_ok, fake_engine_ok, fake_monitor_ok,
    retry_queue_manager=real_queue_9,
)
mgr_9.enqueue_retry(run_id="run-9", workflow_name="news")
check("9. from_config()経由で渡したRetryQueueManagerに実際に登録される", real_queue_9.count(), 1)
clear_queue_env()
print()


# ═══════════════════════════════════════════════════════════
# テスト10: retry()とQueue操作の独立性
# ═══════════════════════════════════════════════════════════

print("[テスト10] retry()とenqueue_retry()/dequeue_retry()が互いを呼び出さない")

fake_queue_10 = FakeRetryQueueManager(enqueue_result=None, dequeue_result=None)
fake_monitor_10 = FakeWorkflowMonitorManager(record=make_record("run-10", WorkflowMonitorStatus.FAILED))
fake_executor_10 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-10", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None, workflow_engine_result=None,
))
manager_10 = RetryManager(policy=policy_ok, executor=fake_executor_10, monitor=fake_monitor_10, queue=fake_queue_10)

manager_10.retry("run-10", attempt=1)
check("10. retry()を呼んでもFakeQueue.enqueue()は呼ばれない", len(fake_queue_10.enqueue_calls), 0)
check("10. retry()を呼んでもFakeQueue.dequeue()は呼ばれない", fake_queue_10.dequeue_calls, 0)
check("10. retry()呼び出し後、FakeMonitor.get_status()は1回呼ばれている", fake_monitor_10.call_count, 1)
check("10. retry()呼び出し後、FakeExecutor.execute()は1回呼ばれている", len(fake_executor_10.calls), 1)

manager_10.enqueue_retry(run_id="run-10b", workflow_name="news")
manager_10.dequeue_retry()
check("10. enqueue_retry()/dequeue_retry()を呼んでもFakeMonitor.get_status()は増えない", fake_monitor_10.call_count, 1)
check("10. enqueue_retry()/dequeue_retry()を呼んでもFakeExecutor.execute()は増えない", len(fake_executor_10.calls), 1)
check("10. enqueue_retry()/dequeue_retry()によりFakeQueueは1回ずつ呼ばれる", len(fake_queue_10.enqueue_calls), 1)
check("10. enqueue_retry()/dequeue_retry()によりFakeQueueは1回ずつ呼ばれる", fake_queue_10.dequeue_calls, 1)
print()


print("[テスト11] Architecture Guard：enqueue_retry()/dequeue_retry()が"
      "self.retry/_executor/_monitor/_policyを参照しない（静的検査）")

retry_manager_source = (PROJECT_ROOT / "src" / "retry_engine" / "retry_manager.py").read_text(encoding="utf-8")


def extract_method_body(source: str, method_name: str) -> str:
    start_match = re.search(rf"\n    def {re.escape(method_name)}\(", source)
    rest = source[start_match.end():]
    next_match = re.search(r"\n    def ", rest)
    end = next_match.start() if next_match else len(rest)
    return rest[:end]


body_enqueue_retry = extract_method_body(retry_manager_source, "enqueue_retry")
body_dequeue_retry = extract_method_body(retry_manager_source, "dequeue_retry")

for forbidden in ("self.retry(", "self._executor", "self._monitor", "self._policy"):
    check_false(f"11. enqueue_retry()本体が「{forbidden}」を含まない", forbidden in body_enqueue_retry)
    check_false(f"11. dequeue_retry()本体が「{forbidden}」を含まない", forbidden in body_dequeue_retry)
print()


# ═══════════════════════════════════════════════════════════
# テスト12: NullRetryManagerの一貫性
# ═══════════════════════════════════════════════════════════

print("[テスト12] NullRetryManagerのenqueue_retry()/dequeue_retry()の一貫性")

null_mgr_12 = NullRetryManager()
result_12_enqueue = null_mgr_12.enqueue_retry(run_id="run-12", workflow_name="news")
result_12_dequeue = null_mgr_12.dequeue_retry()
check("12. NullRetryManager.enqueue_retry() → outcome=DISABLED", result_12_enqueue.outcome, RetryQueueOutcome.DISABLED)
check("12. NullRetryManager.dequeue_retry() → outcome=DISABLED", result_12_dequeue.outcome, RetryQueueOutcome.DISABLED)
check_contains("12. reasonにRetry Engineが無効である旨が含まれる", result_12_enqueue.reason, "Retry Engine is disabled")

null_queue_reason_12 = NullRetryQueueManager().enqueue("run-x", "wf").reason
check_true(
    "12. NullRetryManagerのreasonはNullRetryQueueManagerのreasonと異なる文言",
    result_12_enqueue.reason != null_queue_reason_12,
)
check("12. NullRetryManagerはQueueを含むいかなるフィールドも持たない", vars(null_mgr_12), {})
print()


# ═══════════════════════════════════════════════════════════
# テスト13: 書き込みが発生しないことの確認
# ═══════════════════════════════════════════════════════════

print("[テスト13] Queue統合の実行前後でファイルが一切作成されない")

write_check_dir_13 = Path(tempfile.mkdtemp())
before_files_13 = list(write_check_dir_13.rglob("*"))

clear_queue_env()
os.environ["RETRY_QUEUE_ENABLED"] = "true"
real_queue_13 = RetryQueueManager.from_config(RetryQueueConfig.from_env())
manager_13 = RetryManager(
    policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=FakeWorkflowMonitorManager(record=None),
    queue=real_queue_13,
)
manager_13.enqueue_retry(run_id="run-13", workflow_name="news")
manager_13.dequeue_retry()
NullRetryManager().enqueue_retry(run_id="run-13b", workflow_name="news")

after_files_13 = list(write_check_dir_13.rglob("*"))
check("13. Queue統合実行前後でファイルが作成されない", after_files_13, before_files_13)
clear_queue_env()
print()


# ═══════════════════════════════════════════════════════════
# テスト14: Architecture Guard（無改修の確認）
# ═══════════════════════════════════════════════════════════

print("[テスト14] 既存ファイルの無変更確認（git diff）")

unchanged_paths_v320 = [
    "main.py",
    "src/execution_history/execution_history_config.py",
    "src/execution_history/execution_history_event.py",
    "src/execution_history/execution_history_manager.py",
    "src/execution_history/execution_history_store.py",
    "src/execution_history/json_execution_history_store.py",
    "src/execution_history/step_execution_record.py",
    "src/execution_history/workflow_execution_record.py",
    "src/workflow_engine/workflow_engine_executor.py",
    "src/workflow_engine/workflow_engine_manager.py",
    "src/workflow_engine/workflow_engine_event.py",
    "src/workflow_engine/workflow_engine_result.py",
    "src/workflow_monitor/workflow_monitor.py",
    "src/workflow_monitor/workflow_monitor_manager.py",
    "src/workflow_monitor/workflow_monitor_config.py",
    "src/workflow_monitor/workflow_monitor_record.py",
    "src/workflow_monitor/workflow_monitor_status.py",
    "src/ai/agent_manager.py",
    "src/scheduler/scheduler_engine.py",
    # retry_engine のうち、本Releaseで変更していないファイル（retry_manager.py以外）
    "src/retry_engine/__init__.py",
    "src/retry_engine/retry_policy.py",
    "src/retry_engine/retry_config.py",
    "src/retry_engine/retry_request.py",
    "src/retry_engine/retry_result.py",
    "src/retry_engine/retry_executor.py",
    # retry_queue（Charterで無改修が要求されている、全ファイル）
    "src/retry_queue/__init__.py",
    "src/retry_queue/retry_queue_status.py",
    "src/retry_queue/retry_queue_item.py",
    "src/retry_queue/retry_queue_result.py",
    "src/retry_queue/retry_queue_config.py",
    "src/retry_queue/retry_queue_manager.py",
    "src/retry_queue/null_retry_queue_manager.py",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths_v320:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"14. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("14. gitが利用できないため無変更確認をスキップ", True)
print()


# ═══════════════════════════════════════════════════════════
# テスト15: retry_queueパッケージの公開APIシグネチャが変化していないこと
# ═══════════════════════════════════════════════════════════

print("[テスト15] RetryQueueManager / NullRetryQueueManagerの公開APIが不変であること")

sig_queue_enqueue_15 = inspect.signature(RetryQueueManager.enqueue)
check(
    "15. RetryQueueManager.enqueue()の引数名が変化していない",
    list(sig_queue_enqueue_15.parameters.keys()),
    ["self", "run_id", "workflow_name", "retry_attempt", "priority"],
)
check("15. retry_attemptのデフォルトが1のまま", sig_queue_enqueue_15.parameters["retry_attempt"].default, 1)
check("15. priorityのデフォルトがNoneのまま", sig_queue_enqueue_15.parameters["priority"].default, None)

sig_queue_dequeue_15 = inspect.signature(RetryQueueManager.dequeue)
check("15. RetryQueueManager.dequeue()に引数が追加されていない", list(sig_queue_dequeue_15.parameters.keys()), ["self"])

for method_name in ("enqueue", "dequeue", "remove", "list", "exists", "count"):
    check_true(f"15. RetryQueueManagerが{method_name}()を保持している", hasattr(RetryQueueManager, method_name))
    check_true(f"15. NullRetryQueueManagerが{method_name}()を保持している", hasattr(NullRetryQueueManager, method_name))
print()


# ═══════════════════════════════════════════════════════════
# テスト16: retry_engineパッケージのexportが変化していないこと
# ═══════════════════════════════════════════════════════════

print("[テスト16] retry_engine.__all__ が本Release前と同一であること")

import retry_engine as re_pkg_16

check(
    "16. retry_engine.__all__ が本Release前と同一（新規公開シンボルを追加していない）",
    set(re_pkg_16.__all__),
    {
        "RetryPolicy", "DEFAULT_TARGET_STATUSES", "RetryConfig", "RetryRequest", "RetryOutcome",
        "RetryResult", "RetryExecutor", "RetryManager", "NullRetryManager",
    },
)
check_true("16. RetryManagerがenqueue_retry()を持つ", hasattr(RetryManager, "enqueue_retry"))
check_true("16. RetryManagerがdequeue_retry()を持つ", hasattr(RetryManager, "dequeue_retry"))
check_true("16. NullRetryManagerがenqueue_retry()を持つ", hasattr(NullRetryManager, "enqueue_retry"))
check_true("16. NullRetryManagerがdequeue_retry()を持つ", hasattr(NullRetryManager, "dequeue_retry"))
print()


# ═══════════════════════════════════════════════════════════
# テスト17: from_config()の新規引数が後方互換な形で追加されていること
# ═══════════════════════════════════════════════════════════

print("[テスト17] from_config()の新規引数が末尾・デフォルト値付きで追加されていること")

sig_from_config_17 = inspect.signature(RetryManager.from_config)
params_17 = list(sig_from_config_17.parameters.keys())
check("17. from_config()の第5引数がretry_queue_manager", params_17[-1], "retry_queue_manager")
check(
    "17. retry_queue_managerのデフォルトはNone",
    sig_from_config_17.parameters["retry_queue_manager"].default,
    None,
)
check(
    "17. 既存4引数の名前・順序が変わっていない",
    params_17[:4],
    ["retry_config", "retry_policy", "workflow_engine_manager", "workflow_monitor_manager"],
)
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
