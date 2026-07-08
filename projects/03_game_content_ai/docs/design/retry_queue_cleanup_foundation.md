# v4.3.0 Retry Queue Cleanup Foundation 設計書（Architecture Design）

作成日：2026-07-08
状態：確定（Architecture Review完了・**Approve with Recommendations**）。
`docs/design/retry_queue_cleanup_foundation_charter.md`（Project Charter、
承認済み）を前提とする。

---

## 1. Architecture Overview

Release 4.2（`docs/design/retry_queue_removal_foundation.md`）までで、
以下が確立した。

* `RetryQueueUpdateDecider`（v4.1.0）が`RetryExecutionResult`から
  `RetryQueueUpdateDecision`（`execution_result` / `outcome` /
  `target_status` / `reason`）を判定できる。`outcome`は`COMPLETE` /
  `FAIL` / `NOOP`の3値
* `RetryQueueRemovalExecutor`（v4.2.0）が`RetryQueueUpdateDecision`のうち
  `outcome`が`COMPLETE`または`FAIL`の項目についてのみ
  `RetryQueueManager.remove(run_id)`を呼び出せる
* `outcome == NOOP`の項目（`SKIPPED` / `NOT_FOUND` / `DISABLED`いずれかに
  由来）はいずれもremove対象外のまま据え置かれている。とりわけ`SKIPPED`
  （`RetryPolicy.max_attempts`到達）は、除去する手段を持たず恒久的に
  Queueへ滞留し得るリスクとして、v4.2.0のCharter・設計書の両方で次Release
  以降の検討事項として明記されていた

本Release（v4.3.0）は、`retry_engine`パッケージに**除去判定のもう一段の
絞り込み**として、`RetryQueueUpdateDecision`のうち`outcome == NOOP`かつ
`retry_result.outcome == SKIPPED`の項目についてのみ`RetryQueueManager.remove(run_id)`
を呼び出し、Queueから該当項目を除去する新規コンポーネントを新設する。
`COMPLETE` / `FAIL`（v4.2.0で既に除去済みのはず） / `NOT_FOUND` /
`DISABLED`はいずれもremove呼び出しの対象から構造的に除外する（KEEP）。

```
Retry Engine（受信・整理・実行・判定・除去、v3.0.0〜v4.2.0）
   │
   ├── decide_retry_queue_updates()（v4.1.0、無改修）
   │      → RetryQueueUpdateDecision のリスト（COMPLETE/FAIL/NOOP）
   ├── apply_retry_queue_removals()（v4.2.0、無改修）
   │      → COMPLETE/FAILのみ remove_fn を呼び出す
   │
   └── decide_retry_queue_cleanup() ★新設
          │
          └─► RetryQueueCleanupDecider ★新設（判定：NOOP+SKIPPEDのみCLEANUP、それ以外KEEP）
                 │
                 ▼
             RetryQueueCleanupDecision ★新設データ構造
                 （update_decision・outcome・reason）

      apply_retry_queue_cleanup() ★新設
          │
          ├── decide_retry_queue_cleanup() を呼び出す
          │
          └─► RetryQueueCleanupExecutor ★新設（除去：CLEANUPのみ remove_fn を呼び出す）
                 │
                 ▼
             RetryQueueCleanupResult ★新設データ構造
                 （decision・attempted・queue_result・reason）
```

本Releaseの核心は、v4.1.0の`RetryQueueUpdateDecision`がすでに保持している
情報（`execution_result.retry_result.outcome`）を追加の突き合わせなしに
再利用し、「`NOOP`のうちどれが`SKIPPED`由来か」を1箇所に集約して判定する
ことである。`RetryQueueUpdateDecider` / `RetryQueueRemovalExecutor` /
`RetryQueueManager`は一切変更しない。新しいQueueステータス（Dead Letter・
隔離Queue等）は導入しない。

---

## 2. Design Policy

* **Foundation First**：`SKIPPED`由来の`NOOP`をCLEANUPできるところまでを
  行う。Cleanup基準のカスタマイズ（猶予期間・再enqueue等）は対象外
