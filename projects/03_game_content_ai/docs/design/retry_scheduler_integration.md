# v3.3.0 Retry Scheduler Integration 設計書（Architecture Design）

作成日：2026-07-03（Architecture Review反映：2026-07-03）
状態：Architecture Review完了（**Approve with Minor Recommendations**）。指摘事項3点を
本ドキュメントへ反映済み。`docs/design/retry_scheduler_integration_charter.md`
（Project Charter）を前提とする。

> **Architecture Review 反映事項（2026-07-03）**：Architecture Reviewの結果、以下3点の
> 指摘事項を本ドキュメントへ反映した。重大な設計変更は伴わない（依存方向・公開メソッド名・
> Scope・Non-Goalsはいずれも初版から変更なし）。
>
> 1. **Configクラスを追加しない**：初版では明示的に「Configを持たない」としていたが、
>    念のため再確認し、方針を維持したまま3章で理由を明記した
> 2. **Managerパターン（`from_config()`等の起動口を持つ構造）を採用しない**：初版の
>    「単一クラスが `RetryQueueManager | NullRetryQueueManager` のUnion型を受け取り、
>    渡された相手によって挙動が変わる」という設計は、実質的に呼び出し元へ
>    `retry_queue` の型（`NullRetryQueueManager`）を意識させてしまっており、
>    Adapterとしての独立性が不完全だった。本改訂でこれを解消する
> 3. **Null Object Patternの2クラス構成へ変更**：プロジェクト全体で一貫している
>    「実装クラス／Nullクラスのペア（Duck Typing、継承なし）」を本パッケージにも
>    適用し、`RetrySchedulerSource` / `NullRetrySchedulerSource` の2クラス構成とする。
>    これにより、Feature GateやConfigを持たずに「有効／無効」を表現でき、かつ
>    プロジェクトの既存設計言語（`RetryManager`/`NullRetryManager`、
>    `RetryQueueManager`/`NullRetryQueueManager`、`WorkflowEngineManager`/
>    `NullWorkflowEngineManager` 等）と完全に整合する

---

## 1. Architecture Overview

Release 3.2（`docs/design/retry_queue_integration.md`）までで、以下の基盤が整備された。

* Scheduler（v2.6.0）：時刻ベースで実行対象Jobを判定し `SchedulerEvent` を生成する
  だけの層。Retry Queueの存在を一切知らない
* Retry Queue（v3.1.0）：`enqueue` / `dequeue` / `remove` / `list` / `exists` /
  `count` の6操作を提供するQueue管理層。標準ライブラリのみに依存する独立した
  葉パッケージ
* Retry Queue Integration（v3.2.0）：`RetryManager`（retry_engine）が
  `RetryQueueManager` を保持し、`enqueue_retry()` / `dequeue_retry()` で薄く
  委譲する。ただし、これはあくまで「Retry Engine側からQueueを操作できるように
  なった」だけであり、**Queueを定期的に監視する主体（＝将来のSchedulerの役割）は
  いまだ存在しない**

本Release（v3.3.0）は、この「Queueを見る主体がいない」というギャップに対して、
Scheduler側の入口となる新規独立パッケージ `src/retry_scheduler_source/` を追加する。
ただし、Project Charter（4章・8章）で確定したとおり、本Releaseの範囲は
**Adapterの新設と読み取り機能の実装のみ**であり、Scheduler本体（`SchedulerEngine`
等）からの実際の呼び出し配線は行わない。

```
Scheduler          （判断、v2.6.0、無改修）
   │
   │  ※本Releaseでは未接続
   ▼
RetrySchedulerSource / NullRetrySchedulerSource（Adapter、v3.3.0、新規） ★本Release
   │
   └── Retry Queue （Queue管理、v3.1.0、無改修）
          │
          └── （retry_engine / workflow_engine / workflow_monitor 等は
                本Releaseの依存グラフには一切登場しない）
```

