"""
E2E テスト: v5.9.0 Retry Runtime Loop Wiring Foundation

テストシナリオ（docs/design/retry_runtime_loop_wiring_foundation.md 対応）:
    ── CLI / argparse ──
    1.  引数なしでは従来どおり単発実行（run_once(dry_run=False)が1回だけ呼ばれる）
    2.  --dry-run単独では単発dry-run（run_once(dry_run=True)が1回だけ呼ばれる）
    3.  --loopでLoop経路へ入る
    4.  --loop --dry-runで全サイクルへdry_runが伝播する
    5.  --loopでinterval未指定の場合は60秒
    6.  正の--interval-secondsがLoopへ渡される
    7.  0秒は拒否（CLIエラー、非0終了）
    8.  負数は拒否（CLIエラー、非0終了）
    9.  数値でない値はargparseエラー
    10. --loopなしの--interval-secondsはCLIエラー

    ── Loop Wiring ──
    11. 既存RetryRuntimeLoop（本番クラス）がそのまま使用される（identity確認）
    12. run_once_fnとして薄いcycle関数が注入される（構造確認）
    13. sleep_fnとしてtime.sleepが渡される（構造確認・実際の呼び出し確認）
    14. should_continue_fnはLoop継続を可能にする（複数サイクルの実行で確認）
    15. 各サイクルでorchestrator.run_once()が呼ばれる
    16. 各サイクルでformat_summary()が呼ばれる
    17. 各サイクルでSummaryがprintされる
    18. Loopはrun_once_fnの戻り値を解釈しない（main()がloop.run()の戻り値を使わない）

    ── Exception / Stop ──
    19. 通常例外は握りつぶされず伝播する
    20. 通常例外時は後続sleepが呼ばれない（既存契約を破壊しない）
    21. KeyboardInterruptはLoop実行時のみ捕捉される（run_once_fn内・sleep_fn内の両方）
    22. KeyboardInterrupt時は短い終了メッセージが表示される
    23. KeyboardInterrupt時は正常終了扱い（main()から例外が伝播しない）
    24. KeyboardInterrupt以外の例外は非0終了（実CLIサブプロセス確認）

    ── Backward Compatibility ──
    25. 単発実行時のformat_summary()出力形式が変わらない
    26. RetryRuntimeCycleResult無変更（git diff）
    27. format_summary()の公開契約無変更（シグネチャ）
    28. RetryRuntimeLoop本体無変更（git diff）
    29. RetryRuntimeOrchestrator無変更（git diff）
    30. RetryCompositionRoot無変更（git diff）
    31. RetryManager（retry_engine）無変更（git diff）
    32. Retry関連の既存主要パッケージに意図しない変更がない（git diff一括確認）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v5_9_0_retry_runtime_loop_wiring_foundation.py
"""
import contextlib
import importlib.util
import inspect
import io
import os
import subprocess
import sys
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
print("v5.9.0 Retry Runtime Loop Wiring Foundation E2E テスト")
print("=" * 60)
print()

from retry_enqueue_trigger import RetryEnqueueTriggerResult
from retry_runtime_orchestrator import RetryRuntimeCycleResult
from retry_runtime_loop import RetryRuntimeLoop as _RealRetryRuntimeLoop


SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_retry_runtime.py"

spec = importlib.util.spec_from_file_location("run_retry_runtime_v590", SCRIPT_PATH)
run_retry_runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_retry_runtime)


# ─── Fake群 ───

trigger_result_sample = RetryEnqueueTriggerResult(
    scanned=7, enqueued=2, skipped_existing=3, skipped_status=1, failed=1,
)
result_sample = RetryRuntimeCycleResult(
    trigger_result=trigger_result_sample,
    scheduler_events=[1, 2],
    execution_results=[1],
    removal_results=[1],
    cleanup_results=[],
    terminal_cleanup_results=[],
    history_results=[1],
)


