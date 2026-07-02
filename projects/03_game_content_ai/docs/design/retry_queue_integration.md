# v3.2.0 Retry Queue Integration 設計書（Architecture Design）

作成日：2026-07-02（Architecture Review反映：2026-07-02）
状態：Architecture Review完了（**Approve with Minor Recommendations**）。指摘事項3点を
9.2節（新規E2Eテスト観点）へ反映済み。重大な設計変更は伴わない。
`docs/design/retry_queue_integration_charter.md`（Project Charter、承認済み）を前提とする。
実装コードはまだ作成しない（Architecture Designのみ）。

> **Architecture Review 反映事項（2026-07-02）**：Architecture Reviewの結果、以下3点を
> 9.2節（新規E2Eテストで確認する観点）へ反映した。API・クラス構造の変更は伴わない
> （いずれもテスト観点の追加のみ）。
> 1. `enqueue_retry()`のデフォルト値`retry_attempt=1`が`RetryQueueManager.enqueue()`の
>    デフォルト値と独立して重複定義されているため、両者が一致することを確認するテストを追加
> 2. Fakeベースの単体検証に偏っていたため、実`RetryQueueManager`を使った
>    `enqueue_retry()` → `dequeue_retry()`の往復統合テストを追加
> 3. `retry_queue_manager`を明示的に`NullRetryQueueManager()`インスタンスとして渡した場合と、
>    省略した場合（内部フォールバック）が同じ結果になることを検証するテストを追加
>
> レビューの全文は本Releaseの会話記録を参照。指摘事項以外の7観点（RetryManagerへの責務混入・
> 委譲の薄さ・retry()との非結合・from_config()後方互換性・Null系の責務分離・
> retry_queue無改修・既存Regression影響）はいずれも設計どおりでApprove。

---

## 1. Architecture Overview

Retry Engine（v3.0.0、`src/retry_engine/`）と Retry Queue（v3.1.0、`src/retry_queue/`）は、
これまでそれぞれ独立に完結したFoundationとしてリリースされており、互いを一切importしていない
（`retry_queue`は`retry_engine`の存在を知らず、`retry_engine`も`retry_queue`を呼び出す経路を
持たない）。

本Release（v3.2.0）は、この2つのFoundationの間に**片方向の配線**を1本追加する。

```
Retry Engine（再実行判断・依頼、v3.0.0）
   │
   ├── RetryManager が RetryQueueManager を保持する（DI） ★本Release
   │      ├─ enqueue_retry()  … RetryQueueManager.enqueue() へ委譲
   │      └─ dequeue_retry()  … RetryQueueManager.dequeue() へ委譲
   │
   └── RetryManager.retry()（既存、無改修） ─── Queueとは独立した経路のまま
         │
         ▼
   Workflow Engine（実行、v2.7.0、無改修）

Retry Queue（Queue管理、v3.1.0、無改修）
```

配線は`retry_manager.py`の変更のみで完結し、`src/retry_queue/`配下は1バイトも変更しない
（6章で詳述）。`RetryManager.retry()`（Workflow再実行の判定・実行）と、新設する
`enqueue_retry()` / `dequeue_retry()`（Queueへの出し入れの中継）は、**互いに呼び出し合わない
独立した2つの経路**として共存する（5章で詳述）。

---

## 2. Design Policy

Project Charter の Design Principles を、本設計では次のように具体化する。

1. **委譲のみ・判定ロジックの複製禁止**：`RetryManager`に追加する2メソッドは、
   `RetryQueueManager`の対応するメソッドを呼び、その戻り値をそのまま返すだけとする。
   容量チェック・重複チェック・優先度ソートといったQueue管理上の判断は一切`retry_engine`
   側に持ち込まない（Single Responsibility）。
2. **DIのデフォルトはNull**：`RetryManager`はQueueを渡されなくても構築・動作できる
   （後方互換性）。渡されなかった場合は`NullRetryQueueManager()`を内部で用いることで、
   「Queueを持たない`RetryManager`」ではなく「常にQueueへの参照を持つが、それが
   `NullRetryQueueManager`である`RetryManager`」という一貫した内部構造にする
   （4章 Design Decision #2）。
3. **2つの経路の独立性**：`retry()`（Workflow再実行）と`enqueue_retry()` /
   `dequeue_retry()`（Queue操作）は、`RetryManager`内で状態や呼び出しを共有しない。
   `dequeue_retry()`が返した`RetryQueueItem`を使って実際に再実行するかどうかは、
   **呼び出し元が`RetryManager.retry(item.run_id, attempt=item.retry_attempt)`を
   別途明示的に呼ぶ**という運用を前提とし、`RetryManager`自身がその橋渡しを行うことは
   本Releaseでは一切しない（Charter 8章 Non-Goals）。

---

## 3. Package Structure

```
src/retry_engine/
├── __init__.py             # 無改修（新規公開シンボルなし。RetryQueueManager等はretry_queueから直接import）
├── retry_policy.py         # 無改修
├── retry_config.py         # 無改修
├── retry_request.py        # 無改修
├── retry_result.py         # 無改修
├── retry_executor.py       # 無改修
└── retry_manager.py        # ★変更：RetryManager / NullRetryManager にQueue統合を追加

src/retry_queue/             # 全ファイル無改修（6章）
```

変更ファイルは`retry_manager.py`1点のみ。`__init__.py`にも変更を加えない
（`RetryQueueManager` / `NullRetryQueueManager` / `RetryQueueResult`等を呼び出し元が
使う場合は、`retry_queue`パッケージから直接importする想定であり、`retry_engine`が
それらを再exportする必要はない。10章 Design Decision #5）。

