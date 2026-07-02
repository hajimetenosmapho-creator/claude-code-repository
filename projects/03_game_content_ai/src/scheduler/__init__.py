"""
Scheduler Foundation パッケージ（v2.6.0）

SchedulerJob / TriggerType / SchedulerEvent / SchedulerRepository /
InMemorySchedulerRepository / SchedulerManager / SchedulerEngine /
ClockProvider / SystemClockProvider / SchedulerConfig / Scheduler例外群 を提供する。

処理フロー（v2.6.0）:
    SchedulerJob（登録） → SchedulerManager（管理） → SchedulerRepository（保持）
        → SchedulerEngine.evaluate(jobs, now)（判定） → SchedulerEvent（生成）

設計方針:
    - src/ai/ ・src/pipeline/ を一切importしない独立パッケージとする。
      Scheduler は NewsAgent / ReviewAgent / PublishAgent を直接呼ばず、
      SchedulerEvent を生成するだけに責務を留める（Event Driven Architecture）。
      実際の処理起動は、SchedulerEventを受け取る側（既存Trigger Agent等、
      将来のScheduler実行エントリ）の責務とする
    - 本パッケージは Foundation Release（v2.6.0）であり、cron完全互換ではない
      （TriggerTypeはDAILY / INTERVAL / ONCEの3種類のみ、判定は分単位マッチング）。
      将来Releaseでの拡張候補：
        - cron対応（TriggerType.CRON の追加）
        - retry（判定・実行失敗時の再試行）
        - last_run_at（前回実行時刻の保持）
        - persistence（JSON / SQLite等への永続化）
        - Windows Task Scheduler連携
        - Linux cron連携
      これらはいずれも既存クラスへのフィールド追加・新規クラス追加で
      対応できる設計としており、本バージョンの実装は変更しない想定
"""
from .exceptions import (
    SchedulerError,
    SchedulerJobNotFoundError,
    DuplicateSchedulerJobError,
)
from .scheduler_job import TriggerType, SchedulerJob
from .scheduler_event import SchedulerEvent
from .scheduler_repository import SchedulerRepository, InMemorySchedulerRepository
from .scheduler_manager import SchedulerManager
from .scheduler_engine import ClockProvider, SystemClockProvider, SchedulerEngine
from .scheduler_config import SchedulerConfig

__all__ = [
    "SchedulerError",
    "SchedulerJobNotFoundError",
    "DuplicateSchedulerJobError",
    "TriggerType",
    "SchedulerJob",
    "SchedulerEvent",
    "SchedulerRepository",
    "InMemorySchedulerRepository",
    "SchedulerManager",
    "ClockProvider",
    "SystemClockProvider",
    "SchedulerEngine",
    "SchedulerConfig",
]
