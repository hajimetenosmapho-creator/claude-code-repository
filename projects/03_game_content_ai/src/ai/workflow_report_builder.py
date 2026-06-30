"""
ワークフローレポートビルダー（v1.20.0）

WorkflowReportBuilder: WorkflowResult を唯一の入力として Markdown レポートを生成する

設計方針（Single Source of Truth）:
    WorkflowResult を唯一の情報源とし、
    list[WorkflowStepResult] を直接受け取らない設計にすることで
    レポートに必要な全情報（ステップ結果・warnings・skipped_steps・全体サマリー）を
    一元管理する。
"""
from __future__ import annotations

from datetime import datetime

from .workflow_result import WorkflowResult
from .workflow_step import WorkflowStep

_STEP_LABELS: dict[WorkflowStep, str] = {
    WorkflowStep.IMPROVEMENT:        "AI 改善提案（v1.14）",
    WorkflowStep.IMPROVEMENT_REVIEW: "改善提案レビュー（v1.15）",
    WorkflowStep.REWRITE:            "AI リライト（v1.16）",
    WorkflowStep.REWRITE_REVIEW:     "リライトレビュー（v1.17）",
    WorkflowStep.PUBLISH:            "AI 公開（v1.18）",
    WorkflowStep.PUBLISH_REVIEW:     "公開レビュー（v1.19）",
}


class WorkflowReportBuilder:
    """
    WorkflowResult から Markdown レポートを生成するビルダー。

    Single Source of Truth:
        WorkflowResult のみを入力とする。
        list[WorkflowStepResult] を直接受け取らない。
    """

    def build(self, result: WorkflowResult) -> str:
        lines: list[str] = []
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        lines.append("# AI Workflow 実行レポート")
        lines.append("")
        lines.append(f"生成日時: {now_str}")
        lines.append("")

        # サマリー
        status = "SUCCESS" if result.overall_success else "FAILURE"
        lines.append("## サマリー")
        lines.append("")
        lines.append(f"- ステータス: **{status}**")
        lines.append(f"- 合計処理件数: {result.total_processed} 件")
        lines.append(f"- 開始: {result.started_at.strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(f"- 終了: {result.finished_at.strftime('%Y-%m-%d %H:%M:%S')}")

        elapsed = result.finished_at - result.started_at
        lines.append(f"- 経過時間: {int(elapsed.total_seconds())} 秒")

        if result.skipped_steps:
            labels = [_STEP_LABELS.get(s, s.value) for s in result.skipped_steps]
            lines.append(f"- スキップ: {', '.join(labels)}")

        lines.append("")

        # 警告
        if result.warnings:
            lines.append("## 警告")
            lines.append("")
            for w in result.warnings:
                lines.append(f"- {w}")
            lines.append("")

        # ステップ別結果
        lines.append("## ステップ別結果")
        lines.append("")

        if not result.steps:
            lines.append("実行されたステップはありません。")
            lines.append("")
        else:
            for step_result in result.steps:
                label = _STEP_LABELS.get(step_result.step, step_result.step.value)
                mark  = "OK" if step_result.success else "NG"
                lines.append(f"### [{mark}] {label}")
                lines.append("")
                lines.append(f"- 処理件数: {step_result.processed_count} 件")
                elapsed_step = step_result.finished_at - step_result.started_at
                lines.append(f"- 経過時間: {int(elapsed_step.total_seconds())} 秒")
                if step_result.report_path:
                    lines.append(f"- レポート: `{step_result.report_path}`")
                if step_result.error_message:
                    lines.append(f"- エラー: {step_result.error_message}")
                lines.append("")

        # スキップされたステップ
        if result.skipped_steps:
            lines.append("## スキップされたステップ")
            lines.append("")
            for skipped in result.skipped_steps:
                label = _STEP_LABELS.get(skipped, skipped.value)
                lines.append(f"- {label}")
            lines.append("")

        return "\n".join(lines)