---

## 4. Public API（論点1・2・3・4に対応）

### 4.1 `RetryManager.__init__`（論点2：DIする方法）

```python
def __init__(
    self,
    policy: RetryPolicy,
    executor: RetryExecutor,
    monitor: WorkflowMonitorManager,
    queue: "RetryQueueManager | NullRetryQueueManager | None" = None,
):
    self._policy = policy
    self._executor = executor
    self._monitor = monitor
    self._queue = queue if queue is not None else NullRetryQueueManager()
```

* `queue`引数を末尾に追加し、**デフォルト値`None`**を持たせる。既存の呼び出し
  （`RetryManager(policy=..., executor=..., monitor=...)`、キーワード引数）はそのまま
  動作する（7.1節・8章で確認）。
* `queue=None`の場合、コンストラクタ内部で`NullRetryQueueManager()`にフォールバックする。
  これにより`self._queue`は常に「`enqueue` / `dequeue`を持つオブジェクト」であることが
  保証され、`enqueue_retry()` / `dequeue_retry()`側で`None`チェックが不要になる
  （10章 Design Decision #1）。

### 4.2 `RetryManager.from_config`（論点2・3：DI経路とfrom_config()の後方互換性）

```python
@classmethod
def from_config(
    cls,
    retry_config: RetryConfig,
    retry_policy: RetryPolicy,
    workflow_engine_manager: "WorkflowEngineManager | NullWorkflowEngineManager",
    workflow_monitor_manager: "WorkflowMonitorManager | NullWorkflowMonitorManager",
    retry_queue_manager: "RetryQueueManager | NullRetryQueueManager | None" = None,
) -> "RetryManager | NullRetryManager":
    if not retry_config.is_ready():
        return NullRetryManager()
    if isinstance(workflow_engine_manager, NullWorkflowEngineManager):
        return NullRetryManager()

    executor = RetryExecutor(workflow_engine_manager=workflow_engine_manager)
    return cls(
        policy=retry_policy,
        executor=executor,
        monitor=workflow_monitor_manager,
        queue=retry_queue_manager,  # None のままでよい（__init__ 側でNullにフォールバック）
    )
```

**後方互換性の根拠（論点3）**：

* 新規引数`retry_queue_manager`は**第5引数・デフォルト値`None`**として末尾に追加する。
  既存呼び出しはすべて4引数（`retry_config` / `retry_policy` / `workflow_engine_manager` /
  `workflow_monitor_manager`）で完結しており、位置引数・キーワード引数のいずれの呼び出し
  スタイルでも影響を受けない。
* 既存コード（`tests/test_e2e_v3_0_0_retry_engine_foundation.py`）での実際の呼び出し例：
  ```python
  RetryManager.from_config(RetryConfig(enabled=True), policy_3, fake_engine_19, fake_monitor_19)
  ```
  この4引数の位置引数呼び出しは、5番目の`retry_queue_manager`が省略されデフォルト値`None`
  が使われるため、本Release後もエラーにならず、かつ**戻り値の型・`RetryResult`の入出力仕様は
  一切変わらない**（`retry()`のロジックに変更がないため）。
* ゲート判定ロジック（`retry_config.is_ready()`・`NullWorkflowEngineManager`判定）にも
  変更を加えない。`retry_queue_manager`の状態（有効／無効／未指定）はゲート判定に
  **一切関与しない**（Retry EngineのゲートとRetry QueueのゲートはCharter 5章の設計原則
  どおり独立したまま）。

### 4.3 `RetryManager.enqueue_retry` / `dequeue_retry`（論点1：追加メソッド）

```python
def enqueue_retry(
    self,
    run_id: str,
    workflow_name: str,
    retry_attempt: int = 1,
    priority: int | None = None,
) -> RetryQueueResult:
    """
    再実行対象を Retry Queue へ登録する。RetryQueueManager.enqueue() への委譲のみを行い、
    判定・加工は一切行わない。RetryPolicy／Workflow Monitorへの問い合わせも行わない
    （Queue登録可否の判断はretry_queue側の責務のまま）。
    """
    return self._queue.enqueue(
        run_id=run_id,
        workflow_name=workflow_name,
        retry_attempt=retry_attempt,
        priority=priority,
    )

def dequeue_retry(self) -> RetryQueueResult:
    """
    Retry Queue から再実行対象を1件取り出す。RetryQueueManager.dequeue() への委譲のみを
    行う。取り出した項目に対して retry() を呼ぶかどうかは呼び出し元の判断に委ねられ、
    RetryManager自身は一切自動実行しない（5章）。
    """
    return self._queue.dequeue()
```

* **メソッド名**：`enqueue_retry` / `dequeue_retry`。既存の`RetryQueueManager.enqueue` /
  `dequeue`と紛らわしくならないよう、`RetryManager`側では「retry対象を」であることが
  わかる接尾辞を付けた名前とする（`RetryManager.retry()`との対比で「何をenqueue/dequeue
  するのか」が名前から読み取れることを優先し、`RetryQueueManager`と完全に同名にはしない）。
* **引数**：`RetryQueueManager.enqueue()`の引数（`run_id` / `workflow_name` /
  `retry_attempt` / `priority`）をそのまま踏襲する。`RetryManager`側で独自の引数（例：
  `RetryPolicy`由来のデフォルト値等）を追加しない。
