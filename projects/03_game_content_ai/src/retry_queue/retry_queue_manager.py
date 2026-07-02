"""
Retry Queue Manager（v3.1.0）

RetryQueueManager: Retry Queue全体の起動口。enqueue/dequeue/remove/list/exists/count の
                    6操作のみを提供し、内部にQueueの実データ（dict[str, RetryQueueItem]）を
                    保持する。

設計方針:
    - Queue管理のみを責務とする。Retry実行・Retry可否判定（RetryPolicyの責務）・
      Scheduler連携・永続化はいずれも行わない
      （docs/design/retry_queue_foundation.md 5章）。
    - workflow_engine/workflow_monitor/retry_engine/execution_history のいずれも
      importしない（呼び出さない）。標準ライブラリのみに依存する独立した葉パッケージ
      （同設計書7章）。
    - enqueue()はRetryQueueItemを直接受け取らず、個々のフィールドを受け取って内部で
      組み立てる（呼び出し元は入力の意味だけを知っていればよい、という
      RetryManager.retry()と同じ考え方。同設計書4章）。
    - Queueへの出し入れの可否判定は「容量上限」「run_idの重複」の2点のみ。
    - 呼び出し元へ返すRetryQueueItemは常にコピー（dataclasses.replace()）であり、
      呼び出し元が書き換えても内部ストアには影響しない。
    - スレッド安全性は保証しない（既存Manager群と同じく単一プロセス・単一スレッドでの
      利用を前提とする。同設計書11章）。
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from .null_retry_queue_manager import NullRetryQueueManager
from .retry_queue_config import RetryQueueConfig
from .retry_queue_item import RetryQueueItem
from .retry_queue_result import RetryQueueOutcome, RetryQueueResult
from .retry_queue_status import RetryQueueStatus


class RetryQueueManager:
    """Retry Queue全体の起動口。Queue管理（出し入れ）のみを行う。"""

    def __init__(self, config: RetryQueueConfig):
        self._config = config
        self._items: dict[str, RetryQueueItem] = {}

    @classmethod
    def from_config(cls, config: RetryQueueConfig) -> "RetryQueueManager | NullRetryQueueManager":
        """
        RetryQueueConfig から RetryQueueManager を構築する。

        RETRY_QUEUE_ENABLED が false の場合は NullRetryQueueManager を返す。
        """
        if not config.is_ready():
            return NullRetryQueueManager()
        return cls(config=config)

    def enqueue(
        self,
        run_id: str,
        workflow_name: str,
        retry_attempt: int = 1,
        priority: int | None = None,
    ) -> RetryQueueResult:
        """
        run_id をQueueへ追加する。

        既にQueueに存在するrun_id、またはmax_queue_sizeに達している場合はREJECTEDを返す。
        priority省略時はconfig.default_priorityを使用する。
        """
        if run_id in self._items:
            return RetryQueueResult(
                outcome=RetryQueueOutcome.REJECTED, item=None,
                reason=f"duplicate run_id: {run_id}",
            )
        if len(self._items) >= self._config.max_queue_size:
            return RetryQueueResult(
                outcome=RetryQueueOutcome.REJECTED, item=None,
                reason=f"queue is full (max_queue_size={self._config.max_queue_size}).",
            )

        item = RetryQueueItem(
            run_id=run_id,
            workflow_name=workflow_name,
            enqueue_time=datetime.now(),
            priority=priority if priority is not None else self._config.default_priority,
            retry_attempt=retry_attempt,
            status=RetryQueueStatus.WAITING,
        )
        self._items[run_id] = item
        return RetryQueueResult(outcome=RetryQueueOutcome.ENQUEUED, item=replace(item), reason=None)

    def dequeue(self) -> RetryQueueResult:
        """
        priority昇順・enqueue_time昇順で先頭の項目をQueueから取り出す。

        取り出された項目はstatus=PROCESSINGに更新された上でQueueから削除される
        （以後list()/exists()/count()には現れない）。Queueが空の場合はEMPTYを返す。
        """
        if not self._items:
            return RetryQueueResult(outcome=RetryQueueOutcome.EMPTY, item=None, reason="queue is empty.")

        next_run_id = min(
            self._items, key=lambda run_id: (self._items[run_id].priority, self._items[run_id].enqueue_time),
        )
        item = self._items.pop(next_run_id)
        item.status = RetryQueueStatus.PROCESSING
        return RetryQueueResult(outcome=RetryQueueOutcome.DEQUEUED, item=replace(item), reason=None)

    def remove(self, run_id: str) -> RetryQueueResult:
        """
        指定したrun_idをQueueから取り消す。

        取り消された項目はstatus=CANCELLEDに更新された上でQueueから削除される。
        Queueに存在しない場合はNOT_FOUNDを返す。
        """
        if run_id not in self._items:
            return RetryQueueResult(
                outcome=RetryQueueOutcome.NOT_FOUND, item=None,
                reason=f"run_id={run_id} was not found in the queue.",
            )
        item = self._items.pop(run_id)
        item.status = RetryQueueStatus.CANCELLED
        return RetryQueueResult(outcome=RetryQueueOutcome.REMOVED, item=replace(item), reason=None)

    def list(self, limit: int | None = None) -> list[RetryQueueItem]:
        """Queue内の項目をpriority昇順・enqueue_time昇順で返す（コピー）。"""
        ordered = sorted(self._items.values(), key=lambda item: (item.priority, item.enqueue_time))
        if limit is not None:
            ordered = ordered[:limit]
        return [replace(item) for item in ordered]

    def exists(self, run_id: str) -> bool:
        """run_idがQueueに存在するか返す。"""
        return run_id in self._items

    def count(self) -> int:
        """Queueに保持されている項目数を返す。"""
        return len(self._items)
