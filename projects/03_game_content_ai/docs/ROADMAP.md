# ROADMAP

---

## v1.1.0 — WordPress下書き投稿対応（2026-06-26 完了）

- [x] OutputManager アーキテクチャ導入（`src/outputs/` パッケージ）
- [x] MarkdownOutput クラス分離
- [x] WordPressOutput 実装（WordPress REST API / Application Password認証）
- [x] WordPress下書き投稿のE2Eテスト成功
- [x] importance_prompt.md の `{}` 問題を修正

---

## v1.2.0 — カテゴリ・タグ自動設定（2026-06-27 完了）

- [x] `taxonomy_config.py` 新規作成（カテゴリ・タグIDの一元管理）
- [x] `resolve_taxonomy()` 実装（重要度 → カテゴリID・タグIDを解決）
- [x] `WordPressOutput.save()` にカテゴリ・タグ設定を追加
- [x] E2Eテスト成功（カテゴリ・タグ付き下書き投稿の全工程確認）

---

## v1.3.0 — アイキャッチ画像URL抽出・記録（2026-06-27 完了）

- [x] `image_extractor.py` 新規作成（RSSエントリーから画像URL抽出）
- [x] `collector.py` に `extract_image_url()` 呼び出しを追加（`NewsItem.image_candidates` に格納）
- [x] `ArticleData` に `featured_image_url` フィールドを追加（デフォルト空文字）
- [x] `markdown_output.py` にアイキャッチ候補URLをコメントとして記録
- [x] E2Eテスト成功（画像あり・なし両方で正常動作確認）

---

## v1.4.0 — SEO Foundation（2026-06-30 完了）

- [x] `src/image_resolver.py` 新規作成（画像候補選択責務を main.py から分離）
  - `resolve_featured_image(item: NewsItem) -> str`：v1.4.0は candidates[0] を返す
  - v1.5.0以降でデフォルト画像・権利確認済み画像・AI生成画像への拡張に対応
- [x] `ArticleData` に `excerpt` / `meta_description` フィールドを追加（`base.py` 修正）
- [x] `_extract_excerpt()` を `main.py` に追加（ルールベース・API追加なし）
  - 記事本文の先頭段落からMarkdown記法を除去して最大150字で抽出
  - 句点・読点で自然に切れる位置を自動検出
- [x] `WordPressOutput.save()` の payload に `"excerpt"` を追加
- [x] `markdown_output.py` の YAML front matter に `excerpt` / `meta_description` を追記
- [x] E2Eテスト成功（excerpt生成・WordPress excerpt設定・Markdown記録の全工程確認）

---

## v1.5.0 — Publishing Enhancement（2026-06-30 完了）

- [x] `src/slug_generator.py` 新規作成（`generate_slug(seo_title, date_str) -> str`）
  - ASCII英数字を抽出・小文字化・ケバブケース変換・最大30文字 + 日付で一意性保証
  - 英字が取れない場合は `article-YYYYMMDD` にフォールバック
- [x] `ArticleData` に `slug: str = ""` フィールドを追加（後方互換性維持）
- [x] `main.py` で slug を生成し `ArticleData` に渡す（API追加なし）
- [x] `markdown_output.py` の YAML front matter に `slug` を追記
- [x] `wordpress_output.py` の payload に `"slug"` を追加
- [x] WordPress 投稿後の投稿 ID・slug・編集URL をログに表示
- [x] 実行時間を完了サマリーに表示（`実行時間: XX.X秒`）
- [x] E2Eテスト成功

---

## v1.6.0 — Image Pipeline（2026-06-30 完了）

- [x] `ArticleData` に `featured_media_id: int = 0` フィールドを追加（`base.py` 修正）
- [x] `image_resolver.py` に `resolve_media_id(item, default_media_id) -> int` を追加
  - `image_terms_confirmed == False` の間は常に `default_media_id` を返す
  - 将来（v1.7.0）の権利確認済み画像アップロードに対応した拡張ポイント設計
- [x] `main.py` で `DEFAULT_MEDIA_ID` を `os.getenv()` から取得し `resolve_media_id()` へ渡す
- [x] `wordpress_output.py` に `featured_media` 設定を追加
  - `featured_media_id > 0` の場合のみ payload に `"featured_media"` キーを追加
  - `featured_media_id == 0` の場合は従来どおりアイキャッチなしで投稿
- [x] `.env.example` に `DEFAULT_MEDIA_ID` を追記（コメントアウトで設定方法を説明）
- [x] `docs/blog_strategy.md` に画像利用ポリシーを追記
  - RSS画像・OGP画像のアップロード禁止ルールを明文化
  - デフォルト画像の設定手順（WordPress管理画面でのID確認方法）
- [x] E2Eテスト成功（DEFAULT_MEDIA_ID=0 で従来動作確認）

---

## v1.7.0 — Publishing Automation Foundation（2026-06-30 完了）★ Release 1.1 開始

- [x] `src/publishing_config.py` 新規作成
  - `PublishStatus` Enum（DRAFT / PENDING / FUTURE / PUBLISH）
  - `PublishingConfig` dataclass（`from_env()` / `resolve_status()`）
  - Validation：許可値外は WARNING + DRAFT フォールバック
  - 将来拡張フィールドのコメント予約（`publish_time` / `timezone` / `review_required` / `priority`）
- [x] `docs/design/publishing_automation.md` 新規作成（v1.7.0 設計書）
- [x] `ArticleData.publish_status: PublishStatus = DRAFT` 追加（`base.py` 修正）
- [x] `wordpress_output.py` の `"status": "draft"` ハードコードを `article.publish_status.value` に変更
- [x] コンソールログに `ステータス:` 表示を追加
- [x] `.env.example` に `PUBLISH_STATUS_S` / `PUBLISH_STATUS_A` 追加
- [x] E2Eテスト成功（draft / pending / 不正値フォールバック の3パターン）
- [x] Release 1.0 完全後方互換確認

---

## v1.8.0 — Logging Foundation（2026-06-30 完了）★ Release 1.1 — Epic 2

- [x] 実行ログのファイル出力（`src/logger/log_manager.py`、JSON Lines形式）
- [x] エラーログの構造化（`ErrorLogEntry`）
- [x] 投稿履歴の記録（`ArticleLogEntry`）
- [x] 投稿処理（`ExecutionLogEntry`）の記録
- [ ] AI判定履歴の記録（未着手。v1.14.0以降のAI系ログとの統合を検討）
- [ ] API利用履歴の記録（未着手）
- [x] `docs/design/logging_foundation.md` 設計書作成

---

## v1.9.0 — SNS Foundation（2026-06-30 完了）★ Release 1.1 — Epic 3

- [x] X投稿URLの保存（`wp_public_url`をログに記録）
- [x] 投稿履歴の管理（`ArticleLogEntry`にSNS関連フィールドを追加）
- [x] 将来のAPI連携設計（`SnsPostStatus` Enumで拡張ポイントを用意。X API自動投稿は未実装）
- [x] `docs/design/sns_foundation.md` 設計書作成

---

## v1.10.0 — Analytics Foundation（2026-06-30 完了）★ Release 1.1 — Epic 4

- [x] Analyticsデータモデル設計（`AnalyticsEntry` / `ArticleAnalysisRecord` / `AiInputRecord`）
- [ ] Search Console 連携（→ v1.12.0で実装）
- [ ] Google Analytics 連携（→ v1.13.0で実装）
- [ ] AI改善提案（→ v1.14.0で実装）
- [x] `docs/design/analytics_foundation.md` 設計書作成

---

## v1.11.0 — SaveResult Foundation（2026-06-30 完了）

- [x] `SaveResult` dataclass新規作成（`src/outputs/save_result.py`）
- [x] `WordPressOutput.save()` の戻り値をAPIレスポンス直接参照方式に変更（post_id推測の廃止）
- [ ] 詳細設計書（見送り。必要になった時点で追加）

---

## v1.12.0 — Search Console Foundation（2026-06-30 完了）★ Release 1.1 — Epic 4 続き

- [x] `SearchConsoleClient` / `SearchConsoleFetcher` 実装
- [x] `scripts/fetch_search_console_metrics.py`（バッチ取得スクリプト）
- [x] APIエラー時のWARNING継続処理（システム全体を停止させない）
- [ ] 詳細設計書（見送り。必要になった時点で追加）

---

## v1.13.0 — Google Analytics Foundation（2026-06-30 完了）★ Release 1.1 — Epic 4 続き

- [x] `GoogleAnalyticsClient` / `GoogleAnalyticsFetcher` 実装
- [x] `scripts/fetch_google_analytics_metrics.py`
- [x] `[GA4 WARNING]`によるSearch Consoleとの区別
- [ ] 詳細設計書（見送り。必要になった時点で追加）

---

## v1.14.0 — AI Improvement Foundation（2026-06-30 完了）★ Release 1.2 — Epic 1

- [x] `src/ai/` パッケージ新規作成（AI系機能全体の起点）
- [x] `ClaudeClient` / `AiImprovementService` 実装（Configuration First）
- [x] `scripts/run_ai_improvement.py`（投稿フローと独立したバッチ実行）
- [x] `docs/design/ai_improvement_foundation.md` 設計書作成（v2.1.0にて追加）

---

## v1.15.0 — AI Improvement Review Foundation（2026-06-30 完了）★ Release 1.2 — Epic 2

- [x] `ImprovementReviewService`（Claude API呼び出しなしのレポート生成）
- [x] `scripts/run_ai_improvement_report.py`
- [ ] 詳細設計書（見送り。v1.14.0設計書の範囲として今後扱う）

---

## v1.16.0 — AI Rewrite Foundation（2026-06-30 完了）★ Release 1.2 — Epic 3

- [x] `RewriteService` 実装（改善提案を元にClaude APIで記事をリライト）
- [x] `ArticleProvider`（WordPress記事取得）
- [x] `scripts/run_ai_rewrite.py`
- [x] `docs/design/ai_rewrite_foundation.md` 設計書作成（v2.1.0にて追加）

---

## v1.17.0 — AI Rewrite Review Foundation（2026-06-30 完了）★ Release 1.2 — Epic 4

- [x] `RewriteReviewService`（差分サマリー生成、Claude API呼び出しなし）
- [x] `scripts/run_ai_rewrite_review.py`
- [ ] 詳細設計書（見送り。v1.16.0設計書の範囲として今後扱う）

---

## v1.18.0 — AI Publish Foundation（2026-06-30 完了）★ Release 1.2 — Epic 5

- [x] `AiPublishService`（採用済みレビューの重複チェック→WordPress下書き投稿）
- [x] `WordPressDraftClient`
- [x] `scripts/run_ai_publish.py`
- [x] `docs/design/ai_publish_foundation.md` 設計書作成（v2.1.0にて追加）

---

## v1.19.0 — AI Publish Review Foundation（2026-06-30 完了）★ Release 1.2 — Epic 6

- [x] `AiPublishReviewService`（非破壊・読み取りのみのレビュー）
- [x] `scripts/run_ai_publish_review.py`
- [ ] 詳細設計書（見送り。v1.18.0設計書の範囲として今後扱う）

---

## v1.20.0 — AI Workflow Foundation（2026-07-01 完了）★ Release 1.2 完了

- [x] `WorkflowRunner`：Improvement→ImprovementReview→Rewrite→RewriteReview→Publish→PublishReviewの6ステップを統合
- [x] `WorkflowStepExecutor`（DIによる各Service注入）
- [x] `scripts/run_ai_workflow.py`
- [x] `docs/design/ai_workflow_foundation.md` 設計書作成（v2.1.0にて追加）

---

## v2.0.0 — AI Agent Foundation（2026-07-01 完了）★ Release 2.0 開始

- [x] `AgentManager` / `AgentExecutor` / `BaseAgent` 実装（「Workflowを今実行すべきか判断する」上位レイヤーの骨組み）
- [x] Configuration First（`AI_AGENT_ENABLED=false`がデフォルト。既存フローに影響なし）
- [ ] 具体的なAgent実装（News Agent等）は未着手。v2.0.0時点では`executors=[]`
- [x] `docs/design/agent_foundation.md` 設計書作成（v2.1.0にて追加）

---

## v2.1.0 — Agent Documentation Foundation（2026-07-01 完了）

- [x] CHANGELOG.md / ROADMAP.md をv1.8.0〜v2.0.0まで最新化
- [x] architecture.md にWorkflow層・Agent層を追記
- [x] `docs/design/`に5本の設計書を追加（AI Improvement / AI Rewrite / AI Publish / AI Workflow / Agent Foundation）
- [ ] 見送った6バージョン（SaveResult / Search Console / Google Analytics / AI Improvement Review / AI Rewrite Review / AI Publish Review）の詳細設計書は、必要になった時点で追加する

---

## v2.2.0 — News Agent Foundation（2026-07-01 完了）★ Release 2.0 続き

- [x] `NewsAgentConfig`新規実装（判断・実行の設定値管理。`main_py_path` / `working_directory` / `python_executable`を含む）
- [x] `src/pipeline/`（実行層）新規実装：`PipelineResult` / `NewsPipelineRunner`
- [x] `NewsAgent`（`BaseAgent`継承）実装：`decide()`は実行ログベースの判断、`act()`は`NewsPipelineRunner.run()`への委譲のみ
- [x] `AgentManager.from_config()`に`NewsAgent`をDI（v2.0.0の`executors=[]`から初めて実体化）
- [x] `scripts/run_news_agent.py`新規作成（`--dry-run` / `--max-articles`対応）
- [x] `docs/design/news_agent_foundation.md`設計書作成
- [x] Agent＝判断／PipelineRunner＝実行の責務分離を徹底（`main.py`・`WorkflowRunner`は無変更）
- [x] E2Eテスト117/117 PASS、既存回帰1153/1153 PASS（v1.10.0 Known Issue除く）

---

## v2.3.0 — Workflow Trigger Agent Foundation（2026-07-02 完了）★ Release 2.0 続き

