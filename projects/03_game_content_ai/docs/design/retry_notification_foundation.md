# Retry Notification Foundation（v6.6.0候補）

作成日：2026-07-15
更新日：2026-07-15（ChatGPT Architecture Review「Request Changes」反映：①`RetryNotificationStatus.SKIP`を`NO_NOTIFICATION`へ改名し「処理スキップ」との混同を解消、②Enum採用理由から将来`SUPPRESSED`拡張ありきの記述を削除、③Architecture Testの中心を文字列検索からimport解析（AST等）へ変更、④テスト戦略から実装構文（if/elif等）への恒久固定を撤回し振る舞いのみを検証対象化、⑤Definition of Doneから「0 diff」表現を削除し「ベースライン件数のまま全件PASS」＋Release Review時の`git diff --name-status`/`git status --short`確認へ変更）
更新日：2026-07-15（ChatGPT Architecture Review「Approve with Minor Corrections」反映：①「Evaluatorは必ず呼び出される」という契約範囲を超えた表現を削除し、保証範囲を「呼び出された場合の戻り値契約」に限定、②「通知対象となるAlertが存在しない」という表現を「入力されたRetryAlertが通知対象となる状態ではない」へ修正（入力オブジェクト自体は常に存在するため）。9章`NO_NOTIFICATION`の意味を最終確定。Design Freeze実施）
作成者：Claude Code（Architecture Designドラフト・Review指摘反映・Documentation）／ChatGPT（Architecture Review）／ユーザー（最終承認・Design Freeze確定）
状態：**Design Freeze（実装未着手）**
分類：**Architecture Release**（development_workflow.md 6章・7章）

> 本ドキュメントはユーザー指示「Release 6.6 Architecture Design」に基づく設計のみを目的とする。**実装は行わない**。
> 依拠する既定方針：`docs/design/retry_alert_foundation.md` 2.3節（`retry_notification → retry_alert`が許可される正しい依存方向であることを先行合意済み）、`docs/design/retry_alert_foundation.md` 7章（アラートの抑制・重複排除・レート制限は「将来Notification側の責務」と位置づけ済み）。

---

## 1. 概要

Retry Notification Foundationは、`Metrics → Monitoring → Alert → Notification`という一方向パイプラインの4段目にあたる、独立した新規パッケージ`src/retry_notification/`である。

v6.5.0の`RetryAlertEvaluator`が「`RetryHealthReport`からアラートを出すべきかどうかを判定する」だけの**Judgment Only Foundation**であったのと同じ位置づけで、本Foundationは「`RetryAlert`から通知すべきかどうかを判定する」だけの**Judgment Only Foundation**とする。

- 実際の通知送信（Slack／メール／Webhook等）は行わない
- Runtime・Metrics・Monitoringには一切依存せず、依存するのは`retry_alert`のみ
- 出力は「通知すべきかどうか」を表すImmutableなDomain Object（`RetryNotificationDecision`）1種類のみ
- 状態を持たない・副作用を持たないStateless Pure Functionとして実装する

---

## 2. 背景

- v6.3.0（Metrics：数える）→ v6.4.0（Monitoring：問題かどうか判断する）→ v6.5.0（Alert：知らせるべきかどうか判断する）という責務の連鎖が既に確立している。
- v6.5.0設計書2.3節は、将来のRetry Notification Foundationのimport依存として`retry_notification → retry_alert`を「正しい・意図された」方向として明記済みである。
- v6.5.0設計書7章は、アラートの抑制・重複排除・レート制限を「状態を要するためStatelessという要件と両立しない。将来Notification側の責務とする」と明記済みである。ただしこれは「Notification領域のいずれ担うべき責務」を示したものであり、本Release（最小のNotification Decision Foundation）に含めることを意味しない。
- 現在のパイプライン構成は以下のとおりで固定されている。

```
CLI（scripts/run_retry_runtime.py）
    → RetryRuntimeLock → RetryRuntimeShutdown → RetryRuntimeLoop
         → RetryRuntimeOrchestrator → RetryManager（retry_engine）
              → RetryRuntimeCycleLogger → .run/retry_runtime_log.jsonl

RetryRuntimeLogReader（v6.3.0）→ RetryMetricsCalculator（v6.3.0）→ RetryMetricsSnapshot（v6.3.0）
    → RetryHealthEvaluator（v6.4.0）→ RetryHealthReport（v6.4.0）
    → RetryAlertEvaluator（v6.5.0）→ RetryAlert（v6.5.0）
```

