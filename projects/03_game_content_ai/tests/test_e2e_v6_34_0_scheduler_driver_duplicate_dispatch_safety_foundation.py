"""
E2E テスト: v6.34.0 Scheduler Driver & Duplicate Dispatch Safety

テストシナリオ（docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md
23章 Test Strategy 対応、Codex `codex-readonly-review` Round 5 APPROVED版に準拠）:

    ── Stable Event Identity（7章） ──
    1.  build_event_identity()：同一job_id・同一分内は同一event_identityを導出する
    2.  build_event_identity()：異なるjob_id／異なる分では異なるevent_identityになる

    ── Dispatch Ledger 基本契約（8章） ──
    3.  claim()：recordなしはacknowledged=True
    4.  claim()：既存recordがあれば（phase不問）acknowledged=False（duplicate suppressionの核）
    5.  confirm()：phase==CLAIMEDのみ成功しCONFIRMEDへ遷移する
    6.  confirm()：phase不一致（CONFIRMED等）はFalseを返し書き込まない

    ── Fail-Closed Dispatch（10章） ──
    7.  claim()がacknowledged=Falseの場合、WorkflowEngineManager.run()が一切呼ばれない

    ── Duplicate Suppression — Restart / Same-minute（8・11.2章） ──
    8.  claim()→confirm()完了後、新規SchedulerDispatchLedgerインスタンスで同一
        event_identityをclaim()するとacknowledged=False（プロセス再起動を模擬）
    9.  同一cycle内で同一occurrenceを複数回claim()試行しても2回目以降はacknowledged=False

    ── Claim→Dispatch Crash / Reconciliation（11・8.5章(4)） ──
    10. claim()成功後confirm()を呼ばずにreconcile_stale_claims()を実行すると
        RECOVERY_REQUIREDへ遷移し、以後の再claim()もacknowledged=False
    11. fresh-read-under-lock契約：enumeration時点でCLAIMEDだったrecordが、
        per-recordロック取得後のfresh readでCONFIRMEDへ変化していた場合、
        RECOVERY_REQUIREDで上書きしない（スキップする）

    ── Second Driver Fail-Closed（12章） ──
    12. RetryRuntimeLockを先に取得した状態で2つ目の取得を試みると
        RetryRuntimeLockErrorが送出される

    ── Ownership-Integrity Self-Check / Lock Lifecycle Contract（12.1・12.2章） ──
    13. 自PIDと一致する場合は_verify_lock_ownership()がTrueを返す
    14. 別PIDへ書き換えると_verify_lock_ownership()がFalseを返す
    15. _release_if_owned()：ownership一致時はlock.release()が呼ばれファイルが削除される
    16. _release_if_owned()：ownership不一致時はreleaseをスキップしファイルが変更されない

    ── Retry-candidate除外（16章 Design Decision J） ──
    17. metadata["retry_candidate"]キーを持つeventはdispatch対象から除外される
    18. job_idがproduction_job_idsに含まれないeventは除外される（allowlist、二次防御）
    19. metadata["retry_candidate"]を持たない限り"retry:"prefixのjob_idでも
        allowlistに含まれれば対象に含まれる（allowlistがprefixを特別扱いしない）

    ── run_once() 統合・Exception containment（13・15章） ──
    20. .run()がExceptionを送出してもrun_once()全体が例外を伝播させず、
        他eventの処理・confirm()が継続する（outcome_summaryにEXCEPTION記録）
    21. .run()が正常完了した場合、confirm()にWorkflowEngineResult.run_idが伝播する
    22. run_once()冒頭のOwnership-Integrity Self-Checkが不一致の場合、
        reconcile/evaluate/claim/dispatchのいずれも実行されない

    ── Ledger Store I/O失敗（8.5章） ──
    23. 破損したrecordファイルに対しclaim()はacknowledged=False（読み取り不能≠不在）
    24. reconcile_stale_claims()の列挙不能時は例外が送出され0件処理

    ── Scheduler Driver / Retry Runtime 構造的非干渉（14章） ──
    25. 別々のlock pathは互いを妨げない（同時取得可能）

    ── run_workflow_engine.py Zero-Diff境界・R9 contract evidence（9.2章・25章R9） ──
    26. ProductionScheduleSource().jobs()の現在のcardinalityは1件
        （将来の変化を検知するcontract evidence。R9を将来見失わないための回帰検知）
    27. resolve_event()：--job-id手動経路は変更前と同一の挙動（Zero-Diff）
    28. resolve_event()：Scheduler経由はProductionScheduleSourceのJob定義を使う

    ── Store-level fail-closed強化（Codex Independent Code Review Round 1対応） ──
    29. [Blocking修正] store_dir自体が構築後に消失した場合、Store.get()は
        Noneではなく例外を送出し、claim()はacknowledged=Falseとなり
        二重dispatchを許さない（peek()は診断専用のためNoneを返す設計を維持）
    30. [Major修正] event_identityとjob_id/occurrence_minuteが不整合な
        recordは読み取り失敗として扱われる
    31. [Major修正] phaseフィールドの型不正（文字列でない）は読み取り失敗
        として扱われる
    32. [Blocking修正の追加検証、Codex Round 2対応] store_dirが削除ではなく
        通常ファイルに置き換わった場合も、os.stat()のstat.S_ISDIR()検査に
        より読み取り失敗として扱われる（Path.exists()ベースの判定はこの
        ケースを見逃しうる）
    33. [Major修正、Codex Round 4対応] _sanitize_event_identity()が単射
        （旧実装で衝突しえた入力が異なるファイル名になる）であること、
        および get()/list_all() がファイル名とrecord内容のevent_identity
        不整合を検出しfail-closedで扱うこと（多層防御）
    34. [Major修正、Codex Round 5対応] _sanitize_event_identity()の出力が
        ASCII英字を一切含まないこと（Windowsファイルシステムのcase-
        insensitivityに対しても単射性を維持するため）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_34_0_scheduler_driver_duplicate_dispatch_safety_foundation.py
"""
import importlib.util
import json
import os
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

