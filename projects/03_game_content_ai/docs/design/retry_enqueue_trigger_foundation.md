# v4.6.0 Retry Enqueue Trigger Foundation 設計書（Architecture Design）

作成日：2026-07-09
状態：Architecture Review完了（**Approve**）・ユーザー承認済み・実装完了。
`docs/design/retry_enqueue_trigger_foundation_charter.md`（Project Charter）を
前提とし、ユーザーが指定した4つのOpen Question方針（Charter 8章）をすべて
反映する。

---

## 1. Architecture Overview

v3.0.0〜v4.5.0の16回のReleaseで、以下が整備された。

* Workflow Monitor（v2.9.0）：Execution Historyを唯一の情報源として
  `FAILED` / `TIMEOUT` / `RUNNING` / `SUCCESS`を判定する読み取り専用層
* Retry Queue（v3.1.0）：`enqueue` / `dequeue` / `remove` / `list` / `exists` /
  `count`を提供するQueue管理層
* Retry Scheduler Source〜Retry Policy Foundation（v3.2.0〜v4.5.0）：
  Queueから候補を選び、Retry Engineが認識・整理・実行し、結果に応じて
  Queueの後始末（更新・除去・清掃）を行う下流パイプライン一式

しかし`RetryQueueManager.enqueue()` / `RetryManager.enqueue_retry()`は
コードベース全体のどこからも呼び出されておらず、下流パイプラインは
実データを一度も受け取ったことがない（Charter 1章）。

本Release（v4.6.0）は、この「Queueへ実際に投入する主体がいない」という
ギャップに対して、Workflow Monitor側の出口となる新規独立パッケージ
`src/retry_enqueue_trigger/`を追加する。Charter（4章・8章）で確定した
とおり、本Releaseの範囲は**Adapterの新設とenqueue機能の実装のみ**であり、
これを定期的に駆動する起動スクリプト（Composition Root）は追加しない。

```
WorkflowMonitorManager（判定、v2.9.0、無改修）
   │
   ▼
RetryEnqueueTrigger / NullRetryEnqueueTrigger（Adapter、v4.6.0、新規） ★本Release
   │
   └── RetryQueueManager（Queue管理、v3.1.0、無改修）
          │
          └── （retry_engine / scheduler / retry_scheduler_source 等は
                本Releaseの依存グラフには一切登場しない）
```

本パッケージは`workflow_monitor`と`retry_queue`という、既存の2つの独立した
葉パッケージを橋渡しする「合流点」として新設されるが、いずれの既存パッケージ
にも書き込みを行わない（`workflow_monitor`からは読み取りのみ、`retry_queue`
へは`enqueue()`の呼び出しのみ）。本Release時点では、`RetrySchedulerSource`
（v3.3.0）・`WorkflowMonitorManager`（v2.9.0）・`RetryQueue`（v3.1.0）と同じ
「消費者不在の先行実装」パターンとして、どのパッケージからも呼ばれない状態で
リリースされる。

---

## 2. Design Policy

Project Charterの Design Principles（5章）およびユーザー確定方針
（Charter 8章 Open Questions回答）を、本パッケージ固有の形で具体化する。

1. **Feature Gate・Configクラスを持たない（ユーザー確定方針 #1）**：
   `RetrySchedulerSource` / `NullRetrySchedulerSource`（v3.3.0）と同じ
   Null Object Patternの2クラス構成とする。`RetryEnqueueTriggerConfig`の
   ような起動口・環境変数は本Releaseでは追加しない。有効/無効は、呼び出し元
   （将来のComposition Root）が`RetryEnqueueTrigger(monitor, queue)`と
   `NullRetryEnqueueTrigger()`のどちらを構築するかで表現する。