* **Single Responsibility**：`RetryQueueCleanupDecider`は判定のみ、
  `RetryQueueCleanupExecutor`は除去実行のみを担う。v4.1.0
  `RetryQueueUpdateDecider` / v4.2.0`RetryQueueRemovalExecutor`と同じ
  Decider/Executor分離パターンを踏襲する
* **Stateless**：両コンポーネントとも内部状態を一切保持しない
* **既存コンポーネントの再利用**（Charter 5章）：`RetryQueueCleanupDecider`
  は`RetryQueueUpdateDecider`が既に判定済みの`RetryQueueUpdateDecision`を
  入力とし、`RetryExecutionResult`やそれ以前の生データへは遡らない。
  `RetryQueueCleanupExecutor`は`RetryQueueRemovalExecutor`と同じく
  `remove_fn: Callable[[str], RetryQueueResult]`を関数として受け取り、
  `RetryQueueManager`型への直接依存を持たない
* **RetryManagerの責務を肥大化させない**：新規委譲メソッドは
  `decide_retry_queue_updates()`（v4.1.0、無変更）への委譲＋新規
  コンポーネントへの委譲、という薄い合成のみで完結させる

---

## 3. Cleanup方針（CLEANUP/KEEP Policy）

| `update_decision.outcome` | `retry_result.outcome` | Cleanup判定 | 理由 |
|---|---|---|---|
| `COMPLETE` | `RETRIED`（成功） | **KEEP** | v4.2.0の`apply_retry_queue_removals()`で既に除去されているはずの項目。本Foundationは再判定・二重除去を行わない |
| `FAIL` | `RETRIED`（失敗） | **KEEP** | 同上 |
| `NOOP` | `SKIPPED` | **CLEANUP** | `max_attempts`到達により再試行対象外と判定され、今後も状態が変わる見込みがない滞留項目（Project Charter「Cleanup対象：SKIPPEDのみ」） |
| `NOOP` | `NOT_FOUND` | **KEEP** | `run_id`がWorkflow Monitorに存在しないケース。`SKIPPED`と異なり、以後別のrun_idとしてenqueueし直される等の運用差異があり得るため、本Foundationでは対象外のまま据え置く（Project Charter「対象外：NOT_FOUND」） |
| `NOOP` | `DISABLED` | **KEEP** | `RETRY_ENGINE_ENABLED=false`等でRetry Engineそのものが無効だったケース。Retry Engine自体が動いていない状況でのCleanup実行はそもそも想定されない（Project Charter「対象外：DISABLED」） |

Dead Letter Queue・隔離Queueといった新しいQueueステータスの追加は行わない。
`CLEANUP`と判定された項目は、既存の`RetryQueueManager.remove()`
（v3.1.0、`status=CANCELLED`に更新後Queueから削除）をそのまま呼び出す。

---

## 4. Package Structure（変更差分）

```
src/retry_engine/
├── retry_queue_cleanup_decider.py   ★新規
│     RetryQueueCleanupOutcome（CLEANUP / KEEP）
│     RetryQueueCleanupDecision（update_decision / outcome / reason）
│     RetryQueueCleanupDecider（decide() / decide_all()）
├── retry_queue_cleanup_executor.py  ★新規
│     RetryQueueCleanupResult（decision / attempted / queue_result / reason）
│     RetryQueueCleanupExecutor（apply() / apply_all()）
├── retry_manager.py                 ★変更
│     RetryManager.__init__ / from_config() に
│         queue_cleanup_decider / queue_cleanup_executor 引数を追加（末尾・デフォルトNone）
│     RetryManager.decide_retry_queue_cleanup() ★新設
│     RetryManager.apply_retry_queue_cleanup()  ★新設
│     NullRetryManager に同名2メソッド ★新設（常に[]を返す）
└── __init__.py                      ★変更（新規5シンボルexport）
```

`retry_queue_update_decider.py` / `retry_queue_removal_executor.py`を
含む既存ファイルは無改修（ゼロ改修）。

---

