"""
MediaUploadSafetyCoordinator（Release 6.32、9.9節）

Source of Truth: docs/design/side_effect_fail_closed_human_review_safety_foundation.md

`MEDIA_UPLOAD`の全durable state変更は、単一のCoordinator（Shared Coordination
Boundary）を経由する（25章Invariant #15）。4公開メソッド（record_not_applicable /
record_prepared / record_attempted / record_confirmed）はいずれも
`_run_with_commit_aware_lock()`を経由してidentity-scoped lockを取得し、durable
semantic ACK確定を戻り値構築・post-commit cleanupの成否から独立させる（ACK
Determinism、9.9.6節）。`get()`はidentity-lock-freeであり、個々のstoreの
old-or-newな完全ファイル内容のみを保証する——複数storeにまたがるcomposite
atomic/linearizable snapshotは主張しない（27.3節、authoritative）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, ClassVar, Protocol

from article_media_upload_state.article_media_upload_state import ArticleMediaUploadState
from article_media_upload_state.article_media_upload_state_manager import (
    ArticleMediaUploadStateManager,
)

from .commit_aware_lock import (
    CleanupDiagnostic,
    CommitAwareResult,
    _run_with_commit_aware_lock,
    now_utc_iso,
)
from .errors import (
    MediaUploadSafetyContractViolationError,
    MediaUploadSafetyIOError,
    MediaUploadSafetyImplementationContractError,
    MediaUploadSafetyTransitionError,
)
from .media_upload_applicability_store import MediaUploadApplicabilityStore, NotApplicableRecord
from .media_upload_attempt_context_store import MediaUploadAttemptContextStore
from .media_upload_context_phase import MediaUploadAttemptContextRecord, MediaUploadContextPhase
from .media_upload_safety_coordinator_lock import (
    MediaUploadSafetyCoordinatorLock,
    build_media_upload_safety_coordinator_lock,
)
from .side_effect_operation_identity import SideEffectOperationIdentity

from pathlib import Path


@dataclass(frozen=True)
class NotApplicableMediaUploadSafetyRecord:
    """`record_not_applicable()`のみが構築するsemantic kind（Gate OFF）。"""

    identity: SideEffectOperationIdentity
    member_run_id: str
    updated_at: str


@dataclass(frozen=True)
class PreparedMediaUploadSafetyRecord:
    """`record_prepared()`のみが構築するsemantic kind（9.9.4.7節）。"""

    identity: SideEffectOperationIdentity
    member_run_id: str
    updated_at: str


@dataclass(frozen=True)
class IoArmedMediaUploadSafetyRecord:
    """`record_attempted()`のsemantic commit pointが構築するsemantic kind。"""

    identity: SideEffectOperationIdentity
    member_run_id: str
    updated_at: str


@dataclass(frozen=True)
class ConfirmedMediaUploadSafetyRecord:
    """`record_confirmed()`のみが構築するsemantic kind。"""

    identity: SideEffectOperationIdentity
    member_run_id: str
    media_id: int
    updated_at: str


MediaUploadSafetyRecord = (
    NotApplicableMediaUploadSafetyRecord
    | PreparedMediaUploadSafetyRecord
    | IoArmedMediaUploadSafetyRecord
    | ConfirmedMediaUploadSafetyRecord
)


class MediaUploadSafetyRecoveryPolicy(Protocol):
    """4つの具体的なPolicyが満たすべき最小契約（9.9.4.2節）。"""

    expected_type: "ClassVar[type[MediaUploadSafetyRecord]]"

    def build_minimal(self, updated_at: str) -> "MediaUploadSafetyRecord": ...

    def validate(self, value: object) -> "MediaUploadSafetyRecord | None": ...


@dataclass(frozen=True)
class NotApplicableRecoveryPolicy:
    identity: SideEffectOperationIdentity
    member_run_id: str
    expected_type: "ClassVar[type]" = NotApplicableMediaUploadSafetyRecord

    def build_minimal(self, updated_at: str) -> "MediaUploadSafetyRecord":
        return NotApplicableMediaUploadSafetyRecord(
            identity=self.identity, member_run_id=self.member_run_id, updated_at=updated_at,
        )

    def validate(self, value: object) -> "MediaUploadSafetyRecord | None":
        return value if isinstance(value, self.expected_type) else None


@dataclass(frozen=True)
class PreparedRecoveryPolicy:
    identity: SideEffectOperationIdentity
    member_run_id: str
    expected_type: "ClassVar[type]" = PreparedMediaUploadSafetyRecord

    def build_minimal(self, updated_at: str) -> "MediaUploadSafetyRecord":
        return PreparedMediaUploadSafetyRecord(
            identity=self.identity, member_run_id=self.member_run_id, updated_at=updated_at,
        )

    def validate(self, value: object) -> "MediaUploadSafetyRecord | None":
        return value if isinstance(value, self.expected_type) else None


@dataclass(frozen=True)
class IoArmedRecoveryPolicy:
    identity: SideEffectOperationIdentity
    member_run_id: str
    expected_type: "ClassVar[type]" = IoArmedMediaUploadSafetyRecord

    def build_minimal(self, updated_at: str) -> "MediaUploadSafetyRecord":
        return IoArmedMediaUploadSafetyRecord(
            identity=self.identity, member_run_id=self.member_run_id, updated_at=updated_at,
        )

    def validate(self, value: object) -> "MediaUploadSafetyRecord | None":
        return value if isinstance(value, self.expected_type) else None


@dataclass(frozen=True)
class ConfirmedRecoveryPolicy:
    identity: SideEffectOperationIdentity
    member_run_id: str
    media_id: int
    expected_type: "ClassVar[type]" = ConfirmedMediaUploadSafetyRecord

    def build_minimal(self, updated_at: str) -> "MediaUploadSafetyRecord":
        return ConfirmedMediaUploadSafetyRecord(
            identity=self.identity, member_run_id=self.member_run_id,
            media_id=self.media_id, updated_at=updated_at,
        )

    def validate(self, value: object) -> "MediaUploadSafetyRecord | None":
        return value if isinstance(value, self.expected_type) else None


def _minimal_safety_record(
    identity: SideEffectOperationIdentity, member_run_id: str, policy: "MediaUploadSafetyRecoveryPolicy",
) -> MediaUploadSafetyRecord:
    """`_value_or_recover()`の最終フォールバック段。追加I/Oを一切行わない。"""
    try:
        updated_at = now_utc_iso()
    except Exception:
        updated_at = ""
    return policy.build_minimal(updated_at)


# _read_all()が返すcategory（9.9.7節のCross-Store Combination Tableをそのまま
# 実装した内部分類、18通り中6通りが有効な状態、残り12通りはCONTRACT_VIOLATION）。
# ここでの"ALL_ABSENT"は「classify()（12.2節、reconciliation層）が返すCONTRACT_
# VIOLATION」とは異なる——単に「まだ何も記録されていない」という、新規write-ahead
# operationにとっての正常な出発点を表す（get()はこの場合Noneを返し、Noneを
# CONTRACT_VIOLATIONへ変換する判断はclassify()側の責務である、12.2節）。
_CATEGORY_ALL_ABSENT = "ALL_ABSENT"
_CATEGORY_NOT_APPLICABLE = "NOT_APPLICABLE"
_CATEGORY_PREPARED_ONLY = "PREPARED_ONLY"
_CATEGORY_PREPARED_PLUS_ATTEMPTED = "PREPARED_PLUS_ATTEMPTED"
_CATEGORY_IO_ARMED_PLUS_ATTEMPTED = "IO_ARMED_PLUS_ATTEMPTED"
_CATEGORY_IO_ARMED_PLUS_CONFIRMED = "IO_ARMED_PLUS_CONFIRMED"
_CATEGORY_CONTRACT_VIOLATION = "CONTRACT_VIOLATION"


def _classify_combination(marker, context, upload_state) -> str:
    """9.9.7節Cross-Store Combination Table（18通り）をそのまま実装する。"""
    if marker is not None:
        if context is None and upload_state is None:
            return _CATEGORY_NOT_APPLICABLE
        return _CATEGORY_CONTRACT_VIOLATION

    if context is None:
        if upload_state is None:
            return _CATEGORY_ALL_ABSENT
        return _CATEGORY_CONTRACT_VIOLATION

    if context.phase is MediaUploadContextPhase.PREPARED:
        if upload_state is None:
            return _CATEGORY_PREPARED_ONLY
        if upload_state.state is ArticleMediaUploadState.ATTEMPT_STARTED:
            return _CATEGORY_PREPARED_PLUS_ATTEMPTED
        return _CATEGORY_CONTRACT_VIOLATION  # PREPARED + CONFIRMED_SUCCESS

    # context.phase is IO_ARMED
    if upload_state is None:
        return _CATEGORY_CONTRACT_VIOLATION  # IO_ARMEDはATTEMPTED確定後にのみ到達しうる
    if upload_state.state is ArticleMediaUploadState.ATTEMPT_STARTED:
        return _CATEGORY_IO_ARMED_PLUS_ATTEMPTED
    return _CATEGORY_IO_ARMED_PLUS_CONFIRMED  # UPLOAD_CONFIRMED


@dataclass(frozen=True)
class _ThreeStoreSnapshot:
    """marker・context（phase含む）・upload_stateの3つを読んだ結果（9.9.4.4節）。"""

    identity: SideEffectOperationIdentity
    member_run_id: str
    category: str
    marker: "NotApplicableRecord | None"
    context: "MediaUploadAttemptContextRecord | None"
    upload_state: object  # ArticleMediaUploadRecord | None

    def to_safety_record(self) -> "MediaUploadSafetyRecord | None":
        """カテゴリごとにexact semantic kindへ写像する。ALL_ABSENTはNone
        （レコード非存在）、CONTRACT_VIOLATIONはfail-closedに例外送出する
        （get()の契約、9.9.4.6節）。"""
        if self.category == _CATEGORY_ALL_ABSENT:
            return None
        if self.category == _CATEGORY_NOT_APPLICABLE:
            return NotApplicableMediaUploadSafetyRecord(
                identity=self.identity, member_run_id=self.member_run_id,
                updated_at=self.marker.updated_at,
            )
        if self.category in (_CATEGORY_PREPARED_ONLY, _CATEGORY_PREPARED_PLUS_ATTEMPTED):
            return PreparedMediaUploadSafetyRecord(
                identity=self.identity, member_run_id=self.member_run_id,
                updated_at=self.context.updated_at,
            )
        if self.category == _CATEGORY_IO_ARMED_PLUS_ATTEMPTED:
            return IoArmedMediaUploadSafetyRecord(
                identity=self.identity, member_run_id=self.member_run_id,
                updated_at=self.context.updated_at,
            )
        if self.category == _CATEGORY_IO_ARMED_PLUS_CONFIRMED:
            return ConfirmedMediaUploadSafetyRecord(
                identity=self.identity, member_run_id=self.member_run_id,
                media_id=self.upload_state.media_id, updated_at=self.upload_state.updated_at,
            )
        raise MediaUploadSafetyContractViolationError(
            f"cross-store combination is not a valid lifecycle state (category={self.category})"
        )


class MediaUploadSafetyCoordinator:
    def __init__(
        self,
        media_upload_manager: ArticleMediaUploadStateManager,
        applicability_store: MediaUploadApplicabilityStore,
        attempt_context_store: MediaUploadAttemptContextStore,
        lock_factory: "Callable[[SideEffectOperationIdentity], MediaUploadSafetyCoordinatorLock]",
    ):
        self._media_upload_manager = media_upload_manager
        self._applicability_store = applicability_store
        self._attempt_context_store = attempt_context_store
        self._lock_factory = lock_factory

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    def _read_all(
        self, identity: SideEffectOperationIdentity, expected_member_run_id: str, allow_absent_only: bool,
    ) -> _ThreeStoreSnapshot:
        """marker・context・upload_stateの3つを読み、identity/member_run_idを検証した
        上で9.9.7節の組み合わせ表に従いcategoryを判定する（lockを取得しない）。

        allow_absent_only=Trueで呼ばれ、判定したcategoryがALL_ABSENTでない場合
        （record_not_applicable()が同一identity・同一member_run_idで2回目以降
        呼ばれた等）、本メソッド自身がMediaUploadSafetyTransitionErrorを直接
        送出する（唯一の決定的outcome、Invariant #11）。
        """
        marker = self._applicability_store.get(identity, expected_member_run_id)
        context = self._attempt_context_store.get(identity, expected_member_run_id)
        upload_state = self._media_upload_manager.get_state(identity.as_store_key())

        category = _classify_combination(marker, context, upload_state)

        if allow_absent_only and category != _CATEGORY_ALL_ABSENT:
            raise MediaUploadSafetyTransitionError(
                f"cannot proceed: identity already has evidence (category={category})"
            )

        return _ThreeStoreSnapshot(
            identity=identity, member_run_id=expected_member_run_id, category=category,
            marker=marker, context=context, upload_state=upload_state,
        )

    def _log_cleanup_diagnostics_if_any(
        self, identity: SideEffectOperationIdentity, method_name: str,
        diagnostics: "tuple[CleanupDiagnostic, ...]",
    ) -> None:
        # Release 6.32 sub-milestone 6D-6B（28.-2節#4）：本メソッドは
        # _run_with_commit_aware_lock()のtry/exceptの外側で呼ばれるため、
        # ロギング自体の失敗（例：コンソールのエンコーディング起因の
        # print()失敗）がACK済みのsemantic successを呼び出し元エラーへ
        # 転化させないよう、ロギング処理全体をbest-effortで囲む。
        try:
            for diag in diagnostics:
                print(
                    f"  [MEDIA UPLOAD SAFETY WARNING] {method_name}: post-commit cleanup issue "
                    f"(reason={diag.reason_code.value}, exception_type={diag.exception_type})"
                )
        except Exception:
            pass

    def _log_recovery_validation_failure(
        self, identity: SideEffectOperationIdentity, stage: str, expected_type: type, actual_type: type,
    ) -> None:
        print(
            f"  [MEDIA UPLOAD SAFETY WARNING] recovery validation failed at {stage} "
            f"(expected={expected_type.__name__}, actual={actual_type.__name__})"
        )

    def _value_or_recover(
        self,
        outcome: "CommitAwareResult",
        identity: SideEffectOperationIdentity,
        member_run_id: str,
        policy: "MediaUploadSafetyRecoveryPolicy",
    ) -> "MediaUploadSafetyRecord":
        """3段のfallbackで構成する（9.9.4.4節）。全段で`policy.validate()`による
        runtime isinstance検証を行う。"""
        validated = policy.validate(outcome.value) if outcome.value is not None else None
        if validated is not None:
            return validated
        if outcome.value is not None:
            self._log_recovery_validation_failure(
                identity, "stage1_commit_state_value", policy.expected_type, type(outcome.value),
            )

        try:
            snapshot = self._read_all(identity, member_run_id, allow_absent_only=False)
            candidate = snapshot.to_safety_record()
        except Exception:
            candidate = None
        else:
            validated = policy.validate(candidate)
            if validated is not None:
                return validated
            if candidate is not None:
                self._log_recovery_validation_failure(
                    identity, "stage2_durable_reread", policy.expected_type, type(candidate),
                )

        minimal = _minimal_safety_record(identity, member_run_id, policy)
        validated = policy.validate(minimal)
        if validated is None:
            raise MediaUploadSafetyImplementationContractError(
                "RecoveryPolicy.build_minimal() returned a value that fails its own "
                "validate(); this is an implementation contract violation"
            )
        return validated

    # ------------------------------------------------------------------
    # 4公開メソッド + get()
    # ------------------------------------------------------------------

    def record_not_applicable(
        self, identity: SideEffectOperationIdentity, member_run_id: str,
    ) -> "NotApplicableMediaUploadSafetyRecord":
        def body(commit_state):
            self._read_all(identity, member_run_id, allow_absent_only=True)
            result = self._applicability_store.create(identity, member_run_id, now_utc_iso())
            if not result.acknowledged:
                raise MediaUploadSafetyIOError(result.reason)
            commit_state["committed"] = True
            prospective_record = NotApplicableMediaUploadSafetyRecord(
                identity=identity, member_run_id=member_run_id, updated_at=result.record.updated_at,
            )
            commit_state["value"] = prospective_record
            return prospective_record

        outcome = _run_with_commit_aware_lock(self._lock_factory(identity), identity, body)
        self._log_cleanup_diagnostics_if_any(identity, "record_not_applicable", outcome.cleanup_diagnostics)
        return self._value_or_recover(
            outcome, identity, member_run_id,
            policy=NotApplicableRecoveryPolicy(identity=identity, member_run_id=member_run_id),
        )

    def record_prepared(
        self, identity: SideEffectOperationIdentity, member_run_id: str,
    ) -> "PreparedMediaUploadSafetyRecord":
        def body(commit_state):
            snapshot = self._read_all(identity, member_run_id, allow_absent_only=False)
            if snapshot.category == _CATEGORY_ALL_ABSENT:
                context_result = self._attempt_context_store.create_prepared(
                    identity, member_run_id, now_utc_iso(),
                )
                if not context_result.acknowledged:
                    raise MediaUploadSafetyIOError(context_result.reason)
                context_record = context_result.record
            elif snapshot.category in (_CATEGORY_PREPARED_ONLY, _CATEGORY_PREPARED_PLUS_ATTEMPTED):
                context_record = snapshot.context  # 冪等no-op（Safe Continuationと同型）
            else:
                raise MediaUploadSafetyTransitionError(
                    f"cannot prepare: unexpected existing combination {snapshot.category}"
                )
            commit_state["committed"] = True
            prospective_record = PreparedMediaUploadSafetyRecord(
                identity=identity, member_run_id=member_run_id, updated_at=context_record.updated_at,
            )
            commit_state["value"] = prospective_record
            return prospective_record

        outcome = _run_with_commit_aware_lock(self._lock_factory(identity), identity, body)
        self._log_cleanup_diagnostics_if_any(identity, "record_prepared", outcome.cleanup_diagnostics)
        return self._value_or_recover(
            outcome, identity, member_run_id,
            policy=PreparedRecoveryPolicy(identity=identity, member_run_id=member_run_id),
        )

    def record_attempted(
        self, identity: SideEffectOperationIdentity, member_run_id: str,
    ) -> "IoArmedMediaUploadSafetyRecord":
        def body(commit_state):
            snapshot = self._read_all(identity, member_run_id, allow_absent_only=False)

            if snapshot.category == _CATEGORY_ALL_ABSENT:
                context_result = self._attempt_context_store.create_prepared(
                    identity, member_run_id, now_utc_iso(),
                )
                if not context_result.acknowledged:  # PREPARED ACK（committed=Falseのまま）
                    raise MediaUploadSafetyIOError(context_result.reason)
                upload_started = self._media_upload_manager.record_upload_started(  # ATTEMPTED ACK
                    article_identity=identity.as_store_key(),
                )
            elif snapshot.category in (_CATEGORY_PREPARED_ONLY, _CATEGORY_PREPARED_PLUS_ATTEMPTED):
                if snapshot.category == _CATEGORY_PREPARED_ONLY:
                    upload_started = self._media_upload_manager.record_upload_started(
                        article_identity=identity.as_store_key(),
                    )
                else:
                    upload_started = snapshot.upload_state  # Safe Continuation（不変）
            else:
                raise MediaUploadSafetyTransitionError(
                    f"cannot proceed: unexpected existing combination {snapshot.category}"
                )

            transition_result = self._attempt_context_store.transition_to_io_armed(
                identity, member_run_id, now_utc_iso(),
            )
            if not transition_result.acknowledged:
                raise MediaUploadSafetyIOError(transition_result.reason)
            # IO_ARMED durable ACK確認。直ちにcommitted=Trueを設定する。
            commit_state["committed"] = True
            prospective_record = IoArmedMediaUploadSafetyRecord(
                identity=identity, member_run_id=member_run_id, updated_at=upload_started.updated_at,
            )
            commit_state["value"] = prospective_record
            return prospective_record

        outcome = _run_with_commit_aware_lock(self._lock_factory(identity), identity, body)
        self._log_cleanup_diagnostics_if_any(identity, "record_attempted", outcome.cleanup_diagnostics)
        return self._value_or_recover(
            outcome, identity, member_run_id,
            policy=IoArmedRecoveryPolicy(identity=identity, member_run_id=member_run_id),
        )

    def record_confirmed(
        self, identity: SideEffectOperationIdentity, member_run_id: str, media_id: int,
    ) -> "ConfirmedMediaUploadSafetyRecord":
        def body(commit_state):
            snapshot = self._read_all(identity, member_run_id, allow_absent_only=False)
            if snapshot.category != _CATEGORY_IO_ARMED_PLUS_ATTEMPTED:
                raise MediaUploadSafetyTransitionError(
                    f"cannot confirm: current combination is {snapshot.category}, "
                    f"expected IO_ARMED_PLUS_ATTEMPTED"
                )
            record = self._media_upload_manager.record_upload_succeeded(  # CONFIRMED_SUCCESS durable ACK
                article_identity=identity.as_store_key(), media_id=media_id,
            )
            commit_state["committed"] = True
            prospective_record = ConfirmedMediaUploadSafetyRecord(
                identity=identity, member_run_id=member_run_id,
                media_id=media_id, updated_at=record.updated_at,
            )
            commit_state["value"] = prospective_record
            return prospective_record

        outcome = _run_with_commit_aware_lock(self._lock_factory(identity), identity, body)
        self._log_cleanup_diagnostics_if_any(identity, "record_confirmed", outcome.cleanup_diagnostics)
        return self._value_or_recover(
            outcome, identity, member_run_id,
            policy=ConfirmedRecoveryPolicy(identity=identity, member_run_id=member_run_id, media_id=media_id),
        )

    def get(
        self, identity: SideEffectOperationIdentity, expected_member_run_id: str,
    ) -> "MediaUploadSafetyRecord | None":
        """read専用・lock-free（27.3節、authoritative）。durable stateのみを権威とする
        （reconciliationがCONFIRMED_SUCCESS/NOT_APPLICABLEをauthoritativeに扱えることの
        直接的な根拠、9.9.6・9.9.7節）。identity-scoped lockは取得しない——stale
        identity lockの影響も受けない（27.5節）。`_read_all()`が読む各storeは
        それぞれ単体でold-or-newのcomplete file内容を返すが、複数store横断の
        composite atomicityは保証しない——cross-store skew自体は正常な観測タイミング
        の結果であり、その意味はCross-Store Combination Table（9.9.7節）が定める
        exactな組み合わせ判定にのみ従う（27.3節）。"""
        snapshot = self._read_all(identity, expected_member_run_id, allow_absent_only=False)
        return snapshot.to_safety_record()


def build_media_upload_safety_coordinator(
    media_upload_manager: ArticleMediaUploadStateManager,
    applicability_store: MediaUploadApplicabilityStore,
    attempt_context_store: MediaUploadAttemptContextStore,
    locks_dir: Path,
) -> MediaUploadSafetyCoordinator:
    """identity-scoped lock factoryをlocks_dirへ束縛した状態でCoordinatorを構築する。"""
    return MediaUploadSafetyCoordinator(
        media_upload_manager=media_upload_manager,
        applicability_store=applicability_store,
        attempt_context_store=attempt_context_store,
        lock_factory=lambda identity: build_media_upload_safety_coordinator_lock(locks_dir, identity),
    )
