"""
GA4 APIレスポンスを GoogleAnalyticsMetrics に変換するモジュール（v1.13.0）

Single Responsibility:
    - page_url を受け取り GoogleAnalyticsClient から生データを取得する
    - 生データを既存の GoogleAnalyticsMetrics に変換する
    - 例外を [GA4 WARNING] として出力しシステム全体を停止させない

禁止事項:
    - Google API への直接通信（GoogleAnalyticsClient の責務）
    - AnalyticsEntry の保存（AnalyticsManager の責務）
    - GoogleAnalyticsMetrics の独自定義（analytics_entry.py を Single Source of Truth とする）
    - ファイル I/O

例外処理方針:
    - GoogleAPIError: [GA4 WARNING] のみ表示して GoogleAnalyticsMetrics() ゼロ値を返す
    - 予期せぬ Exception: [GA4 WARNING] のみ表示してゼロ値を返す
    - システム全体を停止させない

[GA4 WARNING] プレフィックスにより Search Console の [SC WARNING] と区別できる。
"""
from __future__ import annotations

from .analytics_entry import GoogleAnalyticsMetrics
from .google_analytics_client import GoogleAnalyticsClient, NullGoogleAnalyticsClient

try:
    from google.api_core.exceptions import GoogleAPIError
except ImportError:
    class GoogleAPIError(Exception):  # type: ignore[misc]
        """google-analytics-data 未インストール時のフォールバック。"""


class GoogleAnalyticsFetcher:
    """
    page_url → GoogleAnalyticsMetrics の変換を担うクラス。

    GoogleAnalyticsClient の fetch_raw() 結果を受け取り、
    既存の GoogleAnalyticsMetrics（analytics_entry.py 定義）に変換して返す。

    GA4 指標マッピング:
        screenPageViews      → page_views
        sessions             → sessions
        bounceRate           → bounce_rate
        averageEngagementTime → avg_time_on_page
    """

    def __init__(self, client: "GoogleAnalyticsClient | NullGoogleAnalyticsClient"):
        self._client = client

    @classmethod
    def from_env(cls) -> "GoogleAnalyticsFetcher":
        """環境変数からクライアントを構築して GoogleAnalyticsFetcher を返す。"""
        client = GoogleAnalyticsClient.from_env()
        return cls(client)

    def is_available(self) -> bool:
        """フェッチが可能な状態かを返す。"""
        return self._client.is_available()

    def fetch(self, page_url: str, period_days: int = 28) -> GoogleAnalyticsMetrics:
        """
        指定 URL の GA4 アクセス指標を取得して GoogleAnalyticsMetrics を返す。

        クライアントが利用不可・例外発生時はゼロ値を返してシステムを継続する。

        Args:
            page_url:    取得対象の記事 permalink（SaveResult.permalink を使用）
                         GoogleAnalyticsClient 内部で pagePath に変換される。
            period_days: 集計期間（日数）

        Returns:
            GoogleAnalyticsMetrics: 取得結果。取得不可・失敗時はゼロ値（全フィールド 0）。
        """
        if not self._client.is_available():
            return GoogleAnalyticsMetrics()

        try:
            raw = self._client.fetch_raw(page_url, period_days)
            return self._parse(raw)
        except GoogleAPIError as e:
            print(f"  [GA4 WARNING] GA4 API エラー（処理継続）: {e}")
            return GoogleAnalyticsMetrics()
        except Exception as e:
            print(f"  [GA4 WARNING] 予期せぬエラー（処理継続）: {e}")
            return GoogleAnalyticsMetrics()

    def _parse(self, raw: dict) -> GoogleAnalyticsMetrics:
        """
        GA4 API レスポンス（dict）から GoogleAnalyticsMetrics を生成する。

        レスポンス形式（GoogleAnalyticsClient.fetch_raw() が正規化して返す）:
            {
                "rows": [
                    {
                        "screenPageViews": 1500,
                        "sessions": 1200,
                        "bounceRate": 0.35,
                        "averageEngagementTime": 62.5
                    }
                ]
            }

        rows が空の場合（データなし・記事が新しすぎる等）はゼロ値を返す。
        複数行の場合は page_views / sessions を合計、bounce_rate / avg_time_on_page を平均する。
        """
        rows = raw.get("rows", [])
        if not rows:
            return GoogleAnalyticsMetrics()

        total_page_views = sum(int(r.get("screenPageViews", 0)) for r in rows)
        total_sessions = sum(int(r.get("sessions", 0)) for r in rows)
        bounce_rates = [float(r.get("bounceRate", 0.0)) for r in rows]
        engagement_times = [float(r.get("averageEngagementTime", 0.0)) for r in rows]
        count = len(rows)

        return GoogleAnalyticsMetrics(
            page_views=total_page_views,
            sessions=total_sessions,
            bounce_rate=sum(bounce_rates) / count if count > 0 else 0.0,
            avg_time_on_page=sum(engagement_times) / count if count > 0 else 0.0,
        )
