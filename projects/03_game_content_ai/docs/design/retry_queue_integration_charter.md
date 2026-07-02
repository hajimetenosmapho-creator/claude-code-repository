# Project Charter — Release 3.2「Retry Queue Integration」

作成日：2026-07-02
状態：承認済み（Architecture Review完了・**Approve with Minor Recommendations**、2026-07-02）
対象：RetryManager（v3.0.0）がRetryQueueManager（v3.1.0）を利用し、再実行対象をQueueへ
登録・取得できるようにする最小統合。自動実行・Scheduler連携・永続化は行わない。

---

## 1. Background

* Retry Engine Foundation（v3.0.0）：`RetryManager.retry(run_id)` が1件の`run_id`に対して
  「今すぐ再実行してよいか」を判定し、よければ即座に`WorkflowEngineManager.run()`を呼び出す、
  **同期・単発**の仕組み。複数`run_id`の一覧管理・優先度付け・「後で実行」という概念を
  持たない（`docs/design/retry_engine_foundation.md` 11章 Future Extensions「Retry Queue /
  Priority Queue」として対象外に明記済み）。
* Retry Queue Foundation（v3.1.0）：`enqueue` / `dequeue` / `remove` / `list` / `exists` /
  `count`の6操作のみを提供するQueue管理層（`src/retry_queue/`）。`workflow_engine` /
  `workflow_monitor` / `execution_history` / `retry_engine`のいずれもimportしない、
  **独立した葉パッケージ**として先行リリースされた（`docs/design/retry_queue_foundation.md`
  1章）。リリース時点でどのパッケージからも呼ばれておらず、実配線は明示的にOut of Scope
  とされていた（同設計書1章・11章「Retry Engineとの実配線」）。
* 結果として、「Queueに登録する」「Queueから取り出す」という操作自体はv3.1.0時点で
  すでに`RetryQueueManager`のAPIとして存在するが、Retry Engine側（`RetryManager`）から
  それを呼び出す経路が存在しない。本Release（v3.2.0）は、この「存在するが繋がっていない」
  というギャップだけを埋める。

```
Retry Engine（再実行判断・依頼、v3.0.0、無改修予定 → 本Releaseで軽微に変更）
   │
   └── Retry Queue（Queue管理、v3.1.0、無改修） ★本Releaseは「配線」のみ追加
```

---

## 2. Purpose

`RetryManager`が`RetryQueueManager`を保持し、「再実行対象をQueueへ登録する」「Queueから
再実行対象を取り出す」という2つの操作を、それぞれの既存パッケージの公開APIへの**薄い委譲**
として提供する。これにより、将来のScheduler連携・自動Retry実装が「Queueへの出し入れ」と
「Retry可否判定・実行」を同じ起動口（`RetryManager`）から扱えるようになる土台を作る。

ただし本Releaseは Foundation の延長であり、**統合の配線だけ**を行う。Queueから取り出した
項目を自動的に`retry()`する、Schedulerの周期実行に乗せる、といった自動化は次のRelease以降に
送る。

---

## 3. Goals

本Releaseで確立する Retry Queue Integration は、次のことだけを行う。

1. `RetryManager`が`RetryQueueManager`（または`NullRetryQueueManager`）をDependency
   Injectionで保持できるようにする
2. `RetryManager`に、再実行対象を Queue へ登録するメソッドを追加する（内部では
   `RetryQueueManager.enqueue()`を呼ぶだけの薄い委譲）
3. `RetryManager`に、Queue から再実行対象を取り出すメソッドを追加する（内部では
   `RetryQueueManager.dequeue()`を呼ぶだけの薄い委譲）
4. 上記2メソッドの追加によっても、既存の`RetryManager.retry()` / `RetryManager.from_config()`
   の呼び出し方・戻り値の意味を一切変更しない（後方互換性の維持）

---

## 4. Scope

### 実装対象

`src/retry_engine/retry_manager.py`の変更（`RetryManager` / `NullRetryManager`のみ）。

* `RetryManager.__init__`に、Queue操作を委譲する先（`RetryQueueManager | NullRetryQueueManager`）
  を保持する引数を追加する
* `RetryManager.from_config()`に、構築済みの`RetryQueueManager | NullRetryQueueManager`を
  受け取る引数を追加する。**省略可能とし、省略時は`NullRetryQueueManager()`を用いる**ことで、
  既存の呼び出し（Queueを渡さない呼び出し）が変更なく動作し続けるようにする
* 新規メソッド：Queueへ再実行対象を登録する（`RetryQueueManager.enqueue()`と同じ入力・
  戻り値`RetryQueueResult`をそのまま中継する）
* 新規メソッド：Queueから再実行対象を取り出す（`RetryQueueManager.dequeue()`の戻り値
  `RetryQueueResult`をそのまま中継する）
* `NullRetryManager`にも同名2メソッドを追加し、常に`outcome=DISABLED`相当を返す
  （既存の`retry()`と同じDuck Typingの一貫性を保つ）
