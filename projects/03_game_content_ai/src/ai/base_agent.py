"""
Agent基底クラス（v2.0.0）

BaseAgent: 全Agent実装が継承する抽象基底クラス（ABC）

設計方針:
    - Agent は Workflow を置き換えるものではない。
      Workflow（WorkflowRunner）は既存の「6ステップを実行する」仕組みであり、
      Agent はその Workflow を「今、実行すべきかどうか」を判断する上位概念である。
    - BaseAgent の中心責務は「実行」ではなく「判断」。
      実際の Workflow 起動・副作用の実行は AgentExecutor が担う
      （BaseAgent はここでは import しない。責務を混同しないため）。
    - decide() は判断専用メソッドであり、副作用を持たない
      （ファイル書き込み・Workflow起動・外部API呼び出しなどを行わない）。
    - act() は decision.should_act=True かつ context.dry_run=False の場合のみ、
      AgentExecutor から呼び出される想定。
      （dry_run=True の場合や should_act=False の場合、AgentExecutor は
      act() を呼び出さない）
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .agent_context import AgentContext
from .agent_decision import AgentDecision
from .agent_result import AgentResult


class BaseAgent(ABC):
    """全Agent実装が継承する抽象基底クラス。"""

    @abstractmethod
    def name(self) -> str:
        """このAgentの識別名を返す。"""
        ...

    @abstractmethod
    def decide(self, context: AgentContext) -> AgentDecision:
        """現在の状況を判断し、Action を実行すべきか判断する（副作用なし）。"""
        ...

    @abstractmethod
    def act(self, decision: AgentDecision, context: AgentContext) -> AgentResult:
        """decide() の判断結果に基づき Action を実行する。"""
        ...
