"""
E2E テスト: v6.14.0 Article Featured Media Orchestration Foundation

Source of Truth:
    docs/design/article_featured_media_orchestration_foundation.md
    （Architecture Review：Approved、Critical/Major/Minor/Suggestion いずれも0件、
      Blocking Issueなし）

本テストは実OpenAI API・実WordPress API・実HTTP通信・実課金のいずれも発生させない。
image_generator／media_uploaderはFake（test file内限定）を明示的にConstructor
Injectionで注入し、実OpenAIImageGenerator／実WordPressMediaUploader／実
GeneratedImageWordPressMediaUploaderインスタンスは生成しない。bind_featured_media()
自体はFakeへ差し替えず、実Production関数（article_featured_media package）を使用する。

Scenario構成（34 Scenario）:
    PUB-1（Public import Contract）
    SIG-1（Public signature Contract：Constructor／apply）
    CTOR-1（Constructor正常構築）
    CAP-1/2/3/4（capability不正4ケース、Duck Typing Guard）
    CTOR-PROP-1/2（getattr()がAttributeError以外を送出した場合の無変換伝播）
    CTOR-ORDER-1（Validation順序：image_generator優先）
    CTOR-ORDER-AST-1（Constructor本体のSource Guard：Validation後にのみself代入）
    NORM-1（正常系呼び出し順序・引数受け渡し・戻り値）
    IMMUT-1（ArticleData不変性）
    VAL-ARTICLE-1（article型不正）
    VAL-PROMPT-1（prompt型不正）
    VAL-PROMPT-2（prompt空白）
    VAL-FILENAME-1（filename型不正）
    VAL-FILENAME-2（filename空白）
    VAL-ORDER-1/2/3（apply() Validation順序）
    VAL-NOCALL-1（Validation失敗時のdependency未呼出）
    STRSUB-1（str subclass許可・非正規化）
    GENFAIL-1（画像生成失敗の無変換伝播）
    UPLOADFAIL-1（Upload失敗の無変換伝播）
    BINDFAIL-1（Binding失敗の無変換伝播、実bind_featured_media使用）
    PROTO-1（Protocol構造互換性Guard：静的signature比較）
    STATE-1（Runtime連続呼出の独立性）
    STATE-AST-1（self属性代入Source Guard：__init__／apply()）
    LOOP-AST-1（for／while／comprehension／generator expression禁止Guard）
    TRY-AST-1（try／except禁止Guard）
    GLOBAL-AST-1（global／nonlocal禁止Guard）
    MODULE-AST-1（module-level Assign禁止Guard）
    SEC-1（Security Guard）
    DEP-1（許可依存Guard）
    DEP-2（逆依存Guard：vacuous pass防止）
    RUNTIME-1（Consumer-less Guard：Production Runtime未接続）
    SIDE-1（Side Effect Guard）

Regressionは本ファイルのScenario数に含まない。

実行方法:
    cd projects/03_game_content_ai
    python tests/test_e2e_v6_14_0_article_featured_media_orchestration_foundation.py
"""
import ast
import inspect
import sys
from dataclasses import fields
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ─── テスト用ユーティリティ（v6.9.0〜v6.13.0 precedentを踏襲） ───

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


GENERATE_CAPABILITY_MESSAGE = "image_generator must provide a callable generate method"
UPLOAD_CAPABILITY_MESSAGE = "media_uploader must provide a callable upload method"
ARTICLE_ERROR_MESSAGE = "article must be an ArticleData"
PROMPT_TYPE_ERROR_MESSAGE = "prompt must be a str"
PROMPT_BLANK_ERROR_MESSAGE = "prompt must not be blank"
FILENAME_TYPE_ERROR_MESSAGE = "filename must be a str"
FILENAME_BLANK_ERROR_MESSAGE = "filename must not be blank"


# ─── AST解析ユーティリティ（v6.9.0〜v6.13.0 precedentを踏襲・拡張） ───


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


def get_module_level_assign_lines(tree) -> list:
    """module-level（tree.body直下）のAssign／AnnAssign／AugAssignの行番号一覧を返す。"""
    lines = []
    for node in tree.body:
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
            lines.append(node.lineno)
    return lines


def find_node_type_lines(node, node_types) -> list:
    """node以下を再帰的に走査し、node_typesに一致するノードの行番号一覧を返す。"""
    return [n.lineno for n in ast.walk(node) if isinstance(n, node_types)]


def _target_contains_self_attribute(target: ast.AST) -> bool:
    """代入先targetが self.<attribute>（直接、またはtuple／list targetの内側）を
    含むかどうかを判定する。ローカル変数への代入は対象外とする。"""
    if (
        isinstance(target, ast.Attribute)
        and isinstance(target.value, ast.Name)
        and target.value.id == "self"
    ):
        return True
    if isinstance(target, (ast.Tuple, ast.List)):
        return any(_target_contains_self_attribute(elt) for elt in target.elts)
    return False


def find_disallowed_self_state_constructs(method_node) -> list:
    """method_node（ast.FunctionDef）のbody以下を再帰的に走査し、
    ast.AugAssign／ast.AnnAssign（self.属性向け）／setattr(self, ...)／
    object.__setattr__(self, ...)の行番号一覧を返す（単純なself.attr = valueの
    ast.Assignは対象外、別途find_self_simple_assign_namesで扱う）。"""
    violations = []
    if method_node is None:
        return violations
    for node in ast.walk(method_node):
        if isinstance(node, ast.AnnAssign):
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
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "__setattr__"
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "object"
            and len(node.args) >= 1
            and isinstance(node.args[0], ast.Name)
            and node.args[0].id == "self"
        ):
            violations.append(node.lineno)
    return violations


def find_self_simple_assign_names(method_node) -> list:
    """method_node（ast.FunctionDef）のbody直下（ast.walkで全体を走査）にある
    単純なself.<attr> = value 形式のast.Assign（tuple／list targetは含まない
    単一Attributeターゲットのみ）から、<attr>名一覧を出現順に返す。"""
    names = []
    if method_node is None:
        return names
    for node in ast.walk(method_node):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (
                    isinstance(target, ast.Attribute)
                    and isinstance(target.value, ast.Name)
                    and target.value.id == "self"
                ):
                    names.append(target.attr)
    return names


def file_references_name(file_path: Path, name: str) -> bool:
    """file_pathのソーステキストにnameという文字列が含まれるかどうかを返す
    （Production Runtime未接続Guard：importに限らずコメント等も含めた参照非存在の確認）。"""
    return name in file_path.read_text(encoding="utf-8")


print("=" * 60)
print("v6.14.0 Article Featured Media Orchestration Foundation E2E テスト")
print("=" * 60)
print()

import article_featured_media_orchestration
from article_featured_media_orchestration import (
    ArticleFeaturedMediaOrchestrator,
    GeneratedImageUploadCapability,
)

from ai_image_generation import GeneratedImage
from outputs import ArticleData
from collector import NewsItem
from publishing_config import PublishStatus
from wordpress_media import MediaUploadResult

ORCH_DIR = PROJECT_ROOT / "src" / "article_featured_media_orchestration"
FILES = {
    "__init__": ORCH_DIR / "__init__.py",
    "article_featured_media_orchestrator": ORCH_DIR / "article_featured_media_orchestrator.py",
}

