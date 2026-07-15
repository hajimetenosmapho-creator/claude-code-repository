# Retry Notification CLI Report Wiring Foundation — Architecture Design（v6.8.0）

作成日：2026-07-15
作成者：Claude Code（Architecture Designドラフト・Review指摘反映・Documentation）／ChatGPT（Architecture Review）／ユーザー（最終承認）
状態：**Design Freeze**
分類：**Architecture Release**（development_workflow.md 6章・7章。新規Public API・新規Dependency方向の確立を伴うため）

---

## 1. Release概要

Release 6.3〜6.7で完成した以下5つの「消費者不在の先行実装」を、単一CLIスクリプトから初めて連続実行し、人間可読なReportとして標準出力へ表示する。

```text
RetryRuntimeLogReader
    ↓
RetryMetricsCalculator
    ↓
RetryHealthEvaluator
    ↓
RetryAlertEvaluator
    ↓
RetryNotificationEvaluator
    ↓
RetryNotificationMessageBuilder
    ↓
Retry Notification CLI Report
```

目的は、人間がMetricsからNotification Messageまでの判定過程を確認できるようにすることである。Runtime Pipelineへの本組み込みは行わない。

`RetryCompositionRoot`・`RetryRuntimeOrchestrator`・`scripts/run_retry_runtime.py`のいずれも、現時点で`retry_metrics` / `retry_monitoring` / `retry_alert` / `retry_notification` / `retry_notification_message`のいずれも参照していないことを実装調査で確認済みである（本Release着手前の事実確認）。

## 2. Release分類

**Architecture Release**（development_workflow.md 6章・7章）。

Fast Track候補条件（development_workflow.md 7章）との照合：

| 条件 | 該当有無 | 内容 |
|---|---|---|
| Public API変更 | なし | 既存5パッケージのシグネチャ変更なし |
| Constructor変更 | なし | 同上 |
| Composition Root変更 | なし | `RetryCompositionRoot`は無改修 |
| Layer変更 | なし | 新規`src/`パッケージを追加しない |
| **Dependency変更** | **あり（新規Public API・新規依存方向）** | `scripts/show_retry_notification.py`が5パッケージのpackage rootへ新規依存する。CLI Entry PointからFoundation層への新しい依存方向が確立されるため、既存Fast Track相当（軽微なCLIオプション追加）とは性質が異なる |
| 永続化変更 | なし | 該当なし |
| Event変更 | なし | 該当なし |
| 外部I/O変更 | なし | ファイル読み取り（既存契約の再利用）のみ |

Layer変更・Dependency変更のいずれにも厳密には該当しないという見方も可能だが、5パッケージ全体を初めて連続実行するという性質上、development_workflow.md 4章「判断に迷った場合はArchitecture Releaseを選択する」に従い、**Architecture Release**として扱う。ユーザー指示により確定済み。

## 3. Status

```text
Architecture Design：Completed
Architecture Review：Approved
Test Review：Approved
Code Review：Approved
Implementation：Completed
Release Review：Approved
```

## 4. 現状と背景

- v6.3.0〜v6.7.0で、`retry_metrics`（Read Only）→`retry_monitoring`（Judgment Only）→`retry_alert`（Judgment Only）→`retry_notification`（Judgment Only）→`retry_notification_message`（Value Building Only）という5段階の一方向パイプラインが完成した。
- 5パッケージはいずれも「消費者不在の先行実装（Foundation First）」であり、`RetryCompositionRoot`・`RetryRuntimeOrchestrator`・`scripts/run_retry_runtime.py`のいずれからも配線されていないことを実装のgrep調査で確認済みである。
- 人間がこのパイプラインの動作（Metricsの集計値から最終的なNotification Messageまでの判定過程）を確認する手段は、本Release着手前の時点で一切存在しない。
- 本Releaseは、Runtime Pipelineへ本組み込みせず、CLI Report専用の最小Wiringとしてこの確認手段を提供する。

## 5. Design Goal

1. Release 6.3〜6.7の既存Public Contractを変更しない
2. 既存5パッケージを無改修に保つ
3. `RetryCompositionRoot`を変更しない
4. `RetryRuntimeOrchestrator`を変更しない
5. `RetryRuntimeCycleResult`を変更しない
6. `scripts/run_retry_runtime.py`を変更しない
7. 外部送信を行わない
8. Runtime実行を行わない
9. 既存Retry Runtime Logを読み取るだけとする
10. CLIからパイプラインの結果を人間可読形式で確認可能にする
11. `NO_NOTIFICATION`時に`RetryNotificationMessageBuilder`を呼ばない
12. Message生成可能性とNotification評価の正常性を混同しない
13. CLI専用Wiringと将来Runtime Wiringの責務境界を明示する
14. Foundation Firstを維持する
15. 1 Release＝1目的を維持する

## 6. Non-Goals

8章 Out of Scopeに同じ。加えて、`.env`（`python-dotenv`）は読み込まない：5パッケージはいずれも環境変数を一切参照しない（`RetryHealthThresholds`はコード上の固定デフォルト値）ことを実装確認済みであり、`run_retry_runtime.py`のdotenv読み込みは本Releaseには不要である。

## 7. In Scope

- `scripts/show_retry_notification.py`（単一スクリプト）
- `.run/retry_runtime_log.jsonl`の読み取り（Read Only）
- `--log-path`による入力パス上書き
- MetricsからNotification Messageまでの逐次評価（`build_report()`）
- `RetryNotificationCliReport`（scripts.show_retry_notificationモジュール固有のPublic Model）
- `build_report()` / `format_report()` / `main()`
- 人間可読Reportの標準出力
- Reader由来WARNINGの標準エラー出力（既存`RetryRuntimeLogReader`契約の再利用）
- CLI由来ERRORの標準エラー出力（新規、本Release固有）
- Exit Code Policy（20章）
- NO_NOTIFICATION時のMessage非生成
- E2E Test Strategy（24章）
- Regression Test Strategy（25章）
- Documentation Strategy（26章）

