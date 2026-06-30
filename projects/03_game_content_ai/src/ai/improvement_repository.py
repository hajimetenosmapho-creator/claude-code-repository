"""
AI 改善提案 JSON ファイルの読み込みを担うモジュール（v1.15.0）

Single Responsibility:
    - outputs/ai_improvements/ 配下の JSON ファイルを読み込む
    - ImprovementSuggestion として復元する
    - article_id / priority / prompt_version で絞り込む
    - 不正ファイルがあっても全体処理を止めない

禁止事項:
    - Claude API の呼び出し
    - ImprovementSuggestion の生成（読み込み・復元のみ）
    - レポート生成（ImprovementReportBuilder の責務）
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .improvement_suggestion import ImprovementSuggestion


class ImprovementRepository:
    """
    outputs/ai_improvements/ 配下の改善提案 JSON を読み込むリポジトリ。

    ファイル名形式: YYYYMMDD_{article_id}_improvement.json
    不正な JSON ファイルは [REVIEW WARNING] を出力してスキップする。
    """

    def __init__(self, output_dir: Path):
        self._output_dir = output_dir

    @classmethod
    def from_path(cls, output_dir: str | Path) -> "ImprovementRepository":
        """パス文字列またはPath から ImprovementRepository を生成する。"""
        return cls(output_dir=Path(output_dir))

    def load_all(self) -> list[ImprovementSuggestion]:
        """
        output_dir 配下の全 JSON ファイルを読み込む。

        ファイルが存在しない場合は空リストを返す。
        不正ファイルは [REVIEW WARNING] を出力してスキップする。

        Returns:
            list[ImprovementSuggestion]: 読み込んだ改善提案のリスト（created_at 降順）
        """
        if not self._output_dir.exists():
            return []

        suggestions: list[ImprovementSuggestion] = []
        for path in sorted(self._output_dir.glob("*_improvement.json")):
            suggestion = self._load_file(path)
            if suggestion is not None:
                suggestions.append(suggestion)

        suggestions.sort(key=lambda s: s.created_at, reverse=True)
        return suggestions

    def load_by_article_id(self, article_id: str) -> list[ImprovementSuggestion]:
        """
        指定した article_id の改善提案を返す。

        Args:
            article_id: 記事識別子（slug）

        Returns:
            list[ImprovementSuggestion]: 一致する改善提案のリスト
        """
        return [s for s in self.load_all() if s.article_id == article_id]

    def filter_by_priority(
        self,
        suggestions: list[ImprovementSuggestion],
        priority: str,
    ) -> list[ImprovementSuggestion]:
        """
        priority で絞り込む。

        Args:
            suggestions: 絞り込み対象のリスト
            priority:    "high" / "medium" / "low"

        Returns:
            list[ImprovementSuggestion]: 一致する改善提案のリスト
        """
        return [s for s in suggestions if s.priority == priority]

    def filter_by_prompt_version(
        self,
        suggestions: list[ImprovementSuggestion],
        prompt_version: str,
    ) -> list[ImprovementSuggestion]:
        """
        prompt_version で絞り込む。

        Args:
            suggestions:    絞り込み対象のリスト
            prompt_version: "v1" など

        Returns:
            list[ImprovementSuggestion]: 一致する改善提案のリスト
        """
        return [s for s in suggestions if s.prompt_version == prompt_version]

    def _load_file(self, path: Path) -> ImprovementSuggestion | None:
        """
        JSON ファイルを読み込み ImprovementSuggestion として復元する。

        Args:
            path: JSON ファイルのパス

        Returns:
            ImprovementSuggestion: 復元した改善提案。読み込み失敗時は None。
        """
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return _dict_to_suggestion(data)
        except json.JSONDecodeError as e:
            print(f"  [REVIEW WARNING] JSON parse 失敗（スキップ）: {path.name} - {e}")
            return None
        except (KeyError, TypeError, ValueError) as e:
            print(f"  [REVIEW WARNING] データ形式エラー（スキップ）: {path.name} - {e}")
            return None
        except OSError as e:
            print(f"  [REVIEW WARNING] ファイル読み込み失敗（スキップ）: {path.name} - {e}")
            return None


def _dict_to_suggestion(data: dict) -> ImprovementSuggestion:
    """
    dict から ImprovementSuggestion を復元する。

    created_at は ISO 8601 文字列から datetime に変換する。
    """
    created_at_raw = data.get("created_at", "")
    try:
        created_at = datetime.fromisoformat(created_at_raw) if created_at_raw else datetime.now()
    except ValueError:
        created_at = datetime.now()

    return ImprovementSuggestion(
        article_id=str(data.get("article_id", "")),
        title=str(data.get("title", "")),
        permalink=data.get("permalink"),
        prompt_version=str(data.get("prompt_version", "v1")),
        summary=str(data.get("summary", "")),
        priority=str(data.get("priority", "low")),
        issues=_to_str_list(data.get("issues", [])),
        suggestions=_to_str_list(data.get("suggestions", [])),
        seo_title_suggestion=_to_str_or_none(data.get("seo_title_suggestion")),
        meta_description_suggestion=_to_str_or_none(data.get("meta_description_suggestion")),
        internal_link_suggestions=_to_str_list(data.get("internal_link_suggestions", [])),
        raw_response=str(data.get("raw_response", "")),
        created_at=created_at,
    )


def _to_str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _to_str_or_none(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None
