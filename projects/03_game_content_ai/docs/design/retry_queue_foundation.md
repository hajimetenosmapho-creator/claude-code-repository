# v3.1.0 Retry Queue Foundation 設計書（Architecture Design）

作成日：2026-07-02
状態：ドラフト（Architecture Review未実施）。本ドキュメントは Project Charter（本Releaseでは
チャットで提示された Project Charter 本文がSource。別ファイル化はまだ行っていない）を前提とする。
実装コードはまだ作成しない（Architecture Designのみ）。

---

## 1. Architecture Overview

Release 3.0（`docs/design/retry_engine_foundation.md`）で確立した Retry Engine は、
1件の `run_id` に対して「今すぐ再実行してよいか」を判定し、よければ即座に
`WorkflowEngineManager.run()` を呼び出す、**同期・単発**の仕組みだった。

しかし実運用では、以下のようなケースに対応できない。

- 複数の `run_id` が同時に `FAILED` / `TIMEOUT` になった場合、どれから再実行すべきか
  （優先度）を判断する仕組みがない
- 再実行を「今すぐ」ではなく「後で（Schedulerの次のサイクルで）」行いたい場合に、
  対象を一時的に保持しておく場所がない
- Retry Engine は `RetryManager.retry(run_id)` を呼んだその場でしか動かないため、
  「再実行待ちの一覧」という概念そのものが存在しない

本Release（v3.1.0）は、この「保持する場所がない」というギャップを埋める
**Retry Queue Foundation**（新規パッケージ `src/retry_queue/`）を追加する。

```
Scheduler        （判断、v2.6.0、無改修）
   │
Workflow Engine    （実行、v2.7.0、無改修）
   │
Execution History（記録、v2.8.0、無改修）
   │
Workflow Monitor（状態判定、v2.9.0、無改修）
   │
Retry Engine（再実行判断・依頼、v3.0.0、無改修）
   │
   └── Retry Queue（Queue管理、v3.1.0、新規） ★本Release
```

Retry Queue は Retry Engine の**補助コンポーネント**として設計するが、本Releaseの
スコープは「Queue管理のみ」であり、Retry Engine との実際の配線（`RetryManager` から
`RetryQueueManager` を呼び出す等）は行わない（Out of Scope・Scheduler連携も同様）。
そのため `src/retry_queue/` は本Release時点では **どのパッケージからも呼ばれない、
独立した Foundation 層**として先行実装される。これは v2.9.0 の `WorkflowMonitorManager`
が「実呼び出し元を持たないまま先行リリースされた」前例（`docs/design/
workflow_monitor_foundation.md` 11章）と同型のパターンである。

---

## 2. Design Policy

Project Charter の Design Principles をそのまま踏襲し、本設計では特に以下の3点を
Retry Queue 固有の形で具体化する。

1. **Foundation First**：Queue管理（enqueue / dequeue / remove / list / exists / count）
   のみを先に確立する。優先度付けアルゴリズムの高度化・永続化・Scheduler連携・
   Retry Engineとの実配線はすべて後続Releaseへ送る（11章 Future Extension）。

2. **Stateless の解釈**：Retry Engine（v3.0.0）における「Stateless」は
   「Workflowの実行状態を自ら保持せず、毎回 Workflow Monitor に問い合わせる」ことを
   意味していた。Retry Queue は性質上これと同じ意味では成立しない
   ── **Queueに入っている項目を保持すること自体が本コンポーネントの責務**だからである。
   そこで本設計では「Stateless」を次のように再定義して適用する。

   > Retry Queue が保持するのは「再実行待ちの `run_id` とそのメタデータ
   > （`RetryQueueItem`）」という **Queue管理専用の状態**のみであり、
   > Workflowの実行結果・監視ステータス（`WorkflowMonitorStatus`）を独自に
   > 複製・キャッシュすることはない。Queueに入っている `run_id` の「今の
   > 実行状態」を知りたい場合は、依然として Workflow Monitor に問い合わせる
   > 必要があり、Retry Queue はそれを代替しない（Single Source of Truthは
   > Execution History のまま）。

   言い換えると、Retry Queue は「**Queueという名の状態を持つことを許された、
   唯一のコンポーネント**」であり、それ以外の状態（Workflow状態）については
   これまでと同様Statelessである。

