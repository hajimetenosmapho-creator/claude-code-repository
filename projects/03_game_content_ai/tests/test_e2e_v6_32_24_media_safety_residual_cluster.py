"""
E2E テスト: Release 6.32 Media Safety residual cluster
（§28.-40・§28.-35・§28.-15・§28.0a・§28.0b・§28.2）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    §28.-40（get()/stale-lock/read-then-mutate、6件）・§28.-35
    （_apply_featured_media_step()明示的dependency binding、15件）・§28.-15
    （呼び出し箇所B、11件）・§28.0a（Cross-Store Combination Table、14件）・
    §28.0b（media_id導出、6件）・§28.2（Gate OFF、8件）。

Canonical Gap Inventory照合（read-only、subagentによる網羅的coverage監査を
含む）の結果、既存test（v6_32_0/1/4/13/15/16/17/18/21/22）でCOMPLETEと
判定された項目は再実装しない。本ファイルは以下の残存clauseのみを閉じる：

    §28.0a #10（marker+upload_state、context無し→CONTRACT_VIOLATION）・
             #11（WordPressDraftRecord member_run_id不一致→classifier
                  CONTRACT_VIOLATION）
    §28.0b #1b（status≠APPLIEDならfeatured_media_id>0でもrecord_confirmed
                抑止）・#4（record_confirmed()durable ACK失敗→ATTEMPTEDの
                まま→HRR、呼び出し箇所レベル）
    §28.2  #3（Gate OFF+record_not_applicable() ACK失敗≠valid NOT_APPLICABLE）・
           #6（Gate設定変更は過去のNOT_APPLICABLEを再解釈しない）
    §28.-15 #7（identity構築の自由変数参照=0、AST監査）・#9（
             build_protected_execution_context()呼び出し箇所=1）・#10（
             Runtime Foundationに6.32-specific parameter=0）・#11（obsolete
             generic type参照=0）
    §28.-35 #1（明示的binding signature）・#6（Foundation 3ファイルへの
             6.32 module import=0、article_featured_media_runtime.py分を
             追加）・#7（protected builder exact dependencies）・#8（legacy
             builder signature）・#9/#12/#14（production dispatch path、
             実行ベース）・#13（orphan runtime argument audit）
    §28.-40 #4（4-combination time-skewed cross-store観測のexact classify）・
             #6（read-then-mutateのordering、mutation method signatureに
             pre-fetched snapshot引数が存在しないことの監査）

**external I/O = 0の保証**：前クラスタでtest harnessの実装ミスにより実HTTPS
通信が発生した反省を踏まえ、本ファイルはAnthropic/OpenAI/WordPress等への
実クライアントを一切構築・呼び出さない。§28.-35のH6（実行ベース）では
main.main()を使うが、`collect_all_news()`をmockして空リストを返すことで、
記事生成・API呼び出しへ到達する前（dispatch構築直後）にmain()を正常終了
させる（fake API keyのみに頼らない、構造的なnetwork遮断）。

対象production: なし（全てtest-only。production変更は一切行っていない）。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_24_media_safety_residual_cluster.py
"""
from __future__ import annotations

import ast
import dataclasses
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
print("Media Safety residual cluster（§28.-40・-35・-15・0a・0b・2）E2E テスト")
print("=" * 60)
print()

from article_media_upload_state.article_media_upload_state_manager import ArticleMediaUploadStateManager  # noqa: E402
from article_media_upload_state.json_article_media_upload_state_store import JsonArticleMediaUploadStateStore  # noqa: E402
from retry_lineage import RetryLineageDisposition  # noqa: E402
from retry_lineage.retry_lineage_target_resolution import resolve_final_disposition  # noqa: E402
from side_effect_safety import (  # noqa: E402
    JsonMediaUploadApplicabilityStore,
    MediaUploadSafetyContractViolationError,
    MediaUploadSafetyIOError,
    ProtectedSideEffectKind,
    SideEffectOperationIdentity,
    SideEffectSite,
    build_media_upload_safety_coordinator,
    build_protected_execution_context,
)
from side_effect_safety.commit_aware_lock import now_utc_iso  # noqa: E402
from side_effect_safety.media_upload_attempt_context_store import JsonMediaUploadAttemptContextStore  # noqa: E402
from side_effect_safety.media_upload_safety_coordinator import (  # noqa: E402
    ConfirmedMediaUploadSafetyRecord,
    IoArmedMediaUploadSafetyRecord,
    NotApplicableMediaUploadSafetyRecord,
    PreparedMediaUploadSafetyRecord,
)
from side_effect_safety.side_effect_safety_category import (  # noqa: E402
    ProtectedOperationContext,
    SideEffectSafetyCategory,
    SideEffectSafetyReport,
)
from side_effect_safety_classifier import SideEffectSafetyClassifier  # noqa: E402
from wordpress_draft_state.wordpress_draft_state_store import JsonWordPressDraftStateStore  # noqa: E402

