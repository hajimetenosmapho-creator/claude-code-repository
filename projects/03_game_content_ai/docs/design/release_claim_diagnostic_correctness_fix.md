# Design Summary — release_claim() Diagnostic Correctness Fix（Release 6.37.0）

**分類**：Fast Track Release（`docs/development_workflow.md` 6〜7章）
**Architecture Contract Change**：NO
**位置づけ**：Release 6.35でMVP COMPLETEに到達した後の、Post-MVP 2件目のRelease（6.36に続く）。MVP Definition of Doneは変更・再オープンしない。

---

## 1. 背景・目的

Release 6.32 Final Review（Independent Code Review 2回目）で、Codex/Claude Codeの独立検証によりnon-blocking Suggestionとして記録された既知gapを解消する：

> `RetryExecutor.execute()`が`RetryLineageManager.release_claim()`のbool戻り値を確認していない。そのためrelease失敗時（durable store save失敗等）でも、`RetryResult.reason`が無条件に「claim released back to READY_ELIGIBLE」と返り、実durable state（CLAIMEDのまま）とずれうる。

本Suggestionは6.32 Final Reviewで「Release safety blockerではない、future improvementとして記録」とされ、6.33・6.34・6.35・6.36の各Releaseで独立したFast Track候補として保留され続けてきた（`docs/CHANGELOG.md`各該当節・`docs/architecture.md`該当節参照）。

durable state自体はfail-closedのまま維持され、CLAIMED orphanは既存`reconcile_all()`のCLAIMED orphan回収ロジックで安全に収束することを、既存targeted test（`tests/test_e2e_v6_32_35_admission_failure_durable_save_failure_closure.py`グループN）が事前に確認済みである。本Releaseは**durable safety改善ではなく、diagnostic correctness改善**として扱う。

---

## 2. Baseline

- branch: main
- HEAD = origin/main
- commit: `813ba378f794160ef3ef96988962c4d0d4fc3bf9`（Release 6.36.0完了時点）
- Working Tree: clean

---

## 3. In Scope

1. `RetryExecutor.execute()`の`hook_ack_state["acknowledged"] is False`経路で、`release_claim()`のbool戻り値を取得する
2. release成功/失敗を正確に`RetryResult.reason`へ反映する
3. `test_e2e_v6_32_35_admission_failure_durable_save_failure_closure.py`のN7(d)/N8(d)を意図transplantとしてTEST MIGRATION
4. success/failure coverageの確認、不足分のみ最小targeted test追加
5. Design Summary／CHANGELOG／ROADMAP／architecture.mdの整合更新
6. targeted validation
7. 関連Architecture Guard
8. Formal Regression全37ファイル
9. Codex `codex-readonly-review`によるCodex High独立レビュー

## 4. Out of Scope

- `release_claim()`本体・authority contract（4段階owner_token検証）の変更
- 例外再raise側call site（`RetryExecutor.execute()`のhook例外経路。対応する`reason`文言自体が存在しないため対象外）のロジック/ログ変更
- `reconcile_all()`の変更
- 自動修復・自動再claim・自動retry
- 新state／phase／retry policyの追加
- Queue/History persistence
- WordPress/Media idempotency
- Scheduler関連

---

## 5. Fast Track候補条件チェック結果（`docs/development_workflow.md` 7章）

実装着手前に確認した結果、8項目すべてを満たす。

| # | 条件 | 判定 | 根拠 |
|---|---|---|---|
| 1 | Public API変更なし | ✅ | `release_claim()`のシグネチャ・戻り値型は無変更。`RetryResult.reason: str \| None`のフィールド型も無変更（値の分岐のみ） |
| 2 | Constructor変更なし | ✅ | `RetryExecutor.__init__`・`RetryLineageManager.__init__`いずれも無変更 |
| 3 | Composition Root変更なし | ✅ | `src/retry_composition/`は無変更 |
| 4 | Layer変更なし | ✅ | 既存Executor層内部の分岐ロジックのみ |
| 5 | Dependency変更なし | ✅ | 新規import・pip追加なし |
| 6 | 永続化変更なし | ✅ | durable lineage state schema・JSON構造は無変更。`reason`は診断用の一時文字列であり永続化されない |
| 7 | Event変更なし | ✅ | `WorkflowEngineEvent`等のイベント型は無変更 |
| 8 | 外部I/O変更なし | ✅ | ネットワーク・外部サービス呼び出しの追加・変更なし |

