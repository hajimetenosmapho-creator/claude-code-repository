# v1.9.0 SNS Foundation 設計書

作成日：2026-06-30  
対象バージョン：v1.9.0  
対象 Epic：Release 1.1 — Epic 3 SNS Foundation  
ステータス：Draft（設計フェーズ）

---

## 1. Goal

X（旧 Twitter）投稿文と WordPress 記事 URL を紐付けて管理し、
「どの記事のX投稿文が、どのステータスで、どのURLと紐付いているか」を
ローカルログで追跡できる基盤を整える。

現在（v1.8.0）では、X投稿文はMarkdownファイルに保存されているが、
ログには記録されておらず、ブログURLのプレースホルダー `[ブログURL]` が
差し替えられないまま残っている。

v1.9.0 では X API 自動投稿は行わない。
まず「SNS投稿文と投稿URLを管理できる基盤」を作り、
将来の X API 連携・他SNS対応のための拡張ポイントを整備する。

---

## 2. Background

### 現状の問題点

```
main.py 実行
  → generate_x_post() が X投稿文を生成
  → blog_url は "[ブログURL]" プレースホルダーのまま
  → ArticleData.x_post に "[ブログURL]" が残った状態で保存
  → ArticleLogEntry に x_post フィールドなし
  → 実行後、X投稿文はどこに何があるか分からない
  → 「昨日の記事のX投稿文をコピーして投稿したい」が困難
```

具体的に管理できていない情報：

| 情報 | v1.8.0 時点 |
|------|------------|
| X投稿文の最終形（ブログURL入り） | Markdownのみ、ログ未記録 |
| WordPress 公開予定URL | 管理なし |
| X投稿ステータス（未投稿/投稿済み） | 管理なし |
| X投稿後のポストURL | 管理なし |
| 記事とX投稿文の紐付け | 曖昧（Markdownファイルのみ） |

### v1.9.0 が解決すること

| Before（v1.8.0） | After（v1.9.0） |
|-----------------|----------------|
| `[ブログURL]` が残ったままのX投稿文 | WordPress slug から公開予定URLを生成し、プレースホルダーを置換 |
| X投稿文がログに記録されない | `ArticleLogEntry` に `x_post_text` フィールドを追加 |
| SNS投稿ステータスの管理手段なし | `x_post_status` で pending / posted / skipped を管理 |
| 記事とSNS情報の紐付けなし | `wp_public_url` / `x_post_url` を同一ログエントリーに記録 |

---

## 3. Scope

v1.9.0 で実装する範囲。

### 実装対象

| 対象 | 内容 |
|------|------|
| `src/sns_config.py` | 新規作成。`SnsConfig` dataclass（ブログURL生成・SNS設定管理） |
| `src/logger/log_entry.py` | `ArticleLogEntry` に4フィールドを追加（後方互換あり） |
| `src/logger/log_manager.py` | `log_article()` に SNS パラメータを追加 |
| `main.py` | 処理順変更（slug→x_post）、`SnsConfig` 連携、SNS情報のログ記録 |
| `.env.example` | `BLOG_BASE_URL` / `SNS_ENABLED` の設定例を追加 |

### v1.9.0 が管理する SNS 情報

| フィールド | 内容 |
|-----------|------|
| `wp_public_url` | WordPress 公開予定URL（`BLOG_BASE_URL` + `slug` から推定） |
| `x_post_text` | X投稿文（ブログURL置換済みの最終形） |
| `x_post_status` | X投稿ステータス（`pending` / `posted` / `failed` / `skipped`） |
| `x_post_url` | X投稿後のポストURL（v1.9.0 は常に空。将来のX API対応時に記録） |

---

## 4. Non Goal

v1.9.0 では実装しないこと。