* **戻り値**：いずれも`RetryQueueResult`（`retry_queue`パッケージの既存型）をそのまま
  返す。新しい型・新しい`RetryQueueOutcome`値は追加しない。
* **`remove` / `list` / `exists` / `count`は中継しない**：Charterのスコープ
  （「登録できるようにする」「取得できるようにする」の2操作）に厳密に対応させ、
  それ以外のQueue操作（取り消し・一覧・存在確認・件数）は`RetryManager`からは
  提供しない。それらが必要な呼び出し元は、`RetryQueueManager`インスタンスを
  直接保持して使う（`RetryManager`はあくまで`retry()`の起動口であり、Queueの
  汎用アクセサではないという役割分担を維持する）。

### 4.4 `NullRetryManager`（論点4：NullRetryQueueManagerの扱い）

```python
class NullRetryManager:
    def retry(self, run_id: str, attempt: int = 1, dry_run: bool = False) -> RetryResult:
        # 既存のまま、無改修
        ...

    def enqueue_retry(
        self,
        run_id: str,
        workflow_name: str,
        retry_attempt: int = 1,
        priority: int | None = None,
    ) -> RetryQueueResult:
        return RetryQueueResult(
            outcome=RetryQueueOutcome.DISABLED,
            item=None,
            reason="Retry Engine is disabled (RETRY_ENGINE_ENABLED=false, "
                   "or AI_AGENT_ENABLED/WORKFLOW_ENGINE_ENABLED is not ready).",
        )

    def dequeue_retry(self) -> RetryQueueResult:
        return RetryQueueResult(
            outcome=RetryQueueOutcome.DISABLED,
            item=None,
            reason="Retry Engine is disabled (RETRY_ENGINE_ENABLED=false, "
                   "or AI_AGENT_ENABLED/WORKFLOW_ENGINE_ENABLED is not ready).",
        )
```

* `NullRetryManager`は既存どおり**Queueへの参照を一切持たない**（`RetryQueueManager`も
  `NullRetryQueueManager`も保持しない、フィールドなしの完全なダミーのまま）。
  `RETRY_ENGINE_ENABLED=false`、または下位ゲート（`AI_AGENT_ENABLED` /
  `WORKFLOW_ENGINE_ENABLED`）が閉じている場合は、Queueが有効かどうかに関わらず
  Retry Engine自体が丸ごと無効化されるため、Queueとの接続を持つ意味がない。
* 理由文字列（`reason`）は既存の`retry()`用メッセージと同じ「Retry Engineが無効」を
  示す文言を再利用し、`RetryManager`（実インスタンス）が持つ`NullRetryQueueManager`の
  「Retry Queueが無効」メッセージ（`_DISABLED_REASON = "Retry Queue is disabled
  (RETRY_QUEUE_ENABLED=false)."`）とは**意図的に文言を分ける**。これにより、
  呼び出し元は`reason`文字列から「Retry Engine自体が無効なのか」「Retry Engineは
  有効だがRetry Queueだけが無効なのか」を区別できる（11.3節）。

### 4.5 `RetryManager`（実インスタンス）が`NullRetryQueueManager`を保持する場合

`RETRY_ENGINE_ENABLED=true`だが`retry_queue_manager`を渡さなかった場合、または渡した
`RetryQueueManager`が`RETRY_QUEUE_ENABLED=false`により`NullRetryQueueManager`だった場合、
`RetryManager`（実インスタンス）の`self._queue`は`NullRetryQueueManager`になる。この場合、
`enqueue_retry()` / `dequeue_retry()`は`NullRetryQueueManager`の実装（無改修、
`null_retry_queue_manager.py`）をそのまま呼び出し、`outcome=DISABLED, reason="Retry Queue
is disabled (RETRY_QUEUE_ENABLED=false)."`が返る。これは`retry_queue`パッケージが
v3.1.0ですでに提供している挙動であり、本Releaseで新しく作るロジックではない
（6章：ゼロ改修の確認）。

---

## 5. Queue操作とretry()実行の独立性（論点5）

`enqueue_retry()` / `dequeue_retry()`は、`self._policy` / `self._executor` /
`self._monitor`のいずれにも触れない。逆に`retry()`は`self._queue`に一切触れない。
両者は`RetryManager`という同じクラスに同居するが、**呼び出しグラフ上は完全に分離**している。

```
RetryManager
├── retry(run_id, attempt, dry_run)
│     └── self._monitor.get_status()
│     └── self._policy.should_retry()
│     └── self._executor.execute()
│            └── self._executor._engine.run()   … Workflow Engineへ到達する唯一の経路
│
├── enqueue_retry(run_id, workflow_name, retry_attempt, priority)
│     └── self._queue.enqueue()                  … retry()/self._executor/self._monitorには
│                                                     一切到達しない
│
└── dequeue_retry()
      └── self._queue.dequeue()                  … 同上
```

`dequeue_retry()`が返す`RetryQueueResult.item`（`RetryQueueItem`）には`run_id`が含まれるが、
それを使って`self.retry(item.run_id)`を呼び出す処理は`RetryManager`のどのメソッドにも
実装しない。この「取り出した後どうするかは呼び出し元が決める」という境界線が、
Charter Non-Goal「Queueから取り出した項目を自動的にretry()する仕組み」を満たす
構造的な担保になる。12章 Testing Strategyで、Fakeオブジェクトを用いてこの独立性を
振る舞いレベルで検証する。

---

## 6. `src/retry_queue/` 無改修の確認（論点6）

