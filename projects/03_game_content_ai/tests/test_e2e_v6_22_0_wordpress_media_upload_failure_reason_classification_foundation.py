"""
E2E テスト: v6.22.0 WordPress Media Upload Failure Reason Classification Foundation（DI-10）

Source of Truth:
    docs/design/wordpress_media_upload_failure_reason_classification_foundation.md
    （Architecture Review 5：Approved with Suggestions、Blocking 0・Major 0・
      Minor 1（M5-1、Deferred）・Suggestion 1）

本テストは実WordPress API・実HTTP通信を一切行わない。requests.post は
unittest.mock.patch でFake化する（Patch target:
wordpress_media.wordpress_media_uploader.requests.post）。

本Releaseは Consumer-less Foundation であり、production behavior（成功・失敗の
挙動・例外型・例外message・upload()のsignature・分岐条件）を一切変更しない。
変更するのは `src/wordpress_media/wordpress_media_uploader.py` と
`src/wordpress_media/__init__.py` の2ファイルのみ（reasonの純追加）。

Scenario構成:
    API-       Enum定義・12値・package root公開・__all__ 4 symbol
    SIG-       WordPressMediaUploadError.__init__ のsignature
    CTOR-      1引数構築（後方互換）／positional 2引数／keyword 2引数
    NOVAL-     不正なreason値でも__init__が例外を送出しない
    REQEXC-    _classify_request_exceptionの型判定（ConnectTimeout多重継承含む）
    STATUS-    _classify_status_codeの値判定
    REASON-R1〜R9  9 raise経路それぞれのreasonを1件ずつ固定
    MSG-       9経路のmessageがv6.21.0時点と完全一致
    COND-      成功／失敗の分岐条件が不変
    SUCCESS-   2xx正常系でMediaUploadResultが不変
    CHAIN-     R-1・R-3の__cause__が保持される
    NOPARSE-   分類関数2本のみを対象としたAST検査（message解析禁止）
    GUARD-     GUARD-WMUE-CONSTRUCTION-SHAPE（occurrence-context allow-list）＋
               GUARD-WMUE-POSITIVE-CONTROL（P-1〜P-10・N-1〜N-9）
    SEC-       reason全12値が安全なラベルのみ・response非保持
    POLICY-    v6.19 decide_image_generation_fallback()が12 reason全てで不変
    DEP-       src/wordpress_media/の importがos/re/enum/requests/.media_upload_resultのみ
    SOCKET-    in-process network遮断検証
    NOIMPACT-  v6.22.0 baseline commit固定によるRuntime Zero Diff
               （containment／coverage／untracked補完／baseline pinned・ancestor）
    COMPAT-    v6.10〜v6.21各packageの__all__・MediaUploadResult・upload() signature・
               基底クラス不変
    COMPAT-DEP- v6.9 DEP-1〜4・ENV-4・ENV-5 guardが本Release実装後もPASSすること

実行方法:
    cd projects/03_game_content_ai
    venv\\Scripts\\python.exe tests/test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py
"""
import ast
import inspect
import socket
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ─── テスト用ユーティリティ（v6.9.0〜v6.21.0 precedentを踏襲） ───

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


def invoke(fn):
    """例外を送出せず(結果, 例外)のペアを返す。"""
    try:
        return fn(), None
    except Exception as exc:  # noqa: BLE001 - テスト用の汎用捕捉
        return None, exc


print("=" * 60)
print("v6.22.0 WordPress Media Upload Failure Reason Classification Foundation E2E テスト")
print("=" * 60)
print()

# ─── production module の import ───

import wordpress_media  # noqa: E402
from wordpress_media import (  # noqa: E402
    MediaUploadResult,
    WordPressMediaUploadError,
    WordPressMediaUploadErrorReason,
    WordPressMediaUploader,
)
from wordpress_media import wordpress_media_uploader as _wmu_module  # noqa: E402

_classify_request_exception = _wmu_module._classify_request_exception
_classify_status_code = _wmu_module._classify_status_code

_UPLOADER_FILE = PROJECT_ROOT / "src" / "wordpress_media" / "wordpress_media_uploader.py"
_INIT_FILE = PROJECT_ROOT / "src" / "wordpress_media" / "__init__.py"

_uploader = WordPressMediaUploader(
    site_url="https://example.com", username="user", app_password="pass"
)

_PATCH_TARGET = "wordpress_media.wordpress_media_uploader.requests.post"


def _make_mock_response(status_code, json_value=None, json_side_effect=None):
    resp = MagicMock()
    resp.status_code = status_code
    if json_side_effect is not None:
        resp.json.side_effect = json_side_effect
    else:
        resp.json.return_value = json_value
    return resp


_SUCCESS_JSON = {
    "id": 1,
    "source_url": "https://example.com/wp-content/uploads/x.png",
    "mime_type": "image/png",
}


# =====================================================================
# API: Enum定義・package root公開Contract
# =====================================================================

print("[API] WordPressMediaUploadErrorReason Enum Contract")

_ALL_REASONS = list(WordPressMediaUploadErrorReason)
check("API-1. reasonが12値である", len(_ALL_REASONS), 12)

_EXPECTED_REASON_VALUES = {
    "TIMEOUT": "timeout",
    "CONNECTION": "connection",
    "AUTHENTICATION": "authentication",
    "PERMISSION_DENIED": "permission_denied",
    "ROUTE_NOT_FOUND": "route_not_found",
    "PAYLOAD_TOO_LARGE": "payload_too_large",
    "UNSUPPORTED_MEDIA_TYPE": "unsupported_media_type",
    "RATE_LIMIT": "rate_limit",
    "REQUEST_REJECTED": "request_rejected",
    "SERVER_ERROR": "server_error",
    "INVALID_RESPONSE": "invalid_response",
    "UNKNOWN": "unknown",
}
check(
    "API-2. reason名の集合が設計書10.1節と一致する",
    sorted(r.name for r in _ALL_REASONS),
    sorted(_EXPECTED_REASON_VALUES.keys()),
)
for _name, _value in _EXPECTED_REASON_VALUES.items():
    check(
        f"API-3[{_name}]. valueが固定文字列と一致する",
        WordPressMediaUploadErrorReason[_name].value,
        _value,
    )

check_true(
    "API-4. WordPressMediaUploadErrorReasonがpackage rootから公開される",
    "WordPressMediaUploadErrorReason" in dir(wordpress_media),
)
check(
    "API-5. __all__が4 symbolである",
    sorted(wordpress_media.__all__),
    sorted([
        "MediaUploadResult",
        "WordPressMediaUploadError",
        "WordPressMediaUploadErrorReason",
        "WordPressMediaUploader",
    ]),
)
print()

# =====================================================================
# SIG / CTOR / NOVAL: __init__ のsignature・構築形・非validation Contract
# =====================================================================

print("[SIG] WordPressMediaUploadError.__init__ Signature Contract")

