"""
Retry Manager（v3.0.0 / v3.2.0でRetry Queue統合を追加）

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

    - （v3.2.0）RetryManager は RetryQueueManager / NullRetryQueueManager を
      Dependency Injection で保持できる（省略時は NullRetryQueueManager() に
      フォールバックする）。enqueue_retry() / dequeue_retry() は
      RetryQueueManager.enqueue() / dequeue() への薄い委譲のみであり、
      判定・加工は一切行わない（docs/design/retry_queue_integration.md 4章）。
    - （v3.2.0）retry()（Retry実行）と enqueue_retry() / dequeue_retry()（Queue操作）は
      呼び出しグラフ上で完全に独立している。dequeue_retry() が取り出した
      RetryQueueItem を retry() へ渡す変換ロジックは持たない（自動実行はしない。
      同設計書5章・10章 Design Decision #4）。
    - （v3.2.0）src/retry_queue/ は本Releaseでも無改修。RetryManager は
      retry_queue パッケージの公開シンボル（__init__.py の __all__）のみを
      importする（同設計書6章）。

    - （v3.8.0）RetryManager は RetryEventConsumer（retry_event_consumer、新設）を
      Constructor Injection で保持できる（省略時は RetryEventConsumer() に
      自動フォールバックする。RetryEventConsumerはConfig不要のStatelessな
      コンポーネントであるため、v3.4.0の RetrySchedulerSource と同様に
      「省略時は安全な実装へ自動フォールバックする」方式を採用する。
      docs/design/retry_engine_event_consumption.md 13章 Design Decision #5）。
    - （v3.8.0）recognize_retry_events() を新設し、
      RetryEventConsumer.recognize_all() への薄い委譲のみを行う。
      retry()（Retry実行）・enqueue_retry() / dequeue_retry()（Queue操作）とは
      呼び出しグラフ上で完全に独立しており、認識結果を使って自動的に
      何かを実行する処理はここにはない（自動実行はしない。同設計書9.2節）。
    - （v3.8.0）RetryManager が scheduler パッケージへ依存する初めてのReleaseだが、
      importするのは SchedulerEvent 型のみ（SchedulerEngine 等の実行系クラスは
      importしない）。src/scheduler/ / src/retry_scheduler_decision/ /
      src/retry_scheduler_source/ / src/retry_queue/ は本Releaseでも無改修
      （同設計書3章）。

    - （v3.9.0）RetryManager は RetryEventDispatcher（retry_event_dispatcher、新設）を
      Constructor Injection で保持できる（省略時は RetryEventDispatcher() に
      自動フォールバックする。RetryEventDispatcherもConfig不要のStatelessな
      コンポーネントであるため、v3.8.0の RetryEventConsumer と同様に
      「省略時は安全な実装へ自動フォールバックする」方式を採用する。
      docs/design/retry_engine_event_dispatch.md 13章 Design Decision #5）。
    - （v3.9.0）dispatch_retry_events() を新設し、recognize_retry_events()（v3.8.0）
      への委譲、続けて RetryEventDispatcher.dispatch() への薄い委譲、の2段階のみで
      完結する。retry()（Retry実行）・enqueue_retry() / dequeue_retry()（Queue操作）とは
      呼び出しグラフ上で完全に独立しており、Dispatch結果を使って自動的に
      何かを実行する処理はここにはない（自動実行はしない。同設計書9.2節）。
    - （v3.9.0）dispatchable の判定基準は RetryCandidateEvent.run_id が空でないかという
      構造的妥当性のみに限定する。優先度・件数上限に基づく選別ロジックは
      本Releaseの対象外（同設計書13章 Design Decision #2）。

    - （v4.0.0）RetryManager は RetryExecutionSelector（retry_execution_selector、新設）と
      RetryExecutionCoordinator（retry_execution_coordinator、新設）を Constructor Injection
      で保持できる（省略時はそれぞれ RetryExecutionSelector() / RetryExecutionCoordinator() に
      自動フォールバックする。docs/design/retry_execution_foundation.md 14章 Design Decision #8）。
    - （v4.0.0）execute_dispatchable_retries() を新設し、dispatch_retry_events()（v3.9.0）への
      委譲、RetryExecutionSelector.select()（dispatchable=True のみ選別。判定を1箇所に集約）、
      RetryExecutionCoordinator.execute()（選別済みの候補についてself.retryを呼び出し、
      結果を集約）の3段階のみで完結する。enqueue_retry() / dequeue_retry()（Queue操作）とは
      呼び出しグラフ上で完全に独立しており、Retry Queueの更新は一切行わない
      （同設計書9章・10章）。

    - （v4.1.0）RetryManager は RetryQueueUpdateDecider（retry_queue_update_decider、新設）を
      Constructor Injection で保持できる（省略時は RetryQueueUpdateDecider() に自動
      フォールバックする。docs/design/retry_queue_update_foundation.md 3章 Design Policy 4）。
    - （v4.1.0）decide_retry_queue_updates() を新設し、execute_dispatchable_retries()
      （v4.0.0）への委譲、RetryQueueUpdateDecider.decide_all()（各RetryExecutionResultから
      更新先のRetryQueueStatusを判定）の2段階のみで完結する。判定結果を実際に
      RetryQueueManager.remove() 等でQueueへ反映する処理はここには一切なく（Foundation
      First）、enqueue_retry() / dequeue_retry()（Queue操作）とは呼び出しグラフ上で
      完全に独立している（同設計書9章・11章）。

    - （v4.2.0）RetryManager は RetryQueueRemovalExecutor（retry_queue_removal_executor、
      新設）を Constructor Injection で保持できる（省略時は RetryQueueRemovalExecutor() に
      自動フォールバックする。docs/design/retry_queue_removal_foundation.md 3章 Design
      Policy 4）。
    - （v4.2.0）apply_retry_queue_removals() を新設し、decide_retry_queue_updates()
      （v4.1.0）への委譲、RetryQueueRemovalExecutor.apply_all()（各RetryQueueUpdateDecision
      についてoutcomeがCOMPLETE/FAILの項目のみRetryQueueManager.remove()を呼び出す）の
      2段階のみで完結する。remove_fnにはself._queue.remove（v3.2.0で既に保持している
      Queueのバウンドメソッド）を渡すのみであり、retry_manager.py自体に新規の
      RetryQueueManager型への依存は発生しない。NOOP（SKIPPED / NOT_FOUND / DISABLED
      由来）の項目はremove_fnを一切呼び出さない（同設計書4章・11章）。

    - （v4.3.0）RetryManager は RetryQueueCleanupDecider（retry_queue_cleanup_decider、
      新設）と RetryQueueCleanupExecutor（retry_queue_cleanup_executor、新設）を
      Constructor Injection で保持できる（省略時はそれぞれ RetryQueueCleanupDecider() /
      RetryQueueCleanupExecutor() に自動フォールバックする。
      docs/design/retry_queue_cleanup_foundation.md 3章 Design Policy 4）。
    - （v4.3.0）decide_retry_queue_cleanup() を新設し、decide_retry_queue_updates()
      （v4.1.0）への委譲、RetryQueueCleanupDecider.decide_all()（各RetryQueueUpdateDecision
      についてSKIPPED由来のNOOPのみCLEANUPと判定する）の2段階のみで完結する。
    - （v4.3.0）apply_retry_queue_cleanup() を新設し、decide_retry_queue_cleanup()への
      委譲、RetryQueueCleanupExecutor.apply_all()（outcomeがCLEANUPの項目のみ
      RetryQueueManager.remove()を呼び出す）の2段階のみで完結する。remove_fnには
      apply_retry_queue_removals()と同じくself._queue.removeを渡すのみである。
      Cleanup対象はSKIPPEDのみで、COMPLETE / FAILED（v4.2.0で除去済み） / NOT_FOUND /
      DISABLEDはいずれも対象外（KEEP）。新しいQueueステータス・Dead Letter・隔離Queueは
      追加せず、既存のRetryQueueManager.remove()を再利用する（同設計書4章・11章）。
"""
from __future__ import annotations

