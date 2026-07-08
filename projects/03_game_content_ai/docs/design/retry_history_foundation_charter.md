# Project Charter — Release 4.7「Retry History Foundation」

作成日：2026-07-09
状態：承認済み・実装完了
対象：`original_run_id`ごとの再試行履歴（試行回数・直近記録時刻）を記録するだけの
最小基盤（`retry_history`パッケージ・`RetryHistoryRecordExecutor`）を新設する。

> **本Releaseの位置づけについての注記**：ROADMAP.md
> 「Retry Enqueue Triggerの無限再投入対策」項目は「Composition Root実装前に
> 対策が必要」と明記している。v4.6.0で追加した`RetryEnqueueTrigger`は
> `RetryQueueManager.exists()`のみで重複防止しており、Queueから除去された
> `run_id`がWorkflow Monitor上でなお`FAILED` / `TIMEOUT`のまま観測され続ける
> ケースを無限に再enqueueしてしまう既知の欠陥（Known Issue）を抱えている。
> Composition Rootを先に実装すると、この欠陥に実際に発火する定期実行の主体を
> 与えてしまう。本Releaseはこの土台（再試行履歴の記録）を先に用意する。

---

## 1. Background

* `docs/design/retry_enqueue_trigger_foundation.md` 11章 Known Issueは、対策候補として
  「`metadata["retried_from"]`（`retry_executor.py`が既に記録している）を手掛かりに
  判定できる新規コンポーネント」を挙げていた。
* **重要な発見**：この対策候補は現状のコードでは実現できない。`RetryExecutor.execute()`
  （v3.0.0、無改修）は`WorkflowEngineEvent.metadata`に`{"retried_from": ..., "attempt": ...}`
  を積むが、`WorkflowEngineExecutor`はこの`metadata`を`ExecutionHistoryManager.start_run()`
  へ渡していない（`workflow_engine_executor.py` 78行目付近）。`WorkflowExecutionRecord`
  （`execution_history/workflow_execution_record.py`）自体に`metadata`フィールドが
  存在せず、`to_dict()` / `from_dict()`にも含まれない。したがって`WorkflowMonitorRecord`
  からも`retried_from`は一切参照できない。
* 一方、`RetryResult`（`retry_engine/retry_result.py`、v3.0.0）は`RetryManager.retry()`が
  実行のたびに直接生成するデータであり、`original_run_id` / `outcome` / `attempt`を
  常に保持している。新しいrun_id（再実行後に発行される値）は公開していないが
  （同ファイル設計方針コメント参照）、「original_run_idが何回再試行されたか」を
  記録する目的には`RetryResult`で十分である。
* 本Releaseの情報源は`RetryResult`（Retry Engine自身が生成するデータ）のみとし、
  Execution Historyのmetadataには一切依存しない。

```
RetryManager.execute_dispatchable_retries()（v4.0.0、無変更）
        │  RetryExecutionResult（retry_result.outcome を含む）
        ▼
   ★本Releaseで新設：RetryHistoryRecordExecutor（retry_engine内、Stateless）
        │  outcome=RETRIEDの項目のみ抽出
        ▼
   ★本Releaseで新設：RetryHistoryManager（retry_history、新規独立パッケージ）
        │  original_run_idごとにattempt_countを記録
        ▼
  （次Release以降：RetryEnqueueTrigger等の消費側で無限再投入対策として利用）
```

---

## 2. Purpose

`original_run_id`ごとに「何回・直近いつ再試行されたか」を記録するだけの最小基盤を
新設する。記録結果を使って再enqueueを止める・`RetryPolicy.max_attempts`と比較する
といった判定は本Releaseでは一切行わない（Foundation First）。

---

## 3. Goals

1. `original_run_id`ごとの再試行履歴（試行回数・直近記録時刻）を保持する新規独立
   パッケージ`src/retry_history/`を新設する
2. `retry_engine`側に、`RetryExecutionResult`のうち`outcome=RETRIED`の項目のみを
   抽出して記録するStatelessなコンポーネント（`RetryHistoryRecordExecutor`）を新設する
3. `RetryManager`が両コンポーネントをConstructor Injectionで保持できるようにし、
   `record_retry_history()`を新設する（薄い委譲のみ）
4. `retry_queue`と同じ理由（stateful store）で、`history`省略時は
   `NullRetryHistoryManager()`にフォールバックする
5. `retry_history`は`retry_engine`を一切importしない（循環なし）
6. 記録結果を使ってRetryEnqueueTrigger側の再enqueueガード判定に反映する処理は
   次Release以降に送る

---

## 4. Scope

### 対象

* 新規パッケージ`src/retry_history/`の新設
  （`RetryHistoryRecord` / `RetryHistoryManager` / `NullRetryHistoryManager`）
* `retry_engine`側の新規コンポーネント`RetryHistoryRecordExecutor`
  （`retry_history_recorder.py`）
* `RetryManager` / `NullRetryManager`への`record_retry_history()`追加
  （末尾デフォルト引数・薄い委譲のみ）
* テスト（新規E2Eテスト・既存回帰確認）
* 関連ドキュメント更新（CHANGELOG / ROADMAP / architecture.md）

### 対象外（今回やらないこと）

* `RetryEnqueueTrigger`側が本履歴を参照して再enqueueを止める判定（次Release以降）
* `RetryPolicy.max_attempts`との統合判定
* Composition Root本体
* 永続化（プロセス終了で消える。`retry_queue`と同じ扱い）
* Feature Gate・Configクラスの新設

---

## 5. Design Principles

