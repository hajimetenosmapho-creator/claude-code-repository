"""
E2E テスト: v6.4.0 Retry Monitoring Foundation

テストシナリオ（docs/design/retry_monitoring_foundation.md 対応）:
    ── RetryHealthStatus ──
    1.  HEALTHY / DEGRADED / UNHEALTHY の3値を持つ

    ── RetryHealthThresholds（Immutable Value Object / Domain Value） ──
    2.  デフォルト値はdegraded_below=0.8 / unhealthy_below=0.5
    3.  フィールド再代入でFrozenInstanceErrorを送出する

    ── RetryHealthReport（Immutable、statusのみ） ──
    4.  フィールド再代入でFrozenInstanceErrorを送出する
    5.  保持するフィールドはstatusのみ（reason/warnings/detailsを持たない）

    ── RetryHealthEvaluator（判定ロジック・閾値境界値） ──
    6.  enqueue_success_ratioがNoneの場合、例外を送出せずHEALTHYを返す
    7.  ratio=1.0（degraded_below以上）はHEALTHY
    8.  ratio=0.8（degraded_belowと同値）はHEALTHY（境界値、未満のみDEGRADED）
    9.  ratio=0.79（degraded_below未満）はDEGRADED
    10. ratio=0.5（unhealthy_belowと同値）はDEGRADED（境界値、未満のみUNHEALTHY）
    11. ratio=0.49（unhealthy_below未満）はUNHEALTHY
    12. ratio=0.0はUNHEALTHY
    13. カスタムThresholdsを渡した場合、判定がその閾値に従って変わる
    14. thresholds未指定時はデフォルト値（RetryHealthThresholds()）が使われる

    ── RetryHealthEvaluator（Stateless Pure Function） ──
    15. 同一Snapshotを複数回渡しても常に同一Reportを返す（決定的）
    16. 異なるEvaluatorインスタンス（同一Threshold）でも同一Snapshotに対し同一結果を返す

    ── Dependency Rule（依存方向の構造的検証） ──
    17. retry_monitoringはRuntime/Logger系パッケージをimportしない
    18. retry_monitoringはファイルI/O関連コード（open/Path/.jsonl）を含まない
    19. retry_metricsはretry_monitoringをimportしない（逆依存禁止）

    ── 統合テスト（Metrics → Monitoring end-to-end） ──
    20. RetryRuntimeLogReader → RetryMetricsCalculator → RetryHealthEvaluatorが一貫して動作する

    ── Backward Compatibility / Zero Diff（Runtime Pipeline・retry_metrics無改修確認） ──
    21-29. 各既存コンポーネントに変更がないこと（git diff）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_4_0_retry_monitoring_foundation.py
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
print("v6.4.0 Retry Monitoring Foundation E2E テスト")
print("=" * 60)
print()

import retry_metrics.retry_metrics_calculator as _metrics_calculator_module
import retry_metrics.retry_metrics_snapshot as _metrics_snapshot_module
import retry_metrics.retry_runtime_log_reader as _metrics_reader_module
import retry_metrics.retry_runtime_log_record as _metrics_record_module
import retry_monitoring.retry_health_evaluator as _evaluator_module
import retry_monitoring.retry_health_report as _report_module
import retry_monitoring.retry_health_status as _status_module
import retry_monitoring.retry_health_thresholds as _thresholds_module
from retry_metrics import RetryMetricsCalculator, RetryMetricsSnapshot, RetryRuntimeLogReader
from retry_monitoring import (
    RetryHealthEvaluator,
    RetryHealthReport,
    RetryHealthStatus,
    RetryHealthThresholds,
)


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
# テスト1: RetryHealthStatus
# ═══════════════════════════════════════════════════════════

print("[テスト1] RetryHealthStatusはHEALTHY/DEGRADED/UNHEALTHYの3値を持つ")
check("1. メンバー数は3", len(list(RetryHealthStatus)), 3)
check("1. HEALTHYが存在する", RetryHealthStatus.HEALTHY.value, "HEALTHY")
check("1. DEGRADEDが存在する", RetryHealthStatus.DEGRADED.value, "DEGRADED")
check("1. UNHEALTHYが存在する", RetryHealthStatus.UNHEALTHY.value, "UNHEALTHY")
print()


# ═══════════════════════════════════════════════════════════
# テスト2-3: RetryHealthThresholds
# ═══════════════════════════════════════════════════════════

print("[テスト2] RetryHealthThresholdsのデフォルト値")
default_thresholds = RetryHealthThresholds()
check("2. degraded_belowのデフォルトは0.8", default_thresholds.degraded_below, 0.8)
check("2. unhealthy_belowのデフォルトは0.5", default_thresholds.unhealthy_below, 0.5)
print()

print("[テスト3] RetryHealthThresholdsはフィールド再代入でFrozenInstanceErrorを送出する")
raised_3 = None
try:
    default_thresholds.degraded_below = 0.1
except FrozenInstanceError as e:
    raised_3 = e
check_true("3. FrozenInstanceErrorが送出される", raised_3 is not None)
print()


# ═══════════════════════════════════════════════════════════
# テスト4-5: RetryHealthReport
# ═══════════════════════════════════════════════════════════

print("[テスト4] RetryHealthReportはフィールド再代入でFrozenInstanceErrorを送出する")
report_4 = RetryHealthReport(status=RetryHealthStatus.HEALTHY)
raised_4 = None
try:
    report_4.status = RetryHealthStatus.UNHEALTHY
except FrozenInstanceError as e:
    raised_4 = e
check_true("4. FrozenInstanceErrorが送出される", raised_4 is not None)
print()

print("[テスト5] RetryHealthReportが保持するフィールドはstatusのみ")
field_names_5 = tuple(f.name for f in dataclasses.fields(RetryHealthReport))
check("5. フィールドは(status,)のみ", field_names_5, ("status",))
check_true("5. reasonフィールドを持たない", "reason" not in field_names_5)
check_true("5. warningsフィールドを持たない", "warnings" not in field_names_5)
check_true("5. detailsフィールドを持たない", "details" not in field_names_5)
check_true("5. violationsフィールドを持たない", "violations" not in field_names_5)
print()


# ═══════════════════════════════════════════════════════════
# テスト6-12: RetryHealthEvaluator 閾値境界値
# ═══════════════════════════════════════════════════════════

evaluator = RetryHealthEvaluator()

print("[テスト6] enqueue_success_ratioがNoneの場合、例外を送出せずHEALTHYを返す")
raised_6 = None
report_6 = None
try:
    report_6 = evaluator.evaluate(make_snapshot(None))
except Exception as e:
    raised_6 = e
check_true("6. 例外を送出しない", raised_6 is None)
check("6. HEALTHYを返す", report_6.status, RetryHealthStatus.HEALTHY)
print()

print("[テスト7] ratio=1.0はHEALTHY")
check("7. HEALTHY", evaluator.evaluate(make_snapshot(1.0)).status, RetryHealthStatus.HEALTHY)
print()

print("[テスト8] ratio=0.8（degraded_belowと同値）はHEALTHY")
check("8. HEALTHY", evaluator.evaluate(make_snapshot(0.8)).status, RetryHealthStatus.HEALTHY)
print()

print("[テスト9] ratio=0.79（degraded_below未満）はDEGRADED")
check("9. DEGRADED", evaluator.evaluate(make_snapshot(0.79)).status, RetryHealthStatus.DEGRADED)
print()

print("[テスト10] ratio=0.5（unhealthy_belowと同値）はDEGRADED")
check("10. DEGRADED", evaluator.evaluate(make_snapshot(0.5)).status, RetryHealthStatus.DEGRADED)
print()

print("[テスト11] ratio=0.49（unhealthy_below未満）はUNHEALTHY")
check("11. UNHEALTHY", evaluator.evaluate(make_snapshot(0.49)).status, RetryHealthStatus.UNHEALTHY)
print()

print("[テスト12] ratio=0.0はUNHEALTHY")
check("12. UNHEALTHY", evaluator.evaluate(make_snapshot(0.0)).status, RetryHealthStatus.UNHEALTHY)
print()

print("[テスト13] カスタムThresholdsを渡した場合、判定がその閾値に従って変わる")
custom_thresholds = RetryHealthThresholds(degraded_below=0.95, unhealthy_below=0.9)
custom_evaluator = RetryHealthEvaluator(thresholds=custom_thresholds)
check(
    "13. デフォルトならHEALTHYになるratio=0.92がカスタムThresholdsではDEGRADEDになる",
    custom_evaluator.evaluate(make_snapshot(0.92)).status,
    RetryHealthStatus.DEGRADED,
)
check(
    "13. デフォルトならHEALTHYになるratio=0.85がカスタムThresholdsではUNHEALTHYになる",
    custom_evaluator.evaluate(make_snapshot(0.85)).status,
    RetryHealthStatus.UNHEALTHY,
)
print()

print("[テスト14] thresholds未指定時はデフォルト値が使われる")
evaluator_14 = RetryHealthEvaluator()
check("14. thresholds.degraded_below=0.8", evaluator_14.thresholds.degraded_below, 0.8)
check("14. thresholds.unhealthy_below=0.5", evaluator_14.thresholds.unhealthy_below, 0.5)
print()


# ═══════════════════════════════════════════════════════════
# テスト15-16: Stateless Pure Function
# ═══════════════════════════════════════════════════════════

print("[テスト15] 同一Snapshotを複数回渡しても常に同一Reportを返す（決定的）")
snapshot_15 = make_snapshot(0.6)
results_15 = [evaluator.evaluate(snapshot_15).status for _ in range(5)]
check_true("15. 5回とも同じstatusを返す", all(status == results_15[0] for status in results_15))
check("15. 返す値はDEGRADED", results_15[0], RetryHealthStatus.DEGRADED)
print()

print("[テスト16] 異なるEvaluatorインスタンス（同一Threshold）でも同一Snapshotに対し同一結果を返す")
evaluator_a = RetryHealthEvaluator(thresholds=RetryHealthThresholds())
evaluator_b = RetryHealthEvaluator(thresholds=RetryHealthThresholds())
snapshot_16 = make_snapshot(0.3)
check(
    "16. インスタンスが異なっても結果は同一",
    evaluator_a.evaluate(snapshot_16).status,
    evaluator_b.evaluate(snapshot_16).status,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト17-19: Dependency Rule
# ═══════════════════════════════════════════════════════════

print("[テスト17] retry_monitoringはRuntime/Logger系パッケージをimportしない")
monitoring_modules = {
    "retry_health_status": inspect.getsource(_status_module),
    "retry_health_thresholds": inspect.getsource(_thresholds_module),
    "retry_health_report": inspect.getsource(_report_module),
    "retry_health_evaluator": inspect.getsource(_evaluator_module),
}
forbidden_imports = (
    "retry_runtime_logging", "retry_runtime_orchestrator", "retry_runtime_loop",
    "retry_runtime_shutdown", "retry_runtime_lock", "retry_engine",
    "retry_composition", "retry_queue", "retry_history", "retry_enqueue_trigger",
    "workflow_monitor", "workflow_engine", "scheduler", "execution_history",
)
for module_name, source in monitoring_modules.items():
    for forbidden in forbidden_imports:
        check_not_contains(f"17. {module_name}が{forbidden}をimportしない（import文）", source, f"import {forbidden}")
        check_not_contains(f"17. {module_name}が{forbidden}をimportしない（from文）", source, f"from {forbidden}")
print()

print("[テスト18] retry_monitoringはファイルI/O関連コード（open/Path/.jsonl）を含まない")
for module_name, source in monitoring_modules.items():
    check_not_contains(f"18. {module_name}がopen(を含まない", source, "open(")
    check_not_contains(f"18. {module_name}がpathlib.Pathをimportしない", source, "from pathlib")
    check_not_contains(f"18. {module_name}が.jsonlという文字列を含まない", source, ".jsonl")
print()

print("[テスト19] retry_metricsはretry_monitoringをimportしない（逆依存禁止）")
metrics_modules = {
    "retry_metrics_snapshot": inspect.getsource(_metrics_snapshot_module),
    "retry_metrics_calculator": inspect.getsource(_metrics_calculator_module),
    "retry_runtime_log_reader": inspect.getsource(_metrics_reader_module),
    "retry_runtime_log_record": inspect.getsource(_metrics_record_module),
}
for module_name, source in metrics_modules.items():
    check_not_contains(f"19. {module_name}がretry_monitoringをimportしない（import文）", source, "import retry_monitoring")
    check_not_contains(f"19. {module_name}がretry_monitoringをimportしない（from文）", source, "from retry_monitoring")
print()


# ═══════════════════════════════════════════════════════════
# テスト20: 統合テスト（Metrics → Monitoring end-to-end）
# ═══════════════════════════════════════════════════════════

print("[テスト20] RetryRuntimeLogReader → RetryMetricsCalculator → RetryHealthEvaluatorが一貫して動作する")
from retry_enqueue_trigger import RetryEnqueueTriggerResult
from retry_runtime_logging import RetryRuntimeCycleLogger
from retry_runtime_orchestrator import RetryRuntimeCycleResult

with tempfile.TemporaryDirectory() as tmpdir_20:
    log_path_20 = Path(tmpdir_20) / "retry_runtime_log.jsonl"
    writer_20 = RetryRuntimeCycleLogger(log_path=log_path_20)

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
    writer_20.log_cycle(cycle_number=1, result=make_cycle_result(scanned=10, enqueued=1), dry_run=False)

    reader_20 = RetryRuntimeLogReader(log_path=log_path_20)
    records_20 = reader_20.read()
    snapshot_20 = RetryMetricsCalculator().calculate(records_20)
    check("20. enqueue_success_ratio=0.1", snapshot_20.enqueue_success_ratio, 0.1)

    report_20 = RetryHealthEvaluator().evaluate(snapshot_20)
    check("20. UNHEALTHYと判定される", report_20.status, RetryHealthStatus.UNHEALTHY)
print()


# ═══════════════════════════════════════════════════════════
# テスト21-29: Backward Compatibility / Zero Diff
# ═══════════════════════════════════════════════════════════

print("[テスト21-29] Runtime Pipeline・retry_metrics関連コンポーネントに変更がないこと（git diff）")

unchanged_paths = [
    "src/retry_runtime_lock",
    "src/retry_runtime_shutdown",
    "src/retry_runtime_loop",
    "src/retry_runtime_orchestrator",
    "src/retry_engine",
    "src/retry_composition",
    "src/retry_runtime_logging",
    "src/retry_metrics",
    "scripts/run_retry_runtime.py",
]

import subprocess

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"21-29. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("21-29. gitが利用できないため無変更確認をスキップ", True)
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
