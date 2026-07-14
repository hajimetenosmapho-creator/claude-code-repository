"""
Retry Alert パッケージ（v6.5.0）

RetryHealthReport（v6.4.0 retry_monitoringが生成する健全性判定結果）のみを
入力として受け取り、アラートの度合い（RetryAlert）を判定するだけの、
Judgment Only Foundationパッケージ。

設計方針（docs/design/retry_alert_foundation.md）:
    - Judgment Only Foundation：判定のみを担当し、Runtime・Metrics・
      Monitoring側へ一切フィードバックを行わない
    - 唯一の入力はRetryHealthReport。RetryMetricsSnapshot・Runtime・
      RetryManager・Logger・JSONLのいずれも知らない・importしない
      （retry_monitoring以外の他のretry_*パッケージへは一切依存しない）
    - RetryAlertはImmutable（frozen dataclass）。levelのみを保持する
    - RetryAlertEvaluatorは閾値判定を行わない。RetryHealthStatusから
      RetryAlertLevelへの固定対応表（4.1節）に従って変換するだけの
      Stateless Pure Functionである
    - RetryAlertLevel.NONEは「評価は正常完了・通知対象なし」を表す正常系の
      明示値である。未対応のRetryHealthStatusはNONE等へフォールバックせず
      ValueErrorを送出する（4.3節、Fail Fast契約）
    - Notification（Slack／メール等への実際の通知）は本パッケージの責務外。
      本Releaseでは消費者不在の先行実装（Foundation First）
"""
from .retry_alert import RetryAlert
from .retry_alert_evaluator import RetryAlertEvaluator
from .retry_alert_level import RetryAlertLevel

__all__ = [
    "RetryAlertLevel",
    "RetryAlert",
    "RetryAlertEvaluator",
]
