"""
Retry Enqueue Trigger パッケージ（v4.6.0、v4.8.0で拡張）

WorkflowMonitorManager（v2.9.0）が判定したFAILED/TIMEOUTのWorkflowを検知し、
RetryEnqueueGuard（v4.8.0）の判定を経て、まだRetry Queue（v3.1.0）に
存在しないものだけをenqueueする最小Adapter。retry_engineは経由せず、
workflow_monitor / retry_queue / retry_history（v4.8.0）に直接依存する。

処理フロー（v4.8.0）:
    RetryEnqueueTrigger.enqueue_pending_failures(limit)
        → WorkflowMonitorManager.list_status(limit) でFAILED/TIMEOUTを検知
        → RetryHistoryManager.has_history(run_id) を参照し
          RetryEnqueueGuard.decide() でALLOW/BLOCKを判定（v4.8.0新規）
        → RetryQueueManager.exists(run_id) で重複を確認
        → RetryQueueManager.enqueue(run_id, workflow_name) で未投入分のみ投入
        → RetryEnqueueTriggerResult（集計結果。skipped_historyを含む）を返す

設計方針:
    - workflow_monitor / retry_queue / retry_history / retry_engineのいずれも
      本Releaseでは無改修（docs/design/retry_enqueue_guard.md 1章）。
    - Feature Gate・Configクラスは持たない。有効/無効はRetryEnqueueTrigger /
      NullRetryEnqueueTriggerのどちらを構築するかで表現する（同設計書2章）。
    - Queue内重複防止はRetryQueueManager.exists()に加え、v4.8.0で
      RetryEnqueueGuard（再試行履歴が1回でもあればブロックする二値判定）を
      追加した。これにより、Queueから除去された後もMonitor上でFAILED/TIMEOUTの
      まま観測され続けるrun_idの無限再投入リスク（v4.6.0 Known Issue）を
      解消した（docs/design/retry_enqueue_guard.md 11章 Known Issue参照。
      ただしRETRY_MAX_ATTEMPTSを活かした複数回リトライは本Releaseでは
      実質使えないままである）。
"""
from .retry_enqueue_guard import (
    RetryEnqueueGuard,
    RetryEnqueueGuardDecision,
    RetryEnqueueGuardOutcome,
)
from .retry_enqueue_trigger import (
    NullRetryEnqueueTrigger,
    RetryEnqueueTrigger,
    RetryEnqueueTriggerResult,
)

__all__ = [
    "RetryEnqueueTrigger",
    "NullRetryEnqueueTrigger",
    "RetryEnqueueTriggerResult",
    "RetryEnqueueGuard",
    "RetryEnqueueGuardOutcome",
    "RetryEnqueueGuardDecision",
]
