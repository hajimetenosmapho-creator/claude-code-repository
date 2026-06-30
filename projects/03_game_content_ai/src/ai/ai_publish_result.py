"""
AI 公開結果のデータモデル（v1.18.0）

Single Source of Truth:
    AiPublishResult が AI 公開機能の唯一の出力形式。
    AiPublishRepository / AiPublishService はすべてこのクラスを扱う。

設計方針:
    - success=True                     → WordPress への下書き投稿が成功した
    - success=False / skipped=True     → NullWordPressDraftClient によりスキップされた
    - success=False / error_message あり → 投稿中にエラーが発生した
    - source_review_status / source_rewrite_created_at で「どの情報を基に投稿したか」を記録する
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class AiPublishResult:
    """
    WordPress 下書き投稿の結果。

    Attributes:
        article_id:                   元記事の識別子（slug）
        title:                        記事タイトル
        original_permalink:           元記事の WordPress 公開 URL
        source_review_status:         採用時のレビュー状態（例: "adopted"）
        source_rewrite_created_at:    元になった RewriteResult の生成日時

        wp_post_id:                   WordPress の新規投稿 ID
        wp_draft_slug:                新規下書きに割り当てられたスラッグ
        wp_edit_url:                  WordPress 管理画面の編集 URL
        wp_draft_permalink:           下書きのプレビュー URL

        published_at:                 この投稿処理を実行した日時
        success:                      WordPress への投稿が成功したか
        skipped:                      NullWordPressDraftClient によりスキップされたか
        skip_reason:                  スキップ理由（skipped=True の場合に設定）
        error_message:                失敗理由（success=False かつ skipped=False の場合に設定）
    """
    article_id: str
    title: str
    original_permalink: str | None
    source_review_status: str
    source_rewrite_created_at: datetime | None

    wp_post_id: int | None = None
    wp_draft_slug: str | None = None
    wp_edit_url: str | None = None
    wp_draft_permalink: str | None = None

    published_at: datetime = field(default_factory=datetime.now)
    success: bool = True
    skipped: bool = False
    skip_reason: str | None = None
    error_message: str | None = None

    def to_dict(self) -> dict:
        """JSON 保存用の辞書に変換する。"""
        return {
            "article_id": self.article_id,
            "title": self.title,
            "original_permalink": self.original_permalink,
            "source_review_status": self.source_review_status,
            "source_rewrite_created_at": (
                self.source_rewrite_created_at.isoformat()
                if self.source_rewrite_created_at is not None
                else None
            ),
            "wp_post_id": self.wp_post_id,
            "wp_draft_slug": self.wp_draft_slug,
            "wp_edit_url": self.wp_edit_url,
            "wp_draft_permalink": self.wp_draft_permalink,
            "published_at": self.published_at.isoformat(),
            "success": self.success,
            "skipped": self.skipped,
            "skip_reason": self.skip_reason,
            "error_message": self.error_message,
        }

    def to_json(self, indent: int = 2) -> str:
        """JSON 文字列に変換する。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)
