"""
Retry Engine パッケージ（v3.0.0）

Workflow Monitor（v2.9.0）が FAILED / TIMEOUT と判定したWorkflowを、Workflow Engine
（v2.7.0）の公開APIを通じて再実行する最小基盤。Workflow Monitor・Workflow Engine
いずれの判定・実行ロジックにも変更を加えない。

処理フロー（v3.0.0）:
    RetryManager.retry(run_id)
        → WorkflowMonitorManager.get_status(run_id)（Read Before Retry）
        → RetryPolicy.should_retry(monitor_status, attempt) を判定
        → 対象であれば RetryRequest を生成し RetryExecutor.execute() へ委譲
        → RetryExecutor が WorkflowEngineEvent を組み立て WorkflowEngineManager.run() を呼ぶ
        → RetryResult を返す

設計方針:
    - src/workflow_monitor/ と src/workflow_engine/ の公開APIのみをimportする。
      src/execution_history/ / src/ai/ / src/pipeline/ / src/scheduler/ はいずれも
      importしない（Workflow Engineの構築に必要なこれらへの依存は workflow_engine
      パッケージの内部に閉じたままとする）。
    - Retry Engine自身はWorkflowの状態を保持しない（Stateless）。判定は毎回
      Workflow Monitor に問い合わせる。
    - RETRY_ENGINE_ENABLED=false（デフォルト）の場合はNullRetryManagerがすべて
      no-opで動作する。
"""
from .retry_config import RetryConfig
from .retry_policy import DEFAULT_TARGET_STATUSES, RetryPolicy
from .retry_request import RetryRequest
from .retry_result import RetryOutcome, RetryResult
from .retry_executor import RetryExecutor
from .retry_manager import NullRetryManager, RetryManager

__all__ = [
    "RetryPolicy",
    "DEFAULT_TARGET_STATUSES",
    "RetryConfig",
    "RetryRequest",
    "RetryOutcome",
    "RetryResult",
    "RetryExecutor",
    "RetryManager",
    "NullRetryManager",
]
