# Project Charter — Release 4.2「Retry Queue Removal Foundation」

作成日：2026-07-06
状態：ドラフト（ユーザー確認待ち）
対象：v4.1.0で`RetryManager.decide_retry_queue_updates()`が返すようになった
`RetryQueueUpdateDecision`（`COMPLETE` / `FAIL` / `NOOP`）を入力に、
`RetryQueueManager.remove()`を初めて呼び出し可能にする。`COMPLETE` / `FAIL`
のみをQueue反映（除去）対象とし、`NOOP`（`SKIPPED` / `NOT_FOUND` /
`DISABLED`に由来）はいずれもremove対象外のままとする。Queue永続化・
Retry Policy・Retry Metrics・Queue最適化・Scheduler改修はいずれも対象外。

> **本Releaseの位置づけについての注記**：`docs/ROADMAP.md`「v3.x 以降の候補」
> 569行目に記載済みの「**Retry Queue Removal**：`RetryQueueUpdateDecider`
> （v4.1.0）が判定した`RetryQueueUpdateDecision`を使って、実際に
> `RetryQueueManager.remove()`を呼び出し、Queueから該当項目を除去する仕組み」
> に相当する項目に着手する。同項目には「あわせて、`NOOP`と判定された項目
> （特に`SKIPPED`＝`max_attempts`到達）が本Foundationでは除去する手段を
> 持たず恒久的にQueueへ滞留し得るリスクへの対応（除去する／Dead Letter
> Queueへ回す等）を、本項目の最初の検討事項として扱う」とも記載されているが、
> ユーザー指示により本Releaseはこの検討事項（`SKIPPED`の滞留対応）には
> 踏み込まず、`COMPLETE` / `FAIL`のQueue反映のみに意図的にスコープを絞る。
> `SKIPPED`（`max_attempts`到達）は本Releaseでもremove()を持たずQueueに
> 滞留し続ける仕様のまま据え置き、対応要否の判断は次Release以降に委ねる。

---

## 1. Background

* Retry Queue Update Foundation（v4.1.0）：`RetryManager.decide_retry_queue_updates()`
  経由で、`RetryExecutionResult`のリストから`RetryQueueUpdateDecision`
  （`execution_result` / `outcome` / `target_status` / `reason`）のリストを
  判定できるようになった。`outcome`は`COMPLETE`（再実行成功）・`FAIL`
  （再実行失敗）・`NOOP`（`SKIPPED` / `NOT_FOUND` / `DISABLED`いずれかに
  由来し、再実行が実行されていない）の3値。
* `RetryQueueUpdateDecider`（v4.1.0）は`RetryQueueManager` /
  `NullRetryQueueManager`への参照を一切持たず、判定結果を実際にQueueへ
  反映する処理（`remove()`呼び出し・内部ストアの書き換え）は
  `retry_engine`パッケージのどこにも存在しない。
* `RetryQueueManager.remove(run_id)`（v3.1.0、`retry_queue_manager.py`）は
  既に実装済みで、`run_id`をQueueから取り消し（`status=CANCELLED`に更新後
  内部ストアから削除）、`RetryQueueResult`（`outcome`：`REMOVED` /
  `NOT_FOUND`）を返す。`NullRetryQueueManager.remove()`は常に`DISABLED`を
  返す。v3.1.0〜v4.1.0のいずれのリリースでも、この`remove()`は
  構造的に（AST・Spyで）呼び出されないことが確認され続けてきた。本Releaseで
  初めてこの制約を解除する。
* `RetryQueueUpdateDecision.execution_result`（`RetryExecutionResult`、
  v4.0.0）は分解されずに保持されており、
  `execution_result.dispatch_event.candidate_event.run_id`
  （`RetryCandidateEvent.run_id`、v3.8.0で定義済みのフィールド）経由で、
  追加の突き合わせなしに対象の`run_id`へ到達できる（v4.1.0 Architecture
  Review 16.1節 観点2で確認済み）。

