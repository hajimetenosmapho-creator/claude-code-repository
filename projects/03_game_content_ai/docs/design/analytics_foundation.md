# v1.10.0 Analytics Foundation 設計書

作成日：2026-06-30  
対象バージョン：v1.10.0  
対象 Epic：Release 1.1 — Epic 4 Analytics Foundation  
ステータス：実装中（ChatGPT レビュー反映済み）

---

> **[ChatGPT レビュー反映 — v1.10.0]**
>
> **Logging Foundation と Analytics Foundation のデフォルト有効/無効の設計方針**
>
> | 機能 | デフォルト | 理由 |
> |------|-----------|------|
> | `LOG_ENABLED=true` | **有効** | 実行履歴を残すのは基本動作のため、すべての実行で有効にする |
> | `ANALYTICS_ENABLED=false` | **無効** | 外部API連携・分析処理に発展する基盤のため、v1.10.0 では意図的に無効化してリリースし、準備が整った段階で有効化する |
>
> この方針により、`ANALYTICS_ENABLED` を設定しない既存ユーザーには一切影響を与えない。

---

## 1. Goal

記事の投稿実績・パフォーマンスデータ・SNS状態を統合した「分析用データ構造」を設計・実装し、
将来の Search Console / Google Analytics 連携・AI改善提案に必要な基盤を整える。

現在（v1.9.0）では、投稿ログ（`logs/articles/`）とSNSステータスは記録されているが、
記事ごとの「閲覧数・検索順位・クリック率」などのパフォーマンスデータを蓄積する構造がない。

v1.10.0 では外部API連携（Search Console・Google Analytics）は行わない。
まず「将来のパフォーマンスデータを受け入れられるデータ構造」と
「AI改善提案のための入力データ形式」を設計・実装する。

---

## 2. Background

### 現状の問題点

```
v1.9.0 時点での情報管理状況
  logs/articles/YYYYMMDD_articles.jsonl → 投稿実績は記録済み
  logs/execution/YYYYMMDD_execution.jsonl → 実行サマリーは記録済み
  x_post_status → SNSステータスは記録済み
  wp_public_url → WordPress公開URLは記録済み

  ❌ 閲覧数・検索順位・クリック率 → 記録する構造なし
  ❌ Search Console との紐付け → 設計なし
  ❌ Google Analytics との紐付け → 設計なし
  ❌ AI改善提案用の統合データ → 設計なし
  ❌ 複数日分のパフォーマンス推移 → 追跡不可
```

具体的に欠けている情報：

| 情報 | v1.9.0 時点 |
|------|------------|
| 検索表示回数（impressions） | 記録する構造なし |
| 検索クリック数（clicks） | 記録する構造なし |
| クリック率（CTR） | 記録する構造なし |
| 平均検索順位（avg_position） | 記録する構造なし |
| ページ閲覧数（page_views） | 記録する構造なし |
| セッション数（sessions） | 記録する構造なし |
| AI改善提案の入力データ形式 | 未定義 |

### v1.10.0 が解決すること

| Before（v1.9.0） | After（v1.10.0） |
|-----------------|----------------|
| パフォーマンスデータの受け皿なし | `AnalyticsEntry` dataclass で構造化 |
| 記事ログと外部データが別々 | `ArticleAnalysisRecord` で統合 |
| AI提案用データ形式が未定義 | `AiInputRecord` で入力形式を定義 |
| Search Console 連携の設計なし | フィールド定義とデータモデルを整備 |
| Google Analytics 連携の設計なし | 同上 |
| analytics設定管理なし | `AnalyticsConfig` dataclass で管理 |

---

## 3. Scope

v1.10.0 で実装する範囲。

### 実装対象

| 対象 | 内容 |
|------|------|
| `src/analytics/__init__.py` | 新規作成。`AnalyticsManager` / `AnalyticsEntry` / `AiInputRecord` を公開 |
| `src/analytics/analytics_entry.py` | 新規作成。`AnalyticsEntry` / `ArticleAnalysisRecord` / `AiInputRecord` dataclass |
| `src/analytics/analytics_config.py` | 新規作成。`AnalyticsConfig` dataclass（設定管理） |
| `src/analytics/analytics_manager.py` | 新規作成。`AnalyticsManager` / `NullAnalyticsManager` |
| `.env.example` | `ANALYTICS_ENABLED` の設定例を追加 |
| `docs/design/analytics_foundation.md` | この設計書（新規作成） |

### v1.10.0 で設計・管理する情報

| フィールド | 来源 | 内容 |
|-----------|------|------|
| `post_id` | ArticleLog（既存） | WordPress 投稿ID（Search Console との紐付けキー） |
| `slug` | ArticleLog（既存） | WordPress slug（URLパス・検索キーワード分析に使用） |
| `wp_public_url` | ArticleLog（既存） | 公開URL（Search Console の page URL に対応） |
| `publish_status` | ArticleLog（既存） | draft/pending（公開済み記事のみ分析対象） |
| `x_post_status` | ArticleLog（既存） | pending/posted/skipped（SNS経由流入分析に使用） |
| `impressions` | 将来: Search Console API | 検索表示回数 |
| `clicks` | 将来: Search Console API | 検索クリック数 |
| `ctr` | 将来: Search Console API | クリック率 |
| `avg_position` | 将来: Search Console API | 平均検索順位 |
| `page_views` | 将来: GA API | ページ閲覧数 |
| `sessions` | 将来: GA API | セッション数 |
| `bounce_rate` | 将来: GA API | 直帰率 |

