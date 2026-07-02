"""
Scheduler Event定義（v2.6.0）

SchedulerEvent: SchedulerEngineが「実行すべき」と判断したJobに対して生成するイベント

設計方針:
    - Scheduler は判断結果として SchedulerEvent を生成するだけであり、
      実際のAgent起動・処理実行は一切行わない
      （Scheduler は NewsAgent / ReviewAgent / PublishAgent を直接呼ばない、
      という Event Driven Architecture の原則を体現するデータモデル）
    - 既存の Trigger Agent 側（AgentTask）と連携しやすいよう、metadata フィールドは
      SchedulerJob.metadata をそのまま引き継ぐ構造にする。呼び出し側はこの
      metadata を AgentTask(task_id=..., params=event.metadata) のように
      組み立て直して利用できる
    - execute_time は Job が「実行されるべきと判定された時刻」であり、
      実際に処理が実行された時刻（今回のFoundation Releaseでは記録しない）とは
      異なる概念である
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SchedulerEvent:
    job_id: str
    execute_time: datetime
    trigger_reason: str
    metadata: dict = field(default_factory=dict)
