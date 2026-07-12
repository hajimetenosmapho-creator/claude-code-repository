# Retry Runtime Safe Dry Run Foundation（v5.6.0）

作成日：2026-07-12
作成者：Claude Code（Architecture Design・Architecture Review・実装）／ChatGPT（GPT-5.6 Sol、Architecture Review）／ユーザー（最終承認）
状態：**完成版（実装済み）**

---

## 1. 背景

v5.3.0（Retry Runtime Run Once Foundation）で`RetryRuntimeOrchestrator.run_once()`にKnown Issueとして記録された「安全なdry_runになっていない」問題への対応。

`RetryExecutor.execute()`（`src/retry_engine/retry_executor.py`）は、`dry_run`の値に関わらず常に`outcome=RetryOutcome.RETRIED`を返していた。`WorkflowEngineManager.run(event, dry_run=True)`自体は安全（Agent層の`act()`が呼ばれず、WordPress投稿等の外部作用はゼロ）だったが、後続の`RetryQueueUpdateDecider`が「実際に再試行された」と誤判定し、`RetryQueueRemovalExecutor`によるQueue除去・`RetryHistoryRecordExecutor`による履歴記録という**取り消せない副作用**が発生していた。

`docs/ROADMAP.md`のv5.5.0時点の候補欄に「Loop Wiringは、dry_run安全性（Safe Dry Run Foundation）の状況を踏まえて着手要否を判断する」と明記されていたこと、`docs/design/retry_runtime_loop_foundation.md`のArchitecture Reviewでも同様の指摘があったことから、Release 5.6のテーマとして採用した。

---

## 2. Architecture Design

### 2.1 採用案

1. `RetryOutcome`（`retry_result.py`）に新しい値`DRY_RUN = "dry_run"`を追加する
2. `RetryExecutor.execute()`が`request.dry_run=True`の場合、`WorkflowEngineManager.run()`の呼び出し自体は維持する（`workflow_engine_result`により「何が起きたはずか」を可視化する価値があるため）が、戻り値の`outcome`を`RetryOutcome.RETRIED`ではなく`RetryOutcome.DRY_RUN`とする
3. `RetryQueueUpdateDecider` / `RetryHistoryRecordExecutor` / `RetryQueueRemovalExecutor` / `RetryQueueCleanupDecider`（v4.3.0）は**無改修**とする。いずれも「outcome==RETRIEDかどうか」またはallowlist方式で判定しているため、`DRY_RUN`は自動的に安全側（NOOP・記録なし・除去なし）に倒れる
4. `retry_outcome_terminality.py`のみ改修する（2.2節参照）
5. `RetryRuntimeOrchestrator.run_once()`に`dry_run: bool = False`引数を追加し、`manager.execute_dispatchable_retries(events, dry_run=dry_run)`へ伝播する

### 2.2 【最重要】`retry_outcome_terminality.py`の改修が必須である理由

コード調査の結果、採用案をそのまま実装すると**`run_once(dry_run=True)`がクラッシュする**ことをArchitecture Reviewで発見した。

`classify_reason()`（`retry_outcome_terminality.py`）は、`RetryQueueTerminalCleanupDecider`（`run_once()`の実行順序に組み込み済み）から呼ばれ、NOOP判定のうち`SKIPPED` / `NOT_FOUND` / `DISABLED`の3値だけを明示的にチェックし、**それ以外は`raise ValueError(...)`で例外を送出する**設計になっている（else方式ではなく、網羅チェック方式）。新しい`DRY_RUN`はNOOPに分類されるため、この関数を素通りして`ValueError`を送出し、`run_once()`全体を落とす。

対応として以下を追加した：

