"""
News Agent（v2.2.0）

NewsAgent: ゲームニュース収集を「今実行すべきか」判断する BaseAgent 実装

設計方針:
    - NewsAgent の責務は「判断」（decide()）と「実行の委譲」（act()）のみ。
      ニュース収集の実行方法（subprocess等）は一切知らず、NewsPipelineRunner に委譲する。
    - decide() は logs/execution/ 配下の実行ログ（読み取り専用）を根拠に判断する。
      ファイル書き込み・削除・外部API呼び出しなどの副作用は一切持たない。
    - act() は NewsPipelineRunner.run() を呼ぶだけで、subprocess や main.py を
      直接importしない（既存パイプラインの起動手段は Pipeline層に閉じ込める）。
    - WorkflowRunner は importしない。NewsAgent は WorkflowRunner とは別系統の
      Agent であり、既存ニュース収集パイプライン（main.py）のみを対象とする。
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta

from .agent_context import AgentContext
from .agent_decision import AgentDecision
from .agent_result import AgentResult
from .base_agent import BaseAgent
from .news_agent_config import NewsAgentConfig

from pipeline import NewsPipelineRunner

EXECUTION_LOG_SUBDIR = "logs/execution"


class NewsAgent(BaseAgent):
    """ゲームニュース収集の実行要否を判断し、必要な場合のみ NewsPipelineRunner に委譲する。"""

    def __init__(self, config: NewsAgentConfig, runner: NewsPipelineRunner):
        self._config = config
        self._runner = runner

    def name(self) -> str:
        return "news_agent"

    def decide(self, context: AgentContext) -> AgentDecision:
        """
        logs/execution/ 配下の実行ログ（読み取り専用）から直近の finished_at を求め、
        min_interval_minutes と比較して収集要否を判断する（副作用なし）。
        """
        latest_finished_at, had_read_error = self._find_latest_execution(context)

        if latest_finished_at is None:
            if had_read_error:
                return AgentDecision(
                    should_act=True,
                    reason="実行ログの読み取りに失敗し判断不能のため、実行可能と判断",
                )
            return AgentDecision(
                should_act=True,
                reason="実行履歴が見つからないため初回実行と判断",
            )

        min_interval = self._config.min_interval_minutes
        now = datetime.now().astimezone()
        elapsed_minutes = (now - latest_finished_at).total_seconds() / 60

        if elapsed_minutes >= min_interval:
            return AgentDecision(
                should_act=True,
                reason=f"前回実行から{elapsed_minutes:.1f}分経過（基準: {min_interval}分）",
            )

        remaining_minutes = min_interval - elapsed_minutes
        return AgentDecision(
            should_act=False,
            reason=(
                f"前回実行から{elapsed_minutes:.1f}分のみ経過"
                f"（基準: {min_interval}分、あと{remaining_minutes:.1f}分で実行可能）"
            ),
        )

    def act(self, decision: AgentDecision, context: AgentContext) -> AgentResult:
        """NewsPipelineRunner.run() のみを呼び出し、PipelineResult を AgentResult へ変換する。"""
        assert not context.dry_run

        result = self._runner.run(params=context.task.params)

        warnings = list(context.warnings)
        if result.stdout_log_path:
            warnings.append(f"stdoutログ: {result.stdout_log_path}")
        if result.stderr_log_path:
            warnings.append(f"stderrログ: {result.stderr_log_path}")

        return AgentResult(
            run_id=context.run_id,
            agent_name=context.agent_name,
            task=context.task,
            decision=decision,
            action_taken=True,
            success=result.success,
            workflow_result=None,
            error_message=result.error_message,
            started_at=context.started_at,
            finished_at=context.finished_at,
            warnings=warnings,
        )

    def _find_latest_execution(
        self, context: AgentContext
    ) -> tuple[datetime | None, bool]:
        """
        logs/execution/ 配下を log_lookback_days 分だけ遡って走査し、
        最新の finished_at（datetime）を返す。

        Returns:
            (最新の finished_at または None, 読み取り不能な行・ファイルがあったか)
        """
        log_dir = self._config.working_directory / EXECUTION_LOG_SUBDIR
        latest: datetime | None = None
        had_error = False
        today = datetime.now().date()

        for offset in range(self._config.log_lookback_days):
            date_str = (today - timedelta(days=offset)).strftime("%Y%m%d")
            path = log_dir / f"{date_str}_execution.jsonl"
            if not path.exists():
                continue

            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError) as e:
                had_error = True
                context.warnings.append(
                    f"実行ログの読み取りに失敗しました（{path.name}）: {e}"
                )
                continue

            for line in lines:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                    finished_at = datetime.fromisoformat(entry["finished_at"])
                except (json.JSONDecodeError, KeyError, ValueError) as e:
                    had_error = True
                    context.warnings.append(
                        f"実行ログの1行を解析できませんでした（{path.name}）: {e}"
                    )
                    continue

                if latest is None or finished_at > latest:
                    latest = finished_at

        return latest, had_error
