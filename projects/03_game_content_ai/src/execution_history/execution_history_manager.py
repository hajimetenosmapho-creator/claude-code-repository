"""
Execution History Manager（v2.8.0、Release 6.30でrun_idベースAPIへ移行）

ExecutionHistoryManager:     Workflow実行履歴の記録責務を集約するクラス
NullExecutionHistoryManager: EXECUTION_HISTORY_ENABLED=false（無効）の場合のダミー実装

設計方針:
    - 「実行の観測・記録」のみを担当する。Workflow Engineの実行判断・分岐・再試行判断には
      一切関与しない（docs/design/execution_history_foundation.md 2章・原則1・2）。

Release 6.30での変更（docs/design/production_canonical_run_outcome_contract_foundation.md
9〜17章）:
    - 呼び出し側はmutableな WorkflowExecutionRecord を保持しない。run_id のみを渡す。
      Manager内部が self._last_acknowledged で最後にacknowledgeされたsnapshotを保持する
      （Manager-owned snapshot / Copy-on-write）。
    - 各transitionは copy.deepcopy(snapshot) による独立したcandidateへ適用してから
      store.save() する。ack=True の場合のみsnapshotをcandidateへ置換する。
    - start_run() は StartRunWriteResult（run_id, acknowledged: bool）を返す。Manager自身は
      CanonicalAdmissionFailure を送出しない（呼び出し側の責務）。
    - start_step()/finish_step()/finish_run() は bool（acknowledged）を返す。
    - finish_step()/finish_run() のpersist失敗時は、runをFAILEDへ終端させるrecoveryを
      1回だけ試行する（Terminal Immutability・Recovery契約、13〜14章）。
    - release_run(run_id) はcleanup primitive。idempotent・missing-safe・non-throwing。
"""
from __future__ import annotations

import copy
from datetime import datetime

from .execution_history_event import (
    EVENT_STEP_FINISHED,
    EVENT_STEP_STARTED,
    EVENT_WORKFLOW_FINISHED,
    EVENT_WORKFLOW_STARTED,
    ExecutionHistoryEvent,
)
from .execution_history_config import ExecutionHistoryConfig
from .execution_history_store import ExecutionHistoryStore
from .json_execution_history_store import JsonExecutionHistoryStore
from .start_run_write_result import StartRunWriteResult
from .step_execution_record import StepExecutionRecord, StepExecutionStatus
from .workflow_execution_record import WorkflowExecutionRecord, WorkflowExecutionStatus


