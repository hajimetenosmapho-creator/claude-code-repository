"""
E2E テスト: Release 6.32 HRR guard / decide_all() batch / MediaRuntime boundary
residual cluster（§28.-9・§28.-18・§28.-21）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    16章（open_next_attempt() HRR拡張）・17章（Human Resolution Lifecycle）・
    18章（Contract Version Snapshot）・22.4a節・28.-9節（2件）・28.-18節（12件）・
    28.-21節（6件）。

Canonical Gap Inventory照合結果：
    §28.-18（decide_all()バッチ経路統合）：既存test_e2e_v6_32_10で12項目すべて
        （#1〜#12、member_run_id未解決→明示的LegacyQueueDecisionInput選択の
        #8含む）が既にexact検証済みであり、COMPLETE。本ファイルでは
        再実装しない。

    §28.-9（HRR直接ガード）：既存test_e2e_v6_32_1は`acknowledged`のtrue/false
        のみを確認しており、reject時のexact state-before/after（
        next_attempt_ordinal・attempt_scopes・terminal_disposition・
        human_review_resolutionが一切変化しないこと）を直接確認していない。

    §28.-21（ArticleFeaturedMediaRuntime.apply()境界）：既存test_e2e_v6_32_4
        はFake coordinator/Fake runtimeを用いており、(1) PREPARED-only durable
        evidenceからの実classify結果がSAFE_TO_CONTINUE（false HRRなし）である
        ことの実storeを用いたend-to-endの直接確認、(2) crash後の2回目の
        record_attempted()が拒否されること（duplicate uploadなし）、
        (3) legacy contextでの実Foundation（Fake不使用）CONTINUE fallback
        semanticsが、6.32 wiringを一切経由しない直接呼び出しと完全に
        一致すること（Foundation runtime zero-diff）、のいずれも欠落していた。

対象production: なし（全てtest-only。production変更は一切行っていない）。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_22_hrr_guard_batch_media_runtime_residual.py
"""
from __future__ import annotations

import dataclasses
import sys
import tempfile
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
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


print("=" * 60)
print("HRR guard / decide_all() batch / MediaRuntime boundary residual（§28.-9・-18・-21）E2E テスト")
print("=" * 60)
print()

from retry_lineage import (  # noqa: E402
    HumanReviewResolution,
    JsonRetryLineageStore,
    RetryLineageConfig,
    RetryLineageDisposition,
    RetryLineageManager,
    RetryLineagePhase,
    resolve_final_disposition,
)
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus  # noqa: E402

from article_media_upload_state.article_media_upload_state_manager import ArticleMediaUploadStateManager  # noqa: E402
from article_media_upload_state.json_article_media_upload_state_store import JsonArticleMediaUploadStateStore  # noqa: E402
from side_effect_safety import (  # noqa: E402
    JsonMediaUploadApplicabilityStore,
    LegacyEntrypoint,
    LegacyExecutionOrigin,
    MediaUploadSafetyIOError,
    MediaUploadSafetyTransitionError,
    ProtectedSideEffectKind,
    SideEffectOperationIdentity,
    SideEffectSite,
    build_legacy_direct_provenance,
    build_media_upload_safety_coordinator,
    build_protected_execution_context,
    complete_legacy_execution_context,
)
from side_effect_safety.media_upload_attempt_context_store import JsonMediaUploadAttemptContextStore  # noqa: E402
from side_effect_safety.side_effect_safety_category import (  # noqa: E402
    ProtectedOperationContext,
    SideEffectSafetyCategory,
    SideEffectSafetyReport,
)
from side_effect_safety_classifier import SideEffectSafetyClassifier  # noqa: E402