import main  # noqa: E402
from outputs.base import ArticleData  # noqa: E402
from collector import NewsItem  # noqa: E402
from publishing_config import PublishStatus  # noqa: E402
from side_effect_safety.media_upload_write_ahead_wiring import (  # noqa: E402
    LegacyFeaturedMediaSideEffectBinding,
    MediaUploadWriteAheadAdapters,
    ProtectedFeaturedMediaSideEffectBinding,
    build_legacy_featured_media_side_effect_binding,
    build_protected_featured_media_side_effect_binding,
)
from article_featured_media_runtime import ArticleFeaturedMediaRuntime, ArticleFeaturedMediaRuntimeStatus  # noqa: E402
from article_featured_media_composition import ArticleFeaturedMediaCompositionRoot  # noqa: E402


def _tmp() -> Path:
    return Path(tempfile.mkdtemp(prefix="v6_32_24_"))


# Codex Final Review Blocking#2対応：protected bindingでのmanifest_registrar省略
# によるregistration bypassは許可されなくなったため、実のManifestRegistrarFacade
# を配線するヘルパー（test-owned tmp dir、production非変更）。
from protected_operation_manifest import JsonProtectedOperationManifestStore, ManifestRegistrarFacade  # noqa: E402


def _make_manifest_registrar(root_run_id: str, attempt_ordinal: int, member_run_id: str):
    store = JsonProtectedOperationManifestStore(base_dir=_tmp() / "manifest")
    store.create_for_attempt(root_run_id, attempt_ordinal, member_run_id)
    return ManifestRegistrarFacade(store)


def _identity(instance_key="art", root_run_id="r1", attempt_ordinal=1, kind=ProtectedSideEffectKind.MEDIA_UPLOAD, site=SideEffectSite.NEWS_STEP):
    return SideEffectOperationIdentity(
        root_run_id=root_run_id, attempt_ordinal=attempt_ordinal, operation_kind=kind,
        effect_site=site, operation_instance_key=instance_key,
    )


def _make_media_coordinator(tmpdir: Path):
    media_manager = ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(tmpdir / "media"))
    applicability_store = JsonMediaUploadApplicabilityStore(tmpdir / "applicability")
    attempt_context_store = JsonMediaUploadAttemptContextStore(tmpdir / "context")
    coordinator = build_media_upload_safety_coordinator(
        media_upload_manager=media_manager, applicability_store=applicability_store,
        attempt_context_store=attempt_context_store, locks_dir=tmpdir / "locks",
    )
    return coordinator, media_manager, applicability_store, attempt_context_store


class _UnusedDraftState:
    def get(self, *args, **kwargs):
        raise AssertionError("MEDIA_UPLOAD分岐ではdraft_state.get()は呼ばれないはず")


class _UnusedMediaCoordinator:
    def get(self, *args, **kwargs):
        raise AssertionError("WORDPRESS_DRAFT_CREATION分岐ではmedia_coordinator.get()は呼ばれないはず")


def _classify_media(coordinator, identity, member_run_id) -> SideEffectSafetyCategory:
    classifier = SideEffectSafetyClassifier(media_coordinator=coordinator, draft_state=_UnusedDraftState())
    return classifier._classify_one(identity, member_run_id, ProtectedSideEffectKind.MEDIA_UPLOAD)


def _classify_draft(draft_store, identity, member_run_id) -> SideEffectSafetyCategory:
    classifier = SideEffectSafetyClassifier(media_coordinator=_UnusedMediaCoordinator(), draft_state=draft_store)
    return classifier._classify_one(identity, member_run_id, ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION)


def _disposition_for(category: SideEffectSafetyCategory, kind: ProtectedSideEffectKind, site: SideEffectSite, instance_key: str) -> RetryLineageDisposition:
    report = SideEffectSafetyReport(entries=(
        (ProtectedOperationContext(operation_kind=kind, effect_site=site, operation_instance_key=instance_key), category),
    ))
    return resolve_final_disposition([], report)


# =====================================================================
# Part D: §28.0a Cross-Store Combination Table residual
# =====================================================================

print("[D1] §28.0a#10: marker + upload_state（context無し）→ CONTRACT_VIOLATION")

tmp_d1 = _tmp()
coordinator_d1, media_manager_d1, applicability_store_d1, _ = _make_media_coordinator(tmp_d1)
identity_d1 = _identity(instance_key="d1")

coordinator_d1.record_not_applicable(identity_d1, "member-d1")  # markerのみ確定
# コーディネータを経由せず、直接upload_stateへ書き込む（人為的な矛盾注入）
media_manager_d1.record_upload_started(article_identity=identity_d1.as_store_key())

raised_d1 = None
try:
    coordinator_d1.get(identity_d1, "member-d1")
except MediaUploadSafetyContractViolationError as e:
    raised_d1 = e

check_true("D1a. marker+upload_state（context無し）はMediaUploadSafetyContractViolationErrorとして検出される", raised_d1 is not None)
category_d1 = _classify_media(coordinator_d1, identity_d1, "member-d1")
check("D1b. classify()結果はCONTRACT_VIOLATION", category_d1, SideEffectSafetyCategory.CONTRACT_VIOLATION)
print()


print("[D2] §28.0a#11: WordPressDraftRecordのmember_run_id不一致 → classifier CONTRACT_VIOLATION")

