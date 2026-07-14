"""
E2E テスト: v6.5.0 Retry Alert Foundation

テストシナリオ（docs/design/retry_alert_foundation.md 対応）:
    ── RetryAlertLevel ──
    1.  NONE / WARNING / CRITICAL の3値を持つ

    ── RetryAlert（Immutable、levelのみ） ──
    2.  フィールド再代入でFrozenInstanceErrorを送出する
    3.  保持するフィールドはlevelのみ（message/triggered_at/source_reportを持たない）

    ── RetryAlertEvaluator（変換規則・Design Contract、4.1節） ──
    4.  HEALTHY -> NONE
    5.  DEGRADED -> WARNING
    6.  UNHEALTHY -> CRITICAL

    ── RetryAlertEvaluator（未対応Statusの扱い・Fail Fast契約、4.3節） ──
    7.  既知の3 Status以外が渡された場合、フォールバックせずValueErrorを送出する
    8.  例外はNONE等の既存Levelへのフォールバックではないことを確認する

    ── RetryAlertLevel.NONEの意味（正常系の明示値、4.2節） ──
    9.  HEALTHY入力時、evaluate()はNoneではなく具体的なRetryAlert(level=NONE)を返す（Total Function）

    ── RetryAlertEvaluator（Stateless Pure Function） ──
    10. 同一Reportを複数回渡しても常に同一Alertを返す（決定的）
    11. 異なるEvaluatorインスタンスでも同一Reportに対し同一結果を返す

    ── Dependency Rule（依存方向の構造的検証） ──
    12. retry_alertはretry_metrics/Runtime/Logger系パッケージをimportしない
    13. retry_alertはファイルI/O関連コード（open/Path/.jsonl）を含まない
    14. retry_monitoringはretry_alertをimportしない（逆依存禁止）

    ── 統合テスト（Metrics → Monitoring → Alert end-to-end） ──
    15. RetryRuntimeLogReader → RetryMetricsCalculator → RetryHealthEvaluator → RetryAlertEvaluatorが一貫して動作する

既存コンポーネントの無改修確認（Zero Diff）について:
    本ファイルは恒久的なE2Eテストであるため、コミット時点の差分に依存する`git diff`ベースの
    無改修確認は含めない。既存コンポーネントの無改修確認はRelease Reviewにおいて
    `git diff --name-status` / `git status --short`で個別に行う（Code Review指摘反映）。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_5_0_retry_alert_foundation.py
"""
import dataclasses
import inspect
import sys
import tempfile
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


def check_not_contains(label: str, text, keyword: str):
    check(label, keyword in str(text), False)


print("=" * 60)
print("v6.5.0 Retry Alert Foundation E2E テスト")
print("=" * 60)
print()

import retry_alert.retry_alert as _alert_module
import retry_alert.retry_alert_evaluator as _alert_evaluator_module
import retry_alert.retry_alert_level as _alert_level_module
import retry_monitoring.retry_health_evaluator as _monitoring_evaluator_module
import retry_monitoring.retry_health_report as _monitoring_report_module
import retry_monitoring.retry_health_status as _monitoring_status_module
import retry_monitoring.retry_health_thresholds as _monitoring_thresholds_module
from retry_alert import RetryAlert, RetryAlertEvaluator, RetryAlertLevel
from retry_metrics import RetryMetricsCalculator, RetryMetricsSnapshot, RetryRuntimeLogReader
from retry_monitoring import RetryHealthEvaluator, RetryHealthReport, RetryHealthStatus


def make_snapshot(enqueue_success_ratio):
    """テスト用にenqueue_success_ratioのみ制御したRetryMetricsSnapshotを組み立てる。"""
    return RetryMetricsSnapshot(
        cycle_count=1,
        period_start="2026-07-14T00:00:00+00:00",
        period_end="2026-07-14T00:00:00+00:00",
        dry_run_cycle_count=0,
        enqueue_scanned_total=10,
        enqueue_enqueued_total=0,
        enqueue_skipped_existing_total=0,
        enqueue_skipped_status_total=0,
        enqueue_skipped_history_total=0,
        enqueue_failed_total=0,
        scheduler_candidates_total=0,
        execution_executed_total=0,
        removal_removed_total=0,
        cleanup_cleaned_total=0,
        terminal_cleanup_cleaned_total=0,
        history_recorded_total=0,
        enqueue_success_ratio=enqueue_success_ratio,
    )


# ═══════════════════════════════════════════════════════════
# テスト1: RetryAlertLevel
# ═══════════════════════════════════════════════════════════

print("[テスト1] RetryAlertLevelはNONE/WARNING/CRITICALの3値を持つ")
check("1. メンバー数は3", len(list(RetryAlertLevel)), 3)
check("1. NONEが存在する", RetryAlertLevel.NONE.value, "NONE")
check("1. WARNINGが存在する", RetryAlertLevel.WARNING.value, "WARNING")
check("1. CRITICALが存在する", RetryAlertLevel.CRITICAL.value, "CRITICAL")
print()


