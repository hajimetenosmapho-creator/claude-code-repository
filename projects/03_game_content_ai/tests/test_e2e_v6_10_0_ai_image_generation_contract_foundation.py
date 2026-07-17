"""
E2E テスト: v6.10.0 AI Image Generation Contract Foundation

Source of Truth:
    docs/design/ai_image_generation_contract_foundation.md（Architecture Review Approved）
    Test Design（Test Review Approved、37 Scenario / 70 Case / 78 Assertion実測）
    Code Review 1（Changes Required）反映: image_bytesの型検証をisinstance()から
    type(value) is bytesへ変更し、bytes subclass拒否Caseを追加（GI-IB-TYPE）。

本テストは外部API・外部I/O・ネットワーク・ファイルI/O・環境変数のいずれにも依存しない
（本Release自体が外部I/Oを持たないため、モック化の対象自体が存在しない）。
production sourceを読み取るAST解析（Dependency Guard・Protocol構造検証）のみを行う。

Scenario構成（37 Scenario）:
    Public Package API: PKG-1〜PKG-5（5）
    GeneratedImage正常系: GI-1〜GI-12（12）
    GeneratedImage異常系（image_bytes）: GI-IB-TYPE, GI-IB-EMPTY（2）
    GeneratedImage異常系（mime_type）: GI-MT-TYPE, GI-MT-BLANK, GI-MT-STRUCT,
        GI-MT-CASE, GI-MT-DOMAIN, GI-MT-UNICODE, GI-MT-CTRL（7）
    AIImageGenerator Protocol: PROTO-1〜PROTO-4（4）
    Dependency Guard（AST）: DEP-1〜DEP-3（3、対象3ファイルごとに実行）
    Side Effect Guard（AST）: SIDE-1〜SIDE-4（4、対象3ファイルごとに実行）

Regressionは本ファイルのScenario数に含まない（別途Regression Execution Planとして運用する）。

実行方法:
    cd projects/03_game_content_ai
    python tests/test_e2e_v6_10_0_ai_image_generation_contract_foundation.py
"""
import ast
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

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


# ─── AST解析ユーティリティ ───


def get_import_details(file_path: Path) -> dict:
    """
    file_pathをASTでパースし、import情報を構造化して返す。

    - absolute_roots: 絶対import（level == 0）のトップレベルモジュール名集合
    - relative_imports: 相対import（level >= 1）のlevelとmodule名を保持する
      リスト。docstringやコメント中の単語を誤検知しないよう、テキスト検索
      ではなくASTの構文構造に基づいて判定する。
    """
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
    """file_pathをASTでパースし、指定した組み込み関数呼び出しの行番号一覧を返す。"""
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


def base_names(class_def) -> list:
    names = []
    for base in class_def.bases:
        if isinstance(base, ast.Name):
            names.append(base.id)
        elif isinstance(base, ast.Attribute):
            names.append(base.attr)
    return names


def decorator_names(class_def) -> list:
    names = []
    for dec in class_def.decorator_list:
        target = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(target, ast.Name):
            names.append(target.id)
        elif isinstance(target, ast.Attribute):
            names.append(target.attr)
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
print("v6.10.0 AI Image Generation Contract Foundation E2E テスト")
print("=" * 60)
print()

import ai_image_generation
from ai_image_generation import AIImageGenerator, GeneratedImage

AI_IMAGE_GENERATION_DIR = PROJECT_ROOT / "src" / "ai_image_generation"
FILES = {
    "__init__": AI_IMAGE_GENERATION_DIR / "__init__.py",
    "generated_image": AI_IMAGE_GENERATION_DIR / "generated_image.py",
    "ai_image_generator": AI_IMAGE_GENERATION_DIR / "ai_image_generator.py",
}

_VALID_BYTES = b"validbytes"

# =====================================================================
# PKG: Public Package API
# =====================================================================

print("[PKG-1] package import")
check_true("PKG-1. ai_image_generationがimportできる", "ai_image_generation" in sys.modules)
print()

print("[PKG-2] GeneratedImageをpackage rootからimport")
check_true("PKG-2. GeneratedImageがimportできる", GeneratedImage is not None)
print()

print("[PKG-3] AIImageGeneratorをpackage rootからimport")
check_true("PKG-3. AIImageGeneratorがimportできる", AIImageGenerator is not None)
print()

print("[PKG-4] __all__の集合が2 Public APIと一致し、件数が2")
check(
    "PKG-4. __all__の集合一致",
    set(ai_image_generation.__all__),
    {"GeneratedImage", "AIImageGenerator"},
)
check("PKG-4. __all__の件数が2", len(ai_image_generation.__all__), 2)
print()

