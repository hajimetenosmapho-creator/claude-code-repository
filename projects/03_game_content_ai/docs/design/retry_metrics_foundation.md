# Retry Metrics Foundation（v6.3.0候補）／ Retry Monitoring Foundation 境界検討

作成日：2026-07-14
更新日：2026-07-14（Architecture Review 1回目フィードバック反映：RetryMetricsSnapshotのImmutability明確化／Read Only Foundationの明記／Monitoringとの一方向依存の補強）
更新日：2026-07-14（ChatGPT Architecture Review（最終）Approve取得、Implementation完了。v6.3.0として`src/retry_metrics/`実装・`tests/test_e2e_v6_3_0_retry_metrics_foundation.py`（174/174 PASS）・既存回帰（v5.9.0/v6.0.0/v6.1.0/v6.2.0、いずれもベースライン件数のままPASS）・`docs/architecture.md` / `docs/ROADMAP.md` / `docs/CHANGELOG.md`反映）
作成者：Claude Code（Architecture Designドラフト・Implementation・Test・Documentation）／ChatGPT（Architecture Review・Approve）／ユーザー（最終承認・実装指示）
状態：**Implementation完了（Release Review・commit／push待ち）**
分類：**Architecture Release**（[development_workflow.md](../development_workflow.md) 6章。0章で理由を明記）

> 本ドキュメントはROADMAP「Retry Metrics / Monitoring」（`docs/ROADMAP.md` 580行目・605行目）を対象としたArchitecture Designである。実装スコープは **Retry Metrics Foundation** のみとし、Retry Monitoring Foundationは責務境界を明確化した上で将来Releaseへ切り出す（11章参照）。

---

## 0. 分類再検討（重要）

ユーザー指示では本Releaseは「Fast Track Release」とされていたが、[development_workflow.md](../development_workflow.md) 7章のFast Track候補条件と照合した結果、**Fast Trackの条件を満たさない**ことが判明したため、本ドキュメントは**Architecture Release**として作成する。

### 0.1 Fast Track Checklist該当確認

| 条件 | 該当有無 | 内容 |
|---|---|---|
| Public API変更 | なし | 既存クラスのシグネチャ変更なし |
| Constructor変更 | なし | 既存クラスのConstructor変更なし |
| Composition Root変更 | なし | `RetryCompositionRoot`は無改修（消費者不在の先行実装） |
| **Layer変更** | **あり** | 新規パッケージ`src/retry_metrics/`を新設する。[development_workflow.md](../development_workflow.md) 5章の定義「新しい層の追加、または既存層の責務変更はLayer変更に該当する」に抵触する |
| Dependency変更 | なし | 標準ライブラリのみ。他の`retry_*`パッケージへの新規importなし |
| 永続化変更 | なし | 新しい永続化アーティファクトは発生しない（既存`.run/retry_runtime_log.jsonl`の読み取りのみ） |
| Event変更 | なし | 該当なし |
| 外部I/O変更 | なし | 該当なし |

**結論**：Layer変更に該当するため、Fast Track候補条件（development_workflow.md 7章）をすべて満たさない。v6.2.0（Structured Loop Logging Foundation）が全く同じ理由（新規パッケージ追加＝Layer変更）でArchitecture Releaseに分類された前例（`docs/design/retry_runtime_structured_loop_logging_foundation.md` 0.5節）と整合させ、本Releaseも**Architecture Release**として扱う。

Development Workflow 12章「Claude Codeは分類を最終確定させない」に従い、この分類は暫定判断であり、最終確定はChatGPTのArchitecture Reviewを経て行う。

---

## 1. Background

- v6.2.0（Structured Loop Logging Foundation）で、Retry Runtimeの1サイクル分の実行結果をJSON Lines形式で`.run/retry_runtime_log.jsonl`へ記録する`RetryRuntimeCycleLogger`（`src/retry_runtime_logging/`）が完成した。
- 同Releaseの設計書は「Retry Metrics / Monitoring（ROADMAP未着手項目）は、本Foundationが生成するJSON Linesログを入力データとして今後着手可能になった」と明記しており（同設計書9章 Technical Debt）、ROADMAP側にも「Retry Metrics / Monitoring（再掲、v6.2.0で入力データが整備された）」として次候補が記録されている（`docs/ROADMAP.md` 605行目）。
- ROADMAPが元々想定していたゴールは「Retry実行の成功率・試行回数分布・Queue滞留時間等を集計・可視化する仕組み」（`docs/ROADMAP.md` 580行目）である。
- 現在のRuntime構成は以下のとおりで固定されている。

