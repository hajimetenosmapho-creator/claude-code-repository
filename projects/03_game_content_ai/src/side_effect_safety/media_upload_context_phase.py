"""
MediaUploadContextPhase：2-phase design（Release 6.32、9.9.2節）
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .side_effect_operation_identity import SideEffectOperationIdentity


class MediaUploadContextPhase(Enum):
    """PREPARED→IO_ARMEDの一方向のみを許可する（9.9.2節）。逆方向・resetは
    APIとして一切提供しない。"""

    PREPARED = "prepared"
    IO_ARMED = "io_armed"


@dataclass(frozen=True)
class MediaUploadAttemptContextRecord:
    identity: SideEffectOperationIdentity
    member_run_id: str
    phase: MediaUploadContextPhase
    updated_at: str
