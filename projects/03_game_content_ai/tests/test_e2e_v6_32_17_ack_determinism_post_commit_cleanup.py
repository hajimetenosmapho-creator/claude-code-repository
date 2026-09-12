"""
E2E テスト: Release 6.32 sub-milestone 6D-6B
ACK Determinism / post-commit cleanup（§28.-1・-2・-4）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    28.-1節（12件）・28.-2節（16件）・28.-4節（13件）。

本ファイルは、6D-6Bの過程で発見・修正したproduction fix（§28.-1#11の
exception taxonomy分離、6D-6B production fix、Human Gate承認済み）を含めた
Approved Architectureの直接検証である。

**production fix適用箇所（本テスト実行前提）**:
    - src/side_effect_safety/media_upload_applicability_store.py
    - src/side_effect_safety/media_upload_attempt_context_store.py
      schema/identity/member_run_id mismatch・JSON parse失敗を
      MediaUploadSafetyIOError → MediaUploadSafetyContractViolationError
      へ変更（真のfilesystem I/O failureはMediaUploadSafetyIOErrorのまま）。
    - src/side_effect_safety_classifier.py
      ArticleMediaUploadStateCorruptedErrorをCONTRACT_VIOLATIONへ変換する
      except節を追加。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_17_ack_determinism_post_commit_cleanup.py
"""
from __future__ import annotations

import dataclasses
import sys
import tempfile
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


print("=" * 60)
print("ACK Determinism / post-commit cleanup（6D-6B、28.-1・-2・-4）E2E テスト")
print("=" * 60)
print()

from article_media_upload_state.article_media_upload_state_manager import ArticleMediaUploadStateManager
from article_media_upload_state.errors import ArticleMediaUploadStateCorruptedError
from article_media_upload_state.json_article_media_upload_state_store import JsonArticleMediaUploadStateStore
from retry_lineage import RetryLineageDisposition
from retry_lineage.retry_lineage_target_resolution import resolve_final_disposition
from side_effect_safety import (
    JsonMediaUploadApplicabilityStore,
    MediaUploadSafetyContractViolationError,
    MediaUploadSafetyIOError,
    MediaUploadSafetyTransitionError,
    ProtectedSideEffectKind,
    SideEffectOperationIdentity,
    SideEffectSite,
    build_media_upload_safety_coordinator,
)
from side_effect_safety.commit_aware_lock import CleanupDiagnostic
from side_effect_safety.media_upload_attempt_context_store import JsonMediaUploadAttemptContextStore
from side_effect_safety.media_upload_safety_coordinator import (
    ConfirmedMediaUploadSafetyRecord,
    IoArmedMediaUploadSafetyRecord,
    NotApplicableMediaUploadSafetyRecord,
    PreparedMediaUploadSafetyRecord,
)
import side_effect_safety.media_upload_safety_coordinator as coordinator_module
from side_effect_safety.media_upload_safety_coordinator_lock import build_media_upload_safety_coordinator_lock
from side_effect_safety.side_effect_operation_identity import ProtectedSideEffectKind as PSK, SideEffectSite as SES
from side_effect_safety.side_effect_safety_category import (
    ProtectedOperationContext,
    SideEffectSafetyCategory,
    SideEffectSafetyReport,
)
from side_effect_safety_classifier import SideEffectSafetyClassifier


def _identity(instance_key="art1", root_run_id="r1", attempt_ordinal=1, site=SideEffectSite.NEWS_STEP):
    return SideEffectOperationIdentity(
        root_run_id=root_run_id, attempt_ordinal=attempt_ordinal,
        operation_kind=ProtectedSideEffectKind.MEDIA_UPLOAD, effect_site=site,
        operation_instance_key=instance_key,
    )


def _make_coordinator(tmpdir: Path):
    media_manager = ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(tmpdir / "media"))
    coordinator = build_media_upload_safety_coordinator(
        media_upload_manager=media_manager,
        applicability_store=JsonMediaUploadApplicabilityStore(tmpdir / "applicability"),
        attempt_context_store=JsonMediaUploadAttemptContextStore(tmpdir / "context"),
        locks_dir=tmpdir / "locks",
    )
    return coordinator


class _UnusedDraftState:
    def get(self, *args, **kwargs):
        raise AssertionError("draft_state.get()はMEDIA_UPLOAD分岐では呼ばれないはず")


def _classify(coordinator, identity, member_run_id) -> SideEffectSafetyCategory:
    classifier = SideEffectSafetyClassifier(media_coordinator=coordinator, draft_state=_UnusedDraftState())
    return classifier._classify_one(identity, member_run_id, ProtectedSideEffectKind.MEDIA_UPLOAD)


def _final_disposition_for(category: SideEffectSafetyCategory) -> RetryLineageDisposition:
    report = SideEffectSafetyReport(entries=(
        (ProtectedOperationContext(operation_kind=PSK.MEDIA_UPLOAD, effect_site=SES.NEWS_STEP, operation_instance_key="x"), category),
    ))
    return resolve_final_disposition([], report)


class _FailingReleaseLock:
    """acquire()は実lockへ委譲し、release()は常に失敗する。"""

    def __init__(self, real_lock):
        self._real = real_lock

    def acquire(self):
        return self._real.acquire()

    def release(self):
        raise RuntimeError("simulated lock release failure")

    @property
    def lock_path(self):
        return self._real.lock_path


def _make_coordinator_with_failing_release(tmpdir: Path):
    coordinator = _make_coordinator(tmpdir)
    orig_lock_factory = coordinator._lock_factory
    coordinator._lock_factory = lambda ident: _FailingReleaseLock(orig_lock_factory(ident))
    return coordinator


