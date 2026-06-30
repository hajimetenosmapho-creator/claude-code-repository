"""
AiPublishResult の読み書きと投稿対象の選別を担うモジュール（v1.18.0）

Single Responsibility:
    - RewriteReviewRepository を通じて採用済みレビューとリライト結果を読み込む
    - 重複投稿防止フィルタ（filter_unpublished）を提供する
    - outputs/ai_publishes/ 配下に AiPublishResult JSON を保存・読み込む

禁止事項:
    - WordPress API の呼び出し（WordPressDraftClient の責務）
    - AiPublishResult の生成（AiPublishService の責務）
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .ai_publish_result import AiPublishResult
from .rewrite_result import RewriteResult
from .rewrite_review_repository import RewriteReviewRepository
from .rewrite_review_result import ReviewStatus, RewriteReviewResult


class AiPublishRepository:
    """
    AiPublishResult の読み書きと投稿対象の選別を担うリポジトリ。

    内部で RewriteReviewRepository を使ってレビュー・リライト結果を読み込む。
    自身は outputs/ai_publishes/ のみを読み書きする。
    """

    def __init__(
        self,
        rewrite_review_repo: RewriteReviewRepository,
        publish_dir: Path,
    ):
        self._rewrite_review_repo = rewrite_review_repo
        self._publish_dir = publish_dir

    @classmethod
    def from_paths(
        cls,
        review_dir: str | Path = "outputs/ai_rewrite_reviews",
        rewrite_dir: str | Path = "outputs/ai_rewrites",
        publish_dir: str | Path = "outputs/ai_publishes",
        base_dir: Path | None = None,
    ) -> "AiPublishRepository":
        """
        パスから AiPublishRepository を構築する。

        Args:
            review_dir:  レビュー結果 JSON の格納ディレクトリ
            rewrite_dir: リライト結果 JSON の格納ディレクトリ
            publish_dir: 投稿結果 JSON の保存先ディレクトリ
            base_dir:    相対パスの基準ディレクトリ（None の場合はそのまま使用）
        """
        if base_dir is not None:
            rv_dir  = base_dir / review_dir
            rw_dir  = base_dir / rewrite_dir
            pub_dir = base_dir / publish_dir
        else:
            rv_dir  = Path(review_dir)
            rw_dir  = Path(rewrite_dir)
            pub_dir = Path(publish_dir)

        rewrite_review_repo = RewriteReviewRepository(
            rewrite_dir=rw_dir,
            review_dir=rv_dir,
        )
        return cls(rewrite_review_repo=rewrite_review_repo, publish_dir=pub_dir)

    # ── 採用済みレビューの読み込み ──

    def load_adopted_reviews(self) -> list[RewriteReviewResult]:
        """
        review_status == ADOPTED のレビュー結果を返す（reviewed_at 降順）。

        Returns:
            list[RewriteReviewResult]: 採用済みレビューのリスト
        """
        all_reviews = self._rewrite_review_repo.load_reviews()
        return [r for r in all_reviews if r.review_status == ReviewStatus.ADOPTED]

    def load_rewrite_by_article_id(self, article_id: str) -> RewriteResult | None:
        """
        指定 article_id の最新 success=True の RewriteResult を返す。

        load_rewrite_by_article_id() は created_at 降順で並んでいるため、
        先頭の success=True が最新の成功結果。

        Args:
            article_id: 記事識別子（slug）

        Returns:
            RewriteResult: 最新の成功リライト結果。見つからない場合は None。
        """
        results = self._rewrite_review_repo.load_rewrite_by_article_id(article_id)
        for r in results:
            if r.success:
                return r
        return None

    # ── 重複投稿防止フィルタ ──

    def filter_unpublished(
        self,
        reviews: list[RewriteReviewResult],
    ) -> list[RewriteReviewResult]:
        """
        success=True の投稿結果がまだない記事のみ返す。

        既に success=True の AiPublishResult が存在する article_id はスキップ対象。
        success=False（スキップ・エラー）の結果は「未投稿」として扱い、再試行を許可する。

        Args:
            reviews: 絞り込み対象のレビューリスト

        Returns:
            list[RewriteReviewResult]: まだ投稿されていないレビューのリスト
        """
        already_published = {
            r.article_id
            for r in self.load_publish_results()
            if r.success
        }
        return [r for r in reviews if r.article_id not in already_published]

    # ── AiPublishResult の読み書き ──

    def save(self, result: AiPublishResult) -> Path | None:
        """
        AiPublishResult を publish_dir に JSON として保存する。

        ファイル名形式: YYYYMMDD_{article_id}_publish.json

        Args:
            result: 保存する AiPublishResult（success=False でも保存する）

        Returns:
            Path: 保存したファイルパス。失敗時は None。
        """
        try:
            self._publish_dir.mkdir(parents=True, exist_ok=True)
            date_str = result.published_at.strftime("%Y%m%d")
            filename = f"{date_str}_{result.article_id}_publish.json"
            path = self._publish_dir / filename
            with path.open("w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, ensure_ascii=False, indent=2)
            print(f"  [PUBLISH] JSON 保存: {path}")
            return path
        except OSError as e:
            print(f"  [PUBLISH WARNING] JSON 保存失敗（処理継続）: {e}")
            return None

    def load_publish_results(self) -> list[AiPublishResult]:
        """
        publish_dir 配下の全 *_publish.json を読み込む。

        ファイルが存在しない場合は空リストを返す。
        不正ファイルは [PUBLISH WARNING] を出力してスキップする。

        Returns:
            list[AiPublishResult]: 読み込んだ投稿結果のリスト（published_at 降順）
        """
        if not self._publish_dir.exists():
            return []

        results: list[AiPublishResult] = []
        for path in sorted(self._publish_dir.glob("*_publish.json")):
            result = self._load_publish_file(path)
            if result is not None:
                results.append(result)

        results.sort(key=lambda r: r.published_at, reverse=True)
        return results

    def _load_publish_file(self, path: Path) -> AiPublishResult | None:
        """JSON ファイルを読み込み AiPublishResult として復元する。"""
        try:
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return _dict_to_publish_result(data)
        except json.JSONDecodeError as e:
            print(f"  [PUBLISH WARNING] JSON parse 失敗（スキップ）: {path.name} - {e}")
            return None
        except (KeyError, TypeError, ValueError) as e:
            print(f"  [PUBLISH WARNING] データ形式エラー（スキップ）: {path.name} - {e}")
            return None
        except OSError as e:
            print(f"  [PUBLISH WARNING] ファイル読み込み失敗（スキップ）: {path.name} - {e}")
            return None


def _dict_to_publish_result(data: dict) -> AiPublishResult:
    """dict から AiPublishResult を復元する。"""
    published_at_raw = data.get("published_at", "")
    try:
        published_at = (
            datetime.fromisoformat(published_at_raw) if published_at_raw else datetime.now()
        )
    except ValueError:
        published_at = datetime.now()

    src_created_at_raw = data.get("source_rewrite_created_at")
    try:
        source_rewrite_created_at = (
            datetime.fromisoformat(src_created_at_raw) if src_created_at_raw else None
        )
    except ValueError:
        source_rewrite_created_at = None

    return AiPublishResult(
        article_id=str(data.get("article_id", "")),
        title=str(data.get("title", "")),
        original_permalink=data.get("original_permalink"),
        source_review_status=str(data.get("source_review_status", "")),
        source_rewrite_created_at=source_rewrite_created_at,
        wp_post_id=data.get("wp_post_id"),
        wp_draft_slug=data.get("wp_draft_slug"),
        wp_edit_url=data.get("wp_edit_url"),
        wp_draft_permalink=data.get("wp_draft_permalink"),
        published_at=published_at,
        success=bool(data.get("success", False)),
        skipped=bool(data.get("skipped", False)),
        skip_reason=data.get("skip_reason"),
        error_message=data.get("error_message"),
    )
