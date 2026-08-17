# Retry Observability Pipeline Foundation（Release 6.29.0）設計書

## 0. Status

Architecture Review：Claude Code単独設計 → Codex読み取り専用independent review（3ラウンド）を経て収束。

| ラウンド | Verdict | 指摘 |
|---|---|---|
| 1回目 | `ARCHITECTURE_APPROVABLE` | 初期設計に対する重点確認7項目を提示 |
| 2回目（Blocking/Major/Minor/Suggestion分類レビュー） | `NEEDS_REVISION` | Major 2件（message分岐のfail-open性・Report invariant欠如）、Minor 2件（5 package直接依存の位置づけ・CLI重複の未文書化）、Suggestion 2件 |
| 3回目（Major/Minor修正反映後の再レビュー） | `NEEDS_REVISION` | 新規Major 1件（zero-diff registry結論のoverbroad判定）、新規Minor 1件（CLI parity testのharness未確定） |
| 4回目（targeted re-review） | `APPROVED_WITH_SUGGESTIONS` | Blocking/Major 0件。Minor suggestion 1件（registry自己編集時の追加登録要否の明示） |

本設計書は、上記4ラウンドの収束結果を正式に記録するものである。**本Releaseの実装はまだ行われていない**（Design Docのみ）。

---

## 1. Background / Motivation

Release 6.3.0〜6.8.0で、以下5つの「消費者不在の先行実装（Foundation First）」パッケージが確立された：

```
retry_metrics（v6.3.0）
    → retry_monitoring（v6.4.0）
    → retry_alert（v6.5.0）
    → retry_notification（v6.6.0）
    → retry_notification_message（v6.7.0）
```

これらはいずれもStateless・Pure・Consumer-lessであり、`RetryRuntimeOrchestrator` / `RetryCompositionRoot` / Schedulerのいずれからも参照されていない（コード確認済み、grep 0件）。唯一の実消費者は`scripts/show_retry_notification.py`（v6.8.0）の`build_report()`であり、これはCLIスクリプト内のローカル関数として5パッケージを直接Composeしている。

この`build_report()`のロジックは、`src/`配下の再利用可能なコンポーネントとして存在しない。将来のRuntime Wiring（Retry Runtimeへこのパイプラインを実際に接続するRelease）がこの合成ロジックを必要とする際、CLIのprivateな実装をそのまま再利用することはできない。

本Releaseは、この合成ロジックを`src/`配下の独立した再利用可能パッケージとして抽出する、**Orchestration/Facade層のFoundation**である。

---

## 2. Goals

1. `metrics → monitoring → alert → notification → message`の5段階を、既存の公開Evaluator/Builderのみを用いて固定順序で呼び出す、単一の再利用可能なpure componentを確立する
2. 将来のRuntime Wiring Releaseが、CLIの実装を複製せずにこのパイプラインを利用できる土台を用意する
3. 既存6 Foundation（5パッケージ＋CLI）・Runtime・Schedulerを一切変更せず、Zero-Diffを維持する

## 3. Non-Goals（Out of Scope）

- `RetryRuntimeOrchestrator` / `RetryCompositionRoot` / `SchedulerEngine`の変更
- `scripts/show_retry_notification.py`の変更（CLIは本Releaseでは無改修のまま維持する。CLIとの合成ロジック重複は本Releaseの意図的なtemporary debtとする。次項4章参照）
- `.run/retry_runtime_log.jsonl`のJSON Schema変更
- ログファイルの実際の読み取り（I/O）。`RetryRuntimeLogReader`は本パッケージから一切importしない
- Sender／実際の通知送信（Slack／メール等）／外部I/O全般
- 既存5パッケージ（`retry_metrics` / `retry_monitoring` / `retry_alert` / `retry_notification` / `retry_notification_message`）の変更
- 具体的なChannel／Delivery destinationの導入（Release 6.29ではChannel Foundationは`ARCHITECTURE_BLOCKED`と判定済み。本Releaseはそれとは独立した別方向のFoundation）

---

## 4. CLIとの一時的重複（Temporary Debt）

