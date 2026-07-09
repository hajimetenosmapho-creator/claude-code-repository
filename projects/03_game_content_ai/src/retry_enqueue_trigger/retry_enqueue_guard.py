"""
Retry Enqueue Guard（v4.8.0、v5.0.0で判定基準を精緻化）

RetryEnqueueGuard: next_attempt（次に実行しようとしている試行番号）が
                    max_attempts（許容される最大試行回数）を超えるかどうかから、
                    enqueueを許可するか拒否するかを判定するだけのStatelessな
                    コンポーネント。

設計方針:
    - next_attempt: int / max_attempts: int という、既に解決済みのプリミティブ値
      のみを入力とし、RetryHistoryManager / NullRetryHistoryManager型は
      もちろんRetryPolicy（retry_engine）型も一切importしない（RetryQueueUpdate
      Decider・RetryQueueCleanupDeciderと同じ設計言語。docs/design/
      retry_enqueue_guard_refinement_foundation.md 2章 Design Policy #1）。
    - 判定基準は「次の試行番号が上限を超えるか」の1点のみ：
      next_attempt > max_attempts ならBLOCK、そうでなければALLOW。
      （v4.8.0の「履歴が1回でもあればBLOCK」二値判定から精緻化。同設計書2章）。
    - decide_all()（バッチ版）は追加しない。呼び出し元（RetryEnqueueTrigger）は
      WorkflowMonitorRecordを1件ずつループしており、decide()を1件ずつ呼ぶ形が
      既存構造と一貫する。
    - NullRetryEnqueueGuardは追加しない。Guardを無効化したい場合は呼び出し元が
      historyを省略する（NullRetryHistoryManager()にフォールバックし、
      next_attemptが常に1になる）ことで既に完結している。
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
    next_attempt（次の試行番号）がmax_attempts（許容される最大試行回数）を
    超えるかどうかから、enqueueを許可するか拒否するかを判定するStatelessな
    コンポーネント。RetryHistoryManager・RetryPolicy等の外部型には一切依存しない。
    """

    def decide(self, run_id: str, next_attempt: int, max_attempts: int) -> RetryEnqueueGuardDecision:
        """
        next_attemptがmax_attemptsを超える場合はBLOCK、そうでなければALLOWを返す。
        """
        if next_attempt > max_attempts:
            return RetryEnqueueGuardDecision(
                run_id=run_id,
                outcome=RetryEnqueueGuardOutcome.BLOCK,
                reason=(
                    f"run_id={run_id} next_attempt={next_attempt} exceeds "
                    f"max_attempts={max_attempts}."
                ),
            )
        return RetryEnqueueGuardDecision(
            run_id=run_id,
            outcome=RetryEnqueueGuardOutcome.ALLOW,
            reason=(
                f"run_id={run_id} next_attempt={next_attempt} is within "
                f"max_attempts={max_attempts}."
            ),
        )
