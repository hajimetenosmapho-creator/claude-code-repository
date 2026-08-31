"""
Retry Lineage Manager戻り値型（v6.31.0、Release 6.31）

CreateNewLineageResult: create_new_lineage()の戻り値
ClaimResult:            claim()の戻り値
MarkTerminalResult:      mark_terminal()の戻り値
OpenNextAttemptResult:   open_next_attempt()の戻り値
ReconcileSummary:        reconcile_all()の戻り値

設計方針（docs/design/retry_lineage_eligibility_durable_attempt_state.md 7.2・
9.3.2・9.8.1・12・13章）:
    - mark_execution_started()は単純なbool（ack）を返す（post-admission hookの
      戻り値へそのまま詰め替えられる、10.2.2章）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .retry_lineage_record import RetryLineageRecord


@dataclass
class CreateNewLineageResult:
    lineage: "RetryLineageRecord | None"
    admission_rejected: bool = False
    reason: str | None = None


@dataclass
class ClaimResult:
    acknowledged: bool
    reason: str | None = None
    attempt_no: int | None = None
    correlation_id: str | None = None
    steps_to_execute: list[str] | None = None


@dataclass
class MarkTerminalResult:
    acknowledged: bool
    reason: str | None = None


@dataclass
class OpenNextAttemptResult:
    acknowledged: bool
    reason: str | None = None
    attempt_no: int | None = None


@dataclass
class ReconcileSummary:
    skipped: bool = False
    reason: str | None = None
    resolved_count: int = 0
    opened_count: int = 0
    # Architecture Amendment（Code Review Blocking#1対応、16章(c)）：phase==CLAIMEDの
    # orphan（post-admission hook呼び出しに到達する前のプロセスクラッシュ由来）を
    # release_claim()でREADY_ELIGIBLEへ回収した件数。
    released_count: int = 0
