"""
Article Featured Media Orchestration Foundation.

Consumer-less Foundation: 既存4 Foundation（AIImageGenerator Protocol・
GeneratedImage → Media Upload capability・bind_featured_media）を、
generate → upload → bind という固定順序で呼び出すOrchestratorのみを責務とする
独立package。main.py・image_resolver.py・WordPressOutput・OutputManager・
Pipeline・Composition Root・Retry Runtime・scripts関連の既存コードのいずれへも
依存しない。
"""
from .article_featured_media_orchestrator import (
    ArticleFeaturedMediaOrchestrator,
    GeneratedImageUploadCapability,
)

__all__ = [
    "ArticleFeaturedMediaOrchestrator",
    "GeneratedImageUploadCapability",
]
