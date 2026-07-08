"""
Retry Enqueue Trigger パッケージ（v4.6.0）

WorkflowMonitorManager（v2.9.0）が判定したFAILED/TIMEOUTのWorkflowを検知し、
まだRetry Queue（v3.1.0）に存在しないものだけをenqueueする最小Adapter。
retry_engineは経由せず、workflow_monitor / retry_queueに直接依存する。

処理フロー（v4.6.0）:
    RetryEnqueueTrigger.enqueue_pending_failures(limit)
        → WorkflowMonitorManager.list_status(limit) でFAILED/TIMEOUTを検知
        → RetryQueueManager.exists(run_id) で重複を確認
        → RetryQueueManager.enqueue(run_id, workflow_name) で未投入分のみ投入
        → RetryEnqueueTriggerResult（集計結果）を返す

設計方針:
    - workflow_monitor / retry_queue / retry_engineのいずれも本Releaseでは
      無改修（docs/design/retry_enqueue_trigger_foundation.md 1章）。
    - Feature Gate・Configクラスは持たない。有効/無効はRetryEnqueueTrigger /
      NullRetryEnqueueTriggerのどちらを構築するかで表現する（同設計書2章）。
    - Queue内重複防止はRetryQueueManager.exists()のみ。Queueから除去された
      run_idの無限再投入リスクは本Releaseでは対策しない（Known Issue、
      同設計書11章）。
"""
from .retry_enqueue_trigger import (
    NullRetryEnqueueTrigger,
    RetryEnqueueTrigger,
    RetryEnqueueTriggerResult,
)

__all__ = [
    "RetryEnqueueTrigger",
    "NullRetryEnqueueTrigger",
    "RetryEnqueueTriggerResult",
]