* 単体テスト・E2Eテスト（`tests/test_e2e_v3_2_0_retry_queue_integration.py`）
* 関連ドキュメント更新（CHANGELOG / ROADMAP / architecture.md）

### 対象外

* `RetryQueueManager` / `NullRetryQueueManager`（`src/retry_queue/`配下の全ファイル）の
  改修（ゼロ改修を維持する）
* `RetryManager.retry()`・`RetryPolicy`・`RetryExecutor`・`RetryConfig`・`RetryRequest`・
  `RetryResult`の変更（追加する2メソッドとDIパラメータ以外は無改修）
* Queueから取り出した項目を自動的に`retry()`する仕組み（自動実行）
* Scheduler連携（定期的にdequeueして処理する自動運用）
* Queueの永続化
* 優先度付けアルゴリズムの高度化
* `RetryQueueItem.retry_attempt`とRetry Historyの連携
* CLIエントリスクリプト（`scripts/run_retry_queue.py`等）
* Workflow Engine / Workflow Monitor / Execution History / Scheduler本体の改修

---

## 5. Design Principles

* **Foundation First**：Queueへの登録・取得という最小の配線のみを行う。自動実行・優先度戦略・
  永続化はすべて後続Releaseへ送る
* **Single Responsibility**：Queue管理のロジック（容量チェック・重複チェック・優先度ソート）は
  `retry_queue`側に残したまま、`retry_engine`側には一切複製しない。`RetryManager`の新規
  メソッドは`RetryQueueManager`への**委譲のみ**であり、判定・加工を行わない
* **Stateless**：`RetryManager`はQueueの中身を独自に保持・キャッシュしない。Queueの状態の
  Single Source of Truthは引き続き`RetryQueueManager`（の内部`_items`）であり、`RetryManager`
  は呼ばれるたびにそこへ委譲するだけである
* **Read Before Action**：Queueからの取り出しは常に`RetryQueueManager.dequeue()`への
  その場の呼び出しであり、事前に取得した内容を使い回さない
* **Single Source of Truth**：「どのrun_idが再実行待ちか」は`retry_queue`が唯一の情報源で
  あり続ける。「run_idの今の実行状態」は引き続き`workflow_monitor`が唯一の情報源である
  （`retry_engine`はいずれも複製しない）
* **既存モジュールの責務変更や依存関係の逆転を避ける**：`workflow_engine` /
  `workflow_monitor` / `execution_history` / `retry_queue`はいずれも無改修とする。
  依存方向は`retry_engine → retry_queue`の一方向のみとし、`retry_queue`が`retry_engine`を
  参照することはない
* **後方互換性を維持する**：`RetryManager.retry()`・`RetryManager.from_config()`の既存の
  呼び出し（Queueを渡さない場合）は本Release前とまったく同じ結果になる

---

## 6. Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryQueueManager`（v3.1.0、無改修） | Queueへの出し入れ（登録・取り出し・削除・一覧・存在確認・件数）そのもの | 再実行の可否判定・実行 |
| `RetryManager`（本Releaseで変更） | Feature Gate判定・Workflow Monitorからの状態取得・Retry Policyの適用・Retry Executorへの委譲（既存）に加え、`RetryQueueManager`への参照を保持し、登録・取り出しの呼び出しをそのまま中継する | Queue内部の判定ロジック（容量・重複・優先度ソート）の実装・Queueから取り出した項目の自動再実行 |
| `RetryExecutor`（無改修） | `WorkflowEngineManager`の公開APIを呼び出すだけの薄いコンポーネント | Queueとの連携 |

「Queueに何を入れるか・いつ取り出すか」の判定ロジックはこれまでどおり`retry_queue`側に
閉じたままとし、`retry_engine`は呼び出し口を提供するだけに徹する。これにより
「Queue管理とRetry実行の責務を分離する」という要件を、委譲のみで判定ロジックを持たない
構造で満たす。

---

## 7. Dependencies

```
retry_engine ──→ retry_queue（公開APIのみ：RetryQueueManager / NullRetryQueueManager /
                  RetryQueueResult / RetryQueueOutcome）
      │
      ├──→ workflow_engine（公開APIのみ、既存・無改修）
      └──→ workflow_monitor（公開APIのみ、既存・無改修）

retry_queue  ──→ （なし。標準ライブラリのみ、無改修）
```

* `retry_queue`は本Releaseでも他パッケージを一切importしない（無改修のまま、独立した
  葉パッケージであり続ける）
* `retry_engine`は`retry_queue`の公開シンボル（`__init__.py`でexportされたもの）のみを
  importし、内部モジュール（例：`retry_queue._internal`のような非公開実装）には依存しない
* 循環importは発生しない（`retry_queue`が`retry_engine`を参照する経路は存在しない）

---

## 8. Non-Goals