from datetime import datetime

from retry_queue import NullRetryQueueManager, RetryQueueManager, RetryQueueOutcome, RetryQueueResult
from scheduler import SchedulerEvent
from workflow_engine import NullWorkflowEngineManager, WorkflowEngineManager
from workflow_monitor import NullWorkflowMonitorManager, WorkflowMonitorManager, WorkflowMonitorStatus

from .retry_config import RetryConfig
from .retry_event_consumer import RetryCandidateEvent, RetryEventConsumer
from .retry_event_dispatcher import RetryDispatchEvent, RetryEventDispatcher
from .retry_execution_coordinator import RetryExecutionCoordinator, RetryExecutionResult
from .retry_execution_selector import RetryExecutionSelector
from .retry_executor import RetryExecutor
from .retry_policy import RetryPolicy
from .retry_queue_cleanup_decider import RetryQueueCleanupDecider, RetryQueueCleanupDecision
from .retry_queue_cleanup_executor import RetryQueueCleanupExecutor, RetryQueueCleanupResult
from .retry_queue_removal_executor import RetryQueueRemovalExecutor, RetryQueueRemovalResult
from .retry_queue_update_decider import RetryQueueUpdateDecider, RetryQueueUpdateDecision
from .retry_request import RetryRequest
from .retry_result import RetryOutcome, RetryResult


