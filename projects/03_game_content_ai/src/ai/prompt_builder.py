"""
AiInputRecord からプロンプト文字列を生成するモジュール（v1.14.0）

Single Responsibility:
    - AiInputRecord を受け取り、プロンプト文字列を返す
    - Prompt Version に応じたテンプレートを選択する
    - API 通信は行わない

禁止事項:
    - Claude API の直接呼び出し（ClaudeClient の責務）
    - ImprovementSuggestion の生成（ImprovementSuggestionParser の責務）
    - ファイル I/O
"""
from __future__ import annotations

from analytics.analytics_entry import AiInputRecord


class PromptBuilder:
    """
    AiInputRecord → プロンプト文字列の変換を担うクラス。

    Prompt Version 管理:
        v1 → prompts/v1_improvement.py の build_prompt() を使用
        未知のバージョン → v1 にフォールバック
    """

    SUPPORTED_VERSIONS = ("v1",)
    DEFAULT_VERSION = "v1"

    def __init__(self, prompt_version: str = "v1"):
        if prompt_version not in self.SUPPORTED_VERSIONS:
            print(f"  [AI WARNING] 未対応のプロンプトバージョン '{prompt_version}'。v1 を使用します。")
            prompt_version = self.DEFAULT_VERSION
        self._prompt_version = prompt_version

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    def build(self, ai_input: AiInputRecord) -> str:
        """
        AiInputRecord からプロンプト文字列を生成する。

        Args:
            ai_input: AI 改善提案の入力データ

        Returns:
            str: Claude API に渡すプロンプト文字列
        """
        article_data = ai_input.to_dict()

        if self._prompt_version == "v1":
            from .prompts.v1_improvement import build_prompt
            return build_prompt(article_data)

        # フォールバック（SUPPORTED_VERSIONS チェックで通常は到達しない）
        from .prompts.v1_improvement import build_prompt
        return build_prompt(article_data)