2. **`retry_engine`を経由せず、`workflow_monitor` / `retry_queue`に直接依存する
   （ユーザー確定方針 #2）**：`RetrySchedulerSource → retry_queue`の前例と
   同じ「下位パッケージへの直接依存」パターンを踏襲する。`RetryManager.
   enqueue_retry()`（薄い委譲のみ）や`NullRetryManager`（`RETRY_ENGINE_ENABLED`
   ゲート）は一切経由しない。これにより、`RETRY_ENGINE_ENABLED=false`
   （デフォルト）の状態でも、`RetryEnqueueTrigger`単体としてはQueueへの
   投入を行える構造になる（Queueへの投入自体は外部副作用を伴わないメモリ
   操作であり、`RetryQueueConfig.enabled`のデフォルトが`true`である既存
   設計——Charter 1章——と同じ分類に属するため）。「実際にRetryを実行するか」
   は引き続き下流の`RetryConfig.enabled`（デフォルト`false`）で止まる
   ため、安全性は損なわれない。

3. **無限再投入対策は本格実装しない（ユーザー確定方針 #3）**：
   `RetryQueueManager.exists()`による「Queue内に現在存在するか」の確認のみを
   重複防止として行う。Queueから一度除去された後もWorkflow Monitor上で
   `FAILED` / `TIMEOUT`のまま観測され続けるケース（4章 Known Issue）への
   対策は本Releaseでは実装せず、Known Issueとして明記する。将来どこで
   対策できるかは11章 Future Extensionに残す。

4. **一括処理結果はシンプルな集計dataclassとする（ユーザー確定方針 #4）**：
   `RetryEnqueueTriggerResult`（`scanned` / `enqueued` / `skipped_existing` /
   `skipped_status` / `failed`の5フィールドのみ）とし、理由文字列の列挙や
   例外的なケース分岐は追加しない（4章）。

5. **Foundation First**：enqueue機能の新設のみに限定し、これを定期的に
   駆動する起動スクリプト（Composition Root）は11章 Future Extensionへ送る。

6. **既存モジュール無改修**：`workflow_monitor` / `retry_queue` /
   `retry_engine`のいずれも変更しない。`RetryEnqueueTrigger`は両パッケージの
   公開シンボルのみをimportする独立パッケージとして設計する。

---

## 3. Package Structure

```
src/retry_enqueue_trigger/
├── __init__.py                  # 公開シンボルのexport（4章）
└── retry_enqueue_trigger.py     # RetryEnqueueTrigger / NullRetryEnqueueTrigger /
                                  # RetryEnqueueTriggerResult
```

`RetrySchedulerSource`（v3.3.0）と同じ考え方で、実装クラス・ダミークラス・
結果dataclassを単一ファイルに同居させる（メソッド数が1個ずつのみの極小実装
であり、ファイル分離の利点よりも見通しの良さを優先する）。

Configファイル・Manager的な起動口ファイルは作らない（2章）。既存パッケージ
と比べて最小の2ファイル構成となるが、Foundation Releaseのスコープ（enqueue
1メソッドのみを、実体／ダミーの2クラスで提供する）に対して過不足のない
構成である。

既存パッケージへの変更は一切行わない（ゼロ改修）。

---

## 4. Public API

### `retry_enqueue_trigger.py`