results_log = []


def check(label: str, actual, expected):
    ok = actual == expected
    status = "PASS" if ok else "FAIL"
    results_log.append((status, label))
    mark = "OK" if ok else "NG"
    print(f"  [{mark}] {label}")
    if not ok:
        print(f"       期待値: {expected!r}")
        print(f"       実際値: {actual!r}")


def check_true(label: str, value: bool):
    check(label, value, True)


def check_false(label: str, value: bool):
    check(label, value, False)


print("=" * 60)
print("v6.34.0 Scheduler Driver & Duplicate Dispatch Safety E2E テスト")
print("=" * 60)
print()

from scheduler import SchedulerEvent, SchedulerJob, TriggerType
from scheduler_dispatch_ledger import (
    DispatchPhase,
    JsonSchedulerDispatchLedgerStore,
    SchedulerDispatchLedger,
    SchedulerDispatchLedgerConfig,
    SchedulerDispatchLedgerReconcileError,
    SchedulerDispatchLedgerStoreReadError,
)
from scheduler_dispatch_ledger.scheduler_dispatch_ledger_store import _SAFE_FILENAME_CHARS, _sanitize_event_identity
from scheduler_driver import (
    LockIntegrityViolationError,
    SchedulerDriverOrchestrator,
    _release_if_owned,
    _verify_lock_ownership,
    build_event_identity,
)
from scheduler_driver.scheduler_driver_dispatch_filter import _select_dispatchable_events
from scheduler_schedule_source import ProductionScheduleSource
from retry_runtime_lock import RetryRuntimeLock, RetryRuntimeLockError
from workflow_engine import SOURCE_SCHEDULER, CanonicalAdmissionFailure, WorkflowEngineEvent, WorkflowEngineResult


# ─── テスト用ユーティリティ ───

tmp_dirs: list[Path] = []


def make_ledger() -> tuple[SchedulerDispatchLedger, Path]:
    tmp_root = Path(tempfile.mkdtemp())
    tmp_dirs.append(tmp_root)
    config = SchedulerDispatchLedgerConfig(ledger_dir=tmp_root, store_lock_timeout_seconds=1.0)
    store = JsonSchedulerDispatchLedgerStore(config.store_dir)
    return SchedulerDispatchLedger(store=store, config=config), tmp_root


class FakeClockProvider:
    def __init__(self, now: datetime):
        self._now = now

    def now(self) -> datetime:
        return self._now


class FakeScheduleSource:
    def __init__(self, jobs: list[SchedulerJob]):
        self._jobs = jobs

    def jobs(self) -> list[SchedulerJob]:
        return self._jobs


class FakeSchedulerEngine:
    """SchedulerEngine.evaluate()と同一シグネチャを持つFake。job_idと現在時刻から
    テスト用のSchedulerEventを合成するだけで、実際のtrigger_type判定は行わない。"""

    def __init__(self, extra_events: list[SchedulerEvent] | None = None):
        self._extra_events = extra_events or []

    def evaluate(self, jobs: list[SchedulerJob], now: datetime) -> list[SchedulerEvent]:
        events = [
            SchedulerEvent(job_id=job.job_id, execute_time=now, trigger_reason="test matched", metadata=dict(job.metadata))
            for job in jobs
        ]
        return events + list(self._extra_events)


@dataclass
class FakeWorkflowEngineManager:
    """WorkflowEngineManager.run()と同一シグネチャを持つFake。呼び出し履歴を記録する。"""

    calls: list[WorkflowEngineEvent] = field(default_factory=list)
    result_to_return: WorkflowEngineResult | None = None
    exception_to_raise: Exception | None = None

    def run(self, event: WorkflowEngineEvent, dry_run: bool = False, **kwargs) -> WorkflowEngineResult | None:
        self.calls.append(event)
        if self.exception_to_raise is not None:
            raise self.exception_to_raise
        return self.result_to_return


