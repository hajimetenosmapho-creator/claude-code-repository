# v5.0.0 Retry Enqueue Guard Refinement Foundation 設計書（Project Charter / Architecture Design）

作成日：2026-07-09
状態：確定（Architecture Review Final・ユーザー承認済み・実装完了）

---

## 1. Project Charter

### 1.1 目的

`RetryEnqueueGuard`（v4.8.0）の判定基準を、「再試行履歴が1回でもあればBLOCK」
という二値判定から、「`next_attempt > max_attempts` ならBLOCK」という回数比較
判定へ精緻化する。これにより、v4.9.0（Retry Attempt Synchronization Foundation）
で配線済みだった`retry_attempt`の実回数連動に、初めて実際の消費者を与える。

### 1.2 背景

v4.9.0時点では`RetryEnqueueTrigger`が`next_attempt`（実際の試行回数+1）を正しく
算出してQueueへ渡すようになっていたが、`RetryEnqueueGuard`が依然として「履歴の
有無」の二値判定のままだったため、`RETRY_MAX_ATTEMPTS`（`max_attempts`）を活かした
複数回リトライは実質機能しないままだった（v4.9.0 Known Issue）。

### 1.3 Non-Goal（本Releaseで実施しないこと）

* Composition Root（`RetryEnqueueTrigger`の定期実行導線、`RetryPolicy.from_env()`
  の値を実際に注入する起動スクリプト）
* `RetryPolicy` / `RetryExecutionCoordinator` / `RetryManager`への変更
* `RetryEnqueueOptions`等のDTO（Immutable Value Object）の導入（12章参照）
* `.env.example`整備

---

## 2. Architecture Design

### 2.1 変更対象

```
src/retry_enqueue_trigger/retry_enqueue_guard.py
    RetryEnqueueGuard.decide()  ★変更（シグネチャ・判定式）

src/retry_enqueue_trigger/retry_enqueue_trigger.py
    RetryEnqueueTrigger.enqueue_pending_failures()  ★変更（引数追加・呼び出し順序）
    RetryEnqueueTrigger.__init__  無変更
```

以下は無改修：`RetryHistoryManager` / `NullRetryHistoryManager` / `RetryQueueManager` /
`WorkflowMonitorManager` / `RetryPolicy` / `RetryManager`（`retry_engine`パッケージ
全体）。

### 2.2 Design Policy（Architecture Review Finalで確定した方針）

1. **`RetryEnqueueGuard`はプリミティブ値のみを受け取る**：
   `decide(run_id: str, next_attempt: int, max_attempts: int) -> RetryEnqueueGuardDecision`。
   `next_attempt > max_attempts`ならBLOCK、そうでなければALLOW。`RetryHistoryManager`型は
   もちろん`RetryPolicy`（`retry_engine`）型も一切importしない。

2. **`max_attempts`は`RetryEnqueueTrigger.__init__`ではなく`enqueue_pending_failures()`
   の呼び出し引数として受け取る**：
   `enqueue_pending_failures(limit: int | None = None, max_attempts: int = 1)`。
   Triggerはこの値をインスタンス状態として保持しない（呼び出しが終われば破棄される）。
   これにより`RetryEnqueueTrigger.__init__`のシグネチャは本Releaseでも完全に無変更となる
   （既存の`limit`引数と同じ「呼び出しの都度渡す」スタイルに統一）。

3. **`next_attempt`はGuard判定・Queue登録の両方に使う共通の値として1箇所で算出する**：
   `history_record = self._history.get(run_id)` → `next_attempt = (history_record.attempt_count
   if history_record else 0) + 1`。v4.9.0から算出ロジック自体は変更しないが、Guard呼び出しの
   直前に確定させる（v4.9.0時点はGuard判定後にQueue登録用として別途算出していた）。

4. **`max_attempts`のデフォルト値`1`は、`RetryPolicy.max_attempts`（デフォルト3）とは
   意図的に独立した値である**：`RetryPolicy.max_attempts`は`retry_engine`内で完結する
   業務ルールであり、`RetryEnqueueTrigger`は`retry_engine`への依存を避けるという
   既存方針（v4.6.0 Design Policy #2）を優先するため、これを直接参照しない。
   `max_attempts=1`という既定値は「呼び出し元が明示的に業務ルールを注入しなかった場合の
   構造的セーフガード」であり、v4.8.0/v4.9.0時点とまったく同じ安全側の挙動
   （履歴が1件でもあれば以降ブロック）を再現する。

