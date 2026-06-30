"""
Analytics データの読み書きを管理するモジュール。

Single Responsibility: analytics/ ディレクトリへのファイル I/O と
                       ArticleLogEntry + AnalyticsEntry の統合処理のみを担う。
外部API（Search Console / Google Analytics）は呼び出さない。

設計方針（Configuration First）:
    ANALYTICS_ENABLED=false → from_env() が NullAnalyticsManager を返す（デフォルト）
    ANALYTICS_ENABLED=true  → 通常の AnalyticsManager が返る
"""
import json
from datetime import date
from pathlib import Path
from typing import Iterator

from .analytics_config import AnalyticsConfig
from .analytics_entry import (
    AnalyticsEntry,
    ArticleAnalysisRecord,
    AiInputRecord,
    SearchConsoleMetrics,
    GoogleAnalyticsMetrics,
)


class AnalyticsManager:
    """
    Analytics データを logs/analytics/ へ JSON Lines 形式で書き込み、
    ArticleLogEntry との統合レコードを生成する。

    外部API呼び出しは行わない。データ構造の管理のみを担う。
    """

    def __init__(self, log_dir: Path, period_days: int = 28):
        self.log_dir = log_dir
        self.period_days = period_days

    @classmethod
    def from_env(cls, base_dir: Path | None = None) -> "AnalyticsManager | NullAnalyticsManager":
        """
        環境変数から設定を読み込み、AnalyticsManager または NullAnalyticsManager を返す。

        Args:
            base_dir: ログディレクトリの基準ディレクトリ。
                      None の場合は LOG_DIR をそのまま Path として使用する。

        Returns:
            ANALYTICS_ENABLED=true  → AnalyticsManager
            ANALYTICS_ENABLED=false → NullAnalyticsManager（デフォルト）
        """
        config = AnalyticsConfig.from_env()
        if not config.enabled:
            return NullAnalyticsManager()

        import os
        log_dir_name = os.getenv("LOG_DIR", "logs")
        if base_dir is not None:
            log_dir = base_dir / log_dir_name
        else:
            log_dir = Path(log_dir_name)

        return cls(log_dir=log_dir, period_days=config.period_days)

    def _get_analytics_path(self, date_str: str) -> Path:
        """analytics ログファイルのパスを返し、親ディレクトリを作成する。"""
        path = self.log_dir / "analytics" / f"{date_str}_analytics.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _append(self, path: Path, line: str) -> None:
        """JSON Lines 形式で1行追記する。書き込み失敗は WARNING のみ出力して続行する。"""
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as e:
            print(f"  [ANALYTICS WARNING] 書き込み失敗（処理は継続します）: {e}")

    def create_placeholder_entry(
        self,
        post_id: int,
        slug: str,
        wp_public_url: str,
    ) -> AnalyticsEntry:
        """
        外部APIデータなしのプレースホルダー AnalyticsEntry を生成する。
        v1.10.0 ではすべてゼロ値。将来の API 実装時に実データが上書きされる。
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
        """AnalyticsEntry を logs/analytics/ に追記する。"""
        date_str = entry.measured_at.replace("-", "")
        path = self._get_analytics_path(date_str)
        self._append(path, entry.to_json_line())

    def load_article_logs(self, log_dir: Path, date_str: str) -> Iterator[dict]:
        """
        logs/articles/YYYYMMDD_articles.jsonl を読み込み、dict を逐次 yield する。
        ファイルが存在しない場合は何も返さない。不正な JSON 行はスキップする。
        """
        path = log_dir / "articles" / f"{date_str}_articles.jsonl"
        if not path.exists():
            return
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    pass

    def load_analytics_logs(self, date_str: str) -> dict[int, AnalyticsEntry]:
        """
        logs/analytics/YYYYMMDD_analytics.jsonl を読み込み、
        post_id をキーとした辞書を返す。
        ファイルが存在しない場合は空の辞書を返す。不正な行はスキップする。
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
                        search_console=SearchConsoleMetrics(
                            **data.get("search_console", {})
                        ),
                        google_analytics=GoogleAnalyticsMetrics(
                            **data.get("google_analytics", {})
                        ),
                        data_source=data.get("data_source", "placeholder"),
                    )
                    result[entry.post_id] = entry
                except (KeyError, TypeError):
                    pass
        return result

    def build_analysis_record(
        self,
        article: dict,
        analytics: AnalyticsEntry | None,
    ) -> ArticleAnalysisRecord:
        """
        ArticleLogEntry（dict）と AnalyticsEntry を統合して ArticleAnalysisRecord を生成する。
        analytics が None の場合はゼロ値（未計測状態）を使用する。
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
            # v1.13.0: GA4 指標を全フィールドマッピング
            sessions=ga.sessions,
            bounce_rate=ga.bounce_rate,
            avg_engagement_time=ga.avg_time_on_page,  # GA4: averageEngagementTime
        )

    def build_ai_input(self, record: ArticleAnalysisRecord) -> AiInputRecord:
        """
        ArticleAnalysisRecord を AI 改善提案用の AiInputRecord に変換する。

        published フラグ: publish_status="pending" かつ wp_public_url が空でない場合のみ True。
        x_posted フラグ:  x_post_status="posted" の場合のみ True。
        """
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
            # v1.13.0: GA4 指標を AI 入力に反映
            sessions=record.sessions,
            bounce_rate=record.bounce_rate,
            avg_engagement_time=record.avg_engagement_time,
            # v1.14.0: permalink を AI 改善提案用に追加
            permalink=record.wp_public_url or None,
        )


class NullAnalyticsManager:
    """
    ANALYTICS_ENABLED=false のときに返されるダミー実装（デフォルト）。
    すべてのメソッドが何もしない（no-op）。
    main.py は AnalyticsManager か NullAnalyticsManager かを意識しなくてよい。
    """

    def create_placeholder_entry(self, post_id: int = 0, slug: str = "", wp_public_url: str = "") -> None:
        pass

    def save_analytics_entry(self, entry=None) -> None:
        pass

    def load_article_logs(self, log_dir=None, date_str: str = "") -> Iterator[dict]:
        return iter([])

    def load_analytics_logs(self, date_str: str = "") -> dict:
        return {}

    def build_analysis_record(self, article=None, analytics=None) -> None:
        return None

    def build_ai_input(self, record=None) -> None:
        return None
