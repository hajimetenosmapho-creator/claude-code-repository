"""
E2E テスト: v6.12.0 Generated Image WordPress Media Upload Wiring Foundation

Source of Truth:
    docs/design/generated_image_wordpress_media_upload_wiring_foundation.md
    （Architecture Review 5：Approved、Test Review：Approved、43.7章参照）

本テストは実HTTP・実WordPress投稿・実OpenAI Client生成・実WordPress Client生成の
いずれも発生させない。media_uploaderはFake（test file内限定）を明示的にConstructor
Injectionで注入し、実WordPressMediaUploaderインスタンスは生成しない。本Wiring層は
Constructor Injectionのみでfrom_env()やClient生成経路を持たないため、実Client構築を
強制遮断するRuntime Guardは必須としない（Test Review Suggestion TR-S-3、31.6章）。

Scenario構成（17 Scenario）:
    PUB-1（Public import Contract）
    CTOR-1（Constructor deferred validation）
    CAP-1/2/3（capability不正3ケース、Duck Typing Guard）
    VAL-1（image型不正）
    VAL-2（検証順序：image優先）
    DELEGATE-1（正常系委譲＋引数＋戻り値＋呼出回数＋Duck Typing）
    SIG-1（signature不一致TypeError）
    PROP-1/2/3（dependency内部TypeError／WordPressMediaUploadError／RuntimeErrorの無変換伝播）
    INTERRUPT-1（KeyboardInterrupt伝播）
    INTERRUPT-2（SystemExit伝播）
    STATE-1（request単位state非保持：Runtime）
    STATE-AST-1（request単位state非保持：Constructor Source Guard／upload() Source Guard、
        Code Review Finding CR-m-1反映：upload()本体のself属性代入非存在をAST解析で確認）
    SEC-1（Security固定message非露出）
    LOG-1（Loggingなし）
    DEP-1（許可依存Guard）
    DEP-2（逆依存Guard）
    SIDE-1（Side Effect Guard）

Regressionは本ファイルのScenario数に含まない（35章のRegression Strategy参照）。

実行方法:
    cd projects/03_game_content_ai
    python tests/test_e2e_v6_12_0_generated_image_wordpress_media_upload_wiring_foundation.py
"""
import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ─── テスト用ユーティリティ（v6.10.0／v6.11.0 precedentを踏襲） ───

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


def invoke(func):
    """funcを呼び出し、(戻り値, 例外)のタプルを返す。例外がなければ(結果, None)。"""
    try:
        return func(), None
    except BaseException as exc:
        return None, exc


CAPABILITY_MESSAGE = "media_uploader must provide a callable upload method"


# ─── AST解析ユーティリティ（v6.10.0／v6.11.0 precedentを踏襲） ───


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


def get_imported_names_from(file_path: Path, module_name: str) -> set:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == module_name:
            for alias in node.names:
                names.add(alias.name)
    return names


def find_class_def(tree, class_name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    return None


def find_method(class_def, method_name: str):
    if class_def is None:
        return None
    for item in class_def.body:
        if isinstance(item, ast.FunctionDef) and item.name == method_name:
            return item
    return None


def _target_contains_self_attribute(target: ast.AST) -> bool:
    """代入先targetが self.<attribute>（直接、またはtuple／list targetの内側）を
    含むかどうかを判定する。ローカル変数への代入（例: upload_method = ...）は
    対象外とする。"""
    if (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "self"
    ):
        return True
    if isinstance(target, (ast.Tuple, ast.List)):
        return any(_target_contains_self_attribute(elt) for elt in target.elts)
    return False


def find_self_state_violations(method_node) -> list:
    """method_node（ast.FunctionDef）のbody以下を再帰的に走査し、
    self.<attribute>へのAssign／AnnAssign／AugAssign、またはsetattr(self, ...)呼出の
    行番号一覧を返す。request単位stateをインスタンス属性へ保存していないことを
    静的に検証するためのGuard（Frozen Architecture 21.1節）。"""
    violations = []
    if method_node is None:
        return violations
    for node in ast.walk(method_node):
        if isinstance(node, ast.Assign):
            if any(_target_contains_self_attribute(t) for t in node.targets):
                violations.append(node.lineno)
        elif isinstance(node, ast.AnnAssign):
            if _target_contains_self_attribute(node.target):
                violations.append(node.lineno)
        elif isinstance(node, ast.AugAssign):
            if _target_contains_self_attribute(node.target):
                violations.append(node.lineno)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "setattr"
            and len(node.args) >= 1
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "self"
        ):
            violations.append(node.lineno)
    return violations


