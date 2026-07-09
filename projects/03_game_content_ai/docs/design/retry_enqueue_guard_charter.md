# Project Charter — Release 4.8「Retry Enqueue Guard」

作成日：2026-07-09
状態：ドラフト作成（Claude Code、自己レビュー待ち）
対象：`RetryHistoryManager`（v4.7.0）が記録した再試行履歴を`RetryEnqueueTrigger`
（v4.6.0）が参照し、既に再試行済みの`original_run_id`を再enqueueしないようにする
新規Decider `RetryEnqueueGuard` を新設する。v4.6.0 Known Issue（無限再投入リスク）・
v4.7.0 Future Extension「Retry Enqueue Guard」の完成にあたる。

---

## 1. Background

* v4.6.0（Retry Enqueue Trigger Foundation）は、`WorkflowMonitorManager`が判定した
  `FAILED` / `TIMEOUT`を検知し、`RetryQueueManager.exists()`による重複確認のみを
  行ったうえで`enqueue()`する`RetryEnqueueTrigger`を新設した。この時点で、
  「Queueから除去された`run_id`が、Monitor上でなお`FAILED` / `TIMEOUT`のまま
  観測され続けると無限に再enqueueされうる」という既知の欠陥（Known Issue、
  `docs/design/retry_enqueue_trigger_foundation.md` 11章）が明記された。
* v4.7.0（Retry History Foundation）は、この対策の土台として`original_run_id`ごとの
  再試行履歴（試行回数・直近記録時刻）を記録するだけの新規独立パッケージ
  `src/retry_history/`を新設した。ただし記録のみに留め、`RetryEnqueueTrigger`側からの
  参照・ガード判定は次Release以降に送っている（`docs/design/retry_history_foundation.md`
  10章 Future Extension「Retry Enqueue Guard」）。
* v4.7.0 Project Charterの冒頭注記が明示するとおり、**Composition Root（実運用の
  定期実行導線）を先に実装すると、この欠陥に実際に発火する主体を与えてしまう**。
  本Releaseはその前に対策を完成させる、という位置づけである。

### 1.1 対策の必要性についての追加調査（本Charter作成時に実施）

`docs/design/retry_enqueue_trigger_foundation.md` 11章は対策候補として
「`metadata["retried_from"]`を手掛かりにする案」と「`RetryPolicy.max_attempts`を
`RetryEnqueueTrigger`側でも参照する案」の2つを挙げていた。前者はv4.7.0で
実現不可能と判明済み（`WorkflowExecutionRecord`に`metadata`フィールドが存在しない）。
後者は本Charter作成時に、単なる設計上の選択の問題ではなく、**実際に安全性上の
必要条件であること**が以下のコード調査で判明した。

* `RetryEnqueueTrigger.enqueue_pending_failures()`（`retry_enqueue_trigger.py` 78行目）
  は`self._queue.enqueue(run_id=record.run_id, workflow_name=record.workflow_name)`を
  呼び出しており、`retry_attempt`を明示的に渡していない。
* `RetryQueueManager.enqueue()`（`retry_queue_manager.py` 54-58行目）の
  `retry_attempt: int = 1`はデフォルト値であり、`RetryEnqueueTrigger`経由のenqueueは
  **常に`retry_attempt=1`固定**でQueueへ投入される。
* 下流の`RetryExecutionCoordinator.execute()`（`retry_execution_coordinator.py`
  60-61行目）は`attempt = getattr(candidate, "retry_attempt", 1)`でQueue項目から
  `attempt`を取得し、`RetryManager.retry(run_id, attempt=attempt, ...)`を呼び出す。
* `RetryPolicy.should_retry()`（`retry_policy.py` 45-47行目）は
  `monitor_status in target_statuses and attempt < max_attempts`で判定する。
  `RETRY_MAX_ATTEMPTS`のデフォルトは3であるため、`attempt=1 < 3 = True`が
  **毎回**成立する。

つまり、現状のコードは`original_run_id`が実際に何回再試行されたかを
`RetryPolicy`側の`attempt`判定に一切反映しない構造になっている（`attempt`は
Queueへのenqueue時点の固定値1のまま、実際の累積試行回数と連動しない）。
この状態で無対策のままComposition Rootが実運用化されると、`RetryPolicy`の
`max_attempts`（試行回数の上限）は実質的に機能せず、**同一`original_run_id`に
対する完全な再実行（News収集・WordPress下書き投稿等の実際の副作用を伴う
Workflow実行）が、Workflow Monitor上のステータスが変化しない限り、
Enqueue Triggerが呼ばれるたびに無制限に繰り返される**。

