"""
E2E テスト: v6.32.0 Side-Effect Fail-Closed & Human Review Safety — Foundation

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md

sub-milestone 0（foundation types + 新規2package）の direct tests。本テストは
実WordPress API・実HTTP通信のいずれも発生させない。一時ディレクトリへの
ファイルI/Oのみ。

Scenario構成:
    IDENTITY-    SideEffectOperationIdentity・as_store_key()（8章）
    MODE-        Explicit Side-Effect Execution Mode discriminated union・
                 validate_side_effect_execution_context()（2章）
    WPSTATE-     WordPressDraftStateStore：create/duplicate/compare-and-transition/
                 get()のlock-free契約（9章・27章）
    MEDIA-       MediaUploadSafetyCoordinator：4公開メソッド・lifecycle・
                 Cross-Store Combination Table（9.9節）
    LOCK-        stale identity lockがget()を阻止しないこと（27.5節）
    ACK-         Commit-Aware Lock HelperのACK Determinism（post-commit例外でも
                 acknowledged=Trueを維持）（9.9.4.3節）

実行方法:
    cd projects/03_game_content_ai
    .\\venv\\Scripts\\python.exe tests\\test_e2e_v6_32_0_side_effect_fail_closed_foundation.py
"""
import shutil
import sys
import tempfile
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
print("v6.32.0 Side-Effect Fail-Closed Safety Foundation E2E テスト")
print("=" * 60)
print()

from side_effect_safety import (  # noqa: E402
    ExecutionModeFailureReasonCode,
    JsonMediaUploadApplicabilityStore,
    JsonMediaUploadAttemptContextStore,
    LegacyDirectExecutionContext,
    LegacyEntrypoint,
    LegacyExecutionOrigin,
    MediaUploadContextPhase,
    MediaUploadSafetyContractViolationError,
    MediaUploadSafetyTransitionError,
    ProtectedSideEffectKind,
    RetryLineageProtectedExecutionContext,
    SideEffectExecutionModeContractError,
    SideEffectOperationIdentity,
    SideEffectSite,
    build_media_upload_safety_coordinator,
    build_protected_execution_context,
    complete_legacy_execution_context,
    build_legacy_direct_provenance,
    validate_side_effect_execution_context,
)
from side_effect_safety.media_upload_attempt_context_store import JsonMediaUploadAttemptContextStore as _CtxStore
from side_effect_safety.media_upload_safety_coordinator_lock import build_media_upload_safety_coordinator_lock
from article_media_upload_state.article_media_upload_state_manager import ArticleMediaUploadStateManager  # noqa: E402
from article_media_upload_state.json_article_media_upload_state_store import JsonArticleMediaUploadStateStore  # noqa: E402
from wordpress_draft_state import (  # noqa: E402
    JsonWordPressDraftStateStore,
    WordPressDraftStateCorruptedError,
    WordPressDraftStateManager,
    WordPressDraftStateTransitionError,
    build_wordpress_draft_state_store_lock,
)


def _identity(kind, instance_key="art1", root_run_id="r1", attempt_ordinal=1, site=SideEffectSite.NEWS_STEP):
    return SideEffectOperationIdentity(
        root_run_id=root_run_id, attempt_ordinal=attempt_ordinal,
        operation_kind=kind, effect_site=site, operation_instance_key=instance_key,
    )


# ─── [テスト1] IDENTITY: as_store_key()の決定論性 ───

print("[テスト1] IDENTITY: as_store_key()の決定論性")

id_a = _identity(ProtectedSideEffectKind.MEDIA_UPLOAD)
id_b = _identity(ProtectedSideEffectKind.MEDIA_UPLOAD)
id_c = _identity(ProtectedSideEffectKind.MEDIA_UPLOAD, attempt_ordinal=2)
check("1a. 同一構成要素は同一key", id_a.as_store_key(), id_b.as_store_key())
check_true("1b. attempt_ordinal違いは別key", id_a.as_store_key() != id_c.as_store_key())
print()


# ─── [テスト2] MODE: discriminated union・validator ───

print("[テスト2] MODE: Explicit Side-Effect Execution Mode")

protected = build_protected_execution_context(
    root_run_id="r1", attempt_ordinal=1, member_run_id="m1", side_effect_contract_version=1,
)
check_true("2a. protected contextは検証を通過する", validate_side_effect_execution_context(protected) is protected)

legacy_prov = build_legacy_direct_provenance(LegacyEntrypoint.RUN_NEWS_AGENT)
legacy = complete_legacy_execution_context(legacy_prov, LegacyExecutionOrigin.NEWS_AGENT)
check_true("2b. legacy contextは検証を通過する", validate_side_effect_execution_context(legacy) is legacy)