def make_engine_result(run_id: str = "run-x", overall_success: bool = True) -> WorkflowEngineResult:
    now = datetime.now()
    return WorkflowEngineResult(
        run_id=run_id, steps=[], overall_success=overall_success, stopped_early=False,
        started_at=now, finished_at=now,
    )


class _StaleSnapshotStore:
    """list_all()は初回呼び出し時点のスナップショットを返し続け、get()/save()は
    実storeへ委譲するテスト用ラッパー。reconciliationのfresh-read-under-lock契約
    （enumeration後にrecordが変化するレース）を再現するために使う。"""

    def __init__(self, real_store):
        self._real = real_store
        self._snapshot = None

    def list_all(self):
        if self._snapshot is None:
            self._snapshot = self._real.list_all()
        return self._snapshot

    def get(self, event_identity):
        return self._real.get(event_identity)

    def save(self, entry) -> bool:
        return self._real.save(entry)


class _EnumerationFailingStore:
    def list_all(self):
        raise SchedulerDispatchLedgerStoreReadError("simulated enumeration failure")

    def get(self, event_identity):
        return None

    def save(self, entry) -> bool:
        return True


NOW = datetime(2026, 9, 16, 9, 0, 30)


# ═══════════════════════════════════════════════════════════
# テスト1-2: Stable Event Identity
# ═══════════════════════════════════════════════════════════
print("[テスト1-2] build_event_identity()")

id_a, occ_a = build_event_identity("job-x", datetime(2026, 9, 16, 9, 0, 5))
id_b, occ_b = build_event_identity("job-x", datetime(2026, 9, 16, 9, 0, 55))
check("1. 同一分内（秒違い）は同一event_identity", id_a, id_b)
check("1. 同一分内は同一occurrence_minute", occ_a, occ_b)

id_c, _ = build_event_identity("job-y", datetime(2026, 9, 16, 9, 0, 5))
id_d, _ = build_event_identity("job-x", datetime(2026, 9, 16, 9, 1, 5))
check_true("2. 異なるjob_idは異なるevent_identity", id_a != id_c)
check_true("2. 異なる分は異なるevent_identity", id_a != id_d)
print()


# ═══════════════════════════════════════════════════════════
# テスト3-6: Dispatch Ledger 基本契約
# ═══════════════════════════════════════════════════════════
print("[テスト3-6] SchedulerDispatchLedger.claim() / confirm()")

ledger_36, _ = make_ledger()
r3 = ledger_36.claim("job-a::2026-09-16T09:00", "job-a", "2026-09-16T09:00")
check_true("3. claim(): recordなしはacknowledged=True", r3.acknowledged)

r4 = ledger_36.claim("job-a::2026-09-16T09:00", "job-a", "2026-09-16T09:00")
check_false("4. claim(): 既存recordありはacknowledged=False", r4.acknowledged)

c5 = ledger_36.confirm("job-a::2026-09-16T09:00", "run-1", "overall_success=True")
check_true("5. confirm(): phase==CLAIMEDは成功", c5)
check("5. confirm()後のphaseはCONFIRMED", ledger_36.peek("job-a::2026-09-16T09:00").phase, DispatchPhase.CONFIRMED)

c6 = ledger_36.confirm("job-a::2026-09-16T09:00", "run-2", "overall_success=True")
check_false("6. confirm(): phase不一致（既にCONFIRMED）はFalse", c6)
print()


# ═══════════════════════════════════════════════════════════
# テスト7: Fail-Closed Dispatch
# ═══════════════════════════════════════════════════════════
print("[テスト7] Fail-Closed Dispatch")

ledger_7, _ = make_ledger()
ledger_7.claim("job-a::2026-09-16T09:00", "job-a", "2026-09-16T09:00")  # 先に埋める

fake_manager_7 = FakeWorkflowEngineManager(result_to_return=make_engine_result())
job_7 = SchedulerJob(job_id="job-a", name="job-a", trigger_type=TriggerType.DAILY, schedule="09:00")
orchestrator_7 = SchedulerDriverOrchestrator(
    scheduler_engine=FakeSchedulerEngine(),
    schedule_source=FakeScheduleSource([job_7]),
    ledger=ledger_7,
    workflow_engine_manager=fake_manager_7,
    lock_path=Path("unused"),
    own_pid=os.getpid(),
    clock=FakeClockProvider(NOW),
)
# lock_pathが存在しない場合_verify_lock_ownershipはFalseになるため、直接_dispatch_one()を検証する
event_7 = SchedulerEvent(job_id="job-a", execute_time=NOW, trigger_reason="test", metadata={})
outcome_7 = orchestrator_7._dispatch_one(event_7)
check_false("7. claim失敗時はdispatched=False", outcome_7.dispatched)
check("7. claim失敗時はWorkflowEngineManager.run()が呼ばれない", len(fake_manager_7.calls), 0)
print()


