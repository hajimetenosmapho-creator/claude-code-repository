# v4.1.0 Retry Queue Update Foundation 設計書（Architecture Design）

作成日：2026-07-06
状態：ドラフト（Architecture Review未実施。本文書提示後に実施する）。
`docs/design/retry_queue_update_foundation_charter.md`（Project Charter、
ユーザー承認済み、2026-07-06）を前提とする。

---

## 1. Architecture Overview

Release 4.0（`docs/design/retry_execution_foundation.md`）までで、以下が
確立した。

* `retry_engine`パッケージに`RetryExecutionSelector` / `RetryExecutionCoordinator`
  が新設され、`RetryManager.execute_dispatchable_retries(events)`が、
  `dispatchable=True`の`RetryDispatchEvent`を対象に`RetryManager.retry()`を
  呼び出し、結果を`RetryExecutionResult`（`dispatch_event` / `retry_result`）
  として集約できるようになった
* `RetryExecutionResult`を使って何かをさらに実行する処理（Queueへの
  フィードバック等）は、`retry_engine`側に一切存在しない
* `RetryQueueStatus`（`retry_queue`、v3.1.0）には`COMPLETED` / `FAILED`が
  予約値として定義済みだが、判定ロジックからはまだ到達しない

本Release（v4.1.0）は、`retry_engine`パッケージに**Executionの次の段階**
として、`RetryExecutionResult`を対象に、対応するRetry Queue項目が
`COMPLETED` / `FAILED`のどちらへ更新されるべきか（あるいは更新しないか）を
判定する新規コンポーネントを新設する。ユーザー指示の推奨名称
（`RetryQueueUpdateDecider` / `RetryQueueUpdateDecision`）をそのまま採用し、
判定方針（5種類の`RetryResult`状態 → 3種類の判定結果）を本設計書で明文化する。

```
Retry Engine（受信・整理・実行・判断、v3.0.0〜v4.0.0）
   │
   ├── dispatch_retry_events()（v3.9.0、無改修）
   │      → RetryDispatchEvent のリスト（candidate_event・dispatchable）
   ├── execute_dispatchable_retries()（v4.0.0、無改修）
   │      → RetryExecutionResult のリスト（dispatch_event・retry_result）
   │
   └── decide_retry_queue_updates() ★新設
          │
          └─► RetryQueueUpdateDecider ★新設（判定：RetryExecutionResult → RetryQueueUpdateDecision）
                 │
                 ▼
             RetryQueueUpdateDecision ★新設データ構造
                 （execution_result・outcome・target_status・reason）
```

本Releaseの核心は、「`RetryExecutionResult`が持つ`retry_result.outcome`
（および`workflow_engine_result.overall_success`）から、Queue項目の
更新先状態を導出する」という1つの新しい関心事を、**判定のみに特化した
単一のStatelessコンポーネント**として追加することである。`RetryQueueManager`・
`RetryExecutionSelector`・`RetryExecutionCoordinator`は一切変更しない。
判定結果を実際にQueueへ反映する処理（`remove()`呼び出し・内部ストアの
書き換え）は本Releaseでは一切行わない（Foundation First）。

---

## 2. Design Options（比較検討）

Charter 8章 Open Question 1（配置場所）に対応し、2案を比較する。

### 案A（採用）：`retry_engine`パッケージ内に新規ファイルとして追加する

`retry_queue_update_decider.py`を`retry_engine`配下に新設する。
`RetryManager`は既に`retry_queue`パッケージ（`RetryQueueOutcome` /
`RetryQueueResult` / `RetryQueueManager` / `NullRetryQueueManager`）へ
依存済み（v3.2.0）であるため、`RetryQueueStatus`という追加のシンボルを
importする以上の新規依存は発生しない。

* メリット：
  * v3.8.0（`RetryEventConsumer`）・v3.9.0（`RetryEventDispatcher`）・
    v4.0.0（`RetryExecutionSelector` / `RetryExecutionCoordinator`）と
    同じ「`retry_engine`パッケージが1Releaseごとに1〜2ファイル増える」
    という既存の成長パターンをそのまま踏襲できる
  * 新規の依存**方向**（パッケージ間の矢印）が一切増えない。
    `retry_engine → retry_queue`という既存の矢印の中で、参照する
    シンボルが1つ増えるだけである
  * `RetryManager`が`decide_retry_queue_updates()`という薄い委譲
    メソッドを追加する際、既存の`execute_dispatchable_retries()`
    （v4.0.0）をそのまま呼び出せる（同一パッケージ内のメソッド呼び出し）
* デメリット：
  * `retry_engine`パッケージのファイル数が引き続き増加する
    （本Release後、9ファイル構成になる）

### 案B：独立した新規パッケージ（例：`retry_queue_update`）に切り出す

`retry_scheduler_decision` / `retry_scheduler_source`と同様に、独立した
パッケージとして切り出す。

* メリット：
  * `retry_engine`パッケージ自体のファイル数増加を抑えられる
  * 「`RetryExecutionResult`（retry_engine）を`RetryQueueStatus`
    （retry_queue）の言葉へ変換する」という関心事を、両パッケージから
    独立した第3の境界として明示できる
* デメリット：
  * 新規パッケージが`retry_engine`（`RetryExecutionResult`型の参照）と
    `retry_queue`（`RetryQueueStatus`型の参照）の**両方**に依存する
    形になり、現状どの既存パッケージも持っていない「2つの兄弟パッケージへ
    同時に依存する」という新しい依存パターンを追加することになる
  * `retry_scheduler_decision` / `retry_scheduler_source`は
    いずれも`scheduler`から`retry_queue`への**片方向**の依存のみで
    構成されており、本Releaseだけがこのパターンから外れる
  * `RetryManager`が新規パッケージをimportする必要があり、
    `retry_engine`の`__init__.py`が持つ「`retry_engine`配下の
    シンボルのみをexportする」という一貫性がわずかに崩れる
  * Foundation規模のコンポーネント1つのために新規パッケージを作る
    ことは、本Releaseの「Foundation First」「RetryManagerの責務を
    肥大化させない」という目的に対してオーバーエンジニアリングになる
    リスクがある

### 比較表

| 観点 | 案A（retry_engine内、採用） | 案B（新規パッケージ） |
|---|---|---|
| 新規の依存方向 | 追加なし（既存の`retry_engine → retry_queue`のまま） | 追加あり（新規パッケージ → retry_engine、新規パッケージ → retry_queue） |
| 既存パターンとの整合性 | v3.8.0〜v4.0.0と同じ成長パターン | `retry_scheduler_*`とは異なる双方向依存パターン |
| ファイル数 | `retry_engine`が1ファイル増 | 新規パッケージ1つ（2ファイル程度） |
| Foundation規模との釣り合い | 妥当 | やや過剰 |

**結論**：案Aを採用する。新規の依存方向を一切追加せず、既存の成長パターンを
踏襲できる点が、Foundation Releaseとしての規模感に最も合致する。

---

## 3. Design Policy

