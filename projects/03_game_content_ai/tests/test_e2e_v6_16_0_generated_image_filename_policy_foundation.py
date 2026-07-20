"""
E2E テスト: v6.16.0 Generated Image Filename Policy Foundation

Source of Truth:
    docs/design/generated_image_filename_policy_foundation.md
    （Architecture Review：Approved／Architecture Amendment：Approved、
      いずれもBlocking Issueなし。19章確定Inventory：60 Scenario・
      104 Case・143 Assertion）

本テストは実HTTP・実WordPress投稿・実Media Upload・実画像生成のいずれも発生させない。
generate_image_filename()はConsumer-less Foundationであり、Production Runtime
（main.py／image_resolver.py等）からは一切呼び出されていない。本テストはすべて
test file内で直接importして呼び出す。

hash期待値はProduction関数から生成せず、設計書10.5.2節に記載の実測値
（hashlib.sha256(title.encode("utf-8")).hexdigest()[:8]をtest作成時に
事前計算したliteral）をそのまま使用する。

Scenario構成（60 Scenario）:
    PUB-1（Public import）
    SIG-1（signature）
    NORM-1〜4（正規化：ASCII／mixed case／punctuation／repeated separators）
    UNI-1〜2（Japanese／Unicode title）
    EMPTY-1〜2（empty／whitespace title）
    CTRL-1〜2（control characters）
    WIN-1〜3（Windows予約文字／予約デバイス名／境界）
    SLASH-1〜2（slash／backslash）
    DOT-1〜2（dot／space edge cases）
    LEN-1〜2（maximum length／境界）
    FALLBACK-1（fallback basename）
    HASH-1〜3・LONGUNI-1・HASH-ENV-1（Architecture Amendment新規）
    MIME-1〜10（拡張子マッピング／unsupported／case／whitespace／parameter／空）
    TYPE-1〜3（invalid type／str subclass）
    ORDER-1〜3（Validation Order）
    DETERM-1〜2（determinism）
    BASENAME-1〜2（no path traversal／絶対path）
    EXT-1・NONEMPTY-1（extension Contract／非空保証）
    NOAPI-1・NOLOG-1〜2・ENV-1・NOFS-1（Side Effect Guard）
    STATE-AST-1〜2（State非保持）
    DEP-1〜2（Dependency Guard／Reverse Dependency Guard）
    RUNTIME-1（Runtime Zero Diff）
    SEC-1（Security：例外message）

実行方法:
    cd projects/03_game_content_ai
    python tests/test_e2e_v6_16_0_generated_image_filename_policy_foundation.py
"""
import ast
import inspect
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ─── テスト用ユーティリティ（v6.9.0〜v6.15.0 precedentを踏襲） ───

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


def invoke(func, *args, **kwargs):
    """funcを呼び出し、(戻り値, 例外)のタプルを返す。例外がなければ(結果, None)。"""
    try:
        return func(*args, **kwargs), None
    except BaseException as exc:
        return None, exc


# ─── AST解析ユーティリティ（v6.9.0〜v6.15.0 precedentを踏襲） ───


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


def get_module_level_assign_lines(tree) -> list:
    """module-level（tree.body直下）のAssign／AnnAssign／AugAssignの行番号一覧を返す。"""
    lines = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            lines.append(node.lineno)
    return lines


def file_references_name(file_path: Path, name: str) -> bool:
    if not file_path.is_file():
        return False
    text = file_path.read_text(encoding="utf-8")
    return name in text


PACKAGE_DIR = PROJECT_ROOT / "src" / "generated_image_filename_policy"
MODULE_PATH = PACKAGE_DIR / "generated_image_filename_policy.py"
INIT_PATH = PACKAGE_DIR / "__init__.py"

MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")
MODULE_TREE = ast.parse(MODULE_SOURCE, filename=str(MODULE_PATH))
MODULE_IMPORTS = get_import_details(MODULE_PATH)
INIT_IMPORTS = get_import_details(INIT_PATH)

