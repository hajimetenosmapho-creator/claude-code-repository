"""
Write-Ahead-Aware Media Upload Capability（Release 6.32、呼び出し箇所B、15.4.1・22.3.2節）

Source of Truth: docs/design/side_effect_fail_closed_human_review_safety_foundation.md

`GeneratedImageUploadCapability` Protocol（既存のDependency Inversion拡張点、
`article_featured_media_orchestrator.py`）を実装するdecorator。`upload()`の
直前で`media_upload_coordinator.record_attempted()`（IO_ARMED durable ACK、
9.9.4.4節）を確認した後にのみ、真の外部I/Oである`inner.upload()`を呼ぶ。

`record_confirmed()`はこのdecorator自身は一切呼ばない——呼び出し元
（`main.py::_apply_featured_media_step()`、22.3.2節）が唯一のownerである
（15.5.1節）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from ai_image_generation import GeneratedImage
from wordpress_media import MediaUploadResult

if TYPE_CHECKING:
    from article_featured_media_orchestration import GeneratedImageUploadCapability

    from .media_upload_safety_coordinator import MediaUploadSafetyCoordinator
    from .side_effect_operation_identity import SideEffectOperationIdentity


class WriteAheadAwareMediaUploadCapability:
    """
    `inner`（既存の`GeneratedImageWordPressMediaUploader`インスタンス）へ
    委譲する前に、identity-scopedなIO_ARMED durable ACKを確認するdecorator。

    記事1件・呼び出し1回ごとに新規構築する（identityをupload(image, filename)
    というProtocol署名へ渡す経路がないため、22.3.2節）。
    """

    def __init__(
        self,
        inner: "GeneratedImageUploadCapability",
        media_upload_coordinator: "MediaUploadSafetyCoordinator",
        identity: "SideEffectOperationIdentity",
        member_run_id: str,
    ) -> None:
        self._inner = inner
        self._media_upload_coordinator = media_upload_coordinator
        self._identity = identity
        self._member_run_id = member_run_id

    def upload(self, image: GeneratedImage, filename: str) -> MediaUploadResult:
        self._media_upload_coordinator.record_attempted(self._identity, self._member_run_id)
        # IO_ARMED durable ACK確認後にのみ、真の外部I/Oへ進む
        # （9.9.1節のwrite-ahead-before-I/O契約、15.4節）。
        return self._inner.upload(image, filename)