`scripts/show_retry_notification.py::build_report()`は、本Releaseで新設する`RetryObservabilityPipeline.evaluate()`と実質的に同一の合成ロジック（Metrics→Health→Alert→Notification→Message）を、v6.8.0以来CLIローカルに保持し続ける。

- **本Releaseでは意図的にCLIを変更しない**（IN/OUT scopeにより明記）。これにより、Composition Rootに相当するロジックが一時的に2箇所（CLIローカル関数／本Facade）に存在する状態が発生する
- これは本Repositoryにおいて初めて許容する種類のtemporary debtであり、恒久化させてはならない
- **解消計画**：次Release（Wiring Release、未着手）で、`scripts/show_retry_notification.py::build_report()`を`RetryObservabilityPipeline.evaluate()`への薄い委譲へ置き換え、CLI側のCompositionロジックを削除する。この置き換えはCLI出力を変えないことをParity Testで担保する
- 本Releaseの時点で、CLIとFacadeの出力が意味的に同一であることをE2E内のParity Testで検証する（8章参照）。これにより「重複が正しく同期していること」を実装完了時点から保証し、Wiring Release側の置き換えを安全にする

---

## 5. Package

**Package名**：`src/retry_observability_pipeline/`

```
src/retry_observability_pipeline/
    __init__.py
    retry_observability_report.py       # RetryObservabilityReport（frozen dataclass）
    retry_observability_pipeline.py     # RetryObservabilityPipeline（Stateless Composer）
```

---

## 6. Public API

```python
# retry_observability_report.py
from __future__ import annotations

from dataclasses import dataclass

from retry_alert import RetryAlert
from retry_metrics import RetryMetricsSnapshot
from retry_monitoring import RetryHealthReport
from retry_notification import RetryNotificationDecision, RetryNotificationStatus
from retry_notification_message import RetryNotificationMessage


@dataclass(frozen=True)
class RetryObservabilityReport:
    """RetryObservabilityPipeline.evaluate()の結果を表すImmutableな値オブジェクト。"""

    metrics: RetryMetricsSnapshot
    health_report: RetryHealthReport
    alert: RetryAlert
    notification_decision: RetryNotificationDecision
    message: RetryNotificationMessage | None

    def __post_init__(self) -> None:
        status = self.notification_decision.status

        if status is RetryNotificationStatus.NOTIFY:
            if self.message is None:
                raise ValueError(
                    "RetryObservabilityReport: "
                    "status=NOTIFYの場合、messageはNoneであってはならない"
                )
            return

        if status is RetryNotificationStatus.NO_NOTIFICATION:
            if self.message is not None:
                raise ValueError(
                    "RetryObservabilityReport: "
                    "status=NO_NOTIFICATIONの場合、messageはNoneでなければならない"
                )
            return

        raise ValueError(
            f"RetryObservabilityReport: 未対応のRetryNotificationStatusです"
            f"（フォールバックしません）: {status!r}"
        )
```

