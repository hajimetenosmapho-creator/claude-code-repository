"""
Workflow Monitor Status定義（v2.9.0）

WorkflowMonitorStatus: Workflowの監視上の状態を表すEnum

設計方針:
    - RUNNING/SUCCESS/FAILED/TIMEOUTの4値のみを判定ロジック（WorkflowMonitor._judge()）が返す。
    - CANCELLED/WAITINGは将来拡張用の予約値。判定対象となる元データ（Workflow Engine・
      Execution Historyの状態モデル）が現時点で存在しないため、判定ロジックからは
      到達しない（docs/design/workflow_monitor_foundation.md 2章・4章）。
"""
from __future__ import annotations

from enum import Enum


class WorkflowMonitorStatus(Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"
    WAITING = "waiting"