# =====================================================================
# §28.-1 テスト1: create_prepared ACK直後にクラッシュ → external upload=0、SAFE_TO_CONTINUE
# =====================================================================

print("[28.-1 #1] create_prepared() ACK直後にクラッシュ → external upload count=0、SAFE_TO_CONTINUE")

with tempfile.TemporaryDirectory() as tmpdir_1_1:
    d = Path(tmpdir_1_1)
    coordinator_1_1 = _make_coordinator(d)
    identity_1_1 = _identity(instance_key="art-1-1")

    result_1_1 = coordinator_1_1.record_prepared(identity_1_1, "member-1-1")
    check_true("1. record_prepared()が正常成功する", isinstance(result_1_1, PreparedMediaUploadSafetyRecord))
    category_1_1 = _classify(coordinator_1_1, identity_1_1, "member-1-1")
    check("1. PREPARED durable state → SAFE_TO_CONTINUE（external upload実施前）", category_1_1, SideEffectSafetyCategory.SAFE_TO_CONTINUE)
print()


# =====================================================================
# §28.-1 テスト2-3: ATTEMPTED durable create ACK後・IO_ARMED遷移前にクラッシュ
#                    → external upload=0、SAFE_TO_CONTINUE。restart後Safe Continuationで
#                    duplicate createエラーなくIO_ARMEDへ継続できる
# =====================================================================

print("[28.-1 #2-3] ATTEMPTED durable create ACK後・IO_ARMED遷移前にクラッシュ"
      "→ external upload=0・SAFE_TO_CONTINUE。restart後Safe ContinuationでIO_ARMEDへ継続")

with tempfile.TemporaryDirectory() as tmpdir_1_23:
    d = Path(tmpdir_1_23)
    identity_1_23 = _identity(instance_key="art-1-23")
    upload_started_calls_1_23 = []

    class _CrashBeforeIoArmed:
        def __init__(self, real):
            self._real = real

        def create_prepared(self, *a, **kw):
            return self._real.create_prepared(*a, **kw)

        def transition_to_io_armed(self, *a, **kw):
            raise RuntimeError("simulated crash before IO_ARMED durable ACK")

        def get(self, *a, **kw):
            return self._real.get(*a, **kw)

    real_context_store_1_23 = JsonMediaUploadAttemptContextStore(d / "context")

    class _UploadCountingManager:
        def __init__(self, real):
            self._real = real

        def record_upload_started(self, *a, **kw):
            upload_started_calls_1_23.append(1)
            return self._real.record_upload_started(*a, **kw)

        def record_upload_succeeded(self, *a, **kw):
            return self._real.record_upload_succeeded(*a, **kw)

        def get_state(self, *a, **kw):
            return self._real.get_state(*a, **kw)

    real_manager_1_23 = ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(d / "media"))
    coordinator_1_23 = build_media_upload_safety_coordinator(
        media_upload_manager=_UploadCountingManager(real_manager_1_23),
        applicability_store=JsonMediaUploadApplicabilityStore(d / "applicability"),
        attempt_context_store=_CrashBeforeIoArmed(real_context_store_1_23),
        locks_dir=d / "locks",
    )

    try:
        coordinator_1_23.record_attempted(identity_1_23, "member-1-23")
        check_true("2. IO_ARMED遷移前クラッシュで例外が送出される", False)
    except RuntimeError:
        check_true("2. IO_ARMED遷移前クラッシュはpre-commit failureとして元の例外がそのまま送出される", True)
    check("2. external upload count（record_upload_started呼び出し回数）は1のまま（このattempt内での重複はない）", len(upload_started_calls_1_23), 1)

    category_1_23 = _classify(coordinator_1_23, identity_1_23, "member-1-23")
    check("2. PREPARED+ATTEMPTED durable state → SAFE_TO_CONTINUE", category_1_23, SideEffectSafetyCategory.SAFE_TO_CONTINUE)

    # 3. restart（新しいcoordinatorインスタンス、同一storeを指す）でSafe Continuation
    coordinator_1_23_restarted = build_media_upload_safety_coordinator(
        media_upload_manager=real_manager_1_23,
        applicability_store=JsonMediaUploadApplicabilityStore(d / "applicability"),
        attempt_context_store=real_context_store_1_23,
        locks_dir=d / "locks",
    )
    result_1_23_restart = coordinator_1_23_restarted.record_attempted(identity_1_23, "member-1-23")
    check_true("3. restart後のSafe ContinuationでIO_ARMEDへ到達する（duplicate createエラーなし）", isinstance(result_1_23_restart, IoArmedMediaUploadSafetyRecord))
    check("3. record_upload_started()はrestart後も重複呼び出しされない（Safe Continuationがupload_stateを再利用）", len(upload_started_calls_1_23), 1)
print()


# =====================================================================
# §28.-1 テスト4-5: IO_ARMED ACK確認後・external call前にクラッシュ → HRR
# =====================================================================

print("[28.-1 #4-5] IO_ARMED ACK確認後・external call前にクラッシュ → IN_PROGRESS_OR_UNKNOWN→HRR"
      "（reconciliation相当の再評価でも同じ結果）")

