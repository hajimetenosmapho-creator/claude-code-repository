"""
E2E テスト: sub-milestone 6C — §28.-36節 WorkflowRunner Chain Invariant #37
direct closure（12件）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    2.2a節・25章 Invariant #37・28.-36節。

28.-12節が`WorkflowEngineContext`→`AgentContext`および News/Publish pipeline
runnerの一般的なpropagationを検証するのに対し、本ファイルは実際の
`WorkflowTriggerAgent`→`WorkflowPipelineRunner`→`WorkflowRunner`→
`WorkflowContext`→`PublishStepExecutor`という具体的なprotected chainを直接
exerciseする。`PublishStepExecutor.execute()`をauthoritative validation
boundaryとし（`validate_side_effect_execution_context()`を既存tryブロックの
外側で呼ぶ、22.3.12節）、`WorkflowPipelineRunner.run()`・
`AgentExecutor.execute()`という、さらに外側の2つのbroad `except Exception`
についてもcontract-error carve-outを検証する（sub-milestone 6Cで新設）。

実行方法:
    cd projects/03_game_content_ai
    .\\venv\\Scripts\\python.exe tests\\test_e2e_v6_32_9_invariant_37_workflowrunner_chain.py
"""
import ast
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
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


def check_false(label: str, value: bool):
    check(label, bool(value), False)


print("=" * 60)
print("§28.-36 WorkflowRunner Chain Invariant #37 direct closure E2E テスト")
print("=" * 60)
print()

from ai.agent_context import AgentContext  # noqa: E402
from ai.agent_task import AgentTask  # noqa: E402
from ai.agent_decision import AgentDecision  # noqa: E402
from ai.agent_executor import AgentExecutor  # noqa: E402
from ai.workflow_trigger_agent import WorkflowTriggerAgent  # noqa: E402
from ai.workflow_trigger_agent_config import WorkflowTriggerAgentConfig  # noqa: E402
from ai.workflow_runner import WorkflowRunner  # noqa: E402
from ai.workflow_config import WorkflowConfig  # noqa: E402
from ai.workflow_step import WorkflowStep  # noqa: E402
from ai.workflow_step_executor import PublishStepExecutor  # noqa: E402
from pipeline.workflow_pipeline_runner import WorkflowPipelineRunner  # noqa: E402
from side_effect_safety import (  # noqa: E402
    LegacyEntrypoint,
    LegacyExecutionOrigin,
    RetryLineageProtectedExecutionContext,
    SideEffectExecutionModeContractError,
    build_legacy_direct_provenance,
    build_protected_execution_context,
    complete_legacy_execution_context,
)
from side_effect_safety.side_effect_execution_mode import (  # noqa: E402
    ALLOWED_LEGACY_ENTRYPOINT_ORIGINS,
    ExecutionModeFailureReasonCode,
)

_PROTECTED_CONTEXT = build_protected_execution_context(
    root_run_id="root-36a", attempt_ordinal=2, member_run_id="member-36a",
    side_effect_contract_version=1,
)
_LEGACY_CONTEXT = complete_legacy_execution_context(
    build_legacy_direct_provenance(LegacyEntrypoint.RUN_WORKFLOW_TRIGGER_AGENT),
    LegacyExecutionOrigin.WORKFLOW_TRIGGER_AGENT,
)


def _make_workflow_trigger_agent_config(tmp_path: Path) -> WorkflowTriggerAgentConfig:
    return WorkflowTriggerAgentConfig(
        enabled=True, min_interval_minutes=1440, reports_dir=tmp_path / "reports",
        workflow_enabled=True, project_root=tmp_path,
    )


def _run_full_chain(tmp_path: Path, side_effect_execution_context, fake_service=None):
    """WorkflowTriggerAgent.act() → WorkflowPipelineRunner.run() →
    WorkflowRunner.run() → WorkflowContext → PublishStepExecutor.execute() →
    AiPublishService.run()/_process()/_post() の実chainを、AiPublishServiceの
    箇所だけspy化して実行する。戻り値は(AgentResult, fake_service)。
    """
    if fake_service is None:
        fake_service = MagicMock()
        fake_service.run.return_value = None
        fake_service.get_results.return_value = []

    publish_executor = PublishStepExecutor(service=fake_service)
    real_runner = WorkflowRunner(
        config=WorkflowConfig(enabled=True, steps=[WorkflowStep.PUBLISH], base_dir=tmp_path),
        executors=[publish_executor],
    )

    with patch("ai.WorkflowRunner.from_config", return_value=real_runner):
        wpr = WorkflowPipelineRunner(_make_workflow_trigger_agent_config(tmp_path))
        wta = WorkflowTriggerAgent(config=_make_workflow_trigger_agent_config(tmp_path), runner=wpr)
        agent_executor = AgentExecutor(wta)
        context = AgentContext(
            task=AgentTask(task_id="run_workflow", params={}),
            dry_run=False, run_id="run-36a", agent_name="",
            side_effect_execution_context=side_effect_execution_context,
        )
        result = agent_executor.execute(context)
    return result, fake_service


