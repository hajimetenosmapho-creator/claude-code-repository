"""
AI リライト結果のデータモデル（v1.16.0）

Single Source of Truth:
    RewriteResult が AI リライト機能の唯一の出力形式。
    RewriteParser / RewriteService / RewriteRepository はすべてこのクラスを扱う。

設計方針:
    - success=True  → rewrite_draft に改善版記事が格納される
    - success=False → error_message に失敗理由が格納される（rewrite_draft は空）
    - original_content は ArticleProvider が取得した元記事本文（空文字も許容）
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class RewriteResult:
    """
    Claude API が生成した AI リライト結果。

    Attributes:
        article_id:          記事識別子（slug）
        title:               記事 SEO タイトル
        permalink:           WordPress 公開 URL
        prompt_version:      使用したプロンプトバージョン（例: "v1"）
        original_content:    取得した元記事本文（空文字 = 取得不可）
        rewrite_draft:       Claude が生成した改善版記事（Markdown）
        improvement_summary: 変更点の要約
        changes:             主な変更一覧
        raw_response:        Claude の生レスポンス（デバッグ用）
        created_at:          生成日時
        success:             生成が成功したか
        error_message:       失敗時の理由（success=True の場合は None）
    """
    article_id: str
    title: str
    permalink: str | None
    prompt_version: str
    original_content: str
    rewrite_draft: str
    improvement_summary: str
    changes: list[str]
    raw_response: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    success: bool = True
    error_message: str | None = None

    def to_dict(self) -> dict:
        """JSON 保存用の辞書に変換する。"""
        return {
            "article_id": self.article_id,
            "title": self.title,
            "permalink": self.permalink,
            "prompt_version": self.prompt_version,
            "original_content": self.original_content,
            "rewrite_draft": self.rewrite_draft,
            "improvement_summary": self.improvement_summary,
            "changes": self.changes,
            "raw_response": self.raw_response,
            "created_at": self.created_at.isoformat(),
            "success": self.success,
            "error_message": self.error_message,
        }

    def to_json(self, indent: int = 2) -> str:
        """JSON 文字列に変換する。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def empty(
        cls,
        article_id: str = "",
        title: str = "",
        permalink: str | None = None,
        prompt_version: str = "v1",
        original_content: str = "",
        raw_response: str = "",
        error_message: str | None = None,
    ) -> "RewriteResult":
        """
        失敗時・無効時に返す RewriteResult。
        success=False、error_message に失敗理由を格納する。
        """
        return cls(
            article_id=article_id,
            title=title,
            permalink=permalink,
            prompt_version=prompt_version,
            original_content=original_content,
            rewrite_draft="",
            improvement_summary="",
            changes=[],
            raw_response=raw_response,
            success=False,
            error_message=error_message,
        )
