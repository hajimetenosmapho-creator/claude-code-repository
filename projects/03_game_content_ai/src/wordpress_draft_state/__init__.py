"""
WordPress Draft State パッケージ（Release 6.32）

`WORDPRESS_DRAFT_CREATION`（呼び出し箇所A・C）のside-effect fail-closed
write-ahead契約を担う。
"""
from __future__ import annotations

from .errors import (
    WordPressDraftStateCorruptedError,
    WordPressDraftStateIOError,
    WordPressDraftStateTransitionError,
)
from .wordpress_draft_record import WordPressDraftRecord
from .wordpress_draft_state_manager import WordPressDraftStateManager
from .wordpress_draft_state_store import (
    CreateResult,
    JsonWordPressDraftStateStore,
    TransitionResult,
    WordPressDraftStateStore,
)
from .wordpress_draft_state_store_lock import (
    WordPressDraftStateStoreLock,
    WordPressDraftStateStoreLockError,
    build_wordpress_draft_state_store_lock,
)

__all__ = [
    "WordPressDraftStateCorruptedError",
    "WordPressDraftStateIOError",
    "WordPressDraftStateTransitionError",
    "WordPressDraftRecord",
    "WordPressDraftStateManager",
    "CreateResult",
    "JsonWordPressDraftStateStore",
    "TransitionResult",
    "WordPressDraftStateStore",
    "WordPressDraftStateStoreLock",
    "WordPressDraftStateStoreLockError",
    "build_wordpress_draft_state_store_lock",
]