`RetryAlert`は、v6.5.0時点では生成されるだけで消費者が存在しない、パイプライン最下流の構造化データである。

---

## 3. 目的

1. 独立パッケージ`src/retry_notification/`を新設し、`RetryAlert`（v6.5.0の出力）**のみ**を入力として受け取れるようにする
2. 受け取った`RetryAlert`から、固定対応表に基づき通知要否（`RetryNotificationStatus`のEnum）を判定できるようにする
3. 判定結果を呼び出し元へ返すだけの、副作用のないライブラリとして提供する（実送信・CLI表示は対象外）
4. 将来の送信処理（Message生成・Channel選択・実送信）が本Foundationの出力を消費できる、明確な出力契約を確立する

**明示的にGoalとしないもの**（14章・15章で詳述）：実際の通知送信、メッセージ生成、チャネル選択、抑制・重複排除・レート制限、Runtime／Composition Root Wiring、CLI表示。

---

## 4. Release分類

### 4.1 Fast Track Checklist該当確認

| 条件 | 該当有無 | 内容 |
|---|---|---|
| Public API変更 | なし | 既存クラスのシグネチャ変更なし |
| Constructor変更 | なし | 既存クラスのConstructor変更なし |
| Composition Root変更 | なし | `RetryCompositionRoot`は無改修（消費者不在の先行実装） |
| **Layer変更** | **あり** | 新規パッケージ`src/retry_notification/`を新設する |
| **Dependency変更** | **あり（新規import）** | `retry_notification`が`retry_alert`を新規importする |
| 永続化変更 | なし | 新しい永続化アーティファクトは発生しない |
| Event変更 | なし | 該当なし |
| 外部I/O変更 | なし | 通知送信（Slack／メール等）は対象外（Foundation First） |

**結論**：Layer変更・Dependency変更の2条件に該当するため、Fast Track候補条件（development_workflow.md 7章）を満たさない。v6.3.0（Metrics）・v6.4.0（Monitoring）・v6.5.0（Alert）と同じ理由により、本Releaseも**Architecture Release**として扱う。

Development Workflow 12章「Claude Codeは分類を最終確定させない」に従い、最終確定はChatGPTのArchitecture Reviewを経て行う（本文書は2回のReview「Request Changes」「Approve with Minor Corrections」を経て確定済み）。

---

## 5. 現在のArchitecture

```
RetryHealthReport（v6.4.0の出力）
    │
    ▼
RetryAlertEvaluator.evaluate(report) -> RetryAlert（v6.5.0の出力。本Foundationの唯一の入力）
    │
    ▼
（呼び出し元は v6.5.0 時点では未定。消費者不在の先行実装）
```

`retry_alert`パッケージは`retry_notification`の存在を一切知らない。逆方向の依存は構造的に存在しない。

---

## 6. 提案Architecture

### 6.1 データフロー（実行順序）

```
Runtime実行 → Logger記録 → Metrics集計 → Monitoring判定 → Alert判定 → Notification判定（本Foundation） → 実送信（将来）
```

### 6.2 import依存方向（データフローと逆向き）

```
Notification（本Foundation） → Alert → Monitoring → Metrics
```

Release 6.6時点の実際のimport依存：

```
retry_notification → retry_alert
```

- `retry_notification` → `retry_alert`（`RetryAlert` / `RetryAlertLevel`型の参照のみ）＋標準ライブラリ（`enum` / `dataclasses` / `__future__`）
- `retry_notification`は`retry_monitoring` / `retry_metrics` / Runtime系（`retry_runtime_lock` / `retry_runtime_shutdown` / `retry_runtime_loop` / `retry_runtime_orchestrator` / `retry_runtime_logging`） / `retry_engine` / `retry_composition`のいずれもimportしない
- `retry_alert`は`retry_notification`をimportしない（**逆依存の禁止**）
- 新しい外部パッケージ（pip）は追加しない
- `src/retry_alert/__init__.py`は既に`RetryAlert` / `RetryAlertLevel` / `RetryAlertEvaluator`を`__all__`でexport済みのため、既存ファイルの変更は不要

### 6.3 パッケージ構成

```
src/retry_notification/
    __init__.py                     # 公開API定義
    retry_notification_status.py    # RetryNotificationStatus（Enum）
    retry_notification_decision.py  # RetryNotificationDecision（frozen dataclass）
    retry_notification_evaluator.py # RetryNotificationEvaluator（RetryAlert → RetryNotificationDecision）
```

