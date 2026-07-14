# Retry Alert Foundation（v6.5.0候補）

作成日：2026-07-14
更新日：2026-07-14（ChatGPT Architecture Review「条件付きPASS」反映：①変換規則を設計契約として明記、②`RetryAlertLevel.NONE`の意味を「評価は正常完了・通知対象なし」を表す正常系の明示値として明確化、③未対応Statusへのフォールバック禁止・明示的失敗方針を追記。4.1節・4.2節を拡充、4.3節「未対応Statusの扱い」を新設。5章・6章・9章・10章・11章に関連反映）
更新日：2026-07-14（ユーザー承認によりArchitecture Reviewを正式PASSとし、本ドキュメントをDesign Freeze。Implementation完了：`src/retry_alert/`実装・`tests/test_e2e_v6_5_0_retry_alert_foundation.py`（141/141 PASS）・既存回帰（v5.9.0 64/64・v6.0.0 43/43・v6.1.0 44/44・v6.2.0 64/64・v6.3.0 174/174・v6.4.0 171/171、いずれもベースライン件数のままPASS）・`docs/architecture.md` / `docs/ROADMAP.md` / `docs/CHANGELOG.md`反映）
更新日：2026-07-15（ChatGPT Code Review「修正要求付き条件付きPASS」反映：①`tests/test_e2e_v6_5_0_retry_alert_foundation.py`からテスト16-25（Zero Diff、`git diff --quiet`ベースの無改修確認）を削除し131/131 PASSへ変更。既存コンポーネントの無改修確認はRelease Reviewで`git diff --name-status` / `git status --short`により行う方針へ変更、②2章をデータフローとimport依存方向を明確に区別する構成へ全面改訂し2.3節を新設。「Notification → Alertへの逆依存は禁止する」という誤った記述を、「禁止するのは`retry_alert → retry_notification`（Alertが Notificationをimportする方向）」という正しい記述へ訂正、③本Release関連のテスト件数記載を131件へ統一）
作成者：Claude Code（Architecture Designドラフト・Review指摘反映・Implementation・Test・Documentation）／ChatGPT（Architecture Review）／ユーザー（最終承認・実装指示）
状態：**Implementation Completed（commit／push待ち）**
分類：**Architecture Release**（development_workflow.md 5章・7章）

> 本ドキュメントはユーザー指示「Release 6.5 Architecture Design」に基づく設計のみを目的とする。**実装は行わない**。
> 依拠する既定方針：`docs/design/retry_monitoring_foundation.md` 11.1節（Retry Alert Foundationの責務境界を先行合意済み）、`docs/ROADMAP.md` 607行目。

---

## 1. Architecture Overview

Retry Alert Foundationは、`Metrics → Monitoring → Alert`という一方向パイプラインの3段目にあたる、独立した新規パッケージ`src/retry_alert/`である。

v6.4.0の`RetryHealthEvaluator`が「`RetryMetricsSnapshot`から健全性ステータスを判定する」だけの**Judgment Only Foundation**であったのと同じ位置づけで、本Foundationは「`RetryHealthReport`からアラートを出すべきかどうかを判定する」だけの**Judgment Only Foundation**とする。

- Slack／メール等への実際の通知（Notification実装）は行わない（ユーザー指定の必須条件）
- Runtimeには一切依存せず、依存するのは`retry_monitoring`のみ
- 出力は「アラートを送るべきかどうか」を表すImmutableなDomain Object（`RetryAlert`）1種類のみ
- 状態を持たない・副作用を持たないStateless Pure Functionとして実装する

v6.3.0（Metrics：数える）→ v6.4.0（Monitoring：問題かどうか判断する）→ v6.5.0（Alert：知らせるべきかどうか判断する）という責務の連鎖を、実際に通知する層（将来のNotification Foundation）とは明確に切り離す。

---

## 2. Dependency Direction

**データフロー（処理の実行順序）とimport依存方向（ソースコードがどのパッケージをimportするか）は逆向きになる。** 本章では両者を明確に分けて記述する（Code Review指摘反映）。

### 2.1 データフロー（実行順序）

```
Runtime実行 → Logger記録 → Metrics集計 → Monitoring判定 → Alert判定（本Foundation） → Notification送信（将来）
```

