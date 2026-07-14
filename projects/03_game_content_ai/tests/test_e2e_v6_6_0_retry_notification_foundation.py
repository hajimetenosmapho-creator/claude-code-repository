"""
E2E テスト: v6.6.0 Retry Notification Foundation

テストシナリオ（docs/design/retry_notification_foundation.md 対応）:
    ── RetryNotificationStatus ──
    1.  NO_NOTIFICATION / NOTIFY の2値を持つ

    ── RetryNotificationDecision（Immutable、statusのみ） ──
    2.  フィールド再代入でFrozenInstanceErrorを送出する
    3.  保持するフィールドはstatusのみ（RetryAlert/RetryAlertLevelの複製・
        message/channel/timestamp等を持たない）
    4.  同じstatus同士はequal、異なるstatus同士はnot equal

    ── RetryNotificationEvaluator（変換規則・Design Contract、11章） ──
    5.  NONE -> NO_NOTIFICATION
    6.  WARNING -> NOTIFY
    7.  CRITICAL -> NOTIFY
    8.  戻り値の型はRetryNotificationDecision

    ── RetryNotificationEvaluator（未対応Levelの扱い・Fail Fast契約、12章） ──
    9.  未対応値ではRetryNotificationDecisionを返さず、ValueErrorを送出する
        （ValueError送出・正常な戻り値の非返却・エラーメッセージへのEvaluator名／
        実際値の包含を1シナリオで統合検証する。NO_NOTIFICATION／NOTIFYの
        いずれへもフォールバックしないことは、「正常な戻り値が返らない」ことの
        確認によって保証される）

    ── RetryNotificationEvaluator（Stateless Pure Function） ──
    10. 同一Alertを複数回渡しても常に同一Decisionを返す（決定的）
    11. 異なるEvaluatorインスタンスでも同一Alertに対し同一結果を返す
    12. 入力RetryAlertオブジェクトを変更しない
    13. Evaluatorは__init__を持たず、呼び出し間で状態を保持しない

    ── Public API（__init__.pyのexport契約） ──
    14. package rootの__all__は、RetryNotificationStatus／RetryNotificationDecision／
        RetryNotificationEvaluatorの3型のみをexportする（余分なexportがない）

    ── Dependency Rule（依存方向の構造的検証、AST解析ベース） ──
    15. retry_notificationの絶対importは標準ライブラリとretry_alert以外の
        自作パッケージをimportしない
    16. retry_notificationはretry_monitoring/retry_metrics/Runtime系/RetryManager/
        Logger/scripts/外部ライブラリをimportしない
    17. retry_notification配下の相対importは同一パッケージ内（level==1）のみで、
        親パッケージ方向（level>=2、例：`from ..retry_monitoring import X`）の
        相対importが存在しない
    18. retry_alert（__init__.py含む全productionモジュール）はretry_notification
        をimportしない（逆依存禁止）

    ── 外部I/Oの不在（構造的検証） ──
    19. retry_notification配下のいずれのファイルも組み込みopen()を呼び出さない

    ── 統合テスト（Alert → Notification end-to-end） ──
    20. RetryAlertEvaluator → RetryNotificationEvaluatorが一貫して動作する

既存コンポーネントの無改修確認について:
    本ファイルは恒久的なE2Eテストであるため、コミット時点の差分に依存する`git diff`ベース
    の無改修確認は含めない。既存コンポーネントの無改修確認はRelease Reviewにおいて
    `git diff --name-status` / `git status --short`で個別に行う（v6.5.0の運用を踏襲）。

Architecture Test方針について（docs/design/retry_notification_foundation.md 16章）:
    依存方向・外部I/O不在の主たる保証手段はimport解析（AST）とする。文字列検索は用いない
    （コメント・docstring内の誤検出、動的importの検知不能という限界があるため）。
    相対import（`from . import x`等）は、level（親ディレクトリを遡る段数）を区別して
    扱う。level==1（retry_notificationパッケージ内部での相対import）のみを許容し、
    level>=2（親パッケージ方向、例：`from ..retry_monitoring import X`）は、絶対import
    による禁止依存チェックと同様に構造的に検出・禁止する（ChatGPT Code Review指摘反映）。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_6_0_retry_notification_foundation.py
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
print("v6.6.0 Retry Notification Foundation E2E テスト")
print("=" * 60)
print()

import retry_notification
from retry_alert import RetryAlert, RetryAlertEvaluator, RetryAlertLevel
from retry_monitoring import RetryHealthReport, RetryHealthStatus
from retry_notification import (
    RetryNotificationDecision,
    RetryNotificationEvaluator,
    RetryNotificationStatus,
)

RETRY_NOTIFICATION_DIR = PROJECT_ROOT / "src" / "retry_notification"
RETRY_ALERT_DIR = PROJECT_ROOT / "src" / "retry_alert"

notification_files = {
    "__init__": RETRY_NOTIFICATION_DIR / "__init__.py",
    "retry_notification_status": RETRY_NOTIFICATION_DIR / "retry_notification_status.py",
    "retry_notification_decision": RETRY_NOTIFICATION_DIR / "retry_notification_decision.py",
    "retry_notification_evaluator": RETRY_NOTIFICATION_DIR / "retry_notification_evaluator.py",
}

alert_files = {
    "retry_alert_level": RETRY_ALERT_DIR / "retry_alert_level.py",
    "retry_alert": RETRY_ALERT_DIR / "retry_alert.py",
    "retry_alert_evaluator": RETRY_ALERT_DIR / "retry_alert_evaluator.py",
    "__init__": RETRY_ALERT_DIR / "__init__.py",
}


# ═══════════════════════════════════════════════════════════
# テスト1: RetryNotificationStatus
# ═══════════════════════════════════════════════════════════

print("[テスト1] RetryNotificationStatusはNO_NOTIFICATION/NOTIFYの2値を持つ")
check("1. メンバー数は2", len(list(RetryNotificationStatus)), 2)
check("1. NO_NOTIFICATIONが存在する", RetryNotificationStatus.NO_NOTIFICATION.value, "NO_NOTIFICATION")
check("1. NOTIFYが存在する", RetryNotificationStatus.NOTIFY.value, "NOTIFY")
print()


# ═══════════════════════════════════════════════════════════
# テスト2-4: RetryNotificationDecision
# ═══════════════════════════════════════════════════════════

print("[テスト2] RetryNotificationDecisionはフィールド再代入でFrozenInstanceErrorを送出する")
decision_2 = RetryNotificationDecision(status=RetryNotificationStatus.NO_NOTIFICATION)
raised_2 = None
try:
    decision_2.status = RetryNotificationStatus.NOTIFY
except FrozenInstanceError as e:
    raised_2 = e
check_true("2. FrozenInstanceErrorが送出される", raised_2 is not None)
print()

print("[テスト3] RetryNotificationDecisionが保持するフィールドはstatusのみ")
field_names_3 = tuple(f.name for f in dataclasses.fields(RetryNotificationDecision))
check("3. フィールドは(status,)のみ", field_names_3, ("status",))
check_true("3. alertフィールドを持たない", "alert" not in field_names_3)
check_true("3. levelフィールドを持たない（RetryAlertLevelの複製なし）", "level" not in field_names_3)
check_true("3. messageフィールドを持たない", "message" not in field_names_3)
check_true("3. channelフィールドを持たない", "channel" not in field_names_3)
check_true("3. timestampフィールドを持たない", "timestamp" not in field_names_3)
print()

print("[テスト4] 同じstatus同士はequal、異なるstatus同士はnot equal")
decision_4a = RetryNotificationDecision(status=RetryNotificationStatus.NOTIFY)
decision_4b = RetryNotificationDecision(status=RetryNotificationStatus.NOTIFY)
decision_4c = RetryNotificationDecision(status=RetryNotificationStatus.NO_NOTIFICATION)
check_true("4. 同じstatus同士はequal", decision_4a == decision_4b)
check_true("4. 異なるstatus同士はnot equal", decision_4a != decision_4c)
print()


# ═══════════════════════════════════════════════════════════
# テスト5-8: RetryNotificationEvaluator 変換規則（Design Contract）
# ═══════════════════════════════════════════════════════════

evaluator = RetryNotificationEvaluator()

print("[テスト5] NONE -> NO_NOTIFICATION")
check(
    "5. NO_NOTIFICATIONを返す",
    evaluator.evaluate(RetryAlert(level=RetryAlertLevel.NONE)).status,
    RetryNotificationStatus.NO_NOTIFICATION,
)
print()

print("[テスト6] WARNING -> NOTIFY")
check(
    "6. NOTIFYを返す",
    evaluator.evaluate(RetryAlert(level=RetryAlertLevel.WARNING)).status,
    RetryNotificationStatus.NOTIFY,
)
print()

print("[テスト7] CRITICAL -> NOTIFY")
check(
    "7. NOTIFYを返す",
    evaluator.evaluate(RetryAlert(level=RetryAlertLevel.CRITICAL)).status,
    RetryNotificationStatus.NOTIFY,
)
print()

print("[テスト8] 戻り値の型はRetryNotificationDecision")
result_8 = evaluator.evaluate(RetryAlert(level=RetryAlertLevel.WARNING))
check_true("8. RetryNotificationDecisionのインスタンスである", isinstance(result_8, RetryNotificationDecision))
print()


# ═══════════════════════════════════════════════════════════
# テスト9: RetryNotificationEvaluator 未対応Levelの扱い（Fail Fast契約、統合検証）
# ═══════════════════════════════════════════════════════════

print("[テスト9] 未対応値ではRetryNotificationDecisionを返さず、ValueErrorを送出する（Fail Fast契約の統合検証）")
# RetryAlertLevelは現時点でNONE/WARNING/CRITICALの3値のみだが、将来値が追加された
# 場合の未対応Levelを模擬するため、意図的に既知の3値のいずれでもない文字列を
# levelとして持つRetryAlertを組み立てる（dataclassは型を実行時強制しないため、
# これが可能）。
unknown_alert_9 = RetryAlert(level="UNKNOWN_FUTURE_LEVEL")
raised_9 = None
result_9 = None
try:
    result_9 = evaluator.evaluate(unknown_alert_9)
except ValueError as e:
    raised_9 = e
check_true("9. ValueErrorが送出される", raised_9 is not None)
check_true(
    "9. 正常なRetryNotificationDecisionは返らない"
    "（NO_NOTIFICATION/NOTIFYいずれへもフォールバックしないことの保証）",
    result_9 is None,
)
check_true("9. エラーメッセージにRetryNotificationEvaluatorが含まれる", "RetryNotificationEvaluator" in str(raised_9))
check_true("9. エラーメッセージに実際の値が含まれる", "UNKNOWN_FUTURE_LEVEL" in str(raised_9))
print()


# ═══════════════════════════════════════════════════════════
# テスト10-13: Stateless Pure Function
# ═══════════════════════════════════════════════════════════

print("[テスト10] 同一Alertを複数回渡しても常に同一Decisionを返す（決定的）")
alert_10 = RetryAlert(level=RetryAlertLevel.CRITICAL)
results_10 = [evaluator.evaluate(alert_10).status for _ in range(5)]
check_true("10. 5回とも同じstatusを返す", all(status == results_10[0] for status in results_10))
check("10. 返す値はNOTIFY", results_10[0], RetryNotificationStatus.NOTIFY)
print()

print("[テスト11] 異なるEvaluatorインスタンスでも同一Alertに対し同一結果を返す")
evaluator_a = RetryNotificationEvaluator()
evaluator_b = RetryNotificationEvaluator()
alert_11 = RetryAlert(level=RetryAlertLevel.NONE)
check(
    "11. インスタンスが異なっても結果は同一",
    evaluator_a.evaluate(alert_11).status,
    evaluator_b.evaluate(alert_11).status,
)
print()

print("[テスト12] 入力RetryAlertオブジェクトを変更しない")
alert_12 = RetryAlert(level=RetryAlertLevel.WARNING)
evaluator.evaluate(alert_12)
check("12. evaluate()呼び出し後もlevelは不変", alert_12.level, RetryAlertLevel.WARNING)
print()

print("[テスト13] Evaluatorは__init__を持たず、呼び出し間で状態を保持しない")
check_true(
    "13. RetryNotificationEvaluatorは__init__を定義しない",
    not has_init_method(notification_files["retry_notification_evaluator"], "RetryNotificationEvaluator"),
)
stateless_evaluator_13 = RetryNotificationEvaluator()
stateless_evaluator_13.evaluate(RetryAlert(level=RetryAlertLevel.CRITICAL))
check("13. evaluate()呼び出し後もインスタンス属性は空", stateless_evaluator_13.__dict__, {})
print()


# ═══════════════════════════════════════════════════════════
# テスト14: Public API（__init__.pyのexport契約）
# ═══════════════════════════════════════════════════════════

print("[テスト14] package rootの__all__はDesign Freezeされた3型のみをexportする")
expected_public_api_14 = {"RetryNotificationStatus", "RetryNotificationDecision", "RetryNotificationEvaluator"}
check("14. __all__の件数は3", len(retry_notification.__all__), 3)
check_true(
    "14. __all__の集合はDesign Freezeされた3型と一致する（余分なexportがないことの確認を兼ねる）",
    set(retry_notification.__all__) == expected_public_api_14,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト15-18: Dependency Rule（AST解析ベース）
# ═══════════════════════════════════════════════════════════

ALLOWED_MODULES = {"__future__", "enum", "dataclasses", "retry_alert"}
FORBIDDEN_MODULES = (
    "retry_monitoring", "retry_metrics", "retry_runtime_lock", "retry_runtime_shutdown",
    "retry_runtime_loop", "retry_runtime_orchestrator", "retry_runtime_logging",
    "retry_engine", "retry_composition", "retry_queue", "retry_history",
    "retry_enqueue_trigger", "workflow_monitor", "workflow_engine", "scheduler",
    "execution_history", "logging", "requests", "smtplib", "urllib", "http", "socket",
)

notification_import_details = {
    module_name: get_import_details(file_path)
    for module_name, file_path in notification_files.items()
}

print("[テスト15] retry_notificationの絶対importは標準ライブラリとretry_alert以外の自作パッケージをimportしない")
for module_name, details in notification_import_details.items():
    check_true(
        f"15. {module_name}の絶対importはALLOWED_MODULESの部分集合",
        details["absolute_roots"].issubset(ALLOWED_MODULES),
    )
print()

print("[テスト16] retry_notificationはretry_monitoring/retry_metrics/Runtime系/RetryManager/Logger/scripts/外部ライブラリをimportしない")
for module_name, details in notification_import_details.items():
    for forbidden in FORBIDDEN_MODULES:
        check_true(f"16. {module_name}が{forbidden}をimportしない", forbidden not in details["absolute_roots"])
print()

print("[テスト17] retry_notification配下の相対importは同一パッケージ内（level==1）のみで、親パッケージ方向（level>=2）の相対importが存在しない")
for module_name, details in notification_import_details.items():
    relative_levels = [imp["level"] for imp in details["relative_imports"]]
    check_true(
        f"17. {module_name}の相対importにlevel>=2（親パッケージ方向）が存在しない",
        all(level == 1 for level in relative_levels),
    )
print()

print("[テスト18] retry_alert（__init__.py含む全productionモジュール）はretry_notificationをimportしない（逆依存禁止）")
for module_name, file_path in alert_files.items():
    imported = get_imported_root_modules(file_path)
    check_true(f"18. {module_name}がretry_notificationをimportしない", "retry_notification" not in imported)
print()


# ═══════════════════════════════════════════════════════════
# テスト19: 外部I/Oの不在（構造的検証）
# ═══════════════════════════════════════════════════════════

print("[テスト19] retry_notification配下のいずれのファイルも組み込みopen()を呼び出さない")
for module_name, file_path in notification_files.items():
    open_calls = get_open_call_lines(file_path)
    check_true(f"19. {module_name}がopen()を呼び出さない", len(open_calls) == 0)
print()


# ═══════════════════════════════════════════════════════════
# テスト20: 統合テスト（Alert → Notification end-to-end）
# ═══════════════════════════════════════════════════════════

print("[テスト20] RetryAlertEvaluator → RetryNotificationEvaluatorが一貫して動作する")
report_20 = RetryHealthReport(status=RetryHealthStatus.UNHEALTHY)
alert_20 = RetryAlertEvaluator().evaluate(report_20)
check("20. RetryAlertはCRITICALと判定される", alert_20.level, RetryAlertLevel.CRITICAL)

decision_20 = RetryNotificationEvaluator().evaluate(alert_20)
check("20. RetryNotificationDecisionはNOTIFYと判定される", decision_20.status, RetryNotificationStatus.NOTIFY)

report_20b = RetryHealthReport(status=RetryHealthStatus.HEALTHY)
alert_20b = RetryAlertEvaluator().evaluate(report_20b)
decision_20b = RetryNotificationEvaluator().evaluate(alert_20b)
check("20. HEALTHY経由の場合はNO_NOTIFICATIONと判定される", decision_20b.status, RetryNotificationStatus.NO_NOTIFICATION)
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