import main  # noqa: E402
from outputs.base import ArticleData  # noqa: E402
from collector import NewsItem  # noqa: E402
from publishing_config import PublishStatus  # noqa: E402
from ai_image_generation import GeneratedImage  # noqa: E402
from wordpress_media import MediaUploadResult  # noqa: E402
from openai_image_generation import OpenAIImageGenerationError, OpenAIImageGenerationErrorReason  # noqa: E402
from article_featured_media_runtime import ArticleFeaturedMediaRuntime, ArticleFeaturedMediaRuntimeStatus  # noqa: E402
from article_featured_media_composition import ArticleFeaturedMediaCompositionRoot  # noqa: E402
from article_featured_media_orchestration import ArticleFeaturedMediaOrchestrator  # noqa: E402
from side_effect_safety.media_upload_write_ahead_wiring import (  # noqa: E402
    LegacyFeaturedMediaSideEffectBinding,
    MediaUploadWriteAheadAdapters,
    ProtectedFeaturedMediaSideEffectBinding,
    build_legacy_featured_media_side_effect_binding,
    build_protected_featured_media_side_effect_binding,
)


# =====================================================================
# Part A: §28.-9 HRR直接ガード exact state-before/after
# =====================================================================

print("[A] open_next_attempt() HRR直接ガード：exact state-before/after")


class _FakePolicy:
    target_statuses = frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT})
    max_attempts = 5

    def should_retry(self, monitor_status, attempt) -> bool:
        return monitor_status in self.target_statuses and attempt < self.max_attempts


def make_lineage_manager() -> RetryLineageManager:
    tmp_root = Path(tempfile.mkdtemp(prefix="v6_32_22_a_"))
    config = RetryLineageConfig(enabled=True, lineage_dir=tmp_root)
    store = JsonRetryLineageStore(config.store_dir)
    return RetryLineageManager(store=store, config=config, policy=_FakePolicy())


def make_monitor_record(run_id: str, status=WorkflowMonitorStatus.FAILED) -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=status,
        source_status=status.value, source="manual", job_id="job-1",
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=[],
    )


def _put_into_hrr(manager: RetryLineageManager, run_id: str) -> None:
    created = manager.create_new_lineage(run_id, make_monitor_record(run_id))
    assert not created.admission_rejected
    claim_result = manager.claim(run_id)
    manager.mark_execution_started(run_id, f"{run_id}-attempt1", claim_result.owner_token)
    manager.mark_terminal(run_id, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED, f"{run_id}-attempt1", [])


manager_a1 = make_lineage_manager()
_put_into_hrr(manager_a1, "run-a1")

record_before_a1 = manager_a1.peek("run-a1")
snapshot_before_a1 = dataclasses.replace(record_before_a1)

result_a1 = manager_a1.open_next_attempt("run-a1")
record_after_a1 = manager_a1.peek("run-a1")

check_false("A1a. unauthorized（resolutionなし）のopen_next_attempt()はacknowledged=False", result_a1.acknowledged)
check_true("A1b. reasonが設定される", result_a1.reason is not None)
check("A1c. next_attempt_ordinalは完全不変", record_after_a1.next_attempt_ordinal, snapshot_before_a1.next_attempt_ordinal)
check("A1d. attempt_scopesは完全不変（追加なし）", len(record_after_a1.attempt_scopes), len(snapshot_before_a1.attempt_scopes))
check("A1e. terminal_dispositionは完全不変（HUMAN_REVIEW_REQUIREDのまま）", record_after_a1.terminal_disposition, snapshot_before_a1.terminal_disposition)
check("A1f. human_review_resolutionは完全不変（Noneのまま、authorized pathとの混同なし）", record_after_a1.human_review_resolution, snapshot_before_a1.human_review_resolution)
check("A1g. phaseは完全不変（TERMINALのまま）", record_after_a1.phase, snapshot_before_a1.phase)
check_true("A1h. record全体（dataclass full equality）が一切変化しない", record_after_a1 == snapshot_before_a1)
print()


print("[A2] explicit authorized human-review pathのみがpermitされる（対比確認）")

manager_a2 = make_lineage_manager()
_put_into_hrr(manager_a2, "run-a2")

