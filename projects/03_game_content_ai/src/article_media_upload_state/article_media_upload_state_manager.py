"""
Article Media Upload State Manager（v6.28.0）

Source of Truth: docs/design/article_media_upload_state_foundation.md 4章・5章

Public APIは3つのみ（record_upload_started / record_upload_succeeded / get_state）。
FAILED state・reason field・record_upload_uncertain() / record_upload_failed() は
いずれも設計書3.1節の理由により採用しない。

設計方針:
    - 全Public APIは、store access（hash計算・path生成・ファイルI/O）より前に
      article_identityをfail-fast validationする（4.1節）。
    - record_upload_succeeded() は既存recordとのmedia_id比較より前に、渡された
      media_idの型・範囲を検証する。この順序を誤ると、Pythonの `1 == True` により
      bool値がstable replayとして誤受理される経路が生じる（設計書4.1節、
      Codex Round 4 M-1）。
    - 既存 ATTEMPT_STARTED への record_upload_started() はno-opにせず
      ArticleMediaUploadStateTransitionError を送出する（fail-closed。設計書5章）。
      Foundationは「同一attempt内の重複呼び出し」と「retry/restart」を区別できない
      ため、updated_at refresh目的の再startedにも安全上の意味を持たせない。
"""
from __future__ import annotations

from .article_media_upload_record import ArticleMediaUploadRecord, now_utc_iso
from .article_media_upload_state import ArticleMediaUploadState
from .article_media_upload_state_store import ArticleMediaUploadStateStore
from .errors import (
    ArticleMediaUploadStateConflictError,
    ArticleMediaUploadStateTransitionError,
)


def _validate_identity(article_identity: str) -> None:
    if type(article_identity) is not str or not article_identity.strip():
        raise ValueError("article_identity must be a non-empty, non-whitespace str")


class ArticleMediaUploadStateManager:
    """article単位のupload状態を記録・照会するstrict lifecycle API。"""

    def __init__(self, store: ArticleMediaUploadStateStore):
        self._store = store

    def record_upload_started(self, article_identity: str) -> ArticleMediaUploadRecord:
        """新しいupload試行の開始を記録する。

        既存recordがある場合（ATTEMPT_STARTED・UPLOAD_CONFIRMEDいずれも）は
        ArticleMediaUploadStateTransitionError を送出する（fail-closed）。
        """
        _validate_identity(article_identity)
        existing = self._store.get(article_identity)
        if existing is None:
            record = ArticleMediaUploadRecord(
                article_identity=article_identity,
                state=ArticleMediaUploadState.ATTEMPT_STARTED,
                media_id=None,
                updated_at=now_utc_iso(),
            )
            self._store.save(record)
            return record
        raise ArticleMediaUploadStateTransitionError(
            f"cannot start a new attempt: existing state is {existing.state.value}"
        )

    def record_upload_succeeded(
        self, article_identity: str, media_id: int
    ) -> ArticleMediaUploadRecord:
        """upload確定成功を記録する。

        ATTEMPT_STARTED からのみ UPLOAD_CONFIRMED へ遷移できる。既に
        UPLOAD_CONFIRMED（同一media_id）の場合はstable replayとしてno-op、
        異なるmedia_idの場合は ArticleMediaUploadStateConflictError を送出する。
        recordが存在しない場合は ArticleMediaUploadStateTransitionError を送出する
        （direct success禁止）。
        """
        _validate_identity(article_identity)
        if type(media_id) is not int or media_id <= 0:
            raise ValueError("media_id must be a positive int (bool rejected)")

        existing = self._store.get(article_identity)
        if existing is None:
            raise ArticleMediaUploadStateTransitionError("no existing attempt to confirm")

        if existing.state is ArticleMediaUploadState.UPLOAD_CONFIRMED:
            if existing.media_id == media_id:
                return existing
            raise ArticleMediaUploadStateConflictError(
                f"media_id conflict: existing={existing.media_id}, new={media_id}"
            )

        record = ArticleMediaUploadRecord(
            article_identity=article_identity,
            state=ArticleMediaUploadState.UPLOAD_CONFIRMED,
            media_id=media_id,
            updated_at=now_utc_iso(),
        )
        self._store.save(record)
        return record

    def get_state(self, article_identity: str) -> ArticleMediaUploadRecord | None:
        """article_identityに対応するrecordを返す。未記録の場合はNone。"""
        _validate_identity(article_identity)
        return self._store.get(article_identity)