RuntimeがLoggerを駆動し、Loggerが記録したログをMetricsが集計し、Metricsの集計結果をMonitoringが判定し、Monitoringの判定結果をAlertが判定し、Alertの判定結果を将来Notificationが送信する、という**処理が実行される順序**を表す。この図はimportの方向を表すものではない。

### 2.2 import依存方向（ソースコードの依存関係）

各段階は「自分が入力として受け取るデータの型」を定義しているパッケージをimportする。そのため、**import依存の向きはデータフローとは逆になる**。

```
Notification（将来） → Alert（本Foundation） → Monitoring → Metrics
```

Release 6.5時点の実際のimport依存：

```
retry_alert → retry_monitoring → retry_metrics
```

（`retry_alert → retry_monitoring`はRelease 6.5で新規に追加する直接のimport。`retry_monitoring → retry_metrics`はv6.4.0で既に存在する直接のimportであり、本Releaseでは変更しない）

- `retry_alert` → `retry_monitoring`（`RetryHealthReport` / `RetryHealthStatus`型の参照のみ）＋標準ライブラリ（`enum` / `dataclasses`）
- `retry_alert`は`retry_metrics` / `retry_runtime_logging` / `retry_runtime_orchestrator` / `retry_runtime_loop` / `retry_runtime_lock` / `retry_runtime_shutdown` / `retry_engine` / `retry_composition`のいずれもimportしない（v6.4.0が確立した「Monitoringより下流の層を飛び越えて参照しない」というルールを、Alertでも踏襲する）
- `retry_monitoring`は`retry_alert`をimportしない（**逆依存の禁止**。import依存の向きで言えば`retry_monitoring → retry_alert`（Monitoringが Alertをimportする方向）に相当し、ユーザー指定の必須条件で明示的に禁止されている）
- Runtime Pipeline（`RetryRuntimeLock` / `RetryRuntimeShutdown` / `RetryRuntimeLoop` / `RetryRuntimeOrchestrator` / `RetryManager`）への依存は一切発生しない（「Runtimeから完全に独立」というユーザー指定の必須条件を、import文そのものが存在しないことで構造的に保証する）
- 新しい外部パッケージ（pip）は追加しない（Notificationを実装しないため、Slack SDK等は不要）

### 2.3 将来のRetry Notification Foundationのimport依存（許可される方向）

将来のRetry Notification Foundationは、本Foundationの出力である`RetryAlert`を入力として受け取るため、以下のimport依存を**許可する必要がある**。

```
retry_notification → retry_alert
```

これはRetry Notification Foundationが`RetryAlert`型を参照するために必要な、**正しい・意図された**import依存である。禁止すべきなのは逆方向、すなわち**`retry_alert`が`retry_notification`をimportする方向**（`retry_alert → retry_notification`）である。Alert層は将来のNotification層の存在を一切知ってはならない（Code Review指摘反映：「Notification → Alertへの逆依存は禁止する」という表現は誤りであり、本節の記述に訂正する）。

依存方向の検証は、v6.4.0の8.1節と同型のソースコード走査テストで機械的に保証する想定（Test Strategyは実装Releaseで確定）。

---

## 3. Package Structure

```
src/retry_alert/
    __init__.py              # 公開API定義
    retry_alert_level.py     # RetryAlertLevel（Enum）
    retry_alert.py           # RetryAlert（frozen dataclass、Alert Domain Object）
    retry_alert_evaluator.py # RetryAlertEvaluator（RetryHealthReport → RetryAlert）
```

命名・粒度は`src/retry_monitoring/`（`retry_health_status.py` / `retry_health_report.py` / `retry_health_evaluator.py`）と対称にする。「Enum 1ファイル」「値オブジェクト 1ファイル」「Evaluator 1ファイル」という既存の分割方針をそのまま踏襲する。

---

## 4. Domain Model

### 4.1 RetryAlertLevel（Enum）

```python
class RetryAlertLevel(Enum):
    NONE = "NONE"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
```

`RetryHealthStatus`（`HEALTHY` / `DEGRADED` / `UNHEALTHY`）とは**別の語彙**として定義する。Monitoring側の語彙（健全性の状態）とAlert側の語彙（知らせるべき度合い）を型として分離しておくことで、将来Alert側だけの都合（例：同じ`DEGRADED`でも状況によって`WARNING`と`CRITICAL`を分けたい等）で拡張する余地を残す。本Releaseでは以下の固定マッピングのみ実装する。

