"""
AI 改善提案パッケージ（v1.14.0）

処理フロー:
    AiInputRecord → PromptBuilder → ClaudeClient → ImprovementSuggestionParser → ImprovementSuggestion

Configuration First:
    AI_IMPROVEMENT_ENABLED=false → AiImprovementService.from_env() が NullAiImprovementService を返す
"""
from .ai_improvement_config import AiImprovementConfig
from .improvement_suggestion import ImprovementSuggestion
from .improvement_suggestion_parser import ImprovementSuggestionParser
from .prompt_builder import PromptBuilder
from .claude_client import ClaudeClient, NullClaudeClient
from .ai_improvement_service import AiImprovementService, NullAiImprovementService

__all__ = [
    "AiImprovementConfig",
    "ImprovementSuggestion",
    "ImprovementSuggestionParser",
    "PromptBuilder",
    "ClaudeClient",
    "NullClaudeClient",
    "AiImprovementService",
    "NullAiImprovementService",
]
