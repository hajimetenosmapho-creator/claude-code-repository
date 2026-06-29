# v1.8.0 Logging Foundation 設計書

作成日：2026-06-30  
対象バージョン：v1.8.0  
対象 Epic：Release 1.1 — Epic 2 Logging Foundation  
ステータス：Draft（設計フェーズ）

---

## 1. Goal

実行履歴・投稿履歴・エラーログをローカルファイルへ構造化して保存し、
「いつ・何を・どのステータスで・成功/失敗したか」を後から確認できるようにする。

現在（v1.7.0）はすべての記録が `print()` によるコンソール出力のみであり、
実行後に過去の投稿結果を参照する手段がない。
v1.8.0 では JSON Lines 形式のファイルへ構造化ログを出力し、
将来の CSV / DB 拡張・AI改善提案・Analytics 連携への基盤を整備する。

---

## 2. Background

### 現状の問題点

```
main.py 実行
  → コンソールに print() で情報を表示
  → 実行終了後は情報が消える
  → 「昨日の投稿結果を確認したい」が不可能
  → 「エラーが多い記事の傾向を知りたい」が不可能
```

具体的に消えてしまっている情報：

| 情報 | v1.7.0 時点 |
|------|------------|
| 実行日時 | コンソールのみ（残らない） |
| 投稿した記事の post_id | コンソールのみ（残らない） |
| slug / edit_url | コンソールのみ（残らない） |
| publish_status（draft/pending） | コンソールのみ（残らない） |
| category_ids / tag_ids | 記録なし |
| 実行時間 | コンソールのみ（残らない） |
| 成功 / 失敗の件数 | コンソールのみ（残らない） |
| エラーメッセージ | コンソールのみ（残らない） |

### v1.8.0 が解決すること

| Before（v1.7.0） | After（v1.8.0） |
|-----------------|----------------|
| 記録はコンソールのみ | JSON Lines ファイルに永続保存 |
| 実行後に過去の投稿を確認する手段なし | `logs/` を見れば過去の全記録を確認可能 |
| エラーは画面で流れてしまう | エラーログに構造化して記録 |
| 将来の Analytics 連携が困難 | 構造化データがすでに存在する |

---

## 3. Scope

v1.8.0 で実装する範囲。

### 実装対象

| 対象 | 内容 |
|------|------|
| `src/logger/__init__.py` | 新規作成。`LogManager`・`ArticleLogEntry`・`ExecutionLogEntry`・`ErrorLogEntry` を公開 |
| `src/logger/log_entry.py` | 新規作成。ログエントリーの dataclass 定義 |
| `src/logger/log_manager.py` | 新規作成。ファイルへの書き込み・ディレクトリ管理を担う `LogManager` クラス |
| `main.py` | `LogManager.from_env()` の初期化と各ログ出力の呼び出しを追加 |
| `.env.example` | `LOG_ENABLED` / `LOG_DIR` の設定例を追加 |

### 保存する情報

| 情報 | ログ種別 |
|------|---------|
| 実行日時・実行時間 | ExecutionLog |
| 収集件数・フィルター件数・重複除去件数 | ExecutionLog |
| 記事生成件数・API呼び出し回数 | ExecutionLog |
| 成功 / 失敗 / スキップ件数 | ExecutionLog |
| 記事タイトル（seo_title） | ArticleLog |
| slug / post_id / edit_url | ArticleLog |
| publish_status（draft/pending） | ArticleLog |
| importance（S/A/B） | ArticleLog |
| category_ids / tag_ids | ArticleLog |
| featured_media_id | ArticleLog |
| ソース名 / ソースURL | ArticleLog |
| 成功 / 失敗 の結果 | ArticleLog |
| エラー種別・エラーメッセージ | ErrorLog |

---

## 4. Non Goal

v1.8.0 では実装しないこと。

