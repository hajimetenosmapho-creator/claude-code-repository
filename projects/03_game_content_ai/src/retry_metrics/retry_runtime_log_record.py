"""
Retry Runtime Log Record（v6.3.0）

RetryRuntimeLogRecord: .run/retry_runtime_log.jsonl の1行（v6.2.0固定スキーマ）
                        をミラーリングした不変の値オブジェクト。

設計方針（docs/design/retry_metrics_foundation.md 6.3節）:
    - v6.2.0で確定したJSON Schema（RetryRuntimeCycleLogger.log_cycle()が
      書き込む15フィールド）をそのままミラーリングする
    - retry_runtime_logging側の定義を直接importせず、独自にdataclassを
      定義し直す（型参照ではなく契約（shape一致）による疎結合。
      docs/design/retry_metrics_foundation.md 12章 Alternatives #3）
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryRuntimeLogRecord:
    """.run/retry_runtime_log.jsonl の1行（v6.2.0固定スキーマ）をミラーリングした値オブジェクト。"""

    cycle_number: int
    timestamp: str
    dry_run: bool
    enqueue_scanned: int
    enqueue_enqueued: int
    enqueue_skipped_existing: int
    enqueue_skipped_status: int
    enqueue_skipped_history: int
    enqueue_failed: int
    scheduler_candidates: int
    execution_executed: int
    removal_removed: int
    cleanup_cleaned: int
    terminal_cleanup_cleaned: int
    history_recorded: int
