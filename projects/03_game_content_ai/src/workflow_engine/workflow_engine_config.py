"""
Workflow Engine設定（v2.7.0）

WorkflowEngineConfig: Workflow Engine全体（二重ゲートの2段目）の設定値を保持するデータクラス

設計方針:
    - Configuration First: AgentConfig（AI_AGENT_ENABLED）と同様、
      WORKFLOW_ENGINE_ENABLED（デフォルトfalse）で有効・無効を切り替える。
    - Workflow Engine全体の有効化は二重ゲート（AI_AGENT_ENABLED × WORKFLOW_ENGINE_ENABLED）、
      各ステップの実行可否はステップごとの既存Configの is_ready() に委ねる「二層構造」とする
      （docs/design/workflow_engine_foundation.md 7章）。

環境変数:
    WORKFLOW_ENGINE_ENABLED  (default: false)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class WorkflowEngineConfig:
    enabled: bool
    project_root: Path

    @classmethod
    def from_env(cls, project_root: Path) -> "WorkflowEngineConfig":
        """環境変数から WorkflowEngineConfig を構築する。"""
        enabled = os.environ.get("WORKFLOW_ENGINE_ENABLED", "false").lower() == "true"
        return cls(enabled=enabled, project_root=project_root)

    def is_ready(self) -> bool:
        """Workflow Engine全体のゲート（二重ゲートの2段目）が開いているか返す。"""
        return self.enabled
