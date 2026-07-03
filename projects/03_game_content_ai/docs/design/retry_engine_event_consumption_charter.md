# Project Charter — Release 3.8「Retry Engine Event Consumption」

作成日：2026-07-03
状態：ドラフト（ユーザー確認待ち）
対象：v3.7.0で`SchedulerEngine.evaluate()` / `run_due()`が生成するようになった
Retry候補由来の`SchedulerEvent`（`job_id="retry:"+run_id`）を、Retry Engine側
（`retry_engine`パッケージ）が「受け取って認識できる」ようにする統合。
Retry Queueの更新・`dequeue()` / `remove()`の呼び出し・Retry実行の開始・
Queue永続化はいずれも対象外とする。

> **本Releaseの位置づけについての注記**：v3.3.0〜v3.7.0までの5リリースは
> いずれも「Scheduler側から見て、Retry Queueの情報をどう読み取り・選択し・
> `SchedulerEvent`として表現するか」という**Scheduler側（発信側）**の統合だった。
> 本Release（v3.8.0）は初めて**Retry Engine側（受信側）**に手を入れるReleaseであり、
> `docs/ROADMAP.md`「v3.x 以降の候補」に記載済みの
> 「Retry候補由来の`SchedulerEvent`（v3.7.0）を消費する仕組み：Retry Engine起動・
> Workflow Engine起動等、実際に候補を処理する統合」の**最初の一歩**に相当する。
> ただし今回は「消費（実行）」ではなく「認識（受け取って、それとわかる）」までに
> 意図的に限定する。ROADMAP.mdで次段階として記載されている「自動Retry実行：
> `select_next_candidate()` / `select_candidates()`で選ばれた候補を`dequeue()`で
> 取り出し`RetryManager.retry()`へ渡す一連の自動化」には本Releaseでは進まない。

---

## 1. Background

* Retry Scheduler Integration（v3.3.0）〜Retry Scheduler Decision Wiring（v3.6.0）：
  Retry Queueの情報を`RetrySchedulerSource`→`RetrySchedulerDecision`の順で
  `SchedulerEngine`まで読み取り専用で中継する経路を確立した。
* Retry Scheduler Event Integration（v3.7.0）：`SchedulerEngine.evaluate()` /
  `run_due()`が、`RetrySchedulerDecision.select_candidates()`の結果を
  Additive方式で`SchedulerEvent`として出力に含めるようになった。
  `job_id="retry:"+run_id`、`metadata={"retry_candidate": 候補オブジェクト}`という
  形式が確定している（`docs/design/retry_scheduler_event_integration.md`）。
* 一方、`retry_engine`パッケージ（`RetryManager` / `NullRetryManager`、v3.0.0〜v3.2.0）は
  `scheduler`パッケージを一切importしておらず、`SchedulerEvent`という型の存在を
  知らない。v3.7.0で生成されるようになったRetry候補由来の`SchedulerEvent`は、
  「誰にも受け取られない」状態のまま存在している
  （v3.3.0の`RetrySchedulerSource`と同じ「消費者不在の先行実装」パターン）。
* `docs/ROADMAP.md`「v3.x 以降の候補」に、次の未着手項目として記載がある：
  「Retry候補由来の`SchedulerEvent`（v3.7.0）を消費する仕組み：Retry Engine起動・
  Workflow Engine起動等、実際に候補を処理する統合（v3.7.0では`SchedulerEvent`を
  生成するところまでで意図的に対象外）」。本Releaseはこの項目の**着手**に相当するが、
  スコープを「認識できるようにする」ところまでに絞る（詳細は3章 Goals）。

```
Scheduler（判断、v2.6.0〜v3.7.0）                    Retry Engine（実行判断、v3.0.0〜v3.2.0）
   │                                                      │
   └── evaluate() / run_due()                             ├── retry()（Read Before Retry）
            │                                              ├── enqueue_retry() / dequeue_retry()
            └── SchedulerEvent 生成                        │      （RetryQueueManagerへの薄い委譲）
                 （Job由来 ＋ Retry候補由来、v3.7.0）        │
                          │                                 │
                          └──────── ★本Releaseで新設 ────────┘
                             「Retry候補由来のSchedulerEventを
                              Retry Engine側が認識できるようにする経路」
                              （認識のみ。実行・Queue操作は行わない）
```

