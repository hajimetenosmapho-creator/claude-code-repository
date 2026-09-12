"""
WordPress Draft State Manager（Release 6.32、9.5節）
"""
from __future__ import annotations

from side_effect_safety.commit_aware_lock import now_utc_iso
from side_effect_safety.side_effect_operation_identity import SideEffectOperationIdentity

from .errors import WordPressDraftStateTransitionError
from .wordpress_draft_record import WordPressDraftRecord
from .wordpress_draft_state_store import WordPressDraftStateStore


class WordPressDraftStateManager:
    """`record_not_applicable()`は6.32 current APIから除外済み（9.3節）。"""

    def __init__(self, store: WordPressDraftStateStore):
        self._store = store

    def record_attempted(
        self, identity: SideEffectOperationIdentity, member_run_id: str,
    ) -> WordPressDraftRecord:
        result = self._store.create_attempted(identity, member_run_id, now_utc_iso())
        if not result.acknowledged:
            raise WordPressDraftStateTransitionError(result.reason)
        return result.record

    def record_confirmed(
        self, identity: SideEffectOperationIdentity, member_run_id: str, wp_post_id: int,
    ) -> WordPressDraftRecord:
        if type(wp_post_id) is not int or wp_post_id <= 0:
            raise ValueError("wp_post_id must be a positive int (bool rejected)")
        result = self._store.transition_to_confirmed(identity, member_run_id, wp_post_id, now_utc_iso())
        if not result.acknowledged:
            raise WordPressDraftStateTransitionError(result.reason)
        return result.record

    def get_state(
        self, identity: SideEffectOperationIdentity, expected_member_run_id: str,
    ) -> WordPressDraftRecord | None:
        return self._store.get(identity, expected_member_run_id)
