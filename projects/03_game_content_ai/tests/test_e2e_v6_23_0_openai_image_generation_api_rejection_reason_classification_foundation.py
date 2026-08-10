"""
E2E テスト: v6.23.0 OpenAI Image Generation API Rejection Reason Classification Foundation

Source of Truth:
    docs/design/openai_image_generation_api_rejection_reason_classification_foundation.md
    （Architecture Review：Approved with Findings／Test Review：Changes Required →
      Findings 反映済み。承認済み設計書）

DI-11 前半：v6.11 の REQUEST_REJECTED を、SDK 例外型のみを根拠として4値へ細分化する。
REQUEST_REJECTED は削除せず後方互換のため保持する。

本テストは実HTTP・実課金を一切発生させない。socket を遮断し、openai.OpenAI を
Runtime Guard で patch して無許可の実Client構築を検出する。

Assertion 構成（設計書12.8.2節・見込み332）:
    API-              23    Enum 13値の shape・value・定義順・__all__
    COMPAT-REJECTED-   7    REQUEST_REJECTED の存続と外部構築時の契約
    CLS-              28    _classify_api_error の型判定（14ケース × 2）
    ORDER-            11    SDK 例外階層と判定順序 contract
    E2E-              16    generate() 経由の end-to-end（4型 × 4）
    MSG-               2    message 凍結
    CHAIN-             8    exception chaining（4型 × 2）
    POLICY-           30    fallback policy の全数写像（13値）
    REJECTSET-         6    _REJECTED_REASONS の完全一致 allow-list
    CONT-              9    CONTINUE 集合の非拡大
    ZERODIFF-         27    v6.22.0 時点との action／category 一致
    RUNTIME-           8    Runtime 層の PROPAGATE／CONTINUE 不変
    NOPARSE-          26    例外引数使用形の positive allow-list guard
    SEC-              10    secret 非露出・固定ラベル
    DEP-               3    依存 guard
    NOEXC-             3    policy module の構造不変
    COMPAT-           13    周辺 Public API 不変
    NOIMPACT-         97    Runtime Zero Diff（baseline 固定 guard）
    SOCKET-            3    実通信0件
    ENV-               2    環境変数の非汚染
    ────────────────────────
    合計              332

数え方（設計書12.8.1節 R-a〜R-e）:
    1 assertion = results_log への1 append = check() の1回呼び出し。
    反復回数と assertion 数は一致しない場合がある（12.8.3節）。

実行方法:
    cd projects/03_game_content_ai
    .\\venv\\Scripts\\python.exe tests\\test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py
"""
import ast
import dataclasses
import inspect
import itertools
import os
import socket
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ─── テスト用ユーティリティ（v6.19.0／v6.22.0 precedent を踏襲） ───

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

    from article_featured_media_runtime import (
        ArticleFeaturedMediaRuntime,
        ArticleFeaturedMediaRuntimeStatus,
    )
    from ai_image_generation import GeneratedImage
    from collector import NewsItem
    from outputs import ArticleData
    from publishing_config import PublishStatus
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

    # 凍結 message（v6.22.0 時点の文字列。1文字も変更してはならない）
    MSG_REJECTED = "OpenAI APIへのリクエストが不正です（Content Policy等による生成拒否を含む）"
    MSG_AUTH = "OpenAI APIへの認証に失敗しました"
    MSG_PERM = "OpenAI APIへのアクセス権限がありません（Organization Verification等の可能性）"
    MSG_RATE = "OpenAI APIのレート制限に達しました"
    MSG_TIMEOUT = "OpenAI APIへのリクエストがタイムアウトしました"
    MSG_CONN = "OpenAI APIへの接続に失敗しました"
    MSG_SERVER = "OpenAI API側でエラーが発生しました"
    MSG_CATCHALL = "OpenAI Images APIの呼び出しに失敗しました"

    # ─── Fake provider 例外の構築（実通信なし） ───

    SECRET_MARKER = "provider-secret-marker-0xC0FFEE"

    def make_request():
        return httpx.Request("POST", "https://example.invalid/v1/images/generations")

    def make_response(status_code: int):
        return httpx.Response(
            status_code,
            request=make_request(),
            json={"error": {"message": SECRET_MARKER, "code": SECRET_MARKER}},
        )

    def make_status_error(error_type, status_code: int):
        return error_type(
            SECRET_MARKER,
            response=make_response(status_code),
            body={"error": {"message": SECRET_MARKER}},
        )

    def make_timeout_error():
        return openai.APITimeoutError(make_request())

    def make_connection_error():
        return openai.APIConnectionError(message=SECRET_MARKER, request=make_request())

    def make_generic_api_error():
        return openai.APIError(SECRET_MARKER, make_request(), body=None)

    def make_response_validation_error():
        return openai.APIResponseValidationError(response=make_response(200), body=None)

    # ─── Fake OpenAI client（generate() 経由の E2E 用） ───

    class _FakeImages:
        def __init__(self, error):
            self._error = error

        def generate(self, **kwargs):
            raise self._error

    class _FakeClient:
        def __init__(self, error):
            self.images = _FakeImages(error)

        def with_options(self, **kwargs):
            return self

    def make_error_generator(error):
        return OpenAIImageGenerator(api_key="test-key", client=_FakeClient(error))

    # ─── Runtime 用 Fake ───

    def make_news_item():
        return NewsItem(
            title="PS6正式発表",
            url="https://blog.playstation.com/test",
            summary="PlayStation 6 が正式に発表されました。",
            source="PlayStation Blog",
            published_at="2026-07-18",
            image_candidates=[],
        )

    def make_article():
        return ArticleData(
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

    class FakeOrchestrator:
        def __init__(self, *, error):
            self._error = error

        def apply(self, article, prompt, filename):
            raise self._error

    class FakeCompositionRoot:
        def __init__(self, *, orchestrator, image_mime_type="image/png", available=True):
            self.orchestrator = orchestrator
            self.image_mime_type = image_mime_type
            self._available = available

        def is_available(self):
            return self._available

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

    # ─── NOPARSE guard 本体（設計書7.8.2節 I-EXC-1・12.6.1節） ───

    def exception_param_name(func_node):
        """例外引数名を AST から決定する（ハードコードしない）。"""
        args = func_node.args
        positional = list(args.posonlyargs) + list(args.args)
        return positional[0].arg if positional else None

    def _parent_map(func_node):
        parents = {}
        for parent in ast.walk(func_node):
            for child in ast.iter_child_nodes(parent):
                parents[child] = parent
        return parents

    def _is_allowed_occurrence(node, parent):
        """許可される唯一の形：isinstance(<exc>, ...) の第1引数。"""
        if not isinstance(parent, ast.Call):
            return False
        if not isinstance(parent.func, ast.Name):
            return False
        if parent.func.id != "isinstance":
            return False
        if not parent.args:
            return False
        return parent.args[0] is node

    def scan_exc_usage(func_node):
        """戻り値: (出現総数, allow 形の数, 違反リスト)"""
        param = exception_param_name(func_node)
        if param is None:
            return (0, 0, ["<no positional parameter>"])
        parents = _parent_map(func_node)
        total = 0
        allowed = 0
        violations = []
        for node in ast.walk(func_node):
            if not isinstance(node, ast.Name) or node.id != param:
                continue
            total += 1
            parent = parents.get(node)
            if _is_allowed_occurrence(node, parent):
                allowed += 1
            else:
                violations.append(
                    f"L{node.lineno}:{param} used in {type(parent).__name__ if parent else 'None'}"
                )
        return (total, allowed, violations)

    def scan_source_snippet(src: str, func_name: str = "_classify_api_error"):
        node = find_function(ast.parse(src), func_name)
        return scan_exc_usage(node) if node is not None else None

    print("=" * 70)
    print("v6.23.0 OpenAI Image Generation API Rejection Reason Classification Foundation")
    print("=" * 70)
    print()

    # =====================================================================
    # API: Enum 13値の shape（23 assertion）
    # =====================================================================

    print("[API] Enum 13値の Public API")

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
        # v6.24.0（DI-11後半）で末尾へ追加された2値。本Release（v6.23.0）の関心は
        # 上記13値であるが、Enum 全数を対象とする検査は15値へ追随する必要がある
        # （v6.19.0 と同型の、期待表駆動テストの構造的追随）。
        ("UNEXPECTED_EXCEPTION", "unexpected_exception"),
        ("INVALID_RESPONSE_STRUCTURE", "invalid_response_structure"),
    ]
    _NEW_NAMES = ["BAD_REQUEST", "RESOURCE_NOT_FOUND", "CONFLICT", "UNPROCESSABLE_ENTITY"]
    _ALL_REASONS = list(R)

    check("API-COUNT-13. Enum member が15値である（v6.24.0 で13→15）", len(_ALL_REASONS), 15)
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
    check(
        "API-VALUE-UNIQUE. value に重複がない",
        len({r.value for r in _ALL_REASONS}),
        15,
    )
    for _name, _value in _EXPECTED_NAME_VALUE:
        check(f"API-VALUE[{_name}]. value が {_value} である", getattr(R, _name).value, _value)
    check(
        "API-DEFINITION-ORDER. 定義順が既存9値（v6.22.0 時点の順序）＋v6.23.0 の新4値"
        "＋v6.24.0 の新2値の順である",
        [r.name for r in _ALL_REASONS],
        [n for n, _ in _EXPECTED_NAME_VALUE],
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
    # CLS: _classify_api_error の型判定（14ケース × 2 = 28 assertion）
    # =====================================================================

    print("[CLS] _classify_api_error の型判定（14ケース）")

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
        # catch-all 経路（M-1 対応）。#11 は status_code が 400 でも
        # BadRequestError ではないため BAD_REQUEST にならない＝型のみ判定の証明。
        ("STATUS-400-NOT-BADREQ", make_status_error(openai.APIStatusError, 400), R.UNKNOWN, MSG_CATCHALL),
        ("STATUS-500-NOT-SERVER", make_status_error(openai.APIStatusError, 500), R.UNKNOWN, MSG_CATCHALL),
        ("BARE-APIERROR", make_generic_api_error(), R.UNKNOWN, MSG_CATCHALL),
        ("RESP-VALIDATION", make_response_validation_error(), R.UNKNOWN, MSG_CATCHALL),
    ]

    _cls_results = []
    for _cid, _exc, _expected_reason, _expected_msg in _CLS_CASES:
        _msg, _reason = _classify_api_error(_exc)
        _cls_results.append(_reason)
        check(f"CLS-{_cid}. reason が {_expected_reason.name} である", _reason, _expected_reason)
        check(f"CLS-{_cid}-MSG. message が凍結文字列と完全一致する", _msg, _expected_msg)
    print()

    # =====================================================================
    # COMPAT-REJECTED: REQUEST_REJECTED の存続と外部構築契約（7 assertion）
    # =====================================================================

    print("[COMPAT-REJECTED] REQUEST_REJECTED の後方互換")

    check_true("COMPAT-REJECTED-EXISTS. Enum member として存続している",
               hasattr(R, "REQUEST_REJECTED"))
    check("COMPAT-REJECTED-VALUE. value が request_rejected のまま不変である",
          R.REQUEST_REJECTED.value, "request_rejected")
    check_true("COMPAT-REJECTED-VALUE-LOOKUP. value からの逆引きが従来どおり成立する",
               R("request_rejected") is R.REQUEST_REJECTED)
    _rej_decision = decide_image_generation_fallback(
        OpenAIImageGenerationError("外部から構築", R.REQUEST_REJECTED)
    )
    check("COMPAT-REJECTED-CATEGORY. 外部構築時も IMAGE_GENERATION_REQUEST_REJECTED へ写像される",
          _rej_decision.category, CAT.IMAGE_GENERATION_REQUEST_REJECTED)
    check("COMPAT-REJECTED-ACTION. 外部構築時も PROPAGATE_ORIGINAL_ERROR となる",
          _rej_decision.action, ACT.PROPAGATE_ORIGINAL_ERROR)
    _rej_variants = [
        decide_image_generation_fallback(OpenAIImageGenerationError(_m, R.REQUEST_REJECTED))
        for _m in [MSG_REJECTED, "model 'x' does not exist", "", "HTTP 404 model_not_found"]
    ]
    check_true(
        "COMPAT-REJECTED-MESSAGE-INDEPENDENT. 全 message バリエーションで結果が同一である",
        all(_d == _rej_variants[0] for _d in _rej_variants),
    )
    check(
        "COMPAT-REJECTED-NOT-PRODUCED. production の分類経路14ケースが "
        "REQUEST_REJECTED を1件も生成しない",
        [c for c in _cls_results if c is R.REQUEST_REJECTED],
        [],
    )
    print()

    # =====================================================================
    # ORDER: SDK 例外階層と判定順序 contract（11 assertion）
    # =====================================================================

    print("[ORDER] SDK 例外階層・判定順序 contract")

    _FOUR = [openai.BadRequestError, openai.NotFoundError,
             openai.ConflictError, openai.UnprocessableEntityError]
    _PRIOR = [openai.AuthenticationError, openai.PermissionDeniedError,
              openai.RateLimitError, openai.APITimeoutError,
              openai.APIConnectionError, openai.InternalServerError]

    check_true(
        "ORDER-TIMEOUT-IS-CONNECTION-SUBCLASS. APITimeoutError が APIConnectionError の "
        "subclass である（判定順序が必要である根拠。H-4）",
        issubclass(openai.APITimeoutError, openai.APIConnectionError),
    )
    check(
        "ORDER-TIMEOUT-BEFORE-CONNECTION. APITimeoutError が TIMEOUT へ分類される"
        "（CONNECTION へ吸われない。O-1）",
        _classify_api_error(make_timeout_error())[1],
        R.TIMEOUT,
    )
    for _cls in _FOUR:
        check(
            f"ORDER-DIRECT-BASE[{_cls.__name__}]. APIStatusError の直接 subclass である",
            tuple(b.__name__ for b in _cls.__bases__),
            ("APIStatusError",),
        )
    check(
        "ORDER-MUTUAL-INDEPENDENT. 対象4型の相互 issubclass 行列が単位行列である（H-1）",
        [[issubclass(a, b) for b in _FOUR] for a in _FOUR],
        [[i == j for j in range(4)] for i in range(4)],
    )
    check(
        "ORDER-NOT-SUBCLASS-OF-PRIOR. 対象4型が先行判定6型のいずれの subclass でもない（H-2）",
        sorted(f"{a.__name__}<{b.__name__}" for a in _FOUR for b in _PRIOR if issubclass(a, b)),
        [],
    )
    check(
        "ORDER-PRIOR-NOT-SUBCLASS-OF-FOUR. 先行判定6型が対象4型のいずれの subclass でもない（H-3）",
        sorted(f"{b.__name__}<{a.__name__}" for b in _PRIOR for a in _FOUR if issubclass(b, a)),
        [],
    )
    _perm_expected = {
        openai.BadRequestError: R.BAD_REQUEST,
        openai.NotFoundError: R.RESOURCE_NOT_FOUND,
        openai.ConflictError: R.CONFLICT,
        openai.UnprocessableEntityError: R.UNPROCESSABLE_ENTITY,
    }
    _perm_mismatch = []
    for _order in itertools.permutations(_FOUR):          # 24 反復 → 1 assertion（R-e）
        for _cls in _order:
            _status = {openai.BadRequestError: 400, openai.NotFoundError: 404,
                       openai.ConflictError: 409, openai.UnprocessableEntityError: 422}[_cls]
            if _classify_api_error(make_status_error(_cls, _status))[1] is not _perm_expected[_cls]:
                _perm_mismatch.append(_cls.__name__)
    check(
        "ORDER-FOUR-PERMUTATION-STABLE. 対象4型を全24順列で評価しても分類結果が同一である"
        "（24反復 → 1 assertion。O-2）",
        sorted(set(_perm_mismatch)),
        [],
    )
    check(
        "ORDER-SERVER-ERROR-STABLE. InternalServerError が SERVER_ERROR のまま不変である（O-4）",
        _classify_api_error(make_status_error(openai.InternalServerError, 503))[1],
        R.SERVER_ERROR,
    )
    print()

    # =====================================================================
    # E2E: generate() 経由の end-to-end（4型 × 4 = 16 assertion）
    # =====================================================================

    print("[E2E] generate() 経由の end-to-end")

    _E2E_CASES = [
        ("BADREQ", openai.BadRequestError, 400, R.BAD_REQUEST),
        ("NOTFOUND", openai.NotFoundError, 404, R.RESOURCE_NOT_FOUND),
        ("CONFLICT", openai.ConflictError, 409, R.CONFLICT),
        ("UNPROCESSABLE", openai.UnprocessableEntityError, 422, R.UNPROCESSABLE_ENTITY),
    ]
    _e2e_excs = {}
    for _cid, _cls, _status, _expected_reason in _E2E_CASES:
        _gen = make_error_generator(make_status_error(_cls, _status))
        _result, _raised = invoke(lambda g=_gen: g.generate("正常なprompt"))
        _e2e_excs[_cid] = _raised
        check_true(f"E2E-{_cid}-TYPE. OpenAIImageGenerationError が送出される",
                   isinstance(_raised, OpenAIImageGenerationError))
        check(f"E2E-{_cid}-REASON. reason が {_expected_reason.name} である",
              getattr(_raised, "reason", None), _expected_reason)
        check(f"E2E-{_cid}-MSG. message が凍結文字列と完全一致する",
              str(_raised) if _raised else None, MSG_REJECTED)
        check_not_contains(
            f"E2E-{_cid}-NO-SECRET. provider 由来の secret marker が露出しない",
            "|".join([str(_raised), repr(_raised), str(getattr(_raised, "args", ())),
                      repr(getattr(_raised, "__dict__", {}))]),
            SECRET_MARKER,
        )
    print()

    # =====================================================================
    # MSG: message 凍結（2 assertion）
    # =====================================================================

    print("[MSG] message 凍結")

    check(
        "MSG-FOUR-IDENTICAL. 対象4型の message が相互に完全同一である",
        {_classify_api_error(make_status_error(_cls, _st))[0]
         for _cls, _st in [(openai.BadRequestError, 400), (openai.NotFoundError, 404),
                           (openai.ConflictError, 409), (openai.UnprocessableEntityError, 422)]},
        {MSG_REJECTED},
    )
    check(
        "MSG-CONSTANT-SET. 分類経路14ケースが返す message 集合が v6.22.0 時点の集合と一致する",
        sorted({_classify_api_error(_exc)[0] for _, _exc, _, _ in _CLS_CASES}),
        sorted({MSG_AUTH, MSG_PERM, MSG_RATE, MSG_TIMEOUT, MSG_CONN,
                MSG_REJECTED, MSG_SERVER, MSG_CATCHALL}),
    )
    print()

    # =====================================================================
    # CHAIN: exception chaining（4型 × 2 = 8 assertion）
    # =====================================================================

    print("[CHAIN] exception chaining（raise ... from None の維持）")

    for _cid, _, _, _ in _E2E_CASES:
        _exc = _e2e_excs[_cid]
        check(f"CHAIN-{_cid}-CAUSE. __cause__ が None である",
              getattr(_exc, "__cause__", "NOT-RAISED"), None)
        check(f"CHAIN-{_cid}-CONTEXT. __context__ が None である",
              getattr(_exc, "__context__", "NOT-RAISED"), None)
    print()

    # =====================================================================
    # POLICY: fallback policy の全数写像（30 assertion）
    # =====================================================================

    print("[POLICY] fallback policy の全数写像（13値）")

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
        # v6.24.0（DI-11後半）で追加された2値。C-17 の allow-list 性質により
        # policy 無改修のまま UNCLASSIFIED（安全側）へ落ちる。
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
        check(f"POLICY-ACTION[{_reason.name}]. action が写像表と一致する",
              _d.action, _EXPECTED_ACTION[_EXPECTED_CATEGORY[_reason.name]])

    check(
        "POLICY-COVERAGE-13. Enum 全15値が写像表と過不足なく一致する（v6.24.0 で13→15）",
        {r.name for r in _ALL_REASONS},
        set(_EXPECTED_CATEGORY.keys()),
    )
    _split = {}
    for _cat in _actual_category.values():
        _split[_cat] = _split.get(_cat, 0) + 1
    check(
        "POLICY-SPLIT. 実測集計が 4/5/2/4 に分割される"
        "（v6.24.0 で UNCLASSIFIED 側が2→4。"
        "FAILED 側が4のままであることが CONTINUE 非拡大の直接証拠）",
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
    check("POLICY-SPLIT-TOTAL. 実測分類の合計が15件である（v6.24.0 で13→15）",
          sum(_split.values()), 15)
    check(
        "POLICY-NO-STRAY-CATEGORY. 実測 category が既存4種以外へ分類されていない",
        set(_split.keys()),
        {CAT.IMAGE_GENERATION_FAILED, CAT.IMAGE_GENERATION_REQUEST_REJECTED,
         CAT.IMAGE_GENERATION_NOT_AUTHORIZED, CAT.UNCLASSIFIED},
    )
    print()

    # =====================================================================
    # REJECTSET: _REJECTED_REASONS の完全一致 allow-list（6 assertion）
    # =====================================================================

    print("[REJECTSET] _REJECTED_REASONS の完全一致 allow-list")

    check(
        "REJECTSET-EXACT. _REJECTED_REASONS が期待5値と完全一致する",
        _REJECTED_REASONS,
        frozenset({R.REQUEST_REJECTED, R.BAD_REQUEST, R.RESOURCE_NOT_FOUND,
                   R.CONFLICT, R.UNPROCESSABLE_ENTITY}),
    )
    check_true("REJECTSET-IS-FROZENSET. frozenset である（実行時に書き換えられない）",
               isinstance(_REJECTED_REASONS, frozenset))
    check(
        "REJECTSET-DISJOINT. _CONTINUABLE_REASONS と交わらない",
        sorted(r.name for r in (_REJECTED_REASONS & _CONTINUABLE_REASONS)),
        [],
    )
    check(
        "REJECTSET-UNION-COVERAGE. 2つの allow-list の和が9値であり、"
        "残り6値（AUTH／PERM／INVALID_RESPONSE／UNKNOWN／v6.24.0 の新2値）は else 経路である"
        "（allow-list 方式により、後続 Release の新値が自動的に安全側へ落ちることの実証）",
        sorted(r.name for r in (set(_ALL_REASONS) - _REJECTED_REASONS - _CONTINUABLE_REASONS)),
        sorted(["AUTHENTICATION", "PERMISSION_DENIED", "INVALID_RESPONSE", "UNKNOWN",
                "UNEXPECTED_EXCEPTION", "INVALID_RESPONSE_STRUCTURE"]),
    )
    _fake_reason_error = OpenAIImageGenerationError("probe", R.TIMEOUT)
    _fake_reason_error.reason = "bad_request"          # Enum ではない文字列
    check(
        "REJECTSET-ALLOWLIST-SEMANTICS. Enum member でない疑似値は REJECTED へ入らず "
        "UNCLASSIFIED へ落ちる（C-17 の安全側性質を維持）",
        decide_image_generation_fallback(_fake_reason_error).category,
        CAT.UNCLASSIFIED,
    )
    _rejectset_before = frozenset(_REJECTED_REASONS)
    for _reason in _ALL_REASONS:
        decide_image_generation_fallback(OpenAIImageGenerationError("probe", _reason))
    check("REJECTSET-IMMUTABLE. decide() を全15値へ適用した後も内容が不変である",
          frozenset(_REJECTED_REASONS), _rejectset_before)
    print()

    # =====================================================================
    # CONT: CONTINUE 集合の非拡大（9 assertion）
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
            f"CONT-NEW-NONE[{_name}]. v6.23.0 で追加した reason は CONTINUE にならない",
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
    # ZERODIFF: v6.22.0 時点との action／category 一致（27 assertion）
    # =====================================================================

    print("[ZERODIFF] v6.22.0 時点との Runtime action／category Zero Diff")

    _V622_EXPECTED = {
        "AUTHENTICATION": (CAT.IMAGE_GENERATION_NOT_AUTHORIZED, ACT.PROPAGATE_ORIGINAL_ERROR),
        "PERMISSION_DENIED": (CAT.IMAGE_GENERATION_NOT_AUTHORIZED, ACT.PROPAGATE_ORIGINAL_ERROR),
        "RATE_LIMIT": (CAT.IMAGE_GENERATION_FAILED, ACT.CONTINUE_WITHOUT_FEATURED_MEDIA),
        "TIMEOUT": (CAT.IMAGE_GENERATION_FAILED, ACT.CONTINUE_WITHOUT_FEATURED_MEDIA),
        "CONNECTION": (CAT.IMAGE_GENERATION_FAILED, ACT.CONTINUE_WITHOUT_FEATURED_MEDIA),
        "REQUEST_REJECTED": (CAT.IMAGE_GENERATION_REQUEST_REJECTED, ACT.PROPAGATE_ORIGINAL_ERROR),
        "SERVER_ERROR": (CAT.IMAGE_GENERATION_FAILED, ACT.CONTINUE_WITHOUT_FEATURED_MEDIA),
        "INVALID_RESPONSE": (CAT.UNCLASSIFIED, ACT.PROPAGATE_ORIGINAL_ERROR),
        "UNKNOWN": (CAT.UNCLASSIFIED, ACT.PROPAGATE_ORIGINAL_ERROR),
    }
    for _name, (_exp_cat, _exp_act) in _V622_EXPECTED.items():
        _d = decide_image_generation_fallback(
            OpenAIImageGenerationError("probe", getattr(R, _name))
        )
        check(f"ZERODIFF-CATEGORY-V622[{_name}]. category が v6.22.0 時点と一致する",
              _d.category, _exp_cat)
    for _name, (_exp_cat, _exp_act) in _V622_EXPECTED.items():
        _d = decide_image_generation_fallback(
            OpenAIImageGenerationError("probe", getattr(R, _name))
        )
        check(f"ZERODIFF-ACTION-V622[{_name}]. action が v6.22.0 時点と一致する",
              _d.action, _exp_act)

    # SDK 例外型を起点とした end-to-end。policy を戻すと UNCLASSIFIED へ落ちて FAIL する
    # ＝「Enum のみ追加・policy 未更新」の片側 rollback 検出器（設計書12.9節）。
    for _cid, _cls, _status, _ in _E2E_CASES:
        _gen = make_error_generator(make_status_error(_cls, _status))
        _, _raised = invoke(lambda g=_gen: g.generate("正常なprompt"))
        _d = decide_image_generation_fallback(_raised)
        check(f"ZERODIFF-SDK-CATEGORY[{_cid}]. SDK 例外起点でも category が v6.22.0 時点と一致する",
              _d.category, CAT.IMAGE_GENERATION_REQUEST_REJECTED)
    for _cid, _cls, _status, _ in _E2E_CASES:
        _gen = make_error_generator(make_status_error(_cls, _status))
        _, _raised = invoke(lambda g=_gen: g.generate("正常なprompt"))
        _d = decide_image_generation_fallback(_raised)
        check(f"ZERODIFF-SDK-ACTION[{_cid}]. SDK 例外起点でも action が PROPAGATE のままである",
              _d.action, ACT.PROPAGATE_ORIGINAL_ERROR)
    check(
        "ZERODIFF-PARTIAL-ENUM-ONLY. 新4 reason がすべて _REJECTED_REASONS に含まれる"
        "（Enum のみ追加して policy を更新しない片側実装の検出）",
        sorted(n for n in _NEW_NAMES if getattr(R, n) not in _REJECTED_REASONS),
        [],
    )
    print()

    # =====================================================================
    # RUNTIME: Runtime 層の PROPAGATE／CONTINUE 不変（8 assertion）
    # =====================================================================

    print("[RUNTIME] Runtime 層の Zero Diff")

    for _cid, _, _, _expected_reason in _E2E_CASES:
        _orig = OpenAIImageGenerationError("probe", _expected_reason)
        _runtime = ArticleFeaturedMediaRuntime(
            FakeCompositionRoot(orchestrator=FakeOrchestrator(error=_orig), available=True)
        )
        _res, _raised = invoke(lambda rt=_runtime: rt.apply(make_article()))
        check_true(
            f"RUNTIME-PROPAGATE[{_cid}]. 元例外が無変換で再送出される（同一 object）",
            _raised is _orig,
        )
    for _name in ("TIMEOUT", "CONNECTION", "RATE_LIMIT", "SERVER_ERROR"):
        _runtime = ArticleFeaturedMediaRuntime(
            FakeCompositionRoot(
                orchestrator=FakeOrchestrator(
                    error=OpenAIImageGenerationError("probe", getattr(R, _name))
                ),
                available=True,
            )
        )
        _res, _raised = invoke(lambda rt=_runtime: rt.apply(make_article()))
        check(
            f"RUNTIME-CONTINUE-UNCHANGED[{_name}]. 既存 CONTINUE 4値の status が不変である",
            _res.status if _res else _raised,
            ArticleFeaturedMediaRuntimeStatus.CONTINUED_WITHOUT_FEATURED_MEDIA,
        )
    print()

    # =====================================================================
    # NOPARSE: 例外引数使用形の positive allow-list guard（26 assertion）
    # =====================================================================

    print("[NOPARSE] 例外引数使用形の positive allow-list guard")

    _openai_tree = parse_file(OPENAI_MODULE_FILE)
    _classify_node = find_function(_openai_tree, "_classify_api_error")

    check_true("NOPARSE-FN-FOUND. _classify_api_error の FunctionDef を検出できる",
               _classify_node is not None)
    check("NOPARSE-PARAM-NAME. 例外引数名を AST から決定できる（ハードコードしない）",
          exception_param_name(_classify_node), "exc")

    _total, _allowed, _violations = scan_exc_usage(_classify_node)
    check("NOPARSE-OCCURRENCE-COUNT-10. 例外引数の Name 出現が10件である"
          "（設計書7.3節の10段判定と一致。走査が空振りしていないことの証明）",
          _total, 10)
    check("NOPARSE-ALLOWED-EQUALS-TOTAL. 全出現が allow 形である（allow 数 == 出現総数）",
          _allowed, _total)
    check("NOPARSE-VIOLATIONS-EMPTY. 違反が0件である（I-EXC-1）", _violations, [])

    _generate_node = find_function(_openai_tree, "generate")
    _, _, _generate_violations = scan_exc_usage(_generate_node)
    check_true(
        "NOPARSE-SCOPE-FUNCTION-ONLY. 同じ規則を他関数（generate）へ適用すると違反が出る"
        "＝検査対象を _classify_api_error に限定する必要がある（設計書7.8.4節）",
        len(_generate_violations) > 0,
    )

    _POSITIVE_CASES = {
        "P-1 exc.code": "def _classify_api_error(exc):\n    return exc.code",
        "P-2 exc.request": "def _classify_api_error(exc):\n    return exc.request",
        "P-3 exc.<未知属性>": "def _classify_api_error(exc):\n    return exc.future_unknown_attr_xyz",
        "P-4 exc['code']": "def _classify_api_error(exc):\n    return exc['code']",
        "P-5 getattr(exc, ...)": "def _classify_api_error(exc):\n    return getattr(exc, 'code')",
        "P-6 hasattr(exc, ...)": "def _classify_api_error(exc):\n    return hasattr(exc, 'code')",
        "P-7 str(exc)": "def _classify_api_error(exc):\n    return str(exc)",
        "P-8 repr(exc)": "def _classify_api_error(exc):\n    return repr(exc)",
        "P-9 vars(exc)": "def _classify_api_error(exc):\n    return vars(exc)",
        "P-10 helper(exc)": "def _classify_api_error(exc):\n    return helper(exc)",
        "P-11 return exc": "def _classify_api_error(exc):\n    return exc",
        "P-12 代入": "def _classify_api_error(exc):\n    _x = exc\n    return _x",
        "P-13 collection格納": "def _classify_api_error(exc):\n    return [exc]",
        "P-14 comparison": "def _classify_api_error(exc):\n    return exc == other",
        "P-15 isinstance第2引数": "def _classify_api_error(exc):\n    return isinstance(other, exc)",
        "P-16 f-string": 'def _classify_api_error(exc):\n    return f"{exc}"',
    }
    for _label, _src in _POSITIVE_CASES.items():
        _t, _a, _v = scan_source_snippet(_src)
        check_true(f"NOPARSE-POSITIVE[{_label}]. allow-list 外の使用形が違反として検出される",
                   len(_v) > 0)

    _NEGATIVE_CASES = {
        "N-1 単一型isinstance":
            "def _classify_api_error(exc):\n"
            "    if isinstance(exc, openai.BadRequestError):\n"
            "        return ('m', R.BAD_REQUEST)\n"
            "    return ('u', R.UNKNOWN)",
        "N-2 タプルisinstance":
            "def _classify_api_error(exc):\n"
            "    if isinstance(exc, (openai.BadRequestError, openai.NotFoundError)):\n"
            "        return ('m', R.X)\n"
            "    return ('u', R.UNKNOWN)",
        "N-3 他識別子の属性参照":
            "def _classify_api_error(exc):\n"
            "    import openai\n"
            "    if isinstance(exc, openai.NotFoundError):\n"
            "        return ('m', R.RESOURCE_NOT_FOUND)\n"
            "    return ('u', R.UNKNOWN)",
        "N-4 文字列/docstring内のexc":
            "def _classify_api_error(exc):\n"
            '    """exc を解析してはならない。"""\n'
            "    if isinstance(exc, openai.ConflictError):\n"
            "        return ('exc conflict', R.CONFLICT)\n"
            "    return ('u', R.UNKNOWN)",
    }
    for _label, _src in _NEGATIVE_CASES.items():
        _t, _a, _v = scan_source_snippet(_src)
        check_true(f"NOPARSE-NEGATIVE[{_label}]. 正当な使用形が違反にならない（過剰検出でない）",
                   len(_v) == 0 and _t > 0 and _a == _t)
    print()

    # =====================================================================
    # SEC: secret 非露出・固定ラベル（10 assertion）
    # =====================================================================

    print("[SEC] Security")

    check_true(
        "SEC-VALUE-LABEL-SET. 15値の value が英小文字とアンダースコアのみで構成される"
        "（URL・credential・応答本文を含まない）",
        all(v.replace("_", "").isascii() and v.replace("_", "").islower()
            and v.replace("_", "").isalpha() for v in (r.value for r in _ALL_REASONS)),
    )
    for _cid, _, _, _ in _E2E_CASES:
        _exc = _e2e_excs[_cid]
        check_not_contains(
            f"SEC-NO-SECRET[{_cid}]. secret marker が message・repr・args・__dict__ に露出しない",
            "|".join([str(_exc), repr(_exc), str(getattr(_exc, "args", ())),
                      repr(getattr(_exc, "__dict__", {}))]),
            SECRET_MARKER,
        )
    for _cid, _, _, _ in _E2E_CASES:
        _exc = _e2e_excs[_cid]
        check(
            f"SEC-NO-RESPONSE-ATTR[{_cid}]. 送出例外が response／body／status_code を保持しない",
            sorted(a for a in ("response", "body", "status_code") if hasattr(_exc, a)),
            [],
        )
    check(
        "SEC-EXC-ATTRS. 例外インスタンスの __dict__ が reason のみを保持する",
        sorted(vars(_e2e_excs["BADREQ"]).keys()),
        ["reason"],
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
    # NOEXC: policy module の構造不変（3 assertion）
    # =====================================================================

    print("[NOEXC] policy module の構造不変")

    _policy_tree = parse_file(POLICY_MODULE_FILE)
    check(
        "NOEXC-EXCEPT-0. policy module に ast.ExceptHandler が0件である",
        sum(1 for n in ast.walk(_policy_tree) if isinstance(n, ast.ExceptHandler)),
        0,
    )
    check(
        "NOEXC-RAISE-FROM-0. raise ... from ... が0件である",
        sum(1 for n in ast.walk(_policy_tree)
            if isinstance(n, ast.Raise) and n.cause is not None),
        0,
    )
    check(
        "NOEXC-CLASS-SET. 定義 class が Enum 2件と dataclass 1件のままである",
        {n.name: [b.id for b in n.bases if isinstance(b, ast.Name)]
         for n in ast.walk(_policy_tree) if isinstance(n, ast.ClassDef)},
        {
            "ImageGenerationFallbackAction": ["Enum"],
            "ImageGenerationFailureCategory": ["Enum"],
            "ImageGenerationFallbackDecision": [],
        },
    )
    print()

    # =====================================================================
    # COMPAT: 周辺 Public API 不変（13 assertion）
    # =====================================================================

    print("[COMPAT] 周辺 Public API 不変")

    check(
        "COMPAT-OPENAI-ALL. openai_image_generation.__all__ が3 symbol のまま不変である",
        sorted(_v611_pkg.__all__),
        sorted(["OpenAIImageGenerator", "OpenAIImageGenerationError",
                "OpenAIImageGenerationErrorReason"]),
    )
    _err_sig = inspect.signature(OpenAIImageGenerationError.__init__)
    check(
        "COMPAT-OPENAI-ERROR-SIG-PARAMS. __init__ の parameter 名が不変である",
        list(_err_sig.parameters.keys()),
        ["self", "message", "reason"],
    )
    check_true(
        "COMPAT-OPENAI-ERROR-SIG-NO-DEFAULT. reason が既定値を持たない必須引数のままである",
        _err_sig.parameters["reason"].default is inspect.Parameter.empty,
    )
    check_true("COMPAT-OPENAI-ERROR-BASE. 基底が RuntimeError のまま不変である",
               issubclass(OpenAIImageGenerationError, RuntimeError))
    check(
        "COMPAT-POLICY-ALL. image_generation_fallback_policy.__all__ が既存4 symbol＋"
        "v6.25.0のextract_safe_reasonの5 symbolである",
        sorted(_policy_pkg.__all__),
        sorted(["ImageGenerationFailureCategory", "ImageGenerationFallbackAction",
                "ImageGenerationFallbackDecision", "decide_image_generation_fallback",
                "extract_safe_reason"]),
    )
    check(
        "COMPAT-POLICY-SIG. decide_image_generation_fallback の signature が (error) のままである",
        list(inspect.signature(decide_image_generation_fallback).parameters.keys()),
        ["error"],
    )
    check("COMPAT-CATEGORY-5. ImageGenerationFailureCategory が5値のまま不変である",
          len(list(CAT)), 5)
    check("COMPAT-ACTION-2. ImageGenerationFallbackAction が2値のまま不変である",
          len(list(ACT)), 2)
    check(
        "COMPAT-DECISION-FIELDS. ImageGenerationFallbackDecision の field が category のみである",
        [f.name for f in dataclasses.fields(ImageGenerationFallbackDecision)],
        ["category"],
    )
    check("COMPAT-WP-REASON-12. WordPressMediaUploadErrorReason が12値のまま不変である",
          len(list(WordPressMediaUploadErrorReason)), 12)
    import wordpress_media as _v69_pkg
    check(
        "COMPAT-WP-ALL. wordpress_media.__all__ が4 symbol のまま不変である",
        sorted(_v69_pkg.__all__),
        sorted(["MediaUploadResult", "WordPressMediaUploadError",
                "WordPressMediaUploadErrorReason", "WordPressMediaUploader"]),
    )
    check("COMPAT-RUNTIME-STATUS-3. ArticleFeaturedMediaRuntimeStatus が3値のまま不変である",
          len(list(ArticleFeaturedMediaRuntimeStatus)), 3)
    check(
        "COMPAT-GENERATOR-MEMBERS. OpenAIImageGenerator の public member が不変である",
        sorted(n for n in vars(OpenAIImageGenerator) if not n.startswith("_")),
        sorted(["from_env", "generate", "output_mime_type"]),
    )
    print()

    # =====================================================================
    # NOIMPACT: Runtime Zero Diff（baseline 固定 guard・97 assertion）
    # =====================================================================

    print("[NOIMPACT] Runtime Zero Diff（baseline 固定 guard）")

    BASELINE_COMMIT = "8fd845348d1ee4c80db8de2942da5f99c2bcf0fd"

    _rev_proc = subprocess.run(
        ["git", "rev-parse", "--verify", f"{BASELINE_COMMIT}^{{commit}}"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
    )
    check_true("NOIMPACT-BASELINE-RESOLVABLE. baseline commit が解決できる"
               "（vacuous pass 防止）", _rev_proc.returncode == 0)

    # v6.21.0／v6.22.0 と同一の22パス（GR-1：保護対象を削除しない）。
    # DEF-6.23-9（v6.26.0）により、_protected_paths・_allowed_source_changes・
    # _allowed_test_changes は tests/zero_diff_guard_registry.py（共有レジストリ）
    # 側で一元管理する。本guard自身の値・判定結果はrefactor前と完全一致する
    # （tests/test_e2e_v6_26_0_zero_diff_guard_registry_foundation.py で固定検証）。
    import zero_diff_guard_registry as _guard_registry  # noqa: E402

    _protected_paths = list(_guard_registry.PROTECTED_PATHS)

    # 本Releaseが正当に変更する2ファイル（設計書10.1節・GR-4）
    _allowed_source_changes = _guard_registry.allowed_source_changes_for("v6.23.0")

    for _rel in _protected_paths:
        check_true(f"NOIMPACT-EXISTS[{_rel}]. 検査対象が作業ツリーに実在する",
                   (PROJECT_ROOT / _rel).exists())
        _ls = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", BASELINE_COMMIT, "--", _rel],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
        )
        check_true(f"NOIMPACT-BASELINE-TRACKED[{_rel}]. baseline に追跡ファイルが存在する",
                   _ls.returncode == 0 and bool(_ls.stdout.strip()))
        _diff = subprocess.run(
            ["git", "diff", "--name-only", "--relative", BASELINE_COMMIT, "--", _rel],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
        )
        _changed = {line.strip() for line in _diff.stdout.splitlines() if line.strip()}
        check(f"NOIMPACT-SCOPE[{_rel}]. baseline からの差分が allow-list の範囲内である",
              sorted(_changed - _allowed_source_changes.get(_rel, frozenset())), [])
        _status = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all", "--", _rel],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
        )
        check(f"NOIMPACT-NO-UNTRACKED[{_rel}]. untracked 集合が空である",
              [line for line in _status.stdout.splitlines() if line.startswith("??")], [])

    # coverage / equality（GR-6：新Release側は equality で検証する）
    for _rel, _allowed in _allowed_source_changes.items():
        _diff = subprocess.run(
            ["git", "diff", "--name-only", "--relative", BASELINE_COMMIT, "--", _rel],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
        )
        _changed = {line.strip() for line in _diff.stdout.splitlines() if line.strip()}
        check(f"NOIMPACT-SCOPE-COVERAGE[{_rel}]. allow-list のファイルが実際に変更されている",
              sorted(_allowed - _changed), [])
    for _rel, _allowed in _allowed_source_changes.items():
        _diff = subprocess.run(
            ["git", "diff", "--name-only", "--relative", BASELINE_COMMIT, "--", _rel],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
        )
        _changed = {line.strip() for line in _diff.stdout.splitlines() if line.strip()}
        check_true(f"NOIMPACT-SCOPE-EXACT[{_rel}]. containment と coverage の両方が成立し "
                   "equality となる", _changed == set(_allowed))

    # 共有レジストリ（DEF-6.23-9）が本Release（v6.23.0）以降のwindowとして
    # 合成する集合の範囲内以外に差分があってはならない。
    _allowed_test_changes = set(_guard_registry.allowed_test_changes_for("v6.23.0"))
    _tests_diff = subprocess.run(
        ["git", "diff", "--name-only", BASELINE_COMMIT, "--", "tests"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
    )
    _changed_tests = {
        Path(line.strip().replace("\\", "/")).name
        for line in _tests_diff.stdout.splitlines() if line.strip()
    }
    check("NOIMPACT-TESTS-SCOPE. tests/ の差分が allow-list の範囲内である"
          "（GR-7 に従い許容件数はラベルへ埋め込まない）",
          sorted(_changed_tests - _allowed_test_changes), [])
    _tests_status = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", "tests"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
    )
    _untracked_tests = {
        Path(line[3:]).name for line in _tests_status.stdout.splitlines()
        if line.startswith("??")
    }
    check("NOIMPACT-NO-UNTRACKED-TESTS. tests/ の untracked が allow-list の範囲内である",
          sorted(_untracked_tests - _allowed_test_changes), [])

    # ── 陽性対照：allow-list 機構が空振りしていないことの確認（DEF-6.23-12 解消） ──
    # v6.24.0 で、ハードコードされたリテラル集合のみを演算する恒真式2件から、
    # 実 _changed_actual（git diff 実測出力）と実 allow-list 値を参照する
    # D12-1〜D12-5 の5 assertion へ置換した。既存の NOIMPACT-SCOPE（containment）／
    # -COVERAGE／-EXACT は検査ロジック・期待値・件数のいずれも変更していない（D-b）。
    _pc_rel = "src/openai_image_generation"
    _pc_diff = subprocess.run(
        ["git", "diff", "--name-only", "--relative", BASELINE_COMMIT, "--", _pc_rel],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
    )
    _changed_actual = {line.strip() for line in _pc_diff.stdout.splitlines() if line.strip()}
    _allowed_actual = frozenset(_allowed_source_changes[_pc_rel])
    _DUMMY = "src/openai_image_generation/__positive_control_never_exists__.py"
    _snapshot_before = {k: frozenset(v) for k, v in _allowed_source_changes.items()}

    # D12-1：実差分が非空であること（以降の陽性対照が vacuous でないことの前提）
    check_true(
        "NOIMPACT-POSITIVE-PRECOND-CHANGED-NONEMPTY. 実差分が非空である"
        "（以降の陽性対照が vacuous でないことの前提）",
        len(_changed_actual) > 0,
    )
    # D12-2：ダミー path が実差分に含まれないこと
    check_false(
        "NOIMPACT-POSITIVE-PRECOND-DUMMY-ABSENT. ダミー path が実差分に含まれない",
        _DUMMY in _changed_actual,
    )
    # D12-3：実 _changed_actual に対し、allow-list を空にすると containment が違反を検出する
    check_true(
        "NOIMPACT-POSITIVE-EMPTY-ALLOWLIST. allow-list を空にすると差分が検出される"
        "（containment 検査が有効に働いている。実 _changed_actual を参照）",
        len(_changed_actual - frozenset()) > 0,
    )
    # D12-4：実 allow-list 値に未変更 path を加えると coverage が検出する
    #        （| は新しい frozenset を生成し、元集合を破壊しない。D-a）
    check_true(
        "NOIMPACT-POSITIVE-UNCHANGED-ALLOWLIST. allow-list に書いたのに未変更なら "
        "coverage が検出する（実 allow-list 値を参照）",
        len((_allowed_actual | {_DUMMY}) - _changed_actual) > 0,
    )
    # D12-5：陽性対照が元集合を破壊的に変更していないこと
    check(
        "NOIMPACT-POSITIVE-NONDESTRUCTIVE. 陽性対照が _allowed_source_changes を"
        "破壊的に変更しない",
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
print("Release：v6.23.0")
print("正式名称：OpenAI Image Generation API Rejection Reason Classification Foundation")
print(f"Assertion合計：{total}（設計書12.8.2節の見込み値：332）")
print(f"合計: {passed}/{total} PASS  /  {failed} FAIL")
print("=" * 70)

if failed > 0:
    print()
    print("FAILしたテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
