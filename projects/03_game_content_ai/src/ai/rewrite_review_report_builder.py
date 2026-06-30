"""
RewriteReviewResult を Markdown レポートに変換するモジュール（v1.17.0）

Single Responsibility:
    - RewriteReviewResult のリストを受け取り Markdown 文字列を生成する
    - ステータス別（PENDING / ADOPTED / ON_HOLD / REJECTED）に整理する
    - 人間がレビューしやすい形式で出力する

禁止事項:
    - Claude API の呼び出し
    - ファイルへの書き込み（RewriteReviewService の責務）
    - RewriteReviewResult の生成（Service の責務）
    - diff_summary の生成（Service の責務）
"""
from __future__ import annotations

from datetime import datetime

from .rewrite_review_result import ReviewStatus, RewriteReviewResult

STATUS_ORDER = (
    ReviewStatus.PENDING,
    ReviewStatus.ADOPTED,
    ReviewStatus.ON_HOLD,
    ReviewStatus.REJECTED,
)

STATUS_LABELS = {
    ReviewStatus.PENDING:  "⏳ Pending（未レビュー）",
    ReviewStatus.ADOPTED:  "✅ Adopted（採用）",
    ReviewStatus.ON_HOLD:  "🔵 On Hold（保留）",
    ReviewStatus.REJECTED: "❌ Rejected（却下）",
}


class RewriteReviewReportBuilder:
    """
    RewriteReviewResult のリストを Markdown レポートに変換するクラス。

    出力形式:
        - ヘッダー（生成日時・件数・ステータス別件数）
        - ステータス別サマリー
        - ステータス別詳細（PENDING → ADOPTED → ON_HOLD → REJECTED の順）
    """

    def build(self, reviews: list[RewriteReviewResult]) -> str:
        """
        レビュー結果リストから Markdown レポートを生成する。

        Args:
            reviews: RewriteReviewResult のリスト

        Returns:
            str: Markdown 形式のレポート文字列
        """
        now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        total = len(reviews)

        by_status: dict[ReviewStatus, list[RewriteReviewResult]] = {s: [] for s in STATUS_ORDER}
        for r in reviews:
            by_status[r.review_status].append(r)

        sections: list[str] = []
        sections.append(self._build_header(now, total, by_status))
        sections.append(self._build_summary(by_status))

        for status in STATUS_ORDER:
            items = by_status[status]
            if items:
                sections.append(self._build_status_section(status, items))

        sections.append(f"\n---\n*生成日時: {now}*\n")
        return "\n".join(sections)

    def _build_header(
        self,
        now: str,
        total: int,
        by_status: dict[ReviewStatus, list[RewriteReviewResult]],
    ) -> str:
        pending  = len(by_status[ReviewStatus.PENDING])
        adopted  = len(by_status[ReviewStatus.ADOPTED])
        on_hold  = len(by_status[ReviewStatus.ON_HOLD])
        rejected = len(by_status[ReviewStatus.REJECTED])
        return (
            f"# AI リライトレビューレポート\n\n"
            f"**生成日時**: {now}  \n"
            f"**対象記事数**: {total} 件  \n"
            f"**pending**: {pending} 件 / **adopted**: {adopted} 件 / "
            f"**on_hold**: {on_hold} 件 / **rejected**: {rejected} 件"
        )

    def _build_summary(
        self,
        by_status: dict[ReviewStatus, list[RewriteReviewResult]],
    ) -> str:
        lines = ["## ステータス別サマリー", ""]
        for status in STATUS_ORDER:
            items = by_status[status]
            label = STATUS_LABELS[status]
            lines.append(f"### {label}")
            if not items:
                lines.append("*対象なし*")
                lines.append("")
                continue
            for r in items:
                title_display = r.title or r.article_id
                summary_short = (
                    r.improvement_summary[:60] + "…"
                    if len(r.improvement_summary) > 60
                    else r.improvement_summary
                )
                if r.success and r.original_char_count > 0:
                    sign = "+" if r.char_diff >= 0 else ""
                    diff_str = f"（{sign}{r.char_diff:,}字 / {sign}{r.change_ratio:.1%}）"
                else:
                    diff_str = "（リライト失敗）" if not r.success else "（元記事なし）"
                lines.append(f"- **{title_display}** — {summary_short}{diff_str}")
            lines.append("")
        return "\n".join(lines)

    def _build_status_section(
        self,
        status: ReviewStatus,
        items: list[RewriteReviewResult],
    ) -> str:
        label = STATUS_LABELS[status]
        lines = [f"## {label}", ""]
        for r in items:
            lines.append(self._build_article_section(r))
        return "\n".join(lines)

    def _build_article_section(self, r: RewriteReviewResult) -> str:
        title_display = r.title or r.article_id
        lines = [f"### {title_display}", ""]

        lines.append("| 項目 | 値 |")
        lines.append("|------|-----|")
        lines.append(f"| 記事ID | `{r.article_id}` |")
        if r.permalink:
            lines.append(f"| URL | [{r.permalink}]({r.permalink}) |")
        else:
            lines.append("| URL | *(なし)* |")
        lines.append(f"| ステータス | {r.review_status.value} |")

        if not r.success:
            lines.append("| 生成状態 | ⚠️ リライト失敗 |")
        else:
            sign      = "+" if r.char_diff >= 0 else ""
            line_sign = "+" if r.line_diff >= 0 else ""
            lines.append(f"| 元記事文字数 | {r.original_char_count:,} 字 |")
            lines.append(
                f"| リライト文字数 | {r.rewrite_char_count:,} 字"
                f"（{sign}{r.char_diff:,}字 / **{sign}{r.change_ratio:.1%}**） |"
            )
            lines.append(f"| 元記事行数 | {r.original_line_count:,} 行 |")
            lines.append(
                f"| リライト行数 | {r.rewrite_line_count:,} 行"
                f"（{line_sign}{r.line_diff:,}行） |"
            )
            lines.append(f"| 変更点件数 | {r.changes_count} 件 |")

        lines.append(f"| 生成日時 | {r.created_at.strftime('%Y-%m-%d %H:%M')} |")
        lines.append("")

        if r.review_note:
            lines.append("**レビューメモ**")
            lines.append(f"> {r.review_note}")
            lines.append("")

        if not r.success:
            lines.append("**エラー**")
            lines.append("> リライト生成に失敗しました。差分情報はありません。")
            lines.append("")
            lines.append("---")
            lines.append("")
            return "\n".join(lines)

        if r.improvement_summary:
            lines.append("**改善サマリー**")
            lines.append(f"> {r.improvement_summary}")
            lines.append("")

        if r.diff_summary:
            lines.append("**差分サマリー**")
            for item in r.diff_summary:
                lines.append(f"- {item}")
            lines.append("")

        lines.append("---")
        lines.append("")
        return "\n".join(lines)
