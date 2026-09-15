"""
Dispatch Phase定義（v6.34.0、Release 6.34）

DispatchPhase: DispatchLedgerEntryのライフサイクルを表す3値のEnum

設計方針（docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md 8.1・8.2章）:
    - CLAIMED -> CONFIRMED（正常完了、terminal）
    - CLAIMED -> RECOVERY_REQUIRED（reconciliationによるorphan回収、terminal）
    - 4-phase（RetryLineagePhase）ではなく3-phase。owner_token authorityは持たない
      （8.4章：single-active-driver制約下ではRetry Lineageと異なり複数の正当な
      claimant候補が恒常的に存在しないため）。
    - write-once-forward-only。RECOVERY_REQUIRED / CONFIRMEDからの遷移（再claim）は
      存在しない（Out of Scope: RECOVERY_REQUIRED自動復旧なし）。
"""
from __future__ import annotations

from enum import Enum


class DispatchPhase(Enum):
    CLAIMED = "claimed"
    CONFIRMED = "confirmed"
    RECOVERY_REQUIRED = "recovery_required"
