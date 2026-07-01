# CHANGELOG

このファイルはプロジェクトの変更履歴を記録します。
フォーマットは [Keep a Changelog](https://keepachangelog.com/ja/) に準拠。

---

## Known Issues（現在判明している既知の問題）

> このセクションは「いつ・何がリリースされたか」というリリース履歴とは別に、
> **現時点（2026-07-01, v2.1.0 Documentation Foundation作業時点）で判明している未解決の問題**をまとめたものです。
> 各バージョンの`### Tested`欄はリリース当時の記録として維持し、現在の状況はここに集約します。

### [KI-1] v1.10.0 Analytics Foundation のE2Eテストが現環境で失敗する

- **発見日**：2026-07-01（v2.1.0 ドキュメント整備作業中）
- **対象**：`tests/test_e2e_v1_10_0_analytics_foundation.py`
- **症状**：`logs/analytics/` サブディレクトリが未作成のまま書き込もうとして `FileNotFoundError` が発生する（`src/analytics/`側の問題と推測される）
- **v1.10.0実装当時の状況**：`docs/design/analytics_foundation.md` の「Definition of Done」は全項目未チェック（`[ ]`）のままであり、実装当時に本当にテストがPASSしていたかを裏付ける記録は見つからなかった。実装当時の成否は不明。
- **対応状況**：未修正。`src/`はv2.1.0（本ドキュメント整備リリース）の変更対象外のため、コード修正は行っていない
- **今後の対応**：別リリースで`src/analytics/analytics_manager.py`側のディレクトリ作成漏れを調査・修正する想定

---

## [v2.2.0] - 2026-07-01 ★ News Agent Foundation

### Added

- `src/ai/news_agent_config.py`: `NewsAgentConfig`（`min_interval_minutes` / `timeout_sec` / `log_lookback_days` / `main_py_path` / `working_directory` / `python_executable`。`NEWS_AGENT_MIN_INTERVAL_MINUTES`等の環境変数から`from_env(project_root)`で構築）
- `src/ai/news_agent.py`: `NewsAgent`（`BaseAgent`継承）。`decide()`は`logs/execution/`配下の実行ログ（読み取り専用）から経過時間を判断し、`act()`は`NewsPipelineRunner.run()`のみを呼ぶ
- `src/pipeline/`（新規パッケージ、実行層）
  - `pipeline_result.py`: `PipelineResult`（`success` / `returncode` / `elapsed_sec` / `stdout_log_path` / `stderr_log_path` / `error_message`）
  - `news_pipeline_runner.py`: `NewsPipelineRunner`。`main.py`をsubprocessとして起動し、timeout・stdout/stderr保存・returncode判定を担う
- `scripts/run_news_agent.py` 新規作成（`--dry-run` / `--max-articles`対応の手動実行エントリ）
- `tests/test_e2e_v2_2_0_news_agent_foundation.py` 新規作成
- `docs/design/news_agent_foundation.md` 新規作成（本リリースで追加）

### Changed

- `src/ai/agent_manager.py`: `AgentManager.from_config()`の`executors`構築部分のみ更新。`AI_AGENT_ENABLED=true`の場合に`NewsAgentConfig` / `NewsPipelineRunner` / `NewsAgent`を生成し、`AgentExecutor(NewsAgent(...))`を`executors`に登録する（v2.0.0時点の`executors=[]`から初めて実体を持つ）
- `src/ai/__init__.py`: `NewsAgent` / `NewsAgentConfig`を新規export（既存のimport/exportは変更なし）

### Note

- Agent＝「判断」、PipelineRunner＝「実行」の責務分離を徹底。`NewsAgent`はsubprocessも`main.py`のパスも知らず、`NewsPipelineRunner.run(params) -> PipelineResult`という薄いインターフェースのみに依存する
- `NewsPipelineRunner`（`src/pipeline/`）はAgent層の型・`WorkflowRunner`を一切importしない（`ai → pipeline`の一方向依存）。将来のWorkflow Trigger Agent / Publish Agent / Scheduler Agentが同じ実行層の形を再利用できる想定
- `main.py`本体・既存ニュース収集パイプライン（`collector.py`等）・`WorkflowRunner`・`BaseAgent` / `AgentExecutor` / `AgentContext` / `AgentDecision` / `AgentResult`は無変更（`git diff`で確認済み）
- `dry_run=True`の場合、`AgentExecutor`（v2.0.0の既存設計）により`NewsAgent.act()`自体が呼ばれないため、`NewsPipelineRunner.run()`（＝`main.py`起動）は構造的に発生しない
- デフォルトは無効（`AI_AGENT_ENABLED=false`）。既存フローに影響なし

### Tested

- `tests/test_e2e_v2_2_0_news_agent_foundation.py`: 117/117 PASS
- 既存回帰確認：v1.9.0〜v1.20.0・v2.0.0の既存E2Eテスト13ファイル合計 1153/1153 PASS（`test_e2e_v1_10_0_analytics_foundation.py`はKnown Issues [KI-1]により対象外。本リリースの変更とは無関係であることを確認済み）

---

## [v2.0.0] - 2026-07-01 ★ AI Agent Foundation

### Added

- `src/ai/` に Agent基盤（8ファイル）を新規追加
  - `agent_task.py`: `AgentTask`（エージェントに判断を依頼する作業単位。`task_id` は自由記述）
  - `agent_decision.py`: `AgentDecision`（`should_act` / `reason` を持つ判断結果）
  - `agent_context.py`: `AgentContext`（実行時状態。`elapsed_time` は計算プロパティ）
  - `agent_result.py`: `AgentResult`（判断・実行結果。`workflow_result` は参照のみ保持しコピーしない）
  - `agent_config.py`: `AgentConfig`（`AI_AGENT_ENABLED` を読む。Configuration First）
  - `base_agent.py`: `BaseAgent`（ABC）。`decide()`（判断・副作用なし）と `act()`（実行）を分離
  - `agent_executor.py`: `AgentExecutor`。`decide()` → `should_act`かつ`dry_run=False`の場合のみ`act()`を呼ぶパイプライン
  - `agent_manager.py`: `AgentManager` / `NullAgentManager`（`AI_AGENT_ENABLED=false`時のダミー実装）
- `docs/design/agent_foundation.md` 新規作成（本リリースで追加、v2.1.0 Documentation Foundationにて作成）

### Note

- Agent は Workflow（`WorkflowRunner`）を置き換えるものではなく、「Workflowを今実行すべきか判断する」上位レイヤーとして設計されている
- v2.0.0時点では具体的な `BaseAgent` 実装は追加されていない。`AgentManager.from_config()` は `is_ready()=True` でも `executors=[]`（空リスト）を返す
- デフォルトは無効（`AI_AGENT_ENABLED=false`）。既存の `WorkflowRunner` 経由の自動実行フローに影響を与えない

### Tested

- `tests/test_e2e_v2_0_0_ai_agent_foundation.py`: 118/118 PASS

---

## [v1.20.0] - 2026-07-01 ★ AI Workflow Foundation

### Added

- `src/ai/` にWorkflow実行エンジン（7ファイル）を新規追加
  - `workflow_step.py`: `WorkflowStep` Enum（`improvement` / `improvement_review` / `rewrite` / `rewrite_review` / `publish` / `publish_review` の6ステップ）、`WorkflowStepResult`
  - `workflow_config.py`: `WorkflowConfig`（`AI_WORKFLOW_ENABLED` デフォルトtrue、`AI_WORKFLOW_CONTINUE_ON_ERROR`）
  - `workflow_context.py`: `WorkflowContext`
  - `workflow_step_executor.py`: 6ステップ分の `WorkflowStepExecutor` 実装（DIで各Serviceを注入）
  - `workflow_result.py`: `WorkflowResult`（`overall_success` / `total_processed` / `warnings` / `skipped_steps`）
  - `workflow_report_builder.py`: `WorkflowReportBuilder`
  - `workflow_runner.py`: `WorkflowRunner` / `NullWorkflowRunner`
- `scripts/run_ai_workflow.py` 新規作成
- `docs/design/ai_workflow_foundation.md` 新規作成（本リリースで追加）

### Note

- v1.14.0〜v1.19.0で個別に実装したImprovement→ImprovementReview→Rewrite→RewriteReview→Publish→PublishReviewの6ステップを、決まった順序で実行するオーケストレーターとして統合
- `WorkflowRunner` は各ステップのServiceを直接知らず、`WorkflowStepExecutor` 経由でDIする
- `AI_WORKFLOW_ENABLED=false` → `NullWorkflowRunner` を返す（Configuration First）

### Tested

- `tests/test_e2e_v1_20_0_ai_workflow_foundation.py`: 170/170 PASS

---

## [v1.19.0] - 2026-07-01 ★ AI Publish Review Foundation

### Added

- `src/ai/`: `ai_publish_review_result.py`（`PublishReviewStatus` Enum、`AiPublishReviewResult`）、`ai_publish_review_repository.py`、`ai_publish_review_report_builder.py`、`ai_publish_review_service.py`（`NullAiPublishReviewService`含む）
- `scripts/run_ai_publish_review.py` 新規作成

### Note

- Claude API・WordPress API（書き込み）は呼び出さない（読み取り・確認のみ、非破壊）
- 元記事・WordPress下書きの変更は行わない
- `NullAiPublishReviewService` は明示的な無効化時のみ使用（対象なしの場合は通常のServiceが「対象なし」レポートを生成する）
- 詳細設計書は見送り（v1.18.0 `ai_publish_foundation.md` の一部として今後扱う。必要度が上がった時点で個別設計書を追加）

### Tested

- `tests/test_e2e_v1_19_0_ai_publish_review_foundation.py`: 124/124 PASS

---

## [v1.18.0] - 2026-06-30 ★ AI Publish Foundation

### Added

- `src/ai/` にWordPress自動公開（6ファイル）を新規追加
  - `ai_publish_config.py`: `AiPublishConfig`（`AI_PUBLISH_ENABLED`、`WORDPRESS_URL`/`WORDPRESS_USERNAME`/`WORDPRESS_APP_PASSWORD`）
  - `ai_publish_result.py`: `AiPublishResult`（`wp_post_id` / `wp_edit_url` / `success` / `skipped` / `skip_reason`）
  - `wordpress_draft_client.py`: `WordPressDraftClient` / `NullWordPressDraftClient`
  - `ai_publish_repository.py`, `ai_publish_report_builder.py`, `ai_publish_service.py`（`NullAiPublishService`含む）
- `scripts/run_ai_publish.py` 新規作成
- `docs/design/ai_publish_foundation.md` 新規作成（本リリースで追加）

### Note

- v1.17.0で採用（adopted）されたリライト結果を重複チェックした上でWordPressへ投稿する
- 投稿は常に下書き（draft）のみ。publishは行わない（誤公開防止、v1.1.0以来の方針を踏襲）
- `AI_PUBLISH_ENABLED=false` または WordPress認証情報未設定 → `NullAiPublishService`

### Tested

- `tests/test_e2e_v1_18_0_ai_publish_foundation.py`: 109/109 PASS

---

## [v1.17.0] - 2026-06-30 ★ AI Rewrite Review Foundation

### Added

- `src/ai/`: `rewrite_review_result.py`（`ReviewStatus` Enum、`RewriteReviewResult`）、`rewrite_review_repository.py`、`rewrite_review_report_builder.py`、`rewrite_review_service.py`（`NullRewriteReviewService`含む）
- `scripts/run_ai_rewrite_review.py` 新規作成

### Note

- Claude APIを呼び出さない（リライト前後の差分サマリー生成のみ）
- `NullRewriteReviewService` は対象ファイルが存在しない・レビュー不要なケース用のno-op実装（Claude APIのON/OFFとは無関係）
- 詳細設計書は見送り（v1.16.0 `ai_rewrite_foundation.md` の一部として今後扱う）

### Tested

- `tests/test_e2e_v1_17_0_ai_rewrite_review_foundation.py`: 123/123 PASS

---

## [v1.16.0] - 2026-06-30 ★ AI Rewrite Foundation

### Added

- `src/ai/` にAIリライト機能（7ファイル）を新規追加
  - `rewrite_config.py`: `RewriteConfig`（`AI_REWRITE_ENABLED`、`AI_REWRITE_MODEL`、`AI_REWRITE_MAX_ARTICLES`等）
  - `rewrite_result.py`: `RewriteResult`（`rewrite_draft` / `improvement_summary` / `changes` / `success`）
  - `article_provider.py`: `ArticleProvider` / `WordPressArticleProvider` / `NullArticleProvider`
  - `rewrite_prompt_builder.py`, `rewrite_parser.py`, `rewrite_repository.py`, `rewrite_service.py`（`NullRewriteService`含む）
  - `prompts/v1_rewrite.py`
- `scripts/run_ai_rewrite.py` 新規作成
- `docs/design/ai_rewrite_foundation.md` 新規作成（本リリースで追加）

### Note

- v1.14.0の改善提案（`ImprovementSuggestion`）を受け取り、Claude APIで記事を実際に書き換える
- `AI_REWRITE_ENABLED=false` → `NullRewriteService`（Configuration First）
- 結果は `outputs/ai_rewrites/` にMarkdown＋JSONで保存（元記事は変更しない）

### Tested

- `tests/test_e2e_v1_16_0_ai_rewrite_foundation.py`: 81/81 PASS

---

## [v1.15.0] - 2026-06-30 ★ AI Improvement Review Foundation

### Added

- `src/ai/`: `improvement_report_builder.py`、`improvement_repository.py`、`improvement_review_service.py`
- `scripts/run_ai_improvement_report.py` 新規作成

### Note

- Claude APIを呼び出さない（`ImprovementRepository`が保存済みJSONを読み込み、Markdownレポート化するのみ）
- 詳細設計書は見送り（v1.14.0 `ai_improvement_foundation.md` の一部として今後扱う）

### Tested

- `tests/test_e2e_v1_15_0_ai_improvement_review_foundation.py`: 62/62 PASS

---

## [v1.14.0] - 2026-06-30 ★ AI Improvement Foundation

### Added

- `src/ai/` パッケージを新規作成（AI系機能全体の起点、8ファイル）
  - `claude_client.py`: `ClaudeClient` / `NullClaudeClient`
  - `ai_improvement_config.py`: `AiImprovementConfig`（`AI_IMPROVEMENT_ENABLED`、`AI_IMPROVEMENT_MODEL`、`AI_IMPROVEMENT_MAX_ARTICLES`等）
  - `improvement_suggestion.py`: `ImprovementSuggestion`（`priority` / `issues` / `suggestions` / `seo_title_suggestion`等）
  - `improvement_suggestion_parser.py`, `prompt_builder.py`, `ai_improvement_service.py`（`NullAiImprovementService`含む）
  - `prompts/v1_improvement.py`
- `scripts/run_ai_improvement.py` 新規作成（記事投稿フローとは独立したバッチ実行スクリプト）
- `docs/design/ai_improvement_foundation.md` 新規作成（本リリースで追加）

### Note

- v1.10.0で設計した `AiInputRecord`（Analytics Foundation）を入力とし、Claude APIで改善提案を生成する
- `main.py`（投稿処理）からは呼び出さない設計。SC/GA4データ取得後に別スクリプトとして実行する
- `AI_IMPROVEMENT_ENABLED=false`（デフォルト）→ `NullAiImprovementService`

### Tested

- `tests/test_e2e_v1_14_0_ai_improvement_foundation.py`: 74/74 PASS

---

## [v1.13.0] - 2026-06-30 ★ Google Analytics Foundation

### Added

- `src/analytics/`: `google_analytics_client.py`、`google_analytics_config.py`、`google_analytics_fetcher.py`
- `scripts/fetch_google_analytics_metrics.py` 新規作成
- `.env.example` に `GOOGLE_ANALYTICS_ENABLED` / `GA4_PROPERTY_ID` / `GA4_APPLICATION_CREDENTIALS` / `GA4_TIMEOUT_SECONDS` を追加

### Note

- GA4 APIエラーは `[GA4 WARNING]` プレフィックスで表示しゼロ値継続（Search Consoleの`[SC WARNING]`と区別）
- Google API への直接通信は `GoogleAnalyticsClient` の責務、変換・ゼロ値フォールバックは `GoogleAnalyticsFetcher` の責務に分離
- 詳細設計書は見送り（Search Console Foundationと同一パターンのため、必要になった時点で追加）

### Tested

- `tests/test_e2e_v1_13_0_google_analytics_foundation.py`: 70/70 PASS

---

## [v1.12.0] - 2026-06-30 ★ Search Console Foundation

### Added

- `src/analytics/`: `search_console_client.py`、`search_console_config.py`、`search_console_fetcher.py`
- `scripts/fetch_search_console_metrics.py` 新規作成
- `.env.example` に `SEARCH_CONSOLE_ENABLED` / `SEARCH_CONSOLE_PROPERTY` / `GOOGLE_APPLICATION_CREDENTIALS` / `SEARCH_CONSOLE_TIMEOUT` を追加
- `.gitignore` に `credentials/` を追加（Service Account鍵の除外）

### Note

- 投稿直後はSearch Consoleデータが存在しないため、`main.py`とは独立したバッチスクリプトとして設計
- 429（レート制限）・その他HTTPエラー・予期せぬ例外はすべてWARNING表示してゼロ値の`SearchConsoleMetrics`を返し、システム全体を停止させない
- 詳細設計書は見送り（必要になった時点で追加）

### Tested

- `tests/test_e2e_v1_12_0_search_console_foundation.py`: 47/47 PASS

---

## [v1.11.0] - 2026-06-30 ★ SaveResult Foundation

### Added

- `src/outputs/save_result.py` 新規作成（`SaveResult` dataclass）

### Changed

- `WordPressOutput.save()` / `MarkdownOutput.save()` の戻り値を文字列から `SaveResult` に変更
  - WordPress REST APIレスポンスの `"id"` フィールドから直接 `post_id` を取得する方式に変更（v1.8.0までの、`edit_url`文字列からの正規表現抽出という暫定実装を廃止）
- `OutputManager.save_all()` / `main.py` / `src/logger/log_manager.py` を `SaveResult` ベースの呼び出しに更新

### Note

- Single Source of Truthの原則：post_idはAPIレスポンスから直接取得し、他の文字列から推測しない
- 詳細設計書は見送り（内部データ構造の整理が中心のため）

### Tested

- `tests/test_e2e_v1_11_0_save_result.py`: 43/43 PASS

---

## [v1.10.0] - 2026-06-30 ★ Analytics Foundation

### Added

- `src/analytics/` パッケージ新規作成
  - `analytics_entry.py`: `AnalyticsEntry` / `ArticleAnalysisRecord` / `AiInputRecord` dataclass
  - `analytics_config.py`: `AnalyticsConfig`（`ANALYTICS_ENABLED`デフォルトfalse、`ANALYTICS_DIR`、`ANALYTICS_PERIOD_DAYS`）
  - `analytics_manager.py`: `AnalyticsManager`
- `docs/design/analytics_foundation.md` 新規作成（v1.10.0 設計書）
- `.env.example` に `ANALYTICS_ENABLED` / `ANALYTICS_DIR` / `ANALYTICS_PERIOD_DAYS` を追加

### Note

- v1.10.0時点では外部API連携（Search Console・Google Analytics）は行わない。将来のパフォーマンスデータ・AI改善提案の入力データ構造のみを設計
- Logging Foundation（`LOG_ENABLED`）と異なり、外部連携へ発展する基盤のため意図的にデフォルト無効（`ANALYTICS_ENABLED=false`）

### Tested

- `tests/test_e2e_v1_10_0_analytics_foundation.py` が実装時に追加されている。実装当時にPASSしていたことを裏付ける記録（設計書のチェック欄・実行ログ等）は見つからなかった
- 現在の環境で本テストを実行すると失敗する既知の問題がある。詳細は本ファイル冒頭の **Known Issues [KI-1]** を参照

---

## [v1.9.0] - 2026-06-30 ★ SNS Foundation

### Added

- `src/sns_config.py` 新規作成（`SnsConfig`：`BLOG_BASE_URL`解決、`SNS_ENABLED`、`SnsPostStatus` Enum）
- `docs/design/sns_foundation.md` 新規作成（v1.9.0 設計書）
- `.env.example` に `BLOG_BASE_URL` / `SNS_ENABLED` を追加

### Changed

- `src/logger/log_entry.py` / `log_manager.py`: SNS関連フィールド（`wp_public_url`、`x_post_status`）を追加
- `main.py`: X投稿文生成より先にslugを計算するよう処理順を変更（API呼び出し回数は変化なし）

### Note

- X API自動投稿は行わない。将来のX API連携・他SNS対応のための管理基盤のみを整備
- `BLOG_BASE_URL`未設定時は`WP_SITE_URL`にフォールバック、両方未設定なら`"[ブログURL]"`のプレースホルダーのまま

### Tested

- `tests/test_e2e_v1_9_0_sns_foundation.py`: 15/15 PASS

---

## [v1.8.0] - 2026-06-30 ★ Release 1.1 — Epic 2 Logging Foundation

### Added

- `src/logger/` パッケージ新規作成
  - `log_entry.py`: `ArticleLogEntry` / `ExecutionLogEntry` / `ErrorLogEntry` dataclass
  - `log_manager.py`: `LogManager` / `NullLogManager`
- `docs/design/logging_foundation.md` 新規作成（v1.8.0 設計書）
- `.env.example` に `LOG_ENABLED`（デフォルトtrue） / `LOG_DIR` を追加

### Changed

- `main.py`: 記事保存後・エラー発生時・全処理完了後にJSON Linesログを記録する処理を追加（`try/except`を新規追加）

### Note

- ログはJSON Lines形式で`logs/`配下に保存。`LOG_ENABLED=false`でv1.7.0以前と同じ動作（ログなし）
- 将来のCSVエクスポート・集計レポート・DB移行・AI改善提案の基盤として設計

### Tested

- 専用のE2Eテストファイルは作成されていない（設計書内の手動確認のみ。以降のバージョンから自動テストファイルが整備されている）

---

## [v1.7.0] - 2026-06-30  ★ Release 1.1 — Epic 1 Publishing Automation

### Added

- `src/publishing_config.py` 新規作成（Release 1.1 — Publishing Automation の中核モジュール）
  - `PublishStatus` Enum（`str` 継承）：`DRAFT` / `PENDING` / `FUTURE` / `PUBLISH` の4値
    - `FUTURE` / `PUBLISH` は将来実装用の予約定義
    - `str` 継承により `PublishStatus.DRAFT == "draft"` が True になり、ログ出力・JSON変換がそのまま使える
  - `PublishingConfig` dataclass：`status_s` / `status_a` フィールド
    - `from_env()`: `PUBLISH_STATUS_S` / `PUBLISH_STATUS_A` を環境変数から読み込む
    - `resolve_status(importance)`: 重要度 → `PublishStatus` を解決
    - Validation: 許可値外（`publish` / `future` / 任意の不正値）は `DRAFT` にフォールバック + WARNING出力
    - 将来拡張フィールドのコメント予約：`publish_time` / `timezone` / `review_required` / `priority`
- `docs/design/publishing_automation.md` 新規作成（v1.7.0 設計書）
- `ArticleData` に `publish_status: PublishStatus = PublishStatus.DRAFT` フィールドを追加（`base.py` 修正）

### Changed

- `src/outputs/wordpress_output.py`
  - `"status": "draft"`（ハードコード）を `"status": article.publish_status.value` に変更
  - コンソールログに `ステータス: <値>` を追加（投稿ID・slug・編集URLと並んで表示）
- `main.py`
  - `from publishing_config import PublishingConfig` をインポート追加
  - `publishing_config = PublishingConfig.from_env()` を起動時に1回呼び出す
  - 記事ループ内で `publish_status = publishing_config.resolve_status(importance)` を呼び出し `ArticleData` に設定
- `.env.example`
  - `PUBLISH_STATUS_S=draft` / `PUBLISH_STATUS_A=draft` を追加（使用可能な値・設定例付き）

### Note

- API呼び出し回数は増加なし（1記事あたり引き続き3回）
- 外部ライブラリ追加なし
- **Release 1.0 と完全後方互換**：`PUBLISH_STATUS_S/A` 未設定の場合は全記事 `draft` で動作（従来と同じ）

### Tested

- E2Eテスト①：`PUBLISH_STATUS_S=draft`（未設定・デフォルト）→ WordPress API で `status='draft'` 確認（post 10337）
- E2Eテスト②：`PUBLISH_STATUS_S=pending` → WordPress API で `status='pending'` 確認（post 10338）
- E2Eテスト③：`PUBLISH_STATUS_S=publish` / `PUBLISH_STATUS_A=abc`（不正値）→ WARNING 出力 + `status='draft'` でフォールバック確認（post 10339）

---

## [v1.6.0] - 2026-06-30

### Added

- `ArticleData` に `featured_media_id: int = 0` フィールドを追加（`base.py` 修正）
  - 0 の場合はアイキャッチなし（従来動作と同じ）
  - WordPress `featured_media` フィールドの値として使用
- `image_resolver.py` に `resolve_media_id(item, default_media_id)` 関数を追加
  - `image_terms_confirmed == False`（全RSS画像が未確認）の間は常に `default_media_id` を返す
  - 将来（v1.7.0）の権利確認済み画像アップロード対応のための拡張ポイント
- `main.py` に `DEFAULT_MEDIA_ID` の読み込みを追加（`os.getenv("DEFAULT_MEDIA_ID", "0")`）
  - `resolve_media_id(item, default_media_id)` を呼び出して `ArticleData.featured_media_id` に設定
- `.env.example` に `DEFAULT_MEDIA_ID` の設定例を追記（コメントアウト形式・設定方法の説明付き）
- `docs/blog_strategy.md` に画像利用ポリシーを追記（v1.6.0 確定版）
  - RSS画像・OGP画像のアップロード禁止ルールを明文化
  - デフォルト画像の WordPress 設定手順（Media ID 確認方法）

### Changed

- `wordpress_output.py` の payload に `featured_media` 条件付き追加
  - `article.featured_media_id > 0` の場合のみ `payload["featured_media"]` を設定
  - 0 の場合はキーごと省略（WordPress の既定値が優先される）

### Note

- API呼び出し回数は増加なし（1記事あたり引き続き3回）
- 外部ライブラリ追加なし
- `.env` の実ファイル変更不要（`DEFAULT_MEDIA_ID` 未設定の場合は 0 として動作）
- WordPress Media API（`/wp-json/wp/v2/media`）は使用しない（v1.7.0 以降の予定）

### Tested

- E2Eテスト成功（`python main.py --max-articles 1`、`DEFAULT_MEDIA_ID=0`）
  - featured_media が payload に含まれないことを確認（従来動作）
  - API呼び出し回数: 3回（変化なし）

---

## [v1.5.0] - 2026-06-30

### Added

- `slug_generator.py` 新規作成（`src/slug_generator.py`）
  - `generate_slug(seo_title: str, date_str: str) -> str`
  - ASCII英数字部分を抽出・小文字化・ケバブケース変換・最大30文字 + 日付付加
  - 英字が取れない場合は `article-YYYYMMDD` にフォールバック
  - 新規パッケージ追加なし・API呼び出しなし
- `ArticleData` に `slug: str = ""` フィールドを追加（`base.py` 修正）
- `main.py` で `generate_slug(seo_title, date_str)` を呼び出して `ArticleData.slug` を設定
- `main.py` に実行時間計測を追加（`time.time()` による計測、完了サマリーに `実行時間: XX.X秒` を表示）
- WordPress 投稿後の投稿 ID・slug・編集 URL をコンソールに表示（`wordpress_output.py` 修正）

### Changed

- `wordpress_output.py` の payload に `"slug": article.slug` を追加
- `markdown_output.py` の YAML front matter に `slug` フィールドを追記
- 完了サマリーの表示に実行時間を追加

### Note

- API呼び出し回数は増加なし（1記事あたり引き続き3回）
- 外部ライブラリ追加なし
- `.env` 変更不要

### Tested

- slug 生成の単体テスト（7ケース）：PS6/Switch混在・英字のみ・日本語のみ・記号のみ・長文・全英語
- E2Eテスト成功（`python main.py --max-articles 1`）

---

## [v1.4.0] - 2026-06-30

### Added

- `image_resolver.py` 新規作成（`src/image_resolver.py`）
  - `resolve_featured_image(item: NewsItem) -> str`：image_candidates の先頭URLを返す
  - 候補なしの場合は空文字を返す（例外を発生させない安全設計）
  - v1.5.0以降でデフォルト画像・権利確認済み画像・AI生成画像への拡張に対応可能
- `ArticleData` に `excerpt: str = ""` / `meta_description: str = ""` フィールドを追加（`base.py` 修正）
  - `excerpt`：WordPress抜粋・Markdown記録用
  - `meta_description`：将来のSEOプラグイン連携用（v1.4.0では excerpt と同値）
- `_extract_excerpt()` を `main.py` に追加
  - 記事本文の先頭段落からMarkdown記法（見出し・太字・斜体）を除去してルールベースで生成
  - 最大150字。句点（。）・読点（、）で自然に切れる位置を自動検出
  - APIを呼び出さない（API呼び出し回数は v1.3.0 と同じ1記事3回のまま）
- `WordPressOutput.save()` の payload に `"excerpt": article.excerpt` を追加
- `markdown_output.py` の YAML front matter に `excerpt` / `meta_description` を追記

### Changed

- `main.py` の `item.image_candidates[0] if item.image_candidates else ""` を `resolve_featured_image(item)` に差し替え（ImageResolver 経由に統一）

### Note

- API呼び出し回数は増加なし（1記事あたり引き続き3回）
- 著作権リスクは増加なし（画像のダウンロード・アップロードは行わない）
- `meta_description` は将来のSEOプラグイン（Rank Math等）連携の準備フィールド。v1.4.0では excerpt と同値を設定

### Tested

- E2Eテスト成功（`python main.py --max-articles 1`）
  - excerpt が Markdown YAML に記録されること
  - meta_description が excerpt と同値で記録されること
  - WordPress 下書きに excerpt フィールドが送信されること（post ID: 10331 で確認）
  - ImageResolver が candidates[0] を正しく返すこと
  - image_candidates が空でも空文字を返して正常終了すること

---

## [v1.3.0] - 2026-06-27

### Added

- `image_extractor.py` 新規作成（RSSエントリーから画像URLを抽出するモジュール）
  - `extract_image_url(entry) -> str`：media:thumbnail → enclosures → media:content の順に画像URLを探索
  - 取得できない場合は空文字を返す（例外を発生させない安全設計）
- `NewsItem.image_candidates` への画像URL格納（`collector.py` 修正）
- `ArticleData` に `featured_image_url: str = ""` フィールドを追加（`base.py` 修正）
- Markdownファイルの末尾に `<!-- アイキャッチ候補: URL -->` コメントを記録（`markdown_output.py` 修正）
- Markdownの `image_candidates` YAMLフィールドに実際の候補URLを出力

### Note

- 画像のWordPressアップロードは著作権リスクのため実装しない（v1.4.0 以降で検討）
- 取得した画像URLは候補として記録するのみ。利用前に著作権を確認すること

### Tested

- E2Eテスト成功（画像URLあり・なし両方のニュースで正常動作確認）

---

## [v1.2.0] - 2026-06-27

### Added

- `taxonomy_config.py` 新規作成（カテゴリ・タグIDの一元管理）
  - `GAME_NEWS_CATEGORY_ID`：「ゲームニュース」カテゴリIDの定数
  - `_TAG_ID_BY_IMPORTANCE`：重要度別タグIDの辞書（S→注目 / A→速報 / B→なし）
  - `resolve_taxonomy(importance)`：重要度からカテゴリID・タグIDを解決する関数
    - ID が 0（未設定）の場合は自動的にスキップ
- `WordPressOutput.save()` にカテゴリ・タグ設定を追加
  - `resolve_taxonomy()` を呼び出し、`categories` / `tags` をペイロードに追加
  - カテゴリ・タグが空リストの場合はペイロードから省略（WordPress標準に準拠）

### Tested

- カテゴリ・タグID設定済み環境でのE2Eテスト成功
  - RSS収集 → フィルター → 重複排除 → 重要度判定 → 記事生成 → Markdown保存 → WordPress下書き投稿（カテゴリ・タグ付き）の全工程を確認

---

## [v1.1.0] - 2026-06-26

### Added

- OutputManager アーキテクチャ導入（`src/outputs/` パッケージ新設）
  - `BaseOutput` 抽象クラス（`save()` / `is_available()` インターフェース）
  - `ArticleData` データクラス（記事生成結果をまとめて出力処理へ渡す）
  - `OutputManager.save_all()`: 全出力先に一括保存、1つ失敗しても他を続行
- `MarkdownOutput` クラス: v1.0 の `_save_as_markdown()` をクラスとして分離
- `WordPressOutput` クラス: WordPress REST API による下書き投稿対応
  - Application Password 認証
  - 投稿状態は `draft` 固定（誤公開防止）
  - `.env` 未設定時は `is_available()` が `False` を返し自動スキップ
  - エンドポイント: `/wp-json/wp/v2/posts`
- `.env.example` に WordPress設定項目を追加（`WP_SITE_URL` / `WP_USERNAME` / `WP_APP_PASSWORD`）

### Fixed

- `importance_judge.py` のプロンプト展開を `.format()` から `.replace()` に変更
  - `prompts/importance_prompt.md` のJSON例に含まれる `{}` を `str.format()` がプレースホルダーと誤認識する問題を修正

### Tested

- 実際のゲームニュース1件でE2Eテスト成功
  - RSS収集 → キーワードフィルター → 重複排除 → Claude重要度判定 → 記事生成 → Markdown保存 → WordPress下書き投稿の全工程を確認

---

## [v1.0] - 2026-06-26

### Added

- Steam News フィード追加（`https://store.steampowered.com/feeds/news/?l=japanese`）
  - 「公式」カテゴリに追加（PlayStation公式・Nintendo公式・Xbox公式・Steam）
  - 合計16サイトからのRSS収集に対応
- RSS取得サマリー表示（カテゴリ別の取得件数・成否を一覧表示）
  - `FeedStats` データクラスによる取得結果の構造化
  - `FEED_GROUPS` によるカテゴリ別グルーピング
  - 取得合計・フィルター通過・重複除去後・記事生成の件数を末尾に表示

---

## [v0.9] - 2026-06-26

### Added

- RSSニュース取得（15サイト対応）
  - 日本語：4Gamer、Game\*Spark
  - 公式：PlayStation公式、Nintendo公式、Xbox公式
  - 総合英語：IGN、GameSpot、Eurogamer、Gematsu、VGC、Insider Gaming、PC Gamer
  - プラットフォーム特化：Nintendo Life、Push Square、Pure Xbox
- キーワードフィルター（API節約のための事前スクリーニング）
- Claude APIによる重要度判定（S / A / B / なし）
- 日本語記事下書き生成
- SEOタイトル生成
- X（旧Twitter）投稿文生成
- Markdownファイル保存（output/ フォルダ）
- 重複ニュース排除（`duplicate_filter.py`、URLの正規化付き）

### Fixed

- JSON抽出処理を正規表現ベースに変更し、APIレスポンス形式の変化に対応
- Windows環境でのUTF-8文字コード問題を修正（起動時にstdout/stderrを設定）
