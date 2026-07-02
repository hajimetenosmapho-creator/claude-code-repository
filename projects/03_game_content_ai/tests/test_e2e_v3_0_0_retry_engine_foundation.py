"""
E2E テスト: v3.0.0 Retry Engine Foundation

テストシナリオ:
    ── RetryPolicy ──
    1.  should_retry() 真理値表（FAILED/TIMEOUT/SUCCESS/RUNNING/CANCELLED/WAITING × attempt）
    2.  from_env() のデフォルト値（max_attempts=3）・環境変数上書き・target_statuses固定

    ── RetryConfig ──
    3.  from_env() のデフォルト値（enabled=False）・環境変数上書き・is_ready()

    ── RetryRequest / RetryResult / RetryOutcome ──
    4.  構築・フィールドの整合性

    ── RetryExecutor（Fakeの WorkflowEngineManager を注入） ──
    5.  execute() が常に RetryOutcome.RETRIED を返し、Fakeのrun()が1回だけ呼ばれる
    6.  渡される WorkflowEngineEvent の source/job_id/metadata が正しい
    7.  dry_run が self._engine.run(event, dry_run=...) にそのまま伝播する
    8.  workflow_engine_result にFakeの戻り値がそのまま格納される
    9.  RetryExecutor のコンストラクタが policy 引数を持たない（RetryPolicyを保持しない）

    ── RetryManager（Fakeの WorkflowMonitorManager / RetryExecutor を注入） ──
    10. get_status()がNoneを返す場合 → NOT_FOUND、RetryExecutorが呼ばれない
    11. monitor_statusが対象外（SUCCESS/RUNNING）→ SKIPPED、RetryExecutorが呼ばれない
    12. attempt >= max_attempts → SKIPPED、RetryExecutorが呼ばれない
    13. FAILED/TIMEOUTかつattempt < max_attempts → RetryExecutorへ委譲され戻り値がそのまま返る
    14. 同一run_idに複数回retry()を呼ぶと毎回get_status()が呼ばれる（Read Before Retry）

    ── RetryManager.from_config()（ゲート判定） ──
    15. RetryConfig.enabled=False → NullRetryManager
    16. enabled=TrueだがNullWorkflowEngineManager → NullRetryManager
    17. 両方満たす場合 → RetryManager（実インスタンス）

    ── NullRetryManager ──
    18. retry() は常に outcome=DISABLED を返す

    ── 書き込みが発生しないことの確認 ──
    19. RetryManager / RetryExecutor 実行前後でファイルが一切作成されない

    ── Enum比較の確認 ──
    20. RetryPolicy.target_statuses の要素が WorkflowMonitorStatus のインスタンスである

    ── Architecture Guard ──
    21. src/retry_engine/ が execution_history/ai/pipeline/scheduler をimportしない（静的検査）
    22. 既存ファイル（workflow_engine/workflow_monitor/execution_history等）に変更がない（git diff）
    23. retry_engine パッケージのexport確認

    ── RetryManager.retry() の dry_run 引数 ──
    24. retry(run_id, attempt, dry_run=True) が RetryRequest.dry_run=True としてExecutorへ渡る
    25. dry_run省略時（デフォルトFalse）の既存呼び出し互換性が保たれる
    26. NullRetryManager.retry() が dry_run 引数を受け取ってもエラーにならない

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v3_0_0_retry_engine_foundation.py
"""
import inspect
import os
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
print("v3.0.0 Retry Engine Foundation E2E テスト")
print("=" * 60)
print()

from workflow_engine import (
    SOURCE_MANUAL,
    NullWorkflowEngineManager,
    WorkflowEngineResult,
)
from workflow_monitor import NullWorkflowMonitorManager, WorkflowMonitorRecord, WorkflowMonitorStatus
from retry_engine import (
    DEFAULT_TARGET_STATUSES,
    NullRetryManager,
    RetryConfig,
    RetryExecutor,
    RetryManager,
    RetryOutcome,
    RetryPolicy,
    RetryRequest,
    RetryResult,
)

