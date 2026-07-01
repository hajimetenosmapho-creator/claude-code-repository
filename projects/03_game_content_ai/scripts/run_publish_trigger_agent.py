"""
Publish Trigger Agent 実行スクリプト（v2.4.0）

PublishTriggerAgent（「AiPublishService（WordPress下書き投稿）を今実行すべきか」を
判断するAgent）を手動実行するための最小限のCLIエントリスクリプト。

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/run_publish_trigger_agent.py
    ./venv/Scripts/python.exe scripts/run_publish_trigger_agent.py --dry-run
    ./venv/Scripts/python.exe scripts/run_publish_trigger_agent.py --article-id sample-article

動作の流れ:
    1. AgentConfig.from_env() で Agent Foundation の設定を読み込む
    2. AgentManager.from_config(config) で Manager を構築する
       （AI_AGENT_ENABLED=false の場合は NullAgentManager が返り、run() は空リストを返す）
    3. AgentTask(task_id="run_publish", params={...}) を組み立てる
    4. manager.run(task, dry_run=args.dry_run) を実行する

前提条件（.env 設定、三重ゲート）:
    AI_AGENT_ENABLED=true
    PUBLISH_TRIGGER_AGENT_ENABLED=true
    AI_PUBLISH_ENABLED=true（かつ WORDPRESS_URL / WORDPRESS_USERNAME / WORDPRESS_APP_PASSWORD 設定済み）

注意:
    - 本スクリプトは AiPublishService を直接呼び出さない。
      AgentManager → PublishTriggerAgent → PublishPipelineRunner → AiPublishService
      という既存の標準構成を経由して実行される。
    - manager.run() は AgentManager に登録されているすべての Agent
      （NewsAgent / WorkflowTriggerAgent / PublishTriggerAgent）を同じタスクで実行する。
      三重ゲートが揃っている場合、本スクリプトを実行すると NewsAgent 等の
      decide()/act() も同時に実行される。Agentを個別に選んで実行する仕組みは
      現時点では存在しない（run_workflow_trigger_agent.py と同じ制約）。
    - --dry-run を指定した場合、実際のPublish実行（WordPress下書き投稿）は行われない。
      これは AgentExecutor（v2.0.0）の設計により構造的に保証されている
      （dry_run=True の場合、BaseAgent.act() 自体が呼び出されない。これは
      manager.run() に登録されている全Agentに共通で適用される）。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from ai import AgentConfig, AgentManager, NullAgentManager, AgentTask


def main():
    parser = argparse.ArgumentParser(
        description="Publish Trigger Agent 実行スクリプト（v2.4.0）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="実際のPublish実行は行わず、判断結果のみ確認する（Agent側dry_run）",
    )
    parser.add_argument(
        "--article-id",
        default=None,
        metavar="SLUG",
        help="Publish実行時に絞り込む記事ID（未指定: 全件）",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent

    config = AgentConfig.from_env(base_dir=base_dir)

    print("=" * 50)
    print("Publish Trigger Agent 開始")
    print("=" * 50)
    if args.dry_run:
        print("  モード: DRY RUN（Agent側。実際のPublish実行は行いません）")
    if args.article_id:
        print(f"  絞り込み: article_id={args.article_id}")
    print()

    manager = AgentManager.from_config(config)

    if isinstance(manager, NullAgentManager):
        print("[情報] AI Agent基盤が無効です。")
        print("  AI_AGENT_ENABLED=true を .env に設定してください。")
        return

    params = {}
    if args.article_id is not None:
        params["article_id"] = args.article_id

    task = AgentTask(task_id="run_publish", params=params)
    results = manager.run(task, dry_run=args.dry_run)

    print()
    print("=" * 50)
    print(f"Publish Trigger Agent 完了: {len(results)} 件のAgentを実行しました")
    print("=" * 50)

    for result in results:
        print(f"  Agent: {result.agent_name}")
        print(f"    判断: should_act={result.decision.should_act}")
        print(f"    理由: {result.decision.reason}")
        print(f"    実行: action_taken={result.action_taken}, success={result.success}")
        if result.error_message:
            print(f"    エラー: {result.error_message}")
        for warning in result.warnings:
            print(f"    警告: {warning}")
        print()

    if not any(r.agent_name == "publish_trigger_agent" for r in results):
        print("[情報] PublishTriggerAgent は実行されませんでした。")
        print("  PUBLISH_TRIGGER_AGENT_ENABLED=true と AI_PUBLISH_ENABLED=true")
        print("  （および WordPress認証情報）を .env に設定してください（三重ゲート）。")


if __name__ == "__main__":
    main()
