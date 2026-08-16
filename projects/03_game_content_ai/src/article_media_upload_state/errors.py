"""
Article Media Upload State エラー定義（v6.28.0）

Source of Truth: docs/design/article_media_upload_state_foundation.md
"""
from __future__ import annotations


class ArticleMediaUploadStateCorruptedError(Exception):
    """永続化されたstateがclosed schema・Record invariantに違反している場合に送出される
    （設計書8章・9章）。読み取り側は破損をNoneへfail-openせず、必ずこの例外を送出する。"""


class ArticleMediaUploadStateIOError(Exception):
    """filesystem write（parent directory作成・一時ファイル作成・open・書き込み・置換）が
    OSErrorで失敗した場合に送出される（設計書11章）。raw OSErrorをPublic APIから
    漏らさないための統一Contract。"""


class ArticleMediaUploadStateConflictError(Exception):
    """UPLOAD_CONFIRMEDへ異なるmedia_idで再確定しようとした場合に送出される
    （設計書4.2節）。"""


class ArticleMediaUploadStateTransitionError(Exception):
    """許可されていないstate遷移が要求された場合に送出される（設計書4.2節・5章）。
    silent no-opでAPI誤用を隠さない。"""
