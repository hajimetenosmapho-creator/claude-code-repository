"""
AI 公開レビュー結果のデータモデル（v1.19.0）

Single Source of Truth:
    AiPublishReviewResult が AI 公開レビュー機能の唯一の出力形式。
    AiPublishReviewRepository / AiPublishReviewService はすべてこのクラスを扱う。

役割の分離:
    publish_status  → 投稿処理がどうだったか（"success" / "skipped" / "failed"）
    review_status   → 人が公開してよいか判断する欄（Foundation では全件 PENDING）
    is_publish_candidate → 公開候補かどうかの計算値（publish_success and not publish_skipped）

設計方針:
    - AiPublishResult を入力として from_publish_result() で生成する
    - WordPress への書き込みは一切行わない（読み取り・確認のみ）
    - review_status は Foundation では PENDING 固定。将来バージョンで人が更新する
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class PublishReviewStatus(Enum):
    """
    公開前レビューの状態（人の公開判断を表す）。

    v1.17.0 の ReviewStatus（リライトレビュー用）とは別クラス。
    用途: WordPress 下書きを公開してよいかの判断欄。
    """
    PENDING  = "pending"   # 未判断（Foundation では全件この状態）
    APPROVED = "approved"  # 公開承認済み
    ON_HOLD  = "on_hold"   # 保留中
    REJECTED = "rejected"  # 却下


@dataclass
class AiPublishReviewResult:
    """
    AiPublishResult に対する公開前レビュー結果。

    Attributes:
        article_id:              記事識別子（slug）
        title:                   記事タイトル
        original_permalink:      元記事の WordPress 公開 URL
        source_review_status:    採用時のリライトレビュー状態（例: "adopted"）

        wp_post_id:              WordPress 投稿 ID（下書き）
        wp_draft_slug:           下書きスラッグ
        wp_edit_url:             WordPress 管理画面の編集 URL
        wp_draft_permalink:      下書きプレビュー URL
        published_at:            投稿処理を実行した日時

        publish_status:          投稿処理結果（"success" / "skipped" / "failed"）
        publish_success:         投稿が成功したか
        publish_skipped:         スキップされたか
        publish_skip_reason:     スキップ理由
        publish_error:           失敗理由

        is_publish_candidate:    公開候補か（publish_success and not publish_skipped）
        review_status:           人の公開判断（PublishReviewStatus Enum）
        review_note:             レビューメモ（人が後で記入する欄、初期値: ""）
        reviewed_at:             このレビュー結果の生成日時
    """
    article_id: str
    title: str
    original_permalink: str | None
    source_review_status: str

    wp_post_id: int | None
    wp_draft_slug: str | None
    wp_edit_url: str | None
    wp_draft_permalink: str | None
    published_at: datetime

    publish_status: str
    publish_success: bool
    publish_skipped: bool
    publish_skip_reason: str | None
    publish_error: str | None

    is_publish_candidate: bool
    review_status: PublishReviewStatus
    review_note: str

    reviewed_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """JSON 保存用の辞書に変換する。"""
        return {
            "article_id": self.article_id,
            "title": self.title,
            "original_permalink": self.original_permalink,
            "source_review_status": self.source_review_status,
            "wp_post_id": self.wp_post_id,
            "wp_draft_slug": self.wp_draft_slug,
            "wp_edit_url": self.wp_edit_url,
            "wp_draft_permalink": self.wp_draft_permalink,
            "published_at": self.published_at.isoformat(),
            "publish_status": self.publish_status,
            "publish_success": self.publish_success,
            "publish_skipped": self.publish_skipped,
            "publish_skip_reason": self.publish_skip_reason,
            "publish_error": self.publish_error,
            "is_publish_candidate": self.is_publish_candidate,
            "review_status": self.review_status.value,
            "review_note": self.review_note,
            "reviewed_at": self.reviewed_at.isoformat(),
        }

    def to_json(self, indent: int = 2) -> str:
        """JSON 文字列に変換する。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_publish_result(
        cls,
        result: "AiPublishResult",
        review_status: PublishReviewStatus = PublishReviewStatus.PENDING,
        review_note: str = "",
    ) -> "AiPublishReviewResult":
        """
        AiPublishResult から AiPublishReviewResult を生成する。

        publish_status の判定:
            result.success == True              → "success"
            result.skipped == True              → "skipped"
            それ以外（success=False, skipped=False） → "failed"

        is_publish_candidate の判定:
            result.success and not result.skipped

        Args:
            result:        元になる AiPublishResult
            review_status: 公開判断の初期状態（デフォルト: PENDING）
            review_note:   レビューメモ（デフォルト: ""）
        """
        from .ai_publish_result import AiPublishResult  # 循環インポート回避

        if result.success:
            publish_status = "success"
        elif result.skipped:
            publish_status = "skipped"
        else:
            publish_status = "failed"

        is_publish_candidate = result.success and not result.skipped

        return cls(
            article_id=result.article_id,
            title=result.title,
            original_permalink=result.original_permalink,
            source_review_status=result.source_review_status,
            wp_post_id=result.wp_post_id,
            wp_draft_slug=result.wp_draft_slug,
            wp_edit_url=result.wp_edit_url,
            wp_draft_permalink=result.wp_draft_permalink,
            published_at=result.published_at,
            publish_status=publish_status,
            publish_success=result.success,
            publish_skipped=result.skipped,
            publish_skip_reason=result.skip_reason,
            publish_error=result.error_message,
            is_publish_candidate=is_publish_candidate,
            review_status=review_status,
            review_note=review_note,
        )
