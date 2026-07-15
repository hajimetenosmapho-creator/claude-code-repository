"""
E2E テスト: v6.9.0 WordPress Media Upload Foundation

Source of Truth:
    docs/design/wordpress_media_upload_foundation.md（Design Freeze）
    Test Design（Test Review 3 Approved、48 Scenario / 115 Case / 約215〜250 Assertions）

本テストはWordPress Media REST API (POST /wp-json/wp/v2/media) への実通信を一切行わない。
requests.post は unittest.mock.patch でFake化する（Patch target:
wordpress_media.wordpress_media_uploader.requests.post）。

Scenario構成（48 Scenario）:
    Public Model／Package API: PM-1〜PM-4（4）
    Constructor: CTOR-1〜CTOR-5（5）
    from_env: ENV-1〜ENV-5（5）
    image_bytes: IB-1〜IB-2（2）
    filename: FN-1〜FN-4（4）
    mime_type: MT-1〜MT-4（4）
    HTTP Request／Success: HTTP-1〜HTTP-4（4、Mock観測可能性はHTTP-1へ統合）
    Success Response Failure: SRF-1〜SRF-6（6）
    RequestException: REX-1〜REX-2（2）
    Non-2xx／Safe Error: ERR-1〜ERR-8（8）
    Dependency／Scope／Side Effect: DEP-1〜DEP-4（4）

Compatibility／Regressionは本ファイルのScenario数に含まない
（Release Review ChecklistおよびRegression Execution Planとして別途運用する）。

実行方法:
    cd projects/03_game_content_ai
    python tests/test_e2e_v6_9_0_wordpress_media_upload_foundation.py
"""
import ast
import sys
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from unittest.mock import MagicMock, patch

import requests

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ─── テスト用ユーティリティ ───

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


import os as _os


@contextmanager
def patched_environ(updates: dict, removals: tuple = ()):
    original = dict(_os.environ)
    try:
        for name in removals:
            _os.environ.pop(name, None)
        for name, value in updates.items():
            _os.environ[name] = value
        yield
    finally:
        _os.environ.clear()
        _os.environ.update(original)


print("=" * 60)
print("v6.9.0 WordPress Media Upload Foundation E2E テスト")
print("=" * 60)
print()

import wordpress_media
from wordpress_media import (
    MediaUploadResult,
    WordPressMediaUploadError,
    WordPressMediaUploader,
)

_PATCH_TARGET = "wordpress_media.wordpress_media_uploader.requests.post"

_uploader = WordPressMediaUploader(
    site_url="https://example.com", username="user", app_password="pass"
)

_SECRET_USERNAME = "secretUser123"
_SECRET_APP_PASSWORD = "secretPass456"
_SECRET_IMAGE_BYTES = b"SECRETBYTESMARKER"
_RAW_TEXT_MARKER = "raw-response-text-marker-should-not-leak"
_RAW_CONTENT_MARKER_TEXT = "raw-response-content-marker-should-not-leak"
_RAW_CONTENT_MARKER = _RAW_CONTENT_MARKER_TEXT.encode()

_secret_uploader = WordPressMediaUploader(
    site_url="https://example.com",
    username=_SECRET_USERNAME,
    app_password=_SECRET_APP_PASSWORD,
)


def _make_mock_response(status_code, json_value=None, json_side_effect=None):
    resp = MagicMock()
    resp.status_code = status_code
    if json_side_effect is not None:
        resp.json.side_effect = json_side_effect
    else:
        resp.json.return_value = json_value
    resp.text = _RAW_TEXT_MARKER
    resp.content = _RAW_CONTENT_MARKER
    return resp


def _check_security_common(label: str, exc: Exception):
    msg = str(exc)
    check_not_contains(f"{label}: username非露出", msg, _SECRET_USERNAME)
    check_not_contains(f"{label}: app_password非露出", msg, _SECRET_APP_PASSWORD)
    check_not_contains(f"{label}: image_bytes非露出", msg, "SECRETBYTESMARKER")
    check_not_contains(f"{label}: response.text非露出", msg, _RAW_TEXT_MARKER)
    check_not_contains(f"{label}: response.content非露出", msg, _RAW_CONTENT_MARKER_TEXT)


_success_response = MagicMock()
_success_response.status_code = 201
_success_response.json.return_value = {
    "id": 1,
    "source_url": "https://example.com/wp-content/uploads/x.png",
    "mime_type": "image/png",
}

# =====================================================================
# Public Model／Package API
# =====================================================================

print("[PM-1] MediaUploadResult Structure Contract")
_pm1_result = MediaUploadResult(
    media_id=1, source_url="https://example.com/a.png", mime_type="image/png"
)
check("PM-1a. media_id保持", _pm1_result.media_id, 1)
check("PM-1a. source_url保持", _pm1_result.source_url, "https://example.com/a.png")
check("PM-1a. mime_type保持", _pm1_result.mime_type, "image/png")

_pm1_field_names = [f.name for f in fields(MediaUploadResult)]
check("PM-1b. フィールド数は3", len(_pm1_field_names), 3)
check(
    "PM-1b. フィールド順序",
    _pm1_field_names,
    ["media_id", "source_url", "mime_type"],
)

try:
    _pm1_result.media_id = 999
    _pm1_frozen_raised = False
except FrozenInstanceError:
    _pm1_frozen_raised = True