AI_IMAGE_GENERATION_DIR = PROJECT_ROOT / "src" / "ai_image_generation"
WORDPRESS_MEDIA_DIR = PROJECT_ROOT / "src" / "wordpress_media"
ARTICLE_FEATURED_MEDIA_DIR = PROJECT_ROOT / "src" / "article_featured_media"
OUTPUTS_DIR = PROJECT_ROOT / "src" / "outputs"

_ORCH_SOURCE = FILES["article_featured_media_orchestrator"].read_text(encoding="utf-8")
_ORCH_TREE = ast.parse(_ORCH_SOURCE, filename=str(FILES["article_featured_media_orchestrator"]))
_ORCH_CLASS = find_class_def(_ORCH_TREE, "ArticleFeaturedMediaOrchestrator")
_PROTOCOL_CLASS = find_class_def(_ORCH_TREE, "GeneratedImageUploadCapability")
_INIT_METHOD = find_method(_ORCH_CLASS, "__init__")
_APPLY_METHOD = find_method(_ORCH_CLASS, "apply")


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


def make_generated_image(mime_type: str = "image/png", data: bytes = b"PNGDATA") -> GeneratedImage:
    return GeneratedImage(image_bytes=data, mime_type=mime_type)


def make_media_result(media_id=123, source_url="https://example.com/photo.png", mime_type="image/png"):
    return MediaUploadResult(media_id=media_id, source_url=source_url, mime_type=mime_type)


# ─── Test Double（Fake／sentinel、test file内限定。production packageへは配置しない） ───


class _RecordingImageGenerator:
    """callableなgenerateを持つFake。呼出promptを記録し、設定可能なGeneratedImageを返す。"""

    def __init__(self, result, call_log=None):
        self.calls = []
        self._result = result
        self._call_log = call_log if call_log is not None else []

    def generate(self, prompt):
        self.calls.append(prompt)
        self._call_log.append(("generate", prompt))
        return self._result


class _RecordingMediaUploader:
    """callableなuploadを持つFake。呼出(image, filename)を記録し、設定可能なMediaUploadResultを返す。"""

    def __init__(self, result, call_log=None):
        self.calls = []
        self._result = result
        self._call_log = call_log if call_log is not None else []

    def upload(self, image, filename):
        self.calls.append((image, filename))
        self._call_log.append(("upload", filename))
        return self._result


class _FailingImageGenerator:
    """呼出を記録したうえで、事前構築済みexceptionを送出するFake。"""

    def __init__(self, exc, call_log=None):
        self.calls = []
        self._exc = exc
        self._call_log = call_log if call_log is not None else []

    def generate(self, prompt):
        self.calls.append(prompt)
        self._call_log.append(("generate", prompt))
        raise self._exc


class _FailingMediaUploader:
    """呼出を記録したうえで、事前構築済みexceptionを送出するFake。"""

    def __init__(self, exc, call_log=None):
        self.calls = []
        self._exc = exc
        self._call_log = call_log if call_log is not None else []

    def upload(self, image, filename):
        self.calls.append((image, filename))
        self._call_log.append(("upload", filename))
        raise self._exc


class _MissingGenerateGenerator:
    """generate属性を持たないFake。"""
    pass


class _NoneGenerateGenerator:
    """generate = Noneを持つFake。"""
    generate = None


class _StringGenerateGenerator:
    """generate = 非callable文字列を持つFake。"""
    generate = "not callable"


class _MissingUploadUploader:
    """upload属性を持たないFake。"""
    pass


class _NoneUploadUploader:
    """upload = Noneを持つFake。"""
    upload = None


class _StringUploadUploader:
    """upload = 非callable文字列を持つFake。"""
    upload = "not callable"


class _PropertyRaisingGenerateGenerator:
    """generateがproperty経由で属性アクセス自体が例外を送出するFake。"""

    def __init__(self, exc):
        self._exc = exc

    @property
    def generate(self):
        raise self._exc


class _PropertyRaisingUploadUploader:
    """uploadがproperty経由で属性アクセス自体が例外を送出するFake。"""

    def __init__(self, exc):
        self._exc = exc

    @property
    def upload(self):
        raise self._exc


class _PromptStr(str):
    """promptのstr subclass許可を確認するためのFake型。"""
    pass


class _FilenameStr(str):
    """filenameのstr subclass許可を確認するためのFake型。"""
    pass


class _SentinelGenerateError(Exception):
    pass


class _SentinelUploadError(Exception):
    pass


class _SentinelPropertyError(Exception):
    pass


def _valid_generator():
    return _RecordingImageGenerator(make_generated_image())


def _valid_uploader():
    return _RecordingMediaUploader(make_media_result())


# =====================================================================
# PUB-1: Public import Contract
# =====================================================================

print("[PUB-1] Public import Contract")
check_true(
    "PUB-1. article_featured_media_orchestrationがimportできる",
    "article_featured_media_orchestration" in sys.modules,
)
check_true(
    "PUB-1. ArticleFeaturedMediaOrchestratorがimportできる",
    ArticleFeaturedMediaOrchestrator is not None,
)
check_true(
    "PUB-1. GeneratedImageUploadCapabilityがimportできる",
    GeneratedImageUploadCapability is not None,
)
check("PUB-1. class名が一致", ArticleFeaturedMediaOrchestrator.__name__, "ArticleFeaturedMediaOrchestrator")
check("PUB-1. Protocol名が一致", GeneratedImageUploadCapability.__name__, "GeneratedImageUploadCapability")
check(
    "PUB-1. __all__の集合一致",
    set(article_featured_media_orchestration.__all__),
    {"ArticleFeaturedMediaOrchestrator", "GeneratedImageUploadCapability"},
)
check("PUB-1. __all__の件数が2", len(article_featured_media_orchestration.__all__), 2)
print()

# =====================================================================
# SIG-1: Public signature Contract
# =====================================================================

print("[SIG-1] Public signature Contract")
_ctor_sig = inspect.signature(ArticleFeaturedMediaOrchestrator.__init__)
_ctor_param_names = [n for n in _ctor_sig.parameters.keys() if n != "self"]
check("SIG-1. __init__引数名・順序が一致", _ctor_param_names, ["image_generator", "media_uploader"])
check_true(
    "SIG-1. __init__にデフォルト値を持つ引数がない（両方必須引数）",
    all(
        p.default is inspect.Parameter.empty
        for name, p in _ctor_sig.parameters.items()
        if name != "self"
    ),
)

_apply_sig = inspect.signature(ArticleFeaturedMediaOrchestrator.apply)
_apply_param_names = [n for n in _apply_sig.parameters.keys() if n != "self"]
check("SIG-1. apply()引数名・順序が一致", _apply_param_names, ["article", "prompt", "filename"])
check_true(
    "SIG-1. apply()にデフォルト値を持つ引数がない（すべて必須引数）",
    all(
        p.default is inspect.Parameter.empty
        for name, p in _apply_sig.parameters.items()
        if name != "self"
    ),
)

