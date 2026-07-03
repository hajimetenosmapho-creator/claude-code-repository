# v3.4.0 Retry Scheduler Wiring 設計書（Architecture Design）

作成日：2026-07-03
状態：ドラフト（ChatGPTレビュー待ち）。`docs/design/retry_scheduler_wiring_charter.md`
（Project Charter、ユーザー承認済み、2026-07-03）を前提とする。

---

## 1. Architecture Overview

Release 3.3（`docs/design/retry_scheduler_integration.md`）までで、以下の基盤が
整備された。

* Scheduler（v2.6.0）：`SchedulerEngine.evaluate(jobs, now)` / `run_due(jobs)` が
  時刻ベースで実行対象Jobを判定し `SchedulerEvent` を生成するだけの層。
  Retry Queueの存在を一切知らない
* Retry Scheduler Source（v3.3.0）：`RetrySchedulerSource` /
  `NullRetrySchedulerSource` が `RetryQueueManager` の読み取り専用API
  （`list()` / `count()`）を `list_pending_retries()` /
  `count_pending_retries()` として中継するAdapter。ただし v3.3.0 時点では
  **どのパッケージからも呼ばれていない**（消費者不在の先行実装）

本Release（v3.4.0）は、この2つを **接続するだけ** のRelease である。
`SchedulerEngine` が `RetrySchedulerSource` / `NullRetrySchedulerSource` を
Constructor Injectionで保持できるようにし、判定サイクルと同じクラスの上で
pending retryを**読み取れる**状態を作る。読み取った結果を使って何をするか
（自動実行・通知等）は一切実装しない。

```
Scheduler（判断、v2.6.0）
   │
   │  SchedulerEngine.__init__(clock, retry_source)  ★本Releaseで新設
   ▼
RetrySchedulerSource / NullRetrySchedulerSource（Adapter、v3.3.0、無改修）
   │
   └── Retry Queue（Queue管理、v3.1.0、無改修）
```

`SchedulerEngine` の既存責務（`evaluate()` によるDAILY/INTERVAL/ONCE判定、
`SchedulerEvent` の生成）には一切手を入れない。新設するのは、それとは独立した
「pending retryを読み取るだけの2メソッド」である（4章）。

---

## 2. Design Policy

Project Charterの Design Principles（5章）を、本設計では以下の形で具体化する。

1. **Foundation First**：`SchedulerEngine` が `RetrySchedulerSource` を
   *呼び出せる* 状態を作るところまでを本Releaseの範囲とする。実際に
   pending retryの件数を使って何かを判断・実行する呼び出し元（実運用の
   Scheduler起動スクリプト等）は、本Releaseでは追加しない（11章）。
   これはv3.3.0が「Adapterを作ったが誰も呼ばない」状態で完結したのと対称的に、
   本Releaseは「呼べるようにしたが、呼んだ結果をまだ使わない」状態で完結する

2. **Single Responsibility**：`SchedulerEngine` に追加する2メソッド
   （`count_pending_retries()` / `list_pending_retries()`）は
   `RetrySchedulerSource` への薄い委譲のみを行う。判定ロジック
   （`evaluate()` の中身）にも、Retry Queueの中身にも一切関与しない

3. **Stateless**：`SchedulerEngine` はpending retryの件数・一覧を独自に
   保持・キャッシュしない。呼び出すたびに `RetrySchedulerSource` 経由で
   最新状態を取得する

4. **Constructor Injection のみ**：`SchedulerEngine.__init__` に
   `retry_source` 引数を追加する。セッター・実行時の差し替えメソッド・
   ファクトリメソッド（`from_config()`等）は追加しない

5. **Read Only Adapter**：`SchedulerEngine` が呼び出すのは
   `RetrySchedulerSource` の `list_pending_retries()` /
   `count_pending_retries()` のみ。`dequeue()` / `remove()` に相当する
   メソッドは `RetrySchedulerSource` 自体に存在しないため、構造的に
   呼び出しようがない（10章で境界線を明記）

6. **Backward Compatibility**：`retry_source` はデフォルト `None` の
   オプション引数とし、省略時は `NullRetrySchedulerSource()` に
   フォールバックする。これは v3.2.0 の `RetryManager.__init__` が
   `queue: RetryQueueManager | NullRetryQueueManager | None = None` を
   追加し、省略時に `NullRetryQueueManager()` へフォールバックした設計
   （`docs/design/retry_queue_integration.md` 4章）と全く同じパターンであり、
   既存の `SchedulerEngine(clock=...)` / `SchedulerEngine()` 呼び出しは
   本Release前とまったく同じ挙動になる

7. **新規Wrapperクラスを作らない（Small Release）**：Charter 8章 Open
   Question 1（`SchedulerEngine` に直接持たせるか、別の薄いラッパーを
   設けるか）に対する結論として、新規ラッパークラスは作らない。理由は
   13章で述べる

---

## 3. Package Structure（変更差分）