```python
# retry_observability_pipeline.py
from __future__ import annotations

from retry_alert import RetryAlertEvaluator
from retry_metrics import RetryMetricsCalculator, RetryRuntimeLogRecord
from retry_monitoring import RetryHealthEvaluator, RetryHealthThresholds
from retry_notification import RetryNotificationEvaluator, RetryNotificationStatus
from retry_notification_message import RetryNotificationMessageBuilder

from .retry_observability_report import RetryObservabilityReport


class RetryObservabilityPipeline:
    """
    metrics -> monitoring -> alert -> notification -> messageの5段階を
    固定順序で呼び出すだけの、状態を持たないOrchestration/Facadeコンポーネント。
    """

    def __init__(self, thresholds: RetryHealthThresholds | None = None):
        self._metrics_calculator = RetryMetricsCalculator()
        self._health_evaluator = RetryHealthEvaluator(thresholds)
        self._alert_evaluator = RetryAlertEvaluator()
        self._notification_evaluator = RetryNotificationEvaluator()
        self._message_builder = RetryNotificationMessageBuilder()

    def evaluate(self, records: list[RetryRuntimeLogRecord]) -> RetryObservabilityReport:
        """
        records（既にパース済みのRetryRuntimeLogRecordのリスト、唯一の入力）から、
        5段階の既存Evaluator/Builderを固定順序で呼び出し、RetryObservabilityReportを返す。

        - ファイルI/Oは一切行わない（RetryRuntimeLogReaderは使用しない）
        - 各Evaluator/Builderが送出する例外（ValueError等）はいずれも無変換のまま
          呼び出し元へ伝播する（本コンポーネント自身はtry/exceptを持たない）
        - notification_decision.statusがNOTIFYの場合のみMessageBuilder.build()を呼ぶ。
          NO_NOTIFICATIONの場合は呼ばずmessage=Noneとする。未対応のstatusは
          フォールバックせずValueErrorを送出する（Fail Fast契約）
        """
        metrics = self._metrics_calculator.calculate(records)
        health_report = self._health_evaluator.evaluate(metrics)
        alert = self._alert_evaluator.evaluate(health_report)
        notification_decision = self._notification_evaluator.evaluate(alert)

        status = notification_decision.status
        if status is RetryNotificationStatus.NOTIFY:
            message = self._message_builder.build(notification_decision)
        elif status is RetryNotificationStatus.NO_NOTIFICATION:
            message = None
        else:
            raise ValueError(
                f"RetryObservabilityPipeline: 未対応のRetryNotificationStatusです"
                f"（フォールバックしません）: {status!r}"
            )

        return RetryObservabilityReport(
            metrics=metrics,
            health_report=health_report,
            alert=alert,
            notification_decision=notification_decision,
            message=message,
        )
```

```python
# __init__.py
from .retry_observability_pipeline import RetryObservabilityPipeline
from .retry_observability_report import RetryObservabilityReport

__all__ = [
    "RetryObservabilityReport",
    "RetryObservabilityPipeline",
]
```

---

## 7. Dependency Direction

```
retry_observability_pipeline
    ├─→ retry_metrics
    ├─→ retry_monitoring
    ├─→ retry_alert
    ├─→ retry_notification
    └─→ retry_notification_message
```

### 7.1 Orchestration/Facade層固有の契約（one-hop-back規律の例外）

既存5パッケージは、それぞれ「直前の1つのlayerの出力型のみに依存する」という"one-hop-back"規律を守っている（例：`retry_notification_message`は`retry_notification`のみに依存し、`retry_alert` / `retry_monitoring` / `retry_metrics`への直接依存は明示的に禁止されている。`docs/design/retry_notification_message_foundation.md`15章）。

`retry_observability_pipeline`はこの規律の「例外」ではなく、**Orchestration/Facade層という別カテゴリの契約**として位置づける。この契約は以下の通り：

- Orchestration/Facade層は、既存の判断（Judgment）・値構築（Value Building）ロジックを一切追加せず、既存Foundationの呼び出し順序を固定するだけの責務に限定される場合に限り、複数の下位Foundationへ直接依存してよい
- 本Repositoryにはこの契約の先行事例が既に存在する：`ArticleFeaturedMediaOrchestrator`（v6.14.0、`src/article_featured_media_orchestration/`）は、`generate → upload → bind`という固定順序で複数の既存Foundationを直接呼び出すOrchestratorとして正式にApprovedされている
- この契約は「他のFoundationが自由に多段依存してよい」という一般化ではない。既存5パッケージそれぞれの one-hop-back 規律は本Releaseでも一切変更しない

### 7.2 Reverse Dependency禁止

既存5パッケージ（`retry_metrics` / `retry_monitoring` / `retry_alert` / `retry_notification` / `retry_notification_message`）のいずれも、`retry_observability_pipeline`をimportしてはならない。この逆依存の禁止をE2Eのソースコード走査（AST解析）で機械的に保証する（8章参照）。

### 7.3 禁止する依存

- `retry_metrics.RetryRuntimeLogReader`（I/O。本パッケージはこれを一切importしない）
- Runtime系（`retry_composition` / `retry_runtime_*` / `RetryManager`）
- `RetryCompositionRoot`
- `scheduler`
- CLI（`scripts/`）
- Logger／JSONL
- 外部pipライブラリ

