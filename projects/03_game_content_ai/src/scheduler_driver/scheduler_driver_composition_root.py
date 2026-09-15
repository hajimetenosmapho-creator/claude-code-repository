"""
Scheduler Driver Composition Root（v6.34.0、Release 6.34）

SchedulerDriverCompositionRoot: SchedulerEngine・ProductionScheduleSource・
                                 SchedulerDispatchLedger・WorkflowEngineManagerを
                                 環境変数から組み立てるComposition Root

設計方針: scripts/run_workflow_engine.py・scripts/run_retry_runtime.py（既存）と
          同じ「scripts層はBusiness Logicを持たない」原則を踏襲し、組み立てロジック
          はすべて本クラスへ集約する。
"""
from __future__ import annotations

from pathlib import Path

from ai import AgentConfig
from scheduler import SchedulerEngine
from scheduler_dispatch_ledger import JsonSchedulerDispatchLedgerStore, SchedulerDispatchLedger, SchedulerDispatchLedgerConfig
from scheduler_schedule_source import ProductionScheduleSource
from workflow_engine import WorkflowEngineConfig, WorkflowEngineManager

from .scheduler_driver_config import SchedulerDriverConfig


class SchedulerDriverStoreInitializationError(Exception):
    """dispatch ledger storeの初期化・疎通確認に失敗した場合に送出される例外。
    8.5章(5)：単一起動制約ロックを取得する前に検出することで「ロックだけ保持
    したまま何もできない」状態を回避する（from_env()はlock取得前に呼ばれる、
    scripts/run_scheduler_driver.pyの構成順序自体がこの契約を保証する）。"""


class SchedulerDriverCompositionRoot:
    def __init__(
        self,
        driver_config: SchedulerDriverConfig,
        ledger_config: SchedulerDispatchLedgerConfig,
        scheduler_engine: SchedulerEngine,
        schedule_source: ProductionScheduleSource,
        ledger: SchedulerDispatchLedger,
        workflow_engine_manager,
    ):
        self.driver_config = driver_config
        self.ledger_config = ledger_config
        self.scheduler_engine = scheduler_engine
        self.schedule_source = schedule_source
        self.ledger = ledger
        self.workflow_engine_manager = workflow_engine_manager

    @classmethod
    def from_env(cls, project_root: Path) -> "SchedulerDriverCompositionRoot":
        driver_config = SchedulerDriverConfig.from_env()
        ledger_config = SchedulerDispatchLedgerConfig.from_env(project_root)

        # 8.5章(5)：起動時のstore初期化・疎通確認。単一起動制約ロック取得前に行う
        # （本メソッド自体がscripts/run_scheduler_driver.pyのlock.acquire()より
        # 前に呼ばれる構成順序により、この契約が保証される）。
        try:
            ledger_config.store_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise SchedulerDriverStoreInitializationError(
                f"dispatch ledger storeの初期化に失敗しました（{ledger_config.store_dir}）: {e}"
            ) from e

        agent_config = AgentConfig.from_env(base_dir=project_root)
        workflow_engine_config = WorkflowEngineConfig.from_env(project_root=project_root)
        workflow_engine_manager = WorkflowEngineManager.from_config(agent_config, workflow_engine_config)

        scheduler_engine = SchedulerEngine()
        schedule_source = ProductionScheduleSource()
        ledger = SchedulerDispatchLedger(
            store=JsonSchedulerDispatchLedgerStore(ledger_config.store_dir),
            config=ledger_config,
        )

        return cls(
            driver_config=driver_config,
            ledger_config=ledger_config,
            scheduler_engine=scheduler_engine,
            schedule_source=schedule_source,
            ledger=ledger,
            workflow_engine_manager=workflow_engine_manager,
        )
