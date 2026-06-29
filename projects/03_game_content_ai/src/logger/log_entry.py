"""
ログエントリーの dataclass 定義。

各クラスは1レコード分のデータを保持し、to_json_line() で JSON Lines 形式に変換する。
"""
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