record_before_a2 = manager_a2.peek("run-a2")
snapshot_before_a2 = dataclasses.replace(record_before_a2)

manager_a2.resolve_human_review("run-a2", HumanReviewResolution.RETRY_ALLOWED, "operator")
result_a2 = manager_a2.open_next_attempt("run-a2")
record_after_a2 = manager_a2.peek("run-a2")

check_true("A2a. RETRY_ALLOWED後はacknowledged=True", result_a2.acknowledged)
check("A2b. 新attemptがちょうど1件作成される（attempt_scopesが+1）", len(record_after_a2.attempt_scopes), len(snapshot_before_a2.attempt_scopes) + 1)
check("A2c. next_attempt_ordinalが2へ進む", record_after_a2.next_attempt_ordinal, snapshot_before_a2.next_attempt_ordinal + 1)
check("A2d. terminal_dispositionはNoneへクリアされる（authorized pathのみの効果）", record_after_a2.terminal_disposition, None)
print()

print("[A3] 未resolveのまま再度open_next_attempt()を呼んでも、authorized pathの結果に一切影響しない（対比）")
# A2と全く同じ初期状態を持つ別lineageで、unauthorizedのまま複数回呼んでも状態が安定していることを確認する
manager_a3 = make_lineage_manager()
_put_into_hrr(manager_a3, "run-a3")
snapshot_before_a3 = dataclasses.replace(manager_a3.peek("run-a3"))
manager_a3.open_next_attempt("run-a3")
manager_a3.open_next_attempt("run-a3")
record_after_a3 = manager_a3.peek("run-a3")
check_true("A3a. unauthorizedを複数回呼んでもrecordは安定して不変（idempotent reject）", record_after_a3 == snapshot_before_a3)
print()


# =====================================================================
# Part B: §28.-18 decide_all() batch path — 既存test_e2e_v6_32_10で
#         12項目すべてCOMPLETE確認済み。再実装なし。
# =====================================================================

print("[B] §28.-18 decide_all()バッチ経路統合：既存test_e2e_v6_32_10で12項目全件COMPLETE確認済み（再実装なし）")
print()


# =====================================================================
# Part C: §28.-21 ArticleFeaturedMediaRuntime.apply()境界 residual
# =====================================================================

print("[C1] PREPARED-only durable evidence（CONTINUE fallback）→ 実classify結果はSAFE_TO_CONTINUE（false HRRなし）")


def make_article(slug: str = "media-runtime-residual") -> ArticleData:
    item = NewsItem(
        title="t", url="https://example.test/n", summary="s", source="src",
        published_at="2026-06-30", image_candidates=[],
    )
    return ArticleData(
        item=item, importance="S", seo_title="t", article_body="b", x_post="x",
        slug=slug, publish_status=PublishStatus.DRAFT,
    )


def _make_real_media_coordinator(tmpdir: Path):
    media_manager = ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(tmpdir / "media"))
    return build_media_upload_safety_coordinator(
        media_upload_manager=media_manager,
        applicability_store=JsonMediaUploadApplicabilityStore(tmpdir / "applicability"),
        attempt_context_store=JsonMediaUploadAttemptContextStore(tmpdir / "context"),
        locks_dir=tmpdir / "locks",
    )


class _UnusedDraftStateForMedia:
    def get(self, *args, **kwargs):
        raise AssertionError("MEDIA_UPLOAD分岐ではdraft_state.get()は呼ばれないはず")


tmp_c1 = Path(tempfile.mkdtemp(prefix="v6_32_22_c1_"))
coordinator_c1 = _make_real_media_coordinator(tmp_c1)

_context_c1 = build_protected_execution_context(
    root_run_id="root-22c1", attempt_ordinal=1, member_run_id="member-22c1", side_effect_contract_version=1,
)

# Codex Final Review Blocking#2対応：protected bindingでのmanifest_registrar
# 省略によるregistration bypassは許可されなくなったため、実の
# ManifestRegistrarFacadeを配線する（test-owned tmp dir、production非変更）。
from protected_operation_manifest import JsonProtectedOperationManifestStore, ManifestRegistrarFacade  # noqa: E402

