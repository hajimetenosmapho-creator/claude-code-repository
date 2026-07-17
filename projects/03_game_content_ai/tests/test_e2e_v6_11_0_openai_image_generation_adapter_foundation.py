"""
E2E テスト: v6.11.0 OpenAI Image Generation Adapter Foundation

Source of Truth:
    docs/design/openai_image_generation_adapter_foundation.md
    （Architecture Review 5：Approved、Test Review 6：Approved）

本テストは実HTTP・実課金を一切発生させない。openai.OpenAIをRuntime Guardでpatchし、
無許可の実Client構築をAssertionErrorで即座に検出する（31.4章）。通常Scenarioは
Fake Client（client=）を明示注入し、自己生成経路を確認するScenarioのみ、
安全なFake Constructorへ局所的にpatchを上書きする。

Scenario構成（123 Scenario）:
    Public API: PKG-*（4）
    Constructor: CTOR-*（21）
    from_env: ENV-*（12）
    Prompt: PROMPT-*（16）
    Request: REQ-*（4）
    Client Injection: CLIENT-*（7）
    Response: RESP-*（13）
    Base64: B64-*（7）
    MIME: MIME-*（4）
    Provider errors: ERR-*（13）
    Exception chaining: CHAIN-*（4）
    Security messages: MSG-*（3）
    Runtime Guard: GUARD-*（2）
    Side effects: SIDE-*（6）
    Dependency: DEP-*（3）
    Protocol: PROTO-*（2）
    repr: REPR-*（2）

    合計: 123 Scenario / 163 Case / 248 Assertion

Regressionは本ファイルのScenario数に含まない（32.9章のRegression Test Strategy参照）。

実行方法:
    cd projects/03_game_content_ai
    python tests/test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py
"""
import ast
import base64
import sys
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ─── テスト用ユーティリティ（v6.10.0 precedentを踏襲） ───

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


def check_not_contains(label: str, text, keyword: str):
    check(label, keyword in str(text), False)


def check_raises_value_error(label: str, func) -> None:
    """1 Caseにつき1 Assertion。送出確認と型確認を分離しない。"""
    try:
        func()
    except ValueError:
        check(label, "ValueError", "ValueError")
    except Exception as exc:
        check(label, f"{type(exc).__name__} (not ValueError)", "ValueError")
    else:
        check(label, "no exception raised", "ValueError")


def invoke(func):
    """funcを呼び出し、(戻り値, 例外)のタプルを返す。例外がなければ(結果, None)。"""
    try:
        return func(), None
    except BaseException as exc:
        return None, exc


def check_openai_error(label: str, exc, expected_reason, expected_message: str, marker: str = None):
    """OpenAIImageGenerationErrorの型・reason・messageを確認する。
    markerが指定された場合のみ、marker非露出を追加で確認する（4 Assertion）。
    markerが指定されない場合は型・reason・messageの3 Assertionのみ。"""
    check_true(f"{label}. OpenAIImageGenerationErrorが送出される", isinstance(exc, OpenAIImageGenerationError))
    actual_reason = exc.reason if isinstance(exc, OpenAIImageGenerationError) else None
    check(f"{label}. reasonが{expected_reason.name}", actual_reason, expected_reason)
    actual_message = str(exc) if exc is not None else None
    check(f"{label}. messageが固定文言と一致", actual_message, expected_message)
    if marker is not None:
        haystack = "|".join([
            str(exc), repr(exc),
            str(getattr(exc, "args", ())), repr(getattr(exc, "__dict__", {})),
        ])
        check_not_contains(f"{label}. marker({marker})が非露出", haystack, marker)


def check_chain(label: str, exc):
    check(f"{label}. __cause__がNone", exc.__cause__ if exc is not None else "NOT-RAISED", None)
    check(f"{label}. __context__がNone", exc.__context__ if exc is not None else "NOT-RAISED", None)


# ─── AST解析ユーティリティ（v6.10.0 precedentを踏襲） ───


def get_import_details(file_path: Path) -> dict:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    absolute_roots = set()
    relative_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                absolute_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                relative_imports.append({"level": node.level, "module": node.module})
            elif node.module:
                absolute_roots.add(node.module.split(".")[0])
    return {"absolute_roots": absolute_roots, "relative_imports": relative_imports}


def get_call_lines(file_path: Path, func_name: str) -> list:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    lines = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == func_name
        ):
            lines.append(node.lineno)
    return lines


def get_ai_image_generation_imported_names(file_path: Path) -> set:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "ai_image_generation":
            for alias in node.names:
                names.add(alias.name)
    return names


def annotation_name(node):
    if node is None:
        return None
    if isinstance(node, ast.Name):
        return node.id
    if isinstance(node, ast.Attribute):
        return node.attr
    if isinstance(node, ast.Constant):
        return node.value
    return None


print("=" * 60)
print("v6.11.0 OpenAI Image Generation Adapter Foundation E2E テスト")
print("=" * 60)
print()

import openai
import httpx

import openai_image_generation
from openai_image_generation import (
    OpenAIImageGenerator,
    OpenAIImageGenerationError,
    OpenAIImageGenerationErrorReason,
)

OPENAI_IMAGE_GENERATION_DIR = PROJECT_ROOT / "src" / "openai_image_generation"
FILES = {
    "__init__": OPENAI_IMAGE_GENERATION_DIR / "__init__.py",
    "openai_image_generator": OPENAI_IMAGE_GENERATION_DIR / "openai_image_generator.py",
}

# ─── Test Double（31章） ───


class _FakeImagesResource:
    def __init__(self):
        self.calls = []
        self.response = None
        self.exception = None

    def generate(self, **kwargs):
        self.calls.append(kwargs)
        if self.exception is not None:
            raise self.exception
        return self.response


class _FakeOpenAIClient:
    """with_options(timeout=..., max_retries=...)を実装するFake Client（31.2章）。"""

    def __init__(self, images_resource=None):
        self.images = images_resource if images_resource is not None else _FakeImagesResource()
        self.with_options_calls = []
        self._with_options_return = None

    def with_options(self, *, timeout=None, max_retries=None):
        self.with_options_calls.append((timeout, max_retries))
        if self._with_options_return is not None:
            return self._with_options_return
        return self


class _FakeClientWithoutWithOptions:
    """with_options()を意図的に持たない最小Fake（16.2章fail-fast検証用）。"""

    def __init__(self, images_resource=None):
        self.images = images_resource if images_resource is not None else _FakeImagesResource()


class _RecordingFakeOpenAIConstructor:
    """openai.OpenAI(...)の代わりに使う、実Clientを一切生成しない安全なFake。"""

    def __init__(self, fake_client):
        self.calls = []
        self._fake_client = fake_client

    def __call__(self, **kwargs):
        self.calls.append(kwargs)
        return self._fake_client


def make_response(b64_json="aGVsbG8="):
    return SimpleNamespace(data=[SimpleNamespace(b64_json=b64_json)])


def make_normal_generator(**ctor_kwargs):
    images = _FakeImagesResource()
    images.response = make_response()
    client = _FakeOpenAIClient(images)
    generator = OpenAIImageGenerator(api_key="test-api-key", client=client, **ctor_kwargs)
    return generator, client, images


def make_error_generator(exc, **ctor_kwargs):
    images = _FakeImagesResource()
    images.exception = exc
    client = _FakeOpenAIClient(images)
    generator = OpenAIImageGenerator(api_key="test-api-key", client=client, **ctor_kwargs)
    return generator, client, images


def make_resp_generator(response, **ctor_kwargs):
    images = _FakeImagesResource()
    images.response = response
    client = _FakeOpenAIClient(images)
    generator = OpenAIImageGenerator(api_key="test-api-key", client=client, **ctor_kwargs)
    return generator, client, images


