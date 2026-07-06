# v4.2.0 Retry Queue Removal Foundation 設計書（Architecture Design）

作成日：2026-07-06
状態：ドラフト（Architecture Review未実施。本文書提示後に実施する）。
`docs/design/retry_queue_removal_foundation_charter.md`（Project Charter、
ユーザー確認待ち、2026-07-06）を前提とする。

---

## 1. Architecture Overview

Release 4.1（`docs/design/retry_queue_update_foundation.md`）までで、
以下が確立した。

* `retry_engine`パッケージに`RetryQueueUpdateDecider`が新設され、
  `RetryManager.decide_retry_queue_updates(events)`が、`RetryExecutionResult`
  のリストから`RetryQueueUpdateDecision`（`execution_result` / `outcome` /
  `target_status` / `reason`）のリストを判定できるようになった
* `outcome`（`RetryQueueUpdateOutcome`）は`COMPLETE` / `FAIL` / `NOOP`の
  3値。`COMPLETE` / `FAIL`は再実行が実際に行われたケース、`NOOP`は
  `SKIPPED` / `NOT_FOUND` / `DISABLED`いずれかに由来し再実行が行われて
  いないケース
* `RetryQueueUpdateDecision`を使って何かをさらに実行する処理（Queueへの
  実際の反映等）は、`retry_engine`側に一切存在しない
* `RetryQueueManager.remove(run_id)`（v3.1.0）は実装済みだが、
  v3.1.0〜v4.1.0のいずれのリリースでも構造的に（AST・Spyで）呼び出されない
  ことが確認され続けてきた

本Release（v4.2.0）は、`retry_engine`パッケージに**判定の次の段階**として、
`RetryQueueUpdateDecision`を対象に、`outcome`が`COMPLETE`または`FAIL`の
項目についてのみ`RetryQueueManager.remove(run_id)`を呼び出し、Queueから
該当項目を除去する新規コンポーネントを新設する。`outcome`が`NOOP`の項目
（`SKIPPED` / `NOT_FOUND` / `DISABLED`いずれに由来する場合も）は、remove
呼び出しの対象から構造的に除外する。

```
Retry Engine（受信・整理・実行・判定、v3.0.0〜v4.1.0）
   │
   ├── decide_retry_queue_updates()（v4.1.0、無改修）
   │      → RetryQueueUpdateDecision のリスト（COMPLETE/FAIL/NOOP）
   │
   └── apply_retry_queue_removals() ★新設
          │
          └─► RetryQueueRemovalExecutor ★新設（除去：COMPLETE/FAILのみ remove_fn を呼び出す）
                 │
                 ▼
             RetryQueueRemovalResult ★新設データ構造
                 （decision・attempted・queue_result・reason）
```

本Releaseの核心は、「`RetryQueueUpdateDecision.outcome`が`COMPLETE` /
`FAIL`かどうかで、実際にQueueへ反映する（`remove()`を呼ぶ）かどうかを
振り分ける」という1つの新しい関心事を、**除去の実行にのみ特化した
単一のStatelessコンポーネント**として追加することである。
`RetryQueueUpdateDecider` / `RetryExecutionSelector` /
`RetryExecutionCoordinator` / `RetryQueueManager`は一切変更しない。
`SKIPPED`（`max_attempts`到達）由来の`NOOP`項目のQueue滞留対応は本Release
では一切行わない（Foundation First）。

---

## 2. Design Options（比較検討）

Charter 8章 Open Question 2（remove操作の受け取り方）に対応し、2案を
比較する。

### 案A（採用）：remove操作を`remove_fn: Callable[[str], RetryQueueResult]`として関数で受け取る

`RetryQueueRemovalExecutor`は`RetryQueueManager`型を一切importせず、
`apply_all(decisions, remove_fn)`のようにメソッド引数として関数を
受け取る。v4.0.0`RetryExecutionCoordinator`が`retry_fn: Callable[...,
RetryResult]`をメソッド引数として受け取ったパターンをそのまま踏襲する。

* メリット：
  * `RetryQueueRemovalExecutor`が`RetryQueueManager` /
    `NullRetryQueueManager`型への依存を一切持たない。既存の
    `RetryExecutionSelector` / `RetryExecutionCoordinator` /
    `RetryQueueUpdateDecider`が貫いてきた「実行系・判定系コンポーネントは
    具象Managerクラスに依存しない」という一貫したパターンを継続できる
  * `RetryManager`が`self._queue.remove`（既にv3.2.0で保持している
    `self._queue`のバウンドメソッド）をそのまま渡せるため、
    `RetryQueueRemovalExecutor`側に新しいimportを追加する必要がない
  * テスト時にFakeの`remove_fn`（単純な関数・ラムダ）を渡すだけで
    構造的な検証（Spyパターン）ができ、`RetryQueueManager`の
    フルスタブを用意する必要がない
* デメリット：
  * `remove_fn`の型が`Callable[[str], RetryQueueResult]`という抽象的な
    シグネチャになり、呼び出し元（`RetryManager`）が正しい関数
    （`self._queue.remove`）を渡す責任を負う（ただし`RetryManager`は
    既に`self._queue`を保持しているため、渡し間違いのリスクは低い）

### 案B：`RetryQueueManager | NullRetryQueueManager`型を直接コンストラクタで受け取る

`RetryQueueRemovalExecutor.__init__(self, queue: RetryQueueManager |
NullRetryQueueManager)`のように、Queue自体への参照を保持する。

* メリット：
  * `remove()`だけでなく将来`exists()` / `list()`等、Queueの他の操作も
    同じコンポーネントから呼び出せる拡張性がある
* デメリット：
  * `retry_engine`パッケージのコンポーネントが初めて`RetryQueueManager`
    型そのものへ直接依存することになり、v4.0.0`RetryExecutionCoordinator`・
    v4.1.0`RetryQueueUpdateDecider`が意図的に避けてきた「実行系・判定系は
    具象Managerクラスに依存しない」という既存方針から外れる
  * 本Releaseのスコープ（`remove()`のみを呼び出す）に対して、Queue全体への
    参照を持たせるのは責務過剰（Single Responsibilityにやや反する）
  * テスト時に`RetryQueueManager`相当のスタブ（`remove()`メソッドを持つ
    オブジェクト）を用意する必要があり、案Aより準備コストが高い

### 比較表

