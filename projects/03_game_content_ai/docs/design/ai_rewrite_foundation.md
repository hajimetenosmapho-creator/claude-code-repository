# v1.16.0 AI Rewrite Foundation 設計書

作成日：2026-07-01（v2.1.0 Documentation Foundationにて事後作成）

> 本設計書は実装（2026-06-30, commit `940bd82`）から遅れて作成されたものです。
> 内容はソースコードのDocstring・実装から再構成しています。

---

## 1. Goal

v1.14.0で生成した改善提案（`ImprovementSuggestion`）を元に、Claude APIで記事本文を実際に書き換え、
「改善版記事のドラフト（Rewrite Draft）」を生成する基盤を作る。

v1.16.0では書き換え結果の**保存**までを行い、WordPressへの反映は行わない（反映はv1.18.0 AI Publish Foundationで実装）。

---

## 2. Background

### 現状の問題点

- v1.14.0/v1.15.0で「何を改善すべきか」は提案できるようになったが、実際に記事を書き換える手段がなかった。
- 改善提案をブロガー自身が手作業で反映するのは工数がかかる。

### v1.16.0 が解決すること

- `ImprovementSuggestion` と元記事本文を入力とし、Claude APIで改善版記事を生成する。
- 生成結果は元記事を上書きせず、`outputs/ai_rewrites/` にMarkdown＋JSONとして保存し、人による確認（v1.17.0のレビュー）を挟めるようにする。

---

## 3. Scope

### 実装対象

- `ArticleProvider`（ABC）/ `WordPressArticleProvider` / `NullArticleProvider`：元記事本文の取得
- `RewriteConfig`：設定値管理
- `RewritePromptBuilder` / `RewriteParser`：プロンプト生成・レスポンス解析
- `RewriteRepository`：結果の保存
- `RewriteService` / `NullRewriteService`：上記を統合するサービス層
- `scripts/run_ai_rewrite.py`

### 対象外（Non Goalへ）

- リライト結果のレビュー・差分サマリー生成（v1.17.0）
- WordPressへの投稿（v1.18.0）

---

## 4. Non Goal

- 元記事（WordPress上の投稿）は変更しない。あくまで下書きとして別ファイルに保存する。
- `main.py`（投稿処理）から呼び出さない。v1.14.0と同様、独立したバッチスクリプトとして実行する。

---

## 5. User Workflow

### Before（v1.15.0）

- 改善提案のレポートは読めるが、実際の書き換え文章を作るのはブロガー自身の作業だった。

### After（v1.16.0）

1. ブロガーが `python scripts/run_ai_rewrite.py` を実行する
2. `RewriteService` が改善提案ごとに元記事を取得し、Claude APIで改善版を生成する
3. 結果が `outputs/ai_rewrites/` にMarkdown（読む用）＋JSON（後続処理用）で保存される
4. ブロガーが内容を確認し、必要であれば手動でWordPressに反映する（自動反映はv1.18.0）

---

## 6. System Workflow

```
ImprovementSuggestion（v1.14.0の出力）
  → ArticleProvider.fetch(article_id, permalink)   元記事本文を取得（失敗時は空文字列）
  → RewritePromptBuilder.build(suggestion, content) プロンプトを組み立てる
  → ClaudeClient.send()                             Claude API へ送信
  → RewriteParser.parse()                           RewriteResult に変換
  → RewriteRepository.save()                        Markdown + JSON を保存
```

### ClaudeClientの再利用について

`ClaudeClient` は `AiImprovementConfig` を受け取る設計になっている（v1.14.0時点の設計）。
`RewriteService.from_env()` は `ClaudeClient` 自体を変更せず、`RewriteConfig` の値から `AiImprovementConfig` を組み立てて渡すことで、既存コードとの後方互換性を維持しながら再利用している。

### ArticleProviderの選択

`RewriteService.from_env()` は、WordPress認証情報（後述）が揃っている場合は `WordPressArticleProvider` を、
未設定の場合は `NullArticleProvider`（常に空文字列を返す）を選択する。`article_content=""` でも処理は継続する。

---

## 7. Data Model

### `RewriteResult`（`rewrite_result.py`）

| フィールド | 型 | 内容 |
|---|---|---|
| `article_id` | `str` | 記事識別子（slug） |
| `title` | `str` | 記事SEOタイトル |
| `permalink` | `str \| None` | WordPress公開URL |
| `prompt_version` | `str` | 使用したプロンプトバージョン |
| `original_content` | `str` | 取得した元記事本文（空文字＝取得不可） |
| `rewrite_draft` | `str` | Claudeが生成した改善版記事（Markdown） |
| `improvement_summary` | `str` | 変更点の要約 |
| `changes` | `list[str]` | 主な変更一覧 |
| `raw_response` | `str` | Claudeの生レスポンス |
| `created_at` | `datetime` | 生成日時 |
| `success` | `bool` | 生成が成功したか |
| `error_message` | `str \| None` | 失敗時の理由 |

`success=False` の場合、`rewrite_draft` は空文字列のまま保存される（`RewriteReviewService`側で失敗を判別できる）。

---

## 8. Directory Structure

