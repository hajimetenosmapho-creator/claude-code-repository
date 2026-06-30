"""
AI 改善提案パッケージ（v1.14.0 / v1.15.0 / v1.16.0 / v1.17.0）

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

Configuration First:
    AI_IMPROVEMENT_ENABLED=false → AiImprovementService.from_env() が NullAiImprovementService を返す
    AI_REWRITE_ENABLED=false     → RewriteService.from_env() が NullRewriteService を返す
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
]