Charter 5章 Design Principles、およびユーザー指示を、本設計では以下の形で
具体化する。

1. **Foundation First**：`RetryExecutionResult`を入力に更新先状態を
   判定するところまでを行う。判定結果を実際にQueueへ反映する処理
   （`RetryQueueManager.remove()`呼び出し・内部ストアの書き換え）は
   後続Release（Retry Queue Removal）へ送る（12章）
2. **Single Responsibility**：`RetryQueueUpdateDecider`は「`RetryExecutionResult`
   1件から`RetryQueueUpdateDecision`1件を導出する」ことのみを担う。
   実行（`RetryExecutionCoordinator`）・選別（`RetryExecutionSelector`）・
   Queue操作（`RetryQueueManager`）のいずれも複製・肩代わりしない
3. **Stateless**：`RetryQueueUpdateDecider`は内部状態を一切持たない。
   コンストラクタ引数を取らず、`decide()` / `decide_all()`は渡された
   `RetryExecutionResult`のみから結果を導出する
4. **Backward Compatibility**：`RetryManager.__init__` / `from_config()`に
   `queue_update_decider`引数（デフォルト`None`）を追加し、省略時は
   `RetryQueueUpdateDecider()`に自動フォールバックする。既存の`retry()` /
   `enqueue_retry()` / `dequeue_retry()` / `recognize_retry_events()` /
   `dispatch_retry_events()` / `execute_dispatchable_retries()`は1行も
   変更しない
5. **RetryManagerの責務を肥大化させない**：新規委譲メソッド
   `decide_retry_queue_updates()`は「`execute_dispatchable_retries()`
   （v4.0.0、無変更）への委譲→`RetryQueueUpdateDecider.decide_all()`
   への委譲」という2行の合成のみで完結させる
6. **既存コンポーネントの責務を変更しない**：`RetryExecutionSelector` /
   `RetryExecutionCoordinator` / `RetryQueueManager` / `RetryQueueStatus`
   はいずれも無改修。`RetryQueueStatus.COMPLETED` / `FAILED`は
   v3.1.0で既に予約値として定義済みであり、本Releaseは**新しい値を
   追加する必要が一切ない**（`retry_queue`パッケージ改修の「必要最小限」は
   本Releaseにおいてはゼロである）

---

## 4. 判定方針（Decision Policy）

`RetryQueueUpdateDecider`が扱う入力は`RetryExecutionResult.retry_result`
（`RetryResult`、v3.0.0、無変更）である。`RetryResult.outcome`
（`RetryOutcome`）の4値と、`outcome == RETRIED`の場合にのみ値を持つ
`workflow_engine_result.overall_success`を組み合わせ、ユーザー指示にある
5つの入力シナリオ（SUCCESS / FAILED / SKIPPED / NOT_FOUND / DISABLED）を
次のように`RetryQueueUpdateOutcome`（3値：`COMPLETE` / `FAIL` / `NOOP`）へ
写像する。

| 入力シナリオ | `RetryResult.outcome` | `overall_success` | 判定結果（`RetryQueueUpdateOutcome`） | `target_status` | 判定理由 |
|---|---|---|---|---|---|
| SUCCESS（再実行が成功） | `RETRIED` | `True` | `COMPLETE` | `RetryQueueStatus.COMPLETED` | 再実行が実行され、Workflow Engineが成功（`overall_success=True`）と報告した |
| FAILED（再実行が失敗） | `RETRIED` | `False` | `FAIL` | `RetryQueueStatus.FAILED` | 再実行は実行されたが、Workflow Engineが失敗（`overall_success=False`）と報告した |
| SKIPPED（再実行対象外） | `SKIPPED` | （値なし） | `NOOP` | `None` | `RetryPolicy`が「対象外」と判定し、再実行自体が行われていない。状態が変化していないため、本Foundationでは更新先を確定させない（8章・13章 Design Decision #2） |
| NOT_FOUND（Monitor未登録） | `NOT_FOUND` | （値なし） | `NOOP` | `None` | `run_id`がWorkflow Monitorに存在せず、再実行の成否を判断する材料がない |
| DISABLED（Retry Engine無効） | `DISABLED` | （値なし） | `NOOP` | `None` | Retry Engine自体が無効であり、何も実行されていない |

* `COMPLETE` / `FAIL`の2値のみが`target_status`（`RetryQueueStatus.COMPLETED` /
  `FAILED`）を持つ。`NOOP`の場合は`target_status=None`であり、「Queueを
  更新しない」ことを明示的に表す（`RetryQueueStatus`に対応する値を
  新設しない。3章 Design Policy 6）
* `RETRIED`の場合に`workflow_engine_result`が`None`であることは、
  `RetryExecutor.execute()`（v3.0.0、無変更）の実装上発生しない
  （`retry_result.py`のdocstringに明記済みの既存の不変条件）。したがって
  `RetryQueueUpdateDecider`はこのケースに対する防御的な分岐を持たない
  （発生しえないケースへのエラーハンドリングを追加しない、という
  本プロジェクトの開発方針に従う。13章 Design Decision #3）
* `dry_run`は`RetryQueueUpdateDecider`の判定に一切影響しない。
  `RetryResult`は`dry_run`の値に関わらず同じ形（`outcome` /
  `workflow_engine_result`）で返るため、`RetryQueueUpdateDecider`は
  `dry_run`を意識する必要がない（13章 Design Decision #4）

---

## 5. Package Structure（変更差分）

```
src/retry_engine/
├── __init__.py                    # 変更：新規シンボルのexport追加。docstring更新
├── retry_event_consumer.py        # 無変更（v3.8.0のまま）
├── retry_event_dispatcher.py      # 無変更（v3.9.0のまま）
├── retry_execution_selector.py    # 無変更（v4.0.0のまま）
├── retry_execution_coordinator.py # 無変更（v4.0.0のまま）
├── retry_queue_update_decider.py  # ★新規：RetryQueueUpdateOutcome /
│                                  #        RetryQueueUpdateDecision /
│                                  #        RetryQueueUpdateDecider
├── retry_manager.py               # ★変更：RetryManager.__init__ に
│                                  #        queue_update_decider 引数追加。
│                                  #        decide_retry_queue_updates() を追加。
│                                  #        NullRetryManager にも同名メソッドを追加
├── retry_config.py                # 無変更
├── retry_executor.py              # 無変更
├── retry_policy.py                # 無変更
├── retry_request.py               # 無変更
└── retry_result.py                # 無変更

src/scheduler/                     # 全ファイル無改修
src/retry_scheduler_decision/      # 全ファイル無改修
src/retry_scheduler_source/        # 全ファイル無改修
src/retry_queue/                   # 全ファイル無改修（RetryQueueStatus は
                                    # 既存の公開シンボルをimportするのみ）

tests/
└── test_e2e_v4_1_0_retry_queue_update_foundation.py   # 新規
```

