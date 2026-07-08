# Project Charter — Release 4.3「Retry Queue Cleanup Foundation」

作成日：2026-07-08
状態：確定（ユーザー承認済み）
対象：v4.1.0の`RetryQueueUpdateDecider`が判定した`RetryQueueUpdateDecision`の
うち、`outcome == NOOP`かつ`SKIPPED`（`max_attempts`到達）由来の項目のみを
対象に、既存の`RetryQueueManager.remove()`を呼び出してQueueから除去する。
`COMPLETE` / `FAILED`（v4.2.0で既に除去済みのはず） / `NOT_FOUND` /
`DISABLED`はいずれも対象外。新しいQueueステータス・Dead Letter Queue・
隔離Queueは追加しない。

> **本Releaseの位置づけについての注記**：v4.2.0（Retry Queue Removal
> Foundation）のCharterで「`SKIPPED`（`max_attempts`到達）のQueue滞留対応は
> 意図的にスコープ外とし、次Release以降の検討事項として持ち越す」と
> 明記されていた項目（`docs/design/retry_queue_removal_foundation_charter.md`
> 冒頭注記）に、本Releaseで着手する。`docs/ROADMAP.md`569〜570行目に
> 記載済みの懸念事項への対応であり、Foundation Firstの方針は維持する
> （Dead Letter Queue等の新しい仕組みは導入しない）。

---

## 1. Background

* Retry Queue Update Foundation（v4.1.0）：`RetryQueueUpdateDecider`が
  `RetryExecutionResult`から`RetryQueueUpdateDecision`
  （`execution_result` / `outcome` / `target_status` / `reason`）を判定
  できるようになった。`outcome`は`COMPLETE` / `FAIL` / `NOOP`の3値。
  `NOOP`は`retry_result.outcome`が`SKIPPED` / `NOT_FOUND` / `DISABLED`の
  いずれかに由来する場合の共通の安全側の結果であり、`RetryQueueUpdateDecision`
  自身はどの理由に由来する`NOOP`かを区別しない（区別するには
  `decision.execution_result.retry_result.outcome`を参照する必要がある）。
* Retry Queue Removal Foundation（v4.2.0）：`RetryQueueRemovalExecutor`が
  `RetryQueueUpdateDecision`のうち`outcome`が`COMPLETE`または`FAIL`の項目
  についてのみ`RetryQueueManager.remove()`を呼び出せるようになった。
  `NOOP`（`SKIPPED` / `NOT_FOUND` / `DISABLED`いずれも含む）はremove対象外
  のまま据え置かれた。
* この結果、`SKIPPED`（`RetryPolicy.max_attempts`到達により再試行対象外と
  判定されたケース）に由来する`NOOP`項目は、v4.2.0の時点でも除去する手段を
  持たず、恒久的にQueueへ滞留し得るリスクが残っていた
  （`docs/design/retry_queue_removal_foundation.md` 12章 Future Extension）。

```
Retry Engine（受信・整理・実行・判定・除去、v3.0.0〜v4.2.0）
   │
   ├── decide_retry_queue_updates()（v4.1.0、無改修）
   │      → RetryQueueUpdateDecision のリスト（COMPLETE/FAIL/NOOP）
   ├── apply_retry_queue_removals()（v4.2.0、無改修）
   │      → COMPLETE/FAILのみ RetryQueueManager.remove() を呼び出す
   │
   └──────── ★本Releaseで新設 ────────
        「RetryQueueUpdateDecision を入力に、NOOPのうちSKIPPED由来の
         ものだけを判定（CLEANUP/KEEP）し、CLEANUPのみ
         RetryQueueManager.remove(run_id) を呼び出せる Foundation」
        （COMPLETE/FAILED/NOT_FOUND/DISABLEDはいずれも対象外。
         新しいQueueステータス・Dead Letter Queueは追加しない）
```

---

## 2. Purpose

`RetryQueueUpdateDecision`のリストを受け取り、`outcome == NOOP`かつ
`retry_result.outcome == SKIPPED`の項目についてのみ既存の
`RetryQueueManager.remove(run_id)`を呼び出し、Queueから該当項目を除去
できる新規コンポーネントを追加する。`COMPLETE` / `FAILED`
（v4.2.0で既に除去済みのはず） / `NOT_FOUND` / `DISABLED`はいずれも対象外
（KEEP）のまま構造的に除外する。

新しいQueueステータス（Dead Letter・隔離Queue等）は追加しない。

---

## 3. Goals

1. 新規コンポーネント（Decider・Executorの2段構成）を追加し、
   `list[RetryQueueUpdateDecision]`を受け取り、`NOOP`かつ`SKIPPED`由来の
   項目のみをCLEANUP、それ以外をKEEPと判定する
2. CLEANUPと判定された項目についてのみ`RetryQueueManager.remove(run_id)`
   （実際には`RetryManager`が保持する`self._queue.remove`を関数として
   受け取る）を呼び出し、結果を集約したリストを返す
3. KEEPと判定された項目はremove呼び出しを一切行わず、スキップした
   ことが結果から判別できるようにする
4. 新規コンポーネントは既存パターン（v4.1.0`RetryQueueUpdateDecider`・
   v4.2.0`RetryQueueRemovalExecutor`）を踏襲し、Stateless・
   `RetryQueueManager`への直接依存なし（`remove_fn`は関数として受け取る）
   とする
5. `RetryManager`から、薄い委譲メソッド2つ（`decide_retry_queue_cleanup()` /
   `apply_retry_queue_cleanup()`）で到達できるようにする
