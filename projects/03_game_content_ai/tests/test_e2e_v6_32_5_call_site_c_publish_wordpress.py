"""
E2E テスト: v6.32.5 呼び出し箇所C（PUBLISH / AiPublishService._post()）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    15.6節（呼び出し箇所Cの統合）・22.3.3節（Exact Integration Points）・
    22.3.12節（PublishStepExecutorのauthoritative validation boundary化）・
    22.3.13節(1)（PublishPipelineRunnerのcontract-error carve-out）。

sub-milestone 5のdirect tests。以下を検証する：
    (a) protected write-ahead ACK確認前にpost_draft()（実I/O）が呼ばれない
    (b) write-ahead ACK失敗時はexternal I/O = 0
    (c) side_effect_execution_context欠落/不正時はexternal I/O = 0
    (d) protected時にdraft_state_manager欠落ならexternal I/O前にfail-closed
    (e) POST成功時のみrecord_confirmed()が呼ばれる
    (f) POST失敗時はrecord_confirmed()を呼ばない
    (g) legacy経路は既存external behaviorを維持し、4 safety methodsへ一切触れない
    (h) identity fields（operation_kind/effect_site/operation_instance_key/
        root_run_id/attempt_ordinal）が仕様どおり
    (i) contract errorがnormal failureへ変換されない
        （PublishStepExecutor・PublishPipelineRunnerの両方）
    (j) queue/scheduler関連パッケージへの新規依存が発生していない

実行方法:
    cd projects/03_game_content_ai
    .\\venv\\Scripts\\python.exe tests\\test_e2e_v6_32_5_call_site_c_publish_wordpress.py
"""
import ast
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

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
print("v6.32.5 呼び出し箇所C（PUBLISH / AiPublishService._post()）E2E テスト")
print("=" * 60)
print()

from ai.ai_publish_service import AiPublishService, NullAiPublishService  # noqa: E402
from ai.rewrite_review_result import RewriteReviewResult, ReviewStatus  # noqa: E402
from ai.rewrite_result import RewriteResult  # noqa: E402
from ai.workflow_step_executor import PublishStepExecutor  # noqa: E402
from ai.workflow_context import WorkflowContext  # noqa: E402
from pipeline.publish_pipeline_runner import PublishPipelineRunner  # noqa: E402
from side_effect_safety import (  # noqa: E402
    ExecutionModeFailureReasonCode,
    LegacyEntrypoint,
    LegacyExecutionOrigin,
    ProtectedSideEffectKind,
    SideEffectExecutionModeContractError,
    SideEffectSite,
    build_legacy_direct_provenance,
    build_protected_execution_context,
    complete_legacy_execution_context,
)
from wordpress_draft_state.errors import WordPressDraftStateTransitionError  # noqa: E402


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


_LEGACY_CONTEXT = complete_legacy_execution_context(
    build_legacy_direct_provenance(LegacyEntrypoint.RUN_AI_PUBLISH),
    LegacyExecutionOrigin.AI_PUBLISH_DIRECT,
)

_PROTECTED_CONTEXT = build_protected_execution_context(
    root_run_id="root-c1", attempt_ordinal=1, member_run_id="member-c1",
    side_effect_contract_version=1,
)

# Codex Final Review Blocking#2対応：protected contextでのAiPublishService._post()は
# manifest_registrarを必須とする。既存test（write-ahead-before-I/O契約等）を
# 維持するため実のManifestRegistrarFacadeを配線する（test-owned tmp dir、
# production非変更）。admission相当のcreate_for_attempt()を先に行う。
import tempfile  # noqa: E402
from protected_operation_manifest import JsonProtectedOperationManifestStore, ManifestRegistrarFacade  # noqa: E402

_manifest_store_c = JsonProtectedOperationManifestStore(base_dir=Path(tempfile.mkdtemp()) / "manifest")
_manifest_store_c.create_for_attempt("root-c1", 1, "member-c1")
_manifest_registrar_c = ManifestRegistrarFacade(_manifest_store_c)

_SUCCESS_RESPONSE = {
    "post_id": 555, "slug": "test-art-rewrite-20260630",
    "edit_url": "https://example.test/wp-admin/post.php?post=555",
    "permalink": "https://example.test/test-art-rewrite/",
}


