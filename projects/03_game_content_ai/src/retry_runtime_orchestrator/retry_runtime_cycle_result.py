"""
Retry Runtime Cycle Result（v5.3.0）

RetryRuntimeCycleResult: RetryRuntimeOrchestrator.run_once() 1回分の実行結果を
                          まとめて保持する集約データ。

設計方針:
    - run_once() が呼び出した各ステップ（Enqueue / Scheduler / Execute / Decide /
      Apply / Record）の結果をすべて保持する。run_once() が「何をしたか」を
      呼び出し元が外から確認できるようにするための集約結果であり、
      判定・加工ロジックは一切持たない（frozen dataclassのみ）。
    - scheduler_events を保持する理由：Schedulerが何件のRetry候補を返したかを
      trigger_result（Enqueue件数）と突き合わせて確認できるようにするため
      （docs/design/retry_runtime_run_once_foundation.md 参照）。
"""
from __future__ import annotations

from dataclasses import dataclass

from retry_engine import (
    RetryExecutionResult,
    RetryHistoryRecordResult,
    RetryQueueCleanupResult,
    RetryQueueRemovalResult,
    RetryQueueTerminalCleanupResult,
)
from retry_enqueue_trigger import RetryEnqueueTriggerResult
from scheduler import SchedulerEvent


@dataclass(frozen=True)
class RetryRuntimeCycleResult:
    """run_once() 1回分の実行結果を保持する集約データ。"""

    trigger_result: RetryEnqueueTriggerResult
    scheduler_events: list[SchedulerEvent]
    execution_results: list[RetryExecutionResult]
    removal_results: list[RetryQueueRemovalResult]
    cleanup_results: list[RetryQueueCleanupResult]
    terminal_cleanup_results: list[RetryQueueTerminalCleanupResult]
    history_results: list[RetryHistoryRecordResult]