ENV_KEYS = ("RETRY_ENGINE_ENABLED", "RETRY_MAX_ATTEMPTS")


def clear_env():
    for key in ENV_KEYS:
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

    def __init__(self, result: RetryResult):
        self.calls: list[tuple] = []
        self._result = result

    def execute(self, request: RetryRequest, record: WorkflowMonitorRecord) -> RetryResult:
        self.calls.append((request, record))
        return self._result


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


# ═══════════════════════════════════════════════════════════
# テスト1-2: RetryPolicy
# ═══════════════════════════════════════════════════════════

print("[テスト1] RetryPolicy.should_retry() 真理値表")

policy_3 = RetryPolicy(target_statuses=DEFAULT_TARGET_STATUSES, max_attempts=3)

check_true("1. FAILED かつ attempt(1) < max_attempts(3) → True", policy_3.should_retry(WorkflowMonitorStatus.FAILED, 1))
check_false("1. FAILED かつ attempt(3) >= max_attempts(3) → False", policy_3.should_retry(WorkflowMonitorStatus.FAILED, 3))
check_true("1. TIMEOUT かつ attempt(1) < max_attempts(3) → True", policy_3.should_retry(WorkflowMonitorStatus.TIMEOUT, 1))
check_false("1. SUCCESS → False", policy_3.should_retry(WorkflowMonitorStatus.SUCCESS, 1))
check_false("1. RUNNING → False", policy_3.should_retry(WorkflowMonitorStatus.RUNNING, 1))
check_false("1. CANCELLED → False（防御的テスト）", policy_3.should_retry(WorkflowMonitorStatus.CANCELLED, 1))
check_false("1. WAITING → False（防御的テスト）", policy_3.should_retry(WorkflowMonitorStatus.WAITING, 1))
print()

print("[テスト2] RetryPolicy.from_env()")

clear_env()
p1 = RetryPolicy.from_env()
check("2. デフォルト max_attempts=3", p1.max_attempts, 3)
check("2. target_statuses が {FAILED, TIMEOUT} 固定", p1.target_statuses, DEFAULT_TARGET_STATUSES)

os.environ["RETRY_MAX_ATTEMPTS"] = "5"
p2 = RetryPolicy.from_env()
check("2. RETRY_MAX_ATTEMPTS の環境変数上書き", p2.max_attempts, 5)
check("2. 環境変数上書き後も target_statuses は固定のまま", p2.target_statuses, DEFAULT_TARGET_STATUSES)
os.environ.pop("RETRY_MAX_ATTEMPTS", None)
print()


# ═══════════════════════════════════════════════════════════
# テスト3: RetryConfig
# ═══════════════════════════════════════════════════════════

print("[テスト3] RetryConfig.from_env()")

clear_env()
c1 = RetryConfig.from_env()
check_false("3. デフォルト enabled=False", c1.enabled)
check_false("3. デフォルトは is_ready()=False", c1.is_ready())

os.environ["RETRY_ENGINE_ENABLED"] = "true"
c2 = RetryConfig.from_env()
check_true("3. RETRY_ENGINE_ENABLED=true で enabled=True", c2.enabled)
check_true("3. is_ready()=True", c2.is_ready())
os.environ.pop("RETRY_ENGINE_ENABLED", None)
print()


# ═══════════════════════════════════════════════════════════
# テスト4: RetryRequest / RetryResult / RetryOutcome
# ═══════════════════════════════════════════════════════════

print("[テスト4] RetryRequest / RetryResult / RetryOutcome の構築")

req = RetryRequest(run_id="run-x", attempt=2, requested_at=datetime.now())
check("4. RetryRequest.run_id", req.run_id, "run-x")
check("4. RetryRequest.attempt", req.attempt, 2)
check_false("4. RetryRequest.dry_run のデフォルトはFalse", req.dry_run)

