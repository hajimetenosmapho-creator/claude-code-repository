"""
Retry Event Dispatcher（v3.9.0）

RetryDispatchEvent:   RetryCandidateEventをDispatch対象として整理した結果を表す軽量データ
RetryEventDispatcher: RetryCandidateEventのリストを受け取り、Dispatch対象として整理するコンポーネント

設計方針:
    - 入力は RetryEventConsumer.recognize_all()（v3.8.0）が返した RetryCandidateEvent の
      リストに限定する。生の SchedulerEvent（Job由来を含む混在リスト）は本コンポーネントの
      入力にならない。「通常イベントとRetryイベントの振り分け」は v3.8.0 の認識段階で
      既に完了しているという前提を踏襲し、本コンポーネントは Retry イベントのみを扱う
      （二段階フィルタリング方針、docs/design/retry_engine_event_dispatch.md 13章 Design Decision #4）。
    - RetryEventDispatcher はStateless。RetryCandidateEvent のリストを受け取り、
      Dispatch整理結果のリストを返すだけの純粋関数的なメソッドのみを持つ。
    - dispatchable は「run_id が空でないか」という構造的な妥当性のみを判定する。
      優先度・件数上限に基づく選別（ROADMAP.md記載の将来候補）は本Releaseの対象外
      （同設計書13章 Design Decision #2）。
    - Queueの状態を変更する操作（enqueue() / dequeue() / remove()）・Retry実行
      （RetryManager.retry()）への参照は一切持たない。
    - RetryCandidateEvent（candidate・source_event を含む）は分解・変換せず、
      RetryDispatchEvent.candidate_event 経由でそのままアクセス可能な状態を維持する
      （v3.7.0・v3.8.0の「候補オブジェクトを分解しない」方針を踏襲する）。
    - dispatchable=False と判定されたイベントもリストから除外せず、そのまま
      RetryDispatchEvent として返す（Dispatch対象かどうかの判定結果を可視化する）。
"""
from __future__ import annotations

from dataclasses import dataclass

from .retry_event_consumer import RetryCandidateEvent


@dataclass(frozen=True)
class RetryDispatchEvent:
    """RetryCandidateEventをDispatch対象として整理した結果を表す軽量データ。"""

    candidate_event: RetryCandidateEvent
    dispatchable: bool


class RetryEventDispatcher:
    """RetryCandidateEventのリストを受け取り、Dispatch対象として整理するコンポーネント。"""

    def dispatch_one(self, candidate_event: RetryCandidateEvent) -> RetryDispatchEvent:
        """
        1件のRetryCandidateEventをDispatch対象として整理する。
        run_idが空でない場合はdispatchable=True、空の場合はdispatchable=Falseとする。
        """
        dispatchable = bool(candidate_event.run_id)
        return RetryDispatchEvent(candidate_event=candidate_event, dispatchable=dispatchable)

    def dispatch(self, candidate_events: list[RetryCandidateEvent]) -> list[RetryDispatchEvent]:
        """複数件のRetryCandidateEventをDispatch対象として整理する。"""
        return [self.dispatch_one(candidate_event) for candidate_event in candidate_events]
