# Retry Monitoring Foundation（v6.4.0候補）

作成日：2026-07-14
更新日：2026-07-14（ChatGPT Architecture Review Approve取得、フィードバック反映：RetryHealthThresholdsのDomain Value明確化／RetryHealthReportをstatusのみに簡素化しreason・warnings・details等は将来拡張へ切り出し／RetryHealthEvaluatorのThreshold生成禁止の明記／Stateless Pure Functionテストの追加。6.5節 Architecture Decision新設）
更新日：2026-07-14（Implementation完了。`src/retry_monitoring/`実装・`tests/test_e2e_v6_4_0_retry_monitoring_foundation.py`（171/171 PASS）・既存回帰（v5.9.0 64/64・v6.0.0 43/43・v6.1.0 44/44・v6.2.0 64/64・v6.3.0 174/174、いずれもベースライン件数のままPASS）・`docs/architecture.md` / `docs/ROADMAP.md` / `docs/CHANGELOG.md`反映）
作成者：Claude Code（Architecture Designドラフト・Implementation・Test・Documentation）／ChatGPT（Architecture Review・Approve）／ユーザー（最終承認・実装指示）
状態：**Implementation Completed（commit／push待ち）**
分類：**Architecture Release**（[development_workflow.md](../development_workflow.md) 6章。0章で理由を明記）

> 本ドキュメントはROADMAP「Retry Monitoring Foundation」（`docs/ROADMAP.md` 606行目）およびv6.3.0設計書（`docs/design/retry_metrics_foundation.md` 11.1節）で責務境界のみ先行合意済みの次候補を対象としたArchitecture Designである。実装スコープは **Retry Monitoring Foundation** のみとし、CLI表示・Alert通知は将来Releaseへ切り出す（4章・11章参照）。

---

## 0. 分類再検討

[development_workflow.md](../development_workflow.md) 7章のFast Track候補条件と照合する。

### 0.1 Fast Track Checklist該当確認

| 条件 | 該当有無 | 内容 |
|---|---|---|
| Public API変更 | なし | 既存クラスのシグネチャ変更なし |
| Constructor変更 | なし | 既存クラスのConstructor変更なし |
| Composition Root変更 | なし | `RetryCompositionRoot`は無改修（消費者不在の先行実装。10章） |
| **Layer変更** | **あり** | 新規パッケージ`src/retry_monitoring/`を新設する。development_workflow.md 5章の定義「新しい層の追加、または既存層の責務変更はLayer変更に該当する」に抵触する |
| Dependency変更 | あり（新規import） | `retry_monitoring`が`retry_metrics`を新規importする（`RetryMetricsSnapshot`型を参照するため）。development_workflow.md 5章「`src/`配下パッケージ間の新しいimport関係の追加」に該当する |
| 永続化変更 | なし | 新しい永続化アーティファクトは発生しない（`.jsonl`を直接読まない。必須条件） |
| Event変更 | なし | 該当なし |
| 外部I/O変更 | なし | 通知（Slack／メール等）は対象外（Foundation First、4章） |

**結論**：Layer変更・Dependency変更の2条件に該当するため、Fast Track候補条件（development_workflow.md 7章）を満たさない。v6.2.0・v6.3.0と同じ理由（新規パッケージ追加＝Layer変更）に加え、今回は`retry_metrics`への新規importというDependency変更も伴うため、v6.3.0以上に明確にArchitecture Releaseへ該当する。本Releaseは**Architecture Release**として扱う。

Development Workflow 12章「Claude Codeは分類を最終確定させない」に従い、この分類は暫定判断であり、最終確定はChatGPTのArchitecture Reviewを経て行う。

---

## 1. Background

- v6.3.0（Retry Metrics Foundation）で、`.run/retry_runtime_log.jsonl`を読み取り集計する独立パッケージ`src/retry_metrics/`が完成した。出力は`RetryMetricsSnapshot`（frozen dataclass、16フィールド。`src/retry_metrics/retry_metrics_snapshot.py`）である。
- v6.3.0設計書11.1節は、次候補であるRetry Monitoring Foundationの責務境界を既に定義済みである。「`RetryMetricsSnapshot`（本Foundationの出力）を入力として受け取り、閾値に基づいて健全性ステータスを判定するだけの、別の独立パッケージ（`src/retry_monitoring/`）」とし、依存の向きを`Metrics → Monitoring → Alert`の一方向のみに限定する方針が、ChatGPT Architecture Reviewを経てApprove済みである。
- 本Release（ユーザー指示）は、この既定方針をさらに厳格化する形で以下を明示している。
  - Monitoringの入力は`RetryMetricsSnapshot`のみとする
  - MonitoringはRuntime・RetryManager・Logger・JSONLのいずれも知らない
  - 依存方向は`Runtime → Logger → Metrics → Monitoring → Alert（Future）`のみ許可し、Monitoringから上位層への逆依存は禁止する
