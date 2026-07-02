"""
Retry Executor（v3.0.0）

RetryExecutor: WorkflowEngineManagerの公開APIを呼び出すだけの薄いコンポーネント

設計方針:
    - 再実行の可否判定（RetryPolicyの適用）・RetryRequestの生成は RetryManager の責務であり、
      RetryExecutorはRetryManagerによってすでに「再実行する」と判定された RetryRequest の
      みを受け取る。ここでの唯一の仕事は、RetryRequest / WorkflowMonitorRecord を
      WorkflowEngineEvent へ変換して WorkflowEngineManager.run() を呼び出し、戻り値を
      RetryResult へ詰め替えて返すことだけである
      （docs/design/retry_engine_foundation.md 10章 Design Decision #10、Architecture Review反映）。
    - RetryPolicy を一切参照・保持しない（コンストラクタに policy 引数を持たない）。
    - source は新規定数を追加せず、既存の SOURCE_MANUAL を再利用する。再実行由来である
      ことは WorkflowEngineEvent.metadata に積む（同設計書10章 Design Decision #4）。
    - WorkflowEngineExecutor 等の内部実装には一切触れない。WorkflowEngineManager.run()の
      みを公開APIとして呼び出す。
"""
from __future__ import annotations

from workflow_engine import SOURCE_MANUAL, WorkflowEngineEvent, WorkflowEngineManager
from workflow_monitor import WorkflowMonitorRecord

from .retry_request import RetryRequest
from .retry_result import RetryOutcome, RetryResult


class RetryExecutor:
    """WorkflowEngineManagerの公開APIを呼び出すだけの薄いコンポーネント。"""

    def __init__(self, workflow_engine_manager: WorkflowEngineManager):
        self._engine = workflow_engine_manager

    def execute(self, request: RetryRequest, record: WorkflowMonitorRecord) -> RetryResult:
        """RetryRequestをWorkflowEngineEventへ変換し、再実行を依頼する。"""
        event = WorkflowEngineEvent(
            job_id=record.job_id,
            source=SOURCE_MANUAL,
            triggered_at=request.requested_at,
            trigger_reason=(
                f"Retry of run_id={request.run_id} "
                f"(monitor_status={record.monitor_status.value}, attempt={request.attempt})."
            ),
            metadata={"retried_from": request.run_id, "attempt": request.attempt},
        )
        engine_result = self._engine.run(event, dry_run=request.dry_run)
        return RetryResult(
            original_run_id=request.run_id,
            outcome=RetryOutcome.RETRIED,
            attempt=request.attempt,
            monitor_status=record.monitor_status,
            reason=None,
            workflow_engine_result=engine_result,
        )