## 5. Public API

```python
class RetryQueueCleanupOutcome(Enum):
    CLEANUP = "cleanup"
    KEEP = "keep"


@dataclass(frozen=True)
class RetryQueueCleanupDecision:
    update_decision: RetryQueueUpdateDecision
    outcome: RetryQueueCleanupOutcome
    reason: str


class RetryQueueCleanupDecider:
    def decide(self, update_decision: RetryQueueUpdateDecision) -> RetryQueueCleanupDecision: ...
    def decide_all(self, update_decisions: list[RetryQueueUpdateDecision]) -> list[RetryQueueCleanupDecision]: ...


RemoveFn = Callable[[str], RetryQueueResult]


@dataclass(frozen=True)
class RetryQueueCleanupResult:
    decision: RetryQueueCleanupDecision
    attempted: bool
    queue_result: RetryQueueResult | None
    reason: str


class RetryQueueCleanupExecutor:
    def apply(self, decision: RetryQueueCleanupDecision, remove_fn: RemoveFn) -> RetryQueueCleanupResult: ...
    def apply_all(self, decisions: list[RetryQueueCleanupDecision], remove_fn: RemoveFn) -> list[RetryQueueCleanupResult]: ...


# RetryManager（追加分のみ）
def decide_retry_queue_cleanup(self, events: list[SchedulerEvent], dry_run: bool = False) -> list[RetryQueueCleanupDecision]: ...
def apply_retry_queue_cleanup(self, events: list[SchedulerEvent], dry_run: bool = False) -> list[RetryQueueCleanupResult]: ...
```

---

## 6. Sequence（apply_retry_queue_cleanup()）

```
呼び出し元
   │
   ▼
RetryManager.apply_retry_queue_cleanup(events, dry_run)
   │
   ├─► self.decide_retry_queue_cleanup(events, dry_run)
   │        │
   │        ├─► self.decide_retry_queue_updates(events, dry_run)（v4.1.0、無変更）
   │        │        → list[RetryQueueUpdateDecision]
   │        │
   │        └─► self._queue_cleanup_decider.decide_all(update_decisions)
   │                 → list[RetryQueueCleanupDecision]
   │
   └─► self._queue_cleanup_executor.apply_all(cleanup_decisions, remove_fn=self._queue.remove)
            → CLEANUPの項目のみ remove_fn(run_id) を呼び出す
            → list[RetryQueueCleanupResult]
```

`decide_retry_queue_updates()`は内部で`execute_dispatchable_retries()`
（v4.0.0、再実行の実行を含む）を呼び出すため、`apply_retry_queue_removals()`
（v4.2.0）と`apply_retry_queue_cleanup()`（本Release）を同じ`events`に対して
両方呼び出すと、再実行が2回実行される点は既存の`apply_retry_queue_removals()`
自体が持つ設計上の性質であり、本Releaseで新たに導入するものではない
（v4.0.0〜v4.2.0の既存の呼び出しグラフ構造をそのまま踏襲する）。

---

## 7. Boundary（今回入れない境界線）

* `RetryQueueCleanupDecider` / `RetryQueueCleanupExecutor`は
  `RetryQueueManager` / `NullRetryQueueManager`型への直接依存を持たない
* Dead Letter Queue・隔離Queueといった新しいQueueステータスの追加は
  行わない。既存の`RetryQueueStatus`（`CANCELLED`）のみを経由する
* `COMPLETE` / `FAIL`判定の再実行・二重チェックは行わない
  （v4.2.0の`apply_retry_queue_removals()`の責務のまま）
* `NOT_FOUND` / `DISABLED`由来の`NOOP`のCleanupは対象外のまま
  （Project Charterで明示的にスコープ外と確定済み）
* Cleanup基準のカスタマイズ（猶予期間・優先度に基づく選別等）は行わない

---

## 8. Future Extension

* `NOT_FOUND` / `DISABLED`由来の`NOOP`のCleanup方針の検討
  （本Foundationでは意図的に対象外としたが、運用実績次第では次Release
  以降の検討事項となり得る）
