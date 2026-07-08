# v4.7.0 Retry History Foundation 設計書（Architecture Design）

作成日：2026-07-09
状態：Architecture Review完了・承認済み・実装完了

---

## 1. Architecture Overview

`original_run_id`ごとの再試行履歴（試行回数・直近記録時刻）を記録するだけの
最小基盤。Retry可否判定・Retry実行・Queue操作・Enqueueガード判定はいずれも
行わない。

```
Scheduler        （判断、v2.6.0、無改修）
   │
Workflow Engine    （実行、v2.7.0、無改修）
   │
Execution History（記録、v2.8.0、無改修）
   │
Workflow Monitor（状態判定、v2.9.0、無改修）
   │
Retry Engine（再実行判断・依頼、v3.0.0〜v4.6.0、record_retry_history()のみ追加）
   │
   └── RetryHistoryRecordExecutor（retry_engine内、Stateless）★本Release
          │
          └── RetryHistoryManager（retry_history、新規独立パッケージ）★本Release
```

`RetryEnqueueTrigger`（v4.6.0）は本Releaseでは無改修のまま。記録結果を使って
再enqueueを止める判定は次Release以降に送る。

---

## 2. 情報源についての設計判断

Charter 1章で述べたとおり、`retry_enqueue_trigger_foundation.md`が対策候補として
挙げていた`metadata["retried_from"]`は、`WorkflowExecutionRecord`
（`execution_history/workflow_execution_record.py`）に`metadata`フィールドが
存在しないため、実際には参照不可能である。

```python
# execution_history/workflow_execution_record.py（無改修）
@dataclass
class WorkflowExecutionRecord:
    run_id: str
    workflow_name: str
    source: str
    job_id: str
    status: WorkflowExecutionStatus
    started_at: datetime
    finished_at: datetime | None = None
    steps: list[StepExecutionRecord] = field(default_factory=list)
    events: list[ExecutionHistoryEvent] = field(default_factory=list)
    error_message: str | None = None
    # metadata フィールドは存在しない
```

`WorkflowEngineExecutor`（`workflow_engine_executor.py` 78行目付近）も
`ExecutionHistoryManager.start_run()`へ`metadata`を渡していない。したがって
`WorkflowMonitorRecord`（Workflow Monitorの公開データ）からも`retried_from`は
一切参照できない。

本Releaseは、この事実を踏まえ、情報源を`RetryResult`（`retry_engine/retry_result.py`、
v3.0.0、無改修）に限定する。`RetryResult`は`RetryManager.retry()`が実行のたびに
直接生成するデータであり、`original_run_id` / `outcome` / `attempt`を常に保持して
いるため、Execution Historyの拡張を一切必要としない。

---

## 3. Package Structure

```
src/retry_history/                      ★新規独立パッケージ
├── __init__.py                         # 公開シンボルのexport
├── retry_history_record.py             # RetryHistoryRecord（frozen dataclass）
├── retry_history_manager.py            # RetryHistoryManager
└── null_retry_history_manager.py       # NullRetryHistoryManager

src/retry_engine/
├── retry_history_recorder.py           ★新規：RetryHistoryRecordResult / RetryHistoryRecordExecutor
├── retry_manager.py                    （変更：history / history_recorder 引数、record_retry_history()追加）
└── __init__.py                         （変更：新規シンボルexport）
```

`retry_queue`と同型（`RetryQueueManager` / `NullRetryQueueManager`が別々の`.py`に
分かれている構成）を踏襲し、`RetryHistoryManager` / `NullRetryHistoryManager`も
ファイルを分離した。

---

## 4. Public API

### `retry_history/retry_history_record.py`（新規）

```python
@dataclass(frozen=True)
class RetryHistoryRecord:
    original_run_id: str
    attempt_count: int
    last_attempt: int
    last_recorded_at: datetime
```

### `retry_history/retry_history_manager.py`（新規）

```python
class RetryHistoryManager:
    def __init__(self): ...
    def record(self, original_run_id: str, attempt: int, recorded_at: datetime) -> RetryHistoryRecord: ...
    def get(self, original_run_id: str) -> RetryHistoryRecord | None: ...
    def has_history(self, original_run_id: str) -> bool: ...
```

`record()`は既存レコードがあれば`attempt_count`をインクリメントし、
`last_attempt` / `last_recorded_at`を更新する。呼び出し元へ返す値は常にコピー
（`dataclasses.replace()`）。

### `retry_history/null_retry_history_manager.py`（新規）

```python
class NullRetryHistoryManager:
    def record(self, original_run_id, attempt, recorded_at) -> None: ...
    def get(self, original_run_id) -> None: ...
    def has_history(self, original_run_id) -> bool: ...  # 常にFalse
```

`ExecutionHistoryManager`の`NullExecutionHistoryManager.start_run()`と同じ方針で、
`record()`は`None`を返す（「記録されなかった」ことを明示する）。

### `retry_engine/retry_history_recorder.py`（新規）

