# Retry Observability Runtime Integration（Release 6.33）設計書

## 0. Status

Architecture Final Approved（Rev.4、Claude Code単独設計）。Release 6.33.0として実装完了済み。

**Codex Round 1 Independent Architecture Review実施済み**（`codex-readonly-review` workflow）：
`VERDICT: NOT APPROVED` / `BLOCKING: 0` / `MAJOR: 4` / `MINOR: 2`。

**Codex Round 2 Independent Architecture Review実施済み**（Rev.2に対して）：
`VERDICT: NOT APPROVED` / `BLOCKING: 0` / `MAJOR: 1` / `MINOR: 2`。

**Codex Round 3 Independent Architecture Review実施済み**（Rev.3に対して）：
`VERDICT: NOT APPROVED` / `BLOCKING: 0` / `MAJOR: 1` / `MINOR: 1`。

Rev.2はRound 1の4 MAJOR/2 MINORへ、Rev.3はRound 2の1 MAJOR/2 MINORへ対応した。Round 3で
新たに、(a) `Exception`はcontainしてruntime継続、`BaseException`はcontainせず正常に伝播する
という区別を固定するfault-injectionテスト（`observe_and_report()`・`_warn_best_effort()`双方
での`BaseException`非捕捉テスト）が12章に欠落しているMAJOR（M-1）、(b) 16章Open Questionsが
既にユーザー承認済みの決定（`log_cycle()`のscope解釈・Bounded Tail Window先送り）を依然
「要確認」のまま記載しており、採用済み設計・承認済みScopeと矛盾しているMINOR（m-1）、
が検出された。

Rev.4は、Round 3で検出されたMAJOR/MINORへの対応として、Architecture Designを改訂した
ものである（Rev.4作成時点では実装は未着手だった）。Round 1〜3すべてへの対応状況は
16章「Codex Finding Resolution Matrix」に一覧化する。Rev.4改訂の要点：

- 12章E2E Test Strategyへ、`observe_and_report()`（reader/evaluate/format/report-output
  各境界）・`_warn_best_effort()`（message formatting／stderr output境界、両ファイルの
  複製分）それぞれについて、`SystemExit`/`KeyboardInterrupt`が非containのまま正常に
  伝播することを固定するBaseException Non-Containment Testsを明記
- 16章Open Questionsのうち、ユーザーが既に承認済みの3項目（`log_cycle()`のscope解釈、
  AD-6a test migration、Bounded Tail Window先送り）・1項目（`_warn_best_effort()`の
  module-private複製）を、新設した「Confirmed Decisions」へ移動し、Open Questionsからは
  除去

Rev.4はHuman Gateでユーザー承認済みのArchitecture Final Approved版であり、これに基づき
Release 6.33.0の実装（6〜9章記載の`src/retry_runtime_observability/`新設・
`scripts/run_retry_runtime.py` / `scripts/show_retry_notification.py`変更・
`src/retry_runtime_logging/retry_runtime_cycle_logger.py`変更・新規E2E・Documentation
Integrationを含む）は完了している。Architecture Design自体の内容・Rev.4での決定事項は、
実装完了後も変更していない。

本設計書は、Release 6.32完了時点（baseline commit `66aa8e3c8fd8e195ef1baef793a1f37010610408`、origin/main同期・Working Tree clean）を前提に、Human Gateで承認された下記Approved Scope（2026-09-13）に基づいて作成する。

**Approved Scope**：
- Retry Runtime → `RetryObservabilityPipeline`のruntime integration
- `RetryRuntimeLogRecord`のcanonicalな調達境界・呼出順序の確定
- `evaluate()`のruntime failure policy確定
- `RetryObservabilityReport`のlocal observation先確定
- `scripts/show_retry_notification.py`をPipelineへの薄い委譲へ統一
- 必要なE2E / architecture guard / zero-diff / docs integration

**Out of Scope**（承認済み）：
- Slack等のexternal sender/write
- v6.32 `release_claim()`残存Suggestion
- Retry lineage / HRR / durable state semantics変更
- Scheduler等6.34以降のscope
- `human-gate.ps1` / Global Claude settings / Remote Tunnel / Universal Assets変更

**重要Invariant**（承認済み、10章で個別に整合を示す）：
1. Observability integrationはretry判断・durable state・side-effect safetyを変更しない
2. v6.29 Public API / reverse-dependency禁止 / CLI parity / backward compatibilityを維持
3. Pipelineの Fail Fast契約を安易に変更しない
4. 「毎サイクル全ログ再読込」は本設計書内での代替案比較を経て決定する（未承認の既定路線として採用しない）

---

## 1. Background / Motivation

`RetryObservabilityPipeline`（v6.29.0、`src/retry_observability_pipeline/`）は、`metrics → monitoring → alert → notification → message`の5段階を固定順序で呼び出す、状態を持たないOrchestration/Facadeコンポーネントとして完成済みである。しかし現時点でこれをimportしているのは自分自身（パッケージ内部・E2E）のみであり、Retry Runtime本体（`scripts/run_retry_runtime.py` → `RetryCompositionRoot` → `RetryRuntimeOrchestrator.run_once()`）からは一切参照されていない。

唯一の実消費者は`scripts/show_retry_notification.py::build_report()`であり、これは`RetryObservabilityPipeline.evaluate()`と実質的に同一の合成ロジックを、v6.8.0以来CLIローカルに保持し続けている（v6.29.0設計書4章で明示的に許容された一時的debt）。

本Releaseは、このFoundationを実際のRetry Runtimeへ配線し、CLI側の重複を解消する、v6.29.0設計書14章が定義した「将来Wiring境界」の実施である。

---

## 2. Goals

1. Retry Runtimeの1サイクル実行完了後、`RetryObservabilityPipeline.evaluate()`を安全な既定の境界・順序・失敗方針で呼び出し、結果をローカルに観測可能にする
2. `scripts/show_retry_notification.py::build_report()`を`RetryObservabilityPipeline.evaluate()`への薄い委譲へ置き換え、CLIローカルの重複合成ロジックを解消する
3. 上記1・2を、既存のRetry判断ロジック（`RetryManager` / `RetryLineageManager` / `RetryQueueManager` / `WorkflowMonitorManager`等）・durable state・side-effect安全性に一切影響を与えずに実現する

## 3. Non-Goals（Out of Scope）

- 外部Sender（Slack等）への実送信・実書き込み
- v6.32 `release_claim()`残存Suggestion（`RetryExecutor.execute()`のdiagnostic gap）への対応
- Retry lineage / HRR / durable attempt state のsemantics変更
- `SchedulerEngine` / production schedule driver（6.34領域）への変更
- ログローテーション・Observability専用の新規durable storageの導入
- `RetryHealthThresholds`のデフォルト値変更・環境変数化

---

## 4. Baseline / Preconditions

- baseline commit：`66aa8e3c8fd8e195ef1baef793a1f37010610408`（main、origin/main同期、Working Tree clean）
- 前提Release：6.32（Retry Runtimeが安全に実行され、実際に`.run/retry_runtime_log.jsonl`へログを生成していること。既存）
- 本Release時点で新規E2E・新規設計書ファイルは存在しない（Preflightで確認済み）

---

## 5. Architecture Decisions

### AD-1：Canonical Record Procurement Boundary（records調達境界）

**背景**：`RetryMetricsCalculator.calculate(records)`は、渡された`records`全体を対象にcycle_count・各種totalを積算し、`enqueue_success_ratio = enqueue_enqueued_total / enqueue_scanned_total`を算出する。これは**累積型（cross-cycle集計）**の設計であり、単一cycleのスナップショットではなく複数cycleにまたがる比率を前提にしている（`RetryHealthEvaluator`もこの比率にのみ閾値0.8/0.5を適用する）。この事実が、records調達方式の選択に直接影響する。

比較した代替案：

