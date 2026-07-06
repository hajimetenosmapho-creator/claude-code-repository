# Project Charter — Release 4.1「Retry Queue Update Foundation」

作成日：2026-07-06
状態：ドラフト（ユーザー確認待ち）
対象：v4.0.0で`RetryManager.execute_dispatchable_retries()`が返すようになった
`RetryExecutionResult`のリストを入力に、対応するRetry Queue項目が
どの状態（`RetryQueueStatus.COMPLETED` / `FAILED`）へ更新されるべきかを
判定できる基盤を構築する。`RetryQueueManager.remove()` / `dequeue()`の
呼び出し・Queue永続化・Retry Policy・Retry Metricsはいずれも対象外とする。

> **本Releaseの位置づけについての注記**：`docs/ROADMAP.md`「v3.x 以降の候補」に
> 記載済みの「**Retry Queue Update**：Retry実行の結果（成功・失敗）を
> Retry Queueへフィードバックする仕組み（`RetryQueueStatus.COMPLETED` /
> `FAILED`への到達。v3.1.0で予約値として定義済みだが、判定ロジックからは
> 到達しない）」に相当する項目に着手する。ただし、ROADMAP.mdの当該項目は
> 将来的な完成形（実際にQueueへ反映し、`remove()`等でQueueから除去する
> ところまで）を指しており、それを一度に実現するのではなく、ユーザー指示に
> 基づき本Releaseでは意図的にスコープを絞る。すなわち「`RetryExecutionResult`
> を受け取り、対応するQueue項目がどの状態へ更新されるべきかを判定できる
> Foundation」までに限定し、`RetryQueueManager.remove()`の呼び出し・
> `dequeue()`の本格実装（Queueから実際に取り出して回す自動化）・
> Queue永続化には進まない。これらは`docs/ROADMAP.md`に別項目として記載済みの
> **Retry Queue Removal** / **Retry Queue Persistence**（本Release後も
> 未着手のまま）に委ねる。Retry Policy・Retry Metricsも同様に別項目として
> 記載済みであり、本Releaseの対象外とする。

---

## 1. Background

* Retry Execution Foundation（v4.0.0）：`RetryManager.execute_dispatchable_retries()`
  経由で、`dispatchable=True`の`RetryDispatchEvent`を対象に`RetryManager.retry()`
  を呼び出し、結果を`RetryExecutionResult`（`dispatch_event` / `retry_result`）
  として集約できるようになった。`RetryExecutionResult`を使って何かをさらに
  実行する処理（Queueへのフィードバック等）は`retry_engine`側に一切存在しない。
* `RetryQueueStatus`（v3.1.0、`retry_queue_status.py`）には`COMPLETED` /
  `FAILED`が予約値として定義済みだが、docstringに明記の通り「実際の再実行結果
  （`RetryOutcome`）をQueueへフィードバックする仕組み（Retry Engineとの連携）
  が必要だが、本Releaseの対象外」とされたまま、v3.1.0〜v4.0.0のどの判定ロジック
  からも到達していない。
* `docs/ROADMAP.md`「v3.x 以降の候補」に、次の未着手項目として記載がある：
  「**Retry Queue Update**：Retry実行の結果（成功・失敗）をRetry Queueへ
  フィードバックする仕組み」。本Releaseはこの項目に着手するが、スコープを
  「`RetryExecutionResult`を入力に、対応するQueue項目の更新先状態を判定できる
  Foundationの構築」までに絞る（詳細は3章 Goals・上記の位置づけ注記）。

```
Retry Engine（受信・整理・実行、v3.0.0〜v4.0.0）
   │
   ├── dispatch_retry_events()（v3.9.0、無改修）
   │      → RetryDispatchEvent のリスト（candidate_event・dispatchable）
   ├── execute_dispatchable_retries()（v4.0.0、無改修）
   │      → RetryExecutionResult のリスト（dispatch_event・retry_result）
   │
   └──────── ★本Releaseで新設 ────────
        「RetryExecutionResult を入力に、対応するQueue項目が
         COMPLETED / FAILED のどちらへ更新されるべきかを判定できる Foundation」
        （RetryQueueManager.remove() / dequeue() の呼び出し・Queueへの
         実際の反映・永続化は行わない）
```

