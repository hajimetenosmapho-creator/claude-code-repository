"""
AI Image Generator Contract（Provider非依存、外部I/Oなし）。
"""
from typing import Protocol

from .generated_image import GeneratedImage


class AIImageGenerator(Protocol):
    """
    画像生成を行うProviderが実装すべき最小限のContract。

    typing.Protocolによる構造的型付け（Structural Typing）のみを表現する。
    @runtime_checkableは付与しない（isinstance()検証を目的としたPublic API
    拡張を行わないため）。promptの実行時validationはこのProtocol自体では
    行わない（将来Adapter Foundationの責務）。
    """

    def generate(self, prompt: str) -> GeneratedImage:
        ...
