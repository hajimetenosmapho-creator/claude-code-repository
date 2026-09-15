"""
Scheduler Driver Event Identity（v6.34.0、Release 6.34）

build_event_identity(): stable event identity（(job_id, occurrence_minute)の組）を
                         SchedulerEvent.execute_time から導出する

設計方針（docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md 7章）:
    - occurrence_minute は execute_time を "%Y-%m-%dT%H:%M" 形式（分単位切り捨て）で
      文字列化した値。SchedulerEngine._match_daily()/_match_interval()/_match_once()
      はいずれも分単位マッチングのみで判定しており秒・マイクロ秒は使わないため、
      同一分内の複数tickは同じevent_identityへ正規化される（duplicate suppression
      の前提）。
    - event_identity = f"{job_id}::{occurrence_minute}"。
    - naive datetime（タイムゾーン・DST非対応）の既知の限界を継承する
      （SchedulerEngine自体が既にこの限界を持つため、本Releaseで新規に持ち込む
      ものではない。7章 Minor開示参照）。
"""
from __future__ import annotations

from datetime import datetime

OCCURRENCE_MINUTE_FORMAT = "%Y-%m-%dT%H:%M"


def build_occurrence_minute(execute_time: datetime) -> str:
    return execute_time.strftime(OCCURRENCE_MINUTE_FORMAT)


def build_event_identity(job_id: str, execute_time: datetime) -> tuple[str, str]:
    """(event_identity, occurrence_minute) のタプルを返す。"""
    occurrence_minute = build_occurrence_minute(execute_time)
    event_identity = f"{job_id}::{occurrence_minute}"
    return event_identity, occurrence_minute
