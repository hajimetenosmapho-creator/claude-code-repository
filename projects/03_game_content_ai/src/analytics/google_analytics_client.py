"""
Google Analytics 4 API との通信を担うモジュール（v1.13.0）

Single Responsibility:
    - GA4 API（BetaAnalyticsDataClient）への HTTP 通信のみを担う
    - Service Account 認証を行う
    - page_url から pagePath を抽出して API に渡す
    - run_report() の実行と生レスポンスの dict 変換

禁止事項:
    - GoogleAnalyticsMetrics への変換（GoogleAnalyticsFetcher の責務）
    - AnalyticsEntry の保存（AnalyticsManager の責務）
    - ファイル I/O
    - main.py との直接結合

URL変換について（SearchConsoleClient との違い）:
    GA4 API はページ識別に pagePath（パス部分のみ）を使用する。
    fetch_raw() 内部で urlparse(page_url).path により抽出を行う。
    例: "https://your-blog.com/ps6-announced-20260630/" → "/ps6-announced-20260630/"

取得する GA4 指標:
    screenPageViews      → GoogleAnalyticsMetrics.page_views
    sessions             → GoogleAnalyticsMetrics.sessions
    bounceRate           → GoogleAnalyticsMetrics.bounce_rate
    averageEngagementTime → GoogleAnalyticsMetrics.avg_time_on_page

設計方針（Configuration First）:
    GOOGLE_ANALYTICS_ENABLED=false または設定不足 → from_env() が NullGoogleAnalyticsClient を返す
"""
from __future__ import annotations

from urllib.parse import urlparse

from .google_analytics_config import GoogleAnalyticsConfig

try:
    from google.api_core.exceptions import GoogleAPIError
except ImportError:
    class GoogleAPIError(Exception):  # type: ignore[misc]
        """google-analytics-data 未インストール時のフォールバック。"""


class GoogleAnalyticsClient:
    """
    Google Analytics 4 API と通信するクライアント。
    Service Account 認証（サービスアカウント JSON）を使用する。

    GOOGLE_ANALYTICS_ENABLED=false の場合は from_env() が NullGoogleAnalyticsClient を返す。
    """

    def __init__(self, config: GoogleAnalyticsConfig):
        self._config = config
        self._client = None  # 初回 fetch_raw() 時に遅延初期化

    @classmethod
    def from_env(cls) -> "GoogleAnalyticsClient | NullGoogleAnalyticsClient":
        """
        環境変数から設定を読み込み、適切なクライアントを返す。

        GOOGLE_ANALYTICS_ENABLED=false または設定不足の場合は NullGoogleAnalyticsClient。
        """
        config = GoogleAnalyticsConfig.from_env()
        if not config.is_ready():
            return NullGoogleAnalyticsClient()
        return cls(config)

    def _build_client(self):
        """Service Account 認証で BetaAnalyticsDataClient を構築する。"""
        from google.oauth2 import service_account
        from google.analytics.data_v1beta import BetaAnalyticsDataClient

        credentials = service_account.Credentials.from_service_account_file(
            self._config.credentials_path,
            scopes=["https://www.googleapis.com/auth/analytics.readonly"],
        )
        return BetaAnalyticsDataClient(credentials=credentials)

    def is_available(self) -> bool:
        """API 通信が可能な状態かを返す。"""
        return self._config.is_ready()

    def fetch_raw(self, page_url: str, period_days: int = 28) -> dict:
        """
        指定 URL の GA4 データを取得する。

        Args:
            page_url:    取得対象の記事 permalink（フルURL）
                         内部で pagePath に変換して GA4 API に渡す。
                         例: "https://your-blog.com/ps6-announced/" → "/ps6-announced/"
            period_days: 集計期間（日数）

        Returns:
            dict: 正規化した GA4 データ
                  {"rows": [{"screenPageViews": 100, "sessions": 80,
                             "bounceRate": 0.3, "averageEngagementTime": 45.2}]}
                  データなし時は {"rows": []}
        """
        if self._client is None:
            self._client = self._build_client()

        from datetime import date, timedelta
        from google.analytics.data_v1beta.types import (
            DateRange,
            Dimension,
            Metric,
            FilterExpression,
            Filter,
            RunReportRequest,
        )

        # page_url から pagePath を抽出（GA4 は pagePath を使用する）
        page_path = urlparse(page_url).path or "/"

        end_date = date.today()
        start_date = end_date - timedelta(days=period_days)

        request = RunReportRequest(
            property=f"properties/{self._config.property_id}",
            date_ranges=[DateRange(
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
            )],
            dimensions=[Dimension(name="pagePath")],
            metrics=[
                Metric(name="screenPageViews"),
                Metric(name="sessions"),
                Metric(name="bounceRate"),
                Metric(name="averageEngagementTime"),
            ],
            dimension_filter=FilterExpression(
                filter=Filter(
                    field_name="pagePath",
                    string_filter=Filter.StringFilter(
                        match_type=Filter.StringFilter.MatchType.EXACT,
                        value=page_path,
                    ),
                )
            ),
        )

        response = self._client.run_report(request)

        # proto レスポンスを dict に変換（GoogleAnalyticsMetrics への変換は Fetcher の責務）
        rows = []
        for row in response.rows:
            rows.append({
                "screenPageViews": int(row.metric_values[0].value or "0"),
                "sessions": int(row.metric_values[1].value or "0"),
                "bounceRate": float(row.metric_values[2].value or "0.0"),
                "averageEngagementTime": float(row.metric_values[3].value or "0.0"),
            })

        return {"rows": rows}


class NullGoogleAnalyticsClient:
    """
    GOOGLE_ANALYTICS_ENABLED=false または設定不足のときに返されるダミー実装。
    is_available() が False を返し、fetch_raw() は空の dict を返す。
    main.py / GoogleAnalyticsFetcher は GoogleAnalyticsClient か NullGoogleAnalyticsClient かを意識しなくてよい。
    """

    def is_available(self) -> bool:
        return False

    def fetch_raw(self, page_url: str, period_days: int = 28) -> dict:
        return {}
