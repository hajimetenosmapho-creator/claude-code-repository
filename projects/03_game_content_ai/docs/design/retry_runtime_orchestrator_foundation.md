# v5.2.0 Retry Runtime Orchestrator Foundation 設計書（Project Charter / Architecture Design）

作成日：2026-07-09
状態：確定（Architecture Review Final・ユーザー承認済み・実装完了）

---

## 1. Project Charter

### 1.1 目的

「Retry Runtimeの実行順序を将来管理する場所」として`RetryRuntimeOrchestrator`を新設する。
本Releaseでは実行順序そのもの（`run_once()`等）は実装せず、次Release（Execution Release）が
安全に乗るための構造（Composition Rootとの責務分離・保持すべき依存の確定）のみを整える。

あわせて、`RetryCompositionRoot`（v5.1.0）にScheduler系3コンポーネント
（`RetrySchedulerSource` / `RetrySchedulerDecision` / `SchedulerEngine`）の配線を追加し、
Retry Queueに積まれた再試行候補がSchedulerEvent経由で実行可能な状態になる前提を整える。

### 1.2 背景

v5.1.0はEnqueue側（`RetryEnqueueTrigger`）とExecute側（`RetryManager`）が
`RetryQueueManager` / `RetryHistoryManager`を共有する前提条件を整えたが、
Architecture Reviewの過程で2つの追加の発見があった。

**発見A**：`RetryManager.execute_dispatchable_retries(events)`が要求する
`events: list[SchedulerEvent]`は、`RetryQueueManager → RetrySchedulerSource →
RetrySchedulerDecision → SchedulerEngine.evaluate()/run_due()`という経路でしか
得られない。v5.1.0の`RetryCompositionRoot`はこの経路を一切配線しておらず、
「Queueに積まれた候補を実行可能にする」ことが現状できなかった。

**発見B**：`RetryManager`の上位メソッド群（`apply_retry_queue_removals()` /
`apply_retry_queue_cleanup()` / `apply_retry_queue_terminal_cleanup()` /
`record_retry_history()`）は、それぞれ独立に`execute_dispatchable_retries(events)`を
再計算する。同一`events`に対してこれらを素朴に並べて呼び出すと、`retry()`
（実際のWorkflow再実行）が同一run_idに対して最大4回呼ばれるリスクがある。

これらの発見を踏まえ、ChatGPTレビューを経て以下の方針へ収束した。

- Scheduler系配線の追加だけを単独Releaseにするのは、Mechanicalな変更でSmall Release
  としての価値が薄い
- 「実行順序を管理する場所」として`RetryRuntimeOrchestrator`を新設し、Composition
  （組み立て）とOrchestration（実行順序）の責務分離を明確にする
- 発見Bの解決は、`RetryManager`へ`run_cycle()`等の統合APIを追加するのではなく、
  将来のExecution Releaseで**Orchestratorが`execute_dispatchable_retries()`を
  1回だけ呼び、その結果を保持して既存の公開Decider/Executor群
  （`RetryQueueUpdateDecider` / `RetryQueueRemovalExecutor` / `RetryQueueCleanupDecider` /
  `RetryQueueCleanupExecutor` / `RetryQueueTerminalCleanupDecider` /
  `RetryQueueTerminalCleanupExecutor` / `RetryHistoryRecordExecutor`。いずれも
  `retry_engine`から既に公開されているStateless・無引数コンストラクタのクラス）へ
  配布する**方向とする。これにより`retry_manager.py`は無改修のまま維持できる

### 1.3 Non-Goal（本Releaseで実施しないこと）

* `RetryRuntimeOrchestrator`への`run()` / `run_once()` / `loop()` / `daemon()` /
  `execute()`等のBusiness Logicの実装
* `RetryCompositionRoot`への実行系メソッドの追加（Composition Rootの責務は
  今後もDependency Injectionのみ）
* `RetryManager`への統合API（`run_cycle()`等）の追加（`retry_manager.py`は無改修）
* `scripts/`層へのBusiness Flowの実装（scriptsはEntry Pointのみ。本Releaseでは
  scriptsの追加自体を行わない）
* 発見Bの解決の実装（Decider/Executor直接構成による1回実行・結果配布の実装は
  次Execution Releaseへ送る。本Releaseでは方針の確定のみ）
* 既存パッケージ（`workflow_monitor` / `retry_queue` / `retry_history` /
  `retry_enqueue_trigger` / `retry_engine` / `workflow_engine` / `ai` /
  `execution_history` / `scheduler` / `retry_scheduler_source` /
  `retry_scheduler_decision`）への変更

---

## 2. Architecture Design

### 2.1 `RetryCompositionRoot`の拡張

```
src/retry_composition/retry_composition_root.py

RetryCompositionRoot.from_env()
   │
   ├─ ...（v5.1.0までの組み立て、無変更）...
   ├─ RetrySchedulerSource(queue)                          ★新規、同一queueインスタンスを注入
   ├─ RetrySchedulerDecision(retry_source)                  ★新規
   ├─ SchedulerEngine(retry_source=..., retry_decision=...) ★新規
   └─ ...（policy・manager組み立て、無変更）...
```

