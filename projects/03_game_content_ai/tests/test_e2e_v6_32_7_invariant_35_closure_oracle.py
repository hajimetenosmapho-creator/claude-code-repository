"""
E2E テスト: sub-milestone 6B — Invariant #35 closure oracle（§28.-34 test #3）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    25章 Invariant #35・22.3.11節（Entrypoint Closure Contract）・28.-34節test #3。

本テストは、production entrypointの「到達しうるterminal sink（A/B/C）」の
closed setが、22.3.11節が定めるmanifest（SIDE_EFFECT_CAPABLE 9エントリ＋
NON_SIDE_EFFECT_CAPABLE 10エントリ、計19エントリ）と一致することを、
repository自身をAST解析するstatic closure oracleとして直接証明する。

test #4（tests/test_e2e_v6_32_6_invariant_35_static_oracle.py、HTTP
mutation primitiveの構文検出）とは独立した検出原理（import/call closureの
sink到達性）に基づく相互補完のオラクルである——両方が独立にPASSして初めて
Invariant #35は満たされる（28.-34節「Invariant #35のPASS条件」）。本ファイルは
test #3単体としてPASSすることのみを検証する。

Stage A（fail-fast manifest match）:
    (1) candidate root列挙：project-root直下の全*.pyファイル・scripts/配下の
        全*.pyファイル（再帰）・packaging entry_points（本repositoryには
        存在しないため空集合）の合併をファイルシステムから直接列挙する。
    (2) 22.3.11節のclosed classification manifest（19エントリ）との
        exactly-once matchを確認する。不一致（未分類・重複分類）が1件でも
        あれば、closure解析を試みる前に直ちにFAILする。

Stage B（19エントリの回帰検証、sink-terminal closureオラクル）:
    - AgentManager.run()到達4 launcher（run_news_agent.py等）：22.3.11節
      Classification rule 4.が定める登録契約（NewsAgent無条件登録・
      WorkflowTriggerAgent/PublishTriggerAgent/ReviewTriggerAgent各々の
      is_ready()ゲート）をAST解析で直接確認し、aggregate {A,B,C}を
      4エージェントそれぞれの実closure（本オラクルのAST closureエンジンで
      個別に算出）の和集合として検証する。
    - run_retry_runtime.py：RetryCompositionRoot→RetryRuntimeOrchestrator→
      RetryExecutor.execute()→WorkflowEngineManager.run()という深いchainを
      実際に読み込んで確認したうえで（本ファイル冒頭のコメント参照）、
      WorkflowEngineManager.from_config()のNEWS/REVIEW/PUBLISH登録契約
      （AgentManagerと同型だがWorkflowTriggerAgentを含まない3-way fan-out）
      を直接検証し、その3エージェントの実closureの和集合を確認する。
    - 残り15ファイル（main.py・run_ai_publish.py・run_ai_workflow.py・
      run_workflow_engine.py・run_retry_runtime.py内部で使うAgent型5クラス、
      および10 NON_SIDE_EFFECT_CAPABLEファイル）：本ファイルが実装する
      汎用recursive AST closureエンジン（import/call追跡、
      self-attribute型解決、Protocol/抽象型のfinite-set resolution）で
      実際にsink到達性を算出する。

実行方法:
    cd projects/03_game_content_ai
    .\\venv\\Scripts\\python.exe tests\\test_e2e_v6_32_7_invariant_35_closure_oracle.py
"""
from __future__ import annotations

import ast
import sys
import tempfile
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"

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
    check(label, bool(value), True)


print("=" * 60)
print("Invariant #35 closure oracle（§28.-34 test #3）E2E テスト")
print("=" * 60)
print()

# =====================================================================
# Stage A: candidate root列挙 + closed classification manifest
# =====================================================================

# 22.3.11節「closed classification manifest（全candidate root、9 + 10 = 19エントリ）」
# を直接転記する。ここに書かれた値だけがoracleの比較対象であり、本テストの
# 他の箇所はこのmanifestを直接参照するのみで、独自のgrep heuristicは持たない。
SINK_A, SINK_B, SINK_C = "A", "B", "C"

SIDE_EFFECT_CAPABLE_MANIFEST = {
    "main.py": frozenset({SINK_A, SINK_B}),
    "scripts/run_news_agent.py": frozenset({SINK_A, SINK_B, SINK_C}),
    "scripts/run_workflow_trigger_agent.py": frozenset({SINK_A, SINK_B, SINK_C}),
    "scripts/run_publish_trigger_agent.py": frozenset({SINK_A, SINK_B, SINK_C}),
    "scripts/run_review_trigger_agent.py": frozenset({SINK_A, SINK_B, SINK_C}),
    "scripts/run_ai_publish.py": frozenset({SINK_C}),
    "scripts/run_ai_workflow.py": frozenset({SINK_C}),
    "scripts/run_workflow_engine.py": frozenset({SINK_A, SINK_B, SINK_C}),
    # 22.3.11節本文（表の直後の段落）：「scripts/run_retry_runtime.pyが唯一の
    # protected composition rootであり...A・B・C到達」。9番目のSIDE_EFFECT_CAPABLE
    # エントリとして、表には現れないがここで明示的に転記する。
    "scripts/run_retry_runtime.py": frozenset({SINK_A, SINK_B, SINK_C}),
}

NON_SIDE_EFFECT_CAPABLE_MANIFEST = {
    "scripts/fetch_google_analytics_metrics.py",
    "scripts/fetch_search_console_metrics.py",
    "scripts/run_ai_improvement.py",
    "scripts/run_ai_improvement_report.py",
    "scripts/run_ai_publish_review.py",
    "scripts/run_ai_rewrite.py",
    "scripts/run_ai_rewrite_review.py",
    "scripts/show_execution_history.py",
    "scripts/show_retry_notification.py",
    "scripts/show_workflow_status.py",
}

_AGENT_MANAGER_FANOUT_FILES = {
    "scripts/run_news_agent.py",
    "scripts/run_workflow_trigger_agent.py",
    "scripts/run_publish_trigger_agent.py",
    "scripts/run_review_trigger_agent.py",
}

assert set(SIDE_EFFECT_CAPABLE_MANIFEST) & NON_SIDE_EFFECT_CAPABLE_MANIFEST == set()
assert len(SIDE_EFFECT_CAPABLE_MANIFEST) == 9
assert len(NON_SIDE_EFFECT_CAPABLE_MANIFEST) == 10

FULL_MANIFEST = dict(SIDE_EFFECT_CAPABLE_MANIFEST)
for rel in NON_SIDE_EFFECT_CAPABLE_MANIFEST:
    FULL_MANIFEST[rel] = frozenset()


def _rel(path: Path) -> str:
    return path.relative_to(PROJECT_ROOT).as_posix()


