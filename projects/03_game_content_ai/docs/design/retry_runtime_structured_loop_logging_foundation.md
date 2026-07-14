# Structured Loop Logging Foundation（v6.2.0）

作成日：2026-07-14
作成者：Claude Code（Architecture Design・Implementation・Documentation）／ユーザー（最終承認）
状態：**実装完了（Architecture Review反映済み）**
分類：Architecture Release（[development_workflow.md](../development_workflow.md) 6章）

---

## 0. 前提・分類根拠

### 0.1 現在のRuntime構成

```
CLI（scripts/run_retry_runtime.py）
    → RetryRuntimeLock（v6.0.0、多重起動防止）
    → RetryRuntimeShutdown（v6.1.0、Graceful Shutdown）
    → RetryRuntimeLoop（v5.5.0、interval毎の繰り返し実行）
    → RetryRuntimeOrchestrator（v5.2.0／v5.3.0、1サイクルの実行順序）
    → RetryManager（retry_engine、実際のretry実行）
```

- ROADMAP.md v6.1.0エントリで「Structured Loop Logging Foundation：ループ実行のサイクル番号・タイムスタンプ・JSON出力等、運用監視のための構造化ログ基盤」が次Release候補として明記されていた。本Releaseはこの候補に着手する。
- 比較検討の結果、同時に候補だった「Stale Lock Recovery Foundation」は、stale判定が`RetryRuntimeLock`の責務そのものに本質的に食い込むため、「Lockへの責務追加禁止」という本Releaseの制約と構造的に衝突すると判断し見送った（Architecture Design段階の比較検討）。

### 0.2 Problem（現状の課題）

現状、Retry Runtimeの実行結果は`format_summary()`によるコンソール出力のみで、機械可読な記録が一切残らない。運用監視（Retry Metrics / Monitoring、ROADMAP未着手項目）を将来構築するための入力データが存在しない。

### 0.3 Goal

Retry Runtimeの各サイクル終了時に、JSON Lines形式で1サイクル1レコードのRuntimeログを出力する独立Foundationを新設する。運用監視の土台を構築することを目的とし、監視・集計・ダッシュボード自体は対象外とする。

### 0.4 Requirements（Architecture Reviewで確定した制約）

- Runtime Pipeline（CLI → Lock → Shutdown → Loop → Orchestrator → RetryManager）は変更しない
- Loggingの実行はCLI層（`scripts/run_retry_runtime.py`）のみに限定する
- `RetryRuntimeLoop` / `RetryRuntimeShutdown` / `RetryRuntimeLock` / `RetryManager` / `RetryRuntimeOrchestrator`への責務追加は禁止
- DIのみで接続する
- JSONレコードのスキーマを本Releaseで固定し、将来の変更はフィールド追加のみを基本方針とする（既存フィールドの意味変更は禁止）
- ログ書き込み失敗はRetry Runtimeを停止させない（ベストエフォート、ただしstderrへWARNING出力）

### 0.5 Fast Track Checklist該当確認

| 条件 | 該当有無 | 内容 |
|---|---|---|
| Public API変更 | なし | 既存クラスのシグネチャは無改修。新規クラスの追加のみ |
| Constructor変更 | なし | 既存クラスのConstructorは無改修 |
| Composition Root変更 | なし | `RetryCompositionRoot`は無改修 |
| **Layer変更** | **あり** | 新規パッケージ`src/retry_runtime_logging/`を新設する |
| Dependency変更 | なし | 標準ライブラリ（`json`／`datetime`／`sys`）のみで実装 |
| **永続化変更** | **あり** | 新しい永続化アーティファクト（`.run/retry_runtime_log.jsonl`）が発生する |
| Event変更 | なし | 該当なし |
| 外部I/O変更 | なし | 該当なし |

Layer変更・永続化変更に該当するため、Architecture Releaseに分類する。

---

## 1. Architecture Overview

### 1.1 設計方針

`RetryRuntimeCycleLogger`（新規パッケージ`src/retry_runtime_logging/`）は、

