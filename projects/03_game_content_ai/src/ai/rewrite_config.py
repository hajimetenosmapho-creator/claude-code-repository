"""
AI リライト機能の設定モジュール（v1.16.0）

Configuration First 設計:
    AI_REWRITE_ENABLED=false → RewriteService.from_env() が NullRewriteService を返す（デフォルト）
    AI_REWRITE_ENABLED=true  → 通常の RewriteService が返る

禁止事項:
    - Claude API の直接呼び出し（ClaudeClient の責務）
    - ファイル I/O
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class RewriteConfig:
    """
    AI リライト機能の設定値。
    すべての値は環境変数から読み込む（Configuration First）。
    """
    enabled: bool = False
    model: str = "claude-sonnet-4-6"
    prompt_version: str = "v1"
    max_articles: int = 5
    output_dir: str = "outputs/ai_rewrites"
    api_key: str | None = None
    timeout_seconds: int = 60
    wordpress_url: str | None = None
    wordpress_username: str | None = None
    wordpress_app_password: str | None = None

    @classmethod
    def from_env(cls) -> "RewriteConfig":
        """環境変数から設定を読み込む。"""
        enabled = os.getenv("AI_REWRITE_ENABLED", "false").lower().strip() == "true"
        model = os.getenv("AI_REWRITE_MODEL", "claude-sonnet-4-6")
        prompt_version = os.getenv("AI_REWRITE_PROMPT_VERSION", "v1")
        try:
            max_articles = int(os.getenv("AI_REWRITE_MAX_ARTICLES", "5"))
        except ValueError:
            max_articles = 5
        output_dir = os.getenv("AI_REWRITE_OUTPUT_DIR", "outputs/ai_rewrites")
        api_key = os.getenv("ANTHROPIC_API_KEY") or None
        try:
            timeout_seconds = int(os.getenv("AI_TIMEOUT_SECONDS", "60"))
        except ValueError:
            timeout_seconds = 60
        wordpress_url = os.getenv("WORDPRESS_URL") or None
        wordpress_username = os.getenv("WORDPRESS_USERNAME") or None
        wordpress_app_password = os.getenv("WORDPRESS_APP_PASSWORD") or None

        return cls(
            enabled=enabled,
            model=model,
            prompt_version=prompt_version,
            max_articles=max_articles,
            output_dir=output_dir,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
            wordpress_url=wordpress_url,
            wordpress_username=wordpress_username,
            wordpress_app_password=wordpress_app_password,
        )

    def is_ready(self) -> bool:
        """AI リライトの実行が可能な状態かを返す。"""
        return self.enabled and bool(self.api_key)

    def has_wordpress_credentials(self) -> bool:
        """WordPress REST API への接続情報が揃っているかを返す。"""
        return bool(self.wordpress_url and self.wordpress_username and self.wordpress_app_password)