_sig = inspect.signature(WordPressMediaUploadError.__init__)
check(
    "SIG-1. parameter名が[self, message, reason]である",
    list(_sig.parameters.keys()),
    ["self", "message", "reason"],
)
check(
    "SIG-2. reasonの既定値がUNKNOWNである",
    _sig.parameters["reason"].default,
    WordPressMediaUploadErrorReason.UNKNOWN,
)
print()

print("[CTOR] 構築形Contract")

_ctor1 = WordPressMediaUploadError("m")
check(
    "CTOR-1. 1引数構築（後方互換）でreasonがUNKNOWNになる",
    _ctor1.reason,
    WordPressMediaUploadErrorReason.UNKNOWN,
)

_ctor2 = WordPressMediaUploadError("m", WordPressMediaUploadErrorReason.TIMEOUT)
check(
    "CTOR-2. positional 2引数構築でreasonが反映される",
    _ctor2.reason,
    WordPressMediaUploadErrorReason.TIMEOUT,
)

_ctor3 = WordPressMediaUploadError("m", reason=WordPressMediaUploadErrorReason.CONNECTION)
check(
    "CTOR-3. keyword 2引数構築でreasonが反映される",
    _ctor3.reason,
    WordPressMediaUploadErrorReason.CONNECTION,
)
check("CTOR-4. messageがstr(exc)へ反映される", str(_ctor1), "m")
print()

print("[NOVAL] reason非validation Contract")

for _label, _bad_reason in [("str", "not-a-reason"), ("None", None), ("list", ["x"])]:
    _result, _exc = invoke(lambda br=_bad_reason: WordPressMediaUploadError("m", reason=br))
    check_true(f"NOVAL-1[{_label}]. __init__が例外を送出しない", _exc is None)
    if _result is not None:
        check(f"NOVAL-2[{_label}]. 不正な値がそのままreasonへ保持される", _result.reason, _bad_reason)
print()

# =====================================================================
# REQEXC: _classify_request_exception の型判定Contract
# =====================================================================

print("[REQEXC] _classify_request_exception 型判定Contract")

_REQEXC_TIMEOUT_TYPES = [
    requests.exceptions.ConnectTimeout,  # ConnectionError と Timeout の両方のsubclass
    requests.exceptions.ReadTimeout,
    requests.exceptions.Timeout,
]
for _exc_cls in _REQEXC_TIMEOUT_TYPES:
    check(
        f"REQEXC-TIMEOUT[{_exc_cls.__name__}]. TIMEOUTへ分類される",
        _classify_request_exception(_exc_cls("x")),
        WordPressMediaUploadErrorReason.TIMEOUT,
    )

_REQEXC_CONNECTION_TYPES = [
    requests.exceptions.ConnectionError,
    requests.exceptions.SSLError,
    requests.exceptions.ProxyError,
]
for _exc_cls in _REQEXC_CONNECTION_TYPES:
    check(
        f"REQEXC-CONNECTION[{_exc_cls.__name__}]. CONNECTIONへ分類される",
        _classify_request_exception(_exc_cls("x")),
        WordPressMediaUploadErrorReason.CONNECTION,
    )

_REQEXC_UNKNOWN_TYPES = [
    requests.exceptions.TooManyRedirects,
    requests.exceptions.URLRequired,
    requests.exceptions.InvalidURL,
    requests.exceptions.ChunkedEncodingError,
    requests.exceptions.RetryError,
    requests.exceptions.RequestException,
]
for _exc_cls in _REQEXC_UNKNOWN_TYPES:
    check(
        f"REQEXC-UNKNOWN[{_exc_cls.__name__}]. UNKNOWNへ分類される",
        _classify_request_exception(_exc_cls("x")),
        WordPressMediaUploadErrorReason.UNKNOWN,
    )
print()

# =====================================================================
# STATUS: _classify_status_code の値判定Contract
# =====================================================================

print("[STATUS] _classify_status_code 値判定Contract")

_STATUS_INDIVIDUAL = {
    401: WordPressMediaUploadErrorReason.AUTHENTICATION,
    403: WordPressMediaUploadErrorReason.PERMISSION_DENIED,
    404: WordPressMediaUploadErrorReason.ROUTE_NOT_FOUND,
    413: WordPressMediaUploadErrorReason.PAYLOAD_TOO_LARGE,
    415: WordPressMediaUploadErrorReason.UNSUPPORTED_MEDIA_TYPE,
    429: WordPressMediaUploadErrorReason.RATE_LIMIT,
}
for _code, _expected in _STATUS_INDIVIDUAL.items():
    check(f"STATUS-INDIVIDUAL[{_code}]. 個別reasonへ分類される", _classify_status_code(_code), _expected)

for _code in (400, 402, 405, 409, 422):
    check(
        f"STATUS-REQUEST-REJECTED[{_code}]. REQUEST_REJECTEDへ分類される",
        _classify_status_code(_code),
        WordPressMediaUploadErrorReason.REQUEST_REJECTED,
    )

for _code in (500, 502, 503, 599):
    check(
        f"STATUS-SERVER-ERROR[{_code}]. SERVER_ERRORへ分類される",
        _classify_status_code(_code),
        WordPressMediaUploadErrorReason.SERVER_ERROR,
    )

for _code in (199, 300, 304, 600):
    check(
        f"STATUS-UNKNOWN[{_code}]. UNKNOWNへ分類される（範囲外）",
        _classify_status_code(_code),
        WordPressMediaUploadErrorReason.UNKNOWN,
    )

for _label, _bad_value in [("bool-True", True), ("float", 404.0), ("None", None)]:
    check(
        f"STATUS-DEFENSIVE[{_label}]. 非int(bool含む)はUNKNOWNへ分類される（防御的分岐）",
        _classify_status_code(_bad_value),
        WordPressMediaUploadErrorReason.UNKNOWN,
    )
print()

# =====================================================================
# REASON-R1〜R9 / MSG / COND / SUCCESS / CHAIN
# =====================================================================

print("[REASON-R1〜R9 / MSG / COND / SUCCESS / CHAIN] 9 raise経路の behavioral 検証")

# --- R-1: requests.RequestException（通信失敗） ---
with patch(_PATCH_TARGET, side_effect=requests.ConnectionError("boom")):
    _, _exc_r1 = invoke(
        lambda: _uploader.upload(b"\x89PNG", "a.png", "image/png")
    )
check_true("REASON-R1. 例外が送出される", isinstance(_exc_r1, WordPressMediaUploadError))
check(
    "REASON-R1. reasonがCONNECTIONへ分類される",
    _exc_r1.reason,
    WordPressMediaUploadErrorReason.CONNECTION,
)
check("MSG-R1. messageがv6.21.0時点と完全一致する", str(_exc_r1), "WordPress Media APIへの通信に失敗しました")
check_true("CHAIN-R1. __cause__が保持される", isinstance(_exc_r1.__cause__, requests.ConnectionError))

# --- R-2: non-2xx status ---
with patch(_PATCH_TARGET, return_value=_make_mock_response(500)):
    _, _exc_r2 = invoke(lambda: _uploader.upload(b"\x89PNG", "a.png", "image/png"))
