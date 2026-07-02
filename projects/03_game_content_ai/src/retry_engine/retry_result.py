"""
Retry Result定義（v3.0.0）

RetryOutcome: 1回の再実行試行の結果種別を表すEnum
RetryResult:  1回の再実行試行の結果を保持するデータクラス

設計方針:
    - workflow_engine_result は outcome == RetryOutcome.RETRIED の場合のみ値を持つ。
      WorkflowEngineManager.run() の戻り値をそのまま透過的に保持することで、呼び出し元は
      再実行の成否をこの1回の同期呼び出しの中だけで把握できる（新しいrun_idそのものは
      WorkflowEngineResultが公開していないため保持しない。
      docs/design/retry_engine_foundation.md 10章 Design Decision #5）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from workflow_engine import WorkflowEngineResult
from workflow_monitor import WorkflowMonitorStatus


class RetryOutcome(Enum):
    RETRIED = "retried"      # WorkflowEngineManager.run()を呼び出し、再実行した
    SKIPPED = "skipped"      # 再実行対象外（状態不一致 or 上限到達）
    NOT_FOUND = "not_found"  # run_idがWorkflow Monitorに存在しない
    DISABLED = "disabled"    # RETRY_ENGINE_ENABLED=false、または下位ゲートが閉じている


@dataclass(frozen=True)
class RetryResult:
    original_run_id: str
    outcome: RetryOutcome
    attempt: int
    monitor_status: WorkflowMonitorStatus | None
    reason: str | None
    workflow_engine_result: WorkflowEngineResult | None
