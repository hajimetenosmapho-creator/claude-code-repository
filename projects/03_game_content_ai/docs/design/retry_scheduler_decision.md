# v3.5.0 Retry Scheduler Decision 設計書（Architecture Design）

作成日：2026-07-03
状態：ドラフト（ChatGPTレビュー待ち）。`docs/design/retry_scheduler_decision_charter.md`
（Project Charter、ユーザー承認済み、2026-07-03）を前提とする。

---

## 1. Architecture Overview

Release 3.4（`docs/design/retry_scheduler_wiring.md`）までで、以下の基盤が整備された。

* Retry Scheduler Integration（v3.3.0）：`RetrySchedulerSource` /
  `NullRetrySchedulerSource` が `RetryQueueManager` の読み取り専用API
  （`list()` / `count()`）を `list_pending_retries()` / `count_pending_retries()`
  として中継するAdapter
* Retry Scheduler Wiring（v3.4.0）：`SchedulerEngine` が `RetrySchedulerSource` /
  `NullRetrySchedulerSource` をConstructor Injectionで保持し、
  `count_pending_retries()` / `list_pending_retries()` への薄い委譲メソッドを持つ

本Release（v3.5.0）は、「読み取れる」状態の先にある「次に処理すべき候補を選ぶ」
という関心事を、新規独立コンポーネント `RetrySchedulerDecision` として切り出す。
`SchedulerEngine`（v3.4.0）には一切手を加えない（Charter 1章：v3.4.0 Architecture
Reviewで残した「3つ目の異種責務が入ったら責務分割を再検討する」という指摘への対応）。

```
Scheduler（判断、v2.6.0 / v3.4.0、無改修）
   │
   ├── RetrySchedulerSource（Adapter、v3.3.0、無改修）
   │        │
   │        └── Retry Queue（v3.1.0、無改修）
   │
   └── RetrySchedulerDecision（新規、v3.5.0） ★本Release
            │  ※本Releaseでは未接続。RetrySchedulerSourceを個別にDIで保持する
            │    独立コンポーネントとして先行実装する
            ▼
      RetrySchedulerSource（同上と同じインスタンスを想定するが、
                             SchedulerEngineとは独立した経路で保持される）
```

`RetrySchedulerDecision` は Retry Queue の**補助コンポーネント**として設計するが、
本Releaseのスコープは「選択ロジックの新設のみ」であり、`SchedulerEngine`との実際の
配線は行わない（Out of Scope・Charter 4章）。v3.3.0の`RetrySchedulerSource`と同じ
「消費者不在の先行実装」パターンである。

---

## 2. Design Policy

Project Charter の Design Principles（5章）を、本設計では以下の形で具体化する。

1. **Foundation First**：候補選択ロジックの新設のみを先に確立する。
   `SchedulerEngine`との実配線・選択結果を使った実行（自動Retry実行）はすべて
   後続Releaseへ送る（11章 Future Extension）
2. **Single Responsibility**：`RetrySchedulerDecision`は「並んでいる候補から選ぶ」
   責務のみを持つ。整列ロジック（`RetryQueueManager.list()`、無改修）・Adapterと
   しての中継（`RetrySchedulerSource`、無改修）・時刻ベースの判定
   （`SchedulerEngine`、無改修）のいずれも複製・肩代わりしない
3. **Stateless**：候補の状態を独自に保持・キャッシュしない。呼び出すたびに
   `RetrySchedulerSource`経由で最新状態を取得し、その場で選択する
4. **Constructor Injection のみ**：`retry_source`を必須のコンストラクタ引数として
   受け取る。セッター・ファクトリメソッド（`from_config()`等）は持たない
5. **既存モジュール無改修**：`scheduler` / `retry_scheduler_source` /
   `retry_queue` / `retry_engine` のいずれも変更しない。
   `retry_scheduler_decision`は`retry_scheduler_source`の公開シンボルのみを
   importする独立パッケージとして設計する

---

## 3. Package Structure

```
src/retry_scheduler_decision/
├── __init__.py                    # 公開シンボルのexport（4章）
└── retry_scheduler_decision.py    # RetrySchedulerDecision
```

`RetrySchedulerSource` / `NullRetrySchedulerSource` が `retry_scheduler_source.py`
に同居している（v3.3.0）のと異なり、本Releaseでは**Null Object Patternを採用しない**
（2章 Design Decision #2で理由を述べる）ため、単一クラスのみの2ファイル構成となる。
既存パッケージ（`retry_scheduler_source`が2ファイル）と比べても最小構成である。