---

## 2. Purpose

`retry_engine`パッケージに、`scheduler`パッケージが生成した`SchedulerEvent`の
リストを受け取り、その中から「Retry候補由来のイベント」だけを識別・認識できる
コンポーネントを新設する。これにより、Retry Engine側は「今どのRetry候補が
Schedulerによって選ばれているか」を、Retry Queueへ一切書き込むことなく
把握できるようになる。

ただし、認識した結果を使って実際に`retry()`を呼び出す・Retry Queueから
取り出す（`dequeue()`）・取り除く（`remove()`）といった**行動**は本Releaseの
対象外とする。あくまで「受け取って、それとわかる」ところまでに留める。

---

## 3. Goals

本Releaseで確立する Retry Engine Event Consumption は、次のことだけを行う。

1. `retry_engine`パッケージに、`SchedulerEvent`のリストを受け取り、
   Retry候補由来のものだけを識別する新規コンポーネントを追加する
   （具体的なクラス名・配置場所は8章 Open Questionsで確定する）
2. 識別の判定基準は、v3.7.0で確定済みの規約
   （`job_id`が`"retry:"`で始まる）を踏襲する
3. 認識結果には、元の`SchedulerEvent`・`run_id`・`metadata["retry_candidate"]`に
   格納された候補オブジェクトを含める（候補オブジェクトを分解・変換しない。
   v3.7.0 Design Decision #3の方針を受信側でも踏襲する）
4. 認識処理は読み取り専用（Stateless）とし、`RetryQueueManager.dequeue()` /
   `remove()`・`RetryManager.retry()`・`enqueue_retry()` / `dequeue_retry()`の
   いずれも呼び出さない（構造的に到達しない設計にする）
5. `RetryManager`（既存の起動口）から、この新規コンポーネントへ薄い委譲メソッドで
   到達できるようにする（v3.4.0で`SchedulerEngine`が`RetrySchedulerSource`を
   DIで保持したのと同じパターン）が、既存の`retry()` / `enqueue_retry()` /
   `dequeue_retry()`とは呼び出しグラフ上で完全に独立させる
6. 既存の`RetryManager()` / `RetryManager.from_config()`呼び出し・
   `NullRetryManager`の動作は本Release後も無変更で動作すること
   （後方互換性維持）