| RetryHealthStatus（入力） | RetryAlertLevel（出力） |
|---|---|
| `HEALTHY` | `NONE` |
| `DEGRADED` | `WARNING` |
| `UNHEALTHY` | `CRITICAL` |

**Design Contract（Architecture Review反映）**：上記の対応表は実装の詳細ではなく、本Foundationの**設計契約**である。`RetryAlertEvaluator`は独自の閾値判定・条件分岐ロジックを一切持たず、`RetryHealthEvaluator`（v6.4.0）によって**既に確定したStatus**を、上記の固定表に従って対応するAlert Levelへ変換するだけの、単純な写像（マッピング）である。「`enqueue_success_ratio`がいくつ以上ならWARNINGか」といった閾値判定は本Foundationの責務ではなく、v6.4.0の`RetryHealthEvaluator` / `RetryHealthThresholds`の責務のまま変更しない（8章・9章の依存方向ルールの帰結でもある：`retry_alert`は`RetryMetricsSnapshot`にも生の数値にも一切触れないため、閾値判定自体が構造的に不可能である）。

### 4.2 RetryAlert（frozen dataclass、Alert Domain Object）

```python
@dataclass(frozen=True)
class RetryAlert:
    level: RetryAlertLevel
```

- `RetryHealthReport`（v6.4.0）・`RetryMetricsSnapshot`（v6.3.0）と同じ設計判断（`frozen=True`、setter／update()を持たない）を踏襲する
- Release 6.5では`level`のみを扱う（Foundation First）。`message`（通知文面）・`triggered_at`（判定時刻）・`source_report`（元になった`RetryHealthReport`への参照）等は将来拡張の対象とし、本Releaseでは追加しない（11.5節と同型の判断。10章参照）
- `level == RetryAlertLevel.NONE`であっても`RetryAlert`インスタンスは生成される（Optionalを返さない、Total Function）。「アラートを送るかどうか」の判定は、`RetryAlert.level`を見た呼び出し元（将来のNotification Foundation）の責務とする

**`RetryAlertLevel.NONE`の意味（Architecture Review反映）**：`NONE`は、**「健康状態の評価は正常に完了したが、通知対象となるAlertは存在しない」ことを表す正常系の明示値**である。以下のいずれの意味も持たない。

| `NONE`が意味しないもの | 理由 |
|---|---|
| 評価の失敗 | 評価（`RetryHealthEvaluator.evaluate()` → `RetryAlertEvaluator.evaluate()`）が正常に完了した結果として`NONE`が返る。例外的状況の結果ではない |
| データ不足 | データ不足時、v6.4.0の`RetryHealthEvaluator`は既に`HEALTHY`を返す設計（9章 Failure Policy、v6.4.0設計書）であり、本Foundationはそれをそのまま`NONE`へ変換するだけである。「データ不足だからNONE」ではなく「HEALTHYと判定されたのでNONE」という経路しか存在しない |
| 不明な状態 | 不明・未対応のStatusは`NONE`へフォールバックしない（4.3節）。「不明」と「アラートなし」は明確に区別する |
| 処理のスキップ | `RetryAlertEvaluator.evaluate()`は`HEALTHY`が入力された場合も必ず実行され、`RetryAlert(level=NONE)`という具体的な値を生成する。判定処理自体を省略することはない |

将来のNotification Foundationは、`RetryAlert.level == RetryAlertLevel.NONE`の場合、通知を送信してはならない。これは本Foundationが保証する契約ではなく（本Foundationは通知を行わないため）、**Notification Foundation側が遵守すべき呼び出し契約**として、ここに明記しておく（7章 Out of Scope、11章 Known Issues）。

### 4.3 未対応Statusの扱い（Fail Fast契約・Architecture Review反映）

`RetryHealthStatus`（v6.4.0）は現時点で`HEALTHY` / `DEGRADED` / `UNHEALTHY`の3値のみだが、将来のRelease（v6.4.0設計書11.4節「複数指標に基づく総合判定」等）でStatusに新しい値が追加される可能性がある。