本Releaseが新設する`RetryEnqueueGuard`（`RetryHistoryManager.has_history()`を
参照し、一度でも再試行履歴がある`original_run_id`のenqueueを拒否する）は、
この問題に対する唯一の現実的なセーフティネットである（`attempt`の実回数連動は
本Release後も引き続き未実装であり、10章 Non-Goalsに明記する）。

```
WorkflowMonitorManager（判定、v2.9.0、無改修）
   │
   ▼
RetryEnqueueTrigger（Adapter、v4.6.0、拡張）
   │
   ├── RetryEnqueueGuard（判定、v4.8.0、新規） ★本Release
   │      └── RetryHistoryManager.has_history()（v4.7.0、無改修）を参照
   │
   └── RetryQueueManager.enqueue()（v3.1.0、無改修）
```

---

## 2. Purpose

`original_run_id`について既に1回以上の再試行履歴（`RetryHistoryManager`が記録した
`RETRIED`実績）が存在する場合、`RetryEnqueueTrigger`がそのrun_idを再enqueueしない
ようにする。これにより、v4.6.0 Known Issueで指摘された無限再投入リスクを解消し、
Composition Root（実運用の定期実行導線）を安全に実装できる状態を整える。

---

## 3. Goals

1. `RetryHistoryManager.has_history(original_run_id)`を参照し、既に再試行履歴がある
   run_idのenqueueを拒否する新規Deciderコンポーネント`RetryEnqueueGuard`を
   `src/retry_enqueue_trigger/`配下に新設する
2. `RetryEnqueueTrigger`が`RetryHistoryManager | NullRetryHistoryManager`と
   `RetryEnqueueGuard`をConstructor Injectionで保持できるようにする（末尾の
   デフォルト値付き引数として追加。既存の2引数コンストラクタ呼び出しは無変更で
   動作する）
3. `RetryEnqueueTriggerResult`に、Guardによってスキップされた件数を表す
   `skipped_history`フィールド（デフォルト値0）を追加する
4. `history`省略時は`NullRetryHistoryManager()`にフォールバックし、Guardは常に
   ALLOW（履歴なし相当）を返す。これにより、本Releaseの新規引数を渡さない
   既存の呼び出しは、v4.6.0時点とまったく同じ挙動になる（Backward Compatibility）
5. `retry_history` / `retry_queue` / `workflow_monitor` / `retry_engine`はいずれも
   本Releaseでも無改修とする

---

## 4. Scope

### 対象

* 新規コンポーネント`RetryEnqueueGuard`（`RetryEnqueueGuardOutcome` /
  `RetryEnqueueGuardDecision`を含む）の新設
  （`src/retry_enqueue_trigger/retry_enqueue_guard.py`）
* `RetryEnqueueTrigger`（`retry_enqueue_trigger.py`）の変更：
  * `__init__`に`history` / `guard`引数（いずれも末尾・デフォルト`None`）を追加
  * `enqueue_pending_failures()`にGuard判定の呼び出しを追加（既存のstatus判定・
    exists判定のロジック自体は変更しない）
* `RetryEnqueueTriggerResult`に`skipped_history: int = 0`フィールドを追加
* `NullRetryEnqueueTrigger`は無改修（既存の全フィールド0の戻り値は、新フィールドの
  デフォルト値0がそのまま適用されるため、追加コードなしで整合する）
* `src/retry_enqueue_trigger/__init__.py`の公開シンボル更新
* テスト（新規E2Eテスト・既存回帰確認）
* 関連ドキュメント更新（CHANGELOG / ROADMAP / architecture.md）

### 対象外（今回やらないこと）

* `RetryPolicy.max_attempts`と実際の累積試行回数（`RetryHistoryRecord.attempt_count`）を
  連動させ、`RetryQueueManager.enqueue()`の`retry_attempt`引数へ反映する統合
  （1章1.1節で述べた根本課題。本Releaseは「1回再試行済みなら再enqueueしない」という
  Guardのみを実装し、複数回のRetryを許容する`max_attempts>1`の運用を安全に
  活かす仕組みは次Release以降の課題とする）
* Composition Root本体（`RetryEnqueueTrigger`を定期的に呼び出す起動スクリプト）
* `retry_engine`（`RetryManager`等）への変更（本Releaseは`retry_enqueue_trigger`
  パッケージ内で完結する）
* `RetryHistoryManager`側の変更（`retry_history`パッケージは無改修）
* Feature Gate・Configクラスの新設
* 永続化

---

## 5. Design Principles

