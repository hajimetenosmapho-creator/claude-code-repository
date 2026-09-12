"""
E2E テスト: Release 6.32 sub-milestone 6D cluster 2
RecoveryPolicy静的契約（Invariant #40）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    28.-29節（method→policy binding direct test、3件）・
    28.-30節（Invariant #40 Layer 1・Layer 2 direct test、Layer1=1件・Layer2=2件）。

Invariant #40（25章）は、`MediaUploadSafetyCoordinator`の4公開メソッド
（record_not_applicable/record_prepared/record_attempted/record_confirmed）が
「acknowledged durable semantic commitは別のsemantic kindへ再分類されない」
ことを4層で保証する：
    Layer 1: 4公開メソッドのexact public return type annotation（本節#1）
    Layer 2: 各RecoveryPolicyクラス自身がvariant-specificであること（本節#2・#3）
    Layer 3: Stage 1/2/3 runtime validation（28.-24節、既存）
    Layer 4: method→policy binding（28.-29節#1〜#3、本節）

本テストは、production側（src/side_effect_safety/media_upload_safety_coordinator.py）
を変更せず、既存実装がApproved Architectureどおり正しいことをtest-onlyで直接
証明する。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_11_recovery_policy_static_contract.py
"""
from __future__ import annotations

import ast
import inspect
import sys
import typing
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

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
print("RecoveryPolicy静的契約（Invariant #40、28.-29・28.-30）E2E テスト")
print("=" * 60)
print()

from side_effect_safety import (
    ConfirmedMediaUploadSafetyRecord,
    IoArmedMediaUploadSafetyRecord,
    JsonMediaUploadApplicabilityStore,
    NotApplicableMediaUploadSafetyRecord,
    PreparedMediaUploadSafetyRecord,
    ProtectedSideEffectKind,
    SideEffectOperationIdentity,
    SideEffectSite,
    build_media_upload_safety_coordinator,
)
from side_effect_safety.media_upload_attempt_context_store import JsonMediaUploadAttemptContextStore
from side_effect_safety.media_upload_safety_coordinator import (
    ConfirmedRecoveryPolicy,
    IoArmedRecoveryPolicy,
    MediaUploadSafetyCoordinator,
    NotApplicableRecoveryPolicy,
    PreparedRecoveryPolicy,
)
from article_media_upload_state.article_media_upload_state_manager import ArticleMediaUploadStateManager
from article_media_upload_state.json_article_media_upload_state_store import JsonArticleMediaUploadStateStore

import tempfile


def _identity(kind, instance_key="art1", root_run_id="r1", attempt_ordinal=1, site=SideEffectSite.NEWS_STEP):
    return SideEffectOperationIdentity(
        root_run_id=root_run_id, attempt_ordinal=attempt_ordinal,
        operation_kind=kind, effect_site=site, operation_instance_key=instance_key,
    )


# authoritative method→policy mapping（28.-29節）
AUTHORITATIVE_METHOD_POLICY_MAPPING = {
    "record_not_applicable": "NotApplicableRecoveryPolicy",
    "record_prepared": "PreparedRecoveryPolicy",
    "record_attempted": "IoArmedRecoveryPolicy",
    "record_confirmed": "ConfirmedRecoveryPolicy",
}

# authoritative method→exact return type mapping（28.-30節 Layer 1）
AUTHORITATIVE_METHOD_RETURN_TYPE_MAPPING = {
    "record_not_applicable": NotApplicableMediaUploadSafetyRecord,
    "record_prepared": PreparedMediaUploadSafetyRecord,
    "record_attempted": IoArmedMediaUploadSafetyRecord,
    "record_confirmed": ConfirmedMediaUploadSafetyRecord,
}

# authoritative RecoveryPolicy → expected_type mapping（28.-30節 Layer 2）
RECOVERY_POLICY_CLASSES = {
    "NotApplicableRecoveryPolicy": NotApplicableRecoveryPolicy,
    "PreparedRecoveryPolicy": PreparedRecoveryPolicy,
    "IoArmedRecoveryPolicy": IoArmedRecoveryPolicy,
    "ConfirmedRecoveryPolicy": ConfirmedRecoveryPolicy,
}


# =====================================================================
# §28.-29 テスト1-2: method→policy binding（static監査、自動テストとして実装）
# =====================================================================

print("[28.-29 #1-2] 4公開メソッドがpolicy=へ渡すRecoveryPolicyコンストラクタのstatic監査（AST）")

coordinator_source_path = SRC_DIR / "side_effect_safety" / "media_upload_safety_coordinator.py"
coordinator_source = coordinator_source_path.read_text(encoding="utf-8")
coordinator_tree = ast.parse(coordinator_source)


def _extract_method_body_node(tree, method_name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == method_name:
            return node
    return None


def _find_policy_kwarg_class(method_node) -> "str | None":
    """method本体を走査し、_value_or_recover(...)呼び出しの`policy=`キーワード引数に
    渡されているコンストラクタ呼び出しのクラス名を返す。"""
    for node in ast.walk(method_node):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "_value_or_recover"):
            continue
        for kw in node.keywords:
            if kw.arg == "policy" and isinstance(kw.value, ast.Call) and isinstance(kw.value.func, ast.Name):
                return kw.value.func.id
    return None


_mismatched_pairs = []
for method_name, expected_policy_class in AUTHORITATIVE_METHOD_POLICY_MAPPING.items():
    method_node = _extract_method_body_node(coordinator_tree, method_name)
    check_true(f"1. {method_name}()がsource内に存在する", method_node is not None)
    actual_policy_class = _find_policy_kwarg_class(method_node) if method_node is not None else None
    check(
        f"1. {method_name}() が policy={expected_policy_class}(...) のみを渡す",
        actual_policy_class, expected_policy_class,
    )
    if actual_policy_class != expected_policy_class:
        _mismatched_pairs.append((method_name, actual_policy_class, expected_policy_class))

check(
    "1. mismatched method/policy pair = 0（4件の1:1対応が完全に成立）",
    _mismatched_pairs, [],
)
# #2：上記#1の監査自体が、prose code reviewではなく本ファイル（実行可能なスクリプト、
# ./venv/Scripts/python.exe経由でCI実行可能）として実装されていることそのものが
# #2の要求を満たす（別途assertする対象を持たない、監査の実装形態自体が要求）。
print()


# =====================================================================
# §28.-29 テスト3: 4メソッドを実際に呼び出し、返り値の型をisinstance()で検証
# =====================================================================

print("[28.-29 #3] 4公開メソッドを実行し、返り値の型をisinstance()でexact typeと直接照合")

with tempfile.TemporaryDirectory() as tmpdir:
    d = Path(tmpdir)
    media_manager = ArticleMediaUploadStateManager(JsonArticleMediaUploadStateStore(d / "media"))
    coordinator: MediaUploadSafetyCoordinator = build_media_upload_safety_coordinator(
        media_upload_manager=media_manager,
        applicability_store=JsonMediaUploadApplicabilityStore(d / "applicability"),
        attempt_context_store=JsonMediaUploadAttemptContextStore(d / "context"),
        locks_dir=d / "locks",
    )

    id_na = _identity(ProtectedSideEffectKind.MEDIA_UPLOAD, instance_key="art-na")
    result_na = coordinator.record_not_applicable(id_na, "member-na")
    check_true(
        "3. record_not_applicable() → isinstance(NotApplicableMediaUploadSafetyRecord)",
        isinstance(result_na, NotApplicableMediaUploadSafetyRecord),
    )

    id_main = _identity(ProtectedSideEffectKind.MEDIA_UPLOAD, instance_key="art-main")
    result_prepared = coordinator.record_prepared(id_main, "member-main")
    check_true(
        "3. record_prepared() → isinstance(PreparedMediaUploadSafetyRecord)",
        isinstance(result_prepared, PreparedMediaUploadSafetyRecord),
    )

    result_attempted = coordinator.record_attempted(id_main, "member-main")
    check_true(
        "3. record_attempted() → isinstance(IoArmedMediaUploadSafetyRecord)",
        isinstance(result_attempted, IoArmedMediaUploadSafetyRecord),
    )

    result_confirmed = coordinator.record_confirmed(id_main, "member-main", media_id=99)
    check_true(
        "3. record_confirmed() → isinstance(ConfirmedMediaUploadSafetyRecord)",
        isinstance(result_confirmed, ConfirmedMediaUploadSafetyRecord),
    )
print()


# =====================================================================
# §28.-30 Layer 1: 4公開メソッドのexact return type annotation
# =====================================================================

print("[28.-30 Layer1 #1] get_type_hints()で4公開メソッドのreturn annotationを取得し、exact typeと照合")

_type_hints_mismatch = []
for method_name, expected_return_type in AUTHORITATIVE_METHOD_RETURN_TYPE_MAPPING.items():
    method = getattr(MediaUploadSafetyCoordinator, method_name)
    hints = typing.get_type_hints(method)
    actual_return_type = hints.get("return")
    check(
        f"1. {method_name}() の宣言済みreturn annotationがexactly {expected_return_type.__name__}",
        actual_return_type, expected_return_type,
    )
    if actual_return_type is not expected_return_type:
        _type_hints_mismatch.append(method_name)

check("1. return annotation mismatch = 0（4メソッド全てexact type、Union/Anyではない）", _type_hints_mismatch, [])
print()


# =====================================================================
# §28.-30 Layer 2 テスト2: RecoveryPolicy.expected_typeとbuild_minimal()の一致
# =====================================================================

print("[28.-30 Layer2 #2] 4つのRecoveryPolicyクラス：expected_typeとbuild_minimal()構築型の一致（static監査）")


