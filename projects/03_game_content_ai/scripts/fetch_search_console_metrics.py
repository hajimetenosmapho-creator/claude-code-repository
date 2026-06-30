"""
Search Console メトリクス取得バッチスクリプト（v1.12.0）

日次バッチとして実行し、公開済み記事の Search Console パフォーマンスデータを取得して
AnalyticsEntry に保存する。

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/fetch_search_console_metrics.py
    ./venv/Scripts/python.exe scripts/fetch_search_console_metrics.py --date 20260630

動作の流れ:
    1. logs/articles/YYYYMMDD_articles.jsonl から投稿済み記事を読み込む
    2. 各記事の wp_public_url を permalink として SearchConsoleFetcher に渡す
    3. SearchConsoleMetrics を AnalyticsEntry に反映して logs/analytics/ へ保存する

前提条件（.env に設定が必要）:
    SEARCH_CONSOLE_ENABLED=true
    SEARCH_CONSOLE_PROPERTY=https://your-blog.com/
    GOOGLE_APPLICATION_CREDENTIALS=credentials/search_console_sa.json
    ANALYTICS_ENABLED=true

なぜ投稿直後ではなく別スクリプトか:
    Search Console のデータは、記事公開後 1〜3日以上経過してから反映されるため、
    投稿時点では取得できない。このスクリプトを日次バッチとして実行することで、
    データが揃ってから取得する設計になっている。
"""
import argparse
import sys
from datetime import date
from pathlib import Path

# src/ をインポートパスに追加（プロジェクトルートから相対パスで解決）
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from analytics import AnalyticsManager, NullAnalyticsManager
from analytics.analytics_entry import AnalyticsEntry, SearchConsoleMetrics, GoogleAnalyticsMetrics
from analytics.search_console_fetcher import SearchConsoleFetcher


def main():
    parser = argparse.ArgumentParser(
        description="Search Console メトリクス取得バッチ（v1.12.0）"
    )
    parser.add_argument(
        "--date",
        default=date.today().strftime("%Y%m%d"),
        metavar="YYYYMMDD",
        help="対象日付（デフォルト: 今日）",
    )
    args = parser.parse_args()
    date_str = args.date

    base_dir = Path(__file__).parent.parent

    # AnalyticsManager の確認（ANALYTICS_ENABLED=true が必要）
    analytics_manager = AnalyticsManager.from_env(base_dir=base_dir)
    if isinstance(analytics_manager, NullAnalyticsManager):
        print("[エラー] ANALYTICS_ENABLED=true が必要です。")
        print("  .env に ANALYTICS_ENABLED=true を設定してください。")
        sys.exit(1)

    # SearchConsoleFetcher の確認（SEARCH_CONSOLE_ENABLED=true が必要）
    fetcher = SearchConsoleFetcher.from_env()
    if not fetcher.is_available():
        print("[エラー] Search Console が利用できません。以下を確認してください：")
        print("  SEARCH_CONSOLE_ENABLED=true")
        print("  SEARCH_CONSOLE_PROPERTY=https://your-blog.com/")
        print("  GOOGLE_APPLICATION_CREDENTIALS=credentials/search_console_sa.json")
        sys.exit(1)

    # 対象記事の読み込み
    log_dir = base_dir / "logs"
    articles = list(analytics_manager.load_article_logs(log_dir=log_dir, date_str=date_str))

    if not articles:
        print(f"対象記事なし（{date_str}）")
        sys.exit(0)

    print(f"Search Console メトリクス取得開始: {len(articles)}件（{date_str}）")
    print()

    success_count = 0
    skip_count = 0

    for article in articles:
        post_id = article.get("post_id", 0)
        slug = article.get("slug", "")
        wp_public_url = article.get("wp_public_url", "")

        if not wp_public_url or not post_id:
            print(f"  [スキップ] URL/post_id なし: {slug or '(slug不明)'}")
            skip_count += 1
            continue

        print(f"  取得中 [{post_id}] {wp_public_url}")
        metrics = fetcher.fetch(wp_public_url, period_days=28)

        has_data = metrics.impressions > 0 or metrics.clicks > 0
        data_source = "search_console" if has_data else "placeholder"

        entry = AnalyticsEntry(
            measured_at=date.today().isoformat(),
            post_id=post_id,
            slug=slug,
            wp_public_url=wp_public_url,
            period_days=28,
            search_console=metrics,
            google_analytics=GoogleAnalyticsMetrics(),
            data_source=data_source,
        )
        analytics_manager.save_analytics_entry(entry)
        success_count += 1

        if has_data:
            print(
                f"    impressions={metrics.impressions}"
                f" clicks={metrics.clicks}"
                f" ctr={metrics.ctr:.3f}"
                f" position={metrics.avg_position:.1f}"
            )
        else:
            print("    データなし（placeholder として保存）")

    print()
    print(f"完了: 処理={success_count}件 / スキップ={skip_count}件 / 合計={len(articles)}件")
    print(f"保存先: {log_dir}/analytics/")


if __name__ == "__main__":
    main()