| 項目 | 理由 |
|------|------|
| X API 自動投稿 | リスク管理。まず基盤を整えてから v2.x 以降で設計 |
| SNS への自動ログイン | 同上 |
| Instagram / Threads / YouTube 連携 | スコープ外。将来 `SnsConfig` を拡張して対応 |
| Google Analytics 連携 | Release 1.1 Epic 4（v1.10.0）の対象 |
| Search Console 連携 | 同上 |
| SNS 投稿の効果測定 | スコープ外 |
| 管理画面 | スコープ外 |
| WordPress 記事の公開確認（API で公開状態を確認） | スコープ外。draft のままなので公開URLは推定値 |
| 複数SNSプラットフォーム対応 | 将来拡張。v1.9.0 は X のみを設計の軸に置く |

---

## 5. User Workflow

### Before（v1.8.0）

```
1. main.py を実行する
2. 記事が WordPress に下書き投稿される
3. X投稿文は Markdown ファイルの末尾に "[ブログURL]" 入りで保存される
4. 手動でXに投稿したい場合：
   - output/ フォルダを開く
   - 対象 Markdown ファイルを探す
   - X投稿文をコピーする
   - "[ブログURL]" を手動でブログのURLに書き換える
   - X に投稿する
```

### After（v1.9.0）

```
1. .env に BLOG_BASE_URL を設定しておく（初回のみ）
   BLOG_BASE_URL=https://nozo3-kao6.tokyo

2. main.py を実行する
3. 記事が WordPress に下書き投稿される

4. logs/articles/20260630_articles.jsonl に以下が記録される：
   - wp_public_url  : "https://nozo3-kao6.tokyo/ps6-announced-20260630/"
   - x_post_text   : "PS6はSwitch型になる？\n\nソニーが発表...\n\n詳しくはこちら👇\nhttps://nozo3-kao6.tokyo/ps6-announced-20260630/"
   - x_post_status : "pending"
   - x_post_url    : ""（まだX投稿前）

5. Xに手動で投稿したい場合：
   - logs/articles/ を開く
   - 対象エントリーの "x_post_text" フィールドをそのままコピーする
   - ブログURL置換済みのため、そのままXに貼り付けて投稿できる

6. メリット：
   - "[ブログURL]" の手動書き換えが不要
   - どの記事のX投稿文がどのステータスか一目でわかる
   - 将来、X API 連携した場合も同じログ構造で管理できる
```

---

## 6. System Workflow

```
main.py
  │
  ├─ 起動時
  │    ├─ PublishingConfig.from_env()        （既存・変更なし）
  │    ├─ LogManager.from_env()              （既存・変更なし）
  │    └─ SnsConfig.from_env()              ← v1.9.0 追加
  │         └─ BLOG_BASE_URL / SNS_ENABLED を読み込む
  │
  └─ 記事ループ（各記事について）
       │
       ├─ API呼び出し順序を変更（v1.9.0 変更点）
       │    ├─ generate_article()            API 呼び出し 1回目（変更なし）
       │    ├─ generate_seo_title()          API 呼び出し 2回目（変更なし）
       │    ├─ slug = generate_slug()        ← 先に slug を確定（v1.9.0 から順序変更）
       │    ├─ wp_public_url = sns_config.resolve_public_url(slug)  ← v1.9.0 追加
       │    └─ generate_x_post(blog_url=wp_public_url)  API 呼び出し 3回目
       │                                     ← blog_url を渡す（v1.9.0 変更）
       │         └─ x_post にブログURL入り投稿文が入る
       │
       ├─ ArticleData を構築                 （変更なし。x_post はすでに最終形）
       │
       ├─ output_manager.save_all(article)   （既存・変更なし）
       │
       └─ log_manager.log_article(           ← SNS パラメータを追加（v1.9.0 変更）
              article=article,
              edit_url=edit_url,
              result=wp_result,
              wp_public_url=wp_public_url,   ← v1.9.0 追加
              x_post_status="pending",        ← v1.9.0 追加（固定値）
          )
```

### API呼び出し順序の変更について

v1.8.0 まで：
```
article → seo_title → x_post → (slug, excerpt, ...の計算)
```

v1.9.0 から：
```
article → seo_title → (slug計算 ← ここを前に移動) → x_post(blog_url付き) → (excerpt, ...)
```

