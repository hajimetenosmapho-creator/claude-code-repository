"""
Media Upload Applicability Store（Release 6.32、9.9節）

`MEDIA_UPLOAD`のNOT_APPLICABLE（Gate OFF）durable markerを永続化する。1 identity
につき1回のみcreateされる（duplicate検出はCoordinator側の`_read_all(...,
allow_absent_only=True)`が担い、本store自体はduplicate検出責務を持たない——
Commit-Aware Lock Helper経由でCoordinatorのidentity-scoped lock保持区間内から
のみ呼ばれる、9.9.4.4節）。
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from .errors import MediaUploadSafetyContractViolationError, MediaUploadSafetyIOError
from .side_effect_operation_identity import (
    ProtectedSideEffectKind,
    SideEffectOperationIdentity,
    SideEffectSite,
)

_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class NotApplicableRecord:
    identity: SideEffectOperationIdentity
    member_run_id: str
    updated_at: str


@dataclass(frozen=True)
class CreateResult:
    acknowledged: bool
    reason: str | None
    record: NotApplicableRecord | None


class MediaUploadApplicabilityStore(ABC):
    @abstractmethod
    def create(
        self, identity: SideEffectOperationIdentity, member_run_id: str, updated_at: str,
    ) -> CreateResult:
        """NOT_APPLICABLE durable markerを作成する。"""

    @abstractmethod
    def get(
        self, identity: SideEffectOperationIdentity, expected_member_run_id: str,
    ) -> NotApplicableRecord | None:
        """read専用・lock-free。"""


def _to_schema_dict(record: NotApplicableRecord) -> dict:
    return {
        "schema_version": _SCHEMA_VERSION,
        "root_run_id": record.identity.root_run_id,
        "attempt_ordinal": record.identity.attempt_ordinal,
        "operation_kind": record.identity.operation_kind.value,
        "effect_site": record.identity.effect_site.value,
        "operation_instance_key": record.identity.operation_instance_key,
        "member_run_id": record.member_run_id,
        "updated_at": record.updated_at,
    }


def _record_from_schema_dict(document: object, requested_identity: SideEffectOperationIdentity) -> NotApplicableRecord:
    # Release 6.32 sub-milestone 6D-6B（28.-1節#11、production fix）：
    # persisted stateのcontract violation（schema不正・identity不一致）は、
    # 真のfilesystem I/O failure（MediaUploadSafetyIOError）とは意味的に
    # 別物であるため、WordPressDraftStateStore側（*CorruptedError）と対称的に
    # MediaUploadSafetyContractViolationErrorを送出する。
    if type(document) is not dict:
        raise MediaUploadSafetyContractViolationError("persisted applicability marker is not a JSON object")
    expected_keys = {
        "schema_version", "root_run_id", "attempt_ordinal", "operation_kind", "effect_site",
        "operation_instance_key", "member_run_id", "updated_at",
    }
    if set(document.keys()) != expected_keys or document.get("schema_version") != _SCHEMA_VERSION:
        raise MediaUploadSafetyContractViolationError("persisted applicability marker has unexpected schema")

    persisted_identity = SideEffectOperationIdentity(
        root_run_id=document["root_run_id"],
        attempt_ordinal=document["attempt_ordinal"],
        operation_kind=ProtectedSideEffectKind(document["operation_kind"]),
        effect_site=SideEffectSite(document["effect_site"]),
        operation_instance_key=document["operation_instance_key"],
    )
    if persisted_identity != requested_identity:
        raise MediaUploadSafetyContractViolationError("persisted applicability marker identity mismatch")

    return NotApplicableRecord(
        identity=persisted_identity,
        member_run_id=document["member_run_id"],
        updated_at=document["updated_at"],
    )


class JsonMediaUploadApplicabilityStore(MediaUploadApplicabilityStore):
    """{base_dir}/{sha256(identity.as_store_key())}.json へJSON形式でatomicに保存する実装。"""

    def __init__(self, base_dir: Path):
        self._base_dir = base_dir

    def _path_for(self, identity: SideEffectOperationIdentity) -> Path:
        digest = hashlib.sha256(identity.as_store_key().encode("utf-8")).hexdigest()
        return self._base_dir / f"{digest}.json"

    def create(
        self, identity: SideEffectOperationIdentity, member_run_id: str, updated_at: str,
    ) -> CreateResult:
        path = self._path_for(identity)
        record = NotApplicableRecord(identity=identity, member_run_id=member_run_id, updated_at=updated_at)
        payload = json.dumps(_to_schema_dict(record))

        try:
            self._base_dir.mkdir(parents=True, exist_ok=True)
            fd, tmp_path_str = tempfile.mkstemp(
                dir=str(self._base_dir), prefix=f"{path.name}.", suffix=".tmp"
            )
        except OSError as exc:
            raise MediaUploadSafetyIOError("failed to prepare temporary applicability marker file") from exc

        tmp_path = Path(tmp_path_str)
        try:
            try:
                f = os.fdopen(fd, "w", encoding="utf-8")
            except OSError as exc:
                with contextlib.suppress(OSError):
                    os.close(fd)
                raise MediaUploadSafetyIOError("failed to open temporary applicability marker file") from exc
            try:
                with f:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as exc:
                raise MediaUploadSafetyIOError("failed to write temporary applicability marker file") from exc
            try:
                os.replace(tmp_path, path)
            except OSError as exc:
                raise MediaUploadSafetyIOError("failed to replace applicability marker file") from exc
        except BaseException:
            with contextlib.suppress(OSError):
                tmp_path.unlink(missing_ok=True)
            raise

        return CreateResult(acknowledged=True, reason=None, record=record)

    def get(
        self, identity: SideEffectOperationIdentity, expected_member_run_id: str,
    ) -> NotApplicableRecord | None:
        path = self._path_for(identity)
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise MediaUploadSafetyIOError("failed to read applicability marker file") from exc
        try:
            document = json.loads(raw)
        except ValueError as exc:
            # Release 6.32 sub-milestone 6D-6B（28.-1節#11、production fix）：
            # JSON parse失敗はfilesystem I/O failureではなくpersisted content
            # 自体のcorruptionであるため、WordPressDraftStateStore側
            # （*CorruptedError）と対称的にMediaUploadSafetyContractViolationError
            # とする（真のfilesystem read failureはOSErrorのまま上のexceptで
            # MediaUploadSafetyIOErrorへ区別済み）。
            raise MediaUploadSafetyContractViolationError(
                "persisted applicability marker is not valid JSON"
            ) from exc
        record = _record_from_schema_dict(document, identity)
        if record.member_run_id != expected_member_run_id:
            raise MediaUploadSafetyContractViolationError("persisted applicability marker member_run_id mismatch")
        return record
