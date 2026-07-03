# Project Charter — Release 3.3「Retry Scheduler Integration」

作成日：2026-07-03（Null Object Pattern反映：2026-07-03）
状態：承認済み（ユーザー確定、2026-07-03）。Architecture Review完了
（`docs/design/retry_scheduler_integration.md` 13章、Approve with Minor
Recommendations）。
対象：Scheduler が Retry Queue の状態（待機中の項目の有無・件数）を、新規Adapter
パッケージ `RetrySchedulerSource` を介して読み取れるようにする最小統合。
Scheduler は Retry Queue を直接参照しない。Queueからの取り出し（dequeue）・
自動Retry実行・Retry Engineとの連携は行わない。

---

## 1. Background

* Retry Queue Foundation（v3.1.0）：`enqueue` / `dequeue` / `remove` / `list` /
  `exists` / `count` の6操作のみを提供するQueue管理層。標準ライブラリのみに依存する
  独立した葉パッケージ。
* Retry Queue Integration（v3.2.0）：`RetryManager`（retry_engine）が
  `RetryQueueManager` への参照を持ち、`enqueue_retry()` / `dequeue_retry()` で
  薄い委譲を行うようになった。ただし、Queueに項目を投入する主体・Queueを定期的に
  監視する主体は、v3.2.0時点でもまだ存在しない。
* Scheduler Agent Foundation（v2.6.0）：`SchedulerEngine.evaluate(jobs, now)` が
  時刻ベースの判定のみを行い、`SchedulerEvent` を生成する。Retry Queueの存在を
  一切知らない。
* 結果として、「Queueに再実行待ちの項目が溜まっている」という状態を、定期的に
  確認する仕組みがどこにも存在しない。本Release（v3.3.0）は、この「誰も見ていない」
  というギャップを埋める。

* **ユーザーフィードバック（2026-07-03）を反映し、当初案から以下を確定した**：
  1. Scheduler が `RetryQueueManager` を直接保持する構成ではなく、新規独立パッケージ
     `RetrySchedulerSource` を挟む構成とする（依存の逆転を避け・将来の自動Retry実行
     への拡張性を優先）
  2. `dequeue()` / `remove()` は完全に対象外とし、`list()` / `count()`（非破壊の
     読み取り専用API）のみを使用する
  3. `SchedulerEngine` を含む既存Scheduler本体（`SchedulerEngine` /
     `SchedulerManager` / `SchedulerJob` / `SchedulerEvent`）は無改修とし、
     Queue監視機能は新規パッケージへ完全に切り出す
  4. 新しいFeature Gate・Configクラス・Managerパターン（`from_config()`等の
     起動口）は追加しない。かわりに、プロジェクト全体で一貫している
     Null Object Pattern（継承なしのDuck Typingペア）を採用し、
     `RetrySchedulerSource`（実装クラス）／`NullRetrySchedulerSource`
     （ダミー実装）の2クラス構成とする。有効・無効は呼び出し元がどちらの
     クラスを構築するかによって決まる
  5. `RetrySchedulerSource` のコンストラクタは Constructor Injection のみとし、
     セッターインジェクション・ファクトリメソッドは持たない
  6. 本Releaseでは `RetrySchedulerSource` / `NullRetrySchedulerSource` を
     どこからも呼び出さない（v2.9.0 WorkflowMonitorManager・v3.1.0
     RetryQueueと同じ「将来接続のためのFoundationを先行実装する」Releaseとして
     扱う）

```
Scheduler（判断、v2.6.0、無改修）
   │
   │  ※本Releaseでは未接続（Foundation First。4章参照）
   ▼
RetrySchedulerSource（新規Adapter、v3.3.0） ★本Release
   │
   └──→ Retry Queue（Queue管理、v3.1.0、無改修）
```

---

## 2. Purpose

Retry Queue の状態を読み取るための専用Adapter `RetrySchedulerSource` を新規に
追加する。Scheduler が将来この Adapter を通じて「再実行待ちの項目がある」ことを
把握できるようにするための土台を作る。

Adapterを挟む理由は、Scheduler本体が `RetryQueueManager` の内部API（Queueの
データ構造・操作方法）を直接知る必要をなくし、将来 Retry Queue 側のAPIが変わっても
Scheduler本体に影響が及ばないようにするためである。同時に、将来「自動Retry実行」を
実装する際にも、`RetrySchedulerSource` がその窓口として自然に拡張できる設計とする。

ただし本Releaseは Foundation の延長であり、**Adapterの新設と読み取り機能の実装
だけ**を行う。Scheduler本体からの実際の呼び出し配線、Queueから取り出した項目を
実際に再実行する処理は、次のRelease以降に送る。

---

## 3. Goals

本Releaseで確立する Retry Scheduler Integration は、次のことだけを行う。

