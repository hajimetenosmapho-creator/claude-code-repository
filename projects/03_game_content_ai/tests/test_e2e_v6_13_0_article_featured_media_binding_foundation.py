"""
E2E テスト: v6.13.0 Article Featured Media Binding Foundation

Source of Truth:
    docs/design/article_featured_media_binding_foundation.md
    （Architecture Review：Approved、Blocking Issueなし。
      Minor 2件・Suggestion 2件はいずれもNon-Blockingで、本Releaseの
      Implementation工程で正式設計書へ反映済み。AR-m-1〜AR-S-2参照）

本テストは実HTTP・実WordPress投稿・実Media Upload・実画像生成のいずれも発生させない。
bind_featured_media()はConsumer-less Foundationであり、Production Runtime（main.py／
image_resolver.py／wordpress_output.py等）からは一切呼び出されていない。本テストは
すべてtest file内で直接importして呼び出す。

Scenario構成（24 Scenario）:
    PUB-1（Public import Contract）
    SIG-1（Public signature Contract）
    BIND-1（正常Binding）
    MUT-1（元ArticleData非mutation：Runtime、全field snapshot比較）
    OBJ-1（戻り値別object）
    FIELD-1（featured_media_id以外の全field維持）
    ITEM-1（nested object item参照維持）
    ID-1/2/3（既存featured_media_id：0／同一／異なる）
    VAL-1（article型不正）
    VAL-2（media_result型不正）
    VAL-3（media_id bool拒否）
    VAL-4（media_id非int拒否）
    VAL-5（media_id == 0拒否）
    VAL-6（media_id負数拒否）
    ORDER-1/2/3（Validation Order）
    SEC-1（例外message Security）
    STATE-1（連続呼び出し独立性：Runtime）
    DETERM-1（同一入力の決定性）
    STATE-AST-1（module-level state非保持：module-level Assign／ast.Global／
        ast.Nonlocal検出、Architecture Review Finding AR-m-2反映）
    MUT-AST-1（article入力objectへの属性代入非存在：Source Guard、補助）
    SIDE-1（Side Effect Guard：import／call）
    DEP-1（許可依存Guard）
    DEP-2（逆依存Guard：Architecture Review Finding AR-S-1反映、vacuous pass防止）
    RUNTIME-1（Production Runtime未接続Guard）

Regressionは本ファイルのScenario数に含まない（26章のRegression Test Strategy参照）。

実行方法:
    cd projects/03_game_content_ai
    python tests/test_e2e_v6_13_0_article_featured_media_binding_foundation.py
"""
import ast
import inspect
import sys
from dataclasses import fields
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ─── テスト用ユーティリティ（v6.9.0〜v6.12.0 precedentを踏襲） ───

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


# ─── AST解析ユーティリティ（v6.9.0〜v6.12.0 precedentを踏襲） ───


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


def find_function_def(tree, function_name: str):
    """module-level（tree.body直下）のFunctionDefのみを対象とする。"""
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            return node
    return None


def get_module_level_assign_lines(tree) -> list:
    """module-level（tree.body直下）のAssign／AnnAssign／AugAssignの行番号一覧を返す。"""
    lines = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            lines.append(node.lineno)
    return lines


def find_global_nonlocal_violations(func_node) -> list:
    """func_node（ast.FunctionDef）のbody以下を再帰的に走査し、
    ast.Global／ast.Nonlocalの行番号一覧を返す（Architecture Review Finding
    AR-m-2反映：module-levelのAssign検査だけでは検出できないglobal文・
    nonlocal文を、関数本体を対象として直接検出する）。"""
    violations = []
    if func_node is None:
        return violations
    for node in ast.walk(func_node):
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            violations.append(node.lineno)
    return violations


def _target_contains_name_attribute(target: ast.AST, name: str) -> bool:
    """代入先targetが <name>.<attribute>（直接、またはtuple／list targetの内側）を
    含むかどうかを判定する。ローカル変数への代入は対象外とする。"""
    if (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == name
    ):
        return True
    if isinstance(target, (ast.Tuple, ast.List)):
        return any(_target_contains_name_attribute(elt, name) for elt in target.elts)
    return False


