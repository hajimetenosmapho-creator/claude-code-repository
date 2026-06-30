"""
RewriteResult を Markdown + JSON に保存するモジュール（v1.16.0）

Single Responsibility:
    - RewriteResult を outputs/ai_rewrites/ に保存する
    - Markdown と JSON の2形式で保存する

公開 API は save() のみ:
    - 呼び出し側は保存先の詳細（形式・パス構造）を知らない
    - 将来的に保存先が DB / S3 / GitHub に変わっても呼び出し側への影響はゼロ
    - _save_json() / _save_markdown() は内部メソッドとして分離

禁止事項:
    - Claude API の呼び出し
    - RewriteResult の生成（RewriteService / RewriteParser の責務）
"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from .rewrite_result import RewriteResult


class RewriteRepository:
    """
    RewriteResult を outputs/ai_rewrites/ に Markdown + JSON で保存するクラス。

    ファイル名形式:
        YYYYMMDD_{article_id}_rewrite.json
        YYYYMMDD_{article_id}_rewrite.md

    success=False の RewriteResult も保存対象とし、失敗状態を記録に残す。
    """

    def __init__(self, output_dir: Path):
        self._output_dir = output_dir

    @classmethod
    def from_path(cls, output_dir: str | Path) -> "RewriteRepository":
        """パス文字列または Path から RewriteRepository を生成する。"""
        return cls(output_dir=Path(output_dir))

    def save(self, result: RewriteResult) -> tuple[Path | None, Path | None]:
        """
        RewriteResult を Markdown と JSON の両形式で保存する。

        外部から呼び出せる唯一のメソッド。
        保存先の詳細（ファイル形式・パス構造）は内部メソッドが担う。

        Args:
            result: 保存する RewriteResult（success=False でも保存する）

        Returns:
            tuple[Path | None, Path | None]: (json_path, markdown_path)
            保存失敗時は対応する要素が None になる。
        """
        try:
            self._output_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            print(f"  [REWRITE WARNING] 出力ディレクトリ作成失敗: {e}")
            return None, None

        json_path = self._save_json(result)
        md_path = self._save_markdown(result)
        return json_path, md_path

    def _save_json(self, result: RewriteResult) -> Path | None:
        """
        RewriteResult を JSON ファイルとして保存する。

        Returns:
            Path: 保存したファイルパス。失敗時は None。
        """
        try:
            date_str = date.today().strftime("%Y%m%d")
            filename = f"{date_str}_{result.article_id}_rewrite.json"
            path = self._output_dir / filename
            with path.open("w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
            print(f"  [REWRITE] JSON 保存: {path}")
            return path
        except OSError as e:
            print(f"  [REWRITE WARNING] JSON 保存失敗（処理継続）: {e}")
            return None

    def _save_markdown(self, result: RewriteResult) -> Path | None:
        """
        RewriteResult を Markdown ファイルとして保存する。

        success=False の場合はエラー情報を含む Markdown を保存する。

        Returns:
            Path: 保存したファイルパス。失敗時は None。
        """
        try:
            date_str = date.today().strftime("%Y%m%d")
            filename = f"{date_str}_{result.article_id}_rewrite.md"
            path = self._output_dir / filename
            content = _build_markdown(result)
            with path.open("w", encoding="utf-8") as f:
                f.write(content)
            print(f"  [REWRITE] Markdown 保存: {path}")
            return path
        except OSError as e:
            print(f"  [REWRITE WARNING] Markdown 保存失敗（処理継続）: {e}")
            return None


def _build_markdown(result: RewriteResult) -> str:
    """RewriteResult から Markdown 文字列を生成する。"""
    lines: list[str] = []

    lines.append(f"# リライト結果: {result.title}")
    lines.append("")
    lines.append(f"- **記事ID**: {result.article_id}")
    if result.permalink:
        lines.append(f"- **URL**: {result.permalink}")
    lines.append(f"- **プロンプトバージョン**: {result.prompt_version}")
    lines.append(f"- **生成日時**: {result.created_at.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- **成功**: {'はい' if result.success else 'いいえ'}")
    if result.error_message:
        lines.append(f"- **エラー**: {result.error_message}")
    lines.append("")

    if not result.success:
        lines.append("## エラー")
        lines.append("")
        lines.append(f"> {result.error_message or '不明なエラー'}")
        lines.append("")
        return "\n".join(lines)

    if result.improvement_summary:
        lines.append("## 改善サマリー")
        lines.append("")
        lines.append(result.improvement_summary)
        lines.append("")

    if result.changes:
        lines.append("## 主な変更点")
        lines.append("")
        for change in result.changes:
            lines.append(f"- {change}")
        lines.append("")

    if result.rewrite_draft:
        lines.append("## 改善版記事")
        lines.append("")
        lines.append(result.rewrite_draft)
        lines.append("")

    if result.original_content:
        lines.append("## 元記事")
        lines.append("")
        lines.append(result.original_content)
        lines.append("")

    return "\n".join(lines)