- `RetryCleanupReason`に`DRY_RUN`を追加
- `classify_reason()`に`DRY_RUN`の分岐を追加
- `RETRY_OUTCOME_TERMINALITY`に`DRY_RUN → TRANSIENT`を追加（判定理由：dry_runかどうかは呼び出し時の一時的な条件であり、同じrun_idを次回`dry_run=False`で呼べば結果が変わりうるため、TERMINALではなくTRANSIENT。TRANSIENT＝KEEPなので、Dry Run結果によってQueueの候補が誤って掃除されることもない）

**恒久ルール**：`RetryOutcome`へ新しい値を追加する場合は、リポジトリ全体で`RetryOutcome`の参照箇所を確認し、明示列挙・例外送出・永続化・表示・シリアライズへの影響をレビューすること。特に「明示列挙+raise」という網羅チェック方式（else方式ではない）の箇所は見逃すとクラッシュにつながる。

### 2.3 却下案

| 案 | 却下理由 |
|---|---|
| A. dry_run時は`WorkflowEngineManager.run()`自体を呼ばない | 呼ばないと「dry_runで何が起きたはずか」を示す`WorkflowEngineResult`が得られなくなり、可視化という価値を失う |
| B. 新しいOutcomeを追加せず既存の`SKIPPED`を流用する | `SKIPPED`は「RetryPolicyが対象外と判定した」という別の意味を既に持っており、混同を招く |
| C. Decider/Executor層に`dry_run`引数を追加して明示的に分岐させる | 判定根拠が「outcome種別」と「dry_runフラグ」の2箇所に分散し複雑化する。新しいOutcome1つの追加で済む方がCharter「一つの変更は一つの目的のために」に適う |
| D. `run_once(dry_run=...)`をRequest Object（`RunOnceOptions`等）にまとめる | `RetryManager.retry()` / `execute_dispatchable_retries()`等、retry_engine全体が「呼び出しの都度渡すbool引数」で統一されている。単一の振る舞い変更フラグのためにRequest Objectを導入するのはDevelopment Charter「抽象化は必要になってから行う」に反する（3.1節参照） |

---

## 3. ChatGPT（GPT-5.6 Sol）レビューと再評価

Architecture Review確定稿をChatGPT（GPT-5.6 Sol）へ提示したところ、以下4点の修正検討事項が提示された。Claude Codeが独立に検証し、採用可否を判断した。

### 3.1 修正検討事項①：`run_once(dry_run=...)`のRequest Object化 → **採用しない（現状案を維持）**

理由：
- 既存の慣習と矛盾する（`RetryManager.retry(dry_run=...)` / `execute_dispatchable_retries(dry_run=...)`等、既に「呼び出しの都度渡すbool引数」というスタイルで統一されている。`RetryEnqueueTrigger.enqueue_pending_failures(max_attempts=...)`のv5.0.0 Architecture Review Finalでも同様の判断が下されている）
- `dry_run`は「CLIの見た目」ではなく「実行の中身」を変える。`verbose`/`json`/`summary`のような表示層の関心事とは性質が異なり、`RetryExecutor`まで届く正当なOrchestration層の関心事である

**将来の基準**：行動を変えるフラグ（表示専用のverbose/json等ではなく）が2つ目以上出てきた時点で、Request Object化を再検討する。

### 3.2 修正検討事項②：CLI変更（argparse・`--dry-run`）を今回に含めるか → **採用する（分離する）**

このプロジェクトの過去履歴では、`run_once()`本体の追加（v5.3.0、Execution Release）と、それをCLIから呼べるようにする配線（v5.4.0、Entry Point Release）が毎回別Releaseに分けられている。今回だけ一体化すると一貫したパターンを崩すため、CLI配線は次Release「Retry Runtime Safe Dry Run Wiring」へ分離した（`docs/ROADMAP.md`参照）。

### 3.3 修正検討事項③：`RetryOutcome`判定箇所の総点検 → **採用する**

`src/retry_engine`内で`RetryOutcome`を参照している全箇所を確認した結果：

