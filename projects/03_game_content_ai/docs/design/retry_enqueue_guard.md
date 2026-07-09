# v4.8.0 Retry Enqueue Guard 設計書（Architecture Design）

作成日：2026-07-09
状態：Architecture Review完了（自己レビュー、Approve）・ユーザー承認済み・実装未着手
`docs/design/retry_enqueue_guard_charter.md`（Project Charter）を前提とする。

---

## 1. Architecture Overview

v4.6.0（Retry Enqueue Trigger Foundation）が新設した`RetryEnqueueTrigger`は、
`RetryQueueManager.exists()`による「Queue内に現在存在するか」の確認のみで重複防止を
行っており、Queueから除去（`COMPLETE` / `FAIL` / `CLEANUP`）された後もWorkflow Monitor上で
`FAILED` / `TIMEOUT`のまま観測され続ける`run_id`を無限に再enqueueしうる欠陥
（Known Issue）を抱えていた。

v4.7.0（Retry History Foundation）は、この対策の土台として`original_run_id`ごとの
再試行履歴を記録する`RetryHistoryManager`を新設したが、`RetryEnqueueTrigger`側からの
参照・ガード判定は未接続のまま残していた。

本Release（v4.8.0）は、この最後の接続を行う。

```
WorkflowMonitorManager（判定、v2.9.0、無改修）
   │
   ▼
RetryEnqueueTrigger（Adapter、v4.6.0、拡張） ★本Release
   │
   ├─① self._monitor.list_status(limit)                         （無改修の既存呼び出し）
   ├─② status not in {FAILED, TIMEOUT} → skipped_status          （無改修の既存判定）
   ├─③ self._history.has_history(run_id)                         （新規：RetryHistoryManager, v4.7.0 無改修）
   │     └── self._guard.decide(run_id, has_history) → BLOCK/ALLOW （新規：RetryEnqueueGuard） ★本Release
   │           BLOCK → skipped_history
   ├─④ self._queue.exists(run_id) → skipped_existing              （無改修の既存判定）
   └─⑤ self._queue.enqueue(run_id, workflow_name)                 （無改修の既存呼び出し）
```

`RetryEnqueueGuard`は`RetryEnqueueTrigger`内部のみで使われる新規Deciderであり、
`retry_history` / `retry_queue` / `workflow_monitor` / `retry_engine`のいずれにも
変更を加えない。

---

## 2. Design Policy

Project Charter（5章 Design Principles・8章 Open Questions）で確定した方針を、
実装レベルで具体化する。

1. **Guard判定は「履歴の有無」の二値のみ（Charter 8章 Open Question #1）**：
   `RetryEnqueueGuard.decide(run_id, has_history: bool) -> RetryEnqueueGuardDecision`。
   `RetryHistoryRecord.attempt_count`や`RetryPolicy.max_attempts`との比較は行わない。
   これにより`RetryEnqueueGuard`は`retry_history`型はもちろん`retry_engine`型も
   一切importしない、完全に独立したコンポーネントになる。

2. **`RetryEnqueueGuard`はStateless・既に解決済みの値のみを受け取る**：
   `RetryQueueUpdateDecider.decide(execution_result)`・`RetryQueueCleanupDecider.
   decide(update_decision)`と同じ設計言語。外部ストアへの問い合わせ（`self._history.
   has_history(run_id)`の呼び出し）は`RetryEnqueueTrigger`側の責務として残し、
   `RetryEnqueueGuard`自体は`bool`を受け取って`Enum`を返すだけの純粋な判定に留める。

3. **`history`は`RetryQueueManager`と同じ理由でstateful store扱い（Null Object
   Patternへのフォールバック）**：`RetryEnqueueTrigger.__init__`の新規引数`history`は
   デフォルト`None`とし、省略時は`NullRetryHistoryManager()`にフォールバックする
   （v4.7.0`RetryManager.__init__`の`history`引数と同じ設計判断）。

