"""
E2E テスト: v6.20.0 Article Featured Media Runtime Foundation

Source of Truth:
    docs/design/article_featured_media_runtime_wiring.md
    （Architecture Review 2：Approved with Suggestions／Architecture Amendment 2）

本テストは実OpenAI API・実WordPress API・実HTTP通信・実課金のいずれも発生させない。
`article_featured_media_runtime` はConsumer-lessであり、main.py・image_resolver.py・
outputs・pipeline・scriptsのいずれからも参照されていないことをRUNTIME-Scenarioで
確認する。

main.pyへの実接続（配線）・callerによる元例外の無変換再送出後の上位Runtimeの扱いは
本E2Eの保証対象に含めない。これはDI-4 Runtime Wiring（v6.21.0）のProduction
Implementation／E2Eで検証する契約である（設計書10.2節 A-7、v6.19 §21.6 W-1〜W-4）。

Scenario構成:
    API-       Public API：__all__・export面・signature・from_env()委譲
    STATUS-    ArticleFeaturedMediaRuntimeStatus 3値
    RESULT-    frozen・field構成・category非field既定
    ARTICLETYPE- A-1契約：articleがArticleDataでない場合のValueError
    DISABLED-  is_available()==False時の未実行保証
    APPLIED-   生成成功→Upload成功→Binding成功
    ARGS-      orchestratorへ渡るprompt／filenameの完全一致
    SEQ-       generate→upload の呼び出し順序
    CONT-      継続対象：4 reasonのみ（allow-list）
    PROP-      伝播対象の網羅（9項目）
    IDENT-     元例外同一性
    NOMUT-     ArticleData非改変（CONTINUE／DISABLED時）
    TRY-       try範囲：prompt／filenameのValueErrorがpolicyへ非到達
    BASE-      BaseException非捕捉
    AST-       AST検証：ExceptHandler1件・bare raise
    URL-       featured_image_url不変
    NOIMPACT-  記事本文・タイトル等への非影響
    SEC-       秘密非保持
    DEP-       禁止import・許可importのみ
    IMPORT-    clean subprocessによるopenai非import検証
    SOCKET-    in-process socket遮断検証
    RUNTIME-   Runtime Zero Diff
    COMPAT-    既存Public API不変（v6.9〜v6.19）

実行方法:
    cd projects/03_game_content_ai
    venv\\Scripts\\python.exe tests/test_e2e_v6_20_0_article_featured_media_runtime_foundation.py
"""
import ast
import dataclasses
import inspect
import os
import socket
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ─── テスト用ユーティリティ（v6.14.0〜v6.19.0 precedentを踏襲） ───

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


def invoke(func):
    """funcを呼び出し、(戻り値, 例外)のタプルを返す。例外がなければ(結果, None)。"""
    try:
        return func(), None
    except BaseException as exc:
        return None, exc


# ─── AST解析ユーティリティ（v6.13.0〜v6.19.0 precedentを踏襲） ───


def get_import_roots(file_path: Path) -> set:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def get_except_handler_info(file_path: Path) -> list:
    """file_path内のExceptHandlerについて、(型名, bare raiseを含むか)の情報を返す。"""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    handlers = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            type_name = node.type.id if isinstance(node.type, ast.Name) else None
            has_bare_raise = any(
                isinstance(n, ast.Raise) and n.exc is None for n in ast.walk(node)
            )
            handlers.append({"type": type_name, "has_bare_raise": has_bare_raise})
    return handlers


def get_raise_nodes(file_path: Path) -> list:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    return [n for n in ast.walk(tree) if isinstance(n, ast.Raise)]


def file_references_name(file_path: Path, name: str) -> bool:
    return name in file_path.read_text(encoding="utf-8")


print("=" * 60)
print("v6.20.0 Article Featured Media Runtime Foundation E2E テスト")
print("=" * 60)
print()

# ─── Environment隔離：テスト開始前の状態を保存し、finallyで完全に復元する ───

_ENV_KEYS = (
    "AI_IMAGE_GENERATION_ENABLED",
    "OPENAI_API_KEY",
    "OPENAI_IMAGE_TIMEOUT_SECONDS",
    "WP_SITE_URL",
    "WP_USERNAME",
    "WP_APP_PASSWORD",
)
_SAVED_ENV = {key: os.environ.get(key) for key in _ENV_KEYS}


def _restore_env():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


