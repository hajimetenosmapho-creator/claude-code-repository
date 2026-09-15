"""
Scheduler Driver Orchestrator（v6.34.0、Release 6.34）

SchedulerDriverOrchestrator: 1 cycle分の判定・claim・dispatch・confirmを行う
                              Business Logic本体

設計方針（docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md
11〜13・15・16章）:
    - run_once()の先頭で必ずOwnership-Integrity Self-Check（12.1章）を行う。
      Falseの場合はLockIntegrityViolationErrorを送出し、reconcile_stale_claims()
      以降には一切進まない。
    - 次にreconcile_stale_claims()（11.2章：毎cycle先頭）を呼ぶ。
    - SchedulerEngine.evaluate()自体は無改修のまま呼び出すのみ（pure boundary
      維持、Zero-Diff）。戻り値へDesign Decision J（16章）のfilterを適用してから
      dispatchする。
    - _dispatch_one()内でWorkflowEngineManager.run()呼び出しをtry/except
      Exceptionで囲み、containし再raiseしない（15章 Design Decision I）。
      BaseExceptionはcatchしない。
    - confirm()の戻り値を必ず確認する（8.2章、6.32 Suggestionと同種のgapを
      再発させないための明示的設計原則）。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from workflow_engine import SOURCE_SCHEDULER, WorkflowEngineEvent

from .scheduler_driver_cycle_result import DispatchOutcome, SchedulerDriverCycleResult
from .scheduler_driver_dispatch_filter import _select_dispatchable_events
from .scheduler_driver_event_identity import build_event_identity
from .scheduler_driver_lock_integrity import LockIntegrityViolationError, _verify_lock_ownership

if TYPE_CHECKING:
    from pathlib import Path

    from scheduler import ClockProvider, SchedulerEngine, SchedulerEvent
    from scheduler_dispatch_ledger import SchedulerDispatchLedger
    from scheduler_schedule_source import ProductionScheduleSource
    from workflow_engine import WorkflowEngineManager


class SchedulerDriverOrchestrator:
    """1 cycle分の判定・claim・dispatch・confirmを行うOrchestrator。"""

    def __init__(
        self,
        scheduler_engine: "SchedulerEngine",
        schedule_source: "ProductionScheduleSource",
        ledger: "SchedulerDispatchLedger",
        workflow_engine_manager: "WorkflowEngineManager",
        lock_path: "Path",
        own_pid: int,
        clock: "ClockProvider | None" = None,
    ):
        from scheduler import SystemClockProvider

        self._scheduler_engine = scheduler_engine
        self._schedule_source = schedule_source
        self._ledger = ledger
        self._workflow_engine_manager = workflow_engine_manager
        self._lock_path = lock_path
        self._own_pid = own_pid
        self._clock = clock or SystemClockProvider()

    def run_once(self) -> SchedulerDriverCycleResult:
        # 12.1章：Ownership-Integrity Self-Check（run_once()冒頭）。
        if not _verify_lock_ownership(self._lock_path, self._own_pid):
            raise LockIntegrityViolationError(self._lock_path, self._own_pid)

        # 11.2章：reconcile_stale_claims()は毎cycle先頭（self-check直後）で呼ぶ。
        # 失敗時（8.5章(4)）は例外がそのまま伝播し、以降の処理へは一切進まない。
        reconcile_summary = self._ledger.reconcile_stale_claims()

        now = self._clock.now()
        jobs = self._schedule_source.jobs()
        events = self._scheduler_engine.evaluate(jobs, now)
        production_job_ids = frozenset(j.job_id for j in jobs)
        events = _select_dispatchable_events(events, production_job_ids)

        dispatched: list[DispatchOutcome] = []
        skipped: list[DispatchOutcome] = []
        for event in events:
            outcome = self._dispatch_one(event)
            (dispatched if outcome.dispatched else skipped).append(outcome)

        return SchedulerDriverCycleResult(
            dispatched=dispatched, skipped=skipped, recovery_marked=reconcile_summary.recovery_marked,
        )

    def _dispatch_one(self, event: "SchedulerEvent") -> DispatchOutcome:
        event_identity, occurrence_minute = build_event_identity(event.job_id, event.execute_time)

        # 10章 Design Decision D：fail-closed dispatch契約。claimのdurable ackを
        # 得られない限り、WorkflowEngineManager.run()を一切呼ばない。
        claim_result = self._ledger.claim(event_identity, event.job_id, occurrence_minute)
        if not claim_result.acknowledged:
            return DispatchOutcome(
                event_identity=event_identity, job_id=event.job_id, dispatched=False,
                reason=f"claim not acknowledged: {claim_result.reason}",
            )

        workflow_event = WorkflowEngineEvent(
            job_id=event.job_id,
            source=SOURCE_SCHEDULER,
            triggered_at=event.execute_time,
            trigger_reason=event.trigger_reason,
            metadata=dict(event.metadata),
        )

        # 15章 Design Decision I：Exceptionはcontainし再raiseしない
        # （1eventの失敗が同一cycle内の他event・次cycleをブロックしないため）。
        # BaseExceptionはcatchしない。
        run_id: str | None = None
        try:
            result = self._workflow_engine_manager.run(workflow_event, dry_run=False)
        except Exception as e:  # noqa: BLE001 - 15章の意図的な広いcontainment方針
            run_id = getattr(e, "run_id", None)
            outcome_summary = f"EXCEPTION:{type(e).__name__}"
        else:
            run_id = getattr(result, "run_id", None) if result is not None else None
            overall_success = getattr(result, "overall_success", None) if result is not None else None
            outcome_summary = f"overall_success={overall_success}"

        # confirm()の戻り値は必ず確認する（8.2章、6.32 Suggestionと同種のgap回避）。
        confirmed = self._ledger.confirm(event_identity, run_id, outcome_summary)
        if not confirmed:
            print(
                f"  [SCHEDULER DRIVER WARNING] confirm()がack=Falseを返しました"
                f"（event_identity={event_identity}）。次回reconciliationで"
                "RECOVERY_REQUIREDへ倒れます（8.2章の意図的な安全側トレードオフ）。"
            )

        return DispatchOutcome(
            event_identity=event_identity, job_id=event.job_id, dispatched=True,
            reason=outcome_summary, run_id=run_id,
        )