```
src/scheduler/
├── __init__.py           # モジュールdocstringのみ更新（v3.4.0の変更点を追記）。__all__は無変更
├── scheduler_engine.py   # ★変更：__init__にretry_source引数を追加。
│                         #   count_pending_retries() / list_pending_retries() を新設。
│                         #   evaluate() / run_due() / _match*() は無変更
├── scheduler_config.py   # 無変更
├── scheduler_event.py    # 無変更
├── scheduler_job.py      # 無変更
├── scheduler_manager.py  # 無変更
├── scheduler_repository.py # 無変更
└── exceptions.py         # 無変更

src/retry_scheduler_source/  # 全ファイル無改修（v3.3.0のまま）
src/retry_queue/             # 全ファイル無改修（v3.1.0のまま）
src/retry_engine/            # 全ファイル無改修（本Releaseでは一切関与しない）

tests/
└── test_e2e_v3_4_0_retry_scheduler_wiring.py   # 新規
```

変更対象は `scheduler_engine.py` の1ファイルのみ（`__init__.py` はdocstring更新のみ）。
`SchedulerManager` / `SchedulerRepository` / `SchedulerJob` / `SchedulerEvent` /
`SchedulerConfig` はJob管理・データモデル・Feature Gateの責務であり、
「時刻ベースの判定サイクル」を持つ `SchedulerEngine` とは責務が異なるため、
本Releaseの変更対象に含めない（Charter 8章 Open Question 4への回答。14章で詳述）。

---

## 4. Public API

### `scheduler_engine.py`（変更部分のみ抜粋）

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from retry_scheduler_source import NullRetrySchedulerSource, RetrySchedulerSource

from .scheduler_event import SchedulerEvent
from .scheduler_job import SchedulerJob, TriggerType

# ClockProvider / SystemClockProvider は無変更（省略）


class SchedulerEngine:
    """現在時刻とJob一覧から実行対象Jobを判定するエンジン。"""

    def __init__(
        self,
        clock: ClockProvider | None = None,
        retry_source: "RetrySchedulerSource | NullRetrySchedulerSource | None" = None,
    ):
        self._clock = clock or SystemClockProvider()
        self._retry_source = retry_source if retry_source is not None else NullRetrySchedulerSource()

    # evaluate() / run_due() / _match() / _match_daily() / _match_interval() /
    # _match_once() はいずれも無変更（本Releaseでは1行も触れない）

    def count_pending_retries(self) -> int:
        """
        RetrySchedulerSource.count_pending_retries() への委譲。

        判定サイクル（evaluate() / run_due()）とは独立したメソッドであり、
        呼び出しても SchedulerEvent の生成には一切影響しない（読み取りのみ）。
        """
        return self._retry_source.count_pending_retries()

    def list_pending_retries(self, limit: int | None = None) -> list:
        """
        RetrySchedulerSource.list_pending_retries() への委譲。

        戻り値の要素は RetryQueueItem（retry_queueパッケージの公開型）だが、
        scheduler パッケージは retry_queue に直接依存しない方針のため、
        型ヒントとしてはimportしない（7章 Dependencies参照）。
        判定サイクル（evaluate() / run_due()）とは独立したメソッドであり、
        呼び出しても SchedulerEvent の生成には一切影響しない（読み取りのみ）。
        """
        return self._retry_source.list_pending_retries(limit=limit)
