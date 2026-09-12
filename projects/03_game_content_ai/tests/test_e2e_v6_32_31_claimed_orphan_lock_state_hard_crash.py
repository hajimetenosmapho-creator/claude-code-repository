"""
E2E テスト: Release 6.32 — CLAIMED Orphan Lock-State Matrix & Hard-Crash
Durability Closure（§18 test#22 + test#25）

Source of Truth: docs/design/
side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md
（Approved Architecture Amendment、Round 10 APPROVED）
§9.2a（mark_execution_started()臨界区間のlock構造・crash境界ごとの残存
lock/durable state matrix）・§9.3（recovery chain）・§18 test#22（CLAIMED
orphan回収のfull chain、B0〜B4個別証明）・test#25（Hard-Crash Test
Methodology、Category A/B分離）

本テストは、test_e2e_v6_32_27（representative caseのみ・実crashなし）を
補完し、以下を「いずれか」で代表させず個別に直接証明する：

    1. B0・B1・B2・B3各境界で、mark_execution_started()の実行を実際の
       別プロセス（child process）でos._exit()によるhard terminationにより
       中断させ（Category B、通常のmock例外ではwith文の__exit__が必ず
       呼ばれてしまい残存lockを正しく検証できないため）、親プロセスから
       残存lock（RetryExecutionLock / RetryLineageStoreLock / Manifest
       attempt lock）・durable manifest state・durable lineage phaseを
       §9.2aの表と直接照合する。
    2. reconcile_all()のactual public behavior：RetryExecutionLock競合時は
       ReconcileSummary(skipped=True)という通常の戻り値（例外として
       伝播しない）、RetryLineageStoreLock残存時は
       RetryLineageStoreLockErrorが catchされない生の例外として伝播する
       （既存6.31由来の非対称性、§9.2a）ことを直接確認する。
    3. 残存する全lockの手動削除（旧holder processの終了をsubprocess.wait()
       で確認済みの場合のみ実行する既存運用手順）後、reconcile_all()に
       よるCLAIMED orphan回収 → READY_ELIGIBLE → 後続claim() →
       新しいmember_run_idによる新しいmanifest generation（孤児manifestの
       非再利用・共存）までを実チェーンで確認する。

production code（RetryLineageManager・各種lock・ProtectedOperation
ManifestStore等）は一切変更しない。read-onlyでの実コード確認結果に基づき、
テストのみを追加する。isolated temp directory以外のfilesystem状態には
一切触れない。network / WordPress / 外部I/O = 0。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_31_claimed_orphan_lock_state_hard_crash.py
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

WORKER_SCRIPT = Path(__file__).parent / "hard_crash_worker_v6_32_31.py"

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
    check(label, bool(value), True)


def check_false(label: str, value: bool):
    check(label, bool(value), False)


print("=" * 70)
print("CLAIMED Orphan Lock-State Matrix & Hard-Crash Durability — E2E テスト")
print("=" * 70)
print()

from protected_operation_manifest import (
    JsonProtectedOperationManifestStore,
    build_protected_operation_manifest_store_lock,
)
from retry_lineage import (
    JsonRetryLineageStore,
    RetryLineageConfig,
    RetryLineageManager,
    RetryLineagePhase,
    RetryLineageStoreLockError,
)
from workflow_monitor import WorkflowMonitorStatus

tmp_dirs: list[Path] = []


class _FixedPolicy:
    target_statuses = frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT})

    @property
    def max_attempts(self) -> int:
        return 5

    def should_retry(self, monitor_status, attempt: int) -> bool:
        return monitor_status in self.target_statuses and attempt < self.max_attempts


def run_worker(boundary: str, tmp_root: Path, root_run_id: str, member_run_id: str) -> int:
    """§9.2aの指定境界で実際にhard crashするchild processを起動し、その
    returncodeを返す（親プロセス自体は生存し続ける、test#25 Category B契約）。"""
    proc = subprocess.run(
        [sys.executable, str(WORKER_SCRIPT), boundary, str(tmp_root), root_run_id, member_run_id],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
    )
    if proc.returncode not in (1, 2, 3, 4):
        print(f"       [worker stdout] {proc.stdout}")
        print(f"       [worker stderr] {proc.stderr}")
    return proc.returncode