# ═══════════════════════════════════════════════════════════
# テスト2-3: RetryAlert
# ═══════════════════════════════════════════════════════════

print("[テスト2] RetryAlertはフィールド再代入でFrozenInstanceErrorを送出する")
alert_2 = RetryAlert(level=RetryAlertLevel.NONE)
raised_2 = None
try:
    alert_2.level = RetryAlertLevel.CRITICAL
except FrozenInstanceError as e:
    raised_2 = e
check_true("2. FrozenInstanceErrorが送出される", raised_2 is not None)
print()

print("[テスト3] RetryAlertが保持するフィールドはlevelのみ")
field_names_3 = tuple(f.name for f in dataclasses.fields(RetryAlert))
check("3. フィールドは(level,)のみ", field_names_3, ("level",))
check_true("3. messageフィールドを持たない", "message" not in field_names_3)
check_true("3. triggered_atフィールドを持たない", "triggered_at" not in field_names_3)
check_true("3. source_reportフィールドを持たない", "source_report" not in field_names_3)
print()


# ═══════════════════════════════════════════════════════════
# テスト4-6: RetryAlertEvaluator 変換規則（Design Contract）
# ═══════════════════════════════════════════════════════════

evaluator = RetryAlertEvaluator()

print("[テスト4] HEALTHY -> NONE")
check(
    "4. NONEを返す",
    evaluator.evaluate(RetryHealthReport(status=RetryHealthStatus.HEALTHY)).level,
    RetryAlertLevel.NONE,
)
print()

print("[テスト5] DEGRADED -> WARNING")
check(
    "5. WARNINGを返す",
    evaluator.evaluate(RetryHealthReport(status=RetryHealthStatus.DEGRADED)).level,
    RetryAlertLevel.WARNING,
)
print()