| 観点 | 案A（関数で受け取る、採用） | 案B（Manager型を直接保持） |
|---|---|---|
| `RetryQueueManager`型への依存 | なし | あり（新規） |
| 既存パターンとの整合性 | v4.0.0`RetryExecutionCoordinator`と同じ | 既存のどのコンポーネントとも異なる新パターン |
| 責務の広さ | `remove()`呼び出しのみに限定 | Queue操作全般に拡張しやすいが本Releaseには過剰 |
| テスト容易性 | 関数（ラムダ）で十分 | スタブオブジェクトが必要 |

**結論**：案Aを採用する。既存の「実行系・判定系コンポーネントは具象
Managerクラスに依存しない」という一貫したパターンを継続でき、本Release
のスコープ（`remove()`のみ）にも過不足なく合致する。

---

## 3. Design Policy

Charter 5章 Design Principles、およびユーザー指示を、本設計では以下の形で
具体化する。

1. **Foundation First**：`RetryQueueUpdateDecision`を入力に`COMPLETE` /
   `FAIL`の項目のみ`remove()`を呼び出せるところまでを行う。`NOOP`
   （特に`SKIPPED`の滞留問題）への対応は後続Releaseへ送る（10章）
2. **Single Responsibility**：`RetryQueueRemovalExecutor`は
   「`RetryQueueUpdateDecision`1件について、`outcome`が`COMPLETE` /
   `FAIL`なら`remove_fn`を呼び出し、`NOOP`なら呼び出さずスキップする」
   ことのみを担う。判定（`RetryQueueUpdateDecider`）・実行
   （`RetryExecutionCoordinator`）・Queue管理そのもの
   （`RetryQueueManager`）のいずれも複製・肩代わりしない
3. **Stateless**：`RetryQueueRemovalExecutor`は内部状態を一切持たない。
   コンストラクタ引数を取らず、`apply()` / `apply_all()`は渡された
   `RetryQueueUpdateDecision`と`remove_fn`のみから結果を導出する
4. **Backward Compatibility**：`RetryManager.__init__` / `from_config()`に
   `queue_removal_executor`引数（デフォルト`None`）を追加し、省略時は
   `RetryQueueRemovalExecutor()`に自動フォールバックする。既存の`retry()` /
   `enqueue_retry()` / `dequeue_retry()` / `recognize_retry_events()` /
   `dispatch_retry_events()` / `execute_dispatchable_retries()` /
   `decide_retry_queue_updates()`は1行も変更しない
5. **RetryManagerの責務を肥大化させない**：新規委譲メソッド
   `apply_retry_queue_removals()`は「`decide_retry_queue_updates()`
   （v4.1.0、無変更）への委譲→`RetryQueueRemovalExecutor.apply_all()`
   （`remove_fn=self._queue.remove`を渡す）への委譲」という2行の合成
   のみで完結させる
6. **既存コンポーネントの責務を変更しない**：`RetryQueueUpdateDecider` /
   `RetryExecutionSelector` / `RetryExecutionCoordinator` /
   `RetryQueueManager`はいずれも無改修
7. **`NOOP`はremove対象外として結果に明示する**：`decision.outcome ==
   NOOP`の項目は`remove_fn`を呼び出さず、`RetryQueueRemovalResult
   (attempted=False, queue_result=None, ...)`として結果リストに含める
   （黙って除外せず、「remove対象外だった」ことを呼び出し元が確認できる
   ようにする）

---

## 4. 除去方針（Removal Policy）

`RetryQueueRemovalExecutor`が扱う入力は`RetryQueueUpdateDecision.outcome`
（`RetryQueueUpdateOutcome`、v4.1.0、無変更）である。

| `decision.outcome` | remove呼び出し | `attempted` | `queue_result` | 判定理由 |
|---|---|---|---|---|
| `COMPLETE` | 呼び出す（`remove_fn(run_id)`） | `True` | `remove_fn`の戻り値（`REMOVED` / `NOT_FOUND` / `DISABLED`のいずれか） | 再実行が成功し、Queueから該当項目を除去すべきと判定済み |
| `FAIL` | 呼び出す（`remove_fn(run_id)`） | `True` | `remove_fn`の戻り値（`REMOVED` / `NOT_FOUND` / `DISABLED`のいずれか） | 再実行が失敗したが、Queueから該当項目を除去すべきと判定済み（v4.1.0 4章の判定方針通り、失敗も除去対象） |
| `NOOP` | 呼び出さない | `False` | `None` | 再実行が実際には行われていない（`SKIPPED` / `NOT_FOUND` / `DISABLED`いずれか由来）ため、Queueの状態を変える根拠がない（v4.1.0 14章 Design Decision #2の判断を継承する） |

* `run_id`は`decision.execution_result.dispatch_event.candidate_event.run_id`
  から取得する（`RetryCandidateEvent.run_id`、v3.8.0で定義済みのフィールド）。
  `execution_result`を分解せず保持したまま利用するため、追加の突き合わせ
  （`RetryQueueManager.list()`等）は発生しない
* `remove_fn`の戻り値が`RetryQueueOutcome.NOT_FOUND`であっても
  `RetryQueueRemovalExecutor`はエラーとして扱わない。`run_id`がQueueに
  存在しない状態（例：`enqueue_retry()`を経由せずに`retry()`が実行された
  ケース）は既存の`RetryQueueManager.remove()`の正常な結果の1つである
* `remove_fn`の戻り値が`RetryQueueOutcome.DISABLED`（`RETRY_QUEUE_ENABLED
  =false`で`NullRetryQueueManager`が使われている場合）も同様にエラー
  として扱わない
* `dry_run`は`RetryQueueRemovalExecutor`の除去方針に一切影響しない。
  `RetryManager.apply_retry_queue_removals(events, dry_run=False)`が
  `dry_run`を受け取るのは`decide_retry_queue_updates()`（v4.1.0）へ
  そのまま伝播するためであり、`dry_run=True`で実行された`retry()`の結果
  そのものが`RETRIED`にならない（`RetryExecutor`側の既存挙動）ため、
  `RetryQueueRemovalExecutor`自体は`dry_run`の概念を知る必要がない

---

## 5. Package Structure（変更差分）