**禁止契約の対象範囲（Codex read-only review 5回目の指摘への回答）**：禁止するのは`RetryRuntimeLogReader`の直接参照・生成・利用、およびそれに伴うfile I/Oである。`retry_metrics`パッケージroot（`from retry_metrics import ...`）からのimportは`retry_metrics.__init__.py`が`RetryRuntimeLogReader`を再exportしている都合上、Pythonのmodule loading機構としてtransitiveに`RetryRuntimeLogReader`のモジュール自体をロードするが、これは許容する（`RetryRuntimeLogReader`を参照・インスタンス化・呼び出ししない限り、ロードされるだけでは禁止契約に抵触しない）。現行のPipeline実装・E2Eの直接Reader import禁止guard・no-I/O guardはいずれも変更しない。

---

## 8. Validation / Fail-Fast Policy

| 入力・状態 | 方針 |
|---|---|
| `records`が空リスト | 例外なし。`RetryMetricsCalculator`の既存契約通り`cycle_count=0`→`enqueue_success_ratio=None`→`RetryHealthEvaluator`が`HEALTHY`を返す→`RetryAlertLevel.NONE`→`RetryNotificationStatus.NO_NOTIFICATION`→`message=None`という連鎖が自然に導出される |
| `notification_decision.status == NOTIFY` | `RetryNotificationMessageBuilder.build()`を呼び`message`を設定 |
| `notification_decision.status == NO_NOTIFICATION` | Builderを呼ばず`message=None` |
| 未対応の`RetryNotificationStatus`相当値 | `evaluate()`内でフォールバックせず`ValueError`を送出（Fail Fast契約） |
| `RetryObservabilityReport`の直接構築時、`NOTIFY`かつ`message=None`／`NO_NOTIFICATION`かつ`message`が非None | `__post_init__`が`ValueError`を送出（`evaluate()`経由でない直接構築からもInvariantを保護する） |
| `RetryObservabilityReport`の直接構築時、未対応のstatus | `__post_init__`が`ValueError`を送出 |
| 各Evaluator/Builderが送出する`ValueError`（未対応enum値等） | `RetryObservabilityPipeline`は一切catchせず、無変換のまま伝播する |
| 引数の型違反 | 既存Foundation群と同様、明示的な`isinstance`検査は行わない |

`evaluate()`内の分岐（呼び出し経路のFail Fast）と`RetryObservabilityReport.__post_init__`（データ構造のInvariant）は意図的に二重に存在する。前者は「正しい呼び出し方」を強制する通常経路のガードであり、後者は「Reportが独立して直接構築されるケース」（テストコード等）に備えたデータ不変条件のガードである。

---

## 9. Data Flow

```
list[RetryRuntimeLogRecord]（唯一の入力。呼び出し元がI/Oを済ませた後の型）
    ↓
RetryMetricsCalculator.calculate()
    ↓
RetryMetricsSnapshot
    ↓
RetryHealthEvaluator.evaluate()
    ↓
RetryHealthReport
    ↓
RetryAlertEvaluator.evaluate()
    ↓
RetryAlert
    ↓
RetryNotificationEvaluator.evaluate()
    ↓
RetryNotificationDecision
    ↓
（NOTIFYの場合のみ）RetryNotificationMessageBuilder.build()
    ↓
RetryObservabilityReport（metrics / health_report / alert / notification_decision / message）
```

---

## 10. In Scope

- 新規`retry_observability_pipeline`パッケージ
- `RetryObservabilityReport` / `RetryObservabilityPipeline`
- 5段階の固定順序Composition
- `__post_init__`によるstatus/message invariant強制
- 未対応status相当値へのFail Fast
- Public API／`__all__`
- Dependency Direction（Orchestration/Facade層契約として文書化）とReverse Dependency禁止のAST Guard
- 新規E2E（12章）
- CLI/Pipeline Parity Test（本Release内で実施）
- `tests/zero_diff_guard_registry.py`への最小限の追記（13章）
- 本設計書