check_true("PM-1c. frozen dataclass（FrozenInstanceError）", _pm1_frozen_raised)

_pm1_public_attrs = sorted(
    name for name in dir(_pm1_result) if not name.startswith("_")
)
check(
    "PM-1d. 追加のPublic属性／Methodなし",
    _pm1_public_attrs,
    sorted(["media_id", "source_url", "mime_type"]),
)
print()

print("[PM-2] MediaUploadResult Equality Contract")
_pm2_a = MediaUploadResult(1, "u", "image/png")
_pm2_b = MediaUploadResult(1, "u", "image/png")
_pm2_c = MediaUploadResult(2, "u", "image/png")
check_true("PM-2a. 同一値は等価", _pm2_a == _pm2_b)
check_false("PM-2b. 異なる値は非等価", _pm2_a == _pm2_c)
print()

print("[PM-3] Package root Public API Contract")
check_true("PM-3a. MediaUploadResult がpackage rootから公開", "MediaUploadResult" in dir(wordpress_media))
check_true(
    "PM-3a. WordPressMediaUploadError がpackage rootから公開",
    "WordPressMediaUploadError" in dir(wordpress_media),
)
check_true(
    "PM-3a. WordPressMediaUploader がpackage rootから公開",
    "WordPressMediaUploader" in dir(wordpress_media),
)
check(
    "PM-3b. __all__完全一致",
    sorted(wordpress_media.__all__),
    sorted(["MediaUploadResult", "WordPressMediaUploadError", "WordPressMediaUploader"]),
)
print()

print("[PM-4] Internal Module Non-Exposure Contract")
check_false("PM-4a. media_upload_resultは__all__に含まれない", "media_upload_result" in wordpress_media.__all__)
check_false(
    "PM-4b. wordpress_media_uploaderは__all__に含まれない",
    "wordpress_media_uploader" in wordpress_media.__all__,
)
print()

# =====================================================================
# Constructor
# =====================================================================

print("[CTOR-1] Constructor正常構築／正規化Contract")
_ctor1a = WordPressMediaUploader(site_url="https://example.com", username="user", app_password="pass")
check("CTOR-1a. site_url保持", _ctor1a.site_url, "https://example.com")
check("CTOR-1a. username保持", _ctor1a.username, "user")
check("CTOR-1a. app_password保持", _ctor1a.app_password, "pass")

_ctor1b = WordPressMediaUploader(site_url="https://example.com/", username="user", app_password="pass")
check("CTOR-1b. 末尾スラッシュ除去", _ctor1b.site_url, "https://example.com")

_ctor1c = WordPressMediaUploader(site_url="  https://example.com  ", username="user", app_password="pass")
check("CTOR-1c. 前後空白除去", _ctor1c.site_url, "https://example.com")

_ctor1d = WordPressMediaUploader(site_url="https://example.com", username=" user ", app_password=" pass ")
check("CTOR-1d. username非自動strip", _ctor1d.username, " user ")
check("CTOR-1d. app_password非自動strip", _ctor1d.app_password, " pass ")
print()

print("[CTOR-2] Constructor型検証Contract")
for _field, _kwargs in [
    ("site_url", dict(site_url=123, username=_SECRET_USERNAME, app_password=_SECRET_APP_PASSWORD)),
    ("username", dict(site_url="https://example.com", username=123, app_password=_SECRET_APP_PASSWORD)),
    ("app_password", dict(site_url="https://example.com", username=_SECRET_USERNAME, app_password=123)),
]:
    try:
        WordPressMediaUploader(**_kwargs)
        _ctor2_raised = None
    except ValueError as exc:
        _ctor2_raised = exc
    check_true(f"CTOR-2 {_field}非str: ValueError", isinstance(_ctor2_raised, ValueError))
    check_contains(f"CTOR-2 {_field}非str: フィールド名を含む", str(_ctor2_raised), _field)
    check_not_contains(f"CTOR-2 {_field}非str: username値非露出", str(_ctor2_raised), _SECRET_USERNAME)
    check_not_contains(f"CTOR-2 {_field}非str: app_password値非露出", str(_ctor2_raised), _SECRET_APP_PASSWORD)
print()

print("[CTOR-3] Constructor空文字検証Contract")
for _field, _kwargs in [
    ("site_url", dict(site_url="", username=_SECRET_USERNAME, app_password=_SECRET_APP_PASSWORD)),
    ("username", dict(site_url="https://example.com", username="", app_password=_SECRET_APP_PASSWORD)),
    ("app_password", dict(site_url="https://example.com", username=_SECRET_USERNAME, app_password="")),
]:
    try:
        WordPressMediaUploader(**_kwargs)
        _ctor3_raised = None
    except ValueError as exc:
        _ctor3_raised = exc
    check_true(f"CTOR-3 {_field}空文字: ValueError", isinstance(_ctor3_raised, ValueError))
    check_contains(f"CTOR-3 {_field}空文字: フィールド名を含む", str(_ctor3_raised), _field)
print()

print("[CTOR-4] Constructor空白のみ検証Contract")
for _field, _kwargs in [
    ("site_url", dict(site_url="   ", username=_SECRET_USERNAME, app_password=_SECRET_APP_PASSWORD)),
    ("username", dict(site_url="https://example.com", username="   ", app_password=_SECRET_APP_PASSWORD)),
    ("app_password", dict(site_url="https://example.com", username=_SECRET_USERNAME, app_password="   ")),
]:
    try:
        WordPressMediaUploader(**_kwargs)
        _ctor4_raised = None
    except ValueError as exc:
        _ctor4_raised = exc
    check_true(f"CTOR-4 {_field}空白のみ: ValueError", isinstance(_ctor4_raised, ValueError))
