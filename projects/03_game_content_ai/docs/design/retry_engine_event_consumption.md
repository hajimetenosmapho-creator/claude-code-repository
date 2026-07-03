# v3.8.0 Retry Engine Event Consumption 設計書（Architecture Design）

作成日：2026-07-03
状態：ドラフト（Architecture Review実施済み。ユーザー確認待ち）。
`docs/design/retry_engine_event_consumption_charter.md`（Project Charter、
ユーザー承認済み、2026-07-03）を前提とする。

---

## 1. Architecture Overview

Release 3.7（`docs/design/retry_scheduler_event_integration.md`）までで、以下が
確立した。

* `SchedulerEngine.evaluate()` / `run_due()`が、`RetrySchedulerDecision`の
  選択結果をRetry候補由来の`SchedulerEvent`として出力に含める
  （`job_id="retry:"+run_id`、`metadata={"retry_candidate": 候補オブジェクト}`）
* この`SchedulerEvent`を受け取って何かをする仕組みは、`scheduler`側にも
  `retry_engine`側にも一切存在しない（消費者不在）

本Release（v3.8.0）は、`retry_engine`パッケージに**初めて`scheduler`への依存**を
導入し、`SchedulerEvent`のリストを受け取って「Retry候補由来のものだけを
それと識別する」コンポーネントを新設する。ユーザー指示の6つの設計方針
（新規コンポーネントの配置・データ構造・プレフィックス判定・委譲粒度・
構築責務・NullRetryManagerの扱い）を、Charter 8章 Open Questionsへの
確定回答としてそれぞれ反映する。

```
Scheduler（判断、v2.6.0〜v3.7.0、無改修）          Retry Engine（実行判断、v3.0.0〜v3.2.0）
   │                                                    │
   └── evaluate() / run_due()                           ├── RetryManager
            │                                            │    ├── retry()                 （無改修）
            └── SchedulerEvent 生成                      │    ├── enqueue_retry() /        （無改修）
                 （Job由来 ＋ Retry候補由来）              │    │   dequeue_retry()
                          │                                │    └── recognize_retry_events() ★新設
                          │                                │         │  薄い委譲
                          └───────────────────────────────►│         ▼
                             呼び出し元が SchedulerEvent の  │  RetryEventConsumer ★新設コンポーネント
                             リストをそのまま引数として渡す  │  （retry_engine配下、scheduler依存）
                                                            │
                                                     RetryCandidateEvent ★新設データ構造
                                                     （run_id・candidate・source_event）
```

本Releaseの核心は、「Retry候補由来のSchedulerEventを識別する」という
1つの新しい関心事を、既存の`retry()` / `enqueue_retry()` / `dequeue_retry()`と
**呼び出しグラフ上で完全に独立させたまま**`retry_engine`に追加することである。

---

## 2. Design Policy

Charter 5章 Design Principles、およびユーザー指示の6つの設計方針を、本設計では
以下の形で具体化する。

1. **配置場所（ユーザー指示：まず`retry_engine`内に置く）**：新規ファイル
   `src/retry_engine/retry_event_consumer.py`を追加する（Charter 8章
   Open Question 1、案A）。独立パッケージへの切り出しは行わない
   （13章 Design Decision #1）
2. **認識結果のデータ構造（ユーザー指示：軽量な専用データ構造）**：
   `RetryCandidateEvent`という`frozen=True`の`dataclass`を新設する。
   フィールドは`run_id` / `candidate` / `source_event`の3つのみ
   （13章 Design Decision #2）
3. **`"retry:"`判定（ユーザー指示：`retry_engine`側で定数化。将来`scheduler`側と
   統合できる余地を残す）**：`retry_event_consumer.py`内に
   `RETRY_JOB_ID_PREFIX = "retry:"`を定義する。`scheduler_engine.py`内の
   同名リテラルとは値として重複するが、`scheduler`側の変更は一切行わない
   （Charter Goals 7・Non-Goals）。定数を1箇所（本ファイル冒頭）に集約し、
   将来`scheduler`側が公開定数化した場合に参照先を差し替えやすくする
   （13章 Design Decision #3）
4. **`RetryManager`への委譲（ユーザー指示：最小粒度）**：
   `recognize_retry_events(events) -> list[RetryCandidateEvent]`という
   メソッド1つのみを追加する。`RetrySchedulerSource` / `RetrySchedulerDecision`の
   ように複数粒度（1件用・複数件用・カウント用）を用意しない
   （13章 Design Decision #4）
5. **構築責務（ユーザー指示：後方互換重視で自動フォールバック優先）**：
   `RetryManager.__init__`に`event_consumer: RetryEventConsumer | None = None`を
   追加し、省略時は`RetryEventConsumer()`を自動構築する。
   `RetrySchedulerDecision`（必須DI、Null実装なし）ではなく、
   `RetrySchedulerSource`（省略時は`NullRetrySchedulerSource()`に自動
   フォールバック）に近いパターンを採用する（13章 Design Decision #5）
6. **`NullRetryManager`（ユーザー指示：「受け取れるが何もしない」を維持）**：
   `NullRetryManager`にも同名メソッド`recognize_retry_events(events)`を追加し、
   常に空リストを返す。内部に`RetryEventConsumer`への参照を一切保持しない
   （13章 Design Decision #6）
7. **Foundation First**：認識結果（`RetryCandidateEvent`）を使って何かを
   実行する処理（`retry()`の自動呼び出し等）は一切追加しない（11章）
8. **Single Responsibility**：`RetryEventConsumer`は「`SchedulerEvent`の
   リストからRetry候補由来のものを識別する」ことのみを担う。候補選択ロジック
   自体（`RetrySchedulerDecision`）・Queue管理（`retry_queue`）・実行判断
   （`RetryPolicy`）のいずれも複製・肩代わりしない
9. **Stateless**：`RetryEventConsumer`は内部状態を一切持たない。
   呼び出しごとに渡された`SchedulerEvent`のリストのみから結果を導出する
10. **Backward Compatibility**：`RetryManager()` / `RetryManager.from_config(...)`の
    既存呼び出し（`event_consumer`を渡さない場合）は、本Release後も
    無変更で動作する

