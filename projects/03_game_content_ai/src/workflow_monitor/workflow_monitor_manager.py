"""
Workflow Monitor Manager（v2.9.0）

WorkflowMonitorManager:     Workflow Monitor全体の起動口
NullWorkflowMonitorManager: WORKFLOW_MONITOR_ENABLED=false（無効）の場合のダミー実装

設計方針:
    - ExecutionHistoryConfig / WorkflowMonitorConfig から WorkflowMonitor を構築する。
      ExecutionHistoryConfig.is_ready()（EXECUTION_HISTORY_ENABLED）はチェックしない。
      Execution History自体が無効であっても、過去に記録済みのJSONファイルが
      history_dir に残っていれば読み取れるため（show_execution_history.pyと同じ
      「読み取りと書き込みのゲート分離」の考え方、docs/design/workflow_monitor_foundation.md 6章）。
    - 本Release時点では scripts/show_workflow_status.py は本Managerを経由せず、
      WorkflowMonitorを直接構築して使う（ゲートをバイパスし常に読み取れるようにするため）。
      したがって本Managerは現時点でテスト以外の実呼び出し元を持たない。これは
      v2.0.0（AI Agent Foundation）のAgentManagerがexecutors=[]のまま先行リリースされた
      前例と同型の「Foundation層を先に確立し、消費者は後続Releaseで追加する」パターンである
      （同設計書11章 Architecture Review所見）。
"""
from __future__ import annotations

from execution_history import ExecutionHistoryConfig, JsonExecutionHistoryStore

from .workflow_monitor import WorkflowMonitor
from .workflow_monitor_config import WorkflowMonitorConfig
from .workflow_monitor_record import WorkflowMonitorRecord


class WorkflowMonitorManager:
    """Workflow Monitor全体の起動口。"""

    def __init__(self, monitor: WorkflowMonitor):
        self._monitor = monitor

    @classmethod
    def from_config(
        cls,
        execution_history_config: ExecutionHistoryConfig,
        workflow_monitor_config: WorkflowMonitorConfig,
    ) -> "WorkflowMonitorManager | NullWorkflowMonitorManager":
        """
        ExecutionHistoryConfig と WorkflowMonitorConfig から WorkflowMonitorManager を構築する。

        WORKFLOW_MONITOR_ENABLED が false の場合は NullWorkflowMonitorManager を返す。
        """
        if not workflow_monitor_config.is_ready():
            return NullWorkflowMonitorManager()

        store = JsonExecutionHistoryStore(execution_history_config.history_dir)
        monitor = WorkflowMonitor(store=store, config=workflow_monitor_config)
        return cls(monitor=monitor)

    def get_status(self, run_id: str) -> WorkflowMonitorRecord | None:
        return self._monitor.get_status(run_id)

    def list_status(self, limit: int | None = None) -> list[WorkflowMonitorRecord]:
        return self._monitor.list_status(limit=limit)


class NullWorkflowMonitorManager:
    """WORKFLOW_MONITOR_ENABLED=false のときに使用するダミー実装。すべて no-op。"""

    def get_status(self, run_id: str) -> None:
        return None

    def list_status(self, limit: int | None = None) -> list:
        return []
