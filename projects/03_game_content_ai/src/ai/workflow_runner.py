"""
ワークフロー実行エンジン（v1.20.0）

WorkflowRunner:     WorkflowStepExecutor を介してパイプラインを実行するオーケストレーター
NullWorkflowRunner: AI_WORKFLOW_ENABLED=false 時のダミー実装

設計方針:
    - WorkflowRunner は executor.execute(context) のみを呼び出す
    - 各サービスを直接知らない（WorkflowStepExecutor が担う）
    - Dependency Injection: executors はコンストラクタで注入する
    - WorkflowReportBuilder は WorkflowResult を唯一の入力とする

Configuration First:
    WorkflowConfig.is_ready() が False → from_config() が NullWorkflowRunner を返す
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

from .workflow_config import WorkflowConfig
from .workflow_context import WorkflowContext
from .workflow_report_builder import WorkflowReportBuilder
from .workflow_result import WorkflowResult
from .workflow_step import WorkflowStep, WorkflowStepResult
from .workflow_step_executor import (
    ImprovementReviewStepExecutor,
    ImprovementStepExecutor,
    PublishReviewStepExecutor,
    PublishStepExecutor,
    RewriteReviewStepExecutor,
    RewriteStepExecutor,
    WorkflowStepExecutor,
)


class WorkflowRunner:
    """
    AI パイプライン全体をオーケストレーションするランナー。

    処理フロー:
        WorkflowContext を生成
            → config.steps に含まれる各 executor.execute(context) を順番に呼び出す
            → WorkflowResult を生成
            → WorkflowReportBuilder.build(result) でレポートを生成・保存
    """

    def __init__(
        self,
        config: WorkflowConfig,
        executors: list[WorkflowStepExecutor],
    ):
        self._config    = config
        self._executors = executors
        self._builder   = WorkflowReportBuilder()

    @classmethod
    def from_config(
        cls, config: WorkflowConfig
    ) -> "WorkflowRunner | NullWorkflowRunner":
        """
        WorkflowConfig から WorkflowRunner を構築する。

        is_ready() が False の場合は NullWorkflowRunner を返す。
        各 Executor と依存サービスを構築して DI する唯一の場所。
        """
        if not config.is_ready():
            return NullWorkflowRunner()

        base_dir = config.base_dir
        log_dir  = base_dir / "logs"

        from analytics import AnalyticsManager  # type: ignore[import]
        from .ai_improvement_service import AiImprovementService
        from .improvement_review_service import ImprovementReviewService
        from .rewrite_service import RewriteService
        from .rewrite_review_service import RewriteReviewService
        from .ai_publish_service import AiPublishService
        from .ai_publish_review_service import AiPublishReviewService

        executors: list[WorkflowStepExecutor] = [
            ImprovementStepExecutor(
                service=AiImprovementService.from_env(base_dir=base_dir),
                analytics_manager=AnalyticsManager.from_env(base_dir=base_dir),
                log_dir=log_dir,
            ),
            ImprovementReviewStepExecutor(
                service=ImprovementReviewService.from_paths(base_dir=base_dir),
            ),
            RewriteStepExecutor(
                service=RewriteService.from_env(base_dir=base_dir),
                improvement_dir=base_dir / "outputs" / "ai_improvements",
            ),
            RewriteReviewStepExecutor(
                service=RewriteReviewService.from_paths(base_dir=base_dir),
            ),
            PublishStepExecutor(
                service=AiPublishService.from_env(base_dir=base_dir),
            ),
            PublishReviewStepExecutor(
                service=AiPublishReviewService.from_paths(base_dir=base_dir),
            ),
        ]
        return cls(config=config, executors=executors)

    def run(
        self,
        article_id: str | None = None,
        dry_run: bool = False,
    ) -> WorkflowResult:
        """
        ワークフローを実行し、WorkflowResult を返す。

        Args:
            article_id: 絞り込む記事ID（None = 全件）
            dry_run:    True = 実際の処理をせず対象確認のみ

        Returns:
            WorkflowResult: ワークフロー全体の実行結果
        """
        context    = WorkflowContext(article_id=article_id, dry_run=dry_run)
        skipped:   list[WorkflowStep] = []
        started_at = datetime.now()

        for executor in self._executors:
            if executor.step() not in self._config.steps:
                skipped.append(executor.step())
                continue

            context.current_step = executor.step()
            step_result = executor.execute(context)
            context.step_results.append(step_result)

            if step_result.report_path:
                context.report_paths.append(step_result.report_path)

            if not step_result.success:
                msg = (
                    f"{executor.step().value} 失敗"
                    + (f": {step_result.error_message}" if step_result.error_message else "")
                )
                context.errors.append(msg)
                if not self._config.continue_on_error:
                    break

        workflow_result = WorkflowResult(
            steps=list(context.step_results),
            overall_success=all(r.success for r in context.step_results),
            total_processed=sum(r.processed_count for r in context.step_results),
            report_path=None,
            started_at=started_at,
            finished_at=datetime.now(),
            warnings=list(context.warnings),
            skipped_steps=skipped,
        )

        report_path = self._save_report(workflow_result)
        workflow_result.report_path = report_path

        return workflow_result

    def _save_report(self, result: WorkflowResult) -> Path | None:
        """WorkflowReportBuilder でレポートを生成し、outputs/workflow_reports/ に保存する。"""
        try:
            report_dir = self._config.base_dir / "outputs" / "workflow_reports"
            report_dir.mkdir(parents=True, exist_ok=True)
            date_str = date.today().strftime("%Y%m%d")
            filename = f"{date_str}_workflow_report.md"
            path     = report_dir / filename
            content  = self._builder.build(result)
            with path.open("w", encoding="utf-8") as f:
                f.write(content)
            print(f"  [WORKFLOW] レポート保存: {path}")
            return path
        except OSError as e:
            print(f"  [WORKFLOW WARNING] レポート保存失敗: {e}")
            return None


class NullWorkflowRunner:
    """
    AI_WORKFLOW_ENABLED=false 時のダミー実装。
    すべてのメソッドが no-op で動作する。
    """

    def is_available(self) -> bool:
        return False

    def run(
        self,
        article_id: str | None = None,
        dry_run: bool = False,
    ) -> WorkflowResult:
        print("  [WORKFLOW] AI ワークフローが無効です（AI_WORKFLOW_ENABLED=false）。")
        now = datetime.now()
        return WorkflowResult(
            steps=[],
            overall_success=False,
            total_processed=0,
            report_path=None,
            started_at=now,
            finished_at=now,
            warnings=[],
            skipped_steps=[],
        )
