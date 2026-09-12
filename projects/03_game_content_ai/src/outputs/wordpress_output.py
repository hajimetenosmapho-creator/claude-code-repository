"""
WordPress REST API への記事下書き投稿を担うモジュール。

Release 6.32（Side-Effect Fail-Closed & Human Review Safety、呼び出し箇所A）:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    15.7節・22.3.1節。__init__() に side_effect_execution_context（必須）・
    draft_state_manager（Optional、RETRY_LINEAGE_PROTECTED時のみ必須）を追加し、
    save() 冒頭で validate_side_effect_execution_context() を呼んでから
    requests.post() 前後に write-ahead 呼び出しを挿入する。
"""

import os
from typing import TYPE_CHECKING

import requests
from .base import BaseOutput, ArticleData
from .save_result import SaveResult
from .taxonomy_config import resolve_taxonomy

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


class WordPressOutput(BaseOutput):
    """
    WordPress REST API に記事を下書きとして投稿する。
    WP_SITE_URL / WP_USERNAME / WP_APP_PASSWORD が未設定の場合は
    is_available() が False を返し、OutputManager によりスキップされる。
    """

    def __init__(
        self,
        site_url: str,
        username: str,
        app_password: str,
        side_effect_execution_context: "RetryLineageProtectedExecutionContext | LegacyDirectExecutionContext",
        draft_state_manager: "WordPressDraftStateManager | None" = None,
        manifest_registrar: "ManifestRegistrarFacade | None" = None,
    ):
        self.site_url = site_url.rstrip("/")
        self.username = username
        self.app_password = app_password
        self._context = side_effect_execution_context
        self._draft_state_manager = draft_state_manager
        self._manifest_registrar = manifest_registrar

    @classmethod
    def from_env_with_context(
        cls,
        side_effect_execution_context: "RetryLineageProtectedExecutionContext | LegacyDirectExecutionContext",
        draft_state_manager: "WordPressDraftStateManager | None" = None,
        manifest_registrar: "ManifestRegistrarFacade | None" = None,
    ) -> "WordPressOutput":
        """main.py起動時に一度だけ解決されたside_effect_execution_contextを
        注入するfactory（15.7節「main.py側の配線」）。"""
        return cls(
            site_url=os.getenv("WP_SITE_URL", ""),
            username=os.getenv("WP_USERNAME", ""),
            app_password=os.getenv("WP_APP_PASSWORD", ""),
            side_effect_execution_context=side_effect_execution_context,
            draft_state_manager=draft_state_manager,
            manifest_registrar=manifest_registrar,
        )

    def is_available(self) -> bool:
        """WP_SITE_URL / WP_USERNAME / WP_APP_PASSWORD がすべて設定されている場合のみ True。"""
        return bool(self.site_url and self.username and self.app_password)

    def save(self, article: ArticleData) -> SaveResult:
        """
        WordPress REST API に記事を投稿し、SaveResult を返す。

        v1.11.0: post_id を WordPress API レスポンスの "id" フィールドから直接取得する。
                 edit_url からの正規表現抽出（v1.8.0 の暫定実装）を廃止する。

        Args:
            article: 投稿対象の記事データ

        Returns:
            SaveResult: 投稿結果（post_id / edit_url / slug / permalink 等を格納）

        Raises:
            RuntimeError: 投稿に失敗した場合（ステータスコードが 200/201 以外）
            SideEffectExecutionModeContractError: side_effect_execution_context が
                欠落・unknown・矛盾している場合（15.7節、requests.post()より前で
                fail-closedする。external I/O = 0）。
        """
        context = validate_side_effect_execution_context(self._context)

        identity = None
        if isinstance(context, RetryLineageProtectedExecutionContext):
            identity = SideEffectOperationIdentity(
                root_run_id=context.root_run_id,
                attempt_ordinal=context.attempt_ordinal,
                operation_kind=ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION,
                effect_site=SideEffectSite.NEWS_STEP,
                operation_instance_key=article.slug,
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
                        ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION, SideEffectSite.NEWS_STEP,
                        article.slug,
                    ),
                )
            )
            self._draft_state_manager.record_attempted(identity, context.member_run_id)
            # durable ACK確認後にのみ、以降のrequests.post()（実I/O）へ進む
            # （WORDPRESS_DRAFT_CREATIONはIO_ARMEDフェーズを持たない単一フェーズの
            #  ため、ACK＝record_attempted()の成功のみで足りる、9.3・9.9.1節）。

        # isinstance(context, LegacyDirectExecutionContext)の場合、以降write-ahead
        # 呼び出しを一切行わず、既存（6.31以前）のロジックのまま進む。

        endpoint = f"{self.site_url}/wp-json/wp/v2/posts"
        categories, tags = resolve_taxonomy(article.importance)
        payload = {
            "title": article.seo_title,
            "content": article.article_body,
            "status": article.publish_status.value,  # PublishStatus Enum から文字列に変換
            "excerpt": article.excerpt,
            "slug": article.slug,
        }
        if categories:
            payload["categories"] = categories
        if tags:
            payload["tags"] = tags
        if article.featured_media_id > 0:
            payload["featured_media"] = article.featured_media_id

        response = requests.post(
            endpoint,
            json=payload,
            auth=(self.username, self.app_password),
            timeout=30,
        )

        if response.status_code not in (200, 201):
            raise RuntimeError(
                f"WordPress投稿失敗 (HTTP {response.status_code}): {response.text[:200]}"
            )

        response_data = response.json()
        # v1.11.0: post_id を API レスポンスから直接取得（正規表現抽出を廃止）
        post_id      = response_data.get("id")
        actual_slug  = response_data.get("slug", "")
        actual_status = response_data.get("status", "")
        actual_title  = response_data.get("title", {}).get("rendered", "")
        permalink     = response_data.get("link", "")
        edit_url      = f"{self.site_url}/wp-admin/post.php?post={post_id}&action=edit"

        print(f"      投稿ID  : {post_id}")
        print(f"      slug    : {actual_slug}")
        print(f"      ステータス: {actual_status}")
        print(f"      編集URL : {edit_url}")

        if identity is not None:
            self._draft_state_manager.record_confirmed(identity, context.member_run_id, post_id)
            # POST成功後・record_confirmed()前にクラッシュした場合、durable stateは
            # 「ATTEMPTED」のまま残り、restart後は12.2節の決定表を経て
            # resolve_final_disposition()（13章）がHUMAN_REVIEW_REQUIREDへ導く。

        return SaveResult(
            success=True,
            output_type="wordpress",
            post_id=post_id,
            title=actual_title,
            slug=actual_slug,
            status=actual_status,
            edit_url=edit_url,
            permalink=permalink,
            raw_response=response_data,
        )