| # | 案 | 概要 | Pros | Cons |
|---|---|---|---|---|
| 1 | **Full-File Re-read（無限累積、Rev.2採用）** | 毎cycle、`RetryRuntimeLogReader(log_path).read()`で`.run/retry_runtime_log.jsonl`全体を読み直し、そのまま`evaluate()`へ渡す | 実装が最も単純。CLIの既存挙動（`build_report()`は元々全ファイルを読む）と完全に同一の意味論であり、Runtime/CLI間でauthoritative horizonの不一致が発生しない。既存5 package・Pipeline本体・cross-cycle cumulative semanticsを一切変更しない | Runtime稼働期間が伸びるほど`enqueue_success_ratio`が過去の健全な大量履歴で希釈され、直近の劣化を検出しにくくなる（Health/Alert/Notificationの本来の目的を損なう）。ファイルサイズに比例してI/Oコストが無限に増大する。**いずれもRev.2では既知の受容済みTrade-offとして14章に明記し、本Releaseでは対応しない** |
| 2 | **Current-Cycle-Only（in-memory、ファイル読み取りなし）** | 直近1 cycle分の`RetryRuntimeCycleResult`から`RetryRuntimeLogRecord`をin-memoryで直接構築し、`evaluate([current_record])`を呼ぶ | I/Oコストゼロ。常に最新cycleの結果を反映 | `cycle_count`が常に1に固定され、`RetryMetricsCalculator`が本来意図する複数cycleにまたがる集計（dry_run_cycle_count・各種total・比率の安定化）が意味を失う。単発の一時的な不調（例：たまたまscanned=1件で失敗）がそのままUNHEALTHY判定に直結し、ノイズが増える。加えて`RetryRuntimeCycleLogger.log_cycle()`が持つフィールドマッピングを別の場所で複製することになり、DRY原則に反する |
| 3 | **Bounded Tail Window（Rev.1で採用、Rev.2で撤回）** | `RetryRuntimeLogReader(log_path).read()`で全件を読み取ったうえで、直近N件（`records[-N:]`）のみを`evaluate()`へ渡す。windowingは新規Runtime統合コード側でのみ行い、`retry_metrics` / `retry_observability_pipeline`のいずれも変更しない | 直近の運用状態に対する感度を維持しつつ（希釈問題を解消）、既存5 packageおよびPipeline本体を一切変更しない（Zero-Diff） | I/Oコスト自体（ファイル全体のparse）はOption 1と同じで根本解決にならない。**加えてCodex Round 1指摘：Runtime側の判定入力（health/alert/notification）だけを変え、CLI側は全件のままになるため、「records調達方式」の域を超えた新しいobservability policyの導入に相当し、Approved Scopeを超過するリスクがある（Rev.2で撤回）** |
| 4 | **Incremental Offset Tracking** | 前回読み取り位置（バイトオフセット）をin-memoryで保持し、新規追記分のみを読み、直近N件のdequeを維持する | I/Oコスト・希釈問題の両方を解決 | 新規のstateful component・partial line処理・プロセス再起動時のoffset初期化（またはdurable化）等、この段階のMVPスコープに対して過大な複雑性を要求する。Roadmap・v6.2.0設計書はログローテーション自体を既に明示的にOut of Scopeとしており、本Releaseで同種の複雑性を先取りする理由がない |

**採用（Rev.2、Round 1指摘反映）**：**Option 1（Full-File Re-read）**。

> **Rev.1からの変更**：Rev.1はOption 3（Bounded Tail Window、直近20件）を採用していたが、
> Codex Round 1 Independent Architecture ReviewでMAJORとして指摘され撤回した。指摘の要旨：
> (a) windowが`enqueue_success_ratio`等のhealth/alert/notification判定入力を変えるため、
> 「records調達方式」の変更にとどまらず実質的に新しいobservability policyの導入になっている、
> (b) Runtime側は直近20件・CLI側は全件のまま、という2つの異なるauthoritative horizonが
> 生まれるにもかかわらず、どちらが権威的かをreportにもformatterにも明示していない。
> いずれも「records調達境界の確定」という本Releaseの承認スコープ（Approved Scope）を超え、
> 未承認のobservability policy変更に踏み込むリスクがあるため、Rev.2でOption 1へ差し戻す。

- Runtime・CLIのいずれも`RetryRuntimeLogReader(log_path).read()`が返す**全件**を
  `RetryObservabilityPipeline.evaluate()`へそのまま渡す。windowingは行わない
- これにより、Runtime側とCLI側は文字通り同一の入力（全件）に対して同一の`evaluate()`を
  呼ぶことになり、「どちらが権威的historyか」という問いそのものが発生しない
  （4章重要Invariant2「CLI parity」・本設計のCLI/Facade parityとも自然に整合する）
- `RetryMetricsCalculator`が前提とするcross-cycle cumulative semantics（cycle_countや
  各種totalが実行開始からの累積であること）を、Runtime側の観測でも変更しない
  （Release 6.32以前からの既存契約を維持。ユーザー承認済みInvariant1にも合致）
- I/Oコスト自体（ファイル全体のparse）が運用期間に比例して増大する点、および
  希釈問題（`enqueue_success_ratio`が長期の健全な履歴で希釈され直近の劣化を検出しにくい
  傾向）は、Option 1採用によって解消されない。これは**既知の受容済みTrade-off**として
  14章Known Issueに明記し、本Releaseでは対応しない（Option 3/4はいずれも15章Future
  Candidatesへ格下げし、再検討時は本Releaseとは独立した新規Architecture Reviewを要する
  observability policy変更として扱う——「records調達方式の内部最適化」としては
  再提案しない）

### AD-2：Composition Position（配線の位置）

**既存の強い先例**：`RetryRuntimeCycleLogger`（v6.2.0、`src/retry_runtime_logging/`）は、「cycle実行結果を観測してJSON Linesへ書くだけ」という単一責務のために、`RetryRuntimeOrchestrator.run_once()`の**外側**（`scripts/run_retry_runtime.py`の`run_cycle()`内、`run_once()`の呼び出し直後）に独立コンポーネントとして配置されている。`RetryRuntimeOrchestrator` / `RetryCompositionRoot`はいずれもこのLoggerを一切知らない。

Observability（cycle結果を観測してPipelineへ渡す）は性質上Loggingと対称的な「post-cycle observation」であり、同じ配置パターンを踏襲するのが最も既存アーキテクチャと整合する。

**決定**：新規独立package`src/retry_runtime_observability/`（6章）を新設し、`scripts/run_retry_runtime.py`の`run_cycle()`内、**`cycle_logger.log_cycle()`の直後**に呼び出す（呼び出す条件はAD-3改訂のcurrent-cycle inclusion契約に従う）。

**この結果、`RetryCompositionRoot`と`RetryRuntimeOrchestrator.run_once()`はいずれも本Releaseで無改修のまま維持できる**（Preflight時点の想定より変更範囲が小さいことが、この設計検討で判明した）。理由：
- `RetryCompositionRoot`は「既存`from_env()`/`from_config()`の組み立てのみ」を責務とする（同Foundation設計方針1章）。Observability Pipelineは`from_env()`を持たない無引数コンストラクタのStateless Composerであり、Composition Rootが担うべき「複数コンポーネント間の共有インスタンス配線」を必要としない（Queue/History/Lineageのような共有状態ではない）
- `RetryRuntimeOrchestrator.run_once()`は「1サイクル分のRetry業務ロジックの実行順序」に責務が限定されており（同Foundation設計方針、および6.31/6.32で追加されたstep群はいずれも実際のRetry判断に関わるものだった）、Observabilityはretry業務ロジックの実行が完全に終わった**後**に行う読み取り専用の観測であるため、`run_once()`の実行順序（1〜4）に新しいstepとして混入させる必然性がない

### AD-3：Call Order（呼出順序）／ Current-Cycle Inclusion Contract

Roadmap項目1「Runtime側でのRetryRuntimeLogRecord調達順序の明確化」に対する回答：

```
1. orchestrator.run_once(dry_run=...)                                   # 既存、無変更
2. print(format_summary(result))                                        # 既存、無変更
3. log_write_succeeded = cycle_logger.log_cycle(cycle_number, result, dry_run)  # 変更（戻り値を利用。後述）
4. if log_write_succeeded:                                               # 新規（本Release）
       observability_reporter.observe_and_report(format_observability_report)  # 新規（本Release）
```

**順序の根拠**：`observe()`は`.run/retry_runtime_log.jsonl`を読み取るため、**必ず`log_cycle()`の後**に呼ぶ。この呼出順序は本設計書で固定し、将来変更する場合は再度Architecture Reviewを要する。

**Rev.1からの変更（Round 1指摘対応）**：Rev.1は「`log_cycle()`の後に呼べば当該cycleが必ず含まれる」と暗黙に仮定していたが、Codex Round 1がこれを覆した：`RetryRuntimeCycleLogger.log_cycle()`は書き込み失敗（`OSError`）をベストエフォートで握りつぶしstderrへWARNINGを出すだけで例外を送出しない（既存契約、無変更）。この場合、呼出順序上は「`log_cycle()`の後」でも、当該cycleの行は実際にはファイルへ書かれておらず、直後の`observe()`は**当該cycleを含まないstale historyを観測してしまう**。これは「呼出順序」レベルでは正しいが「observeされる内容」レベルでは不整合であり、Round 1 MAJORとして指摘された。

**対応（Current-Cycle Inclusion Contract）**：`log_cycle()`の戻り値を`None`→`bool`（`True`＝書き込み成功、`False`＝`OSError`を捕捉し書き込み失敗）へ変更する（既存の`src/retry_runtime_logging/retry_runtime_cycle_logger.py`への追加的変更。詳細は7章）。`run_cycle()`は`log_write_succeeded`が`True`の場合のみ`observability_reporter.observe_and_report()`を呼ぶ。`False`の場合、当該cycleのobservabilityコンソール出力は単純にskipされる（Retry Runtime本体・次cycle以降には一切影響しない。次cycleのlog_cycle()が成功すればそのcycleから観測が再開する）。