from generated_image_filename_policy import generate_image_filename  # noqa: E402

print("=" * 60)
print("v6.16.0 Generated Image Filename Policy Foundation E2E")
print("=" * 60)
print()

# =====================================================================
# PUB-1: Public API import
# =====================================================================

print("[PUB-1] Public API import")

check_true("PUB-1a. generate_image_filenameがimportできる", "generate_image_filename" in dir())
check_true("PUB-1a. generate_image_filenameがcallableである", callable(generate_image_filename))
print()

# =====================================================================
# SIG-1: signature
# =====================================================================

print("[SIG-1] Public API signature")

_sig = inspect.signature(generate_image_filename)
_params = list(_sig.parameters.values())
check("SIG-1a. 引数が2個である", len(_params), 2)
check(
    "SIG-1a. 引数名が(title, mime_type)である",
    tuple(p.name for p in _params),
    ("title", "mime_type"),
)
check_true(
    "SIG-1a. *args/**kwargsが存在しない",
    all(
        p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        for p in _params
    ),
)
print()

# =====================================================================
# NORM-1〜4: title正規化
# =====================================================================

print("[NORM-1] normal ASCII title")
check("NORM-1a.", generate_image_filename("Hello World", "image/png"), "hello-world.png")
check("NORM-1b.", generate_image_filename("PS5 Pro Review", "image/png"), "ps5-pro-review.png")
print()

print("[NORM-2] mixed case")
check("NORM-2a.", generate_image_filename("HELLO World", "image/png"), "hello-world.png")
check("NORM-2b.", generate_image_filename("PlayStation5", "image/png"), "playstation5.png")
print()

print("[NORM-3] punctuation／spaces")
check("NORM-3a.", generate_image_filename("Hello, World!", "image/png"), "hello-world.png")
check("NORM-3b.", generate_image_filename("Foo/Bar?", "image/png"), "foobar.png")
check("NORM-3c.", generate_image_filename("A (Big) Update", "image/png"), "a-big-update.png")
print()

print("[NORM-4] repeated separators")
check("NORM-4a.", generate_image_filename("Hello   World", "image/png"), "hello-world.png")
check("NORM-4b.", generate_image_filename("Foo!!!Bar", "image/png"), "foobar.png")
print()

# =====================================================================
# UNI-1〜2: Japanese／Unicode title
# =====================================================================

print("[UNI-1] Japanese-only title -> hash付きfallback")
check("UNI-1a.", generate_image_filename("速報】新作発表", "image/png"), "generated-image-de4b4035.png")
print()

print("[UNI-2] Japanese + ASCII混在")
check("UNI-2a.", generate_image_filename("速報 Nintendo Direct", "image/png"), "nintendo-direct.png")
check("UNI-2b.", generate_image_filename("PS5【新型】発表", "image/png"), "ps5.png")
print()

# =====================================================================
# EMPTY-1〜2: empty／whitespace title
# =====================================================================

print("[EMPTY-1] empty title -> hash付きfallback")
check("EMPTY-1a.", generate_image_filename("", "image/png"), "generated-image-e3b0c442.png")
print()

print("[EMPTY-2] whitespace-only title -> hash付きfallback")
check("EMPTY-2a.", generate_image_filename("   ", "image/png"), "generated-image-0aad7da7.png")
check("EMPTY-2b.", generate_image_filename("　　", "image/png"), "generated-image-aa27d704.png")
print()

# =====================================================================
# CTRL-1〜2: control characters
# =====================================================================

print("[CTRL-1] control characters除去")
check("CTRL-1a.", generate_image_filename("foo\x00bar", "image/png"), "foobar.png")
check("CTRL-1b.", generate_image_filename("foo\x1bbar", "image/png"), "foobar.png")
print()

print("[CTRL-2] tab／newline／CR -> separator")
check("CTRL-2a.", generate_image_filename("foo\tbar", "image/png"), "foo-bar.png")
check("CTRL-2b.", generate_image_filename("foo\nbar", "image/png"), "foo-bar.png")
print()

