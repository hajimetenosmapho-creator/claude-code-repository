"""
Workflow Trigger Agent（v2.3.0）

WorkflowTriggerAgent: WorkflowRunner を「今実行すべきか」判断する BaseAgent 実装

設計方針:
    - WorkflowTriggerAgent の責務は「判断」（decide()）と「実行の委譲」（act()）のみ。
      Workflowの起動方法（WorkflowRunner.run()を直接呼ぶか等）は一切知らず、
      WorkflowPipelineRunner に委譲する。
    - decide() は outputs/workflow_reports/ 配下のレポートファイル（読み取り専用）の
      mtimeを根拠に判断する。ファイル書き込み・削除・外部API呼び出しなどの副作用は
      一切持たない。
    - act() は WorkflowPipelineRunner.run() を呼ぶだけで、WorkflowRunner を
      直接importしない（既存Workflowの起動手段は Pipeline層に閉じ込める）。
    - NewsAgent は importしない。WorkflowTriggerAgent は NewsAgent とは別系統の
      Agent であり、WorkflowRunner（記事改善〜公開の6ステップ）のみを対象とする。
"""
from __future__ import annotations

from datetime import datetime

from .agent_context import AgentContext
from .agent_decision import AgentDecision
from .agent_result import AgentResult
from .base_agent import BaseAgent
from .workflow_trigger_agent_config import WorkflowTriggerAgentConfig

from pipeline.workflow_pipeline_runner import WorkflowPipelineRunner

REPORT_GLOB_PATTERN = "*.md"

REASON_NO_PREVIOUS_REPORT = "No previous workflow report found."
REASON_INTERVAL_EXCEEDED = "Workflow interval exceeded."
REASON_INTERVAL_NOT_EXCEEDED = "Workflow interval not exceeded."

MESSAGE_SUCCESS = "Workflow pipeline completed successfully."
MESSAGE_FAILURE_FALLBACK = "Workflow pipeline failed."


class WorkflowTriggerAgent(BaseAgent):
    """WorkflowRunnerの実行要否を判断し、必要な場合のみ WorkflowPipelineRunner に委譲する。"""

    def __init__(self, config: WorkflowTriggerAgentConfig, runner: WorkflowPipelineRunner):
        self._config = config
        self._runner = runner

    def name(self) -> str:
        return "workflow_trigger_agent"

    def decide(self, context: AgentContext) -> AgentDecision:
        """
        outputs/workflow_reports/ 配下の *.md の最新mtimeを求め、
        min_interval_minutes と比較して実行要否を判断する（副作用なし）。
        """
        latest_mtime = self._find_latest_report_mtime(context)

        if latest_mtime is None:
            return AgentDecision(
                should_act=True,
                reason=REASON_NO_PREVIOUS_REPORT,
            )

        min_interval = self._config.min_interval_minutes
        now = datetime.now()
        elapsed_minutes = (now - latest_mtime).total_seconds() / 60

        if elapsed_minutes >= min_interval:
            return AgentDecision(
                should_act=True,
                reason=REASON_INTERVAL_EXCEEDED,
            )

        return AgentDecision(
            should_act=False,
            reason=REASON_INTERVAL_NOT_EXCEEDED,
        )

    def act(self, decision: AgentDecision, context: AgentContext) -> AgentResult:
        """WorkflowPipelineRunner.run() のみを呼び出し、PipelineResult を AgentResult へ変換する。"""
        assert not context.dry_run

        result = self._runner.run(params=context.task.params)

        warnings = list(context.warnings)
        if result.success:
            warnings.append(MESSAGE_SUCCESS)
            error_message = None
        else:
            error_message = result.error_message or MESSAGE_FAILURE_FALLBACK

        return AgentResult(
            run_id=context.run_id,
            agent_name=context.agent_name,
            task=context.task,
            decision=decision,
            action_taken=True,
            success=result.success,
            workflow_result=None,
            error_message=error_message,
            started_at=context.started_at,
            finished_at=context.finished_at,
            warnings=warnings,
        )

    def _find_latest_report_mtime(self, context: AgentContext) -> datetime | None:
        """
        outputs/workflow_reports/ 配下の *.md を走査し、最新のmtime（datetime）を返す。

        レポートディレクトリが存在しない、ファイルが1件もない、
        またはすべてのファイルでmtime取得に失敗した場合は None を返す
        （decide() 側で「過去実行なし」＝実行可能と判断される）。
        """
        reports_dir = self._config.reports_dir
        if not reports_dir.exists():
            return None

        try:
            paths = list(reports_dir.glob(REPORT_GLOB_PATTERN))
        except OSError as e:
            context.warnings.append(f"レポートディレクトリの走査に失敗しました: {e}")
            return None

        latest: datetime | None = None
        for path in paths:
            try:
                mtime = datetime.fromtimestamp(path.stat().st_mtime)
            except OSError as e:
                context.warnings.append(
                    f"レポートファイルの取得に失敗しました（{path.name}）: {e}"
                )
                continue

            if latest is None or mtime > latest:
                latest = mtime

        return latest