```
src/retry_engine/
├── __init__.py                     # 変更：新規シンボルのexport追加。docstring更新
├── retry_event_consumer.py         # 無変更（v3.8.0のまま）
├── retry_event_dispatcher.py       # 無変更（v3.9.0のまま）
├── retry_execution_selector.py     # 無変更（v4.0.0のまま）
├── retry_execution_coordinator.py  # 無変更（v4.0.0のまま）
├── retry_queue_update_decider.py   # 無変更（v4.1.0のまま）
├── retry_queue_removal_executor.py # ★新規：RetryQueueRemovalResult /
│                                   #        RetryQueueRemovalExecutor
├── retry_manager.py                # ★変更：RetryManager.__init__ に
│                                   #        queue_removal_executor 引数追加。
│                                   #        apply_retry_queue_removals() を追加。
│                                   #        NullRetryManager にも同名メソッドを追加
├── retry_config.py                 # 無変更
├── retry_executor.py               # 無変更
├── retry_policy.py                 # 無変更
├── retry_request.py                # 無変更
└── retry_result.py                 # 無変更

src/scheduler/                      # 全ファイル無改修
src/retry_scheduler_decision/       # 全ファイル無改修
src/retry_scheduler_source/         # 全ファイル無改修
src/retry_queue/                    # 全ファイル無改修（remove() はv3.1.0の
                                     # 既存実装をそのまま利用するのみ）

tests/
└── test_e2e_v4_2_0_retry_queue_removal_foundation.py   # 新規
```

変更対象は`retry_engine`配下2ファイル（`retry_queue_removal_executor.py`
新規・`retry_manager.py`変更）と`__init__.py`のみ。`scheduler` /
`retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` /
`retry_event_consumer.py` / `retry_event_dispatcher.py` /
`retry_execution_selector.py` / `retry_execution_coordinator.py` /
`retry_queue_update_decider.py`はいずれも本Releaseでもゼロ改修。

---

## 6. Public API

### `retry_queue_removal_executor.py`（新規）

```python
"""
Retry Queue Removal Executor（v4.2.0）

RetryQueueRemovalResult:   RetryQueueUpdateDecision 1件に対する除去処理結果を保持する軽量データ
RetryQueueRemovalExecutor: RetryQueueUpdateDecision のリストを受け取り、outcome が
                           COMPLETE / FAIL の項目についてのみ remove_fn を呼び出し、
                           Queueから該当項目を除去するコンポーネント

設計方針:
    - RetryQueueManager / NullRetryQueueManager 型への依存を一切持たない。remove操作は
      呼び出しごとに remove_fn（Callable[[str], RetryQueueResult]）として受け取る
      （docs/design/retry_queue_removal_foundation.md 2章 案A）。
    - Stateless。RetryQueueUpdateDecision と remove_fn を受け取り、結果を返すだけの
      メソッドのみを持つ。内部状態を一切保持しない。
    - outcome が NOOP の項目は remove_fn を呼び出さない（4章 除去方針）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from retry_queue import RetryQueueResult

from .retry_queue_update_decider import RetryQueueUpdateDecision, RetryQueueUpdateOutcome

RemoveFn = Callable[[str], RetryQueueResult]

_REMOVABLE_OUTCOMES = (RetryQueueUpdateOutcome.COMPLETE, RetryQueueUpdateOutcome.FAIL)


@dataclass(frozen=True)
class RetryQueueRemovalResult:
    """1件のRetryQueueUpdateDecisionに対する除去処理結果を保持する軽量データ。"""

    decision: RetryQueueUpdateDecision
    attempted: bool
    queue_result: RetryQueueResult | None
    reason: str


class RetryQueueRemovalExecutor:
    """RetryQueueUpdateDecisionを対象に、COMPLETE/FAILの項目のみremove_fnを呼び出すコンポーネント。"""

    def apply_all(
        self, decisions: list[RetryQueueUpdateDecision], remove_fn: RemoveFn
    ) -> list[RetryQueueRemovalResult]:
        """decisionsの各要素についてapply()を呼び出し、結果のリストを返す。"""
        return [self.apply(decision, remove_fn) for decision in decisions]

    def apply(
        self, decision: RetryQueueUpdateDecision, remove_fn: RemoveFn
    ) -> RetryQueueRemovalResult:
        """1件のRetryQueueUpdateDecisionについて、除去を試行するかどうかを判定し実行する。"""
        if decision.outcome not in _REMOVABLE_OUTCOMES:
            return RetryQueueRemovalResult(
                decision=decision,
                attempted=False,
                queue_result=None,
                reason=f"decision.outcome={decision.outcome.value} is not eligible for queue removal.",
            )

        run_id = decision.execution_result.dispatch_event.candidate_event.run_id
        queue_result = remove_fn(run_id)
        return RetryQueueRemovalResult(
            decision=decision,
            attempted=True,
            queue_result=queue_result,
            reason=f"remove() was called for run_id={run_id} (decision.outcome={decision.outcome.value}).",
        )
```

### `retry_manager.py`（変更部分のみ抜粋）

```python
from .retry_queue_removal_executor import RetryQueueRemovalExecutor, RetryQueueRemovalResult  # ★新規


class RetryManager:
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
        queue_removal_executor: RetryQueueRemovalExecutor | None = None,  # ★新規
    ):
        ...（既存の初期化は無変更）...
        self._queue_removal_executor = (
            queue_removal_executor if queue_removal_executor is not None else RetryQueueRemovalExecutor()
        )  # ★新規

    @classmethod
    def from_config(
        cls,
        ...,
        queue_removal_executor: RetryQueueRemovalExecutor | None = None,  # ★新規
    ) -> "RetryManager | NullRetryManager":
        ...（既存のガード節は無変更）...
        return cls(
            ...,
            queue_removal_executor=queue_removal_executor,  # ★新規
        )

    # retry() / enqueue_retry() / dequeue_retry() / recognize_retry_events() /
    # dispatch_retry_events() / execute_dispatchable_retries() /
    # decide_retry_queue_updates() / _skip_reason() は無変更（省略）

    def apply_retry_queue_removals(
        self, events: list[SchedulerEvent], dry_run: bool = False
    ) -> list[RetryQueueRemovalResult]:
        """
        SchedulerEventのリストから、各RetryQueueUpdateDecisionについて
        outcomeがCOMPLETE/FAILの項目のみRetryQueueManager.remove()を呼び出し、
        Queueから該当項目を除去する（decide_retry_queue_updates()、v4.1.0、
        無変更、への委譲＋RetryQueueRemovalExecutor.apply_all()への委譲の
        2段階のみで完結する）。

        2段階の委譲のみで完結する：
            1. self.decide_retry_queue_updates(events, dry_run=dry_run)（v4.1.0、無変更）
            2. self._queue_removal_executor.apply_all(decisions, remove_fn=self._queue.remove)
               （新規、除去）
        """
        decisions = self.decide_retry_queue_updates(events, dry_run=dry_run)
        return self._queue_removal_executor.apply_all(decisions, remove_fn=self._queue.remove)


class NullRetryManager:
    # retry() / enqueue_retry() / dequeue_retry() / recognize_retry_events() /
    # dispatch_retry_events() / execute_dispatchable_retries() /
    # decide_retry_queue_updates() は無変更（省略）

    def apply_retry_queue_removals(
        self, events: list[SchedulerEvent], dry_run: bool = False
    ) -> list[RetryQueueRemovalResult]:
        """
        RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている場合、
        除去処理自体を一切行わず常に空リストを返す。RetryQueueRemovalExecutorへの
        参照は保持しない。
        """
        return []
```