def find_attribute_assign_violations(func_node, name: str) -> list:
    """func_node（ast.FunctionDef）のbody以下を再帰的に走査し、<name>.<attribute>への
    Assign／AnnAssign／AugAssign、またはsetattr(<name>, ...)呼出の行番号一覧を返す
    （12.4節：article入力objectへの属性代入禁止のSource Guard、補助）。"""
    violations = []
    if func_node is None:
        return violations
    for node in ast.walk(func_node):
        if isinstance(node, ast.Assign):
            if any(_target_contains_name_attribute(t, name) for t in node.targets):
                violations.append(node.lineno)
        elif isinstance(node, ast.AnnAssign):
            if _target_contains_name_attribute(node.target, name):
                violations.append(node.lineno)
        elif isinstance(node, ast.AugAssign):
            if _target_contains_name_attribute(node.target, name):
                violations.append(node.lineno)
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "setattr"
            and len(node.args) >= 1
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == name
        ):
            violations.append(node.lineno)
    return violations


def file_references_name(file_path: Path, name: str) -> bool:
    """file_pathのソーステキストにnameという文字列が含まれるかどうかを返す
    （Production Runtime未接続Guard：importに限らずコメント等も含めた
    参照非存在の確認）。"""
    return name in file_path.read_text(encoding="utf-8")


print("=" * 60)
print("v6.13.0 Article Featured Media Binding Foundation E2E テスト")
print("=" * 60)
print()

import article_featured_media
from article_featured_media import bind_featured_media

from outputs import ArticleData
from collector import NewsItem
from publishing_config import PublishStatus
from wordpress_media import MediaUploadResult

ARTICLE_FEATURED_MEDIA_DIR = PROJECT_ROOT / "src" / "article_featured_media"
FILES = {
    "__init__": ARTICLE_FEATURED_MEDIA_DIR / "__init__.py",
    "article_featured_media_binder": ARTICLE_FEATURED_MEDIA_DIR / "article_featured_media_binder.py",
}

OUTPUTS_DIR = PROJECT_ROOT / "src" / "outputs"
WORDPRESS_MEDIA_DIR = PROJECT_ROOT / "src" / "wordpress_media"

_BINDER_SOURCE = FILES["article_featured_media_binder"].read_text(encoding="utf-8")
_BINDER_TREE = ast.parse(_BINDER_SOURCE, filename=str(FILES["article_featured_media_binder"]))
_BIND_FUNC_NODE = find_function_def(_BINDER_TREE, "bind_featured_media")


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


def make_media_result(media_id=123, source_url="https://example.com/photo.png", mime_type="image/png"):
    return MediaUploadResult(media_id=media_id, source_url=source_url, mime_type=mime_type)


# =====================================================================
# PUB-1: Public import Contract
# =====================================================================

print("[PUB-1] Public import Contract")
check_true(
    "PUB-1. article_featured_mediaがimportできる",
    "article_featured_media" in sys.modules,
)
check_true(
    "PUB-1. bind_featured_mediaがimportできる",
    bind_featured_media is not None,
)
check(
    "PUB-1. function名が一致",
    bind_featured_media.__name__,
    "bind_featured_media",
)
check(
    "PUB-1. __all__の集合一致",
    set(article_featured_media.__all__),
    {"bind_featured_media"},
)
check("PUB-1. __all__の件数が1", len(article_featured_media.__all__), 1)
print()

# =====================================================================
# SIG-1: Public signature Contract
# =====================================================================

print("[SIG-1] Public signature Contract")
_sig = inspect.signature(bind_featured_media)
_param_names = list(_sig.parameters.keys())
check("SIG-1. 引数名・順序が一致", _param_names, ["article", "media_result"])
check(
    "SIG-1. articleの型annotationがArticleData",
    _sig.parameters["article"].annotation,
    ArticleData,
)
check(
    "SIG-1. media_resultの型annotationがMediaUploadResult",
    _sig.parameters["media_result"].annotation,
    MediaUploadResult,
)
check("SIG-1. 戻り値annotationがArticleData", _sig.return_annotation, ArticleData)
check_true(
    "SIG-1. デフォルト値を持つ引数がない（両方必須引数）",
    all(p.default is inspect.Parameter.empty for p in _sig.parameters.values()),
)
print()

# =====================================================================
# BIND-1: 正常Binding
# =====================================================================

