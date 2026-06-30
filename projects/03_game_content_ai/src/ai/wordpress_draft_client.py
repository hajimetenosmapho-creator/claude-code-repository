"""
WordPress REST API への新規下書き投稿クライアント（v1.18.0）

設計方針:
    - post_draft() の status は "draft" にハードコードする（外部から publish に変更不可）
    - 既存記事の UPDATE（PATCH）は行わない（POST = 新規作成のみ）
    - 認証には Basic 認証（username + app_password）を使用する
    - urllib のみ使用（article_provider.py と統一）

Null Object Pattern:
    NullWordPressDraftClient は認証情報未設定・AI_PUBLISH_ENABLED=false 時のダミー実装。
    post_draft() は {"skipped": True, "reason": ...} を返し、
    AiPublishService がこれをスキップとして解釈する。
"""
from __future__ import annotations

import base64
import json
import urllib.error
import urllib.request


class WordPressDraftClient:
    """
    WordPress REST API に新規下書きを投稿するクライアント。

    禁止事項:
        - status を "draft" 以外に変更できる外部インタフェースの公開
        - 既存記事の UPDATE（既存 post_id への PATCH リクエスト）
    """

    def __init__(self, url: str, username: str, app_password: str):
        self._url = url.rstrip("/")
        self._auth_header = _build_basic_auth_header(username, app_password)

    def post_draft(
        self,
        title: str,
        content: str,
        slug: str,
        excerpt: str | None = None,
    ) -> dict:
        """
        WordPress に新規下書きを投稿する。

        status は "draft" に固定（外部から変更不可）。

        Args:
            title:   投稿タイトル
            content: 投稿本文（rewrite_draft）
            slug:    WordPress スラッグ（元記事とは別の新規スラッグ）
            excerpt: 抜粋（None の場合は payload に含めない）

        Returns:
            dict: {"post_id": int, "slug": str, "edit_url": str, "permalink": str}

        Raises:
            RuntimeError: WordPress API が失敗した場合
        """
        endpoint = f"{self._url}/wp-json/wp/v2/posts"
        payload: dict = {
            "title": title,
            "content": content,
            "slug": slug,
            "status": "draft",  # ハードコード・外部から変更不可
        }
        if excerpt is not None:
            payload["excerpt"] = excerpt

        encoded = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            endpoint,
            data=encoded,
            headers={
                "Authorization": self._auth_header,
                "Content-Type": "application/json",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                response_data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", errors="replace")[:200]
            raise RuntimeError(f"WordPress 投稿失敗 (HTTP {e.code}): {body}")
        except Exception as e:
            raise RuntimeError(f"WordPress 投稿失敗: {e}")

        post_id = response_data.get("id")
        actual_slug = response_data.get("slug", "")
        permalink = response_data.get("link", "")
        edit_url = f"{self._url}/wp-admin/post.php?post={post_id}&action=edit"

        print(f"  [PUBLISH] 投稿完了: post_id={post_id}, slug={actual_slug}")
        return {
            "post_id": post_id,
            "slug": actual_slug,
            "edit_url": edit_url,
            "permalink": permalink,
        }


class NullWordPressDraftClient:
    """
    WordPress 認証情報未設定・AI_PUBLISH_ENABLED=false 時のダミー実装。

    post_draft() は {"skipped": True, "reason": ...} を返す。
    AiPublishService はこれをスキップとして解釈し、
    success=False・skipped=True の AiPublishResult を生成する。
    """

    def __init__(self, reason: str = "WordPress credentials not configured"):
        self._reason = reason

    def post_draft(
        self,
        title: str,
        content: str,
        slug: str,
        excerpt: str | None = None,
    ) -> dict:
        print(f"  [PUBLISH] WordPress 投稿スキップ（{self._reason}）: {slug}")
        return {"skipped": True, "reason": self._reason}


def _build_basic_auth_header(username: str, app_password: str) -> str:
    """Basic 認証ヘッダー値を生成する。"""
    credentials = f"{username}:{app_password}"
    encoded = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    return f"Basic {encoded}"
