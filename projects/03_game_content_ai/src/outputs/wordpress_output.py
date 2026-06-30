"""
WordPress REST API への記事下書き投稿を担うモジュール。
"""

import os
import requests
from .base import BaseOutput, ArticleData
from .save_result import SaveResult
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

    def save(self, article: ArticleData) -> SaveResult:
        """
        WordPress REST API に記事を投稿し、SaveResult を返す。

        v1.11.0: post_id を WordPress API レスポンスの "id" フィールドから直接取得する。
                 edit_url からの正規表現抽出（v1.8.0 の暫定実装）を廃止する。

        Args:
            article: 投稿対象の記事データ

        Returns:
            SaveResult: 投稿結果（post_id / edit_url / slug / permalink 等を格納）

        Raises:
            RuntimeError: 投稿に失敗した場合（ステータスコードが 200/201 以外）
        """
        endpoint = f"{self.site_url}/wp-json/wp/v2/posts"
        categories, tags = resolve_taxonomy(article.importance)
        payload = {
            "title": article.seo_title,
            "content": article.article_body,
            "status": article.publish_status.value,  # PublishStatus Enum から文字列に変換
            "excerpt": article.excerpt,
            "slug": article.slug,
        }
        if categories:
            payload["categories"] = categories
        if tags:
            payload["tags"] = tags
        if article.featured_media_id > 0:
            payload["featured_media"] = article.featured_media_id

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
        # v1.11.0: post_id を API レスポンスから直接取得（正規表現抽出を廃止）
        post_id      = response_data.get("id")
        actual_slug  = response_data.get("slug", "")
        actual_status = response_data.get("status", "")
        actual_title  = response_data.get("title", {}).get("rendered", "")
        permalink     = response_data.get("link", "")
        edit_url      = f"{self.site_url}/wp-admin/post.php?post={post_id}&action=edit"

        print(f"      投稿ID  : {post_id}")
        print(f"      slug    : {actual_slug}")
        print(f"      ステータス: {actual_status}")
        print(f"      編集URL : {edit_url}")

        return SaveResult(
            success=True,
            output_type="wordpress",
            post_id=post_id,
            title=actual_title,
            slug=actual_slug,
            status=actual_status,
            edit_url=edit_url,
            permalink=permalink,
            raw_response=response_data,
        )
