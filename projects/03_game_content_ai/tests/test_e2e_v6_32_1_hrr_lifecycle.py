"""
E2E テスト: v6.32.1 Human Review Required (HRR) Lifecycle

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    16章（open_next_attempt() HRR拡張）・17章（Human Resolution Lifecycle）・
    18章（Contract Version Snapshot）・13章（resolve_final_disposition()）・
    10.2節（SideEffectSafetyClassifier）

sub-milestone 1（HRR lifecycle：retry_lineage拡張）の direct tests。

実行方法:
    cd projects/03_game_content_ai
    .\\venv\\Scripts\\python.exe tests\\test_e2e_v6_32_1_hrr_lifecycle.py
"""
import shutil
import sys
import tempfile
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
    check(label, bool(value), True)


def check_raises(label: str, fn, exc_type):
    try:
        fn()
        check_true(label, False)
    except exc_type:
        check_true(label, True)
    except Exception as e:
        results_log.append(("FAIL", label))
        print(f"  [NG] {label}")
        print(f"       期待した例外型: {exc_type.__name__}")
        print(f"       実際の例外型: {type(e).__name__}: {e}")


print("=" * 60)
print("v6.32.1 HRR Lifecycle E2E テスト")
print("=" * 60)
print()

from retry_lineage import (  # noqa: E402
    ContractVersionEvidence,
    HumanReviewResolution,
    JsonRetryLineageStore,
    RetryLineageConfig,
    RetryLineageDisposition,
    RetryLineageManager,
    RetryLineagePhase,
    SIDE_EFFECT_CONTRACT_VERSION,
    classify_contract_version_evidence,
    resolve_final_disposition,
)
from retry_lineage.retry_lineage_record import HumanReviewResolutionRecord
from retry_lineage.retry_lineage_genuine_action import StepOutcomeCategory
from retry_composition import retry_after_human_review  # noqa: E402
from side_effect_safety import (  # noqa: E402
    JsonMediaUploadApplicabilityStore,
    ProtectedOperationContext,
    ProtectedSideEffectKind,
    SideEffectSafetyCategory,
    SideEffectSite,
    build_media_upload_safety_coordinator,
)
from side_effect_safety.media_upload_attempt_context_store import JsonMediaUploadAttemptContextStore
from side_effect_safety_classifier import SideEffectSafetyClassifier  # noqa: E402
from article_media_upload_state.article_media_upload_state_manager import ArticleMediaUploadStateManager  # noqa: E402
from article_media_upload_state.json_article_media_upload_state_store import JsonArticleMediaUploadStateStore  # noqa: E402
from wordpress_draft_state import JsonWordPressDraftStateStore  # noqa: E402
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus  # noqa: E402


tmp_dirs: list[Path] = []


def make_lineage_manager(policy=None) -> RetryLineageManager:
    tmp_root = Path(tempfile.mkdtemp())
    tmp_dirs.append(tmp_root)
    config = RetryLineageConfig(enabled=True, lineage_dir=tmp_root)
    store = JsonRetryLineageStore(config.store_dir)
    return RetryLineageManager(store=store, config=config, policy=policy or _FakePolicy())


class _FakePolicy:
    target_statuses = frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT})
    max_attempts = 5

    def should_retry(self, monitor_status, attempt) -> bool:
        return monitor_status in self.target_statuses and attempt < self.max_attempts


def make_monitor_record(run_id: str, status=WorkflowMonitorStatus.FAILED) -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=status,
        source_status=status.value, source="manual", job_id="job-1",
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=[],
    )


def _put_into_hrr(manager: RetryLineageManager, run_id: str) -> str:
    """テスト用ヘルパー：新規lineageを作成し、直接HUMAN_REVIEW_REQUIREDへ terminal化する。"""
    created = manager.create_new_lineage(run_id, make_monitor_record(run_id))
    assert not created.admission_rejected
    claimed = manager.claim(run_id)
    assert claimed.acknowledged
    manager.mark_execution_started(run_id, run_id, claimed.owner_token)
    result = manager.mark_terminal(run_id, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED, run_id, [])
    assert result.acknowledged
    return run_id


# ─── [テスト1] Contract Version Snapshot（18章） ───

print("[テスト1] Contract Version Snapshot")

