# v3.7.0 Retry Scheduler Event Integration 設計書（Architecture Design）

作成日：2026-07-03
状態：ドラフト（Architecture Review実施済み。ユーザー確認待ち）。
`docs/design/retry_scheduler_event_integration_charter.md`（Project Charter、
ユーザー承認済み、2026-07-03）を前提とする。

---

## 1. Architecture Overview

Release 3.6（`docs/design/retry_scheduler_decision_wiring.md`）までで、以下の
基盤が整備された。

* `SchedulerEngine`は`RetrySchedulerDecision`（v3.5.0）をConstructor Injectionで
  保持し、`select_candidates(limit)` / `select_next_candidate()`への薄い
  委譲メソッドを持つ（v3.6.0）
* `evaluate()` / `run_due()`（時刻ベースの判定、`SchedulerEvent`生成）は
  v3.4.0・v3.6.0を通じて一貫して無改修だった

本Release（v3.7.0）は、**`evaluate()` / `run_due()`の判定ロジックそのものに
初めて手を加え**、`RetrySchedulerDecision`が選んだRetry候補を`SchedulerEvent`
として出力に含める。ただし、以下の不変条件をコード構造で保証する。

* `retry_decision`が`None`の場合、`evaluate()` / `run_due()`の出力は
  v3.6.0時点と完全に同一
* Retry候補由来の`SchedulerEvent`は「候補として選ばれた」という事実のみを
  表現するデータであり、そのイベントを消費して何かを実行する処理
  （Retry Engine起動・Queue操作）は一切追加しない

```
Scheduler（判断）
   │
   ├── evaluate(jobs, now, retry_limit=None)  ★本Releaseで変更
   │        │
   │        ├── 既存のJob判定ループ（_match* 系、1行も変更しない）
   │        │        → SchedulerEvent（Job由来、既存のまま）
   │        │
   │        └── self.select_candidates(limit=retry_limit)（v3.6.0、無変更）
   │                 │  retry_decision が None の場合は常に [] を返す
   │                 │  （v3.6.0で確立済みのガード節をそのまま再利用）
   │                 ▼
   │             RetrySchedulerDecision → RetrySchedulerSource → Retry Queue
   │             （いずれも無改修。読み取り専用）
   │                 │
   │                 └→ SchedulerEvent（Retry候補由来、★本Releaseで新規）
   │
   └── run_due(jobs, retry_limit=None) ★引数追加のみ。evaluate()への委譲は無変更
```

本Releaseの核心は、「Job判定ループ」と「Retry候補反映ループ」を
**同一メソッド内で完全に独立した2つのブロックとして共存させる**ことである。
両者はデータの読み取り元も判定条件も異なり、互いの出力に影響を与えない。

---

## 2. Design Policy

Project Charter の Design Principles（5章）およびユーザー指示（本メッセージの
重点項目8点）を、本設計では以下の形で具体化する。

1. **Foundation First**：Retry候補を`SchedulerEvent`として「表現できる」ように
   するところまでを行う。生成された`SchedulerEvent`を使った実行は
   一切追加しない（11章 Future Extension）
2. **Single Responsibility**：`evaluate()`は「時刻ベースのJob判定」と
   「Retry候補の`SchedulerEvent`化」という2つの独立した関心事を持つことになるが、
   両者はコード上も完全に分離したブロック（Job判定ループ／Retry候補反映ループ）
   として実装し、後者を`_build_retry_events()`という専用privateメソッドに
   切り出すことで、`evaluate()`本体の可読性と検証容易性を保つ
3. **Stateless**：Retry候補由来の`SchedulerEvent`をキャッシュしない。
   `evaluate()`を呼び出すたびに`self.select_candidates()`経由で最新状態を
   取得する（v3.6.0までと同じ方針の延長）
4. **既存委譲メソッドの再利用**：Retry候補の取得は、本Releaseで新設する
   ロジックではなく、v3.6.0で確立済みの`self.select_candidates(limit=retry_limit)`
   をそのまま呼び出す。これにより「`retry_decision`が`None`の場合は空リストを
   返す」というガード節（v3.6.0で実装済み）を重複実装せずに再利用でき、
   `evaluate()`側に`None`チェックの分岐を新設する必要がなくなる
5. **Backward Compatibility**：`evaluate(jobs, now, retry_limit=None)` /
   `run_due(jobs, retry_limit=None)`はいずれも既存引数の末尾に
   デフォルト値付きの新規引数を追加するのみ。既存の`evaluate(jobs, now)` /
   `run_due(jobs)`という位置引数2つ・1つの呼び出しは、本Release後も
   まったく同じ結果になる（`retry_decision`が`None`の場合。13章 Design Decision #1）
6. **`retry_queue`への直接依存を作らない**：`RetryQueueItem`固有の属性
   （`workflow_name` / `priority` / `retry_attempt` / `status`）を`scheduler_engine.py`内で
   分解・型変換しない。`select_candidates()`が返す候補オブジェクトを
   `metadata`辞書の値として**そのまま**格納する（Duck Typingを最小限にとどめ、
   フィールド単位での型知識を持たない。13章 Design Decision #3）
7. **`job_id`の代替**：`SchedulerEvent.job_id`は本来`SchedulerJob.job_id`を
   想定した文字列フィールドだが、Retry候補には対応するフィールドが存在しない。
   候補オブジェクトが持つ`run_id`属性（v3.1.0から存在する公開フィールド）に
   `"retry:"`という予約プレフィックスを付けた文字列を採用する
   （`import`を追加せず、属性アクセスのみで完結させる。13章 Design Decision #2）

---

## 3. Package Structure（変更差分）

```
src/scheduler/
├── __init__.py           # モジュールdocstringのみ更新（v3.7.0の変更点を追記）。__all__は無変更
├── scheduler_engine.py   # ★変更：evaluate() / run_due() に retry_limit 引数を追加。
│                         #   Retry候補を SchedulerEvent 化する _build_retry_events() を新設。
│                         #   REASON_RETRY_CANDIDATE_SELECTED 定数を追加。
│                         #   _match* 系メソッド・count_pending_retries() /
│                         #   list_pending_retries() / select_candidates() /
│                         #   select_next_candidate() は無変更
├── scheduler_config.py   # 無変更
├── scheduler_event.py    # 無変更（SchedulerEventのデータ構造自体は変更しない）
├── scheduler_job.py      # 無変更
├── scheduler_manager.py  # 無変更
├── scheduler_repository.py # 無変更
└── exceptions.py         # 無変更

src/retry_scheduler_decision/  # 全ファイル無改修（v3.5.0/v3.6.0のまま）
src/retry_scheduler_source/    # 全ファイル無改修（v3.3.0のまま）
src/retry_queue/               # 全ファイル無改修（v3.1.0のまま）
src/retry_engine/              # 全ファイル無改修（本Releaseでは一切関与しない）

tests/
└── test_e2e_v3_7_0_retry_scheduler_event_integration.py   # 新規
```

