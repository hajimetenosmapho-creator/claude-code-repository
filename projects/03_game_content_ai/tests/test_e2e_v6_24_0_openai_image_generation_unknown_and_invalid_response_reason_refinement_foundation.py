"""
E2E テスト: v6.24.0 OpenAI Image Generation Unknown and Invalid Response Reason Refinement Foundation

Source of Truth:
    docs/design/openai_image_generation_unknown_and_invalid_response_reason_refinement_foundation.md
    （Architecture Review：Approved with Minor Amendments／Production実装前Gate：
      Gate 1/2/4/5 PASS・Gate 3 Required Amendment 反映済み。承認済み設計書）

DI-11 後半：v6.23 時点で1値へ集約されていた2組の失敗経路を reason 値として分離する。
    UNKNOWN          → APIError catch-all は UNKNOWN のまま／generic except Exception のみ
                       UNEXPECTED_EXCEPTION へ
    INVALID_RESPONSE → Base64 系は INVALID_RESPONSE のまま／data・b64_json 構造不正のみ
                       INVALID_RESPONSE_STRUCTURE へ
UNKNOWN／INVALID_RESPONSE は削除せず後方互換のため保持する。

本テストは実HTTP・実課金を一切発生させない。socket を遮断し、openai.OpenAI を
Runtime Guard で patch して無許可の実Client構築を検出する。

Assertion 構成（設計書12.6.2節・見込み346）:
    API-              24    Enum 15値の shape・value・定義順・__all__
    UNK-              10    UNKNOWN 2経路の分離（catch-all／generic）
    RESP-             37    data／b64_json 構造不正 → INVALID_RESPONSE_STRUCTURE
    B64-              19    Base64 デコード失敗／0バイト → INVALID_RESPONSE（不変）
    SPLIT-             2    RESP 群と B64 群の reason が相異なる（DEF-6.23-4 の直接証拠）
    COMPAT-           24    既存10経路の reason／message 不変・旧2値の後方互換
    POLICY-           34    fallback policy の全数写像（15値）
    CONT-              7    CONTINUE 集合の非拡大
    ZERODIFF-         31    v6.23.0 時点との action／category 一致
    POLICYFILE-        2    policy module の baseline 差分空・AST 等価
    ASTEQ-             2    _classify_api_error の baseline AST 等価
    NOVALPARSE-       24    外部応答値読み取りの positive allow-list guard（I-VAL-1）
    CHAIN-             4    exception chaining（新2経路 × 2）
    MSG-               4    message 定数集合の不変・secret 非露出
    SIG-               3    _validate_response_structure の signature／3要素返却形
    DEP-               3    依存 guard
    COMPATAPI-        13    周辺 Public API 不変
    NOIMPACT-         98    Runtime Zero Diff（baseline 固定 guard・実値ベース陽性対照）
    SOCKET-            3    実通信0件
    ENV-               2    環境変数の非汚染
    ────────────────────────
    合計              346

数え方（設計書12.6.1節 R-a〜R-e）:
    1 assertion = results_log への1 append = check() の1回呼び出し。
    反復回数と assertion 数は一致しない場合がある（12.6.3節）。

実行方法:
    cd projects/03_game_content_ai
    .\\venv\\Scripts\\python.exe tests\\test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_refinement_foundation.py
"""
import ast
import dataclasses
import inspect
import os
import socket
import subprocess
import sys
import unittest.mock
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ─── テスト用ユーティリティ（v6.19.0／v6.22.0／v6.23.0 precedent を踏襲） ───

results_log = []


def check(label: str, actual, expected):
    ok = actual == expected
    results_log.append(("PASS" if ok else "FAIL", label))
    print(f"  [{'OK' if ok else 'NG'}] {label}")
    if not ok:
        print(f"       期待値: {expected!r}")
        print(f"       実際値: {actual!r}")


def check_true(label: str, value):
    check(label, bool(value), True)


def check_false(label: str, value):
    check(label, bool(value), False)


def check_not_contains(label: str, text, keyword: str):
    check(label, keyword in str(text), False)


def invoke(func):
    try:
        return func(), None
    except BaseException as exc:  # noqa: BLE001
        return None, exc


# ─── 環境変数スナップショット ───

_ENV_KEYS = (
    "AI_IMAGE_GENERATION_ENABLED",
    "OPENAI_API_KEY",
    "OPENAI_IMAGE_TIMEOUT_SECONDS",
    "WP_SITE_URL",
    "WP_USERNAME",
    "WP_APP_PASSWORD",
)
_SAVED_ENV = {key: os.environ.get(key) for key in _ENV_KEYS}
_SAVED_ENVIRON_SNAPSHOT = dict(os.environ)


def _restore_env():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


# ─── in-process network 遮断（テスト全体を通じて有効） ───

class _NetworkBlocked(RuntimeError):
    pass


_ORIG_GETADDRINFO = socket.getaddrinfo
_ORIG_CONNECT = socket.socket.connect


def _blocked_getaddrinfo(*args, **kwargs):
    raise _NetworkBlocked("socket.getaddrinfo is blocked in this test")


def _blocked_connect(*args, **kwargs):
    raise _NetworkBlocked("socket.socket.connect is blocked in this test")


socket.getaddrinfo = _blocked_getaddrinfo
socket.socket.connect = _blocked_connect

