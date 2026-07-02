"""
Retry設定（v3.0.0）

RetryConfig: Retry Engine全体のFeature Gateのみを保持するデータクラス

設計方針:
    - デフォルトは enabled=False。Retry Engine は Execution History / Workflow Monitor
      （読み取り専用、デフォルト有効）と異なり、実際に Workflow を再実行する
      （News収集・WordPress下書き投稿などの外部副作用を再度発生させうる）ため、
      AI_AGENT_ENABLED / WORKFLOW_ENGINE_ENABLED と同じ「安全側で止める」原則を適用する
      （docs/design/retry_engine_foundation.md 10章 Design Decision #2）。
      結果として実質的に
      AI_AGENT_ENABLED × WORKFLOW_ENGINE_ENABLED × RETRY_ENGINE_ENABLED の三重ゲートになる。
    - 「何を再実行対象とするか」（対象ステータス・最大試行回数）は RetryPolicy の責務であり、
      本Configは持たない。

環境変数:
    RETRY_ENGINE_ENABLED  (default: false)
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass
class RetryConfig:
    enabled: bool

    @classmethod
    def from_env(cls) -> "RetryConfig":
        """環境変数から RetryConfig を構築する。"""
        enabled = os.environ.get("RETRY_ENGINE_ENABLED", "false").lower() == "true"
        return cls(enabled=enabled)

    def is_ready(self) -> bool:
        """Retry Engine全体のゲートが開いているか返す。"""
        return self.enabled
