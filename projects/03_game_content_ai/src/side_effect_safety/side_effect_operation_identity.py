"""
Side-Effect Operation Identity Schema（Release 6.32）

Source of Truth: docs/design/side_effect_fail_closed_human_review_safety_foundation.md
6章（Design Decision A）・7章（Design Decision B）・8章（Design Decision C）

`WordPressDraftStateStore`（wordpress_draft_state）・`MediaUploadSafetyCoordinator`
（side_effect_safety）の双方が共有する、不変のclosed-set型・identity schemaを
1箇所に集約する。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class ProtectedSideEffectKind(Enum):
    """Protected Side Effect Operationのclosed set（6章、不変）。"""

    WORDPRESS_DRAFT_CREATION = "wordpress_draft_creation"
    MEDIA_UPLOAD = "media_upload"


class SideEffectOperationState(Enum):
    """Side-Effect Operation State Machine（7章、不変）。"""

    NOT_APPLICABLE = "not_applicable"
    ATTEMPTED = "attempted"
    CONFIRMED_SUCCESS = "confirmed_success"


class SideEffectSite(Enum):
    """呼び出し箇所を区別するEnum（8章、不変）。"""

    NEWS_STEP = "news_step"
    PUBLISH_STEP = "publish_step"


@dataclass(frozen=True)
class SideEffectOperationIdentity:
    """Identity Schema（8章、不変）。

    5つの構成要素すべてが永続化キーの導出元であり、可変フィールドではない
    （26章Non-Recycle Invariant）。
    """

    root_run_id: str
    attempt_ordinal: int
    operation_kind: ProtectedSideEffectKind
    effect_site: SideEffectSite
    operation_instance_key: str

    def as_store_key(self) -> str:
        return (
            f"{self.root_run_id}:{self.attempt_ordinal}:"
            f"{self.operation_kind.value}:{self.effect_site.value}:"
            f"{self.operation_instance_key}"
        )
