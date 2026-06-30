"""
Search Console 機能の設定管理モジュール（v1.12.0）

設計方針（Configuration First）:
    SEARCH_CONSOLE_ENABLED=false → NullSearchConsoleClient を使用（デフォルト）
    SEARCH_CONSOLE_ENABLED=true  → SearchConsoleClient が API 通信を行う

デフォルトが false である理由:
    Service Account 認証情報の設置が前提のため、準備前に有効化しないよう
    明示的にデフォルト無効とする。
"""
import os
from dataclasses import dataclass


@dataclass
class SearchConsoleConfig:
    """
    Search Console 機能の設定。.env から読み込む。

    Attributes:
        enabled:           Search Console 機能の有効/無効（デフォルト: False）
        property_url:      Search Console のプロパティURL（例: https://your-blog.com/）
        credentials_path:  Service Account JSON ファイルのパス
        period_days:       データ取得期間（日数。AnalyticsConfig.period_days と共有）
        timeout_seconds:   API タイムアウト秒数（デフォルト: 30）
    """
    enabled: bool = False
    property_url: str | None = None
    credentials_path: str | None = None
    period_days: int = 28
    timeout_seconds: int = 30

    @classmethod
    def from_env(cls) -> "SearchConsoleConfig":
        """
        環境変数から設定を読み込む。

        読み込む環境変数:
            SEARCH_CONSOLE_ENABLED:         有効/無効（デフォルト: "false"）
            SEARCH_CONSOLE_PROPERTY:        プロパティURL（未設定時は None）
            GOOGLE_APPLICATION_CREDENTIALS: Service Account JSON パス（未設定時は None）
            ANALYTICS_PERIOD_DAYS:          計測期間（AnalyticsConfig と共有。デフォルト: 28）
            SEARCH_CONSOLE_TIMEOUT:         API タイムアウト秒数（デフォルト: 30）
        """
        enabled = os.getenv("SEARCH_CONSOLE_ENABLED", "false").lower().strip() == "true"
        property_url = os.getenv("SEARCH_CONSOLE_PROPERTY") or None
        credentials_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or None
        try:
            period_days = int(os.getenv("ANALYTICS_PERIOD_DAYS", "28"))
        except ValueError:
            period_days = 28
        try:
            timeout_seconds = int(os.getenv("SEARCH_CONSOLE_TIMEOUT", "30"))
        except ValueError:
            timeout_seconds = 30
        return cls(
            enabled=enabled,
            property_url=property_url,
            credentials_path=credentials_path,
            period_days=period_days,
            timeout_seconds=timeout_seconds,
        )

    def is_ready(self) -> bool:
        """API 通信に必要な設定がすべて揃っているかを返す。"""
        return (
            self.enabled
            and bool(self.property_url)
            and bool(self.credentials_path)
        )