- **後方互換性の確認（read-only確認済み）**：`scripts/run_retry_runtime.py`の既存呼び出し（`cycle_logger.log_cycle(...)`、戻り値を破棄）、および既存E2E（`tests/test_e2e_v6_2_0_structured_loop_logging_foundation.py`）を確認した結果、戻り値が`None`であることに依存するcaller・assertionは存在しない（同ファイルのテスト9は「例外を送出しないこと」を検証しており、戻り値そのものは検証していない。同ファイルの`_FakeCycleLogger.log_cycle()`は本Releaseの対象外のテスト専用Fakeであり、Fake自身の戻り値契約は当該既存テストの検証範囲に影響しない）。したがって`None`→`bool`は**追加的（additive）な変更であり、既存契約を破壊しない**。既存互換を壊す必要がある変更ではないため、Human Gateでの追加承認を要さずに本設計へ含める（ただし11章In Scopeに変更対象ファイルとして明記し、変更範囲の透明性を保つ）
- この契約変更により、`RetryRuntimeCycleLogger`（v6.2.0）は本Releaseで唯一「無改修」の対象から外れる既存ファイルとなる（AD-2で無改修と述べた`RetryCompositionRoot`・`RetryRuntimeOrchestrator`とは区別する）

`run_once()`自体の内部実行順序（1〜4のRetry業務ロジック、`execute_dispatchable_retries()`を1回だけ呼ぶ規律）には一切触れない。

### AD-4：Runtime Failure Containment Policy（失敗包含方針）

**制約（Invariant 3）**：`RetryObservabilityPipeline.evaluate()`自身のFail Fast契約（未対応`RetryNotificationStatus`相当値で無条件`ValueError`、`try/except`を持たない）は変更しない。

**方針**：Pipeline自体を変更せず、**呼び出し元（新規パッケージ）が失敗を包含する**。これは既存の`RetryRuntimeCycleLogger`が確立した前例（ログ書き込み失敗はRetry Runtime本体を止めない、ベストエフォート・stderr WARNING）と同型の「Runtime Failure Policy」を、Observability読み取り・評価にも適用するものである。

**Rev.1からの変更（Round 1指摘対応）**：Rev.1は`observe()`単体が`OSError`/`ValueError`のみをcatchする設計だった。Codex Round 1がMAJORとして指摘：(a) `RetryMetricsCalculator.calculate()`は型注釈上`RetryRuntimeLogRecord`を仮定するのみで実行時型検証を行わないため、不正な値が紛れ込んだ場合に`TypeError`等が発生しうるが、これは捕捉対象外だった、(b) formatting／console出力（`format_observability_report()`・`print()`）はcontainment境界の**外側**にあり、ここでの失敗（formatterのバグ等）がRetry Runtime本体を停止させうる。

**Rev.2での対応**：失敗包含境界を「読み取り（`RetryRuntimeLogReader.read()`）→評価（`Pipeline.evaluate()`）→整形（formatter）→コンソール出力（`print()`）」の**全体を覆うひとつの境界**へ拡張し、捕捉範囲を`Exception`（`BaseException`は対象外——`SystemExit`・`KeyboardInterrupt`・`GeneratorExit`は伝播させる。Loop実行中のGraceful Shutdown（v6.1.0）割込みを誤って握りつぶさないため）へ拡大した。

**Rev.2からの変更（Round 2指摘対応、M-1）**：Rev.2の`observe_and_report()`は`except Exception as e: print(f"WARNING: ...{e}", file=sys.stderr)`という実装だったが、このWARNING出力自体（`str(e)`によるメッセージ整形・`print()`のI/O呼び出し）は無防備だった。Codex Round 2がMAJORとして指摘：report-output（読み取り／評価／整形／出力）が失敗し`except`節に入った直後、その中の`str(e)`整形や`print(..., file=sys.stderr)`自体がさらに失敗した場合（例：カスタム例外の`__str__`実装バグ、stderrが閉じている等）、この二次的な例外は`except`節の外側にはcatch節がないため、そのままruntime本体へ伝播してしまう——「Retry Runtime本体を止めない」という契約の抜け穴だった。

**Rev.3での対応（best-effort WARNING helper）**：WARNING出力（メッセージ整形＋`print()`）を独立したbest-effortヘルパー`_warn_best_effort()`へ切り出し、ヘルパー自身の内部で`Exception`をcontainして何も再送出しない設計へ変更する（`BaseException`はここでも対象外）。これにより「report-output失敗」「warning-output失敗」「両方failure（report-output失敗の処理中にwarning-outputも失敗）」のいずれのケースでも、`observe_and_report()`から例外が一切伝播しないことを構造的に保証する（7章コード参照）。

`RetryRuntimeObservabilityReporter`（6・7章）は2つのメソッドを持つ：

| メソッド | 責務 | 失敗包含 |
|---|---|---|
| `observe() -> RetryObservabilityReport` | 読み取り＋評価のみ。raw契約（testability優先） | **なし**（例外はそのまま伝播。単体テストで契約を直接検証できるようにするため） |
| `observe_and_report(formatter, out=None) -> None` | `observe()`→`formatter(report)`→`print(..., file=out or sys.stdout)`までを一括実行する、Runtime本体が実際に呼ぶ唯一の入口 | **あり**（`Exception`全体をcatchし、`_warn_best_effort()`へ委譲してWARNINGを出力する。`BaseException`は対象外。WARNING出力自体の失敗もヘルパー内部でcontainされ、呼び出し元へは一切伝播しない。Round 2 M-1対応） |

発生しうる例外の代表例（すべて`observe_and_report()`が一括して捕捉する。個別のcatch節は設けない）：

| 例外 | 発生源 |
|---|---|
| `OSError` | `RetryRuntimeLogReader.read()`（ファイル自体が読めない：権限エラー等。`FileNotFoundError`は`RetryRuntimeLogReader`内部で空リストとして正常処理されるため、ここに到達するのは真の異常のみ） |
| `TypeError` / その他`Exception`派生 | `RetryMetricsCalculator.calculate()`（型不整合な値を含むrecordに対する算術演算等） |
| `ValueError` | `RetryObservabilityPipeline.evaluate()`（未対応status相当値）・`RetryObservabilityReport.__post_init__`（invariant違反） |
| `Exception`派生全般 | `formatter(report)`（`format_observability_report()`実装上のバグ）・`print()`（出力先I/O異常） |
| `Exception`派生全般（二次障害） | `_warn_best_effort()`内部の`str(exc)`整形・`print(..., file=sys.stderr)`自体（Round 2 M-1対応。ヘルパー内部でcontainされ`observe_and_report()`へは伝播しない） |

**重要**：`observe_and_report()`は`run_once()`が既に完了し、Retry業務ロジックの副作用（Queue更新・History記録・Lineage状態遷移）がすべて確定した**後**にのみ呼ばれる（AD-3のcurrent-cycle inclusion契約により、さらに`log_cycle()`成功後にのみ呼ばれる）。したがってこのメソッド内で何を捕捉しようと、それが原因でRetry判断・durable stateへ影響することは構造的にあり得ない（Observabilityは一方向の終端的な読み取り専用sinkであり、いかなる既存コンポーネントへの書き戻し・feedbackも持たない。8.2節でAST Guardにより機械的に保証する）。二次障害（WARNING出力自体の失敗）を含めても、この構造的保証は`_warn_best_effort()`のcontainmentにより維持される（Round 2 M-1対応）。

### AD-5：Report Sink（観測先）

Roadmap項目3「RetryObservabilityReportの観測先（コンソール出力／ログ記録等）の明確化」に対する回答：

**決定**：**コンソール出力のみ**を本Releaseの観測先とする。

- `scripts/run_retry_runtime.py`に、CLI（`show_retry_notification.py::format_report()`）と同系統だが独立した新規関数`format_observability_report(report: RetryObservabilityReport) -> str`を定義し、`format_summary()`と同様の人間可読ブロックとして毎cycle出力する
- `observability_reporter.observe_and_report(format_observability_report)`が正常終了した場合、常に整形結果をコンソールへ表示する（`NOTIFY`/`NO_NOTIFICATION`いずれも表示、`cycle_count=0`のHEALTHYも表示。ステータスによる表示抑制という新しい判断ロジックを追加しない——v6.29.0設計書7.1節の「Orchestration/Facade層は既存の判断を追加しない」という規律を、統合コード自身にも適用する）。読み取り・評価・整形・出力のいずれかの段階で失敗した場合はAD-4の包含境界によりWARNINGのみがstderrへ出力され、report本体はコンソールへ表示されない
- **（Rev.3変更、Round 2 MINOR対応）** `observe_and_report()`の出力先は`out: TextIO = sys.stdout`（import-time binding）ではなく`out: TextIO | None = None`とし、`out`省略時は**呼び出し時点**の`sys.stdout`を都度参照する（call-time解決。7章コード参照）。Rev.2の`sys.stdout`デフォルト値はモジュールimport時点で評価され束縛されるため、テストが`contextlib.redirect_stdout`等でin-process redirectionを行っても、それより後にモジュールがimportされていない限りcaptureできないという不具合があった
- `dry_run`による出力抑制も行わない（Observabilityは読み取り専用でありdry_runの有無によって安全性が変わらないため、特別扱いする理由がない）
- 新規ログファイル・新規durable storageへの記録は行わない（Out of Scope。Slack等の外部送信は当然含まない）

### AD-6：CLI Delegation（scripts/show_retry_notification.pyの薄い委譲統一）

現状の`build_report()`は`RetryRuntimeLogReader` → 5つのEvaluator/Builderを直接ローカルでCompose している。これを以下へ置き換える：