## 11. Out of Scope

`RetryRuntimeOrchestrator`変更、`RetryCompositionRoot`変更、`SchedulerEngine`変更、`scripts/show_retry_notification.py`変更、`.run/retry_runtime_log.jsonl`のSchema変更、`RetryRuntimeLogReader`の使用（本パッケージ内でのファイルI/O）、Sender／実送信、外部I/O、既存5パッケージの変更、具体的Channel／Delivery destinationの導入。

---

## 12. E2E Test Strategy

新規E2Eファイル（仮称`test_e2e_v6_29_0_retry_observability_pipeline_foundation.py`）で以下を検証する：

### Domain Object（`RetryObservabilityReport`）

- frozen dataclassであること・フィールドは5つのみであること
- `NOTIFY`＋`message=None`での直接構築が`ValueError`になること
- `NO_NOTIFICATION`＋`message`が非Noneでの直接構築が`ValueError`になること
- 未対応status相当値での直接構築が`ValueError`になること
- 正常な組み合わせ（`NOTIFY`＋非None、`NO_NOTIFICATION`＋None）は構築が成功すること

### Pipeline（`RetryObservabilityPipeline.evaluate()`）

- 空`records`→`cycle_count=0`→`HEALTHY`→`NONE`→`NO_NOTIFICATION`→`message=None`
- HEALTHY／DEGRADED／UNHEALTHY各パターンでの5段階連鎖の正しさ
- UNHEALTHY（NOTIFY）時のMessage構築内容の検証
- 未対応status相当値でのFail Fast（`evaluate()`内分岐の検証。既存Evaluator/Builderをmonkeypatch等で模擬）
- `thresholds`未指定時のDefault Threshold透過・カスタムThreshold注入の透過

### Architecture Guard（AST）

- `retry_observability_pipeline`が`RetryRuntimeLogReader` / Runtime系 / `RetryCompositionRoot` / `scheduler` / CLI（`scripts`）/ Logger／JSONL／外部pipライブラリのいずれもimportしないことの検証
- 既存5パッケージのいずれも`retry_observability_pipeline`をimportしていないこと（Reverse Dependency禁止）の検証
- `open()`等のファイルI/O呼び出しが本パッケージのソースコード中に存在しないことの検証

### CLI/Pipeline Parity Test

`scripts/show_retry_notification.py::build_report()`と`RetryObservabilityPipeline.evaluate()`が、同一入力に対し意味的に同一の結果を返すことを検証する。

```python
from unittest import mock

_parity_records: list[RetryRuntimeLogRecord] = [ ... ]  # 直接構築、JSONL/ファイルI/Oを一切経由しない

with mock.patch.object(
    show_retry_notification.RetryRuntimeLogReader, "read", return_value=_parity_records,
):
    _cli_report = show_retry_notification.build_report(Path("unused"))

_pipeline_report = RetryObservabilityPipeline().evaluate(_parity_records)

check("PARITY: metrics", _cli_report.metrics == _pipeline_report.metrics)
check("PARITY: health_report", _cli_report.health_report == _pipeline_report.health_report)
check("PARITY: alert", _cli_report.alert == _pipeline_report.alert)
check(
    "PARITY: notification_decision",
    _cli_report.notification_decision == _pipeline_report.notification_decision,
)
check("PARITY: message", _cli_report.message == _pipeline_report.message)
```

- `RetryRuntimeLogReader.read`をクラスレベルでmonkeypatchすることで、`build_report()`内部の`reader.read()`が実ファイルI/Oを行わずに`_parity_records`を返す。ログの実読み取り・パース処理自体は本テストの対象外（既存v6.8.0 CLI E2Eで別途カバー済み）
- 比較対象の5型（`RetryMetricsSnapshot` / `RetryHealthReport` / `RetryAlert` / `RetryNotificationDecision` / `RetryNotificationMessage`）はいずれも`@dataclass(frozen=True)`かつデフォルトの`__eq__`（`eq=False`指定なし）であるため、`==`によるfield-wise semantic equalityがそのまま成立する
- 検証シナリオ：empty records／HEALTHY／DEGRADED／UNHEALTHY（NOTIFY）の各パターン

