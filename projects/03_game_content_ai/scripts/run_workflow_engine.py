"""
Workflow Engine 実行スクリプト（v2.7.0）

Scheduler（v2.6.0）の判定結果（SchedulerEvent）を受け取り、Workflow Engine
（NewsAgent → ReviewTriggerAgent → PublishTriggerAgentの直列実行）を起動する
手動実行用のCLIエントリスクリプト。

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/run_workflow_engine.py
    ./venv/Scripts/python.exe scripts/run_workflow_engine.py --dry-run
    ./venv/Scripts/python.exe scripts/run_workflow_engine.py --job-id manual-run

引数:
    --dry-run    Workflow Engine全体をdry_run実行する
                 （各ステップのAgentは decide() のみ行い、act() は呼ばれない）
    --job-id     Scheduler判定をスキップし、指定したjob_idでWorkflowEngineEventを
                 その場で合成し、直接WorkflowEngineManager.run()を呼び出す
                 （動作確認・手動起動用。SchedulerEngineの評価を経由しない）

動作の流れ（デフォルト、Scheduler経由）:
    1. InMemorySchedulerRepository() を生成し、SchedulerManager経由で
       固定・最小限のデモ用SchedulerJobを1件だけ登録する
       （job_id="workflow_engine_demo_daily", trigger_type=DAILY, schedule="09:00"）。
       複数Job・設定ファイル化・動的登録はFoundation Releaseの対象外
       （docs/design/workflow_engine_foundation.md 10章・12章「責務範囲の明文化」）
    2. SchedulerEngine().run_due(jobs) で実行対象のSchedulerEventを取得する（v2.6.0、無改修）
    3. 対象がなければ「実行対象なし」を表示して終了する
    4. 対象があれば、SchedulerEventの各フィールドをそのままコピーして
       WorkflowEngineEvent(source=SOURCE_SCHEDULER, ...) を構築する（6章の対応表）
    5. WorkflowEngineManager.from_config(agent_config, workflow_engine_config)
       .run(event, dry_run=args.dry_run) を実行する

動作の流れ（--job-id指定時、Scheduler判定を経由しない）:
    1. WorkflowEngineEvent(job_id=args.job_id, source=SOURCE_MANUAL,
       triggered_at=datetime.now(),
       trigger_reason="Manual invocation via --job-id.") を直接構築する（6章の対応表）
    2. SchedulerConfig / SchedulerManager / SchedulerEngine はいずれも呼び出さない
    3. WorkflowEngineManager.from_config(...).run(event, dry_run=args.dry_run) を実行する

前提条件（.env設定、二重ゲート）:
    AI_AGENT_ENABLED=true
    WORKFLOW_ENGINE_ENABLED=true

    加えて、Review/Publishステップを実際に動かす場合は以下も必要:
    REVIEW_TRIGGER_AGENT_ENABLED=true
    PUBLISH_TRIGGER_AGENT_ENABLED=true（+ AiPublishConfigの認証情報3点）

注意:
    - 本スクリプトは NewsAgent / ReviewTriggerAgent / PublishTriggerAgent を
      直接importしない。WorkflowEngineManager経由でのみ間接的に利用する。
    - SCHEDULER_ENABLED は本スクリプトの動作条件には含めない
      （v2.6.0のSchedulerConfigはSchedulerEngine/SchedulerManager自体の有効・無効を
      制御するものではなく将来のOS連携機能向けの設定であるため）。
    - --dry-run を指定した場合、実際のNews収集・レビューレポート生成・
      WordPress下書き投稿はいずれも行われない。
    - 【運用上の制約】本スクリプトと scripts/run_news_agent.py /
      scripts/run_review_trigger_agent.py / scripts/run_publish_trigger_agent.py /
      scripts/run_workflow_trigger_agent.py など、AgentManager経由の既存script群を
      同時に実行しないこと。decide()からact()完了までの間にロックがないため、
      同時実行するとNews収集・レビューレポート生成・WordPress下書き投稿などが
      二重に発生するリスクがある（docs/design/workflow_engine_foundation.md 13.1節）。
"""
import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from ai import AgentConfig
from scheduler import (
    InMemorySchedulerRepository,
    SchedulerEngine,
    SchedulerJob,
    SchedulerManager,
    TriggerType,
)
from workflow_engine import (
    SOURCE_MANUAL,
    SOURCE_SCHEDULER,
    NullWorkflowEngineManager,
    WorkflowEngineConfig,
    WorkflowEngineEvent,
    WorkflowEngineManager,
)

