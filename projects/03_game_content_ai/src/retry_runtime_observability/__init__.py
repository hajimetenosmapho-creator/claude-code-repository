"""
Retry Runtime Observability パッケージ（v6.33.0）

Retry Runtimeの各サイクル実行完了後、RetryObservabilityPipelineを呼び出して
RetryObservabilityReportを得て、コンソールへ出力するコンポーネント
（RetryRuntimeObservabilityReporter）を提供する。

設計方針（docs/design/retry_observability_runtime_integration_foundation.md）:
    - RetryRuntimeObservabilityReporterはRetryドメイン・実行順序・ループ構造の
      いずれも関知しない。
    - 既存のretry判断コンポーネント（Manager系）・Composition Root・
      Orchestrator・scheduler・scriptsのいずれにも依存しない（retry_metricsと
      retry_observability_pipelineのみに依存する葉パッケージ）。
"""
from .retry_runtime_observability_reporter import RetryRuntimeObservabilityReporter

__all__ = [
    "RetryRuntimeObservabilityReporter",
]
