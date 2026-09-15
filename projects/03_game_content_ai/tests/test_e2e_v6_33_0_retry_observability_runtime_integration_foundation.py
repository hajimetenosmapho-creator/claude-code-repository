"""
E2E テスト: v6.33.0 Retry Observability Runtime Integration Foundation

テストシナリオ（docs/design/retry_observability_runtime_integration_foundation.md
Rev.4、12章 E2E Test Strategy 対応）:

    ── A. RetryRuntimeObservabilityReporter（Full-History Semantics・失敗包含） ──
    1.  空ログ（ファイル不在）→ cycle_count=0・HEALTHY・NO_NOTIFICATION
    2.  複数cycle（25件）が全件evaluate()へ渡される（windowingなし、AD-1）
    3.  observe(): OSError（reader境界）が例外をそのまま伝播する（raw契約）
    4.  observe(): ValueError（evaluate境界）が例外をそのまま伝播する
    5.  observe_and_report(): 正常系でformatterの出力がコンソールへ表示される
    6.  observe_and_report(): reader OSError → 例外を伝播させず包含
    7.  observe_and_report(): evaluate ValueError → 例外を伝播させず包含
    8.  observe_and_report(): TypeError相当（不正recordによるcalculate()失敗）→ 包含
    9.  observe_and_report(): formatter例外 → 包含、report本体は出力されない
    10. observe_and_report(): report-output（print）例外 → 包含
    11. observe_and_report(): 両方failure（formatter失敗＋stderr出力失敗）→ 伝播なし
    12. observe_and_report(): outのcall-time解決（redirect_stdoutでcapture可能）

    ── A'. BaseException Non-Containment（Round 3 M-1対応） ──
    13-14. reader境界でSystemExit／KeyboardInterruptが非containのまま伝播する
    15-16. evaluate境界でSystemExit／KeyboardInterruptが非containのまま伝播する
    17-18. format境界でSystemExit／KeyboardInterruptが非containのまま伝播する
    19-20. report-output境界でSystemExit／KeyboardInterruptが非containのまま伝播する

    ── B. _warn_best_effort()（retry_runtime_observability側）単体 ──
    21. 正常系：prefix + str(exc) がstderrへ出力される
    22. message formatting失敗（__str__が例外）→ 伝播せずreturn
    23. stderr output失敗（fake streamのwrite()が例外）→ 伝播せずreturn
    24-25. message formatting境界でSystemExit／KeyboardInterruptが非contain
    26-27. stderr output境界でSystemExit／KeyboardInterruptが非contain

    ── C. RetryRuntimeCycleLogger.log_cycle() bool契約（AD-3） ──
    28. 成功時 True を返す
    29. OSError捕捉時 False を返す（既存の「例外を送出しない」契約は無変更）
    30. 本ファイル内_warn_best_effort()単体：正常系・message formatting失敗・
        stderr output失敗のいずれも伝播しない
    31. 両方failure（書き込み不可パス＋stderr出力failure）→ 例外を送出せずFalseを返す
    32-33. 本ファイル内_warn_best_effort()：message formatting／stderr output
        境界でSystemExit／KeyboardInterruptが非contain
    34. 2ファイルへ複製された_warn_best_effort()が同一exc・同一fake streamに対し
        同一のWARNING文字列を出力する（実装差異がないことの確認）

    ── D. Runtime統合（scripts/run_retry_runtime.py） ──
    35. run_cycle()実行後、log_cycle()がTrueを返す場合のみobserve_and_report()が
        呼ばれ、かつlog_cycle()より後に呼ばれる（呼び出し順序）
    36. log_cycle()がFalseを返す場合、observe_and_report()が一切呼ばれない
        （Current-Cycle Inclusion Contract）
    37. observe_and_report()が呼ばれた場合、formatterの出力が標準出力に含まれる
    38. main()のソースに新規配線（log_write_succeeded・observe_and_report）が
        含まれる
    39. --loop実行時、log_cycle()の戻り値に応じてcycleごとに
        observe_and_report()の呼び出し有無が切り替わる

    ── E. Architecture Guard（AST、8.2節） ──
    40. retry_runtime_observabilityが禁止packageをいずれもimportしない
    41. 既存retry判断packageがretry_runtime_observabilityをimportしていない
        （Reverse Dependency禁止）
    42. retry_runtime_observabilityのソース中にRetryManager等への参照がない

    ── F. Zero-Diff / Formal Regression ──
    43. src/retry_engine・retry_lineage・retry_queue・retry_history・scheduler
        に対するgit diffが0である
    44. zero_diff_guard_registry.pyのallowed_source_changes_for("v6.33.0")に
        scripts寄与（run_retry_runtime.py・show_retry_notification.py）が
        含まれる

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_33_0_retry_observability_runtime_integration_foundation.py
"""
from __future__ import annotations

import ast
import contextlib
import hashlib
import importlib.util
import inspect
import io
import json
import subprocess
import sys
import tempfile
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


def check_contains(label: str, text, keyword: str):
    check(label, keyword in str(text), True)


def check_not_contains(label: str, text, keyword: str):
    check(label, keyword in str(text), False)


print("=" * 60)
print("v6.33.0 Retry Observability Runtime Integration Foundation E2E テスト")
print("=" * 60)
print()

from retry_metrics import RetryRuntimeLogReader, RetryRuntimeLogRecord
from retry_observability_pipeline import RetryObservabilityPipeline, RetryObservabilityReport
from retry_runtime_observability import RetryRuntimeObservabilityReporter
import retry_runtime_observability.retry_runtime_observability_reporter as _reporter_module
import retry_runtime_logging.retry_runtime_cycle_logger as _cycle_logger_module
from retry_runtime_logging import RetryRuntimeCycleLogger
from retry_runtime_orchestrator import RetryRuntimeCycleResult
from retry_enqueue_trigger import RetryEnqueueTriggerResult

RETRY_RUNTIME_OBSERVABILITY_DIR = PROJECT_ROOT / "src" / "retry_runtime_observability"


