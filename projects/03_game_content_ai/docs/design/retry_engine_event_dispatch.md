# v3.9.0 Retry Engine Event Dispatch 設計書（Architecture Design）

作成日：2026-07-06
状態：ドラフト（Architecture Review実施済み。ユーザー確認待ち）。
`docs/design/retry_engine_event_dispatch_charter.md`（Project Charter、
ユーザー承認済み、2026-07-06）を前提とする。

---

## 1. Architecture Overview

Release 3.8（`docs/design/retry_engine_event_consumption.md`）までで、以下が
確立した。

* `retry_engine`パッケージに`RetryEventConsumer`が新設され、
  `RetryManager.recognize_retry_events(events)`が、Job由来とRetry候補由来が
  混在した`SchedulerEvent`のリストから、Retry候補由来のものだけを
  `RetryCandidateEvent`（`run_id` / `candidate` / `source_event`）として
  認識できるようになった
* 認識結果（`RetryCandidateEvent`）を使って何かを判断・整理する仕組みは、
  `retry_engine`側に一切存在しない（認識のみで完結し、その先は何もない）

本Release（v3.9.0）は、`retry_engine`パッケージに**認識の次の段階**として、
認識済みの`RetryCandidateEvent`を「Dispatch対象として扱える」ようにする
コンポーネントを新設する。ユーザー指示の重点8項目
（責務の配置・判定基準・データ構造・振り分け方針・`retry()`不使用の保証・
Queue不更新の保証・`dequeue()` / `remove()`不使用の保証・後方互換性）を、
Charter 8章 Open Questionsへの確定回答としてそれぞれ反映する。

```
Scheduler（判断、v2.6.0〜v3.7.0、無改修）          Retry Engine（受信・実行判断、v3.0.0〜v3.8.0）
   │                                                    │
   └── evaluate() / run_due()                           ├── RetryManager
            │                                            │    ├── retry()                 （無改修）
            └── SchedulerEvent 生成                      │    ├── enqueue_retry() /        （無改修）
                 （Job由来 ＋ Retry候補由来）              │    │   dequeue_retry()
                          │                                │    ├── recognize_retry_events() （無改修、v3.8.0）
                          │                                │    │      │ 薄い委譲
                          │                                │    │      ▼
                          │                                │    │  RetryEventConsumer（無改修）
                          │                                │    │      │ 生成
                          │                                │    │      ▼
                          │                                │    │  RetryCandidateEvent（無改修）
                          │                                │    │
                          │                                │    └── dispatch_retry_events() ★新設
                          │                                │           │  recognize_retry_events()に委譲
                          │                                │           │  → RetryEventDispatcherに委譲
                          └───────────────────────────────►│           ▼
                             呼び出し元が SchedulerEvent の  │  RetryEventDispatcher ★新設コンポーネント
                             リストをそのまま引数として渡す  │  （retry_engine配下、外部パッケージへの新規依存なし）
                                                            │
                                                     RetryDispatchEvent ★新設データ構造
                                                     （candidate_event・dispatchable）
```

本Releaseの核心は、「認識済みのRetry候補をDispatch対象として整理する」という
1つの新しい関心事を、既存の`retry()` / `enqueue_retry()` / `dequeue_retry()` /
`recognize_retry_events()`と**呼び出しグラフ上で完全に独立させたまま**
`retry_engine`に追加することである。`dispatch_retry_events()`は
`recognize_retry_events()`を内部で呼び出す（合成する）が、これは既存メソッドへの
「利用」であって「変更」ではない。

---

## 2. Design Policy

Charter 5章 Design Principles、およびユーザー指示の8つの重点項目を、本設計では
以下の形で具体化する。

1. **責務の配置（重点1）**：新規ファイル`src/retry_engine/retry_event_dispatcher.py`に
   `RetryEventDispatcher`を追加する（Charter 8章 Open Question 1、案A。
   v3.8.0の`RetryEventConsumer`と同じ配置方針）。独立パッケージへの切り出しは
   行わない（13章 Design Decision #1）
2. **Dispatch対象の判定基準（重点2）**：「優先度・件数上限に基づく選別」
   （ROADMAP.mdが将来候補として例示する内容）は本Releaseでは導入しない。
   代わりに、`RetryCandidateEvent.run_id`が空でないかという**構造的妥当性**のみを
   判定基準とする（`dispatchable: bool`）。空の場合（防御的なケース。v3.7.0・
   v3.8.0で通常発生しない想定だが構造的に排除できない）は`dispatchable=False`
   とし、Dispatch対象から除外する（13章 Design Decision #2）
3. **Dispatch結果の型（重点3）**：`RetryDispatchEvent`という軽量な
   `frozen=True`の`dataclass`を新設する。フィールドは`candidate_event`
   （元の`RetryCandidateEvent`、分解しない）・`dispatchable`（判定結果）の
   2つのみ（13章 Design Decision #3）
4. **通常イベントとRetryイベントの振り分け方針（重点4）**：振り分けは
   **二段階**で構成される。第1段階（v3.8.0の`recognize_retry_events()`、
   無改修）が「Job由来（通常イベント）」を静かに除外し、「Retry候補由来」の
   ものだけを`RetryCandidateEvent`として抽出する。第2段階（本Release）は
   その`RetryCandidateEvent`のみを入力とし、生の`SchedulerEvent`混在リストを
   一切受け取らない。したがって通常イベントは第2段階（Dispatch）の入力にすら
   現れない、という構造で振り分け方針を保証する（13章 Design Decision #4）
5. **`retry()`を呼ばないことの保証（重点5）**：`RetryEventDispatcher`は
   `RetryPolicy` / `RetryExecutor` / `WorkflowMonitorManager`のいずれへの
   参照も持たない。`dispatch_retry_events()`も`self._policy` /
   `self._executor` / `self._monitor`を一切参照しない（9.2節）
6. **Retry Queueを更新しないことの保証（重点6）**：`RetryEventDispatcher`は
   `RetryQueueManager` / `NullRetryQueueManager`への参照を一切持たない
   （コンストラクタ引数にも存在しない）。`dispatch_retry_events()`も
   `self._queue`を一切参照しない（9.2節）
7. **`dequeue()` / `remove()`を呼ばないことの保証（重点7）**：上記6と同じ理由で、
   `RetryEventDispatcher`・`dispatch_retry_events()`のいずれからも
   `RetryQueueManager`へ到達する経路が構造的に存在しない（9.2節）
