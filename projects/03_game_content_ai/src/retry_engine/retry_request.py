"""
Retry Request定義（v3.0.0）

RetryRequest: 1回の再実行依頼を表す入力データ

設計方針:
    - attempt は呼び出し元が指定する。Retry Engine自身は過去の再試行回数を記憶・逆算しない
      （Retry History は対象外。docs/design/retry_engine_foundation.md 10章 Design Decision #7）。
    - RetryRequest は RetryManager が「再実行する」と判定した後にのみ生成され、
      RetryExecutor へ渡される（同設計書10章 Design Decision #10）。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class RetryRequest:
    run_id: str
    attempt: int
    requested_at: datetime
    dry_run: bool = False
    reason: str | None = None
