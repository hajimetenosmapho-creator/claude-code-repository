"""
Retry Runtime Logging パッケージ（v6.2.0）

Retry Runtimeの各サイクル終了時に、JSON Lines形式で1サイクル1レコードの
Runtimeログを出力するコンポーネント（RetryRuntimeCycleLogger）を提供する。

設計方針:
    - RetryRuntimeCycleLoggerはRetryドメイン・実行順序・ループ構造のいずれも
      関知しない（詳細は docs/design/retry_runtime_structured_loop_logging_foundation.md）。
    - RetryRuntimeLock / RetryRuntimeShutdown / RetryRuntimeLoop /
      RetryRuntimeOrchestrator / RetryManager等、他のretry_*パッケージの
      いずれにも依存しない（RetryRuntimeCycleResultの型参照のみ）。
"""
from .retry_runtime_cycle_logger import RetryRuntimeCycleLogger

__all__ = [
    "RetryRuntimeCycleLogger",
]
