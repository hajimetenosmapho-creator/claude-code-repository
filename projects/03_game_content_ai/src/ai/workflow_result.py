"""
ワークフロー実行結果（v1.20.0）

WorkflowResult: ワークフロー全体の実行結果を保持するデータクラス

フィールド:
    steps:           各ステップの実行結果
    overall_success: 全実行ステップが成功したか
    total_processed: 全ステップの処理件数合計
    report_path:     ワークフローレポートの保存先パス
    started_at:      開始日時
    finished_at:     終了日時
    warnings:        ワークフロー全体の警告（将来の拡張ポイント）
    skipped_steps:   スキップされたステップ（将来の拡張ポイント）
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .workflow_step import WorkflowStep, WorkflowStepResult


@dataclass
class WorkflowResult:
    steps: list[WorkflowStepResult]
    overall_success: bool
    total_processed: int
    report_path: Path | None
    started_at: datetime
    finished_at: datetime
    warnings: list[str] = field(default_factory=list)
    skipped_steps: list[WorkflowStep] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "overall_success": self.overall_success,
            "total_processed": self.total_processed,
            "report_path": str(self.report_path) if self.report_path else None,
            "started_at":  self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "warnings": list(self.warnings),
            "skipped_steps": [s.value for s in self.skipped_steps],
            "steps": [
                {
                    "step":            r.step.value,
                    "success":         r.success,
                    "processed_count": r.processed_count,
                    "report_path":     str(r.report_path) if r.report_path else None,
                    "error_message":   r.error_message,
                    "started_at":      r.started_at.isoformat(),
                    "finished_at":     r.finished_at.isoformat(),
                }
                for r in self.steps
            ],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