---

## 3. Package Structure（変更差分）

```
src/retry_engine/
├── __init__.py             # 変更：新規シンボル（RetryCandidateEvent / RetryEventConsumer）
│                            #        のexport追加。docstring更新
├── retry_event_consumer.py # ★新規：RetryCandidateEvent / RetryEventConsumer
├── retry_manager.py         # ★変更：RetryManager.__init__ に event_consumer 引数追加。
│                            #        recognize_retry_events() を追加。
│                            #        NullRetryManager にも同名メソッドを追加
├── retry_config.py          # 無変更
├── retry_executor.py        # 無変更
├── retry_policy.py          # 無変更
├── retry_request.py         # 無変更
└── retry_result.py          # 無変更

src/scheduler/                 # 全ファイル無改修（v3.7.0のまま）
src/retry_scheduler_decision/  # 全ファイル無改修
src/retry_scheduler_source/    # 全ファイル無改修
src/retry_queue/               # 全ファイル無改修

tests/
└── test_e2e_v3_8_0_retry_engine_event_consumption.py   # 新規
```

変更対象は`retry_engine`配下2ファイル（`retry_event_consumer.py`新規・
`retry_manager.py`変更）と`__init__.py`のみ。`scheduler`側は本Releaseでも
ゼロ改修（v3.7.0のRetry Scheduler Event Integrationと対をなす、受信側のみの変更）。

---

## 4. Public API

### `retry_event_consumer.py`（新規）

```python
"""
Retry Event Consumer（v3.8.0）

RetryCandidateEvent: Retry候補由来のSchedulerEventから認識された結果を表す軽量データ
RetryEventConsumer:   SchedulerEventのリストから、Retry候補由来のものだけを認識するコンポーネント

設計方針:
    - retry_engine が scheduler パッケージへ依存する、本Releaseで初めて追加される
      コンポーネント。依存は SchedulerEvent という単純な dataclass（副作用を持たない
      データ構造）への参照のみに限定し、SchedulerEngine 等の実行系クラスは
      一切importしない。
    - "retry:" という予約プレフィックス（v3.7.0で確定）の判定は、本Releaseでは
      retry_engine 側のモジュール定数 RETRY_JOB_ID_PREFIX として保持する。
      scheduler側（scheduler_engine.py）は同じ文字列をリテラルとして job_id
      生成に使っているが公開定数としてexportしていないため、値としては
      重複定義になる。将来 scheduler 側がこの文字列を公開定数化した場合に
      備え、参照箇所を本ファイル冒頭の1箇所に集約する。
    - RetryEventConsumer はStateless。SchedulerEventのリストを受け取り、
      認識結果のリストを返すだけの純粋関数的なメソッドのみを持つ。
    - Queueの状態を変更する操作（enqueue() / dequeue() / remove()）・
      Retry実行（RetryManager.retry()）への参照は一切持たない。認識のみを行う。
    - 候補オブジェクト（RetryQueueItemの公開属性を持つオブジェクト）は
      分解・変換せず RetryCandidateEvent.candidate にそのまま格納する
      （v3.7.0 Design Decision #3の方針を受信側でも踏襲する）。
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

    def recognize(self, event: SchedulerEvent) -> RetryCandidateEvent | None:
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
from .retry_event_consumer import RetryCandidateEvent, RetryEventConsumer  # ★新規
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
        event_consumer: RetryEventConsumer | None = None,  # ★新規
    ):
        self._policy = policy
        self._executor = executor
        self._monitor = monitor
        self._queue = queue if queue is not None else NullRetryQueueManager()
        self._event_consumer = event_consumer if event_consumer is not None else RetryEventConsumer()  # ★新規

    @classmethod
    def from_config(
        cls,
        retry_config: RetryConfig,
        retry_policy: RetryPolicy,
        workflow_engine_manager: "WorkflowEngineManager | NullWorkflowEngineManager",
        workflow_monitor_manager: "WorkflowMonitorManager | NullWorkflowMonitorManager",
        retry_queue_manager: "RetryQueueManager | NullRetryQueueManager | None" = None,
        event_consumer: RetryEventConsumer | None = None,  # ★新規
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
            event_consumer=event_consumer,  # ★新規
        )

    # retry() / enqueue_retry() / dequeue_retry() / _skip_reason() は無変更（省略）

    def recognize_retry_events(self, events: list[SchedulerEvent]) -> list[RetryCandidateEvent]:
        """
        SchedulerEventのリストから、Retry候補由来のものだけを認識する。
        RetryEventConsumer.recognize_all() への薄い委譲のみを行う。

        retry()（Retry実行）・enqueue_retry() / dequeue_retry()（Queue操作）とは
        呼び出しグラフ上で完全に独立している。認識結果（RetryCandidateEvent）を
        使って自動的に何かを実行する処理はここにはない（自動実行はしない）。
        """
        return self._event_consumer.recognize_all(events)


class NullRetryManager:
    """RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている場合のダミー実装。"""

    _DISABLED_REASON = (
        "Retry Engine is disabled (RETRY_ENGINE_ENABLED=false, "
        "or AI_AGENT_ENABLED/WORKFLOW_ENGINE_ENABLED is not ready)."
    )

    # retry() / enqueue_retry() / dequeue_retry() は無変更（省略）

    def recognize_retry_events(self, events: list[SchedulerEvent]) -> list[RetryCandidateEvent]:
        """
        RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている場合でも、
        認識処理自体はQueue操作・実行を一切伴わない副作用のない読み取りであるため、
        DISABLEDという特別な結果型は用いず、常に空リストを返す
        （「受け取れるが何もしない」）。RetryEventConsumerへの参照は保持しない。
        """
        return []
```

* `RetryManager.__init__` / `from_config()`とも、既存引数の**末尾**に
  デフォルト値付きの`event_consumer`を追加する。既存の位置引数・
  キーワード引数呼び出しはいずれも影響を受けない
* `recognize_retry_events()`は`self._event_consumer.recognize_all(events)`
  という1行のみで完結する（`retry()` / `enqueue_retry()` / `dequeue_retry()`と
  同じ「薄い委譲」の設計言語を踏襲）