`RetrySchedulerSource` は Retry Queue の**補助コンポーネント**として設計するが、
本Releaseのスコープは「Adapterの新設のみ」であり、Scheduler本体との実際の配線
（`SchedulerEngine.evaluate()` へ組み込む等）は行わない（Out of Scope・Charter 4章）。
そのため `src/retry_scheduler_source/` は本Release時点では **どのパッケージからも
呼ばれない、独立したFoundation層**として先行実装される。これは v2.9.0 の
`WorkflowMonitorManager` および v3.1.0 の `RetryQueue` が「実呼び出し元を持たない
まま先行リリースされた」前例（`docs/design/retry_queue_foundation.md` 1章）と
同型のパターンである。

---

## 2. Design Policy

Project Charter の Design Principles（5章）をそのまま踏襲し、本設計では特に
以下の4点を Retry Scheduler Integration 固有の形で具体化する。

1. **Adapter / Bridge パターン**：`RetrySchedulerSource` は Scheduler と
   Retry Queue の間に立つ変換層とする。Scheduler側（将来の呼び出し元）は
   `RetryQueueManager` の存在・内部データ構造・メソッド名を一切知る必要がなく、
   `RetrySchedulerSource` が公開する2メソッド（4章）だけを知っていればよい。
   これにより、将来 `retry_queue` 側のAPIが変化しても、影響は
   `RetrySchedulerSource` の内部実装に閉じる

2. **Null Object Pattern（プロジェクト全体の設計言語との整合）**：本リポジトリの
   既存パッケージ（`retry_queue` / `retry_engine` / `workflow_engine` /
   `workflow_monitor` / `execution_history`）はすべて「実装クラス」と
   「Nullクラス」のペア（継承関係を持たないDuck Typing）を公開しており、
   呼び出し元はどちらが渡されても同じコードで扱える。

   本Releaseもこのパターンに揃え、`RetrySchedulerSource` /
   `NullRetrySchedulerSource` の2クラス構成とする（4章）。ただし他パッケージと
   異なり、**Feature Gate・Configクラス・`from_config()`／`from_env()`という
   形の「起動口（Manager的な構築ロジック）」は持たない**。理由は次のとおり：

   * 本Releaseの`RetrySchedulerSource`が保持する状態は「Queueへの参照」のみで
     あり、Feature Gateで判定すべき対象（環境変数・容量・試行回数上限等）が
     そもそも存在しない
   * 「有効にするか無効にするか」を`RetrySchedulerSource`自身が判定する必要は
     なく、**呼び出し元が `RetrySchedulerSource(queue)` と
     `NullRetrySchedulerSource()` のどちらを構築するかを選ぶだけ**で
     有効／無効を表現できる（`RetryQueueManager` / `NullRetryQueueManager` の
     選択が `RetryQueueConfig.is_ready()` に委ねられているのと対称的に、
     `RetrySchedulerSource` 側の選択は呼び出し元の判断に委ねる）
   * これにより、`RetrySchedulerSourceConfig` のようなConfigクラスも、
     `from_config()` のような起動口メソッドも本Releaseでは不要となる

   初版設計（`RetrySchedulerSource` 単一クラスが `RetryQueueManager |
   NullRetryQueueManager` のUnion型を受け取る）との違いは、**呼び出し元が
   `retry_queue` パッケージの型（`NullRetryQueueManager`）を意識するか否か**
   にある。初版では「無効化したい場合、呼び出し元は `retry_queue` から
   `NullRetryQueueManager` をimportして渡す」必要があった。本改訂では
   `RetrySchedulerSource` 側にも独自のNull実装を用意することで、呼び出し元は
   `retry_scheduler_source` パッケージの型だけを見ればよくなり、Adapterとしての
   独立性が高まる（`RetrySchedulerSource` の `queue` 引数は本改訂で
   `RetryQueueManager`（実体のみ）に narrowing する。4章参照）

3. **Foundation First**：`list()` / `count()` への委譲のみを先に確立する。
   Scheduler本体との実配線・`dequeue()`を用いた実際の取り出し・自動Retry実行は
   すべて後続Releaseへ送る（11章 Future Extension）。

4. **既存モジュール無改修**：`scheduler` / `retry_queue` / `retry_engine` /
   `workflow_engine` / `workflow_monitor` / `execution_history` のいずれも
   変更しない。`RetrySchedulerSource` は `retry_queue` の公開シンボルのみを
   importする独立パッケージとして設計する。

---

## 3. Package Structure