# =====================================================================
# WIN-1〜3: Windows予約文字／予約デバイス名／境界
# =====================================================================

print("[WIN-1] Windows予約文字除去")
check("WIN-1a.", generate_image_filename("foo<>:bar", "image/png"), "foobar.png")
check("WIN-1b.", generate_image_filename("foo | bar ? baz * qux", "image/png"), "foo-bar-baz-qux.png")
print()

print("[WIN-2] Windows予約デバイス名回避")
check("WIN-2a.", generate_image_filename("CON", "image/png"), "con-image.png")
check("WIN-2b.", generate_image_filename("con", "image/png"), "con-image.png")
check("WIN-2c.", generate_image_filename("Aux", "image/png"), "aux-image.png")
check("WIN-2d.", generate_image_filename("com1", "image/png"), "com1-image.png")
print()

print("[WIN-3] 予約名境界（対象外の確認）")
check("WIN-3a.", generate_image_filename("COM0", "image/png"), "com0.png")
check("WIN-3b.", generate_image_filename("COM10", "image/png"), "com10.png")
check("WIN-3c.", generate_image_filename("conquest", "image/png"), "conquest.png")
print()

# =====================================================================
# SLASH-1〜2: slash／backslash
# =====================================================================

print("[SLASH-1] forward slash除去")
check("SLASH-1a.", generate_image_filename("foo/bar", "image/png"), "foobar.png")
check("SLASH-1b.", generate_image_filename("foo / bar", "image/png"), "foo-bar.png")
print()

print("[SLASH-2] backslash／traversal様入力")
check("SLASH-2a.", generate_image_filename("..\\..\\etc\\passwd", "image/png"), "etcpasswd.png")
check("SLASH-2b.", generate_image_filename("../../secret", "image/png"), "secret.png")
print()

# =====================================================================
# DOT-1〜2: dot／space edge cases
# =====================================================================

print("[DOT-1] leading／trailing dot")
check("DOT-1a.", generate_image_filename(".hidden title.", "image/png"), "hidden-title.png")
check("DOT-1b.", generate_image_filename("...triple...", "image/png"), "triple.png")
print()

print("[DOT-2] leading／trailing space")
check("DOT-2a.", generate_image_filename("  padded title  ", "image/png"), "padded-title.png")
check("DOT-2b.", generate_image_filename("　padded", "image/png"), "padded.png")
print()

# =====================================================================
# LEN-1〜2: maximum length／境界
# =====================================================================

print("[LEN-1] 長いtitleの単語境界truncate")
_len1_title = (
    "alpha bravo charlie delta echo foxtrot golf hotel india "
    "juliet kilomega november oscar"
)
_len1_result = generate_image_filename(_len1_title, "image/png")
check(
    "LEN-1a. 単語境界でtruncateされた正確な値",
    _len1_result,
    "alpha-bravo-charlie-delta-echo-foxtrot-golf-hotel-india.png",
)
check_true(
    "LEN-1a. slug部分がlen()<=60である",
    len(_len1_result.rsplit(".", 1)[0]) <= 60,
)
print()

print("[LEN-2] maximum length境界（60文字／61文字）")
_w60 = "a" * 60
_w61 = "a" * 61
_len2a_result = generate_image_filename(_w60, "image/png")
check("LEN-2a. ちょうど60文字は切り詰められない", _len2a_result, ("a" * 60) + ".png")
_len2b_result = generate_image_filename(_w61, "image/png")
check("LEN-2b. 61文字はhard-cutで60文字になる", _len2b_result, ("a" * 60) + ".png")
check_true("LEN-2b. 戻り値全体がlen()<=65である", len(_len2b_result) <= 65)
print()

# =====================================================================
# FALLBACK-1: fallback basename
# =====================================================================

