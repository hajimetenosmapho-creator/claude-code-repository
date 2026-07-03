# v3.6.0 Retry Scheduler Decision Wiring 設計書（Architecture Design）

作成日：2026-07-03
状態：ドラフト（Architecture Review実施済み。ユーザー確認待ち）。
`docs/design/retry_scheduler_decision_wiring_charter.md`（Project Charter、
ユーザー承認済み、2026-07-03）を前提とする。

---

## 1. Architecture Overview

Release 3.5（`docs/design/retry_scheduler_decision.md`）までで、以下の基盤が
整備された。

* Retry Scheduler Integration（v3.3.0）：`RetrySchedulerSource` /
  `NullRetrySchedulerSource`が`RetryQueueManager`の読み取り専用API（`list()` /
  `count()`）を`list_pending_retries()` / `count_pending_retries()`として
  中継するAdapter
* Retry Scheduler Wiring（v3.4.0）：`SchedulerEngine`が`RetrySchedulerSource` /
  `NullRetrySchedulerSource`をConstructor Injectionで保持し、
  `count_pending_retries()` / `list_pending_retries()`への薄い委譲メソッドを持つ
* Retry Scheduler Decision（v3.5.0）：`RetrySchedulerSource`が返す待機中の項目
  一覧から「次に処理すべき候補」を選ぶ専用コンポーネント`RetrySchedulerDecision`
  （`select_candidates(limit)` / `select_next_candidate()`）を新設した。
  `SchedulerEngine`には一切接続しない「消費者不在の先行実装」として完結させた

本Release（v3.6.0）は、`RetrySchedulerDecision`を`SchedulerEngine`へ
Constructor Injectionで接続し、`SchedulerEngine`から候補選択結果を
**読み取れる**状態を作る。v3.4.0が`RetrySchedulerSource`に対して行った統合と
まったく同型のパターンを`RetrySchedulerDecision`に対しても適用する。

Charter承認時にユーザーから示された方針（Dependency Injection節）により、
Open Question 1（Charter 8章）は「`SchedulerEngine`が`RetrySchedulerDecision`を
外部から直接Constructor Injectionで受け取り、`SchedulerEngine`自身は
`RetrySchedulerDecision`をnewしたり組み立てたりしない」という形で確定済みである。
本設計書はこの確定方針を前提に、Open Question 2〜4（省略時の挙動・委譲メソッド名・
`evaluate()`/`run_due()`との関係の明文化）を具体化する。

```
Scheduler（判断、v2.6.0 / v3.4.0）
   │
   ├── RetrySchedulerSource（Adapter、v3.3.0、無改修）
   │        │
   │        └── Retry Queue（v3.1.0、無改修）
   │
   └── RetrySchedulerDecision（v3.5.0、無改修） ★本Releaseで接続
            │  呼び出し元がConstructor Injectionで組み立てて渡す
            │  （SchedulerEngineは組み立てない）
            ▼
      RetrySchedulerSource（同上。RetrySchedulerDecisionが内部に保持）
```

`SchedulerEngine`は`RetrySchedulerDecision`のインスタンスを**受け取って保持する
だけ**であり、その構築（`RetrySchedulerDecision(retry_source)`の呼び出し）は
呼び出し元（Composition Root）の責務のままとする。

---

## 2. Design Policy

Project Charter の Design Principles（5章）およびユーザー承認時の
Architecture Design方針を、本設計では以下の形で具体化する。

1. **Foundation First**：接続（読み取れる状態を作ること）のみを行う。
   選択結果を使った実行・`evaluate()`/`run_due()`への組み込みは後続Releaseへ
   送る（11章 Future Extension）
2. **Single Responsibility**：`SchedulerEngine`に追加するのは
   `RetrySchedulerDecision`の保持と、`select_candidates()` /
   `select_next_candidate()`への薄い委譲のみ。候補選択ロジック自体
   （`RetrySchedulerDecision`）・Queue管理（`retry_queue`）・Adapterとしての
   中継（`retry_scheduler_source`）のいずれも複製・肩代わりしない
3. **Stateless**：`SchedulerEngine`は候補選択結果を独自にキャッシュしない。
   委譲メソッドを呼び出すたびに`RetrySchedulerDecision`経由で最新状態を取得する
4. **Constructor Injection のみ、かつ外部から直接受け取る**：
   `SchedulerEngine.__init__`に`retry_decision`引数を追加する。セッター・
   実行時の差し替えメソッド・ファクトリメソッド（`from_config()`等）は
   追加しない。**`SchedulerEngine`自身が`RetrySchedulerDecision`を
   `new`・組み立てる処理は一切実装しない**（ユーザー承認方針。13章 Design
   Decision #1で詳述）
5. **Backward Compatibility**：`retry_decision`はデフォルト`None`の
   オプション引数とし、既存の`SchedulerEngine()` / `SchedulerEngine(clock=...)` /
   `SchedulerEngine(retry_source=...)`呼び出しは本Release前とまったく同じ結果に
   なる。ただし、v3.4.0の`retry_source`（省略時に`NullRetrySchedulerSource()`を
   構築してフォールバックする）とは異なり、`retry_decision`省略時に
   `SchedulerEngine`が代替インスタンスを構築することは方針4により行わない
   （具体的な代替策は13章 Design Decision #2で述べる）
