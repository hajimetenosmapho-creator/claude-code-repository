"""
E2E テスト: v6.32.3 呼び出し箇所A（NEWS / WordPressOutput.save()）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    15.7節（呼び出し箇所Aの統合）・22.3.1節（Exact Integration Points）・
    14.3節（main.py側のExplicit Execution Mode検証）・
    14.6節（NEWS Subprocess境界 — Contract-Error Exit Protocol）。

sub-milestone 3のdirect tests。以下を検証する：
    (a) write-ahead ACK確認前にWordPress POST（requests.post()）が呼ばれない
        （write-ahead-before-I/O契約、9.9.3節と同型のOrdering Contract）
    (b) protected/legacy semantics separation（legacyはdraft_state_managerへ
        一切触れない）
    (c) §14 subprocess envelope（NewsPipelineRunner→main.pyの環境変数伝播）
    (d) SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE=3プロトコル
    (e) contract errorが通常/genericな失敗へ変換されないこと

実行方法:
    cd projects/03_game_content_ai
    .\\venv\\Scripts\\python.exe tests\\test_e2e_v6_32_3_call_site_a_news_wordpress.py
"""
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).parent.parent
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
print("v6.32.3 呼び出し箇所A（NEWS / WordPressOutput.save()）E2E テスト")
print("=" * 60)
print()

from outputs.wordpress_output import WordPressOutput  # noqa: E402
from outputs.base import ArticleData  # noqa: E402
from collector import NewsItem  # noqa: E402
from publishing_config import PublishStatus  # noqa: E402
from side_effect_safety import (  # noqa: E402
    LegacyEntrypoint,
    LegacyExecutionOrigin,
    ProtectedSideEffectKind,
    RetryLineageProtectedExecutionContext,
    SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE,
    SideEffectExecutionModeContractError,
    SideEffectOperationIdentity,
    SideEffectSite,
    build_legacy_direct_provenance,
    build_protected_execution_context,
    complete_legacy_execution_context,
)
from side_effect_safety.side_effect_execution_mode import ExecutionModeFailureReasonCode  # noqa: E402
from wordpress_draft_state.errors import WordPressDraftStateTransitionError  # noqa: E402
import pipeline.news_pipeline_runner as npr_module  # noqa: E402
from pipeline.news_pipeline_runner import NewsPipelineRunner  # noqa: E402
from protected_operation_manifest import JsonProtectedOperationManifestStore, ManifestRegistrarFacade  # noqa: E402

# Codex Final Review Blocking#2対応：protected contextでのWordPressOutput構築は
# manifest_registrarを必須とする（省略時はSideEffectExecutionModeContractError）。
# 本ファイルの既存test（write-ahead-before-I/O契約等）を維持するため、実の
# ManifestRegistrarFacadeを配線する（test-owned tmp dir、production非変更）。
_manifest_store_a = JsonProtectedOperationManifestStore(base_dir=Path(tempfile.mkdtemp()) / "manifest")
_manifest_registrar_a = ManifestRegistrarFacade(_manifest_store_a)
# admission（実チェーンではmark_execution_started()が行う）を模し、
# register()より前に空manifestを作成しておく。
_manifest_store_a.create_for_attempt("root-a1", 1, "member-a1")


def make_article() -> ArticleData:
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
        slug="ps6-announced-20260630",
        publish_status=PublishStatus.DRAFT,
    )


_LEGACY_CONTEXT = complete_legacy_execution_context(
    build_legacy_direct_provenance(LegacyEntrypoint.RUN_MAIN_DIRECT),
    LegacyExecutionOrigin.MAIN_DIRECT,
)

