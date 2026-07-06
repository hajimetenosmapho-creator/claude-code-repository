"""
Retry Queue Update Decider（v4.1.0）

RetryQueueUpdateOutcome: RetryExecutionResult 1件に対する判定結果の種別
RetryQueueUpdateDecision: 判定結果を保持する軽量データ
RetryQueueUpdateDecider:  RetryExecutionResult のリストを受け取り、各要素について
                          対応するRetry Queue項目の更新先状態を判定するコンポーネント

設計方針:
    - Queueへの書き込みは一切行わない。RetryQueueManager / NullRetryQueueManager への
      参照を持たない（コンストラクタ引数にも存在しない）。判定のみを行う
      （docs/design/retry_queue_update_foundation.md 3章・10章）。
    - Stateless。RetryExecutionResult を受け取り、判定結果を返すだけの
      純粋関数的なメソッドのみを持つ。
    - RetryQueueStatus（retry_queue の公開シンボル）は型として参照するが、
      RetryQueueManager 等の操作系シンボルは一切importしない
      （同設計書4章の判定方針を参照）。
    - 判定は「再実行が実際に実行されたか」（RetryResult.outcome == RETRIED）を
      唯一の分岐点とする。SKIPPED / NOT_FOUND / DISABLED はいずれも
      「Queueの状態を変える根拠がない」という共通の性質を持つため、NOOP という
      単一の安全側の結果に統一する（同設計書4章・14章 Design Decision #2）。
      とりわけ SKIPPED（RetryPolicy が再試行上限到達等で対象外と判定したケース）は
      NOOP のまま次Releaseまで Queue に滞留し続ける可能性がある。この滞留の扱いは
      本Foundationの対象外とし、Release 4.2「Retry Queue Removal」の検討事項として
      申し送る（同設計書12章 Future Extension・16.3節 Recommendation 2）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from retry_queue import RetryQueueStatus

from .retry_execution_coordinator import RetryExecutionResult
from .retry_result import RetryOutcome


class RetryQueueUpdateOutcome(Enum):
    COMPLETE = "complete"  # 再実行成功 → RetryQueueStatus.COMPLETED
    FAIL = "fail"          # 再実行失敗 → RetryQueueStatus.FAILED
    NOOP = "noop"          # 再実行が行われていない → 更新しない


@dataclass(frozen=True)
class RetryQueueUpdateDecision:
    """1件のRetryExecutionResultに対する判定結果を保持する軽量データ。"""

    execution_result: RetryExecutionResult
    outcome: RetryQueueUpdateOutcome
    target_status: RetryQueueStatus | None
    reason: str


class RetryQueueUpdateDecider:
    """RetryExecutionResultを対象に、対応するQueue項目の更新先状態を判定するコンポーネント。"""

    def decide_all(
        self, execution_results: list[RetryExecutionResult]
    ) -> list[RetryQueueUpdateDecision]:
        """execution_resultsの各要素についてdecide()を呼び出し、結果のリストを返す。"""
        return [self.decide(execution_result) for execution_result in execution_results]

    def decide(self, execution_result: RetryExecutionResult) -> RetryQueueUpdateDecision:
        """1件のRetryExecutionResultについて、更新先のRetryQueueStatusを判定する。"""
        retry_result = execution_result.retry_result

        if retry_result.outcome == RetryOutcome.RETRIED:
            if retry_result.workflow_engine_result.overall_success:
                return RetryQueueUpdateDecision(
                    execution_result=execution_result,
                    outcome=RetryQueueUpdateOutcome.COMPLETE,
                    target_status=RetryQueueStatus.COMPLETED,
                    reason="retry was executed and workflow_engine_result.overall_success=True.",
                )
            return RetryQueueUpdateDecision(
                execution_result=execution_result,
                outcome=RetryQueueUpdateOutcome.FAIL,
                target_status=RetryQueueStatus.FAILED,
                reason="retry was executed but workflow_engine_result.overall_success=False.",
            )

        # SKIPPED / NOT_FOUND / DISABLED: 再実行が行われていないため、
        # Queueの更新先を確定させない（NOOP）。
        return RetryQueueUpdateDecision(
            execution_result=execution_result,
            outcome=RetryQueueUpdateOutcome.NOOP,
            target_status=None,
            reason=f"no retry was executed (retry_result.outcome={retry_result.outcome.value}).",
        )
