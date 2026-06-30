"""
AI 公開機能の設定モジュール（v1.18.0）

Configuration First 設計:
    AI_PUBLISH_ENABLED=false → AiPublishService.from_env() が NullAiPublishService を返す（デフォルト）
    AI_PUBLISH_ENABLED=true かつ WordPress 認証情報あり → AiPublishService が返る

環境変数（src/ai/rewrite_config.py と同じ名前に統一）:
    WORDPRESS_URL          WordPress サイト URL
    WORDPRESS_USERNAME     WordPress ユーザー名
    WORDPRESS_APP_PASSWORD WordPress アプリパスワード

禁止事項:
    - ファイル I/O
    - WordPress API の呼び出し
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AiPublishConfig:
    """
    AI 公開機能の設定値。
    すべての値は環境変数から読み込む（Configuration First）。
    """
    enabled: bool = False
    wordpress_url: str | None = None
    wordpress_username: str | None = None
    wordpress_app_password: str | None = None

    @classmethod
    def from_env(cls) -> "AiPublishConfig":
        """環境変数から設定を読み込む。"""
        enabled = os.getenv("AI_PUBLISH_ENABLED", "false").lower().strip() == "true"
        wordpress_url = os.getenv("WORDPRESS_URL") or None
        wordpress_username = os.getenv("WORDPRESS_USERNAME") or None
        wordpress_app_password = os.getenv("WORDPRESS_APP_PASSWORD") or None

        return cls(
            enabled=enabled,
            wordpress_url=wordpress_url,
            wordpress_username=wordpress_username,
            wordpress_app_password=wordpress_app_password,
        )

    def is_ready(self) -> bool:
        """
        AI 公開処理の実行が可能な状態かを返す。

        以下の4条件がすべて満たされた場合のみ True:
            1. AI_PUBLISH_ENABLED=true
            2. WORDPRESS_URL が設定済み
            3. WORDPRESS_USERNAME が設定済み
            4. WORDPRESS_APP_PASSWORD が設定済み
        """
        return (
            self.enabled
            and bool(self.wordpress_url)
            and bool(self.wordpress_username)
            and bool(self.wordpress_app_password)
        )