```
CLI（scripts/run_retry_runtime.py）
    → RetryRuntimeLock（v6.0.0、多重起動防止）
         → RetryRuntimeShutdown（v6.1.0、--loopのみ）
              → RetryRuntimeLoop（v5.5.0）
                   → RetryRuntimeOrchestrator（v5.2.0／v5.3.0）
                        → RetryManager（retry_engine）
              → RetryRuntimeCycleLogger（v6.2.0、run_cycle()内のみ。Pipeline外の横方向の追加）
                   → .run/retry_runtime_log.jsonl（JSON Lines、Git管理対象外）
```

- Loggingは「Pipelineの縦の実行順序を変えず、CLI層の`run_cycle()`クロージャ内でのみ横方向に追加する」という設計判断がv6.2.0で確立された。本Releaseもこの前例を踏襲し、Runtime Pipelineには一切触れない。

---

## 2. Goals

**v6.3.0 Retry Metrics Foundationのゴール**：

1. 独立パッケージ`src/retry_metrics/`を新設し、`.run/retry_runtime_log.jsonl`を読み取って複数サイクル分のログレコードを取得できるようにする
2. 取得したレコード群から、集計値（`RetryMetricsSnapshot`）を計算できるようにする
3. 計算結果を呼び出し元へ返すだけの、副作用のないライブラリとして提供する（この段階ではCLI表示・ダッシュボード・通知は対象外）
4. 将来のRetry Monitoring Foundationが本Foundationの出力を消費できる、明確な入力契約（`RetryMetricsSnapshot`の型）を確立する

**明示的にGoalとしないもの**（3章・11章で詳述）：

- `RetryOutcome`別（成功／スキップ／dry_run）の内訳に基づく、真の意味での「Retry成功率」の算出（現行JSON Schemaに情報がないため不可能）
- 試行回数（`attempt`）分布の算出（現行JSON Schemaに`attempt`が含まれないため不可能）
- Queue滞留時間の算出（`RetryQueueManager`がin-memoryかつenqueue時刻を保持しないため不可能）
- CLI表示・ダッシュボード化・アラート通知（Retry Monitoring Foundation、将来Release）

---

## 3. Scope

### 対象（本Release）

- 新規パッケージ `src/retry_metrics/`
  - `retry_runtime_log_record.py` — `RetryRuntimeLogRecord`（frozen dataclass、v6.2.0のJSON Schema 15フィールドをミラーリング）
  - `retry_runtime_log_reader.py` — `RetryRuntimeLogReader`（`.jsonl`を読み取り`list[RetryRuntimeLogRecord]`を返す）
  - `retry_metrics_snapshot.py` — `RetryMetricsSnapshot`（frozen dataclass、集計結果）
  - `retry_metrics_calculator.py` — `RetryMetricsCalculator`（`list[RetryRuntimeLogRecord] → RetryMetricsSnapshot`）
  - `__init__.py` — 公開API定義
- 新規テスト `tests/test_e2e_v6_3_0_retry_metrics_foundation.py`

### 対象外（4章参照）

---

## 4. Out of Scope

- `scripts/`エントリーポイント・CLI表示（Retry Metrics CLI/Report Wiring Foundation、将来Release。Foundation First — v5.3.0 Run Once Foundationとv5.4.0 Script Entry Point Foundationの分離と同型パターン）
- Retry Monitoring Foundation本体（閾値判定・健全性ステータス判定・通知。11章参照）
- `.run/retry_runtime_log.jsonl`のJSON Schema変更（`RetryRuntimeCycleLogger`＝v6.2.0の既存コンポーネントへの変更。11章「Retry Runtime Log Schema Extension」で将来検討）
- Runtime Pipeline（`RetryRuntimeLock` / `RetryRuntimeShutdown` / `RetryRuntimeLoop` / `RetryRuntimeOrchestrator` / `RetryManager`）への変更（ユーザー指定の禁止事項。一切触れない）
- Queue滞留時間の算出（現状`RetryQueueManager`はin-memoryかつenqueue時刻を保持しないため、本Releaseのデータソースだけでは算出不能。Queue側の設計変更が前提条件となるため対象外）
- ログローテーション・保持期間管理（v6.2.0からのTechnical Debtを継続）
- 期間フィルタリング（直近24時間のみ等）機能

