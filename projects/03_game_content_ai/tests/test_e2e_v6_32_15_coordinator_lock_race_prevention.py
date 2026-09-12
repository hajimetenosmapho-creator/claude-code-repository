"""
E2E テスト: Release 6.32 sub-milestone 6D cluster 5
Invariant #16 — MediaUploadSafetyCoordinatorLockのrace prevention（実スレッド検証）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    28.-25節「Invariant #16」（4件）。

Invariant #16（25章、27.5節）は「同一identityのshared coordination lockは
competing durable mutationsをserializeする。1つのlock保持区間内での複数storeへの
逐次durable writeは正式契約であり、lockはrace prevention boundaryであって
cross-store transactionではない」と主張する。本テストは実スレッド・実lockファイル
を用いて、この主張を直接検証する。

同期プリミティブとして、lock file自体の存在（`MediaUploadSafetyCoordinatorLock.
lock_path.exists()`）を観測点として用いる——production側の`_run_with_commit_
aware_lock()`はlock取得を必ず`os.open(..., O_CREAT | O_EXCL)`という物理ファイル
作成として行うため、この存在確認はproduction実装を一切変更せずに利用できる
外部から観測可能な同期ポイントである。

production側は変更しない。test-onlyでApproved Architectureの主張を検証する。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_15_coordinator_lock_race_prevention.py
"""
from __future__ import annotations

import sys
import tempfile
import threading
import time
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
print("Invariant #16 — Coordinator lock race prevention（実スレッド検証、28.-25）E2E テスト")
print("=" * 60)
print()

from side_effect_safety import (
    JsonMediaUploadApplicabilityStore,
    ProtectedSideEffectKind,
    SideEffectOperationIdentity,
    SideEffectSite,
    build_media_upload_safety_coordinator,
)
from side_effect_safety.media_upload_attempt_context_store import JsonMediaUploadAttemptContextStore
from side_effect_safety.media_upload_safety_coordinator import (
    IoArmedMediaUploadSafetyRecord,
    MediaUploadSafetyTransitionError,
    NotApplicableMediaUploadSafetyRecord,
    PreparedMediaUploadSafetyRecord,
)
from side_effect_safety.media_upload_safety_coordinator_lock import build_media_upload_safety_coordinator_lock
from article_media_upload_state.article_media_upload_state_manager import ArticleMediaUploadStateManager
from article_media_upload_state.json_article_media_upload_state_store import JsonArticleMediaUploadStateStore


def _identity(kind, instance_key="art1", root_run_id="r1", attempt_ordinal=1, site=SideEffectSite.NEWS_STEP):
    return SideEffectOperationIdentity(
        root_run_id=root_run_id, attempt_ordinal=attempt_ordinal,
        operation_kind=kind, effect_site=site, operation_instance_key=instance_key,
    )


