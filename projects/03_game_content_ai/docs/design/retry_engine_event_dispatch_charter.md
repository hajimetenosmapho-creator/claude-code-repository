# Project Charter — Release 3.9「Retry Engine Event Dispatch」

作成日：2026-07-06
状態：ドラフト（ユーザー確認待ち）
対象：v3.8.0で`RetryManager.recognize_retry_events()`が返すようになった
`RetryCandidateEvent`のリストを、Retry Engine側が「Dispatch対象として扱える」
ようにするFoundationを構築する統合。`RetryManager.retry()`の呼び出し・
Retry Queueの更新・`dequeue()` / `remove()`の呼び出し・Queue永続化は
いずれも対象外とする。

> **本Releaseの位置づけについての注記**：`docs/ROADMAP.md`「v3.x 以降の候補」に
> 記載済みの「**Retry Engine Event Dispatch**：`recognize_retry_events()`
> （v3.8.0）が返した`RetryCandidateEvent`を、実際に処理すべき対象として
> 振り分ける仕組み（例：優先度・件数上限に基づく選別、複数候補からの実行対象決定）。
> 認識（v3.8.0）と実行（Retry Execution）の間に位置する統合ステップ」に相当する。
> v3.8.0までで確立した「認識（受け取って、それとわかる）」の次の段階として、
> 「認識した結果をDispatch対象として扱えるようにする（整理・振り分け）」までに
> 意図的に限定し、ROADMAP.mdで次段階として記載されている「Retry Execution：
> 認識・Dispatchされた`RetryCandidateEvent`を実際に`RetryManager.retry()`へ
> 渡して再実行する自動化」には本Releaseでは進まない。

---

## 1. Background

* Retry Scheduler Event Integration（v3.7.0）：`SchedulerEngine.evaluate()` /
  `run_due()`が、Job由来とRetry候補由来の`SchedulerEvent`が混在したリストを
  出力するようになった（`job_id="retry:"+run_id`という規約で区別可能）。
* Retry Engine Event Consumption（v3.8.0）：`retry_engine`パッケージに
  `RetryEventConsumer`を新設し、`RetryManager.recognize_retry_events(events)`
  経由でこの混在リストから「Retry候補由来のものだけ」を`RetryCandidateEvent`
  として認識できるようにした。ただし認識は純粋なフィルタリングであり、
  「認識した候補のうち、どれをDispatch対象として扱うか」「Event Dispatchという
  処理が何を責務とし、何を責務としないか」は一切定義されていない。
* `docs/ROADMAP.md`「v3.x 以降の候補」に、次の未着手項目として記載がある：
  「**Retry Engine Event Dispatch**：`recognize_retry_events()`（v3.8.0）が
  返した`RetryCandidateEvent`を、実際に処理すべき対象として振り分ける仕組み
  （例：優先度・件数上限に基づく選別、複数候補からの実行対象決定）。認識
  （v3.8.0）と実行（Retry Execution）の間に位置する統合ステップ」。本Releaseは
  この項目に着手するが、スコープを「Dispatch対象として扱えるようにする
  Foundationの構築」までに絞る（詳細は3章 Goals）。

```
Scheduler（判断、v2.6.0〜v3.7.0）              Retry Engine（受信・実行判断、v3.0.0〜v3.8.0）
   │                                                │
   └── evaluate() / run_due()                       ├── recognize_retry_events()（v3.8.0、認識のみ）
            │                                        │      → RetryCandidateEvent のリスト
            └── SchedulerEvent 生成                   │
                 （Job由来 ＋ Retry候補由来）           ├── retry()（Read Before Retry、無改修）
                          │                            ├── enqueue_retry() / dequeue_retry()（無改修）
                          └──── v3.8.0で認識可能 ───────┤
                                                        └──────── ★本Releaseで新設 ────────
                                                           「認識済みRetryCandidateEventを
                                                            Dispatch対象として扱えるようにする
                                                            Foundation」
                                                           （整理・振り分けのみ。実行・Queue操作は行わない）
```

---

## 2. Purpose

`retry_engine`パッケージに、`recognize_retry_events()`（v3.8.0）が返す
`RetryCandidateEvent`のリストを受け取り、それらを「Dispatch対象」として
整理・分類できるコンポーネントを新設する。あわせて、Retry Engine内において
「通常の（Retryに関係しない）イベント」と「Retryイベント」をどう振り分けるかの
方針を定義し、Event Dispatchという処理が担う責務の範囲を明確にする。