`__init__`に`retry_source` / `retry_decision` / `scheduler`の3属性を追加した。
既存の`monitor` / `queue` / `history` / `guard` / `trigger` / `policy` / `manager`は
そのまま維持し、新規3属性を末尾に追加する形とした（既存パラメータの並び順は変更しない）。

責務は引き続き「組み立てて属性として公開すること」のみ。新規business logicはゼロ。

### 2.2 `RetryRuntimeOrchestrator`（新規パッケージ）

```
src/retry_runtime_orchestrator/retry_runtime_orchestrator.py

class RetryRuntimeOrchestrator:
    trigger: RetryEnqueueTrigger
    scheduler: SchedulerEngine
    manager: RetryManager | NullRetryManager
    queue: RetryQueueManager | NullRetryQueueManager
    history: RetryHistoryManager
    policy: RetryPolicy

    @classmethod
    def from_composition_root(cls, root: RetryCompositionRoot) -> "RetryRuntimeOrchestrator":
        ...
```

`from_composition_root()`は`root`が保持する既存インスタンスをそのまま渡すだけの
薄いFactory Methodであり、新規インスタンスは一切生成しない。

### 2.3 Design Policy

1. **Compositionと Orchestration の責務分離を明確にする**。`RetryCompositionRoot`は
   今後もDependency Injectionのみを責務とし、実行系メソッドは追加しない。
   `RetryRuntimeOrchestrator`は「実行順序を管理する場所」だが、本Releaseでは
   その実行順序自体（`run_once()`等）は実装しない
2. **保持する依存は、次Execution Releaseで確定的に必要となるものに限定する**。
   `trigger` / `scheduler` / `manager`に加え、以下の理由で`queue` / `history` /
   `policy`も本Releaseから保持する（2.4節で詳述）
3. **新規インスタンスは生成しない**。`from_composition_root()`は`RetryCompositionRoot`
   が組み立てた参照をそのまま渡すのみであり、`queue` / `history`について
   trigger・manager側と別の参照が生まれることはない
4. **`guard` / `monitor`は保持しない**。`guard`は`RetryEnqueueTrigger`専属の内部
   コンポーネントであり、Orchestratorが直接参照する理由がない。`monitor`は
   本Release時点で確定した将来依存が存在しないため見送る

### 2.4 `queue` / `history` / `policy` を本Releaseから保持する理由

Architecture Reviewの過程で、以下がいずれも「次Execution Releaseで確定的に必要となる
依存」であることが判明した。

* `queue.remove` / `history.record`：発見Bの解決方針（1.2節）で、
  `RetryQueueRemovalExecutor.apply_all(decisions, remove_fn=queue.remove)` /
  `RetryHistoryRecordExecutor.record_all(execution_results, record_fn=history.record)`
  のように、Orchestratorが直接コールバックとして渡す必要がある
* `policy.max_attempts`：v5.1.0設計書6章が既に「次Release候補」として
  `trigger.enqueue_pending_failures(max_attempts=root.policy.max_attempts)`を
  明記しており、Orchestratorがこの値を取得する経路が必要

これらはDevelopment Charter 8章が禁じる「使われる保証のない実装の先回り」には
該当しない。実装（Business Logic）ではなく参照の保持のみであり、かつ利用が
確定している。もし本Releaseで`trigger` / `scheduler` / `manager`の3つのみを
保持した場合、次Releaseで確実にConstructor変更が発生することが分かっているため、
Foundation Releaseの時点でこれを確定させることを優先した。

### 2.5 却下した代替案

| 案 | 却下理由 |
|---|---|
| Scheduler配線のみを単独Releaseにする | Mechanicalな変更のみでSmall Releaseとしての価値が薄い。Orchestratorという受け皿を同時に定義してこそ意味を持つ |
| `RetryCompositionRoot`に`run_once()`等を追加する | Composition Rootの責務をDependency Injectionのみに固定する方針に反する |
| `scripts/run_retry_runtime.py`にBusiness Flowを直接書く | scriptsはEntry Pointに限定し、Business FlowはOrchestratorへ集約する方針に反する |
| `RetryManager`へ`run_cycle()`等の統合APIを追加する | `RetryManager`が実行順序（Trigger/Scheduler/Cleanup/Historyの呼び出し順）まで知ることになり、Single Responsibilityから外れる。既存の公開Decider/Executor群を`retry_manager.py`無改修のまま外部（Orchestrator）から直接構成する方が、責務分離を保ったまま同じ結果を得られる |
| `RetryRuntimeOrchestrator`が`RetryCompositionRoot`全体を1つの参照として保持する | 本プロジェクトの既存アーキテクチャ（`RetryManager`・`RetryCompositionRoot`自身を含め、個別のコンポーネントをConstructor Injectionで明示的に受け取る一貫した流儀）との整合性を優先し、不採用とした |
| `RetryRuntimeOrchestrator`が`trigger` / `scheduler` / `manager`の3つのみを保持する（当初案） | 次Execution Releaseで`queue` / `history` / `policy`が確実に必要になることが判明したため、Foundation Release完了直後に避けられるConstructor変更が発生する。2.4節の理由により`queue` / `history` / `policy`を含めることとした |