print("[BIND-1] 正常Binding")
_bind1_article = make_article(featured_media_id=0)
_bind1_media_result = make_media_result(media_id=555)
_bind1_result, _bind1_exc = invoke(lambda: bind_featured_media(_bind1_article, _bind1_media_result))
check_true("BIND-1. 例外が発生しない", _bind1_exc is None)
check(
    "BIND-1. 戻り値のfeatured_media_idがmedia_result.media_idと一致",
    _bind1_result.featured_media_id if _bind1_result is not None else None,
    555,
)
print()

# =====================================================================
# MUT-1: 元ArticleData非mutation（Runtime、全field snapshot比較）
# =====================================================================

print("[MUT-1] 元ArticleData非mutation")
_mut1_article = make_article(featured_media_id=0)
_mut1_snapshot_before = {f.name: getattr(_mut1_article, f.name) for f in fields(_mut1_article)}
_mut1_media_result = make_media_result(media_id=999)
_mut1_result, _mut1_exc = invoke(lambda: bind_featured_media(_mut1_article, _mut1_media_result))
check_true("MUT-1. 例外が発生しない", _mut1_exc is None)
_mut1_snapshot_after = {f.name: getattr(_mut1_article, f.name) for f in fields(_mut1_article)}
check(
    "MUT-1. 呼び出し前後で元articleの全fieldが不変（snapshot完全一致）",
    _mut1_snapshot_after,
    _mut1_snapshot_before,
)
check(
    "MUT-1. 元article.featured_media_idが0のまま（media_resultの値で汚染されない）",
    _mut1_article.featured_media_id,
    0,
)
print()

# =====================================================================
# OBJ-1: 戻り値別object
# =====================================================================

print("[OBJ-1] 戻り値別object")
_obj1_article = make_article()
_obj1_result, _obj1_exc = invoke(lambda: bind_featured_media(_obj1_article, make_media_result()))
check_true("OBJ-1. 例外が発生しない", _obj1_exc is None)
check_true("OBJ-1. result is not article", _obj1_result is not _obj1_article)
check_true("OBJ-1. 戻り値がArticleData型である", isinstance(_obj1_result, ArticleData))
print()

# =====================================================================
# FIELD-1: featured_media_id以外の全field維持
# =====================================================================

print("[FIELD-1] featured_media_id以外の全field維持")
_field1_article = make_article(featured_media_id=0)
_field1_result, _field1_exc = invoke(
    lambda: bind_featured_media(_field1_article, make_media_result(media_id=321))
)
check_true("FIELD-1. 例外が発生しない", _field1_exc is None)
_field1_mismatches = [
    f.name
    for f in fields(ArticleData)
    if f.name != "featured_media_id"
    and getattr(_field1_article, f.name) != getattr(_field1_result, f.name)
]
check("FIELD-1. featured_media_id以外に値の異なるfieldがない", _field1_mismatches, [])
check(
    "FIELD-1. featured_media_idのみがmedia_result.media_idへ置換されている",
    _field1_result.featured_media_id,
    321,
)
print()

# =====================================================================
# ITEM-1: nested object item参照維持
# =====================================================================

print("[ITEM-1] nested object item参照維持")
_item1_article = make_article()
_item1_result, _item1_exc = invoke(lambda: bind_featured_media(_item1_article, make_media_result()))
check_true("ITEM-1. 例外が発生しない", _item1_exc is None)
check_true(
    "ITEM-1. result.item is article.item（同一object参照、deep copyしない）",
    _item1_result.item is _item1_article.item,
)
print()

# =====================================================================
# ID-1/2/3: 既存featured_media_idパターン（常に決定的上書き）
# =====================================================================

print("[ID-1] featured_media_id == 0 から bind")
_id1_article = make_article(featured_media_id=0)
_id1_result, _id1_exc = invoke(lambda: bind_featured_media(_id1_article, make_media_result(media_id=100)))
check_true("ID-1. 例外が発生しない", _id1_exc is None)
check("ID-1. 0からmedia_result.media_idへ置換される", _id1_result.featured_media_id, 100)

print("[ID-2] 既存featured_media_id == media_result.media_id（同一）から bind")
_id2_article = make_article(featured_media_id=200)
_id2_result, _id2_exc = invoke(lambda: bind_featured_media(_id2_article, make_media_result(media_id=200)))
check_true("ID-2. 例外が発生しない", _id2_exc is None)
check("ID-2. 同一値のまま維持される", _id2_result.featured_media_id, 200)
check_true("ID-2. 値が同一でも新しいobjectが返る", _id2_result is not _id2_article)