## 8. Out of Scope

- Retry Notification Channel Foundation
- Retry Notification Delivery／Sender Foundation
- Slack、メール、Discord等への実送信
- Network I/O
- 外部サービスI/O
- APIキー
- 認証情報
- Timeout
- Sender Retry
- Suppression
- Deduplication
- Rate Limiting
- Recovery通知
- Notification履歴
- Runtime／Scheduler Integration
- `RetryCompositionRoot`配線
- `RetryRuntimeOrchestrator`変更
- `RetryRuntimeCycleResult`変更
- `scripts/run_retry_runtime.py`変更
- 既存5 FoundationのPublic API変更
- Severity-aware Message
- Message Template
- Localization
- title
- timestamp
- reason
- 対応手順
- JSON出力
- 設定ファイル拡張
- 環境変数拡張
- `.env`読み込み
- `python-dotenv`
- ファイル書き込み
- JSONL追記
- デーモン化
- Loop実行
- `--json`
- `--watch`
- `--loop`
- `--interval`
- `--channel`
- `--send`
- `--severity`
- `--config`

---

## 9. Proposed Architecture

CLIスクリプト（`scripts/show_retry_notification.py`）内で5つのEvaluator/Builderを直接Composition（`build_report()`）し、結果をモジュール内Public Model（`RetryNotificationCliReport`）へ集約したうえで、純粋関数（`format_report()`）で文字列化し標準出力へ表示する。

**単一スクリプトを採用する理由**：複数の`show_retry_*`スクリプト（Metrics別／Health別／Alert別等）を採用しないのは、(a) 各段階の組み立てコードが重複すること、(b) 「パイプライン全体を確認可能にする」という単一目的（1 Release＝1目的）に対し複数スクリプトは実質的に複数Releaseを束ねる結果になること、(c) 中間値（Metrics/Health/Alert）を1つのReportに含めることで「なぜこの結果になったか」を1回のコマンド実行で確認できるという利用者価値が最大化されることによる。

**CLIスクリプト内直接Compositionを採用する理由**：5コンポーネントはいずれもStateless（内部状態を持たない）であり、共有インスタンス管理を必要としない。v5.1.0 Retry Composition Root Foundationが`RetryQueueManager`/`RetryHistoryManager`という**Stateful**な共有インスタンスのために新設された事情とは異なり、本Releaseの対象コンポーネントに状態共有の必要性はない。したがって、CLIスクリプトが独自にインスタンスを生成しても、状態の重複・不整合は原理的に発生しない。将来Runtime Integrationが`RetryCompositionRoot`へ同じ5コンポーネントを配線する場合も、両者は同じPublic APIクラスに対する独立した呼び出し元にすぎず、競合しない（この構造的重複は30章Technical Debtとして記録する）。

## 10. Data Flow

```
.run/retry_runtime_log.jsonl（Read Only。デフォルトまたは --log-path で指定）
    ↓ RetryRuntimeLogReader.read()
list[RetryRuntimeLogRecord]
    ↓ RetryMetricsCalculator.calculate()
RetryMetricsSnapshot
    ↓ RetryHealthEvaluator.evaluate()
RetryHealthReport
    ↓ RetryAlertEvaluator.evaluate()
RetryAlert
    ↓ RetryNotificationEvaluator.evaluate()
RetryNotificationDecision
    ↓（status is NOTIFYの場合のみ）RetryNotificationMessageBuilder.build()
RetryNotificationMessage | None
    ↓
RetryNotificationCliReport（scripts/show_retry_notification.py モジュール内Public Model）
    ↓ format_report()
str（末尾改行なし）
    ↓ main() の print()
標準出力（末尾改行1つ）
```

## 11. Dependency Direction

```text
scripts/show_retry_notification.py
    ↓
retry_metrics
retry_monitoring
retry_alert
retry_notification
retry_notification_message
```

これは、Composition起点（CLI Entry Point）から各Layerへの依存である。次の`src`パッケージ間の直前Layer依存原則とは区別する。

```text
retry_notification_message
    ↓
retry_notification
    ↓
retry_alert
    ↓
retry_monitoring
    ↓
retry_metrics
```

**確定事項**：

- データフロー（10章、処理の実行順序）とimport依存方向は別概念であり、混同しない
- CLI Entry Pointは複数Layerを横断してimportしてよい（Composition起点としての依存）
- `src`パッケージ間の既存の直前Layer依存原則（上記後者の図）は本Releaseでも変更しない
- 既存5package間へ新しいimportを追加しない（逆依存も発生させない）
- CLIは各パッケージのpackage root（`__init__.py`が公開するPublic API）のみをimportし、内部モジュール（例：`retry_metrics.retry_runtime_log_reader`）へは直接importしない
- `RetryCompositionRoot`から本CLIへの依存を作らない
- `RetryRuntimeOrchestrator`から本CLIへの依存を作らない
- `scripts/run_retry_runtime.py`から本CLIへの依存を作らない

## 12. CLI Entry Point

```text
projects/03_game_content_ai/scripts/show_retry_notification.py
```

単一スクリプトとする。複数の`show_retry_*`スクリプトは作成しない（9章参照）。

## 13. Composition責務

`build_report()`関数内で、以下5コンポーネントを直接Compositionする。

```python
reader = RetryRuntimeLogReader(log_path=log_path)
calculator = RetryMetricsCalculator()
health_evaluator = RetryHealthEvaluator()
alert_evaluator = RetryAlertEvaluator()
notification_evaluator = RetryNotificationEvaluator()
message_builder = RetryNotificationMessageBuilder()
```

新規`src/`パッケージは作成しない。既存`RetryCompositionRoot`も変更しない。

---

## 14. Public API