- `slug` 計算は Claude API を呼ばない（ローカル処理のみ）
- 移動しても API 呼び出し回数は変わらない（3回のまま）
- `x_post` 生成時に `blog_url` を渡せるようになる

---

## 7. SNS Data Model

### 7-1. `ArticleLogEntry` への追加フィールド（後方互換あり）

v1.8.0 の `ArticleLogEntry` に4フィールドを追加する。
すべてデフォルト値を持つため、呼び出し元の変更は `log_article()` のみで済む。

```python
@dataclass
class ArticleLogEntry:
    # ─── 既存フィールド（v1.8.0、変更なし）───
    logged_at: str
    importance: str
    seo_title: str
    slug: str
    post_id: int
    edit_url: str
    publish_status: str
    category_ids: list
    tag_ids: list
    featured_media_id: int
    source_url: str
    source_name: str
    result: str
    error_message: str

    # ─── SNS フィールド（v1.9.0 追加）───
    wp_public_url: str = ""         # WordPress 公開予定URL（BLOG_BASE_URL + slug から推定）
    x_post_text: str = ""           # X投稿文（ブログURL置換済み・コピペで使える最終形）
    x_post_status: str = "pending"  # X投稿ステータス: "pending" / "posted" / "failed" / "skipped"
    x_post_url: str = ""            # X投稿後のポストURL（v1.9.0 は空・将来のX API対応時に記録）
```

### 7-2. SnsPostStatus Enum（ChatGPT レビュー反映）

`x_post_status` は文字列ではなく `SnsPostStatus` Enum で管理する（`src/sns_config.py` で定義）。

`PublishStatus`（v1.7.0）と同じく `str` を継承する `str, Enum` パターンを採用する。
これにより `json.dumps()` で自動的に文字列としてシリアライズされ、
JSONL 保存時に `.value` を明示的に呼ぶ必要がない。

```python
class SnsPostStatus(str, Enum):
    PENDING = "pending"   # X未投稿（デフォルト）
    POSTED  = "posted"    # X投稿済み（将来: X API 対応時）
    FAILED  = "failed"    # X投稿失敗（将来: X API 対応時）
    SKIPPED = "skipped"   # SNS_ENABLED=false によりスキップ
```

| 値 | 意味 | v1.9.0 |
|----|------|--------|
| `PENDING = "pending"` | X未投稿（デフォルト） | ✅ 使用 |
| `POSTED = "posted"` | X投稿済み | 将来（X API 対応時） |
| `FAILED = "failed"` | X投稿失敗 | 将来（X API 対応時） |
| `SKIPPED = "skipped"` | `SNS_ENABLED=false` によりスキップ | ✅ 使用 |

### 7-3. JSON Lines 出力例（v1.9.0 以降）

```json
{
  "logged_at": "2026-06-30T12:34:56+09:00",
  "importance": "S",
  "seo_title": "【速報】PS6はSwitch型？ソニーが次世代機の特徴を発表",
  "slug": "ps6-switch-type-20260630",
  "post_id": 10340,
  "edit_url": "https://nozo3-kao6.tokyo/wp-admin/post.php?post=10340&action=edit",
  "publish_status": "draft",
  "category_ids": [14],
  "tag_ids": [70, 71],
  "featured_media_id": 0,
  "source_url": "https://www.ign.com/articles/...",
  "source_name": "IGN",
  "result": "success",
  "error_message": "",
  "wp_public_url": "https://nozo3-kao6.tokyo/ps6-switch-type-20260630/",
  "x_post_text": "PS6はSwitch型になる？\n\nソニーが次世代機について発言。\n✅ 「リビング以外でも自然に楽しめる」\n✅ PS6は携帯モードも視野\n✅ 価格は据え置き型相当\n\n詳しくはこちら👇\nhttps://nozo3-kao6.tokyo/ps6-switch-type-20260630/",
  "x_post_status": "pending",
  "x_post_url": ""
}
```

---

## 8. Directory Structure