- 現在のRuntime構成は以下のとおりで固定されている（v6.3.0から無変更）。

```
CLI（scripts/run_retry_runtime.py）
    → RetryRuntimeLock（v6.0.0、多重起動防止）
         → RetryRuntimeShutdown（v6.1.0、--loopのみ）
              → RetryRuntimeLoop（v5.5.0）
                   → RetryRuntimeOrchestrator（v5.2.0／v5.3.0）
                        → RetryManager（retry_engine）
              → RetryRuntimeCycleLogger（v6.2.0、run_cycle()内のみ）
                   → .run/retry_runtime_log.jsonl（JSON Lines、Git管理対象外）

RetryRuntimeLogReader（v6.3.0）→ RetryMetricsCalculator（v6.3.0）→ RetryMetricsSnapshot（v6.3.0）
```

- Loggingが確立した「Pipelineの縦の実行順序を変えず、既存コンポーネントは無改修のまま横方向・上方向に追加する」という設計判断を、v6.3.0がMetricsで踏襲し、本Releaseも同じ前例を踏襲する。Runtime Pipeline・Metricsのいずれにも一切触れない。

---

## 2. Goals

**v6.4.0 Retry Monitoring Foundationのゴール**：

1. 独立パッケージ`src/retry_monitoring/`を新設し、`RetryMetricsSnapshot`（v6.3.0の出力）**のみ**を入力として受け取れるようにする
2. 受け取った`RetryMetricsSnapshot`から、あらかじめ定義した閾値ルールに基づき健全性ステータス（`HEALTHY` / `DEGRADED` / `UNHEALTHY`のEnum）を判定できるようにする
3. 判定結果を呼び出し元へ返すだけの、副作用のないライブラリとして提供する（この段階ではCLI表示・通知・Alertは対象外）
4. 将来のAlert（Slack／メール等）が本Foundationの出力を消費できる、明確な出力契約（判定結果の型）を確立する
5. Monitoringが Runtime／RetryManager／Logger／JSONLのいずれにも一切依存しない（importしない・知らない）ことを、パッケージ構造そのもので保証する

**明示的にGoalとしないもの**（3章・4章で詳述）：

- CLI表示・ダッシュボード化（Retry Monitoring CLI/Report Wiring Foundation、将来Release）
- Slack／メール等への通知（Alert Foundation、将来Release）
- Runtime停止・Runtime制御（ユーザー指定の禁止事項）
- 閾値の動的変更・外部設定ファイル化（本Releaseでは固定値として実装。11.3節）

---

## 3. Scope

### 対象（本Release）

- 新規パッケージ `src/retry_monitoring/`
  - `retry_health_status.py` — `RetryHealthStatus`（`HEALTHY` / `DEGRADED` / `UNHEALTHY`のEnum）
  - `retry_health_thresholds.py` — `RetryHealthThresholds`（frozen dataclass、閾値定義。6.4節）
  - `retry_health_report.py` — `RetryHealthReport`（frozen dataclass、判定結果の値オブジェクト。6.3節）
  - `retry_health_evaluator.py` — `RetryHealthEvaluator`（`RetryMetricsSnapshot → RetryHealthReport`）
  - `__init__.py` — 公開API定義
- 新規テスト `tests/test_e2e_v6_4_0_retry_monitoring_foundation.py`

### 対象外（4章参照）

---

## 4. Out of Scope

