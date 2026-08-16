"""
Article Media Upload State Store 抽象基底クラス（v6.28.0）

Source of Truth: docs/design/article_media_upload_state_foundation.md 3.3節

ExecutionHistoryStore（v2.8.0）と同型のABC分離パターンを踏襲する。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .article_media_upload_record import ArticleMediaUploadRecord


class ArticleMediaUploadStateStore(ABC):
    """ArticleMediaUploadRecordの永続化・照会を担う抽象基底クラス。"""

    @abstractmethod
    def save(self, record: ArticleMediaUploadRecord) -> None:
        """recordを永続化する。"""
        raise NotImplementedError

    @abstractmethod
    def get(self, article_identity: str) -> ArticleMediaUploadRecord | None:
        """article_identityに対応するrecordを返す。未記録の場合はNone。

        永続化データの破損・schema違反・requested/persisted identity不一致は
        Noneではなく ArticleMediaUploadStateCorruptedError を送出する
        （設計書8章・9章）。
        """
        raise NotImplementedError
