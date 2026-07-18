"""
Generated Image WordPress Media Upload Wiring Foundation.

Consumer-less Foundation: GeneratedImage（ai_image_generation）を
WordPressMediaUploader.upload()（wordpress_media）へ橋渡しする単一責務の
Wiring層のみを責務とする独立package。画像生成・Article／featured_media反映・
CLI／Composition Root・Retry Runtime関連の既存コードのいずれへも依存しない。
"""
from .generated_image_wordpress_media_uploader import (
    GeneratedImageWordPressMediaUploader,
)

__all__ = [
    "GeneratedImageWordPressMediaUploader",
]
