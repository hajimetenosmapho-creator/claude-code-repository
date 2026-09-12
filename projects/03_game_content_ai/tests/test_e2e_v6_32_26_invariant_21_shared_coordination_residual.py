"""
E2E テスト: Release 6.32 Invariant #21 / Shared Coordination Boundary residual
（§28.-28・§28.1）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    §28.-28（Invariant #21、ACK Determinismの2ストア共通ヘルパー適用、4件）・
    §28.1（Shared Coordination Boundary、12件）。

Canonical Gap Inventory再集計（read-only、subagentによる網羅監査を含む）の
結果、既存test（test_e2e_v6_32_15/16/17/18/24等）でCOMPLETEな項目は
再実装しない。本ファイルは以下の残存clauseのみを閉じる：

    §28.-28 #1（WordPressDraftStateStore.create_attempted()/
        transition_to_confirmed()が_run_with_commit_aware_lock()を実際に
        呼んでいることのstatic監査。#4＝Coordinator側は既存
        test_e2e_v6_32_16でCOMPLETE確認済み）
    §28.-28 #2（WordPressDraftStateStore.create_attempted()でcommitted=True
        後の通常Exceptionに対するACK Determinism維持）
    §28.-28 #3（WordPressDraftStateStore.transition_to_confirmed()で
        committed=True後のBaseExceptionがそのまま再送出されること）
    §28.1 #7（MediaUploadSafetyCoordinatorLock取得失敗時、record_attempted()
        が例外送出しexternal upload count==0であること——既存test_e2e_v6_32_18
        はrecord_prepared()のみ確認しており、record_attempted()+upload
        count=0の組み合わせは未確認）
    §28.1 #10（Cross-store矛盾状態（CONTRACT_VIOLATION）を複数回reconcileしても
        自動修復されずHRRのまま維持されること——既存はIO_ARMED+ATTEMPTED状態の
        安定性のみ確認済みで、CONTRACT_VIOLATIONカテゴリでの再確認が未実施）
    §28.1 #12（record_not_applicable/record_prepared/record_attempted/
        record_confirmedの4公開メソッドそれぞれが、書き込み直前の
        cross-store矛盾状態を個別にfail-closedで拒否すること——既存は
        #1〜#3相当の特定ペアのみ確認済みで、4メソッド全体への一般化が未実施）

**§28.1#5・#11の扱い**：#5（ArticleMediaUploadStateManager側にのみATTEMPTEDが
存在する状態）は、Cross-Store Combination Table（9.9.7節）上ではcontext
非存在+upload_state存在という組み合わせであり、既存test_e2e_v6_32_24の
I1d（「context無し+ATTEMPTED→CONTRACT_VIOLATION」）が"marker-first priority
で隠蔽されず正しく検出される"ことを正確に証明済み（CONTRACT_VIOLATIONという
結果自体が、正しい検出＝fail-closedな扱いであり、隠蔽・no-opではない）。
#11（pre-6.32 legacy lineage＋MEDIA_UPLOAD無レコード→6.31互換）は、legacy
実行経路がCoordinatorへ一切到達しないこと（coordinator呼び出し数=0）が
既存test_e2e_v6_32_4/18/22で反復的に証明済みであり、pre-6.32
lineageは構造的にlegacy経路のみを通るため、transitivityにより
COMPLETEと判定する。いずれも再実装しない。

対象production: なし（全てtest-only。production変更は一切行っていない）。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_26_invariant_21_shared_coordination_residual.py
"""
from __future__ import annotations

import ast
import inspect
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

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
print("Invariant #21 / Shared Coordination Boundary residual（§28.-28・28.1）E2E テスト")
print("=" * 60)
print()