print("[テスト6] UNHEALTHY -> CRITICAL")
check(
    "6. CRITICALを返す",
    evaluator.evaluate(RetryHealthReport(status=RetryHealthStatus.UNHEALTHY)).level,
    RetryAlertLevel.CRITICAL,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト7-8: RetryAlertEvaluator 未対応Statusの扱い（Fail Fast契約）
# ═══════════════════════════════════════════════════════════

print("[テスト7] 既知の3 Status以外が渡された場合、フォールバックせずValueErrorを送出する")
# RetryHealthStatusは現時点でHEALTHY/DEGRADED/UNHEALTHYの3値のみだが、将来値が
# 追加された場合の未対応Statusを模擬するため、意図的に既知の3値のいずれでもない
# 文字列をstatusとして持つRetryHealthReportを組み立てる（dataclassは型を実行時
# 強制しないため、これが可能）。
unknown_report_7 = RetryHealthReport(status="UNKNOWN_FUTURE_STATUS")
raised_7 = None
result_7 = None
try:
    result_7 = evaluator.evaluate(unknown_report_7)
except ValueError as e:
    raised_7 = e
check_true("7. ValueErrorが送出される", raised_7 is not None)
check_true("7. RetryAlertは返らない", result_7 is None)
print()

print("[テスト8] 未対応Statusの例外はNONE等の既存Levelへのフォールバックではない")
# テスト7で例外が送出されていること自体が「フォールバックしていない」ことの証拠。
# ここでは例外メッセージに未対応であることが分かる情報が含まれることを確認する。
check_true("8. 例外メッセージにstatusの値が含まれる", "UNKNOWN_FUTURE_STATUS" in str(raised_7))
print()


# ═══════════════════════════════════════════════════════════
# テスト9: RetryAlertLevel.NONEの意味（正常系の明示値、Total Function）
# ═══════════════════════════════════════════════════════════

print("[テスト9] HEALTHY入力時、evaluate()はNoneではなく具体的なRetryAlert(level=NONE)を返す")
report_9 = RetryHealthReport(status=RetryHealthStatus.HEALTHY)
result_9 = evaluator.evaluate(report_9)
check_true("9. Noneではない（Optionalを返さない）", result_9 is not None)
check_true("9. RetryAlertのインスタンスである", isinstance(result_9, RetryAlert))
check("9. levelはNONE", result_9.level, RetryAlertLevel.NONE)
print()


# ═══════════════════════════════════════════════════════════
# テスト10-11: Stateless Pure Function
# ═══════════════════════════════════════════════════════════

print("[テスト10] 同一Reportを複数回渡しても常に同一Alertを返す（決定的）")
report_10 = RetryHealthReport(status=RetryHealthStatus.DEGRADED)
results_10 = [evaluator.evaluate(report_10).level for _ in range(5)]
check_true("10. 5回とも同じlevelを返す", all(level == results_10[0] for level in results_10))
check("10. 返す値はWARNING", results_10[0], RetryAlertLevel.WARNING)
print()

print("[テスト11] 異なるEvaluatorインスタンスでも同一Reportに対し同一結果を返す")
evaluator_a = RetryAlertEvaluator()
evaluator_b = RetryAlertEvaluator()
report_11 = RetryHealthReport(status=RetryHealthStatus.UNHEALTHY)
check(
    "11. インスタンスが異なっても結果は同一",
    evaluator_a.evaluate(report_11).level,
    evaluator_b.evaluate(report_11).level,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト12-14: Dependency Rule
# ═══════════════════════════════════════════════════════════

print("[テスト12] retry_alertはretry_metrics/Runtime/Logger系パッケージをimportしない")
alert_modules = {
    "retry_alert_level": inspect.getsource(_alert_level_module),
    "retry_alert": inspect.getsource(_alert_module),
    "retry_alert_evaluator": inspect.getsource(_alert_evaluator_module),
}
forbidden_imports = (
    "retry_metrics", "retry_runtime_logging", "retry_runtime_orchestrator",
    "retry_runtime_loop", "retry_runtime_shutdown", "retry_runtime_lock",
    "retry_engine", "retry_composition", "retry_queue", "retry_history",
    "retry_enqueue_trigger", "workflow_monitor", "workflow_engine",
    "scheduler", "execution_history",
)
for module_name, source in alert_modules.items():
    for forbidden in forbidden_imports:
        check_not_contains(f"12. {module_name}が{forbidden}をimportしない（import文）", source, f"import {forbidden}")
        check_not_contains(f"12. {module_name}が{forbidden}をimportしない（from文）", source, f"from {forbidden}")
print()

print("[テスト13] retry_alertはファイルI/O関連コード（open/Path/.jsonl）を含まない")
for module_name, source in alert_modules.items():
    check_not_contains(f"13. {module_name}がopen(を含まない", source, "open(")
    check_not_contains(f"13. {module_name}がpathlib.Pathをimportしない", source, "from pathlib")
    check_not_contains(f"13. {module_name}が.jsonlという文字列を含まない", source, ".jsonl")
print()

print("[テスト14] retry_monitoringはretry_alertをimportしない（逆依存禁止）")
monitoring_modules = {
    "retry_health_status": inspect.getsource(_monitoring_status_module),
    "retry_health_thresholds": inspect.getsource(_monitoring_thresholds_module),
    "retry_health_report": inspect.getsource(_monitoring_report_module),
    "retry_health_evaluator": inspect.getsource(_monitoring_evaluator_module),
}
for module_name, source in monitoring_modules.items():
    check_not_contains(f"14. {module_name}がretry_alertをimportしない（import文）", source, "import retry_alert")
    check_not_contains(f"14. {module_name}がretry_alertをimportしない（from文）", source, "from retry_alert")
print()


# ═══════════════════════════════════════════════════════════
# テスト15: 統合テスト（Metrics → Monitoring → Alert end-to-end）
# ═══════════════════════════════════════════════════════════

print("[テスト15] RetryRuntimeLogReader → RetryMetricsCalculator → RetryHealthEvaluator → RetryAlertEvaluatorが一貫して動作する")
from retry_enqueue_trigger import RetryEnqueueTriggerResult
from retry_runtime_logging import RetryRuntimeCycleLogger
from retry_runtime_orchestrator import RetryRuntimeCycleResult

with tempfile.TemporaryDirectory() as tmpdir_15:
    log_path_15 = Path(tmpdir_15) / "retry_runtime_log.jsonl"
    writer_15 = RetryRuntimeCycleLogger(log_path=log_path_15)

    def make_cycle_result(scanned, enqueued):
        trigger_result = RetryEnqueueTriggerResult(
            scanned=scanned, enqueued=enqueued, skipped_existing=0,
            skipped_status=0, skipped_history=0, failed=0,
        )
        return RetryRuntimeCycleResult(
            trigger_result=trigger_result,
            scheduler_events=[],
            execution_results=[object()] * enqueued,
            removal_results=[],
            cleanup_results=[],
            terminal_cleanup_results=[],
            history_results=[],
        )

    # enqueue_success_ratio = 1 / 10 = 0.1 -> UNHEALTHY相当のデータを書き込む
    writer_15.log_cycle(cycle_number=1, result=make_cycle_result(scanned=10, enqueued=1), dry_run=False)

    reader_15 = RetryRuntimeLogReader(log_path=log_path_15)
    records_15 = reader_15.read()
    snapshot_15 = RetryMetricsCalculator().calculate(records_15)
    check("15. enqueue_success_ratio=0.1", snapshot_15.enqueue_success_ratio, 0.1)

    report_15 = RetryHealthEvaluator().evaluate(snapshot_15)
    check("15. UNHEALTHYと判定される", report_15.status, RetryHealthStatus.UNHEALTHY)

    alert_15 = RetryAlertEvaluator().evaluate(report_15)
    check("15. CRITICALと判定される", alert_15.level, RetryAlertLevel.CRITICAL)
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
