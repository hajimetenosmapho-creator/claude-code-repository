# v4.5.0 Retry Policy Foundation 設計書（Architecture Design）

作成日：2026-07-08
状態：確定（Architecture Review完了・Approve with Recommendations、
Recommendation 4件反映済み。12章参照）
`docs/design/retry_policy_foundation_charter.md`（Project Charter、承認済み）を
前提とする。

> **本設計書の進め方について**：Charter 8章 Open Questionsで残された5論点
> （Protocol/ABC・インターフェースの範囲・ファイル配置・`RetryManager`の
> 変更範囲・テスト方針）について、ユーザーから示された希望方針
> （Protocol優先／`target_statuses` / `max_attempts`を含める案を優先検討／
> 新規ファイル分離優先／`RetryManager`は動作変更なし）を踏まえつつ、
> 3章・4章で複数案を比較したうえで、それぞれ最も安全な案を確定する。

---

## 1. Architecture Overview

現状（v3.0.0〜v4.4.0）、`RetryManager`は`RetryPolicy`に対して2つの依存を
持っている。

```
RetryManager.retry(run_id, attempt, dry_run)
   │
   ├─ self._monitor.get_status(run_id)               （無改修）
   ├─ self._policy.should_retry(status, attempt)      ← 依存1：判定メソッド
   ├─ self._skip_reason(status, attempt)
   │     ├─ self._policy.target_statuses（membership判定・sorted()での列挙）
   │     └─ self._policy.max_attempts（メッセージ文字列への埋め込み）
   │                                                    ← 依存2：2つの属性
   └─ self._executor.execute(request, record)         （無改修）
```

本Release（v4.5.0）は、この2つの依存を**Protocol（構造的部分型）として
明示化**する。既存`RetryPolicy`（`retry_policy.py`）は無改修のまま、この
Protocolを構造的に満たす実装として扱う。`RetryManager`は`policy`引数の
**型注釈のみ**を変更し、実行時の挙動（`retry()` / `_skip_reason()`の
ロジック本体）は1行も変更しない。

```
src/retry_engine/
   │
   ├── retry_policy.py（v3.0.0、無改修・0 diff）
   │     RetryPolicy（frozen dataclass）
   │       - target_statuses / max_attempts
   │       - should_retry(monitor_status, attempt) -> bool
   │
   ├── retry_policy_protocol.py ★新規
   │     RetryDecisionPolicy（Protocol）      ← 依存1のみを表現する最小契約
   │     ExplainableRetryPolicy（Protocol）   ← 依存1＋依存2を表現する拡張契約
   │           （RetryDecisionPolicyを継承したProtocol）
   │
   └── retry_manager.py ★変更（型注釈のみ）
         RetryManager.__init__ / from_config() の
         policy: RetryPolicy → policy: ExplainableRetryPolicy
         retry() / _skip_reason() の本体は無変更
```

`RetryPolicy`は`retry_policy_protocol.py`を一切importしない
（Protocolは構造的部分型であり、満たす側が明示的にimport・継承する
必要がないため）。依存の向きは`retry_manager.py → retry_policy_protocol.py`
のみであり、`retry_policy.py`は本Releaseにおいて依存グラフ上完全に孤立
したまま（＝無改修であることの構造的な裏付け）。

---

## 2. Design Policy

* **Foundation First**：Protocolという「差し替え可能な構造」を定義する
  ところまでを行う。`FixedRetryPolicy` / `ExponentialBackoffPolicy` /
  `AdaptiveRetryPolicy`の実装、および実際に戦略を切り替える
  Composition Rootは後続Releaseへ送る
* **Single Responsibility**：「再試行すべきかどうかを判定する」契約
  （`RetryDecisionPolicy`）と、「判定結果をどう説明するか（スキップ理由の
  生成）に必要な情報を公開する」契約（`ExplainableRetryPolicy`）を分離する
  （4章で詳述）。1つのProtocolに両方の責務を詰め込まない