```python
from __future__ import annotations

from dataclasses import dataclass

from retry_queue import RetryQueueManager, RetryQueueOutcome
from workflow_monitor import WorkflowMonitorManager, WorkflowMonitorStatus

_RETRY_TARGET_STATUSES = frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT})


@dataclass(frozen=True)
class RetryEnqueueTriggerResult:
    """enqueue_pending_failures() 1回分の集計結果。"""
    scanned: int            # list_status() が返したレコード総数
    enqueued: int            # enqueue()がENQUEUEDを返した件数
    skipped_existing: int    # 既にQueueに存在したためenqueueをスキップした件数
    skipped_status: int      # monitor_statusがFAILED/TIMEOUT以外だった件数
    failed: int               # enqueue()がENQUEUED以外を返した件数（主に容量超過）


class RetryEnqueueTrigger:
    """
    WorkflowMonitorManagerが判定したFAILED/TIMEOUTのWorkflowを検知し、
    まだRetry Queueに存在しないものだけをenqueueするAdapter（実装クラス）。
    """

    def __init__(self, monitor: WorkflowMonitorManager, queue: RetryQueueManager):
        self._monitor = monitor
        self._queue = queue

    def enqueue_pending_failures(self, limit: int | None = None) -> RetryEnqueueTriggerResult:
        """
        WorkflowMonitorManager.list_status(limit) を走査し、monitor_statusが
        FAILED/TIMEOUTのレコードのうち、まだQueueに存在しないものだけを
        RetryQueueManager.enqueue()する。
        """
        records = self._monitor.list_status(limit=limit)
        scanned = len(records)
        enqueued = 0
        skipped_existing = 0
        skipped_status = 0
        failed = 0

        for record in records:
            if record.monitor_status not in _RETRY_TARGET_STATUSES:
                skipped_status += 1
                continue
            if self._queue.exists(record.run_id):
                skipped_existing += 1
                continue
            result = self._queue.enqueue(run_id=record.run_id, workflow_name=record.workflow_name)
            if result.outcome == RetryQueueOutcome.ENQUEUED:
                enqueued += 1
            else:
                failed += 1

        return RetryEnqueueTriggerResult(
            scanned=scanned,
            enqueued=enqueued,
            skipped_existing=skipped_existing,
            skipped_status=skipped_status,
            failed=failed,
        )


class NullRetryEnqueueTrigger:
    """
    RetryEnqueueTrigger のダミー実装（Null Object）。

    workflow_monitor / retry_queue への参照を一切保持せず、常に
    「検知0件・enqueue 0件」の結果を返す。
    """

    def enqueue_pending_failures(self, limit: int | None = None) -> RetryEnqueueTriggerResult:
        return RetryEnqueueTriggerResult(
            scanned=0, enqueued=0, skipped_existing=0, skipped_status=0, failed=0,
        )
```

* `RetryEnqueueTrigger.__init__`は`WorkflowMonitorManager` /
  `RetryQueueManager`（いずれも実体のみ）を受け取る（Union型にはしない）。
  無効化したい場合は`RetryEnqueueTrigger(...)`を構築せず
  `NullRetryEnqueueTrigger()`を使う、という選択を呼び出し元に委ねる設計とする
  （`RetrySchedulerSource`のv3.3.0改訂と同じ判断）
* コンストラクタは`monitor` / `queue`のみを受け取る単純なDIとする。
  `from_config()`は用意しない（そもそも保持するConfigが存在しない）
* `retry_attempt`は`enqueue()`のデフォルト値（`1`）をそのまま使い、明示的に
  指定しない。`priority`も同様にデフォルト（`RetryQueueConfig.
  default_priority`）に委ねる（Charter 4章 対象外：試行回数管理は本Release
  の対象外）
* `enqueue_pending_failures()`という名前は、`RetrySchedulerSource`の
  `list_pending_retries()`と対になる語彙とし、「Monitor側の関心事」を
  表現する（Workflow Monitorの語彙で「保留中の失敗」を扱っていることを
  明確にする）
* 戻り値`RetryEnqueueTriggerResult`は独自の集計dataclassとし、
  `RetryQueueResult`をそのまま列挙して返すことはしない（大量の
  `WorkflowMonitorRecord`を走査する用途では、呼び出し元は通常「何件処理
  されたか」の要約のみを必要とするため。個々の`run_id`単位の詳細が必要に
  なった場合は11章Future Extensionで再検討する）
* `RetryEnqueueTrigger`と`NullRetryEnqueueTrigger`の間に継承関係は持たせ
  ない（プロジェクト全体のDuck Typingペアと同じ。6章 Class Diagram）

### `__init__.py` の公開シンボル

```python
from .retry_enqueue_trigger import (
    NullRetryEnqueueTrigger,
    RetryEnqueueTrigger,
    RetryEnqueueTriggerResult,
)

__all__ = [
    "RetryEnqueueTrigger",
    "NullRetryEnqueueTrigger",
    "RetryEnqueueTriggerResult",
]
```

---