命名・粒度は`src/retry_alert/`（`retry_alert_level.py` / `retry_alert.py` / `retry_alert_evaluator.py`）と対称にする。「Enum 1ファイル」「値オブジェクト1ファイル」「Evaluator 1ファイル」という既存の分割方針をそのまま踏襲する。

---

## 7. 責務境界

| コンポーネント | 責務 | 依存 |
|---|---|---|
| `RetryNotificationStatus`（新規） | 通知要否の結果を表すEnum | なし（標準ライブラリのみ） |
| `RetryNotificationDecision`（新規） | 判定結果を表すImmutableな値オブジェクト。`status`のみを保持し、生成後は変更されない。`RetryAlert`や`RetryAlertLevel`は保持・複製しない | `RetryNotificationStatus` |
| `RetryNotificationEvaluator`（新規） | `RetryAlert.level`を10章の固定対応表に従って`RetryNotificationDecision`へ変換するのみ（閾値判定は行わない）。ファイルI/O・送信・Runtime参照・Alert内部状態への書き込みは一切行わない | `retry_alert`（`RetryAlert` / `RetryAlertLevel`型） |
| `RetryAlert` / `RetryAlertLevel` / `RetryAlertEvaluator`（v6.5.0） | 無変更。本Releaseからは`RetryAlert`と`RetryAlertLevel`の型のみ参照され、`RetryAlertEvaluator`は参照も依存もされない | — |
| Runtime Pipeline全体・`retry_metrics`・`retry_monitoring` | 無変更。本Foundationからは存在すら参照されない | — |

「判定（`RetryNotificationEvaluator`）」と「実行（将来の送信処理）」を別レイヤーへ分離するのは、v6.3.0〜v6.5.0が確立した「判断する層」と「実行する層」の責務分離を、Notification段階でも維持するためである。

---

## 8. Domain Model

```python
# src/retry_notification/retry_notification_status.py
from __future__ import annotations
from enum import Enum


class RetryNotificationStatus(Enum):
    """RetryNotificationEvaluatorが判定する通知要否の結果。

    NO_NOTIFICATION: RetryNotificationEvaluator.evaluate()が正常に実行・完了
                      した結果、入力されたRetryAlertが通知対象となる状態では
                      ないことを表す正常系の明示値。評価失敗・入力不足・
                      未対応値・処理スキップ・Evaluator未実行のいずれも意味
                      しない（9章）。
    NOTIFY: 入力されたRetryAlertが通知対象となる状態であることを表す。
    """
    NO_NOTIFICATION = "NO_NOTIFICATION"
    NOTIFY = "NOTIFY"
```

```python
# src/retry_notification/retry_notification_decision.py
from __future__ import annotations
from dataclasses import dataclass

from .retry_notification_status import RetryNotificationStatus


@dataclass(frozen=True)
class RetryNotificationDecision:
    """RetryNotificationEvaluatorの判定結果を表すImmutableな値オブジェクト。

    statusのみを保持する。RetryAlert・RetryAlertLevelは保持・複製しない
    （Foundation First。呼び出し元は既にRetryAlertを保持しているため、
    Decision側で複製保持する必要性が薄い。7章・14章参照）。
    """
    status: RetryNotificationStatus
```

```python
# src/retry_notification/retry_notification_evaluator.py
from __future__ import annotations

from retry_alert import RetryAlert, RetryAlertLevel

from .retry_notification_decision import RetryNotificationDecision
from .retry_notification_status import RetryNotificationStatus


class RetryNotificationEvaluator:
    """RetryAlertからRetryNotificationDecisionを計算するだけの、状態を持たないコンポーネント。"""

    def evaluate(self, alert: RetryAlert) -> RetryNotificationDecision:
        """
        alert（RetryAlert、唯一の入力）のlevelを、10章の固定対応表に従って
        RetryNotificationStatusへ変換し、RetryNotificationDecisionを返す。

        - NONE / WARNING / CRITICAL 以外のlevelが渡された場合、
          フォールバックせずValueErrorを送出する（12章 Fail Fast方針）
        """
        ...
```

`RetryNotificationDecision`は`RetryHealthReport`（v6.4.0）・`RetryAlert`（v6.5.0）と同じ設計判断（`frozen=True`、setter／update()を持たない）を踏襲する。

---

## 9. NO_NOTIFICATIONの厳密な意味

