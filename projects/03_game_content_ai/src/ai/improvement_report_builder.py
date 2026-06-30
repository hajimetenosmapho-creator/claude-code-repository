"""
AI 改善提案を Markdown レポートに変換するモジュール（v1.15.0）

Single Responsibility:
    - ImprovementSuggestion のリストを受け取り Markdown 文字列を生成する
    - 優先度別（high / medium / low）に整理する
    - 人間がレビューしやすい形式で出力する

禁止事項:
    - Claude API の呼び出し
    - ファイルへの書き込み（ImprovementReviewService の責務）
    - ImprovementSuggestion の生成（ImprovementRepository の責務）
"""
from __future__ import annotations

from datetime import datetime

from .improvement_suggestion import ImprovementSuggestion

PRIORITY_ORDER = ("high", "medium", "low")
PRIORITY_LABELS = {
    "high": "🔴 High（優先対応）",
    "medium": "🟡 Medium（改善推奨）",
    "low": "🟢 Low（軽微）",
}


class ImprovementReportBuilder:
    """
    ImprovementSuggestion のリストを Markdown レポートに変換するクラス。

    出力形式:
        - ヘッダー（生成日時・件数）
        - 優先度別サマリー
        - 優先度別詳細（high → medium → low の順）
    """

    def build(self, suggestions: list[ImprovementSuggestion]) -> str:
        """
        改善提案リストから Markdown レポートを生成する。

        Args:
            suggestions: ImprovementSuggestion のリスト

        Returns:
            str: Markdown 形式のレポート文字列
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total = len(suggestions)

        by_priority: dict[str, list[ImprovementSuggestion]] = {p: [] for p in PRIORITY_ORDER}
        for s in suggestions:
            priority = s.priority if s.priority in PRIORITY_ORDER else "low"
            by_priority[priority].append(s)

        sections: list[str] = []
        sections.append(self._build_header(now, total, by_priority))
        sections.append(self._build_summary(by_priority))

        for priority in PRIORITY_ORDER:
            items = by_priority[priority]
            if items:
                sections.append(self._build_priority_section(priority, items))

        sections.append(f"\n---\n*生成日時: {now}*\n")
        return "\n".join(sections)

    def _build_header(
        self,
        now: str,
        total: int,
        by_priority: dict[str, list[ImprovementSuggestion]],
    ) -> str:
        high = len(by_priority["high"])
        medium = len(by_priority["medium"])
        low = len(by_priority["low"])
        return (
            f"# AI 改善提案レポート\n\n"
            f"**生成日時**: {now}  \n"
            f"**対象記事数**: {total} 件  \n"
            f"**High**: {high} 件 / **Medium**: {medium} 件 / **Low**: {low} 件"
        )

    def _build_summary(
        self,
        by_priority: dict[str, list[ImprovementSuggestion]],
    ) -> str:
        lines = ["## 優先度別サマリー", ""]
        for priority in PRIORITY_ORDER:
            items = by_priority[priority]
            label = PRIORITY_LABELS[priority]
            lines.append(f"### {label}")
            if not items:
                lines.append("*対象なし*")
                lines.append("")
                continue
            for s in items:
                title_display = s.title or s.article_id
                lines.append(f"- **{title_display}** — {s.summary[:80]}{'…' if len(s.summary) > 80 else ''}")
            lines.append("")
        return "\n".join(lines)

    def _build_priority_section(
        self,
        priority: str,
        items: list[ImprovementSuggestion],
    ) -> str:
        label = PRIORITY_LABELS[priority]
        lines = [f"## {label}", ""]
        for s in items:
            lines.append(self._build_article_section(s))
        return "\n".join(lines)

    def _build_article_section(self, s: ImprovementSuggestion) -> str:
        title_display = s.title or s.article_id
        lines = [f"### {title_display}", ""]

        lines.append(f"| 項目 | 値 |")
        lines.append(f"|------|-----|")
        lines.append(f"| 記事ID | `{s.article_id}` |")
        if s.permalink:
            lines.append(f"| URL | [{s.permalink}]({s.permalink}) |")
        else:
            lines.append(f"| URL | *(なし)* |")
        lines.append(f"| 優先度 | {s.priority} |")
        lines.append(f"| プロンプトバージョン | {s.prompt_version} |")
        lines.append(f"| 生成日時 | {s.created_at.strftime('%Y-%m-%d %H:%M')} |")
        lines.append("")

        lines.append(f"**概要**")
        lines.append(f"> {s.summary}" if s.summary else "> *(概要なし)*")
        lines.append("")

        if s.issues:
            lines.append("**検出された問題点**")
            for issue in s.issues:
                lines.append(f"- {issue}")
            lines.append("")

        if s.suggestions:
            lines.append("**改善提案**")
            for suggestion in s.suggestions:
                lines.append(f"- {suggestion}")
            lines.append("")

        if s.seo_title_suggestion:
            lines.append(f"**SEO タイトル改善案**")
            lines.append(f"> {s.seo_title_suggestion}")
            lines.append("")

        if s.meta_description_suggestion:
            lines.append(f"**メタディスクリプション改善案**")
            lines.append(f"> {s.meta_description_suggestion}")
            lines.append("")

        if s.internal_link_suggestions:
            lines.append("**内部リンク提案**")
            for link in s.internal_link_suggestions:
                lines.append(f"- {link}")
            lines.append("")

        lines.append("---")
        lines.append("")
        return "\n".join(lines)
