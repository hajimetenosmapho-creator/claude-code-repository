"""
Retry Queue Status定義（v3.1.0）

RetryQueueStatus: Queue内での1項目のライフサイクル状態を表すEnum

設計方針:
    - WAITING/PROCESSING/CANCELLEDの3値のみが本Releaseの操作（enqueue/dequeue/remove）
      から到達する。
    - COMPLETED/FAILEDは将来拡張用の予約値。実際の再実行結果（RetryOutcome）をQueueへ
      フィードバックする仕組み（Retry Engineとの連携）が必要だが、本Releaseの対象外
      （docs/design/retry_queue_foundation.md 4章）。WorkflowMonitorStatus.CANCELLED/
      WAITINGが判定ロジックから到達しない予約値として定義されている前例
      （docs/design/workflow_monitor_foundation.md 2章）に倣う。
"""
from __future__ import annotations

from enum import Enum


class RetryQueueStatus(Enum):
    WAITING = "waiting"        # enqueue()直後。Queueの中で再実行を待っている
    PROCESSING = "processing"  # dequeue()により取り出された（Queueからは削除済み）
    CANCELLED = "cancelled"    # remove()により取り消された（Queueからは削除済み）
    COMPLETED = "completed"    # 予約値。本Releaseの操作からは到達しない
    FAILED = "failed"          # 予約値。本Releaseの操作からは到達しない
