"""
Execution History Event定義（v2.8.0）

ExecutionHistoryEvent: WorkflowExecutionRecordに時系列で追記される最小の構造化イベント

設計方針:
    - ExecutionHistoryManager（start_run/start_step/finish_step/finish_run）が
      呼ばれるたびに自動生成する。呼び出し側（WorkflowEngineExecutor）が個別に
      イベントを組み立てる必要はない（docs/design/execution_history_foundation.md 5章）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

EVENT_WORKFLOW_STARTED = "workflow_started"
EVENT_WORKFLOW_FINISHED = "workflow_finished"
EVENT_STEP_STARTED = "step_started"
EVENT_STEP_FINISHED = "step_finished"


@dataclass
class ExecutionHistoryEvent:
    event_type: str
    occurred_at: datetime
    message: str
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "occurred_at": self.occurred_at.isoformat(),
            "message": self.message,
            "payload": dict(self.payload),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionHistoryEvent":
        return cls(
            event_type=data["event_type"],
            occurred_at=datetime.fromisoformat(data["occurred_at"]),
            message=data["message"],
            payload=dict(data.get("payload") or {}),
        )