6. 既存の`RetryManager()` / `RetryManager.from_config()`呼び出し・
   `NullRetryManager`の動作は本Release後も無変更で動作すること
7. 既存コンポーネント（`retry_queue_update_decider.py` /
   `retry_queue_removal_executor.py`含む）は可能な限り無改修とする

---

## 4. Scope

### 対象

* `RetryQueueUpdateDecision`を受け取り、SKIPPED由来の`NOOP`のみを
  CLEANUP、それ以外をKEEPと判定する新規Decider
  （`retry_queue_cleanup_decider.py`）
* CLEANUP判定の項目のみ`remove_fn`を呼び出す新規Executor
  （`retry_queue_cleanup_executor.py`）
* `RetryManager`への薄い委譲メソッド2つの追加
  （`decide_retry_queue_cleanup()` / `apply_retry_queue_cleanup()`）
* `NullRetryManager`への同名メソッドの追加（無効時は空リスト）
* CLEANUP/KEEP双方のパターンの単体テスト
* 関連ドキュメント更新（CHANGELOG / ROADMAP / architecture.md）

### 対象外（今回やらないこと）

* Dead Letter Queue・隔離Queューといった新しいQueueステータスの追加
* Queue永続化（SQLite/Redis等）
* Retry Policy（選別基準の拡張）
* Retry Metrics / Monitoring
* Queue最適化（heapqベースのPriority Queue化等）
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source`
  パッケージ自体の改修
* `retry_queue`パッケージ自体の改修（ゼロ改修を維持）
* 既存の`retry_queue_update_decider.py` / `retry_queue_removal_executor.py`
  の変更
* `RetryQueueManager.dequeue()`の本格実装
* 実運用のComposition Root

---

## 5. Design Principles

* **Foundation First**：`SKIPPED`由来の`NOOP`をCLEANUPできるところまでを
  行う。Dead Letter Queue化・Cleanup基準のカスタマイズ（設定可能な猶予
  期間等）は後続Releaseへ送る
* **Single Responsibility**：Decider（判定）とExecutor（除去実行）を
  それぞれ既存パターン（`RetryQueueUpdateDecider` /
  `RetryQueueRemovalExecutor`）と同型で分離する
* **Stateless**：両コンポーネントとも`RetryQueueManager`への参照を
  コンストラクタで保持しない
* **Backward Compatibility**：`RetryManager()` /
  `RetryManager.from_config(...)`の既存呼び出し（新規引数を渡さない場合）
  は本Release後も無変更で動作する
* **既存コンポーネントの再利用**：新しいQueueステータス・Dead Letter Queue
  は追加せず、既存の`RetryQueueManager.remove()`を再利用する

---

## 6. Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryQueueUpdateDecider`（v4.1.0、無改修） | `RetryExecutionResult`から`RetryQueueUpdateDecision`を判定する | CLEANUP/KEEP判定・Queueへの反映 |
| `RetryQueueRemovalExecutor`（v4.2.0、無改修） | `COMPLETE` / `FAIL`の項目についてremoveを呼び出す | `NOOP`（SKIPPED含む）の扱い |
| `RetryQueueCleanupDecider`（本Releaseで新規追加） | `RetryQueueUpdateDecision`を対象に、SKIPPED由来の`NOOP`のみCLEANUP、それ以外をKEEPと判定する | Queueへの実際の反映・`COMPLETE`/`FAIL`の再判定 |
| `RetryQueueCleanupExecutor`（本Releaseで新規追加） | CLEANUP判定の項目についてのみremove操作を呼び出し、結果を集約する | 判定ロジックの再実装・Queueの内部ストア構造への直接アクセス |
| `RetryManager`（本Releaseで変更） | 新規コンポーネントへの薄い委譲窓口を持つ | 判定・除去ロジックの再実装 |

---

## 7. Dependencies

```
retry_engine  ──→ retry_queue（v3.2.0のまま。remove操作は関数として受け取る）
retry_engine  ──→ scheduler（SchedulerEvent型の参照のみ、無改修）
retry_engine  ──→ workflow_engine（無改修）
retry_engine  ──→ workflow_monitor（無改修）
```

新規の依存方向は追加しない。循環importは発生しない。

---

## 8. Acceptance Criteria

* `RetryQueueUpdateDecision.outcome == NOOP`かつ対応する
  `retry_result.outcome == SKIPPED`の項目について、`RetryQueueManager.remove()`
  が呼び出され、Queueから実際に除去されること
* `COMPLETE` / `FAIL`、および`NOOP`でも`NOT_FOUND` / `DISABLED`由来の項目に
  ついては`remove()`が一切呼び出されないこと（Spyオブジェクトによる構造的確認）
* 既存の`RetryManager()` / `RetryManager.from_config(...)`（新規引数を
  渡さない場合）が本Release後も無変更で動作すること
* `retry_queue_update_decider.py` / `retry_queue_removal_executor.py`を
  含む既存ファイルに変更がないこと（`git diff`で確認）
* CLEANUP/KEEP双方のパターンを独立した単体テストとして固定化すること
  （Architecture Review Recommendation）
* E2Eテスト全PASS

---

## 9. Non-Goals

* Dead Letter Queue・隔離Queueの追加
* Queue永続化
* Retry Policy拡張・Retry Metrics
* Queue最適化・Scheduler改修
* `retry_queue`パッケージ自体の変更

---

## 10. Status

- [x] Project Charter 作成・確定（ユーザー承認済み）
- [x] Architecture Design（`docs/design/retry_queue_cleanup_foundation.md`）
- [x] 実装・単体テスト（CLEANUP/KEEP双方）完了