---

## 4. Non Goal

v1.10.0 では実装しないこと。

| 項目 | 理由 |
|------|------|
| Google Analytics API 連携 | 認証設計・APIクォータ管理が必要。将来バージョンの対象 |
| Search Console API 連携 | 同上 |
| 自動レポート生成 | データ収集基盤が整ってから着手 |
| AI改善提案の自動実行 | v2.x 以降の対象 |
| SNS効果測定の実装 | X API 連携が前提。将来バージョンの対象 |
| データベース（SQLite等）導入 | JSON Lines で十分。v2.x で検討 |
| 管理画面・可視化UI | スコープ外 |
| 外部BIツール連携 | スコープ外 |
| main.py の修正 | v1.10.0 は分析基盤の追加。記事生成フローは変更しない |
| APIコール数の増加 | v1.10.0 はAPIを呼ばない。記事生成の3回/記事を維持 |

---

## 5. User Workflow

### Before（v1.9.0）

```
1. main.py を実行する
2. 記事が投稿され、logs/articles/ にログが記録される
3. 「この記事が検索でどれくらい表示されているか」を確認したくても手段がない
4. 「どの記事をリライトすべきか」の判断材料がない
5. X投稿文は pending のまま、その後の反応は追えない
```

### After（v1.10.0）

```
1. main.py を実行する（動作は変わらない）
2. 記事が投稿され、logs/articles/ にログが記録される（変わらない）

3. [将来の運用イメージ]
   python tools/fetch_analytics.py          ← 将来実装（v1.10.0 では未実装）
     → Search Console から閲覧データを取得
     → Google Analytics からセッションデータを取得
     → logs/analytics/YYYYMMDD_analytics.jsonl に保存

4. [将来の運用イメージ]
   python tools/generate_ai_input.py        ← 将来実装
     → logs/articles/ + logs/analytics/ を統合
     → ai_input/YYYYMMDD_ai_input.json を生成
     → Claude API に入力 → 改善提案を受け取る

5. v1.10.0 での実装範囲：
   - AnalyticsEntry dataclass（将来のデータを受け入れる構造）
   - ArticleAnalysisRecord dataclass（記事ログ + 分析データの統合形式）
   - AiInputRecord dataclass（AI改善提案の入力形式）
   - AnalyticsManager（analytics/ への読み書き管理）
   - AnalyticsConfig（設定管理）
```

---

## 6. System Workflow

### v1.10.0 の全体像

```
[現在のフロー（変更なし）]

main.py
  └─ 記事生成 → WordPress投稿 → LogManager.log_article()
                                         ↓
                               logs/articles/YYYYMMDD_articles.jsonl


[v1.10.0 で追加するデータフロー（将来の外部API連携を受け入れる設計）]

logs/articles/YYYYMMDD_articles.jsonl
        │
        │ ArticleLogEntry を読み込む
        ↓
AnalyticsManager.load_article_logs()
        │
        │ 外部APIデータ（Search Console / Google Analytics）を追加
        │ ← v1.10.0 では空データ（将来のAPIが書き込む予定）
        ↓
ArticleAnalysisRecord（統合レコード）
        │
        │ AI改善提案用フォーマットに変換
        ↓
AiInputRecord
        │
        │ logs/ai_inputs/YYYYMMDD_ai_input.jsonl に保存
        ↓
（将来）Claude API → 改善提案テキストを受け取る
```

### Analytics データフロー（将来設計）

```
Search Console API（将来）
  └─ impressions / clicks / ctr / avg_position
        │
        ↓
AnalyticsEntry.search_console フィールドに格納
        │
logs/analytics/YYYYMMDD_analytics.jsonl に保存
        │
        ↓
AnalyticsManager.load_analytics()
  └─ post_id / slug をキーにして ArticleLogEntry と結合
        ↓
ArticleAnalysisRecord（統合レコード）
```

---

## 7. Analytics Data Model

### 7-1. AnalyticsEntry dataclass

外部API（Search Console / Google Analytics）から取得したパフォーマンスデータを格納する。
v1.10.0 では空のプレースホルダーとして存在する。将来の API 実装時に値が埋まる。