* `RetryManager.__init__` / `from_config()`とも、既存引数の**末尾**に
  デフォルト値付きの`queue_removal_executor`を追加する。既存の位置引数・
  キーワード引数呼び出しはいずれも影響を受けない
* `NullRetryManager.apply_retry_queue_removals()`は`RetryQueueRemovalExecutor`
  を一切構築・参照せず、リテラルの空リストを返す
* `RetryManager.apply_retry_queue_removals()`は`remove_fn=self._queue.remove`
  として、v3.2.0で既に保持している`self._queue`のバウンドメソッドを渡す
  のみであり、`retry_manager.py`に新規の`RetryQueueManager`型への依存は
  発生しない（既存の`self._queue`をそのまま利用する）

### `__init__.py`の公開シンボル（追加分のみ）

```python
from .retry_queue_removal_executor import (     # ★新規
    RetryQueueRemovalExecutor,
    RetryQueueRemovalResult,
)

__all__ = [
    ...,  # 既存はすべて維持
    "RetryQueueRemovalResult",      # ★新規
    "RetryQueueRemovalExecutor",    # ★新規
]
```

---

## 7. Class Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryQueueUpdateDecider`（v4.1.0、無改修） | `RetryExecutionResult`を対象に、更新先の`RetryQueueUpdateDecision`（`COMPLETE` / `FAIL` / `NOOP`）を判定する | Queueへの実際の反映（`remove()`等） |
| `RetryQueueRemovalExecutor`（本Releaseで新規） | `RetryQueueUpdateDecision`を対象に、`outcome`が`COMPLETE` / `FAIL`の項目のみ`remove_fn`を呼び出し、結果を集約する | 判定ロジックの再実装・`remove_fn`自体の実装（`RetryQueueManager.remove()`が担う）・`NOOP`の内訳判断・永続化 |
| `RetryManager`（本Releaseで変更） | `RetryQueueRemovalExecutor`への薄い委譲窓口を持ち、`remove_fn=self._queue.remove`を渡す | 除去ロジックの再実装・判定ロジックの再実装 |
| `RetryQueueManager`（v3.1.0、無改修） | `remove()`の実処理（Queueからの取り消し・内部ストア更新） | Queue項目の更新先判定・除去対象の選別 |

`RetryQueueRemovalExecutor`は`RetryQueueUpdateDecision`（v4.1.0、無変更）
という**既存の型を消費する**ことのみを担い、生成元にも変更を加えない。

---

## 8. Class Diagram

```
┌───────────────────────────────────────────────────┐
│                       RetryManager                       │
│───────────────────────────────────────────────────│
│ - _policy / _executor / _monitor / _queue                │  無変更
│ - _event_consumer / _event_dispatcher                     │  無変更（v3.8.0/v3.9.0）
│ - _execution_selector / _execution_coordinator            │  無変更（v4.0.0）
│ - _queue_update_decider                                    │  無変更（v4.1.0）
│ - _queue_removal_executor: RetryQueueRemovalExecutor       │  ★新設
│───────────────────────────────────────────────────│
│ + __init__(..., queue_removal_executor=None)               │  ★引数追加
│ + from_config(...)                                          │  ★引数追加
│ + decide_retry_queue_updates(events, dry_run=False)         │  無変更（v4.1.0）
│     -> list[RetryQueueUpdateDecision]                         │
│ + apply_retry_queue_removals(events, dry_run=False)          │  ★新設
│     -> list[RetryQueueRemovalResult]                          │
└───────────────────────┬───────────────────────────┘
                         │ 委譲①：decide_retry_queue_updates（無変更）
                         │ 委譲②：apply_all（remove_fn=self._queue.remove）
                         ▼
        ┌─────────────────────────────────┐
        │        RetryQueueRemovalExecutor       │  ★新設
        │─────────────────────────────────│
        │ + apply(decision, remove_fn)            │
        │     -> RetryQueueRemovalResult          │
        │ + apply_all(decisions, remove_fn)       │
        │     -> list[RetryQueueRemovalResult]    │
        └─────────────────┬───────────────┘
                           │ 生成
                           ▼
        ┌─────────────────────────────────────┐
        │           RetryQueueRemovalResult            │  ★新設（frozen dataclass）
        │─────────────────────────────────────│
        │ + decision: RetryQueueUpdateDecision         │  （v4.1.0、分解しない）
        │ + attempted: bool                             │  ★新設
        │ + queue_result: RetryQueueResult | None       │  （v3.1.0、分解しない）
        │ + reason: str                                 │
        └─────────────────────────────────────┘

┌────────────────────────────────────┐
│              NullRetryManager             │
│────────────────────────────────────│
│ + decide_retry_queue_updates(...)          │  無変更（常に[]）
│ + apply_retry_queue_removals(events, ...)   │  ★新設（常に[]）
│     -> list[RetryQueueRemovalResult]         │
└────────────────────────────────────┘
```

`RetryQueueRemovalExecutor`は`RetryManager`にのみ保持され、
`NullRetryManager`はこれを一切参照しない。`RetryQueueRemovalExecutor`は
コンストラクタ引数を一切取らない（`RetryQueueManager`への参照も持たない。
`remove_fn`はメソッド引数として都度渡される）。

---

## 9. Sequence Diagram

### 9.1 apply_retry_queue_removals()（再実行が成功しCOMPLETE判定された場合）

