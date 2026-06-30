"""
Google API クライアントの共通インターフェース（v1.12.0）

将来の Google Analytics 4 API クライアントとの共通化を見据えた Protocol を定義する。
SearchConsoleClient と将来の GoogleAnalyticsClient が準拠する。
"""
from typing import Protocol, runtime_checkable


@runtime_checkable
class GoogleApiClient(Protocol):
    """
    Google API クライアントの共通インターフェース。

    実装クラス:
        SearchConsoleClient（v1.12.0）
        NullSearchConsoleClient（v1.12.0）
        GoogleAnalyticsClient（将来）
    """

    def fetch_raw(self, page_url: str, period_days: int) -> dict:
        """
        指定 URL のパフォーマンスデータを取得し、APIレスポンス（dict）を返す。

        Args:
            page_url:    取得対象の記事 permalink
            period_days: データ集計期間（日数）

        Returns:
            dict: API レスポンスの生データ
        """
        ...

    def is_available(self) -> bool:
        """
        API 通信が可能な状態かを返す。設定不足・無効時は False。

        Returns:
            bool: 通信可能なら True
        """
        ...