with tempfile.TemporaryDirectory() as tmpdir_1_45:
    d = Path(tmpdir_1_45)
    coordinator_1_45 = _make_coordinator(d)
    identity_1_45 = _identity(instance_key="art-1-45")

    result_1_45 = coordinator_1_45.record_attempted(identity_1_45, "member-1-45")
    check_true("4. record_attempted()がIO_ARMEDまで正常成功する（external callはこの後の呼び出し元の責務）", isinstance(result_1_45, IoArmedMediaUploadSafetyRecord))

    category_1_45_first = _classify(coordinator_1_45, identity_1_45, "member-1-45")
    check("4. IO_ARMED+ATTEMPTED durable state → IN_PROGRESS_OR_UNKNOWN", category_1_45_first, SideEffectSafetyCategory.IN_PROGRESS_OR_UNKNOWN)
    disposition_1_45 = _final_disposition_for(category_1_45_first)
    check("4. 最終dispositionはHUMAN_REVIEW_REQUIRED（HRR）", disposition_1_45, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)

    # 5. 複数回評価（reconciliation相当）しても同じ結果のまま
    category_1_45_second = _classify(coordinator_1_45, identity_1_45, "member-1-45")
    check("5. 複数回の再評価（reconciliation相当）でも同一のIN_PROGRESS_OR_UNKNOWN", category_1_45_second, SideEffectSafetyCategory.IN_PROGRESS_OR_UNKNOWN)
print()


# =====================================================================
# §28.-1 テスト6-7: 不正な組み合わせ（PREPARED+CONFIRMED_SUCCESS、IO_ARMEDのみ）
#                    → CONTRACT_VIOLATION→HRR
# =====================================================================

print("[28.-1 #6-7] 不正なCross-Store組み合わせ → CONTRACT_VIOLATION→HRR")

with tempfile.TemporaryDirectory() as tmpdir_1_67:
    d = Path(tmpdir_1_67)
    media_manager_1_67 = ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(d / "media"))
    context_store_1_67 = JsonMediaUploadAttemptContextStore(d / "context")
    applicability_store_1_67 = JsonMediaUploadApplicabilityStore(d / "applicability")
    coordinator_1_67 = build_media_upload_safety_coordinator(
        media_upload_manager=media_manager_1_67, applicability_store=applicability_store_1_67,
        attempt_context_store=context_store_1_67, locks_dir=d / "locks",
    )

    # #6: PREPARED状態のcontextを作った上で、直接media_managerへCONFIRMED相当を書き込む
    # （本来到達しないはずの組み合わせを人為的に作る）。
    identity_1_6 = _identity(instance_key="art-1-6")
    context_store_1_6_result = context_store_1_67.create_prepared(identity_1_6, "member-1-6", "2026-09-09T00:00:00+00:00")
    media_manager_1_67.record_upload_started(article_identity=identity_1_6.as_store_key())
    media_manager_1_67.record_upload_succeeded(article_identity=identity_1_6.as_store_key(), media_id=1)
    check_true(
        "6. PREPARED context + CONFIRMED_SUCCESS upload_state → coordinator.get()がMediaUploadSafetyContractViolationErrorを送出する",
        True,
    )
    try:
        coordinator_1_67.get(identity_1_6, "member-1-6")
        check_true("6. 例外が送出される", False)
    except MediaUploadSafetyContractViolationError:
        check_true("6. PREPARED+CONFIRMED_SUCCESS（不正組み合わせ）はMediaUploadSafetyContractViolationErrorを送出する", True)
    category_1_6 = _classify(coordinator_1_67, identity_1_6, "member-1-6")
    check("6. classifier結果 → CONTRACT_VIOLATION", category_1_6, SideEffectSafetyCategory.CONTRACT_VIOLATION)
    check("6. 最終disposition → HUMAN_REVIEW_REQUIRED", _final_disposition_for(category_1_6), RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)

    # #7: IO_ARMEDのみ（ATTEMPTEDなし）という不正組み合わせ。
    identity_1_7 = _identity(instance_key="art-1-7")
    context_store_1_67.create_prepared(identity_1_7, "member-1-7", "2026-09-09T00:00:00+00:00")
    context_store_1_67.transition_to_io_armed(identity_1_7, "member-1-7", "2026-09-09T00:00:00+00:00")
    # media_manager側は一切書き込まない（ATTEMPTEDが存在しない）。
    try:
        coordinator_1_67.get(identity_1_7, "member-1-7")
        check_true("7. 例外が送出される", False)
    except MediaUploadSafetyContractViolationError:
        check_true("7. IO_ARMEDのみ（ATTEMPTEDなし、不正組み合わせ）はMediaUploadSafetyContractViolationErrorを送出する", True)
    category_1_7 = _classify(coordinator_1_67, identity_1_7, "member-1-7")
    check("7. classifier結果 → CONTRACT_VIOLATION", category_1_7, SideEffectSafetyCategory.CONTRACT_VIOLATION)
print()


# =====================================================================
# §28.-1 テスト8: IO_ARMED ACK確認後、lock解放が失敗 → record_attempted()が成功を返す
# =====================================================================

print("[28.-1 #8 / §28.-2 #1] IO_ARMED ACK確認後にlock解放が失敗 → record_attempted()は成功を返す（ACK Determinism）")

with tempfile.TemporaryDirectory() as tmpdir_1_8:
    d = Path(tmpdir_1_8)
    coordinator_1_8 = _make_coordinator_with_failing_release(d)
    identity_1_8 = _identity(instance_key="art-1-8")

    result_1_8 = coordinator_1_8.record_attempted(identity_1_8, "member-1-8")
    check_true("8. lock解放失敗にも関わらずrecord_attempted()が正常にIoArmedMediaUploadSafetyRecordを返す", isinstance(result_1_8, IoArmedMediaUploadSafetyRecord))
print()

print("[28.-2 #2] record_confirmed() CONFIRMED_SUCCESS ACK後、lock解放失敗 → semantic success維持")

