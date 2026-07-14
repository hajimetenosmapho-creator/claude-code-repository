"""
E2E テスト: v6.2.0 Structured Loop Logging Foundation

テストシナリオ（docs/design/retry_runtime_structured_loop_logging_foundation.md 対応）:
    ── RetryRuntimeCycleLogger 単体 ──
    1.  存在しないログファイルへlog_cycle()すると新規作成され1行書き込まれる
    2.  2回log_cycle()すると既存の1行目を残したまま2行目が追記される（append動作）
    3.  各行がjson.loads()でパース可能な妥当なJSONである
    4.  必須フィールド（cycle_number/timestamp/dry_run/各件数）がすべて含まれる
    5.  cycle_numberが渡した値どおりに記録される
    6.  dry_run=Trueを渡すとレコードのdry_runがtrueになる
    7.  dry_run=False（省略時）を渡すとレコードのdry_runがfalseになる
    8.  RetryRuntimeCycleResultの各件数（enqueue/scheduler/execution/removal/
        cleanup/terminal_cleanup/history）が正しく記録される
    9.  ログ書き込みに失敗（書き込み不可なパス）してもlog_cycle()が例外を
        送出しない
    10. 9の際、stderrへ"WARNING"と"Failed to write runtime log"を含む
        メッセージが出力される
    11. RetryRuntimeCycleLoggerは他のretry_*パッケージに依存しない
        （RetryRuntimeCycleResultの型参照を除く。依存方向確認）

    ── scripts/run_retry_runtime.py 配線（ソース確認） ──
    12. main()のソースに"cycle_logger.log_cycle("が含まれる
    13. main()のソースに"cycle_count += 1"が含まれる
    14. main()のソースに"nonlocal cycle_count"が含まれる

    ── scripts/run_retry_runtime.py 配線（Fake経由の統合動作確認） ──
    15. --loop実行で、cycle_numberが1, 2, 3...と連番でlog_cycle()へ渡される
    16. 単発実行（--loopなし）ではlog_cycle()がちょうど1回、cycle_number=1で
        呼ばれる
    17. --loop実行時、--dry-run指定がlog_cycle()のdry_run引数へ伝播する

    ── format_summary()への非干渉確認 ──
    18. format_summary()の公開契約が無変更（シグネチャ）
    19. format_summary()の出力文字列にログ関連の文言が含まれない
        （コンソール表示とログ出力の分離確認）

    ── Backward Compatibility / Zero Diff ──
    20. RetryRuntimeLock無変更（git diff）
    21. RetryRuntimeShutdown無変更（git diff）
    22. RetryRuntimeLoop無変更（git diff）
    23. RetryRuntimeOrchestrator無変更（git diff）
    24. RetryManager（retry_engine）無変更（git diff）
    25. RetryCompositionRoot無変更（git diff）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_2_0_structured_loop_logging_foundation.py
"""
import contextlib
import importlib.util
import inspect
import io
import json
import sys
import tempfile
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


def check_false(label: str, value: bool):
    check(label, value, False)


def check_contains(label: str, text, keyword: str):
    check(label, keyword in str(text), True)


def check_not_contains(label: str, text, keyword: str):
    check(label, keyword in str(text), False)


print("=" * 60)
print("v6.2.0 Structured Loop Logging Foundation E2E テスト")
print("=" * 60)
print()

from retry_runtime_logging import RetryRuntimeCycleLogger
import retry_runtime_logging.retry_runtime_cycle_logger as _logger_module
from retry_runtime_orchestrator import RetryRuntimeCycleResult
from retry_enqueue_trigger import RetryEnqueueTriggerResult

SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_retry_runtime.py"
REAL_LOCK_PATH = PROJECT_ROOT / ".run" / "retry_runtime.lock"

spec = importlib.util.spec_from_file_location("run_retry_runtime_v620", SCRIPT_PATH)
run_retry_runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_retry_runtime)


def ensure_real_lock_absent():
    REAL_LOCK_PATH.unlink(missing_ok=True)


ensure_real_lock_absent()


def make_result(scanned=3, enqueued=1, skipped_existing=0, skipped_status=1,
                 skipped_history=1, failed=0, scheduler_events=None,
                 execution_results=None, removal_results=None,
                 cleanup_results=None, terminal_cleanup_results=None,
                 history_results=None):
    trigger_result = RetryEnqueueTriggerResult(
        scanned=scanned, enqueued=enqueued, skipped_existing=skipped_existing,
        skipped_status=skipped_status, skipped_history=skipped_history, failed=failed,
    )
    return RetryRuntimeCycleResult(
        trigger_result=trigger_result,
        scheduler_events=scheduler_events if scheduler_events is not None else [],
        execution_results=execution_results if execution_results is not None else [],
        removal_results=removal_results if removal_results is not None else [],
        cleanup_results=cleanup_results if cleanup_results is not None else [],
        terminal_cleanup_results=terminal_cleanup_results if terminal_cleanup_results is not None else [],
        history_results=history_results if history_results is not None else [],
    )