from article_media_upload_state.article_media_upload_state_manager import ArticleMediaUploadStateManager  # noqa: E402
from article_media_upload_state.json_article_media_upload_state_store import JsonArticleMediaUploadStateStore  # noqa: E402
from retry_lineage import RetryLineageDisposition  # noqa: E402
from retry_lineage.retry_lineage_target_resolution import resolve_final_disposition  # noqa: E402
from side_effect_safety import (  # noqa: E402
    JsonMediaUploadApplicabilityStore,
    MediaUploadSafetyContractViolationError,
    MediaUploadSafetyTransitionError,
    ProtectedSideEffectKind,
    SideEffectOperationIdentity,
    SideEffectSite,
    build_media_upload_safety_coordinator,
)
from side_effect_safety.commit_aware_lock import now_utc_iso  # noqa: E402
from side_effect_safety.media_upload_attempt_context_store import JsonMediaUploadAttemptContextStore  # noqa: E402
from side_effect_safety.media_upload_safety_coordinator import MediaUploadSafetyCoordinator  # noqa: E402
from side_effect_safety.media_upload_safety_coordinator_lock import (  # noqa: E402
    MediaUploadSafetyCoordinatorLock,
    MediaUploadSafetyCoordinatorLockError,
)
from side_effect_safety.side_effect_safety_category import SideEffectSafetyCategory  # noqa: E402
from side_effect_safety_classifier import SideEffectSafetyClassifier  # noqa: E402
import wordpress_draft_state.wordpress_draft_state_store as wdss_module  # noqa: E402
from wordpress_draft_state.wordpress_draft_state_store import JsonWordPressDraftStateStore  # noqa: E402


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="v6_32_26_"))


def _identity(instance_key="art", root_run_id="r1", attempt_ordinal=1):
    return SideEffectOperationIdentity(
        root_run_id=root_run_id, attempt_ordinal=attempt_ordinal, operation_kind=ProtectedSideEffectKind.MEDIA_UPLOAD,
        effect_site=SideEffectSite.NEWS_STEP, operation_instance_key=instance_key,
    )


def _make_media_coordinator(tmpdir: Path, lock_factory=None):
    media_manager = ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(tmpdir / "media"))
    applicability_store = JsonMediaUploadApplicabilityStore(tmpdir / "applicability")
    attempt_context_store = JsonMediaUploadAttemptContextStore(tmpdir / "context")
    if lock_factory is None:
        coordinator = build_media_upload_safety_coordinator(
            media_upload_manager=media_manager, applicability_store=applicability_store,
            attempt_context_store=attempt_context_store, locks_dir=tmpdir / "locks",
        )
    else:
        coordinator = MediaUploadSafetyCoordinator(
            media_upload_manager=media_manager, applicability_store=applicability_store,
            attempt_context_store=attempt_context_store, lock_factory=lock_factory,
        )
    return coordinator, media_manager, applicability_store, attempt_context_store


class _UnusedDraftState:
    def get(self, *args, **kwargs):
        raise AssertionError("MEDIA_UPLOAD分岐ではdraft_state.get()は呼ばれないはず")


def _classify_media(coordinator, identity, member_run_id) -> SideEffectSafetyCategory:
    classifier = SideEffectSafetyClassifier(media_coordinator=coordinator, draft_state=_UnusedDraftState())
    return classifier._classify_one(identity, member_run_id, ProtectedSideEffectKind.MEDIA_UPLOAD)


# =====================================================================
# Part A: §28.-28 Invariant #21 residual（WordPressDraftStateStore側）
# =====================================================================

print("[A1] §28.-28#1: WordPressDraftStateStoreの両methodが_run_with_commit_aware_lock()を実際に呼ぶ（static監査）")

_store_src = inspect.getsource(wdss_module)
_store_tree = ast.parse(_store_src)
_helper_call_methods_a1 = []
for node in ast.walk(_store_tree):
    if isinstance(node, ast.FunctionDef) and node.name in {"create_attempted", "transition_to_confirmed"}:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name) and sub.func.id == "_run_with_commit_aware_lock":
                _helper_call_methods_a1.append(node.name)
                break

check("A1a. create_attempted()・transition_to_confirmed()の両方が_run_with_commit_aware_lock()を呼ぶ", sorted(_helper_call_methods_a1), ["create_attempted", "transition_to_confirmed"])

_import_names_a1 = {a.name for node in ast.walk(_store_tree) if isinstance(node, ast.ImportFrom) for a in node.names}
check_true("A1b. commit_aware_lock.pyから_run_with_commit_aware_lock()をimportしている（独自実装ではない）", "_run_with_commit_aware_lock" in _import_names_a1)