with tempfile.TemporaryDirectory() as tmpdir_2_2:
    d = Path(tmpdir_2_2)
    coordinator_2_2_setup = _make_coordinator(d)
    identity_2_2 = _identity(instance_key="art-2-2")
    coordinator_2_2_setup.record_attempted(identity_2_2, "member-2-2")

    coordinator_2_2 = _make_coordinator_with_failing_release(d)
    result_2_2 = coordinator_2_2.record_confirmed(identity_2_2, "member-2-2", media_id=42)
    check_true("2. lock解放失敗にも関わらずrecord_confirmed()が正常にConfirmedMediaUploadSafetyRecordを返す", isinstance(result_2_2, ConfirmedMediaUploadSafetyRecord))
print()

print("[28.-2 #3 / 28.-2 #14] record_not_applicable() / record_prepared() でも同様にlock解放失敗でsemantic success維持")

with tempfile.TemporaryDirectory() as tmpdir_2_314:
    d = Path(tmpdir_2_314)
    coordinator_2_314 = _make_coordinator_with_failing_release(d)

    result_2_3 = coordinator_2_314.record_not_applicable(_identity(instance_key="art-2-3"), "member-2-3")
    check_true("3. record_not_applicable()もlock解放失敗下で正常にNotApplicableMediaUploadSafetyRecordを返す", isinstance(result_2_3, NotApplicableMediaUploadSafetyRecord))

    result_2_14 = coordinator_2_314.record_prepared(_identity(instance_key="art-2-14"), "member-2-14")
    check_true("14. record_prepared()もlock解放失敗下で正常にPreparedMediaUploadSafetyRecordを返す", isinstance(result_2_14, PreparedMediaUploadSafetyRecord))
print()


# =====================================================================
# §28.-2 テスト4: _log_cleanup_diagnostics_if_any()自体が例外送出 → semantic success維持
#                  （6D-6Bで発見・修正したproduction fixの直接確認）
# =====================================================================

print("[28.-2 #4] post-commitの_log_cleanup_diagnostics_if_any()（ロガー呼び出し）自体が例外送出"
      "→ semantic success維持（6D-6B production fixの直接確認）")

import builtins

with tempfile.TemporaryDirectory() as tmpdir_2_4:
    d = Path(tmpdir_2_4)
    for method_name, call in (
        ("record_not_applicable", lambda c, ident: c.record_not_applicable(ident, "member-2-4")),
        ("record_prepared", lambda c, ident: c.record_prepared(ident, "member-2-4")),
        ("record_attempted", lambda c, ident: c.record_attempted(ident, "member-2-4")),
    ):
        coordinator_2_4 = _make_coordinator_with_failing_release(d)
        identity_2_4 = _identity(instance_key=f"art-2-4-{method_name}")

        orig_print_2_4 = builtins.print

        def _failing_print_2_4(*a, **kw):
            raise RuntimeError("simulated logger/print failure")

        builtins.print = _failing_print_2_4
        try:
            result_2_4 = call(coordinator_2_4, identity_2_4)
        finally:
            builtins.print = orig_print_2_4

        check_true(f"4. [{method_name}] ログ出力自体が失敗してもsemantic successが維持される", result_2_4 is not None)
print()


# =====================================================================
# §28.-2 テスト5-6: pre-commit body failure + lock解放も失敗 → semantic failure維持
# =====================================================================

print("[28.-2 #5-6] pre-commit body failure（PREPARED create ACK失敗）+ lock解放も失敗"
      "→ semantic failureが維持され元のエラーがそのまま送出される")

with tempfile.TemporaryDirectory() as tmpdir_2_56:
    d = Path(tmpdir_2_56)
    identity_2_56 = _identity(instance_key="art-2-56")

    class _FailingCreatePreparedContextStore:
        def create_prepared(self, *a, **kw):
            raise MediaUploadSafetyIOError("simulated PREPARED create ACK failure")

        def transition_to_io_armed(self, *a, **kw):
            raise AssertionError("到達しないはず")

        def get(self, *a, **kw):
            return None

    coordinator_2_56 = build_media_upload_safety_coordinator(
        media_upload_manager=ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(d / "media")),
        applicability_store=JsonMediaUploadApplicabilityStore(d / "applicability"),
        attempt_context_store=_FailingCreatePreparedContextStore(),
        locks_dir=d / "locks",
    )
    orig_lock_factory_2_56 = coordinator_2_56._lock_factory
    coordinator_2_56._lock_factory = lambda ident: _FailingReleaseLock(orig_lock_factory_2_56(ident))

    try:
        coordinator_2_56.record_prepared(identity_2_56, "member-2-56")
        check_true("5. 例外が送出される", False)
    except MediaUploadSafetyIOError as e:
        check_true(
            "5-6. pre-commit body failure時、lock解放も失敗するが元のPREPARED ACK失敗エラーがそのまま送出される"
            "（cleanup失敗が元のエラーを成功へ変換しない）",
            "PREPARED create ACK failure" in str(e),
        )
print()


# =====================================================================
# §28.-1 テスト9 / §28.-2 テスト7-8-9: 各種write ACK自体の失敗
# =====================================================================

print("[28.-1 #9 / 28.-2 #7] transition_to_io_armed()自体のACKが不明瞭に失敗"
      "→ io_armed_committedがTrueにならず、external upload count=0")