* `NullRetryManager.recognize_retry_events()`は`RetryEventConsumer`を
  一切構築・参照せず、リテラルの空リストを返す

### `__init__.py` の公開シンボル

```python
from .retry_config import RetryConfig
from .retry_policy import DEFAULT_TARGET_STATUSES, RetryPolicy
from .retry_request import RetryRequest
from .retry_result import RetryOutcome, RetryResult
from .retry_executor import RetryExecutor
from .retry_event_consumer import RetryCandidateEvent, RetryEventConsumer  # ★新規
from .retry_manager import NullRetryManager, RetryManager

__all__ = [
    "RetryPolicy",
    "DEFAULT_TARGET_STATUSES",
    "RetryConfig",
    "RetryRequest",
    "RetryOutcome",
    "RetryResult",
    "RetryExecutor",
    "RetryCandidateEvent",  # ★新規
    "RetryEventConsumer",   # ★新規
    "RetryManager",
    "NullRetryManager",
]
```

---

## 5. Class Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `SchedulerEngine`（v3.7.0、無改修） | Retry候補由来の`SchedulerEvent`を生成する | 生成した`SchedulerEvent`を`RetryManager`へ届けること |
| `RetryEventConsumer`（本Releaseで新規） | `SchedulerEvent`のリストからRetry候補由来のものを識別・認識する | 実行判断（`RetryPolicy`）・Queue操作・Retry実行・候補選択ロジックの再実装 |
| `RetryManager`（本Releaseで変更） | `RetryEventConsumer`への薄い委譲窓口を持つ（既存の`retry()` / `enqueue_retry()` / `dequeue_retry()`と対等な1メソッドとして追加） | 認識ロジックの再実装／認識結果の自動実行 |
| `NullRetryManager`（本Releaseで変更） | 無効時に安全な空リストを返す | `RetryEventConsumer`の構築・保持 |
| `RetryPolicy` / `RetryExecutor`（v3.0.0、無改修） | Retry可否判定・実行 | イベント認識 |
| `RetryQueueManager`（v3.1.0、無改修） | Queueへの出し入れ・整列 | イベント認識・実行判断 |

`SchedulerEvent`の生成は本Releaseでも`SchedulerEngine`のみが持つ責務のまま
変わらない。`RetryEventConsumer`は「受け取ったものを識別する」ところで
責務が完結し、識別結果をどう使うか（実行・破棄等）には一切関与しない。

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
│ - _event_consumer: RetryEventConsumer           │  ★新設
│───────────────────────────────────────────│
│ + __init__(policy, executor, monitor,           │  ★event_consumer引数を追加
│            queue=None, event_consumer=None)      │
│ + from_config(...) -> RetryManager|              │  ★event_consumer引数を追加
│                        NullRetryManager           │
│ + retry(run_id, attempt=1, dry_run=False)       │  無変更
│     -> RetryResult                               │
│ + enqueue_retry(run_id, workflow_name, ...)     │  無変更
│     -> RetryQueueResult                          │
│ + dequeue_retry() -> RetryQueueResult           │  無変更
│ + recognize_retry_events(events)                │  ★新設
│     -> list[RetryCandidateEvent]                 │
└──────────────────┬────────────────────────┘
                    │ 委譲（recognize_all のみ）
                    ▼
        ┌──────────────────────────┐
        │      RetryEventConsumer       │  ★新設（Stateless）
        │──────────────────────────│
        │ + recognize(event)             │
        │     -> RetryCandidateEvent|None │
        │ + recognize_all(events)        │
        │     -> list[RetryCandidateEvent]│
        └──────────────┬───────────┘
                        │ 生成
                        ▼
        ┌──────────────────────────────┐
        │        RetryCandidateEvent         │  ★新設（frozen dataclass）
        │──────────────────────────────│
        │ + run_id: str                       │
        │ + candidate: Any                    │  （RetryQueueItem由来、分解しない）
        │ + source_event: SchedulerEvent      │  （scheduler.SchedulerEvent）
        └──────────────────────────────┘

┌────────────────────────────────┐
│           NullRetryManager           │
│────────────────────────────────│
│ + retry(...) -> RetryResult          │  無変更（DISABLED）
│ + enqueue_retry(...)                 │  無変更（DISABLED）
│     -> RetryQueueResult              │
│ + dequeue_retry() -> RetryQueueResult│  無変更（DISABLED）
│ + recognize_retry_events(events)     │  ★新設（常に[]）
│     -> list[RetryCandidateEvent]     │
└────────────────────────────────┘
```

`RetryEventConsumer`は`RetryManager`にのみ保持され、`NullRetryManager`は
これを一切参照しない（構築コスト・依存を持たずに「何もしない」を実現する）。

---

## 7. Sequence Diagram

### 7.1 recognize_retry_events()（Retry候補由来のイベントを含む場合）

```
Caller            RetryManager           RetryEventConsumer
  │  events = scheduler_engine.evaluate(jobs, now, retry_limit=2)          │
  │  # events = [SchedulerEvent(job_id="job-a", ...),                     │
  │  #           SchedulerEvent(job_id="retry:run-001", metadata={...}),  │
  │  #           SchedulerEvent(job_id="retry:run-002", metadata={...})]  │
  │                                                                        │
  │  retry_manager.recognize_retry_events(events)                        │
  ├──────────────────►│                                                  │
  │                    │  self._event_consumer.recognize_all(events)     │
  │                    ├───────────────────────────►│                   │
  │                    │                             │ for event in events:│
  │                    │                             │   event.job_id     │
  │                    │                             │     .startswith("retry:")│
  │                    │                             │   → "job-a"は対象外  │
  │                    │                             │   → "retry:run-001"・│
  │                    │                             │     "retry:run-002"は│
  │                    │                             │     RetryCandidateEvent化│
  │                    │◄───────────────────────────┤                   │
  │◄──────────────────┤  [RetryCandidateEvent(run_id="run-001", ...),   │
  │                    │   RetryCandidateEvent(run_id="run-002", ...)]   │