```python
@dataclass
class SearchConsoleMetrics:
    """Search Console から取得するパフォーマンス指標。"""
    impressions: int = 0        # 検索結果への表示回数
    clicks: int = 0             # 検索結果からのクリック数
    ctr: float = 0.0            # クリック率（clicks / impressions）
    avg_position: float = 0.0   # 平均検索順位（1位が最高）


@dataclass
class GoogleAnalyticsMetrics:
    """Google Analytics から取得するパフォーマンス指標。"""
    page_views: int = 0         # ページビュー数
    sessions: int = 0           # セッション数
    bounce_rate: float = 0.0    # 直帰率（0.0〜1.0）
    avg_time_on_page: float = 0.0  # 平均滞在時間（秒）


@dataclass
class AnalyticsEntry:
    """
    1記事のパフォーマンスデータ。
    post_id / slug で ArticleLogEntry と紐付ける。

    measured_at:   データ取得日（YYYY-MM-DD 形式）
    post_id:       WordPress 投稿ID（ArticleLogEntry.post_id と一致）
    slug:          WordPress slug（ArticleLogEntry.slug と一致）
    wp_public_url: WordPress 公開URL（Search Console の page URL に対応）
    period_days:   計測期間（日数。例: 28 = 過去28日間）
    search_console: Search Console のパフォーマンス指標
    google_analytics: Google Analytics のパフォーマンス指標
    data_source:   データ元（"search_console" / "google_analytics" / "manual" / "placeholder"）
    """
    measured_at: str                                      # "YYYY-MM-DD"
    post_id: int                                          # ArticleLogEntry.post_id
    slug: str                                             # ArticleLogEntry.slug
    wp_public_url: str                                    # ArticleLogEntry.wp_public_url
    period_days: int = 28                                 # 計測期間（デフォルト: 28日）
    search_console: SearchConsoleMetrics = field(default_factory=SearchConsoleMetrics)
    google_analytics: GoogleAnalyticsMetrics = field(default_factory=GoogleAnalyticsMetrics)
    data_source: str = "placeholder"                      # v1.10.0 はすべて placeholder

    def to_json_line(self) -> str:
        """JSON Lines 形式の1行文字列に変換する。"""
        return json.dumps(asdict(self), ensure_ascii=False)
```

### JSON Lines 出力例（v1.10.0 時点、データなし状態）

```json
{"measured_at": "2026-06-30", "post_id": 10340, "slug": "ps6-announced-20260630", "wp_public_url": "https://nozo3-kao6.tokyo/ps6-announced-20260630/", "period_days": 28, "search_console": {"impressions": 0, "clicks": 0, "ctr": 0.0, "avg_position": 0.0}, "google_analytics": {"page_views": 0, "sessions": 0, "bounce_rate": 0.0, "avg_time_on_page": 0.0}, "data_source": "placeholder"}
```

### JSON Lines 出力例（将来: Search Console 連携後）

```json
{"measured_at": "2026-07-28", "post_id": 10340, "slug": "ps6-announced-20260630", "wp_public_url": "https://nozo3-kao6.tokyo/ps6-announced-20260630/", "period_days": 28, "search_console": {"impressions": 1200, "clicks": 45, "ctr": 0.0375, "avg_position": 12.3}, "google_analytics": {"page_views": 120, "sessions": 98, "bounce_rate": 0.65, "avg_time_on_page": 182.5}, "data_source": "search_console"}
```

---

### 7-2. ArticleAnalysisRecord dataclass

`ArticleLogEntry`（投稿実績）と `AnalyticsEntry`（パフォーマンス）を統合した分析用レコード。
AI改善提案の入力として使用する。

```python
@dataclass
class ArticleAnalysisRecord:
    """
    投稿実績とパフォーマンスデータを統合した分析レコード。
    AnalyticsManager.build_analysis_record() が生成する。

    article_*:   ArticleLogEntry からの情報（投稿実績）
    analytics_*: AnalyticsEntry からの情報（パフォーマンス）
    """
    # ─── 記事情報（ArticleLogEntry より）───
    post_id: int
    slug: str
    seo_title: str
    importance: str               # "S" / "A" / "B"
    publish_status: str           # "draft" / "pending"
    logged_at: str                # 投稿記録日時（ISO 8601）
    source_name: str              # ニュースソース名
    wp_public_url: str            # WordPress 公開URL
    x_post_status: str            # "pending" / "posted" / "skipped"

    # ─── パフォーマンス情報（AnalyticsEntry より）───
    measured_at: str              # 計測日（"YYYY-MM-DD"。空 = 未計測）
    period_days: int              # 計測期間（日数）
    impressions: int              # 検索表示回数
    clicks: int                   # 検索クリック数
    ctr: float                    # クリック率
    avg_position: float           # 平均検索順位
    page_views: int               # ページビュー数

    def has_analytics_data(self) -> bool:
        """外部APIからのデータが存在するかを返す。"""
        return self.impressions > 0 or self.page_views > 0

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)
```

---

### 7-3. AiInputRecord dataclass

Claude API への入力用データ形式。
将来の AI 改善提案機能で使用する。

```python
@dataclass
class AiInputRecord:
    """
    AI改善提案のための入力データ。
    ArticleAnalysisRecord を変換して生成する。

    設計方針:
      - 不要なフィールド（edit_url, error_message 等）は含めない
      - AI が判断しやすいよう、フィールドを整理・変換する
      - has_performance_data で「分析可能かどうか」を明示する
    """
    # 記事属性
    post_id: int
    slug: str
    seo_title: str
    importance: str
    source_name: str

    # 投稿状態
    published: bool               # publish_status = "pending" かつ wp_public_url あり = True
    x_posted: bool                # x_post_status = "posted" = True

    # パフォーマンス（データなし = すべて 0）
    has_performance_data: bool    # impressions > 0 または page_views > 0
    impressions: int
    clicks: int
    ctr: float
    avg_position: float
    page_views: int

    def to_dict(self) -> dict:
        return asdict(self)
```