変更対象は`scheduler_engine.py`の1ファイルのみ（`__init__.py`はdocstring更新のみ）。
v3.4.0・v3.6.0と同じ変更範囲パターンである。`scheduler_event.py`を変更しない
（`SchedulerEvent`データ構造は無改修のまま）点が、Charter 11章で「見直す可能性あり」と
していた点への結論である（13章 Design Decision #3で理由を述べる）。

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

REASON_DAILY_MATCHED = "Daily schedule matched."
REASON_INTERVAL_MATCHED = "Interval schedule matched."
REASON_ONCE_MATCHED = "One-time schedule matched."
REASON_RETRY_CANDIDATE_SELECTED = "Retry candidate selected."  # ★新設

# ClockProvider / SystemClockProvider は無変更（省略）


class SchedulerEngine:
    """現在時刻とJob一覧から実行対象Jobを判定するエンジン。"""

    # __init__ は無変更（v3.6.0のまま。省略）

    def evaluate(
        self,
        jobs: list[SchedulerJob],
        now: datetime,
        retry_limit: int | None = None,
    ) -> list[SchedulerEvent]:
        """
        現在時刻とJob一覧から、実行対象と判定されたJobのSchedulerEventのリストに、
        Retry候補由来のSchedulerEventを追加して返す（副作用なしの純粋関数）。

        Job判定ロジック（disabled除外・schedule形式マッチング）はv2.6.0から
        1行も変更していない。Retry候補の反映は、Job判定ループとは完全に独立した
        追加ブロックとして行う（_build_retry_events()）。

        retry_decision が注入されていない場合（None）、_build_retry_events() は
        既存の select_candidates()（v3.6.0のガード節）により常に空リストを返すため、
        本メソッドの出力はv3.6.0時点とまったく同一になる。
        """
        events: list[SchedulerEvent] = []
        for job in jobs:
            if not job.enabled:
                continue

            reason = self._match(job, now)
            if reason is None:
                continue

            events.append(
                SchedulerEvent(
                    job_id=job.job_id,
                    execute_time=now,
                    trigger_reason=reason,
                    metadata=dict(job.metadata),
                )
            )

        events.extend(self._build_retry_events(now, retry_limit))
        return events

    def run_due(
        self,
        jobs: list[SchedulerJob],
        retry_limit: int | None = None,
    ) -> list[SchedulerEvent]:
        """ClockProviderから現在時刻を取得し、evaluate()を呼び出す便利メソッド。"""
        return self.evaluate(jobs, now=self._clock.now(), retry_limit=retry_limit)

    def _build_retry_events(
        self,
        now: datetime,
        retry_limit: int | None,
    ) -> list[SchedulerEvent]:
        """
        Retry候補を SchedulerEvent のリストに変換する（本Releaseで新設）。

        self.select_candidates(limit=retry_limit)（v3.6.0）への委譲のみを行う。
        retry_decision が None の場合、select_candidates() は既存のガード節により
        空リストを返すため、本メソッドも空リストを返す（新たな None チェックを
        ここで重複実装しない）。

        候補オブジェクト（RetryQueueItemの公開属性を持つオブジェクト。型としては
        importしない）の run_id 属性のみを job_id 生成に使用し、"retry:" という
        予約プレフィックスを付ける。他の属性（workflow_name / priority /
        retry_attempt / status）は分解・変換せず、候補オブジェクトそのものを
        metadata["retry_candidate"] にそのまま格納する（13章 Design Decision #3）。

        Queueの状態を変更する操作（dequeue() / remove()）・Retry Engineの起動には
        一切到達しない（select_candidates() は読み取り専用の委譲のみ）。
        """
        events: list[SchedulerEvent] = []
        for candidate in self.select_candidates(limit=retry_limit):
            events.append(
                SchedulerEvent(
                    job_id=f"retry:{candidate.run_id}",
                    execute_time=now,
                    trigger_reason=REASON_RETRY_CANDIDATE_SELECTED,
                    metadata={"retry_candidate": candidate},
                )
            )
        return events

    # count_pending_retries() / list_pending_retries() / select_candidates() /
    # select_next_candidate() はv3.4.0・v3.6.0のまま無変更（省略）

    # _match() / _match_daily() / _match_interval() / _match_once() は
    # 無変更（省略）
```

* `evaluate()` / `run_due()`とも、既存引数の**末尾**にデフォルト値付きの
  `retry_limit: int | None = None`を追加する。位置引数・キーワード引数いずれの
  既存呼び出しも影響を受けない
* Job判定ループ（`for job in jobs: ...`）は元のコードから1文字も変更しない。
  Retry候補の反映は`events.extend(self._build_retry_events(now, retry_limit))`
  という1行の追加のみで完結する
* `_build_retry_events()`は`self.select_candidates(limit=retry_limit)`（v3.6.0）
  への委譲のみを行い、`self._retry_decision`を直接参照しない。これにより
  「`retry_decision`が`None`の場合の安全なデフォルト（空リスト）」という
  v3.6.0のガード節を再利用でき、`evaluate()`側に新たな分岐ロジックを増やさない

### `__init__.py` の公開シンボル

変更なし（`SchedulerEngine`は既存のまま`__all__`に含まれている）。

---

## 5. Class Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryQueueManager`（v3.1.0、無改修） | Queueへの出し入れ・整列 | 候補選択・実行判断・イベント生成 |
| `RetrySchedulerSource` / `NullRetrySchedulerSource`（v3.3.0、無改修） | Retry Queueの状態の読み取り専用な中継 | 候補選択ロジック・実行判断・イベント生成 |
| `RetrySchedulerDecision`（v3.5.0、無改修） | 待機中の項目一覧から「次に処理すべき候補」を選ぶ | イベント生成・実行判断 |
| `SchedulerEngine`（本Releaseで変更） | 時刻ベースの判定・Retry候補選択結果の読み取り委譲（v3.6.0）・Retry候補の`SchedulerEvent`化（本Release） | 候補選択ロジックの再実装／Retry候補の属性の解釈・加工／Queueの変更／実行 |
| Retry Engine・Workflow Engine等（本Releaseでは無関係） | （本Releaseの`SchedulerEvent`を将来消費する側） | 本Releaseの対象外 |

