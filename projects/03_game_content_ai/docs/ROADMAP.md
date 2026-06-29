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

## v1.7.0 — Automation Foundation（予定）

- [ ] 権利確認済み画像の WordPress メディアアップロード（`/wp-json/wp/v2/media`）
  - `image_terms_confirmed == True` の画像のみ対象（`MediaUploader` クラスとして実装）
  - `featured_media` に media_id を設定
- [ ] AI生成画像の組み込み検討
- [ ] 内部リンク候補の自動提示

---

## v2.0 — AI Blog Operator（予定）

- [ ] Windows タスクスケジューラによる定時自動実行
- [ ] 重要度別の公開制御（S→即時公開・A→予約投稿・B→下書き）
- [ ] 半自律的なブログ運営支援（人間の承認ゲート付き）

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