```python
from retry_observability_pipeline import RetryObservabilityPipeline

def build_report(log_path: Path) -> RetryNotificationCliReport:
    reader = RetryRuntimeLogReader(log_path=log_path)
    records = reader.read()
    observability_report = RetryObservabilityPipeline().evaluate(records)

    return RetryNotificationCliReport(
        metrics=observability_report.metrics,
        health_report=observability_report.health_report,
        alert=observability_report.alert,
        notification_decision=observability_report.notification_decision,
        message=observability_report.message,
    )
```

- `RetryNotificationCliReport`（CLIローカルのdataclass）自体は**削除せず維持する**。`format_report()`のシグネチャ・出力形式は完全に無変更のまま保つため（後方互換性・既存出力Contractの維持）
- `RetryRuntimeLogReader`の直接呼び出しは維持する。既存Parity Testが`show_retry_notification.RetryRuntimeLogReader.read`をクラスレベルでmonkeypatchする方式に依存しているため、このimport・参照を残すことで既存テストの前提を壊さない
- 削除される依存：`RetryHealthEvaluator` / `RetryAlertEvaluator` / `RetryNotificationEvaluator` / `RetryNotificationMessageBuilder`の直接インスタンス化。型注釈用のimport（`RetryAlert` / `RetryMetricsSnapshot` / `RetryHealthReport` / `RetryNotificationDecision` / `RetryNotificationMessage`）は`RetryNotificationCliReport`のフィールド型として引き続き必要
- この変更後、CLIとPipelineは「同じ`evaluate()`呼び出し」を経由するため、Parity Testは論理的にtautologyに近くなるが、将来の再乖離を防ぐregression guardとして維持する（12章）

### AD-6a：既存v6.8 Monkeypatch Test Migration（Round 1指摘対応）

**Round 1指摘（MAJOR）**：`tests/test_e2e_v6_8_0_retry_notification_cli_report_wiring_foundation.py`の以下4箇所は、CLIローカルのモジュール属性を直接monkeypatchしている：

| Test ID | 行 | Patch対象（現状） | 目的 |
|---|---|---|---|
| PI-5A | 638 | `show_retry_notification.RetryNotificationMessageBuilder` | Message Builder呼び出し回数（0回）の検証 |
| PI-5B | 660 | `show_retry_notification.RetryNotificationMessageBuilder` | Message Builder呼び出し回数（1回）・引数identityの検証 |
| EX-1 | 799 | `show_retry_notification.RetryAlertEvaluator` | `ValueError`伝播（Exit Code 1）の検証 |
| EX-2 | 815 | `show_retry_notification.RetryAlertEvaluator` | 未知例外（`RuntimeError`）の非捕捉伝播の検証 |

AD-6の委譲後、`build_report()`は`RetryAlertEvaluator` / `RetryNotificationMessageBuilder`を自らインスタンス化しない（`RetryObservabilityPipeline.__init__`が内部で`retry_observability_pipeline.retry_observability_pipeline`モジュール自身がimportした`RetryAlertEvaluator` / `RetryNotificationMessageBuilder`をインスタンス化する——`src/retry_observability_pipeline/retry_observability_pipeline.py`5-6章参照）。したがって上記4箇所は**delegationによって迂回され、意図した契約を検証できなくなる**（Codex Round 1が指摘した通り）。

**移行方針（test weakeningではなく、patch対象をアーキテクチャ上の正しい所有者へ再配置する）**：

- 検証したい契約（EX-1のValueError伝播・EX-2のRuntimeError非捕捉伝播・PI-5A/PI-5Bの呼び出し回数／引数identity）は**一切変更しない**。同一の`check`/`check_true`アサーションをそのまま維持する
- Patch対象のみを、実際にクラス参照を解決するモジュールへ変更する：
  ```python
  import retry_observability_pipeline.retry_observability_pipeline as _pipeline_module
  ...
  with patched_attr(_pipeline_module, "RetryAlertEvaluator", _raising_value_error):
      ...
  with patched_attr(_pipeline_module, "RetryNotificationMessageBuilder", CountingMessageBuilder):
      ...
  ```
- 成立根拠：`RetryObservabilityPipeline.__init__`は呼び出しのたびに`RetryAlertEvaluator()` / `RetryNotificationMessageBuilder()`をインスタンス化し、`build_report()`（AD-6）は`RetryObservabilityPipeline()`を呼び出しごとに新規構築する。したがって`with patched_attr(...)`ブロック内で`build_report()`／`main()`を呼び出せば、そのブロック内で構築される`Pipeline`インスタンスは常にpatch後のクラスを参照する（Pythonのモジュール属性解決のタイミングと一致するため、構築順序に関する追加の前提は不要）
- `FR-1`〜`FR-6`（`RetryRuntimeLogReader`の直接呼び出しに依存するテスト群）はAD-6で`RetryRuntimeLogReader`の直接呼び出しを維持するため、**無修正のまま有効**（read-only確認済み）
- 本ファイル自体が変更対象になるため、13章Zero-Diff Guard Registryの`_TEST_CHANGE_CONTRIBUTIONS`へ追記する

---

## 6. New Package：`src/retry_runtime_observability/`

```
src/retry_runtime_observability/
    __init__.py
    retry_runtime_observability_reporter.py   # RetryRuntimeObservabilityReporter
```

設計方針（`RetryRuntimeCycleLogger`と対称）：
- 責務は「ログを全件読み、Pipelineへ渡し、整形し、コンソール出力し、いずれかの段階の失敗を包含すること」に限定する（windowingは行わない。AD-1改訂）
- `RetryManager` / `RetryQueueManager` / `RetryHistoryManager` / `RetryLineageManager` / `RetryCompositionRoot` / `RetryRuntimeOrchestrator` / `scheduler` / `scripts`のいずれにも依存しない（`retry_metrics`と`retry_observability_pipeline`のみに依存する葉パッケージ）。整形ロジック自体（`format_observability_report()`）は`scripts/run_retry_runtime.py`側に置いたまま、`observe_and_report()`へCallableとして注入する（AD-5・7章）ことで、この依存方向を維持する
- Stateless Composerではあるが、`log_path`をConstructor Injectionで保持する点は`RetryRuntimeCycleLogger`（`log_path`を保持）と同型

---

## 7. Public API

```python
# retry_runtime_observability_reporter.py
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, TextIO

from retry_metrics import RetryRuntimeLogReader
from retry_observability_pipeline import RetryObservabilityPipeline, RetryObservabilityReport


class RetryRuntimeObservabilityReporter:
    """
    RetryRuntimeLogReader.read()が返す全件のRetryRuntimeLogRecordから、
    RetryObservabilityPipelineを呼び出してRetryObservabilityReportを得るだけの、
    Retry業務ロジックを一切知らないRuntime Integrationコンポーネント。

    - ファイルI/Oは RetryRuntimeLogReader への委譲のみで行う（自前のopen()は持たない）
    - windowingは行わない。RetryMetricsCalculatorが前提とするcross-cycle
      cumulative semanticsを、CLI（show_retry_notification.py）と同一の
      「全件入力」でRuntime側からも維持する（AD-1）
    - observe()自体は失敗を一切捕捉しない（raw契約。単体テストで
      「例外がそのまま伝播すること」を直接検証できるようにするため）
    - 失敗包含（Runtime Failure Policy。RetryRuntimeCycleLogger.log_cycle()と
      対称的な方針）は observe_and_report() のみが担う単一境界とする（AD-4）
    - dry_run引数は持たない（読み取り専用・観測専用のため、dry_runによる
      挙動分岐が存在しない）
    """

    def __init__(
        self,
        log_path: Path,
        pipeline: RetryObservabilityPipeline | None = None,
    ):
        self.log_path = log_path
        self._pipeline = pipeline if pipeline is not None else RetryObservabilityPipeline()

    def observe(self) -> RetryObservabilityReport:
        """
        log_path から全件のRetryRuntimeLogRecordを取得し、
        RetryObservabilityPipeline.evaluate() を呼び出してRetryObservabilityReport
        を返す。例外は一切捕捉せずそのまま伝播する（失敗包含は
        observe_and_report()の責務。AD-4）。
        """
        records = RetryRuntimeLogReader(log_path=self.log_path).read()
        return self._pipeline.evaluate(records)

    def observe_and_report(
        self,
        formatter: Callable[[RetryObservabilityReport], str],
        out: TextIO | None = None,
    ) -> None:
        """
        読み取り（RetryRuntimeLogReader.read()）・評価（Pipeline.evaluate()）・
        整形（formatter）・コンソール出力（print）までの全段階を、ひとつの
        失敗包含境界として実行する（AD-4）。

        いずれかの段階で Exception 派生の例外が発生した場合（BaseException・
        SystemExit・KeyboardInterrupt・GeneratorExitは対象外、そのまま伝播する）、
        WARNING出力を試みたうえで戻り、呼び出し元（Retry Runtime本体）へは
        一切伝播しない。WARNING出力自体（メッセージ整形・print()）が失敗しても、
        それもこのメソッドの外へは伝播しない（_warn_best_effort()。Round 2 M-1対応）。

        out は呼び出し時点（call time）で解決する。省略時は本メソッドが実際に
        呼ばれた瞬間の sys.stdout を参照する（import時点で束縛しない。
        Round 2 MINOR対応。contextlib.redirect_stdout 等での capture を可能にする）。
        """
        try:
            report = self.observe()
            text = formatter(report)
            print(text, file=out if out is not None else sys.stdout)
        except Exception as e:  # noqa: BLE001 — 意図的な単一失敗包含境界（AD-4）
            _warn_best_effort("Failed to produce retry observability report", e)


def _warn_best_effort(prefix: str, exc: BaseException) -> None:
    """
    prefix と str(exc) を連結した WARNING メッセージを stderr へ出力するだけの、
    失敗しても何も再送出しない best-effort ヘルパー（Round 2 M-1対応）。

    str(exc)（カスタム例外の __str__ 実装バグ等）や print() 自体（stderrが
    閉じている等）が失敗しても、その例外はこの関数の外へは伝播しない
    （Exceptionのみをcontainする。BaseExceptionは対象外——呼び出し元
    observe_and_report()・log_cycle()と同じ方針）。呼び出し元は「WARNINGが
    出力される保証」ではなく「WARNING出力の失敗が呼び出し元へ波及しない保証」
    のみをこの関数から得る。
    """
    try:
        print(f"WARNING: {prefix}: {exc}", file=sys.stderr)
    except Exception:  # noqa: BLE001 — 意図的な二次障害containment（Round 2 M-1対応）
        pass
```

