# v5.3.0 Retry Runtime Run Once Foundation 設計書（Project Charter / Architecture Design）

作成日：2026-07-09
状態：確定（Architecture Review Final・ユーザー承認済み・実装完了）

---

## 1. Project Charter

### 1.1 目的

`RetryRuntimeOrchestrator`（v5.2.0）へ`run_once()`を追加し、Retry Runtimeを
**1サイクルだけ**安全に実行できるようにする。v5.2.0のArchitecture Reviewで発見された
「発見B」（`execute_dispatchable_retries()`の多重実行リスク）を、`RetryManager`を
無改修のまま解消することが本Releaseの中核である。

### 1.2 背景

v5.2.0の設計書（`retry_runtime_orchestrator_foundation.md`）6章「Future Architecture
Consideration」に、本Releaseで実装すべき`run_once()`の方針がすでに具体的に記載されて
いた。本Releaseはこの方針をそのまま実装へ落とし込む。

v5.2.0で発見された2つの課題（再掲）：

- **発見A**（v5.2.0で解消済み）：`RetryManager.execute_dispatchable_retries(events)`が
  要求する`events`は`RetryQueueManager → RetrySchedulerSource → RetrySchedulerDecision →
  SchedulerEngine`という経路でしか得られない。`RetryCompositionRoot`へこの配線を追加済み。
- **発見B**（本Releaseで解消）：`RetryManager`の上位メソッド群
  （`apply_retry_queue_removals()` / `apply_retry_queue_cleanup()` /
  `apply_retry_queue_terminal_cleanup()` / `record_retry_history()`）は、それぞれ独立に
  `execute_dispatchable_retries(events)`を再計算するため、同一`events`に対してこれらを
  素朴に並べて呼び出すと`retry()`が同一run_idに対して最大4回呼ばれるリスクがある。

### 1.3 Non-Goal（本Releaseで実施しないこと）

* `RetryRuntimeOrchestrator`への`loop()` / `daemon()`の実装
* `run_once()`への`dry_run`引数の追加（4章で詳述。安全なdry_runにならないため）
* `run_once()`を呼び出す`scripts/`エントリーポイントの追加
* `RetryManager`への統合API（`run_cycle()`等）の追加（`retry_manager.py`は無改修）
* `SchedulerEngine`へのRetry専用API（例：`run_retry_due()`）の追加
* 既存パッケージ（`workflow_monitor` / `retry_queue` / `retry_history` /
  `retry_enqueue_trigger` / `retry_engine` / `workflow_engine` / `ai` /
  `execution_history` / `scheduler` / `retry_scheduler_source` /
  `retry_scheduler_decision`）への変更

---

## 2. Architecture Design（採用案）

### 2.1 `run_once()`の実行順序

```python
def run_once(self) -> RetryRuntimeCycleResult:
    trigger_result = self.trigger.enqueue_pending_failures(max_attempts=self.policy.max_attempts)

    events = self.scheduler.run_due(jobs=[])  # Retry候補由来のSchedulerEventのみ取得

    execution_results = self.manager.execute_dispatchable_retries(events)  # 必ず1回だけ

    decisions = RetryQueueUpdateDecider().decide_all(execution_results)
    removal_results = RetryQueueRemovalExecutor().apply_all(decisions, remove_fn=self.queue.remove)
    cleanup_results = RetryQueueCleanupExecutor().apply_all(
        RetryQueueCleanupDecider().decide_all(decisions), remove_fn=self.queue.remove)
    terminal_cleanup_results = RetryQueueTerminalCleanupExecutor().apply_all(
        RetryQueueTerminalCleanupDecider().decide_all(decisions), remove_fn=self.queue.remove)
    history_results = RetryHistoryRecordExecutor().record_all(
        execution_results, record_fn=self.history.record)

    return RetryRuntimeCycleResult(
        trigger_result=trigger_result,
        scheduler_events=events,
        execution_results=execution_results,
        removal_results=removal_results,
        cleanup_results=cleanup_results,
        terminal_cleanup_results=terminal_cleanup_results,
        history_results=history_results,
    )
```

```
RetryEnqueueTrigger
        │
        ▼
SchedulerEngine
        │
        ▼
RetryManager.execute_dispatchable_retries()  ← 必ず1回だけ
        │
        ▼
RetryQueueUpdateDecider
        │
        ▼
RetryQueueRemovalExecutor
        │
        ▼
RetryQueueCleanupExecutor
        │
        ▼
RetryQueueTerminalCleanupExecutor
        │
        ▼
RetryHistoryRecordExecutor
```

`RetryQueueUpdateDecider`が生成する`decisions`（`list[RetryQueueUpdateDecision]`）は、
Removal / Cleanup / TerminalCleanupの3系統に**共有**される。COMPLETE/FAIL（Removal対象）・
SKIPPED由来のNOOP（Cleanup対象）・NOT_FOUND由来のNOOP（TerminalCleanup対象）は
構造的に排他であり、同一`run_id`に対して`queue.remove()`が二重に呼ばれることはない
（`retry_engine`側のDecider実装で「対象外はKEEP」として構造的に除外されていることを
実コードで確認済み）。

