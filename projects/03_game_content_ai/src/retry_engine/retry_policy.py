"""
Retry Policy定義（v3.0.0）

RetryPolicy: 再実行対象の状態と最大試行回数を保持する、env非依存の業務ルール

設計方針:
    - target_statuses は Charter の要求（「FAILED または TIMEOUT となった場合に再実行」）に
      従い固定値とし、環境変数では変更不可とする。ステータスごとに異なる再試行方針を
      持たせることは Failure Classification（対象外）に該当するため、本Releaseでは行わない
      （docs/design/retry_engine_foundation.md 6章）。
    - max_attempts のみ RETRY_MAX_ATTEMPTS（デフォルト3）で調整可能とする。
    - WorkflowMonitorStatus は必ずEnumのまま比較する（文字列比較は行わない）。
    - RetryManager は本クラスを「should_retry(monitor_status, attempt) -> bool という
      1メソッドを持つオブジェクト」としてのみ利用する。将来 Strategy Pattern
      （FixedRetryPolicy / ExponentialBackoffPolicy / AdaptiveRetryPolicy 等）へ
      拡張できる構造を保つが、本Foundationでは固定Retry Policyのみを実装する
      （同設計書10章 Design Decision #11）。

環境変数:
    RETRY_MAX_ATTEMPTS  (default: 3)
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from workflow_monitor import WorkflowMonitorStatus

DEFAULT_TARGET_STATUSES: frozenset[WorkflowMonitorStatus] = frozenset(
    {WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT}
)


@dataclass(frozen=True)
class RetryPolicy:
    target_statuses: frozenset[WorkflowMonitorStatus]
    max_attempts: int

    @classmethod
    def from_env(cls) -> "RetryPolicy":
        """環境変数から RetryPolicy を構築する。target_statuses は固定値。"""
        max_attempts = int(os.environ.get("RETRY_MAX_ATTEMPTS", "3"))
        return cls(target_statuses=DEFAULT_TARGET_STATUSES, max_attempts=max_attempts)

    def should_retry(self, monitor_status: WorkflowMonitorStatus, attempt: int) -> bool:
        """monitor_status が再実行対象で、かつ attempt が上限未満であれば True を返す。"""
        return monitor_status in self.target_statuses and attempt < self.max_attempts