# ═══════════════════════════════════════════════════════════
# テスト1-11: RetryRuntimeCycleLogger 単体
# ═══════════════════════════════════════════════════════════

with tempfile.TemporaryDirectory() as tmpdir_1:
    log_path_1 = Path(tmpdir_1) / "sub" / "retry_runtime_log.jsonl"

    print("[テスト1] 存在しないログファイルへlog_cycle()すると新規作成され1行書き込まれる")
    logger_1 = RetryRuntimeCycleLogger(log_path=log_path_1)
    logger_1.log_cycle(cycle_number=1, result=make_result())
    check_true("1. ログファイルが作成される", log_path_1.exists())
    lines_1 = log_path_1.read_text(encoding="utf-8").splitlines()
    check("1. 1行だけ書き込まれる", len(lines_1), 1)
    print()

    print("[テスト2] 2回log_cycle()すると既存の1行目を残したまま2行目が追記される")
    logger_1.log_cycle(cycle_number=2, result=make_result())
    lines_2 = log_path_1.read_text(encoding="utf-8").splitlines()
    check("2. 2行になる（append動作）", len(lines_2), 2)
    record_2_first = json.loads(lines_2[0])
    check("2. 1行目のcycle_numberが1のまま維持される", record_2_first["cycle_number"], 1)
    print()

    print("[テスト3] 各行がjson.loads()でパース可能な妥当なJSONである")
    raised_3 = None
    try:
        for line in lines_2:
            json.loads(line)
    except Exception as e:  # noqa: BLE001
        raised_3 = e
    check("3. 全行がJSONとしてパース可能", raised_3, None)
    print()

    print("[テスト4] 必須フィールドがすべて含まれる")
    record_4 = json.loads(lines_2[1])
    required_fields = [
        "cycle_number", "timestamp", "dry_run",
        "enqueue_scanned", "enqueue_enqueued", "enqueue_skipped_existing",
        "enqueue_skipped_status", "enqueue_skipped_history", "enqueue_failed",
        "scheduler_candidates", "execution_executed", "removal_removed",
        "cleanup_cleaned", "terminal_cleanup_cleaned", "history_recorded",
    ]
    for field in required_fields:
        check_true(f"4. フィールド'{field}'が含まれる", field in record_4)
    print()

    print("[テスト5] cycle_numberが渡した値どおりに記録される")
    check("5. 2行目のcycle_numberが2", record_4["cycle_number"], 2)
    print()

with tempfile.TemporaryDirectory() as tmpdir_6:
    log_path_6 = Path(tmpdir_6) / "retry_runtime_log.jsonl"
    logger_6 = RetryRuntimeCycleLogger(log_path=log_path_6)

    print("[テスト6] dry_run=Trueを渡すとレコードのdry_runがtrueになる")
    logger_6.log_cycle(cycle_number=1, result=make_result(), dry_run=True)
    record_6 = json.loads(log_path_6.read_text(encoding="utf-8").splitlines()[0])
    check("6. dry_runがTrue", record_6["dry_run"], True)
    print()

    print("[テスト7] dry_run=False（省略時）を渡すとレコードのdry_runがfalseになる")
    logger_6.log_cycle(cycle_number=2, result=make_result())
    record_7 = json.loads(log_path_6.read_text(encoding="utf-8").splitlines()[1])
    check("7. dry_runがFalse", record_7["dry_run"], False)
    print()

with tempfile.TemporaryDirectory() as tmpdir_8:
    log_path_8 = Path(tmpdir_8) / "retry_runtime_log.jsonl"
    logger_8 = RetryRuntimeCycleLogger(log_path=log_path_8)

    print("[テスト8] RetryRuntimeCycleResultの各件数が正しく記録される")
    result_8 = make_result(
        scanned=5, enqueued=2, skipped_existing=1, skipped_status=1,
        skipped_history=1, failed=0,
        scheduler_events=[object(), object()],
        execution_results=[object()],
        removal_results=[object()],
        cleanup_results=[object(), object(), object()],
        terminal_cleanup_results=[],
        history_results=[object()],
    )
    logger_8.log_cycle(cycle_number=1, result=result_8)
    record_8 = json.loads(log_path_8.read_text(encoding="utf-8").splitlines()[0])
    check("8. enqueue_scanned=5", record_8["enqueue_scanned"], 5)
    check("8. enqueue_enqueued=2", record_8["enqueue_enqueued"], 2)
    check("8. enqueue_skipped_existing=1", record_8["enqueue_skipped_existing"], 1)
    check("8. enqueue_skipped_status=1", record_8["enqueue_skipped_status"], 1)
    check("8. enqueue_skipped_history=1", record_8["enqueue_skipped_history"], 1)
    check("8. enqueue_failed=0", record_8["enqueue_failed"], 0)
    check("8. scheduler_candidates=2", record_8["scheduler_candidates"], 2)
    check("8. execution_executed=1", record_8["execution_executed"], 1)
    check("8. removal_removed=1", record_8["removal_removed"], 1)
    check("8. cleanup_cleaned=3", record_8["cleanup_cleaned"], 3)
    check("8. terminal_cleanup_cleaned=0", record_8["terminal_cleanup_cleaned"], 0)
    check("8. history_recorded=1", record_8["history_recorded"], 1)
    print()


