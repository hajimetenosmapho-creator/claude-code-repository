"""
E2E テスト: Release 6.32 Phase 2 — Protected Operation Manifest 呼び出し箇所A/C
direct evidence ＋ manifest store direct evidence

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md
    §18 test#2（登録の順序保証）・#10（member_run_id不一致）・#14（Manifest read時の
    IOError、3種×2経路のうち本ファイルはstore層を直接検証）・#21（A/B/Cのmanifest
    registration失敗時のzero downstream calls、本ファイルはA/Cを対象）・#1
    （冪等性、documentation cleanup：旧「#6」表記はRound 9再編前の番号の
    誤記であり#1が正）・#9（Manifest空の正常runでHRRを誘発しない）。

test_e2e_v6_32_27（RetryExecutor/RetryLineageManager側の実チェーン）を補完し、
呼び出し箇所A（wordpress_output.py）・C（ai_publish_service.py）自身の実装コード
（Fakeではなくproduction class）を直接駆動して、manifest登録が既存write-ahead・
外部I/Oより先に完了すること、manifest登録失敗時は既存write-ahead・外部I/Oのいずれも
zero-callであることを証明する。

呼び出し箇所B（main.py `_apply_featured_media_step()`）のGate ON/OFF fault
injection、および3種IOErrorのうちtrue filesystem I/O failureの再現は、production
remediation reportのresidual concernとして別途記録する（本ファイルのscopeには
含まない）。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_29_protected_operation_manifest_call_site_evidence.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

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
print("Protected Operation Manifest — 呼び出し箇所A/C direct evidence ＋ store direct evidence")
print("=" * 70)
print()

from outputs.wordpress_output import WordPressOutput  # noqa: E402
from outputs.base import ArticleData  # noqa: E402
from collector import NewsItem  # noqa: E402
from publishing_config import PublishStatus  # noqa: E402
from side_effect_safety import (  # noqa: E402
    ProtectedSideEffectKind,
    SideEffectSite,
    build_protected_execution_context,
)
from wordpress_draft_state.errors import WordPressDraftStateTransitionError  # noqa: E402
from ai.ai_publish_service import AiPublishService  # noqa: E402
from ai.rewrite_review_result import RewriteReviewResult, ReviewStatus  # noqa: E402
from ai.rewrite_result import RewriteResult  # noqa: E402
from protected_operation_manifest import (  # noqa: E402
    JsonProtectedOperationManifestStore,
    ManifestRegistrarFacade,
    ProtectedOperationManifestContractViolationError,
    ProtectedOperationManifestIOError,
    ProtectedOperationManifestNotFoundError,
    build_manifest_entry,
)
from side_effect_safety.side_effect_safety_category import ProtectedOperationContext, SideEffectSafetyReport  # noqa: E402

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


def make_review(article_id: str = "test-art") -> RewriteReviewResult:
    now = datetime.now()
    return RewriteReviewResult(
        article_id=article_id, title="タイトル", permalink="https://example.test/orig/",
        review_status=ReviewStatus.ADOPTED, review_note="",
        original_char_count=100, rewrite_char_count=120, char_diff=20,
        original_line_count=10, rewrite_line_count=12, line_diff=2,
        change_ratio=0.2, diff_summary=[], changes_count=1,
        improvement_summary="改善", changes=[], created_at=now, reviewed_at=now,
    )


def make_rewrite(article_id: str = "test-art") -> RewriteResult:
    return RewriteResult(
        article_id=article_id, title="タイトル", permalink="https://example.test/orig/",
        prompt_version="v1", original_content="元本文", rewrite_draft="改善版本文",
        improvement_summary="改善", changes=[],
    )


_MOCK_RESPONSE = MagicMock()
_MOCK_RESPONSE.status_code = 201
_MOCK_RESPONSE.json.return_value = {
    "id": 555, "slug": "ps6-announced-20260630", "status": "draft",
    "title": {"rendered": "PS6が正式発表"}, "link": "https://example.test/ps6/",
}


class _FakeDraftStateManager:
    def __init__(self, fail_attempted: bool = False):
        self.calls: list[tuple] = []
        self._fail_attempted = fail_attempted

    def record_attempted(self, identity, member_run_id):
        self.calls.append(("attempted", identity, member_run_id))
        if self._fail_attempted:
            raise WordPressDraftStateTransitionError("simulated write-ahead ACK failure")

    def record_confirmed(self, identity, member_run_id, wp_post_id):
        self.calls.append(("confirmed", identity, member_run_id, wp_post_id))


class _FailingManifestRegistrarFacade:
    """register()が常に失敗した状態を模す（durable ACK failure相当）。"""

    def __init__(self):
        self.calls: list[tuple] = []

    def register(self, root_run_id, attempt_ordinal, member_run_id, entry):
        self.calls.append((root_run_id, attempt_ordinal, member_run_id, entry))
        raise ProtectedOperationManifestIOError("simulated manifest registration durable ACK failure")


_PROTECTED_CONTEXT_A = build_protected_execution_context(
    root_run_id="root-a29", attempt_ordinal=1, member_run_id="member-a29",
    side_effect_contract_version=1,
)


# =====================================================================
# グループA：呼び出し箇所A（wordpress_output.py、production class直接駆動）
# =====================================================================
print("[グループA] 呼び出し箇所A（WordPressOutput.save()）manifest registration evidence")

manifest_store_a1 = make_manifest_store()
manifest_store_a1.create_for_attempt("root-a29", 1, "member-a29")  # Step 0（admission相当）
registrar_a1 = ManifestRegistrarFacade(manifest_store_a1)
draft_mgr_a1 = _FakeDraftStateManager()
events_a1: list[str] = []

_orig_register_a1 = registrar_a1.register
def _tracked_register_a1(*args, **kwargs):
    events_a1.append("registered")
    return _orig_register_a1(*args, **kwargs)
registrar_a1.register = _tracked_register_a1

_orig_attempted_a1 = draft_mgr_a1.record_attempted
def _tracked_attempted_a1(identity, member_run_id):
    events_a1.append("attempted")
    return _orig_attempted_a1(identity, member_run_id)
draft_mgr_a1.record_attempted = _tracked_attempted_a1

def _tracking_post_a1(*args, **kwargs):
    events_a1.append("post_called")
    return _MOCK_RESPONSE

with patch("outputs.wordpress_output.requests.post", side_effect=_tracking_post_a1):
    wp_a1 = WordPressOutput(
        site_url="https://example.test", username="u", app_password="p",
        side_effect_execution_context=_PROTECTED_CONTEXT_A,
        draft_state_manager=draft_mgr_a1, manifest_registrar=registrar_a1,
    )
    wp_a1.save(make_article())

check("A1. 呼び出し順序はregistered→attempted→post_called（manifest登録が既存write-aheadより先）",
      events_a1, ["registered", "attempted", "post_called"])

entries_a1 = manifest_store_a1.list_for_attempt("root-a29", 1, "member-a29")
check("A2. manifestへWORDPRESS_DRAFT_CREATIONのentryが1件登録される", len(entries_a1), 1)
if entries_a1:
    check("A3. entry.operation_kind=WORDPRESS_DRAFT_CREATION", entries_a1[0].operation_kind, ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION)
    check("A4. entry.effect_site=NEWS_STEP", entries_a1[0].effect_site, SideEffectSite.NEWS_STEP)
    check("A5. entry.operation_instance_key=article.slug", entries_a1[0].operation_instance_key, "ps6-announced-20260630")

# manifest登録失敗 → record_attempted()・requests.post()いずれもzero-call
registrar_a2 = _FailingManifestRegistrarFacade()
draft_mgr_a2 = _FakeDraftStateManager()
post_called_a2 = False
def _post_should_not_be_called_a2(*args, **kwargs):
    global post_called_a2
    post_called_a2 = True
    return _MOCK_RESPONSE

wp_a2 = WordPressOutput(
    site_url="https://example.test", username="u", app_password="p",
    side_effect_execution_context=build_protected_execution_context(
        root_run_id="root-a29b", attempt_ordinal=1, member_run_id="member-a29b",
        side_effect_contract_version=1,
    ),
    draft_state_manager=draft_mgr_a2, manifest_registrar=registrar_a2,
)
raised_a2 = None
with patch("outputs.wordpress_output.requests.post", side_effect=_post_should_not_be_called_a2):
    try:
        wp_a2.save(make_article())
    except ProtectedOperationManifestIOError:
        raised_a2 = "ProtectedOperationManifestIOError"

check("A6. manifest登録失敗は呼び出し元へ伝播する（fail-closed）", raised_a2, "ProtectedOperationManifestIOError")
check("A7. manifest登録失敗時、record_attempted()の呼び出し回数=0", len(draft_mgr_a2.calls), 0)
check_false("A8. manifest登録失敗時、requests.post()は一切呼ばれない（external I/O = 0）", post_called_a2)
print()


# =====================================================================
# グループB：呼び出し箇所C（ai_publish_service.py、production class直接駆動）
# =====================================================================
print("[グループB] 呼び出し箇所C（AiPublishService._post()）manifest registration evidence")


class _FakeWordPressDraftClient:
    def __init__(self, events=None):
        self.calls: list[dict] = []
        self._events = events

    def post_draft(self, title, content, slug, excerpt=None):
        self.calls.append({"title": title, "content": content, "slug": slug})
        if self._events is not None:
            self._events.append("post_called")
        return dict(_MOCK_RESPONSE.json.return_value, post_id=555)


_PROTECTED_CONTEXT_C = build_protected_execution_context(
    root_run_id="root-c29", attempt_ordinal=1, member_run_id="member-c29",
    side_effect_contract_version=1,
)

manifest_store_b1 = make_manifest_store()
manifest_store_b1.create_for_attempt("root-c29", 1, "member-c29")  # Step 0（admission相当）
registrar_b1 = ManifestRegistrarFacade(manifest_store_b1)
draft_mgr_b1 = _FakeDraftStateManager()
events_b1: list[str] = []

_orig_register_b1 = registrar_b1.register
def _tracked_register_b1(*args, **kwargs):
    events_b1.append("registered")
    return _orig_register_b1(*args, **kwargs)
registrar_b1.register = _tracked_register_b1

_orig_attempted_b1 = draft_mgr_b1.record_attempted
def _tracked_attempted_b1(identity, member_run_id):
    events_b1.append("attempted")
    return _orig_attempted_b1(identity, member_run_id)
draft_mgr_b1.record_attempted = _tracked_attempted_b1

client_b1 = _FakeWordPressDraftClient(events=events_b1)
service_b1 = AiPublishService(
    repository=None, client=client_b1, report_dir=Path("unused"),
    draft_state_manager=draft_mgr_b1, manifest_registrar=registrar_b1,
)
service_b1._post(make_review("art-b1"), make_rewrite("art-b1"), side_effect_execution_context=_PROTECTED_CONTEXT_C)

check("B1. 呼び出し順序はregistered→attempted→post_called", events_b1, ["registered", "attempted", "post_called"])
entries_b1 = manifest_store_b1.list_for_attempt("root-c29", 1, "member-c29")
check("B2. manifestへWORDPRESS_DRAFT_CREATIONのentryが1件登録される", len(entries_b1), 1)
if entries_b1:
    check("B3. entry.effect_site=PUBLISH_STEP", entries_b1[0].effect_site, SideEffectSite.PUBLISH_STEP)
    check("B4. entry.operation_instance_key=review.article_id", entries_b1[0].operation_instance_key, "art-b1")

# manifest登録失敗 → record_attempted()・post_draft()いずれもzero-call
registrar_b2 = _FailingManifestRegistrarFacade()
draft_mgr_b2 = _FakeDraftStateManager()
client_b2 = _FakeWordPressDraftClient()
service_b2 = AiPublishService(
    repository=None, client=client_b2, report_dir=Path("unused"),
    draft_state_manager=draft_mgr_b2, manifest_registrar=registrar_b2,
)
raised_b2 = None
try:
    service_b2._post(
        make_review("art-b2"), make_rewrite("art-b2"),
        side_effect_execution_context=build_protected_execution_context(
            root_run_id="root-c29b", attempt_ordinal=1, member_run_id="member-c29b",
            side_effect_contract_version=1,
        ),
    )
except ProtectedOperationManifestIOError:
    raised_b2 = "ProtectedOperationManifestIOError"

check("B5. manifest登録失敗は呼び出し元へ伝播する（fail-closed）", raised_b2, "ProtectedOperationManifestIOError")
check("B6. manifest登録失敗時、record_attempted()の呼び出し回数=0", len(draft_mgr_b2.calls), 0)
check("B7. manifest登録失敗時、post_draft()の呼び出し回数=0", len(client_b2.calls), 0)
print()


# =====================================================================
# グループC：manifest store direct evidence（member_run_id不一致・冪等性・
# corruption/IOError・vacuous manifest）
# =====================================================================
print("[グループC] Protected Operation Manifest store direct evidence")

# C1：登録の冪等性（同一identityを2回登録してもentriesが1件のまま）
store_c1 = make_manifest_store()
store_c1.create_for_attempt("root-c1", 1, "member-c1")
entry_c1 = build_manifest_entry(ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION, SideEffectSite.NEWS_STEP, "slug-c1")
store_c1.register("root-c1", 1, "member-c1", entry_c1)
store_c1.register("root-c1", 1, "member-c1", entry_c1)  # 2回目（同一identity）
check("C1. 同一identityを2回登録してもentriesは1件のまま（冪等性）",
      len(store_c1.list_for_attempt("root-c1", 1, "member-c1")), 1)

# C2：member_run_id不一致（既存レコードとは異なるmember_run_idでの登録試行）。
# Round 9設計（永続化キーがroot_run_id・attempt_ordinal・member_run_idの3要素）
# では、異なるmember_run_idは構造的に別ファイル（別キー）を指すため、
# 「mismatch」は「not found」という形で観測される——registerされた3要素の
# うち1つでも異なれば、対応する既存レコードへは到達できない、という
# fail-closed性そのものは維持される（副作用なし）ことを確認する。
store_c2 = make_manifest_store()
store_c2.create_for_attempt("root-c2", 1, "member-c2-correct")
result_c2 = store_c2.register(
    "root-c2", 1, "member-c2-WRONG",
    build_manifest_entry(ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION, SideEffectSite.NEWS_STEP, "slug-c2"),
)
check_false(
    "C2a. 異なるmember_run_idでの登録試行はacknowledged=False"
    "（3要素キー設計では別ファイル＝not foundとして観測される）",
    result_c2.acknowledged,
)
check_true("C2b. reasonに理由が記録される（空文字列ではない）", bool(result_c2.reason))
check("C2c. 不一致登録試行後も正しいmember_run_idのレコードのentriesは空のまま（副作用なし）",
      len(store_c2.list_for_attempt("root-c2", 1, "member-c2-correct")), 0)

# C3：list_for_attempt()のNotFoundError（レコード非存在）
store_c3 = make_manifest_store()
raised_c3 = None
try:
    store_c3.list_for_attempt("root-c3-nonexistent", 1, "member-c3")
except ProtectedOperationManifestNotFoundError:
    raised_c3 = "NotFoundError"
check("C3. レコード非存在時はProtectedOperationManifestNotFoundError（空tupleを返さない）", raised_c3, "NotFoundError")

# C4：list_for_attempt()のContractViolationError（schema破損：不正なJSON）
store_c4 = make_manifest_store()
store_c4.create_for_attempt("root-c4", 1, "member-c4")
path_c4 = store_c4._path_for("root-c4", 1, "member-c4")
path_c4.write_text("{not valid json", encoding="utf-8")
raised_c4 = None
try:
    store_c4.list_for_attempt("root-c4", 1, "member-c4")
except ProtectedOperationManifestContractViolationError:
    raised_c4 = "ContractViolationError"
check("C4. 破損JSON（parse失敗）はProtectedOperationManifestContractViolationError", raised_c4, "ContractViolationError")

# C5：list_for_attempt()のContractViolationError（不明なenum値）
store_c5 = make_manifest_store()
store_c5.create_for_attempt("root-c5", 1, "member-c5")
path_c5 = store_c5._path_for("root-c5", 1, "member-c5")
import json as _json
doc_c5 = _json.loads(path_c5.read_text(encoding="utf-8"))
doc_c5["entries"] = [{
    "operation_kind": "unknown_kind_not_in_closed_set",
    "effect_site": "news_step", "operation_instance_key": "x", "registered_at": "2026-01-01T00:00:00+00:00",
}]
path_c5.write_text(_json.dumps(doc_c5), encoding="utf-8")
raised_c5 = None
try:
    store_c5.list_for_attempt("root-c5", 1, "member-c5")
except ProtectedOperationManifestContractViolationError:
    raised_c5 = "ContractViolationError"
check("C5. 不明なoperation_kind（closed set外）はProtectedOperationManifestContractViolationError", raised_c5, "ContractViolationError")

# C6：list_for_attempt()のIOError（真のfilesystem I/O failure）
store_c6 = make_manifest_store()
store_c6.create_for_attempt("root-c6", 1, "member-c6")
raised_c6 = None
with patch("pathlib.Path.read_text", side_effect=OSError("simulated filesystem I/O failure")):
    try:
        store_c6.list_for_attempt("root-c6", 1, "member-c6")
    except ProtectedOperationManifestIOError:
        raised_c6 = "IOError"
check("C6. 真のfilesystem I/O failureはProtectedOperationManifestIOError（corruptionと区別）", raised_c6, "IOError")

# C7：Manifest空（正常0件）→ classify()がNOT_APPLICABLE（vacuous-safe）を返す
store_c7 = make_manifest_store()
store_c7.create_for_attempt("root-c7", 1, "member-c7")
entries_c7 = store_c7.list_for_attempt("root-c7", 1, "member-c7")
check("C7a. genuinely 0件のNEWS run相当で、entries=()", entries_c7, ())
operations_c7 = [
    ProtectedOperationContext(e.operation_kind, e.effect_site, e.operation_instance_key) for e in entries_c7
]
report_c7 = SideEffectSafetyReport(entries=())
check(
    "C7b. operations=[]相当のSideEffectSafetyReport.worst_case()はNOT_APPLICABLE"
    "（「正常runを恒常的にHRRへ落とさない」ことの直接的な回帰テスト）",
    report_c7.worst_case().value, "not_applicable",
)
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
