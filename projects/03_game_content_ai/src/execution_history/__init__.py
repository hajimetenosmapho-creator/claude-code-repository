"""
Execution History パッケージ（v2.8.0）

Workflow Engine（v2.7.0）が実行した各Workflowについて、実行の開始・終了・各Stepの結果を
観測して記録するだけの最小基盤。実行判断・分岐・再試行判断には一切関与しない
（docs/design/execution_history_foundation.md 2章）。

処理フロー（v6.30時点、run_idベースAPI）:
    WorkflowEngineExecutor.run()
        → ExecutionHistoryManager.start_run() → StartRunWriteResult(run_id, acknowledged)
          （内部でWorkflowExecutionRecord(RUNNING)をManager-owned snapshotとして保持）
        → 各Stepごとに run_id（+ step_name）で start_step() / finish_step()
        → ExecutionHistoryManager.finish_run() → bool（ack）
        → JsonExecutionHistoryStore が logs/execution_history/{run_id}.json へ保存

設計方針:
    - src/workflow_engine/ からのみimportされる一方向依存。本パッケージは
      workflow_engine / ai / pipeline / scheduler のいずれもimportしない。
    - EXECUTION_HISTORY_ENABLED=false（記録無効）の場合はNullExecutionHistoryManagerが
      すべて no-op で動作する。ただしv6.30のCanonical Admission実装により、canonical
      non-dry-run経路でNullExecutionHistoryManagerが渡った場合は、呼び出し元
      （WorkflowEngineExecutor）が`CanonicalAdmissionFailure(EXECUTION_HISTORY_DISABLED)`
      へ変換しfail-closedで拒否する（docs/design/
      production_canonical_run_outcome_contract_foundation.md 9・11・19章）。
"""
from .execution_history_config import ExecutionHistoryConfig
from .execution_history_event import (
    EVENT_STEP_FINISHED,
    EVENT_STEP_STARTED,
    EVENT_WORKFLOW_FINISHED,
    EVENT_WORKFLOW_STARTED,
    ExecutionHistoryEvent,
)
from .step_execution_record import StepExecutionRecord, StepExecutionStatus
from .workflow_execution_record import WorkflowExecutionRecord, WorkflowExecutionStatus
from .execution_history_store import ExecutionHistoryStore
from .json_execution_history_store import JsonExecutionHistoryStore
from .start_run_write_result import StartRunWriteResult
from .execution_history_manager import ExecutionHistoryManager, NullExecutionHistoryManager

__all__ = [
    "ExecutionHistoryConfig",
    "ExecutionHistoryEvent",
    "EVENT_WORKFLOW_STARTED",
    "EVENT_WORKFLOW_FINISHED",
    "EVENT_STEP_STARTED",
    "EVENT_STEP_FINISHED",
    "StepExecutionRecord",
    "StepExecutionStatus",
    "WorkflowExecutionRecord",
    "WorkflowExecutionStatus",
    "ExecutionHistoryStore",
    "JsonExecutionHistoryStore",
    "StartRunWriteResult",
    "ExecutionHistoryManager",
    "NullExecutionHistoryManager",
]
