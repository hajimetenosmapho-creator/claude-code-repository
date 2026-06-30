"""
RewriteResult の読み込みと RewriteReviewResult の読み書きを担うモジュール（v1.17.0）

Single Responsibility:
    - outputs/ai_rewrites/ 配下の RewriteResult JSON を読み込む
    - outputs/ai_rewrite_reviews/ 配下に RewriteReviewResult JSON を保存・読み込む

将来の分離方針:
    load_rewrite_results() / load_rewrite_by_article_id() / filter_by_success()
        → RewriteResultRepository へ移行予定
    load_reviews() / load_review_by_article_id() / save_review()
        → RewriteReviewRepository に残る

禁止事項:
    - Claude API の呼び出し
    - RewriteReviewResult の生成（Service の責務）
    - diff_summary の生成（Service の責務）
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .rewrite_result import RewriteResult
from .rewrite_review_result import ReviewStatus, RewriteReviewResult


class RewriteReviewRepository:
    """
    RewriteResult の読み込みと RewriteReviewResult の読み書きを担うリポジトリ。

    ディレクトリ:
        _rewrite_dir: outputs/ai_rewrites/        （RewriteResult JSON 読み取りのみ）
        _review_dir:  outputs/ai_rewrite_reviews/  （RewriteReviewResult JSON 読み書き）

    メソッドの分類:
        load_rewrite_results()  / load_rewrite_by_article_id() / filter_by_success()
            → 将来 RewriteResultRepository へ移行予定
        load_reviews() / load_review_by_article_id() / save_review()
            → RewriteReviewRepository に残る
    """

    def __init__(self, rewrite_dir: Path, review_dir: Path):
        self._rewrite_dir = rewrite_dir
        self._review_dir  = review_dir

    @classmethod
    def from_paths(
        cls,
        rewrite_dir: str | Path = "outputs/ai_rewrites",
        review_dir:  str | Path = "outputs/ai_rewrite_reviews",
        base_dir: Path | None = None,
    ) -> "RewriteReviewRepository":
        """
        パスから RewriteReviewRepository を構築する。

        Args:
            rewrite_dir: リライト結果 JSON の格納ディレクトリ
            review_dir:  レビュー結果 JSON の保存先ディレクトリ
            base_dir:    相対パスの基準ディレクトリ（None の場合はそのまま使用）
        """
        if base_dir is not None:
            rw_dir = base_dir / rewrite_dir
            rv_dir = base_dir / review_dir
        else:
            rw_dir = Path(rewrite_dir)
            rv_dir = Path(review_dir)
        return cls(rewrite_dir=rw_dir, review_dir=rv_dir)

    # ── RewriteResult の読み込み（将来 RewriteResultRepository へ移行） ──

    def load_rewrite_results(self) -> list[RewriteResult]:
        """
        rewrite_dir 配下の全 *_rewrite.json を読み込む。

        ファイルが存在しない場合は空リストを返す。
        不正ファイルは [REVIEW WARNING] を出力してスキップする。

        Returns:
            list[RewriteResult]: 読み込んだリライト結果のリスト（created_at 降順）
        """
        if not self._rewrite_dir.exists():
            return []

        results: list[RewriteResult] = []
        for path in sorted(self._rewrite_dir.glob("*_rewrite.json")):
            result = self._load_rewrite_file(path)
            if result is not None:
                results.append(result)

        results.sort(key=lambda r: r.created_at, reverse=True)
        return results

    def load_rewrite_by_article_id(self, article_id: str) -> list[RewriteResult]:
        """
        指定した article_id の RewriteResult を返す。

        Args:
            article_id: 記事識別子（slug）

        Returns:
            list[RewriteResult]: 一致するリライト結果のリスト
        """
        return [r for r in self.load_rewrite_results() if r.article_id == article_id]

    def filter_by_success(self, results: list[RewriteResult]) -> list[RewriteResult]:
        """
        success=True の RewriteResult のみ返す。

        Args:
            results: 絞り込み対象のリスト

        Returns:
            list[RewriteResult]: 成功したリライト結果のみのリスト
        """
        return [r for r in results if r.success]

    # ── RewriteReviewResult の読み書き ──

    def save_review(self, review: RewriteReviewResult) -> Path | None:
        """
        RewriteReviewResult を review_dir に JSON として保存する。

        ファイル名形式: YYYYMMDD_{article_id}_review.json

        Args:
            review: 保存する RewriteReviewResult

        Returns:
            Path: 保存したファイルパス。失敗時は None。
        """
        try:
            self._review_dir.mkdir(parents=True, exist_ok=True)
            date_str = review.reviewed_at.strftime("%Y%m%d")
            filename = f"{date_str}_{review.article_id}_review.json"
            path = self._review_dir / filename
            with path.open("w", encoding="utf-8") as f:
                json.dump(review.to_dict(), f, ensure_ascii=False, indent=2)
            print(f"  [REVIEW] レビューJSON保存: {path}")
            return path
        except OSError as e:
            print(f"  [REVIEW WARNING] レビューJSON保存失敗（処理継続）: {e}")
            return None

    def load_reviews(self) -> list[RewriteReviewResult]:
        """
        review_dir 配下の全 *_review.json を読み込む。

        ファイルが存在しない場合は空リストを返す。
        不正ファイルは [REVIEW WARNING] を出力してスキップする。

        Returns:
            list[RewriteReviewResult]: 読み込んだレビュー結果のリスト（reviewed_at 降順）
        """
        if not self._review_dir.exists():
            return []

        reviews: list[RewriteReviewResult] = []
        for path in sorted(self._review_dir.glob("*_review.json")):
            review = self._load_review_file(path)
            if review is not None:
                reviews.append(review)

        reviews.sort(key=lambda r: r.reviewed_at, reverse=True)
        return reviews

    def load_review_by_article_id(self, article_id: str) -> list[RewriteReviewResult]:
        """
        指定した article_id の RewriteReviewResult を返す。

        Args:
            article_id: 記事識別子（slug）

        Returns:
            list[RewriteReviewResult]: 一致するレビュー結果のリスト
        """
        return [r for r in self.load_reviews() if r.article_id == article_id]

    # ── 内部メソッド ──

    def _load_rewrite_file(self, path: Path) -> RewriteResult | None:
        """
        JSON ファイルを読み込み RewriteResult として復元する。

        Returns:
            RewriteResult: 復元したリライト結果。読み込み失敗時は None。
        """
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return _dict_to_rewrite_result(data)
        except json.JSONDecodeError as e:
            print(f"  [REVIEW WARNING] JSON parse 失敗（スキップ）: {path.name} - {e}")
            return None
        except (KeyError, TypeError, ValueError) as e:
            print(f"  [REVIEW WARNING] データ形式エラー（スキップ）: {path.name} - {e}")
            return None
        except OSError as e:
            print(f"  [REVIEW WARNING] ファイル読み込み失敗（スキップ）: {path.name} - {e}")
            return None

    def _load_review_file(self, path: Path) -> RewriteReviewResult | None:
        """
        JSON ファイルを読み込み RewriteReviewResult として復元する。

        Returns:
            RewriteReviewResult: 復元したレビュー結果。読み込み失敗時は None。
        """
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return _dict_to_review_result(data)
        except json.JSONDecodeError as e:
            print(f"  [REVIEW WARNING] レビューJSON parse 失敗（スキップ）: {path.name} - {e}")
            return None
        except (KeyError, TypeError, ValueError) as e:
            print(f"  [REVIEW WARNING] レビューデータ形式エラー（スキップ）: {path.name} - {e}")
            return None
        except OSError as e:
            print(f"  [REVIEW WARNING] レビューファイル読み込み失敗（スキップ）: {path.name} - {e}")
            return None


def _dict_to_rewrite_result(data: dict) -> RewriteResult:
    """dict から RewriteResult を復元する。"""
    created_at_raw = data.get("created_at", "")
    try:
        created_at = datetime.fromisoformat(created_at_raw) if created_at_raw else datetime.now()
    except ValueError:
        created_at = datetime.now()

    return RewriteResult(
        article_id=str(data.get("article_id", "")),
        title=str(data.get("title", "")),
        permalink=data.get("permalink"),
        prompt_version=str(data.get("prompt_version", "v1")),
        original_content=str(data.get("original_content", "")),
        rewrite_draft=str(data.get("rewrite_draft", "")),
        improvement_summary=str(data.get("improvement_summary", "")),
        changes=_to_str_list(data.get("changes", [])),
        raw_response=str(data.get("raw_response", "")),
        created_at=created_at,
        success=bool(data.get("success", False)),
        error_message=data.get("error_message"),
    )


def _dict_to_review_result(data: dict) -> RewriteReviewResult:
    """dict から RewriteReviewResult を復元する。"""
    created_at_raw  = data.get("created_at", "")
    reviewed_at_raw = data.get("reviewed_at", "")

    try:
        created_at = datetime.fromisoformat(created_at_raw) if created_at_raw else datetime.now()
    except ValueError:
        created_at = datetime.now()

    try:
        reviewed_at = datetime.fromisoformat(reviewed_at_raw) if reviewed_at_raw else datetime.now()
    except ValueError:
        reviewed_at = datetime.now()

    try:
        review_status = ReviewStatus(data.get("review_status", "pending"))
    except ValueError:
        review_status = ReviewStatus.PENDING

    return RewriteReviewResult(
        article_id=str(data.get("article_id", "")),
        title=str(data.get("title", "")),
        permalink=data.get("permalink"),
        review_status=review_status,
        review_note=str(data.get("review_note", "")),
        original_char_count=int(data.get("original_char_count", 0)),
        rewrite_char_count=int(data.get("rewrite_char_count", 0)),
        char_diff=int(data.get("char_diff", 0)),
        original_line_count=int(data.get("original_line_count", 0)),
        rewrite_line_count=int(data.get("rewrite_line_count", 0)),
        line_diff=int(data.get("line_diff", 0)),
        change_ratio=float(data.get("change_ratio", 0.0)),
        diff_summary=_to_str_list(data.get("diff_summary", [])),
        changes_count=int(data.get("changes_count", 0)),
        improvement_summary=str(data.get("improvement_summary", "")),
        changes=_to_str_list(data.get("changes", [])),
        created_at=created_at,
        reviewed_at=reviewed_at,
        success=bool(data.get("success", False)),
    )


def _to_str_list(value) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if item is not None]
