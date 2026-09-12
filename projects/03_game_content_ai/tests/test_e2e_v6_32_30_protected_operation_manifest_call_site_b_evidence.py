"""
E2E テスト: Release 6.32 Phase 2 — Protected Operation Manifest 呼び出し箇所B
（main.py、MEDIA_UPLOAD）direct evidence、Gate ON/OFF

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md
    §15（Gate OFF Behavior）・§18 test#2（登録の順序保証）・#12（Gate OFF登録）・
    #21（A/B/Cのmanifest registration失敗時のzero downstream calls、本ファイルはB
    Gate ON/OFF両方を対象）。

test_e2e_v6_32_29（呼び出し箇所A/C）を補完し、呼び出し箇所B
（`main._apply_featured_media_step()`、MEDIA_UPLOAD）自身のproduction codeを
直接駆動して、manifest登録がGate ON/OFFいずれの場合も既存write-ahead
（record_prepared()/record_not_applicable()）より先に完了すること、manifest
登録失敗時はGate ON/OFFいずれの場合も既存write-ahead・外部I/O（upload()）が
zero-callであることを証明する。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_30_protected_operation_manifest_call_site_b_evidence.py
"""
from __future__ import annotations

import sys
import tempfile
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


print("=" * 70)
print("Protected Operation Manifest — 呼び出し箇所B（media upload、Gate ON/OFF）direct evidence")
print("=" * 70)
print()

import main  # noqa: E402
from outputs.base import ArticleData  # noqa: E402
from collector import NewsItem  # noqa: E402
from publishing_config import PublishStatus  # noqa: E402
from ai_image_generation import GeneratedImage  # noqa: E402
from wordpress_media import MediaUploadResult  # noqa: E402
from side_effect_safety import (  # noqa: E402
    ProtectedSideEffectKind,
    build_protected_execution_context,
)
from side_effect_safety.errors import MediaUploadSafetyIOError  # noqa: E402
from side_effect_safety.media_upload_write_ahead_wiring import (  # noqa: E402
    MediaUploadWriteAheadAdapters,
    build_protected_featured_media_side_effect_binding,
)
from protected_operation_manifest import (  # noqa: E402
    JsonProtectedOperationManifestStore,
    ManifestRegistrarFacade,
    ProtectedOperationManifestContractViolationError,
    ProtectedOperationManifestIOError,
)

tmp_dirs: list[Path] = []


def make_manifest_store() -> JsonProtectedOperationManifestStore:
    tmp_root = Path(tempfile.mkdtemp())
    tmp_dirs.append(tmp_root)
    return JsonProtectedOperationManifestStore(base_dir=tmp_root / "manifest")


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


class _FakeMediaUploadSafetyCoordinator:
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


class _FakeImageGenerator:
    def generate(self, prompt):
        return GeneratedImage(image_bytes=b"\x89PNG-fake-bytes", mime_type="image/png")


class _FakeBaseMediaUploader:
    def __init__(self, events: list, media_id: int = 777):
        self._events = events
        self._media_id = media_id

    def upload(self, image, filename):
        self._events.append("upload_called")
        return MediaUploadResult(media_id=self._media_id, source_url="https://example.test/i.png", mime_type="image/png")


class _FailingManifestRegistrarFacade:
    def __init__(self):
        self.calls: list[tuple] = []

    def register(self, root_run_id, attempt_ordinal, member_run_id, entry):
        self.calls.append((root_run_id, attempt_ordinal, member_run_id, entry))
        raise ProtectedOperationManifestIOError("simulated manifest registration durable ACK failure")


def _context(root_run_id: str) -> "object":
    return build_protected_execution_context(
        root_run_id=root_run_id, attempt_ordinal=1, member_run_id=f"{root_run_id}-member",
        side_effect_contract_version=1,
    )


# =====================================================================
# グループB1：Gate ON（record_prepared()経路）
# =====================================================================
print("[グループB1] Gate ON — manifest登録の順序保証・失敗時zero-call")

manifest_store_on1 = make_manifest_store()
manifest_store_on1.create_for_attempt("root-b30on1", 1, "root-b30on1-member")
registrar_on1 = ManifestRegistrarFacade(manifest_store_on1)
events_on1: list[str] = []
coordinator_on1 = _FakeMediaUploadSafetyCoordinator()

_orig_register_on1 = registrar_on1.register
def _tracked_register_on1(*args, **kwargs):
    events_on1.append("registered")
    return _orig_register_on1(*args, **kwargs)
registrar_on1.register = _tracked_register_on1

_orig_prepared_on1 = coordinator_on1.record_prepared
def _tracked_prepared_on1(identity, member_run_id):
    events_on1.append("prepared")
    return _orig_prepared_on1(identity, member_run_id)
coordinator_on1.record_prepared = _tracked_prepared_on1

adapters_on1 = MediaUploadWriteAheadAdapters(
    enabled=True, image_generator=_FakeImageGenerator(),
    base_media_uploader=_FakeBaseMediaUploader(events_on1), image_mime_type="image/png",
)
binding_on1 = build_protected_featured_media_side_effect_binding(
    _context("root-b30on1"), coordinator_on1, adapters_on1, registrar_on1,
)
main._apply_featured_media_step(make_article(), side_effect_binding=binding_on1)