print()

print("[CTOR-5] Constructor正規化後空Contract")
try:
    WordPressMediaUploader(site_url="///", username="user", app_password="pass")
    _ctor5_raised = None
except ValueError as exc:
    _ctor5_raised = exc
check_true("CTOR-5. 正規化後site_urlが空でValueError", isinstance(_ctor5_raised, ValueError))
print()

# =====================================================================
# from_env
# =====================================================================

print("[ENV-1] from_env正常構築Contract")
with patched_environ(
    {"WP_SITE_URL": "https://example.com", "WP_USERNAME": "envuser", "WP_APP_PASSWORD": "envpass"}
):
    _env1 = WordPressMediaUploader.from_env()
check("ENV-1a. site_url", _env1.site_url, "https://example.com")
check("ENV-1a. username", _env1.username, "envuser")
check("ENV-1a. app_password", _env1.app_password, "envpass")
print()

print("[ENV-2] from_env不足変数検出Contract")
_env2_base = {"WP_SITE_URL": "https://example.com", "WP_USERNAME": "envuser", "WP_APP_PASSWORD": "supersecretpw123"}
for _missing_name in ("WP_SITE_URL", "WP_USERNAME", "WP_APP_PASSWORD"):
    _updates = {k: v for k, v in _env2_base.items() if k != _missing_name}
    with patched_environ(_updates, removals=(_missing_name,)):
        try:
            WordPressMediaUploader.from_env()
            _env2_raised = None
        except ValueError as exc:
            _env2_raised = exc
    check_true(f"ENV-2 {_missing_name}不足: ValueError", isinstance(_env2_raised, ValueError))
    check_contains(f"ENV-2 {_missing_name}不足: 変数名を含む", str(_env2_raised), _missing_name)
    check_not_contains(f"ENV-2 {_missing_name}不足: 値非露出", str(_env2_raised), "supersecretpw123")

with patched_environ({"WP_SITE_URL": "https://example.com"}, removals=("WP_USERNAME", "WP_APP_PASSWORD")):
    try:
        WordPressMediaUploader.from_env()
        _env2_multi_raised = None
    except ValueError as exc:
        _env2_multi_raised = exc
check_true("ENV-2 複数不足: ValueError", isinstance(_env2_multi_raised, ValueError))
check_contains("ENV-2 複数不足: WP_USERNAMEを含む", str(_env2_multi_raised), "WP_USERNAME")
check_contains("ENV-2 複数不足: WP_APP_PASSWORDを含む", str(_env2_multi_raised), "WP_APP_PASSWORD")
print()

print("[ENV-3] from_env空／空白のみ検出Contract")
with patched_environ(
    {"WP_SITE_URL": "https://example.com", "WP_USERNAME": "", "WP_APP_PASSWORD": "supersecretpw123"}
):
    try:
        WordPressMediaUploader.from_env()
        _env3a_raised = None
    except ValueError as exc:
        _env3a_raised = exc
check_true("ENV-3 空文字: ValueError", isinstance(_env3a_raised, ValueError))
check_not_contains("ENV-3 空文字: 値非露出", str(_env3a_raised), "supersecretpw123")

with patched_environ(
    {"WP_SITE_URL": "https://example.com", "WP_USERNAME": "envuser", "WP_APP_PASSWORD": "   "}
):
    try:
        WordPressMediaUploader.from_env()
        _env3b_raised = None
    except ValueError as exc:
        _env3b_raised = exc
check_true("ENV-3 空白のみ: ValueError", isinstance(_env3b_raised, ValueError))
print()

_uploader_source = Path(PROJECT_ROOT / "src" / "wordpress_media" / "wordpress_media_uploader.py").read_text(
    encoding="utf-8"
)
_init_source = Path(PROJECT_ROOT / "src" / "wordpress_media" / "__init__.py").read_text(encoding="utf-8")
_combined_source = _uploader_source + _init_source

print("[ENV-4] from_env新規環境変数非参照Contract")
import re as _re

_env_var_literal_refs = set(_re.findall(r'"(WP_[A-Z_]+)"', _uploader_source))
check(
    "ENV-4. 参照する環境変数はWP_SITE_URL／WP_USERNAME／WP_APP_PASSWORDのみ",
    _env_var_literal_refs,
    {"WP_SITE_URL", "WP_USERNAME", "WP_APP_PASSWORD"},
)
print()

print("[ENV-5] from_env `.env`非読込Contract")
check_not_contains("ENV-5a. load_dotenv非使用", _uploader_source, "load_dotenv")
check_not_contains("ENV-5b. python-dotenv非使用", _uploader_source, "dotenv")
print()

# =====================================================================
# image_bytes
# =====================================================================

print("[IB-1] image_bytes正常受理Contract")
with patch(_PATCH_TARGET, return_value=_success_response) as _ib1_mock:
    _ib1_result = _uploader.upload(image_bytes=b"\x89PNG\r\n", filename="test.png", mime_type="image/png")
