"""
Retry Queue Cleanup Executor（v4.3.0）

RetryQueueCleanupResult:   RetryQueueCleanupDecision 1件に対するCleanup実行結果を保持する軽量データ
RetryQueueCleanupExecutor: RetryQueueCleanupDecision のリストを受け取り、outcome が
                           CLEANUP の項目についてのみ remove_fn を呼び出し、Queueから
                           該当項目を除去するコンポーネント

設計方針:
    - RetryQueueManager / NullRetryQueueManager 型への依存を一切持たない。remove操作は
      呼び出しごとに remove_fn（Callable[[str], RetryQueueResult]）として受け取る
      （retry_queue_removal_executor.pyと同じ方針。既存のRetryQueueManager.remove()を
      再利用し、新しいQueueステータス・Dead Letter・隔離Queueは追加しない）。
    - Stateless。RetryQueueCleanupDecision と remove_fn を受け取り、結果を返すだけの
      メソッドのみを持つ。内部状態を一切保持しない。
    - outcome が KEEP の項目は remove_fn を呼び出さない。
    - RetryQueueResult.outcome が NOT_FOUND / DISABLED であってもエラーとして
      扱わない（RetryQueueManager.remove() の既存の正常な結果の範囲内。
      retry_queue_removal_executor.pyと同じ方針）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from retry_queue import RetryQueueResult

from .retry_queue_cleanup_decider import RetryQueueCleanupDecision, RetryQueueCleanupOutcome

RemoveFn = Callable[[str], RetryQueueResult]


@dataclass(frozen=True)
class RetryQueueCleanupResult:
    """1件のRetryQueueCleanupDecisionに対するCleanup実行結果を保持する軽量データ。"""

    decision: RetryQueueCleanupDecision
    attempted: bool
    queue_result: RetryQueueResult | None
    reason: str


class RetryQueueCleanupExecutor:
    """RetryQueueCleanupDecisionを対象に、CLEANUPの項目のみremove_fnを呼び出すコンポーネント。"""

    def apply_all(
        self, decisions: list[RetryQueueCleanupDecision], remove_fn: RemoveFn
    ) -> list[RetryQueueCleanupResult]:
        """decisionsの各要素についてapply()を呼び出し、結果のリストを返す。"""
        return [self.apply(decision, remove_fn) for decision in decisions]

    def apply(
        self, decision: RetryQueueCleanupDecision, remove_fn: RemoveFn
    ) -> RetryQueueCleanupResult:
        """1件のRetryQueueCleanupDecisionについて、除去を試行するかどうかを判定し実行する。"""
        if decision.outcome != RetryQueueCleanupOutcome.CLEANUP:
            return RetryQueueCleanupResult(
                decision=decision,
                attempted=False,
                queue_result=None,
                reason=f"decision.outcome={decision.outcome.value} is not eligible for cleanup.",
            )

        run_id = decision.update_decision.execution_result.dispatch_event.candidate_event.run_id
        queue_result = remove_fn(run_id)
        return RetryQueueCleanupResult(
            decision=decision,
            attempted=True,
            queue_result=queue_result,
            reason=f"remove() was called for run_id={run_id} (decision.outcome={decision.outcome.value}).",
        )
