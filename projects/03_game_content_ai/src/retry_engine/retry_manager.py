"""
Retry Manager（v3.0.0）

RetryManager:     Retry Engine全体の起動口
NullRetryManager: RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている
                  場合のダミー実装

設計方針:
    - Retry可否判定（RetryPolicyの適用）とRetryRequestの生成はここで行い、
      RetryExecutorには「再実行する」と決まった依頼だけを渡す
      （docs/design/retry_engine_foundation.md 10章 Design Decision #10）。
    - from_config() は呼び出し元が構築済みの WorkflowEngineManager / WorkflowMonitorManager
      を Dependency Injection で受け取る（Configから再構築しない）。これにより
      retry_engine パッケージは execution_history / ai / pipeline / scheduler を
      一切importせず、workflow_engine と workflow_monitor の2パッケージのみに依存する
      （同設計書10章 Design Decision #3）。
    - retry() は run_id のみを受け取り、その場で WorkflowMonitorManager.get_status() を
      呼んで最新状態を取得する（Read Before Retry、同設計書10章 Design Decision #9）。
    - Execution History は直接解釈しない。Workflow Monitor の公開APIのみを利用する。
    - retry() は dry_run（デフォルト False）を受け取り、生成する RetryRequest.dry_run へ
      そのまま渡す。RetryExecutor.execute() の既存挙動（RetryRequest.dry_run を
      WorkflowEngineManager.run(event, dry_run=...) へ伝播する）は変更しない。
"""
from __future__ import annotations

from datetime import datetime

from workflow_engine import NullWorkflowEngineManager, WorkflowEngineManager
from workflow_monitor import NullWorkflowMonitorManager, WorkflowMonitorManager, WorkflowMonitorStatus

from .retry_config import RetryConfig
from .retry_executor import RetryExecutor
from .retry_policy import RetryPolicy
from .retry_request import RetryRequest
from .retry_result import RetryOutcome, RetryResult


class RetryManager:
    """
    Retry Engine全体の起動口。

    Retry可否判定（RetryPolicyの適用）とRetryRequestの生成はここで行い、
    RetryExecutorには「再実行する」と決まった依頼だけを渡す。
    """

    def __init__(self, policy: RetryPolicy, executor: RetryExecutor, monitor: WorkflowMonitorManager):
        self._policy = policy
        self._executor = executor
        self._monitor = monitor

    @classmethod
    def from_config(
        cls,
        retry_config: RetryConfig,
        retry_policy: RetryPolicy,
        workflow_engine_manager: "WorkflowEngineManager | NullWorkflowEngineManager",
        workflow_monitor_manager: "WorkflowMonitorManager | NullWorkflowMonitorManager",
    ) -> "RetryManager | NullRetryManager":
        """
        呼び出し元が構築済みの WorkflowEngineManager / WorkflowMonitorManager を
        Dependency Injection で受け取る（Configから再構築しない）。

        RETRY_ENGINE_ENABLED が false、または workflow_engine_manager が
        NullWorkflowEngineManager（下位ゲートが閉じている）の場合は NullRetryManager を返す。
        """
        if not retry_config.is_ready():
            return NullRetryManager()
        if isinstance(workflow_engine_manager, NullWorkflowEngineManager):
            return NullRetryManager()

        executor = RetryExecutor(workflow_engine_manager=workflow_engine_manager)
        return cls(policy=retry_policy, executor=executor, monitor=workflow_monitor_manager)

    def retry(self, run_id: str, attempt: int = 1, dry_run: bool = False) -> RetryResult:
        """
        run_idの現在の状態をWorkflow Monitorから都度読み取り（Read Before Retry）、
        RetryPolicyを適用して再実行可否を判定し、対象であればRetryRequestを生成して
        RetryExecutorへ委譲する。dry_runはそのままRetryRequest.dry_runへ渡される。
        """
        record = self._monitor.get_status(run_id)
        if record is None:
            return RetryResult(
                original_run_id=run_id, outcome=RetryOutcome.NOT_FOUND, attempt=attempt,
                monitor_status=None, reason=f"run_id={run_id} was not found in Workflow Monitor.",
                workflow_engine_result=None,
            )

        if not self._policy.should_retry(record.monitor_status, attempt):
            return RetryResult(
                original_run_id=run_id, outcome=RetryOutcome.SKIPPED, attempt=attempt,
                monitor_status=record.monitor_status,
                reason=self._skip_reason(record.monitor_status, attempt),
                workflow_engine_result=None,
            )

        request = RetryRequest(run_id=run_id, attempt=attempt, requested_at=datetime.now(), dry_run=dry_run)
        return self._executor.execute(request, record)

    def _skip_reason(self, monitor_status: WorkflowMonitorStatus, attempt: int) -> str:
        if monitor_status not in self._policy.target_statuses:
            return (
                f"monitor_status={monitor_status.value} is not a retry target "
                f"({sorted(s.value for s in self._policy.target_statuses)})."
            )
        return f"attempt {attempt} has reached max_attempts={self._policy.max_attempts}."


class NullRetryManager:
    """RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている場合のダミー実装。"""

    def retry(self, run_id: str, attempt: int = 1, dry_run: bool = False) -> RetryResult:
        return RetryResult(
            original_run_id=run_id, outcome=RetryOutcome.DISABLED, attempt=attempt,
            monitor_status=None,
            reason="Retry Engine is disabled (RETRY_ENGINE_ENABLED=false, "
                   "or AI_AGENT_ENABLED/WORKFLOW_ENGINE_ENABLED is not ready).",
            workflow_engine_result=None,
        )
