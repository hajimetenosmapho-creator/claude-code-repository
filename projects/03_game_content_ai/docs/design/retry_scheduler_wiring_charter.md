# Project Charter — Release 3.4「Retry Scheduler Wiring」

作成日：2026-07-03
状態：ドラフト（ユーザー確認待ち）
対象：v3.3.0で新設した `RetrySchedulerSource` / `NullRetrySchedulerSource` を、
Scheduler（`src/scheduler/`）へ Constructor Injection で接続し、Scheduler の
判定サイクルが Retry Queue の状態を参照できる状態にする最小Wiring。
Retry Engine の起動・`dequeue()`・Retry Queueの更新・自動Retry実行・永続化は
一切行わない。

---

## 1. Background

* Retry Queue Foundation（v3.1.0）：`enqueue` / `dequeue` / `remove` / `list` /
  `exists` / `count` の6操作のみを提供するQueue管理層。
* Retry Queue Integration（v3.2.0）：`RetryManager`（retry_engine）が
  `RetryQueueManager` への参照を持ち、`enqueue_retry()` / `dequeue_retry()` で
  薄い委譲を行うようになった。
* Retry Scheduler Integration（v3.3.0）：新規独立パッケージ
  `src/retry_scheduler_source/` に `RetrySchedulerSource` /
  `NullRetrySchedulerSource` を実装した。`RetryQueueManager` の読み取り専用API
  （`list()` / `count()`）への薄い委譲のみを行うAdapterであり、
  `SchedulerEngine` を含む `src/scheduler/` 配下は無改修のまま据え置いた
  （Foundation First。「消費者不在の先行実装」）。
* 結果として、v3.3.0時点では `RetrySchedulerSource` /
  `NullRetrySchedulerSource` はどこからも呼び出されておらず、Scheduler は
  Retry Queue の状態を一切参照できない状態にある
  （`docs/ROADMAP.md` v3.x以降の候補、および
  `docs/design/retry_scheduler_integration.md` 11章 Future Extension参照）。
* 本Release（v3.4.0）は、この「作ったが繋がっていない」ギャップのうち、
  **接続の土台（Wiring）** だけを埋める。実際に接続した先で何をするか
  （自動Retry実行等）は次のRelease以降に送る。

```
Scheduler（判断、v2.6.0）
   │
   │  ★本Releaseで接続する
   ▼
RetrySchedulerSource / NullRetrySchedulerSource（Adapter、v3.3.0、無改修）
   │
   └──→ Retry Queue（Queue管理、v3.1.0、無改修）
```

---

## 2. Purpose

Scheduler が `RetrySchedulerSource`（またはその代替として
`NullRetrySchedulerSource`）を Constructor Injection で保持できるようにし、
Scheduler の判定サイクル（`SchedulerEngine.evaluate()` / `run_due()`）が
Retry Queue の状態（待機中の項目の有無・件数）を参照できる状態を作る。

本Releaseは接続経路（Wiring）の確立のみを目的とし、参照した情報を使って
実際に何かを実行する（Retry Engineの起動・自動再実行）ことは目的としない。
v2.9.0の `WorkflowMonitorManager` DI・v3.1.0の Retry Queue・v3.3.0の
`RetrySchedulerSource` と同じ「Foundation First」の考え方を踏襲する。

---

## 3. Goals

本Releaseで確立する Retry Scheduler Wiring は、次のことだけを行う。

1. Scheduler側（`src/scheduler/` 配下のいずれかのコンポーネント）が
   `RetrySchedulerSource` / `NullRetrySchedulerSource` への参照を
   Constructor Injection で保持できるようにする
2. `RetrySchedulerSource` / `NullRetrySchedulerSource` の生成方法（どちらを
   構築するか、どのタイミングで `RetryQueueManager` の実体を渡すか）を設計する
3. `RetryQueueManager`（v3.1.0）を安全にDIできる経路を確立する
   （Scheduler → RetrySchedulerSource → RetryQueueManager の一方向の
   参照のみ。逆方向の参照・循環参照は作らない）
4. Scheduler の判定サイクル（`evaluate()` / `run_due()`、または新設する
   薄いラッパー）が `RetrySchedulerSource.count_pending_retries()` /
   `list_pending_retries()` を呼び出せる状態にする（読み取りのみ）