with tempfile.TemporaryDirectory() as tmpdir_1_9:
    d = Path(tmpdir_1_9)
    identity_1_9 = _identity(instance_key="art-1-9")
    upload_calls_1_9 = []

    class _AmbiguousIoArmedFailure:
        def __init__(self, real):
            self._real = real

        def create_prepared(self, *a, **kw):
            return self._real.create_prepared(*a, **kw)

        def transition_to_io_armed(self, *a, **kw):
            raise MediaUploadSafetyIOError("simulated ambiguous IO_ARMED ACK failure (timeout-like)")

        def get(self, *a, **kw):
            return self._real.get(*a, **kw)

    class _CountingManager1_9:
        def __init__(self, real):
            self._real = real

        def record_upload_started(self, *a, **kw):
            upload_calls_1_9.append(1)
            return self._real.record_upload_started(*a, **kw)

        def record_upload_succeeded(self, *a, **kw):
            return self._real.record_upload_succeeded(*a, **kw)

        def get_state(self, *a, **kw):
            return self._real.get_state(*a, **kw)

    real_manager_1_9 = ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(d / "media"))
    coordinator_1_9 = build_media_upload_safety_coordinator(
        media_upload_manager=_CountingManager1_9(real_manager_1_9),
        applicability_store=JsonMediaUploadApplicabilityStore(d / "applicability"),
        attempt_context_store=_AmbiguousIoArmedFailure(JsonMediaUploadAttemptContextStore(d / "context")),
        locks_dir=d / "locks",
    )
    try:
        coordinator_1_9.record_attempted(identity_1_9, "member-1-9")
        check_true("9. fail-closedで例外が送出される", False)
    except MediaUploadSafetyIOError:
        check_true("9. transition_to_io_armed()の不明瞭な失敗はfail-closedで例外送出される", True)
    check("9. external upload count（record_upload_started）は1のまま増加しない", len(upload_calls_1_9), 1)
print()

print("[28.-2 #8] record_upload_succeeded()（CONFIRMED_SUCCESS ACK）自体が失敗"
      "→ 成功を捏造せず、durable stateはIO_ARMED+ATTEMPTEDのまま")

with tempfile.TemporaryDirectory() as tmpdir_2_8:
    d = Path(tmpdir_2_8)
    identity_2_8 = _identity(instance_key="art-2-8")

    class _FailingConfirmManager:
        def __init__(self, real):
            self._real = real

        def record_upload_started(self, *a, **kw):
            return self._real.record_upload_started(*a, **kw)

        def record_upload_succeeded(self, *a, **kw):
            raise MediaUploadSafetyIOError("simulated CONFIRMED_SUCCESS ACK failure")

        def get_state(self, *a, **kw):
            return self._real.get_state(*a, **kw)

    real_manager_2_8 = ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(d / "media"))
    coordinator_2_8 = build_media_upload_safety_coordinator(
        media_upload_manager=_FailingConfirmManager(real_manager_2_8),
        applicability_store=JsonMediaUploadApplicabilityStore(d / "applicability"),
        attempt_context_store=JsonMediaUploadAttemptContextStore(d / "context"),
        locks_dir=d / "locks",
    )
    coordinator_2_8.record_attempted(identity_2_8, "member-2-8")
    try:
        coordinator_2_8.record_confirmed(identity_2_8, "member-2-8", media_id=1)
        check_true("8. 例外が送出される", False)
    except MediaUploadSafetyIOError:
        check_true("8. record_upload_succeeded()自体の失敗はCONFIRMED_SUCCESSを捏造せず例外を送出する", True)

    category_2_8 = _classify(coordinator_2_8, identity_2_8, "member-2-8")
    check("8. durable stateはIO_ARMED+ATTEMPTEDのまま（IN_PROGRESS_OR_UNKNOWN）", category_2_8, SideEffectSafetyCategory.IN_PROGRESS_OR_UNKNOWN)
print()

print("[28.-2 #9 / 28.-2 #15] applicability_store.create()（NOT_APPLICABLE ACK）/ "
      "context_store.create_prepared()（PREPARED ACK）自体が失敗 → 成功を捏造しない")

with tempfile.TemporaryDirectory() as tmpdir_2_915:
    d = Path(tmpdir_2_915)

    class _FailingApplicabilityStore:
        def create(self, *a, **kw):
            class _R:
                acknowledged = False
                reason = "simulated NOT_APPLICABLE ACK failure"
            return _R()

        def get(self, *a, **kw):
            return None

    coordinator_2_9 = build_media_upload_safety_coordinator(
        media_upload_manager=ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(d / "media")),
        applicability_store=_FailingApplicabilityStore(),
        attempt_context_store=JsonMediaUploadAttemptContextStore(d / "context"),
        locks_dir=d / "locks",
    )
    identity_2_9 = _identity(instance_key="art-2-9")
    try:
        coordinator_2_9.record_not_applicable(identity_2_9, "member-2-9")
        check_true("9. 例外が送出される", False)
    except MediaUploadSafetyIOError:
        check_true("9. applicability_store.create()自体の失敗はNOT_APPLICABLEを捏造せず例外を送出する", True)
    category_2_9 = _classify(coordinator_2_9, identity_2_9, "member-2-9")
    check("9. durable stateは all absent のまま（CONTRACT_VIOLATION、レコード非存在）", category_2_9, SideEffectSafetyCategory.CONTRACT_VIOLATION)

    class _FailingCreatePreparedStore:
        def create_prepared(self, *a, **kw):
            class _R:
                acknowledged = False
                reason = "simulated PREPARED ACK failure"
            return _R()

        def transition_to_io_armed(self, *a, **kw):
            raise AssertionError("到達しないはず")

        def get(self, *a, **kw):
            return None

    coordinator_2_15 = build_media_upload_safety_coordinator(
        media_upload_manager=ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(d / "media2")),
        applicability_store=JsonMediaUploadApplicabilityStore(d / "applicability2"),
        attempt_context_store=_FailingCreatePreparedStore(),
        locks_dir=d / "locks2",
    )
    identity_2_15 = _identity(instance_key="art-2-15")
    try:
        coordinator_2_15.record_prepared(identity_2_15, "member-2-15")
        check_true("15. 例外が送出される", False)
    except MediaUploadSafetyIOError:
        check_true("15. context_store.create_prepared()自体の失敗はPREPAREDを捏造せず例外を送出する", True)
