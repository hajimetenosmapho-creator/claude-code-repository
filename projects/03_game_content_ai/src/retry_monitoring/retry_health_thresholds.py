"""
Retry Health Thresholds（v6.4.0）

RetryHealthThresholds: RetryHealthEvaluatorが判定に用いる閾値を表す、
                        Immutable（読み取り専用）な値オブジェクト。

設計方針（docs/design/retry_monitoring_foundation.md 6.5節 Architecture Decision AD-1）:
    - frozen=Trueのdataclassとして実装し、フィールドの再代入自体を構造的に
      禁止する（生成後は変更しない）
    - Config（外部設定・環境変数・設定ファイル）ではなく、Monitoring Domainの
      Domain Value（ドメイン値）として位置づける
    - Foundationの責務は「固定値を保持すること」のみであり、値の取得元
      （環境変数・設定ファイル等）を自ら決定する責務は持たない（11.3節）
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryHealthThresholds:
    """RetryHealthEvaluatorが判定に用いる閾値を表すImmutable Value Object（Domain Value）。

    enqueue_success_ratioに対する下限値。RetryMetricsSnapshot.enqueue_success_ratio
    がNone（cycle_count=0等でratio自体が算出不能）の場合、閾値判定は行わずHEALTHYとする。
    """

    degraded_below: float = 0.8
    unhealthy_below: float = 0.5
