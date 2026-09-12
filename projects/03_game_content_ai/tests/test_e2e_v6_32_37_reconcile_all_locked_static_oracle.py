"""
E2E テスト: Release 6.32 — `_reconcile_all_locked()` static oracle
（§18 test#23、Codex Round 9 §3で言及された補助的repository integrity invariant）

Source of Truth: docs/design/
side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md
§9.5.2a（reconciliation orphan releaseはinline処理、単独APIとして切り出さない設計判断）・
§18 test#23（「`_reconcile_all_locked()`が`reconcile_all()`以外から呼ばれる経路が
存在しないことをstatic oracle（補助的）で確認する」）

## read-only事前確認で判明した既存の空白

`test_e2e_v6_32_28_protected_operation_manifest_static_oracle.py`は
`create_for_attempt()`の呼び出し箇所制限を検証するstatic oracleであり、
自身のdocstringで「§18 test#23」を名乗っている。しかし現行（Round 9で
全面差し替えされた）§18本文の項目23は、`create_for_attempt()`ではなく
「`_reconcile_all_locked()`が`reconcile_all()`以外から呼ばれない」ことを
指しており、test_e2e_v6_32_28はこの主張を検証していない
（`create_for_attempt()`呼び出し箇所制限はそれ自体正しい別の補助的invariant
であり、test_e2e_v6_32_28自体は無効化しない——単にラベルが古い版の
番号のまま残っている）。本ファイルは、Round 9以降の現行§18 test#23が
実際に要求する検証（`_reconcile_all_locked()`の呼び出し箇所制限）を
新規に追加する。ラベルの不整合自体はdocumentation cross-reference
cleanupとして別途扱う（本ファイル・test_e2e_v6_32_28の該当箇所を修正する）。

## 重要な位置づけの明記（過大claim禁止）

本static oracleは、`create_for_attempt()`用のoracle（test_e2e_v6_32_28）と
同様、**test実行時にのみ働くrepository integrity guard**であり、
runtime security authorityの代替ではない。`_reconcile_all_locked()`が
`self`経由のprivateメソッドとして呼ばれる以上、Pythonの言語機構としては
どのメソッドからでも技術的には呼び出し可能である——本oracleはあくまで
「現在のソースコード上、実際にそのような呼び出しが存在しないこと」を
機械的に検出するのみであり、将来のreflection的な迂回やmalicious
introspectionまで防ぐものではない（§9.5.3の既存スタンスと同型）。

`_reconcile_all_locked()`が`reconcile_all()`（`RetryExecutionLock`を保持
した状態でのみ呼ばれる公開API）以外から呼ばれないことは、
「reconcile_all()内でRetryExecutionLockを保持している間だけCLAIMED
orphan回収を実行する、という構造そのものがauthorityの根拠」
（§9.5.2a）という設計判断の前提を、コードレベルで裏付ける補助的証拠
として位置づける。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_37_reconcile_all_locked_static_oracle.py
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


print("=" * 70)
print("_reconcile_all_locked() static oracle（§18 test#23） E2E テスト")
print("=" * 70)
print()

_TARGET_ATTR = "_reconcile_all_locked"
_ALLOWED_FILE = "src/retry_lineage/retry_lineage_manager.py"
_ALLOWED_ENCLOSING_FUNCTION = "reconcile_all"


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

print(f"[候補一覧] _reconcile_all_locked() 呼び出し箇所: {len(_sites)}件")
for s in _sites:
    print(f"    {s}")
print()

check_true(
    "1. _reconcile_all_locked()への呼び出し箇所が少なくとも1件存在する（vacuous-pass防止）",
    len(_sites) >= 1,
)

_outside_allowed_file = [s for s in _sites if s.file != _ALLOWED_FILE]
check(
    "2. _reconcile_all_locked()への呼び出し箇所は retry_lineage_manager.py 以外に存在しない",
    [f"{s.file}:{s.lineno}" for s in _outside_allowed_file],
    [],
)

_inside_allowed_file = [s for s in _sites if s.file == _ALLOWED_FILE]
_outside_allowed_function = [s for s in _inside_allowed_file if s.enclosing_function != _ALLOWED_ENCLOSING_FUNCTION]
check(
    "3. retry_lineage_manager.py内の呼び出し箇所は reconcile_all() 本体1箇所のみ",
    [f"{s.file}:{s.lineno} (func={s.enclosing_function})" for s in _outside_allowed_function],
    [],
)

check(
    "4. 許可された呼び出し箇所は正確に1件のみ（reconcile_all()内）",
    len(_inside_allowed_file) - len(_outside_allowed_function),
    1,
)

# [POSITIVE CONTROL] オラクル自身の検出力を合成fixtureで直接確認する
# （test_e2e_v6_32_28と同型の手法——vacuous-passでないことを機械的に証明する）。
print()
print("[POSITIVE CONTROL] オラクル自身の検出力確認")

_violation_source = '''
class FakeManager:
    def reconcile_all(self):
        return self._reconcile_all_locked()

    def some_other_public_method(self):
        # 許可されていない呼び出し箇所（違反ケース）
        return self._reconcile_all_locked()
'''

with tempfile.TemporaryDirectory() as td:
    fixture_path = Path(td) / "fake_manager.py"
    fixture_path.write_text(_violation_source, encoding="utf-8")
    fixture_sites = _analyze_file(fixture_path)

check(
    "5. [POSITIVE CONTROL] 合成fixture（許可外呼び出しを含む）から2件検出する（検出力の確認）",
    len(fixture_sites), 2,
)
_fixture_violations = [s for s in fixture_sites if s.enclosing_function != "reconcile_all"]
check_true(
    "6. [POSITIVE CONTROL] 許可外の呼び出し箇所（some_other_public_method内）を正しく検出する",
    len(_fixture_violations) == 1 and _fixture_violations[0].enclosing_function == "some_other_public_method",
)
print()


# =====================================================================
# サマリー
# =====================================================================
print("=" * 70)
total = len(results_log)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = total - passed
print(f"合計: {total}件 / PASS: {passed}件 / FAIL: {failed}件")
if failed:
    print()
    print("FAILしたテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
print("すべてPASSしました。")