* `retry_manager.py`が`retry_queue`パッケージから追加でimportするのは、既存の公開
  シンボル（`retry_queue/__init__.py`の`__all__`に含まれる）のうち
  `RetryQueueManager` / `NullRetryQueueManager` / `RetryQueueResult` / `RetryQueueOutcome`
  の4つのみであり、いずれもv3.1.0時点ですでに確定・公開済みのAPIである。
* `RetryQueueManager.enqueue()` / `dequeue()`のシグネチャ・戻り値の意味を変更する必要は
  一切ない（4.3節の`enqueue_retry` / `dequeue_retry`はこれらを無改造のまま呼ぶだけ）。
* したがって`src/retry_queue/`配下7ファイル（`__init__.py` /
  `retry_queue_status.py` / `retry_queue_item.py` / `retry_queue_result.py` /
  `retry_queue_config.py` / `retry_queue_manager.py` / `null_retry_queue_manager.py`）は
  **1バイトも変更しない**。Acceptance Criteria（13章）・Testing Strategy（12章）の両方で
  `git diff --stat src/retry_queue/`が空であることを機械的に確認する。

---

## 7. Dependency Diagram

```
src/retry_engine/   ─── import ───→  src/retry_queue/
                                      （公開APIのみ：RetryQueueManager / NullRetryQueueManager /
                                       RetryQueueResult / RetryQueueOutcome）

src/retry_engine/   ─── import ───→  src/workflow_monitor/   （既存、無改修）
src/retry_engine/   ─── import ───→  src/workflow_engine/    （既存、無改修）

src/retry_queue/    ─── import ───→  （なし。標準ライブラリのみ、無改修）
```

依存関係全体は次のDAGになる（矢印は「importする」方向）。

```
retry_engine ──→ workflow_engine ──→ ai, pipeline, execution_history
      │
      ├──────→ workflow_monitor ──→ execution_history
      │
      └──────→ retry_queue            ★本Releaseで新規追加される辺
```

`retry_queue`が`retry_engine`を参照する辺は存在しない（6章のとおり`retry_queue`は
無改修であり、そもそも`retry_engine`の存在を知らない）。循環importは発生しない。

---

## 8. 既存呼び出しへの影響（回帰確認、論点3・7の補足）

`RetryManager` / `NullRetryManager`への現在の直接的な呼び出し元は
`tests/test_e2e_v3_0_0_retry_engine_foundation.py`のみである（他パッケージ・
`scripts/`からの利用は現時点で存在しない）。同ファイル内の呼び出しパターンは
以下の3種類に大別される。

1. `RetryManager(policy=..., executor=..., monitor=...)`（コンストラクタ直接呼び出し、
   キーワード引数）→ `queue`引数を渡していないため、4.1節の`queue: ... = None`の
   デフォルト値がそのまま適用され、`self._queue = NullRetryQueueManager()`になる。
   `retry()`の呼び出し結果には一切影響しない（`retry()`は`self._queue`を参照しない）。
2. `RetryManager.from_config(retry_config, policy, engine_manager, monitor_manager)`
   （4引数の位置引数呼び出し）→ 4.2節のとおり、5番目の`retry_queue_manager`は
   省略されデフォルト値`None`が使われる。戻り値の型・`retry()`の挙動は変更なし。
3. `NullRetryManager()` → 変更なし（コンストラクタ自体に変更なし）。

いずれのパターンも、既存テストのコードを1行も変更せずにそのまま実行できる
（12章「既存回帰確認」）。

---

## 9. Testing Strategy（論点7・8：影響範囲と新規E2Eの観点）

### 9.1 既存テストへの影響範囲（論点7）

* `tests/test_e2e_v3_0_0_retry_engine_foundation.py`：**無変更のまま全PASSすること**を
  回帰確認する。8章で述べたとおり、既存の呼び出しパターンはすべて新規引数の
  デフォルト値でカバーされる。
* `tests/test_e2e_v3_1_0_retry_queue_foundation.py`：`retry_queue`パッケージ自体を
  一切変更しないため、**無変更のまま全PASSすること**を回帰確認する（この点は
  「差分がないこと」の確認そのものであり、テスト内容は本Releaseの影響を受けない）。
* `tests/test_e2e_v2_0_0_ai_agent_foundation.py`〜
  `tests/test_e2e_v2_9_0_workflow_monitor_foundation.py`・
  `tests/test_e2e_v1_20_0_ai_workflow_foundation.py`：`workflow_engine` /
  `workflow_monitor` / `execution_history`等いずれも本Releaseで変更しないため、
  影響なし（既存回帰スイートとしてそのままPASSすることを確認する）。

### 9.2 新規E2Eテストで確認する観点（論点8）

新規ファイル`tests/test_e2e_v3_2_0_retry_queue_integration.py`で、以下を確認する。

**(a) DI・後方互換性**

* `RetryManager(policy=..., executor=..., monitor=...)`（`queue`省略）で構築した
  インスタンスの`enqueue_retry()` / `dequeue_retry()`が、`outcome=DISABLED,
  reason="Retry Queue is disabled (RETRY_QUEUE_ENABLED=false)."`を返すこと
  （`NullRetryQueueManager`へのフォールバックの確認）
* `RetryManager(policy=..., executor=..., monitor=..., queue=<Fakeまたは実RetryQueueManager>)`
  で構築した場合、`enqueue_retry()` / `dequeue_retry()`が渡した`queue`のメソッドを
  呼び出すこと
* `RetryManager.from_config(retry_config, policy, engine_manager, monitor_manager)`
  （4引数、`retry_queue_manager`省略）が本Release前とまったく同じ`RetryManager` /
  `NullRetryManager`判定結果を返すこと
