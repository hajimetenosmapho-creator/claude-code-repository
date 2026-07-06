# Project Charter — Release 4.0「Retry Execution Foundation」

作成日：2026-07-06
状態：ドラフト（ユーザー確認待ち）
対象：v3.9.0で`RetryManager.dispatch_retry_events()`が返すようになった
`RetryDispatchEvent`のうち、`dispatchable=True`のものだけを対象に
`RetryManager.retry()`を初めて呼び出せる基盤を構築する統合。Retry Queueへの
書き込み（`enqueue_retry()` / `dequeue_retry()`の呼び出し）・
`RetryQueueManager.dequeue()` / `remove()`の呼び出し・Queue永続化は
いずれも対象外とする。

> **本Releaseの位置づけについての注記**：`docs/ROADMAP.md`「v3.x 以降の候補」に
> 記載済みの「**Retry Execution**：Dispatchされた`RetryDispatchEvent`
> （`dispatchable=True`のもの）を実際に`RetryManager.retry()`へ渡して
> 再実行する自動化」に相当する項目に着手する。ただし、ROADMAP.mdの当該項目は
> 将来的な完成形（Retry Queueからの取り出し・結果フィードバックまで含む
> 「自動Retry実行」）を指しており、それを一度に実現するのではなく、
> ユーザー指示に基づき本Releaseでは意図的にスコープを絞る。すなわち
> 「`RetryDispatchEvent`を受け取り、`dispatchable=True`のものについて
> `RetryManager.retry()`を呼び出せるようにするFoundation」までに限定し、
> Retry Queueの更新（`enqueue_retry()` / `dequeue_retry()`の呼び出し）・
> `RetryQueueManager.dequeue()` / `remove()`の呼び出し・Queue永続化には
> 進まない。これらは`docs/ROADMAP.md`に別項目として記載済みの
> **Retry Queue Update** / **Retry Queue Persistence**（本Release後も
> 未着手のまま）に委ねる。

---

## 1. Background

* Retry Scheduler Event Integration（v3.7.0）：`SchedulerEngine.evaluate()` /
  `run_due()`が、Job由来とRetry候補由来の`SchedulerEvent`が混在したリストを
  出力するようになった。
* Retry Engine Event Consumption（v3.8.0）：`RetryManager.recognize_retry_events()`
  経由で、混在リストから「Retry候補由来のものだけ」を`RetryCandidateEvent`
  （`run_id` / `candidate` / `source_event`）として認識できるようになった。
  `candidate`は`RetryQueueItem`（`retry_attempt`を含む）をそのまま保持する。
* Retry Engine Event Dispatch（v3.9.0）：`RetryManager.dispatch_retry_events()`
  経由で、認識済みの`RetryCandidateEvent`を`RetryDispatchEvent`
  （`candidate_event` / `dispatchable`）として整理できるようになった。
  `dispatchable`は`candidate_event.run_id`が空でないかという構造的妥当性
  のみを判定する。整理のみで完結しており、`RetryDispatchEvent`を実際に
  使って何かを実行する仕組みは`retry_engine`側に一切存在しない。
* `docs/ROADMAP.md`「v3.x 以降の候補」に、次の未着手項目として記載がある：
  「**Retry Execution**：Dispatchされた`RetryDispatchEvent`
  （`dispatchable=True`のもの）を実際に`RetryManager.retry()`へ渡して
  再実行する自動化（自動Retry実行）」。本Releaseはこの項目に着手するが、
  スコープを「`RetryManager.retry()`を呼び出せるFoundationの構築」までに
  絞る（詳細は3章 Goals・上記の位置づけ注記）。

```
Retry Engine（受信・整理、v3.0.0〜v3.9.0）
   │
   ├── recognize_retry_events()（v3.8.0、無改修）
   │      → RetryCandidateEvent のリスト
   ├── dispatch_retry_events()（v3.9.0、無改修）
   │      → RetryDispatchEvent のリスト（candidate_event・dispatchable）
   │
   └──────── ★本Releaseで新設 ────────
        「dispatchable=True の RetryDispatchEvent を対象に
         RetryManager.retry() を呼び出せる Foundation」
        （Queueの読み書き・永続化は行わない）
```

---

## 2. Purpose

`retry_engine`パッケージに、`dispatch_retry_events()`（v3.9.0）が返す
`RetryDispatchEvent`のリストを受け取り、`dispatchable=True`のものだけを
対象に`RetryManager.retry()`を呼び出す新規コンポーネントを追加する。

ただし、Retry Queueへの書き込み（`enqueue_retry()` / `dequeue_retry()`の
呼び出し）・`RetryQueueManager.dequeue()` / `remove()`の呼び出し・
Queue永続化は本Releaseの対象外とする。あくまで「`RetryDispatchEvent`を
入力に`RetryManager.retry()`を呼び出せるようにする」ところまでに留める。

