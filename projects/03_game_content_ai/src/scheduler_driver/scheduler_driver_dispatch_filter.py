"""
Scheduler Driver Dispatch Filter（v6.34.0、Release 6.34）

Design Decision J：Retry-candidate SchedulerEvent除外契約
（docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md 16章）

_select_dispatchable_events(): SchedulerEngine.evaluate()の戻り値のうち、以下の
    2層のAND条件をいずれも満たすイベントのみを残す：
      1. 一次機構（provenance-based）：event.metadataに"retry_candidate"キーが
         含まれていないこと。SchedulerEngine自身の_build_retry_events()が
         retry候補eventへ無条件に設定する構造的マーカーであり、job_idの
         命名規則（prefix等）とは独立した、値に依存しない判定である。
      2. 二次機構（allowlist、defense-in-depth）：event.job_idが
         production_job_ids（ProductionScheduleSource.jobs()由来）に
         含まれること。

RESERVED_RETRY_CANDIDATE_METADATA_KEY: ProductionScheduleSourceが登録するJob定義の
    metadataに含めてはならない予約キー（一次機構が依拠するキーと同一）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from scheduler import SchedulerEvent

RESERVED_RETRY_CANDIDATE_METADATA_KEY = "retry_candidate"


def _is_dispatchable(event: "SchedulerEvent", production_job_ids: frozenset[str]) -> bool:
    if RESERVED_RETRY_CANDIDATE_METADATA_KEY in event.metadata:
        return False
    return event.job_id in production_job_ids


def _select_dispatchable_events(
    events: list["SchedulerEvent"], production_job_ids: frozenset[str],
) -> list["SchedulerEvent"]:
    return [e for e in events if _is_dispatchable(e, production_job_ids)]
