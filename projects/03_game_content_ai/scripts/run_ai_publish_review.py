"""
AI 公開レビュースクリプト（v1.19.0）

outputs/ai_publishes/ に保存された投稿結果 JSON を読み込み、
公開前レビュー用の Markdown レポートと JSON を生成する。

このスクリプトは WordPress への操作を一切行いません。
人が公開判断するためのレビュー基盤を構築します。

前提条件:
    run_ai_publish.py を先に実行して
    outputs/ai_publishes/ に投稿結果 JSON が存在すること。

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/run_ai_publish_review.py
    ./venv/Scripts/python.exe scripts/run_ai_publish_review.py --article-id ps6-announced-20260630

動作の流れ:
    1. outputs/ai_publishes/ の投稿結果 JSON を読み込む
    2. AiPublishReviewResult を生成する（review_status=pending 固定）
    3. outputs/ai_publish_reviews/YYYYMMDD_{slug}_publish_review.json に保存する
    4. outputs/ai_publish_review_reports/YYYYMMDD_ai_publish_review_report.md を生成する

重要:
    - WordPress への操作は一切行わない
    - 元記事・WordPress 下書きを変更しない
    - 読み取り・確認のみ
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from ai import AiPublishReviewService


def main():
    parser = argparse.ArgumentParser(
        description="AI 公開レビュースクリプト（v1.19.0）"
    )
    parser.add_argument(
        "--article-id",
        default=None,
        metavar="SLUG",
        help="絞り込む記事ID（slug）（未指定: 全件）",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent

    print("AI 公開レビュー処理 開始")
    if args.article_id:
        print(f"  絞り込み: article_id={args.article_id}")
    print()

    service = AiPublishReviewService.from_paths(base_dir=base_dir)
    report_path = service.run(article_id=args.article_id)

    reviews = service.get_reviews(article_id=args.article_id)
    candidates = [r for r in reviews if r.is_publish_candidate]

    print()
    print(f"完了: {len(reviews)} 件を処理しました。")
    print(f"  公開候補: {len(candidates)} 件")
    if report_path:
        print(f"レポート: {report_path}")
    print(f"レビューJSON: {base_dir / 'outputs' / 'ai_publish_reviews'}/")


if __name__ == "__main__":
    main()
