"""
Null Retry History Manager（v4.7.0）

NullRetryHistoryManager: 再試行履歴を記録しないダミー実装。すべての操作が
                          副作用なく「記録なし」相当の結果を返す。

設計方針:
    - RetryHistoryManagerと継承関係を持たない（Duck Typing。retry_queueの
      RetryQueueManager/NullRetryQueueManagerと同じ関係とする）。
    - 実データ（_records）を一切保持しない。
    - record()はExecutionHistoryManager（NullExecutionHistoryManager.start_run()）と
      同じ方針でNoneを返す（「記録されなかった」ことを明示する）。
"""
from __future__ import annotations

from datetime import datetime

from .retry_history_record import RetryHistoryRecord


class NullRetryHistoryManager:
    """再試行履歴を記録しないダミー実装。すべてno-op。"""

    def record(self, original_run_id: str, attempt: int, recorded_at: datetime) -> "RetryHistoryRecord | None":
        return None

    def get(self, original_run_id: str) -> "RetryHistoryRecord | None":
        return None

    def has_history(self, original_run_id: str) -> bool:
        return False
