# v4.9.0 Retry Attempt Synchronization Foundation 設計書（Project Charter / Architecture Design）

作成日：2026-07-09
状態：確定（Architecture Review完了・Approve・ユーザー承認済み）

---

## 1. Project Charter

### 1.1 目的

`RetryEnqueueTrigger.enqueue_pending_failures()`がRetry Queueへenqueueする際、
`retry_attempt`を常に`1`固定で渡している状態を解消し、`RetryHistoryManager`が
保持する実際の試行回数（`RetryHistoryRecord.attempt_count`）をQueueへ受け渡す
基盤を追加する。

### 1.2 背景

v4.8.0（Retry Enqueue Guard）のCHANGELOG Noteに記載の通り、
`RetryEnqueueTrigger.enqueue_pending_failures()`は`queue.enqueue()`呼び出し時に
`retry_attempt`を渡しておらず、常にデフォルト値`1`でQueueへ投入される。この値は
下流の`RetryExecutionCoordinator.execute()` → `RetryManager.retry(attempt=...)` →
`RetryPolicy.should_retry()`まで素通しで伝播するため、`RETRY_MAX_ATTEMPTS`
（`max_attempts`）を活かした複数回リトライの判定基盤が事実上機能しない。

### 1.3 Non-Goal（本Releaseで実施しないこと）

* `RetryEnqueueGuard`の判定基準変更（履歴の有無の二値 → `attempt_count >= max_attempts`比較）
* `RetryPolicy` / `RetryExecutionCoordinator` / `RetryManager`への変更
* Composition Root（定期実行の起動導線）
* `.env.example`整備
* その他Future Extension項目

本Release適用後も、`RetryEnqueueGuard`（v4.8.0）が「履歴が1回でもあれば
無条件でBLOCK」という二値判定のままであるため、**外部から観測可能な挙動は
変化しない**ことを前提として承認済み（2章で詳述）。

---

## 2. Architecture Design

### 2.1 変更対象

```
src/retry_enqueue_trigger/retry_enqueue_trigger.py
    RetryEnqueueTrigger.enqueue_pending_failures()  ★変更（メソッド本体のみ）
```

以下は無改修：`RetryQueueManager` / `RetryQueueItem` / `RetryHistoryManager` /
`RetryEnqueueGuard` / `RetryExecutionCoordinator` / `RetryManager` / `RetryPolicy`。
コード調査の結果、`retry_attempt`を発行元から下流（Queue → Coordinator →
Manager → Policy）まで正しく伝播する経路は既に完成しており、欠けていたのは
`RetryEnqueueTrigger`がその値を解決してQueueへ渡す1箇所のみであることを確認済み。

### 2.2 変更内容

```python
history_record = self._history.get(record.run_id)
guard_decision = self._guard.decide(record.run_id, has_history=history_record is not None)
if guard_decision.outcome == RetryEnqueueGuardOutcome.BLOCK:
    skipped_history += 1
    continue

if self._queue.exists(record.run_id):
    skipped_existing += 1
    continue
next_attempt = history_record.attempt_count + 1 if history_record is not None else 1
result = self._queue.enqueue(
    run_id=record.run_id, workflow_name=record.workflow_name, retry_attempt=next_attempt,
)
```

`self._history.has_history()`の呼び出しを`self._history.get()`（既存の公開API）
に置き換え、1回の呼び出しで「履歴の有無」（Guard判定用）と「次のattempt番号」
（Queue登録用）の両方を導出する。`RetryHistoryManager` / `NullRetryHistoryManager`
はいずれも`get()`を既に実装済みであり、新規依存は発生しない。

### 2.3 なぜ本Release単体では挙動が変化しないか

`RetryEnqueueGuard`（v4.8.0）は「履歴が1回でもあればBLOCK」という二値判定の
ままである。そのため`queue.enqueue()`に実際に到達するのは
`history_record is None`（＝この`run_id`は一度もretryされていない）ケースの
みであり、この分岐における`next_attempt`は常に`1`にしかならない。

これは不具合ではなく、Guardの判定基準精緻化（`attempt_count >= max_attempts`
比較への変更）を将来Releaseへ送るための意図的な「消費者不在の配線」である
（v3.1.0 Retry Queue・v3.5.0 Retry Scheduler Decision・v4.7.0 Retry History
Foundationと同型のFoundation First）。

### 2.4 Compatibility

* `RetryEnqueueTrigger.__init__`のシグネチャは無変更（`self, monitor, queue,
  history=None, guard=None`のまま）
* `RetryEnqueueTriggerResult`のフィールドは無変更
* `src/retry_enqueue_trigger/`のファイル構成（3ファイル）・`__init__.py`の
  `__all__`（6シンボル）はいずれも無変更
* `history` / `guard`を渡さない既存呼び出しは本Release前後でまったく同じ結果になる

---

## 3. Architecture Review

**結論：Approve**

| 観点 | 判定 |
|---|---|
| Foundation First | ✅ Guard判定基準は変更せず、配線のみ追加 |
| Small Release | ✅ 1ファイル・1メソッド内の変更のみ |
| Stateless | ✅ 既存のStateless原則を維持 |
| Single Responsibility | ✅ 「attemptの値を正しく解決する」責務のみに限定 |
| Backward Compatibility | ✅ シグネチャ変更なし。既存呼び出しは全て同じ結果 |
| Composition | ✅ 新規依存なし。`retry_history`の既存公開APIを呼ぶ範囲に留まる |

---

## 4. Known Issue（本Releaseでも未解消）

`RETRY_MAX_ATTEMPTS`（デフォルト3）を活かした複数回の自動リトライ運用は、
本Release後も`RetryEnqueueTrigger`経由では実質的に機能しないままである。
`RetryEnqueueGuard`の判定基準を「履歴の有無」から「`attempt_count >=
max_attempts`」の比較へ精緻化する将来Releaseと組み合わせて初めて解消する
（`docs/design/retry_enqueue_guard.md` 12章 Future Extension参照）。

---

## 5. Status

- [x] Architecture Review 完了（Approve、ユーザー承認済み）
- [x] Implementation
- [x] Unit / E2E Test（`tests/test_e2e_v4_9_0_retry_attempt_synchronization_foundation.py`）
- [x] Regression確認
- [x] Documentation更新
