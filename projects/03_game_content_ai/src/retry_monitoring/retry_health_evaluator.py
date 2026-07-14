"""
Retry Health Evaluator（v6.4.0）

RetryHealthEvaluator: RetryMetricsSnapshot（v6.3.0の出力）から健全性を判定し、
                       RetryHealthReportを返すだけの、状態を持たない
                       Stateless Pure Functionコンポーネント。

設計方針（docs/design/retry_monitoring_foundation.md 6.5節 Architecture Decision AD-2・
          7章 Responsibility・9章 Failure Policy・10章 DI構成）:
    - 入力はRetryMetricsSnapshotのみ。Runtime・RetryManager・Logger・JSONLの
      いずれも知らない・importしない
    - Thresholdを自ら生成しない。（a）呼び出し元からConstructor Injectionで
      外部から受け取る、または（b）未指定時にRetryHealthThresholds()の
      Default Thresholdを使用する、の2通りのみを許可する
    - Stateless Pure Function：同一のRetryMetricsSnapshotを渡した場合、常に
      同一のRetryHealthReportを返す
    - snapshot.enqueue_success_ratioがNone（対象サイクルが0件等で算出不能）の
      場合、閾値判定を行わず例外も送出せずHEALTHYを返す
    - ファイルI/O・ネットワークI/Oを一切行わないため、fail-fastすべき異常系は
      存在しない
"""
from __future__ import annotations

from retry_metrics import RetryMetricsSnapshot

from .retry_health_report import RetryHealthReport
from .retry_health_status import RetryHealthStatus
from .retry_health_thresholds import RetryHealthThresholds


class RetryHealthEvaluator:
    """RetryMetricsSnapshotからRetryHealthReportを計算するだけの、状態を持たないコンポーネント。"""

    def __init__(self, thresholds: RetryHealthThresholds | None = None):
        self.thresholds = thresholds or RetryHealthThresholds()

    def evaluate(self, snapshot: RetryMetricsSnapshot) -> RetryHealthReport:
        """
        snapshot（RetryMetricsSnapshot、唯一の入力）から健全性を判定し
        RetryHealthReport を返す。

        - snapshot.enqueue_success_ratio が None の場合、閾値判定を行わず
          HEALTHY を返す
        - 例外は送出しない（純粋な判定ロジックであり、判定不能な入力は
          「判定しない」という結果として扱う）
        """
        ratio = snapshot.enqueue_success_ratio

        if ratio is None:
            return RetryHealthReport(status=RetryHealthStatus.HEALTHY)

        if ratio < self.thresholds.unhealthy_below:
            return RetryHealthReport(status=RetryHealthStatus.UNHEALTHY)

        if ratio < self.thresholds.degraded_below:
            return RetryHealthReport(status=RetryHealthStatus.DEGRADED)

        return RetryHealthReport(status=RetryHealthStatus.HEALTHY)