| 項目 | 理由 |
|------|------|
| Google Analytics 連携 | Release 1.1 Epic 4（v1.10.0）の対象 |
| Search Console 連携 | 同上 |
| SNS 自動投稿 | Release 1.1 Epic 3（v1.9.0）の対象 |
| データベース（SQLite 等）導入 | JSON Lines で十分。将来の v2.x で検討 |
| 管理画面・可視化UI | スコープ外 |
| 外部ログサービス連携（Datadog 等） | スコープ外 |
| ログを使った AI 改善提案 | v2.0 以降の対象 |
| CSV / DB へのエクスポート機能 | v1.9.0 以降の対象 |
| ログの自動ローテーション | v2.x で検討。v1.8.0 は日付別ファイルで十分 |

---

## 5. User Workflow

### Before（v1.7.0）

```
1. main.py を実行する
2. コンソールに記事の投稿結果が表示される
3. 実行終了後、情報はすべて消える
4. 「昨日、何の記事を投稿したか」を確認したくても手段がない
5. エラーが起きた場合も、画面を閉じると記録が残らない
```

### After（v1.8.0）

```
1. main.py を実行する
2. コンソールへの print() 出力は従来通り（変化なし）
3. 実行と同時に logs/ フォルダにログが自動保存される

   logs/
   ├── articles/20260630_articles.jsonl   ← 各記事の投稿結果
   ├── execution/20260630_execution.jsonl ← 実行全体のサマリー
   └── errors/20260630_errors.jsonl       ← エラーが発生した場合のみ

4. 後から logs/ を確認すれば：
   - いつ、どの記事を、どのステータスで投稿したか確認できる
   - post_id や edit_url を記録から辿れる
   - エラーの内容と対象記事を確認できる

5. LOG_ENABLED=false に設定すれば、ログ出力を完全に無効化できる
   （Release 1.0 と完全に同じ動作になる）
```

---

## 6. System Workflow

```
main.py
  │
  ├─ 起動時
  │    ├─ PublishingConfig.from_env()   （既存・変更なし）
  │    └─ LogManager.from_env()         ← v1.8.0 追加
  │         └─ LOG_ENABLED / LOG_DIR を読み込む
  │              └─ LOG_ENABLED=false なら NullLogManager を返す（何もしない）
  │
  └─ 記事ループ（各記事について）
       │
       ├─ generate_article() / generate_seo_title() / generate_x_post()
       │                                         （既存・変更なし）
       │
       ├─ ArticleData を構築                    （既存・変更なし）
       │
       ├─ output_manager.save_all(article) → destinations
       │                                         （既存・変更なし）
       │
       ├─ [成功した場合]
       │    └─ log_manager.log_article(          ← v1.8.0 追加
       │           article=article,
       │           edit_url=<WPのedit_url>,
       │           result="success"
       │       )
       │
       └─ [RuntimeError が発生した場合]
            ├─ log_manager.log_article(           ← v1.8.0 追加
            │      article=article,
            │      edit_url="",
            │      result="failed",
            │      error_message=str(e)
            │  )
            └─ log_manager.log_error(             ← v1.8.0 追加
                   error_type="WordPressError",
                   error_message=str(e),
                   article_title=article.seo_title
               )
  │
  └─ 全記事処理完了後
       └─ log_manager.log_execution(              ← v1.8.0 追加
              executed_at=...,
              total_collected=...,
              ...
          )
```

### NullLogManager パターン

`LOG_ENABLED=false` の場合は `NullLogManager` を返す。
`NullLogManager` はすべてのメソッドが何もしない（no-op）。
`main.py` は `LogManager` か `NullLogManager` かを意識しない。

```python
# main.py 側のコードは LOG_ENABLED の値を知らなくてよい
log_manager = LogManager.from_env()     # NullLogManager か LogManager が返る
log_manager.log_article(...)            # どちらが返っても呼び出し方は同じ
```

---

## 7. Log Types

### ArticleLog（記事ログ）

1記事の投稿結果を記録する。WordPressへの投稿ごとに1エントリー。
MarkdownOutput への保存は記録しない（ファイルパスは常に変わらない形式のため不要）。

保存ファイル：`logs/articles/YYYYMMDD_articles.jsonl`

### ExecutionLog（実行ログ）