既存パッケージへの変更は一切行わない（ゼロ改修）。

---

## 4. Public API

### `retry_scheduler_decision.py`

```python
from __future__ import annotations

from retry_scheduler_source import NullRetrySchedulerSource, RetrySchedulerSource


class RetrySchedulerDecision:
    """
    RetrySchedulerSource（またはNullRetrySchedulerSource）が返す待機中の項目一覧から、
    「次に処理すべき候補」を選ぶだけの専用コンポーネント。

    RetrySchedulerSource.list_pending_retries()の既存順序（priority昇順・
    enqueue_time昇順）をそのまま活用し、独自の並べ替え・優先度計算は行わない。
    Queueへの書き込み（enqueue / dequeue / remove）は一切行わない。
    """

    def __init__(self, retry_source: "RetrySchedulerSource | NullRetrySchedulerSource"):
        self._retry_source = retry_source

    def select_candidates(self, limit: int | None = None) -> list:
        """
        RetrySchedulerSource.list_pending_retries(limit) への委譲。
        戻り値をそのまま返す（並べ替え・加工はしない）。

        戻り値の要素はRetryQueueItem（retry_queueパッケージの公開型）だが、
        retry_scheduler_decisionはretry_queueに直接依存しない方針のため
        型ヒントとしてはimportしない（13章 Design Decision #4）。
        """
        return self._retry_source.list_pending_retries(limit=limit)

    def select_next_candidate(self):
        """
        select_candidates(limit=1)の戻り値から先頭1件を返す便利メソッド。
        候補が存在しない場合はNoneを返す。
        """
        candidates = self.select_candidates(limit=1)
        return candidates[0] if candidates else None
```

* `retry_source`は**必須引数**（デフォルト値を持たない）とする。本コンポーネントの
  唯一の入力であり、`SchedulerEngine.__init__`の`retry_source`（デフォルト`None`→
  `NullRetrySchedulerSource()`フォールバック）とは異なる設計とする理由は
  13章 Design Decision #1で述べる
* `retry_source`の型は`RetrySchedulerSource | NullRetrySchedulerSource`の
  Union型とする（13章 Design Decision #2）
* `select_candidates()`は`list_pending_retries()`への1行委譲のみ。
  `select_next_candidate()`は`select_candidates(limit=1)`を呼び出す便利メソッド
  （`SchedulerEngine.run_due()`が`evaluate()`を呼び出す構造と同じ考え方）
* いずれのメソッドも`try/except`や加工を行わない
  （`RetrySchedulerSource`自体が例外を送出しない契約であるため）

### `__init__.py` の公開シンボル

```python
from .retry_scheduler_decision import RetrySchedulerDecision

__all__ = [
    "RetrySchedulerDecision",
]
```

---

## 5. Class Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryQueueManager`（v3.1.0、無改修） | Queueへの出し入れ・整列（`list()`は既にpriority昇順・enqueue_time昇順で返す） | 候補選択・実行判断 |
| `RetrySchedulerSource` / `NullRetrySchedulerSource`（v3.3.0、無改修） | Retry Queueの状態の読み取り専用な中継 | 候補選択ロジック・実行判断 |
| `RetrySchedulerDecision`（本Releaseで新設） | `RetrySchedulerSource`が返す既存順序から「次に処理すべき候補」を選ぶ（先頭1件、または指定件数） | 整列・並べ替えの再計算／Queueからの取り出し（`dequeue`）・削除（`remove`）／実行判断の確定／実行／有効・無効の自己判定（Feature Gate）／`SchedulerEngine`との接続 |
| `SchedulerEngine`（v3.4.0、無改修） | 時刻ベースの判定・pending retryの件数/一覧の読み取り委譲 | 候補選択（本Releaseでは関与しない） |

「候補として何件選ぶか」（`limit`の値）の決定は、本パッケージの責務ではなく
**呼び出し元の責務**とする（8章 Data Flowで詳述）。

---

## 6. Class Diagram

