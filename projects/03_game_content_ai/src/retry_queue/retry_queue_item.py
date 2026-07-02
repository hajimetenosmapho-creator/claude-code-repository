"""
Retry Queue Item定義（v3.1.0）

RetryQueueItem: Queueに保持される1件の再実行待ち情報

設計方針:
    - RetryRequest/RetryResult（retry_engine、いずれもfrozen=True）とは異なり、
      frozen=True にしない。RetryQueueItemは「1回限りの入出力データ」ではなく
      「Queueの中に存在し続け、RetryQueueManagerの内部ストアがライフサイクル中に
      状態を書き換える対象」であるため、WorkflowMonitorRecord（workflow_monitor、
      同じくfrozenでない@dataclass）に近い性質を持つ
      （docs/design/retry_queue_foundation.md 4章）。
    - RetryQueueManagerの外（呼び出し元）へは常にコピーを返す。呼び出し元が
      フィールドを書き換えても内部ストアには影響しない。
    - priorityは「数値が小さいほど優先度が高い」（Unix niceと同じ向き）。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .retry_queue_status import RetryQueueStatus


@dataclass
class RetryQueueItem:
    run_id: str
    workflow_name: str
    enqueue_time: datetime
    priority: int
    retry_attempt: int
    status: RetryQueueStatus
