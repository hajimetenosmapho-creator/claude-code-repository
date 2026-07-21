"""
Article Featured Media Composition Root Foundation.

Source of Truth:
    docs/design/article_featured_media_composition_root_foundation.md
    （Architecture Review 2：Approved with Suggestions）

責務（設計書9章）:
    configuration評価・credential解決・adapter構築・adapter間の接続・
    orchestrator構築・利用可能状態の公開の6点に限定する。
    画像workflowの実行（apply()の呼び出し）・promptの実生成・filenameの実生成・
    失敗時の継続／中止判断（Fallback Policy）・Runtimeへの配線はいずれも
    本Releaseの責務外である（設計書5章 N-1〜N-16）。

Consumer-less Foundation: main.py・image_resolver.py・OutputManager・
Pipeline・Agent・Scheduler・Retry Runtime・scripts関連の既存コードの
いずれからも参照されない。generated_image_filename_policy（v6.16）・
article_image_prompt_construction（v6.17）はComposition Root自身が
構築すべき状態を持たないため、本パッケージからは一切importしない
（設計書10.3節）。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from article_featured_media_orchestration import ArticleFeaturedMediaOrchestrator
from generated_image_wordpress_media import GeneratedImageWordPressMediaUploader
from image_generation_config import ImageGenerationConfig
from openai_image_generation import OpenAIImageGenerator
from wordpress_media import WordPressMediaUploader


@dataclass(frozen=True)
class ArticleFeaturedMediaCompositionRoot:
    """
    Release 6.9.0〜6.17.0の画像系Foundationを、Runtimeから独立した単一境界で
    構築・接続するComposition Root。

    orchestratorはfield(repr=False)を付与し、repr()／str()から除外する
    （secret-bearing dependencyを間接保持するため。設計書17.3節）。
    dataclasses.asdict()はこの除外の対象外であり、secret-safeな
    serialization手段ではない（設計書17.2節 S-11）。

    Attributes:
        orchestrator: 構築済みのArticleFeaturedMediaOrchestrator。
            Gate OFF時はNone。
        image_mime_type: 構築済みgeneratorが生成する予定のcanonical MIME type。
            Gate OFF時はNone。
    """

    orchestrator: ArticleFeaturedMediaOrchestrator | None = field(repr=False)
    image_mime_type: str | None

    def __post_init__(self) -> None:
        if (self.orchestrator is None) != (self.image_mime_type is None):
            raise ValueError(
                "orchestrator and image_mime_type must be both set or both None"
            )

        if self.orchestrator is not None:
            if not callable(getattr(self.orchestrator, "apply", None)):
                raise TypeError(
                    "orchestrator must provide a callable apply method"
                )

        if self.image_mime_type is not None:
            if not isinstance(self.image_mime_type, str):
                raise ValueError("image_mime_type must be a str")
            if not self.image_mime_type.strip():
                raise ValueError("image_mime_type must not be blank")

    @classmethod
    def from_env(cls) -> "ArticleFeaturedMediaCompositionRoot":
        """
        環境変数からConfiguration・credentialを読み込み、Composition Rootを構築する。

        Gate（AI_IMAGE_GENERATION_ENABLED）がOFFの場合、以降の環境変数を一切読まず、
        credentialを要求せず、adapterを構築しない（正常な無効状態、設計書13.2節）。

        Gate ON時にcredential不足・値不正がある場合、既存factory
        （OpenAIImageGenerator.from_env() / WordPressMediaUploader.from_env()）が
        送出するValueErrorを無変換で伝播する（Fail Fast、設計書13.3節）。
        """
        config = ImageGenerationConfig.from_env()
        if not config.enabled:
            return cls(orchestrator=None, image_mime_type=None)

        image_generator = OpenAIImageGenerator.from_env()
        image_mime_type = image_generator.output_mime_type

        wordpress_media_uploader = WordPressMediaUploader.from_env()
        generated_image_upload_capability = GeneratedImageWordPressMediaUploader(
            wordpress_media_uploader
        )

        orchestrator = ArticleFeaturedMediaOrchestrator(
            image_generator=image_generator,
            media_uploader=generated_image_upload_capability,
        )

        return cls(orchestrator=orchestrator, image_mime_type=image_mime_type)

    def is_available(self) -> bool:
        """画像featured media処理を実行してよいかを返す。例外を送出しない。"""
        return self.orchestrator is not None
