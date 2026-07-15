"""
E2E テスト: v6.7.0 Retry Notification Message Foundation

テストシナリオ（docs/design/retry_notification_message_foundation.md 対応）:
    ── RetryNotificationMessage（Immutable、bodyのみ） ──
    1.  フィールド再代入でFrozenInstanceErrorを送出する
    2.  保持するフィールドはbodyのみ（RetryAlert/RetryAlertLevel/
        RetryNotificationDecision/RetryNotificationStatus/title/channel/
        timestamp/reasonのいずれも保持しない）
    3.  渡したbodyの値をそのまま保持する
    4.  同じbody同士はequal、異なるbody同士はnot equal

    ── RetryNotificationMessageBuilder（固定対応表、Design Contract、11章） ──
    5.  NOTIFY -> 固定文言のRetryNotificationMessageを返す（本文完全一致・非空）
    6.  戻り値の型はRetryNotificationMessage
    7.  build()呼び出し後も入力RetryNotificationDecisionは不変

    ── RetryNotificationMessageBuilder（Stateless Pure Function） ──
    8.  同一Decisionを複数回渡しても常に同一bodyを返す（決定的）
    9.  異なるBuilderインスタンスでも同一Decisionに対し同一結果を返す
    10. Builderは__init__を持たず、呼び出し間で状態を保持しない

    ── RetryNotificationMessageBuilder（NO_NOTIFICATIONの扱い・Fail Fast契約、12章） ──
    11. NO_NOTIFICATIONではRetryNotificationMessageを返さず、ValueErrorを送出する
        （「評価失敗」ではなく「Message生成契約への違反」であることをエラー
        メッセージへのBuilder名の包含で確認する）

    ── RetryNotificationMessageBuilder（未対応Statusの扱い・Fail Fast契約、17章） ──
    12. 未対応値ではRetryNotificationMessageを返さず、ValueErrorを送出する
        （NO_NOTIFICATIONとは別シナリオとして扱う。同じ例外確認を「NOTIFYへ
        フォールバックしない」等として重複計上しない）

    ── Public API（__init__.pyのexport契約） ──
    13. package rootの__all__は、RetryNotificationMessage／
        RetryNotificationMessageBuilderの2型のみをexportする（余分なexportがない）

    ── Dependency Rule（依存方向の構造的検証、AST解析ベース） ──
    14. retry_notification_messageの絶対importは標準ライブラリとretry_notification
        以外の自作パッケージをimportしない
    15. retry_notification_messageはretry_alert/retry_monitoring/retry_metrics/
        Runtime系/RetryManager/Logger/scripts/外部ライブラリをimportしない
    16. retry_notification_message配下の相対importは同一パッケージ内（level==1）
        のみで、親パッケージ方向（level>=2）の相対importが存在しない
    17. retry_notification（__init__.py含む全productionモジュール）は
        retry_notification_messageをimportしない（逆依存禁止）

    ── 外部I/Oの不在（構造的検証） ──
    18. retry_notification_message配下のいずれのファイルも組み込みopen()を
        呼び出さない

    ── Pipeline統合テスト（手動Composition、Builderを呼ぶ判断は呼び出し元の責務） ──
    19. DEGRADED経路：HEALTHY判定→WARNING→NOTIFY→共通Messageが生成される
    20. UNHEALTHY経路：→CRITICAL→NOTIFY→DEGRADED経路と同一の共通Messageに
        収束する（WARNING/CRITICALを区別しないことの確認）
    21. HEALTHY経路：→NONE→NO_NOTIFICATION→Compositionの分岐によりBuilderを
        呼び出さない（「Builderが何も返さない」のではなく「呼び出し元が呼ばない」
        という責務であることを区別する）

既存コンポーネントの無改修確認について:
    本ファイルは恒久的なE2Eテストであるため、コミット時点の差分に依存する`git diff`ベース
    の無改修確認は含めない。既存コンポーネントの無改修確認はRelease Reviewにおいて
    `git diff --name-status` / `git status --short`で個別に行う（v6.5.0/v6.6.0の運用を踏襲）。

Architecture Test方針について（docs/design/retry_notification_message_foundation.md 21章）:
    依存方向・外部I/O不在の主たる保証手段はimport解析（AST）とする。文字列検索は用いない
    （コメント・docstring内の誤検出、動的importの検知不能という限界があるため）。
    相対import（`from . import x`等）は、level（親ディレクトリを遡る段数）を区別して
    扱う。level==1（retry_notification_messageパッケージ内部での相対import）のみを
    許容し、level>=2（親パッケージ方向）は、絶対importによる禁止依存チェックと同様に
    構造的に検出・禁止する（v6.6.0のChatGPT Code Review指摘を継承）。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_7_0_retry_notification_message_foundation.py
"""
import ast
import dataclasses
import sys
from dataclasses import FrozenInstanceError
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ─── テスト用ユーティリティ ───

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