check("B1a. Gate ON: 呼び出し順序はregistered→prepared→upload_called（manifest登録が既存write-aheadより先）",
      events_on1, ["registered", "prepared", "upload_called"])
entries_on1 = manifest_store_on1.list_for_attempt("root-b30on1", 1, "root-b30on1-member")
check("B1b. manifestへMEDIA_UPLOADのentryが1件登録される", len(entries_on1), 1)
if entries_on1:
    check("B1c. entry.operation_kind=MEDIA_UPLOAD", entries_on1[0].operation_kind, ProtectedSideEffectKind.MEDIA_UPLOAD)

# manifest登録失敗 → record_prepared()・record_attempted()・upload()いずれもzero-call
manifest_store_on2 = make_manifest_store()  # create_for_attempt()しない＝register()は必ず失敗する
registrar_on2 = _FailingManifestRegistrarFacade()
coordinator_on2 = _FakeMediaUploadSafetyCoordinator()
events_on2: list[str] = []
adapters_on2 = MediaUploadWriteAheadAdapters(
    enabled=True, image_generator=_FakeImageGenerator(),
    base_media_uploader=_FakeBaseMediaUploader(events_on2), image_mime_type="image/png",
)
binding_on2 = build_protected_featured_media_side_effect_binding(
    _context("root-b30on2"), coordinator_on2, adapters_on2, registrar_on2,
)
raised_on2 = None
try:
    main._apply_featured_media_step(make_article(), side_effect_binding=binding_on2)
except ProtectedOperationManifestIOError:
    raised_on2 = "ProtectedOperationManifestIOError"

check("B2a. Gate ON: manifest登録失敗は呼び出し元へ伝播する（fail-closed）", raised_on2, "ProtectedOperationManifestIOError")
check("B2b. Gate ON: manifest登録失敗時、record_prepared()の呼び出し回数=0",
      len([c for c in coordinator_on2.calls if c[0] == "prepared"]), 0)
check("B2c. Gate ON: manifest登録失敗時、record_attempted()の呼び出し回数=0",
      len([c for c in coordinator_on2.calls if c[0] == "attempted"]), 0)
check("B2d. Gate ON: manifest登録失敗時、upload()の呼び出し回数=0（external I/O = 0）",
      len(events_on2), 0)
print()


# =====================================================================
# グループB2：Gate OFF（record_not_applicable()経路）
# =====================================================================
print("[グループB2] Gate OFF — manifest登録の順序保証・失敗時zero-call")

manifest_store_off1 = make_manifest_store()
manifest_store_off1.create_for_attempt("root-b30off1", 1, "root-b30off1-member")
registrar_off1 = ManifestRegistrarFacade(manifest_store_off1)
events_off1: list[str] = []
coordinator_off1 = _FakeMediaUploadSafetyCoordinator()

_orig_register_off1 = registrar_off1.register
def _tracked_register_off1(*args, **kwargs):
    events_off1.append("registered")
    return _orig_register_off1(*args, **kwargs)
registrar_off1.register = _tracked_register_off1

_orig_not_applicable_off1 = coordinator_off1.record_not_applicable
def _tracked_not_applicable_off1(identity, member_run_id):
    events_off1.append("not_applicable")
    return _orig_not_applicable_off1(identity, member_run_id)
coordinator_off1.record_not_applicable = _tracked_not_applicable_off1

adapters_off1 = MediaUploadWriteAheadAdapters(enabled=False)  # Gate OFF
binding_off1 = build_protected_featured_media_side_effect_binding(
    _context("root-b30off1"), coordinator_off1, adapters_off1, registrar_off1,
)
main._apply_featured_media_step(make_article(), side_effect_binding=binding_off1)

check("B3a. Gate OFF: 呼び出し順序はregistered→not_applicable（manifest登録が既存write-aheadより先）",
      events_off1, ["registered", "not_applicable"])
check_true("B3b. Gate OFF: record_prepared()・record_attempted()は呼ばれない",
           all(c[0] not in ("prepared", "attempted") for c in coordinator_off1.calls))
entries_off1 = manifest_store_off1.list_for_attempt("root-b30off1", 1, "root-b30off1-member")
check("B3c. Gate OFFでもmanifestへMEDIA_UPLOADのentryが1件登録される（NOT_APPLICABLE経由でHRRを誘発しないための記録）",
      len(entries_off1), 1)

# manifest登録失敗 → record_not_applicable()がzero-call
registrar_off2 = _FailingManifestRegistrarFacade()
coordinator_off2 = _FakeMediaUploadSafetyCoordinator()
adapters_off2 = MediaUploadWriteAheadAdapters(enabled=False)
binding_off2 = build_protected_featured_media_side_effect_binding(
    _context("root-b30off2"), coordinator_off2, adapters_off2, registrar_off2,
)
raised_off2 = None
try:
    main._apply_featured_media_step(make_article(), side_effect_binding=binding_off2)
except ProtectedOperationManifestIOError:
    raised_off2 = "ProtectedOperationManifestIOError"

check("B4a. Gate OFF: manifest登録失敗は呼び出し元へ伝播する（fail-closed）", raised_off2, "ProtectedOperationManifestIOError")
check("B4b. Gate OFF: manifest登録失敗時、record_not_applicable()の呼び出し回数=0",
      len(coordinator_off2.calls), 0)
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
