"""
E2E テスト: v6.32.4 呼び出し箇所B（NEWS / ArticleFeaturedMediaRuntime経由のmedia upload）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    15.4節・15.4.1節・15.5節（Confirmation Invariant）・22.3.2節（Exact Integration Points）。

sub-milestone 4のdirect tests。以下を検証する：
    (a) write-ahead-before-I/O契約：record_attempted()（IO_ARMED durable ACK）
        確認後にのみ、真の外部I/Oである media_uploader.upload() が呼ばれる
        （9.9.3節と同型のOrdering Contract）
    (b) write-ahead ACK失敗時はupload()が一切呼ばれない（external I/O = 0）
    (c) Gate OFF時はrecord_not_applicable()のみが呼ばれ、record_prepared()・
        record_attempted()・record_confirmed()のいずれも呼ばれない
    (d) record_confirmed()はruntime_result.status is APPLIED、かつ
        _extract_confirmed_media_id()が非Noneの場合のみ呼ばれる
        （CONTINUED_WITHOUT_FEATURED_MEDIA・DISABLEDでは呼ばれない）
    (e) legacy bindingでは4 safety methodsのいずれも呼ばれない
    (f) 未知binding型はいずれのI/O・safety methodも呼ぶ前にfail-closedする
    (g) FeaturedMediaPropagatedFailureはraw exceptionへの参照
        （__context__／__cause__）を一切保持しない
    (h) identity構築（operation_kind=MEDIA_UPLOAD・effect_site=NEWS_STEP・
        operation_instance_key=article.slug）

実行方法:
    cd projects/03_game_content_ai
    .\\venv\\Scripts\\python.exe tests\\test_e2e_v6_32_4_call_site_b_media_upload.py
"""
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
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


def check_false(label: str, value: bool):
    check(label, bool(value), False)


print("=" * 60)
print("v6.32.4 呼び出し箇所B（NEWS / media upload）E2E テスト")
print("=" * 60)
print()

import main  # noqa: E402
from outputs.base import ArticleData  # noqa: E402
from collector import NewsItem  # noqa: E402
from publishing_config import PublishStatus  # noqa: E402
from ai_image_generation import GeneratedImage  # noqa: E402
from wordpress_media import MediaUploadResult, WordPressMediaUploadError, WordPressMediaUploadErrorReason  # noqa: E402
from openai_image_generation import OpenAIImageGenerationError, OpenAIImageGenerationErrorReason  # noqa: E402
from article_featured_media_runtime import ArticleFeaturedMediaRuntimeStatus  # noqa: E402
from side_effect_safety import (  # noqa: E402
    LegacyEntrypoint,
    LegacyExecutionOrigin,
    ProtectedSideEffectKind,
    SideEffectExecutionModeContractError,
    SideEffectSite,
    build_legacy_direct_provenance,
    build_protected_execution_context,
    complete_legacy_execution_context,
)
from side_effect_safety.side_effect_execution_mode import ExecutionModeFailureReasonCode  # noqa: E402
from side_effect_safety.errors import MediaUploadSafetyIOError  # noqa: E402
from side_effect_safety.media_upload_write_ahead_wiring import (  # noqa: E402
    FeaturedMediaPropagatedFailure,
    LegacyFeaturedMediaSideEffectBinding,
    MediaUploadWriteAheadAdapters,
    ProtectedFeaturedMediaSideEffectBinding,
    build_legacy_featured_media_side_effect_binding,
    build_protected_featured_media_side_effect_binding,
)
from protected_operation_manifest import JsonProtectedOperationManifestStore, ManifestRegistrarFacade  # noqa: E402


def make_article(slug: str = "ps6-announced-20260630") -> ArticleData:
    item = NewsItem(
        title="PS6正式発表",
        url="https://blog.playstation.com/test",
        summary="PlayStation 6 が正式に発表されました。",
        source="PlayStation Blog",
        published_at="2026-06-30",
        image_candidates=[],
    )
    return ArticleData(
        item=item,
        importance="S",
        seo_title="PS6が正式発表",
        article_body="PS6が発表されました。",
        x_post="PS6発表！",
        slug=slug,
        publish_status=PublishStatus.DRAFT,
    )


_PROTECTED_CONTEXT = build_protected_execution_context(
    root_run_id="root-b1", attempt_ordinal=1, member_run_id="member-b1",
    side_effect_contract_version=1,
)

