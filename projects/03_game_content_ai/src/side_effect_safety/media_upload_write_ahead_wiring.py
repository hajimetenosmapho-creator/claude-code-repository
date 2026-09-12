"""
Media Upload Write-Ahead Wiring（Release 6.32、呼び出し箇所B、22.3.2節）

Source of Truth: docs/design/side_effect_fail_closed_human_review_safety_foundation.md
15.4・15.4.1・22.3.2節。

`ArticleFeaturedMediaRuntime`／`ArticleFeaturedMediaOrchestrator`／
`ArticleFeaturedMediaCompositionRoot`（Foundation 3ファイル）はいずれも
無変更のまま維持する。本モジュールはそれらの外側にある6.32 integration層
（wiring）であり、`ArticleFeaturedMediaCompositionRoot.from_env()`は経由しない
（経由するとdecorator非注入のOrchestratorが確定してしまうため）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from article_featured_media_composition import ArticleFeaturedMediaCompositionRoot
from article_featured_media_orchestration import ArticleFeaturedMediaOrchestrator
from article_featured_media_runtime import ArticleFeaturedMediaRuntime
from generated_image_wordpress_media import GeneratedImageWordPressMediaUploader
from image_generation_config import ImageGenerationConfig
from openai_image_generation import OpenAIImageGenerator
from wordpress_media import WordPressMediaUploader

from .media_upload_write_ahead_capability import WriteAheadAwareMediaUploadCapability

if TYPE_CHECKING:
    from article_featured_media_orchestration import GeneratedImageUploadCapability
    from article_featured_media_runtime import FeaturedMediaFailureObservation
    from ai_image_generation import AIImageGenerator
    from protected_operation_manifest import ManifestRegistrarFacade

    from .media_upload_safety_coordinator import MediaUploadSafetyCoordinator
    from .side_effect_execution_mode import LegacyDirectExecutionContext, RetryLineageProtectedExecutionContext
    from .side_effect_operation_identity import SideEffectOperationIdentity


@dataclass(frozen=True)
class MediaUploadWriteAheadAdapters:
    """
    プロセス起動時に1回だけ構築するadapter束。

    `from_env()`は`ArticleFeaturedMediaCompositionRoot.from_env()`と同一の
    環境変数読み取り・adapter構築ロジックを独立に複製する（`from_env()`自体は
    呼ばない）。credential解決・Fail Fastの挙動（ValueError無変換伝播）は
    既存`from_env()`と同一に保つ。
    """

    enabled: bool
    image_generator: "AIImageGenerator | None" = None
    base_media_uploader: "GeneratedImageUploadCapability | None" = None
    image_mime_type: str | None = None

    @classmethod
    def from_env(cls) -> "MediaUploadWriteAheadAdapters":
        config = ImageGenerationConfig.from_env()
        if not config.enabled:
            return cls(enabled=False)

        image_generator = OpenAIImageGenerator.from_env()
        image_mime_type = image_generator.output_mime_type

        wordpress_media_uploader = WordPressMediaUploader.from_env()
        base_media_uploader = GeneratedImageWordPressMediaUploader(wordpress_media_uploader)

        return cls(
            enabled=True,
            image_generator=image_generator,
            base_media_uploader=base_media_uploader,
            image_mime_type=image_mime_type,
        )


def build_protected_featured_media_runtime(
    adapters: "MediaUploadWriteAheadAdapters",
    media_upload_coordinator: "MediaUploadSafetyCoordinator",
    identity: "SideEffectOperationIdentity",
    member_run_id: str,
) -> "ArticleFeaturedMediaRuntime":
    """記事1件ごとに呼ばれる。Gate OFF/ONいずれの場合も、呼び出し元は分岐を
    問わずこの1つの関数を呼べば足りる（22.3.2節）。"""
    if not adapters.enabled:
        return ArticleFeaturedMediaRuntime(
            ArticleFeaturedMediaCompositionRoot(orchestrator=None, image_mime_type=None)
        )

    decorated_uploader = WriteAheadAwareMediaUploadCapability(
        adapters.base_media_uploader, media_upload_coordinator, identity, member_run_id,
    )
    orchestrator = ArticleFeaturedMediaOrchestrator(
        image_generator=adapters.image_generator,
        media_uploader=decorated_uploader,
    )
    root = ArticleFeaturedMediaCompositionRoot(
        orchestrator=orchestrator, image_mime_type=adapters.image_mime_type,
    )
    return ArticleFeaturedMediaRuntime(root)


@dataclass(frozen=True)
class ProtectedFeaturedMediaSideEffectBinding:
    """protected（RetryLineageProtectedExecutionContext）実行時のみ構築される。

    runtime自体はこのbindingに直接保持しない——`adapters`・
    `media_upload_coordinator`が、記事ごとに`build_protected_featured_media_runtime()`
    を呼ぶために必要十分な材料である。
    """

    context: "RetryLineageProtectedExecutionContext"
    media_upload_coordinator: "MediaUploadSafetyCoordinator"
    adapters: "MediaUploadWriteAheadAdapters"
    manifest_registrar: "ManifestRegistrarFacade | None" = None


@dataclass(frozen=True)
class LegacyFeaturedMediaSideEffectBinding:
    """legacy（LegacyDirectExecutionContext）実行時のみ構築される。

    media_upload_coordinator/adaptersへの参照自体を保持しないため、4 safety
    methods zero-call・protected dependency構築ゼロが構造的に保証される。
    """

    context: "LegacyDirectExecutionContext"
    runtime: "ArticleFeaturedMediaRuntime"


FeaturedMediaSideEffectBinding = (
    "ProtectedFeaturedMediaSideEffectBinding | LegacyFeaturedMediaSideEffectBinding"
)


class FeaturedMediaPropagatedFailure(Exception):
    """`_apply_featured_media_step()`がPROPAGATE対象の例外を分類した結果を、
    main.py記事ループまで運ぶための6.32 integration層専用exception。

    運ぶのは`FeaturedMediaFailureObservation`（Foundation型、無変更）のみで
    あり、元のraw exceptionオブジェクト・そのmessage・tracebackへの参照は
    一切保持しない。`raise`は対応する`except`ブロックの外側で行われるため、
    `carrier.__context__ is None`・`carrier.__cause__ is None`が常に成立する。
    """

    def __init__(self, observation: "FeaturedMediaFailureObservation") -> None:
        self.observation = observation
        super().__init__()


def build_protected_featured_media_side_effect_binding(
    protected_context: "RetryLineageProtectedExecutionContext",
    media_upload_coordinator: "MediaUploadSafetyCoordinator",
    adapters: "MediaUploadWriteAheadAdapters",
    manifest_registrar: "ManifestRegistrarFacade | None",
) -> "ProtectedFeaturedMediaSideEffectBinding":
    """protected専用builder。4引数すべて必須（デフォルト値なし、§28.-35#7 H3aの
    「暗黙のdefaultを持たない」契約をmanifest_registrar追加後も維持する）。
    manifest_registrarを使わない呼び出し元は明示的にNoneを渡すこと
    （Architecture Amendment、Protected Operation Manifest）。"""
    return ProtectedFeaturedMediaSideEffectBinding(
        protected_context, media_upload_coordinator, adapters, manifest_registrar,
    )


def build_legacy_featured_media_side_effect_binding(
    legacy_context: "LegacyDirectExecutionContext",
    runtime: "ArticleFeaturedMediaRuntime",
) -> "LegacyFeaturedMediaSideEffectBinding":
    """legacy専用builder。引数は`legacy_context`と、main.py起動時に既に構築
    済みのlegacy runtimeの2つのみ。"""
    return LegacyFeaturedMediaSideEffectBinding(legacy_context, runtime)
