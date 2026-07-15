"""
WordPress Media Upload成功結果を表す値オブジェクト。
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class MediaUploadResult:
    """
    WordPressMediaUploader.upload() の成功時の戻り値。

    成功時のみ生成される（失敗は例外で表現するため success 等は保持しない）。

    Attributes:
        media_id:   WordPress Media Library上のID（1以上）
        source_url: アップロード済み画像のURL（WordPressレスポンスの source_url がnullならNone）
        mime_type:  WordPressが認識したMIME type（同上）
    """
    media_id: int
    source_url: str | None
    mime_type: str | None
