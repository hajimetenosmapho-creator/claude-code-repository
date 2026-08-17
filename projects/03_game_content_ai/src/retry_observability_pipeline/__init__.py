"""
Retry Observability Pipeline パッケージ（v6.29.0）

retry_metrics（v6.3.0）〜retry_notification_message（v6.7.0）の5パッケージを、
metrics -> monitoring -> alert -> notification -> messageという固定順序で
Composeするだけの、Orchestration/Facade Foundationパッケージ。

設計方針（docs/design/retry_observability_pipeline_foundation.md）:
    - Orchestration/Facade層：判定・値構築ロジックは一切追加せず、既存5パッケージの
      呼び出し順序を固定するだけの責務に限定する（ArticleFeaturedMediaOrchestrator
      （v6.14.0）と同型の契約。one-hop-back Foundation規律の一般的な例外ではない）
    - 唯一の入力はlist[RetryRuntimeLogRecord]（既にパース済みのrecord）。
      RetryRuntimeLogReaderは一切importせず、ファイルI/Oは行わない
    - RetryObservabilityReportはImmutable（frozen dataclass）。__post_init__で
      status/message invariantを強制する
    - Runtime・RetryCompositionRoot・Scheduler・CLI（scripts/）・Senderのいずれも
      知らない・importしない（消費者不在の先行実装、Foundation First）
    - scripts/show_retry_notification.pyのbuild_report()とはv6.29.0時点で
      Compositionロジックが一時的に重複する（temporary debt）。次Wiring Releaseで
      CLI側を本Facadeへの委譲へ置き換え、統一する
"""
from .retry_observability_pipeline import RetryObservabilityPipeline
from .retry_observability_report import RetryObservabilityReport

__all__ = [
    "RetryObservabilityReport",
    "RetryObservabilityPipeline",
]