1. 新規独立パッケージ `src/retry_scheduler_source/` として `RetrySchedulerSource`
   を実装する
2. `RetrySchedulerSource` が `RetryQueueManager`（実体）を Constructor Injection
   で保持できるようにする。無効化したい場合は呼び出し元が `NullRetrySchedulerSource`
   を選択する（プロジェクト全体で一貫しているNull Object Patternに合わせる）
3. `RetrySchedulerSource` に、Retry Queueの状態（待機中の項目一覧・件数）を、
   既存の読み取り専用API（`RetryQueueManager.list()` / `count()`）を通じて取得する
   メソッドを追加する（委譲のみ。判定・加工は行わない）
4. 上記の追加によっても、`src/scheduler/` 配下の既存ファイル（`SchedulerEngine` /
   `SchedulerJob` / `SchedulerEvent` / `SchedulerRepository` / `SchedulerManager` /
   `SchedulerConfig`）および `src/retry_queue/` 配下の既存ファイルを一切変更しない
   （後方互換性の維持・ゼロ改修）

---

## 4. Scope

### 実装対象

新規独立パッケージ `src/retry_scheduler_source/` として、以下を実装する。

* **RetrySchedulerSource**：`RetryQueueManager`（実体）への参照をDIで保持し、
  `list()` / `count()` への薄い委譲のみを行うAdapter。Queueの内部構造
  （容量・重複チェック・優先度ソート）には一切関与しない
* **NullRetrySchedulerSource**：`RetrySchedulerSource` のダミー実装（Null Object）。
  `retry_queue` への参照を一切保持せず、常に空リスト・0件を返す。プロジェクト全体で
  一貫しているNull Object Pattern（`RetryManager`/`NullRetryManager`、
  `RetryQueueManager`/`NullRetryQueueManager` 等）にAdapter層でも合わせるための
  ものであり、Feature Gate・Configクラスは伴わない（5章）
* コンストラクタはDIのみとする（Configからの再構築は行わない。
  `RetryManager.from_config()` が `WorkflowEngineManager` をDIで受け取る設計
  ─ retry_engine_foundation.md 10章 Design Decision #3 ─ と同じ考え方）
* 単体テスト・E2Eテスト（`tests/test_e2e_v3_3_0_retry_scheduler_integration.py`）
* 関連ドキュメント更新（CHANGELOG / ROADMAP / architecture.md）

### 対象外

* `retry_queue` パッケージ（`src/retry_queue/` 配下の全ファイル）の改修
  （ゼロ改修を維持）
* `retry_engine` パッケージ（`src/retry_engine/` 配下の全ファイル）の改修
  （ゼロ改修を維持。本Releaseでは一切参照しない）
* `scheduler` パッケージ（`src/scheduler/` 配下の全ファイル）の改修
  （ゼロ改修を維持。`RetrySchedulerSource` から `SchedulerEngine` 等への呼び出し
  配線も本Releaseでは行わない）
* `RetryQueueManager.dequeue()` / `remove()` の呼び出し（状態を変更するAPIは
  一切使用しない）
* Queueから取り出した項目を自動的に再実行する仕組み（自動Retry実行）
* Scheduler の判定サイクル（`evaluate()` / `run_due()`）へ `RetrySchedulerSource`
  を組み込む統合配線（将来Release）
* 新しいFeature Gate環境変数の追加（5章参照。既存の `RETRY_QUEUE_ENABLED` に
  すべて委ねる）
* Queueの永続化
* 優先度付けアルゴリズムの高度化
* Windows タスクスケジューラ等の外部スケジューラ連携
* CLIエントリスクリプト

---

## 5. Design Principles

* **Adapter / Bridge**：`RetrySchedulerSource` は Scheduler と Retry Queue の間に
  立つ変換層であり、Scheduler側は `RetryQueueManager` の存在を意識しない
  （将来 `retry_queue` 側のAPIが変化しても、影響は `RetrySchedulerSource` の内部に
  閉じる）
* **Foundation First**：Adapterの新設と読み取り機能のみを先に確立する。Scheduler
  本体との実配線・自動実行は後続Releaseへ送る（v2.9.0のWorkflowMonitorManager・
  v3.1.0のRetryQueueと同じ「消費者不在のまま先行実装する」パターンを踏襲）
* **Single Responsibility**：Queue管理のロジック（容量チェック・重複チェック・
  優先度ソート）は `retry_queue` 側に残したまま、`RetrySchedulerSource` には一切
  複製しない。`RetrySchedulerSource` は「Queueの状態を読み取って伝える」責務のみを
  持つ
* **Read Only**：本Releaseでは非破壊の読み取り専用API（`list()` / `count()`）のみを
  使用し、Queueの状態を変更する `dequeue()` / `remove()` は一切呼び出さない
* **Stateless**：`RetrySchedulerSource` はQueueの中身を独自に保持・キャッシュしない。
  Queueの状態のSingle Source of Truthは引き続き `RetryQueueManager` である