_protocol_upload_sig = inspect.signature(GeneratedImageUploadCapability.upload)
_protocol_upload_param_names = [n for n in _protocol_upload_sig.parameters.keys() if n != "self"]
check("SIG-1. Protocol upload()引数名・順序が一致", _protocol_upload_param_names, ["image", "filename"])
print()

# =====================================================================
# CTOR-1: Constructor正常構築
# =====================================================================

print("[CTOR-1] Constructor正常構築")
_ctor1_result, _ctor1_exc = invoke(lambda: ArticleFeaturedMediaOrchestrator(_valid_generator(), _valid_uploader()))
check_true("CTOR-1. 正当なdependencyでconstructor成功", _ctor1_exc is None)
check_true("CTOR-1. 戻り値がArticleFeaturedMediaOrchestrator型", isinstance(_ctor1_result, ArticleFeaturedMediaOrchestrator))
print()

# =====================================================================
# CAP-1/2/3/4: capability不正4ケース（Duck Typing Guard）
# =====================================================================

print("[CAP-1/2/3/4] capability不正4ケース")
_cap_generator_cases = [
    ("CAP-1", "image_generator: generate属性なし", _MissingGenerateGenerator()),
    ("CAP-2", "image_generator: generate = None", _NoneGenerateGenerator()),
    ("CAP-3", "image_generator: generate = 非callable文字列", _StringGenerateGenerator()),
]
for _scenario_id, _label, _fake in _cap_generator_cases:
    _result, _exc = invoke(lambda g=_fake: ArticleFeaturedMediaOrchestrator(g, _valid_uploader()))
    check_true(f"{_scenario_id}. {_label}: TypeErrorが送出される", isinstance(_exc, TypeError))
    check(
        f"{_scenario_id}. {_label}: 固定message完全一致",
        str(_exc) if _exc is not None else None,
        GENERATE_CAPABILITY_MESSAGE,
    )

_cap_uploader_cases = [
    ("CAP-4a", "media_uploader: upload属性なし", _MissingUploadUploader()),
    ("CAP-4b", "media_uploader: upload = None", _NoneUploadUploader()),
    ("CAP-4c", "media_uploader: upload = 非callable文字列", _StringUploadUploader()),
]
for _scenario_id, _label, _fake in _cap_uploader_cases:
    _result, _exc = invoke(lambda u=_fake: ArticleFeaturedMediaOrchestrator(_valid_generator(), u))
    check_true(f"{_scenario_id}. {_label}: TypeErrorが送出される", isinstance(_exc, TypeError))
    check(
        f"{_scenario_id}. {_label}: 固定message完全一致",
        str(_exc) if _exc is not None else None,
        UPLOAD_CAPABILITY_MESSAGE,
    )
print()

# =====================================================================
# CTOR-PROP-1/2: getattr()がAttributeError以外を送出した場合の無変換伝播
# =====================================================================

print("[CTOR-PROP-1] image_generator property例外の無変換伝播")
_prop1_exc_instance = _SentinelPropertyError("generate property boom")
_prop1_result, _prop1_exc = invoke(
    lambda: ArticleFeaturedMediaOrchestrator(_PropertyRaisingGenerateGenerator(_prop1_exc_instance), _valid_uploader())
)
check_true("CTOR-PROP-1. 例外が送出される", _prop1_exc is not None)
check_true("CTOR-PROP-1. 事前構築した例外objectと同一（無変換伝播）", _prop1_exc is _prop1_exc_instance)
check_false("CTOR-PROP-1. TypeErrorへ変換されていない", isinstance(_prop1_exc, TypeError))

print("[CTOR-PROP-2] media_uploader property例外の無変換伝播")
_prop2_exc_instance = _SentinelPropertyError("upload property boom")
_prop2_result, _prop2_exc = invoke(
    lambda: ArticleFeaturedMediaOrchestrator(_valid_generator(), _PropertyRaisingUploadUploader(_prop2_exc_instance))
)
check_true("CTOR-PROP-2. 例外が送出される", _prop2_exc is not None)
check_true("CTOR-PROP-2. 事前構築した例外objectと同一（無変換伝播）", _prop2_exc is _prop2_exc_instance)
check_false("CTOR-PROP-2. TypeErrorへ変換されていない", isinstance(_prop2_exc, TypeError))
print()

# =====================================================================
# CTOR-ORDER-1: Validation順序（image_generator優先）
# =====================================================================

print("[CTOR-ORDER-1] image_generatorとmedia_uploaderの両方が不正：image_generatorエラーが先")
_order1_result, _order1_exc = invoke(
    lambda: ArticleFeaturedMediaOrchestrator(_MissingGenerateGenerator(), _MissingUploadUploader())
)
check_true("CTOR-ORDER-1. TypeErrorが送出される", isinstance(_order1_exc, TypeError))
check(
    "CTOR-ORDER-1. image_generator不正のmessageが送出される（media_uploader不正ではない）",
    str(_order1_exc) if _order1_exc is not None else None,
    GENERATE_CAPABILITY_MESSAGE,
)
print()

# =====================================================================
# CTOR-ORDER-AST-1: Constructor本体のSource Guard
# =====================================================================

print("[CTOR-ORDER-AST-1] Constructor本体：Validation後にのみself代入")
check_true("CTOR-ORDER-AST-1. __init__メソッドが存在する", _INIT_METHOD is not None)
_init_body = _INIT_METHOD.body if _INIT_METHOD is not None else []
_init_if_indices = [i for i, n in enumerate(_init_body) if isinstance(n, ast.If)]
_init_self_assign_indices = [
    i
    for i, n in enumerate(_init_body)
    if isinstance(n, ast.Assign) and any(_target_contains_self_attribute(t) for t in n.targets)
]
check("CTOR-ORDER-AST-1. capability検証If文が2件", len(_init_if_indices), 2)
check("CTOR-ORDER-AST-1. self属性への単純Assignが2件", len(_init_self_assign_indices), 2)
check_true(
    "CTOR-ORDER-AST-1. すべてのIf文（capability検証）が、すべてのself代入より前に位置する"
    "（Validationに成功する前に片方のdependencyだけをselfへ保存しない）",
    bool(_init_if_indices)
    and bool(_init_self_assign_indices)
    and max(_init_if_indices) < min(_init_self_assign_indices),
)
_init_self_assign_names = find_self_simple_assign_names(_INIT_METHOD)
check(
    "CTOR-ORDER-AST-1. __init__で許可するself属性代入がimage_generator・media_uploaderの2つのみ、"
    "この順序で存在する",
    _init_self_assign_names,
    ["_image_generator", "_media_uploader"],
)
_init_disallowed = find_disallowed_self_state_constructs(_INIT_METHOD)
check(
    "CTOR-ORDER-AST-1. __init__本体にAugAssign／AnnAssign／setattr(self,...)／"
    "object.__setattr__(self,...)が存在しない",
    _init_disallowed,
    [],
)
print()

# =====================================================================
# NORM-1: 正常系呼び出し順序・引数受け渡し・戻り値
# =====================================================================