print("[FALLBACK-1] 記号のみ／絵文字のみ -> hash付きfallback")
check("FALLBACK-1a.", generate_image_filename("!!!@@@###", "image/png"), "generated-image-509ee51c.png")
check("FALLBACK-1b.", generate_image_filename("\U0001F3AE\U0001F579️", "image/png"), "generated-image-15b257f2.png")
print()

# =====================================================================
# HASH-1〜3・LONGUNI-1・HASH-ENV-1: Architecture Amendment新規
# =====================================================================

print("[HASH-1] hash差別化（異なる日本語titleは異なるfallback）")
_hash1_a = generate_image_filename("速報】新作発表", "image/png")
_hash1_b = generate_image_filename("速報２】新作発表", "image/png")
check_true("HASH-1a. 異なるtitleは異なる戻り値", _hash1_a != _hash1_b)
print()

print("[HASH-2] hash決定性（同一titleは同一fallback）")
_hash2_first = generate_image_filename("速報】新作発表", "image/png")
_hash2_second = generate_image_filename("速報】新作発表", "image/png")
check("HASH-2a. 2回とも同一文字列", (_hash2_first, _hash2_second), ("generated-image-de4b4035.png", "generated-image-de4b4035.png"))
print()

print("[HASH-3] hash形式（小文字hex8桁）")
_hash_suffix_pattern = re.compile(r"^generated-image-[0-9a-f]{8}\.png$")
_hash3_targets = [
    generate_image_filename("速報】新作発表", "image/png"),
    generate_image_filename("", "image/png"),
    generate_image_filename("   ", "image/png"),
    generate_image_filename("　　", "image/png"),
    generate_image_filename("!!!@@@###", "image/png"),
]
check_true(
    "HASH-3a. いずれもgenerated-image-<8桁小文字hex>.png形式",
    all(_hash_suffix_pattern.fullmatch(v) for v in _hash3_targets),
)
print()

print("[LONGUNI-1] long Unicode title")
_long_jp = ("速報】ゲーム業界の最新ニュースまとめ、新作タイトルの発売日と価格が判明した件について徹底解説する記事です" * 3)
_longuni_result = generate_image_filename(_long_jp, "image/png")
check("LONGUNI-1a. UTF-8実測hash値と一致", _longuni_result, "generated-image-7aa76c4f.png")
_longuni_hash_part = _longuni_result[len("generated-image-"):-len(".png")]
check("LONGUNI-1a. hash部分が常に8文字", len(_longuni_hash_part), 8)
print()

print("[HASH-ENV-1] environment／locale非依存（AST）")
check_true("HASH-ENV-1a. localeのimportが存在しない", "locale" not in MODULE_IMPORTS["absolute_roots"])
print()

# =====================================================================
# MIME-1〜10: MIME typeマッピング／unsupported／case／whitespace／parameter／空
# =====================================================================

print("[MIME-1] image/png -> .png")
check("MIME-1a.", generate_image_filename("Foo", "image/png"), "foo.png")
print()

print("[MIME-2] image/jpeg -> .jpg")
check("MIME-2a.", generate_image_filename("Foo", "image/jpeg"), "foo.jpg")
print()

print("[MIME-3] image/webp -> .webp")
check("MIME-3a.", generate_image_filename("Foo", "image/webp"), "foo.webp")
print()

print("[MIME-4] image/gif -> .gif")
check("MIME-4a.", generate_image_filename("Foo", "image/gif"), "foo.gif")
print()


def check_mime_value_error(label: str, mime_type):
    _, exc = invoke(generate_image_filename, "Foo", mime_type)
    check_true(f"{label} ValueErrorが送出される", isinstance(exc, ValueError))
    check(f"{label} messageが固定文言と一致", str(exc), "mime_type is not a supported image type")


print("[MIME-5] 非canonical（\"jpg\"誤記）")
check_mime_value_error("MIME-5a.", "image/jpg")
print()

print("[MIME-6] unsupported（allow-list外）")
check_mime_value_error("MIME-6a.", "image/tiff")
check_mime_value_error("MIME-6b.", "image/svg+xml")
print()

