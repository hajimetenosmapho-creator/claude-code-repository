"""
Retry History Record Executor（v4.7.0）

RetryHistoryRecordResult:  1件のRetryExecutionResultに対する履歴記録結果を保持する軽量データ
RetryHistoryRecordExecutor: RetryExecutionResultのリストを受け取り、outcomeがRETRIEDの
                            項目についてのみrecord_fnを呼び出し、再試行履歴を記録する
                            コンポーネント

設計方針:
    - RetryHistoryManager / NullRetryHistoryManager型への依存を一切持たない。記録操作は
      呼び出しごとにrecord_fn（Callable[[str, int, datetime], RetryHistoryRecord | None]）
      として受け取る（RetryQueueRemovalExecutor、v4.2.0と同じ設計言語。
      docs/design/retry_history_foundation.md 6章）。
    - Stateless。RetryExecutionResultとrecord_fnを受け取り、結果を返すだけの
      メソッドのみを持つ。内部状態を一切保持しない。
    - outcomeがRETRIED以外（SKIPPED / NOT_FOUND / DISABLED）の項目はrecord_fnを
      呼び出さない（実際に再実行されていない試行を履歴として記録しないため）。
    - 記録結果を使って何かを判定・実行する処理（RetryEnqueueTriggerへのガード接続等）は
      本コンポーネントには一切存在しない（消費側の配線は次Release以降。Foundation First）。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Callable

from retry_history import RetryHistoryRecord

from .retry_execution_coordinator import RetryExecutionResult
from .retry_result import RetryOutcome

RecordFn = Callable[[str, int, datetime], "RetryHistoryRecord | None"]

_RECORDABLE_OUTCOMES = (RetryOutcome.RETRIED,)


@dataclass(frozen=True)
class RetryHistoryRecordResult:
    """1件のRetryExecutionResultに対する履歴記録結果を保持する軽量データ。"""

    execution_result: RetryExecutionResult
    recorded: bool
    history_record: "RetryHistoryRecord | None"
    reason: str


class RetryHistoryRecordExecutor:
    """RetryExecutionResultを対象に、outcome=RETRIEDの項目のみrecord_fnを呼び出すコンポーネント。"""

    def record_all(
        self, execution_results: list[RetryExecutionResult], record_fn: RecordFn
    ) -> list[RetryHistoryRecordResult]:
        """execution_resultsの各要素についてrecord()を呼び出し、結果のリストを返す。"""
        return [self.record(execution_result, record_fn) for execution_result in execution_results]

    def record(self, execution_result: RetryExecutionResult, record_fn: RecordFn) -> RetryHistoryRecordResult:
        """1件のRetryExecutionResultについて、記録を試行するかどうかを判定し実行する。"""
        retry_result = execution_result.retry_result
        if retry_result.outcome not in _RECORDABLE_OUTCOMES:
            return RetryHistoryRecordResult(
                execution_result=execution_result,
                recorded=False,
                history_record=None,
                reason=f"retry_result.outcome={retry_result.outcome.value} is not eligible for history recording.",
            )

        original_run_id = retry_result.original_run_id
        attempt = retry_result.attempt
        history_record = record_fn(original_run_id, attempt, datetime.now())
        return RetryHistoryRecordResult(
            execution_result=execution_result,
            recorded=True,
            history_record=history_record,
            reason=f"record() was called for original_run_id={original_run_id} (attempt={attempt}).",
        )