```text
RetryNotificationStatus.NO_NOTIFICATIONは、
RetryNotificationEvaluator.evaluate()が正常に実行・完了した結果、
入力されたRetryAlertが通知対象となる状態ではないことを表す
正常系の明示値である。

評価失敗、入力不足、未対応値、処理スキップ、
またはEvaluator未実行を意味しない。
```

以下のいずれの意味も持たない。

| `NO_NOTIFICATION`が意味しないもの | 理由 |
|---|---|
| 評価の失敗 | `evaluate()`が正常に完了した結果として`NO_NOTIFICATION`が返る。例外的状況の結果ではない |
| データ不足 | `RetryAlert`は`RetryAlertEvaluator`が既に確定させたImmutableな値であり、Notification層に到達する時点でデータ不足という状態は存在しない |
| 未対応の値 | 未対応の`RetryAlertLevel`は`NO_NOTIFICATION`へフォールバックしない（12章）。「不明」と「通知対象ではない」は明確に区別する |
| 処理のスキップ | `evaluate()`が呼び出された場合、`alert.level`の値に関わらず必ず具体的な`RetryNotificationDecision`（または例外）を生成する。判定処理自体を省略することはない |
| Evaluator未実行 | 本Foundationが保証するのは「`evaluate()`が呼び出された場合の戻り値契約」のみである（10.1節）。`evaluate()`自体が呼び出されない状態と、呼び出された結果として`NO_NOTIFICATION`が返る状態は、型レベルで明確に異なる |

**「Alertが存在しない」という表現は用いない**：`RetryNotificationEvaluator.evaluate()`への入力として`RetryAlert`オブジェクト自体は常に存在する。`NO_NOTIFICATION`が表すのは「入力された`RetryAlert`が通知対象となる状態ではない」ことであり、「Alertオブジェクトが存在しない」ことではない。

将来の送信処理（Message生成・Channel選択）は、`status == RetryNotificationStatus.NO_NOTIFICATION`の場合、通知を送信してはならない。これは本Foundationが保証する契約ではなく（本Foundationは通知を行わないため）、**将来の送信処理側が遵守すべき呼び出し契約**として、ここに明記しておく。

---

## 10. Evaluator契約

### 10.1 保証範囲

```text
RetryNotificationEvaluator.evaluate()が呼び出された場合、
既知のRetryAlertLevelに対しては必ずRetryNotificationDecisionを返す。

未対応値の場合のみValueErrorを送出する。
```

本Foundationが保証するのは、あくまで「`evaluate()`が呼び出された場合」の戻り値契約である。呼び出し元が`evaluate()`を実際に呼び出すかどうかは、本Foundationの契約範囲に含まれない（`retry_notification`は自身を呼び出す消費者を持たない、消費者不在の先行実装であるため）。

### 10.2 性質

- 唯一の入力は`RetryAlert`
- Stateless（内部状態を持たない）
- Pure Function（同一の`RetryAlert`を渡した場合、常に同一の`RetryNotificationDecision`、または常に同一の例外を返す）
- 外部I/Oを行わない
- 閾値判定を行わない。11章の固定対応表に従って変換するだけの単純な写像である

---

## 11. 変換規則

| RetryAlertLevel（入力） | RetryNotificationStatus（出力） |
|---|---|
| `NONE` | `NO_NOTIFICATION` |
| `WARNING` | `NOTIFY` |
| `CRITICAL` | `NOTIFY` |

この対応表は実装の詳細ではなく、本Foundationの**設計契約**である。`WARNING`と`CRITICAL`はいずれも`NOTIFY`へ変換し、重大度による区別はNotification層では行わない（重大度が必要な将来の消費者は、呼び出し元が保持する元の`RetryAlert.level`を直接参照する想定。17章参照）。`RetryAlertLevel`が既に持つ意味をNotification側で複製する新しいPriority語彙（例：`NORMAL`/`URGENT`）は導入しない。

---

## 12. Fail Fast方針

- `RetryNotificationEvaluator`は、11章の対応表にある**既知の3つの`RetryAlertLevel`のみ**を明示的に変換する
- いずれにも一致しない場合、`NO_NOTIFICATION`・`NOTIFY`のどちらへもフォールバックせず、`ValueError`を送出する
- 安全側として`NOTIFY`へフォールバックする案は、過剰通知（Alert Fatigue）を招き、「対応漏れ」という契約違反を「通知した」という一見正常な結果で隠蔽するため採用しない
- 安全側として`NO_NOTIFICATION`へフォールバックする案は、対応漏れを正常系（通知対象ではない）に偽装し、将来重大な新Levelが追加された際に無言で通知が止まるという、より危険なリスクを伴うため採用しない
- 実装（if/elif／match文／辞書等）の具体的な文法構造は本設計書では固定しない。既存の`RetryAlertEvaluator`（v6.5.0）との一貫性からif/elif方式を実装案として推奨するが、テストが検証するのはあくまで入出力の振る舞いである（16章）