print("[ID-3] 既存featured_media_id > 0 かつ media_result.media_idと異なる場合から bind")
_id3_article = make_article(featured_media_id=300)
_id3_result, _id3_exc = invoke(lambda: bind_featured_media(_id3_article, make_media_result(media_id=400)))
check_true("ID-3. 例外が発生しない（拒否されない）", _id3_exc is None)
check("ID-3. 異なる既存IDがmedia_result.media_idへ上書きされる", _id3_result.featured_media_id, 400)
print()

# =====================================================================
# VAL-1: article型不正
# =====================================================================

print("[VAL-1] article型不正")
ARTICLE_ERROR_MESSAGE = "article must be an ArticleData"
_val1_cases = [
    ("None", None),
    ("object()", object()),
    ("MediaUploadResult（型混同）", make_media_result()),
]
for _label, _value in _val1_cases:
    _result, _exc = invoke(lambda v=_value: bind_featured_media(v, make_media_result()))
    check_true(f"VAL-1. article={_label}: ValueErrorが送出される", isinstance(_exc, ValueError))
    check(
        f"VAL-1. article={_label}: 固定message完全一致",
        str(_exc) if _exc is not None else None,
        ARTICLE_ERROR_MESSAGE,
    )
print()

# =====================================================================
# VAL-2: media_result型不正
# =====================================================================

print("[VAL-2] media_result型不正")
MEDIA_RESULT_ERROR_MESSAGE = "media_result must be a MediaUploadResult"
_val2_cases = [
    ("None", None),
    ("object()", object()),
    ("ArticleData（型混同）", make_article()),
]
for _label, _value in _val2_cases:
    _result, _exc = invoke(lambda v=_value: bind_featured_media(make_article(), v))
    check_true(f"VAL-2. media_result={_label}: ValueErrorが送出される", isinstance(_exc, ValueError))
    check(
        f"VAL-2. media_result={_label}: 固定message完全一致",
        str(_exc) if _exc is not None else None,
        MEDIA_RESULT_ERROR_MESSAGE,
    )
print()

# =====================================================================
# VAL-3/4/5/6: media_id値不正
# =====================================================================

print("[VAL-3] media_id bool拒否")
MEDIA_ID_ERROR_MESSAGE = "media_result.media_id must be a positive int"
for _label, _value in [("True", True), ("False", False)]:
    _result, _exc = invoke(
        lambda v=_value: bind_featured_media(make_article(), make_media_result(media_id=v))
    )
    check_true(f"VAL-3. media_id={_label}: ValueErrorが送出される", isinstance(_exc, ValueError))
    check(
        f"VAL-3. media_id={_label}: 固定message完全一致",
        str(_exc) if _exc is not None else None,
        MEDIA_ID_ERROR_MESSAGE,
    )
print()

print("[VAL-4] media_id非int拒否")
for _label, _value in [("文字列'123'", "123"), ("float 1.5", 1.5), ("None", None)]:
    _result, _exc = invoke(
        lambda v=_value: bind_featured_media(make_article(), make_media_result(media_id=v))
    )
    check_true(f"VAL-4. media_id={_label}: ValueErrorが送出される", isinstance(_exc, ValueError))
    check(
        f"VAL-4. media_id={_label}: 固定message完全一致",
        str(_exc) if _exc is not None else None,
        MEDIA_ID_ERROR_MESSAGE,
    )
print()

print("[VAL-5] media_id == 0 拒否")
_val5_result, _val5_exc = invoke(
    lambda: bind_featured_media(make_article(), make_media_result(media_id=0))
)
check_true("VAL-5. ValueErrorが送出される", isinstance(_val5_exc, ValueError))
check(
    "VAL-5. 固定message完全一致",
    str(_val5_exc) if _val5_exc is not None else None,
    MEDIA_ID_ERROR_MESSAGE,
)
print()

print("[VAL-6] media_id負数拒否")
for _label, _value in [("-1", -1), ("-100", -100)]:
    _result, _exc = invoke(
        lambda v=_value: bind_featured_media(make_article(), make_media_result(media_id=v))
    )
    check_true(f"VAL-6. media_id={_label}: ValueErrorが送出される", isinstance(_exc, ValueError))
    check(
        f"VAL-6. media_id={_label}: 固定message完全一致",
        str(_exc) if _exc is not None else None,
        MEDIA_ID_ERROR_MESSAGE,
    )
print()

