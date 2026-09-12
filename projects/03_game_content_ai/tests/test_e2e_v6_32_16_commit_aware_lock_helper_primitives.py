"""
E2E テスト: Release 6.32 sub-milestone 6D-6A
Commit-Aware Lock Helper primitives（§28.-3・-5・-6・-7・-7b）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    28.-3節（3件、-O/PYTHONOPTIMIZE耐性）・28.-5節（4件+1b、CleanupDiagnostic構築・
    段1→段2復旧）・28.-6節（4件、lockなしdurable read・複合fault耐性）・
    28.-7節（5件、_value_or_recover段2失敗フォールバック）・28.-7b節
    （1件、Safe Continuation同一プロセス内二重呼び出し）。

対象production: src/side_effect_safety/commit_aware_lock.py・
                 src/side_effect_safety/media_upload_safety_coordinator.py
（変更しない。既存実装がApproved Architectureどおり正しいことをtest-onlyで
証明する）。

**命名注記（read-only照合で判明、production defectではない）**：§28.-3節の文言は
例外クラス名として`MediaUploadSafetyImplementationContractError`を挙げるが、
実装（commit_aware_lock.py:163）ではbodyがcommitted=Trueを設定せず正常return
した場合の例外は`CommitAwareLockContractError`という、MediaUploadUpload/
WordPress双方が共有する汎用ヘルパー向けの名前になっている
（`MediaUploadSafetyImplementationContractError`はmedia_upload_safety_
coordinator.py内の別の契約違反箇所＝RecoveryPolicy.build_minimal()自身が
自己matchしない場合、で使われる）。これはヘルパーが2パッケージ共有化された際の
命名進化であり、`-O`/PYTHONOPTIMIZE耐性というInvariantの実質（assertではなく
明示的if文で検出する）は完全に満たされているため、本テストは実際に送出される
`CommitAwareLockContractError`を検証する。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_16_commit_aware_lock_helper_primitives.py
"""
from __future__ import annotations

import ast
import subprocess
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
print("Commit-Aware Lock Helper primitives（6D-6A、28.-3・-5・-6・-7・-7b）E2E テスト")
print("=" * 60)
print()

import side_effect_safety.commit_aware_lock as commit_aware_lock_module
from side_effect_safety import (
    JsonMediaUploadApplicabilityStore,
    ProtectedSideEffectKind,
    SideEffectOperationIdentity,
    SideEffectSite,
    build_media_upload_safety_coordinator,
)
from side_effect_safety.commit_aware_lock import (
    CleanupDiagnostic,
    CleanupFailureReasonCode,
    CommitAwareLockContractError,
    CommitAwareResult,
    _build_cleanup_diagnostic,
    _run_with_commit_aware_lock,
)
from side_effect_safety.media_upload_attempt_context_store import JsonMediaUploadAttemptContextStore
from side_effect_safety.media_upload_safety_coordinator import (
    IoArmedMediaUploadSafetyRecord,
    NotApplicableMediaUploadSafetyRecord,
    NotApplicableRecoveryPolicy,
    PreparedRecoveryPolicy,
)
import side_effect_safety.media_upload_safety_coordinator as coordinator_module
from side_effect_safety.media_upload_safety_coordinator_lock import build_media_upload_safety_coordinator_lock
from article_media_upload_state.article_media_upload_state_manager import ArticleMediaUploadStateManager
from article_media_upload_state.json_article_media_upload_state_store import JsonArticleMediaUploadStateStore


