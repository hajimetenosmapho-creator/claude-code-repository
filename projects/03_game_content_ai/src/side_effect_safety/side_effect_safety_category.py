"""
SideEffectSafetyCategory（Release 6.32、11章）

Source of Truth: docs/design/side_effect_fail_closed_human_review_safety_foundation.md
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .side_effect_operation_identity import ProtectedSideEffectKind, SideEffectSite


class SideEffectSafetyCategory(Enum):
    """12章の決定表が出力するclosed set（11.1節）。"""

    NOT_APPLICABLE = "not_applicable"
    SAFE_TO_CONTINUE = "safe_to_continue"
    CONFIRMED_SUCCESS = "confirmed_success"
    IN_PROGRESS_OR_UNKNOWN = "in_progress_or_unknown"
    CONTRACT_VIOLATION = "contract_violation"


# 13章 resolve_final_disposition()のworst_case()優先順位。
# CONTRACT_VIOLATION == IN_PROGRESS_OR_UNKNOWN（同率最高、HRRを発火） >
# CONFIRMED_SUCCESS > SAFE_TO_CONTINUE == NOT_APPLICABLE（同率最下位、HRRを発火しない）
_PRIORITY = {
    SideEffectSafetyCategory.CONTRACT_VIOLATION: 3,
    SideEffectSafetyCategory.IN_PROGRESS_OR_UNKNOWN: 3,
    SideEffectSafetyCategory.CONFIRMED_SUCCESS: 2,
    SideEffectSafetyCategory.SAFE_TO_CONTINUE: 1,
    SideEffectSafetyCategory.NOT_APPLICABLE: 1,
}


@dataclass(frozen=True)
class ProtectedOperationContext:
    """`classify()`が受け取る、判定対象operationの識別情報（root_run_id・
    attempt_ordinal・member_run_idを除く3構成要素、10.2節）。"""

    operation_kind: ProtectedSideEffectKind
    effect_site: SideEffectSite
    operation_instance_key: str


@dataclass(frozen=True)
class SideEffectSafetyReport:
    """`classify()`の戻り値。判定対象operationごとの分類結果を保持する。"""

    entries: "tuple[tuple[ProtectedOperationContext, SideEffectSafetyCategory], ...]"

    def worst_case(self) -> SideEffectSafetyCategory:
        """13章`resolve_final_disposition()`が参照する優先順位に従い、最も
        深刻なcategoryを返す。operationが1件も存在しない場合はNOT_APPLICABLE
        （HRRを発火させない、安全側のvacuous case）を返す。"""
        if not self.entries:
            return SideEffectSafetyCategory.NOT_APPLICABLE
        return max((category for _, category in self.entries), key=lambda c: _PRIORITY[c])

    def categories(self) -> "tuple[SideEffectSafetyCategory, ...]":
        return tuple(category for _, category in self.entries)