```
Caller       RetryManager   RetryQueueRemovalExecutor   RetryQueueManager
  │  events = [SchedulerEvent(job_id="retry:run-001", ...)]                              │
  │                                                                                       │
  │  retry_manager.apply_retry_queue_removals(events)                                   │
  ├────────►│                                                                            │
  │         │ decisions = self.decide_retry_queue_updates(events)                        │
  │         │  # [RetryQueueUpdateDecision(outcome=COMPLETE,                              │
  │         │  #   execution_result=...(candidate_event.run_id="run-001"))]               │
  │         │                                                                            │
  │         │ self._queue_removal_executor.apply_all(decisions,                          │
  │         │                                          remove_fn=self._queue.remove)      │
  │         ├─────────────────────────────────────►│                                     │
  │         │                                        │ outcome=COMPLETE → remove対象        │
  │         │                                        │ run_id = decision.execution_result   │
  │         │                                        │   .dispatch_event.candidate_event    │
  │         │                                        │   .run_id  # "run-001"                │
  │         │                                        │ remove_fn("run-001")                 │
  │         │                                        ├──────────────────────────►│          │
  │         │                                        │                            │ pop item │
  │         │                                        │                            │ CANCELLED│
  │         │                                        │◄───────────────────────────┤          │
  │         │                                        │ RetryQueueResult(REMOVED)             │
  │         │◄─────────────────────────────────────┤                                     │
  │         │ [RetryQueueRemovalResult(                                                    │
  │         │    decision=..., attempted=True,                                             │
  │         │    queue_result=RetryQueueResult(outcome=REMOVED, ...),                       │
  │         │    reason="remove() was called for run_id=run-001 (decision.outcome=complete).")] │
  │◄────────┤                                                                            │
```

### 9.2 apply_retry_queue_removals()（decisionがNOOPの場合）

```
Caller       RetryManager   RetryQueueRemovalExecutor
  │  retry_manager.apply_retry_queue_removals(events)                          │
  ├────────►│                                                                  │
  │         │ decisions = self.decide_retry_queue_updates(events)              │
  │         │  # [RetryQueueUpdateDecision(outcome=NOOP, ...)]                  │
  │         │ self._queue_removal_executor.apply_all(decisions, remove_fn=...) │
  │         ├─────────────────────────────────────►│                         │
  │         │                                        │ outcome=NOOP → remove対象外 │
  │         │                                        │ remove_fnは呼び出さない     │
  │         │◄─────────────────────────────────────┤                         │
  │         │ [RetryQueueRemovalResult(                                        │
  │         │    decision=..., attempted=False, queue_result=None,             │
  │         │    reason="decision.outcome=noop is not eligible for "           │
  │         │            "queue removal.")]                                    │
  │◄────────┤                                                                  │
```

### 9.3 apply_retry_queue_removals()（対象run_idがQueueに存在しない場合）

```
Caller       RetryManager   RetryQueueRemovalExecutor   RetryQueueManager
  │  # COMPLETE判定だが、対象run_idはenqueue_retry()を経由していない            │
  │  retry_manager.apply_retry_queue_removals(events)                          │
  ├────────►│                                                                  │
  │         │ decisions = self.decide_retry_queue_updates(events)              │
  │         │  # [RetryQueueUpdateDecision(outcome=COMPLETE, ...)]              │
  │         │ self._queue_removal_executor.apply_all(decisions, remove_fn=...) │
  │         ├─────────────────────────────────────►│                          │
  │         │                                        │ remove_fn("run-999")        │
  │         │                                        ├──────────────────────────►│
  │         │                                        │                            │ 該当なし │
  │         │                                        │◄───────────────────────────┤          │
  │         │                                        │ RetryQueueResult(NOT_FOUND)           │
  │         │◄─────────────────────────────────────┤                          │
  │         │ [RetryQueueRemovalResult(                                         │
  │         │    attempted=True,                                                │
  │         │    queue_result=RetryQueueResult(outcome=NOT_FOUND, ...))]         │
  │◄────────┤  # エラー扱いしない（正常な結果の1つ）                              │
```

### 9.4 NullRetryManager.apply_retry_queue_removals()

```
Caller       NullRetryManager
  │  null_manager.apply_retry_queue_removals(events)  # eventsの中身は問わない │
  ├────────►│                                                                 │
  │         │ return []  # RetryQueueRemovalExecutorへの参照を持たない          │
  │◄────────┤  []                                                             │
```

---

## 10. Data Flow

```
① 呼び出し元（Composition Root、本Releaseでは未実装）が SchedulerEvent の
   リストを RetryManager.apply_retry_queue_removals(events)
   （または NullRetryManager.apply_retry_queue_removals(events)）へ渡す
        ↓
② RetryManager は self.decide_retry_queue_updates(events, dry_run=dry_run)
   （v4.1.0、無変更）へ委譲し、RetryQueueUpdateDecision のリスト
   （execution_result・outcome・target_status・reason）を得る
        ↓
③ RetryManager は ②で得た RetryQueueUpdateDecision のリストと
   remove_fn=self._queue.remove を
   self._queue_removal_executor.apply_all(decisions, remove_fn)
   （RetryQueueRemovalExecutor、本Release新設）へ委譲する
        ↓
④ RetryQueueRemovalExecutor が各 RetryQueueUpdateDecision について
   outcome を読み取り、COMPLETE/FAILならrun_idを
   decision.execution_result.dispatch_event.candidate_event.run_id から
   取得し remove_fn(run_id) を呼び出す。NOOPなら remove_fn を呼び出さない
        ↓
⑤ RetryQueueManager.remove(run_id)（v3.1.0、無変更）が実行され、
   該当項目をQueueから取り消し（status=CANCELLED後、内部ストアから削除）、
   RetryQueueResult（REMOVED / NOT_FOUND）を返す。RETRY_QUEUE_ENABLED=false
   の場合は NullRetryQueueManager.remove() が DISABLED を返す
        ↓
⑥ RetryQueueRemovalExecutor は ⑤の結果（またはNOOPの場合はNone）を
   RetryQueueRemovalResult（decision・attempted・queue_result・reason）
   として1件生成する
        ↓
⑦ apply_retry_queue_removals() の戻り値として ⑥のリストを返す
```

`retry_queue`パッケージへの直接importは`retry_queue_removal_executor.py`
には発生しない（`RetryQueueResult`は型ヒントとして参照するが、
`RetryQueueManager` / `NullRetryQueueManager`はimportしない。実際の
`remove()`呼び出しは`RetryManager`が保持する`self._queue`経由で行われる）。

---

## 11. Boundary（今回入れない境界線）

本Releaseが**構造的に**実行不可能にする操作、および境界維持の方法を明示する。

### 11.1 `RetryQueueRemovalExecutor`が`RetryQueueManager`型に依存しない境界

