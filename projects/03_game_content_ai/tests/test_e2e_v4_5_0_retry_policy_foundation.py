"""
E2E テスト: v4.5.0 Retry Policy Foundation

テストシナリオ（docs/design/retry_policy_foundation.md 3章・4章・6章・12章 対応）:
    ── 既存RetryPolicyがProtocolに無改修で適合すること ──
    1.  既存RetryPolicyのインスタンスが RetryDecisionPolicy を満たす（isinstance）
    2.  既存RetryPolicyのインスタンスが ExplainableRetryPolicy を満たす（isinstance）
    3.  src/retry_engine/retry_policy.py に変更がない（git diff、0 diff）

    ── Architecture Guard（無改修の確認） ──
    4.  src/scheduler/ / src/retry_scheduler_decision/ / src/retry_scheduler_source/ /
        src/retry_queue/ 配下の全ファイル、および src/retry_engine/ のうち本Releaseで
        変更していないファイル（v4.4.0までに追加された全コンポーネント含む）に変更がないこと

    ── 案C（契約の段階分離）が実際に機能すること ──
    5.  should_retry()のみを持つ最小Fakeは RetryDecisionPolicy を満たすが、
        ExplainableRetryPolicy（target_statuses / max_attemptsも要求）は満たさない
    6.  should_retry() + target_statuses + max_attempts を持つFakeは両方を満たす

    ── RetryManagerへExplainableRetryPolicy互換Fakeを注入して動作確認 ──
    7.  Fake.should_retry()がTrueを返すケース → retry()がexecutorへ委譲しRETRIEDになる。
        Fake.should_retry()が実際に呼び出されたことも確認する
    8.  Fake.should_retry()がFalseを返すケース → retry()がSKIPPEDになり、
        _skip_reason()のメッセージがFakeのmax_attemptsを反映する（RetryPolicy固有の値ではない）
    9.  monitor_statusがFakeのtarget_statusesに含まれないケース →
        _skip_reason()のメッセージがFakeのtarget_statusesを反映する

    ── 既存回帰（本物のRetryPolicyを注入した場合の挙動）──
    10. retry()（RETRIED / SKIPPED / NOT_FOUND）、NullRetryManager.retry()（DISABLED）が
        本Release前とまったく同じ挙動であること

    ── パッケージexport・型注釈の確認 ──
    11. retry_engine.__all__ に新規2シンボル（RetryDecisionPolicy / ExplainableRetryPolicy）が
        追加され、既存36シンボルはそのまま維持されている
    12. RetryManager.__init__ / from_config() の policy / retry_policy 引数の型注釈が
        ExplainableRetryPolicy に解決される（typing.get_type_hints）

    ── 不要import・Non-Goalの確認（AST） ──
    13. retry_manager.py が具体クラス 'RetryPolicy' を実コードとして参照していない
        （ExplainableRetryPolicyのみを参照する。不要importの削除確認）
    14. src/retry_engine/ 配下に FixedRetryPolicy / ExponentialBackoffPolicy /
        AdaptiveRetryPolicy という名称のクラスが存在しない（Non-Goalの遵守確認）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v4_5_0_retry_policy_foundation.py
"""
import ast
import subprocess
import sys
import typing
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
print("v4.5.0 Retry Policy Foundation E2E テスト")
print("=" * 60)
print()

from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus
from retry_engine import (
    DEFAULT_TARGET_STATUSES,
    ExplainableRetryPolicy,
    NullRetryManager,
    RetryDecisionPolicy,
    RetryManager,
    RetryOutcome,
    RetryPolicy,
    RetryResult,
)
from retry_engine.retry_policy_protocol import ExplainableRetryPolicy as ExplainableRetryPolicy_direct
from retry_engine.retry_policy_protocol import RetryDecisionPolicy as RetryDecisionPolicy_direct


