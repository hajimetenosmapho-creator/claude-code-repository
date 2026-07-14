"""
Retry Runtime Lock パッケージ（v6.0.0）

同一Retry Runtimeプロセスの多重起動を防止するための、ファイル存在ベースの
排他制御コンポーネント（RetryRuntimeLock）を提供する。

設計方針:
    - RetryRuntimeLockはRetryドメイン・実行順序・ループ・Daemon化のいずれも
      関知しない（詳細は docs/design/retry_runtime_lock_foundation.md）。
    - RetryCompositionRoot / RetryRuntimeOrchestrator / RetryRuntimeLoop等、
      他のretry_*パッケージのいずれにも依存しない。
"""
from .retry_runtime_lock import RetryRuntimeLock, RetryRuntimeLockError

__all__ = [
    "RetryRuntimeLock",
    "RetryRuntimeLockError",
]
