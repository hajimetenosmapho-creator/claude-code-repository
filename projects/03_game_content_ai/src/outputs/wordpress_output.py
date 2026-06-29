"""
WordPress REST API への記事下書き投稿を担うモジュール。
"""

import os
import requests
from .base import BaseOutput, ArticleData
from .taxonomy_config import resolve_taxonomy


class WordPressOutput(BaseOutput):
    """
    WordPress REST API に記事を下書きとして投稿する。
    WP_SITE_URL / WP_USERNAME / WP_APP_PASSWORD が未設定の場合は
    is_available() が False を返し、OutputManager によりスキップされる。
    """

    def __init__(self, site_url: str, username: str, app_password: str):
        self.site_url = site_url.rstrip("/")
        self.username = username
        self.app_password = app_password

    @classmethod
    def from_env(cls) -> "WordPressOutput":
        """環境変数から認証情報を読み込んでインスタンスを生成する。"""
        return cls(
            site_url=os.getenv("WP_SITE_URL", ""),
            username=os.getenv("WP_USERNAME", ""),
            app_password=os.getenv("WP_APP_PASSWORD", ""),
        )

    def is_available(self) -> bool:
        """WP_SITE_URL / WP_USERNAME / WP_APP_PASSWORD がすべて設定されている場合のみ True。"""
        return bool(self.site_url and self.username and self.app_password)

    def save(self, article: ArticleData) -> str:
        """
        WordPress REST API に記事を下書きとして投稿する。

        Args:
            article: 投稿対象の記事データ

        Returns:
            str: WordPress 管理画面の編集URL

        Raises:
            RuntimeError: 投稿に失敗した場合（ステータスコードが 200/201 以外）
        """
        endpoint = f"{self.site_url}/wp-json/wp/v2/posts"
        categories, tags = resolve_taxonomy(article.importance)
        payload = {
            "title": article.seo_title,
            "content": article.article_body,
            "status": "draft",
            "excerpt": article.excerpt,
            "slug": article.slug,
        }
        if categories:
            payload["categories"] = categories
        if tags:
            payload["tags"] = tags

        response = requests.post(
            endpoint,
            json=payload,
            auth=(self.username, self.app_password),
            timeout=30,
        )

        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"WordPress投稿失敗 (HTTP {response.status_code}): {response.text[:200]}"
            )

        response_data = response.json()
        post_id    = response_data.get("id")
        actual_slug = response_data.get("slug", "")
        edit_url   = f"{self.site_url}/wp-admin/post.php?post={post_id}&action=edit"

        print(f"      投稿ID  : {post_id}")
        print(f"      slug    : {actual_slug}")
        print(f"      編集URL : {edit_url}")

        return edit_url
