"""
Article Media Upload State パッケージ（v6.28.0）

Source of Truth: docs/design/article_media_upload_state_foundation.md

article単位でWordPress media uploadの「試行開始」「確定成功」のみを記録・照会する、
Consumer-lessな独立Foundation。main.py・RetryQueueItem・WordPressMediaUploader等の
既存productionコードはいずれも無変更・未参照。

Public APIは3つのみ（ArticleMediaUploadStateManager）:
    record_upload_started(article_identity) -> ArticleMediaUploadRecord
    record_upload_succeeded(article_identity, media_id) -> ArticleMediaUploadRecord
    get_state(article_identity) -> ArticleMediaUploadRecord | None

state:
    ATTEMPT_STARTED   - 試行開始。retry-safeを意味しない
    UPLOAD_CONFIRMED  - 確定成功。protected terminal state

Hard Wiring Prerequisites（設計書13章）:
    本Releaseはruntime wiringを一切行わない。main.py等への実配線は、HWP-1
    （Concurrency）・HWP-2（Identity Lifecycle）・HWP-3（Unresolved ATTEMPT_STARTED
    Handling）のいずれもArchitecture Reviewで承認されるまで禁止する。
"""
from .article_media_upload_record import ArticleMediaUploadRecord
from .article_media_upload_state import ArticleMediaUploadState
from .article_media_upload_state_config import ArticleMediaUploadStateConfig
from .article_media_upload_state_manager import ArticleMediaUploadStateManager
from .article_media_upload_state_store import ArticleMediaUploadStateStore
from .errors import (
    ArticleMediaUploadStateConflictError,
    ArticleMediaUploadStateCorruptedError,
    ArticleMediaUploadStateIOError,
    ArticleMediaUploadStateTransitionError,
)
from .json_article_media_upload_state_store import JsonArticleMediaUploadStateStore

__all__ = [
    "ArticleMediaUploadState",
    "ArticleMediaUploadRecord",
    "ArticleMediaUploadStateStore",
    "JsonArticleMediaUploadStateStore",
    "ArticleMediaUploadStateConfig",
    "ArticleMediaUploadStateManager",
    "ArticleMediaUploadStateCorruptedError",
    "ArticleMediaUploadStateIOError",
    "ArticleMediaUploadStateConflictError",
    "ArticleMediaUploadStateTransitionError",
]
