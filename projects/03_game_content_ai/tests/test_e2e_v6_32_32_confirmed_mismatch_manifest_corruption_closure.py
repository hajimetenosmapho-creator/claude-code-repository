"""
E2E テスト: Release 6.32 — Confirmed-Mismatch & Manifest-Corruption Path
Closure（§18 test#7 + test#8）

Source of Truth: docs/design/
side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md
（Approved Architecture Amendment、Round 10 APPROVED）
§9.1（Missing/Corrupt Manifest Classification）・§10（Synchronous
Terminalization Algorithm）・§11（Reconciliation Algorithm）・§13（Missing/
Corrupt Manifest Classification、9章に統合済み）・
retry_lineage_target_resolution.resolve_final_disposition()（CONFIRMED_SUCCESS
mismatch分岐）・§18 test#7（confirmed side effect + failed/not_actioned
step）・test#8（Manifest破損）

test_e2e_v6_32_29（C4・C5・C6：list_for_attempt()単体でのcorruption/IOError
taxonomy）・test_e2e_v6_32_27（primary blocking closure、IN_PROGRESS_OR_UNKNOWN
分岐のみ）を補完し、以下2点を「store層の直接テスト」ではなく
`RetryExecutor.execute()`（sync）・`RetryLineageManager.reconcile_all()`
→`_reconcile_all_locked()`（restart）という**実production wiring**を
実際に駆動して直接証明する（人工stateだけでのproduction closure主張はしない）：

    A. sync confirmed-mismatch：manifest側でCONFIRMED_SUCCESS（WordPress
       draft作成が実際に確定済み）だが、同一attempt内の別stepが失敗した
       ケースで、resolve_final_disposition()のCONFIRMED_SUCCESS-mismatch
       分岐が実チェーンで発火し、HUMAN_REVIEW_REQUIREDへfail-closedする
       こと（SAFE/FAILED/NOT_ACTIONEDへ誤って倒れない、自動retryを開かない）。
    B. restart confirmed-mismatch：同シナリオを`_reconcile_all_locked()`
       経路（durable lineageのlatest_run_idを権威あるmember_run_idとして
       使用）で直接証明する。
    C. sync manifest corruption：admission直後にmanifestファイル自体を
       schema不正なJSONへ破損させ、`RetryExecutor.execute()`が
       `list_for_attempt()`のContractViolationErrorを無条件にHRRへ変換
       すること（classify()は一度も呼ばれないこと）を確認する。
    D. restart manifest corruption：同シナリオを`_reconcile_all_locked()`
       経路で直接証明する。

重点確認（各ケース共通）：
    - selected manifest identity（sync=engine_result.run_id、
      restart=record.latest_run_id）
    - classifier呼び出し回数・結果（SpyClassifierで直接観測）
    - final disposition（HUMAN_REVIEW_REQUIRED）
    - mark_terminal()へ渡されたdisposition（durable terminal_dispositionで確認）
    - next automatic retryが開かないこと（reconcile_all()のopened_count=0・
      phaseがREADY_ELIGIBLEへ戻らないこと）
    - old orphan（別member_run_id）のmanifest/draft state evidenceが
      current evidenceとして混入しないこと（グループA内で直接確認）

production code（RetryExecutor・RetryLineageManager・
SideEffectSafetyClassifier・resolve_final_disposition()等）は一切変更しない。
read-onlyでの実コード確認結果に基づき、テストのみを追加する。
network / WordPress / 外部I/O = 0。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_32_confirmed_mismatch_manifest_corruption_closure.py
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
print("Confirmed-Mismatch & Manifest-Corruption Path Closure — E2E テスト")
print("=" * 70)
print()

from dataclasses import dataclass
from execution_history import StepExecutionRecord, StepExecutionStatus
from protected_operation_manifest import (
    JsonProtectedOperationManifestStore,
    ManifestReaderFacade,
    ProtectedOperationManifestContractViolationError,
    build_manifest_entry,
)
from retry_engine import RetryExecutor, RetryRequest
from retry_lineage import (
    JsonRetryLineageStore,
    RetryLineageConfig,
    RetryLineageDisposition,
    RetryLineageManager,
    RetryLineagePhase,
)
from side_effect_safety import ProtectedSideEffectKind, SideEffectOperationIdentity, SideEffectSite
from side_effect_safety_classifier import SideEffectSafetyClassifier
from side_effect_safety.media_upload_applicability_store import JsonMediaUploadApplicabilityStore
from side_effect_safety.media_upload_attempt_context_store import JsonMediaUploadAttemptContextStore
from side_effect_safety.media_upload_safety_coordinator import build_media_upload_safety_coordinator
from side_effect_safety.side_effect_safety_category import SideEffectSafetyCategory
from article_media_upload_state import ArticleMediaUploadStateManager, JsonArticleMediaUploadStateStore
from wordpress_draft_state import JsonWordPressDraftStateStore
from workflow_engine import ALL_WORKFLOW_ENGINE_STEPS, WorkflowEngineResult, WorkflowEngineStep, WorkflowEngineStepResult
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus

tmp_dirs: list[Path] = []


class FakePolicy:
    def __init__(self, max_attempts: int = 3):
        self.target_statuses = frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT})
        self._max_attempts = max_attempts

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    def should_retry(self, monitor_status, attempt: int) -> bool:
        return monitor_status in self.target_statuses and attempt < self._max_attempts


class SpyClassifier:
    """SideEffectSafetyClassifier.classify()の呼び出し回数・引数・結果を観測する
    ためだけのtest-owned wrapper（production classそのものは変更しない）。"""

    def __init__(self, real: SideEffectSafetyClassifier):
        self._real = real
        self.calls: list[tuple] = []

    def classify(self, root_run_id, attempt_ordinal, member_run_id, operations):
        report = self._real.classify(root_run_id, attempt_ordinal, member_run_id, operations)
        self.calls.append((root_run_id, attempt_ordinal, member_run_id, tuple(operations), report))
        return report


@dataclass
class FakeAgentResult:
    success: bool
    action_taken: bool | None = None

    def to_dict(self):
        return {"success": self.success, "action_taken": self.action_taken}


def make_step_result(step, executed, success, action_taken=None):
    ar = FakeAgentResult(success=success, action_taken=action_taken) if executed else None
    return WorkflowEngineStepResult(
        step=step, executed=executed, agent_result=ar, success=success,
        skipped_reason=None if executed else "skipped",
    )


def make_monitor_record(run_id: str, monitor_status=WorkflowMonitorStatus.FAILED, steps=None) -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=monitor_status,
        source_status=monitor_status.value, source="manual", job_id="job-1",
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=steps or [],
    )


def make_stack():
    """lineage/manifest/draft_state/spy_classifierをtmp dirへ構築する。"""
    tmp_root = Path(tempfile.mkdtemp(prefix="v6_32_32_"))
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
    real_classifier = SideEffectSafetyClassifier(media_coordinator=media_upload_coordinator, draft_state=draft_state_store)
    spy_classifier = SpyClassifier(real_classifier)

    lineage = RetryLineageManager(
        store=lineage_store, config=lineage_config, policy=FakePolicy(),
        manifest=manifest_store, side_effect_classifier=spy_classifier,
    )
    return lineage, manifest_store, draft_state_store, spy_classifier


# =====================================================================
# グループA：sync confirmed-mismatch（RetryExecutor.execute()実チェーン）
# =====================================================================
print("[グループA] sync confirmed-mismatch（CONFIRMED_SUCCESS + FAILED step）")

lineage_a, manifest_a, draft_state_a, classifier_a = make_stack()
created_a = lineage_a.create_new_lineage("run-a", make_monitor_record("run-a"))
check_true("A前提: create_new_lineage()成功", not created_a.admission_rejected)
claim_a = lineage_a.claim("run-a")
check_true("A前提: claim()成功", claim_a.acknowledged)

# 重点確認：old orphan（別member_run_id）のmanifest/draft state evidenceが
# current evidenceとして混入しないことの直接確認。旧member "exec-orphan-a" に
# 意図的に矛盾する（今回のattemptとは無関係な）CONFIRMED_SUCCESS evidenceを
# 先に登録しておく——current member（後述のexec-run-a）の判定に一切影響しない
# ことを後段でentries比較により確認する。
orphan_identity_a = SideEffectOperationIdentity(
    root_run_id="run-a", attempt_ordinal=1,
    operation_kind=ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION,
    effect_site=SideEffectSite.NEWS_STEP, operation_instance_key="orphan-slug-a",
)
manifest_a.create_for_attempt("run-a", 1, "exec-orphan-a")
manifest_a.register(
    "run-a", 1, "exec-orphan-a",
    build_manifest_entry(ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION, SideEffectSite.NEWS_STEP, "orphan-slug-a"),
)
draft_state_a.create_attempted(orphan_identity_a, "exec-orphan-a", datetime.now().isoformat())
draft_state_a.transition_to_confirmed(orphan_identity_a, "exec-orphan-a", 99999, datetime.now().isoformat())


class ConfirmedMismatchEngine:
    """呼び出し箇所Aを模す：NEWS stepでWordPress draft作成が実際に確定済み
    （transition_to_confirmed()まで完了）だが、REVIEW stepが失敗する
    シナリオ（confirmed side effect + failed step）。"""

    def __init__(self, manifest_store, draft_state_store, slug: str, member_run_id: str):
        self._manifest = manifest_store
        self._draft_state = draft_state_store
        self._slug = slug
        self._member_run_id = member_run_id
        self.calls = 0

    def run(self, event, dry_run=False, target_step_filter=None, post_admission_hook=None,
            correlation_metadata=None, side_effect_execution_provenance=None):
        self.calls += 1
        run_id = self._member_run_id
        root_run_id = event.job_id
        if post_admission_hook is not None:
            post_admission_hook(run_id)

        identity = SideEffectOperationIdentity(
            root_run_id=root_run_id, attempt_ordinal=1,
            operation_kind=ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION,
            effect_site=SideEffectSite.NEWS_STEP, operation_instance_key=self._slug,
        )
        self._manifest.register(
            root_run_id, 1, run_id,
            build_manifest_entry(ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION, SideEffectSite.NEWS_STEP, self._slug),
        )
        self._draft_state.create_attempted(identity, run_id, datetime.now().isoformat())
        self._draft_state.transition_to_confirmed(identity, run_id, 12345, datetime.now().isoformat())

        steps = [
            make_step_result(WorkflowEngineStep.NEWS, executed=True, success=True, action_taken=True),
            make_step_result(WorkflowEngineStep.REVIEW, executed=True, success=False),
            make_step_result(WorkflowEngineStep.PUBLISH, executed=False, success=False),
        ]
        return WorkflowEngineResult(
            run_id=run_id, steps=steps, overall_success=False, stopped_early=True,
            started_at=datetime.now(), finished_at=datetime.now(),
        )


engine_a = ConfirmedMismatchEngine(manifest_a, draft_state_a, slug="article-a", member_run_id="exec-run-a")
executor_a = RetryExecutor(
    workflow_engine_manager=engine_a, lineage=lineage_a,
    manifest=ManifestReaderFacade(manifest_a), side_effect_classifier=classifier_a,
)
request_a = RetryRequest(run_id="run-a", attempt=1, requested_at=datetime.now(), dry_run=False)
result_a = executor_a.execute(request_a, created_a.lineage, claim_a)

record_a = lineage_a.peek("run-a")
check("A1. selected manifest identity: engine_result.run_id（exec-run-a）由来のみ使用",
      manifest_a.list_for_attempt("run-a", 1, "exec-run-a")[0].operation_instance_key, "article-a")
check("A2. classifierは1回だけ呼ばれる", len(classifier_a.calls), 1)
check("A3. classifier結果（worst_case）はCONFIRMED_SUCCESS", classifier_a.calls[0][4].worst_case(), SideEffectSafetyCategory.CONFIRMED_SUCCESS)
check("A4. final disposition=HUMAN_REVIEW_REQUIRED（SAFE/FAILED/NOT_ACTIONEDへ誤って倒れない）",
      record_a.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("A5. mark_terminal()へ渡されたdispositionもHRR（durable記録で確認）", record_a.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("A6. phaseはTERMINAL（HRRとして確定）", record_a.phase, RetryLineagePhase.TERMINAL)

# old orphan（別member_run_id）が混入していないことの直接確認。
entries_current_a = manifest_a.list_for_attempt("run-a", 1, "exec-run-a")
entries_orphan_a = manifest_a.list_for_attempt("run-a", 1, "exec-orphan-a")
check_true("A7. current memberのentriesとold orphan memberのentriesは別物（instance_keyが異なる）",
           entries_current_a[0].operation_instance_key != entries_orphan_a[0].operation_instance_key)
check_true("A8. classifierへ渡されたmember_run_idはcurrent（exec-run-a）、old orphan（exec-orphan-a）ではない",
           classifier_a.calls[0][2] == "exec-run-a")

# next automatic retryが開かないこと（reconcile_all()を1回走らせて確認）。
summary_a = lineage_a.reconcile_all(lambda run_id: None)
check("A9. next automatic retryが開かない（opened_count=0）", summary_a.opened_count, 0)
check("A10. phaseはREADY_ELIGIBLEへ戻らない（TERMINALのまま）", lineage_a.peek("run-a").phase, RetryLineagePhase.TERMINAL)
print()


# =====================================================================
# グループB：restart confirmed-mismatch（_reconcile_all_locked()実チェーン）
# =====================================================================
print("[グループB] restart confirmed-mismatch（CONFIRMED_SUCCESS + FAILED step）")

lineage_b, manifest_b, draft_state_b, classifier_b = make_stack()
created_b = lineage_b.create_new_lineage("run-b", make_monitor_record("run-b"))
claim_b = lineage_b.claim("run-b")
check_true("B前提: claim()成功", claim_b.acknowledged)
mark_ok_b = lineage_b.mark_execution_started("run-b", "exec-run-b", claim_b.owner_token)
check_true("B前提: mark_execution_started()成功（空manifest作成済み）", mark_ok_b)

identity_b = SideEffectOperationIdentity(
    root_run_id="run-b", attempt_ordinal=1,
    operation_kind=ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION,
    effect_site=SideEffectSite.NEWS_STEP, operation_instance_key="article-b",
)
manifest_b.register(
    "run-b", 1, "exec-run-b",
    build_manifest_entry(ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION, SideEffectSite.NEWS_STEP, "article-b"),
)
draft_state_b.create_attempted(identity_b, "exec-run-b", datetime.now().isoformat())
draft_state_b.transition_to_confirmed(identity_b, "exec-run-b", 54321, datetime.now().isoformat())

monitor_b = make_monitor_record(
    "run-b",
    steps=[
        StepExecutionRecord(step="news", status=StepExecutionStatus.SUCCESS, action_taken=True),
        StepExecutionRecord(step="review", status=StepExecutionStatus.FAILED),
    ],
)
summary_b = lineage_b.reconcile_all(lambda run_id: monitor_b if run_id == "exec-run-b" else None)
record_b = lineage_b.peek("run-b")

check("B1. selected manifest identity: record.latest_run_id（exec-run-b）由来のみ使用", record_b.latest_run_id, "exec-run-b")
check("B2. classifierは1回だけ呼ばれる", len(classifier_b.calls), 1)
check("B3. classifier結果（worst_case）はCONFIRMED_SUCCESS", classifier_b.calls[0][4].worst_case(), SideEffectSafetyCategory.CONFIRMED_SUCCESS)
check("B4. final disposition=HUMAN_REVIEW_REQUIRED", record_b.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("B5. mark_terminal()へ渡されたdispositionもHRR（durable記録で確認）", record_b.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("B6. next automatic retryが開かない（同一reconcile_all()呼び出し内でopened_count=0）", summary_b.opened_count, 0)
check("B7. phaseはTERMINAL", record_b.phase, RetryLineagePhase.TERMINAL)
print()


# =====================================================================
# グループC：sync manifest corruption（RetryExecutor.execute()実チェーン）
# =====================================================================
print("[グループC] sync manifest corruption（schema不正なJSON注入）")

lineage_c, manifest_c, draft_state_c, classifier_c = make_stack()
created_c = lineage_c.create_new_lineage("run-c", make_monitor_record("run-c"))
claim_c = lineage_c.claim("run-c")
check_true("C前提: claim()成功", claim_c.acknowledged)


class CorruptManifestEngine:
    """呼び出し箇所Aを模す：admission（post_admission_hook経由の
    mark_execution_started()）で正しい空manifestが作成された直後、manifest
    ファイル自体をschema不正なJSONへ破損させる（true filesystem I/O
    failureではなく、durableに書かれた内容そのものの破損）。ステップ結果は
    全て成功（破損さえなければSUCCEEDEDになるはずのケース）とし、
    corruption単体がHRRを強制することを切り分けて証明する。"""

    def __init__(self, manifest_store, member_run_id: str):
        self._manifest = manifest_store
        self._member_run_id = member_run_id
        self.calls = 0

    def run(self, event, dry_run=False, target_step_filter=None, post_admission_hook=None,
            correlation_metadata=None, side_effect_execution_provenance=None):
        self.calls += 1
        run_id = self._member_run_id
        root_run_id = event.job_id
        if post_admission_hook is not None:
            post_admission_hook(run_id)  # ここでcreate_for_attempt()により正しい空manifestが作られる

        path = self._manifest._path_for(root_run_id, 1, run_id)
        path.write_text("{not valid json", encoding="utf-8")  # schema不正なJSONへ破損させる

        steps = [make_step_result(s, executed=True, success=True, action_taken=True) for s in ALL_WORKFLOW_ENGINE_STEPS]
        return WorkflowEngineResult(
            run_id=run_id, steps=steps, overall_success=True, stopped_early=False,
            started_at=datetime.now(), finished_at=datetime.now(),
        )


engine_c = CorruptManifestEngine(manifest_c, member_run_id="exec-run-c")
executor_c = RetryExecutor(
    workflow_engine_manager=engine_c, lineage=lineage_c,
    manifest=ManifestReaderFacade(manifest_c), side_effect_classifier=classifier_c,
)
request_c = RetryRequest(run_id="run-c", attempt=1, requested_at=datetime.now(), dry_run=False)
result_c = executor_c.execute(request_c, created_c.lineage, claim_c)
record_c = lineage_c.peek("run-c")

raised_c = None
try:
    manifest_c.list_for_attempt("run-c", 1, "exec-run-c")
except ProtectedOperationManifestContractViolationError:
    raised_c = "ContractViolationError"
check("C1. selected manifest identity（exec-run-c）は実際に破損している（ContractViolationError）", raised_c, "ContractViolationError")
check("C2. classifierは一度も呼ばれない（read errorで短絡、classify()未到達）", len(classifier_c.calls), 0)
check("C3. final disposition=HUMAN_REVIEW_REQUIRED（ステップは全て成功でも破損単体でHRR）",
      record_c.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("C4. mark_terminal()へ渡されたdispositionもHRR（durable記録で確認）", record_c.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("C5. phaseはTERMINAL", record_c.phase, RetryLineagePhase.TERMINAL)

summary_c = lineage_c.reconcile_all(lambda run_id: None)
check("C6. next automatic retryが開かない（opened_count=0）", summary_c.opened_count, 0)
print()


# =====================================================================
# グループD：restart manifest corruption（_reconcile_all_locked()実チェーン）
# =====================================================================
print("[グループD] restart manifest corruption（schema不正なJSON注入）")

lineage_d, manifest_d, draft_state_d, classifier_d = make_stack()
created_d = lineage_d.create_new_lineage("run-d", make_monitor_record("run-d"))
claim_d = lineage_d.claim("run-d")
mark_ok_d = lineage_d.mark_execution_started("run-d", "exec-run-d", claim_d.owner_token)
check_true("D前提: mark_execution_started()成功（空manifest作成済み）", mark_ok_d)

path_d = manifest_d._path_for("run-d", 1, "exec-run-d")
path_d.write_text("{not valid json", encoding="utf-8")

monitor_d = make_monitor_record(
    "run-d",
    steps=[
        StepExecutionRecord(step="news", status=StepExecutionStatus.SUCCESS, action_taken=True),
        StepExecutionRecord(step="review", status=StepExecutionStatus.SUCCESS, action_taken=True),
        StepExecutionRecord(step="publish", status=StepExecutionStatus.SUCCESS, action_taken=True),
    ],
)
summary_d = lineage_d.reconcile_all(lambda run_id: monitor_d if run_id == "exec-run-d" else None)
record_d = lineage_d.peek("run-d")

raised_d = None
try:
    manifest_d.list_for_attempt("run-d", 1, "exec-run-d")
except ProtectedOperationManifestContractViolationError:
    raised_d = "ContractViolationError"
check("D1. selected manifest identity（record.latest_run_id=exec-run-d）は実際に破損している", raised_d, "ContractViolationError")
check("D2. classifierは一度も呼ばれない（read errorで短絡）", len(classifier_d.calls), 0)
check("D3. final disposition=HUMAN_REVIEW_REQUIRED（全step成功でも破損単体でHRR）",
      record_d.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("D4. mark_terminal()へ渡されたdispositionもHRR（durable記録で確認）", record_d.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("D5. next automatic retryが開かない（同一reconcile_all()呼び出し内でopened_count=0）", summary_d.opened_count, 0)
check("D6. phaseはTERMINAL", record_d.phase, RetryLineagePhase.TERMINAL)
print()


# =====================================================================
# 後始末：test-owned temp artifactのみ削除
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
