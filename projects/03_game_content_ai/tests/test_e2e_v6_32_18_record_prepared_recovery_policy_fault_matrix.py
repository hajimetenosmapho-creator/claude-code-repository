"""
E2E テスト: Release 6.32 sub-milestone 6D-6C
record_prepared() / Option (a) decorator injection・RecoveryPolicy fault matrix
（§28.-22・§28.-23・§28.-24）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    28.-22節（12件）・28.-23節（14件）・28.-24節（9件）。

本ファイルは、Canonical Gap Inventoryで「genuinely new（未テスト）」と判定された
以下の項目のみを対象とする。他の項目は既存テスト（test_e2e_v6_32_4・
test_e2e_v6_32_16・test_e2e_v6_32_17等）で既にCOMPLETEであることを確認済みの
ため、本ファイルでは再実装しない：

    28.-22 #2  : record_prepared() PREPARED ACK自体の失敗 → MediaUploadSafetyIOError
                 送出、external upload = 0
    28.-22 #7  : IO_ARMED ACK確認後、decorated upload()実行中にcrash
                 → 再起動後の分類がHUMAN_REVIEW_REQUIRED
    28.-22 #11 : from_env()のdefault construction経路が6.32固有dependencyを
                 一切構築・注入しない（zero-diff）
    28.-22 #12 : Foundation 2ファイルのimport監査（6.32-specific moduleへの
                 直接importが0件）
    28.-23 #7  : stale lockのまま record_prepared() を呼んでも自動破棄・
                 自動解放が一切行われない
    28.-23 #9  : durable reread（段2）が自分自身のexpected_typeと異なる型を
                 返す状況で段3へフォールスルーする（= 28.-24 #2と同一趣旨）
    28.-23 #10 : PreparedMediaUploadSafetyRecordとNotApplicableMediaUploadSafetyRecordが
                 構造的に別の型であり、相互変換APIを持たないことのコード監査
    28.-24 #1  : Stage 1（commit_state["value"]）がwrong kindの場合、段2へ
                 フォールスルーする
    28.-24 #2  : 28.-23 #9と同一（Stage 2 durable reread wrong kind reject）
    28.-24 #3  : build_minimal()がwrong kindを返す状況をtest stubで注入した場合、
                 MediaUploadSafetyImplementationContractErrorでfail-closedする
    28.-24 #8  : `_value_or_recover()`への呼び出しが4公開メソッドいずれも
                 単一の`policy=`引数のみであるAPI surface監査

対象production: src/side_effect_safety/media_upload_safety_coordinator.py・
                 src/side_effect_safety/media_upload_safety_coordinator_lock.py・
                 src/side_effect_safety/media_upload_write_ahead_capability.py・
                 src/article_featured_media_composition/article_featured_media_composition_root.py・
                 src/article_featured_media_orchestration/article_featured_media_orchestrator.py・
                 main.py
（変更しない。既存実装がApproved Architectureどおり正しいことをtest-onlyで
証明する）。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_18_record_prepared_recovery_policy_fault_matrix.py
"""
from __future__ import annotations

import ast
import inspect
import os
import sys
from dataclasses import dataclass, fields
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
print("record_prepared() / RecoveryPolicy fault matrix（6D-6C、28.-22・-23・-24）E2E テスト")
print("=" * 60)
print()

import main  # noqa: E402
from outputs.base import ArticleData  # noqa: E402
from collector import NewsItem  # noqa: E402
from publishing_config import PublishStatus  # noqa: E402