```
┌──────────────────────────────┐
│        RetrySchedulerDecision       │
│──────────────────────────────│
│ - _retry_source: RetrySchedulerSource │
│                | NullRetrySchedulerSource │
│──────────────────────────────│
│ + __init__(retry_source)              │
│ + select_candidates(limit=None) -> list │──┐
│ + select_next_candidate() -> item|None  │  │ 委譲
└──────────────────────────────┘  │
                                          ▼
                ┌─────────────────────────┐   ┌───────────────────────────┐
                │     RetrySchedulerSource    │   │   NullRetrySchedulerSource   │
                │  （v3.3.0、無改修）           │   │  （v3.3.0、無改修）             │
                └─────────────────────────┘   └───────────────────────────┘
```

`RetrySchedulerDecision`と`RetrySchedulerSource`の間に継承関係はない
（コンポジション。`_retry_source`フィールドとして保持するのみ）。
`RetrySchedulerDecision`自体には対になる`NullRetrySchedulerDecision`は存在しない
（13章 Design Decision #2）。

---

## 7. Sequence Diagram

### 7.1 select_candidates（有効な場合：RetrySchedulerSource）

```
Caller          RetrySchedulerDecision   RetrySchedulerSource   RetryQueueManager
  │  decision.select_candidates(limit=2)                                         │
  ├───────────────►│                                                             │
  │                 │  self._retry_source.list_pending_retries(limit=2)          │
  │                 ├────────────────────►│                                      │
  │                 │                      │  self._queue.list(limit=2)          │
  │                 │                      ├─────────────────────────────────────►│
  │                 │                      │                                      │  priority昇順・
  │                 │                      │                                      │  enqueue_time昇順で
  │                 │                      │                                      │  整列しコピーを返す
  │                 │                      │◄─────────────────────────────────────┤
  │                 │◄─────────────────────┤  list[RetryQueueItem]（先頭2件）       │
  │◄────────────────┤  list（そのまま。並べ替えなし）                                │
```

### 7.2 select_next_candidate（候補が存在する場合）

```
Caller          RetrySchedulerDecision
  │  decision.select_next_candidate()                        │
  ├───────────────►│                                          │
  │                 │  self.select_candidates(limit=1)         │
  │                 │   → RetrySchedulerSource.list_pending_retries(limit=1)
  │                 │                                          │
  │◄────────────────┤  candidates[0]（1件のみ返された場合）        │
```

### 7.3 select_candidates / select_next_candidate（無効な場合：NullRetrySchedulerSource）

```
Caller          RetrySchedulerDecision   NullRetrySchedulerSource
  │  decision = RetrySchedulerDecision(NullRetrySchedulerSource())    │
  │                                                                    │
  │  decision.select_candidates()                                     │
  ├───────────────►│                                                  │
  │                 │  self._retry_source.list_pending_retries()       │
  │                 ├────────────────────►│                            │
  │                 │◄─────────────────────┤  []（retry_queueへは一度も到達しない） │
  │◄────────────────┤  []                                              │
  │                                                                    │
  │  decision.select_next_candidate()                                 │
  ├───────────────►│                                                  │
  │                 │  self.select_candidates(limit=1) → []            │
  │◄────────────────┤  None                                            │
```

初版検討時に候補として挙がった`NullRetrySchedulerDecision`を作らずとも、
`NullRetrySchedulerSource`を注入するだけで「候補なし」という安全な結果が
自然に得られることが、この7.3節の流れで確認できる（13章 Design Decision #2）。

---

## 8. Data Flow

```
① 呼び出し元（Composition Root。本Releaseでは未定。将来的にはSchedulerEngineの
   実配線時、または独立したバッチ処理から利用されることを想定）が、
   RetrySchedulerSource（実体）とNullRetrySchedulerSourceのどちらを使うかを
   決定する（v3.3.0から一貫した判断。本パッケージはこの判定に一切関与しない）
        ↓
② 呼び出し元が RetrySchedulerDecision(retry_source) を構築する
   （retry_sourceは必須引数。省略不可）
        ↓
③ 呼び出し元が select_candidates(limit) / select_next_candidate() を呼ぶ
        ↓
④-a RetrySchedulerSource（実体）の場合：
     RetryQueueManager.list(limit) の結果（priority昇順・enqueue_time昇順）を
     そのまま返す
④-b NullRetrySchedulerSource の場合：
     即座に[] / Noneを返す（retry_queueへのアクセスは発生しない）
        ↓
⑤ 呼び出し元は④の戻り値をそのまま受け取る。選ばれた候補を実際にどう扱うか
  （Retry Engineへ渡す・ログに記録する等）は、本Releaseの範囲外
  （呼び出し元が存在しないため、本Release単体では④の先は発生しない）
```

