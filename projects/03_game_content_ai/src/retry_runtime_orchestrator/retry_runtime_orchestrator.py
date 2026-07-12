"""
Retry Runtime Orchestrator（v5.2.0、v5.3.0でrun_once()を追加）

RetryRuntimeOrchestrator: Retry Runtimeの実行順序を管理する場所。
                           RetryCompositionRootが組み立てた各コンポーネントへの
                           参照を保持し、run_once()で1サイクル分の実行順序を
                           決定する。ループ・デーモン化は行わない。

設計方針:
    - 本クラスの責務は「参照を保持すること」と「1サイクル分の実行順序を決めること」
      に限定する。loop() / daemon()等はいずれも追加しない（Non-Goal。
      docs/design/retry_runtime_run_once_foundation.md 1.3節）。
    - Composition（組み立て）は RetryCompositionRoot の責務であり続ける。
      本クラスは新規インスタンスを一切生成せず、RetryCompositionRoot が
      生成した既存インスタンスをそのまま受け取る（docs/design/
      retry_runtime_orchestrator_foundation.md 2章）。
    - trigger / scheduler / manager / queue / history / policy の6つを保持する。
      queue / history は trigger・manager が内部で参照するものと同一の
      インスタンスであり、本クラスが新たに参照を分岐させることはない。
    - guard（RetryEnqueueTrigger専属の内部コンポーネント）・monitor（将来依存が
      未確定）は保持しない。

    - （v5.3.0）run_once()：Retry Runtimeを1サイクルだけ実行する。
      trigger.enqueue_pending_failures() → scheduler.run_due(jobs=[]) →
      manager.execute_dispatchable_retries()（1回だけ） → 既存の公開
      Decider/Executor群（retry_engineが既に公開しているStateless・
      無引数コンストラクタのクラス）への結果配布、という順序で実行する
      （docs/design/retry_runtime_run_once_foundation.md 2章）。
    - （v5.3.0）execute_dispatchable_retries()は本メソッド内で必ず1回だけ
      呼び出す。その戻り値（execution_results）を保持したまま、Queue更新・
      Cleanup・History記録の各Decider/Executorへ配布することで、v5.2.0で
      発見された「同一run_idに対するretry()の多重実行リスク（発見B）」を
      解消する。RetryManagerへの変更（run_cycle()等の追加）は行わない
      （retry_manager.pyは本Releaseでも無改修）。
    - （v5.3.0）dry_run引数は追加しない。RetryExecutor.execute()はdry_runの
      値に関わらず常にoutcome=RETRIEDを返すため、dry_run=Trueを
      execute_dispatchable_retries()へそのまま渡しても、後続のQueue除去・
      History記録という実際の副作用は防げない（安全なdry_runにならない）。
      これは既知の制約として設計書に記録し、本Releaseでは対応しない
      （同設計書4章 Known Issue）。
    - （v5.6.0）run_once()にdry_run: bool = False引数を追加した。RetryOutcome.DRY_RUN
      （retry_engine、v5.6.0新設）により、RetryExecutor.execute()がdry_run=Trueの場合に
      outcome=DRY_RUNを返すようになったため、v5.3.0時点のKnown Issueが解消し、
      dry_run引数をmanager.execute_dispatchable_retries(events, dry_run=dry_run)へ
      伝播させることが安全になった（docs/design/retry_runtime_safe_dry_run_foundation.md
      参照）。
    - （v5.6.0）dry_runはtrigger.enqueue_pending_failures()へは伝播しない
      （RetryEnqueueTriggerはdry_run引数を持たない）。そのためdry_run=Trueで
      run_once()を呼んでも、WorkflowMonitor上のFAILED/TIMEOUTをRetry Queueへ
      enqueueする処理自体は通常どおり実行される（Queueへの追加はin-memoryで可逆的・
      外部作用を伴わないためリスクレベルが異なると判断し、本Releaseでは意図的に
      対象外とした。Known Issueとして記録し、次Release候補「Retry Enqueue Trigger
      Dry Run Foundation」（docs/ROADMAP.md）へ申し送る）。
    - （v5.6.0）CLI（scripts/run_retry_runtime.py）への--dry-run配線は本Releaseの
      対象外（Foundation First。次Release候補「Retry Runtime Safe Dry Run Wiring」
      （docs/ROADMAP.md）へ申し送る）。
    - （v5.8.0）trigger.enqueue_pending_failures()へdry_runを伝播するよう変更した
      （RetryEnqueueTrigger側がdry_run: bool = Falseを呼び出し引数として持つように
      なったため。docs/design/retry_enqueue_trigger_dry_run_foundation.md）。
      これによりdry_run=True時、Retry Queueへの新規enqueueが抑止されるように
      なり、v5.6.0時点のKnown Issue（KI-23）が解消した。run_once()自体の
      シグネチャ・実行順序・他の呼び出し（scheduler.run_due() /
      execute_dispatchable_retries()以降）はいずれも無変更。
"""
from __future__ import annotations