```
src/retry_scheduler_source/
├── __init__.py                  # 公開シンボルのexport（4章）
└── retry_scheduler_source.py    # RetrySchedulerSource / NullRetrySchedulerSource
```

`RetryManager` / `NullRetryManager` が `retry_manager.py` に同居している
（`docs/design/retry_engine_foundation.md`）のと同じ考え方で、
`RetrySchedulerSource` / `NullRetrySchedulerSource` も同一ファイルに同居させる。
両クラスとも数行程度の極小実装であり、`retry_queue` の
`retry_queue_manager.py` / `null_retry_queue_manager.py` のように分離する
必要はないと判断する（ファイルを分離する動機は「`grep`等でダミー実装だけを
追いやすくする」ことだったが、本パッケージはメソッド数が2個のみであり、
その利点よりも「1ファイルで完結する見通しの良さ」を優先する）。

Configファイル・Manager的な起動口ファイルは作らない（2章）。既存パッケージ
（`retry_queue` が6ファイル、`retry_engine` が6ファイル）と比べて最小の
2ファイル構成となるが、これはFoundation Releaseのスコープ（読み取り2メソッドの
みを、実体／ダミーの2クラスで提供する）に対して過不足のない構成である。

既存パッケージへの変更は一切行わない（ゼロ改修）。

---

## 4. Public API

### `retry_scheduler_source.py`

```python
from __future__ import annotations

from retry_queue import RetryQueueItem, RetryQueueManager


class RetrySchedulerSource:
    """
    Retry Queue の状態を Scheduler 側から読み取るための Adapter（実装クラス）。

    RetryQueueManager への参照を Dependency Injection で保持し、list() / count()
    への薄い委譲のみを行う。Queueへの書き込み（enqueue / dequeue / remove）は
    一切行わない。
    """

    def __init__(self, queue: RetryQueueManager):
        self._queue = queue

    def list_pending_retries(self, limit: int | None = None) -> list[RetryQueueItem]:
        """RetryQueueManager.list() への委譲。戻り値をそのまま返す（加工しない）。"""
        return self._queue.list(limit=limit)

    def count_pending_retries(self) -> int:
        """RetryQueueManager.count() への委譲。戻り値をそのまま返す（加工しない）。"""
        return self._queue.count()


class NullRetrySchedulerSource:
    """
    RetrySchedulerSource のダミー実装（Null Object）。

    Retry Queueが無効な場合、またはそもそもQueueと接続したくない呼び出し元が
    使う。retry_queue パッケージへの参照を一切保持せず、常に安全なデフォルト値
    （空リスト・0件）を返す。
    """

    def list_pending_retries(self, limit: int | None = None) -> list[RetryQueueItem]:
        return []

    def count_pending_retries(self) -> int:
        return 0
```

* `RetrySchedulerSource.__init__` は `RetryQueueManager`（実体）のみを受け取る
  （Union型にはしない）。無効化したい場合は `RetrySchedulerSource(...)` を
  構築せず `NullRetrySchedulerSource()` を使う、という選択を呼び出し元に
  委ねる設計とする（2章）
* コンストラクタは `queue` のみを受け取る単純なDIとする。`RetryManager.from_config()`
  が構築済みの `WorkflowEngineManager` / `WorkflowMonitorManager` をDIで受け取り、
  Configから再構築しない設計（`docs/design/retry_engine_foundation.md` 10章
  Design Decision #3）と同じ考え方であり、`RetrySchedulerSource` にも
  `from_config()` は用意しない（そもそも保持するConfigが存在しない）
* メソッド名は `RetryQueueManager` の `list()` / `count()` をそのまま踏襲せず、
  `list_pending_retries()` / `count_pending_retries()` という**Scheduler側の
  語彙**に変換する。これはAdapterパターンの核であり、呼び出し元（将来の
  Scheduler側コード）が「Retry Queueを見ている」ことを意識せず「再実行待ちが
  いくつあるか」という関心事だけを扱えるようにするための命名判断である
* 戻り値の型は `RetryQueueItem`（`retry_queue` の公開型）をそのまま用いる。
  独自DTOへの変換は行わない。これは `RetryResult.workflow_engine_result` が
  `WorkflowEngineResult` をそのまま埋め込む設計（`docs/design/
  retry_engine_foundation.md` 10章 Design Decision #5）と同じ判断であり、
  実際の消費者（Scheduler本体）が存在しない現時点で独自DTOの形状を
  先回りして決め打ちしない（Foundation First）