_LEGACY_CONTEXT = complete_legacy_execution_context(
    build_legacy_direct_provenance(LegacyEntrypoint.RUN_MAIN_DIRECT),
    LegacyExecutionOrigin.MAIN_DIRECT,
)

# Codex Final Review Blocking#2対応：protected bindingでのmanifest_registrar
# 省略によるregistration bypassは許可されなくなったため、既存test（write-ahead
# -before-I/O契約等）を維持するため実のManifestRegistrarFacadeを配線する
# （test-owned tmp dir、production非変更）。admission相当のcreate_for_attempt()
# を先に行う。
_manifest_store_b = JsonProtectedOperationManifestStore(base_dir=Path(tempfile.mkdtemp()) / "manifest")
_manifest_store_b.create_for_attempt("root-b1", 1, "member-b1")
_manifest_registrar_b = ManifestRegistrarFacade(_manifest_store_b)


class _FakeMediaUploadSafetyCoordinator:
    def __init__(self, fail_attempted: bool = False):
        self.calls: list[tuple] = []
        self._fail_attempted = fail_attempted

    def record_not_applicable(self, identity, member_run_id):
        self.calls.append(("not_applicable", identity, member_run_id))

    def record_prepared(self, identity, member_run_id):
        self.calls.append(("prepared", identity, member_run_id))

    def record_attempted(self, identity, member_run_id):
        self.calls.append(("attempted", identity, member_run_id))
        if self._fail_attempted:
            raise MediaUploadSafetyIOError("simulated write-ahead ACK failure")

    def record_confirmed(self, identity, member_run_id, media_id):
        self.calls.append(("confirmed", identity, member_run_id, media_id))


class _RaisingCoordinator:
    """呼ばれたら即fail-closedするFake（legacy経路での0-call保証確認用）。"""

    def record_not_applicable(self, identity, member_run_id):
        raise AssertionError("legacy binding経由でrecord_not_applicable()が呼ばれてはならない")

    def record_prepared(self, identity, member_run_id):
        raise AssertionError("legacy binding経由でrecord_prepared()が呼ばれてはならない")

    def record_attempted(self, identity, member_run_id):
        raise AssertionError("legacy binding経由でrecord_attempted()が呼ばれてはならない")

    def record_confirmed(self, identity, member_run_id, media_id):
        raise AssertionError("legacy binding経由でrecord_confirmed()が呼ばれてはならない")


class _FakeImageGenerator:
    def __init__(self, error: Exception | None = None):
        self._error = error
        self.calls = 0

    def generate(self, prompt):
        self.calls += 1
        if self._error is not None:
            raise self._error
        return GeneratedImage(image_bytes=b"\x89PNG-fake-bytes", mime_type="image/png")


class _FakeBaseMediaUploader:
    """decoratorがwrapする既存GeneratedImageWordPressMediaUploader相当のFake。"""

    def __init__(self, events: list, media_id: int = 777):
        self._events = events
        self._media_id = media_id

    def upload(self, image, filename):
        self._events.append("upload_called")
        return MediaUploadResult(media_id=self._media_id, source_url="https://example.test/i.png", mime_type="image/png")


def _tracked_coordinator_with_events(events: list, fail_attempted: bool = False) -> _FakeMediaUploadSafetyCoordinator:
    coordinator = _FakeMediaUploadSafetyCoordinator(fail_attempted=fail_attempted)
    original_attempted = coordinator.record_attempted

    def _tracked_attempted(identity, member_run_id):
        events.append("attempted")
        return original_attempted(identity, member_run_id)

    coordinator.record_attempted = _tracked_attempted
    return coordinator


def _make_protected_binding(adapters: MediaUploadWriteAheadAdapters, coordinator) -> ProtectedFeaturedMediaSideEffectBinding:
    return build_protected_featured_media_side_effect_binding(
        _PROTECTED_CONTEXT, coordinator, adapters, _manifest_registrar_b,
    )


# ─── [テスト1] write-ahead-before-I/O契約 ───

print("[テスト1] write-ahead-before-I/O契約（record_attempted→upload_calledの順序）")

events_1: list[str] = []
coordinator_1 = _tracked_coordinator_with_events(events_1)
adapters_1 = MediaUploadWriteAheadAdapters(
    enabled=True,
    image_generator=_FakeImageGenerator(),
    base_media_uploader=_FakeBaseMediaUploader(events_1, media_id=777),
    image_mime_type="image/png",
)
binding_1 = _make_protected_binding(adapters_1, coordinator_1)
result_1 = main._apply_featured_media_step(make_article(), side_effect_binding=binding_1)

