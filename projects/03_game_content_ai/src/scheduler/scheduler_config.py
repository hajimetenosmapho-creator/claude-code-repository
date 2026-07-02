"""
Scheduler設定（v2.6.0）

SchedulerConfig: Scheduler全体の基本設定を保持するデータクラス

設計方針:
    - Configuration First: 既存Agent群（AgentConfig等）と同じく、
      SCHEDULER_ENABLED（デフォルトfalse）で有効・無効を切り替える
    - Foundation Releaseのため保持する設定値は最小限（enabled のみ）とする。
      将来Release（retry回数、persistence先パス、Windows Task Scheduler /
      Linux cron連携時の設定等）はこのdataclassにフィールドを追加する形で
      拡張する想定とし、既存フィールドの意味は変えない

環境変数:
    SCHEDULER_ENABLED  (default: false)
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class SchedulerConfig:
    enabled: bool

    @classmethod
    def from_env(cls) -> "SchedulerConfig":
        """環境変数からSchedulerConfigを構築する。"""
        enabled = os.environ.get("SCHEDULER_ENABLED", "false").lower() == "true"
        return cls(enabled=enabled)

    def is_ready(self) -> bool:
        """Schedulerが利用可能な状態か返す。"""
        return self.enabled