print("[テスト9-10] ログ書き込みに失敗しても例外を送出せず、stderrへWARNINGを出力する")
# 書き込み不可なパス：既存ファイルをディレクトリの代わりに親パスとして使う
with tempfile.TemporaryDirectory() as tmpdir_9:
    blocking_file = Path(tmpdir_9) / "not_a_directory"
    blocking_file.write_text("x", encoding="utf-8")
    unwritable_log_path = blocking_file / "retry_runtime_log.jsonl"

    logger_9 = RetryRuntimeCycleLogger(log_path=unwritable_log_path)
    stderr_buf_9 = io.StringIO()
    raised_9 = None
    try:
        with contextlib.redirect_stderr(stderr_buf_9):
            logger_9.log_cycle(cycle_number=1, result=make_result())
    except Exception as e:  # noqa: BLE001
        raised_9 = e
    check("9. log_cycle()が例外を送出しない", raised_9, None)
    check_contains("10. stderrに\"WARNING\"が含まれる", stderr_buf_9.getvalue(), "WARNING")
    check_contains("10. stderrに\"Failed to write runtime log\"が含まれる", stderr_buf_9.getvalue(), "Failed to write runtime log")
print()


print("[テスト11] RetryRuntimeCycleLoggerは他のretry_*パッケージに依存しない（RetryRuntimeCycleResultの型参照を除く）")
logger_source_11 = inspect.getsource(_logger_module)
for forbidden in (
    "retry_composition", "retry_runtime_loop", "retry_runtime_shutdown",
    "retry_runtime_lock", "retry_engine",
):
    check_not_contains(f"11. retry_runtime_cycle_loggerが{forbidden}をimportしない", logger_source_11, forbidden)
print()


# ═══════════════════════════════════════════════════════════
# テスト12-14: scripts/run_retry_runtime.py 配線（ソース確認）
# ═══════════════════════════════════════════════════════════

main_source = inspect.getsource(run_retry_runtime.main)

print("[テスト12] main()のソースに\"cycle_logger.log_cycle(\"が含まれる")
check_contains("12. main()が\"cycle_logger.log_cycle(\"を含む", main_source, "cycle_logger.log_cycle(")
print()

print("[テスト13] main()のソースに\"cycle_count += 1\"が含まれる")
check_contains("13. main()が\"cycle_count += 1\"を含む", main_source, "cycle_count += 1")
print()

print("[テスト14] main()のソースに\"nonlocal cycle_count\"が含まれる")
check_contains("14. main()が\"nonlocal cycle_count\"を含む", main_source, "nonlocal cycle_count")
print()


# ═══════════════════════════════════════════════════════════
# テスト15-17: scripts/run_retry_runtime.py 配線（Fake経由の統合動作確認）
# ═══════════════════════════════════════════════════════════

trigger_result_sample = RetryEnqueueTriggerResult(
    scanned=1, enqueued=0, skipped_existing=0, skipped_status=0, failed=0,
)
result_sample = RetryRuntimeCycleResult(
    trigger_result=trigger_result_sample,
    scheduler_events=[],
    execution_results=[],
    removal_results=[],
    cleanup_results=[],
    terminal_cleanup_results=[],
    history_results=[],
)


class _FakeRoot:
    pass


class _FakeOrchestrator:
    calls: list = []

    def __init__(self):
        pass

    @classmethod
    def from_composition_root(cls, root):
        return cls()

    def run_once(self, dry_run: bool = False):
        _FakeOrchestrator.calls.append(dry_run)
        return result_sample


class _FakeCompositionRoot:
    @staticmethod
    def from_env():
        return _FakeRoot()


class _FakeShutdown:
    """v6.1.0テストと同型のFake（interruptible_sleep呼び出し回数で停止を制御）。"""

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