* **Null Object Pattern（Feature Gate / Config / Managerパターンは採用しない）**：
  `RetrySchedulerSource` 自体は `enabled` フラグ・Configクラス・
  `from_config()` のような起動口を持たない。プロジェクト全体で一貫している
  Null Object Pattern（`RetryManager`/`NullRetryManager`、`RetryQueueManager`/
  `NullRetryQueueManager` 等、継承なしのDuck Typingペア）に合わせ、
  `RetrySchedulerSource`（実装クラス）／`NullRetrySchedulerSource`（ダミー実装）
  の2クラス構成とする。有効・無効は、呼び出し元がどちらのクラスを構築するかで
  決まり、本パッケージ自身は判定ロジックを一切持たない
* **Constructor Injection のみ**：`RetrySchedulerSource` は `RetryQueueManager`
  をコンストラクタ引数として受け取るのみとし、セッターインジェクション・
  Configからの再構築・ファクトリメソッド（`from_config()` 等）は用意しない
* **既存モジュールの責務変更や依存関係の逆転を避ける**：`scheduler` / `retry_queue` /
  `retry_engine` / `workflow_engine` / `workflow_monitor` / `execution_history` は
  いずれも無改修とする。依存方向は `retry_scheduler_source → retry_queue` の
  一方向のみとし、`retry_queue` が `retry_scheduler_source` を参照することはない
* **後方互換性を維持する**：既存パッケージへの変更が一切ないため、既存の呼び出しは
  すべて本Release前とまったく同じ結果になる

---

## 6. Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryQueueManager`（v3.1.0、無改修） | Queueへの出し入れ（登録・取り出し・削除・一覧・存在確認・件数）そのもの | Scheduler向けの変換・整形 |
| `RetrySchedulerSource`（本Releaseで新設） | `RetryQueueManager` への参照を保持し、`list()` / `count()` の呼び出しをそのまま中継する | Queue内部の判定ロジックの実装・Queueからの取り出し（`dequeue`）・実行判断・実行・有効/無効の自己判定 |
| `NullRetrySchedulerSource`（本Releaseで新設） | `RetrySchedulerSource` のダミー実装。常に空リスト・0件を返す | `retry_queue` への参照の保持・Queueとの通信 |
| `SchedulerEngine`（無改修） | 時刻とJob一覧から実行対象を判定するエンジン | Retry Queueの状態把握（本Releaseでは関与しない） |

---

## 7. Dependencies

```
retry_scheduler_source ──→ retry_queue（公開APIのみ：RetryQueueManager /
                            RetryQueueItem / list() / count()）
    ※ NullRetrySchedulerSource は retry_queue を一切importしない

retry_queue  ──→ （なし。標準ライブラリのみ、無改修）
scheduler    ──→ （本Releaseでは retry_scheduler_source を含め、何も追加しない）
retry_engine ──→ （本Releaseでは一切関与しない）
```

* `retry_queue` は本Releaseでも他パッケージを一切importしない（無改修のまま）
* `retry_scheduler_source` は `retry_queue` の公開シンボル（`__init__.py` の
  `__all__`）のみをimportする
* `scheduler` パッケージは本Releaseでは `retry_scheduler_source` を一切importしない
  （Scheduler本体からの呼び出し配線は将来Release）
* 循環importは発生しない

---

## 8. Non-Goals

* Scheduler の判定サイクル（`SchedulerEngine.evaluate()` / `run_due()`）に
  `RetrySchedulerSource` を組み込むこと（本Releaseでは配線しない）
* Queueから取り出した項目を再実行すること（自動実行）
* `RetryQueueManager.dequeue()` / `remove()` の呼び出し
* `retry_engine` との連携（本Releaseでは一切触れない）
* Queueの永続化（プロセス再起動をまたぐ保持）
* `retry_queue` / `scheduler` パッケージ自体の変更（いずれもゼロ改修を維持）
* 新しいFeature Gate環境変数の追加
* Configクラスの追加（`RetrySchedulerSourceConfig` 等）
* Managerパターン（`from_config()` / `from_env()` 等の起動口）の採用

---

## 9. Acceptance Criteria

* `RetrySchedulerSource` が `RetryQueueManager.dequeue()` / `remove()` を一切
  呼び出さないこと（読み取り専用であることの構造的確認）
* `RetrySchedulerSource` が `list()` / `count()` の戻り値をそのまま返し、加工しない
  こと
* `NullRetrySchedulerSource.list_pending_retries()` が常に `[]`、
  `count_pending_retries()` が常に `0` を返すこと。かつ `retry_queue` の
  いかなるシンボルもimport・参照していないこと（`retry_queue` への依存が
  ゼロであることの構造的確認）