check_true("IB-1a. 正常bytesで例外なく成功", isinstance(_ib1_result, MediaUploadResult))
check_true("IB-1b. requests.postが呼ばれた", _ib1_mock.called)
print()

print("[IB-2] image_bytes型／空拒否Contract")
for _label, _bad_value in [
    ("empty bytes", b""),
    ("str", "not-bytes"),
    ("bytearray", bytearray(b"x")),
    ("memoryview", memoryview(b"x")),
    ("None", None),
]:
    with patch(_PATCH_TARGET) as _ib2_mock:
        try:
            _uploader.upload(image_bytes=_bad_value, filename="test.png", mime_type="image/png")
            _ib2_raised = None
        except ValueError as exc:
            _ib2_raised = exc
        check_true(f"IB-2 {_label}: ValueError", isinstance(_ib2_raised, ValueError))
        check_false(f"IB-2 {_label}: HTTP非呼出", _ib2_mock.called)
print()

# =====================================================================
# filename
# =====================================================================

print("[FN-1] filename正常受理Contract")
for _label, _filename in [
    ("normal ascii", "article-image.png"),
    ("digit start", "1image.png"),
    ("hyphen/underscore/dot", "game_news-001.v2.png"),
]:
    with patch(_PATCH_TARGET, return_value=_success_response):
        try:
            _uploader.upload(image_bytes=b"data", filename=_filename, mime_type="image/png")
            _fn1_ok = True
        except ValueError:
            _fn1_ok = False
    check_true(f"FN-1 {_label}: 検証通過", _fn1_ok)
print()

print("[FN-2] filenameパス／セパレータ拒否Contract")
for _label, _filename in [
    ("slash", "folder/image.png"),
    ("backslash", "folder\\image.png"),
    ("path traversal", "../image.png"),
]:
    with patch(_PATCH_TARGET) as _fn2_mock:
        try:
            _uploader.upload(image_bytes=b"data", filename=_filename, mime_type="image/png")
            _fn2_raised = None
        except ValueError as exc:
            _fn2_raised = exc
        check_true(f"FN-2 {_label}: ValueError", isinstance(_fn2_raised, ValueError))
        check_false(f"FN-2 {_label}: HTTP非呼出", _fn2_mock.called)
print()

print("[FN-3] filenameヘッダーインジェクション拒否Contract")
for _label, _filename in [
    ("double quote", '"image".png'),
    ("CR", "image\rInjected.png"),
    ("LF", "image\nInjected.png"),
    ("NUL", "image\x00.png"),
]:
    with patch(_PATCH_TARGET) as _fn3_mock:
        try:
            _uploader.upload(image_bytes=b"data", filename=_filename, mime_type="image/png")
            _fn3_raised = None
        except ValueError as exc:
            _fn3_raised = exc
        check_true(f"FN-3 {_label}: ValueError", isinstance(_fn3_raised, ValueError))
        check_false(f"FN-3 {_label}: HTTP非呼出", _fn3_mock.called)
print()

print("[FN-4] filename文字種／先頭文字拒否Contract")
for _label, _filename in [
    ("unicode", "画像.png"),
    ("leading underscore", "_hidden.png"),
    ("leading hyphen", "-image.png"),
    ("empty", ""),
    ("whitespace only", "   "),
]:
    with patch(_PATCH_TARGET) as _fn4_mock:
        try:
            _uploader.upload(image_bytes=b"data", filename=_filename, mime_type="image/png")
            _fn4_raised = None
        except ValueError as exc:
            _fn4_raised = exc
        check_true(f"FN-4 {_label}: ValueError", isinstance(_fn4_raised, ValueError))
        check_false(f"FN-4 {_label}: HTTP非呼出", _fn4_mock.called)
print()

# =====================================================================
# mime_type
# =====================================================================

print("[MT-1] mime_type正常受理Contract")
with patch(_PATCH_TARGET, return_value=_success_response):
    try:
        _uploader.upload(image_bytes=b"data", filename="test.png", mime_type="image/png")
        _mt1_ok = True
    except ValueError:
        _mt1_ok = False
check_true("MT-1. 正常値で検証通過", _mt1_ok)
print()

print("[MT-2] mime_type空／非str拒否Contract")
for _label, _mime in [
    ("empty", ""),
    ("whitespace only", "   "),
    ("non-str", 123),
]:
    with patch(_PATCH_TARGET) as _mt2_mock:
        try:
            _uploader.upload(image_bytes=b"data", filename="test.png", mime_type=_mime)
            _mt2_raised = None
        except ValueError as exc:
            _mt2_raised = exc
        check_true(f"MT-2 {_label}: ValueError", isinstance(_mt2_raised, ValueError))
        check_false(f"MT-2 {_label}: HTTP非呼出", _mt2_mock.called)
print()

print("[MT-3] mime_type前後空白拒否Contract")
for _label, _mime in [
    ("leading space", " image/png"),
    ("trailing space", "image/png "),
]:
    with patch(_PATCH_TARGET) as _mt3_mock:
        try:
            _uploader.upload(image_bytes=b"data", filename="test.png", mime_type=_mime)
            _mt3_raised = None
        except ValueError as exc:
            _mt3_raised = exc
        check_true(f"MT-3 {_label}: ValueError", isinstance(_mt3_raised, ValueError))
        check_false(f"MT-3 {_label}: HTTP非呼出", _mt3_mock.called)
print()

