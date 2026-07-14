"""
Retry Monitoring パッケージ（v6.4.0）

RetryMetricsSnapshot（v6.3.0 retry_metricsが生成する集計結果）のみを入力として
受け取り、健全性ステータス（RetryHealthReport）を判定するだけの、
Judgment Only Foundationパッケージ。

設計方針（docs/design/retry_monitoring_foundation.md）:
    - Judgment Only Foundation：判定のみを担当し、Runtime・Metrics側へ一切
      フィードバックを行わない（Retry Queueの更新・RetryManagerの変更・
      Runtime Pipeline各コンポーネントの変更・Schedulerへの通知・Retry実行
      可否の判断・通知の送信のいずれも行わない）
    - 唯一の入力はRetryMetricsSnapshot。Runtime・RetryManager・Logger・JSONLの
      いずれも知らない・importしない（retry_metrics以外の他のretry_*
      パッケージへは一切依存しない）
    - RetryHealthThresholds・RetryHealthReportはいずれもImmutable
      （frozen dataclass）。RetryHealthThresholdsはConfigではなくDomain Value
    - RetryHealthEvaluatorはThresholdを生成しない（外部から受け取るか
      Default Thresholdを使用するのみ）。Stateless Pure Functionとして、
      同一のRetryMetricsSnapshotに対し常に同一のRetryHealthReportを返す
    - Release 6.4ではRetryHealthReportはstatusのみを扱う。reason／warnings／
      details（またはviolations）は将来拡張の対象（11.5節）
    - 本Releaseでは消費者不在の先行実装。scripts/エントリーポイント・CLI表示・
      Alert通知は対象外（Foundation First）
"""
from .retry_health_evaluator import RetryHealthEvaluator
from .retry_health_report import RetryHealthReport
from .retry_health_status import RetryHealthStatus
from .retry_health_thresholds import RetryHealthThresholds

__all__ = [
    "RetryHealthStatus",
    "RetryHealthThresholds",
    "RetryHealthReport",
    "RetryHealthEvaluator",
]
