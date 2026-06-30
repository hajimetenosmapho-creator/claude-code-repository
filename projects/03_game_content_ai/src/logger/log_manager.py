"""
ログをローカルの JSON Lines ファイルへ書き込むモジュール。

Single Responsibility: ファイルへの書き込み管理のみを担う。
記事生成・WordPress 投稿処理には一切関与しない。

設計方針（Configuration First）:
    LOG_ENABLED=false → from_env() が NullLogManager を返す（Release 1.0 互換）
    LOG_ENABLED=true  → 通常のログ保存が行われる（デフォルト）
"""
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from .log_entry import ArticleLogEntry, ExecutionLogEntry, ErrorLogEntry


class LogManager:
    """
    ログを logs/ ディレクトリへ JSON Lines 形式で書き込む。

    ディレクトリ構造:
        logs/
        ├── articles/YYYYMMDD_articles.jsonl   ← 1記事ずつ追記
        ├── execution/YYYYMMDD_execution.jsonl ← 実行終了時に追記
        └── errors/YYYYMMDD_errors.jsonl       ← エラー時のみ追記（エラーなしは作成されない）
    """

    def __init__(self, log_dir: Path):
        self.log_dir = log_dir

    @classmethod
    def from_env(cls, base_dir: Path | None = None) -> "LogManager | NullLogManager":
        """
        環境変数から設定を読み込む。

        Args:
            base_dir: ログディレクトリの基準ディレクトリ。
                      指定した場合は base_dir / LOG_DIR を使用する。
                      None の場合は LOG_DIR をそのまま Path として使用する。

        Returns:
            LogManager または NullLogManager。
            LOG_ENABLED=false の場合は NullLogManager（Release 1.0 互換）。
        """
        enabled = os.getenv("LOG_ENABLED", "true").lower().strip()
        if enabled == "false":
            return NullLogManager()

        log_dir_name = os.getenv("LOG_DIR", "logs")
        if base_dir is not None:
            log_dir = base_dir / log_dir_name
        else:
            log_dir = Path(log_dir_name)

        return cls(log_dir=log_dir)

    def _get_log_path(self, subdir: str, date_str: str) -> Path:
        """ログファイルのパスを生成し、親ディレクトリが存在しない場合は作成する。"""
        path = self.log_dir / subdir / f"{date_str}_{subdir}.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    def _append(self, path: Path, line: str) -> None:
        """JSON Lines 形式で1行追記する。書き込み失敗時は警告のみ出力して処理を続行する。"""
        try:
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
        except OSError as e:
            print(f"  [LOG WARNING] ログ書き込み失敗（処理は継続します）: {e}")

    def _now_iso(self) -> str:
        """現在時刻を ISO 8601 形式（タイムゾーン付き）で返す。"""
        return datetime.now(timezone.utc).astimezone().isoformat()

    def _extract_post_id(self, edit_url: str) -> int:
        """
        edit_url から WordPress の post_id を抽出する。

        [v1.8.0 暫定実装]
        既存の BaseOutput.save() インターフェースを維持するため、
        edit_url のクエリパラメータ（?post=XXXX）から正規表現で抽出する。
        将来的には WordPress API レスポンスの response_data["id"] から
        直接取得する構造へ改善する（OutputManager が SaveResult を返す設計）。

        Args:
            edit_url: WordPress 管理画面の編集URL
                      例: "https://example.com/wp-admin/post.php?post=123&action=edit"

        Returns:
            int: 抽出した post_id。取得できない場合は 0。
        """
        match = re.search(r'post=(\d+)', edit_url)
        return int(match.group(1)) if match else 0

    def log_article(
        self,
        article,
        edit_url: str = "",
        result: str = "success",
        error_message: str = "",
        wp_public_url: str = "",
        x_post_status=None,
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
            x_post_status: X投稿ステータス（SnsPostStatus Enum）。
                           None の場合は SnsPostStatus.PENDING を使用。
            x_post_url:    X投稿後のポストURL（v1.9.0 は常に ""）
        """
        from outputs.taxonomy_config import resolve_taxonomy
        from sns_config import SnsPostStatus
        category_ids, tag_ids = resolve_taxonomy(article.importance)
        post_id = self._extract_post_id(edit_url)
        date_str = datetime.now().strftime("%Y%m%d")
        status = x_post_status if x_post_status is not None else SnsPostStatus.PENDING

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
            wp_public_url=wp_public_url,
            x_post_text=article.x_post,
            x_post_status=status,
            x_post_url=x_post_url,
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
    LOG_ENABLED=false のときに使用するダミー実装。
    すべてのメソッドが何もしない（no-op）。
    main.py 側は LogManager か NullLogManager かを意識しなくてよい。
    """

    def log_article(self, article=None, edit_url="", result="success", error_message="",
                    wp_public_url="", x_post_status=None, x_post_url="") -> None:
        pass

    def log_execution(self, entry=None) -> None:
        pass

    def log_error(self, error_type="", error_message="", article_title="", source_url="") -> None:
        pass
