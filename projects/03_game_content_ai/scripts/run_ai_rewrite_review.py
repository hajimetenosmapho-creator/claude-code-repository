"""
AI リライトレビュースクリプト（v1.17.0）

outputs/ai_rewrites/ に保存されたリライト結果 JSON を読み込み、
レビュー結果 JSON と Markdown レポートを生成する。

Claude API を呼び出しません（オフラインで動作します）。

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/run_ai_rewrite_review.py
    ./venv/Scripts/python.exe scripts/run_ai_rewrite_review.py --article-id ps6-announced-20260630

動作の流れ:
    1. outputs/ai_rewrites/ のリライト結果 JSON を読み込む
    2. 記事ID でフィルタリング（オプション）
    3. RewriteReviewService.run() でレビュー結果を生成する
    4. outputs/ai_rewrite_reviews/YYYYMMDD_{slug}_review.json に JSON を保存する
    5. outputs/ai_rewrite_reports/YYYYMMDD_ai_rewrite_review_report.md に Markdown を保存する

前提条件:
    outputs/ai_rewrites/ にリライト結果 JSON が存在すること
    （先に scripts/run_ai_rewrite.py を実行してください）

なぜ別スクリプトか:
    リライトレビューは AI リライト（run_ai_rewrite.py）の後工程として実行する。
    Claude API を使わずオフラインで動作するため、いつでも再実行できる。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from ai import RewriteReviewService


def main():
    parser = argparse.ArgumentParser(
        description="AI リライトレビュースクリプト（v1.17.0）"
    )
    parser.add_argument(
        "--article-id",
        default=None,
        metavar="SLUG",
        help="絞り込む記事ID（slug）（未指定: 全件）",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent

    # リライト結果の存在確認
    rewrite_dir = base_dir / "outputs" / "ai_rewrites"
    if not rewrite_dir.exists():
        print(f"リライト結果ディレクトリが存在しません: {rewrite_dir}")
        print("先に以下のバッチを実行してください：")
        print("  scripts/run_ai_rewrite.py")
        sys.exit(0)

    rewrite_files = list(rewrite_dir.glob("*_rewrite.json"))
    if not rewrite_files:
        print(f"リライト結果 JSON が見つかりません: {rewrite_dir}")
        print("先に以下のバッチを実行してください：")
        print("  scripts/run_ai_rewrite.py")
        sys.exit(0)

    print("AI リライトレビュー開始")
    if args.article_id:
        print(f"  絞り込み: article_id={args.article_id}")
    print()

    service = RewriteReviewService.from_paths(base_dir=base_dir)
    report_path = service.run(article_id=args.article_id)

    reviews = service.get_reviews(article_id=args.article_id)
    print()
    print(f"完了: {len(reviews)} 件のレビュー結果を生成しました。")
    if report_path:
        print(f"レポート: {report_path}")
    print(f"レビューJSON: {base_dir / 'outputs' / 'ai_rewrite_reviews'}/")


if __name__ == "__main__":
    main()