* **Stateless**：新設する2つのProtocolはいずれもデータを持たない
  （構造の宣言のみ）。既存`RetryPolicy`のStateless性（frozen dataclass）
  にも一切影響しない
* **Backward Compatibility**：
  - `retry_policy.py`は0 diff（1バイトも変更しない）
  - `retry_manager.py`は`policy`引数の型注釈のみ変更する。Pythonは型注釈を
    実行時に強制しないため、既存の`RetryManager(policy=RetryPolicy(...), ...)`
    という呼び出しは本Release前後でまったく同じ結果になる
* **既存パターンとの整合性**：v4.4.0`retry_outcome_terminality.py`が
  確立した「新規ファイルとして分離し、既存ファイルには一切手を入れない」
  というパターンを踏襲する

---

## 3. Option比較①：Protocol か ABC か

| 観点 | Protocol（`typing.Protocol`） | ABC（`abc.ABC`） |
|---|---|---|
| 既存`retry_policy.py`への変更 | **不要（0 diff）** | 継承宣言の追加が必要（`class RetryPolicy(RetryDecisionPolicy):`のような1行変更） |
| Backward Compatibility | 完全（既存ファイルへの変更がそもそも発生しない） | 動作は同じでも「既存ファイルは変更しない」というCharter方針・ユーザー指示に反する |
| 型チェッカーでの検証 | 構造的に検証可能。`@runtime_checkable`を付与すれば`isinstance()`によるテスト時の構造確認も可能 | 継承関係により検証。IDE補完・「未実装メソッド」のエラー表示に強い |
| プロジェクトの既存パターンとの整合性 | v4.4.0`retry_outcome_terminality.py`の「新規ファイル分離・既存ファイル無改修」パターンと一致 | このプロジェクトで初めて「既存クラスに継承を後付けする」パターンを持ち込むことになる |
| 将来の新戦略実装のしやすさ | 継承不要。`should_retry()`等を実装するだけで自動的に適合する | 新戦略ごとに明示的な継承が必要（書き漏れを型エラーで検出できる利点はある） |

**結論：Protocolを採用する。**

理由：ユーザー指示（Protocol優先・既存無改修）と完全に一致するうえ、
「既存コンポーネントへの変更を避ける」というこのプロジェクトの一貫した
設計哲学（v3.8.0〜v4.4.0で繰り返し採用）に最も忠実である。ABCが持つ
「書き漏れの静的検出」という利点は、本Releaseでは新戦略を実装しない
（Non-Goal）ため今のところ活用機会がなく、将来新戦略を実装する
Releaseで改めて必要性を評価すればよい。

---

## 4. Option比較②：インターフェースの範囲

1章で確認した通り、`RetryManager`は実際には`should_retry()`（依存1）
だけでなく`target_statuses` / `max_attempts`（依存2、`_skip_reason()`が
使用）にも依存している。この事実をどうインターフェースへ反映するかで
3案を比較する。

### 案A：`should_retry()`のみの最小契約

```python
class RetryDecisionPolicy(Protocol):
    def should_retry(self, monitor_status, attempt) -> bool: ...
```

* 利点：もっとも小さく、将来のあらゆる戦略が確実に満たせる
* 欠点：`_skip_reason()`が実際に依存している`target_statuses` /
  `max_attempts`を隠蔽してしまう。「最小インターフェース」を謳いながら
  実態（1章の発見）と乖離したドキュメントになり、将来
  `target_statuses` / `max_attempts`を持たない戦略を注入すると
  `_skip_reason()`が`AttributeError`で壊れることに気づきにくい

### 案B：3メンバーを1つのProtocolに統合

```python
class RetryDecisionPolicy(Protocol):
    target_statuses: frozenset[WorkflowMonitorStatus]
    max_attempts: int
    def should_retry(self, monitor_status, attempt) -> bool: ...
```

