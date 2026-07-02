"""
Workflow Execution Record定義（v2.8.0）

WorkflowExecutionStatus: Workflow全体の実行状態を表すEnum
WorkflowExecutionRecord: 1回のWorkflow実行の履歴を保持するデータクラス

設計方針:
    - run_id は WorkflowEngineManager._generate_run_id()（既存、uuid.uuid4().hex）が
      発行した値をそのまま再利用する。Execution History側で別のID体系は新設しない
      （docs/design/execution_history_foundation.md 5章）。
    - workflow_name は Foundation Releaseでは固定値 "workflow_engine" を想定する
      （src/ai/workflow_*.py の WorkflowRunner は対象外、同設計書4章）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from .execution_history_event import ExecutionHistoryEvent
from .step_execution_record import StepExecutionRecord


class WorkflowExecutionStatus(Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"


@dataclass
class WorkflowExecutionRecord:
    run_id: str
    workflow_name: str
    source: str
    job_id: str
    status: WorkflowExecutionStatus
    started_at: datetime
    finished_at: datetime | None = None
    steps: list[StepExecutionRecord] = field(default_factory=list)
    events: list[ExecutionHistoryEvent] = field(default_factory=list)
    error_message: str | None = None

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "workflow_name": self.workflow_name,
            "source": self.source,
            "job_id": self.job_id,
            "status": self.status.value,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "steps": [s.to_dict() for s in self.steps],
            "events": [e.to_dict() for e in self.events],
            "error_message": self.error_message,
        }

    def to_json(self) -> str:
        import json
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowExecutionRecord":
        return cls(
            run_id=data["run_id"],
            workflow_name=data["workflow_name"],
            source=data["source"],
            job_id=data["job_id"],
            status=WorkflowExecutionStatus(data["status"]),
            started_at=datetime.fromisoformat(data["started_at"]),
            finished_at=datetime.fromisoformat(data["finished_at"]) if data.get("finished_at") else None,
            steps=[StepExecutionRecord.from_dict(s) for s in data.get("steps", [])],
            events=[ExecutionHistoryEvent.from_dict(e) for e in data.get("events", [])],
            error_message=data.get("error_message"),
        )