# ═══════════════════════════════════════════════════════════
# テスト8-9: Duplicate Suppression（Restart / Same-minute）
# ═══════════════════════════════════════════════════════════
print("[テスト8-9] Duplicate Suppression")

ledger_8a, tmp_8 = make_ledger()
ledger_8a.claim("job-a::2026-09-16T09:00", "job-a", "2026-09-16T09:00")
ledger_8a.confirm("job-a::2026-09-16T09:00", "run-1", "overall_success=True")

# プロセス再起動を模擬：同一tmp_dirに対する新規SchedulerDispatchLedgerインスタンス
config_8b = SchedulerDispatchLedgerConfig(ledger_dir=tmp_8, store_lock_timeout_seconds=1.0)
ledger_8b = SchedulerDispatchLedger(store=JsonSchedulerDispatchLedgerStore(config_8b.store_dir), config=config_8b)
r8 = ledger_8b.claim("job-a::2026-09-16T09:00", "job-a", "2026-09-16T09:00")
check_false("8. 再起動後の同一event_identityへのclaim()はacknowledged=False", r8.acknowledged)

ledger_9, _ = make_ledger()
r9a = ledger_9.claim("job-b::2026-09-16T09:00", "job-b", "2026-09-16T09:00")
r9b = ledger_9.claim("job-b::2026-09-16T09:00", "job-b", "2026-09-16T09:00")
check_true("9. 同一cycle内1回目のclaim()はacknowledged=True", r9a.acknowledged)
check_false("9. 同一cycle内2回目のclaim()はacknowledged=False", r9b.acknowledged)
print()


# ═══════════════════════════════════════════════════════════
# テスト10-11: Claim→Dispatch Crash / Reconciliation
# ═══════════════════════════════════════════════════════════
print("[テスト10] reconcile_stale_claims(): confirm()未到達のCLAIMEDはRECOVERY_REQUIREDへ")

ledger_10, _ = make_ledger()
ledger_10.claim("job-a::2026-09-16T09:00", "job-a", "2026-09-16T09:00")
# confirm()を呼ばずにクラッシュを模擬
summary_10 = ledger_10.reconcile_stale_claims()
check("10. reconcile: recovery_marked=1", summary_10.recovery_marked, 1)
check("10. entryはRECOVERY_REQUIREDへ遷移", ledger_10.peek("job-a::2026-09-16T09:00").phase, DispatchPhase.RECOVERY_REQUIRED)
r10_reclaim = ledger_10.claim("job-a::2026-09-16T09:00", "job-a", "2026-09-16T09:00")
check_false("10. RECOVERY_REQUIRED後の再claim()はacknowledged=False（自動再dispatchなし）", r10_reclaim.acknowledged)
print()

print("[テスト11] fresh-read-under-lock契約")

ledger_11, _ = make_ledger()
ledger_11.claim("job-a::2026-09-16T09:00", "job-a", "2026-09-16T09:00")
real_store_11 = ledger_11._store
stale_store_11 = _StaleSnapshotStore(real_store_11)
ledger_11._store = stale_store_11
# enumerationスナップショットを確定させる（CLAIMEDとして記録）
_ = stale_store_11.list_all()
# 別driverが正当にCONFIRMEDまで進めた状況を模擬（実storeを直接更新）
ledger_11._store = real_store_11
ledger_11.confirm("job-a::2026-09-16T09:00", "run-1", "overall_success=True")
ledger_11._store = stale_store_11

summary_11 = ledger_11.reconcile_stale_claims()
check("11. fresh readがCONFIRMEDを検出しRECOVERY_REQUIREDへ上書きしない: recovery_marked=0", summary_11.recovery_marked, 0)
ledger_11._store = real_store_11
check("11. entryはCONFIRMEDのまま保持される", ledger_11.peek("job-a::2026-09-16T09:00").phase, DispatchPhase.CONFIRMED)
print()


# ═══════════════════════════════════════════════════════════
# テスト12: Second Driver Fail-Closed
# ═══════════════════════════════════════════════════════════
print("[テスト12] Second Driver Fail-Closed（RetryRuntimeLock再利用）")

tmp_lock_dir = Path(tempfile.mkdtemp())
tmp_dirs.append(tmp_lock_dir)
lock_path_12 = tmp_lock_dir / "scheduler_driver.lock"
lock_a_12 = RetryRuntimeLock(lock_path=lock_path_12)
lock_a_12.acquire()
threw_12 = False
try:
    lock_b_12 = RetryRuntimeLock(lock_path=lock_path_12)
    lock_b_12.acquire()
except RetryRuntimeLockError:
    threw_12 = True
check_true("12. 2つ目のRetryRuntimeLock.acquire()はRetryRuntimeLockErrorを送出", threw_12)
lock_a_12.release()
print()