from retry_composition import RetryCompositionRoot
from retry_engine import (
    NullRetryManager,
    RetryHistoryRecordExecutor,
    RetryManager,
    RetryPolicy,
    RetryQueueCleanupDecider,
    RetryQueueCleanupExecutor,
    RetryQueueRemovalExecutor,
    RetryQueueTerminalCleanupDecider,
    RetryQueueTerminalCleanupExecutor,
    RetryQueueUpdateDecider,
)
from retry_enqueue_trigger import RetryEnqueueTrigger
from retry_history import RetryHistoryManager
from retry_queue import NullRetryQueueManager, RetryQueueManager
from scheduler import SchedulerEngine

from .retry_runtime_cycle_result import RetryRuntimeCycleResult


class RetryRuntimeOrchestrator:
    """
    Retry Runtimeの実行順序を管理する場所。

    trigger / scheduler / manager / queue / history / policy への参照を
    Constructor Injectionで保持し、run_once()で1サイクル分の実行順序を
    決定する。ループ・デーモン化はいずれも行わない。
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

    def run_once(self, dry_run: bool = False) -> RetryRuntimeCycleResult:
        """
        Retry Runtimeを1サイクルだけ実行する。

        実行順序（変更しないこと）：
            1. self.trigger.enqueue_pending_failures(max_attempts=self.policy.max_attempts, dry_run=dry_run)
               （FAILED/TIMEOUTのrun_idをRetry Queueへ登録する。dry_run=Trueの場合、
               Guard判定・Queue重複確認までは通常どおり実行するが、実際のenqueue
               （queue.enqueue()）は抑止される。v5.8.0でdry_runの伝播に対応した）
            2. self.scheduler.run_due(jobs=[])
               （jobs=[]により、Job判定は行わずRetry候補由来のSchedulerEventのみ取得する）
            3. self.manager.execute_dispatchable_retries(events, dry_run=dry_run)
               （本メソッド内でちょうど1回だけ呼び出す。dispatchable=Trueの候補について
               実際にretry()を呼び出し、結果をexecution_resultsとして保持する。
               dry_run=Trueの場合、RetryExecutor.execute()がoutcome=RetryOutcome.DRY_RUN
               を返すため、以下4.の各Decider/Executorはいずれも無改修のまま自動的に
               Queue除去・履歴記録を行わない（v5.6.0）
            4. execution_resultsを、retry_engineが公開する既存のStateless・無引数
               コンストラクタのDecider/Executor群へ配布する：
                 - RetryQueueUpdateDecider().decide_all(execution_results)
                 - RetryQueueRemovalExecutor().apply_all(decisions, remove_fn=self.queue.remove)
                 - RetryQueueCleanupDecider().decide_all(decisions)
                   → RetryQueueCleanupExecutor().apply_all(..., remove_fn=self.queue.remove)
                 - RetryQueueTerminalCleanupDecider().decide_all(decisions)
                   → RetryQueueTerminalCleanupExecutor().apply_all(..., remove_fn=self.queue.remove)
                 - RetryHistoryRecordExecutor().record_all(execution_results, record_fn=self.history.record)

        execute_dispatchable_retries()を2回以上呼び出す変更は行わないこと
        （同一run_idに対するretry()の多重実行を招くため）。

        dry_run=Trueの場合、trigger.enqueue_pending_failures()（Retry Queueへの
        新規登録）もdry_runを受け取り、実際のenqueueを抑止する（v5.8.0でKI-23を
        解消。Monitor走査・History参照・Guard判定・Queue重複確認は通常どおり
        実行される）。
        """
        trigger_result = self.trigger.enqueue_pending_failures(
            max_attempts=self.policy.max_attempts, dry_run=dry_run,
        )

        events = self.scheduler.run_due(jobs=[])

        execution_results = self.manager.execute_dispatchable_retries(events, dry_run=dry_run)

        decisions = RetryQueueUpdateDecider().decide_all(execution_results)
        removal_results = RetryQueueRemovalExecutor().apply_all(decisions, remove_fn=self.queue.remove)
        cleanup_results = RetryQueueCleanupExecutor().apply_all(
            RetryQueueCleanupDecider().decide_all(decisions), remove_fn=self.queue.remove
        )
        terminal_cleanup_results = RetryQueueTerminalCleanupExecutor().apply_all(
            RetryQueueTerminalCleanupDecider().decide_all(decisions), remove_fn=self.queue.remove
        )
        history_results = RetryHistoryRecordExecutor().record_all(
            execution_results, record_fn=self.history.record
        )

        return RetryRuntimeCycleResult(
            trigger_result=trigger_result,
            scheduler_events=events,
            execution_results=execution_results,
            removal_results=removal_results,
            cleanup_results=cleanup_results,
            terminal_cleanup_results=terminal_cleanup_results,
            history_results=history_results,
        )