check("1a. 呼び出し順序はattempted→upload_called", events_1, ["attempted", "upload_called"])
check("1b. record_prepared()が最初に呼ばれる", coordinator_1.calls[0][0], "prepared")
check("1c. identityのoperation_kindはMEDIA_UPLOAD", coordinator_1.calls[0][1].operation_kind, ProtectedSideEffectKind.MEDIA_UPLOAD)
check("1d. identityのeffect_siteはNEWS_STEP", coordinator_1.calls[0][1].effect_site, SideEffectSite.NEWS_STEP)
check("1e. identityのoperation_instance_keyはarticle.slug", coordinator_1.calls[0][1].operation_instance_key, "ps6-announced-20260630")
check("1f. member_run_idが伝播する", coordinator_1.calls[0][2], "member-b1")
check("1g. runtime_result.statusはAPPLIED", result_1.status, ArticleFeaturedMediaRuntimeStatus.APPLIED)
check("1h. record_confirmed()が最後に呼ばれ、media_idが伝播する", coordinator_1.calls[-1], ("confirmed", coordinator_1.calls[0][1], "member-b1", 777))
check("1i. article.featured_media_idがbindingされる", result_1.article.featured_media_id, 777)
print()


# ─── [テスト2] write-ahead ACK失敗時はupload()が一切呼ばれない ───

print("[テスト2] write-ahead ACK失敗時はupload()が一切呼ばれない（external I/O = 0）")

events_2: list[str] = []
coordinator_2 = _tracked_coordinator_with_events(events_2, fail_attempted=True)
adapters_2 = MediaUploadWriteAheadAdapters(
    enabled=True,
    image_generator=_FakeImageGenerator(),
    base_media_uploader=_FakeBaseMediaUploader(events_2),
    image_mime_type="image/png",
)
binding_2 = _make_protected_binding(adapters_2, coordinator_2)

raised_2 = None
try:
    main._apply_featured_media_step(make_article(), side_effect_binding=binding_2)
except FeaturedMediaPropagatedFailure as e:
    raised_2 = e

check_true("2a. FeaturedMediaPropagatedFailureが送出される", raised_2 is not None)
check("2b. upload()は一切呼ばれない（eventsにupload_calledが含まれない）", "upload_called" in events_2, False)
check_false("2c. record_confirmed()は呼ばれない", any(c[0] == "confirmed" for c in coordinator_2.calls))
check_true(
    "2d. carrierはraw exceptionへのcontext/causeを保持しない（__context__ is None）",
    raised_2.__context__ is None,
)
check_true("2e. carrierはcauseも保持しない（__cause__ is None）", raised_2.__cause__ is None)
print()


# ─── [テスト3] Gate OFF: record_not_applicable()のみ、他3 safety methodsはzero-call ───

print("[テスト3] Gate OFF（adapters.enabled=False）はrecord_not_applicable()のみ呼ぶ")

coordinator_3 = _FakeMediaUploadSafetyCoordinator()
adapters_3 = MediaUploadWriteAheadAdapters(enabled=False)
binding_3 = _make_protected_binding(adapters_3, coordinator_3)
result_3 = main._apply_featured_media_step(make_article(), side_effect_binding=binding_3)

check("3a. record_not_applicable()が1回だけ呼ばれる", [c[0] for c in coordinator_3.calls], ["not_applicable"])
check("3b. runtime_result.statusはDISABLED", result_3.status, ArticleFeaturedMediaRuntimeStatus.DISABLED)
check("3c. articleは未改変のまま返る（featured_media_id=0）", result_3.article.featured_media_id, 0)
print()


# ─── [テスト4] CONTINUED_WITHOUT_FEATURED_MEDIAではrecord_confirmed()を呼ばない ───

print("[テスト4] CONTINUE fallback経路（画像生成失敗）ではrecord_confirmed()を呼ばない")

events_4: list[str] = []
coordinator_4 = _tracked_coordinator_with_events(events_4)
timeout_error = OpenAIImageGenerationError("timeout", OpenAIImageGenerationErrorReason.TIMEOUT)
adapters_4 = MediaUploadWriteAheadAdapters(
    enabled=True,
    image_generator=_FakeImageGenerator(error=timeout_error),
    base_media_uploader=_FakeBaseMediaUploader(events_4),
    image_mime_type="image/png",
)
binding_4 = _make_protected_binding(adapters_4, coordinator_4)
result_4 = main._apply_featured_media_step(make_article(), side_effect_binding=binding_4)