## 5. Class Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryEnqueueTrigger` | `WorkflowMonitorManager` / `RetryQueueManager`への参照を保持し、FAILED/TIMEOUTの検知とQueue内重複チェックのうえで`enqueue()`を呼ぶ | Retry可否判定（`RetryPolicy`の責務）・Retry実行・Queueの後始末・定期実行・試行回数の追跡 |
| `NullRetryEnqueueTrigger` | 呼び出し元がEnqueue Triggerと接続したくない場合のダミー実装。常に副作用なく空の結果を返す | `workflow_monitor` / `retry_queue`への参照の保持・通信 |
| `WorkflowMonitorManager`（v2.9.0、無改修） | 引き続きWorkflowの状態判定のみを行う | Retry Queueへの関与 |
| `RetryQueueManager`（v3.1.0、無改修） | 引き続きQueue管理のみを行う | 検知・判定ロジック |

「どちらのクラスを構築するか」の判定ロジック（Feature Gate相当の判断）は、
本パッケージの責務ではなく**呼び出し元の責務**とする（8章 Data Flowで詳述）。

---

## 6. Class Diagram

```
┌────────────────────────────┐      ┌─────────────────────────────┐
│      RetryEnqueueTrigger      │      │    NullRetryEnqueueTrigger     │
│────────────────────────────│      │─────────────────────────────│
│ - _monitor: WorkflowMonitorManager│      │ （状態を一切持たない）             │
│ - _queue: RetryQueueManager   │      │─────────────────────────────│
│────────────────────────────│      │ + enqueue_pending_failures(limit)│
│ + __init__(monitor, queue)     │      │     → RetryEnqueueTriggerResult   │
│ + enqueue_pending_failures(limit)│──┐   │        (0, 0, 0, 0, 0)            │
│     → RetryEnqueueTriggerResult  │  │   └─────────────────────────────┘
└────────────────────────────┘  │
      （継承関係なし。Duck            │
       Typingで同一視される）          │ 委譲のみ
                                        ▼
      ┌───────────────────────┐   ┌──────────────────────────┐
      │ WorkflowMonitorManager    │   │    RetryQueueManager        │
      │ （v2.9.0、無改修）          │   │    （v3.1.0、無改修）          │
      │───────────────────────│   │──────────────────────────│
      │ + list_status(limit)      │   │ + exists(run_id) -> bool     │
      │    -> list[Record]         │   │ + enqueue(run_id, name, ...)  │
      └───────────────────────┘   └──────────────────────────┘
```

`RetryEnqueueTrigger`は`WorkflowMonitorManager` / `RetryQueueManager`との
間に継承関係を持たない（コンポジション。`_monitor` / `_queue`フィールドとして
保持するのみ）。`RetryEnqueueTrigger`と`NullRetryEnqueueTrigger`の間にも
継承関係はない。

---

## 7. Sequence Diagram

### 7.1 enqueue_pending_failures（有効な場合：RetryEnqueueTrigger）

```
Caller         RetryEnqueueTrigger   WorkflowMonitorManager   RetryQueueManager
  │  trigger.enqueue_pending_failures(limit=None)                            │
  ├──────────────►│                                                          │
  │                │  self._monitor.list_status(limit=None)                  │
  │                ├─────────────────────►│                                  │
  │                │                       │  Execution Historyを走査し       │
  │                │                       │  各run_idの状態を判定             │
  │                │◄──────────────────────┤                                  │
  │                │  list[WorkflowMonitorRecord]                            │
  │                │                                                          │
  │                │  for record in records:                                 │
  │                │    if monitor_status not in {FAILED, TIMEOUT}: skip     │
  │                │    self._queue.exists(record.run_id)                    │
  │                ├──────────────────────────────────────►│                 │
  │                │◄──────────────────────────────────────┤                 │
  │                │  bool（既に存在すればskip）                              │
  │                │                                                          │
  │                │    self._queue.enqueue(run_id, workflow_name)           │
  │                ├──────────────────────────────────────►│                 │
  │                │                                        │ 重複/容量チェック │
  │                │                                        │ WAITING項目追加  │
  │                │◄──────────────────────────────────────┤                 │
  │                │  RetryQueueResult(outcome=ENQUEUED, ...)                │
  │                │                                                          │
  │◄───────────────┤                                                          │
  │  RetryEnqueueTriggerResult(scanned, enqueued, skipped_existing,          │
  │                             skipped_status, failed)                       │
```

