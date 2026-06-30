"""
AiPublishReviewResult の読み書きを担うモジュール（v1.19.0）

Single Responsibility:
    - AiPublishRepository を通じて投稿結果（AiPublishResult）を読み込む
    - outputs/ai_publish_reviews/ 配下に AiPublishReviewResult JSON を保存・読み込む

禁止事項:
    - WordPress API の呼び出し
    - AiPublishReviewResult の生成（AiPublishReviewService の責務）
    - AiPublishResult の生成・変更（AiPublishRepository の責務）
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .ai_publish_repository import AiPublishRepository
from .ai_publish_result import AiPublishResult
from .ai_publish_review_result import AiPublishReviewResult, PublishReviewStatus


class AiPublishReviewRepository:
    """
    AiPublishResult の読み込みと AiPublishReviewResult の読み書きを担うリポジトリ。

    ディレクトリ:
        _publish_repo: AiPublishRepository（outputs/ai_publishes/ 読み取り委譲）
        _review_dir:   outputs/ai_publish_reviews/（AiPublishReviewResult 読み書き）
    """

    def __init__(
        self,
        publish_repo: AiPublishRepository,
        review_dir: Path,
    ):
        self._publish_repo = publish_repo
        self._review_dir   = review_dir

    @classmethod
    def from_paths(
        cls,
        publish_dir: str | Path = "outputs/ai_publishes",
        review_dir:  str | Path = "outputs/ai_publish_reviews",
        base_dir: Path | None = None,
    ) -> "AiPublishReviewRepository":
        """
        パスから AiPublishReviewRepository を構築する。

        Args:
            publish_dir: 投稿結果 JSON の格納ディレクトリ（読み取りのみ）
            review_dir:  レビュー結果 JSON の保存先ディレクトリ
            base_dir:    相対パスの基準ディレクトリ（None の場合はそのまま使用）
        """
        rev_dir = (base_dir / review_dir) if base_dir is not None else Path(review_dir)

        publish_repo = AiPublishRepository.from_paths(
            publish_dir=publish_dir,
            base_dir=base_dir,
        )
        return cls(publish_repo=publish_repo, review_dir=rev_dir)

    # ── AiPublishResult の読み込み ──

    def load_publish_results(self, article_id: str | None = None) -> list[AiPublishResult]:
        """
        outputs/ai_publishes/ から全投稿結果を読み込む。

        Args:
            article_id: 絞り込む記事ID（None = 全件）

        Returns:
            list[AiPublishResult]: 投稿結果のリスト（published_at 降順）
        """
        results = self._publish_repo.load_publish_results()
        if article_id is not None:
            return [r for r in results if r.article_id == article_id]
        return results

    # ── AiPublishReviewResult の読み書き ──

    def save_review(self, review: AiPublishReviewResult) -> Path | None:
        """
        AiPublishReviewResult を review_dir に JSON として保存する。

        ファイル名形式: YYYYMMDD_{article_id}_publish_review.json

        Args:
            review: 保存する AiPublishReviewResult

        Returns:
            Path: 保存したファイルパス。失敗時は None。
        """
        try:
            self._review_dir.mkdir(parents=True, exist_ok=True)
            date_str = review.reviewed_at.strftime("%Y%m%d")
            filename = f"{date_str}_{review.article_id}_publish_review.json"
            path = self._review_dir / filename
            with path.open("w", encoding="utf-8") as f:
                json.dump(review.to_dict(), f, ensure_ascii=False, indent=2)
            print(f"  [PUBLISH REVIEW] JSON 保存: {path}")
            return path
        except OSError as e:
            print(f"  [PUBLISH REVIEW WARNING] JSON 保存失敗（処理継続）: {e}")
            return None

    def load_reviews(self) -> list[AiPublishReviewResult]:
        """
        review_dir 配下の全 *_publish_review.json を読み込む。

        ファイルが存在しない場合は空リストを返す。
        不正ファイルは [PUBLISH REVIEW WARNING] を出力してスキップする。

        Returns:
            list[AiPublishReviewResult]: 読み込んだレビュー結果のリスト（reviewed_at 降順）
        """
        if not self._review_dir.exists():
            return []

        reviews: list[AiPublishReviewResult] = []
        for path in sorted(self._review_dir.glob("*_publish_review.json")):
            review = self._load_review_file(path)
            if review is not None:
                reviews.append(review)

        reviews.sort(key=lambda r: r.reviewed_at, reverse=True)
        return reviews

    def load_reviews_by_article_id(self, article_id: str) -> list[AiPublishReviewResult]:
        """
        指定した article_id の AiPublishReviewResult を返す。

        Args:
            article_id: 記事識別子（slug）

        Returns:
            list[AiPublishReviewResult]: 一致するレビュー結果のリスト
        """
        return [r for r in self.load_reviews() if r.article_id == article_id]

    # ── 内部メソッド ──

    def _load_review_file(self, path: Path) -> AiPublishReviewResult | None:
        """JSON ファイルを読み込み AiPublishReviewResult として復元する。"""
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return _dict_to_publish_review_result(data)
        except json.JSONDecodeError as e:
            print(f"  [PUBLISH REVIEW WARNING] JSON parse 失敗（スキップ）: {path.name} - {e}")
            return None
        except (KeyError, TypeError, ValueError) as e:
            print(f"  [PUBLISH REVIEW WARNING] データ形式エラー（スキップ）: {path.name} - {e}")
            return None
        except OSError as e:
            print(f"  [PUBLISH REVIEW WARNING] ファイル読み込み失敗（スキップ）: {path.name} - {e}")
            return None


def _dict_to_publish_review_result(data: dict) -> AiPublishReviewResult:
    """dict から AiPublishReviewResult を復元する。"""
    published_at_raw = data.get("published_at", "")
    try:
        published_at = (
            datetime.fromisoformat(published_at_raw) if published_at_raw else datetime.now()
        )
    except ValueError:
        published_at = datetime.now()

    reviewed_at_raw = data.get("reviewed_at", "")
    try:
        reviewed_at = (
            datetime.fromisoformat(reviewed_at_raw) if reviewed_at_raw else datetime.now()
        )
    except ValueError:
        reviewed_at = datetime.now()

    try:
        review_status = PublishReviewStatus(data.get("review_status", "pending"))
    except ValueError:
        review_status = PublishReviewStatus.PENDING

    return AiPublishReviewResult(
        article_id=str(data.get("article_id", "")),
        title=str(data.get("title", "")),
        original_permalink=data.get("original_permalink"),
        source_review_status=str(data.get("source_review_status", "")),
        wp_post_id=data.get("wp_post_id"),
        wp_draft_slug=data.get("wp_draft_slug"),
        wp_edit_url=data.get("wp_edit_url"),
        wp_draft_permalink=data.get("wp_draft_permalink"),
        published_at=published_at,
        publish_status=str(data.get("publish_status", "failed")),
        publish_success=bool(data.get("publish_success", False)),
        publish_skipped=bool(data.get("publish_skipped", False)),
        publish_skip_reason=data.get("publish_skip_reason"),
        publish_error=data.get("publish_error"),
        is_publish_candidate=bool(data.get("is_publish_candidate", False)),
        review_status=review_status,
        review_note=str(data.get("review_note", "")),
        reviewed_at=reviewed_at,
    )