```

### 7.2 recognize_retry_events()（Retry候補由来のイベントを含まない場合）

```
Caller            RetryManager           RetryEventConsumer
  │  events = [SchedulerEvent(job_id="job-a", ...)]  # Job由来のみ         │
  │                                                                        │
  │  retry_manager.recognize_retry_events(events)                        │
  ├──────────────────►│                                                  │
  │                    │  self._event_consumer.recognize_all(events)     │
  │                    ├───────────────────────────►│                   │
  │                    │                             │ job_idが"retry:"で  │
  │                    │                             │ 始まらないため対象外 │
  │                    │◄───────────────────────────┤                   │
  │◄──────────────────┤  []                                              │
```

`retry_decision`がSchedulerEngine側で`None`だった場合（v3.7.0で確立済みの
既存動作）、`evaluate()` / `run_due()`はRetry候補由来のイベントを一切含まない。
その場合でも本メソッドは例外を投げず、空リストを返す（7.2節と同じ経路）。

### 7.3 NullRetryManager.recognize_retry_events()

```
Caller            NullRetryManager
  │  null_manager.recognize_retry_events(events)  # eventsの中身は問わない │
  ├──────────────────►│                                                   │
  │                    │  return []  # RetryEventConsumerへの参照を持たない │
  │◄──────────────────┤  []                                               │
```

`RETRY_ENGINE_ENABLED=false`の場合、Retry Engine自体が無効であるため、
渡された`SchedulerEvent`の中身を検査すること自体を行わない
（`retry()`が`Workflow Monitor`へ問い合わせないのと同じ「ゲートが閉じている
時点で処理をしない」という既存方針の延長）。

---

## 8. Data Flow

```
① 呼び出し元（Composition Root、本Releaseでは未実装）が
   SchedulerEngine.evaluate() / run_due() を呼び出し、SchedulerEvent のリストを得る
   （v3.7.0までで確立済み。本Releaseでは変更しない）
        ↓
② 呼び出し元が、そのリストをそのまま RetryManager.recognize_retry_events(events)
   （または NullRetryManager.recognize_retry_events(events)）へ渡す
   （本Releaseでは、この呼び出し元＝Composition Root自体は実装しない。
   Charter Non-Goals・11章 Future Extension）
        ↓
③ RetryManager は self._event_consumer.recognize_all(events)
   （RetryEventConsumer、本Release新設）へ委譲する
        ↓
④ RetryEventConsumer が各 event.job_id を検査する
   ④-a "retry:" で始まらない場合：無視する（Job由来のSchedulerEventは
        本コンポーネントの関心の外）
   ④-b "retry:" で始まり、かつ metadata["retry_candidate"] が存在する場合：
        candidate.run_id・candidate・event を RetryCandidateEvent に詰めて返す
   ④-c "retry:" で始まるが metadata["retry_candidate"] が存在しない場合
        （通常発生しないが、防御的にNoneを返す。13章 Design Decision #7）：
        無視する
        ↓
⑤ recognize_all() が集めた RetryCandidateEvent のリストを
   recognize_retry_events() の戻り値として返す
        ↓
⑥ ⑤で得られた RetryCandidateEvent を使って何かを判断・実行する処理
   （retry() の自動呼び出し・Queueからの取り出し等）は、本Releaseでは
   一切存在しない（読み取れる＝観測可能になっただけ。11章）
