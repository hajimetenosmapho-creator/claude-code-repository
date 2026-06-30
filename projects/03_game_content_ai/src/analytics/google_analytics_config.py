"""
Google Analytics 4 機能の設定管理モジュール（v1.13.0）

設計方針（Configuration First）:
    GOOGLE_ANALYTICS_ENABLED=false → NullGoogleAnalyticsClient を使用（デフォルト）
    GOOGLE_ANALYTICS_ENABLED=true  → GoogleAnalyticsClient が API 通信を行う

Search Console との違い:
    認証情報は GA4_APPLICATION_CREDENTIALS として分離。
    Search Console（GOOGLE_APPLICATION_CREDENTIALS）と別の Service Account を使用できる。

計測期間:
    ANALYTICS_PERIOD_DAYS を Search Console と共用する（GA4専用変数は設けない）。
"""
import os
from dataclasses import dataclass


@dataclass
class GoogleAnalyticsConfig:
    """
    Google Analytics 4 機能の設定。.env から読み込む。

    Attributes:
        enabled:           GA4 機能の有効/無効（デフォルト: False）
        property_id:       GA4 プロパティID（数値。例: "123456789"）
        credentials_path:  Service Account JSON ファイルのパス（SC とは別ファイル）
        period_days:       データ取得期間（日数。ANALYTICS_PERIOD_DAYS と共用）
        timeout_seconds:   API タイムアウト秒数（デフォルト: 30）
    """
    enabled: bool = False
    property_id: str | None = None
    credentials_path: str | None = None
    period_days: int = 28
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> "GoogleAnalyticsConfig":
        """
        環境変数から設定を読み込む。

        読み込む環境変数:
            GOOGLE_ANALYTICS_ENABLED:  有効/無効（デフォルト: "false"）
            GA4_PROPERTY_ID:           GA4 プロパティID（未設定時は None）
            GA4_APPLICATION_CREDENTIALS: Service Account JSON パス（SC とは独立）
            ANALYTICS_PERIOD_DAYS:     計測期間（SearchConsoleConfig と共用。デフォルト: 28）
            GA4_TIMEOUT_SECONDS:       API タイムアウト秒数（デフォルト: 30）
        """
        enabled = os.getenv("GOOGLE_ANALYTICS_ENABLED", "false").lower().strip() == "true"
        property_id = os.getenv("GA4_PROPERTY_ID") or None
        credentials_path = os.getenv("GA4_APPLICATION_CREDENTIALS") or None
        try:
            period_days = int(os.getenv("ANALYTICS_PERIOD_DAYS", "28"))
        except ValueError:
            period_days = 28
        try:
            timeout_seconds = int(os.getenv("GA4_TIMEOUT_SECONDS", "30"))
        except ValueError:
            timeout_seconds = 30
        return cls(
            enabled=enabled,
            property_id=property_id,
            credentials_path=credentials_path,
            period_days=period_days,
            timeout_seconds=timeout_seconds,
        )

    def is_ready(self) -> bool:
        """API 通信に必要な設定がすべて揃っているかを返す。"""
        return (
            self.enabled
            and bool(self.property_id)
            and bool(self.credentials_path)
        )
