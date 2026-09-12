"""
AI 公開サービス（v1.18.0）

Single Responsibility:
    - AiPublishRepository から採用済みレビューを取得する
    - 重複チェックを経て投稿対象を選別する
    - WordPressDraftClient で WordPress 下書き投稿を実行する
    - AiPublishResult を生成して保存する
    - AiPublishReportBuilder で Markdown レポートを生成・保存する

禁止事項:
    - Claude API の呼び出し
    - JSON ファイルの直接読み書き（Repository の責務）
    - Markdown 生成ロジック（AiPublishReportBuilder の責務）
    - WordPress への publish（draft のみ）

設計方針（Configuration First / Null Object Pattern）:
    AI_PUBLISH_ENABLED=false → NullAiPublishService を返す
    WordPress 認証情報未設定  → NullAiPublishService を返す
"""
from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING

from .ai_publish_config import AiPublishConfig
from .ai_publish_report_builder import AiPublishReportBuilder
from .ai_publish_repository import AiPublishRepository
from .ai_publish_result import AiPublishResult
from .rewrite_result import RewriteResult
from .rewrite_review_result import RewriteReviewResult
from .wordpress_draft_client import NullWordPressDraftClient, WordPressDraftClient

from protected_operation_manifest import build_manifest_entry, raise_if_not_registered
from side_effect_safety import (
    ExecutionModeFailureReasonCode,
    ProtectedSideEffectKind,
    RetryLineageProtectedExecutionContext,
    SideEffectExecutionModeContractError,
    SideEffectOperationIdentity,
    SideEffectSite,
    validate_side_effect_execution_context,
)

if TYPE_CHECKING:
    from protected_operation_manifest import ManifestRegistrarFacade
    from side_effect_safety import LegacyDirectExecutionContext
    from wordpress_draft_state import WordPressDraftStateManager


