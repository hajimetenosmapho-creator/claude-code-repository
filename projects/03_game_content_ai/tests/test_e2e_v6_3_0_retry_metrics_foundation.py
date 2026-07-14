"""
E2E テスト: v6.3.0 Retry Metrics Foundation

テストシナリオ（docs/design/retry_metrics_foundation.md 対応）:
    ── RetryRuntimeLogRecord / RetryMetricsSnapshot Immutability ──
    1.  RetryRuntimeLogRecordはフィールド再代入でFrozenInstanceErrorを送出する
    17. RetryMetricsSnapshotはフィールド再代入でFrozenInstanceErrorを送出する

    ── RetryRuntimeLogReader ──
    2.  存在しないログファイルに対するread()は空リストを返す
    3.  正常なJSONL 2行を正しくRetryRuntimeLogRecordへ変換する
    4.  壊れたJSON行はスキップされ、正常な行のみ読み込まれる
    5.  壊れた行に対しstderrへWARNINGが出力される
    6.  フィールド欠落行（KeyError相当）もスキップされる
    7.  空行はスキップされる（読み込み結果に影響しない）
    8.  ファイル自体が読めない場合は例外を送出する（fail-fast）

    ── RetryMetricsCalculator ──
    9.  calculate([])はcycle_count=0のSnapshotを返す（例外を送出しない）
    10. calculate([])は全合計フィールドが0、period_start/endがNoneになる
    11. calculate([])はenqueue_success_ratioがNoneになる
    12. calculate(records)は各合計フィールドが正しく計算される
    13. calculate(records)はenqueue_success_ratioが正しく計算される
    14. enqueue_scanned_total=0の場合、enqueue_success_ratioはNoneになる
    15. period_start/period_endはtimestampのmin/maxで算出される（リスト順序に依存しない）
    16. dry_run_cycle_countが正しく計算される

    ── Dependency（Read Only Foundation確認） ──
    18. retry_metricsパッケージは他のretry_*パッケージをimportしない

    ── 統合テスト（Read Only Foundation end-to-end） ──
    19. RetryRuntimeCycleLoggerと同じJSONL形式を読み取り、集計まで一貫して行える

    ── Backward Compatibility / Zero Diff（Runtime Pipeline無改修確認） ──
    20. RetryRuntimeLock無変更（git diff）
    21. RetryRuntimeShutdown無変更（git diff）
    22. RetryRuntimeLoop無変更（git diff）
    23. RetryRuntimeOrchestrator無変更（git diff）
    24. RetryManager（retry_engine）無変更（git diff）
    25. RetryCompositionRoot無変更（git diff）
    26. RetryRuntimeCycleLogger（retry_runtime_logging）無変更（git diff）
    27. scripts/run_retry_runtime.py 無変更（git diff）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_3_0_retry_metrics_foundation.py
"""
import contextlib
import inspect
import io
import json
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


def check_contains(label: str, text, keyword: str):
    check(label, keyword in str(text), True)


def check_not_contains(label: str, text, keyword: str):
    check(label, keyword in str(text), False)


print("=" * 60)
print("v6.3.0 Retry Metrics Foundation E2E テスト")
print("=" * 60)
print()

import retry_metrics.retry_metrics_calculator as _calculator_module
import retry_metrics.retry_metrics_snapshot as _snapshot_module
import retry_metrics.retry_runtime_log_reader as _reader_module
import retry_metrics.retry_runtime_log_record as _record_module
from retry_metrics import (
    RetryMetricsCalculator,
    RetryMetricsSnapshot,
    RetryRuntimeLogReader,
    RetryRuntimeLogRecord,
)


def make_record(
    cycle_number=1,
    timestamp="2026-07-14T00:00:00+00:00",
    dry_run=False,
    enqueue_scanned=3,
    enqueue_enqueued=1,
    enqueue_skipped_existing=0,
    enqueue_skipped_status=1,
    enqueue_skipped_history=1,
    enqueue_failed=0,
    scheduler_candidates=1,
    execution_executed=1,
    removal_removed=0,
    cleanup_cleaned=0,
    terminal_cleanup_cleaned=0,
    history_recorded=1,
):
    return RetryRuntimeLogRecord(
        cycle_number=cycle_number,
        timestamp=timestamp,
        dry_run=dry_run,
        enqueue_scanned=enqueue_scanned,
        enqueue_enqueued=enqueue_enqueued,
        enqueue_skipped_existing=enqueue_skipped_existing,
        enqueue_skipped_status=enqueue_skipped_status,
        enqueue_skipped_history=enqueue_skipped_history,
        enqueue_failed=enqueue_failed,
        scheduler_candidates=scheduler_candidates,
        execution_executed=execution_executed,
        removal_removed=removal_removed,
        cleanup_cleaned=cleanup_cleaned,
        terminal_cleanup_cleaned=terminal_cleanup_cleaned,
        history_recorded=history_recorded,
    )