# ─── AST解析ユーティリティ（Dependency Rule / 外部I/O検証用） ───


def get_imported_root_modules(file_path: Path) -> set:
    """
    file_pathをASTでパースし、importされているトップレベルのモジュール名集合を返す。

    相対import（`from . import x` / `from .x import y`、level > 0）はパッケージ
    内部の依存として除外する。トップレベルの `import x` および `from x import y`
    （level == 0）のみを対象とする。
    """
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                continue
            if node.module:
                modules.add(node.module.split(".")[0])
    return modules


def get_import_details(file_path: Path) -> dict:
    """
    file_pathをASTでパースし、import情報を構造化して返す。

    - absolute_roots: 絶対import（level == 0）のトップレベルモジュール名集合
    - relative_imports: 相対import（level >= 1）のlevelとmodule名を保持する
      リスト。`from . import x`のようにmodule名を伴わない相対importは
      module=Noneとして記録する

    get_imported_root_modules()と異なり、相対importをlevel別に保持するため、
    「同一パッケージ内（level==1）は許容し、親パッケージ方向（level>=2）は
    禁止する」という契約を検証できる。
    """
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


def get_open_call_lines(file_path: Path) -> list:
    """file_pathをASTでパースし、組み込みopen()呼び出しの行番号一覧を返す。"""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            lines.append(node.lineno)
    return lines


def has_init_method(file_path: Path, class_name: str) -> bool:
    """file_path内のclass_nameクラスが__init__メソッドを定義しているかを返す。"""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.FunctionDef) and item.name == "__init__":
                    return True
    return False


print("=" * 60)
print("v6.7.0 Retry Notification Message Foundation E2E テスト")
print("=" * 60)
print()

import retry_notification_message
from retry_alert import RetryAlertEvaluator
from retry_monitoring import RetryHealthReport, RetryHealthStatus
from retry_notification import RetryNotificationDecision, RetryNotificationEvaluator, RetryNotificationStatus
from retry_notification_message import RetryNotificationMessage, RetryNotificationMessageBuilder

RETRY_NOTIFICATION_MESSAGE_DIR = PROJECT_ROOT / "src" / "retry_notification_message"
RETRY_NOTIFICATION_DIR = PROJECT_ROOT / "src" / "retry_notification"

# Design Freeze（docs/design/retry_notification_message_foundation.md 11章）で確定した固定文言
EXPECTED_NOTIFY_BODY = "Retry Runtimeで通知対象の状態が検出されました。詳細を確認してください。"

message_files = {
    "__init__": RETRY_NOTIFICATION_MESSAGE_DIR / "__init__.py",
    "retry_notification_message": RETRY_NOTIFICATION_MESSAGE_DIR / "retry_notification_message.py",
    "retry_notification_message_builder": RETRY_NOTIFICATION_MESSAGE_DIR / "retry_notification_message_builder.py",
}

notification_files = {
    "__init__": RETRY_NOTIFICATION_DIR / "__init__.py",
    "retry_notification_status": RETRY_NOTIFICATION_DIR / "retry_notification_status.py",
    "retry_notification_decision": RETRY_NOTIFICATION_DIR / "retry_notification_decision.py",
    "retry_notification_evaluator": RETRY_NOTIFICATION_DIR / "retry_notification_evaluator.py",
}


# ═══════════════════════════════════════════════════════════
# テスト1-4: RetryNotificationMessage（Immutable、bodyのみ）
# ═══════════════════════════════════════════════════════════

print("[テスト1] RetryNotificationMessageはフィールド再代入でFrozenInstanceErrorを送出する")
message_1 = RetryNotificationMessage(body="dummy")
raised_1 = None
try:
    message_1.body = "changed"
except FrozenInstanceError as e:
    raised_1 = e
check_true("1. FrozenInstanceErrorが送出される", raised_1 is not None)
print()