class ExecutionHistoryManager:
    """Workflow実行履歴の記録責務を集約するクラス（Manager-owned snapshot）。"""

    def __init__(self, store: ExecutionHistoryStore):
        self._store = store
        self._last_acknowledged: dict[str, WorkflowExecutionRecord] = {}

    @classmethod
    def from_config(
        cls, config: ExecutionHistoryConfig
    ) -> "ExecutionHistoryManager | NullExecutionHistoryManager":
        """ExecutionHistoryConfigから ExecutionHistoryManager を構築する。

        ゲート（EXECUTION_HISTORY_ENABLED）が閉じている場合は NullExecutionHistoryManager を返す。
        """
        if not config.is_ready():
            return NullExecutionHistoryManager()
        return cls(store=JsonExecutionHistoryStore(config.history_dir))

    def start_run(
        self, run_id: str, workflow_name: str, source: str, job_id: str
    ) -> StartRunWriteResult:
        """RUNNING状態のcandidateを作成し、保存を試みる。"""
        now = datetime.now()
        candidate = WorkflowExecutionRecord(
            run_id=run_id,
            workflow_name=workflow_name,
            source=source,
            job_id=job_id,
            status=WorkflowExecutionStatus.RUNNING,
            started_at=now,
        )
        candidate.events.append(
            ExecutionHistoryEvent(
                event_type=EVENT_WORKFLOW_STARTED,
                occurred_at=now,
                message=f"workflow '{workflow_name}' started (run_id={run_id})",
            )
        )
        ack = self._store.save(candidate)
        if ack:
            self._last_acknowledged[run_id] = candidate
        return StartRunWriteResult(run_id=run_id, acknowledged=ack)

    def start_step(self, run_id: str, step: str) -> bool:
        """RUNNING状態のStepExecutionRecordをcandidateへ追加し、保存を試みる。

        Managerはack=False時にrunを自動的にTERMINALへ遷移させない（recoveryを試みない）。
        durable snapshotは変化しない（docs/design/
        production_canonical_run_outcome_contract_foundation.md 12章）。
        """
        snapshot = self._last_acknowledged.get(run_id)
        if snapshot is None or snapshot.status != WorkflowExecutionStatus.RUNNING:
            return False

        candidate = copy.deepcopy(snapshot)
        now = datetime.now()
        candidate.steps.append(
            StepExecutionRecord(step=step, status=StepExecutionStatus.RUNNING, started_at=now)
        )
        candidate.events.append(
            ExecutionHistoryEvent(
                event_type=EVENT_STEP_STARTED, occurred_at=now, message=f"step '{step}' started"
            )
        )
        ack = self._store.save(candidate)
        if ack:
            self._last_acknowledged[run_id] = candidate
        return ack

    def finish_step(
        self,
        run_id: str,
        step: str,
        status: StepExecutionStatus,
        error_message: str | None = None,
        skipped_reason: str | None = None,
    ) -> bool:
        """直近のRUNNING stepを確定させるか、SKIPPED/NOT_REACHEDの正式recordを追加する。

        persist失敗時は、runをFAILEDへ終端させるrecoveryを1回だけ試行する（13章）。
        executed RUNNING stepはFAILEDへ正規化する。SKIPPED/NOT_REACHEDはstatusを保持
        したまま、run自体のみFAILEDへ終端する。いずれの場合も戻り値はFalse。
        """
        snapshot = self._last_acknowledged.get(run_id)
        if snapshot is None or snapshot.status != WorkflowExecutionStatus.RUNNING:
            return False

        candidate = copy.deepcopy(snapshot)
        now = datetime.now()
        pending = self._find_pending_step(candidate, step)
        if pending is not None:
            pending.status = status
            pending.finished_at = now
            pending.error_message = error_message
            pending.skipped_reason = skipped_reason
        else:
            # SKIPPED / NOT_REACHED：正式なStepExecutionRecordを作成する。started_at=None
            # とする（実際には開始していないため。旧v2.8.0のstarted_at=nowから修正）。
            candidate.steps.append(
                StepExecutionRecord(
                    step=step,
                    status=status,
                    started_at=None,
                    finished_at=now,
                    error_message=error_message,
                    skipped_reason=skipped_reason,
                )
            )
        candidate.events.append(
            ExecutionHistoryEvent(
                event_type=EVENT_STEP_FINISHED,
                occurred_at=now,
                message=f"step '{step}' finished with status={status.value}",
            )
        )

        ack = self._store.save(candidate)
        if ack:
            self._last_acknowledged[run_id] = candidate
            return True

        # recovery: runをFAILEDへ終端することを1回だけ試行する。
        recovery_candidate = copy.deepcopy(snapshot)
        recovery_now = datetime.now()
        if pending is not None:
            # executed RUNNING step: FAILEDへ正規化する
            recovery_pending = self._find_pending_step(recovery_candidate, step)
            if recovery_pending is not None:
                recovery_pending.status = StepExecutionStatus.FAILED
                recovery_pending.finished_at = recovery_now
                recovery_pending.error_message = (
                    error_message or "history persistence failure during finish_step"
                )
                recovery_pending.skipped_reason = None
        else:
            # SKIPPED / NOT_REACHED: statusを変更せず保持したまま追加する
            recovery_candidate.steps.append(
                StepExecutionRecord(
                    step=step,
                    status=status,
                    started_at=None,
                    finished_at=recovery_now,
                    error_message=error_message,
                    skipped_reason=skipped_reason,
                )
            )
        recovery_candidate.status = WorkflowExecutionStatus.FAILED
        recovery_candidate.finished_at = recovery_now
        recovery_candidate.events.append(
            ExecutionHistoryEvent(
                event_type=EVENT_WORKFLOW_FINISHED,
                occurred_at=recovery_now,
                message=(
                    f"workflow '{recovery_candidate.workflow_name}' finished with "
                    "status=failed (history recovery after finish_step persistence failure)"
                ),
            )
        )
        recovery_ack = self._store.save(recovery_candidate)
        if recovery_ack:
            self._last_acknowledged[run_id] = recovery_candidate
        # recovery失敗時はlast-known-good snapshot（pre-failure）がそのまま残る。
        return False

    def finish_run(
        self,
        run_id: str,
        status: WorkflowExecutionStatus,
        error_message: str | None = None,
    ) -> bool:
        """record.status/finished_atを確定させる。

        既にTERMINALなrunへの呼び出しは新規persistを行わない（Terminal Immutability）：
        同一status要求はTrue（no-write）、異なるstatus要求はFalse（no-write）。
        RUNNING→TERMINALのpersist失敗時は、常にFAILED方向へのrecoveryを1回だけ試行する
        （recovery成否に関わらず、このfinish_run()呼び出し自体はFalseを返す）。
        """
        snapshot = self._last_acknowledged.get(run_id)
        if snapshot is None:
            return False

        if snapshot.status != WorkflowExecutionStatus.RUNNING:
            # 既にTERMINAL。同一status要求のみidempotent success（no-write）。
            return snapshot.status == status

        candidate = copy.deepcopy(snapshot)
        now = datetime.now()
        candidate.status = status
        candidate.finished_at = now
        candidate.error_message = error_message
        candidate.events.append(
            ExecutionHistoryEvent(
                event_type=EVENT_WORKFLOW_FINISHED,
                occurred_at=now,
                message=f"workflow '{candidate.workflow_name}' finished with status={status.value}",
            )
        )

        ack = self._store.save(candidate)
        if ack:
            self._last_acknowledged[run_id] = candidate
            return True

        # recovery: 常にFAILED方向へ1回だけ試行する。
        recovery_candidate = copy.deepcopy(snapshot)
        recovery_now = datetime.now()
        recovery_candidate.status = WorkflowExecutionStatus.FAILED
        recovery_candidate.finished_at = recovery_now
        recovery_candidate.error_message = error_message
        recovery_candidate.events.append(
            ExecutionHistoryEvent(
                event_type=EVENT_WORKFLOW_FINISHED,
                occurred_at=recovery_now,
                message=(
                    f"workflow '{recovery_candidate.workflow_name}' finished with "
                    "status=failed (history recovery after finish_run persistence failure)"
                ),
            )
        )
        recovery_ack = self._store.save(recovery_candidate)
        if recovery_ack:
            self._last_acknowledged[run_id] = recovery_candidate
        # 元の要求（status）のpersist自体は失敗しているため、recovery成否に関わらずFalse。
        return False

    def release_run(self, run_id: str) -> None:
        """runのin-memory snapshotを解放する（idempotent・missing-safe・non-throwing）。"""
        self._last_acknowledged.pop(run_id, None)
        return None

    @staticmethod
    def _find_pending_step(record: WorkflowExecutionRecord, step: str) -> StepExecutionRecord | None:
        for step_record in reversed(record.steps):
            if step_record.step == step and step_record.status == StepExecutionStatus.RUNNING:
                return step_record
        return None


class NullExecutionHistoryManager:
    """EXECUTION_HISTORY_ENABLED=false のときに使用するダミー実装。

    Release 6.30：すべてのメソッドが明示的な成功acknowledgementを返す（規範、
    docs/design/production_canonical_run_outcome_contract_foundation.md 9章）。
    """

    def start_run(self, run_id: str, workflow_name: str, source: str, job_id: str) -> StartRunWriteResult:
        return StartRunWriteResult(run_id=run_id, acknowledged=True)

    def start_step(self, run_id: str, step: str) -> bool:
        return True

    def finish_step(
        self,
        run_id: str,
        step: str,
        status: StepExecutionStatus,
        error_message: str | None = None,
        skipped_reason: str | None = None,
    ) -> bool:
        return True

    def finish_run(
        self, run_id: str, status: WorkflowExecutionStatus, error_message: str | None = None
    ) -> bool:
        return True

    def release_run(self, run_id: str) -> None:
        return None