def _enumerate_candidate_roots() -> list[str]:
    """22.3.11節・28.-34節test#3(1)：candidate root定義。
    (a) project-root直下の*.py（非再帰）、(b) scripts/**/*.py（再帰）、
    (c) packaging entry_points（本repositoryにpyproject.toml/setup.py/
    setup.cfgのentry_points宣言は存在しないため空集合）。"""
    roots = []
    for p in sorted(PROJECT_ROOT.glob("*.py")):
        roots.append(_rel(p))
    for p in sorted(SCRIPTS_DIR.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        roots.append(_rel(p))
    # (c) packaging entry_points：空集合（pyproject.toml等にentry_points宣言なし）
    for fname in ("pyproject.toml", "setup.py", "setup.cfg"):
        fpath = PROJECT_ROOT / fname
        if fpath.exists():
            raise AssertionError(
                f"{fname} が新たに追加されている——packaging entry_pointsの手動確認が必要"
            )
    return roots


_candidate_roots = _enumerate_candidate_roots()

print(f"[Stage A] candidate root列挙: {len(_candidate_roots)}件")
for r in _candidate_roots:
    print(f"    {r}")
print()

# --- (2) exactly-once match ---
_unclassified = [r for r in _candidate_roots if r not in FULL_MANIFEST]
_duplicated = [r for r in _candidate_roots if _candidate_roots.count(r) > 1]

check(
    "Stage A-1. unclassified candidate root = 0（manifestに1件も出現しないroot）",
    _unclassified,
    [],
)
check(
    "Stage A-2. duplicate-classified candidate root = 0（同一fileが複数回列挙される）",
    _duplicated,
    [],
)
_manifest_only = [r for r in FULL_MANIFEST if r not in _candidate_roots]
check(
    "Stage A-3. manifestにあるがfilesystem上に存在しないroot = 0（manifestの陳腐化検出）",
    _manifest_only,
    [],
)

_stage_a_ok = not _unclassified and not _duplicated and not _manifest_only
print()

if not _stage_a_ok:
    print("=" * 60)
    print("Stage AがFAILしたため、Stage B（closure解析）はスキップする")
    print("（28.-34節test#3：到達可能性のclosure探索を試みる前に直ちにFAILする契約）")
    print("=" * 60)
    passed = sum(1 for status, _ in results_log if status == "PASS")
    failed = sum(1 for status, _ in results_log if status == "FAIL")
    print(f"結果: {passed} PASS / {failed} FAIL / 合計 {len(results_log)}")
    sys.exit(1)


# =====================================================================
# Stage B: sink-terminal closure エンジン（22.3.11節 Classification rule）
# =====================================================================
#
# 汎用recursive AST closureエンジン。以下を行う：
#   1. import解決（相対・絶対、re-export chainを含む）
#   2. self-attribute型解決（constructor引数のtype annotationを第一手段、
#      annotationがない場合はrepository全体のconstruction call siteを
#      走査するfallbackを第二手段とする——22.3.11節5.が定めるfinite-set
#      resolutionの一般化）
#   3. Protocol/抽象型経由のfinite-set resolution（repository全体で
#      「この基底クラスを継承する具象クラス」をsubclass indexとして
#      構築し、多態的な呼び出し箇所ではそのunionを採用する）
#   4. 3つのterminal sink（A/B/C）への到達を記録し、それ以上は追跡しない
#
# 標準ライブラリ・サードパーティ依存（repository外のモジュール）は
# import解決に失敗するため自然にhaltする（22.3.11節1.）。


class Sink:
    A = "A"
    B = "B"
    C = "C"


# --- sinkの定義（22.3.11節2.） ---
SINK_DEFS = {
    (("outputs", "wordpress_output"), "WordPressOutput", "save"): Sink.A,
    (("article_featured_media_runtime", "article_featured_media_runtime"), "ArticleFeaturedMediaRuntime", "apply"): Sink.B,
    (("ai", "ai_publish_service"), "AiPublishService", "run"): Sink.C,
    (("ai", "ai_publish_service"), "AiPublishService", "_process"): Sink.C,
    (("ai", "ai_publish_service"), "AiPublishService", "_post"): Sink.C,
}


# ---------------------------------------------------------------------
# モジュール解決・AST cache
# ---------------------------------------------------------------------

_ast_cache: dict[Path, ast.Module] = {}


def get_ast(path: Path) -> ast.Module | None:
    path = path.resolve()
    if path not in _ast_cache:
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            _ast_cache[path] = None
            return None
        try:
            _ast_cache[path] = ast.parse(source, filename=str(path))
        except SyntaxError:
            _ast_cache[path] = None
    return _ast_cache[path]


def dotted_to_path(dotted: tuple) -> Path | None:
    """src/配下のdotted module path（tupleで表現）をファイルパスへ解決する。
    標準ライブラリ・サードパーティ・repository外のモジュールは解決できず
    Noneを返す（22.3.11節1.のhalt規則）。"""
    if not dotted:
        return None
    as_pkg = SRC_DIR.joinpath(*dotted, "__init__.py")
    if as_pkg.exists():
        return as_pkg
    as_mod = SRC_DIR.joinpath(*dotted[:-1], dotted[-1] + ".py")
    if as_mod.exists():
        return as_mod
    return None


# standalone module（project-root *.py・scripts/*.py）は、他モジュールから
# importされることがない（leaf entrypoint）ため、dotted解決の対象外とし、
# 個別に(("__file__", str(path)),) という合成キーで扱う。
def file_module_key(path: Path) -> tuple:
    return ("__file__", str(path.resolve()))


ModKey = tuple  # dotted tuple、または("__file__", path)


def mod_path(mod: ModKey) -> Path | None:
    if mod and mod[0] == "__file__":
        return Path(mod[1])
    return dotted_to_path(mod)


def mod_ast(mod: ModKey) -> ast.Module | None:
    p = mod_path(mod)
    if p is None:
        return None
    return get_ast(p)


# ---------------------------------------------------------------------
# import alias解決
# ---------------------------------------------------------------------

# alias table cache: mod -> {local_name: (target_mod, target_symbol_or_None)}
_import_cache: dict[ModKey, dict] = {}


def _package_of(mod: ModKey) -> tuple:
    """相対importの基準パッケージ（dotted tupleのみ、standalone fileは
    パッケージを持たないため空tupleを返す）。"""
    if mod[0] == "__file__":
        return ()
    p = mod_path(mod)
    if p is not None and p.name == "__init__.py":
        return mod  # 自身がパッケージ
    return mod[:-1]


def get_imports(mod: ModKey) -> dict:
    if mod in _import_cache:
        return _import_cache[mod]
    tree = mod_ast(mod)
    table: dict = {}
    if tree is None:
        _import_cache[mod] = table
        return table

    pkg = _package_of(mod)

    # module全体（関数内・try/if内のlazy importを含む）を対象にする。
    # 一部over-approximationになるが（関数ローカルimportがmodule全体の
    # alias tableへ漏れる）、lazy importを取りこぼして解決不能にする
    # リスクの方が本オラクルの目的（sink到達性の見落とし防止）にとって
    # 重大であるため、意図的にこちらを採用する。
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                local = alias.asname or alias.name.split(".")[0]
                table[local] = (tuple(alias.name.split(".")), None)
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                # 相対import: from . import x / from .x import y / from ..x import y
                base = pkg[: len(pkg) - (node.level - 1)] if node.level > 1 else pkg
                if node.module:
                    base = base + tuple(node.module.split("."))
                for alias in node.names:
                    local = alias.asname or alias.name
                    table[local] = (base, alias.name)
            else:
                if node.module is None:
                    continue
                base = tuple(node.module.split("."))
                for alias in node.names:
                    local = alias.asname or alias.name
                    table[local] = (base, alias.name)
    _import_cache[mod] = table
    return table


def resolve_symbol(mod: ModKey, name: str, _seen=None) -> tuple | None:
    """(mod, name) が指すクラス/関数定義を repository 内から解決する。
    見つからない場合（標準ライブラリ・サードパーティ・repository外）はNone。
    戻り値: (defining_mod, ast.ClassDef|ast.FunctionDef) or None"""
    if _seen is None:
        _seen = set()
    key = (mod, name)
    if key in _seen:
        return None
    _seen.add(key)

    tree = mod_ast(mod)
    if tree is None:
        return None

    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return (mod, node)

    imports = get_imports(mod)
    if name in imports:
        target_mod, target_symbol = imports[name]
        return resolve_symbol(target_mod, target_symbol or name, _seen)

    return None


def resolve_name_to_class(mod: ModKey, name: str) -> tuple | None:
    """(mod内のNameまたはAttribute末尾識別子) name が指す「クラス」を解決する。
    ClassDefにのみ解決される場合だけ (defining_mod, class_name) を返す。"""
    resolved = resolve_symbol(mod, name)
    if resolved is None:
        return None
    defining_mod, node = resolved
    if isinstance(node, ast.ClassDef):
        return (defining_mod, node.name)
    return None


# ---------------------------------------------------------------------
# クラスレジストリ・subclass index（repository全体を1回だけeagerly走査）
# ---------------------------------------------------------------------

class ClassInfo:
    __slots__ = ("mod", "name", "node", "bases", "methods")

    def __init__(self, mod, name, node):
        self.mod = mod
        self.name = name
        self.node = node
        self.bases: list[tuple] = []  # [(mod, class_name), ...]（解決できたbaseのみ）
        self.methods: dict = {}
        for item in node.body:
            if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                self.methods[item.name] = item


_class_registry: dict[tuple, ClassInfo] = {}  # (mod, name) -> ClassInfo


def _iter_all_repo_py_files():
    for p in sorted(SRC_DIR.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        yield p
    for p in sorted(SCRIPTS_DIR.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        yield p
    for p in sorted(PROJECT_ROOT.glob("*.py")):
        yield p


def _mod_key_for_src_file(p: Path) -> ModKey:
    rel = p.relative_to(SRC_DIR)
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1][: -len(".py")]
    return tuple(parts)


def _build_class_registry():
    for p in _iter_all_repo_py_files():
        if SRC_DIR in p.parents or p.parent == SRC_DIR:
            mod = _mod_key_for_src_file(p)
        else:
            mod = file_module_key(p)
        tree = get_ast(p)
        if tree is None:
            continue
        for node in tree.body:
            if isinstance(node, ast.ClassDef):
                info = ClassInfo(mod, node.name, node)
                _class_registry[(mod, node.name)] = info


def _resolve_base_classes():
    for (mod, name), info in _class_registry.items():
        for base_expr in info.node.bases:
            base_name = None
            if isinstance(base_expr, ast.Name):
                base_name = base_expr.id
            elif isinstance(base_expr, ast.Attribute):
                base_name = base_expr.attr
            if base_name is None:
                continue
            resolved = resolve_name_to_class(mod, base_name)
            if resolved is not None:
                info.bases.append(resolved)


_build_class_registry()
_resolve_base_classes()

_subclass_index: dict[tuple, list[tuple]] = {}
for (mod, name), info in _class_registry.items():
    for base in info.bases:
        _subclass_index.setdefault(base, []).append((mod, name))


def find_method(mod, cls_name, method_name, _seen=None):
    """クラス自身、または解決済みbaseを辿ってmethodを探す（簡易MRO）。"""
    if _seen is None:
        _seen = set()
    key = (mod, cls_name)
    if key in _seen:
        return None
    _seen.add(key)
    info = _class_registry.get(key)
    if info is None:
        return None
    if method_name in info.methods:
        return (mod, cls_name, info.methods[method_name])
    for base_mod, base_name in info.bases:
        found = find_method(base_mod, base_name, method_name, _seen)
        if found is not None:
            return found
    return None


# ---------------------------------------------------------------------
# 型annotation文字列 → クラス集合 の解決
# ---------------------------------------------------------------------

def _annotation_names(annotation_node) -> list[str]:
    """annotation node（ast.Constant文字列 or 実際のast式）から、
    'X | Y'・'"X | Y"'・'Optional[X]'等に含まれる識別子名を抽出する。"""
    if annotation_node is None:
        return []
    if isinstance(annotation_node, ast.Constant) and isinstance(annotation_node.value, str):
        try:
            parsed = ast.parse(annotation_node.value, mode="eval").body
        except SyntaxError:
            return []
        return _annotation_names(parsed)
    names = []
    for node in ast.walk(annotation_node):
        if isinstance(node, ast.Name):
            names.append(node.id)
        elif isinstance(node, ast.Attribute):
            names.append(node.attr)
    return names


def resolve_annotation_to_classes(mod: ModKey, annotation_node) -> set:
    result = set()
    for name in _annotation_names(annotation_node):
        if name in ("None", "object", "Any", "bool", "str", "int", "float", "dict", "list"):
            continue
        resolved = resolve_name_to_class(mod, name)
        if resolved is not None:
            result.add(resolved)
    return result


# ---------------------------------------------------------------------
# self-attribute型解決（22.3.11節5.のfinite-set resolutionの一般化）
# ---------------------------------------------------------------------

_self_attr_cache: dict[tuple, dict] = {}


def _local_var_types_in_body(mod: ModKey, body_stmts, param_types: dict, self_attr_types: dict | None = None) -> dict:
    """関数bodyを単純に上から下へ走査し、`name = <expr>` の右辺型を
    ベストエフォートで追跡する（分岐・再代入は特に区別しない、
    over-approximationのunionで扱う）。`for x in self.<attr>:` /
    `for x in <local_var>:` / `for x in <param>:` の形（22.3.11節5.の
    finite-set resolutionが必要になる典型パターン、例：
    `for output in self.outputs:` → `output.save(...)`）についても、
    iterableの要素型をloop変数の型として束縛する。"""
    self_attr_types = self_attr_types or {}
    local_types: dict = {}

    def note(name, types):
        if not types:
            return
        local_types.setdefault(name, set()).update(types)

    synthetic = ast.Module(body=list(body_stmts), type_ignores=[])
    for node in ast.walk(synthetic):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            types = _expr_types(mod, node.value, param_types, local_types, self_attr_types)
            note(node.targets[0].id, types)
        elif isinstance(node, (ast.For, ast.AsyncFor)) and isinstance(node.target, ast.Name):
            types = _iter_element_types(mod, node.iter, param_types, local_types, self_attr_types)
            note(node.target.id, types)
    return local_types


def _iter_element_types(mod, iter_expr, param_types, local_types, self_attr_types) -> set:
    """`for x in <iter_expr>:` のiterableの要素型を解決する。
    list[T]アノテーションは resolve_annotation_to_classes が"list"のような
    非解決名を無視しTのみを残すため、self_attr_types/param_typesの値を
    そのまま要素型として扱ってよい。"""
    if isinstance(iter_expr, ast.Attribute) and isinstance(iter_expr.value, ast.Name) and iter_expr.value.id == "self":
        return set(self_attr_types.get(iter_expr.attr, set()))
    if isinstance(iter_expr, ast.Name):
        if iter_expr.id in local_types:
            return set(local_types[iter_expr.id])
        if iter_expr.id in param_types:
            return set(param_types[iter_expr.id])
    return set()


def _expr_types(mod: ModKey, expr, param_types: dict, local_types: dict, self_attr_types: dict | None = None) -> set:
    """式が「どのクラスのインスタンスか」を返す（ベストエフォート）。
    解決できない場合は空集合。"""
    self_attr_types = self_attr_types or {}
    if expr is None:
        return set()
    if isinstance(expr, ast.Name):
        if expr.id in local_types:
            return set(local_types[expr.id])
        if expr.id in param_types:
            return set(param_types[expr.id])
        return set()
    if isinstance(expr, ast.Call):
        func = expr.func
        if isinstance(func, ast.Name):
            resolved = resolve_name_to_class(mod, func.id)
            if resolved is not None:
                return {resolved}
            # クラス直接構築ではない場合：module-level factory関数
            # （例：`build_protected_featured_media_runtime(...)`）の可能性を
            # 戻り値annotationから解決する（22.3.2節の`build_*`関数群のような、
            # classmethodではない独立関数factoryパターンの一般化）。
            resolved_sym = resolve_symbol(mod, func.id)
            if resolved_sym is not None:
                r_mod, node = resolved_sym
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return _plain_function_return_types(r_mod, func.id)
            return set()
        if isinstance(func, ast.Attribute):
            # X.method(...) 形式：Xがクラス（classmethod factory）か、
            # self.attr（インスタンス）かで扱いを分ける。
            if isinstance(func.value, ast.Name):
                owner_name = func.value.id
                if owner_name == "self":
                    return set()  # self.method(...) は本関数では扱わない
                owner_class = resolve_name_to_class(mod, owner_name)
                if owner_class is not None:
                    return _factory_return_types(owner_class[0], owner_class[1], func.attr)
                return set()
            # `self.<attr>.get(<key>)` 形式：dict型self-attributeの
            # `.get()`呼び出し（例：`executor = self._step_executors.get(step)`、
            # WorkflowEngineExecutor.run()の実パターン）。dict[K, V]の
            # K・Vを区別しないself_attr_types（22.3.11節5.の一般化）を
            # そのままVの近似として流用する（`_resolve_call_target()`の
            # ケース6と同型のover-approximation）。
            if (
                func.attr == "get"
                and isinstance(func.value, ast.Attribute)
                and isinstance(func.value.value, ast.Name)
                and func.value.value.id == "self"
            ):
                return set(self_attr_types.get(func.value.attr, set()))
            return set()
        return set()
    if isinstance(expr, ast.Attribute) and isinstance(expr.value, ast.Name):
        # `x = <owner>.<field>` 形式：ownerの型が既知（local/param）である
        # 場合、そのクラス（複数可、discriminated unionを含む）のdataclass
        # field annotationからfield自体の型を解決する（例：
        # `runtime = side_effect_binding.runtime`、22.3.2節のbinding型経由の
        # runtime取得パターン）。ownerが"self"の場合は本関数では扱わない
        # （self-attribute解決は`_resolve_self_attr_types()`の責務）。
        owner_name = expr.value.id
        if owner_name == "self":
            return set()
        owner_types = local_types.get(owner_name) or param_types.get(owner_name)
        if not owner_types:
            return set()
        result = set()
        for (o_mod, o_cls) in owner_types:
            result |= _dataclass_field_types(o_mod, o_cls, expr.attr)
        return result
    return set()


_plain_function_return_cache: dict[tuple, set] = {}


def _plain_function_return_types(mod, func_name) -> set:
    """module-level（classに属さない）factory関数の戻り値型を、戻り値
    annotationから解決する（`_factory_return_types()`のclassmethod専用版に
    対する、独立関数版の一般化）。"""
    key = (mod, func_name)
    if key in _plain_function_return_cache:
        return _plain_function_return_cache[key]
    _plain_function_return_cache[key] = set()  # 再帰防止の先置き

    resolved = resolve_symbol(mod, func_name)
    result = set()
    if resolved is not None:
        def_mod, func_node = resolved
        if isinstance(func_node, (ast.FunctionDef, ast.AsyncFunctionDef)) and func_node.returns is not None:
            result = resolve_annotation_to_classes(def_mod, func_node.returns)

    _plain_function_return_cache[key] = result
    return result


_dataclass_field_cache: dict[tuple, set] = {}


def _dataclass_field_types(mod, cls_name, field_name) -> set:
    """(mod, cls_name)のクラス本体（dataclass fieldのAnnAssign）から
    field_nameのannotationを解決する。"""
    key = (mod, cls_name, field_name)
    if key in _dataclass_field_cache:
        return _dataclass_field_cache[key]

    info = _class_registry.get((mod, cls_name))
    result = set()
    if info is not None:
        for item in info.node.body:
            if (
                isinstance(item, ast.AnnAssign)
                and isinstance(item.target, ast.Name)
                and item.target.id == field_name
            ):
                result = resolve_annotation_to_classes(mod, item.annotation)
                break

    _dataclass_field_cache[key] = result
    return result


_factory_return_cache: dict[tuple, set] = {}


def _factory_return_types(mod, cls_name, method_name) -> set:
    """classmethod factory（from_env/from_config/from_paths等）の戻り値型を
    解決する。優先順位: (1) 戻り値annotation、(2) body中の`return cls(...)`/
    `return ClassName(...)`文の集約、(3) fallback：クラス自身。"""
    key = (mod, cls_name, method_name)
    if key in _factory_return_cache:
        return _factory_return_cache[key]

    found = find_method(mod, cls_name, method_name)
    if found is None:
        _factory_return_cache[key] = {(mod, cls_name)}
        return _factory_return_cache[key]
    def_mod, def_cls, func_node = found

    result = set()
    if func_node.returns is not None:
        result |= resolve_annotation_to_classes(def_mod, func_node.returns)

    if not result:
        for node in ast.walk(func_node):
            if isinstance(node, ast.Return) and isinstance(node.value, ast.Call):
                rfunc = node.value.func
                if isinstance(rfunc, ast.Name):
                    if rfunc.id == "cls":
                        result.add((mod, cls_name))
                    else:
                        resolved = resolve_name_to_class(def_mod, rfunc.id)
                        if resolved is not None:
                            result.add(resolved)
                elif isinstance(rfunc, ast.Attribute) and isinstance(rfunc.value, ast.Name):
                    if rfunc.value.id == "cls":
                        result.add((mod, cls_name))

    if not result:
        result.add((mod, cls_name))

    _factory_return_cache[key] = result
    return result


def _param_types_of(mod: ModKey, func_node) -> dict:
    """関数の引数名 -> annotation解決済み型集合。"""
    out = {}
    args = func_node.args
    all_args = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
    for a in all_args:
        if a.annotation is not None:
            types = resolve_annotation_to_classes(mod, a.annotation)
            if types:
                out[a.arg] = types
    return out


def _resolve_self_attr_types(mod, cls_name) -> dict:
    key = (mod, cls_name)
    if key in _self_attr_cache:
        return _self_attr_cache[key]
    # 事前にキャッシュへ空dictを置き、再帰呼び出し中の無限ループを避ける。
    _self_attr_cache[key] = {}

    info = _class_registry.get(key)
    result: dict = {}
    if info is not None and "__init__" in info.methods:
        init_node = info.methods["__init__"]
        param_types = _param_types_of(mod, init_node)
        local_types = _local_var_types_in_body(mod, init_node.body, param_types)

        for node in ast.walk(init_node):
            if (
                isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Attribute)
                and isinstance(node.targets[0].value, ast.Name)
                and node.targets[0].value.id == "self"
            ):
                attr = node.targets[0].attr
                types = _expr_types(mod, node.value, param_types, local_types)
                if not types and isinstance(node.value, ast.Name):
                    # 直接param/localで解決できなかった場合の最終フォールバック
                    types = set()
                if types:
                    result.setdefault(attr, set()).update(types)

    # --- fallback: repository全体のconstruction call siteを走査する ---
    # (22.3.11節5.の一般化。__init__のparam annotationが存在しない/
    #  duck-typing前提のattribute（例：ImprovementStepExecutor.__init__の
    #  `service`引数）は、annotationからは型を得られないため、
    #  repository内の実際の construction call site から逆算する。)
    unresolved_params = _unresolved_init_params(mod, cls_name)
    if unresolved_params:
        call_types = _scan_construction_sites_for_params(mod, cls_name, unresolved_params)
        for attr, types in call_types.items():
            if types:
                result.setdefault(attr, set()).update(types)

    _self_attr_cache[key] = result
    return result


def _unresolved_init_params(mod, cls_name) -> dict:
    """__init__の中で `self.<attr> = <param>` かつ<param>にannotationが
    ない（＝型が未確定の）ものを {param_name: attr_name} で返す。"""
    info = _class_registry.get((mod, cls_name))
    if info is None or "__init__" not in info.methods:
        return {}
    init_node = info.methods["__init__"]
    annotated_params = {
        a.arg
        for a in (list(init_node.args.posonlyargs) + list(init_node.args.args) + list(init_node.args.kwonlyargs))
        if a.annotation is not None
    }
    out = {}
    for node in ast.walk(init_node):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Attribute)
            and isinstance(node.targets[0].value, ast.Name)
            and node.targets[0].value.id == "self"
            and isinstance(node.value, ast.Name)
            and node.value.id not in annotated_params
        ):
            out[node.value.id] = node.targets[0].attr
    return out


