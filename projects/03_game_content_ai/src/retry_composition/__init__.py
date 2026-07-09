"""
Retry Composition パッケージ（v5.1.0）

workflow_monitor / retry_queue / retry_history / retry_enqueue_trigger /
retry_engine / workflow_engine を、既存の from_env()/from_config() のみで
組み立てる Composition Root（RetryCompositionRoot）を提供する。

RetryQueueManager / RetryHistoryManager を1インスタンスずつ生成し、
RetryEnqueueTrigger（Enqueue側）と RetryManager（Execute側）の両方へ
同一インスタンスとして注入する。実行順序の決定・ループ・デーモン化は
本パッケージの責務としない（docs/design/retry_composition_root_foundation.md参照）。
"""
from .retry_composition_root import RetryCompositionRoot

__all__ = [
    "RetryCompositionRoot",
]
