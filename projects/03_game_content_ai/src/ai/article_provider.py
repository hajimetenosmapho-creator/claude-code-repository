"""
記事本文を取得する抽象クラスと実装クラス群（v1.16.0）

設計方針（Dependency Injection / Open-Closed Principle）:
    - ArticleProvider は ABC（抽象基底クラス）として定義する
    - RewriteService は ArticleProvider 型のみに依存し、具体的な取得元を知らない
    - 将来的に MarkdownArticleProvider / CachedArticleProvider を追加しても
      RewriteService は変更不要

実装クラス:
    - WordPressArticleProvider: WordPress REST API から取得
    - NullArticleProvider:      認証情報未設定時のダミー実装

禁止事項:
    - Claude API の呼び出し
    - ファイル I/O（記事本文のキャッシュなど）
    - 取得失敗時の例外を外部に伝播させること（空文字列を返す）
"""
from __future__ import annotations

import base64
import urllib.request
import urllib.parse
import json
from abc import ABC, abstractmethod


class ArticleProvider(ABC):
    """
    記事本文を取得する抽象クラス。

    RewriteService はこの型にのみ依存する。
    具体的な取得元（WordPress / Markdown / Cache 等）は実装クラスが担う。
    """

    @abstractmethod
    def fetch(self, article_id: str, permalink: str | None = None) -> str:
        """
        記事本文を取得して返す。

        Args:
            article_id: 記事識別子（slug）
            permalink:  記事 URL（ヒント。利用するかは実装次第）

        Returns:
            str: 記事本文。取得失敗時は空文字列を返す（例外を外に出さない）。
        """
        ...


class WordPressArticleProvider(ArticleProvider):
    """
    WordPress REST API で記事本文を取得する実装。

    エンドポイント: GET {wordpress_url}/wp-json/wp/v2/posts?slug={article_id}
    認証:          Basic 認証（username + app_password）

    取得失敗時（認証エラー / ネットワークエラー / 記事なし）は
    [REWRITE WARNING] を出力して空文字列を返す。
    """

    def __init__(self, url: str, username: str, app_password: str):
        self._url = url.rstrip("/")
        self._auth_header = _build_basic_auth_header(username, app_password)

    def fetch(self, article_id: str, permalink: str | None = None) -> str:
        """
        WordPress REST API から記事本文（content.rendered）を取得する。

        Args:
            article_id: slug（例: "ps6-announced-20260630"）
            permalink:  未使用（将来の拡張に備えて受け取る）

        Returns:
            str: 記事本文の HTML。取得失敗時は空文字列。
        """
        try:
            slug = urllib.parse.quote(article_id, safe="")
            api_url = f"{self._url}/wp-json/wp/v2/posts?slug={slug}&_fields=content,title"
            req = urllib.request.Request(
                api_url,
                headers={"Authorization": self._auth_header},
            )
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))

            if not data:
                print(f"  [REWRITE WARNING] 記事が見つかりません（slug={article_id}）")
                return ""

            content = data[0].get("content", {})
            return content.get("rendered", "") if isinstance(content, dict) else ""

        except Exception as e:
            print(f"  [REWRITE WARNING] WordPress API エラー（処理継続）: {e}")
            return ""


class NullArticleProvider(ArticleProvider):
    """
    WordPress 認証情報未設定時のダミー実装（Null Object Pattern）。

    fetch() は常に空文字列を返す。
    RewriteService は article_content="" の状態でも処理を継続できる。
    """

    def fetch(self, article_id: str, permalink: str | None = None) -> str:
        print(f"  [REWRITE] 元記事取得スキップ（WordPress 認証情報なし）: {article_id}")
        return ""


def _build_basic_auth_header(username: str, app_password: str) -> str:
    """Basic 認証ヘッダー値を生成する。"""
    credentials = f"{username}:{app_password}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    return f"Basic {encoded}"