「何件選ぶか（`limit`）」「選んだ結果をどう使うか」はいずれも呼び出し元の責務であり、
`RetrySchedulerDecision`自身は判断しない（5章）。

---

## 9. Configuration

**本Releaseでは新規の環境変数を一切追加しない**（Charter 5章・10章）。

`RetrySchedulerDecision`は環境変数を一切読まず、`is_ready()`のような判定メソッドも
持たない。「有効/無効」は、呼び出し元が`retry_source`にどちらのクラスを渡すかで
決まる（v3.3.0から一貫した設計）。

| 環境変数 | デフォルト | 本Releaseでの役割 |
|---|---|---|
| （なし） | — | `retry_scheduler_decision`パッケージは環境変数を一切読まない |

---

## 10. Boundary（今回入れない境界線）

本Releaseが**構造的に**実行不可能にする操作を明示する。

| 操作 | 本Releaseでの扱い | 根拠 |
|---|---|---|
| `RetryQueueManager.dequeue()` | 呼び出し不可 | `RetrySchedulerSource` / `NullRetrySchedulerSource`のいずれも`dequeue()`に相当するメソッドを公開していない（v3.3.0時点で非公開）。`RetrySchedulerDecision`が`RetryQueueManager`を直接保持することもない |
| `RetryQueueManager.remove()` | 呼び出し不可 | 同上 |
| Retry Engine（`RetryManager.retry()`）の起動 | 呼び出し不可 | `retry_scheduler_decision`は`retry_engine`パッケージを一切importしない（7章 Dependencies）。選択結果を使って何かを実行するコードは本Releaseに一切存在しない |
| Retry Queueへの書き込み（`enqueue`含む） | 呼び出し不可 | `RetrySchedulerDecision`から到達できるのは`RetrySchedulerSource`の`list_pending_retries()`のみ |
| `SchedulerEngine`の変更 | 発生しない | `retry_scheduler_decision`は`scheduler`を一切importせず、`scheduler`も本Releaseでは`retry_scheduler_decision`を一切importしない（相互に無関係） |
| 永続化 | 対象外 | `RetrySchedulerDecision`は候補の状態を保持しない（Stateless。2章） |

Acceptance Criteria（Charter 9章）の「構造的確認」は、上記の表と1対1で対応する形で
テストする。

---

## 11. Future Extension

* **`SchedulerEngine`との実配線**：`SchedulerEngine`（または他の呼び出し元）が
  `RetrySchedulerDecision`を保持し、`select_next_candidate()` /
  `select_candidates()`を実際に呼び出す統合。Constructor Injectionの受け口を
  `SchedulerEngine`に追加するか、別の呼び出し元（実運用スクリプト等）に委ねるかは
  次Release以降で検討する
* **選択結果を使った実行**：`select_next_candidate()`が返した候補を
  `RetryQueueManager.dequeue()`で実際に取り出し、`RetryManager.retry()`へ渡す
  一連の自動化（`docs/design/retry_scheduler_wiring.md` 11章から持ち越し）
* **選択ロジックの高度化**：現時点では`RetrySchedulerSource`が返す順序をそのまま
  使うだけだが、将来的に「同一`workflow_name`は除外する」「直近で選ばれた候補は
  スキップする」等のフィルタリングが必要になった場合、`RetrySchedulerDecision`に
  追加する（既存の`select_candidates()` / `select_next_candidate()`のシグネチャは
  変更せずに拡張できる想定）
* **Null Object Patternの再検討**：本Releaseでは不要と判断した
  （13章 Design Decision #2）が、将来`RetrySchedulerDecision`自身に固有の
  Feature Gateやコストのかかる初期化処理が追加される場合は、その時点で
  `NullRetrySchedulerDecision`の要否を再検討する

---

## 12. Compatibility

* 新規独立パッケージ`src/retry_scheduler_decision/`の追加のみであり、既存パッケージ
  （`scheduler` / `retry_scheduler_source` / `retry_queue` / `retry_engine` /
  `workflow_engine` / `workflow_monitor` / `execution_history` / `ai` /
  `pipeline`）への変更は一切ない（ゼロ改修）
