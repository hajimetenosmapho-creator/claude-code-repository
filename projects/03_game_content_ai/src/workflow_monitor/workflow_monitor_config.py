"""
Workflow Monitor設定（v2.9.0）

WorkflowMonitorConfig: Workflow Monitor機能の有効・無効とTimeout閾値を保持するデータクラス

設計方針:
    - デフォルトは enabled=True。Workflow MonitorはExecution Historyへの書き込みすら
      行わない、純粋な読み取り＋計算のみの層であり、外部への副作用を一切持たないため、
      ExecutionHistoryConfig（v2.8.0、デフォルトtrue）と同じ「原則有効」をデフォルトとする
      （docs/design/workflow_monitor_foundation.md 3章）。
    - Timeoutの閾値はWorkflow Monitor本体にハードコードせず、本Configに一元化する。
      これにより将来のRetry Engine・Metrics Foundation・Dashboard Foundationも
      同じ閾値を参照できる（Charter 5.2節「Single Source of Truth」の帰結）。
    - project_root・保存先パスは保持しない。Execution Historyのデータをどこから読むかは
      ExecutionHistoryConfig（無改修）の責務のままとする。

環境変数:
    WORKFLOW_MONITOR_ENABLED           (default: true)
    WORKFLOW_MONITOR_TIMEOUT_SECONDS   (default: 3600)
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class WorkflowMonitorConfig:
    enabled: bool
    timeout_seconds: int

    @classmethod
    def from_env(cls) -> "WorkflowMonitorConfig":
        """環境変数から WorkflowMonitorConfig を構築する。"""
        enabled = os.environ.get("WORKFLOW_MONITOR_ENABLED", "true").lower() == "true"
        timeout_seconds = int(os.environ.get("WORKFLOW_MONITOR_TIMEOUT_SECONDS", "3600"))
        return cls(enabled=enabled, timeout_seconds=timeout_seconds)

    def is_ready(self) -> bool:
        """判定を行ってよいか（ゲートが開いているか）を返す。"""
        return self.enabled