print("=" * 60)
print("v6.12.0 Generated Image WordPress Media Upload Wiring Foundation E2E テスト")
print("=" * 60)
print()

import generated_image_wordpress_media
from generated_image_wordpress_media import GeneratedImageWordPressMediaUploader

from ai_image_generation import GeneratedImage
from wordpress_media import (
    MediaUploadResult,
    WordPressMediaUploadError,
    WordPressMediaUploader,
)

GENERATED_IMAGE_WORDPRESS_MEDIA_DIR = PROJECT_ROOT / "src" / "generated_image_wordpress_media"
FILES = {
    "__init__": GENERATED_IMAGE_WORDPRESS_MEDIA_DIR / "__init__.py",
    "generated_image_wordpress_media_uploader": (
        GENERATED_IMAGE_WORDPRESS_MEDIA_DIR / "generated_image_wordpress_media_uploader.py"
    ),
}

AI_IMAGE_GENERATION_DIR = PROJECT_ROOT / "src" / "ai_image_generation"
OPENAI_IMAGE_GENERATION_DIR = PROJECT_ROOT / "src" / "openai_image_generation"
WORDPRESS_MEDIA_DIR = PROJECT_ROOT / "src" / "wordpress_media"

_VALID_IMAGE = GeneratedImage(image_bytes=b"PNGDATA", mime_type="image/png")
_VALID_FILENAME = "photo.png"

# ─── Test Double（Fake／Stub、test file内限定。production packageへは配置しない） ───


class _RecordingMediaUploader:
    """callableなuploadを持つFake。呼出引数・回数を記録し、設定可能なMediaUploadResultを返す。
    WordPressMediaUploaderを継承しない（Duck Typing Contractの確認）。"""

    def __init__(self, result=None):
        self.calls = []
        self._result = result if result is not None else MediaUploadResult(
            media_id=1, source_url="https://example.com/photo.png", mime_type="image/png"
        )

    def upload(self, **kwargs):
        self.calls.append(kwargs)
        return self._result


class _MissingUploadUploader:
    """upload属性を持たないFake。"""
    pass


class _NoneUploadUploader:
    """upload = Noneを持つFake。"""
    upload = None


class _StringUploadUploader:
    """upload = 非callable文字列を持つFake。"""
    upload = "not callable"


class _SignatureMismatchUploader:
    """uploadはcallableだが、image_bytes／filename／mime_typeを受け付けないFake。"""

    def upload(self) -> None:
        pass


class _InternalTypeErrorUploader:
    """uploadのsignatureは適合するが、内部でTypeErrorを送出するFake。"""

    def upload(self, image_bytes: bytes, filename: str, mime_type: str) -> MediaUploadResult:
        raise TypeError("internal failure")


class _RaisingWordPressMediaUploadErrorUploader:
    """事前構築済みのWordPressMediaUploadErrorインスタンスを送出するFake。"""

    def __init__(self, exc: WordPressMediaUploadError):
        self._exc = exc

    def upload(self, image_bytes: bytes, filename: str, mime_type: str) -> MediaUploadResult:
        raise self._exc


class _RaisingRuntimeErrorUploader:
    """通常のRuntimeErrorを送出するFake。"""

    def upload(self, image_bytes: bytes, filename: str, mime_type: str) -> MediaUploadResult:
        raise RuntimeError("boom")


class _RaisingKeyboardInterruptUploader:
    """KeyboardInterruptを送出するFake。"""

    def upload(self, image_bytes: bytes, filename: str, mime_type: str) -> MediaUploadResult:
        raise KeyboardInterrupt()


class _RaisingSystemExitUploader:
    """SystemExitを送出するFake。"""

    def upload(self, image_bytes: bytes, filename: str, mime_type: str) -> MediaUploadResult:
        raise SystemExit(1)


# =====================================================================
# PUB-1: Public import Contract
# =====================================================================

