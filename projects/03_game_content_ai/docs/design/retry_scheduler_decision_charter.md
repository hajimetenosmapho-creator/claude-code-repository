# Project Charter — Release 3.5「Retry Scheduler Decision」

作成日：2026-07-03
状態：ドラフト（ユーザー確認待ち）
対象：`RetrySchedulerSource`（v3.3.0）が読み取るRetry Queueの状態から、「次に処理すべき
候補」を選ぶだけの新規独立コンポーネント `RetrySchedulerDecision` を新設する。
`SchedulerEngine`（v3.4.0）・`retry_scheduler_source` / `retry_queue` / `retry_engine`
はいずれも無改修とし、Retry Engineの起動・`dequeue()`・自動実行は一切行わない。

---

## 1. Background

* Retry Scheduler Integration（v3.3.0）：`RetrySchedulerSource` /
  `NullRetrySchedulerSource` が `RetryQueueManager` の読み取り専用API
  （`list()` / `count()`）を `list_pending_retries()` / `count_pending_retries()`
  として中継するAdapterを新設した。
* Retry Scheduler Wiring（v3.4.0）：`SchedulerEngine` が `RetrySchedulerSource` /
  `NullRetrySchedulerSource` を Constructor Injection で保持できるようにし、
  `count_pending_retries()` / `list_pending_retries()` への薄い委譲メソッドを
  追加した。ただし、これは「読み取れる」状態を作っただけであり、読み取った結果を
  使って「次に何をすべきか」を判断する仕組みはまだ存在しない
  （`docs/ROADMAP.md` v3.x以降の候補、`docs/design/retry_scheduler_wiring.md`
  11章 Future Extension参照）。
* v3.4.0 Architecture Review（`docs/design/retry_scheduler_wiring.md` 16.3節）では、
  「`SchedulerEngine`に3つ目の異種責務（時刻判定・pending retry参照に続く判定/選択
  ロジック）が入る場合は責務分割を再検討する」というMinor Recommendationを残した。
  本Release（v3.5.0）はまさにその3つ目に相当するため、ユーザー確認の結果、
  `SchedulerEngine`にはこれ以上手を加えず、新規独立コンポーネントとして切り出す
  方針を確定した（2章）。
* 結果として、`RetrySchedulerSource.list_pending_retries()` が返す
  「待機中の項目一覧（priority昇順・enqueue_time昇順に整列済み）」を、
  「次に処理すべき候補」として選び出すロジックが、本Release（v3.5.0）の対象となる。

```
Scheduler（判断、v2.6.0 / v3.4.0、無改修）
   │
   ├── RetrySchedulerSource（Adapter、v3.3.0、無改修）
   │        │
   │        └── Retry Queue（v3.1.0、無改修）
   │
   └── RetrySchedulerDecision（新規、v3.5.0） ★本Release
            │  RetrySchedulerSourceを個別にConstructor Injectionで保持
            │  （SchedulerEngineへの接続は本Releaseでは行わない）
            ▼
      RetrySchedulerSource（同上への参照。SchedulerEngineとは独立した経路）
```

---

## 2. Purpose

`RetrySchedulerSource`（またはその代替）が返す待機中の項目一覧から、「次に処理すべき
候補」を選ぶだけの専用コンポーネント `RetrySchedulerDecision` を新規に追加する。

`RetryQueueManager.list()` が既に行っている整列（priority昇順・enqueue_time昇順）を
再実装・再計算することはせず、その既存順序をそのまま活用して「先頭から何件を候補と
するか」を選び出す薄い選択層とする。判定結果はあくまで「候補の提示」に留まり、
実際にQueueから取り出す（`dequeue()`）・Retry Engineへ渡して実行する、という一連の
処理は行わない。

`SchedulerEngine`（v3.4.0）には一切手を加えない。`RetrySchedulerDecision`は
`SchedulerEngine`の判定サイクルとは独立したコンポーネントとして新設し、
将来的に`SchedulerEngine`または他の呼び出し元から利用されることを想定した
「消費者不在の先行実装」とする（v3.3.0と同型のFoundation First）。