### 4.1 Runtimeへのフィードバック（Architecture Review反映：明示的に対象外）

Metrics Foundationは**集計のみ**を担当し、Runtimeへ一切フィードバックを行わない。以下はいずれも明示的に対象外である。

- Retry Runtimeの挙動変更
- Retry Queueの更新
- `RetryManager`の変更
- `RetryRuntimeOrchestrator`の変更
- `RetryRuntimeLoop`の変更
- `RetryRuntimeShutdown`の変更
- `RetryRuntimeLock`の変更
- Schedulerへの通知
- Retry実行可否の判断
- Alert判定
- Monitoring Policy（閾値定義・健全性判定そのもの。11.1節のRetry Monitoring Foundationの責務）

詳細は7章 Responsibility「Read Only Foundationとしての位置づけ」を参照。

---

## 5. Current Architecture

```
.run/retry_runtime_log.jsonl（v6.2.0が書き込む。追記のみ・Git管理対象外）
    ↑
    │ 書き込み（このRelease以前から存在。無改修）
    │
RetryRuntimeCycleLogger（src/retry_runtime_logging/、v6.2.0）
    ↑
    │ scripts/run_retry_runtime.py の run_cycle() クロージャ内でのみ呼び出される
    │
CLI（scripts/run_retry_runtime.py）
    → RetryRuntimeLock → RetryRuntimeShutdown → RetryRuntimeLoop
         → RetryRuntimeOrchestrator → RetryManager（retry_engine）
```

`.run/retry_runtime_log.jsonl`は、Runtime Pipelineの実行結果が確定した**後**に生成される、プロセスの外部からも参照可能な唯一の構造化データである。現状、これを読み取る消費者は存在しない。

---

## 6. Proposed Architecture

### 6.1 配置・命名

`src/retry_metrics/`という新規独立パッケージを追加する。命名は既存の`retry_history` / `retry_queue`等と同じ、ドメインスコープの平坦な命名規則に従う（`src/metrics/`のような汎用命名は、2つ目の消費者・対象領域が存在しない段階での先回り抽象化として不採用。development_workflow.md 4章「変更量ではなく設計リスクで分類する」・development_charter.md「抽象化は必要になってから行う」と同じ考え方）。

### 6.2 データフロー

```
.run/retry_runtime_log.jsonl（読み取り専用、v6.2.0が書き込んだファイル）
        │
        ▼
RetryRuntimeLogReader.read() -> list[RetryRuntimeLogRecord]
        │
        ▼
RetryMetricsCalculator.calculate(records) -> RetryMetricsSnapshot
        │
        ▼
（呼び出し元は本Releaseでは未定。消費者不在の先行実装。将来はCLI／Retry Monitoring Foundationが消費）
```

`retry_metrics`パッケージは、`retry_runtime_logging` / `retry_runtime_orchestrator` / `retry_runtime_loop` / `retry_runtime_lock` / `retry_runtime_shutdown` / `retry_engine` / `retry_composition`のいずれもimportしない。ファイルパス（`.run/retry_runtime_log.jsonl`）とJSON Schemaの「形」（shape）のみを契約として扱う、**型参照ではなく契約（shape一致）による疎結合**を採用する（`format_summary()`が`RetryRuntimeCycleResult`の形だけを知る設計、`RetryEnqueueGuard`のProtocol設計と同型のパターン）。

### 6.3 API Design

