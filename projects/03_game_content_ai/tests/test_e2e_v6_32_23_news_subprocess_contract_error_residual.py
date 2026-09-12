"""
E2E テスト: Release 6.32 NEWS Subprocess / Contract-Error Propagation residual
（§28.-39・§28.-38・§28.-33）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    14.6節（NEWS Subprocess境界）・22.3.13節（Contract-Error Non-Absorption）・
    28.-39節（5件）・28.-38節（3件）・28.-33節（Invariant #11、3件）。

Canonical Gap Inventory照合結果：
    §28.-39 #1（child exit protocol）：既存test_e2e_v6_32_3テスト9で実プロセス
        起動によりCOMPLETE。#4（既存0/1/20/21回帰）：pre-6.32から存在する
        test_e2e_v2_2_0/test_e2e_v6_30_0で既にCOMPLETE（本節の変更は
        returncode==3の早期分岐のみで、既存分岐へは非干渉）。いずれも
        重複実装しない。#2（parent detection、mock化しない実subprocess
        chain）・#3（AgentManager配下の実chain上流でのnon-normalization）・
        #5（exit code衝突なしのstatic監査）が欠落していた。

    §28.-38 #1（呼び出し箇所C）：既存test_e2e_v6_32_5テスト7・8で
        実質COMPLETE（重複実装しない）。#2（呼び出し箇所A、OutputManager）：
        既存test_e2e_v6_32_3bは`contract-error output`が先頭のケースのみを
        検証しており、末尾に置かれるケース（順序非依存の確認）が欠落していた。
        #3（呼び出し箇所B、main.py記事ループ）：既存coverageは存在せず、
        `except SideEffectExecutionModeContractError: raise`が
        `except FeaturedMediaPropagatedFailure:`より先に評価されることの
        実行ベースの直接証拠が欠落していた（ユーザー指摘どおりの最重要ギャップ）。

    §28.-33（Invariant #11）：既存test_e2e_v6_32_0はduplicate
        `record_not_applicable()`呼び出しの例外型のみを確認しており、
        2回目の呼び出しで`MediaUploadApplicabilityStore.create()`が
        一切呼ばれないこと（**追加のdurable write = 0**）をモック呼び出し
        回数で直接確認する部分が欠落していた。

対象production: なし（全てtest-only。production変更は一切行っていない）。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_23_news_subprocess_contract_error_residual.py
"""
from __future__ import annotations

import ast
import inspect
import os
import subprocess
import sys
import tempfile
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


print("=" * 60)
print("NEWS Subprocess / Contract-Error Propagation residual（§28.-39・-38・-33）E2E テスト")
print("=" * 60)
print()

from side_effect_safety import (  # noqa: E402
    SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE,
    SideEffectExecutionModeContractError,
)
from side_effect_safety.side_effect_execution_mode import ExecutionModeFailureReasonCode  # noqa: E402
from pipeline.news_pipeline_runner import NewsPipelineRunner  # noqa: E402
from ai.agent_context import AgentContext  # noqa: E402
from ai.agent_executor import AgentExecutor  # noqa: E402
from ai.agent_task import AgentTask  # noqa: E402
from ai.news_agent import NewsAgent  # noqa: E402


# =====================================================================
# Part A: §28.-39 NEWS Subprocess境界
# =====================================================================

_ORPHAN_ENV_KEY = "RETRY_LINEAGE_ROOT_RUN_ID"
_MODE_ENV_KEY = "RETRY_LINEAGE_EXECUTION_MODE"


class _RealRunnerConfig:
    def __init__(self):
        self.python_executable = Path(sys.executable)
        self.main_py_path = PROJECT_ROOT / "main.py"
        self.working_directory = PROJECT_ROOT
        self.timeout_sec = 30


def _inject_orphan_envelope():
    """14.3節のpartial/orphan envelope判定によりCONTRADICTORY_SERIALIZED_FORMを
    誘発する（test_e2e_v6_32_3テスト9と同一の技法）。main()冒頭・API keyチェック
    より前でraiseされるため、ネットワーク・API keyいずれも不要。"""
    saved = {k: os.environ.get(k) for k in (_MODE_ENV_KEY, _ORPHAN_ENV_KEY)}
    os.environ.pop(_MODE_ENV_KEY, None)
    os.environ[_ORPHAN_ENV_KEY] = "root-orphan-23"
    return saved


def _restore_envelope(saved: dict):
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


