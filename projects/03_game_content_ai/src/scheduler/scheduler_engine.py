"""
Scheduler Engine（v2.6.0 / v3.4.0でRetry Scheduler Wiring・
v3.6.0でRetry Scheduler Decision Wiringを追加）

ClockProvider:       現在時刻取得を抽象化するインターフェース（テスト時に固定時刻を注入できるようにする）
SystemClockProvider: datetime.now() を返す本番用実装
SchedulerEngine:      現在時刻とJob一覧から実行対象Jobを判定するエンジン

設計方針:
    - Foundation Release（v2.6.0）のため、TriggerTypeごとの判定は「分単位マッチング」
      という最小限のルールに留める。cron式（5フィールド、範囲指定・リスト指定・
      step等）への対応は対象外（cron完全互換ではない）。将来的にTriggerType.CRONを
      追加し、croniter等のライブラリで判定するロジックを別メソッドとして追加する
      拡張を想定している（既存のDAILY/INTERVAL/ONCE判定ロジックには影響を与えない）
    - evaluate(jobs, now) は現在時刻とJob一覧を受け取って対象Jobを判定するだけの
      純粋関数とする（引数として渡されたnow以外の外部状態を参照しない。
      ファイル書き込み・Job状態の更新等の副作用は一切持たない）
    - datetime.now() を直接呼ぶのは SystemClockProvider のみに閉じ込める。
      SchedulerEngine 本体・evaluate() は ClockProvider に依存せず、
      「呼び出し側が現在時刻を渡す」設計にすることでテストを容易にする
      （ClockProvider は run_due() という便利メソッドのためだけに存在する）
    - disabledなJob（enabled=False）は判定対象から常に除外する
    - last_run_at（前回実行時刻）は今回のFoundation Releaseでは保持しない。
      そのためONCEトリガーは「対象の分に到達した」ことのみを判定し、
      一度実行済みかどうかの判定はSchedulerEngineの責務としない
      （実行後にJobをdisableする等の運用は呼び出し側／将来Releaseの責務とする）
    - persistence（判定結果の永続化）、Windows Task Scheduler / Linux cron連携は、
      いずれも将来Releaseの拡張候補であり本バージョンでは対象外とする

    - （v3.4.0）SchedulerEngine は RetrySchedulerSource / NullRetrySchedulerSource を
      Constructor Injection で保持できる（省略時は NullRetrySchedulerSource() に
      フォールバックする。v3.2.0の RetryManager が RetryQueueManager を同じ形で
      DIで受け取る設計と同一パターン。docs/design/retry_scheduler_wiring.md 2章）。
    - （v3.4.0）count_pending_retries() / list_pending_retries() を新設し、
      RetrySchedulerSource への薄い委譲のみを行う（読み取り専用）。いずれも
      evaluate() / run_due() とは完全に独立しており、判定ロジック・
      SchedulerEventの生成には一切影響しない（同設計書4章・7.4節）。
    - （v3.4.0）SchedulerEngine は RetryQueueManager を直接保持しない。
      Retry Queueへは RetrySchedulerSource 経由でのみ間接的に到達する
      （同設計書10章）。dequeue() / remove() に相当するメソッドは
      RetrySchedulerSource / NullRetrySchedulerSource のいずれにも存在しないため、
      SchedulerEngine からは構造的に呼び出せない。

    - （v3.6.0）SchedulerEngine は RetrySchedulerDecision（retry_scheduler_decision、
      v3.5.0）を Constructor Injection で保持できる（デフォルト None）。
      select_candidates() / select_next_candidate() を新設し、
      RetrySchedulerDecision への薄い委譲のみを行う（読み取り専用）。
      SchedulerEngine 自身は RetrySchedulerDecision を生成しない
      （呼び出し元が組み立てて渡す。docs/design/retry_scheduler_decision_wiring.md
      2章・13章 Design Decision #1）。RetrySchedulerDecision には対になる
      Null実装が存在しないため（v3.5.0の意図的な設計判断）、retry_decision が
      None の場合は select_candidates() / select_next_candidate() 側のガード節で
      [] / None を直接返す（同設計書13章 Design Decision #2）。
      いずれも evaluate() / run_due() とは完全に独立しており、判定ロジック・
      SchedulerEventの生成には一切影響しない（同設計書4章・7.4節）。

    - （v3.7.0）evaluate() / run_due() が、select_candidates()（v3.6.0）の
      戻り値（Retry候補）を SchedulerEvent として出力に含められるようになった
      （Retry Scheduler Event Integration）。既存のJob判定ループは1行も
      変更せず、_build_retry_events() が生成したイベントを events.extend() で
      追加連結するのみ（Additive方式。docs/design/retry_scheduler_event_integration.md
      13章 Design Decision #1）。retry_decision が None の場合、
      select_candidates() は v3.6.0のガード節により常に [] を返すため、
      evaluate() / run_due() の出力は v3.6.0時点と完全に同一となる
      （後方互換性を維持。同設計書7.2節）。
      Retry候補由来の SchedulerEvent の job_id は "retry:" + run_id とする
      （RetryQueueItem には job_id 相当のフィールドが存在しないための代替。
      同設計書13章 Design Decision #2）。metadata には候補オブジェクトを
      分解せずそのまま格納し（{"retry_candidate": 候補}）、retry_queue の
      フィールド構成を scheduler 側で解釈・変換しない（同設計書13章
      Design Decision #3。metadata["retry_candidate"] は本Releaseでは
      in-memoryの観測用途に限定し、永続化・JSON serialization・外部I/O契約
      とはしない）。Retry Engineの起動・dequeue() / remove() の呼び出し・
      Retry Queueへの書き込みはいずれも行わない（select_candidates() への
      委譲のみで、書き込み系メソッドへの参照を一切持たない）。
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from retry_scheduler_decision import RetrySchedulerDecision
from retry_scheduler_source import NullRetrySchedulerSource, RetrySchedulerSource

from .scheduler_event import SchedulerEvent
from .scheduler_job import SchedulerJob, TriggerType

REASON_DAILY_MATCHED = "Daily schedule matched."
REASON_INTERVAL_MATCHED = "Interval schedule matched."
REASON_ONCE_MATCHED = "One-time schedule matched."
REASON_RETRY_CANDIDATE_SELECTED = "Retry candidate selected."


class ClockProvider(ABC):
    """現在時刻取得を抽象化するインターフェース。"""

    @abstractmethod
    def now(self) -> datetime:
        ...


class SystemClockProvider(ClockProvider):
    """datetime.now() を返す本番用ClockProvider。"""

    def now(self) -> datetime:
        return datetime.now()


class SchedulerEngine:
    """現在時刻とJob一覧から実行対象Jobを判定するエンジン。"""

    def __init__(
        self,
        clock: ClockProvider | None = None,
        retry_source: "RetrySchedulerSource | NullRetrySchedulerSource | None" = None,
        retry_decision: "RetrySchedulerDecision | None" = None,
    ):
        self._clock = clock or SystemClockProvider()
        self._retry_source = retry_source if retry_source is not None else NullRetrySchedulerSource()
        self._retry_decision = retry_decision

    def evaluate(
        self,
        jobs: list[SchedulerJob],
        now: datetime,
        retry_limit: int | None = None,
    ) -> list[SchedulerEvent]:
        """
        現在時刻とJob一覧から、実行対象と判定されたJobのSchedulerEventのリストに、
        Retry候補由来のSchedulerEventを追加して返す（副作用なしの純粋関数）。

        disabled（enabled=False）のJobは判定対象から除外する。
        scheduleの形式が不正で判定できないJobは無視する
        （Foundation Releaseでは例外を送出せず、安全側に倒してスキップする）。
        このJob判定ループはv2.6.0から1行も変更していない。

        （v3.7.0）Retry候補の反映は、Job判定ループとは完全に独立した
        _build_retry_events() の結果を追加連結するだけで行う。
        retry_decision が None の場合、_build_retry_events() は
        select_candidates()（v3.6.0のガード節）により常に空リストを返すため、
        本メソッドの出力はv3.6.0時点とまったく同一になる（後方互換性維持）。
        """
        events: list[SchedulerEvent] = []
        for job in jobs:
            if not job.enabled:
                continue

            reason = self._match(job, now)
            if reason is None:
                continue

            events.append(
                SchedulerEvent(
                    job_id=job.job_id,
                    execute_time=now,
                    trigger_reason=reason,
                    metadata=dict(job.metadata),
                )
            )

        events.extend(self._build_retry_events(now, retry_limit))
        return events

    def run_due(
        self,
        jobs: list[SchedulerJob],
        retry_limit: int | None = None,
    ) -> list[SchedulerEvent]:
        """ClockProviderから現在時刻を取得し、evaluate()を呼び出す便利メソッド。"""
        return self.evaluate(jobs, now=self._clock.now(), retry_limit=retry_limit)

    def count_pending_retries(self) -> int:
        """
        RetrySchedulerSource.count_pending_retries() への委譲（v3.4.0）。

        evaluate() / run_due() の判定サイクルとは独立したメソッドであり、呼び出しても
        SchedulerEventの生成には一切影響しない（読み取りのみ）。
        """
        return self._retry_source.count_pending_retries()

    def list_pending_retries(self, limit: int | None = None) -> list:
        """
        RetrySchedulerSource.list_pending_retries() への委譲（v3.4.0）。

        戻り値の要素はRetryQueueItem（retry_queueパッケージの公開型）だが、
        schedulerパッケージはretry_queueに直接依存しない方針のため型ヒントとしては
        importしない（docs/design/retry_scheduler_wiring.md 13章 Design Decision #1）。
        evaluate() / run_due() の判定サイクルとは独立したメソッドであり、呼び出しても
        SchedulerEventの生成には一切影響しない（読み取りのみ）。
        """
        return self._retry_source.list_pending_retries(limit=limit)

    def select_candidates(self, limit: int | None = None) -> list:
        """
        RetrySchedulerDecision.select_candidates() への委譲（v3.6.0）。

        retry_decision が注入されていない場合（None）は、空リストを返す。
        SchedulerEngine 自身が RetrySchedulerDecision を構築することはしない
        （retry_decision=None は「候補選択機能を使わない」という呼び出し元の
        明示的な選択として扱う。docs/design/retry_scheduler_decision_wiring.md
        13章 Design Decision #2）。

        evaluate() / run_due() の判定サイクルとは独立したメソッドであり、呼び出しても
        SchedulerEventの生成には一切影響しない（読み取りのみ）。
        """
        if self._retry_decision is None:
            return []
        return self._retry_decision.select_candidates(limit=limit)

    def select_next_candidate(self):
        """
        RetrySchedulerDecision.select_next_candidate() への委譲（v3.6.0）。

        retry_decision が注入されていない場合（None）は、None を返す
        （候補なしと同じ結果）。

        evaluate() / run_due() の判定サイクルとは独立したメソッドであり、呼び出しても
        SchedulerEventの生成には一切影響しない（読み取りのみ）。
        """
        if self._retry_decision is None:
            return None
        return self._retry_decision.select_next_candidate()

    def _build_retry_events(
        self,
        now: datetime,
        retry_limit: int | None,
    ) -> list[SchedulerEvent]:
        """
        Retry候補を SchedulerEvent のリストに変換する（v3.7.0で新設）。

        self.select_candidates(limit=retry_limit)（v3.6.0）への委譲のみを行う。
        retry_decision が None の場合、select_candidates() は既存のガード節により
        空リストを返すため、本メソッドも空リストを返す（Noneチェックをここで
        重複実装しない）。

        候補オブジェクト（RetryQueueItemの公開属性を持つオブジェクト。型としては
        importしない）の run_id 属性のみを job_id 生成に使用し、"retry:" という
        予約プレフィックスを付ける。他の属性（workflow_name / priority /
        retry_attempt / status）は分解・変換せず、候補オブジェクトそのものを
        metadata["retry_candidate"] にそのまま格納する（in-memoryの観測用途に
        限定し、永続化・JSON serialization・外部I/O契約とはしない。
        docs/design/retry_scheduler_event_integration.md 13章 Design Decision #3）。

        Queueの状態を変更する操作（dequeue() / remove()）・Retry Engineの起動には
        一切到達しない（select_candidates() は読み取り専用の委譲のみ）。
        """
        events: list[SchedulerEvent] = []
        for candidate in self.select_candidates(limit=retry_limit):
            events.append(
                SchedulerEvent(
                    job_id=f"retry:{candidate.run_id}",
                    execute_time=now,
                    trigger_reason=REASON_RETRY_CANDIDATE_SELECTED,
                    metadata={"retry_candidate": candidate},
                )
            )
        return events

    def _match(self, job: SchedulerJob, now: datetime) -> str | None:
        try:
            if job.trigger_type is TriggerType.DAILY:
                return self._match_daily(job.schedule, now)
            if job.trigger_type is TriggerType.INTERVAL:
                return self._match_interval(job.schedule, now)
            if job.trigger_type is TriggerType.ONCE:
                return self._match_once(job.schedule, now)
        except (ValueError, TypeError):
            return None
        return None

    @staticmethod
    def _match_daily(schedule: str, now: datetime) -> str | None:
        """schedule="HH:MM" と now の時刻（分単位）が一致した場合のみ対象とする。"""
        if now.strftime("%H:%M") == schedule:
            return REASON_DAILY_MATCHED
        return None

    @staticmethod
    def _match_interval(schedule: str, now: datetime) -> str | None:
        """
        schedule=分単位の整数。now を「1970-01-01 00:00 からの経過分数」に換算し、
        interval_minutes の倍数と一致する分のみ対象とする（分単位マッチング）。
        """
        interval_minutes = int(schedule)
        if interval_minutes <= 0:
            return None

        epoch = datetime(1970, 1, 1)
        elapsed_minutes = int((now - epoch).total_seconds() // 60)
        if elapsed_minutes % interval_minutes == 0:
            return REASON_INTERVAL_MATCHED
        return None

    @staticmethod
    def _match_once(schedule: str, now: datetime) -> str | None:
        """schedule="YYYY-MM-DDTHH:MM" と now の分単位が一致した場合のみ対象とする。"""
        scheduled_at = datetime.strptime(schedule, "%Y-%m-%dT%H:%M")
        if now.strftime("%Y-%m-%dT%H:%M") == scheduled_at.strftime("%Y-%m-%dT%H:%M"):
            return REASON_ONCE_MATCHED
        return None