* 利点：`RetryManager`の実際の依存を過不足なく1つの契約で表現できる
* 欠点：**責務が膨らむ**。`target_statuses`（対象ステータスの集合）・
  `max_attempts`（固定回数上限）は、いずれも「固定ルール」という
  `RetryPolicy`固有の設計（Charter・`retry_policy.py`docstring）に
  根ざした概念である。将来`ExponentialBackoffPolicy`
  （`base_delay` / `max_delay` / `jitter`等が自然な概念）や
  `AdaptiveRetryPolicy`（外部システムの状態に応じて動的に判定する等）を
  実装する際、これらの戦略が「`target_statuses`という固定集合」
  「`max_attempts`という固定回数」という**Fixed Policy固有の語彙**を
  無理に持たされることになる。「差し替え可能な構造にする」という
  本Releaseの目的（Charter 2章）に対し、かえって将来の戦略実装の自由度を
  狭めるリスクがある

### 案C（推奨）：核となる契約と、説明能力の契約を分離する

```python
class RetryDecisionPolicy(Protocol):
    """再試行すべきかどうかを判定する、あらゆる戦略に共通する最小契約。"""
    def should_retry(self, monitor_status, attempt) -> bool: ...


class ExplainableRetryPolicy(RetryDecisionPolicy, Protocol):
    """RetryDecisionPolicyに加え、判定結果の理由説明に必要な属性を公開する契約。
    RetryManager._skip_reason()が現に依存している面（1章）を明示化したもの。"""
    target_statuses: frozenset[WorkflowMonitorStatus]
    max_attempts: int
```

* `RetryDecisionPolicy`：あらゆる戦略が満たすべき最小契約（案Aと同じ形）
* `ExplainableRetryPolicy`：`RetryDecisionPolicy`を拡張し、
  `_skip_reason()`が今まさに必要としている2属性を追加した契約
* `RetryPolicy`（v3.0.0）は無改修のまま、構造的に両方を満たす
* `RetryManager`の`policy`引数の型注釈は、**現在の実際の依存を偽らず**
  `ExplainableRetryPolicy`とする（1章の依存2を隠蔽しない）
* 将来`target_statuses` / `max_attempts`という概念を持たない戦略
  （例：`ExponentialBackoffPolicy`）を実装する場合、その戦略は
  `RetryDecisionPolicy`のみを満たせばよく、`_skip_reason()`との結合は
  そのReleaseで個別に解消する（9章 Future Extension）

### 比較表

| 観点 | 案A（最小のみ） | 案B（1つに統合） | 案C（分離、推奨） |
|---|---|---|---|
| `RetryManager`の実依存との一致 | ✕ 乖離あり（依存2を隠蔽） | ○ 一致 | ○ 一致（`ExplainableRetryPolicy`で表現） |
| Single Responsibility | ○ | ✕ 判定責務と説明責務が混在 | ○ 2つの契約に分離 |
| 将来戦略の実装しやすさ | ○（ただし`_skip_reason()`との結合が暗黙のまま） | ✕ 無関係な属性を強制される | ○ 最小契約のみ満たせばよい |
| ドキュメントとしての誠実さ | ✕ | ○ | ○ |
| 責務の膨らみ | 小さいが実態を反映しない | 大きい（Fixed Policy固有の語彙が漏れ出す） | 適正（契約を2段階に分割） |

**結論：案Cを採用する。**

ユーザー方針「`target_statuses` / `max_attempts`も含める案を優先検討」を
`ExplainableRetryPolicy`として実現しつつ、「責務が膨らみすぎる場合は
代替案を比較する」という指示に対しては、1つのProtocolに統合せず
Protocol継承によって段階的な契約に分割することで、将来の戦略実装の
自由度（`RetryDecisionPolicy`のみを満たせばよい）を確保する。これが
本Open Questionにおいて最も安全な案と判断する。

---

## 5. Package Structure（変更差分）