print("[PUB-1] Public import Contract")
check_true(
    "PUB-1. generated_image_wordpress_mediaがimportできる",
    "generated_image_wordpress_media" in sys.modules,
)
check_true(
    "PUB-1. GeneratedImageWordPressMediaUploaderがimportできる",
    GeneratedImageWordPressMediaUploader is not None,
)
check(
    "PUB-1. class名が一致",
    GeneratedImageWordPressMediaUploader.__name__,
    "GeneratedImageWordPressMediaUploader",
)
check(
    "PUB-1. __all__の集合一致",
    set(generated_image_wordpress_media.__all__),
    {"GeneratedImageWordPressMediaUploader"},
)
check("PUB-1. __all__の件数が1", len(generated_image_wordpress_media.__all__), 1)
print()

# =====================================================================
# CTOR-1: Constructor deferred validation
# =====================================================================

print("[CTOR-1] Constructor deferred validation")
_ctor1_valid_result, _ctor1_valid_exc = invoke(
    lambda: GeneratedImageWordPressMediaUploader(_RecordingMediaUploader())
)
check_true("CTOR-1. 正当なmedia_uploaderでconstructor成功", _ctor1_valid_exc is None)

_ctor1_invalid_result, _ctor1_invalid_exc = invoke(
    lambda: GeneratedImageWordPressMediaUploader(_MissingUploadUploader())
)
check_true(
    "CTOR-1. capability不正なmedia_uploaderでもconstructor成功（検証は遅延される）",
    _ctor1_invalid_exc is None,
)
print()

# =====================================================================
# CAP-1/2/3: capability不正3ケース（Duck Typing Guard）
# =====================================================================

print("[CAP-1/2/3] capability不正3ケース")
_cap_cases = [
    ("CAP-1", "upload属性なし", _MissingUploadUploader()),
    ("CAP-2", "upload = None", _NoneUploadUploader()),
    ("CAP-3", "upload = 非callable文字列", _StringUploadUploader()),
]
for _scenario_id, _label, _fake in _cap_cases:
    _uploader = GeneratedImageWordPressMediaUploader(_fake)
    _result, _exc = invoke(lambda u=_uploader: u.upload(_VALID_IMAGE, _VALID_FILENAME))
    check_true(f"{_scenario_id}. {_label}: TypeErrorが送出される", isinstance(_exc, TypeError))
    check(
        f"{_scenario_id}. {_label}: 固定message完全一致",
        str(_exc) if _exc is not None else None,
        CAPABILITY_MESSAGE,
    )
    check_true(
        f"{_scenario_id}. {_label}: KeyboardInterrupt/SystemExitではない",
        not isinstance(_exc, (KeyboardInterrupt, SystemExit)),
    )
print()

# =====================================================================
# VAL-1: image型不正
# =====================================================================

print("[VAL-1] image型不正")
_val1_cases = [
    ("None", None),
    ("object()", object()),
]
for _label, _value in _val1_cases:
    _val1_recorder = _RecordingMediaUploader()
    _val1_uploader = GeneratedImageWordPressMediaUploader(_val1_recorder)
    _result, _exc = invoke(lambda u=_val1_uploader, v=_value: u.upload(v, _VALID_FILENAME))
    check_true(f"VAL-1. image={_label}: ValueErrorが送出される", isinstance(_exc, ValueError))
    check(f"VAL-1. image={_label}: 下流upload呼出0回", len(_val1_recorder.calls), 0)
    _val1_message = str(_exc) if _exc is not None else ""
    check_not_contains(f"VAL-1. image={_label}: messageにfilenameが含まれない", _val1_message, _VALID_FILENAME)
    check_not_contains(f"VAL-1. image={_label}: messageにmime_typeが含まれない", _val1_message, "image/png")
print()

# =====================================================================
# VAL-2: 検証順序（image不正＋media_uploader capability不正）
# =====================================================================

print("[VAL-2] 検証順序：imageとmedia_uploaderの両方が不正")
_val2_uploader = GeneratedImageWordPressMediaUploader(_MissingUploadUploader())
_val2_result, _val2_exc = invoke(lambda: _val2_uploader.upload(None, _VALID_FILENAME))
check_true(
    "VAL-2. ValueErrorが送出される（capability不正TypeErrorではない）",
    isinstance(_val2_exc, ValueError),
)
check_false("VAL-2. TypeErrorではない", isinstance(_val2_exc, TypeError))
print()

# =====================================================================
# DELEGATE-1: 正常系委譲＋引数＋戻り値＋呼出回数＋Duck Typing
# =====================================================================

