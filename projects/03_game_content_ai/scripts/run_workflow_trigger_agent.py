"""
Workflow Trigger Agent 実行スクリプト（v2.3.0）

WorkflowTriggerAgent（「Workflow（記事改善〜公開の6ステップ）を今実行すべきか」を
判断するAgent）を手動実行するための最小限のCLIエントリスクリプト。

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/run_workflow_trigger_agent.py
    ./venv/Scripts/python.exe scripts/run_workflow_trigger_agent.py --dry-run
    ./venv/Scripts/python.exe scripts/run_workflow_trigger_agent.py --article-id sample-article
    ./venv/Scripts/python.exe scripts/run_workflow_trigger_agent.py --workflow-dry-run

動作の流れ:
    1. AgentConfig.from_env() で Agent Foundation の設定を読み込む
    2. AgentManager.from_config(config) で Manager を構築する
       （AI_AGENT_ENABLED=false の場合は NullAgentManager が返り、run() は空リストを返す）
    3. AgentTask(task_id="run_workflow", params={...}) を組み立てる
    4. manager.run(task, dry_run=args.dry_run) を実行する

前提条件（.env 設定、二重ゲート）:
    AI_AGENT_ENABLED=true
    WORKFLOW_TRIGGER_AGENT_ENABLED=true
    AI_WORKFLOW_ENABLED=true（未設定時のデフォルトも true）

注意:
    - manager.run() は AgentManager に登録されているすべての Agent
      （NewsAgent / WorkflowTriggerAgent）を同じタスクで実行する。
      AI_AGENT_ENABLED=true かつ WORKFLOW_TRIGGER_AGENT_ENABLED=true の場合、
      本スクリプトを実行すると NewsAgent の decide()/act() も同時に実行される
      （run_news_agent.py を実行した場合も、同じ設定下では WorkflowTriggerAgent が
      同時に実行される）。Agentを個別に選んで実行する仕組みは現時点では存在しない。
    - --dry-run を指定した場合、実際のWorkflow実行（Publishを含む）は行われない。
      これは AgentExecutor（v2.0.0）の設計により構造的に保証されている
      （dry_run=True の場合、BaseAgent.act() 自体が呼び出されない。これは
      manager.run() に登録されている全Agentに共通で適用される）。
    - --workflow-dry-run は Agent側の --dry-run とは別概念。
      WorkflowRunner.run(dry_run=True) にそのまま渡すパラメータであり、
      act() 自体は実行される（WorkflowPipelineRunner 経由で WorkflowRunner が
      起動されるが、WorkflowRunner内部の各ステップがno-opになる）。
      --dry-run と併用した場合は act() 自体が呼ばれないため、
      --workflow-dry-run は実質的に無視される。
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
        description="Workflow Trigger Agent 実行スクリプト（v2.3.0）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="実際のWorkflow実行は行わず、判断結果のみ確認する（Agent側dry_run）",
    )
    parser.add_argument(
        "--article-id",
        default=None,
        metavar="SLUG",
        help="Workflow実行時に絞り込む記事ID（未指定: 全件）",
    )
    parser.add_argument(
        "--workflow-dry-run",
        action="store_true",
        default=False,
        help=(
            "WorkflowRunner.run(dry_run=True) にそのまま渡す（Agent側の --dry-run とは"
            "別概念。act()自体は実行されるが、Workflow内部の各ステップがno-opになる）"
        ),
    )
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent

    config = AgentConfig.from_env(base_dir=base_dir)

    print("=" * 50)
    print("Workflow Trigger Agent 開始")
    print("=" * 50)
    if args.dry_run:
        print("  モード: DRY RUN（Agent側。実際のWorkflow実行は行いません）")
    if args.workflow_dry_run:
        print("  モード: WORKFLOW DRY RUN（WorkflowRunner内部の各ステップがno-opになります）")
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
    if args.workflow_dry_run:
        params["dry_run"] = True

    task = AgentTask(task_id="run_workflow", params=params)
    results = manager.run(task, dry_run=args.dry_run)

    print()
    print("=" * 50)
    print(f"Workflow Trigger Agent 完了: {len(results)} 件のAgentを実行しました")
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

    if not any(r.agent_name == "workflow_trigger_agent" for r in results):
        print("[情報] WorkflowTriggerAgent は実行されませんでした。")
        print("  WORKFLOW_TRIGGER_AGENT_ENABLED=true と AI_WORKFLOW_ENABLED=true を")
        print("  .env に設定してください（二重ゲート）。")


if __name__ == "__main__":
    main()
