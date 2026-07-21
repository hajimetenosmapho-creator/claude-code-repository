"""
Article Featured Media Composition Root Foundation.

Consumer-less Foundation: Release 6.9.0〜6.17.0の画像系Foundationを
組み立てるComposition Rootのみを責務とする独立package。main.py・
image_resolver.py・OutputManager・Pipeline・Agent・Scheduler・
Retry Runtime・scripts関連の既存コードのいずれへも依存しない。
"""
from .article_featured_media_composition_root import ArticleFeaturedMediaCompositionRoot

__all__ = [
    "ArticleFeaturedMediaCompositionRoot",
]
