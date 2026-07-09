"""
Retry Enqueue Guard（v4.8.0）

RetryEnqueueGuard: 再試行履歴（has_history）の有無から、enqueueを許可するか
                    拒否するかを判定するだけのStatelessなコンポーネント。

設計方針:
    - has_history: bool という既に解決済みの値のみを入力とし、RetryHistoryManager /
      NullRetryHistoryManager型を一切importしない（RetryQueueUpdateDecider・
      RetryQueueCleanupDeciderと同じ設計言語。docs/design/retry_enqueue_guard.md
      2章 Design Policy #2）。
    - 判定基準は「履歴が1回でもあればBLOCK」の二値のみ。RetryHistoryRecord.
      attempt_countとRetryPolicy.max_attemptsの比較は行わない（同設計書2章
      Design Policy #1）。RETRY_MAX_ATTEMPTSを活かした複数回リトライは本Release
      では実質使えないままである（同設計書11章 Known Issue）。
    - decide_all()（バッチ版）は追加しない。呼び出し元（RetryEnqueueTrigger）は
      WorkflowMonitorRecordを1件ずつループしており、decide()を1件ずつ呼ぶ形が
      既存構造と一貫する。
    - NullRetryEnqueueGuardは追加しない。Guardを無効化したい場合は呼び出し元が
      historyを省略する（NullRetryHistoryManager()にフォールバックし、
      has_historyが常にFalseになる）ことで既に完結している。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class RetryEnqueueGuardOutcome(Enum):
    ALLOW = auto()
    BLOCK = auto()


@dataclass(frozen=True)
class RetryEnqueueGuardDecision:
    """1件のrun_idに対するGuard判定結果。"""

    run_id: str
    outcome: RetryEnqueueGuardOutcome
    reason: str


class RetryEnqueueGuard:
    """
    再試行履歴（has_history）の有無から、enqueueを許可するか拒否するかを判定する
    Statelessなコンポーネント。RetryHistoryManager等の外部型には一切依存しない。
    """

    def decide(self, run_id: str, has_history: bool) -> RetryEnqueueGuardDecision:
        """
        has_historyがTrueの場合はBLOCK、Falseの場合はALLOWを返す。
        """
        if has_history:
            return RetryEnqueueGuardDecision(
                run_id=run_id,
                outcome=RetryEnqueueGuardOutcome.BLOCK,
                reason=f"run_id={run_id} already has retry history (has_history=True).",
            )
        return RetryEnqueueGuardDecision(
            run_id=run_id,
            outcome=RetryEnqueueGuardOutcome.ALLOW,
            reason=f"run_id={run_id} has no retry history yet.",
        )