print("[NORM-1] 正常系呼び出し順序・引数受け渡し・戻り値")
_norm1_call_log = []
_norm1_generated_image = make_generated_image()
_norm1_media_result = make_media_result(media_id=4242, source_url="https://example.com/n.png", mime_type="image/png")
_norm1_generator = _RecordingImageGenerator(_norm1_generated_image, call_log=_norm1_call_log)
_norm1_uploader = _RecordingMediaUploader(_norm1_media_result, call_log=_norm1_call_log)
_norm1_orchestrator = ArticleFeaturedMediaOrchestrator(_norm1_generator, _norm1_uploader)
_norm1_article = make_article(featured_media_id=0)
_norm1_prompt = "a cat wearing a hat"
_norm1_filename = "cat.png"

_norm1_result, _norm1_exc = invoke(
    lambda: _norm1_orchestrator.apply(_norm1_article, _norm1_prompt, _norm1_filename)
)
check_true("NORM-1. 例外が発生しない", _norm1_exc is None)
check("NORM-1. generate()が1回だけ呼ばれる", len(_norm1_generator.calls), 1)
check("NORM-1. upload()が1回だけ呼ばれる", len(_norm1_uploader.calls), 1)
check(
    "NORM-1. 呼び出し順序がgenerate→uploadの順（各1回）",
    _norm1_call_log,
    [("generate", _norm1_prompt), ("upload", _norm1_filename)],
)
check_true("NORM-1. promptがgenerate()へ同一object(identity)で渡る", _norm1_generator.calls[0] is _norm1_prompt)
check_true(
    "NORM-1. Fake generate()が返したGeneratedImageがそのままupload()のimage引数へ渡る（identity）",
    _norm1_uploader.calls[0][0] is _norm1_generated_image,
)
check_true("NORM-1. filenameがupload()へ同一object(identity)で渡る", _norm1_uploader.calls[0][1] is _norm1_filename)
check_true("NORM-1. 戻り値がArticleData型である", isinstance(_norm1_result, ArticleData))
check(
    "NORM-1. 戻り値のfeatured_media_idがmedia_result.media_idと一致（Fake upload()戻り値のvalueが"
    "bind_featured_media()経由で反映される）",
    _norm1_result.featured_media_id if _norm1_result is not None else None,
    4242,
)
print()

# =====================================================================
# IMMUT-1: ArticleData不変性
# =====================================================================

print("[IMMUT-1] ArticleData不変性")
_immut1_article = make_article(featured_media_id=0)
_immut1_snapshot_before = {f.name: getattr(_immut1_article, f.name) for f in fields(_immut1_article)}
_immut1_orchestrator = ArticleFeaturedMediaOrchestrator(
    _RecordingImageGenerator(make_generated_image()),
    _RecordingMediaUploader(make_media_result(media_id=555)),
)
_immut1_result, _immut1_exc = invoke(lambda: _immut1_orchestrator.apply(_immut1_article, "prompt", "file.png"))
check_true("IMMUT-1. 例外が発生しない", _immut1_exc is None)
_immut1_snapshot_after = {f.name: getattr(_immut1_article, f.name) for f in fields(_immut1_article)}
check(
    "IMMUT-1. 呼び出し前後で元articleの全fieldが不変（snapshot完全一致）",
    _immut1_snapshot_after,
    _immut1_snapshot_before,
)
check_true("IMMUT-1. 戻り値が入力articleとは別object", _immut1_result is not _immut1_article)
check_true("IMMUT-1. nested item参照維持（deep copyしない）", _immut1_result.item is _immut1_article.item)
_immut1_mismatches = [
    f.name
    for f in fields(ArticleData)
    if f.name != "featured_media_id" and getattr(_immut1_article, f.name) != getattr(_immut1_result, f.name)
]
check("IMMUT-1. featured_media_id以外に値の異なるfieldがない", _immut1_mismatches, [])
check("IMMUT-1. featured_media_idがmedia_result.media_idへ置換されている", _immut1_result.featured_media_id, 555)

_immut1_sameid_article = make_article(featured_media_id=777)
_immut1_sameid_orchestrator = ArticleFeaturedMediaOrchestrator(
    _RecordingImageGenerator(make_generated_image()),
    _RecordingMediaUploader(make_media_result(media_id=777)),
)
_immut1_sameid_result, _immut1_sameid_exc = invoke(
    lambda: _immut1_sameid_orchestrator.apply(_immut1_sameid_article, "p", "f.png")
)
check_true("IMMUT-1. 同一media_idケースで例外が発生しない", _immut1_sameid_exc is None)
check_true(
    "IMMUT-1. 既存featured_media_idとmedia_result.media_idが同一値でも新しいobjectが返る",
    _immut1_sameid_result is not _immut1_sameid_article,
)
check("IMMUT-1. 同一値のまま維持される", _immut1_sameid_result.featured_media_id, 777)
print()

# =====================================================================
# VAL-ARTICLE-1: article型不正
# =====================================================================

print("[VAL-ARTICLE-1] article型不正")
_val_article_cases = [
    ("None", None),
    ("object()", object()),
    ("dict", {"item": "not-an-article"}),
]
for _label, _value in _val_article_cases:
    _orch = ArticleFeaturedMediaOrchestrator(_valid_generator(), _valid_uploader())
    _result, _exc = invoke(lambda o=_orch, v=_value: o.apply(v, "prompt", "file.png"))
    check_true(f"VAL-ARTICLE-1. article={_label}: ValueErrorが送出される", isinstance(_exc, ValueError))
    check(
        f"VAL-ARTICLE-1. article={_label}: 固定message完全一致",
        str(_exc) if _exc is not None else None,
        ARTICLE_ERROR_MESSAGE,
    )
print()

# =====================================================================
# VAL-PROMPT-1: prompt型不正
# =====================================================================

print("[VAL-PROMPT-1] prompt型不正")
_val_prompt_type_cases = [
    ("None", None),
    ("int 123", 123),
    ("bytes", b"prompt"),
]
for _label, _value in _val_prompt_type_cases:
    _orch = ArticleFeaturedMediaOrchestrator(_valid_generator(), _valid_uploader())
    _article = make_article()
    _result, _exc = invoke(lambda o=_orch, a=_article, v=_value: o.apply(a, v, "file.png"))
    check_true(f"VAL-PROMPT-1. prompt={_label}: ValueErrorが送出される", isinstance(_exc, ValueError))
    check(
        f"VAL-PROMPT-1. prompt={_label}: 固定message完全一致",
        str(_exc) if _exc is not None else None,
        PROMPT_TYPE_ERROR_MESSAGE,
    )
print()

# =====================================================================
# VAL-PROMPT-2: prompt空白
# =====================================================================

print("[VAL-PROMPT-2] prompt空白")
_val_prompt_blank_cases = [
    ("空文字列", ""),
    ("半角スペース1つ", " "),
    ("タブ", "\t"),
    ("改行", "\n"),
    ("複合空白", " \t\n "),
]
for _label, _value in _val_prompt_blank_cases:
    _orch = ArticleFeaturedMediaOrchestrator(_valid_generator(), _valid_uploader())
    _article = make_article()
    _result, _exc = invoke(lambda o=_orch, a=_article, v=_value: o.apply(a, v, "file.png"))
    check_true(f"VAL-PROMPT-2. prompt={_label!r}: ValueErrorが送出される", isinstance(_exc, ValueError))
    check(
        f"VAL-PROMPT-2. prompt={_label!r}: 固定message完全一致",
        str(_exc) if _exc is not None else None,
        PROMPT_BLANK_ERROR_MESSAGE,
    )