ただし、Dispatch対象として整理した結果を使って実際に`RetryManager.retry()`を
呼び出す・Retry Queueを更新する・`dequeue()` / `remove()`を呼び出すといった
**実行**は本Releaseの対象外とする。あくまで「Dispatch対象として扱えるように
する」ところまでに留める。

---

## 3. Goals

本Releaseで確立する Retry Engine Event Dispatch は、次のことだけを行う。

1. `retry_engine`パッケージに、`RetryCandidateEvent`のリストを受け取り、
   Dispatch対象として整理・分類する新規コンポーネントを追加する
   （具体的なクラス名・配置場所は8章 Open Questionsで確定する）
2. Retry Engine内での「通常イベントとRetryイベントの振り分け方針」を定義する。
   v3.8.0の`recognize_retry_events()`によるフィルタリング（Retry候補由来か
   否かの識別）を前提とし、その認識結果をさらに「Dispatch対象とするか」の
   観点で整理する関係を明文化する
3. Event Dispatchの責務を「認識済みの候補をDispatch対象として整理・分類する
   こと」に限定し、実行判断（`RetryPolicy`）・Retry実行（`RetryManager.retry()`）・
   Queue操作（`enqueue_retry()` / `dequeue_retry()` / `RetryQueueManager`の
   直接操作）とは明確に切り分ける
4. Dispatch整理処理は読み取り専用（Stateless）とし、渡された
   `RetryCandidateEvent`のリストのみから結果を導出する（独自のキャッシュ・
   保持を行わない）。`RetryManager.retry()` / `enqueue_retry()` /
   `dequeue_retry()` / `RetryQueueManager.dequeue()` / `remove()`のいずれも
   呼び出さない（構造的に到達しない設計にする）
5. `RetryManager`（既存の起動口）から、この新規コンポーネントへ薄い委譲
   メソッドで到達できるようにする（v3.8.0で`RetryEventConsumer`をDIで
   保持したのと同じパターン）が、既存の`retry()` / `enqueue_retry()` /
   `dequeue_retry()`とは呼び出しグラフ上で完全に独立させる
6. 既存の`RetryManager()` / `RetryManager.from_config()`呼び出し・
   `NullRetryManager`の動作は本Release後も無変更で動作すること
   （後方互換性維持）
7. `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
   `retry_queue`はいずれも本Releaseでも無改修（ゼロ改修）を維持する

---

## 4. Scope

### 対象

* `retry_engine`パッケージへの、`RetryCandidateEvent`を受け取りDispatch対象
  として整理する新規コンポーネントの追加
* `RetryManager`への、その新規コンポーネントを利用する薄い委譲メソッドの追加
* Retry Engine内での「通常イベント／Retryイベント」の振り分け方針の明文化
  （設計書として整理する。既存`recognize_retry_events()`との関係を含む）
* 単体テスト・E2Eテスト
  （`tests/test_e2e_v3_9_0_retry_engine_event_dispatch.py`）
* 関連ドキュメント更新（CHANGELOG / ROADMAP / architecture.md）

### 対象外（今回やらないこと）

* `RetryManager.retry()`の呼び出し（Dispatch対象に対する自動実行）
* Retry Queueの更新（`enqueue` / `dequeue` / `remove`を含むあらゆる書き込み）
* `RetryQueueManager.dequeue()`の呼び出し
* `RetryQueueManager.remove()`の呼び出し
* Queue永続化（SQLite/Redis等）
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
  `retry_queue`パッケージ自体の改修（いずれもゼロ改修を維持）
* 実運用のComposition Root（Scheduler → Retry Engineを実際につなぎ、
  Dispatch対象を継続的に処理するスクリプト）
* `job_id`予約プレフィックス（`"retry:"`）の構造的な衝突防止の仕組み化
  （v3.7.0・v3.8.0からの既知の限界を本Releaseでも引き継ぐ）
* 新しいFeature Gate環境変数の追加・Configクラスの追加・Managerパターン
  （`from_config()` / `from_env()`等の新規起動口）の採用

---

## 5. Design Principles

* **Foundation First**：認識済みの`RetryCandidateEvent`を「Dispatch対象として
  扱える」ところまでを行う。Dispatch対象を使った実行（`retry()`の自動呼び出し・
  自動Retry実行）は後続Release（Retry Execution）へ送る
* **Single Responsibility**：新規コンポーネントは「認識済みの
  `RetryCandidateEvent`をDispatch対象として整理・分類する」ことのみを担う。
  認識ロジック自体（`RetryEventConsumer`）・実行判断（`RetryPolicy` /
  `RetryManager.retry()`）・Queue管理（`retry_queue`）のいずれも複製・
  肩代わりしない
* **Stateless**：新規コンポーネントは受け取った`RetryCandidateEvent`を
  独自にキャッシュ・保持しない。呼び出しごとに渡された引数のみから結果を
  導出する純粋関数的な設計にする
* **Backward Compatibility**：`RetryManager()` / `RetryManager.from_config(...)`の
  既存呼び出し（新規引数を渡さない場合）は、本Release後も無変更で動作する。
  `NullRetryManager`にも同名の委譲メソッドを追加し、無効時は安全側
  （空リスト等）を返す

---

## 6. Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryEventConsumer`（v3.8.0、無改修） | `SchedulerEvent`のリストからRetry候補由来のものを認識する | Dispatch対象の判定・整理・実行 |
| 新規コンポーネント（本Releaseで追加、`retry_engine`配下） | 認識済みの`RetryCandidateEvent`をDispatch対象として整理・分類する | 実行判断（`RetryPolicy`）・Queue操作・Retry実行 |
| `RetryManager`（本Releaseで変更） | 新規コンポーネントへの薄い委譲窓口を持つ | Dispatchロジックの再実装／Dispatch結果の自動実行 |
| `RetryPolicy` / `RetryExecutor`（v3.0.0、無改修） | Retry可否判定・実行 | イベント認識・Dispatch |
| `RetryQueueManager`（v3.1.0、無改修） | Queueへの出し入れ・整列 | イベント認識・Dispatch |

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
  `retry_engine`パッケージ内部の`RetryCandidateEvent`（v3.8.0で新設済み）
  のみを入力とするため、`scheduler`への依存は既存（v3.8.0で確立済み）の
  ままで変化しない見込み（8章 Open Question 1で最終確定する）