- `scripts/`エントリーポイント・CLI表示（Retry Monitoring CLI/Report Wiring Foundation、将来Release。Foundation First — v6.3.0設計書11.2節と同型のパターン）
- Alert本体（Slack／メール等への通知、外部I/O。将来Release。11.1節）
- Runtime Pipeline（`RetryRuntimeLock` / `RetryRuntimeShutdown` / `RetryRuntimeLoop` / `RetryRuntimeOrchestrator` / `RetryManager`）への変更（ユーザー指定の禁止事項。一切触れない）
- Scheduler変更（ユーザー指定の禁止事項）
- `src/retry_metrics/`（`RetryMetricsCalculator` / `RetryMetricsSnapshot` / `RetryRuntimeLogReader` / `RetryRuntimeLogRecord`）への変更（ユーザー指定の禁止事項。Metrics側は本Releaseの都合で一切変更しない。11章「Monitoring→Metricsへの逆依存禁止」参照）
- `.run/retry_runtime_log.jsonl`のJSON Schema変更・JSONLの直接読み取り（ユーザー指定の必須条件「MonitoringはJSONLを読まない」に直結。7章）
- Runtime停止・Runtime制御（ユーザー指定の禁止事項。健全性判定はあくまで「情報の提供」であり、判定結果に基づくRuntimeの挙動変更は本Foundationの責務外）
- 閾値の外部設定ファイル化・動的変更（本Releaseでは固定値。11.3節）

### 4.1 Runtimeへのフィードバック（明示的に対象外）

Monitoring Foundationは**判定のみ**を担当し、Runtime・Metrics側へ一切フィードバックを行わない。以下はいずれも明示的に対象外である。

- Retry Runtimeの挙動変更
- Retry Queueの更新
- `RetryManager`の変更
- `RetryRuntimeOrchestrator` / `RetryRuntimeLoop` / `RetryRuntimeShutdown` / `RetryRuntimeLock`の変更
- `RetryMetricsCalculator` / `RetryMetricsSnapshot`の変更
- `RetryRuntimeCycleLogger`の変更
- Schedulerへの通知
- Retry実行可否の判断
- 通知の送信（Alertは将来Release、11.1節）

詳細は7章 Responsibility「Judgment Only Foundationとしての位置づけ」を参照。

---

## 5. Current Architecture

```
.run/retry_runtime_log.jsonl（v6.2.0が書き込む）
    ↑
RetryRuntimeCycleLogger（v6.2.0）
    ↑
CLI → RetryRuntimeLock → RetryRuntimeShutdown → RetryRuntimeLoop
     → RetryRuntimeOrchestrator → RetryManager

RetryRuntimeLogReader（v6.3.0）
    │  .run/retry_runtime_log.jsonl を読み取る
    ▼
RetryMetricsCalculator（v6.3.0）
    │  list[RetryRuntimeLogRecord] を集計する
    ▼
RetryMetricsSnapshot（v6.3.0、Immutable）
    │
    ▼
（呼び出し元は v6.3.0 時点では未定。消費者不在の先行実装）
```

`RetryMetricsSnapshot`は、v6.3.0の時点では生成されるだけで消費者が存在しない、唯一の構造化された集計データである。

---

## 6. Proposed Architecture

### 6.1 配置・命名

`src/retry_monitoring/`という新規独立パッケージを追加する。命名は既存の`retry_metrics` / `retry_history` / `retry_queue`等と同じ、ドメインスコープの平坦な命名規則に従う。

### 6.2 データフロー

```
RetryMetricsSnapshot（v6.3.0が生成した集計結果。本Releaseの唯一の入力）
        │
        ▼
RetryHealthEvaluator.evaluate(snapshot) -> RetryHealthReport
        │
        ▼
（呼び出し元は本Releaseでは未定。消費者不在の先行実装。将来はCLI／Alertが消費）
```

`retry_monitoring`パッケージは、`retry_runtime_logging` / `retry_runtime_orchestrator` / `retry_runtime_loop` / `retry_runtime_lock` / `retry_runtime_shutdown` / `retry_engine` / `retry_composition`のいずれもimportしない。唯一のimportは`retry_metrics`（`RetryMetricsSnapshot`の型を参照するため）であり、これは**唯一許可された依存**である（7章・8章で明記）。

`.run/retry_runtime_log.jsonl`というファイルパスの存在自体を、本パッケージのどのモジュールも一切知らない。ファイル入出力（`open()` / `Path` / `json`によるファイル読み取り）を行うコードは、本パッケージ内に一切存在しない。

### 6.3 API Design

```python
# src/retry_monitoring/retry_health_status.py
from __future__ import annotations
from enum import Enum


class RetryHealthStatus(Enum):
    """RetryHealthEvaluatorが判定する健全性ステータス。"""
    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
```

