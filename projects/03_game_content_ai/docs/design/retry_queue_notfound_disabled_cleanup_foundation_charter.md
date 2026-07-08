# Project Charter — Release 4.4「NOT_FOUND / DISABLED Cleanup Foundation」

作成日：2026-07-08
状態：ドラフト（ユーザー確認待ち）
対象：v4.3.0の`RetryQueueCleanupDecider`がKEEPと判定していた`RetryQueueUpdateDecision`
のうち、`outcome == NOOP`かつ`retry_result.outcome`が`NOT_FOUND`または`DISABLED`の
項目について、Cleanup方針（CLEANUP／KEEP）を確定し、対象と判定された項目のみ
既存の`RetryQueueManager.remove()`を呼び出してQueueから除去する。`COMPLETE` /
`FAILED`（v4.2.0で除去済み） / `SKIPPED`（v4.3.0で除去済み）はいずれも対象外。
新しいQueueステータス・Dead Letter Queue・隔離Queueは追加しない。

> **本Releaseの位置づけについての注記**：v4.3.0（Retry Queue Cleanup
> Foundation）のCharter・設計書双方で「`NOT_FOUND` / `DISABLED`由来の`NOOP`の
> Cleanup方針の検討」が意図的に対象外とされ、Future Extensionとして次Release
> 以降に持ち越されていた項目
> （`docs/design/retry_queue_cleanup_foundation.md` 8章 Future Extension、
> `docs/design/retry_queue_cleanup_foundation_charter.md` 冒頭注記）に、
> 本Releaseで着手する。

---

## 1. Background

* Retry Queue Update Foundation（v4.1.0）：`RetryQueueUpdateDecider`が
  `RetryExecutionResult`から`RetryQueueUpdateDecision`を判定できるように
  なった。`outcome`は`COMPLETE` / `FAIL` / `NOOP`の3値。`NOOP`は
  `retry_result.outcome`が`SKIPPED` / `NOT_FOUND` / `DISABLED`のいずれかに
  由来する共通の安全側の結果であり、`RetryQueueUpdateDecision`自身はどの
  理由に由来する`NOOP`かを区別しない（`decision.execution_result.retry_result.outcome`
  を参照する必要がある）。
* Retry Queue Removal Foundation（v4.2.0）：`COMPLETE` / `FAIL`のみを
  `RetryQueueManager.remove()`の対象とした。`NOOP`はいずれもremove対象外
  のまま据え置かれた。
* Retry Queue Cleanup Foundation（v4.3.0）：`NOOP`のうち`SKIPPED`
  （`max_attempts`到達）由来の項目のみをCLEANUPと判定しremoveできるように
  なった。同時に、`NOT_FOUND`・`DISABLED`由来の`NOOP`は明示的にKEEPと
  判定され、Cleanup方針の検討はFuture Extensionとして持ち越された
  （`retry_queue_cleanup_decider.py`18〜20行目にも「これらはQueueに滞留する
  性質がSKIPPEDと異なる」と明記されている）。
* `RetryOutcome`（`retry_result.py`）の定義上、`NOT_FOUND`と`DISABLED`は
  `SKIPPED`とは性質が異なる。
  * `SKIPPED`：`RetryPolicy.max_attempts`到達。判定条件（試行回数）は
    今後変化する見込みがなく、恒久的にQueueに滞留し得る。
  * `NOT_FOUND`：判定時点で`run_id`がWorkflow Monitorに存在しない。
    Execution Historyへの記録タイミングとの競合（記録前に判定してしまう
    レース）である可能性と、当該`run_id`自体が本当に存在しない
    （恒久的な状態）である可能性の両方があり得る。
  * `DISABLED`：判定時点で`RETRY_ENGINE_ENABLED=false`または下位ゲートが
    閉じていた。これは**判定時点の設定値**を反映した一時的な状態であり、
    後から`RETRY_ENGINE_ENABLED=true`に戻る、あるいは下位ゲートが開く
    ことで、同じQueue項目が将来的に再試行可能になる余地がある。
* この差異（`SKIPPED`＝恒久 vs `NOT_FOUND`／`DISABLED`＝状況により一時的
  の可能性）は、v4.3.0のCleanup方針をそのまま横展開してよいかどうかを
  左右する重要な論点であり、本Charterで扱う。