```python
def build_report(
    log_path: Path,
) -> RetryNotificationCliReport:
    ...


def format_report(
    report: RetryNotificationCliReport,
) -> str:
    ...


def main(
    argv: list[str] | None = None,
) -> int:
    ...


if __name__ == "__main__":
    sys.exit(main())
```

- `scripts/show_retry_notification.py`は`src/*`のpackageではないため、`__all__`は定義しない。理由は「非公開だから」ではなく、**scripts/配下のEntry Pointモジュールは元々`__all__`を持たないという本プロジェクトの既存慣習（`scripts/run_retry_runtime.py`を実装確認済み。`__all__`定義なし）に合わせるため**である。
- 既存`scripts/run_retry_runtime.py`の`main() -> None`とは異なり、本Releaseは`main(argv: list[str] | None = None) -> int`という明示的な戻り値型を採用する。これは意図的な差分であり、理由は以下のとおり（32章 Architecture Decision Summaryにも記録）：
  - E2Eテストが`SystemExit`を捕捉することなく、`main(["--log-path", ...])`の戻り値を直接assertできる
  - 本CLIは非0となる条件が複数（`OSError` / `ValueError`）存在し、各条件のExit Codeを戻り値として明示的に区別できる
  - argparseの構文エラー（`SystemExit 2`）は`main()`内で捕捉しないため、この方針と両立する

---

## 15. RetryNotificationCliReport Contract

**方針**：`RetryNotificationCliReport`は、`src/*` FoundationのPublic APIには追加しない。ただし、`scripts.show_retry_notification`モジュール内では、`build_report()`の戻り値を構成する**CLIモジュール固有のPublic Model**として扱う。

```text
scripts.show_retry_notificationモジュール固有のPublic Model
≠
src FoundationのPublic API
```

| 確定事項 | 内容 |
|---|---|
| 定義位置 | `scripts/show_retry_notification.py`モジュール直下 |
| クラス名 | `RetryNotificationCliReport`（先頭アンダースコアを付けない） |
| 型 | `frozen dataclass` |
| フィールド数 | 5つのみ |
| `__all__` | 定義しない。理由は「`__all__`がないから非公開」ではなく、**scripts/配下のEntry Pointモジュールが元々`__all__`を持たないという本プロジェクトの既存慣習（`scripts/run_retry_runtime.py`）に合わせるため** |
| `src/*` packageのPublic API | 含めない。いずれの`__init__.py`の`__all__`にも追加しない |
| 他Foundationからの依存 | されない。`retry_metrics`〜`retry_notification_message`のいずれもこの型を知らない・importしない |
| 責務 | CLI用の値集約のみ。Builder・Evaluator・Formatterの責務は一切持たない（`build_report()`が生成し、`format_report()`が読み取るだけの受け渡し用データ） |

```python
@dataclass(frozen=True)
class RetryNotificationCliReport:
    metrics: RetryMetricsSnapshot
    health_report: RetryHealthReport
    alert: RetryAlert
    notification_decision: RetryNotificationDecision
    message: RetryNotificationMessage | None
```

`message`フィールドを`RetryNotificationMessage | None`とすることで、`NO_NOTIFICATION`（Messageが存在しない正常系）をOptionalの具体的な値として表現する。これはTotal Function契約と整合し、v6.7.0設計書が採用した「Optionalを返すAPIより明示的な値を優先する」設計判断とは異なる文脈（本Reportはあくまで**CLI表示用の集約型**であり、Evaluator/Builder自体のAPI契約ではない）であるため、Optional型の使用がv6.3.0〜v6.7.0の設計判断と矛盾するものではない。

---

## 16. NO_NOTIFICATION Contract

```text
RetryNotificationStatus.NO_NOTIFICATION
```

は正常系である。ただし、

```text
RetryNotificationMessageBuilder.build(NO_NOTIFICATION)
```

は既存契約どおり`ValueError`である（v6.7.0設計書12章 NO_NOTIFICATION Semantics）。

CLI側の制御：

```python
alert = alert_evaluator.evaluate(health_report)              # 未対応Statusで ValueError（伝播）
decision = notification_evaluator.evaluate(alert)            # 未対応Levelで ValueError（伝播）

if decision.status is RetryNotificationStatus.NOTIFY:
    message = message_builder.build(decision)
elif decision.status is RetryNotificationStatus.NO_NOTIFICATION:
    message = None
else:
    raise ValueError(
        "show_retry_notification: "
        f"未対応のRetryNotificationStatusです: {decision.status!r}"
    )
```

最後の`else`分岐は現状到達不能である（`RetryNotificationStatus`は`NOTIFY`/`NO_NOTIFICATION`の2値のみ）。既存5パッケージすべてが徹底している「既知値の網羅的分岐＋フォールバック禁止」という設計慣習をCLI側でも一貫させるために追加する。将来`RetryNotificationStatus`が拡張された場合に、CLIが黙って`None`扱いするような不整合を防ぐ防御的分岐である。

| 状態 | 判定 | Message | Report | Exit Code |
|---|---|---|---|---|
| `NO_NOTIFICATION` | 正常 | Message Builderを呼ばない、`message`は`None` | 正常Report | 0 |
| `NOTIFY` | 正常 | Message Builderを呼ぶ、`message`あり | 正常Report | 0 |
| 未対応値 | 契約違反 | フォールバックしない、`ValueError` | Reportなし | 1 |

**「Message生成可能性」と「Notification評価の正常性」の混同禁止**：`NO_NOTIFICATION`は`RetryNotificationEvaluator`にとって正常な明示値であり、CLIにとっても「Message欄に何を表示するか」という表示上の分岐にすぎない。一方、`RetryNotificationMessageBuilder.build()`が`NO_NOTIFICATION`を拒否する（`ValueError`を送出する）のは、Builder自身の契約違反検知であり、CLIはこの契約違反を発生させないよう`if`/`elif`で制御する。既存`RetryNotificationMessageBuilder`へのNO_NOTIFICATION対応追加は行わない（8章 Out of Scope）。

---

## 17. CLI Output Contract

