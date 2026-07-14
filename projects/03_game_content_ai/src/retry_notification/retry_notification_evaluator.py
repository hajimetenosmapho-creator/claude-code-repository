"""
Retry Notification Evaluator（v6.6.0）

RetryNotificationEvaluator: RetryAlert（v6.5.0の出力）からRetryNotification
                             Decisionを判定するだけの、状態を持たない
                             Stateless Pure Functionコンポーネント。

設計方針（docs/design/retry_notification_foundation.md 10章・11章・12章）:
    - 入力はRetryAlertのみ。RetryHealthReport・RetryMetricsSnapshot・
      Runtime・RetryManager・Logger・JSONLのいずれも知らない・importしない
    - 閾値判定は一切行わない。RetryAlertEvaluator（v6.5.0）が既に確定した
      levelを、以下の固定対応表に従ってRetryNotificationStatusへ変換するだけの
      単純な写像（マッピング）である
        NONE     -> NO_NOTIFICATION
        WARNING  -> NOTIFY
        CRITICAL -> NOTIFY
    - 既知の3 Levelのみを明示的かつ網羅的（exhaustive）に分岐させる。dictの
      .get(level, デフォルト値)のような「知らない値は既定値へ丸める」形は
      採らない
    - 未対応のLevel（将来RetryAlertLevelに値が追加された場合）を
      NO_NOTIFICATION・NOTIFYのいずれへも自動的にフォールバックすることを
      禁止する。未対応のLevelを検知した場合はValueErrorを送出する
      （Fail Fast契約）
    - Stateless Pure Function：同一のRetryAlertを渡した場合、常に同一の
      RetryNotificationDecision（既知Levelの場合）または同一の例外
      （未対応Levelの場合）を返す
"""
from __future__ import annotations

from retry_alert import RetryAlert, RetryAlertLevel

from .retry_notification_decision import RetryNotificationDecision
from .retry_notification_status import RetryNotificationStatus


class RetryNotificationEvaluator:
    """RetryAlertからRetryNotificationDecisionを計算するだけの、状態を持たないコンポーネント。"""

    def evaluate(self, alert: RetryAlert) -> RetryNotificationDecision:
        """
        alert（RetryAlert、唯一の入力）のlevelを、固定対応表に従って
        RetryNotificationStatusへ変換し、RetryNotificationDecisionを返す。

        - NONE / WARNING / CRITICAL 以外のlevelが渡された場合、
          フォールバックせずValueErrorを送出する（未対応Levelの明示的失敗、
          Fail Fast契約）
        """
        level = alert.level

        if level is RetryAlertLevel.NONE:
            return RetryNotificationDecision(status=RetryNotificationStatus.NO_NOTIFICATION)

        if level is RetryAlertLevel.WARNING:
            return RetryNotificationDecision(status=RetryNotificationStatus.NOTIFY)

        if level is RetryAlertLevel.CRITICAL:
            return RetryNotificationDecision(status=RetryNotificationStatus.NOTIFY)

        raise ValueError(
            f"RetryNotificationEvaluator: 未対応のRetryAlertLevelです"
            f"（フォールバックしません）: {level!r}"
        )