# =====================================================================
# ORDER-1/2/3: Validation Order
# =====================================================================

print("[ORDER-1] articleとmedia_resultの両方が不正：articleエラーが先")
_order1_result, _order1_exc = invoke(lambda: bind_featured_media(None, None))
check_true("ORDER-1. ValueErrorが送出される", isinstance(_order1_exc, ValueError))
check(
    "ORDER-1. article不正のmessageが送出される（media_result不正ではない）",
    str(_order1_exc) if _order1_exc is not None else None,
    ARTICLE_ERROR_MESSAGE,
)

print("[ORDER-2] article正常・media_result不正（属性を持たないobject）：media_resultエラー")
_order2_result, _order2_exc = invoke(lambda: bind_featured_media(make_article(), object()))
check_true("ORDER-2. ValueErrorが送出される", isinstance(_order2_exc, ValueError))
check(
    "ORDER-2. media_result不正のmessageが送出される（AttributeErrorではない、"
    "media_id属性が存在しないobjectでもmedia_id検証前にisinstance検証で拒否される）",
    str(_order2_exc) if _order2_exc is not None else None,
    MEDIA_RESULT_ERROR_MESSAGE,
)

print("[ORDER-3] articleとmedia_resultの型は正常・media_idが不正：media_idエラー")
_order3_result, _order3_exc = invoke(
    lambda: bind_featured_media(make_article(), make_media_result(media_id=0))
)
check_true("ORDER-3. ValueErrorが送出される", isinstance(_order3_exc, ValueError))
check(
    "ORDER-3. media_id不正のmessageが送出される",
    str(_order3_exc) if _order3_exc is not None else None,
    MEDIA_ID_ERROR_MESSAGE,
)
print()

# =====================================================================
# SEC-1: 例外message Security
# =====================================================================

print("[SEC-1] 例外message Security")
_sec1_secret_title = "SECRET_TITLE_MARKER"
_sec1_secret_url = "https://secret-marker.example.com/leak"
_sec1_secret_mime = "image/SECRET-MIME-MARKER"
_sec1_article = make_article(seo_title=_sec1_secret_title)

_sec1_article_exc_result, _sec1_article_exc = invoke(
    lambda: bind_featured_media(object(), make_media_result())
)
_sec1_article_msg = str(_sec1_article_exc) if _sec1_article_exc is not None else ""
check("SEC-1. article不正messageが固定文言と完全一致", _sec1_article_msg, ARTICLE_ERROR_MESSAGE)
check_not_contains("SEC-1. article不正messageにNewsItem内容が含まれない", _sec1_article_msg, "PlayStation")

_sec1_mr_exc_result, _sec1_mr_exc = invoke(
    lambda: bind_featured_media(_sec1_article, object())
)
_sec1_mr_msg = str(_sec1_mr_exc) if _sec1_mr_exc is not None else ""
check("SEC-1. media_result不正messageが固定文言と完全一致", _sec1_mr_msg, MEDIA_RESULT_ERROR_MESSAGE)
check_not_contains("SEC-1. media_result不正messageにseo_titleが含まれない", _sec1_mr_msg, _sec1_secret_title)

_sec1_mid_exc_result, _sec1_mid_exc = invoke(
    lambda: bind_featured_media(
        _sec1_article,
        make_media_result(media_id=-1, source_url=_sec1_secret_url, mime_type=_sec1_secret_mime),
    )
)
_sec1_mid_msg = str(_sec1_mid_exc) if _sec1_mid_exc is not None else ""
check("SEC-1. media_id不正messageが固定文言と完全一致", _sec1_mid_msg, MEDIA_ID_ERROR_MESSAGE)
check_not_contains("SEC-1. media_id不正messageにmedia_id実値(-1)が含まれない", _sec1_mid_msg, "-1")
check_not_contains("SEC-1. media_id不正messageにsource_urlが含まれない", _sec1_mid_msg, _sec1_secret_url)
check_not_contains("SEC-1. media_id不正messageにmime_typeが含まれない", _sec1_mid_msg, _sec1_secret_mime)
check_not_contains("SEC-1. media_id不正messageにseo_titleが含まれない", _sec1_mid_msg, _sec1_secret_title)
print()

# =====================================================================
# STATE-1: 連続呼び出し独立性（Runtime）
# =====================================================================