---

### 7-4. データ間の紐付けキー

| フィールド | 用途 | 照合先 |
|-----------|------|--------|
| `post_id` | 主キー（最も確実） | ArticleLogEntry ↔ AnalyticsEntry |
| `slug` | Search Console ページURL の構成要素 | `wp_public_url` の `/slug/` 部分 |
| `wp_public_url` | Search Console の page URL と完全一致 | Search Console レスポンスの `page` フィールド |

---

## 8. Directory Structure

```
projects/03_game_content_ai/
│
├── main.py                              （変更なし）
├── .env.example                         ← MODIFIED（ANALYTICS_ENABLED 追加）
│
├── logs/                                （既存・.gitignore 対象）
│   ├── articles/                        （既存・v1.8.0）
│   ├── execution/                       （既存・v1.8.0）
│   ├── errors/                          （既存・v1.8.0）
│   └── analytics/                       ← NEW（v1.10.0）
│       └── YYYYMMDD_analytics.jsonl     ← 日付別・分析データ（placeholder含む）
│
├── docs/
│   └── design/
│       ├── publishing_automation.md     （変更なし）
│       ├── logging_foundation.md        （変更なし）
│       ├── sns_foundation.md            （変更なし）
│       └── analytics_foundation.md     ← この設計書（NEW）
│
└── src/
    ├── analytics/                       ← NEW パッケージ
    │   ├── __init__.py                  ← AnalyticsManager / AnalyticsEntry 等を公開
    │   ├── analytics_entry.py           ← SearchConsoleMetrics / GoogleAnalyticsMetrics /
    │   │                                    AnalyticsEntry / ArticleAnalysisRecord / AiInputRecord
    │   ├── analytics_config.py          ← AnalyticsConfig dataclass
    │   └── analytics_manager.py         ← AnalyticsManager / NullAnalyticsManager
    │
    ├── logger/                          （変更なし・v1.8.0）
    ├── sns_config.py                    （変更なし・v1.9.0）
    ├── publishing_config.py             （変更なし）
    └── outputs/                         （変更なし）
```

---

## 9. Module Design

### 9-1. `src/analytics/analytics_entry.py`

分析データの dataclass 群を定義する。シリアライズヘルパーを含む。

```python
import json
from dataclasses import dataclass, field, asdict


@dataclass
class SearchConsoleMetrics:
    impressions: int = 0
    clicks: int = 0
    ctr: float = 0.0
    avg_position: float = 0.0


@dataclass
class GoogleAnalyticsMetrics:
    page_views: int = 0
    sessions: int = 0
    bounce_rate: float = 0.0
    avg_time_on_page: float = 0.0


@dataclass
class AnalyticsEntry:
    measured_at: str
    post_id: int
    slug: str
    wp_public_url: str
    period_days: int = 28
    search_console: SearchConsoleMetrics = field(default_factory=SearchConsoleMetrics)
    google_analytics: GoogleAnalyticsMetrics = field(default_factory=GoogleAnalyticsMetrics)
    data_source: str = "placeholder"

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class ArticleAnalysisRecord:
    post_id: int
    slug: str
    seo_title: str
    importance: str
    publish_status: str
    logged_at: str
    source_name: str
    wp_public_url: str
    x_post_status: str
    measured_at: str
    period_days: int
    impressions: int
    clicks: int
    ctr: float
    avg_position: float
    page_views: int

    def has_analytics_data(self) -> bool:
        return self.impressions > 0 or self.page_views > 0

    def to_json_line(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class AiInputRecord:
    post_id: int
    slug: str
    seo_title: str
    importance: str
    source_name: str
    published: bool
    x_posted: bool
    has_performance_data: bool
    impressions: int
    clicks: int
    ctr: float
    avg_position: float
    page_views: int

    def to_dict(self) -> dict:
        return asdict(self)
```

---

### 9-2. `src/analytics/analytics_config.py`

Analytics 機能の有効/無効と設定値を管理する。
Logging Foundation の `LogManager.from_env()` と同じ Configuration First パターンを採用する。

```python
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass
class AnalyticsConfig:
    """
    Analytics 機能の設定。.env から読み込む。

    設計方針（Configuration First）:
        - ANALYTICS_ENABLED=false → NullAnalyticsManager を返す（デフォルト動作維持）
        - ANALYTICS_ENABLED=true  → AnalyticsManager を返す

    Attributes:
        enabled:        Analytics 機能の有効/無効
        analytics_dir:  analytics ログの保存先（logs/ 配下のサブディレクトリ）
        period_days:    パフォーマンス計測期間（日数。デフォルト: 28）
    """
    enabled: bool = False          # デフォルト false（将来の機能のため）
    analytics_dir: str = "analytics"
    period_days: int = 28

    @classmethod
    def from_env(cls) -> "AnalyticsConfig":
        enabled = os.getenv("ANALYTICS_ENABLED", "false").lower().strip() == "true"
        analytics_dir = os.getenv("ANALYTICS_DIR", "analytics")
        period_days_str = os.getenv("ANALYTICS_PERIOD_DAYS", "28")
        try:
            period_days = int(period_days_str)
        except ValueError:
            period_days = 28
        return cls(
            enabled=enabled,
            analytics_dir=analytics_dir,
            period_days=period_days,
        )
```

