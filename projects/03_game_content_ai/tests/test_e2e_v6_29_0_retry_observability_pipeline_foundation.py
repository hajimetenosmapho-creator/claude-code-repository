"""
E2E テスト: v6.29.0 Retry Observability Pipeline Foundation

テストシナリオ（docs/design/retry_observability_pipeline_foundation.md 対応）:
    ── RetryObservabilityReport（Immutable、5フィールド、status/message invariant） ──
    1.  フィールド再代入でFrozenInstanceErrorを送出する
    2.  保持するフィールドはmetrics/health_report/alert/notification_decision/
        messageの5つのみ
    3.  NOTIFY + message非Noneの組み合わせは正常に構築できる
    4.  NO_NOTIFICATION + message=Noneの組み合わせは正常に構築できる
    5.  NOTIFY + message=Noneの組み合わせは構築時にValueErrorを送出する
    6.  NO_NOTIFICATION + message非Noneの組み合わせは構築時にValueErrorを送出する
    7.  未対応のstatus相当値は構築時にValueErrorを送出する

    ── RetryObservabilityPipeline（固定順序Composition） ──
    8.  空records → cycle_count=0 → HEALTHY → NONE → NO_NOTIFICATION → message=None
    9.  HEALTHY経路（高いenqueue成功率）→ NO_NOTIFICATION → message=None
    10. DEGRADED経路 → WARNING → NOTIFY → 固定文言のMessageが生成される
    11. UNHEALTHY経路 → CRITICAL → NOTIFY → DEGRADED経路と同一のMessageへ収束する
    12. thresholds未指定時はDefault Thresholdが透過的に使用される
    13. カスタムthresholdsが透過的に注入される
    14. 未対応のRetryNotificationStatus相当値ではevaluate()がValueErrorを送出する
        （Fail Fast契約、monkeypatchで模擬）

    ── Public API（__init__.pyのexport契約） ──
    15. package rootの__all__は、RetryObservabilityReport／RetryObservabilityPipeline
        の2型のみをexportする

    ── Dependency Rule（依存方向の構造的検証、AST解析ベース） ──
    16. retry_observability_pipelineの絶対importはALLOWED_MODULESの部分集合
    17. retry_observability_pipelineはRuntime系/RetryCompositionRoot/Scheduler/
        CLI/Logger/外部ライブラリをimportしない
    18. retry_observability_pipelineはretry_metricsからRetryRuntimeLogReaderを
        importしない（I/O境界の構造的禁止）
    19. retry_observability_pipeline配下の相対importは同一パッケージ内（level==1）
        のみ
    20. 既存5パッケージ（retry_metrics/retry_monitoring/retry_alert/
        retry_notification/retry_notification_message）のいずれも
        retry_observability_pipelineをimportしない（逆依存禁止）

    ── 外部I/Oの不在（構造的検証） ──
    21. retry_observability_pipeline配下のいずれのファイルも組み込みopen()を
        呼び出さない

    ── CLI/Pipeline Parity Test ──
    22. empty records: CLI（build_report、RetryRuntimeLogReader.readをmock）と
        Pipelineが意味的に同一の結果を返す
    23. HEALTHY records: 同上
    24. DEGRADED records: 同上
    25. UNHEALTHY records: 同上

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_29_0_retry_observability_pipeline_foundation.py
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from dataclasses import FrozenInstanceError, fields
from pathlib import Path
from unittest import mock

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


def get_import_details(file_path: Path) -> dict:
    """
    file_pathをASTでパースし、import情報を構造化して返す。

    - absolute_roots: 絶対import（level == 0）のトップレベルモジュール名集合
    - from_names_by_module: モジュール名 -> importされた名前集合（symbol-level検証用）
    - relative_imports: 相対import（level >= 1）のlevelとmodule名のリスト
    """
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    absolute_roots = set()
    from_names_by_module: dict = {}
    relative_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                absolute_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                relative_imports.append({"level": node.level, "module": node.module})
            elif node.module:
                root = node.module.split(".")[0]
                absolute_roots.add(root)
                from_names_by_module.setdefault(root, set()).update(
                    alias.name for alias in node.names
                )
    return {
        "absolute_roots": absolute_roots,
        "from_names_by_module": from_names_by_module,
        "relative_imports": relative_imports,
    }


def get_imported_root_modules(file_path: Path) -> set:
    """file_pathをASTでパースし、importされているトップレベルのモジュール名集合を返す（相対importは除外）。"""
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


def get_open_call_lines(file_path: Path) -> list:
    """file_pathをASTでパースし、組み込みopen()呼び出しの行番号一覧を返す。"""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    lines = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
            lines.append(node.lineno)
    return lines


print("=" * 60)
print("v6.29.0 Retry Observability Pipeline Foundation E2E テスト")
print("=" * 60)
print()

import retry_observability_pipeline
from retry_alert import RetryAlert, RetryAlertLevel
from retry_metrics import RetryMetricsSnapshot, RetryRuntimeLogRecord
from retry_monitoring import RetryHealthReport, RetryHealthStatus, RetryHealthThresholds
from retry_notification import RetryNotificationDecision, RetryNotificationEvaluator, RetryNotificationStatus
from retry_notification_message import RetryNotificationMessage
from retry_observability_pipeline import RetryObservabilityPipeline, RetryObservabilityReport

import retry_alert as retry_alert_pkg
import retry_metrics as retry_metrics_pkg
import retry_monitoring as retry_monitoring_pkg
import retry_notification as retry_notification_pkg
import retry_notification_message as retry_notification_message_pkg

RETRY_OBSERVABILITY_PIPELINE_DIR = PROJECT_ROOT / "src" / "retry_observability_pipeline"

pipeline_files = {
    "__init__": RETRY_OBSERVABILITY_PIPELINE_DIR / "__init__.py",
    "retry_observability_report": RETRY_OBSERVABILITY_PIPELINE_DIR / "retry_observability_report.py",
    "retry_observability_pipeline": RETRY_OBSERVABILITY_PIPELINE_DIR / "retry_observability_pipeline.py",
}

lower_package_files = {
    "retry_metrics": PROJECT_ROOT / "src" / "retry_metrics",
    "retry_monitoring": PROJECT_ROOT / "src" / "retry_monitoring",
    "retry_alert": PROJECT_ROOT / "src" / "retry_alert",
    "retry_notification": PROJECT_ROOT / "src" / "retry_notification",
    "retry_notification_message": PROJECT_ROOT / "src" / "retry_notification_message",
}

EXPECTED_NOTIFY_BODY = "Retry Runtimeで通知対象の状態が検出されました。詳細を確認してください。"


def make_record(
    cycle_number: int,
    timestamp: str,
    enqueue_scanned: int,
    enqueue_enqueued: int,
) -> RetryRuntimeLogRecord:
    return RetryRuntimeLogRecord(
        cycle_number=cycle_number,
        timestamp=timestamp,
        dry_run=False,
        enqueue_scanned=enqueue_scanned,
        enqueue_enqueued=enqueue_enqueued,
        enqueue_skipped_existing=0,
        enqueue_skipped_status=0,
        enqueue_skipped_history=0,
        enqueue_failed=0,
        scheduler_candidates=0,
        execution_executed=0,
        removal_removed=0,
        cleanup_cleaned=0,
        terminal_cleanup_cleaned=0,
        history_recorded=0,
    )


HEALTHY_RECORDS = [make_record(1, "2026-07-14T00:00:00+00:00", enqueue_scanned=10, enqueue_enqueued=9)]
DEGRADED_RECORDS = [make_record(1, "2026-07-14T00:00:00+00:00", enqueue_scanned=10, enqueue_enqueued=6)]
UNHEALTHY_RECORDS = [make_record(1, "2026-07-14T00:00:00+00:00", enqueue_scanned=10, enqueue_enqueued=3)]


# ═══════════════════════════════════════════════════════════
# テスト1-7: RetryObservabilityReport（Immutable、invariant）
# ═══════════════════════════════════════════════════════════

_base_metrics = RetryMetricsSnapshot(
    cycle_count=0, period_start=None, period_end=None, dry_run_cycle_count=0,
    enqueue_scanned_total=0, enqueue_enqueued_total=0, enqueue_skipped_existing_total=0,
    enqueue_skipped_status_total=0, enqueue_skipped_history_total=0, enqueue_failed_total=0,
    scheduler_candidates_total=0, execution_executed_total=0, removal_removed_total=0,
    cleanup_cleaned_total=0, terminal_cleanup_cleaned_total=0, history_recorded_total=0,
    enqueue_success_ratio=None,
)
_base_health_healthy = RetryHealthReport(status=RetryHealthStatus.HEALTHY)
_base_alert_none = RetryAlert(level=RetryAlertLevel.NONE)
_decision_notify = RetryNotificationDecision(status=RetryNotificationStatus.NOTIFY)
_decision_no_notification = RetryNotificationDecision(status=RetryNotificationStatus.NO_NOTIFICATION)
_message_sample = RetryNotificationMessage(body=EXPECTED_NOTIFY_BODY)

print("[テスト1] RetryObservabilityReportはフィールド再代入でFrozenInstanceErrorを送出する")
report_1 = RetryObservabilityReport(
    metrics=_base_metrics, health_report=_base_health_healthy, alert=_base_alert_none,
    notification_decision=_decision_no_notification, message=None,
)
raised_1 = None
try:
    report_1.message = _message_sample
except FrozenInstanceError as e:
    raised_1 = e
check_true("1. FrozenInstanceErrorが送出される", raised_1 is not None)
print()

print("[テスト2] RetryObservabilityReportが保持するフィールドは5つのみ")
field_names_2 = tuple(f.name for f in fields(RetryObservabilityReport))
check(
    "2. フィールドは(metrics, health_report, alert, notification_decision, message)",
    field_names_2,
    ("metrics", "health_report", "alert", "notification_decision", "message"),
)
print()

print("[テスト3] NOTIFY + message非Noneの組み合わせは正常に構築できる")
raised_3 = None
try:
    RetryObservabilityReport(
        metrics=_base_metrics, health_report=_base_health_healthy, alert=_base_alert_none,
        notification_decision=_decision_notify, message=_message_sample,
    )
except ValueError as e:
    raised_3 = e
check_true("3. ValueErrorは送出されない", raised_3 is None)
print()

print("[テスト4] NO_NOTIFICATION + message=Noneの組み合わせは正常に構築できる")
raised_4 = None
try:
    RetryObservabilityReport(
        metrics=_base_metrics, health_report=_base_health_healthy, alert=_base_alert_none,
        notification_decision=_decision_no_notification, message=None,
    )
except ValueError as e:
    raised_4 = e
check_true("4. ValueErrorは送出されない", raised_4 is None)
print()

print("[テスト5] NOTIFY + message=Noneの組み合わせは構築時にValueErrorを送出する")
raised_5 = None
try:
    RetryObservabilityReport(
        metrics=_base_metrics, health_report=_base_health_healthy, alert=_base_alert_none,
        notification_decision=_decision_notify, message=None,
    )
except ValueError as e:
    raised_5 = e
check_true("5. ValueErrorが送出される", raised_5 is not None)
check_true("5. エラーメッセージにNOTIFYが含まれる", "NOTIFY" in str(raised_5))
print()

print("[テスト6] NO_NOTIFICATION + message非Noneの組み合わせは構築時にValueErrorを送出する")
raised_6 = None
try:
    RetryObservabilityReport(
        metrics=_base_metrics, health_report=_base_health_healthy, alert=_base_alert_none,
        notification_decision=_decision_no_notification, message=_message_sample,
    )
except ValueError as e:
    raised_6 = e
check_true("6. ValueErrorが送出される", raised_6 is not None)
check_true("6. エラーメッセージにNO_NOTIFICATIONが含まれる", "NO_NOTIFICATION" in str(raised_6))
print()

print("[テスト7] 未対応のstatus相当値は構築時にValueErrorを送出する")
_unknown_decision_7 = RetryNotificationDecision(status="UNKNOWN_FUTURE_STATUS")
raised_7 = None
try:
    RetryObservabilityReport(
        metrics=_base_metrics, health_report=_base_health_healthy, alert=_base_alert_none,
        notification_decision=_unknown_decision_7, message=None,
    )
except ValueError as e:
    raised_7 = e
check_true("7. ValueErrorが送出される", raised_7 is not None)
check_true("7. エラーメッセージに実際の値が含まれる", "UNKNOWN_FUTURE_STATUS" in str(raised_7))
print()


# ═══════════════════════════════════════════════════════════
# テスト8-14: RetryObservabilityPipeline（固定順序Composition）
# ═══════════════════════════════════════════════════════════

print("[テスト8] 空records → cycle_count=0 → HEALTHY → NONE → NO_NOTIFICATION → message=None")
report_8 = RetryObservabilityPipeline().evaluate([])
check("8. cycle_count == 0", report_8.metrics.cycle_count, 0)
check_true("8. HEALTHY", report_8.health_report.status is RetryHealthStatus.HEALTHY)
check_true("8. NONE", report_8.alert.level is RetryAlertLevel.NONE)
check_true(
    "8. NO_NOTIFICATION",
    report_8.notification_decision.status is RetryNotificationStatus.NO_NOTIFICATION,
)
check("8. message is None", report_8.message, None)
print()

print("[テスト9] HEALTHY経路（enqueue成功率0.9）→ NO_NOTIFICATION → message=None")
report_9 = RetryObservabilityPipeline().evaluate(HEALTHY_RECORDS)
check_true("9. HEALTHY", report_9.health_report.status is RetryHealthStatus.HEALTHY)
check_true(
    "9. NO_NOTIFICATION",
    report_9.notification_decision.status is RetryNotificationStatus.NO_NOTIFICATION,
)
check("9. message is None", report_9.message, None)
print()

print("[テスト10] DEGRADED経路（enqueue成功率0.6）→ WARNING → NOTIFY → 固定文言のMessage")
report_10 = RetryObservabilityPipeline().evaluate(DEGRADED_RECORDS)
check_true("10. DEGRADED", report_10.health_report.status is RetryHealthStatus.DEGRADED)
check_true("10. WARNING", report_10.alert.level is RetryAlertLevel.WARNING)
check_true("10. NOTIFY", report_10.notification_decision.status is RetryNotificationStatus.NOTIFY)
check_true("10. messageは非None", report_10.message is not None)
check("10. 固定文言のMessageが生成される", report_10.message.body, EXPECTED_NOTIFY_BODY)
print()

print("[テスト11] UNHEALTHY経路（enqueue成功率0.3）→ CRITICAL → NOTIFY → DEGRADED経路と同一のMessage")
report_11 = RetryObservabilityPipeline().evaluate(UNHEALTHY_RECORDS)
check_true("11. UNHEALTHY", report_11.health_report.status is RetryHealthStatus.UNHEALTHY)
check_true("11. CRITICAL", report_11.alert.level is RetryAlertLevel.CRITICAL)
check_true("11. NOTIFY", report_11.notification_decision.status is RetryNotificationStatus.NOTIFY)
check(
    "11. WARNING経路（テスト10）とCRITICAL経路（本テスト）は同一のMessageへ収束する",
    report_11.message.body,
    report_10.message.body,
)
print()

print("[テスト12] thresholds未指定時はDefault Threshold（degraded_below=0.8, unhealthy_below=0.5）が透過的に使用される")
_default_thresholds_pipeline = RetryObservabilityPipeline()
_default_thresholds_report = _default_thresholds_pipeline.evaluate(DEGRADED_RECORDS)
check_true(
    "12. Default Thresholdの下でDEGRADEDと判定される（enqueue成功率0.6は[0.5, 0.8)の範囲）",
    _default_thresholds_report.health_report.status is RetryHealthStatus.DEGRADED,
)
print()

print("[テスト13] カスタムthresholdsが透過的に注入される")
_custom_thresholds = RetryHealthThresholds(degraded_below=0.95, unhealthy_below=0.9)
_custom_thresholds_report = RetryObservabilityPipeline(thresholds=_custom_thresholds).evaluate(HEALTHY_RECORDS)
check_true(
    "13. カスタムthresholdsの下ではenqueue成功率0.9はDEGRADED（0.95未満）と判定される",
    _custom_thresholds_report.health_report.status is RetryHealthStatus.DEGRADED,
)
print()

print("[テスト14] 未対応のRetryNotificationStatus相当値ではevaluate()がValueErrorを送出する（Fail Fast契約）")
with mock.patch.object(
    RetryNotificationEvaluator,
    "evaluate",
    return_value=RetryNotificationDecision(status="UNKNOWN_FUTURE_STATUS"),
):
    raised_14 = None
    try:
        RetryObservabilityPipeline().evaluate(HEALTHY_RECORDS)
    except ValueError as e:
        raised_14 = e
check_true("14. ValueErrorが送出される", raised_14 is not None)
check_true("14. エラーメッセージに実際の値が含まれる", "UNKNOWN_FUTURE_STATUS" in str(raised_14))
print()


# ═══════════════════════════════════════════════════════════
# テスト15: Public API（__init__.pyのexport契約）
# ═══════════════════════════════════════════════════════════

print("[テスト15] package rootの__all__は2型のみをexportする")
expected_public_api_15 = {"RetryObservabilityReport", "RetryObservabilityPipeline"}
check("15. __all__の件数は2", len(retry_observability_pipeline.__all__), 2)
check_true(
    "15. __all__の集合は期待される2型と一致する",
    set(retry_observability_pipeline.__all__) == expected_public_api_15,
)
check_true(
    "15. RetryMetricsSnapshot等の下位型はpackage rootから直接アクセスできない（再exportしていない）",
    not hasattr(retry_observability_pipeline, "RetryMetricsSnapshot"),
)
check_true(
    "15. RetryRuntimeLogReaderはpackage rootから直接アクセスできない",
    not hasattr(retry_observability_pipeline, "RetryRuntimeLogReader"),
)
print()


# ═══════════════════════════════════════════════════════════
# テスト16-20: Dependency Rule（AST解析ベース）
# ═══════════════════════════════════════════════════════════

ALLOWED_MODULES = {
    "__future__", "dataclasses",
    "retry_metrics", "retry_monitoring", "retry_alert", "retry_notification", "retry_notification_message",
}
FORBIDDEN_MODULES = (
    "retry_runtime_lock", "retry_runtime_shutdown", "retry_runtime_loop",
    "retry_runtime_orchestrator", "retry_runtime_logging", "retry_runtime_loop_wiring",
    "retry_engine", "retry_composition", "retry_queue", "retry_history",
    "retry_enqueue_trigger", "retry_scheduler_source", "retry_scheduler_decision",
    "workflow_monitor", "workflow_engine", "scheduler",
    "execution_history", "ai", "pipeline", "outputs", "logger",
    "logging", "requests", "smtplib", "urllib", "http", "socket",
)

pipeline_import_details = {
    module_name: get_import_details(file_path)
    for module_name, file_path in pipeline_files.items()
}

print("[テスト16] retry_observability_pipelineの絶対importはALLOWED_MODULESの部分集合")
for module_name, details in pipeline_import_details.items():
    check_true(
        f"16. {module_name}の絶対importはALLOWED_MODULESの部分集合",
        details["absolute_roots"].issubset(ALLOWED_MODULES),
    )
print()

print("[テスト17] retry_observability_pipelineはRuntime系/RetryCompositionRoot/Scheduler/CLI/Logger/外部ライブラリをimportしない")
for module_name, details in pipeline_import_details.items():
    for forbidden in FORBIDDEN_MODULES:
        check_true(f"17. {module_name}が{forbidden}をimportしない", forbidden not in details["absolute_roots"])
print()

print("[テスト18] retry_observability_pipelineはretry_metricsからRetryRuntimeLogReaderをimportしない")
for module_name, details in pipeline_import_details.items():
    imported_names_from_metrics = details["from_names_by_module"].get("retry_metrics", set())
    check_true(
        f"18. {module_name}がretry_metrics.RetryRuntimeLogReaderをimportしない",
        "RetryRuntimeLogReader" not in imported_names_from_metrics,
    )
print()

print("[テスト19] retry_observability_pipeline配下の相対importは同一パッケージ内（level==1）のみ")
for module_name, details in pipeline_import_details.items():
    relative_levels = [imp["level"] for imp in details["relative_imports"]]
    check_true(
        f"19. {module_name}の相対importにlevel>=2（親パッケージ方向）が存在しない",
        all(level == 1 for level in relative_levels),
    )
print()

print("[テスト20] 既存5パッケージのいずれもretry_observability_pipelineをimportしない（逆依存禁止）")
for pkg_name, pkg_dir in lower_package_files.items():
    for py_file in sorted(pkg_dir.glob("*.py")):
        imported = get_imported_root_modules(py_file)
        check_true(
            f"20. {pkg_name}/{py_file.name}がretry_observability_pipelineをimportしない",
            "retry_observability_pipeline" not in imported,
        )
print()


# ═══════════════════════════════════════════════════════════
# テスト21: 外部I/Oの不在（構造的検証）
# ═══════════════════════════════════════════════════════════

print("[テスト21] retry_observability_pipeline配下のいずれのファイルも組み込みopen()を呼び出さない")
for module_name, file_path in pipeline_files.items():
    open_calls = get_open_call_lines(file_path)
    check_true(f"21. {module_name}がopen()を呼び出さない", len(open_calls) == 0)
print()


# ═══════════════════════════════════════════════════════════
# テスト22-25: CLI/Pipeline Parity Test
# ═══════════════════════════════════════════════════════════

SCRIPT_PATH = PROJECT_ROOT / "scripts" / "show_retry_notification.py"
MODULE_NAME = "show_retry_notification_v6_29_e2e"

check_true("0. show_retry_notification.py が存在する", SCRIPT_PATH.exists())

spec = importlib.util.spec_from_file_location(MODULE_NAME, SCRIPT_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("show_retry_notification.pyをロードできません")

show_retry_notification = importlib.util.module_from_spec(spec)

_previous_module = sys.modules.get(MODULE_NAME)
sys.modules[MODULE_NAME] = show_retry_notification

try:
    spec.loader.exec_module(show_retry_notification)
except Exception:
    if _previous_module is None:
        sys.modules.pop(MODULE_NAME, None)
    else:
        sys.modules[MODULE_NAME] = _previous_module
    raise


def parity_check(scenario_label: str, test_number: int, records: list) -> None:
    """
    RetryRuntimeLogReader.readをクラスレベルでmonkeypatchし、CLIの
    build_report()とPipelineのevaluate()へ同一recordsを与えて、両者の
    出力が意味的に同一であることを検証する。

    ファイルI/O・JSONLパース処理自体はこの検証の対象外（既存v6.8.0 CLI E2E
    で別途カバー済み）。
    """
    with mock.patch.object(
        show_retry_notification.RetryRuntimeLogReader, "read", return_value=records,
    ):
        cli_report = show_retry_notification.build_report(Path("unused.jsonl"))

    pipeline_report = RetryObservabilityPipeline().evaluate(records)

    check(f"{test_number}. PARITY[{scenario_label}]: metrics", cli_report.metrics, pipeline_report.metrics)
    check(
        f"{test_number}. PARITY[{scenario_label}]: health_report",
        cli_report.health_report,
        pipeline_report.health_report,
    )
    check(f"{test_number}. PARITY[{scenario_label}]: alert", cli_report.alert, pipeline_report.alert)
    check(
        f"{test_number}. PARITY[{scenario_label}]: notification_decision",
        cli_report.notification_decision,
        pipeline_report.notification_decision,
    )
    check(f"{test_number}. PARITY[{scenario_label}]: message", cli_report.message, pipeline_report.message)


print("[テスト22] CLI/Pipeline Parity（empty records）")
parity_check("empty", 22, [])
print()

print("[テスト23] CLI/Pipeline Parity（HEALTHY records）")
parity_check("HEALTHY", 23, HEALTHY_RECORDS)
print()

print("[テスト24] CLI/Pipeline Parity（DEGRADED records）")
parity_check("DEGRADED", 24, DEGRADED_RECORDS)
print()

print("[テスト25] CLI/Pipeline Parity（UNHEALTHY records）")
parity_check("UNHEALTHY", 25, UNHEALTHY_RECORDS)
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