4. **`guard`はStateless系コンポーネントと同じ理由で実体へのデフォルトフォールバック**：
   `RetryEnqueueGuard`はコンストラクタ引数を取らず害のない純粋な判定のみを行うため、
   `guard`引数省略時は`RetryEnqueueGuard()`（実体）にフォールバックする
   （`RetryHistoryRecordExecutor` / `RetryQueueUpdateDecider`と同じ扱い）。

5. **`RetryEnqueueTriggerResult`への追加フィールドは末尾デフォルト値付き**：
   `skipped_history: int = 0`を追加する。既存の5フィールドはいずれも無変更・
   順序も変更しない。

6. **既存の判定ロジック（status判定・exists判定）は1行も変更しない**：
   Guard判定は独立した新しい分岐として追加するのみで、既存の`if / continue`構造には
   手を加えない。

---

## 3. Package Structure

```
src/retry_enqueue_trigger/
├── __init__.py                  # 公開シンボルのexport（変更：新規3シンボル追加）
├── retry_enqueue_trigger.py     # RetryEnqueueTrigger / NullRetryEnqueueTrigger /
│                                 # RetryEnqueueTriggerResult（変更）
└── retry_enqueue_guard.py       # RetryEnqueueGuardOutcome / RetryEnqueueGuardDecision /
                                  # RetryEnqueueGuard（新規）
```

`RetryEnqueueGuard`を独立パッケージ（例：`src/retry_enqueue_guard/`）にはしない。
`RetryQueueCleanupDecider`（`retry_engine`パッケージ内の1ファイル）と同じ考え方で、
`RetryEnqueueTrigger`専属の内部コンポーネントであり、他のどのパッケージからも
単独で参照される想定がないため、既存パッケージ内へ同居させる。

`src/retry_history/` / `src/retry_queue/` / `src/workflow_monitor/` / `src/retry_engine/`
への変更は一切行わない（ゼロ改修）。

---

## 4. Public API

### `retry_enqueue_guard.py`（新規）

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum, auto


class RetryEnqueueGuardOutcome(Enum):
    ALLOW = auto()
    BLOCK = auto()


@dataclass(frozen=True)
class RetryEnqueueGuardDecision:
    """1件のrun_idに対するGuard判定結果。"""
    run_id: str
    outcome: RetryEnqueueGuardOutcome
    reason: str


class RetryEnqueueGuard:
    """
    再試行履歴（has_history）の有無から、enqueueを許可するか拒否するかを判定する
    Statelessなコンポーネント。RetryHistoryManager等の外部型には一切依存しない。
    """

    def decide(self, run_id: str, has_history: bool) -> RetryEnqueueGuardDecision:
        if has_history:
            return RetryEnqueueGuardDecision(
                run_id=run_id,
                outcome=RetryEnqueueGuardOutcome.BLOCK,
                reason=f"run_id={run_id} already has retry history (has_history=True).",
            )
        return RetryEnqueueGuardDecision(
            run_id=run_id,
            outcome=RetryEnqueueGuardOutcome.ALLOW,
            reason=f"run_id={run_id} has no retry history yet.",
        )
```

* `decide_all()`（バッチ版）は追加しない。呼び出し元（`RetryEnqueueTrigger.
  enqueue_pending_failures()`）は元々`WorkflowMonitorRecord`を1件ずつループしており、
  ループ内で`decide()`を1件ずつ呼ぶ形が既存構造（`queue.exists()`も同様に1件ずつ
  呼ばれている）と一貫する
* `RetryEnqueueGuard`と対になるNull実装（`NullRetryEnqueueGuard`）は追加しない。
  `RetrySchedulerDecision`（v3.5.0）と同じ判断：本コンポーネントには対応する
  Feature Gate/Config軸が存在せず、「Guardを無効化したい」場合は`history`を
  省略する（`NullRetryHistoryManager()`へフォールバックし`has_history`が常に`False`に
  なる）ことで既に完結しているため

### `retry_enqueue_trigger.py`（変更）

```python
from __future__ import annotations