def make_record_dict(**overrides):
    base = {
        "cycle_number": 1,
        "timestamp": "2026-07-14T00:00:00+00:00",
        "dry_run": False,
        "enqueue_scanned": 3,
        "enqueue_enqueued": 1,
        "enqueue_skipped_existing": 0,
        "enqueue_skipped_status": 1,
        "enqueue_skipped_history": 1,
        "enqueue_failed": 0,
        "scheduler_candidates": 1,
        "execution_executed": 1,
        "removal_removed": 0,
        "cleanup_cleaned": 0,
        "terminal_cleanup_cleaned": 0,
        "history_recorded": 1,
    }
    base.update(overrides)
    return base


# ═══════════════════════════════════════════════════════════
# テスト1: RetryRuntimeLogRecord Immutability
# ═══════════════════════════════════════════════════════════

print("[テスト1] RetryRuntimeLogRecordはフィールド再代入でFrozenInstanceErrorを送出する")
record_1 = make_record()
raised_1 = None
try:
    record_1.cycle_number = 999
except FrozenInstanceError as e:
    raised_1 = e
check_true("1. FrozenInstanceErrorが送出される", raised_1 is not None)
print()


# ═══════════════════════════════════════════════════════════
# テスト2-8: RetryRuntimeLogReader
# ═══════════════════════════════════════════════════════════

with tempfile.TemporaryDirectory() as tmpdir_2:
    print("[テスト2] 存在しないログファイルに対するread()は空リストを返す")
    reader_2 = RetryRuntimeLogReader(log_path=Path(tmpdir_2) / "does_not_exist.jsonl")
    records_2 = reader_2.read()
    check("2. 空リストが返る", records_2, [])
    print()

with tempfile.TemporaryDirectory() as tmpdir_3:
    log_path_3 = Path(tmpdir_3) / "retry_runtime_log.jsonl"
    log_path_3.write_text(
        json.dumps(make_record_dict(cycle_number=1)) + "\n"
        + json.dumps(make_record_dict(cycle_number=2)) + "\n",
        encoding="utf-8",
    )

    print("[テスト3] 正常なJSONL 2行を正しくRetryRuntimeLogRecordへ変換する")
    reader_3 = RetryRuntimeLogReader(log_path=log_path_3)
    records_3 = reader_3.read()
    check("3. 2件のRetryRuntimeLogRecordが返る", len(records_3), 2)
    check_true("3. 全件がRetryRuntimeLogRecord型", all(isinstance(r, RetryRuntimeLogRecord) for r in records_3))
    check("3. 1件目のcycle_numberが1", records_3[0].cycle_number, 1)
    check("3. 2件目のcycle_numberが2", records_3[1].cycle_number, 2)
    print()

with tempfile.TemporaryDirectory() as tmpdir_4:
    log_path_4 = Path(tmpdir_4) / "retry_runtime_log.jsonl"
    log_path_4.write_text(
        json.dumps(make_record_dict(cycle_number=1)) + "\n"
        + "{not valid json\n"
        + json.dumps(make_record_dict(cycle_number=2)) + "\n",
        encoding="utf-8",
    )

    print("[テスト4] 壊れたJSON行はスキップされ、正常な行のみ読み込まれる")
    reader_4 = RetryRuntimeLogReader(log_path=log_path_4)
    stderr_buf_4 = io.StringIO()
    with contextlib.redirect_stderr(stderr_buf_4):
        records_4 = reader_4.read()
    check("4. 正常な2件のみ読み込まれる", len(records_4), 2)
    check("4. 1件目のcycle_numberが1", records_4[0].cycle_number, 1)
    check("4. 2件目のcycle_numberが2", records_4[1].cycle_number, 2)
    print()

    print("[テスト5] 壊れた行に対しstderrへWARNINGが出力される")
    check_contains("5. stderrに\"WARNING\"が含まれる", stderr_buf_4.getvalue(), "WARNING")
    print()