- `RetryAlertEvaluator`は、4.1節の対応表にある**既知の3つのStatusのみ**を明示的かつ網羅的（exhaustive）に変換する。実装はdictの`.get(status, デフォルト値)`のような「知らない値は既定値へ丸める」形を取らず、if/elif（またはmatch文）で既知の3値を明示的に分岐させ、**いずれにも一致しない場合は最終分岐で例外を送出する**形とする
- 未対応のStatusを`RetryAlertLevel.NONE`（またはその他の既存Level）へ自動的にフォールバックすることを**明示的に禁止**する。フォールバックは「対応漏れ」という開発上の契約違反を、あたかも「アラートなしの正常系」であるかのように静かに握りつぶしてしまい、4.2節で定義した`NONE`の意味（正常系の明示値）を汚染するため
- これは、v6.4.0の`RetryHealthEvaluator`が「データ不足」という**正常に起こりうる実行時状態**に対して例外を送出しない設計（v6.4.0設計書9章 Failure Policy）とは前提が異なる。未対応のStatusは実行時に自然に発生するデータ状態ではなく、「`RetryHealthStatus`にEnum値を追加したのに`RetryAlertEvaluator`の変換ロジックを追従させ忘れた」という**プログラミング契約違反**であり、fail-fastで検知すべき異常である
- 送出する例外の具体的な型（`ValueError` / 専用の例外クラス等）は本Architecture Designでは確定せず、実装Releaseで決定する。ただし「例外を送出せず処理を継続する」設計は採用しない、という方針のみを本節の設計契約として確定する

---

## 5. Responsibility of each class

| コンポーネント | 責務 | 依存 |
|---|---|---|
| `RetryAlertLevel`（新規） | アラートの度合いを表すEnum | なし（標準ライブラリのみ） |
| `RetryAlert`（新規） | 判定結果を表すImmutableな値オブジェクト。生成後は変更されない。将来のNotification Foundationは参照のみで更新は行わない | `RetryAlertLevel` |
| `RetryAlertEvaluator`（新規） | `RetryHealthReport.status`を4.1節の固定対応表に従って`RetryAlert`へ変換するのみ（閾値判定は行わない、v6.4.0の確定済みStatusをそのまま写像するだけ）。既知の3 Statusを網羅的に分岐させ、未対応のStatusはフォールバックせず例外を送出する（4.3節）。ファイルI/O・通知・Runtime参照・Monitoring内部状態への書き込みは一切行わない | `retry_monitoring`（`RetryHealthReport` / `RetryHealthStatus`型） |
| `RetryHealthReport` / `RetryHealthStatus` / `RetryHealthEvaluator` / `RetryHealthThresholds`（v6.4.0） | 無変更。本Releaseからは`RetryHealthReport`と`RetryHealthStatus`の型のみ参照され、`RetryHealthEvaluator` / `RetryHealthThresholds`は参照も依存もされない | — |
| Runtime Pipeline全体・`retry_metrics`・`retry_runtime_logging` | 無変更。本Foundationからは存在すら参照されない | — |

「判定（`RetryAlertEvaluator`）」と「通知の実行（将来のNotification Foundation）」を別パッケージへ分離するのは、v6.4.0が確立した「Monitoring＝判断する」「Alert（実際には将来のNotification）＝実行する」という責務分離を、Alert段階でも維持するためである。本Foundation自体は**判断のみ**を行い、実行（Slack API呼び出し等）は一切行わない。

---

## 6. Data Flow

```
RetryHealthReport（v6.4.0の出力。本Foundationの唯一の入力）
        │
        ▼
RetryAlertEvaluator.evaluate(report) -> RetryAlert
        │
        ▼
（呼び出し元は本Releaseでは未定。消費者不在の先行実装。将来はNotification Foundationが消費する想定）
```

`retry_alert`パッケージは、`RetryHealthReport`が内部でどう計算されたか（`RetryMetricsSnapshot`・`.run/retry_runtime_log.jsonl`等）を一切知らない。`RetryAlertEvaluator`が参照するのは`RetryHealthReport.status`のみである。

`status`が4.1節の既知の3値のいずれかである限り、`evaluate()`は必ず`RetryAlert`を返す（例外を送出しない、Total Function）。`status`が未対応の値である場合のみ、`evaluate()`は例外を送出し`RetryAlert`を返さない（4.3節）。この2つの経路は明確に区別され、後者は呼び出し元にとって「実装の更新漏れ」を示す明示的なシグナルとなる。

---

## 7. Out of Scope