* `RetryManager.from_config(..., retry_queue_manager=<実RetryQueueManagerインスタンス>)`
  で構築した`RetryManager`の`enqueue_retry()`が、実際にその`RetryQueueManager`へ
  項目を登録すること（`RetryQueueManager.count()`が1増えることで確認）
* **【Architecture Review反映】** 同一の実`RetryQueueManager`インスタンスを共有する
  単一の`RetryManager`に対して、`enqueue_retry(run_id="r1", ...)`→ `dequeue_retry()`を
  順に呼び、`dequeue_retry()`の戻り値`item.run_id == "r1"`であることを確認する
  （Fake同士の呼び出し回数検証だけでなく、実コンポーネントを使った
  enqueue→dequeueの往復が`RetryManager`経由でも壊れていないことを確認する
  end-to-endなケース）
* **【Architecture Review反映】** `RetryQueueConfig(enabled=False)`から
  `RetryQueueManager.from_config()`で得た`NullRetryQueueManager()`インスタンスを
  **明示的に**`retry_queue_manager`へ渡した場合と、`retry_queue_manager`を
  **省略**した場合（4.1節の`__init__`内フォールバック）とで、`enqueue_retry()` /
  `dequeue_retry()`の戻り値（`outcome` / `reason`）が完全に一致することを確認する
  （4.5節で述べた等価性が実装上も保証されていることの確認）

**(b) 委譲の正確性（加工しないことの確認）**

* `enqueue_retry(run_id, workflow_name, retry_attempt, priority)`の全引数が
  `RetryQueueManager.enqueue()`にそのまま渡されること（Fakeの`RetryQueueManager`で
  受け取った引数を検証）
* `enqueue_retry()` / `dequeue_retry()`の戻り値が、`RetryQueueManager`側の戻り値
  （`RetryQueueResult`）とオブジェクトとして等価であること（フィールドの改変が
  ないことの確認）
* Queueが満杯・`run_id`重複の場合、`enqueue_retry()`が`RetryQueueManager.enqueue()`
  と同じ`outcome=REJECTED`をそのまま返すこと（`RetryManager`側で独自の再判定・
  リトライを行わないことの確認）
* Queueが空の場合、`dequeue_retry()`が`outcome=EMPTY`をそのまま返すこと
* **【Architecture Review反映】** `RetryManager.enqueue_retry()`の`retry_attempt`
  デフォルト値（`1`）と`RetryQueueManager.enqueue()`の`retry_attempt`デフォルト値
  （`1`）が一致すること（`retry_attempt`を省略して`enqueue_retry()`を呼んだ結果の
  `item.retry_attempt`と、`RetryQueueManager.enqueue()`を直接省略呼び出しした結果の
  `item.retry_attempt`を突き合わせて確認する）。この値は`RetryQueueConfig`のような
  設定オブジェクトから導出されず、両ファイルにリテラルとして重複定義されるため
  （10章 Design Decision参照）、将来どちらか一方だけが変更された場合に本テストが
  検知する

**(c) `retry()`実行との独立性（Charter Non-Goal・5章の構造的分離の確認）**

* Fakeの`WorkflowMonitorManager` / `RetryExecutor`を注入した`RetryManager`に対し、
  `enqueue_retry()` / `dequeue_retry()`を呼んでも、Fakeの`get_status()` /
  `execute()`が**一度も呼ばれない**こと（`retry()`の呼び出しグラフに一切入らない
  ことの振る舞いレベルの確認）
* `dequeue_retry()`で`RetryQueueItem`を取り出した後、`RetryManager`側で
  自動的に`retry(item.run_id)`が呼ばれる経路が存在しないこと（`RetryManager`の
  ソースコードに`dequeue_retry`から`self.retry`または`self._executor`への
  呼び出しが存在しないことをコードレベルでも確認：Architecture Guard）
* 逆に、Fakeの`RetryQueueManager`を注入した`RetryManager`に対し`retry(run_id)`を
  呼んでも、Fakeの`enqueue()` / `dequeue()`が一度も呼ばれないこと

**(d) `NullRetryManager`の一貫性**

* `NullRetryManager().enqueue_retry(...)` / `NullRetryManager().dequeue_retry()`が
  常に`outcome=DISABLED`を返し、かつ`reason`の文言が「Retry Engineが無効」である
  ことを示す文言（`RetryManager`実インスタンス配下の`NullRetryQueueManager`が返す
  「Retry Queueが無効」文言とは異なる文字列）であること
* `NullRetryManager`の新規2メソッドが、いかなる`WorkflowMonitorManager` /
  `WorkflowEngineManager` / `RetryQueueManager`のメソッドも呼び出さないこと
  （`NullRetryManager`がフィールドを一切持たない、という既存の設計をコード上で
  再確認する）

**(e) `src/retry_queue/`無改修の確認（6章）**

* `git diff --stat`（またはテスト実行環境で取得したファイルハッシュ一覧）で
  `src/retry_queue/`配下に差分が存在しないことを確認する（Architecture Guard）
* `import retry_queue`した`RetryQueueManager` / `NullRetryQueueManager`の公開
  メソッドシグネチャ（`enqueue` / `dequeue` / `remove` / `list` / `exists` /
  `count`）が v3.1.0 時点のものと一致すること（`inspect.signature()`等による
  簡易な型レベル確認）

### 9.3 既存回帰確認（実装フェーズで実施）

* `tests/test_e2e_v3_1_0_retry_queue_foundation.py`（最重要。`retry_queue`が
  無改修であることの直接証拠）