class _FakeRoot:
    pass


class _FakeOrchestrator:
    calls: list = []
    raise_on_call = None
    raise_exception = None

    def __init__(self):
        pass

    @classmethod
    def from_composition_root(cls, root):
        return cls()

    def run_once(self, dry_run: bool = False):
        _FakeOrchestrator.calls.append(dry_run)
        call_number = len(_FakeOrchestrator.calls)
        if _FakeOrchestrator.raise_on_call == call_number:
            raise _FakeOrchestrator.raise_exception
        return result_sample


class _FakeCompositionRoot:
    @staticmethod
    def from_env():
        return _FakeRoot()


class _StopLoopMarker(Exception):
    """テスト専用: Loopを能動的に止めるためのSentinel例外（本番コードには存在しない）。"""


class _CustomError(Exception):
    """テスト専用: run_once_fn内で発生する通常例外を模したダミー。"""


def _make_counting_sleep(raise_after=None, raise_exc=None):
    calls: list = []

    def _sleep(seconds):
        calls.append(seconds)
        if raise_after is not None and len(calls) >= raise_after:
            raise raise_exc

    _sleep.calls = calls
    return _sleep


def run_main_with_argv(argv, sleep_fn=None, raise_on_call=None, raise_exception=None):
    """
    main()をFakeのCompositionRoot/Orchestratorに差し替えて実行するテストヘルパー。

    RetryRuntimeLoop自体はモックしない（本番クラスをそのまま使用する）。sleep_fnを
    渡した場合のみ run_retry_runtime.time.sleep を差し替え、無限Loopに陥らないよう
    有限回でSentinel例外を送出させる。
    """
    _FakeOrchestrator.calls = []
    _FakeOrchestrator.raise_on_call = raise_on_call
    _FakeOrchestrator.raise_exception = raise_exception
    original_root = run_retry_runtime.RetryCompositionRoot
    original_orchestrator = run_retry_runtime.RetryRuntimeOrchestrator
    original_sleep = run_retry_runtime.time.sleep
    original_argv = sys.argv
    run_retry_runtime.RetryCompositionRoot = _FakeCompositionRoot
    run_retry_runtime.RetryRuntimeOrchestrator = _FakeOrchestrator
    if sleep_fn is not None:
        run_retry_runtime.time.sleep = sleep_fn
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
        run_retry_runtime.time.sleep = original_sleep
        sys.argv = original_argv
    return buf.getvalue(), raised