```
src/retry_engine/
├── retry_policy.py                ← 無改修（0 diff）
├── retry_policy_protocol.py       ★新規
│     RetryDecisionPolicy（Protocol, runtime_checkable）
│     ExplainableRetryPolicy（Protocol, runtime_checkable。RetryDecisionPolicyを拡張）
├── retry_manager.py               ★変更（型注釈のみ）
│     RetryManager.__init__ / from_config() の
│         policy: RetryPolicy → policy: ExplainableRetryPolicy
│     retry() / _skip_reason() / その他既存メソッドは1行も変更しない
└── __init__.py                    ★変更（新規2シンボルexport）
```

`retry_config.py` / `retry_result.py` / `retry_request.py` / `retry_executor.py`
を含む、Retry Queue / Cleanup系列（v4.1.0〜v4.4.0の全ファイル）はいずれも
無改修。

---

## 6. Public API

```python
# retry_policy_protocol.py
from __future__ import annotations

from typing import Protocol, runtime_checkable

from workflow_monitor import WorkflowMonitorStatus


@runtime_checkable
class RetryDecisionPolicy(Protocol):
    """
    再試行すべきかどうかを判定する、あらゆるRetry戦略に共通する最小契約。
    RetryManager.retry() が唯一呼び出す判定メソッドのみを要求する。
    """

    def should_retry(self, monitor_status: WorkflowMonitorStatus, attempt: int) -> bool: ...


@runtime_checkable
class ExplainableRetryPolicy(RetryDecisionPolicy, Protocol):
    """
    RetryDecisionPolicyに加え、RetryManager._skip_reason() が
    スキップ理由の文字列を生成するために必要とする属性を公開する契約。

    target_statuses / max_attempts は Fixed Retry Policy（RetryPolicy）に
    根ざした概念であり、将来の戦略（Exponential Backoff等）がこの契約まで
    満たす必要はない（RetryDecisionPolicyのみで足りる）。
    """

    target_statuses: frozenset[WorkflowMonitorStatus]
    max_attempts: int
```

```python
# retry_manager.py（差分イメージ、型注釈のみ）
from .retry_policy_protocol import ExplainableRetryPolicy

class RetryManager:
    def __init__(
        self,
        policy: ExplainableRetryPolicy,   # 変更前： policy: RetryPolicy
        executor: RetryExecutor,
        ...
    ):
        self._policy = policy   # 代入自体は無変更
        ...

    @classmethod
    def from_config(
        cls,
        retry_config: RetryConfig,
        retry_policy: ExplainableRetryPolicy,  # 変更前： retry_policy: RetryPolicy
        ...
    ) -> "RetryManager | NullRetryManager":
        ...

    # retry() / _skip_reason() の本体は1行も変更しない
```

`retry_policy.py`側の変更は一切ない（`RetryPolicy`クラスの定義は現状の
まま）。`RetryPolicy`が`ExplainableRetryPolicy`を満たすことは、
`@runtime_checkable`により実行時にも`isinstance()`で確認できる
（7章）。

> **命名の視認性について（Architecture Review 12.3節 Recommendation 1反映）**：
> `retry_policy_protocol.py`のモジュールdocstring冒頭に、「本ファイルは
> 抽象契約（Protocol）のみを定義する。再試行ルールの具体的な実装は
> 引き続き`RetryPolicy`（`retry_policy.py`、無改修）である。名称が似ている
> （`RetryDecisionPolicy` / `ExplainableRetryPolicy` vs `RetryPolicy`）ため
> 混同しないこと」という一文を明記する。

> **実装時の不要import整理について（Architecture Review 12.1節
> Recommendation 2反映）**：`retry_manager.py`の`policy` / `retry_policy`
> 引数の型注釈を`RetryPolicy`から`ExplainableRetryPolicy`へ変更した結果、
> `from .retry_policy import RetryPolicy`のimportが型注釈以外の目的で
> 使われていない場合は、実装時に不要importとして削除する（削除自体も
> 「型注釈のみの変更」の一部であり、実行時の挙動には影響しない）。

---

## 7. Sequence（適合性の確認例）

