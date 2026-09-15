"""
Scheduler Dispatch Ledger Results定義（v6.34.0、Release 6.34）

ClaimResult:       claim()の戻り値
ReconcileSummary:  reconcile_stale_claims()の戻り値（成功時のみ返る。失敗時は例外、8.5章）

設計方針: dispatch_run_id等と同じく診断専用。安全性はledger.claim()のacknowledged
          （呼び出し元が確認する戻り値そのもの）のみに依拠する。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ClaimResult:
    acknowledged: bool
    reason: str | None = None


@dataclass
class ReconcileSummary:
    recovery_marked: int = 0