3. **既存モジュール無改修**：`workflow_engine` / `workflow_monitor` /
   `execution_history` / `retry_engine` / `ai` / `pipeline` / `scheduler` の
   いずれも変更しない。Retry Queue は後述（7章）のとおり、これらのいずれも
   import しない**独立した葉（leaf）パッケージ**として設計する。これにより
   「既存モジュールの責務を変更しない」という原則を、依存関係レベルで
   最も強く満たす（Retry Engineより一段徹底した独立性）。

---

## 3. Package Structure

```
src/retry_queue/
├── __init__.py               # 公開シンボルのexport（4章）
├── retry_queue_status.py     # RetryQueueStatus（Queue内での項目のライフサイクル状態）
├── retry_queue_item.py       # RetryQueueItem（Queueに保持される1件のデータ）
├── retry_queue_result.py     # RetryQueueResult, RetryQueueOutcome（操作結果）
├── retry_queue_config.py     # RetryQueueConfig（Feature Gate・容量・デフォルト優先度）
├── retry_queue_manager.py    # RetryQueueManager（Queue管理の起動口）
└── null_retry_queue_manager.py  # NullRetryQueueManager（Gate無効時のダミー実装）
```

Charter で候補として挙げられた `null_retry_queue_manager.py` は、`retry_engine`
（`NullRetryManager` は `retry_manager.py` に同居）とは異なり**独立ファイル**とする。
Charter で明示的にファイルが分離されているため、そのまま踏襲する（Manager本体と
ダミー実装を別ファイルにすることで、`grep` 等でダミー実装だけを追いやすくする
副次的な利点もある）。

既存パッケージへの変更は一切行わない（ゼロ改修）。

---

## 4. Public API

### `retry_queue_status.py`

```python
class RetryQueueStatus(Enum):
    WAITING = "waiting"        # enqueue()直後。Queueの中で再実行を待っている
    PROCESSING = "processing"  # dequeue()により取り出された（Queueからは削除済み）
    CANCELLED = "cancelled"    # remove()により取り消された（Queueからは削除済み）
    COMPLETED = "completed"    # 予約値。本Releaseの操作からは到達しない（11章）
    FAILED = "failed"          # 予約値。本Releaseの操作からは到達しない（11章）
```

`COMPLETED` / `FAILED` は、実際に再実行された結果（`RetryOutcome`）をQueueへ
フィードバックする仕組みが必要になるが、それは Retry Engine との連携（Out of Scope）
なしには成立しない。`WorkflowMonitorStatus.CANCELLED` / `WAITING` が判定ロジックから
到達しない予約値として定義されている前例（`docs/design/workflow_monitor_foundation.md`
2章）に倣い、本Releaseでは値だけを定義し、到達させる仕組みは後続Releaseに委ねる。

### `retry_queue_item.py`

```python
@dataclass
class RetryQueueItem:
    run_id: str
    workflow_name: str
    enqueue_time: datetime
    priority: int
    retry_attempt: int
    status: RetryQueueStatus
```

`RetryRequest` / `RetryResult`（`retry_engine`、いずれも `frozen=True`）とは異なり
**`frozen=True` にしない**。理由：`RetryQueueItem` は「1回限りの入出力データ」ではなく
「Queueの中に存在し続け、`RetryQueueManager` の内部ストアがライフサイクル中に
状態を書き換える対象」であるため、性質としては `WorkflowMonitorRecord`
（`workflow_monitor`、同じく `frozen` でない `@dataclass`）に近い。ただし
`RetryQueueManager` の外（呼び出し元）からは `list()` / `dequeue()` の戻り値として
**コピー**を返し、呼び出し元が書き換えても内部ストアには影響しない（6章 Data Flow）。

`priority` は「数値が小さいほど優先度が高い」（Unix `nice` と同じ向き）と定義する。

### `retry_queue_result.py`

