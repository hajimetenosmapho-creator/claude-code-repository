"""
Retry Alert Evaluator（v6.5.0）

RetryAlertEvaluator: RetryHealthReport（v6.4.0の出力）からRetryAlertを判定する
                      だけの、状態を持たないStateless Pure Functionコンポーネント。

設計方針（docs/design/retry_alert_foundation.md 4.1節・4.3節・7章・9章）:
    - 入力はRetryHealthReportのみ。RetryMetricsSnapshot・Runtime・
      RetryManager・Logger・JSONLのいずれも知らない・importしない
    - 閾値判定は一切行わない。RetryHealthEvaluator（v6.4.0）が既に確定した
      statusを、以下の固定対応表に従ってRetryAlertLevelへ変換するだけの
      単純な写像（マッピング）である（Design Contract）
        HEALTHY   -> NONE
        DEGRADED  -> WARNING
        UNHEALTHY -> CRITICAL
    - 既知の3 Statusのみを明示的かつ網羅的（exhaustive）に分岐させる。dictの
      .get(status, デフォルト値)のような「知らない値は既定値へ丸める」形は
      採らない
    - 未対応のStatus（将来RetryHealthStatusに値が追加された場合）を
      RetryAlertLevel.NONE等へ自動的にフォールバックすることを禁止する。
      未対応のStatusを検知した場合はValueErrorを送出する（Fail Fast契約）。
      これは「対応漏れ」という開発上の契約違反を検知するためのものであり、
      v6.4.0のRetryHealthEvaluatorが「データ不足」という正常な実行時状態に
      対して例外を送出しない設計（v6.4.0設計書9章）とは前提が異なる
    - Stateless Pure Function：同一のRetryHealthReportを渡した場合、常に
      同一のRetryAlert（既知Statusの場合）または同一の例外（未対応Statusの
      場合）を返す
"""
from __future__ import annotations

from retry_monitoring import RetryHealthReport, RetryHealthStatus

from .retry_alert import RetryAlert
from .retry_alert_level import RetryAlertLevel


class RetryAlertEvaluator:
    """RetryHealthReportからRetryAlertを計算するだけの、状態を持たないコンポーネント。"""

    def evaluate(self, report: RetryHealthReport) -> RetryAlert:
        """
        report（RetryHealthReport、唯一の入力）のstatusを、固定対応表に従って
        RetryAlertLevelへ変換し、RetryAlertを返す。

        - HEALTHY / DEGRADED / UNHEALTHY 以外のstatusが渡された場合、
          フォールバックせずValueErrorを送出する（未対応Statusの明示的失敗、
          4.3節 Fail Fast契約）
        """
        status = report.status

        if status is RetryHealthStatus.HEALTHY:
            return RetryAlert(level=RetryAlertLevel.NONE)

        if status is RetryHealthStatus.DEGRADED:
            return RetryAlert(level=RetryAlertLevel.WARNING)

        if status is RetryHealthStatus.UNHEALTHY:
            return RetryAlert(level=RetryAlertLevel.CRITICAL)

        raise ValueError(
            f"RetryAlertEvaluator: 未対応のRetryHealthStatusです（フォールバックしません）: {status!r}"
        )