* `tests/test_e2e_v3_0_0_retry_engine_foundation.py`（`RetryManager`の既存挙動が
  壊れていないことの確認）
* `tests/test_e2e_v2_9_0_workflow_monitor_foundation.py`〜
  `tests/test_e2e_v2_0_0_ai_agent_foundation.py`、
  `tests/test_e2e_v1_20_0_ai_workflow_foundation.py`

---

## 10. Design Decisions

1. **`queue`引数のデフォルトは`None`とし、`__init__`内部で`NullRetryQueueManager()`に
   フォールバックする。** `RetryQueueManager` / `NullRetryQueueManager`いずれかを
   常に保持させることで、`enqueue_retry()` / `dequeue_retry()`側に`None`分岐を
   持たせずに済む。`NullRetryQueueManager()`は状態を持たない値オブジェクトであり、
   デフォルト引数の可変オブジェクト問題（mutable default argument）には該当しない
   （呼び出しごとに新しいインスタンスを生成しても副作用がないため、実装上は
   `queue=None`をデフォルトにして`__init__`内で生成する方式・
   `field(default_factory=...)`相当の方式のいずれでも安全だが、既存コードの
   スタイル（`dataclass`ではなく素の`class`）に合わせ、`__init__`内での
   `if queue is not None else NullRetryQueueManager()`を採用する）。

2. **`from_config()`の新規引数名は`retry_queue_manager`とし、`workflow_engine_manager` /
   `workflow_monitor_manager`と同じ命名規則（`<パッケージ名>_manager`）に揃える。**
   一貫性のため、`queue`という短縮名は`__init__`内部のみで使用し、公開APIである
   `from_config()`ではパッケージ名を明示した名前を用いる。

3. **`enqueue_retry` / `dequeue_retry`は`RetryQueueManager`の`remove` / `list` /
   `exists` / `count`を中継しない（4.3節）。** Charterのスコープ「登録できるように
   する」「取得できるようにする」の2点に厳密に対応させる。将来これらの操作も
   `RetryManager`経由で使いたい要求が出た場合は、11章 Future Extensionで再検討する。

4. **`dequeue_retry()`は`RetryQueueItem`を`retry()`に渡す変換ロジックを持たない。**
   `RetryQueueItem.run_id`と`RetryManager.retry(run_id)`の引数名は偶然一致するが、
   `RetryQueueItem.retry_attempt`を`retry(attempt=...)`にマッピングするといった
   変換コードは意図的に実装しない。これを実装すると「Queueから取り出したら
   実際に再実行する」という自動化の入り口になり、Charter Non-Goalに抵触する
   （5章）。呼び出し元が明示的に`item = manager.dequeue_retry().item`と
   `manager.retry(item.run_id, attempt=item.retry_attempt)`を**別々の文として**
   呼ぶ必要がある、という非対称性を意図的に残す。

5. **`retry_engine/__init__.py`は変更しない。** `RetryQueueManager` /
   `NullRetryQueueManager` / `RetryQueueResult` / `RetryQueueOutcome`を
   `retry_engine`パッケージから再exportしない。`RetryManager.from_config()`に
   `retry_queue_manager`を渡す呼び出し元は、`from retry_queue import
   RetryQueueManager`のように`retry_queue`パッケージから直接importする。
   これにより「`retry_engine`が`retry_queue`の型を隠蔽・再定義する」という
   誤解を避け、依存方向（7章）が呼び出し元のimport文からも明確に読み取れる
   ようにする。

6. **`enqueue_retry()`の`retry_attempt: int = 1`はデフォルト値の意味的な重複を許容する
   （Architecture Review、2026-07-02反映）。** `RetryQueueManager.enqueue()`のデフォルト値
   （同じく`1`）を`RetryQueueConfig`のような共有設定から導出せず、両ファイルに独立した
   リテラルとして持つ。`priority`（`None`のままQueue側の`config.default_priority`に
   委ねる）とは異なり、`retry_attempt`は`RetryQueueManager`側にもConfig由来のデフォルト
   機構がなく（`retry_queue_manager.py`のシグネチャがリテラル`1`をハードコードしている）、
   `retry_engine`側だけを`None`委譲に変更しても`retry_queue`側の重複は解消できない
   （`retry_queue`は無改修対象のため変更不可）。実害は限定的（両者とも`1`という
   同じ値を独立に持つだけで、意味のずれは生じていない）と判断し、値の一致を
   9.2節のテストで継続的に検証することで将来のドリフトを検知する方針とする。

7. **`NullRetryManager`は`RetryQueueManager` / `NullRetryQueueManager`への参照を
   一切持たない（4.4節）。** `RetryManager`（実インスタンス）とは異なり、
   `NullRetryManager`は状態も依存も持たない完全なダミーであり続ける。Queue統合の
   有無に関わらず、Retry Engine自体が無効な場合はQueueへのアクセスも一律で
   `DISABLED`にする方が、呼び出し元にとって「ゲートが1つ増えた」という誤解を
   与えずに済む（Retry EngineとRetry Queueのゲートはあくまで独立、という
   Charter 5章の原則を`NullRetryManager`の内部構造でも再確認する形になる）。

---

## 11. Error Handling

### 11.1 例外方針

Retry Engine（既存）・Retry Queue（既存）と同じ方針を踏襲する。`enqueue_retry()` /
`dequeue_retry()`は新しい例外を発生させない。`RetryQueueManager.enqueue()` /
`dequeue()`が発生させうる例外（現状、業務上のエラーはすべて`RetryQueueResult.outcome`
で表現されており、想定される分岐で例外は発生しない）をそのまま透過する。