---

## 13. import依存方向

許可：

```text
retry_notification → retry_alert
```

禁止：

```text
retry_alert → retry_notification
retry_notification → retry_monitoring
retry_notification → retry_metrics
retry_notification → Runtime系（retry_runtime_lock / retry_runtime_shutdown / retry_runtime_loop / retry_runtime_orchestrator / retry_runtime_logging）
retry_notification → RetryManager（retry_engine）
retry_notification → Logger
retry_notification → CLI（scripts/）
retry_notification → 外部ライブラリ（pip）
```

`retry_alert`が公開している型（`RetryAlert` / `RetryAlertLevel`）を経由した間接的な意味上の参照は許容される。検証方法は16章参照。

---

## 14. In Scope

- 新規パッケージ`src/retry_notification/`
  - `retry_notification_status.py` — `RetryNotificationStatus`（`NO_NOTIFICATION` / `NOTIFY`のEnum）
  - `retry_notification_decision.py` — `RetryNotificationDecision`（frozen dataclass、`status`のみ）
  - `retry_notification_evaluator.py` — `RetryNotificationEvaluator`（`RetryAlert → RetryNotificationDecision`）
  - `__init__.py` — 公開API定義
- 新規テスト `tests/test_e2e_v6_6_0_retry_notification_foundation.py`（実装Releaseで作成）

---

## 15. Out of Scope

- 実際の通知送信（Slack／メール／Webhook等への外部I/O）
- メッセージ生成・チャネル選択
- 重複排除・通知抑制・レート制限・Cooldown（状態を要するため、本Stateless Foundationとは責務が異なる。21章）
- Recovery通知・履歴の永続化
- Runtime Pipeline・`retry_metrics`・`retry_monitoring`・`retry_alert`への変更
- `RetryCompositionRoot`への配線（消費者不在の先行実装のため）
- CLI表示・ダッシュボード化

---

## 16. テスト戦略

実装Release（次工程）で以下を実施する想定。本文書はテスト方針の確定のみを行い、テストコード自体はまだ作成しない。

### Domain Object

- `RetryNotificationStatus`が`NO_NOTIFICATION` / `NOTIFY`の2値のみを持つことの確認
- `RetryNotificationDecision`がfrozen dataclassであり、フィールド再代入が`FrozenInstanceError`になることの確認
- `RetryNotificationDecision`が`status`フィールドのみを保持することの確認
- equalityの確認
- importが正常にできること（`__all__`確認）

### Evaluator（振る舞いを検証し、実装構文は固定しない）

- `RetryAlert(level=NONE)` → `RetryNotificationDecision(status=NO_NOTIFICATION)`の確認
- `RetryAlert(level=WARNING)` → `RetryNotificationDecision(status=NOTIFY)`の確認
- `RetryAlert(level=CRITICAL)` → `RetryNotificationDecision(status=NOTIFY)`の確認
- 未対応値が`ValueError`になることの確認
- 未対応値が`NO_NOTIFICATION`へフォールバックしないことの確認
- 未対応値が`NOTIFY`へフォールバックしないことの確認
- 同一入力に対する決定性（Stateless Pure Functionの確認：複数回呼び出し・複数インスタンス間での結果一致）
- 入力の`RetryAlert`オブジェクトを変更しないことの確認
- Evaluatorインスタンス自体が呼び出し間で状態を保持しないことの確認

### Architecture（依存方向・外部I/O禁止）

主たる保証手段はimport解析（AST等）とする。

- `src/retry_notification/`配下の各モジュールのimport文を解析し、許可される自作パッケージが`retry_alert`のみであること、標準ライブラリ以外の外部ライブラリをimportしていないことを確認
- 同様の解析で`retry_monitoring` / `retry_metrics` / Runtime系 / `RetryManager` / Logger / CLIをいずれもimportしていないことを確認
- `src/retry_alert/`配下の各モジュールのimport文を解析し、`retry_notification`をimportしていないこと（逆依存禁止）を確認
- 文字列検索（`open(` / `pathlib.Path`等の不在確認）は補助的チェックとしてのみ用いる場合がある。コメント・docstring内の誤検出や動的importの検知不能という限界を認識した上で、主要な保証手段としては扱わない