| 確認観点 | 本Releaseでの扱い |
|---|---|
| `retry_queue_removal_executor.py`に`from retry_queue import RetryQueueManager`が存在するか | 存在しない。importは`retry_queue`から`RetryQueueResult`（型ヒントのみ）、`.retry_queue_update_decider`（`retry_engine`パッケージ内）のみ |
| `RetryQueueRemovalExecutor`が`RetryQueueManager` / `NullRetryQueueManager`型を参照するか | しない。remove操作は`remove_fn: Callable[[str], RetryQueueResult]`として関数で受け取る |
| `RetryQueueRemovalExecutor.apply()` / `apply_all()`が`RetryQueueManager`のインスタンスを保持する経路を持つか | 持たない。コンストラクタは引数を一切取らない |

### 11.2 `NOOP`（`SKIPPED` / `NOT_FOUND` / `DISABLED`）に関する境界

| 操作 | 本Releaseでの扱い | 根拠 |
|---|---|---|
| `NOOP`判定項目に対する`remove()`呼び出し | 呼び出し不可 | `RetryQueueRemovalExecutor.apply()`は`decision.outcome`が`COMPLETE` / `FAIL`のいずれでもない場合、`remove_fn`を一切呼び出さずに`attempted=False`を返す（4章） |
| `SKIPPED`（`max_attempts`到達）由来の`NOOP`項目の除去・Dead Letter Queueへの振り分け | 対象外 | ユーザー指示・Charter注記により、本Releaseでは意図的にスコープ外とする。当該項目は本Release後もQueueに滞留し続ける |
| `NOT_FOUND`（Monitor未登録）由来の`NOOP`項目の除去 | 対象外 | 同上（`COMPLETE` / `FAIL`以外はいずれもremove対象外という一貫した扱い） |
| `DISABLED`（Retry Engine無効）由来の`NOOP`項目の除去 | 対象外 | 同上 |

### 11.3 実行・Queue操作に関する境界

| 操作 | 本Releaseでの扱い | 根拠 |
|---|---|---|
| `RetryQueueManager.dequeue()`の本格運用 | 呼び出し不可 | `RetryQueueRemovalExecutor`・`apply_retry_queue_removals()`のいずれも`self._queue.dequeue`を参照しない。既存の`dequeue_retry()`（v3.2.0、薄い委譲）は無変更のまま維持されるが、`apply_retry_queue_removals()`からは呼び出されない |
| `RetryQueueManager.enqueue()`の呼び出し | 呼び出し不可 | 同上。`apply_retry_queue_removals()`は`self._queue.remove`のみを`remove_fn`として渡す |
| `RetryQueueRemovalResult`の永続化 | 対象外 | `RetryQueueRemovalExecutor`はStateless（結果を内部にキャッシュしない） |
| Retry Policyによる選別基準の拡張 | 発生しない | `RetryQueueRemovalExecutor`は`decision.outcome`のみを参照し、優先度・件数上限等の判定は一切行わない |
| Queue最適化（heapq化等） | 対象外 | `RetryQueueManager`自体は無改修（本Releaseのスコープ外） |
| Scheduler改修 | 対象外 | `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source`はいずれも無改修 |
| 既存コンポーネント（`RetryQueueUpdateDecider` / `RetryExecutionSelector` / `RetryExecutionCoordinator` / `RetryQueueManager`）への影響 | 発生しない | 本Releaseは`retry_engine`配下（新規1ファイル・`retry_manager.py`・`__init__.py`）のみを変更する |

Acceptance Criteria（Charter 9章）の「構造的確認」は、上記の表と1対1で
対応する形でテストする（`RetryQueueRemovalExecutor`のソースコードに
`RetryQueueManager` / `NullRetryQueueManager`への参照が存在しないことを
コードレビュー・Spyオブジェクトによるテストの両面で確認する。加えて
`NOOP`判定項目について`remove_fn`が呼び出されないことをSpyで確認する）。

---

## 12. Future Extension

* **`SKIPPED`（`max_attempts`到達）のQueue滞留対応**：本Releaseで唯一
  `NOOP`のまま据え置かれる項目。除去する（`FAIL`相当として扱う）か、
  Dead Letter Queueへ振り分けるかは次Release以降の検討事項とする
  （`docs/design/retry_queue_update_foundation.md` 12章 Future Extension・
  ROADMAP.md 569行目で既に記録済み）
* **Retry Queue Persistence**：Queue永続化（SQLite/Redis等）。本Release
  でも引き続き対象外
* **Retry Policy拡張**：`RetryExecutionSelector`の選別基準拡張
  （優先度・件数上限）。本Releaseでも引き続き対象外
* **Retry Metrics / Monitoring**：`RetryQueueRemovalResult`のリストを
  集計し、除去成功率・`NOT_FOUND`発生率等を可視化する仕組み
* **実運用のComposition Root**：`SchedulerEngine.run_due()`の結果を
  実際に`RetryManager.apply_retry_queue_removals()`へ渡して回す
  起動スクリプトは引き続き未着手

---

## 13. Compatibility

* `RetryManager.__init__` / `from_config()`への`queue_removal_executor`
  オプション引数追加のみ。既存の全呼び出しパターン（`queue=...` /
  `event_consumer=...` / `event_dispatcher=...` /
  `execution_selector=..., execution_coordinator=...` /
  `queue_update_decider=...`を含む）は、本Release後もまったく同じ結果になる
* `retry()` / `enqueue_retry()` / `dequeue_retry()` /
  `recognize_retry_events()` / `dispatch_retry_events()` /
  `execute_dispatchable_retries()` / `decide_retry_queue_updates()`
  （`RetryManager` / `NullRetryManager`とも）は1行も変更しない
* `retry_event_consumer.py` / `retry_event_dispatcher.py` /
  `retry_execution_selector.py` / `retry_execution_coordinator.py` /
  `retry_queue_update_decider.py` / `retry_config.py` / `retry_executor.py` /
  `retry_policy.py` / `retry_request.py` / `retry_result.py`は無改修
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
  `retry_queue`配下の全ファイルも無改修
* 新規の環境変数を追加しないため、`.env` / `.env.example`の変更も不要
* 既存の`RetryManager()` / `RetryManager.from_config(...)`呼び出しテスト
  （v3.0.0〜v4.1.0）は無改修のまま全PASSする想定

---

## 14. Design Decisions（設計判断の根拠）

### Design Decision #1：新規コンポーネントは`retry_engine`パッケージ内の1ファイルに配置する

Charter 8章 Open Question 1に対し、`retry_queue_removal_executor.py`
（`RetryQueueRemovalResult` / `RetryQueueRemovalExecutor`）の1ファイルに
集約する。v3.8.0〜v4.1.0と同じ「1Release1ファイル」の成長パターンを踏襲する。

### Design Decision #2：remove操作は`remove_fn`として関数で受け取る