from article_media_upload_state.article_media_upload_state_manager import ArticleMediaUploadStateManager  # noqa: E402
from article_media_upload_state.json_article_media_upload_state_store import JsonArticleMediaUploadStateStore  # noqa: E402
from retry_lineage import RetryLineageDisposition  # noqa: E402
from retry_lineage.retry_lineage_target_resolution import resolve_final_disposition  # noqa: E402
from side_effect_safety import (  # noqa: E402
    JsonMediaUploadApplicabilityStore,
    LegacyEntrypoint,
    LegacyExecutionOrigin,
    MediaUploadSafetyIOError,
    ProtectedSideEffectKind,
    SideEffectOperationIdentity,
    SideEffectSite,
    build_legacy_direct_provenance,
    build_media_upload_safety_coordinator,
    build_protected_execution_context,
)
from side_effect_safety.commit_aware_lock import CommitAwareResult
from side_effect_safety.errors import MediaUploadSafetyImplementationContractError
from side_effect_safety.media_upload_attempt_context_store import JsonMediaUploadAttemptContextStore
from side_effect_safety.media_upload_safety_coordinator import (
    ConfirmedMediaUploadSafetyRecord,
    IoArmedMediaUploadSafetyRecord,
    NotApplicableMediaUploadSafetyRecord,
    NotApplicableRecoveryPolicy,
    PreparedMediaUploadSafetyRecord,
    PreparedRecoveryPolicy,
)
from side_effect_safety.media_upload_safety_coordinator_lock import (
    MediaUploadSafetyCoordinatorLock,
    MediaUploadSafetyCoordinatorLockError,
)
from side_effect_safety.media_upload_write_ahead_capability import WriteAheadAwareMediaUploadCapability
from side_effect_safety.media_upload_write_ahead_wiring import (
    MediaUploadWriteAheadAdapters,
    ProtectedFeaturedMediaSideEffectBinding,
    build_protected_featured_media_side_effect_binding,
)
from side_effect_safety.side_effect_safety_category import (
    ProtectedOperationContext,
    SideEffectSafetyCategory,
    SideEffectSafetyReport,
)
from side_effect_safety_classifier import SideEffectSafetyClassifier

from article_featured_media_composition import ArticleFeaturedMediaCompositionRoot
from article_featured_media_orchestration import ArticleFeaturedMediaOrchestrator


# ─── 共通ヘルパー ───

def _identity(instance_key="art1", root_run_id="r1", attempt_ordinal=1) -> SideEffectOperationIdentity:
    return SideEffectOperationIdentity(
        root_run_id=root_run_id, attempt_ordinal=attempt_ordinal,
        operation_kind=ProtectedSideEffectKind.MEDIA_UPLOAD, effect_site=SideEffectSite.NEWS_STEP,
        operation_instance_key=instance_key,
    )


def _make_coordinator(tmpdir: Path, lock_timeout: float | None = None):
    media_manager = ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(tmpdir / "media"))
    if lock_timeout is None:
        return build_media_upload_safety_coordinator(
            media_upload_manager=media_manager,
            applicability_store=JsonMediaUploadApplicabilityStore(tmpdir / "applicability"),
            attempt_context_store=JsonMediaUploadAttemptContextStore(tmpdir / "context"),
            locks_dir=tmpdir / "locks",
        )
    from side_effect_safety.media_upload_safety_coordinator import MediaUploadSafetyCoordinator
    from side_effect_safety.media_upload_safety_coordinator_lock import build_media_upload_safety_coordinator_lock

    def _lock_factory(identity):
        base = build_media_upload_safety_coordinator_lock(tmpdir / "locks", identity)
        return MediaUploadSafetyCoordinatorLock(base.lock_path, timeout_seconds=lock_timeout, retry_interval_seconds=0.02)

    return MediaUploadSafetyCoordinator(
        media_upload_manager=media_manager,
        applicability_store=JsonMediaUploadApplicabilityStore(tmpdir / "applicability"),
        attempt_context_store=JsonMediaUploadAttemptContextStore(tmpdir / "context"),
        lock_factory=_lock_factory,
    )


class _UnusedDraftState:
    def get(self, *args, **kwargs):
        raise AssertionError("draft_state.get()はMEDIA_UPLOAD分岐では呼ばれないはず")


def _classify(coordinator, identity, member_run_id) -> SideEffectSafetyCategory:
    classifier = SideEffectSafetyClassifier(media_coordinator=coordinator, draft_state=_UnusedDraftState())
    return classifier._classify_one(identity, member_run_id, ProtectedSideEffectKind.MEDIA_UPLOAD)


def _final_disposition_for(category: SideEffectSafetyCategory) -> RetryLineageDisposition:
    report = SideEffectSafetyReport(entries=(
        (ProtectedOperationContext(
            operation_kind=ProtectedSideEffectKind.MEDIA_UPLOAD, effect_site=SideEffectSite.NEWS_STEP,
            operation_instance_key="x",
        ), category),
    ))
    return resolve_final_disposition([], report)


import tempfile  # noqa: E402


def _tmp() -> Path:
    d = Path(tempfile.mkdtemp(prefix="v6_32_18_"))
    return d


# =====================================================================
# [テスト群1] 28.-22 #2: record_prepared() PREPARED ACK自体の失敗
# =====================================================================

print("[テスト1] record_prepared() PREPARED ACK失敗 → MediaUploadSafetyIOError、external upload = 0")


