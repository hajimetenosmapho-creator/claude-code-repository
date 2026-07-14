"""
Retry Runtime Cycle Logger（v6.2.0）

RetryRuntimeCycleLogger: Retry Runtimeの1サイクル分の実行結果を、JSON Lines
                          形式で1レコードとしてログファイルへ追記するだけの、
                          Retryドメインを一切知らない汎用コンポーネント。

設計方針（docs/design/retry_runtime_structured_loop_logging_foundation.md）:
    - 本クラスの責務は「JSON Linesへ1レコード追記すること」のみに限定する。
      サイクル番号のカウント・実行順序・ループ・スケジューリングはいずれも
      関知しない（呼び出し元がcycle_numberを都度渡す）。
    - RetryRuntimeLock / RetryRuntimeShutdown / RetryRuntimeLoop /
      RetryRuntimeOrchestrator / RetryManager等、他のretry_*パッケージの
      いずれにも依存しない（RetryRuntimeCycleResultの型参照のみ）。
    - ログ書き込みの失敗（ディスク容量不足・権限エラー等）はRetry Runtime本体
      を停止させない。ベストエフォートとし、例外を送出せずstderrへWARNINGを
      出力するのみに留める（Runtime Failure Policy。Exit Code Policy
      （docs/design/retry_runtime_script_entry_point_foundation.md 2.4節）とは
      区別する）。
    - JSONスキーマは本Releaseで固定する。将来の変更はフィールド追加のみを
      基本方針とし、既存フィールドの意味変更は行わない（Logging Policy）。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from retry_runtime_orchestrator import RetryRuntimeCycleResult


class RetryRuntimeCycleLogger:
    """
    1サイクル分の実行結果をJSON Lines形式で追記するだけの、Retryドメインを
    一切知らないログコンポーネント。
    """

    def __init__(self, log_path: Path):
        self.log_path = log_path

    def log_cycle(
        self,
        cycle_number: int,
        result: RetryRuntimeCycleResult,
        dry_run: bool = False,
    ) -> None:
        """
        1サイクル分の実行結果を1行のJSONレコードとしてlog_pathへ追記する。

        親ディレクトリが存在しない場合は作成する。ログファイルが存在しない
        場合は新規作成し、存在する場合は末尾へ追記する。書き込みに失敗した
        場合は例外を送出せず、stderrへWARNINGメッセージを出力したうえで
        呼び出し元（Retry Runtime本体）の処理を継続させる。
        """
        trigger_result = result.trigger_result
        record = {
            "cycle_number": cycle_number,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dry_run": dry_run,
            "enqueue_scanned": trigger_result.scanned,
            "enqueue_enqueued": trigger_result.enqueued,
            "enqueue_skipped_existing": trigger_result.skipped_existing,
            "enqueue_skipped_status": trigger_result.skipped_status,
            "enqueue_skipped_history": trigger_result.skipped_history,
            "enqueue_failed": trigger_result.failed,
            "scheduler_candidates": len(result.scheduler_events),
            "execution_executed": len(result.execution_results),
            "removal_removed": len(result.removal_results),
            "cleanup_cleaned": len(result.cleanup_results),
            "terminal_cleanup_cleaned": len(result.terminal_cleanup_results),
            "history_recorded": len(result.history_results),
        }

        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except OSError as e:
            print(f"WARNING: Failed to write runtime log: {e}", file=sys.stderr)
