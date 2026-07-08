"""
Retry Queue Terminal Cleanup Decider（v4.4.0）

RetryQueueTerminalCleanupDecision: RetryQueueUpdateDecision 1件に対するCleanup判定結果を
                                    保持する軽量データ
RetryQueueTerminalCleanupDecider:  RetryQueueUpdateDecision のリストを受け取り、各要素について
                                    NOT_FOUND / DISABLED由来のNOOPのみ、
                                    retry_outcome_terminality.RETRY_OUTCOME_TERMINALITY
                                    分類表を参照してCLEANUP/KEEPを判定するコンポーネント

命名の相互参照（混同注意）:
    本ファイルはv4.3.0の RetryQueueCleanupDecider（retry_queue_cleanup_decider.py、
    SKIPPED由来のNOOP専用）とは別の新規コンポーネントである。名称が似ている
    （RetryQueueCleanupDecider vs RetryQueueTerminalCleanupDecider）ため混同しないこと。
    本コンポーネントの対象は NOT_FOUND / DISABLED 由来のNOOPのみであり、SKIPPED由来の
    NOOPは引き続き RetryQueueCleanupDecider（v4.3.0、無改修）の責務のままである。

設計方針:
    - Queueへの書き込みは一切行わない。RetryQueueManager / NullRetryQueueManager への
      参照を持たない（コンストラクタ引数にも存在しない）。判定のみを行う
      （retry_queue_cleanup_decider.pyと同じ方針）。
    - Stateless。RetryQueueUpdateDecision を受け取り、判定結果を返すだけの
      純粋関数的なメソッドのみを持つ。
    - Cleanup方針の判断基準は本ファイル内にハードコードしない。
      retry_outcome_terminality.classify_terminality()（RETRY_OUTCOME_TERMINALITY
      分類表）を唯一の判断基準とし、TERMINAL→CLEANUP、TRANSIENT→KEEPとして機械的に
      導出する（ただし本表の権威範囲は本Decider自身に限られる。retry_outcome_terminality.py
      のモジュールdocstring、docs/design/retry_queue_notfound_disabled_cleanup_foundation.md
      2章・3.2節）。
    - COMPLETE / FAIL / SKIPPED（いずれも他コンポーネントが既にCleanup/remove済み
      のはずの範囲）は、本Deciderでは分類表を参照するまでもなく構造的にKEEP
      （対象外）として扱う。これにより、v4.2.0 RetryQueueRemovalExecutor・v4.3.0
      RetryQueueCleanupDeciderとの二重remove呼び出しを避ける
      （docs/design/retry_queue_notfound_disabled_cleanup_foundation.md 8章 Boundary）。
    - Dead Letter・隔離Queueといった新しいQueueステータスは追加しない
      （既存のRetryQueueStatusのみを使用する）。
"""
from __future__ import annotations

from dataclasses import dataclass

from .retry_outcome_terminality import (
    RetryCleanupReason,
    RetryOutcomeTerminality,
    classify_reason,
    classify_terminality,
)
from .retry_queue_cleanup_decider import RetryQueueCleanupOutcome
from .retry_queue_update_decider import RetryQueueUpdateDecision

_OUT_OF_SCOPE_REASONS = (
    RetryCleanupReason.COMPLETE,
    RetryCleanupReason.FAIL,
    RetryCleanupReason.SKIPPED,
)


@dataclass(frozen=True)
class RetryQueueTerminalCleanupDecision:
    """1件のRetryQueueUpdateDecisionに対するCleanup判定結果を保持する軽量データ。"""

    update_decision: RetryQueueUpdateDecision
    outcome: RetryQueueCleanupOutcome
    reason: str


class RetryQueueTerminalCleanupDecider:
    """
    RetryQueueUpdateDecisionを対象に、NOT_FOUND / DISABLED由来のNOOPのみ
    RetryOutcomeTerminality分類表を参照してCLEANUP/KEEPを判定するコンポーネント。

    COMPLETE / FAIL / SKIPPED由来の項目は対象外（KEEP）のまま構造的に除外する
    （他コンポーネントの責務範囲。二重remove呼び出しを避けるため）。
    """

    def decide_all(
        self, update_decisions: list[RetryQueueUpdateDecision]
    ) -> list[RetryQueueTerminalCleanupDecision]:
        """update_decisionsの各要素についてdecide()を呼び出し、結果のリストを返す。"""
        return [self.decide(update_decision) for update_decision in update_decisions]

    def decide(self, update_decision: RetryQueueUpdateDecision) -> RetryQueueTerminalCleanupDecision:
        """1件のRetryQueueUpdateDecisionについて、CleanupすべきかKeepすべきかを判定する。"""
        reason = classify_reason(update_decision)

        if reason in _OUT_OF_SCOPE_REASONS:
            return RetryQueueTerminalCleanupDecision(
                update_decision=update_decision,
                outcome=RetryQueueCleanupOutcome.KEEP,
                reason=(
                    f"reason={reason.value} is out of scope for this Decider "
                    "(handled by RetryQueueRemovalExecutor/RetryQueueCleanupDecider)."
                ),
            )

        terminality = classify_terminality(reason)
        if terminality == RetryOutcomeTerminality.TERMINAL:
            return RetryQueueTerminalCleanupDecision(
                update_decision=update_decision,
                outcome=RetryQueueCleanupOutcome.CLEANUP,
                reason=f"reason={reason.value} is classified as TERMINAL (eligible for cleanup).",
            )

        return RetryQueueTerminalCleanupDecision(
            update_decision=update_decision,
            outcome=RetryQueueCleanupOutcome.KEEP,
            reason=f"reason={reason.value} is classified as TRANSIENT (not eligible for cleanup).",
        )