print()

# =====================================================================
# VAL-FILENAME-1: filename型不正
# =====================================================================

print("[VAL-FILENAME-1] filename型不正")
_val_filename_type_cases = [
    ("None", None),
    ("bytes", b"file.png"),
    ("pathlib.Path", Path("file.png")),
]
for _label, _value in _val_filename_type_cases:
    _orch = ArticleFeaturedMediaOrchestrator(_valid_generator(), _valid_uploader())
    _article = make_article()
    _result, _exc = invoke(lambda o=_orch, a=_article, v=_value: o.apply(a, "prompt", v))
    check_true(f"VAL-FILENAME-1. filename={_label}: ValueErrorが送出される", isinstance(_exc, ValueError))
    check(
        f"VAL-FILENAME-1. filename={_label}: 固定message完全一致",
        str(_exc) if _exc is not None else None,
        FILENAME_TYPE_ERROR_MESSAGE,
    )
print()

# =====================================================================
# VAL-FILENAME-2: filename空白
# =====================================================================

print("[VAL-FILENAME-2] filename空白")
_val_filename_blank_cases = [
    ("空文字列", ""),
    ("半角スペース1つ", " "),
    ("タブ", "\t"),
    ("改行", "\n"),
    ("複合空白", " \t\n "),
]
for _label, _value in _val_filename_blank_cases:
    _orch = ArticleFeaturedMediaOrchestrator(_valid_generator(), _valid_uploader())
    _article = make_article()
    _result, _exc = invoke(lambda o=_orch, a=_article, v=_value: o.apply(a, "prompt", v))
    check_true(f"VAL-FILENAME-2. filename={_label!r}: ValueErrorが送出される", isinstance(_exc, ValueError))
    check(
        f"VAL-FILENAME-2. filename={_label!r}: 固定message完全一致",
        str(_exc) if _exc is not None else None,
        FILENAME_BLANK_ERROR_MESSAGE,
    )
print()

# =====================================================================
# VAL-ORDER-1/2/3: apply() Validation順序
# =====================================================================

print("[VAL-ORDER-1] articleとpromptの両方が不正：articleエラーが先")
_vord1_orch = ArticleFeaturedMediaOrchestrator(_valid_generator(), _valid_uploader())
_vord1_result, _vord1_exc = invoke(lambda: _vord1_orch.apply(None, None, "file.png"))
check_true("VAL-ORDER-1. ValueErrorが送出される", isinstance(_vord1_exc, ValueError))
check(
    "VAL-ORDER-1. article不正のmessageが送出される（prompt不正ではない）",
    str(_vord1_exc) if _vord1_exc is not None else None,
    ARTICLE_ERROR_MESSAGE,
)

print("[VAL-ORDER-2] articleは正当・promptが不正：promptエラー")
_vord2_orch = ArticleFeaturedMediaOrchestrator(_valid_generator(), _valid_uploader())
_vord2_result, _vord2_exc = invoke(lambda: _vord2_orch.apply(make_article(), None, "file.png"))
check_true("VAL-ORDER-2. ValueErrorが送出される", isinstance(_vord2_exc, ValueError))
check(
    "VAL-ORDER-2. prompt不正のmessageが送出される",
    str(_vord2_exc) if _vord2_exc is not None else None,
    PROMPT_TYPE_ERROR_MESSAGE,
)

print("[VAL-ORDER-3] article・prompt双方が正当・filenameが不正：filenameエラー")
_vord3_orch = ArticleFeaturedMediaOrchestrator(_valid_generator(), _valid_uploader())
_vord3_result, _vord3_exc = invoke(lambda: _vord3_orch.apply(make_article(), "prompt", None))
check_true("VAL-ORDER-3. ValueErrorが送出される", isinstance(_vord3_exc, ValueError))
check(
    "VAL-ORDER-3. filename不正のmessageが送出される",
    str(_vord3_exc) if _vord3_exc is not None else None,
    FILENAME_TYPE_ERROR_MESSAGE,
)
print()

# =====================================================================
# VAL-NOCALL-1: Validation失敗時のdependency未呼出
# =====================================================================

print("[VAL-NOCALL-1] Validation失敗時、generate／uploadが一切呼ばれない")
_nocall_generator = _RecordingImageGenerator(make_generated_image())
_nocall_uploader = _RecordingMediaUploader(make_media_result())
_nocall_orch = ArticleFeaturedMediaOrchestrator(_nocall_generator, _nocall_uploader)
invoke(lambda: _nocall_orch.apply(None, "prompt", "file.png"))
invoke(lambda: _nocall_orch.apply(make_article(), None, "file.png"))
invoke(lambda: _nocall_orch.apply(make_article(), "", "file.png"))
invoke(lambda: _nocall_orch.apply(make_article(), "prompt", None))
invoke(lambda: _nocall_orch.apply(make_article(), "prompt", ""))
check("VAL-NOCALL-1. 5件のValidation失敗を通じてgenerate()呼出回数が0", len(_nocall_generator.calls), 0)
check("VAL-NOCALL-1. 5件のValidation失敗を通じてupload()呼出回数が0", len(_nocall_uploader.calls), 0)
print()

# =====================================================================
# STRSUB-1: str subclass許可・非正規化
# =====================================================================

print("[STRSUB-1] str subclass許可・前後空白の非正規化")
_strsub1_call_log = []
_strsub1_generated_image = make_generated_image()
_strsub1_generator = _RecordingImageGenerator(_strsub1_generated_image, call_log=_strsub1_call_log)
_strsub1_uploader = _RecordingMediaUploader(make_media_result(media_id=99), call_log=_strsub1_call_log)
_strsub1_orch = ArticleFeaturedMediaOrchestrator(_strsub1_generator, _strsub1_uploader)
_strsub1_prompt = _PromptStr(" a cat in a hat ")
_strsub1_filename = _FilenameStr(" cat.png ")
_strsub1_article = make_article()

_strsub1_result, _strsub1_exc = invoke(
    lambda: _strsub1_orch.apply(_strsub1_article, _strsub1_prompt, _strsub1_filename)
)
check_true("STRSUB-1. str subclassのprompt／filenameが拒否されない（例外なし）", _strsub1_exc is None)
check_true(
    "STRSUB-1. generate()へ渡るpromptが元のstr subclass object（identity、strip済みへ置換されない）",
    _strsub1_generator.calls[0] is _strsub1_prompt,
)
check(
    "STRSUB-1. generate()へ渡るpromptの値が前後空白を含んだまま",
    _strsub1_generator.calls[0],
    " a cat in a hat ",
)
check_true(
    "STRSUB-1. upload()へ渡るfilenameが元のstr subclass object（identity、strip済みへ置換されない）",
    _strsub1_uploader.calls[0][1] is _strsub1_filename,
)
check(
    "STRSUB-1. upload()へ渡るfilenameの値が前後空白を含んだまま",
    _strsub1_uploader.calls[0][1],
    " cat.png ",
)
print()

