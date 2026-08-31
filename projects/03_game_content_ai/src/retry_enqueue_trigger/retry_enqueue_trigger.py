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
    - （Release 6.31）lineage（RetryLineageManager）を省略可能な追加依存として
      Constructor Injectionできるようにした（docs/design/
      retry_lineage_eligibility_durable_attempt_state.md 10.3.3・19章）。
      membership-first判定：候補run_idについて、まず
      `lineage.find_by_member_run_id(candidate_run_id)`を試み、既存lineageの
      membershipに既に記録されている（＝mark_execution_started()が過去に成功した
      attemptのrun_idである）場合、この候補run_idを独立候補として扱わず
      enqueue対象から除外する（skipped_lineage_memberとして計上）。
      lineage省略時（None）は既存の全呼び出し元に対して完全にZero-Diff。
    - （Release 6.31、correlation-fallback実装）history_store
      （execution_history.ExecutionHistoryStore）を省略可能な追加依存として
      Constructor Injectionできるようにした。membership-firstで見つからなかった
      候補についてのみ（hook失敗由来のorphan候補、10.2章）、
      `history_store.get(candidate_run_id).correlation_metadata["retry_lineage"]`
      を読み取り、`lineage.verify_orphan_correlation()`（root_run_id実在・
      intended_attempt_no厳密一致・correlation_id完全一致の3条件、10.3.3章(b)）で
      検証する。3条件すべてを満たした場合のみ独立候補から除外する
      （skipped_lineage_correlationとして計上）。malformed（型不正・キー欠落）・
      forged（存在しないroot_run_idを騙る）・stale（古いattempt_noを騙る）は
      いずれもfail-closed（`_extract_retry_lineage_correlation()`・
      `verify_orphan_correlation()`双方が、条件を満たさない限り通常の独立候補
      処理へフォールバックさせる、10.3.4章）ため、無関係なFAILED候補を誤って
      除外することはない。
      `WorkflowMonitorRecord`（workflow_monitor、本Releaseの承認済み変更対象外、
      22章「無改修（明示）」）は`correlation_metadata`を保持していないため、
      本機能はworkflow_monitorを経由せず、execution_historyへの新規の直接依存
      （`ExecutionHistoryStore`のみ、`ExecutionHistoryManager`等の書き込み系APIは
      importしない）を追加することで実現した。history_store省略時（None）は
      既存の全呼び出し元に対して完全にZero-Diff。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from retry_history import NullRetryHistoryManager, RetryHistoryManager
from retry_queue import RetryQueueManager, RetryQueueOutcome
from workflow_monitor import WorkflowMonitorManager, WorkflowMonitorStatus

from .retry_enqueue_guard import RetryEnqueueGuard, RetryEnqueueGuardOutcome

if TYPE_CHECKING:
    from execution_history import ExecutionHistoryStore
    from retry_lineage import RetryLineageManager

_RETRY_TARGET_STATUSES = frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT})


def _extract_retry_lineage_correlation(record) -> "tuple[str, str, str] | None":
    """WorkflowExecutionRecord.correlation_metadataから"retry_lineage"namespaceを
    fail-closedに抽出する（10.3.4章）。期待する型・キーが揃っていない場合は
    Noneを返し、呼び出し元は相関情報が存在しない場合と同一の経路（通常の独立候補
    処理）へフォールバックする。"""
    if record is None:
        return None
    metadata = record.correlation_metadata
    if not isinstance(metadata, dict):
        return None
    namespace = metadata.get("retry_lineage")
    if not isinstance(namespace, dict):
        return None
    root_run_id = namespace.get("root_run_id")
    intended_attempt_no = namespace.get("intended_attempt_no")
    correlation_id = namespace.get("correlation_id")
    if not isinstance(root_run_id, str) or not root_run_id:
        return None
    if not isinstance(intended_attempt_no, str) or not intended_attempt_no:
        return None
    if not isinstance(correlation_id, str) or not correlation_id:
        return None
    return root_run_id, intended_attempt_no, correlation_id


@dataclass(frozen=True)
class RetryEnqueueTriggerResult:
    """enqueue_pending_failures() 1回分の集計結果。"""

    scanned: int
    enqueued: int
    skipped_existing: int
    skipped_status: int
    failed: int
    skipped_history: int = 0
    skipped_lineage_member: int = 0
    skipped_lineage_correlation: int = 0


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
        lineage: "RetryLineageManager | None" = None,
        history_store: "ExecutionHistoryStore | None" = None,
    ):
        self._monitor = monitor
        self._queue = queue
        self._history = history if history is not None else NullRetryHistoryManager()
        self._guard = guard if guard is not None else RetryEnqueueGuard()
        self._lineage = lineage
        self._history_store = history_store

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
        skipped_lineage_member = 0
        skipped_lineage_correlation = 0
        failed = 0

        for record in records:
            if record.monitor_status not in _RETRY_TARGET_STATUSES:
                skipped_status += 1
                continue

            if self._lineage is not None:
                if self._lineage.find_by_member_run_id(record.run_id) is not None:
                    # membership-first（10.3.3章(1)）：既存lineageのmembershipに
                    # 既に記録されているrun_id（例：open_next_attempt()後のattemptが
                    # それ自体FAILED/TIMEOUTとしてMonitor上に観測された場合）は、
                    # 独立候補として扱わない。retry_lineageの通常のreconcile経路が
                    # 既にこのlineageを処理する。
                    skipped_lineage_member += 1
                    continue

                if self._history_store is not None:
                    # correlation-fallback（10.3.3章(2)）：membership-firstで
                    # 見つからなかった候補（＝mark_execution_started()が一度も
                    # 成功していない、hook ack失敗由来のorphan候補、10.2章）に
                    # 限り、correlation_metadataのexact-match検証を試みる。
                    exec_record = self._history_store.get(record.run_id)
                    correlation = _extract_retry_lineage_correlation(exec_record)
                    if correlation is not None:
                        root_run_id, intended_attempt_no, correlation_id = correlation
                        if self._lineage.verify_orphan_correlation(
                            root_run_id, intended_attempt_no, correlation_id,
                        ):
                            skipped_lineage_correlation += 1
                            continue
                    # correlationがNone、またはverify_orphan_correlation()がFalse
                    # （a・b・cのいずれか不成立）の場合は、相関情報が存在しない場合と
                    # 全く同じ扱い（fail-closed、盲目的に信頼しない、10.3.4章）で
                    # 通常の独立候補処理へフォールバックする。

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
            skipped_lineage_member=skipped_lineage_member,
            skipped_lineage_correlation=skipped_lineage_correlation,
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