main.py の1回の実行全体のサマリーを記録する。
実行終了時に1エントリーを書き込む。

保存ファイル：`logs/execution/YYYYMMDD_execution.jsonl`

### ErrorLog（エラーログ）

記事処理中に発生した例外・エラーを記録する。
エラーが発生しない実行ではファイルは作成されない。

保存ファイル：`logs/errors/YYYYMMDD_errors.jsonl`

---

## 8. Log Data Model

### 8-1. ArticleLogEntry dataclass

```python
@dataclass
class ArticleLogEntry:
    logged_at: str          # ISO 8601（例: "2026-06-30T12:34:56+09:00"）
    importance: str         # "S" / "A" / "B"
    seo_title: str          # AIが生成したSEOタイトル
    slug: str               # WordPress slug
    post_id: int            # WordPress 投稿ID（0 = 失敗またはWP未設定）
    edit_url: str           # WordPress 管理画面の編集URL（"" = 同上）
    publish_status: str     # "draft" / "pending"
    category_ids: list[int] # WordPress カテゴリID（例: [14]）
    tag_ids: list[int]      # WordPress タグID（例: [70, 71]）
    featured_media_id: int  # WordPress media_id（0 = アイキャッチなし）
    source_url: str         # ニュース元のURL
    source_name: str        # ニュースソース名（例: "PlayStation Blog"）
    result: str             # "success" / "failed" / "skipped"
    error_message: str      # エラーメッセージ（"" = エラーなし）
```

> **[ChatGPT レビュー反映 — v1.8.0 暫定実装] `post_id` の取得方法について**
>
> v1.8.0 では既存の `BaseOutput.save()` インターフェースを維持するため、
> `edit_url` の URL パラメータ（`?post=XXXX`）から正規表現で `post_id` を抽出する暫定実装を採用する。
>
> ```
> edit_url = "https://example.com/wp-admin/post.php?post=123&action=edit"
>                                                         ↑ ここから抽出
> ```
>
> 将来的には `BaseOutput.save()` の戻り値を `str` から `SaveResult` dataclass に変更し、
> WordPress API レスポンスの `response_data["id"]` から `post_id` を直接取得する構造へ改善する。
> この改善は `OutputManager` / `BaseOutput` インターフェースの変更を伴うため、v1.9.0 以降のスコープとする。

### JSON Lines 出力例（成功時）

```json
{"logged_at": "2026-06-30T12:34:56+09:00", "importance": "S", "seo_title": "PS6正式発表", "slug": "ps6-announced-20260630", "post_id": 123, "edit_url": "https://example.com/wp-admin/post.php?post=123&action=edit", "publish_status": "pending", "category_ids": [14], "tag_ids": [70, 71], "featured_media_id": 456, "source_url": "https://blog.playstation.com/...", "source_name": "PlayStation Blog", "result": "success", "error_message": ""}
```

### JSON Lines 出力例（失敗時）

```json
{"logged_at": "2026-06-30T12:35:10+09:00", "importance": "A", "seo_title": "Nintendo Switch 後継機情報", "slug": "switch-successor-20260630", "post_id": 0, "edit_url": "", "publish_status": "draft", "category_ids": [14], "tag_ids": [71], "featured_media_id": 0, "source_url": "https://...", "source_name": "Famitsu", "result": "failed", "error_message": "WordPress投稿失敗 (HTTP 401): ..."}
```

---

### 8-2. ExecutionLogEntry dataclass

```python
@dataclass
class ExecutionLogEntry:
    executed_at: str        # ISO 8601（実行開始時刻）
    finished_at: str        # ISO 8601（実行終了時刻）
    execution_time_sec: float  # 実行時間（秒）
    total_collected: int    # RSS収集件数
    total_filtered: int     # フィルター通過件数
    total_deduped: int      # 重複除去後件数
    total_generated: int    # 記事生成件数（S+Aの処理件数）
    total_wp_success: int   # WordPress投稿成功件数
    total_wp_failed: int    # WordPress投稿失敗件数
    total_wp_skipped: int   # WordPress未設定によるスキップ件数
    api_call_count: int     # Claude APIの呼び出し回数
    result: str             # "success" / "partial" / "failed"
```