from dataclasses import dataclass

from retry_history import NullRetryHistoryManager, RetryHistoryManager
from retry_queue import RetryQueueManager, RetryQueueOutcome
from workflow_monitor import WorkflowMonitorManager, WorkflowMonitorStatus

from .retry_enqueue_guard import RetryEnqueueGuard, RetryEnqueueGuardOutcome

_RETRY_TARGET_STATUSES = frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT})


@dataclass(frozen=True)
class RetryEnqueueTriggerResult:
    """enqueue_pending_failures() 1回分の集計結果。"""
    scanned: int
    enqueued: int
    skipped_existing: int
    skipped_status: int
    failed: int
    skipped_history: int = 0          # ★新規（末尾・デフォルト値付き）


class RetryEnqueueTrigger:
    def __init__(
        self,
        monitor: WorkflowMonitorManager,
        queue: RetryQueueManager,
        history: "RetryHistoryManager | NullRetryHistoryManager | None" = None,   # ★新規（末尾）
        guard: RetryEnqueueGuard | None = None,                                    # ★新規（末尾）
    ):
        self._monitor = monitor
        self._queue = queue
        self._history = history if history is not None else NullRetryHistoryManager()
        self._guard = guard if guard is not None else RetryEnqueueGuard()

    def enqueue_pending_failures(self, limit: int | None = None) -> RetryEnqueueTriggerResult:
        records = self._monitor.list_status(limit=limit)
        scanned = len(records)
        enqueued = 0
        skipped_existing = 0
        skipped_status = 0
        skipped_history = 0
        failed = 0

        for record in records:
            if record.monitor_status not in _RETRY_TARGET_STATUSES:
                skipped_status += 1
                continue

            has_history = self._history.has_history(record.run_id)
            guard_decision = self._guard.decide(record.run_id, has_history=has_history)
            if guard_decision.outcome == RetryEnqueueGuardOutcome.BLOCK:
                skipped_history += 1
                continue

            if self._queue.exists(record.run_id):
                skipped_existing += 1
                continue
            result = self._queue.enqueue(run_id=record.run_id, workflow_name=record.workflow_name)
            if result.outcome == RetryQueueOutcome.ENQUEUED:
                enqueued += 1
            else:
                failed += 1

        return RetryEnqueueTriggerResult(
            scanned=scanned,
            enqueued=enqueued,
            skipped_existing=skipped_existing,
            skipped_status=skipped_status,
            failed=failed,
            skipped_history=skipped_history,
        )


class NullRetryEnqueueTrigger:
    def enqueue_pending_failures(self, limit: int | None = None) -> RetryEnqueueTriggerResult:
        return RetryEnqueueTriggerResult(
            scanned=0, enqueued=0, skipped_existing=0, skipped_status=0, failed=0,
            skipped_history=0,
        )
```

* `history` / `guard`はいずれも末尾のデフォルト値付き引数として追加するため、
  既存の`RetryEnqueueTrigger(monitor, queue)`という2引数呼び出し（v4.6.0の
  全89件のテストを含む）は本Release後もまったく同じ挙動で動作する
* Guard判定はstatus判定の直後・exists判定の直前に置く。「この`run_id`をそもそも
  enqueue候補として検討してよいか」（Guard）は、「現在Queueにあるか」（exists）より
  上位の関心事であるため、この順序とする（ただし通常運用では両者は排他的にしか
  真にならない想定：Guardが`BLOCK`を返す状況＝過去に`RETRIED`済みで既にQueueから
  除去されている状況であり、`exists()`が`True`である状況とは基本的に重ならない）
* `NullRetryEnqueueTrigger`は`skipped_history=0`を明示的に返す（既存5フィールドと
  同じスタイルを踏襲し、デフォルト値に暗黙に頼らない）

### `__init__.py` の公開シンボル（変更）

```python
from .retry_enqueue_guard import (
    RetryEnqueueGuard,
    RetryEnqueueGuardDecision,
    RetryEnqueueGuardOutcome,
)
from .retry_enqueue_trigger import (
    NullRetryEnqueueTrigger,
    RetryEnqueueTrigger,
    RetryEnqueueTriggerResult,
)