### Regression

- 既存Regression Suite（v5.9.0〜v6.5.0）が**ベースライン件数のまま全件PASSする**こと
- 既存Regressionテストファイル自体に意図しない変更がないこと
- 既存production codeの無改修確認は、恒久的なE2Eテストには含めず、**Release Review時**に`git diff --name-status` / `git status --short`で個別に確認する

---

## 17. 代替案比較

### 戻り値の型

| 案 | 判定 | 理由 |
|---|---|---|
| `None` | 却下 | Optionalは呼び出し元に`is not None`分岐を強い、Total Function契約を崩す |
| `bool`のみ | 却下 | 意味が弱く、既存Evaluatorの戻り値規約（`evaluate() -> frozen dataclass`）と不整合 |
| Enumを裸で返す | 却下 | dataclass wrapがないと将来の拡張性・既存パターンとの対称性を失う |
| **frozen dataclass（採用）** | 採用 | `RetryHealthReport` / `RetryAlert`と同型。Total Function・Immutabilityの両方を満たす |
| `RetryAlertLevel`をそのまま返す | 却下 | Alert層の語彙をNotification層のAPIとして再露出し、意味の複製・責務混同を招く |
| 例外で「通知なし」を表す | 却下 | 「通知なし」は正常系の結果であり、例外（異常系）で表すのは不適切 |

### Decision Objectの最小構造

| 案 | 判定 | 理由 |
|---|---|---|
| `should_notify: bool`のみ | 却下 | Enumを経由しないため既存慣習との対称性が弱く、将来の語彙拡張時に型変更が破壊的になる |
| **`status: RetryNotificationStatus`のみ（採用）** | 採用 | `RetryHealthReport(status)` / `RetryAlert(level)`と同型の最小構成 |
| `should_notify: bool` + `alert: RetryAlert` | 却下 | Alertが`source_report`を先送りした前例と矛盾。情報の重複保持 |
| `status: RetryNotificationStatus` + `alert: RetryAlert` | 却下 | 同上。呼び出し元が既に`RetryAlert`を保持しているため不要な複製 |
| `RetryAlertLevel`を複製したフィールドを追加 | 却下 | Alert Levelの意味を不用意に複製しないという方針に抵触 |

### 実装方式

| 案 | 判定 | 理由 |
|---|---|---|
| **Stateless Evaluatorクラス（採用）** | 採用 | `RetryHealthEvaluator` / `RetryAlertEvaluator`と対称 |
| モジュールレベル関数 | 却下 | 既存クラス形式との一貫性を優先 |
| Policy Object（DIで変換ルール注入） | 却下 | 固定写像以外の要求がなく、現時点ではYAGNI |
| Factory | 却下 | 生成物が1種類のみで複雑さに見合わない |
| `RetryAlert`へメソッド追加 | 却下 | Alertの責務拡張につながり、Alert層がNotificationの存在を知らないという境界と矛盾する |
| `RetryAlertEvaluator`へ通知判定を追加 | 却下 | 判定（Alert）と判定（Notification）の責務分離をパッケージ内で握り潰すことになる |

### スコープ

| 案 | 判定 | 理由 |
|---|---|---|
| **判定のみ（採用）** | 採用 | Metrics/Monitoring/Alertと同型のFoundation First継続 |
| 判定＋送信チャネル決定 | 却下（将来Release） | 実送信境界に抵触。関心事の混在 |
| 判定＋メッセージ生成 | 却下（将来Release） | 消費者の要件が固まってから設計する方が手戻りが少ない |
| 判定＋実送信 | 却下 | 外部I/O変更に該当し、単独でも十分大きいArchitecture Reviewを要する |
| 抑制・重複排除まで含める | 却下 | 状態を要するため、本FoundationのStateless要件と両立しない |

### Enum名（`NONE` / `NOTIFY` と `NO_NOTIFICATION` / `NOTIFY` の比較）

| 案 | 長所 | 短所 |
|---|---|---|
| `NONE` / `NOTIFY` | 短い。`RetryAlertLevel.NONE`と表記を揃えられる | `RetryAlertLevel.NONE`と`RetryNotificationStatus.NONE`という別の型に属する同名メンバーが生まれ、型情報なしに読み違えるリスクがある |
| **`NO_NOTIFICATION` / `NOTIFY`（採用）** | 名前自体がドメイン上の意味を説明する。`RetryAlertLevel`とのメンバー名衝突がない | やや長い（許容範囲） |

