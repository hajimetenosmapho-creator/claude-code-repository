# v4.0.0 Retry Execution Foundation 設計書（Architecture Design）

作成日：2026-07-06
状態：ドラフト（Architecture Review実施済み。ユーザー確認待ち）。
`docs/design/retry_execution_foundation_charter.md`（Project Charter、
ユーザー承認済み、2026-07-06）を前提とする。

---

## 1. Architecture Overview

Release 3.9（`docs/design/retry_engine_event_dispatch.md`）までで、以下が
確立した。

* `retry_engine`パッケージに`RetryEventDispatcher`が新設され、
  `RetryManager.dispatch_retry_events(events)`が、認識済みの
  `RetryCandidateEvent`を`RetryDispatchEvent`（`candidate_event` /
  `dispatchable`）として整理できるようになった
* `dispatchable`は`candidate_event.run_id`が空でないかという構造的妥当性
  のみを判定する。整理結果（`RetryDispatchEvent`）を使って何かを実行する
  仕組みは、`retry_engine`側に一切存在しない

本Release（v4.0.0）は、`retry_engine`パッケージに**Dispatchの次の段階**
として、`dispatchable=True`の`RetryDispatchEvent`を対象に、初めて
`RetryManager.retry()`を呼び出せるコンポーネントを新設する。ユーザー
指示の重点5項目（RetryManagerの責務分離・単一の実行入口・Queue非依存・
専用Result型・retry_attemptの扱い）を、Charter 8章 Open Questionsへの
確定回答として反映する。

```
Retry Engine（受信・整理・実行判断、v3.0.0〜v3.9.0）
   │
   ├── recognize_retry_events()（v3.8.0、無改修）
   │      → RetryCandidateEvent のリスト
   ├── dispatch_retry_events()（v3.9.0、無改修）
   │      → RetryDispatchEvent のリスト（candidate_event・dispatchable）
   │
   └── execute_dispatchable_retries() ★新設
          │
          ├─► RetryExecutionSelector ★新設（判定：dispatchable=True のみ選別）
          │
          └─► RetryExecutionCoordinator ★新設（実行：retry_fn を呼び出し、結果を集約）
                 │ retry_fn = self.retry（既存、無改修）
                 ▼
             RetryExecutionResult ★新設データ構造（dispatch_event・retry_result）
```

本Releaseの核心は、「`dispatchable=True`と判定された候補だけを実行対象と
認め、既存の`RetryManager.retry()`をそのまま呼び出す」という1つの新しい
関心事を、**判定（Selector）と実行（Coordinator）という2つの責務に
分離した状態**で追加することである。`RetryManager.retry()`自体・
`RetryPolicy` / `RetryExecutor`は一切変更しない（既存の再実行可否判定
ロジックはそのまま活きる）。

---

## 2. Design Options（比較検討）

ユーザー指示の重点1「RetryManagerの責務を増やしすぎないこと。実行判定と
`RetryManager.retry()`呼び出しの分離を含めて比較検討する」に対応し、
3案を比較する。

### 案A：`RetryManager`に新規メソッドを1つ追加するだけ（新規コンポーネントなし）

`RetryManager.execute_dispatchable_retries()`の中で、フィルタリングと
`self.retry()`呼び出しのループを直接書く。

* メリット：ファイル数・クラス数が増えず、実装量が最小
* デメリット：
  * v3.8.0・v3.9.0で確立した「`RetryManager`は薄い委譲のみを行い、
    実際のロジックは専用コンポーネントが持つ」という既存アーキテクチャ
    パターンから逸脱する
  * `RetryManager`が「判定ロジック」と「ループ＋結果集約ロジック」を
    直接抱えることになり、ユーザー指示の重点1（責務を増やしすぎない）
    に反する
  * 将来Retry Policyの導入等で判定ロジックが複雑化した場合、
    `RetryManager`自体を変更する必要が生じ、既存API変更を最小化する
    という設計原則と衝突しやすい

### 案B：判定と実行を1つの新規コンポーネントにまとめる

`RetryExecutionCoordinator`のようなコンポーネント1つが、
「`dispatchable=True`の選別」と「`retry()`呼び出し＋結果集約」の両方を
担う。

* メリット：新規ファイルが1つで済み、v3.8.0（`RetryEventConsumer`のみ）・
  v3.9.0（`RetryEventDispatcher`のみ）と同じ「1Release1コンポーネント」
  という見た目上のシンプルさを保てる
* デメリット：
  * ユーザー指示の重点2「`dispatchable=true`を唯一の実行入口とし、
    判定を一か所に集約できる設計」を満たせるが、「判定」と「実行」が
    同じクラスの同じメソッド内に混在するため、将来Retry Policyが
    判定基準を拡張する際に、実行ロジック（`retry_fn`呼び出し・結果集約）
    まで巻き込んで変更する必要が生じやすい
  * 単体テストの観点でも、「判定だけ」「実行だけ」を独立に検証しにくい

### 案C（採用）：判定（`RetryExecutionSelector`）と実行（`RetryExecutionCoordinator`）を分離する

`RetryExecutionSelector`（`dispatchable=True`のみを選別する、判定に特化した
Statelessコンポーネント）と、`RetryExecutionCoordinator`（選別済みの
`RetryDispatchEvent`を受け取り、`retry_fn`を呼び出して結果を集約する、
実行に特化したStatelessコンポーネント）に分離する。`RetryManager`は
両者への薄い委譲のみを行う。

* メリット：
  * ユーザー指示の重点1・2を最も直接的に満たす。「`dispatchable=true`
    という判定基準」が`RetryExecutionSelector`という1箇所に完全に
    集約され、実行ロジック（`RetryExecutionCoordinator`）はその判定
    基準が何であるかを一切知らない（選別済みリストを受け取るだけ）
  * 将来Retry Policyが「`dispatchable`以外の基準」（優先度・件数上限等）
    を追加する場合、`RetryExecutionSelector`だけを拡張・置換すればよく、
    `RetryExecutionCoordinator`・`RetryManager`は無改修のまま拡張できる
    （Charter・ユーザー指示の「拡張性を維持する」要件に直接応える）
  * `RetryManager.execute_dispatchable_retries()`は「dispatch→select→
    execute」の3行の委譲のみで完結し、`recognize_retry_events()` /
    `dispatch_retry_events()`と同じ「薄い委譲メソッド」という既存の
    性質を維持できる
  * 単体テストで「選別ロジックのみ」「実行ロジックのみ」を独立に
    検証できる
* デメリット：
  * 新規ファイル・新規クラスが案A・案Bより1つ多い（Foundationの規模の
    割に構成要素が増える）
  * `RetryExecutionCoordinator`が`retry_fn`という関数を外部から受け取る
    形になるため、コンストラクタではなくメソッド引数でDIを行うという、
    既存コンポーネント（`RetryEventConsumer` / `RetryEventDispatcher`は
    コンストラクタ引数を取らない）とはやや異なる形になる（4章で詳述）

### 比較表

| 観点 | 案A（メソッド追加のみ） | 案B（統合コンポーネント） | 案C（Selector/Coordinator分離、採用） |
|---|---|---|---|
| RetryManagerの責務 | 増える（判定＋実行ループを直接持つ） | 増えない | 増えない |
| 判定基準の一箇所集約 | 弱い（RetryManager内に埋没） | 満たす | 最も明確に満たす |
| 将来のRetry Policy拡張時の影響範囲 | RetryManager本体 | Coordinator全体（実行ロジックも道連れ） | Selectorのみ |
| 既存アーキテクチャパターン（v3.8.0/v3.9.0）との整合性 | 逸脱する | 整合する | 整合する（責務分離をさらに一歩進める） |
| 新規ファイル数 | 0 | 1 | 2 |
| 単体テストの独立性 | 低い | 中程度 | 高い |