class _FakeWordPressDraftClient:
    def __init__(self, *, response=None, error: Exception | None = None, events: list | None = None):
        self.calls: list[dict] = []
        self._response = response if response is not None else dict(_SUCCESS_RESPONSE)
        self._error = error
        self._events = events

    def post_draft(self, title, content, slug, excerpt=None):
        self.calls.append({"title": title, "content": content, "slug": slug})
        if self._events is not None:
            self._events.append("post_called")
        if self._error is not None:
            raise self._error
        return self._response


class _FakeDraftStateManager:
    def __init__(self, *, fail_attempted: bool = False, events: list | None = None):
        self.calls: list[tuple] = []
        self._fail_attempted = fail_attempted
        self._events = events

    def record_attempted(self, identity, member_run_id):
        self.calls.append(("attempted", identity, member_run_id))
        if self._events is not None:
            self._events.append("attempted")
        if self._fail_attempted:
            raise WordPressDraftStateTransitionError("simulated write-ahead ACK failure")

    def record_confirmed(self, identity, member_run_id, wp_post_id):
        self.calls.append(("confirmed", identity, member_run_id, wp_post_id))


class _RaisingDraftStateManager:
    """legacy経路では一切呼ばれてはならないことを確認するための、
    呼ばれたら即fail-closedするFake。"""

    def record_attempted(self, identity, member_run_id):
        raise AssertionError("legacy contextではrecord_attempted()が呼ばれてはならない")

    def record_confirmed(self, identity, member_run_id, wp_post_id):
        raise AssertionError("legacy contextではrecord_confirmed()が呼ばれてはならない")


def make_service(client, draft_state_manager=None, manifest_registrar=None) -> AiPublishService:
    return AiPublishService(
        repository=None, client=client, report_dir=Path("unused"),
        draft_state_manager=draft_state_manager, manifest_registrar=manifest_registrar,
    )


# ─── [テスト1] write-ahead-before-I/O契約 ───

print("[テスト1] write-ahead-before-I/O契約（record_attempted→post_draftの順序）")

events_1: list[str] = []
draft_mgr_1 = _FakeDraftStateManager(events=events_1)
client_1 = _FakeWordPressDraftClient(events=events_1)
service_1 = make_service(client_1, draft_mgr_1, manifest_registrar=_manifest_registrar_c)

result_1 = service_1._post(make_review(), make_rewrite(), side_effect_execution_context=_PROTECTED_CONTEXT)

check("1a. 呼び出し順序はattempted→post_called", events_1, ["attempted", "post_called"])
check("1b. record_attempted()にProtected contextのidentityが渡される",
      draft_mgr_1.calls[0][1].operation_kind, ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION)
check("1c. record_attempted()のeffect_siteはPUBLISH_STEP", draft_mgr_1.calls[0][1].effect_site, SideEffectSite.PUBLISH_STEP)
check("1d. identity.operation_instance_keyはreview.article_id（new_slugではない）",
      draft_mgr_1.calls[0][1].operation_instance_key, "test-art")
check("1e. identity.root_run_idがcontextから伝播する", draft_mgr_1.calls[0][1].root_run_id, "root-c1")
check("1f. identity.attempt_ordinalがcontextから伝播する", draft_mgr_1.calls[0][1].attempt_ordinal, 1)
check("1g. record_attempted()にmember_run_idが渡される", draft_mgr_1.calls[0][2], "member-c1")
check("1h. POST成功後にrecord_confirmed()が呼ばれる", draft_mgr_1.calls[1][0], "confirmed")
check("1i. record_confirmed()にwp_post_idが渡される", draft_mgr_1.calls[1][3], 555)
check_true("1j. _post()はsuccess=Trueを返す", result_1.success)
print()


# ─── [テスト2] write-ahead ACK失敗時はexternal I/O = 0 ───

print("[テスト2] write-ahead ACK失敗時はpost_draft()が一切呼ばれない（external I/O = 0）")

events_2: list[str] = []
draft_mgr_2 = _FakeDraftStateManager(fail_attempted=True, events=events_2)
client_2 = _FakeWordPressDraftClient(events=events_2)
service_2 = make_service(client_2, draft_mgr_2, manifest_registrar=_manifest_registrar_c)

raised_2 = None
try:
    service_2._post(make_review(), make_rewrite(), side_effect_execution_context=_PROTECTED_CONTEXT)
except WordPressDraftStateTransitionError as e:
    raised_2 = e

check_true("2a. write-ahead ACK失敗時はWordPressDraftStateTransitionErrorが伝播する", raised_2 is not None)
check("2b. post_draft()は一切呼ばれない（external I/O = 0）", len(client_2.calls), 0)
print()


# ─── [テスト3] side_effect_execution_context欠落/不正時はexternal I/O = 0 ───

