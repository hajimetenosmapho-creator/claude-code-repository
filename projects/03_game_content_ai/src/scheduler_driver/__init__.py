"""
Scheduler Driver パッケージ（v6.34.0、Release 6.34）

SchedulerEngine（v2.6.0、無改修）を定期的に駆動し、production workflowへ配線する
loop driverを構成するコンポーネント群。

処理フロー:
    ProductionScheduleSource.jobs()（Job定義） -> SchedulerEngine.evaluate()（判定、
    無改修） -> Design Decision J filter（retry候補除外） -> SchedulerDispatchLedger
    経由のfail-closed claim -> WorkflowEngineManager.run()（dispatch） -> confirm()

設計方針（docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md）:
    - src/scheduler/・src/workflow_engine/・src/retry_lineage/等の既存パッケージは
      一切変更しない（21章 Zero-Diff対象）。
    - RetryRuntimeLock/RetryRuntimeLoop/RetryRuntimeShutdown（src/retry_runtime_*/）
      はコード変更ゼロのまま、scripts/run_scheduler_driver.py 側で再利用する
      （13章 Design Decision G）。
"""
from .scheduler_driver_composition_root import SchedulerDriverCompositionRoot, SchedulerDriverStoreInitializationError
from .scheduler_driver_config import SchedulerDriverConfig
from .scheduler_driver_cycle_result import DispatchOutcome, SchedulerDriverCycleResult
from .scheduler_driver_dispatch_filter import RESERVED_RETRY_CANDIDATE_METADATA_KEY, _select_dispatchable_events
from .scheduler_driver_event_identity import build_event_identity, build_occurrence_minute
from .scheduler_driver_lock_integrity import LockIntegrityViolationError, _release_if_owned, _verify_lock_ownership
from .scheduler_driver_orchestrator import SchedulerDriverOrchestrator

__all__ = [
    "SchedulerDriverCompositionRoot",
    "SchedulerDriverStoreInitializationError",
    "SchedulerDriverConfig",
    "DispatchOutcome",
    "SchedulerDriverCycleResult",
    "RESERVED_RETRY_CANDIDATE_METADATA_KEY",
    "_select_dispatchable_events",
    "build_event_identity",
    "build_occurrence_minute",
    "LockIntegrityViolationError",
    "_verify_lock_ownership",
    "_release_if_owned",
    "SchedulerDriverOrchestrator",
]
