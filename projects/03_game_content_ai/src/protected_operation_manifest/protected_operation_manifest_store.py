"""
Protected Operation Manifest Store（Release 6.32 Architecture Amendment、Round 9設計）

Source of Truth: docs/design/
side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md
2・4・6・8・9章

Store公開APIはcreate専用1操作（`create_for_attempt()`）＋追記1操作（`register()`）＋
`list_for_attempt()`のみ。rebind/overwriteに相当するAPIは一切存在しない
（IMMUTABLE EXECUTION/MEMBER GENERATION、Round 9）。

atomic write契約は`wordpress_draft_state_store.py`のtempfile→fsync→os.replace
パターンをそのまま踏襲する。durable mutationはkey-scopedロック
（`ProtectedOperationManifestStoreLock`）を取得する。`list_for_attempt()`は
lock-free（既存store群のget()と同一posture）。
"""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from side_effect_safety.side_effect_operation_identity import ProtectedSideEffectKind, SideEffectSite

from .errors import (
    ProtectedOperationManifestContractViolationError,
    ProtectedOperationManifestIOError,
    ProtectedOperationManifestNotFoundError,
)
from .protected_operation_manifest_record import ManifestEntry, ProtectedOperationManifestRecord
from .protected_operation_manifest_store_lock import build_protected_operation_manifest_store_lock

_SCHEMA_VERSION = 1


def _now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class RegisterResult:
    acknowledged: bool
    reason: str | None = None


class ProtectedOperationManifestStore(ABC):
    @abstractmethod
    def create_for_attempt(
        self, root_run_id: str, attempt_ordinal: int, member_run_id: str,
    ) -> bool:
        """Step 0・新規作成専用。entries=()の空レコードをdurableに作成する。
        既存レコードが（well-formed・破損問わず）発見された場合は
        ProtectedOperationManifestContractViolationErrorを送出する（fail-closed、
        呼び出し元はcatchしない、rebindは一切試みない——正常経路ではmember_run_id
        が毎回新しいuuid4であるため、この衝突は構造的に発生し得ない）。
        本メソッド自体はauthorityを検証しない（dumb writer）。"""

    @abstractmethod
    def register(
        self, root_run_id: str, attempt_ordinal: int, member_run_id: str, entry: ManifestEntry,
    ) -> RegisterResult:
        """Step 1。既存レコード（Step 0で作成済みのはず）へentryを冪等追記する。"""

    @abstractmethod
    def list_for_attempt(
        self, root_run_id: str, attempt_ordinal: int, expected_member_run_id: str,
    ) -> "tuple[ManifestEntry, ...]":
        """read専用・lock-free。レコード非存在時は
        ProtectedOperationManifestNotFoundErrorを送出する（空tupleを返さない）。
        レコードは存在するがentriesが空の場合のみ、空tupleを正常に返す。"""


def _to_schema_dict(record: ProtectedOperationManifestRecord) -> dict:
    return {
        "schema_version": _SCHEMA_VERSION,
        "root_run_id": record.root_run_id,
        "attempt_ordinal": record.attempt_ordinal,
        "member_run_id": record.member_run_id,
        "entries": [
            {
                "operation_kind": e.operation_kind.value,
                "effect_site": e.effect_site.value,
                "operation_instance_key": e.operation_instance_key,
                "registered_at": e.registered_at,
            }
            for e in record.entries
        ],
        "contract_version": record.contract_version,
    }