```python
# src/retry_monitoring/retry_health_thresholds.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryHealthThresholds:
    """RetryHealthEvaluatorが判定に用いる閾値定義（Immutable Value Object）。

    enqueue_success_ratioに対する下限値。RetryMetricsSnapshot.enqueue_success_ratio
    がNone（cycle_count=0等でratio自体が算出不能）の場合、閾値判定は行わずHEALTHYとする
    （9章 Failure Policy）。

    Architecture Decision（17章）：本クラスはConfig（外部設定・環境変数・設定ファイル）
    ではなく、Monitoring DomainのDomain Value（ドメイン値）として位置づける。
    frozen dataclassとして実装し、生成後の変更を構造的に禁止する。Foundationが持つのは
    「固定値を保持する」責務のみであり、値の取得元（環境変数・設定ファイル等）を自ら
    決定する責務は持たない（11.3節）。
    """
    degraded_below: float = 0.8
    unhealthy_below: float = 0.5
```

```python
# src/retry_monitoring/retry_health_report.py
from __future__ import annotations
from dataclasses import dataclass

from src.retry_monitoring.retry_health_status import RetryHealthStatus


@dataclass(frozen=True)
class RetryHealthReport:
    """RetryHealthEvaluatorの判定結果を表すImmutableな値オブジェクト。

    Release 6.4ではstatusのみを扱う（Foundation First）。reason／warnings／
    details（またはviolations）等の診断情報は将来拡張の対象とし、本Releaseでは
    追加実装しない（11.5節）。
    """
    status: RetryHealthStatus
```

```python
# src/retry_monitoring/retry_health_evaluator.py
from __future__ import annotations

from src.retry_metrics.retry_metrics_snapshot import RetryMetricsSnapshot
from src.retry_monitoring.retry_health_report import RetryHealthReport
from src.retry_monitoring.retry_health_status import RetryHealthStatus
from src.retry_monitoring.retry_health_thresholds import RetryHealthThresholds


class RetryHealthEvaluator:
    def __init__(self, thresholds: RetryHealthThresholds | None = None):
        self.thresholds = thresholds or RetryHealthThresholds()

    def evaluate(self, snapshot: RetryMetricsSnapshot) -> RetryHealthReport:
        """
        snapshot（RetryMetricsSnapshot、唯一の入力）から健全性を判定し
        RetryHealthReport を返す。

        - snapshot.enqueue_success_ratio が None の場合、閾値判定を行わず
          HEALTHY を返す（9章 Failure Policy）
        - 例外は送出しない（純粋な判定ロジックであり、判定不能な入力は
          「判定しない」という結果として扱う。ファイルI/O等の失敗系が
          存在しないため、本Foundationにfail-fastすべき異常系はない）
        """
        ...
```

`RetryHealthEvaluator`は`RetryMetricsSnapshot`のフィールドのうち`enqueue_success_ratio`のみを参照する。v6.3.0設計書14章が明記するとおり`enqueue_success_ratio`は**Enqueue段階の成功率**であり、Retry実行そのものの成否を表す指標ではない点は、将来`reason`等の診断フィールドを追加する際（11.5節）に踏襲し誤解を招かないようにする。

### 6.4 RetryHealthReportの責務（Immutability）

`RetryHealthReport`は**Immutable（読み取り専用）の値オブジェクト**である。`RetryMetricsSnapshot`（v6.3.0）と同じ設計判断（frozen dataclass、setter・update()を持たない）を踏襲する。新しい判定結果が必要な場合は`RetryHealthEvaluator.evaluate()`を再度呼び出し、新しいインスタンスを生成する。将来のAlertは`RetryHealthReport`を**参照するだけ**であり、更新は一切行わない（11.1節）。

### 6.5 Architecture Decision（Architecture Review反映）

Architecture Reviewでの指摘を受け、以下をArchitecture Decisionとして明記する。

- **AD-1（RetryHealthThresholdsの性質）**：`RetryHealthThresholds`は**Immutable Value Object**であり、`frozen=True`のdataclassとして実装する。これは**Config（設定）ではなくDomain Value（ドメイン値）**である。Threshold（閾値）はMonitoring Domainが持つ値であり、Foundationの責務は「固定値を保持すること」のみとする。値の外部化（環境変数・設定ファイル読み込み等）は本Releaseのスコープに含めない（11.3節）。
- **AD-2（RetryHealthEvaluatorの責務境界）**：`RetryHealthEvaluator`は**Thresholdを生成しない**。Thresholdは（a）呼び出し元からConstructor Injectionで外部から受け取る、または（b）未指定時に`RetryHealthThresholds()`のDefault Thresholdを使用する、の2通りのみを許可する。`RetryHealthEvaluator`がConfig生成（環境変数の読み込み・条件分岐によるThreshold組み立て等）の責務を持つことは禁止する。Thresholdの生成・供給は常に`RetryHealthEvaluator`の外側の責務とする。