* `scheduler`パッケージ側（`scheduler → retry_engine`という逆方向）は
  一切追加しない
* 循環importは発生しない

---

## 8. Open Questions（Architecture Designで確定する事項）

Project Charterの時点では確定せず、次工程のArchitecture Designで検討する。

1. **配置場所**：新規コンポーネントを`retry_engine`パッケージ内の新規ファイル
   （例：`src/retry_engine/retry_event_dispatcher.py`）に置くか、v3.3.0・v3.5.0
   の前例に倣って独立した新規パッケージに切り出すか
2. **Dispatch対象の判定基準**：v3.9.0時点で「Dispatch対象として扱う」ことの
   具体的な意味をどう定義するか。ユーザー指示の「振り分け方針を定義する」
   「責務を整理する」を踏まえ、（a）認識済みの`RetryCandidateEvent`を無条件で
   全件Dispatch対象とし型・構造だけを整理する案、（b）優先度や件数上限に
   基づく選別ロジックまで本Releaseで導入する案、のいずれを採るか
   （ROADMAP.mdの「例：優先度・件数上限に基づく選別」という記載は次の
   Retry Execution一歩手前の候補例であり、本Release単独での必須要件では
   ない点に留意する）
3. **Dispatch結果の型**：専用データクラス（例：`RetryDispatchEvent` /
   `DispatchDecision(candidate_event, dispatchable)`）を新設するか、
   `RetryCandidateEvent`をそのまま右から左へ受け渡すか（v3.7.0 Design
   Decision #3・v3.8.0の「候補オブジェクトを分解しない」方針との整合を含む）
4. **「通常イベントとRetryイベントの振り分け」の入力**：新規コンポーネントの
   入力を、v3.8.0の`recognize_retry_events()`が返した後の`RetryCandidateEvent`
   のリスト（Retry候補由来のみ、既にフィルタ済み）に限定するか、生の
   `SchedulerEvent`混在リストを受け取って「Retry候補由来かどうか」の判定と
   「Dispatch対象かどうか」の判定を新規コンポーネント内で連続して行うか
5. **`RetryManager`への委譲メソッドの粒度**：`recognize_retry_events()`と
   対になる1メソッド（例：`dispatch_retry_events(events)`）とするのか、
   複数粒度（1件判定 / 複数件判定）を用意するか
6. **新規コンポーネントの構築責務**：`RetryManager.__init__`が新規コンポーネントを
   デフォルトで自動生成する（Stateless・設定不要のため、v3.8.0の
   `RetryEventConsumer`と同じ「省略時は自動フォールバック」）か、呼び出し元が
   必ず組み立てて渡す方式にするか