```

* `retry_source` は `RetrySchedulerSource`（実体）を渡すことも
  `NullRetrySchedulerSource()` を渡すことも可能。省略した場合は
  `NullRetrySchedulerSource()` にフォールバックする（2章 Design Policy 6）
* `count_pending_retries()` / `list_pending_retries()` はいずれも
  `self._retry_source` への1行委譲のみ。`try/except` や加工は行わない
  （`RetrySchedulerSource` 自体が例外を送出しない契約であるため。
  `docs/design/retry_scheduler_integration.md` 10章と同じ判断）
* `list_pending_retries()` の戻り値型ヒントを `list`（無型引数）とした
  理由は13章 Design Decision #1で述べる

### `__init__.py` の公開シンボル

変更なし（`SchedulerEngine` は既存のまま `__all__` に含まれている）。

---

## 5. Class Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `SchedulerEngine`（本Releaseで変更） | 時刻とJob一覧から実行対象を判定する（無変更）／`RetrySchedulerSource` を保持し、pending retryの件数・一覧を読み取れるようにする（新設） | pending retryを使って判定を変える・イベントを生成する・Retryを実行する・`dequeue()` / `remove()` を呼ぶ |
| `RetrySchedulerSource` / `NullRetrySchedulerSource`（v3.3.0、無改修） | Retry Queueの状態の読み取り専用な中継 | Scheduler側への組み込み方法の決定（本Releaseで確定） |
| `SchedulerManager` / `SchedulerRepository`（無改修） | Jobの登録・削除・取得・一覧・enable/disable | pending retryの参照（本Releaseでは関与しない） |
| `SchedulerConfig`（無改修） | `SCHEDULER_ENABLED` によるScheduler全体の有効/無効判定 | Retry Queue連携の有効/無効判定（`RetryQueueConfig.is_ready()` が別途担う。9章） |

「`SchedulerEngine` が `RetrySchedulerSource` と `NullRetrySchedulerSource` の
どちらを保持するか」の判定（＝Retry Queue連携を有効にするかどうか）は、
`SchedulerEngine` 自身の責務ではなく **呼び出し元（Composition Root）** の
責務とする（v3.3.0 で確立した「呼び出し元がどちらのクラスを構築するかで
有効/無効が決まる」という設計を、呼び出し元が `SchedulerEngine` を組み立てる
段階まで一段伝播させただけであり、新しい判定ロジックを追加するわけではない）。

---

## 6. Class Diagram

```
┌────────────────────────────────────────┐
│              SchedulerEngine               │
│────────────────────────────────────────│
│ - _clock: ClockProvider                    │
│ - _retry_source: RetrySchedulerSource |    │  ★本Releaseで追加
│                   NullRetrySchedulerSource │
│────────────────────────────────────────│
│ + __init__(clock=None, retry_source=None)  │  ★retry_source引数を追加
│ + evaluate(jobs, now) -> list[SchedulerEvent] │  無変更
│ + run_due(jobs) -> list[SchedulerEvent]    │  無変更
│ + count_pending_retries() -> int           │  ★新設（委譲のみ）
│ + list_pending_retries(limit=None) -> list │  ★新設（委譲のみ）
│ - _match(job, now)                         │  無変更
└──────────────────┬─────────────────────┘
                    │ 委譲（count_pending_retries / list_pending_retries のみ）
                    ▼
   ┌─────────────────────────┐   ┌───────────────────────────┐
   │     RetrySchedulerSource    │   │   NullRetrySchedulerSource   │
   │  （v3.3.0、無改修）           │   │  （v3.3.0、無改修）             │
   └─────────────────────────┘   └───────────────────────────┘
```

`SchedulerEngine` と `RetrySchedulerSource` の間に継承関係はない
（コンポジション。`_retry_source` フィールドとして保持するのみ）。
`SchedulerEngine` は `RetrySchedulerSource` / `NullRetrySchedulerSource` を
Duck Typingで同一視し、どちらが渡されても同じコードで動作する。

---

## 7. Sequence Diagram

### 7.1 Composition Root（呼び出し元）での組み立て

```
Composition Root（本Releaseではテストコードが担う。11章参照）
  │
  │  queue_config = RetryQueueConfig.from_env()
  │
  │  if queue_config.is_ready():   # 既存の RETRY_QUEUE_ENABLED を参照
  │      queue = RetryQueueManager.from_config(queue_config)
  │      retry_source = RetrySchedulerSource(queue)
  │  else:
  │      retry_source = NullRetrySchedulerSource()
  │
  │  engine = SchedulerEngine(retry_source=retry_source)
  ▼
SchedulerEngine が RetrySchedulerSource（またはNull版）を保持した状態で構築される
```

`SchedulerEngine` 自身は `RetryQueueConfig` を一切知らない。
「どちらを構築するか」の判定は呼び出し元にあり、`SchedulerEngine` は
渡された `retry_source` をそのまま保持するだけである。

### 7.2 count_pending_retries（有効な場合）

```
Caller          SchedulerEngine      RetrySchedulerSource      RetryQueueManager
  │  engine.count_pending_retries()                                             │
  ├───────────────►│                                                           │
  │                 │  self._retry_source.count_pending_retries()              │
  │                 ├────────────────────►│                                    │
  │                 │                      │  self._queue.count()              │
  │                 │                      ├───────────────────────────────────►│
  │                 │                      │◄───────────────────────────────────┤
  │                 │◄─────────────────────┤  int                               │
  │◄────────────────┤  int（そのまま）                                          │
```

### 7.3 list_pending_retries / count_pending_retries（無効な場合）

```
Caller          SchedulerEngine      NullRetrySchedulerSource
  │  engine = SchedulerEngine()  # retry_source省略 → NullRetrySchedulerSource() にフォールバック
  │
  │  engine.count_pending_retries()                          │
  ├───────────────►│                                          │
  │                 │  self._retry_source.count_pending_retries() │
  │                 ├────────────────────►│                    │
  │                 │◄─────────────────────┤  0（retry_queueへは一度も到達しない） │
  │◄────────────────┤  0                                       │
```

### 7.4 evaluate() / run_due()（既存責務。本Releaseでも完全に無変更であることの確認）

```
Caller          SchedulerEngine
  │  engine.evaluate(jobs, now)                               │
  ├───────────────►│                                          │
  │                 │  # retry_source には一切アクセスしない       │
  │                 │  # v2.6.0時点とまったく同じロジック          │
  │◄────────────────┤  list[SchedulerEvent]（本Release前と同一）  │
