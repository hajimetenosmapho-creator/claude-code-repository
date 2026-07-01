# v1.18.0 AI Publish Foundation 設計書

作成日：2026-07-01（v2.1.0 Documentation Foundationにて事後作成）

> 本設計書は実装（2026-06-30, commit `22e2407`）から遅れて作成されたものです。
> 内容はソースコードのDocstring・実装から再構成しています。

---

## 1. Goal

v1.17.0のレビューで「採用（adopted）」と判定されたリライト結果を、WordPressへ**自動で下書き投稿**する基盤を作る。
AI改善サイクル（Improvement→Review→Rewrite→Review）の最終出口として、人が確認しやすい形でWordPress管理画面に反映する。

---

## 2. Background

### 現状の問題点

- v1.14.0〜v1.17.0でAIによる改善提案・リライト・レビューまでは自動化できたが、
  最終的にWordPressへ反映する作業は手動のままだった。
- 手動反映は工数がかかり、採用済みリライトが放置されるリスクがある。

### v1.18.0 が解決すること

- 採用済みリライトを重複チェックした上でWordPress REST APIへ新規下書きとして投稿する。
- **投稿は常にdraft固定**とし、誤って公開されることを防ぐ（v1.1.0以来の一貫した方針）。

---

## 3. Scope

### 実装対象

- `AiPublishConfig`：設定値管理（`AI_PUBLISH_ENABLED`、WordPress認証情報）
- `WordPressDraftClient` / `NullWordPressDraftClient`：WordPress新規下書き投稿
- `AiPublishRepository`：採用済みレビュー・リライト結果の読み込み、重複投稿防止
- `AiPublishResult`：投稿結果のデータモデル
- `AiPublishReportBuilder`：Markdownレポート生成
- `AiPublishService` / `NullAiPublishService`：上記を統合するサービス層
- `scripts/run_ai_publish.py`

### 対象外（Non Goalへ）

- 投稿結果のレビュー（v1.19.0）
- 既存記事のUPDATE（PATCH）：本バージョンはPOST（新規作成）のみ

---

## 4. Non Goal

- WordPressへの`publish`（公開）は行わない。ステータスは常に`"draft"`にハードコードし、外部から変更できないようにする。
- 既存投稿の更新は行わない。新規スラッグ（`{article_id}-rewrite-{YYYYMMDD}`）で別記事として投稿する。

---

## 5. User Workflow

### Before（v1.17.0）

- レビューで「採用」と判定されたリライト案があっても、WordPressへの反映はブロガーが手動で行う必要があった。

### After（v1.18.0）

1. ブロガーが `python scripts/run_ai_publish.py` を実行する
2. `AiPublishService` が採用済み・未投稿のレビューを抽出し、WordPressへ下書き投稿する
3. 投稿結果が `outputs/ai_publishes/` にJSON保存され、Markdownレポートが `outputs/ai_publish_reports/` に生成される
4. ブロガーがWordPress管理画面で下書きを確認し、公開ボタンを押すかを判断する

---

## 6. System Workflow

```
AiPublishRepository.load_adopted_reviews()   採用済みレビューを読み込む（RewriteReviewRepository経由）
  → _dedup_by_article_id()                   同一記事は最新レビューのみ残す
  → filter_unpublished()                     未投稿のみに絞り込む
  → load_rewrite_by_article_id()             対応するリライト本文を取得
  → WordPressDraftClient.post_draft()        WordPressへ新規下書き投稿（status="draft"固定）
  → AiPublishResult 生成 → AiPublishRepository.save()
  → AiPublishReportBuilder.build()           Markdownレポート生成
```

投稿失敗（`RuntimeError`）・スキップ（認証情報なし）・成功の3パターンをすべて`AiPublishResult`として記録し、処理を継続する。

---

## 7. Data Model

### `AiPublishResult`（`ai_publish_result.py`）

| フィールド | 型 | 内容 |
|---|---|---|
| `article_id` | `str` | 元記事の識別子（slug） |
| `source_review_status` | `str` | 採用時のレビュー状態（例：`"adopted"`） |
| `source_rewrite_created_at` | `datetime \| None` | 元になったRewriteResultの生成日時 |
| `wp_post_id` / `wp_draft_slug` / `wp_edit_url` / `wp_draft_permalink` | | WordPress投稿結果 |
| `success` | `bool` | 投稿が成功したか |
| `skipped` | `bool` | `NullWordPressDraftClient`によりスキップされたか |
| `skip_reason` / `error_message` | `str \| None` | スキップ理由・失敗理由 |

`success=False`には「スキップ」と「エラー」の2ケースがあり、`skipped`フィールドで区別する。

---

## 8. Directory Structure

```
src/ai/
├── ai_publish_config.py             # AiPublishConfig
├── wordpress_draft_client.py        # WordPressDraftClient / NullWordPressDraftClient
├── ai_publish_repository.py         # AiPublishRepository
├── ai_publish_result.py             # AiPublishResult
├── ai_publish_report_builder.py     # AiPublishReportBuilder
└── ai_publish_service.py            # AiPublishService / NullAiPublishService

scripts/
└── run_ai_publish.py

outputs/
├── ai_publishes/                    # AiPublishResult JSON
└── ai_publish_reports/              # Markdownレポート
```