__all__ = [
    "RetryEnqueueTrigger",
    "NullRetryEnqueueTrigger",
    "RetryEnqueueTriggerResult",
    "RetryEnqueueGuard",
    "RetryEnqueueGuardOutcome",
    "RetryEnqueueGuardDecision",
]
```

既存の3シンボルは維持し、新規3シンボルを追加する（合計6シンボル）。

---

## 5. Class Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryEnqueueGuard` | `run_id`と`has_history`（bool）から、`ALLOW` / `BLOCK`を判定する | `RetryHistoryManager`への問い合わせ・Queue操作・Monitor状態の判定・複数回判定のバッチ処理 |
| `RetryEnqueueTrigger` | `WorkflowMonitorManager` / `RetryQueueManager` / `RetryHistoryManager` / `RetryEnqueueGuard`への参照を保持し、検知・履歴問い合わせ・Guard判定・重複確認・enqueueへの薄い委譲を行う | Guard判定ロジック自体の実装・再試行履歴の記録（`RetryManager.record_retry_history()`の責務） |
| `NullRetryEnqueueTrigger` | 常に副作用なく全フィールド0（`skipped_history`含む）の結果を返す | `workflow_monitor` / `retry_queue` / `retry_history`への参照の保持 |
| `RetryHistoryManager`（v4.7.0、無改修） | 引き続き再試行履歴の記録・参照のみを行う | Guard判定・Queue操作 |

---

## 6. Class Diagram

```
┌────────────────────────────────┐
│         RetryEnqueueTrigger         │
│────────────────────────────────│
│ - _monitor: WorkflowMonitorManager      │
│ - _queue: RetryQueueManager            │
│ - _history: RetryHistoryManager |        │──── has_history(run_id) ────▶ RetryHistoryManager（v4.7.0、無改修）
│             NullRetryHistoryManager      │
│ - _guard: RetryEnqueueGuard             │──── decide(run_id, has_history) ─▶┌──────────────────┐
│────────────────────────────────│                                          │  RetryEnqueueGuard   │
│ + __init__(monitor, queue, history=None,│                                  │──────────────────│
│            guard=None)                    │                                  │（状態を一切持たない） │
│ + enqueue_pending_failures(limit)         │                                  │──────────────────│
│     → RetryEnqueueTriggerResult            │                                  │ + decide(run_id,       │
└────────────────────────────────┘                                  │     has_history)       │
                                                                            │   → RetryEnqueueGuard   │
                                                                            │     Decision              │
                                                                            └──────────────────┘
```

`RetryEnqueueTrigger`と`RetryEnqueueGuard`の間に継承関係はない（コンポジション）。
`RetryEnqueueGuard`は`RetryHistoryManager` / `NullRetryHistoryManager`のいずれの型も
importせず、`RetryEnqueueTrigger`が問い合わせた結果（`bool`）のみを受け取る。

---

## 7. Sequence Diagram

### 7.1 履歴なし（ALLOW、通常のenqueue経路）