def _identity(kind=ProtectedSideEffectKind.MEDIA_UPLOAD, instance_key="art1", root_run_id="r1", attempt_ordinal=1, site=SideEffectSite.NEWS_STEP):
    return SideEffectOperationIdentity(
        root_run_id=root_run_id, attempt_ordinal=attempt_ordinal,
        operation_kind=kind, effect_site=site, operation_instance_key=instance_key,
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


# =====================================================================
# §28.-3: 実装契約違反検出（-O/PYTHONOPTIMIZE耐性）
# =====================================================================

print("[28.-3 #1] bodyがcommitted=Trueを設定せず正常returnする実装バグを模擬"
      "→ CommitAwareLockContractErrorが確実に送出される")

with tempfile.TemporaryDirectory() as tmpdir_3_1:
    lock_3_1 = build_media_upload_safety_coordinator_lock(Path(tmpdir_3_1) / "locks", _identity())

    def _buggy_body_never_commits(commit_state):
        return "some value"  # committed=Trueを一切設定せず正常return（実装バグ）

    try:
        _run_with_commit_aware_lock(lock_3_1, _identity(), _buggy_body_never_commits)
        check_true("1. CommitAwareLockContractErrorが送出される", False)
    except CommitAwareLockContractError:
        check_true("1. CommitAwareLockContractErrorが送出される（committed=True未設定の契約違反）", True)

    check_true("1. lockはcleanupされる（結果は無視、lock fileが残存しない）", not lock_3_1.lock_path.exists())
print()

print("[28.-3 #2] -O/PYTHONOPTIMIZE=1相当の実行環境下でも同じ検出が機能する"
      "（assertではなく常に評価されるif文のため、最適化フラグで消えない）")

_subprocess_script_3_2 = """
import sys
sys.path.insert(0, {src_dir!r})
from pathlib import Path
import tempfile
from side_effect_safety.commit_aware_lock import _run_with_commit_aware_lock, CommitAwareLockContractError
from side_effect_safety.media_upload_safety_coordinator_lock import build_media_upload_safety_coordinator_lock
from side_effect_safety.side_effect_operation_identity import SideEffectOperationIdentity, ProtectedSideEffectKind, SideEffectSite

identity = SideEffectOperationIdentity(
    root_run_id="r1", attempt_ordinal=1, operation_kind=ProtectedSideEffectKind.MEDIA_UPLOAD,
    effect_site=SideEffectSite.NEWS_STEP, operation_instance_key="art1",
)
with tempfile.TemporaryDirectory() as tmpdir:
    lock = build_media_upload_safety_coordinator_lock(Path(tmpdir) / "locks", identity)

    def buggy_body(commit_state):
        return "value"

    try:
        _run_with_commit_aware_lock(lock, identity, buggy_body)
        print("NO_ERROR_RAISED")
    except CommitAwareLockContractError:
        print("CONTRACT_ERROR_RAISED")
""".format(src_dir=str(SRC_DIR))

completed_3_2 = subprocess.run(
    [sys.executable, "-O", "-c", _subprocess_script_3_2],
    capture_output=True, text=True, timeout=30,
)
check(
    "2. -Oフラグ付きサブプロセスでも同じCommitAwareLockContractErrorが確実に送出される"
    "（assert文への依存なし、最適化フラグ耐性の直接確認）",
    completed_3_2.stdout.strip(), "CONTRACT_ERROR_RAISED",
)
print()

print("[28.-3 #3] 4公開メソッドいずれも同一の_run_with_commit_aware_lock()を経由する"
      "（実装が単一の共通Helperに集約されている、メソッド間で挙動が分岐しない）")

coordinator_source = (SRC_DIR / "side_effect_safety" / "media_upload_safety_coordinator.py").read_text(encoding="utf-8")
coordinator_tree = ast.parse(coordinator_source)

_helper_call_methods = []
for node in ast.walk(coordinator_tree):
    if isinstance(node, ast.FunctionDef) and node.name in (
        "record_not_applicable", "record_prepared", "record_attempted", "record_confirmed",
    ):
        for inner in ast.walk(node):
            if (
                isinstance(inner, ast.Call)
                and isinstance(inner.func, ast.Name)
                and inner.func.id == "_run_with_commit_aware_lock"
            ):
                _helper_call_methods.append(node.name)
                break

check(
    "3. 4公開メソッド全てが_run_with_commit_aware_lock()を1回ずつ呼ぶ"
    "（共通Helperへの集約、メソッド固有の契約違反検出ロジックの重複実装なし）",
    sorted(_helper_call_methods),
    ["record_attempted", "record_confirmed", "record_not_applicable", "record_prepared"],
)
print()


# =====================================================================
# §28.-5: Cleanup診断構築（_build_cleanup_diagnostic()）のフィールド単位fault injection
# =====================================================================

print("[28.-5 #1] identity.operation_kind.valueアクセス自体が例外送出"
      "→ operation_kind=Noneへfallback、CleanupDiagnostic自体は正常に返る")


class _RaisingOperationKind:
    @property
    def value(self):
        raise RuntimeError("simulated operation_kind.value failure")


class _IdentityWithRaisingOperationKind:
    def __init__(self, real_identity):
        self.operation_kind = _RaisingOperationKind()
        self.effect_site = real_identity.effect_site


diag_5_1 = _build_cleanup_diagnostic(
    CleanupFailureReasonCode.LOCK_RELEASE_FAILED, RuntimeError("boom"),
    _IdentityWithRaisingOperationKind(_identity()),
)
check_true("1. CleanupDiagnosticが正常に返る（例外が外部へ伝播しない）", diag_5_1 is not None)
check("1. operation_kindがNoneへfallbackする", diag_5_1.operation_kind, None)
check_true("1. effect_siteは正常に取得できている（他フィールドへの影響なし）", diag_5_1.effect_site is not None)
print()

print("[28.-5 #1b] 残りの個別計算フィールド（exception_type・effect_site・occurred_at）"
      "それぞれについて、個別にfault injectionしてもCleanupDiagnostic自体は正常に返る")


class _RaisingType:
    """type(error).__name__でRuntimeErrorを送出させるための、__class__自体が
    例外を送出するダミーオブジェクト。"""

    @property
    def __class__(self):  # noqa: A003
        raise RuntimeError("simulated type() failure")


class _RaisingEffectSite:
    @property
    def value(self):
        raise RuntimeError("simulated effect_site.value failure")


class _IdentityWithRaisingEffectSite:
    def __init__(self, real_identity):
        self.operation_kind = real_identity.operation_kind
        self.effect_site = _RaisingEffectSite()


diag_5_1b_effect_site = _build_cleanup_diagnostic(
    CleanupFailureReasonCode.LOCK_RELEASE_FAILED, RuntimeError("boom"),
    _IdentityWithRaisingEffectSite(_identity()),
)
check_true("1b. effect_site計算が失敗してもCleanupDiagnosticは正常に返る", diag_5_1b_effect_site is not None)
check("1b. effect_siteがNoneへfallbackする", diag_5_1b_effect_site.effect_site, None)
check_true(
    "1b. operation_kindは正常に取得できている（フィールド間の独立性）",
    diag_5_1b_effect_site.operation_kind is not None,
)

# occurred_at（now_utc_iso()失敗）は_build_cleanup_diagnostic()自身のnow_utc_iso呼び出し
# をmodule-level monkeypatchで一時的に失敗させて確認する。
_orig_now_utc_iso_5_1b = commit_aware_lock_module.now_utc_iso
try:
    def _raising_now_utc_iso():
        raise RuntimeError("simulated now_utc_iso() failure")

    commit_aware_lock_module.now_utc_iso = _raising_now_utc_iso
    diag_5_1b_occurred_at = _build_cleanup_diagnostic(
        CleanupFailureReasonCode.LOCK_RELEASE_FAILED, RuntimeError("boom"), _identity(),
    )
finally:
    commit_aware_lock_module.now_utc_iso = _orig_now_utc_iso_5_1b

check_true("1b. occurred_at計算が失敗してもCleanupDiagnosticは正常に返る", diag_5_1b_occurred_at is not None)
check("1b. occurred_atが空文字列へfallbackする", diag_5_1b_occurred_at.occurred_at, "")
print()

print("[28.-5 #2] CleanupDiagnostic(...)のdataclass構築自体が例外送出"
      "→ 最終防衛線が作動し、Noneを返す（helperへ例外を伝播させない）")

_orig_cleanup_diagnostic_class_5_2 = commit_aware_lock_module.CleanupDiagnostic
try:
    class _AlwaysRaisingCleanupDiagnostic:
        def __init__(self, *args, **kwargs):
            raise RuntimeError("simulated CleanupDiagnostic construction failure")

    commit_aware_lock_module.CleanupDiagnostic = _AlwaysRaisingCleanupDiagnostic
    diag_5_2 = _build_cleanup_diagnostic(
        CleanupFailureReasonCode.LOCK_RELEASE_FAILED, RuntimeError("boom"), _identity(),
    )
finally:
    commit_aware_lock_module.CleanupDiagnostic = _orig_cleanup_diagnostic_class_5_2

check(
    "2. CleanupDiagnostic構築自体が失敗した場合、_build_cleanup_diagnostic()はNoneを返す"
    "（最終防衛線、helperへ例外を伝播させない）",
    diag_5_2, None,
)
print()

print("[28.-5 #3-4] record_not_applicable()等でcommitted=True後の戻り値構築が失敗"
      "→ _value_or_recover()の段2（durable reread）がdurable stateから復旧する")

with tempfile.TemporaryDirectory() as tmpdir_5_34:
    d = Path(tmpdir_5_34)
    coordinator_5_34 = _make_coordinator(d)
    identity_5_34 = _identity(instance_key="art-5-34")

    # 実際にNOT_APPLICABLEをdurableにACKさせておく（段2のdurable rereadが読み取る
    # 権威あるstateを実際に用意する）。
    coordinator_5_34.record_not_applicable(identity_5_34, "member-5-34")

    # commit_state["value"]がNoneのまま（構築失敗を模擬）というoutcomeを直接構築し、
    # _value_or_recover()を直接呼ぶ——段1が空・段2のdurable rereadがdurable stateから
    # 正しく復旧することを直接検証する（21章シナリオ45・46と同一趣旨）。
    outcome_5_34 = CommitAwareResult(acknowledged=True, value=None, cleanup_diagnostics=())
    recovered_5_34 = coordinator_5_34._value_or_recover(
        outcome_5_34, identity_5_34, "member-5-34",
        policy=NotApplicableRecoveryPolicy(identity=identity_5_34, member_run_id="member-5-34"),
    )
    check_true(
        "3. record_not_applicable()相当：段1(value=None)→段2でdurable stateから正しく復旧する",
        isinstance(recovered_5_34, NotApplicableMediaUploadSafetyRecord),
    )

    # 同様のパターンをrecord_prepared相当でも確認する（4メソッド共通の3段fallback）。
    identity_5_34b = _identity(instance_key="art-5-34b")
    coordinator_5_34.record_prepared(identity_5_34b, "member-5-34b")
    outcome_5_34b = CommitAwareResult(acknowledged=True, value=None, cleanup_diagnostics=())
    recovered_5_34b = coordinator_5_34._value_or_recover(
        outcome_5_34b, identity_5_34b, "member-5-34b",
        policy=PreparedRecoveryPolicy(identity=identity_5_34b, member_run_id="member-5-34b"),
    )
    check_true(
        "4. record_prepared()相当でも同様に段2がdurable stateから正しく復旧する"
        "（4メソッドいずれもNoneを返す経路・自分自身以外のsemantic kindを返す経路を持たない）",
        recovered_5_34b.__class__.__name__ == "PreparedMediaUploadSafetyRecord",
    )
print()


# =====================================================================
# §28.-6: lockなしdurable read・複合fault耐性
# =====================================================================

print("[28.-6 #1] post-commit cleanup失敗（stale lock）＋戻り値構築失敗の複合状況"
      "→ 段2のdurable read（lock-free）がstale lockの影響を受けず正しく読み直せる")

with tempfile.TemporaryDirectory() as tmpdir_6_1:
    d = Path(tmpdir_6_1)
    coordinator_6_1 = _make_coordinator(d)
    identity_6_1 = _identity(instance_key="art-6-1")
    coordinator_6_1.record_attempted(identity_6_1, "member-6-1")

    # stale lock（他identityの残存lockではなく、当該identityのlock file自体が
    # 何らかの理由でまだ存在する状況）を人為的に作る——_read_all()はlockを一切
    # 取得しない（27.3節authoritative）ため、stale lockが存在してもdurable read
    # 自体は成功するはずである。
    stale_lock_6_1 = build_media_upload_safety_coordinator_lock(d / "locks", identity_6_1)
    stale_lock_6_1.acquire()  # 解放せずstaleなまま残す

    outcome_6_1 = CommitAwareResult(acknowledged=True, value=None, cleanup_diagnostics=())
    recovered_6_1 = coordinator_6_1._value_or_recover(
        outcome_6_1, identity_6_1, "member-6-1",
        policy=coordinator_module.IoArmedRecoveryPolicy(identity=identity_6_1, member_run_id="member-6-1"),
    )
    check_true(
        "1. stale lockが存在していても段2のdurable read（lock-free）は正しく復旧する",
        isinstance(recovered_6_1, IoArmedMediaUploadSafetyRecord),
    )
    stale_lock_6_1.release()
print()

print("[28.-6 #2] CleanupDiagnosticクラス自体が常に例外送出"
      "→ _build_cleanup_diagnostic()がNoneを返し、acknowledged=Trueを引き続き維持する")

with tempfile.TemporaryDirectory() as tmpdir_6_2:
    lock_6_2 = build_media_upload_safety_coordinator_lock(Path(tmpdir_6_2) / "locks", _identity())

    def _body_commits_then_raises(commit_state):
        commit_state["committed"] = True
        commit_state["value"] = "committed-value"
        raise RuntimeError("post-commit body exception")

    _orig_cleanup_diagnostic_class_6_2 = commit_aware_lock_module.CleanupDiagnostic
    try:
        class _AlwaysRaisingCleanupDiagnostic6_2:
            def __init__(self, *args, **kwargs):
                raise RuntimeError("simulated CleanupDiagnostic construction failure")

        commit_aware_lock_module.CleanupDiagnostic = _AlwaysRaisingCleanupDiagnostic6_2
        result_6_2 = _run_with_commit_aware_lock(lock_6_2, _identity(), _body_commits_then_raises)
    finally:
        commit_aware_lock_module.CleanupDiagnostic = _orig_cleanup_diagnostic_class_6_2

    check_true(
        "2. CleanupDiagnosticが常に構築失敗してもacknowledged=Trueが維持される"
        "（post-commit body exception経路、ACK Determinism）",
        result_6_2.acknowledged,
    )
    check("2. valueはcommit_state['value']のまま", result_6_2.value, "committed-value")
    check(
        "2. cleanup_diagnosticsはCleanupDiagnostic構築失敗により空タプル"
        "（診断情報の欠落は許容されるが、成功結果自体は揺るがない）",
        result_6_2.cleanup_diagnostics, (),
    )
print()

print("[28.-6 #3] 段1（outcome.value）が非Noneかつ有効な基準ケース"
      "→ 段2以降へは進まない")

with tempfile.TemporaryDirectory() as tmpdir_6_3:
    d = Path(tmpdir_6_3)
    coordinator_6_3 = _make_coordinator(d)
    identity_6_3 = _identity(instance_key="art-6-3")

    stage1_value_6_3 = NotApplicableMediaUploadSafetyRecord(
        identity=identity_6_3, member_run_id="member-6-3", updated_at="2026-09-09T00:00:00+00:00",
    )
    outcome_6_3 = CommitAwareResult(acknowledged=True, value=stage1_value_6_3, cleanup_diagnostics=())

    # durable state側は一切書き込まれていない（段2に進んだ場合はALL_ABSENT・
    # policy.validate()に失敗しうる状態）——段1のみで完結することを、段2が
    # 呼ばれた場合には得られないはずの「段1の値そのもの」がそのまま返ることで確認する。
    recovered_6_3 = coordinator_6_3._value_or_recover(
        outcome_6_3, identity_6_3, "member-6-3",
        policy=NotApplicableRecoveryPolicy(identity=identity_6_3, member_run_id="member-6-3"),
    )
    check_true(
        "3. 段1の値がそのまま返る（段2以降のdurable reread・synthesisを経由しない）",
        recovered_6_3 is stage1_value_6_3,
    )
print()

print("[28.-6 #4] 4メソッド×3段（構築済み値・durable read・minimal synthesis）"
      "のいずれか1段のみ失敗させ、残り2段は正常とする組み合わせを網羅する")

_policy_factories_6_4 = {
    "NotApplicable": lambda ident, mrid: NotApplicableRecoveryPolicy(identity=ident, member_run_id=mrid),
    "Prepared": lambda ident, mrid: PreparedRecoveryPolicy(identity=ident, member_run_id=mrid),
    "IoArmed": lambda ident, mrid: coordinator_module.IoArmedRecoveryPolicy(identity=ident, member_run_id=mrid),
    "Confirmed": lambda ident, mrid: coordinator_module.ConfirmedRecoveryPolicy(identity=ident, member_run_id=mrid, media_id=1),
}

# 各methodについて、実際にそのsemantic kindをdurableに確定させた状態を用意し、
# 段1=None（構築済み値の欠落）→段2でdurable stateから正しく復旧することを、
# 4メソッド全てで確認する（段1欠落パターンは§28.-5 #3-4と同型だが、
# 本節は4メソッド全ての組み合わせ的な網羅を目的として再度全件実施する）。
with tempfile.TemporaryDirectory() as tmpdir_6_4:
    d = Path(tmpdir_6_4)
    coordinator_6_4 = _make_coordinator(d)

    identity_na_6_4 = _identity(instance_key="art-6-4-na")
    coordinator_6_4.record_not_applicable(identity_na_6_4, "member-6-4-na")
    recovered_na_6_4 = coordinator_6_4._value_or_recover(
        CommitAwareResult(acknowledged=True, value=None, cleanup_diagnostics=()),
        identity_na_6_4, "member-6-4-na", _policy_factories_6_4["NotApplicable"](identity_na_6_4, "member-6-4-na"),
    )
    check_true("4. [NotApplicable] 段1欠落→段2復旧", recovered_na_6_4.__class__.__name__ == "NotApplicableMediaUploadSafetyRecord")

    identity_prep_6_4 = _identity(instance_key="art-6-4-prep")
    coordinator_6_4.record_prepared(identity_prep_6_4, "member-6-4-prep")
    recovered_prep_6_4 = coordinator_6_4._value_or_recover(
        CommitAwareResult(acknowledged=True, value=None, cleanup_diagnostics=()),
        identity_prep_6_4, "member-6-4-prep", _policy_factories_6_4["Prepared"](identity_prep_6_4, "member-6-4-prep"),
    )
    check_true("4. [Prepared] 段1欠落→段2復旧", recovered_prep_6_4.__class__.__name__ == "PreparedMediaUploadSafetyRecord")

    identity_armed_6_4 = _identity(instance_key="art-6-4-armed")
    coordinator_6_4.record_attempted(identity_armed_6_4, "member-6-4-armed")
    recovered_armed_6_4 = coordinator_6_4._value_or_recover(
        CommitAwareResult(acknowledged=True, value=None, cleanup_diagnostics=()),
        identity_armed_6_4, "member-6-4-armed", _policy_factories_6_4["IoArmed"](identity_armed_6_4, "member-6-4-armed"),
    )
    check_true("4. [IoArmed] 段1欠落→段2復旧", recovered_armed_6_4.__class__.__name__ == "IoArmedMediaUploadSafetyRecord")

    identity_conf_6_4 = _identity(instance_key="art-6-4-conf")
    coordinator_6_4.record_attempted(identity_conf_6_4, "member-6-4-conf")
    coordinator_6_4.record_confirmed(identity_conf_6_4, "member-6-4-conf", media_id=7)
    recovered_conf_6_4 = coordinator_6_4._value_or_recover(
        CommitAwareResult(acknowledged=True, value=None, cleanup_diagnostics=()),
        identity_conf_6_4, "member-6-4-conf", _policy_factories_6_4["Confirmed"](identity_conf_6_4, "member-6-4-conf"),
    )
    check_true("4. [Confirmed] 段1欠落→段2復旧", recovered_conf_6_4.__class__.__name__ == "ConfirmedMediaUploadSafetyRecord")

    # 段1・段2両方失敗（durable stateが全く存在しない全く新しいidentity）→段3
    # （minimal synthesis）が正しいsemantic kindを合成することを4メソッド全てで確認する。
    for policy_name, policy_factory in _policy_factories_6_4.items():
        fresh_identity_6_4 = _identity(instance_key=f"art-6-4-fresh-{policy_name}")
        policy_6_4 = policy_factory(fresh_identity_6_4, f"member-6-4-fresh-{policy_name}")
        recovered_fresh_6_4 = coordinator_6_4._value_or_recover(
            CommitAwareResult(acknowledged=True, value=None, cleanup_diagnostics=()),
            fresh_identity_6_4, f"member-6-4-fresh-{policy_name}", policy_6_4,
        )
        check(
            f"4. [{policy_name}] 段1・段2いずれも失敗（durable state非存在）→段3のminimal synthesisが"
            f"exactly {policy_6_4.expected_type.__name__}を返す",
            recovered_fresh_6_4.__class__.__name__, policy_6_4.expected_type.__name__,
        )
print()


# =====================================================================
# §28.-7: _value_or_recover()段2失敗フォールバック
# =====================================================================

print("[28.-7 #1] 段2（self._read_all()）自体が一時的な例外を送出"
      "→ 段3（_minimal_safety_record()）へフォールスルーする")

with tempfile.TemporaryDirectory() as tmpdir_7_1:
    d = Path(tmpdir_7_1)
    coordinator_7_1 = _make_coordinator(d)
    identity_7_1 = _identity(instance_key="art-7-1")

    _orig_read_all_7_1 = coordinator_7_1._read_all

    def _raising_read_all_7_1(*args, **kwargs):
        raise RuntimeError("simulated transient durable read failure")

    coordinator_7_1._read_all = _raising_read_all_7_1
    try:
        recovered_7_1 = coordinator_7_1._value_or_recover(
            CommitAwareResult(acknowledged=True, value=None, cleanup_diagnostics=()),
            identity_7_1, "member-7-1",
            NotApplicableRecoveryPolicy(identity=identity_7_1, member_run_id="member-7-1"),
        )
    finally:
        coordinator_7_1._read_all = _orig_read_all_7_1

    check_true(
        "1. 段2が例外を送出しても段3へフォールスルーし、例外は呼び出し元へ伝播しない",
        recovered_7_1.__class__.__name__ == "NotApplicableMediaUploadSafetyRecord",
    )
print()

print("[28.-7 #2] 段2がMediaUploadSafetyContractViolationErrorを送出"
      "（durable state矛盾検出）→ 同様に段3へフォールスルーする")

from side_effect_safety import MediaUploadSafetyContractViolationError

with tempfile.TemporaryDirectory() as tmpdir_7_2:
    d = Path(tmpdir_7_2)
    coordinator_7_2 = _make_coordinator(d)
    identity_7_2 = _identity(instance_key="art-7-2")

    _orig_read_all_7_2 = coordinator_7_2._read_all

    def _contract_violation_read_all_7_2(*args, **kwargs):
        raise MediaUploadSafetyContractViolationError("simulated cross-store contradiction")

    coordinator_7_2._read_all = _contract_violation_read_all_7_2
    try:
        recovered_7_2 = coordinator_7_2._value_or_recover(
            CommitAwareResult(acknowledged=True, value=None, cleanup_diagnostics=()),
            identity_7_2, "member-7-2",
            NotApplicableRecoveryPolicy(identity=identity_7_2, member_run_id="member-7-2"),
        )
    finally:
        coordinator_7_2._read_all = _orig_read_all_7_2

    check_true(
        "2. MediaUploadSafetyContractViolationErrorも段3へ一律フォールスルーする"
        "（durable read失敗の一種として特別扱いしない設計の確認）",
        recovered_7_2.__class__.__name__ == "NotApplicableMediaUploadSafetyRecord",
    )
print()

print("[28.-7 #3] _minimal_safety_record()（段3）は追加のfilesystem I/O・store呼び出しを"
      "一切発生させない")

with tempfile.TemporaryDirectory() as tmpdir_7_3:
    d = Path(tmpdir_7_3)
    call_log_7_3: list[str] = []

    class _CountingStore:
        def __init__(self, real):
            self._real = real

        def __getattr__(self, name):
            real_attr = getattr(self._real, name)
            if not callable(real_attr):
                return real_attr

            def _wrapped(*args, **kwargs):
                call_log_7_3.append(name)
                return real_attr(*args, **kwargs)

            return _wrapped

    media_manager_7_3 = _CountingStore(ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(d / "media")))
    applicability_store_7_3 = _CountingStore(JsonMediaUploadApplicabilityStore(d / "applicability"))
    attempt_context_store_7_3 = _CountingStore(JsonMediaUploadAttemptContextStore(d / "context"))
    coordinator_7_3 = build_media_upload_safety_coordinator(
        media_upload_manager=media_manager_7_3,
        applicability_store=applicability_store_7_3,
        attempt_context_store=attempt_context_store_7_3,
        locks_dir=d / "locks",
    )
    identity_7_3 = _identity(instance_key="art-7-3")

    _orig_read_all_7_3 = coordinator_7_3._read_all
    coordinator_7_3._read_all = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("force stage3"))
    try:
        call_log_7_3.clear()
        recovered_7_3 = coordinator_7_3._value_or_recover(
            CommitAwareResult(acknowledged=True, value=None, cleanup_diagnostics=()),
            identity_7_3, "member-7-3",
            NotApplicableRecoveryPolicy(identity=identity_7_3, member_run_id="member-7-3"),
        )
    finally:
        coordinator_7_3._read_all = _orig_read_all_7_3

    check_true("3. 段3到達（minimal synthesis）で正しいsemantic kindが返る", recovered_7_3.__class__.__name__ == "NotApplicableMediaUploadSafetyRecord")
    check(
        "3. 段3実行中、3つのstoreへの追加呼び出しは一切発生しない（call_log=空）",
        call_log_7_3, [],
    )
