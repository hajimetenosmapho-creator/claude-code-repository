"""
Scheduler Driver設定（v6.34.0、Release 6.34）

SchedulerDriverConfig: Scheduler Driver自体の有効・無効を保持するデータクラス

環境変数:
    SCHEDULER_DRIVER_ENABLED  (default: false)

設計方針（docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md 6.6章）:
    - デフォルトは enabled=False（既存gate命名規約「安全側で止める」原則を踏襲。
      RETRY_LINEAGE_ENABLED・AI_AGENT_ENABLED等と同じ扱い）。
    - 本ゲートはWorkflowEngineManagerが内部で持つAI_AGENT_ENABLED /
      WORKFLOW_ENGINE_ENABLEDの二重ゲートとは独立した、Scheduler Driver自身の
      ゲートである。SCHEDULER_DRIVER_ENABLED=falseの場合、scripts/run_scheduler_driver.py
      はlock取得・ledger初期化のいずれも行わずinfoメッセージのみ表示して終了する
      （scripts/run_workflow_engine.pyのNullWorkflowEngineManager早期return
      パターンを踏襲）。
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class SchedulerDriverConfig:
    enabled: bool

    @classmethod
    def from_env(cls) -> "SchedulerDriverConfig":
        enabled = os.environ.get("SCHEDULER_DRIVER_ENABLED", "false").lower() == "true"
        return cls(enabled=enabled)

    def is_ready(self) -> bool:
        return self.enabled