8. **既存APIとの後方互換性（重点8）**：`RetryManager.__init__` /
   `from_config()`に`event_dispatcher`引数（デフォルト`None`）を追加し、
   省略時は`RetryEventDispatcher()`に自動フォールバックする。既存の
   `retry()` / `enqueue_retry()` / `dequeue_retry()` / `recognize_retry_events()`は
   1行も変更しない（12章）
9. **Foundation First**：Dispatch結果（`RetryDispatchEvent`）を使って
   何かを実行する処理（`retry()`の自動呼び出し等）は一切追加しない（11章）
10. **Single Responsibility**：`RetryEventDispatcher`は「認識済みの
    `RetryCandidateEvent`をDispatch対象として整理する」ことのみを担う。
    認識ロジック自体（`RetryEventConsumer`）・Queue管理（`retry_queue`）・
    実行判断（`RetryPolicy`）のいずれも複製・肩代わりしない
11. **Stateless**：`RetryEventDispatcher`は内部状態を一切持たない。
    呼び出しごとに渡された`RetryCandidateEvent`のリストのみから結果を導出する

---

## 3. Package Structure（変更差分）

```
src/retry_engine/
├── __init__.py               # 変更：新規シンボル（RetryDispatchEvent / RetryEventDispatcher）
│                              #        のexport追加。docstring更新
├── retry_event_consumer.py   # 無変更（v3.8.0のまま）
├── retry_event_dispatcher.py # ★新規：RetryDispatchEvent / RetryEventDispatcher
├── retry_manager.py           # ★変更：RetryManager.__init__ に event_dispatcher 引数追加。
│                              #        dispatch_retry_events() を追加。
│                              #        NullRetryManager にも同名メソッドを追加
├── retry_config.py            # 無変更
├── retry_executor.py          # 無変更
├── retry_policy.py            # 無変更
├── retry_request.py           # 無変更
└── retry_result.py            # 無変更

src/scheduler/                 # 全ファイル無改修（v3.7.0のまま）
src/retry_scheduler_decision/  # 全ファイル無改修
src/retry_scheduler_source/    # 全ファイル無改修
src/retry_queue/               # 全ファイル無改修

tests/
└── test_e2e_v3_9_0_retry_engine_event_dispatch.py   # 新規
```

変更対象は`retry_engine`配下2ファイル（`retry_event_dispatcher.py`新規・
`retry_manager.py`変更）と`__init__.py`のみ。`scheduler` /
`retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue`・
`retry_event_consumer.py`はいずれも本Releaseでもゼロ改修。

---

## 4. Public API

### `retry_event_dispatcher.py`（新規）

```python
"""
Retry Event Dispatcher（v3.9.0）

RetryDispatchEvent:   RetryCandidateEventをDispatch対象として整理した結果を表す軽量データ
RetryEventDispatcher: RetryCandidateEventのリストを受け取り、Dispatch対象として整理するコンポーネント

設計方針:
    - 入力は RetryEventConsumer.recognize_all()（v3.8.0）が返した RetryCandidateEvent の
      リストに限定する。生の SchedulerEvent（Job由来を含む混在リスト）は本コンポーネントの
      入力にならない。「通常イベントとRetryイベントの振り分け」は v3.8.0 の認識段階で
      既に完了しているという前提を踏襲し、本コンポーネントは Retry イベントのみを扱う
      （二段階フィルタリング方針、本設計書2章・13章 Design Decision #4）。
    - RetryEventDispatcher はStateless。RetryCandidateEvent のリストを受け取り、
      Dispatch整理結果のリストを返すだけの純粋関数的なメソッドのみを持つ。
    - dispatchable は「run_id が空でないか」という構造的な妥当性のみを判定する。
      優先度・件数上限に基づく選別（ROADMAP.md記載の将来候補）は本Releaseの対象外
      （13章 Design Decision #2）。
    - Queueの状態を変更する操作（enqueue() / dequeue() / remove()）・Retry実行
      （RetryManager.retry()）への参照は一切持たない。
    - RetryCandidateEvent（candidate・source_event を含む）は分解・変換せず、
      RetryDispatchEvent.candidate_event 経由でそのままアクセス可能な状態を維持する
      （v3.7.0 Design Decision #3・v3.8.0 Design Decision #2の
      「候補オブジェクトを分解しない」方針を踏襲する）。
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
```

### `retry_manager.py`（変更部分のみ抜粋）

```python
from __future__ import annotations

from datetime import datetime

from retry_queue import NullRetryQueueManager, RetryQueueManager, RetryQueueOutcome, RetryQueueResult
from scheduler import SchedulerEvent
from workflow_engine import NullWorkflowEngineManager, WorkflowEngineManager
from workflow_monitor import NullWorkflowMonitorManager, WorkflowMonitorManager, WorkflowMonitorStatus

from .retry_config import RetryConfig
from .retry_event_consumer import RetryCandidateEvent, RetryEventConsumer
from .retry_event_dispatcher import RetryDispatchEvent, RetryEventDispatcher  # ★新規
from .retry_executor import RetryExecutor
from .retry_policy import RetryPolicy
from .retry_request import RetryRequest
from .retry_result import RetryOutcome, RetryResult


class RetryManager:
    def __init__(
        self,
        policy: RetryPolicy,
        executor: RetryExecutor,
        monitor: WorkflowMonitorManager,
        queue: "RetryQueueManager | NullRetryQueueManager | None" = None,
        event_consumer: RetryEventConsumer | None = None,
        event_dispatcher: RetryEventDispatcher | None = None,  # ★新規
    ):
        self._policy = policy
        self._executor = executor
        self._monitor = monitor
        self._queue = queue if queue is not None else NullRetryQueueManager()
        self._event_consumer = event_consumer if event_consumer is not None else RetryEventConsumer()
        self._event_dispatcher = (
            event_dispatcher if event_dispatcher is not None else RetryEventDispatcher()
        )  # ★新規

    @classmethod
    def from_config(
        cls,
        retry_config: RetryConfig,
        retry_policy: RetryPolicy,
        workflow_engine_manager: "WorkflowEngineManager | NullWorkflowEngineManager",
        workflow_monitor_manager: "WorkflowMonitorManager | NullWorkflowMonitorManager",
        retry_queue_manager: "RetryQueueManager | NullRetryQueueManager | None" = None,
        event_consumer: RetryEventConsumer | None = None,
        event_dispatcher: RetryEventDispatcher | None = None,  # ★新規
    ) -> "RetryManager | NullRetryManager":
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
            event_dispatcher=event_dispatcher,  # ★新規
        )

    # retry() / enqueue_retry() / dequeue_retry() / recognize_retry_events() /
    # _skip_reason() は無変更（省略）

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


class NullRetryManager:
    """RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている場合のダミー実装。"""

    _DISABLED_REASON = (
        "Retry Engine is disabled (RETRY_ENGINE_ENABLED=false, "
        "or AI_AGENT_ENABLED/WORKFLOW_ENGINE_ENABLED is not ready)."
    )

    # retry() / enqueue_retry() / dequeue_retry() / recognize_retry_events() は無変更（省略）

    def dispatch_retry_events(self, events: list[SchedulerEvent]) -> list[RetryDispatchEvent]:
        """
        RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている場合でも、
        Dispatch整理自体はQueue操作・実行を一切伴わない副作用のない読み取りであるため、
        recognize_retry_events()と同じ理由で常に空リストを返す
        （「受け取れるが何もしない」）。RetryEventDispatcherへの参照は保持しない。
        """
        return []
```