manager1 = make_lineage_manager()
created1 = manager1.create_new_lineage("run-1", make_monitor_record("run-1"))
check("1a. create_new_lineage()はSIDE_EFFECT_CONTRACT_VERSIONをスタンプする", created1.lineage.side_effect_contract_version, SIDE_EFFECT_CONTRACT_VERSION)
check("1b. classify_contract_version_evidence: PROTECTED", classify_contract_version_evidence(created1.lineage), ContractVersionEvidence.PROTECTED)

legacy_record = manager1.peek("run-1")
legacy_record.side_effect_contract_version = None
check("1c. classify_contract_version_evidence: LEGACY", classify_contract_version_evidence(legacy_record), ContractVersionEvidence.LEGACY)
legacy_record.side_effect_contract_version = 0
check("1d. classify_contract_version_evidence: INVALID（0）", classify_contract_version_evidence(legacy_record), ContractVersionEvidence.INVALID)
legacy_record.side_effect_contract_version = -1
check("1e. classify_contract_version_evidence: INVALID（負値）", classify_contract_version_evidence(legacy_record), ContractVersionEvidence.INVALID)
print()


# ─── [テスト2] HumanReviewResolutionRecord シリアライズ ───

print("[テスト2] HumanReviewResolutionRecord シリアライズ")

rec = HumanReviewResolutionRecord(
    resolution=HumanReviewResolution.RETRY_ALLOWED, actor="operator-a", note="approved",
    resolved_at=datetime(2026, 1, 1, 0, 0, 0), opened_attempt_no=None,
)
roundtrip = HumanReviewResolutionRecord.from_dict(rec.to_dict())
check("2a. round-trip: resolution", roundtrip.resolution, HumanReviewResolution.RETRY_ALLOWED)
check("2b. round-trip: opened_attempt_no", roundtrip.opened_attempt_no, None)

check_raises(
    "2c. opened_attempt_no=0はValueError（正のintのみ許容）",
    lambda: HumanReviewResolutionRecord.from_dict({**rec.to_dict(), "opened_attempt_no": 0}),
    ValueError,
)
check_raises(
    "2d. opened_attempt_no=Trueはbool拒否でValueError",
    lambda: HumanReviewResolutionRecord.from_dict({**rec.to_dict(), "opened_attempt_no": True}),
    ValueError,
)
print()


# ─── [テスト3] resolve_human_review() ───

print("[テスト3] resolve_human_review()")

manager3 = make_lineage_manager()
_put_into_hrr(manager3, "run-3")

not_hrr = manager3.create_new_lineage("run-3b", make_monitor_record("run-3b"))
check_true("3a. HUMAN_REVIEW_REQUIRED以外はacknowledged=False", not manager3.resolve_human_review("run-3b", HumanReviewResolution.RETRY_ALLOWED, "op").acknowledged)

result3b = manager3.resolve_human_review("run-3", HumanReviewResolution.RETRY_ALLOWED, "operator-1", "approved")
check_true("3b. RETRY_ALLOWEDはacknowledged=True", result3b.acknowledged)

result3c = manager3.resolve_human_review("run-3", HumanReviewResolution.RETRY_ALLOWED, "operator-2", "different note")
check_true("3c. 同一decisionの再送はidempotent success", result3c.acknowledged)
check("3d. actor/noteは最初の記録のまま", manager3.peek("run-3").human_review_resolution.actor, "operator-1")

result3e = manager3.resolve_human_review("run-3", HumanReviewResolution.ABANDONED, "operator-3")
check_true("3e. conflicting resolutionはacknowledged=False", not result3e.acknowledged)
print()


# ─── [テスト4] open_next_attempt() HRR authorized拡張 ───

print("[テスト4] open_next_attempt() HRR authorized拡張")

manager4 = make_lineage_manager()
_put_into_hrr(manager4, "run-4")

unauthorized = manager4.open_next_attempt("run-4")
check_true("4a. resolutionなしのHRRはopen_next_attempt()拒否", not unauthorized.acknowledged)

manager4.resolve_human_review("run-4", HumanReviewResolution.RETRY_ALLOWED, "operator")
authorized = manager4.open_next_attempt("run-4")
check_true("4b. RETRY_ALLOWED後はopen_next_attempt()成功", authorized.acknowledged)
check("4c. attempt_no=2", authorized.attempt_no, 2)