変更対象は`retry_engine`配下2ファイル（`retry_queue_update_decider.py`
新規・`retry_manager.py`変更）と`__init__.py`のみ。`scheduler` /
`retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` /
`retry_event_consumer.py` / `retry_event_dispatcher.py` /
`retry_execution_selector.py` / `retry_execution_coordinator.py`は
いずれも本Releaseでもゼロ改修。

---

## 6. Public API

### `retry_queue_update_decider.py`（新規）

```python
"""
Retry Queue Update Decider（v4.1.0）

RetryQueueUpdateOutcome: RetryExecutionResult 1件に対する判定結果の種別
RetryQueueUpdateDecision: 判定結果を保持する軽量データ
RetryQueueUpdateDecider:  RetryExecutionResult のリストを受け取り、各要素について
                          対応するRetry Queue項目の更新先状態を判定するコンポーネント

設計方針:
    - Queueへの書き込みは一切行わない。RetryQueueManager / NullRetryQueueManager への
      参照を持たない（コンストラクタ引数にも存在しない）。判定のみを行う
      （docs/design/retry_queue_update_foundation.md 3章・10章）。
    - Stateless。RetryExecutionResult を受け取り、判定結果を返すだけの
      純粋関数的なメソッドのみを持つ。
    - RetryQueueStatus（retry_queue の公開シンボル）は型として参照するが、
      RetryQueueManager 等の操作系シンボルは一切importしない
      （同設計書4章の判定方針を参照）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from retry_queue import RetryQueueStatus

from .retry_execution_coordinator import RetryExecutionResult
from .retry_result import RetryOutcome


class RetryQueueUpdateOutcome(Enum):
    COMPLETE = "complete"  # 再実行成功 → RetryQueueStatus.COMPLETED
    FAIL = "fail"          # 再実行失敗 → RetryQueueStatus.FAILED
    NOOP = "noop"          # 再実行が行われていない → 更新しない


@dataclass(frozen=True)
class RetryQueueUpdateDecision:
    """1件のRetryExecutionResultに対する判定結果を保持する軽量データ。"""

    execution_result: RetryExecutionResult
    outcome: RetryQueueUpdateOutcome
    target_status: RetryQueueStatus | None
    reason: str


class RetryQueueUpdateDecider:
    """RetryExecutionResultを対象に、対応するQueue項目の更新先状態を判定するコンポーネント。"""

    def decide_all(
        self, execution_results: list[RetryExecutionResult]
    ) -> list[RetryQueueUpdateDecision]:
        """execution_resultsの各要素についてdecide()を呼び出し、結果のリストを返す。"""
        return [self.decide(execution_result) for execution_result in execution_results]

    def decide(self, execution_result: RetryExecutionResult) -> RetryQueueUpdateDecision:
        """1件のRetryExecutionResultについて、更新先のRetryQueueStatusを判定する。"""
        retry_result = execution_result.retry_result

        if retry_result.outcome == RetryOutcome.RETRIED:
            if retry_result.workflow_engine_result.overall_success:
                return RetryQueueUpdateDecision(
                    execution_result=execution_result,
                    outcome=RetryQueueUpdateOutcome.COMPLETE,
                    target_status=RetryQueueStatus.COMPLETED,
                    reason="retry was executed and workflow_engine_result.overall_success=True.",
                )
            return RetryQueueUpdateDecision(
                execution_result=execution_result,
                outcome=RetryQueueUpdateOutcome.FAIL,
                target_status=RetryQueueStatus.FAILED,
                reason="retry was executed but workflow_engine_result.overall_success=False.",
            )

        return RetryQueueUpdateDecision(
            execution_result=execution_result,
            outcome=RetryQueueUpdateOutcome.NOOP,
            target_status=None,
            reason=f"no retry was executed (retry_result.outcome={retry_result.outcome.value}).",
        )
```

### `retry_manager.py`（変更部分のみ抜粋）

```python
from .retry_queue_update_decider import RetryQueueUpdateDecider, RetryQueueUpdateDecision  # ★新規


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
        queue_update_decider: RetryQueueUpdateDecider | None = None,  # ★新規
    ):
        ...（既存の初期化は無変更）...
        self._queue_update_decider = (
            queue_update_decider if queue_update_decider is not None else RetryQueueUpdateDecider()
        )  # ★新規

    @classmethod
    def from_config(
        cls,
        ...,
        queue_update_decider: RetryQueueUpdateDecider | None = None,  # ★新規
    ) -> "RetryManager | NullRetryManager":
        ...（既存のガード節は無変更）...
        return cls(
            ...,
            queue_update_decider=queue_update_decider,  # ★新規
        )

    # retry() / enqueue_retry() / dequeue_retry() / recognize_retry_events() /
    # dispatch_retry_events() / execute_dispatchable_retries() / _skip_reason() は
    # 無変更（省略）

    def decide_retry_queue_updates(
        self, events: list[SchedulerEvent], dry_run: bool = False
    ) -> list[RetryQueueUpdateDecision]:
        """
        SchedulerEventのリストから、dispatchable=Trueの候補についてretry()を実行し
        （execute_dispatchable_retries()、v4.0.0、無変更）、各RetryExecutionResultに
        ついて対応するRetry Queue項目の更新先状態（COMPLETED / FAILED / 更新なし）を
        判定する。

        2段階の委譲のみで完結する：
            1. self.execute_dispatchable_retries(events, dry_run=dry_run)（v4.0.0、無変更）
            2. self._queue_update_decider.decide_all(execution_results)（新規、判定）

        判定結果を使ってRetryQueueManager.remove() / dequeue()を呼び出す処理、
        判定結果をQueueへ実際に反映する処理は本Releaseには一切存在しない
        （Foundation First）。
        """
        execution_results = self.execute_dispatchable_retries(events, dry_run=dry_run)
        return self._queue_update_decider.decide_all(execution_results)


class NullRetryManager:
    # retry() / enqueue_retry() / dequeue_retry() / recognize_retry_events() /
    # dispatch_retry_events() / execute_dispatchable_retries() は無変更（省略）

    def decide_retry_queue_updates(
        self, events: list[SchedulerEvent], dry_run: bool = False
    ) -> list[RetryQueueUpdateDecision]:
        """
        RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている場合、
        判定自体を一切行わず常に空リストを返す。RetryQueueUpdateDeciderへの参照は
        保持しない。
        """
        return []
```

* `RetryManager.__init__` / `from_config()`とも、既存引数の**末尾**に
  デフォルト値付きの`queue_update_decider`を追加する。既存の位置引数・
  キーワード引数呼び出しはいずれも影響を受けない
* `NullRetryManager.decide_retry_queue_updates()`は`RetryQueueUpdateDecider`
  を一切構築・参照せず、リテラルの空リストを返す

### `__init__.py`の公開シンボル（追加分のみ）

```python
from .retry_queue_update_decider import (       # ★新規
    RetryQueueUpdateDecider,
    RetryQueueUpdateDecision,
    RetryQueueUpdateOutcome,
)

__all__ = [
    ...,  # 既存はすべて維持
    "RetryQueueUpdateOutcome",     # ★新規
    "RetryQueueUpdateDecision",    # ★新規
    "RetryQueueUpdateDecider",     # ★新規
]
```