- **Notification実装本体**（Slack Webhook／メール送信等の外部I/O）。ユーザー指定の必須条件により明示的に対象外とする。将来「Retry Notification Foundation」として別Releaseで検討する
- CLI表示・ダッシュボード化（Retry Alert CLI/Report Wiring Foundation、将来Release。v6.4.0の11.2節と同型のパターン）
- Runtime Pipeline（`RetryRuntimeLock` / `RetryRuntimeShutdown` / `RetryRuntimeLoop` / `RetryRuntimeOrchestrator` / `RetryManager`）への変更（一切触れない）
- `src/retry_metrics/` / `src/retry_monitoring/`への変更（本Releaseの都合で一切変更しない。逆依存も発生させない）
- アラートの抑制・重複排除・レート制限（同じ`UNHEALTHY`が連続しても、呼び出すたびに独立した`RetryAlert(level=CRITICAL)`を返す。抑制ロジックは状態を要するため、Statelessという要件と両立しない。将来Notification側の責務とする）
- アラート履歴の永続化（ファイル・DB等への保存は行わない）
- 閾値・マッピングルールの外部設定化（本Releaseでは4.1節の固定マッピングのみ）
- `RetryCompositionRoot`への配線（消費者不在のため本Releaseでは行わない）

---

## 8. Alternative Designs

| # | 案 | 内容 | 判断 |
|---|---|---|---|
| A | **（採用）独立パッケージ＋固定Enumマッピング** | `src/retry_alert/`を新設し、`RetryHealthStatus`→`RetryAlertLevel`の3値→3値固定マッピングのみを実装する | Foundation First・Stateless・Pure Functionの要件を満たしつつ、最小構成で依存境界を確立できる |
| B | `RetryAlertPolicy`（設定可能なマッピングルール）をConstructor Injectionで注入可能にする | v6.4.0の`RetryHealthThresholds`と同型のDI設計を、マッピングルールにも適用する | 現時点では3値→3値の恒等に近いマッピングしかなく、設定可能にする具体的な要求がない。YAGNI（v6.4.0設計書12章#4と同じ考え方）。将来、複数指標を組み合わせた高度な判定（11.4節相当）が必要になった時点で改めて検討する |
| C | `RetryAlert`に`reason`（判定理由の文字列）を最初から含める | `RetryHealthReport`の`status`に加え、人間可読な説明を持たせる | v6.4.0の`RetryHealthReport`が`status`のみの最小構成から始めたのと同じ理由（11.5節）で見送る。消費者（Notification）が実際に必要とする文面フォーマットが決まってから追加する方が手戻りが少ない |
| D | `RetryAlertEvaluator`を関数（クラスを持たないモジュールレベル関数）として実装する | `evaluate(report: RetryHealthReport) -> RetryAlert`のような単純関数にする | 既存の`RetryMetricsCalculator` / `RetryHealthEvaluator`がいずれもクラス（将来のDI拡張余地を残すため）として実装されている慣習と一貫性を保つため、クラス形式（案Aの一部）を採用する。ただし内部状態は持たない |

---

## 9. Rejected Alternatives

