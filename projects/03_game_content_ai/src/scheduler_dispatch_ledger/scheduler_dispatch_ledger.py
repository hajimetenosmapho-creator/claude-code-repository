"""
Scheduler Dispatch Ledger（v6.34.0、Release 6.34）

SchedulerDispatchLedger: stable event identityごとのdispatch記録の唯一の管理者

設計方針（docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md 8章）:
    - claim() / confirm() / reconcile_stale_claims()の3操作が本パッケージの安全性契約
      すべてを担う。write-once-forward-only（CLAIMED → CONFIRMED | RECOVERY_REQUIRED、
      いずれも終端）。
    - claim()：recordが存在しない場合のみCLAIMEDとして新規保存する。既存recordが
      あれば（phase不問）常にacknowledged=Falseを返す——これ1点で同一event_identityの
      二重claimが構造的に不可能になる（8.2章）。
    - confirm()：既存recordのphaseがCLAIMEDであることを要求する。TOCTOU残存window中に
      他driverの真に処理中のCLAIMED recordをreconciliationが誤ってRECOVERY_REQUIREDへ
      遷移させた場合でも、実際に処理していたdriverのconfirm()はここで単にFalseを返す
      だけであり、二重dispatchや状態の不整合な上書きには至らない（8.2章、8.4章）。
    - reconcile_stale_claims()：列挙→全件読み取り（1件でも失敗したら例外、書き込み
      ゼロ件）→個別record書き込み（per-recordロック取得後にfresh readで再確認して
      からのみRECOVERY_REQUIREDへ書き込む。fresh readがCLAIMED以外を示す場合は
      スキップ、retry_lineage_manager.py の _reconcile_all_locked() と同型のcontract）
      の順で処理する（8.5章(4)）。
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from .dispatch_ledger_entry import DispatchLedgerEntry
from .dispatch_phase import DispatchPhase
from .scheduler_dispatch_ledger_config import SchedulerDispatchLedgerConfig
from .scheduler_dispatch_ledger_results import ClaimResult, ReconcileSummary
from .scheduler_dispatch_ledger_store import SchedulerDispatchLedgerStore, SchedulerDispatchLedgerStoreReadError
from .scheduler_dispatch_ledger_store_lock import SchedulerDispatchLedgerStoreLock


class SchedulerDispatchLedgerReconcileError(Exception):
    """reconcile_stale_claims()が個別recordの読み取り・書き込みに失敗した場合に
    送出される例外。当該cycleでの新規dispatchを一切行わないためのfail-closed信号。"""


class SchedulerDispatchLedger:
    """stable event identityごとのdispatch記録の唯一の管理者。"""

    def __init__(self, store: SchedulerDispatchLedgerStore, config: SchedulerDispatchLedgerConfig):
        self._store = store
        self._config = config

    def _store_lock(self) -> SchedulerDispatchLedgerStoreLock:
        return SchedulerDispatchLedgerStoreLock(
            self._config.store_lock_path, timeout_seconds=self._config.store_lock_timeout_seconds,
        )

    def claim(self, event_identity: str, job_id: str, occurrence_minute: str) -> ClaimResult:
        with self._store_lock():
            try:
                existing = self._store.get(event_identity)
            except SchedulerDispatchLedgerStoreReadError as e:
                return ClaimResult(acknowledged=False, reason=f"store read failure: {e}")

            if existing is not None:
                return ClaimResult(
                    acknowledged=False,
                    reason=f"already exists (phase={existing.phase.value})",
                )

            now = datetime.now()
            entry = DispatchLedgerEntry(
                event_identity=event_identity,
                job_id=job_id,
                occurrence_minute=occurrence_minute,
                phase=DispatchPhase.CLAIMED,
                claimed_at=now,
                updated_at=now,
            )
            if not self._store.save(entry):
                return ClaimResult(acknowledged=False, reason="store write failure")
            return ClaimResult(acknowledged=True, reason=None)

    def confirm(self, event_identity: str, run_id: str | None, outcome_summary: str) -> bool:
        with self._store_lock():
            try:
                existing = self._store.get(event_identity)
            except SchedulerDispatchLedgerStoreReadError:
                return False

            if existing is None or existing.phase != DispatchPhase.CLAIMED:
                return False

            now = datetime.now()
            updated = replace(
                existing,
                phase=DispatchPhase.CONFIRMED,
                confirmed_at=now,
                dispatch_run_id=run_id,
                outcome_summary=outcome_summary,
                updated_at=now,
            )
            return self._store.save(updated)

    def reconcile_stale_claims(self) -> ReconcileSummary:
        # (a)(b) 列挙 + 全件読み取り。いずれかの失敗はSchedulerDispatchLedgerStoreReadError
        # がそのまま伝播する（呼び出し元へfail-closedで通知、書き込みはゼロ件）。
        all_entries = self._store.list_all()
        claimed_entries = [e for e in all_entries if e.phase == DispatchPhase.CLAIMED]

        recovery_marked = 0
        for entry in claimed_entries:
            with self._store_lock():
                try:
                    fresh = self._store.get(entry.event_identity)
                except SchedulerDispatchLedgerStoreReadError as e:
                    raise SchedulerDispatchLedgerReconcileError(
                        f"reconcile write phase read failure for {entry.event_identity}: {e}"
                    ) from e

                # fresh-read-under-lock契約（8.5章(4)(c)）：スナップショット取得後に
                # 他driverが正当にCONFIRMED等へ進めていた場合は上書きしない。
                if fresh is None or fresh.phase != DispatchPhase.CLAIMED:
                    continue

                now = datetime.now()
                updated = replace(fresh, phase=DispatchPhase.RECOVERY_REQUIRED, updated_at=now)
                if not self._store.save(updated):
                    raise SchedulerDispatchLedgerReconcileError(
                        f"reconcile write phase save failure for {entry.event_identity}"
                    )
                recovery_marked += 1

        return ReconcileSummary(recovery_marked=recovery_marked)

    def list_recovery_required(self) -> list[DispatchLedgerEntry]:
        """read-only診断用（20章 Manual Recovery Procedure）。"""
        all_entries = self._store.list_all()
        return [e for e in all_entries if e.phase == DispatchPhase.RECOVERY_REQUIRED]

    def peek(self, event_identity: str) -> DispatchLedgerEntry | None:
        """read-only診断用。読み取り失敗時はNoneを返す（安全性判断には使わない）。"""
        try:
            return self._store.get(event_identity)
        except SchedulerDispatchLedgerStoreReadError:
            return None