---

## 7. Class Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryExecutionCoordinator`（v4.0.0、無改修） | `RetryDispatchEvent`を対象に`retry()`を呼び出し`RetryExecutionResult`として集約する | Queue項目の更新先判定・Queue操作 |
| `RetryQueueUpdateDecider`（本Releaseで新規） | `RetryExecutionResult`を対象に、更新先の`RetryQueueUpdateDecision`（`COMPLETE` / `FAIL` / `NOOP`）を判定する | 実行（`retry()`呼び出し）の再実装・Queueへの実際の反映（`remove()`等）・永続化・優先度や再試行回数に基づく選別（Retry Policyの責務） |
| `RetryManager`（本Releaseで変更） | `RetryQueueUpdateDecider`への薄い委譲窓口を持つ（`execute_dispatchable_retries()`との合成のみ） | 判定ロジックの再実装／判定結果の自動的なQueueフィードバック |
| `RetryQueueStatus`（v3.1.0、無改修） | 状態種別の定義（`COMPLETED` / `FAILED`を含む） | 判定ロジック自体 |
| `RetryQueueManager`（v3.1.0、無改修） | Queueへの出し入れ・整列 | Queue項目の更新先判定・実行 |

`RetryQueueUpdateDecider`は`RetryExecutionResult`（v4.0.0、無変更）と
`RetryQueueStatus`（v3.1.0、無変更）という**既存の2つの型を橋渡しする**
ことのみを担い、いずれの型の生成元にも変更を加えない。

---

## 8. Class Diagram

```
┌───────────────────────────────────────────────────┐
│                       RetryManager                       │
│───────────────────────────────────────────────────│
│ - _policy / _executor / _monitor / _queue                │  無変更
│ - _event_consumer / _event_dispatcher                     │  無変更（v3.8.0/v3.9.0）
│ - _execution_selector / _execution_coordinator            │  無変更（v4.0.0）
│ - _queue_update_decider: RetryQueueUpdateDecider           │  ★新設
│───────────────────────────────────────────────────│
│ + __init__(..., queue_update_decider=None)                │  ★引数追加
│ + from_config(...)                                          │  ★引数追加
│ + execute_dispatchable_retries(events, dry_run=False)      │  無変更（v4.0.0）
│     -> list[RetryExecutionResult]                            │
│ + decide_retry_queue_updates(events, dry_run=False)         │  ★新設
│     -> list[RetryQueueUpdateDecision]                        │
└───────────────────────┬───────────────────────────┘
                         │ 委譲①：execute_dispatchable_retries（無変更）
                         │ 委譲②：decide_all
                         ▼
        ┌─────────────────────────────────┐
        │        RetryQueueUpdateDecider         │  ★新設
        │─────────────────────────────────│
        │ + decide(execution_result)             │
        │     -> RetryQueueUpdateDecision         │
        │ + decide_all(execution_results)         │
        │     -> list[RetryQueueUpdateDecision]   │
        └─────────────────┬───────────────┘
                           │ 生成
                           ▼
        ┌─────────────────────────────────────┐
        │           RetryQueueUpdateDecision          │  ★新設（frozen dataclass）
        │─────────────────────────────────────│
        │ + execution_result: RetryExecutionResult    │  （v4.0.0、分解しない）
        │ + outcome: RetryQueueUpdateOutcome           │  ★新設（COMPLETE/FAIL/NOOP）
        │ + target_status: RetryQueueStatus | None     │  （v3.1.0、分解しない）
        │ + reason: str                                │
        └─────────────────────────────────────┘

┌────────────────────────────────────┐
│              NullRetryManager             │
│────────────────────────────────────│
│ + execute_dispatchable_retries(...)        │  無変更（常に[]）
│ + decide_retry_queue_updates(events, ...)   │  ★新設（常に[]）
│     -> list[RetryQueueUpdateDecision]        │
└────────────────────────────────────┘
```

`RetryQueueUpdateDecider`は`RetryManager`にのみ保持され、`NullRetryManager`
はこれを一切参照しない。`RetryQueueUpdateDecider`はコンストラクタ引数を
一切取らない（`RetryQueueManager`への参照も持たない）ため、v4.0.0の
`RetryExecutionCoordinator`（`retry_fn`を引数で受け取る形）よりもさらに
単純な、完全に無状態な変換コンポーネントとなる。

---

## 9. Sequence Diagram

### 9.1 decide_retry_queue_updates()（再実行が成功した場合）

```
Caller       RetryManager   RetryQueueUpdateDecider
  │  events = [SchedulerEvent(job_id="retry:run-001", ...)]                    │
  │                                                                             │
  │  retry_manager.decide_retry_queue_updates(events)                         │
  ├────────►│                                                                  │
  │         │ execution_results = self.execute_dispatchable_retries(events)   │
  │         │  # [RetryExecutionResult(dispatch_event=..., retry_result=      │
  │         │  #   RetryResult(outcome=RETRIED,                                │
  │         │  #     workflow_engine_result=WorkflowEngineResult(              │
  │         │  #       overall_success=True)))]                                │
  │         │                                                                  │
  │         │ self._queue_update_decider.decide_all(execution_results)        │
  │         ├─────────────────────────────────────►│                         │
  │         │                                        │ outcome=RETRIED かつ     │
  │         │                                        │ overall_success=True    │
  │         │                                        │ → COMPLETE              │
  │         │◄─────────────────────────────────────┤                         │
  │         │ [RetryQueueUpdateDecision(                                       │
  │         │    execution_result=...,                                         │
  │         │    outcome=COMPLETE,                                             │
  │         │    target_status=RetryQueueStatus.COMPLETED,                     │
  │         │    reason="retry was executed and ... overall_success=True.")]   │
  │◄────────┤                                                                  │
```

### 9.2 decide_retry_queue_updates()（dispatchable=Falseで実行自体が行われない場合）

```
Caller       RetryManager   RetryQueueUpdateDecider
  │  retry_manager.decide_retry_queue_updates(events)                         │
  ├────────►│                                                                  │
  │         │ execution_results = self.execute_dispatchable_retries(events)   │
  │         │  # []  （v4.0.0のRetryExecutionSelectorがdispatchable=Falseを      │
  │         │  #      除外済みのため、そもそもRetryExecutionResultが生成されない）│
  │         │ self._queue_update_decider.decide_all([])                       │
  │         ├─────────────────────────────────────►│（空リストのため何も判定しない）│
  │         │◄─────────────────────────────────────┤                         │
  │◄────────┤  []                                                              │
```

### 9.3 decide_retry_queue_updates()（RetryPolicyがSKIPPEDと判定した場合）