### 2.2 `RetryRuntimeCycleResult`（新規）

```python
@dataclass(frozen=True)
class RetryRuntimeCycleResult:
    trigger_result: RetryEnqueueTriggerResult
    scheduler_events: list[SchedulerEvent]
    execution_results: list[RetryExecutionResult]
    removal_results: list[RetryQueueRemovalResult]
    cleanup_results: list[RetryQueueCleanupResult]
    terminal_cleanup_results: list[RetryQueueTerminalCleanupResult]
    history_results: list[RetryHistoryRecordResult]
```

`run_once()`は`None`ではなく本結果オブジェクトを返す。理由：

* 本プロジェクトの一貫した流儀（`RetryEnqueueTriggerResult`等、必ず結果オブジェクトを
  返す）に合わせるため
* Development Charter 3章「壊れたときに気づけることを品質の一部として扱う」に基づき、
  1サイクルで何が起きたか（Enqueue件数・Retry候補件数・実行結果・Queue更新・履歴記録）
  を外部から確認できるようにするため
* `scheduler_events`を保持することで、Schedulerが返した候補件数と`trigger_result`
  （Enqueue件数）を突き合わせて確認できる（デバッグ・監視・テスト容易性）

### 2.3 Design Policy

1. **`execute_dispatchable_retries()`は`run_once()`内で必ず1回だけ呼び出す**。その
   戻り値（`execution_results`）を保持したまま、Queue更新・Cleanup・History記録の
   各Decider/Executorへ配布する。これにより発見Bの多重実行リスクを構造的に解消する
2. **`RetryManager`は無改修のまま維持する**。`run_cycle()`等の統合APIは追加しない。
   実行順序の知識は`RetryRuntimeOrchestrator.run_once()`だけに閉じる
   （Single Responsibility）
3. **Decider/Executorは既存の公開シンボルをそのまま`retry_engine`からimportして使う**。
   いずれも`__init__`引数を持たないStateless実装であることをソースコードで確認済み
4. **`scheduler.run_due(jobs=[])`を利用する**。`jobs=[]`によりJob判定ループは
   空振りするだけで、Retry候補由来の`SchedulerEvent`のみを取得できる
   （`scheduler_engine.py`のコードで確認済み）
5. **`dry_run`は追加しない**（4章）
6. **例外はそのまま呼び出し元へ伝播させる（fail-fast）**。既存の
   `RetryExecutionCoordinator.execute()`が「retry_fnが例外を送出した場合はそのまま
   伝播させる」という方針を採用しているため（Design Decision #7）、`run_once()`でも
   同じ方針を踏襲し、途中のステップだけ独自にtry/exceptで握りつぶすことはしない

### 2.4 却下した代替案

| 案 | 却下理由 |
|---|---|
| `RetryManager`へ`run_cycle()`統合APIを追加する | v5.2.0で既に却下済み（`RetryManager`が実行順序まで知ることになりSingle Responsibilityから外れる）。本Releaseでも同じ理由で不採用 |
| `run_once()`に`dry_run`引数を追加し`execute_dispatchable_retries(events, dry_run=dry_run)`へそのまま渡す | `RetryExecutor.execute()`はdry_runの値に関わらず常に`outcome=RetryOutcome.RETRIED`を返すため、Queue除去（`queue.remove()`）・History記録（`history.record()`）という実際の副作用がdry_run=Trueでも実行されてしまう。「安全なはずのdry_runが実は副作用を起こす」という、最も避けたい種類のバグを生むため不採用（4章で詳述） |
| `scripts/run_retry_runtime.py`を同時に追加する | Small Release原則。`run_once()`本体の設計・実装・テストに集中し、起動スクリプトは動作確認後の次の区切りに回す |
| `run_once()`内で各ステップをtry/exceptで囲み部分失敗時も継続する | 既存コード全体が一貫してfail-fast方針（`RetryExecutionCoordinator`Design Decision #7）。ここだけ挙動を変えると既存アーキテクチャとの整合性が崩れる |
| `SchedulerEngine`に`run_retry_due()`等のRetry専用APIを新設する | `scheduler`パッケージへの変更はNon-Goal。`run_due(jobs=[])`で目的を達成できるため今回は不要（4章のFuture Architecture Considerationとして記録するに留める） |

---

## 3. Architecture Review（Final）

**結論：Approve**

| 観点 | 判定 | コメント |
|---|---|---|
| Foundation First → Execution First | ✅ | v5.2.0までの土台がそのまま機能することを実コードで確認済み |
| Small Release | ✅ | `run_once()`と`RetryRuntimeCycleResult`の追加のみ。scripts/・dry_run・loopは対象外として明確に除外 |
| Single Responsibility | ✅ | `retry_manager.py`は無改修。実行順序の知識は`RetryRuntimeOrchestrator`だけに閉じる |
| Backward Compatibility | ✅ | 既存11パッケージ（`workflow_monitor`〜`retry_scheduler_decision`）はいずれも無改修 |
| Stateless / Composition優先 | ✅ | Decider/Executorは無引数コンストラクタで都度生成。新規インスタンスの保持・使い回しは行わない |
| 安全性（Development Charter最優先事項） | ✅ | dry_runの安全上の問題を発見し、今回のスコープから明示的に除外することで回避 |
| 検証可能性 | ✅ | `RetryRuntimeCycleResult`により1サイクルの全結果を外部から確認できる |