```
projects/03_game_content_ai/
│
├── main.py                                ← MODIFIED（SnsConfig・処理順変更・SNSログ）
├── .env.example                           ← MODIFIED（BLOG_BASE_URL / SNS_ENABLED 追加）
│
├── docs/
│   └── design/
│       ├── publishing_automation.md       （変更なし）
│       ├── logging_foundation.md          （変更なし）
│       └── sns_foundation.md              ← この設計書（NEW）
│
└── src/
    ├── sns_config.py                      ← NEW（SnsConfig dataclass）
    │
    ├── logger/
    │   ├── __init__.py                    （変更なし）
    │   ├── log_entry.py                   ← MODIFIED（ArticleLogEntry に SNS フィールド追加）
    │   └── log_manager.py                 ← MODIFIED（log_article() に SNS パラメータ追加）
    │
    ├── publishing_config.py               （変更なし）
    ├── image_resolver.py                  （変更なし）
    ├── slug_generator.py                  （変更なし）
    ├── image_extractor.py                 （変更なし）
    ├── collector.py                       （変更なし）
    ├── keyword_filter.py                  （変更なし）
    ├── duplicate_filter.py                （変更なし）
    ├── importance_judge.py                （変更なし）
    ├── article_generator.py               （変更なし）
    ├── seo_title_generator.py             （変更なし）
    ├── x_post_generator.py                （変更なし・blog_url 引数は既存）
    └── outputs/                           （変更なし）
```

---

## 9. Module Design

### 9-1. 新規モジュール：`src/sns_config.py`

```python
"""
SNS連携の設定を管理するモジュール。

v1.9.0: WordPress公開予定URLの生成・SNS機能の有効/無効を管理。
将来: X API認証情報・他SNSプラットフォーム設定の追加。
"""
import os
from dataclasses import dataclass


@dataclass
class SnsConfig:
    """
    SNS連携の設定。.env から読み込む。

    設計方針（Configuration First）:
        - 未設定の場合は wp_public_url に "[ブログURL]" を使用（v1.8.0 互換）
        - SNS_ENABLED=false でSNS機能を無効化できる

    将来の拡張フィールド（現在は未実装・コメントとして予約）:
        x_api_key: str          - X API キー（将来の自動投稿用）
        x_api_secret: str       - X API シークレット（将来の自動投稿用）
        x_access_token: str     - X アクセストークン（将来の自動投稿用）
        x_access_secret: str    - X アクセスシークレット（将来の自動投稿用）
        instagram_enabled: bool - Instagram 連携（将来対応）
        threads_enabled: bool   - Threads 連携（将来対応）

    Attributes:
        blog_base_url: WordPress ブログのベースURL（公開予定URL生成に使用）
        sns_enabled:   SNS機能全体の有効/無効
    """
    blog_base_url: str = ""
    sns_enabled: bool = True

    @classmethod
    def from_env(cls) -> "SnsConfig":
        """
        環境変数から設定を読み込む。

        読み込む環境変数:
            BLOG_BASE_URL: ブログのベースURL（未設定時は WP_SITE_URL にフォールバック）
            SNS_ENABLED:   SNS機能の有効/無効（未設定時: "true"）

        Returns:
            SnsConfig: 検証済みの設定インスタンス
        """
        blog_base_url = (
            os.getenv("BLOG_BASE_URL")
            or os.getenv("WP_SITE_URL", "")
        ).rstrip("/")

        sns_enabled = os.getenv("SNS_ENABLED", "true").lower().strip() != "false"

        return cls(
            blog_base_url=blog_base_url,
            sns_enabled=sns_enabled,
        )

    def resolve_public_url(self, slug: str) -> str:
        """
        WordPress slug から公開予定URLを生成する。

        URL構造: {blog_base_url}/{slug}/
        例: "https://nozo3-kao6.tokyo/ps6-announced-20260630/"

        前提: WordPress のパーマリンク設定が「投稿名」形式であること
        （例: /%postname%/）。別のパーマリンク構造を使う場合は
        BLOG_BASE_URL の設定で対応する。

        Args:
            slug: WordPress slug（例: "ps6-announced-20260630"）

        Returns:
            str: 公開予定URL。blog_base_url または slug が空の場合は "[ブログURL]"。
        """
        if not self.blog_base_url or not slug:
            return "[ブログURL]"
        return f"{self.blog_base_url}/{slug}/"
```

