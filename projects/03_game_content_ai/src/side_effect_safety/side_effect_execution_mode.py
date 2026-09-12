"""
Explicit Side-Effect Execution Mode（Release 6.32）

Source of Truth: docs/design/side_effect_fail_closed_human_review_safety_foundation.md
2章（Scope境界）・14章（Subprocess/Cross-boundary Identity Propagation）

`RetryLineageProtectedExecutionContext`（RETRY_LINEAGE_PROTECTED）と
`LegacyDirectExecutionContext`（LEGACY_DIRECT）を、互いにフィールド構成が
異なるdiscriminated unionとして分離する（2.1節Trusted Composition Boundary
Invariant）。mode混同（protectedとlegacyの値レベルでの区別不能）を型レベルで
構造的に不可能にする。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from enum import Enum


class LegacyEntrypoint(Enum):
    """Stage 1：プロセスがどのlegacy entrypointから起動されたかを示すclosed
    set（8値、2.1・2.3節）。"""

    RUN_NEWS_AGENT = "run_news_agent"
    RUN_WORKFLOW_TRIGGER_AGENT = "run_workflow_trigger_agent"
    RUN_PUBLISH_TRIGGER_AGENT = "run_publish_trigger_agent"
    RUN_REVIEW_TRIGGER_AGENT = "run_review_trigger_agent"
    RUN_AI_PUBLISH = "run_ai_publish"
    RUN_AI_WORKFLOW = "run_ai_workflow"
    RUN_WORKFLOW_ENGINE_DIRECT = "run_workflow_engine_direct"
    RUN_MAIN_DIRECT = "run_main_direct"


class LegacyExecutionOrigin(Enum):
    """Stage 2：実際にprotected side-effect operationへ到達しうるコンポーネント
    の識別子（closed set、8値、2.1・2.3節）。"""

    NEWS_AGENT = "news_agent"
    WORKFLOW_TRIGGER_AGENT = "workflow_trigger_agent"
    PUBLISH_TRIGGER_AGENT = "publish_trigger_agent"
    REVIEW_TRIGGER_AGENT = "review_trigger_agent"
    AI_PUBLISH_DIRECT = "ai_publish_direct"
    AI_WORKFLOW_DIRECT = "ai_workflow_direct"
    WORKFLOW_ENGINE_DIRECT = "workflow_engine_direct"
    MAIN_DIRECT = "main_direct"


@dataclass(frozen=True)
class LegacyDirectProvenance:
    """Stage 1完成物（2.1節）。"""

    legacy_entrypoint: LegacyEntrypoint


@dataclass(frozen=True)
class RetryLineageProtectedExecutionContext:
    """RETRY_LINEAGE_PROTECTEDの最終形（2.1節）。4フィールドすべて必須。"""

    root_run_id: str
    attempt_ordinal: int
    member_run_id: str
    side_effect_contract_version: int


@dataclass(frozen=True)
class LegacyDirectExecutionContext:
    """LEGACY_DIRECTの最終形（Stage 2完成物、2.1節）。"""

    legacy_entrypoint: LegacyEntrypoint
    legacy_execution_origin: LegacyExecutionOrigin


@dataclass(frozen=True)
class RetryLineageProtectedProvenance:
    """RetryExecutorが構築時点で確定できる3フィールドのみを持つpre-context
    （2.1a節）。member_run_idはまだ含まない。"""

    root_run_id: str
    attempt_ordinal: int
    side_effect_contract_version: int


# SideEffectExecutionContext = RetryLineageProtectedExecutionContext | LegacyDirectExecutionContext（2.1節）
# SideEffectExecutionProvenance = RetryLineageProtectedProvenance | LegacyDirectExecutionContext（2.1a節）
# 型チェッカー向けのUnion aliasはPython実行時には不要なため、docstring上でのみ表現する
# （dataclass自体はいずれもisinstance判定で分岐する、2.1b節）。


# 2.1c節 Legacy Entrypoint/Origin Compatibility Matrix
_AGENT_MANAGER_ENTRYPOINTS = (
    LegacyEntrypoint.RUN_NEWS_AGENT,
    LegacyEntrypoint.RUN_WORKFLOW_TRIGGER_AGENT,
    LegacyEntrypoint.RUN_PUBLISH_TRIGGER_AGENT,
    LegacyEntrypoint.RUN_REVIEW_TRIGGER_AGENT,
)
_AGENT_MANAGER_ORIGINS = (
    LegacyExecutionOrigin.NEWS_AGENT,
    LegacyExecutionOrigin.WORKFLOW_TRIGGER_AGENT,
    LegacyExecutionOrigin.PUBLISH_TRIGGER_AGENT,
    LegacyExecutionOrigin.REVIEW_TRIGGER_AGENT,
)

ALLOWED_LEGACY_ENTRYPOINT_ORIGINS: frozenset[tuple[LegacyEntrypoint, LegacyExecutionOrigin]] = frozenset({
    *(
        (entrypoint, origin)
        for entrypoint in _AGENT_MANAGER_ENTRYPOINTS
        for origin in _AGENT_MANAGER_ORIGINS
    ),
    (LegacyEntrypoint.RUN_AI_PUBLISH, LegacyExecutionOrigin.AI_PUBLISH_DIRECT),
    (LegacyEntrypoint.RUN_AI_WORKFLOW, LegacyExecutionOrigin.AI_WORKFLOW_DIRECT),
    (LegacyEntrypoint.RUN_WORKFLOW_ENGINE_DIRECT, LegacyExecutionOrigin.WORKFLOW_ENGINE_DIRECT),
    (LegacyEntrypoint.RUN_MAIN_DIRECT, LegacyExecutionOrigin.MAIN_DIRECT),
})


class ExecutionModeFailureReasonCode(Enum):
    """secret-safeな構造化理由コード（2.5節）。生の環境変数値・secretは含まない。"""

    MISSING_EXECUTION_MODE = "missing_execution_mode"
    UNKNOWN_EXECUTION_MODE = "unknown_execution_mode"
    UNKNOWN_LEGACY_ENTRYPOINT = "unknown_legacy_entrypoint"
    UNKNOWN_LEGACY_EXECUTION_ORIGIN = "unknown_legacy_execution_origin"
    CONTRADICTORY_LEGACY_PAIR = "contradictory_legacy_pair"
    MISSING_LINEAGE_CONTEXT = "missing_lineage_context"
    CONTEXT_MISMATCH = "context_mismatch"
    CONTRACT_VERSION_MISMATCH = "contract_version_mismatch"
    CONTRADICTORY_SERIALIZED_FORM = "contradictory_serialized_form"
    SUBPROCESS_CONTRACT_VIOLATION = "subprocess_contract_violation"
    # Codex Final Review Blocking#2対応：呼び出し箇所A/B/C（15.4・15.6・15.7節）が
    # RetryLineageProtectedExecutionContext（protected）で実行されているにも
    # かかわらず、ManifestRegistrarFacade相当のregistrarが渡されていない場合に
    # 送出する。protected modeではregistrar省略によるmanifest registration
    # bypassを許可しない（legacy modeのみ既存どおりregistrar省略を許容する）。
    PROTECTED_MANIFEST_REGISTRAR_REQUIRED = "protected_manifest_registrar_required"


class SideEffectExecutionModeContractError(Exception):
    """SideEffectExecutionMode契約違反を表すfail-closed例外（2.5節）。呼び出し元は
    これをcatchして成功へ変換してはならない。"""

    def __init__(self, reason_code: ExecutionModeFailureReasonCode):
        self.reason_code = reason_code
        super().__init__(reason_code.value)


# NEWS subprocess境界（14.6節）専用の予約exit code。main.py Outcome Contract
# （0/1/2/20/21）のいずれとも衝突しない値として3を予約する。
SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE = 3


def _is_well_formed_root_run_id(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_well_formed_attempt_ordinal(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def _is_well_formed_member_run_id(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_well_formed_contract_version(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 1


def build_protected_execution_context(
    root_run_id: str, attempt_ordinal: int, member_run_id: str, side_effect_contract_version: int,
) -> RetryLineageProtectedExecutionContext:
    """protected factory。RetryLineageRecordのauthoritative valueからのみ
    呼び出してよい（2.2節）。"""
    return RetryLineageProtectedExecutionContext(
        root_run_id=root_run_id, attempt_ordinal=attempt_ordinal,
        member_run_id=member_run_id, side_effect_contract_version=side_effect_contract_version,
    )


def build_legacy_direct_provenance(legacy_entrypoint: LegacyEntrypoint) -> LegacyDirectProvenance:
    """legacy Stage 1 factory。8つのlegacy entrypointのcomposition rootからのみ
    呼び出してよい（2.3節）。"""
    return LegacyDirectProvenance(legacy_entrypoint=legacy_entrypoint)


def complete_legacy_execution_context(
    provenance: LegacyDirectProvenance, legacy_execution_origin: LegacyExecutionOrigin,
) -> LegacyDirectExecutionContext:
    """legacy Stage 2 factory（唯一の完成点、2.3節）。"""
    return LegacyDirectExecutionContext(
        legacy_entrypoint=provenance.legacy_entrypoint,
        legacy_execution_origin=legacy_execution_origin,
    )


def validate_side_effect_execution_context(
    context: "RetryLineageProtectedExecutionContext | LegacyDirectExecutionContext | None",
) -> "RetryLineageProtectedExecutionContext | LegacyDirectExecutionContext":
    """呼び出し箇所A/B/C（15.4・15.6・15.7節）が共通で呼ぶ、唯一のvalidation関数
    （2.1b節）。isinstance判定のみで分岐する。"""
    if context is None:
        raise SideEffectExecutionModeContractError(
            ExecutionModeFailureReasonCode.MISSING_EXECUTION_MODE,
        )

    if isinstance(context, RetryLineageProtectedExecutionContext):
        if not _is_well_formed_root_run_id(context.root_run_id):
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.MISSING_LINEAGE_CONTEXT,
            )
        if not _is_well_formed_attempt_ordinal(context.attempt_ordinal):
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.CONTEXT_MISMATCH,
            )
        if not _is_well_formed_member_run_id(context.member_run_id):
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.CONTEXT_MISMATCH,
            )
        if not _is_well_formed_contract_version(context.side_effect_contract_version):
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.CONTRACT_VERSION_MISMATCH,
            )
        return context

    if isinstance(context, LegacyDirectExecutionContext):
        if context.legacy_entrypoint not in LegacyEntrypoint:
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.UNKNOWN_LEGACY_ENTRYPOINT,
            )
        if context.legacy_execution_origin not in LegacyExecutionOrigin:
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.UNKNOWN_LEGACY_EXECUTION_ORIGIN,
            )
        if (context.legacy_entrypoint, context.legacy_execution_origin) not in ALLOWED_LEGACY_ENTRYPOINT_ORIGINS:
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.CONTRADICTORY_LEGACY_PAIR,
            )
        return context

    raise SideEffectExecutionModeContractError(
        ExecutionModeFailureReasonCode.UNKNOWN_EXECUTION_MODE,
    )


# 14.2節：subprocess境界での環境変数key（既存main.py CLI/env varとは衝突しない）。
ENV_EXECUTION_MODE = "RETRY_LINEAGE_EXECUTION_MODE"
ENV_ROOT_RUN_ID = "RETRY_LINEAGE_ROOT_RUN_ID"
ENV_ATTEMPT_ORDINAL = "RETRY_LINEAGE_ATTEMPT_ORDINAL"
ENV_MEMBER_RUN_ID = "RETRY_LINEAGE_MEMBER_RUN_ID"
ENV_CONTRACT_VERSION = "RETRY_LINEAGE_CONTRACT_VERSION"
ENV_LEGACY_ENTRYPOINT = "RETRY_LINEAGE_LEGACY_ENTRYPOINT"
ENV_LEGACY_EXECUTION_ORIGIN = "RETRY_LINEAGE_LEGACY_EXECUTION_ORIGIN"

_MODE_TAG_PROTECTED = "retry_lineage_protected"
_MODE_TAG_LEGACY = "legacy_direct"

_PROTECTED_ENV_KEYS = (ENV_ROOT_RUN_ID, ENV_ATTEMPT_ORDINAL, ENV_MEMBER_RUN_ID, ENV_CONTRACT_VERSION)
_LEGACY_ENV_KEYS = (ENV_LEGACY_ENTRYPOINT, ENV_LEGACY_EXECUTION_ORIGIN)


def _serialize_execution_context(
    context: "RetryLineageProtectedExecutionContext | LegacyDirectExecutionContext | None",
) -> dict[str, str]:
    """2.1a節のtyped unionをenvironment variablesへ変換する唯一の関数（14.2節）。
    protected/legacyそれぞれ対応するfieldのみを書き出し、両者を混在させない。
    context欠落（None）はlegacyへの推測を行わずMISSING_EXECUTION_MODEでfail-closed
    する（2.4節Fail-Closed Matrix）。"""
    if context is None:
        raise SideEffectExecutionModeContractError(ExecutionModeFailureReasonCode.MISSING_EXECUTION_MODE)
    if isinstance(context, RetryLineageProtectedExecutionContext):
        return {
            ENV_EXECUTION_MODE: _MODE_TAG_PROTECTED,
            ENV_ROOT_RUN_ID: context.root_run_id,
            ENV_ATTEMPT_ORDINAL: str(context.attempt_ordinal),
            ENV_MEMBER_RUN_ID: context.member_run_id,
            ENV_CONTRACT_VERSION: str(context.side_effect_contract_version),
        }
    if isinstance(context, LegacyDirectExecutionContext):
        return {
            ENV_EXECUTION_MODE: _MODE_TAG_LEGACY,
            ENV_LEGACY_ENTRYPOINT: context.legacy_entrypoint.value,
            ENV_LEGACY_EXECUTION_ORIGIN: context.legacy_execution_origin.value,
        }
    raise SideEffectExecutionModeContractError(ExecutionModeFailureReasonCode.UNKNOWN_EXECUTION_MODE)


def _parse_and_validate_remaining_context(
    raw_attempt_ordinal: str | None, raw_member_run_id: str | None, raw_contract_version: str | None,
) -> tuple[int, str, int]:
    """protected contextの残り3フィールドをparse・validateする（14.3節）。root_run_id
    は呼び出し元が別途identify済みのため、ここでの失敗はhard failureではなく
    CONTEXT_MISMATCH/CONTRACT_VERSION_MISMATCH（CONTRACT_VIOLATION経路）とする。"""
    try:
        attempt_ordinal = int(raw_attempt_ordinal) if raw_attempt_ordinal is not None else None
    except ValueError:
        attempt_ordinal = None
    if not _is_well_formed_attempt_ordinal(attempt_ordinal):
        raise SideEffectExecutionModeContractError(ExecutionModeFailureReasonCode.CONTEXT_MISMATCH)

    if not _is_well_formed_member_run_id(raw_member_run_id):
        raise SideEffectExecutionModeContractError(ExecutionModeFailureReasonCode.CONTEXT_MISMATCH)

    try:
        contract_version = int(raw_contract_version) if raw_contract_version is not None else None
    except ValueError:
        contract_version = None
    if not _is_well_formed_contract_version(contract_version):
        raise SideEffectExecutionModeContractError(ExecutionModeFailureReasonCode.CONTRACT_VERSION_MISMATCH)

    return attempt_ordinal, raw_member_run_id, contract_version


def _parse_execution_context_from_env() -> "RetryLineageProtectedExecutionContext | LegacyDirectExecutionContext":
    """14.2節`_serialize_execution_context()`の逆変換。main.py起動時に一度だけ呼ぶ
    （14.3節）。execution-envelope関連変数が完全に1つも存在しない場合に限り、
    main.py自身がtrusted direct composition rootとしてRUN_MAIN_DIRECT/MAIN_DIRECTの
    provenanceを自己発生させる。"""
    protected_fields_present = any(os.environ.get(k) is not None for k in _PROTECTED_ENV_KEYS)
    legacy_fields_present = any(os.environ.get(k) is not None for k in _LEGACY_ENV_KEYS)

    raw_mode = os.environ.get(ENV_EXECUTION_MODE)
    if raw_mode is None:
        if protected_fields_present or legacy_fields_present:
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.CONTRADICTORY_SERIALIZED_FORM,
            )
        provenance = build_legacy_direct_provenance(LegacyEntrypoint.RUN_MAIN_DIRECT)
        return complete_legacy_execution_context(provenance, LegacyExecutionOrigin.MAIN_DIRECT)

    if raw_mode == _MODE_TAG_PROTECTED:
        if legacy_fields_present:
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.CONTRADICTORY_SERIALIZED_FORM,
            )
        root_run_id = os.environ.get(ENV_ROOT_RUN_ID)
        if not _is_well_formed_root_run_id(root_run_id):
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.MISSING_LINEAGE_CONTEXT,
            )
        attempt_ordinal, member_run_id, contract_version = _parse_and_validate_remaining_context(
            os.environ.get(ENV_ATTEMPT_ORDINAL),
            os.environ.get(ENV_MEMBER_RUN_ID),
            os.environ.get(ENV_CONTRACT_VERSION),
        )
        return build_protected_execution_context(
            root_run_id=root_run_id, attempt_ordinal=attempt_ordinal,
            member_run_id=member_run_id, side_effect_contract_version=contract_version,
        )

    if raw_mode == _MODE_TAG_LEGACY:
        if protected_fields_present:
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.CONTRADICTORY_SERIALIZED_FORM,
            )
        raw_entrypoint = os.environ.get(ENV_LEGACY_ENTRYPOINT)
        try:
            entrypoint = LegacyEntrypoint(raw_entrypoint)
        except ValueError:
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.UNKNOWN_LEGACY_ENTRYPOINT,
            ) from None
        raw_origin = os.environ.get(ENV_LEGACY_EXECUTION_ORIGIN)
        try:
            origin = LegacyExecutionOrigin(raw_origin)
        except ValueError:
            raise SideEffectExecutionModeContractError(
                ExecutionModeFailureReasonCode.UNKNOWN_LEGACY_EXECUTION_ORIGIN,
            ) from None
        return LegacyDirectExecutionContext(legacy_entrypoint=entrypoint, legacy_execution_origin=origin)

    raise SideEffectExecutionModeContractError(ExecutionModeFailureReasonCode.UNKNOWN_EXECUTION_MODE)
