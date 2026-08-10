"""
Article Featured Media Runtime Foundation.

Source of Truth:
    docs/design/article_featured_media_runtime_wiring.md
    （Architecture Review 2：Approved with Suggestions／Architecture Amendment 2）

Release 6.9.0〜6.19.0で整備された画像系Foundationを、main.pyが唯一参照する
単一のFacadeとして公開する。main.pyへの実接続（配線）はDI-4 Runtime Wiring
（v6.21.0）の責務であり、本Releaseはconsumer-lessである。
"""
from .article_featured_media_runtime import (
    ArticleFeaturedMediaRuntime,
    ArticleFeaturedMediaRuntimeResult,
    ArticleFeaturedMediaRuntimeStatus,
    FeaturedMediaFailureObservation,
)

__all__ = [
    "ArticleFeaturedMediaRuntimeStatus",
    "ArticleFeaturedMediaRuntimeResult",
    "ArticleFeaturedMediaRuntime",
    "FeaturedMediaFailureObservation",
]