7. `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
   `retry_queue`はいずれも本Releaseでも無改修（ゼロ改修）を維持する

---

## 4. Scope

### 対象

* `retry_engine`パッケージへの、`SchedulerEvent`を受け取り認識する
  新規コンポーネントの追加
* `RetryManager`への、その新規コンポーネントを利用する薄い委譲メソッドの追加
* `retry_engine`パッケージが`scheduler`パッケージ（`SchedulerEvent`型）へ
  依存する、新規の依存方向の確立
* 単体テスト・E2Eテスト
  （`tests/test_e2e_v3_8_0_retry_engine_event_consumption.py`）
* 関連ドキュメント更新（CHANGELOG / ROADMAP / architecture.md）

### 対象外（今回やらないこと）

* Retry Queueの更新（`enqueue` / `dequeue` / `remove`を含むあらゆる書き込み）
* `RetryQueueManager.dequeue()`の呼び出し
* `RetryQueueManager.remove()`の呼び出し
* Retry実行の開始（`RetryManager.retry()`の自動呼び出し、認識結果からの自動起動）
* Queue永続化（SQLite/Redis等）
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
  `retry_queue`パッケージ自体の改修（いずれもゼロ改修を維持）
* 実運用のComposition Root（`SchedulerEngine.run_due()`の結果を実際に
  `RetryManager`へ渡して回すスクリプト、例：`scripts/run_scheduler.py`）
* `job_id`予約プレフィックス（`"retry:"`）の構造的な衝突防止の仕組み化
  （v3.7.0からの既知の限界を本Releaseでも引き継ぐ。11章参照）
* 新しいFeature Gate環境変数の追加・Configクラスの追加・Managerパターン
  （`from_config()` / `from_env()`等の新規起動口）の採用

---

## 5. Design Principles

* **Foundation First**：Retry候補由来の`SchedulerEvent`を「受け取って
  それとわかる」ところまでを行う。認識結果を使った実行
  （`retry()`の自動呼び出し・自動Retry実行）は後続Releaseへ送る
* **Single Responsibility**：新規コンポーネントは「`SchedulerEvent`のリストから
  Retry候補由来のものを識別する」ことのみを担う。候補選択ロジック自体
  （`RetrySchedulerDecision`）・Queue管理（`retry_queue`）・実行判断
  （`RetryPolicy` / `RetryManager.retry()`）のいずれも複製・肩代わりしない
* **Stateless**：新規コンポーネントは受け取った`SchedulerEvent`を
  独自にキャッシュ・保持しない。呼び出しごとに渡された引数のみから結果を
  導出する純粋関数的な設計にする
* **Constructor Injection のみ**：セッターインジェクション・実行時の差し替え
  メソッド・ファクトリメソッド（`from_config()`等）は追加しない
* **Read Only（Retry Queueに対して）**：新規コンポーネントも`RetryManager`の
  委譲メソッドも、`RetryQueueManager`の書き込み系メソッド
  （`enqueue()` / `dequeue()` / `remove()`）へ到達する経路を一切持たない
* **Backward Compatibility**：`RetryManager()` / `RetryManager.from_config()`の
  既存呼び出し（新規引数を渡さない場合）は、本Release後も無変更で動作する。
  `NullRetryManager`にも同名の委譲メソッドを追加し、無効時は安全側
  （空リスト等）を返す

---

## 6. Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `SchedulerEngine`（v3.7.0、無改修） | Retry候補由来の`SchedulerEvent`を生成する | 生成した`SchedulerEvent`を誰かに届ける／実行させる |
| 新規コンポーネント（本Releaseで追加、`retry_engine`配下） | `SchedulerEvent`のリストからRetry候補由来のものを識別・認識する | 実行判断（`RetryPolicy`）・Queue操作・Retry実行 |
| `RetryManager`（本Releaseで変更） | 新規コンポーネントへの薄い委譲窓口を持つ | 認識ロジックの再実装／認識結果の自動実行 |
| `RetryPolicy` / `RetryExecutor`（v3.0.0、無改修） | Retry可否判定・実行 | イベント認識 |
| `RetryQueueManager`（v3.1.0、無改修） | Queueへの出し入れ・整列 | イベント認識・実行判断 |

---

## 7. Dependencies

```
retry_engine  ──→ scheduler（SchedulerEvent型の参照のみ） ★本Releaseで新規追加
retry_engine  ──→ retry_queue（v3.2.0のまま、無改修）
retry_engine  ──→ workflow_engine（v3.0.0のまま、無改修）
retry_engine  ──→ workflow_monitor（v3.0.0のまま、無改修）