### JSON Lines 出力例

```json
{"executed_at": "2026-06-30T12:34:00+09:00", "finished_at": "2026-06-30T12:40:30+09:00", "execution_time_sec": 390.5, "total_collected": 120, "total_filtered": 35, "total_deduped": 28, "total_generated": 7, "total_wp_success": 7, "total_wp_failed": 0, "total_wp_skipped": 0, "api_call_count": 21, "result": "success"}
```

---

### 8-3. ErrorLogEntry dataclass

```python
@dataclass
class ErrorLogEntry:
    logged_at: str          # ISO 8601
    error_type: str         # "WordPressError" / "APIError" / "UnexpectedError"
    error_message: str      # エラーメッセージ（全文）
    article_title: str      # 処理中の記事タイトル（"" = 記事に紐づかないエラー）
    source_url: str         # 処理中のニュース元URL（"" = 同上）
```

### JSON Lines 出力例

```json
{"logged_at": "2026-06-30T12:35:10+09:00", "error_type": "WordPressError", "error_message": "WordPress投稿失敗 (HTTP 401): Unauthorized", "article_title": "Nintendo Switch 後継機情報", "source_url": "https://famitsu.com/..."}
```

---

### 8-4. result フィールドの定義

| 値 | 意味 | 使用するログ |
|----|------|------------|
| `"success"` | 正常完了 | ArticleLog / ExecutionLog |
| `"failed"` | エラー発生・処理中断 | ArticleLog / ExecutionLog |
| `"partial"` | 一部成功・一部失敗 | ExecutionLog のみ |
| `"skipped"` | WP未設定による記録スキップ | ArticleLog のみ |

---

## 9. Directory Structure

```
projects/03_game_content_ai/
│
├── main.py                              ← MODIFIED（LogManager 追加）
├── .env.example                         ← MODIFIED（LOG_ENABLED / LOG_DIR 追加）
│
├── logs/                                ← NEW（.gitignore 対象）
│   ├── articles/
│   │   └── 20260630_articles.jsonl      ← 日付別・記事ログ（append書き込み）
│   ├── execution/
│   │   └── 20260630_execution.jsonl     ← 日付別・実行ログ（append書き込み）
│   └── errors/
│       └── 20260630_errors.jsonl        ← 日付別・エラーログ（エラー時のみ作成）
│
├── docs/
│   └── design/
│       ├── publishing_automation.md     （変更なし）
│       └── logging_foundation.md        ← この設計書（NEW）
│
└── src/
    ├── logger/                          ← NEW パッケージ
    │   ├── __init__.py                  ← LogManager / LogEntry 類を公開
    │   ├── log_entry.py                 ← ArticleLogEntry / ExecutionLogEntry / ErrorLogEntry
    │   └── log_manager.py               ← LogManager / NullLogManager
    │
    ├── publishing_config.py             （変更なし）
    ├── image_resolver.py                （変更なし）
    ├── slug_generator.py                （変更なし）
    ├── image_extractor.py               （変更なし）
    ├── collector.py                     （変更なし）
    ├── keyword_filter.py                （変更なし）
    ├── duplicate_filter.py              （変更なし）
    ├── importance_judge.py              （変更なし）
    ├── article_generator.py             （変更なし）
    ├── seo_title_generator.py           （変更なし）
    ├── x_post_generator.py             （変更なし）
    └── outputs/                         （変更なし）
        ├── base.py
        ├── wordpress_output.py
        ├── markdown_output.py
        ├── manager.py
        ├── taxonomy_config.py
        └── __init__.py
```

### logs/ の .gitignore 対象について

`logs/` はローカルの実行履歴であり、GitHub へのアップロード対象外。
`.gitignore` に以下を追記する。

```
# 実行ログ（ローカルのみ）
projects/03_game_content_ai/logs/
```

---

## 10. Module Design

### 10-1. `src/logger/log_entry.py`

3種類のエントリー dataclass を定義する。
シリアライズ（JSON変換）のヘルパーを含む。