```python
class RetryQueueOutcome(Enum):
    ENQUEUED = "enqueued"      # enqueue()が成功した
    DEQUEUED = "dequeued"      # dequeue()が項目を取り出した
    REMOVED = "removed"        # remove()が項目を取り消した
    REJECTED = "rejected"      # enqueue()が容量超過または重複run_idにより拒否した
    NOT_FOUND = "not_found"    # remove()の対象run_idがQueueに存在しない
    EMPTY = "empty"            # dequeue()時にQueueが空だった
    DISABLED = "disabled"      # RETRY_QUEUE_ENABLED=false

@dataclass(frozen=True)
class RetryQueueResult:
    outcome: RetryQueueOutcome
    item: RetryQueueItem | None
    reason: str | None
```

`RetryResult`（`retry_engine`）と同型の「操作結果を1つの型に統一する」パターンを
`enqueue()` / `dequeue()` / `remove()` の3操作すべてに適用する。`list()` /
`exists()` / `count()` は読み取り専用の問い合わせであり失敗の概念がないため、
`RetryQueueResult` でラップせず、素の型（`list[RetryQueueItem]` / `bool` / `int`）を
直接返す（`WorkflowMonitorManager.get_status()` / `list_status()` が素の型を返すのと
同じ考え方）。

### `retry_queue_config.py`

```python
@dataclass
class RetryQueueConfig:
    enabled: bool
    max_queue_size: int
    default_priority: int

    @classmethod
    def from_env(cls) -> "RetryQueueConfig":
        enabled = os.environ.get("RETRY_QUEUE_ENABLED", "true").lower() == "true"
        max_queue_size = int(os.environ.get("RETRY_QUEUE_MAX_SIZE", "100"))
        default_priority = int(os.environ.get("RETRY_QUEUE_DEFAULT_PRIORITY", "0"))
        return cls(enabled=enabled, max_queue_size=max_queue_size, default_priority=default_priority)

    def is_ready(self) -> bool:
        return self.enabled
```

`RETRY_QUEUE_ENABLED` のデフォルトは **`true`**。これは `RETRY_ENGINE_ENABLED`
（デフォルト`false`）とは異なる判断であり、理由は9章で詳述する（要点：Queue管理は
実際のWorkflow再実行という外部副作用を一切伴わないため、`EXECUTION_HISTORY_ENABLED` /
`WORKFLOW_MONITOR_ENABLED`（いずれもデフォルト`true`、読み取り専用）と同じ「安全に
既定で有効にできる」分類に属する）。

### `retry_queue_manager.py` / `null_retry_queue_manager.py`

```python
class RetryQueueManager:
    def __init__(self, config: RetryQueueConfig):
        self._config = config
        self._items: dict[str, RetryQueueItem] = {}

    @classmethod
    def from_config(cls, config: RetryQueueConfig) -> "RetryQueueManager | NullRetryQueueManager":
        if not config.is_ready():
            return NullRetryQueueManager()
        return cls(config=config)

    def enqueue(
        self, run_id: str, workflow_name: str, retry_attempt: int = 1, priority: int | None = None,
    ) -> RetryQueueResult: ...

    def dequeue(self) -> RetryQueueResult: ...

    def remove(self, run_id: str) -> RetryQueueResult: ...

    def list(self, limit: int | None = None) -> list[RetryQueueItem]: ...

    def exists(self, run_id: str) -> bool: ...

    def count(self) -> int: ...


class NullRetryQueueManager:
    def enqueue(self, run_id, workflow_name, retry_attempt=1, priority=None) -> RetryQueueResult: ...
    def dequeue(self) -> RetryQueueResult: ...
    def remove(self, run_id: str) -> RetryQueueResult: ...
    def list(self, limit: int | None = None) -> list: ...
    def exists(self, run_id: str) -> bool: ...
    def count(self) -> int: ...
```