print("[MT-4] mime_type制御文字拒否Contract")
for _label, _mime in [
    ("CR", "image/png\rInjected"),
    ("LF", "image/png\nInjected"),
    ("tab", "image/png\tInjected"),
    ("NUL", "image/png\x00Injected"),
    ("DEL", "image/png\x7fInjected"),
]:
    with patch(_PATCH_TARGET) as _mt4_mock:
        try:
            _uploader.upload(image_bytes=b"data", filename="test.png", mime_type=_mime)
            _mt4_raised = None
        except ValueError as exc:
            _mt4_raised = exc
        check_true(f"MT-4 {_label}: ValueError", isinstance(_mt4_raised, ValueError))
        check_false(f"MT-4 {_label}: HTTP非呼出", _mt4_mock.called)
print()

# =====================================================================
# HTTP Request／Success
# =====================================================================

print("[HTTP-1] HTTP Request Contract（正常201、Mock観測可能性統合）")
_http1_response = MagicMock()
_http1_response.status_code = 201
_http1_response.json.return_value = {
    "id": 42,
    "source_url": "https://example.com/wp-content/uploads/x.png",
    "mime_type": "image/png",
}
with patch(_PATCH_TARGET, return_value=_http1_response) as _http1_mock:
    _http1_result = _uploader.upload(image_bytes=b"binarydata", filename="upload-test.png", mime_type="image/png")

check_true("HTTP-1a. requests.postがPatch経由で呼ばれた（実通信なし）", _http1_mock.called)
_http1_args, _http1_kwargs = _http1_mock.call_args
check("HTTP-1b. Endpoint完全一致", _http1_args[0], "https://example.com/wp-json/wp/v2/media")
check("HTTP-1c. data=image_bytes", _http1_kwargs.get("data"), b"binarydata")
check_false("HTTP-1d. json未使用", "json" in _http1_kwargs)
check_false("HTTP-1e. files未使用", "files" in _http1_kwargs)
check("HTTP-1f. Content-Type一致", _http1_kwargs["headers"]["Content-Type"], "image/png")
check(
    "HTTP-1g. Content-Disposition一致",
    _http1_kwargs["headers"]["Content-Disposition"],
    'attachment; filename="upload-test.png"',
)
check("HTTP-1h. auth一致", _http1_kwargs["auth"], ("user", "pass"))
check("HTTP-1i. timeout=30", _http1_kwargs["timeout"], 30)
check_true("HTTP-1j. MediaUploadResult生成", isinstance(_http1_result, MediaUploadResult))
print()

print("[HTTP-2] HTTP成功ステータス境界Contract")
for _status in (200, 201, 299):
    _http2_resp = MagicMock()
    _http2_resp.status_code = _status
    _http2_resp.json.return_value = {"id": 1, "source_url": None, "mime_type": None}
    with patch(_PATCH_TARGET, return_value=_http2_resp):
        try:
            _uploader.upload(image_bytes=b"d", filename="a.png", mime_type="image/png")
            _http2_ok = True
        except WordPressMediaUploadError:
            _http2_ok = False
    check_true(f"HTTP-2 status={_status}: 成功", _http2_ok)
print()

print("[HTTP-3] 成功レスポンスField抽出Contract")
for _label, _source_url, _mime in [
    ("source_url str", "https://example.com/a.png", "image/png"),
    ("source_url None", None, "image/png"),
    ("mime_type str", "https://example.com/a.png", "image/webp"),
    ("mime_type None", "https://example.com/a.png", None),
]:
    _http3_resp = MagicMock()
    _http3_resp.status_code = 200
    _http3_resp.json.return_value = {"id": 7, "source_url": _source_url, "mime_type": _mime}
    with patch(_PATCH_TARGET, return_value=_http3_resp):
        _http3_result = _uploader.upload(image_bytes=b"d", filename="a.png", mime_type="image/png")
    check(f"HTTP-3 {_label}: source_url", _http3_result.source_url, _source_url)
    check(f"HTTP-3 {_label}: mime_type", _http3_result.mime_type, _mime)
print()

print("[HTTP-4] 成功レスポンス未知Field許容Contract")
_http4_resp = MagicMock()
_http4_resp.status_code = 200
_http4_resp.json.return_value = {
    "id": 9,
    "source_url": "https://example.com/a.png",
    "mime_type": "image/png",
    "guid": {"rendered": "x"},
    "title": {"rendered": "y"},
}
with patch(_PATCH_TARGET, return_value=_http4_resp):
    _http4_result = _uploader.upload(image_bytes=b"d", filename="a.png", mime_type="image/png")
check("HTTP-4a. media_id抽出", _http4_result.media_id, 9)
check_true("HTTP-4b. 未知fieldを無視して成功", isinstance(_http4_result, MediaUploadResult))
print()

# =====================================================================
# Success Response Failure
# =====================================================================

print("[SRF-1] JSON Decode Failure Contract")
_srf1_resp = _make_mock_response(200, json_side_effect=ValueError("invalid json"))
with patch(_PATCH_TARGET, return_value=_srf1_resp):
    try:
        _secret_uploader.upload(image_bytes=_SECRET_IMAGE_BYTES, filename="a.png", mime_type="image/png")
        _srf1_raised = None
    except WordPressMediaUploadError as exc:
        _srf1_raised = exc
