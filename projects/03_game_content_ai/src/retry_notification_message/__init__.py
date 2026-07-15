"""
Retry Notification Message パッケージ（v6.7.0）

RetryNotificationDecision（v6.6.0 retry_notificationが生成する通知要否判定結果）
のみを入力として受け取り、送信可能な固定Message Value Object
（RetryNotificationMessage）を構築するだけの、Value Building Only Foundation
パッケージ。

設計方針（docs/design/retry_notification_message_foundation.md）:
    - Value Building Only Foundation：判定（Judgment）は一切行わず、Runtime・
      Metrics・Monitoring・Alert・Notification側へ一切フィードバックを行わない
    - 唯一の入力はRetryNotificationDecision。RetryAlert・RetryAlertLevel・
      RetryHealthReport・RetryMetricsSnapshot・Runtime・Logger・JSONLの
      いずれも知らない・importしない（retry_notification以外の他のretry_*
      パッケージへは一切依存しない）
    - RetryNotificationMessageはImmutable（frozen dataclass）。bodyのみを
      保持する
    - RetryNotificationMessageBuilderは判定を行わない。RetryNotificationStatus
      からRetryNotificationMessageへの固定対応表に従って変換するだけの
      Stateless Value Buildingコンポーネントである
    - RetryNotificationStatus.NO_NOTIFICATIONをbuild()へ渡すことは契約違反
      であり、フォールバックせずValueErrorを送出する（Fail Fast契約）
    - RetryAlertLevel.WARNING／CRITICALはいずれもNOTIFYへ収束するため区別
      せず、共通の固定Messageを返す
    - 実際の通知送信（Slack／メール等）・チャネル選択は本パッケージの責務外。
      本Releaseでは消費者不在の先行実装（Foundation First）
"""
from .retry_notification_message import RetryNotificationMessage
from .retry_notification_message_builder import RetryNotificationMessageBuilder

__all__ = [
    "RetryNotificationMessage",
    "RetryNotificationMessageBuilder",
]