---

## 3. Goals

本Releaseで確立する Retry Scheduler Decision は、次のことだけを行う。

1. 新規独立パッケージ `src/retry_scheduler_decision/` として
   `RetrySchedulerDecision` を実装する
2. `RetrySchedulerDecision` が `RetrySchedulerSource`（またはその代替）への参照を
   Constructor Injection で保持できるようにする
3. `RetrySchedulerSource.list_pending_retries()` の戻り値順序
   （priority昇順・enqueue_time昇順）をそのまま活用し、「次に処理すべき候補」を
   選ぶロジックを追加する（新たな並べ替え・優先度計算ロジックは追加しない。
   既存順序に対する選択・抽出のみ）
4. 上記の追加によっても、`SchedulerEngine`（`src/scheduler/`配下の全ファイル）・
   `retry_scheduler_source` ・`retry_queue` ・`retry_engine` はいずれも
   本Releaseでも無改修（ゼロ改修）を維持する

---

## 4. Scope

### 対象

* 新規独立パッケージ `src/retry_scheduler_decision/` の新設
* `RetrySchedulerDecision` の `RetrySchedulerSource`（またはその代替）への
  Constructor Injection
* `RetrySchedulerSource.list_pending_retries()` の既存順序を活用した
  「次に処理すべき候補」の選択ロジック（1件 or 指定件数。具体的な出力形状は
  Architecture Designで確定する。8章 Open Questions参照）
* 単体テスト・E2Eテスト（`tests/test_e2e_v3_5_0_retry_scheduler_decision.py`）
* 関連ドキュメント更新（CHANGELOG / ROADMAP / architecture.md）

### 対象外（今回やらないこと）

* Retry Engine の起動（`RetryManager.retry()` の呼び出し）
* `RetryQueueManager.dequeue()` の呼び出し
* `RetryQueueManager.remove()` の呼び出し
* Retry Queue の更新（`enqueue` / `dequeue` / `remove` を含むあらゆる書き込み）
* 自動Retry実行（選ばれた候補を実際に再試行する仕組み）
* 永続化
* `SchedulerEngine` の改修（`src/scheduler/`配下は本Releaseでも全ファイル無改修）
* `retry_scheduler_source` / `retry_queue` / `retry_engine` の改修
  （いずれもゼロ改修を維持）
* 新しいFeature Gate環境変数の追加・Configクラスの追加・Managerパターン
  （`from_config()` / `from_env()`等の起動口）の採用（プロジェクト全体で
  一貫しているNull Object Patternに合わせる方針。v3.3.0・v3.4.0からの継続。
  10章 Non-Goals参照）

---

## 5. Design Principles

* **Foundation First**：選択ロジックの新設のみを行う。`SchedulerEngine`との実配線・
  選択結果を使った実行（自動Retry実行）は後続Releaseへ送る。v3.3.0の
  `RetrySchedulerSource`（消費者不在のまま先行実装）と同型のパターンを踏襲する
* **Single Responsibility**：`RetrySchedulerDecision`は「並んでいる候補から選ぶ」
  責務のみを持つ。Queue管理のロジック（`retry_queue`）・整列ロジック
  （`RetryQueueManager.list()`）・Adapterとしての中継（`retry_scheduler_source`）
  ・時刻ベースの判定（`SchedulerEngine`）のいずれも複製・肩代わりしない
* **Stateless**：`RetrySchedulerDecision`は選択結果・候補の状態を独自に
  保持・キャッシュしない。呼び出すたびに`RetrySchedulerSource`経由で最新状態を
  取得し、その場で選択する
* **Constructor Injection のみ**：セッターインジェクション・実行時の差し替え
  メソッド・ファクトリメソッド（`from_config()`等）は追加しない