record4 = manager4.peek("run-4")
check("4d. terminal_dispositionはNoneへクリア", record4.terminal_disposition, None)
check_true("4e. human_review_resolutionはクリアされず保持される", record4.human_review_resolution is not None)
check("4f. opened_attempt_noが新attempt番号と一致", record4.human_review_resolution.opened_attempt_no, 2)
check("4g. phase=READY_ELIGIBLE", record4.phase, RetryLineagePhase.READY_ELIGIBLE)

# mark_execution_started()でクリアされることを確認
claim_run4 = manager4.claim("run-4")
manager4.mark_execution_started("run-4", "run-4-attempt2", claim_run4.owner_token)
record4b = manager4.peek("run-4")
check("4h. mark_execution_started()後にhuman_review_resolutionがクリアされる", record4b.human_review_resolution, None)

# ABANDONED経路
manager4b = make_lineage_manager()
_put_into_hrr(manager4b, "run-4b")
manager4b.resolve_human_review("run-4b", HumanReviewResolution.ABANDONED, "operator")
abandoned_open = manager4b.open_next_attempt("run-4b")
check_true("4i. ABANDONEDはopen_next_attempt()を永続的に禁止", not abandoned_open.acknowledged)
print()


# ─── [テスト5] 通常のFAILED経路への非影響（回帰確認） ───

print("[テスト5] 通常のFAILED経路への非影響")

manager5 = make_lineage_manager()
created5 = manager5.create_new_lineage("run-5", make_monitor_record("run-5"))
claim_run5 = manager5.claim("run-5")
manager5.mark_execution_started("run-5", "run-5", claim_run5.owner_token)
manager5.mark_terminal("run-5", RetryLineageDisposition.FAILED, "run-5", [])
opened5 = manager5.open_next_attempt("run-5")
check_true("5a. 通常のFAILED経路は無改修のまま動作", opened5.acknowledged)
check("5b. human_review_resolutionはNoneのまま", manager5.peek("run-5").human_review_resolution, None)
print()


# ─── [テスト6] retry_after_human_review() ───

print("[テスト6] retry_after_human_review()")


class _FakeRetryManager:
    def __init__(self):
        self.retry_calls: list[tuple] = []

    def retry(self, run_id: str, attempt: int = 1, dry_run: bool = False):
        self.retry_calls.append((run_id, attempt))
        return ("RETRIED", run_id, attempt)


manager6 = make_lineage_manager()
_put_into_hrr(manager6, "run-6")
fake_retry_manager = _FakeRetryManager()

result6 = retry_after_human_review(manager6, fake_retry_manager, "run-6", HumanReviewResolution.RETRY_ALLOWED, "operator")
check("6a. end-to-endでmanager.retry()が呼ばれる", fake_retry_manager.retry_calls, [("run-6", 2)])
check("6b. 戻り値はmanager.retry()の結果", result6, ("RETRIED", "run-6", 2))

# crash-resume: 既にopened_attempt_no確定済みのREADY_ELIGIBLE状態から再度呼ぶ
fake_retry_manager2 = _FakeRetryManager()
manager6b = make_lineage_manager()
_put_into_hrr(manager6b, "run-6b")
manager6b.resolve_human_review("run-6b", HumanReviewResolution.RETRY_ALLOWED, "operator")
manager6b.open_next_attempt_after_human_review("run-6b")
# ここでdispatch前にクラッシュしたことを模擬（phase=READY_ELIGIBLE・opened_attempt_no確定済み）
result6b = retry_after_human_review(manager6b, fake_retry_manager2, "run-6b", HumanReviewResolution.RETRY_ALLOWED, "operator")
check("6c. crash-resume: resolve_human_review()を再度呼ばずdispatchのみ再開", fake_retry_manager2.retry_calls, [("run-6b", 2)])
print()


# ─── [テスト7] resolve_final_disposition()（13章） ───

print("[テスト7] resolve_final_disposition()")


class _FakeSafetyReport:
    def __init__(self, worst):
        self._worst = worst

    def worst_case(self):
        return self._worst


