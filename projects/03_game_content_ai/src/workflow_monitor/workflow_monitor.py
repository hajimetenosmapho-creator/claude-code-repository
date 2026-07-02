"""
Workflow Monitor（v2.9.0）

WorkflowMonitor: ExecutionHistoryStoreを読み取り、WorkflowMonitorStatusを判定するロジック本体

設計方針:
    - Execution Historyを唯一の情報源（Single Source of Truth）とする。Workflow Engineの
      内部状態・メモリ上の状態・一時キャッシュには一切依存しない（Charter 5.1節）。
    - stateless：判定結果を独自に保持・永続化しない。呼び出されるたびに
      ExecutionHistoryStoreから最新のレコードを読み直し、その場で判定する。
    - 判定はWorkflow単位（run_id）のみ。Step単位の独自判定ロジックは持たず、
      StepExecutionRecordは生データのままコピーして保持する
      （docs/design/workflow_monitor_foundation.md 2章 Open Question #1）。
    - Timeout判定は datetime.now() を直接使用する。SchedulerEngine（v2.6.0）のような
      ClockProvider抽象化は導入しない。TIMEOUT判定のテストは started_at を過去日時に
      設定することで再現できるため、時刻注入の仕組みを追加する必要性は低いと判断した
      （Architecture Review指摘事項#2）。
"""
from __future__ import annotations

from datetime import datetime

from execution_history import ExecutionHistoryStore, WorkflowExecutionRecord, WorkflowExecutionStatus

from .workflow_monitor_config import WorkflowMonitorConfig
from .workflow_monitor_record import WorkflowMonitorRecord
from .workflow_monitor_status import WorkflowMonitorStatus


class WorkflowMonitor:
    """ExecutionHistoryStoreを読み取り、WorkflowMonitorStatusを判定するロジック本体。"""

    def __init__(self, store: ExecutionHistoryStore, config: WorkflowMonitorConfig):
        self._store = store
        self._config = config

    def get_status(self, run_id: str) -> WorkflowMonitorRecord | None:
        """指定run_idのWorkflowMonitorRecordを返す。存在しない場合はNoneを返す。"""
        record = self._store.get(run_id)
        if record is None:
            return None
        return self._to_monitor_record(record)

    def list_status(self, limit: int | None = None) -> list[WorkflowMonitorRecord]:
        """全WorkflowExecutionRecordを判定し、started_atの新しい順で返す。"""
        records = self._store.list_all()
        monitor_records = [self._to_monitor_record(r) for r in records]
        if limit is not None:
            return monitor_records[:limit]
        return monitor_records

    def _to_monitor_record(self, record: WorkflowExecutionRecord) -> WorkflowMonitorRecord:
        monitor_status, reason = self._judge(record)
        now = datetime.now()
        elapsed = ((record.finished_at or now) - record.started_at).total_seconds()
        return WorkflowMonitorRecord(
            run_id=record.run_id,
            workflow_name=record.workflow_name,
            monitor_status=monitor_status,
            source_status=record.status.value,
            source=record.source,
            job_id=record.job_id,
            started_at=record.started_at,
            finished_at=record.finished_at,
            elapsed_seconds=elapsed,
            reason=reason,
            steps=list(record.steps),
        )

    def _judge(self, record: WorkflowExecutionRecord) -> tuple[WorkflowMonitorStatus, str | None]:
        """Charter 4章の判定方針を実装する。CANCELLED/WAITINGはいずれの分岐からも返らない。"""
        if record.status == WorkflowExecutionStatus.SUCCESS:
            return WorkflowMonitorStatus.SUCCESS, None
        if record.status == WorkflowExecutionStatus.FAILED:
            return WorkflowMonitorStatus.FAILED, record.error_message

        # record.status == WorkflowExecutionStatus.RUNNING
        elapsed = (datetime.now() - record.started_at).total_seconds()
        if elapsed >= self._config.timeout_seconds:
            reason = (
                f"started_at から {int(elapsed)}秒経過し、"
                f"閾値（{self._config.timeout_seconds}秒）を超過したため TIMEOUT と判定"
            )
            return WorkflowMonitorStatus.TIMEOUT, reason
        return WorkflowMonitorStatus.RUNNING, None
