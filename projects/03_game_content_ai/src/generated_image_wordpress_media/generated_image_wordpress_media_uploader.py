"""
Generated Image WordPress Media Upload Wiring Foundation.

GeneratedImage（ai_image_generation, v6.10.0）を WordPressMediaUploader.upload()
（wordpress_media, v6.9.0）へ橋渡しする、単一責務のWiring層。

Consumer-less Foundation: 画像生成（prompt → GeneratedImage）を行わず、
openai_image_generation・image_resolver・outputs・Pipeline・Workflow・
Scheduler・Retry Runtimeのいずれへも依存しない。
"""
from ai_image_generation import GeneratedImage
from wordpress_media import MediaUploadResult, WordPressMediaUploader


class GeneratedImageWordPressMediaUploader:
    """
    GeneratedImageを受け取り、WordPressMediaUploader.upload()へ委譲する薄いWiring層。

    media_uploaderはConstructor Injectionでのみ受け取り、isinstance()による
    nominal型検証は行わない（Duck Typing）。upload capabilityの検証は
    upload()呼び出し時まで遅延させる。
    """

    def __init__(self, media_uploader: WordPressMediaUploader) -> None:
        self._media_uploader = media_uploader

    def upload(self, image: GeneratedImage, filename: str) -> MediaUploadResult:
        if not isinstance(image, GeneratedImage):
            raise ValueError("image must be a GeneratedImage")

        upload_method = getattr(self._media_uploader, "upload", None)
        if not callable(upload_method):
            raise TypeError(
                "media_uploader must provide a callable upload method"
            )

        return upload_method(
            image_bytes=image.image_bytes,
            filename=filename,
            mime_type=image.mime_type,
        )
