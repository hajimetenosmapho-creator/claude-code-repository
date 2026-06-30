"""
ワークフローステップ定義（v1.20.0）

WorkflowStep:       AIパイプラインの各ステップを定義する Enum
WorkflowStepResult: 各ステップの実行結果を保持するデータクラス
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from pathlib import Path


class WorkflowStep(Enum):
    IMPROVEMENT        = "improvement"
    IMPROVEMENT_REVIEW = "improvement_review"
    REWRITE            = "rewrite"
    REWRITE_REVIEW     = "rewrite_review"
    PUBLISH            = "publish"
    PUBLISH_REVIEW     = "publish_review"


@dataclass
class WorkflowStepResult:
    step: WorkflowStep
    success: bool
    processed_count: int
    report_path: Path | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime
