"""
MediaUploadSafetyCoordinator 例外定義（Release 6.32、9.9.4.6節）
"""
from __future__ import annotations


class MediaUploadSafetyIOError(Exception):
    """filesystem I/O自体の失敗。"""


class MediaUploadSafetyTransitionError(Exception):
    """許可されない遷移・duplicate・cross-store競合。"""


class MediaUploadSafetyContractViolationError(Exception):
    """get()時、矛盾を検出。"""


class MediaUploadSafetyImplementationContractError(Exception):
    """`RecoveryPolicy.build_minimal()`が自分自身の`validate()`に失敗する等、
    到達しないはずの実装契約違反（9.9.4.4節）。"""