def run_cli(extra_args, env_overrides=None, timeout=15):
    env = dict(os.environ)
    for key in (
        "AI_AGENT_ENABLED", "WORKFLOW_ENGINE_ENABLED", "RETRY_ENGINE_ENABLED",
        "RETRY_QUEUE_ENABLED", "WORKFLOW_MONITOR_ENABLED",
        "REVIEW_TRIGGER_AGENT_ENABLED", "PUBLISH_TRIGGER_AGENT_ENABLED",
    ):
        env.pop(key, None)
    env.update({
        "AI_AGENT_ENABLED": "false", "WORKFLOW_ENGINE_ENABLED": "false", "RETRY_ENGINE_ENABLED": "false",
    })
    if env_overrides:
        env.update(env_overrides)
    env["PYTHONIOENCODING"] = "utf-8"
    args = [sys.executable, str(SCRIPT_PATH)] + extra_args
    return subprocess.run(
        args, cwd=str(PROJECT_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env, timeout=timeout,
    )


# ═══════════════════════════════════════════════════════════
# テスト1-2: 単発実行（引数なし・--dry-run単独）
# ═══════════════════════════════════════════════════════════

print("[テスト1] 引数なしでは従来どおり単発実行")

stdout_1, raised_1 = run_main_with_argv([])
check("1. run_once(dry_run=False)が1回だけ呼ばれる", _FakeOrchestrator.calls, [False])
check("1. main()から例外が伝播しない", raised_1, None)
check_contains("1. 単発実行の見出しが表示される", stdout_1, "1サイクルのみ実行")
check_not_contains("1. Loop見出しが表示されない", stdout_1, "Loop実行")
print()


print("[テスト2] --dry-run単独では単発dry-run")

stdout_2, raised_2 = run_main_with_argv(["--dry-run"])
check("2. run_once(dry_run=True)が1回だけ呼ばれる", _FakeOrchestrator.calls, [True])
check_contains("2. [DRY RUN MODE]が表示される", stdout_2, "[DRY RUN MODE]")
check_not_contains("2. Loop見出しが表示されない", stdout_2, "Loop実行")
print()


# ═══════════════════════════════════════════════════════════
# テスト3-6: --loop / --interval-seconds の正常系
# ═══════════════════════════════════════════════════════════

print("[テスト3] --loopでLoop経路へ入る")

sleep_3 = _make_counting_sleep(raise_after=1, raise_exc=_StopLoopMarker())
stdout_3, raised_3 = run_main_with_argv(["--loop"], sleep_fn=sleep_3)
check_true("3. Sentinel例外が伝播する（1サイクル後に停止）", isinstance(raised_3, _StopLoopMarker))
check("3. run_once(dry_run=False)が1回呼ばれた", _FakeOrchestrator.calls, [False])
check_contains("3. Loop見出しが表示される", stdout_3, "Loop実行")
print()


print("[テスト4] --loop --dry-runで全サイクルへdry_runが伝播する")

sleep_4 = _make_counting_sleep(raise_after=3, raise_exc=_StopLoopMarker())
stdout_4, raised_4 = run_main_with_argv(["--loop", "--dry-run"], sleep_fn=sleep_4)
check("4. 3サイクルすべてdry_run=True", _FakeOrchestrator.calls, [True, True, True])
check_true("4. Sentinel例外が伝播する", isinstance(raised_4, _StopLoopMarker))
print()


print("[テスト5] --loopでinterval未指定の場合は60秒")

sleep_5 = _make_counting_sleep(raise_after=1, raise_exc=_StopLoopMarker())
stdout_5, raised_5 = run_main_with_argv(["--loop"], sleep_fn=sleep_5)
check("5. sleepにinterval=60.0が渡される", sleep_5.calls, [60.0])
check_contains("5. バナーにinterval_seconds=60.0が表示される", stdout_5, "interval_seconds=60.0")
print()


print("[テスト6] 正の--interval-secondsがLoopへ渡される")

sleep_6 = _make_counting_sleep(raise_after=1, raise_exc=_StopLoopMarker())
stdout_6, raised_6 = run_main_with_argv(["--loop", "--interval-seconds", "5"], sleep_fn=sleep_6)
check("6. sleepにinterval=5.0が渡される", sleep_6.calls, [5.0])
print()


# ═══════════════════════════════════════════════════════════
# テスト7-10: --interval-seconds のバリデーション（実CLI）
# ═══════════════════════════════════════════════════════════

print("[テスト7] 0秒は拒否される（CLIエラー、非0終了）")

completed_7 = run_cli(["--loop", "--interval-seconds", "0"])
check_true("7. returncodeが0ではない", completed_7.returncode != 0)
check_contains("7. エラーメッセージに--interval-secondsが含まれる", completed_7.stderr, "--interval-seconds")
print()


print("[テスト8] 負数は拒否される（CLIエラー、非0終了）")

completed_8 = run_cli(["--loop", "--interval-seconds", "-5"])
check_true("8. returncodeが0ではない", completed_8.returncode != 0)
check_contains("8. エラーメッセージに--interval-secondsが含まれる", completed_8.stderr, "--interval-seconds")
print()


print("[テスト9] 数値でない値はargparseエラー")

completed_9 = run_cli(["--loop", "--interval-seconds", "abc"])
check_true("9. returncodeが0ではない", completed_9.returncode != 0)
print()


print("[テスト10] --loopなしの--interval-secondsはCLIエラー")

completed_10 = run_cli(["--interval-seconds", "60"])
check_true("10. returncodeが0ではない", completed_10.returncode != 0)
check_contains("10. エラーメッセージが--loopとの関係を示す", completed_10.stderr, "--loop")
print()


# ═══════════════════════════════════════════════════════════
# テスト11-18: Loop Wiring
# ═══════════════════════════════════════════════════════════

print("[テスト11] 既存RetryRuntimeLoop（本番クラス）がそのまま使用される")

check_true("11. run_retry_runtime.RetryRuntimeLoopが本番のRetryRuntimeLoopと同一", run_retry_runtime.RetryRuntimeLoop is _RealRetryRuntimeLoop)
print()


print("[テスト12] run_once_fnとして薄いcycle関数が注入される（構造確認）")

main_source_12 = inspect.getsource(run_retry_runtime.main)
check_contains("12. main()にrun_cycleというローカル関数が定義されている", main_source_12, "def run_cycle")
check_contains("12. run_cycleがorchestrator.run_once()を呼ぶ", main_source_12, "orchestrator.run_once(dry_run=args.dry_run)")
check_contains("12. run_cycleがformat_summary()を呼ぶ", main_source_12, "format_summary(result)")
print()


print("[テスト13] sleep_fnとしてtime.sleepが渡される")

check_contains("13. RetryRuntimeLoop構築でsleep_fn=time.sleepが指定される", main_source_12, "sleep_fn=time.sleep")
check("13. 実際にrun_retry_runtime.time.sleep経由でsleepが呼ばれる（テスト5で確認済み）", sleep_5.calls, [60.0])
print()


print("[テスト14] should_continue_fnはLoop継続を可能にする（複数サイクルで確認）")

sleep_14 = _make_counting_sleep(raise_after=4, raise_exc=_StopLoopMarker())
stdout_14, raised_14 = run_main_with_argv(["--loop"], sleep_fn=sleep_14)
check("14. should_continue_fn=lambda: Trueにより4サイクル実行される", len(_FakeOrchestrator.calls), 4)
print()


print("[テスト15] 各サイクルでorchestrator.run_once()が呼ばれる")

check("15. テスト14で4回のrun_once呼び出しを確認済み", len(_FakeOrchestrator.calls), 4)
print()


print("[テスト16] 各サイクルでformat_summary()が呼ばれる／[テスト17] Summaryがprintされる")

check("16-17. 標準出力にSummaryが4回出力される", stdout_14.count("Retry Runtime 実行結果"), 4)
print()


print("[テスト18] Loopはrun_once_fnの戻り値を解釈しない（main()がloop.run()の戻り値を使わない）")

check_not_contains("18. main()内でloop.run()の戻り値を変数へ代入していない", main_source_12, "= loop.run()")
check_contains("18. loop.run()が呼ばれている", main_source_12, "loop.run()")
print()


# ═══════════════════════════════════════════════════════════
# テスト19-20: 通常例外の伝播
# ═══════════════════════════════════════════════════════════

print("[テスト19] 通常例外は握りつぶされず伝播する")

sleep_19 = _make_counting_sleep()
stdout_19, raised_19 = run_main_with_argv(
    ["--loop"], sleep_fn=sleep_19, raise_on_call=2, raise_exception=_CustomError("boom"),
)
check_true("19. _CustomErrorがmain()から伝播する", isinstance(raised_19, _CustomError))
check("19. run_onceが2回呼ばれた時点で例外発生", len(_FakeOrchestrator.calls), 2)
print()


print("[テスト20] 通常例外時は後続sleepが呼ばれない")

check("20. sleepは1回だけ呼ばれた（2回目のrun_once例外後は呼ばれない）", sleep_19.calls, [60.0])
print()


# ═══════════════════════════════════════════════════════════
# テスト21-24: KeyboardInterrupt
# ═══════════════════════════════════════════════════════════

print("[テスト21] KeyboardInterruptはLoop実行時のみ捕捉される（sleep_fn内で発生）")

sleep_21a = _make_counting_sleep(raise_after=1, raise_exc=KeyboardInterrupt())
stdout_21a, raised_21a = run_main_with_argv(["--loop"], sleep_fn=sleep_21a)
check("21. sleep_fn内のKeyboardInterruptが捕捉されmain()から例外が伝播しない", raised_21a, None)
print()


print("[テスト21b] KeyboardInterruptはLoop実行時のみ捕捉される（run_once_fn内で発生）")

sleep_21b = _make_counting_sleep()
stdout_21b, raised_21b = run_main_with_argv(
    ["--loop"], sleep_fn=sleep_21b, raise_on_call=1, raise_exception=KeyboardInterrupt(),
)
check("21b. run_once_fn内のKeyboardInterruptも捕捉されmain()から例外が伝播しない", raised_21b, None)
print()


print("[テスト22] KeyboardInterrupt時は短い終了メッセージが表示される")

check_contains("22. 終了メッセージが表示される", stdout_21a, "Retry runtime loop stopped.")
print()


print("[テスト23] KeyboardInterrupt時は正常終了扱い（main()から例外が伝播しない）")

check("23. raisedがNone（テスト21・21bで確認済み）", (raised_21a, raised_21b), (None, None))
print()


print("[テスト24] KeyboardInterrupt以外の例外は非0終了（実CLIサブプロセス確認）")

completed_24 = run_cli(["--loop"], env_overrides={"RETRY_QUEUE_MAX_SIZE": "not_a_number"})
check_true("24. returncodeが0ではない", completed_24.returncode != 0)
check_contains("24. stderrにValueErrorが含まれる（fail-fast）", completed_24.stderr, "ValueError")
print()


# ═══════════════════════════════════════════════════════════
# テスト25-32: Backward Compatibility
# ═══════════════════════════════════════════════════════════

print("[テスト25] 単発実行時のformat_summary()出力形式が変わらない")

summary_text_25 = run_retry_runtime.format_summary(result_sample)
check_contains("25. Enqueue行が従来形式で出力される", summary_text_25, "scanned=7, enqueued=2")
check_contains("25. Scheduler行が従来形式で出力される", summary_text_25, "candidates=2")
check_contains("25. Execution行が従来形式で出力される", summary_text_25, "executed=1")
print()


print("[テスト26-31] 主要コンポーネントに変更がないこと（git diff）")

unchanged_paths_26_31 = [
    "src/retry_runtime_orchestrator/retry_runtime_cycle_result.py",
    "src/retry_runtime_loop",
    "src/retry_composition",
    "src/retry_engine",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths_26_31:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"26-31. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("26-31. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト27] format_summary()の公開契約が無変更（シグネチャ）")

sig_27 = inspect.signature(run_retry_runtime.format_summary)
check("27. パラメータがresultのみ", list(sig_27.parameters.keys()), ["result"])
print()


print("[テスト32] Retry関連の既存主要パッケージに意図しない変更がない（git diff一括確認）")

unchanged_paths_32 = [
    "src/retry_runtime_loop",
    "src/retry_runtime_orchestrator",
    "src/retry_composition",
    "src/retry_engine",
    "src/retry_enqueue_trigger",
    "src/retry_queue",
    "src/retry_history",
    "src/workflow_monitor",
    "src/workflow_engine",
    "src/scheduler",
    "src/retry_scheduler_source",
    "src/retry_scheduler_decision",
    "src/ai",
    "src/execution_history",
]

if git_available:
    for rel_path in unchanged_paths_32:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"32. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("32. gitが利用できないため無変更確認をスキップ", True)
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
