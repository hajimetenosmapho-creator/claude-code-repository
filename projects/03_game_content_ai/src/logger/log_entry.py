"""
ログエントリーの dataclass 定義。

各クラスは1レコード分のデータを保持し、to_json_line() で JSON Lines 形式に変換する。
"""
import json
from dataclasses import dataclass, asdict
from sns_config import SnsPostStatus


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

    # ─── SNS フィールド（v1.9.0 追加・デフォルト値ありで後方互換）───
    wp_public_url: str = ""                           # WordPress 公開予定URL（BLOG_BASE_URL + slug）
    x_post_text: str = ""                             # X投稿文（ブログURL置換済みの最終形）
    x_post_status: SnsPostStatus = SnsPostStatus.PENDING  # X投稿ステータス
    x_post_url: str = ""                              # X投稿後のポストURL（将来のX API対応時に記録）

    def to_json_line(self) -> str:
        """JSON Lines 形式の1行文字列に変換する。
        SnsPostStatus は str を継承するため json.dumps が自動的に文字列として扱う。
        """
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
        """JSON Lines 形式の1行文字列に変換する。"""
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
        """JSON Lines 形式の1行文字列に変換する。"""
        return json.dumps(asdict(self), ensure_ascii=False)
