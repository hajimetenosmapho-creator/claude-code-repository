"""
Agent管理（v2.0.0 / v2.2.0 / v2.3.0 / v2.4.0 / v2.5.0）

AgentManager:     登録された AgentExecutor にタスクを実行させるマネージャ
NullAgentManager: AI_AGENT_ENABLED=false 時のダミー実装

設計方針:
    - Configuration First: AgentConfig.is_ready() が False の場合、
      from_config() が NullAgentManager を返す（呼び出し側は分岐不要）
    - v2.2.0で NewsAgent（+ NewsPipelineRunner）を初めて executors にDIする。
      is_ready()=True の場合のみ NewsAgentConfig / NewsPipelineRunner / NewsAgent を
      生成する（AI_AGENT_ENABLED=false のときはこれらのオブジェクトすら生成しない）
    - v2.3.0で WorkflowTriggerAgent（+ WorkflowPipelineRunner）を三重ゲート方式でDIする。
      AI_AGENT_ENABLED（AgentConfig.is_ready()）に加えて、
      WorkflowTriggerAgentConfig.is_ready()（WORKFLOW_TRIGGER_AGENT_ENABLED かつ
      AI_WORKFLOW_ENABLED）の両方が True の場合のみ executors に追加する。
      Publishを含むWorkflowが AI_AGENT_ENABLED=true だけで自動実行されないようにするための
      安全策（Project Charter・設計書で合意済み）。
    - v2.4.0で PublishTriggerAgent（+ PublishPipelineRunner）を同様の三重ゲート方式でDIする。
      AI_AGENT_ENABLED（AgentConfig.is_ready()）に加えて、
      PublishTriggerAgentConfig.is_ready()（PUBLISH_TRIGGER_AGENT_ENABLED かつ
      AI_PUBLISH_ENABLED等のAiPublishConfig.is_ready()）の両方が True の場合のみ
      executors に追加する。WordPressへの下書き投稿が AI_AGENT_ENABLED=true だけで
      自動実行されないようにするための安全策（WorkflowTriggerAgentと同じ考え方）。
    - v2.5.0で ReviewTriggerAgent（+ ReviewPipelineRunner）を二重ゲート方式でDIする。
      AI_AGENT_ENABLED（AgentConfig.is_ready()）に加えて、
      ReviewTriggerAgentConfig.is_ready()（REVIEW_TRIGGER_AGENT_ENABLED）が
      True の場合のみ executors に追加する。AiPublishReviewService には
      Config/is_ready()が存在しないため、WorkflowTriggerAgent / PublishTriggerAgent
      のような三重ゲートへは寄せず、二重ゲートのまま確定している
      （Project Charter・Architecture Designで合意済み）。
    - run_id はタスク実行のたびに AgentManager が生成する
      （AgentContext の構築は AgentManager の責務）
"""
from __future__ import annotations

import uuid

from .agent_config import AgentConfig
from .agent_context import AgentContext
from .agent_executor import AgentExecutor
from .agent_result import AgentResult
from .agent_task import AgentTask
from .news_agent import NewsAgent
from .news_agent_config import NewsAgentConfig
from .publish_trigger_agent import PublishTriggerAgent
from .publish_trigger_agent_config import PublishTriggerAgentConfig
from .review_trigger_agent import ReviewTriggerAgent
from .review_trigger_agent_config import ReviewTriggerAgentConfig
from .workflow_trigger_agent import WorkflowTriggerAgent
from .workflow_trigger_agent_config import WorkflowTriggerAgentConfig

from pipeline import (
    NewsPipelineRunner,
    PublishPipelineRunner,
    ReviewPipelineRunner,
    WorkflowPipelineRunner,
)