- 「1サイクル分の実行結果をJSON Linesへ1行追記すること」のみに責務を限定した薄いコンポーネント
- `RetryRuntimeLock` / `RetryRuntimeShutdown` / `RetryRuntimeLoop` / `RetryRuntimeOrchestrator` / `RetryManager`のいずれもimportしない（`RetryRuntimeCycleResult`の型参照のみ、`format_summary()`と同型の依存）
- サイクル番号のカウントは本クラスの責務にしない。`RetryRuntimeLoop`のStateless性を維持するため、カウンタは`scripts/run_retry_runtime.py`の`run_cycle()`クロージャ内のローカル変数（`cycle_count`）として保持する

### 1.2 DIのみによる接続

`RetryRuntimeCycleLogger`は`RetryRuntimeLoop`のConstructor Injection（`run_once_fn` / `sleep_fn` / `should_continue_fn`）には一切登場しない。`run_cycle()`クロージャの内部で、`orchestrator.run_once()`の結果を受け取った直後に直接呼び出されるのみであり、Pipelineの各段（Lock/Shutdown/Loop/Orchestrator）はいずれも`RetryRuntimeCycleLogger`の存在を知らない。

### 1.3 JSON Schema（固定）

本Releaseで以下のスキーマを固定する。将来の変更は**フィールド追加のみ**を基本方針とし、既存フィールドの意味変更は行わない。

| フィールド | 型 | 内容 |
|---|---|---|
| `cycle_number` | int | 1から始まる連番（プロセス起動ごとにリセット。永続化しない） |
| `timestamp` | str | ISO8601形式（UTC、`datetime.now(timezone.utc).isoformat()`） |
| `dry_run` | bool | `--dry-run`指定の有無 |
| `enqueue_scanned` | int | `RetryEnqueueTriggerResult.scanned` |
| `enqueue_enqueued` | int | `RetryEnqueueTriggerResult.enqueued` |
| `enqueue_skipped_existing` | int | `RetryEnqueueTriggerResult.skipped_existing` |
| `enqueue_skipped_status` | int | `RetryEnqueueTriggerResult.skipped_status` |
| `enqueue_skipped_history` | int | `RetryEnqueueTriggerResult.skipped_history` |
| `enqueue_failed` | int | `RetryEnqueueTriggerResult.failed` |
| `scheduler_candidates` | int | `len(result.scheduler_events)` |
| `execution_executed` | int | `len(result.execution_results)` |
| `removal_removed` | int | `len(result.removal_results)` |
| `cleanup_cleaned` | int | `len(result.cleanup_results)` |
| `terminal_cleanup_cleaned` | int | `len(result.terminal_cleanup_results)` |
| `history_recorded` | int | `len(result.history_results)` |

命名は`format_summary()`のセクション名（Enqueue/Scheduler/Execution/Removal/Cleanup/TerminalCleanup/History）と対応させ、コンソール出力とログ出力の対応関係を分かりやすくした。

### 1.4 Architecture図

```
CLI → argparse（既存、無変更）
    → RetryRuntimeLock(lock_path).acquire()（v6.0.0、無改修）
         → [--loop の場合のみ] RetryRuntimeShutdown().install()（v6.1.0、無改修）
              → RetryCompositionRoot.from_env()（無改修）
              → RetryRuntimeOrchestrator.from_composition_root()（無改修）
              → RetryRuntimeCycleLogger(log_path=...)（新規、scripts層で直接構築）
              → RetryRuntimeLoop(
                    run_once_fn=run_cycle,       ← run_cycle内でcycle_logger.log_cycle()を呼ぶ
                    sleep_fn=shutdown.interruptible_sleep,
                    should_continue_fn=shutdown.should_continue,
                    interval_seconds=interval_seconds,
                 ).run()（RetryRuntimeLoop自体は無改修）
         → lock.release()（with文により保証、既存のまま）
    → exit code 0
```

Pipeline本体の縦の実行順序（Lock→Shutdown→Loop→Orchestrator→RetryManager）は一切変更されない。ログ出力は`run_cycle()`クロージャ内でのみ発生する横方向の追加である。