print("[PKG-5] ImageGenerationRequest／AIImageGenerationErrorがpackage属性にない（補助assertion）")
check_false(
    "PKG-5. ImageGenerationRequestがpackage属性にない",
    hasattr(ai_image_generation, "ImageGenerationRequest"),
)
check_false(
    "PKG-5. AIImageGenerationErrorがpackage属性にない",
    hasattr(ai_image_generation, "AIImageGenerationError"),
)
print()

# =====================================================================
# GI: GeneratedImage 正常系
# =====================================================================

print("[GI-1〜GI-7] 既知・未知image/*サブタイプの正常構築（許可リスト非固定の確認）")
_gi_positive_cases = [
    ("GI-1", "image/png"),
    ("GI-2", "image/jpeg"),
    ("GI-3", "image/webp"),
    ("GI-4", "image/avif"),
    ("GI-5", "image/svg+xml"),
    ("GI-6", "image/x-custom-format"),
    ("GI-7", "image/vnd.example.format"),
]
for _scenario_id, _mime in _gi_positive_cases:
    _instance = GeneratedImage(image_bytes=_VALID_BYTES, mime_type=_mime)
    check(f"{_scenario_id}. mime_type={_mime!r}で正常構築", _instance.mime_type, _mime)
print()

print("[GI-8, GI-9] image_bytesの長さバリエーション")
_gi8 = GeneratedImage(image_bytes=b"\x89", mime_type="image/png")
check("GI-8. image_bytes 1byteで正常構築", _gi8.image_bytes, b"\x89")

_gi9_bytes = b"x" * 4096
_gi9 = GeneratedImage(image_bytes=_gi9_bytes, mime_type="image/png")
check("GI-9. image_bytes 複数byteで正常構築", len(_gi9.image_bytes), 4096)
print()

print("[GI-10] frozen dataclass（再代入不可）")
_gi10 = GeneratedImage(image_bytes=_VALID_BYTES, mime_type="image/png")

_gi10_image_bytes_raised = False
try:
    _gi10.image_bytes = b"changed"
except FrozenInstanceError:
    _gi10_image_bytes_raised = True
check_true("GI-10. image_bytes再代入でFrozenInstanceError", _gi10_image_bytes_raised)

_gi10_mime_type_raised = False
try:
    _gi10.mime_type = "image/jpeg"
except FrozenInstanceError:
    _gi10_mime_type_raised = True
check_true("GI-10. mime_type再代入でFrozenInstanceError", _gi10_mime_type_raised)
print()

print("[GI-11] 等価性")
_gi11_a = GeneratedImage(image_bytes=_VALID_BYTES, mime_type="image/png")
_gi11_b = GeneratedImage(image_bytes=_VALID_BYTES, mime_type="image/png")
_gi11_c = GeneratedImage(image_bytes=_VALID_BYTES, mime_type="image/jpeg")
check_true("GI-11. 同一値は等価", _gi11_a == _gi11_b)
check_false("GI-11. 異なる値は非等価", _gi11_a == _gi11_c)
print()

print("[GI-12] repr Security Contract")
_GI12_MARKER = b"PNGDATA"
_gi12 = GeneratedImage(image_bytes=_GI12_MARKER, mime_type="image/png")

_gi12_repr_raised = False
_gi12_repr_text = ""
try:
    _gi12_repr_text = repr(_gi12)
except Exception:
    _gi12_repr_raised = True
check_false("GI-12. repr()が例外を出さない", _gi12_repr_raised)
check_contains("GI-12. reprにmime_typeが含まれる", _gi12_repr_text, "image/png")
check_not_contains("GI-12. reprにimage_bytesの値(marker)が含まれない", _gi12_repr_text, "PNGDATA")
print()

# =====================================================================
# GI: GeneratedImage 異常系（image_bytes）
# =====================================================================

print("[GI-IB-TYPE] image_bytes型不正")


class _CustomBytesSubclass(bytes):
    """厳密にbytes型（type(x) is bytes）のみを許可するContractを検証するための、
    test file内限定のbytes subclass。production packageへは配置しない。"""


_ib_type_cases = [
    ("None", None),
    ("str", "not-bytes"),
    ("bytearray", bytearray(b"x")),
    ("memoryview", memoryview(b"x")),
    ("int", 123),
    ("bytes subclass", _CustomBytesSubclass(b"x")),
]
for _case_label, _value in _ib_type_cases:
    check_raises_value_error(
        f"GI-IB-TYPE. image_bytes={_case_label}でValueError",
        lambda v=_value: GeneratedImage(image_bytes=v, mime_type="image/png"),
    )