# §9.2a matrixの期待値（境界ごと）。
EXPECTED_MATRIX = {
    # boundary: (execution_lock残存, store_lock残存, manifest_lock残存, durable_manifest_exists)
    "B0": (True, False, False, False),
    "B1": (True, True, False, False),
    "B2": (True, True, True, False),
    "B3": (True, True, True, True),
    "B4": (True, True, False, True),
}

for boundary, (expect_exec_lock, expect_store_lock, expect_manifest_lock, expect_manifest_exists) in EXPECTED_MATRIX.items():
    print(f"[{boundary}] §9.2a boundary evidence")

    tmp_root = Path(tempfile.mkdtemp(prefix=f"v6_32_31_{boundary}_"))
    tmp_dirs.append(tmp_root)
    root_run_id = f"root-{boundary}-{uuid.uuid4().hex[:8]}"
    member_run_id = f"exec-{boundary}-{uuid.uuid4().hex[:8]}"

    lineage_config = RetryLineageConfig(enabled=True, lineage_dir=tmp_root / "lineage")
    lineage_store = JsonRetryLineageStore(lineage_config.store_dir)
    manifest_store = JsonProtectedOperationManifestStore(base_dir=tmp_root / "manifest")
    manifest_lock_path = build_protected_operation_manifest_store_lock(
        tmp_root / "manifest" / ".locks", root_run_id, 1, member_run_id,
    ).lock_path

    # --- (1) 実際のhard crash（別プロセス、os._exit()） -----------------
    returncode = run_worker(boundary, tmp_root, root_run_id, member_run_id)
    check(f"{boundary}-1. workerはos._exit(1)でhard terminationした（親processは生存）", returncode, 1)

    # --- (2) 残存lock・durable stateをexact matrixとして照合 ------------
    check(f"{boundary}-2a. RetryExecutionLock残存", lineage_config.execution_lock_path.exists(), expect_exec_lock)
    check(f"{boundary}-2b. RetryLineageStoreLock残存", lineage_config.store_lock_path.exists(), expect_store_lock)
    check(f"{boundary}-2c. Manifest attempt lock残存", manifest_lock_path.exists(), expect_manifest_lock)

    durable_manifest = manifest_store._read_raw(root_run_id, 1, member_run_id)
    check(f"{boundary}-2d. durable manifest existence", durable_manifest is not None, expect_manifest_exists)
    if durable_manifest is not None:
        check(f"{boundary}-2e. durable manifestはentries=()のまま（atomic write完了直後）", durable_manifest.entries, ())

    lineage_readonly = RetryLineageManager(store=lineage_store, config=lineage_config, policy=_FixedPolicy(), manifest=manifest_store)
    record_after_crash = lineage_readonly.peek(root_run_id)
    check(f"{boundary}-2f. durable lineage phase=CLAIMEDのまま", record_after_crash.phase, RetryLineagePhase.CLAIMED)
    check(f"{boundary}-2g. durable owner_tokenはclaim由来の値のまま非null", record_after_crash.owner_token is not None, True)
    original_owner_token = record_after_crash.owner_token

    # --- (3) reconcile_all(): RetryExecutionLock競合中はskipped=True（例外化しない） ---
    summary_busy = lineage_readonly.reconcile_all(lambda run_id: None)
    check_true(f"{boundary}-3a. RetryExecutionLock残存中はreconcile_all()がskipped=True（通常の戻り値）", summary_busy.skipped)
    check_true(f"{boundary}-3b. skip理由に'execution lock busy'を含む", "execution lock busy" in (summary_busy.reason or ""))
    check(f"{boundary}-3c. skip中はlineage phaseが変化しない", lineage_readonly.peek(root_run_id).phase, RetryLineagePhase.CLAIMED)

    # --- (4) 手動lock復旧の前提：旧holder process終了確認済み -----------
    # subprocess.run()のreturncode取得自体が、旧holder processが実際に終了
    # していることの確認に相当する（9.2a章「旧holder process終了確認後にのみ」）。
    lineage_config.execution_lock_path.unlink()

    # --- (5) RetryLineageStoreLock残存時の非対称性（catchされない生の例外） ---
    if expect_store_lock:
        raised = False
        try:
            lineage_readonly.reconcile_all(lambda run_id: None)
        except RetryLineageStoreLockError:
            raised = True
        check_true(
            f"{boundary}-5a. RetryLineageStoreLock残存時、reconcile_all()はRetryLineageStoreLockErrorを"
            f"catchされない生の例外として伝播する（RetryExecutionLockBusyErrorとの非対称性）",
            raised,
        )
        lineage_config.store_lock_path.unlink()
    else:
        check_true(f"{boundary}-5a. RetryLineageStoreLock非残存（B0）のため非対称性は非発生", True)

    if expect_manifest_lock:
        manifest_lock_path.unlink()

    # --- (6) 全lock復旧後：reconcile_all()成功 → CLAIMED orphan回収 -----
    summary_recover = lineage_readonly.reconcile_all(lambda run_id: None)
    check_false(f"{boundary}-6a. 全lock復旧後、reconcile_all()はskipped=False", summary_recover.skipped)
    check(f"{boundary}-6b. CLAIMED orphanを1件回収", summary_recover.released_count, 1)
    record_recovered = lineage_readonly.peek(root_run_id)
    check(f"{boundary}-6c. 回収後phase=READY_ELIGIBLE", record_recovered.phase, RetryLineagePhase.READY_ELIGIBLE)
    check(f"{boundary}-6d. 回収後owner_token=None", record_recovered.owner_token, None)

    # --- (7) 後続claim() → 新しいmember_run_idでのmanifest generation ---
    claim_after = lineage_readonly.claim(root_run_id)
    check_true(f"{boundary}-7a. 後続claim()が成功する", claim_after.acknowledged)
    check_true(f"{boundary}-7b. 新しいowner_tokenが旧owner_tokenと異なる", claim_after.owner_token != original_owner_token)

    new_member_run_id = f"exec-{boundary}-second-{uuid.uuid4().hex[:8]}"
    check_true(f"{boundary}-7c. 新member_run_idは旧member_run_idと異なる", new_member_run_id != member_run_id)
    mark_ok = lineage_readonly.mark_execution_started(root_run_id, new_member_run_id, claim_after.owner_token)
    check_true(f"{boundary}-7d. mark_execution_started()が新member_run_idで成功する", mark_ok)

    new_manifest = manifest_store._read_raw(root_run_id, 1, new_member_run_id)
    check_true(f"{boundary}-7e. 新member_run_idキーで新規manifestが作成されている", new_manifest is not None)
    if new_manifest is not None:
        check(f"{boundary}-7f. 新manifestはentries=()", new_manifest.entries, ())

    if expect_manifest_exists:
        old_manifest_after_recovery = manifest_store._read_raw(root_run_id, 1, member_run_id)
        check_true(f"{boundary}-7g. 旧（孤児化した）manifestは削除・変更されず引き続き存在する", old_manifest_after_recovery is not None)
        if old_manifest_after_recovery is not None:
            check(f"{boundary}-7h. 旧manifestはentries=()のまま不変", old_manifest_after_recovery.entries, ())

    print()


# =====================================================================
# 後始末：test-owned temp artifactのみ削除（repo本体には一切触れない）
# =====================================================================
for d in tmp_dirs:
    shutil.rmtree(d, ignore_errors=True)


# =====================================================================
# サマリー
# =====================================================================
print("=" * 70)
total = len(results_log)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = total - passed
print(f"合計: {total}件 / PASS: {passed}件 / FAIL: {failed}件")
if failed:
    print()
    print("FAILしたテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
print("すべてPASSしました。")