print("[MIME-7] MIME case（大文字）")
check_mime_value_error("MIME-7a.", "IMAGE/PNG")
check_mime_value_error("MIME-7b.", "Image/Png")
print()

print("[MIME-8] MIME whitespace")
check_mime_value_error("MIME-8a.", " image/png ")
check_mime_value_error("MIME-8b.", "image/png\n")
print()

print("[MIME-9] MIME parameter付き")
check_mime_value_error("MIME-9a.", "image/png; charset=binary")
check_mime_value_error("MIME-9b.", "image/jpeg;q=0.9")
print()

print("[MIME-10] MIME空文字／空白")
check_mime_value_error("MIME-10a.", "")
check_mime_value_error("MIME-10b.", "   ")
print()

# =====================================================================
# TYPE-1〜3: invalid type／str subclass
# =====================================================================


def check_title_type_error(label: str, title):
    _, exc = invoke(generate_image_filename, title, "image/png")
    check_true(f"{label} ValueErrorが送出される", isinstance(exc, ValueError))
    check(f"{label} messageが固定文言と一致", str(exc), "title must be a str")


def check_mime_type_type_error(label: str, mime_type):
    _, exc = invoke(generate_image_filename, "Foo", mime_type)
    check_true(f"{label} ValueErrorが送出される", isinstance(exc, ValueError))
    check(f"{label} messageが固定文言と一致", str(exc), "mime_type must be a str")


print("[TYPE-1] invalid title type")
check_title_type_error("TYPE-1a.", None)
check_title_type_error("TYPE-1b.", 123)
check_title_type_error("TYPE-1c.", b"bytes")
check_title_type_error("TYPE-1d.", ["list"])
print()

print("[TYPE-2] invalid mime_type type")
check_mime_type_type_error("TYPE-2a.", None)
check_mime_type_type_error("TYPE-2b.", 123)
check_mime_type_type_error("TYPE-2c.", b"image/png")
print()

print("[TYPE-3] str subclass受理")


class _StrSubclass(str):
    pass


_type3a_result, _type3a_exc = invoke(generate_image_filename, _StrSubclass("Foo"), "image/png")
check_true("TYPE-3a. titleがstr subclassでも例外を送出しない", _type3a_exc is None)
_type3b_result, _type3b_exc = invoke(generate_image_filename, "Foo", _StrSubclass("image/png"))
check_true("TYPE-3b. mime_typeがstr subclassでも例外を送出しない", _type3b_exc is None)
print()

# =====================================================================
# ORDER-1〜3: Validation Order
# =====================================================================

print("[ORDER-1] title・mime_type両方が型不正 -> titleのみ")
_, _order1_exc = invoke(generate_image_filename, None, None)
check("ORDER-1a.", str(_order1_exc), "title must be a str")
print()

print("[ORDER-2] titleが正当・mime_typeが型不正")
_, _order2_exc = invoke(generate_image_filename, "Foo", None)
check("ORDER-2a.", str(_order2_exc), "mime_type must be a str")
print()

print("[ORDER-3] titleがfallback対象・mime_typeがunsupported")
_, _order3_exc = invoke(generate_image_filename, "", "image/tiff")
check("ORDER-3a.", str(_order3_exc), "mime_type is not a supported image type")
print()

# =====================================================================
# DETERM-1〜2: determinism
# =====================================================================

print("[DETERM-1] 同一入力の反復呼び出し")
_determ_results = [generate_image_filename("Foo Bar", "image/png") for _ in range(5)]
check_true("DETERM-1a. 5回とも同一文字列", len(set(_determ_results)) == 1)
print()

print("[DETERM-2] datetime／random／uuid非依存（AST）")
check_true("DETERM-2a. datetimeのimportが存在しない", "datetime" not in MODULE_IMPORTS["absolute_roots"])
check_true("DETERM-2a. randomのimportが存在しない", "random" not in MODULE_IMPORTS["absolute_roots"])
check_true("DETERM-2a. uuidのimportが存在しない", "uuid" not in MODULE_IMPORTS["absolute_roots"])
print()