print("[STATE-1] 連続呼び出し独立性（Runtime）")
_state1_first_result, _state1_first_exc = invoke(
    lambda: bind_featured_media(make_article(), make_media_result(media_id=0))
)
check_true("STATE-1. 1回目（不正media_id）でValueErrorが発生する", isinstance(_state1_first_exc, ValueError))

_state1_second_article = make_article(featured_media_id=0, seo_title="2回目の記事")
_state1_second_result, _state1_second_exc = invoke(
    lambda: bind_featured_media(_state1_second_article, make_media_result(media_id=777))
)
check_true("STATE-1. 2回目（正当な入力）は1回目の失敗に影響されず成功する", _state1_second_exc is None)
check(
    "STATE-1. 2回目の呼び出しのfeatured_media_idが正しく反映される（前回のstateが混入しない）",
    _state1_second_result.featured_media_id if _state1_second_result is not None else None,
    777,
)
check(
    "STATE-1. 2回目の戻り値のseo_titleが2回目のarticleと一致する",
    _state1_second_result.seo_title if _state1_second_result is not None else None,
    "2回目の記事",
)
print()

# =====================================================================
# DETERM-1: 同一入力の決定性
# =====================================================================

print("[DETERM-1] 同一入力の決定性")
_determ1_article = make_article(featured_media_id=0)
_determ1_media_result = make_media_result(media_id=888)
_determ1_result1, _determ1_exc1 = invoke(
    lambda: bind_featured_media(_determ1_article, _determ1_media_result)
)
_determ1_result2, _determ1_exc2 = invoke(
    lambda: bind_featured_media(_determ1_article, _determ1_media_result)
)
check_true("DETERM-1. 1回目・2回目とも例外が発生しない", _determ1_exc1 is None and _determ1_exc2 is None)
check_true(
    "DETERM-1. result1 == result2（値として等しい、ArticleDataのdataclass equalityを使用）",
    _determ1_result1 == _determ1_result2,
)
check_true("DETERM-1. result1 is not result2（別object）", _determ1_result1 is not _determ1_result2)
check_true("DETERM-1. result1 is not article", _determ1_result1 is not _determ1_article)
check_true("DETERM-1. result2 is not article", _determ1_result2 is not _determ1_article)
print()

# =====================================================================
# STATE-AST-1: module-level state非保持
# =====================================================================

print("[STATE-AST-1] module-level state非保持（module-level Assign）")
check_true(
    "STATE-AST-1. article_featured_media_binder.py内にbind_featured_media関数が"
    "module-levelに1件存在する",
    _BIND_FUNC_NODE is not None,
)
_module_level_assigns = get_module_level_assign_lines(_BINDER_TREE)
check(
    "STATE-AST-1. module-levelにrequest単位stateを示すAssignが存在しない"
    "（article／media_result／media_id／featured_media_id／result／cache等の"
    "module global定義がない）",
    _module_level_assigns,
    [],
)

print("[STATE-AST-1] bind_featured_media()本体のast.Global／ast.Nonlocal検出"
      "（Architecture Review Finding AR-m-2反映）")
_global_nonlocal_violations = find_global_nonlocal_violations(_BIND_FUNC_NODE)
check(
    "STATE-AST-1. bind_featured_media()本体にglobal文・nonlocal文が存在しない",
    _global_nonlocal_violations,
    [],
)
print()

# =====================================================================
# MUT-AST-1: article入力objectへの属性代入非存在（Source Guard、補助）
# =====================================================================

print("[MUT-AST-1] article入力objectへの属性代入非存在（Source Guard、補助）")
_article_attr_violations = find_attribute_assign_violations(_BIND_FUNC_NODE, "article")
check(
    "MUT-AST-1. bind_featured_media()本体にarticle.<attr>への代入・"
    "setattr(article, ...)が存在しない",
    _article_attr_violations,
    [],
)
print()

# =====================================================================
# SIDE-1: Side Effect Guard（AST）
# =====================================================================

print("[SIDE-1] Side Effect Guard")
_binder_import_details = get_import_details(FILES["article_featured_media_binder"])
FORBIDDEN_SIDE_EFFECT_MODULES = (
    "requests",
    "urllib",
    "http",
    "os",
    "logging",
    "subprocess",
    "time",
    "pathlib",
    "openai",
)
for _mod in FORBIDDEN_SIDE_EFFECT_MODULES:
    check_false(
        f"SIDE-1. article_featured_media_binder.pyが{_mod}をimportしない",
        _mod in _binder_import_details["absolute_roots"],
    )