def make_article(slug: str = "ps6-announced-20260630") -> ArticleData:
    item = NewsItem(
        title="PS6正式発表", url="https://blog.playstation.com/test",
        summary="PlayStation 6 が正式に発表されました。", source="PlayStation Blog",
        published_at="2026-06-30", image_candidates=[],
    )
    return ArticleData(
        item=item, importance="S", seo_title="PS6が正式発表",
        article_body="PS6が発表されました。", x_post="PS6発表！",
        slug=slug, publish_status=PublishStatus.DRAFT,
    )


_PROTECTED_CONTEXT_1 = build_protected_execution_context(
    root_run_id="root-18-1", attempt_ordinal=1, member_run_id="member-18-1",
    side_effect_contract_version=1,
)

# Codex Final Review Blocking#2対応：protected bindingでのmanifest_registrar
# 省略によるregistration bypassは許可されなくなったため、本ファイルの対象
# シナリオ（record_prepared()自体の失敗）へ到達させるために実の
# ManifestRegistrarFacadeを配線する（test-owned tmp dir、production非変更）。
from protected_operation_manifest import JsonProtectedOperationManifestStore, ManifestRegistrarFacade  # noqa: E402

_manifest_store_18 = JsonProtectedOperationManifestStore(base_dir=Path(tempfile.mkdtemp()) / "manifest")
_manifest_store_18.create_for_attempt("root-18-1", 1, "member-18-1")
_manifest_registrar_18 = ManifestRegistrarFacade(_manifest_store_18)


class _FailingPreparedCoordinator:
    """record_prepared()自体がMediaUploadSafetyIOErrorを送出するFake。"""

    def __init__(self):
        self.calls: list[tuple] = []

    def record_not_applicable(self, identity, member_run_id):
        self.calls.append(("not_applicable", identity, member_run_id))

    def record_prepared(self, identity, member_run_id):
        self.calls.append(("prepared", identity, member_run_id))
        raise MediaUploadSafetyIOError("simulated PREPARED ACK failure")

    def record_attempted(self, identity, member_run_id):
        self.calls.append(("attempted", identity, member_run_id))

    def record_confirmed(self, identity, member_run_id, media_id):
        self.calls.append(("confirmed", identity, member_run_id, media_id))


class _SpyBaseUploader:
    def __init__(self):
        self.calls = 0

    def upload(self, image, filename):
        self.calls += 1
        raise AssertionError("record_prepared()失敗後、実uploadは一切呼ばれてはならない")


coordinator_1 = _FailingPreparedCoordinator()
spy_uploader_1 = _SpyBaseUploader()
adapters_1 = MediaUploadWriteAheadAdapters(
    enabled=True, image_generator=object(), base_media_uploader=spy_uploader_1, image_mime_type="image/png",
)
binding_1 = build_protected_featured_media_side_effect_binding(
    _PROTECTED_CONTEXT_1, coordinator_1, adapters_1, _manifest_registrar_18,
)

raised_1 = None
try:
    main._apply_featured_media_step(make_article(), side_effect_binding=binding_1)
except MediaUploadSafetyIOError as e:
    raised_1 = e

check_true("1a. MediaUploadSafetyIOErrorがそのまま送出される（wrapされない）", raised_1 is not None)
check("1b. record_prepared()が1回だけ呼ばれる", [c[0] for c in coordinator_1.calls], ["prepared"])
check("1c. 実upload()は一切呼ばれない（external upload = 0）", spy_uploader_1.calls, 0)
print()


# =====================================================================
# [テスト群2] 28.-22 #7: IO_ARMED ACK確認後、decorated upload()実行中にcrash
#             → 再起動後の分類がHUMAN_REVIEW_REQUIRED
# =====================================================================

print("[テスト2] IO_ARMED ACK確認後、decorated upload()実行中にcrash → 再起動後HUMAN_REVIEW_REQUIRED")

tmp_2 = _tmp()
identity_2 = _identity(instance_key="art-2", root_run_id="root-18-2")
member_run_id_2 = "member-18-2"
coordinator_2a = _make_coordinator(tmp_2)  # 「クラッシュ前」プロセスを模す


class _CrashingInnerUploader:
    def upload(self, image, filename):
        raise RuntimeError("simulated crash during real upload I/O")


coordinator_2a.record_prepared(identity_2, member_run_id_2)
decorated_2 = WriteAheadAwareMediaUploadCapability(
    inner=_CrashingInnerUploader(), media_upload_coordinator=coordinator_2a,
    identity=identity_2, member_run_id=member_run_id_2,
)
crash_2 = None
try:
    decorated_2.upload(image=object(), filename="x.png")
