"""
Retry Queue Result定義（v3.1.0）

RetryQueueOutcome: enqueue/dequeue/remove 1回の操作結果種別を表すEnum
RetryQueueResult:  enqueue/dequeue/remove 1回の操作結果を保持するデータクラス

設計方針:
    - RetryResult（retry_engine）と同型の「操作結果を1つの型に統一する」パターンを
      enqueue()/dequeue()/remove()の3操作すべてに適用する。
    - list()/exists()/count()は読み取り専用の問い合わせであり失敗の概念がないため、
      RetryQueueResultでラップせず素の型（list[RetryQueueItem]/bool/int）を直接返す
      （docs/design/retry_queue_foundation.md 4章）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .retry_queue_item import RetryQueueItem


class RetryQueueOutcome(Enum):
    ENQUEUED = "enqueued"    # enqueue()が成功した
    DEQUEUED = "dequeued"    # dequeue()が項目を取り出した
    REMOVED = "removed"      # remove()が項目を取り消した
    REJECTED = "rejected"    # enqueue()が容量超過または重複run_idにより拒否した
    NOT_FOUND = "not_found"  # remove()の対象run_idがQueueに存在しない
    EMPTY = "empty"          # dequeue()時にQueueが空だった
    DISABLED = "disabled"    # RETRY_QUEUE_ENABLED=false


@dataclass(frozen=True)
class RetryQueueResult:
    outcome: RetryQueueOutcome
    item: RetryQueueItem | None
    reason: str | None