```

`evaluate()` / `run_due()` の内部実装は `self._retry_source` を一切参照しない
（4章のコード抜粋にコメントで明記のとおり）。そのため既存のv2.6.0回帰テスト
（118件）は、`SchedulerEngine` の構築方法（`retry_source` を渡すか省略するか）
に関わらず、本Release前とまったく同じ結果を返す。

---

## 8. Data Flow

```
① 呼び出し元（Composition Root。本Releaseではテストコードが担う）が、
   既存の RetryQueueConfig.from_env().is_ready()（RETRY_QUEUE_ENABLED、
   デフォルトtrue）を参照し、Retry Queue連携を有効にするかを判断する
   （新しい判定ロジック・新しい環境変数はここでは一切追加しない。
   既存のFeature Gateをそのまま再利用するだけ）
        ↓
② 有効な場合：RetryQueueManager.from_config(queue_config) で queue（実体）を
   得て、RetrySchedulerSource(queue) を構築する
   無効な場合：NullRetrySchedulerSource() を構築する
        ↓
③ SchedulerEngine(clock=..., retry_source=retry_source) を構築する
   （retry_source を省略した場合も、SchedulerEngine.__init__ 内で
   NullRetrySchedulerSource() に自動フォールバックする。②を経ずに
   安全なデフォルトになる）
        ↓
④ 判定サイクル（evaluate() / run_due()）と、pending retryの参照
   （count_pending_retries() / list_pending_retries()）は、同じ
   SchedulerEngineインスタンス上で呼び出せるが、互いに独立している
   （④-aと④-bは呼び出し順序に依存関係がない）
   ④-a evaluate(jobs, now) → 時刻ベースの判定のみ。retry_sourceは無関係
   ④-b count_pending_retries() / list_pending_retries(limit)
       → self._retry_source への委譲のみ。jobsやevaluate()の結果とは無関係
        ↓
⑤ ④-bの戻り値（件数・一覧）を使って何かを判断・実行する処理は、
   本Releaseでは一切存在しない（呼び出せるようになっただけ。11章）