```python
# __init__.py
from .retry_runtime_observability_reporter import RetryRuntimeObservabilityReporter

__all__ = ["RetryRuntimeObservabilityReporter"]
```

**`scripts/run_retry_runtime.py`側の変更点**（差分イメージ）：

```python
from retry_runtime_observability import RetryRuntimeObservabilityReporter

...

observability_reporter = RetryRuntimeObservabilityReporter(
    log_path=_PROJECT_ROOT / ".run" / "retry_runtime_log.jsonl",
)

def format_observability_report(report) -> str:
    ...  # format_summary()と同系統の人間可読ブロック（独自定義、他scriptsからimportしない）

def run_cycle():
    nonlocal cycle_count
    cycle_count += 1
    result = orchestrator.run_once(dry_run=args.dry_run)
    print(format_summary(result))
    log_write_succeeded = cycle_logger.log_cycle(
        cycle_number=cycle_count, result=result, dry_run=args.dry_run,
    )
    if log_write_succeeded:
        observability_reporter.observe_and_report(format_observability_report)
    return result
```

`RetryCompositionRoot` / `RetryRuntimeOrchestrator` は無改修。

**`src/retry_runtime_logging/retry_runtime_cycle_logger.py`側の変更点**（既存ファイル、AD-3参照。差分イメージ）：

**Rev.3での変更（Round 2 MINOR対応）**：Rev.2は`True`の意味を「書き込みが成功したこと」「当該cycleがログへ確実に記録されたこと」と表現していたが、これは実際にこのメソッドが保証できる範囲を超えていた。Codex Round 2が指摘：`True`が保証できるのは「`open()`によるappend・`write()`・`with`ブロックによる`close()`が`OSError`を送出せず完了したこと」のみであり、OSレベルのバッファがディスクへ`fsync`されたことの保証（durability）や、その後の外部プロセス・手動操作によるファイル変更からの保護までは一切含まない。Rev.3ではdocstringの表現をこの範囲に限定する。また、既存の`except OSError`（catchするexceptionの種類）は不用意に拡張しない（`Exception`全体への拡大等は行わない。既存exception policyを維持する）。WARNING出力（`print(..., file=sys.stderr)`）のみ、7章`RetryRuntimeObservabilityReporter`と同型のbest-effortヘルパーでcontainする（Round 2 M-1対応。既存の`except OSError`のcatch対象自体は変更しない）：

```python
def log_cycle(
    self,
    cycle_number: int,
    result: RetryRuntimeCycleResult,
    dry_run: bool = False,
) -> bool:                                              # 変更: -> None から -> bool へ
    """
    （既存docstring本文は無変更、以下を追記）
    戻り値は、このメソッドの書き込み処理（mkdir・open・write・close）が
    OSError を送出せず完了したかどうかのみを示す（True＝完了、False＝
    OSError を捕捉）。durability（fsyncによるディスクへの確実な反映）は
    保証しない。書き込み完了後に他プロセス・手動操作がログファイルを
    変更・削除した場合の保護も行わない。呼び出し元はこの戻り値を用いて、
    当該cycleの書き込み呼び出し自体がOSErrorなく完了したことを確認した
    うえでのみ後続処理（Observability等）を行うことができる
    （Current-Cycle Inclusion Contract。AD-3。保証範囲はここに記載の通り
    限定的であり、それ以上の意味を持たせない）。
    """
    ...  # record構築部分は無変更
    try:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return True                                     # 追加
    except OSError as e:                                # 既存exception policy、範囲不変
        _warn_best_effort("Failed to write runtime log", e)  # 変更：best-effort化（Round 2 M-1対応）
        return False                                    # 追加
```

`_warn_best_effort()`は7章`retry_runtime_observability_reporter.py`のヘルパーと同一の実装パターン（メッセージ整形・`print()`を`try/except Exception: pass`でcontainし、`BaseException`は対象外）を、本ファイル内にモジュールプライベートな関数として複製する。2つの独立package間で新たな共有依存を作らないため（8章依存方向を変更しない）、あえて共通ユーティリティへ抽出しない。

---

## 8. Dependency Direction / Architecture Guards

### 8.1 依存方向

```
retry_runtime_observability
    ├─→ retry_metrics（RetryRuntimeLogReader）
    └─→ retry_observability_pipeline（RetryObservabilityPipeline, RetryObservabilityReport）
```

禁止する依存（`retry_observability_pipeline`の既存禁止契約7.3節に準拠）：
- `retry_engine` / `retry_queue` / `retry_history` / `retry_lineage` / `retry_enqueue_trigger` / `scheduler` / `retry_composition` / `retry_runtime_orchestrator`
- CLI（`scripts/`）

### 8.2 One-Way Terminal Sink Guarantee（新規AST Guard）

Observabilityが「読み取り専用・一方向の終端」であることを機械的に保証するため、以下をE2E内のAST走査で検証する（v6.29.0設計書7.2節「Reverse Dependency禁止」と同型）：

- `retry_engine` / `retry_queue` / `retry_history` / `retry_lineage` / `retry_enqueue_trigger` / `scheduler` / `retry_composition` / `retry_runtime_orchestrator`のいずれも`retry_runtime_observability`をimportしていないこと
- `retry_runtime_observability`が上記いずれのpackageもimportしていないこと（8.1の禁止依存の検証）
- `retry_runtime_observability`のソースコード中に、既存のretry判断コンポーネント（`RetryManager` / `RetryLineageManager`等）への参照が一切存在しないこと

---

## 9. Data Flow

```
[cycle N 完了]
RetryRuntimeOrchestrator.run_once() → RetryRuntimeCycleResult
    ↓
log_write_succeeded = RetryRuntimeCycleLogger.log_cycle()
    → .run/retry_runtime_log.jsonl へ1行追記（既存ロジック無変更、戻り値をbool化。AD-3）
    ↓
if log_write_succeeded:                          # Current-Cycle Inclusion Contract（AD-3）
    RetryRuntimeObservabilityReporter.observe_and_report(format_observability_report)
        │
        ├─ RetryRuntimeLogReader.read()  → list[RetryRuntimeLogRecord]（全件、既存・無変更。
        │                                    windowingなし。AD-1改訂）
        ├─ RetryObservabilityPipeline.evaluate(records)  → RetryObservabilityReport（既存、無変更）
        ├─ format_observability_report(report) → str
        └─ print(..., file=out) → コンソール出力
        （上記4段階はひとつの失敗包含境界。AD-4）
```

CLI経路（独立、既存と並存）：

```
scripts/show_retry_notification.py::build_report()
    ↓
RetryRuntimeLogReader.read()  → 全件（Runtime側と同じくwindowingなし。AD-1改訂により
                                  Runtime/CLIは同一入力・同一evaluate()を経由するため、
                                  authoritative horizonの不一致が構造的に発生しない）
    ↓
RetryObservabilityPipeline().evaluate(records)
    ↓
RetryNotificationCliReport（フィールドをそのまま転記）
    ↓
format_report() → コンソール出力（既存、無変更）
```

---

## 10. Invariant Preservation Mapping