---

## 3. Goals

本Releaseで確立する Retry Execution Foundation は、次のことだけを行う。

1. `retry_engine`パッケージに、`RetryDispatchEvent`のリストを受け取り、
   `dispatchable=True`のものだけを対象に`RetryManager.retry()`を呼び出す
   新規コンポーネントを追加する（具体的なクラス名・配置場所は8章
   Open Questionsで確定する）
2. `dispatchable=False`のイベントは`retry()`を呼ばずスキップし、その扱いを
   （結果リストに含めるか、除外するか）明確化する（8章 Open Question）
3. `retry()`呼び出しに必要な`attempt`値を、`RetryCandidateEvent.candidate`
   （`RetryQueueItem`）の`retry_attempt`から取得する方針を定義する
   （8章 Open Question）
4. 実行結果をどのような型で返すか（`RetryResult`のリストそのままか、
   `candidate_event`と対にした新規ラッパー型か）を定義する
   （8章 Open Question）
5. 新規コンポーネントはStatelessとし、独自のキャッシュ・保持を行わない。
   `enqueue_retry()` / `dequeue_retry()` / `RetryQueueManager.dequeue()` /
   `remove()`のいずれも呼び出さない（構造的に到達しない設計にする）
6. `RetryManager`（既存の起動口）から、この新規コンポーネントへ薄い委譲
   メソッドで到達できるようにする（v3.8.0・v3.9.0と同じパターン）が、
   Queue操作系（`enqueue_retry()` / `dequeue_retry()`）とは呼び出しグラフ上
   で完全に独立させる
7. 既存の`RetryManager()` / `RetryManager.from_config()`呼び出し・
   `NullRetryManager`の動作は本Release後も無変更で動作すること
   （後方互換性維持）
8. `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
   `retry_queue`はいずれも本Releaseでも無改修（ゼロ改修）を維持する

---

## 4. Scope

### 対象

* `retry_engine`パッケージへの、`RetryDispatchEvent`を受け取り
  `dispatchable=True`のものについて`RetryManager.retry()`を呼び出す
  新規コンポーネントの追加
* `RetryManager`への、その新規コンポーネントを利用する薄い委譲メソッドの追加
* `NullRetryManager`への同名メソッドの追加（無効時は安全側の挙動）
* 単体テスト・E2Eテスト
  （`tests/test_e2e_v4_0_0_retry_execution_foundation.py`）
* 関連ドキュメント更新（CHANGELOG / ROADMAP / architecture.md）

### 対象外（今回やらないこと）

* Retry Queueの更新（`enqueue_retry()` / `dequeue_retry()`の呼び出しを含む
  あらゆる書き込み）
* `RetryQueueManager.dequeue()`の呼び出し
* `RetryQueueManager.remove()`の呼び出し
* Queue永続化（SQLite/Redis等）
* `dispatchable`の判定基準の変更（優先度・件数上限に基づく選別。
  v3.9.0のまま無改修）
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
  `retry_queue`パッケージ自体の改修（いずれもゼロ改修を維持）
* 実運用のComposition Root（Scheduler → Retry Engineを実際につなぎ、
  Dispatch結果を継続的に実行するスクリプト）
* `job_id`予約プレフィックス（`"retry:"`）の構造的な衝突防止の仕組み化
* 新しいFeature Gate環境変数の追加・Configクラスの追加・Managerパターン
  （`from_config()` / `from_env()`等の新規起動口）の採用
* Retry実行結果（成功・失敗）をRetry Queueへフィードバックする仕組み
  （`docs/ROADMAP.md`記載の別項目「Retry Queue Update」に委ねる）

---

## 5. Design Principles

* **Foundation First**：`dispatchable=True`の`RetryDispatchEvent`を対象に
  `RetryManager.retry()`を呼び出せるところまでを行う。Retry Queueからの
  取り出し（`dequeue()`）・実行結果のQueueへの反映（`remove()`等）は
  後続Release（Retry Queue Update）へ送る
* **Single Responsibility**：新規コンポーネントは「`RetryDispatchEvent`の
  リストから`dispatchable=True`のものを選び、`RetryManager.retry()`へ
  渡す」ことのみを担う。Dispatch判定ロジック自体（`RetryEventDispatcher`）・
  Retry可否判定（`RetryPolicy`）・Queue管理（`retry_queue`）のいずれも
  複製・肩代わりしない
* **Stateless**：新規コンポーネントは受け取った`RetryDispatchEvent`を
  独自にキャッシュ・保持しない。呼び出しごとに渡された引数のみから結果を
  導出する
* **Backward Compatibility**：`RetryManager()` / `RetryManager.from_config(...)`の
  既存呼び出し（新規引数を渡さない場合）は、本Release後も無変更で動作する。
  `NullRetryManager`にも同名の委譲メソッドを追加し、無効時は安全側
  （空リスト等）を返す

---

## 6. Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryEventDispatcher`（v3.9.0、無改修） | `RetryCandidateEvent`をDispatch対象として整理する（`dispatchable`の判定） | 実行（`retry()`呼び出し）・Queue操作 |
| 新規コンポーネント（本Releaseで追加、`retry_engine`配下） | `dispatchable=True`の`RetryDispatchEvent`を対象に`RetryManager.retry()`を呼び出す | Dispatch判定の再実装・Retry可否判定・Queue操作 |
| `RetryManager`（本Releaseで変更） | 新規コンポーネントへの薄い委譲窓口を持つ | 実行ロジックの再実装／Queue操作との結合 |
| `RetryPolicy` / `RetryExecutor`（v3.0.0、無改修） | Retry可否判定・実行（`retry()`内部で引き続き使用） | イベント認識・Dispatch |
| `RetryQueueManager`（v3.1.0、無改修） | Queueへの出し入れ・整列 | イベント認識・Dispatch・実行 |

