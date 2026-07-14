"""
Retry Health Status（v6.4.0）

RetryHealthStatus: RetryHealthEvaluatorが判定する健全性ステータスを表すEnum。

設計方針（docs/design/retry_monitoring_foundation.md 6.3節）:
    - HEALTHY / DEGRADED / UNHEALTHY の3値のみを持つ
"""
from __future__ import annotations

from enum import Enum


class RetryHealthStatus(Enum):
    """RetryHealthEvaluatorが判定する健全性ステータス。"""

    HEALTHY = "HEALTHY"
    DEGRADED = "DEGRADED"
    UNHEALTHY = "UNHEALTHY"