```python
from retry_engine.retry_policy import RetryPolicy
from retry_engine.retry_policy_protocol import RetryDecisionPolicy, ExplainableRetryPolicy

policy = RetryPolicy(target_statuses=DEFAULT_TARGET_STATUSES, max_attempts=3)

assert isinstance(policy, RetryDecisionPolicy)     # True（構造的に満たす）
assert isinstance(policy, ExplainableRetryPolicy)  # True（構造的に満たす）

# 既存の呼び出しは無変更で動作する
manager = RetryManager(policy=policy, executor=executor, monitor=monitor)
```

差し替え可能性を確認するための最小Fake（本物の戦略実装ではない、
テスト専用）：

```python
class _FakeAlwaysRetryPolicy:
    """ExplainableRetryPolicyを満たす最小Fake。テストでの構造確認専用。"""
    target_statuses = frozenset({WorkflowMonitorStatus.FAILED})
    max_attempts = 99

    def should_retry(self, monitor_status, attempt) -> bool:
        return True

fake = _FakeAlwaysRetryPolicy()
assert isinstance(fake, ExplainableRetryPolicy)  # 継承なしで構造的に適合

manager = RetryManager(policy=fake, executor=executor, monitor=monitor)
# manager.retry(...) は fake.should_retry(...) を呼び出して動作する
```

`RetryDecisionPolicy`のみを満たす（`target_statuses` / `max_attempts`を
持たない）Fakeも定義可能であり、`isinstance(minimal_fake,
RetryDecisionPolicy)`はTrueだが`isinstance(minimal_fake,
ExplainableRetryPolicy)`はFalseになることをテストで確認する
（案Cの「段階的な契約」が実際に機能することの構造的な裏付け）。

> **`isinstance()`の限界について（Architecture Review 12.5節
> Recommendation 3反映）**：`@runtime_checkable`による`isinstance()`は
> メソッド・属性の**存在**のみを検証し、シグネチャ（引数の型・個数・
> 戻り値の型）までは検証しない。したがって`isinstance(fake,
> ExplainableRetryPolicy)`が`True`であることは「構造が存在する」ことの
> 確認に過ぎず、「正しく動作する」ことの証明にはならない。本Releaseの
> テストは、この構造確認に加えて`RetryManager(policy=fake,
> ...).retry(...)`を実際に呼び出し`fake.should_retry(...)`が意図通りに
> 呼ばれ結果に反映されることを確認する振る舞いテストを**必須**とする
> （両方を揃えて初めて「差し替え可能である」ことの十分な確認となる）。

---

## 8. Boundary（今回入れない境界線）

* `FixedRetryPolicy` / `ExponentialBackoffPolicy` / `AdaptiveRetryPolicy`
  等、`RetryDecisionPolicy` / `ExplainableRetryPolicy`を満たす具体的な
  新戦略の実装
* `_skip_reason()`が`target_statuses` / `max_attempts`に直接依存している
  こと自体の解消（本Releaseでは依存の事実を契約として明示するだけに
  留め、依存そのものを切り離すリファクタリングは行わない。9章）
* 複数戦略を実行時に選択・切り替えるComposition Root
* `RetryPolicy.from_env()` / `RETRY_MAX_ATTEMPTS`環境変数仕様の変更
* Retry Queue / Cleanup系列（`retry_queue_update_decider.py`以下v4.1.0〜
  v4.4.0の全ファイル）への変更

---

## 9. Future Extension

* 将来`target_statuses` / `max_attempts`という概念を持たない戦略
  （例：`ExponentialBackoffPolicy`）を実装するReleaseでは、以下いずれかの
  対応を検討する
  1. `_skip_reason()`を`RetryDecisionPolicy`（最小契約）のみに依存する
     よう見直し、`ExplainableRetryPolicy`を満たさない戦略の場合は
     汎用的なメッセージにフォールバックする
  2. 各戦略が独自の「スキップ理由説明」ロジックを持てるよう、
     `ExplainableRetryPolicy`とは別の、より抽象的な説明用インターフェース
     （例：`explain_skip(monitor_status, attempt) -> str`）を新設する
  いずれを選ぶかは、実際にその戦略を実装するReleaseで、その戦略の
  性質を踏まえて判断する（本Releaseで先回りして決めない）
