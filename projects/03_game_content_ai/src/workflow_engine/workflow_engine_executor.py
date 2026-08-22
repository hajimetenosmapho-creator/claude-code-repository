"""
Workflow Engine Executor（v2.7.0、v2.8.0でExecution History連携を追加、
Release 6.30でCanonical Admission / run_idベースAPIへ移行）

WorkflowEngineExecutor: WorkflowEngineDefinitionに従い、既存Agentを順序どおりに実行するエンジン

設計方針:
    - 各ステップに対応する既存 AgentExecutor.execute(context) をそのまま呼び出す。
      各Agentの decide()（mtime間隔判断）・dry_run制御は一切迂回しない
      （docs/design/workflow_engine_foundation.md 8.1節）。強制的に act() させる
      経路は用意しない。
    - 打ち切り基準：「実行した結果として失敗した（AgentResult.success=False）」場合のみ
      後続ステップを打ち切る。Gate閉鎖によるスキップ・decide()による
      should_act=False判断は失敗として扱わず、後続ステップの実行を継続する
      （同設計書8.3節）。
    - WorkflowEngineResult.steps は、打ち切りが発生した場合も含めて常に
      definition.steps と同じ件数になる。未到達ステップは
      executed=False, success=False, skipped_reason=REASON_NOT_REACHED として
      記録する（同設計書8.3節、修正推奨事項）。

Release 6.30での変更（docs/design/production_canonical_run_outcome_contract_foundation.md
7・9〜19章。以下、章番号は同ドキュメント参照）:
    - Canonical History Invariant（7章）：dry-runではeffective_history_managerを
      NullExecutionHistoryManagerへ差し替える（zero-write）。canonical non-dry-runで
      Historyが無効な場合は CanonicalAdmissionFailure(reason="EXECUTION_HISTORY_DISABLED")
      をraiseする。この判定は try の内側で行い、finallyのrelease_run()が全経路で
      必ず実行されることを保証する。
    - start_run() のack失敗は CanonicalAdmissionFailure(reason="START_RUN_ACK_FAILED")。
    - start_step()==False：Managerは自動終端しない。Agent未実行。残stepはin-memoryの
      みNOT_REACHED。ループ終了後finish_run(FAILED)を1回だけ明示的に呼ぶ
      （owe_closing_finish_run制御フロー専用フラグ。実際のdurable状態は推測しない）。
    - finish_step()==False：Managerが既にterminal recoveryを1回試行済み。以降History
      APIを一切呼ばない（finish_runも含む）。残stepはin-memoryのみNOT_REACHED。
    - history_write_failed（latch）をWorkflowEngineResultへ記録する。
    - release_run() は try/finally の finally で必ず1回呼ばれる。
"""
from __future__ import annotations

from datetime import datetime

from ai import AgentContext, AgentExecutor, AgentTask
from execution_history import (
    ExecutionHistoryManager,
    NullExecutionHistoryManager,
    StepExecutionStatus,
    WorkflowExecutionStatus,
)

from .workflow_engine_context import WorkflowEngineContext
from .workflow_engine_definition import WorkflowEngineDefinition
from .workflow_engine_exceptions import CanonicalAdmissionFailure
from .workflow_engine_result import (
    REASON_HISTORY_WRITE_FAILED,
    REASON_NOT_REACHED,
    WorkflowEngineResult,
    WorkflowEngineStepResult,
)
from .workflow_engine_step import WorkflowEngineStep

WORKFLOW_NAME = "workflow_engine"