# =====================================================================
# GENFAIL-1: 画像生成失敗の無変換伝播
# =====================================================================

print("[GENFAIL-1] 画像生成失敗の無変換伝播")
_genfail1_exc_instance = _SentinelGenerateError("generate boom")
_genfail1_call_log = []
_genfail1_generator = _FailingImageGenerator(_genfail1_exc_instance, call_log=_genfail1_call_log)
_genfail1_uploader = _RecordingMediaUploader(make_media_result(), call_log=_genfail1_call_log)
_genfail1_orch = ArticleFeaturedMediaOrchestrator(_genfail1_generator, _genfail1_uploader)
_genfail1_article = make_article(featured_media_id=0)
_genfail1_snapshot_before = {f.name: getattr(_genfail1_article, f.name) for f in fields(_genfail1_article)}

_genfail1_result, _genfail1_exc = invoke(
    lambda: _genfail1_orch.apply(_genfail1_article, "prompt", "file.png")
)
check_true("GENFAIL-1. 例外が送出される", _genfail1_exc is not None)
check_true("GENFAIL-1. 事前構築した例外objectと同一（無変換伝播）", _genfail1_exc is _genfail1_exc_instance)
check("GENFAIL-1. generate()が1回呼ばれる", len(_genfail1_generator.calls), 1)
check("GENFAIL-1. upload()が呼ばれていない（0回）", len(_genfail1_uploader.calls), 0)
check("GENFAIL-1. 呼び出しログにuploadが含まれない", _genfail1_call_log, [("generate", "prompt")])
_genfail1_snapshot_after = {f.name: getattr(_genfail1_article, f.name) for f in fields(_genfail1_article)}
check("GENFAIL-1. 元ArticleDataが不変", _genfail1_snapshot_after, _genfail1_snapshot_before)
print()

# =====================================================================
# UPLOADFAIL-1: Upload失敗の無変換伝播
# =====================================================================

print("[UPLOADFAIL-1] Upload失敗の無変換伝播")
_uploadfail1_exc_instance = _SentinelUploadError("upload boom")
_uploadfail1_call_log = []
_uploadfail1_generated_image = make_generated_image()
_uploadfail1_generator = _RecordingImageGenerator(_uploadfail1_generated_image, call_log=_uploadfail1_call_log)
_uploadfail1_uploader = _FailingMediaUploader(_uploadfail1_exc_instance, call_log=_uploadfail1_call_log)
_uploadfail1_orch = ArticleFeaturedMediaOrchestrator(_uploadfail1_generator, _uploadfail1_uploader)
_uploadfail1_article = make_article(featured_media_id=0)
_uploadfail1_snapshot_before = {f.name: getattr(_uploadfail1_article, f.name) for f in fields(_uploadfail1_article)}

_uploadfail1_result, _uploadfail1_exc = invoke(
    lambda: _uploadfail1_orch.apply(_uploadfail1_article, "prompt", "file.png")
)
check_true("UPLOADFAIL-1. 例外が送出される", _uploadfail1_exc is not None)
check_true("UPLOADFAIL-1. 事前構築した例外objectと同一（無変換伝播）", _uploadfail1_exc is _uploadfail1_exc_instance)
check("UPLOADFAIL-1. generate()が1回呼ばれる", len(_uploadfail1_generator.calls), 1)
check("UPLOADFAIL-1. upload()が1回呼ばれる", len(_uploadfail1_uploader.calls), 1)
check_true(
    "UPLOADFAIL-1. upload()が同一GeneratedImage objectを受け取っていた（identity）",
    _uploadfail1_uploader.calls[0][0] is _uploadfail1_generated_image,
)
check(
    "UPLOADFAIL-1. 呼び出しログがgenerate→uploadの順で2件のみ（bind未到達）",
    _uploadfail1_call_log,
    [("generate", "prompt"), ("upload", "file.png")],
)
_uploadfail1_snapshot_after = {f.name: getattr(_uploadfail1_article, f.name) for f in fields(_uploadfail1_article)}
check("UPLOADFAIL-1. 元ArticleDataが不変", _uploadfail1_snapshot_after, _uploadfail1_snapshot_before)
print()

# =====================================================================
# BINDFAIL-1: Binding失敗の無変換伝播（実bind_featured_media使用）
# =====================================================================

print("[BINDFAIL-1] Binding失敗の無変換伝播（実bind_featured_media使用）")
_bindfail1_invalid_media_result = MediaUploadResult(media_id=0, source_url=None, mime_type=None)
_bindfail1_generated_image = make_generated_image()
_bindfail1_generator = _RecordingImageGenerator(_bindfail1_generated_image)
_bindfail1_uploader = _RecordingMediaUploader(_bindfail1_invalid_media_result)
_bindfail1_orch = ArticleFeaturedMediaOrchestrator(_bindfail1_generator, _bindfail1_uploader)
_bindfail1_article = make_article(featured_media_id=0)
_bindfail1_snapshot_before = {f.name: getattr(_bindfail1_article, f.name) for f in fields(_bindfail1_article)}

_bindfail1_result, _bindfail1_exc = invoke(
    lambda: _bindfail1_orch.apply(_bindfail1_article, "prompt", "file.png")
)
check_true("BINDFAIL-1. ValueErrorが送出される（実bind_featured_media()由来）", isinstance(_bindfail1_exc, ValueError))
check(
    "BINDFAIL-1. 固定message完全一致",
    str(_bindfail1_exc) if _bindfail1_exc is not None else None,
    "media_result.media_id must be a positive int",
)
check("BINDFAIL-1. generate()が1回呼ばれる", len(_bindfail1_generator.calls), 1)
check("BINDFAIL-1. upload()が1回呼ばれる", len(_bindfail1_uploader.calls), 1)
_bindfail1_snapshot_after = {f.name: getattr(_bindfail1_article, f.name) for f in fields(_bindfail1_article)}
check("BINDFAIL-1. 元ArticleDataが不変", _bindfail1_snapshot_after, _bindfail1_snapshot_before)
print()

# =====================================================================
# PROTO-1: Protocol構造互換性Guard（静的signature比較）
# =====================================================================

print("[PROTO-1] Protocol構造互換性Guard（静的signature比較）")
from generated_image_wordpress_media import GeneratedImageWordPressMediaUploader

check_true(
    "PROTO-1. GeneratedImageWordPressMediaUploaderがimportできる（対象class存在確認）",
    GeneratedImageWordPressMediaUploader is not None,
)
check_true(
    "PROTO-1. GeneratedImageWordPressMediaUploader.uploadメソッドが存在する（対象method存在確認）",
    hasattr(GeneratedImageWordPressMediaUploader, "upload"),
)
check_true(
    "PROTO-1. GeneratedImageUploadCapabilityがimportできる（対象class存在確認）",
    GeneratedImageUploadCapability is not None,
)
check_true(
    "PROTO-1. GeneratedImageUploadCapability.uploadメソッドが存在する（対象method存在確認）",
    hasattr(GeneratedImageUploadCapability, "upload"),
)