| # | 却下した設計 | 理由 |
|---|---|---|
| 1 | Retry AlertとNotification（実際の通知）を1つのReleaseとして一括実装する | Foundation First原則（1バージョン=1目的）に反する。ユーザー指定の必須条件「Notification実装を避ける」に直接抵触する |
| 2 | `RetryHealthEvaluator`（v6.4.0）に`to_alert()`のような変換APIを追加する | Monitoringの責務を「健全性判定」から拡張することになり、v6.4.0で確定した責務（Judgment Only Foundation）を変更してしまう。v6.4.0設計書13章#2と同じ理由で却下する |
| 3 | `RetryAlertEvaluator`が`RetryMetricsSnapshot`を直接参照し、`RetryHealthReport`を経由せず自前で判定する | ユーザー指定の必須条件「入力はRetryHealthReportを優先する」に反する。また`Monitoring`層を飛び越えた依存となり、2章の依存方向ルール（`Metrics → Monitoring → Alert`の一方向）に反する |
| 4 | `RetryAlert`をmutableなclassとして実装する | `RetryHealthReport` / `RetryMetricsSnapshot`等、Result系オブジェクトが一貫してfrozen dataclassである慣習と整合させるため |
| 5 | `level == NONE`の場合は`RetryAlert`を生成せず`None`を返す | Optionalを返すAPIは呼び出し元に`if result is not None`という条件分岐を強いる。v6.4.0が「判定不能でも例外を送出せず`HEALTHY`を返す」という設計判断をした前例（v6.4.0設計書13章#3）と対称的に、Alertも「アラートなし」を`level=NONE`という正常な値として表現し、Total Functionとして統一する |
| 6 | `RetryAlertEvaluator`が判定結果に応じてRuntimeへフィードバックする（例：`CRITICAL`時にLoopを止める） | ユーザー指定の禁止事項「Runtimeから完全に独立」に直接抵触する。また`Alert → Runtime`という新たな依存が発生し、2章の依存方向ルールに反する |
| 7 | 本Foundation内でSlack Webhook等への送信を試みる（try/exceptで失敗を握りつぶす等） | ユーザー指定の必須条件「Notification実装を避ける」に直接抵触する。外部I/Oを含めた瞬間、Statelessという性質も損なわれる（送信リトライ等の状態管理が必要になるため） |
| 8 | 未対応（将来追加された）Statusを`RetryAlertLevel.NONE`（または既存のいずれかのLevel）へ自動的にフォールバックする | Architecture Review指摘により却下。「対応漏れ」という契約違反を、あたかも正常系（アラートなし）であるかのように隠蔽してしまい、4.2節で定義した`NONE`＝「正常系の明示値」という意味を汚染する。フォールバックにより、`RetryHealthStatus`拡張時の実装追従漏れがテストでも実運用でも検知されないまま放置されるリスクが生じる（4.3節） |

---

## 10. Risks

- **「アラートなし」の表現が空虚になるリスク**：`RetryAlert(level=NONE)`は「送るべき通知がない」ことを表す値であり、9章#5の判断により意図的にこの形にしているが、将来の消費者（Notification Foundation）が誤って`NONE`も送信対象に含めてしまうと、無意味な通知が大量発生する。呼び出し側の実装ガイドとして明記が必要（Notification Foundation設計時の申し送り事項とする）
- **マッピングの恣意性**：`DEGRADED → WARNING` / `UNHEALTHY → CRITICAL`という対応は本Releaseの暫定判断であり、実運用でのアラート疲れ（Alert Fatigue）を評価するデータがまだない。運用開始後に見直しが必要になる可能性がある
- **重複排除なしによる通知過多のリスク**：8章・9章の判断により本Foundationは状態を持たないため、同一の異常状態が続く限り毎サイクル`CRITICAL`の`RetryAlert`を返し続ける。実際に通知を行うNotification Foundation側で抑制・レート制限を実装しない限り、通知が氾濫する可能性がある（この責務分担を明記しておく必要がある）
- **消費者不在による設計の未検証リスク**：v6.3.0・v6.4.0と同様、実際の呼び出し元（Notification Foundation）が存在しないまま設計するため、実装時にAPIの使い勝手が見直される可能性がある
- **Status拡張時の実行時失敗リスク（Architecture Review反映）**：4.3節のFail Fast契約により、将来`RetryHealthStatus`に新しい値が追加された際、`RetryAlertEvaluator`側の変換ロジックを同時に更新しない限り、本Foundationは実行時に例外を送出するようになる。これは「対応漏れを握りつぶさない」という意図的な設計判断（9章#8）だが、運用上は「Statusを1つ追加しただけでAlert段階が例外を送出し始める」という結合が生まれる。`RetryHealthStatus`拡張を行うReleaseでは、`retry_alert`側の追従修正を同時スコープに含める運用ルールが必要になる（Known Issuesにも記載）

---

## 11. Known Issues

- 実装未着手のため、既存Architecture Guard（v5.9.0〜v6.4.0のE2Eテスト）への影響は本Release時点では発生していない（新規Known Issueなし）
- 設計上の既知の制約（実装前に判明済み）：
  - `RetryAlertLevel`と`RetryHealthStatus`は現時点で1:1の恒等に近いマッピングであり、型を分離した意義が実装だけを見ると分かりにくい可能性がある。分離の理由（4.1節）をコードコメント・テストで明記する必要がある
  - 抑制・重複排除・レート制限の責務がNotification Foundation側に完全に委ねられており、本Foundationだけを見ると「アラートが際限なく生成されうる」という誤解を招きやすい（10章のRiskと表裏）
  - **（Architecture Review反映）** `RetryHealthStatus`の拡張と`RetryAlertEvaluator`の変換ロジック更新は本来1セットで行うべき変更だが、両者は別パッケージ（`retry_monitoring` / `retry_alert`）に属するため、片方の更新漏れをコンパイル時（Pythonのため型チェック時）に機械的検知する手段が現状ない。実装Release時にE2Eテスト側で「`RetryHealthStatus`の全メンバーが`RetryAlertEvaluator`で明示的に処理されていること」を検証するテストケース（4.3節の網羅性を担保するテスト）を追加することを推奨する
  - **（Architecture Review反映）** 将来のNotification Foundationが`RetryAlertLevel.NONE`の意味（4.2節）を正しく理解せず、`NONE`を「エラーで通知できなかった」等と誤解して独自にリトライ処理を実装してしまうリスクがある。Notification Foundation設計時に、本節（4.2節）を必読事項として申し送る必要がある