### 7.2 無効な場合（NullRetryEnqueueTrigger。両パッケージへ一切到達しない）

```
Caller              NullRetryEnqueueTrigger
  │  # 呼び出し元がEnqueue Triggerと接続しない選択をした
  │  trigger = NullRetryEnqueueTrigger()
  │                                                            │
  │  trigger.enqueue_pending_failures()                        │
  ├──────────────────────────────────────────────────────────►│
  │                                                            │  何もしない
  │◄──────────────────────────────────────────────────────────┤
  │  RetryEnqueueTriggerResult(0, 0, 0, 0, 0)                  │
  │  （workflow_monitor / retry_queueへは一度も到達しない）        │
```

---

## 8. Data Flow

```
① 呼び出し元（本Releaseでは未定。将来のComposition Root）が
   「Enqueue Triggerを有効にするか」を判断する（判断基準は本Releaseでは
   定義しない。将来的にはWorkflowMonitorConfig.is_ready() /
   RetryQueueConfig.is_ready()の両方を参照することが想定されるが、これは
   呼び出し元の実装詳細であり、本パッケージはその判断ロジックを持たない）
        ↓
② 有効にする場合：
     WorkflowMonitorManager.from_config(...) と RetryQueueManager.
     from_config(...) で monitor / queue（いずれも実体）を得て、
     RetryEnqueueTrigger(monitor, queue) を構築する
   無効にする場合：
     NullRetryEnqueueTrigger() を構築する
        ↓
③ 呼び出し元が enqueue_pending_failures(limit) を、どちらのクラスに
   対しても同じ呼び出し方で呼ぶ（Duck Typing）
        ↓
④-a RetryEnqueueTrigger の場合：
     monitor.list_status(limit) → FAILED/TIMEOUTのみ抽出 →
     各run_idについて queue.exists(run_id) → False の場合のみ
     queue.enqueue(run_id, workflow_name) を呼ぶ
④-b NullRetryEnqueueTrigger の場合：即座に空の結果を返す
     （workflow_monitor / retry_queueへのアクセスは発生しない）
        ↓
⑤ WorkflowMonitorManager（実体）はExecution Historyを読み取るだけで
   状態を変更しない（Read Only）。RetryQueueManager（実体）は
   enqueue()によってのみ内部dictへ新しいWAITING項目を追加する
   （既存のRetry Queueの他の操作——list/exists/count/dequeue/remove——には
   一切影響しない）
        ↓
⑥ 呼び出し元は④の戻り値（RetryEnqueueTriggerResult）をそのまま受け取る
```

`RetryEnqueueTrigger`は`WorkflowMonitorManager` / `RetryQueueManager`の
内部データ構造（Execution Historyのレコード形式・Queueの`_items` dict）に
直接アクセスすることはない。常に両パッケージの公開メソッド経由でのみ
状態を参照・変更する。

---

## 9. Configuration

**本Releaseでは新規の環境変数を一切追加しない**（Charter 5章、Open
Questions #1回答）。

`RetryEnqueueTrigger` / `NullRetryEnqueueTrigger`のどちらを使うかは、
呼び出し元のコードが直接選択する。本パッケージ自身は環境変数を一切読まず、
`is_ready()`のような判定メソッドも持たない。

| 環境変数 | デフォルト | 説明 |
|---|---|---|
| （なし） | — | `retry_enqueue_trigger`パッケージは環境変数を一切読まない |

