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
from image_generation_fallback_policy import ImageGenerationFailureCategory  # noqa: E402

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
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            result_article = main._apply_featured_media_step(runtime, article)
        return result_article, None, buf.getvalue()
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
    "GATEOFF-SAME-OBJECT. articleが同一object（素通し）",
    _gateoff_result is _gateoff_input,
)
check(
    "GATEOFF-MEDIA-ID-UNCHANGED. featured_media_idが未改変",
    _gateoff_result.featured_media_id,
    _gateoff_input.featured_media_id,
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
check_false(
    "APPLIED-NEW-OBJECT. articleが新しいobjectに置き換わる",
    _applied_result is _applied_input,
)
check("APPLIED-MEDIA-ID. featured_media_idが生成画像のmedia_id", _applied_result.featured_media_id, 999)
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
    "CONT-SAME-OBJECT（NOMUT）. articleが同一object・未改変",
    _cont_result is _cont_input,
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
    check_true(
        "LOOP-HANDLER-NO-BINDING. 例外を変数へ束縛していない（SEC-2／SEC-3の構造的保証）",
        _handler.name is None,
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

# 設計書15.3節「変更禁止範囲」に対応する対象一覧
_protected_paths = [
    "src/image_resolver.py",
    "src/outputs",
    "src/logger",
    "src/analytics",
    "src/pipeline",
    "src/ai",
    "src/scheduler",
    "src/wordpress_media",
    "src/ai_image_generation",
    "src/openai_image_generation",
    "src/generated_image_wordpress_media",
    "src/article_featured_media",
    "src/article_featured_media_orchestration",
    "src/image_generation_config",
    "src/generated_image_filename_policy",
    "src/article_image_prompt_construction",
    "src/article_featured_media_composition",
    "src/image_generation_fallback_policy",
    "src/article_featured_media_runtime",
    "scripts",
    "requirements.txt",
    ".env.example",
]

# v6.22.0（DI-10）が Architecture Design で正式に宣言した「保護対象内での意図的変更」。
# 既定は空集合（＝従来と同じ「差分ゼロ」の意味）。src/wordpress_media のみ非空。
# 設計書11.7.1節「採用する精緻化（案C：allow-list 方式）」参照。
_allowed_source_changes = {
    "src/wordpress_media": frozenset({
        "src/wordpress_media/__init__.py",
        "src/wordpress_media/wordpress_media_uploader.py",
    }),
}

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

# 既存testsは、設計書15.3節が認める2つの例外（v6.13.0／v6.20.0のGuard精緻化）に加え、
# v6.22.0（DI-10）が正式に宣言した3件（v6.9.0／v6.19.0の既存アサーション更新、
# および新規E2E自身）以外に差分があってはならない（設計書11.7.3節）
_allowed_test_changes = {
    # 設計書15.3節が認めるGuard精緻化の例外2件
    "test_e2e_v6_13_0_article_featured_media_binding_foundation.py",
    "test_e2e_v6_20_0_article_featured_media_runtime_foundation.py",
    # 本Releaseで新規追加するE2E自身（commit後はbaseline比較で「追加」として現れる）
    "test_e2e_v6_21_0_article_featured_media_runtime_wiring.py",
    # v6.22.0（DI-10）が既存アサーションを更新するファイル2件（X-1・X-2/X-3）
    "test_e2e_v6_9_0_wordpress_media_upload_foundation.py",
    "test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py",
    # v6.22.0（DI-10）の新規E2E自身
    "test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py",
}
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
    "NOIMPACT-TESTS-SCOPE. tests/の差分が許容6件（15.3節の例外2件＋v6.21 E2E＋"
    "v6.22.0が更新する既存2件＋v6.22 E2E自身）の範囲内",
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