print("[テスト2] RetryNotificationMessageが保持するフィールドはbodyのみ")
field_names_2 = tuple(f.name for f in dataclasses.fields(RetryNotificationMessage))
check("2. フィールドは(body,)のみ", field_names_2, ("body",))
check_true(
    "2. levelフィールドを持たない（RetryAlertLevelを複製しないというArchitecture Review指摘反映）",
    "level" not in field_names_2,
)
check_true("2. statusフィールドを持たない（RetryNotificationStatusを複製しない）", "status" not in field_names_2)
print()

print("[テスト3] 渡したbodyの値をそのまま保持する")
message_3 = RetryNotificationMessage(body="任意の本文")
check("3. bodyは渡した値と一致する", message_3.body, "任意の本文")
print()

print("[テスト4] 同じbody同士はequal、異なるbody同士はnot equal")
message_4a = RetryNotificationMessage(body="同じ本文")
message_4b = RetryNotificationMessage(body="同じ本文")
message_4c = RetryNotificationMessage(body="異なる本文")
check_true("4. 同じbody同士はequal", message_4a == message_4b)
check_true("4. 異なるbody同士はnot equal", message_4a != message_4c)
print()


# ═══════════════════════════════════════════════════════════
# テスト5-7: RetryNotificationMessageBuilder 固定対応表（Design Contract）
# ═══════════════════════════════════════════════════════════

builder = RetryNotificationMessageBuilder()

print("[テスト5] NOTIFY -> 固定文言のRetryNotificationMessageを返す")
decision_5 = RetryNotificationDecision(status=RetryNotificationStatus.NOTIFY)
result_5 = builder.build(decision_5)
check("5. bodyは固定文言と完全一致する", result_5.body, EXPECTED_NOTIFY_BODY)
check_true("5. bodyは空文字ではない", len(result_5.body) > 0)
print()

print("[テスト6] 戻り値の型はRetryNotificationMessage")
check_true("6. RetryNotificationMessageのインスタンスである", isinstance(result_5, RetryNotificationMessage))
print()

print("[テスト7] build()呼び出し後も入力RetryNotificationDecisionは不変")
decision_7 = RetryNotificationDecision(status=RetryNotificationStatus.NOTIFY)
builder.build(decision_7)
check("7. build()呼び出し後もstatusは不変", decision_7.status, RetryNotificationStatus.NOTIFY)
print()


# ═══════════════════════════════════════════════════════════
# テスト8-10: RetryNotificationMessageBuilder Stateless Pure Function
# ═══════════════════════════════════════════════════════════

print("[テスト8] 同一Decisionを複数回渡しても常に同一bodyを返す（決定的）")
decision_8 = RetryNotificationDecision(status=RetryNotificationStatus.NOTIFY)
results_8 = [builder.build(decision_8).body for _ in range(5)]
check_true("8. 5回とも同じbodyを返す", all(body == results_8[0] for body in results_8))
print()

print("[テスト9] 異なるBuilderインスタンスでも同一Decisionに対し同一結果を返す")
builder_a = RetryNotificationMessageBuilder()
builder_b = RetryNotificationMessageBuilder()
decision_9 = RetryNotificationDecision(status=RetryNotificationStatus.NOTIFY)
check(
    "9. インスタンスが異なっても結果は同一",
    builder_a.build(decision_9).body,
    builder_b.build(decision_9).body,
)
print()

print("[テスト10] Builderは__init__を持たず、呼び出し間で状態を保持しない")
check_true(
    "10. RetryNotificationMessageBuilderは__init__を定義しない",
    not has_init_method(message_files["retry_notification_message_builder"], "RetryNotificationMessageBuilder"),
)
stateless_builder_10 = RetryNotificationMessageBuilder()
stateless_builder_10.build(RetryNotificationDecision(status=RetryNotificationStatus.NOTIFY))
check("10. build()呼び出し後もインスタンス属性は空", stateless_builder_10.__dict__, {})
print()


# ═══════════════════════════════════════════════════════════
# テスト11: NO_NOTIFICATIONの扱い（Fail Fast契約、Message生成契約への違反）
# ═══════════════════════════════════════════════════════════

print("[テスト11] NO_NOTIFICATIONではRetryNotificationMessageを返さず、ValueErrorを送出する")
decision_11 = RetryNotificationDecision(status=RetryNotificationStatus.NO_NOTIFICATION)
raised_11 = None
result_11 = None
try:
    result_11 = builder.build(decision_11)
except ValueError as e:
    raised_11 = e
