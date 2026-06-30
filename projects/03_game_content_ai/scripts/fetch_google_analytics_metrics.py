"""
Google Analytics 4 メトリクス取得バッチスクリプト（v1.13.0）

日次バッチとして実行し、公開済み記事の GA4 アクセス指標を取得して
AnalyticsEntry に保存する。

Search Console バッチ（scripts/fetch_search_console_metrics.py）とは独立して動作する。
2つのバッチの統合は v1.14.0 以降で検討する。

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/fetch_google_analytics_metrics.py
    ./venv/Scripts/python.exe scripts/fetch_google_analytics_metrics.py --date 20260630

動作の流れ:
    1. logs/articles/YYYYMMDD_articles.jsonl から投稿済み記事を読み込む
    2. 各記事の wp_public_url を permalink として GoogleAnalyticsFetcher に渡す
    3. GoogleAnalyticsMetrics を AnalyticsEntry に反映して logs/analytics/ へ保存する

前提条件（.env に設定が必要）:
    GOOGLE_ANALYTICS_ENABLED=true
    GA4_PROPERTY_ID=123456789
    GA4_APPLICATION_CREDENTIALS=credentials/google_analytics_sa.json
    ANALYTICS_ENABLED=true

なぜ投稿直後ではなく別スクリプトか:
    GA4 のデータは、記事公開後 24〜48 時間以上経過してから反映されるため、
    投稿時点では取得できない。このスクリプトを日次バッチとして実行することで、
    データが揃ってから取得する設計になっている。
"""
import argparse
import sys
from datetime import date
from pathlib import Path

# src/ をインポートパスに追加
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from analytics import AnalyticsManager, NullAnalyticsManager
from analytics.analytics_entry import AnalyticsEntry, GoogleAnalyticsMetrics, SearchConsoleMetrics
from analytics.google_analytics_fetcher import GoogleAnalyticsFetcher


def main():
    parser = argparse.ArgumentParser(
        description="Google Analytics 4 メトリクス取得バッチ（v1.13.0）"
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

    # GoogleAnalyticsFetcher の確認（GOOGLE_ANALYTICS_ENABLED=true が必要）
    fetcher = GoogleAnalyticsFetcher.from_env()
    if not fetcher.is_available():
        print("[エラー] Google Analytics 4 が利用できません。以下を確認してください：")
        print("  GOOGLE_ANALYTICS_ENABLED=true")
        print("  GA4_PROPERTY_ID=123456789")
        print("  GA4_APPLICATION_CREDENTIALS=credentials/google_analytics_sa.json")
        sys.exit(1)

    # 対象記事の読み込み
    log_dir = base_dir / "logs"
    articles = list(analytics_manager.load_article_logs(log_dir=log_dir, date_str=date_str))

    if not articles:
        print(f"対象記事なし（{date_str}）")
        sys.exit(0)

    print(f"GA4 メトリクス取得開始: {len(articles)}件（{date_str}）")
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

        has_data = metrics.page_views > 0 or metrics.sessions > 0
        data_source = "google_analytics" if has_data else "placeholder"

        entry = AnalyticsEntry(
            measured_at=date.today().isoformat(),
            post_id=post_id,
            slug=slug,
            wp_public_url=wp_public_url,
            period_days=28,
            search_console=SearchConsoleMetrics(),  # SC は別バッチで管理
            google_analytics=metrics,
            data_source=data_source,
        )
        analytics_manager.save_analytics_entry(entry)
        success_count += 1

        if has_data:
            print(
                f"    page_views={metrics.page_views}"
                f" sessions={metrics.sessions}"
                f" bounce_rate={metrics.bounce_rate:.3f}"
                f" avg_engagement_time={metrics.avg_time_on_page:.1f}s"
            )
        else:
            print("    データなし（placeholder として保存）")

    print()
    print(f"完了: 処理={success_count}件 / スキップ={skip_count}件 / 合計={len(articles)}件")
    print(f"保存先: {log_dir}/analytics/")


if __name__ == "__main__":
    main()