`SchedulerEvent`を生成する責務は本Releaseでも`SchedulerEngine`のみが持つ。
`RetrySchedulerDecision`は「選ぶ」ところまでで責務が完結し、選んだ結果を
どう表現するか（`SchedulerEvent`化）には一切関与しない
（v3.5.0で確立済みの責務境界を維持）。

---

## 6. Class Diagram

```
┌──────────────────────────────────────────┐
│                 SchedulerEngine                │
│──────────────────────────────────────────│
│ - _clock: ClockProvider                        │
│ - _retry_source: RetrySchedulerSource |        │  v3.4.0
│                   NullRetrySchedulerSource     │
│ - _retry_decision: RetrySchedulerDecision |    │  v3.6.0
│                     None                        │
│──────────────────────────────────────────│
│ + __init__(clock=None, retry_source=None,      │  無変更
│            retry_decision=None)                 │
│ + evaluate(jobs, now, retry_limit=None)         │  ★retry_limit引数を追加
│     -> list[SchedulerEvent]                     │  ★Retry候補由来のEventを追加
│ + run_due(jobs, retry_limit=None)               │  ★retry_limit引数を追加
│     -> list[SchedulerEvent]                     │  （evaluate()への委譲は無変更）
│ + count_pending_retries() -> int                │  無変更（v3.4.0のまま）
│ + list_pending_retries(limit=None) -> list      │  無変更（v3.4.0のまま）
│ + select_candidates(limit=None) -> list         │  無変更（v3.6.0のまま）
│ + select_next_candidate() -> item|None          │  無変更（v3.6.0のまま）
│ - _build_retry_events(now, retry_limit)         │  ★新設（private）
│     -> list[SchedulerEvent]                     │
│ - _match(job, now)                              │  無変更
└──────────────────────┬───────────────────────┘
                        │ 委譲（select_candidates のみ。
                        │ _build_retry_events() 経由）
                        ▼
              ┌───────────────────────────┐
              │     RetrySchedulerDecision     │  （v3.5.0、無改修）
              │───────────────────────────│
              │ + select_candidates(limit=None) │
              │ + select_next_candidate()       │
              └───────────────────────────┘
```

`_build_retry_events()`は`SchedulerEngine`の内部実装（private）であり、
`select_candidates()`という既存の公開委譲メソッドを経由して
`RetrySchedulerDecision`にアクセスする。`self._retry_decision`を
直接参照する新たな経路は追加しない。

---

## 7. Sequence Diagram

### 7.1 evaluate()（retry_decisionが注入されている場合）

```
Caller       SchedulerEngine              RetrySchedulerDecision   RetrySchedulerSource
  │  engine.evaluate(jobs, now, retry_limit=2)                                          │
  ├───────────────►│                                                                    │
  │                 │  for job in jobs: ... （既存のJob判定ループ、無変更）              │
  │                 │  → events = [SchedulerEvent(job_id=..., ...), ...]                │
  │                 │                                                                    │
  │                 │  self._build_retry_events(now, 2)                                 │
  │                 │      self.select_candidates(limit=2)                              │
  │                 │      ├────────────────────►│                                     │
  │                 │      │                      │  list_pending_retries(limit=2)      │
  │                 │      │                      ├─────────────────────────────►│      │
  │                 │      │                      │◄─────────────────────────────┤      │
  │                 │      │◄─────────────────────┤  list（先頭2件）                    │
  │                 │  → [SchedulerEvent(job_id="retry:run-001", ...),                  │
  │                 │      SchedulerEvent(job_id="retry:run-002", ...)]                 │
  │                 │                                                                    │
  │                 │  events.extend(...)                                               │
  │◄────────────────┤  events（Job由来 ＋ Retry候補由来）                                │
```

### 7.2 evaluate()（retry_decisionが省略された場合。既存動作との一致確認）

```
Caller       SchedulerEngine
  │  engine = SchedulerEngine()  # retry_decision省略 → self._retry_decision = None
  │
  │  engine.evaluate(jobs, now)                                │
  ├───────────────►│                                          │
  │                 │  for job in jobs: ... （既存のJob判定ループ、無変更）│
  │                 │  → events = [SchedulerEvent(job_id=..., ...), ...] │
  │                 │                                          │
  │                 │  self._build_retry_events(now, None)     │
  │                 │      self.select_candidates(limit=None)  │
  │                 │      self._retry_decision is None → []   │  v3.6.0のガード節
  │                 │  → []                                    │
  │                 │                                          │
  │                 │  events.extend([])  # 実質何も追加しない  │
  │◄────────────────┤  events（Job由来のみ。v3.6.0と完全に同一） │
```

`retry_decision`省略時、`_build_retry_events()`は空リストを返し
`events.extend([])`は何も行わない。したがって`evaluate()`の出力は
v3.6.0時点とバイト単位で同一になる（`SchedulerEvent`インスタンスの生成順序・
内容を含め、Job判定ループの結果のみがそのまま返る）。

### 7.3 run_due()

```
Caller       SchedulerEngine
  │  engine.run_due(jobs, retry_limit=5)                       │
  ├───────────────►│                                          │
  │                 │  self.evaluate(jobs, now=self._clock.now(), retry_limit=5) │
  │                 ├───────────────►│（7.1と同じ流れ）         │
  │                 │◄───────────────┤                         │
  │◄────────────────┤  events                                  │
```

`run_due()`自体のロジックは「`self._clock.now()`を取得して`evaluate()`へ
委譲する」という既存の1行のみで、`retry_limit`をそのまま中継するだけである。

---

## 8. Data Flow