### 11.2 引数の型安全性

`enqueue_retry()`の引数（`run_id` / `workflow_name` / `retry_attempt` / `priority`）に
ついて、`RetryManager`側でのバリデーションは追加しない。バリデーション（型・値の
妥当性チェック）は既存どおり`RetryQueueManager`側の責務のままとする。

### 11.3 `reason`文字列によるゲート原因の切り分け（論点4の補足）

| ケース | `enqueue_retry()` / `dequeue_retry()`の`outcome` | `reason` |
|---|---|---|
| `RETRY_ENGINE_ENABLED=false`（`NullRetryManager`） | `DISABLED` | "Retry Engine is disabled (...)"（4.4節、Retry Engine起因） |
| `RETRY_ENGINE_ENABLED=true`だが`RETRY_QUEUE_ENABLED=false`（`RetryManager`が`NullRetryQueueManager`を保持） | `DISABLED` | "Retry Queue is disabled (RETRY_QUEUE_ENABLED=false)."（`retry_queue`パッケージ既存の文言、Retry Queue起因） |
| 両方`true`だが`run_id`重複／容量超過 | `REJECTED` | `RetryQueueManager.enqueue()`の既存文言 |
| 両方`true`だがQueueが空（`dequeue_retry()`） | `EMPTY` | `RetryQueueManager.dequeue()`の既存文言 |

新しい`RetryQueueOutcome`値は追加しない。既存の`DISABLED` / `REJECTED` / `EMPTY`の
`reason`文字列の違いのみで、呼び出し元は原因を切り分けられる。

---

## 12. Compatibility

* 変更ファイルは`src/retry_engine/retry_manager.py`の1点のみ
* `src/retry_queue/`配下は無改修（6章）
* `src/workflow_engine/` / `src/workflow_monitor/` / `src/execution_history/` /
  `src/ai/` / `src/pipeline/` / `src/scheduler/`は無改修
* 既存の公開API（`RetryManager.retry()` / `RetryManager.from_config()`の4引数呼び出し /
  `NullRetryManager.retry()`）のシグネチャ・戻り値の意味は変更しない
  （新規引数はすべてデフォルト値付きの追加のみ）
* `RetryManager.__init__`のシグネチャは`queue`引数が増えるが、既存の3キーワード引数
  （`policy` / `executor` / `monitor`）による呼び出しは影響を受けない

---

## 13. Architecture Review（セルフレビュー）

### SOLID

* **単一責任（SRP）**：`enqueue_retry` / `dequeue_retry`は「`RetryQueueManager`への
  委譲」という1つの責務のみを持つ。判定・変換ロジックを持たないことを10章
  Design Decision #4で明示している。
* **開放閉鎖（OCP）**：`RetryManager`はQueueの実装（`RetryQueueManager`か
  `NullRetryQueueManager`か）を意識せず、Duck Typing（`enqueue` / `dequeue`という
  共通シグネチャ）越しに扱う。将来Queueの実装が増えても`RetryManager`側の変更は
  不要。
* **リスコフの置換（LSP）**：`RetryManager`と`NullRetryManager`は、本Releaseで
  追加する2メソッドについても戻り値の型（`RetryQueueResult`）を一致させており、
  呼び出し元は両者を区別せず扱える。
* **インターフェース分離（ISP）**：`RetryManager`は`RetryQueueManager`の全6操作
  ではなく、Charterで要求された2操作（登録・取得）のみを中継する（10章
  Design Decision #3）。
* **依存性逆転（DIP）**：`RetryManager`は`RetryQueueManager`の抽象的な
  インターフェース（`enqueue` / `dequeue`を持つオブジェクト）にのみ依存し、
  具象クラスを直接生成しない（Charter・v3.0.0以来のDI方針を踏襲）。

### Foundation First

Queueへの登録・取得という最小の配線のみを実装し、自動実行・優先度戦略・永続化・
Scheduler連携はすべて対象外のまま維持している（Charter 4章・8章と1対1で対応）。

### 責務分離

「Queueに何を入れるか・いつ取り出すか」という判断ロジックは`retry_queue`側に
完全に残り、`retry_engine`側は呼び出し口の提供のみを行う。5章で示したとおり、
`retry()`（Retry実行）と`enqueue_retry` / `dequeue_retry`（Queue操作）は
呼び出しグラフ上で分離されている。

### 後方互換性

8章・12章のとおり、既存の呼び出しパターン（コンストラクタ直接呼び出し・
`from_config()`4引数呼び出し）はいずれも新規引数のデフォルト値でカバーされ、
既存テストを無変更のまま全PASSさせられる設計になっている。

### 依存方向

```
src/retry_engine/  ─── import ───→  src/retry_queue/（新規）・src/workflow_engine/・src/workflow_monitor/（既存）
src/retry_queue/   ─── import ───→  （なし。無改修のまま）
```

循環importは存在しない（7章）。

### 残された懸念（Minor）

* `enqueue_retry()` / `dequeue_retry()`という命名が、将来`RetryQueueManager`の
  `remove` / `list` / `exists` / `count`も中継したくなった場合に一貫した命名
  規則（`remove_retry` / `list_retry` 等）を要求する可能性がある。本Releaseでは
  Charterのスコープ（登録・取得の2操作）を厳密に守るため見送るが、拡張時は
  本Releaseの命名パターンを踏襲する想定とする（11章 Future Extension相当、
  Charterには明記していないため次回Charter作成時に検討する）。