* 既存の公開APIのシグネチャ・戻り値の意味は変更しない
* `src/retry_scheduler_decision/`はどのパッケージからもimportされない状態で
  リリースされる（1章）。v3.3.0の`RetrySchedulerSource`と同じ
  「消費者不在の先行実装」パターンであり、後方互換性上のリスクはない
* 新規の環境変数を追加しないため、`.env` / `.env.example`の変更も不要

---

## 13. Design Decisions（Charter Open Questionsへの回答）

### Design Decision #1：`retry_source`を必須引数とする（デフォルトを持たない）

Charter 8章 Open Question 1（Constructor Injectionの引数型）に対し、`retry_source`は
**デフォルト値を持たない必須引数**とする。

`SchedulerEngine.__init__`の`retry_source`（デフォルト`None`→
`NullRetrySchedulerSource()`フォールバック）とは異なる設計とする理由：

* `SchedulerEngine`にとってRetry Queue連携は**副次的な機能**（主機能は時刻ベースの
  判定）であり、省略時に安全な既定値へフォールバックする意味がある
* `RetrySchedulerDecision`にとって`retry_source`は**唯一の入力**であり、省略時の
  「安全な既定値」という概念自体が存在しない（何を選ぶための情報も渡されないまま
  構築することに意味がない）。呼び出し元に明示的な選択を促す方が設計として誠実である

### Design Decision #2：Null Object Patternは採用しない

Charter 8章 Open Question 2に対し、`NullRetrySchedulerDecision`は**作らない**と
結論する。

プロジェクト全体では「実装クラス／Nullクラス」のペアが一貫しているが、
以下の理由から本コンポーネントには適用しない。

* Null Object Patternは、これまで一貫して「呼び出し元が持つFeature Gate的な
  判定（`XxxConfig.is_ready()`等）の結果を、コンポーネントの型として表現する」
  ために使われてきた（`RetryQueueManager`/`NullRetryQueueManager`は
  `RETRY_QUEUE_ENABLED`を、`RetrySchedulerSource`/`NullRetrySchedulerSource`は
  呼び出し元の任意の判断を表現する）。`RetrySchedulerDecision`自体には
  対応する判定軸（Feature Gate・Config）が存在しない（Charter 10章で新規
  Feature Gate/Config追加を明示的に禁止している）
* 「無効化」の表現は、`retry_source`に`NullRetrySchedulerSource()`を渡すことで
  **既に完結している**。この場合`select_candidates()`は常に`[]`、
  `select_next_candidate()`は常に`None`を返す（7.3節）。
  `NullRetrySchedulerDecision`を追加しても、`RetrySchedulerDecision`が
  `NullRetrySchedulerSource`を保持している場合とまったく同じ戻り値になり、
  実質的に重複した表現になる
* Small Release / YAGNI：本Releaseは消費者不在の先行実装であり、将来の呼び出し元が
  実際に「`RetrySchedulerDecision`自体を無効化したい」という要求を持つかどうかは
  現時点では不明である。仮の要求のために型を1つ増やすことは、Charter 5章
  「Small Release」の方針に反する

この判断はプロジェクトの設計言語からの意図的な逸脱であり、次工程のArchitecture
Reviewでも重点的に扱う想定である。

### Design Decision #3：メソッド名は`select_candidates()` / `select_next_candidate()`とする

Charter 8章 Open Question 4に対し、以下の2メソッド構成とする。

* `select_candidates(limit: int | None = None) -> list`：`RetrySchedulerSource`の
  `list_pending_retries()`と対になる、複数候補を返す基本形
* `select_next_candidate()`：`select_candidates(limit=1)`の便利ラッパー。単一候補が
  欲しい典型的なユースケース（1件ずつ処理する将来のRetry実行ループ等）に対応する

「専用データクラス（例：`RetrySchedulerDecisionResult`）を新設するか」という
Open Question 3の別案は採用しない。`RetrySchedulerSource`が`RetryQueueItem`を
そのまま返す設計（加工しない）を踏襲し、本Releaseでは選択結果に「理由」等の
付加情報を持たせる要求がないため、戻り値は`RetryQueueItem`（型ヒント上は無型の
`list` / 単一要素）のままとする。

### Design Decision #4：`select_candidates()`の戻り値型を無型の`list`にする

`docs/design/retry_scheduler_wiring.md` 13章 Design Decision #1と同じ理由。
`RetryQueueItem`は`retry_queue`の公開型であり、`retry_scheduler_source`経由でも
再exportされていない。型の厳密さよりも「`retry_scheduler_decision → retry_scheduler_source`
の一方向のみ」という依存方向の一貫性（Charter 7章）を優先し、無型の`list`とする
（docstringで実際の要素型を説明する）。