with tempfile.TemporaryDirectory() as tmpdir_6:
    log_path_6 = Path(tmpdir_6) / "retry_runtime_log.jsonl"
    incomplete_dict = make_record_dict()
    del incomplete_dict["history_recorded"]
    log_path_6.write_text(
        json.dumps(make_record_dict(cycle_number=1)) + "\n"
        + json.dumps(incomplete_dict) + "\n"
        + json.dumps(make_record_dict(cycle_number=3)) + "\n",
        encoding="utf-8",
    )

    print("[テスト6] フィールド欠落行（KeyError相当）もスキップされる")
    reader_6 = RetryRuntimeLogReader(log_path=log_path_6)
    stderr_buf_6 = io.StringIO()
    with contextlib.redirect_stderr(stderr_buf_6):
        records_6 = reader_6.read()
    check("6. 正常な2件のみ読み込まれる", len(records_6), 2)
    check("6. 1件目のcycle_numberが1", records_6[0].cycle_number, 1)
    check("6. 2件目のcycle_numberが3", records_6[1].cycle_number, 3)
    check_contains("6. stderrに\"WARNING\"が含まれる", stderr_buf_6.getvalue(), "WARNING")
    print()

with tempfile.TemporaryDirectory() as tmpdir_7:
    log_path_7 = Path(tmpdir_7) / "retry_runtime_log.jsonl"
    log_path_7.write_text(
        json.dumps(make_record_dict(cycle_number=1)) + "\n"
        + "\n"
        + "   \n"
        + json.dumps(make_record_dict(cycle_number=2)) + "\n",
        encoding="utf-8",
    )

    print("[テスト7] 空行はスキップされる（読み込み結果に影響しない）")
    reader_7 = RetryRuntimeLogReader(log_path=log_path_7)
    records_7 = reader_7.read()
    check("7. 空行を除いた2件のみ読み込まれる", len(records_7), 2)
    print()

with tempfile.TemporaryDirectory() as tmpdir_8:
    # log_pathとしてディレクトリを渡すと、open()は「存在しない」のではなく
    # 「存在するが読めない」ため、Windows上ではPermissionErrorを送出する
    # （FileNotFoundErrorとは異なるOSErrorのサブクラス）。fail-fastの
    # 対象となる「ファイル自体が読めない」の代表例として使用する。
    unreadable_log_path_8 = Path(tmpdir_8) / "a_directory"
    unreadable_log_path_8.mkdir()

    print("[テスト8] ファイル自体が読めない場合は例外を送出する（fail-fast）")
    reader_8 = RetryRuntimeLogReader(log_path=unreadable_log_path_8)
    raised_8 = None
    try:
        reader_8.read()
    except OSError as e:
        raised_8 = e
    check_true("8. OSErrorが送出される", raised_8 is not None)
    check_true("8. FileNotFoundErrorではない（正常系との区別）", not isinstance(raised_8, FileNotFoundError))
    print()


# ═══════════════════════════════════════════════════════════
# テスト9-16: RetryMetricsCalculator
# ═══════════════════════════════════════════════════════════

print("[テスト9] calculate([])はcycle_count=0のSnapshotを返す（例外を送出しない）")
calculator = RetryMetricsCalculator()
raised_9 = None
snapshot_9 = None
try:
    snapshot_9 = calculator.calculate([])
except Exception as e:  # noqa: BLE001
    raised_9 = e
check("9. 例外が送出されない", raised_9, None)
check("9. cycle_count=0", snapshot_9.cycle_count, 0)
print()

print("[テスト10] calculate([])は全合計フィールドが0、period_start/endがNoneになる")
check("10. enqueue_scanned_total=0", snapshot_9.enqueue_scanned_total, 0)
check("10. enqueue_enqueued_total=0", snapshot_9.enqueue_enqueued_total, 0)
check("10. execution_executed_total=0", snapshot_9.execution_executed_total, 0)
check("10. history_recorded_total=0", snapshot_9.history_recorded_total, 0)
check("10. dry_run_cycle_count=0", snapshot_9.dry_run_cycle_count, 0)
check("10. period_startがNone", snapshot_9.period_start, None)
check("10. period_endがNone", snapshot_9.period_end, None)
print()

print("[テスト11] calculate([])はenqueue_success_ratioがNoneになる")
check("11. enqueue_success_ratioがNone", snapshot_9.enqueue_success_ratio, None)
print()