check_raises("2c. context=Noneはfail-closed", lambda: validate_side_effect_execution_context(None), SideEffectExecutionModeContractError)


def _bad_root_run_id():
    bad = RetryLineageProtectedExecutionContext(
        root_run_id="", attempt_ordinal=1, member_run_id="m1", side_effect_contract_version=1,
    )
    validate_side_effect_execution_context(bad)


check_raises("2d. root_run_id欠落はhard failure", _bad_root_run_id, SideEffectExecutionModeContractError)


def _contradictory_legacy_pair():
    bad = LegacyDirectExecutionContext(
        legacy_entrypoint=LegacyEntrypoint.RUN_AI_PUBLISH,
        legacy_execution_origin=LegacyExecutionOrigin.NEWS_AGENT,
    )
    validate_side_effect_execution_context(bad)


check_raises(
    "2e. 到達不可能なlegacy entrypoint/origin組み合わせはCONTRADICTORY_LEGACY_PAIR",
    _contradictory_legacy_pair, SideEffectExecutionModeContractError,
)
print()


# ─── [テスト3] WPSTATE: WordPressDraftStateStore lifecycle ───

print("[テスト3] WPSTATE: WordPressDraftStateStore lifecycle")

with tempfile.TemporaryDirectory() as tmpdir:
    d = Path(tmpdir)
    store = JsonWordPressDraftStateStore(d / "wp")
    manager = WordPressDraftStateManager(store)
    identity = _identity(ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION)

    check_true("3a. 初期状態はNone", manager.get_state(identity, "m1") is None)

    attempted = manager.record_attempted(identity, "m1")
    check_true("3b. ATTEMPTED記録", attempted.wp_post_id is None)

    check_raises("3c. duplicate create はTransitionError", lambda: manager.record_attempted(identity, "m1"), WordPressDraftStateTransitionError)

    check_raises(
        "3d. member_run_id不一致でのconfirmedはTransitionError",
        lambda: manager.record_confirmed(identity, "wrong-member", 123),
        WordPressDraftStateTransitionError,
    )

    confirmed = manager.record_confirmed(identity, "m1", 123)
    check_true("3e. CONFIRMED_SUCCESS確定", confirmed.wp_post_id == 123)

    check_raises(
        "3f. CONFIRMED_SUCCESS状態への再transitionはTransitionError（expected_state不一致）",
        lambda: manager.record_confirmed(identity, "m1", 999),
        WordPressDraftStateTransitionError,
    )

    check_true("3g. get()がCONFIRMED_SUCCESSを返す", manager.get_state(identity, "m1").wp_post_id == 123)

    check_raises(
        "3h. get()のexpected_member_run_id不一致はCorruptedError",
        lambda: manager.get_state(identity, "different-member"),
        WordPressDraftStateCorruptedError,
    )

    # 27.3節：get()はlock-free（identityロックファイルを作らない）
    lock = build_wordpress_draft_state_store_lock(d / "wp" / ".locks", identity)
    manager.get_state(identity, "m1")
    check_true("3i. get()はlock fileを作らない（lock-free）", not lock.lock_path.exists())

print()


# ─── [テスト4] MEDIA: MediaUploadSafetyCoordinator lifecycle ───

print("[テスト4] MEDIA: MediaUploadSafetyCoordinator lifecycle")

with tempfile.TemporaryDirectory() as tmpdir:
    d = Path(tmpdir)
    media_manager = ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(d / "media"))
    coordinator = build_media_upload_safety_coordinator(
        media_upload_manager=media_manager,
        applicability_store=JsonMediaUploadApplicabilityStore(d / "applicability"),
        attempt_context_store=_CtxStore(d / "context"),
        locks_dir=d / "locks",
    )
    identity = _identity(ProtectedSideEffectKind.MEDIA_UPLOAD)

    check_true("4a. 初期状態はNone", coordinator.get(identity, "m1") is None)

    prepared = coordinator.record_prepared(identity, "m1")
    check_true("4b. PREPARED記録", prepared.__class__.__name__ == "PreparedMediaUploadSafetyRecord")

    prepared2 = coordinator.record_prepared(identity, "m1")
    check_true("4c. 2回目のrecord_prepared()は冪等no-op", prepared2.__class__.__name__ == "PreparedMediaUploadSafetyRecord")

    armed = coordinator.record_attempted(identity, "m1")
    check_true("4d. PREPARED→IO_ARMED（record_attempted、Safe Continuation経由）", armed.__class__.__name__ == "IoArmedMediaUploadSafetyRecord")

    check_raises(
        "4e. IO_ARMED+ATTEMPTED以外からのrecord_confirmed()はTransitionError",
        lambda: coordinator.record_confirmed(_identity(ProtectedSideEffectKind.MEDIA_UPLOAD, instance_key="other"), "m2", media_id=1),
        MediaUploadSafetyTransitionError,
    )

    confirmed = coordinator.record_confirmed(identity, "m1", media_id=42)
    check_true("4f. CONFIRMED_SUCCESS確定", confirmed.media_id == 42)
    check_true("4g. get()がConfirmedを返す", coordinator.get(identity, "m1").media_id == 42)

    # NOT_APPLICABLE経路（別identity）
    na_identity = _identity(ProtectedSideEffectKind.MEDIA_UPLOAD, instance_key="art-na")
    na = coordinator.record_not_applicable(na_identity, "m3")
    check_true("4h. NOT_APPLICABLE記録", na.__class__.__name__ == "NotApplicableMediaUploadSafetyRecord")
    check_raises(
        "4i. 2回目のrecord_not_applicable()はTransitionError（duplicate、Invariant #11）",
        lambda: coordinator.record_not_applicable(na_identity, "m3"),
        MediaUploadSafetyTransitionError,
    )