---

### 9-3. `src/analytics/analytics_manager.py`

`AnalyticsManager` は `LogManager` と同じ責務分離・NullObject パターンを採用する。
ログの読み込み・統合・書き込みを担う。

```python
import json
from datetime import date
from pathlib import Path
from typing import Iterator

from .analytics_entry import (
    AnalyticsEntry, ArticleAnalysisRecord, AiInputRecord,
    SearchConsoleMetrics, GoogleAnalyticsMetrics,
)


class AnalyticsManager:
    """
    Analytics データの読み書きを管理する。
    Single Responsibility: analytics/ へのファイル I/O のみを担う。
    """

    def __init__(self, log_dir: Path, period_days: int = 28):
        self.log_dir = log_dir
        self.period_days = period_days

    def _get_analytics_path(self, date_str: str) -> Path:
        path = self.log_dir / "analytics" / f"{date_str}_analytics.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _append(self, path: Path, line: str) -> None:
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as e:
            print(f"  [ANALYTICS WARNING] 書き込み失敗（処理は継続します）: {e}")

    def create_placeholder_entry(self, post_id: int, slug: str, wp_public_url: str) -> AnalyticsEntry:
        """
        将来の API 連携用のプレースホルダーエントリーを生成する。
        v1.10.0 では実データなし（すべてゼロ）。
        """
        return AnalyticsEntry(
            measured_at=date.today().isoformat(),
            post_id=post_id,
            slug=slug,
            wp_public_url=wp_public_url,
            period_days=self.period_days,
            search_console=SearchConsoleMetrics(),
            google_analytics=GoogleAnalyticsMetrics(),
            data_source="placeholder",
        )

    def save_analytics_entry(self, entry: AnalyticsEntry) -> None:
        """AnalyticsEntry を analytics/ に追記する。"""
        date_str = entry.measured_at.replace("-", "")
        path = self._get_analytics_path(date_str)
        self._append(path, entry.to_json_line())

    def load_article_logs(self, log_dir: Path, date_str: str) -> Iterator[dict]:
        """
        logs/articles/YYYYMMDD_articles.jsonl を読み込み、dict を逐次 yield する。
        ファイルが存在しない場合は空のイテレーターを返す。
        """
        path = log_dir / "articles" / f"{date_str}_articles.jsonl"
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        pass

    def load_analytics_logs(self, date_str: str) -> dict[int, AnalyticsEntry]:
        """
        logs/analytics/YYYYMMDD_analytics.jsonl を読み込み、
        post_id をキーとした dict を返す。
        """
        path = self._get_analytics_path(date_str)
        result: dict[int, AnalyticsEntry] = {}
        if not path.exists():
            return result
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    data = json.loads(line)
                    entry = AnalyticsEntry(
                        measured_at=data["measured_at"],
                        post_id=data["post_id"],
                        slug=data["slug"],
                        wp_public_url=data.get("wp_public_url", ""),
                        period_days=data.get("period_days", 28),
                        search_console=SearchConsoleMetrics(**data.get("search_console", {})),
                        google_analytics=GoogleAnalyticsMetrics(**data.get("google_analytics", {})),
                        data_source=data.get("data_source", "placeholder"),
                    )
                    result[entry.post_id] = entry
                except (KeyError, TypeError):
                    pass
        return result

    def build_analysis_record(
        self, article: dict, analytics: AnalyticsEntry | None
    ) -> ArticleAnalysisRecord:
        """
        ArticleLogEntry（dict）と AnalyticsEntry を統合して
        ArticleAnalysisRecord を生成する。
        analytics が None の場合はゼロ値を使用する。
        """
        sc = analytics.search_console if analytics else SearchConsoleMetrics()
        ga = analytics.google_analytics if analytics else GoogleAnalyticsMetrics()
        measured_at = analytics.measured_at if analytics else ""
        period_days = analytics.period_days if analytics else self.period_days

        return ArticleAnalysisRecord(
            post_id=article.get("post_id", 0),
            slug=article.get("slug", ""),
            seo_title=article.get("seo_title", ""),
            importance=article.get("importance", ""),
            publish_status=article.get("publish_status", ""),
            logged_at=article.get("logged_at", ""),
            source_name=article.get("source_name", ""),
            wp_public_url=article.get("wp_public_url", ""),
            x_post_status=article.get("x_post_status", ""),
            measured_at=measured_at,
            period_days=period_days,
            impressions=sc.impressions,
            clicks=sc.clicks,
            ctr=sc.ctr,
            avg_position=sc.avg_position,
            page_views=ga.page_views,
        )

    def build_ai_input(self, record: ArticleAnalysisRecord) -> AiInputRecord:
        """ArticleAnalysisRecord を AI 改善提案用の AiInputRecord に変換する。"""
        published = bool(record.publish_status == "pending" and record.wp_public_url)
        x_posted = record.x_post_status == "posted"
        return AiInputRecord(
            post_id=record.post_id,
            slug=record.slug,
            seo_title=record.seo_title,
            importance=record.importance,
            source_name=record.source_name,
            published=published,
            x_posted=x_posted,
            has_performance_data=record.has_analytics_data(),
            impressions=record.impressions,
            clicks=record.clicks,
            ctr=record.ctr,
            avg_position=record.avg_position,
            page_views=record.page_views,
        )


class NullAnalyticsManager:
    """
    ANALYTICS_ENABLED=false のときに使用するダミー実装。
    すべてのメソッドが何もしない（no-op）。
    """

    def create_placeholder_entry(self, post_id=0, slug="", wp_public_url="") -> None:
        pass

    def save_analytics_entry(self, entry=None) -> None:
        pass

    def load_article_logs(self, log_dir=None, date_str=""):
        return iter([])

    def load_analytics_logs(self, date_str="") -> dict:
        return {}

    def build_analysis_record(self, article=None, analytics=None) -> None:
        return None

    def build_ai_input(self, record=None) -> None:
        return None
```