---

## 18. 却下案

| # | 却下した設計 | 理由 |
|---|---|---|
| 1 | `level==NONE`相当の場合に`None`を返す | Total Function契約に反する |
| 2 | `RetryNotificationStatus.SKIP`という命名 | 「処理スキップ」を連想させ、「正常評価の結果として通知対象ではない」という意味と混同する（Request Changes指摘） |
| 3 | `RetryNotificationStatus.NONE`という命名（Alert語彙の再利用） | `RetryAlertLevel.NONE`と紛らわしく、別の型に属する同名メンバーの混同を招く |
| 4 | Decision Objectへ`RetryAlert`を保持する | Foundation First・情報重複回避の原則に反する |
| 5 | WARNING/CRITICALを別々のNotifyステータスへ分ける | 本Foundationの責務を超え、Alert Levelの意味を複製することになる |
| 6 | 未対応Levelを`NOTIFY`へ安全側フォールバック | Alert Fatigueを助長し、対応漏れを隠蔽する |
| 7 | 未対応Levelを`NO_NOTIFICATION`へフォールバック | 対応漏れを正常系に偽装し、重大な新Levelが無言で握りつぶされるリスクを伴う |
| 8 | Enum採用理由に「将来`SUPPRESSED`等を追加できる」ことを含める | 将来Architecture（Enum拡張か別型導入か）を本Releaseの時点で固定してしまう（Request Changes指摘、21章） |
| 9 | 「Evaluatorは必ず呼び出される」という契約表現 | 呼び出し元が実際に呼ぶことまでは本Foundationが保証できない（Approve with Minor Corrections指摘） |
| 10 | 「通知対象となるAlertが存在しない」という表現 | 入力の`RetryAlert`オブジェクト自体は常に存在するため不正確（Approve with Minor Corrections指摘） |
| 11 | `match`文への統一、または文法構造をテストで固定すること | 検証すべきは入出力の振る舞いであり、実装の文法構造ではない |
| 12 | `open(`等の文字列検索をArchitecture保証の中心にすること | 誤検出・動的import検知不能という限界があり、AST解析の方が構造的に確実（Request Changes指摘） |
| 13 | `Policy` / `Factory` / `Planner`という命名 | 責務（固定対応表による単純な写像）に対して過大／誤解を招く命名であり、`Evaluator`が既存2クラスとの対称性の観点で最も妥当 |

---

## 19. Known Issues

実装未着手のため、既存Architecture Guard（v5.9.0〜v6.5.0のE2Eテスト）への影響は本Release時点では発生していない（新規Known Issueなし。2026-07-15時点の最新は引き続き`[KI-29]`）。

---

## 20. Technical Debt

- `RetryNotificationDecision`は`WARNING`/`CRITICAL`の区別を保持しないため、将来チャネル選択等で重大度が必要になった場合、呼び出し元が保持する元の`RetryAlert`を別途参照する必要がある
- 抑制・重複排除・レート制限が本Releaseに含まれないため、本Foundationだけを消費する将来の送信処理が素朴に実装されると、同一の`CRITICAL`状態が続く限り毎サイクル`NOTIFY`判定が繰り返される
- Decision単体では「何を」「どこへ」通知すべきかの情報を持たないため、実際に送信可能にするには少なくとも2段階（Message生成・Channel選択）の後続Foundationが前提条件となる

---

## 21. 将来拡張

```
RetryNotificationDecision（本Foundation）
    ↓
RetryNotificationMessage（将来）
    ↓
RetryNotificationChannel（将来）
    ↓
RetryNotificationSender（将来。実送信・外部I・Oを含む）
```

**Suppression（抑制）との境界は本Releaseの時点では未確定とする**：将来、重複排除・レート制限・Cooldown等のSuppression機能を実装する際、以下のどちらのArchitectureになるかは決定していない。

1. `RetryNotificationStatus`へ新しい値（例：`SUPPRESSED`）を追加する拡張
2. `RetryNotificationDecision`とは別の型（例：`RetryDeliveryDecision` / `RetrySuppressionDecision`）を新設し、`RetryNotificationDecision`を入力として状態付きの追加判定を行う

どちらを選ぶかは、Suppressionを実際に設計するReleaseで、要件が明らかになった時点で改めてArchitecture Reviewを経て決定する。本Releaseはこの決定を先取りしない。

