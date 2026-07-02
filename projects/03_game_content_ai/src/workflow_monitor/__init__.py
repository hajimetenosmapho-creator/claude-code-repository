"""
Workflow Monitor パッケージ（v2.9.0）

Execution History（v2.8.0）が記録したWorkflow実行履歴を読み取り、Workflowの実行状態を
判定するだけの最小基盤。Workflow Engine・Execution Historyいずれの実行・記録処理にも
関与しない（docs/design/workflow_monitor_foundation.md 1章）。

処理フロー（v2.9.0）:
    ExecutionHistoryStore.get(run_id) / list_all()
        → WorkflowMonitor が WorkflowExecutionRecord を読み取り WorkflowMonitorStatus を判定
        → WorkflowMonitorRecord として返す
        → scripts/show_workflow_status.py が表示する

設計方針:
    - src/execution_history/ のみを読み取り専用でimportする一方向依存。本パッケージは
      workflow_engine / ai / pipeline / scheduler のいずれもimportしない。
    - Execution Historyへの書き込みは一切行わない（読み取り専用）。
    - WORKFLOW_MONITOR_ENABLED=false の場合はNullWorkflowMonitorManagerがすべてno-opで
      動作する。
"""
from .workflow_monitor_status import WorkflowMonitorStatus
from .workflow_monitor_config import WorkflowMonitorConfig
from .workflow_monitor_record import WorkflowMonitorRecord
from .workflow_monitor import WorkflowMonitor
from .workflow_monitor_manager import WorkflowMonitorManager, NullWorkflowMonitorManager

__all__ = [
    "WorkflowMonitorStatus",
    "WorkflowMonitorConfig",
    "WorkflowMonitorRecord",
    "WorkflowMonitor",
    "WorkflowMonitorManager",
    "NullWorkflowMonitorManager",
]
