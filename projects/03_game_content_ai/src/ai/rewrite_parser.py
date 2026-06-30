"""
Claude API のレスポンスを RewriteResult に変換するモジュール（v1.16.0）

Single Responsibility:
    - raw_response（str）を受け取り RewriteResult に変換する
    - JSON 前後の余計な文章も可能な範囲で抽出する
    - parse 失敗時は success=False の RewriteResult を返す（処理継続）

禁止事項:
    - Claude API の直接呼び出し（ClaudeClient の責務）
    - RewritePromptBuilder の呼び出し
    - ファイル I/O

例外処理方針:
    - JSON parse 失敗時は [REWRITE WARNING] を出力し、success=False の result を返す
    - システム全体を停止させない
"""
from __future__ import annotations

import json

from .rewrite_result import RewriteResult


class RewriteParser:
    """
    Claude API の raw_response を RewriteResult に変換するクラス。

    変換フロー:
        raw_response（str）
            → JSON ブロック抽出（```json ... ``` または生 JSON）
            → json.loads()
            → RewriteResult へのフィールドマッピング
            → RewriteResult（success=True or False）
    """

    def parse(
        self,
        raw_response: str,
        article_id: str = "",
        title: str = "",
        permalink: str | None = None,
        prompt_version: str = "v1",
        original_content: str = "",
    ) -> RewriteResult:
        """
        raw_response を RewriteResult に変換する。

        Args:
            raw_response:     Claude API のテキストレスポンス
            article_id:       記事識別子（slug）
            title:            記事 SEO タイトル
            permalink:        WordPress 公開 URL
            prompt_version:   使用したプロンプトバージョン
            original_content: 元記事本文（ArticleProvider が取得）

        Returns:
            RewriteResult: 変換結果。parse 失敗時は success=False の result。
        """
        if not raw_response.strip():
            return RewriteResult.empty(
                article_id=article_id,
                title=title,
                permalink=permalink,
                prompt_version=prompt_version,
                original_content=original_content,
                raw_response=raw_response,
                error_message="Claude API からの応答が空でした",
            )

        try:
            data = self._extract_json(raw_response)
            return self._map_to_result(
                data=data,
                article_id=article_id,
                title=title,
                permalink=permalink,
                prompt_version=prompt_version,
                original_content=original_content,
                raw_response=raw_response,
            )
        except Exception as e:
            print(f"  [REWRITE WARNING] JSON parse 失敗（処理継続）: {e}")
            return RewriteResult.empty(
                article_id=article_id,
                title=title,
                permalink=permalink,
                prompt_version=prompt_version,
                original_content=original_content,
                raw_response=raw_response,
                error_message=f"JSON parse 失敗: {e}",
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

    def _map_to_result(
        self,
        data: dict,
        article_id: str,
        title: str,
        permalink: str | None,
        prompt_version: str,
        original_content: str,
        raw_response: str,
    ) -> RewriteResult:
        """dict から RewriteResult にマッピングする。"""
        rewrite_draft = str(data.get("rewrite_draft", "")).strip()
        improvement_summary = str(data.get("improvement_summary", "")).strip()
        changes = _to_str_list(data.get("changes", []))

        return RewriteResult(
            article_id=article_id,
            title=title,
            permalink=permalink,
            prompt_version=prompt_version,
            original_content=original_content,
            rewrite_draft=rewrite_draft,
            improvement_summary=improvement_summary,
            changes=changes,
            raw_response=raw_response,
            success=True,
            error_message=None,
        )


def _to_str_list(value) -> list[str]:
    """list 値を list[str] に変換する。None / 非リスト値は空リストに変換。"""
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]