* `RetryManager.__init__` / `from_config()`とも、既存引数の**末尾**に
  デフォルト値付きの`event_dispatcher`を追加する。既存の位置引数・
  キーワード引数呼び出しはいずれも影響を受けない
* `dispatch_retry_events()`は`self.recognize_retry_events(events)`（既存メソッドの
  呼び出し）→`self._event_dispatcher.dispatch(candidate_events)`（新規委譲）の
  2行のみで完結する
* `NullRetryManager.dispatch_retry_events()`は`RetryEventDispatcher`を
  一切構築・参照せず、リテラルの空リストを返す

### `__init__.py` の公開シンボル

```python
from .retry_config import RetryConfig
from .retry_policy import DEFAULT_TARGET_STATUSES, RetryPolicy
from .retry_request import RetryRequest
from .retry_result import RetryOutcome, RetryResult
from .retry_executor import RetryExecutor
from .retry_event_consumer import RetryCandidateEvent, RetryEventConsumer
from .retry_event_dispatcher import RetryDispatchEvent, RetryEventDispatcher  # ★新規
from .retry_manager import NullRetryManager, RetryManager

__all__ = [
    "RetryPolicy",
    "DEFAULT_TARGET_STATUSES",
    "RetryConfig",
    "RetryRequest",
    "RetryOutcome",
    "RetryResult",
    "RetryExecutor",
    "RetryCandidateEvent",
    "RetryEventConsumer",
    "RetryDispatchEvent",     # ★新規
    "RetryEventDispatcher",   # ★新規
    "RetryManager",
    "NullRetryManager",
]
```

---

## 5. Class Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `SchedulerEngine`（v3.7.0、無改修） | Retry候補由来の`SchedulerEvent`を生成する | 認識・Dispatch・実行 |
| `RetryEventConsumer`（v3.8.0、無改修） | `SchedulerEvent`のリストからRetry候補由来のものを識別・認識する | Dispatch対象の判定・整理・実行 |
| `RetryEventDispatcher`（本Releaseで新規） | 認識済みの`RetryCandidateEvent`をDispatch対象として整理・分類する（`dispatchable`の判定） | 認識ロジックの再実装・優先度/件数上限に基づく選別・実行判断・Queue操作・Retry実行 |
| `RetryManager`（本Releaseで変更） | `RetryEventDispatcher`への薄い委譲窓口を持つ（`recognize_retry_events()`との合成のみ） | Dispatchロジックの再実装／Dispatch結果の自動実行 |
| `NullRetryManager`（本Releaseで変更） | 無効時に安全な空リストを返す | `RetryEventDispatcher`の構築・保持 |
| `RetryPolicy` / `RetryExecutor`（v3.0.0、無改修） | Retry可否判定・実行 | イベント認識・Dispatch |
| `RetryQueueManager`（v3.1.0、無改修） | Queueへの出し入れ・整列 | イベント認識・Dispatch・実行判断 |

`RetryEventConsumer`（v3.8.0）と`RetryEventDispatcher`（本Release）は、
「Job由来かRetry候補由来か」（認識）と「Dispatch対象として扱えるか」
（整理）という異なる関心事を、それぞれ独立したコンポーネントとして担う。
両者は`RetryManager.dispatch_retry_events()`内での呼び出し順序（認識→整理）
によってのみ連携し、互いを直接参照しない。

---

## 6. Class Diagram

```
┌───────────────────────────────────────────┐
│                  RetryManager                   │
│───────────────────────────────────────────│
│ - _policy: RetryPolicy                          │  無変更
│ - _executor: RetryExecutor                      │  無変更
│ - _monitor: WorkflowMonitorManager              │  無変更
│ - _queue: RetryQueueManager |                   │  無変更（v3.2.0）
│           NullRetryQueueManager                  │
│ - _event_consumer: RetryEventConsumer           │  無変更（v3.8.0）
│ - _event_dispatcher: RetryEventDispatcher       │  ★新設
│───────────────────────────────────────────│
│ + __init__(policy, executor, monitor,           │  ★event_dispatcher引数を追加
│            queue=None, event_consumer=None,      │
│            event_dispatcher=None)                │
│ + from_config(...) -> RetryManager|              │  ★event_dispatcher引数を追加
│                        NullRetryManager           │
│ + retry(run_id, attempt=1, dry_run=False)       │  無変更
│     -> RetryResult                               │
│ + enqueue_retry(run_id, workflow_name, ...)     │  無変更
│     -> RetryQueueResult                          │
│ + dequeue_retry() -> RetryQueueResult           │  無変更
│ + recognize_retry_events(events)                │  無変更（v3.8.0）
│     -> list[RetryCandidateEvent]                 │
│ + dispatch_retry_events(events)                 │  ★新設
│     -> list[RetryDispatchEvent]                  │
└──────────────────┬────────────────────────┘
                    │ 委譲（recognize_retry_events経由で得たcandidate_eventsをdispatchへ）
                    ▼
        ┌──────────────────────────┐
        │      RetryEventDispatcher      │  ★新設（Stateless）
        │──────────────────────────│
        │ + dispatch_one(candidate_event) │
        │     -> RetryDispatchEvent        │
        │ + dispatch(candidate_events)    │
        │     -> list[RetryDispatchEvent] │
        └──────────────┬───────────┘
                        │ 生成
                        ▼
        ┌──────────────────────────────┐
        │        RetryDispatchEvent          │  ★新設（frozen dataclass）
        │──────────────────────────────│
        │ + candidate_event: RetryCandidateEvent │  （v3.8.0、分解しない）
        │ + dispatchable: bool                │  （run_idが空でないか）
        └──────────────────────────────┘

┌────────────────────────────────┐
│           NullRetryManager           │
│────────────────────────────────│
│ + retry(...) -> RetryResult          │  無変更（DISABLED）
│ + enqueue_retry(...)                 │  無変更（DISABLED）
│     -> RetryQueueResult              │
│ + dequeue_retry() -> RetryQueueResult│  無変更（DISABLED）
│ + recognize_retry_events(events)     │  無変更（v3.8.0、常に[]）
│     -> list[RetryCandidateEvent]     │
│ + dispatch_retry_events(events)      │  ★新設（常に[]）
│     -> list[RetryDispatchEvent]      │
└────────────────────────────────┘
```