```
① 呼び出し元（Composition Root）が SchedulerEngine を構築する
   （retry_decision を渡すか省略するかで、Retry候補反映の有無が決まる。
   v3.6.0までと同じ「DIの有無＝機能の有効/無効」という設計言語を維持する）
        ↓
② engine.evaluate(jobs, now, retry_limit=N) または engine.run_due(jobs, retry_limit=N)
   を呼び出す
        ↓
③ Job判定ループ（既存、無変更）が jobs から SchedulerEvent を生成する
        ↓
④ _build_retry_events(now, retry_limit) が self.select_candidates(limit=retry_limit)
   （v3.6.0）へ委譲する
   ④-a retry_decision が None の場合：select_candidates() は [] を返す
        （v3.6.0のガード節。本Releaseで新たな分岐を追加しない）
   ④-b retry_decision が RetrySchedulerDecision 実体の場合：
        RetrySchedulerDecision → RetrySchedulerSource → RetryQueueManager.list()
        という既存の読み取り専用チェーン（v3.3.0〜v3.6.0）を経由して
        候補一覧を取得する
        ↓
⑤ ④の各候補について、job_id="retry:{run_id}"・execute_time=now・
   trigger_reason=REASON_RETRY_CANDIDATE_SELECTED・
   metadata={"retry_candidate": 候補オブジェクト} という SchedulerEvent を生成する
   （候補オブジェクトの他の属性は一切分解・解釈しない）
        ↓
⑥ ③の結果 ＋ ⑤の結果を連結したリストを evaluate() の戻り値として返す
        ↓
⑦ ⑥で生成された SchedulerEvent（Retry候補由来分を含む）を使って何かを
   判断・実行する処理は、本Releaseでは一切存在しない
   （読み取れる＝観測可能になっただけ。11章）
```

`retry_queue`パッケージへのimportは④・⑤のいずれの段階でも発生しない。
候補オブジェクトの型（`RetryQueueItem`）は`RetrySchedulerSource`
（v3.3.0、`retry_queue`をimportする唯一のパッケージ）の内部でのみ認識され、
`scheduler`はその値を透過的に運ぶだけである（9.1節で詳述）。

---

## 9. Boundary（今回入れない境界線）

本Releaseが**構造的に**実行不可能にする操作、および境界維持の方法を明示する。

### 9.1 `scheduler` が `retry_queue` を直接importしない境界

| 確認観点 | 本Releaseでの扱い |
|---|---|
| `scheduler_engine.py`に`from retry_queue import ...`が存在するか | 存在しない（importは`retry_scheduler_decision` / `retry_scheduler_source`の2つのみ、v3.4.0・v3.6.0から変更なし） |
| `RetryQueueItem`を型ヒントとして使用するか | 使用しない。`_build_retry_events()`の戻り値型は`list[SchedulerEvent]`のみで、候補オブジェクトの型注釈は一切登場しない（`select_candidates()`のv3.6.0からの既存方針を継続） |
| 候補オブジェクトの属性（`workflow_name` / `priority` / `retry_attempt` / `status`）を`scheduler_engine.py`内で参照するか | 参照しない。唯一参照する属性は`run_id`（`job_id`生成のためだけに使用）。他の属性は候補オブジェクトを`metadata["retry_candidate"]`にそのまま格納することで、分解・解釈を`scheduler`側に一切持ち込まない |
| `run_id`属性への依存はどう扱うか | `RetryQueueItem`はv3.1.0から`run_id`フィールドを持ち、`RetrySchedulerSource` / `RetrySchedulerDecision`を経由して変更なく透過している。`scheduler`はこの1属性についてのみ「候補オブジェクトは`run_id`という属性を持つ」という**構造的な期待（Duck Typing）**を持つが、これは`import`ではなく**属性アクセスの契約**であり、v3.4.0・v3.5.0のdocstringが明示してきた「型ヒントとしてはimportしない」という既存方針の延長線上にある |

この設計により、`scheduler`が`retry_queue`の型を直接知る必要があるのは
「候補オブジェクトが`run_id`という属性を持つ」という1点のみに限定され、
`import`文としての依存は本Release後も追加されない。

### 9.2 その他の境界

| 操作 | 本Releaseでの扱い | 根拠 |
|---|---|---|
| `RetryQueueManager.dequeue()` | 呼び出し不可 | `_build_retry_events()`が呼び出すのは`self.select_candidates()`（`RetrySchedulerDecision.select_candidates()`への委譲）のみ。`dequeue()`に相当するメソッドはこの経路のどこにも存在しない |
| `RetryQueueManager.remove()` | 呼び出し不可 | 同上 |
| Retry Engine（`RetryManager.retry()`）の起動 | 呼び出し不可 | `scheduler_engine.py`は`retry_engine`パッケージを一切importしない。生成された`SchedulerEvent`を消費して何かを実行するコードは本Releaseに一切存在しない |
| Retry Queueへの書き込み（`enqueue`含む） | 呼び出し不可 | `_build_retry_events()`から到達できるのは`select_candidates()`という読み取り専用メソッド1つのみ |
| Retry Queue・判定結果の永続化 | 対象外 | `SchedulerEngine`はRetry候補由来の`SchedulerEvent`を保持しない（Stateless。呼び出しのたびに`select_candidates()`で再取得する） |
| `retry_decision=None`時の出力差分 | 発生しない | 7.2節のSequence Diagramのとおり、`_build_retry_events()`は空リストを返し`events.extend([])`は無効果。Job判定ループは1行も変更していない |

Acceptance Criteria（Charter 9章）の「構造的確認」は、上記の表と1対1で
対応する形でテストする（`src/scheduler/`配下に`dequeue` / `remove` /
`RetryManager` / `from retry_queue`という文字列が存在しないことをテストで
確認する）。

---

## 10. Configuration

**本Releaseでは新規の環境変数を一切追加しない**（Charter 5章・8章）。

| 環境変数 | デフォルト | 説明 | 本Releaseでの役割 |
|---|---|---|---|
| `SCHEDULER_ENABLED` | `false` | Scheduler全体の有効/無効（`SchedulerConfig`、無改修） | 本Releaseの変更対象外 |
| `RETRY_QUEUE_ENABLED` | `true` | Retry Queueの有効/無効（`RetryQueueConfig`、無改修） | Composition Rootが`RetrySchedulerSource` / `NullRetrySchedulerSource`のどちらを構築するかの判断に再利用する（v3.4.0のまま） |