* `RetryManager`が保持する`self._queue`の型（`RetryQueueManager |
  NullRetryQueueManager`）はDuck Typingで扱われ、型ヒント上の共通プロトコルは
  定義していない。既存の`WorkflowEngineManager | NullWorkflowEngineManager`等も
  同様の扱いであり、本Releaseとしての一貫性は保たれている。
* **（Architecture Review確認事項）** `RetryManager`は本Releaseにより「Retry可否
  判定・実行」（既存責務）と「Queueへの委譲」（新規責務）という2つの理由で変更
  されうるクラスになる。SRPの観点では単一責務からの逸脱だが、(a) Queue側の
  責務はCharter・本設計で「委譲のみ」に厳密に限定されており判定ロジックは
  複製していないこと、(b) `RetryManager`からQueueへ接続する経路そのものが
  Charterで明示的に要求されていること、の2点から許容範囲と判断する。将来
  Queue関連の中継メソッドが3つ以上に増える場合は、`RetryQueueClient`のような
  専用アダプタへの切り出しを検討する（次回拡張時のCharterで再評価する）。
* **（Architecture Review確認事項）** `retry_manager.py`に`from retry_queue import
  ...`を追加することによるテスト実行環境への影響を確認した。既存の
  `tests/test_e2e_v3_0_0_retry_engine_foundation.py` /
  `tests/test_e2e_v3_1_0_retry_queue_foundation.py`はいずれも`sys.path.insert(0,
  str(PROJECT_ROOT / "src"))`で`src/`直下をパスに追加しており、`retry_engine`・
  `retry_queue`は共に`src/`直下の兄弟パッケージであるため、新規のクロス
  パッケージimportによる追加設定は不要であることを確認済み（新規E2Eテストも
  同じ`sys.path`初期化パターンを踏襲すればよい）。

**総評**：Charterの要求（RetryManagerからRetryQueueManagerを利用可能にする・
登録/取得の2操作・既存API双方の後方互換性・責務分離・retry_queue無改修）を
満たし、かつ既存Foundation群（`retry_engine` / `retry_queue`）との設計整合性
（DIパターン・Manager/Nullペア・`RetryQueueResult`への委譲）を保っている。
Architecture Reviewの結果、**Approve with Minor Recommendations**と判定する
（指摘事項3点は9.2節へ反映済み、SRP・環境面の2点は確認のうえ許容と判断）。

---

## 14. Acceptance Criteria（実装フェーズ向け、Charter 9章の再掲・具体化）

### コード（実装済み）

- [x] `RetryManager.__init__`への`queue`引数追加（`src/retry_engine/retry_manager.py`）
- [x] `RetryManager.from_config()`への`retry_queue_manager`引数追加
- [x] `RetryManager.enqueue_retry()`
- [x] `RetryManager.dequeue_retry()`
- [x] `NullRetryManager.enqueue_retry()`
- [x] `NullRetryManager.dequeue_retry()`

### テスト（実施済み）

- [x] `tests/test_e2e_v3_2_0_retry_queue_integration.py`（9.2節の全ケース、102/102 PASS）
- [x] 既存回帰確認：`v3.0.0`（130/130 PASS）・`v2.0.0`〜`v2.9.0`・`v1.20.0`（全件PASS）
- [x] `v3.1.0`（151/152 PASS）：`src/retry_queue/`無改修に関するテストはすべてPASS。
      1件のみFAIL（`retry_engine`が本Release前提として「無改修」を仮定していた
      Architecture Guard）。v3.2.0での`retry_manager.py`変更はCharter/Design/Review
      で承認済みのため既知の差分として扱い、`docs/CHANGELOG.md` [KI-3]に記録した
      （v3.1.0テストファイル自体は変更していない）
- [x] Architecture Guard：`src/retry_queue/`配下に差分がないこと（`git diff`、テスト14）・
      `enqueue_retry` / `dequeue_retry`から`retry()` / `self._executor` /
      `self._monitor` / `self._policy`への呼び出しが存在しないこと（静的検査、テスト11）

### 満たすべき性質（機能要件、論点1〜8を再掲、確認済み）

- [x] `RetryManager`が`RetryQueueManager`（または`NullRetryQueueManager`）をDIで
      保持できること
- [x] `enqueue_retry()` / `dequeue_retry()`が、それぞれ`RetryQueueManager.enqueue()` /
      `dequeue()`への委譲のみであること（加工なし）
- [x] `from_config()`の新規引数省略時、既存呼び出しと完全に同じ挙動になること
- [x] `NullRetryQueueManager`使用時、常に`outcome=DISABLED`が返ること
- [x] Queue操作が`retry()`の呼び出しグラフに一切入らないこと（逆も同様）
- [x] `src/retry_queue/`配下に変更がないこと
- [x] 既存テスト（`v3.0.0`含む）が無変更のまま全PASSすること。`v3.1.0`は既知の1件を
      除き全PASS（上記参照）

### ドキュメント

- [x] 本設計書（Architecture Design）
- [x] `docs/design/retry_queue_integration_charter.md`（Project Charter、承認済み）
- [x] `docs/CHANGELOG.md` / `docs/ROADMAP.md`への記載（実装完了後、`[KI-3]`追記含む）
- [x] `docs/architecture.md`への追記（「Retry Queue Integration層」セクション新設）

### リリース

- [ ] コミット（実装完了・テストPASS後、ユーザー確認を経て実施）
- [ ] push（コミット後、別途ユーザー確認を経て実施）
