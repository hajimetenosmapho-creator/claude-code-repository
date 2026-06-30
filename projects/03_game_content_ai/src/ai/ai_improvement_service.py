"""
AI 改善提案サービス（v1.14.0）

Single Responsibility:
    - PromptBuilder / ClaudeClient / ImprovementSuggestionParser を統合するサービス層
    - AiInputRecord を受け取り ImprovementSuggestion を返す
    - 結果を JSON ファイルとして outputs/ai_improvements/ に保存する

禁止事項:
    - Claude API の直接呼び出し（ClaudeClient の責務）
    - プロンプト生成（PromptBuilder の責務）
    - JSON 解析（ImprovementSuggestionParser の責務）
    - main.py での直接呼び出し（投稿直後に AI 改善提案を実行しない）

設計方針（Configuration First）:
    AI_IMPROVEMENT_ENABLED=false → from_env() が NullAiImprovementService を返す
    API 失敗 / JSON 解析失敗 → empty ImprovementSuggestion を返して処理継続
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .ai_improvement_config import AiImprovementConfig
from .claude_client import ClaudeClient, NullClaudeClient
from .improvement_suggestion import ImprovementSuggestion
from .improvement_suggestion_parser import ImprovementSuggestionParser
from .prompt_builder import PromptBuilder
from analytics.analytics_entry import AiInputRecord


class AiImprovementService:
    """
    AI 改善提案の実行を担うサービス層。

    処理フロー:
        AiInputRecord
            → PromptBuilder.build()        → prompt
            → ClaudeClient.send()          → raw_response
            → ImprovementSuggestionParser  → ImprovementSuggestion
            → JSON ファイル保存
    """

    def __init__(
        self,
        config: AiImprovementConfig,
        client: "ClaudeClient | NullClaudeClient | None" = None,
        output_dir: Path | None = None,
    ):
        self._config = config
        self._client = client or ClaudeClient(config)
        self._builder = PromptBuilder(prompt_version=config.prompt_version)
        self._parser = ImprovementSuggestionParser()
        self._output_dir = output_dir or Path(config.output_dir)

    @classmethod
    def from_env(cls, base_dir: Path | None = None) -> "AiImprovementService | NullAiImprovementService":
        """
        環境変数から設定を読み込み、AiImprovementService または NullAiImprovementService を返す。
        """
        config = AiImprovementConfig.from_env()
        if not config.is_ready():
            return NullAiImprovementService()

        output_dir = (base_dir / config.output_dir) if base_dir else Path(config.output_dir)
        client = ClaudeClient.from_env()
        return cls(config=config, client=client, output_dir=output_dir)

    def is_available(self) -> bool:
        """サービスが利用可能な状態かを返す。"""
        return self._config.is_ready() and self._client.is_available()

    def improve(self, ai_input: AiInputRecord) -> ImprovementSuggestion:
        """
        AiInputRecord から AI 改善提案を生成し、JSON ファイルに保存する。

        has_performance_data=False の記事でも実行可能（パフォーマンスデータなしで提案）。
        失敗時は empty ImprovementSuggestion を返して処理を継続する。

        Args:
            ai_input: AI 改善提案の入力データ

        Returns:
            ImprovementSuggestion: 改善提案。失敗時は empty suggestion。
        """
        article_id = ai_input.slug
        title = ai_input.seo_title
        permalink = ai_input.permalink

        try:
            prompt = self._builder.build(ai_input)
            raw_response = self._client.send(prompt)
            suggestion = self._parser.parse(
                raw_response=raw_response,
                article_id=article_id,
                title=title,
                permalink=permalink,
                prompt_version=self._builder.prompt_version,
            )
            self._save(suggestion)
            return suggestion
        except Exception as e:
            print(f"  [AI WARNING] AI 改善提案エラー（処理継続）: {e}")
            return ImprovementSuggestion.empty(
                article_id=article_id,
                title=title,
                permalink=permalink,
                prompt_version=self._builder.prompt_version,
            )

    def improve_batch(
        self,
        ai_inputs: list[AiInputRecord],
        performance_only: bool = True,
        max_articles: int | None = None,
    ) -> list[ImprovementSuggestion]:
        """
        複数の AiInputRecord に対して AI 改善提案を実行する。

        Args:
            ai_inputs:         AI 入力レコードのリスト
            performance_only:  True の場合、has_performance_data=True の記事のみ処理
            max_articles:      最大処理件数（None = config の max_articles を使用）

        Returns:
            list[ImprovementSuggestion]: 改善提案のリスト（スキップ分は含まない）
        """
        limit = max_articles if max_articles is not None else self._config.max_articles
        results: list[ImprovementSuggestion] = []

        for ai_input in ai_inputs:
            if len(results) >= limit:
                print(f"  [AI] 上限 {limit} 件に達しました。残りはスキップします。")
                break

            if performance_only and not ai_input.has_performance_data:
                print(f"  [AI スキップ] パフォーマンスデータなし: {ai_input.slug}")
                continue

            print(f"  [AI] 改善提案生成中: {ai_input.slug}")
            suggestion = self.improve(ai_input)
            results.append(suggestion)

        return results

    def _save(self, suggestion: ImprovementSuggestion) -> None:
        """ImprovementSuggestion を JSON ファイルに保存する。"""
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
            date_str = date.today().strftime("%Y%m%d")
            filename = f"{date_str}_{suggestion.article_id}_improvement.json"
            path = self._output_dir / filename
            with path.open("w", encoding="utf-8") as f:
                json.dump(suggestion.to_dict(), f, ensure_ascii=False, indent=2)
            print(f"  [AI] 改善提案保存: {path}")
        except OSError as e:
            print(f"  [AI WARNING] 保存失敗（処理継続）: {e}")


class NullAiImprovementService:
    """
    AI_IMPROVEMENT_ENABLED=false のときに返されるダミー実装（デフォルト）。
    すべてのメソッドが no-op で動作する。
    既存処理を停止させない。
    """

    def is_available(self) -> bool:
        return False

    def improve(self, ai_input: AiInputRecord) -> ImprovementSuggestion:
        print("  [AI] AI 改善提案は無効です（AI_IMPROVEMENT_ENABLED=false）")
        return ImprovementSuggestion.empty(
            article_id=getattr(ai_input, "slug", ""),
            title=getattr(ai_input, "seo_title", ""),
            permalink=getattr(ai_input, "permalink", None),
            prompt_version="v1",
        )

    def improve_batch(
        self,
        ai_inputs: list,
        performance_only: bool = True,
        max_articles: int | None = None,
    ) -> list:
        print("  [AI] AI 改善提案は無効です（AI_IMPROVEMENT_ENABLED=false）")
        return []
