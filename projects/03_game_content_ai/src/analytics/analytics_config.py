"""
Analytics 機能の設定管理モジュール。

設計方針（Configuration First）:
    - ANALYTICS_ENABLED=false → NullAnalyticsManager を返す（デフォルト）
    - ANALYTICS_ENABLED=true  → AnalyticsManager を返す

デフォルトが false である理由:
    Logging Foundation（LOG_ENABLED=true）は実行履歴を残す基本動作のためデフォルト有効。
    Analytics Foundation は外部API連携・分析処理へ発展する基盤のため、
    v1.10.0 では意図的にデフォルト無効とし、準備が整った段階で有効化する。
"""
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AnalyticsConfig:
    """
    Analytics 機能の設定。.env から読み込む。

    Attributes:
        enabled:        Analytics 機能の有効/無効（デフォルト: False）
        analytics_dir:  analytics ログの保存先サブディレクトリ名（デフォルト: "analytics"）
        period_days:    パフォーマンスデータの計測期間（日数。デフォルト: 28）
    """
    enabled: bool = False
    analytics_dir: str = "analytics"
    period_days: int = 28

    @classmethod
    def from_env(cls) -> "AnalyticsConfig":
        """
        環境変数から設定を読み込む。

        読み込む環境変数:
            ANALYTICS_ENABLED:      Analytics 機能の有効/無効（デフォルト: "false"）
            ANALYTICS_DIR:          サブディレクトリ名（デフォルト: "analytics"）
            ANALYTICS_PERIOD_DAYS:  計測期間（日数、デフォルト: "28"）

        Returns:
            AnalyticsConfig: 設定インスタンス
        """
        enabled = os.getenv("ANALYTICS_ENABLED", "false").lower().strip() == "true"
        analytics_dir = os.getenv("ANALYTICS_DIR", "analytics")
        try:
            period_days = int(os.getenv("ANALYTICS_PERIOD_DAYS", "28"))
        except ValueError:
            period_days = 28
        return cls(
            enabled=enabled,
            analytics_dir=analytics_dir,
            period_days=period_days,
        )

    def get_analytics_path(self, log_dir: Path) -> Path:
        """analytics ログの保存先ディレクトリパスを返す。"""
        return log_dir / self.analytics_dir