---

### 9-2. 変更モジュール：`src/logger/log_entry.py`

```python
@dataclass
class ArticleLogEntry:
    """1記事の投稿結果ログ。"""

    # ─── 既存フィールド（v1.8.0、変更なし）───
    logged_at: str
    importance: str
    seo_title: str
    slug: str
    post_id: int
    edit_url: str
    publish_status: str
    category_ids: list
    tag_ids: list
    featured_media_id: int
    source_url: str
    source_name: str
    result: str
    error_message: str

    # ─── SNS フィールド（v1.9.0 追加）───
    # デフォルト値を持つため、v1.8.0 の呼び出し元は変更不要
    wp_public_url: str = ""
    x_post_text: str = ""
    x_post_status: str = "pending"
    x_post_url: str = ""

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)
```

---

### 9-3. 変更モジュール：`src/logger/log_manager.py`

`log_article()` の引数に SNS パラメータを追加する。

```python
def log_article(
    self,
    article,
    edit_url: str = "",
    result: str = "success",
    error_message: str = "",
    # v1.9.0 追加（後方互換あり）
    wp_public_url: str = "",
    x_post_status: str = "pending",
    x_post_url: str = "",
) -> None:
    """
    1記事の投稿結果を ArticleLog に記録する。

    Args:
        article:       投稿した ArticleData
        edit_url:      WordPress 編集URL（"" = WP未設定またはエラー）
        result:        "success" / "failed" / "skipped"
        error_message: エラーメッセージ（"" = エラーなし）
        wp_public_url: WordPress 公開予定URL（SnsConfig.resolve_public_url() の結果）
        x_post_status: X投稿ステータス（"pending" / "posted" / "failed" / "skipped"）
        x_post_url:    X投稿後のポストURL（v1.9.0 は常に ""）
    """
    from outputs.taxonomy_config import resolve_taxonomy
    category_ids, tag_ids = resolve_taxonomy(article.importance)
    post_id = self._extract_post_id(edit_url)
    date_str = datetime.now().strftime("%Y%m%d")

    entry = ArticleLogEntry(
        # 既存フィールド（変更なし）
        logged_at=self._now_iso(),
        importance=article.importance,
        seo_title=article.seo_title,
        slug=article.slug,
        post_id=post_id,
        edit_url=edit_url,
        publish_status=article.publish_status.value,
        category_ids=category_ids,
        tag_ids=tag_ids,
        featured_media_id=article.featured_media_id,
        source_url=article.item.url,
        source_name=article.item.source,
        result=result,
        error_message=error_message,
        # SNS フィールド（v1.9.0 追加）
        wp_public_url=wp_public_url,
        x_post_text=article.x_post,      # ArticleData.x_post は既にURL置換済み
        x_post_status=x_post_status,
        x_post_url=x_post_url,
    )
    path = self._get_log_path("articles", date_str)
    self._append(path, entry.to_json_line())
```

---

### 9-4. 変更モジュール：`main.py`（変更概要）

```python
# ① インポートを追加
from sns_config import SnsConfig

# ② 起動時に初期化（log_manager の直後）
sns_config = SnsConfig.from_env()

# ③ 記事ループ内：処理順を変更（slug を x_post より先に計算）
# Before（v1.8.0）
x_post = generate_x_post(client, item, importance, article_body)
# ...（以降で slug を計算）

# After（v1.9.0）
# slug を先に計算してから x_post を生成（API呼び出し回数は変わらない）
date_str     = datetime.now().strftime("%Y%m%d")
slug         = generate_slug(seo_title, date_str)
wp_public_url = sns_config.resolve_public_url(slug)
x_post       = generate_x_post(client, item, importance, article_body, blog_url=wp_public_url)

# ④ log_manager.log_article() に SNS パラメータを追加
log_manager.log_article(
    article=article,
    edit_url=edit_url,
    result=wp_result,
    wp_public_url=wp_public_url,    # v1.9.0 追加
    x_post_status="pending",         # v1.9.0 追加（固定値）
)
```