check_true("REASON-R2. 例外が送出される", isinstance(_exc_r2, WordPressMediaUploadError))
check(
    "REASON-R2. reasonがSERVER_ERRORへ分類される",
    _exc_r2.reason,
    WordPressMediaUploadErrorReason.SERVER_ERROR,
)
check(
    "MSG-R2. messageが_build_non_2xx_message()の出力形式と一致する",
    str(_exc_r2),
    "WordPress Media API returned HTTP 500",
)

# COND: 2xx境界値（200・299は成功、300は失敗）
for _code in (200, 299):
    with patch(_PATCH_TARGET, return_value=_make_mock_response(_code, json_value=_SUCCESS_JSON)):
        _result, _exc = invoke(lambda: _uploader.upload(b"\x89PNG", "a.png", "image/png"))
    check_true(f"COND-2XX-BOUNDARY[{_code}]. 成功として扱われる", _exc is None and isinstance(_result, MediaUploadResult))
with patch(_PATCH_TARGET, return_value=_make_mock_response(300)):
    _, _exc_300 = invoke(lambda: _uploader.upload(b"\x89PNG", "a.png", "image/png"))
check_true("COND-2XX-BOUNDARY[300]. 失敗として扱われる（2xxでない）", isinstance(_exc_300, WordPressMediaUploadError))
check(
    "COND-2XX-BOUNDARY[300]. reasonがUNKNOWNへ分類される（3xxは範囲外）",
    _exc_300.reason,
    WordPressMediaUploadErrorReason.UNKNOWN,
)

# --- R-3: 2xx応答の.json()がValueError ---
with patch(
    _PATCH_TARGET,
    return_value=_make_mock_response(201, json_side_effect=ValueError("bad json")),
):
    _, _exc_r3 = invoke(lambda: _uploader.upload(b"\x89PNG", "a.png", "image/png"))
check_true("REASON-R3. 例外が送出される", isinstance(_exc_r3, WordPressMediaUploadError))
check(
    "REASON-R3. reasonがINVALID_RESPONSEへ分類される",
    _exc_r3.reason,
    WordPressMediaUploadErrorReason.INVALID_RESPONSE,
)
check(
    "MSG-R3. messageがv6.21.0時点と完全一致する",
    str(_exc_r3),
    "WordPress Media APIの成功レスポンスが不正です",
)
check_true("CHAIN-R3. __cause__が保持される", isinstance(_exc_r3.__cause__, ValueError))

# --- R-4: 2xx応答のJSONがdictでない ---
with patch(_PATCH_TARGET, return_value=_make_mock_response(201, json_value=["not", "a", "dict"])):
    _, _exc_r4 = invoke(lambda: _uploader.upload(b"\x89PNG", "a.png", "image/png"))
check(
    "REASON-R4. reasonがINVALID_RESPONSEへ分類される",
    _exc_r4.reason,
    WordPressMediaUploadErrorReason.INVALID_RESPONSE,
)
check("MSG-R4. messageがv6.21.0時点と完全一致する", str(_exc_r4), "WordPress Media APIの成功レスポンスが不正です")

# --- R-5: id 不正（欠落／bool／非int／<1） ---
for _label, _bad_id in [
    ("missing", {}),
    ("bool", {"id": True}),
    ("non-int", {"id": "1"}),
    ("less-than-1", {"id": 0}),
]:
    _json = {**_SUCCESS_JSON, **_bad_id}
    if _label == "missing":
        _json = {k: v for k, v in _SUCCESS_JSON.items() if k != "id"}
    with patch(_PATCH_TARGET, return_value=_make_mock_response(201, json_value=_json)):
        _, _exc_r5 = invoke(lambda: _uploader.upload(b"\x89PNG", "a.png", "image/png"))
    check(
        f"REASON-R5[{_label}]. reasonがINVALID_RESPONSEへ分類される",
        _exc_r5.reason,
        WordPressMediaUploadErrorReason.INVALID_RESPONSE,
    )
    check(f"MSG-R5[{_label}]. messageがv6.21.0時点と完全一致する", str(_exc_r5), "WordPress Media APIの成功レスポンスが不正です（id）")
# COND: id=1（正の整数）は成功する
with patch(_PATCH_TARGET, return_value=_make_mock_response(201, json_value={**_SUCCESS_JSON, "id": 1})):
    _result_id1, _exc_id1 = invoke(lambda: _uploader.upload(b"\x89PNG", "a.png", "image/png"))
check_true("COND-ID-VALID. id=1は成功する", _exc_id1 is None and isinstance(_result_id1, MediaUploadResult))

# --- R-6: source_url キー欠落 ---
_json_r6 = {k: v for k, v in _SUCCESS_JSON.items() if k != "source_url"}
with patch(_PATCH_TARGET, return_value=_make_mock_response(201, json_value=_json_r6)):
    _, _exc_r6 = invoke(lambda: _uploader.upload(b"\x89PNG", "a.png", "image/png"))
check(
    "REASON-R6. reasonがINVALID_RESPONSEへ分類される",
    _exc_r6.reason,
    WordPressMediaUploadErrorReason.INVALID_RESPONSE,
)
check(
    "MSG-R6. messageがv6.21.0時点と完全一致する",
    str(_exc_r6),
    "WordPress Media APIの成功レスポンスが不正です（source_url）",
)

# --- R-7: source_url が None でも str でもない ---
with patch(
    _PATCH_TARGET,
    return_value=_make_mock_response(201, json_value={**_SUCCESS_JSON, "source_url": 123}),
):
    _, _exc_r7 = invoke(lambda: _uploader.upload(b"\x89PNG", "a.png", "image/png"))
check(
    "REASON-R7. reasonがINVALID_RESPONSEへ分類される",
    _exc_r7.reason,
    WordPressMediaUploadErrorReason.INVALID_RESPONSE,
)
check(
    "MSG-R7. messageがv6.21.0時点と完全一致する",
    str(_exc_r7),
    "WordPress Media APIの成功レスポンスが不正です（source_url）",
)
# COND: source_url=None は許容される（成功する）
with patch(
    _PATCH_TARGET,
    return_value=_make_mock_response(201, json_value={**_SUCCESS_JSON, "source_url": None}),
):
    _result_r7ok, _exc_r7ok = invoke(lambda: _uploader.upload(b"\x89PNG", "a.png", "image/png"))
check_true("COND-SOURCE-URL-NONE. source_url=Noneは成功する", _exc_r7ok is None)

# --- R-8: mime_type キー欠落 ---
_json_r8 = {k: v for k, v in _SUCCESS_JSON.items() if k != "mime_type"}
with patch(_PATCH_TARGET, return_value=_make_mock_response(201, json_value=_json_r8)):
    _, _exc_r8 = invoke(lambda: _uploader.upload(b"\x89PNG", "a.png", "image/png"))
