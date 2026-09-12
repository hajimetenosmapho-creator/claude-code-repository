"""
E2E テスト: v6.32.2 Protected/Legacy Provenance Propagation

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    2.6節（Propagation Contract）・14.2節（_serialize_execution_context()）・
    2.3節（AgentManager fan-out legacy provenance）

sub-milestone 2（protected/legacy provenance・execution context伝播）の
direct tests。main.py側の解決・実際の呼び出し箇所A/B/Cでの消費は
sub-milestone 3〜5で扱うため、本テストは「型がchannelを正しく流れること」
のみを検証する。

実行方法:
    cd projects/03_game_content_ai
    .\\venv\\Scripts\\python.exe tests\\test_e2e_v6_32_2_provenance_propagation.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

results_log = []


def check(label: str, actual, expected):
    ok = actual == expected
    status = "PASS" if ok else "FAIL"
    results_log.append((status, label))
    mark = "OK" if ok else "NG"
    print(f"  [{mark}] {label}")
    if not ok:
        print(f"       期待値: {expected!r}")
        print(f"       実際値: {actual!r}")


def check_true(label: str, value: bool):
    check(label, bool(value), True)


print("=" * 60)
print("v6.32.2 Provenance Propagation E2E テスト")
print("=" * 60)
print()

from ai import AgentContext, AgentTask  # noqa: E402
from ai.agent_manager import _AGENT_TYPE_TO_LEGACY_ORIGIN  # noqa: E402
from ai.news_agent import NewsAgent  # noqa: E402
from ai.publish_trigger_agent import PublishTriggerAgent  # noqa: E402
from ai.workflow_trigger_agent import WorkflowTriggerAgent  # noqa: E402
from workflow_engine.workflow_engine_context import WorkflowEngineContext  # noqa: E402
from workflow_engine.workflow_engine_event import WorkflowEngineEvent  # noqa: E402
from workflow_engine.workflow_engine_executor import (  # noqa: E402
    _complete_side_effect_execution_context,
)
from side_effect_safety import (  # noqa: E402
    LegacyEntrypoint,
    LegacyExecutionOrigin,
    RetryLineageProtectedExecutionContext,
    RetryLineageProtectedProvenance,
    build_legacy_direct_provenance,
    complete_legacy_execution_context,
)
from side_effect_safety.side_effect_execution_mode import (  # noqa: E402
    _parse_and_validate_remaining_context,
    _serialize_execution_context,
)


# ─── [テスト1] AgentContext / WorkflowEngineContext フィールド ───

print("[テスト1] AgentContext / WorkflowEngineContext のside_effect fieldがデフォルトNone")

ctx1 = AgentContext(task=AgentTask(task_id="t", params={}), dry_run=False, run_id="r1", agent_name="")
check("1a. AgentContext.side_effect_execution_contextはデフォルトNone", ctx1.side_effect_execution_context, None)

wec1 = WorkflowEngineContext(
    event=WorkflowEngineEvent(job_id="j1", source="manual", triggered_at=None, trigger_reason="t"),
    dry_run=False, run_id="r1",
)
check("1b. WorkflowEngineContext.side_effect_execution_provenanceはデフォルトNone", wec1.side_effect_execution_provenance, None)
print()


# ─── [テスト2] _complete_side_effect_execution_context()（2.2a節(2)） ───

print("[テスト2] _complete_side_effect_execution_context()")

check("2a. provenance=Noneはそのまま None", _complete_side_effect_execution_context(None, "run-x"), None)

legacy_ctx = complete_legacy_execution_context(
    build_legacy_direct_provenance(LegacyEntrypoint.RUN_WORKFLOW_ENGINE_DIRECT),
    LegacyExecutionOrigin.WORKFLOW_ENGINE_DIRECT,
)
check_true("2b. LegacyDirectExecutionContextはそのまま返る", _complete_side_effect_execution_context(legacy_ctx, "run-x") is legacy_ctx)

pre_context = RetryLineageProtectedProvenance(root_run_id="root-1", attempt_ordinal=2, side_effect_contract_version=1)
completed = _complete_side_effect_execution_context(pre_context, "member-run-9")
check_true("2c. RetryLineageProtectedProvenanceはRetryLineageProtectedExecutionContextへ完成される", isinstance(completed, RetryLineageProtectedExecutionContext))
check("2d. root_run_id/attempt_ordinal/contract_versionは元のprovenanceの値を保持", (completed.root_run_id, completed.attempt_ordinal, completed.side_effect_contract_version), ("root-1", 2, 1))
check("2e. member_run_idはWorkflowEngineExecutor自身のrun_idで補完される", completed.member_run_id, "member-run-9")
print()


# ─── [テスト3] AgentManager fan-out legacy provenance mapping（2.3節） ───

print("[テスト3] AgentManager fan-out Agent型 → LegacyExecutionOrigin対応表")

check("3a. NewsAgent → NEWS_AGENT", _AGENT_TYPE_TO_LEGACY_ORIGIN.get(NewsAgent), LegacyExecutionOrigin.NEWS_AGENT)
check("3b. WorkflowTriggerAgent → WORKFLOW_TRIGGER_AGENT", _AGENT_TYPE_TO_LEGACY_ORIGIN.get(WorkflowTriggerAgent), LegacyExecutionOrigin.WORKFLOW_TRIGGER_AGENT)
check("3c. PublishTriggerAgent → PUBLISH_TRIGGER_AGENT", _AGENT_TYPE_TO_LEGACY_ORIGIN.get(PublishTriggerAgent), LegacyExecutionOrigin.PUBLISH_TRIGGER_AGENT)
print()


# ─── [テスト4] 14.2節 _serialize_execution_context() ───

print("[テスト4] _serialize_execution_context()")

protected_ctx = RetryLineageProtectedExecutionContext(
    root_run_id="root-9", attempt_ordinal=3, member_run_id="member-9", side_effect_contract_version=1,
)
env_protected = _serialize_execution_context(protected_ctx)
check("4a. protected: RETRY_LINEAGE_EXECUTION_MODE", env_protected["RETRY_LINEAGE_EXECUTION_MODE"], "retry_lineage_protected")
check("4b. protected: RETRY_LINEAGE_ROOT_RUN_ID", env_protected["RETRY_LINEAGE_ROOT_RUN_ID"], "root-9")
check("4c. protected: RETRY_LINEAGE_ATTEMPT_ORDINAL", env_protected["RETRY_LINEAGE_ATTEMPT_ORDINAL"], "3")
check("4d. protected: RETRY_LINEAGE_MEMBER_RUN_ID", env_protected["RETRY_LINEAGE_MEMBER_RUN_ID"], "member-9")
check("4e. protected: RETRY_LINEAGE_CONTRACT_VERSION", env_protected["RETRY_LINEAGE_CONTRACT_VERSION"], "1")
check_true("4f. protected: legacy用keyを含まない", "RETRY_LINEAGE_LEGACY_ENTRYPOINT" not in env_protected)

env_legacy = _serialize_execution_context(legacy_ctx)
check("4g. legacy: RETRY_LINEAGE_EXECUTION_MODE", env_legacy["RETRY_LINEAGE_EXECUTION_MODE"], "legacy_direct")
check("4h. legacy: RETRY_LINEAGE_LEGACY_ENTRYPOINT", env_legacy["RETRY_LINEAGE_LEGACY_ENTRYPOINT"], "run_workflow_engine_direct")
check("4i. legacy: RETRY_LINEAGE_LEGACY_EXECUTION_ORIGIN", env_legacy["RETRY_LINEAGE_LEGACY_EXECUTION_ORIGIN"], "workflow_engine_direct")
check_true("4j. legacy: protected用keyを含まない", "RETRY_LINEAGE_ROOT_RUN_ID" not in env_legacy)
print()


# ─── [テスト5] _parse_and_validate_remaining_context() round-trip ───

print("[テスト5] serialize→parse round-trip")

attempt_ordinal, member_run_id, contract_version = _parse_and_validate_remaining_context(
    env_protected["RETRY_LINEAGE_ATTEMPT_ORDINAL"],
    env_protected["RETRY_LINEAGE_MEMBER_RUN_ID"],
    env_protected["RETRY_LINEAGE_CONTRACT_VERSION"],
)
check("5a. attempt_ordinal round-trip", attempt_ordinal, 3)
check("5b. member_run_id round-trip", member_run_id, "member-9")
check("5c. contract_version round-trip", contract_version, 1)
print()


# ─── 結果サマリー ───

print("=" * 60)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = sum(1 for status, _ in results_log if status == "FAIL")
print(f"結果: {passed} PASS / {failed} FAIL / 合計 {len(results_log)}")
if failed:
    print("失敗したテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
print("全テストPASS")