# ═══════════════════════════════════════════════════════════
# テスト13-16: Ownership-Integrity Self-Check / Lock Lifecycle Contract
# ═══════════════════════════════════════════════════════════
print("[テスト13-16] Ownership-Integrity Self-Check / Lock Lifecycle Contract")

tmp_lock_dir2 = Path(tempfile.mkdtemp())
tmp_dirs.append(tmp_lock_dir2)
lock_path_13 = tmp_lock_dir2 / "scheduler_driver.lock"
lock_13 = RetryRuntimeLock(lock_path=lock_path_13)
lock_13.acquire()
own_pid_13 = os.getpid()

check_true("13. 自PIDと一致する場合はTrue", _verify_lock_ownership(lock_path_13, own_pid_13))

lock_path_13.write_text("999999999", encoding="utf-8")
check_false("14. 別PIDへ書き換えるとFalse", _verify_lock_ownership(lock_path_13, own_pid_13))

# 15: ownership一致時はrelease()が呼ばれファイルが削除される
lock_path_13.write_text(str(own_pid_13), encoding="utf-8")
_release_if_owned(lock_13, own_pid_13)
check_false("15. ownership一致時: releaseされファイルが削除される", lock_path_13.exists())

# 16: ownership不一致時はreleaseがスキップされファイルが残る
lock_15b = RetryRuntimeLock(lock_path=lock_path_13)
lock_15b.acquire()
lock_path_13.write_text("999999999", encoding="utf-8")
_release_if_owned(lock_15b, own_pid_13)
check_true("16. ownership不一致時: releaseがスキップされファイルが残存する", lock_path_13.exists())
lock_path_13.unlink(missing_ok=True)
print()


# ═══════════════════════════════════════════════════════════
# テスト17-19: Retry-candidate除外（Design Decision J）
# ═══════════════════════════════════════════════════════════
print("[テスト17-19] Retry-candidate除外契約")

production_job_ids_17 = frozenset({"job-a", "job-b"})
retry_event_17 = SchedulerEvent(job_id="job-a", execute_time=NOW, trigger_reason="retry", metadata={"retry_candidate": object()})
selected_17 = _select_dispatchable_events([retry_event_17], production_job_ids_17)
check("17. metadata['retry_candidate']を持つeventは除外される", len(selected_17), 0)

nonproduction_event_18 = SchedulerEvent(job_id="unknown-job", execute_time=NOW, trigger_reason="x", metadata={})
selected_18 = _select_dispatchable_events([nonproduction_event_18], production_job_ids_17)
check("18. production_job_idsに含まれないeventは除外される（allowlist）", len(selected_18), 0)

