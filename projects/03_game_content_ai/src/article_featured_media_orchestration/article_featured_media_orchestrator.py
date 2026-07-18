"""
Article Featured Media Orchestration Foundation.

既存4 Foundation（AIImageGenerator Protocol・GeneratedImage → Media Upload capability・
bind_featured_media）を、generate → upload → bind という固定順序で呼び出す、
単一責務のstateless Orchestrator。

Consumer-less Foundation: main.py・image_resolver.py・WordPressOutput・OutputManager・
Pipeline・Composition Root・Retry Runtime・scripts関連の既存コードのいずれへも
依存しない。OpenAIImageGenerator・GeneratedImageWordPressMediaUploaderの具象classへも
依存しない（media_uploaderはGeneratedImageUploadCapability Protocol経由のみ）。
"""
from typing import Protocol

from ai_image_generation import AIImageGenerator, GeneratedImage
from article_featured_media import bind_featured_media
from outputs import ArticleData
from wordpress_media import MediaUploadResult


class GeneratedImageUploadCapability(Protocol):
    """
    GeneratedImageをWordPress Media（相当）へアップロードするcapabilityの
    最小Contract。既存generated_image_wordpress_media.GeneratedImageWordPressMediaUploader
    の Public API（upload(image, filename) -> MediaUploadResult）と構造的に適合するが、
    本Orchestratorはその具象classへは依存しない（Dependency Inversion）。
    """

    def upload(self, image: GeneratedImage, filename: str) -> MediaUploadResult:
        ...


class ArticleFeaturedMediaOrchestrator:
    """
    ArticleData・prompt・filenameを受け取り、
    image_generator.generate() → media_uploader.upload() → bind_featured_media()
    という固定順序で呼び出し、featured_media_idが設定された新しいArticleDataを返す。

    image_generator／media_uploaderはConstructor Injectionでのみ受け取り、
    構築時にcapability検証を行う（fail-fast）。apply()はrequest単位のstateを
    インスタンス属性へ保存しない。
    """

    def __init__(
        self,
        image_generator: AIImageGenerator,
        media_uploader: GeneratedImageUploadCapability,
    ) -> None:
        if not callable(getattr(image_generator, "generate", None)):
            raise TypeError("image_generator must provide a callable generate method")

        if not callable(getattr(media_uploader, "upload", None)):
            raise TypeError("media_uploader must provide a callable upload method")

        self._image_generator = image_generator
        self._media_uploader = media_uploader

    def apply(self, article: ArticleData, prompt: str, filename: str) -> ArticleData:
        if not isinstance(article, ArticleData):
            raise ValueError("article must be an ArticleData")

        if not isinstance(prompt, str):
            raise ValueError("prompt must be a str")
        if not prompt.strip():
            raise ValueError("prompt must not be blank")

        if not isinstance(filename, str):
            raise ValueError("filename must be a str")
        if not filename.strip():
            raise ValueError("filename must not be blank")

        generated_image = self._image_generator.generate(prompt)
        media_result = self._media_uploader.upload(generated_image, filename)
        return bind_featured_media(article, media_result)