class AgentManager:
    """
    登録された AgentExecutor にタスクを実行させるマネージャ。

    処理フロー:
        run(task, dry_run) が呼ばれるたびに、
            各 AgentExecutor ごとに新しい run_id を発行して AgentContext を生成
            → executor.execute(context) を呼び出す
            → AgentResult をリストにまとめて返す
    """

    def __init__(self, config: AgentConfig, executors: list[AgentExecutor]):
        self._config    = config
        self._executors = executors

    @classmethod
    def from_config(cls, config: AgentConfig) -> "AgentManager | NullAgentManager":
        """
        AgentConfig から AgentManager を構築する。

        is_ready() が False の場合は NullAgentManager を返す。
        is_ready()=True の場合、NewsAgentConfig / NewsPipelineRunner / NewsAgent を
        生成し、AgentExecutor(NewsAgent(...)) を executors に登録する（v2.2.0）。

        さらに WorkflowTriggerAgentConfig.is_ready()（三重ゲートの2・3段目
        WORKFLOW_TRIGGER_AGENT_ENABLED、および AI_WORKFLOW_ENABLED）が True の場合のみ、
        WorkflowTriggerAgent（+ WorkflowPipelineRunner）も executors に追加する（v2.3.0）。

        同様に PublishTriggerAgentConfig.is_ready()（三重ゲートの2・3段目
        PUBLISH_TRIGGER_AGENT_ENABLED、および AiPublishConfig.is_ready() 相当の
        AI_PUBLISH_ENABLED等）が True の場合のみ、
        PublishTriggerAgent（+ PublishPipelineRunner）も executors に追加する（v2.4.0）。

        同様に ReviewTriggerAgentConfig.is_ready()（二重ゲートの2段目
        REVIEW_TRIGGER_AGENT_ENABLED のみ）が True の場合のみ、
        ReviewTriggerAgent（+ ReviewPipelineRunner）も executors に追加する（v2.5.0）。

        いずれも False の場合（デフォルト）は NewsAgent のみが登録される。
        """
        if not config.is_ready():
            return NullAgentManager()

        news_agent_config = NewsAgentConfig.from_env(project_root=config.base_dir)
        news_pipeline_runner = NewsPipelineRunner(news_agent_config)
        news_agent = NewsAgent(config=news_agent_config, runner=news_pipeline_runner)

        executors: list[AgentExecutor] = [
            AgentExecutor(news_agent),
        ]

        workflow_trigger_agent_config = WorkflowTriggerAgentConfig.from_env(
            project_root=config.base_dir
        )
        if workflow_trigger_agent_config.is_ready():
            workflow_pipeline_runner = WorkflowPipelineRunner(workflow_trigger_agent_config)
            workflow_trigger_agent = WorkflowTriggerAgent(
                config=workflow_trigger_agent_config,
                runner=workflow_pipeline_runner,
            )
            executors.append(AgentExecutor(workflow_trigger_agent))

        publish_trigger_agent_config = PublishTriggerAgentConfig.from_env(
            project_root=config.base_dir
        )
        if publish_trigger_agent_config.is_ready():
            publish_pipeline_runner = PublishPipelineRunner(publish_trigger_agent_config)
            publish_trigger_agent = PublishTriggerAgent(
                config=publish_trigger_agent_config,
                runner=publish_pipeline_runner,
            )
            executors.append(AgentExecutor(publish_trigger_agent))

        review_trigger_agent_config = ReviewTriggerAgentConfig.from_env(
            project_root=config.base_dir
        )
        if review_trigger_agent_config.is_ready():
            review_pipeline_runner = ReviewPipelineRunner(review_trigger_agent_config)
            review_trigger_agent = ReviewTriggerAgent(
                config=review_trigger_agent_config,
                runner=review_pipeline_runner,
            )
            executors.append(AgentExecutor(review_trigger_agent))

        return cls(config=config, executors=executors)

    def is_available(self) -> bool:
        """AgentManagerが実行可能な状態か返す。"""
        return self._config.is_ready()

    def run(self, task: AgentTask, dry_run: bool = False) -> list[AgentResult]:
        """登録されている各 AgentExecutor にタスクを実行させ、結果をまとめて返す。"""
        results: list[AgentResult] = []
        for executor in self._executors:
            context = AgentContext(
                task=task,
                dry_run=dry_run,
                run_id=self._generate_run_id(),
                agent_name="",
            )
            results.append(executor.execute(context))
        return results

    @staticmethod
    def _generate_run_id() -> str:
        return uuid.uuid4().hex


class NullAgentManager:
    """
    AI_AGENT_ENABLED=false 時のダミー実装。
    すべてのメソッドが no-op で動作する。
    """

    def is_available(self) -> bool:
        return False

    def run(self, task: AgentTask, dry_run: bool = False) -> list[AgentResult]:
        print("  [AGENT] AI Agent基盤が無効です（AI_AGENT_ENABLED=false）。")
        return []
