"""
Workflow Engine実行コンテキスト（v2.7.0）

WorkflowEngineContext: Workflow Engine実行中の状態を保持するデータクラス

設計方針:
    - AgentContext（v2.0.0）と同様、設定値ではなく実行時状態のみを保持する。
    - event は Scheduler経由・手動経路（--job-id）のいずれの場合も必ず設定される
      （WorkflowEngineEvent.source で区別できるため、None は許容しない。
      docs/design/workflow_engine_foundation.md 6章、修正必須事項#2）。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from .workflow_engine_event import WorkflowEngineEvent
from .workflow_engine_result import WorkflowEngineStepResult


@dataclass
class WorkflowEngineContext:
    event: WorkflowEngineEvent
    dry_run: bool
    run_id: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    step_results: list[WorkflowEngineStepResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
