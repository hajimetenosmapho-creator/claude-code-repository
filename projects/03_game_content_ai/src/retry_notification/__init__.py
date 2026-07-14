"""
Retry Notification パッケージ（v6.6.0）

RetryAlert（v6.5.0 retry_alertが生成するアラート判定結果）のみを入力として
受け取り、通知要否（RetryNotificationDecision）を判定するだけの、
Judgment Only Foundationパッケージ。

設計方針（docs/design/retry_notification_foundation.md）:
    - Judgment Only Foundation：判定のみを担当し、Runtime・Metrics・
      Monitoring・Alert側へ一切フィードバックを行わない
    - 唯一の入力はRetryAlert。RetryHealthReport・RetryMetricsSnapshot・
      Runtime・RetryManager・Logger・JSONLのいずれも知らない・importしない
      （retry_alert以外の他のretry_*パッケージへは一切依存しない）
    - RetryNotificationDecisionはImmutable（frozen dataclass）。statusのみを
      保持する。RetryAlert・RetryAlertLevelは保持・複製しない
    - RetryNotificationEvaluatorは閾値判定を行わない。RetryAlertLevelから
      RetryNotificationStatusへの固定対応表に従って変換するだけの
      Stateless Pure Functionである
    - RetryNotificationStatus.NO_NOTIFICATIONは「評価は正常完了・入力された
      RetryAlertが通知対象となる状態ではない」を表す正常系の明示値である。
      未対応のRetryAlertLevelはNO_NOTIFICATION等へフォールバックせず
      ValueErrorを送出する（Fail Fast契約）
    - 実際の通知送信（Slack／メール等）は本パッケージの責務外。本Releaseでは
      消費者不在の先行実装（Foundation First）
"""
from .retry_notification_decision import RetryNotificationDecision
from .retry_notification_evaluator import RetryNotificationEvaluator
from .retry_notification_status import RetryNotificationStatus

__all__ = [
    "RetryNotificationStatus",
    "RetryNotificationDecision",
    "RetryNotificationEvaluator",
]