# ─── [テスト1] protected full-chain lossless propagation ───

print("[テスト1] protected contextがfull chainをlosslessに伝播する")

with __import__("tempfile").TemporaryDirectory() as tmpdir_1:
    result_1, fake_service_1 = _run_full_chain(Path(tmpdir_1), _PROTECTED_CONTEXT)

check_true("1a. AgentResult.success=True", result_1.success)
check("1b. service.run()が1回呼ばれる", fake_service_1.run.call_count, 1)
_received_ctx_1 = fake_service_1.run.call_args.kwargs.get("side_effect_execution_context")
check_true("1c. 受け取るcontextはRetryLineageProtectedExecutionContext", isinstance(_received_ctx_1, RetryLineageProtectedExecutionContext))
check("1d. root_run_idが完全一致", _received_ctx_1.root_run_id if _received_ctx_1 else None, "root-36a")
check("1e. attempt_ordinalが完全一致", _received_ctx_1.attempt_ordinal if _received_ctx_1 else None, 2)
check("1f. member_run_idが完全一致", _received_ctx_1.member_run_id if _received_ctx_1 else None, "member-36a")
check("1g. side_effect_contract_versionが完全一致", _received_ctx_1.side_effect_contract_version if _received_ctx_1 else None, 1)
print()


# ─── [テスト2] legacy full-chain lossless propagation ───

print("[テスト2] legacy context（WORKFLOW_TRIGGER_AGENT origin）がfull chainを伝播する")

with __import__("tempfile").TemporaryDirectory() as tmpdir_2:
    result_2, fake_service_2 = _run_full_chain(Path(tmpdir_2), _LEGACY_CONTEXT)

check_true("2a. AgentResult.success=True", result_2.success)
_received_ctx_2 = fake_service_2.run.call_args.kwargs.get("side_effect_execution_context")
check(
    "2b. legacy_execution_originがWORKFLOW_TRIGGER_AGENTのまま保持される（AI_WORKFLOW_DIRECTと混同されない）",
    _received_ctx_2.legacy_execution_origin if _received_ctx_2 else None,
    LegacyExecutionOrigin.WORKFLOW_TRIGGER_AGENT,
)
print()


# ─── [テスト3] WorkflowRunner-chain unknown context fail-closed ───

print("[テスト3] discriminated unionいずれでもないcontextはfail-closedする（external I/O=0）")

with __import__("tempfile").TemporaryDirectory() as tmpdir_3:
    fake_service_3 = MagicMock()
    fake_service_3.run.return_value = None
    fake_service_3.get_results.return_value = []
    raised_3 = None
    try:
        _run_full_chain(Path(tmpdir_3), object(), fake_service=fake_service_3)
    except SideEffectExecutionModeContractError as e:
        raised_3 = e
    except Exception as e:
        raised_3 = e

check_true("3a. SideEffectExecutionModeContractErrorが送出される", isinstance(raised_3, SideEffectExecutionModeContractError))
check(
    "3b. reason_codeはUNKNOWN_EXECUTION_MODE",
    raised_3.reason_code if raised_3 else None,
    ExecutionModeFailureReasonCode.UNKNOWN_EXECUTION_MODE,
)
check("3c. AiPublishServiceのrun()は一切呼ばれない（external I/O=0）", fake_service_3.run.call_count, 0)
print()


# ─── [テスト4] missing context + correlation metadataからの再構築禁止 ───

print("[テスト4] context欠落（None）はcorrelation metadata等から再構築されずfail-closedする")

