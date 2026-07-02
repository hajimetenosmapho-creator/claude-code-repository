"""
Execution History設定（v2.8.0）

ExecutionHistoryConfig: Execution History機能の有効・無効と保存先を保持するデータクラス

設計方針:
    - デフォルトは enabled=True。Agent系のゲート（AI_AGENT_ENABLED等、デフォルトfalse）とは
      異なり、Execution Historyはローカルへの記録のみで外部への副作用を持たないため、
      LOG_ENABLED（v1.8.0、デフォルトtrue）と同じ「原則有効」をデフォルトとする
      （docs/design/execution_history_foundation.md 5章）。

環境変数:
    EXECUTION_HISTORY_ENABLED  (default: true)
    EXECUTION_HISTORY_DIR      (default: logs/execution_history、project_root からの相対パス)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ExecutionHistoryConfig:
    enabled: bool
    history_dir: Path

    @classmethod
    def from_env(cls, project_root: Path) -> "ExecutionHistoryConfig":
        """環境変数から ExecutionHistoryConfig を構築する。"""
        enabled = os.environ.get("EXECUTION_HISTORY_ENABLED", "true").lower() == "true"
        dir_name = os.environ.get("EXECUTION_HISTORY_DIR", "logs/execution_history")
        return cls(enabled=enabled, history_dir=project_root / dir_name)

    def is_ready(self) -> bool:
        """記録を行ってよいか（ゲートが開いているか）を返す。"""
        return self.enabled