check_true("SRF-1a. WordPressMediaUploadError", isinstance(_srf1_raised, WordPressMediaUploadError))
_check_security_common("SRF-1", _srf1_raised)
print()

print("[SRF-2] 非Object JSON拒否Contract")
for _label, _json_value in [("list", [1, 2, 3]), ("str", "ok"), ("int", 123), ("None", None)]:
    _srf2_resp = _make_mock_response(200, json_value=_json_value)
    with patch(_PATCH_TARGET, return_value=_srf2_resp):
        try:
            _secret_uploader.upload(image_bytes=_SECRET_IMAGE_BYTES, filename="a.png", mime_type="image/png")
            _srf2_raised = None
        except WordPressMediaUploadError as exc:
            _srf2_raised = exc
    check_true(f"SRF-2 {_label}: WordPressMediaUploadError", isinstance(_srf2_raised, WordPressMediaUploadError))
    _check_security_common(f"SRF-2 {_label}", _srf2_raised)
print()

print("[SRF-3] id Field契約違反Contract")
for _label, _data in [
    ("missing", {"source_url": "u", "mime_type": "m"}),
    ("bool", {"id": True, "source_url": "u", "mime_type": "m"}),
    ("str", {"id": "123", "source_url": "u", "mime_type": "m"}),
    ("float", {"id": 123.0, "source_url": "u", "mime_type": "m"}),
]:
    _srf3_resp = _make_mock_response(200, json_value=_data)
    with patch(_PATCH_TARGET, return_value=_srf3_resp):
        try:
            _secret_uploader.upload(image_bytes=_SECRET_IMAGE_BYTES, filename="a.png", mime_type="image/png")
            _srf3_raised = None
        except WordPressMediaUploadError as exc:
            _srf3_raised = exc
    check_true(f"SRF-3 {_label}: WordPressMediaUploadError", isinstance(_srf3_raised, WordPressMediaUploadError))
    _check_security_common(f"SRF-3 {_label}", _srf3_raised)
print()

print("[SRF-4] id範囲違反Contract")
for _label, _id_value in [("zero", 0), ("negative", -1)]:
    _srf4_resp = _make_mock_response(200, json_value={"id": _id_value, "source_url": "u", "mime_type": "m"})
    with patch(_PATCH_TARGET, return_value=_srf4_resp):
        try:
            _secret_uploader.upload(image_bytes=_SECRET_IMAGE_BYTES, filename="a.png", mime_type="image/png")
            _srf4_raised = None
        except WordPressMediaUploadError as exc:
            _srf4_raised = exc
    check_true(f"SRF-4 {_label}: WordPressMediaUploadError", isinstance(_srf4_raised, WordPressMediaUploadError))
    _check_security_common(f"SRF-4 {_label}", _srf4_raised)
print()

print("[SRF-5] source_url Field契約違反Contract")
for _label, _data in [
    ("missing", {"id": 1, "mime_type": "m"}),
    ("wrong type", {"id": 1, "source_url": 123, "mime_type": "m"}),
]:
    _srf5_resp = _make_mock_response(200, json_value=_data)
    with patch(_PATCH_TARGET, return_value=_srf5_resp):
        try:
            _secret_uploader.upload(image_bytes=_SECRET_IMAGE_BYTES, filename="a.png", mime_type="image/png")
            _srf5_raised = None
        except WordPressMediaUploadError as exc:
            _srf5_raised = exc
    check_true(f"SRF-5 {_label}: WordPressMediaUploadError", isinstance(_srf5_raised, WordPressMediaUploadError))
    _check_security_common(f"SRF-5 {_label}", _srf5_raised)
print()

print("[SRF-6] mime_type Field契約違反Contract")
for _label, _data in [
    ("missing", {"id": 1, "source_url": "u"}),
    ("wrong type", {"id": 1, "source_url": "u", "mime_type": 123}),
]:
    _srf6_resp = _make_mock_response(200, json_value=_data)
    with patch(_PATCH_TARGET, return_value=_srf6_resp):
        try:
            _secret_uploader.upload(image_bytes=_SECRET_IMAGE_BYTES, filename="a.png", mime_type="image/png")
            _srf6_raised = None
        except WordPressMediaUploadError as exc:
            _srf6_raised = exc
    check_true(f"SRF-6 {_label}: WordPressMediaUploadError", isinstance(_srf6_raised, WordPressMediaUploadError))
    _check_security_common(f"SRF-6 {_label}", _srf6_raised)
print()

# =====================================================================
# RequestException
# =====================================================================

print("[REX-1] RequestException変換Contract")
for _label, _exc_instance in [
    ("ConnectionError", requests.ConnectionError("boom-connection")),
    ("Timeout", requests.Timeout("boom-timeout")),
    ("RequestException", requests.RequestException("boom-generic")),
]:
    with patch(_PATCH_TARGET, side_effect=_exc_instance):
        try:
            _secret_uploader.upload(image_bytes=_SECRET_IMAGE_BYTES, filename="a.png", mime_type="image/png")
            _rex1_raised = None
        except WordPressMediaUploadError as exc:
            _rex1_raised = exc
    check_true(f"REX-1 {_label}: WordPressMediaUploadError", isinstance(_rex1_raised, WordPressMediaUploadError))
    check(f"REX-1 {_label}: 固定Message", str(_rex1_raised), "WordPress Media APIへの通信に失敗しました")
    check_not_contains(f"REX-1 {_label}: 元例外文言非連結", str(_rex1_raised), str(_exc_instance))
    check_true(f"REX-1 {_label}: 例外チェーン保持", _rex1_raised.__cause__ is _exc_instance)
