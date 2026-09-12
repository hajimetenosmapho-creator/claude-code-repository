"""
E2E テスト: sub-milestone 6C — Invariant #37 Authoritative Completion Boundary
Identity Consistency（§28.-37節、7件）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    2.2a節（2段階責務分離）・25章 Invariant #37・28.-37節。

2.2a節が定める2段階の責務分離のうち、(1) `RetryExecutor`のconsistency
validation boundaryと(2) `WorkflowEngineExecutor`のmember completion
boundaryを直接検証する。28.-36節（downstream propagation boundary、
full-chain）とは異なる境界を対象とする。

sub-milestone 6C実装ノート：
    `RetryExecutor.execute()`は既存コードでは`RetryLineageProtectedProvenance`を
    `lineage`/`claim`自身の値から直接構築するのみで、構築後の明示的な
    consistency validationステップを持っていなかった（2.2a節(1)が要求する
    構造的防御が未実装だったcompletion gap）。本sub-milestoneで
    `_validate_provenance_consistency()`を新設し、`execute()`内の
    `self._engine.run()`呼び出し（external I/O）より前に検証するよう配線した。
    `lineage.side_effect_contract_version is None`（pre-6.32 legacy lineage、
    18章）の場合は検証をスキップし、既存6.31以前のlegacy behaviorを維持する
    （既存test回帰で確認済み）。

実行方法:
    cd projects/03_game_content_ai
    .\\venv\\Scripts\\python.exe tests\\test_e2e_v6_32_8_invariant_37_boundary_tests.py
"""
import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

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
print("Invariant #37 Authoritative Completion Boundary（§28.-37）E2E テスト")
print("=" * 60)
print()

from retry_engine.retry_executor import _validate_provenance_consistency  # noqa: E402
from workflow_engine.workflow_engine_executor import _complete_side_effect_execution_context  # noqa: E402
from side_effect_safety import (  # noqa: E402
    RetryLineageProtectedExecutionContext,
    RetryLineageProtectedProvenance,
    SideEffectExecutionModeContractError,
)
from side_effect_safety.side_effect_execution_mode import ExecutionModeFailureReasonCode  # noqa: E402


class _FakeLineage:
    def __init__(self, root_run_id, side_effect_contract_version):
        self.root_run_id = root_run_id
        self.side_effect_contract_version = side_effect_contract_version


class _FakeClaim:
    def __init__(self, attempt_no):
        self.attempt_no = attempt_no


_LINEAGE = _FakeLineage(root_run_id="root-37a", side_effect_contract_version=1)
_CLAIM = _FakeClaim(attempt_no=3)


# ─── [テスト1] valid — RetryExecutor validation PASS ───

print("[テスト1] 一致する値ではvalidationがPASSする")

_valid_provenance = RetryLineageProtectedProvenance(
    root_run_id="root-37a", attempt_ordinal=3, side_effect_contract_version=1,
)
raised_1 = None
try:
    _validate_provenance_consistency(_valid_provenance, _LINEAGE, _CLAIM)
except Exception as e:
    raised_1 = e
check_true("1a. 一致する値では例外が送出されない", raised_1 is None)
print()


# ─── [テスト2] root mismatch ───

print("[テスト2] root_run_id不一致はMISSING_LINEAGE_CONTEXTでfail-closedする")

_root_mismatch = RetryLineageProtectedProvenance(
    root_run_id="root-DIFFERENT", attempt_ordinal=3, side_effect_contract_version=1,
)
raised_2 = None
try:
    _validate_provenance_consistency(_root_mismatch, _LINEAGE, _CLAIM)
except SideEffectExecutionModeContractError as e:
    raised_2 = e
check_true("2a. SideEffectExecutionModeContractErrorが送出される", raised_2 is not None)
check(
    "2b. reason_codeはMISSING_LINEAGE_CONTEXT",
    raised_2.reason_code if raised_2 else None,
    ExecutionModeFailureReasonCode.MISSING_LINEAGE_CONTEXT,
)
print()


# ─── [テスト3] attempt mismatch ───

print("[テスト3] attempt_ordinal不一致はCONTEXT_MISMATCHでfail-closedする")

_attempt_mismatch = RetryLineageProtectedProvenance(
    root_run_id="root-37a", attempt_ordinal=99, side_effect_contract_version=1,
)
raised_3 = None
try:
    _validate_provenance_consistency(_attempt_mismatch, _LINEAGE, _CLAIM)
except SideEffectExecutionModeContractError as e:
    raised_3 = e
check_true("3a. SideEffectExecutionModeContractErrorが送出される", raised_3 is not None)
check(
    "3b. reason_codeはCONTEXT_MISMATCH",
    raised_3.reason_code if raised_3 else None,
    ExecutionModeFailureReasonCode.CONTEXT_MISMATCH,
)
print()


# ─── [テスト4] contract version mismatch ───

print("[テスト4] side_effect_contract_version不一致はCONTRACT_VERSION_MISMATCHでfail-closedする")

_version_mismatch = RetryLineageProtectedProvenance(
    root_run_id="root-37a", attempt_ordinal=3, side_effect_contract_version=2,
)
raised_4 = None
try:
    _validate_provenance_consistency(_version_mismatch, _LINEAGE, _CLAIM)
except SideEffectExecutionModeContractError as e:
    raised_4 = e
check_true("4a. SideEffectExecutionModeContractErrorが送出される", raised_4 is not None)
check(
    "4b. reason_codeはCONTRACT_VERSION_MISMATCH",
    raised_4.reason_code if raised_4 else None,
    ExecutionModeFailureReasonCode.CONTRACT_VERSION_MISMATCH,
)
print()


# ─── [テスト5] malformed field、consistency照合到達前のfail-closed ───