print("[A2] parent detection：mock化せず実subprocess chainを経由する（NewsPipelineRunner.run()）")

saved_env_a2 = _inject_orphan_envelope()
raised_a2 = None
try:
    runner_a2 = NewsPipelineRunner(_RealRunnerConfig())
    result_a2 = "not-set"
    try:
        result_a2 = runner_a2.run(params={"max_articles": 0}, side_effect_execution_context=None)
    except SideEffectExecutionModeContractError as e:
        raised_a2 = e
finally:
    _restore_envelope(saved_env_a2)

check_true("A2a. NewsPipelineRunner.run()がSideEffectExecutionModeContractErrorを送出する（実subprocess経由）", raised_a2 is not None)
check(
    "A2b. reason_codeはSUBPROCESS_CONTRACT_VIOLATION", raised_a2.reason_code if raised_a2 else None,
    ExecutionModeFailureReasonCode.SUBPROCESS_CONTRACT_VIOLATION,
)
check("A2c. PipelineResultへは変換されない（result_a2は呼び出し前の初期値のまま）", result_a2, "not-set")
print()


print("[A3] upper chain non-normalization：AgentExecutor.execute() → NewsAgent.act() → 実NewsPipelineRunner")

class _StubNewsAgentConfig:
    """decide()の判断ロジック（前回実行ログ検索）だけを安全に動かすための最小stub。
    実project直下のlogs/execution/を読ませないよう、空の一時ディレクトリを指す。"""

    def __init__(self, working_directory: Path):
        self.working_directory = working_directory
        self.log_lookback_days = 1
        self.min_interval_minutes = 0


saved_env_a3 = _inject_orphan_envelope()
raised_a3 = None
try:
    tmp_a3_cfg_dir = Path(tempfile.mkdtemp(prefix="v6_32_23_a3_"))
    real_runner_a3 = NewsPipelineRunner(_RealRunnerConfig())
    news_agent_a3 = NewsAgent(config=_StubNewsAgentConfig(tmp_a3_cfg_dir), runner=real_runner_a3)
    agent_executor_a3 = AgentExecutor(news_agent_a3)
    context_a3 = AgentContext(
        task=AgentTask(task_id="run_news", params={"max_articles": 0}), dry_run=False,
        run_id="run-23a3", agent_name="", side_effect_execution_context=None,
    )
    try:
        agent_executor_a3.execute(context_a3)
    except SideEffectExecutionModeContractError as e:
        raised_a3 = e
finally:
    _restore_envelope(saved_env_a3)

check_true(
    "A3a. AgentExecutor.execute()の外まで未変換のまま伝播する（AgentResult(success=False)へ変換されない）",
    raised_a3 is not None,
)
check(
    "A3b. reason_codeはSUBPROCESS_CONTRACT_VIOLATIONのまま（NewsAgent.act()・AgentExecutor.execute()いずれも変換しない）",
    raised_a3.reason_code if raised_a3 else None,
    ExecutionModeFailureReasonCode.SUBPROCESS_CONTRACT_VIOLATION,
)
print()


print("[A4] 既存exit code 0/1/20/21回帰：pre-6.32テスト（test_e2e_v2_2_0・test_e2e_v6_30_0）でCOMPLETE確認済み（再実装なし）")
print()


print("[A5] exit code衝突なし・単一定数定義のstatic監査")

check("A5a. SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODEは3", SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE, 3)
check_false("A5b. 3は既存Outcome Contract{0,1,2,20,21}と衝突しない", SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE in {0, 1, 2, 20, 21})

_mode_module_src = (SRC_DIR / "side_effect_safety" / "side_effect_execution_mode.py").read_text(encoding="utf-8")
_mode_tree = ast.parse(_mode_module_src)
_definition_count = sum(
    1 for node in ast.walk(_mode_tree)
    if isinstance(node, ast.Assign)
    and any(isinstance(t, ast.Name) and t.id == "SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE" for t in node.targets)
)
check("A5c. SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODEはside_effect_execution_mode.py内で1回のみ定義される（単一定数）", _definition_count, 1)

_main_src = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
_npr_src = (SRC_DIR / "pipeline" / "news_pipeline_runner.py").read_text(encoding="utf-8")
check_true("A5d. main.pyはside_effect_safetyからSIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODEをimportする（ハードコード重複なし）", "from side_effect_safety import" in _main_src and "SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE" in _main_src)
check_true("A5e. news_pipeline_runner.pyも同一定数をimportする（ハードコード重複なし）", "SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE" in _npr_src)