---

## 2. Component Responsibilities

| コンポーネント | 責務 | 変更有無 |
|---|---|---|
| `RetryRuntimeCycleLogger`（新規） | 1サイクル分の結果をJSON Linesへ1行追記することのみ。書き込み失敗時はベストエフォートでstderrへWARNINGを出力する | 新規追加 |
| `scripts/run_retry_runtime.py` | `RetryRuntimeCycleLogger`の構築と、`run_cycle()`内での呼び出しのみ追加。サイクル番号カウンタもここに保持する | 変更（`main()`のみ） |
| `RetryRuntimeLoop` | 無変更。`RetryRuntimeCycleLogger`の存在を一切知らない | 無改修 |
| `RetryRuntimeShutdown` / `RetryRuntimeLock` | 無変更 | 無改修 |
| `RetryRuntimeOrchestrator` / `RetryManager` / `RetryCompositionRoot` | 無変更（`RetryRuntimeCycleResult`型の参照のみ、`format_summary()`と同型） | 無改修 |

---

## 3. Runtime Flow

### 3.1 単発実行

```
1. main() 開始、RetryRuntimeLock.acquire() 成功
2. RetryCompositionRoot.from_env() → RetryRuntimeOrchestrator 構築
3. RetryRuntimeCycleLogger 構築
4. run_cycle() 呼び出し
   → cycle_count = 1
   → orchestrator.run_once() 実行
   → print(format_summary(result))（既存どおり）
   → cycle_logger.log_cycle(cycle_number=1, result=result, dry_run=args.dry_run)
5. 正常終了（exit code 0）
```

### 3.2 `--loop`実行

```
1〜3. 単発実行と同じ
4. RetryRuntimeLoop.run() 開始
   while shutdown.should_continue():
       run_cycle()  # cycle_countが1, 2, 3...とインクリメントされ、
                     # 呼び出しのたびにログが1行ずつ追記される
       shutdown.interruptible_sleep(interval_seconds)
5. シグナル受信等でLoop終了 → exit code 0
```

### 3.3 ログ書き込み失敗時（Runtime Failure Policy）

```
1. cycle_logger.log_cycle() 内でOSError（権限エラー・ディスク容量不足等）発生
2. 例外を送出せず、stderrへ "WARNING: Failed to write runtime log: <詳細>" を出力
3. run_cycle() は正常にreturn（結果はコンソールへ表示済み）
4. RetryRuntimeLoop / Retry Runtime本体は処理を継続する
```

Exit Code Policy（`docs/design/retry_runtime_script_entry_point_foundation.md` 2.4節）とは区別し、ログ書き込みの成否はプロセスの終了コードに一切影響しない。

---

## 4. API Design

```python
# src/retry_runtime_logging/retry_runtime_cycle_logger.py
class RetryRuntimeCycleLogger:
    def __init__(self, log_path: Path):
        self.log_path = log_path

    def log_cycle(
        self,
        cycle_number: int,
        result: RetryRuntimeCycleResult,
        dry_run: bool = False,
    ) -> None:
        """1サイクル分の結果をJSON Lines 1行として追記する。失敗時は
        例外を送出せずstderrへWARNINGを出力する。"""
        ...
```

```python
# scripts/run_retry_runtime.py（main()内、抜粋）
cycle_logger = RetryRuntimeCycleLogger(
    log_path=_PROJECT_ROOT / ".run" / "retry_runtime_log.jsonl",
)
cycle_count = 0

def run_cycle():
    nonlocal cycle_count
    cycle_count += 1
    result = orchestrator.run_once(dry_run=args.dry_run)
    print(format_summary(result))
    cycle_logger.log_cycle(
        cycle_number=cycle_count,
        result=result,
        dry_run=args.dry_run,
    )
    return result
```

---

## 5. Logging Policy / Runtime Failure Policy