**結論**：案Cを採用する。Foundation規模に対してファイル数がやや増える
デメリットはあるが、ユーザー指示が明示的に要求する「責務を増やしすぎない」
「判定を一か所に集約する」「将来の拡張性を維持する」の3点すべてに対して
最も明確に応えられるため、トレードオフとして妥当と判断する。

---

## 3. Design Policy

Charter 5章 Design Principles、およびユーザー指示の5つの重点項目を、
本設計では以下の形で具体化する。

1. **RetryManagerの責務分離（重点1）**：2章で述べたとおり、判定
   （`RetryExecutionSelector`）と実行（`RetryExecutionCoordinator`）を
   別コンポーネントに分離する（13章 Design Decision #1）
2. **単一の実行入口（重点2）**：`dispatchable=True`かどうかの判定は
   `RetryExecutionSelector.select()`という1箇所のみで行う。
   `RetryExecutionCoordinator`・`RetryManager`のいずれも`dispatchable`
   フィールドを直接参照・再判定しない（13章 Design Decision #2）
3. **Queue非依存（重点3）**：`RetryExecutionSelector` /
   `RetryExecutionCoordinator`のいずれも`RetryQueueManager` /
   `NullRetryQueueManager`への参照を一切持たない（コンストラクタ引数にも
   存在しない）。入力は`RetryDispatchEvent`（Dispatcherが返した情報）
   のみであり、Queueへの読み書きは一切発生しない（9章で詳述）
4. **専用Result型（重点4）**：既存の`RetryResult`（v3.0.0、frozen）は
   一切変更せず、新規の`RetryExecutionResult`（`dispatch_event` /
   `retry_result`の2フィールドのみを持つ軽量`frozen`データクラス）で
   ラップする。これにより「どの`RetryDispatchEvent`から実行されたか」
   という文脈を保持したまま、将来（Retry Queue Update等）の拡張点を
   残す（13章 Design Decision #6）
5. **retry_attemptの扱い（重点5）**：`RetryCandidateEvent.candidate`
   （型は`Any`。実態は`RetryQueueItem`）が持つ`retry_attempt`属性を
   `getattr(candidate, "retry_attempt", 1)`で取得する。`retry_queue`
   パッケージへのimportは発生させず（Queueとの型結合を避ける）、
   属性が存在しない場合は安全側のデフォルト値`1`にフォールバックする
   （13章 Design Decision #5・8章 Open Question 1）
6. **Foundation First**：`RetryExecutionResult`を使って何かをさらに
   実行する処理（Queueへのフィードバック等）は一切追加しない（12章）
7. **Single Responsibility**：`RetryExecutionSelector`は「選別」のみ、
   `RetryExecutionCoordinator`は「実行と結果集約」のみを担う
8. **Stateless**：両コンポーネントとも内部状態を一切持たない。
   `RetryExecutionCoordinator`は`retry_fn`も含めすべてをメソッド引数
   として受け取り、コンストラクタでは何も保持しない（13章 Design
   Decision #4）
9. **Backward Compatibility**：`RetryManager.__init__` /
   `from_config()`に`execution_selector` / `execution_coordinator`
   引数（デフォルト`None`）を追加し、省略時はそれぞれ
   `RetryExecutionSelector()` / `RetryExecutionCoordinator()`に自動
   フォールバックする。既存の`retry()` / `enqueue_retry()` /
   `dequeue_retry()` / `recognize_retry_events()` /
   `dispatch_retry_events()`は1行も変更しない（11章）

---

## 4. Package Structure（変更差分）

```
src/retry_engine/
├── __init__.py                    # 変更：新規シンボルのexport追加。docstring更新
├── retry_event_consumer.py        # 無変更（v3.8.0のまま）
├── retry_event_dispatcher.py      # 無変更（v3.9.0のまま）
├── retry_execution_selector.py    # ★新規：RetryExecutionSelector
├── retry_execution_coordinator.py # ★新規：RetryExecutionResult / RetryExecutionCoordinator
├── retry_manager.py               # ★変更：RetryManager.__init__ に execution_selector /
│                                  #        execution_coordinator 引数追加。
│                                  #        execute_dispatchable_retries() を追加。
│                                  #        NullRetryManager にも同名メソッドを追加
├── retry_config.py                # 無変更
├── retry_executor.py              # 無変更
├── retry_policy.py                # 無変更
├── retry_request.py               # 無変更
└── retry_result.py                # 無変更

src/scheduler/                     # 全ファイル無改修
src/retry_scheduler_decision/      # 全ファイル無改修
src/retry_scheduler_source/        # 全ファイル無改修
src/retry_queue/                   # 全ファイル無改修

tests/
└── test_e2e_v4_0_0_retry_execution_foundation.py   # 新規
```

変更対象は`retry_engine`配下3ファイル（`retry_execution_selector.py`
新規・`retry_execution_coordinator.py`新規・`retry_manager.py`変更）と
`__init__.py`のみ。`scheduler` / `retry_scheduler_decision` /
`retry_scheduler_source` / `retry_queue` / `retry_event_consumer.py` /
`retry_event_dispatcher.py`はいずれも本Releaseでもゼロ改修。

---

## 5. Public API

### `retry_execution_selector.py`（新規）

```python
"""
Retry Execution Selector（v4.0.0）

RetryExecutionSelector: RetryDispatchEventのリストから、dispatchable=Trueのものだけを
                         実行対象として選別するコンポーネント

設計方針:
    - dispatchable=True を「実行対象として扱う」ための唯一の判定基準とする。
      本コンポーネントが、その判定を行う唯一の場所である
      （docs/design/retry_execution_foundation.md 2章・3章 Design Policy 2）。
    - Stateless。RetryDispatchEvent のリストを受け取り、選別結果のリストを返すだけの
      純粋関数的なメソッドのみを持つ。
    - RetryQueueManager 等への参照は一切持たない（コンストラクタ引数にも存在しない）。
"""
from __future__ import annotations

from .retry_event_dispatcher import RetryDispatchEvent


class RetryExecutionSelector:
    """RetryDispatchEventのリストから、実行対象（dispatchable=True）だけを選別するコンポーネント。"""

    def select(self, dispatch_events: list[RetryDispatchEvent]) -> list[RetryDispatchEvent]:
        """dispatchable=Trueのものだけを実行対象として選別する。"""
        return [event for event in dispatch_events if event.dispatchable]
```

### `retry_execution_coordinator.py`（新規）