_main_tree = ast.parse(_main_src)
_main_hardcoded_3_exit = [
    node for node in ast.walk(_main_tree)
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "exit"
    and any(isinstance(a, ast.Constant) and a.value == 3 for a in node.args)
]
check("A5f. main.py内でsys.exit(3)のリテラルハードコードは0件（定数経由のみ）", len(_main_hardcoded_3_exit), 0)
print()


# =====================================================================
# Part B: §28.-38 呼び出し箇所A/B/C Contract-Error Non-Absorption
# =====================================================================

print("[B1] 呼び出し箇所C：既存test_e2e_v6_32_5テスト7・8でCOMPLETE確認済み（再実装なし）")
print()

print("[B2] 呼び出し箇所A、OutputManager：contract-error出力が末尾（後方）に置かれる構成でも順序非依存")

from outputs.manager import OutputManager  # noqa: E402
from outputs.base import ArticleData, SaveResult  # noqa: E402
from collector import NewsItem  # noqa: E402
from publishing_config import PublishStatus  # noqa: E402


def make_article_b() -> ArticleData:
    item = NewsItem(
        title="t", url="https://example.test/n", summary="s", source="src",
        published_at="2026-06-30", image_candidates=[],
    )
    return ArticleData(
        item=item, importance="S", seo_title="t", article_body="b", x_post="x",
        slug="outputmanager-order-b2", publish_status=PublishStatus.DRAFT,
    )


class _ContractErrorOutputB2:
    def is_available(self):
        return True

    def save(self, article):
        raise SideEffectExecutionModeContractError(ExecutionModeFailureReasonCode.MISSING_EXECUTION_MODE)


class _SuccessOutputB2:
    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    def save(self, article):
        self.calls += 1
        return SaveResult(success=True, output_type="file")


# WordPressOutput相当（contract-error側）を末尾に置く構成
before_output_b2 = _SuccessOutputB2()
contract_output_b2 = _ContractErrorOutputB2()
manager_b2 = OutputManager([before_output_b2, contract_output_b2])

raised_b2 = None
try:
    manager_b2.save_all(make_article_b())
except SideEffectExecutionModeContractError as e:
    raised_b2 = e

check_true("B2a. 末尾に置いてもcontract errorがそのまま伝播する（順序非依存）", isinstance(raised_b2, SideEffectExecutionModeContractError))
check("B2b. 先頭のoutputは既に処理済みのまま（1回呼ばれている、これは正常な逐次処理の帰結）", before_output_b2.calls, 1)
print()


print("[B3] 呼び出し箇所B、main.py記事ループ：実boundaryでのcontract-error非absorption")

import main  # noqa: E402
from importance_judge import judge_all as _unused_judge_all  # noqa: E402,F401

_fake_news_item = NewsItem(
    title="B3テスト記事", url="https://example.test/b3", summary="s", source="src",
    published_at="2026-06-30", image_candidates=[],
)


def _fake_collect_all_news(max_items_per_feed=20):
    return ([_fake_news_item], [])


def _fake_filter_news(all_news):
    return {"pass": list(all_news), "pending": []}


def _fake_deduplicate_news(target_news):
    return target_news


def _fake_judge_all(client, target_news):
    return [{"item": item, "importance": "S"} for item in target_news]


def _fake_generate_article(client, item, importance):
    return "本文（テスト用固定文字列、実API呼び出しなし）"


def _fake_generate_seo_title(client, item, importance):
    return "SEOタイトル（テスト用）"


def _fake_generate_x_post(client, item, importance, article_body, blog_url=""):
    return "Xポスト（テスト用）"


def _fake_generate_slug(seo_title, date_str):
    return "b3-test-slug-" + date_str


def _fake_resolve_featured_image(item):
    return ""


def _fake_resolve_media_id(item, default_media_id):
    return 0


_handle_failure_spy_calls = []


def _spy_handle_featured_media_failure(*args, **kwargs):
    _handle_failure_spy_calls.append((args, kwargs))


_output_manager_save_all_calls = []


class _SpyOutputManager:
    def __init__(self, outputs):
        self.outputs = outputs

    def save_all(self, article):
        _output_manager_save_all_calls.append(article)
        raise AssertionError("contract error発生後、output_manager.save_all()へは到達しないはず")


_apply_step_spy_calls = []


