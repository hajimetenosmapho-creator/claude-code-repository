"""
OpenAI Image Generation Adapter Foundation.

AIImageGenerator Protocol（ai_image_generation, v6.10.0）を構造的に満たす、
OpenAI Images API（gpt-image-2）ベースの最初の具象Provider。
Consumer-less Foundation: WordPress・記事投稿Pipelineへの配線は行わない。
"""
from .openai_image_generator import (
    OpenAIImageGenerationError,
    OpenAIImageGenerationErrorReason,
    OpenAIImageGenerator,
)

__all__ = [
    "OpenAIImageGenerator",
    "OpenAIImageGenerationError",
    "OpenAIImageGenerationErrorReason",
]
