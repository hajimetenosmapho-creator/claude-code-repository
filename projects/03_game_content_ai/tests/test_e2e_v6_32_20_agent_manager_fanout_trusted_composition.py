"""
E2E テスト: Release 6.32 AgentManager fan-out / Trusted Composition Boundary
execution-based evidence（§28.-19・§28.-20）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    2.3節（AgentManager fan-out）・22.3.12節（run_ai_workflow.py composition point）・
    28.-19節（8件）・28.-20節（14件）。

本ファイルは、Canonical Gap Inventoryのread-only照合で判明した
「既存test_e2e_v6_32_2_provenance_propagation.pyは`_AGENT_TYPE_TO_LEGACY_ORIGIN`
という静的dictの参照のみを確認しており、実際に`AgentManager.from_config()`→
`AgentManager.run(legacy_provenance=...)`を実行して各executorが受け取る
実contextを直接検証していない」というexecution-based evidenceの欠落のみを
埋める。§28.-14（Trusted Composition Boundary Validator）・§28.-34#3（closure
oracle）等、既にCOMPLETEなstatic/closure oracleは再実装しない。

対象:
    Part A（§28.-19、AgentManager実fan-out）: `AgentManager.from_config()`を
        実際のgate環境変数で構築し、`run(task, dry_run=True, legacy_provenance=...)`
        を実行して各`AgentExecutor.execute()`へ渡される実際の`AgentContext`を
        spyで捕捉する（本番I/Oなし、dry_run=Trueによりact()は呼ばれない）。
    Part B（§28.-20、run_ai_workflow.py legacy composition）: `run_ai_workflow.py`
        と同一の構成（`WorkflowRunner(config, executors=[PublishStepExecutor(...)])`
        + `AI_WORKFLOW_DIRECT` context）を直接実行し、`AiPublishService.run()`
        （fake）まで実際にcontextが伝播することを確認する
        （test_e2e_v6_32_9のfake-service-spy技法をWORKFLOW_TRIGGER_AGENT経路
        からAI_WORKFLOW_DIRECT直接経路へ適用する）。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_20_agent_manager_fanout_trusted_composition.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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
print("AgentManager fan-out / Trusted Composition Boundary（§28.-19・-20）E2E テスト")
print("=" * 60)
print()

from ai.agent_config import AgentConfig  # noqa: E402
from ai.agent_context import AgentContext  # noqa: E402
from ai.agent_manager import AgentManager, NullAgentManager  # noqa: E402
from ai.agent_result import AgentResult  # noqa: E402
from ai.agent_task import AgentTask  # noqa: E402
from ai.agent_decision import AgentDecision  # noqa: E402
from ai.news_agent import NewsAgent  # noqa: E402
from ai.publish_trigger_agent import PublishTriggerAgent  # noqa: E402
from ai.review_trigger_agent import ReviewTriggerAgent  # noqa: E402
from ai.workflow_trigger_agent import WorkflowTriggerAgent  # noqa: E402
from ai.workflow_config import WorkflowConfig  # noqa: E402
from ai.workflow_runner import WorkflowRunner  # noqa: E402
from ai.workflow_step import WorkflowStep  # noqa: E402
from ai.workflow_step_executor import PublishStepExecutor  # noqa: E402
from side_effect_safety import (  # noqa: E402
    LegacyDirectExecutionContext,
    LegacyEntrypoint,
    LegacyExecutionOrigin,
    SideEffectExecutionModeContractError,
    build_legacy_direct_provenance,
    complete_legacy_execution_context,
)
from side_effect_safety.side_effect_execution_mode import ExecutionModeFailureReasonCode  # noqa: E402

_ALL_GATE_ENV_KEYS = (
    "AI_AGENT_ENABLED",
    "WORKFLOW_TRIGGER_AGENT_ENABLED", "AI_WORKFLOW_ENABLED",
    "PUBLISH_TRIGGER_AGENT_ENABLED", "AI_PUBLISH_ENABLED",
    "WORDPRESS_URL", "WORDPRESS_USERNAME", "WORDPRESS_APP_PASSWORD",
    "REVIEW_TRIGGER_AGENT_ENABLED",
)


def _clear_gate_env():
    for key in _ALL_GATE_ENV_KEYS:
        os.environ.pop(key, None)


def _spy_manager(manager: AgentManager):
    """各executorの execute() を捕捉spyへ差し替え、実agentロジック
    （decide()/act()）を一切呼ばない。captured: 実際にexecute()へ渡された
    AgentContextのリスト（executors登録順）。"""
    captured: list[AgentContext] = []

    def _make_spy(index: int):
        def _spy(context: AgentContext) -> AgentResult:
            captured.append(context)
            return AgentResult(
                run_id=context.run_id, agent_name=f"spy-{index}", task=context.task,
                decision=AgentDecision(should_act=False, reason="spy"),
                action_taken=False, success=True, workflow_result=None,
                error_message=None, started_at=None, finished_at=None,
            )
        return _spy

    for i, executor in enumerate(manager._executors):
        executor.execute = _make_spy(i)
    return captured


# =====================================================================
# Part A: AgentManager 実fan-out（§28.-19）
# =====================================================================

# ─── [A1] 4 gate全有効 → 4executorsの実fan-out、各contextのexact検証 ───

print("[A1] 4 gate全有効でAgentManager.run(legacy_provenance=...)を実行 → 4executorsの実fan-out")

tmp_a1 = Path(tempfile.mkdtemp(prefix="v6_32_20_a1_"))
_clear_gate_env()
os.environ["WORKFLOW_TRIGGER_AGENT_ENABLED"] = "true"
os.environ["AI_WORKFLOW_ENABLED"] = "true"
os.environ["PUBLISH_TRIGGER_AGENT_ENABLED"] = "true"
os.environ["AI_PUBLISH_ENABLED"] = "true"
os.environ["WORDPRESS_URL"] = "https://example.test"
os.environ["WORDPRESS_USERNAME"] = "user"
os.environ["WORDPRESS_APP_PASSWORD"] = "app-password"
os.environ["REVIEW_TRIGGER_AGENT_ENABLED"] = "true"

config_a1 = AgentConfig(enabled=True, base_dir=tmp_a1)
manager_a1 = AgentManager.from_config(config_a1)
check_true("A1a. AgentManagerが返る", isinstance(manager_a1, AgentManager))
check("A1b. 4 executorsが登録される", len(manager_a1._executors), 4)

captured_a1 = _spy_manager(manager_a1)
legacy_provenance_a1 = build_legacy_direct_provenance(LegacyEntrypoint.RUN_NEWS_AGENT)
task_a1 = AgentTask(task_id="run_all", params={})
results_a1 = manager_a1.run(task_a1, dry_run=True, legacy_provenance=legacy_provenance_a1)

check("A1c. run()が4件のAgentResultを返す（実fan-out、単一run()呼び出し内で全executor実行）", len(results_a1), 4)
check("A1d. 4 executorすべてが実際にexecute()を呼ばれる", len(captured_a1), 4)

_expected_origins_a1 = [
    LegacyExecutionOrigin.NEWS_AGENT,
    LegacyExecutionOrigin.WORKFLOW_TRIGGER_AGENT,
    LegacyExecutionOrigin.PUBLISH_TRIGGER_AGENT,
    LegacyExecutionOrigin.REVIEW_TRIGGER_AGENT,
]
for idx, expected_origin in enumerate(_expected_origins_a1):
    ctx = captured_a1[idx]
    check_true(f"A1e-{idx}. executor[{idx}]はLegacyDirectExecutionContextを受け取る", isinstance(ctx.side_effect_execution_context, LegacyDirectExecutionContext))
    check(f"A1f-{idx}. executor[{idx}]のlegacy_execution_originが正しい型に対応する", ctx.side_effect_execution_context.legacy_execution_origin, expected_origin)
    check("A1g-%d. legacy_entrypointは共有された同一値" % idx, ctx.side_effect_execution_context.legacy_entrypoint, LegacyEntrypoint.RUN_NEWS_AGENT)

# 4つのLegacyDirectExecutionContextインスタンスが相互に異なるオブジェクトであること
_ctx_ids_a1 = {id(captured_a1[i].side_effect_execution_context) for i in range(4)}
check("A1h. 4つのLegacyDirectExecutionContextインスタンスは相互に別オブジェクト（mutable/shared reuse=0）", len(_ctx_ids_a1), 4)
print()


# ─── [A2] mapping対応表に存在しない未知Agent型 → context=None、他executorへ影響なし ───

print("[A2] 未知Agent型のexecutorはcontext=Noneのまま構築される（他executorに影響なし）")

tmp_a2 = Path(tempfile.mkdtemp(prefix="v6_32_20_a2_"))
_clear_gate_env()
config_a2 = AgentConfig(enabled=True, base_dir=tmp_a2)
manager_a2 = AgentManager.from_config(config_a2)
check("A2a. 事前条件: NewsAgentのみ1件登録", len(manager_a2._executors), 1)

from ai.agent_executor import AgentExecutor  # noqa: E402


class _UnmappedAgent:
    """2.3節mapping対応表に存在しない、テスト専用の未知Agent型。"""

    def decide(self, context):
        raise AssertionError("spyへ差し替え済みのため呼ばれないはず")

    def act(self, decision, context):
        raise AssertionError("spyへ差し替え済みのため呼ばれないはず")

    def name(self):
        return "unmapped-test-agent"


manager_a2._executors.append(AgentExecutor(_UnmappedAgent()))
check("A2b. 未知Agent型executorを追加後は2件", len(manager_a2._executors), 2)

captured_a2 = _spy_manager(manager_a2)
legacy_provenance_a2 = build_legacy_direct_provenance(LegacyEntrypoint.RUN_NEWS_AGENT)
results_a2 = manager_a2.run(AgentTask(task_id="t", params={}), dry_run=True, legacy_provenance=legacy_provenance_a2)

check("A2c. 2件とも実行される", len(captured_a2), 2)
check_true("A2d. NewsAgent（mapping対応表内）は正しくLegacyDirectExecutionContextを受け取る", isinstance(captured_a2[0].side_effect_execution_context, LegacyDirectExecutionContext))
check("A2e. NewsAgentのorigin_はNEWS_AGENT（未知Agent型追加の影響を受けない）", captured_a2[0].side_effect_execution_context.legacy_execution_origin, LegacyExecutionOrigin.NEWS_AGENT)
check_true("A2f. 未知Agent型のcontextはNoneのまま（推測されない）", captured_a2[1].side_effect_execution_context is None)
print()


# ─── [A3] run_publish_trigger_agent.py相当の構成（NewsAgent + PublishTriggerAgentのみ）───

print("[A3] run_publish_trigger_agent.py相当の構成（PUBLISH_TRIGGER_AGENT_ENABLEDのみ）")

tmp_a3 = Path(tempfile.mkdtemp(prefix="v6_32_20_a3_"))
_clear_gate_env()
os.environ["PUBLISH_TRIGGER_AGENT_ENABLED"] = "true"
os.environ["AI_PUBLISH_ENABLED"] = "true"
os.environ["WORDPRESS_URL"] = "https://example.test"
os.environ["WORDPRESS_USERNAME"] = "user"
os.environ["WORDPRESS_APP_PASSWORD"] = "app-password"

config_a3 = AgentConfig(enabled=True, base_dir=tmp_a3)
manager_a3 = AgentManager.from_config(config_a3)
check("A3a. NewsAgent + PublishTriggerAgentの2件のみ登録される", len(manager_a3._executors), 2)
check_true("A3b. executors[0]がNewsAgent", isinstance(manager_a3._executors[0]._agent, NewsAgent))
check_true("A3c. executors[1]がPublishTriggerAgent", isinstance(manager_a3._executors[1]._agent, PublishTriggerAgent))

captured_a3 = _spy_manager(manager_a3)
legacy_provenance_a3 = build_legacy_direct_provenance(LegacyEntrypoint.RUN_PUBLISH_TRIGGER_AGENT)
manager_a3.run(AgentTask(task_id="t", params={}), dry_run=True, legacy_provenance=legacy_provenance_a3)

check(
    "A3d. NewsAgentはNEWS_AGENT origin（起動scriptがpublish_trigger_agentでもNewsAgent自身の型で決まる）",
    captured_a3[0].side_effect_execution_context.legacy_execution_origin, LegacyExecutionOrigin.NEWS_AGENT,
)
check(
    "A3e. PublishTriggerAgentはPUBLISH_TRIGGER_AGENT origin",
    captured_a3[1].side_effect_execution_context.legacy_execution_origin, LegacyExecutionOrigin.PUBLISH_TRIGGER_AGENT,
)
print()


# ─── [A4] run_review_trigger_agent.py相当の構成（launcher-name reachability inference = 0） ───

print("[A4] run_review_trigger_agent.py相当の構成でも、config次第でNews/Workflow/Reviewが実fan-outする")

tmp_a4 = Path(tempfile.mkdtemp(prefix="v6_32_20_a4_"))
_clear_gate_env()
os.environ["WORKFLOW_TRIGGER_AGENT_ENABLED"] = "true"
os.environ["AI_WORKFLOW_ENABLED"] = "true"
os.environ["REVIEW_TRIGGER_AGENT_ENABLED"] = "true"

config_a4 = AgentConfig(enabled=True, base_dir=tmp_a4)
manager_a4 = AgentManager.from_config(config_a4)
check("A4a. NewsAgent + WorkflowTriggerAgent + ReviewTriggerAgentの3件が登録される", len(manager_a4._executors), 3)
check_true("A4b. executors[0]がNewsAgent", isinstance(manager_a4._executors[0]._agent, NewsAgent))
check_true("A4c. executors[1]がWorkflowTriggerAgent", isinstance(manager_a4._executors[1]._agent, WorkflowTriggerAgent))
check_true("A4d. executors[2]がReviewTriggerAgent", isinstance(manager_a4._executors[2]._agent, ReviewTriggerAgent))

captured_a4 = _spy_manager(manager_a4)
legacy_provenance_a4 = build_legacy_direct_provenance(LegacyEntrypoint.RUN_REVIEW_TRIGGER_AGENT)
results_a4 = manager_a4.run(AgentTask(task_id="t", params={}), dry_run=True, legacy_provenance=legacy_provenance_a4)

check("A4e. 3executorすべてが実際にrun()内でfan-out実行される（launcher名からの到達可能性推測=誤り、実際にはA・B・Cすべてに到達しうる構成）", len(results_a4), 3)
check(
    "A4f. NewsAgent（呼び出し箇所A・B到達）はNEWS_AGENT origin",
    captured_a4[0].side_effect_execution_context.legacy_execution_origin, LegacyExecutionOrigin.NEWS_AGENT,
)
check(
    "A4g. WorkflowTriggerAgent（呼び出し箇所C到達）はWORKFLOW_TRIGGER_AGENT origin",
    captured_a4[1].side_effect_execution_context.legacy_execution_origin, LegacyExecutionOrigin.WORKFLOW_TRIGGER_AGENT,
)
check(
    "A4h. ReviewTriggerAgentはREVIEW_TRIGGER_AGENT origin",
    captured_a4[2].side_effect_execution_context.legacy_execution_origin, LegacyExecutionOrigin.REVIEW_TRIGGER_AGENT,
)
_clear_gate_env()
print()


# =====================================================================
# Part B: run_ai_workflow.py legacy composition 実propagation（§28.-20）
# =====================================================================

# ─── [B1] AI_WORKFLOW_DIRECT contextがAiPublishService.run()まで実際に伝播する ───

print("[B1] run_ai_workflow.py相当の構成（AI_WORKFLOW_DIRECT）がAiPublishService.run()まで実伝播する")

_AI_WORKFLOW_DIRECT_CONTEXT = complete_legacy_execution_context(
    build_legacy_direct_provenance(LegacyEntrypoint.RUN_AI_WORKFLOW),
    LegacyExecutionOrigin.AI_WORKFLOW_DIRECT,
)


def _run_publish_only_workflow(tmp_path: Path, side_effect_execution_context, fake_service=None):
    """run_ai_workflow.py本体と同一の構成（WorkflowRunner(config, executors=[...])
    + runner.run(article_id=..., dry_run=..., side_effect_execution_context=...)）を、
    PublishStepExecutorのみをAiPublishServiceのspyで直接exerciseする。"""
    if fake_service is None:
        fake_service = MagicMock()
        fake_service.run.return_value = None
        fake_service.get_results.return_value = []

    publish_executor = PublishStepExecutor(service=fake_service)
    runner = WorkflowRunner(
        config=WorkflowConfig(enabled=True, steps=[WorkflowStep.PUBLISH], base_dir=tmp_path),
        executors=[publish_executor],
    )
    result = runner.run(
        article_id=None, dry_run=False, side_effect_execution_context=side_effect_execution_context,
    )
    return result, fake_service


tmp_b1 = Path(tempfile.mkdtemp(prefix="v6_32_20_b1_"))
result_b1, fake_service_b1 = _run_publish_only_workflow(tmp_b1, _AI_WORKFLOW_DIRECT_CONTEXT)

check_true("B1a. WorkflowResult.overall_success=True", result_b1.overall_success)
check("B1b. AiPublishService.run()が1回呼ばれる（PublishStepExecutorのvalidation boundaryを実際に通過）", fake_service_b1.run.call_count, 1)
_received_ctx_b1 = fake_service_b1.run.call_args.kwargs.get("side_effect_execution_context")
check_true("B1c. 受け取るcontextはLegacyDirectExecutionContext", isinstance(_received_ctx_b1, LegacyDirectExecutionContext))
check("B1d. legacy_entrypointはRUN_AI_WORKFLOW", _received_ctx_b1.legacy_entrypoint if _received_ctx_b1 else None, LegacyEntrypoint.RUN_AI_WORKFLOW)
check("B1e. legacy_execution_originはAI_WORKFLOW_DIRECT", _received_ctx_b1.legacy_execution_origin if _received_ctx_b1 else None, LegacyExecutionOrigin.AI_WORKFLOW_DIRECT)
print()


# ─── [B2] AI_WORKFLOW_DIRECTとWORKFLOW_TRIGGER_AGENTは値レベルで混同されない ───

print("[B2] AI_WORKFLOW_DIRECT originはWORKFLOW_TRIGGER_AGENT originと値レベルで混同されない")

_WORKFLOW_TRIGGER_AGENT_CONTEXT = complete_legacy_execution_context(
    build_legacy_direct_provenance(LegacyEntrypoint.RUN_WORKFLOW_TRIGGER_AGENT),
    LegacyExecutionOrigin.WORKFLOW_TRIGGER_AGENT,
)
tmp_b2 = Path(tempfile.mkdtemp(prefix="v6_32_20_b2_"))
result_b2, fake_service_b2 = _run_publish_only_workflow(tmp_b2, _WORKFLOW_TRIGGER_AGENT_CONTEXT)
_received_ctx_b2 = fake_service_b2.run.call_args.kwargs.get("side_effect_execution_context")

check_false(
    "B2a. AI_WORKFLOW_DIRECT経路とWORKFLOW_TRIGGER_AGENT経路のoriginは異なる値として区別される",
    _received_ctx_b1.legacy_execution_origin == _received_ctx_b2.legacy_execution_origin,
)
check("B2b. WORKFLOW_TRIGGER_AGENT経路自身のoriginは正しくWORKFLOW_TRIGGER_AGENT", _received_ctx_b2.legacy_execution_origin, LegacyExecutionOrigin.WORKFLOW_TRIGGER_AGENT)
print()


# ─── [B3] context欠落（None）はMISSING_EXECUTION_MODEでfail-closed、external I/O=0 ───

print("[B3] side_effect_execution_context=None → MISSING_EXECUTION_MODEでfail-closed、external I/O=0")

tmp_b3 = Path(tempfile.mkdtemp(prefix="v6_32_20_b3_"))
fake_service_b3 = MagicMock()
fake_service_b3.run.return_value = None
fake_service_b3.get_results.return_value = []

raised_b3 = None
try:
    _run_publish_only_workflow(tmp_b3, None, fake_service=fake_service_b3)
except SideEffectExecutionModeContractError as e:
    raised_b3 = e

check_true("B3a. SideEffectExecutionModeContractErrorが送出される（WorkflowRunner.run()から素通し）", raised_b3 is not None)
check("B3b. reason_codeはMISSING_EXECUTION_MODE", raised_b3.reason_code if raised_b3 else None, ExecutionModeFailureReasonCode.MISSING_EXECUTION_MODE)
check("B3c. AiPublishService.run()は一切呼ばれない（external I/O=0）", fake_service_b3.run.call_count, 0)
print()


# =====================================================================
# 結果サマリ
# =====================================================================

print("=" * 60)
passed = sum(1 for s, _ in results_log if s == "PASS")
failed = sum(1 for s, _ in results_log if s == "FAIL")
print(f"結果: {passed} PASS / {failed} FAIL / 合計 {len(results_log)}")
if failed:
    print("失敗したテスト:")
    for s, label in results_log:
        if s == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
print("全テストPASS")