```
Retry Engine（受信・整理・実行・判定・除去・Cleanup、v3.0.0〜v4.3.0）
   │
   ├── decide_retry_queue_updates()（v4.1.0、無改修）
   │      → RetryQueueUpdateDecision のリスト（COMPLETE/FAIL/NOOP）
   ├── apply_retry_queue_removals()（v4.2.0、無改修）
   │      → COMPLETE/FAILのみ RetryQueueManager.remove() を呼び出す
   ├── apply_retry_queue_cleanup()（v4.3.0、無改修）
   │      → NOOPのうちSKIPPED由来のみ RetryQueueManager.remove() を呼び出す
   │
   └──────── ★本Releaseで検討 ────────
        「NOOPのうちNOT_FOUND / DISABLED由来の項目について、Cleanup方針
         （CLEANUP or KEEP、両者を同一方針とするか個別方針とするか）を
         確定し、対象と判定された項目のみ RetryQueueManager.remove(run_id)
         を呼び出せる Foundation」
        （COMPLETE/FAILED/SKIPPEDはいずれも対象外。新しいQueueステータス・
         Dead Letter Queueは追加しない）
```

---

## 2. Purpose

`RetryQueueUpdateDecision`のリストを受け取り、`outcome == NOOP`かつ
`retry_result.outcome`が`NOT_FOUND`または`DISABLED`の項目について、
Cleanup方針（CLEANUP／KEEP）を確定したうえで判定する新規コンポーネントを
追加する。CLEANUPと判定された項目についてのみ既存の
`RetryQueueManager.remove(run_id)`を呼び出し、Queueから除去する。
`COMPLETE` / `FAILED`（v4.2.0で除去済み） / `SKIPPED`（v4.3.0で除去済み）は
いずれも対象外（KEEP）のまま構造的に除外する。

新しいQueueステータス（Dead Letter・隔離Queue等）は追加しない。

---

## 3. Goals

1. `NOT_FOUND`・`DISABLED`それぞれについて、Cleanup対象とすべきか
   （恒久的な滞留リスクか、一時的な状態であり再試行の余地を残すべきか）を
   Architecture Designで確定する（4章 Scope・8章 Open Questions参照）
2. 新規コンポーネント（Decider・Executorの2段構成、v4.3.0と同型）を追加し、
   `list[RetryQueueUpdateDecision]`を受け取り、確定した方針に従って
   `NOT_FOUND` / `DISABLED`由来の`NOOP`をCLEANUP／KEEPと判定する
3. CLEANUPと判定された項目についてのみ`RetryQueueManager.remove(run_id)`
   （`remove_fn`として関数で受け取る、既存パターン踏襲）を呼び出し、
   結果を集約したリストを返す
4. KEEPと判定された項目はremove呼び出しを一切行わず、スキップした
   ことが結果から判別できるようにする
5. 新規コンポーネントは既存パターン（v4.1.0`RetryQueueUpdateDecider`・
   v4.2.0`RetryQueueRemovalExecutor`・v4.3.0`RetryQueueCleanupDecider`/
   `RetryQueueCleanupExecutor`）を踏襲し、Stateless・
   `RetryQueueManager`への直接依存なしとする
6. `RetryManager`から、薄い委譲メソッドで到達できるようにする
   （名称・粒度はArchitecture Designで確定）
7. 既存の`RetryManager()` / `RetryManager.from_config()`呼び出し・
   `NullRetryManager`の動作は本Release後も無変更で動作すること
8. 既存コンポーネント（`retry_queue_update_decider.py` /
   `retry_queue_removal_executor.py` / `retry_queue_cleanup_decider.py` /
   `retry_queue_cleanup_executor.py`含む）は無改修とする

---

## 4. Scope

### 対象

* `NOT_FOUND`・`DISABLED`それぞれのCleanup方針（CLEANUP／KEEP）の確定
  （8章 Open Questionsとして次工程Architecture Designで結論を出す）
* `RetryQueueUpdateDecision`を受け取り、確定方針に従って`NOT_FOUND` /
  `DISABLED`由来の`NOOP`を判定する新規Decider