_proto1_concrete_sig = inspect.signature(GeneratedImageWordPressMediaUploader.upload)
_proto1_protocol_sig = inspect.signature(GeneratedImageUploadCapability.upload)
_proto1_concrete_params = list(_proto1_concrete_sig.parameters.keys())
_proto1_protocol_params = list(_proto1_protocol_sig.parameters.keys())
check(
    "PROTO-1. GeneratedImageWordPressMediaUploader.uploadのparameter名の並びがself, image, filename",
    _proto1_concrete_params,
    ["self", "image", "filename"],
)
check(
    "PROTO-1. GeneratedImageUploadCapability.uploadのparameter名の並びがself, image, filename",
    _proto1_protocol_params,
    ["self", "image", "filename"],
)
check(
    "PROTO-1. 両signatureのparameter名の並びが完全一致（静的比較のみ、実構築・呼出なし）",
    _proto1_concrete_params,
    _proto1_protocol_params,
)
print()

# =====================================================================
# STATE-1: Runtime連続呼出の独立性
# =====================================================================

print("[STATE-1] Runtime連続呼出の独立性")
_state1_generator = _RecordingImageGenerator(make_generated_image())
_state1_uploader = _RecordingMediaUploader(make_media_result(media_id=1))
_state1_orch = ArticleFeaturedMediaOrchestrator(_state1_generator, _state1_uploader)

_state1_first_result, _state1_first_exc = invoke(lambda: _state1_orch.apply(None, "prompt", "file.png"))
check_true("STATE-1. 1回目（不正article）でValueErrorが発生する", isinstance(_state1_first_exc, ValueError))

_state1_second_article = make_article(featured_media_id=0, seo_title="2回目の記事")
_state1_uploader_2 = _RecordingMediaUploader(make_media_result(media_id=777))
_state1_orch_2 = ArticleFeaturedMediaOrchestrator(_RecordingImageGenerator(make_generated_image()), _state1_uploader_2)
_state1_second_result, _state1_second_exc = invoke(
    lambda: _state1_orch_2.apply(_state1_second_article, "prompt", "file.png")
)
check_true(
    "STATE-1. 同一Orchestrator classを再利用しても、1回目の失敗が2回目（別インスタンス）の成功に影響しない",
    _state1_second_exc is None,
)
check(
    "STATE-1. 2回目のfeatured_media_idが正しく反映される（前回のstateが混入しない）",
    _state1_second_result.featured_media_id if _state1_second_result is not None else None,
    777,
)

_state1_third_result, _state1_third_exc = invoke(
    lambda: _state1_orch_2.apply(make_article(seo_title="3回目"), "prompt2", "file2.png")
)
check_true(
    "STATE-1. 同一インスタンスへの2回目のapply()呼出も1回目の成功結果に依存せず独立して成功する",
    _state1_third_exc is None,
)
check(
    "STATE-1. 3回目呼出でもgenerate()の累計呼出回数が2（1回目失敗時は未呼出、2回目・3回目で各1回）",
    len(_state1_orch_2._image_generator.calls),
    2,
)
print()

# =====================================================================
# STATE-AST-1: self属性代入Source Guard（__init__／apply()）
# =====================================================================

print("[STATE-AST-1] apply()本体がrequest単位stateをself属性へ保存しないことのSource Guard")
check_true("STATE-AST-1. apply()メソッドが存在する", _APPLY_METHOD is not None)
_apply_self_assign_names = find_self_simple_assign_names(_APPLY_METHOD)
check(
    "STATE-AST-1. apply()本体にself属性への単純Assignが存在しない",
    _apply_self_assign_names,
    [],
)
_apply_disallowed = find_disallowed_self_state_constructs(_APPLY_METHOD)
check(
    "STATE-AST-1. apply()本体にAugAssign／AnnAssign／setattr(self,...)／"
    "object.__setattr__(self,...)が存在しない（article／prompt／filename／generated_image／"
    "media_result等のrequest単位stateを保存しない）",
    _apply_disallowed,
    [],
)
_apply_local_assigns = [
    node
    for node in ast.walk(_APPLY_METHOD)
    if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) for t in node.targets)
]
check_true(
    "STATE-AST-1. apply()内にローカル変数へのAssignが存在する"
    "（Guard対比確認対象が実在すること：generated_image = ... / media_result = ...）",
    len(_apply_local_assigns) >= 1,
)
check_true(
    "STATE-AST-1. ローカル変数へのAssign（self.属性ではない）はGuard判定でself属性扱いされない",
    all(
        not any(_target_contains_self_attribute(t) for t in node.targets)
        for node in _apply_local_assigns
    ),
)
print()

# =====================================================================
# LOOP-AST-1: for／while／comprehension／generator expression禁止Guard
# =====================================================================

print("[LOOP-AST-1] for／while／comprehension／generator expression禁止Guard")
_loop_violations = find_node_type_lines(
    _ORCH_TREE,
    (ast.For, ast.While, ast.ListComp, ast.SetComp, ast.DictComp, ast.GeneratorExp),
)
check(
    "LOOP-AST-1. article_featured_media_orchestrator.py全体にfor／while／"
    "list・set・dict comprehension／generator expressionが存在しない",
    _loop_violations,
    [],
)
print()

# =====================================================================
# TRY-AST-1: try／except禁止Guard
# =====================================================================

print("[TRY-AST-1] try／except禁止Guard")
_try_violations = find_node_type_lines(_ORCH_TREE, (ast.Try,))
check("TRY-AST-1. article_featured_media_orchestrator.py全体にtry文が存在しない", _try_violations, [])
print()

# =====================================================================
# GLOBAL-AST-1: global／nonlocal禁止Guard
# =====================================================================

print("[GLOBAL-AST-1] global／nonlocal禁止Guard")
_global_nonlocal_violations = find_node_type_lines(_ORCH_TREE, (ast.Global, ast.Nonlocal))
check(
    "GLOBAL-AST-1. article_featured_media_orchestrator.py全体にglobal文・nonlocal文が存在しない",
    _global_nonlocal_violations,
    [],
)
print()

# =====================================================================
# MODULE-AST-1: module-level Assign禁止Guard
# =====================================================================

print("[MODULE-AST-1] module-level Assign禁止Guard")
_module_level_assigns = get_module_level_assign_lines(_ORCH_TREE)
check(
    "MODULE-AST-1. article_featured_media_orchestrator.pyのmodule-levelに"
    "Assign／AnnAssign／AugAssignが存在しない（class・Protocol・function定義、"
    "importは対象外）",
    _module_level_assigns,
    [],
)
print()

# =====================================================================
# SEC-1: Security Guard
# =====================================================================

print("[SEC-1] Security Guard")
_sec1_orch = ArticleFeaturedMediaOrchestrator(
    _RecordingImageGenerator(make_generated_image(data=b"SECRET_IMAGE_BYTES_MARKER")),
    _RecordingMediaUploader(make_media_result()),
)
invoke(lambda: _sec1_orch.apply(make_article(), "prompt", "file.png"))
check(
    "SEC-1. Orchestratorインスタンスが保持する属性が_image_generator／_media_uploaderの2つのみ"
    "（画像bytes等のrequest単位stateを保持しない）",
    sorted(vars(_sec1_orch).keys()),
    sorted(["_image_generator", "_media_uploader"]),
)
_sec1_import_details = get_import_details(FILES["article_featured_media_orchestrator"])
for _mod in ("logging", "os", "requests", "urllib", "openai"):
    check_false(
        f"SEC-1. article_featured_media_orchestrator.pyが{_mod}をimportしない",
        _mod in _sec1_import_details["absolute_roots"],
    )