check("4a. runtime_result.statusはCONTINUED_WITHOUT_FEATURED_MEDIA", result_4.status, ArticleFeaturedMediaRuntimeStatus.CONTINUED_WITHOUT_FEATURED_MEDIA)
check_false("4b. upload()は一切呼ばれない（画像生成自体が失敗したため）", "upload_called" in events_4)
check_false("4c. record_attempted()は呼ばれない", any(c[0] == "attempted" for c in coordinator_4.calls))
check_false("4d. record_confirmed()は呼ばれない", any(c[0] == "confirmed" for c in coordinator_4.calls))
check("4e. record_prepared()は呼ばれる（PREPARED、SAFE_TO_CONTINUE evidence）", [c[0] for c in coordinator_4.calls], ["prepared"])
print()


# ─── [テスト5] upload失敗（PROPAGATE対象）はFeaturedMediaPropagatedFailureへ ───

print("[テスト5] upload失敗（PROPAGATE対象）はFeaturedMediaPropagatedFailureへ運ばれる")


class _FailingUploader:
    def __init__(self):
        self.calls = 0

    def upload(self, image, filename):
        self.calls += 1
        raise WordPressMediaUploadError("boom", reason=WordPressMediaUploadErrorReason.SERVER_ERROR)


coordinator_5 = _FakeMediaUploadSafetyCoordinator()
failing_uploader_5 = _FailingUploader()
adapters_5 = MediaUploadWriteAheadAdapters(
    enabled=True,
    image_generator=_FakeImageGenerator(),
    base_media_uploader=failing_uploader_5,
    image_mime_type="image/png",
)
binding_5 = _make_protected_binding(adapters_5, coordinator_5)

raised_5 = None
try:
    main._apply_featured_media_step(make_article(), side_effect_binding=binding_5)
except FeaturedMediaPropagatedFailure as e:
    raised_5 = e

check_true("5a. FeaturedMediaPropagatedFailureが送出される", raised_5 is not None)
check_true("5b. record_attempted()は呼ばれた後にupload()が呼ばれる（IO_ARMED後の失敗）", any(c[0] == "attempted" for c in coordinator_5.calls))
check("5c. failing_uploaderは1回だけ呼ばれる", failing_uploader_5.calls, 1)
check_false("5d. record_confirmed()は呼ばれない（IO_ARMED+ATTEMPTEDのまま維持）", any(c[0] == "confirmed" for c in coordinator_5.calls))
print()


# ─── [テスト6] legacy bindingでは4 safety methodsのいずれも呼ばれない ───

print("[テスト6] legacy bindingでは4 safety methodsのいずれも呼ばれない")

events_6: list[str] = []


class _LegacyOrchestratorLikeRuntime:
    """既存ArticleFeaturedMediaRuntime相当の最小Fake（Gate OFF挙動を模す）。"""

    def is_available(self) -> bool:
        return False

    def apply(self, article):
        from article_featured_media_runtime import ArticleFeaturedMediaRuntimeResult
        events_6.append("legacy_apply_called")
        return ArticleFeaturedMediaRuntimeResult(article=article, status=ArticleFeaturedMediaRuntimeStatus.DISABLED)


legacy_runtime_6 = _LegacyOrchestratorLikeRuntime()
binding_6 = build_legacy_featured_media_side_effect_binding(_LEGACY_CONTEXT, legacy_runtime_6)
result_6 = main._apply_featured_media_step(make_article(), side_effect_binding=binding_6)

check("6a. legacy runtimeのapply()が呼ばれる", events_6, ["legacy_apply_called"])
check("6b. runtime_result.statusはDISABLED", result_6.status, ArticleFeaturedMediaRuntimeStatus.DISABLED)
print()


# ─── [テスト7] 未知binding型はいずれのI/O・safety methodも呼ぶ前にfail-closedする ───

print("[テスト7] 未知binding型はfail-closedする（external I/O = 0, safety method call = 0）")


@dataclass(frozen=True)
class _UnknownBinding:
    pass


raised_7 = None
try:
    main._apply_featured_media_step(make_article(), side_effect_binding=_UnknownBinding())
except SideEffectExecutionModeContractError as e:
    raised_7 = e

check_true("7a. SideEffectExecutionModeContractErrorが送出される", raised_7 is not None)
check(
    "7b. reason_codeはUNKNOWN_EXECUTION_MODE",
    raised_7.reason_code if raised_7 is not None else None,
    ExecutionModeFailureReasonCode.UNKNOWN_EXECUTION_MODE,
)
print()