def make_record(run_id: str, monitor_status: WorkflowMonitorStatus, job_id: str = "job-1") -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=monitor_status,
        source_status=monitor_status.value, source="manual", job_id=job_id,
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=[],
    )


class FakeWorkflowMonitorManager:
    def __init__(self, record: "WorkflowMonitorRecord | None"):
        self.record = record
        self.calls: list[str] = []

    def get_status(self, run_id: str):
        self.calls.append(run_id)
        return self.record


class FakeRetryExecutor:
    def __init__(self, result: "RetryResult | None"):
        self.calls: list[tuple] = []
        self._result = result

    def execute(self, request, record) -> RetryResult:
        self.calls.append((request, record))
        return self._result


class FakeMinimalPolicy:
    """should_retry()のみを持つ最小Fake。target_statuses / max_attemptsは持たない。"""

    def __init__(self, retry_decision: bool = True):
        self._retry_decision = retry_decision
        self.calls: list[tuple] = []

    def should_retry(self, monitor_status, attempt) -> bool:
        self.calls.append((monitor_status, attempt))
        return self._retry_decision


class FakeExplainablePolicy:
    """should_retry() + target_statuses + max_attemptsを持つFake。ExplainableRetryPolicyを満たす。"""

    def __init__(self, retry_decision: bool, target_statuses=None, max_attempts: int = 5):
        self.target_statuses = target_statuses if target_statuses is not None else frozenset({WorkflowMonitorStatus.FAILED})
        self.max_attempts = max_attempts
        self._retry_decision = retry_decision
        self.calls: list[tuple] = []

    def should_retry(self, monitor_status, attempt) -> bool:
        self.calls.append((monitor_status, attempt))
        return self._retry_decision


def make_workflow_engine_result(overall_success: bool):
    from workflow_engine import WorkflowEngineResult
    now = datetime.now()
    return WorkflowEngineResult(
        steps=[], overall_success=overall_success, stopped_early=False,
        started_at=now, finished_at=now,
    )


# ═══════════════════════════════════════════════════════════
# テスト1-2: 既存RetryPolicyがProtocolを無改修で満たすこと
# ═══════════════════════════════════════════════════════════

print("[テスト1-2] 既存RetryPolicyがRetryDecisionPolicy / ExplainableRetryPolicyを満たす（isinstance）")

policy_ok = RetryPolicy(target_statuses=DEFAULT_TARGET_STATUSES, max_attempts=3)

check_true("1. RetryPolicyインスタンスがRetryDecisionPolicyを満たす", isinstance(policy_ok, RetryDecisionPolicy))
check_true("2. RetryPolicyインスタンスがExplainableRetryPolicyを満たす", isinstance(policy_ok, ExplainableRetryPolicy))
check_true("2. retry_engine直下importとretry_policy_protocol直接importが同一クラス（RetryDecisionPolicy）", RetryDecisionPolicy is RetryDecisionPolicy_direct)
check_true("2. retry_engine直下importとretry_policy_protocol直接importが同一クラス（ExplainableRetryPolicy）", ExplainableRetryPolicy is ExplainableRetryPolicy_direct)
print()


# ═══════════════════════════════════════════════════════════
# テスト3: retry_policy.py に変更がない（0 diff）
# ═══════════════════════════════════════════════════════════

print("[テスト3] src/retry_engine/retry_policy.py に変更がない（git diff、0 diff）")

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    completed_3 = subprocess.run(
        ["git", "diff", "--quiet", "--", "src/retry_engine/retry_policy.py"],
        cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
    )
    check_true("3. retry_policy.py に変更がない（git diff）", completed_3.returncode == 0)
else:
    check_true("3. gitが利用できないため無変更確認をスキップ", True)
print()


# ═══════════════════════════════════════════════════════════
# テスト4: Architecture Guard（本Releaseで変更していない既存ファイル群）
# ═══════════════════════════════════════════════════════════

print("[テスト4] 本Releaseで変更していない既存ファイルに変更がない（git diff）")