* **Read Only**：`RetrySchedulerDecision`が呼び出すのは`RetrySchedulerSource`の
  読み取り専用メソッド（`list_pending_retries()` / 必要に応じて
  `count_pending_retries()`）のみ。Queueの状態を変更する操作には一切到達しない
* **Backward Compatibility**：`SchedulerEngine`・`retry_scheduler_source`・
  `retry_queue`・`retry_engine`のいずれも変更しないため、既存の呼び出しは
  すべて本Release前とまったく同じ結果になる

---

## 6. Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryQueueManager`（v3.1.0、無改修） | Queueへの出し入れ・整列（`list()`は既にpriority昇順・enqueue_time昇順で返す） | 候補選択・実行判断 |
| `RetrySchedulerSource` / `NullRetrySchedulerSource`（v3.3.0、無改修） | Retry Queueの状態の読み取り専用な中継 | 候補選択ロジック・実行判断 |
| `RetrySchedulerDecision`（本Releaseで新設） | `RetrySchedulerSource`が返す既存順序から「次に処理すべき候補」を選ぶ | 整列・並べ替えの再計算／Queueからの取り出し（`dequeue`）／実行判断の確定／実行／`SchedulerEngine`との接続 |
| `SchedulerEngine`（v3.4.0、無改修） | 時刻ベースの判定・pending retryの件数/一覧の読み取り委譲 | 候補選択（本Releaseでは関与しない） |

---

## 7. Dependencies

```
retry_scheduler_decision ──→ retry_scheduler_source（公開APIのみ：
                              RetrySchedulerSource / NullRetrySchedulerSource /
                              list_pending_retries() / count_pending_retries()）
retry_scheduler_source   ──→ retry_queue（v3.3.0のまま、無改修）
scheduler                ──→ （本Releaseでは retry_scheduler_decision を含め、
                              何も追加しない。retry_scheduler_decisionからも
                              schedulerは一切importしない）
retry_engine              ──→ （本Releaseでは一切関与しない）
```

* 新規に追加される依存方向は `retry_scheduler_decision → retry_scheduler_source`
  の一方向のみ
* `retry_scheduler_decision` は `scheduler` を一切importしない（逆方向依存なし）
* `scheduler` は本Releaseでも `retry_scheduler_decision` を一切importしない
  （本Releaseでは接続しない）
* 循環importは発生しない

---

## 8. Open Questions（Architecture Designで確定する事項）

Project Charterの時点では確定せず、次工程のArchitecture Designで検討する。

1. **Constructor Injectionの引数型**：`RetrySchedulerSource`実体のみを受け取るか
   （v3.3.0の`RetrySchedulerSource.__init__`と同じ narrowing）、
   `RetrySchedulerSource | NullRetrySchedulerSource`のUnion型で受け取るか
   （v3.4.0の`SchedulerEngine.__init__`と同じ形）
2. **Null Object Patternの要否**：`RetrySchedulerDecision`自体に
   `NullRetrySchedulerDecision`のようなダミー実装を用意するか、それとも
   「消費者不在の先行実装」である本Release単体では不要と判断するか
3. **候補選択の出力形状**：単一候補（先頭1件）を返すメソッドとするか、
   複数候補（`limit`件）を返すメソッドとするか、あるいは「選択結果＋理由」を
   表す専用データクラス（例：`RetrySchedulerDecisionResult`）を新設するか
4. **メソッド名**：`select_next_candidate()` / `select_candidates(limit)` 等、
   具体的なAPI名称の確定

---

## 9. Acceptance Criteria

* `RetrySchedulerDecision`が`RetrySchedulerSource`の`list_pending_retries()`
  （必要に応じて`count_pending_retries()`）以外のメソッドを一切呼び出さないこと
  （構造的確認。Spyオブジェクトによりv3.3.0・v3.4.0と同じ手法で検証）
* `RetrySchedulerDecision`が`RetryQueueManager.dequeue()` / `remove()`へ到達する
  呼び出し経路が構造的に存在しないこと