7. **`NullRetryManager`側の扱い**：`NullRetryManager`にも同名の委譲メソッドを
   追加するか。追加する場合、無効時に何を返すか（空リストが妥当と想定される）

---

## 9. Acceptance Criteria

* `RetryCandidateEvent`のリストを渡した際、新規コンポーネントがDispatch対象
  としての整理結果を返すこと（具体的な形式は8章 Open Question 2・3で確定）
* 新規コンポーネント・`RetryManager`の委譲メソッドのいずれからも、
  `RetryManager.retry()`・`enqueue_retry()` / `dequeue_retry()`・
  `RetryQueueManager.dequeue()` / `remove()`へ到達する呼び出し経路が
  構造的に存在しないこと（Spyオブジェクトによる構造的確認、
  v3.3.0〜v3.8.0と同じ手法）
* 既存の`RetryManager()` / `RetryManager.from_config(...)`（新規引数を
  渡さない場合）が、本Release後も無変更で動作すること（後方互換性の回帰確認）
* `NullRetryManager`が本Release後も既存の全メソッド（本Releaseで追加する
  委譲メソッドを含む）で一貫してDISABLED相当の安全な挙動を返すこと
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
  `retry_queue`配下の全ファイルに差分がないこと（`git diff`で確認、ゼロ改修）
* E2Eテスト全PASS・既存回帰（`v2.0.0`〜`v3.8.0`）全PASS

---

## 10. Non-Goals

* `RetryManager.retry()`の呼び出し（Dispatch対象に対する自動実行・自動Retry実行）
* Retry Queueの更新（`enqueue` / `dequeue` / `remove`を含むあらゆる書き込み）
* `RetryQueueManager.dequeue()` / `remove()`の呼び出し
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
├── retry_event_consumer.py    # v3.8.0のまま、無改修
├── retry_event_dispatcher.py  # 新規：RetryCandidateEventをDispatch対象として整理
├── retry_manager.py           # 変更：新規コンポーネントへの委譲メソッド追加
└── __init__.py                 # 変更：新規シンボルのexport

案B：独立パッケージとして切り出す場合（v3.3.0 / v3.5.0の前例踏襲）
src/retry_event_dispatch/
├── retry_event_dispatcher.py   # 新規
└── __init__.py                  # 新規

src/scheduler/                 # 全ファイル無改修
src/retry_scheduler_decision/  # 全ファイル無改修
src/retry_scheduler_source/    # 全ファイル無改修
src/retry_queue/               # 全ファイル無改修

tests/
└── test_e2e_v3_9_0_retry_engine_event_dispatch.py   # 新規
```

---

## 12. Risks and Mitigations

| リスク | 対策 |
|---|---|
| 「Dispatch」という言葉が「実行開始」を連想させ、スコープが実行判断（`RetryPolicy`・`retry()`）まで広がってしまう可能性がある | Purpose・Goals・Non-Goalsで「整理・振り分けのみ、実行は行わない」ことを明記し、Acceptance CriteriaでSpyオブジェクトによる構造的な呼び出し経路の不在確認を必須とする（v3.8.0と同じ手法） |
| Dispatch対象の判定基準（Open Question 2）を安易に決めると、次Release（Retry Execution）で実行対象決定ロジックが複雑になる、または本Release自体が実質的にRetry Executionの前倒しになってしまう | Architecture Designで、次Releaseが必要とするであろう最小限の整理（型・構造の確立）に留め、優先度・件数上限等の選別ロジックを本Releaseで導入するかは慎重に判断する（8章 Open Question 2で明示的に検討） |
| 「認識」（v3.8.0）と「Dispatch」（本Release）の境界が曖昧になり、`RetryEventConsumer`と新規コンポーネントの責務が重複する | 6章Responsibilitiesで両者の責務を明確に分離し、`RetryEventConsumer`は無改修のまま維持する。新規コンポーネントの入力は`RetryEventConsumer`の出力（`RetryCandidateEvent`）を前提とする案を基本線とする（Open Question 4） |
| 「認識できるだけ／Dispatch対象として扱えるだけ」で終える本Releaseの価値が、Retry Executionを行う次Releaseまで実運用に結びつかない | v3.3.0〜v3.8.0でも同様の「消費者不在／未接続」を経て段階的に統合してきた前例がある。本Releaseも同じFoundation Firstパターンとして扱う |

---

## 13. Status

- [x] Project Charter ドラフト作成（本文書、Claude Code作成）
- [ ] ユーザー確認・フィードバック反映
- [ ] Project Charter 確定
- [ ] Architecture Design（次工程。本Releaseでは着手しない）