```python
"""
Retry Execution Coordinator（v4.0.0）

RetryExecutionResult:      1件のRetryDispatchEventに対するretry()呼び出し結果を保持する軽量データ
RetryExecutionCoordinator: 実行対象として選別済みのRetryDispatchEventのリストを受け取り、
                            retry_fn（RetryManager.retry()）を各件に対して呼び出し、
                            結果を集約するコンポーネント

設計方針:
    - Queueに一切依存しない。入力は RetryDispatchEvent（Dispatcherが返した情報）のみで、
      RetryQueueManager への参照・retry_queue パッケージへのimportは一切持たない。
    - retry_fn は呼び出しごとにメソッド引数として受け取り、コンストラクタでは保持しない
      （Stateless。RetryManagerへの逆参照を持たないことで循環参照を避ける。
      docs/design/retry_execution_foundation.md 13章 Design Decision #4）。
    - retry_attempt は candidate_event.candidate から取得する。candidate の型は Any であり、
      retry_attempt 属性を持たない場合はデフォルト値 1 にフォールバックする
      （防御的な設計。v3.8.0 Design Decision #7と同じ設計言語。13章 Design Decision #5）。
    - retry_fn が例外を送出した場合は、そのまま呼び出し元へ伝播させる（fail-fast）。
      本Releaseでは部分失敗時の継続処理は導入しない（13章 Design Decision #7）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .retry_event_dispatcher import RetryDispatchEvent
from .retry_result import RetryResult

RetryFn = Callable[..., RetryResult]


@dataclass(frozen=True)
class RetryExecutionResult:
    """1件のRetryDispatchEventに対するretry()呼び出し結果を保持する軽量データ。"""

    dispatch_event: RetryDispatchEvent
    retry_result: RetryResult


class RetryExecutionCoordinator:
    """選別済みのRetryDispatchEventのリストを対象に、retry_fnを呼び出し結果を集約するコンポーネント。"""

    def execute(
        self,
        dispatch_events: list[RetryDispatchEvent],
        retry_fn: RetryFn,
        dry_run: bool = False,
    ) -> list[RetryExecutionResult]:
        """
        選別済みのRetryDispatchEventのリストについて、それぞれrun_id・attemptを取り出し
        retry_fn(run_id, attempt=attempt, dry_run=dry_run) を呼び出す。結果は
        RetryExecutionResult として dispatch_event と対にして返す。
        """
        results: list[RetryExecutionResult] = []
        for dispatch_event in dispatch_events:
            candidate = dispatch_event.candidate_event.candidate
            attempt = getattr(candidate, "retry_attempt", 1)
            retry_result = retry_fn(
                dispatch_event.candidate_event.run_id, attempt=attempt, dry_run=dry_run
            )
            results.append(RetryExecutionResult(dispatch_event=dispatch_event, retry_result=retry_result))
        return results
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
from .retry_event_dispatcher import RetryDispatchEvent, RetryEventDispatcher
from .retry_execution_coordinator import RetryExecutionCoordinator, RetryExecutionResult  # ★新規
from .retry_execution_selector import RetryExecutionSelector  # ★新規
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
        event_dispatcher: RetryEventDispatcher | None = None,
        execution_selector: RetryExecutionSelector | None = None,        # ★新規
        execution_coordinator: RetryExecutionCoordinator | None = None,  # ★新規
    ):
        self._policy = policy
        self._executor = executor
        self._monitor = monitor
        self._queue = queue if queue is not None else NullRetryQueueManager()
        self._event_consumer = event_consumer if event_consumer is not None else RetryEventConsumer()
        self._event_dispatcher = (
            event_dispatcher if event_dispatcher is not None else RetryEventDispatcher()
        )
        self._execution_selector = (
            execution_selector if execution_selector is not None else RetryExecutionSelector()
        )  # ★新規
        self._execution_coordinator = (
            execution_coordinator if execution_coordinator is not None else RetryExecutionCoordinator()
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
        event_dispatcher: RetryEventDispatcher | None = None,
        execution_selector: RetryExecutionSelector | None = None,        # ★新規
        execution_coordinator: RetryExecutionCoordinator | None = None,  # ★新規
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
            event_dispatcher=event_dispatcher,
            execution_selector=execution_selector,            # ★新規
            execution_coordinator=execution_coordinator,       # ★新規
        )

    # retry() / enqueue_retry() / dequeue_retry() / recognize_retry_events() /
    # dispatch_retry_events() / _skip_reason() は無変更（省略）

    def execute_dispatchable_retries(
        self, events: list[SchedulerEvent], dry_run: bool = False
    ) -> list[RetryExecutionResult]:
        """
        SchedulerEventのリストから、Retry候補由来のものを認識・Dispatch対象として整理した
        うえで、dispatchable=Trueのものだけを選別し、それぞれについてretry()を呼び出す。

        3段階の委譲のみで完結する：
            1. self.dispatch_retry_events(events)（v3.9.0、無変更）
            2. self._execution_selector.select(dispatch_events)（新規、判定を1箇所に集約）
            3. self._execution_coordinator.execute(selected, retry_fn=self.retry, dry_run=dry_run)
               （新規、実行と結果集約）

        Retry Queueの更新（enqueue_retry() / dequeue_retry()）・
        RetryQueueManager.dequeue() / remove()とは呼び出しグラフ上で完全に独立している。
        """
        dispatch_events = self.dispatch_retry_events(events)
        selected = self._execution_selector.select(dispatch_events)
        return self._execution_coordinator.execute(selected, retry_fn=self.retry, dry_run=dry_run)


class NullRetryManager:
    """RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている場合のダミー実装。"""

    _DISABLED_REASON = (
        "Retry Engine is disabled (RETRY_ENGINE_ENABLED=false, "
        "or AI_AGENT_ENABLED/WORKFLOW_ENGINE_ENABLED is not ready)."
    )

    # retry() / enqueue_retry() / dequeue_retry() / recognize_retry_events() /
    # dispatch_retry_events() は無変更（省略）

    def execute_dispatchable_retries(
        self, events: list[SchedulerEvent], dry_run: bool = False
    ) -> list[RetryExecutionResult]:
        """
        RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている場合、
        実行自体を一切行わず常に空リストを返す（「受け取れるが何もしない」）。
        RetryExecutionSelector / RetryExecutionCoordinatorへの参照は保持しない。
        """
        return []
```

* `RetryManager.__init__` / `from_config()`とも、既存引数の**末尾**に
  デフォルト値付きの`execution_selector` / `execution_coordinator`を
  追加する。既存の位置引数・キーワード引数呼び出しはいずれも影響を受けない
* `execute_dispatchable_retries()`は`self.dispatch_retry_events(events)`
  （既存メソッドの呼び出し）→`self._execution_selector.select(...)`
  （新規委譲）→`self._execution_coordinator.execute(..., retry_fn=self.retry, ...)`
  （新規委譲）の3行のみで完結する
* `NullRetryManager.execute_dispatchable_retries()`は`RetryExecutionSelector` /
  `RetryExecutionCoordinator`を一切構築・参照せず、リテラルの空リストを返す

### `__init__.py` の公開シンボル

```python
from .retry_config import RetryConfig
from .retry_policy import DEFAULT_TARGET_STATUSES, RetryPolicy
from .retry_request import RetryRequest
from .retry_result import RetryOutcome, RetryResult
from .retry_executor import RetryExecutor
from .retry_event_consumer import RetryCandidateEvent, RetryEventConsumer
from .retry_event_dispatcher import RetryDispatchEvent, RetryEventDispatcher
from .retry_execution_selector import RetryExecutionSelector  # ★新規
from .retry_execution_coordinator import RetryExecutionCoordinator, RetryExecutionResult  # ★新規
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
    "RetryDispatchEvent",
    "RetryEventDispatcher",
    "RetryExecutionSelector",       # ★新規
    "RetryExecutionCoordinator",    # ★新規
    "RetryExecutionResult",         # ★新規
    "RetryManager",
    "NullRetryManager",
]
```

---