class _FakeCycleLogger:
    instances: list = []

    def __init__(self, log_path):
        self.log_path = log_path
        self.calls: list = []
        _FakeCycleLogger.instances.append(self)

    def log_cycle(self, cycle_number, result, dry_run=False):
        self.calls.append({"cycle_number": cycle_number, "result": result, "dry_run": dry_run})


def run_main_with_argv(argv, stop_after_sleep_calls=1):
    _FakeOrchestrator.calls = []
    _FakeShutdown.instances = []
    _FakeCycleLogger.instances = []
    original_root = run_retry_runtime.RetryCompositionRoot
    original_orchestrator = run_retry_runtime.RetryRuntimeOrchestrator
    original_shutdown_cls = run_retry_runtime.RetryRuntimeShutdown
    original_logger_cls = run_retry_runtime.RetryRuntimeCycleLogger
    original_argv = sys.argv

    def _shutdown_factory(*args, **kwargs):
        fake = _FakeShutdown()
        fake.stop_after_sleep_calls = stop_after_sleep_calls
        return fake

    run_retry_runtime.RetryCompositionRoot = _FakeCompositionRoot
    run_retry_runtime.RetryRuntimeOrchestrator = _FakeOrchestrator
    run_retry_runtime.RetryRuntimeShutdown = _shutdown_factory
    run_retry_runtime.RetryRuntimeCycleLogger = _FakeCycleLogger
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
        sys.argv = original_argv
    return buf.getvalue(), raised


print("[テスト15] --loop実行で、cycle_numberが1, 2, 3...と連番でlog_cycle()へ渡される")
ensure_real_lock_absent()
stdout_15, raised_15 = run_main_with_argv(["--loop"], stop_after_sleep_calls=3)
check("15. 例外が伝播しない", raised_15, None)
check("15. FakeCycleLoggerインスタンスが1つ生成される", len(_FakeCycleLogger.instances), 1)
logged_cycle_numbers_15 = [c["cycle_number"] for c in _FakeCycleLogger.instances[0].calls]
check("15. cycle_numberが[1, 2, 3]の連番で記録される", logged_cycle_numbers_15, [1, 2, 3])
ensure_real_lock_absent()
print()


print("[テスト16] 単発実行（--loopなし）ではlog_cycle()がちょうど1回、cycle_number=1で呼ばれる")
ensure_real_lock_absent()
stdout_16, raised_16 = run_main_with_argv([], stop_after_sleep_calls=1)
check("16. 例外が伝播しない", raised_16, None)
calls_16 = _FakeCycleLogger.instances[0].calls
check("16. log_cycle()がちょうど1回呼ばれる", len(calls_16), 1)
check("16. cycle_numberが1", calls_16[0]["cycle_number"], 1)
ensure_real_lock_absent()
print()


print("[テスト17] --loop実行時、--dry-run指定がlog_cycle()のdry_run引数へ伝播する")
ensure_real_lock_absent()
stdout_17, raised_17 = run_main_with_argv(["--loop", "--dry-run"], stop_after_sleep_calls=2)
check("17. 例外が伝播しない", raised_17, None)
calls_17 = _FakeCycleLogger.instances[0].calls
check_true("17. 記録された全呼び出しでdry_run=True", all(c["dry_run"] is True for c in calls_17))
ensure_real_lock_absent()
print()


# ═══════════════════════════════════════════════════════════
# テスト18-19: format_summary()への非干渉確認
# ═══════════════════════════════════════════════════════════

print("[テスト18] format_summary()の公開契約が無変更（シグネチャ）")
sig_18 = inspect.signature(run_retry_runtime.format_summary)
check("18. パラメータがresultのみ", list(sig_18.parameters.keys()), ["result"])
print()

print("[テスト19] format_summary()の出力文字列にログ関連の文言が含まれない（コンソール表示とログ出力の分離確認）")
summary_19 = run_retry_runtime.format_summary(result_sample)
for forbidden_word in ("jsonl", "cycle_number", "WARNING"):
    check_not_contains(f"19. format_summary()の出力に'{forbidden_word}'が含まれない", summary_19, forbidden_word)
print()


# ═══════════════════════════════════════════════════════════
# テスト20-25: Backward Compatibility / Zero Diff
# ═══════════════════════════════════════════════════════════

print("[テスト20-25] 既存主要コンポーネントに変更がないこと（git diff）")

unchanged_paths = [
    "src/retry_runtime_lock",
    "src/retry_runtime_shutdown",
    "src/retry_runtime_loop",
    "src/retry_runtime_orchestrator",
    "src/retry_engine",
    "src/retry_composition",
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
        check_true(f"20-25. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("20-25. gitが利用できないため無変更確認をスキップ", True)
print()


ensure_real_lock_absent()

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
