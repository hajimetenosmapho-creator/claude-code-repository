"""
Dispatch Ledger Entry定義（v6.34.0、Release 6.34）

DispatchLedgerEntry: stable event identity（job_id x occurrence_minute）ごとの
                      dispatch記録1件を表すdurable recordの中身

設計方針（docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md 7・8章）:
    - event_identity = f"{job_id}::{occurrence_minute}"（分単位に正規化されたキー）。
    - dispatch_run_id / outcome_summary / detail は診断・監査目的のみであり、
      安全性（duplicate suppression）は phase 状態のみに依拠する（8.3章）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .dispatch_phase import DispatchPhase


@dataclass
class DispatchLedgerEntry:
    event_identity: str
    job_id: str
    occurrence_minute: str
    phase: DispatchPhase
    claimed_at: datetime
    confirmed_at: datetime | None = None
    dispatch_run_id: str | None = None
    outcome_summary: str | None = None
    detail: str | None = None
    updated_at: datetime = field(default_factory=datetime.now)