def _raising_apply_featured_media_step(article, *, side_effect_binding):
    _apply_step_spy_calls.append(article)
    raise SideEffectExecutionModeContractError(ExecutionModeFailureReasonCode.MISSING_EXECUTION_MODE)


tmp_b3 = Path(tempfile.mkdtemp(prefix="v6_32_23_b3_"))

saved_env_b3 = {"ANTHROPIC_API_KEY": os.environ.get("ANTHROPIC_API_KEY")}
os.environ["ANTHROPIC_API_KEY"] = "test-key-not-real"
saved_argv_b3 = sys.argv
sys.argv = [str(PROJECT_ROOT / "main.py")]

import contextlib  # noqa: E402

raised_b3 = None
try:
    with contextlib.ExitStack() as stack_b3:
        stack_b3.enter_context(patch("main.OUTPUT_DIR", tmp_b3 / "output"))
        stack_b3.enter_context(patch("main.WORDPRESS_DRAFT_STATE_DIR", tmp_b3 / "state" / "wordpress_draft_state"))
        stack_b3.enter_context(patch("main.MEDIA_UPLOAD_STATE_DIR", tmp_b3 / "state" / "article_media_upload_state"))
        stack_b3.enter_context(patch("main.MEDIA_UPLOAD_APPLICABILITY_DIR", tmp_b3 / "state" / "media_upload_applicability"))
        stack_b3.enter_context(patch("main.MEDIA_UPLOAD_ATTEMPT_CONTEXT_DIR", tmp_b3 / "state" / "media_upload_attempt_context"))
        stack_b3.enter_context(patch("main.MEDIA_UPLOAD_LOCKS_DIR", tmp_b3 / "state" / "media_upload_locks"))
        stack_b3.enter_context(patch("main.collect_all_news", side_effect=_fake_collect_all_news))
        stack_b3.enter_context(patch("main.filter_news", side_effect=_fake_filter_news))
        stack_b3.enter_context(patch("main.deduplicate_news", side_effect=_fake_deduplicate_news))
        stack_b3.enter_context(patch("main.judge_all", side_effect=_fake_judge_all))
        stack_b3.enter_context(patch("main.generate_article", side_effect=_fake_generate_article))
        stack_b3.enter_context(patch("main.generate_seo_title", side_effect=_fake_generate_seo_title))
        stack_b3.enter_context(patch("main.generate_x_post", side_effect=_fake_generate_x_post))
        stack_b3.enter_context(patch("main.generate_slug", side_effect=_fake_generate_slug))
        stack_b3.enter_context(patch("main.resolve_featured_image", side_effect=_fake_resolve_featured_image))
        stack_b3.enter_context(patch("main.resolve_media_id", side_effect=_fake_resolve_media_id))
        stack_b3.enter_context(patch("main._apply_featured_media_step", side_effect=_raising_apply_featured_media_step))
        stack_b3.enter_context(patch("main._handle_featured_media_failure", side_effect=_spy_handle_featured_media_failure))
        stack_b3.enter_context(patch("main.OutputManager", side_effect=_SpyOutputManager))
        try:
            main.main()
        except SideEffectExecutionModeContractError as e:
            raised_b3 = e
finally:
    sys.argv = saved_argv_b3
    if saved_env_b3["ANTHROPIC_API_KEY"] is None:
        os.environ.pop("ANTHROPIC_API_KEY", None)
    else:
        os.environ["ANTHROPIC_API_KEY"] = saved_env_b3["ANTHROPIC_API_KEY"]

check_true("B3a. main()の記事ループ全体を抜けて、contract errorが未変換のまま伝播する", raised_b3 is not None)
check("B3b. _apply_featured_media_step()は1回だけ呼ばれる（記事1件のみ）", len(_apply_step_spy_calls), 1)
check("B3c. _handle_featured_media_failure()は一切呼ばれない（FeaturedMediaPropagatedFailureへ合流していない）", len(_handle_failure_spy_calls), 0)
check("B3d. output_manager.save_all()は一切呼ばれない（continueで次へ進んでいない）", len(_output_manager_save_all_calls), 0)
print()


# main.py source上でも、except SideEffectExecutionModeContractError: raise が
# except FeaturedMediaPropagatedFailure: より先に評価される順序であることを
# AST上で直接確認する（実行結果の裏付けとして）
_main_tree_b3 = ast.parse(_main_src)
_try_node_b3 = None
for node in ast.walk(_main_tree_b3):
    if isinstance(node, ast.Try):
        handler_names = [h.type.id if isinstance(h.type, ast.Name) else getattr(h.type, "attr", None) for h in node.handlers]
        if "SideEffectExecutionModeContractError" in handler_names and "FeaturedMediaPropagatedFailure" in handler_names:
            _try_node_b3 = node
            break