```python
# src/retry_metrics/retry_runtime_log_record.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryRuntimeLogRecord:
    """.run/retry_runtime_log.jsonl の1行（v6.2.0固定スキーマ）をミラーリングした値オブジェクト。"""
    cycle_number: int
    timestamp: str
    dry_run: bool
    enqueue_scanned: int
    enqueue_enqueued: int
    enqueue_skipped_existing: int
    enqueue_skipped_status: int
    enqueue_skipped_history: int
    enqueue_failed: int
    scheduler_candidates: int
    execution_executed: int
    removal_removed: int
    cleanup_cleaned: int
    terminal_cleanup_cleaned: int
    history_recorded: int
```

```python
# src/retry_metrics/retry_runtime_log_reader.py
from pathlib import Path


class RetryRuntimeLogReader:
    def __init__(self, log_path: Path):
        self.log_path = log_path

    def read(self) -> list[RetryRuntimeLogRecord]:
        """
        log_path から JSON Lines を読み取り、RetryRuntimeLogRecord のリストを返す。

        - ファイルが存在しない場合は空リストを返す（正常系。Retry Runtime未実行の状態）
        - 個々の行のJSONパース失敗は、その行のみスキップしstderrへWARNINGを
          出力して処理を継続する（ベストエフォート。クラッシュ時の不完全な
          末尾行を許容するため）
        - ファイル自体が読めない場合（権限エラー等のOSError）は例外を
          そのまま送出する（fail-fast）
        """
        ...
```

```python
# src/retry_metrics/retry_metrics_snapshot.py
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class RetryMetricsSnapshot:
    cycle_count: int
    period_start: str | None
    period_end: str | None
    dry_run_cycle_count: int
    enqueue_scanned_total: int
    enqueue_enqueued_total: int
    enqueue_skipped_existing_total: int
    enqueue_skipped_status_total: int
    enqueue_skipped_history_total: int
    enqueue_failed_total: int
    scheduler_candidates_total: int
    execution_executed_total: int
    removal_removed_total: int
    cleanup_cleaned_total: int
    terminal_cleanup_cleaned_total: int
    history_recorded_total: int
    enqueue_success_ratio: float | None  # enqueue_enqueued_total / enqueue_scanned_total
```

```python
# src/retry_metrics/retry_metrics_calculator.py
class RetryMetricsCalculator:
    def calculate(self, records: list[RetryRuntimeLogRecord]) -> RetryMetricsSnapshot:
        """
        records（時系列順を仮定しない）から集計値を計算し RetryMetricsSnapshot を返す。
        空リストの場合も例外を送出せず、cycle_count=0 の Snapshot を返す。
        """
        ...
```

`enqueue_success_ratio`は**Enqueue段階（Queueへの投入）の成功率**であり、Retry実行そのものの成否（`RetryOutcome`）を表す指標ではない。命名を意図的に区別し、14章 Risksで利用者向けの注意を明記する。

### 6.4 RetryMetricsSnapshotの責務（Immutability、Architecture Review反映）

`RetryMetricsSnapshot`は**Immutable（読み取り専用）の値オブジェクト**である。

- 生成後は変更しない（`frozen=True`のdataclassとして実装し、フィールドの再代入自体を構造的に禁止する。13章 Rejected Designs #2で「mutableなclassとして実装する案」を既に却下済み）
- `RetryMetricsSnapshot`自身は自分自身を更新する手段（setter・`update()`メソッド等）を一切持たない。新しい集計結果が必要な場合は、`RetryMetricsCalculator.calculate()`を再度呼び出し、新しい`RetryMetricsSnapshot`インスタンスを新規生成する
- 将来のRetry Monitoring Foundationは`RetryMetricsSnapshot`を**参照するだけ**であり、更新は一切行わない（11.1節）

責務イメージ：

```
.run/retry_runtime_log.jsonl（JSONL）
        │
        ▼
RetryMetricsCollector（RetryRuntimeLogReader → RetryMetricsCalculatorの合成役割）
        │
        ▼
RetryMetricsSnapshot（Immutable）
```

「`RetryMetricsCollector`」は、`RetryRuntimeLogReader`（読み取り）と`RetryMetricsCalculator`（集計）が共同で果たす「JSONLからSnapshotを生成する」という役割全体を指す概念的な名称であり、6.3節のAPI Designで示した2クラス構成（読み取りと集計の責務分離）を変更するものではない。将来この2クラスを1つの`RetryMetricsCollector`へ統合するかどうかは実装時に改めて判断する（統合する場合も、7章のとおり「JSONL→Snapshot生成」という読み取り専用の一方向フローである点は変わらない）。