print("[DELEGATE-1] 正常系委譲＋引数＋戻り値＋呼出回数＋Duck Typing")
_delegate1_image = GeneratedImage(image_bytes=b"PNGDATA-DELEGATE", mime_type="image/png")
_delegate1_filename = "delegate-photo.png"
_delegate1_expected_result = MediaUploadResult(
    media_id=42, source_url="https://example.com/delegate-photo.png", mime_type="image/png"
)
_delegate1_recorder = _RecordingMediaUploader(result=_delegate1_expected_result)
_delegate1_uploader = GeneratedImageWordPressMediaUploader(_delegate1_recorder)

check_false(
    "DELEGATE-1. FakeはWordPressMediaUploaderを継承しない（Duck Typing）",
    isinstance(_delegate1_recorder, WordPressMediaUploader),
)

_delegate1_result, _delegate1_exc = invoke(
    lambda: _delegate1_uploader.upload(_delegate1_image, _delegate1_filename)
)
check_true("DELEGATE-1. 例外が発生しない", _delegate1_exc is None)
check("DELEGATE-1. upload()が1回だけ呼ばれる", len(_delegate1_recorder.calls), 1)

_delegate1_call_kwargs = _delegate1_recorder.calls[0] if _delegate1_recorder.calls else {}
check(
    "DELEGATE-1. keyword引数のkey集合が完全一致",
    set(_delegate1_call_kwargs.keys()),
    {"image_bytes", "filename", "mime_type"},
)
check(
    "DELEGATE-1. image_bytesの値が等しい",
    _delegate1_call_kwargs.get("image_bytes"),
    _delegate1_image.image_bytes,
)
check("DELEGATE-1. filenameの値が等しい", _delegate1_call_kwargs.get("filename"), _delegate1_filename)
check(
    "DELEGATE-1. mime_typeの値が等しい",
    _delegate1_call_kwargs.get("mime_type"),
    _delegate1_image.mime_type,
)
check(
    "DELEGATE-1. MediaUploadResultが値として一致して返る（value equality、identityは要求しない）",
    _delegate1_result,
    _delegate1_expected_result,
)
print()

# =====================================================================
# SIG-1: signature不一致TypeError
# =====================================================================

print("[SIG-1] signature不一致TypeError")
_sig1_uploader = GeneratedImageWordPressMediaUploader(_SignatureMismatchUploader())
_sig1_result, _sig1_exc = invoke(lambda: _sig1_uploader.upload(_VALID_IMAGE, _VALID_FILENAME))
check_true("SIG-1. TypeErrorが送出される", isinstance(_sig1_exc, TypeError))
check_false(
    "SIG-1. 固定capability messageとは不一致（capability不正ではないことの確認）",
    (str(_sig1_exc) if _sig1_exc is not None else "") == CAPABILITY_MESSAGE,
)
check(
    "SIG-1. __cause__がNone（chaining操作が追加されていない）",
    _sig1_exc.__cause__ if _sig1_exc is not None else "NOT-RAISED",
    None,
)
check(
    "SIG-1. __context__がNone",
    _sig1_exc.__context__ if _sig1_exc is not None else "NOT-RAISED",
    None,
)
print()

# =====================================================================
# PROP-1/2/3: 下流例外の無変換伝播（dependency内部TypeError／
#             WordPressMediaUploadError／RuntimeError）
# =====================================================================

print("[PROP-1] dependency内部TypeErrorの無変換伝播")
_prop1_uploader = GeneratedImageWordPressMediaUploader(_InternalTypeErrorUploader())
_prop1_result, _prop1_exc = invoke(lambda: _prop1_uploader.upload(_VALID_IMAGE, _VALID_FILENAME))
check_true("PROP-1. TypeErrorが送出される", isinstance(_prop1_exc, TypeError))
check(
    "PROP-1. Fake側messageと等価",
    str(_prop1_exc) if _prop1_exc is not None else None,
    "internal failure",
)
check_false(
    "PROP-1. 固定capability messageへ変換されていない",
    (str(_prop1_exc) if _prop1_exc is not None else "") == CAPABILITY_MESSAGE,
)
check(
    "PROP-1. __cause__がNone",
    _prop1_exc.__cause__ if _prop1_exc is not None else "NOT-RAISED",
    None,
)
print()