# =====================================================================
# BASENAME-1〜2: no path traversal／絶対path
# =====================================================================

print("[BASENAME-1] no path traversal")
_basename_targets = [
    generate_image_filename("Hello World", "image/png"),
    generate_image_filename("..\\..\\etc\\passwd", "image/png"),
    generate_image_filename("../../secret", "image/png"),
    generate_image_filename("速報】新作発表", "image/png"),
    generate_image_filename("", "image/png"),
]
check_true(
    "BASENAME-1a. いずれも / や \\ を含まない",
    all(("/" not in v and "\\" not in v) for v in _basename_targets),
)
print()

print("[BASENAME-2] no absolute path")
check_true(
    "BASENAME-2a. いずれも先頭が / でない",
    all(not v.startswith("/") for v in _basename_targets),
)
check_true(
    "BASENAME-2a. いずれも : を含まない",
    all(":" not in v for v in _basename_targets),
)
print()

# =====================================================================
# EXT-1・NONEMPTY-1: extension Contract／非空保証
# =====================================================================

print("[EXT-1] extension Contract")
_ext_targets = [
    generate_image_filename("Foo", "image/png"),
    generate_image_filename("Foo", "image/jpeg"),
    generate_image_filename("Foo", "image/webp"),
    generate_image_filename("Foo", "image/gif"),
]
_allowed_extensions = {"png", "jpg", "webp", "gif"}
check_true(
    "EXT-1a. 拡張子がallow-list4値のいずれかに一致し、dotが1個のみ",
    all(v.count(".") == 1 and v.rsplit(".", 1)[1] in _allowed_extensions for v in _ext_targets),
)
print()

print("[NONEMPTY-1] 非空保証")
_nonempty_targets = _basename_targets + _ext_targets
check_true("NONEMPTY-1a. いずれも空文字列でない", all(len(v) > 0 for v in _nonempty_targets))
print()

# =====================================================================
# NOAPI-1・NOLOG-1〜2・ENV-1・NOFS-1: Side Effect Guard
# =====================================================================

print("[NOAPI-1] no external API call（AST）")
check_true("NOAPI-1a. requestsのimportが存在しない", "requests" not in MODULE_IMPORTS["absolute_roots"])
check_true("NOAPI-1a. urllibのimportが存在しない", "urllib" not in MODULE_IMPORTS["absolute_roots"])
check_true("NOAPI-1a. openaiのimportが存在しない", "openai" not in MODULE_IMPORTS["absolute_roots"])
print()

print("[NOLOG-1] no logging（AST）")
check_true("NOLOG-1a. loggingのimportが存在しない", "logging" not in MODULE_IMPORTS["absolute_roots"])
print()

print("[NOLOG-2] no print（AST）")
check("NOLOG-2a. print()呼び出しが存在しない", get_call_lines(MODULE_PATH, "print"), [])
print()

print("[ENV-1] environment non-dependency（AST）")
check_true("ENV-1a. osのimportが存在しない", "os" not in MODULE_IMPORTS["absolute_roots"])
print()

print("[NOFS-1] no file I/O／非決定的依存（AST）")
check("NOFS-1a. open()呼び出しが存在しない", get_call_lines(MODULE_PATH, "open"), [])
check_true("NOFS-1a. mimetypesのimportが存在しない", "mimetypes" not in MODULE_IMPORTS["absolute_roots"])
print()

# =====================================================================
# STATE-AST-1〜2: State非保持（AST）
# =====================================================================

print("[STATE-AST-1] module-level state非保持（AST）")
check("STATE-AST-1a. module-levelのAssign文が存在しない", get_module_level_assign_lines(MODULE_TREE), [])
print()

print("[STATE-AST-2] global／nonlocal非使用（AST）")
_global_violations = [n.lineno for n in ast.walk(MODULE_TREE) if isinstance(n, ast.Global)]
_nonlocal_violations = [n.lineno for n in ast.walk(MODULE_TREE) if isinstance(n, ast.Nonlocal)]
check("STATE-AST-2a. ast.Globalが存在しない", _global_violations, [])
check("STATE-AST-2a. ast.Nonlocalが存在しない", _nonlocal_violations, [])
print()