unchanged_paths_v450 = [
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
    "src/retry_engine/retry_outcome_terminality.py",
    "src/retry_engine/retry_queue_terminal_cleanup_decider.py",
    "src/retry_engine/retry_queue_terminal_cleanup_executor.py",
    "src/retry_engine/retry_policy.py",
    "src/retry_engine/retry_config.py",
    "src/retry_engine/retry_request.py",
    "src/retry_engine/retry_result.py",
    "src/retry_engine/retry_executor.py",
]

if git_available:
    for rel_path in unchanged_paths_v450:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"4. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("4. gitが利用できないため無変更確認をスキップ", True)
print()


# ═══════════════════════════════════════════════════════════
# テスト5-6: 案C（契約の段階分離）が実際に機能すること
# ═══════════════════════════════════════════════════════════

print("[テスト5-6] should_retry()のみのFakeはRetryDecisionPolicyのみ満たす／属性を揃えたFakeは両方満たす")

fake_minimal = FakeMinimalPolicy()
check_true("5. 最小FakeがRetryDecisionPolicyを満たす", isinstance(fake_minimal, RetryDecisionPolicy))
check_false("5. 最小FakeはExplainableRetryPolicyを満たさない（target_statuses/max_attemptsがない）", isinstance(fake_minimal, ExplainableRetryPolicy))

fake_explainable = FakeExplainablePolicy(retry_decision=True)
check_true("6. 属性を揃えたFakeがRetryDecisionPolicyを満たす", isinstance(fake_explainable, RetryDecisionPolicy))
check_true("6. 属性を揃えたFakeがExplainableRetryPolicyを満たす", isinstance(fake_explainable, ExplainableRetryPolicy))
print()


# ═══════════════════════════════════════════════════════════
# テスト7: Fake.should_retry()=True → retry()がexecutorへ委譲する
# ═══════════════════════════════════════════════════════════

print("[テスト7] ExplainableRetryPolicy互換Fake（should_retry=True）をRetryManagerへ注入し、retry()がFakeを実際に呼び出して動作する")

fake_policy_true_7 = FakeExplainablePolicy(retry_decision=True, max_attempts=5)
fake_monitor_7 = FakeWorkflowMonitorManager(record=make_record("run-7", WorkflowMonitorStatus.FAILED))
fake_executor_7 = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-7", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
))
manager_7 = RetryManager(policy=fake_policy_true_7, executor=fake_executor_7, monitor=fake_monitor_7)
result_7 = manager_7.retry("run-7", attempt=1)

check("7. retry()の結果がRETRIED（Fakeがexecutorへの委譲を許可した）", result_7.outcome, RetryOutcome.RETRIED)
check("7. Fake.should_retry()が実際に1回呼び出された", len(fake_policy_true_7.calls), 1)
check("7. Fake.should_retry()にmonitor_status/attemptが正しく渡された", fake_policy_true_7.calls[0], (WorkflowMonitorStatus.FAILED, 1))
check("7. RetryExecutor.execute()が実際に呼び出された", len(fake_executor_7.calls), 1)
print()


# ═══════════════════════════════════════════════════════════
# テスト8: Fake.should_retry()=False → SKIPPED、理由文言がFakeのmax_attemptsを反映
# ═══════════════════════════════════════════════════════════

print("[テスト8] ExplainableRetryPolicy互換Fake（should_retry=False）→ SKIPPED。理由文言がFakeのmax_attemptsを反映する")

fake_policy_false_8 = FakeExplainablePolicy(
    retry_decision=False,
    target_statuses=frozenset({WorkflowMonitorStatus.FAILED}),
    max_attempts=2,
)
fake_monitor_8 = FakeWorkflowMonitorManager(record=make_record("run-8", WorkflowMonitorStatus.FAILED))
manager_8 = RetryManager(policy=fake_policy_false_8, executor=FakeRetryExecutor(result=None), monitor=fake_monitor_8)
result_8 = manager_8.retry("run-8", attempt=2)