* `RetrySchedulerSource` と `NullRetrySchedulerSource` の間に継承関係は
  持たせない（`RetryQueueManager` / `NullRetryQueueManager` と同じDuck Typing。
  6章 Class Diagram）

### `__init__.py` の公開シンボル

```python
from .retry_scheduler_source import NullRetrySchedulerSource, RetrySchedulerSource

__all__ = [
    "RetrySchedulerSource",
    "NullRetrySchedulerSource",
]
```

---

## 5. Class Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetrySchedulerSource` | `RetryQueueManager` への参照を保持し、`list_pending_retries()` / `count_pending_retries()` の呼び出しをそのまま中継する | Queue内部の判定ロジック（容量・重複・優先度ソート）の実装／Queueからの取り出し（`dequeue`）／削除（`remove`）／実行判断／実行／有効・無効の自己判定（Feature Gate） |
| `NullRetrySchedulerSource` | `RETRY_QUEUE_ENABLED=false` の場合、または呼び出し元がQueueと接続したくない場合のダミー実装。すべての操作が副作用なく安全なデフォルト値を返す | `retry_queue` への参照の保持・Queueとの通信 |

どちらのクラスも `RetryQueueManager` が提供する6操作のうち `list()` /
`count()` に相当する2メソッドのみを公開する。`enqueue()` / `dequeue()` /
`remove()` / `exists()` へのアクセス手段は一切持たない（`exists()` も
Charter Goals（3章）で明示された「一覧・件数」の範囲外のため、本Releaseでは
公開しない）。

「どちらのクラスを構築するか」の判定ロジック（Feature Gate相当の判断）は、
本パッケージの責務ではなく**呼び出し元の責務**とする（8章 Data Flowで詳述）。

---

## 6. Class Diagram

```
┌──────────────────────────┐        ┌───────────────────────────┐
│    RetrySchedulerSource    │        │   NullRetrySchedulerSource   │
│──────────────────────────│        │───────────────────────────│
│ - _queue: RetryQueueManager │        │ （状態を一切持たない）           │
│──────────────────────────│        │───────────────────────────│
│ + __init__(queue)           │        │ + list_pending_retries(limit)│
│ + list_pending_retries(limit)│──┐    │     → []                     │
│ + count_pending_retries()    │  │    │ + count_pending_retries()    │
└──────────────────────────┘  │    │     → 0                       │
        （継承関係なし。Duck        │    └───────────────────────────┘
         Typingで同一視される）      │ 委譲のみ
                                       ▼
                    ┌──────────────────────────┐
                    │      RetryQueueManager       │  （v3.1.0、無改修）
                    │──────────────────────────│
                    │ + list(limit) -> list[Item]  │
                    │ + count() -> int             │
                    │  （enqueue/dequeue/remove/    │
                    │   existsは本パッケージから     │
                    │   呼び出されない）              │
                    └──────────────────────────┘
```

`RetrySchedulerSource` と `RetryQueueManager` の間に継承関係はない
（コンポジション。`_queue` フィールドとして保持するのみ）。
`RetrySchedulerSource` と `NullRetrySchedulerSource` の間にも継承関係はない
（`RetryManager`/`NullRetryManager`、`RetryQueueManager`/
`NullRetryQueueManager` と同じDuck Typingペア）。

---

## 7. Sequence Diagram

### 7.1 list_pending_retries（有効な場合：RetrySchedulerSource）

```
Caller                RetrySchedulerSource        RetryQueueManager
  │  queue = RetryQueueManager.from_config(...)                     │
  │    # RETRY_QUEUE_ENABLED=true 前提                              │
  │  source = RetrySchedulerSource(queue)                           │
  │                                                                   │
  │  source.list_pending_retries(limit=10)                           │
  ├──────────────────────►│                                          │
  │                        │  self._queue.list(limit=10)             │
  │                        ├─────────────────────────────────────────►│
  │                        │                                          │  _items を
  │                        │                                          │  priority昇順・
  │                        │                                          │  enqueue_time昇順で
  │                        │                                          │  ソートし
  │                        │                                          │  コピーを返す
  │                        │◄─────────────────────────────────────────┤
  │                        │  list[RetryQueueItem]                    │
  │◄───────────────────────┤                                          │
  │  list[RetryQueueItem]（そのまま）                                 │
```