`retry_limit`は環境変数ではなく、`evaluate()` / `run_due()`呼び出し時の
オプション引数として呼び出し側が都度指定する（Charter 8章 Open Question 5への
回答。13章 Design Decision #4）。

---

## 11. Future Extension

* **生成された`SchedulerEvent`（Retry候補由来）を消費する仕組み**：
  Retry Engine起動・Workflow Engine起動等、実際に候補を処理する統合
  （Charter Non-Goals・本設計書9.2節で明示的に対象外とした領域）
* **自動Retry実行**：`select_next_candidate()` / `select_candidates()`で
  選ばれた候補を`RetryQueueManager.dequeue()`で実際に取り出し
  `RetryManager.retry()`へ渡す一連の自動化（v3.5.0・v3.6.0から持ち越し）
* **`job_id`プレフィックス衝突の構造的な防止**：本Releaseでは`"retry:"`
  プレフィックスを慣習として採用するのみで、`SchedulerJob.job_id`が
  同じプレフィックスを持つ場合の衝突を構造的に防止する仕組み（Validation等）は
  導入しない。実運用で問題になった場合、`SchedulerJob.job_id`側にも
  予約プレフィックス制約を設けるか再検討する（13章 Design Decision #2）
* **`metadata["retry_candidate"]`の型安全な公開**：現状は候補オブジェクトを
  そのまま格納するのみで、呼び出し元が安全に扱うための公開型・変換関数は
  用意しない。将来的にこの`SchedulerEvent`を消費する側が現れた時点で、
  必要に応じて`retry_queue`側に変換ヘルパーを追加するか検討する
* **実運用のComposition Root**：`scripts/run_scheduler.py`等の起動スクリプトは
  引き続き未着手（v3.4.0から持ち越し）

---

## 12. Compatibility

* `evaluate()` / `run_due()`へのオプション引数（`retry_limit`）追加のみ。
  既存の`evaluate(jobs, now)` / `run_due(jobs)`という呼び出しは、
  `retry_decision`が`None`の場合、本Release前とまったく同じ`SchedulerEvent`列を
  返す（7.2節で確認）
* Job判定ロジック（`_match()` / `_match_daily()` / `_match_interval()` /
  `_match_once()`）は1行も変更しない
* `count_pending_retries()` / `list_pending_retries()` / `select_candidates()` /
  `select_next_candidate()`は無変更
* `SchedulerManager` / `SchedulerRepository` / `SchedulerJob` /
  `SchedulerEvent` / `SchedulerConfig` / `exceptions.py`は無改修
* `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` /
  `retry_engine`配下の全ファイルも無改修
* 新規の環境変数を追加しないため、`.env` / `.env.example`の変更も不要
* **既知の差分**：`evaluate()` / `run_due()`のシグネチャ自体が変更される
  （`retry_limit`引数の追加）ため、シグネチャを厳密に検証する既存
  Architecture Guard（もし存在すれば）はv3.4.0の`[KI-4]`・v3.6.0の`[KI-5]`と
  同型の「本Releaseによる意図的な変更」としてFAILしうる。これは
  Charter 8章 Open Question 7への回答であり、Test工程でCHANGELOG.mdへ
  記録する（13章 Design Decision #5）
* `retry_decision`が`None`の場合の既存回帰テスト（`tests/test_e2e_v2_6_0_*`
  118件・`tests/test_e2e_v3_4_0_*`94件・`tests/test_e2e_v3_6_0_*`104件）は
  無変更のまま全PASSする想定（`SchedulerEvent`の出力内容が変わらないため）

---

## 13. Design Decisions（設計判断の根拠）

### Design Decision #1：`evaluate()` / `run_due()`への統合はAdditive方式とする

Charter 8章 Open Question 1に対し、次の理由からAdditive方式
（既存Job判定ループの結果に、Retry候補由来の`SchedulerEvent`を追加で連結する）を
採用する。

* ユーザー指示の目的候補「`SchedulerEngine`の`evaluate()` / `run_due()`と
  `RetrySchedulerDecision`の統合設計」「Retry候補を`SchedulerEvent`に反映する」は、
  `evaluate()` / `run_due()`自体の出力にRetry候補を含めることを明確に求めている。
  独立した新規メソッド（例：`evaluate_with_retries()`）に切り出す案は、
  「`evaluate()` / `run_due()`と統合する」というユーザー指示の趣旨に反する
* Additive方式であれば、Job判定ループのコードを1文字も変更せずに済み、
  「Retry候補の追加」と「Job判定ロジックの変更」を明確に分離できる
  （`events.extend(self._build_retry_events(...))`という1行のみの追加）
* `retry_decision`が`None`の場合、`_build_retry_events()`は既存の
  `select_candidates()`（v3.6.0のガード節）により空リストを返すため、
  Additive方式でも完全な後方互換性が成立する（7.2節で確認）

### Design Decision #2：`job_id`は`"retry:{run_id}"`という予約プレフィックス文字列とする

Charter 8章 Open Question 3（`RetryQueueItem`に`job_id`相当フィールドがない問題）に
対し、候補オブジェクトが持つ`run_id`属性に`"retry:"`という予約プレフィックスを
付けた文字列を`job_id`として採用する。

* `run_id`は`RetryQueueItem`がv3.1.0から一貫して持つ公開フィールドであり、
  `RetrySchedulerSource` → `RetrySchedulerDecision` → `SchedulerEngine`という
  読み取り専用チェーンを通じて改変されずに透過している。候補を一意に識別する
  情報として最も自然な選択である
* `"retry:"`プレフィックスにより、Job由来の`SchedulerEvent.job_id`
  （`SchedulerJob.job_id`はユーザー・設定側が任意に定義する文字列）との
  衝突を慣習レベルで避ける。ただし本Releaseはこれを構造的に強制しない
  （`SchedulerJob.job_id`に`"retry:"`から始まる値を設定することを妨げる
  Validationは追加しない）。Foundation Releaseとしてのスコープを踏まえ、
  この点は11章 Future Extensionに記載し、実運用上の問題が顕在化した時点で
  再検討する
* `run_id`以外の属性（`workflow_name`等）を`job_id`生成に混ぜない。
  `job_id`は「識別子」という単一の役割に限定し、他の情報は
  `metadata`側に委ねる（Design Decision #3）

### Design Decision #3：候補オブジェクトは分解せず`metadata`にそのまま格納する

