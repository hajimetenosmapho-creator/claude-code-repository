"""
Execution History Manager（v2.8.0）

ExecutionHistoryManager:     Workflow実行履歴の記録責務を集約するクラス
NullExecutionHistoryManager: EXECUTION_HISTORY_ENABLED=false（無効）の場合のダミー実装

設計方針:
    - 「実行の観測・記録」のみを担当する。Workflow Engineの実行判断・分岐・再試行判断には
      一切関与しない（docs/design/execution_history_foundation.md 2章 原則1・2）。
    - NullExecutionHistoryManager の全メソッドは受け取った引数を一切参照せず無視する。
      呼び出し側（WorkflowEngineExecutor）はstart_run()の戻り値（Null時はNone）を
      そのままstart_step等へ渡すだけでよく、if分岐を書く必要がない（同設計書6章）。
"""
from __future__ import annotations

from datetime import datetime

from .execution_history_event import (
    EVENT_STEP_FINISHED,
    EVENT_STEP_STARTED,
    EVENT_WORKFLOW_FINISHED,
    EVENT_WORKFLOW_STARTED,
    ExecutionHistoryEvent,
)
from .execution_history_config import ExecutionHistoryConfig
from .execution_history_store import ExecutionHistoryStore
from .json_execution_history_store import JsonExecutionHistoryStore
from .step_execution_record import StepExecutionRecord, StepExecutionStatus
from .workflow_execution_record import WorkflowExecutionRecord, WorkflowExecutionStatus


class ExecutionHistoryManager:
    """Workflow実行履歴の記録責務を集約するクラス。"""

    def __init__(self, store: ExecutionHistoryStore):
        self._store = store

    @classmethod
    def from_config(
        cls, config: ExecutionHistoryConfig
    ) -> "ExecutionHistoryManager | NullExecutionHistoryManager":
        """ExecutionHistoryConfigから ExecutionHistoryManager を構築する。

        ゲート（EXECUTION_HISTORY_ENABLED）が閉じている場合は NullExecutionHistoryManager を返す。
        """
        if not config.is_ready():
            return NullExecutionHistoryManager()
        return cls(store=JsonExecutionHistoryStore(config.history_dir))

    def start_run(
        self, run_id: str, workflow_name: str, source: str, job_id: str
    ) -> WorkflowExecutionRecord:
        """RUNNING状態のrecordを作成し、即座に保存してから返す。"""
        now = datetime.now()
        record = WorkflowExecutionRecord(
            run_id=run_id,
            workflow_name=workflow_name,
            source=source,
            job_id=job_id,
            status=WorkflowExecutionStatus.RUNNING,
            started_at=now,
        )
        record.events.append(
            ExecutionHistoryEvent(
                event_type=EVENT_WORKFLOW_STARTED,
                occurred_at=now,
                message=f"workflow '{workflow_name}' started (run_id={run_id})",
            )
        )
        self._store.save(record)
        return record

    def start_step(self, record: WorkflowExecutionRecord, step: str) -> None:
        """StepExecutionRecord(status=RUNNING)をrecord.stepsへ追加し、再保存する。"""
        now = datetime.now()
        record.steps.append(
            StepExecutionRecord(step=step, status=StepExecutionStatus.RUNNING, started_at=now)
        )
        record.events.append(
            ExecutionHistoryEvent(
                event_type=EVENT_STEP_STARTED, occurred_at=now, message=f"step '{step}' started"
            )
        )
        self._store.save(record)

    def finish_step(
        self,
        record: WorkflowExecutionRecord,
        step: str,
        status: StepExecutionStatus,
        error_message: str | None = None,
        skipped_reason: str | None = None,
    ) -> None:
        """直近のstart_step対象のStepExecutionRecordを更新するか、なければ新規に確定させて再保存する。"""
        now = datetime.now()
        pending = self._find_pending_step(record, step)
        if pending is not None:
            pending.status = status
            pending.finished_at = now
            pending.error_message = error_message
            pending.skipped_reason = skipped_reason
        else:
            record.steps.append(
                StepExecutionRecord(
                    step=step,
                    status=status,
                    started_at=now,
                    finished_at=now,
                    error_message=error_message,
                    skipped_reason=skipped_reason,
                )
            )
        record.events.append(
            ExecutionHistoryEvent(
                event_type=EVENT_STEP_FINISHED,
                occurred_at=now,
                message=f"step '{step}' finished with status={status.value}",
            )
        )
        self._store.save(record)

    def finish_run(
        self,
        record: WorkflowExecutionRecord,
        status: WorkflowExecutionStatus,
        error_message: str | None = None,
    ) -> None:
        """record.status/finished_atを確定し、再保存する。"""
        now = datetime.now()
        record.status = status
        record.finished_at = now
        record.error_message = error_message
        record.events.append(
            ExecutionHistoryEvent(
                event_type=EVENT_WORKFLOW_FINISHED,
                occurred_at=now,
                message=f"workflow '{record.workflow_name}' finished with status={status.value}",
            )
        )
        self._store.save(record)

    @staticmethod
    def _find_pending_step(record: WorkflowExecutionRecord, step: str) -> StepExecutionRecord | None:
        for step_record in reversed(record.steps):
            if step_record.step == step and step_record.status == StepExecutionStatus.RUNNING:
                return step_record
        return None


class NullExecutionHistoryManager:
    """EXECUTION_HISTORY_ENABLED=false のときに使用するダミー実装。すべて no-op。"""

    def start_run(self, *args, **kwargs) -> None:
        return None

    def start_step(self, *args, **kwargs) -> None:
        return None

    def finish_step(self, *args, **kwargs) -> None:
        return None

    def finish_run(self, *args, **kwargs) -> None:
        return None
