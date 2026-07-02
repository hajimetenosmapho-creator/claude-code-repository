"""
Workflow Monitor Record定義（v2.9.0）

WorkflowMonitorRecord: 1 Workflowの監視結果を保持するデータクラス

設計方針:
    - source_status は WorkflowExecutionStatus（execution_historyパッケージのEnum）を
      そのまま公開フィールドの型にはせず、str（.value）として保持する
      （docs/design/workflow_monitor_foundation.md 4章）。
    - steps は WorkflowExecutionRecord.steps のコピーを保持する（読み取り専用という
      設計意図を実装レベルでも明確にするため、Architecture Review指摘事項#1）。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from execution_history import StepExecutionRecord

from .workflow_monitor_status import WorkflowMonitorStatus


@dataclass
class WorkflowMonitorRecord:
    run_id: str
    workflow_name: str
    monitor_status: WorkflowMonitorStatus
    source_status: str
    source: str
    job_id: str
    started_at: datetime
    finished_at: datetime | None
    elapsed_seconds: float
    reason: str | None
    steps: list[StepExecutionRecord]
