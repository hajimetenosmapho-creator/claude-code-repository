"""
Workflow Trigger Agent設定（v2.3.0）

WorkflowTriggerAgentConfig: WorkflowTriggerAgent / WorkflowPipelineRunner が使用する設定値のみを保持するデータクラス

設計方針:
    - 設定値のみを保持する（実行時状態は AgentContext / PipelineResult が担う）
    - Configuration First: 二重ゲート方式の2段目（WORKFLOW_TRIGGER_AGENT_ENABLED）をここで判定する
      （1段目の AI_AGENT_ENABLED は AgentConfig が担う。AgentManager側で両方をチェックする）
    - workflow_enabled は既存の WorkflowConfig.is_ready() をそのまま再利用し、
      AI_WORKFLOW_ENABLED の解釈ロジックを重複実装しない（WorkflowConfig とのズレを防ぐため）
    - reports_dir は outputs/workflow_reports/ を指すが、is_ready() 判定では
      存在確認をしない（未実行で存在しない場合も「過去実行なし」として判断できるようにするため。
      実際の存在確認は WorkflowTriggerAgent.decide() 側の責務とする）

環境変数:
    WORKFLOW_TRIGGER_AGENT_ENABLED               (default: false)
    WORKFLOW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES  (default: 1440)
    AI_WORKFLOW_ENABLED                          (default: true。WorkflowConfigと共有する環境変数)
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .workflow_config import WorkflowConfig


@dataclass
class WorkflowTriggerAgentConfig:
    enabled: bool
    min_interval_minutes: int
    reports_dir: Path
    workflow_enabled: bool
    project_root: Path

    @classmethod
    def from_env(cls, project_root: Path) -> "WorkflowTriggerAgentConfig":
        """
        環境変数から WorkflowTriggerAgentConfig を構築する。

        Args:
            project_root: 03_game_content_ai のプロジェクトルート（outputs/ が置かれているディレクトリ）
        """
        enabled = os.environ.get("WORKFLOW_TRIGGER_AGENT_ENABLED", "false").lower() == "true"
        min_interval_minutes = int(
            os.environ.get("WORKFLOW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES", "1440")
        )
        workflow_enabled = WorkflowConfig.from_env(base_dir=project_root).is_ready()

        return cls(
            enabled=enabled,
            min_interval_minutes=min_interval_minutes,
            reports_dir=project_root / "outputs" / "workflow_reports",
            workflow_enabled=workflow_enabled,
            project_root=project_root,
        )

    def is_ready(self) -> bool:
        """
        WorkflowTriggerAgentが実行可能な状態か返す（二重ゲートの2段目 + Workflow自体の有効性）。

        reports_dir が現時点でディスク上に存在するかどうかは判定に含めない。
        初回実行（レポート未生成）の場合でも is_ready()=True とし、
        「過去実行なし＝初回実行と判断」という decide() 側の判断に委ねる。
        """
        return self.enabled and self.workflow_enabled
