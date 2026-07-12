"""
Retry Result定義（v3.0.0）

RetryOutcome: 1回の再実行試行の結果種別を表すEnum
RetryResult:  1回の再実行試行の結果を保持するデータクラス

設計方針:
    - workflow_engine_result は outcome == RetryOutcome.RETRIED または RetryOutcome.DRY_RUN
      の場合のみ値を持つ。WorkflowEngineManager.run() の戻り値をそのまま透過的に保持する
      ことで、呼び出し元は再実行（またはdry_runでの試行）の成否をこの1回の同期呼び出しの
      中だけで把握できる（新しいrun_idそのものはWorkflowEngineResultが公開していないため
      保持しない。docs/design/retry_engine_foundation.md 10章 Design Decision #5）。
    - （v5.6.0）RetryOutcomeにDRY_RUNを追加した。RetryExecutor.execute()がdry_run=Trueの
      場合、WorkflowEngineManager.run()自体は呼び出す（dry_run=Trueが伝播しAgent層の
      act()が呼ばれないため実際の副作用はない）が、戻り値のoutcomeをRETRIEDではなく
      DRY_RUNとする。既存のDecider/Executor（RetryQueueUpdateDecider・
      RetryHistoryRecordExecutor・RetryQueueRemovalExecutor・RetryQueueCleanupDecider）は
      いずれも「outcome==RETRIEDかどうか」またはallowlist方式で判定しているため、
      DRY_RUNは無改修のまま自動的に安全側（NOOP・記録なし・除去なし）に倒れる。
      唯一retry_outcome_terminality.pyのみ、明示列挙+raiseの網羅チェック方式のため
      改修が必須だった（docs/design/retry_runtime_safe_dry_run_foundation.md 参照）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from workflow_engine import WorkflowEngineResult
from workflow_monitor import WorkflowMonitorStatus


class RetryOutcome(Enum):
    RETRIED = "retried"      # WorkflowEngineManager.run()を呼び出し、再実行した
    SKIPPED = "skipped"      # 再実行対象外（状態不一致 or 上限到達）
    NOT_FOUND = "not_found"  # run_idがWorkflow Monitorに存在しない
    DISABLED = "disabled"    # RETRY_ENGINE_ENABLED=false、または下位ゲートが閉じている
    DRY_RUN = "dry_run"      # dry_run=Trueで再実行を試行した（Queue/History等への副作用なし、v5.6.0）


@dataclass(frozen=True)
class RetryResult:
    original_run_id: str
    outcome: RetryOutcome
    attempt: int
    monitor_status: WorkflowMonitorStatus | None
    reason: str | None
    workflow_engine_result: WorkflowEngineResult | None