Charter 8章 Open Question 4（`metadata`の組み立て方）に対し、候補オブジェクトの
属性を個別に取り出して`metadata`辞書のキーに展開する方式ではなく、
候補オブジェクトそのものを`metadata["retry_candidate"]`という1つのキーに
格納する方式を採用する。

* v3.5.0・v3.6.0の`select_candidates()`は一貫して「戻り値をそのまま返す
  （並べ替え・加工はしない）」という設計哲学を貫いてきた
  （`docs/design/retry_scheduler_decision.md`参照）。本Releaseもこの哲学を
  踏襲し、候補オブジェクトの中身を`scheduler`側で解釈・変換しない
* 属性を個別展開する方式（例：`metadata={"run_id": ..., "workflow_name": ...,
  "priority": ..., "status": ...}`）を採ると、`scheduler_engine.py`が
  `RetryQueueItem`の全フィールド構成を知っている前提のコードになり、
  `retry_queue`側でフィールドが追加・変更された場合に`scheduler`側の
  追随が必要になる（9.1節が目指す「`run_id`という1属性のみへの依存」という
  最小結合から逸脱する）
* 候補オブジェクトをそのまま格納する方式であれば、`scheduler`は
  `run_id`以外のいかなる属性についても構造的な期待を持たずに済み、
  `retry_queue`側の内部変更に対して`scheduler`側が影響を受けにくくなる
  （Future Extensionで型安全な公開ヘルパーが必要になった場合も、
  `retry_scheduler_decision`側に追加すればよく、`scheduler`側の変更は不要）

`scheduler_event.py`（`SchedulerEvent`データクラス自体）を変更しない
（Charter 11章で「見直す可能性あり」としていた点）のは、この設計により
新しいフィールドを追加する必要がなくなったためである（既存の
`metadata: dict`フィールドだけで表現が完結する）。

> **Minor Recommendation（ユーザー承認時に追記）**：`metadata["retry_candidate"]`は
> **本Release（v3.7.0）ではin-memoryの観測用途に限定する**。具体的には、
> 次の3点をNon-Goalsとして明示する。
>
> * **永続化しない**：`metadata["retry_candidate"]`を含む`SchedulerEvent`を
>   ファイル・DB等へ保存する処理は本Releaseに存在しない（Charter・本設計書
>   全体を通じて「永続化は対象外」という方針と一致する）
> * **JSON serializationの契約としない**：`metadata["retry_candidate"]`の値は
>   `RetryQueueItem`インスタンスそのもの（`datetime`型の`enqueue_time`・
>   `RetryQueueStatus`Enum型の`status`を含む）であり、標準の`json.dumps()`では
>   そのままシリアライズできない。本Releaseはこれを是正する変換ロジック
>   （`__dict__`化・Enum文字列化等）を一切追加しない。したがって、この`metadata`を
>   将来HTTPレスポンス・ログファイル・メッセージキュー等の外部I/Oに渡す場合、
>   呼び出し側が独自に変換処理を用意する必要がある
> * **外部I/O契約としない**：`metadata["retry_candidate"]`のキー名・値の型は、
>   将来Release（Retry Engine等がこのイベントを消費する段階）で見直される
>   可能性がある「暫定的な内部表現」であり、本Releaseの時点で外部API・
>   外部プロセス間の安定した契約として扱わない
>
> この限定は11章 Future Extension「`metadata["retry_candidate"]`の型安全な
> 公開」の前提条件でもある。将来、永続化・外部公開が必要になった時点で、
> 変換責務をどこに置くか（`scheduler`側か`retry_queue`側か）を改めて設計する。

### Design Decision #4：`retry_limit`は呼び出し側が都度指定するオプション引数とする

Charter 8章 Open Question 5（件数の扱い）に対し、`evaluate()` / `run_due()`に
`retry_limit: int | None = None`という引数を追加し、呼び出し側が都度
指定できるようにする。

* 固定値をハードコードすると、呼び出し元の事情（Scheduler実行間隔・
  Job数とのバランス等）に対応できない
* `select_candidates(limit=None)`が既に「無制限（全件）」を意味する
  v3.6.0の既存仕様であるため、`retry_limit=None`をデフォルトとすることで、
  「明示的に指定しない限り全件反映する」という単純な既定動作になる。
  新しいConfigクラス・環境変数を追加しない（Charter Non-Goals）という
  制約とも整合する

### Design Decision #5：`retry_decision=None`時の完全互換性の保証方法

Charter 8章 Open Question 7（過去のAcceptance Criteriaとの関係）に対し、
次の2点で構造的に保証する。

* コード構造：Job判定ループ（既存コード、1行も変更しない）と
  `_build_retry_events()`（新設、`select_candidates()`への委譲のみ）を
  完全に分離し、後者は`retry_decision=None`の場合に空リストを返すことが
  v3.6.0のガード節により保証されている。本Releaseはこのガード節を
  再利用するのみで、新たな条件分岐を`evaluate()`に追加しない
* テスト：`retry_decision`を渡さずに構築した`SchedulerEngine`に対する
  `evaluate()` / `run_due()`の全既存回帰テスト（v2.6.0・v3.4.0・v3.6.0）を
  無改修のまま実行し、全PASSすることを確認する。加えて、本Release新規の
  E2Eテストで「`retry_decision=None`のとき出力が空のRetry候補由来Eventを
  一切含まない」ことを明示的に確認する

一方で、シグネチャ自体（`retry_limit`引数の追加）は変更されるため、
「シグネチャが完全に無変更であること」を検証する種類のArchitecture Guardが
仮に存在する場合はFAILしうる。これは意図的な変更であり、12章で述べたとおり
既知の差分としてCHANGELOG.mdに記録する。

---

## 14. Charter Open Questions への回答

Charter（`docs/design/retry_scheduler_event_integration_charter.md`）8章で
保留した7項目に対する結論。

1. **組み込み方式**：Additive方式。既存Job判定ループの結果に、
   Retry候補由来の`SchedulerEvent`を`_build_retry_events()`経由で追加連結する
   （13章 Design Decision #1）
2. **呼び出し条件**：追加の引数（`include_retries`等）は設けない。
   `retry_decision`が注入されている場合は常に反映し、`None`の場合は
   既存の`select_candidates()`ガード節により常に空になる（DIの有無＝
   機能の有効/無効という既存の設計言語をそのまま踏襲）