```

---

## 9. Configuration

**本Releaseでは新規の環境変数を一切追加しない**（Charter 5章・8章）。

| 環境変数 | デフォルト | 説明 | 本Releaseでの役割 |
|---|---|---|---|
| `SCHEDULER_ENABLED` | `false` | Scheduler全体の有効/無効（`SchedulerConfig`、無改修） | 本Releaseの変更対象外。従来どおりScheduler全体のゲートとしてのみ機能する |
| `RETRY_QUEUE_ENABLED` | `true` | Retry Queueの有効/無効（`RetryQueueConfig`、無改修） | Composition Rootが `RetrySchedulerSource` / `NullRetrySchedulerSource` のどちらを構築するかの判断に**再利用**する（新設ではない） |

`SchedulerEngine` 自身は環境変数を一切読まない。「Retry Queue連携を
有効にするか」の判定は、v3.3.0から一貫して呼び出し元の責務であり、
`SchedulerEngine` に `is_ready()` 相当のメソッドを追加することもしない
（Feature Gate / Config追加なしの方針を`SchedulerEngine`にも適用する）。

---

## 10. Boundary（今回入れない境界線）

本Releaseが**構造的に**実行不可能にする操作を明示する。

| 操作 | 本Releaseでの扱い | 根拠 |
|---|---|---|
| `RetryQueueManager.dequeue()` | 呼び出し不可 | `RetrySchedulerSource` / `NullRetrySchedulerSource` のいずれも `dequeue()` に相当するメソッドを公開していない（v3.3.0の時点で非公開）。`SchedulerEngine` が `RetryQueueManager` を直接保持することもない（7章 Dependencies）ため、`SchedulerEngine` から `dequeue()` へ到達する経路が構造的に存在しない |
| `RetryQueueManager.remove()` | 呼び出し不可 | 同上 |
| Retry Engine（`RetryManager.retry()`）の起動 | 呼び出し不可 | `SchedulerEngine` は `retry_engine` パッケージを一切importしない（7章）。`count_pending_retries()` / `list_pending_retries()` の戻り値を使って何かを実行するコードは本Releaseに一切存在しない |
| Retry Queueへの書き込み（`enqueue`含む） | 呼び出し不可 | `SchedulerEngine` から到達できるのは `RetrySchedulerSource` の2つの読み取り専用メソッドのみ |
| 永続化 | 対象外 | `SchedulerEngine` はpending retryの状態を保持しない（Stateless。2章） |

Acceptance Criteria（Charter 10章）の「構造的確認」は、上記の表と1対1で
対応する形でテストする（`src/scheduler/` 配下に `dequeue` / `remove` /
`RetryManager` という文字列を含むコードが存在しないことをテストで確認する）。

---

## 11. Future Extension

* **実運用のComposition Root**：本Releaseの7.1節で示した組み立て処理を、
  実際に定期実行される起動スクリプト（例：`scripts/run_scheduler.py`）に
  実装する。現時点では該当スクリプトが存在しないため、本Releaseでは
  テストコードが組み立て例を示すのみとする（Small Release。Charter 4章の
  スコープにも新規CLIエントリスクリプトは含まれていない）
* **pending retryの参照結果を使った判断**：`count_pending_retries()` /
  `list_pending_retries()` の戻り値を使って、`SchedulerEvent` を生成する、
  または別種のイベントを生成する等の統合（Charter Non-Goals・本設計書10章
  で明示的に対象外とした領域）
* **自動Retry実行**：pending retryを検知した後、`RetryQueueManager.dequeue()`
  で取り出し `RetryManager.retry()` へ渡す一連の自動化
  （`docs/design/retry_scheduler_integration.md` 11章から持ち越し）
* **`SchedulerEvent` へのpending retry情報の付加**：判定結果
  （`SchedulerEvent`）自体にpending retry件数を含めるかどうかは、
  既存の`SchedulerEvent`データ構造（`job_id` / `execute_time` /
  `trigger_reason` / `metadata`）との整合を含めて再検討が必要なため、
  本Releaseでは行わない（13章 Design Decision #2）
* **Retry Queue連携のFeature Gate統合**：`SCHEDULER_ENABLED` と
  `RETRY_QUEUE_ENABLED` の2つのゲートをComposition Root側でどう扱うか
  （例：両方trueの場合のみ実体を構築する等）は、実運用スクリプト実装時に
  確定する

---

## 12. Compatibility

* `SchedulerEngine.__init__` へのオプション引数追加のみ。既存の
  `SchedulerEngine()` / `SchedulerEngine(clock=...)` の呼び出しは、
  本Release前とまったく同じ `SchedulerEngine` インスタンスが得られる
  （`_retry_source` フィールドが増えるが、`evaluate()` / `run_due()` の
  戻り値には一切影響しない）
* `evaluate()` / `run_due()` / `_match()` / `_match_daily()` /
  `_match_interval()` / `_match_once()` は1行も変更しない
* `SchedulerManager` / `SchedulerRepository` / `SchedulerJob` /
  `SchedulerEvent` / `SchedulerConfig` / `exceptions.py` は無改修
* `retry_scheduler_source` / `retry_queue` / `retry_engine` 配下の
  全ファイルも無改修
* 新規の環境変数を追加しないため、`.env` / `.env.example` の変更も不要
* 既存の `tests/test_e2e_v2_6_0_scheduler_agent_foundation.py`（118件）は
  無変更のまま全PASSする想定（`SchedulerEngine` の構築方法を変えていない
  既存テストコードに対し、本Releaseの変更は後方互換であるため）

---

## 13. Design Decisions（設計判断の根拠）

### Design Decision #1：`list_pending_retries()` の戻り値型を無型の `list` にする

`RetrySchedulerSource.list_pending_retries()` の戻り値は
`list[RetryQueueItem]` だが、`RetryQueueItem` は `retry_queue` パッケージの
公開型であり、`retry_scheduler_source` 経由でも再exportされていない
（`retry_scheduler_source/__init__.py` は `RetrySchedulerSource` /
`NullRetrySchedulerSource` の2シンボルのみを公開。Charter 4章で
`retry_scheduler_source` 自体はゼロ改修と定められており、再export追加もできない）。

`scheduler` パッケージが `RetryQueueItem` を正確に型付けしようとすると
`retry_queue` を直接importする必要が生じ、依存方向が
`scheduler → retry_scheduler_source → retry_queue` の一直線から
`scheduler → retry_queue` の直接依存に崩れてしまう（Charter 7章で
明示的に禁止された経路）。

型の厳密さよりも依存方向の一貫性を優先し、`list_pending_retries()` の
戻り値型は無型の `list` とする（docstringで実際の要素型を説明する）。
これは「今の消費者（テストコードのみ）にとって必要十分な型付け」であり、
将来 `scheduler` 側で `RetryQueueItem` の具体的なフィールドを使う処理が
必要になった時点で、依存方向を含めて再検討する（11章）。

### Design Decision #2：`SchedulerEvent` は変更しない

Charter 8章 Open Question 2（判定サイクルへの組み込み方法）に対し、
「`SchedulerEvent` に情報を追加する」案と「`evaluate()` とは別の新規
読み取り専用メソッドを追加する」案を比較した。

`SchedulerEvent` へ pending retry情報を追加する案は、以下の理由で採用しない。

* `SchedulerEvent` は「実行すべきJob」を表すデータモデルであり
  （`scheduler_event.py` 設計方針）、pending retryの件数はJobの実行判断とは
  無関係な情報である。両者を1つのデータクラスに混ぜると、
  Single Responsibility（2章）に反する
* `evaluate()` の戻り値の形状を変えると、`SchedulerEvent` を消費する
  既存の呼び出し元（将来のTrigger Agent接続部）に影響が及ぶ可能性があり、
  「既存責務を壊さない」というユーザー指示に反する

そのため、`count_pending_retries()` / `list_pending_retries()` という
**`evaluate()` / `run_due()` とは完全に独立したメソッド**を新設する方式を
採用する。同じ `SchedulerEngine` インスタンス上で両方呼び出せるが、
一方の呼び出しがもう一方の結果に影響することはない（7.4節で無変更で
あることを確認済み）。

### Design Decision #3：新規Wrapperクラスを作らない

Charter 8章 Open Question 1（`SchedulerEngine` に直接持たせるか、
`SchedulerManager` に持たせるか、別の新規ラッパーを設けるか）に対し、
`SchedulerEngine` に直接持たせる方式を採用する。

* `SchedulerManager` はJobの登録・削除・取得・一覧・enable/disableという
  CRUD責務を持つクラスであり、「時刻ベースの判定」を行わない
  （`scheduler_manager.py` 設計方針）。pending retryの参照は判定サイクルに
  関連する関心事であるため、`SchedulerManager` に持たせるのは責務の
  ミスマッチになる
* 新規ラッパークラス（例：`SchedulerRetryAwareEngine`）を追加する案は、
  「接続するだけ」の本Releaseの範囲に対して過剰な抽象化であり、
  Small Release（2章）の方針に反する。v3.2.0で `RetryManager` が
  `RetryQueueManager` を直接DIで受け取った（ラッパークラスを作らなかった）
  前例（`docs/design/retry_queue_integration.md`）とも整合する

### Design Decision #4：`SchedulerConfig` は変更しない

Charter 8章 Open Question 4に対し、`SchedulerConfig` へのフィールド追加は
行わないと結論する。

* `SchedulerConfig.enabled`（`SCHEDULER_ENABLED`）はScheduler全体の
  有効/無効を表すFeature Gateであり、「Retry Queue連携を有効にするか」は
  別の関心事である（後者は既存の `RetryQueueConfig.enabled`
  （`RETRY_QUEUE_ENABLED`）が既に担っている。9章）
* `SchedulerEngine` が `retry_source` を保持するかどうかは
  Constructor Injectionのみで表現され（Null Object Pattern）、
  Configクラスのフィールドとして表現する必然性がない
  （v3.2.0で `RetryConfig` に `queue` 関連フィールドを追加しなかった
  前例と同じ判断）
* 結果として `scheduler_config.py` は本Releaseでもゼロ改修となる

---

## 14. Charter Open Questions への回答

Charter（`docs/design/retry_scheduler_wiring_charter.md`）8章で保留した
4項目に対する結論。

1. **Constructor Injectionの受け口**：`SchedulerEngine` に直接持たせる
   （13章 Design Decision #3）
2. **判定サイクルへの組み込み方法**：`evaluate()` / `run_due()` とは独立した
   新規メソッド（`count_pending_retries()` / `list_pending_retries()`）を
   追加する（13章 Design Decision #2）
3. **`RetrySchedulerSource` と `NullRetrySchedulerSource` のどちらを
   構築するかの判断をどこに置くか**：呼び出し元（Composition Root）に置く。
   本Releaseでは `RetryQueueConfig.is_ready()`（既存の
   `RETRY_QUEUE_ENABLED`）を再利用する例をテストコードで示すのみとし、
   実運用の起動スクリプトは11章のFuture Extensionとする
4. **既存 `SchedulerConfig` との関係**：フィールド追加は行わない
   （13章 Design Decision #4）。`scheduler_config.py` はゼロ改修

---

## 16. Architecture Review

状態：**Approve with Minor Recommendations**（Claude Codeによる自己点検。
指摘事項は3件、いずれも本Releaseの実装をブロックしない）。

### 16.1 レビュー観点別の判定（ユーザー指定9項目）

| # | 観点 | 判定 | 根拠 |
|---|---|---|---|
| 1 | `SchedulerEngine` に `RetrySchedulerSource` を直接DIする設計が妥当か | **妥当** | `SchedulerEngine` が判定サイクル（`evaluate()` / `run_due()`）を持つ唯一のクラスであり、Charter Goal 4「Schedulerの判定サイクルへ組み込む」と一致する。さらに `src/scheduler/__init__.py`（v2.6.0）のdocstringが将来拡張候補として「retry（判定・実行失敗時の再試行）」を明示的に挙げており、`SchedulerEngine` へのretry関連拡張は当初から想定範囲内だった（16.4節で詳述）。一方、判定ロジックとpending retry参照という2つの異なる関心事が同一クラスに同居する点はSRP上のトレードオフであり、16.3節でMinor Recommendationとして扱う |
| 2 | `SchedulerManager` や新規Wrapperを追加しない判断が妥当か | **妥当** | `SchedulerManager` はJob CRUD責務でありtime-basedな判定を持たない（責務のミスマッチ）。新規Wrapperは「接続するだけ」のFoundation Releaseに対して過剰な抽象化であり、v3.2.0の`RetryManager`が`RetryQueueManager`を直接DIで受け取りラッパーを作らなかった前例とも整合する（Design Decision #3） |
| 3 | `RetryQueueManager` を `SchedulerEngine` が直接保持しない境界が守られているか | **守られている** | 4章のPublic APIコード抜粋・7章Dependenciesのいずれにも `retry_queue` のimportが登場しない。`SchedulerEngine` が参照できるのは `RetrySchedulerSource` の公開2メソッドのみであり、`RetryQueueManager` へは構造的に到達できない |
| 4 | `retry_source=None` → `NullRetrySchedulerSource` フォールバックの後方互換設計が適切か | **適切** | v3.2.0の`RetryManager.__init__`（`queue: RetryQueueManager \| NullRetryQueueManager \| None = None` → `NullRetryQueueManager()`フォールバック）と同一パターン。本プロジェクトで既に実績のある手法を踏襲しており、新規リスクを持ち込んでいない |
| 5 | `evaluate()` / `run_due()` を変更せず新規メソッド追加に留める設計が安全か | **安全** | 4章のコード抜粋・7.4節のSequence Diagramで、両メソッドが `self._retry_source` を一切参照しないことを明示。既存の分岐・マッチングロジック（`_match` / `_match_daily` / `_match_interval` / `_match_once`）も無変更であり、判定結果（`SchedulerEvent`の内容）に影響する経路が存在しない |
| 6 | `count_pending_retries()` / `list_pending_retries()` がRead Only Adapterへの委譲のみになっているか | **なっている** | いずれも `self._retry_source.xxx()` への1行委譲のみで、加工・分岐・例外処理を持たない（4章）。`RetrySchedulerSource`自体が読み取り専用契約を持つため、委譲するだけで自動的にRead Only性が伝播する |
| 7 | `dequeue()` / `remove()` / Retry Engine起動が混入しないか | **混入しない（構造的に不可能）** | `RetrySchedulerSource` / `NullRetrySchedulerSource` は `dequeue()` / `remove()` 相当のメソッドをそもそも公開していない（v3.3.0時点で非公開）。`SchedulerEngine` は `retry_engine` パッケージを一切importしない。10章Boundaryで経路の不在を明示しており、実装後は「`src/scheduler/`配下に`dequeue`/`remove`/`RetryManager`という文字列が存在しない」ことをテストで構造的に確認する方針も示されている |
| 8 | Foundation First / SRP / Stateless / Constructor Injection / Backward Compatibilityが守られているか | **概ね守られている（SRPはMinor）** | Foundation First：接続のみで消費者不在（Goals 1-4に対応）。Stateless：pending retryの値をキャッシュしない（2章）。Constructor Injection：セッター・ファクトリを追加していない。Backward Compatibility：#4・#5で確認済み。SRP：#1で述べたトレードオフがあり、16.3節でMinor Recommendationとする |
| 9 | 既存Regressionへの影響がないか | **影響なし** | `__init__`の新規引数はオプション（デフォルト`None`）かつ末尾に追加されており、既存の位置引数呼び出し（`SchedulerEngine(clock)`）・キーワード呼び出し（`SchedulerEngine(clock=...)`）のいずれも本Release前と同じ`SchedulerEngine`を得る。`evaluate()`/`run_due()`の戻り値・分岐ロジックも無変更のため、`tests/test_e2e_v2_6_0_scheduler_agent_foundation.py`（118件）は無改修のまま全PASSする想定 |

### 16.2 SOLID

* **単一責任（SRP）**：`SchedulerEngine`は「時刻ベースの判定」と「pending retryの読み取り委譲」という2つの関心事を持つことになるが、両者は独立したメソッド群として分離されており、内部状態も混ざらない（`_clock`と`_retry_source`は互いに参照し合わない）。クラス全体では2責務だが、メソッド単位では単一責任が保たれている（16.3節でさらに議論）
* **開放閉鎖（OCP）**：既存の`evaluate()`/`run_due()`のロジックに変更を加えずに新機能を追加できており、既存コードを閉じたまま拡張できている
* **リスコフの置換（LSP）**：`RetrySchedulerSource`と`NullRetrySchedulerSource`の戻り値型が一致しているため（v3.3.0で確認済み）、`SchedulerEngine`側もどちらを注入されても同じ型で動作する
* **インターフェース分離（ISP）**：`SchedulerEngine`が`RetrySchedulerSource`から利用するのは`list_pending_retries()`/`count_pending_retries()`の2メソッドのみで、Charter・v3.3.0設計が意図した公開範囲と完全に一致する
* **依存性逆転（DIP）**：`SchedulerEngine`は`RetrySchedulerSource`という具象クラスに依存する（Union型経由）。抽象基底クラス（ABC）は導入していないが、`ClockProvider`（既存の唯一のABC）とは異なり、`RetrySchedulerSource`/`NullRetrySchedulerSource`はプロジェクト全体で「継承なしのDuck Typing」を意図的に採用しているため、ここでABCを導入しないのは既存設計言語との一貫性を優先した妥当な判断である

### 16.3 残された懸念（Minor Recommendations）

1. **`SchedulerEngine`のSRPトレードオフ**：時刻判定とpending retry参照という2つの関心事が1クラスに同居する。現時点ではメソッドが完全に独立しており実害はないが、将来さらに別の関心事（例：cron対応、last_run_at保持）が同じクラスに追加され続けると、`SchedulerEngine`が「何でも屋」になるリスクがある。次のRelease以降で3つ目の異種DIが必要になった時点で、責務分割（判定エンジンとpending情報アグリゲータの分離）を再検討することを推奨する。本Releaseの範囲では2つ目の追加に留まるため、実装をブロックする理由にはならない
2. **`retry_scheduler_source`パッケージのdocstring陳腐化**：`src/retry_scheduler_source/__init__.py`および`retry_scheduler_source.py`のdocstringには「本Release時点ではどのパッケージからも呼ばれない」（v3.3.0時点の記述）が残っている。本Release（v3.4.0）で`scheduler`から実際に呼ばれるようになるため、この記述は事実と異なる状態になる。ただしCharter 4章・9章は`retry_scheduler_source`配下の**全ファイルゼロ改修**を要求しており、コメント修正であっても`git diff`が発生してしまう。本Releaseでは意図的にこの記述を放置し、`docs/CHANGELOG.md`に既知のドキュメント負債として記録した上で、次回`retry_scheduler_source`に触れるRelease（またはドキュメント整備専用Release）で修正することを推奨する（v2.6.0のROADMAP遡及記載と同種の扱い）
3. **`list_pending_retries()`の戻り値が無型の`list`であること**：Design Decision #1で意図的に選択した設計であり、依存方向の一貫性を優先した合理的なトレードオフである。実害はないが、将来`scheduler`側で`RetryQueueItem`のフィールド（`run_id`等）を実際に使う処理が必要になった時点で、型付けの方法（`retry_scheduler_source`側での型再export等）を再検討する必要がある点を記録しておく

いずれも実装を妨げる指摘ではなく、次Release以降で状況に応じて対応を検討する事項として整理する。

### 16.4 Foundation First・プロジェクト全体との設計整合性

`src/scheduler/__init__.py`（v2.6.0）のdocstringは、将来拡張候補として
「cron対応」「retry（判定・実行失敗時の再試行）」「last_run_at保持」
「persistence」「Windows Task Scheduler / Linux cron連携」を明示し、
「既存クラスへのフィールド追加・新規クラス追加で対応できる設計」としている。
本Releaseの`SchedulerEngine.__init__`へのオプション引数追加は、この
「フィールド追加による拡張」という当初からの想定路線に沿っており、
場当たり的な設計変更ではない。

Charter（4章・8章）が要求した「Adapterの新設と読み取り機能の実装のみ」
（v3.3.0）に続き、本Release（v3.4.0）は「接続経路の確立のみ」に範囲を
限定しており、`count_pending_retries()`/`list_pending_retries()`の
戻り値を使って何かを実行する処理は一切実装しない（10章・11章）。
v2.9.0（`WorkflowMonitorManager`のDI）・v3.1.0（Retry Queue）・v3.3.0
（`RetrySchedulerSource`）と同じ「消費者不在／利用不在の先行実装」の
パターンを維持しており、Foundation Firstの一貫性が保たれている。

### 16.5 依存方向

```
src/scheduler/ ── import ──→ retry_scheduler_source（公開APIのみ：
                              RetrySchedulerSource / NullRetrySchedulerSource）
