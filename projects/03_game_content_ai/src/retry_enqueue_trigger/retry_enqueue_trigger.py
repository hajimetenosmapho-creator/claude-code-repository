"""
Retry Enqueue Trigger（v4.6.0、v4.8.0・v4.9.0・v5.0.0で拡張）

RetryEnqueueTrigger:     WorkflowMonitorManagerが判定したFAILED/TIMEOUTを検知し、
                         RetryEnqueueGuardの判定を経て、まだRetry Queueに
                         存在しないものだけをenqueueするAdapter。
NullRetryEnqueueTrigger: RetryEnqueueTriggerのダミー実装（Null Object）。

設計方針:
    - RetryEnqueueTriggerはWorkflowMonitorManager / RetryQueueManagerへの参照を
      Constructor Injectionで保持し、監視・enqueueへの薄い委譲のみを行う
      （docs/design/retry_enqueue_trigger_foundation.md 4章）。
    - Feature Gate・Configクラス・from_config()/from_env()は持たない。
      有効/無効は呼び出し元がRetryEnqueueTrigger（実体）とNullRetryEnqueueTrigger
      のどちらを構築するかで決まる（RetrySchedulerSource、v3.3.0と同じNull Object
      Pattern。同設計書2章）。
    - retry_engineは経由せず、workflow_monitor / retry_queue / retry_history に
      直接依存する（同設計書2章 Design Policy #2、docs/design/retry_enqueue_guard.md
      2章）。RetryPolicy（retry_engine）への依存はv5.0.0でも追加しない。
    - RetryQueueManager.exists()による「Queue内に既に存在するか」の確認に加え、
      v4.8.0でRetryEnqueueGuardによる判定を追加した。これにより、Queueから
      除去された後もMonitor上でFAILED/TIMEOUTのまま観測され続けるrun_idの
      無限再投入リスク（v4.6.0 Known Issue）を解消した
      （docs/design/retry_enqueue_guard.md 1章・11章）。
    - history省略時はNullRetryHistoryManager()にフォールバックし、next_attemptは
      常に1になる（v4.6.0時点とまったく同じ挙動。同設計書2章 Design Policy #3）。
    - enqueue_pending_failures()は`self._history.get()`を1回だけ呼び出し、その
      戻り値（RetryHistoryRecord | None）から「次のattempt番号」を算出する
      （v4.9.0）。`next_attempt`は`queue.enqueue()`の`retry_attempt`へ渡すのと
      同時に、Guard判定（`self._guard.decide(run_id, next_attempt, max_attempts)`）
      にも使う唯一の値として1箇所で算出する。
    - （v5.0.0）RetryEnqueueGuardの判定基準を「履歴の有無」の二値から
      「next_attempt > max_attempts」の比較へ精緻化した
      （docs/design/retry_enqueue_guard_refinement_foundation.md）。
      max_attemptsは`enqueue_pending_failures(limit=None, max_attempts=1)`の
      呼び出し引数として受け取り、`__init__`ではインスタンス状態として保持しない
      （RetryEnqueueTrigger.__init__は本Releaseでも無変更。Architecture Review
      Final、Stateless・Single Responsibility優先の判断）。省略時のデフォルト値
      `1`はv4.8.0/v4.9.0時点と完全に同一の挙動（履歴が1件でもあれば以降ブロック）
      を再現する安全側の値であり、RetryPolicy.max_attempts（デフォルト3）とは
      意図的に独立した、retry_engine非依存を保つための構造的セーフガードである
      （同設計書 Future Architecture Consideration）。
    - workflow_monitor / retry_queue / retry_history / retry_engineはいずれも
      本Releaseでも無改修。
    - （v5.8.0）enqueue_pending_failures()へ`dry_run: bool = False`を呼び出し
      引数として追加した（max_attemptsと同じ「呼び出しの都度渡す」スタイル。
      __init__は本Releaseでも無変更）。Monitor走査・History参照・next_attempt
      算出・Guard判定・Queue重複確認はdry_runの値に関わらず常に実行する。
      Guardを通過しQueue重複も存在しない候補について、dry_run=Trueの場合のみ
      `queue.enqueue()`を呼び出さずその候補の処理を終了する（enqueued/failed
      いずれにも加算しない）。RetryEnqueueTriggerResultのフィールド構成は
      本Releaseでも無変更（KI-23、docs/design/retry_enqueue_trigger_dry_run_
      foundation.md参照）。
"""
from __future__ import annotations

from dataclasses import dataclass