* Queueから取り出した項目を`RetryManager`が自ら`retry()`にかけること（自動実行）
* Schedulerの周期実行に乗せてQueueを処理する自動運用
* Queueの永続化（プロセス再起動をまたぐ保持）
* 優先度付けアルゴリズムの高度化（現状の`priority: int`昇順のままとする）
* `retry_queue`パッケージ自体の変更（ゼロ改修を維持）
* `RetryManager.retry()` / `RetryPolicy` / `RetryExecutor`の判定・実行ロジックの変更

---

## 9. Acceptance Criteria

* `RetryManager`が新規メソッドを通じて`RetryQueueManager.enqueue()` /
  `RetryQueueManager.dequeue()`をそれぞれ1回だけ呼び出し、戻り値の`RetryQueueResult`を
  そのまま返すこと（加工しないことの確認）
* `RetryManager.from_config()`で`RetryQueueManager`（または`NullRetryQueueManager`）を
  省略した場合、内部で`NullRetryQueueManager()`が使われ、登録・取り出しメソッドが
  常に`outcome=DISABLED`を返すこと
* 既存の`RetryManager.retry(run_id)` / `RetryManager.from_config(retry_config, retry_policy,
  workflow_engine_manager, workflow_monitor_manager)`（Queue引数なし）の呼び出しが、
  本Release前とまったく同じ結果を返すこと（回帰テストで確認）
* `NullRetryManager`の新規2メソッドが、`WorkflowMonitorManager` / `WorkflowEngineManager` /
  `RetryQueueManager`のいずれのメソッドも呼び出さずに`outcome=DISABLED`を返すこと
* `RetryManager`の新規メソッドが、Queueから取り出した項目に対して`self.retry()`や
  `self._executor`を一切呼び出さないこと（自動実行が混入していないことの構造的確認）
* `src/retry_queue/`配下の全ファイルに差分がないこと（`git diff`で確認、ゼロ改修）
* `src/workflow_engine/` / `src/workflow_monitor/` / `src/execution_history/`配下に
  差分がないこと
* E2Eテスト全PASS・既存回帰（`v2.0.0`〜`v3.1.0`）全PASS

---

## 10. Directory Structure（想定）

```text
src/retry_engine/
├── __init__.py           # 変更なし想定（新規公開シンボルは追加しない。RetryQueueManager等は
│                          #   呼び出し元がretry_queueから直接importして渡す想定）
├── retry_policy.py       # 無改修
├── retry_config.py       # 無改修
├── retry_request.py      # 無改修
├── retry_result.py       # 無改修
├── retry_executor.py     # 無改修
└── retry_manager.py      # 変更（RetryQueueManagerとの統合）

src/retry_queue/           # 全ファイル無改修

tests/
└── test_e2e_v3_2_0_retry_queue_integration.py   # 新規
```

---

## 11. Risks and Mitigations

| リスク | 対策 |
|---|---|
| `from_config()`への引数追加が既存呼び出し元を壊す | 新規引数はデフォルト値付き・省略可能とし、省略時は`NullRetryQueueManager()`にフォールバックする。既存呼び出し（`tests/test_e2e_v3_0_0_retry_engine_foundation.py`等）がQueue引数なしのまま動作することを回帰テストで確認する |
| Queueからの取り出しメソッドの中に、うっかり自動再実行（`self.retry()`呼び出し）が混入する | Architecture Guard（静的検査・単体テスト）で、新規メソッドがFakeの`RetryExecutor` / `WorkflowMonitorManager`を一切呼ばないことを確認する（9章） |
| `retry_engine`が`retry_queue`の非公開実装（内部モジュール）に依存してしまい、将来`retry_queue`側の内部変更で壊れる | `retry_queue`の`__init__.py`が公開する`__all__`のシンボルのみをimportする。Architecture Guardでimport経路を静的検査する |
| Queue無効（`RETRY_QUEUE_ENABLED=false`）とRetry Engine無効（`RETRY_ENGINE_ENABLED=false`）の組み合わせにより、呼び出し元がどちらが原因か判別しづらくなる | 既存の`RetryQueueResult.reason` / `NullRetryManager`の`reason`文字列をそのまま伝播させ、原因の切り分けはメッセージ内容で追えるようにする（新しいreason種別は追加しない） |

---

## 12. Status

- [x] Project Charter ドラフト作成（本ドキュメント）
- [x] Architecture Design（`docs/design/retry_queue_integration.md`）
- [x] Architecture Review（Approve with Minor Recommendations、指摘事項3点を反映済み）
- [x] 実装（`src/retry_engine/retry_manager.py`変更のみ、`src/retry_queue/`無改修）
- [x] Test（新規102件全PASS。既存回帰は`v3.1.0`の1件を除き全PASS。詳細は`docs/CHANGELOG.md` [KI-3]）
- [x] Documentation（`docs/CHANGELOG.md` / `docs/ROADMAP.md` / `docs/architecture.md`更新済み）
- [ ] commit（ユーザー確認後）
- [ ] push（ユーザー確認後）
