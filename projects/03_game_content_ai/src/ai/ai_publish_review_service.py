"""
AI 公開レビューサービス（v1.19.0）

Single Responsibility:
    - AiPublishReviewRepository から AiPublishResult を取得する
    - AiPublishReviewResult を生成して保存する
    - AiPublishReviewReportBuilder で Markdown レポートを生成・保存する

禁止事項:
    - Claude API の呼び出し（このサービスは AI を使わない）
    - WordPress API の呼び出し（読み取り・確認のみ）
    - JSON ファイルの直接読み書き（Repository の責務）
    - Markdown 生成ロジック（AiPublishReviewReportBuilder の責務）
    - 元記事・WordPress 下書きの変更（非破壊・非更新）

設計方針（Null Object Pattern）:
    NullAiPublishReviewService は「明示的な無効化」時のみ使用する。
    outputs/ai_publishes/ が空・存在しない場合でも通常の Service が動作し、
    「対象なし」レポートを生成する。
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from .ai_publish_review_report_builder import AiPublishReviewReportBuilder
from .ai_publish_review_repository import AiPublishReviewRepository
from .ai_publish_review_result import AiPublishReviewResult, PublishReviewStatus


class AiPublishReviewService:
    """
    投稿結果を読み込み、公開前レビュー結果を生成・保存するサービス。

    処理フロー:
        AiPublishReviewRepository.load_publish_results()
            → AiPublishReviewResult.from_publish_result()   → review_status=PENDING で生成
            → AiPublishReviewRepository.save_review()        → JSON 保存
            → AiPublishReviewReportBuilder.build()           → Markdown 生成
            → _save_report()                                 → Markdown 保存
    """

    def __init__(
        self,
        repository: AiPublishReviewRepository,
        report_dir: Path,
    ):
        self._repository = repository
        self._report_dir = report_dir
        self._builder    = AiPublishReviewReportBuilder()

    @classmethod
    def from_paths(
        cls,
        publish_dir: str | Path = "outputs/ai_publishes",
        review_dir:  str | Path = "outputs/ai_publish_reviews",
        report_dir:  str | Path = "outputs/ai_publish_review_reports",
        base_dir: Path | None = None,
    ) -> "AiPublishReviewService":
        """
        パスから AiPublishReviewService を構築する。

        データが 0 件・ディレクトリ不存在でも常に AiPublishReviewService を返す。
        0 件の場合は run() 内で「対象なし」レポートを生成して正常終了する。

        Args:
            publish_dir: 投稿結果 JSON の格納ディレクトリ（読み取りのみ）
            review_dir:  レビュー結果 JSON の保存先ディレクトリ
            report_dir:  Markdown レポートの保存先ディレクトリ
            base_dir:    相対パスの基準ディレクトリ（None の場合はそのまま使用）
        """
        rep_dir = (base_dir / report_dir) if base_dir is not None else Path(report_dir)

        repository = AiPublishReviewRepository.from_paths(
            publish_dir=publish_dir,
            review_dir=review_dir,
            base_dir=base_dir,
        )
        return cls(repository=repository, report_dir=rep_dir)

    def run(self, article_id: str | None = None) -> Path | None:
        """
        投稿結果を読み込み、公開前レビュー結果 JSON と Markdown レポートを生成・保存する。

        投稿結果が 0 件の場合は「対象なし」レポートを生成して正常終了する。

        Args:
            article_id: 絞り込む記事ID（None = 全件）

        Returns:
            Path: 保存した Markdown レポートのパス。保存失敗時は None。
        """
        publish_results = self._repository.load_publish_results(article_id=article_id)
        print(f"  [PUBLISH REVIEW] 対象: {len(publish_results)} 件の投稿結果")

        reviews: list[AiPublishReviewResult] = []
        for result in publish_results:
            review = AiPublishReviewResult.from_publish_result(result)
            self._repository.save_review(review)
            reviews.append(review)

        report_content = self._builder.build(reviews)
        return self._save_report(report_content)

    def get_reviews(self, article_id: str | None = None) -> list[AiPublishReviewResult]:
        """
        保存済みのレビュー結果を返す（レポート保存なし）。

        Args:
            article_id: 絞り込む記事ID（None = 全件）

        Returns:
            list[AiPublishReviewResult]: レビュー結果のリスト
        """
        if article_id is not None:
            return self._repository.load_reviews_by_article_id(article_id)
        return self._repository.load_reviews()

    def _save_report(self, content: str) -> Path | None:
        """Markdown レポートを report_dir に保存する。"""
        try:
            self._report_dir.mkdir(parents=True, exist_ok=True)
            date_str = date.today().strftime("%Y%m%d")
            filename = f"{date_str}_ai_publish_review_report.md"
            path     = self._report_dir / filename
            with path.open("w", encoding="utf-8") as f:
                f.write(content)
            print(f"  [PUBLISH REVIEW] レポート保存: {path}")
            return path
        except OSError as e:
            print(f"  [PUBLISH REVIEW WARNING] レポート保存失敗: {e}")
            return None


class NullAiPublishReviewService:
    """
    AI 公開レビューが明示的に無効化されている場合の no-op 実装。

    用途:
        - 将来の明示的な無効化（AI_PUBLISH_REVIEW_ENABLED=false 等の設定時）
        - テスト用モック（処理を何もしないことを保証したい単体テスト）
        - DI で no-op 動作を差し込みたい場合

    注意:
        outputs/ai_publishes/ の有無によって自動で使われることはない。
        データ 0 件の場合は AiPublishReviewService が「対象なし」レポートを生成する。
    """

    def run(self, article_id: str | None = None) -> None:
        print("  [PUBLISH REVIEW] AI 公開レビュー機能が無効です。")
        return None

    def get_reviews(self, article_id: str | None = None) -> list:
        return []