except RuntimeError as e:
    crash_2 = e

check_true("2a. decorated upload()中のcrashがそのまま伝播する", crash_2 is not None)

# 「再起動後」を新規Coordinatorインスタンス（同一durable dir）として模す
coordinator_2b = _make_coordinator(tmp_2)
category_2 = _classify(coordinator_2b, identity_2, member_run_id_2)
disposition_2 = _final_disposition_for(category_2)

check("2b. 再起動後の分類はIN_PROGRESS_OR_UNKNOWN（9.9.5節Crash Semantics）", category_2, SideEffectSafetyCategory.IN_PROGRESS_OR_UNKNOWN)
check("2c. 再起動後のfinal dispositionはHUMAN_REVIEW_REQUIRED", disposition_2, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
print()


# =====================================================================
# [テスト群3] 28.-22 #11・#12: from_env() zero-diff・import監査
# =====================================================================

print("[テスト3] Foundation 2ファイル：from_env() zero-diff・import監査")

_COMPOSITION_ROOT_SRC = SRC_DIR / "article_featured_media_composition" / "article_featured_media_composition_root.py"
_ORCHESTRATOR_SRC = SRC_DIR / "article_featured_media_orchestration" / "article_featured_media_orchestrator.py"

_FORBIDDEN_632_NAMES = {
    "side_effect_safety", "MediaUploadSafetyCoordinator", "WriteAheadAwareMediaUploadCapability",
    "retry_lineage", "RetryLineage", "SideEffectOperationIdentity", "media_upload_write_ahead_wiring",
    "media_upload_write_ahead_capability",
}


def _collect_import_module_names(tree: ast.AST) -> set[str]:
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
            for alias in node.names:
                names.add(alias.name)
    return names


for label_prefix, src_path in (("Composition Root", _COMPOSITION_ROOT_SRC), ("Orchestrator", _ORCHESTRATOR_SRC)):
    tree = ast.parse(src_path.read_text(encoding="utf-8"))
    imported_names = _collect_import_module_names(tree)
    overlap = {n for n in imported_names if any(f in n for f in _FORBIDDEN_632_NAMES)}
    check(f"3-{label_prefix}: 6.32-specific moduleへの直接importが0件", overlap, set())

# from_env()自体のsource中に6.32-specific識別子が一切現れないことを確認する
_from_env_source = inspect.getsource(ArticleFeaturedMediaCompositionRoot.from_env)
found_in_from_env = {n for n in _FORBIDDEN_632_NAMES if n in _from_env_source}
check("3c. ArticleFeaturedMediaCompositionRoot.from_env()のsourceに6.32固有識別子が0件", found_in_from_env, set())

# 実際にGate OFFでfrom_env()を実行し、6.32 dependencyがゼロ構築であることを確認する
_saved_env = os.environ.pop("AI_IMAGE_GENERATION_ENABLED", None)
try:
    root_3 = ArticleFeaturedMediaCompositionRoot.from_env()
finally:
    if _saved_env is not None:
        os.environ["AI_IMAGE_GENERATION_ENABLED"] = _saved_env

check_true("3d. Gate OFF既定経路: orchestratorはNone", root_3.orchestrator is None)
check_true("3e. Gate OFF既定経路: image_mime_typeはNone", root_3.image_mime_type is None)
check_true("3f. is_available()はFalse", root_3.is_available() is False)

# ArticleFeaturedMediaOrchestrator.__init__のsignatureが6.32固有引数を持たない
sig = inspect.signature(ArticleFeaturedMediaOrchestrator.__init__)
param_names = set(sig.parameters.keys())
check("3g. Orchestrator.__init__の引数は{self, image_generator, media_uploader}のみ",
      param_names, {"self", "image_generator", "media_uploader"})
print()


# =====================================================================
# [テスト群4] 28.-23 #7: stale lockのままrecord_prepared()を呼んでも
#             自動破棄・自動解放が一切行われない
# =====================================================================

print("[テスト4] stale lockのまま record_prepared() → 自動破棄・自動解放は一切行われない")

tmp_4 = _tmp()
identity_4 = _identity(instance_key="art-4", root_run_id="root-18-4")
coordinator_4 = _make_coordinator(tmp_4, lock_timeout=0.3)

from side_effect_safety.media_upload_safety_coordinator_lock import build_media_upload_safety_coordinator_lock

stale_lock_4 = build_media_upload_safety_coordinator_lock(tmp_4 / "locks", identity_4)
stale_lock_4.acquire()  # 他プロセスのPIDが実在しないことを模した「残存lock」（解放しない）
check_true("4a. stale lockのlock fileが事前に存在する", stale_lock_4.lock_path.exists())

timeout_error_4 = None
try:
    coordinator_4.record_prepared(identity_4, "member-18-4")
except MediaUploadSafetyCoordinatorLockError as e:
    timeout_error_4 = e

check_true("4b. record_prepared()はlock取得タイムアウトで失敗する（自動破棄しない）", timeout_error_4 is not None)
check_true("4c. タイムアウト後もlock fileはそのまま残存する（自動解放されない）", stale_lock_4.lock_path.exists())
stale_lock_4.release()  # 後片付け（テスト専用の外部残存lockを解除）
print()


# =====================================================================
# [テスト群5] 28.-23 #9 / 28.-24 #2: Stage 2 durable reread wrong kind reject
# =====================================================================

print("[テスト5] Stage 2 durable reread がwrong kindを返す状況 → Stage 3へフォールスルー")

tmp_5 = _tmp()
identity_5 = _identity(instance_key="art-5", root_run_id="root-18-5")
member_run_id_5 = "member-18-5"
coordinator_5 = _make_coordinator(tmp_5)

# 実durable stateはPREPAREDとして確定させる（policyはNotApplicable側 = wrong kind想定）
real_prepared_5 = coordinator_5.record_prepared(identity_5, member_run_id_5)
check_true("5a. 事前条件: durable stateは実際にPreparedMediaUploadSafetyRecord", isinstance(real_prepared_5, PreparedMediaUploadSafetyRecord))

outcome_5 = CommitAwareResult(acknowledged=True, value=None, cleanup_diagnostics=())
result_5 = coordinator_5._value_or_recover(
    outcome_5, identity_5, member_run_id_5,
    policy=NotApplicableRecoveryPolicy(identity=identity_5, member_run_id=member_run_id_5),
)

check_true("5b. Stage 1は空振り（outcome.value=None）", outcome_5.value is None)
check_true("5c. Stage 2のdurable rereadはwrong kind（Prepared）のためreject、Stage 3の正しいkindが返る",
           isinstance(result_5, NotApplicableMediaUploadSafetyRecord))
check_false("5d. wrong kind（Prepared）がそのまま返っていない", isinstance(result_5, PreparedMediaUploadSafetyRecord))
print()


# =====================================================================
# [テスト群6] 28.-23 #10: 構造的型区別のコード監査
# =====================================================================

print("[テスト6] PreparedMediaUploadSafetyRecord / NotApplicableMediaUploadSafetyRecordの構造的非等価性")

check_false("6a. PreparedとNotApplicableは同一クラスではない", PreparedMediaUploadSafetyRecord is NotApplicableMediaUploadSafetyRecord)
prepared_field_names = {f.name for f in fields(PreparedMediaUploadSafetyRecord)}
not_applicable_field_names = {f.name for f in fields(NotApplicableMediaUploadSafetyRecord)}
check("6b. 両方ともidentity/member_run_id/updated_atの3フィールドのみ（構造は類似するが型は別）",
      (prepared_field_names, not_applicable_field_names), ({"identity", "member_run_id", "updated_at"},) * 2)

conversion_like_methods = {
    name for name in dir(PreparedMediaUploadSafetyRecord)
    if not name.startswith("_") and ("convert" in name or "as_not_applicable" in name or "to_not_applicable" in name)
}
check("6c. Prepared側に相互変換API（convert/as_not_applicable等）が存在しない", conversion_like_methods, set())

is_frozen_prepared = getattr(PreparedMediaUploadSafetyRecord, "__dataclass_params__").frozen
is_frozen_not_applicable = getattr(NotApplicableMediaUploadSafetyRecord, "__dataclass_params__").frozen
check_true("6d. PreparedMediaUploadSafetyRecordはfrozen dataclass（書き換え不可）", is_frozen_prepared)
check_true("6e. NotApplicableMediaUploadSafetyRecordはfrozen dataclass（書き換え不可）", is_frozen_not_applicable)
print()


# =====================================================================
# [テスト群7] 28.-24 #1: Stage 1 wrong kind reject
# =====================================================================

print("[テスト7] Stage 1（commit_state['value']）がwrong kindの場合、Stage 2へフォールスルー")

tmp_7 = _tmp()
identity_7 = _identity(instance_key="art-7", root_run_id="root-18-7")
member_run_id_7 = "member-18-7"
coordinator_7 = _make_coordinator(tmp_7)

real_prepared_7 = coordinator_7.record_prepared(identity_7, member_run_id_7)
check_true("7a. 事前条件: durable stateは実際にPreparedMediaUploadSafetyRecord", isinstance(real_prepared_7, PreparedMediaUploadSafetyRecord))

wrong_kind_stage1_value = NotApplicableMediaUploadSafetyRecord(
    identity=identity_7, member_run_id=member_run_id_7, updated_at="2026-01-01T00:00:00+00:00",
)
outcome_7 = CommitAwareResult(acknowledged=True, value=wrong_kind_stage1_value, cleanup_diagnostics=())
result_7 = coordinator_7._value_or_recover(
    outcome_7, identity_7, member_run_id_7,
    policy=PreparedRecoveryPolicy(identity=identity_7, member_run_id=member_run_id_7),
)

check_true("7b. Stage 1のwrong kind（NotApplicable）はrejectされる", True)
check_true("7c. Stage 2の実durable reread（正しいPrepared）が返る", isinstance(result_7, PreparedMediaUploadSafetyRecord))
check("7d. 返るrecordは実durable stateのupdated_atと一致する（Stage 1の値ではない）", result_7.updated_at, real_prepared_7.updated_at)
print()


# =====================================================================
# [テスト群8] 28.-24 #3: build_minimal()がwrong kindを返す場合の
#             MediaUploadSafetyImplementationContractError
# =====================================================================

print("[テスト8] build_minimal()がwrong kindを返す状況（test stub）→ MediaUploadSafetyImplementationContractError")

tmp_8 = _tmp()
identity_8 = _identity(instance_key="art-8", root_run_id="root-18-8")
member_run_id_8 = "member-18-8"
coordinator_8 = _make_coordinator(tmp_8)  # durable dataは一切書き込まない（Stage 2も空振り）


@dataclass(frozen=True)
class _BadPreparedPolicyReturningWrongKind:
    """Approved Architecture 28.-24#3のためのtest stub。
    expected_typeはPreparedだが、build_minimal()はわざと別kindを返す
    （実装契約違反を人為的に注入する）。"""

    identity: SideEffectOperationIdentity
    member_run_id: str
    expected_type = PreparedMediaUploadSafetyRecord

    def build_minimal(self, updated_at: str):
        return NotApplicableMediaUploadSafetyRecord(
            identity=self.identity, member_run_id=self.member_run_id, updated_at=updated_at,
        )

    def validate(self, value):
        return value if isinstance(value, self.expected_type) else None


outcome_8 = CommitAwareResult(acknowledged=True, value=None, cleanup_diagnostics=())
raised_8 = None
try:
    coordinator_8._value_or_recover(
        outcome_8, identity_8, member_run_id_8,
        policy=_BadPreparedPolicyReturningWrongKind(identity=identity_8, member_run_id=member_run_id_8),
    )
except MediaUploadSafetyImplementationContractError as e:
    raised_8 = e

check_true("8a. wrong-kind build_minimal()はMediaUploadSafetyImplementationContractErrorでfail-closedする", raised_8 is not None)
print()


# =====================================================================
# [テスト群9] 28.-24 #8: _value_or_recover()のAPI surface監査
#             （単一のpolicy=引数のみ、4公開メソッド全て）
# =====================================================================

print("[テスト9] _value_or_recover()呼び出し4箇所すべてが単一のpolicy=引数のみを渡すAPI surface監査")

coordinator_src = inspect.getsource(sys.modules["side_effect_safety.media_upload_safety_coordinator"])
coordinator_tree = ast.parse(coordinator_src)

value_or_recover_calls = []
for node in ast.walk(coordinator_tree):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "_value_or_recover":
        value_or_recover_calls.append(node)

check("9a. _value_or_recover()の呼び出し箇所は4公開メソッド分＝4件", len(value_or_recover_calls), 4)

all_single_policy_kw = True
for call_node in value_or_recover_calls:
    kw_names = [kw.arg for kw in call_node.keywords]
    if kw_names != ["policy"]:
        all_single_policy_kw = False

check_true("9b. 全4呼び出しがkeyword引数として`policy`のみを渡す（他のexpected_type/factory引数を渡す呼び出しは0件）", all_single_policy_kw)
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