参考：既存の`WORKFLOW_MONITOR_ENABLED`（デフォルト`true`）・
`RETRY_QUEUE_ENABLED`（デフォルト`true`）が`false`の場合、それぞれ
`NullWorkflowMonitorManager` / `NullRetryQueueManager`が返る。呼び出し元が
これらの結果を見て`NullRetryEnqueueTrigger()`を選ぶ、という連携は将来Release
（Composition Root）で確立される想定であり、本Releaseでは両クラスの実装
のみを提供する。

---

## 10. Error Handling

`RetryEnqueueTrigger` / `NullRetryEnqueueTrigger`は独自の例外処理を持たない。

| ケース | 挙動 |
|---|---|
| `list_status()`が空リストを返す | `scanned=0`。ループが1回も実行されず、全フィールド0の結果を返す（例外なし） |
| 全レコードが`RUNNING` / `SUCCESS` | 全件`skipped_status`にカウントされ、`enqueued=0` |
| 全レコードが既にQueueに存在 | 全件`skipped_existing`にカウントされ、`enqueued=0`（`queue.enqueue()`は一度も呼ばれない） |
| `queue.enqueue()`が`REJECTED`を返す（容量超過） | `failed`にカウントされる。例外は発生しない（`RetryQueueManager.enqueue()`の既存契約どおり） |
| `NullRetryEnqueueTrigger`を使用 | 常に全フィールド0（`workflow_monitor` / `retry_queue`へのアクセス自体が発生しないため、両パッケージの状態に関わらず一定） |
| `monitor` / `queue`に`None`が渡された場合 | 型ヒント上サポート対象外。呼び出し元の実装ミスとして扱い、防御的なNoneチェックは追加しない（他の全Adapter/Managerクラスと同じ方針） |

---

## 11. Known Issue（本Releaseでは対策しない）

**Queueから除去された`run_id`が、Workflow Monitor上でなお`FAILED` /
`TIMEOUT`のまま観測され続けると、`enqueue_pending_failures()`が呼ばれる
たびに無限に再enqueueされうる。**

原因：`RetryExecutor.execute()`（v3.0.0、無改修）は再実行のたびに
**新しい`WorkflowEngineEvent`**（＝新しい`run_id`）を発行し、`metadata`に
`{"retried_from": 元run_id, "attempt": N}`を記録する（`retry_executor.py`
確認済み）。つまり元の`run_id`のExecution History記録自体は不変であり、
Workflow Monitorが判定する`monitor_status`も`FAILED`のまま変化しない。
一方、Retry Queueからは`COMPLETE` / `FAIL` / `CLEANUP`判定時に`remove()`
される（v4.2.0〜v4.4.0）ため、`RetryQueueManager.exists(元run_id)`は
いずれ`False`に戻る。この状態で再度`enqueue_pending_failures()`が
呼ばれると、既に処理済みのはずの元`run_id`が再びQueueへ投入されてしまう。

本Releaseでは、この問題への対策を意図的に実装しない（Charter Open
Questions #3、ユーザー確定方針）。`exists()`によるQueue内重複防止のみを
提供し、「Queueから出た後の再投入」は本Releaseのスコープ外とする。

**将来の対策候補（Future Extension、下記11章と併読）**：

* `metadata["retried_from"]`（`retry_executor.py`が既に記録している）を
  手掛かりに、「元`run_id`から既に1回以上Retryが発行されているか」を
  判定できる新規コンポーネント（ROADMAP.mdの未着手候補「Retry History
  （再試行回数の永続化）」に相当）を追加し、`RetryEnqueueTrigger`（または
  その後継）が`enqueue`前に参照する
* あるいは、`RetryPolicy.max_attempts` / `should_retry()`（v3.0.0〜v4.5.0で
  既に整備済みのProtocol、`retry_policy_protocol.py`）を`RetryEnqueueTrigger`
  側でも参照できるようにし、「既に`max_attempts`に達した`run_id`は
  enqueueしない」という判定を追加する（ただし、これは`retry_engine`への
  依存を新たに発生させるため、2章の設計方針#2——`retry_engine`を経由しない
  ——との整合性を将来Releaseで再検討する必要がある）