---

## 14. Charter Open Questions への回答（まとめ）

1. **Constructor Injectionの引数型**：`RetrySchedulerSource | NullRetrySchedulerSource`
   のUnion型、かつ必須引数（デフォルトなし）（13章 Design Decision #1・#2）
2. **Null Object Patternの要否**：採用しない。`NullRetrySchedulerSource`を注入する
   ことで「無効化」を表現する（13章 Design Decision #2）
3. **候補選択の出力形状**：専用データクラスは新設せず、`RetryQueueItem`
   （`RetrySchedulerSource`と同じ型）をそのまま返す（13章 Design Decision #3）
4. **メソッド名**：`select_candidates(limit=None)` / `select_next_candidate()`
   （13章 Design Decision #3）

---

## 16. Architecture Review

状態：**Approve with Minor Recommendations**（Claude Codeによる自己点検。
指摘事項は3件、いずれも本Releaseの実装をブロックしない）。

### 16.1 レビュー観点別の判定（ユーザー指定12項目）

| # | 観点 | 判定 | 根拠 |
|---|---|---|---|
| 1 | `RetrySchedulerDecision`を新規独立パッケージとして切り出す判断が妥当か | **妥当** | v3.4.0 Architecture Reviewで残した「`SchedulerEngine`に3つ目の異種責務が入ったら責務分割を再検討する」という指摘に直接対応している。パッケージ単位で層を分ける構成は`retry_scheduler_source`（v3.3.0、2ファイル・1クラスペア）と同型であり、本Releaseは1クラスのみでさらに最小（3章）。プロジェクト全体で「1関心事＝1パッケージ」という構成が一貫しており、過剰な抽象化ではない |
| 2 | `SchedulerEngine`を無改修に保つ判断が妥当か | **妥当** | `retry_scheduler_decision`は`scheduler`を一切importせず、`scheduler`側からも本Releaseでは`retry_scheduler_decision`を一切importしない（7章・10章）。Charter 4章の「対象外：SchedulerEngineの改修」と1対1で対応している |
| 3 | 責務が「候補選択のみ」に限定されているか | **限定されている** | `select_candidates()`は`list_pending_retries()`への1行委譲、`select_next_candidate()`は`select_candidates(limit=1)`の先頭要素取得のみ（4章）。フィルタリング・並べ替え・実行判断のロジックは一切持たない |
| 4 | `list_pending_retries()`の既存順序を信頼し独自ソート・優先度計算を行わない設計が妥当か | **妥当** | `RetryQueueManager.list()`が既に行うpriority昇順・enqueue_time昇順の整列を重複実装しないことで、将来`retry_queue`側の整列基準が変わった場合でも`retry_scheduler_decision`側の修正が不要になる（Adapterパターンの利点がそのまま及ぶ） |
| 5 | `select_candidates(limit=None)` / `select_next_candidate()`のメソッド設計が妥当か | **妥当（Minor Recommendation 1件）** | `RetrySchedulerSource`の`list_pending_retries()` / `count_pending_retries()`ペア、`SchedulerEngine.run_due()`が`evaluate()`を呼び出す構造と一貫している。ただし`select_next_candidate()`の「先頭1件」が意味する順序基準（priority昇順・enqueue_time昇順）がメソッド自身のdocstringには明記されておらず、モジュールdocstring（Design Policy 2章相当）を参照しないと分からない。実装時にdocstringへ一言補うことを推奨する（16.3節 Minor Recommendation 1） |
| 6 | `RetryQueueItem`をそのまま返す出力形状が妥当か | **妥当** | `RetrySchedulerSource`が`RetryQueueItem`をそのまま返す設計（v3.3.0）・`RetryResult`が`WorkflowEngineResult`を埋め込む設計（v3.0.0）と一貫しており、消費者不在の現時点で独自DTOを先回りして決め打ちしない判断は合理的 |
| 7 | Null Object Patternを採用しない判断が妥当か | **妥当（ただし要注記。Minor Recommendation 2件）** | 本コンポーネントには対応するFeature Gate/Config軸が存在せず、`NullRetrySchedulerSource`を注入するだけで「候補なし」が自然に得られる（7.3節）ため、`NullRetrySchedulerDecision`は実質的に重複した表現になる、という論拠は妥当。ただし、プロジェクト内で初めてNull Object Patternを持たない新規コンポーネントとなるため、意図的な逸脱であることが埋没しないよう、実装時のdocstring・テストで明示し続けることを推奨する（既に13章 Design Decision #2・11章Future Extensionで対応済みだが、Test工程でも「`NullRetrySchedulerDecision`が存在しないこと」を確認テストとして残すことを推奨する。16.3節 Minor Recommendation 2） |
| 8 | Constructor Injectionの引数を必須にする判断が妥当か | **妥当** | `RetrySchedulerSource.__init__(self, queue: RetryQueueManager)`（v3.3.0）も同じくデフォルトを持たない必須引数であり、「唯一の実質的入力を持つAdapter/補助コンポーネントは必須引数とする」という既存の先例と一致する。`SchedulerEngine`（複数責務のうちの1つとしてretry_sourceを持つ）とは性質が異なるため、両者で必須/任意が分かれることは矛盾ではなく妥当な使い分けである |
| 9 | `retry_queue` / `retry_engine` / `scheduler`への直接依存が混入しないか | **混入しない** | 4章のPublic APIコード抜粋で確認した限り、importは`retry_scheduler_source`の公開シンボルのみ。`select_candidates()`の戻り値型を無型`list`にしたことで、型ヒントのためだけに`retry_queue`をimportする誘惑も構造的に排除されている（13章 Design Decision #4） |
| 10 | `dequeue()` / `remove()` / Retry Engine起動 / Queue更新が混入しないか | **混入しない（構造的に不可能）** | `RetrySchedulerSource` / `NullRetrySchedulerSource`のいずれも該当メソッドを公開していない。`retry_engine`は一切importされない。10章Boundaryで経路の不在を明示しており、Test工程で構造的確認（Spyオブジェクト）を行う方針も示されている |
| 11 | Foundation First / SRP / Stateless / Constructor Injection / Backward Compatibilityが守られているか | **すべて守られている** | Foundation First：消費者不在（1章）。SRP：単一クラス・単一責務で、これまでの全Releaseの中でも最も責務範囲が狭い。Stateless：候補を保持・キャッシュしない（2章）。Constructor Injection：セッター・ファクトリなし。Backward Compatibility：既存ファイルへの変更が一切ないため、後方互換性リスクは実質ゼロ（12章） |
| 12 | 既存Regressionへの影響がないか | **影響なし（設計上は最小リスク）** | 本Releaseは新規独立パッケージの追加のみであり、既存の`scheduler` / `retry_scheduler_source` / `retry_queue` / `retry_engine`のいずれのファイルも変更しない。v3.4.0（`scheduler_engine.py`を変更）よりもさらに影響範囲が小さく、Test工程での既存回帰確認は形式的な確認で足りる見込み |