# =====================================================================
# DEP-1〜2: Dependency Guard／Reverse Dependency Guard
# =====================================================================

print("[DEP-1] Dependency Guard")
_module_forbidden = MODULE_IMPORTS["absolute_roots"] - {"re", "hashlib"}
check("DEP-1a. re／hashlib以外のimportが存在しない", _module_forbidden, set())
check(
    "DEP-1b. __init__.pyは自module内相対import以外の絶対importを持たない",
    INIT_IMPORTS["absolute_roots"],
    set(),
)
check_true("DEP-1c. hashlibのimportが存在する", "hashlib" in MODULE_IMPORTS["absolute_roots"])
print()

print("[DEP-2] Reverse Dependency Guard")
_reverse_targets = [
    ("DEP-2a", "src/outputs", PROJECT_ROOT / "src" / "outputs"),
    ("DEP-2b", "src/ai_image_generation", PROJECT_ROOT / "src" / "ai_image_generation"),
    ("DEP-2c", "src/wordpress_media", PROJECT_ROOT / "src" / "wordpress_media"),
    ("DEP-2d", "src/generated_image_wordpress_media", PROJECT_ROOT / "src" / "generated_image_wordpress_media"),
    ("DEP-2e", "src/article_featured_media", PROJECT_ROOT / "src" / "article_featured_media"),
    ("DEP-2f", "src/article_featured_media_orchestration", PROJECT_ROOT / "src" / "article_featured_media_orchestration"),
    ("DEP-2g", "src/image_generation_config", PROJECT_ROOT / "src" / "image_generation_config"),
    ("DEP-2h", "src/openai_image_generation", PROJECT_ROOT / "src" / "openai_image_generation"),
]
for _case_id, _label, _dir_path in _reverse_targets:
    _py_files = sorted(_dir_path.glob("*.py")) if _dir_path.is_dir() else []
    check_true(f"{_case_id}. {_label} 配下に.pyファイルが1件以上存在する（vacuous pass防止）", len(_py_files) > 0)
    _violating = [f.name for f in _py_files if file_references_name(f, "generated_image_filename_policy")]
    check(f"{_case_id}. {_label} がgenerated_image_filename_policyをimportしていない", _violating, [])
print()

# =====================================================================
# RUNTIME-1: Runtime Zero Diff
# =====================================================================

print("[RUNTIME-1] Runtime Zero Diff")
_runtime_targets = [
    ("RUNTIME-1a", "main.py", PROJECT_ROOT / "main.py"),
    ("RUNTIME-1b", "src/image_resolver.py", PROJECT_ROOT / "src" / "image_resolver.py"),
]
for _case_id, _label, _path in _runtime_targets:
    check_false(
        f"{_case_id}. {_label}がgenerated_image_filename_policyをimportしていない",
        file_references_name(_path, "generated_image_filename_policy"),
    )
print()

# =====================================================================
# SEC-1: Security（例外message）
# =====================================================================

print("[SEC-1] Security：例外messageへの値の非混入")

_, _sec1a_exc = invoke(generate_image_filename, 999999, "image/png")
check_not_contains("SEC-1a. title型不正例外messageに999999が含まれない", str(_sec1a_exc), "999999")

_, _sec1b_exc = invoke(generate_image_filename, "Foo", 999999)
check_not_contains("SEC-1b. mime_type型不正例外messageに999999が含まれない", str(_sec1b_exc), "999999")

_, _sec1c_exc = invoke(generate_image_filename, "Foo", "image/x-secret-format-zzz")
check_not_contains(
    "SEC-1c. unsupported mime_type例外messageにimage/x-secret-format-zzzが含まれない",
    str(_sec1c_exc),
    "image/x-secret-format-zzz",
)
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