5. **既存の判定ロジック（status判定・exists判定）は1行も変更しない**：Guard判定の
   入力を差し替えるのみで、既存の`if / continue`構造には手を加えない。

### 2.3 Data Flow

```
① RetryEnqueueTrigger(monitor, queue, history=..., guard=...)
   max_attemptsはここでは一切登場しない（__init__は無変更）
        ↓
② enqueue_pending_failures(limit=..., max_attempts=...) 呼び出し
   max_attempts省略時は1（v4.8.0/v4.9.0と同一挙動）
        ↓
③ monitor.list_status(limit) → FAILED/TIMEOUTのみ抽出（無改修）
        ↓
④ 各run_idについて history.get(run_id) から
   next_attempt = (history_record.attempt_count if history_record else 0) + 1 を算出
        ↓
⑤ guard.decide(run_id, next_attempt=next_attempt, max_attempts=max_attempts)
   → next_attempt > max_attempts なら BLOCK、そうでなければ ALLOW
        ↓
⑥-a BLOCK：skipped_history をインクリメントし次のrecordへ
⑥-b ALLOW：queue.exists() → 未存在なら queue.enqueue(..., retry_attempt=next_attempt)
        ↓
⑦ RetryEnqueueTriggerResult を返す（フィールド構成は無変更）
```

---

## 3. Architecture Review（Final）

**結論：Approve**

| 観点 | 判定 |
|---|---|
| Stateless | ✅ `RetryEnqueueGuard`はプリミティブ値のみで判定。`RetryEnqueueTrigger`は`max_attempts`をインスタンス状態として保持しない |
| Single Responsibility | ✅ Triggerの責務（値の解決・Guard委譲・enqueue）は変わらず、設定値の長期保持という別の責務を持たない |
| Composition | ✅ `max_attempts`は呼び出し境界（`limit`と同じ位置づけ）でのみ注入される |
| Dependency Direction | ✅ `retry_enqueue_trigger → retry_engine`の新規依存は発生しない |
| Backward Compatibility | ✅ `__init__`は完全無変更。`enqueue_pending_failures()`は末尾デフォルト引数の追加のみ |
| Foundation First | ✅ Composition Root・DTO導入はいずれも対象外のまま |
| Small Release | ✅ 変更ファイルは2つのみ。新規ファイル追加なし |

---

## 4. Compatibility

* 変更ファイルは`src/retry_enqueue_trigger/`配下2ファイル（新規ファイルなし）
* `retry_history` / `retry_queue` / `workflow_monitor` / `retry_engine`への変更は
  一切ない（ゼロ改修）
* `RetryEnqueueTrigger.__init__`は**完全に無変更**（引数追加すら発生しない）
* `enqueue_pending_failures()`への引数追加（`max_attempts: int = 1`）は末尾の
  デフォルト値付きのみであり、既存の`enqueue_pending_failures()` /
  `enqueue_pending_failures(limit=10)`という呼び出しは本Release後も
  まったく同じ挙動になる
* `RetryEnqueueGuard.decide()`のシグネチャは意図的に変更する（`has_history: bool`を
  廃止し`next_attempt: int` / `max_attempts: int`を新設）。`RetryEnqueueGuard`は
  `RetryEnqueueTrigger`専属の内部コンポーネントであり他パッケージから単独参照
  される想定がないため（v4.8.0設計書5章）、影響範囲は`RetryEnqueueTrigger`自身と
  v4.8.0/v4.9.0の既存テストに閉じる（6章参照）

---

## 5. Known Issue（本Releaseでも未解消）

* **Composition Root未接続のため、本Release単体では複数回リトライは有効化されない**。
  `max_attempts`のデフォルトは`1`（安全側）のままであり、実際に複数回リトライを
  機能させるには、呼び出し元が`RetryPolicy.from_env().max_attempts`等の値を
  `enqueue_pending_failures(max_attempts=...)`へ明示的に渡す必要がある
  （引き続き将来Release）
* **`max_attempts`のデフォルト値がプロジェクト内に2箇所存在する**：
  `RetryPolicy.from_env()`のデフォルト`3`（環境変数`RETRY_MAX_ATTEMPTS`、業務ルール）と、
  `RetryEnqueueTrigger.enqueue_pending_failures()`のデフォルト`1`（ハードコード、
  `retry_engine`非依存を保つための構造的セーフガード）。これは未整理の技術的負債では
  なく、2.2節Design Policy #4で述べた通り意図的に分離した値である
