"""
Null Retry Queue Manager（v3.1.0）

NullRetryQueueManager: RETRY_QUEUE_ENABLED=false の場合のダミー実装。すべての操作が
                        副作用なく DISABLED 相当の結果を返す。

設計方針:
    - RetryQueueManagerと継承関係を持たない（Duck Typing）。retry_engineの
      RetryManager/NullRetryManagerと同じ関係とする
      （docs/design/retry_queue_foundation.md 5章・6章）。
    - Charterで明示的にファイルが分離されているため、retry_queue_manager.pyとは
      独立したファイルとする（retry_engineのNullRetryManagerはretry_manager.pyに
      同居するが、本パッケージでは意図的に踏襲しない）。
    - 実データ（_items）を一切保持しない。
"""
from __future__ import annotations

from .retry_queue_item import RetryQueueItem
from .retry_queue_result import RetryQueueOutcome, RetryQueueResult

_DISABLED_REASON = "Retry Queue is disabled (RETRY_QUEUE_ENABLED=false)."


class NullRetryQueueManager:
    """RETRY_QUEUE_ENABLED=false のときに使用するダミー実装。すべて no-op。"""

    def enqueue(
        self,
        run_id: str,
        workflow_name: str,
        retry_attempt: int = 1,
        priority: int | None = None,
    ) -> RetryQueueResult:
        return RetryQueueResult(outcome=RetryQueueOutcome.DISABLED, item=None, reason=_DISABLED_REASON)

    def dequeue(self) -> RetryQueueResult:
        return RetryQueueResult(outcome=RetryQueueOutcome.DISABLED, item=None, reason=_DISABLED_REASON)

    def remove(self, run_id: str) -> RetryQueueResult:
        return RetryQueueResult(outcome=RetryQueueOutcome.DISABLED, item=None, reason=_DISABLED_REASON)

    def list(self, limit: int | None = None) -> list[RetryQueueItem]:
        return []

    def exists(self, run_id: str) -> bool:
        return False

    def count(self) -> int:
        return 0