| Invariant | 本設計での担保方法 |
|---|---|
| Observability integrationはretry判断・durable state・side-effect safetyを変更しない | `observe()` / `observe_and_report()`は`run_once()`完了後、かつ`log_cycle()`成功後にのみ呼ばれ（AD-3）、いかなるretry判断コンポーネント（Manager/Queue/History/Lineage）へも参照・書き込みを行わない（8.2 AST Guardで機械的に保証）。`RetryCompositionRoot` / `RetryRuntimeOrchestrator`は無改修 |
| v6.29 Public API維持 | `RetryObservabilityPipeline` / `RetryObservabilityReport`のシグネチャ・`__post_init__` invariantは無変更。呼び出し方（`evaluate(records)`）も既存契約通り |
| Reverse-dependency禁止維持 | 既存5 package（metrics/monitoring/alert/notification/message）は本Releaseで一切変更しない。新規`retry_runtime_observability`も8.2のAST Guardで一方向性を保証 |
| CLI parity維持 | `format_report()`のシグネチャ・出力文字列は無変更。`RetryNotificationCliReport`も存置。既存Parity Test（AD-6a移行後）は`retry_observability_pipeline.retry_observability_pipeline`モジュールをpatch対象とすることで同一の契約を検証し続ける |
| Backward compatibility維持（Round 1指摘反映：zero-diffとは表現しない） | 維持対象を明確に区別する：CLI引数・Exit Code Policy・`format_summary()`出力文字列・retry判断・durable state・side-effect safetyは**完全に無変更（zero-diff）**。一方、**Runtime実行時のコンソール出力（`format_observability_report()`）は、`log_cycle()`成功時に毎cycle新規追加される出力であり、これは本Release（6.33）で承認された意図的なadditive behavior change（stdoutの増分）である**。zero-diffの主張はCLI/判断/状態/安全性の範囲に限定し、runtime stdoutをその範囲に含めない |
| Pipelineの Fail Fast契約を安易に変更しない | `evaluate()`自体は無改修。失敗の包含は呼び出し元（新規package・`observe_and_report()`単一境界）でのみ行う（AD-4） |
| 「毎サイクル全ログ再読込」は未承認の既定路線として採用しない | AD-1で4案を比較し、Round 1指摘を経てOption 1（Full-File Re-read）を理由とともに選定（Rev.1で選定したOption 3はRound 1でMAJORとして撤回）。I/O自体が運用期間に比例して増大する点はKnown Issue（14章）として明記し隠蔽しない |

---

## 11. In Scope / Out of Scope（本設計書としての確定）

### In Scope
- 新規package `src/retry_runtime_observability/`（`RetryRuntimeObservabilityReporter`。`observe()` / `observe_and_report()`）
- `scripts/run_retry_runtime.py`：Reporter構築・`run_cycle()`内呼び出し（current-cycle inclusion契約付き）・`format_observability_report()`追加
- `scripts/show_retry_notification.py::build_report()`のPipelineへの委譲統一
- **（Rev.2追加）** `src/retry_runtime_logging/retry_runtime_cycle_logger.py`：`log_cycle()`の戻り値を`None`→`bool`へ追加的に変更（AD-3。既存caller/testsのreturn value依存なしをread-only確認済み）
- **（Rev.2追加）** `tests/test_e2e_v6_8_0_retry_notification_cli_report_wiring_foundation.py`：AD-6a記載のmonkeypatch対象4箇所（PI-5A/PI-5B/EX-1/EX-2）の再配置
- 新規E2E（12章）・新規Architecture Guard（8.2）
- `tests/zero_diff_guard_registry.py`への追記（13章。`_SOURCE_CHANGE_CONTRIBUTIONS`の`scripts`寄与を含む）
- Documentation Integration（`docs/ROADMAP.md` / `docs/architecture.md` / `docs/CHANGELOG.md`、実装完了後）

### Out of Scope（4章の重要Invariantと同一、再掲）
- 外部Sender実送信、`release_claim()`残存Suggestion対応、lineage/HRR/durable state変更、Scheduler等6.34領域、ログローテーション、Threshold値変更・環境変数化、Incremental Offset Tracking（AD-1 Option 4）

---

## 12. E2E Test Strategy

新規E2E（仮称`test_e2e_v6_33_0_retry_observability_runtime_integration_foundation.py`）で以下を検証する：

### `RetryRuntimeObservabilityReporter`
- 空ログ（ファイル不在）→ `records=[]` → `evaluate([])`相当の結果（cycle_count=0・HEALTHY・NO_NOTIFICATION）が得られること
- レコードが複数cycle分存在する場合、**全件**が`evaluate()`へ渡されること（windowingが行われないことの確認。`evaluate()`をmonkeypatchし、渡された引数の長さ・内容がreaderの返した全件と一致することを検証。AD-1改訂）
- `observe()`：`RetryRuntimeLogReader.read()`が`OSError`を送出するケースで、例外がそのまま伝播すること（`None`を返さない。raw契約）
- `observe()`：`RetryObservabilityPipeline.evaluate()`が`ValueError`を送出するケース（monkeypatchで模擬）で、例外がそのまま伝播すること
- `observe_and_report()`：上記2ケースいずれも例外を伝播させず、stderrへWARNINGを出力して戻ること（AD-4の単一失敗包含境界の検証）
- `observe_and_report()`：`RetryMetricsCalculator.calculate()`内で`TypeError`相当が発生するケース（不正な型のrecordをmonkeypatchで模擬）でも同様に包含されること
- `observe_and_report()`：`formatter`自身が例外を送出するケースでも同様に包含され、コンソールへreport本体が出力されないこと
- 正常系（HEALTHY/DEGRADED/UNHEALTHY）で`observe()`がPipeline呼び出し結果をそのまま返すこと、`observe_and_report()`が`formatter`の出力をコンソールへ表示すること
- **（Rev.3追加、Round 2 M-1対応）Fault-Injection Tests**：
  - **report-output failure単独**：`formatter`が例外を送出し、かつ`sys.stderr`への書き込みは正常に成功するケースで、`observe_and_report()`が例外を伝播させず、stderrへ想定通りのWARNINGメッセージが出力されること
  - **warning-output failure単独（`_warn_best_effort()`の単体テスト）**：`_warn_best_effort(prefix, exc)`を直接呼び出し、`print()`が例外を送出するよう`file`に書き込み不能なfake stream（`write()`が例外を送出するオブジェクト）を渡すケースで、`_warn_best_effort()`自体が例外を一切伝播させず正常にreturnすること。`str(exc)`が例外を送出するカスタム例外オブジェクト（`__str__`実装がバグっているFake）を渡すケースについても同様に確認する
  - **両方failure（二重障害）**：`observe_and_report()`全体を通し、`formatter`が例外を送出し**かつ**`sys.stderr`への書き込みも失敗するよう`out`とは独立にstderrをfake streamへ差し替えるケースで、`observe_and_report()`が最終的に例外を一切伝播させず正常にreturnすること（WARNINGメッセージがコンソールに出力されなくても、runtime cycleへの伝播がないことが最重要）
  - **`out`のcall-time解決**：`contextlib.redirect_stdout`で標準出力を差し替えた状態で`out`を省略して`observe_and_report()`を呼び出し、整形結果がredirect先へ出力されること（Round 2 MINOR対応。import-time bindingの不具合が再発していないことの確認）
- **（Rev.4追加、Round 3 M-1対応）BaseException Non-Containment Tests**：`Exception`はcontainしてruntime継続、`BaseException`はcontainせず正常に伝播する、という区別をfault-injectionで固定する
  - **`observe_and_report()`：reader境界での`BaseException`非捕捉**：`RetryRuntimeLogReader.read()`をmonkeypatchし`SystemExit`を送出させるケースで、`observe_and_report()`がこれを一切containせず、`SystemExit`がそのまま呼び出し元へ伝播すること（`try/except Exception`の対象外であることの確認）。同様のケースを`KeyboardInterrupt`でも確認する
  - **`observe_and_report()`：evaluate境界での`BaseException`非捕捉**：`RetryObservabilityPipeline.evaluate()`をmonkeypatchし`SystemExit`（または`KeyboardInterrupt`）を送出させるケースで、同様に伝播すること
  - **`observe_and_report()`：format境界での`BaseException`非捕捉**：`formatter`自身が`SystemExit`（または`KeyboardInterrupt`）を送出するケースで、同様に伝播すること
  - **`observe_and_report()`：report-output（`print()`）境界での`BaseException`非捕捉**：`out`に、`write()`が`SystemExit`（または`KeyboardInterrupt`）を送出するfake streamを渡すケースで、同様に伝播すること
  - **`_warn_best_effort()`単体：message formatting境界での`BaseException`非捕捉**：`__str__`が`SystemExit`（または`KeyboardInterrupt`）を送出するカスタム例外オブジェクトを`exc`として直接渡し、`_warn_best_effort()`自身がこれをcontainせず、そのまま伝播すること（`except Exception`では捕捉されないことの確認）
  - **`_warn_best_effort()`単体：stderr output境界での`BaseException`非捕捉**：`write()`が`SystemExit`（または`KeyboardInterrupt`）を送出するfake streamを`sys.stderr`（または`file`引数相当）に渡すケースで、同様に`_warn_best_effort()`から伝播すること
  - 上記いずれのケースも、**`Exception`派生（`RuntimeError`等）を注入した既存のfault-injectionテスト（Round 2対応分）とペアで実行し**、「`Exception`→contain・runtime継続」「`BaseException`→非contain・正常伝播」という挙動の違いを同一テストファイル内で対比可能な形で記述する