```python
import json
from dataclasses import dataclass, asdict

@dataclass
class ArticleLogEntry:
    """1記事の投稿結果ログ。"""
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

    def to_json_line(self) -> str:
        """JSON Lines 形式の1行文字列に変換する。"""
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class ExecutionLogEntry:
    """1回の実行全体のサマリーログ。"""
    executed_at: str
    finished_at: str
    execution_time_sec: float
    total_collected: int
    total_filtered: int
    total_deduped: int
    total_generated: int
    total_wp_success: int
    total_wp_failed: int
    total_wp_skipped: int
    api_call_count: int
    result: str

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class ErrorLogEntry:
    """エラー発生時の記録。"""
    logged_at: str
    error_type: str
    error_message: str
    article_title: str
    source_url: str

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)
```

---

### 10-2. `src/logger/log_manager.py`

`LogManager` と `NullLogManager` を実装する。

```python
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .log_entry import ArticleLogEntry, ExecutionLogEntry, ErrorLogEntry
from outputs.base import ArticleData
from outputs.taxonomy_config import resolve_taxonomy


class LogManager:
    """
    ログをローカルファイルへ書き込む。
    Single Responsibility: ファイルへの書き込みのみを担う。
    """

    def __init__(self, log_dir: Path):
        self.log_dir = log_dir

    @classmethod
    def from_env(cls) -> "LogManager | NullLogManager":
        """
        環境変数から設定を読み込む。
        LOG_ENABLED=false の場合は NullLogManager を返す。
        """
        enabled = os.getenv("LOG_ENABLED", "true").lower().strip()
        if enabled == "false":
            return NullLogManager()
        log_dir = Path(os.getenv("LOG_DIR", "logs"))
        return cls(log_dir=log_dir)

    def _get_log_path(self, subdir: str, date_str: str) -> Path:
        """ログファイルのパスを生成し、親ディレクトリを作成する。"""
        path = self.log_dir / subdir / f"{date_str}_{subdir}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _append(self, path: Path, line: str) -> None:
        """JSON Lines 形式で1行追記する。"""
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    def _now_iso(self) -> str:
        """現在時刻を ISO 8601 形式で返す。"""
        return datetime.now(timezone.utc).astimezone().isoformat()

    def _extract_post_id(self, edit_url: str) -> int:
        """edit_url から post_id を抽出する。取得できない場合は 0 を返す。"""
        match = re.search(r'post=(\d+)', edit_url)
        return int(match.group(1)) if match else 0

    def log_article(
        self,
        article: ArticleData,
        edit_url: str = "",
        result: str = "success",
        error_message: str = "",
    ) -> None:
        """
        1記事の投稿結果を ArticleLog に記録する。

        Args:
            article:       投稿した記事のデータ
            edit_url:      WordPress 編集URL（"" = WP未設定またはエラー）
            result:        "success" / "failed" / "skipped"
            error_message: エラーメッセージ（"" = エラーなし）
        """
        category_ids, tag_ids = resolve_taxonomy(article.importance)
        post_id = self._extract_post_id(edit_url)
        date_str = datetime.now().strftime("%Y%m%d")

        entry = ArticleLogEntry(
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
        )
        path = self._get_log_path("articles", date_str)
        self._append(path, entry.to_json_line())

    def log_execution(self, entry: ExecutionLogEntry) -> None:
        """実行サマリーを ExecutionLog に記録する。"""
        date_str = datetime.now().strftime("%Y%m%d")
        path = self._get_log_path("execution", date_str)
        self._append(path, entry.to_json_line())

    def log_error(
        self,
        error_type: str,
        error_message: str,
        article_title: str = "",
        source_url: str = "",
    ) -> None:
        """エラーを ErrorLog に記録する。"""
        date_str = datetime.now().strftime("%Y%m%d")
        entry = ErrorLogEntry(
            logged_at=self._now_iso(),
            error_type=error_type,
            error_message=error_message,
            article_title=article_title,
            source_url=source_url,
        )
        path = self._get_log_path("errors", date_str)
        self._append(path, entry.to_json_line())


class NullLogManager:
    """
    LOG_ENABLED=false のときに返されるダミー実装。
    すべてのメソッドが何もしない（no-op）。
    main.py は LogManager か NullLogManager かを意識しなくてよい。
    """

    def log_article(self, article, edit_url="", result="success", error_message="") -> None:
        pass

    def log_execution(self, entry) -> None:
        pass

    def log_error(self, error_type="", error_message="", article_title="", source_url="") -> None:
        pass
```