Charter 8章 Open Question 2に対し、2章 案Aを採用する。v4.0.0
`RetryExecutionCoordinator`の`retry_fn`パターンと同じ設計言語を継承し、
`RetryQueueManager`型への直接依存を避ける。

### Design Decision #3：`COMPLETE`と`FAIL`を区別せず、いずれもremove対象とする

ユーザー指示「COMPLETE / FAIL の Queue反映」に対応する。`FAIL`
（再実行が実行されたが失敗した）場合も、v4.1.0の判定方針上「再実行が
実際に行われた」ことは確定しているため、Queue上に留め置く理由がない。
再試行が必要であれば、それは新たな`enqueue_retry()`呼び出し（Retry
Policyの責務）によって再度Queueへ投入されるべきであり、失敗した古い
Queue項目をそのまま残すことは「1つのrun_idにつき1つのQueue項目」という
既存モデルと矛盾する。

### Design Decision #4：`NOOP`（`SKIPPED`含む）はいずれもremove対象外のまま据え置く

ユーザー指示「SKIPPED / NOT_FOUND / DISABLED / NOOP は remove 対象外」
「SKIPPED（max_attempts到達）は現時点では remove() を持たず Queue に
滞留する仕様」に対応する。ROADMAP.md 569行目が示す次Release検討事項
（`SKIPPED`の滞留対応）には本Releaseでは踏み込まない。

### Design Decision #5：`RetryQueueRemovalResult`は`NOOP`項目も結果リストに含める（除外しない）

`decisions`のうち`COMPLETE` / `FAIL`のものだけを`remove_fn`にかけ、
`NOOP`のものは結果リストから除外する設計も検討したが、`decide_all()`
（v4.1.0）と`apply_all()`の対応関係（入力件数と出力件数が一致する）を
維持し、呼び出し元が「どのdecisionがremove対象外だったか」を`attempted
=False`のエントリとして確認できるようにするため、`NOOP`も結果に含める。

### Design Decision #6：`RetryQueueResult.outcome == NOT_FOUND` / `DISABLED`をエラーとして扱わない

`RetryQueueManager.remove()`（v3.1.0）の既存の正常な結果の範囲内であり、
`RetryQueueRemovalExecutor`はこれらに対する例外処理・特別扱いを追加しない
（本プロジェクトの「発生しうるシナリオ以外へのエラーハンドリングを
追加しない」という開発方針、v4.0.0 Design Decision #7・v4.1.0 Design
Decision #3と同じ判断言語）。

### Design Decision #7：`RetryQueueRemovalExecutor`は`dry_run`を一切扱わない

`RetryManager.apply_retry_queue_removals(events, dry_run=False)`が
`dry_run`を受け取るのは`decide_retry_queue_updates()`（v4.1.0）へ
そのまま伝播するためであり、`RetryQueueRemovalExecutor`自体は`dry_run`
の概念を知らない（v4.1.0 Design Decision #4と同じSingle Responsibility
の徹底）。

---

## 15. Charter Open Questions への回答

Charter（`docs/design/retry_queue_removal_foundation_charter.md`）8章で
保留した8項目に対する結論。

1. **新規コンポーネントの名称・配置場所**：`retry_engine`パッケージ内の
   新規1ファイル（`retry_queue_removal_executor.py`）、クラス名
   `RetryQueueRemovalExecutor`（14章 Design Decision #1）
2. **remove操作の受け取り方**：`remove_fn: Callable[[str],
   RetryQueueResult]`として関数で受け取る（2章 案A・14章 Design Decision #2）
3. **戻り値の型**：`RetryQueueRemovalResult(decision, attempted,
   queue_result, reason)`という専用の`frozen dataclass`を新設する
   （14章 Design Decision #5）
4. **`run_id`の取得経路**：`decision.execution_result.dispatch_event.
   candidate_event.run_id`（4章 除去方針）
5. **`RetryManager`への委譲メソッドの名称・粒度**：
   `apply_retry_queue_removals(events, dry_run=False)`1メソッドのみ
   （6章）
6. **新規コンポーネントの構築責務**：`queue_removal_executor`引数省略時は
   `RetryQueueRemovalExecutor()`を自動構築する（自動フォールバック方式、
   v3.8.0〜v4.1.0と同じ判断）
7. **`NullRetryManager`側の扱い**：同名メソッドを追加し、常に空リストを
   返す（6章）
8. **`NOOP`項目の扱いの明示方法**：結果リストから除外せず、
   `attempted=False`のエントリとして含める（14章 Design Decision #5）

---

## 16. Architecture Review

状態：**Approve with Recommendations**（Claude Codeによる自己点検。
指摘事項は1件、実装をブロックしない）。

### 16.1 レビュー観点別の判定

| # | 観点 | 判定 | 根拠 |
|---|---|---|---|
| 1 | `RetryQueueRemovalExecutor`の責務が「除去の実行のみ」に限定されているか | **限定されている** | コンストラクタ引数を一切取らず、`RetryQueueManager` / `NullRetryQueueManager`への参照を持たない。`remove_fn`をメソッド引数として受け取るのみ（6章・11.1節） |
| 2 | `COMPLETE` / `FAIL`のみがremove対象になっているか | **なっている** | `_REMOVABLE_OUTCOMES = (COMPLETE, FAIL)`という明示的なタプルで判定し、それ以外（`NOOP`）は`remove_fn`を一切呼び出さない（4章・6章） |
| 3 | `run_id`の取得が既存データを分解するだけで、追加の突き合わせを必要としないか | **必要としない** | `decision.execution_result.dispatch_event.candidate_event.run_id`は既存フィールドの単純なアクセスであり、`RetryQueueManager.list()`等の追加問い合わせは発生しない（4章・v4.1.0 Architecture Review 16.1節 観点2で経路自体は事前確認済み） |
| 4 | `RetryQueueUpdateDecider` / `RetryExecutionSelector` / `RetryExecutionCoordinator` / `RetryQueueManager`を無改修に保てているか | **保てている** | 5章 Package Structureのとおり、いずれもファイル差分なし |
| 5 | `RetryManager`の変更が薄い委譲に留まっているか | **留まっている** | `apply_retry_queue_removals()`は`self.decide_retry_queue_updates()`（無変更）→`self._queue_removal_executor.apply_all()`の2行のみで完結する（6章）。v4.1.0と同じ薄さ |
| 6 | 既存APIの後方互換性が維持されているか | **維持されている** | `__init__` / `from_config()`は末尾にデフォルト`None`の`queue_removal_executor`を追加するのみ。既存6メソッドはいずれも無変更（13章） |
| 7 | `NOOP`（`SKIPPED`含む）がremove対象外のまま構造的に保たれているか | **保たれている** | `apply()`が`decision.outcome not in _REMOVABLE_OUTCOMES`の分岐で`remove_fn`を呼び出さずに`return`する。Spyオブジェクトによる呼び出し回数確認で構造的に検証可能（11.2節） |
| 8 | `RetryQueueManager.dequeue()` / `enqueue()`への到達経路がないか | **ない** | `apply_retry_queue_removals()`は`self._queue.remove`のみを`remove_fn`として渡し、`self._queue.dequeue` / `self._queue.enqueue`への参照を一切保持しない（11.3節） |
| 9 | Foundation First / SRP / Statelessが守られているか | **守られている** | Foundation First：`SKIPPED`滞留対応は次Releaseへ送っている。SRP：除去実行のみの単一責任。Stateless：コンストラクタ引数なし、内部状態なし |
| 10 | 新規の外部パッケージ依存方向が発生しないか | **発生しない** | `retry_queue_removal_executor.py`は`retry_queue`から`RetryQueueResult`（型ヒント）のみをimportし、`RetryQueueManager`はimportしない（11.1節） |
| 11 | 既存Regressionへの影響がないか | **影響なし** | `RetryManager` / `NullRetryManager`の既存メソッド・コンストラクタはいずれも無変更。新規メソッド1つ・新規ファイル1つの追加のみ |