---

## 7. Responsibility

**Retry Metrics FoundationはRead Only Foundationである。** 本Foundationは`.run/retry_runtime_log.jsonl`（Logging、v6.2.0が書き込んだJSON Lines）を読み取り、`RetryMetricsSnapshot`を生成する集計処理のみを担当し、Runtime側（Retry Runtime Pipeline・Retry Queue・Scheduler等）へは一切書き込み・通知・フィードバックを行わない（4.1節「Runtimeへのフィードバック」参照）。

| コンポーネント | 責務 | 変更有無 |
|---|---|---|
| `RetryRuntimeLogRecord`（新規） | `.jsonl`の1行を表す不変の値オブジェクト | 新規追加 |
| `RetryRuntimeLogReader`（新規） | `.jsonl`ファイルの読み取り・パースのみ。集計は一切行わない | 新規追加 |
| `RetryMetricsCalculator`（新規） | `list[RetryRuntimeLogRecord]`から集計値を計算するのみ。ファイルI/Oは一切行わない | 新規追加 |
| `RetryMetricsSnapshot`（新規） | 集計結果を表すImmutable（読み取り専用）な値オブジェクト。生成後は変更されない。Monitoring等の消費者は参照のみで更新を行わない | 新規追加 |
| `RetryRuntimeCycleLogger`（v6.2.0） | 無変更。本Releaseからは読み取られるのみで、参照も依存もされない | 無改修 |
| `RetryRuntimeLock` / `RetryRuntimeShutdown` / `RetryRuntimeLoop` / `RetryRuntimeOrchestrator` / `RetryManager` | 無変更（ユーザー指定の禁止事項）。本Foundationからのフィードバックは一切発生しない | 無改修 |
| `RetryCompositionRoot` | 無変更（消費者不在の先行実装のため配線しない） | 無改修 |

「読み取り（`RetryRuntimeLogReader`）」と「集計（`RetryMetricsCalculator`）」を別クラスに分離しているのは、`RetryQueueUpdateDecider`（判定）と`RetryQueueRemovalExecutor`（実行）のように、本プロジェクト全体で一貫している「判定・変換ロジック」と「I/O」を分離する設計慣習に従うためである。

---

## 8. Dependency

- `retry_metrics` → 標準ライブラリのみ（`json` / `pathlib` / `dataclasses`）
- `retry_metrics`は他の`src/*`パッケージのいずれもimportしない（新規の一方向依存を作らない、`retry_history`・`retry_queue`と同じ「独立した葉パッケージ」）
- 既存パッケージから`retry_metrics`への依存も本Releaseでは発生しない（消費者不在の先行実装。v3.3.0 Retry Scheduler Integration・v5.5.0 Retry Runtime Loop Foundationと同型のパターン）
- 新しい外部パッケージ（pip）は追加しない

---

## 9. Failure Policy

| 状況 | 方針 | 理由 |
|---|---|---|
| `.run/retry_runtime_log.jsonl`が存在しない | 例外を送出せず空リストを返す | Retry Runtimeが未実行の状態は正当なシステム状態であり、エラーではない |
| 個々の行のJSONパース失敗（例：クラッシュ時の不完全な末尾行） | その行のみスキップし、stderrへWARNINGを出力して処理を継続する | 追記型ログの性質上、末尾の不完全な行はありふれた事象であり、1行の欠損のために集計処理全体を失敗させるべきではない（`RetryRuntimeCycleLogger`の書き込み側ベストエフォート方針と対称的な、読み取り側のベストエフォート） |
| ファイル自体が読めない（権限エラー等のOSError） | 例外をそのまま送出する（fail-fast） | 「データがまだない」という正常系ではなく環境異常であり、隠蔽すると「実際には読めていないのに0件」という誤った集計結果を招くリスクがあるため |
| `RetryMetricsCalculator.calculate([])` | 例外を送出せず`cycle_count=0`の`RetryMetricsSnapshot`を返す | Null Objectパターンではなく、「0件という正常なデータ」として扱う |