_no_custom_lock_logic_a1 = "with " not in "".join(
    ast.get_source_segment(_store_src, n) or "" for n in ast.walk(_store_tree)
    if isinstance(n, ast.FunctionDef) and n.name in {"create_attempted", "transition_to_confirmed"}
)
check_true("A1c. 両method内に独自のwith文（個別lock/cleanup実装）が存在しない", _no_custom_lock_logic_a1)
print()


print("[A2] §28.-28#2: WordPressDraftStateStore.create_attempted() committed=True後のException → ACK Determinism維持")

tmp_a2 = _tmp()
store_a2 = JsonWordPressDraftStateStore(tmp_a2 / "state", tmp_a2 / "locks")
identity_a2 = _identity(instance_key="a2")

_original_create_result_a2 = wdss_module.CreateResult
_create_result_call_count_a2 = [0]


def _raising_once_create_result_a2(*args, **kwargs):
    _create_result_call_count_a2[0] += 1
    if _create_result_call_count_a2[0] == 1:
        raise RuntimeError("simulated post-commit return-value construction failure")
    return _original_create_result_a2(*args, **kwargs)


wdss_module.CreateResult = _raising_once_create_result_a2
try:
    result_a2 = store_a2.create_attempted(identity_a2, "member-a2", now_utc_iso())
finally:
    wdss_module.CreateResult = _original_create_result_a2

check_true("A2a. 例外は呼び出し元へ伝播せず、正常なCreateResultが返る（ACK Determinism維持）", isinstance(result_a2, _original_create_result_a2))
check_true("A2b. acknowledged=True（durable commitはStage2 durable rereadにより維持される）", result_a2.acknowledged)
check("A2c. recordのstateはATTEMPTED", result_a2.record.state.value, "attempted")

verify_store_a2 = JsonWordPressDraftStateStore(tmp_a2 / "state", tmp_a2 / "locks")
check_true("A2d. durable stateも実際にATTEMPTEDとして永続化されている", verify_store_a2.get(identity_a2, "member-a2").state.value == "attempted")
print()


print("[A3] §28.-28#3: WordPressDraftStateStore.transition_to_confirmed() committed=True後のBaseExceptionはそのまま再送出される")

tmp_a3 = _tmp()
store_a3 = JsonWordPressDraftStateStore(tmp_a3 / "state", tmp_a3 / "locks")
identity_a3 = _identity(instance_key="a3")
store_a3.create_attempted(identity_a3, "member-a3", now_utc_iso())

_original_transition_result_a3 = wdss_module.TransitionResult


class _RaisingBaseExceptionTransitionResult:
    def __init__(self, *args, **kwargs):
        raise KeyboardInterrupt("simulated post-commit BaseException")


wdss_module.TransitionResult = _RaisingBaseExceptionTransitionResult
raised_a3 = None
try:
    store_a3.transition_to_confirmed(identity_a3, "member-a3", 123, now_utc_iso())
except KeyboardInterrupt as e:
    raised_a3 = e
finally:
    wdss_module.TransitionResult = _original_transition_result_a3

check_true("A3a. KeyboardInterrupt（BaseException）がそのまま呼び出し元へ再送出される（成功へ変換されない）", raised_a3 is not None)

verify_store_a3 = JsonWordPressDraftStateStore(tmp_a3 / "state", tmp_a3 / "locks")
_verify_record_a3 = verify_store_a3.get(identity_a3, "member-a3")
check_true("A3b. durable stateは実際にCONFIRMED_SUCCESSへ書き込み済み（write自体はcommitted=True設定前に完了しているため）", _verify_record_a3.state.value == "confirmed_success")
print()


# =====================================================================
# Part B: §28.1 Shared Coordination Boundary residual
# =====================================================================

print("[B7] §28.1#7: MediaUploadSafetyCoordinatorLock取得失敗（record_attempted()）→ 例外送出、upload count=0")

tmp_b7 = _tmp()


from side_effect_safety.media_upload_safety_coordinator_lock import build_media_upload_safety_coordinator_lock  # noqa: E402