---

## 12. Recommendation

以下の最小構成での実装を推奨する。

1. `src/retry_alert/`を新設し、`RetryAlertLevel`（Enum）・`RetryAlert`（frozen dataclass、`level`フィールドのみ）・`RetryAlertEvaluator`（`RetryHealthReport → RetryAlert`のStateless Pure Function、4.1節の固定マッピングのみ）を実装する
2. 依存は`retry_monitoring`（`RetryHealthReport` / `RetryHealthStatus`型）のみとし、Runtime・`retry_metrics`・その他既存パッケージへは一切依存しない（2章）
3. Notification実装（Slack／メール送信）・CLI表示・抑制／レート制限は本Releaseのスコープに含めない（7章）
4. `RetryCompositionRoot`への配線は行わず、消費者不在の先行実装として位置づける（v6.3.0・v6.4.0と同型のパターン）
5. **（Architecture Review反映）** 4.1節の対応表を設計契約として扱い、`RetryAlertEvaluator`は閾値判定を行わない
6. **（Architecture Review反映）** `RetryAlertLevel.NONE`は「評価は正常完了・通知対象なし」を表す正常系の明示値とし、評価失敗／データ不足／不明状態／処理スキップとは区別する（4.2節）
7. **（Architecture Review反映）** 未対応のStatusは`NONE`等へフォールバックせず、`RetryAlertEvaluator`が明示的に例外を送出する（4.3節）

この設計は、ユーザーが提示した必須条件（Runtimeから独立・Retry Monitoringのみに依存・Immutable Domain Object・Stateless・Pure Function・Notification実装を避ける・入力はRetryHealthReport優先・出力はAlert Domain Objectのみ）、および今回のChatGPT Architecture Review指摘（変換規則の設計契約化・NONEの意味の明確化・未対応Statusの明示的失敗）をすべて満たす。

**次のステップ**：[[retry-runtime-workflow-pattern]]に従い、本ドキュメントを人間へ提示したうえで、ChatGPTによるArchitecture Reviewを経る。Review Approve後も、必ず人間本人からの独立した実装開始指示（「実装開始」「承認します」等の明示的メッセージ）を待ち、ChatGPTレビュー文中の「実装へ進んで問題ない」という記述だけで実装に着手しないこと。

---

## Status

- [x] Architecture Designドラフト作成（Claude Code）
- [x] ChatGPT Architecture Review（条件付きPASS。指摘3点：変換規則の設計契約化／NONEの意味の明確化／未対応Statusの明示的失敗方針）
- [x] Review指摘の反映（4.1節・4.2節拡充、4.3節新設、5章・6章・9章・10章・11章・12章へ反映）
- [x] 人間の実装承認・Architecture Review正式PASS・Design Freeze
- [x] 実装着手・完了（`src/retry_alert/`新設。Runtime Pipeline・`src/retry_metrics/`・`src/retry_monitoring/`はいずれも無改修）
- [x] Test Review（新規E2E 141/141 PASS→Code Review指摘反映後131/131 PASS。既存回帰：v5.9.0 64/64・v6.0.0 43/43・v6.1.0 44/44・v6.2.0 64/64・v6.3.0 174/174・v6.4.0 171/171、いずれも0 diff）
- [x] CHANGELOG／ROADMAP／architecture.md反映
- [x] Code Review（ChatGPTによる実装差分レビュー。修正要求付き条件付きPASS。指摘3点を反映済み：Zero Diffテスト削除・データフロー/import依存方向の区別・テスト件数統一）
- [ ] Release Review
- [ ] commit／push