class WorkflowEngineExecutor:
    """WorkflowEngineDefinitionに従い、ステップに対応するAgentExecutorを順に実行する。"""

    def __init__(
        self,
        definition: WorkflowEngineDefinition,
        step_executors: dict[WorkflowEngineStep, AgentExecutor | None],
        step_skip_reasons: dict[WorkflowEngineStep, str] | None = None,
        history_manager: ExecutionHistoryManager | NullExecutionHistoryManager | None = None,
    ):
        self._definition = definition
        self._step_executors = step_executors
        self._step_skip_reasons = step_skip_reasons or {}
        self._history_manager = history_manager or NullExecutionHistoryManager()

    def run(self, context: WorkflowEngineContext) -> WorkflowEngineResult:
        """
        definition.steps を順に処理し、WorkflowEngineResult を返す。

        Canonical History Invariant・Canonical Admission・recovery制御フローについては
        本ファイル冒頭のRelease 6.30変更点、および設計書19章の確定pseudocodeを参照。
        """
        started_at = datetime.now()
        context.started_at = started_at
        run_id = context.run_id

        effective_history_manager = (
            NullExecutionHistoryManager() if context.dry_run else self._history_manager
        )

        try:
            # Canonical History Invariant判定は try の内側に置く。これにより
            # EXECUTION_HISTORY_DISABLED を含む全ての CanonicalAdmissionFailure 経路で
            # finally の release_run() が必ず実行される。
            if not context.dry_run and isinstance(
                effective_history_manager, NullExecutionHistoryManager
            ):
                raise CanonicalAdmissionFailure(run_id, reason="EXECUTION_HISTORY_DISABLED")

            start_result = effective_history_manager.start_run(
                run_id=run_id,
                workflow_name=WORKFLOW_NAME,
                source=context.event.source,
                job_id=context.event.job_id,
            )
            if not start_result.acknowledged:
                raise CanonicalAdmissionFailure(run_id, reason="START_RUN_ACK_FAILED")

            step_results: list[WorkflowEngineStepResult] = []
            stopped_early = False
            history_write_failed = False
            history_closed = False          # True以降は当該run内で追加のHistory API呼び出しをしない
            owe_closing_finish_run = False  # control-flow専用フラグ。start_step ack失敗経路でのみ
                                             # True。実際のdurable terminal状態を推測・claimしない。

            for step in self._definition.steps:
                if history_closed or stopped_early:
                    step_results.append(
                        WorkflowEngineStepResult(
                            step=step,
                            executed=False,
                            agent_result=None,
                            success=False,
                            skipped_reason=REASON_NOT_REACHED,
                        )
                    )
                    if history_closed:
                        continue  # in-memoryのみ。History API呼び出しなし
                    ok = effective_history_manager.finish_step(
                        run_id,
                        step.value,
                        StepExecutionStatus.NOT_REACHED,
                        skipped_reason=REASON_NOT_REACHED,
                    )
                    if not ok:
                        history_write_failed = True
                        history_closed = True
                    continue

                executor = self._step_executors.get(step)

                if executor is None:
                    reason = self._step_skip_reasons.get(
                        step, f"{step.value} step is not configured (gate closed)."
                    )
                    step_results.append(
                        WorkflowEngineStepResult(
                            step=step,
                            executed=False,
                            agent_result=None,
                            success=True,
                            skipped_reason=reason,
                        )
                    )
                    ok = effective_history_manager.finish_step(
                        run_id, step.value, StepExecutionStatus.SKIPPED, skipped_reason=reason
                    )
                    if not ok:
                        history_write_failed = True
                        history_closed = True
                    continue

                ok = effective_history_manager.start_step(run_id, step.value)
                if not ok:
                    history_write_failed = True
                    step_results.append(
                        WorkflowEngineStepResult(
                            step=step,
                            executed=False,
                            agent_result=None,
                            success=False,
                            skipped_reason=REASON_HISTORY_WRITE_FAILED,
                        )
                    )
                    history_closed = True
                    stopped_early = True
                    owe_closing_finish_run = True  # start_step失敗：Managerは自動終端しない
                    continue

                agent_context = AgentContext(
                    task=AgentTask(
                        task_id=f"workflow_engine_{step.value}",
                        params=dict(context.event.metadata),
                    ),
                    dry_run=context.dry_run,
                    run_id=run_id,
                    agent_name="",
                )
                agent_result = executor.execute(agent_context)
                context.warnings.extend(agent_context.warnings)

                step_results.append(
                    WorkflowEngineStepResult(
                        step=step,
                        executed=True,
                        agent_result=agent_result,
                        success=agent_result.success,
                        skipped_reason=None,
                    )
                )

                if agent_result.success:
                    ok = effective_history_manager.finish_step(
                        run_id, step.value, StepExecutionStatus.SUCCESS
                    )
                else:
                    ok = effective_history_manager.finish_step(
                        run_id,
                        step.value,
                        StepExecutionStatus.FAILED,
                        error_message=agent_result.error_message,
                    )
                    stopped_early = True
                if not ok:
                    history_write_failed = True
                    history_closed = True

            context.step_results = step_results
            finished_at = datetime.now()
            context.finished_at = finished_at

            overall_success = all(r.success for r in step_results)

            if not history_closed:
                ok = effective_history_manager.finish_run(
                    run_id,
                    WorkflowExecutionStatus.SUCCESS
                    if overall_success
                    else WorkflowExecutionStatus.FAILED,
                )
                if not ok:
                    history_write_failed = True
            elif owe_closing_finish_run:
                # start_step失敗経路のみ：Executorが負っていた最後の1回の終端呼び出しを行う
                effective_history_manager.finish_run(run_id, WorkflowExecutionStatus.FAILED)
            # else: finish_step失敗経路。Managerが既にrecovery試行済みのため
            # finish_run は呼ばない（recovery成否は問わない）。

            return WorkflowEngineResult(
                steps=step_results,
                overall_success=overall_success,
                stopped_early=stopped_early,
                started_at=started_at,
                finished_at=finished_at,
                warnings=list(context.warnings),
                history_write_failed=history_write_failed,
            )
        finally:
            effective_history_manager.release_run(run_id)
