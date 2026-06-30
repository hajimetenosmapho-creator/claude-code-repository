"""
AI 改善提案の出力モデル（v1.14.0）

Single Source of Truth:
    ImprovementSuggestion がAI改善提案の唯一の出力形式である。
    ClaudeClient / ImprovementSuggestionParser / AiImprovementService は
    すべてこのクラスを返す。

設計方針:
    - priority は "high" / "medium" / "low" を想定する
    - raw_response は JSON parse 失敗時のデバッグ用に保持する
    - Release 2.0 向けフィールド（title_suggestions 等）は本バージョンでは追加しない
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class ImprovementSuggestion:
    """
    Claude API が生成した AI 改善提案。

    Attributes:
        article_id:                 記事識別子（slug を使用）
        title:                      記事 SEO タイトル
        permalink:                  WordPress 公開 URL
        prompt_version:             使用したプロンプトバージョン（例: "v1"）
        summary:                    改善提案の要約
        priority:                   優先度 ("high" / "medium" / "low")
        issues:                     検出された問題点のリスト
        suggestions:                改善提案のリスト
        seo_title_suggestion:       SEO タイトル改善案（任意）
        meta_description_suggestion: メタディスクリプション改善案（任意）
        internal_link_suggestions:  内部リンク提案（Release 2.0 基礎）
        raw_response:               Claude の生レスポンス（デバッグ用）
        created_at:                 生成日時
    """
    article_id: str
    title: str
    permalink: str | None
    prompt_version: str
    summary: str
    priority: str
    issues: list[str]
    suggestions: list[str]
    seo_title_suggestion: str | None = None
    meta_description_suggestion: str | None = None
    internal_link_suggestions: list[str] = field(default_factory=list)
    raw_response: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        """JSON 保存用の辞書に変換する。"""
        return {
            "article_id": self.article_id,
            "title": self.title,
            "permalink": self.permalink,
            "prompt_version": self.prompt_version,
            "summary": self.summary,
            "priority": self.priority,
            "issues": self.issues,
            "suggestions": self.suggestions,
            "seo_title_suggestion": self.seo_title_suggestion,
            "meta_description_suggestion": self.meta_description_suggestion,
            "internal_link_suggestions": self.internal_link_suggestions,
            "raw_response": self.raw_response,
            "created_at": self.created_at.isoformat(),
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
        raw_response: str = "",
    ) -> "ImprovementSuggestion":
        """
        失敗時・無効時に返す空の ImprovementSuggestion。
        raw_response のみ保持し、他フィールドはデフォルト値。
        """
        return cls(
            article_id=article_id,
            title=title,
            permalink=permalink,
            prompt_version=prompt_version,
            summary="",
            priority="low",
            issues=[],
            suggestions=[],
            raw_response=raw_response,
        )