print("[PROP-2] WordPressMediaUploadErrorの無変換伝播（object identity確認）")
_prop2_prebuilt_exc = WordPressMediaUploadError("WordPress Media APIへの通信に失敗しました")
_prop2_uploader = GeneratedImageWordPressMediaUploader(
    _RaisingWordPressMediaUploadErrorUploader(_prop2_prebuilt_exc)
)
_prop2_result, _prop2_exc = invoke(lambda: _prop2_uploader.upload(_VALID_IMAGE, _VALID_FILENAME))
check_true(
    "PROP-2. WordPressMediaUploadErrorが送出される",
    isinstance(_prop2_exc, WordPressMediaUploadError),
)
check_true(
    "PROP-2. 事前構築した例外objectと同一（無変換伝播、==ではなくis）",
    _prop2_exc is _prop2_prebuilt_exc,
)
check(
    "PROP-2. messageが維持される",
    str(_prop2_exc) if _prop2_exc is not None else None,
    str(_prop2_prebuilt_exc),
)
check(
    "PROP-2. __cause__がNone（新規Exception Chainingなし）",
    _prop2_exc.__cause__ if _prop2_exc is not None else "NOT-RAISED",
    None,
)
print()

print("[PROP-3] RuntimeErrorの無変換伝播")
_prop3_uploader = GeneratedImageWordPressMediaUploader(_RaisingRuntimeErrorUploader())
_prop3_result, _prop3_exc = invoke(lambda: _prop3_uploader.upload(_VALID_IMAGE, _VALID_FILENAME))
check_true("PROP-3. RuntimeErrorが送出される", isinstance(_prop3_exc, RuntimeError))
check_false("PROP-3. TypeErrorではない", isinstance(_prop3_exc, TypeError))
check_false("PROP-3. WordPressMediaUploadErrorではない", isinstance(_prop3_exc, WordPressMediaUploadError))
check("PROP-3. Fake側messageと等価", str(_prop3_exc) if _prop3_exc is not None else None, "boom")
print()

# =====================================================================
# INTERRUPT-1/2: KeyboardInterrupt／SystemExitの無変換伝播
# =====================================================================

print("[INTERRUPT-1] KeyboardInterruptを握りつぶさないこと")
_interrupt1_uploader = GeneratedImageWordPressMediaUploader(_RaisingKeyboardInterruptUploader())
_interrupt1_raised = None
try:
    _interrupt1_uploader.upload(_VALID_IMAGE, _VALID_FILENAME)
except KeyboardInterrupt as exc:
    _interrupt1_raised = exc
except Exception:
    _interrupt1_raised = None
check_true("INTERRUPT-1. KeyboardInterruptが伝播する", isinstance(_interrupt1_raised, KeyboardInterrupt))
print()

print("[INTERRUPT-2] SystemExitを握りつぶさないこと")
_interrupt2_uploader = GeneratedImageWordPressMediaUploader(_RaisingSystemExitUploader())
_interrupt2_raised = None
try:
    _interrupt2_uploader.upload(_VALID_IMAGE, _VALID_FILENAME)
except SystemExit as exc:
    _interrupt2_raised = exc
except Exception:
    _interrupt2_raised = None
check_true("INTERRUPT-2. SystemExitが伝播する", isinstance(_interrupt2_raised, SystemExit))
print()

# =====================================================================
# STATE-1: request単位state非保持（Runtime連続呼出の独立性）
# =====================================================================

print("[STATE-1] request単位state非保持（Runtime）")
_state1_recorder = _RecordingMediaUploader()
_state1_uploader = GeneratedImageWordPressMediaUploader(_state1_recorder)

_state1_first_result, _state1_first_exc = invoke(lambda: _state1_uploader.upload(None, "first.png"))
check_true("STATE-1. 1回目（不正image）でValueErrorが発生する", isinstance(_state1_first_exc, ValueError))

_state1_second_result, _state1_second_exc = invoke(
    lambda: _state1_uploader.upload(_VALID_IMAGE, "second.png")
)
check_true("STATE-1. 2回目（正当image）は1回目の例外に影響されず成功する", _state1_second_exc is None)
check(
    "STATE-1. 2回目の呼出でupload()が1回だけ呼ばれる（1回目の失敗は下流へ到達していない）",
    len(_state1_recorder.calls),
    1,
)
check(
    "STATE-1. 2回目の呼出のfilenameが正しく渡る（前回のstateが混入しない）",
    _state1_recorder.calls[0].get("filename"),
    "second.png",
)
print()

