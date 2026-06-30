"""
ImprovementSuggestion + article_content からプロンプト文字列を生成するモジュール（v1.16.0）

Single Responsibility:
    - ImprovementSuggestion と article_content を受け取り、プロンプト文字列を返す
    - Prompt Version に応じたテンプレートを選択する
    - API 通信は行わない

禁止事項:
    - Claude API の直接呼び出し（ClaudeClient の責務）
    - RewriteResult の生成（RewriteParser の責務）
    - ファイル I/O
"""
from __future__ import annotations

from .improvement_suggestion import ImprovementSuggestion


class RewritePromptBuilder:
    """
    ImprovementSuggestion + article_content → プロンプト文字列の変換を担うクラス。

    Prompt Version 管理:
        v1 → prompts/v1_rewrite.py の build_prompt() を使用
        未知のバージョン → v1 にフォールバック
    """

    SUPPORTED_VERSIONS = ("v1",)
    DEFAULT_VERSION = "v1"

    def __init__(self, prompt_version: str = "v1"):
        if prompt_version not in self.SUPPORTED_VERSIONS:
            print(f"  [REWRITE WARNING] 未対応のプロンプトバージョン '{prompt_version}'。v1 を使用します。")
            prompt_version = self.DEFAULT_VERSION
        self._prompt_version = prompt_version

    @property
    def prompt_version(self) -> str:
        return self._prompt_version

    def build(self, suggestion: ImprovementSuggestion, article_content: str = "") -> str:
        """
        ImprovementSuggestion と article_content からプロンプト文字列を生成する。

        Args:
            suggestion:      改善提案（ImprovementSuggestion）
            article_content: ArticleProvider が取得した元記事本文（空文字も許容）

        Returns:
            str: Claude API に渡すプロンプト文字列
        """
        suggestion_data = suggestion.to_dict()

        if self._prompt_version == "v1":
            from .prompts.v1_rewrite import build_prompt
            return build_prompt(
                article_data=suggestion_data,
                suggestion_data=suggestion_data,
                original_content=article_content,
            )

        # フォールバック（SUPPORTED_VERSIONS チェックで通常は到達しない）
        from .prompts.v1_rewrite import build_prompt
        return build_prompt(
            article_data=suggestion_data,
            suggestion_data=suggestion_data,
            original_content=article_content,
        )
