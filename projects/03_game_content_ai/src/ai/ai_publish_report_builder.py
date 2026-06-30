"""
AI 公開結果の Markdown レポートを生成するモジュール（v1.18.0）

Single Responsibility:
    AiPublishResult のリストから Markdown レポートを生成する。

禁止事項:
    - ファイル I/O（保存は AiPublishService の責務）
    - WordPress API の呼び出し
"""
from __future__ import annotations

from .ai_publish_result import AiPublishResult


class AiPublishReportBuilder:
    """AiPublishResult のリストから Markdown レポートを生成するクラス。"""

    def build(self, results: list[AiPublishResult]) -> str:
        """
        AiPublishResult のリストから Markdown レポートを生成する。

        Args:
            results: AiPublishResult のリスト（空リストも許容）

        Returns:
            str: Markdown 形式のレポート文字列
        """
        lines: list[str] = []

        lines.append("# AI Publish レポート")
        lines.append("")

        if not results:
            lines.append("対象なし（採用済みリライト: 0 件）")
            lines.append("")
            return "\n".join(lines)

        success_count = sum(1 for r in results if r.success)
        skipped_count = sum(1 for r in results if r.skipped)
        failed_count  = sum(1 for r in results if not r.success and not r.skipped)

        lines.append("## サマリー")
        lines.append("")
        lines.append(f"- **処理件数**: {len(results)} 件")
        lines.append(f"- **投稿成功**: {success_count} 件")
        lines.append(f"- **スキップ**: {skipped_count} 件")
        lines.append(f"- **投稿失敗**: {failed_count} 件")
        lines.append("")

        if success_count > 0:
            lines.append("## 投稿成功")
            lines.append("")
            for r in results:
                if r.success:
                    lines.append(f"### {r.title}")
                    lines.append("")
                    lines.append(f"- **記事ID**: {r.article_id}")
                    lines.append(f"- **元記事URL**: {r.original_permalink or '不明'}")
                    lines.append(f"- **WordPress 投稿ID**: {r.wp_post_id}")
                    lines.append(f"- **下書きスラッグ**: {r.wp_draft_slug}")
                    if r.wp_edit_url:
                        lines.append(f"- **編集URL**: {r.wp_edit_url}")
                    lines.append(f"- **レビュー状態**: {r.source_review_status}")
                    lines.append(f"- **投稿日時**: {r.published_at.strftime('%Y-%m-%d %H:%M:%S')}")
                    lines.append("")

        if skipped_count > 0:
            lines.append("## スキップ")
            lines.append("")
            for r in results:
                if r.skipped:
                    lines.append(f"### {r.title}")
                    lines.append("")
                    lines.append(f"- **記事ID**: {r.article_id}")
                    lines.append(f"- **スキップ理由**: {r.skip_reason or '不明'}")
                    lines.append(f"- **レビュー状態**: {r.source_review_status}")
                    lines.append("")

        if failed_count > 0:
            lines.append("## 投稿失敗")
            lines.append("")
            for r in results:
                if not r.success and not r.skipped:
                    lines.append(f"### {r.title}")
                    lines.append("")
                    lines.append(f"- **記事ID**: {r.article_id}")
                    lines.append(f"- **エラー**: {r.error_message or '不明'}")
                    lines.append(f"- **レビュー状態**: {r.source_review_status}")
                    lines.append("")

        return "\n".join(lines)
