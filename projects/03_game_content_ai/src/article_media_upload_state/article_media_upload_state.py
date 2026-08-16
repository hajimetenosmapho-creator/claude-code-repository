"""
Article Media Upload State Enum定義（v6.28.0）

Source of Truth: docs/design/article_media_upload_state_foundation.md 3.2節
"""
from __future__ import annotations

from enum import Enum


class ArticleMediaUploadState(Enum):
    """article単位のWordPress media upload状態。

    ATTEMPT_STARTEDが持つ唯一の意味は「試行が開始された」ことであり、
    「安全にretryしてよい」ことではない（crash window B/Cを区別できないため）。
    """

    ATTEMPT_STARTED = "attempt_started"
    UPLOAD_CONFIRMED = "upload_confirmed"
