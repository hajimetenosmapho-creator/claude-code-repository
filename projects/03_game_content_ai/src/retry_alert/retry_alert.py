"""
Retry Alert（v6.5.0）

RetryAlert: RetryAlertEvaluatorの判定結果を表す、Immutable（読み取り専用）な
            値オブジェクト（Alert Domain Object）。

設計方針（docs/design/retry_alert_foundation.md 4.2節）:
    - frozen=Trueのdataclassとして実装し、フィールドの再代入自体を構造的に
      禁止する（生成後は変更しない）
    - 自分自身を更新する手段（setter・update()メソッド等）を一切持たない。
      新しい判定結果が必要な場合はRetryAlertEvaluator.evaluate()を
      再度呼び出し、新しいインスタンスを生成する
    - Release 6.5ではlevelのみを扱う（Foundation First）。message
      （通知文面）／triggered_at（判定時刻）／source_report（元になった
      RetryHealthReportへの参照）等は将来拡張の対象とし、本Releaseでは
      追加実装しない
    - level == RetryAlertLevel.NONEは「健康状態の評価は正常に完了したが、
      通知対象となるAlertは存在しない」ことを表す正常系の明示値である。
      評価失敗・データ不足・不明な状態・処理スキップのいずれも意味しない。
      将来のNotification実装は、level == NONEの場合に通知を送信しては
      ならない（Notification Foundation側が遵守すべき呼び出し契約）
"""
from __future__ import annotations

from dataclasses import dataclass

from .retry_alert_level import RetryAlertLevel


@dataclass(frozen=True)
class RetryAlert:
    """RetryAlertEvaluatorの判定結果を表すImmutableな値オブジェクト（Alert Domain Object）。"""

    level: RetryAlertLevel
