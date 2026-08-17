"""
Retry Observability Report（v6.29.0）

RetryObservabilityReport: RetryObservabilityPipeline.evaluate()の結果を表す、
                           Immutable（読み取り専用）な値オブジェクト。

設計方針（docs/design/retry_observability_pipeline_foundation.md 6章・8章）:
    - frozen=Trueのdataclassとして実装し、フィールドの再代入自体を構造的に
      禁止する（生成後は変更しない）
    - metrics / health_report / alert / notification_decision / message の
      5フィールドのみを保持する
    - __post_init__でstatus/message invariantを強制する：
        NOTIFY          -> messageはNoneであってはならない
        NO_NOTIFICATION -> messageはNoneでなければならない
        未対応のstatus  -> フォールバックせずValueError
      これはevaluate()経由の通常構築だけでなく、Reportが独立して直接構築
      される場合（テストコード等）にもInvariantを保護するためのものである
"""
from __future__ import annotations

from dataclasses import dataclass

from retry_alert import RetryAlert
from retry_metrics import RetryMetricsSnapshot
from retry_monitoring import RetryHealthReport
from retry_notification import RetryNotificationDecision, RetryNotificationStatus
from retry_notification_message import RetryNotificationMessage


@dataclass(frozen=True)
class RetryObservabilityReport:
    """RetryObservabilityPipeline.evaluate()の結果を表すImmutableな値オブジェクト。"""

    metrics: RetryMetricsSnapshot
    health_report: RetryHealthReport
    alert: RetryAlert
    notification_decision: RetryNotificationDecision
    message: RetryNotificationMessage | None

    def __post_init__(self) -> None:
        status = self.notification_decision.status

        if status is RetryNotificationStatus.NOTIFY:
            if self.message is None:
                raise ValueError(
                    "RetryObservabilityReport: "
                    "status=NOTIFYの場合、messageはNoneであってはならない"
                )
            return

        if status is RetryNotificationStatus.NO_NOTIFICATION:
            if self.message is not None:
                raise ValueError(
                    "RetryObservabilityReport: "
                    "status=NO_NOTIFICATIONの場合、messageはNoneでなければならない"
                )
            return

        raise ValueError(
            f"RetryObservabilityReport: 未対応のRetryNotificationStatusです"
            f"（フォールバックしません）: {status!r}"
        )