---

## 7. Responsibility

**Retry Monitoring Foundationは Judgment Only Foundation である。** 本Foundationは`RetryMetricsSnapshot`（v6.3.0が生成した集計結果）のみを入力として受け取り、`RetryHealthReport`を生成する判定処理のみを担当する。Runtime側・Logger側・Metrics側のいずれへも一切書き込み・通知・フィードバックを行わない（4.1節参照）。

| コンポーネント | 責務 | 変更有無 |
|---|---|---|
| `RetryHealthStatus`（新規） | 健全性ステータスを表すEnum | 新規追加 |
| `RetryHealthThresholds`（新規） | 判定に用いる閾値を表す不変の値オブジェクト | 新規追加 |
| `RetryHealthReport`（新規） | 判定結果を表すImmutable（読み取り専用）な値オブジェクト。生成後は変更されない。Alert等の消費者は参照のみで更新を行わない | 新規追加 |
| `RetryHealthEvaluator`（新規） | `RetryMetricsSnapshot`から`RetryHealthReport`を計算するのみ。ファイルI/O・Runtime参照・Logger参照は一切行わない | 新規追加 |
| `RetryMetricsSnapshot` / `RetryMetricsCalculator` / `RetryRuntimeLogReader` / `RetryRuntimeLogRecord`（v6.3.0） | 無変更。本Releaseからは`RetryMetricsSnapshot`の型のみ参照され、他の3クラスは参照も依存もされない | 無改修 |
| `RetryRuntimeCycleLogger`（v6.2.0） | 無変更。本Releaseからは存在すら参照されない | 無改修 |
| `RetryRuntimeLock` / `RetryRuntimeShutdown` / `RetryRuntimeLoop` / `RetryRuntimeOrchestrator` / `RetryManager` | 無変更（ユーザー指定の禁止事項）。本Foundationからのフィードバックは一切発生しない | 無改修 |
| `RetryCompositionRoot` | 無変更（消費者不在の先行実装のため配線しない） | 無改修 |

「判定（`RetryHealthEvaluator`）」と「入力データ生成（v6.3.0の`RetryMetricsCalculator`）」を別パッケージへ分離しているのは、v6.3.0設計書11.1節が確立した「Metrics＝何が起きたかを数える」「Monitoring＝その数値が問題かどうかを判断する」という責務境界を、そのまま実装へ落とし込むためである。

---

## 8. Dependency

- `retry_monitoring` → `retry_metrics`（`RetryMetricsSnapshot`型の参照のみ）＋標準ライブラリ（`enum` / `dataclasses`）
- `retry_monitoring`は`retry_metrics`以外の他の`src/*`パッケージをいずれもimportしない（`retry_runtime_logging` / `retry_runtime_orchestrator` / `retry_runtime_loop` / `retry_runtime_lock` / `retry_runtime_shutdown` / `retry_engine` / `retry_composition`のいずれとも無関係）
- `retry_metrics`は`retry_monitoring`をimportしない（**逆依存の禁止**。ユーザー指定の必須条件「依存方向はRuntime→Logger→Metrics→Monitoring→Alertのみ」を、パッケージのimport文そのもので保証する）
- 既存パッケージから`retry_monitoring`への依存も本Releaseでは発生しない（消費者不在の先行実装。v6.3.0と同型のパターン）
- 新しい外部パッケージ（pip）は追加しない

### 8.1 依存方向の検証（テストで保証する契約）

本Releaseの新規E2Eテストには、以下をコード上で機械的に確認するテストケースを含める（9章・Test Strategyで詳述）。

- `src/retry_monitoring/`配下のいずれのファイルも、`retry_runtime_logging` / `retry_runtime_orchestrator` / `retry_runtime_loop` / `retry_runtime_lock` / `retry_runtime_shutdown` / `retry_engine` / `retry_composition`をimportしていないこと
- `src/retry_monitoring/`配下のいずれのファイルも、`open()`によるファイルI/O、`pathlib.Path`、`.jsonl`という文字列リテラルを含まないこと（JSONLを直接読まないことの構造的な保証）
- `src/retry_metrics/`配下のいずれのファイルも、`retry_monitoring`をimportしていないこと（逆依存禁止の保証）

