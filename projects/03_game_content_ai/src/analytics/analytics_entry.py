"""
Analytics 用データ構造の定義。

v1.10.0: 将来の Search Console / Google Analytics 連携を受け入れる
         データモデルを定義する。外部API呼び出しは一切行わない。

設計方針（Single Source of Truth）:
    ArticleLogEntry（v1.8.0）の値を再計算せず、そのまま参照する。
    AnalyticsEntry は外部APIから取得した追加情報のみを格納する。
"""
import json
from dataclasses import dataclass, field, asdict


@dataclass
class SearchConsoleMetrics:
    """
    Search Console から取得する検索パフォーマンス指標。
    v1.10.0 では全フィールドゼロ（placeholder）。
    将来: fetch_search_console.py がこのフィールドを埋める。
    """
    impressions: int = 0        # 検索結果への表示回数
    clicks: int = 0             # 検索結果からのクリック数
    ctr: float = 0.0            # クリック率（clicks / impressions）
    avg_position: float = 0.0   # 平均検索順位（1位が最高）


@dataclass
class GoogleAnalyticsMetrics:
    """
    Google Analytics 4 から取得するアクセス指標。
    v1.10.0 では全フィールドゼロ（placeholder）。
    v1.13.0: Google Analytics Foundation で実データが書き込まれる。

    GA4 指標名との対応:
        page_views      ← GA4: screenPageViews
        sessions        ← GA4: sessions
        bounce_rate     ← GA4: bounceRate（0.0〜1.0）
        avg_time_on_page ← GA4: averageEngagementTime（秒）
    """
    page_views: int = 0              # ページビュー数（GA4: screenPageViews）
    sessions: int = 0                # セッション数（GA4: sessions）
    bounce_rate: float = 0.0         # 直帰率（GA4: bounceRate, 0.0〜1.0）
    avg_time_on_page: float = 0.0    # 平均エンゲージメント時間（GA4: averageEngagementTime, 秒）


@dataclass
class AnalyticsEntry:
    """
    1記事・1計測日分のパフォーマンスデータ。

    post_id / slug / wp_public_url で ArticleLogEntry と紐付ける。
    v1.10.0 では data_source = "placeholder" でゼロ値のまま保存する。
    将来の外部API実装時に、実データが書き込まれる予定。

    Attributes:
        measured_at:      データ取得日（YYYY-MM-DD 形式）
        post_id:          WordPress 投稿ID（ArticleLogEntry.post_id と一致）
        slug:             WordPress slug（ArticleLogEntry.slug と一致）
        wp_public_url:    WordPress 公開URL（Search Console の page URL に対応）
        period_days:      計測期間（日数。デフォルト: 28日）
        search_console:   Search Console のパフォーマンス指標
        google_analytics: Google Analytics のパフォーマンス指標
        data_source:      データ来源（"placeholder" / "search_console" / "google_analytics"）
    """
    measured_at: str
    post_id: int
    slug: str
    wp_public_url: str
    period_days: int = 28
    search_console: SearchConsoleMetrics = field(default_factory=SearchConsoleMetrics)
    google_analytics: GoogleAnalyticsMetrics = field(default_factory=GoogleAnalyticsMetrics)
    data_source: str = "placeholder"

    def to_json_line(self) -> str:
        """JSON Lines 形式の1行文字列に変換する。"""
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class ArticleAnalysisRecord:
    """
    投稿実績（ArticleLogEntry）とパフォーマンスデータ（AnalyticsEntry）を統合した分析レコード。
    AnalyticsManager.build_analysis_record() が生成する。

    article_* 系フィールド: ArticleLogEntry からの情報（Single Source of Truth を維持）
    analytics 系フィールド: AnalyticsEntry からの情報（データなし = ゼロ値）
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
    measured_at: str              # 計測日（YYYY-MM-DD。空 = 未計測）
    period_days: int              # 計測期間（日数）
    impressions: int              # 検索表示回数
    clicks: int                   # 検索クリック数
    ctr: float                    # クリック率
    avg_position: float           # 平均検索順位
    page_views: int               # ページビュー数

    # ─── GA4 指標（v1.13.0 追加）───
    sessions: int = 0                   # セッション数（GA4: sessions）
    bounce_rate: float = 0.0            # 直帰率（GA4: bounceRate, 0.0〜1.0）
    avg_engagement_time: float = 0.0    # 平均エンゲージメント時間（GA4: averageEngagementTime, 秒）

    def has_analytics_data(self) -> bool:
        """外部APIからの実データが存在するかを返す（すべてゼロ = False）。"""
        return self.impressions > 0 or self.page_views > 0 or self.sessions > 0

    def to_json_line(self) -> str:
        """JSON Lines 形式の1行文字列に変換する。"""
        return json.dumps(asdict(self), ensure_ascii=False)


@dataclass
class AiInputRecord:
    """
    AI改善提案のための入力データ形式。
    AnalyticsManager.build_ai_input() が ArticleAnalysisRecord から生成する。

    設計方針:
        - 不要なフィールド（edit_url, error_message 等）は含めない
        - AI が判断しやすいよう、フラグ型（bool）に変換する
        - has_performance_data で「分析可能かどうか」を明示する
        - 将来の Claude API 入力として使用する
    """
    post_id: int
    slug: str
    seo_title: str
    importance: str               # "S" / "A" / "B"
    source_name: str              # ニュースソース名

    # 投稿状態フラグ
    published: bool               # publish_status="pending" かつ wp_public_url あり = True
    x_posted: bool                # x_post_status="posted" = True

    # パフォーマンス（データなし = すべてゼロ / has_performance_data=False）
    has_performance_data: bool    # impressions > 0 または page_views > 0 または sessions > 0
    impressions: int
    clicks: int
    ctr: float
    avg_position: float
    page_views: int

    # ─── GA4 指標（v1.13.0 追加）───
    sessions: int = 0                   # セッション数（GA4: sessions）
    bounce_rate: float = 0.0            # 直帰率（GA4: bounceRate, 0.0〜1.0）
    avg_engagement_time: float = 0.0    # 平均エンゲージメント時間（GA4: averageEngagementTime, 秒）

    # ─── AI改善提案用（v1.14.0 追加）───
    permalink: str | None = None        # WordPress 公開URL（AI改善提案の対象記事識別に使用）

    def to_dict(self) -> dict:
        """辞書形式に変換する（Claude API 入力時に使用）。"""
        return asdict(self)