* 複数戦略を環境変数や設定で切り替えるComposition Root
* 静的型チェック（mypy等）を導入する場合、`RetryDecisionPolicy` /
  `ExplainableRetryPolicy`を活用した型検証の強化

---

## 10. Compatibility

* `retry_policy.py`：0 diff（変更なし）
* `retry_manager.py`：`RetryManager.__init__` / `from_config()`の
  `policy` / `retry_policy`引数の**型注釈のみ**変更。Pythonは型注釈を
  実行時に強制しないため、既存の
  `RetryManager(policy=RetryPolicy(...), ...)` /
  `RetryManager.from_config(retry_policy=RetryPolicy(...), ...)`という
  呼び出しは本Release前後でまったく同じ結果になる
* `retry()` / `_skip_reason()`を含む既存メソッドの本体はいずれも無変更
* `__init__.py`：`RetryDecisionPolicy` / `ExplainableRetryPolicy`の
  新規2シンボルexportのみ追加

> **モジュールdocstring更新について（Architecture Review 12.4節
> Recommendation 4反映）**：`retry_manager.py` / `__init__.py`は
> v3.0.0〜v4.4.0を通じて、モジュールdocstring冒頭にバージョンごとの
> 設計メモを追記する慣習を一貫して守っている。実装時、本Release
> （v4.5.0）分のメモをこの慣習に従って追記すること（CHANGELOG.md /
> ROADMAP.md / architecture.mdの更新はCharter Scopeに既に含まれているが、
> 各ファイル自身のdocstring追記を忘れないよう本節に明記する）。

---

## 11. Risks and Mitigations

| リスク | 対策 |
|---|---|
| 型注釈の変更だけでは実行時の安全性を保証できない（Pythonは型を強制しない） | `@runtime_checkable`を付与し、テストで`isinstance()`による構造確認を行う（7章）。加えてFake注入によるふるまいテストで実際の動作互換性を確認する |
| `ExplainableRetryPolicy`が依然として「Fixed Policy固有の語彙」（`target_statuses` / `max_attempts`）を含んでおり、真に汎用的とは言えない | 4章で意図的なトレードオフとして明記済み。`RetryDecisionPolicy`（最小契約）を別途用意することで、この語彙を強制されない拡張経路を確保している。将来的な解消方針は9章Future Extensionに記録し、次に新戦略を実装するReleaseで再評価する |
| 将来`RetryDecisionPolicy`のみを満たす戦略を`RetryManager`に注入すると、型注釈上は`ExplainableRetryPolicy`を要求しているため型チェッカーが警告する（実行時は`_skip_reason()`到達時に`AttributeError`） | 本Releaseでは`RetryPolicy`以外は注入されないため実害はない。次に新戦略を実装するReleaseで、9章の対応（`_skip_reason()`の見直し）を先に行うことをそのReleaseのCharterに明記する運用とする |

---

## 12. Architecture Review

**結論：Approve with Recommendations**

3章・4章で確定した設計（Protocol採用・案C＝契約2段階分離）を前提に、
以下5つの観点で確認する。

### 12.1 観点1：Protocol継承の技術的な妥当性

**評価：Approve**

`class ExplainableRetryPolicy(RetryDecisionPolicy, Protocol):`という
Protocol継承は、既存のProtocolの要求メンバーを拡張する標準的な書き方
（PEP 544）であり、技術的な問題はない。`@runtime_checkable`は
`RetryDecisionPolicy` / `ExplainableRetryPolicy`それぞれに個別に
付与する必要がある（継承では自動的に引き継がれない）ことを確認し、
6章のコード例は両方に明示的に付与済みであることを確認した。