```
Retry Engine（受信・整理・実行・判定、v3.0.0〜v4.1.0）
   │
   ├── execute_dispatchable_retries()（v4.0.0、無改修）
   │      → RetryExecutionResult のリスト
   ├── decide_retry_queue_updates()（v4.1.0、無改修）
   │      → RetryQueueUpdateDecision のリスト（COMPLETE/FAIL/NOOP）
   │
   └──────── ★本Releaseで新設 ────────
        「RetryQueueUpdateDecision を入力に、COMPLETE/FAILのものだけ
         RetryQueueManager.remove(run_id) を呼び出し、Queueから
         該当項目を除去できる Foundation」
        （NOOPはremove対象外。Queue永続化・Retry Policy・Retry Metrics・
         Queue最適化・Scheduler改修は行わない）
```

---

## 2. Purpose

`RetryQueueUpdateDecision`（v4.1.0）のリストを受け取り、`outcome`が
`COMPLETE`または`FAIL`の項目についてのみ`RetryQueueManager.remove(run_id)`
を呼び出し、Queueから該当項目を除去できる新規コンポーネントを追加する。
`outcome`が`NOOP`の項目（`SKIPPED` / `NOT_FOUND` / `DISABLED`いずれかに
由来）は、remove呼び出しの対象から構造的に除外する。

Queue永続化・Retry Policy（選別基準拡張）・Retry Metrics・Queue最適化
（heapq化等）・Scheduler改修はいずれも本Releaseの対象外とする。

---

## 3. Goals

本Releaseで確立する Retry Queue Removal Foundation は、次のことだけを行う。

1. 新規コンポーネントを追加し、`list[RetryQueueUpdateDecision]`を受け取り、
   `outcome == COMPLETE`または`outcome == FAIL`の項目についてのみ
   `RetryQueueManager.remove(run_id)`（実際には`RetryManager`が保持する
   `self._queue.remove`を関数として受け取る）を呼び出し、結果を集約した
   リストを返す（具体的なクラス名・戻り値の型は次工程Architecture Designで
   確定する）
2. `outcome == NOOP`の項目はremove呼び出しを一切行わず、スキップした
   ことが結果から判別できるようにする
3. `run_id`の取得は`decision.execution_result.dispatch_event.candidate_event.run_id`
   経由とし、追加の突き合わせ・Queueへの問い合わせ（`list()`等）を挟まない
4. 新規コンポーネントはStatelessとし、`RetryQueueManager`への直接参照
   （コンストラクタ引数としての保持）を持たない。remove操作は呼び出し時に
   関数として受け取る（v4.0.0`RetryExecutionCoordinator`の`retry_fn`と
   同じパターン）
5. `RetryManager`（既存の起動口）から、この新規コンポーネントへ薄い委譲
   メソッドで到達できるようにする（`decide_retry_queue_updates()`
   （v4.1.0、無改修）への委譲＋新規コンポーネントへの委譲、の合成のみ）
6. 既存の`RetryManager()` / `RetryManager.from_config()`呼び出し・
   `NullRetryManager`の動作は本Release後も無変更で動作すること
   （後方互換性維持）
