"""
E2E テスト: v6.17.0 Article Image Prompt Construction Foundation

Source of Truth:
    docs/design/article_image_prompt_construction_foundation.md
    （Architecture Review 1：Changes Required → Architecture Amendment：
      Completed → Architecture Review 2：Approved with Suggestions、
      Blocking Issue 0）

本テストは実HTTP・実WordPress投稿・実Media Upload・実画像生成のいずれも
発生させない。construct_article_image_prompt()はConsumer-less Foundation
であり、Production Runtime（main.py／image_resolver.py等）からは一切
呼び出されていない。本テストはすべてtest file内で直接importして呼び出す。

Architecture Review 2 Suggestion AR2-S-1への対応:
    本テストは Production module の private定数（_SUFFIX・_PREFIX・
    _MID・_EXCERPT_LABEL・_EXCERPT_OPEN・_EXCERPT_CLOSE・
    _TRUNCATION_MARKER・_MAX_PROMPT_LENGTH等）や private helper
    （_fit・_normalize・_assemble_title_only）を一切import・呼び出し
    しない。期待値はすべて、設計書（12章・13章・15章）に記載された
    固定literal・固定数値を、本テストファイル内で独立した定数として
    再定義したものを使用する。

実行方法:
    cd projects/03_game_content_ai
    .\\venv\\Scripts\\python.exe tests/test_e2e_v6_17_0_article_image_prompt_construction_foundation.py

Scenario構成:
    PUB-1（Public import／__all__／signature）
    FIELD-1〜3（title-only／title+excerpt／excerpt末尾句点あり）
    WS-1〜4（改行・タブ・連続空白／全角空白／前後空白／\r正規化、Code Review Finding CR-3対応）
    CTRL-1（ASCII control character）
    ZWSP-1（zero-width spaceが保証対象外）
    MARKUP-1（HTML／Markdown非解析）
    UNI-1（Unicode／絵文字）
    TYPE-1〜3（型不正／str subclass受理）
    EMPTY-1〜4（空title／whitespace-only title／空excerpt／whitespace-only excerpt）
    ORDER-1（Validation Order）
    SEC-1（例外messageへの入力値非混入）
    TRUNC-1〜3（excerpt truncation／title truncation／title-only fallback再fit）
    SUFFIX-1（固定suffix完全保持）
    MAXLEN-1〜2（境界長・上限非超過）
    DETERM-1〜2（determinism）
    INVAR-1（Output Invariants）
    NOAPI-1・NOLOG-1〜2・ENV-1・NOFS-1・NOSUB-1・NODYNIMPORT-1・EVAL-1
        （Side Effect Guard）
    STATE-AST-1〜2（State非保持）
    DEP-1〜2（Dependency Guard／Reverse Dependency Guard）
    RUNTIME-1（Runtime Zero Diff、静的テキスト参照ベース）
"""
import ast
import inspect
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ─── テスト用ユーティリティ（v6.9.0〜v6.16.0 precedentを踏襲） ───

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


# ─── AST解析ユーティリティ（v6.9.0〜v6.16.0 precedentを踏襲） ───


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