with __import__("tempfile").TemporaryDirectory() as tmpdir_4:
    fake_service_4 = MagicMock()
    fake_service_4.run.return_value = None
    fake_service_4.get_results.return_value = []

    publish_executor_4 = PublishStepExecutor(service=fake_service_4)
    real_runner_4 = WorkflowRunner(
        config=WorkflowConfig(enabled=True, steps=[WorkflowStep.PUBLISH], base_dir=Path(tmpdir_4)),
        executors=[publish_executor_4],
    )
    with patch("ai.WorkflowRunner.from_config", return_value=real_runner_4):
        wpr_4 = WorkflowPipelineRunner(_make_workflow_trigger_agent_config(Path(tmpdir_4)))
        wta_4 = WorkflowTriggerAgent(config=_make_workflow_trigger_agent_config(Path(tmpdir_4)), runner=wpr_4)
        agent_executor_4 = AgentExecutor(wta_4)
        # fakeなcorrelation metadata/task paramsに正規contextと同型の値を混入させる
        fake_task_4 = AgentTask(
            task_id="run_workflow",
            params={
                "root_run_id": "fake-root", "attempt_ordinal": 1,
                "member_run_id": "fake-member", "side_effect_contract_version": 1,
            },
        )
        context_4 = AgentContext(
            task=fake_task_4, dry_run=False, run_id="run-36d", agent_name="",
            side_effect_execution_context=None,
        )
        raised_4 = None
        try:
            agent_executor_4.execute(context_4)
        except SideEffectExecutionModeContractError as e:
            raised_4 = e

check_true("4a. SideEffectExecutionModeContractErrorが送出される", isinstance(raised_4, SideEffectExecutionModeContractError))
check(
    "4b. reason_codeはMISSING_EXECUTION_MODE",
    raised_4.reason_code if raised_4 else None,
    ExecutionModeFailureReasonCode.MISSING_EXECUTION_MODE,
)
check("4c. task.paramsのfake値からcontextが再構築されない（AiPublishService到達=0）", fake_service_4.run.call_count, 0)
print()


# ─── [テスト5] protected→legacy silent downgrade = 0 ───

print("[テスト5] protected contextはchain中いずれのboundaryでも型が変化しない")

with __import__("tempfile").TemporaryDirectory() as tmpdir_5:
    result_5, fake_service_5 = _run_full_chain(Path(tmpdir_5), _PROTECTED_CONTEXT)
_received_ctx_5 = fake_service_5.run.call_args.kwargs.get("side_effect_execution_context")
check_true("5a. 最終到達時点でもRetryLineageProtectedExecutionContextのまま", isinstance(_received_ctx_5, RetryLineageProtectedExecutionContext))
print()


# ─── [テスト6] legacy→protected silent upgrade = 0 ───

print("[テスト6] legacy contextはchain中いずれのboundaryでも型が変化しない")

with __import__("tempfile").TemporaryDirectory() as tmpdir_6:
    result_6, fake_service_6 = _run_full_chain(Path(tmpdir_6), _LEGACY_CONTEXT)
_received_ctx_6 = fake_service_6.run.call_args.kwargs.get("side_effect_execution_context")
check_false("6a. 最終到達時点でRetryLineageProtectedExecutionContextへ変化していない", isinstance(_received_ctx_6, RetryLineageProtectedExecutionContext))
print()


# ─── [テスト7] contract errorのgeneric catch非吸収（AST監査＋実行時観測） ───

print("[テスト7] PublishStepExecutor.execute()のvalidateがtryブロックの外側にある（AST監査）")

_source_pse = (PROJECT_ROOT / "src" / "ai" / "workflow_step_executor.py").read_text(encoding="utf-8")
_tree_pse = ast.parse(_source_pse)