print()

print("[GI-IB-EMPTY] image_bytes空bytes")
check_raises_value_error(
    "GI-IB-EMPTY. image_bytes=b''でValueError",
    lambda: GeneratedImage(image_bytes=b"", mime_type="image/png"),
)
print()

# =====================================================================
# GI: GeneratedImage 異常系（mime_type）
# =====================================================================

print("[GI-MT-TYPE] mime_type型不正")
_mt_type_cases = [
    ("None", None),
    ("int", 123),
    ("bytes", b"image/png"),
]
for _case_label, _value in _mt_type_cases:
    check_raises_value_error(
        f"GI-MT-TYPE. mime_type={_case_label}でValueError",
        lambda v=_value: GeneratedImage(image_bytes=_VALID_BYTES, mime_type=v),
    )
print()

print("[GI-MT-BLANK] mime_type空・空白系")
_mt_blank_cases = [
    ("空文字", ""),
    ("空白のみ", "   "),
    ("先頭空白", " image/png"),
    ("末尾空白", "image/png "),
]
for _case_label, _value in _mt_blank_cases:
    check_raises_value_error(
        f"GI-MT-BLANK. mime_type={_case_label}({_value!r})でValueError",
        lambda v=_value: GeneratedImage(image_bytes=_VALID_BYTES, mime_type=v),
    )
print()

print("[GI-MT-STRUCT] mime_type構造不正")
_mt_struct_cases = [
    ("subtypeなし", "image/"),
    ("slash複数", "image//png"),
    ("parameter(charset)", "image/png; charset=x"),
    ("parameter(foo)", "image/png;foo=bar"),
    ("空白混入", "image/ png"),
]
for _case_label, _value in _mt_struct_cases:
    check_raises_value_error(
        f"GI-MT-STRUCT. mime_type={_case_label}({_value!r})でValueError",
        lambda v=_value: GeneratedImage(image_bytes=_VALID_BYTES, mime_type=v),
    )
print()

print("[GI-MT-CASE] mime_type大文字小文字")
check_raises_value_error(
    "GI-MT-CASE. mime_type='Image/png'でValueError",
    lambda: GeneratedImage(image_bytes=_VALID_BYTES, mime_type="Image/png"),
)
print()

print("[GI-MT-DOMAIN] mime_typeがimage/で始まらない")
_mt_domain_cases = [
    ("text/plain", "text/plain"),
    ("application/json", "application/json"),
]
for _case_label, _value in _mt_domain_cases:
    check_raises_value_error(
        f"GI-MT-DOMAIN. mime_type={_case_label!r}でValueError",
        lambda v=_value: GeneratedImage(image_bytes=_VALID_BYTES, mime_type=v),
    )
print()

print("[GI-MT-UNICODE] mime_typeにUnicode文字")
check_raises_value_error(
    "GI-MT-UNICODE. mime_type='image/画像'でValueError",
    lambda: GeneratedImage(image_bytes=_VALID_BYTES, mime_type="image/画像"),
)
print()

print("[GI-MT-CTRL] mime_typeに制御文字")
_mt_ctrl_cases = [
    ("CR", "image/png\r"),
    ("LF", "image/png\n"),
    ("tab", "image/png\t"),
    ("NUL", "image/png\x00"),
    ("DEL", "image/png\x7f"),
]
for _case_label, _value in _mt_ctrl_cases:
    check_raises_value_error(
        f"GI-MT-CTRL. mime_type制御文字={_case_label}({_value!r})でValueError",
        lambda v=_value: GeneratedImage(image_bytes=_VALID_BYTES, mime_type=v),
    )
print()

# =====================================================================
# PROTO: AIImageGenerator
# =====================================================================

_ai_image_generator_source = FILES["ai_image_generator"].read_text(encoding="utf-8")
_ai_image_generator_tree = ast.parse(
    _ai_image_generator_source, filename=str(FILES["ai_image_generator"])
)
_aig_class = find_class_def(_ai_image_generator_tree, "AIImageGenerator")

print("[PROTO-1] AST: AIImageGeneratorがProtocolをbaseに持つ")
_aig_bases = base_names(_aig_class) if _aig_class is not None else []
check_true(
    "PROTO-1. AIImageGeneratorクラスが存在し、basesにProtocolを含む",
    _aig_class is not None and "Protocol" in _aig_bases,
)
print()

