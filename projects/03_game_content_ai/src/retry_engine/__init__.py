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

    - （v3.8.0）RetryManager が RetryEventConsumer（retry_event_consumer、新設）を
      Constructor Injection で保持できるようになった（Retry Engine Event
      Consumption）。recognize_retry_events() を通じて、Scheduler（v3.7.0）が
      生成したRetry候補由来のSchedulerEventを認識できるが、認識のみで
      実行判断・Queue操作には一切関与しない。src/scheduler/ /
      src/retry_scheduler_decision/ / src/retry_scheduler_source/ /
      src/retry_queue/ はいずれも本Releaseでも無改修
      （詳細は docs/design/retry_engine_event_consumption.md）

    - （v3.9.0）RetryManager が RetryEventDispatcher（retry_event_dispatcher、新設）を
      Constructor Injection で保持できるようになった（Retry Engine Event
      Dispatch）。dispatch_retry_events() を通じて、recognize_retry_events()
      （v3.8.0）が認識したRetryCandidateEventをDispatch対象として整理できるが、
      整理のみで実行判断・Queue操作には一切関与しない。src/scheduler/ /
      src/retry_scheduler_decision/ / src/retry_scheduler_source/ /
      src/retry_queue/ / retry_event_consumer.py はいずれも本Releaseでも無改修
      （詳細は docs/design/retry_engine_event_dispatch.md）

    - （v4.0.0）RetryManager が RetryExecutionSelector（retry_execution_selector、新設）・
      RetryExecutionCoordinator（retry_execution_coordinator、新設）を Constructor
      Injection で保持できるようになった（Retry Execution Foundation）。
      execute_dispatchable_retries() を通じて、dispatch_retry_events()（v3.9.0）が
      整理したRetryDispatchEventのうちdispatchable=Trueのものだけを選別し、初めて
      RetryManager.retry() を呼び出せるようになった。判定（Selector）と実行・結果集約
      （Coordinator）は責務を分離しており、Retry Queueの更新・enqueue_retry() /
      dequeue_retry() / RetryQueueManager.dequeue() / remove()・Queue永続化には
      一切関与しない。src/scheduler/ / src/retry_scheduler_decision/ /
      src/retry_scheduler_source/ / src/retry_queue/ / retry_event_consumer.py /
      retry_event_dispatcher.py はいずれも本Releaseでも無改修
      （詳細は docs/design/retry_execution_foundation.md）

    - （v4.1.0）RetryManager が RetryQueueUpdateDecider（retry_queue_update_decider、
      新設）を Constructor Injection で保持できるようになった（Retry Queue Update
      Foundation）。decide_retry_queue_updates() を通じて、execute_dispatchable_retries()
      （v4.0.0）が集約したRetryExecutionResultのそれぞれについて、対応するRetry Queue
      項目の更新先状態（RetryQueueStatus.COMPLETED / FAILED、あるいは更新なし）を
      判定できるが、判定のみで実際にQueueへ反映する処理（RetryQueueManager.remove()の
      呼び出し等）には一切関与しない。src/scheduler/ / src/retry_scheduler_decision/ /
      src/retry_scheduler_source/ / src/retry_queue/ / retry_event_consumer.py /
      retry_event_dispatcher.py / retry_execution_selector.py /
      retry_execution_coordinator.py はいずれも本Releaseでも無改修
      （詳細は docs/design/retry_queue_update_foundation.md）

    - （v4.2.0）RetryManager が RetryQueueRemovalExecutor（retry_queue_removal_executor、
      新設）を Constructor Injection で保持できるようになった（Retry Queue Removal
      Foundation）。apply_retry_queue_removals() を通じて、decide_retry_queue_updates()
      （v4.1.0）が判定したRetryQueueUpdateDecisionのうち、outcomeがCOMPLETE / FAILの
      項目についてのみ RetryQueueManager.remove() を呼び出し、Queueから該当項目を
      除去できるようになった。RetryQueueManager.remove() が本Releaseで初めて呼び出し
      可能になる。NOOP（SKIPPED / NOT_FOUND / DISABLED由来）の項目はremoveを一切
      呼び出さない。SKIPPED（max_attempts到達）のQueue滞留対応は本Releaseの対象外。
      src/scheduler/ / src/retry_scheduler_decision/ / src/retry_scheduler_source/ /
      src/retry_queue/ / retry_event_consumer.py / retry_event_dispatcher.py /
      retry_execution_selector.py / retry_execution_coordinator.py /
      retry_queue_update_decider.py はいずれも本Releaseでも無改修
      （詳細は docs/design/retry_queue_removal_foundation.md）

    - （v4.3.0）RetryManager が RetryQueueCleanupDecider（retry_queue_cleanup_decider、
      新設）・RetryQueueCleanupExecutor（retry_queue_cleanup_executor、新設）を
      Constructor Injection で保持できるようになった（Retry Queue Cleanup Foundation）。
      decide_retry_queue_cleanup() / apply_retry_queue_cleanup() を通じて、
      decide_retry_queue_updates()（v4.1.0）が判定したRetryQueueUpdateDecisionのうち、
      SKIPPED由来のNOOPの項目についてのみ RetryQueueManager.remove() を呼び出し、
      v4.2.0で対象外だったQueue滞留を解消できるようになった。COMPLETE / FAILED
      （v4.2.0で除去済み） / NOT_FOUND / DISABLEDはいずれも対象外（KEEP）。新しい
      Queueステータス・Dead Letter・隔離Queueは追加せず、既存のRetryQueueManager.remove()
      を再利用する。src/scheduler/ / src/retry_scheduler_decision/ /
      src/retry_scheduler_source/ / src/retry_queue/ / retry_event_consumer.py /
      retry_event_dispatcher.py / retry_execution_selector.py /
      retry_execution_coordinator.py / retry_queue_update_decider.py /
      retry_queue_removal_executor.py はいずれも本Releaseでも無改修
      （詳細は docs/design/retry_queue_cleanup_foundation.md）

    - （v4.4.0）RetryManager が RetryQueueTerminalCleanupDecider
      （retry_queue_terminal_cleanup_decider、新設）・RetryQueueTerminalCleanupExecutor
      （retry_queue_terminal_cleanup_executor、新設）を Constructor Injection で
      保持できるようになった（NOT_FOUND / DISABLED Cleanup Foundation）。
      decide_retry_queue_terminal_cleanup() / apply_retry_queue_terminal_cleanup() を
      通じて、decide_retry_queue_updates()（v4.1.0）が判定したRetryQueueUpdateDecision
      のうち、NOT_FOUND由来のNOOPの項目についてのみ RetryQueueManager.remove() を
      呼び出せるようになった（retry_outcome_terminality.RETRY_OUTCOME_TERMINALITY
      分類表でTERMINALと分類。新設）。DISABLED由来のNOOPはTRANSIENTと分類され対象外
      （KEEP）のまま。COMPLETE / FAILED（v4.2.0で除去済み） / SKIPPED（v4.3.0で
      除去済み）はいずれも対象外（KEEP）。新しいQueueステータス・Dead Letter・隔離Queue
      は追加せず、既存のRetryQueueManager.remove()を再利用する。src/scheduler/ /
      src/retry_scheduler_decision/ / src/retry_scheduler_source/ / src/retry_queue/ /
      retry_event_consumer.py / retry_event_dispatcher.py / retry_execution_selector.py /
      retry_execution_coordinator.py / retry_queue_update_decider.py /
      retry_queue_removal_executor.py / retry_queue_cleanup_decider.py /
      retry_queue_cleanup_executor.py はいずれも本Releaseでも無改修
      （詳細は docs/design/retry_queue_notfound_disabled_cleanup_foundation.md）

    - （v4.5.0）RetryManagerが実際に依存している面（retry()が呼び出す
      should_retry()、_skip_reason()が参照するtarget_statuses / max_attempts）を
      Protocolとして明示化した RetryDecisionPolicy（最小契約）・
      ExplainableRetryPolicy（RetryDecisionPolicyを拡張した説明可能契約）を
      retry_policy_protocol（新設）に追加した（Retry Policy Foundation）。
      RetryManager.__init__() / from_config() の policy / retry_policy引数の
      型注釈をRetryPolicyからExplainableRetryPolicyへ変更したが、型注釈のみの
      変更でありretry() / _skip_reason()のロジック本体・RetryPolicy
      （retry_policy.py）自体はいずれも無改修。将来のRetry戦略
      （FixedRetryPolicy / ExponentialBackoffPolicy / AdaptiveRetryPolicy等）の
      実装は本Releaseの対象外（Non-Goal）
      （詳細は docs/design/retry_policy_foundation.md）

    - （v4.7.0）RetryManager が RetryHistoryManager / NullRetryHistoryManager
      （retry_history、新規独立パッケージ）・RetryHistoryRecordExecutor
      （retry_history_recorder、新設）を Constructor Injection で保持できる
      ようになった（Retry History Foundation）。record_retry_history() を通じて、
      execute_dispatchable_retries()（v4.0.0、無変更）が集約したRetryExecutionResult
      のうち、outcomeがRETRIEDの項目についてのみRetryHistoryManager.record()を
      呼び出し、original_run_idごとの再試行履歴（試行回数・直近記録時刻）を
      記録できるようになった。retry_historyはstateful storeでありretry_queueと
      同じ扱いのため、historyの省略時はNullRetryHistoryManager()にフォールバック
      する。metadata["retried_from"]は現状ExecutionHistoryへ永続化されておらず
      参照できないため、本Releaseの情報源はRetryManager自身が生成するRetryResult
      のみとした。記録結果を使ってRetryEnqueueTrigger側の再enqueueガード判定に
      反映する処理は本Releaseの対象外（Foundation First。次Release以降で検討）。
      retry_history は retry_engine を一切importしない（循環なし）。src/scheduler/ /
      src/retry_scheduler_decision/ / src/retry_scheduler_source/ / src/retry_queue/ /
      retry_event_consumer.py / retry_event_dispatcher.py / retry_execution_selector.py /
      retry_execution_coordinator.py / retry_queue_update_decider.py /
      retry_queue_removal_executor.py / retry_queue_cleanup_decider.py /
      retry_queue_cleanup_executor.py / retry_queue_terminal_cleanup_decider.py /
      retry_queue_terminal_cleanup_executor.py / retry_outcome_terminality.py /
      retry_policy.py / retry_policy_protocol.py はいずれも本Releaseでも無改修
      （詳細は docs/design/retry_history_foundation.md）

    - （v5.6.0）RetryOutcomeにDRY_RUN（retry_result.py）を追加した（Retry Runtime
      Safe Dry Run Foundation）。RetryExecutor.execute()がdry_run=Trueの場合、
      outcome=RETRIEDではなくoutcome=DRY_RUNを返すようになり、後続の
      RetryQueueUpdateDecider・RetryHistoryRecordExecutor・RetryQueueRemovalExecutor・
      RetryQueueCleanupDeciderはいずれも無改修のまま自動的に安全側（NOOP・記録なし・
      除去なし）に倒れる。唯一retry_outcome_terminality.py（classify_reason()が
      明示列挙+raiseの網羅チェック方式のため）のみ、RetryCleanupReason.DRY_RUN追加・
      classify_reason()の分岐追加・RETRY_OUTCOME_TERMINALITYへのDRY_RUN→TRANSIENT
      追加が必須だった。retry_manager.py・retry_execution_coordinator.py等、
      dry_run引数を既に受け取っていた既存箇所は無改修（詳細は
      docs/design/retry_runtime_safe_dry_run_foundation.md）