`RetryEventDispatcher`は`RetryManager`にのみ保持され、`NullRetryManager`は
これを一切参照しない（構築コスト・依存を持たずに「何もしない」を実現する）。
`RetryEventDispatcher`自体も`RetryEventConsumer`への参照を持たない
（両者は`RetryManager`を介してのみ連携する）。

---

## 7. Sequence Diagram

### 7.1 dispatch_retry_events()（正常なRetry候補由来のイベントを含む場合）

```
Caller            RetryManager         RetryEventConsumer      RetryEventDispatcher
  │  events = scheduler_engine.evaluate(jobs, now, retry_limit=2)                            │
  │  # events = [SchedulerEvent(job_id="job-a", ...),                                         │
  │  #           SchedulerEvent(job_id="retry:run-001", metadata={...})]                      │
  │                                                                                            │
  │  retry_manager.dispatch_retry_events(events)                                             │
  ├──────────────────►│                                                                       │
  │                    │  self.recognize_retry_events(events)                                 │
  │                    ├───────────────────────────►│                                        │
  │                    │                             │ "job-a"は対象外                          │
  │                    │                             │ "retry:run-001"→RetryCandidateEvent化    │
  │                    │◄───────────────────────────┤                                        │
  │                    │  [RetryCandidateEvent(run_id="run-001", ...)]                        │
  │                    │                                                                       │
  │                    │  self._event_dispatcher.dispatch(candidate_events)                   │
  │                    ├──────────────────────────────────────────────────►│                │
  │                    │                                                    │ run_id="run-001"  │
  │                    │                                                    │ は空でない         │
  │                    │                                                    │ → dispatchable=True│
  │                    │◄──────────────────────────────────────────────────┤                │
  │◄──────────────────┤  [RetryDispatchEvent(candidate_event=..., dispatchable=True)]         │
```

### 7.2 dispatch_retry_events()（Retry候補由来のイベントを含まない場合）

```
Caller            RetryManager         RetryEventConsumer      RetryEventDispatcher
  │  events = [SchedulerEvent(job_id="job-a", ...)]  # Job由来のみ                             │
  │                                                                                            │
  │  retry_manager.dispatch_retry_events(events)                                              │
  ├──────────────────►│                                                                       │
  │                    │  self.recognize_retry_events(events) → []                             │
  │                    ├───────────────────────────►│（"retry:"で始まらないため対象外）          │
  │                    │◄───────────────────────────┤                                        │
  │                    │  self._event_dispatcher.dispatch([]) → []                             │
  │                    ├──────────────────────────────────────────────────►│（空リストのため何もしない）│
  │                    │◄──────────────────────────────────────────────────┤                │
  │◄──────────────────┤  []                                                                    │
```

### 7.3 dispatch_retry_events()（run_idが空の防御的なケース）

```
Caller            RetryManager                              RetryEventDispatcher
  │  # RetryCandidateEvent.run_id が空文字列になる不正なデータが渡された場合                    │
  │  # （通常のv3.7.0/v3.8.0の生成経路では発生しないが、構造的に排除できないため防御的に扱う）    │
  │                                                                                            │
  │  retry_manager.dispatch_retry_events(events)                                              │
  ├──────────────────►│                                                                       │
  │                    │  candidate_events = [RetryCandidateEvent(run_id="", ...)]             │
  │                    │  self._event_dispatcher.dispatch(candidate_events)                    │
  │                    ├──────────────────────────────────────────────────►│                │
  │                    │                                                    │ run_id="" は空    │
  │                    │                                                    │ → dispatchable=False│
  │                    │◄──────────────────────────────────────────────────┤                │
  │◄──────────────────┤  [RetryDispatchEvent(candidate_event=..., dispatchable=False)]         │
```

`dispatchable=False`の場合でも、`RetryDispatchEvent`自体はリストから除外
されない（呼び出し元へ「Dispatch対象として不適格である」ことを構造的に
可視化する。Charter 8章 Open Question 2で検討した「全件整理し、判定結果を
可視化する」案を採用。13章 Design Decision #2参照）。

### 7.4 NullRetryManager.dispatch_retry_events()

```
Caller            NullRetryManager
  │  null_manager.dispatch_retry_events(events)  # eventsの中身は問わない │
  ├──────────────────►│                                                   │
  │                    │  return []  # RetryEventDispatcherへの参照を持たない │
  │◄──────────────────┤  []                                               │
```

---

## 8. Data Flow

```
① 呼び出し元（Composition Root、本Releaseでは未実装）が
   SchedulerEngine.evaluate() / run_due() を呼び出し、SchedulerEvent のリストを得る
   （v3.7.0までで確立済み。本Releaseでは変更しない）
        ↓
② 呼び出し元が、そのリストをそのまま RetryManager.dispatch_retry_events(events)
   （または NullRetryManager.dispatch_retry_events(events)）へ渡す
   （本Releaseでも、この呼び出し元＝Composition Root自体は実装しない。
   Charter Non-Goals・11章 Future Extension）
        ↓
③ RetryManager は self.recognize_retry_events(events)（v3.8.0、無変更）へ
   委譲し、Retry候補由来の SchedulerEvent だけを RetryCandidateEvent の
   リストとして得る（Job由来の SchedulerEvent はこの時点で除外され、
   以降のステップには一切現れない）
        ↓
④ RetryManager は ③で得た RetryCandidateEvent のリストを
   self._event_dispatcher.dispatch(candidate_events)
   （RetryEventDispatcher、本Release新設）へ委譲する
        ↓
⑤ RetryEventDispatcher が各 candidate_event.run_id を検査する
   ⑤-a run_id が空でない場合：dispatchable=True の RetryDispatchEvent を生成する
   ⑤-b run_id が空の場合（通常発生しないが、防御的な取り扱い。13章 Design
        Decision #2）：dispatchable=False の RetryDispatchEvent を生成する
        （リストから除外はしない）
        ↓
⑥ dispatch() が集めた RetryDispatchEvent のリストを
   dispatch_retry_events() の戻り値として返す
        ↓
⑦ ⑥で得られた RetryDispatchEvent を使って何かを判断・実行する処理
   （dispatchable=True のものだけを選んで retry() を自動的に呼び出す、
   優先度・件数上限に基づく絞り込みを行う等）は、本Releaseでは
   一切存在しない（Dispatch対象として整理できる＝観測可能になっただけ。11章）
```