---

## 10. Configuration Design

### `BLOG_BASE_URL` と `WP_SITE_URL` の使い分け（ChatGPT レビュー反映）

| 環境変数 | 役割 | 優先度 |
|---------|------|--------|
| `BLOG_BASE_URL` | 公開記事URLの生成に使用するベースURL | **優先**（推奨） |
| `WP_SITE_URL` | WordPress REST API の接続先URL | フォールバック |

> **設計意図**
>
> `WP_SITE_URL` は WordPress REST API 接続用（内部URL）として設定されることがある。
> 例えば、WordPress がサブディレクトリ（`https://example.com/blog/`）に設置されている場合、
> `WP_SITE_URL=https://example.com/blog` となるが、
> 公開URLは `https://example.com/blog/{slug}/` になる。
>
> このため、公開URLの生成には専用の `BLOG_BASE_URL` を優先する。
> `BLOG_BASE_URL` が未設定の場合は `WP_SITE_URL` にフォールバックするが、
> **本番運用では `BLOG_BASE_URL` の明示設定を推奨する。**

### `.env.example` への追記内容

```bash
# ─────────────────────────────────────────
# SNS Foundation（v1.9.0 追加）
# ─────────────────────────────────────────
# ブログ公開URLのベース（X投稿文のブログリンク生成に使用）
# 本番運用では BLOG_BASE_URL の設定を推奨します。
# 未設定時: WP_SITE_URL にフォールバック（WP_SITE_URL も未設定なら "[ブログURL]" のまま）
# 設定例: BLOG_BASE_URL=https://nozo3-kao6.tokyo
# BLOG_BASE_URL=

# SNS機能の有効/無効
# true  : X投稿文にブログURLを埋め込み、ログにSNS情報を記録する（デフォルト）
# false : SNS機能を無効化（v1.8.0 以前と同じ動作。wp_public_url は空文字、x_post_status は skipped）
SNS_ENABLED=true
```

### Configuration First の設計意図

| 設定パターン | 動作 | ユースケース |
|-------------|------|-------------|
| `BLOG_BASE_URL=https://example.com` | `https://example.com/{slug}/` を生成 | **本番運用（推奨）** |
| `BLOG_BASE_URL` 未設定・`WP_SITE_URL` あり | `WP_SITE_URL` をフォールバックとして使用 | 暫定運用 |
| `BLOG_BASE_URL` 未設定・`WP_SITE_URL` も未設定 | `"[ブログURL]"` のまま（v1.8.0 互換） | 設定前・テスト |
| `SNS_ENABLED=false` | `x_post_status=skipped`、`wp_public_url=""` | テスト時・SNS不使用 |

### `resolve_public_url()` の出力例

| `blog_base_url` | `slug` | 出力 |
|-----------------|--------|------|
| `"https://nozo3-kao6.tokyo"` | `"ps6-announced-20260630"` | `"https://nozo3-kao6.tokyo/ps6-announced-20260630/"` |
| `""` | `"ps6-announced-20260630"` | `"[ブログURL]"` |
| `"https://example.com"` | `""` | `"[ブログURL]"` |

---

## 11. Logging Foundation との関係

### 責務の分離

| モジュール | 責務 |
|-----------|------|
| `SnsConfig`（`src/sns_config.py`） | SNS設定の管理・公開URL生成 |
| `LogManager`（`src/logger/log_manager.py`） | ログのファイル書き込み |
| `ArticleLogEntry`（`src/logger/log_entry.py`） | ログエントリーのデータ定義 |

各モジュールは互いの実装詳細を知らない。`SnsConfig` は `LogManager` に依存せず、
`LogManager` は `SnsConfig` に依存しない。

