"""
Article Featured Media Binding Foundation.

Consumer-less Foundation: MediaUploadResult.media_id（wordpress_media）を
ArticleData.featured_media_id（outputs）へ反映する、単一責務のBinding層のみを
責務とする独立package。画像生成・Media Upload実行・WordPress記事投稿・Pipeline・
Composition Root関連の既存コードのいずれへも依存しない。
"""
from .article_featured_media_binder import bind_featured_media

__all__ = [
    "bind_featured_media",
]