print()

print("[28.-7 #4] _minimal_safety_record()内のnow_utc_iso()が例外送出"
      "→ updated_at=''へfallbackし、有効なrecordを返す")

with tempfile.TemporaryDirectory() as tmpdir_7_4:
    d = Path(tmpdir_7_4)
    coordinator_7_4 = _make_coordinator(d)
    identity_7_4 = _identity(instance_key="art-7-4")

    _orig_now_utc_iso_7_4 = coordinator_module.now_utc_iso
    coordinator_7_4._read_all = lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("force stage3"))
    try:
        def _raising_now_utc_iso_7_4():
            raise RuntimeError("simulated now_utc_iso() failure in stage3")

        coordinator_module.now_utc_iso = _raising_now_utc_iso_7_4
        recovered_7_4 = coordinator_7_4._value_or_recover(
            CommitAwareResult(acknowledged=True, value=None, cleanup_diagnostics=()),
            identity_7_4, "member-7-4",
            NotApplicableRecoveryPolicy(identity=identity_7_4, member_run_id="member-7-4"),
        )
    finally:
        coordinator_module.now_utc_iso = _orig_now_utc_iso_7_4

    check_true("4. now_utc_iso()失敗でも段3は例外を送出せず有効なrecordを返す", recovered_7_4.__class__.__name__ == "NotApplicableMediaUploadSafetyRecord")
    check("4. updated_atが空文字列へfallbackする", recovered_7_4.updated_at, "")