print("[テスト3] side_effect_execution_context欠落時はpost_draft()前でfail-closedする")

client_3 = _FakeWordPressDraftClient()
service_3 = make_service(client_3, _FakeDraftStateManager())

raised_3 = None
try:
    service_3._post(make_review(), make_rewrite(), side_effect_execution_context=None)
except SideEffectExecutionModeContractError as e:
    raised_3 = e
except Exception as e:
    raised_3 = e

check_true("3a. SideEffectExecutionModeContractErrorが送出される", isinstance(raised_3, SideEffectExecutionModeContractError))
check_true(
    "3b. contract errorはRuntimeError等の一般的な例外へ変換されない（型がそのまま伝播する）",
    type(raised_3) is SideEffectExecutionModeContractError,
)
check("3c. post_draft()は一切呼ばれない", len(client_3.calls), 0)
print()


# ─── [テスト4] protected時にdraft_state_manager欠落ならexternal I/O前にfail-closed ───

print("[テスト4] protected context・draft_state_manager=Noneはpost_draft()前でfail-closedする")

client_4 = _FakeWordPressDraftClient()
service_4 = make_service(client_4, draft_state_manager=None, manifest_registrar=_manifest_registrar_c)

raised_4 = None
try:
    service_4._post(make_review(), make_rewrite(), side_effect_execution_context=_PROTECTED_CONTEXT)
except Exception as e:
    raised_4 = e

check_true("4a. draft_state_manager=Noneでは例外が送出される（AttributeError、call site A同型の既存契約）", raised_4 is not None)
check("4b. post_draft()は一切呼ばれない（external I/O = 0）", len(client_4.calls), 0)
print()


# ─── [テスト5] POST失敗時はrecord_confirmed()を呼ばない ───

print("[テスト5] post_draft()失敗（RuntimeError）時はrecord_confirmed()を呼ばない")

draft_mgr_5 = _FakeDraftStateManager()
client_5 = _FakeWordPressDraftClient(error=RuntimeError("WordPress投稿失敗 (HTTP 500)"))
service_5 = make_service(client_5, draft_mgr_5, manifest_registrar=_manifest_registrar_c)

result_5 = service_5._post(make_review(), make_rewrite(), side_effect_execution_context=_PROTECTED_CONTEXT)

check_false("5a. success=False", result_5.success)
check("5b. record_attempted()は呼ばれる（IO_ARMED相当のACKは既に成功済み）", [c[0] for c in draft_mgr_5.calls], ["attempted"])
check_false("5c. record_confirmed()は呼ばれない（ATTEMPTEDのまま維持、13章fail-closed）", any(c[0] == "confirmed" for c in draft_mgr_5.calls))
print()


# ─── [テスト6] legacy経路：既存external behaviorを維持し、4 safety methodsへ一切触れない ───

print("[テスト6] legacy contextはdraft_state_managerへ一切触れない・既存挙動を維持する")

client_6 = _FakeWordPressDraftClient()
service_6 = make_service(client_6, _RaisingDraftStateManager())

result_6 = service_6._post(make_review(), make_rewrite(), side_effect_execution_context=_LEGACY_CONTEXT)

check_true("6a. legacy contextでも既存どおり成功する", result_6.success)
check("6b. wp_post_idはAPIレスポンスから取得される", result_6.wp_post_id, 555)
check("6c. post_draft()は1回だけ呼ばれる（既存動作と同一）", len(client_6.calls), 1)
print()

print("[テスト6続き] legacy contextはdraft_state_manager未指定（None）でも動作する")

client_6b = _FakeWordPressDraftClient()
service_6b = make_service(client_6b, draft_state_manager=None)
result_6b = service_6b._post(make_review(), make_rewrite(), side_effect_execution_context=_LEGACY_CONTEXT)
check_true("6d. draft_state_manager=None・legacy contextで既存どおり成功する", result_6b.success)
print()

# ─── [テスト6c] Codex Final Review Blocking#2: protected context + manifest_registrar=None ───
# 既存の「registrar exists but RegisterResult.acknowledged==False」系fail-closed
# testsとは別ケース（registrar自体がMISSING）であることに注意（混同しない）。

print("[テスト6c] protected context + manifest_registrar省略はpost_draft()前でfail-closedする（Blocking#2）")

client_6c = _FakeWordPressDraftClient()
draft_mgr_6c = _FakeDraftStateManager()
service_6c = make_service(client_6c, draft_mgr_6c)  # manifest_registrar省略（None）
raised_6c = None
try:
    service_6c._post(make_review(), make_rewrite(), side_effect_execution_context=_PROTECTED_CONTEXT)
