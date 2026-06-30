"""
AI リライトサービス（v1.16.0）

Single Responsibility:
    - ArticleProvider / RewritePromptBuilder / ClaudeClient / RewriteParser /
      RewriteRepository を統合するサービス層
    - ImprovementSuggestion を受け取り RewriteResult を返す
    - 結果を outputs/ai_rewrites/ に保存する

禁止事項:
    - Claude API の直接呼び出し（ClaudeClient の責務）
    - プロンプト生成（RewritePromptBuilder の責務）
    - JSON 解析（RewriteParser の責務）
    - 記事取得（ArticleProvider の責務）
    - ファイル保存（RewriteRepository の責務）

設計方針（Configuration First）:
    AI_REWRITE_ENABLED=false → from_env() が NullRewriteService を返す
    API 失敗 / JSON 解析失敗 → success=False の RewriteResult を返して処理継続

ClaudeClient の扱い:
    ClaudeClient は AiImprovementConfig を受け取る設計のため、
    from_env() 内で RewriteConfig の値を使って AiImprovementConfig を組み立てて渡す。
    ClaudeClient 自体には変更を加えない（後方互換性を維持）。
"""
from __future__ import annotations

from pathlib import Path

from .ai_improvement_config import AiImprovementConfig
from .article_provider import ArticleProvider, NullArticleProvider, WordPressArticleProvider
from .claude_client import ClaudeClient, NullClaudeClient
from .improvement_suggestion import ImprovementSuggestion
from .rewrite_config import RewriteConfig
from .rewrite_parser import RewriteParser
from .rewrite_prompt_builder import RewritePromptBuilder
from .rewrite_repository import RewriteRepository
from .rewrite_result import RewriteResult


class RewriteService:
    """
    AI リライトの実行を担うサービス層。

    処理フロー:
        ImprovementSuggestion
            → ArticleProvider.fetch()        → article_content
            → RewritePromptBuilder.build()   → prompt
            → ClaudeClient.send()            → raw_response
            → RewriteParser.parse()          → RewriteResult
            → RewriteRepository.save()       → Markdown + JSON ファイル
    """

    def __init__(
        self,
        config: RewriteConfig,
        provider: ArticleProvider,
        client: "ClaudeClient | NullClaudeClient",
        repository: RewriteRepository,
    ):
        self._config = config
        self._provider = provider
        self._client = client
        self._builder = RewritePromptBuilder(prompt_version=config.prompt_version)
        self._parser = RewriteParser()
        self._repository = repository

    @classmethod
    def from_env(
        cls, base_dir: Path | None = None
    ) -> "RewriteService | NullRewriteService":
        """
        環境変数から設定を読み込み、RewriteService または NullRewriteService を返す。

        ClaudeClient の組み立て:
            ClaudeClient は AiImprovementConfig を受け取る設計のため、
            RewriteConfig の値を使って AiImprovementConfig を生成して渡す。
            ClaudeClient には変更を加えない。

        ArticleProvider の選択:
            WordPress 認証情報が揃っている → WordPressArticleProvider
            未設定                         → NullArticleProvider
        """
        config = RewriteConfig.from_env()
        if not config.is_ready():
            return NullRewriteService()

        # RewriteConfig の値を使って AiImprovementConfig を組み立てる
        # ClaudeClient の後方互換性を維持するための設計
        claude_config = AiImprovementConfig(
            enabled=True,
            model=config.model,
            api_key=config.api_key,
            timeout_seconds=config.timeout_seconds,
        )
        client = ClaudeClient(claude_config)

        # WordPress 認証情報の有無で provider を選択する
        if config.has_wordpress_credentials():
            provider: ArticleProvider = WordPressArticleProvider(
                url=config.wordpress_url,
                username=config.wordpress_username,
                app_password=config.wordpress_app_password,
            )
        else:
            provider = NullArticleProvider()

        output_dir = (base_dir / config.output_dir) if base_dir else Path(config.output_dir)
        repository = RewriteRepository(output_dir)

        return cls(
            config=config,
            provider=provider,
            client=client,
            repository=repository,
        )

    def is_available(self) -> bool:
        """サービスが利用可能な状態かを返す。"""
        return self._config.is_ready() and self._client.is_available()

    def rewrite(self, suggestion: ImprovementSuggestion) -> RewriteResult:
        """
        ImprovementSuggestion から改善版記事（Rewrite Draft）を生成し、保存する。

        article_content が空文字（WordPress 認証情報なし等）でも処理を継続する。
        失敗時は success=False の RewriteResult を返して処理を継続する。

        Args:
            suggestion: 改善提案（ImprovementSuggestion）

        Returns:
            RewriteResult: リライト結果。失敗時は success=False の result。
        """
        article_id = suggestion.article_id
        title = suggestion.title
        permalink = suggestion.permalink

        try:
            # 元記事の取得（失敗しても空文字で継続）
            article_content = self._provider.fetch(
                article_id=article_id,
                permalink=permalink,
            )

            prompt = self._builder.build(suggestion, article_content)
            raw_response = self._client.send(prompt)
            result = self._parser.parse(
                raw_response=raw_response,
                article_id=article_id,
                title=title,
                permalink=permalink,
                prompt_version=self._builder.prompt_version,
                original_content=article_content,
            )
            self._repository.save(result)
            return result

        except Exception as e:
            print(f"  [REWRITE WARNING] リライトエラー（処理継続）: {e}")
            result = RewriteResult.empty(
                article_id=article_id,
                title=title,
                permalink=permalink,
                prompt_version=self._builder.prompt_version,
                error_message=f"リライト処理エラー: {e}",
            )
            self._repository.save(result)
            return result

    def rewrite_batch(
        self,
        suggestions: list[ImprovementSuggestion],
        max_articles: int | None = None,
    ) -> list[RewriteResult]:
        """
        複数の ImprovementSuggestion に対してリライトを実行する。

        Args:
            suggestions:   処理する改善提案のリスト
            max_articles:  最大処理件数（None = config の max_articles を使用）

        Returns:
            list[RewriteResult]: リライト結果のリスト（success=False も含む）
        """
        limit = max_articles if max_articles is not None else self._config.max_articles
        results: list[RewriteResult] = []

        for suggestion in suggestions:
            if len(results) >= limit:
                print(f"  [REWRITE] 上限 {limit} 件に達しました。残りはスキップします。")
                break

            print(f"  [REWRITE] リライト生成中: {suggestion.article_id}")
            result = self.rewrite(suggestion)
            results.append(result)

        return results


class NullRewriteService:
    """
    AI_REWRITE_ENABLED=false のときに返されるダミー実装（デフォルト）。
    すべてのメソッドが no-op で動作する。
    既存処理を停止させない。
    """

    def is_available(self) -> bool:
        return False

    def rewrite(self, suggestion: ImprovementSuggestion) -> RewriteResult:
        print("  [REWRITE] AI リライトは無効です（AI_REWRITE_ENABLED=false）")
        return RewriteResult.empty(
            article_id=getattr(suggestion, "article_id", ""),
            title=getattr(suggestion, "title", ""),
            permalink=getattr(suggestion, "permalink", None),
            prompt_version="v1",
            error_message="AI リライトが無効です（AI_REWRITE_ENABLED=false）",
        )

    def rewrite_batch(
        self,
        suggestions: list,
        max_articles: int | None = None,
    ) -> list:
        print("  [REWRITE] AI リライトは無効です（AI_REWRITE_ENABLED=false）")
        return []