6. **`evaluate()` / `run_due()`は無改修**：判定ロジック（`SchedulerEvent`生成）に
   候補選択結果を一切組み込まない。v3.4.0と同じく、判定サイクルとは完全に独立した
   新規メソッドとして追加する

---

## 3. Package Structure（変更差分）

```
src/scheduler/
├── __init__.py           # モジュールdocstringのみ更新（v3.6.0の変更点を追記）。__all__は無変更
├── scheduler_engine.py   # ★変更：__init__にretry_decision引数を追加。
│                         #   select_candidates() / select_next_candidate() を新設。
│                         #   evaluate() / run_due() / _match*() / 既存のretry_source
│                         #   関連コード（count_pending_retries / list_pending_retries）は無変更
├── scheduler_config.py   # 無変更
├── scheduler_event.py    # 無変更
├── scheduler_job.py      # 無変更
├── scheduler_manager.py  # 無変更
├── scheduler_repository.py # 無変更
└── exceptions.py         # 無変更

src/retry_scheduler_decision/  # 全ファイル無改修（v3.5.0のまま）
src/retry_scheduler_source/    # 全ファイル無改修（v3.3.0のまま）
src/retry_queue/               # 全ファイル無改修（v3.1.0のまま）
src/retry_engine/              # 全ファイル無改修（本Releaseでは一切関与しない）

tests/
└── test_e2e_v3_6_0_retry_scheduler_decision_wiring.py   # 新規
```

変更対象は`scheduler_engine.py`の1ファイルのみ（`__init__.py`はdocstring更新のみ）。
v3.4.0と同じ変更範囲パターンである。

---

## 4. Public API

### `scheduler_engine.py`（変更部分のみ抜粋）

```python
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from retry_scheduler_decision import RetrySchedulerDecision
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
        retry_decision: "RetrySchedulerDecision | None" = None,
    ):
        self._clock = clock or SystemClockProvider()
        self._retry_source = retry_source if retry_source is not None else NullRetrySchedulerSource()
        self._retry_decision = retry_decision

    # evaluate() / run_due() / _match() / _match_daily() / _match_interval() /
    # _match_once() はいずれも無変更（本Releaseでは1行も触れない）

    # count_pending_retries() / list_pending_retries() はv3.4.0のまま無変更
    # （self._retry_source への委譲。本Releaseでは触れない）

    def select_candidates(self, limit: int | None = None) -> list:
        """
        RetrySchedulerDecision.select_candidates() への委譲。

        retry_decision が注入されていない場合（None）は、空リストを返す。
        SchedulerEngine 自身が RetrySchedulerDecision を構築することはしない
        （retry_decision=None は「候補選択機能を使わない」という呼び出し元の
        明示的な選択として扱う。13章 Design Decision #2）。

        判定サイクル（evaluate() / run_due()）とは独立したメソッドであり、
        呼び出しても SchedulerEvent の生成には一切影響しない（読み取りのみ）。
        """
        if self._retry_decision is None:
            return []
        return self._retry_decision.select_candidates(limit=limit)

    def select_next_candidate(self):
        """
        RetrySchedulerDecision.select_next_candidate() への委譲。

        retry_decision が注入されていない場合（None）は、None を返す
        （候補なしと同じ結果。13章 Design Decision #2）。

        判定サイクル（evaluate() / run_due()）とは独立したメソッドであり、
        呼び出しても SchedulerEvent の生成には一切影響しない（読み取りのみ）。
        """
        if self._retry_decision is None:
            return None
        return self._retry_decision.select_next_candidate()
```

* `retry_decision`は`RetrySchedulerDecision | None`型のオプション引数
  （デフォルト`None`）とする。`RetrySchedulerSource | NullRetrySchedulerSource`の
  ようなUnion型にしないのは、`RetrySchedulerDecision`に対になる`NullRetrySchedulerDecision`
  が存在しない（v3.5.0の意図的な設計判断）ため（13章 Design Decision #2）
* `select_candidates()` / `select_next_candidate()`はいずれも、
  `self._retry_decision`が`None`かどうかを確認するガード節のみを持ち、
  `RetrySchedulerDecision`インスタンスの構築（`RetrySchedulerDecision(...)`の
  呼び出し）は一切行わない。ガード節はNull Object Patternの代替ではなく、
  「未接続の場合の安全なデフォルト値を直接返すだけ」の分岐である
* `retry_decision`が`RetrySchedulerDecision`実体の場合、以降は`RetrySchedulerDecision`
  自身が内部で保持する`retry_source`（v3.5.0で確定済み）を使って候補選択を行う。
  `SchedulerEngine`が別途保持する`self._retry_source`（v3.4.0）とは**独立した
  参照**であり、両者が同じ`RetrySchedulerSource`インスタンスを指すかどうかは
  呼び出し元の組み立て方次第である（8章 Data Flowで詳述）

### `__init__.py` の公開シンボル

変更なし（`SchedulerEngine`は既存のまま`__all__`に含まれている）。

---