### 7.2 count_pending_retries（有効な場合：RetrySchedulerSource）

```
Caller                RetrySchedulerSource        RetryQueueManager
  │  source.count_pending_retries()                                  │
  ├──────────────────────►│                                          │
  │                        │  self._queue.count()                    │
  │                        ├─────────────────────────────────────────►│
  │                        │◄─────────────────────────────────────────┤
  │                        │  int（len(_items)）                      │
  │◄───────────────────────┤                                          │
  │  int（そのまま）                                                  │
```

### 7.3 無効な場合（NullRetrySchedulerSource。retry_queueへは一切到達しない）

```
Caller                NullRetrySchedulerSource
  │  # RETRY_QUEUE_ENABLED=false、または呼び出し元がQueueと接続しない選択をした
  │  source = NullRetrySchedulerSource()
  │                                                        │
  │  source.list_pending_retries()                         │
  ├──────────────────────────────────────────────────────►│
  │                                                        │  何もしない
  │◄──────────────────────────────────────────────────────┤
  │  []（空リスト。retry_queueへは一度も到達しない）           │
  │                                                        │
  │  source.count_pending_retries()                        │
  ├──────────────────────────────────────────────────────►│
  │◄──────────────────────────────────────────────────────┤
  │  0（retry_queueへは一度も到達しない）                     │
```

初版設計（`RetrySchedulerSource` がUnion型で `NullRetryQueueManager` を
受け取る）との違いはここに現れる。改訂版では、無効時に`retry_queue`パッケージへ
一切アクセスしない経路（`NullRetrySchedulerSource`）が独立して存在するため、
`RetrySchedulerSource` 自身は「実際にQueueと接続している場合」のみを扱う
シンプルな実装のままでいられる。

---

## 8. Data Flow

```
① 呼び出し元（本Releaseでは未定。将来Scheduler側の何らかのコード）が
   「Retry Queue連携を有効にするか」を判断する（判断基準は本Releaseでは
   定義しない。将来的には RetryQueueConfig.from_env().is_ready() を参照する
   ことが想定されるが、これは呼び出し元の実装詳細であり、本パッケージは
   その判断ロジックを持たない）
        ↓
② 有効にする場合：
     RetryQueueConfig.from_env() → RetryQueueManager.from_config(config) で
     queue（実体）を得て、RetrySchedulerSource(queue) を構築する
   無効にする場合：
     NullRetrySchedulerSource() を構築する（retry_queueは一切import・
     構築されない可能性もある）
        ↓
③ 呼び出し元が list_pending_retries(limit) / count_pending_retries() を、
   どちらのクラスに対しても同じ呼び出し方で呼ぶ（Duck Typing）
        ↓
④-a RetrySchedulerSource の場合：self._queue.list(limit) /
     self._queue.count() をそのまま呼び出す（引数・戻り値ともに加工しない）
④-b NullRetrySchedulerSource の場合：即座に [] / 0 を返す（retry_queueへの
     アクセスは発生しない）
        ↓
⑤ RetryQueueManager（実体）は _items を読み取るだけで状態を変更しない
   （Read Only。retry_queue_foundation.md 8章）
        ↓
⑥ 呼び出し元は④の戻り値をそのまま受け取る
```

本Release全体を通じて、`RetrySchedulerSource` / `NullRetrySchedulerSource` の
いずれも `_items`（Queueの実データ）に直接アクセスすることはない。
`RetrySchedulerSource` は常に `RetryQueueManager` の公開メソッド経由でのみ
Queueの状態を参照し、`NullRetrySchedulerSource` はそもそも `retry_queue` を
参照しない。

---

## 9. Configuration

**本Releaseでは新規の環境変数を一切追加しない**（Charter 5章・8章）。

`RetrySchedulerSource` / `NullRetrySchedulerSource` のどちらを使うかは、
呼び出し元のコードが直接選択する。本パッケージ自身は環境変数を一切読まず、
`is_ready()` のような判定メソッドも持たない。