def _scan_construction_sites_for_params(mod, cls_name, unresolved_params: dict) -> dict:
    """repository全体を走査し、`ClassName(...)` の呼び出し箇所で
    unresolved_paramsに該当する引数へ渡された式の型を解決する。"""
    info = _class_registry.get((mod, cls_name))
    if info is None or "__init__" not in info.methods:
        return {}
    init_node = info.methods["__init__"]
    all_args = list(init_node.args.posonlyargs) + list(init_node.args.args)
    param_order = [a.arg for a in all_args]  # self含む

    result: dict = {}
    for call_mod, call_ast in _all_module_asts():
        for node in ast.walk(call_ast):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            target_name = None
            if isinstance(func, ast.Name):
                target_name = func.id
            elif isinstance(func, ast.Attribute):
                target_name = func.attr
            if target_name != cls_name:
                continue
            resolved = resolve_name_to_class(call_mod, target_name)
            if resolved != (mod, cls_name):
                continue

            # このcall siteのローカル型情報（簡易）
            enclosing_func = _enclosing_function(call_ast, node)
            call_param_types = _param_types_of(call_mod, enclosing_func) if enclosing_func else {}
            call_local_types = (
                _local_var_types_in_body(call_mod, enclosing_func.body, call_param_types)
                if enclosing_func
                else {}
            )

            for kw in node.keywords:
                if kw.arg in unresolved_params:
                    types = _expr_types(call_mod, kw.value, call_param_types, call_local_types)
                    if types:
                        attr = unresolved_params[kw.arg]
                        result.setdefault(attr, set()).update(types)
            for idx, arg in enumerate(node.args, start=1):  # position 0 = self
                if idx < len(param_order):
                    pname = param_order[idx]
                    if pname in unresolved_params:
                        types = _expr_types(call_mod, arg, call_param_types, call_local_types)
                        if types:
                            attr = unresolved_params[pname]
                            result.setdefault(attr, set()).update(types)
    return result