```
Caller    RetryEnqueueTrigger   WorkflowMonitorManager   RetryHistoryManager   RetryEnqueueGuard   RetryQueueManager
  │ enqueue_pending_failures()                                                                                       │
  ├────────►│                                                                                                        │
  │         │ list_status(limit)                                                                                     │
  │         ├──────────────►│                                                                                        │
  │         │◄───────────────┤ list[WorkflowMonitorRecord]                                                           │
  │         │                                                                                                        │
  │         │ for record in records:                                                                                 │
  │         │   status in {FAILED, TIMEOUT}                                                                          │
  │         │   has_history(record.run_id)                                                                           │
  │         ├─────────────────────────────────►│                                                                     │
  │         │◄─────────────────────────────────┤ False                                                               │
  │         │   guard.decide(run_id, has_history=False)                                                              │
  │         ├───────────────────────────────────────────────►│                                                      │
  │         │◄───────────────────────────────────────────────┤ RetryEnqueueGuardDecision(ALLOW)                     │
  │         │   queue.exists(run_id)                                                                                 │
  │         ├──────────────────────────────────────────────────────────────────────►│                              │
  │         │◄──────────────────────────────────────────────────────────────────────┤ False                        │
  │         │   queue.enqueue(run_id, workflow_name)                                                                 │
  │         ├──────────────────────────────────────────────────────────────────────►│                              │
  │         │◄──────────────────────────────────────────────────────────────────────┤ RetryQueueResult(ENQUEUED)   │
  │◄────────┤ RetryEnqueueTriggerResult(enqueued=1, skipped_history=0, ...)                                          │
```

### 7.2 履歴あり（BLOCK、Guardによりenqueueへ到達しない）

```
Caller    RetryEnqueueTrigger   WorkflowMonitorManager   RetryHistoryManager   RetryEnqueueGuard   RetryQueueManager
  │ enqueue_pending_failures()                                                                                       │
  ├────────►│                                                                                                        │
  │         │ list_status(limit) → [record(run_id=X, status=FAILED)]                                                 │
  │         │ has_history(X)                                                                                         │
  │         ├─────────────────────────────────►│                                                                     │
  │         │◄─────────────────────────────────┤ True（過去にRetryManager.retry()経由でRETRIED済み）                 │
  │         │   guard.decide(X, has_history=True)                                                                    │
  │         ├───────────────────────────────────────────────►│                                                      │
  │         │◄───────────────────────────────────────────────┤ RetryEnqueueGuardDecision(BLOCK)                     │
  │         │   （queue.exists() / queue.enqueue() のいずれにも到達しない）                                          │
  │◄────────┤ RetryEnqueueTriggerResult(enqueued=0, skipped_history=1, ...)                                          │
```

### 7.3 `history`省略時（NullRetryHistoryManager、v4.6.0時点と完全に同一の挙動）

```
Caller    RetryEnqueueTrigger              NullRetryHistoryManager   RetryEnqueueGuard
  │ RetryEnqueueTrigger(monitor, queue)  # history省略                                    │
  ├────────►│                                                                             │
  │         │ has_history(run_id)                                                         │
  │         ├──────────────────►│                                                         │
  │         │◄──────────────────┤ False（常に）                                            │
  │         │ guard.decide(run_id, has_history=False)                                      │
  │         ├─────────────────────────────────────►│                                      │
  │         │◄─────────────────────────────────────┤ RetryEnqueueGuardDecision(ALLOW)     │
  │         │ （以降はv4.6.0時点と完全に同一の経路：queue.exists() → queue.enqueue()）        │
```

---

## 8. Data Flow

```
① 呼び出し元が RetryEnqueueTrigger を構築する（本Release後の新しい構築例）：
     RetryEnqueueTrigger(
         monitor=WorkflowMonitorManager.from_config(...),
         queue=RetryQueueManager.from_config(...),
         history=RetryHistoryManager(),   # 省略可（省略時はGuardが常にALLOWになる）
     )
   guard は省略可（省略時は RetryEnqueueGuard() が自動構築される）
        ↓
② enqueue_pending_failures(limit) を呼ぶ（v4.6.0時点と同じ呼び出し方）
        ↓
③ monitor.list_status(limit) → FAILED/TIMEOUTのみ抽出（無改修）
        ↓
④ 各run_idについて history.has_history(run_id) を問い合わせ、
   guard.decide(run_id, has_history) で ALLOW/BLOCK を判定する ★本Release
        ↓
⑤-a BLOCK の場合：skipped_history をインクリメントし、次のrecordへ（queue.exists() /
     queue.enqueue() のいずれにも到達しない）
⑤-b ALLOW の場合：v4.6.0時点と同じ経路（queue.exists() → 未存在ならqueue.enqueue()）
        ↓
⑥ 呼び出し元は RetryEnqueueTriggerResult（skipped_history を含む6フィールド）を
   そのまま受け取る
```