* **Foundation First**：記録のみに留め、消費側（無限再投入ガード）は次Release以降へ送る
* **Single Responsibility**：`retry_history`はQueue管理・判定・Retry実行のいずれも行わない
* **Stateless（コンポーネント単位）**：`RetryHistoryRecordExecutor`はStateless。
  状態（履歴）を保持するのは`RetryHistoryManager`のみ（`retry_queue`と同じ「意図的な例外」）
* **Backward Compatibility**：`RetryManager.__init__` / `from_config()`への追加引数は
  末尾のデフォルト値付きのみ。既存メソッドは1行も変更しない
* **依存方向**：`retry_engine → retry_history`の新規一方向依存のみ。
  `retry_history`は`retry_engine`を一切importしない（循環なし）
* **情報源の限定**：`metadata["retried_from"]`はExecution Historyに永続化されておらず
  参照できないため、対策の根拠として使用しない。情報源は`RetryResult`のみとする

---

## 6. Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryHistoryManager`（新設） | `original_run_id`ごとの再試行履歴を記録・参照する | Retry可否判定・Retry実行・Queue操作 |
| `NullRetryHistoryManager`（新設） | 無効時のダミー実装。記録・参照とも常に「なし」を返す | 実データの保持 |
| `RetryHistoryRecordExecutor`（新設） | `RetryExecutionResult`のうちoutcome=RETRIEDの項目のみrecord_fnを呼び出す | `RetryHistoryManager`型への直接依存・判定ロジックの複製 |
| `RetryManager`（既存、v3.0.0〜） | `record_retry_history()`で上記2コンポーネントへ薄く委譲する | 記録ロジック自体の実装 |

---

## 7. Dependencies

```
retry_engine   ──→ retry_history（新規。RetryHistoryManager / NullRetryHistoryManager型の参照のみ）
retry_history  ──→ （なし。標準ライブラリのみ、独立した葉パッケージ）
```

`retry_history`が`retry_engine`を参照する辺は存在しない。循環importは発生しない。

---

## 8. Open Questions（Architecture Designで確定した事項）

1. **`history`省略時のフォールバック先**：Stateless系コンポーネント（`event_consumer`等）
   は省略時に実体へフォールバックするが、`retry_history`はstateful storeであるため
   `retry_queue`（`queue`引数）と同じ扱いとし、省略時は`NullRetryHistoryManager()`へ
   フォールバックすることに決定した。
2. **`record_all()`の1:1対応**：`RetryQueueUpdateDecider`等の既存Decider群と同じ設計言語を
   踏襲し、`RetryHistoryRecordExecutor.record_all()`は入力`RetryExecutionResult`と
   同じ件数・順序の結果（`RetryHistoryRecordResult`）を返すことに決定した（記録対象外の
   項目も`recorded=False`として結果に含め、暗黙に捨てない）。
3. **dry_runの扱い**：既存の`apply_retry_queue_removals()`等が`dry_run`時もQueue側の
   副作用（remove呼び出し）を実行する既存パターンを踏襲し、`record_retry_history()`も
   `dry_run`の値に関わらず記録を行うことに決定した（メモリ上の記録のみで外部副作用が
   ないため、既存パターンとの一貫性を優先）。

---

## 9. Acceptance Criteria

* `RetryHistoryManager.record()`が、同一`original_run_id`への複数回の呼び出しで
  `attempt_count`を正しく積算すること
* `RetryHistoryRecordExecutor`が、`outcome=RETRIED`の項目のみ記録し、
  `SKIPPED` / `NOT_FOUND` / `DISABLED`は記録しないこと
* `NullRetryHistoryManager`が実データを一切保持せず、常に「記録なし」相当の結果を
  返すこと
* `retry_history`が`retry_engine`を一切importしないこと（静的検査で確認）
* `RetryManager.__init__` / `from_config()`の新規引数が末尾・デフォルト値付きで
  追加されていること
* `retry()` 〜 `apply_retry_queue_terminal_cleanup()`までの既存メソッドが1行も
  変更されていないこと
* `metadata["retried_from"]`という文字列が新規ファイルに一切含まれないこと
  （情報源として使用していないことの構造的確認）
* E2Eテスト全PASS、既存回帰（v2.0.0〜v4.6.0）で新規に発生する差分が、既存の
  `git diff`ベースの一時差分・`__all__`/最終引数の恒久差分（`[KI-3]`〜`[KI-14]`と
  同種）のみであること

---

## 10. Non-Goals

* `RetryEnqueueTrigger`側の消費（無限再投入ガード）
* `RetryPolicy.max_attempts`との統合判定
* Composition Root
* 永続化
* Feature Gate・Configクラスの新設

---

## 11. Risks and Mitigations

| リスク | 対策 |
|---|---|
| 記録の土台ができても、消費側（`RetryEnqueueTrigger`）への接続がなければKnown Issue自体は未解消のまま | 本Releaseの対象外として明記し、次Release（Retry Enqueue Guard等）で接続する方針をCHANGELOGに記録する |
| `record_retry_history()`が既存の`execute_dispatchable_retries()`を再度呼び出す構造のため、他の委譲メソッド（`apply_retry_queue_removals()`等）と同じ`events`に対して両方を呼ぶと`retry()`が重複実行されうる | 既存Release群（v4.1.0〜v4.4.0）から継続する既知の系統的特性であり、本Releaseで新たに導入した問題ではないため対応しない |

---

## 12. Status

- [x] Project Charter ドラフト作成（本文書、Claude Code作成）
- [x] ユーザー承認（Architecture Review指摘事項を設計上の前提として採用）
- [x] Architecture Design
- [x] Implementation
- [x] Test（E2Eテスト178件・既存回帰確認、いずれも完了）