* `RetrySchedulerSource` / `NullRetrySchedulerSource` のいずれも
  `from_config()` / `from_env()` 等のファクトリメソッドを持たないこと
  （Constructor Injectionのみであることの確認）
* `src/retry_scheduler_source/` 配下に `Config` を名前に含むクラス・
  `enabled` フィールドを持つクラスが存在しないこと（Feature Gate / Config
  クラスを追加していないことの確認）
* `src/scheduler/` 配下の全ファイルに差分がないこと（`git diff` で確認、ゼロ改修）
* `src/retry_queue/` 配下の全ファイルに差分がないこと（ゼロ改修）
* `src/retry_engine/` 配下の全ファイルに差分がないこと（本Releaseでは無関係のため
  ゼロ改修）
* `RetrySchedulerSource` / `NullRetrySchedulerSource` に `RETRY_ENGINE_ENABLED`
  等の既存Feature Gate環境変数、および本Release独自の新規Feature Gate環境変数の
  いずれも参照するコードが存在しないこと
* 既存の `SchedulerEngine.evaluate()` / `SchedulerManager` の呼び出しが、本Release
  前とまったく同じ結果を返すこと（回帰テストで確認）
* E2Eテスト全PASS・既存回帰（`v2.0.0`〜`v3.2.0`）全PASS

---

## 10. Directory Structure（想定）

```text
src/retry_scheduler_source/
├── __init__.py
└── retry_scheduler_source.py   # RetrySchedulerSource / NullRetrySchedulerSource
                                 # （同一ファイルに同居。RetryManager/
                                 #   NullRetryManagerと同じ構成）

src/scheduler/    # 全ファイル無改修
src/retry_queue/  # 全ファイル無改修
src/retry_engine/ # 全ファイル無改修

tests/
└── test_e2e_v3_3_0_retry_scheduler_integration.py   # 新規
```

Configファイル（例：`retry_scheduler_source_config.py`）は作らない。
Feature Gate・Configクラスを持たない方針（5章）のため、既存パッケージ
（`retry_queue` 6ファイル、`retry_engine` 6ファイル）と比べて最小の
2ファイル構成となる。

---

## 11. Risks and Mitigations

| リスク | 対策 |
|---|---|
| `RetrySchedulerSource` が誤って `dequeue()` / `remove()` を呼び出し、Queueの状態を意図せず変更してしまう | Architecture Guard（静的検査・単体テスト）で、`RetrySchedulerSource` が `RetryQueueManager` の `list` / `count` 以外のメソッドを一切呼ばないことを確認する（9章） |
| `RetrySchedulerSource` が `retry_queue` の非公開実装に依存し、将来 `retry_queue` 側の内部変更で壊れる | `retry_queue` の `__init__.py` が公開する `__all__` のシンボルのみをimportする |
| Adapterを挟んだことで「誰も呼んでいないコード」が増え、Foundation First の名目で放置される懸念 | v2.9.0 / v3.1.0 と同じ「消費者不在の先行実装」パターンであることを明記し、次のRelease（Scheduler本体との実配線）を ROADMAP の候補として明示的に記録する |
| Feature Gate / Configクラスを追加しないことで、有効/無効の切り替え判断がどこにも定義されず、将来の呼び出し元が誤って常に `RetrySchedulerSource`（実体）を使ってしまう | 「どちらのクラスを構築するか」の判定は本Releaseでは意図的に呼び出し元へ委ね、Future Extension（Architecture Design 11章）として次のRelease（Scheduler本体との実配線）で確定する方針を明記する。本Releaseでは読み取り専用APIの呼び出しのみで外部副作用がないため、誤操作時の実害は小さい |
| `RetrySchedulerSource` を実体のみ受け取る設計にしたことで、無効化したい場合に `NullRetryQueueManager` を渡すという直感的な選択肢が使えなくなる | `NullRetrySchedulerSource` を独立クラスとして用意し、「無効化＝`NullRetrySchedulerSource()`を構築する」という単一の手段に統一する（Architecture Design 2章）ことで、無効化の表現方法が2通り存在する曖昧さを排除する |

---

## 12. Status

- [x] Project Charter ドラフト作成（初版）
- [x] ユーザーフィードバック反映（Adapter構成・list/count限定・SchedulerEngine無改修・Feature Gate追加なし）
- [x] Project Charter 確定（本ドキュメント、ユーザー承認済み、2026-07-03）
- [x] Architecture Design（`docs/design/retry_scheduler_integration.md`、ドラフト作成済み）
- [x] ユーザーフィードバック反映（Null Object Pattern・Constructor Injection・
      Config/Managerパターン不使用への統一。Charter本文に反映済み、2026-07-03）
- [x] Architecture Review完了（Approve with Minor Recommendations、
      `docs/design/retry_scheduler_integration.md` 13章参照）
- [ ] 実装開始（ユーザー確認待ち）
