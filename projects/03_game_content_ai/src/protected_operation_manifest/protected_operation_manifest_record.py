"""
Protected Operation Manifest Record（Release 6.32 Architecture Amendment、Round 9設計）

Source of Truth: docs/design/
side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md 2章

IMMUTABLE EXECUTION/MEMBER GENERATION：永続化キーは
(root_run_id, attempt_ordinal, member_run_id) の3要素。member_run_idは
WorkflowEngineManagerが実行のたびに新規生成する一意なuuid4であるため
（同amendment §2 Round 9確認済み）、同一キーへの2度目の書き込みは正常経路では
構造的に発生し得ない——rebind/overwrite APIは存在しない。
"""
from __future__ import annotations

from dataclasses import dataclass

from side_effect_safety.side_effect_operation_identity import ProtectedSideEffectKind, SideEffectSite


@dataclass(frozen=True)
class ManifestEntry:
    operation_kind: ProtectedSideEffectKind
    effect_site: SideEffectSite
    operation_instance_key: str
    registered_at: str  # ISO8601 UTC


@dataclass(frozen=True)
class ProtectedOperationManifestRecord:
    root_run_id: str
    attempt_ordinal: int
    member_run_id: str
    entries: "tuple[ManifestEntry, ...]"
    contract_version: int