```
src/ai/
├── rewrite_config.py           # RewriteConfig
├── article_provider.py         # ArticleProvider / WordPressArticleProvider / NullArticleProvider
├── rewrite_prompt_builder.py   # RewritePromptBuilder
├── rewrite_parser.py           # RewriteParser
├── rewrite_repository.py       # RewriteRepository
├── rewrite_result.py           # RewriteResult
├── rewrite_service.py          # RewriteService / NullRewriteService
└── prompts/
    └── v1_rewrite.py           # プロンプトテンプレート（v1）

scripts/
└── run_ai_rewrite.py

outputs/
└── ai_rewrites/                # リライト結果（Markdown + JSON）の保存先
```

---

## 9. Module Design

### `RewriteConfig`（`rewrite_config.py`）

| フィールド | デフォルト |
|---|---|
| `enabled` | `False`（`AI_REWRITE_ENABLED`） |
| `model` | `"claude-sonnet-4-6"` |
| `max_articles` | `5` |
| `output_dir` | `"outputs/ai_rewrites"` |
| `wordpress_url` / `wordpress_username` / `wordpress_app_password` | `None` |

`is_ready()` は `enabled and bool(api_key)`。`has_wordpress_credentials()` は3つのWordPress設定が揃っているかを判定する。

### `ArticleProvider`（`article_provider.py`）

Dependency Injection / Open-Closed Principleに基づき、ABCとして定義。`RewriteService`は具体的な取得元を知らない。

- `WordPressArticleProvider`：`GET {url}/wp-json/wp/v2/posts?slug={id}` をBasic認証で呼び出し、`content.rendered` を取得。失敗時は`[REWRITE WARNING]`を出して空文字列を返す（例外を外に伝播させない）
- `NullArticleProvider`：認証情報未設定時のダミー実装。常に空文字列を返す

### `RewriteService` / `NullRewriteService`（`rewrite_service.py`）

- `rewrite(suggestion)`：1件処理。元記事取得→プロンプト生成→API送信→解析→保存。いずれかで例外が起きても`success=False`の`RewriteResult`を保存して返す（処理継続）
- `rewrite_batch(suggestions, max_articles=None)`：複数件をまとめて処理。件数上限あり

---

## 10. Configuration Design

`.env.example` には本バージョンでの追記はない（`AI_REWRITE_*` の環境変数は `RewriteConfig.from_env()` 内でのみ定義されており、`.env.example` への反映は本設計書作成時点（v2.1.0）でも未実施）。

```
AI_REWRITE_ENABLED=false
# AI_REWRITE_MODEL=claude-sonnet-4-6
# AI_REWRITE_PROMPT_VERSION=v1
# AI_REWRITE_MAX_ARTICLES=5
# AI_REWRITE_OUTPUT_DIR=outputs/ai_rewrites
WORDPRESS_URL=
WORDPRESS_USERNAME=
WORDPRESS_APP_PASSWORD=
```

> **注意（本設計書作成時に判明した点）**：`RewriteConfig` が読む WordPress 認証用の環境変数名は
> `WORDPRESS_URL` / `WORDPRESS_USERNAME` / `WORDPRESS_APP_PASSWORD` であり、
> v1.1.0 `WordPressOutput` が読む `WP_SITE_URL` / `WP_USERNAME` / `WP_APP_PASSWORD` とは**別の変数名**になっている。
> 同じWordPressサイトに接続する場合、`.env` に両方を設定する必要がある。今後の統一を検討課題として残す。

---

## 11. AI Improvement Foundation との関係

- 入力：`ImprovementSuggestion`（v1.14.0の出力）
- `RewriteService` は改善提案の生成方法には関知せず、受け取った`ImprovementSuggestion`をそのままプロンプトに利用する

---

## 12. Error Handling

| ケース | 対応 |
|---|---|
| 元記事取得失敗（WordPress APIエラー・認証情報なし） | `[REWRITE WARNING]`出力、空文字列で処理継続 |
| Claude API呼び出し失敗 | `ClaudeClient`側で`[AI WARNING]`、空文字列を返す |
| JSON解析失敗・その他例外 | `success=False`の`RewriteResult`を生成し保存、処理継続 |
| `AI_REWRITE_ENABLED=false` | `NullRewriteService`がno-opで動作 |

---

## 13. AI Publish Foundation との関係（v1.18.0への引き継ぎ）

`RewriteResult`（`success=True`かつv1.17.0レビューで`adopted`と判定されたもの）が、v1.18.0 `AiPublishService` の入力となる。
`RewriteService`自体はWordPressへの投稿を一切行わない（投稿は下書き取得のみに限定された責務）。

---

## 14. Future Extensions

- Phase 2：リライト結果のレビュー・差分サマリー生成（v1.17.0で実装済み）
- Phase 3：レビュー済みリライトの自動公開（v1.18.0で実装済み）
- Phase 4：`WORDPRESS_URL`系と`WP_SITE_URL`系の環境変数統一（未着手）
- Phase 5：Agent層（v2.0.0）による「リライトを実行すべきか」の自動判断（未着手）

---

## 15. Definition of Done

### コード

- [x] `ArticleProvider` / `RewriteService` 一式の実装

### テスト

- [x] `tests/test_e2e_v1_16_0_ai_rewrite_foundation.py`: 81/81 PASS

### ドキュメント

- [x] 本設計書（v2.1.0にて事後作成）
- [x] CHANGELOG.md / ROADMAP.md への記載

### リリース

- [x] 2026-06-30 コミット済み（`940bd82`）