`RetryEnqueueGuard`は`RetryHistoryManager`の内部データ構造（`_records` dict）に
直接アクセスすることはない。常に`RetryEnqueueTrigger`が問い合わせた`bool`値のみを
経由する。

---

## 9. Configuration

**本Releaseでは新規の環境変数を一切追加しない**（Charter 4章 対象外「Feature Gate・
Configクラスの新設」）。

`history` / `guard`をどう構築するかは、呼び出し元のコードが直接選択する。
`RetryEnqueueGuard`自身は環境変数を一切読まない。

| 環境変数 | デフォルト | 説明 |
|---|---|---|
| （なし） | — | `RetryEnqueueGuard`は環境変数を一切読まない |

参考：`history`を省略した場合、`RetryEnqueueTrigger`はv4.6.0時点とまったく同じ挙動
（Guard相当の機能が存在しないのと同じ状態）になる。実運用でGuardを機能させるには、
呼び出し元が`RetryHistoryManager`の実体を明示的に渡す必要がある（この判断は
Composition Root側の責務であり、本Releaseの対象外）。

---

## 10. Error Handling

`RetryEnqueueGuard`は独自の例外処理を持たない。

| ケース | 挙動 |
|---|---|
| `has_history=True` | `BLOCK`を返す。例外なし |
| `has_history=False` | `ALLOW`を返す。例外なし |
| `history`省略（`NullRetryHistoryManager`） | `has_history()`は常に`False`を返すため、Guardは常に`ALLOW`。v4.6.0時点と同じ挙動 |
| `guard`省略 | `RetryEnqueueGuard()`が自動構築され、通常どおり動作する（省略しても機能が無効化されるわけではない点が`history`省略時と異なる） |

---

## 11. Known Issue（本Releaseでは対策しない）

**`RETRY_MAX_ATTEMPTS`（デフォルト3）を活かした複数回の自動リトライ運用は、
`RetryEnqueueTrigger`経由では本Release後も実質的に機能しないままである。**

原因（Project Charter 1章1.1節で詳述）：`RetryEnqueueTrigger.enqueue_pending_failures()`は
`queue.enqueue()`呼び出し時に`retry_attempt`を明示的に渡しておらず、常にデフォルト値
`1`でQueueへ投入される。下流の`RetryExecutionCoordinator.execute()`は
`candidate.retry_attempt`（Queue項目由来の`1`固定）をそのまま`RetryManager.retry()`の
`attempt`引数として使うため、`RetryPolicy.should_retry()`は常に`attempt=1 < max_attempts`
という条件で判定される。

本Releaseが導入する`RetryEnqueueGuard`は「一度でも再試行履歴（`RETRIED`実績）があれば
以後は再enqueueしない」という二値判定のみを行うため、`max_attempts=3`のように
複数回のリトライを許容する設定であっても、`RetryEnqueueTrigger`経由の自動enqueueでは
**実質的に1回しか再試行されない**（2回目以降のチャンスはGuardによってブロックされる）。

これは無限再投入という安全性上の問題（本Releaseで解消）とは異なる、別種の制約である。
**安全性を優先し、意図的にこの制約を受け入れる**（Development Charter 13章の意思決定
原則：安全性を最優先とする）。将来、複数回リトライの運用を実現したい場合は、
「実際の累積試行回数（`RetryHistoryRecord.attempt_count`）をQueueへのenqueue時点の
`retry_attempt`へ反映する」統合を別Releaseで先に実装したうえで、Guardの判定基準を
「履歴の有無」から「`attempt_count >= max_attempts`」へ精緻化する必要がある
（12章 Future Extension参照）。