class RetryManager:
    """
    Retry Engine全体の起動口。

    Retry可否判定（RetryPolicyの適用）とRetryRequestの生成はここで行い、
    RetryExecutorには「再実行する」と決まった依頼だけを渡す。
    """

    def __init__(
        self,
        policy: RetryPolicy,
        executor: RetryExecutor,
        monitor: WorkflowMonitorManager,
        queue: "RetryQueueManager | NullRetryQueueManager | None" = None,
        event_consumer: RetryEventConsumer | None = None,
        event_dispatcher: RetryEventDispatcher | None = None,
        execution_selector: RetryExecutionSelector | None = None,
        execution_coordinator: RetryExecutionCoordinator | None = None,
        queue_update_decider: RetryQueueUpdateDecider | None = None,
        queue_removal_executor: RetryQueueRemovalExecutor | None = None,
        queue_cleanup_decider: RetryQueueCleanupDecider | None = None,
        queue_cleanup_executor: RetryQueueCleanupExecutor | None = None,
    ):
        self._policy = policy
        self._executor = executor
        self._monitor = monitor
        self._queue = queue if queue is not None else NullRetryQueueManager()
        self._event_consumer = event_consumer if event_consumer is not None else RetryEventConsumer()
        self._event_dispatcher = event_dispatcher if event_dispatcher is not None else RetryEventDispatcher()
        self._execution_selector = (
            execution_selector if execution_selector is not None else RetryExecutionSelector()
        )
        self._execution_coordinator = (
            execution_coordinator if execution_coordinator is not None else RetryExecutionCoordinator()
        )
        self._queue_update_decider = (
            queue_update_decider if queue_update_decider is not None else RetryQueueUpdateDecider()
        )
        self._queue_removal_executor = (
            queue_removal_executor if queue_removal_executor is not None else RetryQueueRemovalExecutor()
        )
        self._queue_cleanup_decider = (
            queue_cleanup_decider if queue_cleanup_decider is not None else RetryQueueCleanupDecider()
        )
        self._queue_cleanup_executor = (
            queue_cleanup_executor if queue_cleanup_executor is not None else RetryQueueCleanupExecutor()
        )

    @classmethod
    def from_config(
        cls,
        retry_config: RetryConfig,
        retry_policy: RetryPolicy,
        workflow_engine_manager: "WorkflowEngineManager | NullWorkflowEngineManager",
        workflow_monitor_manager: "WorkflowMonitorManager | NullWorkflowMonitorManager",
        retry_queue_manager: "RetryQueueManager | NullRetryQueueManager | None" = None,
        event_consumer: RetryEventConsumer | None = None,
        event_dispatcher: RetryEventDispatcher | None = None,
        execution_selector: RetryExecutionSelector | None = None,
        execution_coordinator: RetryExecutionCoordinator | None = None,
        queue_update_decider: RetryQueueUpdateDecider | None = None,
        queue_removal_executor: RetryQueueRemovalExecutor | None = None,
        queue_cleanup_decider: RetryQueueCleanupDecider | None = None,
        queue_cleanup_executor: RetryQueueCleanupExecutor | None = None,
    ) -> "RetryManager | NullRetryManager":
        """
        呼び出し元が構築済みの WorkflowEngineManager / WorkflowMonitorManager を
        Dependency Injection で受け取る（Configから再構築しない）。

        RETRY_ENGINE_ENABLED が false、または workflow_engine_manager が
        NullWorkflowEngineManager（下位ゲートが閉じている）の場合は NullRetryManager を返す。

        retry_queue_manager は省略可能（デフォルト None）。省略した場合は
        RetryManager.__init__ 内で NullRetryQueueManager() にフォールバックするため、
        本引数を渡さない既存の呼び出しはすべて本Release前と同じ挙動になる。

        event_consumer も省略可能（デフォルト None）。省略した場合は
        RetryManager.__init__ 内で RetryEventConsumer() にフォールバックするため、
        本引数を渡さない既存の呼び出しはすべて本Release前と同じ挙動になる（v3.8.0）。

        event_dispatcher も省略可能（デフォルト None）。省略した場合は
        RetryManager.__init__ 内で RetryEventDispatcher() にフォールバックするため、
        本引数を渡さない既存の呼び出しはすべて本Release前と同じ挙動になる（v3.9.0）。

        execution_selector / execution_coordinator も省略可能（デフォルト None）。
        省略した場合は RetryManager.__init__ 内でそれぞれ RetryExecutionSelector() /
        RetryExecutionCoordinator() にフォールバックするため、本引数を渡さない既存の
        呼び出しはすべて本Release前と同じ挙動になる（v4.0.0）。

        queue_update_decider も省略可能（デフォルト None）。省略した場合は
        RetryManager.__init__ 内で RetryQueueUpdateDecider() にフォールバックするため、
        本引数を渡さない既存の呼び出しはすべて本Release前と同じ挙動になる（v4.1.0）。

        queue_removal_executor も省略可能（デフォルト None）。省略した場合は
        RetryManager.__init__ 内で RetryQueueRemovalExecutor() にフォールバックするため、
        本引数を渡さない既存の呼び出しはすべて本Release前と同じ挙動になる（v4.2.0）。

        queue_cleanup_decider / queue_cleanup_executor も省略可能（デフォルト None）。
        省略した場合は RetryManager.__init__ 内でそれぞれ RetryQueueCleanupDecider() /
        RetryQueueCleanupExecutor() にフォールバックするため、本引数を渡さない既存の
        呼び出しはすべて本Release前と同じ挙動になる（v4.3.0）。
        """
        if not retry_config.is_ready():
            return NullRetryManager()
        if isinstance(workflow_engine_manager, NullWorkflowEngineManager):
            return NullRetryManager()

        executor = RetryExecutor(workflow_engine_manager=workflow_engine_manager)
        return cls(
            policy=retry_policy,
            executor=executor,
            monitor=workflow_monitor_manager,
            queue=retry_queue_manager,
            event_consumer=event_consumer,
            event_dispatcher=event_dispatcher,
            execution_selector=execution_selector,
            execution_coordinator=execution_coordinator,
            queue_update_decider=queue_update_decider,
            queue_removal_executor=queue_removal_executor,
            queue_cleanup_decider=queue_cleanup_decider,
            queue_cleanup_executor=queue_cleanup_executor,
        )

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

    def enqueue_retry(
        self,
        run_id: str,
        workflow_name: str,
        retry_attempt: int = 1,
        priority: int | None = None,
    ) -> RetryQueueResult:
        """
        再実行対象を Retry Queue へ登録する。RetryQueueManager.enqueue() への委譲のみを
        行い、判定・加工は一切行わない（RetryPolicy／Workflow Monitorへの問い合わせも
        行わない。Queue登録可否の判断はretry_queue側の責務のまま）。
        """
        return self._queue.enqueue(
            run_id=run_id,
            workflow_name=workflow_name,
            retry_attempt=retry_attempt,
            priority=priority,
        )

    def dequeue_retry(self) -> RetryQueueResult:
        """
        Retry Queue から再実行対象を1件取り出す。RetryQueueManager.dequeue() への
        委譲のみを行う。取り出した項目に対して retry() を呼ぶかどうかは呼び出し元の
        判断に委ねられ、RetryManager自身は一切自動実行しない。
        """
        return self._queue.dequeue()

    def recognize_retry_events(self, events: list[SchedulerEvent]) -> list[RetryCandidateEvent]:
        """
        SchedulerEventのリストから、Retry候補由来のものだけを認識する。
        RetryEventConsumer.recognize_all() への薄い委譲のみを行う。

        retry()（Retry実行）・enqueue_retry() / dequeue_retry()（Queue操作）とは
        呼び出しグラフ上で完全に独立している。認識結果（RetryCandidateEvent）を
        使って自動的に何かを実行する処理はここにはない（自動実行はしない）。
        """
        return self._event_consumer.recognize_all(events)

    def dispatch_retry_events(self, events: list[SchedulerEvent]) -> list[RetryDispatchEvent]:
        """
        SchedulerEventのリストから、Retry候補由来のものを認識したうえで
        Dispatch対象として整理する。recognize_retry_events()（v3.8.0）への委譲、
        続けて RetryEventDispatcher.dispatch() への薄い委譲、の2段階のみで完結する。

        retry()（Retry実行）・enqueue_retry() / dequeue_retry()（Queue操作）とは
        呼び出しグラフ上で完全に独立している。Dispatch結果（RetryDispatchEvent）を
        使って自動的に何かを実行する処理はここにはない（自動実行はしない）。
        """
        candidate_events = self.recognize_retry_events(events)
        return self._event_dispatcher.dispatch(candidate_events)

    def execute_dispatchable_retries(
        self, events: list[SchedulerEvent], dry_run: bool = False
    ) -> list[RetryExecutionResult]:
        """
        SchedulerEventのリストから、Retry候補由来のものを認識・Dispatch対象として整理した
        うえで、dispatchable=Trueのものだけを選別し、それぞれについてretry()を呼び出す。

        3段階の委譲のみで完結する：
            1. self.dispatch_retry_events(events)（v3.9.0、無変更）
            2. self._execution_selector.select(dispatch_events)（判定を1箇所に集約）
            3. self._execution_coordinator.execute(selected, retry_fn=self.retry, dry_run=dry_run)
               （実行と結果集約）

        Retry Queueの更新（enqueue_retry() / dequeue_retry()）・
        RetryQueueManager.dequeue() / remove()とは呼び出しグラフ上で完全に独立している。
        """
        dispatch_events = self.dispatch_retry_events(events)
        selected = self._execution_selector.select(dispatch_events)
        return self._execution_coordinator.execute(selected, retry_fn=self.retry, dry_run=dry_run)

    def decide_retry_queue_updates(
        self, events: list[SchedulerEvent], dry_run: bool = False
    ) -> list[RetryQueueUpdateDecision]:
        """
        SchedulerEventのリストから、dispatchable=Trueの候補についてretry()を実行し
        （execute_dispatchable_retries()、v4.0.0、無変更）、各RetryExecutionResultに
        ついて対応するRetry Queue項目の更新先状態（COMPLETED / FAILED / 更新なし）を
        判定する。

        2段階の委譲のみで完結する：
            1. self.execute_dispatchable_retries(events, dry_run=dry_run)（v4.0.0、無変更）
            2. self._queue_update_decider.decide_all(execution_results)（新規、判定）

        判定結果を使ってRetryQueueManager.remove()を呼び出す処理、判定結果をQueueへ
        実際に反映する処理は本Releaseには一切存在しない（Foundation First）。
        """
        execution_results = self.execute_dispatchable_retries(events, dry_run=dry_run)
        return self._queue_update_decider.decide_all(execution_results)

    def apply_retry_queue_removals(
        self, events: list[SchedulerEvent], dry_run: bool = False
    ) -> list[RetryQueueRemovalResult]:
        """
        SchedulerEventのリストから、各RetryQueueUpdateDecisionについてoutcomeが
        COMPLETE / FAILの項目のみRetryQueueManager.remove()を呼び出し、Queueから
        該当項目を除去する。

        2段階の委譲のみで完結する：
            1. self.decide_retry_queue_updates(events, dry_run=dry_run)（v4.1.0、無変更）
            2. self._queue_removal_executor.apply_all(decisions, remove_fn=self._queue.remove)
               （新規、除去）

        outcomeがNOOP（SKIPPED / NOT_FOUND / DISABLED由来）の項目はremove_fnを
        一切呼び出さない（Foundation First。SKIPPEDのQueue滞留対応は本Releaseの
        対象外）。
        """
        decisions = self.decide_retry_queue_updates(events, dry_run=dry_run)
        return self._queue_removal_executor.apply_all(decisions, remove_fn=self._queue.remove)

    def decide_retry_queue_cleanup(
        self, events: list[SchedulerEvent], dry_run: bool = False
    ) -> list[RetryQueueCleanupDecision]:
        """
        SchedulerEventのリストから、各RetryQueueUpdateDecisionについてSKIPPED由来の
        NOOPのみをCLEANUP対象と判定する。

        2段階の委譲のみで完結する：
            1. self.decide_retry_queue_updates(events, dry_run=dry_run)（v4.1.0、無変更）
            2. self._queue_cleanup_decider.decide_all(decisions)（新規、判定）

        判定結果を使ってRetryQueueManager.remove()を呼び出す処理、判定結果をQueueへ
        実際に反映する処理は本メソッドには一切存在しない（Foundation First）。
        """
        decisions = self.decide_retry_queue_updates(events, dry_run=dry_run)
        return self._queue_cleanup_decider.decide_all(decisions)

    def apply_retry_queue_cleanup(
        self, events: list[SchedulerEvent], dry_run: bool = False
    ) -> list[RetryQueueCleanupResult]:
        """
        SchedulerEventのリストから、各RetryQueueCleanupDecisionについてoutcomeが
        CLEANUP（SKIPPED由来のNOOP）の項目のみRetryQueueManager.remove()を呼び出し、
        Queueから該当項目を除去する。

        2段階の委譲のみで完結する：
            1. self.decide_retry_queue_cleanup(events, dry_run=dry_run)（新規、判定）
            2. self._queue_cleanup_executor.apply_all(decisions, remove_fn=self._queue.remove)
               （新規、除去。apply_retry_queue_removals()と同じself._queue.removeを渡す）

        outcomeがKEEP（COMPLETE / FAIL / SKIPPED以外由来のNOOP）の項目はremove_fnを
        一切呼び出さない。
        """
        decisions = self.decide_retry_queue_cleanup(events, dry_run=dry_run)
        return self._queue_cleanup_executor.apply_all(decisions, remove_fn=self._queue.remove)

    def _skip_reason(self, monitor_status: WorkflowMonitorStatus, attempt: int) -> str:
        if monitor_status not in self._policy.target_statuses:
            return (
                f"monitor_status={monitor_status.value} is not a retry target "
                f"({sorted(s.value for s in self._policy.target_statuses)})."
            )
        return f"attempt {attempt} has reached max_attempts={self._policy.max_attempts}."


