"""
AI 改善提案パッケージ（v1.14.0 / v1.15.0）

処理フロー（v1.14.0）:
    AiInputRecord → PromptBuilder → ClaudeClient → ImprovementSuggestionParser → ImprovementSuggestion

レビューフロー（v1.15.0）:
    ImprovementRepository → ImprovementReportBuilder → ImprovementReviewService → Markdown レポート

Configuration First:
    AI_IMPROVEMENT_ENABLED=false → AiImprovementService.from_env() が NullAiImprovementService を返す
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
]