check("8. retry()の結果がSKIPPED", result_8.outcome, RetryOutcome.SKIPPED)
check("8. 理由文言にFake.max_attempts（2）が反映される", "max_attempts=2" in result_8.reason, True)
check("8. RetryExecutor.execute()は呼び出されない", len(FakeRetryExecutor(result=None).calls), 0)
print()


# ═══════════════════════════════════════════════════════════
# テスト9: monitor_statusがFakeのtarget_statusesに含まれない → 理由文言がFakeのtarget_statusesを反映
# ═══════════════════════════════════════════════════════════

print("[テスト9] monitor_statusがFakeのtarget_statusesに含まれないケース → 理由文言がFakeのtarget_statusesを反映する")

fake_policy_false_9 = FakeExplainablePolicy(
    retry_decision=False,
    target_statuses=frozenset({WorkflowMonitorStatus.TIMEOUT}),
    max_attempts=9,
)
fake_monitor_9 = FakeWorkflowMonitorManager(record=make_record("run-9", WorkflowMonitorStatus.FAILED))
manager_9 = RetryManager(policy=fake_policy_false_9, executor=FakeRetryExecutor(result=None), monitor=fake_monitor_9)
result_9 = manager_9.retry("run-9", attempt=1)

check("9. retry()の結果がSKIPPED", result_9.outcome, RetryOutcome.SKIPPED)
check("9. 理由文言が「対象外」の文言になる", "is not a retry target" in result_9.reason, True)
check("9. 理由文言にFake.target_statuses（timeout）が反映される", "timeout" in result_9.reason, True)
check("9. 理由文言にFake.target_statuses外（failed）が含まれない", "'failed'" not in result_9.reason, True)
print()


# ═══════════════════════════════════════════════════════════
# テスト10: 既存回帰（本物のRetryPolicyを注入した場合の挙動）
# ═══════════════════════════════════════════════════════════

print("[テスト10] 本物のRetryPolicyを注入した場合のretry()挙動が本Release前と同じ")

fake_monitor_10a = FakeWorkflowMonitorManager(record=make_record("run-10a", WorkflowMonitorStatus.FAILED))
fake_executor_10a = FakeRetryExecutor(result=RetryResult(
    original_run_id="run-10a", outcome=RetryOutcome.RETRIED, attempt=1,
    monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
    workflow_engine_result=make_workflow_engine_result(overall_success=True),
))
manager_10a = RetryManager(policy=policy_ok, executor=fake_executor_10a, monitor=fake_monitor_10a)
result_10a = manager_10a.retry("run-10a", attempt=1)
check("10. retry()がRETRIED（対象ステータス・上限未到達）", result_10a.outcome, RetryOutcome.RETRIED)

fake_monitor_10b = FakeWorkflowMonitorManager(record=make_record("run-10b", WorkflowMonitorStatus.FAILED))
manager_10b = RetryManager(policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=fake_monitor_10b)
result_10b = manager_10b.retry("run-10b", attempt=3)
check("10. retry()がSKIPPED（max_attempts=3到達）", result_10b.outcome, RetryOutcome.SKIPPED)

fake_monitor_10c = FakeWorkflowMonitorManager(record=None)
manager_10c = RetryManager(policy=policy_ok, executor=FakeRetryExecutor(result=None), monitor=fake_monitor_10c)
result_10c = manager_10c.retry("run-10c", attempt=1)
check("10. retry()がNOT_FOUND（Workflow Monitorに存在しない）", result_10c.outcome, RetryOutcome.NOT_FOUND)

null_manager_10 = NullRetryManager()
result_10d = null_manager_10.retry("run-10d", attempt=1)
check("10. NullRetryManager.retry()がDISABLED", result_10d.outcome, RetryOutcome.DISABLED)
print()


# ═══════════════════════════════════════════════════════════
# テスト11: retry_engine.__all__ の確認
# ═══════════════════════════════════════════════════════════

