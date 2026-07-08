"""
Retry Queue Cleanup Decider（v4.3.0）

RetryQueueCleanupOutcome: RetryQueueUpdateDecision 1件に対するCleanup判定結果の種別
RetryQueueCleanupDecision: 判定結果を保持する軽量データ
RetryQueueCleanupDecider:  RetryQueueUpdateDecision のリストを受け取り、各要素について
                           SKIPPED由来のNOOPのみをCLEANUP対象と判定するコンポーネント

設計方針:
    - Queueへの書き込みは一切行わない。RetryQueueManager / NullRetryQueueManager への
      参照を持たない（コンストラクタ引数にも存在しない）。判定のみを行う
      （retry_queue_update_decider.py・retry_queue_removal_executor.pyと同じ方針）。
    - Stateless。RetryQueueUpdateDecision を受け取り、判定結果を返すだけの
      純粋関数的なメソッドのみを持つ。
    - Cleanup対象はoutcome=NOOPのうちretry_result.outcome=SKIPPEDのものに限定する
      （Project Charter「Cleanup対象: SKIPPEDのみ」）。
    - COMPLETE / FAIL（v4.2.0で既にremove済みのはずの項目）は対象外（KEEP）。
    - NOOPであってもretry_result.outcomeがNOT_FOUND / DISABLEDの項目は対象外（KEEP）。
      これらはQueueに滞留する性質がSKIPPED（max_attempts到達）と異なり、本Foundationの
      対象外とする（Project Charter「対象外: COMPLETE / FAILED / NOT_FOUND / DISABLED」）。
    - Dead Letter・隔離Queueといった新しいQueueステータスは追加しない
      （既存のRetryQueueStatusのみを使用する）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .retry_queue_update_decider import RetryQueueUpdateDecision, RetryQueueUpdateOutcome
from .retry_result import RetryOutcome


class RetryQueueCleanupOutcome(Enum):
    CLEANUP = "cleanup"  # SKIPPED由来のNOOP → Queueから除去してよい
    KEEP = "keep"        # それ以外 → Queueに残す


@dataclass(frozen=True)
class RetryQueueCleanupDecision:
    """1件のRetryQueueUpdateDecisionに対するCleanup判定結果を保持する軽量データ。"""

    update_decision: RetryQueueUpdateDecision
    outcome: RetryQueueCleanupOutcome
    reason: str


class RetryQueueCleanupDecider:
    """RetryQueueUpdateDecisionを対象に、SKIPPED由来のNOOPのみCLEANUPと判定するコンポーネント。"""

    def decide_all(
        self, update_decisions: list[RetryQueueUpdateDecision]
    ) -> list[RetryQueueCleanupDecision]:
        """update_decisionsの各要素についてdecide()を呼び出し、結果のリストを返す。"""
        return [self.decide(update_decision) for update_decision in update_decisions]

    def decide(self, update_decision: RetryQueueUpdateDecision) -> RetryQueueCleanupDecision:
        """1件のRetryQueueUpdateDecisionについて、CleanupすべきかKeepすべきかを判定する。"""
        if update_decision.outcome != RetryQueueUpdateOutcome.NOOP:
            return RetryQueueCleanupDecision(
                update_decision=update_decision,
                outcome=RetryQueueCleanupOutcome.KEEP,
                reason=f"update_decision.outcome={update_decision.outcome.value} is not NOOP.",
            )

        retry_outcome = update_decision.execution_result.retry_result.outcome
        if retry_outcome == RetryOutcome.SKIPPED:
            return RetryQueueCleanupDecision(
                update_decision=update_decision,
                outcome=RetryQueueCleanupOutcome.CLEANUP,
                reason="NOOP originates from RetryOutcome.SKIPPED (eligible for cleanup).",
            )

        return RetryQueueCleanupDecision(
            update_decision=update_decision,
            outcome=RetryQueueCleanupOutcome.KEEP,
            reason=(
                f"NOOP originates from RetryOutcome.{retry_outcome.value} "
                "(not SKIPPED; out of cleanup scope)."
            ),
        )