---

### 10-3. `src/logger/__init__.py`

```python
from .log_entry import ArticleLogEntry, ExecutionLogEntry, ErrorLogEntry
from .log_manager import LogManager, NullLogManager

__all__ = [
    "LogManager",
    "NullLogManager",
    "ArticleLogEntry",
    "ExecutionLogEntry",
    "ErrorLogEntry",
]
```

---

### 10-4. `main.py` への変更点（イメージ）

変更は以下の4箇所のみ。既存のロジックは変更しない。

```python
# ① インポートを追加
from logger import LogManager, ExecutionLogEntry

# ② 起動時に1回だけ初期化（PublishingConfig.from_env() の直下）
log_manager = LogManager.from_env()

# ③ 記事ループ内：save_all() の直後に追記
destinations = output_manager.save_all(article)      # 既存
edit_url = next((d for d in destinations if "wp-admin" in d), "")  # WPのedit_urlを取得
log_manager.log_article(article=article, edit_url=edit_url, result="success")

# ④ RuntimeError をキャッチして記録
# （現在は未キャッチ → v1.8.0 で try/except を追加）
try:
    destinations = output_manager.save_all(article)
    edit_url = next((d for d in destinations if "wp-admin" in d), "")
    log_manager.log_article(article=article, edit_url=edit_url, result="success")
except RuntimeError as e:
    log_manager.log_article(article=article, result="failed", error_message=str(e))
    log_manager.log_error(
        error_type="WordPressError",
        error_message=str(e),
        article_title=article.seo_title,
        source_url=article.item.url,
    )
    print(f"    [ERROR] WordPress投稿失敗: {e}")

# ⑤ 全処理完了後（完了サマリーの直後）
log_manager.log_execution(ExecutionLogEntry(
    executed_at=started_at_iso,
    finished_at=datetime.now(timezone.utc).astimezone().isoformat(),
    execution_time_sec=round(elapsed, 2),
    total_collected=total_collected,
    total_filtered=filtered_count,
    total_deduped=deduped_count,
    total_generated=planned,
    total_wp_success=wp_success_count,
    total_wp_failed=wp_failed_count,
    total_wp_skipped=0,
    api_call_count=api_call_count,
    result="success" if wp_failed_count == 0 else "partial",
))
```

---

## 11. Configuration Design

### `.env.example` への追記内容

```bash
# ─────────────────────────────────────────
# Logging（v1.8.0 追加）
# ─────────────────────────────────────────
# ログ出力の有効/無効
# true  : logs/ フォルダに実行ログを保存する（デフォルト）
# false : ログを一切保存しない（v1.7.0 以前と同じ動作）
LOG_ENABLED=true

# ログの保存先ディレクトリ（main.py からの相対パス）
# デフォルト: logs
LOG_DIR=logs
```

### Configuration First の設計意図

| 設定パターン | 動作 | ユースケース |
|-------------|------|-------------|
| 未設定（デフォルト） | `logs/` に保存 | 通常の運用 |
| `LOG_ENABLED=false` | ログ出力なし（v1.7.0 互換） | トラブルシューティング・テスト時 |
| `LOG_DIR=my_logs` | 任意のディレクトリに保存 | ディレクトリを変えたい場合 |

### ログファイルの命名規則

| 種別 | ファイル名 | 書き込み方式 |
|------|-----------|------------|
| 記事ログ | `YYYYMMDD_articles.jsonl` | 追記（1日1ファイル、実行毎に追記） |
| 実行ログ | `YYYYMMDD_execution.jsonl` | 追記（1実行1エントリー） |
| エラーログ | `YYYYMMDD_errors.jsonl` | 追記（エラー発生時のみ、ファイルなし=正常） |