最終分類の確定はChatGPT（設計担当AI）のArchitecture Review（簡易）を経て行う（`docs/development_workflow.md` 7章）。

---

## 6. 変更内容

### 6.1 Production

- `src/retry_engine/retry_executor.py`：`RetryExecutor.execute()`の`hook_ack_state["acknowledged"] is False`分岐（旧行251-269）で、`released = self._lineage.release_claim(...)`として戻り値を取得し、`RetryResult.reason`を以下のように分岐させる。
  - release成功時（`released is True`）：従来と同一の文言「...claim released back to READY_ELIGIBLE (Architecture Amendment, Blocking#1).」を維持（byte-identical、既存動作への影響なし）
  - release失敗時（`released is False`）：「...claim release failed (release_claim() returned False); durable phase may remain CLAIMED (Architecture Amendment, Blocking#1, Release 6.37.0 diagnostic correctness fix); orphan recovery deferred to reconcile_all().」という新文言を返す

例外再raise側call site（旧行242-249、hookが例外を送出した場合の`release_claim()`呼び出し）は変更しない。対応する`RetryResult`自体が構築されない経路（`raise`のみ）であり、reason文言の不整合が元々発生しないため。

### 6.2 Test（TEST MIGRATION・追加）

- `tests/test_e2e_v6_32_35_admission_failure_durable_save_failure_closure.py`
  - N7(d)：「無条件文言」を期待値とする記述 → 「release失敗時、reasonが解放失敗を示す文言（'claim release failed'）を含む」ことを検証する記述へ改訂（意図transplant）
  - N7b(d)（新規）：release失敗時、reasonがもはや旧無条件文言「claim released back to READY_ELIGIBLE」を含まないことを直接確認（診断gap解消の直接証拠）
  - N8(d)：durable phaseがCLAIMEDのまま、という検証意図自体は無変更（durable state契約は無変更のため）
  - M9b(d)（新規）：release成功時、reasonが実際の解放成功（phase=READY_ELIGIBLE）と整合することを直接確認（成功/失敗双方のreason正確性を対で証明）

---

## 7. 検証結果

- targeted test（`test_e2e_v6_32_35_admission_failure_durable_save_failure_closure.py`）：**31/31 PASS**（従来29件＋新規2件）
- 関連Architecture Guard（`tests/test_e2e_v6_3*.py`系列54ファイル一括実行）：**53/54 PASS**。唯一のFAILは`test_e2e_v6_33_0_retry_observability_runtime_integration_foundation.py`のテスト43（`src/retry_engine`に対する素の`git diff --quiet`、allow-list非参照のstandalone guard）。本Releaseがcommit前のため意図通りFAILする既知差分（`docs/CHANGELOG.md` `[KI-36]`参照、commit後に自然解消見込み）
- Formal Regression（正式Inventory37ファイル）：**36/37ファイルがexit code 0**。残る1ファイルは上記と同一原因
- Independent Codex `codex-readonly-review`（Codex High）：**APPROVED**（Blocking 0／Major 0／Minor 0／Suggestions 0）。`release_claim()`本体・authority check・`reconcile_all()`・例外再raise側call siteがいずれも無変更であること、新設のreason分岐ロジックにバグがないこと、migrated/追加テストが「見せかけの緑」ではなく意図通りの契約を検証していること、Fast Track候補条件8項目のいずれにも抵触しないことを確認済み（詳細はwrapper出力のEVIDENCE欄、`docs/CHANGELOG.md` `[v6.37.0]`参照）。

---

## 8. Known Issue

`docs/CHANGELOG.md` `[KI-36]`参照：`test_e2e_v6_33_0`テスト43が、本Release承認済み変更（`src/retry_engine/retry_executor.py`）のuncommitted状態にのみ起因してFAILする。commit自体が解消条件であり、`[KI-33]`・`[KI-35]`と同じ「commit解消」パターン。

---

## 9. commit/push

Human Gate待ち。本Design Summary作成・実装・検証まで完了しているが、commit/pushは実施していない。