## 6. Class Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryEventDispatcher`（v3.9.0、無改修） | `RetryCandidateEvent`をDispatch対象として整理する（`dispatchable`の算出） | 実行対象の選別・実行・Queue操作 |
| `RetryExecutionSelector`（本Releaseで新規） | `RetryDispatchEvent`のリストから`dispatchable=True`のものだけを選別する（実行対象の唯一の判定箇所） | 実行（`retry()`呼び出し）・結果集約・Queue操作 |
| `RetryExecutionCoordinator`（本Releaseで新規） | 選別済みの`RetryDispatchEvent`について`retry_fn`を呼び出し、結果を`RetryExecutionResult`として集約する | 実行対象かどうかの判定（`dispatchable`の再解釈）・Queue操作・Retry可否判定（`RetryPolicy`はretry_fn内部でそのまま適用される） |
| `RetryManager`（本Releaseで変更） | `RetryExecutionSelector` / `RetryExecutionCoordinator`への薄い委譲窓口を持つ（`dispatch_retry_events()`との合成のみ） | 実行ロジックの再実装／実行結果の自動的なQueueフィードバック |
| `RetryPolicy` / `RetryExecutor`（v3.0.0、無改修） | Retry可否判定・実行（`retry()`内部で引き続き使用される） | イベント認識・Dispatch・実行対象の選別 |
| `RetryQueueManager`（v3.1.0、無改修） | Queueへの出し入れ・整列 | イベント認識・Dispatch・実行対象の選別・実行 |

`RetryExecutionSelector`と`RetryExecutionCoordinator`は、「`dispatchable`
かどうか」（判定）と「`retry_fn`を呼び出して結果を集める」（実行）という
異なる関心事を、それぞれ独立したコンポーネントとして担う。両者は
`RetryManager.execute_dispatchable_retries()`内での呼び出し順序
（選別→実行）によってのみ連携し、互いを直接参照しない。

---

## 7. Class Diagram

```
┌─────────────────────────────────────────────────┐
│                     RetryManager                       │
│─────────────────────────────────────────────────│
│ - _policy / _executor / _monitor / _queue              │  無変更
│ - _event_consumer: RetryEventConsumer                  │  無変更（v3.8.0）
│ - _event_dispatcher: RetryEventDispatcher              │  無変更（v3.9.0）
│ - _execution_selector: RetryExecutionSelector          │  ★新設
│ - _execution_coordinator: RetryExecutionCoordinator    │  ★新設
│─────────────────────────────────────────────────│
│ + __init__(..., execution_selector=None,               │  ★引数追加
│            execution_coordinator=None)                  │
│ + from_config(...)                                      │  ★引数追加
│ + retry(run_id, attempt=1, dry_run=False)               │  無変更
│     -> RetryResult                                       │
│ + recognize_retry_events(events)                        │  無変更（v3.8.0）
│     -> list[RetryCandidateEvent]                         │
│ + dispatch_retry_events(events)                          │  無変更（v3.9.0）
│     -> list[RetryDispatchEvent]                          │
│ + execute_dispatchable_retries(events, dry_run=False)   │  ★新設
│     -> list[RetryExecutionResult]                        │
└──────────────────────┬──────────────────────────┘
                        │ 委譲①：select                       │ 委譲②：execute（retry_fn=self.retry）
                        ▼                                      ▼
        ┌───────────────────────────┐        ┌────────────────────────────────┐
        │   RetryExecutionSelector       │        │      RetryExecutionCoordinator      │
        │───────────────────────────│        │────────────────────────────────│
        │ + select(dispatch_events)      │        │ + execute(dispatch_events,           │
        │     -> list[RetryDispatchEvent] │──────► │           retry_fn, dry_run=False)   │
        │ （dispatchable=True のみ抽出） │  選別済み │     -> list[RetryExecutionResult]    │
        └───────────────────────────┘  リスト  └────────────────┬───────────────┘
                                                                  │ 生成
                                                                  ▼
                                                  ┌───────────────────────────────┐
                                                  │        RetryExecutionResult        │  ★新設（frozen dataclass）
                                                  │───────────────────────────────│
                                                  │ + dispatch_event: RetryDispatchEvent │  （v3.9.0、分解しない）
                                                  │ + retry_result: RetryResult          │  （v3.0.0、分解しない）
                                                  └───────────────────────────────┘

┌────────────────────────────────────┐
│              NullRetryManager             │
│────────────────────────────────────│
│ + retry(...) -> RetryResult                │  無変更（DISABLED）
│ + recognize_retry_events(events)           │  無変更（v3.8.0、常に[]）
│ + dispatch_retry_events(events)            │  無変更（v3.9.0、常に[]）
│ + execute_dispatchable_retries(events, ...) │  ★新設（常に[]）
│     -> list[RetryExecutionResult]           │
└────────────────────────────────────┘
```

`RetryExecutionSelector` / `RetryExecutionCoordinator`はいずれも
`RetryManager`にのみ保持され、`NullRetryManager`はこれらを一切参照しない。
`RetryExecutionCoordinator`は`RetryManager`への参照（`retry_fn`）を
コンストラクタでは保持せず、`execute()`呼び出しのたびに引数として受け取る
（循環参照を避け、Stateless性を維持する。13章 Design Decision #4）。

---

## 8. Sequence Diagram

### 8.1 execute_dispatchable_retries()（dispatchable=Trueの候補が実際にRetryされる場合）

```
Caller       RetryManager   RetryExecutionSelector   RetryExecutionCoordinator
  │  events = [SchedulerEvent(job_id="retry:run-001", ...)]                                │
  │                                                                                          │
  │  retry_manager.execute_dispatchable_retries(events)                                    │
  ├────────►│                                                                               │
  │         │ dispatch_events = self.dispatch_retry_events(events)                          │
  │         │  # [RetryDispatchEvent(candidate_event=..., dispatchable=True)]               │
  │         │                                                                                │
  │         │ self._execution_selector.select(dispatch_events)                             │
  │         ├──────────────────────────►│                                                  │
  │         │                            │ dispatchable=True のみ残す                        │
  │         │◄──────────────────────────┤                                                  │
  │         │ [RetryDispatchEvent(..., dispatchable=True)]                                  │
  │         │                                                                                │
  │         │ self._execution_coordinator.execute(selected, retry_fn=self.retry)            │
  │         ├───────────────────────────────────────────────────►│                        │
  │         │                                                     │ attempt = candidate      │
  │         │                                                     │   .retry_attempt         │
  │         │                                                     │ retry_fn("run-001",      │
  │         │                                                     │   attempt=1, dry_run=False)│
  │         │◄─── self.retry("run-001", attempt=1, dry_run=False) が呼ばれる（既存メソッド）──┤
  │         │  RetryResult(outcome=RETRIED, ...)                                             │
  │         │                                                     │◄────────────────────────┤
  │         │                                                     │ RetryExecutionResult生成 │
  │         │◄───────────────────────────────────────────────────┤                        │
  │◄────────┤  [RetryExecutionResult(dispatch_event=..., retry_result=RetryResult(RETRIED))]│
```

### 8.2 execute_dispatchable_retries()（dispatchable=Falseの候補は実行されない場合）

```
Caller       RetryManager   RetryExecutionSelector   RetryExecutionCoordinator
  │  # RetryCandidateEvent.run_id が空の防御的なケース                                       │
  │  retry_manager.execute_dispatchable_retries(events)                                     │
  ├────────►│                                                                                │
  │         │ dispatch_events = [RetryDispatchEvent(..., dispatchable=False)]                │
  │         │ self._execution_selector.select(dispatch_events)                              │
  │         ├──────────────────────────►│                                                   │
  │         │                            │ dispatchable=False は除外                          │
  │         │◄──────────────────────────┤                                                   │
  │         │ []                                                                             │
  │         │ self._execution_coordinator.execute([], retry_fn=self.retry)                   │
  │         ├───────────────────────────────────────────────────►│（空リストのため何も呼ばない）│
  │         │◄───────────────────────────────────────────────────┤                         │
  │◄────────┤  []                                                                            │
```

