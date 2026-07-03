"""
Retry Scheduler Source パッケージ（v3.3.0）

Retry Queue の状態（待機中の項目一覧・件数）を Scheduler 側の語彙で読み取る
ための最小Adapter。RetrySchedulerSource / NullRetrySchedulerSource を提供する。

処理フロー（v3.3.0）:
    RetrySchedulerSource(queue).list_pending_retries(limit)
        → RetryQueueManager.list(limit) への委譲
    RetrySchedulerSource(queue).count_pending_retries()
        → RetryQueueManager.count() への委譲

設計方針:
    - src/retry_scheduler_source/ は retry_queue の公開シンボルのみに依存する。
      workflow_engine/workflow_monitor/retry_engine/execution_history/ai/
      pipeline/scheduler はいずれもimportしない
      （docs/design/retry_scheduler_integration.md 7章）。
    - Feature Gate・Configクラス・from_config()/from_env() は持たない。
      有効／無効は呼び出し元がどちらのクラスを構築するかで決まる。
    - dequeue() / remove() は一切使用しない（読み取り専用）。
    - 本Release時点ではどのパッケージからも呼ばれない（Foundation First）。
"""
from .retry_scheduler_source import NullRetrySchedulerSource, RetrySchedulerSource

__all__ = [
    "RetrySchedulerSource",
    "NullRetrySchedulerSource",
]