* `RetryEnqueueGuard.decide()`のシグネチャ変更に伴い、v4.8.0の既存テスト
  （`tests/test_e2e_v4_8_0_retry_enqueue_guard.py`）はテスト1で`TypeError`により
  中断する。v4.9.0の既存テスト（`tests/test_e2e_v4_9_0_retry_attempt_synchronization_
  foundation.py`）もテスト2で、カスタムGuard（`_AlwaysAllowGuard`）のシグネチャが
  旧`has_history`のままのため`TypeError`により中断する。いずれも既存の`[KI-3]`〜
  `[KI-17]`と同種の意図的な既知差分だが、従来のような「assertion FAILのカウント」
  ではなく、シグネチャ不一致による例外中断という形で現れる点が異なる（docs/CHANGELOG.md
  `[KI-18]`参照）

---

## 6. Future Architecture Consideration

本Releaseでは`enqueue_pending_failures()`にGuard判定用の値として`limit`・
`max_attempts`の2引数のみを渡す設計を採用した。しかし、この呼び出し境界に渡す値は
将来的に増える可能性がある。想定される追加候補：

* `retry_delay`（再試行までの最小待機時間）
* `batch_size`（1回の走査でenqueueする上限件数）
* `priority`（Queueへの優先度指定）
* `timeout`（Guard判定・enqueue処理自体のタイムアウト）
* scheduling options（実行対象時間帯の制約等）

これらのように、Retry Enqueueに関わるPolicy値が**複数**に増えた段階では、素朴な
引数の羅列は可読性・呼び出し側の引数順序ミスリスクの両面で限界を迎える。その時点で、
以下のようなImmutable Value Object（Policy Snapshot）の導入を再検討する。

```python
@dataclass(frozen=True)
class RetryEnqueueOptions:
    max_attempts: int = 1
    retry_delay: timedelta | None = None
    batch_size: int | None = None
    # ... 将来必要になった値のみを追加
```

導入する場合も、既存の`RetryQueueUpdateDecision` / `RetryEnqueueGuardDecision`と
同じ「`frozen=True`の`dataclass`」という本プロジェクト内で確立済みの設計言語を
踏襲する（新しいパターンを持ち込まない）。

### DTOを採用しない理由（本Releaseでは見送る）

* 現時点でRetry Enqueueに渡すPolicy値は`max_attempts`の1項目のみであり、複数値を
  まとめる動機（引数の増加による可読性低下）がまだ発生していない
* 保持する値が1つしかない状態でDTOを導入しても、`options.max_attempts`という
  間接参照が増えるだけで、単一の`int`引数より複雑になる。YAGNI
  （You Aren't Gonna Need It）に反する
* Development Charter 8章「抽象化は必要になってから行う」に明確に反する
* 本Releaseは「Retry Enqueue Guard Refinement」という単一目的のFoundation Release
  であり、将来の拡張を先取りしたDTO設計を持ち込むことは、Foundation First・
  Small Releaseの原則から外れた過剰設計になる

### 将来DTOを導入する判断基準

以下のいずれかに該当した時点で、`RetryEnqueueOptions`（または`RetryEnqueueContext`）
導入のCharter作成を検討する。

1. `enqueue_pending_failures()`へ渡すPolicy値が**具体的に2件以上**追加される
   必要が生じた時点
2. 追加されるPolicy値の一部が省略可能・一部が必須など、単純な位置引数/キーワード
   引数の並びでは呼び出し側の意図が読み取りにくくなった時点
3. `RetryEnqueueTrigger`以外の呼び出し元（例：将来のComposition Root・別のAdapter）
   が同じPolicy値の組を再利用する必要が生じ、値の集合として名前を与える価値が
   明確になった時点

逆に、上記に該当しない限り、素朴な引数のままで維持し、先回りしたDTO導入は行わない。

---

## 7. Status

- [x] Architecture Review 完了（Final、ユーザー承認済み）
- [x] Implementation
- [x] Unit / E2E Test（`tests/test_e2e_v5_0_0_retry_enqueue_guard_refinement_foundation.py`）
- [x] Regression確認
- [x] Documentation更新