### Runtime統合（`scripts/run_retry_runtime.py`）
- `run_cycle()`実行後、`log_cycle()`が`True`を返す場合のみ`observe_and_report()`が呼ばれ、かつ`log_cycle()`より後に呼ばれること（呼び出し順序の検証。呼び出し記録を持つFakeで検証）
- `log_cycle()`が`False`を返す場合（書き込み失敗をFakeで模擬）、`observe_and_report()`が一切呼ばれず、追加のコンソール出力が発生しないこと（Current-Cycle Inclusion Contractの検証。AD-3）
- `observe_and_report()`が結果を返す場合、`format_observability_report()`の出力が標準出力に含まれること
- 既存の`--dry-run` / `--loop` / `--interval-seconds` / Exit Code Policyに回帰がないこと

### 既存ファイルの回帰確認（Rev.2追加）
- `src/retry_runtime_logging/retry_runtime_cycle_logger.py`：`log_cycle()`が成功時`True`、`OSError`捕捉時`False`を返すこと（既存の「例外を送出しない」契約は無変更のまま維持されることも併せて確認）
- `tests/test_e2e_v6_2_0_structured_loop_logging_foundation.py`：本Releaseによる無修正のままの完全PASSを確認（読み取り専用確認済み：同ファイルは戻り値を検証しないため影響を受けない）
- **（Rev.3追加、Round 2 M-1対応）`log_cycle()`のFault-Injection Tests**：
  - **write failure単独**：書き込み不可なパス（既存テスト9と同条件）で`OSError`が発生し、`log_cycle()`が例外を送出せず`False`を返し、stderrへ想定通りのWARNINGが出力されること（既存契約の再確認）
  - **warning-output failure単独**：本ファイル内の`_warn_best_effort()`を直接呼び出し、7章と同一のfault-injection（`write()`が例外を送出するfake stream・`__str__`がバグったカスタム例外）で、例外を伝播させず正常にreturnすることを確認する
  - **両方failure（二重障害）**：書き込み不可なパスに加え、`sys.stderr`もfake streamへ差し替えたケースで、`log_cycle()`が最終的に例外を一切伝播させず`False`を返してreturnすること
- **（Rev.4追加、Round 3 M-1対応）`retry_runtime_cycle_logger.py`の`_warn_best_effort()`単体：BaseException Non-Containment Tests**：7章の`RetryRuntimeObservabilityReporter`側と同一契約（`Exception`のみcontain、`BaseException`は非捕捉）を、本ファイル内のprivate helperについても独立に確認する
  - message formatting境界（`__str__`が`SystemExit`/`KeyboardInterrupt`を送出するカスタム例外）で`_warn_best_effort()`が非containのまま伝播すること
  - stderr output境界（`write()`が`SystemExit`/`KeyboardInterrupt`を送出するfake stream）で同様に伝播すること
  - 2ファイルへ複製された`_warn_best_effort()`が、この`BaseException`非捕捉契約について実装上の差異を持たないこと（挙動の一致を両テストの対比で確認する）

### CLI委譲（`scripts/show_retry_notification.py`）
- 既存Parity Testの拡張・再確認：委譲後も`build_report()`の出力が委譲前と意味的に同一であること（既存5パターン：empty/HEALTHY/DEGRADED/UNHEALTHY(NOTIFY)を再検証）
- `format_report()`の出力文字列が本Release前後で完全に同一であること（既存E2Eの再実行で確認）
- **（Rev.2追加、AD-6a）** PI-5A/PI-5B/EX-1/EX-2の4テストについて、patch対象を`show_retry_notification.RetryNotificationMessageBuilder` / `RetryAlertEvaluator`から`retry_observability_pipeline.retry_observability_pipeline.RetryNotificationMessageBuilder` / `RetryAlertEvaluator`へ変更したうえで、既存と同一のアサーション（呼び出し回数・引数identity・例外伝播）が引き続き成立することを確認する

### Architecture Guard（AST）
- `retry_runtime_observability`が禁止package（8.1）をいずれもimportしないこと
- 既存retry判断package（`retry_engine`等、8.2列挙）のいずれも`retry_runtime_observability`をimportしていないこと（Reverse Dependency禁止）

### Formal Regression
- 正式Inventory（現行34ファイル、5671/5671 PASS）に新規E2Eを加えた完全PASSを確認
- Zero-Diff確認：`src/retry_engine/` / `src/retry_lineage/` / `src/retry_queue/` / `src/retry_history/` / `src/scheduler/` に対するgit diffが0であることを確認

---

## 13. Zero-Diff Guard Registry Impact

**Round 1指摘（MAJOR）**：Rev.1は`_SOURCE_CHANGE_CONTRIBUTIONS`への追記要否を「実装時に確認して確定する」と先送りしていたが、`PROTECTED_PATHS`（`tests/zero_diff_guard_registry.py`91-114行）を読み取り専用で確認した結果、`"scripts"`は既に保護対象パスとして登録済みであることが判明した。本Releaseは`scripts/run_retry_runtime.py`と`scripts/show_retry_notification.py`の両方を変更するため、`_SOURCE_CHANGE_CONTRIBUTIONS`への明示的な追記が必須であり、先送りは不可（Round 1がまさにこの欠落を指摘した）。Rev.2で確定する。

v6.29.0/v6.30.0/v6.32.0と同型のパターン（同ファイル151-153行・177-185行に既存の`"scripts"`寄与record有り）で、`tests/zero_diff_guard_registry.py`へ以下を追記する（既存recordの書き換えは行わない、append-onlyのGR-1原則）：

1. `RELEASE_ORDER`へ`"v6.33.0"`を追記
2. `_SOURCE_CHANGE_CONTRIBUTIONS`へ以下を追記（`"scripts"`は保護対象パスであり必須。Round 1 MAJOR対応）：
   ```python
   ("scripts", "v6.33.0", frozenset({
       "scripts/run_retry_runtime.py",
       "scripts/show_retry_notification.py",
   })),
   ```
3. `_TEST_CHANGE_CONTRIBUTIONS`へ以下を追記：
   ```python
   ("test_e2e_v6_33_0_retry_observability_runtime_integration_foundation.py", "v6.33.0"),
   ("zero_diff_guard_registry.py", "v6.33.0"),
   ("test_e2e_v6_8_0_retry_notification_cli_report_wiring_foundation.py", "v6.33.0"),  # AD-6a monkeypatch対象の再配置
   ```
4. `src/retry_runtime_observability/`（新規package）・`src/retry_runtime_logging/`（`log_cycle()`戻り値変更）は、いずれも`PROTECTED_PATHS`に含まれないことをread-only確認済み（`retry_*`系packageは本Registryが対象とする過去の凍結範囲（画像生成・WordPress・AI Agent系等）に含まれていない）。したがってこの2 packageについては`_SOURCE_CHANGE_CONTRIBUTIONS`への追記は不要と確定する（先送りしない）

---

## 14. Known Issues / Deferred Items

1. **I/O growth・希釈問題（AD-1 Option 1 Cons再掲）**：Full-File Re-readは`.run/retry_runtime_log.jsonl`自体のparseコストが全件readのままであり、ログが長期間・高頻度で肥大化した場合のI/Oコストは未解決。また`enqueue_success_ratio`が長期の健全な履歴で希釈され、直近の劣化を検出しにくくなる傾向も残る。ログローテーション自体が既存Roadmap（v6.2.0設計時点）でPost-MVP Out of Scopeとされていることと整合する形で、本Releaseでも対応しない（Rev.1で検討したBounded Tail Windowは、Round 1 Architecture ReviewでCLI/Runtime間のauthoritative horizon不一致・未承認observability policy変更に該当するとMAJOR指摘され撤回した。15章参照）
2. **観測先はコンソールのみ**：ログ記録・ダッシュボード化等が将来必要になった場合はFuture Candidateとする
3. **v6.32 `release_claim()`残存Suggestion**：本Releaseでは意図的に対応しない（承認済みOut of Scope）。既存のnon-blocking suggestionとして`docs/CHANGELOG.md`に記録済みのまま維持する

## 15. Future Candidates

- **Bounded Tail Window / Incremental Offset Tracking**（AD-1 Option 3・Option 4）によるI/Oコスト削減・希釈問題の緩和。**重要**：Round 1 Architecture Reviewの指摘により、これらは「records調達方式の内部最適化」としては再提案しない。再検討する場合は、(a) Runtime/CLI双方でauthoritative horizonをどう統一するか（あるいは意図的に分離するとして、それをどう明示するか）、(b) health/alert/notification判定へ与える影響、を含む独立したobservability policy変更として、本Releaseとは別に新規Architecture Reviewを経ること
- Observability結果の構造化ログ記録・外部Sender連携（Slack等、Retry Notification Channel Foundation再評価と合わせて検討）

---

## 16. Codex Finding Resolution Matrix

### Round 1

Round 1（`codex-readonly-review`、baseline commit `66aa8e3c8fd8e195ef1baef793a1f37010610408`、review対象：本設計書Rev.1）の結果：`VERDICT: NOT APPROVED` / `BLOCKING: 0` / `MAJOR: 4` / `MINOR: 2`。

#### MAJOR