`dispatchable=False`の候補に対しては、`self.retry()`（＝
`WorkflowMonitorManager.get_status()` / `RetryPolicy.should_retry()` /
`RetryExecutor.execute()`を含む一連の既存処理）が一切呼び出されない
（`RetryExecutionSelector`の時点で除外されるため）。

### 8.3 NullRetryManager.execute_dispatchable_retries()

```
Caller       NullRetryManager
  │  null_manager.execute_dispatchable_retries(events)  # eventsの中身は問わない │
  ├────────►│                                                                    │
  │         │ return []  # RetryExecutionSelector / RetryExecutionCoordinatorへの参照を持たない │
  │◄────────┤  []                                                                │
```

---

## 9. Data Flow

```
① 呼び出し元（Composition Root、本Releaseでは未実装）が SchedulerEvent の
   リストを RetryManager.execute_dispatchable_retries(events)
   （または NullRetryManager.execute_dispatchable_retries(events)）へ渡す
        ↓
② RetryManager は self.dispatch_retry_events(events)（v3.9.0、無変更）へ
   委譲し、RetryDispatchEvent のリスト（candidate_event・dispatchable）を得る
        ↓
③ RetryManager は ②で得た RetryDispatchEvent のリストを
   self._execution_selector.select(dispatch_events)
   （RetryExecutionSelector、本Release新設）へ委譲する
        ↓
④ RetryExecutionSelector が dispatchable=True のものだけを抽出する
   （dispatchable=False のものはここで実行対象から除外され、
   以降のステップには一切現れない）
        ↓
⑤ RetryManager は ④で得た選別済みリストを
   self._execution_coordinator.execute(selected, retry_fn=self.retry, dry_run=dry_run)
   （RetryExecutionCoordinator、本Release新設）へ委譲する
        ↓
⑥ RetryExecutionCoordinator が各 dispatch_event について
   candidate_event.candidate.retry_attempt（存在しない場合は1）を取得し、
   retry_fn(candidate_event.run_id, attempt=attempt, dry_run=dry_run) を呼び出す
   （retry_fn の実体は RetryManager.retry()、無変更）
        ↓
⑦ RetryManager.retry() が既存どおり Read Before Retry・RetryPolicy判定・
   RetryExecutor.execute() を行い、RetryResult を返す（本Releaseでの変更なし）
        ↓
⑧ RetryExecutionCoordinator が ⑦の RetryResult を dispatch_event と対にして
   RetryExecutionResult を生成し、リストに集約する
        ↓
⑨ execute_dispatchable_retries() の戻り値として ⑧のリストを返す
        ↓
⑩ ⑨で得られた RetryExecutionResult を使って Retry Queue を更新する処理
   （enqueue_retry() / dequeue_retry() / RetryQueueManager.dequeue() /
   remove() の呼び出し、実行結果のQueueへのフィードバック）は、
   本Releaseでは一切存在しない（Foundation First。11章）
```

`retry_queue`パッケージへのimportは本Releaseのどの段階でも新規に発生
しない。`RetryExecutionSelector` / `RetryExecutionCoordinator`はいずれも
`retry_engine`パッケージ内部の型（`RetryDispatchEvent` / `RetryResult`）
のみをimportし、外部パッケージへの新規importは発生しない。

---

## 10. Boundary（今回入れない境界線）

本Releaseが**構造的に**実行不可能にする操作、および境界維持の方法を明示
する（ユーザー指示の重点3「Queue非依存」を含む）。

### 10.1 `RetryExecutionSelector` / `RetryExecutionCoordinator` が新規の外部パッケージ依存を持たない境界

| 確認観点 | 本Releaseでの扱い |
|---|---|
| `retry_execution_selector.py`に`from retry_queue import ...`が存在するか | 存在しない。importは`.retry_event_dispatcher`（`retry_engine`パッケージ内）のみ |
| `retry_execution_coordinator.py`に`from retry_queue import ...`が存在するか | 存在しない。importは`.retry_event_dispatcher` / `.retry_result`（いずれも`retry_engine`パッケージ内）と標準ライブラリ（`dataclasses` / `typing`）のみ |
| `RetryExecutionCoordinator`が`RetryQueueManager` / `NullRetryQueueManager`型を参照するか | しない。`candidate`は型`Any`のまま扱い、`getattr()`による属性アクセスのみを行う（`RetryQueueItem`型そのものをimportしない） |

### 10.2 実行・Queue操作に関する境界（重点3）

| 操作 | 本Releaseでの扱い | 根拠 |
|---|---|---|
| Retry Queueへの書き込み（`enqueue`含む） | 呼び出し不可 | `RetryExecutionSelector` / `RetryExecutionCoordinator`はいずれも`RetryQueueManager` / `NullRetryQueueManager`への参照を一切持たない（コンストラクタが引数を取らない） |
| `RetryQueueManager.dequeue()` | 呼び出し不可 | 同上。`execute_dispatchable_retries()`も`self._queue`を一切参照しない |
| `RetryQueueManager.remove()` | 呼び出し不可 | 同上 |
| `RetryExecutionResult`の永続化 | 対象外 | `RetryExecutionCoordinator`はStateless（`RetryExecutionResult`を内部にキャッシュしない）。呼び出しのたびに引数で渡された`dispatch_events`のみから結果を導出する |
| `dispatchable`判定の重複・再実装 | 発生しない | `RetryExecutionCoordinator`は`dispatchable`フィールドを一切参照しない。選別は`RetryExecutionSelector`の時点で完了しており、`execute()`に渡される時点で全件`dispatchable=True`であることが構造的に保証される |
| 既存Job判定ループ（`SchedulerEngine._match*`系）・`RetryEventConsumer` / `RetryEventDispatcher`への影響 | 発生しない | 本Releaseは`retry_engine`配下（新規2ファイル・`retry_manager.py`・`__init__.py`）のみを変更する |

Acceptance Criteria（Charter 9章）の「構造的確認」は、上記の表と1対1で
対応する形でテストする（`RetryExecutionSelector` / `RetryExecutionCoordinator`
のソースコードに`self._queue` / `RetryQueueManager` /
`NullRetryQueueManager`への参照が存在しないことをコードレビュー・
Spyオブジェクトによるテストの両面で確認する）。

---

## 11. Configuration

**本Releaseでは新規の環境変数を一切追加しない**（Charter 5章・Goals 6）。

| 環境変数 | デフォルト | 説明 | 本Releaseでの役割 |
|---|---|---|---|
| `RETRY_ENGINE_ENABLED` | `false` | Retry Engine全体の有効/無効（`RetryConfig`、無改修） | `from_config()`が`RetryManager` / `NullRetryManager`のどちらを返すかの既存判断基準（無変更）。`RetryExecutionSelector` / `RetryExecutionCoordinator`の有効/無効はこのゲートに紐付かない（`RetryManager`が存在すれば常に有効） |
| `RETRY_QUEUE_ENABLED` | `true` | Retry Queueの有効/無効（`RetryQueueConfig`、無改修） | 本Releaseの変更対象外 |

`RetryExecutionSelector` / `RetryExecutionCoordinator`自体には対応する
Feature Gate・環境変数を設けない（Stateless・副作用の起点ではなく、
既存`retry()`の呼び出し窓口にすぎないため。v3.8.0・v3.9.0と同じ判断）。

