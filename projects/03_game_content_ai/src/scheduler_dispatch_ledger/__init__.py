"""
Scheduler Dispatch Ledger パッケージ（v6.34.0、Release 6.34）

Scheduler Driver（v6.34.0）が、stable event identity（job_id x occurrence_minute）
ごとのdispatch記録をdurableに保持するための独立パッケージ。

設計方針（docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md 8章）:
    - src/retry_lineage/ 等のRetry系パッケージを一切importしない独立パッケージとする
      （Design Decision H：Scheduler DriverとRetry Runtimeのownership分離、14章）。
    - 3-phase（CLAIMED / CONFIRMED / RECOVERY_REQUIRED）、owner_token authorityなし
      （8.4章：single-active-driver制約下での意図的な単純化）。
    - claim()のacknowledged=False条件（recordが既に存在する場合）のみが、
      duplicate dispatch防止の唯一の権威となる不変条件である（8章・25章R2）。
"""
from .dispatch_ledger_entry import DispatchLedgerEntry
from .dispatch_phase import DispatchPhase
from .scheduler_dispatch_ledger import SchedulerDispatchLedger, SchedulerDispatchLedgerReconcileError
from .scheduler_dispatch_ledger_config import SchedulerDispatchLedgerConfig
from .scheduler_dispatch_ledger_results import ClaimResult, ReconcileSummary
from .scheduler_dispatch_ledger_store import (
    JsonSchedulerDispatchLedgerStore,
    SchedulerDispatchLedgerStore,
    SchedulerDispatchLedgerStoreReadError,
)
from .scheduler_dispatch_ledger_store_lock import (
    SchedulerDispatchLedgerStoreLock,
    SchedulerDispatchLedgerStoreLockError,
)

__all__ = [
    "DispatchLedgerEntry",
    "DispatchPhase",
    "SchedulerDispatchLedger",
    "SchedulerDispatchLedgerReconcileError",
    "SchedulerDispatchLedgerConfig",
    "ClaimResult",
    "ReconcileSummary",
    "SchedulerDispatchLedgerStore",
    "JsonSchedulerDispatchLedgerStore",
    "SchedulerDispatchLedgerStoreReadError",
    "SchedulerDispatchLedgerStoreLock",
    "SchedulerDispatchLedgerStoreLockError",
]
