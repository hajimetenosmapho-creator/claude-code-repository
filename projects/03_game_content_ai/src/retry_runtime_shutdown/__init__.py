"""
Retry Runtime Shutdown パッケージ（v6.1.0）

--loop実行中のRetry Runtimeに対するGraceful Shutdown（実行中サイクルは
完了させたうえで、次のサイクルを開始せず終了する）を実現するための
コンポーネント（RetryRuntimeShutdown）を提供する。

設計方針:
    - RetryRuntimeShutdownはRetryドメイン・実行順序・ループ構造のいずれも
      関知しない（詳細は docs/design/retry_runtime_graceful_shutdown_foundation.md）。
    - RetryCompositionRoot / RetryRuntimeOrchestrator / RetryRuntimeLoop等、
      他のretry_*パッケージのいずれにも依存しない。
"""
from .retry_runtime_shutdown import RetryRuntimeShutdown

__all__ = [
    "RetryRuntimeShutdown",
]