| 環境変数 | デフォルト | 説明 |
|---|---|---|
| （なし） | — | `retry_scheduler_source` パッケージは環境変数を一切読まない |

参考：既存の `RETRY_QUEUE_ENABLED`（`retry_queue` パッケージ側、無改修）が
`false` の場合、`RetryQueueManager.from_config()` は `NullRetryQueueManager`
を返す。呼び出し元がこの結果を見て `NullRetrySchedulerSource()` を選ぶ、
という連携は将来Release（Scheduler本体との実配線）で確立される想定であり、
本Releaseでは両クラスの実装のみを提供する。

---

## 10. Error Handling

`RetrySchedulerSource` / `NullRetrySchedulerSource` は独自の例外処理を持たない。
`RetryQueueManager.list()` / `count()` はいずれも例外を送出しない契約
（`docs/design/retry_queue_foundation.md` 10章：Queueが空でも `list()` は
空リストを返すのみで例外にはならない）であるため、`RetrySchedulerSource` 側
でも try/except は不要と判断する。

| ケース | 挙動 |
|---|---|
| Queueが空 | `RetrySchedulerSource.list_pending_retries()` は `[]`、`count_pending_retries()` は `0` を返す（例外なし） |
| `NullRetrySchedulerSource` を使用 | 常に `[]` / `0`（`retry_queue` へのアクセス自体が発生しないため、Queueの状態に関わらず一定） |
| `queue` に `None` が渡された場合 | 型ヒント上サポート対象外（`RetrySchedulerSource.__init__` は `RetryQueueManager` のみを受け付ける）。呼び出し元の実装ミスとして扱い、本Releaseでは防御的なNoneチェックを追加しない（他の全Managerクラスも同様に呼び出し元の責任としている） |

---

## 11. Future Extension

* **Scheduler本体との実配線**：`SchedulerEngine` の判定サイクル
  （`evaluate()` / `run_due()`）に `RetrySchedulerSource` /
  `NullRetrySchedulerSource` を組み込む統合。「どちらを構築するか」の判定
  ロジック（`RETRY_QUEUE_ENABLED` の参照等）もこの段階で確立する。具体的な
  組み込み方（`SchedulerEngine` に新しい判定メソッドを追加するか、
  `SchedulerEvent` に新しい種別を設けるか、あるいは全く別の呼び出し口を
  用意するか）は、Charter 8章 Open Design Decisionとして次のRelease検討時に
  改めて設計する
* **`dequeue()`を用いた実際の取り出し**：本Releaseでは非破壊の `list()` /
  `count()` のみに限定したが、将来的にQueueから実際に項目を取り出して処理する
  経路を追加する場合、`RetrySchedulerSource` に `dequeue` 相当のメソッドを
  追加するか、別コンポーネントに切り出すかを再検討する。
  `NullRetrySchedulerSource` 側にも対応するno-opメソッドを追加することで、
  Null Object Patternを崩さずに拡張できる
* **自動Retry実行との連携**：取り出した `RetryQueueItem` を
  `RetryManager.retry()` へ渡す変換ロジック（現状は `retry_engine` 側にも
  存在しない。`docs/design/retry_queue_integration.md` 8章で明示的に対象外と
  されている）。`NullRetrySchedulerSource` が存在することで、この種の拡張を
  `RetrySchedulerSource` 側にのみ追加し、無効時の経路（`retry_queue`
  非依存）を保ったまま進められる
* **Scheduler側の判定ロジックの置き場所**：「有効／無効をどう判定するか」は
  本Releaseでは意図的に未定義のままとした（9章）。将来的に
  `RetryQueueConfig.from_env().is_ready()` を直接参照するのか、Scheduler側に
  別の判定基準を設けるのかは、実配線時に決定する
* **件数閾値に基づく通知・アラート**：`count_pending_retries()` が一定数を
  超えた場合の通知（Slack / Discord等）
* **`exists()` の公開**：特定の `run_id` がQueueに存在するかを確認する用途が
  将来生じた場合、両クラスに `has_pending_retry(run_id)` 相当のメソッドを
  追加する（`NullRetrySchedulerSource` は常に `False` を返す）

---

## 12. Compatibility

