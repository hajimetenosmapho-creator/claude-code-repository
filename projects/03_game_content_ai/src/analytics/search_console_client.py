"""
Google Search Console API との通信を担うモジュール（v1.12.0）

Single Responsibility:
    - Google Search Console API への HTTP 通信のみを担う
    - Service Account 認証を行う
    - searchanalytics().query(...).execute() の実行
    - APIレスポンスの生データ（dict）を返す

禁止事項:
    - SearchConsoleMetrics への変換（SearchConsoleFetcher の責務）
    - AnalyticsEntry の保存（AnalyticsManager の責務）
    - ファイル I/O
    - main.py との直接結合

設計方針（Configuration First）:
    SEARCH_CONSOLE_ENABLED=false または設定不足 → from_env() が NullSearchConsoleClient を返す
    SEARCH_CONSOLE_ENABLED=true + 設定完備     → SearchConsoleClient が API 通信を行う
"""
from __future__ import annotations

from .search_console_config import SearchConsoleConfig

try:
    from googleapiclient.errors import HttpError
except ImportError:
    class HttpError(Exception):  # type: ignore[misc]
        """google-api-python-client 未インストール時のフォールバック。"""
        resp = type("_Resp", (), {"status": 0})()


class SearchConsoleClient:
    """
    Google Search Console API と通信するクライアント。
    Service Account 認証（サービスアカウント JSON）を使用する。

    SEARCH_CONSOLE_ENABLED=false の場合は from_env() が NullSearchConsoleClient を返す。
    """

    def __init__(self, config: SearchConsoleConfig):
        self._config = config
        self._service = None  # 初回 fetch_raw() 時に遅延初期化

    @classmethod
    def from_env(cls) -> "SearchConsoleClient | NullSearchConsoleClient":
        """
        環境変数から設定を読み込み、適切なクライアントを返す。

        SEARCH_CONSOLE_ENABLED=false または設定不足の場合は NullSearchConsoleClient。
        """
        config = SearchConsoleConfig.from_env()
        if not config.is_ready():
            return NullSearchConsoleClient()
        return cls(config)

    def _build_service(self):
        """Service Account 認証で Google Search Console API サービスを構築する。"""
        from google.oauth2 import service_account
        from googleapiclient.discovery import build

        credentials = service_account.Credentials.from_service_account_file(
            self._config.credentials_path,
            scopes=["https://www.googleapis.com/auth/webmasters.readonly"],
        )
        return build("searchconsole", "v1", credentials=credentials)

    def is_available(self) -> bool:
        """API 通信が可能な状態かを返す。"""
        return self._config.is_ready()

    def fetch_raw(self, page_url: str, period_days: int = 28) -> dict:
        """
        指定 URL の Search Console データを取得する。

        Args:
            page_url:    取得対象の記事 permalink
                         例: https://your-blog.com/ps6-announced-20260630/
            period_days: 集計期間（日数）

        Returns:
            dict: Search Console API のレスポンス
                  {"rows": [{"impressions": 100, "clicks": 5, "ctr": 0.05, "position": 3.2}]}
                  データなし時は {"rows": []} または rows キーなし
        """
        if self._service is None:
            self._service = self._build_service()

        from datetime import date, timedelta
        end_date = date.today()
        start_date = end_date - timedelta(days=period_days)

        response = (
            self._service.searchanalytics()
            .query(
                siteUrl=self._config.property_url,
                body={
                    "startDate": start_date.isoformat(),
                    "endDate": end_date.isoformat(),
                    "dimensions": ["page"],
                    "dimensionFilterGroups": [
                        {
                            "filters": [
                                {
                                    "dimension": "page",
                                    "operator": "equals",
                                    "expression": page_url,
                                }
                            ]
                        }
                    ],
                },
            )
            .execute()
        )
        return response


class NullSearchConsoleClient:
    """
    SEARCH_CONSOLE_ENABLED=false または設定不足のときに返されるダミー実装。
    is_available() が False を返し、fetch_raw() は空の dict を返す。
    main.py / SearchConsoleFetcher は SearchConsoleClient か NullSearchConsoleClient かを意識しなくてよい。
    """

    def is_available(self) -> bool:
        return False

    def fetch_raw(self, page_url: str, period_days: int = 28) -> dict:
        return {}
