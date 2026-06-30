"""
ワークフロー設定（v1.20.0）

WorkflowConfig: ワークフローの設定値のみを保持するデータクラス

設計方針:
    - 設定値のみを保持する（実行時状態は WorkflowContext が担う）
    - article_id / dry_run は実行時パラメータなので含まない
    - Configuration First: is_ready() が False → NullWorkflowRunner を返す

環境変数:
    AI_WORKFLOW_ENABLED              (default: true)
    AI_WORKFLOW_CONTINUE_ON_ERROR    (default: false)
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from .workflow_step import WorkflowStep

ALL_WORKFLOW_STEPS: list[WorkflowStep] = [
    WorkflowStep.IMPROVEMENT,
    WorkflowStep.IMPROVEMENT_REVIEW,
    WorkflowStep.REWRITE,
    WorkflowStep.REWRITE_REVIEW,
    WorkflowStep.PUBLISH,
    WorkflowStep.PUBLISH_REVIEW,
]


@dataclass
class WorkflowConfig:
    enabled: bool
    steps: list[WorkflowStep]
    base_dir: Path
    continue_on_error: bool = False

    @classmethod
    def from_env(cls, base_dir: Path | None = None) -> "WorkflowConfig":
        """
        環境変数から WorkflowConfig を構築する。

        Args:
            base_dir: プロジェクトのルートディレクトリ（None の場合は現在のディレクトリ）
        """
        enabled = os.environ.get("AI_WORKFLOW_ENABLED", "true").lower() == "true"
        continue_on_error = (
            os.environ.get("AI_WORKFLOW_CONTINUE_ON_ERROR", "false").lower() == "true"
        )
        resolved_base = base_dir if base_dir is not None else Path(".")

        return cls(
            enabled=enabled,
            steps=list(ALL_WORKFLOW_STEPS),
            base_dir=resolved_base,
            continue_on_error=continue_on_error,
        )

    def is_ready(self) -> bool:
        """ワークフローが実行可能な状態か返す。"""
        return self.enabled and len(self.steps) > 0
