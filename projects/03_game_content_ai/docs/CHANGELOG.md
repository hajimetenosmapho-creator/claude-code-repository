# CHANGELOG

このファイルはプロジェクトの変更履歴を記録します。
フォーマットは [Keep a Changelog](https://keepachangelog.com/ja/) に準拠。

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