* CLEANUP判定の項目のみ`remove_fn`を呼び出す新規Executor
* `RetryManager`への薄い委譲メソッドの追加
* `NullRetryManager`への同名メソッドの追加（無効時は空リスト）
* 確定した方針の全パターン（CLEANUP／KEEP、`NOT_FOUND`・`DISABLED`双方）を
  独立した単体テストとして固定化
* 関連ドキュメント更新（CHANGELOG / ROADMAP / architecture.md）

### 対象外（今回やらないこと）

* `COMPLETE` / `FAILED`（v4.2.0で除去済み） / `SKIPPED`（v4.3.0で除去済み）
  の再判定・二重除去
* Dead Letter Queue・隔離Queueといった新しいQueueステータスの追加
* Queue永続化（SQLite/Redis等）
* Retry Policy（選別基準の拡張、`DISABLED`解消後の自動再enqueue等）
* Retry Metrics / Monitoring
* Queue最適化（heapqベースのPriority Queue化等）
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source`
  パッケージ自体の改修
* `retry_queue`パッケージ自体の改修（ゼロ改修を維持）
* 既存の`retry_queue_update_decider.py` / `retry_queue_removal_executor.py` /
  `retry_queue_cleanup_decider.py` / `retry_queue_cleanup_executor.py`の変更
* `RetryQueueManager.dequeue()`の本格実装
* 実運用のComposition Root

---

## 5. Design Principles

* **Foundation First**：`NOT_FOUND` / `DISABLED`由来の`NOOP`について
  Cleanup方針を確定し、CLEANUPと判定された範囲でremoveできるところまでを
  行う。猶予期間付きCleanup・`DISABLED`解消後の自動再試行などの高度化は
  後続Releaseへ送る
* **Single Responsibility**：Decider（判定）とExecutor（除去実行）を
  それぞれ既存パターン（v4.3.0`RetryQueueCleanupDecider` /
  `RetryQueueCleanupExecutor`）と同型で分離する
* **Stateless**：両コンポーネントとも`RetryQueueManager`への参照を
  コンストラクタで保持しない
* **Backward Compatibility**：`RetryManager()` /
  `RetryManager.from_config(...)`の既存呼び出し（新規引数を渡さない場合）
  は本Release後も無変更で動作する
* **既存コンポーネントの再利用**：新しいQueueステータス・Dead Letter Queue
  は追加せず、既存の`RetryQueueManager.remove()`を再利用する
* **恒久的な状態か一時的な状態かを区別してから判定基準を決める**：
  v4.3.0の`SKIPPED`（恒久的）と異なり、`NOT_FOUND` / `DISABLED`は判定時点の
  一時的な状態である可能性がある（1章 Background参照）。この性質の違いを
  無視して機械的にCLEANUP方針を横展開しない

---

## 6. Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryQueueUpdateDecider`（v4.1.0、無改修） | `RetryExecutionResult`から`RetryQueueUpdateDecision`を判定する | CLEANUP/KEEP判定・Queueへの反映 |
| `RetryQueueRemovalExecutor`（v4.2.0、無改修） | `COMPLETE` / `FAIL`の項目についてremoveを呼び出す | `NOOP`（SKIPPED / NOT_FOUND / DISABLED含む）の扱い |
| `RetryQueueCleanupDecider` / `Executor`（v4.3.0、無改修） | `SKIPPED`由来の`NOOP`のみCLEANUP、それ以外をKEEPと判定・除去する | `NOT_FOUND` / `DISABLED`由来の`NOOP`のCleanup判定 |
| 新規Decider（本Releaseで追加） | `RetryQueueUpdateDecision`を対象に、確定方針に従い`NOT_FOUND` / `DISABLED`由来の`NOOP`をCLEANUP／KEEPと判定する | Queueへの実際の反映・他outcomeの再判定 |
| 新規Executor（本Releaseで追加） | CLEANUP判定の項目についてのみremove操作を呼び出し、結果を集約する | 判定ロジックの再実装・Queueの内部ストア構造への直接アクセス |
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

## 8. Open Questions（Architecture Designで確定する事項）

1. **`NOT_FOUND`はCLEANUP対象とすべきか**：`run_id`がWorkflow Monitorに
   恒久的に存在しない（誤ったrun_id・記録漏れ等）ケースが大半だと想定
   されるが、Execution Historyへの記録タイミングとの競合により一時的に
   `NOT_FOUND`となるレースが理論上あり得るか、あり得るとして無視して
   良い水準かを確認したうえで方針を確定する