7. `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
   `retry_queue`・既存の`retry_execution_selector.py` /
   `retry_execution_coordinator.py` / `retry_queue_update_decider.py`は
   いずれも本Releaseでも無改修（ゼロ改修）を維持する

---

## 4. Scope

### 対象

* `RetryQueueUpdateDecision`を受け取り、`COMPLETE` / `FAIL`の項目のみ
  `RetryQueueManager.remove(run_id)`を呼び出す新規コンポーネントの追加
* `RetryManager`への、その新規コンポーネントを利用する薄い委譲メソッドの追加
* `NullRetryManager`への同名メソッドの追加（無効時は安全側の挙動）
* Queue項目除去（`remove()`呼び出し）の呼び出し基盤
* `RetryQueueUpdateDecision`との接続（`execution_result`経由の`run_id`取得）
* 単体テスト・E2Eテスト
  （`tests/test_e2e_v4_2_0_retry_queue_removal_foundation.py`）
* 関連ドキュメント更新（CHANGELOG / ROADMAP / architecture.md）

### 対象外（今回やらないこと）

* `SKIPPED`（`max_attempts`到達）のQueue滞留対応（除去する／Dead Letter
  Queueへ回す等）。`NOOP`（`SKIPPED` / `NOT_FOUND` / `DISABLED`いずれも
  含む）はremove対象外のまま据え置く
* Queue永続化（SQLite/Redis等）
* Retry Policy（`RetryExecutionSelector`が行う`dispatchable=True`の選別
  基準の拡張。優先度・件数上限に基づく選別は対象外）
* Retry Metrics / Monitoring（成功率・試行回数分布・Queue滞留時間等の集計）
* Queue最適化（heapqベースのPriority Queue化等）
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source`
  パッケージ自体の改修（Scheduler改修は対象外）
* `RetryQueueManager` / `RetryQueueStatus` / `RetryQueueResult`
  （`retry_queue`パッケージ）自体の改修（ゼロ改修を維持）
* 既存の`retry_execution_selector.py` / `retry_execution_coordinator.py` /
  `retry_queue_update_decider.py`（v4.0.0・v4.1.0）の変更
* `RetryQueueManager.dequeue()`の本格実装（Queueから実際に取り出して回す
  自動化。既存の薄い委譲メソッド`RetryManager.dequeue_retry()`（v3.2.0）
  は無改修のまま維持する）
* 実運用のComposition Root（Scheduler → Retry Engine → Retry Queueを実際に
  つなぎ、除去処理を継続的に回すスクリプト）
* 新しいFeature Gate環境変数の追加・Configクラスの追加・Managerパターン
  （`from_config()` / `from_env()`等の新規起動口）の採用

---

## 5. Design Principles

* **Foundation First**：`RetryQueueUpdateDecision`を入力に`COMPLETE` /
  `FAIL`のみremoveを呼び出せるところまでを行う。`NOOP`（特に`SKIPPED`の
  滞留問題）への対応は後続Releaseへ送る
* **Single Responsibility**：新規コンポーネントは「`RetryQueueUpdateDecision`
  のリストから、`COMPLETE` / `FAIL`の項目についてremove操作を呼び出し、
  結果を集約する」ことのみを担う。判定ロジック（`RetryQueueUpdateDecider`）・
  実行ロジック（`RetryExecutionCoordinator`）・Queue管理そのもの
  （`RetryQueueManager`）のいずれも複製・肩代わりしない
* **Stateless**：新規コンポーネントは`RetryQueueManager`への参照を
  コンストラクタで保持しない。remove操作は呼び出しごとに関数として
  受け取る（v4.0.0`RetryExecutionCoordinator`の`retry_fn`と同じパターン）
* **Backward Compatibility**：`RetryManager()` / `RetryManager.from_config(...)`の
  既存呼び出し（新規引数を渡さない場合）は、本Release後も無変更で動作する。
  `NullRetryManager`にも同名の委譲メソッドを追加し、無効時は安全側
  （空リスト等）を返す
* **RetryManagerの責務を肥大化させない**：新規委譲メソッドは
  `decide_retry_queue_updates()`（v4.1.0、無変更）への委譲＋新規
  コンポーネントへの委譲、という薄い合成のみで完結させる

---

## 6. Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryQueueUpdateDecider`（v4.1.0、無改修） | `RetryExecutionResult`を対象に、更新先の`RetryQueueUpdateDecision`（`COMPLETE` / `FAIL` / `NOOP`）を判定する | Queueへの実際の反映（`remove()`等） |
| 新規コンポーネント（本Releaseで追加） | `RetryQueueUpdateDecision`を対象に、`COMPLETE` / `FAIL`の項目についてのみremove操作を呼び出し、結果を集約する | 判定ロジックの再実装・`NOOP`の内訳判断・Queueの内部ストア構造への直接アクセス・永続化 |
| `RetryManager`（本Releaseで変更） | 新規コンポーネントへの薄い委譲窓口を持つ | 判定ロジック・除去ロジックの再実装 |
| `RetryQueueManager`（v3.1.0、無改修） | `remove()`の実処理（Queueからの取り消し・内部ストア更新） | Queue項目の更新先判定・除去対象の選別 |

