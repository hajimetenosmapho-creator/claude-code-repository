"""
Agent判断結果（v2.0.0）

AgentDecision: BaseAgent.decide() の戻り値を表すデータクラス

設計方針:
    - decide() は判断のみを行い、副作用（Workflow呼び出し等）を持たない
    - should_act が True の場合のみ、後続で BaseAgent.act() が呼び出される
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class AgentDecision:
    should_act: bool
    reason: str
