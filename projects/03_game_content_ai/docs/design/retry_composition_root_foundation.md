# v5.1.0 Retry Composition Root Foundation 設計書（Project Charter / Architecture Design）

作成日：2026-07-09
状態：確定（Architecture Review Final・ユーザー承認済み・実装完了）

---

## 1. Project Charter

### 1.1 目的

`RetryEnqueueTrigger`（Enqueue側）と`RetryManager`（Execute側）が、同一の
`RetryQueueManager` / `RetryHistoryManager`インスタンスを共有した状態で組み立てられる
Composition Rootを新設する。これにより、将来Enqueue・Executeを同一プロセス内で
呼び出す際に、Queue内容・再試行履歴が正しく共有される前提条件を整える。

### 1.2 背景

v5.0.0で`RetryEnqueueGuard`の判定基準を「`next_attempt > max_attempts`」の回数比較へ
精緻化したが、この判定が実際に意味を持つのは、Enqueueで記録された再試行履歴を
その後のExecuteが読み書きし、次のEnqueueがそれを再度参照する、という一連の流れが
**同一のQueue/Historyインスタンス上で完結する場合のみ**である。

`RetryQueueManager` / `RetryHistoryManager`はいずれもプロセス内メモリの`dict`のみで
状態を保持し、永続化を持たない。そのため、Enqueue用スクリプトとExecute用スクリプトを
別々に構築・実行すると、それぞれが独立した空のQueue/Historyを持つことになり、
v4.7.0〜v5.0.0で構築したGuardの回数比較判定が実運用上意味を持たなくなるという
アーキテクチャ上のリスクが、Architecture Reviewの過程で判明した。

本Releaseは、このリスクに対する解決策として、「実行順序の決定・ループ・デーモン化」を
一切伴わない**組み立てのみ**のComposition Root（`RetryCompositionRoot`）を新設し、
`RetryQueueManager` / `RetryHistoryManager`を1インスタンスずつ生成して
`RetryEnqueueTrigger`・`RetryManager`の両方へ注入する。

### 1.3 Non-Goal（本Releaseで実施しないこと）

* 実行順序の決定（`enqueue_pending_failures()` / `execute_dispatchable_retries()`等を
  呼び出す独自メソッド、例：`run_once()`）
* ループ・デーモン化・タスクスケジューラ連携
* `RetryCompositionRoot`を実際に呼び出す起動スクリプト（`scripts/`配下）
* `RetryQueueManager` / `RetryHistoryManager`の永続化
* 新規Configクラス・Feature Gate（すべて下位の既存Configの`is_ready()`判定に委譲する）
* 既存パッケージ（`workflow_monitor` / `retry_queue` / `retry_history` /
  `retry_enqueue_trigger` / `retry_engine` / `workflow_engine` / `ai` /
  `execution_history`）への変更

---

## 2. Architecture Design

### 2.1 配置・命名（Architecture Reviewでの再検討結果）

* パッケージ：`src/retry_composition/`（`src/runtime/` / `src/application/`のような
  汎用Compositionレイヤは採用しない。`src/`配下の既存16パッケージがすべてドメイン
  スコープの命名であり、Composition Rootが必要な系統が現時点で`retry`関連の1つに
  限られる段階での汎用レイヤ新設は時期尚早な抽象化と判断した）
* クラス名：`RetryCompositionRoot`（`RetryRuntime`は不採用。「Runtime」は実行責任を
  連想させ、本Releaseの「組み立てのみ・実行しない」という責務境界と矛盾するため。
  `RetryRuntimeBuilder` / `RetryRuntimeFactory`も、生成後に`trigger` / `manager`への
  参照を保持し続ける本クラスの性質（使い捨てでない）とはやや不一致と判断し不採用。
  本セッションのArchitecture Reviewで一貫して使ってきた「Composition Root」という
  既存語彙をそのままクラス名に採用することで、設計文書と実装の対応関係を明確にした）

### 2.2 構成

```
src/retry_composition/retry_composition_root.py

class RetryCompositionRoot:
    monitor: WorkflowMonitorManager | NullWorkflowMonitorManager
    queue: RetryQueueManager | NullRetryQueueManager
    history: RetryHistoryManager
    guard: RetryEnqueueGuard
    trigger: RetryEnqueueTrigger
    policy: RetryPolicy
    manager: RetryManager | NullRetryManager

    @classmethod
    def from_env(cls, base_dir: Path | None = None) -> "RetryCompositionRoot":
        ...
```

`from_env()`は既存の`from_env()`/`from_config()`のみを呼び出して組み立てる。

```
WorkflowMonitorManager.from_config(ExecutionHistoryConfig.from_env(...), WorkflowMonitorConfig.from_env())
RetryQueueManager.from_config(RetryQueueConfig.from_env())          ★1インスタンスのみ生成
RetryHistoryManager()                                                ★1インスタンスのみ生成
RetryEnqueueGuard()
RetryEnqueueTrigger(monitor=monitor, queue=queue, history=history, guard=guard)
RetryPolicy.from_env()
WorkflowEngineManager.from_config(AgentConfig.from_env(...), WorkflowEngineConfig.from_env(...))
RetryManager.from_config(
    retry_config=RetryConfig.from_env(), retry_policy=policy,
    workflow_engine_manager=..., workflow_monitor_manager=monitor,
    retry_queue_manager=queue,      ← trigger と同一インスタンス
    retry_history_manager=history,  ← trigger と同一インスタンス
)
```

### 2.3 Design Policy

1. **責務は「組み立てて属性として公開すること」のみ**。`RetryCompositionRoot`は
   `from_env()`以外の公開メソッドを持たない（`run()` / `run_once()` / `execute()` /
   `loop()` / `start()` / `daemon()`等はいずれも追加しない）
