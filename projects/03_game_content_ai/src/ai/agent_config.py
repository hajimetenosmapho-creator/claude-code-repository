"""
Agent設定（v2.0.0）

AgentConfig: エージェント基盤の設定値のみを保持するデータクラス

設計方針:
    - 設定値のみを保持する（実行時状態は AgentContext が担う）
    - Configuration First: is_ready() が False → NullAgentManager を返す
    - デフォルトは無効（false）とし、既存の自動実行フロー（WorkflowRunner経由）に
      影響を与えない

環境変数:
    AI_AGENT_ENABLED  (default: false)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AgentConfig:
    enabled: bool
    base_dir: Path

    @classmethod
    def from_env(cls, base_dir: Path | None = None) -> "AgentConfig":
        """
        環境変数から AgentConfig を構築する。

        Args:
            base_dir: プロジェクトのルートディレクトリ（None の場合は現在のディレクトリ）
        """
        enabled = os.environ.get("AI_AGENT_ENABLED", "false").lower() == "true"
        resolved_base = base_dir if base_dir is not None else Path(".")

        return cls(
            enabled=enabled,
            base_dir=resolved_base,
        )

    def is_ready(self) -> bool:
        """Agent基盤が実行可能な状態か返す。"""
        return self.enabled