* **Foundation First**：v4.6.0 Known Issueの解消に限定し、Composition Root・
  `attempt`実回数連動はいずれも次Release以降へ送る
* **Single Responsibility**：`RetryEnqueueGuard`は「再試行履歴の有無からALLOW/BLOCKを
  判定する」1つの責務のみを持つ。`RetryHistoryManager`への実際の問い合わせ（外部状態の
  参照）は`RetryEnqueueTrigger`側の責務のまま残し、`RetryEnqueueGuard`自体は
  完全にStateless（外部パッケージ型への直接依存を一切持たない）とする
* **Stateless**：`RetryEnqueueGuard`はコンストラクタ引数を取らず、`decide(run_id,
  has_history)`のように既に解決済みの値のみを入力とする、既存の
  `RetryQueueUpdateDecider` / `RetryQueueCleanupDecider`と同じ設計言語を踏襲する
* **Backward Compatibility**：`RetryEnqueueTrigger.__init__` / `RetryEnqueueTriggerResult`
  への変更は、いずれも末尾のデフォルト値付き引数・フィールドの追加のみとし、
  既存の呼び出し（v4.6.0時点の2引数コンストラクタ呼び出し・5フィールド参照）は
  本Release後もまったく同じ挙動になる
* **既存アーキテクチャとの整合性**：`RetryEnqueueGuard`は、`RetryQueueCleanupDecider`
  （v4.3.0）・`RetryQueueTerminalCleanupDecider`（v4.4.0）と同型（Enum + frozen
  dataclass + Stateless Deciderクラス）の構成とする。プロジェクト全体で一貫している
  「新しい判定は新しい小さなDeciderを追加し、既存クラスへは薄い委譲のみを足す」という
  設計言語を、`retry_engine`外（`retry_enqueue_trigger`パッケージ内）でも踏襲する
* **依存方向**：`retry_enqueue_trigger → retry_history`の新規一方向依存を追加する
  （`RetryEnqueueTrigger`が`history`引数の型として`RetryHistoryManager` /
  `NullRetryHistoryManager`を参照する）。`RetryEnqueueGuard`自体は`retry_history`を
  一切importしない（`has_history: bool`という既に解決済みの値のみを受け取るため）

---

## 6. Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryEnqueueGuard`（新設） | `run_id`と`has_history`（bool）から、enqueueを許可するか拒否するかを判定する | `RetryHistoryManager`への問い合わせ・Queueへのenqueue実行・Monitor状態の判定 |
| `RetryEnqueueTrigger`（既存、拡張） | `WorkflowMonitorManager` / `RetryQueueManager`に加え、`RetryHistoryManager` / `RetryEnqueueGuard`への参照を保持し、検知・Guard判定・重複確認・enqueueへの薄い委譲を行う | Guard判定ロジック自体の実装（`RetryEnqueueGuard`の責務）・再試行履歴の記録（`RetryManager.record_retry_history()`の責務） |
| `RetryHistoryManager`（v4.7.0、無改修） | 引き続き再試行履歴の記録・参照のみを行う | Guard判定・Queue操作 |
| `RetryQueueManager`（v3.1.0、無改修） | 引き続きQueue管理のみを行う | Guard判定・履歴参照 |

---

## 7. Dependencies

```
retry_enqueue_trigger  ──→  retry_history（新規。RetryHistoryManager /
                             NullRetryHistoryManager型の参照のみ。RetryEnqueueTrigger
                             が保持する）
retry_enqueue_trigger  ──→  workflow_monitor（既存、v4.6.0、無改修）
retry_enqueue_trigger  ──→  retry_queue（既存、v4.6.0、無改修）
retry_history           ──→  （なし。標準ライブラリのみ、独立した葉パッケージ、無改修）
```

`RetryEnqueueGuard`自体はいかなる外部パッケージもimportしない（`retry_enqueue_trigger`
パッケージ内の`RetryEnqueueTrigger`からのみ利用される内部コンポーネント）。循環importは
発生しない（`retry_history`は`retry_enqueue_trigger`を知らない）。

---

## 8. Open Questions（ユーザー確認事項）

1. **Guardの判定基準を「履歴の有無（`has_history`のbool）」のみに限定してよいか**：
   `RetryHistoryRecord.attempt_count`と`RetryPolicy.max_attempts`を比較する、より
   精密な判定（例：「max_attempts未満ならALLOW」）も技術的には可能だが、これは
   `retry_enqueue_trigger`パッケージが`retry_engine`（`RetryPolicy`）へ新たに
   依存することを意味し、v4.6.0 Design Policy #2（`retry_engine`を経由しない）との
   整合性を崩す。本Charterは「一度でも再試行履歴があれば以後は再enqueueしない」
   という単純な二値判定を提案する（1章1.1節の根拠どおり、`attempt`が実回数と
   連動していない現状では、これ以上精密な判定を導入しても正しく機能しないため）。
   **提案：単純な二値判定（has_historyのみ）を採用する。**
