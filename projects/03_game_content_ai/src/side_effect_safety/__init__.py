"""
Side-Effect Safety 統合層（Release 6.32）

Source of Truth: docs/design/side_effect_fail_closed_human_review_safety_foundation.md

このパッケージは、Release 6.32が定めるSide-Effect Fail-Closed & Human Review Safety
architectureの共有基盤（Identity Schema・Explicit Side-Effect Execution Mode・
MEDIA_UPLOAD側のMediaUploadSafetyCoordinator）を提供する。
"""
from __future__ import annotations

from .side_effect_operation_identity import (
    ProtectedSideEffectKind,
    SideEffectOperationIdentity,
    SideEffectOperationState,
    SideEffectSite,
)
from .side_effect_execution_mode import (
    LegacyDirectExecutionContext,
    LegacyDirectProvenance,
    LegacyEntrypoint,
    LegacyExecutionOrigin,
    RetryLineageProtectedExecutionContext,
    RetryLineageProtectedProvenance,
    ExecutionModeFailureReasonCode,
    SideEffectExecutionModeContractError,
    SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE,
    build_legacy_direct_provenance,
    build_protected_execution_context,
    complete_legacy_execution_context,
    validate_side_effect_execution_context,
)
from .errors import (
    MediaUploadSafetyContractViolationError,
    MediaUploadSafetyIOError,
    MediaUploadSafetyImplementationContractError,
    MediaUploadSafetyTransitionError,
)
from .media_upload_context_phase import MediaUploadAttemptContextRecord, MediaUploadContextPhase
from .media_upload_safety_coordinator import (
    ConfirmedMediaUploadSafetyRecord,
    IoArmedMediaUploadSafetyRecord,
    MediaUploadSafetyCoordinator,
    NotApplicableMediaUploadSafetyRecord,
    PreparedMediaUploadSafetyRecord,
    build_media_upload_safety_coordinator,
)
from .media_upload_applicability_store import JsonMediaUploadApplicabilityStore, MediaUploadApplicabilityStore
from .media_upload_attempt_context_store import (
    JsonMediaUploadAttemptContextStore,
    MediaUploadAttemptContextStore,
)
from .media_upload_safety_coordinator_lock import (
    MediaUploadSafetyCoordinatorLock,
    build_media_upload_safety_coordinator_lock,
)
from .side_effect_safety_category import (
    ProtectedOperationContext,
    SideEffectSafetyCategory,
    SideEffectSafetyReport,
)

__all__ = [
    "ProtectedSideEffectKind",
    "SideEffectOperationIdentity",
    "SideEffectOperationState",
    "SideEffectSite",
    "LegacyDirectExecutionContext",
    "LegacyDirectProvenance",
    "LegacyEntrypoint",
    "LegacyExecutionOrigin",
    "RetryLineageProtectedExecutionContext",
    "RetryLineageProtectedProvenance",
    "ExecutionModeFailureReasonCode",
    "SideEffectExecutionModeContractError",
    "SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE",
    "build_legacy_direct_provenance",
    "build_protected_execution_context",
    "complete_legacy_execution_context",
    "validate_side_effect_execution_context",
    "MediaUploadSafetyContractViolationError",
    "MediaUploadSafetyIOError",
    "MediaUploadSafetyImplementationContractError",
    "MediaUploadSafetyTransitionError",
    "MediaUploadAttemptContextRecord",
    "MediaUploadContextPhase",
    "ConfirmedMediaUploadSafetyRecord",
    "IoArmedMediaUploadSafetyRecord",
    "MediaUploadSafetyCoordinator",
    "NotApplicableMediaUploadSafetyRecord",
    "PreparedMediaUploadSafetyRecord",
    "build_media_upload_safety_coordinator",
    "JsonMediaUploadApplicabilityStore",
    "MediaUploadApplicabilityStore",
    "JsonMediaUploadAttemptContextStore",
    "MediaUploadAttemptContextStore",
    "MediaUploadSafetyCoordinatorLock",
    "build_media_upload_safety_coordinator_lock",
    "ProtectedOperationContext",
    "SideEffectSafetyCategory",
    "SideEffectSafetyReport",
]