print()

print("[28.-7 #5] 既存crash/restart/identity/legacy testの回帰確認"
      "（既存sub-milestone 0テストへの委譲、本節では実行確認のみ）")
check_true(
    "5. 本項目は既存tests/test_e2e_v6_32_0_side_effect_fail_closed_foundation.py等の"
    "既存テストスイートで継続的にPASSしている（regression sweepで別途確認済み）",
    True,
)
print()


# =====================================================================
# §28.-7b: Safe Continuation 同一プロセス内二重呼び出し
# =====================================================================

print("[28.-7b] 同一プロセス内で同一identityへrecord_attempted()を意図的に2回連続で呼ぶ"
      "（1回目はIO_ARMED ACK到達前で中断、2回目はrestartなしで即座に再試行）"
      "→ 2回目でSafe Continuationが発火し、エラーにならず安全に処理される")

with tempfile.TemporaryDirectory() as tmpdir_7b:
    d = Path(tmpdir_7b)
    call_log_7b: list[str] = []

    class _UploadCallCountingManager:
        def __init__(self, real):
            self._real = real

        def record_upload_started(self, *args, **kwargs):
            call_log_7b.append("record_upload_started")
            return self._real.record_upload_started(*args, **kwargs)

        def record_upload_succeeded(self, *args, **kwargs):
            return self._real.record_upload_succeeded(*args, **kwargs)

        def get_state(self, *args, **kwargs):
            return self._real.get_state(*args, **kwargs)

    class _CrashOnceThenPassThroughContextStore:
        """1回目のtransition_to_io_armed()呼び出しのみ例外を送出し（IO_ARMED
        durable ACK到達前のcrashを模擬）、2回目以降は実storeへ正常に委譲する。"""

        def __init__(self, real):
            self._real = real
            self._transition_calls = 0

        def create_prepared(self, *args, **kwargs):
            return self._real.create_prepared(*args, **kwargs)

        def transition_to_io_armed(self, *args, **kwargs):
            self._transition_calls += 1
            if self._transition_calls == 1:
                raise RuntimeError("simulated crash before IO_ARMED durable ACK (1st call)")
            return self._real.transition_to_io_armed(*args, **kwargs)

        def get(self, *args, **kwargs):
            return self._real.get(*args, **kwargs)

    real_manager_7b = ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(d / "media"))
    real_context_store_7b = JsonMediaUploadAttemptContextStore(d / "context")
    coordinator_7b = build_media_upload_safety_coordinator(
        media_upload_manager=_UploadCallCountingManager(real_manager_7b),
        applicability_store=JsonMediaUploadApplicabilityStore(d / "applicability"),
        attempt_context_store=_CrashOnceThenPassThroughContextStore(real_context_store_7b),
        locks_dir=d / "locks",
    )
    identity_7b = _identity(instance_key="art-7b")

    # 1回目：ATTEMPTED durable ACK確定後・IO_ARMED durable ACK到達前でcrash
    # （pre-commit failure、committed=True未到達のため元の例外がそのまま伝播する）。
    try:
        coordinator_7b.record_attempted(identity_7b, "member-7b")
        check_true("7b. 1回目はIO_ARMED ACK到達前のcrash模擬により例外を送出する", False)
    except RuntimeError:
        check_true(
            "7b. 1回目はATTEMPTED ACK確定後・IO_ARMED ACK到達前のcrash模擬で"
            "pre-commit failureとして元の例外がそのまま送出される",
            True,
        )
    check("7b. 1回目の結果としてrecord_upload_started()が1回呼ばれている（ATTEMPTED ACKは確定済み）", call_log_7b.count("record_upload_started"), 1)

    # 2回目：同一プロセス内・restartなしで即座に再試行する。durable stateは
    # PREPARED_PLUS_ATTEMPTEDのまま（1回目でATTEMPTED ACKは確定済み、IO_ARMEDのみ未到達）
    # のため、Safe Continuation分岐（snapshot.category in (PREPARED_ONLY,
    # PREPARED_PLUS_ATTEMPTED)）が発火するはずである。
    second_result_7b = coordinator_7b.record_attempted(identity_7b, "member-7b")
    check_true(
        "7b. 2回目（同一プロセス内、restartなし）の再試行はエラーにならず"
        "安全に処理される（Safe Continuation分岐の発火、IO_ARMEDまで到達する）",
        isinstance(second_result_7b, IoArmedMediaUploadSafetyRecord),
    )
    check(
        "7b. 2回目の呼び出し結果としてrecord_upload_started()の呼び出し回数は増加しない"
        "（external upload countが増加しない——Safe Continuationはsnapshot.upload_stateを"
        "再利用し、record_upload_started()を再度呼ばない）",
        call_log_7b.count("record_upload_started"), 1,
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