3. **`job_id`相当フィールド**：候補オブジェクトの`run_id`属性に`"retry:"`
   プレフィックスを付けた文字列とする（13章 Design Decision #2）
4. **`metadata`の組み立て方**：候補オブジェクトを分解せず、
   `metadata["retry_candidate"]`にそのまま格納する（13章 Design Decision #3）
5. **件数の扱い**：`evaluate()` / `run_due()`に`retry_limit: int | None = None`
   引数を追加し、内部で`self.select_candidates(limit=retry_limit)`
   （複数件、v3.6.0の既存メソッド）を呼び出す。`select_next_candidate()`
   （1件のみ）は本統合には使用しない（13章 Design Decision #4）
6. **`trigger_reason`の命名**：`REASON_RETRY_CANDIDATE_SELECTED`とする。
   既存の`REASON_*_MATCHED`（スケジュール一致）とは意味論が異なる
   （「選択された」であって「一致した」ではない）ため、あえて`_SELECTED`
   という異なる語尾を採用する
7. **過去のAcceptance Criteriaとの関係**：「`retry_decision`が`None`の場合に
   限り、出力がv3.6.0と完全に同一」という条件付きの文言にCharter
   Acceptance Criteriaを改めており、本設計書はこれをコード構造
   （Job判定ループとRetry候補反映ループの分離）とテスト（既存回帰＋
   新規E2E）の両面で保証する（13章 Design Decision #5）

---

## 15. Architecture Review

状態：**Approve with Minor Recommendations**（Claude Codeによる自己点検。
指摘事項は2件、いずれも本Releaseの実装をブロックしない）。

### 15.1 レビュー観点別の判定

| # | 観点 | 判定 | 根拠 |
|---|---|---|---|
| 1 | `retry_decision=None`時に`evaluate()` / `run_due()`が完全互換か | **互換** | 7.2節のSequence Diagramのとおり、`_build_retry_events()`は空リストを返し`events.extend([])`は無効果。Job判定ループは1行も変更していない |
| 2 | Retry Engineの起動が構造的に不可能か | **不可能** | `scheduler_engine.py`は`retry_engine`を一切importしない。`_build_retry_events()`は`select_candidates()`への委譲のみ（4章） |
| 3 | `dequeue()` / `remove()`の呼び出しが構造的に不可能か | **不可能** | `_build_retry_events()`から到達できる経路は`select_candidates()`（読み取り専用）のみ。9.2節で確認 |
| 4 | Queue更新・永続化が発生しないか | **発生しない** | `SchedulerEngine`はRetry候補由来の`SchedulerEvent`を保持せず、書き込み系メソッドへの参照も持たない |
| 5 | `SchedulerEngine`がRetry候補を`SchedulerEvent`として観測可能にできているか | **できている** | 7.1節のSequence Diagramのとおり、`evaluate()` / `run_due()`の戻り値にRetry候補由来の`SchedulerEvent`が含まれる |
| 6 | `job_id`欠如問題への対処が妥当か | **妥当（構造的強制はなし、Future Extensionへ明記）** | `run_id`ベースの予約プレフィックス方式は最小の依存で識別子を提供する。衝突防止の構造的強制がない点は11章・13章 Design Decision #2で明示済みのトレードオフ |
| 7 | `scheduler`が`retry_queue`を直接importしない境界が維持されているか | **維持されている** | 4章のimport文に`retry_queue`は登場しない。9.1節で唯一の属性依存（`run_id`）を明示し、他の属性は分解せず不透過に運ぶ設計とした |
| 8 | Foundation First / SRP / Stateless / Backward Compatibilityが守られているか | **概ね守られている（SRPは評価コメントあり）** | Foundation First：観測可能にするのみで実行系は一切追加していない。Stateless：候補をキャッシュしない。Backward Compatibility：12章・Design Decision #5で確認済み。SRPについては15.3節で述べる |
| 9 | `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_engine`が無改修か | **無改修** | 3章Package Structureのとおり、`scheduler`配下1ファイル（`scheduler_engine.py`）の変更のみ |
| 10 | 既存Regressionへの影響がないか | **影響なし（シグネチャ変更に伴う既知差分を除く）** | `retry_limit`はデフォルト値付きの末尾追加引数であり、既存の呼び出し（位置引数・キーワード引数）は本Release前と同じ結果を得る。ただしシグネチャ自体の変更はv3.4.0`[KI-4]`・v3.6.0`[KI-5]`と同型の既知差分となりうる（12章） |

### 15.2 SOLID

* **単一責任（SRP）**：`evaluate()`は「Job判定」と「Retry候補の`SchedulerEvent`化」
  という2つの関心事を持つことになるが、後者を`_build_retry_events()`という
  独立したprivateメソッドに切り出しており、`evaluate()`本体は「2つの結果を
  連結する」という調整役に留めている。ただし、これはv3.4.0・v3.6.0までの
  「`evaluate()` / `run_due()`は完全に無関与」という一貫した不変条件からの
  意図的な逸脱であり、`SchedulerEngine`自体が担う関心事は本Releaseで
  明確に増える（15.3節で評価する）
* **開放閉鎖（OCP）**：既存のJob判定ロジック（`_match*`系）に変更を加えず、
  `evaluate()`の末尾に追加ブロックを設けることで拡張している
* **リスコフの置換（LSP）**：本Releaseで新たな型の置換可能性は発生しない
  （`retry_decision`は既存の`RetrySchedulerDecision | None`のまま）
* **インターフェース分離（ISP）**：`_build_retry_events()`が利用するのは
  `self.select_candidates()`という単一の既存メソッドのみ
* **依存性逆転（DIP）**：v3.4.0・v3.6.0から変更なし。具象クラス
  （`RetrySchedulerDecision`）への依存を維持する既存方針をそのまま踏襲する

### 15.3 残された懸念（Minor Recommendations）

1. **`evaluate()` / `run_due()`が「無改修」という不変条件を初めて手放すこと**：
   v3.4.0・v3.6.0のArchitecture Reviewはいずれも「判定サイクルへの不介入」を
   最大の安全性の根拠としてきた。本Releaseはこの前提を初めて崩すため、
   `_build_retry_events()`という分離されたメソッドで影響範囲を局所化しては
   いるものの、次Release（自動Retry実行等）でさらに`evaluate()`への変更が
   重なった場合、判定ロジックの複雑化が進むリスクがある。次Release検討時に
   「`evaluate()`が担う関心事がこれ以上増える場合は、Retry候補の`SchedulerEvent`化を
   専用クラス（例：`RetrySchedulerEventBuilder`）に切り出すか」を再検討することを
   推奨する