出力仕様はArchitecture Design段階で確定する。

### タイトル

```text
Retry Notification Report
```

### 区切り線

```python
"=" * 50
```

### セクション順（固定）

```text
Metrics
Health
Alert
Notification
Message
```

### Metrics表示項目（4項目に限定）

```text
cycle_count
period_start
period_end
enqueue_success_ratio
```

**実装確認済みの事実**：`src/retry_monitoring/retry_health_evaluator.py`の`RetryHealthEvaluator.evaluate()`は`ratio = snapshot.enqueue_success_ratio`のみを参照し、`RetryMetricsSnapshot`が保持する他の12フィールド（`enqueue_scanned_total`等）は一切参照しない。したがって`enqueue_success_ratio`は**現在のRetryHealthEvaluatorが参照する唯一の判定根拠**である。`cycle_count` / `period_start` / `period_end`は判定対象の母数・期間を示す文脈情報として併記する。その他のMetricsフィールドは本Releaseでは表示しない（将来のRetry Metrics CLI Wiring Foundationの責務として切り出す）。

### ラベル（確定）

```text
[Metrics]
  対象サイクル数
  記録開始
  記録終了
  Enqueue成功率

[Health]
  ステータス

[Alert]
  レベル

[Notification]
  ステータス

[Message]
  （ラベルなし。本文またはNO_NOTIFICATION文をそのまま1行表示）
```

### 表示値の契約

#### `cycle_count`

```text
10進整数（str(cycle_count)）
```

#### `period_start` / `period_end`

型（実装確認済み）：`str | None`

実装確認済みの事実：

- `RetryRuntimeCycleLogger`（`src/retry_runtime_logging/retry_runtime_cycle_logger.py`）が`datetime.now(timezone.utc).isoformat()`で`timestamp`フィールドとして書き込む
- `RetryMetricsCalculator`（`src/retry_metrics/retry_metrics_calculator.py`）が`min(timestamps)` / `max(timestamps)`（文字列の辞書順比較）で`period_start` / `period_end`を算出する
- CLIは`RetryMetricsSnapshot.period_start` / `period_end`が保持する文字列を**そのまま表示**する
- CLI側で再フォーマット・タイムゾーン記号の付与や変更は行わない（`Z`等を推測で追加しない）

値がない場合：

```text
（記録なし）
```

#### `enqueue_success_ratio`

値がある場合：

```python
f"{ratio:.2f}"
```

例：`0.00` / `0.83` / `1.00`

値がない場合：

```text
（算出不能）
```

#### Enum

```text
.value
```

例：`HEALTHY` / `NONE` / `NO_NOTIFICATION` / `DEGRADED` / `WARNING` / `NOTIFY` / `UNHEALTHY` / `CRITICAL`

#### Message

NOTIFY時：

```text
RetryNotificationMessage.body
```

NO_NOTIFICATION時：

```text
（通知対象ではないため、Messageは生成されません）
```

#### 空ログ時の注記

`cycle_count == 0`の場合、`[Metrics]`セクション冒頭へ次を追加する。

```text
（Retry Runtimeの実行記録がありません）
```

### 通常時Report例

```text
==================================================
Retry Notification Report
==================================================
[Metrics]
  対象サイクル数     : 12
  記録開始           : 2026-07-14T00:00:00.123456+00:00
  記録終了           : 2026-07-15T00:00:00.654321+00:00
  Enqueue成功率      : 0.83

[Health]
  ステータス         : DEGRADED

[Alert]
  レベル             : WARNING

[Notification]
  ステータス         : NOTIFY

[Message]
  Retry Runtimeで通知対象の状態が検出されました。詳細を確認してください。
==================================================
```

（日時はCLIが加工した値ではなく、`RetryMetricsSnapshot`が保持する文字列をそのまま表示した参考例である。実際の書式は`RetryRuntimeCycleLogger`の実装（`datetime.now(timezone.utc).isoformat()`）に依存する）

### 空ログ時Report例

```text
==================================================
Retry Notification Report
==================================================
[Metrics]
  （Retry Runtimeの実行記録がありません）
  対象サイクル数     : 0
  記録開始           : （記録なし）
  記録終了           : （記録なし）
  Enqueue成功率      : （算出不能）

[Health]
  ステータス         : HEALTHY

[Alert]
  レベル             : NONE

[Notification]
  ステータス         : NO_NOTIFICATION

[Message]
  （通知対象ではないため、Messageは生成されません）
==================================================
```

### 改行契約

```text
format_report()の戻り値：末尾改行なし（"\n".join()で構築するため構造的に末尾改行を持たない）
main()のprint(format_report(report))：標準の改行を1つだけ付与する
```

### Public Contract化の範囲

セクション見出し・ラベルの存在と順序、およびEnum `.value` / ratio小数第2位固定 / period文字列無加工表示という値の表示規則は、E2Eで固定するContractとする。区切り線の文字数等、純粋な見た目の微調整は本Contractの対象外とする。

---

## 18. CLI Argument Policy

```python
parser.add_argument(
    "--log-path",
    type=Path,
    default=_DEFAULT_LOG_PATH,
)
```

`--log-path`のみを追加する。argparseを使用する（`scripts/run_retry_runtime.py`が既にargparseを使用している一貫性を保つため）。

以下はOut of Scope（8章）：`--json` / `--watch` / `--loop` / `--interval` / `--channel` / `--send` / `--severity` / `--config`

## 19. Default Path Policy

既存`scripts/run_retry_runtime.py`のパターン（`_PROJECT_ROOT = Path(__file__).parent.parent`）と命名・算出方法を一致させる。

```python
_PROJECT_ROOT = Path(__file__).parent.parent

_DEFAULT_LOG_PATH = (
    _PROJECT_ROOT
    / ".run"
    / "retry_runtime_log.jsonl"
)
```

