"""
Image Generation Fallback Policy Foundation.

Consumer-less Foundation: 画像featured media処理（generate → upload → bind）の
実行時失敗に対し、featured mediaなしで記事投稿を継続してよいか、それとも
呼び出し側が捕捉した元の例外を無変換で再送出すべきかを決定する、
provider中立な分類語彙を公開するpolicyのみを責務とする独立package。
Runtimeへの配線（main.py・image_resolver.py・OutputManager・Pipeline・
Composition Root等）は行わない。
"""
from .image_generation_fallback_policy import (
    ImageGenerationFailureCategory,
    ImageGenerationFallbackAction,
    ImageGenerationFallbackDecision,
    decide_image_generation_fallback,
)

__all__ = [
    "ImageGenerationFailureCategory",
    "ImageGenerationFallbackAction",
    "ImageGenerationFallbackDecision",
    "decide_image_generation_fallback",
]