- [x] `WorkflowTriggerAgentConfig`新規実装（二重ゲート方式の判断・実行双方の設定値管理。`WORKFLOW_TRIGGER_AGENT_ENABLED`（デフォルト`false`）と既存`AI_WORKFLOW_ENABLED`の両方を`is_ready()`に反映）
- [x] `src/pipeline/workflow_pipeline_runner.py`（実行層）新規実装：`WorkflowPipelineRunner`（`WorkflowRunner.run()`を直接呼び出す薄いラッパー、subprocess不使用）
- [x] `WorkflowTriggerAgent`（`BaseAgent`継承）実装：`decide()`は`outputs/workflow_reports/`のmtimeベースの判断、`act()`は`WorkflowPipelineRunner.run()`への委譲のみ
- [x] `AgentManager.from_config()`に`WorkflowTriggerAgent`をDI（二重ゲート方式：`AI_AGENT_ENABLED` かつ `WORKFLOW_TRIGGER_AGENT_ENABLED` かつ `AI_WORKFLOW_ENABLED`の3条件がすべて揃った場合のみ有効化）
- [x] `scripts/run_workflow_trigger_agent.py`新規作成（`--dry-run` / `--article-id` / `--workflow-dry-run`対応）
- [x] `docs/design/workflow_trigger_agent_foundation.md`設計書作成
- [x] Agent＝判断／PipelineRunner＝実行／WorkflowRunner＝オーケストレーションの3層責務分離を徹底（`WorkflowRunner`・`NewsAgent`・`NewsPipelineRunner`・`main.py`は無変更）
- [x] E2Eテスト110/110 PASS、既存回帰（`v2.0.0` 118/118・`v2.2.0` 120/120・`v1.20.0` 170/170）PASS

---

## v2.4.0 — Publish Trigger Agent Foundation（2026-07-02 完了）★ Release 2.0 続き

- [x] `PublishTriggerAgentConfig`新規実装（三重ゲート方式の判断・実行双方の設定値管理。`PUBLISH_TRIGGER_AGENT_ENABLED`（デフォルト`false`）と既存`AiPublishConfig.is_ready()`（`AI_PUBLISH_ENABLED`＋WordPress認証情報3点）の両方を`is_ready()`に反映）
- [x] `src/pipeline/publish_pipeline_runner.py`（実行層）新規実装：`PublishPipelineRunner`（`AiPublishService.run()`を直接呼び出す薄いラッパー、subprocess不使用）
- [x] `PublishTriggerAgent`（`BaseAgent`継承）実装：`decide()`は`outputs/ai_publish_reports/`のmtimeベースの判断、`act()`は`PublishPipelineRunner.run()`への委譲のみ
- [x] `AgentManager.from_config()`に`PublishTriggerAgent`をDI（三重ゲート方式：`AI_AGENT_ENABLED` かつ `PUBLISH_TRIGGER_AGENT_ENABLED` かつ `AiPublishConfig.is_ready()`の3条件がすべて揃った場合のみ有効化）
- [x] `scripts/run_publish_trigger_agent.py`新規作成（`--dry-run` / `--article-id`対応）
- [x] `docs/design/publish_trigger_agent_foundation.md`設計書作成（実装完了後の事後整備として2026-07-02追加）
- [x] Agent＝判断／PipelineRunner＝実行／AiPublishService＝WordPress下書き投稿処理の3層責務分離を徹底（`AiPublishService`・`NewsAgent`・`WorkflowTriggerAgent`は無変更）
- [x] E2Eテスト120/120 PASS、既存回帰（`v2.0.0` 118/118・`v2.2.0` 120/120・`v2.3.0` 110/110・`v1.20.0` 170/170）PASS
- [x] `docs/architecture.md`への追記（Agent → Pipeline → Runnerパターンの表への追加）：2026-07-02、v2.5.0ドキュメント整備時にあわせて追記
- [ ] `.env.example`への環境変数追記は未着手（v1.14.0以降の複数バージョンにまたがる既存負債。別タスクで対応予定）

---

## v2.5.0 — Review Trigger Agent Foundation（2026-07-02 完了）★ Release 2.0 続き

- [x] Project Charter作成：`docs/design/review_trigger_agent_charter.md`（対象Serviceを`AiPublishReviewService`（v1.19.0）のみに限定）
- [x] Architecture Design確定：`docs/design/review_trigger_agent_foundation.md`（Gate方式・decide()方式・min_interval_minutesの3点を確定）
- [x] `ReviewTriggerAgentConfig`新規実装（二重ゲート方式の判断・実行双方の設定値管理。`REVIEW_TRIGGER_AGENT_ENABLED`（デフォルト`false`）のみで`is_ready()`を判定。`AiPublishReviewService`に`Config`/`is_ready()`が存在しないため、`WorkflowTriggerAgent` / `PublishTriggerAgent`のような三重ゲートへは寄せない）
- [x] `src/pipeline/review_pipeline_runner.py`（実行層）新規実装：`ReviewPipelineRunner`（`AiPublishReviewService.run()`を直接呼び出す薄いラッパー、subprocess不使用）
- [x] `ReviewTriggerAgent`（`BaseAgent`継承）実装：`decide()`は`outputs/ai_publish_review_reports/`のmtimeベースの判断（既存3Agentと同じ時間間隔方式。未レビュー件数・入力/出力差分検知はFuture Extensionsに記録し今回は見送り）、`act()`は`ReviewPipelineRunner.run()`への委譲のみ
- [x] `AgentManager.from_config()`に`ReviewTriggerAgent`をDI（二重ゲート方式：`AI_AGENT_ENABLED` かつ `REVIEW_TRIGGER_AGENT_ENABLED`の2条件がすべて揃った場合のみ有効化）
- [x] `scripts/run_review_trigger_agent.py`新規作成（`--dry-run` / `--article-id`対応）
- [x] Agent＝判断／PipelineRunner＝実行／AiPublishReviewService＝公開前レビューレポート生成処理の3層責務分離を徹底（`AiPublishReviewService`・`NewsAgent`・`WorkflowTriggerAgent`・`PublishTriggerAgent`は無変更）
- [x] E2Eテスト118/118 PASS、既存回帰（`v2.0.0` 118/118・`v2.2.0` 120/120・`v2.3.0` 110/110・`v2.4.0` 120/120・`v1.20.0` 170/170）PASS
- [x] `docs/architecture.md`への追記：2026-07-02（v2.4.0分とあわせて追記）

---

## v2.6.0 — Scheduler Agent Foundation（2026-07-02 完了）★ Release 2.0 続き

> 本エントリはcommit `0d28d30`時点でROADMAP.mdへの記載が漏れていたため、v2.7.0ドキュメント整備作業（2026-07-02）で実装済みコードを確認のうえ遡及的に追記したものです（`docs/CHANGELOG.md` [KI-2]参照）。

- [x] `src/scheduler/`新規パッケージ実装：`SchedulerJob` / `TriggerType`（DAILY/INTERVAL/ONCE） / `SchedulerEvent` / `SchedulerRepository`（ABC）/ `InMemorySchedulerRepository` / `SchedulerManager` / `SchedulerEngine`（`evaluate()` / `run_due()`） / `SchedulerConfig`
- [x] Event Driven Architecture：Schedulerは判定のみ行い`SchedulerEvent`を生成する。既存Trigger Agentの起動は一切行わない（`src/ai/` / `src/pipeline/`を一切importしない独立パッケージ）
- [x] `tests/test_e2e_v2_6_0_scheduler_agent_foundation.py`新規作成（118件）
- [ ] `SchedulerEvent`を受け取ってAgentを起動する呼び出し元（→ v2.7.0で実装）
- [ ] Project Charter / Architecture Design設計書（見送り。既知のドキュメント負債としてv2.7.0のドキュメント整備時に記録）
- [ ] Windows タスクスケジューラ / Linux cron連携、永続化、retry、last_run_at保持（いずれも対象外、将来Release候補）

---

## v2.7.0 — Workflow Engine Foundation（2026-07-02 完了）★ Release 2.0 続き

- [x] Project Charter作成：`docs/design/workflow_engine_foundation_charter.md`
- [x] Architecture Design確定：`docs/design/workflow_engine_foundation.md`（Architecture Review完了・修正必須事項3点反映済み）
- [x] `src/workflow_engine/`新規パッケージ実装：`WorkflowEngineStep` / `WorkflowEngineDefinition` / `WorkflowEngineEvent` / `WorkflowEngineContext` / `WorkflowEngineStepResult` / `WorkflowEngineResult` / `WorkflowEngineConfig` / `WorkflowEngineExecutor` / `WorkflowEngineManager`
- [x] Scheduler（v2.6.0）→ Workflow Engine → NewsAgent → ReviewTriggerAgent → PublishTriggerAgentの直列実行基盤を確立（既存4 Trigger Agent・`AgentManager` / `AgentExecutor`・Scheduler本体はいずれも無改修）
- [x] Gate二層構造（Workflow Engine全体の二重ゲート × ステップ別の既存Config再利用）、打ち切り基準（実行失敗のみ打ち切り、Gate閉鎖/decide()スキップは継続）を確立
- [x] `scripts/run_workflow_engine.py`新規作成（`--dry-run` / `--job-id`対応。固定・最小限のデモJob1件のみ）
- [x] `tests/test_e2e_v2_7_0_workflow_engine_foundation.py`新規作成（163件、`FakeAgent`によるExecutor単体テスト含む）
- [x] E2Eテスト163/163 PASS、既存回帰（`v2.0.0` 118/118・`v2.2.0` 120/120・`v2.3.0` 110/110・`v2.4.0` 120/120・`v2.5.0` 118/118・`v2.6.0` 118/118・`v1.20.0` 170/170）PASS
- [ ] 複数実行主体の排他制御（ロック機構）：運用制約として明記のみ、実装は対象外（→ 将来Release候補）
- [ ] SchedulerJobの永続化・複数Job登録・設定ファイル化：対象外（→ 将来Release候補）
- [ ] `WorkflowTriggerAgent`（AI改善6ステップ）の統合：`PublishTriggerAgent`との役割重複整理後に再検討

---

## v2.8.0 — Execution History Foundation（2026-07-02 完了）★ Release 2.0 続き

- [x] Project Charter作成：`docs/design/execution_history_foundation_charter.md`
- [x] Architecture Design確定：`docs/design/execution_history_foundation.md`
- [x] `src/execution_history/`新規パッケージ実装：`ExecutionHistoryConfig` / `ExecutionHistoryEvent` / `StepExecutionRecord` / `StepExecutionStatus` / `WorkflowExecutionRecord` / `WorkflowExecutionStatus` / `ExecutionHistoryStore` / `JsonExecutionHistoryStore` / `ExecutionHistoryManager` / `NullExecutionHistoryManager`
- [x] Workflow Engine（v2.7.0）が実行したWorkflowの開始・終了・各Stepの結果を観測して記録する基盤を確立（実行判断・分岐・再試行判断には一切関与しない、記録専用）
- [x] `workflow_engine` → `execution_history`の一方向依存を維持。既存Workflow Engineの実行制御ロジックは無変更（`WorkflowEngineExecutor` / `WorkflowEngineManager`へのDI追加のみ）
- [x] `scripts/show_execution_history.py`新規作成（読み取り専用CLI、`--run-id` / `--limit`対応）
- [x] `tests/test_e2e_v2_8_0_execution_history_foundation.py`新規作成（182件）
- [x] E2Eテスト182/182 PASS、既存回帰（`v2.0.0` 118/118・`v2.2.0` 120/120・`v2.3.0` 110/110・`v2.4.0` 120/120・`v2.5.0` 118/118・`v2.6.0` 118/118・`v2.7.0` 163/163・`v1.20.0` 170/170）PASS
- [ ] Retry Engine・Workflow Monitor・Metrics Foundation・Dashboard Foundation：対象外（→ Workflow Monitorはv2.9.0で実装。Retry Engine・Metrics・Dashboardは引き続き将来Release候補）
- [ ] JSON保存からDB永続化への差し替え：対象外（`ExecutionHistoryStore`インターフェースにより将来差し替え可能な設計のみ用意）

---

## v2.9.0 — Workflow Monitor Foundation（2026-07-02 完了）★ Release 2.0 続き

- [x] Project Charter作成：`docs/design/workflow_monitor_foundation_charter.md`
- [x] Architecture Design確定：`docs/design/workflow_monitor_foundation.md`（Architecture Review完了・指摘事項3点反映済み）
- [x] `src/workflow_monitor/`新規パッケージ実装：`WorkflowMonitorStatus` / `WorkflowMonitorConfig` / `WorkflowMonitorRecord` / `WorkflowMonitor` / `WorkflowMonitorManager` / `NullWorkflowMonitorManager`
- [x] Execution History（v2.8.0）が記録した`WorkflowExecutionRecord`を唯一の情報源（Single Source of Truth）として、Workflowの実行状態を判定するだけの基盤を確立
- [x] `RUNNING` / `SUCCESS` / `FAILED` / `TIMEOUT`の4状態判定に対応。`CANCELLED` / `WAITING`はEnumに定義するが、判定対象となる元データが存在しないため将来拡張用の予約値とする
- [x] Workflow Engine（v2.7.0）・Execution History（v2.8.0）はいずれも無改修。`workflow_monitor` → `execution_history`の一方向依存のみ
- [x] `scripts/show_workflow_status.py`新規作成（読み取り専用CLI。`--run-id` / `--limit`対応。ゲートをバイパスして常に判定結果を表示）
- [x] `tests/test_e2e_v2_9_0_workflow_monitor_foundation.py`新規作成（103件）
- [x] E2Eテスト103/103 PASS、既存回帰（`v2.0.0` 118/118・`v2.2.0` 120/120・`v2.3.0` 110/110・`v2.4.0` 120/120・`v2.5.0` 118/118・`v2.6.0` 118/118・`v2.7.0` 163/163・`v2.8.0` 182/182・`v1.20.0` 170/170）PASS
- [x] Retry Engine・Metrics Foundation・Dashboard Foundationの前提基盤として位置づけ（いずれも本Releaseの対象外）
- [ ] `CANCELLED`の正式な判定方法・`WAITING`の導入タイミング：対象外（→ 将来Release候補）

