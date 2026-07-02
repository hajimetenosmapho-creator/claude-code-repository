"""
AI 改善提案パッケージ（v1.14.0 / v1.15.0 / v1.16.0 / v1.17.0 / v1.18.0 / v1.19.0 / v1.20.0）

処理フロー（v1.14.0）:
    AiInputRecord → PromptBuilder → ClaudeClient → ImprovementSuggestionParser → ImprovementSuggestion

レビューフロー（v1.15.0）:
    ImprovementRepository → ImprovementReportBuilder → ImprovementReviewService → Markdown レポート

リライトフロー（v1.16.0）:
    ImprovementSuggestion → ArticleProvider → RewritePromptBuilder → ClaudeClient
        → RewriteParser → RewriteResult → RewriteRepository → Markdown + JSON

リライトレビューフロー（v1.17.0）:
    RewriteResult（JSON）→ RewriteReviewRepository → RewriteReviewService
        → RewriteReviewResult → RewriteReviewReportBuilder → Markdown + JSON

公開フロー（v1.18.0）:
    RewriteReviewResult（adopted）→ AiPublishRepository → AiPublishService
        → WordPressDraftClient → WordPress 下書き → AiPublishResult
        → AiPublishReportBuilder → Markdown + JSON

公開レビューフロー（v1.19.0）:
    AiPublishResult（JSON）→ AiPublishReviewRepository → AiPublishReviewService
        → AiPublishReviewResult（review_status=PENDING）
        → AiPublishReviewReportBuilder → Markdown + JSON

ワークフローフロー（v1.20.0）:
    WorkflowConfig → WorkflowRunner.from_config()
        → [WorkflowStepExecutor × 6] → WorkflowContext
        → WorkflowResult → WorkflowReportBuilder → Markdown

Configuration First:
    AI_IMPROVEMENT_ENABLED=false → AiImprovementService.from_env() が NullAiImprovementService を返す
    AI_REWRITE_ENABLED=false     → RewriteService.from_env() が NullRewriteService を返す
    AI_PUBLISH_ENABLED=false     → AiPublishService.from_env() が NullAiPublishService を返す
"""
from .ai_improvement_config import AiImprovementConfig
from .improvement_suggestion import ImprovementSuggestion
from .improvement_suggestion_parser import ImprovementSuggestionParser
from .prompt_builder import PromptBuilder
from .claude_client import ClaudeClient, NullClaudeClient
from .ai_improvement_service import AiImprovementService, NullAiImprovementService
from .improvement_repository import ImprovementRepository
from .improvement_report_builder import ImprovementReportBuilder
from .improvement_review_service import ImprovementReviewService
from .rewrite_config import RewriteConfig
from .rewrite_result import RewriteResult
from .article_provider import ArticleProvider, WordPressArticleProvider, NullArticleProvider
from .rewrite_prompt_builder import RewritePromptBuilder
from .rewrite_parser import RewriteParser
from .rewrite_repository import RewriteRepository
from .rewrite_service import RewriteService, NullRewriteService
from .rewrite_review_result import ReviewStatus, RewriteReviewResult
from .rewrite_review_repository import RewriteReviewRepository
from .rewrite_review_report_builder import RewriteReviewReportBuilder
from .rewrite_review_service import RewriteReviewService, NullRewriteReviewService
from .ai_publish_config import AiPublishConfig
from .ai_publish_result import AiPublishResult
from .wordpress_draft_client import WordPressDraftClient, NullWordPressDraftClient
from .ai_publish_repository import AiPublishRepository
from .ai_publish_report_builder import AiPublishReportBuilder
from .ai_publish_service import AiPublishService, NullAiPublishService
from .ai_publish_review_result import PublishReviewStatus, AiPublishReviewResult
from .ai_publish_review_repository import AiPublishReviewRepository
from .ai_publish_review_report_builder import AiPublishReviewReportBuilder
from .ai_publish_review_service import AiPublishReviewService, NullAiPublishReviewService
from .workflow_step import WorkflowStep, WorkflowStepResult
from .workflow_context import WorkflowContext
from .workflow_config import WorkflowConfig, ALL_WORKFLOW_STEPS
from .workflow_result import WorkflowResult
from .workflow_step_executor import (
    WorkflowStepExecutor,
    ImprovementStepExecutor,
    ImprovementReviewStepExecutor,
    RewriteStepExecutor,
    RewriteReviewStepExecutor,
    PublishStepExecutor,
    PublishReviewStepExecutor,
)
from .workflow_report_builder import WorkflowReportBuilder
from .workflow_runner import WorkflowRunner, NullWorkflowRunner