---

## 12. Future Extension

* **Retry Queue Update**：`RetryExecutionResult`（本Release新設）が持つ
  `dispatch_event.candidate_event.candidate`（`RetryQueueItem`相当）を
  使って、実行結果を`RetryQueueManager.dequeue()` / `remove()`へ
  フィードバックする自動化。本Releaseで`RetryExecutionResult`が
  `dispatch_event`を保持したまま返す設計にしているのは、この将来Releaseが
  「どのQueue項目に対する結果か」を追加の突き合わせなしに参照できるように
  するため（Charter Non-Goals・本設計書10章で明示的に対象外とした領域）
* **Retry Policyによる選別基準の拡張**：優先度・件数上限に基づく選別を
  導入する場合、`RetryExecutionSelector.select()`のみを拡張・置換すれば
  よい（`RetryExecutionCoordinator` / `RetryManager`は無改修のまま拡張
  可能。2章 案C・13章 Design Decision #3）
* **部分失敗時の継続処理**：現状`RetryExecutionCoordinator.execute()`は
  `retry_fn`が例外を送出した場合、即座に呼び出し元へ伝播させる
  （fail-fast）。将来、複数件のうち一部が失敗しても残りを処理し続ける
  必要が生じた場合、`execute()`内に例外捕捉・結果への反映ロジックを
  追加する拡張余地を残す（13章 Design Decision #7）
* **`retry_attempt`取得方法の正式な型定義**：現状`getattr(candidate,
  "retry_attempt", 1)`という緩やかなダックタイピングに依存している。
  将来、`RetryCandidateEvent` / `RetryDispatchEvent`に`retry_attempt`を
  明示的なフィールドとして追加する（v3.8.0・v3.9.0の`frozen dataclass`を
  変更する）ことで、より型安全にする余地がある。本Releaseではこれら
  既存データクラスへの変更を避けるため導入しない（8章 Open Question 1）
* **実運用のComposition Root**：`SchedulerEngine.run_due()`の結果を
  実際に`RetryManager.execute_dispatchable_retries()`へ渡して回す
  起動スクリプトは引き続き未着手（v3.4.0から持ち越し）
* **`RetryExecutionCoordinator`のバッチ実行最適化**：現状は1件ずつ
  順番に`retry_fn`を呼び出す単純なループ。将来、大量件数に対する
  並列実行等が必要になった場合の拡張余地を残す（本Releaseでは導入しない）

---

## 13. Compatibility

* `RetryManager.__init__` / `from_config()`への`execution_selector` /
  `execution_coordinator`オプション引数追加のみ。既存の
  `RetryManager(policy, executor, monitor)` /
  `RetryManager(policy, executor, monitor, queue=...)` /
  `RetryManager(policy, executor, monitor, event_consumer=...)` /
  `RetryManager(policy, executor, monitor, event_dispatcher=...)` /
  `RetryManager.from_config(...)`（新規引数を渡さない場合）は、
  本Release後もまったく同じ結果になる
* `retry()` / `enqueue_retry()` / `dequeue_retry()` /
  `recognize_retry_events()` / `dispatch_retry_events()`
  （`RetryManager` / `NullRetryManager`とも）は1行も変更しない
* `retry_event_consumer.py` / `retry_event_dispatcher.py` /
  `retry_config.py` / `retry_executor.py` / `retry_policy.py` /
  `retry_request.py` / `retry_result.py`は無改修
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
  `retry_queue`配下の全ファイルも無改修
* 新規の環境変数を追加しないため、`.env` / `.env.example`の変更も不要
* 既存の`RetryManager()` / `RetryManager.from_config(...)`呼び出しテスト
  （v3.0.0〜v3.9.0）は無改修のまま全PASSする想定（コンストラクタ・
  `from_config()`のシグネチャ変更は末尾へのデフォルト値付き引数追加のみ
  であり、位置引数・キーワード引数いずれの既存呼び出しにも影響しない）

---

## 14. Design Decisions（設計判断の根拠）

### Design Decision #1：新規コンポーネントは`retry_engine`パッケージ内の2ファイルに分離配置する

Charter 8章 Open Question 1・2に対し、`retry_execution_selector.py`
（`RetryExecutionSelector`）と`retry_execution_coordinator.py`
（`RetryExecutionResult` / `RetryExecutionCoordinator`）の2ファイルに
分離する（2章 案C）。

* v3.8.0（`RetryEventConsumer`）・v3.9.0（`RetryEventDispatcher`）は
  それぞれ1Release1ファイルだったが、本Releaseは「判定」と「実行」
  という異なる関心事を1つのReleaseで同時に追加するため、単一ファイルに
  まとめると責務混在のリスクがある（2章の比較検討を参照）
* `RetryExecutionCoordinator`は既存の`RetryExecutor`（v3.0.0、
  `WorkflowEngineManager.run()`を実際に呼ぶ実行系）と役割が異なるため、
  混同を避ける名称とした（`RetryExecutor`＝Workflow Engineへの実行、
  `RetryExecutionCoordinator`＝`RetryDispatchEvent`を起点とした
  `RetryManager.retry()`呼び出しの束ね役）

### Design Decision #2：`dispatchable=True`の判定は`RetryExecutionSelector`のみが行う

Charter 8章 Open Questionに対し、ユーザー指示の重点2（単一の実行入口）に
基づき、`dispatchable`フィールドを参照する箇所を
`RetryExecutionSelector.select()`の1メソッドのみに限定する。

* `RetryExecutionCoordinator`・`RetryManager`は`dispatchable`フィールド
  を一切参照しない。`execute()`に渡された時点で全件が実行対象である
  ことが、型ではなく**呼び出しグラフの構造**によって保証される
* 将来、選別基準が複雑化した場合でも、変更箇所は
  `RetryExecutionSelector`のみに閉じる（12章 Future Extension）

### Design Decision #3：`RetryManager`は「dispatch → select → execute」の3行の委譲のみを行う

2章の比較検討（案A・案Bとの比較）で述べたとおり、`RetryManager`に
判定ロジック・実行ループを直接書かず、既存の薄い委譲メソッド
（`recognize_retry_events()` / `dispatch_retry_events()`）と同じ性質を
維持する。

### Design Decision #4：`RetryExecutionCoordinator`は`retry_fn`をメソッド引数として受け取り、コンストラクタでは保持しない

Charter 8章 Open Question・ユーザー指示の重点3（Queue非依存、および
Stateless性）に対応する。

* `RetryExecutionCoordinator`が`RetryManager`インスタンスへの参照を
  コンストラクタで保持する設計も検討したが、その場合`RetryManager`
  自身への逆参照を`RetryManager.__init__`内で組み立てる必要が生じ
  （`self`をまだ構築中の`__init__`内で自分自身の一部として渡す形になり
  不自然）、DIのタイミングが複雑になる
* `execute(dispatch_events, retry_fn, dry_run)`のように呼び出し時に
  `retry_fn=self.retry`を渡す形にすることで、`RetryExecutionCoordinator`
  はどのクラスの`retry`メソッドか一切知らないまま動作でき、
  Stateless性・テスト容易性（Spy関数を渡すだけで検証可能）が向上する

### Design Decision #5：`retry_attempt`は`candidate.retry_attempt`から`getattr`で取得し、Queueパッケージへは依存しない

Charter 8章 Open Question・ユーザー指示の重点5に対応する。