---

## 3. Architecture Review（Final）

**結論：Approve**

| 観点 | 判定 |
|---|---|
| Foundation First | ✅ `RetryRuntimeOrchestrator`はBusiness Logicを一切持たない。参照保持のみ |
| Small Release | ✅ 新規パッケージ1つ＋`RetryCompositionRoot`の属性拡張のみ。新規business logicはゼロ |
| YAGNI | ✅ `queue` / `history` / `policy`の保持は「実装の先回り」ではなく「既に確定した次Release設計のための参照の先回り」であり、Development Charter 8章の「使われる保証のない実装」には該当しない |
| Single Responsibility | ✅ Composition＝組み立て、Orchestration＝実行順序の置き場所、という責務分離を明確化。`retry_manager.py`は無改修のためRetryManagerのSRPも維持される |
| Backward Compatibility | ✅ 既存パッケージ（`workflow_monitor` / `retry_queue` / `retry_history` / `retry_enqueue_trigger` / `retry_engine` / `workflow_engine` / `ai` / `execution_history` / `scheduler` / `retry_scheduler_source` / `retry_scheduler_decision`）はいずれも無改修 |
| 既存アーキテクチャとの整合性 | ✅ `RetryCompositionRoot` / `RetryManager`と同じ「Constructor Injectionで個別に受け取る」流儀を踏襲 |
| Composition優先 | ✅ Orchestratorは新規インスタンスを一切生成せず、Composition Rootが組み立てた参照をそのまま受け取る |
| 検証可能性 | ✅ `from_composition_root(root)`で得た6属性すべてが`root`の対応する属性と`is`比較で同一であることを検証できる |

---

## 4. Compatibility

* `RetryCompositionRoot.__init__`に`retry_source` / `retry_decision` / `scheduler`の
  3属性が追加される。既存の呼び出し元は`from_env()`経由のみであり、
  `from_env()`のシグネチャ自体（`cls, base_dir=None`）は無変更のため、
  `RetryCompositionRoot`の利用者（本Release時点では存在しない）への影響はない
* v5.1.0の既存E2Eテスト（`tests/test_e2e_v5_1_0_retry_composition_root_foundation.py`
  テスト15：`__init__`のパラメータ一覧が`(self, monitor, queue, history, guard,
  trigger, policy, manager)`であることを確認する）は、本Releaseにより
  **恒久的にFAILする**（新規3パラメータが追加されたため）。これは`[KI-3]`以降
  一貫して記録してきた「Architecture Guardの既知差分」と同型であり、CHANGELOG.mdへ
  `[KI-19]`として記録する
* `src/retry_runtime_orchestrator/`を呼び出す既存コード（`scripts/`含む）は
  存在しない（消費者不在の先行実装。v3.1.0・v3.3.0・v3.5.0・v5.1.0と同型の
  Foundation First）

---

## 5. Known Issue（本Releaseでも未解消）

* **本Release単体では何も実行されない**。`RetryRuntimeOrchestrator`は
  `from_composition_root()`で組み立てられるだけであり、ユーザーから見て
  動く機能が増えるわけではない
* **発見B（同一サイクル内での多重実行リスク）は本Releaseでは解消しない**。
  解決方針（1.2節・2.5節）は確定したが、実装は次Execution Releaseへ送る
* `RetryQueueManager` / `RetryHistoryManager`の永続化は引き続き対象外

---

## 6. Future Architecture Consideration

* **次Release候補（Execution Release）**：`RetryRuntimeOrchestrator`に
  `run_once()`を追加し、以下の順序で1サイクル分を実行する。
  ```python
  self.trigger.enqueue_pending_failures(max_attempts=self.policy.max_attempts)
  events = self.scheduler.run_due(jobs=[])  # Retry候補由来のSchedulerEventのみ取得
  execution_results = self.manager.execute_dispatchable_retries(events)

  decisions = RetryQueueUpdateDecider().decide_all(execution_results)
  RetryQueueRemovalExecutor().apply_all(decisions, remove_fn=self.queue.remove)
  RetryQueueCleanupExecutor().apply_all(
      RetryQueueCleanupDecider().decide_all(decisions), remove_fn=self.queue.remove)
  RetryQueueTerminalCleanupExecutor().apply_all(
      RetryQueueTerminalCleanupDecider().decide_all(decisions), remove_fn=self.queue.remove)
  RetryHistoryRecordExecutor().record_all(execution_results, record_fn=self.history.record)
  ```
  `execute_dispatchable_retries()`は1回のみ呼び出され、`retry_manager.py`は無改修のまま
* ループ・デーモン化・タスクスケジューラ連携の要否は、上記`run_once()`が
  実運用でどう使われるかを踏まえて改めて判断する

---

## 7. Status

- [x] Architecture Review 完了（Final、ユーザー承認済み）
- [x] Implementation
- [x] Unit / E2E Test
- [x] Regression確認
- [x] Documentation更新