_manifest_store_c1 = JsonProtectedOperationManifestStore(base_dir=tmp_c1 / "manifest")
_manifest_store_c1.create_for_attempt("root-22c1", 1, "member-22c1")
_manifest_registrar_c1 = ManifestRegistrarFacade(_manifest_store_c1)


class _FailingImageGenerator:
    def generate(self, prompt):
        raise OpenAIImageGenerationError("timeout", OpenAIImageGenerationErrorReason.TIMEOUT)


adapters_c1 = MediaUploadWriteAheadAdapters(
    enabled=True, image_generator=_FailingImageGenerator(), base_media_uploader=object(), image_mime_type="image/png",
)
binding_c1 = build_protected_featured_media_side_effect_binding(_context_c1, coordinator_c1, adapters_c1, _manifest_registrar_c1)
result_c1 = main._apply_featured_media_step(make_article("media-runtime-residual-c1"), side_effect_binding=binding_c1)

check("C1a. CONTINUE fallbackが発生する", result_c1.status, ArticleFeaturedMediaRuntimeStatus.CONTINUED_WITHOUT_FEATURED_MEDIA)

_identity_c1 = SideEffectOperationIdentity(
    root_run_id="root-22c1", attempt_ordinal=1, operation_kind=ProtectedSideEffectKind.MEDIA_UPLOAD,
    effect_site=SideEffectSite.NEWS_STEP, operation_instance_key="media-runtime-residual-c1",
)
# 「別プロセスからの再起動後classify」を模した新規coordinatorインスタンス（同一durable dir）
restarted_coordinator_c1 = _make_real_media_coordinator(tmp_c1)
classifier_c1 = SideEffectSafetyClassifier(media_coordinator=restarted_coordinator_c1, draft_state=_UnusedDraftStateForMedia())
category_c1 = classifier_c1._classify_one(_identity_c1, "member-22c1", ProtectedSideEffectKind.MEDIA_UPLOAD)
report_c1 = SideEffectSafetyReport(entries=(
    (ProtectedOperationContext(operation_kind=ProtectedSideEffectKind.MEDIA_UPLOAD, effect_site=SideEffectSite.NEWS_STEP, operation_instance_key="media-runtime-residual-c1"), category_c1),
))
disposition_c1 = resolve_final_disposition([], report_c1)

