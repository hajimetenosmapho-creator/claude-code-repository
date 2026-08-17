"""
Retry Observability Pipeline（v6.29.0）

RetryObservabilityPipeline: metrics -> monitoring -> alert -> notification ->
                             messageの5段階を、既存の公開Evaluator/Builderの
                             みを用いて固定順序で呼び出すだけの、状態を持たない
                             Orchestration/Facadeコンポーネント。

設計方針（docs/design/retry_observability_pipeline_foundation.md 6章・7章・8章）:
    - Orchestration/Facade層：判定（Judgment）・値構築（Value Building）ロジックは
      一切追加せず、既存5パッケージの呼び出し順序を固定するだけの責務に限定する
      （ArticleFeaturedMediaOrchestrator（v6.14.0）と同型の契約）
    - 唯一の入力はlist[RetryRuntimeLogRecord]（既にパース済みのrecord）。
      RetryRuntimeLogReaderは一切importせず、ファイルI/Oは行わない
    - notification_decision.statusがNOTIFYの場合のみMessageBuilder.build()を
      呼ぶ。NO_NOTIFICATIONの場合は呼ばずmessage=Noneとする。未対応のstatusは
      フォールバックせずValueErrorを送出する（Fail Fast契約）
    - 各Evaluator/Builderが送出する例外はいずれも無変換のまま呼び出し元へ
      伝播する（本コンポーネント自身はtry/exceptを持たない）
    - Runtime・RetryCompositionRoot・Scheduler・CLI・Senderのいずれも知らない・
      importしない（消費者不在の先行実装、Foundation First）
"""
from __future__ import annotations

from retry_alert import RetryAlertEvaluator
from retry_metrics import RetryMetricsCalculator, RetryRuntimeLogRecord
from retry_monitoring import RetryHealthEvaluator, RetryHealthThresholds
from retry_notification import RetryNotificationEvaluator, RetryNotificationStatus
from retry_notification_message import RetryNotificationMessageBuilder

from .retry_observability_report import RetryObservabilityReport


class RetryObservabilityPipeline:
    """metrics -> monitoring -> alert -> notification -> messageを固定順序で呼び出すだけの、状態を持たないコンポーネント。"""

    def __init__(self, thresholds: RetryHealthThresholds | None = None):
        self._metrics_calculator = RetryMetricsCalculator()
        self._health_evaluator = RetryHealthEvaluator(thresholds)
        self._alert_evaluator = RetryAlertEvaluator()
        self._notification_evaluator = RetryNotificationEvaluator()
        self._message_builder = RetryNotificationMessageBuilder()

    def evaluate(self, records: list[RetryRuntimeLogRecord]) -> RetryObservabilityReport:
        """
        records（既にパース済みのRetryRuntimeLogRecordのリスト、唯一の入力）から、
        5段階の既存Evaluator/Builderを固定順序で呼び出し、RetryObservabilityReportを返す。

        - ファイルI/Oは一切行わない（RetryRuntimeLogReaderは使用しない）
        - 各Evaluator/Builderが送出する例外（ValueError等）はいずれも無変換のまま
          呼び出し元へ伝播する
        - notification_decision.statusがNOTIFYの場合のみMessageBuilder.build()を
          呼ぶ。NO_NOTIFICATIONの場合は呼ばずmessage=Noneとする。未対応のstatusは
          フォールバックせずValueErrorを送出する（Fail Fast契約）
        """
        metrics = self._metrics_calculator.calculate(records)
        health_report = self._health_evaluator.evaluate(metrics)
        alert = self._alert_evaluator.evaluate(health_report)
        notification_decision = self._notification_evaluator.evaluate(alert)

        status = notification_decision.status
        if status is RetryNotificationStatus.NOTIFY:
            message = self._message_builder.build(notification_decision)
        elif status is RetryNotificationStatus.NO_NOTIFICATION:
            message = None
        else:
            raise ValueError(
                f"RetryObservabilityPipeline: 未対応のRetryNotificationStatusです"
                f"（フォールバックしません）: {status!r}"
            )

        return RetryObservabilityReport(
            metrics=metrics,
            health_report=health_report,
            alert=alert,
            notification_decision=notification_decision,
            message=message,
        )
