"""
Scheduler Foundation パッケージ（v2.6.0 / v3.4.0でRetry Scheduler Wiring・
v3.6.0でRetry Scheduler Decision Wiring・v3.7.0でRetry Scheduler Event
Integrationを追加）

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
        - last_run_at（前回実行時刻の保持）
        - persistence（JSON / SQLite等への永続化）
        - Windows Task Scheduler連携
        - Linux cron連携
      これらはいずれも既存クラスへのフィールド追加・新規クラス追加で
      対応できる設計としており、本バージョンの実装は変更しない想定
    - （v3.4.0）SchedulerEngine が RetrySchedulerSource / NullRetrySchedulerSource
      （src/retry_scheduler_source/、v3.3.0）をConstructor Injectionで保持できる
      ようになった（Retry Scheduler Wiring）。count_pending_retries() /
      list_pending_retries() を通じてRetry Queueの状態を読み取れるが、
      evaluate() / run_due() の判定ロジックには一切影響しない（読み取りのみ）。
      dequeue() / remove() の呼び出し・Retry Engineの起動・自動Retry実行は
      本パッケージの責務外のまま（詳細は docs/design/retry_scheduler_wiring.md）
    - （v3.6.0）SchedulerEngine が RetrySchedulerDecision（src/retry_scheduler_decision/、
      v3.5.0）をConstructor Injectionで保持できるようになった（Retry Scheduler
      Decision Wiring）。select_candidates() / select_next_candidate() を通じて
      「次に処理すべき候補」を読み取れるが、evaluate() / run_due() の判定ロジックには
      一切影響しない（読み取りのみ）。SchedulerEngine は RetrySchedulerDecision を
      自ら生成せず、呼び出し元が組み立てて渡す。dequeue() / remove() の呼び出し・
      Retry Engineの起動・自動Retry実行・SchedulerEventへの組み込みは本パッケージの
      責務外のまま（詳細は docs/design/retry_scheduler_decision_wiring.md）
    - （v3.7.0）evaluate() / run_due() が、select_candidates()（v3.6.0）の
      戻り値（Retry候補）を SchedulerEvent として出力に含められるようになった
      （Retry Scheduler Event Integration）。retry_decision が None の場合は
      本Release前とまったく同じ結果を返す（後方互換性維持）。Retry候補由来の
      SchedulerEvent の job_id は "retry:" + run_id、metadata は候補オブジェクトを
      そのまま格納する（{"retry_candidate": 候補}、in-memory観測用途限定）。
      Retry Engineの起動・dequeue() / remove() の呼び出し・Retry Queueへの
      書き込みは本パッケージの責務外のまま（詳細は
      docs/design/retry_scheduler_event_integration.md）
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