---

## v3.0.0 — Retry Engine Foundation（2026-07-02 完了）★ Release 2.0 続き

- [x] Project Charter作成：`docs/design/retry_engine_foundation_charter.md`
- [x] Architecture Design確定：`docs/design/retry_engine_foundation.md`（Architecture Review完了・指摘事項4点反映済み）
- [x] `src/retry_engine/`新規パッケージ実装：`RetryPolicy` / `RetryConfig` / `RetryRequest` / `RetryResult` / `RetryOutcome` / `RetryExecutor` / `RetryManager` / `NullRetryManager`
- [x] Workflow Monitor（v2.9.0）が`FAILED` / `TIMEOUT`と判定したWorkflowを、Workflow Engine（v2.7.0）の公開API（`WorkflowEngineManager.run()`）を通じて再実行する基盤を確立
- [x] Retry可否判定・RetryPolicy適用・RetryRequest生成はRetryManagerが担当し、RetryExecutorはWorkflowEngineManagerの公開APIを呼び出すだけの薄いコンポーネントとする設計に整理（Architecture Review反映）
- [x] Workflowの状態は保持しない（Stateless）。`WorkflowMonitorManager`の公開API（`get_status()`）を毎回呼び出して最新状態を取得する（Read Before Retry）。Execution Historyは直接参照・解釈しない
- [x] Workflow Engine（v2.7.0）・Workflow Monitor（v2.9.0）・Execution History（v2.8.0）はいずれも無改修。`retry_engine` → `workflow_engine` / `workflow_monitor`の2パッケージのみへの依存
- [x] 追加調整：`RetryManager.retry(run_id, attempt=1, dry_run=False)`。`dry_run=True`でdry-run retryが可能（既存呼び出しの後方互換性は維持。`RetryExecutor` / `RetryRequest`の責務・データ構造は無変更）
- [x] `tests/test_e2e_v3_0_0_retry_engine_foundation.py`新規作成（130件、`dry_run`引数追加分5件を含む）
- [x] E2Eテスト130/130 PASS、既存回帰（`v2.0.0` 118/118・`v2.2.0` 120/120・`v2.3.0` 110/110・`v2.4.0` 120/120・`v2.5.0` 118/118・`v2.6.0` 118/118・`v2.7.0` 163/163・`v2.8.0` 182/182・`v2.9.0` 103/103・`v1.20.0` 170/170）PASS
- [ ] Retry Queue・Retry History・RetryDecision・RetryReason Enum・Exponential Backoff・Adaptive Retry・Metrics・Dashboard・Notification・Circuit Breaker・AI Retry Decision・Parallel/Distributed Retry・Manual Retry UI・CLIエントリスクリプト：対象外（→ 将来Release候補）

---

## v3.1.0 — Retry Queue Foundation（2026-07-02 完了）★ Release 2.0 続き

- [x] Architecture Design確定：`docs/design/retry_queue_foundation.md`（Project Charterはチャット上で提示された内容が前提。別ファイル化は本Releaseでは未実施）
- [x] `src/retry_queue/`新規パッケージ実装：`RetryQueueStatus` / `RetryQueueItem` / `RetryQueueOutcome` / `RetryQueueResult` / `RetryQueueConfig` / `RetryQueueManager` / `NullRetryQueueManager`
- [x] `enqueue` / `dequeue` / `remove` / `list` / `exists` / `count` の6操作を実装。Queue管理のみを責務とし、Retry実行・Workflow Engine呼び出し・Retry Engine呼び出し・Workflow Monitor呼び出し・Execution History呼び出しはいずれも行わない
- [x] `retry_queue`はWorkflow Engine・Workflow Monitor・Retry Engine・Execution Historyのいずれもimportしない、標準ライブラリのみに依存する独立した葉パッケージとして実装（Retry Engine v3.0.0よりもさらに徹底した独立性）
- [x] `RETRY_QUEUE_ENABLED`のデフォルトは`true`（Queue操作はメモリ上の`dict`を読み書きするだけで外部副作用を伴わないため、Execution History/Workflow Monitorと同じ「安全に既定で有効にできる」分類とした）
- [x] `COMPLETED` / `FAILED`は将来拡張用の予約値として定義（`WorkflowMonitorStatus.CANCELLED` / `WAITING`の前例を踏襲。本Releaseの操作からは到達しない）
- [x] `tests/test_e2e_v3_1_0_retry_queue_foundation.py`新規作成（152件）
- [x] E2Eテスト152/152 PASS、既存回帰（`v2.0.0` 118/118・`v2.2.0` 120/120・`v2.3.0` 110/110・`v2.4.0` 120/120・`v2.5.0` 118/118・`v2.6.0` 118/118・`v2.7.0` 163/163・`v2.8.0` 182/182・`v2.9.0` 103/103・`v3.0.0` 130/130・`v1.20.0` 170/170）PASS。`v1.10.0`は`[KI-1]`（既知の問題、本Releaseと無関係）によりFAIL
- [x] Retry Engineとの実配線：v3.2.0で実装済み（下記参照）
- [ ] Scheduler連携・Queue永続化（SQLite/Redis）・`COMPLETED`/`FAILED`への到達（結果フィードバックAPI）・Priority Queueの効率化（heapqベース）・Dead Letter Queue・Notification・Dashboard/API/UI：対象外（→ 将来Release候補）

---

## v3.2.0 — Retry Queue Integration（2026-07-02 完了）★ Release 2.0 続き

- [x] Project Charter作成：`docs/design/retry_queue_integration_charter.md`（承認済み）
- [x] Architecture Design確定：`docs/design/retry_queue_integration.md`（Architecture Review完了・Approve with Minor Recommendations、指摘事項3点をテスト観点へ反映済み）
- [x] `src/retry_engine/retry_manager.py`変更：`RetryManager`が`RetryQueueManager` / `NullRetryQueueManager`をDependency Injectionで保持できるようにし、`enqueue_retry()` / `dequeue_retry()`を追加（いずれも`RetryQueueManager`への薄い委譲のみ。判定・加工は行わない）
- [x] `RetryManager.from_config()`に`retry_queue_manager`引数（デフォルト`None`）を追加。省略時は`NullRetryQueueManager()`にフォールバックし、既存の4引数呼び出しは無変更で動作する（後方互換性維持）
- [x] `NullRetryManager`にも同名2メソッドを追加。Queueへの参照は一切保持せず、常に自前で`outcome=DISABLED`を返す
- [x] `retry()`（Retry実行）と`enqueue_retry()` / `dequeue_retry()`（Queue操作）は呼び出しグラフ上で完全に独立。Queueから取り出した項目を自動的に`retry()`する仕組み（自動実行）は実装しない
- [x] `src/retry_queue/`は本Releaseでも無改修。`retry_engine → retry_queue`の一方向依存を新規に追加（既存の`retry_engine → workflow_engine` / `workflow_monitor`はそのまま）
- [x] `tests/test_e2e_v3_2_0_retry_queue_integration.py`新規作成（102件）
- [x] E2Eテスト102/102 PASS、既存回帰（`v2.0.0` 118/118・`v2.2.0` 120/120・`v2.3.0` 110/110・`v2.4.0` 120/120・`v2.5.0` 118/118・`v2.6.0` 118/118・`v2.7.0` 163/163・`v2.8.0` 182/182・`v2.9.0` 103/103・`v3.0.0` 130/130・`v1.20.0` 170/170）PASS。`v3.1.0`は151/152 PASS（1件は既知の差分、`docs/CHANGELOG.md` [KI-3]参照）
- [ ] Queueから取り出した項目の自動再実行・Scheduler連携（定期的な`dequeue()`処理）・Queue永続化・優先度付けアルゴリズムの高度化・CLIエントリスクリプト：対象外（→ 将来Release候補）

---

## v3.3.0 — Retry Scheduler Integration（2026-07-03 完了）★ Release 2.0 続き

- [x] Project Charter作成：`docs/design/retry_scheduler_integration_charter.md`（承認済み）
- [x] Architecture Design確定：`docs/design/retry_scheduler_integration.md`（Architecture Review完了・Approve with Minor Recommendations、指摘事項3点を反映済み）
- [x] `src/retry_scheduler_source/`新規パッケージ実装：`RetrySchedulerSource`（`RetryQueueManager`をConstructor Injectionで保持し、`list_pending_retries(limit)` / `count_pending_retries()`への薄い委譲のみを行うAdapter）、`NullRetrySchedulerSource`（`retry_queue`への参照を一切保持しないダミー実装）
- [x] Feature Gate・Configクラス・Managerパターン（`from_config()` / `from_env()`等の起動口）はいずれも追加しない。プロジェクト全体で一貫しているNull Object Pattern（継承なしのDuck Typingペア）を踏襲し、有効/無効は呼び出し元がどちらのクラスを構築するかで決まる
- [x] Constructor Injectionのみを採用（`RetrySchedulerSource.__init__`は`RetryQueueManager`実体のみを受け取る）
- [x] `list()` / `count()`（非破壊の読み取り専用API）のみを使用。`dequeue()` / `remove()`は一切呼び出さない
- [x] `src/scheduler/` / `src/retry_queue/` / `src/retry_engine/`は本Releaseでも無改修。新規の依存方向は`retry_scheduler_source → retry_queue`の一方向のみ
- [x] 本Releaseでは`RetrySchedulerSource` / `NullRetrySchedulerSource`をどこからも呼び出さない（`v2.9.0`のWorkflowMonitorManager・`v3.1.0`のRetryQueueと同じ「消費者不在の先行実装」パターン）
- [x] `tests/test_e2e_v3_3_0_retry_scheduler_integration.py`新規作成（72件）
- [x] E2Eテスト72/72 PASS、既存回帰（`v2.0.0` 118/118・`v2.2.0` 120/120・`v2.3.0` 110/110・`v2.4.0` 120/120・`v2.5.0` 118/118・`v2.6.0` 118/118・`v2.7.0` 163/163・`v2.8.0` 182/182・`v2.9.0` 103/103・`v3.0.0` 130/130・`v3.1.0` 152/152・`v3.2.0` 102/102）PASS
- [ ] Scheduler本体（`SchedulerEngine.evaluate()` / `run_due()`）との実配線・Queueから取り出した項目の自動再実行（自動Retry実行）・`dequeue()` / `remove()`の使用：対象外（→ 将来Release候補。次の節参照）

---

## v3.4.0 — Retry Scheduler Wiring（2026-07-03 完了）★ Release 2.0 続き

- [x] Project Charter作成：`docs/design/retry_scheduler_wiring_charter.md`（承認済み）
- [x] Architecture Design確定：`docs/design/retry_scheduler_wiring.md`（Architecture Review完了・Approve with Minor Recommendations、指摘事項3点を記録）
- [x] `src/scheduler/scheduler_engine.py`変更：`SchedulerEngine`が`RetrySchedulerSource` / `NullRetrySchedulerSource`（v3.3.0）をConstructor Injectionで保持できるようにし、`count_pending_retries()` / `list_pending_retries()`を追加（いずれも`RetrySchedulerSource`への薄い委譲のみ。判定・加工は行わない）
- [x] `SchedulerEngine.__init__`に`retry_source`引数（デフォルト`None`）を追加。省略時は`NullRetrySchedulerSource()`にフォールバックし、既存の`SchedulerEngine()` / `SchedulerEngine(clock=...)`呼び出しは無変更で動作する（後方互換性維持）
- [x] `evaluate()` / `run_due()` / `_match*()`はいずれも無変更。判定サイクルとpending retryの参照は完全に独立したメソッドとして共存する
- [x] `SchedulerEngine`は`RetryQueueManager`を直接保持しない。Retry Queueへは`RetrySchedulerSource`経由でのみ間接的に到達する（v3.3.0のAdapter境界を維持）
- [x] `SchedulerManager`・新規Wrapperクラスは追加しない。Constructor Injectionの受け口は`SchedulerEngine`に一本化
- [x] 新規Feature Gate・Configクラス・Managerパターンはいずれも追加しない。`src/scheduler/`は本Releaseでも新規ファイル追加なし（`scheduler_engine.py` / `__init__.py`の変更のみ）
- [x] `src/retry_scheduler_source/` / `src/retry_queue/` / `src/retry_engine/`は本Releaseでも無改修
- [x] `tests/test_e2e_v3_4_0_retry_scheduler_wiring.py`新規作成（94件）
- [x] E2Eテスト94/94 PASS、既存回帰（`v2.0.0` 118/118・`v2.2.0` 120/120・`v2.3.0` 110/110・`v2.4.0` 120/120・`v2.5.0` 118/118・`v2.6.0` 118/118・`v1.20.0` 170/170）PASS。`v2.7.0`〜`v3.3.0`は`docs/CHANGELOG.md` `[KI-4]`（本Releaseによる意図的な変更）を参照
- [ ] 実運用のComposition Root（例：`scripts/run_scheduler.py`）・pending retryの参照結果を使った判断・自動Retry実行・`dequeue()` / `remove()`の使用：対象外（→ 将来Release候補。次の節参照）

---

## v3.5.0 — Retry Scheduler Decision（2026-07-03 完了）★ Release 2.0 続き

