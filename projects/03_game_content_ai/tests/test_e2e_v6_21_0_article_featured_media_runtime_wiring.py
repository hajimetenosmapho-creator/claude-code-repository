"""
E2E テスト: v6.21.0 Article Featured Media Runtime Wiring

Source of Truth:
    docs/design/article_featured_media_runtime_wiring.md
    （Architecture Review 2：Approved with Suggestions／Architecture Amendment 2、
      5.6節、および Release Review Findings Remediation）

本テストは実OpenAI API・実WordPress API・実HTTP通信・実RSS収集・実課金の
いずれも発生させない（設計書14.1節・N-10）。main() は Claude API・RSS収集を
伴うため実行しない（設計書14.3節）。かわりに次の2手法を組み合わせて検証する：

    (a) main.py が切り出した module-level private helper
        `_apply_featured_media_step()` / `_handle_featured_media_failure()` を
        Fake依存で直接駆動する（Behavioral）。
    (b) 記事ループ内に残る glue（`wp_failed_count` 加算・`continue`・呼び出し
        位置）は helper へ切り出せないため、AST構造解析で契約を検証する
        （Structural）。

Scenario構成:
    GATEOFF-   Gate OFF時、helperがarticleを素通しする（Behavioral）
    APPLIED-   生成成功時、featured_media_idが更新された新しいArticleDataが返る（Behavioral）
    CONT-      CONTINUE対象reasonで例外を送出せず、articleが未改変で返る（Behavioral／NOMUT）
    PROP-      PROPAGATE対象reasonで、注入した例外オブジェクトが無変換で送出される（Behavioral／IDENT）
    MDOK-      PROPAGATE後処理：Markdown保存成功→saved_files反映・failed logging（Behavioral／F-3a・F-3c）
    MDOK-OBS-  PROPAGATE後処理：observation非Noneがcategory/action/reasonとしてlog_article()へ
               正しく転記されること（Behavioral。Code Review Major-2対応。DI-5、v6.25.0）
    MDFAIL-    PROPAGATE後処理：Markdown保存失敗（OSError／success=False）でも例外を出さず継続（Behavioral／F-3b）
    NOWP-      PROPAGATE後処理がWordPress出力へ一切到達しない（Behavioral＋Structural／F-1）
    SEC-       例外message・例外class名がconsole／ArticleLogへ現れない（Behavioral／SEC-2・SEC-3・SEC-8）
    WIRE-      呼び出し位置がArticleData構築の後・save_all()の前であること（Structural／AST）
    GUARD-     main.pyがarticle_featured_media_runtime以外の画像系package名を参照しないこと（Structural／AST）
    NODYN-     main.pyが動的import・package名の文字列リテラルを用いないこと（Structural／AST）
    LOOP-      記事ループのPROPAGATE glue：helper呼び出し・counter加算・continue（Structural／AST）
    CONFIG-    Gate ON かつ必須env欠落時、起動時にexit(1)相当で停止し、値がmessageに現れないこと
               （hermetic subprocess。OPENAI_API_KEY欠落／WP_*欠落の2 variant）
    NOIMPACT-  変更禁止範囲（image_resolver.py・src/配下・scripts/・requirements.txt・
               .env.example・既存tests）が、Release 6.21.0 baseline commit
               （8d89506）から1バイトも変わっていないこと
               （`git diff --quiet <baseline> -- <path>`）。baselineを固定して
               いるため、未stage・stage後・commit後のいずれの状態でも同一の
               判定が得られる恒久guardである（HEAD基準では commit 後に
               「未コミット変更がないこと」しか検証できず不十分）

実行方法:
    cd projects/03_game_content_ai
    venv\\Scripts\\python.exe tests/test_e2e_v6_21_0_article_featured_media_runtime_wiring.py
"""
import ast
import contextlib
import io
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

MAIN_FILE = PROJECT_ROOT / "main.py"
PYTHON_EXE = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"

# ─── テスト用ユーティリティ（v6.13.0〜v6.20.0 precedentを踏襲） ───

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
    check(label, value, True)


def check_false(label: str, value: bool):
    check(label, value, False)


def check_contains(label: str, text, keyword: str):
    check(label, keyword in str(text), True)


# ─── AST解析ユーティリティ（v6.13.0〜v6.20.0 precedentを踏襲） ───


def get_import_roots(file_path: Path) -> set:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            roots.add(node.module.split(".")[0])
    return roots


def find_call_lines(tree, name: str) -> list:
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == name:
                lines.append(node.lineno)
            elif isinstance(func, ast.Attribute) and func.attr == name:
                lines.append(node.lineno)
    return sorted(lines)


def find_dynamic_import_lines(tree) -> list:
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == "__import__":
                lines.append(node.lineno)
            elif isinstance(func, ast.Attribute) and func.attr == "import_module":
                lines.append(node.lineno)
    return lines