---

## 12. Error Handling

### ログ書き込み自体が失敗した場合

ログ書き込みの失敗で記事生成の処理を止めてはならない。
`_append()` 内での例外は `print()` で警告するだけにとどめ、処理を続行する。

```python
def _append(self, path: Path, line: str) -> None:
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        print(f"  [LOG WARNING] ログ書き込み失敗（処理は継続します）: {e}")
```

### 各エラーケースの対応方針

| ケース | 挙動 |
|--------|------|
| `LOG_ENABLED` 未設定 | `"true"` として動作（サイレント） |
| `LOG_DIR` 未設定 | `"logs"` を使用（サイレント） |
| `LOG_DIR` のディレクトリ作成失敗 | WARNING を print して処理続行 |
| ログファイルへの書き込み失敗 | WARNING を print して処理続行 |
| `edit_url` から `post_id` が抽出できない | `post_id = 0` として記録（警告なし） |
| WordPress 未設定（`is_available() = False`） | `result = "skipped"` として記録 |

### try/except の追加について

現在（v1.7.0）の `main.py` では、`output_manager.save_all()` が投げる `RuntimeError` をキャッチしていない。
v1.8.0 では、エラーを記録するために `try/except RuntimeError` を追加する。

---

## 13. PublishingConfig との関係

### 責務の分離

| モジュール | 責務 |
|-----------|------|
| `PublishingConfig`（`src/publishing_config.py`） | WordPress 投稿ステータスを決定する |
| `LogManager`（`src/logger/log_manager.py`） | 投稿結果をファイルに記録する |

両者は互いに依存しない。`LogManager` は `PublishingConfig` を参照しない。

### publish_status の Single Source of Truth

`ArticleLogEntry.publish_status` は `ArticleData.publish_status.value` から取得する。
`PublishingConfig.resolve_status()` を再度呼び出すことはしない。

```python
# ❌ NGパターン（PublishingConfig を再参照）
publish_status = publishing_config.resolve_status(article.importance)

# ✅ OKパターン（ArticleData から取得）
publish_status = article.publish_status.value   # "draft" or "pending"
```

### v1.7.0 から引き継ぐログ対象項目

v1.7.0 設計書（`publishing_automation.md`）の「v1.8.0 への引き継ぎ内容」に記載した通り、
以下の項目を v1.8.0 で実装する。

| ログ項目 | v1.7.0 | v1.8.0 |
|---------|--------|--------|
| `publish_status` の値 | コンソール出力のみ | `ArticleLogEntry` に記録 |
| 設定値（`PUBLISH_STATUS_S/A`） | 警告時のみコンソール | `ExecutionLogEntry` に記録（将来検討） |
| 投稿ステータスの変更履歴 | 未対応 | 投稿 ID + status を `ArticleLogEntry` に記録 |

---

## 14. Future Extensions

### Phase 2: CSV エクスポート（v1.9.0 以降）

JSONL から CSV を生成するユーティリティを追加し、
Excel で投稿履歴を確認できるようにする。

```
logs/
└── export/
    └── 20260630_articles.csv   ← jsonl から変換
```

### Phase 3: ログの集計・レポート（v1.10.0 以降）

複数日分の JSONL を読み込み、
「先週の投稿数・成功率・エラー発生件数」などのサマリーを生成する。

### Phase 4: DB 移行（v2.x）

SQLite へ移行することで、期間検索・集計クエリが容易になる。
JSONL から SQLite へのマイグレーションスクリプトを提供する。

現在の設計（`ArticleLogEntry` dataclass + JSON Lines）は、
SQLite の1テーブル1行として自然に対応する。移行コストは低い。

### Phase 5: AI 改善提案（v2.x 以降）

蓄積した ArticleLog を分析し、
- 「エラーが多いソースはどこか」
- 「S評価の記事はどの時間帯に多いか」
- 「投稿頻度の傾向」

などをAIが提案できるようにする。

---

## 15. Definition of Done

