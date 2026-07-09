"""
Retry Runtime Loop パッケージ（v5.5.0）

run_once_fn を interval ごとに繰り返し呼び出すだけの薄いWrapper（RetryRuntimeLoop）を
提供する。

設計方針:
    - RetryRuntimeLoopはBusiness Logicを一切持たない。run_once_fn / sleep_fn /
      should_continue_fnへの参照を保持し、繰り返し呼び出す順序のみを実行する
      （詳細は docs/design/retry_runtime_loop_foundation.md）。
    - RetryManager / RetryQueueManager / RetryHistoryManager / RetryPolicy /
      RetryRuntimeOrchestrator / RetryCompositionRootのいずれもimportしない。
    - 本Release時点で、本クラスを呼び出す既存コード（scripts/を含む）は存在しない
      （消費者不在の先行実装）。
"""
from .retry_runtime_loop import RetryRuntimeLoop

__all__ = [
    "RetryRuntimeLoop",
]
