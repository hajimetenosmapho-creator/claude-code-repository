"""
Article Media Upload Record定義（v6.28.0）

Source of Truth: docs/design/article_media_upload_state_foundation.md 6章・7章

設計方針:
    - frozen dataclass + __post_init__ により、Manager経由の構築・Store deserialize時の
      構築・直接構築のいずれの経路でも同一のInvariantが必ず成立する（設計書6章）。
    - updated_atはcanonical UTC ISO8601（+00:00固定・round-trip equality必須）のみを
      許可する。既存Repository precedent（execution_history_manager.pyのnaive
      datetime.now()）からの意図的な安全側逸脱（設計書7章）。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from .article_media_upload_state import ArticleMediaUploadState


def now_utc_iso() -> str:
    """canonical UTC ISO8601文字列を生成する（設計書7章）。"""
    return datetime.now(timezone.utc).isoformat()


def is_canonical_utc_iso8601(value: object) -> bool:
    """valueがcanonical UTC ISO8601文字列（+00:00固定・round-trip equality）か判定する
    （設計書7章）。"""
    if type(value) is not str:
        return False
    if not value.endswith("+00:00"):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return False
    return parsed.isoformat() == value


@dataclass(frozen=True)
class ArticleMediaUploadRecord:
    """article単位のWordPress media upload状態を表す不変Record。

    __post_init__ が全fieldのsemantic invariantを構築境界で強制する
    （設計書6章）。
    """

    article_identity: str
    state: ArticleMediaUploadState
    media_id: int | None
    updated_at: str

    def __post_init__(self) -> None:
        if type(self.article_identity) is not str or not self.article_identity.strip():
            raise ValueError("article_identity must be a non-empty, non-whitespace str")
        if not isinstance(self.state, ArticleMediaUploadState):
            raise ValueError("state must be an ArticleMediaUploadState member")

        if self.state is ArticleMediaUploadState.ATTEMPT_STARTED:
            if self.media_id is not None:
                raise ValueError("ATTEMPT_STARTED requires media_id=None")
        elif self.state is ArticleMediaUploadState.UPLOAD_CONFIRMED:
            if type(self.media_id) is not int or self.media_id <= 0:
                raise ValueError(
                    "UPLOAD_CONFIRMED requires a positive int media_id (bool rejected)"
                )

        if not is_canonical_utc_iso8601(self.updated_at):
            raise ValueError("updated_at must be a canonical UTC ISO8601 str (7章)")
