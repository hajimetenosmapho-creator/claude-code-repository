"""
Retry Runtime Orchestrator（v5.2.0）

RetryRuntimeOrchestrator: Retry Runtimeの実行順序を将来管理する場所。
                           RetryCompositionRootが組み立てた各コンポーネントへの
                           参照を保持するだけで、実行順序の決定・ループ・
                           デーモン化はいずれも行わない。

設計方針:
    - 本クラスの責務は「参照を保持すること」のみに限定する。run() / run_once() /
      loop() / daemon() / execute()等はいずれも追加しない（Non-Goal。
      docs/design/retry_runtime_orchestrator_foundation.md 1.3節）。
    - Composition（組み立て）は RetryCompositionRoot の責務であり続ける。
      本クラスは新規インスタンスを一切生成せず、RetryCompositionRoot が
      生成した既存インスタンスをそのまま受け取る（同設計書2章）。
    - trigger / scheduler / manager / queue / history / policy の6つを保持する。
      queue / history は trigger・manager が内部で参照するものと同一の
      インスタンスであり、本クラスが新たに参照を分岐させることはない。
    - 次Release（Execution Release）で、`manager.execute_dispatchable_retries()`を
      1回だけ呼び出し、その結果（RetryExecutionResultのリスト）を保持したうえで
      RetryQueueUpdateDecider等の既存Decider/Executor群（retry_engineが既に公開
      している）へ配布する設計を予定している（同設計書3章・6章）。本Releaseでは
      その実装には着手しない。
    - guard（RetryEnqueueTrigger専属の内部コンポーネント）・monitor（将来依存が
      未確定）は保持しない（同設計書2.4節）。
"""
from __future__ import annotations

from retry_composition import RetryCompositionRoot
from retry_engine import NullRetryManager, RetryManager, RetryPolicy
from retry_enqueue_trigger import RetryEnqueueTrigger
from retry_history import RetryHistoryManager
from retry_queue import NullRetryQueueManager, RetryQueueManager
from scheduler import SchedulerEngine


class RetryRuntimeOrchestrator:
    """
    Retry Runtimeの実行順序を将来管理する場所。

    trigger / scheduler / manager / queue / history / policy への参照を
    Constructor Injectionで保持するだけで、実行順序の決定・ループ・
    デーモン化はいずれも行わない。
    """

    def __init__(
        self,
        trigger: RetryEnqueueTrigger,
        scheduler: SchedulerEngine,
        manager: "RetryManager | NullRetryManager",
        queue: "RetryQueueManager | NullRetryQueueManager",
        history: RetryHistoryManager,
        policy: RetryPolicy,
    ):
        self.trigger = trigger
        self.scheduler = scheduler
        self.manager = manager
        self.queue = queue
        self.history = history
        self.policy = policy

    @classmethod
    def from_composition_root(cls, root: RetryCompositionRoot) -> "RetryRuntimeOrchestrator":
        """
        RetryCompositionRootが組み立てた既存インスタンスをそのまま受け取って
        RetryRuntimeOrchestratorを構築する。新規インスタンスは生成しない。
        """
        return cls(
            trigger=root.trigger,
            scheduler=root.scheduler,
            manager=root.manager,
            queue=root.queue,
            history=root.history,
            policy=root.policy,
        )