_module_ast_list_cache = None


def _all_module_asts():
    global _module_ast_list_cache
    if _module_ast_list_cache is None:
        out = []
        for p in _iter_all_repo_py_files():
            if SRC_DIR in p.parents or p.parent == SRC_DIR:
                mod = _mod_key_for_src_file(p)
            else:
                mod = file_module_key(p)
            tree = get_ast(p)
            if tree is not None:
                out.append((mod, tree))
        _module_ast_list_cache = out
    return _module_ast_list_cache


def _enclosing_function(tree, target_node):
    """target_nodeを直接含む最小のFunctionDef/AsyncFunctionDefを返す
    （モジュールtop-levelの場合はNone）。"""
    best = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for child in ast.walk(node):
                if child is target_node:
                    best = node
                    break
    return best


# ---------------------------------------------------------------------
# closure本体：関数/メソッドのbodyを辿り、到達するsinkを算出する
# ---------------------------------------------------------------------

# 既知のcallback-typed parameter（Protocol/Callable型で、repository内に
# 具象クラス階層を持たない）についての、手動検証済みexemption。
#
# `post_admission_hook`：src/retry_engine/retry_executor.py::RetryExecutor.execute()
# 内部で構築される唯一の実装（本ファイル内のnested function）は
# `self._lineage.mark_execution_started(...)` のみを呼び、sink A/B/Cの
# いずれにも到達しない（手動確認済み）。この関数はnested defとして
# retry_executor.py::execute()のbody全体に含まれるため、run_retry_runtime.py
# 側のchain検証（本ファイル後半）で個別に確認済みである。
# WorkflowEngineExecutor.run()側の`context.post_admission_hook(run_id)`は
# Protocol型（PostAdmissionHook）呼び出しであり、repository全体で
# この関数以外の実装が構築されないことを手動確認済みのため、追加の
# sink寄与なしとして扱う（fail-closedにせず、検証済みexemptionとして
# 明示的に除外する）。
_KNOWN_SAFE_CALLBACK_ATTRS = {"post_admission_hook"}