check(
    "REASON-R8. reasonがINVALID_RESPONSEへ分類される",
    _exc_r8.reason,
    WordPressMediaUploadErrorReason.INVALID_RESPONSE,
)
check(
    "MSG-R8. messageがv6.21.0時点と完全一致する",
    str(_exc_r8),
    "WordPress Media APIの成功レスポンスが不正です（mime_type）",
)

# --- R-9: mime_type が None でも str でもない ---
with patch(
    _PATCH_TARGET,
    return_value=_make_mock_response(201, json_value={**_SUCCESS_JSON, "mime_type": 999}),
):
    _, _exc_r9 = invoke(lambda: _uploader.upload(b"\x89PNG", "a.png", "image/png"))
check(
    "REASON-R9. reasonがINVALID_RESPONSEへ分類される",
    _exc_r9.reason,
    WordPressMediaUploadErrorReason.INVALID_RESPONSE,
)
check(
    "MSG-R9. messageがv6.21.0時点と完全一致する",
    str(_exc_r9),
    "WordPress Media APIの成功レスポンスが不正です（mime_type）",
)

# SUCCESS: 2xx正常系でMediaUploadResultが不変・例外なし
with patch(_PATCH_TARGET, return_value=_make_mock_response(201, json_value=_SUCCESS_JSON)):
    _success_result, _success_exc = invoke(lambda: _uploader.upload(b"\x89PNG", "a.png", "image/png"))
check_true("SUCCESS-1. 例外が送出されない", _success_exc is None)
check_true("SUCCESS-2. MediaUploadResultが返る", isinstance(_success_result, MediaUploadResult))
check("SUCCESS-3. media_idが反映される", _success_result.media_id, 1)
check(
    "SUCCESS-4. source_urlが反映される",
    _success_result.source_url,
    "https://example.com/wp-content/uploads/x.png",
)
check("SUCCESS-5. mime_typeが反映される", _success_result.mime_type, "image/png")
print()

# =====================================================================
# NOPARSE: 分類関数2本のみを対象としたAST検査（message解析禁止）
# =====================================================================

print("[NOPARSE] 分類関数のmessage解析禁止Contract（AST検査）")

_FORBIDDEN_ATTRS = {"args", "text", "headers", "content"}


def _scan_noparse_violations(func_node) -> list:
    violations = []
    for node in ast.walk(func_node):
        if isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_ATTRS:
            violations.append(f"L{node.lineno}:.{node.attr}")
        if isinstance(node, ast.Call):
            _f = node.func
            if isinstance(_f, ast.Attribute) and _f.attr == "json":
                violations.append(f"L{node.lineno}:.json()")
            # S2R-1（DEF-6.22-15）の解消：ここでは str() の引数を限定せず、
            # 対象2関数内の「任意の」str(...)呼び出しを禁止している。
            # AC-6.22-13の例示は str(exc) だが、引数名で絞ると
            # str(exc.args[0]) 等の等価な迂回を許してしまう。両分類関数には
            # 正当な str() 呼び出しが存在しないため、引数を問わず一律に
            # 禁止するほうが安全側であり、将来どちらの関数へも一貫して
            # 適用できる。これは意図的な設計判断であり、検査漏れではない。
            if isinstance(_f, ast.Name) and _f.id == "str":
                violations.append(f"L{node.lineno}:str(...)")
        if isinstance(node, ast.Name) and node.id == "message":
            violations.append(f"L{node.lineno}:message")
    return violations


_uploader_tree = ast.parse(_UPLOADER_FILE.read_text(encoding="utf-8"))
_classify_req_node = None
_classify_status_node = None
_non2xx_node = None
_upload_node = None
for _n in ast.walk(_uploader_tree):
    if isinstance(_n, ast.FunctionDef) and _n.name == "_classify_request_exception":
        _classify_req_node = _n
    if isinstance(_n, ast.FunctionDef) and _n.name == "_classify_status_code":
        _classify_status_node = _n
    if isinstance(_n, ast.FunctionDef) and _n.name == "_build_non_2xx_message":
        _non2xx_node = _n
    if isinstance(_n, ast.FunctionDef) and _n.name == "upload":
        _upload_node = _n

check_true("NOPARSE-0. _classify_request_exceptionが検出できる", _classify_req_node is not None)
check_true("NOPARSE-0. _classify_status_codeが検出できる", _classify_status_node is not None)

check(
    "NOPARSE-1. _classify_request_exceptionが禁止参照を持たない",
    _scan_noparse_violations(_classify_req_node),
    [],
)
check(
    "NOPARSE-2. _classify_status_codeが禁止参照を持たない",
    _scan_noparse_violations(_classify_status_node),
    [],
)

# 陽性対照：禁止参照の各形を含む合成ソースが、それぞれ独立に違反として
# 検出されること（設計書17章・AC-6.22-13が列挙する6形すべてを個別に確認する）
_NOPARSE_POSITIVE_CASES = {
    "str(exc)": "def _bad(exc):\n    return str(exc)",
    "exc.args": "def _bad(exc):\n    return exc.args",
    "response.text": "def _bad(response):\n    return response.text",
    "response.json()": "def _bad(response):\n    return response.json()",
    "response.headers": "def _bad(response):\n    return response.headers",
    "response.content": "def _bad(response):\n    return response.content",
}
for _label, _src in _NOPARSE_POSITIVE_CASES.items():
    _pc_tree = ast.parse(_src)
    _pc_func = next(n for n in ast.walk(_pc_tree) if isinstance(n, ast.FunctionDef))
    check_true(
        f"NOPARSE-POSITIVE-CONTROL[{_label}]. 禁止参照({_label})を含む合成ソースが"
        "違反として検出される",
        len(_scan_noparse_violations(_pc_func)) > 0,
    )

# NOPARSE-SCOPE: 本検査が「分類関数2本のみ」を対象とし、module全体
# （特に _build_non_2xx_message() / upload() 内の正当な response.json() 呼び出し）
# を対象としないことを、実際のAST構造に基づいて検証する（vacuous assertionを避ける）。
check_true(
    "NOPARSE-SCOPE-EXISTS[_build_non_2xx_message]. "
    "既存のresponse.json()呼び出しが実在する（本guardが除外すべき対象が"
    "本当に存在することの確認）",
    _non2xx_node is not None
    and any(
        isinstance(_c, ast.Call)
        and isinstance(_c.func, ast.Attribute)
        and _c.func.attr == "json"
        for _c in ast.walk(_non2xx_node)
    ),
)
check_true(
    "NOPARSE-SCOPE-EXISTS[upload]. "
    "既存のresponse.json()呼び出しが実在する（本guardが除外すべき対象が"
    "本当に存在することの確認）",
    _upload_node is not None
    and any(
        isinstance(_c, ast.Call)
        and isinstance(_c.func, ast.Attribute)
        and _c.func.attr == "json"
        for _c in ast.walk(_upload_node)
    ),
)
check_true(
    "NOPARSE-SCOPE-WOULD-VIOLATE[_build_non_2xx_message]. "
    "_build_non_2xx_message()を仮に本検査へ通すと違反が検出される"
    "（response.json()呼び出し・messageローカル変数を持つため）。"
    "これにより「NOPARSE走査対象は_classify_request_exception／"
    "_classify_status_codeの2関数だけ」というスコープ限定が、"
    "実際に意味を持つ制約であることを示す（本テストが_non2xx_nodeを"
    "_scan_noparse_violations()の対象として実際に呼び出すことはない）",
    len(_scan_noparse_violations(_non2xx_node)) > 0,
)
check_true(
    "NOPARSE-SCOPE-WOULD-VIOLATE[upload]. "
    "upload()を仮に本検査へ通すと違反が検出される（response.json()呼び出しを"
    "持つため）。scope限定の対象外であることの構造的証明",
    len(_scan_noparse_violations(_upload_node)) > 0,
)
print()