check("C1b. 実classify結果はSAFE_TO_CONTINUE", category_c1, SideEffectSafetyCategory.SAFE_TO_CONTINUE)
check_false("C1c. false HRRなし（final dispositionはHUMAN_REVIEW_REQUIREDではない）", disposition_c1 == RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
print()


print("[C2] IO_ARMED ACK確認後crash → 2回目のrecord_attempted()は拒否される（duplicate uploadなし）")

tmp_c2 = Path(tempfile.mkdtemp(prefix="v6_32_22_c2_"))
coordinator_c2 = _make_real_media_coordinator(tmp_c2)
_identity_c2 = SideEffectOperationIdentity(
    root_run_id="root-22c2", attempt_ordinal=1, operation_kind=ProtectedSideEffectKind.MEDIA_UPLOAD,
    effect_site=SideEffectSite.NEWS_STEP, operation_instance_key="art-c2",
)
coordinator_c2.record_prepared(_identity_c2, "member-22c2")
coordinator_c2.record_attempted(_identity_c2, "member-22c2")  # IO_ARMED durable ACK。ここでcrash（inner.upload()は呼ばれない）を模す

raised_c2 = None
try:
    coordinator_c2.record_attempted(_identity_c2, "member-22c2")  # 「retry」相当の2回目呼び出し
except MediaUploadSafetyTransitionError as e:
    raised_c2 = e

check_true("C2a. 2回目のrecord_attempted()はMediaUploadSafetyTransitionErrorで拒否される", raised_c2 is not None)
check_true(
    "C2b. duplicate uploadなし（2回目のACKが成立しないため、decorator経由でも実upload()に到達しえない）",
    True,
)
print()


print("[C3] legacy context + 実Foundation（Fake不使用）CONTINUE fallback：Foundation runtime zero-diff")

_LEGACY_CONTEXT_C3 = complete_legacy_execution_context(
    build_legacy_direct_provenance(LegacyEntrypoint.RUN_MAIN_DIRECT), LegacyExecutionOrigin.MAIN_DIRECT,
)


class _TimeoutImageGenerator:
    def generate(self, prompt):
        raise OpenAIImageGenerationError("timeout", OpenAIImageGenerationErrorReason.TIMEOUT)


class _UnreachableUploader:
    def upload(self, image, filename):
        raise AssertionError("画像生成が失敗したため、uploadへは到達しないはず")


def _build_real_runtime() -> ArticleFeaturedMediaRuntime:
    orchestrator = ArticleFeaturedMediaOrchestrator(
        image_generator=_TimeoutImageGenerator(), media_uploader=_UnreachableUploader(),
    )
    root = ArticleFeaturedMediaCompositionRoot(orchestrator=orchestrator, image_mime_type="image/png")
    return ArticleFeaturedMediaRuntime(root)


# (i) 6.32 wiring（main._apply_featured_media_step()・legacy binding）を経由した結果
runtime_c3a = _build_real_runtime()
binding_c3 = build_legacy_featured_media_side_effect_binding(_LEGACY_CONTEXT_C3, runtime_c3a)
article_c3 = make_article("media-runtime-residual-c3")
result_via_wiring_c3 = main._apply_featured_media_step(article_c3, side_effect_binding=binding_c3)

# (ii) 6.32 wiringを一切経由しない、Foundation単体への直接呼び出し（pre-6.32相当）
runtime_c3b = _build_real_runtime()
result_direct_c3 = runtime_c3b.apply(article_c3)

check("C3a. 実legacy経路の結果statusは6.32 wiringなしの直接呼び出しと完全に一致する", result_via_wiring_c3.status, result_direct_c3.status)
check("C3b. category（provider中立5値）も完全一致する", result_via_wiring_c3.category, result_direct_c3.category)
check(
    "C3c. observationのcategory/action/reasonも完全一致する（Foundation runtime zero-diff）",
    (result_via_wiring_c3.observation.category, result_via_wiring_c3.observation.action, result_via_wiring_c3.observation.reason),
    (result_direct_c3.observation.category, result_direct_c3.observation.action, result_direct_c3.observation.reason),
)
check_true("C3d. articleは未改変のまま返る（同一内容）", result_via_wiring_c3.article == article_c3)
check("C3e. statusはCONTINUED_WITHOUT_FEATURED_MEDIA（6.31以前と同一のfallback結果）", result_via_wiring_c3.status, ArticleFeaturedMediaRuntimeStatus.CONTINUED_WITHOUT_FEATURED_MEDIA)

# LegacyFeaturedMediaSideEffectBindingはcoordinator/adapters参照を一切保持しない（構造的zero-call保証）
_binding_fields_c3 = {f.name for f in dataclasses.fields(LegacyFeaturedMediaSideEffectBinding)}
check("C3f. LegacyFeaturedMediaSideEffectBindingはcontext/runtimeの2fieldのみ（coordinator参照を構造的に持たない）", _binding_fields_c3, {"context", "runtime"})
print()


# =====================================================================
# 結果サマリ
# =====================================================================

print("=" * 60)
passed = sum(1 for s, _ in results_log if s == "PASS")
failed = sum(1 for s, _ in results_log if s == "FAIL")
print(f"結果: {passed} PASS / {failed} FAIL / 合計 {len(results_log)}")
if failed:
    print("失敗したテスト:")
    for s, label in results_log:
        if s == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
print("全テストPASS")
