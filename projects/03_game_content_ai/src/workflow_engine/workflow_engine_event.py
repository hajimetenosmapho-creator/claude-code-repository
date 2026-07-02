"""
Workflow Engine Event定義（v2.7.0）

WorkflowEngineEvent: Workflow Engineが実行単位として扱うイベント

設計方針:
    - SchedulerEvent（src/scheduler/scheduler_event.py、v2.6.0）とフィールド構成は近いが、
      あえて別クラスとして定義する。src/workflow_engine/ が src/scheduler/ を
      importしない設計にするため（docs/design/workflow_engine_foundation.md 10章）。
      SchedulerEvent → WorkflowEngineEvent の変換は呼び出し元
      （scripts/run_workflow_engine.py）の責務とする。
    - source は起動経路を表す（同設計書6章の対応表、修正必須事項#2）：
        SOURCE_SCHEDULER: SchedulerEvent経由（job_id/triggered_at/trigger_reasonは
                           SchedulerEventの値をそのままコピー）
        SOURCE_MANUAL:     --job-id経由（triggered_atは呼び出し時点のdatetime.now()、
                           trigger_reasonは固定文言）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

SOURCE_SCHEDULER = "scheduler"
SOURCE_MANUAL = "manual"


@dataclass
class WorkflowEngineEvent:
    job_id: str
    source: str
    triggered_at: datetime
    trigger_reason: str
    metadata: dict = field(default_factory=dict)