- [x] Project Charter作成：`docs/design/retry_scheduler_decision_charter.md`（承認済み）
- [x] Architecture Design確定：`docs/design/retry_scheduler_decision.md`（Architecture Review完了・Approve with Minor Recommendations、指摘事項3点を記録）
- [x] `src/retry_scheduler_decision/`新規パッケージ実装：`RetrySchedulerDecision`（`RetrySchedulerSource | NullRetrySchedulerSource`をConstructor Injectionで**必須引数として**保持し、`select_candidates(limit)` / `select_next_candidate()`への薄い委譲のみを行う）
- [x] `RetrySchedulerSource.list_pending_retries()`の既存順序（priority昇順・enqueue_time昇順）をそのまま活用し、独自の並べ替え・優先度計算は一切行わない
- [x] `retry_source`はデフォルト値を持たない必須引数とする（`SchedulerEngine.__init__`とは異なり、本コンポーネントにとって唯一の実質的な入力であるため。`RetrySchedulerSource.__init__(queue)`と同じ判断）
- [x] Null Object Pattern（`NullRetrySchedulerDecision`）は採用しない。プロジェクト全体で一貫している設計言語からの意図的な逸脱であり、本コンポーネントには対応するFeature Gate/Config軸が存在せず、「無効化」は`retry_source`に`NullRetrySchedulerSource()`を渡すことで既に完結しているため
- [x] `SchedulerEngine`（`src/scheduler/`配下の全ファイル）・`retry_scheduler_source` / `retry_queue` / `retry_engine`はいずれも本Releaseでも無改修。新規の依存方向は`retry_scheduler_decision → retry_scheduler_source`の一方向のみ
- [x] 本Releaseでは`RetrySchedulerDecision`をどこからも呼び出さない（`v3.3.0`のRetrySchedulerSourceと同じ「消費者不在の先行実装」パターン）
- [x] `tests/test_e2e_v3_5_0_retry_scheduler_decision.py`新規作成（72件）
- [x] E2Eテスト72/72 PASS、既存回帰（`v2.0.0` 118/118・`v2.2.0` 120/120・`v2.3.0` 110/110・`v2.4.0` 120/120・`v2.5.0` 118/118・`v2.6.0` 118/118・`v2.7.0` 163/163・`v2.8.0` 182/182・`v2.9.0` 103/103・`v3.0.0` 130/130・`v3.1.0` 152/152・`v3.2.0` 102/102・`v3.4.0` 94/94・`v1.20.0` 170/170）PASS。`v3.3.0`は71/72 PASSで、1件FAILは`docs/CHANGELOG.md` `[KI-4]`の延長（新規Known Issueなし）
- [ ] `SchedulerEngine`との実配線・選択結果を使った実行（自動Retry実行）・`RetryQueueManager.dequeue()` / `remove()`の使用：対象外（→ 将来Release候補。次の節参照）

---

## v3.6.0 — Retry Scheduler Decision Wiring（2026-07-03 完了）★ Release 2.0 続き

- [x] Project Charter作成：`docs/design/retry_scheduler_decision_wiring_charter.md`（承認済み）
- [x] Architecture Design確定：`docs/design/retry_scheduler_decision_wiring.md`（Architecture Review完了・Approve with Minor Recommendations、指摘事項2点を記録）
- [x] `src/scheduler/scheduler_engine.py`変更：`SchedulerEngine`が`RetrySchedulerDecision`（v3.5.0）をConstructor Injectionで保持できるようにし、`select_candidates(limit=None)` / `select_next_candidate()`を追加（いずれも`RetrySchedulerDecision`への薄い委譲のみ。判定・加工は行わない）
- [x] `SchedulerEngine`は`RetrySchedulerDecision`を自ら生成しない（呼び出し元が組み立てて渡す。ユーザー承認済みの設計方針）
- [x] `retry_decision`はデフォルト`None`のオプション引数とし、`None`の場合は`select_candidates()` / `select_next_candidate()`内のガード節で`[]` / `None`を直接返す（`RetrySchedulerDecision`に対になるNull実装が存在しないため、v3.4.0の`retry_source`とは異なるフォールバック方式を採用）
- [x] `evaluate()` / `run_due()` / `_match*()`はいずれも無変更。判定サイクルと候補選択の参照は完全に独立したメソッドとして共存する
- [x] 新規Feature Gate・Configクラス・Managerパターンはいずれも追加しない。`src/scheduler/`は本Releaseでも新規ファイル追加なし（`scheduler_engine.py` / `__init__.py`の変更のみ）
- [x] `src/retry_scheduler_decision/` / `src/retry_scheduler_source/` / `src/retry_queue/` / `src/retry_engine/`は本Releaseでも無改修
- [x] `tests/test_e2e_v3_6_0_retry_scheduler_decision_wiring.py`新規作成（104件）
- [x] E2Eテスト104/104 PASS、既存回帰（`v2.0.0` 118/118・`v2.6.0` 118/118・`v3.4.0` 94/94・`v1.20.0` 170/170）PASS。`v2.7.0`〜`v3.3.0`・`v3.5.0`は`docs/CHANGELOG.md` `[KI-4]`（本Releaseによる意図的な変更）を参照。`v2.2.0`〜`v2.5.0`・`v2.7.0`〜`v2.9.0`の一部は本Releaseと無関係な既存問題（`docs/CHANGELOG.md` `[KI-5]`、新規追加）
- [ ] `evaluate()` / `run_due()`への候補選択結果の組み込み（`SchedulerEvent`生成への反映）・選択結果を使った実行（自動Retry実行）・`RetryQueueManager.dequeue()` / `remove()`の使用：対象外（→ 将来Release候補。次の節参照）

---

## v3.7.0 — Retry Scheduler Event Integration（2026-07-03 完了）★ Release 2.0 続き

- [x] Project Charter作成：`docs/design/retry_scheduler_event_integration_charter.md`（承認済み）
- [x] Architecture Design確定：`docs/design/retry_scheduler_event_integration.md`（Architecture Review完了・Approve with Minor Recommendations、指摘事項2点を記録。ユーザー承認時のMinor Recommendation追記1件を含む）
- [x] `src/scheduler/scheduler_engine.py`変更：`evaluate()` / `run_due()`が、`RetrySchedulerDecision`の選択結果（`select_candidates()`、v3.6.0）をRetry候補由来の`SchedulerEvent`として出力に含められるようになった（Additive方式。既存のJob判定ループ（`_match*()`系）は1行も変更せず、新設の`_build_retry_events(now, retry_limit)`が返すリストを`events.extend(...)`で追加連結するのみ）
- [x] `retry_decision`が`None`の場合、`evaluate()` / `run_due()`はv3.6.0時点と完全に同一の結果を返す（後方互換性維持。`_build_retry_events()`が`select_candidates()`のv3.6.0ガード節へ委譲するのみで、新たな分岐を追加していないため）
- [x] Retry候補由来の`SchedulerEvent`の`job_id`は`"retry:" + run_id`とする（`RetryQueueItem`に`job_id`相当のフィールドが存在しない問題への対処。`scheduler`は`retry_queue`を直接importせず、`run_id`という1属性への構造的な期待（Duck Typing）のみに依存する）
- [x] `metadata`は候補オブジェクトを分解せず`{"retry_candidate": 候補オブジェクト}`としてそのまま格納する。`metadata["retry_candidate"]`は本Release（v3.7.0）ではin-memoryの観測用途に限定し、永続化・JSON serialization・外部I/O契約とはしない（ユーザー承認時のMinor Recommendation）
- [x] Retry Engineの起動・`RetryQueueManager.dequeue()` / `remove()`の呼び出し・Retry Queueへの書き込み（永続化を含む）はいずれも行わない（`_build_retry_events()`が呼び出すのは読み取り専用の`select_candidates()`のみ）
- [x] `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_engine`は本Releaseでも無改修
- [x] `tests/test_e2e_v3_7_0_retry_scheduler_event_integration.py`新規作成（74件）
- [x] E2Eテスト74/74 PASS、既存回帰（`v2.6.0` 118/118・`v3.4.0` 94/94・`v1.20.0` 170/170）PASS。`v3.6.0`は102/104 PASSで、2件FAILは`docs/CHANGELOG.md` `[KI-6]`（本Releaseによる意図的な変更。`retry_decision`ありの場合にRetry候補由来の`SchedulerEvent`が追加されるようになったため）
- [ ] 生成された`SchedulerEvent`（Retry候補由来）を消費する仕組み（Retry Engine起動・Workflow Engine起動等）・自動Retry実行・`RetryQueueManager.dequeue()` / `remove()`の使用・`job_id`プレフィックス衝突の構造的な防止・`metadata["retry_candidate"]`の型安全な公開（永続化・外部公開が必要になった場合）：対象外（→ 将来Release候補。次の節参照）

---

## v3.8.0 — Retry Engine Event Consumption（2026-07-03 完了）★ Release 2.0 続き

- [x] Project Charter作成：`docs/design/retry_engine_event_consumption_charter.md`（承認済み）
- [x] Architecture Design確定：`docs/design/retry_engine_event_consumption.md`（Architecture Review完了・Approve with Minor Recommendations、指摘事項2点を記録）
- [x] `src/retry_engine/retry_event_consumer.py`新規作成：Scheduler（v3.7.0）が生成したRetry候補由来の`SchedulerEvent`を、Retry Engine側が受け取って認識するための最小コンポーネント。`RETRY_JOB_ID_PREFIX = "retry:"`・`RetryCandidateEvent`（`run_id` / `candidate` / `source_event`の3フィールドのみを持つ軽量な`frozen dataclass`）・`RetryEventConsumer`（`recognize(event)` / `recognize_all(events)`の2メソッドのみを持つStatelessなコンポーネント）を追加
- [x] **Retry Engineが`SchedulerEvent`を認識可能になった。** `job_id`が`"retry:"`で始まる`SchedulerEvent`だけを識別し、`metadata["retry_candidate"]`に格納された候補オブジェクトを分解せずそのまま保持する（v3.7.0 Design Decision #3の方針を受信側でも踏襲）
- [x] `src/retry_engine/retry_manager.py`変更：`RetryManager`が`RetryEventConsumer`をConstructor Injectionで保持できるようにし、`recognize_retry_events(events) -> list[RetryCandidateEvent]`を追加（`RetryEventConsumer.recognize_all()`への薄い委譲のみ）。`event_consumer`引数省略時は`RetryEventConsumer()`に自動フォールバックする（後方互換性維持）
- [x] `NullRetryManager`にも同名`recognize_retry_events(events)`を追加。`RetryEventConsumer`を一切構築・参照せず、常に空リスト`[]`を返す（「受け取れるが何もしない」）
- [x] `retry_engine`が`scheduler`パッケージ（`SchedulerEvent`型のみ）に依存する初めてのRelease。`SchedulerEngine`等の実行系クラスは一切importしない。`scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue`はいずれも本Releaseでも無改修
- [x] Retry Queueの更新・`RetryQueueManager.dequeue()` / `remove()`の呼び出し・Retry実行の開始・Queue永続化・既存Job判定ループの変更はいずれも行わない（構造的にAST・Spyで確認済み）
- [x] `tests/test_e2e_v3_8_0_retry_engine_event_consumption.py`新規作成（70件）
- [x] E2Eテスト70/70 PASS、既存回帰（`v2.6.0` 118/118・`v2.7.0` 163/163・`v2.8.0` 182/182・`v2.9.0` 103/103）PASS。`v3.0.0`（134/136）・`v3.1.0`（151/152）・`v3.2.0`（99/102）・`v3.3.0`（69/72）・`v3.4.0`（92/94）・`v3.5.0`（69/72）・`v3.6.0`（100/104）・`v3.7.0`（72/74）はいずれも`docs/CHANGELOG.md` `[KI-7]`（本Releaseによる意図的な変更）を含む
- [ ] 認識結果（`RetryCandidateEvent`）を使った自動Retry実行・実運用のComposition Root・`job_id`プレフィックス衝突の構造的な防止・`RetryCandidateEvent.candidate`の型安全な公開：対象外（→ 将来Release候補。次の節参照）

---

## v3.9.0 — Retry Engine Event Dispatch（2026-07-06 完了）★ Release 2.0 続き

- [x] Project Charter作成：`docs/design/retry_engine_event_dispatch_charter.md`（承認済み）
- [x] Architecture Design確定：`docs/design/retry_engine_event_dispatch.md`（Architecture Review完了・Approve with Minor Recommendations、指摘事項1点を記録）
- [x] `src/retry_engine/retry_event_dispatcher.py`新規作成：`RetryEventConsumer`（v3.8.0）が認識した`RetryCandidateEvent`を、Retry Engine側がDispatch対象として整理するための最小コンポーネント。`RetryDispatchEvent`（`candidate_event` / `dispatchable`の2フィールドのみを持つ軽量な`frozen dataclass`）・`RetryEventDispatcher`（`dispatch_one(candidate_event)` / `dispatch(candidate_events)`の2メソッドのみを持つStatelessなコンポーネント）を追加
- [x] **Retry Engineが認識済みのRetryCandidateEventをDispatch対象として扱えるようになった。** `dispatchable`は`candidate_event.run_id`が空でないかという構造的妥当性のみで判定し、優先度・件数上限に基づく選別ロジックはあえて導入しない。`dispatchable=False`と判定されたイベントもリストから除外せず、そのまま返す（判定結果を可視化する）
- [x] 通常イベントとRetryイベントの振り分けは二段階構成とした：第1段階（`recognize_retry_events()`、v3.8.0、無改修）がJob由来の`SchedulerEvent`を除外し、第2段階（本Release、`dispatch_retry_events()`）はRetry候補由来の`RetryCandidateEvent`のみを入力とする。`RetryEventDispatcher`は生の`SchedulerEvent`を一切扱わない
- [x] `src/retry_engine/retry_manager.py`変更：`RetryManager`が`RetryEventDispatcher`をConstructor Injectionで保持できるようにし、`dispatch_retry_events(events) -> list[RetryDispatchEvent]`を追加（`recognize_retry_events()`への委譲→`RetryEventDispatcher.dispatch()`への委譲、の2段階のみで完結する薄い委譲）。`event_dispatcher`引数省略時は`RetryEventDispatcher()`に自動フォールバックする（後方互換性維持）
- [x] `NullRetryManager`にも同名`dispatch_retry_events(events)`を追加。`RetryEventDispatcher`を一切構築・参照せず、常に空リスト`[]`を返す（「受け取れるが何もしない」）
- [x] `retry_event_dispatcher.py`は`scheduler` / `retry_queue`いずれも新規importしない（`.retry_event_consumer`（`retry_engine`パッケージ内）と標準ライブラリのみに依存）。`scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_event_consumer.py`はいずれも本Releaseでも無改修
- [x] Retry Queueの更新・`RetryQueueManager.dequeue()` / `remove()`の呼び出し・Retry実行の開始・Queue永続化・既存Job判定ループの変更はいずれも行わない（構造的にAST・Spyで確認済み）
- [x] `tests/test_e2e_v3_9_0_retry_engine_event_dispatch.py`新規作成（73件）
- [x] E2Eテスト73/73 PASS、既存回帰（`v1.20.0` 170/170・`v2.0.0` 118/118・`v2.6.0` 118/118・`v2.7.0` 163/163・`v2.8.0` 182/182・`v2.9.0` 103/103）PASS。`v3.0.0`（140/142）・`v3.1.0`（151/152）・`v3.2.0`（99/102）・`v3.3.0`（69/72）・`v3.4.0`（92/94）・`v3.5.0`（69/72）・`v3.6.0`（100/104）・`v3.7.0`（72/74）・`v3.8.0`（67/70）はいずれも`docs/CHANGELOG.md` `[KI-8]`（本Releaseによる意図的な変更）を含む
- [ ] Dispatch結果（`RetryDispatchEvent`）を使った自動Retry実行（Retry Execution）・優先度・件数上限に基づく選別ロジック・実運用のComposition Root・`job_id`プレフィックス衝突の構造的な防止：対象外（→ 将来Release候補。次の節参照）