scheduler                ──→ retry_scheduler_decision（v3.6.0のまま、無改修）
scheduler                ──→ retry_scheduler_source（v3.4.0のまま、無改修）
retry_scheduler_decision ──→ retry_scheduler_source（v3.5.0のまま、無改修）
retry_scheduler_source   ──→ retry_queue（v3.3.0のまま、無改修）
```

* 本Releaseで新規に追加される依存方向は`retry_engine → scheduler`の1本のみ。
  `SchedulerEvent`（データクラス、副作用を持たない）への参照に限定し、
  `SchedulerEngine` / `SchedulerManager` / `SchedulerRepository`等の
  実行系クラスはimportしない
* `scheduler`パッケージ側（`scheduler → retry_engine`という逆方向）は
  一切追加しない。既存の一方向依存原則
  （`scheduler`は`src/ai/` / `src/pipeline/`を一切importしないEvent Driven
  Architectureの原則）を、`retry_engine`から見た片方向依存としても維持する
* 循環importは発生しない（`scheduler`パッケージの依存先である
  `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue`は
  いずれも`retry_engine`をimportしないため）

---

## 8. Open Questions（Architecture Designで確定する事項）

Project Charterの時点では確定せず、次工程のArchitecture Designで検討する。

1. **配置場所**：新規コンポーネントを`retry_engine`パッケージ内の新規ファイル
   （例：`src/retry_engine/retry_event_consumer.py`）に置くか、v3.3.0
   （`retry_scheduler_source`）・v3.5.0（`retry_scheduler_decision`）の前例に
   倣って独立した新規パッケージ（例：`src/retry_scheduler_event_consumer/`）に
   切り出すか。前者は「Retry EngineがRetryイベントを認識できるようにする」
   というユーザー指示の目的に直接的だが`retry_engine`の依存が増える。
   後者はパッケージの独立性を保てるが、`RetryManager`から見ると
   v3.2.0（`retry_queue`）・v3.3.0（`retry_scheduler_source`）と並ぶ
   3つ目の外部依存を管理する形になる
2. **識別結果の型**：認識結果を表す専用データクラス（例：
   `RetryCandidateEvent(run_id, candidate, source_event)`）を新設するか、
   `metadata["retry_candidate"]`の値（候補オブジェクト）とその`run_id`だけを
   タプル等の軽量な形で返すか
3. **判定基準の実装方法**：`"retry:"`という予約プレフィックスの文字列を
   `retry_engine`側でも定数として重複定義するか、それとも
   `scheduler`パッケージ側にこの定数を公開APIとして追加してもらい
   `retry_engine`から参照するか（後者は`scheduler`パッケージの変更を伴うため
   「Scheduler側は無改修」というGoals 7と矛盾する。前者は重複定義という
   技術的負債を伴う。11章 Risks参照）
4. **`RetryManager`への委譲メソッドの粒度**：`RetrySchedulerSource` /
   `RetrySchedulerDecision`に対する`SchedulerEngine`の委譲パターン
   （`count_pending_retries()` / `list_pending_retries()` /
   `select_candidates()` / `select_next_candidate()`）を踏襲し、
   「認識のみ行うメソッド」を1つ追加するのか、複数粒度
   （1件識別 / 複数件識別）を用意するか
5. **新規コンポーネントの構築責務**：`RetryManager.__init__`が新規コンポーネントを
   デフォルトで自動生成する（Stateless・設定不要のため、v3.6.0の
   `RetrySchedulerDecision`のような「必須DI・Null実装なし」ではなく、
   `RetrySchedulerSource`に近い「省略時は自動フォールバック」にできる可能性が
   高い）か、`RetrySchedulerDecision`のように呼び出し元が必ず組み立てて
   渡す方式にするか
6. **`NullRetryManager`側の扱い**：`NullRetryManager`にも同名の委譲メソッドを
   追加するか。追加する場合、無効時に何を返すか（空リストが妥当と想定されるが、
   `DISABLED`を表す何らかの結果を返す既存メソッド群との一貫性を含めて確定する）

---

## 9. Acceptance Criteria

* `SchedulerEvent`のリストを渡した際、`job_id`が`"retry:"`で始まるものだけが
  認識結果に含まれ、それ以外（Job由来の`SchedulerEvent`）は含まれないこと
* 認識結果から、元の`metadata["retry_candidate"]`に格納された候補オブジェクトへ
  分解・変換なしにアクセスできること
* 新規コンポーネント・`RetryManager`の委譲メソッドのいずれからも、
  `RetryQueueManager.dequeue()` / `remove()`・`RetryManager.retry()`・
  `enqueue_retry()` / `dequeue_retry()`へ到達する呼び出し経路が
  構造的に存在しないこと（Spyオブジェクトによる構造的確認、
  v3.3.0〜v3.7.0と同じ手法）
* 既存の`RetryManager()` / `RetryManager.from_config(...)`（新規引数を
  渡さない場合）が、本Release後も無変更で動作すること（後方互換性の回帰確認）
* `NullRetryManager`が本Release後も既存の4メソッド
  （`retry()` / `enqueue_retry()` / `dequeue_retry()`、および本Releaseで
  追加する委譲メソッド）で一貫してDISABLED相当の安全な挙動を返すこと
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
  `retry_queue`配下の全ファイルに差分がないこと（`git diff`で確認、ゼロ改修）
* `retry_engine`から`scheduler`への依存が、`SchedulerEvent`型の参照のみに
  限定されており、`SchedulerEngine` / `SchedulerManager`等の実行系クラスを
  importしていないこと
* E2Eテスト全PASS・既存回帰（`v2.0.0`〜`v3.7.0`）全PASS

---

## 10. Non-Goals

* Retry Queueの更新（`enqueue` / `dequeue` / `remove`を含むあらゆる書き込み）
* `RetryQueueManager.dequeue()` / `remove()`の呼び出し
* Retry実行の開始（認識結果を使った`RetryManager.retry()`の自動呼び出し）
* Queue永続化（SQLite/Redis等）
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
  `retry_queue`パッケージ自体の変更（いずれもゼロ改修を維持）
* 実運用のComposition Root（Scheduler → Retry Engineを実際につなぐ起動スクリプト）
* `job_id`予約プレフィックスの構造的な衝突防止の仕組み化
* 新しいFeature Gate環境変数の追加
* Configクラスの追加
* Managerパターン（`from_config()` / `from_env()`等の新規起動口）の採用

---

## 11. Directory Structure（想定・Open Question 1で確定）

```text
案A：retry_engineパッケージ内に追加する場合
src/retry_engine/
├── retry_event_consumer.py   # 新規：SchedulerEventからRetry候補由来のものを認識
├── retry_manager.py           # 変更：新規コンポーネントへの委譲メソッド追加
└── __init__.py                 # 変更：新規シンボルのexport

