"""
AI 改善提案レビューサービス（v1.15.0）

Single Responsibility:
    - ImprovementRepository から改善提案を取得する
    - ImprovementReportBuilder で Markdown レポートを生成する
    - outputs/ai_improvement_reports/ へレポートを保存する

禁止事項:
    - Claude API の呼び出し
    - JSON ファイルの直接読み込み（ImprovementRepository の責務）
    - Markdown 生成ロジック（ImprovementReportBuilder の責務）
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from .improvement_repository import ImprovementRepository
from .improvement_report_builder import ImprovementReportBuilder
from .improvement_suggestion import ImprovementSuggestion


class ImprovementReviewService:
    """
    改善提案 JSON を読み込み、Markdown レポートを生成・保存するサービス。

    処理フロー:
        ImprovementRepository（JSON読み込み）
            → ImprovementReportBuilder（Markdown生成）
            → outputs/ai_improvement_reports/ へ保存
    """

    def __init__(
        self,
        repository: ImprovementRepository,
        report_dir: Path,
    ):
        self._repository = repository
        self._report_dir = report_dir
        self._builder = ImprovementReportBuilder()

    @classmethod
    def from_paths(
        cls,
        improvement_dir: str | Path = "outputs/ai_improvements",
        report_dir: str | Path = "outputs/ai_improvement_reports",
        base_dir: Path | None = None,
    ) -> "ImprovementReviewService":
        """
        パスから ImprovementReviewService を構築する。

        Args:
            improvement_dir: 改善提案 JSON の格納ディレクトリ
            report_dir:      Markdown レポートの保存先ディレクトリ
            base_dir:        相対パスの基準ディレクトリ（None の場合はそのまま使用）
        """
        if base_dir is not None:
            imp_dir = base_dir / improvement_dir
            rep_dir = base_dir / report_dir
        else:
            imp_dir = Path(improvement_dir)
            rep_dir = Path(report_dir)

        return cls(
            repository=ImprovementRepository(imp_dir),
            report_dir=rep_dir,
        )

    def run(
        self,
        priority: str | None = None,
        prompt_version: str | None = None,
        article_id: str | None = None,
    ) -> Path | None:
        """
        改善提案 JSON を読み込み、Markdown レポートを生成・保存する。

        Args:
            priority:       絞り込む優先度（None = 全件）
            prompt_version: 絞り込むプロンプトバージョン（None = 全件）
            article_id:     絞り込む記事ID（None = 全件）

        Returns:
            Path: 保存したレポートファイルのパス。保存失敗時は None。
        """
        suggestions = self._repository.load_all()

        if article_id is not None:
            suggestions = [s for s in suggestions if s.article_id == article_id]
        if priority is not None:
            suggestions = self._repository.filter_by_priority(suggestions, priority)
        if prompt_version is not None:
            suggestions = self._repository.filter_by_prompt_version(suggestions, prompt_version)

        print(f"  [REVIEW] 対象: {len(suggestions)} 件の改善提案")

        report_content = self._builder.build(suggestions)
        return self._save_report(report_content)

    def get_suggestions(
        self,
        priority: str | None = None,
        prompt_version: str | None = None,
        article_id: str | None = None,
    ) -> list[ImprovementSuggestion]:
        """
        条件に一致する改善提案リストを返す（レポート保存なし）。

        Args:
            priority:       絞り込む優先度（None = 全件）
            prompt_version: 絞り込むプロンプトバージョン（None = 全件）
            article_id:     絞り込む記事ID（None = 全件）

        Returns:
            list[ImprovementSuggestion]: 条件に一致する改善提案
        """
        suggestions = self._repository.load_all()

        if article_id is not None:
            suggestions = [s for s in suggestions if s.article_id == article_id]
        if priority is not None:
            suggestions = self._repository.filter_by_priority(suggestions, priority)
        if prompt_version is not None:
            suggestions = self._repository.filter_by_prompt_version(suggestions, prompt_version)

        return suggestions

    def _save_report(self, content: str) -> Path | None:
        """Markdown レポートを outputs/ai_improvement_reports/ に保存する。"""
        try:
            self._report_dir.mkdir(parents=True, exist_ok=True)
            date_str = date.today().strftime("%Y%m%d")
            filename = f"{date_str}_ai_improvement_report.md"
            path = self._report_dir / filename
            with path.open("w", encoding="utf-8") as f:
                f.write(content)
            print(f"  [REVIEW] レポート保存: {path}")
            return path
        except OSError as e:
            print(f"  [REVIEW WARNING] レポート保存失敗: {e}")
            return None