---

## 9. Failure Policy

| 状況 | 方針 | 理由 |
|---|---|---|
| `snapshot.enqueue_success_ratio`が`None`（対象サイクルが0件等） | 例外を送出せず、閾値判定を行わず`HEALTHY`の`RetryHealthReport`を返す | 「データがまだない」状態は異常ではなく、判定不能を`UNHEALTHY`として扱うと誤ったアラートを招くため（v6.3.0の「0件という正常なデータ」という扱いと対称的） |
| `snapshot`が`cycle_count=0`のSnapshot | 上記と同じ扱い（`enqueue_success_ratio`が`None`になるため自動的にHEALTHY） | 同上 |
| `thresholds`未指定（`RetryHealthEvaluator()`をデフォルト引数で生成） | `RetryHealthThresholds()`のデフォルト値（`degraded_below=0.8` / `unhealthy_below=0.5`）を使用する | 呼び出し元が閾値を意識せずとも動作する、消費者不在の先行実装として妥当なデフォルトを提供するため |

本Foundationはファイル I/O・ネットワーク I/O を一切行わないため、v6.3.0（9章）にあるような「ファイルが読めない」「JSONパース失敗」といった環境異常系は構造的に発生しない。したがって本Foundationに`OSError`等のfail-fast系ポリシーは存在しない。

---

## 10. DI構成

- `RetryHealthEvaluator`は`thresholds: RetryHealthThresholds | None = None`をConstructor Injectionで保持する（未指定時はデフォルト値を使用、9章）
- `RetryHealthEvaluator`は状態を持たないStatelessコンポーネントとし、`evaluate(snapshot) -> RetryHealthReport`という純粋関数的APIとする（`RetryMetricsCalculator`（v6.3.0）と同型）
- 本Releaseでは`RetryCompositionRoot`への配線を行わない（Composition Root変更なし）
- 将来CLI／Alertから利用する際は、呼び出し元が`RetryRuntimeLogReader(log_path=...)` → `RetryMetricsCalculator()` → `RetryHealthEvaluator()`を自身で組み立てて呼び出す想定とし、`RetryCompositionRoot`への追加は実際の消費者が現れた時点で改めて検討する

---

## 11. Future Extension

### 11.1 Retry Alert Foundation（次候補）

`RetryHealthReport`（本Foundationの出力）を入力として受け取り、`status`が`DEGRADED`／`UNHEALTHY`の場合にSlack／メール等の外部サービスへ通知する、別の独立パッケージ（例：`src/retry_alert/`）として設計する。

**責務境界（一方向依存）**：

```
Metrics（v6.3.0。JSONLを集計するだけ）
    │  RetryMetricsSnapshot（Immutable）
    ▼
Monitoring（本Foundation。Snapshotを参照し健全性を判定するだけ）
    │  RetryHealthReport（Immutable）
    ▼
Alert（将来。判定結果を通知先へ送るだけ）
```

`Alert → Monitoring`の逆依存は禁止する。Alert側の都合（通知チャネルの追加等）によってMonitoring側の判定ロジックが変更されることがあってはならない。Alertは外部I/O（Slack API等）を伴うため、単独でArchitecture Release相当の検討を要する。

### 11.2 Retry Monitoring CLI/Report Wiring Foundation

`scripts/show_retry_health.py`等を新設し、`RetryHealthReport`を人間可読な形式でコンソール表示する。v6.3.0設計書11.2節と同型のパターン。

### 11.3 閾値の外部設定化

`RetryHealthThresholds`は本Releaseではコード上の固定デフォルト値（`degraded_below=0.8` / `unhealthy_below=0.5`）とする。運用実績を踏まえ、環境変数または設定ファイルからの読み込みが必要になった場合、別Releaseとして検討する（設定ファイルの読み込みは新しい外部I/O・永続化変更に該当する可能性があるため、独立したArchitecture Reviewを要する）。

### 11.4 複数指標に基づく総合判定

