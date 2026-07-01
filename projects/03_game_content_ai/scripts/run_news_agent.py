"""
News Agent 実行スクリプト（v2.2.0）

NewsAgent（「ニュース収集を今実行すべきか」を判断するAgent）を手動実行するための
最小限のCLIエントリスクリプト。

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/run_news_agent.py
    ./venv/Scripts/python.exe scripts/run_news_agent.py --dry-run
    ./venv/Scripts/python.exe scripts/run_news_agent.py --max-articles 3

動作の流れ:
    1. AgentConfig.from_env() で Agent Foundation の設定を読み込む
    2. AgentManager.from_config(config) で Manager を構築する
       （AI_AGENT_ENABLED=false の場合は NullAgentManager が返り、run() は空リストを返す）
    3. AgentTask(task_id="collect_news", params={...}) を組み立てる
    4. manager.run(task, dry_run=args.dry_run) を実行する

前提条件（.env 設定）:
    AI_AGENT_ENABLED=true

注意:
    --dry-run を指定した場合、実際のニュース収集（main.py の起動）は行われない。
    これは AgentExecutor（v2.0.0）の設計により構造的に保証されている
    （dry_run=True の場合、BaseAgent.act() 自体が呼び出されない）。
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
        description="News Agent 実行スクリプト（v2.2.0）"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="実際の収集は行わず、判断結果のみ確認する",
    )
    parser.add_argument(
        "--max-articles",
        type=int,
        default=None,
        metavar="N",
        help="収集実行時に main.py へ渡す --max-articles（テスト用）",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent

    config = AgentConfig.from_env(base_dir=base_dir)

    print("=" * 50)
    print("News Agent 開始")
    print("=" * 50)
    if args.dry_run:
        print("  モード: DRY RUN（実際の収集は行いません）")
    print()

    manager = AgentManager.from_config(config)

    if isinstance(manager, NullAgentManager):
        print("[情報] AI Agent基盤が無効です。")
        print("  AI_AGENT_ENABLED=true を .env に設定してください。")
        return

    params = {}
    if args.max_articles is not None:
        params["max_articles"] = args.max_articles

    task = AgentTask(task_id="collect_news", params=params)
    results = manager.run(task, dry_run=args.dry_run)

    print()
    print("=" * 50)
    print(f"News Agent 完了: {len(results)} 件のAgentを実行しました")
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


if __name__ == "__main__":
    main()