class ClosureResult:
    def __init__(self):
        self.sinks: set = set()
        self.unresolved: list = []  # list[str] 理由

    def __repr__(self):
        return f"ClosureResult(sinks={self.sinks!r}, unresolved={self.unresolved!r})"


def compute_closure(mod, cls_name, method_name, _visited=None) -> ClosureResult:
    """(mod, cls_name, method_name) から到達するterminal sink集合を計算する。
    cls_nameがNoneの場合はモジュールレベル関数。"""
    if _visited is None:
        _visited = set()
    result = ClosureResult()
    key = (mod, cls_name, method_name)
    if key in _visited:
        return result
    _visited.add(key)

    if cls_name is not None:
        found = find_method(mod, cls_name, method_name)
        if found is None:
            result.unresolved.append(f"method not found: {mod}.{cls_name}.{method_name}")
            return result
        def_mod, def_cls, func_node = found
        param_types = _param_types_of(def_mod, func_node)
        self_attr_types = _resolve_self_attr_types(def_mod, def_cls)
    else:
        resolved = resolve_symbol(mod, method_name)
        if resolved is None:
            result.unresolved.append(f"function not found: {mod}.{method_name}")
            return result
        def_mod, func_node = resolved
        def_cls = None
        param_types = _param_types_of(def_mod, func_node)
        self_attr_types = {}

    local_types = _local_var_types_in_body(def_mod, func_node.body, param_types, self_attr_types)

    for node in ast.walk(func_node):
        if not isinstance(node, ast.Call):
            continue
        func = node.func

        # --- subprocess.run(...) 特別扱い（22.3.11節本文・14章：
        #     NewsPipelineRunner.run()がmain.pyをsubprocess起動する経路は、
        #     プロセス境界を越えてmain.py自身のclosureへ「到達」したものと
        #     扱う。design doc 1.5節・14章・2016行目参照。この特別扱いは
        #     `src/pipeline/news_pipeline_runner.py`のsubprocess.run()呼び出し
        #     1箇所にのみ適用する）。 ---
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "run"
            and isinstance(func.value, ast.Name)
            and func.value.id == "subprocess"
            and def_mod[-1:] == ("news_pipeline_runner",)
        ):
            main_py_closure = _main_py_closure()
            result.sinks |= main_py_closure.sinks
            result.unresolved.extend(main_py_closure.unresolved)
            continue

        # --- 既知の安全callback（手動検証済みexemption） ---
        if isinstance(func, ast.Attribute) and func.attr in _KNOWN_SAFE_CALLBACK_ATTRS:
            continue

        target = _resolve_call_target(def_mod, def_cls, func, param_types, self_attr_types, local_types)
        if target is None:
            # 解決不能：ただしよく知られた「安全に無視してよい」パターン
            # （組み込み関数・print等の単純name呼び出しで、repository内
            #  symbolでないもの）は無視する。resolve_symbolがNoneを返す
            # 場合はrepository外（stdlib/third-party）であり、22.3.11節1.
            # の「repository外はhalt」に該当するため、unresolvedとしては
            # 扱わない（構文上区別できないrepository内symbolの解決失敗のみ
            # unresolvedとして計上する）。
            continue

        if target == "UNRESOLVABLE_DYNAMIC":
            result.unresolved.append(
                f"dynamic/unresolvable call at {mod}:{getattr(node, 'lineno', '?')} "
                f"in {def_mod}.{cls_name}.{method_name}"
            )
            continue

        for (t_mod, t_cls, t_method) in target:
            sink = SINK_DEFS.get((t_mod, t_cls, t_method))
            if sink is not None:
                result.sinks.add(sink)
                continue  # terminal：これ以上追跡しない
            sub = compute_closure(t_mod, t_cls, t_method, _visited)
            result.sinks |= sub.sinks
            result.unresolved.extend(sub.unresolved)

    return result


def _resolve_call_target(mod, cls_ctx, func_expr, param_types, self_attr_types, local_types):
    """Callノードのfunc式から、呼び出し先を (mod, cls_name_or_None, method_name)
    のリストとして解決する。解決できない場合はNone（無視してよい＝repository外
    または未対応の単純パターン）、動的で解決不能な場合は文字列
    "UNRESOLVABLE_DYNAMIC" を返す。"""

    # --- getattr(obj, "literal")(...) は本repositoryのsink到達経路には
    #     出現しない（test#4のgrammarとは異なるスコープ）ため、
    #     動的attribute名のみunresolvableとして扱う。 ---
    if isinstance(func_expr, ast.Call) and isinstance(func_expr.func, ast.Name) and func_expr.func.id == "getattr":
        name_arg = func_expr.args[1] if len(func_expr.args) > 1 else None
        if not (isinstance(name_arg, ast.Constant) and isinstance(name_arg.value, str)):
            return "UNRESOLVABLE_DYNAMIC"
        return None

    if isinstance(func_expr, ast.Name):
        # モジュール内の関数 or クラス直接構築（コンストラクタ呼び出し自体は
        # sinkにならないため、__init__は特別扱いしない＝追跡しない。
        # ただし関数の場合は追跡する）。
        resolved = resolve_symbol(mod, func_expr.id)
        if resolved is None:
            return None
        r_mod, node = resolved
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            return [(r_mod, None, func_expr.id)]
        return None  # クラス直接構築：__init__のsink到達は別途self_attr経由で捕捉

    if not isinstance(func_expr, ast.Attribute):
        return None

    attr = func_expr.attr
    value = func_expr.value

    if isinstance(value, ast.Name):
        # ケース1: self.<method>(...)  1段階＝同一クラスの別メソッドへの
        #          delegation（例: self._save_log(...)）。
        if value.id == "self" and cls_ctx is not None:
            same_class_method = find_method(mod, cls_ctx, attr)
            if same_class_method is not None:
                return [(same_class_method[0], same_class_method[1], attr)]
            # メソッドとして見つからない場合、self.<attr>自体がcallableな
            # DI依存として直接呼ばれている可能性（例: self._callback(...)）を
            # self_attr_types経由で解決する。型情報が一切ない場合は
            # sink候補になり得ないため無視する（unresolvableとはしない）。
            if attr in self_attr_types:
                return _dispatch_polymorphic(self_attr_types[attr], attr)
            return None

        # ケース2: ローカル変数.<method>(...)
        if value.id in local_types:
            return _dispatch_polymorphic(local_types[value.id], attr)

        # ケース3: パラメータ.<method>(...)
        if value.id in param_types:
            return _dispatch_polymorphic(param_types[value.id], attr)

        # ケース4: ClassName.<classmethod>(...) （通常は_expr_typesが処理する
        # ため、ここには「クラスかつ戻り値を使わず直接呼ぶ」形しか来ない。
        # 例: SomeClass.some_classmethod(...) を直接文として呼ぶ場合。
        resolved_cls = resolve_name_to_class(mod, value.id)
        if resolved_cls is not None:
            found = find_method(resolved_cls[0], resolved_cls[1], attr)
            if found is not None:
                return [(found[0], found[1], attr)]
            return None

        return None

    if isinstance(value, ast.Attribute):
        # ケース5: self.<attr>.<method>(...)  2段階＝DI依存の呼び出し
        #          （例: self._runner.run(...)、self._engine.run(...)）。
        if isinstance(value.value, ast.Name) and value.value.id == "self" and cls_ctx is not None:
            inner_attr = value.attr
            if inner_attr in self_attr_types:
                return _dispatch_polymorphic(self_attr_types[inner_attr], attr)
            # 型情報が一切ない場合（duck-typing属性等）は無視する。
            return None
        # self.<a>.<b>.<method>(...) （3段階以上）・ローカル変数経由の
        # 多段attributeは本repositoryのsink到達経路には出現しない
        # （手動確認済み）ため未対応（無視）。
        return None

    if isinstance(value, (ast.Call, ast.Subscript)):
        # ケース6: `<dict受信先>.get(<key>).<method>(...)` /
        #          `<dict受信先>[<key>].<method>(...)` 形式——dict型
        #          self-attributeの値型経由の多態的dispatch（例：
        #          `self._step_executors.get(step).execute(agent_context)`、
        #          WorkflowEngineExecutor.run()の実パターン）。
        #          受信先（`.get`/subscriptのbase）の型情報を、既存の
        #          self-attribute/local/param型解決からそのまま流用する
        #          （dict[K, V]のK・Vを区別せず両方をunionとして扱う
        #          over-approximationだが、method_nameを実際に持つのは
        #          通常V側のみであるため、_dispatch_polymorphic側の
        #          「methodが見つからないクラスからの寄与なし」処理により
        #          実質的にVのみが寄与する）。
        if isinstance(value, ast.Call):
            inner_func = value.func
            if not (isinstance(inner_func, ast.Attribute) and inner_func.attr == "get"):
                return None
            base_expr = inner_func.value
        else:
            base_expr = value.value

        if isinstance(base_expr, ast.Attribute) and isinstance(base_expr.value, ast.Name) and base_expr.value.id == "self" and cls_ctx is not None:
            base_types = self_attr_types.get(base_expr.attr, set())
        elif isinstance(base_expr, ast.Name):
            base_types = local_types.get(base_expr.id) or param_types.get(base_expr.id) or set()
        else:
            base_types = set()

        if not base_types:
            return None
        return _dispatch_polymorphic(base_types, attr)

    return None