* いずれの対策も、`RetryEnqueueTrigger`をStatelessに保ったまま実現できる
  （対策に必要な「これまでの試行履歴」は`RetryEnqueueTrigger`自身ではなく、
  Execution History／新設コンポーネントのいずれかに永続化された情報として
  外部から参照する形になる）

---

## 12. Future Extension

* **Composition Root（実運用の起動導線）**：`RetryEnqueueTrigger`を定期的に
  呼び出し、その結果を将来的には`RetrySchedulerSource`〜`RetryManager`の
  下流パイプラインへつなげる起動スクリプト（例：`scripts/
  run_retry_enqueue_trigger.py`）。「どちらのクラス（`RetryEnqueueTrigger`
  / `NullRetryEnqueueTrigger`）を構築するか」の判定ロジック
  （`WORKFLOW_MONITOR_ENABLED` / `RETRY_QUEUE_ENABLED`の参照等）もこの段階で
  確立する
* **無限再投入対策（Retry History）**：11章 Known Issueで述べた対策候補の
  実装。ROADMAP.md未着手候補「Retry History（再試行回数の永続化）」の
  具体化として位置づける
* **`limit`のチューニング**：`list_status()`に`limit`を指定しない場合、
  Execution History件数の増加とともに毎回の走査コストが増える可能性がある。
  実運用の呼び出し頻度・件数が判明した時点で`limit`の要否を再評価する
* **`RetryEnqueueTriggerResult`への詳細情報追加**：現状は集計件数のみだが、
  将来的に「どのrun_idがenqueueされたか」のトレーサビリティが必要になった
  場合、`enqueued_run_ids: list[str]`等の追加を検討する（Charter方針#4の
  「過度に複雑な理由列挙を避ける」との兼ね合いで、必要性が明確になってから
  追加する）
* **Feature Gateの追加**：将来的にEnqueue Trigger単体でのON/OFFを環境変数で
  制御したいニーズが生じた場合、`RetrySchedulerSource`と同様、本パッケージに
  Configクラスを追加するのではなく、呼び出し元（Composition Root）側で
  判定する設計を優先する（2章 Design Policy #1との整合性）

---

## 13. Compatibility

* 新規独立パッケージ`src/retry_enqueue_trigger/`の追加のみであり、既存
  パッケージ（`workflow_monitor` / `retry_queue` / `retry_engine` /
  `workflow_engine` / `scheduler` / `retry_scheduler_source`等）への変更は
  一切ない（ゼロ改修）
* 既存の公開APIのシグネチャ・戻り値の意味は変更しない
* `src/retry_enqueue_trigger/`は本Release時点でどのパッケージからも
  importされない状態でリリースされる（1章）。`WorkflowMonitorManager`
  （v2.9.0）・`RetryQueue`（v3.1.0）・`RetrySchedulerSource`（v3.3.0）と
  同じ「消費者不在の先行実装」パターンであり、後方互換性上のリスクはない
* 新規の環境変数を追加しないため、`.env` / `.env.example`の変更も不要

---

## 14. Architecture Review

### SOLID

* **単一責任（SRP）**：`RetryEnqueueTrigger`は「FAILED/TIMEOUTを検知し、
  未投入のものだけenqueueする」という1つの責務のみを持つ。Retry可否判定・
  実行・Queueの後始末はいずれも既存コンポーネントの責務のまま複製しない
* **開放閉鎖（OCP）**：`RetryEnqueueTrigger`は`WorkflowMonitorManager` /
  `RetryQueueManager`の公開インターフェースにのみ依存しており、両パッケージの
  内部実装が変わっても影響を受けない
* **リスコフの置換（LSP）**：`RetryEnqueueTrigger`と`NullRetryEnqueueTrigger`
  は戻り値の型（`RetryEnqueueTriggerResult`）を完全に一致させており、
  呼び出し元はどちらを渡されても同じコードパスで正しく動作する
* **インターフェース分離（ISP）**：`enqueue_pending_failures()`1メソッドの
  みを公開し、`WorkflowMonitorManager.get_status()`や`RetryQueueManager`の
  `dequeue()` / `remove()` / `list()` / `count()`には一切アクセスしない