prefixed_but_allowed_19 = SchedulerEvent(job_id="retry:something", execute_time=NOW, trigger_reason="x", metadata={})
production_job_ids_19 = frozenset({"retry:something"})
selected_19 = _select_dispatchable_events([prefixed_but_allowed_19], production_job_ids_19)
check(
    "19. 'retry:'prefixでもmetadataキーがなくallowlistに含まれれば対象に含まれる",
    len(selected_19), 1,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト20-22: run_once() 統合・Exception containment
# ═══════════════════════════════════════════════════════════
print("[テスト20-22] run_once() 統合")

job_20 = SchedulerJob(job_id="job-exc", name="job-exc", trigger_type=TriggerType.DAILY, schedule="09:00")
job_20b = SchedulerJob(job_id="job-ok", name="job-ok", trigger_type=TriggerType.DAILY, schedule="09:00")
ledger_20, _ = make_ledger()


class _MultiOutcomeManager:
    def __init__(self):
        self.calls = []

    def run(self, event, dry_run=False, **kwargs):
        self.calls.append(event)
        if event.job_id == "job-exc":
            raise CanonicalAdmissionFailure(run_id="run-exc-1", reason="START_RUN_ACK_FAILED")
        return make_engine_result(run_id="run-ok-1", overall_success=True)


manager_20 = _MultiOutcomeManager()
lock_path_20 = Path(tempfile.mkdtemp()) / "scheduler_driver.lock"
tmp_dirs.append(lock_path_20.parent)
lock_20 = RetryRuntimeLock(lock_path=lock_path_20)
lock_20.acquire()
own_pid_20 = os.getpid()

orchestrator_20 = SchedulerDriverOrchestrator(
    scheduler_engine=FakeSchedulerEngine(),
    schedule_source=FakeScheduleSource([job_20, job_20b]),
    ledger=ledger_20,
    workflow_engine_manager=manager_20,
    lock_path=lock_path_20,
    own_pid=own_pid_20,
    clock=FakeClockProvider(NOW),
)
result_20 = orchestrator_20.run_once()
check("20. run_once()は例外を伝播させず両方のeventを処理する", len(manager_20.calls), 2)
check("20. dispatched件数は2件（例外側もdispatched=Trueとして記録）", len(result_20.dispatched), 2)

exc_identity_20, _ = build_event_identity("job-exc", NOW)
entry_20 = ledger_20.peek(exc_identity_20)
check("20. Exception側のconfirm()結果はoutcome_summaryにEXCEPTIONを含む", "EXCEPTION" in (entry_20.outcome_summary or ""), True)
check("21. Exception側のdispatch_run_idはCanonicalAdmissionFailure.run_idから伝播する", entry_20.dispatch_run_id, "run-exc-1")

ok_identity_20, _ = build_event_identity("job-ok", NOW)
entry_20b = ledger_20.peek(ok_identity_20)
check("21. 正常完了側のdispatch_run_idはWorkflowEngineResult.run_idから伝播する", entry_20b.dispatch_run_id, "run-ok-1")
check("21. 正常完了側はphase==CONFIRMED", entry_20b.phase, DispatchPhase.CONFIRMED)

lock_path_20.write_text("999999999", encoding="utf-8")
threw_22 = False
try:
    orchestrator_20.run_once()
except LockIntegrityViolationError:
    threw_22 = True
check_true("22. ownership不一致時はrun_once()冒頭でLockIntegrityViolationErrorを送出", threw_22)
check("22. ownership不一致時は新規dispatchが発生しない（callsは変化しない）", len(manager_20.calls), 2)
lock_20.release()
print()


# ═══════════════════════════════════════════════════════════
# テスト23-24: Ledger Store I/O失敗
# ═══════════════════════════════════════════════════════════
print("[テスト23-24] Ledger Store I/O失敗")

ledger_23, tmp_23 = make_ledger()
ledger_23.claim("job-a::2026-09-16T09:00", "job-a", "2026-09-16T09:00")
# recordファイルを直接破損させる
broken_path = tmp_23 / "entries" / f"{_sanitize_event_identity('job-a::2026-09-16T09:00')}.json"
broken_path.write_text("{not valid json", encoding="utf-8")
r23 = ledger_23.claim("job-a::2026-09-16T09:00", "job-a", "2026-09-16T09:00")
check_false("23. 破損recordへのclaim()はacknowledged=False（読めない≠存在しない）", r23.acknowledged)

ledger_24, _ = make_ledger()
ledger_24._store = _EnumerationFailingStore()
threw_24 = False
try:
    ledger_24.reconcile_stale_claims()
except SchedulerDispatchLedgerStoreReadError:
    threw_24 = True
check_true("24. 列挙不能時はSchedulerDispatchLedgerStoreReadErrorが送出される", threw_24)
print()


# ═══════════════════════════════════════════════════════════
# テスト25: Scheduler Driver / Retry Runtime 構造的非干渉
# ═══════════════════════════════════════════════════════════
print("[テスト25] Scheduler Driver / Retry Runtime 構造的非干渉")

tmp_lock_dir3 = Path(tempfile.mkdtemp())
tmp_dirs.append(tmp_lock_dir3)
scheduler_lock_path = tmp_lock_dir3 / "scheduler_driver.lock"
retry_lock_path = tmp_lock_dir3 / "retry_runtime.lock"
scheduler_lock = RetryRuntimeLock(lock_path=scheduler_lock_path)
retry_lock = RetryRuntimeLock(lock_path=retry_lock_path)
scheduler_lock.acquire()
no_interference = True
try:
    retry_lock.acquire()
except RetryRuntimeLockError:
    no_interference = False
check_true("25. 別々のlock pathは互いを妨げず同時取得できる", no_interference)
scheduler_lock.release()
retry_lock.release()
print()


# ═══════════════════════════════════════════════════════════
# テスト26-28: run_workflow_engine.py Zero-Diff境界・R9 contract evidence
# ═══════════════════════════════════════════════════════════
print("[テスト26-28] run_workflow_engine.py 整合性・R9 contract evidence")

production_jobs_26 = ProductionScheduleSource().jobs()
check(
    "26. [R9 contract evidence] ProductionScheduleSource().jobs()の現在のcardinalityは1件"
    "（変化した場合はrun_workflow_engine.pyのevents[0]専用ロジックの再検討が必要、25章R9）",
    len(production_jobs_26), 1,
)
check("26. [R9 contract evidence] 唯一のJobはDAILY trigger", production_jobs_26[0].trigger_type, TriggerType.DAILY)

spec = importlib.util.spec_from_file_location(
    "run_workflow_engine_under_test", PROJECT_ROOT / "scripts" / "run_workflow_engine.py",
)
run_workflow_engine_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_workflow_engine_mod)


class _Args:
    def __init__(self, job_id=None):
        self.job_id = job_id


event_27 = run_workflow_engine_mod.resolve_event(_Args(job_id="manual-test-27"))
check_true("27. --job-id手動経路は従来通りWorkflowEngineEventを直接構築する", event_27 is not None)
check("27. --job-id手動経路のjob_idは指定値のまま", event_27.job_id, "manual-test-27")
check("27. --job-id手動経路のsourceはSOURCE_MANUAL", event_27.source, "manual")