`retry_manager.py`側では、型注釈を`RetryPolicy`から
`ExplainableRetryPolicy`に変更した結果、型注釈以外の目的で使われて
いなければ`from .retry_policy import RetryPolicy`のimportが不要になる。
これは実装時に見落としやすい点である。

> **Recommendation 2**：6章の該当箇所に既に反映済み（実装時、不要import
> の削除を明記）。

### 12.2 観点2：案C（契約2段階分離）はSingle Responsibilityを実際に達成しているか

**評価：Approve**

`RetryDecisionPolicy`（判定のみ）と`ExplainableRetryPolicy`（判定＋説明用
属性）を分離したことで、将来`target_statuses` / `max_attempts`という
概念を持たない戦略は`RetryDecisionPolicy`のみを満たせばよい構造になって
いることを4章の比較表・6章のコード例で確認した。責務の混在は解消されて
いる。

### 12.3 観点3：命名の視認性（既存`RetryPolicy`との混同リスク）

**評価：軽微な懸念あり（Approve、ドキュメント注記を推奨）**

`RetryDecisionPolicy` / `ExplainableRetryPolicy`（抽象契約）と
`RetryPolicy`（具体実装）は、字面が非常に似ている。CLAUDE.mdに
「プログラミング初心者」と明記されている運用者にとって、「Protocolの
名前」と「実装クラスの名前」の違いを一目で区別するのは難しい可能性が
ある。v4.4.0でも`RetryQueueCleanupDecider` vs
`RetryQueueTerminalCleanupDecider`について同種の懸念が指摘され、
モジュールdocstringへの注記で対応した前例がある。

> **Recommendation 1**：6章の該当箇所に既に反映済み（`retry_policy_protocol.py`
> のモジュールdocstringに、`RetryPolicy`との関係を明記する）。

### 12.4 観点4：Backward Compatibilityの構造的な裏付け

**評価：Approve**

`retry_policy.py`が0 diffであることは、依存グラフ上
`retry_policy_protocol.py`から一切参照されない（Protocolは満たす側が
importする必要がない）という1章の構造から論理的に裏付けられている。
`retry_manager.py`の変更が型注釈のみに限られることも、Pythonが型注釈を
実行時に強制しないという事実（10章）から裏付けられている。

ただし、この慣習（バージョンごとのdocstring追記）を本Releaseでも
守ることを明記していなかった。

> **Recommendation 4**：10章の該当箇所に既に反映済み（`retry_manager.py`
> / `__init__.py`のモジュールdocstringにv4.5.0分を追記することを明記）。

### 12.5 観点5：テスト方針の十分性（`isinstance()`の限界）

**評価：Approve（前提の明記を推奨）**

`@runtime_checkable`による`isinstance()`は、メソッド・属性の**存在**の
みを検証し、シグネチャ（引数の型・個数・戻り値の型）までは検証しない
という`typing`モジュールの既知の制約がある。7章の設計は構造確認
（`isinstance()`）と振る舞い確認（`RetryManager(...).retry(...)`の
実行）の両方を含んでおり、この制約を踏まえた十分なテスト方針である
ことを確認した。ただし、この限界を認識したうえでの設計であることが
明記されていなかった。

> **Recommendation 3**：7章の該当箇所に既に反映済み（`isinstance()`は
> 構造確認のみであり、振る舞いテストと併用することを必須と明記）。

### まとめ

4件のRecommendationはいずれも「実装時に見落としやすい点をドキュメント
上で明示する」性質のものであり、3章・4章で確定した設計方針（Protocol・
案C・型注釈のみの変更）そのものを変更する指摘はなかった。全て2〜11章の
該当箇所に反映済み。

---

## 13. Status

- [x] Architecture Design ドラフト作成（本文書、Claude Code作成）
- [x] Architecture Review 実施（Approve with Recommendations、4件反映済み）
- [ ] ユーザー確認・フィードバック反映
- [ ] Implementation