# ─── Fixture Helper ───


def make_record_dict(cycle_number: int, timestamp: str, enqueue_scanned=1, enqueue_enqueued=1) -> dict:
    return {
        "cycle_number": cycle_number,
        "timestamp": timestamp,
        "dry_run": False,
        "enqueue_scanned": enqueue_scanned,
        "enqueue_enqueued": enqueue_enqueued,
        "enqueue_skipped_existing": 0,
        "enqueue_skipped_status": 0,
        "enqueue_skipped_history": 0,
        "enqueue_failed": 0,
        "scheduler_candidates": 0,
        "execution_executed": 0,
        "removal_removed": 0,
        "cleanup_cleaned": 0,
        "terminal_cleanup_cleaned": 0,
        "history_recorded": 0,
    }


def write_jsonl_records(path: Path, count: int) -> None:
    lines = [
        json.dumps(make_record_dict(i, f"2026-07-{(i % 28) + 1:02d}T00:00:00+00:00"))
        for i in range(1, count + 1)
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def make_record(cycle_number: int, enqueue_scanned: int, enqueue_enqueued: int) -> RetryRuntimeLogRecord:
    return RetryRuntimeLogRecord(
        cycle_number=cycle_number,
        timestamp="2026-07-14T00:00:00+00:00",
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


class _CapturingPipeline:
    """入力recordsの内容を記録しつつ、実Pipelineへそのまま委譲するFake。"""

    def __init__(self):
        self.received = None
        self._real = RetryObservabilityPipeline()

    def evaluate(self, records):
        self.received = list(records)
        return self._real.evaluate(records)


class _RaisingPipeline:
    def __init__(self, exc_factory):
        self._exc_factory = exc_factory

    def evaluate(self, records):
        raise self._exc_factory()


class _FakeWriteRaisingStream:
    """write()が指定した例外を送出するだけのfake stream（file=引数として渡す用）。"""

    def __init__(self, exc_factory):
        self._exc_factory = exc_factory

    def write(self, _text):
        raise self._exc_factory()

    def flush(self):
        pass


class _BadStrException(Exception):
    """__str__自体が例外を送出する、message formatting失敗を模擬するためのFake例外。"""

    def __init__(self, exc_factory):
        super().__init__("bad-str-exception")
        self._exc_factory = exc_factory

    def __str__(self):
        raise self._exc_factory()


EMPTY_REPORT = RetryObservabilityPipeline().evaluate([])


def sample_formatter(report: RetryObservabilityReport) -> str:
    return f"cycle_count={report.metrics.cycle_count} status={report.health_report.status.value}"


def raising_formatter(_report: RetryObservabilityReport) -> str:
    raise RuntimeError("formatter boom")


# ═══════════════════════════════════════════════════════════
# テスト1-2: Full-History Semantics（AD-1）
# ═══════════════════════════════════════════════════════════
print("[テスト1] 空ログ（ファイル不在）→ cycle_count=0・HEALTHY・NO_NOTIFICATION")
with tempfile.TemporaryDirectory() as _tmp:
    _missing_path = Path(_tmp) / "does_not_exist.jsonl"
    _reporter_1 = RetryRuntimeObservabilityReporter(log_path=_missing_path)
    _report_1 = _reporter_1.observe()
check("1. cycle_count == 0", _report_1.metrics.cycle_count, 0)
check_true("1. HEALTHY", _report_1.health_report.status.value == "HEALTHY")
check_true("1. NO_NOTIFICATION", _report_1.notification_decision.status.value == "NO_NOTIFICATION")
print()

print("[テスト2] 複数cycle（25件）が全件evaluate()へ渡される（windowingなし、AD-1）")
with tempfile.TemporaryDirectory() as _tmp:
    _many_path = Path(_tmp) / "many.jsonl"
    write_jsonl_records(_many_path, 25)
    _capturing_pipeline_2 = _CapturingPipeline()
    _reporter_2 = RetryRuntimeObservabilityReporter(log_path=_many_path, pipeline=_capturing_pipeline_2)
    _report_2 = _reporter_2.observe()
check("2. evaluate()へ渡されたrecords件数は25（全件）", len(_capturing_pipeline_2.received), 25)
check("2. metrics.cycle_countも25", _report_2.metrics.cycle_count, 25)
check(
    "2. 渡されたrecordsのcycle_numberが1〜25全件を含む（windowingで切り捨てられていない）",
    sorted(r.cycle_number for r in _capturing_pipeline_2.received),
    list(range(1, 26)),
)
print()


# ═══════════════════════════════════════════════════════════
# テスト3-4: observe() raw契約（例外はそのまま伝播）
# ═══════════════════════════════════════════════════════════
print("[テスト3] observe(): OSError（reader境界）が例外をそのまま伝播する")
with tempfile.TemporaryDirectory() as _tmp:
    _path_3 = Path(_tmp) / "x.jsonl"
    _reporter_3 = RetryRuntimeObservabilityReporter(log_path=_path_3)
    with mock.patch.object(RetryRuntimeLogReader, "read", side_effect=OSError("reader boom")):
        _raised_3 = None
        try:
            _reporter_3.observe()
        except OSError as e:
            _raised_3 = e
check_true("3. OSErrorがそのまま伝播する", _raised_3 is not None)
print()

print("[テスト4] observe(): ValueError（evaluate境界）が例外をそのまま伝播する")
with tempfile.TemporaryDirectory() as _tmp:
    _path_4 = Path(_tmp) / "x.jsonl"
    _reporter_4 = RetryRuntimeObservabilityReporter(
        log_path=_path_4, pipeline=_RaisingPipeline(lambda: ValueError("evaluate boom")),
    )
    _raised_4 = None
    try:
        _reporter_4.observe()
    except ValueError as e:
        _raised_4 = e
check_true("4. ValueErrorがそのまま伝播する", _raised_4 is not None)
print()


# ═══════════════════════════════════════════════════════════
# テスト5-12: observe_and_report() 失敗包含境界（AD-4）
# ═══════════════════════════════════════════════════════════
print("[テスト5] observe_and_report(): 正常系でformatterの出力がコンソールへ表示される")
with tempfile.TemporaryDirectory() as _tmp:
    _path_5 = Path(_tmp) / "x.jsonl"
    _reporter_5 = RetryRuntimeObservabilityReporter(log_path=_path_5)
    _buf_5 = io.StringIO()
    _reporter_5.observe_and_report(sample_formatter, out=_buf_5)
check_contains("5. 出力にcycle_count=0が含まれる", _buf_5.getvalue(), "cycle_count=0")
check_contains("5. 出力にstatus=HEALTHYが含まれる", _buf_5.getvalue(), "status=HEALTHY")
print()

print("[テスト6] observe_and_report(): reader OSError → 例外を伝播させず包含")
with tempfile.TemporaryDirectory() as _tmp:
    _path_6 = Path(_tmp) / "x.jsonl"
    _reporter_6 = RetryRuntimeObservabilityReporter(log_path=_path_6)
    _stderr_6 = io.StringIO()
    _raised_6 = None
    with mock.patch.object(RetryRuntimeLogReader, "read", side_effect=OSError("reader boom")):
        try:
            with contextlib.redirect_stderr(_stderr_6):
                _reporter_6.observe_and_report(sample_formatter)
        except Exception as e:  # noqa: BLE001
            _raised_6 = e
check("6. 例外が伝播しない", _raised_6, None)
check_contains("6. stderrにWARNING", _stderr_6.getvalue(), "WARNING")
print()

print("[テスト7] observe_and_report(): evaluate ValueError → 例外を伝播させず包含")
with tempfile.TemporaryDirectory() as _tmp:
    _path_7 = Path(_tmp) / "x.jsonl"
    _reporter_7 = RetryRuntimeObservabilityReporter(
        log_path=_path_7, pipeline=_RaisingPipeline(lambda: ValueError("evaluate boom")),
    )
    _stderr_7 = io.StringIO()
    _raised_7 = None
    try:
        with contextlib.redirect_stderr(_stderr_7):
            _reporter_7.observe_and_report(sample_formatter)
    except Exception as e:  # noqa: BLE001
        _raised_7 = e
check("7. 例外が伝播しない", _raised_7, None)
check_contains("7. stderrにWARNING", _stderr_7.getvalue(), "WARNING")
print()

print("[テスト8] observe_and_report(): TypeError相当（calculate()失敗）→ 包含")
with tempfile.TemporaryDirectory() as _tmp:
    _path_8 = Path(_tmp) / "x.jsonl"
    _reporter_8 = RetryRuntimeObservabilityReporter(
        log_path=_path_8, pipeline=_RaisingPipeline(lambda: TypeError("calculate boom")),
    )
    _stderr_8 = io.StringIO()
    _raised_8 = None
    try:
        with contextlib.redirect_stderr(_stderr_8):
            _reporter_8.observe_and_report(sample_formatter)
    except Exception as e:  # noqa: BLE001
        _raised_8 = e
check("8. 例外が伝播しない", _raised_8, None)
check_contains("8. stderrにWARNING", _stderr_8.getvalue(), "WARNING")
print()

print("[テスト9] observe_and_report(): formatter例外 → 包含、report本体は出力されない")
with tempfile.TemporaryDirectory() as _tmp:
    _path_9 = Path(_tmp) / "x.jsonl"
    _reporter_9 = RetryRuntimeObservabilityReporter(log_path=_path_9)
    _stdout_9, _stderr_9 = io.StringIO(), io.StringIO()
    _raised_9 = None
    try:
        with contextlib.redirect_stderr(_stderr_9):
            _reporter_9.observe_and_report(raising_formatter, out=_stdout_9)
    except Exception as e:  # noqa: BLE001
        _raised_9 = e
check("9. 例外が伝播しない", _raised_9, None)
check("9. stdoutは空（report本体が出力されない）", _stdout_9.getvalue(), "")
check_contains("9. stderrにWARNING", _stderr_9.getvalue(), "WARNING")
print()

print("[テスト10] observe_and_report(): report-output（print）例外 → 包含")
with tempfile.TemporaryDirectory() as _tmp:
    _path_10 = Path(_tmp) / "x.jsonl"
    _reporter_10 = RetryRuntimeObservabilityReporter(log_path=_path_10)
    _stderr_10 = io.StringIO()
    _raised_10 = None
    try:
        with contextlib.redirect_stderr(_stderr_10):
            _reporter_10.observe_and_report(sample_formatter, out=_FakeWriteRaisingStream(lambda: OSError("io boom")))
    except Exception as e:  # noqa: BLE001
        _raised_10 = e
check("10. 例外が伝播しない", _raised_10, None)
check_contains("10. stderrにWARNING", _stderr_10.getvalue(), "WARNING")
print()

print("[テスト11] observe_and_report(): 両方failure（formatter失敗＋stderr出力failure）→ 伝播なし")
with tempfile.TemporaryDirectory() as _tmp:
    _path_11 = Path(_tmp) / "x.jsonl"
    _reporter_11 = RetryRuntimeObservabilityReporter(log_path=_path_11)
    _raised_11 = None
    with mock.patch.object(sys, "stderr", _FakeWriteRaisingStream(lambda: OSError("stderr boom"))):
        try:
            _reporter_11.observe_and_report(raising_formatter)
        except Exception as e:  # noqa: BLE001
            _raised_11 = e
check("11. 二重障害でも例外が伝播しない", _raised_11, None)
print()

print("[テスト12] observe_and_report(): outのcall-time解決（redirect_stdoutでcapture可能）")
with tempfile.TemporaryDirectory() as _tmp:
    _path_12 = Path(_tmp) / "x.jsonl"
    _reporter_12 = RetryRuntimeObservabilityReporter(log_path=_path_12)
    _stdout_12 = io.StringIO()
    with contextlib.redirect_stdout(_stdout_12):
        _reporter_12.observe_and_report(sample_formatter)
check_contains("12. redirect_stdout先へcaptureされる", _stdout_12.getvalue(), "cycle_count=0")
print()


# ═══════════════════════════════════════════════════════════
# テスト13-20: BaseException Non-Containment（Round 3 M-1対応）
# ═══════════════════════════════════════════════════════════
for _label, _exc_cls in (("SystemExit", SystemExit), ("KeyboardInterrupt", KeyboardInterrupt)):
    print(f"[テスト13/15/17/19系] observe_and_report(): reader境界で{_label}が非containのまま伝播する")
    with tempfile.TemporaryDirectory() as _tmp:
        _path = Path(_tmp) / "x.jsonl"
        _reporter = RetryRuntimeObservabilityReporter(log_path=_path)
        _propagated = False
        with mock.patch.object(RetryRuntimeLogReader, "read", side_effect=_exc_cls("boom")):
            try:
                _reporter.observe_and_report(sample_formatter)
            except _exc_cls:
                _propagated = True
    check_true(f"reader境界: {_label}が伝播する", _propagated)
    print()

    print(f"[テスト系] observe_and_report(): evaluate境界で{_label}が非containのまま伝播する")
    with tempfile.TemporaryDirectory() as _tmp:
        _path = Path(_tmp) / "x.jsonl"
        _reporter = RetryRuntimeObservabilityReporter(
            log_path=_path, pipeline=_RaisingPipeline(lambda ec=_exc_cls: ec("boom")),
        )
        _propagated = False
        try:
            _reporter.observe_and_report(sample_formatter)
        except _exc_cls:
            _propagated = True
    check_true(f"evaluate境界: {_label}が伝播する", _propagated)
    print()

    print(f"[テスト系] observe_and_report(): format境界で{_label}が非containのまま伝播する")

    def _raising_formatter_base(_report, ec=_exc_cls):
        raise ec("boom")

    with tempfile.TemporaryDirectory() as _tmp:
        _path = Path(_tmp) / "x.jsonl"
        _reporter = RetryRuntimeObservabilityReporter(log_path=_path)
        _propagated = False
        try:
            _reporter.observe_and_report(_raising_formatter_base)
        except _exc_cls:
            _propagated = True
    check_true(f"format境界: {_label}が伝播する", _propagated)
    print()

    print(f"[テスト系] observe_and_report(): report-output境界で{_label}が非containのまま伝播する")
    with tempfile.TemporaryDirectory() as _tmp:
        _path = Path(_tmp) / "x.jsonl"
        _reporter = RetryRuntimeObservabilityReporter(log_path=_path)
        _propagated = False
        try:
            _reporter.observe_and_report(sample_formatter, out=_FakeWriteRaisingStream(lambda ec=_exc_cls: ec("boom")))
        except _exc_cls:
            _propagated = True
    check_true(f"report-output境界: {_label}が伝播する", _propagated)
    print()


# ═══════════════════════════════════════════════════════════
# テスト21-27: _warn_best_effort()（retry_runtime_observability側）単体
# ═══════════════════════════════════════════════════════════
print("[テスト21] _warn_best_effort(): 正常系でprefix + str(exc)がstderrへ出力される")
_stderr_21 = io.StringIO()
with contextlib.redirect_stderr(_stderr_21):
    _reporter_module._warn_best_effort("prefix-21", RuntimeError("boom-21"))
check_contains("21. WARNINGが含まれる", _stderr_21.getvalue(), "WARNING")
check_contains("21. prefixが含まれる", _stderr_21.getvalue(), "prefix-21")
check_contains("21. exc本文が含まれる", _stderr_21.getvalue(), "boom-21")
print()

print("[テスト22] _warn_best_effort(): message formatting失敗（__str__が例外）→ 伝播せずreturn")
_raised_22 = None
try:
    _reporter_module._warn_best_effort("prefix-22", _BadStrException(lambda: RuntimeError("str boom")))
except Exception as e:  # noqa: BLE001
    _raised_22 = e
check("22. 例外が伝播しない", _raised_22, None)
print()

print("[テスト23] _warn_best_effort(): stderr output失敗（fake streamのwrite()が例外）→ 伝播せずreturn")
_raised_23 = None
with mock.patch.object(sys, "stderr", _FakeWriteRaisingStream(lambda: OSError("stderr boom"))):
    try:
        _reporter_module._warn_best_effort("prefix-23", RuntimeError("boom-23"))
    except Exception as e:  # noqa: BLE001
        _raised_23 = e
check("23. 例外が伝播しない", _raised_23, None)
print()

for _label, _exc_cls in (("SystemExit", SystemExit), ("KeyboardInterrupt", KeyboardInterrupt)):
    print(f"[テスト系] _warn_best_effort(): message formatting境界で{_label}が非contain")
    _propagated = False
    try:
        _reporter_module._warn_best_effort("prefix", _BadStrException(lambda ec=_exc_cls: ec("boom")))
    except _exc_cls:
        _propagated = True
    check_true(f"message formatting境界: {_label}が伝播する", _propagated)
    print()

    print(f"[テスト系] _warn_best_effort(): stderr output境界で{_label}が非contain")
    _propagated = False
    with mock.patch.object(sys, "stderr", _FakeWriteRaisingStream(lambda ec=_exc_cls: ec("boom"))):
        try:
            _reporter_module._warn_best_effort("prefix", RuntimeError("boom"))
        except _exc_cls:
            _propagated = True
    check_true(f"stderr output境界: {_label}が伝播する", _propagated)
    print()


# ═══════════════════════════════════════════════════════════
# テスト28-34: RetryRuntimeCycleLogger.log_cycle() bool契約（AD-3）
# ═══════════════════════════════════════════════════════════

def make_result(scanned=3, enqueued=1) -> RetryRuntimeCycleResult:
    trigger_result = RetryEnqueueTriggerResult(
        scanned=scanned, enqueued=enqueued, skipped_existing=0, skipped_status=0, failed=0,
    )
    return RetryRuntimeCycleResult(
        trigger_result=trigger_result,
        scheduler_events=[], execution_results=[], removal_results=[],
        cleanup_results=[], terminal_cleanup_results=[], history_results=[],
    )


print("[テスト28] log_cycle(): 成功時 True を返す")
with tempfile.TemporaryDirectory() as _tmp:
    _log_path_28 = Path(_tmp) / "log.jsonl"
    _logger_28 = RetryRuntimeCycleLogger(log_path=_log_path_28)
    _result_28 = _logger_28.log_cycle(cycle_number=1, result=make_result())
check("28. Trueを返す", _result_28, True)
print()

print("[テスト29] log_cycle(): OSError捕捉時 False を返す（既存の「例外を送出しない」契約は無変更）")
with tempfile.TemporaryDirectory() as _tmp:
    _blocking_file_29 = Path(_tmp) / "not_a_directory"
    _blocking_file_29.write_text("x", encoding="utf-8")
    _unwritable_log_path_29 = _blocking_file_29 / "retry_runtime_log.jsonl"
    _logger_29 = RetryRuntimeCycleLogger(log_path=_unwritable_log_path_29)
    _stderr_29 = io.StringIO()
    _raised_29 = None
    _result_29 = None
    try:
        with contextlib.redirect_stderr(_stderr_29):
            _result_29 = _logger_29.log_cycle(cycle_number=1, result=make_result())
    except Exception as e:  # noqa: BLE001
        _raised_29 = e
check("29. 例外を送出しない", _raised_29, None)
check("29. Falseを返す", _result_29, False)
check_contains("29. stderrにWARNING", _stderr_29.getvalue(), "WARNING")
print()

print("[テスト30] 本ファイル内_warn_best_effort()単体：正常系・message formatting失敗・stderr output失敗のいずれも伝播しない")
_stderr_30 = io.StringIO()
with contextlib.redirect_stderr(_stderr_30):
    _cycle_logger_module._warn_best_effort("prefix-30", RuntimeError("boom-30"))
check_contains("30. 正常系でWARNINGが出力される", _stderr_30.getvalue(), "WARNING")

_raised_30b = None
try:
    _cycle_logger_module._warn_best_effort("prefix-30b", _BadStrException(lambda: RuntimeError("boom")))
except Exception as e:  # noqa: BLE001
    _raised_30b = e
check("30. message formatting失敗でも伝播しない", _raised_30b, None)

_raised_30c = None
with mock.patch.object(sys, "stderr", _FakeWriteRaisingStream(lambda: OSError("boom"))):
    try:
        _cycle_logger_module._warn_best_effort("prefix-30c", RuntimeError("boom"))
    except Exception as e:  # noqa: BLE001
        _raised_30c = e
check("30. stderr output失敗でも伝播しない", _raised_30c, None)
print()

print("[テスト31] log_cycle(): 両方failure（書き込み不可パス＋stderr出力failure）→ 例外を送出せずFalseを返す")
with tempfile.TemporaryDirectory() as _tmp:
    _blocking_file_31 = Path(_tmp) / "not_a_directory"
    _blocking_file_31.write_text("x", encoding="utf-8")
    _unwritable_log_path_31 = _blocking_file_31 / "retry_runtime_log.jsonl"
    _logger_31 = RetryRuntimeCycleLogger(log_path=_unwritable_log_path_31)
    _raised_31 = None
    _result_31 = None
    with mock.patch.object(sys, "stderr", _FakeWriteRaisingStream(lambda: OSError("stderr boom"))):
        try:
            _result_31 = _logger_31.log_cycle(cycle_number=1, result=make_result())
        except Exception as e:  # noqa: BLE001
            _raised_31 = e
check("31. 二重障害でも例外を送出しない", _raised_31, None)
check("31. Falseを返す", _result_31, False)
print()

for _label, _exc_cls in (("SystemExit", SystemExit), ("KeyboardInterrupt", KeyboardInterrupt)):
    print(f"[テスト系] 本ファイル内_warn_best_effort(): message formatting境界で{_label}が非contain")
    _propagated = False
    try:
        _cycle_logger_module._warn_best_effort("prefix", _BadStrException(lambda ec=_exc_cls: ec("boom")))
    except _exc_cls:
        _propagated = True
    check_true(f"32/33系: message formatting境界: {_label}が伝播する", _propagated)
    print()

    print(f"[テスト系] 本ファイル内_warn_best_effort(): stderr output境界で{_label}が非contain")
    _propagated = False
    with mock.patch.object(sys, "stderr", _FakeWriteRaisingStream(lambda ec=_exc_cls: ec("boom"))):
        try:
            _cycle_logger_module._warn_best_effort("prefix", RuntimeError("boom"))
        except _exc_cls:
            _propagated = True
    check_true(f"32/33系: stderr output境界: {_label}が伝播する", _propagated)
    print()

print("[テスト34] 2ファイルへ複製された_warn_best_effort()が同一exc・同一fake streamに対し同一のWARNING文字列を出力する")
_stderr_34a, _stderr_34b = io.StringIO(), io.StringIO()
with contextlib.redirect_stderr(_stderr_34a):
    _reporter_module._warn_best_effort("Failed to produce retry observability report", RuntimeError("shared-boom"))
with contextlib.redirect_stderr(_stderr_34b):
    _cycle_logger_module._warn_best_effort("Failed to produce retry observability report", RuntimeError("shared-boom"))
check(
    "34. 両ファイルのWARNING出力文字列が一致する",
    _stderr_34a.getvalue(),
    _stderr_34b.getvalue(),
)
print()


# ═══════════════════════════════════════════════════════════
# テスト35-39: Runtime統合（scripts/run_retry_runtime.py）
# ═══════════════════════════════════════════════════════════

SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_retry_runtime.py"
REAL_LOCK_PATH = PROJECT_ROOT / ".run" / "retry_runtime.lock"

_spec = importlib.util.spec_from_file_location("run_retry_runtime_v6_33_e2e", SCRIPT_PATH)
run_retry_runtime = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(run_retry_runtime)

_result_sample = make_result(scanned=1, enqueued=0)

_CALL_ORDER_LOG: list = []


class _FakeLock:
    """
    RetryRuntimeLockをテスト全体で差し替えるFake（Lock Safety対応）。

    __enter__/__exit__のみを提供するno-op context managerであり、
    ファイルシステムへは一切触れない（open()・os.open()・unlink()・write()の
    いずれも呼ばない）。run_retry_runtime.RetryRuntimeLockをこのクラスへ
    差し替えることで、main()が実project直下の.run/retry_runtime.lockを
    参照するコード自体（_PROJECT_ROOT基準の固定パス、production側は無変更）
    はそのまま実行しつつ、実ファイルへの実際のI/O（作成・削除・上書き）が
    一切発生しないことを保証する。既存の注入seam（run_retry_runtime module
    属性の差し替え。他のFake（_FakeCompositionRoot等）と同型）を利用するのみで、
    production code・lock pathの構築ロジックは無変更。
    """

    acquired_paths: list = []

    def __init__(self, lock_path):
        self.lock_path = lock_path
        _FakeLock.acquired_paths.append(lock_path)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return False


class _FakeRoot:
    pass


class _FakeCompositionRoot:
    @staticmethod
    def from_env():
        return _FakeRoot()


class _FakeOrchestrator:
    def __init__(self):
        pass

    @classmethod
    def from_composition_root(cls, root):
        return cls()

    def run_once(self, dry_run: bool = False):
        _CALL_ORDER_LOG.append("run_once")
        return _result_sample


class _FakeCycleLoggerBool:
    instances: list = []
    next_return_values: list = []

    def __init__(self, log_path):
        self.log_path = log_path
        self.calls: list = []
        _FakeCycleLoggerBool.instances.append(self)

    def log_cycle(self, cycle_number, result, dry_run=False):
        self.calls.append({"cycle_number": cycle_number, "result": result, "dry_run": dry_run})
        _CALL_ORDER_LOG.append("log_cycle")
        if _FakeCycleLoggerBool.next_return_values:
            return _FakeCycleLoggerBool.next_return_values.pop(0)
        return True


class _FakeObservabilityReporter:
    instances: list = []

    def __init__(self, log_path, pipeline=None):
        self.log_path = log_path
        self.calls: list = []
        _FakeObservabilityReporter.instances.append(self)

    def observe_and_report(self, formatter, out=None):
        self.calls.append({"formatter": formatter})
        _CALL_ORDER_LOG.append("observe_and_report")
        print(formatter(EMPTY_REPORT), file=out)


class _FakeShutdown:
    instances: list = []

    def __init__(self, poll_interval_seconds: float = 0.5):
        self.installed = False
        self.uninstalled = False
        self.sleep_calls: list = []
        self.stop_after_sleep_calls = None
        self._requested = False
        self._signal_name = None
        _FakeShutdown.instances.append(self)

    def install(self) -> None:
        self.installed = True

    def uninstall(self) -> None:
        self.uninstalled = True

    @property
    def requested(self) -> bool:
        return self._requested

    @property
    def signal_name(self):
        return self._signal_name

    def should_continue(self) -> bool:
        return not self._requested

    def interruptible_sleep(self, seconds: float) -> None:
        self.sleep_calls.append(seconds)
        if self.stop_after_sleep_calls is not None and len(self.sleep_calls) >= self.stop_after_sleep_calls:
            self._requested = True
            self._signal_name = "FAKE_SIGNAL"


def run_main_with_argv(argv, stop_after_sleep_calls=1, log_cycle_return_values=None):
    _FakeCycleLoggerBool.instances = []
    _FakeCycleLoggerBool.next_return_values = list(log_cycle_return_values) if log_cycle_return_values else []
    _FakeObservabilityReporter.instances = []
    _FakeShutdown.instances = []
    _CALL_ORDER_LOG.clear()
    original_root = run_retry_runtime.RetryCompositionRoot
    original_orchestrator = run_retry_runtime.RetryRuntimeOrchestrator
    original_shutdown_cls = run_retry_runtime.RetryRuntimeShutdown
    original_logger_cls = run_retry_runtime.RetryRuntimeCycleLogger
    original_reporter_cls = run_retry_runtime.RetryRuntimeObservabilityReporter
    original_lock_cls = run_retry_runtime.RetryRuntimeLock
    original_argv = sys.argv

    def _shutdown_factory(*args, **kwargs):
        fake = _FakeShutdown()
        fake.stop_after_sleep_calls = stop_after_sleep_calls
        return fake

    run_retry_runtime.RetryCompositionRoot = _FakeCompositionRoot
    run_retry_runtime.RetryRuntimeOrchestrator = _FakeOrchestrator
    run_retry_runtime.RetryRuntimeShutdown = _shutdown_factory
    run_retry_runtime.RetryRuntimeCycleLogger = _FakeCycleLoggerBool
    run_retry_runtime.RetryRuntimeObservabilityReporter = _FakeObservabilityReporter
    # Lock Safety（Round 1 Code Review MAJOR-2対応）：RetryRuntimeLockをFakeへ
    # 差し替え、main()内部のlock_path構築ロジック（production code、無変更）が
    # 実project直下の.run/retry_runtime.lockを指し続けていても、実際の
    # ファイルI/O（作成・削除・上書き）が一切発生しないようにする。
    run_retry_runtime.RetryRuntimeLock = _FakeLock
    sys.argv = ["run_retry_runtime.py"] + argv
    buf = io.StringIO()
    raised = None
    try:
        with contextlib.redirect_stdout(buf):
            run_retry_runtime.main()
    except BaseException as exc:  # noqa: BLE001 - テストヘルパーとして意図的に全例外を捕捉
        raised = exc
    finally:
        run_retry_runtime.RetryCompositionRoot = original_root
        run_retry_runtime.RetryRuntimeOrchestrator = original_orchestrator
        run_retry_runtime.RetryRuntimeShutdown = original_shutdown_cls
        run_retry_runtime.RetryRuntimeCycleLogger = original_logger_cls
        run_retry_runtime.RetryRuntimeObservabilityReporter = original_reporter_cls
        run_retry_runtime.RetryRuntimeLock = original_lock_cls
        sys.argv = original_argv
    return buf.getvalue(), raised


print("[テスト35] run_cycle()実行後、実際のイベント順序がrun_once→log_cycle→observe_and_reportの厳密な順序であること")
_stdout_35, _raised_35 = run_main_with_argv([], stop_after_sleep_calls=1)
check("35. 例外が伝播しない", _raised_35, None)
check("35. FakeCycleLoggerが1回呼ばれる", len(_FakeCycleLoggerBool.instances[0].calls), 1)
check("35. FakeObservabilityReporterが1回呼ばれる", len(_FakeObservabilityReporter.instances[0].calls), 1)
check(
    "35. イベント順序がrun_once→log_cycle→observe_and_reportの厳密な順序（共有event logで検証、Round 1 MINOR-1対応）",
    list(_CALL_ORDER_LOG),
    ["run_once", "log_cycle", "observe_and_report"],
)
print()

print("[テスト36] log_cycle()がFalseを返す場合、observe_and_report()がevent logへ一切現れない（Current-Cycle Inclusion Contract）")
_stdout_36, _raised_36 = run_main_with_argv([], stop_after_sleep_calls=1, log_cycle_return_values=[False])
check("36. 例外が伝播しない", _raised_36, None)
check("36. log_cycle()は1回呼ばれる", len(_FakeCycleLoggerBool.instances[0].calls), 1)
check("36. observe_and_report()は一切呼ばれない", len(_FakeObservabilityReporter.instances[0].calls), 0)
check(
    "36. イベント順序はrun_once→log_cycleのみでobserve_and_reportを含まない（Round 1 MINOR-1対応）",
    list(_CALL_ORDER_LOG),
    ["run_once", "log_cycle"],
)
print()

print("[テスト37] observe_and_report()が呼ばれた場合、formatterの出力が標準出力に含まれる")
_stdout_37, _raised_37 = run_main_with_argv([], stop_after_sleep_calls=1)
check("37. 例外が伝播しない", _raised_37, None)
check_contains("37. 標準出力にformatterの出力が含まれる", _stdout_37, "cycle_count=0")
print()

print("[テスト38] main()のソースに新規配線（log_write_succeeded・observe_and_report）が含まれる")
_main_source_38 = inspect.getsource(run_retry_runtime.main)
check_contains("38. main()が\"log_write_succeeded\"を含む", _main_source_38, "log_write_succeeded")
check_contains("38. main()が\"observe_and_report\"を含む", _main_source_38, "observe_and_report")
print()

print("[テスト39] --loop実行時、log_cycle()の戻り値に応じてcycleごとのevent順序が厳密に切り替わる")
_stdout_39, _raised_39 = run_main_with_argv(
    ["--loop"], stop_after_sleep_calls=3, log_cycle_return_values=[True, False, True],
)
check("39. 例外が伝播しない", _raised_39, None)
check("39. log_cycle()が3回呼ばれる", len(_FakeCycleLoggerBool.instances[0].calls), 3)
check("39. observe_and_report()は2回のみ呼ばれる（Falseの回はskip）", len(_FakeObservabilityReporter.instances[0].calls), 2)
check(
    "39. cycleごとのイベント順序が[True, False, True]の戻り値と厳密に一致する（Round 1 MINOR-1対応）",
    list(_CALL_ORDER_LOG),
    [
        "run_once", "log_cycle", "observe_and_report",
        "run_once", "log_cycle",
        "run_once", "log_cycle", "observe_and_report",
    ],
)
print()


# ═══════════════════════════════════════════════════════════
# テスト39a-39c: Lock Safety（Round 1 Code Review MAJOR-2対応）
# ═══════════════════════════════════════════════════════════

print("[テスト39a] _FakeLockのソースに実ファイルI/O・mutation相当の呼び出しが一切存在しない（構造的検証、Round 2 MINOR-1対応で検出対象を拡充）")
_fake_lock_source_tree = ast.parse(inspect.getsource(_FakeLock))
_fake_lock_call_names = set()
for _node in ast.walk(_fake_lock_source_tree):
    if isinstance(_node, ast.Call):
        if isinstance(_node.func, ast.Name):
            _fake_lock_call_names.add(_node.func.id)
        elif isinstance(_node.func, ast.Attribute):
            _fake_lock_call_names.add(_node.func.attr)
# 「現在PASSする」ことではなく「将来_FakeLockへfile mutationが混入しても
# このguardが検出できる」ことを目的とした網羅的な禁止リスト（Round 2 MINOR-1）。
# pathlib.Path系（write_text/write_bytes/touch/rename/replace/unlink/mkdir/
# rmdir）・os系（open/remove/rename/replace/makedirs/removedirs/rmdir）・
# shutil系（move/copy/copyfile/copytree/rmtree）を横断的に検出する。
_FORBIDDEN_MUTATING_CALLS = (
    "open", "write", "write_text", "write_bytes", "touch",
    "unlink", "remove", "rmdir", "removedirs",
    "mkdir", "makedirs",
    "rename", "replace",
    "move", "copy", "copyfile", "copytree", "rmtree",
)
for _forbidden_call in _FORBIDDEN_MUTATING_CALLS:
    check_true(f"39a. _FakeLockが{_forbidden_call}()を呼ばない", _forbidden_call not in _fake_lock_call_names)
print()

print("[テスト39b] run_main_with_argv()実行中、production RetryRuntimeLockが一切インスタンス化されない（構造的検証、real classへのspy）")
from retry_runtime_lock import RetryRuntimeLock as _RealRetryRuntimeLock  # noqa: E402 - このテスト専用のスコープ内import


def _real_lock_init_spy(self, *args, **kwargs):
    raise AssertionError(
        "production RetryRuntimeLock must not be instantiated while RetryRuntimeLock is patched to _FakeLock"
    )


_real_lock_instantiated_39b = None
with mock.patch.object(_RealRetryRuntimeLock, "__init__", _real_lock_init_spy):
    try:
        _stdout_39b, _raised_39b = run_main_with_argv([], stop_after_sleep_calls=1)
    except AssertionError as e:
        _real_lock_instantiated_39b = e
        _raised_39b = None
check("39b. 例外が伝播しない", _raised_39b, None)
check(
    "39b. production RetryRuntimeLock.__init__が一度も呼ばれない（real classへのspyがAssertionErrorを送出していない）",
    _real_lock_instantiated_39b,
    None,
)
print()

print("[テスト39c] run_main_with_argv()実行前後で、実project直下の.run/retry_runtime.lockが一切変化しない（read-only snapshot比較。本テストは実lock pathへ一切write/create/delete/renameしない）")
_lock_existed_before_39c = REAL_LOCK_PATH.exists()
_snapshot_before_39c = None
if _lock_existed_before_39c:
    _stat_before_39c = REAL_LOCK_PATH.stat()
    _snapshot_before_39c = {
        "size": _stat_before_39c.st_size,
        "mtime_ns": _stat_before_39c.st_mtime_ns,
        "sha256": hashlib.sha256(REAL_LOCK_PATH.read_bytes()).hexdigest(),
    }

_stdout_39c, _raised_39c = run_main_with_argv([], stop_after_sleep_calls=1)
check("39c. 例外が伝播しない", _raised_39c, None)

_lock_exists_after_39c = REAL_LOCK_PATH.exists()
if _lock_existed_before_39c:
    check_true("39c. 実行前に存在した実lockファイルは実行後も存在する（read-only比較、削除していない）", _lock_exists_after_39c)
    if _lock_exists_after_39c:
        _stat_after_39c = REAL_LOCK_PATH.stat()
        _snapshot_after_39c = {
            "size": _stat_after_39c.st_size,
            "mtime_ns": _stat_after_39c.st_mtime_ns,
            "sha256": hashlib.sha256(REAL_LOCK_PATH.read_bytes()).hexdigest(),
        }
        check(
            "39c. 実行前後でsize/mtime/sha256のsnapshotが完全に不変（read-only比較のみ、本テストは書き込みを一切行わない）",
            _snapshot_after_39c,
            _snapshot_before_39c,
        )
else:
    check_true("39c. 実行前に存在しなかった実lockファイルは実行後も作成されない（read-only比較のみ）", not _lock_exists_after_39c)
print()


# ═══════════════════════════════════════════════════════════
# テスト40-42: Architecture Guard（AST、8.2節）
# ═══════════════════════════════════════════════════════════

FORBIDDEN_DEPENDENCIES = (
    "retry_engine", "retry_queue", "retry_history", "retry_lineage",
    "retry_enqueue_trigger", "scheduler", "retry_composition", "retry_runtime_orchestrator",
)


def get_imported_root_modules(file_path: Path) -> set:
    tree = ast.parse(file_path.read_text(encoding="utf-8"), filename=str(file_path))
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


observability_files = sorted(RETRY_RUNTIME_OBSERVABILITY_DIR.glob("*.py"))

print("[テスト40] retry_runtime_observabilityが禁止package（8.1節）をいずれもimportしない")
for _f in observability_files:
    _imported = get_imported_root_modules(_f)
    for _forbidden in FORBIDDEN_DEPENDENCIES + ("scripts",):
        check_true(f"40. {_f.name}が{_forbidden}をimportしない", _forbidden not in _imported)
print()

print("[テスト41] 既存retry判断packageがretry_runtime_observabilityをimportしていない（Reverse Dependency禁止）")
for _pkg_name in FORBIDDEN_DEPENDENCIES:
    _pkg_dir = PROJECT_ROOT / "src" / _pkg_name
    if not _pkg_dir.is_dir():
        continue
    for _py_file in sorted(_pkg_dir.glob("*.py")):
        _imported = get_imported_root_modules(_py_file)
        check_true(
            f"41. {_pkg_name}/{_py_file.name}がretry_runtime_observabilityをimportしない",
            "retry_runtime_observability" not in _imported,
        )
print()

print("[テスト42] retry_runtime_observabilityのソース中にRetryManager等への参照がない")
for _f in observability_files:
    _source = _f.read_text(encoding="utf-8")
    for _forbidden_ref in ("RetryManager", "RetryLineageManager", "RetryQueueManager", "RetryHistoryManager"):
        check_not_contains(f"42. {_f.name}に{_forbidden_ref}への参照がない", _source, _forbidden_ref)
print()


# ═══════════════════════════════════════════════════════════
# テスト43-44: Zero-Diff / Formal Regression
# ═══════════════════════════════════════════════════════════
print("[テスト43] src/retry_engine・retry_lineage・retry_queue・retry_history・schedulerに対するgit diffが0である")
_git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    _git_available = False

if _git_available:
    for _rel_path in (
        "src/retry_engine", "src/retry_lineage", "src/retry_queue",
        "src/retry_history", "src/scheduler",
    ):
        _completed = subprocess.run(
            ["git", "diff", "--quiet", "--", _rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"43. {_rel_path} に変更がない（git diff）", _completed.returncode == 0)
else:
    check_true("43. gitが利用できないため無変更確認をスキップ", True)
print()

print("[テスト44] zero_diff_guard_registry.pyのallowed_source_changes_for(\"v6.33.0\")にscripts寄与が含まれる")
import zero_diff_guard_registry as _registry  # noqa: E402 - importlib的sys.path構成の都合上、テスト末尾でimport

_allowed_44 = _registry.allowed_source_changes_for("v6.33.0")
check_true("44. \"scripts\"エントリが存在する", "scripts" in _allowed_44)
check_true(
    "44. scripts/run_retry_runtime.pyが許容ファイルに含まれる",
    "scripts/run_retry_runtime.py" in _allowed_44.get("scripts", frozenset()),
)
check_true(
    "44. scripts/show_retry_notification.pyが許容ファイルに含まれる",
    "scripts/show_retry_notification.py" in _allowed_44.get("scripts", frozenset()),
)
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
