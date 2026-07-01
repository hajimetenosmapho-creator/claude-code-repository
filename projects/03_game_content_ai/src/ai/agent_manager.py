"""
Agent管理（v2.0.0 / v2.2.0）

AgentManager:     登録された AgentExecutor にタスクを実行させるマネージャ
NullAgentManager: AI_AGENT_ENABLED=false 時のダミー実装

設計方針:
    - Configuration First: AgentConfig.is_ready() が False の場合、
      from_config() が NullAgentManager を返す（呼び出し側は分岐不要）
    - v2.2.0で NewsAgent（+ NewsPipelineRunner）を初めて executors にDIする。
      is_ready()=True の場合のみ NewsAgentConfig / NewsPipelineRunner / NewsAgent を
      生成する（AI_AGENT_ENABLED=false のときはこれらのオブジェクトすら生成しない）
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

from pipeline import NewsPipelineRunner


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
        is_ready()=True の場合のみ NewsAgentConfig / NewsPipelineRunner / NewsAgent を
        生成し、AgentExecutor(NewsAgent(...)) を executors に登録する（v2.2.0）。
        """
        if not config.is_ready():
            return NullAgentManager()

        news_agent_config = NewsAgentConfig.from_env(project_root=config.base_dir)
        news_pipeline_runner = NewsPipelineRunner(news_agent_config)
        news_agent = NewsAgent(config=news_agent_config, runner=news_pipeline_runner)

        executors: list[AgentExecutor] = [
            AgentExecutor(news_agent),
        ]
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