`retry_queue`パッケージへのimportは本Releaseのどの段階でも新規に発生しない。
`scheduler`パッケージへの新規importも発生しない（`RetryEventDispatcher`は
`RetryCandidateEvent`（`retry_engine`パッケージ内、v3.8.0で新設済み）のみを
importし、`scheduler.SchedulerEvent`を直接importしない。9.1節で詳述）。

---

## 9. Boundary（今回入れない境界線）

本Releaseが**構造的に**実行不可能にする操作、および境界維持の方法を明示する
（ユーザー指示の重点5・6・7に対応）。

### 9.1 `RetryEventDispatcher` が新規の外部パッケージ依存を持たない境界

| 確認観点 | 本Releaseでの扱い |
|---|---|
| `retry_event_dispatcher.py`に`from scheduler import ...`が存在するか | 存在しない。importするのは`.retry_event_consumer`（`retry_engine`パッケージ内）と標準ライブラリ（`dataclasses`）のみ |
| `retry_event_dispatcher.py`に`from retry_queue import ...`が存在するか | 存在しない |
| `RetryCandidateEvent.candidate` / `source_event`の中身を解釈・分解するか | しない。`dispatch_one()`が参照するのは`candidate_event.run_id`のみ（`bool()`判定のためだけに使用）。`candidate` / `source_event`は`RetryDispatchEvent.candidate_event`にそのまま格納される |

### 9.2 実行・Queue操作に関する境界（重点5・6・7）

| 操作 | 本Releaseでの扱い | 根拠 |
|---|---|---|
| `RetryManager.retry()`の自動呼び出し（重点5） | 呼び出し不可 | `RetryEventDispatcher`は`RetryPolicy` / `RetryExecutor` / `WorkflowMonitorManager`のいずれへの参照も持たない（コンストラクタが引数を取らない）。`dispatch_retry_events()`も`self._policy` / `self._executor` / `self._monitor`のいずれも参照しない（4章のとおり2行のみで完結） |
| Retry Queueへの書き込み（`enqueue`含む、重点6） | 呼び出し不可 | `RetryEventDispatcher`は`RetryQueueManager` / `NullRetryQueueManager`への参照を一切持たない |
| `RetryQueueManager.dequeue()`（重点7） | 呼び出し不可 | 同上。`dispatch_retry_events()`も`self._queue`を一切参照しない |
| `RetryQueueManager.remove()`（重点7） | 呼び出し不可 | 同上 |
| Dispatch結果（`RetryDispatchEvent`）の永続化 | 対象外 | `RetryEventDispatcher`はStateless（`RetryDispatchEvent`を内部にキャッシュしない）。呼び出しのたびに引数で渡された`candidate_events`のみから結果を導出する |
| 既存Job判定ループ（`SchedulerEngine._match*`系）・`RetryEventConsumer`への影響 | 発生しない | 本Releaseは`retry_engine`配下（新規1ファイル・`retry_manager.py`・`__init__.py`）のみを変更する |

Acceptance Criteria（Charter 9章）の「構造的確認」は、上記の表と1対1で
対応する形でテストする（`src/retry_engine/retry_event_dispatcher.py`に
`self._queue` / `self._policy` / `self._executor` / `self._monitor` /
`RetryQueueManager` / `WorkflowMonitorManager` / `RetryPolicy` /
`RetryExecutor`への参照が存在しないことをコードレビュー・Spyオブジェクトに
よるテストの両面で確認する）。

---

## 10. Configuration

**本Releaseでは新規の環境変数を一切追加しない**（Charter 5章・Goals 7）。

| 環境変数 | デフォルト | 説明 | 本Releaseでの役割 |
|---|---|---|---|
| `RETRY_ENGINE_ENABLED` | `false` | Retry Engine全体の有効/無効（`RetryConfig`、無改修） | `from_config()`が`RetryManager` / `NullRetryManager`のどちらを返すかの既存判断基準（無変更）。`RetryEventDispatcher`の有効/無効はこのゲートに紐付かない（`RetryManager`が存在すれば常に有効） |
| `RETRY_QUEUE_ENABLED` | `true` | Retry Queueの有効/無効（`RetryQueueConfig`、無改修） | 本Releaseの変更対象外 |

`RetryEventDispatcher`自体には対応するFeature Gate・環境変数を設けない
（Stateless・副作用なしの整理処理であり、`RetryEventConsumer`（v3.8.0）と
同じく「無効化」という概念を持たない。Charter 8章 Open Question 6への回答、
13章 Design Decision #5）。

---

## 11. Future Extension

* **Dispatch結果（`RetryDispatchEvent`）を使った自動Retry実行（Retry
  Execution）**：`dispatch_retry_events()`が返した`dispatchable=True`の候補を
  実際に`RetryManager.retry()`へ渡して再実行する自動化（Charter Non-Goals・
  本設計書9.2節で明示的に対象外とした領域。ROADMAP.md記載の次段階）
* **優先度・件数上限に基づく選別ロジック**：ROADMAP.mdが将来候補として
  例示する「優先度・件数上限に基づく選別」は、本Releaseでは`dispatchable`の
  構造的妥当性判定のみに留め、意図的に導入しない。Retry Executionの
  設計段階で、`dispatchable=True`の候補群に対してどう優先度付け・件数制限を
  適用するかを検討する
* **実運用のComposition Root**：`SchedulerEngine.run_due()`の結果を
  実際に`RetryManager.dispatch_retry_events()`へ渡して回す起動スクリプトは
  引き続き未着手（v3.4.0から持ち越し）
* **`RetryDispatchEvent.dispatchable`の判定基準の拡張**：現状は
  `run_id`の空文字チェックのみ。将来、候補オブジェクトの他の属性
  （`retry_attempt` / `status`等）を使った判定基準が必要になった場合、
  `dispatch_one()`内のロジックを拡張する余地を残す（型・フィールドは
  変更不要）
* **`"retry:"`プレフィックス定数の重複解消**：v3.8.0から持ち越しの既知の
  限界（`scheduler_engine.py`のリテラルと`retry_event_consumer.py`の
  `RETRY_JOB_ID_PREFIX`の重複）。本Releaseでも解消しない