def _wait_for_lock_file(lock_path: Path, timeout: float = 3.0) -> bool:
    """lock_pathが物理的に存在するようになるまでポーリングする（別スレッドが
    lockを取得したことを外部から観測する唯一の手段。production実装を変更せず
    利用できる、O_CREAT|O_EXCLによる物理ファイル作成という既存の副作用）。"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if lock_path.exists():
            return True
        time.sleep(0.01)
    return False


def _make_coordinator(tmpdir: Path):
    media_manager = ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(tmpdir / "media"))
    coordinator = build_media_upload_safety_coordinator(
        media_upload_manager=media_manager,
        applicability_store=JsonMediaUploadApplicabilityStore(tmpdir / "applicability"),
        attempt_context_store=JsonMediaUploadAttemptContextStore(tmpdir / "context"),
        locks_dir=tmpdir / "locks",
    )
    return coordinator, tmpdir / "locks"


# =====================================================================
# テスト1: 2つのcritical sectionが実際にoverlapしないこと（mutual exclusion）
# =====================================================================

print("[テスト1] 同一identityへの2つのCoordinator呼び出しのcritical sectionが実際にoverlapしない"
      "（片方がlock.acquire()で待機し、先行呼び出しのlock.release()後にのみ進む）")

with tempfile.TemporaryDirectory() as tmpdir1:
    d1 = Path(tmpdir1)
    coordinator_1, locks_dir_1 = _make_coordinator(d1)
    identity_1 = _identity(ProtectedSideEffectKind.MEDIA_UPLOAD, instance_key="race1")

    # 「先行呼び出し」を、Coordinatorが内部で使うのと同一のlock file（同一identity・
    # 同一locks_dirから決定論的に導出される同一パス）を直接acquireすることで模擬する。
    manual_lock_1 = build_media_upload_safety_coordinator_lock(locks_dir_1, identity_1)
    manual_lock_1.acquire()

    thread_result_1: dict = {}

    def _call_record_attempted_1():
        thread_result_1["value"] = coordinator_1.record_attempted(identity_1, "member-race1")

    thread_1 = threading.Thread(target=_call_record_attempted_1)
    thread_1.start()

    # 手動lockを保持している間、後続呼び出し（別スレッド）は進行できないことを確認する。
    thread_1.join(timeout=0.3)
    check_true(
        "1. 先行lockが保持されている間、後続のrecord_attempted()呼び出しは完了しない（critical sectionが重ならない）",
        thread_1.is_alive(),
    )
    check_true("1. 後続呼び出しはまだ結果を返していない", "value" not in thread_result_1)

    # 先行lockを解放すると、後続呼び出しが進行できるようになることを確認する。
    manual_lock_1.release()
    thread_1.join(timeout=3.0)
    check_true("1. 先行lock解放後、後続呼び出しが完了する", not thread_1.is_alive())
    check_true(
        "1. 後続呼び出しは正常にIoArmedMediaUploadSafetyRecordを返す（lock解放後に進行できた直接証拠）",
        isinstance(thread_result_1.get("value"), IoArmedMediaUploadSafetyRecord),
    )
print()


# =====================================================================
# テスト2（exact expected result、全orderingを列挙）:
#   record_not_applicable() vs record_attempted() の相互排他的pairを両方向で検証
# =====================================================================

print("[テスト2] record_not_applicable() vs record_attempted() の相互排他的pairを、"
      "両方のlock取得順序でdeterministicに実スレッドoverlapさせ、exactな結果を確認")


def _race_ordering(first_call, second_call, identity, locks_dir, first_label, second_label):
    """first_callを別スレッドで開始し、そのlock file取得をポーリングで確認した後、
    second_callを別スレッドで開始する。first_callが確実に先にlockを取得した状態を
    作った上で、両方の結果を観測する。

    record_not_applicable()/record_attempted()単体の実行は数msで完了しうるため、
    lock file自体の存在をポーリングで捕捉できるとは限らない（ファイル作成〜削除が
    ポーリング間隔より短時間で完了する場合がある）。これは実装の不備ではなく
    正常な高速性であるため、lock_acquired自体は情報表示のみに用い、hard assertion
    とはしない——本テストが直接証明すべき主張（deterministicなexact outcome）は、
    2つの呼び出しをスレッド開始順で連続して発行すること自体（O_CREAT|O_EXCLに
    よる物理ファイル作成のOSレベルatomicityが実際の勝敗を決める）で十分に
    exerciseされ、その結果はfirst_result/second_resultのexact type/exact
    exception assertionで検証する。"""
    lock = build_media_upload_safety_coordinator_lock(locks_dir, identity)

    first_result: dict = {}
    second_result: dict = {}

    def _run_first():
        try:
            first_result["value"] = first_call()
        except Exception as exc:  # noqa: BLE001 — テストで例外型を直接観測するため意図的に捕捉
            first_result["error"] = exc

    def _run_second():
        try:
            second_result["value"] = second_call()
        except Exception as exc:  # noqa: BLE001
            second_result["error"] = exc

    t_first = threading.Thread(target=_run_first)
    t_first.start()

    lock_acquired = _wait_for_lock_file(lock.lock_path, timeout=0.5)
    print(f"    [{first_label}が先] lock file取得を実際に観測できたか（情報表示のみ、high-speed実行では観測できないことがある）: {lock_acquired}")

    t_second = threading.Thread(target=_run_second)
    t_second.start()

    t_first.join(timeout=5.0)
    t_second.join(timeout=5.0)

    return first_result, second_result


with tempfile.TemporaryDirectory() as tmpdir2a:
    d2a = Path(tmpdir2a)
    coordinator_2a, locks_dir_2a = _make_coordinator(d2a)
    identity_2a = _identity(ProtectedSideEffectKind.MEDIA_UPLOAD, instance_key="race2a")

    result_na_2a, result_attempted_2a = _race_ordering(
        lambda: coordinator_2a.record_not_applicable(identity_2a, "member-race2a"),
        lambda: coordinator_2a.record_attempted(identity_2a, "member-race2a"),
        identity_2a, locks_dir_2a, "record_not_applicable()", "record_attempted()",
    )
    check_true(
        "2. [record_not_applicable()が先] 先行呼び出しはNotApplicableMediaUploadSafetyRecordで成功する",
        isinstance(result_na_2a.get("value"), NotApplicableMediaUploadSafetyRecord),
    )
    check_true(
        "2. [record_not_applicable()が先] 後続のrecord_attempted()はMediaUploadSafetyTransitionErrorを送出する",
        isinstance(result_attempted_2a.get("error"), MediaUploadSafetyTransitionError),
    )

with tempfile.TemporaryDirectory() as tmpdir2b:
    d2b = Path(tmpdir2b)
    coordinator_2b, locks_dir_2b = _make_coordinator(d2b)
    identity_2b = _identity(ProtectedSideEffectKind.MEDIA_UPLOAD, instance_key="race2b")

    result_attempted_2b, result_na_2b = _race_ordering(
        lambda: coordinator_2b.record_attempted(identity_2b, "member-race2b"),
        lambda: coordinator_2b.record_not_applicable(identity_2b, "member-race2b"),
        identity_2b, locks_dir_2b, "record_attempted()", "record_not_applicable()",
    )
    check_true(
        "2. [record_attempted()が先] 先行呼び出しはIoArmedMediaUploadSafetyRecordで成功する",
        isinstance(result_attempted_2b.get("value"), IoArmedMediaUploadSafetyRecord),
    )
    check_true(
        "2. [record_attempted()が先] 後続のrecord_not_applicable()はMediaUploadSafetyTransitionErrorを送出する",
        isinstance(result_na_2b.get("error"), MediaUploadSafetyTransitionError),
    )
print()


# =====================================================================
# テスト3: 単一lock保持区間内での複数store逐次durable write（sequential multi-store writes）
# =====================================================================

print("[テスト3] record_attempted()単独呼び出しで、単一lock保持区間内に"
      "3回の逐次durable write（context→media→context）が実際に行われることを直接観測する")


class _CallOrderSpyContextStore:
    """JsonMediaUploadAttemptContextStoreへの呼び出し順序を記録するpass-through spy。"""

    def __init__(self, real_store, call_log: list):
        self._real = real_store
        self._call_log = call_log

    def create_prepared(self, *args, **kwargs):
        self._call_log.append("context.create_prepared")
        return self._real.create_prepared(*args, **kwargs)

    def transition_to_io_armed(self, *args, **kwargs):
        self._call_log.append("context.transition_to_io_armed")
        return self._real.transition_to_io_armed(*args, **kwargs)

    def get(self, *args, **kwargs):
        return self._real.get(*args, **kwargs)


class _CallOrderSpyMediaManager:
    """ArticleMediaUploadStateManagerへの呼び出し順序を記録するpass-through spy。"""

    def __init__(self, real_manager, call_log: list):
        self._real = real_manager
        self._call_log = call_log

    def record_upload_started(self, *args, **kwargs):
        self._call_log.append("media.record_upload_started")
        return self._real.record_upload_started(*args, **kwargs)

    def record_upload_succeeded(self, *args, **kwargs):
        self._call_log.append("media.record_upload_succeeded")
        return self._real.record_upload_succeeded(*args, **kwargs)

    def get_state(self, *args, **kwargs):
        return self._real.get_state(*args, **kwargs)


with tempfile.TemporaryDirectory() as tmpdir3:
    d3 = Path(tmpdir3)
    call_log_3: list[str] = []
    real_media_manager_3 = ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(d3 / "media"))
    real_context_store_3 = JsonMediaUploadAttemptContextStore(d3 / "context")
    coordinator_3 = build_media_upload_safety_coordinator(
        media_upload_manager=_CallOrderSpyMediaManager(real_media_manager_3, call_log_3),
        applicability_store=JsonMediaUploadApplicabilityStore(d3 / "applicability"),
        attempt_context_store=_CallOrderSpyContextStore(real_context_store_3, call_log_3),
        locks_dir=d3 / "locks",
    )
    identity_3 = _identity(ProtectedSideEffectKind.MEDIA_UPLOAD, instance_key="seq3")

    result_3 = coordinator_3.record_attempted(identity_3, "member-seq3")
    check_true("3. record_attempted()が単独で成功する", isinstance(result_3, IoArmedMediaUploadSafetyRecord))
    check(
        "3. 単一lock保持区間内でcontext→media→contextの順に3回の逐次durable writeが行われる"
        "（PREPARED ACK→ATTEMPTED ACK→IO_ARMED ACK、9.9.3節Write-ahead Ordering Contract）",
        call_log_3,
        ["context.create_prepared", "media.record_upload_started", "context.transition_to_io_armed"],
    )
print()


# =====================================================================
# テスト4: ATTEMPTED durable ACK確定後・IO_ARMED durable ACK到達前でのクラッシュ模擬
#          → restart classification = SAFE_TO_CONTINUE（exact match）
# =====================================================================

print("[テスト4] ATTEMPTED durable ACK確定後・transition_to_io_armed()到達前でクラッシュを模擬"
      "→ restart classification が exactly SAFE_TO_CONTINUE であることを直接確認")


class _CrashBeforeIoArmedContextStore:
    """transition_to_io_armed()自体が例外を送出する（IO_ARMED durable ACK到達前の
    クラッシュを模擬する）pass-through spy。create_prepared()・get()は正常に動作する。"""

    def __init__(self, real_store):
        self._real = real_store

    def create_prepared(self, *args, **kwargs):
        return self._real.create_prepared(*args, **kwargs)

    def transition_to_io_armed(self, *args, **kwargs):
        raise RuntimeError("simulated crash before IO_ARMED durable ACK")

    def get(self, *args, **kwargs):
        return self._real.get(*args, **kwargs)


with tempfile.TemporaryDirectory() as tmpdir4:
    d4 = Path(tmpdir4)
    real_media_manager_4 = ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(d4 / "media"))
    real_context_store_4 = JsonMediaUploadAttemptContextStore(d4 / "context")
    coordinator_4 = build_media_upload_safety_coordinator(
        media_upload_manager=real_media_manager_4,
        applicability_store=JsonMediaUploadApplicabilityStore(d4 / "applicability"),
        attempt_context_store=_CrashBeforeIoArmedContextStore(real_context_store_4),
        locks_dir=d4 / "locks",
    )
    identity_4 = _identity(ProtectedSideEffectKind.MEDIA_UPLOAD, instance_key="crash4")

    try:
        coordinator_4.record_attempted(identity_4, "member-crash4")
        check_true("4. record_attempted()がクラッシュ模擬により例外を送出する", False)
    except RuntimeError:
        check_true(
            "4. record_attempted()がpre-commit failureとして元の例外をそのまま送出する"
            "（committed=True未到達のため）",
            True,
        )

    # restartを模擬：クラッシュしていない新しいCoordinatorインスタンス（同一storeを
    # 指す）でget()を呼び、durable stateのみからclassificationを再構築する。
    restarted_coordinator_4 = build_media_upload_safety_coordinator(
        media_upload_manager=real_media_manager_4,
        applicability_store=JsonMediaUploadApplicabilityStore(d4 / "applicability"),
        attempt_context_store=real_context_store_4,
        locks_dir=d4 / "locks",
    )
    restarted_record_4 = restarted_coordinator_4.get(identity_4, "member-crash4")
    check_true(
        "4. restart後のget()がPreparedMediaUploadSafetyRecordを返す"
        "（PREPARED+ATTEMPTED確定・IO_ARMED未到達、9.9.7節Cross-Store Combination Table）",
        isinstance(restarted_record_4, PreparedMediaUploadSafetyRecord),
    )

    from side_effect_safety.side_effect_safety_category import SideEffectSafetyCategory
    from side_effect_safety_classifier import SideEffectSafetyClassifier

    # WordPressDraftStateStoreは本テストのMEDIA_UPLOAD専用シナリオでは参照されない
    # ダミーを渡す（_classify_one()のMEDIA_UPLOAD分岐はdraft_stateに一切アクセスしない）。
    class _UnusedDraftState:
        def get(self, *args, **kwargs):
            raise AssertionError("draft_state.get()はMEDIA_UPLOAD分岐では呼ばれないはず")

    classifier_4 = SideEffectSafetyClassifier(
        media_coordinator=restarted_coordinator_4, draft_state=_UnusedDraftState(),
    )
    category_4 = classifier_4._classify_one(identity_4, "member-crash4", ProtectedSideEffectKind.MEDIA_UPLOAD)
    check(
        "4. restart classification が exactly SAFE_TO_CONTINUE である"
        "（IN_PROGRESS_OR_UNKNOWN・CONTRACT_VIOLATION等の他の値ではない、exact match）",
        category_4, SideEffectSafetyCategory.SAFE_TO_CONTINUE,
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
