# CHANGELOG

このファイルはプロジェクトの変更履歴を記録します。
フォーマットは [Keep a Changelog](https://keepachangelog.com/ja/) に準拠。

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