---

## 2. Purpose

`RetryExecutionResult`（v4.0.0）のリストを受け取り、各要素について対応する
Retry Queue項目が`RetryQueueStatus.COMPLETED`（再実行成功）または
`RetryQueueStatus.FAILED`（再実行失敗、あるいは実行対象外）のどちらへ
更新されるべきかを判定する新規コンポーネントを追加する。

ただし、判定結果を使って`RetryQueueManager.remove()`を呼び出す・
`dequeue()`を本格的に運用する（Queueから実際に取り出して回す自動化）・
判定結果をQueueへ永続化するといった処理は本Releaseの対象外とする。
あくまで「`RetryExecutionResult`を入力に、更新先状態を判定できるように
する」ところまでに留める。

---

## 3. Goals

本Releaseで確立する Retry Queue Update Foundation は、次のことだけを行う。

1. 新規コンポーネントを追加し、`list[RetryExecutionResult]`を受け取り、
   各要素について更新先の`RetryQueueStatus`（`COMPLETED` / `FAILED`）を
   判定した結果のリストを返す（具体的なクラス名・配置場所・戻り値の型は
   8章 Open Questionsで確定する）
2. 判定基準（`RetryResult.outcome`が`RETRIED`かつ
   `workflow_engine_result.overall_success`が真なら`COMPLETED`、それ以外
   （`SKIPPED` / `NOT_FOUND` / `DISABLED`、または`RETRIED`だが
   `overall_success`が偽）なら`FAILED`とする案を基本方針としつつ、
   詳細な場合分けは8章 Open Questionで確定する
3. 新規コンポーネントはStatelessとし、独自のキャッシュ・保持を行わない。
   `RetryQueueManager.remove()` / `dequeue()`のいずれも呼び出さない
   （構造的に到達しない設計にする）
4. `RetryManager`（既存の起動口）から、この新規コンポーネントへ薄い委譲
   メソッドで到達できるようにする（v3.9.0・v4.0.0と同じパターン）が、
   Queue操作系（`remove()` / `dequeue()`）とは呼び出しグラフ上で完全に
   独立させる
5. 既存の`RetryManager()` / `RetryManager.from_config()`呼び出し・
   `NullRetryManager`の動作は本Release後も無変更で動作すること
   （後方互換性維持）
