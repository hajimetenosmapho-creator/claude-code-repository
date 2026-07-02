"""
Execution History Store（v2.8.0）

ExecutionHistoryStore: WorkflowExecutionRecordの永続化方式を抽象化するインターフェース

設計方針:
    - src/scheduler/scheduler_repository.py（v2.6.0）の SchedulerRepository と同型のABC設計。
      将来的なDB化を見据え、保存方式を差し替え可能にする
      （docs/design/execution_history_foundation.md 5章）。
    - SchedulerRepository と異なり update() を独立させず save() に統合する。
      Execution Historyは「同一run_idへの複数回の上書き保存」が正常系であるため
      （start_run/start_step/finish_step/finish_run のたびに再保存する）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .workflow_execution_record import WorkflowExecutionRecord


class ExecutionHistoryStore(ABC):
    """WorkflowExecutionRecordの永続化方式を抽象化するインターフェース。"""

    @abstractmethod
    def save(self, record: WorkflowExecutionRecord) -> None:
        """recordをrun_idで保存する（新規・上書き両対応）。"""
        ...

    @abstractmethod
    def get(self, run_id: str) -> WorkflowExecutionRecord | None:
        """run_idに対応するrecordを返す。存在しない場合はNoneを返す。"""
        ...

    @abstractmethod
    def list_all(self) -> list[WorkflowExecutionRecord]:
        """保存されているすべてのrecordを、started_atの新しい順で返す。"""
        ...
