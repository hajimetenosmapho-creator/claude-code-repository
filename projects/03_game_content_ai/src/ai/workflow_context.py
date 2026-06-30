"""
ワークフロー実行コンテキスト（v1.20.0）

WorkflowContext: ワークフロー実行中の状態を保持するデータクラス

設計方針:
    - WorkflowConfig（設定値）とは分離し、実行時状態のみを保持する
    - WorkflowRunner が current_step / step_results / report_paths を更新する
    - WorkflowStepExecutor が warnings / errors に追記できる
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .workflow_step import WorkflowStep, WorkflowStepResult


@dataclass
class WorkflowContext:
    # 実行パラメータ（呼び出し元から渡される）
    article_id: str | None
    dry_run: bool

    # ランタイム状態（WorkflowRunner / WorkflowStepExecutor が更新する）
    current_step: WorkflowStep | None = None
    step_results: list[WorkflowStepResult] = field(default_factory=list)
    report_paths: list[Path] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