except SideEffectExecutionModeContractError as e:
    raised_6c = e

check_true("6c-a. protected + registrar省略はSideEffectExecutionModeContractErrorで拒否される", raised_6c is not None)
check(
    "6c-b. reason_codeはPROTECTED_MANIFEST_REGISTRAR_REQUIRED",
    raised_6c.reason_code if raised_6c else None,
    ExecutionModeFailureReasonCode.PROTECTED_MANIFEST_REGISTRAR_REQUIRED,
)
check("6c-c. draft_state_manager.record_attempted()は一切呼ばれない（write-ahead=0）", len(draft_mgr_6c.calls), 0)
check("6c-d. post_draft()は一切呼ばれない（external I/O=0）", len(client_6c.calls), 0)
print()


# ─── [テスト7] PublishStepExecutor：authoritative validation boundary ───

print("[テスト7] PublishStepExecutorはbroad exceptより前でvalidateし、contract errorをstep失敗へ変換しない")

_service_never_called = MagicMock()
executor_7 = PublishStepExecutor(service=_service_never_called)
ctx_7 = WorkflowContext(article_id=None, dry_run=False)  # side_effect_execution_context省略＝None

raised_7 = None
try:
    executor_7.execute(ctx_7)
except SideEffectExecutionModeContractError as e:
    raised_7 = e
except Exception as e:
    raised_7 = e

check_true(
    "7a. SideEffectExecutionModeContractErrorがexecute()の外へそのまま伝播する（WorkflowStepResultへ変換されない）",
    isinstance(raised_7, SideEffectExecutionModeContractError),
)
check("7b. self._service.run()は一切呼ばれない（validateがrun()より前）", _service_never_called.run.call_count, 0)
print()

print("[テスト7続き] dry_run=Trueの場合はvalidateより前にdry_run resultを返す（既存動作維持）")

ctx_7b = WorkflowContext(article_id=None, dry_run=True)
result_7b = executor_7.execute(ctx_7b)
check_true("7c. dry_run=Trueはcontext欠落でも例外を出さない", result_7b.success)
check("7d. dry_run結果はprocessed_count=0", result_7b.processed_count, 0)
print()


# ─── [テスト8] PublishPipelineRunner：contract-error carve-out ───

print("[テスト8] PublishPipelineRunnerはSideEffectExecutionModeContractErrorをPipelineResultへ変換しない")


class _FakeRunnerConfig:
    def __init__(self, project_root):
        self.project_root = project_root


import tempfile  # noqa: E402

with tempfile.TemporaryDirectory() as tmpdir_8:
    fake_service_8 = MagicMock()
    fake_service_8.run.side_effect = SideEffectExecutionModeContractError(
        list(__import__("side_effect_safety").ExecutionModeFailureReasonCode)[0]
    )

    with patch("ai.AiPublishService") as mock_cls_8:
        mock_cls_8.from_env.return_value = fake_service_8
        runner_8 = PublishPipelineRunner(_FakeRunnerConfig(Path(tmpdir_8)))
        raised_8 = None
        try:
            runner_8.run(params={"article_id": "x"}, side_effect_execution_context=None)
        except SideEffectExecutionModeContractError as e:
            raised_8 = e

check_true(
    "8a. contract errorがPipelineResult(success=False)へ変換されず、そのまま伝播する",
    raised_8 is not None,
)
print()


# ─── [テスト9] queue/scheduler関連パッケージへの新規依存なし（Consumer-less確認） ───

print("[テスト9] 変更対象ファイルがretry_queue/scheduler等へ新規依存していないこと")

_FORBIDDEN_ROOTS = {
    "retry_queue", "retry_runtime_orchestrator", "retry_engine", "retry_lineage",
    "retry_composition", "workflow_engine", "scheduler",
}


def _import_roots(file_path: Path) -> set:
    tree = ast.parse(file_path.read_text(encoding="utf-8"))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            roots.add(node.module.split(".")[0])
    return roots


for _rel in (
    "src/ai/ai_publish_service.py",
    "src/ai/workflow_step_executor.py",
    "src/pipeline/publish_pipeline_runner.py",
):
    _hits = sorted(_FORBIDDEN_ROOTS & _import_roots(PROJECT_ROOT / _rel))
    check(f"9. {_rel} がqueue/scheduler系packageへ依存しない", _hits, [])
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