try:
    import article_featured_media_runtime as _pkg
    import article_featured_media_runtime.article_featured_media_runtime as _impl_module
    from article_featured_media_runtime import (
        ArticleFeaturedMediaRuntime,
        ArticleFeaturedMediaRuntimeResult,
        ArticleFeaturedMediaRuntimeStatus,
    )
    from article_featured_media_orchestration import ArticleFeaturedMediaOrchestrator
    from article_image_prompt_construction import construct_article_image_prompt
    from generated_image_filename_policy import generate_image_filename
    from image_generation_fallback_policy import (
        ImageGenerationFailureCategory,
        decide_image_generation_fallback,
    )
    from openai_image_generation import (
        OpenAIImageGenerationError,
        OpenAIImageGenerationErrorReason,
    )
    from wordpress_media import WordPressMediaUploadError, MediaUploadResult
    from ai_image_generation import GeneratedImage
    from outputs import ArticleData
    from collector import NewsItem
    from publishing_config import PublishStatus

    PACKAGE_DIR = PROJECT_ROOT / "src" / "article_featured_media_runtime"
    MODULE_FILE = PACKAGE_DIR / "article_featured_media_runtime.py"
    INIT_FILE = PACKAGE_DIR / "__init__.py"

    # ─── テストfixture builder（v6.14.0 precedent踏襲） ───

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

    def make_generated_image(mime_type: str = "image/png", data: bytes = b"PNGDATA") -> GeneratedImage:
        return GeneratedImage(image_bytes=data, mime_type=mime_type)

    def make_media_result(media_id=123, source_url="https://example.com/photo.png", mime_type="image/png"):
        return MediaUploadResult(media_id=media_id, source_url=source_url, mime_type=mime_type)

    # ─── Test Double（Fake／sentinel、test file内限定。production packageへは配置しない） ───

    class FakeOrchestrator:
        """root.orchestrator の Fake。実際のArticleFeaturedMediaOrchestratorを
        経由せず、apply()の呼び出しのみを記録し、指定されたresult／errorを返す。"""

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
        """ArticleFeaturedMediaCompositionRoot の Fake。Duck Typingのため
        isinstance検証は行われない（設計書10.1節）。"""

        def __init__(self, *, orchestrator, image_mime_type="image/png", available=True):
            self.orchestrator = orchestrator
            self.image_mime_type = image_mime_type
            self._available = available

        def is_available(self):
            return self._available

    class _RealChainGenerator:
        """実ArticleFeaturedMediaOrchestrator経由でgenerate→uploadの順序を
        検証するためのFake image_generator。"""

        def __init__(self, recorder, image=None, error=None):
            self._recorder = recorder
            self._image = image if image is not None else make_generated_image()
            self._error = error

        def generate(self, prompt):
            self._recorder.append(("generate", prompt))
            if self._error is not None:
                raise self._error
            return self._image

    class _RealChainUploader:
        def __init__(self, recorder, result=None):
            self._recorder = recorder
            self._result = result if result is not None else make_media_result()

        def upload(self, image, filename):
            self._recorder.append(("upload", filename))
            return self._result

    # =====================================================================
    # API: Public API
    # =====================================================================

    print("[API] Public API")

    check(
        "API-ALL-EXACT. __all__が3 symbolのみである",
        sorted(_pkg.__all__),
        sorted(
            [
                "ArticleFeaturedMediaRuntimeStatus",
                "ArticleFeaturedMediaRuntimeResult",
                "ArticleFeaturedMediaRuntime",
            ]
        ),
    )
    for _name in _pkg.__all__:
        check_true(
            f"API-EXPORT-EXISTS[{_name}]. {_name}がpackage直下からimportできる",
            hasattr(_pkg, _name),
        )

    _init_sig = inspect.signature(ArticleFeaturedMediaRuntime.__init__)
    _init_params = list(_init_sig.parameters.values())
    check("API-INIT-PARAM-COUNT. __init__の引数がself+rootの2件", len(_init_params), 2)
    check("API-INIT-PARAM-NAME. 第2引数名がrootである", _init_params[1].name, "root")

    check_true(
        "API-FROM-ENV-IS-CLASSMETHOD. from_env()がclassmethodである",
        inspect.ismethod(ArticleFeaturedMediaRuntime.from_env),
    )

    _apply_sig = inspect.signature(ArticleFeaturedMediaRuntime.apply)
    _apply_params = list(_apply_sig.parameters.values())
    check("API-APPLY-PARAM-COUNT. apply()の引数がself+articleの2件", len(_apply_params), 2)
    check("API-APPLY-PARAM-NAME. 第2引数名がarticleである", _apply_params[1].name, "article")

    check_true(
        "API-IS-AVAILABLE-CALLABLE. is_available()がcallableである",
        callable(ArticleFeaturedMediaRuntime.is_available),
    )

    _env_backup = {k: os.environ.pop(k, None) for k in _ENV_KEYS}
    try:
        _facade_from_env = ArticleFeaturedMediaRuntime.from_env()
        check_false(
            "API-FROM-ENV-GATE-OFF. Gate OFF（env未設定）時、is_available()==False",
            _facade_from_env.is_available(),
        )
    finally:
        _restore_env()

    # Gate ON かつ credential 不足時、既存Composition Rootの ValueError が
    # 無変換伝播すること（Fail Fast。from_env() が自前で再実装・変更していないことの確認）
    _env_backup2 = {k: os.environ.pop(k, None) for k in _ENV_KEYS}
    try:
        os.environ["AI_IMAGE_GENERATION_ENABLED"] = "true"
        _, _from_env_raised = invoke(lambda: ArticleFeaturedMediaRuntime.from_env())
    finally:
        _restore_env()
    check_true(
        "API-FROM-ENV-GATE-ON-FAILFAST. Gate ON・OPENAI_API_KEY未設定時、"
        "ValueErrorが無変換伝播する（既存Composition Root契約への委譲確認）",
        isinstance(_from_env_raised, ValueError),
    )
    print()

    # =====================================================================
    # STATUS: ArticleFeaturedMediaRuntimeStatus 3値
    # =====================================================================

    print("[STATUS] ArticleFeaturedMediaRuntimeStatus 3値")

    check("STATUS-COUNT. 3値である", len(list(ArticleFeaturedMediaRuntimeStatus)), 3)
    check("STATUS-DISABLED-VALUE. DISABLEDの値", ArticleFeaturedMediaRuntimeStatus.DISABLED.value, "DISABLED")
    check("STATUS-APPLIED-VALUE. APPLIEDの値", ArticleFeaturedMediaRuntimeStatus.APPLIED.value, "APPLIED")
    check(
        "STATUS-CONTINUED-VALUE. CONTINUED_WITHOUT_FEATURED_MEDIAの値",
        ArticleFeaturedMediaRuntimeStatus.CONTINUED_WITHOUT_FEATURED_MEDIA.value,
        "CONTINUED_WITHOUT_FEATURED_MEDIA",
    )
    print()

    # =====================================================================
    # RESULT: frozen・field構成
    # =====================================================================

    print("[RESULT] frozen・field構成")

    check_true(
        "RESULT-FROZEN. frozen dataclassである",
        ArticleFeaturedMediaRuntimeResult.__dataclass_params__.frozen,
    )
    _field_names = tuple(f.name for f in dataclasses.fields(ArticleFeaturedMediaRuntimeResult))
    check(
        "RESULT-FIELDS. fieldがarticle/status/categoryの3件・この順序",
        _field_names,
        ("article", "status", "category"),
    )
    _category_field = dataclasses.fields(ArticleFeaturedMediaRuntimeResult)[2]
    check("RESULT-CATEGORY-DEFAULT-NONE. categoryの既定値がNone", _category_field.default, None)

    _sample_result = ArticleFeaturedMediaRuntimeResult(
        article=make_article(), status=ArticleFeaturedMediaRuntimeStatus.DISABLED
    )
    _, _frozen_exc = invoke(
        lambda: setattr(_sample_result, "status", ArticleFeaturedMediaRuntimeStatus.APPLIED)
    )
    check_true(
        "RESULT-IMMUTABLE. 属性再代入がFrozenInstanceErrorを送出する",
        isinstance(_frozen_exc, dataclasses.FrozenInstanceError),
    )
    print()

    # =====================================================================
    # ARTICLETYPE: A-1契約：articleがArticleDataでない場合のValueError
    # =====================================================================

    print("[ARTICLETYPE] A-1契約：articleがArticleDataでない場合のValueError")

    _articletype_policy_calls = []
    _orig_decide_fn_for_articletype = _impl_module.decide_image_generation_fallback

    def _spy_decide_for_articletype(error):
        _articletype_policy_calls.append(error)
        return _orig_decide_fn_for_articletype(error)

    _impl_module.decide_image_generation_fallback = _spy_decide_for_articletype
    try:
        _articletype_orch = FakeOrchestrator()
        _articletype_root = FakeCompositionRoot(orchestrator=_articletype_orch, available=True)
        _articletype_runtime = ArticleFeaturedMediaRuntime(_articletype_root)

        for _bad_label, _bad_article in (
            ("STRING", "not an ArticleData"),
            ("NONE", None),
            ("DICT", {"seo_title": "x", "excerpt": "y"}),
        ):
            _articletype_result, _articletype_raised = invoke(
                lambda a=_bad_article: _articletype_runtime.apply(a)
            )
            check_true(
                f"ARTICLETYPE-VALUEERROR[{_bad_label}]. ArticleDataでない入力でValueErrorが送出される",
                isinstance(_articletype_raised, ValueError),
            )
            check(
                f"ARTICLETYPE-MESSAGE[{_bad_label}]. messageが設計どおり固定文言である（A-1）",
                str(_articletype_raised),
                "article must be an ArticleData",
            )
    finally:
        _impl_module.decide_image_generation_fallback = _orig_decide_fn_for_articletype

    check(
        "ARTICLETYPE-ORCH-NOT-CALLED. orchestrator.apply()が一度も呼ばれない"
        "（is_available()==Trueでも、型検証がGate評価より前に働く）",
        len(_articletype_orch.calls),
        0,
    )
    check(
        "ARTICLETYPE-POLICY-NOT-CALLED. decide_image_generation_fallback()が一度も呼ばれない",
        len(_articletype_policy_calls),
        0,
    )
    print()

    # =====================================================================
    # DISABLED: is_available()==False時の未実行保証
    # =====================================================================

    print("[DISABLED] 設定無効時の既存挙動")

    _prompt_spy_calls = []
    _filename_spy_calls = []

    def _spy_prompt(*a, **kw):
        _prompt_spy_calls.append((a, kw))
        return "SHOULD_NOT_BE_CALLED"

    def _spy_filename(*a, **kw):
        _filename_spy_calls.append((a, kw))
        return "SHOULD_NOT_BE_CALLED"

    _orig_prompt_fn = _impl_module.construct_article_image_prompt
    _orig_filename_fn = _impl_module.generate_image_filename
    _impl_module.construct_article_image_prompt = _spy_prompt
    _impl_module.generate_image_filename = _spy_filename
    try:
        _disabled_orch = FakeOrchestrator()
        _disabled_root = FakeCompositionRoot(orchestrator=_disabled_orch, available=False)
        _disabled_article = make_article()
        _disabled_result = ArticleFeaturedMediaRuntime(_disabled_root).apply(_disabled_article)
    finally:
        _impl_module.construct_article_image_prompt = _orig_prompt_fn
        _impl_module.generate_image_filename = _orig_filename_fn

    check_true(
        "DISABLED-STATUS. status==DISABLED",
        _disabled_result.status is ArticleFeaturedMediaRuntimeStatus.DISABLED,
    )
    check_true(
        "DISABLED-ARTICLE-IDENTITY. articleが同一object",
        _disabled_result.article is _disabled_article,
    )
    check("DISABLED-CATEGORY-NONE. categoryがNone", _disabled_result.category, None)
    check("DISABLED-NO-PROMPT-CALL. prompt構築が一度も呼ばれない", len(_prompt_spy_calls), 0)
    check("DISABLED-NO-FILENAME-CALL. filename構築が一度も呼ばれない", len(_filename_spy_calls), 0)
    check("DISABLED-NO-ORCH-CALL. orchestrator.apply()が一度も呼ばれない", len(_disabled_orch.calls), 0)
    print()

    # =====================================================================
    # APPLIED / ARGS / SEQ: 画像生成成功→Upload成功→Binding成功
    # =====================================================================

    print("[APPLIED/ARGS/SEQ] 画像生成成功／Upload成功／Binding成功・呼び出し順序")

    _chain_recorder = []
    _real_orchestrator = ArticleFeaturedMediaOrchestrator(
        image_generator=_RealChainGenerator(_chain_recorder),
        media_uploader=_RealChainUploader(_chain_recorder, result=make_media_result(media_id=555)),
    )
    _applied_root = FakeCompositionRoot(
        orchestrator=_real_orchestrator, image_mime_type="image/png", available=True
    )
    _applied_article = make_article(seo_title="テストタイトル", excerpt="テスト概要")
    _applied_result = ArticleFeaturedMediaRuntime(_applied_root).apply(_applied_article)

    _expected_prompt = construct_article_image_prompt(
        _applied_article.seo_title, _applied_article.excerpt
    )
    _expected_filename = generate_image_filename(_applied_article.seo_title, "image/png")

    check_true(
        "APPLIED-STATUS. status==APPLIED",
        _applied_result.status is ArticleFeaturedMediaRuntimeStatus.APPLIED,
    )
    check(
        "APPLIED-MEDIA-ID. featured_media_idが生成画像のmedia_id",
        _applied_result.article.featured_media_id,
        555,
    )
    check("APPLIED-CATEGORY-NONE. categoryがNone", _applied_result.category, None)
    check_false(
        "APPLIED-NEW-OBJECT. Orchestrator経由でarticleは新しいobjectになる（元objectと非同一）",
        _applied_result.article is _applied_article,
    )
    check(
        "SEQ-ORDER. generate→uploadの順で呼ばれる",
        [c[0] for c in _chain_recorder],
        ["generate", "upload"],
    )
    check("ARGS-PROMPT. orchestratorへ渡るpromptがconstruct_article_image_prompt()の出力と一致する", _chain_recorder[0][1], _expected_prompt)
    check("ARGS-FILENAME. orchestratorへ渡るfilenameがgenerate_image_filename()の出力と一致する", _chain_recorder[1][1], _expected_filename)
    print()

    # =====================================================================
    # CONT: 継続対象：4 reasonのみ（allow-list）
    # =====================================================================

    print("[CONT] 継続対象：4 reasonのみ（allow-list）")

    for _reason_name in ("TIMEOUT", "CONNECTION", "RATE_LIMIT", "SERVER_ERROR"):
        _reason = getattr(OpenAIImageGenerationErrorReason, _reason_name)
        _cont_error = OpenAIImageGenerationError(f"probe {_reason_name}", _reason)
        _cont_orch = FakeOrchestrator(error=_cont_error)
        _cont_root = FakeCompositionRoot(orchestrator=_cont_orch, available=True)
        _cont_article = make_article()
        _cont_result = ArticleFeaturedMediaRuntime(_cont_root).apply(_cont_article)

        check_true(
            f"CONT-STATUS[{_reason_name}]. status==CONTINUED_WITHOUT_FEATURED_MEDIA",
            _cont_result.status is ArticleFeaturedMediaRuntimeStatus.CONTINUED_WITHOUT_FEATURED_MEDIA,
        )
        check(
            f"CONT-CATEGORY[{_reason_name}]. categoryがIMAGE_GENERATION_FAILED",
            _cont_result.category,
            ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED,
        )
        check_true(
            f"CONT-ARTICLE-IDENTITY[{_reason_name}]. articleが同一object（未改変）",
            _cont_result.article is _cont_article,
        )
    print()

    # =====================================================================
    # PROP / IDENT: 伝播対象の網羅・元例外同一性
    # =====================================================================

    print("[PROP/IDENT] 伝播対象の網羅・元例外同一性")

    _prop_cases = []
    for _reason_name in ("REQUEST_REJECTED", "AUTHENTICATION", "PERMISSION_DENIED", "INVALID_RESPONSE", "UNKNOWN"):
        _reason = getattr(OpenAIImageGenerationErrorReason, _reason_name)
        _prop_cases.append((_reason_name, OpenAIImageGenerationError(f"probe {_reason_name}", _reason)))

    _unknown_reason_error = OpenAIImageGenerationError("probe unknown-reason", "not_a_real_reason_value")
    _prop_cases.append(("UNKNOWN_REASON_VALUE", _unknown_reason_error))

    _missing_reason_error = OpenAIImageGenerationError(
        "probe missing-reason", OpenAIImageGenerationErrorReason.TIMEOUT
    )
    del _missing_reason_error.reason
    _prop_cases.append(("MISSING_REASON_ATTR", _missing_reason_error))

    _prop_cases.append(("WORDPRESS_MEDIA_UPLOAD_ERROR", WordPressMediaUploadError("probe wp upload failure")))
    _prop_cases.append(("UNKNOWN_EXCEPTION_TYPE", RuntimeError("probe unknown exception type")))

    for _label, _prop_error in _prop_cases:
        _prop_orch = FakeOrchestrator(error=_prop_error)
        _prop_root = FakeCompositionRoot(orchestrator=_prop_orch, available=True)
        _prop_article = make_article()
        _prop_result, _prop_raised = invoke(
            lambda a=_prop_article, r=_prop_root: ArticleFeaturedMediaRuntime(r).apply(a)
        )

        check_true(f"PROP-RAISED[{_label}]. 例外が送出される", _prop_raised is not None)
        check_true(
            f"IDENT-SAME-OBJECT[{_label}]. 送出された例外が注入した例外オブジェクトと同一である",
            _prop_raised is _prop_error,
        )
        check_true(
            f"IDENT-NO-CAUSE[{_label}]. __cause__が加工されていない（Noneのまま）",
            _prop_raised.__cause__ is None,
        )
        check(f"IDENT-MESSAGE[{_label}]. messageが不変", str(_prop_raised), str(_prop_error))
    print()

    # =====================================================================
    # BASE: BaseException非捕捉
    # =====================================================================

    print("[BASE] BaseException非捕捉")

    class _CustomBaseException(BaseException):
        pass

    for _base_label, _base_error in (
        ("CUSTOM_BASE_EXCEPTION", _CustomBaseException("base probe")),
        ("KEYBOARD_INTERRUPT", KeyboardInterrupt()),
        ("SYSTEM_EXIT", SystemExit(1)),
    ):
        _base_orch = FakeOrchestrator(error=_base_error)
        _base_root = FakeCompositionRoot(orchestrator=_base_orch, available=True)
        _base_article = make_article()
        _base_result, _base_raised = invoke(
            lambda a=_base_article, r=_base_root: ArticleFeaturedMediaRuntime(r).apply(a)
        )
        check_true(f"BASE-PROPAGATED[{_base_label}]. BaseExceptionが素通しされる", _base_raised is _base_error)
        check_false(
            f"BASE-NOT-CAUGHT-AS-EXCEPTION[{_base_label}]. Exceptionとして捕捉されていない（isinstance(Exception)==False）",
            isinstance(_base_raised, Exception),
        )
    print()

    # =====================================================================
    # TRY: try範囲：prompt／filenameのValueErrorがpolicyへ非到達
    # =====================================================================

    print("[TRY] try範囲：prompt／filenameのValueErrorがpolicyへ非到達")

    _policy_calls = []
    _orig_decide_fn = _impl_module.decide_image_generation_fallback

    def _spy_decide(error):
        _policy_calls.append(error)
        return _orig_decide_fn(error)

    _impl_module.decide_image_generation_fallback = _spy_decide
    try:
        _try_orch = FakeOrchestrator()
        _try_root = FakeCompositionRoot(orchestrator=_try_orch, available=True)
        _try_article = make_article(seo_title="   ")
        _try_result, _try_raised = invoke(
            lambda: ArticleFeaturedMediaRuntime(_try_root).apply(_try_article)
        )
    finally:
        _impl_module.decide_image_generation_fallback = _orig_decide_fn

    check_true("TRY-VALUEERROR-RAISED. prompt構築のValueErrorが送出される", isinstance(_try_raised, ValueError))
    check("TRY-POLICY-NOT-CALLED. decide_image_generation_fallback()が呼ばれない", len(_policy_calls), 0)
    check("TRY-ORCH-NOT-CALLED. orchestrator.apply()が呼ばれない", len(_try_orch.calls), 0)
    print()

    # =====================================================================
    # AST: AST検証：ExceptHandler1件・bare raise
    # =====================================================================

    print("[AST] AST検証：ExceptHandler1件・bare raise")

    _handlers = get_except_handler_info(MODULE_FILE)
    check("AST-EXCEPT-COUNT. ExceptHandlerが1件のみ", len(_handlers), 1)
    if _handlers:
        check("AST-EXCEPT-TYPE. 型がExceptionである", _handlers[0]["type"], "Exception")
        check_true("AST-BARE-RAISE. PROPAGATE分岐がbare raiseである", _handlers[0]["has_bare_raise"])

    _raise_nodes = get_raise_nodes(MODULE_FILE)
    _bare_raise_nodes = [n for n in _raise_nodes if n.exc is None]
    check("AST-BARE-RAISE-COUNT. bare raiseが1件のみ", len(_bare_raise_nodes), 1)
    print()

    # =====================================================================
    # URL / NOIMPACT / NOMUT: 既存fieldへの非影響・非改変
    # =====================================================================

    print("[URL/NOIMPACT/NOMUT] 既存fieldへの非影響・非改変")

    _impact_article = make_article(featured_image_url="https://example.com/original.png")
    _snapshot = dict(
        article_body=_impact_article.article_body,
        seo_title=_impact_article.seo_title,
        slug=_impact_article.slug,
        excerpt=_impact_article.excerpt,
        publish_status=_impact_article.publish_status,
        item=_impact_article.item,
        featured_image_url=_impact_article.featured_image_url,
    )

    _disabled_root2 = FakeCompositionRoot(orchestrator=FakeOrchestrator(), available=False)
    _result_disabled2 = ArticleFeaturedMediaRuntime(_disabled_root2).apply(_impact_article)

    _cont_error2 = OpenAIImageGenerationError("probe", OpenAIImageGenerationErrorReason.TIMEOUT)
    _cont_root2 = FakeCompositionRoot(orchestrator=FakeOrchestrator(error=_cont_error2), available=True)
    _result_cont2 = ArticleFeaturedMediaRuntime(_cont_root2).apply(_impact_article)

    _chain_recorder2 = []
    _applied_orch2 = ArticleFeaturedMediaOrchestrator(
        image_generator=_RealChainGenerator(_chain_recorder2),
        media_uploader=_RealChainUploader(_chain_recorder2, result=make_media_result(media_id=999)),
    )
    _applied_root2 = FakeCompositionRoot(orchestrator=_applied_orch2, available=True)
    _result_applied2 = ArticleFeaturedMediaRuntime(_applied_root2).apply(_impact_article)

    for _label, _res in (
        ("DISABLED", _result_disabled2),
        ("CONTINUE", _result_cont2),
        ("APPLIED", _result_applied2),
    ):
        check(f"URL-UNCHANGED[{_label}]. featured_image_urlが不変", _res.article.featured_image_url, _snapshot["featured_image_url"])
        check(f"NOIMPACT-BODY[{_label}]. article_bodyが不変", _res.article.article_body, _snapshot["article_body"])
        check(f"NOIMPACT-TITLE[{_label}]. seo_titleが不変", _res.article.seo_title, _snapshot["seo_title"])
        check(f"NOIMPACT-SLUG[{_label}]. slugが不変", _res.article.slug, _snapshot["slug"])
        check(f"NOIMPACT-EXCERPT[{_label}]. excerptが不変", _res.article.excerpt, _snapshot["excerpt"])
        check(f"NOIMPACT-PUBLISHSTATUS[{_label}]. publish_statusが不変", _res.article.publish_status, _snapshot["publish_status"])
        check_true(f"NOIMPACT-ITEM[{_label}]. itemが同一object", _res.article.item is _snapshot["item"])

    check_true("NOMUT-DISABLED-IDENTITY. DISABLED時articleが同一object", _result_disabled2.article is _impact_article)
    check_true("NOMUT-CONTINUE-IDENTITY. CONTINUE時articleが同一object", _result_cont2.article is _impact_article)
    print()

    # =====================================================================
    # SEC: 秘密非保持
    # =====================================================================

    print("[SEC] 秘密非保持")

    _secret_marker = "SECRET_MARKER_39fae2"
    _sec_error = OpenAIImageGenerationError(_secret_marker, OpenAIImageGenerationErrorReason.RATE_LIMIT)
    _sec_orch = FakeOrchestrator(error=_sec_error)
    _sec_root = FakeCompositionRoot(orchestrator=_sec_orch, available=True)
    _sec_article = make_article()
    _sec_result = ArticleFeaturedMediaRuntime(_sec_root).apply(_sec_article)

    check_false("SEC-NO-EXC-MESSAGE-IN-REPR. repr(result)に例外messageが現れない", _secret_marker in repr(_sec_result))
    check_false("SEC-NO-EXC-MESSAGE-IN-STR. str(result)に例外messageが現れない", _secret_marker in str(_sec_result))
    check_false(
        "SEC-NO-EXC-MESSAGE-IN-ASDICT. dataclasses.asdict(result)に例外messageが現れない",
        _secret_marker in repr(dataclasses.asdict(_sec_result)),
    )

    # APPLIED経路：生成画像bytesがResultへ漏れないことを確認する
    # （article.excerpt／seo_title等の既存ArticleData fieldはResultの正当なfieldであり
    #   秘密ではないため、ここでは検証対象にしない。SEC-1が禁じるのはraw exception・
    #   prompt・credential・provider応答本文・生成画像bytesである）
    _image_bytes_marker = "IMAGEBYTESMARKER77z"
    _sec_recorder2 = []
    _sec_real_orch = ArticleFeaturedMediaOrchestrator(
        image_generator=_RealChainGenerator(
            _sec_recorder2, image=make_generated_image(data=_image_bytes_marker.encode("ascii"))
        ),
        media_uploader=_RealChainUploader(_sec_recorder2, result=make_media_result(media_id=42)),
    )
    _sec_root2 = FakeCompositionRoot(orchestrator=_sec_real_orch, available=True)
    _sec_result2 = ArticleFeaturedMediaRuntime(_sec_root2).apply(make_article())

    check_false(
        "SEC-NO-IMAGE-BYTES-IN-REPR. repr(result)に生成画像bytesが現れない（APPLIED時）",
        _image_bytes_marker in repr(_sec_result2),
    )
    check_false(
        "SEC-NO-IMAGE-BYTES-IN-ASDICT. asdict(result)に生成画像bytesが現れない（APPLIED時）",
        _image_bytes_marker in repr(dataclasses.asdict(_sec_result2)),
    )
    print()

    # =====================================================================
    # DEP: 依存Guard
    # =====================================================================

    print("[DEP] 依存Guard")

    _ALLOWED_IMPORT_ROOTS = {
        "__future__",
        "dataclasses",
        "enum",
        "article_featured_media_composition",
        "article_image_prompt_construction",
        "generated_image_filename_policy",
        "image_generation_fallback_policy",
        "outputs",
    }
    _actual_roots = get_import_roots(MODULE_FILE)
    check_true(
        "DEP-FORBIDDEN-IMPORTS. importするrootが許可集合の部分集合である"
        "（main／image_resolver／pipeline／ai／scheduler／retry_*等を一切importしない）",
        _actual_roots <= _ALLOWED_IMPORT_ROOTS,
    )
    for _forbidden in ("os", "logging", "requests", "socket", "main", "image_resolver", "pipeline", "ai", "scheduler"):
        check_false(
            f"DEP-NO-{_forbidden.upper()}-IMPORT. {_forbidden}をmodule-levelでimportしない",
            _forbidden in _actual_roots,
        )
    check_false(
        "DEP-NO-RETRY-PREFIX-IMPORT. retry_*で始まるrootをimportしない",
        any(r.startswith("retry_") for r in _actual_roots),
    )

    _init_actual_roots = get_import_roots(INIT_FILE)
    _ALLOWED_INIT_IMPORT_ROOTS = {"article_featured_media_runtime"}
    check_true(
        "DEP-INIT-FORBIDDEN-IMPORTS. __init__.pyがimportするrootが許可集合（自パッケージへの相対importのみ）の部分集合である",
        _init_actual_roots <= _ALLOWED_INIT_IMPORT_ROOTS,
    )
    for _forbidden in ("os", "logging", "requests", "socket", "openai"):
        check_false(
            f"DEP-INIT-NO-{_forbidden.upper()}-IMPORT. __init__.pyが{_forbidden}をimportしない",
            _forbidden in _init_actual_roots,
        )
    print()

    # =====================================================================
    # IMPORT: 外部接続ゼロ
    # =====================================================================

    print("[IMPORT] 外部接続ゼロ")

    _VENV_PYTHON = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
    check_true("IMPORT-VENV-PYTHON-EXISTS. Repository venv Pythonが存在する", _VENV_PYTHON.is_file())

    _subprocess_script = (
        "import sys; "
        "sys.path.insert(0, 'src'); "
        "from article_featured_media_runtime import ArticleFeaturedMediaRuntime; "
        "print('OPENAI_IMPORTED=' + str('openai' in sys.modules))"
    )
    _completed = subprocess.run(
        [str(_VENV_PYTHON), "-c", _subprocess_script],
        cwd=str(PROJECT_ROOT),
        env=dict(os.environ),
        capture_output=True,
        text=True,
        timeout=30,
    )
    check("IMPORT-1-SUBPROCESS-EXIT-CODE. subprocessのexit codeが0", _completed.returncode, 0)
    check_contains(
        "IMPORT-1-OPENAI-NOT-IMPORTED. import後もopenaiがimportされていない"
        "（clean subprocessによる決定的検証、skipなし）",
        _completed.stdout,
        "OPENAI_IMPORTED=False",
    )
    check("IMPORT-1-STDERR-EMPTY. stderrが空（tracebackが出ていない）", _completed.stderr.strip(), "")
    print()

    # =====================================================================
    # SOCKET: in-process network遮断検証
    # =====================================================================

    print("[SOCKET] in-process network遮断")

    _orig_getaddrinfo = socket.getaddrinfo
    _orig_connect = socket.socket.connect

    def _blocked_getaddrinfo(*args, **kwargs):
        raise AssertionError("socket.getaddrinfo was called (unexpected DNS resolution)")

    def _blocked_connect(self, *args, **kwargs):
        raise AssertionError("socket.socket.connect was called (unexpected network connection)")

    socket.getaddrinfo = _blocked_getaddrinfo
    socket.socket.connect = _blocked_connect
    try:
        _socket_error = OpenAIImageGenerationError("x", OpenAIImageGenerationErrorReason.TIMEOUT)
        _socket_orch = FakeOrchestrator(error=_socket_error)
        _socket_root = FakeCompositionRoot(orchestrator=_socket_orch, available=True)
        _, _network_exc = invoke(lambda: ArticleFeaturedMediaRuntime(_socket_root).apply(make_article()))

        _socket_recorder = []
        _socket_real_orch = ArticleFeaturedMediaOrchestrator(
            image_generator=_RealChainGenerator(_socket_recorder),
            media_uploader=_RealChainUploader(_socket_recorder),
        )
        _socket_root2 = FakeCompositionRoot(orchestrator=_socket_real_orch, available=True)
        _, _network_exc2 = invoke(lambda: ArticleFeaturedMediaRuntime(_socket_root2).apply(make_article()))
    finally:
        socket.getaddrinfo = _orig_getaddrinfo
        socket.socket.connect = _orig_connect

    check_true(
        "SOCKET-NO-NETWORK. apply()はsocket.getaddrinfo／socket.socket.connectのいずれも呼び出さない"
        "（test本体プロセス内でのin-process遮断検証。IMPORT-1のsubprocessとは独立）",
        _network_exc is None and _network_exc2 is None,
    )
    check_true(
        "SOCKET-RESTORED. socket関数がpatch前の状態へ復元されている",
        socket.getaddrinfo is _orig_getaddrinfo and socket.socket.connect is _orig_connect,
    )
    print()

    # =====================================================================
    # RUNTIME: Runtime Zero Diff
    # =====================================================================

    print("[RUNTIME] Runtime Zero Diff")

    # RUNTIME-1a（main.py）: v6.20.0時点では「参照しないこと」がRuntime Zero Diffの
    # 証跡だった。v6.21.0（Article Featured Media Runtime Wiring）はmain.pyのみを
    # 対象にこのZero Diffを設計上解除する（設計書15.4節）ため、本チェックは
    # v6.21.0時点で意図的にFAILする状態になる。単純に削除・無効化するのではなく、
    # 恒久的に保持すべき契約（main.pyが本packageを参照する場合は、承認済み
    # static importのみに限られ、コメント・文字列・動的import等の非import経路を
    # 経由しないこと）へ精緻化する（v6.13.0 RUNTIME-1の精緻化＝設計書5.5節と同型の
    # 対応）。main.py以外の対象（RUNTIME-1b〜1e）はいずれの時点でも本packageを
    # 一切参照してはならないため、従来どおり「参照しないこと」を維持する。
    _main_path = PROJECT_ROOT / "main.py"
    _main_source = _main_path.read_text(encoding="utf-8")
    _main_tree = ast.parse(_main_source, filename=str(_main_path))

    # 本packageをimportしているstatic import文が占める行番号の集合
    _approved_import_linenos = set()
    for _node in ast.walk(_main_tree):
        _imports_pkg = False
        if isinstance(_node, ast.Import):
            _imports_pkg = any(
                _a.name.split(".")[0] == "article_featured_media_runtime" for _a in _node.names
            )
        elif isinstance(_node, ast.ImportFrom) and _node.module and not _node.level:
            _imports_pkg = _node.module.split(".")[0] == "article_featured_media_runtime"
        if _imports_pkg:
            _approved_import_linenos.update(
                range(_node.lineno, (_node.end_lineno or _node.lineno) + 1)
            )

    # ソーステキスト上でpackage名が出現する行番号の集合
    _reference_linenos = {
        _i
        for _i, _line in enumerate(_main_source.splitlines(), 1)
        if "article_featured_media_runtime" in _line
    }

    # 「のみ」の実検証：import文の行以外にpackage名が現れてはならない
    # （コメント・docstring・文字列リテラル・動的import経由の参照をすべて拒否する）
    _non_import_references = sorted(_reference_linenos - _approved_import_linenos)
    check(
        "RUNTIME-1a. main.pyにおけるarticle_featured_media_runtimeの出現が、"
        "承認済みstatic import文の行のみに限られる（非import参照の行番号リストが空）",
        _non_import_references,
        [],
    )
    check_true(
        "RUNTIME-1a. main.pyが本packageを参照する場合、AST上のimport rootとして"
        "解決される（v6.21.0 Wiring後も維持される恒久契約）",
        (not _reference_linenos) or ("article_featured_media_runtime" in get_import_roots(_main_path)),
    )

    _runtime_targets = [
        ("RUNTIME-1b", "src/image_resolver.py", PROJECT_ROOT / "src" / "image_resolver.py"),
    ]
    for _outputs_file in sorted((PROJECT_ROOT / "src" / "outputs").glob("*.py")):
        _runtime_targets.append(
            (f"RUNTIME-1c[{_outputs_file.name}]", f"src/outputs/{_outputs_file.name}", _outputs_file)
        )
    for _pipeline_file in sorted((PROJECT_ROOT / "src" / "pipeline").glob("*.py")):
        _runtime_targets.append(
            (f"RUNTIME-1d[{_pipeline_file.name}]", f"src/pipeline/{_pipeline_file.name}", _pipeline_file)
        )
    for _script_file in sorted((PROJECT_ROOT / "scripts").glob("*.py")):
        _runtime_targets.append(
            (f"RUNTIME-1e[{_script_file.name}]", f"scripts/{_script_file.name}", _script_file)
        )

    for _case_id, _label, _path in _runtime_targets:
        check_false(
            f"{_case_id}. {_label}がarticle_featured_media_runtimeを参照していない",
            file_references_name(_path, "article_featured_media_runtime"),
        )
    print()

    # =====================================================================
    # COMPAT: 既存Public API不変（v6.9〜v6.19）
    # =====================================================================

    print("[COMPAT] 既存Public API不変（v6.9〜v6.19）")

    import ai_image_generation as _v610_pkg
    import wordpress_media as _v609_pkg
    import openai_image_generation as _v611_pkg
    import generated_image_wordpress_media as _v612_pkg
    import article_featured_media as _v613_pkg
    import article_featured_media_orchestration as _v614_pkg
    import image_generation_config as _v615_pkg
    import generated_image_filename_policy as _v616_pkg
    import article_image_prompt_construction as _v617_pkg
    import article_featured_media_composition as _v618_pkg
    import image_generation_fallback_policy as _v619_pkg

    check(
        "COMPAT-V609. wordpress_media.__all__が不変",
        sorted(_v609_pkg.__all__),
        sorted(["MediaUploadResult", "WordPressMediaUploadError", "WordPressMediaUploader"]),
    )
    check(
        "COMPAT-V610. ai_image_generation.__all__が不変",
        sorted(_v610_pkg.__all__),
        sorted(["GeneratedImage", "AIImageGenerator"]),
    )
    check(
        "COMPAT-V611. openai_image_generation.__all__が不変",
        sorted(_v611_pkg.__all__),
        sorted(["OpenAIImageGenerator", "OpenAIImageGenerationError", "OpenAIImageGenerationErrorReason"]),
    )
    check(
        "COMPAT-V612. generated_image_wordpress_media.__all__が不変",
        sorted(_v612_pkg.__all__),
        sorted(["GeneratedImageWordPressMediaUploader"]),
    )
    check(
        "COMPAT-V613. article_featured_media.__all__が不変",
        sorted(_v613_pkg.__all__),
        sorted(["bind_featured_media"]),
    )
    check(
        "COMPAT-V614. article_featured_media_orchestration.__all__が不変",
        sorted(_v614_pkg.__all__),
        sorted(["ArticleFeaturedMediaOrchestrator", "GeneratedImageUploadCapability"]),
    )
    check(
        "COMPAT-V615. image_generation_config.__all__が不変",
        sorted(_v615_pkg.__all__),
        sorted(["ImageGenerationConfig"]),
    )
    check(
        "COMPAT-V616. generated_image_filename_policy.__all__が不変",
        sorted(_v616_pkg.__all__),
        sorted(["generate_image_filename"]),
    )
    check(
        "COMPAT-V617. article_image_prompt_construction.__all__が不変",
        sorted(_v617_pkg.__all__),
        sorted(["construct_article_image_prompt"]),
    )
    check(
        "COMPAT-V618. article_featured_media_composition.__all__が不変",
        sorted(_v618_pkg.__all__),
        sorted(["ArticleFeaturedMediaCompositionRoot"]),
    )
    check(
        "COMPAT-V619. image_generation_fallback_policy.__all__が不変",
        sorted(_v619_pkg.__all__),
        sorted(
            [
                "ImageGenerationFailureCategory",
                "ImageGenerationFallbackAction",
                "ImageGenerationFallbackDecision",
                "decide_image_generation_fallback",
            ]
        ),
    )
    print()

finally:
    _restore_env()

# ─── 結果サマリー ───
print("=" * 60)
total = len(results_log)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = total - passed
print("Release：v6.20.0")
print("正式名称：Article Featured Media Runtime Foundation")
print(f"Assertion合計：{total}")
print(f"合計: {passed}/{total} PASS  /  {failed} FAIL")
print("=" * 60)

if failed > 0:
    print()
    print("FAILしたテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
else:
    print("全テスト PASS")