check_true("B3e. main.py source上に該当try文が存在する", _try_node_b3 is not None)
if _try_node_b3 is not None:
    _handler_order_b3 = [h.type.id if isinstance(h.type, ast.Name) else getattr(h.type, "attr", None) for h in _try_node_b3.handlers]
    idx_contract_b3 = _handler_order_b3.index("SideEffectExecutionModeContractError")
    idx_propagated_b3 = _handler_order_b3.index("FeaturedMediaPropagatedFailure")
    check_true("B3f. except SideEffectExecutionModeContractError: がexcept FeaturedMediaPropagatedFailure: より先に評価される順序（source順）", idx_contract_b3 < idx_propagated_b3)
    _contract_handler_body_b3 = _try_node_b3.handlers[idx_contract_b3].body
    check("B3g. except SideEffectExecutionModeContractError:のbodyはbare `raise`のみ（1文）", len(_contract_handler_body_b3), 1)
    check_true("B3h. その1文がast.Raise（bare re-raise）である", isinstance(_contract_handler_body_b3[0], ast.Raise))
    check_true("B3i. bare raiseはexc引数を持たない（元の例外をそのまま再送出、変換なし）", _contract_handler_body_b3[0].exc is None)
print()


# =====================================================================
# Part C: §28.-33 Invariant #11 残存clause
# =====================================================================

print("[C1] record_not_applicable() duplicate: 2回目呼び出しでapplicability_store.create()が一切呼ばれない（call countで直接確認）")

from side_effect_safety import (  # noqa: E402
    JsonMediaUploadApplicabilityStore,
    ProtectedSideEffectKind,
    SideEffectOperationIdentity,
    SideEffectSite,
    build_media_upload_safety_coordinator,
)
from side_effect_safety.media_upload_attempt_context_store import JsonMediaUploadAttemptContextStore  # noqa: E402
from article_media_upload_state.article_media_upload_state_manager import ArticleMediaUploadStateManager  # noqa: E402
from article_media_upload_state.json_article_media_upload_state_store import JsonArticleMediaUploadStateStore  # noqa: E402
from side_effect_safety.errors import MediaUploadSafetyTransitionError  # noqa: E402

tmp_c1 = Path(tempfile.mkdtemp(prefix="v6_32_23_c1_"))
real_applicability_store_c1 = JsonMediaUploadApplicabilityStore(tmp_c1 / "applicability")

create_call_count_c1 = [0]
_original_create_c1 = real_applicability_store_c1.create


def _counting_create(*args, **kwargs):
    create_call_count_c1[0] += 1
    return _original_create_c1(*args, **kwargs)


real_applicability_store_c1.create = _counting_create

media_manager_c1 = ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(tmp_c1 / "media"))
coordinator_c1 = build_media_upload_safety_coordinator(
    media_upload_manager=media_manager_c1,
    applicability_store=real_applicability_store_c1,
    attempt_context_store=JsonMediaUploadAttemptContextStore(tmp_c1 / "context"),
    locks_dir=tmp_c1 / "locks",
)
_identity_c1 = SideEffectOperationIdentity(
    root_run_id="root-23c1", attempt_ordinal=1, operation_kind=ProtectedSideEffectKind.MEDIA_UPLOAD,
    effect_site=SideEffectSite.NEWS_STEP, operation_instance_key="art-c1",
)

first_c1 = coordinator_c1.record_not_applicable(_identity_c1, "member-23c1")
check_true("C1a. 1回目は成功する", first_c1 is not None)
check("C1b. 1回目呼び出し後、applicability_store.create()は1回だけ呼ばれる", create_call_count_c1[0], 1)

raised_c1 = None
try:
    coordinator_c1.record_not_applicable(_identity_c1, "member-23c1")
except MediaUploadSafetyTransitionError as e:
    raised_c1 = e

check_true("C1c. 2回目はMediaUploadSafetyTransitionError（duplicate）", raised_c1 is not None)
check(
    "C1d. 2回目呼び出し後もapplicability_store.create()の呼び出し回数は1のまま（追加のdurable write = 0）",
    create_call_count_c1[0], 1,
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
