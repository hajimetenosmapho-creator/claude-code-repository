"""
SideEffectSafetyClassifier（Release 6.32、10.2節）

Source of Truth: docs/design/side_effect_fail_closed_human_review_safety_foundation.md

`side_effect_safety`（MediaUploadSafetyCoordinator）と`wordpress_draft_state`
（WordPressDraftStateStore）の双方に依存する統合層。いずれの依存先パッケージも
本モジュールをimportしない（一方向依存）。
"""
from __future__ import annotations

from article_media_upload_state.errors import ArticleMediaUploadStateCorruptedError
from side_effect_safety.errors import MediaUploadSafetyContractViolationError
from side_effect_safety.media_upload_safety_coordinator import (
    ConfirmedMediaUploadSafetyRecord,
    IoArmedMediaUploadSafetyRecord,
    MediaUploadSafetyCoordinator,
    NotApplicableMediaUploadSafetyRecord,
    PreparedMediaUploadSafetyRecord,
)
from side_effect_safety.side_effect_operation_identity import (
    ProtectedSideEffectKind,
    SideEffectOperationIdentity,
    SideEffectOperationState,
)
from side_effect_safety.side_effect_safety_category import (
    ProtectedOperationContext,
    SideEffectSafetyCategory,
    SideEffectSafetyReport,
)
from wordpress_draft_state.errors import WordPressDraftStateCorruptedError
from wordpress_draft_state.wordpress_draft_state_store import WordPressDraftStateStore


class SideEffectSafetyClassifier:
    """8章のidentityをoperationごとに構成し、9.3/9.9節のstoreから権威ある
    durable stateを読み取ってSideEffectSafetyCategoryへ写像する（12・12.5節）。"""

    def __init__(
        self,
        media_coordinator: MediaUploadSafetyCoordinator,
        draft_state: WordPressDraftStateStore,
    ):
        self._media_coordinator = media_coordinator
        self._draft_state = draft_state

    def classify(
        self,
        root_run_id: str,
        attempt_ordinal: int,
        member_run_id: str,
        operations: "list[ProtectedOperationContext]",
    ) -> SideEffectSafetyReport:
        entries = []
        for op in operations:
            identity = SideEffectOperationIdentity(
                root_run_id=root_run_id,
                attempt_ordinal=attempt_ordinal,
                operation_kind=op.operation_kind,
                effect_site=op.effect_site,
                operation_instance_key=op.operation_instance_key,
            )
            category = self._classify_one(identity, member_run_id, op.operation_kind)
            entries.append((op, category))
        return SideEffectSafetyReport(entries=tuple(entries))

    def _classify_one(
        self,
        identity: SideEffectOperationIdentity,
        member_run_id: str,
        operation_kind: ProtectedSideEffectKind,
    ) -> SideEffectSafetyCategory:
        if operation_kind is ProtectedSideEffectKind.MEDIA_UPLOAD:
            try:
                record = self._media_coordinator.get(identity, member_run_id)
            except (MediaUploadSafetyContractViolationError, ArticleMediaUploadStateCorruptedError):
                # Release 6.32 sub-milestone 6D-6B（28.-1節#11、production fix）：
                # MediaUploadSafetyContractViolationErrorはside_effect_safety
                # package自身が検出するcontract violation。
                # ArticleMediaUploadStateCorruptedErrorは_read_all()が読む
                # 3ストアのうち唯一別package（article_media_upload_state）に
                # 属するArticleMediaUploadStateManager.get_state()が検出する
                # 同種のpersisted state corruptionであり、同一のfail-closed
                # classificationとして扱う。真のfilesystem I/O failure
                # （*IOError系）はApproved Architectureにexact mappingが
                # 明記されていないため、ここでは広くcatchしない。
                return SideEffectSafetyCategory.CONTRACT_VIOLATION
            if record is None:
                # 12.5節：非存在（record自体がNone）のみ12.2節「レコード非存在」行を
                # 適用する。reachability rules（StepOutcomeCategory）は参照しない。
                return SideEffectSafetyCategory.CONTRACT_VIOLATION
            if isinstance(record, NotApplicableMediaUploadSafetyRecord):
                return SideEffectSafetyCategory.NOT_APPLICABLE
            if isinstance(record, PreparedMediaUploadSafetyRecord):
                return SideEffectSafetyCategory.SAFE_TO_CONTINUE
            if isinstance(record, IoArmedMediaUploadSafetyRecord):
                return SideEffectSafetyCategory.IN_PROGRESS_OR_UNKNOWN
            if isinstance(record, ConfirmedMediaUploadSafetyRecord):
                return SideEffectSafetyCategory.CONFIRMED_SUCCESS
            return SideEffectSafetyCategory.CONTRACT_VIOLATION

        # WORDPRESS_DRAFT_CREATION（9.3・12.2節）
        try:
            record = self._draft_state.get(identity, member_run_id)
        except WordPressDraftStateCorruptedError:
            return SideEffectSafetyCategory.CONTRACT_VIOLATION
        if record is None:
            return SideEffectSafetyCategory.CONTRACT_VIOLATION
        if record.state is SideEffectOperationState.CONFIRMED_SUCCESS:
            return SideEffectSafetyCategory.CONFIRMED_SUCCESS
        if record.state is SideEffectOperationState.ATTEMPTED:
            return SideEffectSafetyCategory.IN_PROGRESS_OR_UNKNOWN
        if record.state is SideEffectOperationState.NOT_APPLICABLE:
            return SideEffectSafetyCategory.NOT_APPLICABLE
        return SideEffectSafetyCategory.CONTRACT_VIOLATION