```python
RecordFn = Callable[[str, int, datetime], "RetryHistoryRecord | None"]

@dataclass(frozen=True)
class RetryHistoryRecordResult:
    execution_result: RetryExecutionResult
    recorded: bool
    history_record: "RetryHistoryRecord | None"
    reason: str

class RetryHistoryRecordExecutor:
    def record_all(self, execution_results, record_fn: RecordFn) -> list[RetryHistoryRecordResult]: ...
    def record(self, execution_result, record_fn: RecordFn) -> RetryHistoryRecordResult: ...
```

`RetryQueueRemovalExecutor`（v4.2.0）と同じ設計言語：`RetryHistoryManager`型を
直接importせず、`record_fn`をメソッド引数で受け取る。コンストラクタ引数を
一切取らない（Stateless）。

### `retry_manager.py`（変更部分のみ）

```python
def __init__(
    self,
    ...,  # 既存引数はすべて無変更
    terminal_cleanup_executor: RetryQueueTerminalCleanupExecutor | None = None,
    history: "RetryHistoryManager | NullRetryHistoryManager | None" = None,       # ★新規（末尾）
    history_recorder: RetryHistoryRecordExecutor | None = None,                    # ★新規（末尾）
):
    ...
    self._history = history if history is not None else NullRetryHistoryManager()
    self._history_recorder = history_recorder if history_recorder is not None else RetryHistoryRecordExecutor()

def record_retry_history(
    self, events: list[SchedulerEvent], dry_run: bool = False
) -> list[RetryHistoryRecordResult]:
    execution_results = self.execute_dispatchable_retries(events, dry_run=dry_run)
    return self._history_recorder.record_all(execution_results, record_fn=self._history.record)
```

`NullRetryManager.record_retry_history()`は常に`[]`を返す。

---

## 5. Class Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryHistoryRecord` | 1つの`original_run_id`についての再試行履歴を保持する（データのみ） | 判定・記録処理そのもの |
| `RetryHistoryManager` | `original_run_id`ごとの再試行履歴を記録・参照する | Retry可否判定・Retry実行・Queue操作 |
| `NullRetryHistoryManager` | 無効時のダミー実装 | 実データの保持 |
| `RetryHistoryRecordExecutor` | `RetryExecutionResult`のうちoutcome=RETRIEDの項目のみ`record_fn`を呼び出す | `RetryHistoryManager`型への直接依存・判定ロジックの複製 |
| `RetryManager.record_retry_history()` | 上記2コンポーネントへの薄い委譲 | 記録ロジック自体の実装 |

---

## 6. Data Flow

```
RetryManager.record_retry_history(events, dry_run=False)
    │
    ├─ 1. self.execute_dispatchable_retries(events, dry_run=dry_run)（v4.0.0、無変更）
    │       └─ dispatchable=Trueの候補についてretry()を呼び出し、RetryExecutionResultを集約
    │
    └─ 2. self._history_recorder.record_all(execution_results, record_fn=self._history.record)
            │
            └─ 各RetryExecutionResultについて：
                 retry_result.outcome == RETRIED の場合のみ
                   → record_fn(original_run_id, attempt, datetime.now())
                   → RetryHistoryRecordResult(recorded=True, history_record=...)
                 それ以外（SKIPPED / NOT_FOUND / DISABLED）
                   → RetryHistoryRecordResult(recorded=False, history_record=None)
```

---

## 7. Boundary（今回入れない境界線）

### 7.1 消費側（無限再投入ガード）への接続

`record_retry_history()`の結果を`RetryEnqueueTrigger`（v4.6.0）の
`enqueue_pending_failures()`へ反映する処理は本Releaseには一切存在しない。
`RetryEnqueueTrigger`は本Releaseでも無改修のまま。次Release以降で、
`RetryHistoryManager.has_history()` / `get()`を参照する新しいガード判定
（例：`RetryEnqueueGuard`）を追加する想定。

### 7.2 `RetryPolicy.max_attempts`との統合

`RetryHistoryManager`は「何回再試行されたか」を記録するのみで、
`max_attempts`と比較して「これ以上再試行すべきでない」と判定する処理は
持たない。この判定は次Release以降の消費側コンポーネントの責務とする。

### 7.3 永続化

`RetryHistoryManager`はプロセス内メモリ（`dict`）のみで構成され、ファイル・DBへの
書き込みは一切行わない（`retry_queue`と同じ扱い）。

---

## 8. Compatibility

* 新規独立パッケージ`src/retry_history/`の追加、および`retry_engine`パッケージ内の
  新規ファイル1点（`retry_history_recorder.py`）の追加