- 出力先：`<project_root>/.run/retry_runtime_log.jsonl`（JSON Lines形式）
- 親ディレクトリが存在しない場合は作成する。ファイルが存在しない場合は新規作成、存在する場合は追記する
- ログファイルはランタイム生成物であり、`.run/`として既にGit管理対象外（`.gitignore`、v6.0.0で登録済み）
- ログ書き込みの失敗（`OSError`）は例外を送出せず、stderrへ`WARNING: Failed to write runtime log: <詳細>`を出力したうえでRetry Runtime本体の処理を継続する（ベストエフォート）

---

## 6. Out of Scope

- ログローテーション・保持期間管理
- Metrics集計・Dashboard化・Prometheus／SQLite／CSV等への出力（ROADMAP「Retry Metrics / Monitoring」で別途検討）
- ログ出力先の環境変数化（固定パス。将来必要になった時点で`from_env()`化を検討）
- Daemon化・Windows Service化（v6.0.0／v6.1.0で前提を整備済みだが本Releaseの対象外）
- `format_summary()`のコンソール出力形式の変更
- Orchestrator/RetryManager内部の個別処理単位でのログ出力（サイクル単位のサマリーのみ）
- Stale Lock Recovery Foundation（引き続き未着手。0.1節参照）

---

## 7. Alternatives Considered

| # | 案 | 却下理由 |
|---|---|---|
| 1 | Stale Lock Recovery Foundationを先に着手 | stale判定が`RetryRuntimeLock`の責務に本質的に食い込み、「Lockへの責務追加禁止」制約と構造的に衝突する |
| 2 | ログ責務を`RetryRuntimeOrchestrator.run_once()`内部に持たせる | ドメインオーケストレーターにI/O・フォーマット責務を持ち込むことになり、Composition/Orchestration責務分離（v5.2.0）の原則に反する |
| 3 | `format_summary()`自体をJSON出力に置き換える | v5.4.0設計書が温存した「将来Formatterクラスへ抽出可能な構造」の意図と矛盾し、既存の人間可読コンソール出力を壊す |

---

## 8. Known Risks

- **ログファイル肥大化**：ローテーションを行わないため、長時間`--loop`運用時にファイルが際限なく成長する。Windows Service Foundation着手時に再評価する既知のTrade-off
- **サイクル番号の非永続性**：プロセス再起動ごとに1から再カウントする。診断目的のみのため実害は限定的
- **ログ書き込み失敗時のベストエフォート方針**：Retry Runtime全体のfail-fast方針（v5.4.0 Exit Code Policy）とは異なる例外的な扱いであり、Architecture Reviewで明示的に合意済みの方針である

---

## 9. Technical Debt

- Stale Lock Recovery Foundation（v6.0.0から持ち越し）は本Releaseでも引き続き未着手
- ログ出力先の環境変数化は見送った。運用上の要望が出た時点でFuture Extensionとして検討する
- Retry Metrics / Monitoring（ROADMAP未着手項目）は、本Foundationが生成するJSON Linesログを入力データとして今後着手可能になった

---

## 10. Recommendation

- 新規独立パッケージ`src/retry_runtime_logging/`（`RetryRuntimeCycleLogger`）を新設し、`scripts/run_retry_runtime.py`の`run_cycle()`内にのみ配線する設計を採用した。`RetryRuntimeLock` / `RetryRuntimeShutdown` / `RetryRuntimeLoop` / `RetryRuntimeOrchestrator` / `RetryManager` / `RetryCompositionRoot`はいずれも無改修（0 diff）のまま、Runtime Pipelineの縦の実行順序を一切変えずに実現した。
- JSON Schemaを本Releaseで固定し、将来のフィールド追加のみを許容する方針とした。

---

## Status

- [x] Architecture Design（比較検討・11項目）
- [x] ChatGPT Architecture Reviewの反映（Runtime Failure Policy／JSON Schema固定／DI例の反映）
- [x] 人間の実装承認
- [x] 実装着手（`src/retry_runtime_logging/`新設、`scripts/run_retry_runtime.py`配線）
- [x] Test Review（新規E2E 64/64 PASS。既存回帰：v5.9.0 64/64・v6.0.0 43/43・v6.1.0 44/44、いずれも0 diff）
- [ ] Release Review
- [ ] commit／push