def attr_name_for_self(func_expr):
    return func_expr.attr


def _dispatch_polymorphic(types: set, method_name: str):
    """typesが指す各クラスについて、method_nameを解決する。
    typesが空集合の場合はUNRESOLVABLE_DYNAMICとする（型が一切
    分からない動的呼び出し）。
    さらに、typesに含まれる各クラスがsubclass_indexのキーである場合
    （＝repository内に具象subclassが存在する抽象/基底型である場合）は、
    そのクラス自身のmethodではなく、全subclassのunionを採用する
    （22.3.11節5.のfinite-set resolutionの一般化）。"""
    if not types:
        return "UNRESOLVABLE_DYNAMIC"

    expanded = set()
    for t in types:
        subclasses = _subclass_index.get(t)
        if subclasses:
            expanded |= set(subclasses)
        else:
            expanded.add(t)

    out = []
    for (t_mod, t_cls) in expanded:
        found = find_method(t_mod, t_cls, method_name)
        if found is not None:
            out.append((found[0], found[1], method_name))
        # methodが見つからない場合（例：Nullオブジェクトが同名methodを
        # 持たない）は単純に無視する（そのクラスからの寄与なし）。
    return out


_main_py_closure_cache = None


def _main_py_closure() -> ClosureResult:
    global _main_py_closure_cache
    if _main_py_closure_cache is None:
        main_mod = file_module_key(PROJECT_ROOT / "main.py")
        _main_py_closure_cache = compute_closure(main_mod, None, "main")
    return _main_py_closure_cache


# =====================================================================
# Stage B-1: main.py・run_ai_publish.py・run_ai_workflow.py・
#            run_workflow_engine.py（4/5ファイル、run_retry_runtime.pyは
#            後述の専用検証）
# =====================================================================


def closure_of_script(rel_path: str, func_name: str = "main") -> ClosureResult:
    p = PROJECT_ROOT / rel_path
    mod = file_module_key(p)
    return compute_closure(mod, None, func_name)


print("[Stage B] 汎用closureエンジンによる算出（main.py・run_ai_publish.py・"
      "run_ai_workflow.py・run_workflow_engine.py）")

_main_result = _main_py_closure()
print(f"    main.py: sinks={_main_result.sinks} unresolved={_main_result.unresolved}")
check("Stage B-1a. main.py の到達sink集合", _main_result.sinks, set(SIDE_EFFECT_CAPABLE_MANIFEST["main.py"]))
check("Stage B-1a'. main.py に解決不能な動的呼び出し辺なし", _main_result.unresolved, [])

_ai_publish_result = closure_of_script("scripts/run_ai_publish.py")
print(f"    run_ai_publish.py: sinks={_ai_publish_result.sinks} unresolved={_ai_publish_result.unresolved}")
check(
    "Stage B-1b. run_ai_publish.py の到達sink集合",
    _ai_publish_result.sinks,
    set(SIDE_EFFECT_CAPABLE_MANIFEST["scripts/run_ai_publish.py"]),
)
check("Stage B-1b'. run_ai_publish.py に解決不能な動的呼び出し辺なし", _ai_publish_result.unresolved, [])

_ai_workflow_result = closure_of_script("scripts/run_ai_workflow.py")
print(f"    run_ai_workflow.py: sinks={_ai_workflow_result.sinks} unresolved={_ai_workflow_result.unresolved}")
check(
    "Stage B-1c. run_ai_workflow.py の到達sink集合",
    _ai_workflow_result.sinks,
    set(SIDE_EFFECT_CAPABLE_MANIFEST["scripts/run_ai_workflow.py"]),
)
check("Stage B-1c'. run_ai_workflow.py に解決不能な動的呼び出し辺なし", _ai_workflow_result.unresolved, [])

_workflow_engine_result = closure_of_script("scripts/run_workflow_engine.py")
print(f"    run_workflow_engine.py: sinks={_workflow_engine_result.sinks} unresolved={_workflow_engine_result.unresolved}")
check(
    "Stage B-1d. run_workflow_engine.py の到達sink集合",
    _workflow_engine_result.sinks,
    set(SIDE_EFFECT_CAPABLE_MANIFEST["scripts/run_workflow_engine.py"]),
)
check("Stage B-1d'. run_workflow_engine.py に解決不能な動的呼び出し辺なし", _workflow_engine_result.unresolved, [])
print()


# =====================================================================
# Stage B-2: 10 NON_SIDE_EFFECT_CAPABLE ファイル
# =====================================================================

print("[Stage B] 汎用closureエンジンによる算出（NON_SIDE_EFFECT_CAPABLE 10件）")
for rel in sorted(NON_SIDE_EFFECT_CAPABLE_MANIFEST):
    r = closure_of_script(rel)
    print(f"    {rel}: sinks={r.sinks} unresolved={r.unresolved}")
    check(f"Stage B-2. {rel} の到達sink集合は空", r.sinks, set())
    check(f"Stage B-2'. {rel} に解決不能な動的呼び出し辺なし", r.unresolved, [])
print()


# =====================================================================
# Stage B-3: AgentManager.run()到達4 launcher（登録契約＋aggregate closure）
# =====================================================================
#
# 22.3.11節Classification rule 4.：NewsAgentは無条件登録、
# WorkflowTriggerAgent/PublishTriggerAgent/ReviewTriggerAgentは各々の
# is_ready()ゲートで条件付き登録される（AgentManager.from_config()）。
# 本テストは (a) この登録契約をAST構造として直接確認したうえで、
# (b) 4エージェントそれぞれの実closure（本エンジンで算出）の和集合が
# manifestの宣言する{A,B,C}と一致することを確認する。


def _local_simple_constructor_vars(func_node) -> dict:
    """関数body全体を単純に走査し、`name = ClassName(...)` という単一代入
    （分岐を問わない、over-approximation）から `name -> ClassName` の対応表を
    構築する。`AgentExecutor(<agent_var>)` のように、Agentインスタンスが
    先に変数へ束縛されてから参照される呼び出し形（agent_manager.py::
    from_config()の実際のコードパターン、例：
    `news_agent = NewsAgent(...); executors=[AgentExecutor(news_agent)]`）を
    解決するために使う。"""
    mapping: dict = {}
    for node in ast.walk(func_node):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
        ):
            mapping[node.targets[0].id] = node.value.func.id
    return mapping


def _agent_class_from_call(call_node, var_map: dict):
    # AgentExecutor(<agent_expr>) の <agent_expr> がどのAgentクラスの
    # コンストラクタ呼び出しかを取り出す。<agent_expr>がinlineの
    # `AgentClass(...)`呼び出しである場合と、先に変数へ束縛された後
    # `AgentExecutor(agent_var)`という形で参照される場合の両方を扱う。
    if not (isinstance(call_node, ast.Call) and isinstance(call_node.func, ast.Name) and call_node.func.id == "AgentExecutor"):
        return None
    if not call_node.args:
        return None
    inner = call_node.args[0]
    if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name):
        return inner.func.id
    if isinstance(inner, ast.Name) and inner.id in var_map:
        return var_map[inner.id]
    return None


def _registration_contract(mod: ModKey, cls_name: str, method_name: str) -> dict:
    """`<mod>.<cls_name>.<method_name>()`（AgentManager.from_config()・
    WorkflowEngineManager.from_config()いずれも同型）を解析し、どのAgent型が
    無条件登録・どのAgent型がis_ready()ゲート付き登録かをAST構造として
    直接確認する。"""
    found = find_method(mod, cls_name, method_name)
    assert found is not None, f"{mod}.{cls_name}.{method_name}() が見つからない"
    _, _, func_node = found

    var_map = _local_simple_constructor_vars(func_node)
    unconditional = set()
    conditional = set()

    # 関数top-levelのstatementを見て、If文の中にあるかどうかで
    # 条件付き/無条件を判定する（ネストしたIf内であることのみ確認すれば
    # 十分。is_ready()呼び出しがそのIf.testに含まれることも確認する）。
    def walk_stmts(stmts, in_if_is_ready: bool):
        for stmt in stmts:
            if isinstance(stmt, ast.If):
                test_has_is_ready = any(
                    isinstance(n, ast.Call)
                    and isinstance(n.func, ast.Attribute)
                    and n.func.attr == "is_ready"
                    for n in ast.walk(stmt.test)
                )
                walk_stmts(stmt.body, in_if_is_ready or test_has_is_ready)
                walk_stmts(stmt.orelse, in_if_is_ready)
            else:
                for call_node in ast.walk(stmt):
                    agent_cls = _agent_class_from_call(call_node, var_map)
                    if agent_cls is not None:
                        if in_if_is_ready:
                            conditional.add(agent_cls)
                        else:
                            unconditional.add(agent_cls)

    walk_stmts(func_node.body, False)
    return {"unconditional": unconditional, "conditional": conditional}