```
Caller       RetryManager   RetryQueueUpdateDecider
  │  # dispatchable=True だが RetryPolicy.should_retry() が False の候補         │
  │  retry_manager.decide_retry_queue_updates(events)                          │
  ├────────►│                                                                   │
  │         │ execution_results = self.execute_dispatchable_retries(events)    │
  │         │  # [RetryExecutionResult(..., retry_result=RetryResult(            │
  │         │  #     outcome=SKIPPED, ...))]                                     │
  │         │ self._queue_update_decider.decide_all(execution_results)         │
  │         ├─────────────────────────────────────►│                          │
  │         │                                        │ outcome=SKIPPED → NOOP    │
  │         │◄─────────────────────────────────────┤                          │
  │         │ [RetryQueueUpdateDecision(                                        │
  │         │    outcome=NOOP, target_status=None,                              │
  │         │    reason="no retry was executed (retry_result.outcome=skipped).")]│
  │◄────────┤                                                                   │
```

### 9.4 NullRetryManager.decide_retry_queue_updates()

```
Caller       NullRetryManager
  │  null_manager.decide_retry_queue_updates(events)  # eventsの中身は問わない │
  ├────────►│                                                                 │
  │         │ return []  # RetryQueueUpdateDeciderへの参照を持たない            │
  │◄────────┤  []                                                             │
```

---

## 10. Data Flow

```
① 呼び出し元（Composition Root、本Releaseでは未実装）が SchedulerEvent の
   リストを RetryManager.decide_retry_queue_updates(events)
   （または NullRetryManager.decide_retry_queue_updates(events)）へ渡す
        ↓
② RetryManager は self.execute_dispatchable_retries(events, dry_run=dry_run)
   （v4.0.0、無変更）へ委譲し、RetryExecutionResult のリスト
   （dispatch_event・retry_result）を得る
        ↓
③ RetryManager は ②で得た RetryExecutionResult のリストを
   self._queue_update_decider.decide_all(execution_results)
   （RetryQueueUpdateDecider、本Release新設）へ委譲する
        ↓
④ RetryQueueUpdateDecider が各 RetryExecutionResult について
   retry_result.outcome（と RETRIED の場合のみ overall_success）を読み取り、
   4章の判定方針に従って RetryQueueUpdateDecision（outcome・target_status・
   reason）を1件生成する
        ↓
⑤ decide_retry_queue_updates() の戻り値として ④のリストを返す
        ↓
⑥ ⑤で得られた RetryQueueUpdateDecision を使って実際にQueueを更新する処理
   （RetryQueueManager.remove() の呼び出し、内部ストアの status 書き換え、
   dequeue() の本格運用）は、本Releaseでは一切存在しない
   （Foundation First。12章）
```

`retry_queue`パッケージへのimportは、本Releaseでは`RetryQueueStatus`
（型としての参照のみ）に限定される。`RetryQueueManager` /
`NullRetryQueueManager`へのimportは`retry_queue_update_decider.py`には
一切発生しない。

---

## 11. Boundary（今回入れない境界線）

本Releaseが**構造的に**実行不可能にする操作、および境界維持の方法を明示する。

### 11.1 `RetryQueueUpdateDecider`が新規の操作系依存を持たない境界

| 確認観点 | 本Releaseでの扱い |
|---|---|
| `retry_queue_update_decider.py`に`from retry_queue import RetryQueueManager`が存在するか | 存在しない。importは`retry_queue`から`RetryQueueStatus`のみ、`.retry_execution_coordinator` / `.retry_result`（いずれも`retry_engine`パッケージ内）のみ |
| `RetryQueueUpdateDecider`が`RetryQueueManager` / `NullRetryQueueManager`型を参照するか | しない。コンストラクタは引数を一切取らない |
| `RetryQueueUpdateDecider.decide()` / `decide_all()`が`RetryQueueManager`のインスタンスメソッドを呼び出す経路を持つか | 持たない。入力は`RetryExecutionResult`のみで、戻り値も新規データ型のみ |

### 11.2 実行・Queue操作に関する境界

| 操作 | 本Releaseでの扱い | 根拠 |
|---|---|---|
| `RetryQueueManager.remove()` | 呼び出し不可 | `RetryQueueUpdateDecider`は`RetryQueueManager`への参照を一切持たない（コンストラクタが引数を取らない）。`decide_retry_queue_updates()`も`self._queue`を一切参照しない |
| `RetryQueueManager.dequeue()`の本格運用 | 呼び出し不可 | 同上。既存の`dequeue_retry()`（v3.2.0、薄い委譲）は無変更のまま維持されるが、`decide_retry_queue_updates()`からは呼び出されない |
| `RetryQueueUpdateDecision`の永続化 | 対象外 | `RetryQueueUpdateDecider`はStateless（`RetryQueueUpdateDecision`を内部にキャッシュしない）。呼び出しのたびに引数で渡された`execution_results`のみから結果を導出する |
| `RetryQueueStatus.COMPLETED` / `FAILED`への実際の到達（Queue内部ストアの書き換え） | 対象外 | `target_status`は判定結果として返すのみで、`RetryQueueItem.status`を実際に書き換える処理は存在しない（次Release「Retry Queue Removal」の対象） |
| Retry Policyによる選別基準の拡張 | 発生しない | `RetryQueueUpdateDecider`は`retry_result.outcome`と`overall_success`のみを参照し、優先度・件数上限等の判定は一切行わない |
| 既存コンポーネント（`RetryExecutionSelector` / `RetryExecutionCoordinator` / `RetryQueueManager`）への影響 | 発生しない | 本Releaseは`retry_engine`配下（新規1ファイル・`retry_manager.py`・`__init__.py`）のみを変更する |

Acceptance Criteria（Charter 9章）の「構造的確認」は、上記の表と1対1で
対応する形でテストする（`RetryQueueUpdateDecider`のソースコードに
`RetryQueueManager` / `NullRetryQueueManager`への参照が存在しないことを
コードレビュー・Spyオブジェクトによるテストの両面で確認する）。

---

## 12. Future Extension

* **Retry Queue Removal**：`RetryQueueUpdateDecision`（本Release新設）が
  持つ`target_status`（`COMPLETED` / `FAILED` / `None`）を使って、実際に
  `RetryQueueManager.remove()`を呼び出し、Queueから該当項目を除去する
  自動化。`execution_result.dispatch_event.candidate_event.candidate`
  （`RetryQueueItem`相当）を経由して、どのQueue項目に対する判定かを
  追加の突き合わせなしに特定できる（本Releaseで`RetryQueueUpdateDecision`
  が`execution_result`を保持したまま返す設計にしている理由）
* **`NOOP`判定の精緻化**：現状`SKIPPED` / `NOT_FOUND` / `DISABLED`は
  一律`NOOP`（更新しない）としているが、将来的には
  * `SKIPPED`のうち「既に成功していたために対象外となったケース」
    （`monitor_status`が`RetryPolicy.target_statuses`に含まれない）を
    `COMPLETE`として扱うべきかどうか
  * `NOT_FOUND`が示す「Queue項目が孤立している」状態をDead Letter Queue
    （ROADMAP記載の別項目）へ振り分けるべきかどうか
  といった判断が必要になる可能性がある。本Releaseでは判定ロジックを
  単純に保つため、これらはいずれも`NOOP`という安全側の結果に統一し、
  将来のRelease（Retry Queue Removal・Retry Policy拡張）に委ねる
  （4章 判定方針で明示的に記録済み）