# ─── Provider例外Fake構築Helper（31.6章） ───

_TEST_URL = "https://example.invalid/v1/images/generations"


def make_request() -> httpx.Request:
    return httpx.Request(
        "POST", _TEST_URL,
        headers={"Authorization": "Bearer authorization-secret-marker"},
    )


def make_api_status_error(error_type, *, status_code: int, message: str = "provider-secret-marker"):
    response = httpx.Response(
        status_code,
        request=make_request(),
        json={"error": {"message": "response-secret-marker"}},
    )
    return error_type(
        message,
        response=response,
        body={"error": {"message": "body-secret-marker"}},
    )


def make_connection_error() -> "openai.APIConnectionError":
    return openai.APIConnectionError(
        message="connection-secret-marker",
        request=make_request(),
    )


def make_timeout_error() -> "openai.APITimeoutError":
    return openai.APITimeoutError(make_request())


def make_generic_api_error() -> "openai.APIError":
    return openai.APIError(
        "generic-secret-marker",
        make_request(),
        body={"error": "body-secret-marker"},
    )


# ─── Runtime Guard（31.4章） ───

_PATCH_TARGET = "openai.OpenAI"


def _raise_if_real_client_constructed(**kwargs):
    raise AssertionError(
        "OpenAIImageGenerator attempted to construct a real openai.OpenAI client "
        "during E2E execution. Every Scenario must inject client= explicitly "
        "(Architecture Review 1 Finding M-5)."
    )


_TRUE_ORIGINAL_OPENAI_CLIENT = openai.OpenAI

# =====================================================================
# GUARD-PATCH-RESTORE（31.5.2章）
# Guard適用前の真のopenai.OpenAIを、既定Guard適用前に取得しておく。
# =====================================================================

print("[GUARD-PATCH-RESTORE] patch解除後にopenai.OpenAIが復元されること")

with unittest.mock.patch(_PATCH_TARGET, side_effect=_raise_if_real_client_constructed):
    _patched_constructor_during_block = openai.OpenAI
    # このスコープ内ではopenai.OpenAI(...)を実際に呼び出さない。

_restored_constructor = openai.OpenAI
check_true(
    "GUARD-PATCH-RESTORE. withブロック終了後にopenai.OpenAIが元のconstructorへ復元されている",
    _restored_constructor is _TRUE_ORIGINAL_OPENAI_CLIENT,
)
print()

# =====================================================================
# 以降、Guard B（既定：AssertionError版）を適用した状態で全Scenarioを実行する。
# 自己生成経路を検証するScenario（CLIENT-SELFGEN-*）のみ、局所的に
# 安全なFake Constructorへpatchを上書きする。
# =====================================================================