class NullRetryManager:
    """RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている場合のダミー実装。"""

    _DISABLED_REASON = (
        "Retry Engine is disabled (RETRY_ENGINE_ENABLED=false, "
        "or AI_AGENT_ENABLED/WORKFLOW_ENGINE_ENABLED is not ready)."
    )

    def retry(self, run_id: str, attempt: int = 1, dry_run: bool = False) -> RetryResult:
        return RetryResult(
            original_run_id=run_id, outcome=RetryOutcome.DISABLED, attempt=attempt,
            monitor_status=None,
            reason=self._DISABLED_REASON,
            workflow_engine_result=None,
        )

    def enqueue_retry(
        self,
        run_id: str,
        workflow_name: str,
        retry_attempt: int = 1,
        priority: int | None = None,
    ) -> RetryQueueResult:
        """
        RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている場合は、
        Retry Queueが有効かどうかに関わらずRetry Engine自体が無効であるため、
        Queueへの参照を一切保持せずDISABLEDを返す（retry_queue側は一切呼び出さない）。
        """
        return RetryQueueResult(outcome=RetryQueueOutcome.DISABLED, item=None, reason=self._DISABLED_REASON)

    def dequeue_retry(self) -> RetryQueueResult:
        """enqueue_retry()と同じ理由でDISABLEDを返す（retry_queue側は一切呼び出さない）。"""
        return RetryQueueResult(outcome=RetryQueueOutcome.DISABLED, item=None, reason=self._DISABLED_REASON)

    def recognize_retry_events(self, events: list[SchedulerEvent]) -> list[RetryCandidateEvent]:
        """
        RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている場合でも、
        認識処理自体はQueue操作・実行を一切伴わない副作用のない読み取りであるため、
        DISABLEDという特別な結果型は用いず、常に空リストを返す
        （「受け取れるが何もしない」）。RetryEventConsumerへの参照は保持しない。
        """
        return []

    def dispatch_retry_events(self, events: list[SchedulerEvent]) -> list[RetryDispatchEvent]:
        """
        RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている場合でも、
        Dispatch整理自体はQueue操作・実行を一切伴わない副作用のない読み取りであるため、
        recognize_retry_events()と同じ理由で常に空リストを返す
        （「受け取れるが何もしない」）。RetryEventDispatcherへの参照は保持しない。
        """
        return []

    def execute_dispatchable_retries(
        self, events: list[SchedulerEvent], dry_run: bool = False
    ) -> list[RetryExecutionResult]:
        """
        RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている場合、
        実行自体を一切行わず常に空リストを返す（「受け取れるが何もしない」）。
        RetryExecutionSelector / RetryExecutionCoordinatorへの参照は保持しない。
        """
        return []

    def decide_retry_queue_updates(
        self, events: list[SchedulerEvent], dry_run: bool = False
    ) -> list[RetryQueueUpdateDecision]:
        """
        RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている場合、
        判定自体を一切行わず常に空リストを返す（「受け取れるが何もしない」）。
        RetryQueueUpdateDeciderへの参照は保持しない。
        """
        return []

    def apply_retry_queue_removals(
        self, events: list[SchedulerEvent], dry_run: bool = False
    ) -> list[RetryQueueRemovalResult]:
        """
        RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている場合、
        除去処理自体を一切行わず常に空リストを返す（「受け取れるが何もしない」）。
        RetryQueueRemovalExecutorへの参照は保持しない。
        """
        return []

    def decide_retry_queue_cleanup(
        self, events: list[SchedulerEvent], dry_run: bool = False
    ) -> list[RetryQueueCleanupDecision]:
        """
        RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている場合、
        判定自体を一切行わず常に空リストを返す（「受け取れるが何もしない」）。
        RetryQueueCleanupDeciderへの参照は保持しない。
        """
        return []

    def apply_retry_queue_cleanup(
        self, events: list[SchedulerEvent], dry_run: bool = False
    ) -> list[RetryQueueCleanupResult]:
        """
        RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている場合、
        除去処理自体を一切行わず常に空リストを返す（「受け取れるが何もしない」）。
        RetryQueueCleanupExecutorへの参照は保持しない。
        """
        return []