* `retry_manager.py`の変更は、末尾デフォルト引数2点の追加と`record_retry_history()`
  の新設のみ。既存メソッド（`retry()` 〜 `apply_retry_queue_terminal_cleanup()`）は
  1行も変更していない
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` /
  `retry_event_consumer.py` / `retry_event_dispatcher.py` / `retry_execution_selector.py` /
  `retry_execution_coordinator.py` / `retry_queue_update_decider.py` /
  `retry_queue_removal_executor.py` / `retry_queue_cleanup_decider.py` /
  `retry_queue_cleanup_executor.py` / `retry_queue_terminal_cleanup_decider.py` /
  `retry_queue_terminal_cleanup_executor.py` / `retry_outcome_terminality.py` /
  `retry_policy.py` / `retry_policy_protocol.py` / `retry_enqueue_trigger`はいずれも
  本Releaseでも無改修（ゼロ改修）
* `retry_history`は`retry_engine`を一切importしない（循環なし）

---

## 9. Design Decisions（設計判断の根拠）

### Design Decision #1：情報源を`RetryResult`に限定する

Execution Historyの`metadata`拡張（`WorkflowExecutionRecord`への`metadata`
フィールド追加）という選択肢もあったが、これは`execution_history`パッケージ本体の
スキーマ変更を伴い、v2.8.0以降維持されてきた「ゼロ改修」の対象範囲を広げてしまう。
`RetryResult`（`retry_engine`自身が生成するデータ）だけで目的（再試行履歴の記録）を
達成できるため、本Releaseでは`execution_history`に一切触れない設計とした。

### Design Decision #2：`history`省略時は`NullRetryHistoryManager()`にフォールバックする

`event_consumer`等のStateless系コンポーネントは省略時に実体へフォールバックするが、
`RetryHistoryManager`は`RetryQueueManager`と同じstateful storeであるため、
`queue`引数と同じ扱い（省略時はNullへフォールバック）とした。これにより、
本Releaseの新規引数を渡さない既存の呼び出しは、記録が一切行われない
（＝本Release前と観測可能な挙動が完全に同じ）という安全側のデフォルトになる。

### Design Decision #3：`RetryHistoryRecordExecutor`は`record_fn`経由の疎結合とする

`RetryQueueRemovalExecutor`（v4.2.0）と同じ設計言語を踏襲し、
`RetryHistoryManager` / `NullRetryHistoryManager`型への直接依存を持たせず、
`record_fn: Callable[[str, int, datetime], RetryHistoryRecord | None]`として
メソッド引数で受け取る。これにより`RetryHistoryRecordExecutor`は完全にStateless
であり、テストではFakeの`record_fn`を渡すだけで単体テストできる。

### Design Decision #4：`record_all()`は1:1対応（記録対象外も結果に含める）

`RetryQueueUpdateDecider.decide_all()`等の既存Decider群と同じ設計言語を踏襲し、
`record_all()`は入力`RetryExecutionResult`と同じ件数・順序で
`RetryHistoryRecordResult`を返す。`outcome != RETRIED`の項目も
`recorded=False`として結果に含め、暗黙に取り除かない。

### Design Decision #5：`dry_run`は記録の実施可否に影響させない

`apply_retry_queue_removals()`等の既存メソッドは、`dry_run`が`execute_dispatchable_retries()`
経由でWorkflow実行の副作用（News収集・WordPress投稿等）のみを抑制し、Queue側の
後始末（`remove()`呼び出し）自体は`dry_run`の値に関わらず実行するという既存パターンを
持つ。`record_retry_history()`もこのパターンを踏襲し、記録処理自体はメモリ上の
操作のみで外部副作用を持たないため、`dry_run`の値に関わらず実行する。

---

## 10. Future Extension

* **Retry Enqueue Guard**：`RetryHistoryManager.has_history()` / `get()`を参照し、
  `RetryEnqueueTrigger.enqueue_pending_failures()`が既に再試行済みの`run_id`を
  再enqueueしないようにする新規コンポーネント（無限再投入対策の完成）
* **`RetryPolicy.max_attempts`との統合**：`RetryHistoryRecord.attempt_count`と
  `RetryPolicy.max_attempts`を比較し、上限到達を判定する仕組み
* **永続化**：`RetryQueueManager`と同様、プロセス終了で履歴が失われる制約を
  解消する場合はQueue永続化と合わせて再評価する

---

## 11. Architecture Review

### 11.1 レビュー観点別の判定

| 観点 | 判定 | 備考 |
|---|---|---|
| Foundation First | ✅ | 記録のみ。消費側（無限再投入ガード）は次Release以降に送る |
| Single Responsibility | ✅ | `retry_history`はQueue管理・判定・Retry実行のいずれも行わない |
| Stateless（コンポーネント単位） | ✅ | `RetryHistoryRecordExecutor`はStateless。状態を保持するのは`RetryHistoryManager`のみ |
| Backward Compatibility | ✅ | 末尾デフォルト引数のみ。既存メソッドは1行も変更していない |
| Composition | ✅ | 変更ファイルは`retry_manager.py`・`__init__.py`のみ。新規ファイルは独立パッケージ側に閉じる |

### 11.2 残された懸念（Known Issueとして記録）

* 本Releaseでは無限再投入対策そのものは未解消のまま（記録の土台ができた段階に
  留まる）。`docs/CHANGELOG.md` `[KI-15]`に記録する。
* `record_retry_history()`は`decide_retry_queue_updates()`等の既存メソッド群と同じ
  「呼ばれるたびに`execute_dispatchable_retries()`を再実行する」構造を持つ。同じ
  `events`に対して複数の委譲メソッドを呼ぶと`retry()`が重複実行されうるが、これは
  v4.1.0〜v4.4.0から継続する既存の系統的特性であり、本Releaseで新たに導入した
  問題ではないため対応しない。