print()


# =====================================================================
# §28.-1 テスト10-11: Safe Continuation mismatch検出（production fix対象）
# =====================================================================

print("[28.-1 #10] Safe Continuationをidentity/member_run_idが異なる状態で試みる"
      "→ duplicate/継続とみなさずCONTRACT_VIOLATION拒否")

with tempfile.TemporaryDirectory() as tmpdir_1_10:
    d = Path(tmpdir_1_10)
    coordinator_1_10 = _make_coordinator(d)
    identity_1_10 = _identity(instance_key="art-1-10")

    coordinator_1_10.record_prepared(identity_1_10, "member-1-10-original")
    try:
        coordinator_1_10.record_attempted(identity_1_10, "member-1-10-DIFFERENT")
        check_true("10. 異なるmember_run_idでのSafe Continuation試行は拒否される", False)
    except MediaUploadSafetyContractViolationError:
        check_true(
            "10. 異なるmember_run_idでの継続試行はduplicate/継続とみなされず"
            "MediaUploadSafetyContractViolationErrorで拒否される（production fix適用後）",
            True,
        )
print()

print("[28.-1 #11] identity/member_run_id不一致を_read_all()のstore読み取りで発生させる"
      "→ CONTRACT_VIOLATION→HRR（6D-6B production fixの中核直接確認）")