---

### 9-4. `src/analytics/__init__.py`

```python
from .analytics_entry import (
    SearchConsoleMetrics,
    GoogleAnalyticsMetrics,
    AnalyticsEntry,
    ArticleAnalysisRecord,
    AiInputRecord,
)
from .analytics_config import AnalyticsConfig
from .analytics_manager import AnalyticsManager, NullAnalyticsManager

__all__ = [
    "SearchConsoleMetrics",
    "GoogleAnalyticsMetrics",
    "AnalyticsEntry",
    "ArticleAnalysisRecord",
    "AiInputRecord",
    "AnalyticsConfig",
    "AnalyticsManager",
    "NullAnalyticsManager",
]
```

---

## 10. Configuration Design

### `.env.example` への追記内容

```bash
# ─────────────────────────────────────────
# Analytics Foundation（v1.10.0 追加）
# ─────────────────────────────────────────
# Analytics 機能の有効/無効
# false : Analytics機能を使用しない（デフォルト。v1.9.0 以前と同じ動作）
# true  : AnalyticsManager を有効化（将来のAPI連携・AI改善提案の準備として）
ANALYTICS_ENABLED=false

# Analytics ログの保存先ディレクトリ（LOG_DIR 配下のサブディレクトリ名）
# デフォルト: analytics（logs/analytics/ に保存されます）
# ANALYTICS_DIR=analytics

# パフォーマンスデータの計測期間（日数）
# デフォルト: 28（過去28日間）
# ANALYTICS_PERIOD_DAYS=28
```

### Configuration First の設計意図

| 設定パターン | 動作 | ユースケース |
|-------------|------|-------------|
| 未設定（デフォルト） | `ANALYTICS_ENABLED=false` として動作 | v1.9.0 以前と完全互換 |
| `ANALYTICS_ENABLED=false` | `NullAnalyticsManager`（何もしない） | 通常の記事生成のみ |
| `ANALYTICS_ENABLED=true` | `AnalyticsManager` を有効化 | analytics/ へのデータ蓄積を開始 |

### 設定値のデフォルト一覧

| 環境変数 | デフォルト | 型 | 説明 |
|---------|-----------|-----|------|
| `ANALYTICS_ENABLED` | `"false"` | bool | Analytics 機能の有効/無効 |
| `ANALYTICS_DIR` | `"analytics"` | str | analytics ログの保存先サブディレクトリ |
| `ANALYTICS_PERIOD_DAYS` | `"28"` | int | パフォーマンス計測期間（日数） |

---

## 11. Logging Foundation との関係

### 責務の分離

| モジュール | 責務 |
|-----------|------|
| `LogManager`（v1.8.0） | 投稿実績（記事生成・WordPress投稿・エラー）をファイルに記録する |
| `AnalyticsManager`（v1.10.0） | パフォーマンスデータの読み書きと統合レコードの生成を担う |

両者は互いに直接依存しない。`AnalyticsManager` は `LogManager` が書いた
`logs/articles/` の JSONL を **読み込む** が、`LogManager` のクラスやインスタンスには依存しない。

### データの流れ（Single Source of Truth の維持）

```
ArticleLogEntry（v1.8.0 が記録）
    ├─ post_id    →  AnalyticsEntry の照合キー
    ├─ slug       →  Search Console の page URL 構成要素
    ├─ wp_public_url → Search Console の照合キー
    ├─ publish_status → AI入力の published フラグの計算元
    └─ x_post_status → AI入力の x_posted フラグの計算元
```

`AnalyticsManager` は `ArticleLogEntry` の値を **再計算しない**。
`logs/articles/` から読み込んだ値をそのまま使用する。

### ファイル命名の統一

既存の `logs/` 配下のディレクトリ命名規則を踏襲する。

```
logs/
├── articles/   YYYYMMDD_articles.jsonl   （v1.8.0）
├── execution/  YYYYMMDD_execution.jsonl  （v1.8.0）
├── errors/     YYYYMMDD_errors.jsonl     （v1.8.0）
└── analytics/  YYYYMMDD_analytics.jsonl  （v1.10.0・NEW）
```

