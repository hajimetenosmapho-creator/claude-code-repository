"""
AI リライトレビューサービス（v1.17.0）

Single Responsibility:
    - RewriteReviewRepository から RewriteResult を取得する
    - _generate_diff_summary() で差分サマリーを生成する
    - RewriteReviewResult を生成して保存する
    - RewriteReviewReportBuilder で Markdown レポートを生成・保存する

禁止事項:
    - Claude API の呼び出し（このサービスは AI を使わない）
    - JSON ファイルの直接読み書き（Repository の責務）
    - Markdown 生成ロジック（RewriteReviewReportBuilder の責務）

設計方針（Null Object Pattern）:
    NullRewriteReviewService は対象ファイルが存在しない・
    レビュー不要なケースで使用する no-op 実装。
    Claude API の ON/OFF とは無関係（このサービスは AI を呼ばない）。
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from .rewrite_result import RewriteResult
from .rewrite_review_report_builder import RewriteReviewReportBuilder
from .rewrite_review_repository import RewriteReviewRepository
from .rewrite_review_result import ReviewStatus, RewriteReviewResult


class RewriteReviewService:
    """
    リライト結果を読み込み、レビュー結果を生成・保存するサービス。

    処理フロー:
        RewriteReviewRepository.load_rewrite_results()
            → filter_by_success()               → 成功したリライトのみ対象
            → RewriteReviewResult.from_rewrite_result()
            → _generate_diff_summary()           → diff_summary を注入
            → RewriteReviewRepository.save_review()   → JSON 保存
            → RewriteReviewReportBuilder.build()       → Markdown 生成
            → _save_report()                           → Markdown 保存
    """

    def __init__(
        self,
        repository: RewriteReviewRepository,
        report_dir: Path,
    ):
        self._repository = repository
        self._report_dir = report_dir
        self._builder    = RewriteReviewReportBuilder()

    @classmethod
    def from_paths(
        cls,
        rewrite_dir: str | Path = "outputs/ai_rewrites",
        review_dir:  str | Path = "outputs/ai_rewrite_reviews",
        report_dir:  str | Path = "outputs/ai_rewrite_reports",
        base_dir: Path | None = None,
    ) -> "RewriteReviewService":
        """
        パスから RewriteReviewService を構築する。

        Args:
            rewrite_dir: リライト結果 JSON の格納ディレクトリ
            review_dir:  レビュー結果 JSON の保存先ディレクトリ
            report_dir:  Markdown レポートの保存先ディレクトリ
            base_dir:    相対パスの基準ディレクトリ（None の場合はそのまま使用）
        """
        rep_dir = (base_dir / report_dir) if base_dir is not None else Path(report_dir)

        return cls(
            repository=RewriteReviewRepository.from_paths(
                rewrite_dir=rewrite_dir,
                review_dir=review_dir,
                base_dir=base_dir,
            ),
            report_dir=rep_dir,
        )

    def run(self, article_id: str | None = None) -> Path | None:
        """
        リライト結果を読み込み、レビュー結果 JSON と Markdown レポートを生成・保存する。

        Args:
            article_id: 絞り込む記事ID（None = 全件）

        Returns:
            Path: 保存した Markdown レポートのパス。保存失敗時は None。
        """
        results = self._load_targets(article_id)
        print(f"  [REVIEW] 対象: {len(results)} 件のリライト結果")

        reviews: list[RewriteReviewResult] = []
        for result in results:
            review = self._create_review(result)
            self._repository.save_review(review)
            reviews.append(review)

        report_content = self._builder.build(reviews)
        return self._save_report(report_content)

    def get_reviews(self, article_id: str | None = None) -> list[RewriteReviewResult]:
        """
        保存済みのレビュー結果を返す（レポート保存なし）。

        Args:
            article_id: 絞り込む記事ID（None = 全件）

        Returns:
            list[RewriteReviewResult]: レビュー結果のリスト
        """
        if article_id is not None:
            return self._repository.load_review_by_article_id(article_id)
        return self._repository.load_reviews()

    def _load_targets(self, article_id: str | None) -> list[RewriteResult]:
        """対象の RewriteResult を読み込み、成功したもののみ返す。"""
        if article_id is not None:
            results = self._repository.load_rewrite_by_article_id(article_id)
        else:
            results = self._repository.load_rewrite_results()
        return self._repository.filter_by_success(results)

    def _create_review(
        self,
        result: RewriteResult,
        status: ReviewStatus = ReviewStatus.PENDING,
        note: str = "",
    ) -> RewriteReviewResult:
        """
        RewriteResult から RewriteReviewResult を生成する。
        diff_summary はここで生成して注入する。
        """
        diff_summary = self._generate_diff_summary(result)
        return RewriteReviewResult.from_rewrite_result(
            result=result,
            status=status,
            note=note,
            diff_summary=diff_summary,
        )

    def _generate_diff_summary(self, result: RewriteResult) -> list[str]:
        """
        RewriteResult から簡易差分サマリーを生成する（Foundation 版）。

        Foundation 段階では changes リストと数値変化（文字数・行数）を列挙する。
        将来のバージョンで difflib 等による行レベル差分に拡張予定。

        Args:
            result: リライト結果

        Returns:
            list[str]: 差分サマリーの文字列リスト
        """
        summary: list[str] = []

        for change in result.changes:
            summary.append(f"変更: {change}")

        original_chars = len(result.original_content)
        rewrite_chars  = len(result.rewrite_draft)
        char_diff      = rewrite_chars - original_chars
        char_sign      = "+" if char_diff >= 0 else ""
        summary.append(
            f"文字数: {original_chars:,}字 → {rewrite_chars:,}字"
            f"（{char_sign}{char_diff:,}字）"
        )

        original_lines = len(result.original_content.splitlines()) if result.original_content else 0
        rewrite_lines  = len(result.rewrite_draft.splitlines())    if result.rewrite_draft  else 0
        line_diff      = rewrite_lines - original_lines
        line_sign      = "+" if line_diff >= 0 else ""
        summary.append(
            f"行数: {original_lines}行 → {rewrite_lines}行"
            f"（{line_sign}{line_diff}行）"
        )

        return summary

    def _save_report(self, content: str) -> Path | None:
        """Markdown レポートを report_dir に保存する。"""
        try:
            self._report_dir.mkdir(parents=True, exist_ok=True)
            date_str = date.today().strftime("%Y%m%d")
            filename = f"{date_str}_ai_rewrite_review_report.md"
            path     = self._report_dir / filename
            with path.open("w", encoding="utf-8") as f:
                f.write(content)
            print(f"  [REVIEW] レポート保存: {path}")
            return path
        except OSError as e:
            print(f"  [REVIEW WARNING] レポート保存失敗: {e}")
            return None


class NullRewriteReviewService:
    """
    対象リライト結果が存在しない・レビュー不要な場合に使用するダミー実装。
    すべてのメソッドが no-op で動作する。既存処理を停止させない。
    """

    def run(self, article_id: str | None = None) -> None:
        print("  [REVIEW] リライトレビュー対象がありません。")
        return None

    def get_reviews(self, article_id: str | None = None) -> list:
        return []