## 5. Class Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryQueueManager`（v3.1.0、無改修） | Queueへの出し入れ・整列 | 候補選択・実行判断 |
| `RetrySchedulerSource` / `NullRetrySchedulerSource`（v3.3.0、無改修） | Retry Queueの状態の読み取り専用な中継 | 候補選択ロジック・実行判断 |
| `RetrySchedulerDecision`（v3.5.0、無改修） | `RetrySchedulerSource`が返す既存順序から「次に処理すべき候補」を選ぶ | 実行判断の確定／実行／`SchedulerEngine`への接続の起点になること（受け身の被参照のみ）／自身の構築（呼び出し元の責務） |
| `SchedulerEngine`（本Releaseで変更） | 時刻ベースの判定・pending retryの件数/一覧の読み取り委譲（v3.4.0）・候補選択結果の読み取り委譲（本Release） | 候補選択ロジックの再実装／`RetrySchedulerDecision`の構築（`new`）／判定ロジックへの候補選択結果の反映／実行 |

「`RetrySchedulerDecision`を構築するかどうか・どの`retry_source`を渡して
構築するか」の判定は、`SchedulerEngine`自身の責務ではなく**呼び出し元
（Composition Root）**の責務とする（v3.4.0で`retry_source`について確立した
方針を、`retry_decision`にも一貫して適用する。ただし v3.4.0とは異なり、
`SchedulerEngine`は省略時にも代替インスタンスを構築しない点が本Releaseの
差分である。13章 Design Decision #2）。

---

## 6. Class Diagram

```
┌──────────────────────────────────────────┐
│                 SchedulerEngine                │
│──────────────────────────────────────────│
│ - _clock: ClockProvider                        │
│ - _retry_source: RetrySchedulerSource |        │  v3.4.0
│                   NullRetrySchedulerSource     │
│ - _retry_decision: RetrySchedulerDecision |    │  ★本Releaseで追加
│                     None                        │
│──────────────────────────────────────────│
│ + __init__(clock=None, retry_source=None,      │  ★retry_decision引数を追加
│            retry_decision=None)                 │
│ + evaluate(jobs, now) -> list[SchedulerEvent]   │  無変更
│ + run_due(jobs) -> list[SchedulerEvent]         │  無変更
│ + count_pending_retries() -> int                │  無変更（v3.4.0のまま）
│ + list_pending_retries(limit=None) -> list      │  無変更（v3.4.0のまま）
│ + select_candidates(limit=None) -> list         │  ★新設（委譲＋Noneガード）
│ + select_next_candidate() -> item|None          │  ★新設（委譲＋Noneガード）
│ - _match(job, now)                              │  無変更
└──────────────────────┬───────────────────────┘
                        │ 委譲（select_candidates / select_next_candidate のみ。
                        │ retry_decisionがNoneでない場合のみ到達）
                        ▼
              ┌───────────────────────────┐
              │     RetrySchedulerDecision     │  （v3.5.0、無改修）
              │───────────────────────────│
              │ - _retry_source: ...            │
              │ + select_candidates(limit=None) │
              │ + select_next_candidate()       │
              └───────────────────────────┘
```

`SchedulerEngine`と`RetrySchedulerDecision`の間に継承関係はない
（コンポジション。`_retry_decision`フィールドとして保持するのみ）。
`SchedulerEngine`は`_retry_decision`が`None`の場合、`RetrySchedulerDecision`へは
一切アクセスしない（矢印はガード節を通過した場合のみ発生する）。

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
  │  retry_decision = RetrySchedulerDecision(retry_source)   # ★呼び出し元が組み立てる
  │                                                            # （SchedulerEngineは組み立てない）
  │
  │  engine = SchedulerEngine(
  │      retry_source=retry_source,      # v3.4.0のまま
  │      retry_decision=retry_decision,  # ★本Releaseで追加
  │  )
  ▼
SchedulerEngine が RetrySchedulerSource と RetrySchedulerDecision の両方を
保持した状態で構築される（同じ retry_source インスタンスを共有するかどうかは
呼び出し元の実装次第。SchedulerEngine自身はこの一致を検証・強制しない）
```

`SchedulerEngine`自身は`RetrySchedulerDecision`の構築方法（どの`retry_source`を
渡すか）を一切知らない。「どう構築するか」の判定はすべて呼び出し元にあり、
`SchedulerEngine`は渡された`retry_decision`をそのまま保持するだけである
（v3.4.0の`retry_source`と同じ考え方だが、フォールバック構築を行わない点が異なる。
13章 Design Decision #2）。

### 7.2 select_candidates（retry_decisionが注入されている場合）

```
Caller       SchedulerEngine      RetrySchedulerDecision   RetrySchedulerSource
  │  engine.select_candidates(limit=2)                                          │
  ├───────────────►│                                                            │
  │                 │  self._retry_decision is not None                        │
  │                 │  self._retry_decision.select_candidates(limit=2)          │
  │                 ├────────────────────►│                                    │
  │                 │                      │  self._retry_source.list_pending_retries(limit=2) │
  │                 │                      ├────────────────────────────────────►│
  │                 │                      │◄────────────────────────────────────┤
  │                 │◄─────────────────────┤  list（先頭2件）                     │
  │◄────────────────┤  list（そのまま）                                          │