* Dead Letter Queueの導入（Cleanupではなく隔離を選ぶ場合の代替設計）
* Cleanup実行の定期スケジューリング（Composition Root）
* Cleanup件数・滞留時間のMetrics化

---

## 9. Compatibility

* `RetryManager.__init__` / `from_config()`への
  `queue_cleanup_decider` / `queue_cleanup_executor`引数追加は末尾の
  デフォルト値付き引数のみであり、既存呼び出し（新規引数を渡さない場合）
  は本Release後もまったく同じ結果になる
* `retry()` / `enqueue_retry()` / `dequeue_retry()` /
  `recognize_retry_events()` / `dispatch_retry_events()` /
  `execute_dispatchable_retries()` / `decide_retry_queue_updates()` /
  `apply_retry_queue_removals()`（`RetryManager` / `NullRetryManager`とも）
  は1行も変更していない

---

## 10. Design Decisions（設計判断の根拠）

1. **入力はv4.1.0の`RetryQueueUpdateDecision`のリストとし、`RetryExecutionResult`
   やそれ以前のデータへは遡らない。** `RetryQueueUpdateDecision`は
   `execution_result`（＝`RetryExecutionResult`）を分解せずに保持して
   おり、`update_decision.execution_result.retry_result.outcome`経由で
   追加の突き合わせなしに`SKIPPED`由来かどうかへ到達できる
2. **`COMPLETE` / `FAIL`をKEEPとする。** v4.2.0の`apply_retry_queue_removals()`
   が既に除去しているはずの項目であり、本Foundationでの再判定・二重の
   `remove()`呼び出しは行わない（Single Responsibility）
3. **remove操作は`remove_fn: Callable[[str], RetryQueueResult]`として
   関数で受け取る。** v4.0.0`RetryExecutionCoordinator`の`retry_fn`・
   v4.2.0`RetryQueueRemovalExecutor`の`remove_fn`と同じパターンを継続する
4. **`RetryManager.__init__`が新規コンポーネントをデフォルトで自動生成する。**
   v3.8.0〜v4.2.0で確立された「省略時は安全な実装へ自動フォールバックする」
   方式を踏襲する
5. **`NullRetryManager`にも同名の委譲メソッドを追加し、常に空リストを返す。**
   既存の`apply_retry_queue_removals()`等と一貫した「受け取れるが何もしない」
   方式を踏襲する
6. **CLEANUP/KEEP判定結果はリストから除外せず、`outcome`フィールドで
   明示する。** `RetryQueueUpdateDecision`・`RetryQueueRemovalResult`が
   採用してきた「NOOP/非対象の項目も結果リストに含め、`attempted`等で
   判別可能にする」方式と一貫させる

---

## 11. Architecture Review

**結論：Approve with Recommendations**

* 本設計（Decider/Executor分離、`remove_fn`を関数として受け取る、
  既存`RetryQueueUpdateDecision`を入力とする）は、v4.1.0・v4.2.0の
  既存パターンと一貫しており、承認する
* **Recommendation（反映済み）**：`CLEANUP`パターンと`KEEP`パターンの
  双方について、それぞれ独立した単体テストとして固定化すること。
  特に`KEEP`は「`COMPLETE` / `FAIL`」「`NOOP`だが`NOT_FOUND`」
  「`NOOP`だが`DISABLED`」の3種の由来を区別して個別に確認すること
  → `tests/test_e2e_v4_3_0_retry_queue_cleanup_foundation.py`テスト1-5・
    25-27で反映済み

---

## 12. Status

- [x] Project Charter 確定（ユーザー承認済み）
- [x] Architecture Design 確定（本文書、Architecture Review完了・
      Approve with Recommendations）
- [x] 実装（`retry_queue_cleanup_decider.py` / `retry_queue_cleanup_executor.py` /
      `retry_manager.py` / `__init__.py`）
- [x] 単体テスト（CLEANUP/KEEP双方のパターンを含む108件）全PASS
- [x] ドキュメント更新（CHANGELOG / ROADMAP）
