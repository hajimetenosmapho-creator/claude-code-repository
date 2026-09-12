"""
Protected Operation Manifest パッケージ（Release 6.32 Architecture Amendment）

Source of Truth: docs/design/
side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md

IMMUTABLE EXECUTION/MEMBER GENERATION（Round 9設計）：呼び出し箇所A/B/Cが、
自分自身の既存write-ahead呼び出しよりもさらに前に、このManifestへ自分自身の
identityをdurable登録する。terminalization/reconciliationは、このManifestを
「このexecution試行で何を確認すべきか」の一次情報源として使う。
"""
from __future__ import annotations

from .errors import (
    ProtectedOperationManifestContractViolationError,
    ProtectedOperationManifestError,
    ProtectedOperationManifestIOError,
    ProtectedOperationManifestNotFoundError,
    ProtectedOperationManifestReadError,
)
from .protected_operation_manifest_facades import ManifestReaderFacade, ManifestRegistrarFacade
from .protected_operation_manifest_record import ManifestEntry, ProtectedOperationManifestRecord
from .protected_operation_manifest_store import (
    JsonProtectedOperationManifestStore,
    ProtectedOperationManifestStore,
    RegisterResult,
    build_manifest_entry,
    raise_if_not_registered,
)
from .protected_operation_manifest_store_lock import (
    ProtectedOperationManifestStoreLock,
    ProtectedOperationManifestStoreLockError,
    build_protected_operation_manifest_store_lock,
)

__all__ = [
    "ProtectedOperationManifestError",
    "ProtectedOperationManifestReadError",
    "ProtectedOperationManifestNotFoundError",
    "ProtectedOperationManifestContractViolationError",
    "ProtectedOperationManifestIOError",
    "ManifestEntry",
    "ProtectedOperationManifestRecord",
    "ProtectedOperationManifestStore",
    "JsonProtectedOperationManifestStore",
    "RegisterResult",
    "build_manifest_entry",
    "raise_if_not_registered",
    "ProtectedOperationManifestStoreLock",
    "ProtectedOperationManifestStoreLockError",
    "build_protected_operation_manifest_store_lock",
    "ManifestReaderFacade",
    "ManifestRegistrarFacade",
]
