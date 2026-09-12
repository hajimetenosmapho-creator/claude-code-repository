"""
E2E テスト: Release 6.32 sub-milestone 6D cluster 4
Invariant #15 — MEDIA_UPLOAD store/manager型のrepository全体AST静的列挙

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    28.-27節（2件）。
    docs/design/side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md
    Implementation Clarification（Phase 2 production remediation、HUMAN GATE
    APPROVED — OPTION A WITH NARROW INVARIANT #15 CLARIFICATION）。

Invariant #15（25章）は「MEDIA_UPLOADの全durable state**変更**は、単一の
MediaUploadSafetyCoordinatorを経由する」と主張する（mutation authorityの閉包性、
Coordinator構築箇所の単数性そのものを主張するものではない）。本テストは元々
「構築箇所=main.py 1箇所のみ」をInvariant #15のstatic oracle代理条件として
実装していたが、Phase 2 production remediation（Protected Operation Manifest）
により、`RetryCompositionRoot`（親/orchestratorプロセス）が、terminalization/
reconciliation時のMEDIA_UPLOAD evidence分類専用（`SideEffectSafetyClassifier`→
`coordinator.get()`のみ、read-only）に、独立した第2のCoordinatorインスタンスを
構築する必要が生じた——main.py（NEWS等のsubprocess）とは別プロセスであり、同一
runtime instanceを共有できないため。これはInvariant #15の文言（durable state
**変更**の閉包性）には抵触しない（mutation authorityはMediaUploadSafetyCoordinator
に閉じたまま）。

本テストはこの区別を反映し、以下を検証する（project-root・src/・scripts/配下の
全*.pyファイルをAST走査）：
    - ArticleMediaUploadStateManager
    - JsonMediaUploadApplicabilityStore（MediaUploadApplicabilityStoreの唯一の
      具象実装）
    - JsonMediaUploadAttemptContextStore（MediaUploadAttemptContextStoreの
      唯一の具象実装）
(a) コンストラクタ呼び出し箇所が、承認された**exactな**2箇所（main.py・
src/retry_composition/retry_composition_root.py、wildcard/package-wide除外は
使わない）以外に存在しないこと、(b) 構築済みインスタンスがCoordinator以外へ
渡される箇所が0件であること、(c) Coordinator以外（3型への直接bypass）からの
mutationメソッド直接呼び出しが0件であること、(d) retry/orchestrator側
（src/retry_lineage・src/retry_engine・src/retry_composition配下）から
MediaUploadSafetyCoordinatorの4 durable state mutationメソッド
（record_not_applicable/record_prepared/record_attempted/record_confirmed）が
一切呼ばれないこと（read-only使用のstatic evidence）、のいずれも直接証明する。

production側は変更しない。test-onlyでApproved Architectureの主張を検証する。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_13_media_upload_store_composition_root_closure.py
"""
from __future__ import annotations

import ast
import sys
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
print("Invariant #15 — MEDIA_UPLOAD store型のCoordinator閉包性（repository全体AST監査、28.-27）")
print("=" * 60)
print()

TARGET_CLASS_NAMES = {
    "ArticleMediaUploadStateManager",
    "JsonMediaUploadApplicabilityStore",
    "JsonMediaUploadAttemptContextStore",
}
BUILDER_FUNCTION_NAME = "build_media_upload_safety_coordinator"
# Coordinator自身の定義ファイル（内部でself._media_upload_manager等を保持・使用する
# 唯一の正当な場所、22.1・22.3.2節）。
COORDINATOR_FILE = "src/side_effect_safety/media_upload_safety_coordinator.py"
# 承認されたCoordinator構築箇所（exact、wildcard/package-wide exclusion禁止、
# HUMAN GATE APPROVED — OPTION A WITH NARROW INVARIANT #15 CLARIFICATION）。
# main.py：既存のsubprocess側write-ahead用途（mutation含む）。
# src/retry_composition/retry_composition_root.py：Phase 2 production remediation
# で追加された、親/orchestratorプロセス側のterminalization/reconciliation用途
# （read-only、SideEffectSafetyClassifier経由のcoordinator.get()専用）。
APPROVED_CONSTRUCTION_FILES = {
    "main.py",
    "src/retry_composition/retry_composition_root.py",
}
# retry/orchestrator側（read-only使用が要求される範囲）。
RETRY_SIDE_DIR_PREFIXES = (
    "src/retry_lineage/",
    "src/retry_engine/",
    "src/retry_composition/",
)
# MediaUploadSafetyCoordinatorの4 durable state mutationメソッド（22.1・9.9節）。
COORDINATOR_MUTATION_METHOD_NAMES = {
    "record_not_applicable",
    "record_prepared",
    "record_attempted",
    "record_confirmed",
}