check(
    "7a. CONTRACT_VIOLATIONは常にHUMAN_REVIEW_REQUIRED",
    resolve_final_disposition([StepOutcomeCategory.GENUINE_SUCCESS], _FakeSafetyReport(SideEffectSafetyCategory.CONTRACT_VIOLATION)),
    RetryLineageDisposition.HUMAN_REVIEW_REQUIRED,
)
check(
    "7b. IN_PROGRESS_OR_UNKNOWNは常にHUMAN_REVIEW_REQUIRED",
    resolve_final_disposition([StepOutcomeCategory.GENUINE_SUCCESS], _FakeSafetyReport(SideEffectSafetyCategory.IN_PROGRESS_OR_UNKNOWN)),
    RetryLineageDisposition.HUMAN_REVIEW_REQUIRED,
)
check(
    "7c. CONFIRMED_SUCCESS + base=SUCCEEDEDはSUCCEEDEDのまま",
    resolve_final_disposition([StepOutcomeCategory.GENUINE_SUCCESS], _FakeSafetyReport(SideEffectSafetyCategory.CONFIRMED_SUCCESS)),
    RetryLineageDisposition.SUCCEEDED,
)
check(
    "7d. CONFIRMED_SUCCESS + base!=SUCCEEDEDはHUMAN_REVIEW_REQUIRED",
    resolve_final_disposition([StepOutcomeCategory.RETRYABLE_FAILURE], _FakeSafetyReport(SideEffectSafetyCategory.CONFIRMED_SUCCESS)),
    RetryLineageDisposition.HUMAN_REVIEW_REQUIRED,
)
check(
    "7e. SAFE_TO_CONTINUEはbase_dispositionをそのまま通す",
    resolve_final_disposition([StepOutcomeCategory.RETRYABLE_FAILURE], _FakeSafetyReport(SideEffectSafetyCategory.SAFE_TO_CONTINUE)),
    RetryLineageDisposition.FAILED,
)
check(
    "7f. NOT_APPLICABLEはbase_dispositionをそのまま通す",
    resolve_final_disposition([StepOutcomeCategory.GENUINE_SUCCESS], _FakeSafetyReport(SideEffectSafetyCategory.NOT_APPLICABLE)),
    RetryLineageDisposition.SUCCEEDED,
)
print()


# ─── [テスト8] SideEffectSafetyClassifier（10.2節） ───

print("[テスト8] SideEffectSafetyClassifier")

with tempfile.TemporaryDirectory() as tmpdir:
    d = Path(tmpdir)
    media_manager = ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(d / "media"))
    coordinator = build_media_upload_safety_coordinator(
        media_upload_manager=media_manager,
        applicability_store=JsonMediaUploadApplicabilityStore(d / "applicability"),
        attempt_context_store=JsonMediaUploadAttemptContextStore(d / "context"),
        locks_dir=d / "locks",
    )
    draft_store = JsonWordPressDraftStateStore(d / "wp")
    classifier = SideEffectSafetyClassifier(media_coordinator=coordinator, draft_state=draft_store)

    ops = [
        ProtectedOperationContext(ProtectedSideEffectKind.MEDIA_UPLOAD, SideEffectSite.NEWS_STEP, "art-1"),
        ProtectedOperationContext(ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION, SideEffectSite.NEWS_STEP, "art-1"),
    ]

    report8a = classifier.classify("root-1", 1, "member-1", ops)
    check(
        "8a. 未着手の両operationはCONTRACT_VIOLATION",
        set(report8a.categories()), {SideEffectSafetyCategory.CONTRACT_VIOLATION},
    )

    coordinator.record_not_applicable(
        __import__("side_effect_safety").SideEffectOperationIdentity(
            root_run_id="root-1", attempt_ordinal=1,
            operation_kind=ProtectedSideEffectKind.MEDIA_UPLOAD,
            effect_site=SideEffectSite.NEWS_STEP, operation_instance_key="art-1",
        ),
        "member-1",
    )
    report8b = classifier.classify("root-1", 1, "member-1", [ops[0]])
    check("8b. NOT_APPLICABLE markerはNOT_APPLICABLEへ写像", report8b.worst_case(), SideEffectSafetyCategory.NOT_APPLICABLE)

print()


# ─── 結果サマリー ───

print("=" * 60)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = sum(1 for status, _ in results_log if status == "FAIL")
print(f"結果: {passed} PASS / {failed} FAIL / 合計 {len(results_log)}")

for d in tmp_dirs:
    shutil.rmtree(d, ignore_errors=True)

if failed:
    print("失敗したテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
print("全テストPASS")