---

## 9. Module Design

### `AiPublishConfig`（`ai_publish_config.py`）

環境変数名は `rewrite_config.py` と統一されている（設計上の意図として明記されている）：

```
AI_PUBLISH_ENABLED
WORDPRESS_URL / WORDPRESS_USERNAME / WORDPRESS_APP_PASSWORD
```

`is_ready()` は「`enabled=true`」かつ「WordPress認証情報3点が揃っている」の両方を要求する（4条件のAND）。

### `WordPressDraftClient` / `NullWordPressDraftClient`（`wordpress_draft_client.py`）

- `post_draft(title, content, slug, excerpt=None) -> dict`：`POST /wp-json/wp/v2/posts` を実行。`status`は`"draft"`にハードコードされ、外部インターフェースからは変更できない
- 既存記事のUPDATE（PATCH）は行わない（POST=新規作成のみ）。禁止事項として明記されている
- `NullWordPressDraftClient.post_draft()` は `{"skipped": True, "reason": ...}` を返し、`AiPublishService`側でスキップとして解釈される

### `AiPublishRepository`（`ai_publish_repository.py`）

- 内部で `RewriteReviewRepository`（v1.17.0）を利用し、レビュー・リライト結果を読み込む
- `outputs/ai_publishes/` のみを自身で読み書きする（WordPress API呼び出しは行わない）
- 重複投稿防止：`_dedup_by_article_id()`（同一記事の最新レビューのみ）＋ `filter_unpublished()`（未投稿のみ）の2段階フィルタ

### `AiPublishService`（`ai_publish_service.py`）

- 新規スラッグは `{article_id}-rewrite-{YYYYMMDD}` 形式で生成し、元記事と重複しないようにする
- `run(article_id=None)`：全件または指定記事のみ処理し、Markdownレポートのパスを返す
- `get_results(article_id=None)`：投稿処理を行わず、保存済み結果のみを返す

---

## 10. Configuration Design

`.env.example` への追記は本バージョンでは未実施（`AI_PUBLISH_*` 系変数は `.env.example` に反映されていない）。

```
AI_PUBLISH_ENABLED=false
WORDPRESS_URL=
WORDPRESS_USERNAME=
WORDPRESS_APP_PASSWORD=
```

### Configuration First の設計意図

`AI_PUBLISH_ENABLED=false` または WordPress認証情報が1つでも欠けている場合、`NullAiPublishService`を返す。4条件すべてを`AiPublishConfig.is_ready()`でAND判定することで、「有効化したのに認証情報が足りず実行時エラーになる」事態を防いでいる。

---

## 11. WordPress との関係（v1.1.0 WordPressOutputとの違い）

| | v1.1.0 `WordPressOutput` | v1.18.0 `WordPressDraftClient` |
|---|---|---|
| 用途 | 通常の記事投稿フロー（`main.py`） | AI改善サイクルの最終出口 |
| 環境変数 | `WP_SITE_URL` / `WP_USERNAME` / `WP_APP_PASSWORD` | `WORDPRESS_URL` / `WORDPRESS_USERNAME` / `WORDPRESS_APP_PASSWORD` |
| ステータス | `PublishingConfig`により`draft`/`pending`等を選択可 | 常に`draft`固定（変更不可） |

同じWordPressサイトを両方の機能で使う場合、`.env`に両方の変数セットを設定する必要がある点に注意（v1.16.0設計書にも同様の注記あり）。

---

## 12. Error Handling

| ケース | 対応 |
|---|---|
| WordPress API失敗（`RuntimeError`） | `[PUBLISH WARNING]`出力、`success=False`の`AiPublishResult`を保存し処理継続 |
| 対応するリライト結果が見つからない | `success=False`（`error_message="リライト結果が見つかりません"`） |
| 認証情報未設定・機能無効 | `NullWordPressDraftClient`が`skipped=True`を返す |
| レポート保存失敗（`OSError`） | `[PUBLISH WARNING]`出力、`None`を返す（投稿処理自体は継続済み） |

---

## 13. AI Publish Review Foundation との関係（v1.19.0への引き継ぎ）

`AiPublishResult`（JSON保存済み）が、v1.19.0 `AiPublishReviewService` の入力となる。
`AiPublishReviewService`はWordPress APIを呼び出さず、投稿結果の確認・レポート化のみを行う（非破壊）。

---

## 14. Future Extensions

- Phase 2：投稿結果のレビュー（v1.19.0で実装済み）
- Phase 3：6ステップ全体をオーケストレーションする `WorkflowRunner`（v1.20.0で実装済み）
- Phase 4：`draft`以外のステータス（`pending`等）への対応（未着手。現状はdraft固定）
- Phase 5：Agent層（v2.0.0）による「公開を実行すべきか」の自動判断（未着手）

---

## 15. Definition of Done

### コード

- [x] `AiPublishService` 一式の実装（draft固定・重複投稿防止を含む）

### テスト

- [x] `tests/test_e2e_v1_18_0_ai_publish_foundation.py`: 109/109 PASS

### ドキュメント

- [x] 本設計書（v2.1.0にて事後作成）
- [x] CHANGELOG.md / ROADMAP.md への記載

### リリース

- [x] 2026-06-30 コミット済み（`22e2407`）
