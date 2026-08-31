"""
Retry Lineage Phase定義（v6.31.0、Release 6.31）

RetryLineagePhase: 1 lineageが取りうる4つの状態を表すEnum

設計方針（docs/design/retry_lineage_eligibility_durable_attempt_state.md 12章）:
    READY_ELIGIBLE → CLAIMED → EXECUTION_STARTED → TERMINAL
    disposition不問でTERMINALへ到達する（4-phase state machine）。
"""
from __future__ import annotations

from enum import Enum


class RetryLineagePhase(Enum):
    READY_ELIGIBLE = "ready_eligible"
    CLAIMED = "claimed"
    EXECUTION_STARTED = "execution_started"
    TERMINAL = "terminal"
