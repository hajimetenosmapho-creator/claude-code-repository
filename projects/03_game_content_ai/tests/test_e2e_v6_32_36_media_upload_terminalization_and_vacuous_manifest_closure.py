"""
E2E テスト: Release 6.32 — Terminalization Completeness Closure
（§18 test#6 + test#9）

Source of Truth: docs/design/
side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md
§9.1（Missing/Corrupt Manifest Classification、vacuous case）・§11（restart
Reconciliation Algorithm）・§18 test#6（crash路：media upload confirm直前）・
test#9（Manifest空、正常0件）

## グループP：§18 test#6 — MEDIA_UPLOAD confirm直前crash → restart → HRR

呼び出し箇所B（`main.py` `_apply_featured_media_step()`）の実際の状態遷移
（`MediaUploadSafetyCoordinator.record_attempted()`＝IO_ARMED、外部upload
I/Oが実際に成功した後にのみ到達するdurable state）を実際に構築し、
`record_confirmed()`（durable確定）を**呼ばないまま**（crash相当）、
`RetryLineageManager.reconcile_all()`→`_reconcile_all_locked()`の実チェーンで
disposition=HUMAN_REVIEW_REQUIREDへ収束し、`mark_terminal()`へHRRが渡り、
同一`reconcile_all()`呼び出し内で`opened_count=0`（自動retry不開始）となる
ことを直接証明する。

外部upload API・WordPress APIは一切importしない（`MediaUploadSafetyCoordinator`
はJSON storeのみに依存する、read-only事前確認済み）——real external I/Oは
発生しない。`record_attempted()`自体を「upload external I/Oが成功した」
ことのdurable evidenceとして扱う（Approved Architecture、IO_ARMED semantics）。

## グループQ：§18 test#9 — vacuous manifest（entries=()）

0エントリのmanifest（Step 0（admission）は成功したがStep 1（register）が
一度も呼ばれなかった、正常0件のNEWS run相当）について、
`RetryExecutor.execute()`の実チェーンで：

    - `list_for_attempt()`が正常return（entries=()、NotFoundではない）
    - `SideEffectSafetyReport.worst_case()`がNOT_APPLICABLE（vacuous safe）
    - 不要なHRRを発生させない
    - 期待される final disposition（SUCCEEDED）へ実際に到達する

ことを、`SideEffectSafetyClassifier.classify()`を含む実チェーンで直接証明
する（store層単体では`test_e2e_v6_32_29`のC7で証明済みだが、
`RetryExecutor.execute()`のproduction wiringを通した証明はこれが初出）。

いずれのグループもproduction code
（`RetryExecutor`・`RetryLineageManager`・`SideEffectSafetyClassifier`・
`MediaUploadSafetyCoordinator`等）を一切変更しない。
network / WordPress / 外部I/O = 0。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_36_media_upload_terminalization_and_vacuous_manifest_closure.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from dataclasses import dataclass
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
print("Terminalization Completeness Closure（§18 #6+#9） — E2E テスト")
print("=" * 70)
print()

from protected_operation_manifest import (
    JsonProtectedOperationManifestStore,
    ManifestReaderFacade,
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
from workflow_engine import ALL_WORKFLOW_ENGINE_STEPS, WorkflowEngineResult, WorkflowEngineStepResult
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


class SpyClassifier:
    def __init__(self, real: SideEffectSafetyClassifier):
        self._real = real
        self.calls: list[tuple] = []

    def classify(self, root_run_id, attempt_ordinal, member_run_id, operations):
        report = self._real.classify(root_run_id, attempt_ordinal, member_run_id, operations)
        self.calls.append((root_run_id, attempt_ordinal, member_run_id, tuple(operations), report))
        return report


def make_monitor_record(run_id: str, steps=None) -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=WorkflowMonitorStatus.FAILED,
        source_status="FAILED", source="manual", job_id="job-1",
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=steps or [],
    )


def make_stack():
    """lineage/manifest/draft_state/media_upload_coordinator/spy_classifierを
    tmp dirへ構築する（media_upload_coordinatorも直接返す点がtest_32/33/34/35の
    make_stack()との違い）。"""
    tmp_root = Path(tempfile.mkdtemp(prefix="v6_32_36_"))
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
    return lineage, manifest_store, draft_state_store, media_upload_coordinator, spy_classifier


# =====================================================================
# グループP：§18 test#6 — MEDIA_UPLOAD confirm直前crash → restart → HRR
# =====================================================================
print("[グループP] §18 test#6: MEDIA_UPLOAD confirm直前crash → restart reconciliation → HRR")

lineage_p, manifest_p, draft_state_p, media_coordinator_p, classifier_p = make_stack()
created_p = lineage_p.create_new_lineage("run-p", make_monitor_record("run-p"))
claim_p = lineage_p.claim("run-p")
mark_ok_p = lineage_p.mark_execution_started("run-p", "exec-run-p", claim_p.owner_token)
check_true("P前提: mark_execution_started()成功（空manifest作成済み）", mark_ok_p)

# old orphan（別member_run_id）で矛盾するCONFIRMED相当evidenceを先に仕込み、
# fallback非発生を後段で確認する。
identity_orphan_p = SideEffectOperationIdentity(
    root_run_id="run-p", attempt_ordinal=1,
    operation_kind=ProtectedSideEffectKind.MEDIA_UPLOAD,
    effect_site=SideEffectSite.NEWS_STEP, operation_instance_key="orphan-slug-p",
)
manifest_p.create_for_attempt("run-p", 1, "exec-orphan-p")
manifest_p.register(
    "run-p", 1, "exec-orphan-p",
    build_manifest_entry(ProtectedSideEffectKind.MEDIA_UPLOAD, SideEffectSite.NEWS_STEP, "orphan-slug-p"),
)
media_coordinator_p.record_attempted(identity_orphan_p, "exec-orphan-p")
media_coordinator_p.record_confirmed(identity_orphan_p, "exec-orphan-p", media_id=77777)

# current memberでの実シナリオ：呼び出し箇所B相当（外部upload I/O成功→IO_ARMED
# durable記録）まで実際に到達し、record_confirmed()（durable確定）は
# 呼ばないまま放棄する（crash相当）。
identity_p = SideEffectOperationIdentity(
    root_run_id="run-p", attempt_ordinal=1,
    operation_kind=ProtectedSideEffectKind.MEDIA_UPLOAD,
    effect_site=SideEffectSite.NEWS_STEP, operation_instance_key="article-p",
)
manifest_p.register(
    "run-p", 1, "exec-run-p",
    build_manifest_entry(ProtectedSideEffectKind.MEDIA_UPLOAD, SideEffectSite.NEWS_STEP, "article-p"),
)
attempted_record_p = media_coordinator_p.record_attempted(identity_p, "exec-run-p")
check_true("P前提: record_attempted()成功（外部upload I/O成功相当、IO_ARMED durable記録）", attempted_record_p is not None)
# record_confirmed()は意図的に呼ばない（confirmation durable記録前crash）。

from execution_history import StepExecutionRecord, StepExecutionStatus
monitor_p = make_monitor_record(
    "run-p",
    steps=[StepExecutionRecord(step=s.value, status=StepExecutionStatus.SUCCESS, action_taken=True) for s in ALL_WORKFLOW_ENGINE_STEPS],
)
summary_p = lineage_p.reconcile_all(lambda run_id: monitor_p if run_id == "exec-run-p" else None)
record_p = lineage_p.peek("run-p")

check("P1. restartがcurrent durable member identity（record.latest_run_id=exec-run-p）を使用", record_p.latest_run_id, "exec-run-p")
check("P2. classifierは1回だけ呼ばれる", len(classifier_p.calls), 1)
check("P3. classifierへ渡されたmember_run_idはcurrent（exec-run-p）、old orphan（exec-orphan-p）ではない", classifier_p.calls[0][2], "exec-run-p")
check("P4. classifier結果（worst_case）はIN_PROGRESS_OR_UNKNOWN（IO_ARMEDのみ、confirm未到達）", classifier_p.calls[0][4].worst_case(), SideEffectSafetyCategory.IN_PROGRESS_OR_UNKNOWN)
check("P5. final disposition=HUMAN_REVIEW_REQUIRED", record_p.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("P6. mark_terminal()へ渡されたdispositionもHRR（durable記録で確認）", record_p.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("P7. 同一reconcile_all()呼び出し内でopened_count=0（自動retry不開始）", summary_p.opened_count, 0)
check("P8. phaseはTERMINAL", record_p.phase, RetryLineagePhase.TERMINAL)

# old orphanが無傷であることの確認（fallback非発生の直接証拠）。
orphan_after_p = media_coordinator_p.get(identity_orphan_p, "exec-orphan-p")
check_true("P9. old orphan（exec-orphan-p）のCONFIRMED evidenceは無傷のまま（current判定に混入していない）",
           type(orphan_after_p).__name__ == "ConfirmedMediaUploadSafetyRecord")
print()


# =====================================================================
# グループQ：§18 test#9 — vacuous manifest（entries=()、RetryExecutor.execute()実チェーン）
# =====================================================================
print("[グループQ] §18 test#9: vacuous manifest（0エントリ）→ SUCCEEDED（HRR非発火）")

lineage_q, manifest_q, draft_state_q, media_coordinator_q, classifier_q = make_stack()
created_q = lineage_q.create_new_lineage("run-q", make_monitor_record("run-q"))
claim_q = lineage_q.claim("run-q")
check_true("Q前提: claim()成功", claim_q.acknowledged)


@dataclass
class FakeAgentResult:
    success: bool
    action_taken: bool | None = None

    def to_dict(self):
        return {"success": self.success, "action_taken": self.action_taken}


class VacuousEngine:
    """呼び出し箇所A/B/Cのいずれも発火しない0記事NEWS run相当：admission
    （post_admission_hook）は成功させ空manifestを作成するが、manifest.register()
    は一度も呼ばない。全stepは正常に成功する（0記事のため保護対象operationが
    1件も発生しなかっただけで、実行自体は正常終了）。"""

    def __init__(self, member_run_id: str):
        self._member_run_id = member_run_id
        self.calls = 0

    def run(self, event, dry_run=False, target_step_filter=None, post_admission_hook=None,
            correlation_metadata=None, side_effect_execution_provenance=None):
        self.calls += 1
        run_id = self._member_run_id
        if post_admission_hook is not None:
            post_admission_hook(run_id)
        steps = [
            WorkflowEngineStepResult(step=s, executed=True, agent_result=FakeAgentResult(True, True), success=True, skipped_reason=None)
            for s in ALL_WORKFLOW_ENGINE_STEPS
        ]
        return WorkflowEngineResult(
            run_id=run_id, steps=steps, overall_success=True, stopped_early=False,
            started_at=datetime.now(), finished_at=datetime.now(),
        )


engine_q = VacuousEngine(member_run_id="exec-run-q")
executor_q = RetryExecutor(
    workflow_engine_manager=engine_q, lineage=lineage_q,
    manifest=ManifestReaderFacade(manifest_q), side_effect_classifier=classifier_q,
)
request_q = RetryRequest(run_id="run-q", attempt=1, requested_at=datetime.now(), dry_run=False)
executor_q.execute(request_q, created_q.lineage, claim_q)
record_q = lineage_q.peek("run-q")

entries_q = manifest_q.list_for_attempt("run-q", 1, "exec-run-q")
check("Q1. exact manifestがselectされ、entries=()（正常return、NotFoundではない）", entries_q, ())
check("Q2. classifierは1回だけ呼ばれる（operations=[]で呼ばれる）", len(classifier_q.calls), 1)
check("Q3. classifier結果（worst_case）はNOT_APPLICABLE（vacuous safe）", classifier_q.calls[0][4].worst_case(), SideEffectSafetyCategory.NOT_APPLICABLE)
check("Q4. final disposition=SUCCEEDED（不要なHRRを発生させない）", record_q.terminal_disposition, RetryLineageDisposition.SUCCEEDED)
check("Q5. phaseはTERMINAL", record_q.phase, RetryLineagePhase.TERMINAL)

summary_q = lineage_q.reconcile_all(lambda run_id: None)
check("Q6. SUCCEEDEDのため次の自動retryも開かない（opened_count=0）", summary_q.opened_count, 0)
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