現時点の`RetryHealthEvaluator`は`enqueue_success_ratio`のみを参照する単一指標判定である。`RetryMetricsSnapshot`が保持する他のフィールド（`enqueue_failed_total`等）を組み合わせた総合判定へ拡張するかどうかは、v6.3.0設計書11.3節（Retry Runtime Log Schema Extension）の進捗と合わせて将来検討する。

### 11.5 RetryHealthReportの拡張候補（Architecture Review反映）

`RetryHealthReport`は6.3節のとおりRelease 6.4では`status`のみを扱うが、将来的には以下の情報を追加できる設計であることをここに明記する。

| 追加候補フィールド | 想定用途 |
|---|---|
| `reason` | 判定理由を人間可読な文字列として説明する（例：「enqueue_success_ratioが閾値0.5を下回った」） |
| `warnings` | `HEALTHY`判定であっても注意が必要な兆候をリストとして保持する（例：閾値に近づいているが未到達の場合） |
| `details`（または`violations`） | 判定の根拠となった具体的な数値・違反した閾値ルールを構造化して保持する |

これらはいずれも**Release 6.4では追加実装しない**。Foundationは現時点で`status`のみを扱う最小構成とし、上記フィールドの追加はAlert（11.1節）・CLI/Report Wiring（11.2節）等、実際の消費者の要件が明らかになった時点で改めてArchitecture Reviewを経て検討する。

---

## 12. Alternatives

| # | 案 | 却下理由 |
|---|---|---|
| 1 | Retry MonitoringとRetry Alertを1つのReleaseとして一括実装する | Foundation First原則（1バージョン=1目的）に反する。v6.3.0設計書13章#1と同じ理由で却下する |
| 2 | `RetryMetricsCalculator`（v6.3.0）に`evaluate_health()`のような判定APIを追加する | 同クラスの責務を「集計」から拡張することになり、v6.3.0で確定した責務（集計のみ、Read Only Foundation）を変更してしまう。v6.3.0設計書13章の設計判断（責務境界を同一パッケージ内で曖昧にしない）と矛盾する |
| 3 | `RetryHealthEvaluator`が`.run/retry_runtime_log.jsonl`を直接読み取り、`RetryMetricsSnapshot`を経由せず自前で集計する | ユーザー指定の必須条件「MonitoringはJSONLを読まない」に直接抵触する。また`retry_runtime_logging`への直接依存が発生し、8章の依存方向ルールに反する |
| 4 | 閾値判定に外部ルールエンジン（ライブラリ）を利用する | 単純な数値比較のみのため外部ライブラリは不要。v6.3.0設計書12章#4と同じ考え方（Dependency変更を避ける） |

---

## 13. Rejected Designs

| # | 却下した設計 | 理由 |
|---|---|---|
| 1 | MonitoringをMetricsと同一パッケージ内のサブモジュールとして実装する | v6.3.0設計書13章#1のRejected Designをそのまま踏襲。ユーザー要求「Monitoringは独立Package」に反する |
| 2 | `RetryHealthReport`をmutableなclassとして実装する | 既存の`RetryMetricsSnapshot`（v6.3.0）・`RetryRuntimeCycleResult`等、Result系オブジェクトが一貫してfrozen dataclassである慣習と整合させるため |
| 3 | `RetryHealthEvaluator`が判定不能時（`enqueue_success_ratio`が`None`）に例外を送出する | 「データがまだない」状態は異常ではなく正常なシステム状態であり、例外送出は呼び出し元に不要なtry/exceptを強いる。v6.3.0の`RetryMetricsCalculator.calculate([])`が例外を送出せず`cycle_count=0`を返す設計と対称的な判断とした |
| 4 | Runtime側から`RetryHealthReport`を参照し、`UNHEALTHY`時にRuntimeの挙動を自動的に変更する（例：Loop停止） | ユーザー指定の禁止事項「Runtime停止」「Runtime制御」に直接抵触する。また`Runtime → Monitoring`の依存が新たに発生し、7章の依存方向ルール（Monitoringから上位層への逆依存禁止）にも反する |

---

## 14. Risks