---

## 22. 実装予定ファイル

**新規production code**（次工程・実装Releaseで作成。本Design Freeze時点では未作成）

- `src/retry_notification/__init__.py`
- `src/retry_notification/retry_notification_status.py`
- `src/retry_notification/retry_notification_decision.py`
- `src/retry_notification/retry_notification_evaluator.py`

**新規テスト**（同上）

- `tests/test_e2e_v6_6_0_retry_notification_foundation.py`

**変更なし（既存コード無改修方針）**

- `src/retry_metrics/`・`src/retry_monitoring/`・`src/retry_alert/`（`__init__.py`含む。既存exportで足りるため変更不要）
- Runtime Pipeline全体・`RetryCompositionRoot`・`scripts/`
- 既存テストファイル一式

---

## 23. Definition of Done

- [ ] `src/retry_notification/`実装完了（3ファイル＋`__init__.py`）
- [ ] 新規E2Eテスト全PASS
- [ ] 既存Regression Suite（v5.9.0〜v6.5.0）がベースライン件数のまま全件PASSする
- [ ] 既存Regressionテストファイルに意図しない変更がない
- [ ] 依存方向テスト（import解析による、`retry_notification → retry_alert`のみ・逆依存なし・Monitoring/Metrics/Runtime系への非import確認）PASS
- [x] `docs/design/retry_notification_foundation.md`作成・ChatGPT Architecture Review「Approve with Minor Corrections」・Design Freeze
- [ ] 人間の実装承認
- [ ] Code Review（ChatGPTによる実装差分レビュー）
- [ ] `docs/architecture.md` / `docs/ROADMAP.md` / `docs/CHANGELOG.md`反映
- [ ] Release Reviewにおいて`git diff --name-status` / `git status --short`で既存コード無改修を確認
- [ ] commit／push（人間承認後）

---

## 24. Design Freeze

このArchitecture DesignはChatGPT Architecture Reviewで**Approve with Minor Corrections**となり、指摘事項（9章`NO_NOTIFICATION`の意味の精緻化、10.1節Evaluator保証範囲の限定）を反映した。

Release 6.6の実装は、このDesign Freezeされた設計に従う。

実装中に以下の変更が必要になった場合は、実装を停止してArchitecture Reviewへ戻る。

- Public API変更
- Enumメンバー変更
- Decision Objectのフィールド変更
- import依存方向変更
- 実送信や外部I/Oの追加
- Runtime／Composition Rootへの接続
- Suppression／重複排除等の追加
- 既存production codeの変更

---

## Status

> **2026-07-15追記（Release 6.7 Documentation Updateにて是正）**：本Status章は、Release 6.6の
> 実装・テスト・commit完了後も未更新のまま「実装着手（未着手）」以下が`[ ]`のまま残っていた
> ドキュメント記載漏れであることが判明した。`docs/CHANGELOG.md`「[v6.6.0]」セクションに、
> 新規E2E135/135 PASS・既存Regression691/691 PASS・commit `7c77eef`（`feat(v6.6.0): add Retry
> Notification Foundation`、mainへpush済み）という完了実績が既に記録されている。以下は、この
> **Release 6.6完了実績に基づくStatus記載漏れの是正**である。Release 6.6の設計内容・Public API・
> 責務・Technical Debtはいずれも変更していない。新規Known Issueの追加もない。

- [x] Architecture Designドラフト作成（Claude Code）
- [x] ChatGPT Architecture Review 1回目「Request Changes」・指摘反映（`SKIP`→`NO_NOTIFICATION`改名、Enum採用理由修正、Architecture Test方針修正、テスト戦略修正、Definition of Done修正）
- [x] ChatGPT Architecture Review 2回目「Approve with Minor Corrections」・指摘反映（Evaluator保証範囲の限定、NO_NOTIFICATIONの意味の最終確定）
- [x] Design Freeze確定（本文書）
- [x] 実装着手（`src/retry_notification/`実装完了。記載漏れの是正）
- [x] Test Review（記載漏れの是正）
- [x] CHANGELOG／ROADMAP／architecture.md反映（`docs/CHANGELOG.md` [v6.6.0]セクション等に反映済み。記載漏れの是正）
- [x] Code Review（記載漏れの是正）
- [x] Release Review（記載漏れの是正）
- [x] commit／push（commit `7c77eef`としてmainへpush済み。記載漏れの是正）