v1.8.0 実装完了の判定基準。

### コード

- [ ] `src/logger/__init__.py` 新規作成
  - [ ] `LogManager` / `NullLogManager` / `ArticleLogEntry` / `ExecutionLogEntry` / `ErrorLogEntry` をエクスポート
- [ ] `src/logger/log_entry.py` 新規作成
  - [ ] `ArticleLogEntry` dataclass（全フィールド定義済み）
  - [ ] `ExecutionLogEntry` dataclass（全フィールド定義済み）
  - [ ] `ErrorLogEntry` dataclass（全フィールド定義済み）
  - [ ] 各クラスに `to_json_line()` メソッド実装
- [ ] `src/logger/log_manager.py` 新規作成
  - [ ] `LogManager.from_env()` classmethod
    - [ ] `LOG_ENABLED=false` で `NullLogManager` を返す
  - [ ] `LogManager.log_article()` 実装
    - [ ] `edit_url` から `post_id` を抽出
    - [ ] `resolve_taxonomy()` で `category_ids` / `tag_ids` を取得
    - [ ] `ArticleLogEntry` を構築して JSONL に追記
  - [ ] `LogManager.log_execution()` 実装
  - [ ] `LogManager.log_error()` 実装
  - [ ] ログ書き込み失敗時に WARNING を表示して処理続行
  - [ ] `NullLogManager` 実装（すべてのメソッドが no-op）
- [ ] `main.py` 修正
  - [ ] `from logger import LogManager, ExecutionLogEntry` 追加
  - [ ] `log_manager = LogManager.from_env()` を起動時に1回呼び出す
  - [ ] `output_manager.save_all()` を `try/except RuntimeError` で囲む
  - [ ] 成功時に `log_manager.log_article(result="success")` を呼ぶ
  - [ ] 失敗時に `log_manager.log_article(result="failed")` と `log_manager.log_error()` を呼ぶ
  - [ ] 全完了後に `log_manager.log_execution()` を呼ぶ
- [ ] `.env.example` 修正
  - [ ] `LOG_ENABLED=true` を追記
  - [ ] `LOG_DIR=logs` を追記
- [ ] `.gitignore` 修正
  - [ ] `projects/03_game_content_ai/logs/` を追記

### テスト・動作確認

- [ ] E2E テスト①：`LOG_ENABLED=true`（デフォルト）
  - [ ] 実行後に `logs/articles/YYYYMMDD_articles.jsonl` が作成されている
  - [ ] 実行後に `logs/execution/YYYYMMDD_execution.jsonl` が作成されている
  - [ ] JSONL の各フィールドが正しい値になっている（`post_id`・`slug`・`publish_status` 等）
  - [ ] 2回目の実行で同じファイルに追記される（上書きでない）
- [ ] E2E テスト②：`LOG_ENABLED=false`
  - [ ] `logs/` ディレクトリが作成されない
  - [ ] 記事生成・WordPress投稿の動作に変化がない（完全後方互換）
- [ ] E2E テスト③：WordPress投稿が失敗した場合
  - [ ] `logs/errors/YYYYMMDD_errors.jsonl` が作成される
  - [ ] `ArticleLogEntry.result = "failed"` が記録される
  - [ ] エラーが発生しても処理が止まらず、残りの記事を処理し続ける
- [ ] API 呼び出し回数が変化していないこと（1記事あたり 3回のまま）
- [ ] Release 1.0 互換維持（`LOG_ENABLED=false` 時に動作変化なし）

### ドキュメント

- [ ] `docs/CHANGELOG.md` に v1.8.0 エントリーを追加
- [ ] `docs/ROADMAP.md` の v1.8.0 を完了マークに更新
- [ ] `docs/architecture.md` に `src/logger/` パッケージと `logs/` ディレクトリを追記

### リリース

- [ ] git commit 完了
- [ ] git push 完了
- [ ] working tree clean
- [ ] API 呼び出し回数変化なし（1記事あたり 3回）
- [ ] Release 1.0 互換維持（`LOG_ENABLED=false` 時に動作変化なし）