2. **Queue/Historyインスタンスの共有が本Releaseの中核**。`RetryQueueManager` /
   `RetryHistoryManager`はそれぞれ`from_env()`内で1回だけ生成し、`trigger`と
   `manager`の両方へ同一インスタンスを注入する
3. **RetryEnqueueTrigger / RetryEnqueueGuardは常に実体を構築する**。両者は
   Feature Gateを持たない設計（v4.6.0・v4.8.0）のため、`monitor` / `queue`が
   下位ゲート閉鎖によりNull実装であっても、`RetryEnqueueTrigger`自体は常に実体で
   構築し、Null実装側の安全な戻り値（空リスト・DISABLED）をそのまま受け取る
4. **新規business logicは追加しない**。各値の組み立てはすべて既存の
   `from_env()`/`from_config()`への委譲のみで完結する
5. **新規Configクラス・Feature Gateは追加しない**。`RetryCompositionRoot`自体に
   `is_ready()`は持たせず、すべて下位の既存Configの判定にそのまま委譲する

### 2.4 却下した代替案

| 案 | 却下理由 |
|---|---|
| Enqueue単体のComposition Root（`RetryEnqueueTrigger`のみを配線するスクリプト） | Queue/Historyインスタンスの共有問題を解決できず、Runtime全体を組む段階になった時点で書き直しが発生する「使い捨てComposition Root」になる |
| `RetryCompositionRoot`に`run_once()`等の実行メソッドを持たせる | 「Composition（組み立て）」と「オーケストレーション（実行順序の決定）」は別の責務であり、混ぜるとDevelopment Charter 4章「一つの変更は一つの目的のために行う」に反する |
| ループ・デーモン化・タスクスケジューラ連携を本Releaseに含める | Small Release逸脱。`RetryQueueManager` / `RetryHistoryManager`がインメモリのままである以上、プロセス常駐化は別途独立した検討が必要 |
| `src/runtime/`・`src/application/`等の汎用Compositionレイヤ新設 | 2つ目の消費者が存在しない段階での先回り抽象化（YAGNI）。既存16パッケージの命名規則（ドメインスコープ）とも不整合 |

---

## 3. Architecture Review（Final）

**結論：Approve**

| 観点 | 判定 |
|---|---|
| Foundation First | ✅ 実行・ループ・デーモン化はいずれも対象外のまま。組み立てのみ |
| Small Release | ✅ 新規ファイルは2つのみ（`__init__.py` / `retry_composition_root.py`）。既存の`from_env()`/`from_config()`への委譲のみで新規business logicはゼロ |
| Stateless | △→許容：`RetryCompositionRoot`自体は状態（Manager参照）を保持するが、新しい判定・decision logicは持たない。Composition Rootの性質上不可避（`WorkflowEngineManager`も同様にAgentインスタンスを保持する既存パターン） |
| Single Responsibility | ✅ 「Queue/Historyインスタンスを共有した状態でRetry関連コンポーネントを1つに束ねる」という単一責務 |
| Backward Compatibility | ✅ 既存8パッケージ（`workflow_monitor` / `retry_queue` / `retry_history` / `retry_enqueue_trigger` / `retry_engine` / `workflow_engine` / `ai` / `execution_history`）はいずれも無改修 |
| Composition | ✅ `retry_composition`という新しい最上位層に依存を閉じ込め、既存パッケージ間の依存方向（`retry_enqueue_trigger`が`retry_engine`を経由しない等）は崩さない |
| 検証可能性 | ✅ E2Eテストで「`trigger`側と`manager`側が同一のQueue/Historyインスタンスを参照していること」を`is`比較で直接検証できる（本Releaseの中心的な検証観点） |

---

## 4. Compatibility

* 新規パッケージ`src/retry_composition/`の追加のみ。既存パッケージへの変更は一切ない
  （ゼロ改修）
* `RetryCompositionRoot`を呼び出す既存コード（`scripts/`含む）は存在しない
  （消費者不在の先行実装。v3.1.0 Retry Queue・v3.5.0 Retry Scheduler Decisionと同型の
  Foundation First）

---

## 5. Known Issue（本Releaseでも未解消）

* **本Release単体では何も実行されない**。`RetryCompositionRoot.from_env()`を呼び出して
  終わりであり、ユーザーから見て動く機能が増えるわけではない。価値は「次Release以降の
  実行系が正しい前提（Queue/Historyインスタンスの共有）の上に積み上がる土台ができる
  こと」に限定される
* `RetryQueueManager` / `RetryHistoryManager`の永続化は引き続き対象外。本Releaseは
  「同一プロセス内でのインスタンス共有」を解決するものであり、プロセスをまたいだ
  永続化の問題（タスクスケジューラ等でプロセスが再起動される運用）はこのままでは
  未解決である。次Release以降で「1サイクル実行」を同一プロセス内に閉じる形で実装するか、
  永続化を導入するかの判断が必要

---

## 6. Future Architecture Consideration

* **次Release候補**：`RetryCompositionRoot.from_env()`を呼び出し、`trigger.
  enqueue_pending_failures(max_attempts=root.policy.max_attempts)` →
  `manager.execute_dispatchable_retries(...)` 等を1サイクル分実行する
  `scripts/run_retry_composition.py`（一時的な単発実行、ループ・デーモン化は含まない）
* ループ・デーモン化・タスクスケジューラ連携の要否は、上記「1サイクル実行」が
  実運用でどう使われるかを踏まえて改めて判断する

---

## 7. Status

- [x] Architecture Review 完了（Final、ユーザー承認済み）
- [x] Implementation
- [x] Unit / E2E Test（`tests/test_e2e_v5_1_0_retry_composition_root_foundation.py`、38件）
- [x] Regression確認
- [x] Documentation更新