* 新規独立パッケージ `src/retry_scheduler_source/` の追加のみであり、既存
  パッケージ（`scheduler` / `retry_queue` / `retry_engine` / `workflow_engine` /
  `workflow_monitor` / `execution_history` / `ai` / `pipeline`）への変更は
  一切ない（ゼロ改修）
* 既存の公開APIのシグネチャ・戻り値の意味は変更しない
* `src/retry_scheduler_source/` はどのパッケージからもimportされない状態で
  リリースされる（1章）。これは「消費者不在のままFoundationを先行リリースする」
  という `WorkflowMonitorManager`（v2.9.0）・`RetryQueue`（v3.1.0）と同じ
  パターンであり、後方互換性上のリスクはない（既存の挙動を一切変更しないため）
* 新規の環境変数を追加しないため、`.env` / `.env.example` の変更も不要

---

## 13. Architecture Review

### レビュー経緯

初版設計（`RetrySchedulerSource` 単一クラスが `RetryQueueManager |
NullRetryQueueManager` のUnion型を受け取る）に対し、ユーザーレビューにより
以下3点の指摘を受けた。

1. Feature Gateを追加しない（初版から変更なし。維持を再確認）
2. Configクラスを追加しない（初版から変更なし。維持を再確認）
3. Managerパターン（`from_config()`等の起動口）を採用せず、プロジェクト全体で
   一貫している Null Object Pattern（実装クラス／Nullクラスの2クラス構成）を
   本パッケージにも適用する

指摘3を受け、`RetrySchedulerSource` の `queue` 引数を `RetryQueueManager`
（実体のみ）に narrowing し、無効化の表現を `NullRetrySchedulerSource`
という独立クラスに切り出した（4章）。これにより、「Feature Gate / Config /
Managerパターンを持たない」という制約と「Null Object Patternを維持する」
という要求を両立している。

### SOLID

* **単一責任（SRP）**：`RetrySchedulerSource` は「有効なQueueから状態を
  読み取る」、`NullRetrySchedulerSource` は「安全なデフォルト値を返す」と、
  責務が1クラス1つに明確に分離されている。Queue管理そのものは `retry_queue`
  側に残したまま複製していない
* **開放閉鎖（OCP）**：`RetrySchedulerSource` は `RetryQueueManager` の公開
  インターフェースにのみ依存しており、`retry_queue` 側の内部実装
  （`_items` の型・ソートアルゴリズム等）が変わっても影響を受けない
* **リスコフの置換（LSP）**：`RetrySchedulerSource` と
  `NullRetrySchedulerSource` は戻り値の型（`list[RetryQueueItem]` / `int`）を
  完全に一致させており、呼び出し元はどちらを渡されても同じコードパスで
  正しく動作する（継承関係を持たないDuck Typingだが、型の一貫性は保証される）
* **インターフェース分離（ISP）**：両クラスとも `list_pending_retries()` /
  `count_pending_retries()` の2メソッドのみを公開し、`enqueue()` /
  `dequeue()` / `remove()` / `exists()` には一切アクセスしない
* **依存性逆転（DIP）**：`RetrySchedulerSource` は具象クラス
  `RetryQueueManager` に依存する。`NullRetrySchedulerSource` はいかなる
  外部パッケージにも依存しない（`retry_queue` を一切importしない）。
  「有効／無効の切り替え」という関心事は、抽象を介さず「呼び出し元がどちらの
  クラスを構築するか選ぶ」という形で解決しており、Manager内部でのDIP
  （`RetryQueueConfig.is_ready()` による分岐）とは異なるアプローチだが、
  「呼び出し元が構築するインスタンスを選択する」という設計は
  `AgentManager.from_config()` が複数Trigger Agentを条件付きでDIする際の
  発想と近い

### Foundation First

`list()` / `count()` への委譲のみに限定し、Scheduler本体との実配線・
`dequeue()`の使用・自動Retry実行・Feature Gate追加をすべて11章 Future
Extensionへ送っている。Charter 4章 対象外リストと1対1で対応しており、
スコープの逸脱はない。

### 責務分離