---

## 12. Future Extension

* **`attempt`の実回数連動**：11章 Known Issueで述べた制約の解消。`RetryHistoryRecord.
  attempt_count`を`RetryQueueManager.enqueue()`の`retry_attempt`引数へ反映し、
  `RetryPolicy.max_attempts`を活かした複数回リトライの運用を実現する
* **Guard判定基準の精緻化**：`attempt`の実回数連動が実現した後、`RetryEnqueueGuard`の
  判定基準を「履歴の有無」の二値から「`attempt_count >= max_attempts`」の比較へ
  発展させる。ただしこれは`retry_engine`（`RetryPolicy.max_attempts`）への新規依存を
  伴うため、v4.6.0 Design Policy #2との整合性を改めて検討する必要がある
* **Composition Root（実運用の起動導線）**：本Release完了後、`RetryEnqueueTrigger`を
  定期的に呼び出す起動スクリプトの実装に着手できる状態になる（v4.7.0 Project Charter
  冒頭注記の前提条件を満たす）
* **`RetryEnqueueTriggerResult`への詳細情報追加**：現状は集計件数のみだが、将来的に
  「どのrun_idがGuardでBLOCKされたか」のトレーサビリティが必要になった場合、
  `blocked_run_ids: list[str]`等の追加を検討する（v4.6.0設計書12章と同じ「必要性が
  明確になってから追加する」方針を踏襲）

---

## 13. Compatibility

* 変更ファイルは`src/retry_enqueue_trigger/`配下3ファイル（新規1・変更2）のみ
  （`retry_enqueue_guard.py`新規、`retry_enqueue_trigger.py` / `__init__.py`変更）
* `retry_history` / `retry_queue` / `workflow_monitor` / `retry_engine`への変更は
  一切ない（ゼロ改修）
* `RetryEnqueueTrigger.__init__`への引数追加は末尾のデフォルト値付きのみであり、
  既存の`RetryEnqueueTrigger(monitor, queue)`という2引数呼び出しは本Release後も
  まったく同じ挙動になる（v4.6.0の89件のテストが検証済みの挙動を破壊しない）
* `RetryEnqueueTriggerResult`へのフィールド追加も末尾のデフォルト値付きのみであり、
  既存の5フィールドをキーワード引数で指定する既存コード（テストを含む）は
  本Release後もそのまま動作する
* `NullRetryEnqueueTrigger`の公開挙動（常に全フィールド0を返す）は変わらない
* 新規の環境変数を追加しないため、`.env` / `.env.example`の変更も不要

---

## 14. Architecture Review（自己レビュー）

### SOLID

* **単一責任（SRP）**：`RetryEnqueueGuard`は「`has_history`から`ALLOW`/`BLOCK`を
  判定する」1つの責務のみを持つ。`RetryEnqueueTrigger`は「外部状態の問い合わせ＋
  各Deciderへの薄い委譲」という既存の責務（v4.6.0）をそのまま維持し、判定ロジック
  自体を複製しない
* **開放閉鎖（OCP）**：`RetryEnqueueTrigger`は`RetryHistoryManager` /
  `RetryEnqueueGuard`の公開インターフェースにのみ依存しており、両者の内部実装が
  変わっても影響を受けない
* **リスコフの置換（LSP）**：`RetryHistoryManager`と`NullRetryHistoryManager`は
  `has_history()`の戻り値の型（`bool`）を完全に一致させており、`RetryEnqueueTrigger`は
  どちらを渡されても同じコードパスで正しく動作する