`enqueue()` は `RetryQueueItem` を直接受け取らず、個々のフィールドを受け取って
内部で組み立てる（`enqueue_time=datetime.now()`、`status=RetryQueueStatus.WAITING`、
`priority` 省略時は `config.default_priority` を使用）。これは `RetryManager.retry()`
が `RetryRequest` を呼び出し元に組み立てさせず内部で構築する設計（`retry_engine`）と
同じ考え方であり、「呼び出し元は入力の意味だけを知っていればよく、内部データ構造の
組み立て責任は Manager が持つ」という一貫性を保つ。

### `__init__.py` の公開シンボル

```python
__all__ = [
    "RetryQueueStatus",
    "RetryQueueItem",
    "RetryQueueOutcome",
    "RetryQueueResult",
    "RetryQueueConfig",
    "RetryQueueManager",
    "NullRetryQueueManager",
]
```

---

## 5. Class Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryQueueStatus` | Queue内での1項目のライフサイクル状態を表すEnum | 実際のWorkflow実行結果（それは`WorkflowMonitorStatus`の責務） |
| `RetryQueueItem` | Queueに保持される1件の再実行待ち情報（不変ではなく、Manager内部で状態遷移する記録） | 実行・判定・永続化 |
| `RetryQueueOutcome` / `RetryQueueResult` | `enqueue` / `dequeue` / `remove` 1回の操作結果を統一的に表す不変データ | 結果の永続化・集計・通知 |
| `RetryQueueConfig` | Retry Queue全体のFeature Gate（`RETRY_QUEUE_ENABLED`）・容量上限（`MAX_QUEUE_SIZE`）・既定優先度（`DEFAULT_PRIORITY`）を保持する | Queueの中身そのもの・優先度付けアルゴリズムの実装詳細 |
| `RetryQueueManager` | Queue全体の起動口。`enqueue` / `dequeue` / `remove` / `list` / `exists` / `count` の6操作のみを提供し、内部にQueueの実データ（`dict[str, RetryQueueItem]`）を保持する | Retry実行・Retry可否判定（`RetryPolicy`の責務）・Scheduler連携・永続化 |
| `NullRetryQueueManager` | `RETRY_QUEUE_ENABLED=false` の場合のダミー実装。すべての操作が副作用なく `DISABLED` 相当の結果を返す | 実データの保持 |

`RetryQueueManager` は `RetryPolicy` のような「再実行してよいか」の判定を一切行わない
（Charter Out of Scope「Retry実行」）。Queueへの出し入れの可否判定は「容量上限」
「`run_id` の重複」の2点のみであり、いずれも純粋なQueue管理上の制約である。

---

## 6. Class Diagram

```
┌───────────────────────┐
│   RetryQueueStatus     │  <<enum>>
│───────────────────────│
│ WAITING                │
│ PROCESSING             │
│ CANCELLED              │
│ COMPLETED (予約)        │
│ FAILED (予約)           │
└───────────────────────┘
            ▲ 1
            │ 保持
            │ 1
┌───────────────────────┐        ┌────────────────────────┐
│    RetryQueueItem      │        │   RetryQueueOutcome     │  <<enum>>
│───────────────────────│        │────────────────────────│
│ run_id: str             │        │ ENQUEUED / DEQUEUED /   │
│ workflow_name: str      │        │ REMOVED / REJECTED /    │
│ enqueue_time: datetime  │        │ NOT_FOUND / EMPTY /     │
│ priority: int           │        │ DISABLED                │
│ retry_attempt: int      │        └────────────────────────┘
│ status: RetryQueueStatus│                     ▲ 1
└───────────────────────┘                     │ 保持
            ▲ 0..*                              │ 1
            │ 保持（内部dict）           ┌────────────────────────┐
            │                          │    RetryQueueResult     │
┌───────────────────────┐  返す  │────────────────────────│
│   RetryQueueManager     │────────►│ outcome: RetryQueueOutcome│
│───────────────────────│         │ item: RetryQueueItem|None │
│ - _items: dict[str,     │         │ reason: str|None          │
│     RetryQueueItem]     │         └────────────────────────┘
│ - _config: RetryQueueConfig
│───────────────────────│
│ + from_config(config)   │
│ + enqueue(...)          │
│ + dequeue()             │
│ + remove(run_id)        │
│ + list(limit)           │
│ + exists(run_id)        │
│ + count()               │
└───────────────────────┘
            ▲
            │ 保持（Gate判定用）
            │
┌───────────────────────┐
│   RetryQueueConfig      │
│───────────────────────│
│ enabled: bool            │
│ max_queue_size: int      │
│ default_priority: int    │
│───────────────────────│
│ + from_env()             │
│ + is_ready()             │
└───────────────────────┘

┌───────────────────────┐
│  NullRetryQueueManager  │   （RetryQueueManagerと同じ6メソッドを持つが、
│───────────────────────│    すべてDISABLED相当を返すダミー実装。継承関係は
│ + enqueue(...)           │    持たない＝Duck Typingで同一視する。
│ + dequeue()              │    retry_engine の RetryManager/NullRetryManager
│ + remove(run_id)         │    と同じ関係）
│ + list(limit)            │
│ + exists(run_id)         │
│ + count()                │
└───────────────────────┘
```