print("[テスト5] malformed fieldはwell-formedness検証が先に発火し、consistency照合には到達しない")

# root_run_idが空文字列（malformed）。仮にlineageの値と「一致」していたとしても
# （空文字列同士）、well-formedness検証が先に発火することを確認する。
_malformed_lineage = _FakeLineage(root_run_id="", side_effect_contract_version=1)
_malformed_provenance = RetryLineageProtectedProvenance(
    root_run_id="", attempt_ordinal=3, side_effect_contract_version=1,
)
raised_5 = None
try:
    _validate_provenance_consistency(_malformed_provenance, _malformed_lineage, _CLAIM)
except SideEffectExecutionModeContractError as e:
    raised_5 = e
check_true("5a. SideEffectExecutionModeContractErrorが送出される（malformed値のconsistency一致では救済されない）", raised_5 is not None)
check(
    "5b. reason_codeはMISSING_LINEAGE_CONTEXT（well-formedness検証由来）",
    raised_5.reason_code if raised_5 else None,
    ExecutionModeFailureReasonCode.MISSING_LINEAGE_CONTEXT,
)

# attempt_ordinal=0（malformed、well-formedは1以上を要求）。lineage/claim側も
# 同じ0であれば一致はするが、well-formedness検証が先に発火するはず。
_malformed_claim_0 = _FakeClaim(attempt_no=0)
_malformed_provenance_2 = RetryLineageProtectedProvenance(
    root_run_id="root-37a", attempt_ordinal=0, side_effect_contract_version=1,
)
raised_5b = None
try:
    _validate_provenance_consistency(_malformed_provenance_2, _LINEAGE, _malformed_claim_0)
except SideEffectExecutionModeContractError as e:
    raised_5b = e
check_true("5c. attempt_ordinal=0（malformed）も一致有無に関わらずfail-closedする", raised_5b is not None)
check(
    "5d. reason_codeはCONTEXT_MISMATCH（well-formedness検証由来）",
    raised_5b.reason_code if raised_5b else None,
    ExecutionModeFailureReasonCode.CONTEXT_MISMATCH,
)
print()


# ─── [テスト5続き] legacy lineage（contract_version is None）は検証自体をスキップする ───

print("[テスト5続き] pre-6.32 legacy lineage（contract_version=None）は6.32検証の対象外")

_legacy_lineage = _FakeLineage(root_run_id="root-legacy", side_effect_contract_version=None)
_legacy_provenance = RetryLineageProtectedProvenance(
    root_run_id="root-DIFFERENT-still-ok", attempt_ordinal=-1, side_effect_contract_version=None,
)
raised_5e = None
try:
    _validate_provenance_consistency(_legacy_provenance, _legacy_lineage, _CLAIM)
except Exception as e:
    raised_5e = e
check_true(
    "5e. legacy lineage（contract_version=None）ではmalformed/mismatchな値があっても検証自体がスキップされる",
    raised_5e is None,
)
print()


# ─── [テスト6] member completion — pass-through整合性 ───

print("[テスト6] WorkflowEngineExecutorはvalidated pre-contextの3値を無変更で引き継ぐ")

_pre_context = RetryLineageProtectedProvenance(
    root_run_id="root-37a", attempt_ordinal=3, side_effect_contract_version=1,
)
_completed = _complete_side_effect_execution_context(_pre_context, "member-run-xyz")

check_true("6a. 完成形はRetryLineageProtectedExecutionContext", isinstance(_completed, RetryLineageProtectedExecutionContext))
check("6b. root_run_idが無変更", _completed.root_run_id, "root-37a")
check("6c. attempt_ordinalが無変更", _completed.attempt_ordinal, 3)
check("6d. side_effect_contract_versionが無変更", _completed.side_effect_contract_version, 1)
check("6e. member_run_idはWorkflowEngineExecutor自身のrun_idと一致する", _completed.member_run_id, "member-run-xyz")
print()


# ─── [テスト7] member_run_id caller override禁止（static監査） ───

print("[テスト7] protected factory呼び出しがcaller供給値をmember_run_idとして受け付けない（static監査）")

_source = (PROJECT_ROOT / "src" / "workflow_engine" / "workflow_engine_executor.py").read_text(encoding="utf-8")
_tree = ast.parse(_source)


def _find_function(tree, name):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    return None


_func = _find_function(_tree, "_complete_side_effect_execution_context")
check_true("7a. _complete_side_effect_execution_context()が存在する", _func is not None)

if _func is not None:
    _param_names = [a.arg for a in _func.args.args]
    check(
        "7b. 関数の引数はprovenance・run_idの2つのみ（caller供給のmember_run_id相当の引数を持たない）",
        _param_names,
        ["provenance", "run_id"],
    )

    _build_calls = [
        n for n in ast.walk(_func)
        if isinstance(n, ast.Call)
        and (
            (isinstance(n.func, ast.Name) and n.func.id == "build_protected_execution_context")
            or (isinstance(n.func, ast.Attribute) and n.func.attr == "build_protected_execution_context")
        )
    ]
    check("7c. build_protected_execution_context()呼び出しが1件存在する", len(_build_calls), 1)
    if _build_calls:
        _member_run_id_kw = next((kw for kw in _build_calls[0].keywords if kw.arg == "member_run_id"), None)
        check_true("7d. member_run_id引数が渡されている", _member_run_id_kw is not None)
        if _member_run_id_kw is not None:
            check_true(
                "7e. member_run_id引数の値は関数自身のrun_idパラメータそのもの（Name('run_id')）",
                isinstance(_member_run_id_kw.value, ast.Name) and _member_run_id_kw.value.id == "run_id",
            )
print()


# ─── 結果サマリー ───

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
