"""
Retry Lineage Target Resolution（v6.31.0、Release 6.31）

decide_disposition():           WorkflowEngineResultからRetryLineageDispositionを判定する
compute_newly_confirmed():      同期パス用。今回のattemptでGENUINE_SUCCESSと分類できたstep名を返す
compute_steps_to_execute():     steps_confirmed_doneから次に実行すべきstep集合を算出する
compute_initial_confirmed_steps(): attempt 1用。元recordのGENUINE_SUCCESS stepのみを抽出する
_canonicalize_step_order():     steps_to_executeをWorkflow canonical orderへ正規化する共通ヘルパー

設計方針（docs/design/retry_lineage_eligibility_durable_attempt_state.md 11.4.3・
11.5・7.2.2・7.3章）:
    - ファイル配置についての注記はretry_lineage_genuine_action.py冒頭を参照。
    - compute_steps_to_execute()の戻り値は常にALL_WORKFLOW_ENGINE_STEPSの列挙順
      （Workflow canonical order）で並ぶ不変条件を持つ。この関数がstoredの
      attempt_scopes[-1].steps_to_execute（lineage作成時またはopen_next_attempt()が
      書き込む値）とclaim()の再計算値の両方を生成する唯一の関数であるため、両者は
      常に同一のcanonical orderで比較可能である。
    - _canonicalize_step_order()は、create_new_lineage()・open_next_attempt()
      （書き込み時）・claim()（比較時）の3箇所で共有される、唯一のcanonicalize実装。
"""
from __future__ import annotations

from execution_history import StepExecutionRecord
from workflow_engine import ALL_WORKFLOW_ENGINE_STEPS, WorkflowEngineResult

from .retry_lineage_disposition import RetryLineageDisposition
from .retry_lineage_genuine_action import (
    StepOutcomeCategory,
    classify_execution_history_step,
    classify_step_outcome,
)


def decide_disposition(engine_result: WorkflowEngineResult) -> RetryLineageDisposition:
    """優先順位：UNKNOWN→FAILED、RETRYABLE_FAILURE→FAILED、SILENT_NO_ACTION→NOT_ACTIONED、
    それ以外（全executed stepがGENUINE_SUCCESS、残りはNOT_APPLICABLE/INTENTIONAL_NO_ACTION）
    →SUCCEEDED。"""
    categories = [classify_step_outcome(s) for s in engine_result.steps]
    return disposition_from_categories(categories)


def disposition_from_categories(categories: list[StepOutcomeCategory]) -> RetryLineageDisposition:
    """decide_disposition()の判定ロジック本体（同期パス）と、reconcile_all()経路
    （classify_execution_history_step()ベースのcategories）の両方から共有される。"""
    if any(c == StepOutcomeCategory.UNKNOWN for c in categories):
        return RetryLineageDisposition.FAILED
    if any(c == StepOutcomeCategory.RETRYABLE_FAILURE for c in categories):
        return RetryLineageDisposition.FAILED
    if any(c == StepOutcomeCategory.SILENT_NO_ACTION for c in categories):
        return RetryLineageDisposition.NOT_ACTIONED
    return RetryLineageDisposition.SUCCEEDED


def compute_newly_confirmed(engine_result: WorkflowEngineResult) -> list[str]:
    """このattemptでGENUINE_SUCCESSと分類されたstep名を返す（steps_confirmed_doneへ
    追加する対象）。"""
    return [
        s.step.value for s in engine_result.steps
        if classify_step_outcome(s) == StepOutcomeCategory.GENUINE_SUCCESS
    ]


def compute_steps_to_execute(steps_confirmed_done: list[str]) -> list[str]:
    """次attemptで実際に実行すべきstep（既にconfirmed doneのものを除く全step）を返す。

    不変条件：戻り値は常にALL_WORKFLOW_ENGINE_STEPSの列挙順（Workflow canonical
    order、NEWS→REVIEW→PUBLISHの固定順）で並ぶ。
    """
    return [s.value for s in ALL_WORKFLOW_ENGINE_STEPS if s.value not in steps_confirmed_done]


def compute_initial_confirmed_steps(steps: list[StepExecutionRecord]) -> list[str]:
    """元のFAILED/TIMEOUT実行のStepExecutionRecord列（WorkflowMonitorRecord.steps、
    実体はWorkflowExecutionRecord.stepsのコピー）から、GENUINE_SUCCESSと分類できた
    stepのみをattempt 1のsteps_confirmed_done初期値として返す。

    classify_execution_history_step()を再利用し、compute_newly_confirmed()と同一の
    「GENUINE_SUCCESSのみが合成対象」契約を保つ。NOT_APPLICABLE（NOT_REACHED等）・
    RETRYABLE_FAILURE・SILENT_NO_ACTION・INTENTIONAL_NO_ACTION・UNKNOWN（legacy
    record、action_taken未設定等を含む）は、いずれもGENUINE_SUCCESSではないため
    自動的に除外される。
    """
    return [
        s.step for s in steps
        if classify_execution_history_step(s) == StepOutcomeCategory.GENUINE_SUCCESS
    ]


def _canonicalize_step_order(steps: list[str]) -> list[str]:
    """ALL_WORKFLOW_ENGINE_STEPSの列挙順（Workflow canonical order）へ正規化する。

    compute_steps_to_execute()の戻り値は既にこの順序で構築される不変条件を持つが、
    このヘルパーはdefense-in-depthとして、書き込み直前・比較直前のいずれでも
    独立に適用できる、順序破損に対する冪等な正規化操作として提供する。
    """
    canonical_order = {s.value: i for i, s in enumerate(ALL_WORKFLOW_ENGINE_STEPS)}
    return sorted(steps, key=lambda s: canonical_order[s])
