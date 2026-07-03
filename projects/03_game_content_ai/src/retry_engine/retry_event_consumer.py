"""
Retry Event Consumer（v3.8.0）

RetryCandidateEvent: Retry候補由来のSchedulerEventから認識された結果を表す軽量データ
RetryEventConsumer:   SchedulerEventのリストから、Retry候補由来のものだけを認識するコンポーネント

設計方針:
    - retry_engine が scheduler パッケージへ依存する、本Releaseで初めて追加される
      コンポーネント。依存は SchedulerEvent という単純な dataclass（副作用を持たない
      データ構造）への参照のみに限定し、SchedulerEngine 等の実行系クラスは
      一切importしない。
    - "retry:" という予約プレフィックス（v3.7.0、
      docs/design/retry_scheduler_event_integration.md 13章 Design Decision #2で確定）の
      判定は、本Releaseでは retry_engine 側のモジュール定数 RETRY_JOB_ID_PREFIX として
      保持する。scheduler側（scheduler_engine.py）は同じ文字列をリテラルとして
      job_id生成に使っているが公開定数としてexportしていないため、値としては
      重複定義になる。この重複を解消する統合（scheduler側の公開定数を参照する形への
      置き換え）は将来検討する余地として残し、本Releaseでは retry_engine 側で
      独立して定義する（docs/design/retry_engine_event_consumption.md 13章 Design Decision #3）。
    - RetryEventConsumer はStateless。SchedulerEventのリストを受け取り、認識結果の
      リストを返すだけの純粋関数的なメソッドのみを持つ。内部状態を一切保持しない。
    - Queueの状態を変更する操作（enqueue() / dequeue() / remove()）・Retry実行
      （RetryManager.retry()）への参照は一切持たない。認識のみを行う
      （Retry Queueへは到達しない。構造的に到達不可能）。
    - 候補オブジェクト（RetryQueueItemの公開属性を持つオブジェクト）は分解・変換せず
      RetryCandidateEvent.candidate にそのまま格納する（v3.7.0 Design Decision #3の
      「候補オブジェクトを分解しない」方針を受信側でも踏襲する）。
    - job_idが"retry:"で始まっていても metadata["retry_candidate"] が存在しない
      場合は、防御的にNoneを返す（例外を送出しない。安全側に倒す）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scheduler import SchedulerEvent

RETRY_JOB_ID_PREFIX = "retry:"


@dataclass(frozen=True)
class RetryCandidateEvent:
    """Retry候補由来のSchedulerEventから認識された結果を表す軽量データ。"""

    run_id: str
    candidate: Any
    source_event: SchedulerEvent


class RetryEventConsumer:
    """SchedulerEventのリストから、Retry候補由来のものだけを認識するコンポーネント。"""

    def recognize(self, event: SchedulerEvent) -> "RetryCandidateEvent | None":
        """
        1件のSchedulerEventを認識する。job_idが"retry:"で始まらない場合、
        または metadata["retry_candidate"] が存在しない場合はNoneを返す。
        """
        if not event.job_id.startswith(RETRY_JOB_ID_PREFIX):
            return None

        candidate = event.metadata.get("retry_candidate")
        if candidate is None:
            return None

        return RetryCandidateEvent(
            run_id=candidate.run_id,
            candidate=candidate,
            source_event=event,
        )

    def recognize_all(self, events: list[SchedulerEvent]) -> list[RetryCandidateEvent]:
        """複数件のSchedulerEventから、Retry候補由来のものだけを認識結果として返す。"""
        recognized: list[RetryCandidateEvent] = []
        for event in events:
            result = self.recognize(event)
            if result is not None:
                recognized.append(result)
        return recognized
