"""
Retry Scheduler Decision パッケージ（v3.5.0）

RetrySchedulerSource（またはNullRetrySchedulerSource）が返す待機中の項目一覧から、
「次に処理すべき候補」を選ぶだけの最小コンポーネント。RetrySchedulerDecisionを提供する。

処理フロー（v3.5.0）:
    RetrySchedulerDecision(retry_source).select_candidates(limit)
        → RetrySchedulerSource.list_pending_retries(limit) への委譲
    RetrySchedulerDecision(retry_source).select_next_candidate()
        → select_candidates(limit=1) の先頭1件（またはNone）

設計方針:
    - src/retry_scheduler_decision/ は retry_scheduler_source の公開シンボルのみに
      依存する。scheduler/retry_queue/retry_engine/workflow_engine/
      workflow_monitor/execution_history/ai/pipelineはいずれもimportしない。
    - Null Object Pattern（NullRetrySchedulerDecision）は採用しない。無効化は
      呼び出し元がretry_sourceにNullRetrySchedulerSource()を渡すことで表現する
      （本コンポーネント自身にはFeature Gate/Config軸が存在しないため。
      詳細は docs/design/retry_scheduler_decision.md 13章 Design Decision #2）。
    - dequeue() / remove()は一切使用しない（読み取り専用）。
    - 本Release時点ではどのパッケージからも呼ばれない（Foundation First）。
"""
from .retry_scheduler_decision import RetrySchedulerDecision

__all__ = [
    "RetrySchedulerDecision",
]