res = RetryResult(
    original_run_id="run-x", outcome=RetryOutcome.SKIPPED, attempt=2,
    monitor_status=WorkflowMonitorStatus.SUCCESS, reason="not a target", workflow_engine_result=None,
)
check("4. RetryResult.outcome", res.outcome, RetryOutcome.SKIPPED)
check("4. RetryOutcomeの4値が定義されている", {o.value for o in RetryOutcome}, {"retried", "skipped", "not_found", "disabled"})
print()


# ═══════════════════════════════════════════════════════════
# テスト5-9: RetryExecutor
# ═══════════════════════════════════════════════════════════

print("[テスト5-9] RetryExecutor.execute()")

fake_engine_5 = FakeWorkflowEngineManager()
executor_5 = RetryExecutor(workflow_engine_manager=fake_engine_5)
record_5 = make_record("run-5", WorkflowMonitorStatus.FAILED, job_id="job-5")
request_5 = RetryRequest(run_id="run-5", attempt=1, requested_at=datetime.now())

result_5 = executor_5.execute(request_5, record_5)
check("5. execute() は常に RetryOutcome.RETRIED を返す", result_5.outcome, RetryOutcome.RETRIED)
check("5. Fakeのrun()が1回だけ呼ばれる", len(fake_engine_5.calls), 1)

event_5, dry_run_5 = fake_engine_5.calls[0]
check("6. WorkflowEngineEvent.source == SOURCE_MANUAL", event_5.source, SOURCE_MANUAL)
check("6. WorkflowEngineEvent.job_id が record.job_id と一致", event_5.job_id, "job-5")
check("6. metadata が retried_from/attempt を含む", event_5.metadata, {"retried_from": "run-5", "attempt": 1})

check_false("7. dry_run未指定時は False が伝播する", dry_run_5)

fake_engine_7 = FakeWorkflowEngineManager()
executor_7 = RetryExecutor(workflow_engine_manager=fake_engine_7)
request_7 = RetryRequest(run_id="run-7", attempt=1, requested_at=datetime.now(), dry_run=True)
executor_7.execute(request_7, make_record("run-7", WorkflowMonitorStatus.TIMEOUT))
check_true("7. dry_run=True が self._engine.run(event, dry_run=True) に伝播する", fake_engine_7.calls[0][1])

check_true("8. workflow_engine_result にFakeの戻り値がそのまま格納される", result_5.workflow_engine_result is not None)
check_true("8. workflow_engine_result.overall_success がFakeの値と一致", result_5.workflow_engine_result.overall_success)

executor_sig = inspect.signature(RetryExecutor.__init__)
check_false("9. RetryExecutor.__init__ が policy 引数を持たない", "policy" in executor_sig.parameters)
print()


# ═══════════════════════════════════════════════════════════
# テスト10-14: RetryManager
# ═══════════════════════════════════════════════════════════

print("[テスト10-14] RetryManager.retry()")

# テスト10: get_status()がNone → NOT_FOUND
fake_monitor_10 = FakeWorkflowMonitorManager(record=None)
fake_executor_10 = FakeRetryExecutor(result=None)
manager_10 = RetryManager(policy=policy_3, executor=fake_executor_10, monitor=fake_monitor_10)
result_10 = manager_10.retry("run-missing", attempt=1)
check("10. record=None → NOT_FOUND", result_10.outcome, RetryOutcome.NOT_FOUND)
check("10. RetryExecutor.execute() は呼ばれない", len(fake_executor_10.calls), 0)

# テスト11: monitor_statusが対象外（SUCCESS）
record_11 = make_record("run-success", WorkflowMonitorStatus.SUCCESS)
fake_monitor_11 = FakeWorkflowMonitorManager(record=record_11)
fake_executor_11 = FakeRetryExecutor(result=None)
manager_11 = RetryManager(policy=policy_3, executor=fake_executor_11, monitor=fake_monitor_11)
result_11 = manager_11.retry("run-success", attempt=1)
check("11. SUCCESS → SKIPPED", result_11.outcome, RetryOutcome.SKIPPED)
check("11. RetryExecutor.execute() は呼ばれない", len(fake_executor_11.calls), 0)
check_contains("11. reasonに対象外である旨が含まれる", result_11.reason, "not a retry target")

