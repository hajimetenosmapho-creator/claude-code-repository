"""
Workflow Engine例外定義（Release 6.30）

CanonicalAdmissionFailure: canonical runがExecution Historyへ受理（admit）されなかったことを
                            表す例外。WorkflowEngineExecutor.run()がraiseする。

設計方針:
    - ExecutionHistoryManager自身はこの例外を送出しない。Managerはack（bool /
      StartRunWriteResult.acknowledged）を返すのみで、それをCanonicalAdmissionFailureへ
      変換する判断はWorkflowEngineExecutorの責務とする
      （docs/design/production_canonical_run_outcome_contract_foundation.md 9・11・19章）。
    - reason は最低限 "EXECUTION_HISTORY_DISABLED"（canonical non-dry-runでHistoryが
      無効） / "START_RUN_ACK_FAILED"（start_run()のpersist失敗）の2値を想定する。
    - Retry Runtime（Codex Ruling A）はこの例外を既存のfail-fastでそのまま伝播させる。
      RetryExecutor/RetryManager側に新規catch/変換ロジックは追加しない（同設計書21章）。
"""
from __future__ import annotations


class CanonicalAdmissionFailure(Exception):
    """canonical runがExecution Historyへ受理されなかったことを表す例外。"""

    def __init__(self, run_id: str, reason: str):
        self.run_id = run_id
        self.reason = reason
        super().__init__(f"Canonical admission failed for run_id={run_id}: reason={reason}")