def get_module_level_assign_names(tree) -> list:
    """module-level（tree.body直下）のAssign／AnnAssignの代入先変数名一覧を返す。"""
    names = []
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.append(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.append(node.target.id)
    return names


def file_references_name(file_path: Path, name: str) -> bool:
    if not file_path.is_file():
        return False
    text = file_path.read_text(encoding="utf-8")
    return name in text


PACKAGE_DIR = PROJECT_ROOT / "src" / "article_image_prompt_construction"
MODULE_PATH = PACKAGE_DIR / "article_image_prompt_construction.py"
INIT_PATH = PACKAGE_DIR / "__init__.py"

MODULE_SOURCE = MODULE_PATH.read_text(encoding="utf-8")
MODULE_TREE = ast.parse(MODULE_SOURCE, filename=str(MODULE_PATH))
MODULE_IMPORTS = get_import_details(MODULE_PATH)
INIT_IMPORTS = get_import_details(INIT_PATH)

import article_image_prompt_construction as _pkg  # noqa: E402
from article_image_prompt_construction import construct_article_image_prompt  # noqa: E402

# ─── Test側で独立に再定義する固定literal（AR2-S-1：Productionのprivate定数はimportしない） ───

_T_PREFIX = "「"
_T_MID = "」というゲームニュース記事のアイキャッチ画像を生成してください。"
_T_EXCERPT_LABEL = "記事概要："
_T_EXCERPT_OPEN = "「"
_T_EXCERPT_CLOSE = "」。"
_T_SUFFIX = (
    "画像内に読める文字、透かし、UIやテキストの"
    "オーバーレイを含めないでください。"
)
_T_MARKER = "…"
_T_MAX_LEN = 1000

print("=" * 60)
print("v6.17.0 Article Image Prompt Construction Foundation E2E")
print("=" * 60)
print()

# =====================================================================
# PUB-1: Public API import
# =====================================================================

print("[PUB-1] Public API import／__all__／signature")

check_true("PUB-1a. construct_article_image_promptがimportできる", "construct_article_image_prompt" in dir())
check_true("PUB-1a. construct_article_image_promptがcallableである", callable(construct_article_image_prompt))
check("PUB-1b. __all__が期待どおり", list(_pkg.__all__), ["construct_article_image_prompt"])

_sig = inspect.signature(construct_article_image_prompt)
_params = list(_sig.parameters.values())
check("PUB-1c. 引数が2個である", len(_params), 2)
check(
    "PUB-1c. 引数名が(title, excerpt)である",
    tuple(p.name for p in _params),
    ("title", "excerpt"),
)
check_true(
    "PUB-1c. *args/**kwargsが存在しない",
    all(
        p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
        for p in _params
    ),
)
print()

# =====================================================================
# FIELD-1〜3: 正常系 exact literal
# =====================================================================

print("[FIELD-1] title-only exact literal")

_title_a = "世界的人気ゲームの新作が発表"
_expected_field1 = _T_PREFIX + _title_a + _T_MID + _T_SUFFIX
check("FIELD-1a.", construct_article_image_prompt(_title_a, ""), _expected_field1)
print()

print("[FIELD-2] title+excerpt exact literal（excerpt末尾句点なし）")

_excerpt_no_period = "発売日や対応プラットフォームが明らかになった"
_expected_field2 = (
    _T_PREFIX + _title_a + _T_MID
    + _T_EXCERPT_LABEL + _T_EXCERPT_OPEN + _excerpt_no_period + _T_EXCERPT_CLOSE
    + _T_SUFFIX
)
check("FIELD-2a.", construct_article_image_prompt(_title_a, _excerpt_no_period), _expected_field2)
print()

print("[FIELD-3] title+excerpt exact literal（excerpt末尾句点あり、句点重複を意図的に許容、AR2-S-3）")

_excerpt_with_period = "発売日や対応プラットフォームが明らかになった。"
_expected_field3 = (
    _T_PREFIX + _title_a + _T_MID
    + _T_EXCERPT_LABEL + _T_EXCERPT_OPEN + _excerpt_with_period + _T_EXCERPT_CLOSE
    + _T_SUFFIX
)
check("FIELD-3a.", construct_article_image_prompt(_title_a, _excerpt_with_period), _expected_field3)
check_true("FIELD-3b. 句点重複（。」。）が意図的に含まれる（設計書13章の許容事項どおり、Production側で重複回避していない）", "。」。" in _expected_field3)
print()

# =====================================================================
# WS-1〜3: 空白正規化
# =====================================================================

print("[WS-1] 改行・タブ・連続半角空白の正規化")

_ws_title = "速報\n\n新作\tゲーム   発表"
_expected_ws1 = _T_PREFIX + "速報 新作 ゲーム 発表" + _T_MID + _T_SUFFIX
check("WS-1a.", construct_article_image_prompt(_ws_title, ""), _expected_ws1)
print()

print("[WS-2] 全角空白（U+3000）の正規化")

_ws2_title = "速報　新作　ゲーム"
_expected_ws2 = _T_PREFIX + "速報 新作 ゲーム" + _T_MID + _T_SUFFIX
check("WS-2a.", construct_article_image_prompt(_ws2_title, ""), _expected_ws2)
print()

print("[WS-3] 前後空白の除去")

_ws3_title = "   速報タイトル   "
_expected_ws3 = _T_PREFIX + "速報タイトル" + _T_MID + _T_SUFFIX
check("WS-3a.", construct_article_image_prompt(_ws3_title, ""), _expected_ws3)
print()

print("[WS-4] \\r（キャリッジリターン）の正規化（Code Review Finding CR-3対応）")

_ws4_title = "速報\r新作ゲーム"
_expected_ws4 = _T_PREFIX + "速報 新作ゲーム" + _T_MID + _T_SUFFIX
_ws4_result = construct_article_image_prompt(_ws4_title, "")
check("WS-4a. exact literal一致（\\rが半角space 1個へ収束）", _ws4_result, _expected_ws4)
check_false("WS-4b. \\rが出力に含まれない", "\r" in _ws4_result)
print()

# =====================================================================
# CTRL-1: ASCII control character
# =====================================================================

print("[CTRL-1] ASCII control characterの正規化")

_ctrl_title = "速報\x07新作"
_expected_ctrl1 = _T_PREFIX + "速報 新作" + _T_MID + _T_SUFFIX
check("CTRL-1a.", construct_article_image_prompt(_ctrl_title, ""), _expected_ctrl1)
print()

# =====================================================================
# ZWSP-1: zero-width spaceが保証対象外
# =====================================================================

print("[ZWSP-1] zero-width space（U+200B）が除去されないことの契約確認")

_zwsp_title = "速報​新作"
_zwsp_result, _zwsp_exc = invoke(construct_article_image_prompt, _zwsp_title, "")
check_true("ZWSP-1a. 例外を送出しない", _zwsp_exc is None)
check_contains("ZWSP-1b. zero-width spaceが除去されずそのまま出力へ残存する", _zwsp_result, "​")
print()

# =====================================================================
# MARKUP-1: HTML／Markdown非解析
# =====================================================================

print("[MARKUP-1] HTML／Markdown markupの非解析（単なる文字列として扱う）")

_markup_title = "<b>速報</b>新作発表"
_expected_markup1 = _T_PREFIX + _markup_title + _T_MID + _T_SUFFIX
check("MARKUP-1a. HTMLタグが除去・解釈されずそのまま埋め込まれる", construct_article_image_prompt(_markup_title, ""), _expected_markup1)
print()

# =====================================================================
# UNI-1: Unicode／絵文字
# =====================================================================

print("[UNI-1] Unicode／絵文字の保持")

_uni_title = "🎮新作ゲーム発表🎉"
_expected_uni1 = _T_PREFIX + _uni_title + _T_MID + _T_SUFFIX
check("UNI-1a.", construct_article_image_prompt(_uni_title, ""), _expected_uni1)
check("UNI-1b. 出力長が期待どおり", len(_expected_uni1), 81)
print()

# =====================================================================
# TYPE-1〜3: 型不正／str subclass受理
# =====================================================================

print("[TYPE-1] title型不正")

_, _type1a_exc = invoke(construct_article_image_prompt, None, "")
check("TYPE-1a.", str(_type1a_exc), "title must be a str")
check("TYPE-1a. 例外型", type(_type1a_exc), ValueError)

_, _type1b_exc = invoke(construct_article_image_prompt, 123, "")
check("TYPE-1b.", str(_type1b_exc), "title must be a str")
print()

print("[TYPE-2] excerpt型不正")

_, _type2a_exc = invoke(construct_article_image_prompt, "タイトル", None)
check("TYPE-2a.", str(_type2a_exc), "excerpt must be a str")
check("TYPE-2a. 例外型", type(_type2a_exc), ValueError)

_, _type2b_exc = invoke(construct_article_image_prompt, "タイトル", 123)
check("TYPE-2b.", str(_type2b_exc), "excerpt must be a str")
print()

print("[TYPE-3] str subclass受理")


class _StrSubclass(str):
    pass


_type3a_result, _type3a_exc = invoke(construct_article_image_prompt, _StrSubclass("タイトル"), "")
check_true("TYPE-3a. titleがstr subclassでも例外を送出しない", _type3a_exc is None)
_type3b_result, _type3b_exc = invoke(construct_article_image_prompt, "タイトル", _StrSubclass("概要"))
check_true("TYPE-3b. excerptがstr subclassでも例外を送出しない", _type3b_exc is None)
print()

# =====================================================================
# EMPTY-1〜4: 空title／空excerpt
# =====================================================================

print("[EMPTY-1] 空title")

_, _empty1_exc = invoke(construct_article_image_prompt, "", "")
check("EMPTY-1a.", str(_empty1_exc), "title must not be blank")
print()

print("[EMPTY-2] whitespace-only title")

_, _empty2_exc = invoke(construct_article_image_prompt, "   \n\t　", "")
check("EMPTY-2a.", str(_empty2_exc), "title must not be blank")
print()

print("[EMPTY-3] 空excerpt（正常値、title-onlyへ収束）")

_empty3_result, _empty3_exc = invoke(construct_article_image_prompt, "タイトル", "")
check_true("EMPTY-3a. 例外を送出しない", _empty3_exc is None)
check("EMPTY-3b.", _empty3_result, _T_PREFIX + "タイトル" + _T_MID + _T_SUFFIX)
print()

print("[EMPTY-4] whitespace-only excerpt（正規化後空、title-onlyへ収束）")

_empty4_result, _empty4_exc = invoke(construct_article_image_prompt, "タイトル", "　\t\n  ")
check_true("EMPTY-4a. 例外を送出しない", _empty4_exc is None)
check("EMPTY-4b.", _empty4_result, _T_PREFIX + "タイトル" + _T_MID + _T_SUFFIX)
print()

# =====================================================================
# ORDER-1: Validation Order
# =====================================================================

print("[ORDER-1] title・excerpt両方が型不正 -> titleのみ")

_, _order1_exc = invoke(construct_article_image_prompt, None, None)
check("ORDER-1a.", str(_order1_exc), "title must be a str")
print()

# =====================================================================
# SEC-1: Security（例外messageへの入力値非混入）
# =====================================================================

print("[SEC-1] 例外messageへの入力値非混入")

_, _sec1a_exc = invoke(construct_article_image_prompt, 999999, "")
check_not_contains("SEC-1a. title型不正例外messageに999999が含まれない", str(_sec1a_exc), "999999")

_, _sec1b_exc = invoke(construct_article_image_prompt, "タイトル", 999999)
check_not_contains("SEC-1b. excerpt型不正例外messageに999999が含まれない", str(_sec1b_exc), "999999")

_secret_excerpt = "SECRET-EXCERPT-VALUE-ZZZ999"
_, _sec1c_exc = invoke(construct_article_image_prompt, "", _secret_excerpt)
check_not_contains(
    "SEC-1c. title blank例外messageにexcerpt値が含まれない",
    str(_sec1c_exc),
    _secret_excerpt,
)
print()

# =====================================================================
# TRUNC-1〜3: Truncation Contract
# =====================================================================

print("[TRUNC-1] excerpt部分truncation（title=テスト, excerpt=あ*2000）")

_trunc1_title = "テスト"
_trunc1_excerpt = "あ" * 2000
# 固定部分（with-excerpt）: PREFIX(1)+MID(32)+LABEL(5)+OPEN(1)+CLOSE(2)+SUFFIX(39)=80
# title_budget = 1000-80=920, fitted_title="テスト"(3, truncationなし)
# remaining = 920-3=917, fitted_excerpt = "あ"*916 + "…"（917文字）
_trunc1_fitted_excerpt = "あ" * 916 + _T_MARKER
_expected_trunc1 = (
    _T_PREFIX + _trunc1_title + _T_MID
    + _T_EXCERPT_LABEL + _T_EXCERPT_OPEN + _trunc1_fitted_excerpt + _T_EXCERPT_CLOSE
    + _T_SUFFIX
)
_trunc1_result = construct_article_image_prompt(_trunc1_title, _trunc1_excerpt)
check("TRUNC-1a. exact literal一致", _trunc1_result, _expected_trunc1)
check("TRUNC-1b. 出力長がちょうど1000", len(_trunc1_result), 1000)
check_true("TRUNC-1c. truncation markerが1個含まれる", _trunc1_result.count(_T_MARKER) == 1)
check_true("TRUNC-1d. titleは切り詰められず完全な形で含まれる", _trunc1_title in _trunc1_result)
print()

print("[TRUNC-2] title-only title truncation（title=あ*2000, excerpt=空）")

_trunc2_title = "あ" * 2000
# 固定部分（title-only）: PREFIX(1)+MID(32)+SUFFIX(39)=72
# title_budget = 1000-72=928, fitted_title = "あ"*927 + "…"（928文字）
_trunc2_fitted_title = "あ" * 927 + _T_MARKER
_expected_trunc2 = _T_PREFIX + _trunc2_fitted_title + _T_MID + _T_SUFFIX
_trunc2_result = construct_article_image_prompt(_trunc2_title, "")
check("TRUNC-2a. exact literal一致", _trunc2_result, _expected_trunc2)
check("TRUNC-2b. 出力長がちょうど1000", len(_trunc2_result), 1000)
check_true("TRUNC-2c. truncation markerが1個含まれる", _trunc2_result.count(_T_MARKER) == 1)
print()

print("[TRUNC-3] title極端に長くexcerptが1文字も入らない -> title-onlyへfallback、title-only budgetで再fit")

_trunc3_title = "い" * 2000
_trunc3_excerpt = "のテスト"
# with-excerpt budget(920)をtitleだけで使い切るためexcerptは1文字も入らず、
# title-only template（budget=928）へfallbackし、titleをbudget 928で再fitする
# （920で切り詰めたtitleを使い回さない）
_trunc3_fitted_title = "い" * 927 + _T_MARKER
_expected_trunc3 = _T_PREFIX + _trunc3_fitted_title + _T_MID + _T_SUFFIX
_trunc3_result = construct_article_image_prompt(_trunc3_title, _trunc3_excerpt)
check("TRUNC-3a. exact literal一致（title-only budgetで再fitされている）", _trunc3_result, _expected_trunc3)
check("TRUNC-3b. 出力長がちょうど1000", len(_trunc3_result), 1000)
check_false("TRUNC-3c. 記事概要セグメントを含まない（title-onlyへ収束している）", "記事概要" in _trunc3_result)
print()

# =====================================================================
# SUFFIX-1: 固定suffix完全保持
# =====================================================================

print("[SUFFIX-1] 固定suffixが常に完全な形で末尾に含まれる")

for _label, _result in [
    ("SUFFIX-1a. FIELD-1", construct_article_image_prompt(_title_a, "")),
    ("SUFFIX-1b. TRUNC-1", _trunc1_result),
    ("SUFFIX-1c. TRUNC-2", _trunc2_result),
    ("SUFFIX-1d. TRUNC-3", _trunc3_result),
]:
    check_true(f"{_label}. 固定suffixで終わる", _result.endswith(_T_SUFFIX))
print()

# =====================================================================
# MAXLEN-1〜2: 長さ上限
# =====================================================================

print("[MAXLEN-1] 境界長（ちょうど1000文字）")

check("MAXLEN-1a. TRUNC-1が1000", len(_trunc1_result), 1000)
check("MAXLEN-1b. TRUNC-2が1000", len(_trunc2_result), 1000)
check("MAXLEN-1c. TRUNC-3が1000", len(_trunc3_result), 1000)
print()

print("[MAXLEN-2] 様々な固定入力でoutputが1000文字を超えない")

_maxlen2_cases = [
    ("速報", ""),
    ("世界的人気ゲームの新作が発表", "発売日や対応プラットフォームが明らかになった"),
    ("あ" * 2000, "い" * 2000),
    ("", ""),
    ("a" * 500, "b" * 500),
]
for _t, _e in _maxlen2_cases:
    if not _t.strip():
        continue
    _r = construct_article_image_prompt(_t, _e)
    check_true(f"MAXLEN-2a. len<=1000 (title先頭10文字={_t[:10]!r})", len(_r) <= _T_MAX_LEN)
print()

# =====================================================================
# DETERM-1〜2: determinism
# =====================================================================

print("[DETERM-1] 同一入力の反復呼び出し")

_determ_results = [construct_article_image_prompt("速報タイトル", "概要テキスト") for _ in range(5)]
check_true("DETERM-1a. 5回とも同一文字列", len(set(_determ_results)) == 1)
print()

print("[DETERM-2] datetime／random／uuid非依存（AST）")

check_true("DETERM-2a. datetimeのimportが存在しない", "datetime" not in MODULE_IMPORTS["absolute_roots"])
check_true("DETERM-2a. randomのimportが存在しない", "random" not in MODULE_IMPORTS["absolute_roots"])
check_true("DETERM-2a. uuidのimportが存在しない", "uuid" not in MODULE_IMPORTS["absolute_roots"])
print()

# =====================================================================
# INVAR-1: Output Invariants
# =====================================================================

print("[INVAR-1] Output Invariants（非空／strip済み／改行・CR・tabなし）")

_invar_cases = [
    construct_article_image_prompt("タイトル", ""),
    construct_article_image_prompt("タイトル", "概要"),
    _trunc1_result,
    _trunc2_result,
    _trunc3_result,
]
for _idx, _r in enumerate(_invar_cases):
    check_true(f"INVAR-1a-{_idx}. output != ''", _r != "")
    check(f"INVAR-1b-{_idx}. output == output.strip()", _r, _r.strip())
    check_false(f"INVAR-1c-{_idx}. 改行を含まない", "\n" in _r)
    check_false(f"INVAR-1d-{_idx}. CRを含まない", "\r" in _r)
    check_false(f"INVAR-1e-{_idx}. tabを含まない", "\t" in _r)
print()

# =====================================================================
# NOAPI-1・NOLOG-1〜2・ENV-1・NOFS-1・NOSUB-1・NODYNIMPORT-1・EVAL-1: Side Effect Guard
# =====================================================================

print("[NOAPI-1] no external API call（AST）")
check_true("NOAPI-1a. requestsのimportが存在しない", "requests" not in MODULE_IMPORTS["absolute_roots"])
check_true("NOAPI-1a. urllibのimportが存在しない", "urllib" not in MODULE_IMPORTS["absolute_roots"])
check_true("NOAPI-1a. openaiのimportが存在しない", "openai" not in MODULE_IMPORTS["absolute_roots"])
check_true("NOAPI-1a. httpのimportが存在しない", "http" not in MODULE_IMPORTS["absolute_roots"])
check_true("NOAPI-1a. socketのimportが存在しない", "socket" not in MODULE_IMPORTS["absolute_roots"])
print()

print("[NOLOG-1] no logging（AST）")
check_true("NOLOG-1a. loggingのimportが存在しない", "logging" not in MODULE_IMPORTS["absolute_roots"])
print()

print("[NOLOG-2] no print（AST）")
check("NOLOG-2a. print()呼び出しが存在しない", get_call_lines(MODULE_PATH, "print"), [])
print()

print("[ENV-1] environment非依存（AST）")
check_true("ENV-1a. osのimportが存在しない", "os" not in MODULE_IMPORTS["absolute_roots"])
check_false("ENV-1b. ソース中にos.environへの言及がない", "environ" in MODULE_SOURCE)
print()

print("[NOFS-1] no file I/O（AST）")
check("NOFS-1a. open()呼び出しが存在しない", get_call_lines(MODULE_PATH, "open"), [])
check_true("NOFS-1b. pathlibのimportが存在しない", "pathlib" not in MODULE_IMPORTS["absolute_roots"])
check_true("NOFS-1c. ioのimportが存在しない", "io" not in MODULE_IMPORTS["absolute_roots"])
print()

print("[NOSUB-1] no subprocess（AST）")
check_true("NOSUB-1a. subprocessのimportが存在しない", "subprocess" not in MODULE_IMPORTS["absolute_roots"])
print()

print("[NODYNIMPORT-1] no dynamic import（AST）")
check_true("NODYNIMPORT-1a. importlibのimportが存在しない", "importlib" not in MODULE_IMPORTS["absolute_roots"])
check("NODYNIMPORT-1b. __import__()呼び出しが存在しない", get_call_lines(MODULE_PATH, "__import__"), [])
print()

print("[EVAL-1] no eval／exec（AST）")
check("EVAL-1a. eval()呼び出しが存在しない", get_call_lines(MODULE_PATH, "eval"), [])
check("EVAL-1b. exec()呼び出しが存在しない", get_call_lines(MODULE_PATH, "exec"), [])
print()

# =====================================================================
# STATE-AST-1〜2: State非保持（AST）
# =====================================================================

print("[STATE-AST-1] global／nonlocal非使用（AST）")
_global_violations = [n.lineno for n in ast.walk(MODULE_TREE) if isinstance(n, ast.Global)]
_nonlocal_violations = [n.lineno for n in ast.walk(MODULE_TREE) if isinstance(n, ast.Nonlocal)]
check("STATE-AST-1a. ast.Globalが存在しない", _global_violations, [])
check("STATE-AST-1a. ast.Nonlocalが存在しない", _nonlocal_violations, [])
print()

print("[STATE-AST-2] module-level定数の重複代入なし（AST）")
_assign_names = get_module_level_assign_names(MODULE_TREE)
check_true("STATE-AST-2a. module-level定数が1件以上存在する", len(_assign_names) > 0)
check(
    "STATE-AST-2b. module-level定数名に重複がない（各定数は1回のみ代入される）",
    len(_assign_names),
    len(set(_assign_names)),
)
print()

# =====================================================================
# DEP-1〜2: Dependency Guard／Reverse Dependency Guard
# =====================================================================

print("[DEP-1] Dependency Guard")
_module_forbidden = MODULE_IMPORTS["absolute_roots"] - {"re"}
check("DEP-1a. re以外のimportが存在しない", _module_forbidden, set())
check(
    "DEP-1b. __init__.pyは自module内相対import以外の絶対importを持たない",
    INIT_IMPORTS["absolute_roots"],
    set(),
)
check_true("DEP-1c. reのimportが存在する", "re" in MODULE_IMPORTS["absolute_roots"])
print()

print("[DEP-2] Reverse Dependency Guard")
_reverse_dir_targets = [
    ("DEP-2a", "src/outputs", PROJECT_ROOT / "src" / "outputs"),
    ("DEP-2b", "src/ai_image_generation", PROJECT_ROOT / "src" / "ai_image_generation"),
    ("DEP-2c", "src/openai_image_generation", PROJECT_ROOT / "src" / "openai_image_generation"),
    ("DEP-2d", "src/wordpress_media", PROJECT_ROOT / "src" / "wordpress_media"),
    ("DEP-2e", "src/generated_image_wordpress_media", PROJECT_ROOT / "src" / "generated_image_wordpress_media"),
    ("DEP-2f", "src/article_featured_media", PROJECT_ROOT / "src" / "article_featured_media"),
    ("DEP-2g", "src/article_featured_media_orchestration", PROJECT_ROOT / "src" / "article_featured_media_orchestration"),
    ("DEP-2h", "src/image_generation_config", PROJECT_ROOT / "src" / "image_generation_config"),
    ("DEP-2i", "src/generated_image_filename_policy", PROJECT_ROOT / "src" / "generated_image_filename_policy"),
    ("DEP-2j", "src/ai", PROJECT_ROOT / "src" / "ai"),
]
for _case_id, _label, _dir_path in _reverse_dir_targets:
    _py_files = sorted(_dir_path.glob("*.py")) if _dir_path.is_dir() else []
    check_true(f"{_case_id}. {_label} 配下に.pyファイルが1件以上存在する（vacuous pass防止）", len(_py_files) > 0)
    _violating = [f.name for f in _py_files if file_references_name(f, "article_image_prompt_construction")]
    check(f"{_case_id}. {_label} がarticle_image_prompt_constructionをimportしていない", _violating, [])
print()

# =====================================================================
# RUNTIME-1: Runtime Zero Diff（静的テキスト参照ベース、AR-M-4対応）
# =====================================================================

print("[RUNTIME-1] Runtime Zero Diff（main.py／image_resolver.py／Orchestratorの静的参照確認）")
_runtime_targets = [
    ("RUNTIME-1a", "main.py", PROJECT_ROOT / "main.py"),
    ("RUNTIME-1b", "src/image_resolver.py", PROJECT_ROOT / "src" / "image_resolver.py"),
    (
        "RUNTIME-1c",
        "src/article_featured_media_orchestration/article_featured_media_orchestrator.py",
        PROJECT_ROOT / "src" / "article_featured_media_orchestration" / "article_featured_media_orchestrator.py",
    ),
]
for _case_id, _label, _path in _runtime_targets:
    check_false(
        f"{_case_id}. {_label}がarticle_image_prompt_constructionをimportしていない",
        file_references_name(_path, "article_image_prompt_construction"),
    )
print(
    "  ※ main.py／image_resolver.py等への実バイト差分（git diff）の確認は"
    "本テストの対象外であり、Review／Release工程内で別途実施する"
    "（設計書22章 Runtime Zero Diff Verification方針）。"
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
