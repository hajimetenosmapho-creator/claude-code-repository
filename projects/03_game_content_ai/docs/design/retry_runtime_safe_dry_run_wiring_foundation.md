# Retry Runtime Safe Dry Run Wiring Foundation（v5.7.0）

作成日：2026-07-12
作成者：Claude Code（Architecture Design・Architecture Review・実装）／ユーザー（最終承認）
状態：**完成版（実装済み）**

---

## 1. 背景

v5.6.0（Retry Runtime Safe Dry Run Foundation）で`RetryRuntimeOrchestrator.run_once(dry_run=True)`が「安全なdry_run」として完成した。しかし`scripts/run_retry_runtime.py`はCLI引数を一切持たず、常に`dry_run=False`（実行）でしか起動できないため、v5.6.0で作った安全機構はPythonから直接呼び出すかテストコードでしか使えない状態にあった。

v5.6.0の設計書（`docs/design/retry_runtime_safe_dry_run_foundation.md` 4節）およびChatGPTレビュー反映（同3.2節）で、CLI配線は次Release候補「Retry Runtime Safe Dry Run Wiring」として明示的に切り出されていた。v5.3.0（Execution Release）→v5.4.0（Entry Point Release）と同じ、本プロジェクト一貫のパターンを踏襲するものである。

---

## 2. Architecture Design

### 2.1 採用案

`scripts/run_retry_runtime.py`の`main()`関数内部のみを変更し、`--dry-run`フラグを`RetryRuntimeOrchestrator.run_once(dry_run=...)`（v5.6.0）へ伝播させる。

1. `main()`内で`argparse`をローカルimportし、`ArgumentParser`を組み立てて`--dry-run`（`action="store_true"`、デフォルト`False`）を解析する
2. `--dry-run`指定時、`main()`が`print("[DRY RUN MODE]")`を出力する（`format_summary()`は経由しない）
3. `orchestrator.run_once(dry_run=args.dry_run)`を呼び出す
4. `format_summary(result)`は**無改修**のまま呼び出す

### 2.2 変更対象を`main()`内部のみへ限定した理由（ユーザー確定方針）

Architecture Reviewの過程で、以下4点について複数の設計選択肢が検討されたが、いずれも「変更範囲の最小化」「既存責務の維持」を優先し、より変更範囲の小さい案を採用した。

| 論点 | 検討した選択肢 | 採用案 | 理由 |
|---|---|---|---|
| argparseの扱い | ①独立関数`parse_args()`へ分離／②`main()`内で直接処理 | ② | フラグが`--dry-run`1つのみの現時点では分離の恩恵がない（YAGNI）。`--loop`等が増えた時点で再検討する |
| `import argparse`の位置 | ①モジュールトップレベル／②`main()`内のローカルimport | ② | CLI関心事を`main()`内に完全に閉じ込め、モジュールレベルの既存import一覧を不変に保つ |
| dry_run表示 | ①`format_summary(result, dry_run)`へ引数追加／②`main()`側で`print()` | ② | `format_summary()`の既存責務（`RetryRuntimeCycleResult`→Summary文字列）にCLI都合の情報を持ち込まないため |
| Known Issueの案内 | ①Summary内に注記を追加／②CLI出力には含めずdocs側で管理 | ② | CLI Summaryの責務を「実行結果の表示のみ」に限定するユーザー方針を優先 |

### 2.3 却下案

| 案 | 却下理由 |
|---|---|
| A. `RetryRuntimeCycleResult`へ`dry_run`フィールドを追加する | CLI都合の情報をDomain側のResultクラスへ持ち込むことになり、「Retry Runtimeの実行結果のみを表す」という既存責務に反する |
| B. `format_summary(result, dry_run)`へシグネチャ変更する | Summary生成の責務にCLI層の関心事が混在する。dry_run表示は`main()`側の`print()`で完結させる方針を優先した |
| C. `parse_args()`への関数分離 | フラグが1つのみの現時点では分離の恩恵がなく、YAGNIに反する |
| D. Enqueue側のdry_run対応を本Releaseに含める（Retry Enqueue Trigger Dry Run Foundationの前倒し） | ①未完了ではCLIから`--dry-run`自体を呼べず実利がない。「1 Release = 1目的」の原則にも反する。次Release候補として独立させた |
| E. CLI SummaryへKnown Issue（Enqueue非対象）の注記を表示する | CLI Summaryの責務を「実行結果のみ」に限定する方針を優先し、既知の制約の説明はdocs側（CHANGELOG.md Known Issues）で管理することとした |

---

## 3. 最終スコープ

### 対象

- `scripts/run_retry_runtime.py`の`main()`内部のみ：
  - `argparse`のローカルimport・`ArgumentParser`組み立て・`--dry-run`解析
  - `[DRY RUN MODE]`表示（`--dry-run`指定時のみ）
  - `orchestrator.run_once(dry_run=args.dry_run)`への引数伝播
- `tests/test_e2e_v5_7_0_retry_runtime_safe_dry_run_wiring_foundation.py`新規作成
- architecture.md / ROADMAP.md / CHANGELOG.md更新