* **`job_id`プレフィックス衝突の構造的な防止**：v3.7.0から持ち越しの
  既知の限界。本Releaseでも解消しない

---

## 12. Compatibility

* `RetryManager.__init__` / `from_config()`への`event_dispatcher`オプション
  引数追加のみ。既存の`RetryManager(policy, executor, monitor)` /
  `RetryManager(policy, executor, monitor, queue=...)` /
  `RetryManager(policy, executor, monitor, event_consumer=...)` /
  `RetryManager.from_config(...)`（新規引数を渡さない場合）は、
  本Release後もまったく同じ結果になる
* `retry()` / `enqueue_retry()` / `dequeue_retry()` / `recognize_retry_events()`
  （`RetryManager` / `NullRetryManager`とも）は1行も変更しない
* `retry_event_consumer.py`（`RetryCandidateEvent` / `RetryEventConsumer`）・
  `retry_config.py` / `retry_executor.py` / `retry_policy.py` /
  `retry_request.py` / `retry_result.py`は無改修
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
  `retry_queue`配下の全ファイルも無改修
* 新規の環境変数を追加しないため、`.env` / `.env.example`の変更も不要
* 既存の`RetryManager()` / `RetryManager.from_config(...)`呼び出しテスト
  （v3.0.0〜v3.8.0）は無改修のまま全PASSする想定
  （コンストラクタ・`from_config()`のシグネチャ変更は末尾への
  デフォルト値付き引数追加のみであり、位置引数・キーワード引数いずれの
  既存呼び出しにも影響しない）

---

## 13. Design Decisions（設計判断の根拠）

### Design Decision #1：新規コンポーネントは`retry_engine`パッケージ内に配置する

Charter 8章 Open Question 1に対し、v3.8.0の`RetryEventConsumer`と同じ配置
方針（案A）を採用する。

* 「Retry EngineがRetry候補をDispatch対象として扱えるようにする」という
  ユーザー指示の目的に対し、`RetryManager`・`RetryEventConsumer`と同じ
  パッケージに置くことで、責務の所在が直感的になる
* `RetryEventDispatcher`は`RetryEventConsumer`の出力（`RetryCandidateEvent`）
  のみを入力とする性質上、`retry_engine`パッケージ外に置くと
  `RetryCandidateEvent`という型を新たにパッケージ境界を越えて公開する
  必要が生じ、かえって結合が増える
* 将来、Dispatchロジックが複雑化し他のコンポーネントからも再利用される
  必要が生じた場合、`retry_engine`パッケージ内から独立パッケージへ
  切り出すリファクタリングは可能（現時点で先回りして分離しない）

### Design Decision #2：Dispatch対象の判定基準は構造的妥当性（run_idの非空判定）に限定する

Charter 8章 Open Question 2に対し、「(a) 認識済みの`RetryCandidateEvent`を
無条件で全件Dispatch対象とし型・構造だけを整理する案」と「(b) 優先度・件数
上限に基づく選別ロジックまで本Releaseで導入する案」のうち、両者の中間
（構造的妥当性のみを判定する）を採用する。

* ROADMAP.mdの「例：優先度・件数上限に基づく選別」という記載は、
  Retry Executionの一歩手前の候補例であり、本Release単独での必須要件では
  ない（Charter冒頭の位置づけ注記）。優先度・件数上限といった**ビジネス
  判断**を本Releaseに持ち込むと、Retry Execution（実行対象決定）との
  責務境界が曖昧になり、Foundation Firstの原則から逸脱する
* 一方、完全に無条件（常に`dispatchable=True`）とすると、
  「Dispatch対象かどうかを判定する基準」（ユーザー指示の重点2）という
  設計上の要求に対して実質的な判定ロジックが存在しないことになる
* 折衷案として、`run_id`が空でないかという**構造的な妥当性チェック**のみを
  採用する。これはv3.8.0 Design Decision #7（`metadata["retry_candidate"]`
  欠如時に防御的にNoneを返す）と同じ「規約から外れたデータに対して
  安全側に倒す」という設計言語の延長であり、ビジネス判断（優先度・件数
  上限）とは性質が異なる
* `dispatchable=False`になったイベントをリストから除外せず、
  `RetryDispatchEvent`として可視化する（7.3節）ことで、将来の消費者
  （Retry Execution）が「なぜDispatch対象から外れたか」を観測できる
  余地を残す

### Design Decision #3：Dispatch結果は`RetryDispatchEvent`という軽量frozen dataclassとする

Charter 8章 Open Question 3に対し、専用データクラスを新設する。
フィールドは`candidate_event` / `dispatchable`の2つのみに絞る。

* `RetryCandidateEvent`（v3.8.0）・`RetryRequest` / `RetryResult`
  （v3.0.0、いずれも`frozen=True`）と同じく「1回限りの入出力データ」
  としての性質を持つため、`frozen=True`を採用する
* `candidate_event`フィールドに`RetryCandidateEvent`をそのまま保持する
  ことで、`run_id` / `candidate` / `source_event`への既存のアクセス経路
  （`candidate_event.run_id`等）をそのまま維持しつつ、分解・変換を行わない
  （v3.7.0 Design Decision #3・v3.8.0 Design Decision #2の方針を踏襲）
* `dispatchable`を独立したフィールドとして持つことで、呼び出し元が
  「Dispatch対象として整理された全件」と「実際にDispatch可能と判定された
  件数」を、フィルタ操作なしに区別できる（`[e for e in results if
  e.dispatchable]`という単純なリスト内包表記で絞り込み可能）

### Design Decision #4：通常イベントとRetryイベントの振り分けは二段階構成とする

Charter 8章 Open Question 4に対し、`RetryEventDispatcher`の入力を
`RetryCandidateEvent`のリストに限定し、生の`SchedulerEvent`混在リストは
`RetryManager.dispatch_retry_events()`内で`recognize_retry_events()`
（v3.8.0、無変更）に委譲した後の結果としてのみ受け取る方式を採用する。

* 「振り分け」を1つのコンポーネントに集約せず、既存の`RetryEventConsumer`
  （Job由来 vs Retry候補由来の識別）と新規の`RetryEventDispatcher`
  （Dispatch対象かどうかの整理）という**責務の異なる2段階**として構成する
  ことで、v3.8.0の実装・テストを一切変更せずに本Releaseを追加できる
* `RetryEventDispatcher`が`SchedulerEvent`（および`job_id`の`"retry:"`
  プレフィックス）を一切知らないことにより、`RetryEventConsumer`との
  責務重複（Single Responsibility違反）を構造的に防止する（Charter 12章
  Riskで挙げた懸念への対処）