2. **`job_id`の`"retry:"`プレフィックス衝突が構造的に防止されていないこと**：
   Design Decision #2で述べたとおり、`SchedulerJob.job_id`が偶然
   `"retry:"`から始まる値を持つ場合、Job由来のイベントとRetry候補由来の
   イベントが`job_id`のみでは区別できなくなる。本Releaseでは実害が低い
   （既存の`SchedulerJob`設定例・テストデータのいずれも該当しない）として
   許容するが、実運用データでこの前提が崩れた場合に備え、11章 Future
   Extensionに記載した「予約プレフィックスの構造的な検証」を次Release以降で
   検討することを推奨する

いずれも実装を妨げる指摘ではなく、次Release以降で状況に応じて対応を
検討する事項として整理する。

### 15.4 Foundation First・プロジェクト全体との設計整合性

Charter・ユーザー指示が要求した「Retry候補を`SchedulerEvent`に反映するが、
Retry Engineは起動しない・`dequeue()` / `remove()`は使用しない・Queue更新や
永続化は行わない」という範囲に対し、本設計は生成された`SchedulerEvent`を
消費する処理を一切追加しておらず、スコープの逸脱はない。
v3.3.0〜v3.6.0と同じ「Foundation First・消費者不在の実行ロジックなし」という
パターンを維持しつつ、`evaluate()` / `run_due()`自体への統合という
ユーザー指示の核心部分のみを新たに実現している。

### 15.5 依存方向

```
src/scheduler/ ── import ──→ retry_scheduler_decision（公開APIのみ：RetrySchedulerDecision）
src/scheduler/ ── import ──→ retry_scheduler_source（公開APIのみ：
                              RetrySchedulerSource / NullRetrySchedulerSource）
retry_scheduler_decision ── import ──→ retry_scheduler_source（v3.5.0のまま、無改修）
retry_scheduler_source   ── import ──→ retry_queue（v3.3.0のまま、無改修）
```

`scheduler`は`retry_queue`・`retry_engine`のいずれも直接importしない
（v3.4.0〜v3.6.0から変更なし。9.1節で詳述）。`retry_scheduler_decision`は
本Releaseでも`scheduler`を一切importしない（逆方向依存なし）。循環importの
余地は構造的に存在しない。

### 15.6 後方互換性

12章で述べたとおり、変更は`evaluate()` / `run_due()`へのオプション引数
（`retry_limit`）追加と、既存メソッドに影響しないprivateメソッド1つの追加のみ。
`retry_decision`が`None`の場合、Job判定ロジック（`_match*`系）・
`count_pending_retries()` / `list_pending_retries()` / `select_candidates()` /
`select_next_candidate()`はいずれも無変更であり、`SchedulerManager` /
`SchedulerRepository` / `SchedulerJob` / `SchedulerEvent` / `SchedulerConfig` /
`exceptions.py`もゼロ改修。既存呼び出し元への影響はないと判断する
（シグネチャ変更自体に伴う既知差分は12章参照）。

### 15.7 総評

Charter・ユーザー指示が要求した重点項目（`retry_decision=None`時の完全互換・
Retry Engine不起動・`dequeue()`/`remove()`不使用・Queue更新/永続化なし・
Retry候補の`SchedulerEvent`化・`job_id`欠如問題への対処・`retry_queue`直接import
禁止の維持・Foundation First/SRP/Stateless/Backward Compatibilityの遵守）は
いずれも設計上満たされている。Minor Recommendations 2件（15.3節）は
いずれも実装をブロックする性質のものではなく、次Release以降の検討事項として
記録すれば足りる。

**Approve with Minor Recommendations** と判断する。

---

## 16. Status

- [x] Architecture Design ドラフト作成（本文書、Claude Code作成）
- [x] Architecture Review完了（Claude Codeによる自己点検、Approve with Minor
      Recommendations。指摘事項2件は次Release検討事項として記録済み）
- [x] ユーザー確認・実装可否判断（承認済み。Minor Recommendation追記
      （13章 Design Decision #3補足）を反映のうえ実装へ進行）
- [x] 実装完了：`src/scheduler/scheduler_engine.py` / `src/scheduler/__init__.py`
      （4章の設計どおり。`_build_retry_events()`・`REASON_RETRY_CANDIDATE_SELECTED`・
      `evaluate()` / `run_due()`への`retry_limit`引数追加。設計からの逸脱なし）
- [x] テスト完了：`tests/test_e2e_v3_7_0_retry_scheduler_event_integration.py`
      74/74 PASS。既存回帰：`v2.6.0`（118/118）・`v3.4.0`（94/94）・`v1.20.0`（170/170）
      全PASS。`v3.6.0`は102/104 PASSで、2件FAILは`docs/CHANGELOG.md` `[KI-6]`
      （本Releaseによる意図的な変更。12章・13章 Design Decision #5で事前に
      想定済みの既知差分）

### 16.1 実装後の補足

* 4章で示したコード設計と、実装後の`scheduler_engine.py`の間に差分はない
  （`_build_retry_events()`のシグネチャ・`job_id`生成方式・`metadata`の
  格納方式はいずれも設計どおり）
* 15.1節「観点9」で想定していた「シグネチャ変更に伴う既知差分」は、
  実際には`tests/test_e2e_v3_6_0_retry_scheduler_decision_wiring.py`の
  テスト16・17（「`retry_decision`有無で結果完全一致」）としてFAILする形で
  顕在化した。これは`evaluate()`のシグネチャそのものではなく出力内容の差分だが、
  性質としては同じ「意図的な既知差分」であり、`docs/CHANGELOG.md` `[KI-6]`として
  記録した
* `metadata["retry_candidate"]`のin-memory観測用途限定（Minor Recommendation、
  13章 Design Decision #3補足）は、コード側では`_build_retry_events()`の
  docstringに明記した。永続化・JSON serialization・外部I/O契約を行う
  変換ロジックは実装していない（設計どおり）