---

## 4. dry_runを追加しない理由（Known Issue）

`RetryExecutor.execute()`（`retry_executor.py`）は、`dry_run`の値に関わらず常に
`outcome=RetryOutcome.RETRIED`を返す。`dry_run`は`WorkflowEngineManager.run(event,
dry_run=...)`の内部にのみ伝わり、`RetryResult.outcome`自体は変化しない。

一方、`RetryQueueUpdateDecider` / `RetryQueueRemovalExecutor` / `RetryHistoryRecordExecutor`
は、いずれも`RetryResult.outcome`（＝常にRETRIED）だけを見て動作を決める。`dry_run`という
概念そのものを一切知らない。

つまり、もし`run_once()`に`dry_run`引数を追加し`execute_dispatchable_retries(events,
dry_run=True)`へそのまま渡すと、Workflow自体の再実行はdry_runで抑制されるが、
**`queue.remove()`（Queueからの実削除）と`history.record()`（履歴への実書き込み）は、
dry_runかどうかに関係なく実行されてしまう**。

これは「dry_runのつもりで実行したら、実際にQueueと履歴が書き換わっていた」という、
Development Charter 3章が最も警戒する種類の誤動作である。本Releaseでは`dry_run`引数を
追加せず、実際にRetryが実行される前提で設計する。安全な確認手段（本当のdry_run）は、
Decider/Executor層が`dry_run`を正しく認識できるようになってから、独立したReleaseとして
設計し直す。

---

## 5. Compatibility

* `RetryRuntimeOrchestrator.__init__`・`from_composition_root()`のシグネチャは無変更
* `RetryRuntimeOrchestrator`に`run_once()`が追加される。v5.2.0の既存E2Eテスト
  （`tests/test_e2e_v5_2_0_retry_runtime_orchestrator_foundation.py`テスト18：
  「`from_composition_root`以外の公開メソッドが存在しない」ことを確認するテスト）は、
  本Releaseにより**恒久的にFAILする**（`run_once()`という新規公開メソッドが追加された
  ため）。これは`[KI-3]`以降一貫して記録してきた「Architecture Guardの既知差分」と
  同型であり、CHANGELOG.mdへ`[KI-20]`として記録する
* `src/retry_runtime_orchestrator/`を呼び出す既存コード（`scripts/`含む）は
  引き続き存在しない（消費者不在の先行実装）

---

## 6. Known Issue（本Releaseでも未解消）

* **`dry_run`は未対応**（4章）。安全なdry_runの設計は将来の独立Releaseへ送る
* **同一サイクル内での即時再試行**：`trigger.enqueue_pending_failures()`で新規に
  Enqueueされた`run_id`は、直後の`scheduler.run_due(jobs=[])`でそのまま候補として
  拾われ、同じ`run_once()`呼び出し内で即座に`retry()`される。失敗検知から再試行までの
  間に待ち時間（バックオフ）が一切ないのは、既存の`RetryPolicy`設計（Exponential
  Backoff等は既存Known Issueとして将来送り）からの継続的な制約であり、本Releaseが
  新規に生む問題ではないが、`run_once()`によって初めて実際に動く経路になる
* **`scheduler.run_due()`は常にシステム時刻を使う**：`RetryCompositionRoot.from_env()`
  は`SchedulerEngine`に`clock`を渡していないため、`run_once()`の呼び出しは常に実時刻
  依存になる（テスト時は個別にFakeで代替する）
* `RetryQueueManager` / `RetryHistoryManager`の永続化は引き続き対象外
* `run_once()`を呼び出す起動スクリプト（`scripts/`）は引き続き未着手

---

## 7. Future Architecture Consideration

* **`scripts/run_retry_runtime.py`**（次Release候補）：`RetryRuntimeOrchestrator.
  from_composition_root(RetryCompositionRoot.from_env()).run_once()`を1回呼び出すだけの
  Entry Point。ループ・デーモン化は含まない
* **Retry専用Scheduler API**：現時点では`SchedulerEngine.run_due(jobs=[])`を利用する。
  「空リストを渡すこと」がRetry Runtimeの意味になっている点は、将来
  `run_retry_due()`のような専用APIが`scheduler`パッケージへ追加された場合に
  置き換え可能とする（本Releaseでは実装しない）
* **安全なdry_run**：Decider/Executor層（`RetryQueueUpdateDecider`等）が`dry_run`を
  認識できるようになった段階で、独立Releaseとして再設計する
* ループ・デーモン化・タスクスケジューラ連携の要否は、`run_once()`が実運用で
  どう使われるかを踏まえて改めて判断する

---

## 8. Status

- [x] Architecture Review 完了（Final、ユーザー承認済み）
- [x] Implementation
- [x] Unit / E2E Test
- [x] Regression確認
- [x] Documentation更新