def _record_from_schema_dict(document: object) -> ProtectedOperationManifestRecord:
    if type(document) is not dict:
        raise ProtectedOperationManifestContractViolationError("persisted manifest is not a JSON object")

    expected_keys = {
        "schema_version", "root_run_id", "attempt_ordinal", "member_run_id", "entries", "contract_version",
    }
    if set(document.keys()) != expected_keys:
        raise ProtectedOperationManifestContractViolationError(
            "persisted manifest has unexpected/missing keys"
        )
    if document["schema_version"] != _SCHEMA_VERSION:
        raise ProtectedOperationManifestContractViolationError(
            "persisted manifest has an unknown schema_version"
        )

    try:
        entries = tuple(
            ManifestEntry(
                operation_kind=ProtectedSideEffectKind(e["operation_kind"]),
                effect_site=SideEffectSite(e["effect_site"]),
                operation_instance_key=e["operation_instance_key"],
                registered_at=e["registered_at"],
            )
            for e in document["entries"]
        )
        return ProtectedOperationManifestRecord(
            root_run_id=document["root_run_id"],
            attempt_ordinal=document["attempt_ordinal"],
            member_run_id=document["member_run_id"],
            entries=entries,
            contract_version=document["contract_version"],
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise ProtectedOperationManifestContractViolationError(
            "persisted manifest violates ProtectedOperationManifestRecord schema"
        ) from exc


class JsonProtectedOperationManifestStore(ProtectedOperationManifestStore):
    """{base_dir}/{sha256(f"{root_run_id}:{attempt_ordinal}:{member_run_id}")}.json
    へJSON形式でatomicに保存する実装（Round 9、3要素キー）。"""

    def __init__(self, base_dir: Path, locks_dir: Path | None = None):
        self._base_dir = base_dir
        self._locks_dir = locks_dir if locks_dir is not None else base_dir / ".locks"

    def _path_for(self, root_run_id: str, attempt_ordinal: int, member_run_id: str) -> Path:
        key = f"{root_run_id}:{attempt_ordinal}:{member_run_id}"
        digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
        return self._base_dir / f"{digest}.json"

    def _read_raw(
        self, root_run_id: str, attempt_ordinal: int, member_run_id: str,
    ) -> ProtectedOperationManifestRecord | None:
        path = self._path_for(root_run_id, attempt_ordinal, member_run_id)
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise ProtectedOperationManifestIOError("failed to read manifest file") from exc
        try:
            document = json.loads(raw)
        except ValueError as exc:
            raise ProtectedOperationManifestContractViolationError(
                "persisted manifest is not valid JSON"
            ) from exc
        record = _record_from_schema_dict(document)
        if (
            record.root_run_id != root_run_id
            or record.attempt_ordinal != attempt_ordinal
            or record.member_run_id != member_run_id
        ):
            raise ProtectedOperationManifestContractViolationError(
                "persisted manifest identity does not match the requested key"
            )
        return record

    def _write_raw(self, record: ProtectedOperationManifestRecord) -> None:
        path = self._path_for(record.root_run_id, record.attempt_ordinal, record.member_run_id)
        try:
            self._base_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise ProtectedOperationManifestIOError(
                "failed to create parent directory for manifest file"
            ) from exc

        payload = json.dumps(_to_schema_dict(record))

        try:
            fd, tmp_path_str = tempfile.mkstemp(
                dir=str(self._base_dir), prefix=f"{path.name}.", suffix=".tmp"
            )
        except OSError as exc:
            raise ProtectedOperationManifestIOError("failed to create temporary manifest file") from exc

        tmp_path = Path(tmp_path_str)
        try:
            try:
                f = os.fdopen(fd, "w", encoding="utf-8")
            except OSError as exc:
                with contextlib.suppress(OSError):
                    os.close(fd)
                raise ProtectedOperationManifestIOError("failed to open temporary manifest file") from exc

            try:
                with f:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as exc:
                raise ProtectedOperationManifestIOError("failed to write temporary manifest file") from exc

            try:
                os.replace(tmp_path, path)
            except OSError as exc:
                raise ProtectedOperationManifestIOError("failed to replace manifest file") from exc
        except BaseException:
            with contextlib.suppress(OSError):
                tmp_path.unlink(missing_ok=True)
            raise

    def create_for_attempt(
        self, root_run_id: str, attempt_ordinal: int, member_run_id: str,
    ) -> bool:
        lock = build_protected_operation_manifest_store_lock(
            self._locks_dir, root_run_id, attempt_ordinal, member_run_id,
        )
        with lock:
            existing = self._read_raw(root_run_id, attempt_ordinal, member_run_id)
            if existing is not None:
                # 正常経路では構造的に発生し得ない（member_run_idは毎回新しいuuid4）。
                # rebind等は一切試みず、fail-closedに伝播させる（Round 9）。
                raise ProtectedOperationManifestContractViolationError(
                    f"cannot create: key already has a manifest record "
                    f"(root_run_id={root_run_id}, attempt_ordinal={attempt_ordinal}, "
                    f"member_run_id={member_run_id})"
                )
            record = ProtectedOperationManifestRecord(
                root_run_id=root_run_id, attempt_ordinal=attempt_ordinal, member_run_id=member_run_id,
                entries=(), contract_version=_SCHEMA_VERSION,
            )
            self._write_raw(record)
            return True

    def register(
        self, root_run_id: str, attempt_ordinal: int, member_run_id: str, entry: ManifestEntry,
    ) -> RegisterResult:
        lock = build_protected_operation_manifest_store_lock(
            self._locks_dir, root_run_id, attempt_ordinal, member_run_id,
        )
        with lock:
            existing = self._read_raw(root_run_id, attempt_ordinal, member_run_id)
            if existing is None:
                # Step 0が失敗していればadmission自体が失敗しているはずであり、本来
                # 到達しない経路——防御的検証（Amendment §6）。
                return RegisterResult(
                    acknowledged=False,
                    reason=(
                        f"cannot register: no manifest record for "
                        f"(root_run_id={root_run_id}, attempt_ordinal={attempt_ordinal}, "
                        f"member_run_id={member_run_id})"
                    ),
                )
            if existing.member_run_id != member_run_id:
                return RegisterResult(acknowledged=False, reason="member_run_id mismatch")

            for e in existing.entries:
                if (
                    e.operation_kind == entry.operation_kind
                    and e.effect_site == entry.effect_site
                    and e.operation_instance_key == entry.operation_instance_key
                ):
                    return RegisterResult(acknowledged=True, reason=None)  # 冪等no-op

            updated = ProtectedOperationManifestRecord(
                root_run_id=existing.root_run_id, attempt_ordinal=existing.attempt_ordinal,
                member_run_id=existing.member_run_id, entries=existing.entries + (entry,),
                contract_version=existing.contract_version,
            )
            self._write_raw(updated)
            return RegisterResult(acknowledged=True, reason=None)

    def list_for_attempt(
        self, root_run_id: str, attempt_ordinal: int, expected_member_run_id: str,
    ) -> "tuple[ManifestEntry, ...]":
        record = self._read_raw(root_run_id, attempt_ordinal, expected_member_run_id)
        if record is None:
            raise ProtectedOperationManifestNotFoundError(
                f"no manifest record for (root_run_id={root_run_id}, "
                f"attempt_ordinal={attempt_ordinal}, member_run_id={expected_member_run_id})"
            )
        return record.entries


def build_manifest_entry(
    operation_kind: ProtectedSideEffectKind, effect_site: SideEffectSite, operation_instance_key: str,
) -> ManifestEntry:
    """呼び出し箇所A/B/Cが共通で使う、registered_atを現在時刻で埋める便宜関数。"""
    return ManifestEntry(
        operation_kind=operation_kind, effect_site=effect_site,
        operation_instance_key=operation_instance_key, registered_at=_now_utc_iso(),
    )


def raise_if_not_registered(result: RegisterResult) -> None:
    """呼び出し箇所A/B/Cが共通で使う、register()のdurable ACKを必ず確認する
    ヘルパー（Amendment §5：Step 1の失敗はcall site自身の即時失敗とし、外部I/O
    へは一切進まない、fail-closed）。record_attempted()等の既存write-aheadが
    raiseする既存パターンと同型——register()の戻り値をcheckせず読み捨てる
    経路を作らない。"""
    if not result.acknowledged:
        raise ProtectedOperationManifestContractViolationError(
            result.reason or "manifest registration did not acknowledge"
        )
