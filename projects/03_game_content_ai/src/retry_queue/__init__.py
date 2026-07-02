"""
Retry Queue パッケージ（v3.1.0）

再実行待ちの run_id を保持・出し入れするだけの最小基盤。Retry実行・Retry可否判定
（RetryPolicyの責務）・Workflow Engine/Retry Engine/Workflow Monitor/Execution History の
呼び出しはいずれも行わない。

処理フロー（v3.1.0）:
    RetryQueueManager.enqueue(run_id, workflow_name, retry_attempt, priority)
        → 重複run_id/容量超過チェック
        → RetryQueueItem(status=WAITING) を内部dictへ格納
        → RetryQueueResult(outcome=ENQUEUED, item=...) を返す

    RetryQueueManager.dequeue()
        → priority昇順・enqueue_time昇順で先頭の項目を取り出す
        → status=PROCESSINGに更新した上で内部dictから削除
        → RetryQueueResult(outcome=DEQUEUED, item=...) を返す

設計方針:
    - src/retry_queue/ はどの既存パッケージ（workflow_engine/workflow_monitor/
      retry_engine/execution_history/ai/pipeline/scheduler）もimportしない、
      標準ライブラリのみに依存する独立した葉パッケージ
      （docs/design/retry_queue_foundation.md 7章）。
    - RETRY_QUEUE_ENABLED=false の場合はNullRetryQueueManagerがすべてno-opで動作する。
    - Queueに入っている項目（RetryQueueItem）以外の状態は一切保持しない。
"""
from .null_retry_queue_manager import NullRetryQueueManager
from .retry_queue_config import RetryQueueConfig
from .retry_queue_item import RetryQueueItem
from .retry_queue_manager import RetryQueueManager
from .retry_queue_result import RetryQueueOutcome, RetryQueueResult
from .retry_queue_status import RetryQueueStatus

__all__ = [
    "RetryQueueStatus",
    "RetryQueueItem",
    "RetryQueueOutcome",
    "RetryQueueResult",
    "RetryQueueConfig",
    "RetryQueueManager",
    "NullRetryQueueManager",
]