### 対象外（Non-Goal）

- `RetryRuntimeOrchestrator` / `RetryManager` / `RetryExecutor` / `RetryCompositionRoot` / `RetryRuntimeCycleResult`への変更（いずれも無改修）
- `format_summary()`のシグネチャ変更・実装変更（無改修）
- `parse_args()`等の関数分離（YAGNI、将来フラグ増加時に再検討）
- CLI SummaryへのKnown Issue説明文の表示
- `RetryEnqueueTrigger`側のdry_run対応（Enqueue自体の抑止）→ 次Release候補「Retry Enqueue Trigger Dry Run Foundation」
- `--loop`のCLI配線
- Exit Code再設計・Summary Formatterクラスへの抽出

---

## 4. テストで確認した内容

`tests/test_e2e_v5_7_0_retry_runtime_safe_dry_run_wiring_foundation.py`（86件、全PASS）で以下を確認した。

1. `format_summary()`のシグネチャ・実装が無改修であること（`(result)`のみ、dry_run分岐を含まない）
2. `RetryRuntimeCycleResult`が`dry_run`フィールドを持たないこと
3. `parse_args()`という独立関数が存在しないこと（YAGNI）
4. `argparse`が`main()`内でのみimportされ、モジュールトップレベルではimportされていないこと
5. `main()`が`--dry-run`未指定時は`run_once(dry_run=False)`、指定時は`run_once(dry_run=True)`を呼び出すこと（`RetryCompositionRoot` / `RetryRuntimeOrchestrator`をFakeに差し替えたモック検証）
6. `--dry-run`指定時のみ標準出力に`[DRY RUN MODE]`が含まれ、`format_summary()`の出力（Summary本文）自体は`--dry-run`の有無に関わらず同一であること
7. サブプロセスによる実CLI呼び出し（全Gate無効）で、`--dry-run`有無いずれもreturncode 0・副作用ファイルなし
8. 不正な環境変数指定時、`--dry-run`有無に関わらずfail-fast（非0 returncode・ValueErrorのtraceback）が維持されること
9. 既存13パッケージ・他scriptsが無改修であること（git diff）

既存回帰確認として、変更前後で関連するE2Eテスト（v5.4.0・v5.5.0・v5.6.0）および無関係な既存46ファイルを実行し、新規に発生した差分がすべて意図的なもの（下記`[KI-24]`）であり、それ以外の予期しない回帰がないことを確認した。

- `tests/test_e2e_v5_4_0_retry_runtime_script_entry_point_foundation.py`：66/67 PASS（新規1件FAIL、`[KI-24]`）
- `tests/test_e2e_v5_5_0_retry_runtime_loop_foundation.py`：36/37 PASS（新規1件FAIL、`[KI-24]`）
- `tests/test_e2e_v5_6_0_retry_runtime_safe_dry_run_foundation.py`：48/49 PASS（新規1件FAIL、`[KI-24]`）
- それ以外の既存46ファイルはいずれも変更前と同一の結果（`v1.10.0`の`[KI-1]`、`v4.8.0`/`v4.9.0`のv5.0.0由来の既存不整合など、本Releaseと無関係な既存事象を除く）

---

## 5. Known Issue

### 5.1 [KI-23]（新規、CHANGELOG.md記載）：`--dry-run`指定時でもEnqueueは通常どおり実行される

`--dry-run`指定時も、`RetryEnqueueTrigger`はdry_run非対応のため、WorkflowMonitor上のFAILED/TIMEOUTはRetry Queueへ通常どおりenqueueされる。v5.6.0時点では設計書内の記述に留まっていたが、CLIで一般公開されることに伴い正式なKnown Issueとして記録する。

- 対応予定Release：「Retry Enqueue Trigger Dry Run Foundation」

### 5.2 [KI-24]（新規、CHANGELOG.md記載）：本Releaseにより、v5.4.0/v5.5.0/v5.6.0の一部Architecture GuardがFAILする

`scripts/run_retry_runtime.py`への`argparse`導入・`main()`変更に伴い、同ファイルの「無改修であること」を前提としたArchitecture Guardテストが新規にFAILする。`[KI-3]`〜`[KI-22]`と同型の既知差分であり、対応不要。

---

## 6. Technical Debt（本Release対象外、記録のみ）

`NullRetryEnqueueTrigger.enqueue_pending_failures()`のシグネチャ不整合：v5.0.0で`RetryEnqueueTrigger.enqueue_pending_failures()`に追加された`max_attempts`引数が、`NullRetryEnqueueTrigger`側には存在しない（`limit`引数のみ）。

- **可視化**：本節にて記録
- **理由（先送りの根拠）**：`RetryCompositionRoot`は`RetryEnqueueTrigger`を常に実体で構築するため（Feature Gateを持たない設計、v4.6.0〜v5.0.0）、現状この経路は到達不能であり実害がない
- **将来の解消タイミング**：`NullRetryEnqueueTrigger`が実際に構築される設計変更が入る場合（例：`RetryEnqueueTrigger`へFeature Gateを追加する等）に、あわせて修正を検討する。本Releaseでは対象外（ユーザー確定方針）
