"""
Workflow Engine実行結果（v2.7.0）

WorkflowEngineStepResult: 各ステップの実行結果を保持するデータクラス
WorkflowEngineResult:     Workflow Engine全体の実行結果を保持するデータクラス

設計方針:
    - src/ai/workflow_result.py の WorkflowResult（v1.20.0、AI記事改善6ステップ用）とは
      別物。対象・フィールドの意味が異なるため混同しないこと
      （docs/design/workflow_engine_foundation.md 5章）。
    - WorkflowEngineResult.steps は、打ち切り（stopped_early）が発生した場合も含めて
      常に WorkflowEngineDefinition.steps と同じ件数になるようにする。
      Gate閉鎖によるスキップ（success=True）、前段の失敗による未到達
      （REASON_NOT_REACHED、success=False）のいずれも、executed=False の
      エントリとして必ず記録する（同設計書8.3節、修正推奨事項）。
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from ai import AgentResult

from .workflow_engine_step import WorkflowEngineStep

REASON_NOT_REACHED = "Not reached: an earlier step failed."


@dataclass
class WorkflowEngineStepResult:
    step: WorkflowEngineStep
    executed: bool
    agent_result: AgentResult | None
    success: bool
    skipped_reason: str | None

    def to_dict(self) -> dict:
        return {
            "step": self.step.value,
            "executed": self.executed,
            "agent_result": self.agent_result.to_dict() if self.agent_result else None,
            "success": self.success,
            "skipped_reason": self.skipped_reason,
        }


@dataclass
class WorkflowEngineResult:
    steps: list[WorkflowEngineStepResult]
    overall_success: bool
    stopped_early: bool
    started_at: datetime
    finished_at: datetime
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "overall_success": self.overall_success,
            "stopped_early": self.stopped_early,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "warnings": list(self.warnings),
            "steps": [s.to_dict() for s in self.steps],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