```

`retry_queue`パッケージへのimportは本Releaseのどの段階でも新規に発生しない
（`RetryEventConsumer`は`candidate`オブジェクトの型を`import`せず、
`run_id`という1属性への構造的な期待（Duck Typing）のみに依存する。
9.1節で詳述）。

---

## 9. Boundary（今回入れない境界線）

本Releaseが**構造的に**実行不可能にする操作、および境界維持の方法を明示する。

### 9.1 `retry_engine` が `retry_queue` の型を直接知らない境界

| 確認観点 | 本Releaseでの扱い |
|---|---|
| `retry_event_consumer.py`に`from retry_queue import ...`が存在するか | 存在しない。importするのは`scheduler`（`SchedulerEvent`型のみ）と標準ライブラリ（`dataclasses` / `typing`）のみ |
| `RetryQueueItem`を型ヒントとして使用するか | 使用しない。`RetryCandidateEvent.candidate`の型は`Any`とし、候補オブジェクトの型情報を`retry_event_consumer.py`側で持たない（v3.7.0の`scheduler`側と同じ「型としてはimportしない」方針を受信側でも踏襲） |
| 候補オブジェクトの属性（`workflow_name` / `priority` / `retry_attempt` / `status`）を参照するか | 参照しない。唯一参照する属性は`run_id`（`RetryCandidateEvent.run_id`を組み立てるためだけに使用）。他の属性は候補オブジェクトを`candidate`フィールドにそのまま格納することで、分解・解釈を`retry_engine`側に持ち込まない |
| `run_id`属性への依存はどう扱うか | `scheduler`パッケージ（v3.4.0〜v3.7.0）が既に確立している「候補オブジェクトは`run_id`という属性を持つ」という構造的な期待（Duck Typing）を、`retry_engine`側でも同じ形で踏襲する。`import`文としての依存ではなく、属性アクセスの契約である |

`retry_engine`自体は既に`retry_queue`をimportしている（v3.2.0の
`RetryQueueManager` / `NullRetryQueueManager`）ため、`RetryQueueItem`を
型として直接importすること自体は技術的に可能である。しかし本設計では
あえて`Any`型を採用し、`retry_event_consumer.py`単体では`retry_queue`の
型構造を一切知らない状態を維持する。これは、`RetryEventConsumer`が
「`scheduler`が生成した`SchedulerEvent`を認識する」という責務に純粋に
留まり、Queue側のデータ構造の変更に追随する必要をなくすためである
（13章 Design Decision #2）。

### 9.2 その他の境界

| 操作 | 本Releaseでの扱い | 根拠 |
|---|---|---|
| `RetryQueueManager.dequeue()` | 呼び出し不可 | `RetryEventConsumer`・`recognize_retry_events()`のいずれも`self._queue`（`RetryManager`が保持する既存フィールド）へアクセスしない。`recognize_retry_events()`の実装は`self._event_consumer.recognize_all(events)`の1行のみ |
| `RetryQueueManager.remove()` | 呼び出し不可 | 同上 |
| `RetryManager.retry()`の自動呼び出し | 呼び出し不可 | `recognize_retry_events()`は`self._policy` / `self._executor` / `self._monitor`のいずれも参照しない。認識結果（`RetryCandidateEvent`）を`retry()`へ渡す変換ロジックは本Releaseに一切存在しない |
| Retry Queueへの書き込み（`enqueue`含む） | 呼び出し不可 | `RetryEventConsumer`は`RetryQueueManager`への参照を一切持たない（コンストラクタ引数にも存在しない） |
| Retry Queue・認識結果の永続化 | 対象外 | `RetryEventConsumer`はStateless（`RetryCandidateEvent`を内部にキャッシュしない）。呼び出しのたびに引数で渡された`events`のみから結果を導出する |
| 既存Job判定ループ（`SchedulerEngine._match*`系）への影響 | 発生しない | 本Releaseは`retry_engine`配下のみを変更し、`scheduler`配下は一切変更しない |

Acceptance Criteria（Charter 9章）の「構造的確認」は、上記の表と1対1で
対応する形でテストする（`src/retry_engine/`配下に`dequeue` / `remove` /
`self._queue` / `self._policy` / `self._executor` / `self._monitor`への
参照が`recognize_retry_events()` / `RetryEventConsumer`の実装から
到達しないことをコードレビュー・テストの両面で確認する）。

---

## 10. Configuration

**本Releaseでは新規の環境変数を一切追加しない**（Charter 5章・Goals 7）。

| 環境変数 | デフォルト | 説明 | 本Releaseでの役割 |
|---|---|---|---|
| `RETRY_ENGINE_ENABLED` | `false` | Retry Engine全体の有効/無効（`RetryConfig`、無改修） | `from_config()`が`RetryManager` / `NullRetryManager`のどちらを返すかの既存判断基準（無変更）。`RetryEventConsumer`の有効/無効はこのゲートに紐付かない（`RetryManager`が存在すれば常に有効） |
| `RETRY_QUEUE_ENABLED` | `true` | Retry Queueの有効/無効（`RetryQueueConfig`、無改修） | 本Releaseの変更対象外 |

`RetryEventConsumer`自体には対応するFeature Gate・環境変数を設けない
（Stateless・副作用なしの認識処理であり、`RetrySchedulerDecision`と同じく
「無効化」という概念を持たない。Charter 8章 Open Question 5への回答、
13章 Design Decision #5）。

---

## 11. Future Extension

* **認識結果（`RetryCandidateEvent`）を使った自動Retry実行**：
  `recognize_retry_events()`が返した候補を`RetryQueueManager.dequeue()`で
  実際に取り出し`RetryManager.retry()`へ渡す一連の自動化
  （Charter Non-Goals・本設計書9.2節で明示的に対象外とした領域）
* **実運用のComposition Root**：`SchedulerEngine.run_due()`の結果を
  実際に`RetryManager.recognize_retry_events()`へ渡して回す起動スクリプト
  （例：`scripts/run_scheduler.py`）は引き続き未着手（v3.4.0から持ち越し）
* **`"retry:"`プレフィックス定数の重複解消**：現状`scheduler_engine.py`（文字列
  リテラル）と`retry_event_consumer.py`（`RETRY_JOB_ID_PREFIX`定数）の
  2箇所に同じ値が存在する。将来`scheduler`パッケージがこの文字列を
  公開定数としてexportした場合、`retry_engine`側はそれを参照する形に
  置き換えられる（13章 Design Decision #3）
* **`job_id`プレフィックス衝突の構造的な防止**：v3.7.0から持ち越しの
  既知の限界（`SchedulerJob.job_id`が偶然`"retry:"`から始まる場合の
  区別不能性）。本Releaseでも解消しない
* **`RetryCandidateEvent.candidate`の型安全な公開**：現状`Any`型で
  候補オブジェクトをそのまま保持するのみ。将来`retry_queue`側に
  変換ヘルパーが追加された場合、型を厳密化する余地を残す

---

## 12. Compatibility

* `RetryManager.__init__` / `from_config()`への`event_consumer`オプション引数
  追加のみ。既存の`RetryManager(policy, executor, monitor)` /
  `RetryManager(policy, executor, monitor, queue=...)` /
  `RetryManager.from_config(...)`（新規引数を渡さない場合）は、
  本Release後もまったく同じ結果になる
* `retry()` / `enqueue_retry()` / `dequeue_retry()`（`RetryManager` /
  `NullRetryManager`とも）は1行も変更しない
* `retry_config.py` / `retry_executor.py` / `retry_policy.py` /
  `retry_request.py` / `retry_result.py`は無改修
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
  `retry_queue`配下の全ファイルも無改修
* 新規の環境変数を追加しないため、`.env` / `.env.example`の変更も不要
* 既存の`RetryManager()` / `RetryManager.from_config(...)`呼び出しテスト
  （v3.0.0〜v3.2.0）は無改修のまま全PASSする想定
  （コンストラクタ・`from_config()`のシグネチャ変更は末尾への
  デフォルト値付き引数追加のみであり、位置引数・キーワード引数いずれの
  既存呼び出しにも影響しない）

---

## 13. Design Decisions（設計判断の根拠）

### Design Decision #1：新規コンポーネントは`retry_engine`パッケージ内に配置する

Charter 8章 Open Question 1に対し、ユーザー指示のとおり案A
（`retry_engine`内への配置）を採用する。

* 「Retry EngineがRetryイベントを認識できるようにする」というユーザー指示の
  目的に対し、認識コンポーネントを`RetryManager`と同じパッケージに置くことで、
  責務の所在が直感的になる
* 独立パッケージ化（案B）は、`RetryManager`から見て`retry_queue`
  （v3.2.0）・`scheduler`（本Release、間接的に）に続く3つ目の外部パッケージ
  依存を管理する形になり、現時点でのメリット（`retry_scheduler_source` /
  `retry_scheduler_decision`のような「他のコンポーネントからも再利用される」
  見込み）が薄い。認識コンポーネントは`RetryManager`専属の内部実装として
  扱う方が、本Releaseのスコープ（Foundation First）に合致する
* 将来、認識ロジックが複雑化し他のコンポーネントからも再利用される必要が
  生じた場合、`retry_engine`パッケージ内から独立パッケージへ切り出す
  リファクタリングは可能（現時点で先回りして分離しない）

### Design Decision #2：認識結果は`RetryCandidateEvent`という軽量frozen dataclassとする

Charter 8章 Open Question 2に対し、ユーザー指示のとおり専用データクラスを
新設する。フィールドは`run_id` / `candidate` / `source_event`の3つのみに
絞る。

* `RetryRequest` / `RetryResult`（既存、いずれも`frozen=True`）と同じく
  「1回限りの入出力データ」としての性質を持つため、`frozen=True`を採用する
  （`RetryQueueItem`のようにライフサイクル中に書き換えられる対象ではない）
* `run_id`を独立したフィールドとして持つことで、呼び出し元が
  `candidate.run_id`という属性アクセスに頼らずに済む（`candidate`の型が
  `Any`であるため、呼び出し元にとって`run_id`が型安全にアクセスできる
  唯一のフィールドになる）
* `candidate`（元の候補オブジェクト）と`source_event`（元の`SchedulerEvent`）を
  両方保持することで、将来の消費者（自動Retry実行等）が必要な情報
  （候補の全属性、あるいは元イベントの`execute_time` / `trigger_reason`）に
  後から手を伸ばせる。ただし本Releaseではこれらを一切解釈・加工しない

### Design Decision #3：`"retry:"`判定は`retry_engine`側で独立して定数化する

Charter 8章 Open Question 3に対し、ユーザー指示のとおり、`scheduler`側の
変更を伴わない形（`retry_engine`側での重複定義）を採用する。

* Charter Goals 7「`scheduler`はいずれも本Releaseでも無改修」という制約が
  最優先である。`scheduler`パッケージ側にこの文字列を公開定数として
  追加する案は、たとえ1行の変更であっても`scheduler`への改修に該当し、
  本Releaseのスコープ外になる
* 重複定義という技術的負債は残るが、値は`"retry:"`という単純な文字列であり、
  v3.7.0のDesign Decision #2で確定した規約（変更頻度が低いことが期待される）
  であるため、実害は小さいと判断する
* `RETRY_JOB_ID_PREFIX`という定数名・定義位置を`retry_event_consumer.py`の
  冒頭1箇所に集約することで、将来`scheduler`側が公開定数化した際に
  影響範囲を局所化する（11章 Future Extension）

### Design Decision #4：`RetryManager`への委譲は`recognize_retry_events()`1メソッドのみとする

Charter 8章 Open Question 4に対し、ユーザー指示のとおり最小粒度
（1メソッドのみ）を採用する。

* `RetrySchedulerSource`（`count_pending_retries()` / `list_pending_retries()`の
  2メソッド）・`RetrySchedulerDecision`（`select_candidates()` /
  `select_next_candidate()`の2メソッド）は、いずれも「複数件」と「1件」の
  両方の使用場面を想定していた。しかし本Releaseの認識処理は
  「`SchedulerEvent`のリストを渡して、Retry候補由来のものだけを抜き出す」
  という単一の使用場面のみを想定しており、1件版（例：
  `recognize_single_event(event)`）を`RetryManager`の公開APIとして
  用意する具体的な必要性がない
* `RetryEventConsumer`自体は`recognize()`（1件）と`recognize_all()`
  （複数件）の両方を持つため、将来`RetryManager`側で1件版の委譲メソッドが
  必要になった場合も、`RetryEventConsumer`側の変更なしに追加できる

### Design Decision #5：構築責務は自動フォールバック方式とする

Charter 8章 Open Question 5に対し、ユーザー指示のとおり
「後方互換重視の自動フォールバック」を採用する。`event_consumer`引数を
省略した場合、`RetryManager.__init__`が`RetryEventConsumer()`を自動構築する。

* `RetryEventConsumer`は設定値（Config）を持たず、外部リソース
  （ファイル・DB・ネットワーク）にも一切アクセスしないStateless
  コンポーネントである。`RetrySchedulerDecision`（v3.5.0）が「必須DI・
  Null実装なし」を選んだ理由（`retry_source`という唯一の実質的な入力を
  持ち、それ自体が呼び出し元の構築判断を必要とする）とは異なり、
  `RetryEventConsumer`には呼び出し元が判断すべき構築パラメータが存在しない
  （常に同じ振る舞いになる）
* `RetrySchedulerSource`（v3.4.0、`SchedulerEngine`が省略時に
  `NullRetrySchedulerSource()`へ自動フォールバックする）に近い構築責務の
  性質を持つ。ただし`RetryEventConsumer`には対になる`NullRetryEventConsumer`を
  作らない（`RetryEventConsumer`自体が既に「引数なしで安全に動作する」
  実装であり、Null Object Patternを重ねる必要がないため）
* 既存の`RetryManager(policy, executor, monitor)`という3引数呼び出しは、
  本Release後、`recognize_retry_events()`という新しい能力を暗黙に獲得する
  （Additive）。これは「新しいFeature Gateの追加」ではなく、「常に安全に
  実行できる読み取り専用メソッドが1つ増えた」という扱いであり、
  既存の`RETRY_ENGINE_ENABLED`ゲートの意味論（Workflowを実際に再実行するか
  どうか）とは独立している

### Design Decision #6：`NullRetryManager.recognize_retry_events()`は常に空リストを返す

Charter 8章 Open Question 6に対し、ユーザー指示のとおり
「受け取れるが何もしない」を実装する。`NullRetryManager`は
`RetryEventConsumer`への参照を一切保持せず、`recognize_retry_events()`は
渡された`events`の中身を検査せずに空リストを返す。

* 既存の`retry()` / `enqueue_retry()` / `dequeue_retry()`は、いずれも
  `RetryResult` / `RetryQueueResult`という「結果に`outcome=DISABLED`という
  種別を持つデータクラス」を返す。しかし`recognize_retry_events()`の
  戻り値型`list[RetryCandidateEvent]`には、そのような「結果種別」を
  表現するフィールドがない（`RetryCandidateEvent`は認識結果1件を表す
  データであり、「認識処理全体の成否」を表すものではないため）
* `SchedulerEngine.select_candidates()`が`retry_decision=None`の場合に
  「候補なし」を`DISABLED`のような特別な値ではなく単純な空リスト`[]`で
  表現した（v3.6.0の既存パターン）のと同じ設計判断を踏襲する。
  「認識対象が0件だった」ことと「Retry Engineが無効だから何もしない」
  ことを、呼び出し元から見て同じ`[]`という形で表現し、区別する必要がある
  場合は`RetryManager` / `NullRetryManager`のどちらを保持しているかを
  呼び出し元が把握していることを前提とする（DIの有無＝機能の有効/無効という
  プロジェクト全体の既存の設計言語）
* `RetryEventConsumer`を構築しない（参照すら持たない）ことで、
  `NullRetryManager`が本Release後も「外部依存を一切持たないダミー実装」
  という既存の性質を維持する

### Design Decision #7：`metadata["retry_candidate"]`が存在しない場合は防御的にNoneを返す

`RetryEventConsumer.recognize()`は、`job_id`が`"retry:"`で始まっていても
`metadata["retry_candidate"]`が存在しない場合、`None`を返す（例外を送出しない）。

* v3.7.0の`_build_retry_events()`の実装上、Retry候補由来の`SchedulerEvent`は
  常に`metadata={"retry_candidate": 候補オブジェクト}`という形で生成される
  ため、この分岐は通常到達しない
* しかし`RetryEventConsumer`は`scheduler`パッケージの内部実装
  （`_build_retry_events()`）を直接参照できる立場になく、「`job_id`が
  `"retry:"`で始まる`SchedulerEvent`」という規約のみに依存する。
  規約から外れたデータ（例：手動で組み立てられたテスト用`SchedulerEvent`）が
  渡された場合に例外で落ちるのではなく、安全側（無視する）に倒すことで、
  認識処理自体の堅牢性を高める（Foundation Releaseとしての「安全側に倒す」
  という既存方針、`SchedulerEngine._match()`が不正な`schedule`形式を
  例外送出せずスキップする設計と同じ考え方）

---

## 14. Charter Open Questions への回答

Charter（`docs/design/retry_engine_event_consumption_charter.md`）8章で
保留した6項目に対する結論（いずれもユーザー指示の設計方針をそのまま採用）。

1. **配置場所**：`retry_engine`パッケージ内の新規ファイル
   `retry_event_consumer.py`（案A）。独立パッケージへの切り出しは行わない
   （13章 Design Decision #1）
2. **識別結果の型**：`RetryCandidateEvent(run_id, candidate, source_event)`
   という専用の`frozen dataclass`（13章 Design Decision #2）
3. **判定基準の実装方法**：`retry_engine`側で`RETRY_JOB_ID_PREFIX = "retry:"`
   として独立定数化する。`scheduler`側は無改修のまま
   （13章 Design Decision #3）
4. **`RetryManager`への委譲メソッドの粒度**：`recognize_retry_events(events)`
   1メソッドのみ（13章 Design Decision #4）
5. **新規コンポーネントの構築責務**：`event_consumer`引数省略時は
   `RetryEventConsumer()`を自動構築する（自動フォールバック方式。
   13章 Design Decision #5）
6. **`NullRetryManager`側の扱い**：同名メソッドを追加し、常に空リストを
   返す（13章 Design Decision #6）

---

## 15. Architecture Review

状態：**Approve with Minor Recommendations**（Claude Codeによる自己点検。
指摘事項は2件、いずれも本Releaseの実装をブロックしない）。

### 15.1 レビュー観点別の判定

| # | 観点 | 判定 | 根拠 |
|---|---|---|---|
| 1 | 既存の`RetryManager()` / `from_config()`呼び出しが完全互換か | **互換** | `event_consumer`は末尾のデフォルト値付き引数。12章で確認 |
| 2 | Retry実行（`retry()`）の自動呼び出しが構造的に不可能か | **不可能** | `recognize_retry_events()`・`RetryEventConsumer`のいずれも`self._policy` / `self._executor` / `self._monitor`を参照しない（9.2節） |
| 3 | `dequeue()` / `remove()`の呼び出しが構造的に不可能か | **不可能** | `RetryEventConsumer`は`RetryQueueManager`への参照を一切持たない。`recognize_retry_events()`も`self._queue`を参照しない（9.2節） |
| 4 | Queue更新・永続化が発生しないか | **発生しない** | `RetryEventConsumer`はStateless。`RetryCandidateEvent`をキャッシュ・保存しない |
| 5 | `retry_engine`がRetry候補由来の`SchedulerEvent`を認識できているか | **できている** | 7.1節のSequence Diagramのとおり、`job_id`が`"retry:"`で始まるものだけが`RetryCandidateEvent`として抽出される |
| 6 | `scheduler`が本Releaseでも無改修か | **無改修** | 3章Package Structureのとおり、変更は`retry_engine`配下2ファイルのみ |
| 7 | `retry_engine → scheduler`という新規依存が最小限か | **最小限** | `retry_event_consumer.py`のimportは`SchedulerEvent`型のみ。`SchedulerEngine` / `SchedulerManager`等の実行系クラスは一切importしない（9.1節） |
| 8 | 循環importが発生しないか | **発生しない** | `scheduler`の依存先（`retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue`）はいずれも`retry_engine`をimportしない（Charter 7章で確認済み） |
| 9 | Foundation First / SRP / Stateless / Backward Compatibilityが守られているか | **守られている** | Foundation First：認識のみで実行系は一切追加していない。SRP：`RetryEventConsumer`は識別のみを担う。Stateless：内部状態を持たない。Backward Compatibility：12章で確認済み |
| 10 | `NullRetryManager`が「受け取れるが何もしない」を体現しているか | **体現している** | `recognize_retry_events()`は`RetryEventConsumer`を構築・参照せず、常に`[]`を返す（7.3節） |
| 11 | `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue`が無改修か | **無改修** | 3章のとおり |
| 12 | 既存Regressionへの影響がないか | **影響なし** | `RetryManager` / `NullRetryManager`の既存4メソッド（`retry()` / `enqueue_retry()` / `dequeue_retry()`、コンストラクタ）はいずれも無変更。新規メソッド1つの追加のみ |

### 15.2 SOLID

* **単一責任（SRP）**：`RetryEventConsumer`は「`SchedulerEvent`のリストから
  Retry候補由来のものを識別する」という1つの関心事のみを持つ。`RetryManager`は
  委譲窓口が1つ増えるが、既存の`retry()` / `enqueue_retry()` / `dequeue_retry()`と
  同じ「薄い委譲メソッドの集合」という性質を維持しており、v3.2.0で
  `RetryQueueManager`を追加した際と同型の変化に留まる
* **開放閉鎖（OCP）**：既存の`retry()` / `enqueue_retry()` / `dequeue_retry()`に
  変更を加えず、新規メソッドの追加のみで機能を拡張している
* **リスコフの置換（LSP）**：`RetryManager` / `NullRetryManager`とも同名の
  `recognize_retry_events(events) -> list[RetryCandidateEvent]`を持ち、
  戻り値の型・意味論（「認識できたものの一覧」）が一貫している
  （`NullRetryManager`は常に空集合を返す部分集合として振る舞う）
* **インターフェース分離（ISP）**：`recognize_retry_events()`が利用するのは
  `self._event_consumer.recognize_all()`という単一の既存メソッドのみ
* **依存性逆転（DIP）**：`RetryManager`は`RetryEventConsumer`という具象クラスに
  依存する。これは`RetryQueueManager` / `WorkflowEngineManager` /
  `WorkflowMonitorManager`など、プロジェクト全体で一貫している
  「Null Object Patternによるダックタイピングのみで、ABCは導入しない」
  という既存方針の延長である

### 15.3 残された懸念（Minor Recommendations）

1. **`"retry:"`プレフィックスの重複定義（Design Decision #3）**：
   `scheduler_engine.py`のリテラルと`retry_event_consumer.py`の
   `RETRY_JOB_ID_PREFIX`が同じ値を独立に持つ。どちらか一方だけを変更すると
   認識が壊れるサイレントな結合が生じる。本Releaseでは`scheduler`
   ゼロ改修という制約上やむを得ない選択だが、次Release以降で
   `scheduler`側の公開定数化を検討する余地があることを11章に明記した
2. **`RetryCandidateEvent.candidate`が`Any`型であること**：型安全性は
   犠牲になるが、`retry_engine`が`retry_queue`の内部構造
   （`RetryQueueItem`のフィールド）に依存しないための意図的な選択である
   （9.1節）。将来、認識結果を実際に消費する側（自動Retry実行）が
   現れた時点で、必要な型情報をどこまで公開するか再設計を推奨する

いずれも実装を妨げる指摘ではなく、次Release以降で状況に応じて対応を
検討する事項として整理する。

### 15.4 Foundation First・プロジェクト全体との設計整合性

Charter・ユーザー指示が要求した「Retry Engineがイベントを認識できるように
するが、Queue更新・`dequeue()` / `remove()`・Retry実行開始・Queue永続化・
既存Job判定ループの変更はいずれも行わない」という範囲に対し、本設計は
認識結果を消費する処理を一切追加しておらず、スコープの逸脱はない。
v3.3.0〜v3.7.0の「Foundation First・消費者不在の実行ロジックなし」という
パターンを、今回は受信側（`retry_engine`）でも踏襲している。

### 15.5 依存方向

```
retry_engine  ── import ──→ scheduler（公開APIのみ：SchedulerEvent型） ★本Releaseで新規追加
retry_engine  ── import ──→ retry_queue（v3.2.0のまま、無改修）
retry_engine  ── import ──→ workflow_engine（v3.0.0のまま、無改修）
retry_engine  ── import ──→ workflow_monitor（v3.0.0のまま、無改修）

