"""
Retry Composition Root（v5.1.0、v5.2.0でScheduler系配線を追加）

RetryCompositionRoot: workflow_monitor / retry_queue / retry_history /
                       retry_enqueue_trigger / retry_engine / workflow_engine /
                       retry_scheduler_source / retry_scheduler_decision / scheduler の
                       既存 from_env()/from_config() のみを呼び出して組み立て、
                       RetryQueueManager / RetryHistoryManager を共有インスタンスとして
                       RetryEnqueueTrigger（Enqueue側）と RetryManager（Execute側）の
                       両方へ注入するComposition Root。

設計方針:
    - 本クラスの責務は「組み立てて属性として公開すること」のみに限定する。
      enqueue_pending_failures() / execute_dispatchable_retries() 等の呼び出し、
      実行順序の決定、ループ・デーモン化はいずれも行わない（Non-Goal。
      docs/design/retry_composition_root_foundation.md 1.3節）。
    - RetryQueueManager / RetryHistoryManager はそれぞれ from_env() 内で1インスタンスのみ
      生成し、RetryEnqueueTrigger と RetryManager の両方へ同一インスタンスとして注入する。
      これにより、将来これらを同一プロセス内で呼び出す場合に、EnqueueとExecuteが
      Queue内容・再試行履歴を正しく共有できる（同設計書2章）。
    - 新規business logicは追加しない。各値の組み立ては既存の from_env()/from_config()
      への委譲のみで完結する。
    - RetryEnqueueTrigger / RetryEnqueueGuard はFeature Gateを持たない設計
      （v4.6.0・v4.8.0）のため、本Releaseでも常に実体を構築する。渡す monitor / queue が
      Null実装（各Configのゲートが閉じている場合）であっても、RetryEnqueueTrigger自体は
      Null実装側の安全な戻り値（空リスト・DISABLED）をそのまま受け取って動作する。
    - RetryManager.from_config() は RETRY_ENGINE_ENABLED や下位ゲート（AI_AGENT_ENABLED /
      WORKFLOW_ENGINE_ENABLED）が閉じている場合、既存の挙動どおり NullRetryManager を返す
      （retry_engine側は無改修）。
    - 既存パッケージ（workflow_monitor / retry_queue / retry_history /
      retry_enqueue_trigger / retry_engine / workflow_engine / ai / execution_history）は
      いずれも本Releaseでも無改修。

    - （v5.2.0）RetryQueueManagerに積まれた再試行候補を、将来SchedulerEvent経由で
      実行可能な状態にするため、RetrySchedulerSource / RetrySchedulerDecision / SchedulerEngine
      の3コンポーネントを新たに組み立てる（Retry Runtime Orchestrator Foundation）。
      RetrySchedulerSource には trigger/manager と同一の queue インスタンスを注入し、
      RetrySchedulerDecision には retry_source を、SchedulerEngine には
      retry_source / retry_decision の両方を Constructor Injection で渡す。
    - （v5.2.0）retry_scheduler_source / retry_scheduler_decision / scheduler はいずれも
      本Releaseでも無改修。RetryCompositionRoot が既存の公開コンストラクタを呼び出す
      だけであり、新規business logicは追加しない。
"""
from __future__ import annotations

from pathlib import Path

from ai import AgentConfig
from execution_history import ExecutionHistoryConfig
from retry_engine import NullRetryManager, RetryConfig, RetryManager, RetryPolicy
from retry_enqueue_trigger import RetryEnqueueGuard, RetryEnqueueTrigger
from retry_history import RetryHistoryManager
from retry_queue import NullRetryQueueManager, RetryQueueConfig, RetryQueueManager
from retry_scheduler_decision import RetrySchedulerDecision
from retry_scheduler_source import NullRetrySchedulerSource, RetrySchedulerSource
from scheduler import SchedulerEngine
from workflow_engine import NullWorkflowEngineManager, WorkflowEngineConfig, WorkflowEngineManager
from workflow_monitor import NullWorkflowMonitorManager, WorkflowMonitorConfig, WorkflowMonitorManager

# src/retry_composition/retry_composition_root.py から見たプロジェクトルート
_PROJECT_ROOT = Path(__file__).parent.parent.parent


class RetryCompositionRoot:
    """
    Retry関連コンポーネントを、Queue/Historyインスタンスを共有した状態で束ねる
    Composition Root。実行・判定・ループはいずれも行わない。
    """

    def __init__(
        self,
        monitor: "WorkflowMonitorManager | NullWorkflowMonitorManager",
        queue: "RetryQueueManager | NullRetryQueueManager",
        history: RetryHistoryManager,
        guard: RetryEnqueueGuard,
        trigger: RetryEnqueueTrigger,
        policy: RetryPolicy,
        manager: "RetryManager | NullRetryManager",
        retry_source: "RetrySchedulerSource | NullRetrySchedulerSource",
        retry_decision: RetrySchedulerDecision,
        scheduler: SchedulerEngine,
    ):
        self.monitor = monitor
        self.queue = queue
        self.history = history
        self.guard = guard
        self.trigger = trigger
        self.policy = policy
        self.manager = manager
        self.retry_source = retry_source
        self.retry_decision = retry_decision
        self.scheduler = scheduler

    @classmethod
    def from_env(cls, base_dir: Path | None = None) -> "RetryCompositionRoot":
        """
        環境変数・既存Configの from_env()/from_config() のみを使って
        RetryCompositionRoot を組み立てる。

        base_dir省略時は本ファイルの位置から算出したプロジェクトルートを使用する
        （scripts/run_workflow_engine.py の base_dir 解決と同じ考え方）。
        """
        project_root = base_dir if base_dir is not None else _PROJECT_ROOT

        monitor = WorkflowMonitorManager.from_config(
            ExecutionHistoryConfig.from_env(project_root=project_root),
            WorkflowMonitorConfig.from_env(),
        )
        queue = RetryQueueManager.from_config(RetryQueueConfig.from_env())
        history = RetryHistoryManager()
        guard = RetryEnqueueGuard()
        trigger = RetryEnqueueTrigger(monitor=monitor, queue=queue, history=history, guard=guard)

        retry_source = RetrySchedulerSource(queue)
        retry_decision = RetrySchedulerDecision(retry_source)
        scheduler = SchedulerEngine(retry_source=retry_source, retry_decision=retry_decision)

        policy = RetryPolicy.from_env()
        agent_config = AgentConfig.from_env(base_dir=project_root)
        workflow_engine_manager = WorkflowEngineManager.from_config(
            agent_config,
            WorkflowEngineConfig.from_env(project_root=project_root),
        )
        manager = RetryManager.from_config(
            retry_config=RetryConfig.from_env(),
            retry_policy=policy,
            workflow_engine_manager=workflow_engine_manager,
            workflow_monitor_manager=monitor,
            retry_queue_manager=queue,
            retry_history_manager=history,
        )

        return cls(
            monitor=monitor,
            queue=queue,
            history=history,
            guard=guard,
            trigger=trigger,
            policy=policy,
            manager=manager,
            retry_source=retry_source,
            retry_decision=retry_decision,
            scheduler=scheduler,
        )
