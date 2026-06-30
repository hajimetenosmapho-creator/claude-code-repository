"""
AI 公開サービス（v1.18.0）

Single Responsibility:
    - AiPublishRepository から採用済みレビューを取得する
    - 重複チェックを経て投稿対象を選別する
    - WordPressDraftClient で WordPress 下書き投稿を実行する
    - AiPublishResult を生成して保存する
    - AiPublishReportBuilder で Markdown レポートを生成・保存する

禁止事項:
    - Claude API の呼び出し
    - JSON ファイルの直接読み書き（Repository の責務）
    - Markdown 生成ロジック（AiPublishReportBuilder の責務）
    - WordPress への publish（draft のみ）

設計方針（Configuration First / Null Object Pattern）:
    AI_PUBLISH_ENABLED=false → NullAiPublishService を返す
    WordPress 認証情報未設定  → NullAiPublishService を返す
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from .ai_publish_config import AiPublishConfig
from .ai_publish_report_builder import AiPublishReportBuilder
from .ai_publish_repository import AiPublishRepository
from .ai_publish_result import AiPublishResult
from .rewrite_result import RewriteResult
from .rewrite_review_result import RewriteReviewResult
from .wordpress_draft_client import NullWordPressDraftClient, WordPressDraftClient


class AiPublishService:
    """
    採用済みリライト案を WordPress 下書きとして投稿するサービス。

    処理フロー:
        AiPublishRepository.load_adopted_reviews()
            → _dedup_by_article_id()             → 同一記事は最新レビューのみ残す
            → filter_unpublished()                → 未投稿のみ対象
            → load_rewrite_by_article_id()        → リライト本文を取得
            → WordPressDraftClient.post_draft()   → WordPress 下書き投稿
            → AiPublishResult を生成
            → AiPublishRepository.save()          → JSON 保存
            → AiPublishReportBuilder.build()      → Markdown 生成
            → _save_report()                      → Markdown 保存
    """

    def __init__(
        self,
        repository: AiPublishRepository,
        client: "WordPressDraftClient | NullWordPressDraftClient",
        report_dir: Path,
    ):
        self._repository = repository
        self._client     = client
        self._report_dir = report_dir
        self._builder    = AiPublishReportBuilder()

    @classmethod
    def from_env(
        cls,
        base_dir: Path | None = None,
    ) -> "AiPublishService | NullAiPublishService":
        """
        環境変数から設定を読み込み、AiPublishService または NullAiPublishService を返す。

        is_ready() が False の場合（enabled=False または認証情報不足）は
        NullAiPublishService を返す。
        """
        config = AiPublishConfig.from_env()
        if not config.is_ready():
            return NullAiPublishService()

        client = WordPressDraftClient(
            url=config.wordpress_url or "",
            username=config.wordpress_username or "",
            app_password=config.wordpress_app_password or "",
        )
        repository = AiPublishRepository.from_paths(base_dir=base_dir)
        report_dir = (
            (base_dir / "outputs/ai_publish_reports")
            if base_dir is not None
            else Path("outputs/ai_publish_reports")
        )
        return cls(repository=repository, client=client, report_dir=report_dir)

    def run(self, article_id: str | None = None) -> Path | None:
        """
        採用済みリライト案を WordPress 下書きとして投稿する。

        Args:
            article_id: 絞り込む記事ID（None = 全件）

        Returns:
            Path: 保存した Markdown レポートのパス。保存失敗時は None。
        """
        adopted = self._repository.load_adopted_reviews()
        if article_id is not None:
            adopted = [r for r in adopted if r.article_id == article_id]

        # 同一 article_id で最新のレビューのみ残す（reviewed_at 降順なので先頭が最新）
        unique_adopted = _dedup_by_article_id(adopted)

        targets = self._repository.filter_unpublished(unique_adopted)
        print(f"  [PUBLISH] 採用済み: {len(unique_adopted)} 件 → 未投稿: {len(targets)} 件")

        results: list[AiPublishResult] = []
        for review in targets:
            result = self._process(review)
            self._repository.save(result)
            results.append(result)

        report_content = self._builder.build(results)
        return self._save_report(report_content)

    def get_results(self, article_id: str | None = None) -> list[AiPublishResult]:
        """
        保存済みの投稿結果を返す（レポート保存なし）。

        Args:
            article_id: 絞り込む記事ID（None = 全件）

        Returns:
            list[AiPublishResult]: 投稿結果のリスト
        """
        results = self._repository.load_publish_results()
        if article_id is not None:
            return [r for r in results if r.article_id == article_id]
        return results

    def _process(self, review: RewriteReviewResult) -> AiPublishResult:
        """
        1件のレビューを処理し、AiPublishResult を生成する。

        リライト結果が見つからない場合は success=False として返す。
        """
        rewrite = self._repository.load_rewrite_by_article_id(review.article_id)
        if rewrite is None:
            print(f"  [PUBLISH WARNING] リライト結果が見つかりません: {review.article_id}")
            return AiPublishResult(
                article_id=review.article_id,
                title=review.title,
                original_permalink=review.permalink,
                source_review_status=review.review_status.value,
                source_rewrite_created_at=None,
                success=False,
                error_message="リライト結果が見つかりません",
            )

        return self._post(review, rewrite)

    def _post(
        self,
        review: RewriteReviewResult,
        rewrite: RewriteResult,
    ) -> AiPublishResult:
        """
        WordPressDraftClient を呼び出し、AiPublishResult を生成する。

        スラッグ形式: {article_id}-rewrite-{YYYYMMDD}（元記事と重複しない）
        """
        new_slug = f"{review.article_id}-rewrite-{date.today().strftime('%Y%m%d')}"

        try:
            response = self._client.post_draft(
                title=review.title,
                content=rewrite.rewrite_draft,
                slug=new_slug,
            )
        except RuntimeError as e:
            print(f"  [PUBLISH WARNING] 投稿失敗（処理継続）: {review.article_id} - {e}")
            return AiPublishResult(
                article_id=review.article_id,
                title=review.title,
                original_permalink=review.permalink,
                source_review_status=review.review_status.value,
                source_rewrite_created_at=rewrite.created_at,
                success=False,
                error_message=str(e),
            )

        if response.get("skipped"):
            print(f"  [PUBLISH] スキップ: {review.article_id} ({response.get('reason')})")
            return AiPublishResult(
                article_id=review.article_id,
                title=review.title,
                original_permalink=review.permalink,
                source_review_status=review.review_status.value,
                source_rewrite_created_at=rewrite.created_at,
                skipped=True,
                skip_reason=response.get("reason"),
                success=False,
            )

        print(f"  [PUBLISH] 成功: {review.article_id} → post_id={response.get('post_id')}")
        return AiPublishResult(
            article_id=review.article_id,
            title=review.title,
            original_permalink=review.permalink,
            source_review_status=review.review_status.value,
            source_rewrite_created_at=rewrite.created_at,
            wp_post_id=response.get("post_id"),
            wp_draft_slug=response.get("slug"),
            wp_edit_url=response.get("edit_url"),
            wp_draft_permalink=response.get("permalink"),
            success=True,
        )

    def _save_report(self, content: str) -> Path | None:
        """Markdown レポートを report_dir に保存する。"""
        try:
            self._report_dir.mkdir(parents=True, exist_ok=True)
            date_str = date.today().strftime("%Y%m%d")
            filename = f"{date_str}_ai_publish_report.md"
            path = self._report_dir / filename
            with path.open("w", encoding="utf-8") as f:
                f.write(content)
            print(f"  [PUBLISH] レポート保存: {path}")
            return path
        except OSError as e:
            print(f"  [PUBLISH WARNING] レポート保存失敗: {e}")
            return None


class NullAiPublishService:
    """
    AI_PUBLISH_ENABLED=false または WordPress 認証情報未設定時のダミー実装。
    すべてのメソッドが no-op で動作する。既存処理を停止させない。
    """

    def run(self, article_id: str | None = None) -> None:
        print("  [PUBLISH] AI 公開機能が無効です（AI_PUBLISH_ENABLED=false または認証情報未設定）。")
        return None

    def get_results(self, article_id: str | None = None) -> list:
        return []


def _dedup_by_article_id(reviews: list[RewriteReviewResult]) -> list[RewriteReviewResult]:
    """
    同一 article_id の中で最初のもの（reviewed_at 降順なので最新）のみ残す。
    """
    seen: set[str] = set()
    result: list[RewriteReviewResult] = []
    for review in reviews:
        if review.article_id not in seen:
            result.append(review)
            seen.add(review.article_id)
    return result