| # | Round 1指摘 | Rev.2での対応 | 対応箇所 | Status |
|---|---|---|---|---|
| M-1 | AD-4のfailure containmentが不完全（`OSError`/`ValueError`のみ捕捉。malformed recordsによる`TypeError`が未捕捉。formatting/printingがcontainment境界外）。`log_cycle()`失敗時に`observe()`がstale historyを評価し、call-order保証が崩れる | 失敗包含境界を`reader→evaluate→format→console output`全体を覆う単一境界（`observe_and_report()`）へ拡張し、捕捉範囲を`Exception`（`BaseException`除く）へ拡大。`log_cycle()`の戻り値をbool化し、成功時のみ`observe_and_report()`を呼ぶcurrent-cycle inclusion契約を追加 | AD-3・AD-4・7章 | **Resolved（Round 1の指摘範囲内。ただしRound 2で本境界自体の別のgap——WARNING出力自体の無防備さ——が新規に検出された。下記Round 2 M-1参照。Rev.3で対応済み）** |
| M-2 | AD-1のBounded Tail Windowは「records調達方式」に留まらず、実質的に新しいobservability policyになっている。どちらのhorizonが権威的かreport/formatterに明示がない | Option 3（Bounded Tail Window）を撤回し、Option 1（Full-File Re-read）を採用。Runtime/CLIとも全件を`evaluate()`へ渡すことで、authoritative horizonの不一致という問題自体を解消 | AD-1 | **Resolved**（Round 2で再確認済み、異論なし） |
| M-3 | regression/zero-diff計画が不成立：既存v6.8テストがCLI-local evaluator/builder symbolsをmonkeypatchしており、delegationがこれを迂回する | AD-6aとして、PI-5A/PI-5B/EX-1/EX-2のpatch対象を`retry_observability_pipeline.retry_observability_pipeline`モジュールへ再配置する具体的な移行戦略を明記。アサーション自体は変更しない（test weakeningではない） | AD-6a・12章 | **Resolved**（Round 2で「実際のlookup seamであり、delegation破損時に確実にFAILする」ことを確認済み） |
| M-4 | Section 13がmodified scripts（2ファイル）のsource-change contributionを記載していない（`scripts`はprotected path） | `PROTECTED_PATHS`を確認し`"scripts"`が保護対象であることを確定。`_SOURCE_CHANGE_CONTRIBUTIONS`へ`("scripts", "v6.33.0", frozenset({...}))`を明記 | 13章 | **Resolved**（Round 2で既存registry構造・ratchet/append-only規律との整合を確認済み） |

#### MINOR

| # | Round 1指摘 | Rev.2での対応 | 対応箇所 | Status |
|---|---|---|---|---|
| m-1 | 主張されているbackward compatibilityはAPI的な追加互換性に過ぎず、zero-diffなruntime挙動ではない（成功cycleごとにstdoutブロックが増える） | Backward compatibility invariantの記述を「CLI引数/Exit Code/判断/durable state/side-effect safetyはzero-diff、runtime consoleへの追加出力はRelease 6.33で承認されたadditive behavior changeである」と明確に区別して表現するよう改訂 | 10章 | **Resolved**（Round 2で再確認済み） |
| m-2 | `window_size <= 0`がsilentlyに全件選択となり、bounded-window契約と矛盾する | AD-1でwindowing自体を撤回したため、`window_size`パラメータそのものが設計から削除された（本指摘の前提となるコードパスが消滅） | AD-1・7章 | **Resolved（設計変更により前提解消）** |

#### SUGGESTIONS（Blocking/Majorではないが確認した対応状況）

| # | Round 1指摘 | Rev.2での対応 |
|---|---|---|
| s-1 | runtime出力契約を完全に明文化し、「latest 20 valid records」horizonラベルをテスト込みで用意する | windowing撤回によりhorizonラベル自体が不要に。AD-1・Data Flow（9章）でRuntime/CLIとも「全件」であることを明記 |
| s-2 | `window_size`を正の整数としてvalidateする | windowing撤回によりvalidation自体が不要に |
| s-3 | dependency injection箇所で`pipeline is not None`の明示チェックを使う | 7章のコンストラクタで`pipeline if pipeline is not None else RetryObservabilityPipeline()`へ変更済み |

### Round 2

Round 2（`codex-readonly-review`、baseline commit `66aa8e3c8fd8e195ef1baef793a1f37010610408`、review対象：本設計書Rev.2）の結果：`VERDICT: NOT APPROVED` / `BLOCKING: 0` / `MAJOR: 1` / `MINOR: 2`。

#### MAJOR

| # | Round 2指摘 | Rev.3での対応 | 対応箇所 | Status |
|---|---|---|---|---|
| M-1 | `observe_and_report()`のexception handler内の`print(..., file=sys.stderr)`（WARNING出力）自体が無防備。report-output失敗時、WARNING整形・出力自体がさらに失敗すると例外が伝播しruntime cycleを止めうる。`log_cycle()`のWARNING出力にも同型のgapがある | WARNING出力（メッセージ整形＋`print()`）を`_warn_best_effort()`ヘルパーへ切り出し、ヘルパー内部で`Exception`をcontainし何も再送出しない設計へ変更。`log_cycle()`側にも同一パターンのヘルパーを適用。fault-injection tests（report-output failure単独／warning-output failure単独／両方failure）を12章へ追加 | AD-4・7章・12章 | **Resolved** |

#### MINOR

| # | Round 2指摘 | Rev.3での対応 | 対応箇所 | Status |
|---|---|---|---|---|
| m-1 | `log_cycle()`の戻り値変更を一律「additive」と呼び、`True`が「確実に記録された」ことを保証するかのような表現は過大。`True`が保証できるのは`OSError`を送出せず完了したことのみで、`fsync`durabilityや外部変更からの保護は保証しない | `True`の意味を「append/write/closeがOSErrorを送出せず完了したこと」に限定し、durability・外部変更保護を保証しないことをdocstringへ明記。既存`except OSError`のcatch対象範囲は変更しない | AD-3・7章 | **Resolved** |
| m-2 | `out: TextIO = sys.stdout`がimport時にstdoutをbindするため、後からの`contextlib.redirect_stdout`等のin-process redirectionをcaptureできない | `out: TextIO | None = None`へ変更し、`out`省略時は呼び出し時点の`sys.stdout`を都度参照するcall-time解決へ変更。`contextlib.redirect_stdout`でのcapture確認テストを12章へ追加 | AD-5・7章・12章 | **Resolved** |

### Round 3

Round 3（`codex-readonly-review`、baseline commit `66aa8e3c8fd8e195ef1baef793a1f37010610408`、review対象：本設計書Rev.3）の結果：`VERDICT: NOT APPROVED` / `BLOCKING: 0` / `MAJOR: 1` / `MINOR: 1`。

#### MAJOR

| # | Round 3指摘 | Rev.4での対応 | 対応箇所 | Status |
|---|---|---|---|---|
| M-1 | 12章に、`BaseException`派生（`SystemExit`/`KeyboardInterrupt`）が`observe_and_report()`・`_warn_best_effort()`を素通りして正常に伝播することを証明するfault-injectionテストが欠落している。Graceful Shutdown除外方針に対するregression coverageが存在しない | `observe_and_report()`のreader/evaluate/format/report-output各境界、および両ファイルの`_warn_best_effort()`（message formatting／stderr output境界）について、`SystemExit`/`KeyboardInterrupt`が非containのまま伝播することを固定するBaseException Non-Containment Testsを12章へ明記。`Exception`→contain・`BaseException`→非containという対比が同一テストファイル内で明確になるよう記述 | 12章 | **Resolved** |

#### MINOR

| # | Round 3指摘 | Rev.4での対応 | 対応箇所 | Status |
|---|---|---|---|---|
| m-1 | 16章Open Questionsが、既にユーザー承認済みの`log_cycle()`scope解釈・Bounded Tail Window先送りを依然「要確認」のまま記載しており、採用済み設計・現在の承認済みScopeと矛盾している | ユーザー承認済みの4項目（`log_cycle()`のscope解釈／AD-6a test migration／Bounded Tail Window先送り／`_warn_best_effort()`のmodule-private複製）を「Confirmed Decisions」へ移動し、Open Questionsから除去 | 16章 | **Resolved** |

### Confirmed Decisions（ユーザー承認済み、2026-09-13）

以下はいずれもユーザーが明示的に承認済みであり、Open Questionsの対象ではない：

1. `RetryRuntimeCycleLogger.log_cycle()`の戻り値変更（`None`→`bool`）は、Release 6.33のApproved Scope内として承認済み
2. AD-6aのtest migration（monkeypatch対象の再配置）は、Round 2での検証（実際のlookup seamへの再配置であり、delegationが破損すれば確実にFAILすることを確認済み）をもって解消済みとして扱う
3. Bounded Tail Window（windowing）は、Release 6.33からは除外し、15章Future Candidatesへ先送りすることを承認済み。Release 6.33内で追加の方針明記は不要
4. `_warn_best_effort()`は、本Releaseでは`retry_runtime_observability_reporter.py`と`retry_runtime_cycle_logger.py`の2ファイルへモジュールプライベートな関数として複製する設計を承認済み。共有utility／新規packageは新設しない

### 未解消・オープンな論点（ユーザー確認事項）

NONE（Round 3時点で確認された論点はすべてConfirmed Decisionsへ移動済み）