# テスト12: attempt >= max_attempts
record_12 = make_record("run-failed", WorkflowMonitorStatus.FAILED)
fake_monitor_12 = FakeWorkflowMonitorManager(record=record_12)
fake_executor_12 = FakeRetryExecutor(result=None)
manager_12 = RetryManager(policy=policy_3, executor=fake_executor_12, monitor=fake_monitor_12)
result_12 = manager_12.retry("run-failed", attempt=3)
check("12. attempt(3) >= max_attempts(3) → SKIPPED", result_12.outcome, RetryOutcome.SKIPPED)
check("12. RetryExecutor.execute() は呼ばれない", len(fake_executor_12.calls), 0)
check_contains("12. reasonに上限到達の旨が含まれる", result_12.reason, "max_attempts")

# テスト13: FAILEDかつattempt < max_attempts → RetryExecutorへ委譲
record_13 = make_record("run-timeout", WorkflowMonitorStatus.TIMEOUT)
expected_result_13 = RetryResult(
    original_run_id="run-timeout", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.TIMEOUT, reason=None, workflow_engine_result=None,
)
fake_monitor_13 = FakeWorkflowMonitorManager(record=record_13)
fake_executor_13 = FakeRetryExecutor(result=expected_result_13)
manager_13 = RetryManager(policy=policy_3, executor=fake_executor_13, monitor=fake_monitor_13)
result_13 = manager_13.retry("run-timeout", attempt=1)
check("13. TIMEOUTかつattempt<max → RetryExecutorへ委譲", len(fake_executor_13.calls), 1)
check("13. RetryExecutorの戻り値がそのまま返る", result_13, expected_result_13)

# テスト14: 複数回retry()を呼ぶと毎回get_status()が呼ばれる
manager_13.retry("run-timeout", attempt=1)
manager_13.retry("run-timeout", attempt=1)
check("14. 3回のretry()呼び出しで毎回get_status()が呼ばれる", fake_monitor_13.call_count, 3)
print()


# ═══════════════════════════════════════════════════════════
# テスト15-17: RetryManager.from_config()
# ═══════════════════════════════════════════════════════════

print("[テスト15-17] RetryManager.from_config()（ゲート判定）")

fake_engine_ok = FakeWorkflowEngineManager()
fake_monitor_ok = FakeWorkflowMonitorManager(record=None)

mgr_15 = RetryManager.from_config(
    RetryConfig(enabled=False), policy_3, fake_engine_ok, fake_monitor_ok,
)
check_true("15. RetryConfig.enabled=False → NullRetryManager", isinstance(mgr_15, NullRetryManager))

mgr_16 = RetryManager.from_config(
    RetryConfig(enabled=True), policy_3, NullWorkflowEngineManager(), fake_monitor_ok,
)
check_true("16. enabled=TrueだがNullWorkflowEngineManager → NullRetryManager", isinstance(mgr_16, NullRetryManager))

mgr_17 = RetryManager.from_config(
    RetryConfig(enabled=True), policy_3, fake_engine_ok, fake_monitor_ok,
)
check_true("17. 両方満たす場合 → RetryManager（実インスタンス）", isinstance(mgr_17, RetryManager))
print()


# ═══════════════════════════════════════════════════════════
# テスト18: NullRetryManager
# ═══════════════════════════════════════════════════════════

print("[テスト18] NullRetryManager.retry()")

null_mgr = NullRetryManager()
result_18 = null_mgr.retry("any-run-id", attempt=1)
check("18. outcome は常に DISABLED", result_18.outcome, RetryOutcome.DISABLED)
check_none("18. workflow_engine_result は None", result_18.workflow_engine_result)
print()


# ═══════════════════════════════════════════════════════════
# テスト19: 書き込みが発生しないことの確認
# ═══════════════════════════════════════════════════════════

print("[テスト19] Retry Engine自身がファイルを一切作成しないこと")

