"""
Retry Health Report（v6.4.0）

RetryHealthReport: RetryHealthEvaluatorの判定結果を表す、Immutable
                    （読み取り専用）な値オブジェクト。

設計方針（docs/design/retry_monitoring_foundation.md 6.3節・6.4節・11.5節）:
    - frozen=Trueのdataclassとして実装し、フィールドの再代入自体を構造的に
      禁止する（生成後は変更しない）
    - 自分自身を更新する手段（setter・update()メソッド等）を一切持たない。
      新しい判定結果が必要な場合はRetryHealthEvaluator.evaluate()を
      再度呼び出し、新しいインスタンスを生成する
    - Release 6.4ではstatusのみを扱う（Foundation First）。reason／warnings／
      details（またはviolations）等の診断情報は将来拡張の対象とし、本Release
      では追加実装しない
"""
from __future__ import annotations

from dataclasses import dataclass

from .retry_health_status import RetryHealthStatus


@dataclass(frozen=True)
class RetryHealthReport:
    """RetryHealthEvaluatorの判定結果を表すImmutableな値オブジェクト。"""

    status: RetryHealthStatus
