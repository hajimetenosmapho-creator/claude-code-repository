"""
Workflow Engine Executor（v2.7.0、v2.8.0でExecution History連携を追加）

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
    - [v2.8.0] history_manager（省略時は NullExecutionHistoryManager）へ、既存の
      分岐結果をそのまま横流しして記録するのみ。実行判断・分岐・打ち切り基準には
      一切関与しない（docs/design/execution_history_foundation.md 2章・7章）。
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
from .workflow_engine_result import (
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

        処理順序:
            1. 前段までに打ち切りが発生していれば、以降のステップは
               「未到達」（skipped_reason=REASON_NOT_REACHED, success=False）として記録する
            2. ステップに対応する AgentExecutor が未構築（Gate閉鎖）の場合、
               「スキップ」（success=True）として記録し、後続ステップの実行を継続する
            3. AgentExecutor が存在する場合、既存の AgentExecutor.execute() を
               無改修のまま呼び出す。AgentResult.success=False の場合のみ、
               以降のステップを打ち切る
        """
        started_at = datetime.now()
        context.started_at = started_at

        history_record = self._history_manager.start_run(
            run_id=context.run_id,
            workflow_name=WORKFLOW_NAME,
            source=context.event.source,
            job_id=context.event.job_id,
        )

        step_results: list[WorkflowEngineStepResult] = []
        stopped_early = False

        for step in self._definition.steps:
            if stopped_early:
                step_results.append(
                    WorkflowEngineStepResult(
                        step=step,
                        executed=False,
                        agent_result=None,
                        success=False,
                        skipped_reason=REASON_NOT_REACHED,
                    )
                )
                self._history_manager.finish_step(
                    history_record,
                    step.value,
                    StepExecutionStatus.NOT_REACHED,
                    skipped_reason=REASON_NOT_REACHED,
                )
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
                self._history_manager.finish_step(
                    history_record, step.value, StepExecutionStatus.SKIPPED, skipped_reason=reason
                )
                continue

            self._history_manager.start_step(history_record, step.value)

            agent_context = AgentContext(
                task=AgentTask(
                    task_id=f"workflow_engine_{step.value}",
                    params=dict(context.event.metadata),
                ),
                dry_run=context.dry_run,
                run_id=context.run_id,
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
                self._history_manager.finish_step(history_record, step.value, StepExecutionStatus.SUCCESS)
            else:
                self._history_manager.finish_step(
                    history_record,
                    step.value,
                    StepExecutionStatus.FAILED,
                    error_message=agent_result.error_message,
                )
                stopped_early = True

        context.step_results = step_results
        finished_at = datetime.now()
        context.finished_at = finished_at

        overall_success = all(r.success for r in step_results)

        self._history_manager.finish_run(
            history_record,
            WorkflowExecutionStatus.SUCCESS if overall_success else WorkflowExecutionStatus.FAILED,
        )

        return WorkflowEngineResult(
            steps=step_results,
            overall_success=overall_success,
            stopped_early=stopped_early,
            started_at=started_at,
            finished_at=finished_at,
            warnings=list(context.warnings),
        )