6. `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
   `retry_queue`・既存の`retry_execution_selector.py` /
   `retry_execution_coordinator.py`はいずれも本Releaseでも無改修
   （ゼロ改修）を維持する

---

## 4. Scope

### 対象

* `RetryExecutionResult`を受け取り、更新先の`RetryQueueStatus`を判定する
  新規コンポーネントの追加（配置場所は8章 Open Questionで確定）
* `RetryManager`への、その新規コンポーネントを利用する薄い委譲メソッドの追加
* `NullRetryManager`への同名メソッドの追加（無効時は安全側の挙動）
* 単体テスト・E2Eテスト
  （`tests/test_e2e_v4_1_0_retry_queue_update_foundation.py`）
* 関連ドキュメント更新（CHANGELOG / ROADMAP / architecture.md）

### 対象外（今回やらないこと）

* `RetryQueueManager.remove()`の呼び出し
* `RetryQueueManager.dequeue()`の本格実装（Queueから実際に取り出して回す
  自動化。既存の薄い委譲メソッド`RetryManager.dequeue_retry()`（v3.2.0）
  は無改修のまま維持する）
* Queue永続化（SQLite/Redis等）
* 判定結果をQueue内部ストア（`RetryQueueManager._items`）へ実際に反映する処理
* Retry Policy（`RetryExecutionSelector`が行う`dispatchable=True`の選別基準
  の拡張。優先度・件数上限に基づく選別は対象外）
* Retry Metrics / Monitoring（成功率・試行回数分布・Queue滞留時間等の集計）
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
  `retry_queue`パッケージ自体の改修（いずれもゼロ改修を維持）
* 既存の`retry_execution_selector.py` / `retry_execution_coordinator.py`
  （v4.0.0）の変更
* 実運用のComposition Root（Scheduler → Retry Engine → Retry Queueを実際に
  つなぎ、判定結果を継続的にQueueへ反映するスクリプト）
* 新しいFeature Gate環境変数の追加・Configクラスの追加・Managerパターン
  （`from_config()` / `from_env()`等の新規起動口）の採用

---

## 5. Design Principles

* **Foundation First**：`RetryExecutionResult`を入力に更新先状態を判定
  できるところまでを行う。判定結果を実際にQueueへ反映する処理
  （`remove()`呼び出し・内部ストアの書き換え）は後続Release
  （Retry Queue Removal）へ送る
* **Single Responsibility**：新規コンポーネントは「`RetryExecutionResult`
  のリストから、各要素の更新先`RetryQueueStatus`を判定する」ことのみを
  担う。実行ロジック（`RetryExecutionCoordinator`）・選別ロジック
  （`RetryExecutionSelector`）・Queue管理（`RetryQueueManager`）のいずれも
  複製・肩代わりしない
* **Stateless**：新規コンポーネントは受け取った`RetryExecutionResult`を
  独自にキャッシュ・保持しない。呼び出しごとに渡された引数のみから結果を
  導出する
* **Backward Compatibility**：`RetryManager()` / `RetryManager.from_config(...)`の
  既存呼び出し（新規引数を渡さない場合）は、本Release後も無変更で動作する。
  `NullRetryManager`にも同名の委譲メソッドを追加し、無効時は安全側
  （空リスト等）を返す
* **RetryManagerの責務を肥大化させない**：新規委譲メソッドは
  `execute_dispatchable_retries()`（v4.0.0、無変更）への委譲＋新規
  コンポーネントへの委譲、という薄い合成のみで完結させる（判定ロジック
  自体をRetryManagerに直接書かない）

---

## 6. Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryExecutionCoordinator`（v4.0.0、無改修） | `RetryDispatchEvent`を対象に`retry()`を呼び出し`RetryExecutionResult`として集約する | Queue項目の更新先判定・Queue操作 |
| 新規コンポーネント（本Releaseで追加） | `RetryExecutionResult`を対象に、更新先の`RetryQueueStatus`（`COMPLETED` / `FAILED`）を判定する | 実行（`retry()`呼び出し）の再実装・Queueへの実際の反映（`remove()`等）・永続化 |
| `RetryManager`（本Releaseで変更） | 新規コンポーネントへの薄い委譲窓口を持つ | 判定ロジックの再実装／Queue操作との結合 |
| `RetryQueueStatus`（v3.1.0、無改修） | 状態種別の定義（`COMPLETED` / `FAILED`を含む） | 判定ロジック自体 |
| `RetryQueueManager`（v3.1.0、無改修） | Queueへの出し入れ・整列 | Queue項目の更新先判定・実行 |

---

## 7. Dependencies

```
retry_engine  ──→ retry_queue（v3.2.0のまま。新規コンポーネントが
                   RetryQueueStatusを参照する場合も、既存の依存方向の
                   範囲内でのシンボル追加にとどまる想定。8章 Open Questionで確定）
retry_engine  ──→ scheduler（SchedulerEvent型の参照のみ、v3.8.0で確立済み、無改修）
retry_engine  ──→ workflow_engine（v3.0.0のまま、無改修）
retry_engine  ──→ workflow_monitor（v3.0.0のまま、無改修）

scheduler                ──→ retry_scheduler_decision（v3.6.0のまま、無改修）
scheduler                ──→ retry_scheduler_source（v3.4.0のまま、無改修）
retry_scheduler_decision ──→ retry_scheduler_source（v3.5.0のまま、無改修）
retry_scheduler_source   ──→ retry_queue（v3.3.0のまま、無改修）
```