---

## 7. Sequence Diagram

### 7.1 enqueue（正常系）

```
Caller          RetryQueueManager
  │  enqueue(run_id="r1",     │
  │  workflow_name="news",    │
  │  retry_attempt=1)         │
  ├───────────────────────────►│
  │                            │  run_id="r1" が _items に無いことを確認
  │                            │  count() < max_queue_size を確認
  │                            │  RetryQueueItem(run_id="r1", ...,
  │                            │    enqueue_time=now(), priority=default_priority,
  │                            │    status=WAITING) を組み立て _items へ格納
  │◄───────────────────────────┤
  │  RetryQueueResult(          │
  │    outcome=ENQUEUED, item=…)│
```

### 7.2 enqueue（拒否系：重複 / 容量超過）

```
Caller          RetryQueueManager
  │  enqueue(run_id="r1", …)  │
  ├───────────────────────────►│
  │                            │  "r1" が既に _items に存在 → 格納しない
  │◄───────────────────────────┤
  │  RetryQueueResult(          │
  │    outcome=REJECTED,        │
  │    reason="duplicate run_id: r1")
```

### 7.3 dequeue

```
Caller          RetryQueueManager
  │  dequeue()                │
  ├───────────────────────────►│
  │                            │  _items が空 → EMPTY を返す（下記は非空の場合）
  │                            │  priority昇順・enqueue_time昇順でソートし
  │                            │  先頭の項目を選ぶ
  │                            │  status を PROCESSING に更新した上で
  │                            │  _items から削除（Queueの外へ「取り出す」）
  │◄───────────────────────────┤
  │  RetryQueueResult(          │
  │    outcome=DEQUEUED,        │
  │    item=RetryQueueItem(status=PROCESSING, …))
```

### 7.4 remove

```
Caller          RetryQueueManager
  │  remove(run_id="r1")      │
  ├───────────────────────────►│
  │                            │  "r1" が _items に無い → NOT_FOUND を返す
  │                            │  （下記は存在する場合）
  │                            │  status を CANCELLED に更新した上で
  │                            │  _items から削除
  │◄───────────────────────────┤
  │  RetryQueueResult(          │
  │    outcome=REMOVED,         │
  │    item=RetryQueueItem(status=CANCELLED, …))
```

### 7.5 Gate無効時（NullRetryQueueManager）

```
Caller          NullRetryQueueManager
  │  enqueue(...) / dequeue() / remove(...)
  ├───────────────────────────►│
  │                            │  何もしない（_itemsを持たない）
  │◄───────────────────────────┤
  │  RetryQueueResult(outcome=DISABLED, item=None,
  │    reason="Retry Queue is disabled (RETRY_QUEUE_ENABLED=false).")
```

---

## 8. Data Flow