Exit Code Policy（`docs/design/retry_runtime_script_entry_point_foundation.md` 2.4節）・Runtime Failure Policy（v6.2.0）とは別の文脈（本Foundationは非同期のクエリ処理であり、Retry Runtime本体のプロセスライフサイクルとは無関係）であるため、両者を混同しないよう明記する。

---

## 10. DI構成

- `RetryRuntimeLogReader`は`log_path: Path`をConstructor Injectionで保持する（`RetryRuntimeCycleLogger.__init__(log_path: Path)`と対称的な設計）
- `RetryMetricsCalculator`は状態を持たないStatelessコンポーネントとし、無引数コンストラクタ・`calculate(records) -> RetryMetricsSnapshot`という純粋関数的APIとする（`RetryQueueUpdateDecider`等、既存の多くのDecider系コンポーネントと同型）
- 本Releaseでは`RetryCompositionRoot`への配線を行わない（Composition Root変更なし）
- 将来CLI／Retry Monitoring Foundationから利用する際は、呼び出し元が`RetryRuntimeLogReader(log_path=...)` → `RetryMetricsCalculator()`を自身で組み立てて呼び出す想定とし、`RetryCompositionRoot`への追加は実際の消費者が現れた時点で改めて検討する

---

## 11. Future Extension

### 11.1 Retry Monitoring Foundation（次候補、責務境界の明確化）

Retry Monitoring Foundationは、`RetryMetricsSnapshot`（本Foundationの出力）を入力として受け取り、閾値（例：`enqueue_success_ratio`が一定値を下回った場合等）に基づいて健全性ステータス（例：`HEALTHY` / `DEGRADED` / `UNHEALTHY`等のEnum）を判定するだけの、別の独立パッケージ（例：`src/retry_monitoring/`）として設計する。

**責務境界（一方向依存、Architecture Review反映）**：

```
Metrics（本Foundation。JSONLを集計するだけ）
    │
    │  RetryMetricsSnapshot（Immutable、6.4節）を渡す
    ▼
Monitoring（将来。Snapshotを参照し健全性を判定するだけ）
    │
    │  健全性ステータス（Enum等）を渡す
    ▼
Alert（さらに将来。通知先へ送るだけ）
```

| 層 | 責務 | 入力 | 出力 |
|---|---|---|---|
| Retry Metrics（本Foundation） | 「何が起きたかを数える」 | `.run/retry_runtime_log.jsonl` | `RetryMetricsSnapshot`（生の集計値） |
| Retry Monitoring（将来） | 「その数値が問題かどうかを判断する」 | `RetryMetricsSnapshot` | 健全性ステータス（Enum等） |
| Alert（さらに将来） | 「判断結果を通知する」 | 健全性ステータス | Slack／メール等への通知（外部I/O） |

**依存の向きは`Metrics → Monitoring → Alert`の一方向のみとし、逆方向の依存は禁止する。**

- Retry Monitoringは`.run/retry_runtime_log.jsonl`を直接読み取らず、必ず`RetryMetricsSnapshot`経由でのみRetry Metricsの結果を消費する（`retry_monitoring → retry_metrics`の一方向依存のみを許可し、`retry_monitoring → retry_runtime_logging`という直接依存は作らない）。これにより、ログの生データ形式が変わってもMonitoring側は`RetryMetricsSnapshot`の型が変わらない限り影響を受けない
- **`Monitoring → Metrics`への逆依存は禁止する。** Metrics側（`RetryMetricsCalculator` / `RetryMetricsSnapshot` / `RetryRuntimeLogReader`）は、Monitoringパッケージの存在を一切知らない・importしない。Monitoring側の都合（閾値・アラート要件等）によってMetrics側の集計ロジックやSnapshotの型が変更されることがあってはならない
- 同様に`Alert → Monitoring`も一方向のみとし、Alert側の都合でMonitoringの判定ロジックが変更されることも禁止する
- 6.4節のとおり`RetryMetricsSnapshot`はImmutableであるため、Monitoringが受け取ったSnapshotを書き換えて後続処理へ渡す、といった経路も構造的に発生し得ない