def _find_class_method(tree, class_name, method_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == method_name:
                    return item
    return None


_execute_method = _find_class_method(_tree_pse, "PublishStepExecutor", "execute")
check_true("7a. PublishStepExecutor.execute()が存在する", _execute_method is not None)

if _execute_method is not None:
    _validate_calls = [
        n for n in ast.walk(_execute_method)
        if isinstance(n, ast.Call)
        and (
            (isinstance(n.func, ast.Name) and n.func.id == "validate_side_effect_execution_context")
            or (isinstance(n.func, ast.Attribute) and n.func.attr == "validate_side_effect_execution_context")
        )
    ]
    check("7b. validate_side_effect_execution_context()呼び出しが1件存在する", len(_validate_calls), 1)

    _try_nodes = [n for n in ast.walk(_execute_method) if isinstance(n, ast.Try)]
    _validate_inside_try = False
    for _try in _try_nodes:
        for _n in ast.walk(_try):
            if _n in _validate_calls:
                _validate_inside_try = True
    check_false("7c. validate呼び出しがtryブロックの内側にない（外側に位置する）", _validate_inside_try)

check_true("7d. テスト3の実行観測でSideEffectExecutionModeContractErrorがWorkflowStepResultへ変換されず伝播した", isinstance(raised_3, SideEffectExecutionModeContractError))
print()


# ─── [テスト8] contract errorがStage-1 callerまで生存すること（full chain + AST監査） ───

print("[テスト8] contract errorはWorkflowPipelineRunner/AgentExecutorのexcept節にも捕捉されず伝播する")


def _except_handlers_of(tree, func_name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return [n for n in ast.walk(node) if isinstance(n, ast.ExceptHandler)]
    return []


_wpr_source = (PROJECT_ROOT / "src" / "pipeline" / "workflow_pipeline_runner.py").read_text(encoding="utf-8")
_wpr_tree = ast.parse(_wpr_source)
_wpr_handlers = _except_handlers_of(_wpr_tree, "run")
_wpr_handler_types = [
    h.type.id if isinstance(h.type, ast.Name) else None for h in _wpr_handlers
]
check_true(
    "8a. WorkflowPipelineRunner.run()にexcept SideEffectExecutionModeContractError: raise節が存在する",
    "SideEffectExecutionModeContractError" in _wpr_handler_types,
)

_ae_source = (PROJECT_ROOT / "src" / "ai" / "agent_executor.py").read_text(encoding="utf-8")
_ae_tree = ast.parse(_ae_source)
_ae_handlers = _except_handlers_of(_ae_tree, "execute")
_ae_handler_types = [
    h.type.id if isinstance(h.type, ast.Name) else None for h in _ae_handlers
]
check_true(
    "8b. AgentExecutor.execute()にexcept SideEffectExecutionModeContractError: raise節が存在する",
    "SideEffectExecutionModeContractError" in _ae_handler_types,
)

check_true(
    "8c. 実行時：contract errorはAgentExecutor.execute()の呼び出し元まで未変換のまま伝播する（テスト3で確認済み）",
    isinstance(raised_3, SideEffectExecutionModeContractError),
)
check("8d. AiPublishServiceへの到達=0（テスト3で確認済み）", fake_service_3.run.call_count, 0)
print()


# ─── [テスト9] malformed protected context、full-chain fail-closed ───

print("[テスト9] malformed protected contextの各フィールドはfull chainでfail-closedする")

_malformed_protected_cases = [
    ("root_run_id=''", RetryLineageProtectedExecutionContext(
        root_run_id="", attempt_ordinal=1, member_run_id="m", side_effect_contract_version=1,
    ), ExecutionModeFailureReasonCode.MISSING_LINEAGE_CONTEXT),
    ("attempt_ordinal=-1", RetryLineageProtectedExecutionContext(
        root_run_id="r", attempt_ordinal=-1, member_run_id="m", side_effect_contract_version=1,
    ), ExecutionModeFailureReasonCode.CONTEXT_MISMATCH),
    ("member_run_id=''", RetryLineageProtectedExecutionContext(
        root_run_id="r", attempt_ordinal=1, member_run_id="", side_effect_contract_version=1,
    ), ExecutionModeFailureReasonCode.CONTEXT_MISMATCH),
    ("side_effect_contract_version=0", RetryLineageProtectedExecutionContext(
        root_run_id="r", attempt_ordinal=1, member_run_id="m", side_effect_contract_version=0,
    ), ExecutionModeFailureReasonCode.CONTRACT_VERSION_MISMATCH),
]

for label, malformed_ctx, expected_reason in _malformed_protected_cases:
    with __import__("tempfile").TemporaryDirectory() as tmpdir_9:
        fake_service_9 = MagicMock()
        fake_service_9.run.return_value = None
        fake_service_9.get_results.return_value = []
        raised_9 = None
        try:
            _run_full_chain(Path(tmpdir_9), malformed_ctx, fake_service=fake_service_9)
        except SideEffectExecutionModeContractError as e:
            raised_9 = e
        check_true(f"9. [{label}] SideEffectExecutionModeContractErrorが送出される", raised_9 is not None)
        check(f"9. [{label}] reason_code", raised_9.reason_code if raised_9 else None, expected_reason)
        check(f"9. [{label}] AiPublishServiceへの到達=0", fake_service_9.run.call_count, 0)
print()


# ─── [テスト10] malformed/mismatched legacy context、full-chain fail-closed ───

print("[テスト10] malformed legacy contextの各フィールドはfull chainでfail-closedする")

from side_effect_safety import LegacyDirectExecutionContext  # noqa: E402

_malformed_legacy_cases = [
    ("legacy_entrypoint=unknown", LegacyDirectExecutionContext(
        legacy_entrypoint="not-a-real-entrypoint", legacy_execution_origin=LegacyExecutionOrigin.WORKFLOW_TRIGGER_AGENT,
    ), ExecutionModeFailureReasonCode.UNKNOWN_LEGACY_ENTRYPOINT),
    ("legacy_execution_origin=unknown", LegacyDirectExecutionContext(
        legacy_entrypoint=LegacyEntrypoint.RUN_WORKFLOW_TRIGGER_AGENT, legacy_execution_origin="not-a-real-origin",
    ), ExecutionModeFailureReasonCode.UNKNOWN_LEGACY_EXECUTION_ORIGIN),
]

for label, malformed_ctx, expected_reason in _malformed_legacy_cases:
    with __import__("tempfile").TemporaryDirectory() as tmpdir_10:
        fake_service_10 = MagicMock()
        fake_service_10.run.return_value = None
        fake_service_10.get_results.return_value = []
        raised_10 = None
        try:
            _run_full_chain(Path(tmpdir_10), malformed_ctx, fake_service=fake_service_10)
        except SideEffectExecutionModeContractError as e:
            raised_10 = e
        check_true(f"10. [{label}] SideEffectExecutionModeContractErrorが送出される", raised_10 is not None)
        check(f"10. [{label}] reason_code", raised_10.reason_code if raised_10 else None, expected_reason)
        check(f"10. [{label}] AiPublishServiceへの到達=0", fake_service_10.run.call_count, 0)
print()


# ─── [テスト11] contradictory legacy pair ───

print("[テスト11] individually-validだが組み合わせ不正なlegacy pairはfull chainでfail-closedする")

_contradictory_pair_ctx = LegacyDirectExecutionContext(
    legacy_entrypoint=LegacyEntrypoint.RUN_AI_PUBLISH, legacy_execution_origin=LegacyExecutionOrigin.NEWS_AGENT,
)
check_false(
    "11a. この組み合わせはALLOWED_LEGACY_ENTRYPOINT_ORIGINSに存在しない（fixtureの前提確認）",
    (LegacyEntrypoint.RUN_AI_PUBLISH, LegacyExecutionOrigin.NEWS_AGENT) in ALLOWED_LEGACY_ENTRYPOINT_ORIGINS,
)

with __import__("tempfile").TemporaryDirectory() as tmpdir_11:
    fake_service_11 = MagicMock()
    fake_service_11.run.return_value = None
    fake_service_11.get_results.return_value = []
    raised_11 = None
    try:
        _run_full_chain(Path(tmpdir_11), _contradictory_pair_ctx, fake_service=fake_service_11)
    except SideEffectExecutionModeContractError as e:
        raised_11 = e
check_true("11b. SideEffectExecutionModeContractErrorが送出される", raised_11 is not None)
check(
    "11c. reason_codeはCONTRADICTORY_LEGACY_PAIR",
    raised_11.reason_code if raised_11 else None,
    ExecutionModeFailureReasonCode.CONTRADICTORY_LEGACY_PAIR,
)
check("11d. AiPublishServiceへの到達=0", fake_service_11.run.call_count, 0)
print()


# ─── [テスト12] 一般的なambient environment stateからの再構築禁止 ───

print("[テスト12] correlation metadata/task params以外のambient stateからも再構築されない")

import os as _os  # noqa: E402

with __import__("tempfile").TemporaryDirectory() as tmpdir_12:
    _os.environ["RETRY_LINEAGE_ROOT_RUN_ID_LOOKALIKE"] = "fake-root-12"  # 正規変数名ではない非公式env var
    try:
        fake_service_12 = MagicMock()
        fake_service_12.run.return_value = None
        fake_service_12.get_results.return_value = []
        raised_12 = None
        try:
            _run_full_chain(Path(tmpdir_12), None, fake_service=fake_service_12)
        except SideEffectExecutionModeContractError as e:
            raised_12 = e
    finally:
        _os.environ.pop("RETRY_LINEAGE_ROOT_RUN_ID_LOOKALIKE", None)

check_true("12a. SideEffectExecutionModeContractErrorが送出される", raised_12 is not None)
check(
    "12b. reason_codeはMISSING_EXECUTION_MODE（非公式env varから再構築されない）",
    raised_12.reason_code if raised_12 else None,
    ExecutionModeFailureReasonCode.MISSING_EXECUTION_MODE,
)
check("12c. AiPublishServiceへの到達=0", fake_service_12.run.call_count, 0)
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