with unittest.mock.patch(_PATCH_TARGET, side_effect=_raise_if_real_client_constructed):

    # =================================================================
    # PKG: Public Package API（4 Scenario / 7 Case / 8 Assertion）
    # =================================================================

    print("[PKG-1] package import")
    check_true("PKG-1. openai_image_generationがimportできる", "openai_image_generation" in sys.modules)
    print()

    print("[PKG-2] 3つのPublic APIをpackage rootからimport")
    check_true("PKG-2. OpenAIImageGeneratorがimportできる", OpenAIImageGenerator is not None)
    check_true("PKG-2. OpenAIImageGenerationErrorがimportできる", OpenAIImageGenerationError is not None)
    check_true("PKG-2. OpenAIImageGenerationErrorReasonがimportできる", OpenAIImageGenerationErrorReason is not None)
    print()

    print("[PKG-3] __all__の集合が3 Public APIと一致し、件数が3")
    check(
        "PKG-3. __all__の集合一致",
        set(openai_image_generation.__all__),
        {"OpenAIImageGenerator", "OpenAIImageGenerationError", "OpenAIImageGenerationErrorReason"},
    )
    check("PKG-3. __all__の件数が3", len(openai_image_generation.__all__), 3)
    print()

    print("[PKG-4] 不要public symbolがpackage属性にない（補助assertion）")
    check_false(
        "PKG-4. NullOpenAIImageGeneratorがpackage属性にない",
        hasattr(openai_image_generation, "NullOpenAIImageGenerator"),
    )
    check_false(
        "PKG-4. OpenAIImageGenerationAuthenticationErrorがpackage属性にない",
        hasattr(openai_image_generation, "OpenAIImageGenerationAuthenticationError"),
    )
    print()

    # =================================================================
    # CTOR: Constructor Contract（21 Scenario / 47 Case / 47 Assertion）
    # =================================================================

    print("[CTOR-KEY-TYPE-NONE] api_key=Noneでvalueerror")
    check_raises_value_error(
        "CTOR-KEY-TYPE-NONE. api_key=NoneでValueError",
        lambda: OpenAIImageGenerator(api_key=None),
    )
    print()

    print("[CTOR-KEY-TYPE-INT] api_key=intでValueError")
    check_raises_value_error(
        "CTOR-KEY-TYPE-INT. api_key=123でValueError",
        lambda: OpenAIImageGenerator(api_key=123),
    )
    print()

    print("[CTOR-KEY-TYPE-BYTES] api_key=bytesでValueError")
    check_raises_value_error(
        "CTOR-KEY-TYPE-BYTES. api_key=b'x'でValueError",
        lambda: OpenAIImageGenerator(api_key=b"test"),
    )
    print()

    print("[CTOR-KEY-BLANK] api_key空・空白のみでValueError")
    for _label, _value in [("空文字", ""), ("空白のみ", "   ")]:
        check_raises_value_error(
            f"CTOR-KEY-BLANK. api_key={_label}({_value!r})でValueError",
            lambda v=_value: OpenAIImageGenerator(api_key=v),
        )
    print()

    print("[CTOR-MODEL-TYPE] model型不正でValueError")
    for _label, _value in [("None", None), ("int", 123)]:
        check_raises_value_error(
            f"CTOR-MODEL-TYPE. model={_label}でValueError",
            lambda v=_value: OpenAIImageGenerator(api_key="test-api-key", model=v),
        )
    print()

    print("[CTOR-MODEL-BLANK] model空・空白のみでValueError")
    for _label, _value in [("空文字", ""), ("空白のみ", "   ")]:
        check_raises_value_error(
            f"CTOR-MODEL-BLANK. model={_label}({_value!r})でValueError",
            lambda v=_value: OpenAIImageGenerator(api_key="test-api-key", model=v),
        )
    print()

    print("[CTOR-SIZE-VALID] 正式7値すべてが受理される")
    _allowed_sizes = (
        "1024x1024", "1536x1024", "1024x1536",
        "2048x2048", "2048x1152",
        "3840x2160", "2160x3840",
    )
    for _size in _allowed_sizes:
        _gen = OpenAIImageGenerator(api_key="test-api-key", size=_size)
        check(f"CTOR-SIZE-VALID. size={_size}が受理される", _gen._size, _size)
    print()

    print("[CTOR-SIZE-INVALID] size不正でValueError")
    for _label, _value in [("allowlist外", "999x999"), ("auto", "auto"), ("型不正", 1024)]:
        check_raises_value_error(
            f"CTOR-SIZE-INVALID. size={_label}({_value!r})でValueError",
            lambda v=_value: OpenAIImageGenerator(api_key="test-api-key", size=v),
        )
    print()

    print("[CTOR-QUALITY-VALID] low/medium/highが受理される")
    for _quality in ("low", "medium", "high"):
        _gen = OpenAIImageGenerator(api_key="test-api-key", quality=_quality)
        check(f"CTOR-QUALITY-VALID. quality={_quality}が受理される", _gen._quality, _quality)
    print()

    print("[CTOR-QUALITY-INVALID] quality不正でValueError")
    for _label, _value in [("allowlist外", "ultra"), ("auto", "auto"), ("型不正", 1)]:
        check_raises_value_error(
            f"CTOR-QUALITY-INVALID. quality={_label}({_value!r})でValueError",
            lambda v=_value: OpenAIImageGenerator(api_key="test-api-key", quality=v),
        )
    print()

    print("[CTOR-FORMAT-VALID] png/jpeg/webpが受理される")
    for _fmt in ("png", "jpeg", "webp"):
        _gen = OpenAIImageGenerator(api_key="test-api-key", output_format=_fmt)
        check(f"CTOR-FORMAT-VALID. output_format={_fmt}が受理される", _gen._output_format, _fmt)
    print()

    print("[CTOR-FORMAT-INVALID] output_format不正でValueError")
    for _label, _value in [("jpg", "jpg"), ("型不正", 1)]:
        check_raises_value_error(
            f"CTOR-FORMAT-INVALID. output_format={_label}({_value!r})でValueError",
            lambda v=_value: OpenAIImageGenerator(api_key="test-api-key", output_format=v),
        )
    print()

    print("[CTOR-TIMEOUT-ZERO] timeout_seconds=0でValueError")
    check_raises_value_error(
        "CTOR-TIMEOUT-ZERO. timeout_seconds=0でValueError",
        lambda: OpenAIImageGenerator(api_key="test-api-key", timeout_seconds=0),
    )
    print()

    print("[CTOR-TIMEOUT-NEGATIVE] timeout_seconds負数でValueError")
    check_raises_value_error(
        "CTOR-TIMEOUT-NEGATIVE. timeout_seconds=-1でValueError",
        lambda: OpenAIImageGenerator(api_key="test-api-key", timeout_seconds=-1),
    )
    print()

    print("[CTOR-TIMEOUT-STR] timeout_seconds=strでValueError")
    check_raises_value_error(
        "CTOR-TIMEOUT-STR. timeout_seconds='180'でValueError",
        lambda: OpenAIImageGenerator(api_key="test-api-key", timeout_seconds="180"),
    )
    print()

    print("[CTOR-TIMEOUT-NONE] timeout_seconds=NoneでValueError")
    check_raises_value_error(
        "CTOR-TIMEOUT-NONE. timeout_seconds=NoneでValueError",
        lambda: OpenAIImageGenerator(api_key="test-api-key", timeout_seconds=None),
    )
    print()

    print("[CTOR-TIMEOUT-FLOAT] timeout_seconds=floatでValueError")
    check_raises_value_error(
        "CTOR-TIMEOUT-FLOAT. timeout_seconds=180.0でValueError",
        lambda: OpenAIImageGenerator(api_key="test-api-key", timeout_seconds=180.0),
    )
    print()

    print("[CTOR-TIMEOUT-BOOL-TRUE] timeout_seconds=TrueでValueError")
    check_raises_value_error(
        "CTOR-TIMEOUT-BOOL-TRUE. timeout_seconds=TrueでValueError",
        lambda: OpenAIImageGenerator(api_key="test-api-key", timeout_seconds=True),
    )
    print()

    print("[CTOR-TIMEOUT-BOOL-FALSE] timeout_seconds=FalseでValueError")
    check_raises_value_error(
        "CTOR-TIMEOUT-BOOL-FALSE. timeout_seconds=FalseでValueError",
        lambda: OpenAIImageGenerator(api_key="test-api-key", timeout_seconds=False),
    )
    print()

    print("[CTOR-DEFAULTS] api_keyのみ指定時の既定値")
    _ctor_defaults_gen = OpenAIImageGenerator(api_key="test-api-key")
    check("CTOR-DEFAULTS. modelの既定値", _ctor_defaults_gen._model, "gpt-image-2-2026-04-21")
    check("CTOR-DEFAULTS. sizeの既定値", _ctor_defaults_gen._size, "1024x1024")
    check("CTOR-DEFAULTS. qualityの既定値", _ctor_defaults_gen._quality, "medium")
    check("CTOR-DEFAULTS. output_formatの既定値", _ctor_defaults_gen._output_format, "png")
    check("CTOR-DEFAULTS. timeout_secondsの既定値", _ctor_defaults_gen._timeout_seconds, 180)
    print()

    print("[CTOR-OVERRIDE] 全引数を明示上書きした場合の反映確認")
    _ctor_override_gen = OpenAIImageGenerator(
        api_key="test-api-key",
        model="gpt-image-2",
        size="2048x2048",
        quality="high",
        output_format="webp",
        timeout_seconds=300,
    )
    check("CTOR-OVERRIDE. modelの上書き", _ctor_override_gen._model, "gpt-image-2")
    check("CTOR-OVERRIDE. sizeの上書き", _ctor_override_gen._size, "2048x2048")
    check("CTOR-OVERRIDE. qualityの上書き", _ctor_override_gen._quality, "high")
    check("CTOR-OVERRIDE. output_formatの上書き", _ctor_override_gen._output_format, "webp")
    check("CTOR-OVERRIDE. timeout_secondsの上書き", _ctor_override_gen._timeout_seconds, 300)
    print()

    # =================================================================
    # ENV: from_env() Contract（12 Scenario / 12 Case / 12 Assertion）
    # =================================================================

    print("[ENV-MISSING-KEY] OPENAI_API_KEY未設定でValueError")
    with unittest.mock.patch.dict("os.environ", {}, clear=True):
        check_raises_value_error(
            "ENV-MISSING-KEY. OPENAI_API_KEY未設定でValueError",
            OpenAIImageGenerator.from_env,
        )
    print()

    print("[ENV-EMPTY-KEY] OPENAI_API_KEY=''でValueError")
    with unittest.mock.patch.dict("os.environ", {"OPENAI_API_KEY": ""}, clear=True):
        check_raises_value_error(
            "ENV-EMPTY-KEY. OPENAI_API_KEY=''でValueError",
            OpenAIImageGenerator.from_env,
        )
    print()

    print("[ENV-BLANK-KEY] OPENAI_API_KEY='   'でValueError")
    with unittest.mock.patch.dict("os.environ", {"OPENAI_API_KEY": "   "}, clear=True):
        check_raises_value_error(
            "ENV-BLANK-KEY. OPENAI_API_KEY='   'でValueError",
            OpenAIImageGenerator.from_env,
        )
    print()

    print("[ENV-TIMEOUT-INVALID-STR] OPENAI_IMAGE_TIMEOUT_SECONDS='abc'でValueError")
    with unittest.mock.patch.dict(
        "os.environ",
        {"OPENAI_API_KEY": "test-api-key", "OPENAI_IMAGE_TIMEOUT_SECONDS": "abc"},
        clear=True,
    ):
        check_raises_value_error(
            "ENV-TIMEOUT-INVALID-STR. OPENAI_IMAGE_TIMEOUT_SECONDS='abc'でValueError",
            OpenAIImageGenerator.from_env,
        )
    print()

    print("[ENV-TIMEOUT-ZERO] OPENAI_IMAGE_TIMEOUT_SECONDS='0'でValueError")
    with unittest.mock.patch.dict(
        "os.environ",
        {"OPENAI_API_KEY": "test-api-key", "OPENAI_IMAGE_TIMEOUT_SECONDS": "0"},
        clear=True,
    ):
        check_raises_value_error(
            "ENV-TIMEOUT-ZERO. OPENAI_IMAGE_TIMEOUT_SECONDS='0'でValueError",
            OpenAIImageGenerator.from_env,
        )
    print()

    print("[ENV-TIMEOUT-NEGATIVE] OPENAI_IMAGE_TIMEOUT_SECONDS='-5'でValueError")
    with unittest.mock.patch.dict(
        "os.environ",
        {"OPENAI_API_KEY": "test-api-key", "OPENAI_IMAGE_TIMEOUT_SECONDS": "-5"},
        clear=True,
    ):
        check_raises_value_error(
            "ENV-TIMEOUT-NEGATIVE. OPENAI_IMAGE_TIMEOUT_SECONDS='-5'でValueError",
            OpenAIImageGenerator.from_env,
        )
    print()

    print("[ENV-TIMEOUT-FLOAT-STR] OPENAI_IMAGE_TIMEOUT_SECONDS='30.5'でValueError")
    with unittest.mock.patch.dict(
        "os.environ",
        {"OPENAI_API_KEY": "test-api-key", "OPENAI_IMAGE_TIMEOUT_SECONDS": "30.5"},
        clear=True,
    ):
        check_raises_value_error(
            "ENV-TIMEOUT-FLOAT-STR. OPENAI_IMAGE_TIMEOUT_SECONDS='30.5'でValueError",
            OpenAIImageGenerator.from_env,
        )
    print()

    print("[ENV-OK-DEFAULT-TIMEOUT] OPENAI_API_KEYのみ設定時、timeout_secondsは既定値180")
    with unittest.mock.patch.dict("os.environ", {"OPENAI_API_KEY": "test-api-key"}, clear=True):
        _env_gen = OpenAIImageGenerator.from_env()
        check("ENV-OK-DEFAULT-TIMEOUT. timeout_secondsが既定値180", _env_gen._timeout_seconds, 180)
    print()

    print("[ENV-OK-CUSTOM-TIMEOUT] OPENAI_IMAGE_TIMEOUT_SECONDS='300'設定時の反映")
    with unittest.mock.patch.dict(
        "os.environ",
        {"OPENAI_API_KEY": "test-api-key", "OPENAI_IMAGE_TIMEOUT_SECONDS": "300"},
        clear=True,
    ):
        _env_gen = OpenAIImageGenerator.from_env()
        check("ENV-OK-CUSTOM-TIMEOUT. timeout_secondsが300", _env_gen._timeout_seconds, 300)
    print()

    print("[ENV-OK-WHITESPACE-TIMEOUT] OPENAI_IMAGE_TIMEOUT_SECONDS=' 30 '（前後空白）でも成功")
    with unittest.mock.patch.dict(
        "os.environ",
        {"OPENAI_API_KEY": "test-api-key", "OPENAI_IMAGE_TIMEOUT_SECONDS": " 30 "},
        clear=True,
    ):
        _env_gen = OpenAIImageGenerator.from_env()
        check("ENV-OK-WHITESPACE-TIMEOUT. timeout_secondsが30", _env_gen._timeout_seconds, 30)
    print()

    print("[ENV-OK-OTHER-DEFAULTS] from_env()はmodel等をConstructorの既定値へ委ねる")
    with unittest.mock.patch.dict("os.environ", {"OPENAI_API_KEY": "test-api-key"}, clear=True):
        _env_gen = OpenAIImageGenerator.from_env()
        check("ENV-OK-OTHER-DEFAULTS. modelが既定値のまま", _env_gen._model, "gpt-image-2-2026-04-21")
    print()

    print("[ENV-ISOLATION] Case間でclear=Trueにより環境変数状態が共有されないこと")
    with unittest.mock.patch.dict(
        "os.environ",
        {"OPENAI_API_KEY": "test-api-key", "OPENAI_IMAGE_TIMEOUT_SECONDS": "999"},
        clear=True,
    ):
        OpenAIImageGenerator.from_env()
    with unittest.mock.patch.dict("os.environ", {"OPENAI_API_KEY": "test-api-key"}, clear=True):
        _env_isolation_gen = OpenAIImageGenerator.from_env()
        check(
            "ENV-ISOLATION. 前Caseのtimeout=999が漏れず既定値180に戻る",
            _env_isolation_gen._timeout_seconds,
            180,
        )
    print()

    # =================================================================
    # PROMPT: Prompt Contract（16 Scenario / 24 Case / 25 Assertion）
    # =================================================================

    print("[PROMPT-TYPE] promptがstr以外でValueError")
    _normal_gen_for_prompt, _, _ = make_normal_generator()
    for _label, _value in [("int", 123), ("None", None), ("list", ["a"])]:
        check_raises_value_error(
            f"PROMPT-TYPE. prompt={_label}でValueError",
            lambda v=_value: _normal_gen_for_prompt.generate(v),
        )
    print()

    print("[PROMPT-STR-SUBCLASS] str subclassはtype()is strチェックにより拒否")

    class _CustomStrSubclass(str):
        """type(x) is str のみを許可するContractを検証するための、
        test file内限定のstr subclass。production packageへは配置しない。"""

    check_raises_value_error(
        "PROMPT-STR-SUBCLASS. str subclassでValueError",
        lambda: _normal_gen_for_prompt.generate(_CustomStrSubclass("正常なprompt")),
    )
    print()

    print("[PROMPT-EMPTY] 空文字でValueError")
    check_raises_value_error(
        "PROMPT-EMPTY. prompt=''でValueError",
        lambda: _normal_gen_for_prompt.generate(""),
    )
    print()

    print("[PROMPT-BLANK] 空白のみでValueError")
    check_raises_value_error(
        "PROMPT-BLANK. prompt='   'でValueError",
        lambda: _normal_gen_for_prompt.generate("   "),
    )
    print()

    print("[PROMPT-SURROUNDING-WHITESPACE] 前後空白を含むpromptは拒否されず、値も保持される")
    _ws_gen, _ws_client, _ws_images = make_normal_generator()
    _ws_prompt = "  正常なprompt  "
    _ws_result, _ws_exc = invoke(lambda: _ws_gen.generate(_ws_prompt))
    check_true("PROMPT-SURROUNDING-WHITESPACE. 例外が発生しない", _ws_exc is None)
    check(
        "PROMPT-SURROUNDING-WHITESPACE. kwargsのpromptが前後空白を保持したまま渡る",
        _ws_images.calls[-1]["prompt"] if _ws_images.calls else None,
        _ws_prompt,
    )
    print()

    print("[PROMPT-LF] 改行(LF)を含む正常系")
    _lf_gen, _, _ = make_normal_generator()
    _r, _e = invoke(lambda: _lf_gen.generate("1行目\n2行目"))
    check_true("PROMPT-LF. 例外が発生しない", _e is None)
    print()

    print("[PROMPT-TAB] tabを含む正常系")
    _tab_gen, _, _ = make_normal_generator()
    _r, _e = invoke(lambda: _tab_gen.generate("col1\tcol2"))
    check_true("PROMPT-TAB. 例外が発生しない", _e is None)
    print()

    print("[PROMPT-CR] carriage returnを含む正常系（CR単独・\\r\\n複数行）")
    for _label, _value in [("CR単独", "1行目\r2行目"), ("CRLF複数行", "1行目\r\n2行目")]:
        _cr_gen, _, _ = make_normal_generator()
        _r, _e = invoke(lambda v=_value: _cr_gen.generate(v))
        check_true(f"PROMPT-CR. {_label}で例外が発生しない", _e is None)
    print()

    print("[PROMPT-NUL-REJECT] NUL文字を含む場合の拒否")
    check_raises_value_error(
        "PROMPT-NUL-REJECT. NUL文字でValueError",
        lambda: _normal_gen_for_prompt.generate("正常\x00prompt"),
    )
    print()

    print("[PROMPT-C0-REJECT] NUL・tab・LF・CR以外のC0制御文字の拒否")
    for _cp in (0x01, 0x08, 0x0B, 0x0C, 0x0E, 0x1F):
        _ch = chr(_cp)
        check_raises_value_error(
            f"PROMPT-C0-REJECT. \\x{_cp:02X}でValueError",
            lambda c=_ch: _normal_gen_for_prompt.generate(f"正常{c}prompt"),
        )
    print()

    print("[PROMPT-DEL-REJECT] DEL（\\x7F）を含む場合の拒否")
    check_raises_value_error(
        "PROMPT-DEL-REJECT. DELでValueError",
        lambda: _normal_gen_for_prompt.generate("正常\x7Fprompt"),
    )
    print()

    print("[PROMPT-MAXLEN-EXCEED] 32001文字でValueError")
    check_raises_value_error(
        "PROMPT-MAXLEN-EXCEED. 32001文字でValueError",
        lambda: _normal_gen_for_prompt.generate("a" * 32001),
    )
    print()

    print("[PROMPT-MAXLEN-BOUNDARY] 32000文字ちょうどは正常")
    _boundary_gen, _, _ = make_normal_generator()
    _r, _e = invoke(lambda: _boundary_gen.generate("a" * 32000))
    check_true("PROMPT-MAXLEN-BOUNDARY. 32000文字ちょうどで例外が発生しない", _e is None)
    print()

    print("[PROMPT-JAPANESE] 正常な日本語prompt")
    _ja_gen, _, _ = make_normal_generator()
    _r, _e = invoke(lambda: _ja_gen.generate("ゲームのキャラクターアイキャッチ画像"))
    check_true("PROMPT-JAPANESE. 例外が発生しない", _e is None)
    print()

    print("[PROMPT-ENGLISH] 正常な英語prompt")
    _en_gen, _, _ = make_normal_generator()
    _r, _e = invoke(lambda: _en_gen.generate("a game character eyecatch illustration"))
    check_true("PROMPT-ENGLISH. 例外が発生しない", _e is None)
    print()

    print("[PROMPT-MIXED-VALID] tab・LF・CR・日本語・英語混在の複合正常系")
    _mixed_gen, _, _ = make_normal_generator()
    _r, _e = invoke(lambda: _mixed_gen.generate("Title\tSubtitle\nキャラクター説明\r\nEnglish line"))
    check_true("PROMPT-MIXED-VALID. 例外が発生しない", _e is None)
    print()

    # =================================================================
    # REQ: Request Contract（4 Scenario / 4 Case / 4 Assertion）
    # =================================================================

    print("[REQ-KWARGS-EXACT] images.generate()へ渡るkwargsのkey集合が正式7項目と一致")
    _req_gen, _req_client, _req_images = make_normal_generator()
    _req_gen.generate("正常なprompt")
    check(
        "REQ-KWARGS-EXACT. kwargs keys",
        set(_req_images.calls[-1].keys()),
        {"model", "prompt", "n", "size", "quality", "output_format", "background"},
    )
    print()

    print("[REQ-N-FIXED] n=1が常に固定で渡る")
    check("REQ-N-FIXED. n=1", _req_images.calls[-1]["n"], 1)
    print()

    print("[REQ-BACKGROUND-FIXED] background='opaque'が常に固定で渡る")
    check("REQ-BACKGROUND-FIXED. background='opaque'", _req_images.calls[-1]["background"], "opaque")
    print()

    print("[REQ-UNUSED-PARAMS-ABSENT] 未採用parameterがkwargsに含まれない")
    _unused_params = {"response_format", "moderation", "stream", "partial_images", "user", "style", "output_compression"}
    check(
        "REQ-UNUSED-PARAMS-ABSENT. 未採用parameterとの共通集合が空",
        _unused_params & set(_req_images.calls[-1].keys()),
        set(),
    )
    print()

    # =================================================================
    # CLIENT: Client Injection（7 Scenario / 7 Case / 11 Assertion）
    # =================================================================

    print("[CLIENT-INJECTED-WITH-OPTIONS-CALLED] 注入Client経路でwith_optionsが正しい引数で呼ばれる")
    _inj_gen, _inj_client, _inj_images = make_normal_generator(timeout_seconds=222)
    _inj_gen.generate("正常なprompt")
    check("CLIENT-INJECTED-WITH-OPTIONS-CALLED. timeout=222", _inj_client.with_options_calls[-1][0], 222)
    check("CLIENT-INJECTED-WITH-OPTIONS-CALLED. max_retries=0", _inj_client.with_options_calls[-1][1], 0)
    print()

    print("[CLIENT-SELFGEN-WITH-OPTIONS-CALLED] 自己生成Client経路でwith_optionsが正しい引数で呼ばれる")
    _selfgen_images = _FakeImagesResource()
    _selfgen_images.response = make_response()
    _selfgen_fake_client = _FakeOpenAIClient(_selfgen_images)
    _selfgen_ctor = _RecordingFakeOpenAIConstructor(_selfgen_fake_client)
    with unittest.mock.patch(_PATCH_TARGET, side_effect=_selfgen_ctor):
        _selfgen_gen = OpenAIImageGenerator(api_key="test-api-key", client=None, timeout_seconds=222)
        _selfgen_gen.generate("正常なprompt")
    check(
        "CLIENT-SELFGEN-WITH-OPTIONS-CALLED. timeout=222",
        _selfgen_fake_client.with_options_calls[-1][0], 222,
    )
    check(
        "CLIENT-SELFGEN-WITH-OPTIONS-CALLED. max_retries=0",
        _selfgen_fake_client.with_options_calls[-1][1], 0,
    )
    print()

    print("[CLIENT-SELFGEN-API-KEY-PASSED] 自己生成経路でapi_keyが正しくopenai.OpenAI(...)へ渡る")
    check(
        "CLIENT-SELFGEN-API-KEY-PASSED. api_keyが期待どおり渡る",
        _selfgen_ctor.calls[-1].get("api_key"),
        "test-api-key",
    )
    print()

    print("[CLIENT-MISSING-WITH-OPTIONS-TYPEERROR] with_options()未実装のClientはTypeError（OpenAIImageGenerationErrorではない）")
    _no_wo_images = _FakeImagesResource()
    _no_wo_images.response = make_response()
    _no_wo_client = _FakeClientWithoutWithOptions(_no_wo_images)
    _no_wo_gen = OpenAIImageGenerator(api_key="test-api-key", client=_no_wo_client)
    _no_wo_result, _no_wo_exc = invoke(lambda: _no_wo_gen.generate("正常なprompt"))
    check("CLIENT-MISSING-WITH-OPTIONS-TYPEERROR. TypeErrorが送出される", type(_no_wo_exc), TypeError)
    check_false(
        "CLIENT-MISSING-WITH-OPTIONS-TYPEERROR. OpenAIImageGenerationErrorではない",
        isinstance(_no_wo_exc, OpenAIImageGenerationError),
    )
    print()

    print("[CLIENT-TYPEERROR-MESSAGE-SAFE] TypeErrorメッセージにapi_keyが含まれない")
    check_not_contains(
        "CLIENT-TYPEERROR-MESSAGE-SAFE. api_keyが非露出",
        str(_no_wo_exc),
        "test-api-key",
    )
    print()

    print("[CLIENT-WITH-OPTIONS-RETURNED-CLIENT-USED] images.generate()はwith_options()の返り値のimagesで発生する")
    _orig_images = _FakeImagesResource()
    _orig_images.response = make_response()
    _returned_images = _FakeImagesResource()
    _returned_images.response = make_response()
    _returned_client = _FakeOpenAIClient(_returned_images)
    _orig_client = _FakeOpenAIClient(_orig_images)
    _orig_client._with_options_return = _returned_client
    _ret_gen = OpenAIImageGenerator(api_key="test-api-key", client=_orig_client)
    _ret_gen.generate("正常なprompt")
    check(
        "CLIENT-WITH-OPTIONS-RETURNED-CLIENT-USED. 呼び出しはwith_optionsの返り値のimagesで発生",
        (len(_orig_images.calls), len(_returned_images.calls)),
        (0, 1),
    )
    print()

    print("[CLIENT-ORIGINAL-NOT-MUTATED] 注入したoriginal clientのimages参照はwith_options呼び出し後も同一")
    _mut_gen, _mut_client, _mut_images = make_normal_generator()
    _mut_images_ref_before = _mut_client.images
    _mut_gen.generate("正常なprompt")
    check(
        "CLIENT-ORIGINAL-NOT-MUTATED. client.imagesの参照が同一",
        _mut_client.images is _mut_images_ref_before,
        True,
    )
    check(
        "CLIENT-ORIGINAL-NOT-MUTATED. with_optionsが1回呼ばれている",
        len(_mut_client.with_options_calls),
        1,
    )
    print()

    # =================================================================
    # RESP: Response Contract（13 Scenario / 13 Case / 39 Assertion）
    # =================================================================

    print("[RESP-*] Response構造異常はすべてOpenAIImageGenerationError（reason=INVALID_RESPONSE）")
    _RESP_MSG = "OpenAI Images APIのレスポンス構造が不正です"

    _resp_cases = [
        ("RESP-NONE", None),
        ("RESP-BAD-TYPE", "not-a-response-object"),
        ("RESP-DATA-MISSING", SimpleNamespace()),
        ("RESP-DATA-NONE", SimpleNamespace(data=None)),
        ("RESP-DATA-EMPTY", SimpleNamespace(data=[])),
        ("RESP-DATA-NOT-LIST", SimpleNamespace(data="not-a-list")),
        ("RESP-DATA-ZERO-EXPLICIT", SimpleNamespace(data=list())),
        ("RESP-DATA-TWO-ELEMENTS", SimpleNamespace(data=[SimpleNamespace(b64_json="aGk="), SimpleNamespace(b64_json="aGk=")])),
        ("RESP-B64JSON-MISSING", SimpleNamespace(data=[SimpleNamespace()])),
        ("RESP-B64JSON-NONE", SimpleNamespace(data=[SimpleNamespace(b64_json=None)])),
        ("RESP-B64JSON-NOT-STR", SimpleNamespace(data=[SimpleNamespace(b64_json=123)])),
        ("RESP-B64JSON-EMPTY", SimpleNamespace(data=[SimpleNamespace(b64_json="")])),
    ]
    _resp_none_exc = None
    for _scenario_id, _bad_response in _resp_cases:
        _r_gen, _, _ = make_resp_generator(_bad_response)
        _r_result, _r_exc = invoke(lambda g=_r_gen: g.generate("正常なprompt"))
        check_openai_error(_scenario_id, _r_exc, OpenAIImageGenerationErrorReason.INVALID_RESPONSE, _RESP_MSG)
        if _scenario_id == "RESP-NONE":
            _resp_none_exc = _r_exc
    print()

    print("[RESP-NORMAL] 正常なresponse構造からGeneratedImageが得られる")
    _resp_normal_gen, _, _ = make_normal_generator()
    _resp_normal_result, _resp_normal_exc = invoke(lambda: _resp_normal_gen.generate("正常なprompt"))
    from ai_image_generation import GeneratedImage
    check_true("RESP-NORMAL. GeneratedImageが返る", isinstance(_resp_normal_result, GeneratedImage))
    check_true(
        "RESP-NORMAL. image_bytesがtype(...)is bytes",
        type(_resp_normal_result.image_bytes) is bytes if _resp_normal_result else False,
    )
    check(
        "RESP-NORMAL. mime_typeがimage/png",
        _resp_normal_result.mime_type if _resp_normal_result else None,
        "image/png",
    )
    print()

    # =================================================================
    # B64: Strict Base64 Decode Contract（7 Scenario / 7 Case / 19 Assertion）
    # =================================================================

    print("[B64-*] Base64異常はすべてOpenAIImageGenerationError（reason=INVALID_RESPONSE）")
    _B64_MSG = "OpenAI Images APIのレスポンスのBase64データが不正です"

    _b64_failure_cases = [
        ("B64-INVALID-CHARS", "!!!!"),
        ("B64-PADDING-INSUFFICIENT", "ab"),
        ("B64-PADDING-EXCESSIVE", "===="),
        ("B64-EMBEDDED-NEWLINE", "aGVs\nbG8="),
        ("B64-EMBEDDED-SPACE", "aGVs bG8="),
    ]
    for _scenario_id, _bad_b64 in _b64_failure_cases:
        _b_gen, _, _ = make_resp_generator(make_response(b64_json=_bad_b64))
        _b_result, _b_exc = invoke(lambda g=_b_gen: g.generate("正常なprompt"))
        check_openai_error(_scenario_id, _b_exc, OpenAIImageGenerationErrorReason.INVALID_RESPONSE, _B64_MSG)
    print()

    print("[B64-EMPTY-RESULT-PATCH] base64.b64decodeをpatchし、強制的にb''を返した場合の防御分岐（AD-20）")
    _B64_EMPTY_MSG = "OpenAI Images APIのレスポンスのデコード結果が空でした"
    _b64_empty_gen, _, _ = make_normal_generator()
    _B64DECODE_PATCH_TARGET = "openai_image_generation.openai_image_generator.base64.b64decode"
    with unittest.mock.patch(_B64DECODE_PATCH_TARGET, return_value=b""):
        _b64_empty_result, _b64_empty_exc = invoke(lambda: _b64_empty_gen.generate("正常なprompt"))
    check_openai_error(
        "B64-EMPTY-RESULT-PATCH", _b64_empty_exc,
        OpenAIImageGenerationErrorReason.INVALID_RESPONSE, _B64_EMPTY_MSG,
    )
    print()

    print("[B64-VALID-NORMAL] 有効な非空Base64がstrict decodeで正しくdecodeされる")
    _b64_valid_gen, _, _ = make_normal_generator()
    _b64_valid_result, _b64_valid_exc = invoke(lambda: _b64_valid_gen.generate("正常なprompt"))
    check(
        "B64-VALID-NORMAL. decode結果が期待どおり",
        _b64_valid_result.image_bytes if _b64_valid_result else None,
        base64.b64decode("aGVsbG8=", validate=True),
    )
    print()

    # =================================================================
    # MIME: MIME Type Contract（4 Scenario / 4 Case / 4 Assertion）
    # =================================================================

    print("[MIME-PNG] output_format=png -> image/png")
    _mime_png_gen, _, _ = make_normal_generator(output_format="png")
    _mime_png_result, _ = invoke(lambda: _mime_png_gen.generate("正常なprompt"))
    check("MIME-PNG. mime_type=image/png", _mime_png_result.mime_type if _mime_png_result else None, "image/png")
    print()

    print("[MIME-JPEG] output_format=jpeg -> image/jpeg")
    _mime_jpeg_gen, _, _ = make_normal_generator(output_format="jpeg")
    _mime_jpeg_result, _ = invoke(lambda: _mime_jpeg_gen.generate("正常なprompt"))
    check("MIME-JPEG. mime_type=image/jpeg", _mime_jpeg_result.mime_type if _mime_jpeg_result else None, "image/jpeg")
    print()

    print("[MIME-WEBP] output_format=webp -> image/webp")
    _mime_webp_gen, _, _ = make_normal_generator(output_format="webp")
    _mime_webp_result, _ = invoke(lambda: _mime_webp_gen.generate("正常なprompt"))
    check("MIME-WEBP. mime_type=image/webp", _mime_webp_result.mime_type if _mime_webp_result else None, "image/webp")
    print()

    print("[MIME-FROM-REQUEST-NOT-RESPONSE] mime_typeはresponse.output_formatではなく自身のoutput_formatから決定")
    _mime_resp = SimpleNamespace(data=[SimpleNamespace(b64_json="aGVsbG8=")], output_format="jpeg")
    _mime_mismatch_gen, _, _ = make_resp_generator(_mime_resp, output_format="png")
    _mime_mismatch_result, _ = invoke(lambda: _mime_mismatch_gen.generate("正常なprompt"))
    check(
        "MIME-FROM-REQUEST-NOT-RESPONSE. response.output_format='jpeg'でも自身のoutput_format='png'に従う",
        _mime_mismatch_result.mime_type if _mime_mismatch_result else None,
        "image/png",
    )
    print()

    # =================================================================
    # ERR: Provider Failure（13 Scenario / 13 Case / 49 Assertion）
    # =================================================================

    print("[ERR-*] Provider例外Scenario Matrix（32.5.1章）")

    _ERR_MARKER = "provider-secret-marker"

    _err_auth_exc = None
    _err_unknown_exc_exc = None

    _err_cases = [
        ("ERR-AUTH", make_api_status_error(openai.AuthenticationError, status_code=401),
         OpenAIImageGenerationErrorReason.AUTHENTICATION, "OpenAI APIへの認証に失敗しました"),
        ("ERR-PERM", make_api_status_error(openai.PermissionDeniedError, status_code=403),
         OpenAIImageGenerationErrorReason.PERMISSION_DENIED,
         "OpenAI APIへのアクセス権限がありません（Organization Verification等の可能性）"),
        ("ERR-RATE", make_api_status_error(openai.RateLimitError, status_code=429),
         OpenAIImageGenerationErrorReason.RATE_LIMIT, "OpenAI APIのレート制限に達しました"),
        ("ERR-TIMEOUT", make_timeout_error(),
         OpenAIImageGenerationErrorReason.TIMEOUT, "OpenAI APIへのリクエストがタイムアウトしました"),
        ("ERR-CONN", make_connection_error(),
         OpenAIImageGenerationErrorReason.CONNECTION, "OpenAI APIへの接続に失敗しました"),
        ("ERR-BADREQ", make_api_status_error(openai.BadRequestError, status_code=400),
         OpenAIImageGenerationErrorReason.REQUEST_REJECTED,
         "OpenAI APIへのリクエストが不正です（Content Policy等による生成拒否を含む）"),
        ("ERR-NOTFOUND", make_api_status_error(openai.NotFoundError, status_code=404),
         OpenAIImageGenerationErrorReason.REQUEST_REJECTED,
         "OpenAI APIへのリクエストが不正です（Content Policy等による生成拒否を含む）"),
        ("ERR-CONFLICT", make_api_status_error(openai.ConflictError, status_code=409),
         OpenAIImageGenerationErrorReason.REQUEST_REJECTED,
         "OpenAI APIへのリクエストが不正です（Content Policy等による生成拒否を含む）"),
        ("ERR-UNPROCESSABLE", make_api_status_error(openai.UnprocessableEntityError, status_code=422),
         OpenAIImageGenerationErrorReason.REQUEST_REJECTED,
         "OpenAI APIへのリクエストが不正です（Content Policy等による生成拒否を含む）"),
        ("ERR-SERVER", make_api_status_error(openai.InternalServerError, status_code=500),
         OpenAIImageGenerationErrorReason.SERVER_ERROR, "OpenAI API側でエラーが発生しました"),
        ("ERR-GENERIC", make_generic_api_error(),
         OpenAIImageGenerationErrorReason.UNKNOWN, "OpenAI Images APIの呼び出しに失敗しました"),
        ("ERR-UNKNOWN-EXC", RuntimeError("unexpected-marker"),
         OpenAIImageGenerationErrorReason.UNKNOWN, "OpenAI Images APIの呼び出し中に予期しないエラーが発生しました"),
    ]
    for _scenario_id, _provider_exc, _expected_reason, _expected_msg in _err_cases:
        _e_gen, _, _ = make_error_generator(_provider_exc)
        _e_result, _e_exc = invoke(lambda g=_e_gen: g.generate("正常なprompt"))
        check_openai_error(_scenario_id, _e_exc, _expected_reason, _expected_msg, marker=_ERR_MARKER)
        if _scenario_id == "ERR-AUTH":
            _err_auth_exc = _e_exc
        if _scenario_id == "ERR-UNKNOWN-EXC":
            _err_unknown_exc_exc = _e_exc
    print()

    print("[ERR-TIMEOUT-NOT-ABSORBED] APITimeoutErrorがAPIConnectionError(CONNECTION)に誤分類されないこと")
    _diff_gen, _, _ = make_error_generator(make_timeout_error())
    _diff_result, _diff_exc = invoke(lambda: _diff_gen.generate("正常なprompt"))
    _diff_reason = _diff_exc.reason if isinstance(_diff_exc, OpenAIImageGenerationError) else None
    check(
        "ERR-TIMEOUT-NOT-ABSORBED. reasonがTIMEOUT（CONNECTIONではない）",
        _diff_reason,
        OpenAIImageGenerationErrorReason.TIMEOUT,
    )
    print()

    # =================================================================
    # CHAIN: Exception Chaining（4 Scenario / 4 Case / 8 Assertion）
    # =================================================================

    print("[CHAIN-*] classify-then-raise-outside-exceptにより__cause__／__context__双方が到達不能")
    check_chain("CHAIN-APIERROR", _err_auth_exc)
    check_chain("CHAIN-OTHEREXC", _err_unknown_exc_exc)
    check_chain("CHAIN-B64", _b64_empty_exc)
    check_chain("CHAIN-RESP", _resp_none_exc)
    print()

    # =================================================================
    # MSG: Security messages（3 Scenario / 3 Case / 3 Assertion）
    # =================================================================

    print("[MSG-PROMPT-NOT-LEAKED] prompt全文が例外へ非露出")
    _msg_prompt_gen, _, _ = make_error_generator(make_api_status_error(openai.AuthenticationError, status_code=401))
    _msg_prompt_result, _msg_prompt_exc = invoke(
        lambda: _msg_prompt_gen.generate("この中にprompt-secret-markerを含む通常の文章")
    )
    check_not_contains(
        "MSG-PROMPT-NOT-LEAKED. promptが例外へ非露出",
        f"{_msg_prompt_exc!s}{_msg_prompt_exc!r}",
        "prompt-secret-marker",
    )
    print()

    print("[MSG-APIKEY-NOT-LEAKED] api_keyが例外へ非露出")
    _msg_key_images = _FakeImagesResource()
    _msg_key_images.exception = make_api_status_error(openai.AuthenticationError, status_code=401)
    _msg_key_client = _FakeOpenAIClient(_msg_key_images)
    _msg_key_gen = OpenAIImageGenerator(api_key="api-key-secret-marker", client=_msg_key_client)
    _msg_key_result, _msg_key_exc = invoke(lambda: _msg_key_gen.generate("正常なprompt"))
    check_not_contains(
        "MSG-APIKEY-NOT-LEAKED. api_keyが例外へ非露出",
        f"{_msg_key_exc!s}{_msg_key_exc!r}",
        "api-key-secret-marker",
    )
    print()

    print("[MSG-B64-NOT-LEAKED] Base64文字列そのものが例外へ非露出")
    _msg_b64_gen, _, _ = make_resp_generator(make_response(b64_json="b64-secret-marker!!!"))
    _msg_b64_result, _msg_b64_exc = invoke(lambda: _msg_b64_gen.generate("正常なprompt"))
    check_not_contains(
        "MSG-B64-NOT-LEAKED. Base64文字列が例外へ非露出",
        f"{_msg_b64_exc!s}{_msg_b64_exc!r}",
        "b64-secret-marker",
    )
    print()

    # =================================================================
    # GUARD: Runtime Guard（2 Scenario / 2 Case / 3 Assertion）
    # =================================================================

    print("[GUARD-SELFTEST] Runtime Guardが実際にopenai.OpenAI(...)を遮断すること")
    with unittest.mock.patch(_PATCH_TARGET, side_effect=_raise_if_real_client_constructed):
        _guard_raised_type = None
        _guard_raised_message = None
        try:
            openai.OpenAI(api_key="test-api-key")
        except AssertionError as _guard_exc:
            _guard_raised_type = type(_guard_exc)
            _guard_raised_message = str(_guard_exc)
    check("GUARD-SELFTEST. AssertionErrorが送出される", _guard_raised_type, AssertionError)
    check(
        "GUARD-SELFTEST. messageが固定文言と一致",
        _guard_raised_message,
        "OpenAIImageGenerator attempted to construct a real openai.OpenAI client "
        "during E2E execution. Every Scenario must inject client= explicitly "
        "(Architecture Review 1 Finding M-5).",
    )
    print()

    print("[GUARD-PATCH-RESTORE] （31.5.2章のとおり、Guard適用前に既に実行・確認済み）")
    print()

    # =================================================================
    # SIDE: Side Effect（6 Scenario / 6 Case / 6 Assertion）
    # =================================================================

    _import_details = {name: get_import_details(path) for name, path in FILES.items()}

    print("[SIDE-NO-OPEN] open()呼び出しがないこと（AST）")
    _open_violations = []
    for _name, _path in FILES.items():
        _open_violations.extend(get_call_lines(_path, "open"))
    check("SIDE-NO-OPEN. open()呼び出しが0件", _open_violations, [])
    print()

    print("[SIDE-NO-PRINT] print()呼び出しがないこと（AST）")
    _print_violations = []
    for _name, _path in FILES.items():
        _print_violations.extend(get_call_lines(_path, "print"))
    check("SIDE-NO-PRINT. print()呼び出しが0件", _print_violations, [])
    print()

    print("[SIDE-NO-LOGGING-IMPORT] loggingのimportがないこと（AST）")
    _logging_violations = [n for n, d in _import_details.items() if "logging" in d["absolute_roots"]]
    check("SIDE-NO-LOGGING-IMPORT. loggingをimportしているファイルが0件", _logging_violations, [])
    print()

    print("[SIDE-NO-SUBPROCESS-IMPORT] subprocessのimportがないこと（AST）")
    _subprocess_violations = [n for n, d in _import_details.items() if "subprocess" in d["absolute_roots"]]
    check("SIDE-NO-SUBPROCESS-IMPORT. subprocessをimportしているファイルが0件", _subprocess_violations, [])
    print()

    print("[SIDE-NO-SLEEP] sleep（time.sleepを含む）のimportがないこと（AST）")
    _sleep_violations = [n for n, d in _import_details.items() if "time" in d["absolute_roots"]]
    _sleep_call_violations = []
    for _name, _path in FILES.items():
        _sleep_call_violations.extend(get_call_lines(_path, "sleep"))
    check(
        "SIDE-NO-SLEEP. time importおよびsleep()呼び出しが0件",
        (_sleep_violations, _sleep_call_violations),
        ([], []),
    )
    print()

    print("[SIDE-GENERATE-CALL-COUNT-ONE] images.generate()の呼び出し回数が1回であること")
    _side_gen, _side_client, _side_images = make_normal_generator()
    _side_gen.generate("正常なprompt")
    check("SIDE-GENERATE-CALL-COUNT-ONE. 呼び出し回数が1", len(_side_images.calls), 1)
    print()

    # =================================================================
    # DEP: Dependency（AST、3 Scenario / 6 Case / 6 Assertion）
    # =================================================================

    ALLOWED_MODULES = {"base64", "binascii", "os", "enum", "ai_image_generation", "openai"}
    FORBIDDEN_EXACT = (
        "wordpress_media", "outputs", "image_resolver", "ArticleData",
        "workflow", "scheduler", "requests", "anthropic", "PIL", "Pillow",
    )
    FORBIDDEN_PREFIXES = ("retry_",)

    print("[DEP-1] 標準ライブラリ + ai_image_generation + openai 以外への絶対importがないこと")
    for _name, _details in _import_details.items():
        check_true(
            f"DEP-1. {_name}の絶対importが許可集合の部分集合",
            _details["absolute_roots"].issubset(ALLOWED_MODULES),
        )
    print()

    print("[DEP-2] 禁止packageへのimportがないこと")
    for _name, _details in _import_details.items():
        _violations = sorted(
            m for m in _details["absolute_roots"]
            if m in FORBIDDEN_EXACT or m.startswith(FORBIDDEN_PREFIXES)
        )
        check(f"DEP-2. {_name}の禁止import違反リストが空", _violations, [])
    print()

    print("[DEP-3] ai_image_generationからのimportがGeneratedImageのみであること")
    for _name, _path in FILES.items():
        _names = get_ai_image_generation_imported_names(_path)
        check_true(f"DEP-3. {_name}のai_image_generation importがGeneratedImageのみの部分集合", _names.issubset({"GeneratedImage"}))
    print()

    # =================================================================
    # PROTO: Protocol適合（2 Scenario / 2 Case / 2 Assertion）
    # =================================================================

    print("[PROTO-STRUCTURAL] generate(prompt)呼び出しでGeneratedImageが返ること自体が構造適合の実証")
    _proto_gen, _, _ = make_normal_generator()
    _proto_result, _ = invoke(lambda: _proto_gen.generate("正常なprompt"))
    check_true("PROTO-STRUCTURAL. GeneratedImageが返る", isinstance(_proto_result, GeneratedImage))
    print()

    print("[PROTO-SIGNATURE] inspect.signatureによるgenerate()のパラメータ名・戻り値annotation補助確認")
    import inspect
    _sig = inspect.signature(OpenAIImageGenerator.generate)
    _param_names = [p for p in _sig.parameters if p != "self"]
    check(
        "PROTO-SIGNATURE. パラメータ名が['prompt']、戻り値annotationがGeneratedImage",
        (_param_names, _sig.return_annotation is GeneratedImage or _sig.return_annotation == "GeneratedImage"),
        (["prompt"], True),
    )
    print()

    # =================================================================
    # REPR: repr Contract（2 Scenario / 2 Case / 2 Assertion）
    # =================================================================

    print("[REPR-DEFAULT-FORMAT] 既定object.__repr__形式（クラス名＋メモリアドレス）であること")
    _repr_gen = OpenAIImageGenerator(api_key="repr-test-key")
    _repr_text = repr(_repr_gen)
    check_true(
        "REPR-DEFAULT-FORMAT. 既定reprの形式（<...OpenAIImageGenerator object at 0x...>）",
        _repr_text.startswith("<") and "OpenAIImageGenerator object at 0x" in _repr_text,
    )
    print()

    print("[REPR-NO-SECRETS] reprにapi_keyが含まれない")
    check_not_contains("REPR-NO-SECRETS. api_keyが非露出", _repr_text, "repr-test-key")
    print()

# ─── 結果サマリー ───
print("=" * 60)
total = len(results_log)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = total - passed
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