print("[PROTO-2] AST: generate(self, prompt: str) -> GeneratedImageの形")
_generate_method = find_method(_aig_class, "generate")
_prompt_arg = None
if _generate_method is not None:
    _prompt_arg = next(
        (a for a in _generate_method.args.args if a.arg == "prompt"), None
    )
check(
    "PROTO-2. promptのannotationがstr",
    annotation_name(_prompt_arg.annotation) if _prompt_arg is not None else None,
    "str",
)
check(
    "PROTO-2. 戻り値annotationがGeneratedImage",
    annotation_name(_generate_method.returns) if _generate_method is not None else None,
    "GeneratedImage",
)
print()

print("[PROTO-3] AST: runtime_checkable decoratorがない")
_aig_decorators = decorator_names(_aig_class) if _aig_class is not None else []
check_false("PROTO-3. runtime_checkable decoratorが存在しない", "runtime_checkable" in _aig_decorators)
print()

print("[PROTO-4] test file内Fakeを実行し、prompt伝達とGeneratedImage返却を確認")


class _FakeAIImageGenerator:
    """test file内限定のFake。production packageへは配置しない。"""

    def __init__(self):
        self.received_prompts = []

    def generate(self, prompt: str) -> GeneratedImage:
        self.received_prompts.append(prompt)
        return GeneratedImage(image_bytes=b"FAKE", mime_type="image/png")


_fake = _FakeAIImageGenerator()
_fake_result = _fake.generate("a fake prompt")
check("PROTO-4. Fakeへpromptがそのまま渡る", _fake.received_prompts, ["a fake prompt"])
check_true("PROTO-4. FakeがGeneratedImageを返す", isinstance(_fake_result, GeneratedImage))
print()

# =====================================================================
# DEP: Dependency Guard（AST：ast.Import／ast.ImportFrom解析）
# =====================================================================

ALLOWED_MODULES = {"dataclasses", "re", "typing"}
FORBIDDEN_EXACT = (
    "wordpress_media",
    "outputs",
    "image_resolver",
    "ArticleData",
    "workflow",
    "scheduler",
    "requests",
    "openai",
    "anthropic",
    "PIL",
    "Pillow",
)
FORBIDDEN_PREFIXES = ("retry_",)

_import_details = {name: get_import_details(path) for name, path in FILES.items()}

print("[DEP-1] 標準ライブラリ以外の絶対importがないこと")
for _name, _details in _import_details.items():
    check_true(
        f"DEP-1. {_name}の絶対importが許可集合の部分集合",
        _details["absolute_roots"].issubset(ALLOWED_MODULES),
    )
print()

print("[DEP-2] 禁止packageへのimportがないこと")
for _name, _details in _import_details.items():
    _violations = sorted(
        m
        for m in _details["absolute_roots"]
        if m in FORBIDDEN_EXACT or m.startswith(FORBIDDEN_PREFIXES)
    )
    check(f"DEP-2. {_name}の禁止import違反リストが空", _violations, [])
print()

print("[DEP-3] 相対importにlevel>=2（親package方向）が存在しないこと")
for _name, _details in _import_details.items():
    _bad_levels = [imp["level"] for imp in _details["relative_imports"] if imp["level"] >= 2]
    check(f"DEP-3. {_name}の親package方向相対importが空", _bad_levels, [])
print()

# =====================================================================
# SIDE: Side Effect Guard（AST）
# =====================================================================

print("[SIDE-1] print()呼び出しがないこと（ast.Call）")
for _name, _path in FILES.items():
    _calls = get_call_lines(_path, "print")
    check(f"SIDE-1. {_name}にprint()呼び出しがない", _calls, [])
print()

print("[SIDE-2] loggingのimportがないこと（ast.Import／ast.ImportFrom）")
for _name, _details in _import_details.items():
    check_false(f"SIDE-2. {_name}がloggingをimportしない", "logging" in _details["absolute_roots"])
print()

print("[SIDE-3] subprocessのimportがないこと（ast.Import／ast.ImportFrom）")
for _name, _details in _import_details.items():
    check_false(
        f"SIDE-3. {_name}がsubprocessをimportしない", "subprocess" in _details["absolute_roots"]
    )
print()

print("[SIDE-4] open()呼び出しがないこと（ast.Call）")
for _name, _path in FILES.items():
    _calls = get_call_lines(_path, "open")
    check(f"SIDE-4. {_name}にopen()呼び出しがない", _calls, [])
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