# =====================================================================
# STATE-AST-1: Constructor本体のSource Guard
# =====================================================================

print("[STATE-AST-1] Constructor本体が代入のみであることのSource Guard")
_uploader_source = FILES["generated_image_wordpress_media_uploader"].read_text(encoding="utf-8")
_uploader_tree = ast.parse(
    _uploader_source, filename=str(FILES["generated_image_wordpress_media_uploader"])
)
_uploader_class = find_class_def(_uploader_tree, "GeneratedImageWordPressMediaUploader")
check_true("STATE-AST-1. GeneratedImageWordPressMediaUploaderクラスが存在する", _uploader_class is not None)

_init_method = find_method(_uploader_class, "__init__")
check_true("STATE-AST-1. __init__メソッドが存在する", _init_method is not None)
_init_body = _init_method.body if _init_method is not None else []
check("STATE-AST-1. __init__のbodyが単一の文のみ", len(_init_body), 1)
check_true(
    "STATE-AST-1. __init__のbodyが単一のAssign文のみ（代入以外の処理を行わない）",
    len(_init_body) == 1 and isinstance(_init_body[0], ast.Assign),
)

print("[STATE-AST-1] upload()本体がrequest単位stateをself属性へ保存しないことのSource Guard")
_upload_method = find_method(_uploader_class, "upload")
check_true("STATE-AST-1. uploadメソッドが存在する", _upload_method is not None)

_upload_self_state_violations = find_self_state_violations(_upload_method)
check(
    "STATE-AST-1. upload()本体にself属性へのAssign／AnnAssign／AugAssign／"
    "setattr(self, ...)が存在しない（21.1節：image／filename／MediaUploadResult等の"
    "インスタンス状態保存禁止）",
    _upload_self_state_violations,
    [],
)

_upload_local_assigns = [
    node
    for node in ast.walk(_upload_method)
    if isinstance(node, ast.Assign)
    and any(isinstance(t, ast.Name) for t in node.targets)
]
check_true(
    "STATE-AST-1. upload()内にローカル変数へのAssignが少なくとも1件存在する"
    "（Guardの対比確認対象が実在すること、例：upload_method = getattr(...)）",
    len(_upload_local_assigns) >= 1,
)
check_true(
    "STATE-AST-1. ローカル変数へのAssign（self.属性ではない）はGuard判定でself属性扱いされない",
    all(
        not any(_target_contains_self_attribute(t) for t in node.targets)
        for node in _upload_local_assigns
    ),
)
print()

# =====================================================================
# SEC-1: Security固定message非露出
# =====================================================================

print("[SEC-1] Security固定message非露出")
_sec1_secret_filename = "SECRET_FILENAME_MARKER.png"
_sec1_val_recorder = _RecordingMediaUploader()
_sec1_val_uploader = GeneratedImageWordPressMediaUploader(_sec1_val_recorder)
_sec1_val_result, _sec1_val_exc = invoke(lambda: _sec1_val_uploader.upload(None, _sec1_secret_filename))
_sec1_val_message = str(_sec1_val_exc) if _sec1_val_exc is not None else ""
check_not_contains("SEC-1. ValueError messageにfilenameが含まれない", _sec1_val_message, _sec1_secret_filename)

_sec1_cap_fake = _MissingUploadUploader()
_sec1_cap_uploader = GeneratedImageWordPressMediaUploader(_sec1_cap_fake)
_sec1_cap_result, _sec1_cap_exc = invoke(
    lambda: _sec1_cap_uploader.upload(_VALID_IMAGE, _VALID_FILENAME)
)
_sec1_cap_message = str(_sec1_cap_exc) if _sec1_cap_exc is not None else ""
check("SEC-1. capability TypeError messageが固定文言と完全一致", _sec1_cap_message, CAPABILITY_MESSAGE)
check_not_contains(
    "SEC-1. capability TypeError messageにdependency reprが含まれない",
    _sec1_cap_message,
    repr(_sec1_cap_fake),
)
check_not_contains(
    "SEC-1. capability TypeError messageにdependency class名が含まれない",
    _sec1_cap_message,
    type(_sec1_cap_fake).__name__,
)
print()