5. 上記の追加によっても、`retry_scheduler_source` / `retry_queue` /
   `retry_engine` 配下の既存ファイルを一切変更しない（後方互換性の維持・
   ゼロ改修）

---

## 4. Scope

### 対象

* `src/scheduler/` 配下への `RetrySchedulerSource` /
  `NullRetrySchedulerSource` の Constructor Injection
  （対象クラス・具体的な組み込み方法はArchitecture Designで確定する。
  8章 Open Questions参照）
* `RetrySchedulerSource` / `NullRetrySchedulerSource` の生成方法の設計
  （呼び出し元がどちらを構築するかの判断をどこに置くか）
* `RetryQueueManager` の安全なDI（`RetrySchedulerSource` 経由での間接参照。
  Scheduler が `RetryQueueManager` を直接保持することはしない。v3.3.0の
  Adapter構成を維持する）
* Scheduler の判定サイクルへの `RetrySchedulerSource` の組み込み
  （判定結果への反映方法はArchitecture Designで確定する）
* 単体テスト・E2Eテスト（`tests/test_e2e_v3_4_0_retry_scheduler_wiring.py`）
* 関連ドキュメント更新（CHANGELOG / ROADMAP / architecture.md）

### 対象外（今回やらないこと）

* Retry Engine の起動（`RetryManager.retry()` の呼び出し）
* `RetryQueueManager.dequeue()` の呼び出し
* Retry Queue の更新（`enqueue` / `dequeue` / `remove` を含むあらゆる書き込み）
* Retry の自動実行（検知した待機項目を実際に再試行する仕組み）
* Queueの永続化
* 新しいFeature Gate環境変数の追加
* Configクラスの追加（`SchedulerRetrySourceConfig` 等）
* Managerパターンの追加（`from_config()` / `from_env()` 等の新規起動口）
* `src/retry_scheduler_source/` / `src/retry_queue/` / `src/retry_engine/`
  配下の全ファイルの改修（いずれもゼロ改修を維持）
* `SchedulerEngine.evaluate()` の判定ロジック（DAILY/INTERVAL/ONCEの
  マッチング処理）自体の変更

---

## 5. Design Principles

* **Foundation First**：接続経路（Wiring）の確立のみを行う。接続した先で
  何を実行するか（自動Retry実行等）は後続Releaseへ送る
* **Single Responsibility**：Scheduler は「Retry Queueの状態を読み取れる」
  ようになるだけであり、Retry Queueの中身をどう扱うか（実行判断・実行）の
  責務は持たない
* **Stateless**：Scheduler側もRetry Queueの状態を独自に保持・キャッシュ
  しない。参照するたびに `RetrySchedulerSource` 経由で最新状態を取得する
* **Constructor Injection のみ**：セッターインジェクション・実行時の
  差し替えメソッド・ファクトリメソッド（`from_config()` 等）は追加しない
* **Read Only Adapter**：v3.3.0で確立した「読み取り専用」の性質を維持する。
  本Releaseで新たに書き込み系API（`dequeue()` / `remove()`）を呼び出す
  経路は一切作らない
* **Backward Compatibility**：既存の `SchedulerEngine.evaluate()` /
  `run_due()` の呼び出し（`RetrySchedulerSource` を渡さない場合）は、
  本Release前とまったく同じ結果を返す
* **Small Release**：Wiring（接続）とその生成方法の設計のみに範囲を限定し、
  実行判断・実行ロジックには踏み込まない

---

## 6. Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryQueueManager`（v3.1.0、無改修） | Queueへの出し入れそのもの | Scheduler向けの変換・整形 |
| `RetrySchedulerSource` / `NullRetrySchedulerSource`（v3.3.0、無改修） | Retry Queueの状態の読み取り専用な中継 | 実行判断・実行・Scheduler側への組み込み方法の決定 |
| Scheduler側（本Releaseで変更）| `RetrySchedulerSource` を保持し、判定サイクルから参照できるようにする | Retry Queueの状態を使って実際に何かを実行すること（次Release以降） |

---

## 7. Dependencies

