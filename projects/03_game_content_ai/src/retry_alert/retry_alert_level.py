"""
Retry Alert Level（v6.5.0）

RetryAlertLevel: RetryAlertEvaluatorが判定するアラートの度合いを表すEnum。

設計方針（docs/design/retry_alert_foundation.md 4.1節）:
    - NONE / WARNING / CRITICAL の3値のみを持つ
    - RetryHealthStatus（HEALTHY/DEGRADED/UNHEALTHY）とは別の語彙として定義する。
      Monitoring側の語彙（健全性の状態）とAlert側の語彙（知らせるべき度合い）を
      型として分離しておくことで、将来Alert側だけの都合（例：同じDEGRADEDでも
      状況によってWARNINGとCRITICALを分けたい等）で拡張する余地を残す
"""
from __future__ import annotations

from enum import Enum


class RetryAlertLevel(Enum):
    """RetryAlertEvaluatorが判定するアラートの度合い。"""

    NONE = "NONE"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"