check_true("11. ValueErrorが送出される", raised_11 is not None)
check_true("11. 正常なRetryNotificationMessageは返らない", result_11 is None)
check_true(
    "11. エラーメッセージにRetryNotificationMessageBuilderが含まれる（評価失敗ではなく契約違反であることの識別）",
    "RetryNotificationMessageBuilder" in str(raised_11),
)
print()


# ═══════════════════════════════════════════════════════════
# テスト12: 未対応Statusの扱い（Fail Fast契約、NO_NOTIFICATIONとは別シナリオ）
# ═══════════════════════════════════════════════════════════

print("[テスト12] 未対応値ではRetryNotificationMessageを返さず、ValueErrorを送出する（Fail Fast契約の統合検証）")
# RetryNotificationStatusは現時点でNO_NOTIFICATION/NOTIFYの2値のみだが、将来値が
# 追加された場合の未対応Statusを模擬するため、意図的に既知の2値のいずれでもない
# 文字列をstatusとして持つRetryNotificationDecisionを組み立てる（dataclassは型を
# 実行時強制しないため、これが可能）。
unknown_decision_12 = RetryNotificationDecision(status="UNKNOWN_FUTURE_STATUS")
raised_12 = None
result_12 = None
try:
    result_12 = builder.build(unknown_decision_12)
except ValueError as e:
    raised_12 = e
check_true("12. ValueErrorが送出される", raised_12 is not None)
check_true("12. 正常なRetryNotificationMessageは返らない", result_12 is None)
check_true("12. エラーメッセージに実際の値が含まれる", "UNKNOWN_FUTURE_STATUS" in str(raised_12))
print()


# ═══════════════════════════════════════════════════════════
# テスト13: Public API（__init__.pyのexport契約）
# ═══════════════════════════════════════════════════════════

print("[テスト13] package rootの__all__はDesign Freezeされた2型のみをexportする")
expected_public_api_13 = {"RetryNotificationMessage", "RetryNotificationMessageBuilder"}
check("13. __all__の件数は2", len(retry_notification_message.__all__), 2)
check_true(
    "13. __all__の集合はDesign Freezeされた2型と一致する（余分なexportがないことの確認を兼ねる）",
    set(retry_notification_message.__all__) == expected_public_api_13,
)
# __all__の集合検査だけでは、package rootの名前空間そのものに想定外の属性が
# 存在しないこと（`from x import *`を経由しないアクセスも含む）までは保証できない。
# 固定Message文字列・RetryNotificationDecision・RetryNotificationStatusが
# package rootから直接アクセス可能になっていないことを、hasattr()で個別に確認する。
check_true(
    "13. RetryNotificationDecisionはpackage rootから直接アクセスできない（再exportしていない）",
    not hasattr(retry_notification_message, "RetryNotificationDecision"),
)
check_true(
    "13. RetryNotificationStatusはpackage rootから直接アクセスできない（再exportしていない）",
    not hasattr(retry_notification_message, "RetryNotificationStatus"),
)
check_true(
    "13. 固定Message文字列（_NOTIFY_MESSAGE_BODY相当）はpackage rootから直接アクセスできない",
    not hasattr(retry_notification_message, "_NOTIFY_MESSAGE_BODY"),
)
print()


# ═══════════════════════════════════════════════════════════
# テスト14-17: Dependency Rule（AST解析ベース）
# ═══════════════════════════════════════════════════════════

ALLOWED_MODULES = {"__future__", "dataclasses", "retry_notification"}
FORBIDDEN_MODULES = (
    "retry_alert", "retry_monitoring", "retry_metrics", "retry_runtime_lock", "retry_runtime_shutdown",
    "retry_runtime_loop", "retry_runtime_orchestrator", "retry_runtime_logging",
    "retry_engine", "retry_composition", "retry_queue", "retry_history",
    "retry_enqueue_trigger", "workflow_monitor", "workflow_engine", "scheduler",
    "execution_history", "logging", "requests", "smtplib", "urllib", "http", "socket",
)

message_import_details = {
    module_name: get_import_details(file_path)
    for module_name, file_path in message_files.items()
}

print("[テスト14] retry_notification_messageの絶対importは標準ライブラリとretry_notification以外の自作パッケージをimportしない")
for module_name, details in message_import_details.items():
    check_true(
        f"14. {module_name}の絶対importはALLOWED_MODULESの部分集合",
        details["absolute_roots"].issubset(ALLOWED_MODULES),
    )
print()