# =====================================================================
# LOG-1: Loggingなし
# =====================================================================

print("[LOG-1] Loggingなし（AST）")
_uploader_import_details = get_import_details(FILES["generated_image_wordpress_media_uploader"])
check_false(
    "LOG-1. generated_image_wordpress_media_uploader.pyがloggingをimportしない",
    "logging" in _uploader_import_details["absolute_roots"],
)
_uploader_print_calls = get_call_lines(FILES["generated_image_wordpress_media_uploader"], "print")
check("LOG-1. generated_image_wordpress_media_uploader.pyにprint()呼出がない", _uploader_print_calls, [])
print()

# =====================================================================
# DEP-1: 許可依存Guard（AST：ast.Import／ast.ImportFrom解析）
# =====================================================================

print("[DEP-1] 許可依存Guard")

ALLOWED_MODULES = {"ai_image_generation", "wordpress_media"}
FORBIDDEN_EXACT = (
    "openai_image_generation",
    "image_resolver",
    "outputs",
    "ai",
    "pipeline",
    "workflow_engine",
    "scheduler",
    "scripts",
    "requests",
    "openai",
)
FORBIDDEN_PREFIXES = ("retry_",)

_import_details = {name: get_import_details(path) for name, path in FILES.items()}

for _name, _details in _import_details.items():
    check_true(
        f"DEP-1. {_name}の絶対importが許可集合の部分集合",
        _details["absolute_roots"].issubset(ALLOWED_MODULES),
    )
    _violations = sorted(
        m
        for m in _details["absolute_roots"]
        if m in FORBIDDEN_EXACT or m.startswith(FORBIDDEN_PREFIXES)
    )
    check(f"DEP-1. {_name}の禁止import違反リストが空", _violations, [])

_ai_image_generation_names = get_imported_names_from(
    FILES["generated_image_wordpress_media_uploader"], "ai_image_generation"
)
check_true(
    "DEP-1. ai_image_generationからのimportがGeneratedImageのみの部分集合",
    _ai_image_generation_names.issubset({"GeneratedImage"}),
)

_wordpress_media_names = get_imported_names_from(
    FILES["generated_image_wordpress_media_uploader"], "wordpress_media"
)
check_true(
    "DEP-1. wordpress_mediaからのimportがWordPressMediaUploader／MediaUploadResultのみの部分集合",
    _wordpress_media_names.issubset({"WordPressMediaUploader", "MediaUploadResult"}),
)
print()

# =====================================================================
# DEP-2: 逆依存Guard（AST）
# =====================================================================

print("[DEP-2] 逆依存Guard：既存packageがgenerated_image_wordpress_mediaをimportしていないこと")

_reverse_dep_targets = {
    "ai_image_generation": AI_IMAGE_GENERATION_DIR,
    "openai_image_generation": OPENAI_IMAGE_GENERATION_DIR,
    "wordpress_media": WORDPRESS_MEDIA_DIR,
}
for _package_name, _package_dir in _reverse_dep_targets.items():
    _violating_files = []
    for _py_file in sorted(_package_dir.glob("*.py")):
        _details = get_import_details(_py_file)
        if "generated_image_wordpress_media" in _details["absolute_roots"]:
            _violating_files.append(_py_file.name)
    check(f"DEP-2. {_package_name}がgenerated_image_wordpress_mediaをimportしていない", _violating_files, [])
print()

# =====================================================================
# SIDE-1: Side Effect Guard（AST）
# =====================================================================

print("[SIDE-1] Side Effect Guard")
for _name, _path in FILES.items():
    check(f"SIDE-1. {_name}にsubprocess呼出がない", get_call_lines(_path, "subprocess"), [])
    check(f"SIDE-1. {_name}にopen()呼出がない", get_call_lines(_path, "open"), [])
    _details = _import_details[_name]
    check_false(f"SIDE-1. {_name}がsubprocessをimportしない", "subprocess" in _details["absolute_roots"])
    check_false(f"SIDE-1. {_name}がrequestsをimportしない", "requests" in _details["absolute_roots"])
    check_false(f"SIDE-1. {_name}がopenaiをimportしない", "openai" in _details["absolute_roots"])
    check_false(f"SIDE-1. {_name}がosをimportしない", "os" in _details["absolute_roots"])
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