for _call_name in ("open", "print"):
    check(
        f"SEC-1. article_featured_media_orchestrator.pyに{_call_name}()呼出がない",
        get_call_lines(FILES["article_featured_media_orchestrator"], _call_name),
        [],
    )
_sec1_env_violations = [
    node.lineno
    for node in ast.walk(_ORCH_TREE)
    if isinstance(node, ast.Attribute)
    and node.attr in ("environ", "getenv")
    and isinstance(node.value, ast.Name)
    and node.value.id == "os"
]
check("SEC-1. os.environ／os.getenv参照が存在しない", _sec1_env_violations, [])
print()

# =====================================================================
# DEP-1: 許可依存Guard（AST：ast.Import／ast.ImportFrom解析）
# =====================================================================

print("[DEP-1] 許可依存Guard")

ALLOWED_MODULES = {"typing", "ai_image_generation", "wordpress_media", "article_featured_media", "outputs"}
FORBIDDEN_EXACT = (
    "openai_image_generation",
    "generated_image_wordpress_media",
    "requests",
    "urllib",
    "openai",
    "os",
    "logging",
    "pathlib",
    "subprocess",
    "main",
    "image_resolver",
    "pipeline",
    "workflow_engine",
    "scheduler",
    "scripts",
    "ai",
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
    FILES["article_featured_media_orchestrator"], "ai_image_generation"
)
check_true(
    "DEP-1. ai_image_generationからのimportがAIImageGenerator／GeneratedImageのみの部分集合",
    _ai_image_generation_names.issubset({"AIImageGenerator", "GeneratedImage"}),
)

_wordpress_media_names = get_imported_names_from(
    FILES["article_featured_media_orchestrator"], "wordpress_media"
)
check_true(
    "DEP-1. wordpress_mediaからのimportがMediaUploadResultのみの部分集合"
    "（WordPressMediaUploader本体をimportしない）",
    _wordpress_media_names.issubset({"MediaUploadResult"}),
)

_article_featured_media_names = get_imported_names_from(
    FILES["article_featured_media_orchestrator"], "article_featured_media"
)
check_true(
    "DEP-1. article_featured_mediaからのimportがbind_featured_mediaのみの部分集合",
    _article_featured_media_names.issubset({"bind_featured_media"}),
)

_outputs_names = get_imported_names_from(FILES["article_featured_media_orchestrator"], "outputs")
check_true(
    "DEP-1. outputsからのimportがArticleDataのみの部分集合",
    _outputs_names.issubset({"ArticleData"}),
)

_typing_names = get_imported_names_from(FILES["article_featured_media_orchestrator"], "typing")
check_true(
    "DEP-1. typingからのimportがProtocolのみの部分集合",
    _typing_names.issubset({"Protocol"}),
)
print()

# =====================================================================
# DEP-2: 逆依存Guard（vacuous pass防止）
# =====================================================================

print("[DEP-2] 逆依存Guard：既存4 packageがarticle_featured_media_orchestrationをimportしていないこと")

_reverse_dep_targets = {
    "ai_image_generation": AI_IMAGE_GENERATION_DIR,
    "wordpress_media": WORDPRESS_MEDIA_DIR,
    "article_featured_media": ARTICLE_FEATURED_MEDIA_DIR,
    "outputs": OUTPUTS_DIR,
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
        if "article_featured_media_orchestration" in _details["absolute_roots"]:
            _violating_files.append(_py_file.name)
    check(
        f"DEP-2. {_package_name}がarticle_featured_media_orchestrationをimportしていない",
        _violating_files,
        [],
    )
print()

# =====================================================================
# RUNTIME-1: Consumer-less Guard（Production Runtime未接続）
# =====================================================================

print("[RUNTIME-1] Consumer-less Guard（Production Runtime未接続）")

_required_runtime_files = {
    "main.py": PROJECT_ROOT / "main.py",
    "src/image_resolver.py": PROJECT_ROOT / "src" / "image_resolver.py",
}
for _label, _path in _required_runtime_files.items():
    check_true(f"RUNTIME-1. {_label}が存在する", _path.is_file())
    _details = get_import_details(_path)
    check_false(
        f"RUNTIME-1. {_label}がarticle_featured_media_orchestrationをimportしていない（AST）",
        "article_featured_media_orchestration" in _details["absolute_roots"],
    )
    check_false(
        f"RUNTIME-1. {_label}にArticleFeaturedMediaOrchestratorという文字列が含まれない",
        file_references_name(_path, "ArticleFeaturedMediaOrchestrator"),
    )

_runtime_dirs = {
    "src/outputs": OUTPUTS_DIR,
    "src/pipeline": PROJECT_ROOT / "src" / "pipeline",
    "scripts": PROJECT_ROOT / "scripts",
}
for _dir_label, _dir_path in _runtime_dirs.items():
    check_true(f"RUNTIME-1. {_dir_label}ディレクトリが存在する", _dir_path.is_dir())
    _py_files = sorted(_dir_path.glob("*.py"))
    check_true(
        f"RUNTIME-1. {_dir_label}配下の.pyファイル一覧が1件以上存在する（vacuous pass防止）",
        len(_py_files) >= 1,
    )
    _violating = []
    for _py_file in _py_files:
        _details = get_import_details(_py_file)
        if "article_featured_media_orchestration" in _details["absolute_roots"]:
            _violating.append(_py_file.name)
    check(f"RUNTIME-1. {_dir_label}配下にimportしているファイルがない（AST）", _violating, [])

_retry_dirs = sorted(p for p in PROJECT_ROOT.glob("src/retry_*") if p.is_dir())
check_true("RUNTIME-1. retry_*ディレクトリが1件以上存在する（vacuous pass防止）", len(_retry_dirs) >= 1)
_retry_violating = []
for _retry_dir in _retry_dirs:
    for _py_file in sorted(_retry_dir.glob("*.py")):
        _details = get_import_details(_py_file)
        if "article_featured_media_orchestration" in _details["absolute_roots"]:
            _retry_violating.append(f"{_retry_dir.name}/{_py_file.name}")
check(
    f"RUNTIME-1. retry_*配下（{len(_retry_dirs)}package）にimportしているファイルがない（AST）",
    _retry_violating,
    [],
)
print()

# =====================================================================
# SIDE-1: Side Effect Guard
# =====================================================================

print("[SIDE-1] Side Effect Guard")
for _name, _path in FILES.items():
    _details = get_import_details(_path)
    for _mod in ("subprocess", "requests", "urllib", "openai", "os", "logging", "pathlib"):
        check_false(f"SIDE-1. {_name}が{_mod}をimportしない", _mod in _details["absolute_roots"])
    for _call_name in ("open", "print", "sleep", "setattr"):
        check(f"SIDE-1. {_name}に{_call_name}()呼出がない", get_call_lines(_path, _call_name), [])
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