def _agent_manager_registration_contract() -> dict:
    """src/ai/agent_manager.py::AgentManager.from_config() を解析し、
    どのAgent型が無条件登録・どのAgent型がis_ready()ゲート付き登録かを
    AST構造として直接確認する。"""
    return _registration_contract(("ai", "agent_manager"), "AgentManager", "from_config")


_registration = _agent_manager_registration_contract()
print("[Stage B-3] AgentManager.from_config() 登録契約")
print(f"    無条件登録: {_registration['unconditional']}")
print(f"    is_ready()ゲート付き登録: {_registration['conditional']}")
check_true(
    "Stage B-3a. NewsAgentが無条件登録される",
    "NewsAgent" in _registration["unconditional"] and "NewsAgent" not in _registration["conditional"],
)
check(
    "Stage B-3b. WorkflowTriggerAgent/PublishTriggerAgent/ReviewTriggerAgentが"
    "is_ready()ゲート付きでのみ登録される",
    _registration["conditional"],
    {"WorkflowTriggerAgent", "PublishTriggerAgent", "ReviewTriggerAgent"},
)

_news_agent_closure = compute_closure(("ai", "news_agent"), "NewsAgent", "act")
_workflow_trigger_agent_closure = compute_closure(("ai", "workflow_trigger_agent"), "WorkflowTriggerAgent", "act")
_publish_trigger_agent_closure = compute_closure(("ai", "publish_trigger_agent"), "PublishTriggerAgent", "act")
_review_trigger_agent_closure = compute_closure(("ai", "review_trigger_agent"), "ReviewTriggerAgent", "act")

print(f"    NewsAgent.act() closure: {_news_agent_closure.sinks} unresolved={_news_agent_closure.unresolved}")
print(f"    WorkflowTriggerAgent.act() closure: {_workflow_trigger_agent_closure.sinks} unresolved={_workflow_trigger_agent_closure.unresolved}")
print(f"    PublishTriggerAgent.act() closure: {_publish_trigger_agent_closure.sinks} unresolved={_publish_trigger_agent_closure.unresolved}")
print(f"    ReviewTriggerAgent.act() closure: {_review_trigger_agent_closure.sinks} unresolved={_review_trigger_agent_closure.unresolved}")

_agent_manager_aggregate = (
    _news_agent_closure.sinks
    | _workflow_trigger_agent_closure.sinks
    | _publish_trigger_agent_closure.sinks
    | _review_trigger_agent_closure.sinks
)
_agent_manager_unresolved = (
    _news_agent_closure.unresolved
    + _workflow_trigger_agent_closure.unresolved
    + _publish_trigger_agent_closure.unresolved
    + _review_trigger_agent_closure.unresolved
)

check(
    "Stage B-3c. 4エージェントの実closureの和集合 = {A,B,C}（manifestのaggregateと一致）",
    _agent_manager_aggregate,
    {SINK_A, SINK_B, SINK_C},
)
check("Stage B-3c'. 4エージェントの実closureに解決不能な動的呼び出し辺なし", _agent_manager_unresolved, [])

for rel in sorted(_AGENT_MANAGER_FANOUT_FILES):
    check(
        f"Stage B-3d. {rel} の到達sink集合（aggregate、manifest宣言値）",
        _agent_manager_aggregate,
        set(SIDE_EFFECT_CAPABLE_MANIFEST[rel]),
    )
print()


# =====================================================================
# Stage B-4: run_retry_runtime.py（深いchainの手動検証 + WorkflowEngineManager
# fan-out登録契約 + aggregate closure）
# =====================================================================
#
# 【run_retry_runtime.pyのchainについての設計判断（手動読解の記録）】
#
# scripts/run_retry_runtime.py の呼び出しchainは、以下の実ファイルを
# 実際に読んで確認した（本テスト実装時点のsource）：
#
#   1. scripts/run_retry_runtime.py::main()
#        → RetryCompositionRoot.from_env()  （構築のみ）
#        → RetryRuntimeOrchestrator.from_composition_root(root)  （構築のみ）
#        → orchestrator.run_once(dry_run=...)
#   2. src/retry_runtime_orchestrator/retry_runtime_orchestrator.py::
#        RetryRuntimeOrchestrator.run_once()
#        → self.manager.execute_dispatchable_retries(events, dry_run=dry_run)
#          （self.manager: "RetryManager | NullRetryManager"、constructor annotation）
#   3. src/retry_engine/retry_manager.py::RetryManager.execute_dispatchable_retries()
#        → dispatch_retry_events() → self._execution_selector.select(...)
#          → self._execution_coordinator.execute(selected, retry_fn=self.retry, ...)
#        この経路は「callableパラメータ（retry_fn）へのbound method参照の
#        引渡し」というcallback-threadingを含み、汎用closureエンジンの
#        単純なself-attribute型解決では追跡できない（型注釈はCallable相当）。
#        そのため、`RetryManager.retry()`が最終的に`self._executor.execute(
#        request, lineage, claim)`（retry_executor.py:477、grep済み）を
#        呼ぶことを、構造チェック（AST上の呼び出し文の存在確認）として
#        別途直接検証する（下記 `_verify_call_present` 参照）。
#   4. src/retry_engine/retry_executor.py::RetryExecutor.execute()
#        → self._engine.run(...)  （self._engine: WorkflowEngineManager、
#          constructor annotationで解決可能——ここは汎用エンジンでも追跡できる）
#   5. src/workflow_engine/workflow_engine_manager.py::WorkflowEngineManager.run()
#        → self._executor.run(context)  （self._executor: WorkflowEngineExecutor）
#   6. src/workflow_engine/workflow_engine_executor.py::WorkflowEngineExecutor.run()
#        → self._step_executors.get(step).execute(agent_context)
#        step_executorsは WorkflowEngineManager.from_config() が構築する
#        {NEWS: AgentExecutor(NewsAgent(...))（無条件）,
#         REVIEW: AgentExecutor(ReviewTriggerAgent(...))（is_ready()ゲート）,
#         PUBLISH: AgentExecutor(PublishTriggerAgent(...))（is_ready()ゲート）}
#        という、AgentManagerと同型だがWorkflowTriggerAgentを含まない
#        3-way fan-outである（config依存のため、AgentManagerの4-launcherと
#        同じ理由でfull closure traceは行わず、登録契約の直接確認＋
#        3エージェントの実closureの和集合で代替する、22.3.11節
#        Classification rule 4.と同型の扱い）。
#
# 上記2.のself.manager型注釈・4.のself._engine型注釈・5.のself._executor型
# 注釈はいずれも汎用エンジンのself-attribute解決でも到達可能だが、3.の
# callback-threadingのみ手動検証（構造チェック）に置き換える。


def _source_contains_call(mod: ModKey, cls_name: str, method_name: str, callee_attr_chain: list) -> bool:
    """(mod, cls_name, method_name) のbody中に、
    `<recv0>.<recv1>....<callee_attr_chain[-1]>(...)` 形式（属性チェーンの
    末尾から順にcallee_attr_chainと一致する）のCallノードが存在するかを
    直接確認する（grepではなくASTノード構造の一致判定）。"""
    found = find_method(mod, cls_name, method_name) if cls_name else resolve_symbol(mod, method_name)
    if found is None:
        return False
    if cls_name:
        _, _, func_node = found
    else:
        _, func_node = found

    def chain_matches(func_expr, chain):
        # chain は末尾（method名）から先頭（receiver root）の順で並んでいる
        # 例: ["run", "_engine", "self"] は self._engine.run(...) にマッチ
        cur = func_expr
        for i, name in enumerate(chain):
            if i == 0:
                if not (isinstance(cur, ast.Attribute) and cur.attr == name):
                    return False
                cur = cur.value
            else:
                if isinstance(cur, ast.Name):
                    return cur.id == name and i == len(chain) - 1
                if not (isinstance(cur, ast.Attribute) and cur.attr == name):
                    return False
                cur = cur.value
        return isinstance(cur, ast.Name) and cur.id == chain[-1]

    for node in ast.walk(func_node):
        if isinstance(node, ast.Call) and chain_matches(node.func, callee_attr_chain):
            return True
    return False


print("[Stage B-4] run_retry_runtime.py の深いchain検証")