---

## 7. Dependencies

```
retry_engine  ──→ retry_queue（v3.2.0のまま。remove操作は関数として
                   受け取るため、新規コンポーネントが RetryQueueManager
                   型を直接importする必要はない想定。8章 Open Questionで確定）
retry_engine  ──→ scheduler（SchedulerEvent型の参照のみ、v3.8.0で確立済み、無改修）
retry_engine  ──→ workflow_engine（v3.0.0のまま、無改修）
retry_engine  ──→ workflow_monitor（v3.0.0のまま、無改修）
```

* 本Releaseは新規の依存**方向**を追加しない想定である。`RetryManager`は
  既に`retry_queue`パッケージへ依存しているため（v3.2.0）、新規コンポーネント
  自体は`remove_fn: Callable[[str], RetryQueueResult]`という関数型のみを
  扱い、`RetryQueueManager`型への直接依存を持たない設計にできるかを
  Architecture Designで確定する
* `retry_queue`パッケージ側（`retry_queue → retry_engine`という逆方向）は
  一切追加しない
* 循環importは発生しない

---

## 8. Open Questions（Architecture Designで確定する事項）

1. **新規コンポーネントの名称・配置場所**：`retry_engine`パッケージ内の
   新規ファイルとする（v3.8.0〜v4.1.0の既存成長パターンを踏襲する想定）。
   具体的なクラス名を確定する
2. **remove操作の受け取り方**：`RetryQueueManager`型を直接コンストラクタ
   またはメソッド引数で受け取るか、`remove_fn: Callable[[str],
   RetryQueueResult]`という関数型で受け取るか（v4.0.0
   `RetryExecutionCoordinator`の`retry_fn`パターンとの整合性）
3. **戻り値の型**：除去結果をどのようなデータ構造で返すか（`decision` /
   `queue_result`（remove呼び出し結果、`None`は未実施） /
   `reason`を持つ新規`frozen`データクラスを想定）
4. **`run_id`の取得経路**：`decision.execution_result.dispatch_event.
   candidate_event.run_id`を正式な取得経路として確定する
5. **`RetryManager`への委譲メソッドの名称・粒度**：
   `decide_retry_queue_updates()`と対になる1メソッドとする
   （名称は例えば`apply_retry_queue_removals()`）
6. **新規コンポーネントの構築責務**：`RetryManager.__init__`が新規
   コンポーネントをデフォルトで自動生成するか（v3.8.0〜v4.1.0と同じ
   「省略時は自動フォールバック」）
7. **`NullRetryManager`側の扱い**：同名の委譲メソッドを追加するか。
   追加する場合、無効時に何を返すか（空リストが妥当と想定される）
8. **`NOOP`項目の扱いの明示方法**：remove対象外であることを、結果リストに
   含めて明示するか（例：`attempted=False`のエントリとして含める）、
   結果リストから除外するか

---

## 9. Acceptance Criteria

* `RetryQueueUpdateDecision.outcome == COMPLETE`の項目について、対応する
  `run_id`で`RetryQueueManager.remove()`が呼び出され、`RetryQueueResult`
  （`outcome`：`REMOVED`または`NOT_FOUND`）が結果に反映されること
* `RetryQueueUpdateDecision.outcome == FAIL`の項目についても同様に
  `remove()`が呼び出されること
* `RetryQueueUpdateDecision.outcome == NOOP`の項目（`SKIPPED` /
  `NOT_FOUND` / `DISABLED`いずれに由来する場合も）については、
  `RetryQueueManager.remove()`が一切呼び出されないこと（Spyオブジェクトに
  よる構造的確認）