* **Retry Metrics / Monitoring**：`RetryQueueUpdateDecision`のリストを
  集計し、成功率・失敗率・NOOP率等を可視化する仕組み（ROADMAP記載の
  別項目）
* **実運用のComposition Root**：`SchedulerEngine.run_due()`の結果を
  実際に`RetryManager.decide_retry_queue_updates()`へ渡して回す
  起動スクリプトは引き続き未着手（v3.4.0から持ち越し）

---

## 13. Compatibility

* `RetryManager.__init__` / `from_config()`への`queue_update_decider`
  オプション引数追加のみ。既存の`RetryManager(policy, executor, monitor)` /
  `RetryManager(policy, executor, monitor, queue=...)` /
  `RetryManager(policy, executor, monitor, event_consumer=...)` /
  `RetryManager(policy, executor, monitor, event_dispatcher=...)` /
  `RetryManager(policy, executor, monitor, execution_selector=..., execution_coordinator=...)` /
  `RetryManager.from_config(...)`（新規引数を渡さない場合）は、本Release後も
  まったく同じ結果になる
* `retry()` / `enqueue_retry()` / `dequeue_retry()` /
  `recognize_retry_events()` / `dispatch_retry_events()` /
  `execute_dispatchable_retries()`（`RetryManager` / `NullRetryManager`とも）
  は1行も変更しない
* `retry_event_consumer.py` / `retry_event_dispatcher.py` /
  `retry_execution_selector.py` / `retry_execution_coordinator.py` /
  `retry_config.py` / `retry_executor.py` / `retry_policy.py` /
  `retry_request.py` / `retry_result.py`は無改修
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
  `retry_queue`配下の全ファイルも無改修
* 新規の環境変数を追加しないため、`.env` / `.env.example`の変更も不要
* 既存の`RetryManager()` / `RetryManager.from_config(...)`呼び出しテスト
  （v3.0.0〜v4.0.0）は無改修のまま全PASSする想定（コンストラクタ・
  `from_config()`のシグネチャ変更は末尾へのデフォルト値付き引数追加のみ
  であり、位置引数・キーワード引数いずれの既存呼び出しにも影響しない）

---

## 14. Design Decisions（設計判断の根拠）

### Design Decision #1：新規コンポーネントは`retry_engine`パッケージ内の1ファイルに配置する

Charter 8章 Open Question 1に対し、`retry_queue_update_decider.py`
（`RetryQueueUpdateOutcome` / `RetryQueueUpdateDecision` /
`RetryQueueUpdateDecider`）の1ファイルに集約する（2章 案A）。

* v4.0.0は「判定」と「実行」という異なる関心事を2ファイルに分離したが、
  本Releaseは「判定」という単一の関心事のみを追加するため、v3.8.0・
  v3.9.0と同じ「1Release1ファイル」のシンプルさに戻す
* `RetryQueueUpdateOutcome`（Enum）・`RetryQueueUpdateDecision`
  （dataclass）・`RetryQueueUpdateDecider`（判定ロジック）は密接に
  関連する1セットであり、`retry_queue_result.py`（`RetryQueueOutcome` +
  `RetryQueueResult`を1ファイルにまとめる、v3.1.0の既存パターン）と
  同じ構成方針を踏襲する

### Design Decision #2：`SKIPPED` / `NOT_FOUND` / `DISABLED`はいずれも`NOOP`に統一する

ユーザー指示の判定方針（4章）に対応する。

* 「再実行が実際に実行されたかどうか」（`outcome == RETRIED`）を
  唯一の分岐点とし、実行されなかった3種類（`SKIPPED` / `NOT_FOUND` /
  `DISABLED`）はいずれも「Queueの状態を変える根拠がない」という共通の
  性質を持つため、`NOOP`という単一の安全側の結果に統一する
* `SKIPPED`を`FAIL`として扱う案も検討したが、`SKIPPED`は「再試行の
  上限に達した」場合と「既に対象外の状態になっている（成功後など）」
  場合の両方を含み、後者を`FAIL`とするのは誤りである。本Foundationでは
  この2つを区別する情報を持たないため、`NOOP`という判断を保留する
  結果に統一し、区別が必要になった時点で将来Release（12章 Future
  Extension）に委ねる

### Design Decision #3：`workflow_engine_result`の`None`チェックを行わない

4章の判定方針で述べたとおり、`retry_result.py`のdocstringに明記済みの
既存の不変条件（`workflow_engine_result`は`outcome == RETRIED`の場合のみ
値を持つ）を信頼し、`RetryQueueUpdateDecider.decide()`は`RETRIED`分岐の
中で`retry_result.workflow_engine_result.overall_success`に直接アクセス
する。発生しえないケースに対する防御的な`None`チェックは、本プロジェクトの
「発生しうるシナリオ以外へのエラーハンドリングを追加しない」という開発
方針に反するため追加しない（v4.0.0 Design Decision #7と同じ判断言語）。

### Design Decision #4：`RetryQueueUpdateDecider`は`dry_run`を一切扱わない

`RetryResult`は`dry_run`の値に関わらず同じ形（`outcome` /
`workflow_engine_result`）で返る（`RetryExecutor.execute()`、v3.0.0、
無変更）。したがって`RetryQueueUpdateDecider.decide()` / `decide_all()`
は`dry_run`引数を持たない。`RetryManager.decide_retry_queue_updates(events,
dry_run=False)`が`dry_run`を受け取るのは`execute_dispatchable_retries()`
（v4.0.0）へそのまま伝播するためであり、`RetryQueueUpdateDecider`自体は
`dry_run`の概念を一切知らない（Single Responsibilityの徹底）。

### Design Decision #5：`RetryQueueUpdateDecider`はコンストラクタ引数を一切取らない

v4.0.0の`RetryExecutionCoordinator`は`retry_fn`をメソッド引数として
受け取ったが、`RetryQueueUpdateDecider`は外部関数への依存すら持たない
（判定は純粋に`RetryExecutionResult`の内容だけから導出できるため）。
これにより`RetryExecutionCoordinator`よりもさらに単純な、完全に
無状態な変換コンポーネントとなる（8章 Class Diagram）。

### Design Decision #6：`RetryQueueUpdateDecision`は`execution_result`を保持したまま返す

ユーザー指示の推奨事項（`RetryQueueUpdateDecision`というDTO名称）に対応する。

* `RetryExecutionResult`をそのまま保持することで、「どの`RetryDispatchEvent`
  （＝どのQueue候補）に対する判定か」という文脈を失わずに済む
* これにより、将来のRetry Queue Removal（12章 Future Extension）が
  `execution_result.dispatch_event.candidate_event.candidate`
  （`RetryQueueItem`相当）を経由して対象のQueue項目を特定できる
  （v4.0.0 Design Decision #6と同じ設計言語の継承）

### Design Decision #7：`target_status`は`RetryQueueStatus | None`とし、新しいEnum値は追加しない

