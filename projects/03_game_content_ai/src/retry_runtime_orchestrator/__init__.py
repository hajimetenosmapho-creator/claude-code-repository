"""
Retry Runtime Orchestrator パッケージ（v5.2.0、v5.3.0でrun_once()を追加）

Retry Runtimeの実行順序を管理する場所。RetryRuntimeOrchestrator（run_once()を含む）・
RetryRuntimeCycleResultを提供する。

設計方針:
    - trigger / scheduler / manager / queue / history / policy への参照を
      Constructor Injectionで保持する。loop() / daemon()等のBusiness Logicは
      いずれも持たない（Foundation First）。
    - from_composition_root()は、RetryCompositionRootが公開する属性を
      そのまま渡すだけの薄いFactory Methodであり、新規インスタンスを
      生成しない（詳細は docs/design/retry_runtime_orchestrator_foundation.md）。
    - （v5.3.0）run_once()はRetry Runtimeを1サイクルだけ実行し、
      RetryRuntimeCycleResultを返す（詳細は
      docs/design/retry_runtime_run_once_foundation.md）。
    - 本Release時点でも、run_once()を呼び出す既存コード（scripts/を含む）は
      存在しない（消費者不在の先行実装）。
"""
from .retry_runtime_cycle_result import RetryRuntimeCycleResult
from .retry_runtime_orchestrator import RetryRuntimeOrchestrator

__all__ = [
    "RetryRuntimeOrchestrator",
    "RetryRuntimeCycleResult",
]
