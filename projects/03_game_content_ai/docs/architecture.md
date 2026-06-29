# 出力アーキテクチャ設計

作成日：2026-06-26  
更新日：2026-06-30（v1.6.0 — Image Pipeline・featured_media_id 追加）

---

## 背景・目的

v1.0 では `main.py` に `_save_as_markdown()` が直書きされており、
出力先を追加するたびに `main.py` を修正する必要があった。

WordPress REST API 連携（v1.x）を追加するにあたり、
「どこへ出力するか」を差し替えやすい構造へ変更する。

---

## 現在（v1.0）の構造

```
main.py
  └─ _save_as_markdown()  ← Markdownへの保存処理が直書き
```

---

## 変更後（v1.1〜）の構造

```
main.py
  └─ output_manager.save_all(article)
       └─ OutputManager
            ├─ MarkdownOutput     ← v1.1 実装済み
            ├─ WordPressOutput    ← v1.1 実装済み
            ├─ NotionOutput       ← 将来
            └─ DiscordOutput      ← 将来
```

`main.py` は「何を出力するか（ArticleData）」だけを知り、
「どこへ出力するか」は `OutputManager` に委ねる。

---

## ディレクトリ構成

```
src/
├── image_extractor.py       # RSSエントリーから画像URL候補を抽出（v1.3 追加）
├── image_resolver.py        # アイキャッチ画像候補URLを解決（v1.4 追加）
├── slug_generator.py        # WordPress slug を生成（v1.5 追加）
└── outputs/
    ├── __init__.py          # OutputManager, MarkdownOutput, ArticleData を公開
    ├── base.py              # ArticleData dataclass / BaseOutput 抽象クラス
    ├── manager.py           # OutputManager
    ├── markdown_output.py   # MarkdownOutput（実装済み）
    ├── taxonomy_config.py   # カテゴリ・タグIDの設定（v1.2 追加）
    └── wordpress_output.py  # WordPressOutput（v1.1 実装済み）
```

---

## 各クラスの責務

### ImageResolver（`image_resolver.py`）（v1.4 追加）

アイキャッチ画像候補URLと WordPress media_id を解決するモジュール。

| 関数 | 役割 |
|------|------|
| `resolve_featured_image(item)` | NewsItem から使用する画像URLを1件選んで返す（Markdown記録用） |
| `resolve_media_id(item, default_media_id)` | WordPress に設定する featured_media の ID を返す（v1.6 追加） |

`resolve_media_id()` は v1.6.0 では `image_terms_confirmed == False` のため常に `default_media_id` を返す。v1.7.0 以降で `True` の場合に `MediaUploader` 経由でアップロード結果の ID を返す拡張ポイントとして設計。

### ArticleData（`base.py`）

記事生成結果をまとめて出力処理に渡すデータクラス。

| フィールド | 型 | 内容 |
|-----------|-----|------|
| `item` | `NewsItem` | 元ニュース情報（タイトル・URL・ソース等） |
| `importance` | `str` | 重要度（S / A / B） |
| `seo_title` | `str` | AIが生成したSEOタイトル |
| `article_body` | `str` | AIが生成した記事本文 |
| `x_post` | `str` | AIが生成したX投稿文 |
| `featured_image_url` | `str` | アイキャッチ画像候補URL（v1.3 追加、空文字 = なし） |
| `excerpt` | `str` | WordPress抜粋・Markdown記録用（v1.4 追加、空文字 = なし） |
| `meta_description` | `str` | 将来のSEOプラグイン連携用（v1.4 追加、現在はexcerptと同値） |
| `slug` | `str` | WordPress slug（v1.5 追加、空文字 = なし） |
| `featured_media_id` | `int` | WordPress media_id（v1.6 追加、0 = アイキャッチなし） |

### BaseOutput（`base.py`）

全出力クラスの抽象基底クラス。

| メソッド | 返り値 | 役割 |
|---------|-------|------|
| `save(article)` | `str` | 記事を保存・投稿する。保存先を示す文字列を返す |
| `is_available()` | `bool` | この出力先が利用可能かを返す（APIキー不足などを検知） |

### MarkdownOutput（`markdown_output.py`）

`output/` フォルダへのMarkdownファイル保存を担う。
v1.0 の `_save_as_markdown()` をクラスとして移植したもの。
`is_available()` は常に `True`（ディスク書き込みは常に可能とみなす）。

### OutputManager（`manager.py`）

複数の `BaseOutput` を受け取り、`save_all()` で全出力先に一括保存する。

- 1つの出力先が失敗しても他の出力先への保存は続行する
- `is_available()` が `False` の出力先はスキップする
- 保存に成功した保存先文字列のリストを返す

---

## main.py からの呼び出し

```python
# 起動時に1回だけ初期化
output_manager = OutputManager(outputs=[
    MarkdownOutput(output_dir=OUTPUT_DIR),
    WordPressOutput.from_env(),  # .env 未設定時は is_available()=False で自動スキップ
])

# 記事生成後の保存（v1.6.0 以降）
excerpt            = _extract_excerpt(article_body)            # ルールベース・API追加なし
featured_image_url = resolve_featured_image(item)              # Markdown記録用URL（v1.4 追加）
featured_media_id  = resolve_media_id(item, default_media_id)  # WordPress media_id（v1.6 追加）
article = ArticleData(
    item=item,
    importance=importance,
    seo_title=seo_title,
    article_body=article_body,
    x_post=x_post,
    featured_image_url=featured_image_url,
    excerpt=excerpt,
    meta_description=excerpt,    # v1.4.0 では excerpt と同値
    slug=slug,                   # v1.5 追加
    featured_media_id=featured_media_id,  # v1.6 追加
)
destinations = output_manager.save_all(article)
```

---

## 将来の拡張手順

新しい出力先（Notion・Discord など）を追加する場合：

1. `src/outputs/` に新しいクラスファイルを作成し `BaseOutput` を継承する
2. `save()` と `is_available()` を実装する
3. `src/outputs/__init__.py` でエクスポートする
4. `main.py` の `OutputManager([...])` に追加する

**既存ファイルへの変更は最小限（main.py の1行追加のみ）。**