for _call_name in ("open", "print", "setattr", "sleep"):
    check(
        f"SIDE-1. article_featured_media_binder.pyに{_call_name}()呼出がない",
        get_call_lines(FILES["article_featured_media_binder"], _call_name),
        [],
    )
print()

# =====================================================================
# DEP-1: 許可依存Guard（AST：ast.Import／ast.ImportFrom解析）
# =====================================================================

print("[DEP-1] 許可依存Guard")

ALLOWED_MODULES = {"dataclasses", "outputs", "wordpress_media"}
FORBIDDEN_EXACT = (
    "generated_image_wordpress_media",
    "ai_image_generation",
    "openai_image_generation",
    "image_resolver",
    "ai",
    "pipeline",
    "workflow_engine",
    "scheduler",
    "scripts",
    "main",
    "requests",
    "urllib",
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

_outputs_names = get_imported_names_from(FILES["article_featured_media_binder"], "outputs")
check_true(
    "DEP-1. outputsからのimportがArticleDataのみの部分集合",
    _outputs_names.issubset({"ArticleData"}),
)

_wordpress_media_names = get_imported_names_from(
    FILES["article_featured_media_binder"], "wordpress_media"
)
check_true(
    "DEP-1. wordpress_mediaからのimportがMediaUploadResultのみの部分集合",
    _wordpress_media_names.issubset({"MediaUploadResult"}),
)
print()

# =====================================================================
# DEP-2: 逆依存Guard（Architecture Review Finding AR-S-1反映、vacuous pass防止）
# =====================================================================

print("[DEP-2] 逆依存Guard：outputs・wordpress_mediaがarticle_featured_mediaをimportしていないこと")

_reverse_dep_targets = {
    "outputs": OUTPUTS_DIR,
    "wordpress_media": WORDPRESS_MEDIA_DIR,
}
for _package_name, _package_dir in _reverse_dep_targets.items():
    check_true(f"DEP-2. {_package_name}ディレクトリが存在する", _package_dir.is_dir())
    _py_files = sorted(_package_dir.glob("*.py"))
    check_true(
        f"DEP-2. {_package_name}配下の.pyファイル一覧が1件以上存在する"
        "（vacuous pass防止：走査対象が空のままPASSしないことの確認）",
        len(_py_files) >= 1,
    )
    _violating_files = []
    for _py_file in _py_files:
        _details = get_import_details(_py_file)
        if "article_featured_media" in _details["absolute_roots"]:
            _violating_files.append(_py_file.name)
    check(f"DEP-2. {_package_name}がarticle_featured_mediaをimportしていない", _violating_files, [])
print()

# =====================================================================
# RUNTIME-1: Production Runtime未接続Guard
# =====================================================================

print("[RUNTIME-1] Production Runtime未接続Guard")

_required_runtime_files = {
    "main.py": PROJECT_ROOT / "main.py",
    "src/image_resolver.py": PROJECT_ROOT / "src" / "image_resolver.py",
    "src/outputs/wordpress_output.py": PROJECT_ROOT / "src" / "outputs" / "wordpress_output.py",
}
for _label, _path in _required_runtime_files.items():
    check_true(f"RUNTIME-1. {_label}が存在する", _path.is_file())
    check_false(
        f"RUNTIME-1. {_label}にarticle_featured_mediaという文字列が含まれない",
        file_references_name(_path, "article_featured_media"),
    )
    check_false(
        f"RUNTIME-1. {_label}にbind_featured_mediaという文字列が含まれない",
        file_references_name(_path, "bind_featured_media"),
    )

_optional_runtime_dirs = {
    "src/pipeline": PROJECT_ROOT / "src" / "pipeline",
    "src/workflow_engine": PROJECT_ROOT / "src" / "workflow_engine",
    "scripts": PROJECT_ROOT / "scripts",
}
for _dir_label, _dir_path in _optional_runtime_dirs.items():
    if not _dir_path.is_dir():
        continue
    _py_files = sorted(_dir_path.glob("*.py"))
    if not _py_files:
        continue
    _violating = [
        f.name
        for f in _py_files
        if file_references_name(f, "article_featured_media") or file_references_name(f, "bind_featured_media")
    ]
    check(f"RUNTIME-1. {_dir_label}配下に参照ファイルがない", _violating, [])
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