```
scheduler              ──→ retry_scheduler_source（公開APIのみ：
                            RetrySchedulerSource / NullRetrySchedulerSource /
                            list_pending_retries() / count_pending_retries()）
retry_scheduler_source ──→ retry_queue（v3.3.0のまま、無改修）
retry_queue             ──→ （なし。標準ライブラリのみ、無改修）
retry_engine            ──→ （本Releaseでは一切関与しない）
```

* 新規に追加される依存方向は `scheduler → retry_scheduler_source` の
  一方向のみ
* `retry_scheduler_source` は本Releaseでも `scheduler` を一切importしない
  （逆方向の依存を作らない）
* 循環importは発生しない

---

## 8. Open Questions（Architecture Designで確定する事項）

Project Charterの時点では確定せず、次工程のArchitecture Designで検討する。

1. Constructor Injectionの受け口をどこに置くか
   （`SchedulerEngine` に直接持たせるか、`SchedulerManager` に持たせるか、
   両者と別の新規の薄いラッパーを設けるか）
2. 判定サイクルへの組み込み方法
   （`SchedulerEvent` に情報を追加するのか、`evaluate()` とは別の新規
   読み取り専用メソッドを追加するのか）
3. `RetrySchedulerSource`（実体）と `NullRetrySchedulerSource` のどちらを
   構築するかの判断をどこに置くか（呼び出し元に委ねる方針は v3.3.0から
   維持するが、具体的な呼び出し箇所は未定）
4. 既存の `SchedulerConfig` との関係（Configクラスは追加しない方針だが、
   既存 `SchedulerConfig` へのフィールド追加が必要かどうかは、Goal 5
   「既存ファイル無改修」との整合を含めてArchitecture Designで判断する）

---

## 9. Non-Goals

* Retry Engine（`RetryManager`）の起動・呼び出し
* `RetryQueueManager.dequeue()` / `remove()` の呼び出し
* Queueから取り出した項目を再実行すること（自動Retry実行）
* Retry Queueの永続化
* 新しいFeature Gate環境変数の追加
* Configクラスの追加
* Managerパターン（`from_config()` / `from_env()` 等の起動口）の採用
* `retry_scheduler_source` / `retry_queue` / `retry_engine` パッケージ自体の
  変更（いずれもゼロ改修を維持）

---

## 10. Acceptance Criteria

* Scheduler側が `RetrySchedulerSource` / `NullRetrySchedulerSource` を
  Constructor Injectionで受け取れること
* Scheduler側から `RetryQueueManager.dequeue()` / `remove()` へ到達する
  呼び出し経路が一切存在しないこと（構造的確認）
* `RetrySchedulerSource` / `retry_scheduler_source` / `retry_queue` /
  `retry_engine` 配下の全ファイルに差分がないこと（`git diff` で確認、
  ゼロ改修）
* Scheduler に `RetrySchedulerSource` を渡さない（または
  `NullRetrySchedulerSource` を渡す）場合、既存の `evaluate()` /
  `run_due()` の呼び出し結果が本Release前とまったく同じであること
  （回帰テストで確認）
* Scheduler / `retry_scheduler_source` 配下に `Config` を名前に含む新規
  クラス・`enabled` フィールドを持つ新規クラスが存在しないこと
* E2Eテスト全PASS・既存回帰（`v2.0.0`〜`v3.3.0`）全PASS

---

## 11. Risks and Mitigations

| リスク | 対策 |
|---|---|
| Scheduler側への組み込み方法が定まらないまま実装に進み、`SchedulerEngine` の既存責務（時刻ベースの判定）と混ざってしまう | Open Questions（8章）をArchitecture Designで先に確定させ、承認を得てから実装に進む |
| 「接続する」だけのつもりが、実装時に誤って `dequeue()` や自動実行まで踏み込んでしまう | Acceptance Criteria（10章）に構造的確認（呼び出し経路の不在確認）を明記し、Test Reviewで検証する |
| 既存の `SchedulerConfig` にフィールドを追加したくなり、「Configクラス追加なし」の方針との境界が曖昧になる | Open Questions 4番として明示し、既存Configへのフィールド追加が必要かどうかも含めてArchitecture Designで判断してからユーザー確認を得る |

---

## 12. Status

- [x] Project Charter ドラフト作成（本文書、Claude Code作成）
- [ ] ユーザー確認・フィードバック反映
- [ ] Project Charter 確定
- [ ] Architecture Design（次工程。本Releaseでは着手しない）
