"""
Claude API のレスポンスを ImprovementSuggestion に変換するモジュール（v1.14.0）

Single Responsibility:
    - raw_response（str）を受け取り ImprovementSuggestion に変換する
    - JSON 前後の余計な文章も可能な範囲で抽出する
    - parse 失敗時は empty ImprovementSuggestion を返す（処理継続）

禁止事項:
    - Claude API の直接呼び出し（ClaudeClient の責務）
    - PromptBuilder の呼び出し
    - ファイル I/O

例外処理方針:
    - JSON parse 失敗時は [AI WARNING] を出力し、raw_response のみ保持した empty suggestion を返す
    - システム全体を停止させない
"""
from __future__ import annotations

import json

from .improvement_suggestion import ImprovementSuggestion


class ImprovementSuggestionParser:
    """
    Claude API の raw_response を ImprovementSuggestion に変換するクラス。

    変換フロー:
        raw_response（str）
            → JSON ブロック抽出（```json ... ``` または生 JSON）
            → json.loads()
            → ImprovementSuggestion へのフィールドマッピング
            → ImprovementSuggestion
    """

    def parse(
        self,
        raw_response: str,
        article_id: str = "",
        title: str = "",
        permalink: str | None = None,
        prompt_version: str = "v1",
    ) -> ImprovementSuggestion:
        """
        raw_response を ImprovementSuggestion に変換する。

        Args:
            raw_response:   Claude API のテキストレスポンス
            article_id:     記事識別子（slug）
            title:          記事 SEO タイトル
            permalink:      WordPress 公開 URL
            prompt_version: 使用したプロンプトバージョン

        Returns:
            ImprovementSuggestion: 変換結果。parse 失敗時は empty suggestion。
        """
        if not raw_response.strip():
            return ImprovementSuggestion.empty(
                article_id=article_id,
                title=title,
                permalink=permalink,
                prompt_version=prompt_version,
                raw_response=raw_response,
            )

        try:
            data = self._extract_json(raw_response)
            return self._map_to_suggestion(
                data=data,
                article_id=article_id,
                title=title,
                permalink=permalink,
                prompt_version=prompt_version,
                raw_response=raw_response,
            )
        except Exception as e:
            print(f"  [AI WARNING] JSON parse 失敗（処理継続）: {e}")
            return ImprovementSuggestion.empty(
                article_id=article_id,
                title=title,
                permalink=permalink,
                prompt_version=prompt_version,
                raw_response=raw_response,
            )

    def _extract_json(self, raw_response: str) -> dict:
        """
        raw_response から JSON を抽出して dict に変換する。

        対応パターン:
            1. ```json ... ``` ブロック内の JSON
            2. ``` ... ``` ブロック内の JSON
            3. raw_response 全体を JSON として parse
            4. 最初の { から最後の } の範囲を抽出

        Raises:
            json.JSONDecodeError: JSON として解釈できない場合
            ValueError: JSON ブロックが見つからない場合
        """
        text = raw_response.strip()

        # パターン1: ```json ... ``` ブロック
        if "```json" in text:
            start = text.index("```json") + len("```json")
            end = text.index("```", start)
            return json.loads(text[start:end].strip())

        # パターン2: ``` ... ``` ブロック
        if "```" in text:
            start = text.index("```") + 3
            end = text.index("```", start)
            return json.loads(text[start:end].strip())

        # パターン3: 全体を JSON として parse
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass

        # パターン4: { ... } の範囲を抽出
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace != -1 and first_brace < last_brace:
            return json.loads(text[first_brace:last_brace + 1])

        raise ValueError("JSON ブロックが見つかりません")

    def _map_to_suggestion(
        self,
        data: dict,
        article_id: str,
        title: str,
        permalink: str | None,
        prompt_version: str,
        raw_response: str,
    ) -> ImprovementSuggestion:
        """dict から ImprovementSuggestion にマッピングする。"""
        priority = str(data.get("priority", "low")).lower()
        if priority not in ("high", "medium", "low"):
            priority = "low"

        return ImprovementSuggestion(
            article_id=article_id,
            title=title,
            permalink=permalink,
            prompt_version=prompt_version,
            summary=str(data.get("summary", "")),
            priority=priority,
            issues=_to_str_list(data.get("issues", [])),
            suggestions=_to_str_list(data.get("suggestions", [])),
            seo_title_suggestion=_to_str_or_none(data.get("seo_title_suggestion")),
            meta_description_suggestion=_to_str_or_none(data.get("meta_description_suggestion")),
            internal_link_suggestions=_to_str_list(data.get("internal_link_suggestions", [])),
            raw_response=raw_response,
        )


def _to_str_list(value) -> list[str]:
    """list 値を list[str] に変換する。None / 非リスト値は空リストに変換。"""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]


def _to_str_or_none(value) -> str | None:
    """値を str に変換する。None / 空文字は None として扱う。"""
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None