retry_scheduler_source ── import ──→ retry_queue（v3.3.0のまま、無改修）
```

`scheduler`は`retry_queue`・`retry_engine`のいずれも直接importしない
（10章）。`retry_scheduler_source`は本Releaseでも`scheduler`を一切
importしない（逆方向依存なし）。循環importの余地は構造的に存在しない。

### 16.6 後方互換性

12章で述べたとおり、変更は`SchedulerEngine.__init__`へのオプション引数
追加と、既存メソッドに影響しない2つの新規メソッド追加のみ。`evaluate()`/
`run_due()`/`_match*()`はいずれも無変更であり、`SchedulerManager`/
`SchedulerRepository`/`SchedulerJob`/`SchedulerEvent`/`SchedulerConfig`/
`exceptions.py`もゼロ改修。既存呼び出し元（`tests/test_e2e_v2_6_0_scheduler_agent_foundation.py`
118件を含む）への影響はないと判断する。

### 16.7 総評

Charterが要求した9項目（Wiring・生成方法・安全なDI・判定サイクルへの組み込み・
既存責務保持・Read Only境界・dequeue等の排除・Backward Compatibility・
既存Regression回避）はいずれも設計上満たされている。Minor Recommendations
3件（16.3節）はいずれも実装をブロックする性質のものではなく、次Release以降の
検討事項として記録すれば足りる。

**Approve with Minor Recommendations** と判断する。

---

## 17. Status

- [x] Architecture Design ドラフト作成（本文書、Claude Code作成）
- [x] Architecture Review完了（Claude Codeによる自己点検、Approve with Minor
      Recommendations。指摘事項3件はDesign Decisionまたは次Release検討事項として記録済み）
- [ ] ChatGPTレビュー（Project Charter・Architecture Designの妥当性確認）
- [ ] ユーザー確認・実装可否判断
- [ ] 実装開始（未着手）