_PROTECTED_CONTEXT = build_protected_execution_context(
    root_run_id="root-a1", attempt_ordinal=1, member_run_id="member-a1",
    side_effect_contract_version=1,
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


class _RaisingDraftStateManager:
    """legacy経路では一切呼ばれてはならないことを確認するための、
    呼ばれたら即fail-closedするFake。"""

    def record_attempted(self, identity, member_run_id):
        raise AssertionError("legacy contextではrecord_attempted()が呼ばれてはならない")

    def record_confirmed(self, identity, member_run_id, wp_post_id):
        raise AssertionError("legacy contextではrecord_confirmed()が呼ばれてはならない")


# ─── [テスト1] write-ahead ACK確認前にrequests.post()が呼ばれない ───

print("[テスト1] write-ahead-before-I/O契約（9.9.3節と同型のOrdering Contract）")

events: list[str] = []
draft_mgr_1 = _FakeDraftStateManager()


def _tracking_post(*args, **kwargs):
    events.append("post_called")
    return _MOCK_RESPONSE


with patch("outputs.wordpress_output.requests.post", side_effect=_tracking_post):
    orig_record_attempted = draft_mgr_1.record_attempted

    def _tracked_attempted(identity, member_run_id):
        events.append("attempted")
        return orig_record_attempted(identity, member_run_id)

    draft_mgr_1.record_attempted = _tracked_attempted

    wp1 = WordPressOutput(
        site_url="https://example.test", username="u", app_password="p",
        side_effect_execution_context=_PROTECTED_CONTEXT,
        draft_state_manager=draft_mgr_1,
        manifest_registrar=_manifest_registrar_a,
    )
    result1 = wp1.save(make_article())

check("1a. 呼び出し順序はattempted→post_called", events, ["attempted", "post_called"])
check("1b. record_attempted()にProtected contextのidentityが渡される",
      draft_mgr_1.calls[0][1].operation_kind, ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION)
check("1c. record_attempted()のeffect_siteはNEWS_STEP", draft_mgr_1.calls[0][1].effect_site, SideEffectSite.NEWS_STEP)
check("1d. record_attempted()にmember_run_idが渡される", draft_mgr_1.calls[0][2], "member-a1")
check("1e. save()成功後にrecord_confirmed()が呼ばれる", draft_mgr_1.calls[1][0], "confirmed")
check("1f. record_confirmed()にwp_post_idが渡される", draft_mgr_1.calls[1][3], 555)
check_true("1g. save()はSaveResult(success=True)を返す", result1.success)
print()

print("[テスト2] write-ahead ACK失敗時はrequests.post()が一切呼ばれない（external I/O = 0）")

post_called_2 = False


def _post_should_not_be_called(*args, **kwargs):
    global post_called_2
    post_called_2 = True
    return _MOCK_RESPONSE


draft_mgr_2 = _FakeDraftStateManager(fail_attempted=True)
wp2 = WordPressOutput(
    site_url="https://example.test", username="u", app_password="p",
    side_effect_execution_context=_PROTECTED_CONTEXT,
    draft_state_manager=draft_mgr_2,
    manifest_registrar=_manifest_registrar_a,
)
raised_2 = None
with patch("outputs.wordpress_output.requests.post", side_effect=_post_should_not_be_called):
    try:
        wp2.save(make_article())
    except WordPressDraftStateTransitionError as e:
        raised_2 = e

check_true("2a. write-ahead ACK失敗時はWordPressDraftStateTransitionErrorが伝播する", raised_2 is not None)
check_false("2b. requests.post()は一切呼ばれない", post_called_2)
print()


# ─── [テスト3] protected/legacy semantics separation ───

print("[テスト3] legacy contextはdraft_state_managerへ一切触れない")

with patch("outputs.wordpress_output.requests.post", return_value=_MOCK_RESPONSE):
    wp3 = WordPressOutput(
        site_url="https://example.test", username="u", app_password="p",
        side_effect_execution_context=_LEGACY_CONTEXT,
        draft_state_manager=_RaisingDraftStateManager(),
    )
    result3 = wp3.save(make_article())

check_true("3a. legacy contextでも既存どおりsave()が成功する", result3.success)
check("3b. legacy contextのpost_idはAPIレスポンスから取得される", result3.post_id, 555)
print()

print("[テスト4] legacy contextはdraft_state_manager未指定（None）でも動作する")

with patch("outputs.wordpress_output.requests.post", return_value=_MOCK_RESPONSE):
    wp4 = WordPressOutput(
        site_url="https://example.test", username="u", app_password="p",
        side_effect_execution_context=_LEGACY_CONTEXT,
    )
    result4 = wp4.save(make_article())

check_true("4a. draft_state_manager=None・legacy contextで既存どおり成功する", result4.success)
print()


# ─── [テスト5] side_effect_execution_context欠落時のfail-closed ───

print("[テスト5] side_effect_execution_context=Noneはrequests.post()前でfail-closedする")

post_called_5 = False


def _post_should_not_be_called_5(*args, **kwargs):
    global post_called_5
    post_called_5 = True
    return _MOCK_RESPONSE


wp5 = WordPressOutput(
    site_url="https://example.test", username="u", app_password="p",
    side_effect_execution_context=None,
)
raised_5 = None
with patch("outputs.wordpress_output.requests.post", side_effect=_post_should_not_be_called_5):
    try:
        wp5.save(make_article())
    except SideEffectExecutionModeContractError as e:
        raised_5 = e
    except Exception as e:
        raised_5 = e  # 型を確認するため一旦捕捉する

check_true("5a. SideEffectExecutionModeContractErrorが送出される", isinstance(raised_5, SideEffectExecutionModeContractError))
check_true(
    "5b. contract errorはRuntimeError等の一般的な例外へ変換されない（型がそのまま伝播する）",
    type(raised_5) is SideEffectExecutionModeContractError,
)
check_false("5c. requests.post()は一切呼ばれない", post_called_5)
print()


# ─── [テスト5b] Codex Final Review Blocking#2: protected context + manifest_registrar=None ───
# 既存の「registrar exists but RegisterResult.acknowledged==False」系fail-closed
# testsとは別ケース（registrar自体がMISSING）であることに注意（混同しない）。

print("[テスト5b] protected context + manifest_registrar省略はrequests.post()前でfail-closedする（Blocking#2）")

post_called_5b = False


def _post_should_not_be_called_5b(*args, **kwargs):
    global post_called_5b
    post_called_5b = True
    return _MOCK_RESPONSE


draft_mgr_5b = _FakeDraftStateManager()
wp5b = WordPressOutput(
    site_url="https://example.test", username="u", app_password="p",
    side_effect_execution_context=_PROTECTED_CONTEXT,
    draft_state_manager=draft_mgr_5b,
    # manifest_registrar省略（None）。
)
raised_5b = None
with patch("outputs.wordpress_output.requests.post", side_effect=_post_should_not_be_called_5b):
    try:
        wp5b.save(make_article())
    except SideEffectExecutionModeContractError as e:
        raised_5b = e

check_true("5b-a. protected + registrar省略はSideEffectExecutionModeContractErrorで拒否される", raised_5b is not None)
check(
    "5b-b. reason_codeはPROTECTED_MANIFEST_REGISTRAR_REQUIRED",
    raised_5b.reason_code if raised_5b else None,
    ExecutionModeFailureReasonCode.PROTECTED_MANIFEST_REGISTRAR_REQUIRED,
)
check("5b-c. draft_state_manager.record_attempted()は一切呼ばれない（write-ahead=0）", len(draft_mgr_5b.calls), 0)
check_false("5b-d. requests.post()は一切呼ばれない（external I/O=0）", post_called_5b)
print()

print("[テスト5c] legacy contextはmanifest_registrar省略でも既存どおり動作する（互換性維持）")

with patch("outputs.wordpress_output.requests.post", return_value=_MOCK_RESPONSE):
    wp5c = WordPressOutput(
        site_url="https://example.test", username="u", app_password="p",
        side_effect_execution_context=_LEGACY_CONTEXT,
        # manifest_registrar省略（None）。legacyでは許容される。
    )
    result5c = wp5c.save(make_article())

check_true("5c-a. legacy + registrar省略は既存どおり成功する", result5c.success)
print()


# ─── [テスト6] §14 subprocess envelope: NewsPipelineRunner→main.py の環境変数伝播 ───

print("[テスト6] NewsPipelineRunner.run() が protected context を環境変数へ正しく伝播する")


class _FakeRunnerConfig:
    def __init__(self, working_directory):
        self.python_executable = Path(sys.executable)
        self.main_py_path = Path("fake_main.py")
        self.working_directory = working_directory
        self.timeout_sec = 5


class _FakeCompleted:
    def __init__(self, stdout, stderr, returncode):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


_original_subprocess_run = npr_module.subprocess.run

captured_env = {}


def _capturing_run(cmd, cwd=None, capture_output=None, text=None, timeout=None, env=None):
    captured_env.clear()
    captured_env.update(env or {})
    return _FakeCompleted(stdout="ok", stderr="", returncode=0)


tmp_wd_6 = Path(tempfile.mkdtemp())
npr_module.subprocess.run = _capturing_run
try:
    runner_6 = NewsPipelineRunner(_FakeRunnerConfig(tmp_wd_6))
    runner_6.run({}, side_effect_execution_context=_PROTECTED_CONTEXT)
finally:
    npr_module.subprocess.run = _original_subprocess_run

check("6a. RETRY_LINEAGE_EXECUTION_MODEがretry_lineage_protected", captured_env.get("RETRY_LINEAGE_EXECUTION_MODE"), "retry_lineage_protected")
check("6b. RETRY_LINEAGE_ROOT_RUN_IDが伝播する", captured_env.get("RETRY_LINEAGE_ROOT_RUN_ID"), "root-a1")
check("6c. RETRY_LINEAGE_MEMBER_RUN_IDが伝播する", captured_env.get("RETRY_LINEAGE_MEMBER_RUN_ID"), "member-a1")
print()

print("[テスト7] NewsPipelineRunner.run() が legacy context を環境変数へ正しく伝播する")

tmp_wd_7 = Path(tempfile.mkdtemp())
npr_module.subprocess.run = _capturing_run
try:
    runner_7 = NewsPipelineRunner(_FakeRunnerConfig(tmp_wd_7))
    runner_7.run({}, side_effect_execution_context=_LEGACY_CONTEXT)
finally:
    npr_module.subprocess.run = _original_subprocess_run

check("7a. RETRY_LINEAGE_EXECUTION_MODEがlegacy_direct", captured_env.get("RETRY_LINEAGE_EXECUTION_MODE"), "legacy_direct")
check("7b. RETRY_LINEAGE_LEGACY_ENTRYPOINTが伝播する", captured_env.get("RETRY_LINEAGE_LEGACY_ENTRYPOINT"), "run_main_direct")
print()


# ─── [テスト8] SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE=3プロトコル ───

print("[テスト8] returncode=3はPipelineResultへ変換されず、例外がそのまま伝播する（14.6節）")

tmp_wd_8 = Path(tempfile.mkdtemp())
npr_module.subprocess.run = lambda *a, **kw: _FakeCompleted(stdout="", stderr="", returncode=3)
raised_8 = None
result_8 = "not-set"
try:
    runner_8 = NewsPipelineRunner(_FakeRunnerConfig(tmp_wd_8))
    result_8 = runner_8.run({})
except SideEffectExecutionModeContractError as e:
    raised_8 = e
finally:
    npr_module.subprocess.run = _original_subprocess_run

check("8a. SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODEの値は3", SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE, 3)
check_true("8b. returncode=3はSideEffectExecutionModeContractErrorとして伝播する", raised_8 is not None)
check(
    "8c. reason_codeはSUBPROCESS_CONTRACT_VIOLATIONへ集約される",
    raised_8.reason_code if raised_8 is not None else None,
    ExecutionModeFailureReasonCode.SUBPROCESS_CONTRACT_VIOLATION,
)
check(
    "8d. PipelineResult(success=False)へは変換されない（result_8はrun()呼び出し前の初期値のまま）",
    result_8, "not-set",
)
print()


# ─── [テスト9] main.py 実プロセスでのexit code 3（child側、実プロセス起動） ───

print("[テスト9] main.py 実起動：矛盾したenvelope（partial/orphan）でexit code 3")

import os as _os  # noqa: E402

# Windows実プロセス起動には（asyncio初期化等のため）最小限のPATH等では不足する
# ため、実プロセスの環境全体を複製した上で対象変数のみ追加・削除する
# （テスト用最小envを独自構築するとWinError 10106等、契約と無関係の理由で
# 起動自体が失敗するため）。
env_9 = dict(_os.environ)
env_9.pop("RETRY_LINEAGE_EXECUTION_MODE", None)
# RETRY_LINEAGE_EXECUTION_MODEを設定せず、protected fieldの1つのみ設定する
# → 14.3節のpartial/orphan envelope判定によりCONTRADICTORY_SERIALIZED_FORM。
# main()冒頭（ANTHROPIC_API_KEYチェックより前）で raise されるため、
# API key・ネットワークいずれも不要。
env_9["RETRY_LINEAGE_ROOT_RUN_ID"] = "root-orphan-9"
completed_9 = subprocess.run(
    [sys.executable, str(PROJECT_ROOT / "main.py"), "--max-articles", "0"],
    cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30, env=env_9,
)
check("9a. main.py実プロセスのexit codeは3", completed_9.returncode, 3)
print()

print("[テスト10] envelope完全欠落時は自己発生（legacy MAIN_DIRECT）でfail-closedしない")

# main.pyはload_dotenv()を無条件に（モジュールimport時点で）実行するため、
# 実プロセスを起動すると.envのANTHROPIC_API_KEYが常に注入されてしまい、
# 「envelope欠落時に実際にニュース収集まで進んでしまわないか」を安全に
# 検証できない（実ネットワークI/Oに到達する恐れがある）。そのため本テストは
# _parse_execution_context_from_env()自体をenvelope完全欠落状態で直接呼び出し、
# 14.3節が定める自己発生規則（main.py自身がtrusted composition rootとして
# RUN_MAIN_DIRECT/MAIN_DIRECTを自己発生させる）が正しく機能することを
# in-processで確認する。
from side_effect_safety.side_effect_execution_mode import _parse_execution_context_from_env  # noqa: E402

_envelope_keys = (
    "RETRY_LINEAGE_EXECUTION_MODE", "RETRY_LINEAGE_ROOT_RUN_ID", "RETRY_LINEAGE_ATTEMPT_ORDINAL",
    "RETRY_LINEAGE_MEMBER_RUN_ID", "RETRY_LINEAGE_CONTRACT_VERSION",
    "RETRY_LINEAGE_LEGACY_ENTRYPOINT", "RETRY_LINEAGE_LEGACY_EXECUTION_ORIGIN",
)
_saved_env = {k: _os.environ.get(k) for k in _envelope_keys}
for _k in _envelope_keys:
    _os.environ.pop(_k, None)
try:
    resolved_10 = _parse_execution_context_from_env()
finally:
    for _k, _v in _saved_env.items():
        if _v is not None:
            _os.environ[_k] = _v

check("10a. envelope完全欠落時はLegacyDirectExecutionContextが自己発生する（fail-closedしない）",
      resolved_10, _LEGACY_CONTEXT)
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
