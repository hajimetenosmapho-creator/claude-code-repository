"""
Retry Runtime Log Reader（v6.3.0）

RetryRuntimeLogReader: .run/retry_runtime_log.jsonl（v6.2.0 RetryRuntimeCycleLogger
                        が書き込むJSON Linesログ）を読み取り、RetryRuntimeLogRecord
                        のリストへ変換するだけの、読み取り専用コンポーネント。

設計方針（docs/design/retry_metrics_foundation.md 9章 Failure Policy）:
    - ログファイルが存在しない場合は例外を送出せず空リストを返す（Retry Runtime
      未実行の状態は正当なシステム状態であり、エラーではない）
    - 個々の行のパース失敗（JSON自体が壊れている、または期待するフィールドが
      欠けている）は、その行のみスキップしstderrへWARNINGを出力して処理を
      継続する（ベストエフォート。クラッシュ時の不完全な末尾行を許容するため）
    - ファイル自体が読めない場合（権限エラー等のOSError）は例外をそのまま
      送出する（fail-fast。環境異常を隠蔽しない）
    - 他のretry_*パッケージのいずれにも依存しない（ファイルパスとJSON Schemaの
      「形」のみを契約として扱う）
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from .retry_runtime_log_record import RetryRuntimeLogRecord


class RetryRuntimeLogReader:
    """.run/retry_runtime_log.jsonl を読み取り、RetryRuntimeLogRecordのリストへ変換するだけの読み取り専用コンポーネント。"""

    def __init__(self, log_path: Path):
        self.log_path = log_path

    def read(self) -> list[RetryRuntimeLogRecord]:
        """
        log_path から JSON Lines を読み取り、RetryRuntimeLogRecord のリストを返す。

        ファイルが存在しない場合は空リストを返す。個々の行のパースに失敗した
        場合は、その行のみスキップしstderrへWARNINGを出力して処理を継続する。
        ファイル自体が読めない場合（OSError）は例外をそのまま送出する。
        """
        try:
            file_handle = open(self.log_path, "r", encoding="utf-8")
        except FileNotFoundError:
            # ファイルが存在しない＝Retry Runtime未実行の正当な状態（正常系）。
            # これ以外のOSError（権限エラー・パス構造異常等）はfail-fastで
            # そのまま伝播させる（Path.exists()はOSErrorを内部で握りつぶして
            # Falseを返してしまい、この区別ができないため使わない）。
            return []

        records: list[RetryRuntimeLogRecord] = []
        with file_handle as f:
            for line_number, line in enumerate(f, start=1):
                stripped = line.strip()
                if not stripped:
                    continue
                try:
                    raw = json.loads(stripped)
                    records.append(
                        RetryRuntimeLogRecord(
                            cycle_number=raw["cycle_number"],
                            timestamp=raw["timestamp"],
                            dry_run=raw["dry_run"],
                            enqueue_scanned=raw["enqueue_scanned"],
                            enqueue_enqueued=raw["enqueue_enqueued"],
                            enqueue_skipped_existing=raw["enqueue_skipped_existing"],
                            enqueue_skipped_status=raw["enqueue_skipped_status"],
                            enqueue_skipped_history=raw["enqueue_skipped_history"],
                            enqueue_failed=raw["enqueue_failed"],
                            scheduler_candidates=raw["scheduler_candidates"],
                            execution_executed=raw["execution_executed"],
                            removal_removed=raw["removal_removed"],
                            cleanup_cleaned=raw["cleanup_cleaned"],
                            terminal_cleanup_cleaned=raw["terminal_cleanup_cleaned"],
                            history_recorded=raw["history_recorded"],
                        )
                    )
                except (json.JSONDecodeError, KeyError, TypeError) as e:
                    # KeyError/TypeErrorも「壊れた行」として扱う（クラッシュ時の
                    # 不完全な末尾行は、妥当なJSONだがフィールド欠落の形でも
                    # 発生し得るため）。
                    print(
                        f"WARNING: Failed to parse runtime log line {line_number}: {e}",
                        file=sys.stderr,
                    )
                    continue
        return records