---

## 12. SNS Foundation との関係

### x_post_status との連携

`ArticleLogEntry.x_post_status`（v1.9.0 で追加）は、
`AiInputRecord.x_posted` フラグの計算に使用する。

```python
# AnalyticsManager.build_ai_input() 内
x_posted = record.x_post_status == "posted"  # "posted" のみ True
```

| x_post_status | x_posted | 意味 |
|--------------|---------|------|
| `"pending"` | `False` | X未投稿。SNS経由流入は計測不可 |
| `"posted"` | `True` | X投稿済み。SNS経由流入と記事パフォーマンスの相関分析が可能 |
| `"skipped"` | `False` | SNS無効。SNS効果測定の対象外 |

### wp_public_url との連携

`ArticleLogEntry.wp_public_url`（v1.9.0 で追加）は、
Search Console の照合キーとして使用する。

```
Search Console が返す page URL:
  "https://nozo3-kao6.tokyo/ps6-announced-20260630/"

ArticleLogEntry.wp_public_url:
  "https://nozo3-kao6.tokyo/ps6-announced-20260630/"  ← 完全一致
```

この設計により、Search Console API レスポンスと `ArticleLogEntry` の紐付けが
`wp_public_url` の完全一致で可能になる。

### 将来の SNS 効果測定設計（v1.9.0 との連携）

```
[将来設計 - 現在は未実装]

x_post_status = "posted" の記事:
  ├─ x_posted_at（X投稿日時）→ 投稿直後のpage_views急増を検出
  ├─ x_post_url → X側のエンゲージメント取得
  └─ GA sessions の時系列変化 → SNS経由セッションと相関分析
```

---

## 13. WordPress との関係

### post_id の活用

`ArticleLogEntry.post_id`（v1.8.0 で記録開始）は、
analytics データの照合キーとして使用する。

```
post_id = 10340
  → ArticleLogEntry で投稿実績を検索
  → AnalyticsEntry でパフォーマンスデータを検索
  → ArticleAnalysisRecord で統合
```

### 現時点の制約（v1.10.0）

v1.8.0 の設計書に記載の通り、`post_id` は現在 `edit_url` の URL パラメータから
正規表現で抽出する暫定実装である（`?post=(\d+)` のパターン）。

`edit_url` が空（WordPress 未設定・投稿失敗）の場合は `post_id = 0` になる。
`post_id = 0` の記事は Analytics データと紐付けられないため、Analytics 対象外とする。

```python
# AnalyticsManager での扱い
if article.get("post_id", 0) == 0:
    continue  # WordPress 未設定または投稿失敗記事はスキップ
```

### publish_status との関係

検索エンジンにインデックスされるのは公開された記事のみ。
`publish_status = "draft"` の記事は Search Console データが存在しないため、
`AiInputRecord.published = False` として扱う。

| publish_status | wp_public_url | published (AiInputRecord) |
|---------------|--------------|--------------------------|
| `"pending"` | あり | `True` |
| `"draft"` | あり | `False`（非公開のため） |
| `""` | なし | `False` |

---

## 14. Error Handling

### Analytics 書き込み失敗時

Logging Foundation と同じ方針。
書き込み失敗は WARNING を出力するだけで、記事生成フローを止めない。

```python
def _append(self, path: Path, line: str) -> None:
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError as e:
        print(f"  [ANALYTICS WARNING] 書き込み失敗（処理は継続します）: {e}")
```

### 各エラーケースの対応方針

| ケース | 挙動 |
|--------|------|
| `ANALYTICS_ENABLED` 未設定 | `"false"` として動作（NullAnalyticsManager） |
| `ANALYTICS_PERIOD_DAYS` が数値以外 | `28` にフォールバック |
| `logs/articles/` が存在しない | 空のイテレーターを返す（エラーなし） |
| `logs/analytics/` の書き込み失敗 | WARNING を print して続行 |
| JSONL の1行が不正なJSON | その行をスキップして続行 |
| `post_id = 0` の記事 | analytics 統合対象外としてスキップ |
| AnalyticsEntry の `data_source` が不明 | そのまま記録（将来の拡張に備える） |

---

## 15. Future Extensions

### Phase 1: Search Console 連携（v1.11.0 想定）

`AnalyticsEntry.search_console` フィールドへのデータ投入を実装する。
Search Console API からのデータ取得・変換・保存を担う `SearchConsoleClient` を追加する。

```
tools/
└── fetch_search_console.py    ← 新規（Search Console API を呼ぶ独立スクリプト）

実行タイミング: main.py とは独立して定期実行（毎日・週次等）
```

### Phase 2: Google Analytics 連携（v1.12.0 想定）

`AnalyticsEntry.google_analytics` フィールドへのデータ投入を実装する。
GA4 API からのデータ取得・変換・保存を担う `GoogleAnalyticsClient` を追加する。

### Phase 3: AI 改善提案（v2.0 想定）

`AiInputRecord` を Claude API に渡し、以下を提案させる。

```
提案の例:
  - 「SEOタイトルの改善案（クリック率 0.5% → 2% 以上を目指す）」
  - 「検索順位が低い記事のリライト優先順位」
  - 「X投稿文のエンゲージメント改善提案」
  - 「カテゴリ・タグ設定の最適化案」
```

