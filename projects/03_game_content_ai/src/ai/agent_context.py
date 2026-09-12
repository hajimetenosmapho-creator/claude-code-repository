"""
Agent実行コンテキスト（v2.0.0）

AgentContext: エージェント実行中の状態と Execution Metadata を保持するデータクラス

設計方針:
    - AgentConfig（設定値）とは分離し、実行時状態のみを保持する
    - AgentExecutor が run_id / agent_name / started_at / finished_at / decisions を更新する
    - elapsed_time は保存せず計算プロパティとする
      （started_at / finished_at との不整合を構造的に防ぐため）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from .agent_decision import AgentDecision
from .agent_task import AgentTask

if TYPE_CHECKING:
    from side_effect_safety import LegacyDirectExecutionContext, RetryLineageProtectedExecutionContext


@dataclass
class AgentContext:
    # 実行パラメータ（呼び出し元から渡される）
    task: AgentTask
    dry_run: bool

    # Execution Metadata（AgentExecutor が設定する）
    run_id: str
    agent_name: str
    started_at: datetime | None = None
    finished_at: datetime | None = None

    # Release 6.32、2.6節Propagation Contract：Explicit Side-Effect Execution Mode
    # 専用channel。task.params/event.metadataとは独立に、side-effect safety
    # identityのみを運ぶ。RetryLineageProtectedExecutionContext（protected）または
    # LegacyDirectExecutionContext（legacy）のいずれか。未設定（None）は
    # missing contextとしてfail-closedされる（呼び出し箇所A/B/C側の責務）。
    side_effect_execution_context: "RetryLineageProtectedExecutionContext | LegacyDirectExecutionContext | None" = None

    # ランタイム状態（AgentExecutor / BaseAgent が更新する）
    decisions: list[AgentDecision] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    logs: list[str] = field(default_factory=list)

    @property
    def elapsed_time(self) -> float | None:
        """開始から終了までの経過秒数（未確定の場合は None）。"""
        if self.started_at is None or self.finished_at is None:
            return None
        return (self.finished_at - self.started_at).total_seconds()