* 呼び出し元から見ると、`dispatch_retry_events(events)`という単一の
  エントリポイントに生の`SchedulerEvent`リストを渡すだけでよく、
  2段階構成であることを意識する必要はない（4章のとおり内部で
  `recognize_retry_events()`→`dispatch()`の順に自動的に合成される）

### Design Decision #5：`RetryEventDispatcher`にも自動フォールバック方式を採用する

Charter 8章 Open Question 5・6に対し、v3.8.0の`RetryEventConsumer`と同じ
設計判断を踏襲する。`event_dispatcher`引数を省略した場合、
`RetryManager.__init__`が`RetryEventDispatcher()`を自動構築する。
`RetryManager`への委譲は`dispatch_retry_events()`1メソッドのみとする。

* `RetryEventDispatcher`は設定値（Config）を持たず、外部リソースにも
  一切アクセスしないStateless コンポーネントである。v3.8.0の
  `RetryEventConsumer`（Design Decision #5）とまったく同じ理由により、
  「省略時は自動フォールバック」を採用する
* `RetryEventDispatcher`に対になる`NullRetryEventDispatcher`は作らない
  （`RetryEventDispatcher`自体が既に「引数なしで安全に動作する」実装で
  あるため。v3.8.0 Design Decision #5と同じ判断）
* 委譲メソッドは`dispatch_retry_events(events)`1つのみとする。
  `recognize_retry_events()`との合成という性質上、`RetryManager`が
  「認識済みcandidate_eventsを渡してdispatchだけ行う」というAPIを別途
  公開する具体的な必要性は本Release時点でない（将来必要になった場合、
  `RetryEventDispatcher.dispatch()`は既に公開APIとして存在するため、
  `RetryManager`側にAPIを追加するだけで対応可能）

### Design Decision #6：`NullRetryManager.dispatch_retry_events()`は常に空リストを返す

v3.8.0 Design Decision #6と同じ理由により、`NullRetryManager`は
`RetryEventDispatcher`への参照を一切保持せず、`dispatch_retry_events()`は
渡された`events`の中身を検査せずに空リストを返す。

* `dispatch_retry_events()`の戻り値型`list[RetryDispatchEvent]`にも、
  `recognize_retry_events()`と同様「結果種別」を表現するフィールドがない
  ため、`DISABLED`のような特別な値ではなく単純な空リストで表現する
* `RetryEventDispatcher`を構築しない（参照すら持たない）ことで、
  `NullRetryManager`が本Release後も「外部依存を一切持たないダミー実装」
  という既存の性質を維持する

---

## 14. Charter Open Questions への回答

Charter（`docs/design/retry_engine_event_dispatch_charter.md`）8章で
保留した7項目に対する結論。

1. **配置場所**：`retry_engine`パッケージ内の新規ファイル
   `retry_event_dispatcher.py`（案A）。独立パッケージへの切り出しは
   行わない（13章 Design Decision #1）
2. **Dispatch対象の判定基準**：`RetryCandidateEvent.run_id`が空でないかという
   構造的妥当性のみを判定する。優先度・件数上限に基づく選別は本Releaseでは
   導入しない（13章 Design Decision #2）
3. **Dispatch結果の型**：`RetryDispatchEvent(candidate_event, dispatchable)`
   という専用の`frozen dataclass`（13章 Design Decision #3）
4. **「通常イベントとRetryイベントの振り分け」の入力**：`RetryEventDispatcher`
   の入力は`RetryEventConsumer.recognize_all()`が返した後の
   `RetryCandidateEvent`のリストに限定する。生の`SchedulerEvent`混在
   リストは`RetryManager.dispatch_retry_events()`が内部で
   `recognize_retry_events()`に委譲した結果としてのみ扱う
   （13章 Design Decision #4）
5. **`RetryManager`への委譲メソッドの粒度**：`dispatch_retry_events(events)`
   1メソッドのみ（13章 Design Decision #5）
6. **新規コンポーネントの構築責務**：`event_dispatcher`引数省略時は
   `RetryEventDispatcher()`を自動構築する（自動フォールバック方式。
   13章 Design Decision #5）
7. **`NullRetryManager`側の扱い**：同名メソッドを追加し、常に空リストを
   返す（13章 Design Decision #6）

---

## 15. Architecture Review

状態：**Approve with Minor Recommendations**（Claude Codeによる自己点検。
指摘事項は1件、実装をブロックしない）。

### 15.1 レビュー観点別の判定

| # | 観点 | 判定 | 根拠 |
|---|---|---|---|
| 1 | 既存の`RetryManager()` / `from_config()`呼び出しが完全互換か | **互換** | `event_dispatcher`は末尾のデフォルト値付き引数。12章で確認 |
| 2 | Retry実行（`retry()`）の自動呼び出しが構造的に不可能か（重点5） | **不可能** | `RetryEventDispatcher`・`dispatch_retry_events()`のいずれも`self._policy` / `self._executor` / `self._monitor`を参照しない（9.2節） |
| 3 | Retry Queueの更新が構造的に不可能か（重点6） | **不可能** | `RetryEventDispatcher`は`RetryQueueManager`への参照を一切持たない（9.2節） |
| 4 | `dequeue()` / `remove()`の呼び出しが構造的に不可能か（重点7） | **不可能** | 同上。`dispatch_retry_events()`も`self._queue`を参照しない（9.2節） |
| 5 | Dispatch結果の永続化が発生しないか | **発生しない** | `RetryEventDispatcher`はStateless。`RetryDispatchEvent`をキャッシュ・保存しない |
| 6 | RetryCandidateEventをDispatch対象として整理できているか（重点1・3） | **できている** | 7.1節のSequence Diagramのとおり、`RetryEventDispatcher.dispatch()`が`RetryDispatchEvent`のリストを返す |
| 7 | 通常イベントとRetryイベントの振り分け方針が明確か（重点4） | **明確** | 13章 Design Decision #4のとおり、二段階構成（認識→Dispatch）により、通常イベントは第2段階の入力に現れない |
| 8 | `scheduler` / `retry_event_consumer.py`が本Releaseでも無改修か | **無改修** | 3章Package Structureのとおり、変更は`retry_engine`配下2ファイルのみ |
| 9 | 新規の外部パッケージ依存が発生しないか | **発生しない** | `retry_event_dispatcher.py`のimportは`.retry_event_consumer`（`retry_engine`パッケージ内）と標準ライブラリのみ（9.1節） |
| 10 | 循環importが発生しないか | **発生しない** | 新規の依存方向自体が発生しないため、循環の余地がない |
| 11 | Foundation First / SRP / Statelessが守られているか | **守られている** | Foundation First：Dispatch結果を使った実行系は一切追加していない。SRP：`RetryEventDispatcher`は整理のみを担い、認識ロジックとは分離。Stateless：内部状態を持たない |
| 12 | 既存APIとの後方互換性（重点8） | **維持されている** | 12章で確認済み。既存4メソッド（`retry()` / `enqueue_retry()` / `dequeue_retry()` / `recognize_retry_events()`）はいずれも無変更 |
| 13 | `NullRetryManager`が「受け取れるが何もしない」を体現しているか | **体現している** | `dispatch_retry_events()`は`RetryEventDispatcher`を構築・参照せず、常に`[]`を返す（7.4節） |
| 14 | 既存Regressionへの影響がないか | **影響なし** | `RetryManager` / `NullRetryManager`の既存メソッド・コンストラクタはいずれも無変更。新規メソッド1つの追加のみ |

