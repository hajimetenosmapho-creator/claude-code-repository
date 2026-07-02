"""
Retry Queue Config定義（v3.1.0）

RetryQueueConfig: Retry Queue全体のFeature Gate・容量上限・既定優先度を保持するデータクラス

設計方針:
    - RETRY_QUEUE_ENABLEDのデフォルトは true。RETRY_ENGINE_ENABLED（デフォルトfalse）とは
      異なる判断であり、Retry Queueの操作（enqueue/dequeue/remove/list/exists/count）は
      いずれもプロセス内メモリ上のdictを読み書きするだけで、外部副作用（Workflowの
      再実行等）を一切伴わないため。この性質はEXECUTION_HISTORY_ENABLED/
      WORKFLOW_MONITOR_ENABLED（いずれもデフォルトtrue、読み取り中心）と同じ分類に属する
      （docs/design/retry_queue_foundation.md 9章）。
    - max_queue_size/default_priorityが不正な文字列の場合、from_env()内のint()が
      そのままValueErrorを送出する（RetryPolicy.from_env()のRETRY_MAX_ATTEMPTSと同じ扱い。
      起動時設定ミスは早期に落として気付けるようにする方針。同設計書10章）。

環境変数:
    RETRY_QUEUE_ENABLED           (default: true)
    RETRY_QUEUE_MAX_SIZE          (default: 100)
    RETRY_QUEUE_DEFAULT_PRIORITY  (default: 0)
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class RetryQueueConfig:
    enabled: bool
    max_queue_size: int
    default_priority: int

    @classmethod
    def from_env(cls) -> "RetryQueueConfig":
        """環境変数から RetryQueueConfig を構築する。"""
        enabled = os.environ.get("RETRY_QUEUE_ENABLED", "true").lower() == "true"
        max_queue_size = int(os.environ.get("RETRY_QUEUE_MAX_SIZE", "100"))
        default_priority = int(os.environ.get("RETRY_QUEUE_DEFAULT_PRIORITY", "0"))
        return cls(enabled=enabled, max_queue_size=max_queue_size, default_priority=default_priority)

    def is_ready(self) -> bool:
        """Retry Queue全体のゲートが開いているか返す。"""
        return self.enabled
