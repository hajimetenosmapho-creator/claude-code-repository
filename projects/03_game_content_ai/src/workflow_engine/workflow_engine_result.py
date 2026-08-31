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
from execution_history import StepSkipCategory

from .workflow_engine_step import WorkflowEngineStep

REASON_NOT_REACHED = "Not reached: an earlier step failed."
REASON_HISTORY_WRITE_FAILED = "Not executed: start_step() history persistence failed."
REASON_NOT_TARGETED = "Not targeted for this retry attempt (already confirmed done)."


@dataclass
class WorkflowEngineStepResult:
    step: WorkflowEngineStep
    executed: bool
    agent_result: AgentResult | None
    success: bool
    skipped_reason: str | None
    # Release 6.31（docs/design/retry_lineage_eligibility_durable_attempt_state.md
    # 11.3.2章）：executed=Trueなら常にNone。分類関数（retry_lineage.classify_step_outcome()）
    # 専用の構造化フィールド。skipped_reason（人間可読の自由文字列）とは独立。
    skip_category: StepSkipCategory | None = None

    def to_dict(self) -> dict:
        return {
            "step": self.step.value,
            "executed": self.executed,
            "agent_result": self.agent_result.to_dict() if self.agent_result else None,
            "success": self.success,
            "skipped_reason": self.skipped_reason,
            "skip_category": self.skip_category.value if self.skip_category else None,
        }


@dataclass
class WorkflowEngineResult:
    steps: list[WorkflowEngineStepResult]
    overall_success: bool
    stopped_early: bool
    started_at: datetime
    finished_at: datetime
    warnings: list[str] = field(default_factory=list)
    history_write_failed: bool = False
    # Release 6.31：このWorkflowEngineResultを生んだ実行のrun_id。呼び出し元
    # （RetryExecutor）が、次にmark_terminal(executed_run_id=...)へ渡すために必要
    # （docs/design/retry_lineage_eligibility_durable_attempt_state.md 21章）。
    # 既存の非retry呼び出し元にはZero-Diff（単に新しいフィールドが1つ増えるのみ、
    # 参照しなければ無視できる）。
    run_id: str = ""

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "overall_success": self.overall_success,
            "stopped_early": self.stopped_early,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "warnings": list(self.warnings),
            "steps": [s.to_dict() for s in self.steps],
            "history_write_failed": self.history_write_failed,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