### `ArticleLogEntry` の拡張方針

- 新フィールドはすべて**デフォルト値あり**（後方互換性）
- v1.8.0 の `log_manager.log_article()` 呼び出しは変更不要
- v1.9.0 では `wp_public_url` と `x_post_status` を新たに渡す

### Single Source of Truth

| 情報 | Single Source |
|------|--------------|
| `wp_public_url` | `SnsConfig.resolve_public_url(slug)` の戻り値。`main.py` で1回だけ計算 |
| `x_post_text` | `ArticleData.x_post`（ブログURL置換済み）。再計算しない |
| `x_post_status` | `main.py` で決定。v1.9.0 は `"pending"` 固定 |

---

## 12. WordPress との関係

### WordPress 公開 URL の推定

v1.9.0 時点では、記事は `draft` または `pending` 状態のため、
実際には公開されていない。`wp_public_url` は推定値（予定URL）である。

| WordPress 状態 | `wp_public_url` の意味 |
|--------------|----------------------|
| `draft`（下書き） | 推定値。公開後にアクセス可能になる予定 |
| `pending`（レビュー待ち） | 推定値。承認・公開後にアクセス可能になる予定 |
| `publish`（公開済み、将来対応） | 確定URL。実際にアクセス可能 |

### WordPress パーマリンク設定の前提

`resolve_public_url()` は WordPress のパーマリンク設定が
**「投稿名」形式**（`/%postname%/`）であることを前提とする。

実際の WordPress で確認する方法：
```
WordPress 管理画面 → 設定 → パーマリンク → 「投稿名」を選択
```

別の形式（日付入り等）を使う場合は、`BLOG_BASE_URL` で直接カスタマイズできる。

### `WordPressOutput` との関係

`WordPressOutput.save()` は変更しない。返り値（`edit_url`）の構造も変わらない。
`wp_public_url` の生成は `SnsConfig` が独立して担い、`WordPressOutput` に依存しない。

---

## 13. Error Handling

### 設定値エラー

| ケース | 挙動 |
|--------|------|
| `BLOG_BASE_URL` 未設定・`WP_SITE_URL` も未設定 | `resolve_public_url()` が `"[ブログURL]"` を返す（サイレント） |
| `SNS_ENABLED` に無効な値 | `"true"` として動作（フォールバック） |
| `slug` が空文字 | `resolve_public_url()` が `"[ブログURL]"` を返す（サイレント） |

### x_post 生成失敗時

`generate_x_post()` が失敗した場合（既存の try/except で処理済み）、
`x_post` はフォールバック文字列になる。この場合、`ArticleLogEntry.x_post_text`
にはフォールバック文字列が記録される（異常ではない）。

### ログ書き込み失敗

v1.8.0 の `LogManager._append()` がすでに `OSError` をキャッチして
WARNING 出力で継続している。v1.9.0 で追加される SNS フィールドも同様に扱われる。

---

## 14. Future Extensions

### Phase 2：X API 自動投稿（v2.x）

```python
# SnsConfig に追加予定のフィールド
x_api_key: str = ""
x_api_secret: str = ""
x_access_token: str = ""
x_access_secret: str = ""

# 追加予定のメソッド
def post_to_x(self, text: str) -> str:
    """X に投稿し、投稿URLを返す。"""
    ...
```

`main.py` の変更は最小限：
```python
if sns_config.x_api_enabled:
    x_post_url = sns_config.post_to_x(article.x_post)
    x_post_status = "posted"
```

### Phase 3：複数 SNS 対応（v2.x 以降）

```python
# SnsConfig に追加予定のフィールド
instagram_enabled: bool = False
threads_enabled: bool = False
```

`ArticleLogEntry` への追加フィールド（将来検討）：
- `instagram_post_url: str = ""`
- `threads_post_url: str = ""`

### Phase 4：X 投稿タイミングの制御

記事が WordPress で公開された後に X 投稿する運用フロー：
1. WordPress で「公開」ボタンを押す
2. スクリプトが `logs/articles/` を確認
3. `x_post_status == "pending"` の記事を X に投稿
4. `x_post_status` を `"posted"` に更新・`x_post_url` を記録