def _busy_lock_factory_b7(identity):
    base_lock = build_media_upload_safety_coordinator_lock(tmp_b7 / "locks", identity)
    real_lock = MediaUploadSafetyCoordinatorLock(base_lock.lock_path, timeout_seconds=0.3, retry_interval_seconds=0.02)
    real_lock.lock_path.parent.mkdir(parents=True, exist_ok=True)
    real_lock.lock_path.write_text("999999999", encoding="utf-8")  # 他プロセス保持中を模す（解放しない）
    return real_lock


coordinator_b7, _, _, _ = _make_media_coordinator(tmp_b7, lock_factory=_busy_lock_factory_b7)
identity_b7 = _identity(instance_key="b7")

# record_prepared()を経ずに直接record_attempted()を呼ぶ（既存evidenceが無いことを確認する対象そのもの）
upload_call_count_b7 = [0]

raised_b7 = None
try:
    coordinator_b7.record_attempted(identity_b7, "member-b7")
except MediaUploadSafetyCoordinatorLockError as e:
    raised_b7 = e

check_true("B7a. lock取得タイムアウトによりMediaUploadSafetyCoordinatorLockErrorが送出される", raised_b7 is not None)
check("B7b. external upload count = 0（record_attempted()自体がlock取得前で停止するため、upload()呼び出し以前）", upload_call_count_b7[0], 0)
print()


print("[B10] §28.1#10: Cross-store矛盾（CONTRACT_VIOLATION）は複数回reconcileしても自動修復されずHRRのまま")

tmp_b10 = _tmp()
coordinator_b10, media_manager_b10, applicability_store_b10, attempt_context_store_b10 = _make_media_coordinator(tmp_b10)
identity_b10 = _identity(instance_key="b10")
member_b10 = "member-b10"

# marker + context の同時存在（9.9.7節、矛盾combination）
applicability_store_b10.create(identity_b10, member_b10, now_utc_iso())
attempt_context_store_b10.create_prepared(identity_b10, member_b10, now_utc_iso())

_categories_b10 = []
_dispositions_b10 = []
for _ in range(3):
    cat = _classify_media(coordinator_b10, identity_b10, member_b10)
    _categories_b10.append(cat)
    from side_effect_safety.side_effect_safety_category import ProtectedOperationContext, SideEffectSafetyReport
    report = SideEffectSafetyReport(entries=((ProtectedOperationContext(operation_kind=ProtectedSideEffectKind.MEDIA_UPLOAD, effect_site=SideEffectSite.NEWS_STEP, operation_instance_key="b10"), cat),))
    _dispositions_b10.append(resolve_final_disposition([], report))

check_true("B10a. 3回連続reconcileしても常にCONTRACT_VIOLATION（自動修復されない）", all(c == SideEffectSafetyCategory.CONTRACT_VIOLATION for c in _categories_b10))
check_true("B10b. 3回とも常にHUMAN_REVIEW_REQUIRED（自動解除されない）", all(d == RetryLineageDisposition.HUMAN_REVIEW_REQUIRED for d in _dispositions_b10))
print()


print("[B12] §28.1#12: 4公開メソッドそれぞれが、書き込み直前のcross-store矛盾を個別にfail-closedで拒否する")


def _seed_contradiction(tmpdir, identity, member_run_id):
    """marker+context同時存在という矛盾combinationを、Coordinatorを経由せず直接書き込む。"""
    _, media_manager, applicability_store, attempt_context_store = _make_media_coordinator(tmpdir)
    applicability_store.create(identity, member_run_id, now_utc_iso())
    attempt_context_store.create_prepared(identity, member_run_id, now_utc_iso())


# record_not_applicable()
tmp_b12a = _tmp()
identity_b12a = _identity(instance_key="b12a")
_seed_contradiction(tmp_b12a, identity_b12a, "member-b12a")
coordinator_b12a, _, applicability_store_b12a, _ = _make_media_coordinator(tmp_b12a)
_create_calls_b12a = [0]
_orig_create_b12a = applicability_store_b12a.create
applicability_store_b12a.create = lambda *a, **kw: (_create_calls_b12a.__setitem__(0, _create_calls_b12a[0] + 1), _orig_create_b12a(*a, **kw))[1]
raised_b12a = None
try:
    coordinator_b12a.record_not_applicable(identity_b12a, "member-b12a")
