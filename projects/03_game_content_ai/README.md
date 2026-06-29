# 03 ゲームニュース記事生成AI

国内外のゲームニュースをRSSで自動収集し、Claude AIが重要度を判定・日本語記事下書き・SEOタイトル・X投稿文を生成して、Markdownファイルとして保存するツールです。

**ブログ名**：KAORUの部屋  
**ステータス**：v1.5.0 Publishing Enhancement（slug生成・投稿ログ改善）

---

## 実装済み機能

### v1.5.0 — Publishing Enhancement（2026-06-30 完了）

- **slug の自動生成と WordPress への設定**（v1.5.0 追加）
  - `src/slug_generator.py` が SEO タイトルの ASCII 英数字を抽出してケバブケース slug を生成
  - 例：`【速報】PS6はNintendo Switch型に？` → `ps6-nintendo-switch-20260630`
  - 英字が取れない場合は `article-YYYYMMDD` にフォールバック
  - WordPress 投稿 payload の `slug` フィールドに自動設定
  - Markdown YAML front matter にも記録
- **WordPress 投稿ログ改善**（v1.5.0 追加）
  - 投稿 ID・実際に使用された slug・編集 URL をコンソール表示
- **実行時間表示**（v1.5.0 追加）
  - 完了サマリーに `実行時間: XX.X秒` を表示

### v1.4.0 — SEO Foundation（2026-06-30 完了）

- **excerpt（抜粋）の自動生成と記録**（v1.4.0 追加）
  - 記事本文の先頭段落からMarkdown記法を除いてルールベースで生成（API追加なし）
  - WordPress投稿時に `excerpt` フィールドとして送信
  - Markdownファイルの YAML front matter に `excerpt` / `meta_description` として記録
- **ImageResolver 導入**（v1.4.0 追加）
  - `src/image_resolver.py` 新設（画像候補URL選択の責務を main.py から分離）
  - `resolve_featured_image(item)` が image_candidates の先頭URLを返す
  - v1.5.0以降でデフォルト画像・権利確認済み画像・AI生成画像への拡張に対応可能

### v1.3.0 — アイキャッチ画像URL抽出対応

- **RSSからアイキャッチ画像候補URLを自動抽出**（v1.3.0 追加）
  - `src/image_extractor.py` が media:thumbnail / enclosures / media:content を順に探索
  - 取得した画像URLは `NewsItem.image_candidates` に格納
  - Markdownファイルの末尾に `<!-- アイキャッチ候補: URL -->` として記録
  - 画像が見つからない場合はエラーなし・コメントなしで正常終了
  - 著作権リスクのためWordPressへの自動アップロードは行わない（v1.5.0 以降で検討）

### v1.2.0 — カテゴリ・タグ自動設定対応

- **WordPress投稿時のカテゴリ・タグ自動付与**（v1.2.0 追加）
  - カテゴリ：「ゲームニュース」を固定で付与
  - タグ：重要度に応じて自動設定（S→注目 / A→速報 / B→なし）
  - IDは `src/outputs/taxonomy_config.py` で一元管理（WordPressで確認したIDを設定）
  - ID未設定（0のまま）の場合はカテゴリ・タグを省略して投稿

### v1.1.0 — WordPress下書き投稿対応

- **WordPress REST API による下書き投稿**（v1.1.0 追加）
  - `.env` に WordPress設定を追加すると有効になる
  - 未設定の場合はMarkdown保存のみ動作（スキップされる）
  - 投稿状態は `draft`（下書き）固定（誤公開防止）
  - 認証：Application Password

### v1.0.0 — MVP

- 国内外16サイトのRSSからゲームニュースを自動収集
- キーワードフィルターによる事前スクリーニング（Claude API使用量を削減）
- Claude AIによる重要度判定（S / A / B / なし）
- 重要度に応じた記事下書きの自動生成
  - S評価：2000文字以上の詳細記事
  - A評価：800〜1500文字の通常記事（最大5件）
  - B評価：記事化しない（候補ファイルに保存）
- SEOタイトルの自動生成
- X（旧Twitter）投稿文の自動生成
- `output/` フォルダへのMarkdownファイル保存

---

## 対応RSSサイト（16サイト）

### 日本語

| サイト | 言語 |
|--------|------|
| 4Gamer | 日本語 |
| Game*Spark | 日本語 |

### 公式

| サイト | 言語 |
|--------|------|
| PlayStation公式 | 日本語 |
| Nintendo公式 | 日本語 |
| Xbox公式 | 英語 |
| Steam | 日本語 |

### 総合英語

| サイト | 言語 |
|--------|------|
| IGN | 英語 |
| GameSpot | 英語 |
| Eurogamer | 英語 |
| Gematsu | 英語 |
| VGC | 英語 |
| Insider Gaming | 英語 |
| PC Gamer | 英語 |

### プラットフォーム特化

| サイト | 言語 |
|--------|------|
| Nintendo Life | 英語 |
| Push Square | 英語 |
| Pure Xbox | 英語 |

---

## セットアップ

```bash
# 仮想環境を作成・有効化
python -m venv venv
venv\Scripts\activate   # Windows

# 依存パッケージをインストール
pip install -r requirements.txt

# 環境変数の設定
copy .env.example .env
# .env を開いて以下を設定する
#   ANTHROPIC_API_KEY  … Claude API キー（必須）
#   WP_SITE_URL        … WordPressサイトURL（WordPress投稿を使う場合）
#   WP_USERNAME        … WordPressユーザー名（WordPress投稿を使う場合）
#   WP_APP_PASSWORD    … Application Password（WordPress投稿を使う場合）
```

> **注意：** `.env` ファイルは `.gitignore` で除外されています。APIキーをコミットしないよう注意してください。

---

## 実行方法

```bash
# 通常動作（S全件 + A最大5件）
python main.py

# テスト用：先頭N件のみ生成
python main.py --max-articles 3
```

生成されたMarkdownファイルは `output/` フォルダに保存されます。

---

## 今後の予定

### v1.5.0 — Publishing Enhancement

- slug 生成と WordPress への送信
- WordPress 投稿後 URL の取得・X投稿文への自動埋め込み
- 実行ログのファイル出力
- ImageResolver 拡張（デフォルト画像対応）

### v1.6.0 — Image Pipeline

- 権利確認済み画像の WordPress メディアアップロード
- `featured_media` 設定

### v2.0 — AI Blog Operator

- Windowsタスクスケジューラによる定時自動実行
- 重要度別の公開制御（S→公開・A→予約・B→下書き）
- 半自律的なブログ運営支援