print()

print("[REX-2] RequestException秘密値非露出Contract")
for _label, _exc_instance in [
    ("ConnectionError", requests.ConnectionError("boom-connection")),
    ("Timeout", requests.Timeout("boom-timeout")),
    ("RequestException", requests.RequestException("boom-generic")),
]:
    with patch(_PATCH_TARGET, side_effect=_exc_instance):
        try:
            _secret_uploader.upload(image_bytes=_SECRET_IMAGE_BYTES, filename="a.png", mime_type="image/png")
            _rex2_raised = None
        except WordPressMediaUploadError as exc:
            _rex2_raised = exc
    _check_security_common(f"REX-2 {_label}", _rex2_raised)
print()

# =====================================================================
# Non-2xx／Safe Error
# =====================================================================

print("[ERR-1] Non-2xxステータス検知Contract")
for _status in (199, 300, 400, 401, 403, 500):
    _err1_resp = _make_mock_response(_status, json_value={})
    with patch(_PATCH_TARGET, return_value=_err1_resp):
        try:
            _secret_uploader.upload(image_bytes=_SECRET_IMAGE_BYTES, filename="a.png", mime_type="image/png")
            _err1_raised = None
        except WordPressMediaUploadError as exc:
            _err1_raised = exc
    check_true(f"ERR-1 status={_status}: WordPressMediaUploadError", isinstance(_err1_raised, WordPressMediaUploadError))
    check_contains(f"ERR-1 status={_status}: HTTP statusを含む", str(_err1_raised), str(_status))
print()

print("[ERR-2] Safe Field個別採用Contract")
for _label, _json_value, _expect_code, _expect_message in [
    ("code only", {"code": "rest_upload_no_data"}, True, False),
    ("message only", {"message": "No data supplied."}, False, True),
    ("both", {"code": "rest_upload_no_data", "message": "No data supplied."}, True, True),
    ("neither", {"other": "x"}, False, False),
]:
    _err2_resp = _make_mock_response(400, json_value=_json_value)
    with patch(_PATCH_TARGET, return_value=_err2_resp):
        try:
            _secret_uploader.upload(image_bytes=_SECRET_IMAGE_BYTES, filename="a.png", mime_type="image/png")
            _err2_raised = None
        except WordPressMediaUploadError as exc:
            _err2_raised = exc
    _err2_msg = str(_err2_raised)
    if _expect_code:
        check_contains(f"ERR-2 {_label}: codeを含む", _err2_msg, "rest_upload_no_data")
    else:
        check_not_contains(f"ERR-2 {_label}: codeを含まない", _err2_msg, "rest_upload_no_data")
    if _expect_message:
        check_contains(f"ERR-2 {_label}: messageを含む", _err2_msg, "No data supplied.")
    else:
        check_not_contains(f"ERR-2 {_label}: messageを含まない", _err2_msg, "No data supplied.")
print()

print("[ERR-3] Safe Field型拒否Contract")
_err3_resp_a = _make_mock_response(400, json_value={"code": 123, "message": "valid message"})
with patch(_PATCH_TARGET, return_value=_err3_resp_a):
    try:
        _secret_uploader.upload(image_bytes=_SECRET_IMAGE_BYTES, filename="a.png", mime_type="image/png")
        _err3a_raised = None
    except WordPressMediaUploadError as exc:
        _err3a_raised = exc
check_not_contains("ERR-3 code非str: codeを含まない", str(_err3a_raised), "123")
check_contains("ERR-3 code非str: 有効なmessageは採用される", str(_err3a_raised), "valid message")

_err3_resp_b = _make_mock_response(400, json_value={"code": "valid_code", "message": 456})
with patch(_PATCH_TARGET, return_value=_err3_resp_b):
    try:
        _secret_uploader.upload(image_bytes=_SECRET_IMAGE_BYTES, filename="a.png", mime_type="image/png")
        _err3b_raised = None
    except WordPressMediaUploadError as exc:
        _err3b_raised = exc
check_not_contains("ERR-3 message非str: messageを含まない", str(_err3b_raised), "456")
check_contains("ERR-3 message非str: 有効なcodeは採用される", str(_err3b_raised), "valid_code")
print()

print("[ERR-4] Safe Field正規化Contract")
for _label, _raw_code in [
    ("CR", "bad\rcode"),
    ("LF", "bad\ncode"),
    ("tab", "bad\tcode"),
    ("NUL", "bad\x00code"),
    ("DEL", "bad\x7fcode"),
]:
    _err4_resp = _make_mock_response(400, json_value={"code": _raw_code})
    with patch(_PATCH_TARGET, return_value=_err4_resp):
        try:
            _secret_uploader.upload(image_bytes=_SECRET_IMAGE_BYTES, filename="a.png", mime_type="image/png")
            _err4_raised = None
        except WordPressMediaUploadError as exc:
            _err4_raised = exc
    _err4_msg = str(_err4_raised)
    check_not_contains(f"ERR-4 {_label}: 制御文字が残らない", _err4_msg, _raw_code)
    check_contains(f"ERR-4 {_label}: 正規化後の値（空白置換）を含む", _err4_msg, "bad code")
print()

