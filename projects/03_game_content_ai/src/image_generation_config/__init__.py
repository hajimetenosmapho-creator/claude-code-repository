"""
Image Generation Configuration Gate Foundation.

Consumer-less Foundation: 画像生成機能の有効/無効を制御するConfiguration-First
Gateのみを責務とする独立package。main.py・image_resolver.py・OutputManager・
WordPressOutput・OpenAIImageGenerator・ArticleFeaturedMediaOrchestrator・
GeneratedImageWordPressMediaUploader・WordPressMediaUploader・retry_*・
pipeline・workflow_engine・scheduler・scripts関連の既存コードのいずれへも
依存しない。Python標準ライブラリ（os, dataclasses）のみに依存する。
"""
from .image_generation_config import ImageGenerationConfig

__all__ = [
    "ImageGenerationConfig",
]