records_12 = [
    make_record(
        cycle_number=1, timestamp="2026-07-14T00:00:00+00:00", dry_run=False,
        enqueue_scanned=5, enqueue_enqueued=2, enqueue_skipped_existing=1,
        enqueue_skipped_status=1, enqueue_skipped_history=1, enqueue_failed=0,
        scheduler_candidates=2, execution_executed=2, removal_removed=1,
        cleanup_cleaned=1, terminal_cleanup_cleaned=0, history_recorded=2,
    ),
    make_record(
        cycle_number=2, timestamp="2026-07-14T00:01:00+00:00", dry_run=True,
        enqueue_scanned=3, enqueue_enqueued=1, enqueue_skipped_existing=0,
        enqueue_skipped_status=1, enqueue_skipped_history=1, enqueue_failed=0,
        scheduler_candidates=1, execution_executed=1, removal_removed=0,
        cleanup_cleaned=2, terminal_cleanup_cleaned=1, history_recorded=1,
    ),
]

print("[テスト12] calculate(records)は各合計フィールドが正しく計算される")
snapshot_12 = calculator.calculate(records_12)
check("12. cycle_count=2", snapshot_12.cycle_count, 2)
check("12. enqueue_scanned_total=8", snapshot_12.enqueue_scanned_total, 8)
check("12. enqueue_enqueued_total=3", snapshot_12.enqueue_enqueued_total, 3)
check("12. enqueue_skipped_existing_total=1", snapshot_12.enqueue_skipped_existing_total, 1)
check("12. enqueue_skipped_status_total=2", snapshot_12.enqueue_skipped_status_total, 2)
check("12. enqueue_skipped_history_total=2", snapshot_12.enqueue_skipped_history_total, 2)
check("12. enqueue_failed_total=0", snapshot_12.enqueue_failed_total, 0)
check("12. scheduler_candidates_total=3", snapshot_12.scheduler_candidates_total, 3)
check("12. execution_executed_total=3", snapshot_12.execution_executed_total, 3)
check("12. removal_removed_total=1", snapshot_12.removal_removed_total, 1)
check("12. cleanup_cleaned_total=3", snapshot_12.cleanup_cleaned_total, 3)
check("12. terminal_cleanup_cleaned_total=1", snapshot_12.terminal_cleanup_cleaned_total, 1)
check("12. history_recorded_total=3", snapshot_12.history_recorded_total, 3)
print()

print("[テスト13] calculate(records)はenqueue_success_ratioが正しく計算される")
check("13. enqueue_success_ratio=3/8", snapshot_12.enqueue_success_ratio, 3 / 8)
print()

records_14 = [make_record(enqueue_scanned=0, enqueue_enqueued=0)]
print("[テスト14] enqueue_scanned_total=0の場合、enqueue_success_ratioはNoneになる")
snapshot_14 = calculator.calculate(records_14)
check("14. enqueue_scanned_total=0", snapshot_14.enqueue_scanned_total, 0)
check("14. enqueue_success_ratioがNone", snapshot_14.enqueue_success_ratio, None)
print()

records_15 = [
    make_record(cycle_number=3, timestamp="2026-07-14T00:03:00+00:00"),
    make_record(cycle_number=1, timestamp="2026-07-14T00:01:00+00:00"),
    make_record(cycle_number=2, timestamp="2026-07-14T00:02:00+00:00"),
]
print("[テスト15] period_start/period_endはtimestampのmin/maxで算出される（リスト順序に依存しない）")
snapshot_15 = calculator.calculate(records_15)
check("15. period_startが最小timestamp", snapshot_15.period_start, "2026-07-14T00:01:00+00:00")
check("15. period_endが最大timestamp", snapshot_15.period_end, "2026-07-14T00:03:00+00:00")
print()

records_16 = [
    make_record(cycle_number=1, dry_run=True),
    make_record(cycle_number=2, dry_run=False),
    make_record(cycle_number=3, dry_run=True),
]
print("[テスト16] dry_run_cycle_countが正しく計算される")
snapshot_16 = calculator.calculate(records_16)
check("16. dry_run_cycle_count=2", snapshot_16.dry_run_cycle_count, 2)
print()


# ═══════════════════════════════════════════════════════════
# テスト17: RetryMetricsSnapshot Immutability
# ═══════════════════════════════════════════════════════════

