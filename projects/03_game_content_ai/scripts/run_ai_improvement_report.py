"""
AI 改善提案レポート生成バッチスクリプト（v1.15.0）

outputs/ai_improvements/ に保存された改善提案 JSON を読み込み、
Markdown レポートを outputs/ai_improvement_reports/ に生成する。

Claude API は呼び出さない（JSON 読み込み・レポート生成のみ）。

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/run_ai_improvement_report.py
    ./venv/Scripts/python.exe scripts/run_ai_improvement_report.py --priority high
    ./venv/Scripts/python.exe scripts/run_ai_improvement_report.py --article-id ps6-announced-20260630

動作の流れ:
    1. outputs/ai_improvements/ の JSON ファイルを読み込む
    2. 優先度別に整理する
    3. Markdown レポートを生成する
    4. outputs/ai_improvement_reports/YYYYMMDD_ai_improvement_report.md に保存する

前提条件:
    scripts/run_ai_improvement.py を先に実行して、改善提案 JSON が存在すること。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from ai import ImprovementReviewService


def main():
    parser = argparse.ArgumentParser(
        description="AI 改善提案レポート生成バッチ（v1.15.0）"
    )
    parser.add_argument(
        "--priority",
        choices=["high", "medium", "low"],
        default=None,
        help="絞り込む優先度（未指定: 全件）",
    )
    parser.add_argument(
        "--article-id",
        default=None,
        metavar="SLUG",
        help="絞り込む記事ID（slug）",
    )
    parser.add_argument(
        "--prompt-version",
        default=None,
        metavar="VERSION",
        help="絞り込むプロンプトバージョン（例: v1）",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent

    service = ImprovementReviewService.from_paths(
        improvement_dir="outputs/ai_improvements",
        report_dir="outputs/ai_improvement_reports",
        base_dir=base_dir,
    )

    print("AI 改善提案レポート生成開始")
    if args.priority:
        print(f"  絞り込み: priority={args.priority}")
    if args.article_id:
        print(f"  絞り込み: article_id={args.article_id}")
    if args.prompt_version:
        print(f"  絞り込み: prompt_version={args.prompt_version}")
    print()

    report_path = service.run(
        priority=args.priority,
        prompt_version=args.prompt_version,
        article_id=args.article_id,
    )

    if report_path is None:
        print("[エラー] レポートの保存に失敗しました。")
        sys.exit(1)

    print()
    print(f"完了: {report_path}")


if __name__ == "__main__":
    main()
