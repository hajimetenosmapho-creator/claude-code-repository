"""
WordPress Draft Record（Release 6.32、9.2節）

Source of Truth: docs/design/side_effect_fail_closed_human_review_safety_foundation.md
"""
from __future__ import annotations

from dataclasses import dataclass

from side_effect_safety.side_effect_operation_identity import (
    SideEffectOperationIdentity,
    SideEffectOperationState,
)


@dataclass(frozen=True)
class WordPressDraftRecord:
    """`WORDPRESS_DRAFT_CREATION`のdurable record schema（9.2節）。

    `wp_post_id`はCONFIRMED_SUCCESSでのみ正のint必須。NOT_APPLICABLE/ATTEMPTEDでは
    None必須（6.32 current APIでは`create_not_applicable()`は除外されているため、
    NOT_APPLICABLE stateのrecordが実際に永続化されることはない）。
    """

    identity: SideEffectOperationIdentity
    member_run_id: str
    state: SideEffectOperationState
    wp_post_id: int | None
    updated_at: str
    contract_version: int

    def __post_init__(self) -> None:
        if not isinstance(self.identity, SideEffectOperationIdentity):
            raise ValueError("identity must be a SideEffectOperationIdentity")
        if type(self.member_run_id) is not str or not self.member_run_id.strip():
            raise ValueError("member_run_id must be a non-empty, non-whitespace str")
        if not isinstance(self.state, SideEffectOperationState):
            raise ValueError("state must be a SideEffectOperationState member")

        if self.state is SideEffectOperationState.CONFIRMED_SUCCESS:
            if type(self.wp_post_id) is not int or self.wp_post_id <= 0:
                raise ValueError(
                    "CONFIRMED_SUCCESS requires a positive int wp_post_id (bool rejected)"
                )
        else:
            if self.wp_post_id is not None:
                raise ValueError(f"{self.state} requires wp_post_id=None")

        if type(self.contract_version) is not int or self.contract_version <= 0:
            raise ValueError("contract_version must be a positive int (bool rejected)")
