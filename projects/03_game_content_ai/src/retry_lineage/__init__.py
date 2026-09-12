"""
Retry Lineage パッケージ（v6.31.0、Release 6.31）

FAILED/TIMEOUT candidateをRetry Eligibilityへ安全に引き渡すための、
lineage・attempt lifecycle・durable stateの契約を提供する。

処理フロー（v6.31.0）:
    RetryManager._retry_locked(run_id, attempt)
        → RetryLineageManager.find_existing_lineage(run_id)（分岐(1)(2)、read-only）
          見つからなければ → WorkflowMonitorManager.get_status(run_id)
                            → RetryLineageManager.create_new_lineage(run_id, monitor_record)
                              （分岐(3)、initial admission gate）
        → RetryLineageManager.claim(root_run_id)
        → RetryExecutor.execute(...)（post-admission hookでmark_execution_started()）
        → decide_disposition() / compute_newly_confirmed()
        → RetryLineageManager.mark_terminal(...)

    RetryRuntimeOrchestrator.run_once()
        → RetryLineageManager.reconcile_all(resolve_status_fn=monitor.get_status)

設計方針:
    - src/execution_history/ / src/ai/ / src/workflow_engine/ / src/workflow_monitor/
      の公開APIをimportする。retry_engineへは、RetryPolicy互換のProtocol型ヒント
      （ExplainableRetryPolicy）をTYPE_CHECKING経由でのみ参照し、実行時の
      importは発生させない（retry_engine → retry_lineage の一方向依存のみで
      循環を避ける。retry_lineage_genuine_action.py冒頭の設計方針注記も参照）。
    - RETRY_LINEAGE_ENABLED=false（デフォルト）でも、find_existing_lineage() /
      create_new_lineage() / mark_execution_started() / mark_terminal() /
      open_next_attempt() / reconcile_all() はいずれも通常どおり動作する。
      claim()のみがこのゲートのfail-closedスイッチの対象（16章）。
"""
from .retry_execution_lock import RetryExecutionLock, RetryExecutionLockBusyError
from .retry_lineage_config import RetryLineageConfig
from .retry_lineage_disposition import RetryLineageDisposition
from .retry_lineage_genuine_action import (
    StepOutcomeCategory,
    classify_execution_history_step,
    classify_step_outcome,
)
from .retry_lineage_manager import RetryLineageManager
from .retry_lineage_phase import RetryLineagePhase
from .retry_lineage_record import (
    HumanReviewResolution,
    HumanReviewResolutionRecord,
    RetryAttemptExecutionScope,
    RetryLineageMembershipEntry,
    RetryLineageRecord,
    RetryLineageTransitionEvent,
)
from .retry_lineage_results import (
    ClaimResult,
    CreateNewLineageResult,
    MarkTerminalResult,
    OpenNextAttemptResult,
    ReconcileSummary,
    ResolveHumanReviewResult,
)
from .retry_lineage_store import JsonRetryLineageStore, RetryLineageStore
from .retry_lineage_store_lock import RetryLineageStoreLock, RetryLineageStoreLockError
from .retry_lineage_target_resolution import (
    SIDE_EFFECT_CONTRACT_VERSION,
    ContractVersionEvidence,
    RetryLineageContractVersionError,
    classify_contract_version_evidence,
    compute_initial_confirmed_steps,
    compute_newly_confirmed,
    compute_steps_to_execute,
    decide_disposition,
    disposition_from_categories,
    is_6_32_contract_lineage,
    resolve_final_disposition,
)

__all__ = [
    "RetryLineageConfig",
    "RetryLineagePhase",
    "RetryLineageDisposition",
    "StepOutcomeCategory",
    "classify_step_outcome",
    "classify_execution_history_step",
    "decide_disposition",
    "disposition_from_categories",
    "compute_newly_confirmed",
    "compute_steps_to_execute",
    "compute_initial_confirmed_steps",
    "RetryLineageMembershipEntry",
    "RetryLineageTransitionEvent",
    "RetryAttemptExecutionScope",
    "RetryLineageRecord",
    "RetryLineageStore",
    "JsonRetryLineageStore",
    "RetryLineageStoreLock",
    "RetryLineageStoreLockError",
    "RetryExecutionLock",
    "RetryExecutionLockBusyError",
    "CreateNewLineageResult",
    "ClaimResult",
    "MarkTerminalResult",
    "OpenNextAttemptResult",
    "ReconcileSummary",
    "RetryLineageManager",
    "HumanReviewResolution",
    "HumanReviewResolutionRecord",
    "ResolveHumanReviewResult",
    "SIDE_EFFECT_CONTRACT_VERSION",
    "ContractVersionEvidence",
    "RetryLineageContractVersionError",
    "classify_contract_version_evidence",
    "is_6_32_contract_lineage",
    "resolve_final_disposition",
]
