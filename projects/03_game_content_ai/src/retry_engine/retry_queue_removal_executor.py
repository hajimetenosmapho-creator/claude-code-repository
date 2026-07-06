"""
Retry Queue Removal Executor（v4.2.0）

RetryQueueRemovalResult:   RetryQueueUpdateDecision 1件に対する除去処理結果を保持する軽量データ
RetryQueueRemovalExecutor: RetryQueueUpdateDecision のリストを受け取り、outcome が
                           COMPLETE / FAIL の項目についてのみ remove_fn を呼び出し、
                           Queueから該当項目を除去するコンポーネント

設計方針:
    - RetryQueueManager / NullRetryQueueManager 型への依存を一切持たない。remove操作は
      呼び出しごとに remove_fn（Callable[[str], RetryQueueResult]）として受け取る
      （docs/design/retry_queue_removal_foundation.md 2章 案A）。
    - Stateless。RetryQueueUpdateDecision と remove_fn を受け取り、結果を返すだけの
      メソッドのみを持つ。内部状態を一切保持しない。
    - outcome が NOOP（SKIPPED / NOT_FOUND / DISABLED 由来）の項目は remove_fn を
      呼び出さない（4章 除去方針）。SKIPPED（max_attempts到達）のQueue滞留対応は
      本Releaseの対象外とし、次Release以降に委ねる（Charter 注記）。
    - RetryQueueResult.outcome が NOT_FOUND / DISABLED であってもエラーとして
      扱わない（RetryQueueManager.remove() の既存の正常な結果の範囲内、14章
      Design Decision #6）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from retry_queue import RetryQueueResult

from .retry_queue_update_decider import RetryQueueUpdateDecision, RetryQueueUpdateOutcome

RemoveFn = Callable[[str], RetryQueueResult]

_REMOVABLE_OUTCOMES = (RetryQueueUpdateOutcome.COMPLETE, RetryQueueUpdateOutcome.FAIL)


@dataclass(frozen=True)
class RetryQueueRemovalResult:
    """1件のRetryQueueUpdateDecisionに対する除去処理結果を保持する軽量データ。"""

    decision: RetryQueueUpdateDecision
    attempted: bool
    queue_result: RetryQueueResult | None
    reason: str


class RetryQueueRemovalExecutor:
    """RetryQueueUpdateDecisionを対象に、COMPLETE/FAILの項目のみremove_fnを呼び出すコンポーネント。"""

    def apply_all(
        self, decisions: list[RetryQueueUpdateDecision], remove_fn: RemoveFn
    ) -> list[RetryQueueRemovalResult]:
        """decisionsの各要素についてapply()を呼び出し、結果のリストを返す。"""
        return [self.apply(decision, remove_fn) for decision in decisions]

    def apply(
        self, decision: RetryQueueUpdateDecision, remove_fn: RemoveFn
    ) -> RetryQueueRemovalResult:
        """1件のRetryQueueUpdateDecisionについて、除去を試行するかどうかを判定し実行する。"""
        if decision.outcome not in _REMOVABLE_OUTCOMES:
            return RetryQueueRemovalResult(
                decision=decision,
                attempted=False,
                queue_result=None,
                reason=f"decision.outcome={decision.outcome.value} is not eligible for queue removal.",
            )

        run_id = decision.execution_result.dispatch_event.candidate_event.run_id
        queue_result = remove_fn(run_id)
        return RetryQueueRemovalResult(
            decision=decision,
            attempted=True,
            queue_result=queue_result,
            reason=f"remove() was called for run_id={run_id} (decision.outcome={decision.outcome.value}).",
        )