* 本Releaseは新規の依存**方向**を追加しない想定である。`RetryManager`は
  既に`retry_queue`パッケージへ依存しているため（v3.2.0）、新規コンポーネント
  が`RetryQueueStatus`（`retry_queue`の公開シンボル）を参照する場合も、
  既存の依存方向の範囲内でのシンボル追加にとどまる（8章 Open Questionで
  新規コンポーネントの配置場所と合わせて最終確定する）
* `retry_queue`パッケージ側（`retry_queue → retry_engine`という逆方向）は
  一切追加しない
* 循環importは発生しない

---

## 8. Open Questions（Architecture Designで確定する事項）

Project Charterの時点では確定せず、次工程のArchitecture Designで検討する。

1. **配置場所**：新規コンポーネントを`retry_engine`パッケージ内の新規ファイル
   に置くか、`retry_scheduler_decision` / `retry_scheduler_source`のような
   独立した新規パッケージ（例：`retry_queue_update`）に切り出すか
2. **新規コンポーネントの名称**：判定（Resolve）に特化した役割であることが
   明確な名称を検討する（例：`RetryQueueUpdateResolver`）
3. **戻り値の型**：判定結果をどのようなデータ構造で返すか（`run_id` /
   `target_status` / 判定根拠（`RetryExecutionResult`そのものを保持するか）
   を含む新規`frozen`データクラス、例：`RetryQueueUpdate(execution_result,
   target_status, reason)`）
4. **判定基準の詳細な場合分け**：`RetryResult.outcome`が`SKIPPED` /
   `NOT_FOUND` / `DISABLED`の場合（実際には`retry()`が再実行しなかった
   ケース）を一律`FAILED`とするか、Queue Update対象から除外する
   （判定結果リストに含めない）か
5. **`RetryManager`への委譲メソッドの名称・粒度**：
   `execute_dispatchable_retries()`と対になる1メソッドとするか
   （例：`resolve_retry_queue_updates()`）、複数粒度を用意するか
6. **新規コンポーネントの構築責務**：`RetryManager.__init__`が新規
   コンポーネントをデフォルトで自動生成するか（v3.8.0〜v4.0.0と同じ
   「省略時は自動フォールバック」）
7. **`NullRetryManager`側の扱い**：同名の委譲メソッドを追加するか。
   追加する場合、無効時に何を返すか（空リストが妥当と想定される）
8. **`RetryQueueStatus`参照の要否**：新規コンポーネントが`retry_queue`から
   `RetryQueueStatus`をimportする設計でよいか（`RetryExecutionCoordinator`
   がv4.0.0で貫いた「Queue非依存」の原則との整合性をどう説明するか。
   本Releaseの目的自体がQueue状態の判定であるため、型としての参照は
   許容範囲であることを明確化する必要がある）
9. **複数件判定時のエラーハンドリング**：ある`RetryExecutionResult`の
   判定中に例外が発生した場合、残りの処理を継続するか、そのまま伝播
   させるか（v4.0.0 Design Decision #7の踏襲を検討）

---

## 9. Acceptance Criteria

* `RetryResult.outcome == RETRIED`かつ`workflow_engine_result.overall_success
  == True`の`RetryExecutionResult`を渡した際、対応する判定結果が
  `RetryQueueStatus.COMPLETED`となること
* `RetryResult.outcome == RETRIED`かつ`workflow_engine_result.overall_success
  == False`の`RetryExecutionResult`を渡した際、対応する判定結果が
  `RetryQueueStatus.FAILED`となること
* 新規コンポーネント・`RetryManager`の委譲メソッドのいずれからも、
  `RetryQueueManager.remove()` / `dequeue()`へ到達する呼び出し経路が
  構造的に存在しないこと（Spyオブジェクトによる構造的確認、
  v3.3.0〜v4.0.0と同じ手法）
* 既存の`RetryManager()` / `RetryManager.from_config(...)`（新規引数を
  渡さない場合）が、本Release後も無変更で動作すること（後方互換性の回帰確認）
