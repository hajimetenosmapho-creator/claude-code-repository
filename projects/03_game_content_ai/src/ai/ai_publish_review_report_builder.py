"""
AI 公開レビュー結果の Markdown レポートを生成するモジュール（v1.19.0）

Single Responsibility:
    AiPublishReviewResult のリストから Markdown レポートを生成する。
    人が公開判断するために必要な情報を分かりやすく整理する。

禁止事項:
    - ファイル I/O（保存は AiPublishReviewService の責務）
    - WordPress API の呼び出し
    - AiPublishReviewResult の生成（Service の責務）
"""
from __future__ import annotations

from datetime import datetime

from .ai_publish_review_result import AiPublishReviewResult, PublishReviewStatus

REVIEW_STATUS_LABELS = {
    PublishReviewStatus.PENDING:  "⏳ pending（未判断）",
    PublishReviewStatus.APPROVED: "✅ approved（公開承認）",
    PublishReviewStatus.ON_HOLD:  "🔵 on_hold（保留）",
    PublishReviewStatus.REJECTED: "❌ rejected（却下）",
}


class AiPublishReviewReportBuilder:
    """AiPublishReviewResult のリストから Markdown レポートを生成するクラス。"""

    def build(self, results: list[AiPublishReviewResult]) -> str:
        """
        AiPublishReviewResult のリストから Markdown レポートを生成する。

        Args:
            results: AiPublishReviewResult のリスト（空リストも許容）

        Returns:
            str: Markdown 形式のレポート文字列
        """
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        lines: list[str] = []

        lines.append("# AI Publish Review レポート")
        lines.append("")
        lines.append(f"**生成日時**: {now}")
        lines.append("")

        if not results:
            lines.append("対象なし（投稿結果: 0 件）")
            lines.append("")
            lines.append("> `outputs/ai_publishes/` に投稿結果がありません。")
            lines.append("> 先に `scripts/run_ai_publish.py` を実行してください。")
            lines.append("")
            return "\n".join(lines)

        candidates = [r for r in results if r.is_publish_candidate]
        skipped    = [r for r in results if r.publish_skipped]
        failed     = [r for r in results if not r.publish_success and not r.publish_skipped]

        pending  = sum(1 for r in results if r.review_status == PublishReviewStatus.PENDING)
        approved = sum(1 for r in results if r.review_status == PublishReviewStatus.APPROVED)
        on_hold  = sum(1 for r in results if r.review_status == PublishReviewStatus.ON_HOLD)
        rejected = sum(1 for r in results if r.review_status == PublishReviewStatus.REJECTED)

        lines.append("## サマリー")
        lines.append("")
        lines.append(f"- **処理件数**: {len(results)} 件")
        lines.append(f"- 公開候補 (投稿成功): {len(candidates)} 件")
        lines.append(f"- **スキップ**: {len(skipped)} 件")
        lines.append(f"- **投稿失敗**: {len(failed)} 件")
        lines.append(
            f"- **公開判断**: pending {pending} 件 / approved {approved} 件"
            f" / on_hold {on_hold} 件 / rejected {rejected} 件"
        )
        lines.append("")

        if candidates:
            lines.append("---")
            lines.append("")
            lines.append("## 公開候補（投稿成功）")
            lines.append("")
            lines.append(
                "> これらの記事は WordPress 下書きへの投稿が完了しています。  "
            )
            lines.append("> 内容を確認し、公開判断を行ってください。")
            lines.append("")
            for r in candidates:
                lines.extend(self._build_candidate_section(r))

        if skipped:
            lines.append("---")
            lines.append("")
            lines.append("## スキップ一覧")
            lines.append("")
            for r in skipped:
                lines.extend(self._build_skipped_section(r))

        if failed:
            lines.append("---")
            lines.append("")
            lines.append("## 投稿失敗一覧")
            lines.append("")
            for r in failed:
                lines.extend(self._build_failed_section(r))

        lines.append("---")
        lines.append("")
        lines.append("> このレポートは公開前確認用です。WordPress への公開操作は含まれません。")
        lines.append(f"  \n*生成日時: {now}*")
        lines.append("")

        return "\n".join(lines)

    def _build_candidate_section(self, r: AiPublishReviewResult) -> list[str]:
        """公開候補（投稿成功）の1件分を生成する。"""
        lines: list[str] = []
        lines.append(f"### {r.title}")
        lines.append("")
        lines.append(f"- **記事ID**: `{r.article_id}`")
        lines.append(f"- **元記事URL**: {r.original_permalink or '不明'}")
        if r.wp_edit_url:
            lines.append(f"- **下書き編集URL**: {r.wp_edit_url}")
        if r.wp_draft_permalink:
            lines.append(f"- **下書きプレビューURL**: {r.wp_draft_permalink}")
        lines.append(f"- **WordPress 投稿ID**: {r.wp_post_id}")
        lines.append(f"- **下書きスラッグ**: {r.wp_draft_slug}")
        lines.append(f"- **投稿日時**: {r.published_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"- **公開判断**: {REVIEW_STATUS_LABELS[r.review_status]}")
        if r.review_note:
            lines.append(f"- **レビューメモ**: {r.review_note}")
        lines.append("")
        return lines

    def _build_skipped_section(self, r: AiPublishReviewResult) -> list[str]:
        """スキップの1件分を生成する。"""
        lines: list[str] = []
        lines.append(f"### {r.title}")
        lines.append("")
        lines.append(f"- **記事ID**: `{r.article_id}`")
        lines.append(f"- **スキップ理由**: {r.publish_skip_reason or '不明'}")
        lines.append(f"- **元リライトレビュー状態**: {r.source_review_status}")
        lines.append(f"- **公開判断**: {REVIEW_STATUS_LABELS[r.review_status]}")
        lines.append("")
        return lines

    def _build_failed_section(self, r: AiPublishReviewResult) -> list[str]:
        """投稿失敗の1件分を生成する。"""
        lines: list[str] = []
        lines.append(f"### {r.title}")
        lines.append("")
        lines.append(f"- **記事ID**: `{r.article_id}`")
        lines.append(f"- **エラー内容**: {r.publish_error or '不明'}")
        lines.append(f"- **元リライトレビュー状態**: {r.source_review_status}")
        lines.append(f"- **公開判断**: {REVIEW_STATUS_LABELS[r.review_status]}")
        lines.append("")
        return lines
