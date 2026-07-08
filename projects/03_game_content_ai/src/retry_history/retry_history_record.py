"""
Retry History Record定義（v4.7.0）

RetryHistoryRecord: 1つのoriginal_run_idについて記録された再試行履歴を保持するデータクラス

設計方針:
    - original_run_idごとに「何回・直近いつ再試行されたか」のみを保持する
      （docs/design/retry_history_foundation.md 4章）。
    - 新しいrun_id（RetryExecutor再実行後に発行される値）は保持しない。
      RetryResult自体がこれを公開していないため（retry_result.py 設計方針参照）。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RetryHistoryRecord:
    original_run_id: str
    attempt_count: int
    last_attempt: int
    last_recorded_at: datetime