---

## 7. Dependencies

```
retry_engine  ──→ scheduler（SchedulerEvent型の参照のみ、v3.8.0で確立済み・本Releaseで新規追加なし）
retry_engine  ──→ retry_queue（v3.2.0のまま、無改修）
retry_engine  ──→ workflow_engine（v3.0.0のまま、無改修）
retry_engine  ──→ workflow_monitor（v3.0.0のまま、無改修）

scheduler                ──→ retry_scheduler_decision（v3.6.0のまま、無改修）
scheduler                ──→ retry_scheduler_source（v3.4.0のまま、無改修）
retry_scheduler_decision ──→ retry_scheduler_source（v3.5.0のまま、無改修）
retry_scheduler_source   ──→ retry_queue（v3.3.0のまま、無改修）
```

* 本Releaseは新規の依存方向を追加しない想定である。新規コンポーネントは
  `retry_engine`パッケージ内部の`RetryDispatchEvent`（v3.9.0で新設済み）と
  既存の`RetryManager.retry()`のみを利用するため、外部パッケージへの
  新規依存は発生しない見込み（8章 Open Questionで最終確定する）
* `scheduler`パッケージ側（`scheduler → retry_engine`という逆方向）は
  一切追加しない
* 循環importは発生しない

---

## 8. Open Questions（Architecture Designで確定する事項）

Project Charterの時点では確定せず、次工程のArchitecture Designで検討する。

1. **配置場所**：新規コンポーネントを`retry_engine`パッケージ内の新規ファイル
   に置くか、独立した新規パッケージに切り出すか
2. **新規コンポーネントの名称**：既存の`RetryExecutor`（v3.0.0、
   `WorkflowEngineManager.run()`を実際に呼ぶ実行系）と役割が異なることを
   明確にできる名称を検討する（例：`RetryExecutionCoordinator`）
3. **`attempt`値の取得方法**：`RetryManager.retry(run_id, attempt=...)`に
   渡す`attempt`値を、`candidate_event.candidate`（`RetryQueueItem`）の
   `retry_attempt`からそのまま取得する方針でよいか、他の取得方法を
   検討する必要があるか
4. **`dry_run`パラメータの扱い**：新規コンポーネント・委譲メソッドが
   `dry_run`を呼び出し元から受け取れるようにするか、デフォルト`False`
   固定とするか
5. **`dispatchable=False`のイベントの扱い**：`retry()`を呼ばずスキップする
   点は確定だが、結果リストから完全に除外するか、「スキップされたこと」を
   表す結果として含めるか
6. **実行結果の型**：`RetryManager.retry()`が返す`RetryResult`のリストを
   そのまま返すか、`candidate_event`と対にした新規ラッパー型
   （例：`RetryExecutionOutcome(dispatch_event, retry_result)`）を
   新設するか
7. **`RetryManager`への委譲メソッドの粒度・名称**：`dispatch_retry_events()`
   と対になる1メソッドとするか、複数粒度を用意するか
8. **新規コンポーネントの構築責務**：`RetryManager.__init__`が新規
   コンポーネントをデフォルトで自動生成するか（v3.8.0・v3.9.0と同じ
   「省略時は自動フォールバック」）
9. **`NullRetryManager`側の扱い**：同名の委譲メソッドを追加するか。
   追加する場合、無効時に何を返すか（空リストが妥当と想定される）
