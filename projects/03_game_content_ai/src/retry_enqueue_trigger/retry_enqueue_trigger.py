"""
Retry Enqueue Trigger（v4.6.0）

RetryEnqueueTrigger:     WorkflowMonitorManagerが判定したFAILED/TIMEOUTを検知し、
                         まだRetry Queueに存在しないものだけをenqueueするAdapter。
NullRetryEnqueueTrigger: RetryEnqueueTriggerのダミー実装（Null Object）。

設計方針:
    - RetryEnqueueTriggerはWorkflowMonitorManager / RetryQueueManagerへの参照を
      Constructor Injectionで保持し、監視・enqueueへの薄い委譲のみを行う
      （docs/design/retry_enqueue_trigger_foundation.md 4章）。
    - Feature Gate・Configクラス・from_config()/from_env()は持たない。
      有効/無効は呼び出し元がRetryEnqueueTrigger（実体）とNullRetryEnqueueTrigger
      のどちらを構築するかで決まる（RetrySchedulerSource、v3.3.0と同じNull Object
      Pattern。同設計書2章）。
    - retry_engineは経由せず、workflow_monitor / retry_queueに直接依存する
      （同設計書2章 Design Policy #2）。
    - RetryQueueManager.exists()による「Queue内に既に存在するか」の確認のみを
      重複防止として行う。一度Queueから除去された後もMonitor上でFAILED/TIMEOUTの
      まま観測され続けるケースの再enqueue防止は本Releaseの対象外（Known Issue、
      同設計書11章）。
    - workflow_monitor / retry_queue / retry_engineはいずれも本Releaseでも無改修。
"""
from __future__ import annotations

from dataclasses import dataclass

from retry_queue import RetryQueueManager, RetryQueueOutcome
from workflow_monitor import WorkflowMonitorManager, WorkflowMonitorStatus

_RETRY_TARGET_STATUSES = frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT})


@dataclass(frozen=True)
class RetryEnqueueTriggerResult:
    """enqueue_pending_failures() 1回分の集計結果。"""

    scanned: int
    enqueued: int
    skipped_existing: int
    skipped_status: int
    failed: int


class RetryEnqueueTrigger:
    """
    WorkflowMonitorManagerが判定したFAILED/TIMEOUTのWorkflowを検知し、
    まだRetry Queueに存在しないものだけをenqueueするAdapter（実装クラス）。

    WorkflowMonitorManager / RetryQueueManagerへの参照をConstructor Injectionで
    保持し、検知・重複確認・enqueueへの薄い委譲のみを行う。
    """

    def __init__(self, monitor: WorkflowMonitorManager, queue: RetryQueueManager):
        self._monitor = monitor
        self._queue = queue

    def enqueue_pending_failures(self, limit: int | None = None) -> RetryEnqueueTriggerResult:
        """
        WorkflowMonitorManager.list_status(limit) を走査し、monitor_statusが
        FAILED/TIMEOUTのレコードのうち、まだQueueに存在しないものだけを
        RetryQueueManager.enqueue()する。
        """
        records = self._monitor.list_status(limit=limit)
        scanned = len(records)
        enqueued = 0
        skipped_existing = 0
        skipped_status = 0
        failed = 0

        for record in records:
            if record.monitor_status not in _RETRY_TARGET_STATUSES:
                skipped_status += 1
                continue
            if self._queue.exists(record.run_id):
                skipped_existing += 1
                continue
            result = self._queue.enqueue(run_id=record.run_id, workflow_name=record.workflow_name)
            if result.outcome == RetryQueueOutcome.ENQUEUED:
                enqueued += 1
            else:
                failed += 1

        return RetryEnqueueTriggerResult(
            scanned=scanned,
            enqueued=enqueued,
            skipped_existing=skipped_existing,
            skipped_status=skipped_status,
            failed=failed,
        )


class NullRetryEnqueueTrigger:
    """
    RetryEnqueueTrigger のダミー実装（Null Object）。

    workflow_monitor / retry_queue への参照を一切保持せず、常に
    「検知0件・enqueue 0件」の結果を返す。
    """

    def enqueue_pending_failures(self, limit: int | None = None) -> RetryEnqueueTriggerResult:
        return RetryEnqueueTriggerResult(
            scanned=0, enqueued=0, skipped_existing=0, skipped_status=0, failed=0,
        )