```
① 呼び出し元が RetryQueueManager.enqueue(run_id, workflow_name, retry_attempt, priority?) を呼ぶ
        ↓
② Gateチェック（is_ready）は from_config() の時点ですでに解決済み
   （RetryQueueManager実インスタンスに到達している時点で enabled=True 確定）
        ↓
③ run_id の重複チェック → count() >= max_queue_size のチェック
        ↓ いずれか該当 ─────────→ RetryQueueResult(outcome=REJECTED, reason=...) を返す（終了）
        ↓ 両方クリア
④ RetryQueueItem(status=WAITING, enqueue_time=now(), priority=priority or default_priority)
   を組み立て、_items[run_id] = item として内部dictへ格納する
        ↓
⑤ RetryQueueResult(outcome=ENQUEUED, item=itemのコピー) を返す

--- 別フロー ---

① 呼び出し元が RetryQueueManager.dequeue() を呼ぶ
        ↓
② _items が空 → RetryQueueResult(outcome=EMPTY) を返す（終了）
        ↓ 非空
③ _items.values() を (priority, enqueue_time) 昇順でソートし先頭を選ぶ
        ↓
④ 選ばれた item の status を PROCESSING に更新し、_items から削除する
        ↓
⑤ RetryQueueResult(outcome=DEQUEUED, item=更新後のitem) を返す
   （この時点で item は _items 上に存在しない＝以後 list/exists/count には現れない）
```

`list()` / `exists()` / `count()` はいずれも `_items` を読み取るだけで、状態を
変更しない（Read Only）。`RetryQueueManager` が返す `RetryQueueItem` は
`dataclasses.replace()` 等で複製したコピーであり、呼び出し元がフィールドを
書き換えても内部ストア（`_items`）には影響しない（4章）。

---

## 9. Configuration

| 環境変数 | デフォルト | 説明 |
|---|---|---|
| `RETRY_QUEUE_ENABLED` | `true` | Retry Queue全体のFeature Gate |
| `RETRY_QUEUE_MAX_SIZE` | `100` | Queueに同時に保持できる項目数の上限 |
| `RETRY_QUEUE_DEFAULT_PRIORITY` | `0` | `enqueue()` で `priority` 省略時に使う既定優先度（数値が小さいほど高優先） |

**`RETRY_QUEUE_ENABLED` のデフォルトを `true` とする根拠**：Retry Engine
（`RETRY_ENGINE_ENABLED`、デフォルト`false`）は「実際にWorkflowを再実行する」
という外部副作用（News収集・WordPress下書き投稿等）を伴うため安全側で無効化されていた。
一方、Retry Queueの操作（`enqueue` / `dequeue` / `remove` / `list` / `exists` /
`count`）はいずれも**プロセス内メモリ上の `dict` を読み書きするだけ**であり、
外部副作用を一切伴わない。この性質は `EXECUTION_HISTORY_ENABLED` /
`WORKFLOW_MONITOR_ENABLED`（いずれもデフォルト`true`、読み取り中心）と同じ分類に
属すると判断し、`true` を既定値とする。ただし、本Releaseでは Retry Queue と
Retry Engine の実配線を行わないため（Out of Scope）、たとえ `enqueue()` が
将来誤って大量に呼ばれても `MAX_QUEUE_SIZE` の上限により実害の範囲は
「メモリ上の `dict` が最大100件になる」程度に留まる。

---

## 10. Error Handling

Retry Queue は Retry Engine（`retry_engine`）と同じ方針で、**業務上想定される
分岐は例外を投げず `RetryQueueResult` の `outcome` で表現する**。

| ケース | 挙動 |
|---|---|
| `enqueue()` で `run_id` が既に存在 | 例外を投げず `outcome=REJECTED` を返す |
| `enqueue()` で `count() >= max_queue_size` | 例外を投げず `outcome=REJECTED` を返す |
| `dequeue()` を空のQueueに対して呼ぶ | 例外を投げず `outcome=EMPTY` を返す |
| `remove()` で存在しない `run_id` を指定 | 例外を投げず `outcome=NOT_FOUND` を返す |
| `RETRY_QUEUE_ENABLED=false` | `NullRetryQueueManager` が返り、すべての操作が `outcome=DISABLED` を返す |
| `RETRY_QUEUE_MAX_SIZE` / `RETRY_QUEUE_DEFAULT_PRIORITY` が不正な文字列 | `from_env()` 内の `int()` がそのまま `ValueError` を送出する（`RetryPolicy.from_env()` の `RETRY_MAX_ATTEMPTS` と同じ扱い。起動時設定ミスは早期に落として気付けるようにする方針） |