- **判定基準（閾値）の恣意性**：`degraded_below=0.8` / `unhealthy_below=0.5`は本Releaseで暫定的に設定した固定値であり、実運用データに基づく検証は行っていない。運用開始後、閾値が実態と合わない可能性がある（11.3節で外部設定化を将来検討）
- **単一指標判定の限界**：`enqueue_success_ratio`のみに基づく判定であるため、v6.3.0設計書14章が指摘する同指標の限界（Enqueue段階の成功率であり、Retry実行自体の成否を表さない）をそのまま引き継ぐ。真の健全性判定には11.4節・v6.3.0設計書11.3節（Schema Extension）が前提条件となる
- **消費者不在による設計の未検証リスク**：v6.3.0と同様、本Releaseも実際の呼び出し元（CLI／Alert）が存在しないまま設計するため、実際に統合される際にAPIの使い勝手（`RetryHealthThresholds`の受け渡し方法等）が見直される可能性がある

---

## 15. Technical Debt

- 単一指標（`enqueue_success_ratio`）判定であり、複数指標を組み合わせた総合的な健全性判定は本Releaseでは対象外とした（11.4節）
- 閾値がコード上の固定値であり、外部設定化・動的変更の仕組みは本Releaseでは実装しない（11.3節）
- Alert（実際の通知）が存在しないため、本Foundationの判定結果は現時点で人間が能動的に確認する手段がない（11.2節のCLI Wiring、11.1節のAlertが前提条件）

---

## 16. Known Issues

- 実装完了後の確認結果：新規Known Issueなし。既存Architecture Guard（v5.9.0〜v6.3.0のE2Eテスト）はいずれもベースライン件数のままPASSしており、本Releaseによる既存テストへの新規FAILは発生していない（2026-07-14時点の最新Known Issueは引き続き`[KI-29]`）
- 既知の制約（本設計時点で判明済み）：
  - `RetryMetricsSnapshot.enqueue_success_ratio`が`None`の場合、本Foundationは常に`HEALTHY`を返す。「まだ判定材料がない」状態と「実際に健全である」状態が同じステータス値で表現される点は、将来CLI／Alertが表示する際に区別が必要になる可能性がある
  - 本Foundationは`RetryMetricsSnapshot`の生成タイミング（呼び出し元がいつ`RetryMetricsCalculator.calculate()`を呼ぶか）には関与しない。リアルタイム性（最新のRuntime実行結果を反映しているか）は呼び出し元の責務である

---

## Test Strategy

- 新規E2Eテスト `tests/test_e2e_v6_4_0_retry_monitoring_foundation.py` を追加する
  - `RetryHealthEvaluator.evaluate()`の閾値境界値テスト（`degraded_below` / `unhealthy_below`の境界、およびその前後）
  - `enqueue_success_ratio=None`時に例外を送出せず`HEALTHY`を返すことの確認（9章）
  - カスタム`RetryHealthThresholds`を渡した場合に判定が閾値に従って変わることの確認
  - `RetryHealthReport`がfrozen dataclassであり、生成後のフィールド再代入が`FrozenInstanceError`になることの確認（6.4節、v6.3.0の`RetryMetricsSnapshot`と同型のテスト）
  - 8.1節の依存方向検証（`retry_monitoring`が許可外パッケージをimportしていないこと、ファイルI/O関連コードを含まないこと、`retry_metrics`が`retry_monitoring`をimportしていないこと）をソースコード走査で機械的に確認するテストケース
  - **Stateless Pure Functionテスト（Architecture Review反映）**：`RetryHealthEvaluator`はStateless Pure Functionとして扱う。同一の`RetryMetricsSnapshot`を複数回入力した場合、常に同一の`RetryHealthReport`（同一の`status`）を返すことを確認し、内部状態を持たないこと（Statelessであること）を保証する
- 既存回帰テスト：v6.0.0〜v6.3.0のE2Eテストをすべて実行し、Runtime Pipeline・`retry_metrics`が0 diffのまま維持されていることを確認する（development_workflow.md 9章「既存回帰テスト：必須」）

---

## Status

- [x] Architecture Designドラフト作成（Claude Code）
- [x] ChatGPT Architecture Review Approve取得・フィードバック反映
- [x] 人間の実装承認
- [x] 実装着手・完了（`src/retry_monitoring/`新設。Runtime Pipeline・`src/retry_metrics/`はいずれも無改修）
- [x] Test Review（新規E2E 171/171 PASS。既存回帰：v5.9.0 64/64・v6.0.0 43/43・v6.1.0 44/44・v6.2.0 64/64・v6.3.0 174/174、いずれも0 diff）
- [x] CHANGELOG／ROADMAP／architecture.md反映
- [ ] Code Review（ChatGPTによる実装差分レビュー、未実施）
- [ ] Release Review
- [ ] commit／push