* `RetryCandidateEvent.candidate`は型`Any`であり、実態は
  `RetryQueueItem`（`retry_queue`パッケージ、`retry_attempt`フィールドを
  持つ）だが、`retry_engine`側はこの型を一切importしない
  （v3.8.0からの既存方針を踏襲）
* `getattr(candidate, "retry_attempt", 1)`という緩やかなダックタイピング
  でアクセスすることで、`retry_queue`パッケージへの型レベルの依存
  （import）を発生させずに済む。属性が存在しない場合は`RetryManager.retry()`
  のデフォルト値と同じ`1`にフォールバックする（防御的な設計、
  v3.8.0 Design Decision #7と同じ設計言語）
* **Open Questionとして残す**：`candidate`が将来`retry_attempt`属性を
  持たないオブジェクト（`RetryQueueItem`以外の由来）になった場合、
  `attempt=1`に静かにフォールバックする点は、実際の再試行回数を
  反映しない可能性がある。本Releaseでは「Queueとの型結合を避ける」
  ことを優先し、この残存リスクは12章 Future Extensionに記録した上で
  受容する

### Design Decision #6：実行結果は`RetryExecutionResult`という新規ラッパー型で返す（`RetryResult`自体は変更しない）

ユーザー指示の重点4に対応する。

* `execute_dispatchable_retries()`の戻り値を`list[RetryResult]`
  （既存型そのまま）にする案も検討したが、その場合「どの
  `RetryDispatchEvent`（＝どのQueue候補）から実行されたか」という文脈が
  失われ、将来のRetry Queue Update（`dequeue()` / `remove()`対象の特定）
  で改めて突き合わせが必要になる
* `RetryExecutionResult(dispatch_event, retry_result)`という軽量な
  `frozen=True`の`dataclass`を新設することで、既存の`RetryResult`
  （v3.0.0、frozen、無変更）を一切壊さずに、実行文脈を保持したまま
  将来の拡張点（12章 Future Extension）を残せる

### Design Decision #7：`RetryExecutionCoordinator.execute()`は`retry_fn`の例外をそのまま伝播させる（fail-fast）

Charter 8章 Open Question 10に対応する。

* 現時点でRetry Policyのような複雑な判定は導入しておらず、
  `RetryManager.retry()`自体も通常は例外を送出せず`RetryResult`を返す
  設計になっている。存在しないエラーケースに対する防御的なtry/exceptを
  追加することは、本プロジェクトの「発生しうるシナリオ以外への
  エラーハンドリングを追加しない」という開発方針に反する
* 将来、部分失敗時の継続処理が実際に必要になった場合、
  `RetryExecutionCoordinator.execute()`内にのみ変更を加えればよい
  （12章 Future Extension）

### Design Decision #8：`RetryExecutionSelector` / `RetryExecutionCoordinator`にも自動フォールバック方式を採用する

Charter 8章 Open Questionに対し、v3.8.0・v3.9.0と同じ設計判断を踏襲する。
`execution_selector` / `execution_coordinator`引数を省略した場合、
`RetryManager.__init__`がそれぞれ`RetryExecutionSelector()` /
`RetryExecutionCoordinator()`を自動構築する。

* 両コンポーネントとも設定値（Config）を持たず、外部リソースにも
  一切アクセスしないStatelessコンポーネントである
* `NullRetryExecutionSelector` / `NullRetryExecutionCoordinator`は
  作らない（両コンポーネント自体が既に「引数なしで安全に動作する」
  実装であるため。v3.8.0・v3.9.0と同じ判断）

### Design Decision #9：`NullRetryManager.execute_dispatchable_retries()`は常に空リストを返す

v3.8.0 Design Decision #6・v3.9.0 Design Decision #6と同じ理由により、
`NullRetryManager`は`RetryExecutionSelector` / `RetryExecutionCoordinator`
への参照を一切保持せず、`execute_dispatchable_retries()`は渡された
`events`の中身を検査せずに空リストを返す。

---

## 15. Charter Open Questions への回答

Charter（`docs/design/retry_execution_foundation_charter.md`）8章で
保留した10項目に対する結論。

1. **配置場所**：`retry_engine`パッケージ内の新規2ファイル
   （`retry_execution_selector.py` / `retry_execution_coordinator.py`）
   （14章 Design Decision #1）
2. **新規コンポーネントの名称**：`RetryExecutionSelector`（判定）/
   `RetryExecutionCoordinator`（実行・集約）。既存の`RetryExecutor`
   （v3.0.0）とは役割・名称を明確に区別する（14章 Design Decision #1）
3. **`attempt`値の取得方法**：`candidate_event.candidate`の
   `retry_attempt`属性を`getattr(..., 1)`で取得する（Queueパッケージ
   への型依存は発生させない。14章 Design Decision #5）
4. **`dry_run`パラメータの扱い**：`execute_dispatchable_retries(events,
   dry_run=False)`として、呼び出し元がバッチ全体に対して指定できる
   ようにする
5. **`dispatchable=False`のイベントの扱い**：`RetryExecutionSelector`の
   時点で除外し、結果リスト（`RetryExecutionResult`）にも含めない
   （実行されなかったものについて`retry_result`を持たせようがないため）
6. **実行結果の型**：`RetryExecutionResult(dispatch_event, retry_result)`
   という専用の`frozen dataclass`を新設する（14章 Design Decision #6）
7. **`RetryManager`への委譲メソッドの粒度・名称**：
   `execute_dispatchable_retries(events, dry_run=False)`1メソッドのみ
   （14章 Design Decision #3）
8. **新規コンポーネントの構築責務**：`execution_selector` /
   `execution_coordinator`引数省略時はそれぞれ自動構築する
   （自動フォールバック方式。14章 Design Decision #8）
9. **`NullRetryManager`側の扱い**：同名メソッドを追加し、常に空リストを
   返す（14章 Design Decision #9）
10. **複数件実行時のエラーハンドリング**：`retry_fn`が例外を送出した
    場合はそのまま伝播させる（fail-fast）。部分失敗時の継続処理は
    将来Releaseの検討事項とする（14章 Design Decision #7）

---

## 16. Architecture Review

状態：**Approve with Recommendations**（Claude Codeによる自己点検。
指摘事項は2件、実装をブロックしない）。

### 16.1 レビュー観点別の判定

