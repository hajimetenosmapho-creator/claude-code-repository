"""
Agent実行パイプライン（v2.0.0）

AgentExecutor: BaseAgent.decide() / act() を決まった順序で呼び出す Execution Pipeline

設計方針:
    - dry_run 判定・started_at / finished_at の計測は AgentExecutor 側の責務。
      BaseAgent 実装（decide() / act()）はこれらを気にする必要がない。
    - decide() は副作用を持たない判断専用メソッドとして扱う
      （AgentExecutor は decide() の戻り値を context.decisions に記録するのみ）。
    - act() は「should_act=True かつ dry_run=False」の場合のみ呼び出す。
      それ以外（should_act=False、または dry_run=True）は act() を呼ばず、
      AgentExecutor 自身が AgentResult を組み立てる。
    - act() が返す AgentResult の workflow_result はそのまま参照を引き継ぐ。
      WorkflowResult の中身を AgentResult へコピーすることはしない。
    - run_id / agent_name / started_at / finished_at は、経路（should_act=False /
      dry_run / act() 実行 / 例外）によらず必ず context の値と一致するよう、
      _finalize() で最後に上書きして保証する。
"""
from __future__ import annotations

from datetime import datetime

from .agent_context import AgentContext
from .agent_decision import AgentDecision
from .agent_result import AgentResult
from .base_agent import BaseAgent


class AgentExecutor:
    """BaseAgent.decide() / act() を実行する Execution Pipeline。"""

    def __init__(self, agent: BaseAgent):
        self._agent = agent

    def execute(self, context: AgentContext) -> AgentResult:
        """
        Agentの判断・実行を一連の流れで行い、AgentResultを返す。

        処理順序:
            1. before_execute（started_at計測、context.agent_name設定）
            2. BaseAgent.decide() を呼び、context.decisions に記録する
            3. should_act=False、または context.dry_run=True の場合は
               act() を呼ばずに AgentResult を組み立てる
            4. should_act=True かつ dry_run=False の場合のみ BaseAgent.act() を呼ぶ
            5. 例外発生時は context.errors に記録し、失敗した AgentResult を組み立てる
            6. after_execute（finished_at計測）
            7. finalize（run_id / agent_name / started_at / finished_at を保証する）
        """
        self._before_execute(context)

        decision: AgentDecision | None = None
        try:
            decision = self._agent.decide(context)
            context.decisions.append(decision)

            if not decision.should_act:
                result = self._build_result(
                    context=context,
                    decision=decision,
                    action_taken=False,
                    success=True,
                    workflow_result=None,
                    error_message=None,
                )
            elif context.dry_run:
                context.warnings.append(
                    f"dry_run=True のため act() をスキップしました（reason: {decision.reason}）"
                )
                result = self._build_result(
                    context=context,
                    decision=decision,
                    action_taken=False,
                    success=True,
                    workflow_result=None,
                    error_message=None,
                )
            else:
                result = self._agent.act(decision, context)
        except Exception as e:
            context.errors.append(str(e))
            if decision is None:
                decision = AgentDecision(
                    should_act=False,
                    reason=f"例外発生のため判断を確定できませんでした: {e}",
                )
            result = self._build_result(
                context=context,
                decision=decision,
                action_taken=False,
                success=False,
                workflow_result=None,
                error_message=str(e),
            )

        self._after_execute(context)
        return self._finalize(result, context)

    def _before_execute(self, context: AgentContext) -> None:
        """実行前の準備を行う（開始時刻の計測、agent_name の設定）。"""
        context.started_at = datetime.now()
        context.agent_name = self._agent.name()

    def _after_execute(self, context: AgentContext) -> None:
        """実行後の後処理を行う（終了時刻の計測）。"""
        context.finished_at = datetime.now()

    def _build_result(
        self,
        context: AgentContext,
        decision: AgentDecision,
        action_taken: bool,
        success: bool,
        workflow_result,
        error_message: str | None,
    ) -> AgentResult:
        """AgentExecutor自身が AgentResult を組み立てる（act() を呼ばない経路用）。"""
        return AgentResult(
            run_id=context.run_id,
            agent_name=context.agent_name,
            task=context.task,
            decision=decision,
            action_taken=action_taken,
            success=success,
            workflow_result=workflow_result,
            error_message=error_message,
            started_at=context.started_at,
            finished_at=context.finished_at,
            warnings=list(context.warnings),
        )

    def _finalize(self, result: AgentResult, context: AgentContext) -> AgentResult:
        """
        AgentResult の run_id / agent_name / started_at / finished_at が
        context の値と一致することを保証する。

        BaseAgent.act() が独自に AgentResult を構築するケースでも、
        経路によらず Execution Metadata の整合性を担保するため、
        ここで context の値を最終的に上書きする。
        """
        result.run_id = context.run_id
        result.agent_name = context.agent_name
        result.started_at = context.started_at
        result.finished_at = context.finished_at
        return result