### Phase 4: AI 入力バッチ生成スクリプト（v1.10.x 想定）

複数日分の ArticleLog + AnalyticsLog を統合し、
`ai_input/YYYYMMDD_ai_input.jsonl` を一括生成するスクリプトを追加する。

```
tools/
└── generate_ai_input.py       ← 新規（AnalyticsManager を使った集計スクリプト）
```

### Phase 5: 期間集計レポート（v1.10.x 想定）

週次・月次で `logs/` を集計し、
「記事ごとの impressions・clicks・CTR の推移グラフ」をテキストサマリーとして出力する。

### Phase 6: DB 移行（v2.x）

SQLite に移行することで、期間検索・集計クエリが容易になる。
`AnalyticsEntry` / `ArticleAnalysisRecord` の dataclass はそのまま
SQLite テーブルの1行として対応する設計になっている。移行コストは低い。

---

## 16. Definition of Done

v1.10.0 実装完了の判定基準。

### コード

- [ ] `src/analytics/__init__.py` 新規作成
  - [ ] `AnalyticsManager` / `NullAnalyticsManager` / 全 dataclass をエクスポート
- [ ] `src/analytics/analytics_entry.py` 新規作成
  - [ ] `SearchConsoleMetrics` dataclass
  - [ ] `GoogleAnalyticsMetrics` dataclass
  - [ ] `AnalyticsEntry` dataclass（`to_json_line()` 含む）
  - [ ] `ArticleAnalysisRecord` dataclass（`has_analytics_data()` / `to_json_line()` 含む）
  - [ ] `AiInputRecord` dataclass（`to_dict()` 含む）
- [ ] `src/analytics/analytics_config.py` 新規作成
  - [ ] `AnalyticsConfig.from_env()` classmethod
  - [ ] `ANALYTICS_ENABLED=false` で `NullAnalyticsManager` を返す
  - [ ] `ANALYTICS_PERIOD_DAYS` が不正値の場合 `28` にフォールバック
- [ ] `src/analytics/analytics_manager.py` 新規作成
  - [ ] `AnalyticsManager.create_placeholder_entry()` 実装
  - [ ] `AnalyticsManager.save_analytics_entry()` 実装
  - [ ] `AnalyticsManager.load_article_logs()` 実装
  - [ ] `AnalyticsManager.load_analytics_logs()` 実装（post_id キーの dict を返す）
  - [ ] `AnalyticsManager.build_analysis_record()` 実装
  - [ ] `AnalyticsManager.build_ai_input()` 実装
  - [ ] 書き込み失敗時に WARNING を print して処理続行
  - [ ] `NullAnalyticsManager` 実装（すべてのメソッドが no-op）
- [ ] `.env.example` 修正
  - [ ] `ANALYTICS_ENABLED=false` を追記
  - [ ] `ANALYTICS_DIR` / `ANALYTICS_PERIOD_DAYS` をコメント付きで追記
- [ ] `main.py` は変更しない（v1.10.0 はフローに影響しない）

### テスト・動作確認

- [ ] E2E テスト①：`AnalyticsEntry` の生成・JSON シリアライズ
  - [ ] `create_placeholder_entry()` が正しい dataclass を返す
  - [ ] `to_json_line()` で `data_source = "placeholder"` が出力される
  - [ ] JSON に `search_console` / `google_analytics` が含まれる（ゼロ値）
- [ ] E2E テスト②：`ArticleLogEntry` との統合
  - [ ] `load_article_logs()` が既存の JSONL を正しく読み込む
  - [ ] `build_analysis_record()` が `ArticleAnalysisRecord` を正しく生成する
  - [ ] `has_analytics_data()` が `False` を返す（データなし状態）
- [ ] E2E テスト③：`AiInputRecord` の生成
  - [ ] `build_ai_input()` が `AiInputRecord` を正しく生成する
  - [ ] `published` フラグが `publish_status` と `wp_public_url` から正しく計算される
  - [ ] `x_posted` フラグが `x_post_status` から正しく計算される
- [ ] E2E テスト④：`ANALYTICS_ENABLED=false`（デフォルト）
  - [ ] `NullAnalyticsManager` が返る
  - [ ] `logs/analytics/` が作成されない
  - [ ] 記事生成・WordPress投稿の動作に変化がない
- [ ] API 呼び出し回数が変化していないこと（1記事あたり 3回のまま）
- [ ] Release 1.0 / v1.7.0 / v1.8.0 / v1.9.0 互換維持

### ドキュメント

- [ ] `docs/CHANGELOG.md` に v1.10.0 エントリーを追加
- [ ] `docs/ROADMAP.md` の v1.10.0 を完了マークに更新
- [ ] `docs/architecture.md` に `src/analytics/` パッケージと `logs/analytics/` を追記

### リリース

- [ ] git commit 完了
- [ ] git push 完了
- [ ] working tree clean
- [ ] API 呼び出し回数変化なし（1記事あたり 3回）
- [ ] main.py の動作変化なし（ANALYTICS_ENABLED=false 時）