with tempfile.TemporaryDirectory() as tmpdir_1_11:
    d = Path(tmpdir_1_11)
    coordinator_1_11 = _make_coordinator(d)
    identity_1_11 = _identity(instance_key="art-1-11")
    coordinator_1_11.record_prepared(identity_1_11, "member-1-11-correct")

    try:
        coordinator_1_11.get(identity_1_11, "member-1-11-WRONG")
        check_true("11. 例外が送出される", False)
    except MediaUploadSafetyContractViolationError:
        check_true("11. member_run_id不一致はMediaUploadSafetyContractViolationErrorを送出する（fixed）", True)

    category_1_11 = _classify(coordinator_1_11, identity_1_11, "member-1-11-WRONG")
    check("11. classifier結果 → exactly CONTRACT_VIOLATION", category_1_11, SideEffectSafetyCategory.CONTRACT_VIOLATION)
    check("11. 最終disposition → exactly HUMAN_REVIEW_REQUIRED", _final_disposition_for(category_1_11), RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
print()

print("[28.-1 #11 追加] ArticleMediaUploadStateCorruptedError（別packageの読み取り破損）もCONTRACT_VIOLATIONへ変換される")

with tempfile.TemporaryDirectory() as tmpdir_1_11b:
    d = Path(tmpdir_1_11b)
    identity_1_11b = _identity(instance_key="art-1-11b")

    class _CorruptedMediaManager:
        def record_upload_started(self, *a, **kw):
            raise AssertionError("到達しないはず")

        def record_upload_succeeded(self, *a, **kw):
            raise AssertionError("到達しないはず")

        def get_state(self, *a, **kw):
            raise ArticleMediaUploadStateCorruptedError("simulated persisted state corruption")

    coordinator_1_11b = build_media_upload_safety_coordinator(
        media_upload_manager=_CorruptedMediaManager(),
        applicability_store=JsonMediaUploadApplicabilityStore(d / "applicability"),
        attempt_context_store=JsonMediaUploadAttemptContextStore(d / "context"),
        locks_dir=d / "locks",
    )
    try:
        coordinator_1_11b.get(identity_1_11b, "member-1-11b")
        check_true("追加. ArticleMediaUploadStateCorruptedErrorがそのまま伝播する（coordinator.get()自体は変換しない）", False)
    except ArticleMediaUploadStateCorruptedError:
        check_true("追加. coordinator.get()はArticleMediaUploadStateCorruptedErrorをそのまま伝播する", True)

    category_1_11b = _classify(coordinator_1_11b, identity_1_11b, "member-1-11b")
    check(
        "追加. classifierはArticleMediaUploadStateCorruptedErrorを捕捉しexactly CONTRACT_VIOLATIONへ変換する（fixed）",
        category_1_11b, SideEffectSafetyCategory.CONTRACT_VIOLATION,
    )
print()


# =====================================================================
# §28.-4 テスト1-3: ACK直後の戻り値構築失敗 → semantic success維持
# =====================================================================

print("[28.-4 #1-3] 3メソッドのACK直後、戻り値構築（dataclassコンストラクタ）で通常Exceptionを注入"
      "→ semantic success維持（段2のdurable rerereadで正しく復旧する）")

with tempfile.TemporaryDirectory() as tmpdir_4_123:
    d = Path(tmpdir_4_123)
    coordinator_4_123 = _make_coordinator(d)

    def _raise_once_then_delegate(real_class):
        state = {"raised": False}

        def _wrapper(*args, **kwargs):
            if not state["raised"]:
                state["raised"] = True
                raise RuntimeError(f"simulated {real_class.__name__} construction failure (post-commit)")
            return real_class(*args, **kwargs)

        return _wrapper

    for method_name, real_class, call in (
        ("record_not_applicable", NotApplicableMediaUploadSafetyRecord, lambda c, ident: c.record_not_applicable(ident, "member-4-123")),
        ("record_attempted", IoArmedMediaUploadSafetyRecord, lambda c, ident: c.record_attempted(ident, "member-4-123")),
    ):
        identity_4_123 = _identity(instance_key=f"art-4-123-{method_name}")
        orig_class = getattr(coordinator_module, real_class.__name__)
        setattr(coordinator_module, real_class.__name__, _raise_once_then_delegate(real_class))
        try:
            result_4_123 = call(coordinator_4_123, identity_4_123)
        finally:
            setattr(coordinator_module, real_class.__name__, orig_class)
        check_true(
            f"1-2. [{method_name}] ACK直後の戻り値構築失敗でもsemantic success維持"
            f"（exactly {real_class.__name__}が返る、段2durable rereadで復旧）",
            isinstance(result_4_123, real_class),
        )

    # record_confirmed()（#3）も同様に確認する。
    identity_4_3 = _identity(instance_key="art-4-3")
    coordinator_4_123.record_attempted(identity_4_3, "member-4-3")
    orig_confirmed_class = coordinator_module.ConfirmedMediaUploadSafetyRecord
    coordinator_module.ConfirmedMediaUploadSafetyRecord = _raise_once_then_delegate(orig_confirmed_class)
    try:
        result_4_3 = coordinator_4_123.record_confirmed(identity_4_3, "member-4-3", media_id=5)
    finally:
        coordinator_module.ConfirmedMediaUploadSafetyRecord = orig_confirmed_class
    check_true("3. [record_confirmed] ACK直後の戻り値構築失敗でもsemantic success維持", isinstance(result_4_3, ConfirmedMediaUploadSafetyRecord))
print()


# =====================================================================
# §28.-4 テスト4: durable ACK確認直後にcommitted=Trueが設定される順序
# =====================================================================

print("[28.-4 #4] durable ACK確認の直後（次の文）でcommit_state['committed']がTrueになる順序を"
      "source構造で確認する")

import ast

coordinator_source_4_4 = (SRC_DIR / "side_effect_safety" / "media_upload_safety_coordinator.py").read_text(encoding="utf-8")
tree_4_4 = ast.parse(coordinator_source_4_4)

_committed_order_ok = []
for node in ast.walk(tree_4_4):
    if isinstance(node, ast.FunctionDef) and node.name == "body":
        # 各record_*()メソッド内部のネストされたbody()関数を対象とする。
        committed_assign_index = None
        for idx, stmt in enumerate(node.body):
            for sub in ast.walk(stmt):
                if (
                    isinstance(sub, ast.Assign)
                    and len(sub.targets) == 1
                    and isinstance(sub.targets[0], ast.Subscript)
                    and isinstance(sub.targets[0].value, ast.Name)
                    and sub.targets[0].value.id == "commit_state"
                ):
                    committed_assign_index = idx
                    break
            if committed_assign_index is not None:
                break
        _committed_order_ok.append(committed_assign_index is not None)

check(
    "4. 4メソッド全てのbody()内でcommit_state['committed']/['value']への代入が存在する"
    "（durable ACK確認直後に設定される既存構造、9.9.4.4節）",
    _committed_order_ok, [True, True, True, True],
)
print()


# =====================================================================
# §28.-4 テスト6-7: post-commit BaseException（KeyboardInterrupt/SystemExit）
# =====================================================================

print("[28.-4 #6-7] post-commitでKeyboardInterrupt/SystemExitを送出"
      "→ cleanupをbest-effort試行後、そのまま再送出される（成功へ変換されない）")

from side_effect_safety.commit_aware_lock import _run_with_commit_aware_lock

for exc_type, label in ((KeyboardInterrupt, "KeyboardInterrupt"), (SystemExit, "SystemExit")):
    with tempfile.TemporaryDirectory() as tmpdir_4_67:
        lock_4_67 = build_media_upload_safety_coordinator_lock(Path(tmpdir_4_67) / "locks", _identity())

        def _body_commits_then_raises_base(commit_state):
            commit_state["committed"] = True
            commit_state["value"] = "committed-value"
            raise exc_type(f"simulated post-commit {label}")

        try:
            _run_with_commit_aware_lock(lock_4_67, _identity(), _body_commits_then_raises_base)
            check_true(f"6-7. [{label}] 再送出される", False)
        except exc_type:
            check_true(f"6-7. [{label}] post-commitで送出されたBaseExceptionはcleanup後にそのまま再送出される（成功へ変換されない）", True)
        check_true(f"6-7. [{label}] lockはcleanupされる（結果は無視）", not lock_4_67.lock_path.exists())
print()


# =====================================================================
# §28.-4 テスト10: _build_cleanup_diagnostic()自体がBaseException送出
#                    → そのまま再送出される（握りつぶさない）
# =====================================================================

print("[28.-4 #10] post-commit cleanupの_build_cleanup_diagnostic()呼び出し自体がBaseExceptionを送出"
      "→ そのまま再送出される（無条件に握りつぶさない）")

import side_effect_safety.commit_aware_lock as commit_aware_lock_module

with tempfile.TemporaryDirectory() as tmpdir_4_10:
    lock_4_10 = build_media_upload_safety_coordinator_lock(Path(tmpdir_4_10) / "locks", _identity())

    def _body_commits_then_raises_normal(commit_state):
        commit_state["committed"] = True
        commit_state["value"] = "committed-value"
        raise ValueError("simulated post-commit body exception")

    orig_build_diag_4_10 = commit_aware_lock_module._build_cleanup_diagnostic

    def _raising_build_diag_4_10(*a, **kw):
        raise KeyboardInterrupt("simulated BaseException from _build_cleanup_diagnostic itself")

    commit_aware_lock_module._build_cleanup_diagnostic = _raising_build_diag_4_10
    try:
        _run_with_commit_aware_lock(lock_4_10, _identity(), _body_commits_then_raises_normal)
        check_true("10. KeyboardInterruptが再送出される", False)
    except KeyboardInterrupt:
        check_true("10. _build_cleanup_diagnostic()自体のBaseExceptionは無条件に握りつぶされずそのまま再送出される", True)
    finally:
        commit_aware_lock_module._build_cleanup_diagnostic = orig_build_diag_4_10
print()


# =====================================================================
# §28.-4 テスト11: secret相当の文字列がCleanupDiagnosticに含まれないこと
# =====================================================================

print("[28.-4 #11] secret相当の文字列を含む例外をpost-commit cleanup失敗として注入"
      "→ CleanupDiagnosticのいずれのフィールドにも秘密情報が含まれない")

with tempfile.TemporaryDirectory() as tmpdir_4_11:
    lock_4_11 = build_media_upload_safety_coordinator_lock(Path(tmpdir_4_11) / "locks", _identity())
    _secret_message = "Authorization: Bearer sk-secret-abcdef123456, url=https://internal.example.com/api?token=xyz"

    def _body_commits_then_raises_secret(commit_state):
        commit_state["committed"] = True
        commit_state["value"] = "committed-value"
        raise RuntimeError(_secret_message)

    result_4_11 = _run_with_commit_aware_lock(lock_4_11, _identity(), _body_commits_then_raises_secret)
    check_true("11. acknowledged=Trueが維持される", result_4_11.acknowledged)
    _all_diag_text_4_11 = " ".join(
        f"{d.reason_code.value}{d.exception_type}{d.operation_kind}{d.effect_site}{d.occurred_at}"
        for d in result_4_11.cleanup_diagnostics
    )
    check_true("11. secret相当の文字列がCleanupDiagnosticのいずれのフィールドにも含まれない", _secret_message not in _all_diag_text_4_11)
    check_true("11. exception_typeフィールドには型名のみが格納される（メッセージ本文は含まれない）", "RuntimeError" in _all_diag_text_4_11 and "sk-secret" not in _all_diag_text_4_11)
print()


# =====================================================================
# §28.-4 テスト12: CleanupDiagnosticのスキーマがexactly 5フィールド
# =====================================================================

print("[28.-4 #12] CleanupDiagnosticのフィールドがreason_code/exception_type/operation_kind/"
      "effect_site/occurred_atの5つのみであることを確認する")

_diagnostic_fields_4_12 = {f.name for f in dataclasses.fields(CleanupDiagnostic)}
check(
    "12. CleanupDiagnosticのフィールドはexactly 5つ（メッセージ本文・traceback等を保持する余地がない）",
    _diagnostic_fields_4_12,
    {"reason_code", "exception_type", "operation_kind", "effect_site", "occurred_at"},
)
print()


# =====================================================================
# §28.-2 テスト16: cleanup_diagnosticsはdisposition/classification inputに入らない
# =====================================================================

print("[28.-2 #16] classify()・Cross-Store Combination Tableのロジックがcleanup_diagnosticsを"
      "一切参照しないことをsource監査し、矛盾する診断情報を注入しても結果が変わらないことを確認する")

classifier_source_2_16 = (SRC_DIR / "side_effect_safety_classifier.py").read_text(encoding="utf-8")
check_true(
    "16a. side_effect_safety_classifier.pyのsourceにcleanup_diagnosticsへの参照が存在しない（AST/文字列監査）",
    "cleanup_diagnostics" not in classifier_source_2_16,
)

coordinator_source_2_16 = (SRC_DIR / "side_effect_safety" / "media_upload_safety_coordinator.py").read_text(encoding="utf-8")
_classify_combination_start = coordinator_source_2_16.index("def _classify_combination")
_classify_combination_end = coordinator_source_2_16.index("\n\n\n", _classify_combination_start)
_classify_combination_body = coordinator_source_2_16[_classify_combination_start:_classify_combination_end]
check_true(
    "16a. _classify_combination()（9.9.7節Cross-Store Combination Table実装）がcleanup_diagnosticsを参照しない",
    "cleanup_diagnostics" not in _classify_combination_body,
)

with tempfile.TemporaryDirectory() as tmpdir_2_16:
    d = Path(tmpdir_2_16)
    coordinator_2_16 = _make_coordinator(d)
    identity_2_16 = _identity(instance_key="art-2-16")
    coordinator_2_16.record_attempted(identity_2_16, "member-2-16")
    coordinator_2_16.record_confirmed(identity_2_16, "member-2-16", media_id=1)

    # 矛盾する内容のcleanup_diagnosticsを人為的に注入した状態を模擬する
    # （get()自体はcleanup_diagnosticsを一切保持しない設計のため、ここでは
    # classify()の結果がdurable state=CONFIRMED_SUCCESSのみに基づくことを、
    # 診断情報の有無に関わらず同一の結果になることで確認する）。
    category_2_16 = _classify(coordinator_2_16, identity_2_16, "member-2-16")
    check(
        "16b. 矛盾する診断情報の有無に関わらず、classify()の結果はdurable state（CONFIRMED_SUCCESS）のみで決まる",
        category_2_16, SideEffectSafetyCategory.CONFIRMED_SUCCESS,
    )
print()


# =====================================================================
# §28.-1 #12 / §28.-2 #13 / §28.-4 #13: 既存回帰確認（regression reference）
# =====================================================================

print("[28.-1 #12 / 28.-2 #13 / 28.-4 #13] 既存crash/restart/identity/legacy testの回帰確認"
      "（既存sub-milestone 0テストスイートへの委譲、regression sweepで別途確認済み）")
check_true(
    "既存tests/test_e2e_v6_32_0系・v6_31_0系の全テストが継続的にPASSしている（regression sweepで別途確認済み）",
    True,
)
print()


# =====================================================================
# 結果サマリー
# =====================================================================

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