event_28 = run_workflow_engine_mod.resolve_event(_Args(job_id=None))
if event_28 is not None:
    check("28. Scheduler経由のjob_idはProductionScheduleSourceのjob_idと一致する", event_28.job_id, production_jobs_26[0].job_id)
    check("28. Scheduler経由のsourceはSOURCE_SCHEDULER", event_28.source, SOURCE_SCHEDULER)
else:
    # 現在時刻がJobスケジュールと一致しない場合はNoneが正しい（既存挙動どおり）。
    check("28. スケジュール不一致時はNoneを返す（既存挙動維持）", event_28, None)
print()


# ═══════════════════════════════════════════════════════════
# テスト29-31: Codex Independent Code Review Round 1対応の直接回帰テスト
# ═══════════════════════════════════════════════════════════
print("[テスト29-31] Store-level fail-closed強化（Codex Round 1 Blocking/Major対応）")

ledger_29, tmp_29 = make_ledger()
ledger_29.claim("job-a::2026-09-16T09:00", "job-a", "2026-09-16T09:00")
# store_dir自体を構築後に消失させる（ディスク破損・誤削除等を模擬）。
shutil.rmtree(tmp_29 / "entries")
check("29a. store_dir消失後のpeek()はNoneを返す（診断専用、安全性には使わない）", ledger_29.peek("job-a::2026-09-16T09:00"), None)

threw_29b = False
try:
    ledger_29._store.get("job-a::2026-09-16T09:00")
except SchedulerDispatchLedgerStoreReadError:
    threw_29b = True
check_true(
    "29b. [Blocking修正] store_dir消失後、Store.get()はNoneではなくSchedulerDispatchLedgerStoreReadErrorを送出する"
    "（recordなし、と誤認して二重claim()を許してしまう経路を閉じる）",
    threw_29b,
)

r29c = ledger_29.claim("job-a::2026-09-16T09:00", "job-a", "2026-09-16T09:00")
check_false(
    "29c. [Blocking修正] store_dir消失後のclaim()は（Ledger層がread failureをcatchし）acknowledged=False"
    "であり、既にCLAIMED済みだった occurrence を二重dispatchしない",
    r29c.acknowledged,
)

ledger_30, tmp_30 = make_ledger()
ledger_30.claim("job-b::2026-09-16T09:00", "job-b", "2026-09-16T09:00")
tampered_path = tmp_30 / "entries" / f"{_sanitize_event_identity('job-b::2026-09-16T09:00')}.json"
tampered_data = {
    "event_identity": "job-b::2026-09-16T09:00",
    "job_id": "job-c",  # event_identityと不整合な値へ改ざん
    "occurrence_minute": "2026-09-16T09:00",
    "phase": "claimed",
    "claimed_at": datetime.now().isoformat(),
    "confirmed_at": None,
    "dispatch_run_id": None,
    "outcome_summary": None,
    "detail": None,
    "updated_at": datetime.now().isoformat(),
}
tampered_path.write_text(json.dumps(tampered_data), encoding="utf-8")
threw_30 = False
try:
    ledger_30._store.get("job-b::2026-09-16T09:00")
except SchedulerDispatchLedgerStoreReadError:
    threw_30 = True
check_true(
    "30. [Major修正] event_identityとjob_id/occurrence_minuteが不整合なrecordは読み取り失敗として扱われる",
    threw_30,
)

ledger_31, tmp_31 = make_ledger()
ledger_31.claim("job-d::2026-09-16T09:00", "job-d", "2026-09-16T09:00")
wrong_type_path = tmp_31 / "entries" / f"{_sanitize_event_identity('job-d::2026-09-16T09:00')}.json"
wrong_type_data = dict(tampered_data)
wrong_type_data["job_id"] = "job-d"
wrong_type_data["event_identity"] = "job-d::2026-09-16T09:00"
wrong_type_data["phase"] = 12345  # 型不正（文字列でない）
wrong_type_path.write_text(json.dumps(wrong_type_data), encoding="utf-8")
threw_31 = False
try:
    ledger_31._store.get("job-d::2026-09-16T09:00")
except SchedulerDispatchLedgerStoreReadError:
    threw_31 = True
check_true("31. [Major修正] phaseフィールドの型不正（文字列でない）は読み取り失敗として扱われる", threw_31)

# 32: store_dirが（削除ではなく）通常ファイルに置き換わったケース（Codex Round 2 SUGGESTIONS対応）。
# Path.exists()ベースの判定はこのケースでもTrueを返してしまい得るため
# （パスは"存在する"が、ディレクトリではない）、os.stat()のstat.S_ISDIR()検査が
# 正しく機能することを直接確認する。
ledger_32, tmp_32 = make_ledger()
ledger_32.claim("job-e::2026-09-16T09:00", "job-e", "2026-09-16T09:00")
entries_dir_32 = tmp_32 / "entries"
shutil.rmtree(entries_dir_32)
entries_dir_32.write_text("this is now a regular file, not a directory", encoding="utf-8")
threw_32 = False
try:
    ledger_32._store.get("job-e::2026-09-16T09:00")