### 16.2 SOLID

* **単一責任（SRP）**：`RetrySchedulerDecision`は「並んでいる候補から選ぶ」という
  一点のみに責務が絞られている。これまでの全パッケージの中でも最小・最も単純な
  責務範囲であり、SRPの模範的な適用といえる
* **開放閉鎖（OCP）**：`RetrySchedulerSource`の公開インターフェース
  （`list_pending_retries()`）にのみ依存しており、`retry_queue`側の内部実装
  （整列アルゴリズム・データ構造）が変わっても影響を受けない
* **リスコフの置換（LSP）**：`RetrySchedulerSource`と`NullRetrySchedulerSource`は
  戻り値の型（`list[RetryQueueItem]`）が一致しており（v3.3.0で確認済み）、
  `RetrySchedulerDecision`はどちらを注入されても同じコードパスで正しく動作する
* **インターフェース分離（ISP）**：`RetrySchedulerDecision`が利用するのは
  `list_pending_retries()`のみ（`count_pending_retries()`は利用しない）。
  必要最小限のメソッドにしか依存していない
* **依存性逆転（DIP）**：`RetrySchedulerDecision`は`RetrySchedulerSource`という
  具象クラス（Union型経由）に依存する。ABCを導入していない点は`SchedulerEngine`の
  `retry_source`と同様であり、プロジェクト全体の「継承なしDuck Typing」という
  設計言語との一貫性を優先した判断として妥当

### 16.3 残された懸念（Minor Recommendations）

