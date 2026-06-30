"""
AI ワークフロースクリプト（v1.20.0）

v1.14〜v1.19 で構築した AI パイプライン全体を 1 コマンドで連鎖実行する。

実行するステップ（デフォルト: 全ステップ）:
    1. AI 改善提案         （v1.14）
    2. 改善提案レビュー    （v1.15）
    3. AI リライト         （v1.16）
    4. リライトレビュー    （v1.17）
    5. AI 公開             （v1.18）
    6. 公開レビュー        （v1.19）

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/run_ai_workflow.py
    ./venv/Scripts/python.exe scripts/run_ai_workflow.py --dry-run
    ./venv/Scripts/python.exe scripts/run_ai_workflow.py --article-id ps6-announced-20260630
    ./venv/Scripts/python.exe scripts/run_ai_workflow.py --steps improvement,rewrite,publish
    ./venv/Scripts/python.exe scripts/run_ai_workflow.py --continue-on-error

動作の流れ:
    1. WorkflowConfig を構築する
    2. WorkflowRunner.from_config() でパイプラインを組み立てる
    3. WorkflowRunner.run() で全ステップを順番に実行する
    4. outputs/workflow_reports/YYYYMMDD_workflow_report.md にレポートを保存する

前提条件（各ステップの .env 設定）:
    AI_IMPROVEMENT_ENABLED=true
    AI_REWRITE_ENABLED=true
    AI_PUBLISH_ENABLED=true
    ANTHROPIC_API_KEY=your_key_here
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from ai import WorkflowConfig, WorkflowRunner, NullWorkflowRunner, WorkflowStep


def parse_steps(steps_str: str) -> list[WorkflowStep]:
    """カンマ区切りのステップ名を WorkflowStep のリストに変換する。"""
    step_names = [s.strip() for s in steps_str.split(",") if s.strip()]
    result = []
    for name in step_names:
        try:
            result.append(WorkflowStep(name))
        except ValueError:
            valid = [s.value for s in WorkflowStep]
            print(f"[エラー] 不明なステップ名: {name!r}")
            print(f"  有効なステップ: {', '.join(valid)}")
            sys.exit(1)
    return result


def main():
    parser = argparse.ArgumentParser(
        description="AI ワークフロースクリプト（v1.20.0）"
    )
    parser.add_argument(
        "--article-id",
        default=None,
        metavar="SLUG",
        help="絞り込む記事ID（slug）（未指定: 全件）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="実際の処理をせず対象確認のみ行う",
    )
    parser.add_argument(
        "--steps",
        default=None,
        metavar="STEPS",
        help=(
            "実行するステップをカンマ区切りで指定（未指定: 全ステップ）\n"
            "例: improvement,rewrite,publish"
        ),
    )
    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        default=False,
        help="エラー発生時に後続ステップを続行する（デフォルト: 中断）",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent

    # WorkflowConfig の構築
    config = WorkflowConfig.from_env(base_dir=base_dir)
    if args.steps:
        config.steps = parse_steps(args.steps)
    if args.continue_on_error:
        config.continue_on_error = True

    print("=" * 50)
    print("AI ワークフロー 開始")
    print("=" * 50)
    if args.article_id:
        print(f"  絞り込み: article_id={args.article_id}")
    if args.dry_run:
        print("  モード: DRY RUN（実際の処理は行いません）")
    if args.steps:
        print(f"  ステップ: {', '.join(s.value for s in config.steps)}")
    print()

    runner = WorkflowRunner.from_config(config)

    if isinstance(runner, NullWorkflowRunner):
        print("[エラー] AI ワークフローが無効です。")
        print("  AI_WORKFLOW_ENABLED=true を .env に設定してください。")
        sys.exit(1)

    result = runner.run(article_id=args.article_id, dry_run=args.dry_run)

    print()
    print("=" * 50)
    status = "SUCCESS" if result.overall_success else "FAILURE"
    print(f"AI ワークフロー 完了: {status}")
    print(f"  合計処理件数: {result.total_processed} 件")
    print(f"  実行ステップ: {len(result.steps)} 件")
    if result.skipped_steps:
        print(f"  スキップ:     {len(result.skipped_steps)} 件")
    if result.warnings:
        print(f"  警告:         {len(result.warnings)} 件")
    if result.report_path:
        print(f"  レポート: {result.report_path}")
    print("=" * 50)

    if not result.overall_success:
        sys.exit(1)


if __name__ == "__main__":
    main()
