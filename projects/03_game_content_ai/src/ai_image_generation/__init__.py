"""
AI Image Generation Contract Foundation.

Consumer-less Foundation: 外部API・外部I/Oを一切持たない、Provider非依存の
画像生成Contract（要求・結果）のみを責務とする独立package。既存のWordPress
連携・記事生成Pipeline・Workflow・Scheduler・Retry Runtime関連の既存コード
のいずれへも依存しない。
"""
from .ai_image_generator import AIImageGenerator
from .generated_image import GeneratedImage

__all__ = [
    "GeneratedImage",
    "AIImageGenerator",
]