### 15.2 SOLID

* **単一責任（SRP）**：`RetryEventDispatcher`は「認識済みの
  `RetryCandidateEvent`をDispatch対象として整理する」という1つの関心事
  のみを持つ。`RetryManager`は委譲窓口が1つ増えるが、既存の`retry()` /
  `enqueue_retry()` / `dequeue_retry()` / `recognize_retry_events()`と
  同じ「薄い委譲メソッドの集合」という性質を維持する
* **開放閉鎖（OCP）**：既存メソッドに変更を加えず、新規メソッドの追加
  のみで機能を拡張している
* **リスコフの置換（LSP）**：`RetryManager` / `NullRetryManager`とも同名の
  `dispatch_retry_events(events) -> list[RetryDispatchEvent]`を持ち、
  戻り値の型・意味論（「Dispatch対象として整理できたものの一覧」）が
  一貫している（`NullRetryManager`は常に空集合を返す部分集合として
  振る舞う）
* **インターフェース分離（ISP）**：`dispatch_retry_events()`が利用するのは
  `self.recognize_retry_events()`（既存）と`self._event_dispatcher.dispatch()`
  （新規）という2つのみ
* **依存性逆転（DIP）**：`RetryManager`は`RetryEventDispatcher`という
  具象クラスに依存する。プロジェクト全体で一貫している「Null Object
  Patternによるダックタイピングのみで、ABCは導入しない」という既存方針
  の延長である

### 15.3 残された懸念（Minor Recommendations）

1. **`dispatchable`の判定基準が最小限であること（Design Decision #2）**：
   現状は`run_id`の非空チェックのみであり、実運用上の意味のある
   「Dispatch対象かどうか」の判断（優先度・件数上限・重複排除等）は
   一切行わない。これは意図的なFoundation First判断だが、次Release
   （Retry Execution）で実際に必要となる判定基準が本設計の想定と
   異なる可能性がある。11章 Future Extensionに拡張の余地を明記済みだが、
   Retry Executionの設計段階で再検討することを推奨する

いずれも実装を妨げる指摘ではなく、次Release以降で状況に応じて対応を
検討する事項として整理する。

### 15.4 Foundation First・プロジェクト全体との設計整合性

Charter・ユーザー指示が要求した「認識済みのRetryCandidateEventをDispatch
対象として扱えるようにするが、`RetryManager.retry()`は呼ばない・Retry Queue
は更新しない・`dequeue()` / `remove()`は呼ばない・Queue永続化は対象外」
という範囲に対し、本設計はDispatch結果を消費する処理を一切追加しておらず、
スコープの逸脱はない。v3.3.0〜v3.8.0の「Foundation First・消費者不在の
実行ロジックなし」というパターンを、本Releaseでも踏襲している。

### 15.5 依存方向

```
retry_engine  ── import ──→ scheduler（公開APIのみ：SchedulerEvent型、v3.8.0のまま。本Releaseで新規追加なし）
retry_engine  ── import ──→ retry_queue（v3.2.0のまま、無改修）
retry_engine  ── import ──→ workflow_engine（v3.0.0のまま、無改修）
retry_engine  ── import ──→ workflow_monitor（v3.0.0のまま、無改修）

scheduler                ── import ──→ retry_scheduler_decision（v3.6.0のまま、無改修）
scheduler                ── import ──→ retry_scheduler_source（v3.4.0のまま、無改修）
retry_scheduler_decision ── import ──→ retry_scheduler_source（v3.5.0のまま、無改修）
retry_scheduler_source   ── import ──→ retry_queue（v3.3.0のまま、無改修）
```

`retry_engine`パッケージ内部では、新たに
`retry_manager.py → retry_event_dispatcher.py`という依存が追加されるが、
これは既存の`retry_manager.py → retry_event_consumer.py`（v3.8.0）と
同じパッケージ内の依存であり、パッケージ間の新規依存方向ではない。
`scheduler`側（`scheduler → retry_engine`という逆方向）は一切追加されない。

### 15.6 後方互換性

12章で述べたとおり、変更は`RetryManager.__init__` / `from_config()`への
オプション引数（`event_dispatcher`）追加と、既存メソッドに影響しない
新規メソッド1つ・新規ファイル1つの追加のみ。既存の`retry()` /
`enqueue_retry()` / `dequeue_retry()` / `recognize_retry_events()`・
`retry_event_consumer.py` / `retry_config.py` / `retry_executor.py` /
`retry_policy.py` / `retry_request.py` / `retry_result.py`はいずれも
無変更。`scheduler`側もゼロ改修であり、既存呼び出し元への影響はないと
判断する。

### 15.7 総評

Charter・ユーザー指示が要求した重点8項目（責務の配置・Dispatch対象の
判定基準・Dispatch結果の型・通常イベントとRetryイベントの振り分け方針・
`retry()`不使用の保証・Retry Queue不更新の保証・`dequeue()` /
`remove()`不使用の保証・既存APIとの後方互換性）はいずれも設計上
満たされている。Minor Recommendation 1件（15.3節）は実装をブロックする
性質のものではなく、次Release（Retry Execution）の設計段階での検討事項
として記録すれば足りる。

**Approve with Minor Recommendations** と判断する。

---

## 16. Status

- [x] Architecture Design ドラフト作成（本文書、Claude Code作成）
- [x] Architecture Review完了（Claude Codeによる自己点検、Approve with Minor
      Recommendations。指摘事項1件は次Release検討事項として記録済み）
- [ ] ユーザー確認・実装可否判断
- [ ] 実装（本メッセージ時点では未着手）
- [ ] テスト（本メッセージ時点では未着手）
