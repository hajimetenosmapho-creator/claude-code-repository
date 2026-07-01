# v1.20.0 AI Workflow Foundation 設計書

作成日：2026-07-01（v2.1.0 Documentation Foundationにて事後作成）

> 本設計書は実装（2026-07-01, commit `ef51309`）から遅れて作成されたものです。
> 内容はソースコードのDocstring・実装から再構成しています。

---

## 1. Goal

v1.14.0〜v1.19.0で個別に実装した6つのAI改善ステップ（Improvement / ImprovementReview / Rewrite / RewriteReview / Publish / PublishReview）を、
決まった順序で実行するオーケストレーター（`WorkflowRunner`）を作る。
これにより、6本の`scripts/run_*.py`を手動で順番に実行する必要がなくなる。

---

## 2. Background

### 現状の問題点

- v1.14.0〜v1.19.0の各機能は独立したスクリプトとして動作しており、ブロガーが6つのスクリプトを正しい順序で手動実行する必要があった。
- 途中のステップが失敗した場合の扱い（続行するか止めるか）が統一されていなかった。

### v1.20.0 が解決すること

- `WorkflowRunner.run()` を1回呼ぶだけで、6ステップを順番に実行し、全体の結果（`WorkflowResult`）とMarkdownレポートを生成する。
- 各ステップはDIされた`WorkflowStepExecutor`を介して呼び出すことで、`WorkflowRunner`自体は個々のServiceの実装を知らずに済む。

---

## 3. Scope

### 実装対象

- `WorkflowStep` Enum / `WorkflowStepResult`：ステップ定義と個別結果
- `WorkflowConfig`：設定値管理
- `WorkflowContext`：実行時状態
- `WorkflowStepExecutor`（ABC）とその6実装：各ステップのラッパー
- `WorkflowResult`：全体結果
- `WorkflowReportBuilder`：Markdownレポート生成
- `WorkflowRunner` / `NullWorkflowRunner`
- `scripts/run_ai_workflow.py`

### 対象外（Non Goalへ）

- 各ステップの実処理そのもの（v1.14.0〜v1.19.0で実装済み。本バージョンは統合のみ）
- 「Workflowをいつ実行すべきか」の自動判断（v2.0.0 Agent Foundationのスコープ）

---

## 4. Non Goal

- `WorkflowRunner`は各ステップのServiceを直接importしない。依存はすべて`from_config()`内でDIし、`WorkflowStepExecutor`経由で呼び出す。
- `main.py`（投稿処理）からは呼び出さない。投稿後の改善サイクルとして独立実行する（v1.14.0以来の方針を踏襲）。

---

## 5. User Workflow

### Before（v1.19.0）

```
python scripts/run_ai_improvement.py
python scripts/run_ai_improvement_report.py
python scripts/run_ai_rewrite.py
python scripts/run_ai_rewrite_review.py
python scripts/run_ai_publish.py
python scripts/run_ai_publish_review.py
```
6つのスクリプトを順番に、手動で実行する必要があった。

### After（v1.20.0）

```
python scripts/run_ai_workflow.py
```
1コマンドで6ステップすべてが順番に実行され、`outputs/workflow_reports/`に統合レポートが生成される。

---

## 6. System Workflow

```
WorkflowConfig.from_env()
  → WorkflowRunner.from_config(config)     6つのExecutorをDIして構築（is_ready()=Falseならダミー）
       → run(article_id=None, dry_run=False)
            → WorkflowContext 生成
            → 各 executor.execute(context) を順番に実行
                 IMPROVEMENT → IMPROVEMENT_REVIEW → REWRITE → REWRITE_REVIEW → PUBLISH → PUBLISH_REVIEW
            → 失敗時: continue_on_error=False（デフォルト）なら以降のステップを中断
            → WorkflowResult を生成
            → WorkflowReportBuilder.build() → outputs/workflow_reports/ へMarkdown保存
```

### dry_runモード

`run(dry_run=True)`の場合、各`WorkflowStepExecutor`は実処理を行わず`processed_count=0`の結果を返す（`_dry_run_result()`ヘルパー）。対象確認のみ行いたい場合に使う。

---

## 7. Data Model

### `WorkflowStep`（Enum、`workflow_step.py`）

`IMPROVEMENT` / `IMPROVEMENT_REVIEW` / `REWRITE` / `REWRITE_REVIEW` / `PUBLISH` / `PUBLISH_REVIEW` の6値。

### `WorkflowStepResult`

| フィールド | 型 | 内容 |
|---|---|---|
| `step` | `WorkflowStep` | 実行したステップ |
| `success` | `bool` | 成功したか |
| `processed_count` | `int` | 処理件数 |
| `report_path` | `Path \| None` | 個別レポートのパス |
| `error_message` | `str \| None` | 失敗理由 |
| `started_at` / `finished_at` | `datetime` | 実行時刻 |

### `WorkflowResult`

| フィールド | 内容 |
|---|---|
| `steps` | 各`WorkflowStepResult`のリスト |
| `overall_success` | 全ステップが成功したか（`all(r.success for r in steps)`） |
| `total_processed` | 全ステップの処理件数合計 |
| `report_path` | 統合Markdownレポートのパス |
| `warnings` / `skipped_steps` | 将来の拡張ポイント |

---

## 8. Directory Structure

