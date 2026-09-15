"""
Production Schedule Source（v6.34.0、Release 6.34）

ProductionScheduleSource: production SchedulerJob定義を保持する唯一の供給元

設計方針（docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md 9章）:
    - MVP初期実装では、scripts/run_workflow_engine.py の build_demo_job() が
      ローカルに保持していたJob定義（job_id="workflow_engine_demo_daily"、
      DAILY 09:00）を、production Job定義の唯一の供給元として本パッケージへ
      移設する。job_id・name・trigger_type・scheduleはいずれも既存値を完全に
      維持する（挙動を変更しない、Roadmap 6.34「production schedule sourceの
      一元化」要求への対応。9.1章）。
    - `scripts/run_workflow_engine.py`（既存、--job-id手動経路を除く）と、新設
      `scripts/run_scheduler_driver.py`（v6.34.0）の両方が、本クラスを唯一の
      Job定義供給元として使用する。
    - 将来的な複数Job・設定ファイル化はjobs()の内部実装のみを変更すればよく、
      呼び出し元のシグネチャは変更不要（拡張性）。
    - job_idに予約プレフィックス"retry:"を用いない、metadataに予約キー
      "retry_candidate"を含めない、という2つの運用規約を守ること
      （docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md
      16章 Design Decision J・25章R3）。
"""
from __future__ import annotations

from scheduler import SchedulerJob, TriggerType

PRODUCTION_JOB_ID = "workflow_engine_demo_daily"
PRODUCTION_JOB_SCHEDULE = "09:00"


class ProductionScheduleSource:
    """production SchedulerJob定義の唯一の供給元。"""

    def jobs(self) -> list[SchedulerJob]:
        return [
            SchedulerJob(
                job_id=PRODUCTION_JOB_ID,
                name="Workflow Engine Demo (Daily 09:00)",
                trigger_type=TriggerType.DAILY,
                schedule=PRODUCTION_JOB_SCHEDULE,
            )
        ]
