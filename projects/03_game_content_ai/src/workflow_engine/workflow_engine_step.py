"""
Workflow Engine Step定義（v2.7.0）

WorkflowEngineStep:        Workflow Engineが実行するステップの列挙
ALL_WORKFLOW_ENGINE_STEPS: 標準の実行順序（News → Review → Publish）

設計方針:
    - src/ai/workflow_step.py の WorkflowStep（v1.20.0、AI記事改善6ステップ用）とは別物。
      名前衝突を避けるため、本パッケージのクラスはすべて WorkflowEngine 接頭辞を持つ
      （docs/design/workflow_engine_foundation.md 5章）。
    - WorkflowTriggerAgent（v2.3.0、AI改善6ステップ）に対応するステップは含めない。
      PublishTriggerAgentとの役割重複を理由に今回は対象外（同設計書9章）。
"""
from __future__ import annotations

from enum import Enum


class WorkflowEngineStep(Enum):
    NEWS    = "news"
    REVIEW  = "review"
    PUBLISH = "publish"


ALL_WORKFLOW_ENGINE_STEPS = [
    WorkflowEngineStep.NEWS,
    WorkflowEngineStep.REVIEW,
    WorkflowEngineStep.PUBLISH,
]