これにより「公開前にX投稿してしまう」事故を防ぐことができる。

---

## 15. Definition of Done

v1.9.0 実装完了の判定基準。

### コード

- [ ] `src/sns_config.py` 新規作成
  - [ ] `SnsConfig` dataclass（`blog_base_url`・`sns_enabled` フィールド）
  - [ ] `from_env()` classmethod
    - [ ] `BLOG_BASE_URL` 未設定時は `WP_SITE_URL` にフォールバック
    - [ ] `SNS_ENABLED=false` で `sns_enabled=False`
  - [ ] `resolve_public_url(slug: str) -> str` メソッド
    - [ ] `blog_base_url` か `slug` が空なら `"[ブログURL]"` を返す
    - [ ] `"{blog_base_url}/{slug}/"` 形式の URL を返す
- [ ] `src/logger/log_entry.py` 修正
  - [ ] `ArticleLogEntry` に `wp_public_url`, `x_post_text`, `x_post_status`, `x_post_url` を追加
  - [ ] すべてデフォルト値ありで後方互換を維持
- [ ] `src/logger/log_manager.py` 修正
  - [ ] `log_article()` に `wp_public_url`, `x_post_status`, `x_post_url` パラメータを追加
  - [ ] すべてデフォルト値ありで既存呼び出しは変更不要
  - [ ] `ArticleLogEntry` 構築時に SNS フィールドを設定
- [ ] `main.py` 修正
  - [ ] `from sns_config import SnsConfig` 追加
  - [ ] `sns_config = SnsConfig.from_env()` を起動時に1回呼び出す
  - [ ] 記事ループ内で `slug` を `x_post` より**先に**計算
  - [ ] `wp_public_url = sns_config.resolve_public_url(slug)` を計算
  - [ ] `generate_x_post(..., blog_url=wp_public_url)` を渡す
  - [ ] `log_manager.log_article(..., wp_public_url=wp_public_url, x_post_status="pending")` を更新
- [ ] `.env.example` 修正
  - [ ] `BLOG_BASE_URL` の設定例を追加
  - [ ] `SNS_ENABLED=true` を追加

### テスト・動作確認

- [ ] E2E テスト①：`BLOG_BASE_URL=https://nozo3-kao6.tokyo`（設定あり）
  - [ ] X投稿文の `[ブログURL]` が実際のURLに置換されている
  - [ ] `logs/articles/` の `wp_public_url` が `https://nozo3-kao6.tokyo/{slug}/` になっている
  - [ ] `logs/articles/` の `x_post_text` にブログURL入りの投稿文が記録されている
  - [ ] `x_post_status` が `"pending"` になっている
- [ ] E2E テスト②：`SNS_ENABLED=false`
  - [ ] `x_post_status` が `"skipped"` になっている
  - [ ] `wp_public_url` が `""` になっている
  - [ ] 記事生成・WordPress投稿の動作に変化がない
- [ ] E2E テスト③：`BLOG_BASE_URL` 未設定
  - [ ] `WP_SITE_URL` がフォールバックとして使われる
  - [ ] `WP_SITE_URL` も未設定なら `"[ブログURL]"` のまま（v1.8.0 互換）
- [ ] API 呼び出し回数が変化していないこと（1記事あたり 3回のまま）
- [ ] Release 1.0 互換維持（`SNS_ENABLED=false` 時に動作変化なし）

### ドキュメント

- [ ] `docs/CHANGELOG.md` に v1.9.0 エントリーを追加
- [ ] `docs/ROADMAP.md` の v1.9.0 を完了マークに更新
- [ ] `docs/architecture.md` に `sns_config.py` と SNS フィールドを追記

### リリース

- [ ] git commit 完了
- [ ] git push 完了
- [ ] working tree clean
- [ ] API 呼び出し回数変化なし（1記事あたり 3回）
- [ ] Release 1.0 互換維持
