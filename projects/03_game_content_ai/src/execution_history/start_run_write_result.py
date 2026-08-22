"""
Start Run Write Result定義（Release 6.30）

StartRunWriteResult: ExecutionHistoryManager.start_run() の戻り値。

設計方針:
    - Manager自身は CanonicalAdmissionFailure をthrowしない。acknowledged=False を
      どう扱うか（例外化するか等）は呼び出し側（WorkflowEngineExecutor）の責務とする
      （docs/design/production_canonical_run_outcome_contract_foundation.md 9章）。
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class StartRunWriteResult:
    run_id: str
    acknowledged: bool