---

## 13. Zero-Diff Guard Registry

`tests/zero_diff_guard_registry.py`の`NOIMPACT-TESTS-SCOPE`検査（v6.21.0〜v6.24.0の4つのbaseline-fixed guardが共通して実行する）は、`git diff --name-only BASELINE_COMMIT -- tests`により**`tests/`ディレクトリ全体**の差分を検出する。新規E2Eファイルはいずれのbaseline commit時点にも存在しないため、登録なしでは4guardすべてがFAILする。

**確定した変更内容**（v6.28.0の前例と同型）：

1. **`RELEASE_ORDER`（L43-52）へ`"v6.29.0"`を追記**（append-only）。これにより`release_index("v6.29.0")`が解決可能になる
2. **`_TEST_CHANGE_CONTRIBUTIONS`へ以下を追記**：
   ```python
   ("test_e2e_v6_29_0_retry_observability_pipeline_foundation.py", "v6.29.0"),
   ("zero_diff_guard_registry.py", "v6.29.0"),
   ```
   前者は本Releaseの新規E2Eファイル自体、後者は本Releaseが`zero_diff_guard_registry.py`自身を編集すること（上記1.の追記）に対する登録である（v6.28.0が自身の編集を`("zero_diff_guard_registry.py", "v6.28.0")`として登録した前例と同型）

**明確化（Codex Major指摘への回答）**：

- **source contribution（`_SOURCE_CHANGE_CONTRIBUTIONS`）は不要**。historical guardの`NOIMPACT-SCOPE`検査は`PROTECTED_PATHS`のみを走査し、`src/retry_observability_pipeline`はそこに含まれない
- 上記1.・2.は必要（source contributionとは別の理由・別の仕組みによるもの）

この変更は`tests/zero_diff_guard_registry.py`への**追記のみ**（GR-1：既存recordの書き換えは行わない）であり、既存4guardの判定結果・既存`PROTECTED_PATHS`・既存`_SOURCE_CHANGE_CONTRIBUTIONS`はいずれも無変更のまま維持される。

---

## 14. 将来Wiring境界（Runtime Wiring Releaseへの引き継ぎ事項）

本Foundationの出力（`RetryObservabilityReport`）と単一エントリーポイント（`RetryObservabilityPipeline.evaluate(records)`）は完全に自己完結した純粋関数であるため、次のWiring Releaseが決定すべき事項は以下の2点に限定される：

1. `records`（`list[RetryRuntimeLogRecord]`）をRuntime側のどこで・どうやって調達するか（`RetryRuntimeLogReader`をComposition Root等のどこで呼ぶか）
2. `RetryObservabilityReport`を得た後、それをどう扱うか（ログへ記録するか、console出力するか、他の判断へフィードバックするか）

加えて、Wiring Releaseは4章で記録したCLI／Facade間のtemporary debtを解消し、`scripts/show_retry_notification.py::build_report()`を`RetryObservabilityPipeline.evaluate()`への委譲へ置き換える。本Release（Foundation）の時点でParity Testが整備されているため、この置き換えの正しさは差分レビューで確認できる。

---

## 15. Technical Debt

1. CLIと本Facadeの間に、Wiring Release完了までComposition ロジックの一時的な重複が存在する（4章）
2. Package数がさらに1つ増加する（`retry_notification_message_foundation.md`28章で既に記録されたPackage Governance未確立というTechnical Debtの継続）

## 16. Known Issues

なし（本設計書作成時点。実装完了後のFormal Regression結果は実装Releaseで追記する）

## 17. Future Candidates

- Retry Observability Runtime Wiring（本Foundationを実際にRetry Runtimeへ接続する）
- CLI（`scripts/show_retry_notification.py`）の本Facadeへの委譲統一
- Retry Notification Channel Foundation（別途`ARCHITECTURE_BLOCKED`と判定済み。severity保持Message等の前提が整い次第、独立して再評価する）