DEMO_JOB_ID = "workflow_engine_demo_daily"
DEMO_JOB_SCHEDULE = "09:00"
MANUAL_TRIGGER_REASON = "Manual invocation via --job-id."


def build_demo_job() -> SchedulerJob:
    """
    Foundation Releaseで扱う固定・最小限（1件のみ）のデモJob。

    複数Job・設定ファイル化・動的登録はFuture Extensions（対象外）。
    """
    return SchedulerJob(
        job_id=DEMO_JOB_ID,
        name="Workflow Engine Demo (Daily 09:00)",
        trigger_type=TriggerType.DAILY,
        schedule=DEMO_JOB_SCHEDULE,
    )


def resolve_event(args) -> WorkflowEngineEvent | None:
    """
    --job-id 指定時は手動経路、未指定時は Scheduler 経由で WorkflowEngineEvent を構築する。

    Scheduler経由で実行対象のJobがない場合は None を返す。
    """
    if args.job_id is not None:
        return WorkflowEngineEvent(
            job_id=args.job_id,
            source=SOURCE_MANUAL,
            triggered_at=datetime.now(),
            trigger_reason=MANUAL_TRIGGER_REASON,
        )

    repository = InMemorySchedulerRepository()
    scheduler_manager = SchedulerManager(repository)
    scheduler_manager.register_job(build_demo_job())

    jobs = scheduler_manager.list_jobs()
    events = SchedulerEngine().run_due(jobs)

    if not events:
        print("[情報] 実行対象のJobはありません（現在時刻がデモJobのスケジュールと一致しません）。")
        print(f"  デモJob: job_id={DEMO_JOB_ID}, schedule={DEMO_JOB_SCHEDULE}（DAILY）")
        print("  --job-id オプションで手動起動することもできます。")
        return None

    scheduler_event = events[0]
    return WorkflowEngineEvent(
        job_id=scheduler_event.job_id,
        source=SOURCE_SCHEDULER,
        triggered_at=scheduler_event.execute_time,
        trigger_reason=scheduler_event.trigger_reason,
        metadata=dict(scheduler_event.metadata),
    )


def print_result(result) -> None:
    print()
    print("=" * 50)
    print(
        f"Workflow Engine 完了: overall_success={result.overall_success}, "
        f"stopped_early={result.stopped_early}"
    )
    print("=" * 50)

    for step_result in result.steps:
        print(f"  ステップ: {step_result.step.value}")
        print(f"    executed={step_result.executed}, success={step_result.success}")
        if step_result.skipped_reason:
            print(f"    スキップ理由: {step_result.skipped_reason}")
        if step_result.agent_result is not None:
            print(f"    判断: should_act={step_result.agent_result.decision.should_act}")
            print(f"    理由: {step_result.agent_result.decision.reason}")
            if step_result.agent_result.error_message:
                print(f"    エラー: {step_result.agent_result.error_message}")
        print()

    for warning in result.warnings:
        print(f"  警告: {warning}")


def main():
    parser = argparse.ArgumentParser(
        description="Workflow Engine 実行スクリプト（v2.7.0）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Workflow Engine全体をdry_run実行する（各ステップのact()は呼ばれない）",
    )
    parser.add_argument(
        "--job-id",
        default=None,
        metavar="JOB_ID",
        help="Scheduler判定をスキップし、指定したjob_idで直接Workflow Engineを起動する",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent

    agent_config = AgentConfig.from_env(base_dir=base_dir)
    workflow_engine_config = WorkflowEngineConfig.from_env(project_root=base_dir)

    print("=" * 50)
    print("Workflow Engine 開始")
    print("=" * 50)
    if args.dry_run:
        print("  モード: DRY RUN（実際のNews収集・レビューレポート生成・WordPress下書き投稿は行いません）")
    print()

    manager = WorkflowEngineManager.from_config(agent_config, workflow_engine_config)

    if isinstance(manager, NullWorkflowEngineManager):
        print("[情報] Workflow Engineが無効です。")
        print(
            "  AI_AGENT_ENABLED=true と WORKFLOW_ENGINE_ENABLED=true を"
            " .env に設定してください（二重ゲート）。"
        )
        return

    event = resolve_event(args)
    if event is None:
        return

    result = manager.run(event, dry_run=args.dry_run)
    print_result(result)


if __name__ == "__main__":
    main()