print("[テスト15] retry_notification_messageはretry_alert/retry_monitoring/retry_metrics/Runtime系/RetryManager/Logger/scripts/外部ライブラリをimportしない")
for module_name, details in message_import_details.items():
    for forbidden in FORBIDDEN_MODULES:
        check_true(f"15. {module_name}が{forbidden}をimportしない", forbidden not in details["absolute_roots"])
print()

print("[テスト16] retry_notification_message配下の相対importは同一パッケージ内（level==1）のみで、親パッケージ方向（level>=2）の相対importが存在しない")
for module_name, details in message_import_details.items():
    relative_levels = [imp["level"] for imp in details["relative_imports"]]
    check_true(
        f"16. {module_name}の相対importにlevel>=2（親パッケージ方向）が存在しない",
        all(level == 1 for level in relative_levels),
    )
print()

print("[テスト17] retry_notification（__init__.py含む全productionモジュール）はretry_notification_messageをimportしない（逆依存禁止）")
for module_name, file_path in notification_files.items():
    imported = get_imported_root_modules(file_path)
    check_true(f"17. {module_name}がretry_notification_messageをimportしない", "retry_notification_message" not in imported)
print()


# ═══════════════════════════════════════════════════════════
# テスト18: 外部I/Oの不在（構造的検証）
# ═══════════════════════════════════════════════════════════

print("[テスト18] retry_notification_message配下のいずれのファイルも組み込みopen()を呼び出さない")
for module_name, file_path in message_files.items():
    open_calls = get_open_call_lines(file_path)
    check_true(f"18. {module_name}がopen()を呼び出さない", len(open_calls) == 0)
print()


# ═══════════════════════════════════════════════════════════
# テスト19-21: Pipeline統合テスト（手動Composition）
# ═══════════════════════════════════════════════════════════


def run_pipeline(health_status: RetryHealthStatus):
    """
    Metrics以降を模擬した手動Compositionヘルパー（既存4パッケージ+Builderは無改修）。

    RetryNotificationDecision.status == NOTIFYの場合のみBuilder.build()を呼び出す。
    NO_NOTIFICATIONの場合はBuilderを呼び出さない（呼び出すかどうかは呼び出し元の
    Compositionの責務であり、Builder自身がNoneを返す・空Messageを返す等で表現
    するものではない）。

    戻り値: (decision, message_or_none, builder_was_called)
    """
    report = RetryHealthReport(status=health_status)
    alert = RetryAlertEvaluator().evaluate(report)
    decision = RetryNotificationEvaluator().evaluate(alert)
    if decision.status is RetryNotificationStatus.NOTIFY:
        message = RetryNotificationMessageBuilder().build(decision)
        return decision, message, True
    return decision, None, False


print("[テスト19] DEGRADED経路：HEALTHY判定→WARNING→NOTIFY→共通Messageが生成される")
decision_19, message_19, called_19 = run_pipeline(RetryHealthStatus.DEGRADED)
check("19. RetryNotificationDecisionはNOTIFYと判定される", decision_19.status, RetryNotificationStatus.NOTIFY)
check_true("19. Builderが呼び出される", called_19)
check("19. 固定文言のMessageが生成される", message_19.body, EXPECTED_NOTIFY_BODY)
print()

print("[テスト20] UNHEALTHY経路：→CRITICAL→NOTIFY→DEGRADED経路と同一の共通Messageに収束する")
decision_20, message_20, called_20 = run_pipeline(RetryHealthStatus.UNHEALTHY)
check("20. RetryNotificationDecisionはNOTIFYと判定される", decision_20.status, RetryNotificationStatus.NOTIFY)
check_true("20. Builderが呼び出される", called_20)
check(
    "20. WARNING経路（テスト19）とCRITICAL経路（本テスト）は同一のMessageへ収束する",
    message_20.body,
    message_19.body,
)
print()

print("[テスト21] HEALTHY経路：→NONE→NO_NOTIFICATION→Compositionの分岐によりBuilderを呼び出さない")
decision_21, message_21, called_21 = run_pipeline(RetryHealthStatus.HEALTHY)
check("21. RetryNotificationDecisionはNO_NOTIFICATIONと判定される", decision_21.status, RetryNotificationStatus.NO_NOTIFICATION)
check_true("21. Builderが呼び出されない（Compositionの分岐の結果であり、Builder自身のNone返却ではない）", not called_21)
check("21. Messageは生成されない（未呼び出しの結果）", message_21, None)
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
