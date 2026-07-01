"""
Agentタスク定義（v2.0.0）

AgentTask: エージェントに判断を依頼する作業単位を表すデータクラス

設計方針:
    - WorkflowStep のような固定 Enum にはしない
      （Workflow のステップは実行順序が確定した6ステップだが、
      Agent のタスク種別は将来の Agent 追加ごとに増減しうるため）
    - task_id は自由記述の識別子とし、解釈は各 BaseAgent 実装に委ねる
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class AgentTask:
    task_id: str
    params: dict = field(default_factory=dict)
