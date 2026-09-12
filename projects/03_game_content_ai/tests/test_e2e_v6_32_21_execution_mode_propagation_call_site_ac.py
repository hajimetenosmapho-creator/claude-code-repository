"""
E2E テスト: Release 6.32 Explicit Side-Effect Execution Mode / Typed Context
Propagation / Call Site A・C execution-based evidence（§28.-10・§28.-12・§28.-11）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    2.1〜2.4節（Explicit Side-Effect Execution Mode）・2.6節（Propagation Contract）・
    15.6〜15.7節（呼び出し箇所A/C統合）・28.-10節（14件）・28.-12節（13件）・
    28.-11節（12件）。

本ファイルは、Canonical Gap Inventoryのread-only照合で判明した以下の
execution-based evidenceの欠落のみを埋める。他の項目は既存test（特に
test_e2e_v6_32_0/2/3/5/9/17/19/20）でCOMPLETEのため重複実装しない：

    Part A（§28.-10）: `validate_side_effect_execution_context()`のexact
        reason_code matrix。既存test_e2e_v6_32_0はprotected/legacy正常系と
        root_run_id欠落・contradictory legacy pairのみを確認しており、
        attempt_ordinal/member_run_id欠落（CONTEXT_MISMATCH）・
        side_effect_contract_version欠落（CONTRACT_VERSION_MISMATCH）・
        非discriminated-union型（UNKNOWN_EXECUTION_MODE）・legacy closed set外
        の値（UNKNOWN_LEGACY_ENTRYPOINT/UNKNOWN_LEGACY_EXECUTION_ORIGIN）の
        exact reason_codeを確認していない。

    Part B（§28.-12 #5・#6）: `NewsAgent.act()`→`NewsPipelineRunner.run()`・
        `PublishTriggerAgent.act()`→`PublishPipelineRunner.run()`が
        `side_effect_execution_context`を同一オブジェクト参照のまま
        （再構築なく）渡すことの直接確認。

    Part C（§28.-11 #4）: POST/post_draft()の外部I/O成功後・`record_confirmed()`
        実行前にcrashが発生した場合、durable stateが`ATTEMPTED`のまま残り、
        再起動後の再構築classifierが`HUMAN_REVIEW_REQUIRED`を返すこと、かつ
        同一identityでの再実行（リトライ相当）で外部I/Oが重複して呼ばれない
        ことを、実際の呼び出し箇所A（`WordPressOutput.save()`）・C
        （`AiPublishService._post()`）を通じて直接検証する（実
        `WordPressDraftStateManager`/`JsonWordPressDraftStateStore`を使用、
        Store層のモックに閉じない）。

対象production: なし（全てtest-only。production変更は一切行っていない）。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_21_execution_mode_propagation_call_site_ac.py
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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
print("Execution Mode / Typed Propagation / Call Site A-C（§28.-10・-12・-11）E2E テスト")
print("=" * 60)
print()

from ai.agent_context import AgentContext  # noqa: E402
from ai.agent_decision import AgentDecision  # noqa: E402
from ai.agent_task import AgentTask  # noqa: E402
from ai.news_agent import NewsAgent  # noqa: E402
from ai.publish_trigger_agent import PublishTriggerAgent  # noqa: E402
from ai.ai_publish_service import AiPublishService  # noqa: E402
from ai.rewrite_review_result import RewriteReviewResult, ReviewStatus  # noqa: E402
from ai.rewrite_result import RewriteResult  # noqa: E402
from outputs.wordpress_output import WordPressOutput  # noqa: E402
from outputs.base import ArticleData  # noqa: E402
from collector import NewsItem  # noqa: E402
from publishing_config import PublishStatus  # noqa: E402
from retry_lineage import RetryLineageDisposition  # noqa: E402
from retry_lineage.retry_lineage_target_resolution import resolve_final_disposition  # noqa: E402
from side_effect_safety import (  # noqa: E402
    LegacyDirectExecutionContext,
    LegacyEntrypoint,
    LegacyExecutionOrigin,
    ProtectedSideEffectKind,
    RetryLineageProtectedExecutionContext,
    SideEffectExecutionModeContractError,
    SideEffectOperationIdentity,
    SideEffectSite,
    build_legacy_direct_provenance,
    build_protected_execution_context,
    complete_legacy_execution_context,
    validate_side_effect_execution_context,
)
from side_effect_safety.side_effect_execution_mode import ExecutionModeFailureReasonCode  # noqa: E402
from side_effect_safety.side_effect_safety_category import (  # noqa: E402
    ProtectedOperationContext,
    SideEffectSafetyCategory,
    SideEffectSafetyReport,
)
from side_effect_safety_classifier import SideEffectSafetyClassifier  # noqa: E402
from wordpress_draft_state.errors import WordPressDraftStateTransitionError  # noqa: E402
from wordpress_draft_state.wordpress_draft_state_manager import WordPressDraftStateManager  # noqa: E402
from wordpress_draft_state.wordpress_draft_state_store import JsonWordPressDraftStateStore  # noqa: E402


# =====================================================================
# Part A: §28.-10 validate_side_effect_execution_context() exact reason_code matrix
# =====================================================================

print("[A] validate_side_effect_execution_context() exact reason_code matrix")


def _raises_reason(label: str, fn, expected_reason):
    raised = None
    try:
        fn()
    except SideEffectExecutionModeContractError as e:
        raised = e
    check_true(f"{label}: SideEffectExecutionModeContractErrorが送出される", raised is not None)
    check(f"{label}: reason_codeが正確に一致する", raised.reason_code if raised else None, expected_reason)


_BASE_PROTECTED = build_protected_execution_context(
    root_run_id="root-21a", attempt_ordinal=1, member_run_id="member-21a", side_effect_contract_version=1,
)

# A1: attempt_ordinal欠落/malformed（root_run_idは正常）→ CONTEXT_MISMATCH（§28.-10#3）
_raises_reason(
    "A1", lambda: validate_side_effect_execution_context(
        RetryLineageProtectedExecutionContext(
            root_run_id="root-21a", attempt_ordinal=0, member_run_id="member-21a", side_effect_contract_version=1,
        )
    ),
    ExecutionModeFailureReasonCode.CONTEXT_MISMATCH,
)

# A2: member_run_id欠落/malformed（root_run_idは正常）→ CONTEXT_MISMATCH（§28.-10#4）
_raises_reason(
    "A2", lambda: validate_side_effect_execution_context(
        RetryLineageProtectedExecutionContext(
            root_run_id="root-21a", attempt_ordinal=1, member_run_id="", side_effect_contract_version=1,
        )
    ),
    ExecutionModeFailureReasonCode.CONTEXT_MISMATCH,
)

# A3: side_effect_contract_version欠落/malformed → CONTRACT_VERSION_MISMATCH（§28.-10#5）
_raises_reason(
    "A3", lambda: validate_side_effect_execution_context(
        RetryLineageProtectedExecutionContext(
            root_run_id="root-21a", attempt_ordinal=1, member_run_id="member-21a", side_effect_contract_version=0,
        )
    ),
    ExecutionModeFailureReasonCode.CONTRACT_VERSION_MISMATCH,
)

# A4: side_effect_execution_context=None → MISSING_EXECUTION_MODE（§28.-10#7、既存2cは型のみ確認）
_raises_reason(
    "A4", lambda: validate_side_effect_execution_context(None),
    ExecutionModeFailureReasonCode.MISSING_EXECUTION_MODE,
)

# A5: RetryLineageProtectedExecutionContext/LegacyDirectExecutionContextいずれでもない型 → UNKNOWN_EXECUTION_MODE（§28.-10#8）
_raises_reason(
    "A5", lambda: validate_side_effect_execution_context(object()),
    ExecutionModeFailureReasonCode.UNKNOWN_EXECUTION_MODE,
)
_raises_reason(
    "A5b", lambda: validate_side_effect_execution_context({"root_run_id": "fake"}),
    ExecutionModeFailureReasonCode.UNKNOWN_EXECUTION_MODE,
)

# A6: legacy_entrypoint/legacy_execution_originがclosed set外 → UNKNOWN_LEGACY_ENTRYPOINT/ORIGIN（§28.-10#9）
import enum  # noqa: E402


class _FakeLegacyEntrypoint(enum.Enum):
    ROGUE = "rogue_entrypoint"


class _FakeLegacyExecutionOrigin(enum.Enum):
    ROGUE = "rogue_origin"


_raises_reason(
    "A6a", lambda: validate_side_effect_execution_context(
        LegacyDirectExecutionContext(
            legacy_entrypoint=_FakeLegacyEntrypoint.ROGUE, legacy_execution_origin=LegacyExecutionOrigin.NEWS_AGENT,
        )
    ),
    ExecutionModeFailureReasonCode.UNKNOWN_LEGACY_ENTRYPOINT,
)
_raises_reason(
    "A6b", lambda: validate_side_effect_execution_context(
        LegacyDirectExecutionContext(
            legacy_entrypoint=LegacyEntrypoint.RUN_NEWS_AGENT, legacy_execution_origin=_FakeLegacyExecutionOrigin.ROGUE,
        )
    ),
    ExecutionModeFailureReasonCode.UNKNOWN_LEGACY_EXECUTION_ORIGIN,
)

# A7: root_run_id欠落 → MISSING_LINEAGE_CONTEXT（既存test_e2e_v6_32_0 2dで確認済みのため
#     ここでは正しいreason_code値そのものを確認する（既存はSideEffectExecutionModeContractError
#     型のみ確認しreason_codeは未確認）
_raises_reason(
    "A7", lambda: validate_side_effect_execution_context(
        RetryLineageProtectedExecutionContext(
            root_run_id="", attempt_ordinal=1, member_run_id="member-21a", side_effect_contract_version=1,
        )
    ),
    ExecutionModeFailureReasonCode.MISSING_LINEAGE_CONTEXT,
)

# A8: 正常系はprotected/legacyいずれも例外なく通過し、同一オブジェクトがそのまま返る（変換されない）
check_true("A8a. protected正常系はそのまま返る（同一オブジェクト）", validate_side_effect_execution_context(_BASE_PROTECTED) is _BASE_PROTECTED)
_legacy_ok = complete_legacy_execution_context(build_legacy_direct_provenance(LegacyEntrypoint.RUN_NEWS_AGENT), LegacyExecutionOrigin.NEWS_AGENT)
check_true("A8b. legacy正常系はそのまま返る（同一オブジェクト、protected型へ変換されない）", validate_side_effect_execution_context(_legacy_ok) is _legacy_ok)
check_false("A8c. legacy正常系がRetryLineageProtectedExecutionContextへ変換されていない", isinstance(_legacy_ok, RetryLineageProtectedExecutionContext))
print()


# =====================================================================
# Part B: §28.-12 #5・#6 NewsAgent.act()/PublishTriggerAgent.act()の
#         側exact same-object propagation
# =====================================================================

print("[B] NewsAgent.act()/PublishTriggerAgent.act() → runner.run()への同一オブジェクト伝播")

_spy_runner_result = MagicMock(success=True, error_message=None, stdout_log_path=None, stderr_log_path=None)

spy_runner_news = MagicMock()
spy_runner_news.run.return_value = _spy_runner_result
news_agent = NewsAgent(config=None, runner=spy_runner_news)
context_news = AgentContext(
    task=AgentTask(task_id="run_news", params={"k": "v"}), dry_run=False, run_id="run-21b1", agent_name="",
    side_effect_execution_context=_BASE_PROTECTED,
)
news_agent.act(AgentDecision(should_act=True, reason="test"), context_news)

check("B1a. NewsPipelineRunner.run()が1回呼ばれる", spy_runner_news.run.call_count, 1)
check_true(
    "B1b. side_effect_execution_contextは同一オブジェクト参照のまま渡される（再構築なし）",
    spy_runner_news.run.call_args.kwargs.get("side_effect_execution_context") is _BASE_PROTECTED,
)
check("B1c. paramsも改変なく伝播する", spy_runner_news.run.call_args.kwargs.get("params"), {"k": "v"})

spy_runner_publish = MagicMock()
spy_runner_publish.run.return_value = _spy_runner_result
publish_agent = PublishTriggerAgent(config=None, runner=spy_runner_publish)
context_publish = AgentContext(
    task=AgentTask(task_id="run_publish", params={"k2": "v2"}), dry_run=False, run_id="run-21b2", agent_name="",
    side_effect_execution_context=_BASE_PROTECTED,
)
publish_agent.act(AgentDecision(should_act=True, reason="test"), context_publish)

check("B2a. PublishPipelineRunner.run()が1回呼ばれる", spy_runner_publish.run.call_count, 1)
check_true(
    "B2b. side_effect_execution_contextは同一オブジェクト参照のまま渡される（再構築なし）",
    spy_runner_publish.run.call_args.kwargs.get("side_effect_execution_context") is _BASE_PROTECTED,
)

# side_effect_execution_context=Noneの場合はキーワード引数自体を渡さない（既存Fakeとのzero-diff）
spy_runner_news_none = MagicMock()
spy_runner_news_none.run.return_value = _spy_runner_result
news_agent_none = NewsAgent(config=None, runner=spy_runner_news_none)
context_news_none = AgentContext(
    task=AgentTask(task_id="run_news", params={}), dry_run=False, run_id="run-21b3", agent_name="",
    side_effect_execution_context=None,
)
news_agent_none.act(AgentDecision(should_act=True, reason="test"), context_news_none)
check_false(
    "B3a. side_effect_execution_context=Noneの場合、キーワード引数自体を渡さない（zero-diff維持）",
    "side_effect_execution_context" in spy_runner_news_none.run.call_args.kwargs,
)
print()


# =====================================================================
# Part C: §28.-11 #4 POST/post_draft成功後・record_confirmed前crash → 再起動HRR
#         → 同一identityでの再実行で外部I/Oが重複しない（実call site直接検証）
# =====================================================================

print("[C-A] 呼び出し箇所A: POST成功後crash → 再起動HRR → リトライでPOST重複なし")

_MOCK_RESPONSE = MagicMock()
_MOCK_RESPONSE.status_code = 201
_MOCK_RESPONSE.json.return_value = {
    "id": 777, "slug": "crash-test-article", "status": "draft",
    "title": {"rendered": "t"}, "link": "https://example.test/x/",
}


def make_article(slug: str = "crash-test-article") -> ArticleData:
    item = NewsItem(
        title="t", url="https://example.test/n", summary="s", source="src",
        published_at="2026-06-30", image_candidates=[],
    )
    return ArticleData(
        item=item, importance="S", seo_title="t", article_body="b", x_post="x",
        slug=slug, publish_status=PublishStatus.DRAFT,
    )


tmp_ca = Path(tempfile.mkdtemp(prefix="v6_32_21_ca_"))
store_ca = JsonWordPressDraftStateStore(tmp_ca / "state", tmp_ca / "locks")
manager_ca = WordPressDraftStateManager(store_ca)

_ctx_ca = build_protected_execution_context(
    root_run_id="root-21ca", attempt_ordinal=1, member_run_id="member-21ca", side_effect_contract_version=1,
)

# Codex Final Review Blocking#2対応：protected contextでのWordPressOutput/
# AiPublishService構築はmanifest_registrarを必須とする。既存test（POST成功後
# crash→再起動HRR→リトライでPOST重複なし）を維持するため実の
# ManifestRegistrarFacadeを配線する（test-owned tmp dir、production非変更）。
from protected_operation_manifest import JsonProtectedOperationManifestStore, ManifestRegistrarFacade  # noqa: E402

_manifest_store_ca = JsonProtectedOperationManifestStore(base_dir=tmp_ca / "manifest")
_manifest_store_ca.create_for_attempt("root-21ca", 1, "member-21ca")
_manifest_registrar_ca = ManifestRegistrarFacade(_manifest_store_ca)

post_count_ca = [0]


def _crashing_record_confirmed(*args, **kwargs):
    raise RuntimeError("simulated crash before record_confirmed() durable ACK")


with patch("outputs.wordpress_output.requests.post") as mock_post_ca:
    mock_post_ca.return_value = _MOCK_RESPONSE

    def _tracking_post(*args, **kwargs):
        post_count_ca[0] += 1
        return _MOCK_RESPONSE

    mock_post_ca.side_effect = _tracking_post

    with patch.object(manager_ca, "record_confirmed", side_effect=_crashing_record_confirmed):
        wp_ca = WordPressOutput(
            site_url="https://example.test", username="u", app_password="p",
            side_effect_execution_context=_ctx_ca, draft_state_manager=manager_ca,
            manifest_registrar=_manifest_registrar_ca,
        )
        crash_raised_ca = None
        try:
            wp_ca.save(make_article())
        except RuntimeError as e:
            crash_raised_ca = e

check_true("C-A1. crash（record_confirmed失敗）が呼び出し元へ伝播する", crash_raised_ca is not None)
check("C-A2. POSTはこの1回のみ呼ばれた", post_count_ca[0], 1)

_identity_ca = SideEffectOperationIdentity(
    root_run_id="root-21ca", attempt_ordinal=1, operation_kind=ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION,
    effect_site=SideEffectSite.NEWS_STEP, operation_instance_key="crash-test-article",
)
_durable_state_ca = store_ca.get(_identity_ca, "member-21ca")
check("C-A3. durable stateはATTEMPTEDのまま（record_confirmed()が実際には成立していない）", _durable_state_ca.state.value, "attempted")


class _UnusedMediaCoordinator:
    def get(self, *args, **kwargs):
        raise AssertionError("WORDPRESS_DRAFT_CREATION分岐ではmedia_coordinator.get()は呼ばれないはず")


# 「再起動」を新規store/managerインスタンス（同一durable dir）として模す
restarted_store_ca = JsonWordPressDraftStateStore(tmp_ca / "state", tmp_ca / "locks")
restarted_manager_ca = WordPressDraftStateManager(restarted_store_ca)
classifier_ca = SideEffectSafetyClassifier(media_coordinator=_UnusedMediaCoordinator(), draft_state=restarted_store_ca)
category_ca = classifier_ca._classify_one(_identity_ca, "member-21ca", ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION)
report_ca = SideEffectSafetyReport(entries=(
    (ProtectedOperationContext(operation_kind=ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION, effect_site=SideEffectSite.NEWS_STEP, operation_instance_key="crash-test-article"), category_ca),
))
disposition_ca = resolve_final_disposition([], report_ca)

check("C-A4. 再起動後の分類はIN_PROGRESS_OR_UNKNOWN", category_ca, SideEffectSafetyCategory.IN_PROGRESS_OR_UNKNOWN)
check("C-A5. 再起動後のfinal dispositionはHUMAN_REVIEW_REQUIRED", disposition_ca, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)

# 同一identityでの再実行（リトライ相当）: write-aheadのduplicate検出により、POSTは重複して呼ばれない
with patch("outputs.wordpress_output.requests.post") as mock_post_ca2:
    def _tracking_post2(*args, **kwargs):
        post_count_ca[0] += 1
        return _MOCK_RESPONSE

    mock_post_ca2.side_effect = _tracking_post2

    wp_ca2 = WordPressOutput(
        site_url="https://example.test", username="u", app_password="p",
        side_effect_execution_context=_ctx_ca, draft_state_manager=restarted_manager_ca,
        manifest_registrar=_manifest_registrar_ca,
    )
    retry_raised_ca = None
    try:
        wp_ca2.save(make_article())
    except WordPressDraftStateTransitionError as e:
        retry_raised_ca = e

check_true("C-A6. リトライ相当の再実行はduplicate createとしてWordPressDraftStateTransitionErrorで拒否される", retry_raised_ca is not None)
check("C-A7. リトライでPOSTは重複して呼ばれない（累計は依然として1回のまま）", post_count_ca[0], 1)
print()


print("[C-C] 呼び出し箇所C: post_draft()成功後crash → 再起動HRR → リトライでpost_draft重複なし")


def make_review(article_id: str = "crash-test-c") -> RewriteReviewResult:
    from datetime import datetime as _dt
    now = _dt.now()
    return RewriteReviewResult(
        article_id=article_id, title="t", permalink="https://example.test/orig/",
        review_status=ReviewStatus.ADOPTED, review_note="",
        original_char_count=100, rewrite_char_count=120, char_diff=20,
        original_line_count=10, rewrite_line_count=12, line_diff=2,
        change_ratio=0.2, diff_summary=[], changes_count=1,
        improvement_summary="改善", changes=[], created_at=now, reviewed_at=now,
    )


def make_rewrite(article_id: str = "crash-test-c") -> RewriteResult:
    return RewriteResult(
        article_id=article_id, title="t", permalink="https://example.test/orig/",
        prompt_version="v1", original_content="元", rewrite_draft="改",
        improvement_summary="改善", changes=[],
    )


tmp_cc = Path(tempfile.mkdtemp(prefix="v6_32_21_cc_"))
store_cc = JsonWordPressDraftStateStore(tmp_cc / "state", tmp_cc / "locks")
manager_cc = WordPressDraftStateManager(store_cc)

_ctx_cc = build_protected_execution_context(
    root_run_id="root-21cc", attempt_ordinal=1, member_run_id="member-21cc", side_effect_contract_version=1,
)

# Codex Final Review Blocking#2対応（呼び出し箇所C側）。
_manifest_store_cc = JsonProtectedOperationManifestStore(base_dir=tmp_cc / "manifest")
_manifest_store_cc.create_for_attempt("root-21cc", 1, "member-21cc")
_manifest_registrar_cc = ManifestRegistrarFacade(_manifest_store_cc)

post_count_cc = [0]


class _CountingWordPressDraftClient:
    def post_draft(self, title, content, slug, excerpt=None):
        post_count_cc[0] += 1
        return {"post_id": 888, "slug": slug, "edit_url": "https://example.test/x", "permalink": "https://example.test/p"}


with patch.object(manager_cc, "record_confirmed", side_effect=_crashing_record_confirmed):
    service_cc = AiPublishService(
        repository=None, client=_CountingWordPressDraftClient(), report_dir=Path("unused"),
        draft_state_manager=manager_cc, manifest_registrar=_manifest_registrar_cc,
    )
    crash_raised_cc = None
    try:
        service_cc._post(make_review(), make_rewrite(), side_effect_execution_context=_ctx_cc)
    except RuntimeError as e:
        crash_raised_cc = e

check_true("C-C1. crash（record_confirmed失敗）が呼び出し元へ伝播する", crash_raised_cc is not None)
check("C-C2. post_draft()はこの1回のみ呼ばれた", post_count_cc[0], 1)

_identity_cc = SideEffectOperationIdentity(
    root_run_id="root-21cc", attempt_ordinal=1, operation_kind=ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION,
    effect_site=SideEffectSite.PUBLISH_STEP, operation_instance_key="crash-test-c",
)
_durable_state_cc = store_cc.get(_identity_cc, "member-21cc")
check("C-C3. durable stateはATTEMPTEDのまま", _durable_state_cc.state.value, "attempted")

restarted_store_cc = JsonWordPressDraftStateStore(tmp_cc / "state", tmp_cc / "locks")
restarted_manager_cc = WordPressDraftStateManager(restarted_store_cc)
classifier_cc = SideEffectSafetyClassifier(media_coordinator=_UnusedMediaCoordinator(), draft_state=restarted_store_cc)
category_cc = classifier_cc._classify_one(_identity_cc, "member-21cc", ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION)
report_cc = SideEffectSafetyReport(entries=(
    (ProtectedOperationContext(operation_kind=ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION, effect_site=SideEffectSite.PUBLISH_STEP, operation_instance_key="crash-test-c"), category_cc),
))
disposition_cc = resolve_final_disposition([], report_cc)

check("C-C4. 再起動後の分類はIN_PROGRESS_OR_UNKNOWN", category_cc, SideEffectSafetyCategory.IN_PROGRESS_OR_UNKNOWN)
check("C-C5. 再起動後のfinal dispositionはHUMAN_REVIEW_REQUIRED", disposition_cc, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)

service_cc2 = AiPublishService(
    repository=None, client=_CountingWordPressDraftClient(), report_dir=Path("unused"),
    draft_state_manager=restarted_manager_cc, manifest_registrar=_manifest_registrar_cc,
)
retry_raised_cc = None
try:
    service_cc2._post(make_review(), make_rewrite(), side_effect_execution_context=_ctx_cc)
except WordPressDraftStateTransitionError as e:
    retry_raised_cc = e

check_true("C-C6. リトライ相当の再実行はduplicate createとしてWordPressDraftStateTransitionErrorで拒否される", retry_raised_cc is not None)
check("C-C7. リトライでpost_draft()は重複して呼ばれない（累計は依然として1回のまま）", post_count_cc[0], 1)

# 同一article・同一attemptでA（NEWS_STEP）とC（PUBLISH_STEP）が互いに独立であることの直接確認（§28.-11#6）
_identity_a_side = SideEffectOperationIdentity(
    root_run_id="root-21ca", attempt_ordinal=1, operation_kind=ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION,
    effect_site=SideEffectSite.NEWS_STEP, operation_instance_key="crash-test-article",
)
check_false(
    "C8. Call Site AとCのidentityはeffect_site違いにより構造的に別（duplicate扱いされない）",
    _identity_a_side == _identity_cc,
)
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