案B：独立パッケージとして切り出す場合（v3.3.0 / v3.5.0の前例踏襲）
src/retry_scheduler_event_consumer/
├── retry_scheduler_event_consumer.py   # 新規
└── __init__.py                          # 新規

src/scheduler/                 # 全ファイル無改修
src/retry_scheduler_decision/  # 全ファイル無改修
src/retry_scheduler_source/    # 全ファイル無改修
src/retry_queue/               # 全ファイル無改修

tests/
└── test_e2e_v3_8_0_retry_engine_event_consumption.py   # 新規
```

---

## 12. Risks and Mitigations

| リスク | 対策 |
|---|---|
| `"retry:"`という予約プレフィックスが、`retry_engine`側でも文字列として重複定義される可能性がある（v3.7.0で`scheduler`側に閉じたまま、公開定数化されていないため） | Open Question 3として明示し、Architecture Designで重複定義を許容するか`scheduler`側の公開API変更を検討するかを確定する。いずれの場合も本Releaseの対象外である「`scheduler`ゼロ改修」との整合を優先する |
| `retry_engine → scheduler`という新規依存方向が、将来`scheduler`パッケージの変更に`retry_engine`を巻き込むリスクを生む | `SchedulerEvent`（フィールド4つの単純なdataclass、副作用なし）への参照のみに限定し、`SchedulerEngine`等の実行系クラスは一切importしないことをAcceptance Criteriaで構造的に保証する |
| 「認識できるだけ」で終える本Releaseの価値が、自動Retry実行を行う次Releaseまで実運用に結びつかない | v3.3.0〜v3.7.0でも同様の「消費者不在／未接続」を経て段階的に統合してきた前例がある。本Releaseも同じFoundation Firstパターンとして扱う |
| 認識結果のデータ構造（Open Question 2）を安易に決めると、次Release（自動Retry実行）で`RetryRequest`への変換ロジックが複雑になる | Architecture Designで、次Releaseが必要とするであろう最小限の情報（`run_id`・候補オブジェクトそのもの）のみを持つシンプルな構造に留め、変換ロジックは次Release側の責務として明確に切り分ける |

---

## 13. Status

- [x] Project Charter ドラフト作成（本文書、Claude Code作成）
- [ ] ユーザー確認・フィードバック反映
- [ ] Project Charter 確定
- [ ] Architecture Design（次工程。本Releaseでは着手しない）
