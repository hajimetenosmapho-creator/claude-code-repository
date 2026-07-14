"""
Retry Metrics Snapshot（v6.3.0）

RetryMetricsSnapshot: RetryMetricsCalculatorが計算した集計結果を表す、
                       Immutable（読み取り専用）な値オブジェクト。

設計方針（docs/design/retry_metrics_foundation.md 6.4節）:
    - frozen=Trueのdataclassとして実装し、フィールドの再代入自体を構造的に
      禁止する（生成後は変更しない）
    - 自分自身を更新する手段（setter・update()メソッド等）を一切持たない。
      新しい集計結果が必要な場合はRetryMetricsCalculator.calculate()を
      再度呼び出し、新しいインスタンスを生成する
    - 将来のRetry Monitoring FoundationはこのSnapshotを参照するだけであり、
      更新は一切行わない（11.1節）
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryMetricsSnapshot:
    """RetryMetricsCalculatorが計算した集計結果を表すImmutableな値オブジェクト。"""

    cycle_count: int
    period_start: str | None
    period_end: str | None
    dry_run_cycle_count: int
    enqueue_scanned_total: int
    enqueue_enqueued_total: int
    enqueue_skipped_existing_total: int
    enqueue_skipped_status_total: int
    enqueue_skipped_history_total: int
    enqueue_failed_total: int
    scheduler_candidates_total: int
    execution_executed_total: int
    removal_removed_total: int
    cleanup_cleaned_total: int
    terminal_cleanup_cleaned_total: int
    history_recorded_total: int
    enqueue_success_ratio: float | None  # enqueue_enqueued_total / enqueue_scanned_total（Enqueue段階の成功率。Retry実行自体のRetryOutcome成功率ではない）