* `SKIPPED`（`max_attempts`到達）由来の`NOOP`が、本Release後もQueueに
  滞留し続ける（除去されない）ことを回帰的に確認すること
* 新規コンポーネント・`RetryManager`の委譲メソッドのいずれも、
  `RetryQueueManager.dequeue()`・`enqueue()`へは到達しないこと
* 既存の`RetryManager()` / `RetryManager.from_config(...)`（新規引数を
  渡さない場合）が、本Release後も無変更で動作すること（後方互換性の回帰確認）
* `NullRetryManager`が本Release後も既存の全メソッド（本Releaseで追加する
  委譲メソッドを含む）で一貫してDISABLED相当・空リストの安全な挙動を返すこと
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
  `retry_queue`・`retry_execution_selector.py` / `retry_execution_coordinator.py` /
  `retry_queue_update_decider.py`配下の全ファイルに差分がないこと
  （`git diff`で確認、ゼロ改修）
* E2Eテスト全PASS・既存回帰（`v2.0.0`〜`v4.1.0`）全PASS

---

## 10. Non-Goals

* `SKIPPED`（`max_attempts`到達）のQueue滞留対応（除去・Dead Letter Queue化）
* Queue永続化（SQLite/Redis等）
* Retry Policy（選別基準の拡張）
* Retry Metrics / Monitoring
* Queue最適化（heapqベースのPriority Queue化等）
* Scheduler改修（`scheduler` / `retry_scheduler_decision` /
  `retry_scheduler_source`パッケージ自体の変更）
* `retry_queue`パッケージ自体の変更（ゼロ改修を維持）
* 既存の`retry_execution_selector.py` / `retry_execution_coordinator.py` /
  `retry_queue_update_decider.py`の変更
* `RetryQueueManager.dequeue()`の本格実装
* 実運用のComposition Root
* 新しいFeature Gate環境変数の追加・Configクラスの追加・Managerパターンの採用

---

## 11. Risks and Mitigations

| リスク | 対策 |
|---|---|
| `NOOP`（`SKIPPED`）がremove対象外のまま滞留し続けることが、本Releaseの「不完全さ」と誤解される可能性がある | Purpose・Non-Goalsで「`COMPLETE` / `FAIL`のみを対象とする」ことを明記し、ROADMAP.mdの記載と合わせて次Release以降の検討事項であることを明示する |
| 新規コンポーネントが`RetryQueueManager`への直接参照を持つ設計にした場合、v4.0.0までの「Queue非依存」の原則との整合性が問われる | Architecture Designで`remove_fn`を関数として受け取る設計（v4.0.0`RetryExecutionCoordinator`と同じパターン）を採用し、型依存を最小化する（8章 Open Question 2） |
| `remove()`呼び出しが`RetryQueueUpdateDecision`から取得した`run_id`に対応するQueue項目が既に存在しない場合（`NOT_FOUND`）の扱いが曖昧になるリスク | `RetryQueueResult.outcome == NOT_FOUND`はエラーではなく正常な結果として扱い、例外を発生させない（`RetryQueueManager.remove()`の既存挙動をそのまま活用する） |
| 本Releaseで初めて`remove()`が解禁されることで、既存のv3.1.0〜v4.1.0の「remove()は呼び出されない」という回帰テスト前提が崩れる | 既存回帰テストのうち「remove()が呼び出されないこと」を確認していたテストは、本Releaseの新規委譲メソッドを呼び出さない限り従来通りPASSすることを確認する（新規メソッドを呼ばない既存経路には影響がないことを明示） |

---

## 12. Status

- [x] Project Charter ドラフト作成（本文書、Claude Code作成）
- [x] ユーザー確認・フィードバック反映（承認済み）
- [x] Project Charter 確定
- [x] Architecture Design（`docs/design/retry_queue_removal_foundation.md`）