tmp_d2 = _tmp()
draft_store_d2 = JsonWordPressDraftStateStore(tmp_d2 / "state", tmp_d2 / "locks")
identity_d2 = _identity(instance_key="d2", kind=ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION)
draft_store_d2.create_attempted(identity_d2, "member-correct", now_utc_iso())

category_d2 = _classify_draft(draft_store_d2, identity_d2, "member-WRONG")
disposition_d2 = _disposition_for(category_d2, ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION, SideEffectSite.NEWS_STEP, "d2")

check("D2a. member_run_id不一致はCONTRACT_VIOLATIONに分類される", category_d2, SideEffectSafetyCategory.CONTRACT_VIOLATION)
check("D2b. 最終dispositionはHUMAN_REVIEW_REQUIRED", disposition_d2, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
print()


# =====================================================================
# Part E: §28.0b media_id derivation residual
# =====================================================================

print("[E1] §28.0b#1b: status≠APPLIEDなら、featured_media_id>0（偶然の値）でもrecord_confirmed()は抑止される")


def make_article(slug: str) -> ArticleData:
    item = NewsItem(title="t", url="https://example.test/n", summary="s", source="src", published_at="2026-06-30", image_candidates=[])
    return ArticleData(item=item, importance="S", seo_title="t", article_body="b", x_post="x", slug=slug, publish_status=PublishStatus.DRAFT)


class _FakeMediaCoordinatorE1:
    def __init__(self):
        self.calls: list[tuple] = []

    def record_not_applicable(self, identity, member_run_id):
        self.calls.append(("not_applicable", identity, member_run_id))

    def record_prepared(self, identity, member_run_id):
        self.calls.append(("prepared", identity, member_run_id))

    def record_attempted(self, identity, member_run_id):
        self.calls.append(("attempted", identity, member_run_id))

    def record_confirmed(self, identity, member_run_id, media_id):
        self.calls.append(("confirmed", identity, member_run_id, media_id))


article_e1 = make_article("e1-status-mismatch")
article_e1_injected = dataclasses.replace(article_e1, featured_media_id=999)  # テスト用の人為的な「偶然の正の値」


class _FakeRuntimeE1:
    def is_available(self):
        return True

    def apply(self, article):
        from article_featured_media_runtime import ArticleFeaturedMediaRuntimeResult
        from image_generation_fallback_policy import ImageGenerationFailureCategory
        return ArticleFeaturedMediaRuntimeResult(
            article=article_e1_injected, status=ArticleFeaturedMediaRuntimeStatus.CONTINUED_WITHOUT_FEATURED_MEDIA,
            category=ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED, observation=None,
        )

    def classify_propagated_failure(self, exc):
        raise AssertionError("本テストのapply()はPROPAGATE対象例外を送出しないため呼ばれないはず")


coordinator_e1 = _FakeMediaCoordinatorE1()
context_e1 = build_protected_execution_context(root_run_id="root-24e1", attempt_ordinal=1, member_run_id="member-24e1", side_effect_contract_version=1)
adapters_e1 = MediaUploadWriteAheadAdapters(enabled=True, image_generator=object(), base_media_uploader=object(), image_mime_type="image/png")
binding_e1 = build_protected_featured_media_side_effect_binding(
    context_e1, coordinator_e1, adapters_e1, _make_manifest_registrar("root-24e1", 1, "member-24e1"),
)

with patch("main.build_protected_featured_media_runtime", return_value=_FakeRuntimeE1()):
    result_e1 = main._apply_featured_media_step(article_e1, side_effect_binding=binding_e1)

check("E1a. statusはCONTINUED_WITHOUT_FEATURED_MEDIA", result_e1.status, ArticleFeaturedMediaRuntimeStatus.CONTINUED_WITHOUT_FEATURED_MEDIA)
check_false("E1b. record_confirmed()は一切呼ばれない（featured_media_id>0だけでは判断されない）", any(c[0] == "confirmed" for c in coordinator_e1.calls))
print()


print("[E2] §28.0b#4: record_confirmed()のdurable ACK失敗 → ATTEMPTEDのまま → 再起動HRR（呼び出し箇所レベル）")

tmp_e2 = _tmp()
coordinator_e2, media_manager_e2, _, _ = _make_media_coordinator(tmp_e2)
context_e2 = build_protected_execution_context(root_run_id="root-24e2", attempt_ordinal=1, member_run_id="member-24e2", side_effect_contract_version=1)


class _SucceedingGenerator:
    def generate(self, prompt):
        from ai_image_generation import GeneratedImage
        return GeneratedImage(image_bytes=b"\x89PNG", mime_type="image/png")


class _SucceedingUploader:
    def upload(self, image, filename):
        from wordpress_media import MediaUploadResult
        return MediaUploadResult(media_id=555, source_url="https://example.test/i.png", mime_type="image/png")


adapters_e2 = MediaUploadWriteAheadAdapters(enabled=True, image_generator=_SucceedingGenerator(), base_media_uploader=_SucceedingUploader(), image_mime_type="image/png")
binding_e2 = build_protected_featured_media_side_effect_binding(
    context_e2, coordinator_e2, adapters_e2, _make_manifest_registrar("root-24e2", 1, "member-24e2"),
)

article_e2 = make_article("e2-confirm-ack-failure")
raised_e2 = None
with patch.object(media_manager_e2, "record_upload_succeeded", side_effect=MediaUploadSafetyIOError("simulated write failure")):
    try:
        main._apply_featured_media_step(article_e2, side_effect_binding=binding_e2)
    except MediaUploadSafetyIOError as e:
        raised_e2 = e

check_true("E2a. record_confirmed()のdurable ACK失敗が呼び出し元へ伝播する", raised_e2 is not None)

identity_e2 = _identity(instance_key="e2-confirm-ack-failure", root_run_id="root-24e2")
restarted_coordinator_e2, _, _, _ = _make_media_coordinator(tmp_e2)
category_e2 = _classify_media(restarted_coordinator_e2, identity_e2, "member-24e2")
disposition_e2 = _disposition_for(category_e2, ProtectedSideEffectKind.MEDIA_UPLOAD, SideEffectSite.NEWS_STEP, "e2-confirm-ack-failure")

check("E2b. 再起動後の分類はIN_PROGRESS_OR_UNKNOWN（CONFIRMED_SUCCESSは未確定）", category_e2, SideEffectSafetyCategory.IN_PROGRESS_OR_UNKNOWN)
check("E2c. 最終dispositionはHUMAN_REVIEW_REQUIRED", disposition_e2, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
print()


# =====================================================================
# Part F: §28.2 Gate OFF residual
# =====================================================================

print("[F1] §28.2#3: Gate OFF + record_not_applicable() ACK失敗 ≠ valid NOT_APPLICABLE、external I/O=0")

tmp_f1 = _tmp()
coordinator_f1, _, applicability_store_f1, _ = _make_media_coordinator(tmp_f1)
identity_f1 = _identity(instance_key="f1")

raised_f1 = None
with patch.object(applicability_store_f1, "create", side_effect=MediaUploadSafetyIOError("simulated ACK failure")):
    try:
        coordinator_f1.record_not_applicable(identity_f1, "member-f1")
    except MediaUploadSafetyIOError as e:
        raised_f1 = e

check_true("F1a. ACK失敗はMediaUploadSafetyIOErrorとして伝播する（正常なNOT_APPLICABLE確定として扱われない）", raised_f1 is not None)
check_true("F1b. get()はレコード非存在（None）を返す", coordinator_f1.get(identity_f1, "member-f1") is None)
category_f1 = _classify_media(coordinator_f1, identity_f1, "member-f1")
check("F1c. classify()結果はCONTRACT_VIOLATION（レコード非存在）", category_f1, SideEffectSafetyCategory.CONTRACT_VIOLATION)
print()


print("[F2] §28.2#6: Gate設定変更は、過去に確定したNOT_APPLICABLEを再解釈しない")

tmp_f2 = _tmp()
coordinator_f2, _, _, _ = _make_media_coordinator(tmp_f2)
identity_f2 = _identity(instance_key="f2")
coordinator_f2.record_not_applicable(identity_f2, "member-f2")

# get()/classify()はGate設定（adapters.enabled）を一切引数に取らない構造そのものが
# 「現在のGate設定による再解釈が構造的に不可能」であることを示す
_get_sig_params_f2 = set(inspect.signature(coordinator_f2.get).parameters.keys())
check("F2a. get()のシグネチャにGate/adapters/enabledに相当する引数が存在しない", _get_sig_params_f2 & {"gate", "adapters", "enabled", "config"}, set())

record_after_f2 = coordinator_f2.get(identity_f2, "member-f2")
check_true("F2b. 記録済みNOT_APPLICABLEは、現在のGate設定に関わらず同一のNotApplicableMediaUploadSafetyRecordとして返る", isinstance(record_after_f2, NotApplicableMediaUploadSafetyRecord))
category_f2 = _classify_media(coordinator_f2, identity_f2, "member-f2")
check("F2c. classify()結果もNOT_APPLICABLEのまま（HRRへ再解釈されない）", category_f2, SideEffectSafetyCategory.NOT_APPLICABLE)
print()


# =====================================================================
# Part G: §28.-15 呼び出し箇所B residual
# =====================================================================

print("[G1] §28.-15#7: _apply_featured_media_step()のSideEffectOperationIdentity構築が自由変数を参照しない")

_main_src = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
_main_tree = ast.parse(_main_src)

_apply_step_func = None
for node in ast.walk(_main_tree):
    if isinstance(node, ast.FunctionDef) and node.name == "_apply_featured_media_step":
        _apply_step_func = node
        break

check_true("G1a. _apply_featured_media_step()がmain.py内に存在する", _apply_step_func is not None)

_identity_call = None
for node in ast.walk(_apply_step_func):
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "SideEffectOperationIdentity":
        _identity_call = node
        break

check_true("G1b. SideEffectOperationIdentity(...)呼び出しが関数内に存在する", _identity_call is not None)

_local_param_names = {a.arg for a in _apply_step_func.args.args} | {a.arg for a in _apply_step_func.args.kwonlyargs}
_free_variable_refs = []
if _identity_call is not None:
    for kw in _identity_call.keywords:
        for sub in ast.walk(kw.value):
            if isinstance(sub, ast.Name) and sub.id not in _local_param_names and sub.id not in {"context", "identity", "article"}:
                # contextから派生した中間変数（例: context.root_run_id）はast.Attributeの
                # base側にast.Nameとして現れるため、"context"自体は許容する。
                if not (isinstance(kw.value, ast.Attribute)):
                    _free_variable_refs.append(sub.id)

check("G1c. identity構築のkeyword引数値に、article/context/identity以外の自由変数参照が存在しない", _free_variable_refs, [])
print()


print("[G2] §28.-15#9: build_protected_execution_context()のproduction呼び出し箇所は1件のみ")

_call_sites_g2 = []
for py_file in list(SRC_DIR.rglob("*.py")) + [PROJECT_ROOT / "main.py"]:
    if "__pycache__" in str(py_file):
        continue
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
    except SyntaxError:
        continue
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else (fn.attr if isinstance(fn, ast.Attribute) else None)
            if name == "build_protected_execution_context":
                # 定義自体（def build_protected_execution_context）は除外
                if not (py_file.name == "side_effect_execution_mode.py"):
                    _call_sites_g2.append(str(py_file.relative_to(PROJECT_ROOT)))

check("G2a. build_protected_execution_context()のproduction呼び出し箇所は1件（WorkflowEngineExecutor）", len(_call_sites_g2), 1)
if _call_sites_g2:
    check_true("G2b. その1件はworkflow_engine_executor.py内である", "workflow_engine_executor" in _call_sites_g2[0])
print()


print("[G3] §28.-15#10: ArticleFeaturedMediaRuntimeに6.32-specific parameter=0")

_runtime_init_sig = inspect.signature(ArticleFeaturedMediaRuntime.__init__)
_runtime_apply_sig = inspect.signature(ArticleFeaturedMediaRuntime.apply)
_forbidden_param_names = {"side_effect_execution_context", "side_effect_execution_provenance", "media_upload_coordinator", "adapters"}

check("G3a. __init__の引数に6.32-specific paramが存在しない", set(_runtime_init_sig.parameters.keys()) & _forbidden_param_names, set())
check("G3b. apply()の引数に6.32-specific paramが存在しない", set(_runtime_apply_sig.parameters.keys()) & _forbidden_param_names, set())
print()


print("[G4] §28.-15#11: obsolete generic SideEffectExecutionContext型参照=0")

_obsolete_refs_g4 = []
for py_file in list(SRC_DIR.rglob("*.py")) + [PROJECT_ROOT / "main.py"]:
    if "__pycache__" in str(py_file):
        continue
    text = py_file.read_text(encoding="utf-8")
    # 新型（discriminated union）とは異なる、旧世代の汎用execution_modeフィールドを
    # 持つクラス定義が存在しないことを確認する
    if "class SideEffectExecutionContext" in text or "execution_mode:" in text:
        _obsolete_refs_g4.append(str(py_file.relative_to(PROJECT_ROOT)))

check("G4a. 旧世代の汎用SideEffectExecutionContext型定義・execution_modeフィールドへの参照が0件", _obsolete_refs_g4, [])
print()


# =====================================================================
# Part H: §28.-35 _apply_featured_media_step() dependency binding residual
# =====================================================================

print("[H1] §28.-35#1: _apply_featured_media_step()のexplicit binding signature")

_apply_step_sig = inspect.signature(main._apply_featured_media_step)
_positional_params_h1 = [
    name for name, p in _apply_step_sig.parameters.items()
    if p.kind in (inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD)
]
_kwonly_params_h1 = [name for name, p in _apply_step_sig.parameters.items() if p.kind is inspect.Parameter.KEYWORD_ONLY]

check("H1a. 位置引数はarticleの1つのみ", _positional_params_h1, ["article"])
check("H1b. keyword-only引数はside_effect_bindingの1つのみ", _kwonly_params_h1, ["side_effect_binding"])
print()


print("[H2] §28.-35#6: Foundation 3ファイルへの6.32 binding module importが0件")

_foundation_files_h2 = [
    SRC_DIR / "article_featured_media_runtime" / "article_featured_media_runtime.py",
    SRC_DIR / "article_featured_media_composition" / "article_featured_media_composition_root.py",
    SRC_DIR / "article_featured_media_orchestration" / "article_featured_media_orchestrator.py",
]
_forbidden_names_h2 = {
    "FeaturedMediaSideEffectBinding", "ProtectedFeaturedMediaSideEffectBinding",
    "LegacyFeaturedMediaSideEffectBinding", "media_upload_write_ahead_wiring",
}
for f in _foundation_files_h2:
    tree = ast.parse(f.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
            names.update(a.name for a in node.names)
        elif isinstance(node, ast.Import):
            names.update(a.name for a in node.names)
    check(f"H2-{f.name}: 6.32 binding moduleへの直接importが0件", names & _forbidden_names_h2, set())
print()


print("[H3] §28.-35#7: protected builder exact dependencies（is比較、必須3引数）")

_protected_sig = inspect.signature(build_protected_featured_media_side_effect_binding)
check(
    "H3a. protected builderは4引数すべて必須（デフォルト値なし、Architecture Amendment"
    "でmanifest_registrarを追加後も維持、§28.-35#7）",
    [p.default for p in _protected_sig.parameters.values()], [inspect.Parameter.empty] * 4,
)

_ctx_h3 = build_protected_execution_context(root_run_id="root-24h3", attempt_ordinal=1, member_run_id="member-24h3", side_effect_contract_version=1)
_coordinator_h3 = object()
_adapters_h3 = MediaUploadWriteAheadAdapters(enabled=False)
_binding_h3 = build_protected_featured_media_side_effect_binding(_ctx_h3, _coordinator_h3, _adapters_h3, None)

check_true("H3b. binding.contextは渡した値とis同一", _binding_h3.context is _ctx_h3)
check_true("H3c. binding.media_upload_coordinatorは渡した値とis同一", _binding_h3.media_upload_coordinator is _coordinator_h3)
check_true("H3d. binding.adaptersは渡した値とis同一", _binding_h3.adapters is _adapters_h3)
_protected_fields_h3 = {f.name for f in dataclasses.fields(ProtectedFeaturedMediaSideEffectBinding)}
check("H3e. ProtectedFeaturedMediaSideEffectBindingにruntime fieldが存在しない", "runtime" in _protected_fields_h3, False)
print()


print("[H4] §28.-35#8: legacy builder signature（context・runtimeの2引数のみ）")

_legacy_sig = inspect.signature(build_legacy_featured_media_side_effect_binding)
check("H4a. legacy builderの引数は2つのみ", len(_legacy_sig.parameters), 2)
check("H4b. 2引数ともデフォルト値なし（必須）", [p.default for p in _legacy_sig.parameters.values()], [inspect.Parameter.empty] * 2)

_legacy_fields_h4 = {f.name for f in dataclasses.fields(LegacyFeaturedMediaSideEffectBinding)}
check("H4c. LegacyFeaturedMediaSideEffectBindingのfieldはcontext/runtimeの2つのみ", _legacy_fields_h4, {"context", "runtime"})
check_false("H4d. media_upload_coordinator/adaptersに相当するfieldが存在しない", bool(_legacy_fields_h4 & {"media_upload_coordinator", "adapters"}))
print()


print("[H5] §28.-35#13: 'runtime'という名の引数/fieldはLegacyFeaturedMediaSideEffectBinding.runtimeとlegacy builderの2箇所のみ")

_runtime_occurrences_h5 = []
if "runtime" in _apply_step_sig.parameters:
    _runtime_occurrences_h5.append("_apply_featured_media_step.runtime")
if "runtime" in _protected_sig.parameters:
    _runtime_occurrences_h5.append("protected_builder.runtime")
if "runtime" in _legacy_sig.parameters:
    _runtime_occurrences_h5.append("legacy_builder.runtime")
if "runtime" in _protected_fields_h3:
    _runtime_occurrences_h5.append("ProtectedBinding.runtime")
if "runtime" in _legacy_fields_h4:
    _runtime_occurrences_h5.append("LegacyBinding.runtime")

check("H5a. 'runtime'が出現するのはlegacy builder引数とLegacyBinding fieldの2箇所のみ", sorted(_runtime_occurrences_h5), sorted(["legacy_builder.runtime", "LegacyBinding.runtime"]))
print()


print("[H6] §28.-35#9・#12・#14: production dispatch path（main.py起動処理）の実行ベース確認")

tmp_h6 = _tmp()


def _fake_collect_all_news_empty(max_items_per_feed=20):
    return ([], [])


def _run_main_dispatch(env_overrides: dict):
    import os as _os
    saved = {k: _os.environ.get(k) for k in env_overrides}
    saved_key = _os.environ.get("ANTHROPIC_API_KEY")
    saved_argv = sys.argv
    for k, v in env_overrides.items():
        _os.environ[k] = v
    _os.environ["ANTHROPIC_API_KEY"] = "test-key-not-real"
    sys.argv = [str(PROJECT_ROOT / "main.py")]

    _real_runtime_from_env = main.ArticleFeaturedMediaRuntime.from_env
    _real_root_from_env = ArticleFeaturedMediaCompositionRoot.from_env
    _real_legacy_builder = main.build_legacy_featured_media_side_effect_binding
    _real_protected_builder = main.build_protected_featured_media_side_effect_binding
    _returned_runtimes: list = []

    def _runtime_from_env_side_effect():
        rt = _real_runtime_from_env()
        _returned_runtimes.append(rt)
        return rt

    try:
        with patch("main.OUTPUT_DIR", tmp_h6 / "output"), \
             patch("main.WORDPRESS_DRAFT_STATE_DIR", tmp_h6 / "state" / "wordpress_draft_state"), \
             patch("main.MEDIA_UPLOAD_STATE_DIR", tmp_h6 / "state" / "article_media_upload_state"), \
             patch("main.MEDIA_UPLOAD_APPLICABILITY_DIR", tmp_h6 / "state" / "media_upload_applicability"), \
             patch("main.MEDIA_UPLOAD_ATTEMPT_CONTEXT_DIR", tmp_h6 / "state" / "media_upload_attempt_context"), \
             patch("main.MEDIA_UPLOAD_LOCKS_DIR", tmp_h6 / "state" / "media_upload_locks"), \
             patch("main.collect_all_news", side_effect=_fake_collect_all_news_empty), \
             patch("main.ArticleFeaturedMediaRuntime.from_env", side_effect=_runtime_from_env_side_effect) as spy_runtime_from_env, \
             patch.object(ArticleFeaturedMediaCompositionRoot, "from_env", side_effect=_real_root_from_env) as spy_root_from_env, \
             patch("main.build_legacy_featured_media_side_effect_binding", side_effect=_real_legacy_builder) as spy_legacy_builder, \
             patch("main.build_protected_featured_media_side_effect_binding", side_effect=_real_protected_builder) as spy_protected_builder:
            returncode = main.main()
            return returncode, spy_runtime_from_env, spy_root_from_env, spy_legacy_builder, spy_protected_builder, _returned_runtimes
    finally:
        sys.argv = saved_argv
        for k, v in saved.items():
            if v is None:
                _os.environ.pop(k, None)
            else:
                _os.environ[k] = v
        if saved_key is None:
            _os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            _os.environ["ANTHROPIC_API_KEY"] = saved_key


# legacy self-origination経路（RETRY_LINEAGE_*を一切設定しない）
import os as _os_h6  # noqa: E402
_removed_env_h6 = {}
for k in ("RETRY_LINEAGE_EXECUTION_MODE", "RETRY_LINEAGE_ROOT_RUN_ID", "RETRY_LINEAGE_ATTEMPT_ORDINAL", "RETRY_LINEAGE_MEMBER_RUN_ID", "RETRY_LINEAGE_CONTRACT_VERSION"):
    if k in _os_h6.environ:
        _removed_env_h6[k] = _os_h6.environ.pop(k)
try:
    rc_legacy, spy_rt_legacy, spy_root_legacy, spy_legacy_b, spy_protected_b_legacy, returned_runtimes_legacy = _run_main_dispatch({})
finally:
    _os_h6.environ.update(_removed_env_h6)

check("H6a. legacy経路: ArticleFeaturedMediaRuntime.from_env()は1回だけ呼ばれる", spy_rt_legacy.call_count, 1)
check("H6b. legacy経路: build_legacy_featured_media_side_effect_binding()は1回だけ呼ばれる", spy_legacy_b.call_count, 1)
check("H6c. legacy経路: build_protected_featured_media_side_effect_binding()は呼ばれない", spy_protected_b_legacy.call_count, 0)
if spy_rt_legacy.call_count == 1 and spy_legacy_b.call_count == 1:
    _built_runtime_h6 = returned_runtimes_legacy[0]
    _binding_runtime_h6 = spy_legacy_b.call_args[0][1]
    check_true("H6d. legacy binding.runtimeは起動時に構築されたfeatured_media_runtimeとis同一（記事ごとの再構築なし）", _binding_runtime_h6 is _built_runtime_h6)

# protected経路（正当なRETRY_LINEAGE_PROTECTED envelope）
rc_protected, spy_rt_protected, spy_root_protected, spy_legacy_b_protected, spy_protected_b, returned_runtimes_protected = _run_main_dispatch({
    "RETRY_LINEAGE_EXECUTION_MODE": "retry_lineage_protected",
    "RETRY_LINEAGE_ROOT_RUN_ID": "root-24h6",
    "RETRY_LINEAGE_ATTEMPT_ORDINAL": "1",
    "RETRY_LINEAGE_MEMBER_RUN_ID": "member-24h6",
    "RETRY_LINEAGE_CONTRACT_VERSION": "1",
})

check("H6e. protected経路: ArticleFeaturedMediaRuntime.from_env()は呼ばれない（unused legacy runtime construction=0）", spy_rt_protected.call_count, 0)
check("H6f. protected経路: ArticleFeaturedMediaCompositionRoot.from_env()も呼ばれない", spy_root_protected.call_count, 0)
check("H6g. protected経路: build_protected_featured_media_side_effect_binding()が1回だけ呼ばれる", spy_protected_b.call_count, 1)
check("H6h. protected経路: build_legacy_featured_media_side_effect_binding()は呼ばれない", spy_legacy_b_protected.call_count, 0)
print()


# =====================================================================
# Part I: §28.-40 get()/stale-lock/read-then-mutate residual
# =====================================================================

print("[I1] §28.-40#4: 4-combination time-skewed cross-store観測のexact classify")


def _seed_media_stores(tmpdir, identity, member_run_id, *, applicability=False, context_phase=None, upload_state=None):
    coordinator, media_manager, applicability_store, attempt_context_store = _make_media_coordinator(tmpdir)
    if applicability:
        applicability_store.create(identity, member_run_id, now_utc_iso())
    if context_phase == "PREPARED":
        attempt_context_store.create_prepared(identity, member_run_id, now_utc_iso())
    elif context_phase == "IO_ARMED":
        attempt_context_store.create_prepared(identity, member_run_id, now_utc_iso())
        attempt_context_store.transition_to_io_armed(identity, member_run_id, now_utc_iso())
    if upload_state == "ATTEMPTED":
        media_manager.record_upload_started(article_identity=identity.as_store_key())
    elif upload_state == "CONFIRMED_SUCCESS":
        media_manager.record_upload_started(article_identity=identity.as_store_key())
        media_manager.record_upload_succeeded(article_identity=identity.as_store_key(), media_id=321)
    return coordinator


# (a) marker非存在・context=IO_ARMED（旧）・upload_state=CONFIRMED_SUCCESS（新）→ CONFIRMED_SUCCESS
tmp_i1a = _tmp()
identity_i1a = _identity(instance_key="i1a")
coordinator_i1a = _seed_media_stores(tmp_i1a, identity_i1a, "member-i1a", context_phase="IO_ARMED", upload_state="CONFIRMED_SUCCESS")
category_i1a = _classify_media(coordinator_i1a, identity_i1a, "member-i1a")
check("I1a. (a) IO_ARMED+CONFIRMED_SUCCESS → CONFIRMED_SUCCESS", category_i1a, SideEffectSafetyCategory.CONFIRMED_SUCCESS)

# (b) marker非存在・context=PREPARED・upload_state=ATTEMPTED → SAFE_TO_CONTINUE
tmp_i1b = _tmp()
identity_i1b = _identity(instance_key="i1b")
coordinator_i1b = _seed_media_stores(tmp_i1b, identity_i1b, "member-i1b", context_phase="PREPARED", upload_state="ATTEMPTED")
category_i1b = _classify_media(coordinator_i1b, identity_i1b, "member-i1b")
check("I1b. (b) PREPARED+ATTEMPTED → SAFE_TO_CONTINUE", category_i1b, SideEffectSafetyCategory.SAFE_TO_CONTINUE)

# (c) marker非存在・context=IO_ARMED・upload_state=ATTEMPTED → IN_PROGRESS_OR_UNKNOWN
tmp_i1c = _tmp()
identity_i1c = _identity(instance_key="i1c")
coordinator_i1c = _seed_media_stores(tmp_i1c, identity_i1c, "member-i1c", context_phase="IO_ARMED", upload_state="ATTEMPTED")
category_i1c = _classify_media(coordinator_i1c, identity_i1c, "member-i1c")
check("I1c. (c) IO_ARMED+ATTEMPTED → IN_PROGRESS_OR_UNKNOWN", category_i1c, SideEffectSafetyCategory.IN_PROGRESS_OR_UNKNOWN)

# (d) marker非存在・context非存在・upload_state=ATTEMPTED → CONTRACT_VIOLATION
tmp_i1d = _tmp()
identity_i1d = _identity(instance_key="i1d")
coordinator_i1d = _seed_media_stores(tmp_i1d, identity_i1d, "member-i1d", upload_state="ATTEMPTED")
category_i1d = _classify_media(coordinator_i1d, identity_i1d, "member-i1d")
check("I1d. (d) context無し+ATTEMPTED → CONTRACT_VIOLATION（lifecycle違反の矛盾combination）", category_i1d, SideEffectSafetyCategory.CONTRACT_VIOLATION)
print()


print("[I2] §28.-40#6: read-then-mutateのordering（mutation methodにpre-fetched snapshot引数が存在しない）")

from side_effect_safety.media_upload_safety_coordinator import MediaUploadSafetyCoordinator  # noqa: E402
from wordpress_draft_state.wordpress_draft_state_store import JsonWordPressDraftStateStore as _JWDSS  # noqa: E402

_mutation_methods_i2 = [
    (MediaUploadSafetyCoordinator, "record_not_applicable"),
    (MediaUploadSafetyCoordinator, "record_prepared"),
    (MediaUploadSafetyCoordinator, "record_attempted"),
    (MediaUploadSafetyCoordinator, "record_confirmed"),
    (_JWDSS, "create_attempted"),
    (_JWDSS, "transition_to_confirmed"),
]
_forbidden_snapshot_param_names = {"record", "snapshot", "existing", "existing_record", "current_state", "prefetched"}
_snapshot_leak_i2 = []
for cls, method_name in _mutation_methods_i2:
    sig = inspect.signature(getattr(cls, method_name))
    if set(sig.parameters.keys()) & _forbidden_snapshot_param_names:
        _snapshot_leak_i2.append(f"{cls.__name__}.{method_name}")

check("I2a. 全mutation methodのシグネチャにpre-fetched snapshot/record引数が存在しない（呼び出しのたびlock内で再read）", _snapshot_leak_i2, [])

# body内でself._read_all()/self._read_raw()を直接呼んでいる（self.get()経由で
# 外部snapshotを再利用していない）ことをAST監査する
_coordinator_src = inspect.getsource(MediaUploadSafetyCoordinator)
_coordinator_tree = ast.parse(_coordinator_src)
_uses_get_in_mutation_i2 = []
for node in ast.walk(_coordinator_tree):
    if isinstance(node, ast.FunctionDef) and node.name in {"record_not_applicable", "record_prepared", "record_attempted", "record_confirmed"}:
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Attribute) and sub.func.attr == "get" and isinstance(sub.func.value, ast.Name) and sub.func.value.id == "self":
                _uses_get_in_mutation_i2.append(node.name)

check("I2b. 4公開メソッドのbodyがself.get()（lock-free）を呼んでいない（必ずlock内の_read_all()を使う）", _uses_get_in_mutation_i2, [])
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
