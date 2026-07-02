"""
Workflow Engine Definition（v2.7.0）

WorkflowEngineDefinition: Workflow Engineが実行するステップの並びを定義するデータクラス

設計方針:
    - Foundation Releaseでは ALL_WORKFLOW_ENGINE_STEPS 固定の1種類のみを想定するが、
      将来の条件分岐・部分実行（例：Reviewだけ実行）に備え、steps を外部から
      差し替え可能なフィールドとして持たせる（docs/design/workflow_engine_foundation.md
      6章・17章）。条件分岐・並列実行そのものは今回実装しない。
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .workflow_engine_step import ALL_WORKFLOW_ENGINE_STEPS, WorkflowEngineStep


@dataclass
class WorkflowEngineDefinition:
    steps: list[WorkflowEngineStep] = field(default_factory=lambda: list(ALL_WORKFLOW_ENGINE_STEPS))