---

## v4.0.0 — Retry Execution Foundation（2026-07-06 完了）★ Release 2.0 続き

- [x] Project Charter作成：`docs/design/retry_execution_foundation_charter.md`（承認済み）
- [x] Architecture Design確定：`docs/design/retry_execution_foundation.md`（Architecture Review完了・Approve with Recommendations、指摘事項2点を記録）
- [x] `src/retry_engine/retry_execution_selector.py`新規作成：`RetryEventDispatcher`（v3.9.0）が整理した`RetryDispatchEvent`のうち、`dispatchable=True`のものだけを実行対象として選別する最小コンポーネント。`RetryExecutionSelector`（`select(dispatch_events)`の1メソッドのみを持つStatelessなコンポーネント）を追加
- [x] `src/retry_engine/retry_execution_coordinator.py`新規作成：選別済みの`RetryDispatchEvent`について初めて`RetryManager.retry()`を呼び出し、結果を集約する最小コンポーネント。`RetryExecutionResult`（`dispatch_event` / `retry_result`の2フィールドのみを持つ軽量な`frozen dataclass`。既存の`RetryResult`は無変更）・`RetryExecutionCoordinator`（`execute(dispatch_events, retry_fn, dry_run=False)`の1メソッドのみを持つStatelessなコンポーネント）を追加
- [x] **`RetryManager.retry()`が、Dispatch結果（`dispatchable=True`のもの）を起点に初めて呼び出せるようになった。** `dispatchable`を参照する箇所を`RetryExecutionSelector.select()`の1箇所に集約し、「`dispatchable=true`を唯一の実行入口とする」設計を採用した。`RetryExecutionCoordinator`は選別済みのイベントのみを受け取り、実行・結果集約のみを担当する（判定ロジックを複製しない）
- [x] `src/retry_engine/retry_manager.py`変更：`RetryManager`が`RetryExecutionSelector` / `RetryExecutionCoordinator`をConstructor Injectionで保持できるようにし、`execute_dispatchable_retries(events, dry_run=False) -> list[RetryExecutionResult]`を追加（`dispatch_retry_events()`への委譲→`RetryExecutionSelector.select()`への委譲→`RetryExecutionCoordinator.execute()`への委譲、の3段階のみで完結する薄い委譲。判定ロジックは`RetryManager`自身には一切書かない）。`execution_selector` / `execution_coordinator`引数省略時はそれぞれ自動フォールバックする（後方互換性維持）
- [x] `NullRetryManager`にも同名`execute_dispatchable_retries(events, dry_run=False)`を追加。`RetryExecutionSelector` / `RetryExecutionCoordinator`を一切構築・参照せず、常に空リスト`[]`を返す（「受け取れるが何もしない」）
- [x] Queueには一切依存しない設計とした。`RetryExecutionSelector` / `RetryExecutionCoordinator`のいずれも`RetryQueueManager`への参照・importを持たない。`retry_attempt`は`candidate_event.candidate`から`getattr(..., 1)`で取得する（Queue非依存を優先した暫定実装。将来`RetryCandidateEvent`への正式なフィールド追加を検討する余地を残す）
- [x] `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_event_consumer.py` / `retry_event_dispatcher.py`はいずれも本Releaseでも無改修
- [x] Retry Queueの更新・`enqueue_retry()` / `dequeue_retry()`の呼び出し・`RetryQueueManager.dequeue()` / `remove()`の呼び出し・Queue永続化・Retry Policy（優先度・件数上限に基づく選別ロジック）の導入はいずれも行わない（構造的にAST・Spyで確認済み）
- [x] `tests/test_e2e_v4_0_0_retry_execution_foundation.py`新規作成（88件）
- [x] E2Eテスト88/88 PASS、既存回帰（`v1.9.0`〜`v2.9.0`）全PASS。`v3.0.0`（152/154）・`v3.1.0`（151/152）・`v3.2.0`（99/102）・`v3.3.0`（69/72）・`v3.4.0`（92/94）・`v3.5.0`（69/72）・`v3.6.0`（100/104）・`v3.7.0`（72/74）・`v3.8.0`（67/70）・`v3.9.0`（70/73）はいずれも`docs/CHANGELOG.md` `[KI-9]`（本Releaseによる意図的な変更）を含む
- [ ] Retry Queueの更新（`enqueue_retry()` / `dequeue_retry()`の自動呼び出し）・`RetryQueueManager.dequeue()` / `remove()`の呼び出し・Queue永続化・Retry Policy・実運用のComposition Root・Scheduler側の変更：対象外（→ 将来Release候補。次の節参照）

---

## v4.1.0 — Retry Queue Update Foundation（2026-07-06 完了）★ Release 2.0 続き

- [x] Project Charter作成：`docs/design/retry_queue_update_foundation_charter.md`（承認済み）
- [x] Architecture Design確定：`docs/design/retry_queue_update_foundation.md`（Architecture Review完了・Approve with Recommendations、指摘事項2点を記録）
- [x] `src/retry_engine/retry_queue_update_decider.py`新規作成：`RetryManager.execute_dispatchable_retries()`（v4.0.0）が集約した`RetryExecutionResult`のリストを受け取り、各要素について対応するRetry Queue項目の更新先状態を判定する最小コンポーネント。`RetryQueueUpdateOutcome`（`COMPLETE` / `FAIL` / `NOOP`の3値Enum）・`RetryQueueUpdateDecision`（`execution_result` / `outcome` / `target_status` / `reason`の4フィールドを持つ`frozen dataclass`）・`RetryQueueUpdateDecider`（`decide()` / `decide_all()`の2メソッドのみを持つStatelessなコンポーネント）を追加
- [x] **判定基準を「再実行が実際に実行されたか」（`RetryResult.outcome == RETRIED`）の1点に限定した。** `RETRIED`かつ`overall_success=True`は`COMPLETE`（→`RetryQueueStatus.COMPLETED`）、`RETRIED`かつ`overall_success=False`は`FAIL`（→`RetryQueueStatus.FAILED`）、`SKIPPED` / `NOT_FOUND` / `DISABLED`はいずれも`NOOP`（更新なし）に統一する安全側の設計を採用した
- [x] `src/retry_engine/retry_manager.py`変更：`RetryManager`が`RetryQueueUpdateDecider`をConstructor Injectionで保持できるようにし、`decide_retry_queue_updates(events, dry_run=False) -> list[RetryQueueUpdateDecision]`を追加（`execute_dispatchable_retries()`への委譲→`RetryQueueUpdateDecider.decide_all()`への委譲、の2段階のみで完結する薄い委譲）。`queue_update_decider`引数省略時は自動フォールバックする（後方互換性維持）
- [x] `NullRetryManager`にも同名`decide_retry_queue_updates(events, dry_run=False)`を追加。`RetryQueueUpdateDecider`を一切構築・参照せず、常に空リスト`[]`を返す（「受け取れるが何もしない」）
- [x] `retry_queue`パッケージへの変更は一切不要だった。`RetryQueueStatus.COMPLETED` / `FAILED`はv3.1.0で既に予約値として定義済みであり、新しい状態値の追加すら不要。「更新しない」は`retry_engine`側の新規Enum（`NOOP`）と`target_status=None`の組み合わせで表現した
- [x] `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_event_consumer.py` / `retry_event_dispatcher.py` / `retry_execution_selector.py` / `retry_execution_coordinator.py`はいずれも本Releaseでも無改修
- [x] `RetryQueueManager.remove()` / `dequeue()`の呼び出し・Queue永続化・判定結果をQueue内部ストアへ実際に反映する処理・Retry Policy・Retry Metricsはいずれも行わない（構造的にAST・Spyで確認済み）
- [x] `tests/test_e2e_v4_1_0_retry_queue_update_foundation.py`新規作成（87件）。Minor Recommendation 1（`SKIPPED` / `NOT_FOUND` / `DISABLED`それぞれの独立した単体テスト）・Recommendation 2（SKIPPEDによるQueue滞留リスクのドキュメント化確認）を反映
- [x] E2Eテスト87/87 PASS、既存回帰（`v1.9.0`〜`v2.9.0`）全PASS。`v3.0.0`（158/160）・`v3.1.0`（151/152）・`v3.2.0`（99/102）・`v3.3.0`（69/72）・`v3.4.0`（92/94）・`v3.5.0`（69/72）・`v3.6.0`（100/104）・`v3.7.0`（72/74）・`v3.8.0`（67/70）・`v3.9.0`（70/73）・`v4.0.0`（83/88）はいずれも`docs/CHANGELOG.md` `[KI-10]`（本Releaseによる意図的な変更）を含む
- [ ] `RetryQueueManager.remove()`の解禁・`dequeue()`の本格実装・Queue永続化・Retry Policy・Retry Metrics・実運用のComposition Root・Scheduler側の変更：対象外（→ 将来Release候補。次の節参照）

---

## v3.x 以降の候補（未着手）