Monitoring自体も本Foundationと同じくFoundation First原則に従い、まず閾値判定ロジックのみを持つ「消費者不在の先行実装」として着手し、実際の通知（Slack／メール等の外部I/O）は責務が異なる別の後続Releaseへ切り出すことを推奨する（外部I/O変更は単独でArchitecture Release相当の検討を要するため）。

### 11.2 Retry Metrics CLI/Report Wiring Foundation

`scripts/show_retry_metrics.py`等を新設し、`RetryMetricsSnapshot`を人間可読な形式（`format_summary()`と対称的な`format_metrics_summary()`）でコンソール表示する。v5.3.0（Run Once Foundation）とv5.4.0（Script Entry Point Foundation）の分離と同型のパターン。

### 11.3 Retry Runtime Log Schema Extension

真の成功率（`RetryOutcome`別内訳）・試行回数分布を計算可能にするため、`RetryRuntimeCycleLogger`のJSON Schemaへフィールド追加（例：`execution_retried` / `execution_skipped` / `execution_dry_run`のoutcome別内訳）を行う。v6.2.0設計書が明示的に許容する「将来の変更はフィールド追加のみ」という方針に沿うが、既存の永続化スキーマへの変更（永続化変更）であるため、本Foundationとは独立したArchitecture Reviewを要する。

### 11.4 Queue滞留時間の計測

現状`RetryQueueManager`はin-memoryかつenqueue時刻を保持しないため、これを計測可能にするには`RetryQueueItem`側の設計変更が前提となる。`RetryQueueManager` / `RetryQueueItem`は本Foundationの禁止対象ではないが、影響範囲が大きいため独立した検討課題として切り出す。

---

## 12. Alternatives

| # | 案 | 却下理由 |
|---|---|---|
| 1 | Retry MetricsとRetry Monitoringを1つのReleaseとして一括実装する | Foundation First原則（1バージョン=1目的）に反する。過去の全Release（v3.0.0〜v6.2.0）が一貫してこのパターンを避けてきた実績と矛盾し、集計ロジックと閾値判定ロジックが未分離のまま実装されるリスクが高い |
| 2 | `RetryRuntimeCycleLogger`（v6.2.0）に`read_all()`のような読み取りAPIを追加する | 同クラスの責務を「1レコード追記」から拡張することになり、v6.2.0で確定した責務（書き込み専用）を変更してしまう |
| 3 | `RetryRuntimeLogRecord`を`retry_runtime_logging`側に定義し`retry_metrics`がimportして再利用する | `retry_runtime_logging → retry_metrics`の新規依存、または共有定義パッケージの新設のいずれかが必要になり依存関係が複雑化する。JSON Schemaは契約として既に固定されているため、独自にdataclassを定義し直す方が既存の「型参照ではなく契約（shape一致）による疎結合」パターンと整合する |
| 4 | Pandas等の集計ライブラリを利用する | 標準ライブラリのみで完結する既存方針（Dependency変更を避ける）を踏襲。単純な合計・比率計算のみのため外部ライブラリは不要 |

---

## 13. Rejected Designs

| # | 却下した設計 | 理由 |
|---|---|---|
| 1 | MonitoringをMetricsと同一パッケージ内のサブモジュールとして実装する | ユーザー要求「Metricsは独立Package」「MonitoringはMetricsとの責務境界を明確化する」に反する。同一パッケージ内に置くと責務境界があいまいになり、閾値判定ロジックが集計ロジックへ混入するリスクが高い |
| 2 | `RetryMetricsSnapshot`をmutableなclassとして実装する | 既存の`RetryRuntimeCycleResult` / `RetryQueueUpdateDecision`等、Result系オブジェクトが一貫してfrozen dataclassである慣習と整合させるため |
| 3 | Metrics計算をRuntime Pipeline内（例：`RetryRuntimeOrchestrator.run_once()`内）でリアルタイムに行う | ユーザー指定「Runtime Pipeline変更禁止」に直接抵触する。v6.2.0のLogging Foundationが確立した「Pipeline外・CLI層のみ」という前例を踏襲すべきと判断した |
| 4 | `.run/retry_runtime_log.jsonl`をSQLiteへ都度変換してからクエリする | 新しい永続化フォーマット（SQLite）の追加はDependency変更・永続化変更に該当し、Foundation Firstの精神に反する。JSON Linesをそのまま読み取る軽量な実装で十分 |