* `NullRetryManager`が本Release後も既存の全メソッド（本Releaseで追加する
  委譲メソッドを含む）で一貫してDISABLED相当の安全な挙動を返すこと
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
  `retry_queue`・`retry_execution_selector.py` / `retry_execution_coordinator.py`
  配下の全ファイルに差分がないこと（`git diff`で確認、ゼロ改修）
* E2Eテスト全PASS・既存回帰（`v2.0.0`〜`v4.0.0`）全PASS

---

## 10. Non-Goals

* `RetryQueueManager.remove()`の呼び出し
* `RetryQueueManager.dequeue()`の本格実装（Queueから実際に取り出して回す
  自動化）
* Queue永続化（SQLite/Redis等）
* 判定結果をQueue内部ストアへ実際に反映する処理
* Retry Policy（選別基準の拡張）
* Retry Metrics / Monitoring
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
  `retry_queue`パッケージ自体の変更（いずれもゼロ改修を維持）
* 既存の`retry_execution_selector.py` / `retry_execution_coordinator.py`の変更
* 実運用のComposition Root（判定結果を継続的にQueueへ反映する起動スクリプト）
* 新しいFeature Gate環境変数の追加
* Configクラスの追加
* Managerパターン（`from_config()` / `from_env()`等の新規起動口）の採用

---

## 11. Directory Structure（想定・Open Question 1・2で確定）

```text
案A：retry_engineパッケージ内に追加する場合
src/retry_engine/
├── retry_execution_selector.py     # v4.0.0のまま、無改修
├── retry_execution_coordinator.py  # v4.0.0のまま、無改修
├── retry_queue_update_*.py         # 新規：RetryExecutionResultを対象に
│                                   #        更新先RetryQueueStatusを判定するコンポーネント
├── retry_manager.py                # 変更：新規コンポーネントへの委譲メソッド追加
└── __init__.py                      # 変更：新規シンボルのexport

案B：独立した新規パッケージに切り出す場合
src/retry_queue_update/
├── __init__.py
└── retry_queue_update_resolver.py  # 新規

tests/
└── test_e2e_v4_1_0_retry_queue_update_foundation.py   # 新規
```

---

## 12. Risks and Mitigations

| リスク | 対策 |
|---|---|
| 「更新先を判定できる」ことが「実際にQueueへ反映すべきだ」という誤解を招く可能性がある | Purpose・Goals・Non-Goalsで「判定できるようにするところまで」であることを明記し、Acceptance CriteriaでSpyオブジェクトによる構造的な呼び出し経路（`remove()` / `dequeue()`）の不在確認を必須とする（v3.3.0〜v4.0.0と同じ手法） |
| `SKIPPED` / `NOT_FOUND` / `DISABLED`の扱いを誤ると、実際には再実行されていない項目が`COMPLETED`扱いになる等、Queueの意味論を壊すリスクがある | Architecture Designで場合分けを明示的に確定する（8章 Open Question 4） |
| 新規コンポーネントが`RetryQueueStatus`を参照することが、v4.0.0で確立した「Queue非依存」の原則と矛盾するように見える可能性がある | Architecture Designで「実行系（Selector/Coordinator）はQueue非依存を維持しつつ、本Releaseの新規コンポーネントは目的上Queue状態の型を参照する」という役割の違いを明示する（8章 Open Question 8） |
| 本Releaseの価値が、Retry Queue Removal（実際の`remove()`反映）を行う次Releaseまで実運用に完全には結びつかない | v3.3.0〜v4.0.0でも同様の「消費者不在／未接続」を経て段階的に統合してきた前例がある。本Releaseも同じFoundation Firstパターンとして扱う |

---

## 13. Status

- [x] Project Charter ドラフト作成（本文書、Claude Code作成）
- [ ] ユーザー確認・フィードバック反映
- [ ] Project Charter 確定
- [ ] Architecture Design（次工程。本Releaseでは着手しない）
