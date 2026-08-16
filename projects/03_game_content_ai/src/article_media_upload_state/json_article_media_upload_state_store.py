"""
JSON Article Media Upload State Store（v6.28.0）

Source of Truth: docs/design/article_media_upload_state_foundation.md 8章・9章・11章

設計方針:
    - {base_dir}/{sha256(article_identity)}.json へ1 identity = 1 JSONファイルとして保存する。
    - 書き込みは same-directory unique temp -> write -> flush -> fsync(file) -> close ->
      os.replace() によるatomic置換で行う。filesystem writeの全段階（directory作成・
      mkstemp・fdopen・write/flush/fsync/close・replace）で発生するOSErrorは
      ArticleMediaUploadStateIOError へ統一変換し、raw OSErrorをPublic APIから漏らさない。
    - 読み取りは closed schema検証（型・key集合・schema_version・Enum値）を行った上で
      ArticleMediaUploadRecord(...) を構築し、__post_init__ の Invariant検証と一元化する
      （schema検証とRecord invariantの二重実装を避ける）。検証に失敗した場合は
      Noneへfail-openせず ArticleMediaUploadStateCorruptedError を送出する。
    - requested article_identityとpersisted article_identityの不一致も破損として扱う
      （SHA-256ファイル名一致だけをauthorityにしない）。
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from pathlib import Path

from .article_media_upload_record import ArticleMediaUploadRecord
from .article_media_upload_state import ArticleMediaUploadState
from .article_media_upload_state_store import ArticleMediaUploadStateStore
from .errors import ArticleMediaUploadStateCorruptedError, ArticleMediaUploadStateIOError

_SCHEMA_VERSION = 1
_EXPECTED_KEYS = frozenset(
    {"schema_version", "article_identity", "state", "media_id", "updated_at"}
)


def _identity_hash(article_identity: str) -> str:
    return hashlib.sha256(article_identity.encode("utf-8")).hexdigest()


def _to_schema_dict(record: ArticleMediaUploadRecord) -> dict:
    return {
        "schema_version": _SCHEMA_VERSION,
        "article_identity": record.article_identity,
        "state": record.state.value,
        "media_id": record.media_id,
        "updated_at": record.updated_at,
    }


def _record_from_schema_dict(document: object, requested_identity: str) -> ArticleMediaUploadRecord:
    """closed schema検証を行い、requested_identityとの一致まで確認した上でRecordを返す。

    dict型・key集合・schema_version・state文字列のEnum変換はRecord構築前に必要な
    ため個別に検証する。article_identity・media_id・updated_atはArticleMediaUploadRecord
    の __post_init__ に検証を一元化する（二重実装を避ける）。いずれかの検証に失敗した
    場合はArticleMediaUploadStateCorruptedErrorを送出する（raw persisted contentは
    例外メッセージへ含めない）。
    """
    if type(document) is not dict:
        raise ArticleMediaUploadStateCorruptedError("persisted state is not a JSON object")

    if set(document.keys()) != _EXPECTED_KEYS:
        raise ArticleMediaUploadStateCorruptedError("persisted state has unexpected/missing keys")

    schema_version = document["schema_version"]
    if type(schema_version) is not int or schema_version != _SCHEMA_VERSION:
        raise ArticleMediaUploadStateCorruptedError("persisted state has an unknown schema_version")

    state_value = document["state"]
    if type(state_value) is not str:
        raise ArticleMediaUploadStateCorruptedError("persisted state has a non-str state")
    try:
        state = ArticleMediaUploadState(state_value)
    except ValueError as exc:
        raise ArticleMediaUploadStateCorruptedError(
            "persisted state has an unknown state value"
        ) from exc

    try:
        record = ArticleMediaUploadRecord(
            article_identity=document["article_identity"],
            state=state,
            media_id=document["media_id"],
            updated_at=document["updated_at"],
        )
    except ValueError as exc:
        raise ArticleMediaUploadStateCorruptedError(
            "persisted state violates ArticleMediaUploadRecord invariants"
        ) from exc

    if record.article_identity != requested_identity:
        raise ArticleMediaUploadStateCorruptedError(
            "persisted article_identity does not match the requested identity"
        )

    return record


class JsonArticleMediaUploadStateStore(ArticleMediaUploadStateStore):
    """{base_dir}/{sha256(article_identity)}.json へJSON形式で保存する実装。"""

    def __init__(self, base_dir: Path):
        self._base_dir = base_dir

    def _path_for(self, article_identity: str) -> Path:
        return self._base_dir / f"{_identity_hash(article_identity)}.json"

    def save(self, record: ArticleMediaUploadRecord) -> None:
        path = self._path_for(record.article_identity)

        try:
            self._base_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ArticleMediaUploadStateIOError(
                "failed to create parent directory for state file"
            ) from exc

        payload = json.dumps(_to_schema_dict(record))

        try:
            fd, tmp_path_str = tempfile.mkstemp(
                dir=str(self._base_dir), prefix=f"{path.name}.", suffix=".tmp"
            )
        except OSError as exc:
            raise ArticleMediaUploadStateIOError(
                "failed to create temporary state file"
            ) from exc

        tmp_path = Path(tmp_path_str)
        try:
            try:
                f = os.fdopen(fd, "w", encoding="utf-8")
            except OSError as exc:
                # fdopen失敗時、raw fdの所有権はfile objectへ移っていないため明示close
                with contextlib.suppress(OSError):
                    os.close(fd)
                raise ArticleMediaUploadStateIOError(
                    "failed to open temporary state file"
                ) from exc

            try:
                # withブロック終了時のclose()失敗も、write/flush/fsync失敗と同じ
                # except OSErrorで捕捉され、同一のIOError Contractへ変換される
                with f:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as exc:
                raise ArticleMediaUploadStateIOError(
                    "failed to write temporary state file"
                ) from exc

            try:
                os.replace(tmp_path, path)
            except OSError as exc:
                raise ArticleMediaUploadStateIOError(
                    "failed to replace state file"
                ) from exc
        except BaseException:
            # cleanupはbest-effort。cleanup失敗はprimary failureを上書きしない
            with contextlib.suppress(OSError):
                tmp_path.unlink(missing_ok=True)
            raise

    def get(self, article_identity: str) -> ArticleMediaUploadRecord | None:
        path = self._path_for(article_identity)
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ArticleMediaUploadStateIOError("failed to read state file") from exc
        try:
            document = json.loads(raw)
        except ValueError as exc:
            raise ArticleMediaUploadStateCorruptedError("persisted state is not valid JSON") from exc
        return _record_from_schema_dict(document, article_identity)