# =====================================================================
# GUARD: GUARD-WMUE-CONSTRUCTION-SHAPE（occurrence-context allow-list）
# =====================================================================

print("[GUARD] GUARD-WMUE-CONSTRUCTION-SHAPE Contract")

_GUARD_NAME = "WordPressMediaUploadError"


def _guard_docstring_constant_ids(tree: ast.AST) -> set:
    """module/ClassDef/FunctionDef/AsyncFunctionDef のbody先頭docstringに
    該当するast.Constantのid集合を返す（17.1節 手順4のdocstring除外定義）。"""
    ids = set()
    holders = [tree] + [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    for holder in holders:
        body = getattr(holder, "body", None)
        if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
            if isinstance(body[0].value.value, str):
                ids.add(id(body[0].value))
    return ids


def _guard_matches_name(node) -> bool:
    """node が Name(id=NAME) または Attribute(attr=NAME) か（17.1節 手順2/3）。"""
    if isinstance(node, ast.Name) and node.id == _GUARD_NAME:
        return True
    if isinstance(node, ast.Attribute) and node.attr == _GUARD_NAME:
        return True
    return False


def guard_wmue_construction_shape(source: str) -> list:
    """17.1節 手順1〜6 を実装する単一の検査関数（S4-2：単一関数契約）。

    実ファイル・GUARD-WMUE-POSITIVE-CONTROLの全陽性対照(P-1〜P-10)・
    全負の対照(N-1〜N-9)のいずれに対してもこの関数を適用する。
    戻り値：違反の説明文字列のリスト（空リストならPASS）。
    """
    tree = ast.parse(source)
    violations = []

    # 手順2: allow-list の構築
    allowed_ids = set()
    construction_sites = []  # 手順2(b) の Call ノード（raise 直下の直接構築）

    for node in ast.walk(tree):
        # (a) クラス定義
        if isinstance(node, ast.ClassDef) and node.name == _GUARD_NAME:
            allowed_ids.add(id(node))
        # (b) raise 文直下の直接構築
        if isinstance(node, ast.Raise) and isinstance(node.exc, ast.Call):
            if _guard_matches_name(node.exc.func):
                allowed_ids.add(id(node.exc.func))
                construction_sites.append(node.exc)
        # (c) 引数注釈
        if isinstance(node, ast.arg) and node.annotation is not None:
            if _guard_matches_name(node.annotation):
                allowed_ids.add(id(node.annotation))
        # (d) 戻り値注釈
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.returns is not None:
            if _guard_matches_name(node.returns):
                allowed_ids.add(id(node.returns))
        # (e) AnnAssign 注釈（value側は含めない）
        if isinstance(node, ast.AnnAssign):
            if _guard_matches_name(node.annotation):
                allowed_ids.add(id(node.annotation))
        # (f) except節（単一 or Tuple）
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            _targets = node.type.elts if isinstance(node.type, ast.Tuple) else [node.type]
            for _t in _targets:
                if _guard_matches_name(_t):
                    allowed_ids.add(id(_t))
        # (g) isinstance/issubclass 第2引数のみ（単一 or Tuple）
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.func.id in ("isinstance", "issubclass") and len(node.args) >= 2:
                _second = node.args[1]
                _targets = _second.elts if isinstance(_second, ast.Tuple) else [_second]
                for _t in _targets:
                    if _guard_matches_name(_t):
                        allowed_ids.add(id(_t))

    docstring_ids = _guard_docstring_constant_ids(tree)

    # 手順3: 出現の全数検査
    for node in ast.walk(tree):
        if isinstance(node, ast.alias):
            _tail = node.name.split(".")[-1]
            if _tail == _GUARD_NAME or node.asname == _GUARD_NAME:
                violations.append(f"STEP3-ALIAS@L{getattr(node, 'lineno', '?')}")
            continue
        _is_occurrence = (
            (isinstance(node, ast.ClassDef) and node.name == _GUARD_NAME)
            or (isinstance(node, ast.Name) and node.id == _GUARD_NAME)
            or (isinstance(node, ast.Attribute) and node.attr == _GUARD_NAME)
        )
        if _is_occurrence and id(node) not in allowed_ids:
            violations.append(f"STEP3-IDENT@L{node.lineno}")

    # 手順4: 文字列間接参照の封鎖（docstring除外）
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if _GUARD_NAME in node.value and id(node) not in docstring_ids:
                violations.append(f"STEP4-STR@L{node.lineno}")

    # 手順5: 構築形の検査（(b)のみ）
    for call in construction_sites:
        if not any(kw.arg == "reason" for kw in call.keywords):
            violations.append(f"STEP5-NOREASON@L{call.lineno}")
        if len(call.args) != 1:
            violations.append(f"STEP5-POSITIONAL@L{call.lineno}")
        if any(kw.arg is None for kw in call.keywords):
            violations.append(f"STEP5-KWARGS@L{call.lineno}")

    # 手順6: vacuous pass 防止
    if not construction_sites:
        violations.append("STEP6-NOSITES")

    return violations


# --- 実ファイルへ適用 ---
_uploader_source = _UPLOADER_FILE.read_text(encoding="utf-8")
_guard_real_violations = guard_wmue_construction_shape(_uploader_source)
check(
    "GUARD-REAL. 実ファイル(wordpress_media_uploader.py)がGUARD-WMUE-CONSTRUCTION-SHAPEに適合する",
    _guard_real_violations,
    [],
)

# --- GUARD-WMUE-POSITIVE-CONTROL: 陽性対照 P-1〜P-10（正規サイト併存条件） ---
print("[GUARD-WMUE-POSITIVE-CONTROL] 陽性対照 P-1〜P-10")

_GUARD_BASE = 'raise WordPressMediaUploadError("ok", reason=R.TIMEOUT)\n'

_POSITIVE_CASES = {
    "P-1": ('raise WordPressMediaUploadError("m")', "reason=欠落"),
    "P-2": (
        'from .x import WordPressMediaUploadError as E\nraise E("m")',
        "別名import",
    ),
    "P-3": (
        'e = WordPressMediaUploadError("m", reason=R.X)\nraise e',
        "事前構築raiseの再送出",
    ),
    "P-4": ('raise WordPressMediaUploadError("m", R.X)', "positional reason"),
    "P-5": (
        'c = getattr(mod, "WordPressMediaUploadError")\nraise c("m")',
        "getattr経由",
    ),
    "P-6": ('raise globals()["WordPressMediaUploadError"]("m")', "globals()経由"),
    "P-7": (
        '_m = functools.partial(WordPressMediaUploadError)\nraise _m("m")',
        "functools.partial",
    ),
    "P-8": (
        'def _e(msg, reason=R.U):\n    return WordPressMediaUploadError(msg, reason=reason)\n'
        'raise _e("m")',
        "factory/helper経由",
    ),
    "P-9": (
        '_M = {"e": WordPressMediaUploadError}\nraise _M["e"]("m")',
        "dict registry経由",
    ),
    "P-10": ('x = "WordPressMediaUploadErrorReason"', "非docstring文字列"),
}
for _pid, (_extra, _desc) in _POSITIVE_CASES.items():
    _violations = guard_wmue_construction_shape(_GUARD_BASE + _extra)
    check_true(f"GUARD-{_pid}[{_desc}]. 違反として検出される", len(_violations) > 0)

# --- GUARD-WMUE-POSITIVE-CONTROL: 負の対照 N-1〜N-9（正当な記述はPASS） ---
print("[GUARD-WMUE-POSITIVE-CONTROL] 負の対照 N-1〜N-9")

_NEGATIVE_CASES = {
    "N-1": ('raise WordPressMediaUploadError("m", reason=R.X)', "正常形"),
    "N-2": ("def f(e: WordPressMediaUploadError) -> None:\n    pass", "引数注釈"),
    "N-3": ("def f() -> WordPressMediaUploadError:\n    pass", "戻り値注釈"),
    "N-4": ("e: WordPressMediaUploadError\n", "AnnAssign注釈"),
    "N-5": (
        "try:\n    pass\nexcept WordPressMediaUploadError:\n    pass",
        "except節（単一）",
    ),
    "N-5b": (
        "try:\n    pass\nexcept (WordPressMediaUploadError, ValueError):\n    pass",
        "except節（Tuple）",
    ),
    "N-6": ("if isinstance(e, WordPressMediaUploadError):\n    pass", "isinstance"),
    "N-6b": (
        "if isinstance(e, (WordPressMediaUploadError, ValueError)):\n    pass",
        "isinstance（Tuple）",
    ),
    "N-7": ("if issubclass(E, WordPressMediaUploadError):\n    pass", "issubclass第2引数"),
    "N-8": (
        'class WordPressMediaUploadErrorReason(Enum):\n'
        '    """WordPressMediaUploadErrorの安全な失敗分類。"""\n'
        '    U = "u"',
        "Enum docstring",
    ),
    "N-9": ('"""WordPressMediaUploadError を送出するモジュール。"""', "module docstring"),
}
for _nid, (_extra, _desc) in _NEGATIVE_CASES.items():
    if _nid == "N-9":
        _src = _extra + "\n" + _GUARD_BASE
    else:
        _src = _GUARD_BASE + _extra
    _violations = guard_wmue_construction_shape(_src)
    check(f"GUARD-{_nid}[{_desc}]. 違反として検出されない（PASS）", _violations, [])
print()

# =====================================================================
# SEC: reason・例外objectの安全性Contract
# =====================================================================

print("[SEC] reason・例外objectの安全性Contract")

for _reason in _ALL_REASONS:
    _value = _reason.value
    check_true(f"SEC-1[{_reason.name}]. valueが小文字snake_caseの固定文字列である", _value.islower() and " " not in _value)
    check_not_contains(f"SEC-2[{_reason.name}]. valueにhttpを含まない（credential/URL混入防止）", _value, "http")

with patch(_PATCH_TARGET, return_value=_make_mock_response(500)):
    _, _exc_sec = invoke(lambda: _uploader.upload(b"\x89PNG", "a.png", "image/png"))
check_false("SEC-3. 例外instanceがresponse属性を保持しない", hasattr(_exc_sec, "response"))
check_false("SEC-4. 例外instanceがstatus_code属性を保持しない（10.3節 D-2）", hasattr(_exc_sec, "status_code"))
print()

# =====================================================================
# POLICY: v6.19 decide_image_generation_fallback() の出力不変Contract
# =====================================================================

print("[POLICY] v6.19 decide_image_generation_fallback() 出力不変Contract")

from image_generation_fallback_policy import (  # noqa: E402
    ImageGenerationFailureCategory,
    ImageGenerationFallbackAction,
    decide_image_generation_fallback,
)

for _reason in _ALL_REASONS:
    _decision = decide_image_generation_fallback(WordPressMediaUploadError("m", reason=_reason))
    check(
        f"POLICY-CATEGORY[{_reason.name}]. MEDIA_UPLOAD_FAILEDへ分類される",
        _decision.category,
        ImageGenerationFailureCategory.MEDIA_UPLOAD_FAILED,
    )
    check(
        f"POLICY-ACTION[{_reason.name}]. PROPAGATE_ORIGINAL_ERRORとなる",
        _decision.action,
        ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR,
    )
# reason属性が欠落した(既定値未適用の)ケースとの後方互換も確認
_decision_no_reason_kw = decide_image_generation_fallback(WordPressMediaUploadError("m"))
check(
    "POLICY-DEFAULT. reason未指定(既定値UNKNOWN)でもMEDIA_UPLOAD_FAILEDのまま",
    _decision_no_reason_kw.category,
    ImageGenerationFailureCategory.MEDIA_UPLOAD_FAILED,
)
print()

# =====================================================================
# DEP: import制限Contract（AST検査）
# =====================================================================

print("[DEP] src/wordpress_media/wordpress_media_uploader.py の import制限Contract")

_ALLOWED_ABSOLUTE_IMPORTS = {"os", "re", "enum", "requests"}
_ALLOWED_RELATIVE_MODULES = {"media_upload_result"}

_dep_absolute_roots = set()
_dep_relative_modules = set()
for _node in ast.walk(_uploader_tree):
    if isinstance(_node, ast.Import):
        for _alias in _node.names:
            _dep_absolute_roots.add(_alias.name.split(".")[0])
    elif isinstance(_node, ast.ImportFrom):
        if _node.level and _node.level > 0:
            if _node.module:
                _dep_relative_modules.add(_node.module)
        elif _node.module:
            _dep_absolute_roots.add(_node.module.split(".")[0])

check(
    "DEP-1. 絶対importがos/re/enum/requestsのみである",
    sorted(_dep_absolute_roots),
    sorted(_ALLOWED_ABSOLUTE_IMPORTS),
)
check(
    "DEP-2. 相対importが.media_upload_resultのみである",
    sorted(_dep_relative_modules),
    sorted(_ALLOWED_RELATIVE_MODULES),
)
print()

# =====================================================================
# SOCKET: in-process network遮断検証
# =====================================================================

print("[SOCKET] in-process network遮断検証")

_orig_getaddrinfo = socket.getaddrinfo
_orig_connect = socket.socket.connect
_socket_call_log = []


def _blocked_getaddrinfo(*args, **kwargs):
    _socket_call_log.append("getaddrinfo")
    raise AssertionError("socket.getaddrinfo was called (unexpected DNS resolution)")


def _blocked_connect(self, *args, **kwargs):
    _socket_call_log.append("connect")
    raise AssertionError("socket.socket.connect was called (unexpected network connection)")


socket.getaddrinfo = _blocked_getaddrinfo
socket.socket.connect = _blocked_connect
try:
    # 成功系（requests.post を2xxレスポンスでmock化）：例外は送出されないはず
    with patch(_PATCH_TARGET, return_value=_make_mock_response(201, json_value=_SUCCESS_JSON)):
        _, _socket_exc1 = invoke(lambda: _uploader.upload(b"\x89PNG", "a.png", "image/png"))
    # 失敗系（requests.post が ConnectionError をmock化）：
    # upload() が WordPressMediaUploadError を送出するのは正しい挙動であり、
    # ここで確認したいのは「その過程で real socket が一切呼ばれないこと」のみ。
    with patch(_PATCH_TARGET, side_effect=requests.ConnectionError("boom")):
        _, _socket_exc2 = invoke(lambda: _uploader.upload(b"\x89PNG", "a.png", "image/png"))
finally:
    socket.getaddrinfo = _orig_getaddrinfo
    socket.socket.connect = _orig_connect

check_true(
    "SOCKET-SUCCESS-CASE-NO-EXC. 成功系呼び出しで例外が送出されない",
    _socket_exc1 is None,
)
check_true(
    "SOCKET-FAILURE-CASE-EXPECTED-EXC. 失敗系呼び出しでWordPressMediaUploadErrorが送出される"
    "（requests.postのConnectionErrorをupload()が正しく変換した結果であり、socket遮断とは無関係）",
    isinstance(_socket_exc2, WordPressMediaUploadError),
)
check(
    "SOCKET-NO-NETWORK. upload()はsocket.getaddrinfo／socket.socket.connectの"
    "いずれも呼び出さない（requests.postが完全にmock化されているため）",
    _socket_call_log,
    [],
)
check_true(
    "SOCKET-RESTORED. socket関数がpatch前の状態へ復元されている",
    socket.getaddrinfo is _orig_getaddrinfo and socket.socket.connect is _orig_connect,
)
print()

# =====================================================================
# NOIMPACT: v6.22.0 baseline commit固定によるRuntime Zero Diff
# =====================================================================

print("[NOIMPACT] Runtime Zero Diff（Release 6.22.0 baseline commit基準）")

# Release 6.22.0 の baseline commit（Release 6.21.0 完了時点。本Release開始時点）。
BASELINE_COMMIT = "578af6bdaeec23dd0c145a57384369ede433e3e4"

_git_version = subprocess.run(
    ["git", "--version"], cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=10
)
check("NOIMPACT-GIT-AVAILABLE. gitが利用できる（vacuous pass防止）", _git_version.returncode, 0)

# NOIMPACT-BASELINE-PINNED: 設計書↔実装の転記整合を確認する文書的検査（11.7.4節）
check(
    "NOIMPACT-BASELINE-PINNED. BASELINE_COMMITが設計書記録値と一致する",
    BASELINE_COMMIT,
    "578af6bdaeec23dd0c145a57384369ede433e3e4",
)

_baseline_proc = subprocess.run(
    ["git", "rev-parse", "--verify", f"{BASELINE_COMMIT}^{{commit}}"],
    cwd=str(PROJECT_ROOT),
    capture_output=True,
    text=True,
    timeout=30,
)
check(
    "NOIMPACT-BASELINE-RESOLVABLE. Release 6.22.0 baseline commitが解決できる（vacuous pass防止）",
    _baseline_proc.returncode,
    0,
)

# NOIMPACT-BASELINE-IS-ANCESTOR: baselineが現在の履歴上に存在することを保証する
_ancestor_proc = subprocess.run(
    ["git", "merge-base", "--is-ancestor", BASELINE_COMMIT, "HEAD"],
    cwd=str(PROJECT_ROOT),
    capture_output=True,
    timeout=30,
)
check(
    "NOIMPACT-BASELINE-IS-ANCESTOR. baseline commitがHEADの祖先である",
    _ancestor_proc.returncode,
    0,
)

# 設計書15.3節「変更禁止範囲」に対応する対象一覧（v6.21.0 _protected_pathsと同一の22パス）。
# DEF-6.23-9（v6.26.0）により、_protected_paths・_allowed_source_changes・
# _allowed_test_changes は tests/zero_diff_guard_registry.py（共有レジストリ）
# 側で一元管理する。本guard自身の値・判定結果はrefactor前と完全一致する
# （tests/test_e2e_v6_26_0_zero_diff_guard_registry_foundation.py で固定検証）。
import zero_diff_guard_registry as _guard_registry  # noqa: E402

_protected_paths = list(_guard_registry.PROTECTED_PATHS)

# 本Releaseが正当に変更する2ファイル（設計書14.1節・11.7.1節）
_allowed_source_changes = _guard_registry.allowed_source_changes_for("v6.22.0")

for _rel in _protected_paths:
    # vacuous pass防止その1：検査対象が作業ツリーに実在すること
    check_true(f"NOIMPACT-EXISTS[{_rel}]. 検査対象が作業ツリーに実在する", (PROJECT_ROOT / _rel).exists())
    # vacuous pass防止その2：baseline commit に追跡ファイルが実在すること
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
    # containment: changed ⊆ allowed（--relative でproject root相対POSIXパスを取得）
    _diff_proc = subprocess.run(
        ["git", "diff", "--name-only", "--relative", BASELINE_COMMIT, "--", _rel],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    _changed = {line.strip() for line in _diff_proc.stdout.splitlines() if line.strip()}
    _allowed = _allowed_source_changes.get(_rel, frozenset())
    check(
        f"NOIMPACT-SCOPE[{_rel}]. baseline commitからの差分がallow-listの範囲内である",
        sorted(_changed - _allowed),
        [],
    )
    # untracked補完：git diffが検出できないuntracked追加を別途検出する
    _status_proc = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", _rel],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    )
    _untracked = [
        line for line in _status_proc.stdout.splitlines() if line.startswith("??")
    ]
    check(f"NOIMPACT-NO-UNTRACKED[{_rel}]. untracked集合が空である", _untracked, [])

# coverage: allowed ⊆ changed（src/wordpress_mediaのみ。vacuous pass防止の本体）
_wp_diff_proc = subprocess.run(
    ["git", "diff", "--name-only", "--relative", BASELINE_COMMIT, "--", "src/wordpress_media"],
    cwd=str(PROJECT_ROOT),
    capture_output=True,
    text=True,
    timeout=30,
)
_wp_changed = {line.strip() for line in _wp_diff_proc.stdout.splitlines() if line.strip()}
_wp_allowed = _allowed_source_changes["src/wordpress_media"]
check(
    "NOIMPACT-SCOPE-COVERAGE[src/wordpress_media]. allow-listの2ファイルが両方とも実際に変更されている",
    sorted(_wp_allowed - _wp_changed),
    [],
)
check_true(
    "NOIMPACT-SCOPE-EXACT[src/wordpress_media]. containment(⊆)とcoverage(⊇)の両方が"
    "成立しequalityとなる",
    _wp_changed == _wp_allowed,
)

# 既存testsは、共有レジストリ（DEF-6.23-9）が本Release（v6.22.0）以降の
# window として合成する集合の範囲内以外に差分があってはならない（設計書11.7.4節）
_allowed_test_changes = set(_guard_registry.allowed_test_changes_for("v6.22.0"))
_tests_diff_proc = subprocess.run(
    ["git", "diff", "--name-only", BASELINE_COMMIT, "--", "tests"],
    cwd=str(PROJECT_ROOT),
    capture_output=True,
    text=True,
    timeout=30,
)
_changed_tests = {
    Path(line.strip().replace("\\", "/")).name
    for line in _tests_diff_proc.stdout.splitlines()
    if line.strip()
}
check(
    "NOIMPACT-TESTS-SCOPE. tests/の差分がallow-listの範囲内である"
    "（GR-7に従い許容件数はラベルへ埋め込まない）",
    sorted(_changed_tests - _allowed_test_changes),
    [],
)

# untracked補完（tests/）：git statusのpath正規化はPath(line[3:]).nameで行う
# （git status --porcelain は repo-root相対パスを返し --relative を持たないため）
_tests_status_proc = subprocess.run(
    ["git", "status", "--porcelain", "--untracked-files=all", "--", "tests"],
    cwd=str(PROJECT_ROOT),
    capture_output=True,
    text=True,
    timeout=30,
)
_untracked_tests = {
    Path(line[3:]).name
    for line in _tests_status_proc.stdout.splitlines()
    if line.startswith("??")
}
check(
    "NOIMPACT-NO-UNTRACKED-TESTS. tests/のuntracked集合がallow-listの範囲内である"
    "（GR-7に従い許容件数はラベルへ埋め込まない）",
    sorted(_untracked_tests - _allowed_test_changes),
    [],
)
print()

# =====================================================================
# COMPAT: v6.10〜v6.21各packageの既存Public API不変Contract
# =====================================================================

print("[COMPAT] v6.10〜v6.21 既存Public API不変Contract")

import ai_image_generation as _v610_pkg  # noqa: E402
import openai_image_generation as _v611_pkg  # noqa: E402
import generated_image_wordpress_media as _v612_pkg  # noqa: E402
import article_featured_media as _v613_pkg  # noqa: E402
import article_featured_media_orchestration as _v614_pkg  # noqa: E402
import image_generation_config as _v615_pkg  # noqa: E402
import generated_image_filename_policy as _v616_pkg  # noqa: E402
import article_image_prompt_construction as _v617_pkg  # noqa: E402
import article_featured_media_composition as _v618_pkg  # noqa: E402
import image_generation_fallback_policy as _v619_pkg  # noqa: E402
import article_featured_media_runtime as _v620_pkg  # noqa: E402

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
check("COMPAT-V613. article_featured_media.__all__が不変", sorted(_v613_pkg.__all__), sorted(["bind_featured_media"]))
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
    "COMPAT-V620. article_featured_media_runtime.__all__が既存3symbol＋"
    "v6.25.0のFeaturedMediaFailureObservationの4symbolである",
    sorted(_v620_pkg.__all__),
    sorted([
        "ArticleFeaturedMediaRuntimeStatus",
        "ArticleFeaturedMediaRuntimeResult",
        "ArticleFeaturedMediaRuntime",
        "FeaturedMediaFailureObservation",
    ]),
)
check(
    "COMPAT-V619. image_generation_fallback_policy.__all__が既存4symbol＋"
    "v6.25.0のextract_safe_reasonの5symbolである",
    sorted(_v619_pkg.__all__),
    sorted([
        "ImageGenerationFailureCategory",
        "ImageGenerationFallbackAction",
        "ImageGenerationFallbackDecision",
        "decide_image_generation_fallback",
        "extract_safe_reason",
    ]),
)

check(
    "COMPAT-MEDIAUPLOADRESULT. MediaUploadResultのフィールド構成が不変",
    [f.name for f in __import__("dataclasses").fields(MediaUploadResult)],
    ["media_id", "source_url", "mime_type"],
)

check(
    "COMPAT-UPLOAD-SIGNATURE. upload()のsignatureが不変",
    list(inspect.signature(WordPressMediaUploader.upload).parameters.keys()),
    ["self", "image_bytes", "filename", "mime_type"],
)

check_true(
    "COMPAT-BASE-CLASS. WordPressMediaUploadErrorの基底クラスがRuntimeErrorのまま",
    WordPressMediaUploadError.__bases__ == (RuntimeError,),
)
print()

# =====================================================================
# COMPAT-DEP: v6.9 DEP-1〜4・ENV-4・ENV-5 guard が引き続きPASSすることの二重確認
# =====================================================================

print("[COMPAT-DEP] v6.9 DEP-1〜4・ENV-4・ENV-5 guard 継続PASS確認")

_init_source = _INIT_FILE.read_text(encoding="utf-8")
_combined_source = _uploader_source + _init_source

_DEP2_FORBIDDEN = [
    "requests.get",
    "requests.put",
    "requests.patch(",
    "requests.delete",
    "requests.request(",
    "urllib",
    "http.client",
    "socket",
    "open(",
    "write_text",
    "write_bytes",
    "subprocess",
]
for _token in _DEP2_FORBIDDEN:
    check_not_contains(f"COMPAT-DEP-2[{_token}]. 禁止文字列が含まれない", _combined_source, _token)
check_contains("COMPAT-DEP-2[requests.post(]. 許可I/Oは存在する", _combined_source, "requests.post(")

check_not_contains("COMPAT-DEP-3a. print(非使用", _combined_source, "print(")
check_not_contains("COMPAT-DEP-3b. logging非使用", _combined_source, "logging")
check_not_contains("COMPAT-DEP-4. featured_media非出現", _combined_source, "featured_media")

check_not_contains("COMPAT-ENV-5a. load_dotenv非使用", _uploader_source, "load_dotenv")
check_not_contains("COMPAT-ENV-5b. dotenv非使用", _uploader_source, "dotenv")

import re as _re_mod

_env_var_literal_refs = set(_re_mod.findall(r'"(WP_[A-Z_]+)"', _uploader_source))
check(
    "COMPAT-ENV-4. 参照する環境変数はWP_SITE_URL／WP_USERNAME／WP_APP_PASSWORDのみ",
    _env_var_literal_refs,
    {"WP_SITE_URL", "WP_USERNAME", "WP_APP_PASSWORD"},
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
