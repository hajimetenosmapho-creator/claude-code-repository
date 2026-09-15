"""
Scheduler Driver Cycle Result（v6.34.0、Release 6.34）

DispatchOutcome:          1 eventのdispatch試行結果（診断用）
SchedulerDriverCycleResult: run_once() 1回分の結果
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class DispatchOutcome:
    event_identity: str
    job_id: str
    dispatched: bool
    reason: str | None = None
    run_id: str | None = None


@dataclass
class SchedulerDriverCycleResult:
    dispatched: list[DispatchOutcome] = field(default_factory=list)
    skipped: list[DispatchOutcome] = field(default_factory=list)
    recovery_marked: int = 0