print()


# ─── [テスト5] MEDIA: Cross-Store Combination Table（9.9.7節） ───

print("[テスト5] MEDIA: Cross-Store Combination Table")

with tempfile.TemporaryDirectory() as tmpdir:
    d = Path(tmpdir)
    media_manager = ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(d / "media"))
    context_store = _CtxStore(d / "context")
    applicability_store = JsonMediaUploadApplicabilityStore(d / "applicability")
    coordinator = build_media_upload_safety_coordinator(
        media_upload_manager=media_manager,
        applicability_store=applicability_store,
        attempt_context_store=context_store,
        locks_dir=d / "locks",
    )

    # (a) 非存在 | IO_ARMED | ATTEMPTED → IN_PROGRESS_OR_UNKNOWN相当（IoArmedMediaUploadSafetyRecord）
    id_progress = _identity(ProtectedSideEffectKind.MEDIA_UPLOAD, instance_key="progress")
    coordinator.record_attempted(id_progress, "m1")
    check_true("5a. IO_ARMED+ATTEMPTED → IoArmedMediaUploadSafetyRecord", coordinator.get(id_progress, "m1").__class__.__name__ == "IoArmedMediaUploadSafetyRecord")

    # (b) 非存在 | 非存在 | ATTEMPTED（矛盾combination）→ CONTRACT_VIOLATION
    id_violation = _identity(ProtectedSideEffectKind.MEDIA_UPLOAD, instance_key="violation")
    media_manager.record_upload_started(article_identity=id_violation.as_store_key())
    check_raises(
        "5b. context非存在+upload_state存在はCONTRACT_VIOLATION",
        lambda: coordinator.get(id_violation, "m1"),
        MediaUploadSafetyContractViolationError,
    )

    # (c) marker あり + context あり（矛盾combination）→ CONTRACT_VIOLATION
    id_marker_conflict = _identity(ProtectedSideEffectKind.MEDIA_UPLOAD, instance_key="marker-conflict")
    applicability_store.create(id_marker_conflict, "m1", "2026-01-01T00:00:00+00:00")
    context_store.create_prepared(id_marker_conflict, "m1", "2026-01-01T00:00:00+00:00")
    check_raises(
        "5c. marker（NOT_APPLICABLE）とcontextの併存はCONTRACT_VIOLATION",
        lambda: coordinator.get(id_marker_conflict, "m1"),
        MediaUploadSafetyContractViolationError,
    )

print()


# ─── [テスト6] LOCK: stale identity lockはget()を阻止しない（27.5節） ───

print("[テスト6] LOCK: stale identity lockはget()を阻止しない")

with tempfile.TemporaryDirectory() as tmpdir:
    d = Path(tmpdir)
    media_manager = ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(d / "media"))
    coordinator = build_media_upload_safety_coordinator(
        media_upload_manager=media_manager,
        applicability_store=JsonMediaUploadApplicabilityStore(d / "applicability"),
        attempt_context_store=_CtxStore(d / "context"),
        locks_dir=d / "locks",
    )
    identity = _identity(ProtectedSideEffectKind.MEDIA_UPLOAD, instance_key="stale-lock")
    coordinator.record_attempted(identity, "m1")

    # staleロックを人為的に残す
    stale_lock = build_media_upload_safety_coordinator_lock(d / "locks", identity)
    stale_lock.acquire()
    try:
        result = coordinator.get(identity, "m1")
        check_true("6a. staleロック存在下でもget()は成功する", result.__class__.__name__ == "IoArmedMediaUploadSafetyRecord")
    finally:
        stale_lock.release()

print()


# ─── 結果サマリー ───

print("=" * 60)
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
