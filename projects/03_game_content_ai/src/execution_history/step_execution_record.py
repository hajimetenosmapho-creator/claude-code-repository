"""
Step Execution Record定義（v2.8.0、Release 6.31で`action_taken`・`skip_category`を追加）

StepExecutionStatus:   Stepの実行状態を表すEnum
StepExecutionRecord:   1Stepの実行履歴を保持するデータクラス

設計方針:
    - step は WorkflowEngineStep（src/workflow_engine/）を直接受け取らず、str（.value）
      のみを受け取る。execution_historyがworkflow_engineの型を一切importしないための
      一方向依存の徹底（docs/design/execution_history_foundation.md 4章・6章）。
    - WorkflowEngineStepResult（executed/success/skipped_reason）からの変換規則は
      WorkflowEngineExecutor側が担う（同設計書6章の対応表）。

Release 6.31での変更（docs/design/retry_lineage_eligibility_durable_attempt_state.md
11.7.2章）:
    - `action_taken: bool | None = None`・`skip_category: StepSkipCategory | None = None`
      を追加した。旧レコード（本フィールド導入前に保存されたJSON）読込時はいずれも
      `None`となる（後方互換）。
    - `from_dict()`は、`action_taken`がbool型でない場合（文字列・0/1・list等）・
      `skip_category`が`StepSkipCategory`の既知値でない場合、いずれも`None`へ
      正規化するfail-closed契約を持つ（`retry_lineage.classify_execution_history_step()`
      がこれを`UNKNOWN`として扱う、同設計書11.7.2章）。`isinstance(x, bool)`により、
      Pythonの`bool`<`int`継承関係の落とし穴（`0`/`1`がintとして混入すること）を
      明示的に排除する。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .step_skip_category import StepSkipCategory


class StepExecutionStatus(Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"
    NOT_REACHED = "not_reached"


@dataclass
class StepExecutionRecord:
    step: str
    status: StepExecutionStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    skipped_reason: str | None = None
    action_taken: bool | None = None
    skip_category: StepSkipCategory | None = None

    def to_dict(self) -> dict:
        return {
            "step": self.step,
            "status": self.status.value,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "error_message": self.error_message,
            "skipped_reason": self.skipped_reason,
            "action_taken": self.action_taken,
            "skip_category": self.skip_category.value if self.skip_category else None,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "StepExecutionRecord":
        raw_action_taken = data.get("action_taken")
        raw_skip_category = data.get("skip_category")
        known_skip_categories = {c.value for c in StepSkipCategory}
        return cls(
            step=data["step"],
            status=StepExecutionStatus(data["status"]),
            started_at=datetime.fromisoformat(data["started_at"]) if data.get("started_at") else None,
            finished_at=datetime.fromisoformat(data["finished_at"]) if data.get("finished_at") else None,
            error_message=data.get("error_message"),
            skipped_reason=data.get("skipped_reason"),
            # bool型でなければNoneへ正規化する（isinstance(x, bool)で0/1混入を排除、fail-closed）。
            action_taken=raw_action_taken if isinstance(raw_action_taken, bool) else None,
            skip_category=(
                StepSkipCategory(raw_skip_category)
                if raw_skip_category in known_skip_categories
                else None
            ),
        )