_chain_checks = [
    (
        "run_retry_runtime.py が RetryRuntimeOrchestrator.run_once() を呼ぶ",
        file_module_key(PROJECT_ROOT / "scripts" / "run_retry_runtime.py"),
        None,
        "main",
        ["run_once", "orchestrator"],
    ),
    (
        "RetryRuntimeOrchestrator.run_once() が self.manager.execute_dispatchable_retries() を呼ぶ",
        ("retry_runtime_orchestrator", "retry_runtime_orchestrator"),
        "RetryRuntimeOrchestrator",
        "run_once",
        ["execute_dispatchable_retries", "manager", "self"],
    ),
    (
        "RetryManager._retry_locked()（retry()からlock取得後に委譲される実処理）"
        "が self._executor.execute() を呼ぶ（retry_manager.py:477）",
        ("retry_engine", "retry_manager"),
        "RetryManager",
        "_retry_locked",
        ["execute", "_executor", "self"],
    ),
    (
        "RetryExecutor.execute() が self._engine.run() を呼ぶ",
        ("retry_engine", "retry_executor"),
        "RetryExecutor",
        "execute",
        ["run", "_engine", "self"],
    ),
    (
        "WorkflowEngineManager.run() が self._executor.run() を呼ぶ",
        ("workflow_engine", "workflow_engine_manager"),
        "WorkflowEngineManager",
        "run",
        ["run", "_executor", "self"],
    ),
]

for label, mod, cls_name, method_name, chain in _chain_checks:
    ok = _source_contains_call(mod, cls_name, method_name, chain)
    check_true(f"Stage B-4. {label}", ok)


def _workflow_engine_manager_registration_contract() -> dict:
    """src/workflow_engine/workflow_engine_manager.py::
    WorkflowEngineManager.from_config() を解析し、NEWS/REVIEW/PUBLISHの
    登録契約を確認する（AgentManagerの登録契約チェックと同一の共通ロジック
    `_registration_contract()` を使う）。"""
    return _registration_contract(
        ("workflow_engine", "workflow_engine_manager"), "WorkflowEngineManager", "from_config"
    )


_we_registration = _workflow_engine_manager_registration_contract()
print(f"    WorkflowEngineManager.from_config() 無条件登録: {_we_registration['unconditional']}")
print(f"    WorkflowEngineManager.from_config() is_ready()ゲート付き登録: {_we_registration['conditional']}")
check_true(
    "Stage B-4a. WorkflowEngineManager: NewsAgentが無条件登録される",
    "NewsAgent" in _we_registration["unconditional"] and "NewsAgent" not in _we_registration["conditional"],
)
check(
    "Stage B-4b. WorkflowEngineManager: ReviewTriggerAgent/PublishTriggerAgentが"
    "is_ready()ゲート付きでのみ登録され、WorkflowTriggerAgentは含まれない",
    _we_registration["conditional"],
    {"ReviewTriggerAgent", "PublishTriggerAgent"},
)

_retry_runtime_aggregate = (
    _news_agent_closure.sinks | _review_trigger_agent_closure.sinks | _publish_trigger_agent_closure.sinks
)
_retry_runtime_unresolved = (
    _news_agent_closure.unresolved + _review_trigger_agent_closure.unresolved + _publish_trigger_agent_closure.unresolved
)
check(
    "Stage B-4c. run_retry_runtime.py のaggregate closure = {A,B,C}（manifest宣言値と一致）",
    _retry_runtime_aggregate,
    set(SIDE_EFFECT_CAPABLE_MANIFEST["scripts/run_retry_runtime.py"]),
)
check("Stage B-4c'. run_retry_runtime.py のaggregate closureに解決不能な動的呼び出し辺なし", _retry_runtime_unresolved, [])
print()


# =====================================================================
# [POSITIVE/NEGATIVE CONTROL] closureエンジン自身の検出力を確認する
# =====================================================================
#
# repository実ファイルのみを対象とした上記テストは「現状のコードには
# manifestとの不一致がない」ことしか示さない。closureエンジンが実際に
# 「NON_SIDE_EFFECT_CAPABLE-shapedなファイルがsinkを呼んだ場合」を
# 検出できることを、合成fixtureで直接確認する
# （test_e2e_v6_25_0のSEC-GUARD-POSITIVE-CONTROLと同型のパターン）。

print("[POSITIVE/NEGATIVE CONTROL] closureエンジンの検出力確認")


def _with_temp_module(source: str, mod_key: ModKey):
    """sourceを一時ファイルへ書き出し、そのmod_keyのASTとして_ast_cacheへ
    直接注入する（repositoryへは一切書き込まない）。呼び出し元は
    finally節でcacheエントリを除去すること。"""
    tree = ast.parse(source, filename=f"<control-fixture:{mod_key}>")
    path = mod_path(mod_key)
    assert path is not None, f"mod_path解決に失敗: {mod_key}"
    _ast_cache[path.resolve()] = tree
    _import_cache.pop(mod_key, None)
    _self_attr_cache.clear()
    _factory_return_cache.clear()
    global _module_ast_list_cache
    _module_ast_list_cache = None


def _restore_module(mod_key: ModKey):
    path = mod_path(mod_key)
    if path is not None:
        _ast_cache.pop(path.resolve(), None)
    _import_cache.pop(mod_key, None)
    _self_attr_cache.clear()
    _factory_return_cache.clear()
    global _module_ast_list_cache
    _module_ast_list_cache = None


# POS-CONTROL-1: 「NON_SIDE_EFFECT_CAPABLE-shaped」な合成scriptがSink Aを
# 直接呼んだ場合、closureエンジンが空集合ではなくSink Aを検出すること。
_fake_root_path = PROJECT_ROOT / "__control_fixture_root__.py"
_fake_mod = file_module_key(_fake_root_path)
_fake_source_hit = """
from outputs.wordpress_output import WordPressOutput

def main():
    output = WordPressOutput.from_env_with_context(None, None)
    output.save(None)
"""
try:
    _with_temp_module(_fake_source_hit, _fake_mod)
    _fake_result = compute_closure(_fake_mod, None, "main")
    print(f"    POS-CONTROL-1 (sink直接呼び出し): sinks={_fake_result.sinks}")
    check_true(
        "POS-CONTROL-1. closureエンジンはSink Aへの直接呼び出しを検出する",
        SINK_A in _fake_result.sinks,
    )
finally:
    _restore_module(_fake_mod)

# NEG-CONTROL-1: 同じ形だがsinkを呼ばない合成scriptは空集合のままであること
# （エンジンが常にsink候補を返すよう壊れていないことの対照確認）。
_fake_source_miss = """
from outputs.wordpress_output import WordPressOutput

def main():
    output = WordPressOutput.from_env_with_context(None, None)
    return output.is_available()
"""
try:
    _with_temp_module(_fake_source_miss, _fake_mod)
    _fake_result_miss = compute_closure(_fake_mod, None, "main")
    print(f"    NEG-CONTROL-1 (sink非呼び出し): sinks={_fake_result_miss.sinks}")
    check(
        "NEG-CONTROL-1. sinkを呼ばない合成scriptは空集合のまま",
        _fake_result_miss.sinks,
        set(),
    )
finally:
    _restore_module(_fake_mod)

# POS-CONTROL-2: finite-set resolution（OutputManager.save_all()相当）が
# 実際に機能していること——BaseOutputのsubclass unionにWordPressOutputが
# 含まれることで、抽象型経由の呼び出しでもSink Aが検出されることを確認する。
_pos2_result = compute_closure(("outputs", "manager"), "OutputManager", "save_all")
print(f"    POS-CONTROL-2 (OutputManager.save_all()、BaseOutput finite-set): sinks={_pos2_result.sinks}")
check_true(
    "POS-CONTROL-2. OutputManager.save_all() はBaseOutputのfinite-set resolution経由でSink Aを検出する",
    SINK_A in _pos2_result.sinks,
)

# POS-CONTROL-3: dynamic getattr（非literal属性名）に遭遇した場合、
# unresolvableとして記録されること（fail-closed動作の直接確認）。
_fake_source_dynamic = """
def main(obj, method_name):
    return getattr(obj, method_name)()
"""
try:
    _with_temp_module(_fake_source_dynamic, _fake_mod)
    _fake_result_dynamic = compute_closure(_fake_mod, None, "main")
    print(f"    POS-CONTROL-3 (dynamic getattr): unresolved={_fake_result_dynamic.unresolved}")
    check_true(
        "POS-CONTROL-3. 非literal属性名のgetattr(...)()はunresolvableとして記録される",
        len(_fake_result_dynamic.unresolved) >= 1,
    )
finally:
    _restore_module(_fake_mod)

print()


# =====================================================================
# 結果サマリー
# =====================================================================

print("=" * 60)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = sum(1 for status, _ in results_log if status == "FAIL")
print(f"結果: {passed} PASS / {failed} FAIL / 合計 {len(results_log)}")
if failed:
    print("失敗したテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
print("全テストPASS")