「更新しない」状態を`RetryQueueStatus`に新しい値（例：`NO_UPDATE`）として
追加する案も検討したが、`RetryQueueStatus`（v3.1.0）へ変更を加えることは
Charter・本設計書3章 Design Policy 6（`retry_queue`パッケージ改修は
「必要最小限」＝本Releaseにおいてはゼロ、を維持する）に反する。判定結果
レベルの`RetryQueueUpdateOutcome.NOOP`という新しいEnum（`retry_engine`側に
新設）と、`target_status=None`という組み合わせで「更新しない」を表現する
ことで、`RetryQueueStatus`自体には一切手を加えずに済む。

---

## 15. Charter Open Questions への回答

Charter（`docs/design/retry_queue_update_foundation_charter.md`）8章で
保留した9項目に対する結論。

1. **配置場所**：`retry_engine`パッケージ内の新規1ファイル
   （`retry_queue_update_decider.py`）（2章 案A・14章 Design Decision #1）
2. **新規コンポーネントの名称**：`RetryQueueUpdateDecider`（判定のみ）。
   ユーザー指示の推奨名称をそのまま採用（14章 Design Decision #1）
3. **戻り値の型**：`RetryQueueUpdateDecision(execution_result, outcome,
   target_status, reason)`という専用の`frozen dataclass`を新設する
   （14章 Design Decision #6）
4. **判定基準の詳細な場合分け**：`RETRIED`かつ`overall_success=True`は
   `COMPLETE`、`RETRIED`かつ`overall_success=False`は`FAIL`、
   `SKIPPED` / `NOT_FOUND` / `DISABLED`はいずれも`NOOP`に統一する
   （4章 判定方針・14章 Design Decision #2）
5. **`RetryManager`への委譲メソッドの名称・粒度**：
   `decide_retry_queue_updates(events, dry_run=False)`1メソッドのみ
   （6章・14章 Design Decision #4）
6. **新規コンポーネントの構築責務**：`queue_update_decider`引数省略時は
   `RetryQueueUpdateDecider()`を自動構築する（自動フォールバック方式、
   v3.8.0〜v4.0.0と同じ判断）
7. **`NullRetryManager`側の扱い**：同名メソッドを追加し、常に空リストを
   返す（6章）
8. **`RetryQueueStatus`参照の要否**：`retry_engine`は既に`retry_queue`
   パッケージへ依存済み（v3.2.0）であるため、型としての参照は許容範囲と
   結論する。`RetryQueueUpdateDecider`は`RetryQueueManager`等の操作系
   シンボルは一切importしない、という区別によってQueue非依存の原則
   （v4.0.0）との整合性を保つ（3章 Design Policy 6・11章 Boundary）
9. **複数件判定時のエラーハンドリング**：`decide()`は`retry_result.outcome`
   と`overall_success`のブール値を読み取るだけの純粋な分岐であり、例外を
   送出しうる処理（外部呼び出し・I/O）を含まないため、fail-fastの是非を
   論じる対象自体が存在しない（14章 Design Decision #3）

---

## 16. Architecture Review

状態：**Approve with Recommendations**（Claude Codeによる自己点検。
指摘事項は2件、実装をブロックしない）。

### 16.1 レビュー観点別の判定

| # | 観点 | 判定 | 根拠 |
|---|---|---|---|
| 1 | `RetryQueueUpdateDecider`の責務が「判定のみ」に限定されているか | **限定されている** | コンストラクタ引数を一切取らず、`RetryQueueManager` / `NullRetryQueueManager`への参照を持たない。`decide()` / `decide_all()`は`RetryExecutionResult`を受け取り`RetryQueueUpdateDecision`を返すだけの純粋関数的メソッド（6章・11.1節） |
| 2 | `RetryQueueUpdateDecision`が次Release（Queue Removal）に接続できる十分な情報を保持しているか | **保持している** | `execution_result`（→`dispatch_event`→`candidate_event`→`run_id` / `candidate`）を分解せず保持するため、`RetryQueueManager.remove(run_id)`に必要な`run_id`へ追加の突き合わせなしに到達できる。加えて`retry_scheduler_source.py`（v3.3.0）の実装を確認した結果、Queue項目は`RetryQueueManager.list()`（非破壊的な読み取り）経由でCandidate化されており、`dequeue()`によって既にQueueから取り除かれてはいない。したがって次Releaseが`target_status`とともに`remove(run_id)`を呼び出す設計は、現在のQueue状態モデルと矛盾しない（12章 Future Extension） |
| 3 | `SKIPPED` / `NOT_FOUND` / `DISABLED`を`NOOP`とする判断が安全側の設計として妥当か | **妥当** | 「再実行が実際に実行されたか」のみを分岐点とし、実行されなかったケースでQueue状態を動かす根拠を持たないため、誤って`COMPLETE` / `FAIL`と判定するリスクを構造的に排除している（14章 Design Decision #2）。ただし`SKIPPED`（特に`max_attempts`到達）が恒久的に`NOOP`のまま滞留するリスクは残る（16.3節 Recommendation 2） |
| 4 | `RetryQueueManager` / `RetryExecutionSelector` / `RetryExecutionCoordinator`を無改修に保てているか | **保てている** | 5章 Package Structureのとおり、いずれもファイル差分なし。`RetryQueueUpdateDecider`は`RetryQueueStatus`（型）のみをimportし、`RetryQueueManager`はimportしない |
| 5 | `RetryManager`の変更が薄い委譲に留まっているか | **留まっている** | `decide_retry_queue_updates()`は`self.execute_dispatchable_retries()`（無変更）→`self._queue_update_decider.decide_all()`の2行のみで完結する（6章）。v4.0.0の3行委譲よりもさらに薄い |
| 6 | 既存APIの後方互換性が維持されているか | **維持されている** | `__init__` / `from_config()`は末尾にデフォルト`None`の`queue_update_decider`を追加するのみ。既存5メソッド（`retry()` / `enqueue_retry()` / `dequeue_retry()` / `recognize_retry_events()` / `dispatch_retry_events()`）と`execute_dispatchable_retries()`（v4.0.0）はいずれも無変更（13章） |
| 7 | `retry_queue`パッケージに不要な変更が入らない設計になっているか | **入らない** | `COMPLETED` / `FAILED`はv3.1.0で既に予約値として定義済みのため、新しい値の追加すら不要。`retry_queue`配下の変更はゼロ（3章 Design Policy 6・14章 Design Decision #7） |
| 8 | 将来の`remove()` / `dequeue()` / 永続化 / Policy / Metricsと責務衝突しないか | **衝突しない** | `RetryQueueUpdateDecider`は判定結果を返すのみで、いずれの操作も呼び出さない（11.2節）。`Policy`（選別基準）は`RetryExecutionSelector`の責務のまま変更なし。`Metrics`は`RetryQueueUpdateDecision`を消費する側に位置づけられ、本Releaseはその生成元を提供するのみ（12章） |
| 9 | Foundation First / SRP / Statelessが守られているか | **守られている** | Foundation First：判定結果を使ったQueue操作を一切追加していない。SRP：判定のみの単一責任。Stateless：コンストラクタ引数なし、内部状態なし |
| 10 | 新規の外部パッケージ依存方向が発生しないか | **発生しない** | `retry_engine → retry_queue`という既存の依存方向の範囲内で、参照するシンボル（`RetryQueueStatus`）が1つ増えるのみ（7章） |
| 11 | 循環importが発生しないか | **発生しない** | 新規の依存方向自体が発生しない |
| 12 | 既存Regressionへの影響がないか | **影響なし** | `RetryManager` / `NullRetryManager`の既存メソッド・コンストラクタはいずれも無変更。新規メソッド1つ・新規ファイル1つの追加のみ |

