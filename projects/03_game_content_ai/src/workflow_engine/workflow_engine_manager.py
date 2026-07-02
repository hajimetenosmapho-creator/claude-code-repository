"""
Workflow Engine Manager（v2.7.0）

WorkflowEngineManager:     Workflow Engine全体の起動口。既存の NewsAgent / ReviewTriggerAgent /
                            PublishTriggerAgent を無改修のまま独自に構築し、WorkflowEngineExecutorへ委譲する
NullWorkflowEngineManager: 二重ゲートが閉じている場合（デフォルト）のダミー実装

設計方針:
    - AgentManager（v2.0.0）を経由せず、各Trigger Agentの既存 Config.from_env() /
      PipelineRunner / Agent クラスをそのままimportして自前で構築する（「案B」採用）。
      AgentManager / AgentExecutor（v2.0.0 Agent Foundation）・NewsAgent /
      ReviewTriggerAgent / PublishTriggerAgent（いずれも既存）は無改修のまま呼び出すのみ
      （docs/design/workflow_engine_foundation.md 8.2節）。
    - Gate二層構造（同設計書7章）：
        Workflow Engine全体（1・2段目）：AI_AGENT_ENABLED × WORKFLOW_ENGINE_ENABLED
        ステップ別ゲート：
            NEWS    は常に有効（NewsAgentConfigにゲートが存在しないため）
            REVIEW  は ReviewTriggerAgentConfig.is_ready() をそのまま再利用
            PUBLISH は PublishTriggerAgentConfig.is_ready() をそのまま再利用
      ゲートが閉じているステップは AgentExecutor を構築せず、
      WorkflowEngineExecutor 側で「スキップ」として扱われる。
    - 複数実行主体（AgentManager経由の既存scriptとWorkflowEngineManager経由のscript）が
      同時実行された場合の重複実行はロックせず、運用制約として明記するのみとする
      （同設計書13.1節、修正必須事項#3）。ロック実装はRelease 2.7の対象外。
"""
from __future__ import annotations

import uuid

from ai import (
    AgentConfig,
    AgentExecutor,
    NewsAgent,
    NewsAgentConfig,
    PublishTriggerAgent,
    PublishTriggerAgentConfig,
    ReviewTriggerAgent,
    ReviewTriggerAgentConfig,
)
from pipeline import NewsPipelineRunner, PublishPipelineRunner, ReviewPipelineRunner

from .workflow_engine_config import WorkflowEngineConfig
from .workflow_engine_context import WorkflowEngineContext
from .workflow_engine_definition import WorkflowEngineDefinition
from .workflow_engine_event import WorkflowEngineEvent
from .workflow_engine_executor import WorkflowEngineExecutor
from .workflow_engine_result import WorkflowEngineResult
from .workflow_engine_step import WorkflowEngineStep

REASON_REVIEW_GATE_CLOSED = (
    "review step skipped: REVIEW_TRIGGER_AGENT_ENABLED is not set."
)
REASON_PUBLISH_GATE_CLOSED = (
    "publish step skipped: PUBLISH_TRIGGER_AGENT_ENABLED (or AiPublishConfig) is not ready."
)


class WorkflowEngineManager:
    """Workflow Engine全体の起動口。"""

    def __init__(self, config: WorkflowEngineConfig, executor: WorkflowEngineExecutor):
        self._config = config
        self._executor = executor

    @classmethod
    def from_config(
        cls,
        agent_config: AgentConfig,
        workflow_engine_config: WorkflowEngineConfig,
    ) -> "WorkflowEngineManager | NullWorkflowEngineManager":
        """
        AgentConfig と WorkflowEngineConfig から WorkflowEngineManager を構築する。

        二重ゲート（AI_AGENT_ENABLED × WORKFLOW_ENGINE_ENABLED）のいずれかが
        False の場合は NullWorkflowEngineManager を返す（Configuration First）。

        二重ゲートが開いている場合、NEWSステップは無条件で構築し、
        REVIEW / PUBLISH ステップは既存Configの is_ready() が True の場合のみ構築する。
        """
        if not agent_config.is_ready() or not workflow_engine_config.is_ready():
            return NullWorkflowEngineManager()

        project_root = agent_config.base_dir

        news_agent_config = NewsAgentConfig.from_env(project_root=project_root)
        news_executor = AgentExecutor(
            NewsAgent(config=news_agent_config, runner=NewsPipelineRunner(news_agent_config))
        )

        step_executors: dict[WorkflowEngineStep, AgentExecutor | None] = {
            WorkflowEngineStep.NEWS: news_executor,
            WorkflowEngineStep.REVIEW: None,
            WorkflowEngineStep.PUBLISH: None,
        }
        step_skip_reasons: dict[WorkflowEngineStep, str] = {}

        review_trigger_agent_config = ReviewTriggerAgentConfig.from_env(
            project_root=project_root
        )
        if review_trigger_agent_config.is_ready():
            step_executors[WorkflowEngineStep.REVIEW] = AgentExecutor(
                ReviewTriggerAgent(
                    config=review_trigger_agent_config,
                    runner=ReviewPipelineRunner(review_trigger_agent_config),
                )
            )
        else:
            step_skip_reasons[WorkflowEngineStep.REVIEW] = REASON_REVIEW_GATE_CLOSED

        publish_trigger_agent_config = PublishTriggerAgentConfig.from_env(
            project_root=project_root
        )
        if publish_trigger_agent_config.is_ready():
            step_executors[WorkflowEngineStep.PUBLISH] = AgentExecutor(
                PublishTriggerAgent(
                    config=publish_trigger_agent_config,
                    runner=PublishPipelineRunner(publish_trigger_agent_config),
                )
            )
        else:
            step_skip_reasons[WorkflowEngineStep.PUBLISH] = REASON_PUBLISH_GATE_CLOSED

        executor = WorkflowEngineExecutor(
            definition=WorkflowEngineDefinition(),
            step_executors=step_executors,
            step_skip_reasons=step_skip_reasons,
        )
        return cls(config=workflow_engine_config, executor=executor)

    def is_available(self) -> bool:
        """Workflow Engineが実行可能な状態か返す。"""
        return self._config.is_ready()

    def run(self, event: WorkflowEngineEvent, dry_run: bool = False) -> WorkflowEngineResult:
        """WorkflowEngineEventを起点にWorkflowEngineContextを組み立て、Executorへ委譲する。"""
        context = WorkflowEngineContext(
            event=event,
            dry_run=dry_run,
            run_id=self._generate_run_id(),
        )
        return self._executor.run(context)

    @staticmethod
    def _generate_run_id() -> str:
        return uuid.uuid4().hex


class NullWorkflowEngineManager:
    """
    二重ゲートが閉じている場合（デフォルト）のダミー実装。
    すべてのメソッドが no-op で動作する。
    """

    def is_available(self) -> bool:
        return False

    def run(self, event: WorkflowEngineEvent, dry_run: bool = False) -> None:
        print(
            "  [WORKFLOW ENGINE] Workflow Engineが無効です"
            "（AI_AGENT_ENABLED かつ WORKFLOW_ENGINE_ENABLED が必要です）。"
        )
        return None