```

### 7.3 select_candidates / select_next_candidate（retry_decisionが省略された場合）

```
Caller       SchedulerEngine
  │  engine = SchedulerEngine()  # retry_decision省略 → self._retry_decision = None
  │
  │  engine.select_candidates()                              │
  ├───────────────►│                                          │
  │                 │  self._retry_decision is None            │
  │                 │  → RetrySchedulerDecisionへは一切アクセスしない │
  │◄────────────────┤  []（即座に返す）                          │
  │
  │  engine.select_next_candidate()                          │
  ├───────────────►│                                          │
  │                 │  self._retry_decision is None            │
  │◄────────────────┤  None（即座に返す）                        │
```

v3.4.0の`count_pending_retries()`（`NullRetrySchedulerSource()`という
**実インスタンス**を経由して`0`を返す）とは異なり、本Releaseの
`select_candidates()` / `select_next_candidate()`は`RetrySchedulerDecision`の
**インスタンスに一切到達せず**、`SchedulerEngine`内のガード節のみで
同じ結果（空の候補）を返す。挙動の結果は同種だが、経路が異なる
（13章 Design Decision #2）。

### 7.4 evaluate() / run_due()（既存責務。本Releaseでも完全に無変更であることの確認）

```
Caller       SchedulerEngine
  │  engine.evaluate(jobs, now)                               │
  ├───────────────►│                                          │
  │                 │  # retry_source にも retry_decision にも一切アクセスしない │
  │                 │  # v2.6.0時点とまったく同じロジック          │
  │◄────────────────┤  list[SchedulerEvent]（本Release前と同一）  │
```

`evaluate()` / `run_due()`の内部実装は`self._retry_source`・
`self._retry_decision`のいずれも参照しない。既存のv2.6.0回帰テスト（118件）・
v3.4.0回帰テスト（94件）は、`SchedulerEngine`の構築方法（`retry_decision`を
渡すか省略するか）に関わらず、本Release前とまったく同じ結果を返す。

---

## 8. Data Flow

```
① 呼び出し元（Composition Root。本Releaseではテストコードが担う）が、
   既存の RetryQueueConfig.from_env().is_ready() を参照し、Retry Queue連携を
   有効にするかを判断する（v3.4.0のまま。新しい判定ロジックは追加しない）
        ↓
② 有効な場合：RetrySchedulerSource(queue) を構築する
   無効な場合：NullRetrySchedulerSource() を構築する
        ↓
③ 呼び出し元が RetrySchedulerDecision(retry_source) を構築する（②のretry_source
   を渡す。v3.5.0の必須引数どおり）
        ↓
④ SchedulerEngine(retry_source=..., retry_decision=...) を構築する
   （retry_decision を省略した場合、self._retry_decision は None のままとなり、
   SchedulerEngine が代替インスタンスを構築することはない。③を経ずに
   「候補選択機能を使わない」状態になる）
        ↓
⑤ 判定サイクル（evaluate() / run_due()）と、pending retryの参照
   （count_pending_retries() / list_pending_retries()、v3.4.0）と、
   候補選択の参照（select_candidates() / select_next_candidate()、本Release）は、
   同じ SchedulerEngine インスタンス上で呼び出せるが、互いに独立している
   （呼び出し順序に依存関係がない）
   ⑤-a evaluate(jobs, now) → 時刻ベースの判定のみ
   ⑤-b count_pending_retries() / list_pending_retries(limit) → self._retry_source への委譲のみ
   ⑤-c select_candidates(limit) / select_next_candidate() → self._retry_decision への委譲
       （Noneの場合は空の結果を直接返す）
        ↓
⑥ ⑤-cの戻り値（候補）を使って何かを判断・実行する処理は、本Releaseでは
   一切存在しない（読み取れるようになっただけ。11章）