# ─── [テスト8] _extract_confirmed_media_id()：15.5.1節 条件1〜4 ───

print("[テスト8] _extract_confirmed_media_id()：fail-closedな事前条件チェック")

_extract = main._extract_confirmed_media_id

article_valid = make_article()
from dataclasses import replace as _dc_replace  # noqa: E402

check("8a. featured_media_id=5（正の int）は5を返す", _extract(_dc_replace(article_valid, featured_media_id=5)), 5)
check("8b. featured_media_id=0は None を返す（アイキャッチなし）", _extract(_dc_replace(article_valid, featured_media_id=0)), None)
check("8c. featured_media_id=Noneは None を返す", _extract(_dc_replace(article_valid, featured_media_id=None)), None)
check("8d. featured_media_id=True（bool）は None を返す（bool除外）", _extract(_dc_replace(article_valid, featured_media_id=True)), None)
check("8e. ArticleDataでないobjectは None を返す", _extract(object()), None)
check("8f. featured_media_id=-1（負のint）は None を返す", _extract(_dc_replace(article_valid, featured_media_id=-1)), None)
print()


# ─── [テスト9] Codex Final Review Blocking#2: protected binding + manifest_registrar=None ───
# 既存の「registrar exists but RegisterResult.acknowledged==False」系fail-closed
# testsとは別ケース（registrar自体がMISSING）であることに注意（混同しない）。

print("[テスト9] protected binding + manifest_registrar省略はGate ON/OFFいずれもfail-closedする（Blocking#2）")

events_9a: list[str] = []
coordinator_9a = _tracked_coordinator_with_events(events_9a)
adapters_9a = MediaUploadWriteAheadAdapters(
    enabled=True,
    image_generator=_FakeImageGenerator(),
    base_media_uploader=_FakeBaseMediaUploader(events_9a),
    image_mime_type="image/png",
)
binding_9a = build_protected_featured_media_side_effect_binding(_PROTECTED_CONTEXT, coordinator_9a, adapters_9a, None)
raised_9a = None
try:
    main._apply_featured_media_step(make_article(), side_effect_binding=binding_9a)
except SideEffectExecutionModeContractError as e:
    raised_9a = e

check_true("9a. Gate ON + registrar省略はSideEffectExecutionModeContractErrorで拒否される", raised_9a is not None)
check(
    "9b. reason_codeはPROTECTED_MANIFEST_REGISTRAR_REQUIRED",
    raised_9a.reason_code if raised_9a else None,
    ExecutionModeFailureReasonCode.PROTECTED_MANIFEST_REGISTRAR_REQUIRED,
)
check("9c. Gate ON: record_prepared()は一切呼ばれない", sum(1 for c in coordinator_9a.calls if c[0] == "prepared"), 0)
check("9d. Gate ON: record_attempted()は一切呼ばれない", sum(1 for c in coordinator_9a.calls if c[0] == "attempted"), 0)
check("9e. Gate ON: upload()は一切呼ばれない（external I/O=0）", "upload_called" in events_9a, False)

coordinator_9b = _tracked_coordinator_with_events([])
adapters_9b = MediaUploadWriteAheadAdapters(enabled=False)
binding_9b = build_protected_featured_media_side_effect_binding(_PROTECTED_CONTEXT, coordinator_9b, adapters_9b, None)
raised_9b = None
try:
    main._apply_featured_media_step(make_article(), side_effect_binding=binding_9b)
except SideEffectExecutionModeContractError as e:
    raised_9b = e

check_true("9f. Gate OFF + registrar省略はSideEffectExecutionModeContractErrorで拒否される", raised_9b is not None)
check(
    "9g. reason_codeはPROTECTED_MANIFEST_REGISTRAR_REQUIRED（Gate OFF側）",
    raised_9b.reason_code if raised_9b else None,
    ExecutionModeFailureReasonCode.PROTECTED_MANIFEST_REGISTRAR_REQUIRED,
)
check("9h. Gate OFF: record_not_applicable()は一切呼ばれない", sum(1 for c in coordinator_9b.calls if c[0] == "not_applicable"), 0)
print()

print("[テスト10] legacy bindingはmanifest_registrar概念自体を持たない（互換性維持、protected判定と構造的に分離）")

check_true(
    "10a. LegacyFeaturedMediaSideEffectBindingにmanifest_registrarフィールドは存在しない",
    "manifest_registrar" not in LegacyFeaturedMediaSideEffectBinding.__dataclass_fields__,
)
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
