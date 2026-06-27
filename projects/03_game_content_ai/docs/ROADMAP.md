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

## v1.4.0 — アイキャッチ画像WordPress自動アップロード（予定）

- [ ] `src/outputs/wordpress_media.py` 新規作成（画像ダウンロード・アップロード）
- [ ] WordPress `/wp-json/wp/v2/media` へのアップロード実装
- [ ] 投稿 payload に `featured_media` を設定
- [ ] 著作権確認済み画像のみを対象とする仕組みの検討
- [ ] アップロード失敗時のフォールバック処理

---

## v1.5.0 — WordPress出力品質向上（予定）

- [ ] Markdown → HTML変換（記事本文をWordPressで正しく表示）

---

## v2.x — 自動化・品質向上

- [ ] アイキャッチ画像のALTテキスト自動生成
- [ ] WordPress自動投稿（下書き → 公開の自動化）
- [ ] Windows タスクスケジューラによる定時実行対応

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
