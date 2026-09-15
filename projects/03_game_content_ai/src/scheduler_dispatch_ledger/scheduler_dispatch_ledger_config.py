"""
Scheduler Dispatch Ledger設定（v6.34.0、Release 6.34）

SchedulerDispatchLedgerConfig: dispatch ledgerの保存先ディレクトリを保持するデータクラス

環境変数:
    SCHEDULER_DISPATCH_LEDGER_DIR  (default: state/scheduler_dispatch、project_root からの相対パス)

設計方針: RetryLineageConfigのdir構成パターン（store_dir / store_lock_path
          プロパティ経由でのpath解決）を踏襲する。
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class SchedulerDispatchLedgerConfig:
    ledger_dir: Path
    store_lock_timeout_seconds: float = 5.0

    @classmethod
    def from_env(cls, project_root: Path) -> "SchedulerDispatchLedgerConfig":
        dir_name = os.environ.get("SCHEDULER_DISPATCH_LEDGER_DIR", "state/scheduler_dispatch")
        return cls(ledger_dir=project_root / dir_name)

    @property
    def store_dir(self) -> Path:
        return self.ledger_dir / "entries"

    @property
    def store_lock_path(self) -> Path:
        return self.ledger_dir / ".store.lock"