# v2.0.0 AI Agent Foundation
from .agent_task import AgentTask
from .agent_decision import AgentDecision
from .agent_context import AgentContext
from .agent_result import AgentResult
from .agent_config import AgentConfig
from .base_agent import BaseAgent
from .agent_executor import AgentExecutor
from .agent_manager import AgentManager, NullAgentManager

# v2.2.0 News Agent Foundation
from .news_agent_config import NewsAgentConfig
from .news_agent import NewsAgent

# v2.3.0 Workflow Trigger Agent Foundation
from .workflow_trigger_agent_config import WorkflowTriggerAgentConfig
from .workflow_trigger_agent import WorkflowTriggerAgent

# v2.4.0 Publish Trigger Agent Foundation
from .publish_trigger_agent_config import PublishTriggerAgentConfig
from .publish_trigger_agent import PublishTriggerAgent

# v2.5.0 Review Trigger Agent Foundation
from .review_trigger_agent_config import ReviewTriggerAgentConfig
from .review_trigger_agent import ReviewTriggerAgent

__all__ = [
    # v1.14.0
    "AiImprovementConfig",
    "ImprovementSuggestion",
    "ImprovementSuggestionParser",
    "PromptBuilder",
    "ClaudeClient",
    "NullClaudeClient",
    "AiImprovementService",
    "NullAiImprovementService",
    # v1.15.0
    "ImprovementRepository",
    "ImprovementReportBuilder",
    "ImprovementReviewService",
    # v1.16.0
    "RewriteConfig",
    "RewriteResult",
    "ArticleProvider",
    "WordPressArticleProvider",
    "NullArticleProvider",
    "RewritePromptBuilder",
    "RewriteParser",
    "RewriteRepository",
    "RewriteService",
    "NullRewriteService",
    # v1.17.0
    "ReviewStatus",
    "RewriteReviewResult",
    "RewriteReviewRepository",
    "RewriteReviewReportBuilder",
    "RewriteReviewService",
    "NullRewriteReviewService",
    # v1.18.0
    "AiPublishConfig",
    "AiPublishResult",
    "WordPressDraftClient",
    "NullWordPressDraftClient",
    "AiPublishRepository",
    "AiPublishReportBuilder",
    "AiPublishService",
    "NullAiPublishService",
    # v1.19.0
    "PublishReviewStatus",
    "AiPublishReviewResult",
    "AiPublishReviewRepository",
    "AiPublishReviewReportBuilder",
    "AiPublishReviewService",
    "NullAiPublishReviewService",
    # v1.20.0
    "WorkflowStep",
    "WorkflowStepResult",
    "WorkflowContext",
    "WorkflowConfig",
    "ALL_WORKFLOW_STEPS",
    "WorkflowResult",
    "WorkflowStepExecutor",
    "ImprovementStepExecutor",
    "ImprovementReviewStepExecutor",
    "RewriteStepExecutor",
    "RewriteReviewStepExecutor",
    "PublishStepExecutor",
    "PublishReviewStepExecutor",
    "WorkflowReportBuilder",
    "WorkflowRunner",
    "NullWorkflowRunner",
    # v2.0.0
    "AgentTask",
    "AgentDecision",
    "AgentContext",
    "AgentResult",
    "AgentConfig",
    "BaseAgent",
    "AgentExecutor",
    "AgentManager",
    "NullAgentManager",
    # v2.2.0
    "NewsAgentConfig",
    "NewsAgent",
    # v2.3.0
    "WorkflowTriggerAgentConfig",
    "WorkflowTriggerAgent",
    # v2.4.0
    "PublishTriggerAgentConfig",
    "PublishTriggerAgent",
    # v2.5.0
    "ReviewTriggerAgentConfig",
    "ReviewTriggerAgent",
]