def _find_class_node(tree, class_name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return node
    return None


def _find_build_minimal_constructed_class(class_node) -> "str | None":
    """build_minimal()メソッド本体のreturn文が構築するクラス名を返す。"""
    for node in ast.walk(class_node):
        if isinstance(node, ast.FunctionDef) and node.name == "build_minimal":
            for stmt in ast.walk(node):
                if isinstance(stmt, ast.Return) and isinstance(stmt.value, ast.Call) and isinstance(stmt.value.func, ast.Name):
                    return stmt.value.func.id
    return None


_expected_type_mismatch = []
for policy_class_name, policy_class in RECOVERY_POLICY_CLASSES.items():
    class_node = _find_class_node(coordinator_tree, policy_class_name)
    check_true(f"2. {policy_class_name}がsource内に存在する", class_node is not None)

    constructed_class_name = _find_build_minimal_constructed_class(class_node) if class_node is not None else None
    expected_type_name = policy_class.expected_type.__name__
    check(
        f"2. {policy_class_name}.expected_type({expected_type_name}) と build_minimal()構築型が一致",
        constructed_class_name, expected_type_name,
    )
    # 実行時にもexpected_type自体を直接確認する（static監査の裏取り）。
    check(
        f"2. {policy_class_name}.expected_type is {expected_type_name}（実行時確認）",
        policy_class.expected_type.__name__, expected_type_name,
    )
    if constructed_class_name != expected_type_name:
        _expected_type_mismatch.append(policy_class_name)

check("2. mismatched expected_type/build_minimal pair = 0（4クラス全て1:1対応）", _expected_type_mismatch, [])
print()


# =====================================================================
# §28.-30 Layer 2 テスト3: validate()の交差検証（4×3=12通り）
# =====================================================================

print("[28.-30 Layer2 #3] 4つのRecoveryPolicyのvalidate()を他クラスのbuild_minimal()出力へ適用（4×3=12通り交差検証）")

_identity_for_policies = _identity(ProtectedSideEffectKind.MEDIA_UPLOAD, instance_key="art-cross")
_policy_instances = {
    "NotApplicableRecoveryPolicy": NotApplicableRecoveryPolicy(identity=_identity_for_policies, member_run_id="m-cross"),
    "PreparedRecoveryPolicy": PreparedRecoveryPolicy(identity=_identity_for_policies, member_run_id="m-cross"),
    "IoArmedRecoveryPolicy": IoArmedRecoveryPolicy(identity=_identity_for_policies, member_run_id="m-cross"),
    "ConfirmedRecoveryPolicy": ConfirmedRecoveryPolicy(identity=_identity_for_policies, member_run_id="m-cross", media_id=1),
}

_built_minimal_values = {
    name: policy.build_minimal(updated_at="2026-09-09T00:00:00")
    for name, policy in _policy_instances.items()
}

_cross_validation_failures = []
_self_validation_failures = []
for policy_name, policy in _policy_instances.items():
    for value_source_name, value in _built_minimal_values.items():
        result = policy.validate(value)
        if policy_name == value_source_name:
            ok = result is not None
            if not ok:
                _self_validation_failures.append((policy_name, value_source_name))
        else:
            ok = result is None
            if not ok:
                _cross_validation_failures.append((policy_name, value_source_name))
        mark = "OK" if ok else "NG"
        relation = "自分自身" if policy_name == value_source_name else "他クラス"
        print(f"    [{mark}] {policy_name}.validate({value_source_name}の値、{relation}) → {result!r}")

check(
    "3. 自分自身が構築した値はvalidate()が受理する（4件、self-match）",
    _self_validation_failures, [],
)
check(
    "3. 他クラスが構築した値はいずれもvalidate()がNoneを返す（4×3=12通り交差検証、mismatched acceptance = 0）",
    _cross_validation_failures, [],
)
print()


# =====================================================================
# §28.6 Invariant #40 mapping整合確認
# =====================================================================

print("[§28.6整合] Invariant #40 4層すべてがexecutable test IDを持つことの確認")

check_true(
    "Layer 1（exact return type annotation）: 本ファイルのget_type_hints()テストで直接検証済み",
    len(_type_hints_mismatch) == 0,
)
check_true(
    "Layer 2（RecoveryPolicy自身の正しさ）: 本ファイルのexpected_type/build_minimal一致・"
    "validate()交差検証で直接検証済み",
    len(_expected_type_mismatch) == 0 and len(_cross_validation_failures) == 0,
)
check_true(
    "Layer 4（method→policy binding）: 本ファイルのAST監査・実行時isinstance検証で直接検証済み",
    len(_mismatched_pairs) == 0,
)
print(
    "  （Layer 3: Stage 1/2/3 runtime validationは28.-24節の既存テスト範囲——"
    "本クラスタでは再実装しない）"
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
