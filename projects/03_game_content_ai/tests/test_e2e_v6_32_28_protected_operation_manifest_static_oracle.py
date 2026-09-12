"""
E2E テスト: Release 6.32 Phase 2 — Protected Operation Manifest static oracle

Source of Truth: docs/design/
side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md
§9.5.3・§21

Approved Architecture Amendment（Round 10 APPROVED）が定める、補助的
repository integrity invariant：`create_for_attempt()`（authority-bearing
mutation primitive）への呼び出し箇所が、`retry_lineage_manager.py`内の
唯一の許可された呼び出し元（`mark_execution_started()`）1箇所のみであること
をAST解析で機械的に検証する。

**documentation cleanup注記（2026年、実装評価時の訂正）**：本ファイルは
以前「§18 test#23」を名乗っていたが、Round 9で全面差し替えされた現行の
§18本文における項目23は「`reconcile_all()` administrative recovery
boundary + raw owner-less release API=0」という別内容を指す（該当証拠は
`test_e2e_v6_32_37_reconcile_all_locked_static_oracle.py`）。本ファイルが
検証する`create_for_attempt()`呼び出し箇所制限は、§9.5.3が言及する補助的
invariantであり、Round 9以降の§18 test matrix再編では専用のtest番号を
付与されていない（§21実装ノート参照）。本ファイル自体の検証内容・
production挙動への影響は一切ない。

**重要（§9.5.3・Round 8/9/10の判断）**：本オラクルはtest実行時にのみ働く
repository integrity invariantであり、runtime authorityの代替ではない。
主たる防御線は composition root（RetryCompositionRoot）による facade
（ManifestReaderFacade/ManifestRegistrarFacade）のinterface scopingである
（production_closureテストのグループ4参照）。本オラクルは
`RetryLineageManager`自身の将来のrefactoringミスに対する保険として
補助的に機能する。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_28_protected_operation_manifest_static_oracle.py
"""
import ast
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent

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
print("Protected Operation Manifest static oracle（§9.5.3・§18 test#23）E2E テスト")
print("=" * 60)
print()

_TARGET_ATTR = "create_for_attempt"
_ALLOWED_FILE = "src/retry_lineage/retry_lineage_manager.py"
_ALLOWED_ENCLOSING_FUNCTION = "mark_execution_started"


def _iter_production_py_files(project_root: Path):
    for base in ("src", "scripts"):
        base_dir = project_root / base
        if not base_dir.exists():
            continue
        for p in sorted(base_dir.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            yield p
    for p in sorted(project_root.glob("*.py")):
        yield p


def _rel(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()


class _CallSite:
    def __init__(self, file: str, lineno: int, enclosing_function: str | None, receiver_kind: str):
        self.file = file
        self.lineno = lineno
        self.enclosing_function = enclosing_function
        self.receiver_kind = receiver_kind

    def __repr__(self):
        return f"<{self.file}:{self.lineno} func={self.enclosing_function} receiver={self.receiver_kind}>"


def _analyze_file(path: Path) -> list:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    rel = _rel(path)
    sites: list[_CallSite] = []

    parent_of: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_of[id(child)] = parent

    def _enclosing_function_name(node) -> str | None:
        cur = node
        while id(cur) in parent_of:
            cur = parent_of[id(cur)]
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return cur.name
        return None

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        attr_name = None
        receiver_kind = "unknown"
        if isinstance(func, ast.Attribute) and func.attr == _TARGET_ATTR:
            attr_name = func.attr
            receiver_kind = "attribute-call"
        elif (
            isinstance(func, ast.Call)
            and isinstance(func.func, ast.Name)
            and func.func.id == "getattr"
            and len(func.args) >= 2
            and isinstance(func.args[1], ast.Constant)
            and func.args[1].value == _TARGET_ATTR
        ):
            attr_name = _TARGET_ATTR
            receiver_kind = "getattr-call"

        if attr_name != _TARGET_ATTR:
            continue

        sites.append(_CallSite(rel, node.lineno, _enclosing_function_name(node), receiver_kind))

    return sites


def run_oracle() -> list:
    all_sites: list[_CallSite] = []
    for path in _iter_production_py_files(PROJECT_ROOT):
        all_sites.extend(_analyze_file(path))
    return all_sites


_sites = run_oracle()

print(f"[候補一覧] create_for_attempt() 呼び出し箇所: {len(_sites)}件")
for s in _sites:
    print(f"    {s}")
print()

check_true(
    "1. create_for_attempt()への呼び出し箇所が少なくとも1件存在する（vacuous-pass防止）",
    len(_sites) >= 1,
)

_outside_allowed_file = [s for s in _sites if s.file != _ALLOWED_FILE]
check(
    "2. create_for_attempt()への呼び出し箇所は retry_lineage_manager.py 以外に存在しない",
    [f"{s.file}:{s.lineno}" for s in _outside_allowed_file],
    [],
)

_inside_allowed_file = [s for s in _sites if s.file == _ALLOWED_FILE]
_outside_allowed_function = [s for s in _inside_allowed_file if s.enclosing_function != _ALLOWED_ENCLOSING_FUNCTION]
check(
    "3. retry_lineage_manager.py内の呼び出し箇所は mark_execution_started() 本体1箇所のみ",
    [f"{s.file}:{s.lineno} (func={s.enclosing_function})" for s in _outside_allowed_function],
    [],
)

check(
    "4. 許可された呼び出し箇所は正確に1件のみ（mark_execution_started()内）",
    len(_inside_allowed_file) - len(_outside_allowed_function),
    1,
)

# [POSITIVE CONTROL] オラクル自身の検出力を合成fixtureで直接確認する。
print()
print("[POSITIVE CONTROL] オラクル自身の検出力確認")


def _classify_source(source: str) -> list:
    import tempfile
    tree_tmp = tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8")
    tree_tmp.write(source)
    tree_tmp.close()
    tmp_path = Path(tree_tmp.name)
    try:
        return _analyze_file(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)


_control_source = """
def unauthorized_direct_call(manifest_store, root_run_id, attempt_ordinal, member_run_id):
    return manifest_store.create_for_attempt(root_run_id, attempt_ordinal, member_run_id)
"""
_control_sites = _classify_source(_control_source)
check_true("POS-1: 合成fixture内のcreate_for_attempt()直接呼び出しが検出される", len(_control_sites) == 1)
if _control_sites:
    check("POS-1b: enclosing_functionが正しく解決される", _control_sites[0].enclosing_function, "unauthorized_direct_call")

_control_source_getattr = """
def unauthorized_getattr_call(manifest_store, root_run_id, attempt_ordinal, member_run_id):
    return getattr(manifest_store, "create_for_attempt")(root_run_id, attempt_ordinal, member_run_id)
"""
_control_sites_getattr = _classify_source(_control_source_getattr)
check_true("POS-2: getattr()経由の間接呼び出しも検出される", len(_control_sites_getattr) == 1)

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
