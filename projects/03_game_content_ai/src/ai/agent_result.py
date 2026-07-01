"""
Agent実行結果（v2.0.0）

AgentResult: エージェントの判断・実行結果を保持するデータクラス

フィールド:
    run_id:          実行を一意に識別するID
    agent_name:      実行したエージェント名
    task:            依頼された AgentTask
    decision:        BaseAgent.decide() の判断結果
    action_taken:    act() を実際に実行したか
    success:         Agent自身の判断・実行プロセスが例外なく完了したか
    workflow_result: act() が Workflow を起動した場合の参照（起動しなかった場合は None）
    error_message:   例外発生時のメッセージ
    started_at:      開始日時
    finished_at:     終了日時
    warnings:        警告（dry_run による Action 省略などを記録）

設計方針:
    - WorkflowResult のフィールドはコピーしない。workflow_result として参照のみ保持する
    - success は Agent 自身の責務（判断＋Action実行）が完了したかを表す。
      呼び出した Workflow が失敗したかどうかは workflow_result.overall_success を
      別途参照して判断する（両者の責務を混同しない）
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime

from .agent_decision import AgentDecision
from .agent_task import AgentTask
from .workflow_result import WorkflowResult


@dataclass
class AgentResult:
    run_id: str
    agent_name: str
    task: AgentTask
    decision: AgentDecision
    action_taken: bool
    success: bool
    workflow_result: WorkflowResult | None
    error_message: str | None
    started_at: datetime
    finished_at: datetime
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "agent_name": self.agent_name,
            "task_id": self.task.task_id,
            "decision": {
                "should_act": self.decision.should_act,
                "reason": self.decision.reason,
            },
            "action_taken": self.action_taken,
            "success": self.success,
            "workflow_result": (
                self.workflow_result.to_dict() if self.workflow_result else None
            ),
            "error_message": self.error_message,
            "started_at": self.started_at.isoformat(),
            "finished_at": self.finished_at.isoformat(),
            "warnings": list(self.warnings),
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)