from retry_history import NullRetryHistoryManager, RetryHistoryManager
from retry_queue import RetryQueueManager, RetryQueueOutcome
from workflow_monitor import WorkflowMonitorManager, WorkflowMonitorStatus

from .retry_enqueue_guard import RetryEnqueueGuard, RetryEnqueueGuardOutcome

_RETRY_TARGET_STATUSES = frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT})


@dataclass(frozen=True)
class RetryEnqueueTriggerResult:
    """enqueue_pending_failures() 1回分の集計結果。"""

    scanned: int
    enqueued: int
    skipped_existing: int
    skipped_status: int
    failed: int
    skipped_history: int = 0


class RetryEnqueueTrigger:
    """
    WorkflowMonitorManagerが判定したFAILED/TIMEOUTのWorkflowを検知し、
    RetryEnqueueGuardの判定を経て、まだRetry Queueに存在しないものだけを
    enqueueするAdapter（実装クラス）。

    WorkflowMonitorManager / RetryQueueManager / RetryHistoryManager /
    RetryEnqueueGuardへの参照をConstructor Injectionで保持し、検知・Guard判定・
    重複確認・enqueueへの薄い委譲のみを行う。
    """

    def __init__(
        self,
        monitor: WorkflowMonitorManager,
        queue: RetryQueueManager,
        history: "RetryHistoryManager | NullRetryHistoryManager | None" = None,
        guard: RetryEnqueueGuard | None = None,
    ):
        self._monitor = monitor
        self._queue = queue
        self._history = history if history is not None else NullRetryHistoryManager()
        self._guard = guard if guard is not None else RetryEnqueueGuard()

    def enqueue_pending_failures(
        self, limit: int | None = None, max_attempts: int = 1, dry_run: bool = False,
    ) -> RetryEnqueueTriggerResult:
        """
        WorkflowMonitorManager.list_status(limit) を走査し、monitor_statusが
        FAILED/TIMEOUTのレコードのうち、RetryEnqueueGuardがALLOWと判定し、
        まだQueueに存在しないものだけをRetryQueueManager.enqueue()する。

        max_attempts / dry_run はいずれも呼び出しの都度渡されるプリミティブ値
        であり、インスタンス状態としては保持しない（省略時はv4.8.0/v4.9.0時点と
        同一の挙動になる）。

        dry_run=Trueの場合、Monitor走査・History参照・Guard判定・Queue重複確認は
        通常どおり実行するが、Guardを通過しQueue重複も存在しない候補について
        RetryQueueManager.enqueue()を呼び出さない（enqueued/failedいずれにも
        加算しない）。RetryEnqueueTriggerResultのフィールド構成・意味は無変更
        （v5.8.0）。
        """
        records = self._monitor.list_status(limit=limit)
        scanned = len(records)
        enqueued = 0
        skipped_existing = 0
        skipped_status = 0
        skipped_history = 0
        failed = 0

        for record in records:
            if record.monitor_status not in _RETRY_TARGET_STATUSES:
                skipped_status += 1
                continue

            history_record = self._history.get(record.run_id)
            next_attempt = history_record.attempt_count + 1 if history_record is not None else 1
            guard_decision = self._guard.decide(
                record.run_id, next_attempt=next_attempt, max_attempts=max_attempts,
            )
            if guard_decision.outcome == RetryEnqueueGuardOutcome.BLOCK:
                skipped_history += 1
                continue

            if self._queue.exists(record.run_id):
                skipped_existing += 1
                continue

            if dry_run:
                continue

            result = self._queue.enqueue(
                run_id=record.run_id, workflow_name=record.workflow_name, retry_attempt=next_attempt,
            )
            if result.outcome == RetryQueueOutcome.ENQUEUED:
                enqueued += 1
            else:
                failed += 1

        return RetryEnqueueTriggerResult(
            scanned=scanned,
            enqueued=enqueued,
            skipped_existing=skipped_existing,
            skipped_status=skipped_status,
            failed=failed,
            skipped_history=skipped_history,
        )


class NullRetryEnqueueTrigger:
    """
    RetryEnqueueTrigger のダミー実装（Null Object）。

    workflow_monitor / retry_queue / retry_history への参照を一切保持せず、常に
    「検知0件・enqueue 0件」の結果を返す。
    """

    def enqueue_pending_failures(self, limit: int | None = None) -> RetryEnqueueTriggerResult:
        return RetryEnqueueTriggerResult(
            scanned=0, enqueued=0, skipped_existing=0, skipped_status=0, failed=0,
            skipped_history=0,
        )