def _iter_target_files():
    for p in sorted(PROJECT_ROOT.glob("*.py")):
        yield p
    for p in sorted(SRC_DIR.rglob("*.py")):
        if "__pycache__" not in p.parts:
            yield p
    for p in sorted(SCRIPTS_DIR.rglob("*.py")):
        if "__pycache__" not in p.parts:
            yield p


_file_cache: dict[Path, tuple[str, "ast.Module | None"]] = {}


def _get_source_and_tree(p: Path):
    if p not in _file_cache:
        try:
            source = p.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(p))
        except (SyntaxError, UnicodeDecodeError):
            source, tree = "", None
        _file_cache[p] = (source, tree)
    return _file_cache[p]


# =====================================================================
# テスト1（repository-wide static enumeration）：
#   (a) コンストラクタ呼び出し箇所の全列挙
#   (b) 構築済みインスタンスがCoordinator以外へ渡される箇所の確認
# =====================================================================

print("[テスト1] 3型のコンストラクタ呼び出しをrepository全体から列挙し、"
      "main.py::build_media_upload_safety_coordinator()呼び出し内以外に存在しないことを確認")

construction_sites: list[tuple[str, int, str, bool]] = []  # (relpath, lineno, class_name, is_nested_in_builder_call)


def _enclosing_call_is_builder(tree, target_node) -> bool:
    """target_node（コンストラクタ呼び出しのast.Call）が、
    build_media_upload_safety_coordinator(...)呼び出しの引数として（直接または
    キーワード引数として、多重ネストの有無を問わず）現れているかを確認する。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == BUILDER_FUNCTION_NAME:
            for child in ast.walk(node):
                if child is target_node:
                    return True
    return False


for py_file in _iter_target_files():
    source, tree = _get_source_and_tree(py_file)
    if tree is None:
        continue
    rel = py_file.relative_to(PROJECT_ROOT).as_posix()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in TARGET_CLASS_NAMES:
            nested_in_builder = _enclosing_call_is_builder(tree, node)
            construction_sites.append((rel, node.lineno, node.func.id, nested_in_builder))

print(f"    検出したコンストラクタ呼び出し箇所: {len(construction_sites)}件")
for rel, lineno, class_name, nested in construction_sites:
    print(f"      {rel}:{lineno} {class_name}() nested_in_builder_call={nested}")

check(
    "1a. 検出されたコンストラクタ呼び出し箇所はちょうど6件"
    "（3型×承認された2構築箇所＝main.py・retry_composition_root.py）",
    len(construction_sites), 6,
)
check(
    "1a. 検出された型名の集合が3型ちょうど一致する",
    {c[2] for c in construction_sites}, TARGET_CLASS_NAMES,
)

_outside_approved_files = [c for c in construction_sites if c[0] not in APPROVED_CONSTRUCTION_FILES]
check(
    "1a. 承認された2箇所（exact、wildcard/package-wide exclusionなし）以外での"
    "コンストラクタ呼び出し = 0",
    _outside_approved_files, [],
)
_construction_files_seen = sorted({c[0] for c in construction_sites})
check(
    "1a'. 実際に構築を行っているファイルの集合が、承認された2箇所と完全一致する"
    "（片方だけに偏っていないことの確認）",
    _construction_files_seen, sorted(APPROVED_CONSTRUCTION_FILES),
)

_not_nested_in_builder = [c for c in construction_sites if not c[3]]
check(
    "1b. 全コンストラクタ呼び出しがbuild_media_upload_safety_coordinator()呼び出しの引数として"
    "（Composition Root自身）現れる——Coordinator以外へ渡される経路 = 0",
    _not_nested_in_builder, [],
)
print()


# =====================================================================
# テスト2：Coordinator以外からの3型mutationメソッド直接呼び出し
#          （Coordinator bypass）の検出
# =====================================================================

print("[テスト2] Coordinator以外の箇所から3型へのメソッド直接呼び出し（bypass）を検出")


def _track_simple_local_assignments(tree) -> dict:
    """`var = ClassName(...)` という単純な代入（分岐・再代入を区別しない
    over-approximation）から、ローカル変数名 → 構築されたクラス名 のマップを
    ファイル全体で構築する。テスト1で全コンストラクタ呼び出しがinline nested
    argumentであり変数へは一切代入されないことが既に判明しているが、防御的に
    このパターンも独立して監査する。"""
    var_to_class: dict[str, str] = {}
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and len(node.targets) == 1
            and isinstance(node.targets[0], ast.Name)
            and isinstance(node.value, ast.Call)
            and isinstance(node.value.func, ast.Name)
            and node.value.func.id in TARGET_CLASS_NAMES
        ):
            var_to_class[node.targets[0].id] = node.value.func.id
    return var_to_class


bypass_call_sites: list[tuple[str, int, str]] = []

for py_file in _iter_target_files():
    source, tree = _get_source_and_tree(py_file)
    if tree is None:
        continue
    rel = py_file.relative_to(PROJECT_ROOT).as_posix()
    if rel == COORDINATOR_FILE:
        continue  # Coordinator自身の内部実装は対象外（22.1・22.3.2節の正当な使用箇所）

    var_to_class = _track_simple_local_assignments(tree)

    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        receiver = node.func.value
        matched_class = None
        # パターン(i): ClassName(...).method(...) の直接チェーン呼び出し。
        if isinstance(receiver, ast.Call) and isinstance(receiver.func, ast.Name) and receiver.func.id in TARGET_CLASS_NAMES:
            matched_class = receiver.func.id
        # パターン(ii): var = ClassName(...) で束縛済みのローカル変数経由の呼び出し。
        elif isinstance(receiver, ast.Name) and receiver.id in var_to_class:
            matched_class = var_to_class[receiver.id]
        if matched_class is not None:
            bypass_call_sites.append((rel, node.lineno, f"{matched_class}.{node.func.attr}()"))

print(f"    検出したbypass候補: {len(bypass_call_sites)}件")
for rel, lineno, call_desc in bypass_call_sites:
    print(f"      {rel}:{lineno} {call_desc}")

check(
    "2. Coordinator以外からの3型mutationメソッド直接呼び出し（bypass）= 0"
    "（テスト専用のCoordinator bypass注入は28.1#4・#6が別途扱う対象であり、"
    "本テストのscope外——本監査はproduction wiring全体を対象とする）",
    bypass_call_sites, [],
)
print()


# =====================================================================
# テスト3（裏付け）：MediaUploadApplicabilityStoreへの直接呼び出し=0であることの
#          個別確認（Gate OFF時のrecord_not_applicable()経路の見落とし防止）
# =====================================================================

print("[テスト3] MediaUploadApplicabilityStore（Gate OFF経路が使うstore）への"
      "bypass呼び出しが0件であることを個別に強調確認")

applicability_bypass_sites = [s for s in bypass_call_sites if s[2].startswith("JsonMediaUploadApplicabilityStore.")]
check(
    "3. JsonMediaUploadApplicabilityStoreへの直接bypass呼び出し = 0"
    "（Gate OFF時record_not_applicable()経路のCoordinator bypass見落とし防止）",
    applicability_bypass_sites, [],
)
print()


# =====================================================================
# テスト4（HUMAN GATE APPROVED — OPTION A WITH NARROW INVARIANT #15
# CLARIFICATION、厳守条件2）：retry/orchestrator側（src/retry_lineage・
# src/retry_engine・src/retry_composition配下）から、MediaUploadSafetyCoordinator
# の4 durable state mutationメソッドが一切呼ばれないこと（read-only使用の
# static/direct evidence）を確認する。
# =====================================================================

print("[テスト4] retry/orchestrator側からのMediaUploadSafetyCoordinator "
      "mutationメソッド呼び出し = 0（read-only使用のstatic evidence）")

retry_side_mutation_calls: list[tuple[str, int, str]] = []

for py_file in _iter_target_files():
    rel = py_file.relative_to(PROJECT_ROOT).as_posix()
    if not rel.startswith(RETRY_SIDE_DIR_PREFIXES):
        continue
    source, tree = _get_source_and_tree(py_file)
    if tree is None:
        continue
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in COORDINATOR_MUTATION_METHOD_NAMES
        ):
            retry_side_mutation_calls.append((rel, node.lineno, node.func.attr))

print(f"    検出したretry側mutation呼び出し候補: {len(retry_side_mutation_calls)}件")
for rel, lineno, method_name in retry_side_mutation_calls:
    print(f"      {rel}:{lineno} .{method_name}()")

check(
    "4. src/retry_lineage・src/retry_engine・src/retry_composition配下から"
    "record_not_applicable/record_prepared/record_attempted/record_confirmed"
    "のいずれも呼ばれない（retry-side instance is classification/read-only usage）",
    retry_side_mutation_calls, [],
)
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
