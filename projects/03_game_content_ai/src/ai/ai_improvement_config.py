"""
AI 改善提案機能の設定モジュール（v1.14.0）

Configuration First 設計:
    AI_IMPROVEMENT_ENABLED=false → from_env() が NullAiImprovementService を返す（デフォルト）
    AI_IMPROVEMENT_ENABLED=true  → 通常の AiImprovementService が返る

禁止事項:
    - Claude API の直接呼び出し（ClaudeClient の責務）
    - ファイル I/O
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class AiImprovementConfig:
    """
    AI 改善提案機能の設定値。
    すべての値は環境変数から読み込む（Configuration First）。
    """
    enabled: bool = False
    model: str = "claude-sonnet-4-6"
    prompt_version: str = "v1"
    max_articles: int = 10
    output_dir: str = "outputs/ai_improvements"
    api_key: str | None = None
    timeout_seconds: int = 60

    @classmethod
    def from_env(cls) -> "AiImprovementConfig":
        """環境変数から設定を読み込む。"""
        enabled = os.getenv("AI_IMPROVEMENT_ENABLED", "false").lower().strip() == "true"
        model = os.getenv("AI_IMPROVEMENT_MODEL", "claude-sonnet-4-6")
        prompt_version = os.getenv("AI_IMPROVEMENT_PROMPT_VERSION", "v1")
        try:
            max_articles = int(os.getenv("AI_IMPROVEMENT_MAX_ARTICLES", "10"))
        except ValueError:
            max_articles = 10
        output_dir = os.getenv("AI_IMPROVEMENT_OUTPUT_DIR", "outputs/ai_improvements")
        api_key = os.getenv("ANTHROPIC_API_KEY") or None
        try:
            timeout_seconds = int(os.getenv("AI_TIMEOUT_SECONDS", "60"))
        except ValueError:
            timeout_seconds = 60

        return cls(
            enabled=enabled,
            model=model,
            prompt_version=prompt_version,
            max_articles=max_articles,
            output_dir=output_dir,
            api_key=api_key,
            timeout_seconds=timeout_seconds,
        )

    def is_ready(self) -> bool:
        """AI 改善提案の実行が可能な状態かを返す。"""
        return self.enabled and bool(self.api_key)
