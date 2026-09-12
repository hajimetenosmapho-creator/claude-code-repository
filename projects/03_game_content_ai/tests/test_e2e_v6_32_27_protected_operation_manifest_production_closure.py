"""
E2E テスト: Release 6.32 Phase 2 — Protected Operation Manifest Production Closure

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    docs/design/side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md
    （Approved Architecture Amendment、Round 10 APPROVED）

本テストは、Architecture Amendmentが定めるPLANNED IMPLEMENTATION TEST MATRIX
（§18）のうち、Phase 2 production remediationで最優先のdirect evidenceを検証する
focused testである。§18の全25項目を網羅するものではない（A/B/C呼び出し箇所自体の
zero-call fault injection・hard-crash durability testはこのファイルには含まれない
——production remediation reportのresidual concernを参照）。

検証する主要evidence:
    1. primary blocking closure：RetryExecutor.execute() / _reconcile_all_locked()
       が SideEffectSafetyClassifier.classify() → resolve_final_disposition() の
       実チェーンへ接続されていること（旧decide_disposition()/disposition_from_
       categories()のみでは検出できないPOST成功後confirmation前crashシナリオで、
       配線済みの場合のみHUMAN_REVIEW_REQUIREDが正しく発火することを直接対比する）。
    2. owner_token admission/release authority（stale/wrong/missing token拒否、
       stale A / current B race）。
    3. immutable per-execution manifest generation（同一key再利用なし、孤児
       manifest非再利用、create_for_attempt()直接重複呼び出しの拒否）。
    4. facade API surface（ManifestReaderFacade/ManifestRegistrarFacadeが
       create_for_attempt属性を持たない）。
    5. reconcile_all() administrative recovery（owner-less general release API
       が存在しないこと、CLAIMED orphan回収が実際に機能すること）。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_27_protected_operation_manifest_production_closure.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

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
print("Protected Operation Manifest — Phase 2 Production Closure E2E テスト")
print("=" * 70)
print()

from dataclasses import dataclass

from protected_operation_manifest import (
    JsonProtectedOperationManifestStore,
    ManifestReaderFacade,
    ManifestRegistrarFacade,
    ProtectedOperationManifestContractViolationError,
    build_manifest_entry,
)
from retry_engine import RetryExecutor, RetryManager, RetryOutcome, RetryRequest
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
from article_media_upload_state import ArticleMediaUploadStateManager, JsonArticleMediaUploadStateStore
from wordpress_draft_state import JsonWordPressDraftStateStore
from workflow_engine import ALL_WORKFLOW_ENGINE_STEPS, WorkflowEngineResult, WorkflowEngineStep, WorkflowEngineStepResult
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus

tmp_dirs: list[Path] = []


@dataclass
class FakeAgentResult:
    success: bool
    action_taken: bool | None
    error_message: str | None = None

    def to_dict(self):
        return {"success": self.success, "action_taken": self.action_taken}


def make_step_result(step, executed, success, action_taken=None):
    ar = FakeAgentResult(success=success, action_taken=action_taken) if executed else None
    return WorkflowEngineStepResult(
        step=step, executed=executed, agent_result=ar, success=success,
        skipped_reason=None if executed else "skipped",
    )


class FakePolicy:
    def __init__(self, max_attempts: int = 3):
        self.target_statuses = frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT})
        self._max_attempts = max_attempts

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    def should_retry(self, monitor_status, attempt: int) -> bool:
        return monitor_status in self.target_statuses and attempt < self._max_attempts


def make_monitor_record(run_id: str, monitor_status=WorkflowMonitorStatus.FAILED, steps=None) -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=monitor_status,
        source_status=monitor_status.value, source="manual", job_id="job-1",
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=steps or [],
    )


def make_stack(policy=None, with_side_effect_wiring=True):
    """RetryLineageManager + (Option) manifest/classifier をtmp dirへ構築する。"""
    tmp_root = Path(tempfile.mkdtemp())
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

    if with_side_effect_wiring:
        lineage = RetryLineageManager(
            store=lineage_store, config=lineage_config, policy=policy or FakePolicy(),
            manifest=manifest_store, side_effect_classifier=classifier,
        )
    else:
        lineage = RetryLineageManager(store=lineage_store, config=lineage_config, policy=policy or FakePolicy())

    return lineage, manifest_store, draft_state_store, classifier, tmp_root


class DraftCreationEngine:
    """呼び出し箇所Aを模す（実際のWORDPRESS_DRAFT_CREATION write-aheadを
    manifest登録の直後に行うFake .run()）。member_run_idごとに新しいkeyで
    manifest登録・draft state作成を行う——実call siteの順序契約
    （manifest登録 → 既存write-ahead → 外部I/O）をそのまま模す。"""

    def __init__(self, manifest_store, draft_state_store, slug: str, confirm: bool):
        self._manifest = manifest_store
        self._draft_state = draft_state_store
        self._slug = slug
        self._confirm = confirm  # Trueならtransition_to_confirmed()まで行う（正常系）。
                                  # Falseならcreate_attempted()のみ（POST後confirmation前crash相当）。
        self.calls = 0

    def run(self, event, dry_run=False, target_step_filter=None, post_admission_hook=None,
            correlation_metadata=None, side_effect_execution_provenance=None):
        self.calls += 1
        run_id = f"exec-run-{self.calls}"
        root_run_id = event.job_id
        if post_admission_hook is not None:
            post_admission_hook(run_id)

        identity = SideEffectOperationIdentity(
            root_run_id=root_run_id, attempt_ordinal=1,
            operation_kind=ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION,
            effect_site=SideEffectSite.NEWS_STEP, operation_instance_key=self._slug,
        )
        # Step 1（呼び出し箇所Aの模倣）：manifest登録 → 既存write-ahead。
        self._manifest.register(
            root_run_id, 1, run_id,
            build_manifest_entry(ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION, SideEffectSite.NEWS_STEP, self._slug),
        )
        self._draft_state.create_attempted(identity, run_id, datetime.now().isoformat())
        if self._confirm:
            self._draft_state.transition_to_confirmed(identity, run_id, 12345, datetime.now().isoformat())

        steps = [make_step_result(s, executed=True, success=True, action_taken=True) for s in ALL_WORKFLOW_ENGINE_STEPS]
        return WorkflowEngineResult(
            run_id=run_id, steps=steps, overall_success=True, stopped_early=False,
            started_at=datetime.now(), finished_at=datetime.now(),
        )


# =====================================================================
# グループ1：primary blocking closure
# =====================================================================
print("[グループ1] primary blocking closure（RetryExecutor.execute()実チェーン）")

# 1a: 配線あり・POST成功後confirmation前crash相当（confirm=False）→ HRR
lineage_1a, manifest_1a, draft_state_1a, classifier_1a, _ = make_stack()
created_1a = lineage_1a.create_new_lineage("run-1a", make_monitor_record("run-1a"))
check_true("1a前提: create_new_lineage()成功", not created_1a.admission_rejected)
claim_1a = lineage_1a.claim("run-1a")
check_true("1a前提: claim()成功・owner_token非空", claim_1a.acknowledged and bool(claim_1a.owner_token))
engine_1a = DraftCreationEngine(manifest_1a, draft_state_1a, slug="article-1a", confirm=False)
executor_1a = RetryExecutor(workflow_engine_manager=engine_1a, lineage=lineage_1a, manifest=ManifestReaderFacade(manifest_1a), side_effect_classifier=classifier_1a)
request_1a = RetryRequest(run_id="run-1a", attempt=1, requested_at=datetime.now(), dry_run=False)
result_1a = executor_1a.execute(request_1a, created_1a.lineage, claim_1a)
check("1a. 配線あり・confirmation前crash → disposition=HUMAN_REVIEW_REQUIRED（primary blocking finding closure）",
      lineage_1a.peek("run-1a").terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)

# 1b: Codex Final Review Blocking#1対応（旧: 配線なしフォールバック・同一
# シナリオ→旧decide_disposition()のままSUCCEEDEDへ倒れる、というMotivating
# Findingの再現テストだった）。protected lineage（side_effect_contract_version
# is not None）でmanifest/classifierが欠落している場合、production側は
# 決してstep-only fallbackへ降格せず、fail-closedでHUMAN_REVIEW_REQUIREDへ
# 確定するよう修正された。本テストはこの新しい契約を直接証明する
# （primary blocking findingが再導入されていないことの回帰確認）。
lineage_1b, manifest_1b, draft_state_1b, classifier_1b, _ = make_stack(with_side_effect_wiring=False)
created_1b = lineage_1b.create_new_lineage("run-1b", make_monitor_record("run-1b"))
claim_1b = lineage_1b.claim("run-1b")
engine_1b = DraftCreationEngine(manifest_1b, draft_state_1b, slug="article-1b", confirm=False)
executor_1b = RetryExecutor(workflow_engine_manager=engine_1b, lineage=lineage_1b)  # manifest/classifier省略
request_1b = RetryRequest(run_id="run-1b", attempt=1, requested_at=datetime.now(), dry_run=False)
result_1b = executor_1b.execute(request_1b, created_1b.lineage, claim_1b)
check("1b. protected lineage・manifest/classifier省略 → 決してSUCCEEDEDへstep-only fallbackせず、"
      "fail-closedでHUMAN_REVIEW_REQUIREDへ確定する（Blocking#1: primary blocking finding再導入防止）",
      lineage_1b.peek("run-1b").terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check_true("1b-note. decide_disposition()由来のSUCCEEDED/FAILED/NOT_ACTIONEDのいずれでもない（step-only判定は一切使われない）",
           lineage_1b.peek("run-1b").terminal_disposition == RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)

# 1c: 配線あり・正常系（confirm=True）→ SUCCEEDED（誤ってHRRへ倒れないことの確認）
lineage_1c, manifest_1c, draft_state_1c, classifier_1c, _ = make_stack()
created_1c = lineage_1c.create_new_lineage("run-1c", make_monitor_record("run-1c"))
claim_1c = lineage_1c.claim("run-1c")
engine_1c = DraftCreationEngine(manifest_1c, draft_state_1c, slug="article-1c", confirm=True)
executor_1c = RetryExecutor(workflow_engine_manager=engine_1c, lineage=lineage_1c, manifest=ManifestReaderFacade(manifest_1c), side_effect_classifier=classifier_1c)
request_1c = RetryRequest(run_id="run-1c", attempt=1, requested_at=datetime.now(), dry_run=False)
result_1c = executor_1c.execute(request_1c, created_1c.lineage, claim_1c)
check("1c. 配線あり・正常系（confirmed） → disposition=SUCCEEDED（恒常的HRR化していないことの回帰）",
      lineage_1c.peek("run-1c").terminal_disposition, RetryLineageDisposition.SUCCEEDED)

# 1d: restart/reconciliation path（_reconcile_all_locked()実チェーン）
lineage_1d, manifest_1d, draft_state_1d, classifier_1d, _ = make_stack()
created_1d = lineage_1d.create_new_lineage("run-1d", make_monitor_record("run-1d"))
claim_1d = lineage_1d.claim("run-1d")
engine_1d = DraftCreationEngine(manifest_1d, draft_state_1d, slug="article-1d", confirm=False)
executor_1d_probe = RetryExecutor(workflow_engine_manager=engine_1d, lineage=lineage_1d)
# post_admission_hookのみ発火させ、EXECUTION_STARTEDへ遷移させる（disposition確定は
# reconcile側に委ねるため、Executorのdisposition計算より前のraw hookを直接使う）。
lineage_1d.mark_execution_started("run-1d", "exec-run-1d", claim_1d.owner_token)
manifest_1d.register(
    "run-1d", 1, "exec-run-1d",
    build_manifest_entry(ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION, SideEffectSite.NEWS_STEP, "article-1d"),
)
identity_1d = SideEffectOperationIdentity(
    root_run_id="run-1d", attempt_ordinal=1, operation_kind=ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION,
    effect_site=SideEffectSite.NEWS_STEP, operation_instance_key="article-1d",
)
draft_state_1d.create_attempted(identity_1d, "exec-run-1d", datetime.now().isoformat())  # confirmしない＝crash相当
check("1d前提: phase=EXECUTION_STARTED", lineage_1d.peek("run-1d").phase, RetryLineagePhase.EXECUTION_STARTED)

monitor_record_1d = make_monitor_record("exec-run-1d", WorkflowMonitorStatus.SUCCESS)
summary_1d = lineage_1d.reconcile_all(lambda run_id: monitor_record_1d if run_id == "exec-run-1d" else None)
check_false("1d. reconcile_all()はskipped=False", summary_1d.skipped)
check("1d. restart reconciliation実チェーン → disposition=HUMAN_REVIEW_REQUIRED（_reconcile_all_locked()のclassifier配線closure）",
      lineage_1d.peek("run-1d").terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("1d. HRRは次のattemptを自動的に開かない（既存二重ガード、phase=TERMINALのまま）",
      lineage_1d.peek("run-1d").phase, RetryLineagePhase.TERMINAL)
print()


# =====================================================================
# グループ2：owner_token authority
# =====================================================================
print("[グループ2] owner_token admission/release authority")

lineage_2, _, _, _, _ = make_stack(with_side_effect_wiring=False)
lineage_2.create_new_lineage("run-2", make_monitor_record("run-2"))
claim_2 = lineage_2.claim("run-2")
check_true("2前提: claim()成功", claim_2.acknowledged)
check_true("2a. ClaimResult.owner_tokenがnon-empty str", isinstance(claim_2.owner_token, str) and len(claim_2.owner_token) > 0)

check_false("2b. mark_execution_started(): owner_token=None → reject", lineage_2.mark_execution_started("run-2", "x", None))
check_false("2c. mark_execution_started(): owner_token='' → reject", lineage_2.mark_execution_started("run-2", "x", ""))
check_false("2d. mark_execution_started(): wrong owner_token → reject", lineage_2.mark_execution_started("run-2", "x", "wrong-token"))
check("2e. reject後もdurable phaseはCLAIMEDのまま", lineage_2.peek("run-2").phase, RetryLineagePhase.CLAIMED)
check_true("2f. mark_execution_started(): 正当なowner_token → 成功", lineage_2.mark_execution_started("run-2", "exec-run-2", claim_2.owner_token))

check_false("2g. release_claim(): owner_token=None → reject", lineage_2.release_claim("run-2", None))
check_false("2h. release_claim(): wrong owner_token → reject", lineage_2.release_claim("run-2", "wrong-token"))

# stale A / current B race
lineage_3, _, _, _, _ = make_stack(with_side_effect_wiring=False)
lineage_3.create_new_lineage("run-3", make_monitor_record("run-3"))
claim_a = lineage_3.claim("run-3")
owner_a = claim_a.owner_token
check_true("3前提: claim A成功", claim_a.acknowledged)
# Aがpost-admission hookへ到達する前にクラッシュ（CLAIMEDのまま放置）→
# reconcile_all()のCLAIMED orphan回収（owner-less administrative recovery）でBへ。
summary_recover_a = lineage_3.reconcile_all(lambda run_id: None)
check("3a. reconcile_all(): CLAIMED orphan（claim A）を1件回収", summary_recover_a.released_count, 1)
check("3b. 回収後phase=READY_ELIGIBLE", lineage_3.peek("run-3").phase, RetryLineagePhase.READY_ELIGIBLE)
claim_b = lineage_3.claim("run-3")
owner_b = claim_b.owner_token
check_true("3c前提: claim B成功", claim_b.acknowledged)
check_true("3d. owner_token A != owner_token B", owner_a != owner_b)
check_false("3e. stale A（旧owner_token）がmark_execution_started()できない", lineage_3.mark_execution_started("run-3", "x", owner_a))
check_false("3f. stale A（旧owner_token）がrelease_claim()でBを解除できない", lineage_3.release_claim("run-3", owner_a))
check("3g. claim Bはowner_token Bのまま変化しない", lineage_3.peek("run-3").owner_token, owner_b)
check("3h. phaseはCLAIMEDのまま（Bの正当なclaimが誤って解除されていない）", lineage_3.peek("run-3").phase, RetryLineagePhase.CLAIMED)
check_true("3i. 正当なowner_token Bでのrelease_claim()は成功する", lineage_3.release_claim("run-3", owner_b))
print()


# =====================================================================
# グループ3：immutable per-execution manifest generation
# =====================================================================
print("[グループ3] immutable per-execution manifest generation（rebindなし）")

lineage_4, manifest_4, _, _, _ = make_stack()
lineage_4.create_new_lineage("run-4", make_monitor_record("run-4"))
claim_4a = lineage_4.claim("run-4")
check_true("4a前提: claim A成功", claim_4a.acknowledged)
# claim Aをpost-admission hook到達前に放棄（manifest作成前でクラッシュ相当）。
released_4 = lineage_4.reconcile_all(lambda run_id: None)
check("4a. CLAIMED orphan（manifest未作成のまま）を回収", released_4.released_count, 1)

claim_4b = lineage_4.claim("run-4")
check_true("4b前提: claim B成功", claim_4b.acknowledged)
check_true("4b. mark_execution_started() → 新しいmember_run_idで新しいmanifestが作成される",
           lineage_4.mark_execution_started("run-4", "exec-run-4b", claim_4b.owner_token))
entries_4b = manifest_4.list_for_attempt("run-4", 1, "exec-run-4b")
check("4c. 新manifestはentries=()で作成されている", entries_4b, ())

# 孤児manifest非再利用の直接確認：同一lineageを再度CLAIMEDへ戻し、放棄・回収・
# 再claimしてmark_execution_started()するたびに、必ず異なるmember_run_idの
# manifestが作られ、古いものは変更されない。
lineage_5, manifest_5, _, _, _ = make_stack()
lineage_5.create_new_lineage("run-5", make_monitor_record("run-5"))
claim_5a = lineage_5.claim("run-5")
check_true("5a前提: claim成功", lineage_5.mark_execution_started("run-5", "exec-run-5a", claim_5a.owner_token))
entries_5a_before = manifest_5.list_for_attempt("run-5", 1, "exec-run-5a")
lineage_5.mark_terminal("run-5", RetryLineageDisposition.FAILED, "exec-run-5a", [])
opened_5 = lineage_5.open_next_attempt("run-5")
check_true("5b前提: open_next_attempt()成功（attempt_ordinal=2へ）", opened_5.acknowledged)
claim_5b = lineage_5.claim("run-5")
check_true("5c前提: attempt2 claim成功", lineage_5.mark_execution_started("run-5", "exec-run-5b", claim_5b.owner_token))
entries_5b = manifest_5.list_for_attempt("run-5", 2, "exec-run-5b")
check("5d. attempt1のmanifest（exec-run-5a）はattempt2実行後も変化しない（再読み出しで同一内容）",
      manifest_5.list_for_attempt("run-5", 1, "exec-run-5a"), entries_5a_before)
check("5e. attempt2は独立したmanifestキー（attempt_ordinal=2）で成功", entries_5b, ())

# create_for_attempt()の直接重複呼び出し → 常にContractViolationError（rebindしない）
raised_dup = None
try:
    manifest_5.create_for_attempt("run-5", 1, "exec-run-5a")  # 既存キーへの重複create
except ProtectedOperationManifestContractViolationError:
    raised_dup = "ContractViolationError"
except Exception as e:  # pragma: no cover - 想定外の例外型を明示的に検出する
    raised_dup = f"unexpected:{type(e).__name__}"
check("6. create_for_attempt()の直接重複呼び出しはProtectedOperationManifestContractViolationError（rebindしない）",
      raised_dup, "ContractViolationError")
entries_after_dup_attempt = manifest_5.list_for_attempt("run-5", 1, "exec-run-5a")
check("6b. 重複create試行後もentriesは変化しない（no-op、fail-closed）", entries_after_dup_attempt, entries_5a_before)
print()


# =====================================================================
# グループ4：facade API surface
# =====================================================================
print("[グループ4] facade API surface（concrete facade、Codex Round 10 wording整合）")

reader_facade = ManifestReaderFacade(manifest_4)
registrar_facade = ManifestRegistrarFacade(manifest_4)

check_false("7a. ManifestReaderFacadeはcreate_for_attempt属性を持たない", hasattr(reader_facade, "create_for_attempt"))
check_false("7b. ManifestRegistrarFacadeはcreate_for_attempt属性を持たない", hasattr(registrar_facade, "create_for_attempt"))
check_true("7c. ManifestReaderFacadeはlist_for_attempt属性を持つ", hasattr(reader_facade, "list_for_attempt"))
check_true("7d. ManifestRegistrarFacadeはregister属性を持つ", hasattr(registrar_facade, "register"))
check_false("7e. ManifestReaderFacadeはregister属性を持たない（read専用）", hasattr(reader_facade, "register"))
check_false("7f. ManifestRegistrarFacadeはlist_for_attempt属性を持たない（register専用）", hasattr(registrar_facade, "list_for_attempt"))

public_non_mangled_reader = [n for n in dir(reader_facade) if not n.startswith("_")]
check("7g. ManifestReaderFacadeのpublic属性はlist_for_attemptのみ", sorted(public_non_mangled_reader), ["list_for_attempt"])
public_non_mangled_registrar = [n for n in dir(registrar_facade) if not n.startswith("_")]
check("7h. ManifestRegistrarFacadeのpublic属性はregisterのみ", sorted(public_non_mangled_registrar), ["register"])
print()


# =====================================================================
# グループ5：reconcile_all() administrative recovery / owner-less API不在
# =====================================================================
print("[グループ5] reconcile_all() administrative recovery、owner-less general release APIの不在")

lineage_8, _, _, _, _ = make_stack(with_side_effect_wiring=False)
public_methods_8 = [n for n in dir(lineage_8) if not n.startswith("_")]
check_false(
    "8a. RetryLineageManagerに独立した owner-less orphan release メソッドが存在しない",
    any("release_orphan" in n or "orphan_claim" in n for n in public_methods_8),
)
private_methods_8 = [n for n in dir(lineage_8) if n.startswith("_") and not n.startswith("__")]
check_false(
    "8b. private methodとしても独立したorphan release APIが存在しない（インライン化の構造的証拠）",
    any("release_orphan" in n or "orphan_claim" in n for n in private_methods_8),
)

lineage_9, _, _, _, _ = make_stack(with_side_effect_wiring=False)
lineage_9.create_new_lineage("run-9", make_monitor_record("run-9"))
claim_9 = lineage_9.claim("run-9")
check_true("9前提: claim成功、phase=CLAIMED", lineage_9.peek("run-9").phase == RetryLineagePhase.CLAIMED)
summary_9 = lineage_9.reconcile_all(lambda run_id: None)
check_false("9a. reconcile_all()はskipped=False", summary_9.skipped)
check("9b. reconcile_all()がCLAIMED orphanを1件、owner_tokenなしで正しく回収する（administrative recovery）",
      summary_9.released_count, 1)
check("9c. 回収後phase=READY_ELIGIBLE", lineage_9.peek("run-9").phase, RetryLineagePhase.READY_ELIGIBLE)
check("9d. 回収後owner_token=None", lineage_9.peek("run-9").owner_token, None)
print()


# =====================================================================
# グループDEP：Codex Final Review Blocking#1 — protected lineageのmissing
# dependency（manifest/classifier）はfail-closedでHRRへ確定し、決して
# step-only fallback（decide_disposition() / disposition_from_categories()）
# へ降格しない。sync（RetryExecutor.execute()）・restart
# （RetryLineageManager.reconcile_all()）の両方で直接証明する。
# =====================================================================
print("[グループDEP] Codex Final Review Blocking#1: protected + missing dependency → fail-closed HRR")

import retry_engine.retry_executor as _retry_executor_module
import retry_lineage.retry_lineage_manager as _retry_lineage_manager_module


def _raise_if_called(*a, **kw):
    raise AssertionError("protected + missing dependencyのケースでstep-only fallbackが呼ばれた（Blocking#1再導入）")


def make_engine_no_registration(member_run_id: str):
    """DraftCreationEngineと異なり、manifest登録・draft_state登録を一切
    行わない（missing-dependencyシナリオでは呼び出し箇所自体がmanifestへ
    到達しない構成のため、実装上register()呼び出しは不要——admission
    自体がmanifest欠落時は成立しないことを別途§18 test#13で証明済み。
    ここではRetryExecutor.execute()の disposition算出ロジックのみを対象と
    する）。"""
    class _Engine:
        def run(self, event, dry_run=False, target_step_filter=None, post_admission_hook=None,
                 correlation_metadata=None, side_effect_execution_provenance=None):
            run_id = member_run_id
            if post_admission_hook is not None:
                post_admission_hook(run_id)
            steps = [make_step_result(s, executed=True, success=True, action_taken=True) for s in ALL_WORKFLOW_ENGINE_STEPS]
            return WorkflowEngineResult(
                run_id=run_id, steps=steps, overall_success=True, stopped_early=False,
                started_at=datetime.now(), finished_at=datetime.now(),
            )
    return _Engine()


# --- A: protected + manifest=None（classifierは存在） -----------------
print("[DEP-A] protected + manifest=None（sync/restart）")

lineage_depA, manifest_depA, draft_state_depA, classifier_depA, _ = make_stack()
lineage_depA.create_new_lineage("run-depA", make_monitor_record("run-depA"))
claim_depA = lineage_depA.claim("run-depA")
executor_depA = RetryExecutor(
    workflow_engine_manager=make_engine_no_registration("exec-depA"), lineage=lineage_depA,
    manifest=None, side_effect_classifier=classifier_depA,
)
with patch.object(_retry_executor_module, "decide_disposition", side_effect=_raise_if_called), \
     patch.object(_retry_executor_module, "resolve_final_disposition", side_effect=_raise_if_called):
    executor_depA.execute(RetryRequest(run_id="run-depA", attempt=1, requested_at=datetime.now(), dry_run=False),
                           lineage_depA.peek("run-depA"), claim_depA)
check("DEP-A1(sync). manifest=None → disposition=HUMAN_REVIEW_REQUIRED",
      lineage_depA.peek("run-depA").terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
summary_depA = lineage_depA.reconcile_all(lambda run_id: None)
check("DEP-A2(sync). next automatic retryが開かない（opened_count=0）", summary_depA.opened_count, 0)

lineage_depA2, manifest_depA2, draft_state_depA2, classifier_depA2, _ = make_stack()
lineage_depA2.create_new_lineage("run-depA2", make_monitor_record("run-depA2"))
claim_depA2 = lineage_depA2.claim("run-depA2")
lineage_depA2.mark_execution_started("run-depA2", "exec-depA2", claim_depA2.owner_token)
lineage_depA2._manifest = None  # restart path用：直接manifest依存を欠落させる
with patch.object(_retry_lineage_manager_module, "disposition_from_categories", side_effect=_raise_if_called), \
     patch.object(_retry_lineage_manager_module, "resolve_final_disposition", side_effect=_raise_if_called):
    summary_depA2 = lineage_depA2.reconcile_all(lambda run_id: make_monitor_record("run-depA2") if run_id == "exec-depA2" else None)
check("DEP-A1(restart). manifest=None → disposition=HUMAN_REVIEW_REQUIRED",
      lineage_depA2.peek("run-depA2").terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("DEP-A2(restart). 同一reconcile_all()呼び出し内でopened_count=0", summary_depA2.opened_count, 0)
print()


# --- B: protected + classifier=None（manifestは存在） ------------------
print("[DEP-B] protected + side_effect_classifier=None（sync/restart）")

lineage_depB, manifest_depB, draft_state_depB, classifier_depB, _ = make_stack()
lineage_depB.create_new_lineage("run-depB", make_monitor_record("run-depB"))
claim_depB = lineage_depB.claim("run-depB")
executor_depB = RetryExecutor(
    workflow_engine_manager=make_engine_no_registration("exec-depB"), lineage=lineage_depB,
    manifest=ManifestReaderFacade(manifest_depB), side_effect_classifier=None,
)
with patch.object(_retry_executor_module, "decide_disposition", side_effect=_raise_if_called), \
     patch.object(_retry_executor_module, "resolve_final_disposition", side_effect=_raise_if_called):
    executor_depB.execute(RetryRequest(run_id="run-depB", attempt=1, requested_at=datetime.now(), dry_run=False),
                           lineage_depB.peek("run-depB"), claim_depB)
check("DEP-B1(sync). classifier=None → disposition=HUMAN_REVIEW_REQUIRED",
      lineage_depB.peek("run-depB").terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
summary_depB = lineage_depB.reconcile_all(lambda run_id: None)
check("DEP-B2(sync). next automatic retryが開かない（opened_count=0）", summary_depB.opened_count, 0)

lineage_depB2, manifest_depB2, draft_state_depB2, classifier_depB2, _ = make_stack()
lineage_depB2.create_new_lineage("run-depB2", make_monitor_record("run-depB2"))
claim_depB2 = lineage_depB2.claim("run-depB2")
lineage_depB2.mark_execution_started("run-depB2", "exec-depB2", claim_depB2.owner_token)
lineage_depB2._side_effect_classifier = None  # restart path用：直接classifier依存を欠落させる
with patch.object(_retry_lineage_manager_module, "disposition_from_categories", side_effect=_raise_if_called), \
     patch.object(_retry_lineage_manager_module, "resolve_final_disposition", side_effect=_raise_if_called):
    summary_depB2 = lineage_depB2.reconcile_all(lambda run_id: make_monitor_record("run-depB2") if run_id == "exec-depB2" else None)
check("DEP-B1(restart). classifier=None → disposition=HUMAN_REVIEW_REQUIRED",
      lineage_depB2.peek("run-depB2").terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("DEP-B2(restart). 同一reconcile_all()呼び出し内でopened_count=0", summary_depB2.opened_count, 0)
print()


# --- C: protected + 両方欠落（1bのsync評価を再利用しつつrestart側を追加） ---
print("[DEP-C] protected + manifest/classifier両方None（sync/restart）")

check("DEP-C1(sync). 両方None → disposition=HUMAN_REVIEW_REQUIRED（グループ1・test1bと同一シナリオの再確認）",
      lineage_1b.peek("run-1b").terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
summary_1b_reconcile = lineage_1b.reconcile_all(lambda run_id: None)
check("DEP-C2(sync). next automatic retryが開かない（opened_count=0）", summary_1b_reconcile.opened_count, 0)

lineage_depC2, manifest_depC2, draft_state_depC2, classifier_depC2, _ = make_stack()
lineage_depC2.create_new_lineage("run-depC2", make_monitor_record("run-depC2"))
claim_depC2 = lineage_depC2.claim("run-depC2")
lineage_depC2.mark_execution_started("run-depC2", "exec-depC2", claim_depC2.owner_token)
lineage_depC2._manifest = None
lineage_depC2._side_effect_classifier = None
with patch.object(_retry_lineage_manager_module, "disposition_from_categories", side_effect=_raise_if_called), \
     patch.object(_retry_lineage_manager_module, "resolve_final_disposition", side_effect=_raise_if_called):
    summary_depC2 = lineage_depC2.reconcile_all(lambda run_id: make_monitor_record("run-depC2") if run_id == "exec-depC2" else None)
check("DEP-C1(restart). 両方None → disposition=HUMAN_REVIEW_REQUIRED",
      lineage_depC2.peek("run-depC2").terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("DEP-C2(restart). 同一reconcile_all()呼び出し内でopened_count=0", summary_depC2.opened_count, 0)
print()


# --- D: legacy lineage（side_effect_contract_version is None）は既存step-only ---
#        fallbackを引き続き維持する（regression protection、混同しない）。
print("[DEP-D] legacy lineage（contract_version=None）+ 依存欠落 → 既存step-only fallbackを維持")

lineage_depD, manifest_depD, draft_state_depD, classifier_depD, _ = make_stack()
created_depD = lineage_depD.create_new_lineage("run-depD", make_monitor_record("run-depD"))
# 直接recordを書き換えてlegacy（contract_version=None）を模す
# （create_new_lineage()は常にstampするため、公開APIには存在しない経路）。
record_depD = lineage_depD.peek("run-depD")
record_depD.side_effect_contract_version = None
lineage_depD._store.save(record_depD)
claim_depD = lineage_depD.claim("run-depD")
executor_depD = RetryExecutor(
    workflow_engine_manager=make_engine_no_registration("exec-depD"), lineage=lineage_depD,
    manifest=None, side_effect_classifier=None,
)
executor_depD.execute(RetryRequest(run_id="run-depD", attempt=1, requested_at=datetime.now(), dry_run=False),
                       lineage_depD.peek("run-depD"), claim_depD)
check("DEP-D1(sync). legacy + 依存欠落 → 既存step-only判定でSUCCEEDED（HRRへ誤って倒れない、既存互換性維持）",
      lineage_depD.peek("run-depD").terminal_disposition, RetryLineageDisposition.SUCCEEDED)
print()


# =====================================================================
# 結果サマリー
# =====================================================================
print("=" * 70)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = sum(1 for status, _ in results_log if status == "FAIL")
print(f"結果: {passed} PASS / {failed} FAIL / 合計 {len(results_log)}")
if failed:
    print("失敗したテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
print("全テストPASS")