「Queueに何が入っているかを読む」（`RetrySchedulerSource` の責務）と
「Queueの中身をどう管理するか」（`RetryQueueManager` の責務、無改修）を
明確に分離した。「有効か無効か」（`NullRetrySchedulerSource` を選ぶかどうか）
の判定は、本パッケージの責務外（呼び出し元の責務）として明示的に切り離した。

### プロジェクト全体との設計整合性

`RetryManager`/`NullRetryManager`、`RetryQueueManager`/
`NullRetryQueueManager`、`WorkflowEngineManager`/`NullWorkflowEngineManager`、
`WorkflowMonitorManager`/`NullWorkflowMonitorManager` と同じ「継承なし・
戻り値の型が一致するDuck Typingペア」を踏襲した。一方で、他パッケージが
持つ「Configクラス＋`from_config()`という起動口」は本パッケージには存在しない
（2章）。これは指摘を受けての意図的な差別化であり、他パッケージとの非一貫性
ではなく「Feature Gateで判定すべき対象が存在しないコンポーネントには、
Managerパターンを機械的に適用しない」という判断として整理する。

### 将来拡張性

Configクラスや起動口を持たない最小構成としたことで、将来「Scheduler本体との
実配線」や「Feature Gateの追加」が必要になった時点で、既存の2クラスに
手を加える、または新たに起動口（例：将来的な `RetrySchedulerSourceFactory`
的な関数）を呼び出し元側に追加する形で拡張できる。`NullRetrySchedulerSource`
が独立して存在するため、将来の拡張（11章）は「実装クラス側にのみ機能を
追加し、無効時の経路は変更しない」という形で安全に進められる。

### 後方互換性

新規パッケージの追加のみで、既存コードへの影響はゼロ（12章）。

### 依存方向

```
src/retry_scheduler_source/  ─── import ───→  retry_queue（公開APIのみ、RetrySchedulerSourceのみが依存）
```

`NullRetrySchedulerSource` は `retry_queue` を一切importしない。
`retry_scheduler_source` パッケージ全体で見ても `retry_queue` 一つにのみ
依存する「枝1本」のパッケージである。`scheduler` / `retry_engine` /
`workflow_engine` / `workflow_monitor` / `execution_history` のいずれも
importしない。循環importの余地は構造的に存在しない。

### 残された懸念（Minor）

* `RetrySchedulerSource` に消費者が存在しない状態でリリースされるため、
  実際にScheduler側で使われる段階になって初めて、メソッド名
  （`list_pending_retries` / `count_pending_retries`）や引数
  （`limit`）が実用に適しているかが検証される。v2.9.0 / v3.1.0でも同様の
  懸念があったが、後続Releaseでの実配線時に軽微なシグネチャ調整が必要になる
  可能性がある点は許容する
* 「どちらのクラスを構築するか」の判定ロジックを本パッケージが持たないため、
  将来の呼び出し元（Scheduler本体との実配線）が誤った判定基準
  （例：`RETRY_QUEUE_ENABLED` を見ずに常に `RetrySchedulerSource` を使う等）を
  実装してしまうリスクは残る。ただし、この判定ロジック自体をどこに置くかは
  次のRelease（実配線）で確定すべき事項であり、本Foundationの範囲で先回りして
  決め打ちしないことを優先した（Foundation First）

### 総評

Charterの要求（Adapter構成・`list`/`count`限定・Scheduler本体無改修・
Feature Gate追加なし・消費者不在の先行実装）に加え、ユーザーレビューで
指摘されたNull Object Patternへの統一を満たしている。既存Foundation群
（`retry_queue` / `retry_engine`）との設計整合性（公開シンボルのみimport・
委譲のみで判定ロジックを持たない・Duck Typingペア）を保ちつつ、
Configクラス・Managerパターンを持たないという差別化を意図的に行った。
**Approve with Minor Recommendations** と判断する（残された懸念2点は
いずれも後続Releaseでの検討事項であり、本Releaseの実装をブロックしない）。

---

## 14. Status

- [x] Architecture Design ドラフト作成（初版）
- [x] ユーザーレビュー反映（Feature Gate/Config/Managerパターン不使用 → Null Object Pattern 2クラス構成へ変更）
- [x] Architecture Review完了（Approve with Minor Recommendations、指摘事項3点反映済み）
- [ ] 実装開始（ユーザー確認待ち）