例外を送出するのは「プログラムの前提が壊れているとき」（不正な環境変数）のみに限定し、
「Queueの運用上、日常的に起こりうること」（満杯・重複・空）はすべて戻り値の型で表現する。

---

## 11. Future Extension

- **Retry Engineとの実配線**：`RetryManager` が再実行対象を即座に実行するのではなく
  `RetryQueueManager.enqueue()` へ委ねる、または `dequeue()` した項目に対して
  `RetryManager.retry()` を呼ぶ、という統合。本Releaseでは行わない（Out of Scope）
- **Scheduler連携**：`SchedulerEngine` の定期実行のたびに `dequeue()` して
  処理する自動運用
- **Queue永続化**（SQLite / Redis）：プロセス再起動をまたいでQueueの内容を
  保持する。本Releaseは完全にin-memory（`dict`）であり、プロセスが終了すると
  Queueの内容は失われる
- **`COMPLETED` / `FAILED` への到達**：Retry Engine実行後の結果（`RetryOutcome`）を
  Queueへフィードバックする `mark_completed(run_id)` / `mark_failed(run_id)`
  相当のAPIを追加し、5章で「予約値」とした2状態を実際に到達可能にする
- **Priority Queueの効率化**：現状 `dequeue()` は `_items` 全件を毎回ソートする
  （`O(n log n)`）。`MAX_QUEUE_SIZE` の既定値（100件）では実用上問題ないが、
  上限を大きく引き上げる場合は `heapq` ベースの実装に差し替える
- **Dead Letter Queue**：`retry_attempt` が上限に達した項目の退避先
- **Notification**：`REJECTED`（満杯）発生時のSlack/Discord/LINE通知
- **Dashboard / API / UI**：Queueの中身をWeb UIから参照・操作する
- **並行アクセス対応**：現状 `RetryQueueManager` はロックを持たない
  （既存Manager群と同じく単一プロセス・単一スレッドでの利用を前提とする）。
  複数プロセス・複数スレッドから同時に呼ばれる運用に拡張する場合は
  `threading.Lock` 等の追加が必要

---

## 12. Compatibility

- 新規パッケージ `src/retry_queue/` の追加のみであり、既存パッケージ
  （`retry_engine` / `workflow_engine` / `workflow_monitor` / `execution_history` /
  `ai` / `pipeline` / `scheduler`）への変更は一切ない（ゼロ改修）
- 既存の公開APIのシグネチャ・戻り値の意味は変更しない
- `src/retry_queue/` はどのパッケージからもimportされない状態でリリースされる
  （1章）。これは「消費者不在のままFoundationを先行リリースする」という
  `WorkflowMonitorManager`（v2.9.0）の前例と同じパターンであり、後方互換性上の
  リスクはない（既存の挙動を一切変更しないため）

---

## 13. Architecture Review（セルフレビュー）

### SOLID

- **単一責任（SRP）**：`RetryQueueStatus`＝状態の列挙、`RetryQueueItem`＝データ、
  `RetryQueueResult`/`RetryQueueOutcome`＝操作結果、`RetryQueueConfig`＝Gate設定、
  `RetryQueueManager`＝Queue操作の起動口、と6ファイル・6責務に明確に分離されている。
  唯一注意すべき点は、`RetryQueueManager` が「容量チェック」「重複チェック」
  「優先度ソート」という3つの異なるルールを1クラスに持つことだが、いずれも
  「Queue管理」という単一責務の内側にある判断であり、Retry可否判定
  （`RetryPolicy`の責務）のような**別ドメインの責務**の混入ではないため許容する。