- [ ] Windows タスクスケジューラ等の外部スケジューラから `scripts/run_workflow_engine.py` を定時起動する実運用連携（Scheduler Engine自体の内部実装はv2.6.0で完了。OS側との実連携は未着手）
- [ ] 複数実行主体（`AgentManager`経由の既存script群とWorkflow Engine経由のscript）の排他制御（ロック機構）の実装（v2.7.0では運用制約として明記するのみ）
- [ ] SchedulerJobの永続化（JSON/DB化）・複数Job登録・設定ファイル化・動的登録
- [ ] `WorkflowTriggerAgent`（AI改善6ステップ）とWorkflow Engineの統合（`PublishTriggerAgent`との役割重複整理が前提）
- [ ] 重要度別の公開制御（S→即時公開・A→予約投稿・B→下書き）
- [ ] Metrics Foundation・Dashboard Foundation（Workflow Monitor v2.9.0の判定結果・Execution History v2.8.0の履歴データ・Retry Engine v3.0.0の`RetryResult`・Retry Queue v3.1.0の`RetryQueueItem`を消費する側）
- [ ] `CANCELLED`の正式な判定方法・`WAITING`の導入タイミング（Workflow Monitor v2.9.0で予約値として定義済み。Workflow Engine・Schedulerのデータモデル拡張が前提）
- [ ] `scripts/run_retry_engine.py`（CLIエントリポイント）・Scheduler連携による定期自動再試行（Retry Engine v3.0.0では実装対象外。単発の`RetryManager.retry(run_id)`呼び出しのみ提供）
- [x] Retry Queue：v3.1.0で実装済み（Queue管理のみ。`enqueue` / `dequeue` / `remove` / `list` / `exists` / `count`）
- [x] Retry QueueとRetry Engineの実配線：v3.2.0で実装済み（`RetryManager`が`RetryQueueManager`をDIで保持し、`enqueue_retry()` / `dequeue_retry()`で委譲。ただし`dequeue()`した項目を自動的に`RetryManager.retry()`へ渡す自動実行は引き続き対象外）
- [x] Retry QueueとSchedulerの間のAdapter：v3.3.0で実装済み（`RetrySchedulerSource` / `NullRetrySchedulerSource`。`list()` / `count()`への薄い委譲のみで、Scheduler本体からはまだ呼ばれていない「消費者不在の先行実装」）
- [x] Scheduler本体（`SchedulerEngine.evaluate()` / `run_due()`）とのWiring：v3.4.0で実装済み（`SchedulerEngine`が`RetrySchedulerSource` / `NullRetrySchedulerSource`をConstructor Injectionで保持し、`count_pending_retries()` / `list_pending_retries()`で読み取れる。ただし`evaluate()` / `run_due()`の判定ロジック自体には組み込んでおらず、読み取れる状態を作っただけの「接続のみ」のRelease）
- [ ] 実運用のComposition Root：`RetryQueueConfig.is_ready()`（`RETRY_QUEUE_ENABLED`）を参照して`RetrySchedulerSource` / `NullRetrySchedulerSource`を組み立て、`SchedulerEngine`・`RetrySchedulerDecision`へ渡す実際の起動スクリプト（例：`scripts/run_scheduler.py`）。v3.4.0・v3.5.0ではテストコードでの組み立て例のみ（詳細は`docs/design/retry_scheduler_wiring.md` 11章、`docs/design/retry_scheduler_decision.md` 11章 Future Extension）
- [x] pending retryから「次に処理すべき候補」を選ぶロジック：v3.5.0で実装済み（`RetrySchedulerDecision.select_candidates()` / `select_next_candidate()`。`RetrySchedulerSource`の既存順序をそのまま活用し、独自の並べ替えは行わない）
- [x] `RetrySchedulerDecision`と`SchedulerEngine`のConstructor Injectionによる接続：v3.6.0で実装済み（`SchedulerEngine`が`RetrySchedulerDecision`を外部から直接DIで保持し、`select_candidates()` / `select_next_candidate()`で読み取れる。`SchedulerEngine`自身は`RetrySchedulerDecision`を生成しない）
- [x] 選択結果を`evaluate()` / `run_due()`の判定ロジックへ組み込む統合：v3.7.0で実装済み（Retry Scheduler Event Integration。`RetrySchedulerDecision`の選択結果を使ってRetry候補由来の`SchedulerEvent`をAdditive方式で生成する。既存Job判定ループは無変更、`retry_decision=None`時は既存動作と完全互換）
- [ ] 自動Retry実行：`RetrySchedulerDecision.select_next_candidate()` / `select_candidates()`で選ばれた候補（v3.7.0では`SchedulerEvent`として観測可能になった）を、`RetryQueueManager.dequeue()`で取り出し`RetryManager.retry()`へ渡す一連の自動化。`dequeue()` / `remove()`の使用もこの段階で初めて解禁される想定（Retry Scheduler Integration v3.3.0・Retry Scheduler Wiring v3.4.0・Retry Scheduler Decision v3.5.0・Retry Scheduler Event Integration v3.7.0ではいずれも意図的に対象外）
- [x] Retry候補由来の`SchedulerEvent`（v3.7.0）を**認識する**仕組み：v3.8.0で実装済み（Retry Engine Event Consumption。`retry_engine`パッケージに`RetryEventConsumer`を新設し、`RetryManager.recognize_retry_events()`経由で`job_id`が`"retry:"`で始まる`SchedulerEvent`だけを識別・認識できるようにした。認識のみで、実行・Queue操作はいずれも意図的に対象外のまま）
- [x] **Retry Engine Event Dispatch**：`recognize_retry_events()`（v3.8.0）が返した`RetryCandidateEvent`をDispatch対象として整理する仕組み：v3.9.0で実装済み。`retry_engine`パッケージに`RetryEventDispatcher`を新設し、`RetryManager.dispatch_retry_events()`経由で`RetryDispatchEvent`（`candidate_event` / `dispatchable`）として整理できるようにした。`dispatchable`は`run_id`の非空判定のみに限定し、優先度・件数上限に基づく選別ロジックはあえて導入していない（次段階Retry Executionの検討事項として持ち越し）。整理のみで、実行・Queue操作はいずれも意図的に対象外のまま
- [x] **Retry Execution Foundation**：Dispatchされた`RetryDispatchEvent`（`dispatchable=True`のもの）を対象に`RetryManager.retry()`を呼び出せる基盤：v4.0.0で実装済み。`retry_engine`パッケージに`RetryExecutionSelector`（判定：`dispatchable=True`の選別）・`RetryExecutionCoordinator`（実行：`retry_fn`呼び出しと結果集約）を新設し、`RetryManager.execute_dispatchable_retries()`経由で`RetryManager.retry()`を呼び出せるようになった。ただしQueueの読み取り（`dequeue()`によるRetry Queueからの取り出し）は行わず、`execute_dispatchable_retries()`に渡された`SchedulerEvent`（Dispatch対象）のみを入力とする「Foundation」に留まる
- [ ] **自動Retry実行の実運用化（Composition Root）**：Scheduler（`SchedulerEngine.run_due()`）が生成した`SchedulerEvent`を、定期的に`RetryManager.execute_dispatchable_retries()`（v4.0.0）へ渡し続ける実際の起動スクリプト。v4.0.0時点ではテストコードでの呼び出し例のみ（`RetrySchedulerDecision.select_next_candidate()` / `select_candidates()`で選ばれた候補がv3.7.0で`SchedulerEvent`として観測可能・v3.8.0で`retry_engine`側から認識可能・v3.9.0でDispatch対象として整理可能・v4.0.0で`RetryManager.retry()`の呼び出しまで到達したが、これを継続的に回す実運用の起動導線は引き続き未着手）
- [x] **Retry Queue Update**：Retry実行の結果（成功・失敗）を、対応するRetry Queue項目がどの状態（`RetryQueueStatus.COMPLETED` / `FAILED`）へ更新されるべきか判定する仕組み：v4.1.0で実装済み（判定のみ。Queueへの実際の反映は次項「Retry Queue Removal」へ）。`retry_engine`パッケージに`RetryQueueUpdateDecider`を新設し、`RetryManager.decide_retry_queue_updates()`経由で`RetryExecutionResult`から`RetryQueueUpdateDecision`（`COMPLETE` / `FAIL` / `NOOP`）を判定できるようになった
- [x] **Retry Queue Removal**：`RetryQueueUpdateDecider`（v4.1.0）が判定した`RetryQueueUpdateDecision`を使って、実際に`RetryQueueManager.remove()`を呼び出し、Queueから該当項目を除去する仕組み：v4.2.0で実装済み（`COMPLETE` / `FAIL`のみremove対象。`NOOP`はremove対象外のまま）。`retry_engine`パッケージに`RetryQueueRemovalExecutor`を新設し、`RetryManager.apply_retry_queue_removals()`経由で`RetryQueueManager.remove()`を初めて呼び出せるようになった。v3.1.0〜v4.1.0では`dequeue()` / `remove()`いずれも呼び出されないことが構造的に確認されていたが、本項目で`remove()`のみ解禁された（`dequeue()`は引き続き対象外）
- [x] **`SKIPPED`（`max_attempts`到達）のQueue滞留対応（Retry Queue Cleanup）**：v4.3.0で実装済み。`retry_engine`パッケージに`RetryQueueCleanupDecider`（`RetryQueueUpdateDecision`のうちSKIPPED由来の`NOOP`のみをCLEANUP判定）・`RetryQueueCleanupExecutor`（CLEANUP項目のみ`RetryQueueManager.remove()`を呼び出す）を新設し、`RetryManager.decide_retry_queue_cleanup()` / `apply_retry_queue_cleanup()`経由で、v4.2.0では対象外だった`SKIPPED`由来の滞留を解消できるようになった。`COMPLETE` / `FAILED`（v4.2.0で既に除去済み） / `NOT_FOUND` / `DISABLED`はいずれも対象外（KEEP）のまま。新しいQueueステータス・Dead Letter Queueは追加せず、既存の`RetryQueueManager.remove()`を再利用した（`docs/design/retry_queue_cleanup_foundation.md`）
- [x] **`NOT_FOUND` / `DISABLED`由来のQueue滞留対応（NOT_FOUND / DISABLED Cleanup）**：v4.4.0で実装済み。「Terminal（終端状態）かTransient（一時状態）か」という上位概念でまず各`RetryOutcome`を分類し（`retry_outcome_terminality.py`の`RETRY_OUTCOME_TERMINALITY`分類表、v4.4.0新規Deciderに対してのみ権威を持つSingle Source of Truth）、その分類からCleanup方針を導出する設計とした。`NOT_FOUND`は`ExecutionHistoryStore`に削除操作が存在せず不可逆であること・現状のコードベースには自動的にfoundへ遷移する経路が存在しないことを根拠にTerminalと判定しCLEANUP対象とした。`DISABLED`は`RETRY_ENGINE_ENABLED`という判定時点の設定値のスナップショットに過ぎず後で反転しうることを根拠にTransientと判定しKEEPのまま据え置いた（`RetryQueueManager`がin-memory dictのみで構成されることが前提。Queue永続化導入時は要再評価）。`retry_engine`パッケージに`RetryQueueTerminalCleanupDecider` / `RetryQueueTerminalCleanupExecutor`を新設し、`RetryManager.decide_retry_queue_terminal_cleanup()` / `apply_retry_queue_terminal_cleanup()`経由で、v4.3.0では対象外だった`NOT_FOUND`由来の滞留を解消できるようになった。`COMPLETE` / `FAILED`（v4.2.0で除去済み） / `SKIPPED`（v4.3.0で除去済み）はいずれも対象外（KEEP）のまま。新しいQueueステータス・Dead Letter Queueは追加せず、既存の`RetryQueueManager.remove()`を再利用した（`docs/design/retry_queue_notfound_disabled_cleanup_foundation.md`）
- [x] **Retry Policy Foundation**：v4.5.0で実装済み。`RetryPolicy`（v3.0.0、既存の固定ルール実装）が実際に満たしている契約を、`RetryManager`の依存箇所（`retry()`が呼ぶ`should_retry(monitor_status, attempt) -> bool`、`_skip_reason()`が参照する`target_statuses` / `max_attempts`）から洗い出し、`retry_policy_protocol.py`（新規）に`RetryDecisionPolicy`（最小契約）・`ExplainableRetryPolicy`（`RetryDecisionPolicy`を拡張し`target_statuses` / `max_attempts`を追加した契約）としてProtocol化した。`RetryPolicy`自体（`retry_policy.py`）は**本Releaseでも無改修（0 diff）**。`RetryManager.__init__` / `from_config()`の`policy` / `retry_policy`引数の型注釈を`RetryPolicy`（具体クラス）から`ExplainableRetryPolicy`（抽象契約）へ変更したが、これは型注釈のみの変更であり`retry()` / `_skip_reason()`のロジック本体は1行も変更していない。**新しいRetry戦略（`FixedRetryPolicy` / `ExponentialBackoffPolicy` / `AdaptiveRetryPolicy`等）の実装自体は本Releaseの対象外（Non-Goal）。** 本Releaseは「差し替え可能な構造」を整備するところまでに留めた（`docs/design/retry_policy_foundation.md`）
- [x] **Retry Enqueue Trigger Foundation**：v4.6.0で実装済み。`WorkflowMonitorManager`（v2.9.0、無改修）が判定した`FAILED` / `TIMEOUT`のWorkflowを検知し、まだ`RetryQueueManager`（v3.1.0、無改修）に存在しないものだけを`enqueue()`する新規Adapter `RetryEnqueueTrigger` / `NullRetryEnqueueTrigger`（`src/retry_enqueue_trigger/`）を新設した。v3.0.0〜v4.5.0で構築されたRetry Queue〜Retry Engineの下流パイプラインは、Queueへ実際に投入する主体が存在しなかった（`enqueue_retry()` / `enqueue()`がどこからも呼ばれていなかった）ため、本Releaseはこの「上流の欠落」を埋めるものである。`retry_engine`は経由せず`workflow_monitor` / `retry_queue`に直接依存する構成とし（`retry_scheduler_source`と同じ「下位パッケージへの直接依存」パターン）、Feature Gate・Configクラスは追加せずNull Object Patternのみで有効/無効を表現する。Queue内の重複防止は`RetryQueueManager.exists()`のみで、Queueから除去された`run_id`の無限再投入リスクへの対策は意図的に対象外（Known Issue、`docs/design/retry_enqueue_trigger_foundation.md` 11章）。新設Adapterを定期的に駆動する起動スクリプト（Composition Root）は本Releaseの対象外（`docs/design/retry_enqueue_trigger_foundation.md`）
- [x] **Retry History Foundation**：v4.7.0で実装済み。`original_run_id`ごとの再試行履歴（試行回数・直近記録時刻）を記録するだけの新規独立パッケージ`src/retry_history/`（`RetryHistoryRecord` / `RetryHistoryManager` / `NullRetryHistoryManager`）と、`retry_engine`側の新規Statelessコンポーネント`RetryHistoryRecordExecutor`（`retry_history_recorder.py`）を新設した。**重要な発見**：v4.6.0 Known Issueが対策候補として挙げていた`metadata["retried_from"]`は、`WorkflowExecutionRecord`に`metadata`フィールドが存在せず`WorkflowEngineExecutor`もExecution Historyへ渡していないため、実際には参照不可能であることが判明した。本Releaseはこれを踏まえ、情報源を`RetryResult`（`retry_engine`自身が生成するデータ）に限定し、Execution Historyの拡張を一切行わない設計とした。`RetryManager.record_retry_history(events, dry_run=False)`を新設し、`execute_dispatchable_retries()`（v4.0.0、無変更）への委譲→`RetryHistoryRecordExecutor.record_all()`（outcome=RETRIEDの項目のみ記録）の2段階のみで完結する薄い委譲とした。`history` / `history_recorder`引数はいずれも末尾のデフォルト値付きで追加し、既存メソッド（`retry()` 〜 `apply_retry_queue_terminal_cleanup()`）は1行も変更していない。`retry_history`はstateful storeであるため`retry_queue`と同じ理由で、省略時は`NullRetryHistoryManager()`にフォールバックする。`retry_history`は`retry_engine`を一切importしない（循環なし）。**記録のみに留め、`RetryEnqueueTrigger`側が本履歴を参照して再enqueueを止める判定（無限再投入対策の完成）は次Release以降に送った**（Foundation First、`docs/design/retry_history_foundation.md`）
- [x] **Retry Enqueue Guard（無限再投入対策の完成）**：v4.8.0で実装済み。v4.7.0で記録した`RetryHistoryManager`の再試行履歴を`RetryEnqueueTrigger.enqueue_pending_failures()`側が参照し、既に再試行済みの`run_id`を再enqueueしないようにする新規コンポーネント`RetryEnqueueGuard`（`src/retry_enqueue_trigger/retry_enqueue_guard.py`）を新設した。v4.6.0 Known Issue・v4.7.0 Future Extensionの完成形（`docs/design/retry_enqueue_guard.md`）。判定基準は「再試行履歴が1回でもあればブロック」の二値のみ（`retry_engine`への新規依存を避けるための意図的な単純化）。副作用として、`RETRY_MAX_ATTEMPTS`を活かした複数回の自動リトライ運用は本Release後も`RetryEnqueueTrigger`経由では実質使えないままである（新Known Issue、`docs/design/retry_enqueue_guard.md` 11章。`attempt`の実回数連動は将来Release候補）
- [x] **Retry Attempt Synchronization Foundation（`attempt`の実回数連動）**：v4.9.0で実装済み。`RetryEnqueueTrigger.enqueue_pending_failures()`が`self._history.has_history()`ではなく`self._history.get()`を呼び出すよう変更し、その戻り値（`RetryHistoryRecord | None`）から「履歴の有無」（Guard判定用）と「次のattempt番号（`attempt_count + 1`、履歴なしは`1`）」（Queue登録用）の両方を導出するようにした。これまで常に`1`固定だった`RetryQueueManager.enqueue()`の`retry_attempt`引数が、実際の試行回数に連動するようになった（`docs/design/retry_attempt_synchronization_foundation.md`）。**本Release単体では観測可能な挙動変化は発生しない**：`RetryEnqueueGuard`（v4.8.0）は「履歴が1回でもあればBLOCK」の二値判定のままのため、`queue.enqueue()`に実際に到達するのは履歴なし（＝attempt=1）のケースのみである。Guard判定基準の精緻化（`attempt_count >= max_attempts`比較）は引き続き将来Release候補（同設計書4章 Known Issue）
- [x] **Retry Enqueue Guard Refinement Foundation（Guard判定基準の精緻化）**：v5.0.0で実装済み。`RetryEnqueueGuard.decide()`のシグネチャを`decide(run_id, has_history: bool)`から`decide(run_id, next_attempt: int, max_attempts: int)`へ変更し、判定基準を「履歴の有無」の二値から「`next_attempt > max_attempts`ならBLOCK」の回数比較へ精緻化した。これにより、v4.9.0で配線済みだった`retry_attempt`の実回数連動に初めて実際の消費者が生まれ、`max_attempts`を明示的に注入すれば複数回リトライが技術的に可能な状態になった（`docs/design/retry_enqueue_guard_refinement_foundation.md`）。`max_attempts`は`RetryEnqueueTrigger.__init__`ではなく`enqueue_pending_failures(limit=None, max_attempts=1)`の呼び出し引数として受け取り、インスタンス状態としては保持しない設計とした（Architecture Review Finalでの再検討結果。`__init__`は本Releaseでも完全に無変更）。`max_attempts`省略時のデフォルト値`1`は`RetryPolicy.max_attempts`（デフォルト3）とは意図的に独立した、`retry_engine`非依存を保つための構造的セーフガードである。Composition Root（`RetryPolicy.from_env().max_attempts`を実際に注入する起動導線）は引き続き対象外（次項参照）
- [ ] **Retry Queue Persistence**：Retry Queueの永続化（SQLite/Redis等）。現状は完全にin-memoryで、プロセス終了とともにQueueの内容が失われる（v3.1.0 Retry Queue Foundationから継続する対象外項目。**v4.4.0のDISABLED＝Keep判断はこの前提に依存しているため、本項目のCharter作成時に再評価が必要**）
- [ ] **Retry Policy（選別基準の拡張）**：`RetryExecutionSelector`（v4.0.0）が行う`dispatchable=True`の選別に、優先度・件数上限に基づくロジックを追加する。v3.9.0・v4.0.0ではいずれも意図的に導入しておらず、`RetryExecutionSelector.select()`のみを拡張・置換すればよい設計としている（`RetryExecutionCoordinator` / `RetryManager`は無改修のまま拡張可能。`docs/design/retry_execution_foundation.md` 2章・12章）。**混同注意**：本項目は「Dispatch対象の選別基準」の話であり、v4.5.0の`RetryPolicy`（`should_retry()`で再試行対象を判定する既存クラス）とは別物である
- [ ] **Retry Metrics / Monitoring**：Retry実行の成功率・試行回数分布・Queue滞留時間等を集計・可視化する仕組み。一般的な「Metrics Foundation・Dashboard Foundation」（本ファイル該当セクション参照）のRetry Engine向け具体化として、`RetryExecutionResult`（v4.0.0）・`RetryResult`（v3.0.0）・`RetryQueueItem`（v3.1.0）を消費する側に位置づける
- [ ] `job_id`予約プレフィックス（`"retry:"`）の構造的な衝突防止：`SchedulerJob.job_id`が偶然同じプレフィックスを持つ場合の検証・防止（v3.7.0では慣習のみで構造的な強制なし。v3.8.0では`retry_engine`側も同じ慣習を踏襲するのみで解消していない。詳細は`docs/design/retry_scheduler_event_integration.md` 11章・13章 Design Decision #2、`docs/design/retry_engine_event_consumption.md` 11章）
- [ ] `"retry:"`プレフィックス定数の重複解消：`scheduler_engine.py`（文字列リテラル）と`retry_event_consumer.py`（`RETRY_JOB_ID_PREFIX`定数、v3.8.0）の2箇所に同じ値が独立に存在する。将来`scheduler`パッケージがこの文字列を公開定数としてexportした場合、`retry_engine`側はそれを参照する形に置き換えられる（Architecture Review Minor Recommendation、詳細は`docs/design/retry_engine_event_consumption.md` 13章 Design Decision #3・15.3節）
- [ ] `metadata["retry_candidate"]` / `RetryCandidateEvent.candidate`の型安全な公開・永続化・JSON serialization対応：v3.7.0・v3.8.0ではいずれもin-memoryの観測用途に限定（詳細は`docs/design/retry_scheduler_event_integration.md` 13章 Design Decision #3・11章、`docs/design/retry_engine_event_consumption.md` 13章 Design Decision #2・15.3節）
- [ ] Queueから取り出した項目の自動再実行・Scheduler連携（定期的な`dequeue()`処理）・Retry Queueの永続化（SQLite/Redis）・`COMPLETED`/`FAILED`への到達（結果フィードバックAPI）・Priority Queueの効率化（heapqベース）・Dead Letter Queue（Retry Queue Integration v3.2.0・Retry Scheduler Integration v3.3.0でも対象外。詳細は`docs/design/retry_queue_integration.md` / `docs/design/retry_scheduler_integration.md`）
- [ ] RetryDecision（Retry可否判定の専用コンポーネント化）・RetryReason Enum・Exponential Backoff・Adaptive Retry・Failure Classification・AI Retry Decision・Parallel/Distributed Retry・Circuit Breaker・Manual Retry UI・Notification（Retry Engine v3.0.0ではいずれも対象外。詳細は`docs/design/retry_engine_foundation.md` 11章 Future Extensions）。**Exponential Backoff / Adaptive Retryについては、v4.5.0で`RetryDecisionPolicy` / `ExplainableRetryPolicy`（Protocol）という差し替え可能な構造が整備済みであり、実装時はこれらの契約を満たす新クラスを追加するだけでよい（`RetryManager`側の追加改修は不要。`docs/design/retry_policy_foundation.md`）**
- [x] Retry History（再試行回数の記録）：v4.7.0で実装済み（上記「Retry History Foundation」参照）。ただし**永続化はしない**（プロセス内メモリのみ。`retry_queue`と同じ扱い）
- [x] **Retry Enqueue Triggerの無限再投入対策**：v4.8.0で解消済み（上記「Retry Enqueue Guard」参照）。v4.6.0の`RetryEnqueueTrigger`は`RetryQueueManager.exists()`によるQueue内重複防止のみを行い、Queueから除去（`COMPLETE` / `FAIL` / `CLEANUP`）された後もWorkflow Monitor上でなお`FAILED` / `TIMEOUT`のまま観測され続ける`run_id`を再度enqueueしてしまう可能性があった（`docs/design/retry_enqueue_trigger_foundation.md` 11章 Known Issue）。v4.7.0で整備した`RetryHistoryManager`をv4.8.0の`RetryEnqueueGuard`が参照する形で接続が完了し、Composition Root実装の前提条件が満たされた
- [x] **Retry Composition Root Foundation（Queue/Historyインスタンス共有の前提整備）**：v5.1.0で実装済み。新規パッケージ`src/retry_composition/`（`RetryCompositionRoot`）を追加し、`RetryQueueManager` / `RetryHistoryManager`を1インスタンスずつ生成して`RetryEnqueueTrigger`（Enqueue側）・`RetryManager`（Execute側）の両方へ同一インスタンスとして注入できるようにした。Architecture Reviewの過程で、両Managerがプロセス内メモリのみで状態を保持するため、Enqueue単体のComposition Rootを先に作ると「Runtime全体を組む段階で書き直しが発生する使い捨てComposition Root」になるリスクが判明し、Enqueue・Execute双方を対象にしたComposition Rootへとテーマを見直した。責務は「既存の`from_env()`/`from_config()`のみで組み立てて属性として公開すること」に限定し、実行順序の決定（`run_once()`等）・ループ・デーモン化・起動スクリプトはいずれも対象外とした（`docs/design/retry_composition_root_foundation.md`）。既存8パッケージ（`workflow_monitor` / `retry_queue` / `retry_history` / `retry_enqueue_trigger` / `retry_engine` / `workflow_engine` / `ai` / `execution_history`）はいずれも無改修
- [x] **Retry Runtime Orchestrator Foundation（Composition/Orchestration責務分離の確立）**：v5.2.0で実装済み。Architecture Reviewの過程で2つの発見があった。（発見A）`RetryManager.execute_dispatchable_retries()`が要求する`SchedulerEvent`は`RetryQueueManager → RetrySchedulerSource → RetrySchedulerDecision → SchedulerEngine`という経路でしか得られないが、v5.1.0の`RetryCompositionRoot`はこの経路を配線していなかった。（発見B）`RetryManager`の上位メソッド群（`apply_retry_queue_removals()`等）はそれぞれ独立に`execute_dispatchable_retries()`を再計算するため、素朴に並べて呼び出すと`retry()`が重複実行されるリスクがある。本Releaseは、`RetryCompositionRoot`へ`RetrySchedulerSource` / `RetrySchedulerDecision` / `SchedulerEngine`の配線を追加（発見Aの解消）する一方、新規パッケージ`src/retry_runtime_orchestrator/`（`RetryRuntimeOrchestrator`）を追加し、「Retry Runtimeの実行順序を将来管理する場所」として`trigger` / `scheduler` / `manager` / `queue` / `history` / `policy`をConstructor Injectionで保持するだけの構造を確立した（`run()` / `run_once()`等のBusiness Logicは本Releaseの対象外）。発見Bの解決は`RetryManager`へ統合APIを追加せず、次Execution Releaseで`RetryRuntimeOrchestrator`が`execute_dispatchable_retries()`を1回だけ呼び出しその結果を既存の公開Decider/Executor群へ配布する方針とし、`retry_manager.py`を無改修に保つ設計判断とした（`docs/design/retry_runtime_orchestrator_foundation.md`）。既存11パッケージ（`workflow_monitor` / `retry_queue` / `retry_history` / `retry_enqueue_trigger` / `retry_engine` / `workflow_engine` / `ai` / `execution_history` / `scheduler` / `retry_scheduler_source` / `retry_scheduler_decision`）はいずれも無改修
- [x] **Retry Runtime Run Once Foundation（Execution Release）**：v5.3.0で実装済み。`RetryRuntimeOrchestrator.run_once()`を新設し、`self.trigger.enqueue_pending_failures(max_attempts=self.policy.max_attempts)` → `self.scheduler.run_due(jobs=[])`（Retry候補由来のSchedulerEventのみ取得） → `self.manager.execute_dispatchable_retries(events)`（本メソッド内でちょうど1回だけ呼び出す）→ その結果を`RetryQueueUpdateDecider` / `RetryQueueRemovalExecutor` / `RetryQueueCleanupDecider` / `RetryQueueCleanupExecutor` / `RetryQueueTerminalCleanupDecider` / `RetryQueueTerminalCleanupExecutor` / `RetryHistoryRecordExecutor`（いずれも`retry_engine`が既に公開しているStateless・無引数コンストラクタのクラス）へ配布する、という1サイクル分の実行順序を実装した。これにより発見B（同一run_idに対する`retry()`の多重実行リスク）を`retry_manager.py`無改修のまま解消した。戻り値は`None`ではなく新設の`RetryRuntimeCycleResult`（`trigger_result` / `scheduler_events` / `execution_results` / `removal_results` / `cleanup_results` / `terminal_cleanup_results` / `history_results`）。`dry_run`引数は追加していない（`RetryExecutor.execute()`がdry_runの値に関わらず常に`outcome=RETRIED`を返すため、Queue除去・History記録という実際の副作用を防げず「安全なdry_run」にならないと判明したため。Known Issueとして記録し独立Releaseへ送った）。`scripts/`エントリーポイント・ループ・デーモン化は本Releaseの対象外。既存11パッケージおよび`retry_manager.py`はいずれも無改修（`docs/design/retry_runtime_run_once_foundation.md`）
- [x] **`scripts/run_retry_runtime.py`（Entry Point）**：v5.4.0で実装済み。`RetryCompositionRoot.from_env()` → `RetryRuntimeOrchestrator.from_composition_root()` → `run_once()`を1回だけ呼び出すEntry Pointを新設した。CLI引数は持たない（`run_once()`自体に分岐点がないため）。`format_summary(result) -> str`として表示ロジックを局所化し、将来Formatterクラスへ抽出しやすい構造に留めた。Exit Code Policyは正常終了0（Python標準）・例外発生時はPython標準の非0（fail-fast）・独自Exit Code体系は導入しないことを明文化した。Gate（`RETRY_ENGINE_ENABLED`等）が閉じている場合もscriptはNull判定（`isinstance()`）を一切行わず、常に`run_once()`を呼び出して結果件数（すべて0件）をそのまま表示する設計とした。`RetryCompositionRoot` / `RetryRuntimeOrchestrator`・既存12パッケージはいずれも無改修（`docs/design/retry_runtime_script_entry_point_foundation.md`）
- [x] **安全なdry_runの再設計（Retry Runtime Safe Dry Run Foundation）**：v5.6.0で実装済み。`RetryOutcome`へ`DRY_RUN`を追加し、`RetryExecutor.execute()`が`dry_run=True`の場合に`outcome=RetryOutcome.DRY_RUN`を返すよう変更した。`RetryQueueUpdateDecider` / `RetryHistoryRecordExecutor` / `RetryQueueRemovalExecutor` / `RetryQueueCleanupDecider`はいずれも無改修のまま自動的に安全側（NOOP・記録なし・除去なし）に倒れる。`retry_outcome_terminality.py`のみ、`classify_reason()`が明示列挙+raiseの網羅チェック方式であるため改修が必須だった（Architecture Reviewで発見。放置すると`run_once(dry_run=True)`がクラッシュしていた）。`RetryRuntimeOrchestrator.run_once()`に`dry_run: bool = False`引数を追加し伝播させた。`scripts/run_retry_runtime.py`への`--dry-run`配線・`RetryEnqueueTrigger`側（Queueへの新規登録）のdry_run対応はいずれも対象外とし、次Release候補（下記2件）へ申し送った（`docs/design/retry_runtime_safe_dry_run_foundation.md`）
- [x] **Retry Runtime Safe Dry Run Wiring Foundation**：v5.7.0で実装済み。`scripts/run_retry_runtime.py`の`main()`内部のみに`argparse`（ローカルimport）・`--dry-run`フラグを追加し、`RetryRuntimeOrchestrator.run_once(dry_run=...)`（v5.6.0）をCLIから安全に試せるようにした。`--dry-run`指定時は`main()`が`[DRY RUN MODE]`を表示する（`format_summary()`は経由しない）。`format_summary()` / `RetryRuntimeCycleResult` / `RetryRuntimeOrchestrator` / `RetryManager` / `RetryExecutor` / `RetryCompositionRoot`はいずれも無改修とし、変更対象を`main()`内部のみへ最小化した（`parse_args()`等の関数分離もYAGNIとして見送り）。CLI Summaryへの Known Issue説明文の表示は行わず、Enqueue非対象の制約は`docs/CHANGELOG.md` `[KI-23]`として管理する方針とした（`docs/design/retry_runtime_safe_dry_run_wiring_foundation.md`）
- [x] **Retry Enqueue Trigger Dry Run Foundation**：v5.8.0で実装済み。`RetryEnqueueTrigger.enqueue_pending_failures()`へ`dry_run: bool = False`を呼び出し時引数として追加した（`max_attempts`と同じ「呼び出し時引数、コンストラクタ非保持」パターン）。Monitor走査・History参照・Guard判定・Queue重複確認は`dry_run`の値に関わらず通常どおり実行するが、Guardを通過しQueue重複も存在しない候補について、`dry_run=True`の場合は`RetryQueueManager.enqueue()`を呼び出さず処理を終了する（`enqueued` / `failed`いずれにも加算しない）。`RetryRuntimeOrchestrator.run_once()`から`trigger.enqueue_pending_failures(max_attempts=self.policy.max_attempts, dry_run=dry_run)`への伝播も追加し、`--dry-run`指定時にRetry Queueへの新規enqueueが実際に抑止されるようになった（`[KI-23]`解消）。Architecture Review初版では`RetryEnqueueTriggerResult`へ`dry_run_planned`カウンタを追加しCLI表示も更新する案（案A）を提示したが、ユーザーレビューにより「実際に行われた結果のみを表す」という既存Result Contractの一貫性を優先する方針（案B）へ変更し、`RetryEnqueueTriggerResult` / `format_summary()` / `scripts/run_retry_runtime.py` / `RetryRuntimeCycleResult` / `RetryCompositionRoot` / `RetryManager` / `RetryExecutor` / `RetryQueueManager` / `RetryHistoryManager` / `RetryEnqueueGuard` / `RetryRuntimeLoop` / `NullRetryEnqueueTrigger`はいずれも無改修とした。dry_run時、Guard通過かつQueue重複なしの候補が既存カウンタのいずれにも加算されないため合計不変条件が成立しない場合がある点、Queue容量上限のシミュレーションができない点をKnown Limitationとして記録した（`docs/design/retry_enqueue_trigger_dry_run_foundation.md`）
- [ ] **Retry専用Scheduler API（例：`run_retry_due()`）**：現時点では`SchedulerEngine.run_due(jobs=[])`を流用している。「空リストを渡すこと」がRetry Runtimeの意味になっている点を将来解消する（v5.3.0 Future Architecture Consideration）
- [x] **Retry Runtime Loop Foundation（Loop Wrapperの新設、未配線）**：v5.5.0で実装済み。`RetryRuntimeOrchestrator.run_once()`を繰り返し呼び出すだけの薄いWrapper`RetryRuntimeLoop`（`src/retry_runtime_loop/`）を新設した。`run_once_fn` / `sleep_fn` / `should_continue_fn` / `interval_seconds`をConstructor Injectionで保持し、`run()`で`while should_continue_fn(): run_once_fn(); sleep_fn(interval_seconds)`を実行するだけのStateless Wrapperとし、Business Logicは一切持たない（`RetryManager` / `RetryQueueManager` / `RetryHistoryManager` / `RetryPolicy` / `RetryRuntimeOrchestrator` / `RetryCompositionRoot`のいずれもimportしない）。当初「Loop Foundation」は配線・運用まで見据えたものとして一度は見送りを検討したが、Business Logicを持たず`scripts/`への配線を伴わない未配線Foundationに限定すれば、v3.1.0・v3.3.0・v3.5.0・v5.1.0・v5.2.0と同型の「消費者不在の先行実装」パターンとして安全に導入できると判断し、Option A'として採用した（`docs/design/retry_runtime_loop_foundation.md`）。`scripts/run_retry_runtime.py` / `RetryRuntimeOrchestrator` / `RetryCompositionRoot`のいずれからも本Releaseでは配線しない。既存13パッケージはいずれも無改修
- [x] **`scripts/run_retry_runtime.py`への`RetryRuntimeLoop`配線（`--loop`対応、Retry Runtime Loop Wiring Foundation）**：v5.9.0で実装済み。`scripts/run_retry_runtime.py`へ`--loop`（`action="store_true"`）・`--interval-seconds`（`type=float`、`default=None`）を追加した。`--loop`省略時（デフォルト）は従来どおり1サイクルのみで終了する。`--interval-seconds`は`--loop`と併用時のみ有効とし、`--loop`なしでの指定・0以下の指定はいずれもCLIエラー（`parser.error()`、非0終了）とした。`--loop`指定時に省略した場合のデフォルトは60秒。`main()`内のローカル関数`run_cycle()`（`orchestrator.run_once(dry_run=args.dry_run)` → `print(format_summary(result))`）を既存`RetryRuntimeLoop`（v5.5.0）の`run_once_fn`として注入し、`sleep_fn=time.sleep` / `should_continue_fn=lambda: True`とあわせて構築した。Loop実行中の`KeyboardInterrupt`のみを`main()`内で捕捉し、短い終了メッセージを表示したうえで正常終了（exit code 0）とする一方、それ以外の例外はfail-fastのまま伝播させる。`src/retry_runtime_loop/` / `src/retry_runtime_orchestrator/` / `src/retry_composition/` / `RetryManager`（`retry_engine`）はいずれも無改修とし、本Releaseの変更対象を`scripts/run_retry_runtime.py`の1ファイルに限定した（`docs/design/retry_runtime_loop_wiring_foundation.md`）。これにより`retry_runtime_loop`（v5.5.0、消費者不在の先行実装）が初めて実際の消費者を持った
- [ ] **Exit Code設計の再検討**：Windows タスクスケジューラでの成否監視が実運用上必要になった時点で、`RetryRuntimeCycleResult`のどのフィールドをもって「成功」とみなすかを含めて独立Releaseとして検討する（v5.4.0時点では独自Exit Code体系を意図的に導入していない）
- [ ] **Summary Formatterクラスへの抽出**：JSON出力・Slack通知等、表示形式の複数化が必要になった時点で、`scripts/run_retry_runtime.py`の`format_summary()`のロジックをクラスへ抽出する（v5.4.0時点では関数による局所化のみ）
- [x] **Retry Runtime Lock Foundation（Daemon Foundationの前提）**：v6.0.0で実装済み。新規パッケージ`src/retry_runtime_lock/`（`RetryRuntimeLock`）を追加し、`os.open(O_CREAT | O_EXCL)`によるファイル存在ベースの排他制御で、同一Retry Runtimeプロセスの多重起動を防止できるようにした。`scripts/run_retry_runtime.py`は単発実行・`--loop`実行の全体を`with lock:`で包み、ロック取得済みの場合は`RetryCompositionRoot`等を一切構築せず`RetryRuntimeLockError`を専用に捕捉してexit code 1とする。`RetryCompositionRoot` / `RetryRuntimeOrchestrator` / `RetryRuntimeLoop` / `RetryManager`はいずれも無改修。Daemon化そのもの（バックグラウンド常駐・Windows Service化）ではなく、その前提となる最小Foundationと位置づけた（`docs/design/retry_runtime_lock_foundation.md`）
- [ ] **Stale Lock Recovery Foundation**：プロセスが強制終了（`taskkill /F`・電源断等）した場合にロックファイル（v6.0.0）が残存する問題への対応（PID生存確認、または最終更新時刻に基づくタイムアウト判定）
- [x] **Graceful Shutdown Foundation**：v6.1.0で実装済み。新規パッケージ`src/retry_runtime_shutdown/`（`RetryRuntimeShutdown`）を追加し、`--loop`実行時のみSIGINT・SIGTERM（POSIX）・SIGBREAK（Windows）へハンドラを登録するようにした。シグナル受信時は実行中サイクルを中断せず、フラグを立てるのみとする（`RetryRuntimeLoop`の既存DIシーム`should_continue_fn` / `sleep_fn`をそのまま利用し、`RetryRuntimeLoop`自体は無改修）。`sleep_fn`を`RetryRuntimeShutdown.interruptible_sleep`（ポーリング間隔0.5秒単位で早期return）に差し替えたことで、シグナル受信からプロセス終了までの間、旧来の`interval_seconds`（デフォルト60秒）を待たされる問題を解消した。Windowsでの強制終了（`taskkill /F`等）は`TerminateProcess`を用いるため本機構でも検知不可能である点は設計時から既知の制約として明記している。`RetryCompositionRoot` / `RetryRuntimeOrchestrator` / `RetryRuntimeLoop` / `RetryManager` / `RetryRuntimeLock`（v6.0.0）はいずれも無改修（`docs/design/retry_runtime_graceful_shutdown_foundation.md`）
- [ ] **Windows Service Foundation / 実Daemon化**：実際にバックグラウンドプロセスとして常駐させる仕組み（Runtime Lock（v6.0.0）・Graceful Shutdown（v6.1.0）が前提となる）
- [x] **Structured Loop Logging Foundation**：v6.2.0で実装済み。新規パッケージ`src/retry_runtime_logging/`（`RetryRuntimeCycleLogger`）を追加し、Retry Runtimeの1サイクル分の実行結果をJSON Lines形式で`.run/retry_runtime_log.jsonl`へ1レコード追記するだけの独立コンポーネントとした。記録内容はサイクル番号（`scripts/run_retry_runtime.py`の`run_cycle()`クロージャがローカル変数`cycle_count`として保持。`RetryRuntimeLoop`自体は無改修のままStateless性を維持）・タイムスタンプ（ISO8601、UTC）・`--dry-run`指定有無・`RetryRuntimeCycleResult`由来の各件数に限定し、JSON Schemaを本Releaseで固定（将来はフィールド追加のみを基本方針とする）した。ログ書き込み失敗（`OSError`）時は例外を送出せずstderrへWARNINGを出力し処理を継続するベストエフォート方針とした（Exit Code Policyとは区別）。`RetryRuntimeLock` / `RetryRuntimeShutdown` / `RetryRuntimeLoop` / `RetryRuntimeOrchestrator` / `RetryManager` / `RetryCompositionRoot`はいずれも無改修。Architecture Design段階で候補比較した「Stale Lock Recovery Foundation」は、stale判定が`RetryRuntimeLock`の責務に本質的に食い込み「Lockへの責務追加禁止」制約と構造的に衝突するため見送った（`docs/design/retry_runtime_structured_loop_logging_foundation.md`）
- [ ] **Retry Metrics / Monitoring**（再掲、v6.2.0で入力データが整備された）：v6.2.0の`retry_runtime_log.jsonl`を入力データとして、Retry実行の成功率・試行回数分布・Queue滞留時間等を集計・可視化する仕組み。ログローテーション・集計・Dashboard化はv6.2.0では意図的に対象外としており本項目で別途検討する