class AiPublishService:
    """
    採用済みリライト案を WordPress 下書きとして投稿するサービス。

    処理フロー:
        AiPublishRepository.load_adopted_reviews()
            → _dedup_by_article_id()             → 同一記事は最新レビューのみ残す
            → filter_unpublished()                → 未投稿のみ対象
            → load_rewrite_by_article_id()        → リライト本文を取得
            → WordPressDraftClient.post_draft()   → WordPress 下書き投稿
            → AiPublishResult を生成
            → AiPublishRepository.save()          → JSON 保存
            → AiPublishReportBuilder.build()      → Markdown 生成
            → _save_report()                      → Markdown 保存
    """

    def __init__(
        self,
        repository: AiPublishRepository,
        client: "WordPressDraftClient | NullWordPressDraftClient",
        report_dir: Path,
        draft_state_manager: "WordPressDraftStateManager | None" = None,
        manifest_registrar: "ManifestRegistrarFacade | None" = None,
    ):
        self._repository = repository
        self._client     = client
        self._report_dir = report_dir
        self._builder    = AiPublishReportBuilder()
        self._draft_state_manager = draft_state_manager
        self._manifest_registrar = manifest_registrar

    @classmethod
    def from_env(
        cls,
        base_dir: Path | None = None,
        draft_state_manager: "WordPressDraftStateManager | None" = None,
        manifest_registrar: "ManifestRegistrarFacade | None" = None,
    ) -> "AiPublishService | NullAiPublishService":
        """
        環境変数から設定を読み込み、AiPublishService または NullAiPublishService を返す。

        is_ready() が False の場合（enabled=False または認証情報不足）は
        NullAiPublishService を返す。

        Args:
            draft_state_manager: Release 6.32、15.6節。呼び出し箇所C
                （`_post()`）のwrite-ahead記録に使うWordPressDraftStateManager
                （呼び出し箇所Aと同一Foundation・同一storeを再利用する）。
            manifest_registrar: Architecture Amendment、Protected Operation
                Manifest。呼び出し箇所Cのmanifest登録に使うManifestRegistrarFacade。
        """
        config = AiPublishConfig.from_env()
        if not config.is_ready():
            return NullAiPublishService()

        client = WordPressDraftClient(
            url=config.wordpress_url or "",
            username=config.wordpress_username or "",
            app_password=config.wordpress_app_password or "",
        )
        repository = AiPublishRepository.from_paths(base_dir=base_dir)
        report_dir = (
            (base_dir / "outputs/ai_publish_reports")
            if base_dir is not None
            else Path("outputs/ai_publish_reports")
        )
        return cls(
            repository=repository, client=client, report_dir=report_dir,
            draft_state_manager=draft_state_manager, manifest_registrar=manifest_registrar,
        )

    def run(
        self,
        article_id: str | None = None,
        *,
        side_effect_execution_context: "RetryLineageProtectedExecutionContext | LegacyDirectExecutionContext",
    ) -> Path | None:
        """
        採用済みリライト案を WordPress 下書きとして投稿する。

        Args:
            article_id: 絞り込む記事ID（None = 全件）
            side_effect_execution_context: Release 6.32、15.6節。呼び出し箇所C
                （`_post()`）へ伝播するExplicit Side-Effect Execution Mode。
                必須引数（デフォルトなし）——省略時の暗黙のデフォルト値は
                存在しない。呼び出し元は必ず明示的に値を渡さなければならない。

        Returns:
            Path: 保存した Markdown レポートのパス。保存失敗時は None。
        """
        adopted = self._repository.load_adopted_reviews()
        if article_id is not None:
            adopted = [r for r in adopted if r.article_id == article_id]

        # 同一 article_id で最新のレビューのみ残す（reviewed_at 降順なので先頭が最新）
        unique_adopted = _dedup_by_article_id(adopted)

        targets = self._repository.filter_unpublished(unique_adopted)
        print(f"  [PUBLISH] 採用済み: {len(unique_adopted)} 件 → 未投稿: {len(targets)} 件")

        results: list[AiPublishResult] = []
        for review in targets:
            result = self._process(review, side_effect_execution_context)
            self._repository.save(result)
            results.append(result)

        report_content = self._builder.build(results)
        return self._save_report(report_content)

    def get_results(self, article_id: str | None = None) -> list[AiPublishResult]:
        """
        保存済みの投稿結果を返す（レポート保存なし）。

        Args:
            article_id: 絞り込む記事ID（None = 全件）

        Returns:
            list[AiPublishResult]: 投稿結果のリスト
        """
        results = self._repository.load_publish_results()
        if article_id is not None:
            return [r for r in results if r.article_id == article_id]
        return results

    def _process(
        self,
        review: RewriteReviewResult,
        side_effect_execution_context: "RetryLineageProtectedExecutionContext | LegacyDirectExecutionContext",
    ) -> AiPublishResult:
        """
        1件のレビューを処理し、AiPublishResult を生成する。

        リライト結果が見つからない場合は success=False として返す。
        """
        rewrite = self._repository.load_rewrite_by_article_id(review.article_id)
        if rewrite is None:
            print(f"  [PUBLISH WARNING] リライト結果が見つかりません: {review.article_id}")
            return AiPublishResult(
                article_id=review.article_id,
                title=review.title,
                original_permalink=review.permalink,
                source_review_status=review.review_status.value,
                source_rewrite_created_at=None,
                success=False,
                error_message="リライト結果が見つかりません",
            )

        return self._post(review, rewrite, side_effect_execution_context)

    def _post(
        self,
        review: RewriteReviewResult,
        rewrite: RewriteResult,
        side_effect_execution_context: "RetryLineageProtectedExecutionContext | LegacyDirectExecutionContext",
    ) -> AiPublishResult:
        """
        WordPressDraftClient を呼び出し、AiPublishResult を生成する。

        スラッグ形式: {article_id}-rewrite-{YYYYMMDD}（元記事と重複しない）

        Release 6.32（15.6・22.3.3節）: 呼び出し箇所C。
        RETRY_LINEAGE_PROTECTED時のみ、post_draft()（実I/O）の前に
        record_attempted()のdurable ACKを確認する（write-ahead-before-I/O契約、
        9.9.3節と同型のOrdering Contract）。identityはoperation_instance_key に
        review.article_id（new_slugではなく、日付非依存の安定したarticle identity）
        を用いる。LEGACY_DIRECT時は既存（6.31以前）のロジックのまま、write-ahead
        呼び出しを一切行わない。

        Raises:
            SideEffectExecutionModeContractError: side_effect_execution_context が
                欠落・unknown・矛盾している場合（post_draft()より前でfail-closed
                する。external I/O = 0）。
        """
        context = validate_side_effect_execution_context(side_effect_execution_context)

        new_slug = f"{review.article_id}-rewrite-{date.today().strftime('%Y%m%d')}"

        identity = None
        if isinstance(context, RetryLineageProtectedExecutionContext):
            identity = SideEffectOperationIdentity(
                root_run_id=context.root_run_id,
                attempt_ordinal=context.attempt_ordinal,
                operation_kind=ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION,
                effect_site=SideEffectSite.PUBLISH_STEP,
                operation_instance_key=review.article_id,
            )
            # Codex Final Review Blocking#2対応：protected modeでは
            # manifest_registrarの省略によるregistration bypassを許可しない
            # （legacy modeのみ既存どおり省略を許容する）。「composition rootが
            # 必ず注入するはず」という前提のみをsafety guaranteeにせず、この
            # production class自身がfail-closedする。
            if self._manifest_registrar is None:
                raise SideEffectExecutionModeContractError(
                    ExecutionModeFailureReasonCode.PROTECTED_MANIFEST_REGISTRAR_REQUIRED,
                )
            # Architecture Amendment（Protected Operation Manifest、§4.2・§5）：
            # 既存write-ahead呼び出し（record_attempted()）より先にmanifestへ
            # 自分自身のentryを登録する。durable ACKを必ず確認し（raise_if_not_
            # registered()）、未ack時はrecord_attempted()・外部I/Oのいずれへも
            # 進まずfail-closedする。
            raise_if_not_registered(
                self._manifest_registrar.register(
                    context.root_run_id, context.attempt_ordinal, context.member_run_id,
                    build_manifest_entry(
                        ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION, SideEffectSite.PUBLISH_STEP,
                        review.article_id,
                    ),
                )
            )
            self._draft_state_manager.record_attempted(identity, context.member_run_id)
            # durable ACK確認後にのみ、以降のpost_draft()（実I/O）へ進む
            # （WORDPRESS_DRAFT_CREATIONはIO_ARMEDフェーズを持たない単一フェーズの
            #  ため、ACK＝record_attempted()の成功のみで足りる、9.3・9.9.1節）。

        # isinstance(context, LegacyDirectExecutionContext)の場合、以降write-ahead
        # 呼び出しを一切行わず、既存（6.31以前）のロジックのまま進む。

        try:
            response = self._client.post_draft(
                title=review.title,
                content=rewrite.rewrite_draft,
                slug=new_slug,
            )
        except RuntimeError as e:
            print(f"  [PUBLISH WARNING] 投稿失敗（処理継続）: {review.article_id} - {e}")
            return AiPublishResult(
                article_id=review.article_id,
                title=review.title,
                original_permalink=review.permalink,
                source_review_status=review.review_status.value,
                source_rewrite_created_at=rewrite.created_at,
                success=False,
                error_message=str(e),
            )

        if response.get("skipped"):
            print(f"  [PUBLISH] スキップ: {review.article_id} ({response.get('reason')})")
            return AiPublishResult(
                article_id=review.article_id,
                title=review.title,
                original_permalink=review.permalink,
                source_review_status=review.review_status.value,
                source_rewrite_created_at=rewrite.created_at,
                skipped=True,
                skip_reason=response.get("reason"),
                success=False,
            )

        print(f"  [PUBLISH] 成功: {review.article_id} → post_id={response.get('post_id')}")

        if identity is not None:
            self._draft_state_manager.record_confirmed(identity, context.member_run_id, response.get("post_id"))
            # POST成功後・record_confirmed()前にクラッシュした場合、durable stateは
            # 「ATTEMPTED」のまま残り、restart後は12.2節の決定表を経て
            # resolve_final_disposition()（13章）がHUMAN_REVIEW_REQUIREDへ導く。

        return AiPublishResult(
            article_id=review.article_id,
            title=review.title,
            original_permalink=review.permalink,
            source_review_status=review.review_status.value,
            source_rewrite_created_at=rewrite.created_at,
            wp_post_id=response.get("post_id"),
            wp_draft_slug=response.get("slug"),
            wp_edit_url=response.get("edit_url"),
            wp_draft_permalink=response.get("permalink"),
            success=True,
        )

    def _save_report(self, content: str) -> Path | None:
        """Markdown レポートを report_dir に保存する。"""
        try:
            self._report_dir.mkdir(parents=True, exist_ok=True)
            date_str = date.today().strftime("%Y%m%d")
            filename = f"{date_str}_ai_publish_report.md"
            path = self._report_dir / filename
            with path.open("w", encoding="utf-8") as f:
                f.write(content)
            print(f"  [PUBLISH] レポート保存: {path}")
            return path
        except OSError as e:
            print(f"  [PUBLISH WARNING] レポート保存失敗: {e}")
            return None


class NullAiPublishService:
    """
    AI_PUBLISH_ENABLED=false または WordPress 認証情報未設定時のダミー実装。
    すべてのメソッドが no-op で動作する。既存処理を停止させない。
    """

    def run(
        self,
        article_id: str | None = None,
        *,
        side_effect_execution_context: "RetryLineageProtectedExecutionContext | LegacyDirectExecutionContext",
    ) -> None:
        print("  [PUBLISH] AI 公開機能が無効です（AI_PUBLISH_ENABLED=false または認証情報未設定）。")
        return None

    def get_results(self, article_id: str | None = None) -> list:
        return []


def _dedup_by_article_id(reviews: list[RewriteReviewResult]) -> list[RewriteReviewResult]:
    """
    同一 article_id の中で最初のもの（reviewed_at 降順なので最新）のみ残す。
    """
    seen: set[str] = set()
    result: list[RewriteReviewResult] = []
    for review in reviews:
        if review.article_id not in seen:
            result.append(review)
            seen.add(review.article_id)
    return result