- **開放閉鎖（OCP）**：優先度の算出方法（現状は単純な `int` 比較）を将来
  差し替え可能にする余地は、`RetryQueueItem.priority: int` という素朴な型に
  留めることで確保している。複雑な優先度戦略が必要になった場合、
  `RetryPolicy` が将来 Strategy Pattern 化できる構造を保っている前例
  （`docs/design/retry_engine_foundation.md` 10章 Design Decision #11）に倣い、
  `RetryQueueManager` の `dequeue()` 内のソートロジックを差し替え可能な
  コンポーネントへ切り出すことは、本Foundationのインターフェース
  （`priority: int` を持つ `RetryQueueItem`）を壊さずに行える。
- **リスコフの置換（LSP）**：`RetryQueueManager` と `NullRetryQueueManager` は
  継承関係を持たない（Duck Typing）が、6メソッドすべてで戻り値の型
  （`RetryQueueResult` / `list` / `bool` / `int`）を一致させており、
  呼び出し元は両者を区別せず扱える（`RetryManager` / `NullRetryManager` と同型）。
- **インターフェース分離（ISP）**：`RetryQueueManager` は「Queue管理6操作」
  以外のメソッドを一切持たない。Retry実行や状態判定のメソッドを持たせていない。
- **依存性逆転（DIP）**：`RetryQueueManager` はいかなる外部パッケージ
  （`workflow_engine` / `workflow_monitor` 等）にも依存しない（7章参照）ため、
  DIPを議論する余地すらないほど独立している。これはRelease 3.0の
  `RetryManager`（`workflow_engine` / `workflow_monitor` の抽象APIに依存する
  形でDIPを満たしていた）よりもさらに徹底した独立性である。

### Foundation First

Queue管理6操作のみに限定し、優先度アルゴリズムの高度化・永続化・Retry Engine
との実配線・Scheduler連携をすべて11章 Future Extensionへ送っている。Charterの
Out of Scopeと1対1で対応しており、スコープの逸脱はない。

### 責務分離

「Queueに何を入れるか・いつ取り出すか」（Retry Queueの責務）と「取り出した後に
実際に再実行してよいか」（Retry Engine／`RetryPolicy`の責務）を明確に分離した。
`RetryQueueManager` は `RetryPolicy` を一切参照せず、`retry_attempt` を
記録はするが判定には使わない（判定はあくまで将来 Retry Engine 側が行う）。

### 将来拡張性

`COMPLETED` / `FAILED` を予約値として先に定義しておくことで、将来
Retry Engineとの結果フィードバックを実装する際に `RetryQueueStatus` 自体の
変更（＝既存Enum値の追加）を避けられる設計にした。これは
`WorkflowMonitorStatus.CANCELLED` / `WAITING` の前例を踏襲したものである。

### 後方互換性

新規パッケージの追加のみで、既存コードへの影響はゼロ（12章）。

### 依存方向

```
src/retry_queue/  ─── import ───→  （なし。標準ライブラリのみ）
```

`retry_queue` パッケージは他のどの `src/*` パッケージも import しない、
完全に独立した葉パッケージである。将来 Retry Engine との連携を実装する際は
`retry_engine` 側が `retry_queue` を import する形になり（1章の概念図の
向きと一致）、`retry_queue` が `retry_engine` を import することはない
（循環importの余地がそもそも構造的に存在しない）。

### 残された懸念（Minor）

- `RetryQueueManager` のスレッド安全性を保証していない点は、既存Manager群
  （`RetryManager` 等）も同様に無保証であるため本Releaseとしては一貫しているが、
  将来複数プロセス・複数スレッドから同時にenqueue/dequeueされる運用が
  想定される場合は明示的な対応が必要になる（11章に記載済み）
- `dequeue()` の全件ソート（`O(n log n)`）は `MAX_QUEUE_SIZE` の既定値
  （100件）では無視できるコストだが、上限を大きく引き上げる運用が
  将来出てきた場合は要見直し（11章に記載済み）

**総評**：Charterの要求（Queue管理6操作・Out of Scopeの厳守・既存モジュール
無改修）を満たし、かつ既存Foundation群（`retry_engine` / `workflow_monitor`）
との設計整合性（Manager/Nullペア・`from_config`/`from_env`・Result型への
outcome統一・予約Enum値パターン）を保っている。Approve相当と判断する
（正式なArchitecture Reviewは別途実施を推奨）。
