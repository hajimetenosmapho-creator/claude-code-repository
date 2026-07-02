"""
Workflow Engine パッケージ（v2.7.0）

Scheduler（v2.6.0）が生成する SchedulerEvent を起点に、既存の3つのTrigger Agent
（NewsAgent → ReviewTriggerAgent → PublishTriggerAgent）を決まった順序で実行する
オーケストレーション層。

処理フロー（v2.7.0）:
    SchedulerEvent（v2.6.0、Scheduler側で生成） → WorkflowEngineEvent（変換、呼び出し元の責務）
        → WorkflowEngineManager.run() → WorkflowEngineExecutor
            → NewsAgent → ReviewTriggerAgent → PublishTriggerAgent（いずれも既存、無改修）
        → WorkflowEngineResult

設計方針:
    - src/ai/workflow_*.py（v1.20.0、AI記事改善6ステップ用）とは別物。パッケージ・
      クラス名の両方を分離し、名前衝突を避ける（docs/design/workflow_engine_foundation.md 5章）。
    - 既存4 Trigger Agent・AgentManager / AgentExecutor（v2.0.0）・Scheduler本体（v2.6.0）は
      いずれも無改修のまま呼び出すのみ。
    - Configuration First：AI_AGENT_ENABLED × WORKFLOW_ENGINE_ENABLED の二重ゲートが
      揃わない限り、WorkflowEngineManager.from_config() は NullWorkflowEngineManager を返す。
"""
from .workflow_engine_step import ALL_WORKFLOW_ENGINE_STEPS, WorkflowEngineStep
from .workflow_engine_definition import WorkflowEngineDefinition
from .workflow_engine_event import SOURCE_MANUAL, SOURCE_SCHEDULER, WorkflowEngineEvent
from .workflow_engine_result import (
    REASON_NOT_REACHED,
    WorkflowEngineResult,
    WorkflowEngineStepResult,
)
from .workflow_engine_context import WorkflowEngineContext
from .workflow_engine_config import WorkflowEngineConfig
from .workflow_engine_executor import WorkflowEngineExecutor
from .workflow_engine_manager import NullWorkflowEngineManager, WorkflowEngineManager

__all__ = [
    "WorkflowEngineStep",
    "ALL_WORKFLOW_ENGINE_STEPS",
    "WorkflowEngineDefinition",
    "WorkflowEngineEvent",
    "SOURCE_SCHEDULER",
    "SOURCE_MANUAL",
    "WorkflowEngineStepResult",
    "WorkflowEngineResult",
    "REASON_NOT_REACHED",
    "WorkflowEngineContext",
    "WorkflowEngineConfig",
    "WorkflowEngineExecutor",
    "WorkflowEngineManager",
    "NullWorkflowEngineManager",
]
