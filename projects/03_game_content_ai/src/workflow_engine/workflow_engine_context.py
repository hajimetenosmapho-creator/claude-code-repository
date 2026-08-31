"""
Workflow Engine実行コンテキスト（v2.7.0、Release 6.31でRetry Lineage関連フィールドを追加）

WorkflowEngineContext: Workflow Engine実行中の状態を保持するデータクラス

設計方針:
    - AgentContext（v2.0.0）と同様、設定値ではなく実行時状態のみを保持する。
    - event は Scheduler経由・手動経路（--job-id）のいずれの場合も必ず設定される
      （WorkflowEngineEvent.source で区別できるため、None は許容しない。
      docs/design/workflow_engine_foundation.md 6章、修正必須事項#2）。

Release 6.31での変更（docs/design/retry_lineage_eligibility_durable_attempt_state.md
10.1・10.2・10.3・11.4章）:
    - `target_step_filter` / `post_admission_hook` / `correlation_metadata` を
      呼び出しごとの値として追加した。いずれも`WorkflowEngineManager.run()`の
      呼び出し引数（省略時None、対応するworkflow_engine_manager.py参照）から
      素通しされる。`WorkflowEngineExecutor`は単一の共有インスタンスとして
      非retry呼び出し元（target_step_filter/post_admission_hook不要）とRetryExecutor
      経由の呼び出し（claim()結果ごとに異なるhook/filterが必要）の両方から使われる
      ため、これらはExecutor構築時ではなく、Contextのフィールドとして呼び出しごとに
      渡す（workflow_engine_post_admission_hook.py参照）。
    - いずれも省略時（None）は既存の全非retry呼び出し元に対して完全にZero-Diff。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from .workflow_engine_event import WorkflowEngineEvent
from .workflow_engine_result import WorkflowEngineStepResult
from .workflow_engine_step import WorkflowEngineStep

if TYPE_CHECKING:
    from .workflow_engine_post_admission_hook import PostAdmissionHook


@dataclass
class WorkflowEngineContext:
    event: WorkflowEngineEvent
    dry_run: bool
    run_id: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    step_results: list[WorkflowEngineStepResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    target_step_filter: list[WorkflowEngineStep] | None = None
    post_admission_hook: "PostAdmissionHook | None" = None
    correlation_metadata: dict[str, dict[str, str]] | None = None
