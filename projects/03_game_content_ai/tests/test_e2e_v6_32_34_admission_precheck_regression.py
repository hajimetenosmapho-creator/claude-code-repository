"""
E2E テスト: Release 6.32 — Admission Precheck Regression（§18 test#16）

Source of Truth: docs/design/
side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md
§4.1・§9.5.1（owner_token 4段階authority check）・§18 test#16（既存admission
事前チェックとの整合回帰）

実コード確認（read-only、本ファイル作成前に実施）：
    `RetryLineageManager.mark_execution_started()`
    （src/retry_lineage/retry_lineage_manager.py:453-510）は、

        with self._store_lock():
            record = self._store.get(root_run_id)
            if record is None or not _verify_owner_authority(record, owner_token):
                return False
            ...
            if record.side_effect_contract_version is not None and self._manifest is not None:
                manifest_ok = self._manifest.create_for_attempt(...)
                ...

    という構造を持つ。`_verify_owner_authority()`（同ファイル97-108行）は
    4段階check（(1)caller token非空・(2)durable token非空・(3)phase==CLAIMED・
    (4)完全一致）を1つの関数へ統合しており、6.31時代の単純な
    `record is None or record.phase != CLAIMED`という事前チェックは、
    Amendmentにより「owner_token検証と統合されたが、判定順序自体は一切
    変わらず、依然としてmanifest作成呼び出しよりも先に評価される」形で
    存続している——これが本testで直接証明すべき回帰不在の主張である。

既存証拠との関係（重複回避）：
    test_e2e_v6_32_27（グループ2）は、owner_token=None/空文字列/不一致・
    stale A/current B raceのrejectionそのものは既に証明済みだが、いずれも
    `make_stack(with_side_effect_wiring=False)`（manifest=None）で構築されて
    おり、「precheck失敗時にmanifest createが実際に0回であること」は観測
    できていない（manifest自体が存在しないため）。本ファイルは、manifestを
    実際に配線した状態で同種のrejectionケースを再構成し、
    `create_for_attempt()`呼び出し回数を直接カウントすることで、この
    未証明だった一点のみを追加する。

最低限確認する項目：
    - invalid/non-CLAIMED phase → admission拒否（READY_ELIGIBLE・TERMINALの
      両方で確認）
    - missing/empty/wrong owner_token → 拒否
    - current exact owner_tokenのみ許可
    - precheck failure時 manifest create = 0
    - precheck failure時 lineage mutation = 0（durable recordが不変）
    - precheck failure時 external I/O = 0（本テスト環境に外部I/O呼び出し
      そのものが一切存在しないことで構造的に保証、明示的に注記する）
    - valid caseでは manifest create → EXECUTION_STARTED durable save の順序
      （実行順序を直接記録して確認、「構造上そうなるはず」で済ませない）
    - stale A/current BはAを拒否しBを保護（manifest create=0がAに対して
      維持されること込みで確認）

production code（RetryLineageManager等）は一切変更しない。
network / WordPress / 外部I/O = 0。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_34_admission_precheck_regression.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

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
print("Admission Precheck Regression（§18 test#16） — E2E テスト")
print("=" * 70)
print()

from protected_operation_manifest import JsonProtectedOperationManifestStore
from retry_lineage import (
    JsonRetryLineageStore,
    RetryLineageConfig,
    RetryLineageDisposition,
    RetryLineageManager,
    RetryLineagePhase,
)
from side_effect_safety.media_upload_applicability_store import JsonMediaUploadApplicabilityStore
from side_effect_safety.media_upload_attempt_context_store import JsonMediaUploadAttemptContextStore
from side_effect_safety.media_upload_safety_coordinator import build_media_upload_safety_coordinator
from side_effect_safety_classifier import SideEffectSafetyClassifier
from article_media_upload_state import ArticleMediaUploadStateManager, JsonArticleMediaUploadStateStore
from wordpress_draft_state import JsonWordPressDraftStateStore
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus

tmp_dirs: list[Path] = []


class FakePolicy:
    def __init__(self, max_attempts: int = 5):
        self.target_statuses = frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT})
        self._max_attempts = max_attempts

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    def should_retry(self, monitor_status, attempt: int) -> bool:
        return monitor_status in self.target_statuses and attempt < self._max_attempts


def make_monitor_record(run_id: str) -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=WorkflowMonitorStatus.FAILED,
        source_status="FAILED", source="manual", job_id="job-1",
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=[],
    )


def make_stack():
    """lineage（manifest配線あり）+ manifest createコール数spy + 順序記録sequence
    をtmp dirへ構築する。"""
    tmp_root = Path(tempfile.mkdtemp(prefix="v6_32_34_"))
    tmp_dirs.append(tmp_root)
    lineage_config = RetryLineageConfig(enabled=True, lineage_dir=tmp_root / "lineage")
    lineage_store = JsonRetryLineageStore(lineage_config.store_dir)
    manifest_store = JsonProtectedOperationManifestStore(base_dir=tmp_root / "manifest")
    draft_state_store = JsonWordPressDraftStateStore(base_dir=tmp_root / "wordpress_draft_state")
    media_upload_coordinator = build_media_upload_safety_coordinator(
        media_upload_manager=ArticleMediaUploadStateManager(
            JsonArticleMediaUploadStateStore(tmp_root / "article_media_upload_state")
        ),
        applicability_store=JsonMediaUploadApplicabilityStore(tmp_root / "media_upload_applicability"),
        attempt_context_store=JsonMediaUploadAttemptContextStore(tmp_root / "media_upload_attempt_context"),
        locks_dir=tmp_root / "media_upload_locks",
    )
    classifier = SideEffectSafetyClassifier(media_coordinator=media_upload_coordinator, draft_state=draft_state_store)

    lineage = RetryLineageManager(
        store=lineage_store, config=lineage_config, policy=FakePolicy(),
        manifest=manifest_store, side_effect_classifier=classifier,
    )

    sequence: list[tuple] = []
    create_calls: list[tuple] = []

    original_create = manifest_store.create_for_attempt

    def spy_create(root_run_id, attempt_ordinal, member_run_id):
        create_calls.append((root_run_id, attempt_ordinal, member_run_id))
        sequence.append(("manifest_create", root_run_id, attempt_ordinal, member_run_id))
        return original_create(root_run_id, attempt_ordinal, member_run_id)

    manifest_store.create_for_attempt = spy_create

    original_save = lineage_store.save

    def spy_save(record):
        sequence.append(("lineage_save", record.phase.value))
        return original_save(record)

    lineage_store.save = spy_save

    return lineage, manifest_store, lineage_store, create_calls, sequence


def snapshot(record):
    """precheck失敗時にdurable recordが不変であることを比較するための
    最小限のsnapshot。"""
    return (
        record.phase, record.owner_token, record.latest_run_id,
        record.attempt_count, len(record.membership), len(record.transition_history),
        record.terminal_disposition,
    )


# =====================================================================
# グループI：invalid phase（READY_ELIGIBLE、claim前）→ 拒否・manifest create=0
# =====================================================================
print("[グループI] invalid phase（READY_ELIGIBLE、未claim）→ admission拒否")

lineage_i, manifest_i, store_i, create_calls_i, seq_i = make_stack()
created_i = lineage_i.create_new_lineage("run-i", make_monitor_record("run-i"))
check_true("I前提: create_new_lineage()成功（phase=READY_ELIGIBLE、未claim）", not created_i.admission_rejected)
before_i = snapshot(lineage_i.peek("run-i"))

result_i = lineage_i.mark_execution_started("run-i", "exec-run-i", "any-looking-token")
check_false("I1. 未claim（READY_ELIGIBLE）状態でのmark_execution_started()は拒否される", result_i)
check("I2. precheck失敗時、manifest create呼び出し回数=0", len(create_calls_i), 0)
check("I3. precheck失敗時、durable recordは不変（lineage mutation=0）", snapshot(lineage_i.peek("run-i")), before_i)
print()


# =====================================================================
# グループJ：invalid phase（TERMINAL、既に確定済み）→ 拒否・manifest create=0
#            （owner_tokenが表面上まだ一致していてもphase gateで拒否される
#            ことを、owner_token check単体からisolateして確認する）
# =====================================================================
print("[グループJ] invalid phase（TERMINAL）→ admission拒否（owner_token一致でもphase gateで拒否）")

lineage_j, manifest_j, store_j, create_calls_j, seq_j = make_stack()
created_j = lineage_j.create_new_lineage("run-j", make_monitor_record("run-j"))
claim_j = lineage_j.claim("run-j")
check_true("J前提: claim()成功", claim_j.acknowledged)
mark_ok_j = lineage_j.mark_execution_started("run-j", "exec-run-j-1", claim_j.owner_token)
check_true("J前提: 1回目のmark_execution_started()成功（EXECUTION_STARTEDへ）", mark_ok_j)
check("J前提: manifest createは1回のみ（正当なadmission分）", len(create_calls_j), 1)
mark_terminal_j = lineage_j.mark_terminal("run-j", RetryLineageDisposition.SUCCEEDED, "exec-run-j-1", [])
check_true("J前提: mark_terminal()成功（TERMINALへ）", mark_terminal_j.acknowledged)
record_j_terminal = lineage_j.peek("run-j")
check("J前提: phase=TERMINAL、owner_tokenは依然として非null（claim由来の値のまま）",
      (record_j_terminal.phase, record_j_terminal.owner_token is not None), (RetryLineagePhase.TERMINAL, True))

before_j = snapshot(record_j_terminal)
# owner_token自体は（claim_j.owner_tokenと）表面上一致する値を渡しても、
# phase!=CLAIMEDであるため_verify_owner_authority()のcheck(3)で拒否される。
result_j = lineage_j.mark_execution_started("run-j", "exec-run-j-2", claim_j.owner_token)
check_false("J1. TERMINAL状態でのmark_execution_started()は拒否される（owner_token一致でも）", result_j)
check("J2. precheck失敗時、manifest create呼び出し回数は増えない（追加0回）", len(create_calls_j), 1)
check("J3. precheck失敗時、durable recordは不変", snapshot(lineage_j.peek("run-j")), before_j)
print()


# =====================================================================
# グループK：owner_token missing/empty/wrong → 拒否・manifest create=0、
#            正当なtokenのみ許可、manifest create→EXECUTION_STARTED saveの順序
# =====================================================================
print("[グループK] owner_token missing/empty/wrong → 拒否、正当tokenのみ許可、生成順序")

lineage_k, manifest_k, store_k, create_calls_k, seq_k = make_stack()
created_k = lineage_k.create_new_lineage("run-k", make_monitor_record("run-k"))
claim_k = lineage_k.claim("run-k")
check_true("K前提: claim()成功", claim_k.acknowledged)
before_k = snapshot(lineage_k.peek("run-k"))

check_false("K1. owner_token=None → 拒否", lineage_k.mark_execution_started("run-k", "x", None))
check_false("K2. owner_token='' → 拒否", lineage_k.mark_execution_started("run-k", "x", ""))
check_false("K3. owner_token=不一致 → 拒否", lineage_k.mark_execution_started("run-k", "x", "wrong-token"))
check("K4. K1〜K3のいずれもmanifest createを呼ばない（呼び出し回数=0）", len(create_calls_k), 0)
check("K5. K1〜K3のいずれの後もdurable recordは不変", snapshot(lineage_k.peek("run-k")), before_k)

result_k_valid = lineage_k.mark_execution_started("run-k", "exec-run-k", claim_k.owner_token)
check_true("K6. current exact owner_tokenのみ許可される", result_k_valid)
check("K7. 正当admissionでmanifest createが正確に1回呼ばれる", len(create_calls_k), 1)

manifest_create_index = next(i for i, e in enumerate(seq_k) if e[0] == "manifest_create")
lineage_save_index = next(i for i, e in enumerate(seq_k) if e[0] == "lineage_save" and e[1] == RetryLineagePhase.EXECUTION_STARTED.value)
check_true("K8. 実行順序: manifest create → EXECUTION_STARTED durable saveの順（記録されたsequenceで直接確認）",
           manifest_create_index < lineage_save_index)
print()


# =====================================================================
# グループL：stale A / current B → Aは拒否（manifest create=0のまま）、
#            Bは保護される（正当なmanifest createはBの新member_run_idのみ）
# =====================================================================
print("[グループL] stale A / current B → Aを拒否・manifest create=0を維持、Bを保護")

lineage_l, manifest_l, store_l, create_calls_l, seq_l = make_stack()
created_l = lineage_l.create_new_lineage("run-l", make_monitor_record("run-l"))
claim_a_l = lineage_l.claim("run-l")
owner_a_l = claim_a_l.owner_token
check_true("L前提: claim A成功", claim_a_l.acknowledged)

# Aがpost-admission hookへ到達する前に放棄（CLAIMED orphan）→ reconcile_all()で回収。
summary_recover_l = lineage_l.reconcile_all(lambda run_id: None)
check("L前提: CLAIMED orphan（claim A）を1件回収", summary_recover_l.released_count, 1)

claim_b_l = lineage_l.claim("run-l")
owner_b_l = claim_b_l.owner_token
check_true("L前提: claim B成功", claim_b_l.acknowledged)
check_true("L前提: owner_token A != owner_token B", owner_a_l != owner_b_l)
before_l = snapshot(lineage_l.peek("run-l"))

result_stale_a = lineage_l.mark_execution_started("run-l", "exec-stale-a", owner_a_l)
check_false("L1. stale A（旧owner_token）はmark_execution_started()できない", result_stale_a)
check("L2. stale Aの試行はmanifest createを一切呼ばない（呼び出し回数=0）", len(create_calls_l), 0)
check("L3. stale Aの試行後もBのCLAIMEDは不変（durable record不変）", snapshot(lineage_l.peek("run-l")), before_l)

result_current_b = lineage_l.mark_execution_started("run-l", "exec-run-b", owner_b_l)
check_true("L4. current B（正当なowner_token）は成功する", result_current_b)
check("L5. Bの正当admissionでmanifest createが正確に1回呼ばれる", len(create_calls_l), 1)
check("L6. 作成されたmanifestのmember_run_idはBの新run_id（exec-run-b）のみ", create_calls_l[0][2], "exec-run-b")
print()


# =====================================================================
# 外部I/O = 0の構造的注記
# =====================================================================
print("[注記] 本テストのproduction依存は JsonRetryLineageStore /")
print("       JsonProtectedOperationManifestStore / WordPressDraftStateStore /")
print("       MediaUploadSafetyCoordinatorのみで、いずれもlocal filesystemの")
print("       みに書き込む。requests等のHTTPクライアント・WordPress APIは")
print("       importすら行っておらず、外部I/O呼び出しは構造的に0件。")
print()


# =====================================================================
# 後始末
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
