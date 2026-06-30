"""
ワークフローステップエグゼキュータ（v1.20.0）

WorkflowStepExecutor:           各ステップの実行を担う抽象基底クラス（ABC）
ImprovementStepExecutor:        v1.14 AI 改善提案ステップ
ImprovementReviewStepExecutor:  v1.15 改善提案レビューステップ
RewriteStepExecutor:            v1.16 AI リライトステップ
RewriteReviewStepExecutor:      v1.17 リライトレビューステップ
PublishStepExecutor:            v1.18 AI 公開ステップ
PublishReviewStepExecutor:      v1.19 公開レビューステップ

設計方針:
    - WorkflowRunner は executor.execute(context) のみを呼び出す
    - 各 Executor が対応するサービスへの依存を保持する（WorkflowRunner は知らない）
    - Dependency Injection: サービスはコンストラクタで注入する
    - dry_run=True の場合は実処理をせず processed_count=0 の結果を返す
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date, datetime
from pathlib import Path

from .workflow_context import WorkflowContext
from .workflow_step import WorkflowStep, WorkflowStepResult


class WorkflowStepExecutor(ABC):
    """ワークフローの各ステップを実行する抽象基底クラス。"""

    @abstractmethod
    def step(self) -> WorkflowStep:
        """このエグゼキュータが担当するステップを返す。"""
        ...

    @abstractmethod
    def execute(self, context: WorkflowContext) -> WorkflowStepResult:
        """ステップを実行し、結果を返す。"""
        ...


def _dry_run_result(step: WorkflowStep, started_at: datetime) -> WorkflowStepResult:
    """dry_run=True 時の no-op 結果を生成するヘルパー。"""
    return WorkflowStepResult(
        step=step,
        success=True,
        processed_count=0,
        report_path=None,
        error_message=None,
        started_at=started_at,
        finished_at=datetime.now(),
    )


class ImprovementStepExecutor(WorkflowStepExecutor):
    """
    AI 改善提案ステップ（v1.14）のエグゼキュータ。

    AnalyticsManager から AiInputRecord を読み込み、
    AiImprovementService で改善提案を生成する。
    """

    def __init__(self, service, analytics_manager, log_dir: Path):
        self._service           = service
        self._analytics_manager = analytics_manager
        self._log_dir           = log_dir

    def step(self) -> WorkflowStep:
        return WorkflowStep.IMPROVEMENT

    def execute(self, context: WorkflowContext) -> WorkflowStepResult:
        started_at = datetime.now()

        if context.dry_run:
            return _dry_run_result(self.step(), started_at)

        try:
            date_str     = date.today().strftime("%Y%m%d")
            articles     = list(self._analytics_manager.load_article_logs(
                log_dir=self._log_dir, date_str=date_str
            ))
            analytics_map = self._analytics_manager.load_analytics_logs(date_str=date_str)

            ai_inputs = []
            for article in articles:
                post_id         = article.get("post_id", 0)
                analytics_entry = analytics_map.get(post_id)
                analysis_record = self._analytics_manager.build_analysis_record(
                    article, analytics_entry
                )
                if analysis_record is None:
                    continue
                ai_input = self._analytics_manager.build_ai_input(analysis_record)
                if ai_input is None:
                    continue
                if context.article_id and ai_input.slug != context.article_id:
                    continue
                ai_inputs.append(ai_input)

            suggestions = self._service.improve_batch(
                ai_inputs=ai_inputs,
                performance_only=True,
            )
            return WorkflowStepResult(
                step=self.step(),
                success=True,
                processed_count=len(suggestions),
                report_path=None,
                error_message=None,
                started_at=started_at,
                finished_at=datetime.now(),
            )
        except Exception as e:
            return WorkflowStepResult(
                step=self.step(),
                success=False,
                processed_count=0,
                report_path=None,
                error_message=str(e),
                started_at=started_at,
                finished_at=datetime.now(),
            )


class ImprovementReviewStepExecutor(WorkflowStepExecutor):
    """改善提案レビューステップ（v1.15）のエグゼキュータ。"""

    def __init__(self, service):
        self._service = service

    def step(self) -> WorkflowStep:
        return WorkflowStep.IMPROVEMENT_REVIEW

    def execute(self, context: WorkflowContext) -> WorkflowStepResult:
        started_at = datetime.now()

        if context.dry_run:
            return _dry_run_result(self.step(), started_at)

        try:
            report_path = self._service.run(article_id=context.article_id)
            suggestions = self._service.get_suggestions(article_id=context.article_id)
            return WorkflowStepResult(
                step=self.step(),
                success=True,
                processed_count=len(suggestions),
                report_path=report_path,
                error_message=None,
                started_at=started_at,
                finished_at=datetime.now(),
            )
        except Exception as e:
            return WorkflowStepResult(
                step=self.step(),
                success=False,
                processed_count=0,
                report_path=None,
                error_message=str(e),
                started_at=started_at,
                finished_at=datetime.now(),
            )


class RewriteStepExecutor(WorkflowStepExecutor):
    """
    AI リライトステップ（v1.16）のエグゼキュータ。

    ImprovementRepository から改善提案を読み込み、
    RewriteService でリライトを実行する。
    """

    def __init__(self, service, improvement_dir: Path):
        self._service         = service
        self._improvement_dir = improvement_dir

    def step(self) -> WorkflowStep:
        return WorkflowStep.REWRITE

    def execute(self, context: WorkflowContext) -> WorkflowStepResult:
        started_at = datetime.now()

        if context.dry_run:
            return _dry_run_result(self.step(), started_at)

        try:
            from .improvement_repository import ImprovementRepository
            repository  = ImprovementRepository(self._improvement_dir)
            suggestions = repository.load_all()

            if context.article_id:
                suggestions = [s for s in suggestions if s.article_id == context.article_id]

            results       = self._service.rewrite_batch(suggestions=suggestions)
            success_count = sum(1 for r in results if r.success)
            return WorkflowStepResult(
                step=self.step(),
                success=True,
                processed_count=success_count,
                report_path=None,
                error_message=None,
                started_at=started_at,
                finished_at=datetime.now(),
            )
        except Exception as e:
            return WorkflowStepResult(
                step=self.step(),
                success=False,
                processed_count=0,
                report_path=None,
                error_message=str(e),
                started_at=started_at,
                finished_at=datetime.now(),
            )


class RewriteReviewStepExecutor(WorkflowStepExecutor):
    """リライトレビューステップ（v1.17）のエグゼキュータ。"""

    def __init__(self, service):
        self._service = service

    def step(self) -> WorkflowStep:
        return WorkflowStep.REWRITE_REVIEW

    def execute(self, context: WorkflowContext) -> WorkflowStepResult:
        started_at = datetime.now()

        if context.dry_run:
            return _dry_run_result(self.step(), started_at)

        try:
            report_path = self._service.run(article_id=context.article_id)
            reviews     = self._service.get_reviews(article_id=context.article_id)
            return WorkflowStepResult(
                step=self.step(),
                success=True,
                processed_count=len(reviews),
                report_path=report_path,
                error_message=None,
                started_at=started_at,
                finished_at=datetime.now(),
            )
        except Exception as e:
            return WorkflowStepResult(
                step=self.step(),
                success=False,
                processed_count=0,
                report_path=None,
                error_message=str(e),
                started_at=started_at,
                finished_at=datetime.now(),
            )


class PublishStepExecutor(WorkflowStepExecutor):
    """AI 公開ステップ（v1.18）のエグゼキュータ。"""

    def __init__(self, service):
        self._service = service

    def step(self) -> WorkflowStep:
        return WorkflowStep.PUBLISH

    def execute(self, context: WorkflowContext) -> WorkflowStepResult:
        started_at = datetime.now()

        if context.dry_run:
            return _dry_run_result(self.step(), started_at)

        try:
            report_path   = self._service.run(article_id=context.article_id)
            results       = self._service.get_results(article_id=context.article_id)
            success_count = sum(1 for r in results if r.success)
            return WorkflowStepResult(
                step=self.step(),
                success=True,
                processed_count=success_count,
                report_path=report_path,
                error_message=None,
                started_at=started_at,
                finished_at=datetime.now(),
            )
        except Exception as e:
            return WorkflowStepResult(
                step=self.step(),
                success=False,
                processed_count=0,
                report_path=None,
                error_message=str(e),
                started_at=started_at,
                finished_at=datetime.now(),
            )


class PublishReviewStepExecutor(WorkflowStepExecutor):
    """公開レビューステップ（v1.19）のエグゼキュータ。"""

    def __init__(self, service):
        self._service = service

    def step(self) -> WorkflowStep:
        return WorkflowStep.PUBLISH_REVIEW

    def execute(self, context: WorkflowContext) -> WorkflowStepResult:
        started_at = datetime.now()

        if context.dry_run:
            return _dry_run_result(self.step(), started_at)

        try:
            report_path = self._service.run(article_id=context.article_id)
            reviews     = self._service.get_reviews(article_id=context.article_id)
            return WorkflowStepResult(
                step=self.step(),
                success=True,
                processed_count=len(reviews),
                report_path=report_path,
                error_message=None,
                started_at=started_at,
                finished_at=datetime.now(),
            )
        except Exception as e:
            return WorkflowStepResult(
                step=self.step(),
                success=False,
                processed_count=0,
                report_path=None,
                error_message=str(e),
                started_at=started_at,
                finished_at=datetime.now(),
            )
