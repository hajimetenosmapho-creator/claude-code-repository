"""
WordPress Media Upload Foundation.

Consumer-less Foundation: WordPress Media Library への画像アップロード（media_id取得）
のみを責務とする独立package。既存の記事投稿・アイキャッチ関連・Workflow・Scheduler・
Retry Runtime関連の既存コードのいずれへも依存しない。
"""
from .media_upload_result import MediaUploadResult
from .wordpress_media_uploader import (
    WordPressMediaUploadError,
    WordPressMediaUploader,
)

__all__ = [
    "MediaUploadResult",
    "WordPressMediaUploadError",
    "WordPressMediaUploader",
]