10. **複数件実行時のエラーハンドリング**：ある`run_id`に対する`retry()`
    呼び出しが例外を送出した場合、残りの処理を継続するか、そのまま
    伝播させるか

---

## 9. Acceptance Criteria

* `dispatchable=True`の`RetryDispatchEvent`を渡した際、対応する`run_id`に
  対して`RetryManager.retry()`が呼び出されること
* `dispatchable=False`の`RetryDispatchEvent`に対しては`retry()`が
  呼び出されないこと
* 新規コンポーネント・`RetryManager`の委譲メソッドのいずれからも、
  `enqueue_retry()` / `dequeue_retry()`・`RetryQueueManager.dequeue()` /
  `remove()`へ到達する呼び出し経路が構造的に存在しないこと（Spyオブジェクト
  による構造的確認、v3.3.0〜v3.9.0と同じ手法）
* 既存の`RetryManager()` / `RetryManager.from_config(...)`（新規引数を
  渡さない場合）が、本Release後も無変更で動作すること（後方互換性の回帰確認）
* `NullRetryManager`が本Release後も既存の全メソッド（本Releaseで追加する
  委譲メソッドを含む）で一貫してDISABLED相当の安全な挙動を返すこと
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
  `retry_queue`配下の全ファイルに差分がないこと（`git diff`で確認、ゼロ改修）
* E2Eテスト全PASS・既存回帰（`v2.0.0`〜`v3.9.0`）全PASS

---

## 10. Non-Goals

* Retry Queueの更新（`enqueue_retry()` / `dequeue_retry()`の呼び出しを含む
  あらゆる書き込み）
* `RetryQueueManager.dequeue()` / `remove()`の呼び出し
* Queue永続化（SQLite/Redis等）
* `dispatchable`の判定基準の変更（優先度・件数上限に基づく選別）
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
  `retry_queue`パッケージ自体の変更（いずれもゼロ改修を維持）
* 実運用のComposition Root（Scheduler → Retry Engineを実際につなぐ起動スクリプト）
* `job_id`予約プレフィックスの構造的な衝突防止の仕組み化
* 新しいFeature Gate環境変数の追加
* Configクラスの追加
* Managerパターン（`from_config()` / `from_env()`等の新規起動口）の採用
* Retry実行結果のRetry Queueへのフィードバック（Retry Queue Update）

---

## 11. Directory Structure（想定・Open Question 1・2で確定）

```text
案A：retry_engineパッケージ内に追加する場合
src/retry_engine/
├── retry_event_consumer.py    # v3.8.0のまま、無改修
├── retry_event_dispatcher.py  # v3.9.0のまま、無改修
├── retry_execution_*.py       # 新規：dispatchable=True の RetryDispatchEvent を
│                              #        対象に retry() を呼び出すコンポーネント
├── retry_manager.py           # 変更：新規コンポーネントへの委譲メソッド追加
└── __init__.py                 # 変更：新規シンボルのexport

tests/
└── test_e2e_v4_0_0_retry_execution_foundation.py   # 新規
```

---

## 12. Risks and Mitigations

| リスク | 対策 |
|---|---|
| 「`retry()`を呼び出す」ことが「Queue操作（`dequeue()` / `remove()`）まで踏み込むべきだ」という誤解を招く可能性がある | Purpose・Goals・Non-Goalsで「`RetryDispatchEvent`を入力に`retry()`を呼び出せるようにするところまで」であることを明記し、Acceptance CriteriaでSpyオブジェクトによる構造的な呼び出し経路の不在確認を必須とする（v3.8.0・v3.9.0と同じ手法） |
| `attempt`値の取得元（`candidate.retry_attempt`）を誤ると、`RetryPolicy`の判定（`max_attempts`等）がずれ、想定と異なる`RetryOutcome`になる | Architecture Designで`RetryQueueItem.retry_attempt`のセマンティクスを確認し、`retry()`への受け渡し方法を慎重に設計する（8章 Open Question 3） |
| 複数件の`RetryDispatchEvent`を処理する途中で`retry()`が例外を送出した場合の挙動が未定義だと、一部の再実行が silently 失われる可能性がある | Architecture Designで明示的にエラーハンドリング方針を検討する（8章 Open Question 10） |
| 本Releaseの価値が、Retry Queue Update（結果フィードバック）を行う次Releaseまで実運用に完全には結びつかない | v3.3.0〜v3.9.0でも同様の「消費者不在／未接続」を経て段階的に統合してきた前例がある。本Releaseも同じFoundation Firstパターンとして扱う |

---

## 13. Status

- [x] Project Charter ドラフト作成（本文書、Claude Code作成）
- [ ] ユーザー確認・フィードバック反映
- [ ] Project Charter 確定
- [ ] Architecture Design（次工程。本Releaseでは着手しない）