---

## 14. Risks

- **ログファイル肥大化**（v6.2.0からのKnown Risk再掲）：`--loop`長時間運用時、`.run/retry_runtime_log.jsonl`が際限なく成長する。本Foundationはファイル全体を毎回読み込む設計のため、ファイルサイズに比例してメモリ使用量・処理時間が増加する。ログローテーションが実装されるまでは大規模ファイルに対する読み取り性能はTechnical Debtとして残る
- **期間指定機能の欠如**：`RetryMetricsCalculator`は渡された`list[RetryRuntimeLogRecord]`全件を対象とする。期間フィルタリングは呼び出し元（将来のCLI/Monitoring）の責務とし、本Foundationでは実装しない。呼び出し元が実装を誤ると意図せず全期間集計になり得る
- **「成功率」という言葉の誤解リスク**：`enqueue_success_ratio`はEnqueue段階の成功率であり、Retry実行自体の成否（`RetryOutcome`）を表すものではない。ROADMAPが元々意図していた「成功率」とは異なる指標であるため、利用者が誤解しないよう命名・ドキュメントで明確に区別する必要がある
- **不完全な行の静かなスキップ**：クラッシュ時の不完全な末尾行を無警告的に集計対象から除外するため、集計値が実際のサイクル数よりわずかに少なく出る可能性がある（ベストエフォート方針とのトレードオフ）

---

## 15. Technical Debt

- 真の成功率（`RetryOutcome`別内訳）・試行回数分布・Queue滞留時間は、現行の固定JSON Schema（v6.2.0）だけでは算出不能。これらの実現にはスキーマ拡張（11.3節）が必要であり、本Releaseでは意図的に対象外とした
- ログローテーション未対応（v6.2.0からの継続Technical Debt）。ファイルサイズが増大した場合の読み取り性能は本Releaseでは評価・対応しない
- 期間フィルタリングAPIが存在しないため、「直近1時間のみ」等の一般的な運用要求には呼び出し元が独自にフィルタリングを実装する必要がある

---

## 16. Known Issues

- 新規Known Issueの発生は本Release（Architecture Design段階）では未確定。実装完了後、既存Architecture Guard（他パッケージが本Releaseの新規パッケージの有無を前提としていないことを確認するテスト等）への影響有無を確認し、該当があれば`[KI-30]`以降として`docs/CHANGELOG.md`へ記録する（2026-07-14時点の最新は`[KI-29]`）
- 既知の制約（本設計時点で判明済み）：
  - `.run/retry_runtime_log.jsonl`が存在しない環境（Retry Runtimeが一度も実行されていない）では、`RetryMetricsSnapshot`は全項目0件で返る。これはエラーではなく正常系である
  - 本Foundationは`--dry-run`実行分のサイクルも通常サイクルと区別なく集計対象に含める（`dry_run_cycle_count`で内訳のみ提供）。dry_run分を集計から除外するかどうかは呼び出し元の判断に委ねる

---

## Status

- [x] Architecture Designドラフト作成（Claude Code）
- [x] ChatGPT Architecture Review 1回目・フィードバック反映（RetryMetricsSnapshot Immutability明確化／Read Only Foundation明記／Metrics→Monitoring→Alert一方向依存の補強）
- [x] ChatGPT Architecture Review（最終）Approve取得
- [x] 人間の実装承認
- [x] 実装着手・完了（`src/retry_metrics/`新設。Runtime Pipeline・`RetryRuntimeCycleLogger`はいずれも無改修）
- [x] Test Review（新規E2E 174/174 PASS。既存回帰：v5.9.0 64/64・v6.0.0 43/43・v6.1.0 44/44・v6.2.0 64/64、いずれも0 diff）
- [x] CHANGELOG／ROADMAP／architecture.md反映
- [ ] Code Review（ChatGPTによる実装差分レビュー、未実施）
- [ ] Release Review
- [ ] commit／push
