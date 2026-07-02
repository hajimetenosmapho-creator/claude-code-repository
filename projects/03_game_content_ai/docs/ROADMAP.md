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

## v2.x 以降の候補（未着手）

- [ ] Windows タスクスケジューラによる定時自動実行（Scheduler Agent）
- [ ] 重要度別の公開制御（S→即時公開・A→予約投稿・B→下書き）

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