2. **`DISABLED`はCLEANUP対象とすべきか**：`RETRY_ENGINE_ENABLED=false`
   解除後に同じQueue項目を再試行させたい運用ニーズがあるかどうかで結論が
   変わる。Cleanup（除去）してしまうと、再度有効化した後もそのQueue項目
   経由では再試行されなくなる点をリスクとして扱う（11章 Risks参照）
3. **`NOT_FOUND`と`DISABLED`を同一方針にするか、個別方針にするか**：
   両者は性質が異なる（1章 Background）ため、v4.3.0のように単一の
   Decider内でoutcome種別ごとに異なる判定結果を返す設計にするか、
   あるいは一方のみCLEANUPとし他方はKEEPのまま次Release送りにするか
4. **新規コンポーネントの名称**：v4.3.0の`RetryQueueCleanupDecider` /
   `Executor`と役割が重複しないよう区別できる名称とする
   （例：対象outcomeを名称に含める等）
5. **`RetryManager`への委譲メソッドの名称・粒度**：既存の
   `decide_retry_queue_cleanup()` / `apply_retry_queue_cleanup()`との
   名称衝突を避けつつ、対称的な命名とする

---

## 9. Acceptance Criteria

* Open Questions（8章）の結論に基づき、CLEANUPと判定された`NOT_FOUND` /
  `DISABLED`由来の`NOOP`項目について、`RetryQueueManager.remove()`が
  呼び出され、Queueから実際に除去されること
* KEEPと判定された項目（`COMPLETE` / `FAIL` / `SKIPPED`、および
  Open Questionsの結論次第でKEEPのまま据え置かれる`NOT_FOUND` /
  `DISABLED`）については`remove()`が一切呼び出されないこと（Spyオブジェクト
  による構造的確認）
* 既存の`RetryManager()` / `RetryManager.from_config(...)`（新規引数を
  渡さない場合）が本Release後も無変更で動作すること
* `retry_queue_update_decider.py` / `retry_queue_removal_executor.py` /
  `retry_queue_cleanup_decider.py` / `retry_queue_cleanup_executor.py`を
  含む既存ファイルに変更がないこと（`git diff`で確認）
* CLEANUP／KEEP双方（`NOT_FOUND`・`DISABLED`それぞれ）のパターンを
  独立した単体テストとして固定化すること
* E2Eテスト全PASS、既存回帰（v2.0.0〜v4.3.0）全PASS

---

## 10. Non-Goals

* Dead Letter Queue・隔離Queueの追加
* Queue永続化
* Retry Policy拡張（`DISABLED`解消後の自動再enqueue等）・Retry Metrics
* Queue最適化・Scheduler改修
* `retry_queue`パッケージ自体の変更
* `COMPLETE` / `FAILED` / `SKIPPED`の再判定・二重除去

---

## 11. Risks and Mitigations

| リスク | 対策 |
|---|---|
| `DISABLED`をCLEANUP対象にした場合、`RETRY_ENGINE_ENABLED`を再度`true`に戻した運用者が「再試行されるはずのQueue項目が消えている」と誤解する可能性がある | Architecture Design（Open Question 2）で明示的に結論を出し、CLEANUP対象とする場合はPurpose・ドキュメントにその設計判断とトレードオフを明記する |
| `NOT_FOUND`が実はExecution Historyへの記録タイミングとの競合による一時的な状態だった場合、CLEANUPしてしまうと本来存在するはずだった実行記録と紐づく機会を失う | Architecture Design（Open Question 1）でレースの起こりやすさ・実害を確認し、必要であれば`NOT_FOUND`のみ本Releaseでは見送り次Release送りにする選択肢も許容する |
| `NOT_FOUND`と`DISABLED`を同一方針で機械的に扱うと、性質の違い（恒久 vs 一時的）を軽視した設計になるリスクがある | 5章Design Principlesに明記のとおり、両者を安易に同一視せず、Architecture Designで個別に方針を検討する |

---

## 12. Status

- [x] Project Charter ドラフト作成（本文書、Claude Code作成）
- [ ] ユーザー確認・フィードバック反映
- [ ] Project Charter 確定
- [ ] Architecture Design