Working Directory基準にはしない。スクリプトファイル自身の位置から算出することで、どのディレクトリから実行しても同一ファイル（`scripts/run_retry_runtime.py` / `RetryRuntimeCycleLogger`が書き込む先と同一パス）を参照する。

## 20. Exit Code Policy

```text
正常処理：main()が0を返す

NOTIFY：0
NO_NOTIFICATION：0

OSError：main()が1を返す
ValueError：main()が1を返す

argparse構文エラー：argparse標準のSystemExit 2（main()内で捕捉しない）

予期しない例外（OSError／ValueError以外）：main()では捕捉せず伝播、Python標準の非0終了
```

通知状態（NOTIFY/NO_NOTIFICATION）やAlert LevelをExit Codeへ反映しない。Exit CodeはCLI処理の成功／失敗だけを表す。`scripts/run_retry_runtime.py`が明記する「独自のExit Code体系（成功/一部失敗/異常等の多段階区分）は導入しない」という方針をそのまま継承する。

## 21. I/O Policy

```text
標準出力：あり（Report本体）

標準エラー：あり（2種類、23章で区別）
    - Reader由来WARNING（既存RetryRuntimeLogReader契約の再利用、行単位パース失敗時）
    - CLI由来ERROR（本Release固有、[ERROR] {exc} 形式、OSError／ValueError捕捉時）

ファイル読み取り：あり（Read Only、RetryRuntimeLogReader経由）
ファイル書き込み：なし
Network I/O：なし
外部サービスI/O：なし

外部ライブラリ：追加なし（argparseは標準ライブラリ）

.env読み込み：なし
python-dotenv：不使用
```

「外部I/Oなし」と単純化せず、Read Only I/Oが1箇所存在すること、および標準エラー出力が性質の異なる2種類（既存Reader契約由来のWARNINGと本Release固有のERROR）から構成されることを明記する。

---

## 22. Error／Failure Policy

既存`RetryRuntimeLogReader`（`src/retry_metrics/retry_runtime_log_reader.py`）の実装契約を正確に反映する。

| 状況 | 結果 | 根拠（実装確認済み） |
|---|---|---|
| ファイル不存在 | `FileNotFoundError`をReaderが捕捉、`[]`を返す、正常Report、Exit Code 0 | `read()`内`except FileNotFoundError: return []` |
| 空ファイル | 有効Record 0件、正常Report、Exit Code 0 | `for line in f`が0回、`records=[]` |
| 一部不正JSON | 不正行だけスキップ、処理継続、Exit Code 0、stderrへWARNING | `except (json.JSONDecodeError, KeyError, TypeError) as e:`で該当行のみ`continue` |
| 全行不正JSON | 有効Record 0件、正常Report、Exit Code 0、各不正行についてstderr WARNING | 全行が上記except節を通り`records=[]`のまま終了 |
| 必須フィールド不足 | `KeyError`、Readerが行単位でスキップ、Exit Code 0 | 上記と同一except節 |
| 型不正 | `TypeError`、Readerが行単位でスキップ、Exit Code 0 | 上記と同一except節 |
| 読取不能（`FileNotFoundError`以外の`OSError`） | Readerから伝播、`main()`が捕捉、stderrへ`[ERROR]`、Exit Code 1 | Reader実装コメント「これ以外のOSError（権限エラー・パス構造異常等）はfail-fastでそのまま伝播させる」 |
| 評価中の`ValueError`（`RetryAlertEvaluator` / `RetryNotificationEvaluator`の未対応値、または16章末尾else分岐） | `main()`が捕捉、stderrへ`[ERROR]`、Exit Code 1 | `main()`の`except (OSError, ValueError)` |
| CLI引数不正 | argparse標準契約、SystemExit 2 | `main()`内で捕捉しない |

**Reader由来WARNINGの出力方式（実装確認済み）**：

```python
print(
    f"WARNING: Failed to parse runtime log line {line_number}: {exc}",
    file=sys.stderr,
)
```

`logging` / `warnings`モジュール / 独自Loggerはいずれも使用していない（`src/retry_metrics/retry_runtime_log_reader.py`を実装確認済み）。

**不正JSONとOSErrorを混同しない**：不正JSON（行単位のパース失敗）は既存Reader契約により**その行のみスキップしExit Code 0で処理継続**する事象であり、OSError（ファイル自体が読めない）は**fail-fastでExit Code 1**となる別事象である。両者を同一の「不正ログ」として扱わない。

---

## 23. Traceback Policy

### 想定済みの利用者・入力エラー（`OSError` / `ValueError`）

```text
main()で捕捉する
stderrへ最小ERRORメッセージ（[ERROR] {exc}）
Exit Code 1
Tracebackを表示しない
stdoutへ正常Reportを出さない
```

### 予期しないプログラムエラー（`OSError` / `ValueError`以外）

```text
main()では捕捉しない
Python標準の例外伝播
Tracebackはstderrへ出る（Pythonのデフォルト挙動。CLI側で特別な処理を追加しない）
非0終了
stdoutへ正常Reportを出さない
```

`except Exception:`のような過剰捕捉は行わない。

