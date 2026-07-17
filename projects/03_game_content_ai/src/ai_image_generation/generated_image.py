"""
AI Image Generation Contract Foundationの生成結果を表す値オブジェクト。
"""
import re
from dataclasses import dataclass, field

_MIME_TYPE_PATTERN = re.compile(r"^image/[A-Za-z0-9][A-Za-z0-9._+-]*$")


@dataclass(frozen=True)
class GeneratedImage:
    """
    AIImageGenerator.generate() の戻り値。

    Attributes:
        image_bytes: 生成された画像の生バイナリ。repr()には含まれない
                     （field(repr=False)、Security Contract）。
        mime_type:   canonical MIME type（例: "image/png"）。個別形式の
                     許可リストはなく、canonical正規表現を満たす未知の
                     subtypeも許可する。
    """

    image_bytes: bytes = field(repr=False)
    mime_type: str

    def __post_init__(self) -> None:
        if type(self.image_bytes) is not bytes:
            raise ValueError("image_bytes must be bytes")
        if len(self.image_bytes) == 0:
            raise ValueError("image_bytes must not be empty")

        if not isinstance(self.mime_type, str):
            raise ValueError("mime_type must be str")
        if not _MIME_TYPE_PATTERN.fullmatch(self.mime_type):
            raise ValueError(
                "mime_type must match canonical image MIME type syntax (image/<subtype>)"
            )