2. **`skipped_history`カウントの意味論**：Guardによってスキップされた件数を
   `skipped_status` / `skipped_existing`と同じ粒度（対象外理由ごとに排他的な
   カウンタ）で追加してよいか。**提案：既存2フィールドと同じ設計言語を踏襲し、
   `skipped_history`を追加する。**

いずれも本Charterの提案どおりで進めてよいか、Architecture Designに進む前に
承認を得る。

**→ 2026-07-09、ユーザー承認済み。両方とも本Charterの提案どおり（二値判定・
`skipped_history`フィールド追加）で確定した。**

---

## 9. Acceptance Criteria

* `RetryEnqueueGuard.decide(run_id, has_history=True)`が`BLOCK`を返すこと
* `RetryEnqueueGuard.decide(run_id, has_history=False)`が`ALLOW`を返すこと
* `RetryEnqueueTrigger`が、`history`省略時（`None`）は`NullRetryHistoryManager()`に
  フォールバックし、Guardが常に`ALLOW`（`has_history()`が常に`False`のため）を
  返すことで、v4.6.0時点とまったく同じ挙動（`skipped_history`は常に0）になること
* `RetryEnqueueTrigger`が、`history`に実体（`RetryHistoryManager`）を渡し、かつ
  対象run_idに再試行履歴がある場合、その`run_id`について`queue.enqueue()`が
  一度も呼ばれないこと
* `RetryEnqueueTriggerResult`の`scanned = enqueued + skipped_existing +
  skipped_status + skipped_history + failed`が常に成立すること（既存の4フィールドの
  等式にGuardによるスキップ分を追加した形の恒等式）
* `NullRetryEnqueueTrigger`が本Release後も常に全フィールド0（`skipped_history`含む）を
  返すこと
* `retry_history` / `retry_queue` / `workflow_monitor` / `retry_engine`が本Releaseでも
  無改修であること（`git diff`ベースで確認）
* `RetryEnqueueGuard`が`retry_history`パッケージを一切importしないこと（静的検査）
* E2Eテスト全PASS、既存回帰（v2.0.0〜v4.7.0）で新規に発生する差分が、既存の
  `git diff`ベースの一時差分・恒久差分（`[KI-3]`〜`[KI-15]`と同種）のみであること

---

## 10. Non-Goals

* `RetryPolicy.max_attempts`と実際の累積試行回数の統合（1章1.1節・4章参照。
  本Releaseで解消される安全性リスクは「無制限の再enqueue」のみであり、
  「`max_attempts>1`を活かした複数回リトライの運用」自体は本Release後も
  実質的に機能しないままである。これは新たなKnown Issueとして11章に明記する）
* Composition Root本体
* `RetryHistoryManager`の永続化
* Feature Gate・Configクラスの新設

---

## 11. Risks and Mitigations

| リスク | 対策 |
|---|---|
| 本Releaseは「一度でも再試行されたrun_idは二度と自動enqueueされない」という強い制約を導入する。`RETRY_MAX_ATTEMPTS`（デフォルト3）を活かした複数回の自動リトライ運用は、本Release後も`RetryEnqueueTrigger`経由では実現できないままになる | 1章1.1節の技術的根拠（`retry_attempt`が実回数と連動していない）を踏まえ、意図的な安全側の設計判断として明記する。複数回リトライの運用を実現する場合は、`attempt`の実回数連動（4章 対象外）を別Releaseで先に実装する必要があることをKnown Issueとして残す |
| `RetryEnqueueTrigger`のコンストラクタ引数が2個から4個に増える（`history` / `guard`が追加）。将来さらに引数が増え続けると可読性が落ちる懸念 | 現時点では許容範囲（`RetryManager.__init__`は既に10個以上の引数を持つ前例がある）。将来的にConfigオブジェクトへの集約が必要になった場合は、そのタイミングで再設計する（Development Charter 8章「拡張性に関する考え方」：抽象化は必要になってから行う） |

---

## 12. Status

- [x] Project Charter ドラフト作成（本文書、Claude Code作成）
- [x] ユーザー承認（Open Questions 2点とも本Charterの提案どおりで確定）
- [x] Architecture Design
- [x] Architecture Review
- [ ] Implementation（ユーザー承認後、次Sessionで着手）
