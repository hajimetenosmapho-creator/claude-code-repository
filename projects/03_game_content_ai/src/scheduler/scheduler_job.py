"""
Scheduler Job定義（v2.6.0）

TriggerType: SchedulerJobの起動条件の種類を表すEnum
SchedulerJob: Schedulerが管理するジョブそのものを表すデータモデル

設計方針:
    - Foundation Release（v2.6.0）のため、TriggerTypeはDAILY / INTERVAL / ONCEの
      最小構成のみとする。cron式（分・時・日・月・曜日の5フィールド、範囲指定・
      リスト指定・step等）への対応は対象外（cron完全互換ではない）。
      TriggerType.CRONの追加自体は将来Releaseで拡張可能な設計とする
      （Enumにメンバーを追加するだけで既存メンバーの意味は変えずに拡張できる）
    - trigger_type は文字列ではなくEnumとして設計する（誤字によるバグを防ぐため）
    - schedule は trigger_type ごとに解釈が異なる自由記述の文字列とする
      （解釈は SchedulerEngine 側の責務。フォーマットは下記の通り）
        DAILY:    "HH:MM"                    （例: "09:00"）
        INTERVAL: 分単位の整数を文字列化したもの （例: "30"）
        ONCE:     "YYYY-MM-DDTHH:MM"          （例: "2026-07-10T09:00"）
    - last_run_at・retry回数・persistence関連のフィールドは今回のFoundation
      Releaseでは持たない（将来Releaseの拡張候補。SchedulerJobにフィールドを
      追加する形で後方互換的に拡張できるようにしておく）
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class TriggerType(Enum):
    """SchedulerJobの起動条件の種類。"""

    DAILY = "daily"
    INTERVAL = "interval"
    ONCE = "once"


@dataclass
class SchedulerJob:
    job_id: str
    name: str
    trigger_type: TriggerType
    schedule: str
    enabled: bool = True
    metadata: dict = field(default_factory=dict)