```
src/ai/
├── workflow_step.py             # WorkflowStep Enum / WorkflowStepResult
├── workflow_config.py           # WorkflowConfig
├── workflow_context.py          # WorkflowContext
├── workflow_step_executor.py    # WorkflowStepExecutor（ABC）+ 6実装
├── workflow_result.py           # WorkflowResult
├── workflow_report_builder.py   # WorkflowReportBuilder
└── workflow_runner.py           # WorkflowRunner / NullWorkflowRunner

scripts/
└── run_ai_workflow.py

outputs/
└── workflow_reports/            # 統合Markdownレポート
```

---

## 9. Module Design

### `WorkflowConfig`（`workflow_config.py`）

| フィールド | デフォルト |
|---|---|
| `enabled` | `True`（`AI_WORKFLOW_ENABLED`。他のAI機能と異なりデフォルト有効） |
| `steps` | `ALL_WORKFLOW_STEPS`（6ステップ全部） |
| `continue_on_error` | `False`（`AI_WORKFLOW_CONTINUE_ON_ERROR`） |

`is_ready()`は`enabled and len(steps) > 0`。個々のステップ（Improvement等）が無効でも、`WorkflowRunner`自体は動作する（各Serviceが`NullXxxService`として動作するため）。

### `WorkflowStepExecutor`（ABC、`workflow_step_executor.py`）

- `step() -> WorkflowStep`：担当するステップを返す
- `execute(context) -> WorkflowStepResult`：ステップを実行する
- 6つの実装（`ImprovementStepExecutor`等）は、対応するService（`AiImprovementService`等）をコンストラクタで注入される（DI）
- `WorkflowRunner`はこれらExecutorのインターフェースのみに依存し、Service実装を直接知らない

### `WorkflowRunner` / `NullWorkflowRunner`（`workflow_runner.py`）

- `from_config()`が、6つのExecutorとその依存Service一式をDIする**唯一の場所**
- `run()`は`config.steps`に含まれるステップのみ実行し、含まれないステップは`skipped_steps`に記録する
- ステップ失敗時：`continue_on_error=False`（デフォルト）なら`break`で以降を中断。`True`なら全ステップ実行を試みる
- `NullWorkflowRunner`：`AI_WORKFLOW_ENABLED=false`時のダミー実装。`run()`は空の`WorkflowResult`を返す

---

## 10. Configuration Design

`.env.example` への追記は本バージョンでは未実施。

```
AI_WORKFLOW_ENABLED=true
AI_WORKFLOW_CONTINUE_ON_ERROR=false
```

### Configuration First の設計意図

他のAI機能（Improvement/Rewrite/Publish）はデフォルト`false`（明示的opt-in）だが、`WorkflowRunner`自体はデフォルト`true`。これは「Workflowという入れ物」自体は無害（中の各Serviceがデフォルト無効のためNull実装で動作する）という設計判断による。

---

## 11. 各Service（v1.14.0〜v1.19.0）との関係

`WorkflowRunner`は各Serviceの`from_env()` / `from_paths()`をそのまま呼び出してDIするのみで、Serviceの実装ロジックには一切関与しない。各Serviceが`NullXxxService`を返す条件（`ENABLED=false`等）は、そのまま`WorkflowRunner`経由の実行にも引き継がれる。

`ImprovementStepExecutor`のみ、`AnalyticsManager`（v1.10.0）にも依存し、`logs/`配下の記事ログとAnalyticsログを読み込んで`AiInputRecord`を組み立てる橋渡し役を担う。

---

## 12. Error Handling

| ケース | 対応 |
|---|---|
| 各ステップ内の例外 | 各Service側で処理済み（`success=False`の結果を返す設計のため、`WorkflowRunner`側で例外はcatchしない） |
| ステップ失敗 | `continue_on_error`の設定に応じて中断 or 続行 |
| レポート保存失敗（`OSError`） | `[WORKFLOW WARNING]`出力、`report_path=None`のまま`WorkflowResult`を返す |
| `AI_WORKFLOW_ENABLED=false` | `NullWorkflowRunner`が空の`WorkflowResult`を返す |

---

## 13. Agent Foundation との関係（v2.0.0への引き継ぎ）

`WorkflowRunner`は「決まった6ステップを実行する」実行エンジンであり、「いつ実行すべきか」は判断しない。
v2.0.0 `AgentManager`は、この`WorkflowRunner`を呼び出すかどうかを判断する上位レイヤーとして設計されている（`AgentResult.workflow_result`フィールドが`WorkflowResult`を参照する形で接続される想定）。

---

## 14. Future Extensions

- Phase 2：Agent層による実行判断（v2.0.0で骨組みを実装済み。具体的なAgent実装は未着手）
- Phase 3：Windowsタスクスケジューラによる定時実行（未着手）
- Phase 4：`warnings` / `skipped_steps`フィールドの実際の活用（v1.20.0時点では拡張ポイントとして予約のみ）

---

## 15. Definition of Done

### コード

- [x] `WorkflowRunner`とDI対象6 Executorの実装

### テスト

- [x] `tests/test_e2e_v1_20_0_ai_workflow_foundation.py`: 170/170 PASS

### ドキュメント

- [x] 本設計書（v2.1.0にて事後作成）
- [x] CHANGELOG.md / ROADMAP.md への記載
- [x] `docs/architecture.md`にWorkflow層として追記

### リリース

- [x] 2026-07-01 コミット済み（`ef51309`）