```

---

## 9. Configuration

**本Releaseでは新規の環境変数を一切追加しない**（Charter 5章・8章）。

| 環境変数 | デフォルト | 説明 | 本Releaseでの役割 |
|---|---|---|---|
| `SCHEDULER_ENABLED` | `false` | Scheduler全体の有効/無効（`SchedulerConfig`、無改修） | 本Releaseの変更対象外 |
| `RETRY_QUEUE_ENABLED` | `true` | Retry Queueの有効/無効（`RetryQueueConfig`、無改修） | Composition Rootが`RetrySchedulerSource` / `NullRetrySchedulerSource`のどちらを構築するかの判断に再利用する（v3.4.0のまま） |

`SchedulerEngine`自身は環境変数を一切読まない。「`RetrySchedulerDecision`を
構築して渡すかどうか」の判定は、v3.4.0から一貫して呼び出し元の責務である。

---

## 10. Boundary（今回入れない境界線）

本Releaseが**構造的に**実行不可能にする操作を明示する。

| 操作 | 本Releaseでの扱い | 根拠 |
|---|---|---|
| `SchedulerEngine`が`RetrySchedulerDecision`を`new`・組み立てる | 発生しない | `scheduler_engine.py`のコード全体（4章）に`RetrySchedulerDecision(`という構築呼び出しが一切登場しない。`select_candidates()` / `select_next_candidate()`は`self._retry_decision`が`None`かどうかのガード節のみを持ち、代替インスタンスを生成しない（ユーザー承認方針・13章 Design Decision #1） |
| `RetryQueueManager.dequeue()` | 呼び出し不可 | `RetrySchedulerDecision`自体が`dequeue()`に相当するメソッドを公開していない（v3.5.0時点で非公開）。`SchedulerEngine`が`RetryQueueManager`を直接保持することもない |
| `RetryQueueManager.remove()` | 呼び出し不可 | 同上 |
| Retry Engine（`RetryManager.retry()`）の起動 | 呼び出し不可 | `SchedulerEngine`は`retry_engine`パッケージを一切importしない。候補選択結果を使って何かを実行するコードは本Releaseに一切存在しない |
| Retry Queueへの書き込み（`enqueue`含む） | 呼び出し不可 | `SchedulerEngine`から到達できるのは`RetrySchedulerDecision`の2つの読み取り専用メソッドのみ |
| `evaluate()` / `run_due()`への候補選択結果の組み込み | 発生しない | 4章のコード抜粋・7.4節のSequence Diagramで、両メソッドが`self._retry_decision`を一切参照しないことを明示 |
| 永続化 | 対象外 | `SchedulerEngine`は候補選択結果を保持しない（Stateless。2章） |

Acceptance Criteria（Charter 9章）の「構造的確認」は、上記の表と1対1で
対応する形でテストする（`src/scheduler/`配下に`dequeue` / `remove` /
`RetryManager`という文字列、および`RetrySchedulerDecision(`という構築呼び出しが
存在しないことをテストで確認する）。

---

## 11. Future Extension

* **`evaluate()` / `run_due()`への組み込み**：`select_candidates()` /
  `select_next_candidate()`の戻り値を使って`SchedulerEvent`を生成する、
  または別種のイベントを生成する等の統合（Charter Non-Goals・本設計書10章で
  明示的に対象外とした領域。ROADMAP.md記載の「`SchedulerEvent`を生成する等の
  統合」はここに該当する）
* **実運用のComposition Root**：本Releaseの7.1節で示した組み立て処理を、
  実際に定期実行される起動スクリプト（例：`scripts/run_scheduler.py`）に
  実装する。現時点では該当スクリプトが存在しないため、本Releaseでは
  テストコードが組み立て例を示すのみとする（v3.4.0から持ち越し）
* **自動Retry実行**：`select_next_candidate()`で選ばれた候補を
  `RetryQueueManager.dequeue()`で実際に取り出し`RetryManager.retry()`へ渡す
  一連の自動化（`docs/design/retry_scheduler_decision.md` 11章から持ち越し）
* **`retry_source`と`retry_decision`の一貫性検証**：本Releaseでは
  `SchedulerEngine`が保持する`retry_source`と、`retry_decision`が内部で
  参照する`retry_source`が同一インスタンスであることを検証・強制しない
  （7.1節）。将来、両者の不一致が実運用上の問題になった場合、
  Composition Root側でのアサーションや、`SchedulerEngine`側での整合性確認を
  追加するかどうかを再検討する

---

## 12. Compatibility

* `SchedulerEngine.__init__`へのオプション引数追加のみ。既存の
  `SchedulerEngine()` / `SchedulerEngine(clock=...)` /
  `SchedulerEngine(retry_source=...)`の呼び出しは、本Release前とまったく同じ
  `SchedulerEngine`インスタンスが得られる（`_retry_decision`フィールドが
  増えるが、`evaluate()` / `run_due()` / `count_pending_retries()` /
  `list_pending_retries()`の戻り値には一切影響しない）
* `evaluate()` / `run_due()` / `_match()` / `_match_daily()` /
  `_match_interval()` / `_match_once()` / `count_pending_retries()` /
  `list_pending_retries()`は1行も変更しない
* `SchedulerManager` / `SchedulerRepository` / `SchedulerJob` /
  `SchedulerEvent` / `SchedulerConfig` / `exceptions.py`は無改修
* `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` /
  `retry_engine`配下の全ファイルも無改修
* 新規の環境変数を追加しないため、`.env` / `.env.example`の変更も不要
* 既存の`tests/test_e2e_v2_6_0_scheduler_agent_foundation.py`（118件）・
  `tests/test_e2e_v3_4_0_retry_scheduler_wiring.py`（94件）は無変更のまま
  全PASSする想定（`SchedulerEngine`の構築方法を変えていない既存テストコードに
  対し、本Releaseの変更は後方互換であるため）

---

## 13. Design Decisions（設計判断の根拠）

### Design Decision #1：`SchedulerEngine`は`RetrySchedulerDecision`を組み立てない

Charter 8章 Open Question 1に対し、ユーザー承認時のArchitecture Design方針
（Dependency Injection節）で「`SchedulerEngine`は`RetrySchedulerDecision`を
Constructor Injectionで受け取る構成とし、`SchedulerEngine`自身が`new`したり
組み立てたりする責務は持たせない」という結論が既に示されている。

本設計書はこの結論をそのまま採用する。`scheduler_engine.py`のコード
（4章）には`RetrySchedulerDecision(`という構築呼び出しが一切登場しない。
これはv3.4.0の`retry_source`（省略時に`SchedulerEngine`が
`NullRetrySchedulerSource()`を構築してフォールバックする）とは明確に
異なる方針であり、その差分の扱いをDesign Decision #2で述べる。

### Design Decision #2：`retry_decision`省略時はガード節で安全なデフォルトを返す

Charter 8章 Open Question 2（省略時のフォールバック方式）に対し、
以下の理由から「`SchedulerEngine`内のガード節（`if self._retry_decision is
None`）で`[]` / `None`を直接返す」方式を採用する。

* Design Decision #1の制約（`SchedulerEngine`は`RetrySchedulerDecision`を
  組み立てない）により、v3.4.0のようなフォールバック構築
  （`NullRetrySchedulerSource()`を`SchedulerEngine`が自ら生成する）は
  そもそも選択肢から外れる
* `RetrySchedulerDecision`には対になる`NullRetrySchedulerDecision`が
  存在しない（v3.5.0の意図的な設計判断、`docs/design/retry_scheduler_decision.md`
  13章 Design Decision #2）。仮に本Releaseのためだけに
  `NullRetrySchedulerDecision`を新設すると、v3.5.0で確定した
  「Feature Gate/Config軸を持たないコンポーネントにはNull Object Patternを
  機械的に適用しない」という判断と矛盾し、かつCharter・ユーザー承認方針が
  求める「`retry_scheduler_decision`は無改修」にも反する
* ガード節による直接returnは、Null Object Patternと**結果的に同じ戻り値**
  （空リスト・`None`）を、**インスタンスを1つも生成せずに**実現する。
  「候補選択機能が接続されていない」という状態を、オブジェクトの型ではなく
  `None`という値そのもので表現する設計であり、`RetrySchedulerDecision`側の
  設計（Null Object Pattern不採用）との整合性も保たれる

この結果、`retry_source`（v3.4.0、実インスタンスへのフォールバック）と
`retry_decision`（本Release、ガード節による値レベルのフォールバック）とで
異なるフォールバック手法が`SchedulerEngine`内に混在することになるが、
これはユーザーが明示的に指定した制約（`SchedulerEngine`が
`RetrySchedulerDecision`を組み立てない）から必然的に導かれる差分であり、
場当たり的な不統一ではない。

### Design Decision #3：委譲メソッド名は`select_candidates()` / `select_next_candidate()`とする

Charter 8章 Open Question 3に対し、ユーザー承認時のArchitecture Design方針
（責務節）で「`select_candidates()`への薄い委譲」「`select_next_candidate()`
への薄い委譲」と明示的に指定されているため、`SchedulerEngine`側のメソッド名も
`RetrySchedulerDecision`側と同名の`select_candidates(limit=None)` /
`select_next_candidate()`とする。

`SchedulerEngine`の既存命名（`list_pending_retries` /
`count_pending_retries`）とは異なる命名系列になるが、これは`RetrySchedulerSource`
（一覧取得）と`RetrySchedulerDecision`（候補選択）という異なる意味論を持つ
コンポーネントへの委譲であるため、それぞれの提供元と同じ名前を保つ方が
「`SchedulerEngine`のこのメソッドは何に委譲しているか」が呼び出し元にとって
自明になり、独自の命名変換を挟むより誤解が少ない。

### Design Decision #4：`evaluate()` / `run_due()`とは完全に独立したメソッドとする

Charter 8章 Open Question 4に対し、v3.4.0のDesign Decision #2と同じ結論を
採用する。`select_candidates()` / `select_next_candidate()`は`evaluate()` /
`run_due()`とは独立した新規メソッドとし、`SchedulerEvent`のデータ構造・
判定ロジックには一切手を加えない。理由もv3.4.0と同様（`SchedulerEvent`は
「実行すべきJob」を表すデータモデルであり、候補選択結果は無関係な情報である。
両者を混ぜるとSingle Responsibilityに反する）。

---

## 14. Charter Open Questions への回答

Charter（`docs/design/retry_scheduler_decision_wiring_charter.md`）8章で
保留した4項目に対する結論。

1. **Constructor Injectionの受け方**：`SchedulerEngine`が外部から
   `RetrySchedulerDecision`インスタンスを直接受け取る。`SchedulerEngine`自身は
   構築しない（ユーザー承認方針。13章 Design Decision #1）
2. **省略時のフォールバック方式**：`NullRetrySchedulerDecision`は新設しない。
   `retry_decision=None`の場合、`SchedulerEngine`内のガード節で`[]` /
   `None`を直接返す（13章 Design Decision #2）
3. **委譲メソッド名**：`select_candidates(limit=None)` /
   `select_next_candidate()`（`RetrySchedulerDecision`側と同名。ユーザー承認方針・
   13章 Design Decision #3）
4. **`evaluate()` / `run_due()`との関係の明文化**：完全に独立した新規メソッドとし、
   構造的に候補選択結果が判定ロジックへ影響しないことをコード（4章）・
   Sequence Diagram（7.4節）・Test工程のArchitecture Guardで確認する
   （13章 Design Decision #4）

---

## 16. Architecture Review

状態：**Approve with Minor Recommendations**（Claude Codeによる自己点検。
指摘事項は2件、いずれも本Releaseの実装をブロックしない）。

### 16.1 レビュー観点別の判定

| # | 観点 | 判定 | 根拠 |
|---|---|---|---|
| 1 | `SchedulerEngine`が`RetrySchedulerDecision`を外部から直接DIで受け取る設計が妥当か | **妥当** | ユーザー承認済みのDependency Injection方針と1対1で対応している。`SchedulerEngine`が判定サイクルを持つ唯一のクラスであり、候補選択結果を読み取れるようにするという目的とも一致する |
| 2 | `SchedulerEngine`自身が`RetrySchedulerDecision`を組み立てない制約が守られているか | **守られている** | 4章のコード全体に`RetrySchedulerDecision(`という構築呼び出しが一切登場しない。`select_candidates()` / `select_next_candidate()`は`self._retry_decision`のNoneチェックのみを行う |
| 3 | `retry_decision=None`時のガード節方式（Null Object Patternの代替）が妥当か | **妥当** | v3.5.0で確立した「`RetrySchedulerDecision`にNull Object Patternを適用しない」という設計哲学と、Design Decision #1の制約（組み立てない）の両方を同時に満たす唯一の現実的な選択肢である（13章 Design Decision #2で比較検討済み） |
| 4 | `select_candidates()` / `select_next_candidate()`の委譲がRead Onlyか | **Read Only** | いずれも`self._retry_decision.xxx()`への1行委譲、またはNoneガード節による直接returnのみで、加工・分岐・書き込みを行わない |
| 5 | `evaluate()` / `run_due()`が無変更か | **無変更** | 4章のコード抜粋・7.4節のSequence Diagramで、両メソッドが`self._retry_decision`を一切参照しないことを明示。既存の分岐・マッチングロジックも無変更 |
| 6 | `dequeue()` / `remove()` / Retry Engine起動 / Queue更新が混入しないか | **混入しない（構造的に不可能）** | `RetrySchedulerDecision`自体が該当メソッドを公開していない。`SchedulerEngine`は`retry_engine`パッケージを一切importしない。10章Boundaryで経路の不在を明示 |
| 7 | Foundation First / SRP / Stateless / Constructor Injection / Backward Compatibilityが守られているか | **概ね守られている（SRPはv3.4.0からの継続課題）** | Foundation First：接続のみ・消費者不在の実行ロジックなし。Stateless：候補選択結果をキャッシュしない。Constructor Injection：セッター・ファクトリを追加していない。Backward Compatibility：12章で確認済み。SRPについては16.3節で述べる |
| 8 | `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_engine`が無改修か | **無改修** | 3章Package Structureのとおり、`scheduler`配下1ファイル（`scheduler_engine.py`）の変更のみで、他パッケージへの変更は一切ない |
| 9 | 既存Regressionへの影響がないか | **影響なし** | `__init__`の新規引数はオプション（デフォルト`None`）かつ末尾に追加されており、既存の呼び出し（位置引数・キーワード引数いずれも）は本Release前と同じ`SchedulerEngine`を得る。`tests/test_e2e_v2_6_0_scheduler_agent_foundation.py`（118件）・`tests/test_e2e_v3_4_0_retry_scheduler_wiring.py`（94件）は無改修のまま全PASSする想定 |

### 16.2 SOLID

* **単一責任（SRP）**：`SchedulerEngine`は「時刻ベースの判定」「pending retryの
  読み取り委譲（v3.4.0）」「候補選択の読み取り委譲（本Release）」という
  3つの関心事を持つことになる。v3.4.0のArchitecture Review（16.3節）で
  「3つ目の異種DIが入ったら責務分割を再検討する」というMinor Recommendationを
  残していたが、本Releaseの3つ目（候補選択の読み取り委譲）は「pending retryの
  読み取り委譲」と同じ性質（`RetrySchedulerSource`系列への読み取り専用委譲）の
  延長であり、時刻判定とは独立したメソッド群として分離されている。ただし
  クラス全体で見ると保持するフィールドが3つ（`_clock` / `_retry_source` /
  `_retry_decision`）に増えており、この点は16.3節でMinor Recommendationとして
  扱う
* **開放閉鎖（OCP）**：既存の`evaluate()` / `run_due()`のロジックに変更を
  加えずに新機能を追加できており、既存コードを閉じたまま拡張できている
* **リスコフの置換（LSP）**：本Releaseでは`RetrySchedulerDecision`に対する
  代替型（Null版）が存在しないため、LSPの対象は`retry_source`（v3.4.0のまま）
  のみである。`retry_decision`は「ある/ない（None）」の2値であり、型の
  置換可能性という観点では新たな懸念を持ち込まない
* **インターフェース分離（ISP）**：`SchedulerEngine`が`RetrySchedulerDecision`
  から利用するのは`select_candidates()` / `select_next_candidate()`の
  2メソッドのみで、Charter・ユーザー承認方針が意図した公開範囲と完全に一致する
* **依存性逆転（DIP）**：`SchedulerEngine`は`RetrySchedulerDecision`という
  具象クラスに依存する。ABCは導入していないが、v3.4.0の`retry_source`と
  同じくプロジェクト全体の「継承なしDuck Typing」という設計言語との一貫性を
  優先した判断であり、妥当である

### 16.3 残された懸念（Minor Recommendations）

1. **`SchedulerEngine`が保持するフィールド数の増加**：`_clock` /
   `_retry_source` / `_retry_decision`の3フィールドとなり、v3.4.0
   Architecture Reviewで示唆されていた「3つ目の異種責務」への到達が
   現実になった。ただし本Releaseの3つ目は「読み取り専用の委譲」という
   既存の2つ目（`_retry_source`）と同種の性質であり、時刻判定ロジックとは
   独立しているため、実害としてのSRP違反は限定的である。次Release以降で
   さらに4つ目の異種DIが必要になった時点で、責務分割（判定エンジンと
   Retry関連情報アグリゲータの分離）を改めて検討することを推奨する
2. **`retry_source`と`retry_decision`の非一貫性が検出されない**：
   `SchedulerEngine(retry_source=A, retry_decision=RetrySchedulerDecision(B))`
   のように、異なる`RetrySchedulerSource`インスタンスを渡すことが構造的に
   可能であり、`SchedulerEngine`はこれを検証・警告しない（11章 Future
   Extensionに記載済み）。本Releaseの用途（Composition Rootが両方を一貫して
   組み立てる想定）では実害はないが、テストコードでの組み立て例
   （7.1節）に「同じ`retry_source`を渡すこと」を明記し、将来の実運用スクリプト
   実装時に誤った組み立て方をしないよう注意を促すことを推奨する

いずれも実装を妨げる指摘ではなく、次Release以降で状況に応じて対応を
検討する事項として整理する。

### 16.4 Foundation First・プロジェクト全体との設計整合性

Charter・ユーザー承認方針が要求した「接続のみ（読み取れる状態を作ること）」
という範囲に対し、本設計は`evaluate()` / `run_due()`への組み込み・自動Retry
実行をいずれも11章Future Extensionへ送っており、スコープの逸脱はない。
v3.3.0（`RetrySchedulerSource`）・v3.4.0（`SchedulerEngine`への
`RetrySchedulerSource`接続）・v3.5.0（`RetrySchedulerDecision`）と同じ
「Foundation First・消費者不在の実行ロジックなし」というパターンを維持している。

`SchedulerEngine`が`RetrySchedulerDecision`を組み立てないという制約は、
v3.4.0の`retry_source`フォールバック構築パターンからの意図的な逸脱だが、
これはユーザーが明示的に指示した設計方針であり、かつv3.5.0で確立した
「`RetrySchedulerDecision`にNull Object Patternを適用しない」という判断との
整合性を保つ結果になっている（13章 Design Decision #2）。

### 16.5 依存方向

```
src/scheduler/ ── import ──→ retry_scheduler_decision（公開APIのみ：RetrySchedulerDecision）
src/scheduler/ ── import ──→ retry_scheduler_source（公開APIのみ：
                              RetrySchedulerSource / NullRetrySchedulerSource）
retry_scheduler_decision ── import ──→ retry_scheduler_source（v3.5.0のまま、無改修）
retry_scheduler_source   ── import ──→ retry_queue（v3.3.0のまま、無改修）
```

`scheduler`は`retry_queue`・`retry_engine`のいずれも直接importしない。
`retry_scheduler_decision`は本Releaseでも`scheduler`を一切importしない
（逆方向依存なし）。循環importの余地は構造的に存在しない。

### 16.6 後方互換性

12章で述べたとおり、変更は`SchedulerEngine.__init__`へのオプション引数
追加と、既存メソッドに影響しない2つの新規メソッド追加のみ。`evaluate()` /
`run_due()` / `_match*()` / `count_pending_retries()` /
`list_pending_retries()`はいずれも無変更であり、`SchedulerManager` /
`SchedulerRepository` / `SchedulerJob` / `SchedulerEvent` / `SchedulerConfig` /
`exceptions.py`もゼロ改修。既存呼び出し元（v2.6.0・v3.4.0の既存テストを含む）
への影響はないと判断する。

### 16.7 総評

Charter・ユーザー承認方針が要求した項目（外部からの直接DI・組み立てない制約・
責務の限定（保持＋2つの薄い委譲）・`evaluate()`/`run_due()`等の無改修維持・
Foundation First / SRP / Stateless / Constructor Injection / Backward
Compatibilityの遵守）はいずれも設計上満たされている。Minor Recommendations
2件（16.3節）はいずれも実装をブロックする性質のものではなく、次Release以降の
検討事項として記録すれば足りる。

**Approve with Minor Recommendations** と判断する。

---

## 17. Status

- [x] Architecture Design ドラフト作成（本文書、Claude Code作成）
- [x] Architecture Review完了（Claude Codeによる自己点検、Approve with Minor
      Recommendations。指摘事項2件は次Release検討事項として記録済み）
- [ ] ユーザー確認・実装可否判断
- [ ] 実装開始（未着手）
