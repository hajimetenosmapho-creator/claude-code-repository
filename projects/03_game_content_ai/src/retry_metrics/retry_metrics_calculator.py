"""
Retry Metrics Calculator（v6.3.0）

RetryMetricsCalculator: RetryRuntimeLogRecordのリストから集計値
                         （RetryMetricsSnapshot）を計算するだけの、状態を
                         持たないコンポーネント。

設計方針（docs/design/retry_metrics_foundation.md 7章 Responsibility・10章 DI構成）:
    - ファイルI/Oは一切行わない（RetryRuntimeLogReaderの責務）
    - 無引数コンストラクタ・calculate(records) -> RetryMetricsSnapshotという
      純粋関数的API（RetryQueueUpdateDecider等の既存Decider系コンポーネント
      と同型）
    - 空リストを渡されても例外を送出せず、cycle_count=0のSnapshotを返す
      （Null Objectパターンではなく「0件という正常なデータ」として扱う）
    - recordsの時系列順を仮定しない（period_start/period_endはmin/maxで
      算出する。timestampはISO8601（UTC）形式のため文字列の辞書順比較が
      時系列順と一致する）
    - enqueue_success_ratioはEnqueue段階の成功率であり、Retry実行そのものの
      成否（RetryOutcome）を表す指標ではない（14章 Risks）
"""
from __future__ import annotations

from .retry_metrics_snapshot import RetryMetricsSnapshot
from .retry_runtime_log_record import RetryRuntimeLogRecord


class RetryMetricsCalculator:
    """RetryRuntimeLogRecordのリストからRetryMetricsSnapshotを計算するだけの、状態を持たないコンポーネント。"""

    def calculate(self, records: list[RetryRuntimeLogRecord]) -> RetryMetricsSnapshot:
        """
        records（時系列順を仮定しない）から集計値を計算しRetryMetricsSnapshotを返す。
        空リストの場合も例外を送出せず、cycle_count=0のSnapshotを返す。
        """
        cycle_count = len(records)

        if cycle_count == 0:
            return RetryMetricsSnapshot(
                cycle_count=0,
                period_start=None,
                period_end=None,
                dry_run_cycle_count=0,
                enqueue_scanned_total=0,
                enqueue_enqueued_total=0,
                enqueue_skipped_existing_total=0,
                enqueue_skipped_status_total=0,
                enqueue_skipped_history_total=0,
                enqueue_failed_total=0,
                scheduler_candidates_total=0,
                execution_executed_total=0,
                removal_removed_total=0,
                cleanup_cleaned_total=0,
                terminal_cleanup_cleaned_total=0,
                history_recorded_total=0,
                enqueue_success_ratio=None,
            )

        timestamps = [record.timestamp for record in records]
        enqueue_scanned_total = sum(record.enqueue_scanned for record in records)
        enqueue_enqueued_total = sum(record.enqueue_enqueued for record in records)

        return RetryMetricsSnapshot(
            cycle_count=cycle_count,
            period_start=min(timestamps),
            period_end=max(timestamps),
            dry_run_cycle_count=sum(1 for record in records if record.dry_run),
            enqueue_scanned_total=enqueue_scanned_total,
            enqueue_enqueued_total=enqueue_enqueued_total,
            enqueue_skipped_existing_total=sum(record.enqueue_skipped_existing for record in records),
            enqueue_skipped_status_total=sum(record.enqueue_skipped_status for record in records),
            enqueue_skipped_history_total=sum(record.enqueue_skipped_history for record in records),
            enqueue_failed_total=sum(record.enqueue_failed for record in records),
            scheduler_candidates_total=sum(record.scheduler_candidates for record in records),
            execution_executed_total=sum(record.execution_executed for record in records),
            removal_removed_total=sum(record.removal_removed for record in records),
            cleanup_cleaned_total=sum(record.cleanup_cleaned for record in records),
            terminal_cleanup_cleaned_total=sum(record.terminal_cleanup_cleaned for record in records),
            history_recorded_total=sum(record.history_recorded for record in records),
            enqueue_success_ratio=(
                enqueue_enqueued_total / enqueue_scanned_total
                if enqueue_scanned_total > 0
                else None
            ),
        )