* **依存性逆転（DIP）**：`RetryEnqueueTrigger`は具象クラス
  `WorkflowMonitorManager` / `RetryQueueManager`に依存する。
  `NullRetryEnqueueTrigger`はいかなる外部パッケージにも依存しない。
  「有効／無効の切り替え」は、呼び出し元がどちらのクラスを構築するかで
  解決する（`RetrySchedulerSource`と同じアプローチ）

### Foundation First

enqueue機能の新設のみに限定し、Composition Root・無限再投入対策・Feature
Gate追加をすべて12章 Future Extensionへ送っている。Charter 4章 対象外リスト
と1対1で対応しており、スコープの逸脱はない。

### 責務分離

「FAILED/TIMEOUTを検知し、Queueに投入するかを判断する」
（`RetryEnqueueTrigger`の責務）と、「Queueの中身をどう管理するか」
（`RetryQueueManager`の責務、無改修）、「Workflowの状態をどう判定するか」
（`WorkflowMonitorManager`の責務、無改修）を明確に分離した。「有効か無効か」
の判定は、本パッケージの責務外（呼び出し元の責務）として明示的に切り離した。

### プロジェクト全体との設計整合性

`RetryManager`/`NullRetryManager`、`RetryQueueManager`/
`NullRetryQueueManager`、`RetrySchedulerSource`/`NullRetrySchedulerSource`
と同じ「継承なし・戻り値の型が一致するDuck Typingペア」を踏襲した。
`RetrySchedulerSource`と同様、Configクラス・Managerパターン（`from_config()`
等の起動口）は持たない構成とした。

### 依存方向

```
src/retry_enqueue_trigger/  ─── import ───→  workflow_monitor（公開APIのみ）
src/retry_enqueue_trigger/  ─── import ───→  retry_queue（公開APIのみ）
```

`NullRetryEnqueueTrigger`はいずれのパッケージも一切importしない。
`retry_enqueue_trigger`パッケージ全体で見ても`workflow_monitor` /
`retry_queue`の2つにのみ依存する。`retry_engine` / `scheduler` /
`retry_scheduler_source` / `retry_scheduler_decision`のいずれもimportしない。
循環importの余地は構造的に存在しない（`workflow_monitor` / `retry_queue`の
いずれも`retry_enqueue_trigger`を知らない）。

### 残された懸念（Minor、Known Issueとして11章に記録済み）

* Queueから除去された`run_id`の無限再投入リスク（11章 Known Issue）。
  本Releaseでは呼び出し元（Composition Root）が存在しないため実害は
  発生しないが、将来Composition Rootを実装する際は必ずこの制約を踏まえる
  必要がある
* `RetryEnqueueTrigger`に消費者が存在しない状態でリリースされるため、
  実際にComposition Rootで使われる段階になって初めて、メソッド名
  （`enqueue_pending_failures`）や引数（`limit`）が実用に適しているかが
  検証される（`RetrySchedulerSource`等と同じ既知の傾向）

### 総評

Charterの要求（Adapter構成・enqueue機能限定・既存コンポーネント無改修・
Feature Gate追加なし・`retry_engine`非経由・消費者不在の先行実装）と、
ユーザーが確定した4つの方針（Config無し／直接依存／無限再投入対策見送り／
最小集計dataclass）をすべて満たしている。既存Foundation群
（`retry_queue` / `retry_scheduler_source`）との設計整合性を保ちつつ、
Known Issueとして残す制約の所在と将来の対策候補を明記した。
**Approve** と判断する（残された懸念2点はいずれも本Releaseの実装を
ブロックしない、将来Release時の検討事項）。

---

## 15. Status

- [x] Architecture Design ドラフト作成（本文書、Claude Code作成）
- [x] Architecture Review（自己レビュー、Approve）
- [x] ユーザー承認
- [x] Implementation（`src/retry_enqueue_trigger/`、E2Eテスト89件PASS、既存回帰差分なし）