| # | 観点 | 判定 | 根拠 |
|---|---|---|---|
| 1 | 既存の`RetryManager()` / `from_config()`呼び出しが完全互換か | **互換** | `execution_selector` / `execution_coordinator`は末尾のデフォルト値付き引数。13章で確認 |
| 2 | Retry Queueの更新が構造的に不可能か（重点3） | **不可能** | `RetryExecutionSelector` / `RetryExecutionCoordinator`のいずれも`RetryQueueManager`への参照を一切持たない（10章） |
| 3 | `dequeue()` / `remove()`の呼び出しが構造的に不可能か | **不可能** | 同上。`execute_dispatchable_retries()`も`self._queue`を参照しない（10章） |
| 4 | `dispatchable=True`が唯一の実行入口になっているか（重点2） | **なっている** | `RetryExecutionSelector.select()`のみが`dispatchable`を参照する。`RetryExecutionCoordinator`は選別済みリストのみを扱う（14章 Design Decision #2） |
| 5 | RetryManagerの責務が増えすぎていないか（重点1） | **増えていない** | `execute_dispatchable_retries()`は3行の委譲のみ。判定・実行ロジックは2つの新規コンポーネントに分離済み（2章・14章 Design Decision #3） |
| 6 | 専用Result型の要否（重点4） | **導入が妥当** | `RetryExecutionResult`により、既存`RetryResult`を変更せずに実行文脈（`dispatch_event`）を保持できる（14章 Design Decision #6） |
| 7 | `retry_attempt`の扱いがQueueと型結合していないか（重点5） | **結合していない** | `retry_queue`パッケージへのimportは発生しない。`getattr`によるダックタイピングのみ（14章 Design Decision #5） |
| 8 | 将来のRetry Policy・Retry Queue Updateへの拡張性 | **確保されている** | 選別基準の変更は`RetryExecutionSelector`のみに閉じる。`RetryExecutionResult`が`dispatch_event`を保持するためQueue Updateでの突き合わせが容易（12章） |
| 9 | `scheduler` / `retry_event_consumer.py` / `retry_event_dispatcher.py`が本Releaseでも無改修か | **無改修** | 4章Package Structureのとおり |
| 10 | 新規の外部パッケージ依存が発生しないか | **発生しない** | 新規2ファイルのimportは`retry_engine`パッケージ内の型と標準ライブラリのみ（10章） |
| 11 | 循環importが発生しないか | **発生しない** | 新規の依存方向自体が発生しない |
| 12 | Foundation First / SRP / Statelessが守られているか | **守られている** | Foundation First：実行結果を使ったQueue操作は一切追加していない。SRP：判定と実行を分離。Stateless：両コンポーネントとも内部状態を持たず、`retry_fn`も引数で受け取る |
| 13 | 既存APIとの後方互換性 | **維持されている** | 13章で確認済み。既存5メソッド（`retry()` / `enqueue_retry()` / `dequeue_retry()` / `recognize_retry_events()` / `dispatch_retry_events()`）はいずれも無変更 |
| 14 | `NullRetryManager`が「受け取れるが何もしない」を体現しているか | **体現している** | `execute_dispatchable_retries()`は新規コンポーネントを構築・参照せず、常に`[]`を返す（8.3節） |
| 15 | 既存Regressionへの影響がないか | **影響なし** | `RetryManager` / `NullRetryManager`の既存メソッド・コンストラクタはいずれも無変更。新規メソッド1つの追加のみ |

### 16.2 SOLID

* **単一責任（SRP）**：`RetryExecutionSelector`は「`dispatchable=True`の
  選別」、`RetryExecutionCoordinator`は「`retry_fn`呼び出しと結果集約」
  という、それぞれ1つの関心事のみを持つ
* **開放閉鎖（OCP）**：既存メソッドに変更を加えず、新規メソッドの追加
  のみで機能を拡張している。将来の選別基準拡張も`RetryExecutionSelector`
  の内部実装変更のみで対応可能（公開シグネチャは不変）
* **リスコフの置換（LSP）**：`RetryManager` / `NullRetryManager`とも
  同名の`execute_dispatchable_retries(events, dry_run=False) ->
  list[RetryExecutionResult]`を持ち、戻り値の型・意味論が一貫している
  （`NullRetryManager`は常に空集合を返す部分集合として振る舞う）
* **インターフェース分離（ISP）**：`execute_dispatchable_retries()`が
  利用するのは`self.dispatch_retry_events()`（既存）・
  `self._execution_selector.select()`（新規）・
  `self._execution_coordinator.execute()`（新規）の3つのみ
* **依存性逆転（DIP）**：`RetryManager`は`RetryExecutionSelector` /
  `RetryExecutionCoordinator`という具象クラスに依存する。プロジェクト
  全体で一貫している「Null Object Patternによるダックタイピングのみで、
  ABCは導入しない」という既存方針の延長である

### 16.3 残された懸念（Recommendations）

1. **`retry_attempt`のダックタイピング依存（14章 Design Decision #5）**：
   `candidate.retry_attempt`への`getattr`アクセスは、`retry_queue`
   パッケージへの型結合を避けるための意図的な選択だが、`candidate`の
   由来が将来変化した場合に静かに`attempt=1`へフォールバックする
   リスクを残す。実装時、この挙動を単体テストで明示的に固定化し
   （`retry_attempt`が存在する場合／しない場合の両方をテストする）、
   将来`RetryCandidateEvent`への正式なフィールド追加を検討する際の
   判断材料として記録しておくことを推奨する
2. **`RetryExecutionCoordinator.execute()`のfail-fast方針（14章 Design
   Decision #7）**：現時点では該当する例外シナリオが存在しないため
   妥当な判断だが、将来複数件のバッチ実行が実運用で使われる段階
   （Composition Root導入時）で、1件の失敗が残り全件の実行を止めて
   しまう影響範囲を再評価することを推奨する

いずれも実装を妨げる指摘ではなく、実装時のテスト設計、および次Release
以降で状況に応じて対応を検討する事項として記録する。

### 16.4 Foundation First・プロジェクト全体との設計整合性

Charter・ユーザー指示が要求した「`dispatchable=true`の
`RetryDispatchEvent`だけを対象に`RetryManager.retry()`を呼び出せる
基盤を構築するが、Retry Queue更新・`enqueue_retry()` /
`dequeue_retry()` / `remove()`・Queue永続化・Retry Policyの導入・
高度なRetry Attempt管理は対象外」という範囲に対し、本設計は
`RetryExecutionResult`を使ってQueueを更新する処理を一切追加しておらず、
スコープの逸脱はない。v3.3.0〜v3.9.0の「Foundation First・消費者不在の
実行ロジックなし」というパターンを、本Releaseでも踏襲している。

### 16.5 依存方向

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
`retry_manager.py → retry_execution_selector.py` /
`retry_manager.py → retry_execution_coordinator.py`という依存が
追加されるが、これは既存の`retry_manager.py → retry_event_consumer.py`
（v3.8.0）・`retry_manager.py → retry_event_dispatcher.py`（v3.9.0）と
同じパッケージ内の依存であり、パッケージ間の新規依存方向ではない。

### 16.6 後方互換性

13章で述べたとおり、変更は`RetryManager.__init__` / `from_config()`への
オプション引数（`execution_selector` / `execution_coordinator`）追加と、
既存メソッドに影響しない新規メソッド1つ・新規ファイル2つの追加のみ。
既存の`retry()` / `enqueue_retry()` / `dequeue_retry()` /
`recognize_retry_events()` / `dispatch_retry_events()`・
`retry_event_consumer.py` / `retry_event_dispatcher.py` /
`retry_config.py` / `retry_executor.py` / `retry_policy.py` /
`retry_request.py` / `retry_result.py`はいずれも無変更。`scheduler`側も
ゼロ改修であり、既存呼び出し元への影響はないと判断する。

### 16.7 総評

Charter・ユーザー指示が要求した重点5項目（RetryManagerの責務分離・
単一の実行入口・Queue非依存・専用Result型・retry_attemptの扱い）は
いずれも設計上満たされている。Recommendation 2件（16.3節）は実装を
ブロックする性質のものではなく、実装時のテスト設計と次Release以降での
検討事項として記録すれば足りる。

**Approve with Recommendations** と判断する。

---

## 17. Status

- [x] Architecture Design ドラフト作成（本文書、Claude Code作成）
- [x] Architecture Review完了（Claude Codeによる自己点検、Approve with
      Recommendations。指摘事項2件は実装時のテスト設計・次Release検討
      事項として記録済み）
- [ ] ユーザー確認・実装可否判断
- [ ] 実装（本メッセージ時点では未着手）
- [ ] テスト（本メッセージ時点では未着手）
