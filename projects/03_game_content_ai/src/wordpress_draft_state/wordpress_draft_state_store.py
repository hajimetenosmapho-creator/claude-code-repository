"""
WordPress Draft State Store（Release 6.32、9.3〜9.4・9.7・27章）

Source of Truth: docs/design/side_effect_fail_closed_human_review_safety_foundation.md

Store公開APIはcreate系1操作（`create_attempted()`）＋compare-and-transition1操作
（`transition_to_confirmed()`）＋`get()`のみ（9.3節）。`save()`/`delete()`/`reset()`/
`overwrite()`に相当するAPIは一切存在しない。

atomic write契約は`retry_lineage_store.py`のtempfile→fsync→os.replaceパターンを
そのまま踏襲する（27.2節）。durable mutationは`_run_with_commit_aware_lock()`
（side_effect_safety、9.8節）を経由してidentity-scoped lockを取得する。`get()`は
lock-freeであり、複数storeにまたがるcomposite atomicityではなく、単一ファイルの
old-or-new complete snapshotのみを保証する（27.3節、authoritative）。
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

from side_effect_safety.commit_aware_lock import _run_with_commit_aware_lock, now_utc_iso
from side_effect_safety.side_effect_operation_identity import (
    ProtectedSideEffectKind,
    SideEffectOperationIdentity,
    SideEffectOperationState,
    SideEffectSite,
)

from .errors import (
    WordPressDraftStateCorruptedError,
    WordPressDraftStateIOError,
    WordPressDraftStateTransitionError,
)
from .wordpress_draft_record import WordPressDraftRecord
from .wordpress_draft_state_store_lock import build_wordpress_draft_state_store_lock

_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class CreateResult:
    acknowledged: bool
    reason: str | None
    record: WordPressDraftRecord | None


@dataclass(frozen=True)
class TransitionResult:
    acknowledged: bool
    reason: str | None
    record: WordPressDraftRecord | None


class WordPressDraftStateStore(ABC):
    @abstractmethod
    def create_attempted(
        self, identity: SideEffectOperationIdentity, member_run_id: str, updated_at: str,
    ) -> CreateResult:
        """新規identityにATTEMPTED状態のrecordをdurableに作成する（write-ahead）。"""

    @abstractmethod
    def transition_to_confirmed(
        self,
        identity: SideEffectOperationIdentity,
        expected_member_run_id: str,
        wp_post_id: int,
        updated_at: str,
    ) -> TransitionResult:
        """既存recordが (a) identityに一致し、(b) member_run_idが一致し、
        (c) state==ATTEMPTEDである場合のみCONFIRMED_SUCCESSへcompare-and-transitionする。"""

    @abstractmethod
    def get(
        self, identity: SideEffectOperationIdentity, expected_member_run_id: str,
    ) -> WordPressDraftRecord | None:
        """read-only・lock-free（27.3節、authoritative）。レコード非存在はNone。
        schema違反・identity不一致・expected_member_run_id不一致は
        WordPressDraftStateCorruptedErrorを送出する。"""


def _to_schema_dict(record: WordPressDraftRecord) -> dict:
    return {
        "schema_version": _SCHEMA_VERSION,
        "root_run_id": record.identity.root_run_id,
        "attempt_ordinal": record.identity.attempt_ordinal,
        "operation_kind": record.identity.operation_kind.value,
        "effect_site": record.identity.effect_site.value,
        "operation_instance_key": record.identity.operation_instance_key,
        "member_run_id": record.member_run_id,
        "state": record.state.value,
        "wp_post_id": record.wp_post_id,
        "updated_at": record.updated_at,
        "contract_version": record.contract_version,
    }


def _record_from_schema_dict(document: object, requested_identity: SideEffectOperationIdentity) -> WordPressDraftRecord:
    if type(document) is not dict:
        raise WordPressDraftStateCorruptedError("persisted state is not a JSON object")

    expected_keys = {
        "schema_version", "root_run_id", "attempt_ordinal", "operation_kind", "effect_site",
        "operation_instance_key", "member_run_id", "state", "wp_post_id", "updated_at",
        "contract_version",
    }
    if set(document.keys()) != expected_keys:
        raise WordPressDraftStateCorruptedError("persisted state has unexpected/missing keys")

    if document["schema_version"] != _SCHEMA_VERSION:
        raise WordPressDraftStateCorruptedError("persisted state has an unknown schema_version")

    try:
        persisted_identity = SideEffectOperationIdentity(
            root_run_id=document["root_run_id"],
            attempt_ordinal=document["attempt_ordinal"],
            operation_kind=ProtectedSideEffectKind(document["operation_kind"]),
            effect_site=SideEffectSite(document["effect_site"]),
            operation_instance_key=document["operation_instance_key"],
        )
        record = WordPressDraftRecord(
            identity=persisted_identity,
            member_run_id=document["member_run_id"],
            state=SideEffectOperationState(document["state"]),
            wp_post_id=document["wp_post_id"],
            updated_at=document["updated_at"],
            contract_version=document["contract_version"],
        )
    except (ValueError, KeyError) as exc:
        raise WordPressDraftStateCorruptedError(
            "persisted state violates WordPressDraftRecord invariants"
        ) from exc

    if persisted_identity != requested_identity:
        raise WordPressDraftStateCorruptedError(
            "persisted identity does not match the requested identity"
        )

    return record


class JsonWordPressDraftStateStore(WordPressDraftStateStore):
    """{base_dir}/{sha256(identity.as_store_key())}.json へJSON形式でatomicに保存する実装。"""

    def __init__(self, base_dir: Path, locks_dir: Path | None = None):
        self._base_dir = base_dir
        self._locks_dir = locks_dir if locks_dir is not None else base_dir / ".locks"

    def _path_for(self, identity: SideEffectOperationIdentity) -> Path:
        digest = hashlib.sha256(identity.as_store_key().encode("utf-8")).hexdigest()
        return self._base_dir / f"{digest}.json"

    def _read_raw(self, identity: SideEffectOperationIdentity) -> WordPressDraftRecord | None:
        path = self._path_for(identity)
        if not path.exists():
            return None
        try:
            raw = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise WordPressDraftStateIOError("failed to read state file") from exc
        try:
            document = json.loads(raw)
        except ValueError as exc:
            raise WordPressDraftStateCorruptedError("persisted state is not valid JSON") from exc
        return _record_from_schema_dict(document, identity)

    def _write_raw(self, record: WordPressDraftRecord) -> None:
        path = self._path_for(record.identity)
        try:
            self._base_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            raise WordPressDraftStateIOError("failed to create parent directory for state file") from exc

        payload = json.dumps(_to_schema_dict(record))

        try:
            fd, tmp_path_str = tempfile.mkstemp(
                dir=str(self._base_dir), prefix=f"{path.name}.", suffix=".tmp"
            )
        except OSError as exc:
            raise WordPressDraftStateIOError("failed to create temporary state file") from exc

        tmp_path = Path(tmp_path_str)
        try:
            try:
                f = os.fdopen(fd, "w", encoding="utf-8")
            except OSError as exc:
                with contextlib.suppress(OSError):
                    os.close(fd)
                raise WordPressDraftStateIOError("failed to open temporary state file") from exc

            try:
                with f:
                    f.write(payload)
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as exc:
                raise WordPressDraftStateIOError("failed to write temporary state file") from exc

            try:
                os.replace(tmp_path, path)
            except OSError as exc:
                raise WordPressDraftStateIOError("failed to replace state file") from exc
        except BaseException:
            with contextlib.suppress(OSError):
                tmp_path.unlink(missing_ok=True)
            raise

    def create_attempted(
        self, identity: SideEffectOperationIdentity, member_run_id: str, updated_at: str,
    ) -> CreateResult:
        def body(commit_state):
            existing = self._read_raw(identity)
            if existing is not None:
                raise WordPressDraftStateTransitionError(
                    f"cannot create: identity already has a record (state={existing.state.value})"
                )
            record = WordPressDraftRecord(
                identity=identity,
                member_run_id=member_run_id,
                state=SideEffectOperationState.ATTEMPTED,
                wp_post_id=None,
                updated_at=updated_at,
                contract_version=_SCHEMA_VERSION,
            )
            self._write_raw(record)  # ATTEMPTED durable ACK
            # durable ACK確認。直ちにcommitted=Trueを設定する。
            commit_state["committed"] = True
            prospective = CreateResult(acknowledged=True, reason=None, record=record)
            commit_state["value"] = prospective
            return prospective

        lock = build_wordpress_draft_state_store_lock(self._locks_dir, identity)
        outcome = _run_with_commit_aware_lock(lock, identity, body)
        if outcome.value is not None and isinstance(outcome.value, CreateResult):
            return outcome.value
        return CreateResult(acknowledged=True, reason=None, record=self._read_raw(identity))

    def transition_to_confirmed(
        self,
        identity: SideEffectOperationIdentity,
        expected_member_run_id: str,
        wp_post_id: int,
        updated_at: str,
    ) -> TransitionResult:
        def _not_acknowledged(commit_state, reason: str) -> TransitionResult:
            # Release 6.32 sub-milestone WordPressDraftStateStore contract fix
            # （Approved Architecture §9.3・§9.5・§28.3#5・#6・#7・#8・#12）：
            # compare-and-transitionが不成立の場合、例外を送出せずacknowledged=False
            # を返す（terminal recordのrecycleなし、duplicate confirmedの成功への
            # 丸め込みなし）。これはStore層の正常な戻り値契約であり、
            # semantic mutationを一切行っていないため、直ちにcommitted=Trueを
            # 設定して良い（保護すべきdurable stateの変化が存在しない）。
            commit_state["committed"] = True
            prospective = TransitionResult(acknowledged=False, reason=reason, record=None)
            commit_state["value"] = prospective
            return prospective

        def body(commit_state):
            try:
                existing = self._read_raw(identity)
            except WordPressDraftStateCorruptedError:
                # §28.3#12：persisted recordのidentity/schema corruptionで
                # compare-and-transitionを成立させられない場合もacknowledged=False
                # へ変換する（WordPressDraftStateCorruptedErrorを外へ出さない）。
                # 真のWordPressDraftStateIOError（filesystem I/O failure）は
                # ここでcatchせず、pre-commit failureとしてそのまま伝播させる。
                return _not_acknowledged(
                    commit_state,
                    "cannot transition: persisted record is corrupted or does not match the requested identity",
                )
            if existing is None:
                return _not_acknowledged(commit_state, "cannot transition: no existing record")
            if existing.member_run_id != expected_member_run_id:
                return _not_acknowledged(commit_state, "member_run_id mismatch")
            if existing.state is not SideEffectOperationState.ATTEMPTED:
                return _not_acknowledged(
                    commit_state,
                    f"cannot transition: current state is {existing.state.value}, expected ATTEMPTED",
                )
            record = WordPressDraftRecord(
                identity=identity,
                member_run_id=expected_member_run_id,
                state=SideEffectOperationState.CONFIRMED_SUCCESS,
                wp_post_id=wp_post_id,
                updated_at=updated_at,
                contract_version=existing.contract_version,
            )
            self._write_raw(record)  # CONFIRMED_SUCCESS durable ACK
            # durable ACK確認。直ちにcommitted=Trueを設定する。
            commit_state["committed"] = True
            prospective = TransitionResult(acknowledged=True, reason=None, record=record)
            commit_state["value"] = prospective
            return prospective

        lock = build_wordpress_draft_state_store_lock(self._locks_dir, identity)
        outcome = _run_with_commit_aware_lock(lock, identity, body)
        if outcome.value is not None and isinstance(outcome.value, TransitionResult):
            return outcome.value
        return TransitionResult(acknowledged=True, reason=None, record=self._read_raw(identity))

    def get(
        self, identity: SideEffectOperationIdentity, expected_member_run_id: str,
    ) -> WordPressDraftRecord | None:
        record = self._read_raw(identity)
        if record is None:
            return None
        if record.member_run_id != expected_member_run_id:
            raise WordPressDraftStateCorruptedError(
                "persisted member_run_id does not match the expected member_run_id"
            )
        return record