print("[ERR-5] Safe Field長さ制限Contract")
_long_code = "c" * 101
_err5_resp_a = _make_mock_response(400, json_value={"code": _long_code})
with patch(_PATCH_TARGET, return_value=_err5_resp_a):
    try:
        _secret_uploader.upload(image_bytes=_SECRET_IMAGE_BYTES, filename="a.png", mime_type="image/png")
        _err5a_raised = None
    except WordPressMediaUploadError as exc:
        _err5a_raised = exc
check_contains("ERR-5 code: 100文字に切り詰め", str(_err5a_raised), "c" * 100)
check_not_contains("ERR-5 code: 101文字目は含まれない", str(_err5a_raised), "c" * 101)

_long_message = "m" * 201
_err5_resp_b = _make_mock_response(400, json_value={"message": _long_message})
with patch(_PATCH_TARGET, return_value=_err5_resp_b):
    try:
        _secret_uploader.upload(image_bytes=_SECRET_IMAGE_BYTES, filename="a.png", mime_type="image/png")
        _err5b_raised = None
    except WordPressMediaUploadError as exc:
        _err5b_raised = exc
check_contains("ERR-5 message: 200文字に切り詰め", str(_err5b_raised), "m" * 200)
check_not_contains("ERR-5 message: 201文字目は含まれない", str(_err5b_raised), "m" * 201)
print()

print("[ERR-6] 非JSON Non-2xxフォールバックContract")
_err6_resp = _make_mock_response(500, json_side_effect=ValueError("not json"))
with patch(_PATCH_TARGET, return_value=_err6_resp):
    try:
        _secret_uploader.upload(image_bytes=_SECRET_IMAGE_BYTES, filename="a.png", mime_type="image/png")
        _err6_raised = None
    except WordPressMediaUploadError as exc:
        _err6_raised = exc
check_contains("ERR-6a. HTTP statusのみ含む", str(_err6_raised), "500")
check_not_contains("ERR-6b. codeキーワード非含有", str(_err6_raised), "code=")
print()

print("[ERR-7] 非Object JSON Non-2xxフォールバックContract")
_err7_resp = _make_mock_response(500, json_value=["not", "a", "dict"])
with patch(_PATCH_TARGET, return_value=_err7_resp):
    try:
        _secret_uploader.upload(image_bytes=_SECRET_IMAGE_BYTES, filename="a.png", mime_type="image/png")
        _err7_raised = None
    except WordPressMediaUploadError as exc:
        _err7_raised = exc
check_contains("ERR-7. HTTP statusのみ含む", str(_err7_raised), "500")
check_not_contains("ERR-7. messageキーワード非含有", str(_err7_raised), "message=")
print()

print("[ERR-8] Non-2xx生ボディ非露出Contract")
_err8_resp = _make_mock_response(500, json_value={"code": "err", "message": "msg"})
with patch(_PATCH_TARGET, return_value=_err8_resp):
    try:
        _secret_uploader.upload(image_bytes=_SECRET_IMAGE_BYTES, filename="a.png", mime_type="image/png")
        _err8_raised = None
    except WordPressMediaUploadError as exc:
        _err8_raised = exc
_check_security_common("ERR-8", _err8_raised)
print()

# =====================================================================
# Dependency／Scope／Side Effect
# =====================================================================

print("[DEP-1] 禁止import Contract（AST import解析）")


def _collect_imported_module_names(source: str) -> set:
    """Import／ImportFromノードのみを対象に、実際にimportされたモジュール名を集める。
    docstringやコメント中の単語（例: 'image_resolver'を説明文で言及する等）を
    誤検知しないよう、テキスト検索ではなくASTの構文構造に基づいて判定する。"""
    tree = ast.parse(source)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
    return names


def _violates_forbidden_import(name: str) -> bool:
    if name in ("outputs", "image_resolver", "workflow", "scheduler"):
        return True
    if name.startswith(("outputs.", "image_resolver.", "workflow.", "scheduler.")):
        return True
    if name.startswith("retry_"):
        return True
    return False


_dep1_all_imports = _collect_imported_module_names(_uploader_source) | _collect_imported_module_names(
    _init_source
)
_dep1_violations = sorted(name for name in _dep1_all_imports if _violates_forbidden_import(name))
check(
    "DEP-1. WordPressOutput／image_resolver／ArticleData／Workflow／Scheduler／Retry関連の禁止importなし",
    _dep1_violations,
    [],
)
print()

print("[DEP-2] 許可外I/O／Network Contract")
for _token in [
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
]:
    check_not_contains(f"DEP-2. {_token}非存在", _combined_source, _token)
check_contains("DEP-2. requests.postは存在する（許可I/O）", _combined_source, "requests.post(")
print()

print("[DEP-3] ログ／出力禁止Contract")
check_not_contains("DEP-3a. print非使用", _combined_source, "print(")
check_not_contains("DEP-3b. logging非使用", _combined_source, "logging")
_dep3_field_names = [f.name for f in fields(MediaUploadResult)]
check_false("DEP-3c. usernameをResultへ保持しない", "username" in _dep3_field_names)
check_false("DEP-3d. app_passwordをResultへ保持しない", "app_password" in _dep3_field_names)
print()

print("[DEP-4] featured_media非参照Contract")
check_not_contains("DEP-4. featured_media非出現", _combined_source, "featured_media")
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