except SchedulerDispatchLedgerStoreReadError:
    threw_32 = True
check_true(
    "32. [Blocking修正の追加検証] store_dirが通常ファイルに置き換わった場合もSchedulerDispatchLedgerStoreReadErrorを送出する"
    "（os.stat()のstat.S_ISDIR()検査、Path.exists()の“パスは存在する”という判定に依拠しない）",
    threw_32,
)

# 33: [Major修正、Codex Round 4対応] _sanitize_event_identity()の単射性と、
# get()/list_all()のfilename/event_identityクロスチェック。
sanitized_colon_33 = _sanitize_event_identity("job-x::2026-09-16T09:00")
sanitized_dash_33 = _sanitize_event_identity("job-x--2026-09-16T09-00")
check_true(
    "33a. [単射性] 旧実装では衝突しえた「':'を含む識別子」と「既に'-'を含む識別子」が異なるsanitized文字列になる",
    sanitized_colon_33 != sanitized_dash_33,
)

ledger_33, tmp_33 = make_ledger()
ledger_33.claim("job-f::2026-09-16T09:00", "job-f", "2026-09-16T09:00")
forged_path_33 = tmp_33 / "entries" / f"{_sanitize_event_identity('job-f::2026-09-16T09:00')}.json"
forged_data_33 = {
    "event_identity": "job-g::2026-09-16T09:00",  # ファイル名（job-f由来）とわざと不整合にする
    "job_id": "job-g",
    "occurrence_minute": "2026-09-16T09:00",
    "phase": "claimed",
    "claimed_at": datetime.now().isoformat(),
    "confirmed_at": None,
    "dispatch_run_id": None,
    "outcome_summary": None,
    "detail": None,
    "updated_at": datetime.now().isoformat(),
}
forged_path_33.write_text(json.dumps(forged_data_33), encoding="utf-8")
threw_33b = False
try:
    ledger_33._store.get("job-f::2026-09-16T09:00")
except SchedulerDispatchLedgerStoreReadError:
    threw_33b = True
check_true(
    "33b. [多層防御] get()はファイル名（要求されたevent_identity由来）とrecord内容の"
    "event_identityが不整合な場合に読み取り失敗として扱う（誤ったrecordを正当な結果として返さない）",
    threw_33b,
)
threw_33c = False
try:
    ledger_33._store.list_all()
except SchedulerDispatchLedgerStoreReadError:
    threw_33c = True
check_true(
    "33c. [多層防御] list_all()でも同様にfilename/event_identity不整合を検出する",
    threw_33c,
)

# 34: [Major修正、Codex Round 5対応] Windowsファイルシステムのcase-insensitivityに
# 対しても単射性を維持すること（sanitized出力がASCII英字を一切含まないことで保証する）。
sanitized_upper_34 = _sanitize_event_identity("Job::2026-09-16T09:00")
sanitized_lower_34 = _sanitize_event_identity("job::2026-09-16T09:00")
check_true(
    "34a. [case-insensitive安全性] 大文字小文字のみ異なる識別子は、大文字小文字を"
    "区別しないファイルシステム上でも異なるファイル名になる（sanitized出力を"
    "小文字化しても両者は一致しない）",
    sanitized_upper_34.lower() != sanitized_lower_34.lower(),
)
# 34b: 安全文字集合（リテラル通過を許す文字）そのものに英字が含まれないことを
# 直接確認する（"~4A"等のhexエスケープ表現自体にA-Fの文字が出現するのは
# 正常であり問題ではない——重要なのは「元の入力の英字がリテラルのまま
# 通過することはなく、常に自分自身のコードが決定的にuppercaseで生成する
# hexエスケープを経由する」という性質そのものであるため、安全文字集合の
# 定義を直接検査する）。
check_true(
    "34b. [case-insensitive安全性] 安全文字集合（リテラル通過対象）が数字・'_'・'.'のみである"
    "（元の英字がリテラルのまま通過する経路が存在しないことの直接確認。"
    "'~4A'等のhexエスケープ表現自体がA-Fを含むのは正常であり別物）",
    _SAFE_FILENAME_CHARS == frozenset("0123456789_."),
)
print()


# ─── 後片付け ───
for d in tmp_dirs:
    shutil.rmtree(d, ignore_errors=True)


# ─── 結果サマリー ───
print("=" * 60)
total = len(results_log)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = total - passed
print(f"合計: {passed}/{total} PASS  /  {failed} FAIL")
print("=" * 60)

if failed > 0:
    print()
    print("FAILしたテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
else:
    print("全テスト PASS")