### 16.2 SOLID

* **単一責任（SRP）**：`RetryQueueUpdateDecider`は「`RetryExecutionResult`
  から更新先状態を判定する」という1つの関心事のみを持つ。実行・選別・
  Queue操作のいずれも持たない
* **開放閉鎖（OCP）**：既存メソッド・既存コンポーネントに変更を加えず、
  新規ファイル・新規メソッドの追加のみで機能を拡張している。将来
  `NOOP`の内訳を精緻化する場合も`RetryQueueUpdateDecider.decide()`の
  内部実装変更のみで対応可能（公開シグネチャ・`RetryQueueUpdateOutcome`
  の既存3値は不変のまま拡張できる）
* **リスコフの置換（LSP）**：`RetryManager` / `NullRetryManager`とも
  同名の`decide_retry_queue_updates(events, dry_run=False) ->
  list[RetryQueueUpdateDecision]`を持ち、`NullRetryManager`は常に
  空集合を返す部分集合として振る舞う
* **インターフェース分離（ISP）**：`decide_retry_queue_updates()`が
  利用するのは`self.execute_dispatchable_retries()`（既存）・
  `self._queue_update_decider.decide_all()`（新規）の2つのみ
* **依存性逆転（DIP）**：`RetryManager`は`RetryQueueUpdateDecider`という
  具象クラスに依存する。プロジェクト全体で一貫している「Null Object
  Patternによるダックタイピングのみで、ABCは導入しない」という既存方針の
  延長である

### 16.3 残された懸念（Recommendations）

1. **`NOOP`3パターンの区別テスト**：`SKIPPED` / `NOT_FOUND` / `DISABLED`は
   いずれも`outcome=NOOP` / `target_status=None`という同じ判定結果に
   写像されるが、`reason`文字列には`retry_result.outcome`の値が
   埋め込まれる。実装時、この3パターンをそれぞれ独立した単体テストとして
   書き、`reason`文字列で区別可能であることを明示的に固定化することを
   推奨する（4章の判定方針表と1対1対応させる）
2. **`SKIPPED`（`max_attempts`到達）のQueue内滞留リスク**：`NOOP`と
   判定された項目（特に再試行上限に達した`SKIPPED`）は、本Releaseでは
   Queueから除去する手段を持たないため、次Release（Retry Queue Removal）
   まで恒久的にQueueに残り続ける可能性がある。12章 Future Extensionに
   記録済みだが、次Release着手時に「`NOOP`のうち`max_attempts`到達分を
   どう扱うか（除去する／Dead Letter Queueへ回す等）」を最初の検討事項
   として明示的に扱うことを推奨する

いずれも実装を妨げる指摘ではなく、実装時のテスト設計、および次Release
以降で状況に応じて対応を検討する事項として記録する。

### 16.4 Foundation First・プロジェクト全体との設計整合性

ユーザー指示が要求した「`RetryExecutionResult`を受け取り、Retry Queueを
どの状態へ更新すべきかを判定する基盤を追加するが、Queueを実際に更新する
処理は実装しない」という範囲に対し、本設計は判定結果
（`RetryQueueUpdateDecision`）を使ってQueueを更新する処理
（`RetryQueueManager.remove()`呼び出し・内部ストアの書き換え）を一切
追加しておらず、スコープの逸脱はない。v3.3.0〜v4.0.0の「Foundation
First・消費者不在の実行ロジックなし」というパターンを、本Releaseでも
踏襲している。

### 16.5 依存方向

```
retry_engine  ── import ──→ scheduler（公開APIのみ：SchedulerEvent型、v3.8.0のまま。本Releaseで新規追加なし）
retry_engine  ── import ──→ retry_queue（v3.2.0のまま。参照シンボルにRetryQueueStatusが加わるが、依存方向自体は追加なし）
retry_engine  ── import ──→ workflow_engine（v3.0.0のまま、無改修）
retry_engine  ── import ──→ workflow_monitor（v3.0.0のまま、無改修）

scheduler                ── import ──→ retry_scheduler_decision（v3.6.0のまま、無改修）
scheduler                ── import ──→ retry_scheduler_source（v3.4.0のまま、無改修）
retry_scheduler_decision ── import ──→ retry_scheduler_source（v3.5.0のまま、無改修）
retry_scheduler_source   ── import ──→ retry_queue（v3.3.0のまま、無改修）
```

`retry_engine`パッケージ内部では、新たに
`retry_manager.py → retry_queue_update_decider.py`という依存が追加
されるが、これは既存の`retry_manager.py → retry_execution_selector.py` /
`retry_manager.py → retry_execution_coordinator.py`（v4.0.0）と同じ
パッケージ内の依存であり、パッケージ間の新規依存方向ではない。

### 16.6 後方互換性

13章で述べたとおり、変更は`RetryManager.__init__` / `from_config()`への
オプション引数（`queue_update_decider`）追加と、既存メソッドに影響しない
新規メソッド1つ・新規ファイル1つの追加のみ。既存の`retry()` /
`enqueue_retry()` / `dequeue_retry()` / `recognize_retry_events()` /
`dispatch_retry_events()` / `execute_dispatchable_retries()`・
`retry_execution_selector.py` / `retry_execution_coordinator.py` /
`retry_config.py` / `retry_executor.py` / `retry_policy.py` /
`retry_request.py` / `retry_result.py`はいずれも無変更。`retry_queue`側も
ゼロ改修であり、既存呼び出し元への影響はないと判断する。

### 16.7 総評

ユーザー指示が要求した8つのレビュー観点（16.1節、# 1〜8）はいずれも
設計上満たされている。Recommendation 2件（16.3節）は実装をブロックする
性質のものではなく、実装時のテスト設計と次Release以降での検討事項として
記録すれば足りる。

**Approve with Recommendations** と判断する。

---

## 17. Status

- [x] Architecture Design ドラフト作成（本文書、Claude Code作成）
- [x] Architecture Review完了（Claude Codeによる自己点検、Approve with
      Recommendations。指摘事項2件は実装時のテスト設計・次Release検討
      事項として記録済み）
- [ ] ユーザー確認・実装可否判断
- [ ] Implementation（本メッセージ時点では未着手）
- [ ] テスト（本メッセージ時点では未着手）