1. **`select_next_candidate()`のdocstringに順序基準の明記がない**：「先頭1件」が
   priority昇順・enqueue_time昇順の結果であることは、モジュールdocstring
   （設計方針）を読まないと分からない。実装時にメソッドのdocstringへ一言
   （例：「`RetrySchedulerSource`が返す順序＝priority昇順・enqueue_time昇順の
   先頭1件」）を補うことを推奨する
2. **Null Object Pattern不採用という初の例外**：論拠自体は妥当だが、プロジェクト内で
   唯一Null Object Patternを持たないコンポーネントになるため、実装時のdocstring・
   Test工程での確認テスト（「`NullRetrySchedulerDecision`という名前のクラス・
   シンボルが存在しないこと」を明示的にテストする等）を通じて、意図的な設計判断で
   あることが将来にわたって明確に分かる状態を維持することを推奨する
3. **Error Handlingセクションの省略**：v3.3.0・v3.4.0の設計書にあった
   「10. Error Handling」に相当する節が本書にはなく、`retry_source`に`None`が
   渡された場合の扱い（型ヒント上サポート対象外、防御的チェックは追加しない）が
   明文化されていない。既存の全Managerクラスと同じ扱いになる想定だが、実装時に
   Docstringまたはテストコードのコメントで同様の扱いであることを明記することを
   推奨する

いずれも実装を妨げる指摘ではなく、実装時の記述レベルでの補強事項として整理する。

### 16.4 Foundation First・プロジェクト全体との設計整合性

Charter（4章・10章）が要求した「選択ロジックの新設のみ」という範囲に対し、本設計は
`SchedulerEngine`との実配線・選択結果を使った実行（自動Retry実行）をいずれも
11章Future Extensionへ送っており、スコープの逸脱はない。v3.3.0の
`RetrySchedulerSource`・v3.1.0の`RetryQueue`と同じ「消費者不在の先行実装」パターンを
維持している。

Null Object Pattern不採用という判断は、プロジェクト全体の設計言語からの意図的な
逸脱ではあるが、「Feature Gate/Config軸を持たないコンポーネントにはNull Object
Patternを機械的に適用しない」という、v3.3.0の`RetrySchedulerSource`が確立した
考え方（`docs/design/retry_scheduler_integration.md` 13章）をさらに一歩進めた
帰結であり、無秩序な逸脱ではなく一貫した設計哲学の延長線上にある。

### 16.5 依存方向

```
src/retry_scheduler_decision/ ── import ──→ retry_scheduler_source（公開APIのみ：
                                             RetrySchedulerSource / NullRetrySchedulerSource）
retry_scheduler_source        ── import ──→ retry_queue（v3.3.0のまま、無改修）
```

`retry_scheduler_decision`は`scheduler` / `retry_queue` / `retry_engine`のいずれも
直接importしない。`scheduler`側も本Releaseでは`retry_scheduler_decision`を一切
importしない（相互に無関係）。循環importの余地は構造的に存在しない。

### 16.6 後方互換性

12章で述べたとおり、変更は新規独立パッケージの追加のみであり、既存の
`scheduler` / `retry_scheduler_source` / `retry_queue` / `retry_engine`配下の
全ファイルに一切変更がない。これまでの全Releaseの中でも後方互換性リスクが
最小のRelease（v3.4.0は`scheduler_engine.py`を変更したが、本Releaseは既存ファイル
無改修）である。

### 16.7 総評

Charterが要求した項目（新規独立パッケージ化・`SchedulerEngine`無改修・候補選択への
責務限定・既存順序の信頼・メソッド設計・出力形状・Null Object Pattern要否の再検討・
Constructor Injectionの必須化・依存混入防止・dequeue等の排除・Foundation First等の
維持・既存Regression回避）はいずれも設計上満たされている。Minor Recommendations
3件（16.3節）はいずれも実装時の記述レベルの補強事項であり、実装をブロックする
性質のものではない。

**Approve with Minor Recommendations** と判断する。

---

## 17. Status

- [x] Architecture Design ドラフト作成（本文書、Claude Code作成）
- [x] Architecture Review完了（Claude Codeによる自己点検、Approve with Minor
      Recommendations。指摘事項3件は実装時の記述レベルの補強事項として記録済み）
- [ ] ChatGPTレビュー（Project Charter・Architecture Designの妥当性確認）
- [ ] ユーザー確認・実装可否判断
- [ ] 実装開始（未着手）