---

## 長期ビジョン — AI Blog Operator（Release 2.x, 予定）

> 旧ROADMAPでは「v2.0」という名称でこのビジョンを表していましたが、
> 実際にリリースされた `v2.0.0`（AI Agent Foundation）は判断レイヤーの骨組みのみであり、
> 本ビジョン全体を指すものではありません。混同を避けるため、
> バージョン番号を含まない名称に変更しました（v2.1.0 Documentation Foundationにて整理）。

- [ ] 半自律的なブログ運営支援（人間の承認ゲート付き）
- [ ] Agentによる各Workflowステップの実行要否判断（News Agent / Workflow Trigger Agentの先の姿）
- [ ] Windows タスクスケジューラによる定時自動実行
- [ ] 重要度別の公開制御（S→即時公開・A→予約投稿・B→下書き）

---

## 完了済み（v1.0）

- [x] RSS取得サマリー表示（収集ソース別の件数・成否を一覧表示）
- [x] Steam Newsのフィード追加
- [x] v1.0 リリース・動作確認

---

## 完了済み（v0.9）

- [x] RSSニュース収集（15サイト）
- [x] キーワードフィルター
- [x] Claude API重要度判定（S / A / B）
- [x] 日本語記事・SEOタイトル・X投稿文の生成
- [x] Markdownファイル保存
- [x] JSON抽出の安定化
- [x] 重複ニュース排除（`duplicate_filter.py`）