def find_function_def(tree, name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


def walk_stmts(stmts):
    for s in stmts:
        yield from ast.walk(s)


def contains_call_to(stmts, call_name: str) -> bool:
    for node in walk_stmts(stmts):
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id == call_name:
                return True
    return False


def find_try_wrapping_call(scope_node, call_name: str):
    for node in ast.walk(scope_node):
        if isinstance(node, ast.Try) and contains_call_to(node.body, call_name):
            return node
    return None


def attribute_call_names(nodes) -> list:
    return [
        n.func.attr
        for n in nodes
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    ]


def find_calls_to(stmts, name: str) -> list:
    """stmts内で、関数名（Name.id または Attribute.attr）がnameであるast.Callのリストを返す。"""
    calls = []
    for n in walk_stmts(stmts):
        if isinstance(n, ast.Call):
            func = n.func
            if isinstance(func, ast.Name) and func.id == name:
                calls.append(n)
            elif isinstance(func, ast.Attribute) and func.attr == name:
                calls.append(n)
    return calls


def find_name_loads(stmts, name: str) -> list:
    """stmts内で、Load文脈のName(id=name)ノードのリストを返す。"""
    return [
        n
        for n in walk_stmts(stmts)
        if isinstance(n, ast.Name) and n.id == name and isinstance(n.ctx, ast.Load)
    ]


print("=" * 60)
print("v6.21.0 Article Featured Media Runtime Wiring E2E テスト")
print("=" * 60)
print()

# ─── main.py の import（module-levelコードのみ実行。main()は呼ばない） ───

import main  # noqa: E402
from outputs import ArticleData, SaveResult  # noqa: E402
from collector import NewsItem  # noqa: E402
from publishing_config import PublishStatus  # noqa: E402
from openai_image_generation import (  # noqa: E402
    OpenAIImageGenerationError,
    OpenAIImageGenerationErrorReason,
)
from image_generation_fallback_policy import (  # noqa: E402
    ImageGenerationFailureCategory,
    ImageGenerationFallbackAction,
)
from article_featured_media_runtime import FeaturedMediaFailureObservation  # noqa: E402

ArticleFeaturedMediaRuntime = main.ArticleFeaturedMediaRuntime
ArticleFeaturedMediaRuntimeStatus = main.ArticleFeaturedMediaRuntimeStatus


# ─── テストfixture builder（v6.20.0 precedent踏襲） ───


def make_news_item(title: str = "PS6正式発表") -> NewsItem:
    return NewsItem(
        title=title,
        url="https://blog.playstation.com/test",
        summary="PlayStation 6 が正式に発表されました。",
        source="PlayStation Blog",
        published_at="2026-07-18",
        image_candidates=[],
    )


def make_article(**overrides) -> ArticleData:
    defaults = dict(
        item=make_news_item(),
        importance="S",
        seo_title="PS6が正式発表",
        article_body="PS6が発表されました。",
        x_post="PS6発表！ https://example.com/ps6/",
        featured_image_url="https://example.com/ps6.png",
        excerpt="PS6が発表されました。",
        meta_description="PS6が発表されました。",
        slug="ps6-announced-20260718",
        featured_media_id=0,
        publish_status=PublishStatus.DRAFT,
    )
    defaults.update(overrides)
    return ArticleData(**defaults)


# ─── Test Double（Fake／sentinel、test file内限定。production packageへは配置しない） ───


class FakeOrchestrator:
    """root.orchestrator の Fake。apply()の呼び出しを記録し、指定されたresult／errorを返す。"""

    def __init__(self, *, result=None, error=None):
        self.calls = []
        self._result = result
        self._error = error

    def apply(self, article, prompt, filename):
        self.calls.append((article, prompt, filename))
        if self._error is not None:
            raise self._error
        return self._result


class FakeCompositionRoot:
    """ArticleFeaturedMediaCompositionRoot の Fake。Duck Typingのためisinstance検証は行われない。"""

    def __init__(self, *, orchestrator, image_mime_type="image/png", available=True):
        self.orchestrator = orchestrator
        self.image_mime_type = image_mime_type
        self._available = available

    def is_available(self):
        return self._available


class FakeMarkdownOutput:
    """MarkdownOutput の Fake。save()の呼び出しを記録し、指定されたSaveResult／例外を返す。"""

    def __init__(self, *, result=None, error=None):
        self.calls = []
        self._result = result
        self._error = error

    def save(self, article):
        self.calls.append(article)
        if self._error is not None:
            raise self._error
        return self._result


class FakeLogManager:
    """LogManager の Fake。log_article()へ渡された引数をそのまま記録する。"""

    def __init__(self):
        self.calls = []

    def log_article(self, **kwargs):
        self.calls.append(kwargs)


def run_apply_step_capturing_stdout(runtime, article):
    """_apply_featured_media_step()を呼び、(戻り値, 例外, stdout)を返す。

    v6.25.0（DI-5）: 戻り値は ArticleFeaturedMediaRuntimeResult そのもの
    （article単体ではない）。呼び出し元は result.article／result.status／
    result.observation を個別に参照する。
    """
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            result = main._apply_featured_media_step(runtime, article)
        return result, None, buf.getvalue()
    except Exception as exc:
        return None, exc, buf.getvalue()


def run_failure_handler_capturing_stdout(markdown_output, log_manager, article, saved_files, **kwargs):
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            main._handle_featured_media_failure(
                markdown_output, log_manager, article, saved_files, **kwargs
            )
        return None, buf.getvalue()
    except BaseException as exc:
        return exc, buf.getvalue()


_HANDLER_KWARGS = dict(
    importance="S",
    seo_title="PS6が正式発表",
    wp_public_url="https://example.com/ps6/",
    x_post_status=None,
)


# =====================================================================
# GATEOFF: Gate OFF時、helperがarticleを素通しする
# =====================================================================

print("[GATEOFF] Gate OFF時の素通し")

_gateoff_runtime = ArticleFeaturedMediaRuntime(
    FakeCompositionRoot(orchestrator=None, available=False)
)
_gateoff_input = make_article()
_gateoff_result, _gateoff_exc, _gateoff_stdout = run_apply_step_capturing_stdout(
    _gateoff_runtime, _gateoff_input
)
check_true("GATEOFF-NOEXC. 例外が発生しない", _gateoff_exc is None)
check_true(
    "GATEOFF-STATUS-DISABLED. status==DISABLED（v6.25.0）",
    _gateoff_result.status is ArticleFeaturedMediaRuntimeStatus.DISABLED,
)
check_true(
    "GATEOFF-SAME-OBJECT. articleが同一object（素通し）",
    _gateoff_result.article is _gateoff_input,
)
check(
    "GATEOFF-MEDIA-ID-UNCHANGED. featured_media_idが未改変",
    _gateoff_result.article.featured_media_id,
    _gateoff_input.featured_media_id,
)
check(
    "GATEOFF-OBSERVATION-NONE. observationがNone（v6.25.0）",
    _gateoff_result.observation,
    None,
)
check("GATEOFF-NO-OUTPUT. console出力なし", _gateoff_stdout, "")
print()

# =====================================================================
# APPLIED: 生成成功時、featured_media_idが更新される
# =====================================================================

print("[APPLIED] 生成成功時のfeatured_media_id反映")

_applied_orch = FakeOrchestrator(result=make_article(featured_media_id=999))
_applied_runtime = ArticleFeaturedMediaRuntime(
    FakeCompositionRoot(orchestrator=_applied_orch, available=True)
)
_applied_input = make_article()
_applied_result, _applied_exc, _applied_stdout = run_apply_step_capturing_stdout(
    _applied_runtime, _applied_input
)
check_true("APPLIED-NOEXC. 例外が発生しない", _applied_exc is None)
check_true(
    "APPLIED-STATUS. status==APPLIED（v6.25.0）",
    _applied_result.status is ArticleFeaturedMediaRuntimeStatus.APPLIED,
)
check_false(
    "APPLIED-NEW-OBJECT. articleが新しいobjectに置き換わる",
    _applied_result.article is _applied_input,
)
check(
    "APPLIED-MEDIA-ID. featured_media_idが生成画像のmedia_id",
    _applied_result.article.featured_media_id,
    999,
)
check(
    "APPLIED-OBSERVATION-NONE. observationがNone（v6.25.0）",
    _applied_result.observation,
    None,
)
check("APPLIED-ORCH-CALLED-ONCE. orchestrator.apply()が1回呼ばれる", len(_applied_orch.calls), 1)
print()

# =====================================================================
# CONT: CONTINUE対象reasonで継続する（NOMUT含む）
# =====================================================================

print("[CONT] CONTINUE対象reasonでの画像なし継続")

_CONT_SECRET_MARKER = "SECRET_TOKEN_MARKER_CONT_9f3a"
_cont_error = OpenAIImageGenerationError(
    f"timeout occurred ({_CONT_SECRET_MARKER})", OpenAIImageGenerationErrorReason.TIMEOUT
)
_cont_runtime = ArticleFeaturedMediaRuntime(
    FakeCompositionRoot(orchestrator=FakeOrchestrator(error=_cont_error), available=True)
)
_cont_input = make_article()
_cont_result, _cont_exc, _cont_stdout = run_apply_step_capturing_stdout(_cont_runtime, _cont_input)
check_true("CONT-NOEXC. 例外を送出せず継続する", _cont_exc is None)
check_true(
    "CONT-STATUS. status==CONTINUED_WITHOUT_FEATURED_MEDIA（v6.25.0）",
    _cont_result.status is ArticleFeaturedMediaRuntimeStatus.CONTINUED_WITHOUT_FEATURED_MEDIA,
)
check_true(
    "CONT-SAME-OBJECT（NOMUT）. articleが同一object・未改変",
    _cont_result.article is _cont_input,
)
check_contains(
    "CONT-CONSOLE-CATEGORY. consoleにcategoryが1行出力される",
    _cont_stdout,
    ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED.value,
)
check_false(
    "CONT-SEC-NO-MARKER. 例外message原文がconsoleに現れない（SEC-2）",
    _CONT_SECRET_MARKER in _cont_stdout,
)
check_true(
    "CONT-OBSERVATION-NOT-NONE. observationが非None（v6.25.0）",
    _cont_result.observation is not None,
)
check(
    "CONT-OBSERVATION-CATEGORY. observation.categoryがIMAGE_GENERATION_FAILED（v6.25.0）",
    _cont_result.observation.category,
    ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED,
)
check(
    "CONT-OBSERVATION-REASON. observation.reasonが'timeout'（v6.25.0）",
    _cont_result.observation.reason,
    OpenAIImageGenerationErrorReason.TIMEOUT.value,
)
check_false(
    "CONT-OBSERVATION-SEC-NO-MARKER. observation.reasonに例外message原文が現れない（SEC-2）",
    _CONT_SECRET_MARKER in (_cont_result.observation.reason or ""),
)
print()

# =====================================================================
# PROP: PROPAGATE対象reasonで元例外が無変換で送出される（IDENT）
# =====================================================================

print("[PROP] PROPAGATE対象reasonでの元例外伝播")

_PROP_SECRET_MARKER = "SECRET_TOKEN_MARKER_PROP_7c1e"
_prop_error = OpenAIImageGenerationError(
    f"request rejected ({_PROP_SECRET_MARKER})", OpenAIImageGenerationErrorReason.REQUEST_REJECTED
)
_prop_runtime = ArticleFeaturedMediaRuntime(
    FakeCompositionRoot(orchestrator=FakeOrchestrator(error=_prop_error), available=True)
)
_prop_input = make_article()
_prop_result, _prop_exc, _prop_stdout = run_apply_step_capturing_stdout(_prop_runtime, _prop_input)
check_true("PROP-RAISED. 例外が送出される", _prop_exc is not None)
check_true(
    "PROP-IDENT. 送出された例外が注入した例外オブジェクトと同一（is比較・W-1）",
    _prop_exc is _prop_error,
)
check_true("PROP-CAUSE-UNTOUCHED. __cause__が加工されていない", _prop_exc.__cause__ is None)
check_contains(
    "PROP-MESSAGE-UNCHANGED. 元例外のmessageが不変",
    str(_prop_exc),
    _PROP_SECRET_MARKER,
)
check_false(
    "PROP-SEC-NO-MARKER. 例外message原文がhelper内でconsoleに出力されない（SEC-2）",
    _PROP_SECRET_MARKER in _prop_stdout,
)
print()

# =====================================================================
# MDOK: PROPAGATE後処理 — Markdown保存成功（F-3a・F-3c）
# =====================================================================

print("[MDOK] PROPAGATE後処理：Markdown保存成功")

_md_path = PROJECT_ROOT / "output" / "20260730_000000_FakeSource_S.md"
_mdok_output = FakeMarkdownOutput(
    result=SaveResult(success=True, output_type="file", edit_url=str(_md_path))
)
_mdok_log = FakeLogManager()
_mdok_saved_files = []
_mdok_article = make_article()
_mdok_exc, _mdok_stdout = run_failure_handler_capturing_stdout(
    _mdok_output, _mdok_log, _mdok_article, _mdok_saved_files, **_HANDLER_KWARGS
)

check_true("MDOK-NOEXC. 例外が外へ出ない", _mdok_exc is None)
check("MDOK-SAVE-CALLED-ONCE. Markdown save()が1回呼ばれる", len(_mdok_output.calls), 1)
check_true(
    "MDOK-SAVE-RECEIVES-SAME-ARTICLE. save()へ渡るarticleが同一object",
    _mdok_output.calls[0] is _mdok_article,
)
check(
    "MDOK-SAVEDFILES-APPENDED. saved_filesへ1件反映される（F-3c）",
    _mdok_saved_files,
    [("S", "PS6が正式発表", _md_path)],
)
check_contains("MDOK-CONSOLE-FILENAME. consoleに保存ファイル名が出る", _mdok_stdout, _md_path.name)
check_contains(
    "MDOK-CONSOLE-SKIPPED. consoleに投稿見送りの警告が出る（F-6）",
    _mdok_stdout,
    "投稿を見送りました",
)
check("MDOK-LOG-CALLED-ONCE. log_article()が1回呼ばれる", len(_mdok_log.calls), 1)
check('MDOK-LOG-RESULT-FAILED. result="failed"（F-4）', _mdok_log.calls[0].get("result"), "failed")
check("MDOK-LOG-POST-ID-NONE. post_id=None（F-4）", _mdok_log.calls[0].get("post_id"), None)
check(
    "MDOK-LOG-FIXED-LABEL. error_messageが固定ラベル（SEC-8）",
    _mdok_log.calls[0].get("error_message"),
    "featured media processing failed",
)
check_true(
    "MDOK-LOG-ARTICLE-IDENTITY. log_article()へ渡るarticleが同一object",
    _mdok_log.calls[0].get("article") is _mdok_article,
)
print()

# =====================================================================
# MDOK-OBS: PROPAGATE後処理 — observation非NoneがLogへ正しく転記される
# （Code Review Major-2対応。DI-5、v6.25.0）
# =====================================================================

print("[MDOK-OBS] observation非Noneがlog_article()へ正しく渡る")

_mdokobs_secret = "SECRET_MARKER_MDOK_OBS_4d7e"
_mdokobs_observation = FeaturedMediaFailureObservation(
    category=ImageGenerationFailureCategory.IMAGE_GENERATION_REQUEST_REJECTED,
    action=ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR,
    reason=OpenAIImageGenerationErrorReason.REQUEST_REJECTED.value,
)
_mdokobs_output = FakeMarkdownOutput(
    result=SaveResult(success=True, output_type="file", edit_url=str(_md_path))
)
_mdokobs_log = FakeLogManager()
_mdokobs_saved_files = []
_mdokobs_article = make_article()
_mdokobs_exc, _mdokobs_stdout = run_failure_handler_capturing_stdout(
    _mdokobs_output, _mdokobs_log, _mdokobs_article, _mdokobs_saved_files,
    **_HANDLER_KWARGS, observation=_mdokobs_observation,
)

check_true("MDOK-OBS-NOEXC. 例外が外へ出ない", _mdokobs_exc is None)
check("MDOK-OBS-LOG-CALLED-ONCE. log_article()が1回呼ばれる", len(_mdokobs_log.calls), 1)
check(
    "MDOK-OBS-CATEGORY. featured_media_categoryが正しく渡る",
    _mdokobs_log.calls[0].get("featured_media_category"),
    "IMAGE_GENERATION_REQUEST_REJECTED",
)
check(
    "MDOK-OBS-ACTION. featured_media_actionが正しく渡る",
    _mdokobs_log.calls[0].get("featured_media_action"),
    "PROPAGATE_ORIGINAL_ERROR",
)
check(
    "MDOK-OBS-REASON. featured_media_reasonが正しく渡る",
    _mdokobs_log.calls[0].get("featured_media_reason"),
    "request_rejected",
)
check_false(
    "MDOK-OBS-SEC-NO-MARKER. featured_media_reasonに秘密情報が含まれない",
    _mdokobs_secret in (_mdokobs_log.calls[0].get("featured_media_reason") or ""),
)
check(
    "MDOK-OBS-ERROR-MESSAGE-STILL-FIXED. error_messageは引き続き固定ラベルのまま（SEC-8）",
    _mdokobs_log.calls[0].get("error_message"),
    "featured media processing failed",
)

# observation=None（既定値）の場合は既存どおり3フィールドとも""であることの対照
_mdoknone_log = FakeLogManager()
run_failure_handler_capturing_stdout(
    FakeMarkdownOutput(result=SaveResult(success=True, output_type="file", edit_url=str(_md_path))),
    _mdoknone_log, make_article(), [], **_HANDLER_KWARGS,
)
check(
    "MDOK-OBS-NONE-DEFAULT-EMPTY. observation省略時は3フィールドとも''（後方互換）",
    (
        _mdoknone_log.calls[0].get("featured_media_category"),
        _mdoknone_log.calls[0].get("featured_media_action"),
        _mdoknone_log.calls[0].get("featured_media_reason"),
    ),
    ("", "", ""),
)
print()

# =====================================================================
# MDFAIL: PROPAGATE後処理 — Markdown保存失敗（F-3b）
# =====================================================================

print("[MDFAIL] PROPAGATE後処理：Markdown保存失敗")

_MD_SECRET_MARKER = "SECRET_DISK_PATH_MARKER_5b2d"
_mdfail_output = FakeMarkdownOutput(error=OSError(f"No space left on device ({_MD_SECRET_MARKER})"))
_mdfail_log = FakeLogManager()
_mdfail_saved_files = []
_mdfail_article = make_article()
_mdfail_exc, _mdfail_stdout = run_failure_handler_capturing_stdout(
    _mdfail_output, _mdfail_log, _mdfail_article, _mdfail_saved_files, **_HANDLER_KWARGS
)

check_true("MDFAIL-NOEXC. OSErrorが外へ出ない（run全体を止めない）", _mdfail_exc is None)
check("MDFAIL-SAVEDFILES-EMPTY. saved_filesへ反映されない（F-3c）", _mdfail_saved_files, [])
check_contains(
    "MDFAIL-CONSOLE-FIXED-LABEL. 固定ラベルの警告が出る（F-3b）",
    _mdfail_stdout,
    "Markdownファイルの保存に失敗しました",
)
check_false(
    "MDFAIL-SEC-NO-MARKER. OSErrorのmessage原文がconsoleに現れない（SEC-2）",
    _MD_SECRET_MARKER in _mdfail_stdout,
)
check_false(
    "MDFAIL-SEC-NO-CLASSNAME. 例外class名OSErrorがconsoleに現れない（SEC-3）",
    "OSError" in _mdfail_stdout,
)
check("MDFAIL-LOG-CALLED-ONCE. log_article()が1回呼ばれる（F-4）", len(_mdfail_log.calls), 1)
check(
    'MDFAIL-LOG-RESULT-FAILED. result="failed"',
    _mdfail_log.calls[0].get("result"),
    "failed",
)
check_false(
    "MDFAIL-SEC-LOG-NO-MARKER. ArticleLog引数に例外message原文が現れない（SEC-8）",
    _MD_SECRET_MARKER in repr(_mdfail_log.calls[0]),
)

# SaveResult.success=False（例外を伴わない失敗）も同じ扱いになること
_mdns_output = FakeMarkdownOutput(result=SaveResult(success=False, output_type="file", edit_url=None))
_mdns_log = FakeLogManager()
_mdns_saved_files = []
_mdns_exc, _mdns_stdout = run_failure_handler_capturing_stdout(
    _mdns_output, _mdns_log, make_article(), _mdns_saved_files, **_HANDLER_KWARGS
)
check_true("MDFAIL-NOSUCCESS-NOEXC. success=Falseでも例外が外へ出ない", _mdns_exc is None)
check("MDFAIL-NOSUCCESS-SAVEDFILES-EMPTY. saved_filesへ反映されない", _mdns_saved_files, [])
check(
    "MDFAIL-NOSUCCESS-LOG-FAILED. failedとして記録される",
    _mdns_log.calls[0].get("result"),
    "failed",
)
print()

# =====================================================================
# main.py 構造解析（AST）の準備
# =====================================================================

_main_source = MAIN_FILE.read_text(encoding="utf-8")
_main_tree = ast.parse(_main_source, filename=str(MAIN_FILE))
_handler_func = find_function_def(_main_tree, "_handle_featured_media_failure")

# =====================================================================
# NOWP: PROPAGATE後処理がWordPress出力へ到達しない（F-1）
# =====================================================================

print("[NOWP] PROPAGATE後処理のWordPress非到達")

# Behavioral: 上記MDOK-／MDFAIL-はWordPress出力objectを一切渡していないため、
# 構造的に投稿は不可能である。Structuralにもそれを固定する。
check_true("NOWP-HANDLER-EXISTS. _handle_featured_media_failureが存在する", _handler_func is not None)
if _handler_func is not None:
    _handler_func_nodes = list(ast.walk(_handler_func))
    _handler_func_attr_calls = attribute_call_names(_handler_func_nodes)
    check_false(
        "NOWP-NO-SAVE-ALL. helper内でsave_all()が呼ばれない",
        "save_all" in _handler_func_attr_calls,
    )
    _handler_names = {n.id for n in _handler_func_nodes if isinstance(n, ast.Name)}
    for _forbidden in ("WordPressOutput", "output_manager", "OutputManager"):
        check_false(
            f"NOWP-NO-{_forbidden}. helperが{_forbidden}を参照しない",
            _forbidden in _handler_names,
        )
    # helper内のMarkdown保存が独立したtry/except Exceptionで保護されていること（F-3b）
    _handler_try = find_try_wrapping_call(_handler_func, "save") or next(
        (n for n in ast.walk(_handler_func) if isinstance(n, ast.Try)), None
    )
    check_true("NOWP-INNER-TRY-EXISTS. helper内のMarkdown保存がtryで保護される", _handler_try is not None)
    if _handler_try is not None:
        check("NOWP-INNER-HANDLER-COUNT. ExceptHandlerが1件", len(_handler_try.handlers), 1)
        _inner_handler = _handler_try.handlers[0]
        check_true(
            "NOWP-INNER-HANDLER-TYPE. Exceptionを捕捉する（BaseExceptionではない）",
            isinstance(_inner_handler.type, ast.Name) and _inner_handler.type.id == "Exception",
        )
        check_true(
            "NOWP-INNER-NO-BINDING. 例外を変数へ束縛しない（SEC-2／SEC-3の構造的保証）",
            _inner_handler.name is None,
        )
print()

# =====================================================================
# WIRE: 呼び出し位置（ArticleData構築の後・save_all()の前）
# =====================================================================

print("[WIRE] 呼び出し位置")

_articledata_lines = find_call_lines(_main_tree, "ArticleData")
_apply_lines = find_call_lines(_main_tree, "_apply_featured_media_step")
_saveall_lines = find_call_lines(_main_tree, "save_all")

check("WIRE-ARTICLEDATA-COUNT. ArticleData構築が1件", len(_articledata_lines), 1)
check("WIRE-APPLY-COUNT. _apply_featured_media_step呼び出しが1件", len(_apply_lines), 1)
check("WIRE-SAVEALL-COUNT. save_all呼び出しが1件", len(_saveall_lines), 1)
check_true(
    "WIRE-ORDER. ArticleData構築 < apply呼び出し < save_all呼び出し",
    bool(_articledata_lines and _apply_lines and _saveall_lines)
    and _articledata_lines[0] < _apply_lines[0] < _saveall_lines[0],
)
print()

# =====================================================================
# GUARD: main.pyがarticle_featured_media_runtime以外の画像系packageを参照しない
# =====================================================================

print("[GUARD] main.pyの画像系package参照")

_main_roots = get_import_roots(MAIN_FILE)
check_true(
    "GUARD-FACADE-IMPORTED. main.pyがarticle_featured_media_runtimeをimportしている",
    "article_featured_media_runtime" in _main_roots,
)
_forbidden_image_packages = {
    "article_featured_media",
    "article_featured_media_orchestration",
    "image_generation_config",
    "generated_image_filename_policy",
    "article_image_prompt_construction",
    "article_featured_media_composition",
    "image_generation_fallback_policy",
    "openai_image_generation",
    "wordpress_media",
    "generated_image_wordpress_media",
    "ai_image_generation",
}
_violating_roots = sorted(_forbidden_image_packages & _main_roots)
check(
    "GUARD-NO-OTHER-IMAGE-PACKAGE. main.pyがFacade以外の画像系packageを参照しない",
    _violating_roots,
    [],
)
print()

# =====================================================================
# NODYN: main.pyが動的import・package名の文字列リテラルを用いない
# =====================================================================

print("[NODYN] 動的import・文字列リテラル禁止")

_dynamic_lines = find_dynamic_import_lines(_main_tree)
check("NODYN-NO-DYNAMIC-IMPORT. importlib.import_module()／__import__()が使われていない", _dynamic_lines, [])

_bare_literal_hits = re.findall(r'["\']article_featured_media["\']', _main_source)
check(
    "NODYN-NO-BARE-STRING-LITERAL. 低レベルpackage名が文字列リテラル単体で出現しない",
    _bare_literal_hits,
    [],
)

# Facade名についても、文字列リテラル経由の参照を禁止する
# （AST精緻化により静的import以外が検出対象外となった範囲をProduction Code契約で塞ぐ）
_string_literal_hits = sorted(
    {
        n.value
        for n in ast.walk(_main_tree)
        if isinstance(n, ast.Constant)
        and isinstance(n.value, str)
        and "article_featured_media" in n.value
    }
)
check(
    "NODYN-NO-PACKAGE-NAME-IN-STRING. package名を含む文字列リテラルが存在しない",
    _string_literal_hits,
    [],
)
print()

# =====================================================================
# LOOP: 記事ループのPROPAGATE glue（AST構造検証）
# =====================================================================

print("[LOOP] 記事ループのPROPAGATE glue")

_wiring_try = find_try_wrapping_call(_main_tree, "_apply_featured_media_step")
check_true("LOOP-TRY-EXISTS. _apply_featured_media_stepを囲むtryが存在する", _wiring_try is not None)

if _wiring_try is not None:
    check("LOOP-HANDLER-COUNT. ExceptHandlerが1件のみ", len(_wiring_try.handlers), 1)
    _handler = _wiring_try.handlers[0]
    check_true(
        "LOOP-HANDLER-TYPE-EXCEPTION. 捕捉型がExceptionである（BaseExceptionを含まない・W-4）",
        isinstance(_handler.type, ast.Name) and _handler.type.id == "Exception",
    )
    # v6.25.0（DI-5）: 例外は`exc`として束縛される（classify_propagated_failure()
    # へ渡すため）。SEC-2／SEC-3の本来の保証（str(exc)／class名をconsole・log・
    # reportへ出力しない）を、「束縛しない」という実装詳細ではなく、束縛された
    # excの使用形そのものをpositive allow-list方式で機械検証する
    # （v6.23.0 I-EXC-1・v6.24.0 I-VAL-1と同型）。
    check(
        "LOOP-HANDLER-BINDS-EXC. 例外がexcという名前で束縛される（v6.25.0）",
        _handler.name,
        "exc",
    )

    _exc_name_loads = find_name_loads(_handler.body, "exc")
    check_true(
        "LOOP-HANDLER-EXC-USED. excが少なくとも1回参照される",
        len(_exc_name_loads) > 0,
    )

    _str_or_repr_calls = [
        n
        for n in walk_stmts(_handler.body)
        if isinstance(n, ast.Call)
        and isinstance(n.func, ast.Name)
        and n.func.id in ("str", "repr")
        and any(isinstance(a, ast.Name) and a.id == "exc" for a in n.args)
    ]
    check(
        "SEC-NO-STR-EXC. str(exc)／repr(exc)が呼ばれていない",
        len(_str_or_repr_calls),
        0,
    )

    _typename_hits = []
    for _n in walk_stmts(_handler.body):
        if isinstance(_n, ast.Attribute) and _n.attr == "__name__":
            _value = _n.value
            if (
                isinstance(_value, ast.Call)
                and isinstance(_value.func, ast.Name)
                and _value.func.id == "type"
                and any(isinstance(a, ast.Name) and a.id == "exc" for a in _value.args)
            ):
                _typename_hits.append(_n)
            elif (
                isinstance(_value, ast.Attribute)
                and _value.attr == "__class__"
                and isinstance(_value.value, ast.Name)
                and _value.value.id == "exc"
            ):
                _typename_hits.append(_n)
    check(
        "SEC-NO-TYPENAME-EXC. type(exc).__name__／exc.__class__.__name__が参照されていない",
        len(_typename_hits),
        0,
    )

    _raw_exc_to_log_hits = []
    for _call_name in ("ArticleLogEntry", "log_article"):
        for _n in find_calls_to(_handler.body, _call_name):
            _all_args = list(_n.args) + [kw.value for kw in _n.keywords]
            if any(isinstance(a, ast.Name) and a.id == "exc" for a in _all_args):
                _raw_exc_to_log_hits.append(_n)
    check(
        "SEC-NO-RAW-EXC-TO-LOGENTRY. excがArticleLogEntry()／log_article()の引数として渡されていない",
        len(_raw_exc_to_log_hits),
        0,
    )

    _exc_mutation_hits = []
    for _n in walk_stmts(_handler.body):
        if isinstance(_n, (ast.Assign, ast.AugAssign)):
            _targets = _n.targets if isinstance(_n, ast.Assign) else [_n.target]
            for _t in _targets:
                if isinstance(_t, ast.Attribute) and isinstance(_t.value, ast.Name) and _t.value.id == "exc":
                    _exc_mutation_hits.append(_n)
        if isinstance(_n, ast.Call) and isinstance(_n.func, ast.Name) and _n.func.id == "setattr":
            if _n.args and isinstance(_n.args[0], ast.Name) and _n.args[0].id == "exc":
                _exc_mutation_hits.append(_n)
    check(
        "SEC-NO-EXC-MUTATION. excへの属性代入・setattr(exc, ...)が存在しない",
        len(_exc_mutation_hits),
        0,
    )

    _classify_calls = find_calls_to(_handler.body, "classify_propagated_failure")
    _allowed_exc_load_ids = {
        id(a)
        for _n in _classify_calls
        for a in _n.args
        if isinstance(a, ast.Name) and a.id == "exc"
    }
    _disallowed_exc_loads = [n for n in _exc_name_loads if id(n) not in _allowed_exc_load_ids]
    check(
        "SEC-EXC-USAGE-ALLOWLIST. excの唯一の許可された使用形がclassify_propagated_failure(exc)の引数位置である",
        len(_disallowed_exc_loads),
        0,
    )

    _handler_nodes = list(walk_stmts(_handler.body))
    check_true(
        "LOOP-HANDLER-CALLS-HELPER. handlerが_handle_featured_media_failureを呼ぶ",
        contains_call_to(_handler.body, "_handle_featured_media_failure"),
    )
    check_false(
        "LOOP-HANDLER-NO-SAVE-ALL. handler内でsave_all()が呼ばれない（F-1）",
        "save_all" in attribute_call_names(_handler_nodes),
    )

    _augassigns = [
        n
        for n in _handler_nodes
        if isinstance(n, ast.AugAssign) and isinstance(n.target, ast.Name) and n.target.id == "wp_failed_count"
    ]
    check("LOOP-WPFAILED-INCREMENTED. wp_failed_countへの加算が1件（F-5）", len(_augassigns), 1)
    if _augassigns:
        check_true("LOOP-WPFAILED-ADD. 加算演算がAddである", isinstance(_augassigns[0].op, ast.Add))

    _continues = [n for n in _handler_nodes if isinstance(n, ast.Continue)]
    check("LOOP-CONTINUE-PRESENT. handlerがcontinueを含む（run停止しない・F-7・W-2）", len(_continues), 1)

    _breaks = [n for n in _handler_nodes if isinstance(n, ast.Break)]
    _returns = [n for n in _handler_nodes if isinstance(n, ast.Return)]
    _exit_calls = [
        n
        for n in _handler_nodes
        if isinstance(n, ast.Call)
        and (
            (isinstance(n.func, ast.Attribute) and n.func.attr == "exit")
            or (isinstance(n.func, ast.Name) and n.func.id == "exit")
        )
    ]
    check("LOOP-NO-BREAK. handler内にbreakがない", _breaks, [])
    check("LOOP-NO-RETURN. handler内にreturnがない", _returns, [])
    check("LOOP-NO-SYSEXIT. handler内にsys.exit()がない", _exit_calls, [])
print()

# =====================================================================
# CONFIG: startup Fail Fast（hermetic subprocess）
# =====================================================================

print("[CONFIG] startup Fail Fast（hermetic subprocess）")

_DUMMY_ANTHROPIC_KEY = "dummy-test-anthropic-key-v6-21"
_DUMMY_OPENAI_KEY = "dummy-test-openai-key-v6-21-DO-NOT-LEAK"

# 画像系envはpop()せず空文字で明示的に無効化する。
# python-dotenvの既定（override=False）は「os.environに既に存在するキー」を
# .envから補完しないため、値が空でもキーが存在すれば.envの内容に影響されない。
_IMAGE_ENV_KEYS = (
    "AI_IMAGE_GENERATION_ENABLED",
    "OPENAI_API_KEY",
    "OPENAI_IMAGE_TIMEOUT_SECONDS",
    "WP_SITE_URL",
    "WP_USERNAME",
    "WP_APP_PASSWORD",
)


def build_config_env(**overrides) -> dict:
    env = os.environ.copy()
    for key in _IMAGE_ENV_KEYS:
        env[key] = ""
    env["ANTHROPIC_API_KEY"] = _DUMMY_ANTHROPIC_KEY
    env["LOG_ENABLED"] = "false"
    env["ANALYTICS_ENABLED"] = "false"
    env.update(overrides)
    return env


def run_main_startup(env: dict):
    return subprocess.run(
        [str(PYTHON_EXE), str(MAIN_FILE), "--max-articles", "0"],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
        env=env,
    )


check_true(f"CONFIG-PYTHON-EXE. 指定venvのpython.exeが存在する（{PYTHON_EXE.name}）", PYTHON_EXE.is_file())

if PYTHON_EXE.is_file():
    # variant 1: Gate ON かつ OPENAI_API_KEY 欠落 → OpenAI側でFail Fast
    _cfg1 = run_main_startup(build_config_env(AI_IMAGE_GENERATION_ENABLED="true"))
    _cfg1_out = _cfg1.stdout + _cfg1.stderr
    check_true(
        "CONFIG-OPENAI-NONZERO-EXIT. Gate ON・OPENAI_API_KEY欠落時に非0終了する",
        _cfg1.returncode != 0,
    )
    check_contains(
        "CONFIG-OPENAI-VARNAME. messageに環境変数名OPENAI_API_KEYが含まれる（S-7）",
        _cfg1_out,
        "OPENAI_API_KEY",
    )
    check_false(
        "CONFIG-OPENAI-NO-VALUE-LEAK. ダミーANTHROPIC_API_KEYの値がmessageに現れない（SEC-4）",
        _DUMMY_ANTHROPIC_KEY in _cfg1_out,
    )
    check_false(
        "CONFIG-OPENAI-NO-RSS. RSS収集へ到達していない（実HTTP通信なし・14.1節）",
        "RSS取得結果" in _cfg1_out,
    )

    # variant 2（m-3）: Gate ON・OPENAI設定済み・WP_* 欠落 → WordPress側でFail Fast（COMPAT-4）
    _cfg2 = run_main_startup(
        build_config_env(
            AI_IMAGE_GENERATION_ENABLED="true",
            OPENAI_API_KEY=_DUMMY_OPENAI_KEY,
            OPENAI_IMAGE_TIMEOUT_SECONDS="180",
        )
    )
    _cfg2_out = _cfg2.stdout + _cfg2.stderr
    check_true(
        "CONFIG-WP-NONZERO-EXIT. Gate ON・WP_*欠落時に非0終了する（COMPAT-4）",
        _cfg2.returncode != 0,
    )
    check_contains(
        "CONFIG-WP-VARNAME. messageに環境変数名WP_SITE_URLが含まれる（S-7）",
        _cfg2_out,
        "WP_SITE_URL",
    )
    check_false(
        "CONFIG-WP-NO-VALUE-LEAK. ダミーOPENAI_API_KEYの値がmessageに現れない（SEC-4）",
        _DUMMY_OPENAI_KEY in _cfg2_out,
    )
    check_false(
        "CONFIG-WP-NO-RSS. RSS収集へ到達していない（実HTTP通信なし・14.1節）",
        "RSS取得結果" in _cfg2_out,
    )
print()

# =====================================================================
# NOIMPACT: 変更禁止範囲の不変性（HEAD比較。staging/commit状態に依存しない）
# =====================================================================

print("[NOIMPACT] 変更禁止範囲の不変性（Release 6.21.0 baseline commit 基準）")

# Release 6.21.0 の baseline commit（v6.20.0 Release 完了時点）。
# HEAD 基準で比較すると、本Releaseを commit した後は「未コミット変更がないこと」しか
# 検証できず、保護対象へ誤った変更が commit 済みで混入した場合を検出できない。
# baseline commit を固定することで、未stage・stage後・commit後のいずれの状態でも
# 「Release 6.21.0 開始時点から保護対象が1バイトも変わっていないこと」を判定する。
BASELINE_COMMIT = "8d8950684a305bc93c824866578cb30c6b2e4fdd"

_git_version = subprocess.run(
    ["git", "--version"], cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=10
)
check("NOIMPACT-GIT-AVAILABLE. gitが利用できる（vacuous pass防止）", _git_version.returncode, 0)

_baseline_proc = subprocess.run(
    ["git", "rev-parse", "--verify", f"{BASELINE_COMMIT}^{{commit}}"],
    cwd=str(PROJECT_ROOT),
    capture_output=True,
    text=True,
    timeout=30,
)
check(
    "NOIMPACT-BASELINE-RESOLVABLE. Release 6.21.0 baseline commitが解決できる（vacuous pass防止）",
    _baseline_proc.returncode,
    0,
)

# 設計書15.3節「変更禁止範囲」に対応する対象一覧。
# DEF-6.23-9（v6.26.0）により、_protected_paths・_allowed_source_changes・
# _allowed_test_changes は tests/zero_diff_guard_registry.py（共有レジストリ）
# 側で一元管理する。GR-1（削除しない）・GR-9（ratchet構造）の性質は、
# レジストリ側のRELEASE_ORDER上のindex比較としてそのまま保たれる。
# 本guard自身の値・判定結果はrefactor前と完全一致する
# （tests/test_e2e_v6_26_0_zero_diff_guard_registry_foundation.py で固定検証）。
import zero_diff_guard_registry as _guard_registry  # noqa: E402

_protected_paths = list(_guard_registry.PROTECTED_PATHS)
_allowed_source_changes = _guard_registry.allowed_source_changes_for("v6.21.0")

for _rel in _protected_paths:
    # vacuous pass防止その1：検査対象が作業ツリーに実在すること
    check_true(f"NOIMPACT-EXISTS[{_rel}]. 検査対象が作業ツリーに実在する", (PROJECT_ROOT / _rel).exists())
    # vacuous pass防止その2：baseline commit に追跡ファイルが実在すること
    # （pathspecの綴り誤り・対象消滅による「差分なし」の空振りPASSを防ぐ）
    _ls_proc = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", BASELINE_COMMIT, "--", _rel],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    check_true(
        f"NOIMPACT-BASELINE-TRACKED[{_rel}]. baseline commitに追跡ファイルが存在する",
        _ls_proc.returncode == 0 and bool(_ls_proc.stdout.strip()),
    )
    # baseline commit と作業ツリーの差分ファイル集合が allow-list の範囲内であること
    # （containment: changed ⊆ allowed）。allowed が空集合の場合、差分ゼロと論理的に
    # 等価であり検査強度は不変（設計書11.7.1節）。--relative により project root 相対
    # の POSIX パスを git 自身に生成させる（v6.21.0 の basename 正規化より厳密）。
    _scope_diff_proc = subprocess.run(
        ["git", "diff", "--name-only", "--relative", BASELINE_COMMIT, "--", _rel],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    _scope_changed = {line.strip() for line in _scope_diff_proc.stdout.splitlines() if line.strip()}
    _scope_allowed = _allowed_source_changes.get(_rel, frozenset())
    check(
        f"NOIMPACT-SCOPE[{_rel}]. baseline commitからの差分がallow-listの範囲内である",
        sorted(_scope_changed - _scope_allowed),
        [],
    )

# 既存testsは、共有レジストリ（DEF-6.23-9）が本Release（v6.21.0）以降の
# window として合成する集合の範囲内以外に差分があってはならない（設計書11.7.3節）
_allowed_test_changes = set(_guard_registry.allowed_test_changes_for("v6.21.0"))
_tests_diff = subprocess.run(
    ["git", "diff", "--name-only", BASELINE_COMMIT, "--", "tests"],
    cwd=str(PROJECT_ROOT),
    capture_output=True,
    text=True,
    timeout=30,
)
# git は repository root 相対のパスを返すため、ファイル名へ正規化して比較する
_changed_tests = {
    Path(line.strip().replace("\\", "/")).name
    for line in _tests_diff.stdout.splitlines()
    if line.strip()
}
check(
    "NOIMPACT-TESTS-SCOPE. tests/の差分がallow-listの範囲内である"
    "（GR-7に従い許容件数はラベルへ埋め込まない）",
    sorted(_changed_tests - _allowed_test_changes),
    [],
)
print()

# ─── 結果サマリー ───
print("=" * 60)
total = len(results_log)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = total - passed
print(f"合計: {total}  PASS: {passed}  FAIL: {failed}")
if failed:
    print()
    print("FAILしたテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")
print("=" * 60)

sys.exit(0 if failed == 0 else 1)