try:
    import httpx
    import openai

    # Runtime Guard：無許可の実 OpenAI Client 構築を検出する
    _real_client_construction_count = {"n": 0}
    _ORIG_OPENAI_CLIENT = openai.OpenAI

    def _guarded_openai_client(*args, **kwargs):
        _real_client_construction_count["n"] += 1
        raise AssertionError("実 openai.OpenAI が構築されました（テスト契約違反）")

    openai.OpenAI = _guarded_openai_client

    import image_generation_fallback_policy as _policy_pkg
    import openai_image_generation as _v611_pkg
    from image_generation_fallback_policy import (
        ImageGenerationFailureCategory,
        ImageGenerationFallbackAction,
        ImageGenerationFallbackDecision,
        decide_image_generation_fallback,
    )
    from image_generation_fallback_policy.image_generation_fallback_policy import (
        _CONTINUABLE_REASONS,
        _REJECTED_REASONS,
    )
    from openai_image_generation import (
        OpenAIImageGenerationError,
        OpenAIImageGenerationErrorReason,
        OpenAIImageGenerator,
    )
    from openai_image_generation.openai_image_generator import _classify_api_error

    from article_featured_media_runtime import ArticleFeaturedMediaRuntimeStatus
    from wordpress_media import WordPressMediaUploadError, WordPressMediaUploadErrorReason

    R = OpenAIImageGenerationErrorReason
    CAT = ImageGenerationFailureCategory
    ACT = ImageGenerationFallbackAction

    OPENAI_MODULE_FILE = (
        PROJECT_ROOT / "src" / "openai_image_generation" / "openai_image_generator.py"
    )
    POLICY_MODULE_FILE = (
        PROJECT_ROOT / "src" / "image_generation_fallback_policy"
        / "image_generation_fallback_policy.py"
    )

    BASELINE_COMMIT = "38e2487db5760034f4a994319350244960a42e1b"
    _REPO_REL_OPENAI = (
        "projects/03_game_content_ai/src/openai_image_generation/openai_image_generator.py"
    )

    # 凍結 message（v6.23.0 時点の文字列。1文字も変更してはならない）
    MSG_AUTH = "OpenAI APIへの認証に失敗しました"
    MSG_PERM = "OpenAI APIへのアクセス権限がありません（Organization Verification等の可能性）"
    MSG_RATE = "OpenAI APIのレート制限に達しました"
    MSG_TIMEOUT = "OpenAI APIへのリクエストがタイムアウトしました"
    MSG_CONN = "OpenAI APIへの接続に失敗しました"
    MSG_REJECTED = "OpenAI APIへのリクエストが不正です（Content Policy等による生成拒否を含む）"
    MSG_SERVER = "OpenAI API側でエラーが発生しました"
    MSG_CATCHALL = "OpenAI Images APIの呼び出しに失敗しました"
    MSG_UNEXPECTED = "OpenAI Images APIの呼び出し中に予期しないエラーが発生しました"
    MSG_RESP_STRUCTURE = "OpenAI Images APIのレスポンス構造が不正です"
    MSG_B64_INVALID = "OpenAI Images APIのレスポンスのBase64データが不正です"
    MSG_B64_EMPTY = "OpenAI Images APIのレスポンスのデコード結果が空でした"

    # ─── Fake provider 例外の構築（実通信なし） ───

    SECRET_MARKER = "provider-secret-marker-0xC0FFEE"

    def make_request():
        return httpx.Request("POST", "https://example.invalid/v1/images/generations")

    def make_http_response(status_code: int):
        return httpx.Response(
            status_code,
            request=make_request(),
            json={"error": {"message": SECRET_MARKER, "code": SECRET_MARKER}},
        )

    def make_status_error(error_type, status_code: int):
        return error_type(
            SECRET_MARKER,
            response=make_http_response(status_code),
            body={"error": {"message": SECRET_MARKER}},
        )

    def make_timeout_error():
        return openai.APITimeoutError(make_request())

    def make_connection_error():
        return openai.APIConnectionError(message=SECRET_MARKER, request=make_request())

    def make_generic_api_error():
        return openai.APIError(SECRET_MARKER, make_request(), body=None)

    # ─── Fake OpenAI client ───

    class _FakeImages:
        def __init__(self, *, error=None, response=None):
            self._error = error
            self._response = response

        def generate(self, **kwargs):
            if self._error is not None:
                raise self._error
            return self._response

    class _FakeClient:
        def __init__(self, *, error=None, response=None):
            self.images = _FakeImages(error=error, response=response)

        def with_options(self, **kwargs):
            return self

    def make_error_generator(error, **ctor_kwargs):
        return OpenAIImageGenerator(
            api_key="test-key", client=_FakeClient(error=error), **ctor_kwargs
        )

    def make_resp_generator(response, **ctor_kwargs):
        return OpenAIImageGenerator(
            api_key="test-key", client=_FakeClient(response=response), **ctor_kwargs
        )

    def make_normal_response(b64_json="aGVsbG8="):
        return SimpleNamespace(data=[SimpleNamespace(b64_json=b64_json)])

    def check_openai_error(label, exc, expected_reason, expected_message, marker=None):
        """型・reason・message を確認する（marker 指定時のみ4 assertion）。"""
        check_true(f"{label}-TYPE. OpenAIImageGenerationError が送出される",
                   isinstance(exc, OpenAIImageGenerationError))
        check(f"{label}-REASON. reason が {expected_reason.name} である",
              getattr(exc, "reason", None), expected_reason)
        check(f"{label}-MSG. message が凍結文字列と完全一致する",
              str(exc) if exc is not None else None, expected_message)
        if marker is not None:
            check_not_contains(
                f"{label}-NO-SECRET. secret marker が露出しない",
                "|".join([str(exc), repr(exc), str(getattr(exc, "args", ())),
                          repr(getattr(exc, "__dict__", {}))]),
                marker,
            )

    # ─── AST ヘルパ ───

    def parse_file(path: Path):
        return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

    def find_function(tree, name):
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
                return node
        return None

    def get_import_roots(path: Path):
        tree = parse_file(path)
        roots = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    roots.add(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom) and node.module:
                roots.add(node.module.split(".")[0])
        return roots

    def git_out(args, cwd=PROJECT_ROOT):
        """git をバイト列で実行し UTF-8 で復号する（cp932 依存を避ける）。"""
        proc = subprocess.run(["git"] + args, cwd=str(cwd), capture_output=True, timeout=30)
        return proc.returncode, proc.stdout.decode("utf-8", errors="replace")

    def git_show_baseline(repo_rel_path):
        rc, out = git_out(["show", f"{BASELINE_COMMIT}:{repo_rel_path}"], cwd=PROJECT_ROOT)
        return rc, out

    # ─── NOVALPARSE guard 本体（設計書7.8.2節 I-VAL-1・12.5.1節） ───
    # 条件(a) は「外部応答値に由来する識別子集合 R を根とする ast.Attribute が0件」
    # であり、関数全体の Attribute を禁止するものではない（内部 Enum 参照は許容）。

    _ALLOWED_GETATTR_NAMES = {"data", "b64_json"}

    def _root_name(node):
        """Subscript／Attribute チェーンを遡って根の Name.id を返す。"""
        cur = node
        while isinstance(cur, (ast.Subscript, ast.Attribute)):
            cur = cur.value
        return cur.id if isinstance(cur, ast.Name) else None

    def response_param_name(func_node):
        """応答引数名を AST から決定する（ハードコードしない）。"""
        args = func_node.args
        positional = list(args.posonlyargs) + list(args.args)
        return positional[0].arg if positional else None

    def derive_response_identifiers(func_node):
        """R = {応答引数} ∪ {getattr 戻り値の代入先} の不動点集合（12.5.1節 手順3）。"""
        param = response_param_name(func_node)
        if param is None:
            return None
        identifiers = {param}
        changed = True
        while changed:
            changed = False
            for node in ast.walk(func_node):
                if not isinstance(node, ast.Assign):
                    continue
                value = node.value
                if not (isinstance(value, ast.Call)
                        and isinstance(value.func, ast.Name)
                        and value.func.id == "getattr"):
                    continue
                if not value.args or _root_name(value.args[0]) not in identifiers:
                    continue
                for target in node.targets:
                    if isinstance(target, ast.Name) and target.id not in identifiers:
                        identifiers.add(target.id)
                        changed = True
        return identifiers

    def scan_response_read(func_node):
        """戻り値: (R, scoped_attrs, getattr_calls, allowed, violations)"""
        identifiers = derive_response_identifiers(func_node)
        if identifiers is None:
            return (None, [], [], 0, ["<no positional parameter>"])
        violations = []
        scoped_attrs = [
            n for n in ast.walk(func_node)
            if isinstance(n, ast.Attribute) and _root_name(n) in identifiers
        ]
        for node in scoped_attrs:
            violations.append(f"L{node.lineno}: R-rooted ast.Attribute（条件a 違反）")
        getattr_calls = [
            n for n in ast.walk(func_node)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id == "getattr"
        ]
        if len(getattr_calls) != 2:
            violations.append(f"getattr 件数={len(getattr_calls)}（条件b 違反）")
        allowed = 0
        for node in getattr_calls:
            ok_c = len(node.args) == 3 and not node.keywords
            ok_d = (
                len(node.args) >= 2
                and isinstance(node.args[1], ast.Constant)
                and isinstance(node.args[1].value, str)
                and node.args[1].value in _ALLOWED_GETATTR_NAMES
            )
            if ok_c and ok_d:
                allowed += 1
            else:
                violations.append(f"L{node.lineno}: getattr 形（条件c/d 違反）")
        return (identifiers, scoped_attrs, getattr_calls, allowed, violations)

    def scan_snippet(src, func_name="_validate_response_structure"):
        node = find_function(ast.parse(src), func_name)
        return scan_response_read(node) if node is not None else None

    # 対照群の基底：現行実装と同じ形（違反0件になるべき本体）
    _VALID_BODY = (
        "def _validate_response_structure(response):\n"
        "    data = getattr(response, 'data', _MISSING)\n"
        "    if not isinstance(data, list) or len(data) != 1:\n"
        "        return (_MSG, R.INVALID_RESPONSE_STRUCTURE, None)\n"
        "    b64_json = getattr(data[0], 'b64_json', _MISSING)\n"
        "    if not isinstance(b64_json, str) or not b64_json:\n"
        "        return (_MSG, R.INVALID_RESPONSE_STRUCTURE, None)\n"
        "    return (None, None, b64_json)\n"
    )

    def _with_extra_line(extra):
        """_VALID_BODY の末尾 return の直前へ1行差し込む。"""
        lines = _VALID_BODY.rstrip("\n").split("\n")
        return "\n".join(lines[:-1] + [f"    {extra}"] + [lines[-1]]) + "\n"

    print("=" * 70)
    print("v6.24.0 OpenAI Image Generation Unknown and Invalid Response Reason "
          "Refinement Foundation")
    print("=" * 70)
    print()

    # =====================================================================
    # API: Enum 15値の shape（24 assertion）
    # =====================================================================

    print("[API] Enum 15値の Public API")

    _EXPECTED_NAME_VALUE = [
        ("AUTHENTICATION", "authentication"),
        ("PERMISSION_DENIED", "permission_denied"),
        ("RATE_LIMIT", "rate_limit"),
        ("TIMEOUT", "timeout"),
        ("CONNECTION", "connection"),
        ("REQUEST_REJECTED", "request_rejected"),
        ("SERVER_ERROR", "server_error"),
        ("INVALID_RESPONSE", "invalid_response"),
        ("UNKNOWN", "unknown"),
        ("BAD_REQUEST", "bad_request"),
        ("RESOURCE_NOT_FOUND", "resource_not_found"),
        ("CONFLICT", "conflict"),
        ("UNPROCESSABLE_ENTITY", "unprocessable_entity"),
        ("UNEXPECTED_EXCEPTION", "unexpected_exception"),
        ("INVALID_RESPONSE_STRUCTURE", "invalid_response_structure"),
    ]
    _PREFIX_13 = _EXPECTED_NAME_VALUE[:13]
    _NEW_NAMES = ["UNEXPECTED_EXCEPTION", "INVALID_RESPONSE_STRUCTURE"]
    _ALL_REASONS = list(R)

    check("API-COUNT-15. Enum member が15値である", len(_ALL_REASONS), 15)
    check(
        "API-NAMES-EXACT. name 集合が期待15値と一致する",
        sorted(r.name for r in _ALL_REASONS),
        sorted(n for n, _ in _EXPECTED_NAME_VALUE),
    )
    check(
        "API-VALUES-EXACT. value 集合が期待15値と一致する",
        sorted(r.value for r in _ALL_REASONS),
        sorted(v for _, v in _EXPECTED_NAME_VALUE),
    )
    check("API-VALUE-UNIQUE. value に重複がない", len({r.value for r in _ALL_REASONS}), 15)
    for _name, _value in _EXPECTED_NAME_VALUE:
        check(f"API-VALUE[{_name}]. value が {_value} である", getattr(R, _name).value, _value)
    check(
        "API-DEFINITION-ORDER. 定義順が既存13値（v6.23.0 時点の順序）＋新2値の順である",
        [r.name for r in _ALL_REASONS],
        [n for n, _ in _EXPECTED_NAME_VALUE],
    )
    check(
        "API-PREFIX-13-UNCHANGED. 先頭13値の name・value・順序が v6.23.0 時点と完全一致する",
        [(r.name, r.value) for r in _ALL_REASONS[:13]],
        _PREFIX_13,
    )
    for _name in _NEW_NAMES:
        check_true(
            f"API-PKG-ROOT[{_name}]. package root 経由の Enum から参照できる",
            isinstance(getattr(_v611_pkg.OpenAIImageGenerationErrorReason, _name), R),
        )
    check(
        "API-ALL-UNCHANGED. __all__ が3 symbol のまま不変である",
        sorted(_v611_pkg.__all__),
        sorted(["OpenAIImageGenerator", "OpenAIImageGenerationError",
                "OpenAIImageGenerationErrorReason"]),
    )
    print()

    # =====================================================================
    # UNK: UNKNOWN 2経路の分離（10 assertion）
    # =====================================================================

    print("[UNK] UNKNOWN 2経路の分離（DEF-6.23-3）")

    _unk_catchall_gen = make_error_generator(make_generic_api_error())
    _, _unk_catchall_exc = invoke(lambda: _unk_catchall_gen.generate("正常なprompt"))
    check_openai_error("UNK-APIERROR-CATCHALL", _unk_catchall_exc, R.UNKNOWN,
                       MSG_CATCHALL, marker=SECRET_MARKER)

    _unk_generic_gen = make_error_generator(RuntimeError(SECRET_MARKER))
    _, _unk_generic_exc = invoke(lambda: _unk_generic_gen.generate("正常なprompt"))
    check_openai_error("UNK-GENERIC-EXCEPTION", _unk_generic_exc, R.UNEXPECTED_EXCEPTION,
                       MSG_UNEXPECTED, marker=SECRET_MARKER)

    check_true(
        "UNK-DISTINCT. catch-all 経路と generic except Exception 経路の reason が相異なる"
        "（DEF-6.23-3 解消の直接証拠）",
        getattr(_unk_catchall_exc, "reason", None)
        is not getattr(_unk_generic_exc, "reason", None),
    )
    check(
        "UNK-CATCHALL-STILL-UNKNOWN. _classify_api_error の catch-all が UNKNOWN のまま不変である",
        _classify_api_error(make_generic_api_error())[1],
        R.UNKNOWN,
    )
    print()

    # =====================================================================
    # RESP: 構造不正 → INVALID_RESPONSE_STRUCTURE（37 assertion）
    # =====================================================================

    print("[RESP] data／b64_json 構造不正 → INVALID_RESPONSE_STRUCTURE")

    _RESP_CASES = [
        ("RESP-NONE", None),
        ("RESP-BAD-TYPE", "not-a-response-object"),
        ("RESP-DATA-MISSING", SimpleNamespace()),
        ("RESP-DATA-NONE", SimpleNamespace(data=None)),
        ("RESP-DATA-EMPTY", SimpleNamespace(data=[])),
        ("RESP-DATA-NOT-LIST", SimpleNamespace(data="not-a-list")),
        ("RESP-DATA-ZERO-EXPLICIT", SimpleNamespace(data=list())),
        ("RESP-DATA-TWO-ELEMENTS", SimpleNamespace(
            data=[SimpleNamespace(b64_json="aGk="), SimpleNamespace(b64_json="aGk=")])),
        ("RESP-B64JSON-MISSING", SimpleNamespace(data=[SimpleNamespace()])),
        ("RESP-B64JSON-NONE", SimpleNamespace(data=[SimpleNamespace(b64_json=None)])),
        ("RESP-B64JSON-NOT-STR", SimpleNamespace(data=[SimpleNamespace(b64_json=123)])),
        ("RESP-B64JSON-EMPTY", SimpleNamespace(data=[SimpleNamespace(b64_json="")])),
    ]
    _resp_reasons = set()
    _resp_first_exc = None
    for _cid, _bad_response in _RESP_CASES:
        _gen = make_resp_generator(_bad_response)
        _, _raised = invoke(lambda g=_gen: g.generate("正常なprompt"))
        _resp_reasons.add(getattr(_raised, "reason", None))
        if _resp_first_exc is None:
            _resp_first_exc = _raised
        check_openai_error(_cid, _raised, R.INVALID_RESPONSE_STRUCTURE, MSG_RESP_STRUCTURE)
    check(
        "RESP-REASON-UNIFORM. 構造不正12ケースの reason が INVALID_RESPONSE_STRUCTURE 単一である",
        _resp_reasons,
        {R.INVALID_RESPONSE_STRUCTURE},
    )
    print()

    # =====================================================================
    # B64: Base64 系 → INVALID_RESPONSE（不変。19 assertion）
    # =====================================================================

    print("[B64] Base64 デコード失敗／0バイト → INVALID_RESPONSE（不変）")

    _B64_INVALID_CASES = [
        ("B64-INVALID-CHARS", "!!!!"),
        ("B64-PADDING-INSUFFICIENT", "ab"),
        ("B64-PADDING-EXCESSIVE", "===="),
        ("B64-EMBEDDED-NEWLINE", "aGVs\nbG8="),
        ("B64-EMBEDDED-SPACE", "aGVs bG8="),
    ]
    _b64_reasons = set()
    _b64_first_exc = None
    for _cid, _bad_b64 in _B64_INVALID_CASES:
        _gen = make_resp_generator(make_normal_response(b64_json=_bad_b64))
        _, _raised = invoke(lambda g=_gen: g.generate("正常なprompt"))
        _b64_reasons.add(getattr(_raised, "reason", None))
        if _b64_first_exc is None:
            _b64_first_exc = _raised
        check_openai_error(_cid, _raised, R.INVALID_RESPONSE, MSG_B64_INVALID)

    _b64_empty_gen = make_resp_generator(make_normal_response())
    with unittest.mock.patch(
        "openai_image_generation.openai_image_generator.base64.b64decode", return_value=b""
    ):
        _, _b64_empty_exc = invoke(lambda: _b64_empty_gen.generate("正常なprompt"))
    _b64_reasons.add(getattr(_b64_empty_exc, "reason", None))
    check_openai_error("B64-EMPTY-RESULT-PATCH", _b64_empty_exc, R.INVALID_RESPONSE, MSG_B64_EMPTY)

    check(
        "B64-REASON-UNCHANGED. Base64 系6ケースの reason が INVALID_RESPONSE 単一のまま不変である",
        _b64_reasons,
        {R.INVALID_RESPONSE},
    )
    print()

    # =====================================================================
    # SPLIT: RESP 群と B64 群の分離（2 assertion）
    # =====================================================================

    print("[SPLIT] INVALID_RESPONSE の細分化（DEF-6.23-4）")

    check_true(
        "SPLIT-RESP-VS-B64-DISTINCT. 構造不正群と Base64 群の reason が相異なる"
        "（DEF-6.23-4 解消の直接証拠）",
        getattr(_resp_first_exc, "reason", None) is not getattr(_b64_first_exc, "reason", None),
    )
    check(
        "SPLIT-DISJOINT. 構造不正群の reason 集合と Base64 群の reason 集合が交わらない"
        "（18ケースの実測集計 → 1 assertion）",
        sorted(r.name for r in (_resp_reasons & _b64_reasons)),
        [],
    )
    print()

    # =====================================================================
    # COMPAT: 既存10経路の不変・旧2値の後方互換（24 assertion）
    # =====================================================================

    print("[COMPAT] 既存10経路の reason／message 不変・旧2値の後方互換")

    _CLS_CASES = [
        ("AUTH", make_status_error(openai.AuthenticationError, 401), R.AUTHENTICATION, MSG_AUTH),
        ("PERM", make_status_error(openai.PermissionDeniedError, 403), R.PERMISSION_DENIED, MSG_PERM),
        ("RATE", make_status_error(openai.RateLimitError, 429), R.RATE_LIMIT, MSG_RATE),
        ("TIMEOUT", make_timeout_error(), R.TIMEOUT, MSG_TIMEOUT),
        ("CONN", make_connection_error(), R.CONNECTION, MSG_CONN),
        ("BADREQ", make_status_error(openai.BadRequestError, 400), R.BAD_REQUEST, MSG_REJECTED),
        ("NOTFOUND", make_status_error(openai.NotFoundError, 404), R.RESOURCE_NOT_FOUND, MSG_REJECTED),
        ("CONFLICT", make_status_error(openai.ConflictError, 409), R.CONFLICT, MSG_REJECTED),
        ("UNPROCESSABLE", make_status_error(openai.UnprocessableEntityError, 422),
         R.UNPROCESSABLE_ENTITY, MSG_REJECTED),
        ("SERVER", make_status_error(openai.InternalServerError, 500), R.SERVER_ERROR, MSG_SERVER),
    ]
    for _cid, _exc, _expected_reason, _expected_msg in _CLS_CASES:
        _msg, _reason = _classify_api_error(_exc)
        check(f"COMPAT-CLS-{_cid}-REASON. reason が {_expected_reason.name} のまま不変である",
              _reason, _expected_reason)
        check(f"COMPAT-CLS-{_cid}-MSG. message が凍結文字列と完全一致する", _msg, _expected_msg)

    check_true("COMPAT-UNKNOWN-EXISTS. UNKNOWN が Enum member として存続している",
               hasattr(R, "UNKNOWN"))
    check("COMPAT-UNKNOWN-VALUE. UNKNOWN の value が unknown のまま不変である",
          R.UNKNOWN.value, "unknown")
    check_true("COMPAT-INVALID-RESPONSE-EXISTS. INVALID_RESPONSE が Enum member として存続している",
               hasattr(R, "INVALID_RESPONSE"))
    check("COMPAT-INVALID-RESPONSE-VALUE. INVALID_RESPONSE の value が invalid_response のまま不変である",
          R.INVALID_RESPONSE.value, "invalid_response")
    print()

    # =====================================================================
    # POLICY: fallback policy の全数写像（15値・34 assertion）
    # =====================================================================

    print("[POLICY] fallback policy の全数写像（15値）")

    _EXPECTED_CATEGORY = {
        "TIMEOUT": CAT.IMAGE_GENERATION_FAILED,
        "CONNECTION": CAT.IMAGE_GENERATION_FAILED,
        "RATE_LIMIT": CAT.IMAGE_GENERATION_FAILED,
        "SERVER_ERROR": CAT.IMAGE_GENERATION_FAILED,
        "REQUEST_REJECTED": CAT.IMAGE_GENERATION_REQUEST_REJECTED,
        "BAD_REQUEST": CAT.IMAGE_GENERATION_REQUEST_REJECTED,
        "RESOURCE_NOT_FOUND": CAT.IMAGE_GENERATION_REQUEST_REJECTED,
        "CONFLICT": CAT.IMAGE_GENERATION_REQUEST_REJECTED,
        "UNPROCESSABLE_ENTITY": CAT.IMAGE_GENERATION_REQUEST_REJECTED,
        "AUTHENTICATION": CAT.IMAGE_GENERATION_NOT_AUTHORIZED,
        "PERMISSION_DENIED": CAT.IMAGE_GENERATION_NOT_AUTHORIZED,
        "INVALID_RESPONSE": CAT.UNCLASSIFIED,
        "UNKNOWN": CAT.UNCLASSIFIED,
        "UNEXPECTED_EXCEPTION": CAT.UNCLASSIFIED,
        "INVALID_RESPONSE_STRUCTURE": CAT.UNCLASSIFIED,
    }
    _EXPECTED_ACTION = {
        CAT.IMAGE_GENERATION_FAILED: ACT.CONTINUE_WITHOUT_FEATURED_MEDIA,
        CAT.IMAGE_GENERATION_REQUEST_REJECTED: ACT.PROPAGATE_ORIGINAL_ERROR,
        CAT.IMAGE_GENERATION_NOT_AUTHORIZED: ACT.PROPAGATE_ORIGINAL_ERROR,
        CAT.UNCLASSIFIED: ACT.PROPAGATE_ORIGINAL_ERROR,
    }

    _actual_category = {}
    for _reason in _ALL_REASONS:
        _d = decide_image_generation_fallback(OpenAIImageGenerationError("probe", _reason))
        _actual_category[_reason] = _d.category
        check(f"POLICY-CATEGORY[{_reason.name}]. category が写像表と一致する",
              _d.category, _EXPECTED_CATEGORY[_reason.name])
    for _reason in _ALL_REASONS:
        _d = decide_image_generation_fallback(OpenAIImageGenerationError("probe", _reason))
        check(f"POLICY-ACTION[{_reason.name}]. action が写像表と一致する",
              _d.action, _EXPECTED_ACTION[_EXPECTED_CATEGORY[_reason.name]])

    check(
        "POLICY-COVERAGE-15. Enum 全15値が写像表と過不足なく一致する",
        {r.name for r in _ALL_REASONS},
        set(_EXPECTED_CATEGORY.keys()),
    )
    _split = {}
    for _cat in _actual_category.values():
        _split[_cat] = _split.get(_cat, 0) + 1
    check(
        "POLICY-SPLIT. 実測集計が 4/5/2/4 に分割される"
        "（FAILED 側が4のままであることが CONTINUE 非拡大の直接証拠。15反復 → 1 assertion）",
        {
            CAT.IMAGE_GENERATION_FAILED: _split.get(CAT.IMAGE_GENERATION_FAILED, 0),
            CAT.IMAGE_GENERATION_REQUEST_REJECTED: _split.get(CAT.IMAGE_GENERATION_REQUEST_REJECTED, 0),
            CAT.IMAGE_GENERATION_NOT_AUTHORIZED: _split.get(CAT.IMAGE_GENERATION_NOT_AUTHORIZED, 0),
            CAT.UNCLASSIFIED: _split.get(CAT.UNCLASSIFIED, 0),
        },
        {
            CAT.IMAGE_GENERATION_FAILED: 4,
            CAT.IMAGE_GENERATION_REQUEST_REJECTED: 5,
            CAT.IMAGE_GENERATION_NOT_AUTHORIZED: 2,
            CAT.UNCLASSIFIED: 4,
        },
    )
    check("POLICY-SPLIT-TOTAL. 実測分類の合計が15件である", sum(_split.values()), 15)
    check(
        "POLICY-NO-STRAY-CATEGORY. 実測 category が既存4種以外へ分類されていない",
        set(_split.keys()),
        {CAT.IMAGE_GENERATION_FAILED, CAT.IMAGE_GENERATION_REQUEST_REJECTED,
         CAT.IMAGE_GENERATION_NOT_AUTHORIZED, CAT.UNCLASSIFIED},
    )
    print()

    # =====================================================================
    # CONT: CONTINUE 集合の非拡大（7 assertion）
    # =====================================================================

    print("[CONT] CONTINUE 集合の非拡大")

    check(
        "CONT-SET-EXACT. _CONTINUABLE_REASONS が既存4値と完全一致する",
        _CONTINUABLE_REASONS,
        frozenset({R.TIMEOUT, R.CONNECTION, R.RATE_LIMIT, R.SERVER_ERROR}),
    )
    check("CONT-SET-SIZE-4. 要素数が4である", len(_CONTINUABLE_REASONS), 4)
    _actual_continue = sorted(
        r.name for r in _ALL_REASONS
        if decide_image_generation_fallback(
            OpenAIImageGenerationError("probe", r)
        ).action is ACT.CONTINUE_WITHOUT_FEATURED_MEDIA
    )
    check(
        "CONT-ACTUAL-EXACTLY-4. 実測で CONTINUE となる reason が正確に4値である",
        _actual_continue,
        sorted(["TIMEOUT", "CONNECTION", "RATE_LIMIT", "SERVER_ERROR"]),
    )
    for _name in _NEW_NAMES:
        check_false(
            f"CONT-NEW-NONE[{_name}]. v6.24.0 で追加した reason は CONTINUE にならない",
            decide_image_generation_fallback(
                OpenAIImageGenerationError("probe", getattr(R, _name))
            ).action is ACT.CONTINUE_WITHOUT_FEATURED_MEDIA,
        )
    check(
        "CONT-CATEGORY-FAILED-COUNT-4. IMAGE_GENERATION_FAILED へ写像される reason が4件である",
        _split.get(CAT.IMAGE_GENERATION_FAILED, 0),
        4,
    )
    _cont_before = frozenset(_CONTINUABLE_REASONS)
    decide_image_generation_fallback(WordPressMediaUploadError("probe"))
    check("CONT-IMMUTABLE. decide() 呼び出し後も内容が不変である",
          frozenset(_CONTINUABLE_REASONS), _cont_before)
    print()

    # =====================================================================
    # ZERODIFF: v6.23.0 時点との action／category 一致（31 assertion）
    # =====================================================================

    print("[ZERODIFF] v6.23.0 時点との Runtime action／category Zero Diff")

    _V623_EXPECTED = {
        "AUTHENTICATION": (CAT.IMAGE_GENERATION_NOT_AUTHORIZED, ACT.PROPAGATE_ORIGINAL_ERROR),
        "PERMISSION_DENIED": (CAT.IMAGE_GENERATION_NOT_AUTHORIZED, ACT.PROPAGATE_ORIGINAL_ERROR),
        "RATE_LIMIT": (CAT.IMAGE_GENERATION_FAILED, ACT.CONTINUE_WITHOUT_FEATURED_MEDIA),
        "TIMEOUT": (CAT.IMAGE_GENERATION_FAILED, ACT.CONTINUE_WITHOUT_FEATURED_MEDIA),
        "CONNECTION": (CAT.IMAGE_GENERATION_FAILED, ACT.CONTINUE_WITHOUT_FEATURED_MEDIA),
        "REQUEST_REJECTED": (CAT.IMAGE_GENERATION_REQUEST_REJECTED, ACT.PROPAGATE_ORIGINAL_ERROR),
        "SERVER_ERROR": (CAT.IMAGE_GENERATION_FAILED, ACT.CONTINUE_WITHOUT_FEATURED_MEDIA),
        "INVALID_RESPONSE": (CAT.UNCLASSIFIED, ACT.PROPAGATE_ORIGINAL_ERROR),
        "UNKNOWN": (CAT.UNCLASSIFIED, ACT.PROPAGATE_ORIGINAL_ERROR),
        "BAD_REQUEST": (CAT.IMAGE_GENERATION_REQUEST_REJECTED, ACT.PROPAGATE_ORIGINAL_ERROR),
        "RESOURCE_NOT_FOUND": (CAT.IMAGE_GENERATION_REQUEST_REJECTED, ACT.PROPAGATE_ORIGINAL_ERROR),
        "CONFLICT": (CAT.IMAGE_GENERATION_REQUEST_REJECTED, ACT.PROPAGATE_ORIGINAL_ERROR),
        "UNPROCESSABLE_ENTITY": (CAT.IMAGE_GENERATION_REQUEST_REJECTED, ACT.PROPAGATE_ORIGINAL_ERROR),
    }
    for _name, (_exp_cat, _exp_act) in _V623_EXPECTED.items():
        _d = decide_image_generation_fallback(
            OpenAIImageGenerationError("probe", getattr(R, _name))
        )
        check(f"ZERODIFF-CATEGORY-V623[{_name}]. category が v6.23.0 時点と一致する",
              _d.category, _exp_cat)
    for _name, (_exp_cat, _exp_act) in _V623_EXPECTED.items():
        _d = decide_image_generation_fallback(
            OpenAIImageGenerationError("probe", getattr(R, _name))
        )
        check(f"ZERODIFF-ACTION-V623[{_name}]. action が v6.23.0 時点と一致する",
              _d.action, _exp_act)
    for _name in _NEW_NAMES:
        _d = decide_image_generation_fallback(
            OpenAIImageGenerationError("probe", getattr(R, _name))
        )
        check(f"ZERODIFF-NEW-CATEGORY[{_name}]. 新 reason が UNCLASSIFIED へ落ちる",
              _d.category, CAT.UNCLASSIFIED)
    for _name in _NEW_NAMES:
        _d = decide_image_generation_fallback(
            OpenAIImageGenerationError("probe", getattr(R, _name))
        )
        check(f"ZERODIFF-NEW-ACTION[{_name}]. 新 reason が PROPAGATE_ORIGINAL_ERROR となる",
              _d.action, ACT.PROPAGATE_ORIGINAL_ERROR)
    check(
        "ZERODIFF-PARTIAL-ENUM-ONLY. 新2 reason が allow-list 2集合のいずれにも属さない"
        "（C-17 の安全側性質により写像追加不要であることの証明）",
        sorted(n for n in _NEW_NAMES
               if getattr(R, n) in _REJECTED_REASONS or getattr(R, n) in _CONTINUABLE_REASONS),
        [],
    )
    print()

    # =====================================================================
    # POLICYFILE: policy module の無改修（2 assertion）
    # =====================================================================

    print("[POLICYFILE] image_generation_fallback_policy.py の baseline 差分空")

    _rc_policy, _policy_diff = git_out(
        ["diff", "--name-only", "--relative", BASELINE_COMMIT, "--",
         "src/image_generation_fallback_policy"]
    )
    check(
        "POLICYFILE-DIFF-EMPTY. policy package の baseline からの差分が空である（G-8・AC-21）",
        sorted(line.strip() for line in _policy_diff.splitlines() if line.strip()),
        [],
    )
    _rc_pb, _policy_baseline_src = git_show_baseline(
        "projects/03_game_content_ai/src/image_generation_fallback_policy"
        "/image_generation_fallback_policy.py"
    )
    check_true(
        "POLICYFILE-AST-EQUAL. policy module が baseline と AST 等価である",
        _rc_pb == 0
        and ast.dump(ast.parse(_policy_baseline_src))
        == ast.dump(parse_file(POLICY_MODULE_FILE)),
    )
    print()

    # =====================================================================
    # ASTEQ: _classify_api_error の baseline AST 等価（2 assertion）
    # =====================================================================

    print("[ASTEQ] _classify_api_error の 0 diff（C-1・G-9）")

    _rc_ob, _openai_baseline_src = git_show_baseline(_REPO_REL_OPENAI)
    check_true("ASTEQ-BASELINE-AVAILABLE. baseline 版のソースを取得できる（vacuous pass 防止）",
               _rc_ob == 0 and len(_openai_baseline_src) > 0)
    _baseline_classify = find_function(ast.parse(_openai_baseline_src), "_classify_api_error")
    _current_classify = find_function(parse_file(OPENAI_MODULE_FILE), "_classify_api_error")
    check_true(
        "ASTEQ-CLASSIFY-EQUAL. _classify_api_error が baseline と AST 完全一致である",
        _baseline_classify is not None and _current_classify is not None
        and ast.dump(_baseline_classify) == ast.dump(_current_classify),
    )
    print()

    # =====================================================================
    # NOVALPARSE: 外部応答値読み取りの positive allow-list guard（24 assertion）
    # =====================================================================

    print("[NOVALPARSE] 外部応答値読み取りの positive allow-list guard（I-VAL-1）")

    _openai_tree = parse_file(OPENAI_MODULE_FILE)
    _validate_node = find_function(_openai_tree, "_validate_response_structure")

    check_true("NOVALPARSE-FN-FOUND. _validate_response_structure の FunctionDef を検出できる",
               _validate_node is not None)
    check("NOVALPARSE-PARAM-NAME. 応答引数名を AST から決定できる（ハードコードしない）",
          response_param_name(_validate_node), "response")

    _R_ids, _scoped_attrs, _getattrs, _allowed, _violations = scan_response_read(_validate_node)
    check(
        "NOVALPARSE-ATTRIBUTE-ZERO. R を根とする ast.Attribute が0件である（条件a）"
        "（R外の内部 Enum 参照は対象外）",
        len(_scoped_attrs), 0,
    )
    check("NOVALPARSE-GETATTR-COUNT-2. getattr 呼び出しがちょうど2件である（条件b・"
          "0件なら走査が空振り＝vacuous pass 防止）", len(_getattrs), 2)
    check("NOVALPARSE-ALLOWED-EQUALS-TOTAL. 全 getattr が allow 形である（条件c・d）",
          _allowed, len(_getattrs))
    check("NOVALPARSE-VIOLATIONS-EMPTY. 違反が0件である（I-VAL-1。2件の getattr 走査 → 1 assertion）",
          _violations, [])

    _build_node = find_function(_openai_tree, "_build_generated_image")
    _, _, _, _, _build_violations = scan_response_read(_build_node)
    check_true(
        "NOVALPARSE-SCOPE-FUNCTION-ONLY. 同じ規則を他関数（_build_generated_image）へ適用すると"
        "違反が出る＝検査対象を _validate_response_structure に限定する必要がある（設計書7.8.4節）",
        len(_build_violations) > 0,
    )

    _POSITIVE_CASES = {
        "V-1 response.data（ドット記法）": _with_extra_line("_x = response.data"),
        "V-2 response.text": _with_extra_line("_x = response.text"),
        "V-3 response.content": _with_extra_line("_x = response.content"),
        "V-4 response.headers": _with_extra_line("_x = response.headers"),
        "V-5 response.status_code": _with_extra_line("_x = response.status_code"),
        "V-6 response.json()": _with_extra_line("_x = response.json()"),
        "V-7 response.<未知属性>": _with_extra_line("_x = response.future_unknown_attr_xyz"),
        "V-8 getattr(response,'text',...)":
            _VALID_BODY.replace("getattr(response, 'data', _MISSING)",
                                "getattr(response, 'text', _MISSING)"),
        "V-9 getattr(response,'status_code',...)":
            _VALID_BODY.replace("getattr(response, 'data', _MISSING)",
                                "getattr(response, 'status_code', _MISSING)"),
        "V-10 getattr 2引数形式":
            _VALID_BODY.replace("getattr(response, 'data', _MISSING)",
                                "getattr(response, 'data')"),
        "V-11 getattr 第2引数が非 Constant":
            _VALID_BODY.replace("getattr(response, 'data', _MISSING)",
                                "getattr(response, attr_name, _MISSING)"),
        "V-12 getattr 3件目": _with_extra_line("_x = getattr(_other, 'data', None)"),
    }
    for _label, _src in _POSITIVE_CASES.items():
        _res = scan_snippet(_src)
        check_true(f"NOVALPARSE-POSITIVE[{_label}]. allow-list 外の形が違反として検出される",
                   _res is not None and len(_res[4]) > 0)

    _NEGATIVE_CASES = {
        "W-1 許可形1 getattr(response,'data',_MISSING)": _VALID_BODY,
        "W-2 許可形2 getattr(data[0],'b64_json',_MISSING)": _VALID_BODY,
        "W-3 構造検査（isinstance／len／subscript／真偽評価）":
            _with_extra_line("_ok = isinstance(data, list) and len(data) == 1 and not b64_json"),
        "W-4 docstring 中の属性名":
            _VALID_BODY.replace(
                "def _validate_response_structure(response):\n",
                "def _validate_response_structure(response):\n"
                "    \"\"\"status_code・text・headers・json は読んではならない。\"\"\"\n",
            ),
        "W-5 内部 Enum 参照（R外・許容対照）":
            _with_extra_line("_e = R.INVALID_RESPONSE_STRUCTURE"),
    }
    for _label, _src in _NEGATIVE_CASES.items():
        _res = scan_snippet(_src)
        check_true(
            f"NOVALPARSE-NEGATIVE[{_label}]. 正当な形が違反にならない（過剰検出でない）",
            _res is not None and len(_res[4]) == 0 and len(_res[2]) == 2 and _res[3] == 2,
        )
    print()

    # =====================================================================
    # CHAIN: exception chaining（新2経路 × 2 = 4 assertion）
    # =====================================================================

    print("[CHAIN] exception chaining（raise ... from None の維持）")

    for _cid, _exc in (("GENERIC-EXCEPTION", _unk_generic_exc),
                       ("RESP-STRUCTURE", _resp_first_exc)):
        check(f"CHAIN-{_cid}-CAUSE. __cause__ が None である",
              getattr(_exc, "__cause__", "NOT-RAISED"), None)
        check(f"CHAIN-{_cid}-CONTEXT. __context__ が None である",
              getattr(_exc, "__context__", "NOT-RAISED"), None)
    print()

    # =====================================================================
    # MSG: message 定数集合の不変・secret 非露出（4 assertion）
    # =====================================================================

    print("[MSG] message 凍結と secret 非露出")

    _msg_consts = {}
    for _node in ast.walk(_openai_tree):
        if (isinstance(_node, ast.Assign) and len(_node.targets) == 1
                and isinstance(_node.targets[0], ast.Name)
                and _node.targets[0].id.startswith("_MSG_")
                and isinstance(_node.value, ast.Constant)):
            _msg_consts[_node.targets[0].id] = _node.value.value
    check(
        "MSG-CONSTANT-SET. module の _MSG_ 定数4件が v6.23.0 時点の文字列と完全一致する",
        _msg_consts,
        {
            "_MSG_UNEXPECTED_ERROR": MSG_UNEXPECTED,
            "_MSG_INVALID_RESPONSE_STRUCTURE": MSG_RESP_STRUCTURE,
            "_MSG_INVALID_BASE64": MSG_B64_INVALID,
            "_MSG_EMPTY_DECODE_RESULT": MSG_B64_EMPTY,
        },
    )
    _msg_prompt_gen = make_error_generator(RuntimeError("boom"))
    _, _msg_prompt_exc = invoke(
        lambda: _msg_prompt_gen.generate("この中にprompt-secret-markerを含む通常の文章")
    )
    check_not_contains("MSG-PROMPT-NOT-LEAKED. prompt が例外へ非露出",
                       f"{_msg_prompt_exc!s}{_msg_prompt_exc!r}", "prompt-secret-marker")
    _msg_key_gen = OpenAIImageGenerator(
        api_key="api-key-secret-marker", client=_FakeClient(error=RuntimeError("boom"))
    )
    _, _msg_key_exc = invoke(lambda: _msg_key_gen.generate("正常なprompt"))
    check_not_contains("MSG-APIKEY-NOT-LEAKED. api_key が例外へ非露出",
                       f"{_msg_key_exc!s}{_msg_key_exc!r}", "api-key-secret-marker")
    _msg_b64_gen = make_resp_generator(make_normal_response(b64_json="b64-secret-marker!!!"))
    _, _msg_b64_exc = invoke(lambda: _msg_b64_gen.generate("正常なprompt"))
    check_not_contains("MSG-B64-NOT-LEAKED. Base64 文字列が例外へ非露出",
                       f"{_msg_b64_exc!s}{_msg_b64_exc!r}", "b64-secret-marker")
    print()

    # =====================================================================
    # SIG: _validate_response_structure の signature／3要素返却形（3 assertion）
    # =====================================================================

    print("[SIG] _validate_response_structure の契約不変（Z-6・AC-26）")

    check(
        "SIG-VALIDATE-PARAMS. parameter が (response) の1件のままである",
        [a.arg for a in (list(_validate_node.args.posonlyargs) + list(_validate_node.args.args))],
        ["response"],
    )
    _validate_returns = [n for n in ast.walk(_validate_node) if isinstance(n, ast.Return)]
    check(
        "SIG-VALIDATE-RETURN-3. すべての return が3要素 Tuple である（3件・3要素返却形の維持）",
        sorted(len(n.value.elts) if isinstance(n.value, ast.Tuple) else -1
               for n in _validate_returns),
        [3, 3, 3],
    )
    _normal_return = [n for n in _validate_returns
                      if isinstance(n.value, ast.Tuple)
                      and isinstance(n.value.elts[0], ast.Constant)
                      and n.value.elts[0].value is None]
    check_true(
        "SIG-VALIDATE-NORMAL-RETURN. 正常時 return が (None, None, b64_json) の形のままである",
        len(_normal_return) == 1
        and isinstance(_normal_return[0].value.elts[1], ast.Constant)
        and _normal_return[0].value.elts[1].value is None
        and isinstance(_normal_return[0].value.elts[2], ast.Name),
    )
    print()

    # =====================================================================
    # DEP: 依存 guard（3 assertion）
    # =====================================================================

    print("[DEP] 依存 guard")

    check_true(
        "DEP-OPENAI-MODULE. openai_image_generator.py の import root が許可集合の部分集合である",
        get_import_roots(OPENAI_MODULE_FILE) <= {"base64", "binascii", "os", "enum",
                                                 "ai_image_generation", "openai"},
    )
    check(
        "DEP-POLICY-MODULE. policy module の import root が許可集合と完全一致する",
        get_import_roots(POLICY_MODULE_FILE),
        {"__future__", "dataclasses", "enum", "openai_image_generation", "wordpress_media"},
    )
    check(
        "DEP-POLICY-NO-NEW-IMPORT. policy module の import root が v6.19 時点の5 root から"
        "増えていない",
        len(get_import_roots(POLICY_MODULE_FILE)),
        5,
    )
    print()

    # =====================================================================
    # COMPATAPI: 周辺 Public API 不変（13 assertion）
    # =====================================================================

    print("[COMPATAPI] 周辺 Public API 不変")

    check(
        "COMPATAPI-OPENAI-ALL. openai_image_generation.__all__ が3 symbol のまま不変である",
        sorted(_v611_pkg.__all__),
        sorted(["OpenAIImageGenerator", "OpenAIImageGenerationError",
                "OpenAIImageGenerationErrorReason"]),
    )
    _err_sig = inspect.signature(OpenAIImageGenerationError.__init__)
    check(
        "COMPATAPI-OPENAI-ERROR-SIG-PARAMS. __init__ の parameter 名が不変である",
        list(_err_sig.parameters.keys()),
        ["self", "message", "reason"],
    )
    check_true(
        "COMPATAPI-OPENAI-ERROR-SIG-NO-DEFAULT. reason が既定値を持たない必須引数のままである",
        _err_sig.parameters["reason"].default is inspect.Parameter.empty,
    )
    check_true("COMPATAPI-OPENAI-ERROR-BASE. 基底が RuntimeError のまま不変である",
               issubclass(OpenAIImageGenerationError, RuntimeError))
    check(
        "COMPATAPI-POLICY-ALL. image_generation_fallback_policy.__all__ が4 symbol のまま不変である",
        sorted(_policy_pkg.__all__),
        sorted(["ImageGenerationFailureCategory", "ImageGenerationFallbackAction",
                "ImageGenerationFallbackDecision", "decide_image_generation_fallback"]),
    )
    check(
        "COMPATAPI-POLICY-SIG. decide_image_generation_fallback の signature が (error) のままである",
        list(inspect.signature(decide_image_generation_fallback).parameters.keys()),
        ["error"],
    )
    check("COMPATAPI-CATEGORY-5. ImageGenerationFailureCategory が5値のまま不変である",
          len(list(CAT)), 5)
    check("COMPATAPI-ACTION-2. ImageGenerationFallbackAction が2値のまま不変である",
          len(list(ACT)), 2)
    check(
        "COMPATAPI-DECISION-FIELDS. ImageGenerationFallbackDecision の field が category のみである",
        [f.name for f in dataclasses.fields(ImageGenerationFallbackDecision)],
        ["category"],
    )
    check("COMPATAPI-WP-REASON-12. WordPressMediaUploadErrorReason が12値のまま不変である",
          len(list(WordPressMediaUploadErrorReason)), 12)
    import wordpress_media as _v69_pkg
    check(
        "COMPATAPI-WP-ALL. wordpress_media.__all__ が4 symbol のまま不変である",
        sorted(_v69_pkg.__all__),
        sorted(["MediaUploadResult", "WordPressMediaUploadError",
                "WordPressMediaUploadErrorReason", "WordPressMediaUploader"]),
    )
    check("COMPATAPI-RUNTIME-STATUS-3. ArticleFeaturedMediaRuntimeStatus が3値のまま不変である",
          len(list(ArticleFeaturedMediaRuntimeStatus)), 3)
    check(
        "COMPATAPI-GENERATOR-MEMBERS. OpenAIImageGenerator の public member が不変である",
        sorted(n for n in vars(OpenAIImageGenerator) if not n.startswith("_")),
        sorted(["from_env", "generate", "output_mime_type"]),
    )
    print()

    # =====================================================================
    # NOIMPACT: Runtime Zero Diff（baseline 固定 guard・98 assertion）
    # =====================================================================

    print("[NOIMPACT] Runtime Zero Diff（baseline 固定 guard）")

    _rc_rev, _ = git_out(["rev-parse", "--verify", f"{BASELINE_COMMIT}^{{commit}}"])
    check_true("NOIMPACT-BASELINE-RESOLVABLE. baseline commit が解決できる（vacuous pass 防止）",
               _rc_rev == 0)

    # v6.21.0／v6.22.0／v6.23.0 と同一の22パス（GR-1：保護対象を削除しない）
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

    # ── Production source allow-list（設計書10.1節・11.5節・GR-4：1ファイルのみ）──
    # test change allow-list とは別変数として分離する（A-7）。混在させてはならない。
    _allowed_source_changes = {
        "src/openai_image_generation": frozenset({
            "src/openai_image_generation/openai_image_generator.py",
        }),
    }

    for _rel in _protected_paths:
        check_true(f"NOIMPACT-EXISTS[{_rel}]. 検査対象が作業ツリーに実在する",
                   (PROJECT_ROOT / _rel).exists())
        _rc_ls, _ls_out = git_out(["ls-tree", "-r", "--name-only", BASELINE_COMMIT, "--", _rel])
        check_true(f"NOIMPACT-BASELINE-TRACKED[{_rel}]. baseline に追跡ファイルが存在する",
                   _rc_ls == 0 and bool(_ls_out.strip()))
        _, _diff_out = git_out(
            ["diff", "--name-only", "--relative", BASELINE_COMMIT, "--", _rel]
        )
        _changed = {line.strip() for line in _diff_out.splitlines() if line.strip()}
        check(f"NOIMPACT-SCOPE[{_rel}]. baseline からの差分が allow-list の範囲内である",
              sorted(_changed - _allowed_source_changes.get(_rel, frozenset())), [])
        _, _status_out = git_out(
            ["status", "--porcelain", "--untracked-files=all", "--", _rel]
        )
        check(f"NOIMPACT-NO-UNTRACKED[{_rel}]. untracked 集合が空である",
              [line for line in _status_out.splitlines() if line.startswith("??")], [])

    # coverage / equality（GR-6：新Release側は equality で検証する）
    for _rel, _allowed_set in _allowed_source_changes.items():
        _, _diff_out = git_out(
            ["diff", "--name-only", "--relative", BASELINE_COMMIT, "--", _rel]
        )
        _changed = {line.strip() for line in _diff_out.splitlines() if line.strip()}
        check(f"NOIMPACT-SCOPE-COVERAGE[{_rel}]. allow-list のファイルが実際に変更されている",
              sorted(_allowed_set - _changed), [])
    for _rel, _allowed_set in _allowed_source_changes.items():
        _, _diff_out = git_out(
            ["diff", "--name-only", "--relative", BASELINE_COMMIT, "--", _rel]
        )
        _changed = {line.strip() for line in _diff_out.splitlines() if line.strip()}
        check_true(f"NOIMPACT-SCOPE-EXACT[{_rel}]. containment と coverage の両方が成立し "
                   "equality となる", _changed == set(_allowed_set))

    # ── test change allow-list（source allow-list とは別変数。A-7）──
    _allowed_test_changes = {
        "test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py",
        "test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py",
        "test_e2e_v6_21_0_article_featured_media_runtime_wiring.py",
        "test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py",
        "test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py",
        "test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_refinement_foundation.py",
    }
    _, _tests_diff_out = git_out(["diff", "--name-only", BASELINE_COMMIT, "--", "tests"])
    _changed_tests = {
        Path(line.strip().replace("\\", "/")).name
        for line in _tests_diff_out.splitlines() if line.strip()
    }
    check("NOIMPACT-TESTS-SCOPE. tests/ の差分が allow-list の範囲内である"
          "（GR-7 に従い許容件数はラベルへ埋め込まない）",
          sorted(_changed_tests - _allowed_test_changes), [])
    _, _tests_status_out = git_out(
        ["status", "--porcelain", "--untracked-files=all", "--", "tests"]
    )
    _untracked_tests = {
        Path(line[3:]).name for line in _tests_status_out.splitlines()
        if line.startswith("??")
    }
    check("NOIMPACT-NO-UNTRACKED-TESTS. tests/ の untracked が allow-list の範囲内である",
          sorted(_untracked_tests - _allowed_test_changes), [])

    # ── 陽性対照（実 _changed／実 allow-list 値ベース。DEF-6.23-12 と同型の設計）──
    _pc_rel = "src/openai_image_generation"
    _, _pc_diff_out = git_out(
        ["diff", "--name-only", "--relative", BASELINE_COMMIT, "--", _pc_rel]
    )
    _changed_actual = {line.strip() for line in _pc_diff_out.splitlines() if line.strip()}
    _allowed_actual = frozenset(_allowed_source_changes[_pc_rel])
    _DUMMY = "src/openai_image_generation/__positive_control_never_exists__.py"
    _snapshot_before = {k: frozenset(v) for k, v in _allowed_source_changes.items()}

    check_true(
        "NOIMPACT-POSITIVE-PRECOND-CHANGED-NONEMPTY. 実差分が非空である"
        "（以降の陽性対照が vacuous でないことの前提）",
        len(_changed_actual) > 0,
    )
    check_false(
        "NOIMPACT-POSITIVE-PRECOND-DUMMY-ABSENT. ダミー path が実差分に含まれない",
        _DUMMY in _changed_actual,
    )
    check_true(
        "NOIMPACT-POSITIVE-EMPTY-ALLOWLIST. allow-list を空にすると実差分に対し containment 検査が"
        "違反を検出する",
        len(_changed_actual - frozenset()) > 0,
    )
    check_true(
        "NOIMPACT-POSITIVE-UNCHANGED-ALLOWLIST. 実 allow-list へ未変更 path を加えると "
        "coverage 検査が検出する",
        len((_allowed_actual | {_DUMMY}) - _changed_actual) > 0,
    )
    check(
        "NOIMPACT-POSITIVE-NONDESTRUCTIVE. 陽性対照が _allowed_source_changes を破壊的に変更しない",
        {k: frozenset(v) for k, v in _allowed_source_changes.items()},
        _snapshot_before,
    )
    print()

    # =====================================================================
    # SOCKET: 実通信0件（3 assertion）
    # =====================================================================

    print("[SOCKET] 実通信0件")

    _, _gai_exc = invoke(lambda: socket.getaddrinfo("example.invalid", 443))
    check_true("SOCKET-GETADDRINFO-BLOCKED. socket.getaddrinfo が遮断されている",
               isinstance(_gai_exc, _NetworkBlocked))
    _, _conn_exc = invoke(lambda: socket.socket().connect(("127.0.0.1", 9)))
    check_true("SOCKET-CONNECT-BLOCKED. socket.socket.connect が遮断されている",
               isinstance(_conn_exc, _NetworkBlocked))
    check("SOCKET-NO-REAL-CLIENT. 実 openai.OpenAI の構築が0件である",
          _real_client_construction_count["n"], 0)
    print()

    # =====================================================================
    # ENV: 環境変数の非汚染（2 assertion）
    # =====================================================================

    print("[ENV] environment isolation")

    _restore_env()
    check("ENV-ISOLATION-RESTORED. 監視対象の環境変数が開始時の状態へ復元される",
          {key: os.environ.get(key) for key in _ENV_KEYS}, _SAVED_ENV)
    check("ENV-FULL-ENVIRON-UNCHANGED. os.environ 全体が開始時のスナップショットと一致する",
          dict(os.environ), _SAVED_ENVIRON_SNAPSHOT)
    print()

finally:
    socket.getaddrinfo = _ORIG_GETADDRINFO
    socket.socket.connect = _ORIG_CONNECT
    try:
        openai.OpenAI = _ORIG_OPENAI_CLIENT
    except NameError:
        pass
    _restore_env()

# ─── 結果サマリー ───
print("=" * 70)
total = len(results_log)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = total - passed
print("Release：v6.24.0")
print("正式名称：OpenAI Image Generation Unknown and Invalid Response Reason Refinement Foundation")
print(f"Assertion合計：{total}（設計書12.6.2節の見込み値：346）")
print(f"合計: {passed}/{total} PASS  /  {failed} FAIL")
print("=" * 70)

if failed > 0:
    print()
    print("FAILしたテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