* **インターフェース分離（ISP）**：`RetryEnqueueGuard`は`decide()`1メソッドのみを
  公開する。`RetryEnqueueTrigger`は`RetryHistoryManager`の`record()` / `get()`には
  一切アクセスせず、`has_history()`のみを呼ぶ
* **依存性逆転（DIP）**：`RetryEnqueueGuard`はいかなる外部パッケージの具象型にも
  依存しない（`bool`という組み込み型のみ）。「有効／無効の切り替え」は、呼び出し元が
  `history`に実体を渡すか省略するかで解決する（`RetrySchedulerSource`と同じアプローチ）

### Foundation First

Guard判定は「履歴の有無」の二値のみに限定し、`attempt`の実回数連動・
Composition Root・Guard判定基準の精緻化はいずれも12章 Future Extensionへ送っている。
Charter 4章 対象外リストと1対1で対応しており、スコープの逸脱はない。

### 責務分離

「再enqueueを許可するか拒否するか」（`RetryEnqueueGuard`の責務）と、「再試行履歴を
どう記録するか」（`RetryHistoryManager`の責務、無改修）、「Queueをどう管理するか」
（`RetryQueueManager`の責務、無改修）、「Workflowの状態をどう判定するか」
（`WorkflowMonitorManager`の責務、無改修）を明確に分離した。

### プロジェクト全体との設計整合性

`RetryQueueCleanupDecider`（v4.3.0）・`RetryQueueTerminalCleanupDecider`（v4.4.0）と
同じ「Enum + frozen dataclass + Stateless Deciderクラス」の構成を、`retry_engine`外
（`retry_enqueue_trigger`パッケージ内）でも踏襲した。`RetryEnqueueTrigger`自体の
「Constructor Injection・省略時はNull Object Patternまたは実体へフォールバック」という
構成も、`RetryManager`（v4.1.0〜v4.7.0で同じパターンを繰り返し採用）と一貫している。

### 依存方向

```
src/retry_enqueue_trigger/  ─── import ───→  workflow_monitor（公開APIのみ、無改修）
src/retry_enqueue_trigger/  ─── import ───→  retry_queue（公開APIのみ、無改修）
src/retry_enqueue_trigger/  ─── import ───→  retry_history（公開APIのみ、無改修） ★新規
```

`RetryEnqueueGuard`はいずれのパッケージも一切importしない。`retry_engine`への依存は
本Releaseでも発生しない（Charter Design Principles「依存方向」参照）。循環importの
余地は構造的に存在しない（`workflow_monitor` / `retry_queue` / `retry_history`の
いずれも`retry_enqueue_trigger`を知らない）。

### 残された懸念（Known Issueとして11章に記録済み）

* `RETRY_MAX_ATTEMPTS`を活かした複数回リトライ運用が、本Release後も
  `RetryEnqueueTrigger`経由では実質機能しない（11章）。ただし本Releaseの主目的
  （無限再投入の防止）はこの制約と独立に達成されており、実装をブロックしない
* `RetryEnqueueTrigger`のコンストラクタ引数が4個に増える（Charter 11章Risks）。
  現時点では許容範囲と判断する

### 総評

Charterの要求（Guard新設・Enqueue Trigger拡張・既存4パッケージ無改修・
Feature Gate追加なし・Backward Compatibility維持）と、Open Questionsに対する
Charter側の提案（二値判定・`skipped_history`フィールド追加）をすべて満たしている。
既存Foundation群（`retry_queue_cleanup_decider` / `retry_queue_terminal_cleanup_
decider`）との設計整合性を保ちつつ、新たに生じる制約（複数回リトライの実質未対応）を
Known Issueとして明記した。**Approve**と判断する。

---

## 15. Status

- [x] Architecture Design ドラフト作成（本文書、Claude Code作成）
- [x] Architecture Review（自己レビュー、Approve）
- [x] ユーザー承認（2026-07-09、Charter Open Questions 2点とも提案どおりで確定）
- [ ] Implementation（次Sessionで着手）
