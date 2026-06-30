"""
Search Console API レスポンスを SearchConsoleMetrics に変換するモジュール（v1.12.0）

Single Responsibility:
    - page_url を受け取り SearchConsoleClient から生データを取得する
    - APIレスポンスを既存の SearchConsoleMetrics に変換する
    - 例外をWARNING扱いにしてシステム全体を停止させない

禁止事項:
    - Google API への直接通信（SearchConsoleClient の責務）
    - AnalyticsEntry の保存（AnalyticsManager の責務）
    - SearchConsoleMetrics の独自定義（analytics_entry.py を Single Source of Truth とする）
    - ファイル I/O

例外処理方針:
    - 429（レート制限）: WARNING のみ表示して SearchConsoleMetrics() ゼロ値を返す
    - その他 HttpError:  WARNING のみ表示してゼロ値を返す
    - 予期せぬ Exception: WARNING のみ表示してゼロ値を返す
    - システム全体を停止させない
"""
from __future__ import annotations

from .analytics_entry import SearchConsoleMetrics
from .search_console_client import SearchConsoleClient, NullSearchConsoleClient

try:
    from googleapiclient.errors import HttpError
except ImportError:
    class HttpError(Exception):  # type: ignore[misc]
        """google-api-python-client 未インストール時のフォールバック。"""
        resp = type("_Resp", (), {"status": 0})()


class SearchConsoleFetcher:
    """
    page_url → SearchConsoleMetrics の変換を担うクラス。

    SearchConsoleClient の fetch_raw() 結果を受け取り、
    既存の SearchConsoleMetrics（analytics_entry.py 定義）に変換して返す。
    """

    def __init__(self, client: "SearchConsoleClient | NullSearchConsoleClient"):
        self._client = client

    @classmethod
    def from_env(cls) -> "SearchConsoleFetcher":
        """環境変数からクライアントを構築して SearchConsoleFetcher を返す。"""
        client = SearchConsoleClient.from_env()
        return cls(client)

    def is_available(self) -> bool:
        """フェッチが可能な状態かを返す。"""
        return self._client.is_available()

    def fetch(self, page_url: str, period_days: int = 28) -> SearchConsoleMetrics:
        """
        指定 URL の Search Console パフォーマンスデータを取得して SearchConsoleMetrics を返す。

        クライアントが利用不可の場合・例外発生時はゼロ値を返してシステムを継続する。

        Args:
            page_url:    取得対象の記事 permalink（SaveResult.permalink を使用）
            period_days: 集計期間（日数）

        Returns:
            SearchConsoleMetrics: 取得結果。取得不可・失敗時はゼロ値（全フィールド 0）。
        """
        if not self._client.is_available():
            return SearchConsoleMetrics()

        try:
            raw = self._client.fetch_raw(page_url, period_days)
            return self._parse(raw)
        except HttpError as e:
            status = getattr(getattr(e, "resp", None), "status", 0)
            if status == 429:
                print(f"  [SC WARNING] レート制限（処理継続）: {e}")
            else:
                print(f"  [SC WARNING] SC API エラー（処理継続）: {e}")
            return SearchConsoleMetrics()
        except Exception as e:
            print(f"  [SC WARNING] 予期せぬエラー（処理継続）: {e}")
            return SearchConsoleMetrics()

    def _parse(self, raw: dict) -> SearchConsoleMetrics:
        """
        Search Console API レスポンスから SearchConsoleMetrics を生成する。

        API レスポンス形式:
            {
                "rows": [
                    {
                        "keys": ["https://..."],
                        "impressions": 1500,
                        "clicks": 75,
                        "ctr": 0.05,
                        "position": 3.2
                    }
                ]
            }

        rows が空または存在しない場合（データなし）はゼロ値を返す。
        複数行の場合は impressions / clicks を合計、ctr / position を平均する。
        """
        rows = raw.get("rows", [])
        if not rows:
            return SearchConsoleMetrics()

        total_impressions = sum(int(r.get("impressions", 0)) for r in rows)
        total_clicks = sum(int(r.get("clicks", 0)) for r in rows)
        ctr_values = [float(r.get("ctr", 0.0)) for r in rows]
        position_values = [float(r.get("position", 0.0)) for r in rows]
        count = len(rows)

        return SearchConsoleMetrics(
            impressions=total_impressions,
            clicks=total_clicks,
            ctr=sum(ctr_values) / count if count > 0 else 0.0,
            avg_position=sum(position_values) / count if count > 0 else 0.0,
        )
