"""
Retry Enqueue Trigger（v4.6.0、v4.8.0で拡張）

RetryEnqueueTrigger:     WorkflowMonitorManagerが判定したFAILED/TIMEOUTを検知し、
                         RetryEnqueueGuardの判定を経て、まだRetry Queueに
                         存在しないものだけをenqueueするAdapter。
NullRetryEnqueueTrigger: RetryEnqueueTriggerのダミー実装（Null Object）。

設計方針:
    - RetryEnqueueTriggerはWorkflowMonitorManager / RetryQueueManagerへの参照を
      Constructor Injectionで保持し、監視・enqueueへの薄い委譲のみを行う
      （docs/design/retry_enqueue_trigger_foundation.md 4章）。
    - Feature Gate・Configクラス・from_config()/from_env()は持たない。
      有効/無効は呼び出し元がRetryEnqueueTrigger（実体）とNullRetryEnqueueTrigger
      のどちらを構築するかで決まる（RetrySchedulerSource、v3.3.0と同じNull Object
      Pattern。同設計書2章）。
    - retry_engineは経由せず、workflow_monitor / retry_queue / retry_history に
      直接依存する（同設計書2章 Design Policy #2、docs/design/retry_enqueue_guard.md
      2章）。
    - RetryQueueManager.exists()による「Queue内に既に存在するか」の確認に加え、
      v4.8.0でRetryEnqueueGuardによる「再試行履歴が1回でもあればブロック」という
      判定を追加した。これにより、Queueから除去された後もMonitor上でFAILED/TIMEOUTの
      まま観測され続けるrun_idの無限再投入リスク（v4.6.0 Known Issue）を解消した
      （docs/design/retry_enqueue_guard.md 1章・11章）。
    - history省略時はNullRetryHistoryManager()にフォールバックし、Guardは常に
      ALLOWを返す（v4.6.0時点とまったく同じ挙動。同設計書2章 Design Policy #3）。
    - workflow_monitor / retry_queue / retry_history / retry_engineはいずれも
      本Releaseでも無改修。
"""
from __future__ import annotations

from dataclasses import dataclass

from retry_history import NullRetryHistoryManager, RetryHistoryManager
from retry_queue import RetryQueueManager, RetryQueueOutcome
from workflow_monitor import WorkflowMonitorManager, WorkflowMonitorStatus

from .retry_enqueue_guard import RetryEnqueueGuard, RetryEnqueueGuardOutcome

_RETRY_TARGET_STATUSES = frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT})


@dataclass(frozen=True)
class RetryEnqueueTriggerResult:
    """enqueue_pending_failures() 1回分の集計結果。"""

    scanned: int
    enqueued: int
    skipped_existing: int
    skipped_status: int
    failed: int
    skipped_history: int = 0


class RetryEnqueueTrigger:
    """
    WorkflowMonitorManagerが判定したFAILED/TIMEOUTのWorkflowを検知し、
    RetryEnqueueGuardの判定を経て、まだRetry Queueに存在しないものだけを
    enqueueするAdapter（実装クラス）。

    WorkflowMonitorManager / RetryQueueManager / RetryHistoryManager /
    RetryEnqueueGuardへの参照をConstructor Injectionで保持し、検知・Guard判定・
    重複確認・enqueueへの薄い委譲のみを行う。
    """

    def __init__(
        self,
        monitor: WorkflowMonitorManager,
        queue: RetryQueueManager,
        history: "RetryHistoryManager | NullRetryHistoryManager | None" = None,
        guard: RetryEnqueueGuard | None = None,
    ):
        self._monitor = monitor
        self._queue = queue
        self._history = history if history is not None else NullRetryHistoryManager()
        self._guard = guard if guard is not None else RetryEnqueueGuard()

    def enqueue_pending_failures(self, limit: int | None = None) -> RetryEnqueueTriggerResult:
        """
        WorkflowMonitorManager.list_status(limit) を走査し、monitor_statusが
        FAILED/TIMEOUTのレコードのうち、RetryEnqueueGuardがALLOWと判定し、
        まだQueueに存在しないものだけをRetryQueueManager.enqueue()する。
        """
        records = self._monitor.list_status(limit=limit)
        scanned = len(records)
        enqueued = 0
        skipped_existing = 0
        skipped_status = 0
        skipped_history = 0
        failed = 0

        for record in records:
            if record.monitor_status not in _RETRY_TARGET_STATUSES:
                skipped_status += 1
                continue

            has_history = self._history.has_history(record.run_id)
            guard_decision = self._guard.decide(record.run_id, has_history=has_history)
            if guard_decision.outcome == RetryEnqueueGuardOutcome.BLOCK:
                skipped_history += 1
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
            skipped_history=skipped_history,
        )


class NullRetryEnqueueTrigger:
    """
    RetryEnqueueTrigger のダミー実装（Null Object）。

    workflow_monitor / retry_queue / retry_history への参照を一切保持せず、常に
    「検知0件・enqueue 0件」の結果を返す。
    """

    def enqueue_pending_failures(self, limit: int | None = None) -> RetryEnqueueTriggerResult:
        return RetryEnqueueTriggerResult(
            scanned=0, enqueued=0, skipped_existing=0, skipped_status=0, failed=0,
            skipped_history=0,
        )