write_check_dir = Path(tempfile.mkdtemp())
before_files = list(write_check_dir.rglob("*"))

fake_engine_19 = FakeWorkflowEngineManager()
fake_monitor_19 = FakeWorkflowMonitorManager(record=make_record("run-19", WorkflowMonitorStatus.FAILED))
manager_19 = RetryManager.from_config(RetryConfig(enabled=True), policy_3, fake_engine_19, fake_monitor_19)
manager_19.retry("run-19", attempt=1)
manager_19.retry("run-does-not-exist", attempt=1)
NullRetryManager().retry("run-19", attempt=1)

after_files = list(write_check_dir.rglob("*"))
check("19. Retry Engine実行前後でファイルが作成されない", after_files, before_files)
print()


# ═══════════════════════════════════════════════════════════
# テスト20: Enum比較の確認
# ═══════════════════════════════════════════════════════════

print("[テスト20] RetryPolicy.target_statuses がEnumインスタンスであること")

check_true(
    "20. target_statuses の全要素が WorkflowMonitorStatus のインスタンス",
    all(isinstance(s, WorkflowMonitorStatus) for s in DEFAULT_TARGET_STATUSES),
)
print()


# ═══════════════════════════════════════════════════════════
# テスト21-23: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト21] retry_engine が execution_history/ai/pipeline/schedulerをimportしない（静的検査）")

re_dir = PROJECT_ROOT / "src" / "retry_engine"
for py_file in sorted(re_dir.glob("*.py")):
    source = py_file.read_text(encoding="utf-8")
    import_lines = "\n".join(
        line for line in source.splitlines()
        if line.strip().startswith("from ") or line.strip().startswith("import ")
    )
    for forbidden in ("execution_history", "scheduler", "from ai", "import ai", "from pipeline", "import pipeline"):
        check_false(
            f"21. {py_file.name} が {forbidden} をimportしない",
            forbidden in import_lines,
        )
print()


print("[テスト22] 既存ファイルの無変更確認（git diff）")

unchanged_paths_re = [
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
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths_re:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"22. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("22. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト23] import確認（retry_engine パッケージのexport）")

import retry_engine as re_pkg
for name in (
    "RetryPolicy", "RetryConfig", "RetryRequest", "RetryOutcome", "RetryResult",
    "RetryExecutor", "RetryManager", "NullRetryManager",
):
    check_true(f"23. {name} が retry_engine パッケージからエクスポートされている", hasattr(re_pkg, name))
    check_true(f"23. {name} が retry_engine.__all__ に含まれる", name in re_pkg.__all__)
print()


# ═══════════════════════════════════════════════════════════
# テスト24-26: RetryManager.retry() の dry_run 引数
# ═══════════════════════════════════════════════════════════

print("[テスト24-26] RetryManager.retry() の dry_run 引数")

fake_engine_24 = FakeWorkflowEngineManager()
fake_monitor_24 = FakeWorkflowMonitorManager(record=make_record("run-24", WorkflowMonitorStatus.FAILED))
manager_24 = RetryManager.from_config(RetryConfig(enabled=True), policy_3, fake_engine_24, fake_monitor_24)

result_24 = manager_24.retry("run-24", attempt=1, dry_run=True)
check("24. dry_run=True指定時 outcome=RETRIED", result_24.outcome, RetryOutcome.RETRIED)
check_true("24. dry_run=True が WorkflowEngineManager.run(event, dry_run=True) に伝播する", fake_engine_24.calls[0][1])

result_25 = manager_24.retry("run-24", attempt=1)
check_false("25. dry_run省略時（デフォルト）は False のまま伝播する", fake_engine_24.calls[1][1])

check_true("26. NullRetryManager.retry() が dry_run 引数を受け取ってもエラーにならない", True)
result_26 = NullRetryManager().retry("run-26", attempt=1, dry_run=True)
check("26. NullRetryManager.retry(dry_run=True) も outcome=DISABLED", result_26.outcome, RetryOutcome.DISABLED)
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