### 16.2 SOLID

* **単一責任（SRP）**：`RetryQueueRemovalExecutor`は「`RetryQueueUpdateDecision`
  から除去要否を判定し、要否に応じて`remove_fn`を呼び出す」という1つの
  関心事のみを持つ
* **開放閉鎖（OCP）**：既存メソッド・既存コンポーネントに変更を加えず、
  新規ファイル・新規メソッドの追加のみで機能を拡張している。将来
  `SKIPPED`の扱いを精緻化する場合も`_REMOVABLE_OUTCOMES`の拡張、または
  `RetryQueueUpdateDecider`側の判定変更で対応可能
* **リスコフの置換（LSP）**：`RetryManager` / `NullRetryManager`とも
  同名の`apply_retry_queue_removals(events, dry_run=False) ->
  list[RetryQueueRemovalResult]`を持ち、`NullRetryManager`は常に空集合を
  返す部分集合として振る舞う
* **インターフェース分離（ISP）**：`apply_retry_queue_removals()`が
  利用するのは`self.decide_retry_queue_updates()`（既存）・
  `self._queue_removal_executor.apply_all()`（新規）の2つのみ
* **依存性逆転（DIP）**：`RetryManager`は`RetryQueueRemovalExecutor`という
  具象クラスに依存する。プロジェクト全体で一貫している既存方針の延長である

### 16.3 残された懸念（Recommendations）

1. **`COMPLETE` / `FAIL`それぞれの独立した単体テスト、および`NOT_FOUND` /
   `DISABLED`が返るケースの単体テスト**：実装時、`COMPLETE`→`REMOVED`・
   `FAIL`→`REMOVED`・`COMPLETE`かつ対象がQueueに存在しない→`NOT_FOUND`・
   `RETRY_QUEUE_ENABLED=false`時→`DISABLED`・`NOOP`→`attempted=False`
   （remove_fn呼び出しなし）の5パターンを独立したテストとして書き、
   Spyオブジェクトで`remove_fn`の呼び出し回数・引数を固定化することを
   推奨する（v4.1.0 16.3節 Recommendation 1と同じ考え方の継承）

いずれも実装を妨げる指摘ではなく、実装時のテスト設計として記録する。

### 16.4 Foundation First・プロジェクト全体との設計整合性

ユーザー指示が要求した「`RetryQueueUpdateDecision`を利用して
`RetryQueueManager.remove()`を初めて実行可能にする」「対象：remove()
呼び出し基盤・Queue項目除去・COMPLETE/FAILのQueue反映・
RetryQueueUpdateDecisionとの接続」「対象外：Queue永続化・Retry Policy・
Retry Metrics・Queue最適化・Scheduler改修」という範囲に対し、本設計は
過不足なく合致する。`SKIPPED` / `NOT_FOUND` / `DISABLED` / `NOOP`は
remove対象外のまま構造的に維持され、`RetryManager`は薄い委譲を維持する。

### 16.5 依存方向

```
retry_engine  ── import ──→ scheduler（公開APIのみ：SchedulerEvent型、v3.8.0のまま。本Releaseで新規追加なし）
retry_engine  ── import ──→ retry_queue（v3.2.0のまま。retry_queue_removal_executor.pyはRetryQueueResult型のみ参照。RetryQueueManagerはimportしない）
retry_engine  ── import ──→ workflow_engine（v3.0.0のまま、無改修）
retry_engine  ── import ──→ workflow_monitor（v3.0.0のまま、無改修）
```

`retry_engine`パッケージ内部では、新たに`retry_manager.py →
retry_queue_removal_executor.py`という依存が追加されるが、既存の
`retry_manager.py → retry_queue_update_decider.py`（v4.1.0）と同じ
パッケージ内の依存であり、パッケージ間の新規依存方向ではない。

### 16.6 後方互換性

13章で述べたとおり、変更は`RetryManager.__init__` / `from_config()`への
オプション引数（`queue_removal_executor`）追加と、既存メソッドに影響しない
新規メソッド1つ・新規ファイル1つの追加のみ。既存の全メソッド・
`retry_queue`側もゼロ改修であり、既存呼び出し元への影響はないと判断する。

### 16.7 総評

ユーザー指示が要求した範囲（16.4節）はいずれも設計上満たされている。
Recommendation 1件（16.3節）は実装をブロックする性質のものではなく、
実装時のテスト設計として記録すれば足りる。

**Approve with Recommendations** と判断する。

---

## 17. Status

- [x] Architecture Design ドラフト作成（本文書、Claude Code作成）
- [x] Architecture Review完了（Claude Codeによる自己点検、Approve with
      Recommendations。指摘事項1件は実装時のテスト設計として記録済み）
- [x] ユーザー確認・実装可否判断（承認済み）
- [x] Implementation完了（`retry_queue_removal_executor.py`新規・
      `retry_manager.py` / `__init__.py`変更）
- [x] テスト完了（`tests/test_e2e_v4_2_0_retry_queue_removal_foundation.py`、
      94/94 PASS。Recommendation 1（5パターンの独立テスト）反映済み）