| ファイル | パターン | DRY_RUN追加時の安全性 |
|---|---|---|
| `retry_history_recorder.py` | allowlist方式（`in`判定） | ✅ 安全（自動的に対象外） |
| `retry_queue_cleanup_decider.py` | `if SKIPPED: ... else: KEEP` | ✅ 安全（else落ち） |
| `retry_queue_update_decider.py` | `if RETRIED: ... else: NOOP` | ✅ 安全（else落ち） |
| `retry_outcome_terminality.py` | 明示列挙 + `raise ValueError` | ❌ 危険（2.2節で対応済み） |

2.2節の恒久ルールとして設計書へ明記済み。

### 3.4 修正検討事項④：Enqueue側のdry_run非対応をROADMAP候補に格上げ → **採用する**

`RetryEnqueueTrigger.enqueue_pending_failures()`にdry_run引数を追加し、Queueへの書き込み自体を抑止できるようにする対応を、Known Issueだけでなく独立したReleaseテーマ「Retry Enqueue Trigger Dry Run Foundation」として`docs/ROADMAP.md`へ追加した。

---

## 4. 最終スコープ

### 対象

- `RetryOutcome.DRY_RUN`追加（`retry_result.py`）
- `RetryExecutor.execute()`のdry_run対応（`retry_executor.py`）
- `RetryRuntimeOrchestrator.run_once(dry_run: bool = False)`（`retry_runtime_orchestrator.py`）
- `execute_dispatchable_retries()`への伝播
- `RetryCleanupReason.DRY_RUN`追加・`classify_reason()`対応・`RETRY_OUTCOME_TERMINALITY`更新（`retry_outcome_terminality.py`）
- `RetryOutcome`参照箇所の総点検（3.3節）
- architecture.md / ROADMAP.md / CHANGELOG.md更新

### 対象外（Non-Goal、次Release候補として明記）

- CLI変更（`scripts/run_retry_runtime.py`への`argparse` / `--dry-run`配線）→ 次Release候補「Retry Runtime Safe Dry Run Wiring」
- `RetryEnqueueTrigger`側のdry_run対応（Enqueue自体の抑止）→ 次Release候補「Retry Enqueue Trigger Dry Run Foundation」
- `--loop`のCLI配線（Safe Dry Run Wiring完了後に着手要否を判断）
- Summary変更・Exit Code変更・Request Object化

---

## 5. テストで確認した内容

`tests/test_e2e_v5_6_0_retry_runtime_safe_dry_run_foundation.py`（49件、全PASS）で以下を確認した。

1. dry_run=Falseの既存動作が完全維持されること
2. dry_run=Trueで`RetryOutcome.DRY_RUN`が返ること
3. Workflow Engineへdry_run=Trueが伝播すること
4. Queue Update（`RetryQueueUpdateDecider`）が行われないこと（NOOP判定）
5. Queue Removalが行われないこと
6. History Recordが行われないこと
7. Queue Cleanup（v4.3.0、SKIPPED専用）がKEEPになること
8. Terminal Cleanupが例外を出さないこと（2.2節の核心）
9. Enqueueは現状どおり実行されること（対象外であることの実証）
10. 未知のRetryOutcomeは従来どおりfail-fastであること（`classify_reason()`のValueError維持）

既存回帰確認として、変更前後で全48件のE2Eテストを機械的に比較し、新規に発生した差分がすべて意図的なもの（`docs/CHANGELOG.md` `[KI-22]`）であり、それ以外の予期しない回帰がないことを確認した。

---

## 6. Known Issue（未解消）

- `[KI-22]`（`docs/CHANGELOG.md`）：本Releaseにより、v3.0.0〜v5.5.0の一部Architecture Guard（「無改修」を前提としたテスト）がFAILする。設計上の意図的な差分であり対応不要
- Enqueue側のdry_run非対応（4節、次Release候補「Retry Enqueue Trigger Dry Run Foundation」）
- CLI（`--dry-run`）未配線（4節、次Release候補「Retry Runtime Safe Dry Run Wiring」）