```python
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-path", type=Path, default=_DEFAULT_LOG_PATH)
    args = parser.parse_args(argv)

    try:
        report = build_report(args.log_path)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

`parser.parse_args(argv)`はtry節の外にあり、argparseの`SystemExit`（構文エラー時のExit Code 2）を捕捉しない。

**「すべての異常時にTracebackが漏れない」という契約にはしない**：`OSError` / `ValueError`についてのみTracebackを出さないことを保証し、それ以外の予期しない例外についてはPython標準のTraceback出力（stderr）を妨げない（バグの隠蔽を防ぐため）。

---

## 24. E2E Test Strategy

Working Tree／`git diff`状態は恒久E2Eへ含めない。既存production code無改修はRelease Review時にGitコマンドで確認する。

### Pipeline統合

1. HEALTHY → NONE → NO_NOTIFICATION
2. DEGRADED → WARNING → NOTIFY
3. UNHEALTHY → CRITICAL → NOTIFY
4. WARNINGとCRITICALが同一Messageへ収束
5. NO_NOTIFICATION時にMessage Builderを呼ばない

### File／Reader Contract

6. ファイル不存在 → Exit 0
7. 空ファイル → Exit 0
8. 一部不正JSON → WARNING＋Exit 0
9. 全行不正JSON → 有効Record 0件＋Exit 0
10. 読取不能パス（`OSError`）→ Exit 1
11. ReaderのWARNING方式（`print(..., file=sys.stderr)`、`"WARNING: Failed to parse runtime log line"`形式）が既存契約どおりであることの確認

### Exit Code

12. NOTIFY → 0
13. NO_NOTIFICATION → 0
14. OSError → 1
15. ValueError → 1
16. argparse構文エラー → SystemExit 2
17. 予期しない例外（`OSError`／`ValueError`以外）を`except Exception`等で握り潰していないこと

### stdout／stderr

18. 全行正常時はReportをstdoutへ出す
19. 全行正常時はstderrが空
20. 不正行スキップ時はstderrへWARNING
21. 不正行スキップ時は`[ERROR]`なし
22. OSError時はstdoutへReportなし
23. ValueError時はstdoutへReportなし
24. OSError／ValueError時はstderrへ`[ERROR]`
25. OSError／ValueError時はTracebackなし

### Output Contract

26. タイトル固定
27. セクション順固定
28. ラベル固定
29. Enum `.value`表現
30. ratio小数第2位固定（境界値`0.00`/`1.00`含む）
31. `period_start`／`period_end`の無加工表示
32. `None`時の`（記録なし）`表示
33. 空ログ注記（`cycle_count==0`時のみ）
34. NO_NOTIFICATION時のMessage文
35. `format_report()`が末尾改行を含まないこと
36. `main()`のstdout出力に末尾改行が1つだけあること

### CLI Argument

37. デフォルトログパス（`_DEFAULT_LOG_PATH`）の使用確認
38. `--log-path`による上書き確認
39. `type=Path`変換の確認

### Public Model／API

40. `RetryNotificationCliReport`が`frozen dataclass`であること（`FrozenInstanceError`確認）
41. フィールドが5つに限定されていること
42. `message`が`RetryNotificationMessage | None`であること
43. 既存5packageいずれの`__all__`にも`RetryNotificationCliReport`が追加されていないこと
44. `build_report()`の戻り値型が`RetryNotificationCliReport`であること
45. `format_report()`が同一入力に対し常に同一出力を返すこと（Pure Function）
46. `main(argv=None) -> int`のシグネチャ確認

### Dependency Direction

47. `show_retry_notification.py`が5パッケージのpackage rootのみをimportしていること
48. 内部モジュール（例：`retry_metrics.retry_runtime_log_reader`）を直接importしていないこと
49. 既存5package間のimport依存方向が不変であること
50. `retry_composition`のソースが`show_retry_notification`を一切参照していないこと
51. `retry_runtime_orchestrator`のソースが`show_retry_notification`を一切参照していないこと
52. `run_retry_runtime`モジュールのソースが`show_retry_notification`を一切参照していないこと

### I/O制約

53. ファイル書き込み系呼び出し（`open(..., "w")`等）が存在しないこと
54. Network／外部サービスライブラリの非import確認
55. argparse以外の外部ライブラリの非import確認
56. `.env` / `python-dotenv`の非import確認

### テスト方法に関する注意

- `ValueError`経路は、CLIモジュールが参照するEvaluatorまたは依存名をFakeへ一時差し替えて検証する。**本Releaseのためだけにproduction APIへDependency Injection用Constructorを追加しない**（既存5パッケージのPublic APIは無変更のまま、テストコード側でモジュール属性を差し替える）
- 予期しない例外については、可能な範囲でFakeから`RuntimeError`等を送出させ、`main()`が握り潰さず伝播させる振る舞いを確認する
- AST構造への過度な密結合は避け、依存方向の検証はimport文の存在確認を中心に、必要最小限の構造検査に留める
- Working Tree／`git diff`状態は恒久E2Eへ含めない

**想定件数**：24〜27シナリオ、90〜130アサーション程度。件数そのものは設計契約ではなく、Public Contract・Failure Policy・NO_NOTIFICATION契約・出力契約・Dependency Direction・既存Foundation無改修の構造的確認の網羅を優先する。最終件数はTest Reviewおよび実装内容に基づき確定する。

## 25. Regression Test Strategy

```text
既存Regression：v5.9.0〜v6.7.0
ベースライン：943/943 PASS
```

次を確認する：

- ベースライン件数不変
- FAILなし
- 終了コード0
- 警告なし
- Tracebackなし
- 既存Regressionファイル無改修

既存production code無改修の確認は、Release Review時に以下で行う（恒久E2EへGit状態を含めない）。

```bash
git diff --name-status
git status --short
```

---

## 26. Documentation Strategy

Release 6.8で更新予定の文書：

```text
projects/03_game_content_ai/docs/design/retry_notification_cli_report_wiring_foundation.md（本文書）
projects/03_game_content_ai/docs/architecture.md
projects/03_game_content_ai/docs/ROADMAP.md
projects/03_game_content_ai/docs/CHANGELOG.md
```

本工程（Architecture Design）では、新規設計書（本文書）のみを作成する。`architecture.md` / `ROADMAP.md` / `CHANGELOG.md`の更新は実装完了後のDocumentation Update工程で行う。

以下の既存Design Freeze済み設計書は**変更しない**：

```text
docs/design/retry_metrics_foundation.md
docs/design/retry_monitoring_foundation.md
docs/design/retry_alert_foundation.md
docs/design/retry_notification_foundation.md
docs/design/retry_notification_message_foundation.md
```

5パッケージが本Releaseで初めて実際の消費者を持つという事実は、本設計書・`architecture.md`・`ROADMAP.md`・`CHANGELOG.md`へ記録する方針とし、上記5設計書自体（設計内容）は変更しない。

## 27. Compatibility

新規スクリプトの追加のみであり、既存5パッケージのPublic APIへの後方互換性の影響はない。既存の呼び出し元（現状ゼロ）にも影響しない。

---

## 28. Risks and Mitigations

| Risk | Mitigation |
|---|---|
| CLI scriptが肥大化する | `build_report()` / `format_report()` / `main()`の3関数分離を維持し、Business Logicを増やさない |
| CLI scriptが第二のComposition Rootになる | Statelessコンポーネントのみを対象とし、共有インスタンス管理を必要としないことをスコープの前提として明記（9章） |
| 将来Runtime Wiringと重複する | 30章Technical Debtとして明示的に記録し、Runtime Integration設計時に統合要否を再検討する前提を残す |
| CLI Output Contractの将来変更コスト | セクション構造・ラベル・値の表示規則をContract化する一方、区切り線の文字数等の純粋な見た目は非Contractとする（17章） |
| Metrics表示項目の限定 | `enqueue_success_ratio`がHealth判定の唯一の根拠であることを実装確認済みの事実として明記し、4項目限定の妥当性を担保（17章） |
| ERROR文言の固定化 | E2Eでは`[ERROR]`プレフィックス・非0 Exit Code・Traceback不在の確認に留め、完全一致は求めない |
| 空ログと実際のHEALTHYの意味的混同 | 空ログ注記（`（Retry Runtimeの実行記録がありません）`）を明示表示し、利用者が区別可能にする |
| CLI専用Result型の過剰設計 | `RetryNotificationCliReport`をscript内定義に限定し、値集約以外の責務を持たせない（15章） |
| Foundationへの逆依存 | CLIはpackage rootのPublic APIのみをimportし、5package間の既存importには一切触れない（11章、E2E 47〜52で検証） |
| Reportと実送信の混同 | Out of Scope（Channel／Sender）を明示し、本ReleaseはValue確認専用と位置づける |
| Exit Codeと通知状態の混同 | Exit CodeはCLI処理の成功／失敗のみを表し、NOTIFY／NO_NOTIFICATIONいずれも0とする方針を明記（20章） |
| Reader WARNINGとCLI ERRORの混同 | 22章・24章で明確に別契約として区別（Reader由来は`WARNING:`プレフィックス・Exit 0と両立可能、CLI由来は`[ERROR]`プレフィックス・Exit 1） |
| Package Governance未整備 | 本Releaseは新規packageを追加しないため悪化させないが、解消もしない（30章） |

## 29. Alternatives Considered

| 案 | 却下理由 |
|---|---|
| Channel Foundationを先に実装 | Channel選択にMessage単体で重大度を判別できない未解決論点があり、消費者不在のままさらに層を重ねるより先にパイプライン全体の動作確認を優先すべき |
| Runtime Integrationへ直接進む | Runtime Pipeline中核（v6.2.0以降5回連続で無改修）への初めての変更となり影響範囲が最大。CLI Report Wiringで先に手動組み立ての実績を作る方が段階的でリスクが低い |
| `RetryCompositionRoot`へ5 Foundationを追加 | 本Releaseの明示的Out of Scope。Stateful性を要しないため現時点で追加する必然性がない |
| `scripts/run_retry_runtime.py`へReport表示を追加 | Runtime Pipeline本体（Enqueue〜History）とNotification Reportという異なる関心事が混在し、v5.3.0/v5.4.0が確立した「Execution ReleaseとEntry Point Releaseの分離」原則、および本Release自体の「`scripts/run_retry_runtime.py`変更禁止」制約に反する |
| 複数`show_*`スクリプト | 重複コード・1 Release＝1目的違反（9章） |
| `src/`に汎用Notification Pipeline Serviceを新設 | Package Governance悪化、CLI固有責務のsrc/混入（9章） |
| Result Objectなし（ローカル変数のみ） | `format_report()`を純粋関数としてテストする際、5つの独立したローカル変数を毎回引き回すより、1つのImmutableな入力にまとめた方がテストコードが単純になる |
| JSON出力 | 明示的Out of Scope。機械可読形式は将来別候補として切り出す |
| 実送信を同時実装 | 明示的Out of Scope。外部I/O・認証情報管理を伴い、単独でも重量級レビューを要する |
| Severity-aware Messageを同時実装 | 明示的Out of Scope。v6.7.0のDesign Freeze済み契約（Messageは`body`のみ）を破ることになる |
| Message BuilderへNO_NOTIFICATION対応を追加 | 明示的Out of Scope・最終制約。CLI側の呼び出し制御（16章）で対応すべき問題であり、Builderの契約（NO_NOTIFICATIONは契約違反）を変更する理由がない |
| `except Exception`で全例外を捕捉 | 予期しないプログラムエラー（バグ）を隠蔽するリスクがある。想定済みエラー（`OSError`/`ValueError`）のみを明示的に捕捉する方針（23章）と矛盾する |

## 30. Technical Debt

- CLI専用Composition（本Release）と将来Runtime Composition（Runtime Integration候補）の重複
- Metrics表示4項目と将来Metrics CLI Wiringの関係が未整理
- Messageが重大度を保持しない（v6.7.0からの継続）
- WARNING／CRITICALが同一Message（同上）
- Channel／Sender未実装
- Runtime Integration未実装
- Package Governance未整備（本Releaseはpackage数を増やさないため悪化させないが、解消もしない）
- JSON／機械可読形式未実装
- 空ログとHEALTHYの意味的差が注記表示に依存する（構造的な区別ではない）
- ERROR文言の安定性をPublic Contractとしていない（将来変更され得る）

## 31. Open Questions

```text
Architecture Design段階で未解決のOpen Questionなし
```

---

## 32. Architecture Decision Summary

| 論点 | 決定 |
|---|---|
| Entry Point単位 | 単一スクリプト `scripts/show_retry_notification.py` |
| Composition配置 | CLIスクリプト内で直接（新規package新設なし） |
| `RetryNotificationCliReport`の位置づけ | `scripts.show_retry_notification`モジュール固有のPublic Model。`src/*`のPublic APIには非該当 |
| NO_NOTIFICATION制御 | CLI側で`status is NOTIFY`のみBuilder呼出、Builder自体は無変更 |
| CLI引数 | `--log-path`のみ（`type=Path`、`default=_DEFAULT_LOG_PATH`） |
| デフォルトパス | `_PROJECT_ROOT = Path(__file__).parent.parent` ／ `_DEFAULT_LOG_PATH = _PROJECT_ROOT / ".run" / "retry_runtime_log.jsonl"` |
| Exit Code | 0＝CLI処理成功（NOTIFY/NO_NOTIFICATION問わず）、1＝`OSError`／`ValueError`、SystemExit 2＝argparse構文エラー |
| Traceback | `OSError`／`ValueError`のみ捕捉しTracebackを出さない。それ以外は非捕捉でPython標準伝播 |
| Metrics表示範囲 | `cycle_count` / `period_start` / `period_end` / `enqueue_success_ratio`の4項目（`enqueue_success_ratio`がRetryHealthEvaluatorの唯一の判定根拠であることを実装確認済み） |
| `period_start`/`period_end`表示 | 保持文字列をそのまま表示（再フォーマットしない） |
| `format_report()`改行 | 末尾改行なし。`main()`の`print()`が1つ付与 |
| `main()`シグネチャ | `main(argv: list[str] | None = None) -> int`（`run_retry_runtime.py`の`main() -> None`からの意図的差分、14章） |
| `.env`読み込み | 行わない（5パッケージが環境変数非依存のため） |

## 33. Implementation File Plan

**新規production code**（実装Release承認後に作成）

- `projects/03_game_content_ai/scripts/show_retry_notification.py`

**新規テスト**（同上）

- `projects/03_game_content_ai/tests/test_e2e_v6_8_0_retry_notification_cli_report_wiring_foundation.py`

**変更なし（既存無改修方針）**

- `src/retry_metrics/` / `src/retry_monitoring/` / `src/retry_alert/` / `src/retry_notification/` / `src/retry_notification_message/`（`__init__.py`含む）
- `src/retry_composition/` / `src/retry_runtime_orchestrator/` / Runtime Pipeline全体
- `scripts/run_retry_runtime.py`
- 既存テストファイル一式
- `docs/design/retry_metrics_foundation.md` 〜 `retry_notification_message_foundation.md`（v6.3.0〜v6.7.0の5設計書）

---

## 34. Review History

```text
Architecture Review 1：Changes Required
    指摘4件：
    1. RetryNotificationCliReportのPublic Contract整理
    2. 不正JSONとOSErrorの混同
    3. Traceback Policyの矛盾
    4. CLI Output Contract未確定

Architecture Review 2：Approved

Test Review 1：Changes Required
    指摘5件：
    1. Counter Fakeが観測不能
    2. main(None)が環境依存
    3. sys.modules未登録
    4. ratio計算式の確認不足
    5. Scenario数の定義不整合

Test Review 2：Changes Required
    指摘1件：
    1. Fake戻り値と正式Message確認が両立しない
       （PI-3／PI-4を実Builder使用、PI-5をCounter Fake専用へ分離して解消）

Test Review 3：Approved

Code Review：Approved
    軽微な指摘4件（Output Contractの検証精度2件・デバッグ性1件・sys.modules復元の
    堅牢性1件）を発見し、新規E2Eテストのみを最小修正（production code無改修）。
    196→197アサーションへ増加。修正後、新規E2E 197/197 PASS・Regression 943/943 PASSを
    再確認。

Release Review：Approved
    新規E2E 197/197 PASS・Regression 943/943 PASS（合計1140/1140 PASS）を確認。
    既存production code・既存test無改修（git diff --name-statusで確認）。
    architecture.md／ROADMAP.md／CHANGELOG.md反映、本設計書Status更新を実施。
```

## 35. Review指摘反映一覧

| Review指摘 | 修正内容 | 状態 |
|---|---|---|
| Result Objectの公開性 | `RetryNotificationCliReport`を「非公開」から「`scripts.show_retry_notification`モジュール固有のPublic Model」へ再定義。`src/*`のPublic APIには非該当、`__all__`非定義の理由を「非公開だから」ではなく「scripts/配下Entry Pointモジュールの既存慣習（`scripts/run_retry_runtime.py`）に合わせるため」と明記（15章） | Resolved |
| 不正JSONとOSErrorの混同 | Failure Policy表を`RetryRuntimeLogReader`の実装確認（`print(..., file=sys.stderr)`による行単位WARNING＋Exit 0、`FileNotFoundError`以外の`OSError`のみfail-fast＋Exit 1）に基づき正確に区別。「不正ログ（OSError）→非0」という旧表現を削除し、一部不正JSON／全行不正JSON／OSErrorをそれぞれ個別の行として整理（22章） | Resolved |
| Traceback Policyの矛盾 | 「想定済みエラー（`OSError`/`ValueError`）＝捕捉・Traceback非表示」と「予期しないエラー＝非捕捉・Python標準伝播」を明確に分離。「すべての異常時にTracebackが漏れない」という過度な契約を撤回し、`except Exception`を用いない`main()`実装を明示（23章） | Resolved |
| Output Contract未確定 | タイトル・セクション順・ラベル・数値書式（ratio小数第2位固定・period文字列そのまま表示・Enum `.value`）・空ログ注記・NO_NOTIFICATION文・末尾改行契約をすべてArchitecture Design段階で固定。「実装時に確定」という先送り表現を撤回し、Metrics 4項目が判定根拠であることを実装確認済みの事実として明記（17章） | Resolved |

4件すべて`Resolved`。
