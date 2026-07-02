"""
Step Execution Record定義（v2.8.0）

StepExecutionStatus:   Stepの実行状態を表すEnum
StepExecutionRecord:   1Stepの実行履歴を保持するデータクラス

設計方針:
    - step は WorkflowEngineStep（src/workflow_engine/）を直接受け取らず、str（.value）
      のみを受け取る。execution_historyがworkflow_engineの型を一切importしないための
      一方向依存の徹底（docs/design/execution_history_foundation.md 4章・6章）。
    - WorkflowEngineStepResult（executed/success/skipped_reason）からの変換規則は
      WorkflowEngineExecutor側が担う（同設計書6章の対応表）。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class StepExecutionStatus(Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_REACHED = "not_reached"


@dataclass
class StepExecutionRecord:
    step: str
    status: StepExecutionStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    skipped_reason: str | None = None

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "error_message": self.error_message,
            "skipped_reason": self.skipped_reason,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StepExecutionRecord":
        return cls(
            step=data["step"],
            status=StepExecutionStatus(data["status"]),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            finished_at=datetime.fromisoformat(data["finished_at"]) if data.get("finished_at") else None,
            error_message=data.get("error_message"),
            skipped_reason=data.get("skipped_reason"),
        )