"""
from .retry_config import RetryConfig
from .retry_policy import DEFAULT_TARGET_STATUSES, RetryPolicy
from .retry_policy_protocol import ExplainableRetryPolicy, RetryDecisionPolicy
from .retry_request import RetryRequest
from .retry_result import RetryOutcome, RetryResult
from .retry_executor import RetryExecutor
from .retry_event_consumer import RetryCandidateEvent, RetryEventConsumer
from .retry_event_dispatcher import RetryDispatchEvent, RetryEventDispatcher
from .retry_execution_selector import RetryExecutionSelector
from .retry_execution_coordinator import RetryExecutionCoordinator, RetryExecutionResult
from .retry_queue_update_decider import (
    RetryQueueUpdateDecider,
    RetryQueueUpdateDecision,
    RetryQueueUpdateOutcome,
)
from .retry_queue_removal_executor import RetryQueueRemovalExecutor, RetryQueueRemovalResult
from .retry_queue_cleanup_decider import (
    RetryQueueCleanupDecider,
    RetryQueueCleanupDecision,
    RetryQueueCleanupOutcome,
)
from .retry_queue_cleanup_executor import RetryQueueCleanupExecutor, RetryQueueCleanupResult
from .retry_outcome_terminality import (
    RETRY_OUTCOME_TERMINALITY,
    RetryCleanupReason,
    RetryOutcomeTerminality,
    classify_reason,
    classify_terminality,
)
from .retry_queue_terminal_cleanup_decider import (
    RetryQueueTerminalCleanupDecider,
    RetryQueueTerminalCleanupDecision,
)
from .retry_queue_terminal_cleanup_executor import (
    RetryQueueTerminalCleanupExecutor,
    RetryQueueTerminalCleanupResult,
)
from .retry_history_recorder import RetryHistoryRecordExecutor, RetryHistoryRecordResult
from .retry_manager import NullRetryManager, RetryManager

__all__ = [
    "RetryPolicy",
    "DEFAULT_TARGET_STATUSES",
    "RetryDecisionPolicy",
    "ExplainableRetryPolicy",
    "RetryConfig",
    "RetryRequest",
    "RetryOutcome",
    "RetryResult",
    "RetryExecutor",
    "RetryCandidateEvent",
    "RetryEventConsumer",
    "RetryDispatchEvent",
    "RetryEventDispatcher",
    "RetryExecutionSelector",
    "RetryExecutionCoordinator",
    "RetryExecutionResult",
    "RetryQueueUpdateOutcome",
    "RetryQueueUpdateDecision",
    "RetryQueueUpdateDecider",
    "RetryQueueRemovalResult",
    "RetryQueueRemovalExecutor",
    "RetryQueueCleanupOutcome",
    "RetryQueueCleanupDecision",
    "RetryQueueCleanupDecider",
    "RetryQueueCleanupResult",
    "RetryQueueCleanupExecutor",
    "RetryOutcomeTerminality",
    "RetryCleanupReason",
    "RETRY_OUTCOME_TERMINALITY",
    "classify_reason",
    "classify_terminality",
    "RetryQueueTerminalCleanupDecision",
    "RetryQueueTerminalCleanupDecider",
    "RetryQueueTerminalCleanupResult",
    "RetryQueueTerminalCleanupExecutor",
    "RetryHistoryRecordResult",
    "RetryHistoryRecordExecutor",
    "RetryManager",
    "NullRetryManager",
]
