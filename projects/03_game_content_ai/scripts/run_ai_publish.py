"""
AI 公開スクリプト（v1.18.0）

outputs/ai_rewrite_reviews/ に保存された review_status=adopted のレビュー結果を読み込み、
対応するリライト本文を WordPress に新規下書きとして投稿する。

前提条件:
    .env に以下を設定すること:
        AI_PUBLISH_ENABLED=true
        WORDPRESS_URL=https://your-blog.com
        WORDPRESS_USERNAME=your_username
        WORDPRESS_APP_PASSWORD=your_app_password

    未設定の場合は NullAiPublishService が動作し、投稿はスキップされます。

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/run_ai_publish.py
    ./venv/Scripts/python.exe scripts/run_ai_publish.py --article-id ps6-announced-20260630

動作の流れ:
    1. outputs/ai_rewrite_reviews/ のレビュー結果 JSON を読み込む
    2. review_status=adopted のもののみ対象にする
    3. 同 article_id で success=True の投稿結果がある場合はスキップする
    4. 対応する RewriteResult からリライト本文を取得する
    5. WordPress REST API に新規下書きとして投稿する
    6. outputs/ai_publishes/YYYYMMDD_{slug}_publish.json に結果を保存する
    7. outputs/ai_publish_reports/YYYYMMDD_ai_publish_report.md にレポートを保存する

重要:
    - 元記事は変更しない（新規投稿のみ）
    - 投稿ステータスは draft 固定（自動公開なし）
    - 投稿失敗時も結果を JSON に記録して処理継続

なぜ別スクリプトか:
    AI Publish は AI Rewrite Review（run_ai_rewrite_review.py）の後工程として実行する。
    WordPress 認証情報が設定されており、かつ AI_PUBLISH_ENABLED=true の場合のみ投稿する。
    ドライラン（.env を変えずに確認）もできる。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from ai import AiPublishService


def main():
    parser = argparse.ArgumentParser(
        description="AI 公開スクリプト（v1.18.0）"
    )
    parser.add_argument(
        "--article-id",
        default=None,
        metavar="SLUG",
        help="絞り込む記事ID（slug）（未指定: 全件）",
    )
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent

    # レビュー結果の存在確認
    review_dir = base_dir / "outputs" / "ai_rewrite_reviews"
    if not review_dir.exists():
        print(f"レビュー結果ディレクトリが存在しません: {review_dir}")
        print("先に以下のバッチを実行してください：")
        print("  scripts/run_ai_rewrite_review.py")
        sys.exit(0)

    review_files = list(review_dir.glob("*_review.json"))
    if not review_files:
        print(f"レビュー結果 JSON が見つかりません: {review_dir}")
        print("先に以下のバッチを実行してください：")
        print("  scripts/run_ai_rewrite_review.py")
        sys.exit(0)

    print("AI 公開処理 開始")
    if args.article_id:
        print(f"  絞り込み: article_id={args.article_id}")
    print()

    service = AiPublishService.from_env(base_dir=base_dir)
    report_path = service.run(article_id=args.article_id)

    publish_results = service.get_results(article_id=args.article_id)
    print()
    print(f"完了: {len(publish_results)} 件を処理しました。")
    if report_path:
        print(f"レポート: {report_path}")
    print(f"投稿結果JSON: {base_dir / 'outputs' / 'ai_publishes'}/")


if __name__ == "__main__":
    main()