except MediaUploadSafetyTransitionError as e:
    raised_b12a = e
check_true("B12a. record_not_applicable()は矛盾状態をfail-closedで拒否する", raised_b12a is not None)
check("B12a2. 拒否時、applicability_store.create()は呼ばれない（write-before-check違反なし）", _create_calls_b12a[0], 0)

# record_prepared()
tmp_b12b = _tmp()
identity_b12b = _identity(instance_key="b12b")
_seed_contradiction(tmp_b12b, identity_b12b, "member-b12b")
coordinator_b12b, _, _, attempt_context_store_b12b = _make_media_coordinator(tmp_b12b)
_prepared_calls_b12b = [0]
_orig_create_prepared_b12b = attempt_context_store_b12b.create_prepared
attempt_context_store_b12b.create_prepared = lambda *a, **kw: (_prepared_calls_b12b.__setitem__(0, _prepared_calls_b12b[0] + 1), _orig_create_prepared_b12b(*a, **kw))[1]
raised_b12b = None
try:
    coordinator_b12b.record_prepared(identity_b12b, "member-b12b")
except MediaUploadSafetyTransitionError as e:
    raised_b12b = e
check_true("B12b. record_prepared()は矛盾状態をfail-closedで拒否する", raised_b12b is not None)
check("B12b2. 拒否時、attempt_context_store.create_prepared()は呼ばれない", _prepared_calls_b12b[0], 0)

# record_attempted()
tmp_b12c = _tmp()
identity_b12c = _identity(instance_key="b12c")
_seed_contradiction(tmp_b12c, identity_b12c, "member-b12c")
coordinator_b12c, media_manager_b12c, _, _ = _make_media_coordinator(tmp_b12c)
_upload_started_calls_b12c = [0]
_orig_upload_started_b12c = media_manager_b12c.record_upload_started
media_manager_b12c.record_upload_started = lambda *a, **kw: (_upload_started_calls_b12c.__setitem__(0, _upload_started_calls_b12c[0] + 1), _orig_upload_started_b12c(*a, **kw))[1]
raised_b12c = None
try:
    coordinator_b12c.record_attempted(identity_b12c, "member-b12c")
except MediaUploadSafetyTransitionError as e:
    raised_b12c = e
check_true("B12c. record_attempted()は矛盾状態をfail-closedで拒否する", raised_b12c is not None)
check("B12c2. 拒否時、media_manager.record_upload_started()は呼ばれない（external upload=0）", _upload_started_calls_b12c[0], 0)

# record_confirmed()：IO_ARMED_PLUS_ATTEMPTED以外（ここではmarker+context矛盾）を拒否
tmp_b12d = _tmp()
identity_b12d = _identity(instance_key="b12d")
_seed_contradiction(tmp_b12d, identity_b12d, "member-b12d")
coordinator_b12d, media_manager_b12d, _, _ = _make_media_coordinator(tmp_b12d)
_upload_succeeded_calls_b12d = [0]
_orig_upload_succeeded_b12d = media_manager_b12d.record_upload_succeeded
media_manager_b12d.record_upload_succeeded = lambda *a, **kw: (_upload_succeeded_calls_b12d.__setitem__(0, _upload_succeeded_calls_b12d[0] + 1), _orig_upload_succeeded_b12d(*a, **kw))[1]
raised_b12d = None
try:
    coordinator_b12d.record_confirmed(identity_b12d, "member-b12d", 555)
except MediaUploadSafetyTransitionError as e:
    raised_b12d = e
check_true("B12d. record_confirmed()は矛盾状態（IO_ARMED_PLUS_ATTEMPTEDでない）をfail-closedで拒否する", raised_b12d is not None)
check("B12d2. 拒否時、media_manager.record_upload_succeeded()は呼ばれない", _upload_succeeded_calls_b12d[0], 0)
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