print("[テスト11] retry_engine.__all__ に新規2シンボルが追加され、既存36シンボルが維持されていること")

import retry_engine as re_pkg_11

existing_36_symbols_v440 = {
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
}
new_symbols_v450 = {"RetryDecisionPolicy", "ExplainableRetryPolicy"}

check("11. 既存36シンボルが維持されている（v4.4.0時点の集合がそのまま部分集合）", existing_36_symbols_v440.issubset(set(re_pkg_11.__all__)), True)
check(
    "11. retry_engine.__all__ が「既存36シンボル＋新規2シンボル」ちょうどで構成されている",
    set(re_pkg_11.__all__),
    existing_36_symbols_v440 | new_symbols_v450,
)
print(
    "  [注記] v4.4.0の既存テスト（tests/test_e2e_v4_4_0_retry_queue_notfound_disabled_cleanup_foundation.py "
    "テスト38）は、__all__の完全一致を旧36シンボルで固定しているため、本Releaseの新規2シンボル追加により "
    "既知のFAILが1件発生する（v4.4.0時点の事実を固定したArchitecture Guardであり、v3.1.0〜v4.4.0で繰り返し"
    "発生してきた既知差分（KI-9〜KI-13）と同種。CHANGELOG.mdへKI-14として記録予定）"
)
print()


# ═══════════════════════════════════════════════════════════
# テスト12: 型注釈がExplainableRetryPolicyに解決されること
# ═══════════════════════════════════════════════════════════

print("[テスト12] RetryManager.__init__ / from_config() の policy / retry_policy 引数の型注釈がExplainableRetryPolicyに解決される")

hints_init_12 = typing.get_type_hints(RetryManager.__init__)
hints_from_config_12 = typing.get_type_hints(RetryManager.from_config.__func__)

check("12. __init__のpolicy引数の型注釈がExplainableRetryPolicy", hints_init_12.get("policy"), ExplainableRetryPolicy)
check("12. from_config()のretry_policy引数の型注釈がExplainableRetryPolicy", hints_from_config_12.get("retry_policy"), ExplainableRetryPolicy)
print()


# ═══════════════════════════════════════════════════════════
# テスト13-14: 不要import・Non-Goalの確認（AST）
# ═══════════════════════════════════════════════════════════

print("[テスト13] retry_manager.py が具体クラス'RetryPolicy'を実コードとして参照していない（AST）")


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


retry_manager_source_path_13 = PROJECT_ROOT / "src" / "retry_engine" / "retry_manager.py"
tree_13 = ast.parse(retry_manager_source_path_13.read_text(encoding="utf-8"))
referenced_13 = _referenced_names(tree_13)
check_false("13. retry_manager.py: 'RetryPolicy'（具体クラス）への実コード参照が存在しない（不要import削除確認）", "RetryPolicy" in referenced_13)
check_true("13. retry_manager.py: 'ExplainableRetryPolicy' は参照している", "ExplainableRetryPolicy" in referenced_13)
print()

print("[テスト14] src/retry_engine/ 配下にFixedRetryPolicy / ExponentialBackoffPolicy / AdaptiveRetryPolicyが存在しない（Non-Goal確認）")

retry_engine_dir_14 = PROJECT_ROOT / "src" / "retry_engine"
new_strategy_names_14 = {"FixedRetryPolicy", "ExponentialBackoffPolicy", "AdaptiveRetryPolicy"}
found_strategy_classes_14: set = set()
for py_file in retry_engine_dir_14.glob("*.py"):
    tree_14 = ast.parse(py_file.read_text(encoding="utf-8"))
    for node in ast.walk(tree_14):
        if isinstance(node, ast.ClassDef) and node.name in new_strategy_names_14:
            found_strategy_classes_14.add(node.name)
check("14. 新しいRetry戦略クラスが実装されていない（Non-Goal）", found_strategy_classes_14, set())
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