scheduler                ── import ──→ retry_scheduler_decision（v3.6.0のまま、無改修）
scheduler                ── import ──→ retry_scheduler_source（v3.4.0のまま、無改修）
retry_scheduler_decision ── import ──→ retry_scheduler_source（v3.5.0のまま、無改修）
retry_scheduler_source   ── import ──→ retry_queue（v3.3.0のまま、無改修）
```

`scheduler`側（`scheduler → retry_engine`という逆方向）は一切追加されない。
`scheduler`の依存先（`retry_scheduler_decision` / `retry_scheduler_source` /
`retry_queue`）もいずれも`retry_engine`をimportしないため、循環importの
余地は構造的に存在しない。

### 15.6 後方互換性

12章で述べたとおり、変更は`RetryManager.__init__` / `from_config()`への
オプション引数（`event_consumer`）追加と、既存メソッドに影響しない
新規メソッド1つ・新規ファイル1つの追加のみ。既存の`retry()` /
`enqueue_retry()` / `dequeue_retry()`・`retry_config.py` / `retry_executor.py` /
`retry_policy.py` / `retry_request.py` / `retry_result.py`はいずれも無変更。
`scheduler`側もゼロ改修であり、既存呼び出し元への影響はないと判断する。

### 15.7 総評

Charter・ユーザー指示が要求した重点項目（新規コンポーネントの配置・
軽量データ構造・`"retry:"`判定の定数化・最小粒度の委譲・自動フォールバックの
構築責務・`NullRetryManager`の「受け取れるが何もしない」・Queue更新や
`dequeue()` / `remove()`の不使用・Retry実行開始の対象外・Queue永続化なし・
既存Job判定ループの不変更・Foundation First/SRP/Stateless/Backward
Compatibilityの遵守）はいずれも設計上満たされている。Minor
Recommendations 2件（15.3節）はいずれも実装をブロックする性質のものではなく、
次Release以降の検討事項として記録すれば足りる。

**Approve with Minor Recommendations** と判断する。

---

## 16. Status

- [x] Architecture Design ドラフト作成（本文書、Claude Code作成）
- [x] Architecture Review完了（Claude Codeによる自己点検、Approve with Minor
      Recommendations。指摘事項2件は次Release検討事項として記録済み）
- [ ] ユーザー確認・実装可否判断
- [ ] 実装（本メッセージ時点では未着手）
- [ ] テスト（本メッセージ時点では未着手）
