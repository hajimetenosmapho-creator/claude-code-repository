"""
Retry History Manager（v4.7.0）

RetryHistoryManager: original_run_idごとの再試行履歴を記録・参照するだけの最小基盤。
                      record/get/has_historyの3操作のみを提供し、Retry可否判定・
                      Retry実行・Queue操作はいずれも行わない。

設計方針:
    - retry_queueと同型の独立した葉パッケージ。他のどのsrc/*パッケージも
      importしない、標準ライブラリのみに依存する
      （docs/design/retry_history_foundation.md 5章）。
    - 記録のみを責務とする。「既にmax_attemptsに達したか」「再enqueueを
      止めるべきか」といった判定はここでは行わない（次Release以降の消費側の
      責務。Foundation First）。
    - 呼び出し元へ返すRetryHistoryRecordは常にコピー（dataclasses.replace()）
      であり、呼び出し元が書き換えても内部ストアには影響しない
      （RetryQueueManagerと同じ方針）。
    - スレッド安全性は保証しない（既存Manager群と同じく単一プロセス・
      単一スレッドでの利用を前提とする）。
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from .retry_history_record import RetryHistoryRecord


class RetryHistoryManager:
    """Retry History全体の起動口。original_run_idごとの再試行履歴を記録・参照する。"""

    def __init__(self):
        self._records: dict[str, RetryHistoryRecord] = {}

    def record(self, original_run_id: str, attempt: int, recorded_at: datetime) -> RetryHistoryRecord:
        """
        original_run_idについて1回分の再試行を記録する。

        既に記録が存在する場合はattempt_countをインクリメントし、
        last_attempt / last_recorded_atを最新の値に更新する。
        初回の場合はattempt_count=1の新規レコードを作成する。
        """
        existing = self._records.get(original_run_id)
        attempt_count = existing.attempt_count + 1 if existing is not None else 1
        record = RetryHistoryRecord(
            original_run_id=original_run_id,
            attempt_count=attempt_count,
            last_attempt=attempt,
            last_recorded_at=recorded_at,
        )
        self._records[original_run_id] = record
        return replace(record)

    def get(self, original_run_id: str) -> RetryHistoryRecord | None:
        """指定original_run_idの履歴を返す。記録がない場合はNoneを返す。"""
        record = self._records.get(original_run_id)
        return replace(record) if record is not None else None

    def has_history(self, original_run_id: str) -> bool:
        """指定original_run_idについて記録が存在するか返す。"""
        return original_run_id in self._records
