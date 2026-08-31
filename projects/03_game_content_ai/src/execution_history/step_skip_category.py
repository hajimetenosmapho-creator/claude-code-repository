"""
Step Skip Category定義（v6.31.0、Release 6.31 Retry Lineage, Eligibility & Durable
Attempt State foundation）

StepSkipCategory: なぜそのstepがexecuted=Falseになったかを表す構造化Enum

設計方針:
    - `StepExecutionRecord.skipped_reason`（人間可読の自由文字列）とは別に、
      分類ロジック（`retry_lineage.classify_execution_history_step()`）が
      解釈できる構造化フィールドとして`StepExecutionRecord.skip_category`へ
      設定する（docs/design/retry_lineage_eligibility_durable_attempt_state.md
      11.3.2章）。
    - execution_history パッケージは workflow_engine / ai / pipeline / scheduler /
      retry_lineage のいずれもimportしないという既存の一方向依存原則を維持する
      ため、本Enumは（retry_lineage側ではなく）execution_history側に定義する。
      workflow_engine 側の`WorkflowEngineStepResult.skip_category`・retry_lineage
      側の`classify_execution_history_step()`は、いずれも本Enumをexecution_history
      からimportして参照する（同設計書13章）。
"""
from __future__ import annotations

from enum import Enum


class StepSkipCategory(Enum):
    GATE_CLOSED = "gate_closed"                   # 設定起因、恒久的スキップ
    NOT_REACHED = "not_reached"                    # cascade（前段の失敗による未到達）
    HISTORY_WRITE_FAILED = "history_write_failed"  # 構造的スキップ（既存6.30契約）
    HOOK_NOT_ACKNOWLEDGED = "hook_not_acknowledged"  # 構造的スキップ（10.2章）
    HOOK_EXCEPTION = "hook_exception"               # 構造的スキップ（10.2章）
    NOT_TARGETED = "not_targeted"                   # 11.4章：既にconfirmed doneのため今回スキップ
