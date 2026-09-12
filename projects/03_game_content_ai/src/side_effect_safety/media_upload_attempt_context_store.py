"""
Media Upload Attempt Context Store（Release 6.32、9.9.2・9.9.8節）

`MediaUploadContextPhase`（PREPARED→IO_ARMEDの一方向のみ）のdurable
recordを永続化する。duplicate検出・遷移前提条件の検証はCoordinator
（`_read_all()`・各公開メソッドのbody）が担う——本store自体はCoordinatorの
identity-scoped lock保持区間内からのみ呼ばれる。
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
from .media_upload_context_phase import MediaUploadAttemptContextRecord, MediaUploadContextPhase
from .side_effect_operation_identity import (
    ProtectedSideEffectKind,
    SideEffectOperationIdentity,
    SideEffectSite,
)

_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CreateResult:
    acknowledged: bool
    reason: str | None
    record: MediaUploadAttemptContextRecord | None


@dataclass(frozen=True)
class TransitionResult:
    acknowledged: bool
    reason: str | None
    record: MediaUploadAttemptContextRecord | None


class MediaUploadAttemptContextStore(ABC):
    @abstractmethod
    def create_prepared(
        self, identity: SideEffectOperationIdentity, member_run_id: str, updated_at: str,
    ) -> CreateResult: ...

    @abstractmethod
    def transition_to_io_armed(
        self, identity: SideEffectOperationIdentity, expected_member_run_id: str, updated_at: str,
    ) -> TransitionResult: ...

    @abstractmethod
    def get(
        self, identity: SideEffectOperationIdentity, expected_member_run_id: str,
    ) -> MediaUploadAttemptContextRecord | None: ...


def _to_schema_dict(record: MediaUploadAttemptContextRecord) -> dict:
    return {
        "schema_version": _SCHEMA_VERSION,
        "root_run_id": record.identity.root_run_id,
        "attempt_ordinal": record.identity.attempt_ordinal,
        "operation_kind": record.identity.operation_kind.value,
        "effect_site": record.identity.effect_site.value,
        "operation_instance_key": record.identity.operation_instance_key,
        "member_run_id": record.member_run_id,
        "phase": record.phase.value,
        "updated_at": record.updated_at,
    }


def _record_from_schema_dict(
    document: object, requested_identity: SideEffectOperationIdentity,
) -> MediaUploadAttemptContextRecord:
    # Release 6.32 sub-milestone 6D-6B（28.-1節#11、production fix）：
    # persisted stateのcontract violation（schema不正・identity不一致）は、
    # 真のfilesystem I/O failure（MediaUploadSafetyIOError）とは意味的に
    # 別物であるため、WordPressDraftStateStore側（*CorruptedError）と対称的に
    # MediaUploadSafetyContractViolationErrorを送出する。
    if type(document) is not dict:
        raise MediaUploadSafetyContractViolationError("persisted attempt context is not a JSON object")
    expected_keys = {
        "schema_version", "root_run_id", "attempt_ordinal", "operation_kind", "effect_site",
        "operation_instance_key", "member_run_id", "phase", "updated_at",
    }
    if set(document.keys()) != expected_keys or document.get("schema_version") != _SCHEMA_VERSION:
        raise MediaUploadSafetyContractViolationError("persisted attempt context has unexpected schema")

    persisted_identity = SideEffectOperationIdentity(
        root_run_id=document["root_run_id"],
        attempt_ordinal=document["attempt_ordinal"],
        operation_kind=ProtectedSideEffectKind(document["operation_kind"]),
        effect_site=SideEffectSite(document["effect_site"]),
        operation_instance_key=document["operation_instance_key"],
    )
    if persisted_identity != requested_identity:
        raise MediaUploadSafetyContractViolationError("persisted attempt context identity mismatch")

    return MediaUploadAttemptContextRecord(
        identity=persisted_identity,
        member_run_id=document["member_run_id"],
        phase=MediaUploadContextPhase(document["phase"]),
        updated_at=document["updated_at"],
    )


class JsonMediaUploadAttemptContextStore(MediaUploadAttemptContextStore):
    """{base_dir}/{sha256(identity.as_store_key())}.json へJSON形式でatomicに保存する実装。"""

    def __init__(self, base_dir: Path):
        self._base_dir = base_dir

    def _path_for(self, identity: SideEffectOperationIdentity) -> Path:
        digest = hashlib.sha256(identity.as_store_key().encode("utf-8")).hexdigest()
        return self._base_dir / f"{digest}.json"

    def _read_raw(self, identity: SideEffectOperationIdentity) -> MediaUploadAttemptContextRecord | None:
        path = self._path_for(identity)
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise MediaUploadSafetyIOError("failed to read attempt context file") from exc
        try:
            document = json.loads(raw)
        except ValueError as exc:
            # Release 6.32 sub-milestone 6D-6B（28.-1節#11、production fix）：
            # JSON parse失敗はfilesystem I/O failureではなくcontentのcorruption
            # であるため、WordPressDraftStateStore側と対称的にContractViolation
            # とする（真のfilesystem read failureは上のexceptで区別済み）。
            raise MediaUploadSafetyContractViolationError(
                "persisted attempt context is not valid JSON"
            ) from exc
        return _record_from_schema_dict(document, identity)

    def _write_raw(self, record: MediaUploadAttemptContextRecord) -> None:
        path = self._path_for(record.identity)
        payload = json.dumps(_to_schema_dict(record))
        try:
            self._base_dir.mkdir(parents=True, exist_ok=True)
            fd, tmp_path_str = tempfile.mkstemp(
                dir=str(self._base_dir), prefix=f"{path.name}.", suffix=".tmp"
            )
        except OSError as exc:
            raise MediaUploadSafetyIOError("failed to prepare temporary attempt context file") from exc

        tmp_path = Path(tmp_path_str)
        try:
            try:
                f = os.fdopen(fd, "w", encoding="utf-8")
            except OSError as exc:
                with contextlib.suppress(OSError):
                    os.close(fd)
                raise MediaUploadSafetyIOError("failed to open temporary attempt context file") from exc
            try:
                with f:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as exc:
                raise MediaUploadSafetyIOError("failed to write temporary attempt context file") from exc
            try:
                os.replace(tmp_path, path)
            except OSError as exc:
                raise MediaUploadSafetyIOError("failed to replace attempt context file") from exc
        except BaseException:
            with contextlib.suppress(OSError):
                tmp_path.unlink(missing_ok=True)
            raise

    def create_prepared(
        self, identity: SideEffectOperationIdentity, member_run_id: str, updated_at: str,
    ) -> CreateResult:
        record = MediaUploadAttemptContextRecord(
            identity=identity, member_run_id=member_run_id,
            phase=MediaUploadContextPhase.PREPARED, updated_at=updated_at,
        )
        self._write_raw(record)
        return CreateResult(acknowledged=True, reason=None, record=record)

    def transition_to_io_armed(
        self, identity: SideEffectOperationIdentity, expected_member_run_id: str, updated_at: str,
    ) -> TransitionResult:
        existing = self._read_raw(identity)
        if existing is None or existing.member_run_id != expected_member_run_id:
            return TransitionResult(
                acknowledged=False, reason="no matching PREPARED context to transition", record=None,
            )
        if existing.phase is not MediaUploadContextPhase.PREPARED:
            return TransitionResult(
                acknowledged=False,
                reason=f"cannot transition: current phase is {existing.phase.value}, expected PREPARED",
                record=None,
            )
        record = MediaUploadAttemptContextRecord(
            identity=identity, member_run_id=expected_member_run_id,
            phase=MediaUploadContextPhase.IO_ARMED, updated_at=updated_at,
        )
        self._write_raw(record)
        return TransitionResult(acknowledged=True, reason=None, record=record)

    def get(
        self, identity: SideEffectOperationIdentity, expected_member_run_id: str,
    ) -> MediaUploadAttemptContextRecord | None:
        record = self._read_raw(identity)
        if record is None:
            return None
        if record.member_run_id != expected_member_run_id:
            raise MediaUploadSafetyContractViolationError("persisted attempt context member_run_id mismatch")
        return record
