"""
Retry Metrics パッケージ（v6.3.0）

.run/retry_runtime_log.jsonl（v6.2.0 RetryRuntimeCycleLoggerが書き込むJSON
Linesログ）を読み取り、集計値（RetryMetricsSnapshot）を計算するだけの、
Read Only Foundationパッケージ。

設計方針（docs/design/retry_metrics_foundation.md）:
    - Read Only Foundation：集計のみを担当し、Retry Runtimeへ一切
      フィードバックを行わない（Retry Queueの更新・RetryManagerの変更・
      RetryRuntimeOrchestrator/RetryRuntimeLoop/RetryRuntimeShutdown/
      RetryRuntimeLockの変更・Scheduler通知・Retry実行可否の判断・
      Alert判定・Monitoring Policyのいずれも行わない）
    - RetryMetricsSnapshotはImmutable（frozen dataclass）。生成後は変更せず、
      将来のMonitoringはこれを参照するだけで更新しない
    - RetryRuntimeLock / RetryRuntimeShutdown / RetryRuntimeLoop /
      RetryRuntimeOrchestrator / RetryManager / RetryRuntimeCycleLogger等、
      他のretry_*パッケージのいずれにも依存しない（ファイルパスとJSON Schemaの
      「形」のみを契約とする、型参照ではなく契約（shape一致）による疎結合）
    - 本Releaseでは消費者不在の先行実装。scripts/エントリーポイント・CLI表示・
      Retry Monitoring Foundationは対象外（Foundation First）
"""
from .retry_metrics_calculator import RetryMetricsCalculator
from .retry_metrics_snapshot import RetryMetricsSnapshot
from .retry_runtime_log_reader import RetryRuntimeLogReader
from .retry_runtime_log_record import RetryRuntimeLogRecord

__all__ = [
    "RetryRuntimeLogRecord",
    "RetryRuntimeLogReader",
    "RetryMetricsSnapshot",
    "RetryMetricsCalculator",
]