* `RetrySchedulerDecision`の候補選択ロジックが、`RetrySchedulerSource`の
  戻り値順序を変更しない（独自の並べ替えを行わない）こと
* `src/scheduler/`配下の全ファイルに差分がないこと（`git diff`で確認、ゼロ改修）
* `src/retry_scheduler_source/` / `src/retry_queue/` / `src/retry_engine/`配下の
  全ファイルに差分がないこと（ゼロ改修）
* 本Releaseでは`RetrySchedulerDecision`をどのパッケージからも呼び出さないこと
  （`src/scheduler/`を含む既存の全ファイルが`retry_scheduler_decision`を
  参照していないことの確認。消費者不在の先行実装であることの確認）
* `retry_scheduler_decision`配下に`Config`を名前に含むクラス・`enabled`
  フィールドを持つクラスが存在しないこと（Feature Gate / Configクラスを
  追加していないことの確認）
* E2Eテスト全PASS・既存回帰（`v2.0.0`〜`v3.4.0`）全PASS

---

## 10. Non-Goals

* Retry Engine（`RetryManager`）の起動・呼び出し
* `RetryQueueManager.dequeue()` / `remove()` の呼び出し
* 選ばれた候補を実際に再試行すること（自動Retry実行）
* Retry Queueの永続化
* `SchedulerEngine`（`src/scheduler/`配下）の改修
* `retry_scheduler_source` / `retry_queue` / `retry_engine`パッケージ自体の
  変更（いずれもゼロ改修を維持）
* 新しいFeature Gate環境変数の追加
* Configクラスの追加
* Managerパターン（`from_config()` / `from_env()`等の起動口）の採用

---

## 11. Directory Structure（想定）

```text
src/retry_scheduler_decision/
├── __init__.py
└── retry_scheduler_decision.py   # RetrySchedulerDecision（Null Object Patternの
                                   # 要否は8章Open Question。Architecture Designで確定）

src/scheduler/               # 全ファイル無改修
src/retry_scheduler_source/  # 全ファイル無改修
src/retry_queue/             # 全ファイル無改修
src/retry_engine/            # 全ファイル無改修

tests/
└── test_e2e_v3_5_0_retry_scheduler_decision.py   # 新規
```

---

## 12. Risks and Mitigations

| リスク | 対策 |
|---|---|
| 選択ロジックのAPI形状（8章Open Question 3・4）が、将来`SchedulerEngine`との実配線時に不適合であることが判明し、シグネチャ調整が必要になる | v3.3.0・v3.4.0でも同種の懸念を許容してきた（Foundation Firstの性質上、消費者が現れるまで完全な適合性は保証できない）。次Release（実配線）で軽微な調整を許容する方針とする |
| `RetrySchedulerDecision`が誤って`dequeue()`を呼び出し、選んだだけのつもりが実際にQueueから取り出してしまう | Acceptance Criteria（9章）にSpyオブジェクトによる構造的確認を明記し、Test工程で検証する |
| Null Object Patternの要否（8章Open Question 2）が定まらないまま実装に進み、プロジェクト全体の設計言語との整合性が崩れる | Architecture Designで先に確定させ、ユーザー確認を得てから実装に進む |
| `SchedulerEngine`を一切変更しないことで、「候補選択」機能が実際に使われる見通しが本Release単体では立たない | v3.3.0の`RetrySchedulerSource`も同様に消費者不在で先行リリースされ、v3.4.0で接続された前例がある。本Releaseも同じ「Foundation First」パターンとして扱い、次Release以降で`SchedulerEngine`または他の呼び出し元との接続を検討する |

---

## 13. Status

- [x] Project Charter ドラフト作成（本文書、Claude Code作成）
- [ ] ユーザー確認・フィードバック反映
- [ ] Project Charter 確定
- [ ] Architecture Design（次工程。本Releaseでは着手しない）