print("[テスト17] RetryMetricsSnapshotはフィールド再代入でFrozenInstanceErrorを送出する")
raised_17 = None
try:
    snapshot_12.cycle_count = 999
except FrozenInstanceError as e:
    raised_17 = e
check_true("17. FrozenInstanceErrorが送出される", raised_17 is not None)
print()


# ═══════════════════════════════════════════════════════════
# テスト18: Dependency（Read Only Foundation確認）
# ═══════════════════════════════════════════════════════════

print("[テスト18] retry_metricsパッケージは他のretry_*パッケージをimportしない")
modules_18 = {
    "retry_runtime_log_record": inspect.getsource(_record_module),
    "retry_runtime_log_reader": inspect.getsource(_reader_module),
    "retry_metrics_snapshot": inspect.getsource(_snapshot_module),
    "retry_metrics_calculator": inspect.getsource(_calculator_module),
}
forbidden_imports = (
    "retry_runtime_logging", "retry_runtime_orchestrator", "retry_runtime_loop",
    "retry_runtime_shutdown", "retry_runtime_lock", "retry_engine",
    "retry_composition", "retry_queue", "retry_history", "retry_enqueue_trigger",
    "workflow_monitor", "workflow_engine", "scheduler", "execution_history",
)
for module_name, source in modules_18.items():
    for forbidden in forbidden_imports:
        # 実際のimport文（"import X" / "from X"）のみを検出する。単純な部分
        # 文字列一致だと、docstring中の説明文言や"scheduler_candidates"の
        # ようなJSON Schemaフィールド名（"scheduler"を含む）を誤検知するため。
        check_not_contains(f"18. {module_name}が{forbidden}をimportしない（import文）", source, f"import {forbidden}")
        check_not_contains(f"18. {module_name}が{forbidden}をimportしない（from文）", source, f"from {forbidden}")
print()


# ═══════════════════════════════════════════════════════════
# テスト19: 統合テスト（Read Only Foundation end-to-end）
# ═══════════════════════════════════════════════════════════

print("[テスト19] RetryRuntimeCycleLoggerと同じJSONL形式を読み取り、集計まで一貫して行える")
from retry_runtime_logging import RetryRuntimeCycleLogger
from retry_runtime_orchestrator import RetryRuntimeCycleResult
from retry_enqueue_trigger import RetryEnqueueTriggerResult

with tempfile.TemporaryDirectory() as tmpdir_19:
    log_path_19 = Path(tmpdir_19) / "retry_runtime_log.jsonl"
    writer_19 = RetryRuntimeCycleLogger(log_path=log_path_19)

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

    writer_19.log_cycle(cycle_number=1, result=make_cycle_result(scanned=4, enqueued=2), dry_run=False)
    writer_19.log_cycle(cycle_number=2, result=make_cycle_result(scanned=2, enqueued=2), dry_run=True)

    reader_19 = RetryRuntimeLogReader(log_path=log_path_19)
    records_19 = reader_19.read()
    check("19. 2件のRetryRuntimeLogRecordが読み取れる", len(records_19), 2)

    snapshot_19 = calculator.calculate(records_19)
    check("19. cycle_count=2", snapshot_19.cycle_count, 2)
    check("19. enqueue_scanned_total=6", snapshot_19.enqueue_scanned_total, 6)
    check("19. enqueue_enqueued_total=4", snapshot_19.enqueue_enqueued_total, 4)
    check("19. execution_executed_total=4", snapshot_19.execution_executed_total, 4)
    check("19. dry_run_cycle_count=1", snapshot_19.dry_run_cycle_count, 1)
    check("19. enqueue_success_ratio=4/6", snapshot_19.enqueue_success_ratio, 4 / 6)
print()


# ═══════════════════════════════════════════════════════════
# テスト20-27: Backward Compatibility / Zero Diff
# ═══════════════════════════════════════════════════════════

print("[テスト20-27] Runtime Pipeline関連コンポーネントに変更がないこと（git diff）")

unchanged_paths = [
    "src/retry_runtime_lock",
    "src/retry_runtime_shutdown",
    "src/retry_runtime_loop",
    "src/retry_runtime_orchestrator",
    "src/retry_engine",
    "src/retry_composition",
    "src/retry_runtime_logging",
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
        check_true(f"20-27. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("20-27. gitが利用できないため無変更確認をスキップ", True)
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
