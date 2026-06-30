"""
AI リライトレビュー結果のデータモデル（v1.17.0）

Single Source of Truth:
    RewriteReviewResult が AI リライトレビュー機能の唯一の出力形式。
    RewriteReviewRepository / RewriteReviewService はすべてこのクラスを扱う。

設計方針:
    - ReviewStatus は Enum で管理する（JSON保存時のみ .value を使用）
    - diff_summary の生成は RewriteReviewService の責務（このクラスはデータ保持のみ）
    - from_rewrite_result() は status / diff_summary を外部から受け取る
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class ReviewStatus(Enum):
    """リライトレビューの状態。"""
    PENDING  = "pending"
    ADOPTED  = "adopted"
    ON_HOLD  = "on_hold"
    REJECTED = "rejected"


@dataclass
class RewriteReviewResult:
    """
    RewriteResult に対するレビュー結果。

    Attributes:
        article_id:           記事識別子（slug）
        title:                記事 SEO タイトル
        permalink:            WordPress 公開 URL
        review_status:        レビュー状態（ReviewStatus Enum）
        review_note:          レビューメモ（空文字許容）
        original_char_count:  元記事の文字数
        rewrite_char_count:   リライト版の文字数
        char_diff:            文字数の増減（rewrite - original）
        original_line_count:  元記事の行数
        rewrite_line_count:   リライト版の行数
        line_diff:            行数の増減（rewrite - original）
        change_ratio:         文字数変化率（original が 0 の場合は 0.0）
        diff_summary:         簡易差分サマリー（Service が生成して注入する）
        changes_count:        変更点の件数
        improvement_summary:  改善サマリー（RewriteResult から）
        changes:              変更点リスト（RewriteResult から）
        created_at:           元 RewriteResult の生成日時
        reviewed_at:          このレビュー結果の生成日時
        success:              元 RewriteResult が success=True か
    """
    article_id: str
    title: str
    permalink: str | None
    review_status: ReviewStatus
    review_note: str

    # 文字数差分
    original_char_count: int
    rewrite_char_count: int
    char_diff: int

    # 行数差分
    original_line_count: int
    rewrite_line_count: int
    line_diff: int

    # 変化率
    change_ratio: float

    # 差分サマリー（Service が生成して注入する）
    diff_summary: list[str]

    # 変更情報
    changes_count: int
    improvement_summary: str
    changes: list[str]

    # 日時
    created_at: datetime
    reviewed_at: datetime = field(default_factory=datetime.now)

    # フラグ
    success: bool = True

    def to_dict(self) -> dict:
        """JSON 保存用の辞書に変換する。review_status は .value で文字列化する。"""
        return {
            "article_id": self.article_id,
            "title": self.title,
            "permalink": self.permalink,
            "review_status": self.review_status.value,
            "review_note": self.review_note,
            "original_char_count": self.original_char_count,
            "rewrite_char_count": self.rewrite_char_count,
            "char_diff": self.char_diff,
            "original_line_count": self.original_line_count,
            "rewrite_line_count": self.rewrite_line_count,
            "line_diff": self.line_diff,
            "change_ratio": self.change_ratio,
            "diff_summary": self.diff_summary,
            "changes_count": self.changes_count,
            "improvement_summary": self.improvement_summary,
            "changes": self.changes,
            "created_at": self.created_at.isoformat(),
            "reviewed_at": self.reviewed_at.isoformat(),
            "success": self.success,
        }

    def to_json(self, indent: int = 2) -> str:
        """JSON 文字列に変換する。"""
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=indent)

    @classmethod
    def from_rewrite_result(
        cls,
        result: "RewriteResult",
        status: ReviewStatus = ReviewStatus.PENDING,
        note: str = "",
        diff_summary: list[str] | None = None,
    ) -> "RewriteReviewResult":
        """
        RewriteResult からレビュー結果を生成する。

        diff_summary は Service 側で生成して渡す（このクラスは生成しない）。
        success=False の RewriteResult は文字数・行数ともに 0 として扱う。

        Args:
            result:       元になる RewriteResult
            status:       初期レビュー状態（デフォルト: PENDING）
            note:         レビューメモ（デフォルト: ""）
            diff_summary: 差分サマリー（Service が生成して渡す）
        """
        original = result.original_content
        rewrite  = result.rewrite_draft

        original_char_count = len(original)
        rewrite_char_count  = len(rewrite)
        char_diff           = rewrite_char_count - original_char_count

        original_line_count = len(original.splitlines()) if original else 0
        rewrite_line_count  = len(rewrite.splitlines())  if rewrite  else 0
        line_diff           = rewrite_line_count - original_line_count

        change_ratio = char_diff / original_char_count if original_char_count > 0 else 0.0

        return cls(
            article_id=result.article_id,
            title=result.title,
            permalink=result.permalink,
            review_status=status,
            review_note=note,
            original_char_count=original_char_count,
            rewrite_char_count=rewrite_char_count,
            char_diff=char_diff,
            original_line_count=original_line_count,
            rewrite_line_count=rewrite_line_count,
            line_diff=line_diff,
            change_ratio=change_ratio,
            diff_summary=diff_summary if diff_summary is not None else [],
            changes_count=len(result.changes),
            improvement_summary=result.improvement_summary,
            changes=list(result.changes),
            created_at=result.created_at,
            success=result.success,
        )
