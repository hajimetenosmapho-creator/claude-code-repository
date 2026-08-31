"""
Retry Lineage Genuine Action分類（v6.31.0、Release 6.31）

StepOutcomeCategory:            1 stepの実行結果を分類した結果（6値、closed-set）
classify_step_outcome():        WorkflowEngineStepResultを分類する純関数（同期パス用）
classify_execution_history_step(): StepExecutionRecordを分類する純関数（reconcile経路用）

設計方針（docs/design/retry_lineage_eligibility_durable_attempt_state.md 11.3・11.7章）:
    - 両分類関数は「既知の値をin (...)で明示的に列挙し、それ以外はUNKNOWNへ
      fail-closedする」という一字一句対称なclosed-set semanticsを持つ（Round 7、
      M-1対応）。将来の`StepSkipCategory`拡張・`action_taken`の型不正混入は
      いずれもUNKNOWNへ倒れる。
    - 実装配置についての注記：本ファイル・retry_lineage_target_resolution.pyは、
      設計書§14・§22では`src/retry_engine/`配下（`retry_genuine_action.py`・
      `retry_target_resolution.py`）に置く案が示されていたが、実装時に
      `RetryLineageDisposition`（本パッケージ）と`RetryPolicy`（retry_engine）の
      双方向依存という循環importが判明したため、`src/retry_lineage/`側へ配置する
      形へ調整した（retry_engine → retry_lineage の一方向importのみで完結させる。
      retry_lineage → retry_engineは、RetryPolicyの型ヒントをTYPE_CHECKING経由の
      遅延参照とすることで実行時依存を発生させない）。公開する関数シグネチャ・
      分類ロジック・fail-closed契約はいずれも設計書の記述と完全に同一であり、
      アーキテクチャ・振る舞いの変更ではない。
    - execution_historyへの依存（StepExecutionRecord・StepSkipCategory）は
      本パッケージ（retry_lineage）が新たに負う。retry_engine自身は本パッケージ
      経由でのみこれらの型を扱い、execution_historyを直接importしない
      （既存のretry_engine設計原則を維持する）。
"""
from __future__ import annotations

from enum import Enum

from execution_history import StepExecutionRecord, StepExecutionStatus, StepSkipCategory
from workflow_engine import WorkflowEngineStepResult


class StepOutcomeCategory(Enum):
    GENUINE_SUCCESS = "genuine_success"
    RETRYABLE_FAILURE = "retryable_failure"
    SILENT_NO_ACTION = "silent_no_action"
    INTENTIONAL_NO_ACTION = "intentional_no_action"
    NOT_APPLICABLE = "not_applicable"
    UNKNOWN = "unknown"


def classify_step_outcome(step_result: WorkflowEngineStepResult) -> StepOutcomeCategory:
    """WorkflowEngineStepResultをStepOutcomeCategoryへ分類する（同期パス用）。"""
    if not step_result.executed:
        if step_result.agent_result is not None:
            return StepOutcomeCategory.UNKNOWN  # 構造的に到達しないはずだが防御的にfail-closed
        if step_result.skip_category is None:
            return StepOutcomeCategory.UNKNOWN  # 構造化フィールド未設定＝防御的にfail-closed
        if step_result.skip_category == StepSkipCategory.GATE_CLOSED:
            return StepOutcomeCategory.INTENTIONAL_NO_ACTION
        if step_result.skip_category in (
            StepSkipCategory.NOT_REACHED,
            StepSkipCategory.HISTORY_WRITE_FAILED,
            StepSkipCategory.HOOK_NOT_ACKNOWLEDGED,
            StepSkipCategory.HOOK_EXCEPTION,
            StepSkipCategory.NOT_TARGETED,
        ):
            return StepOutcomeCategory.NOT_APPLICABLE
        return StepOutcomeCategory.UNKNOWN  # 将来のenum拡張に対する防御的fail-closed

    # executed=True
    if step_result.agent_result is None:
        return StepOutcomeCategory.UNKNOWN
    if not step_result.success:
        return StepOutcomeCategory.RETRYABLE_FAILURE
    return _classify_action_taken(step_result.agent_result.action_taken)


def classify_execution_history_step(step: StepExecutionRecord) -> StepOutcomeCategory:
    """StepExecutionRecordをStepOutcomeCategoryへ分類する（reconcile_all()経路用）。"""
    if step.status == StepExecutionStatus.FAILED:
        return StepOutcomeCategory.RETRYABLE_FAILURE
    if step.status == StepExecutionStatus.RUNNING:
        return StepOutcomeCategory.RETRYABLE_FAILURE  # abandoned TIMEOUTの対象
    if step.status == StepExecutionStatus.NOT_REACHED:
        return StepOutcomeCategory.NOT_APPLICABLE
    if step.status == StepExecutionStatus.SKIPPED:
        if step.skip_category is None:
            return StepOutcomeCategory.UNKNOWN
        if step.skip_category == StepSkipCategory.GATE_CLOSED:
            return StepOutcomeCategory.INTENTIONAL_NO_ACTION
        if step.skip_category in (
            StepSkipCategory.NOT_REACHED,
            StepSkipCategory.HISTORY_WRITE_FAILED,
            StepSkipCategory.HOOK_NOT_ACKNOWLEDGED,
            StepSkipCategory.HOOK_EXCEPTION,
            StepSkipCategory.NOT_TARGETED,
        ):
            return StepOutcomeCategory.NOT_APPLICABLE
        return StepOutcomeCategory.UNKNOWN
    if step.status == StepExecutionStatus.SUCCESS:
        return _classify_action_taken(step.action_taken)
    return StepOutcomeCategory.UNKNOWN


def _classify_action_taken(action_taken: object) -> StepOutcomeCategory:
    """action_takenの恒等比較による分類。True/False以外（Noneを含む）はUNKNOWNへfail-closed。"""
    if action_taken is True:
        return StepOutcomeCategory.GENUINE_SUCCESS
    if action_taken is False:
        return StepOutcomeCategory.SILENT_NO_ACTION
    return StepOutcomeCategory.UNKNOWN
