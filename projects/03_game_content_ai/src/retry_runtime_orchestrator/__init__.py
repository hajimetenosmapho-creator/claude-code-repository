"""
Retry Runtime Orchestrator パッケージ（v5.2.0）

Retry Runtimeの実行順序を将来管理する場所。RetryRuntimeOrchestratorを提供する。

設計方針:
    - trigger / scheduler / manager / queue / history / policy への参照を
      Constructor Injectionで保持するだけで、run() / run_once() / loop() /
      daemon()等のBusiness Logicはいずれも持たない（Foundation First）。
    - from_composition_root()は、RetryCompositionRootが公開する属性を
      そのまま渡すだけの薄いFactory Methodであり、新規インスタンスを
      生成しない（詳細は docs/design/retry_runtime_orchestrator_foundation.md）。
    - 本Release時点ではどのパッケージからも呼ばれない（Foundation First。
      scripts/を含めても未接続）。
"""
from .retry_runtime_orchestrator import RetryRuntimeOrchestrator

__all__ = [
    "RetryRuntimeOrchestrator",
]
