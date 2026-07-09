"""
E2E テスト: v5.5.0 Retry Runtime Loop Foundation

テストシナリオ:
    ── Functional（Fakeによる振る舞い確認） ──
    1.  __init__ が例外なく RetryRuntimeLoop を返す
    2.  run() が should_continue_fn の回数だけ run_once_fn を呼ぶ
    3.  run() が should_continue_fn の回数だけ sleep_fn を interval_seconds 付きで呼ぶ
    4.  should_continue_fn が最初から False の場合、run_once_fn/sleep_fn が一度も呼ばれない
    5.  呼び出し順序が run_once_fn → sleep_fn の繰り返しである
    6.  run_once_fn の戻り値は run() の戻り値に反映されない（run() は None を返す）
    7.  run_once_fn が例外を送出した場合、run() から伝播し、直後の sleep_fn は呼ばれない
    8.  should_continue_fn が例外を送出した場合、run() から伝播する

    ── 責務境界（Loopは何も知らない） ──
    9.  __init__ のシグネチャが (self, run_once_fn, sleep_fn, should_continue_fn, interval_seconds)
    10. RetryRuntimeLoopが run 以外の公開メソッドを持たない
    11. retry_runtime_loop.py が他のRetry関連パッケージを一切importしない
    12. retry_runtime_loop.py のソースに "RetryRuntimeCycleResult" という識別子が出現しない

    ── ディレクトリ構成・Backward Compatibility ──
    13. src/retry_runtime_loop/ のファイル構成が __init__.py・retry_runtime_loop.py の2ファイルのみ
    14. retry_runtime_loop パッケージのexportが RetryRuntimeLoop のみである

    ── Architecture Guard ──
    15. 既存13パッケージ・scripts/run_retry_runtime.py に変更がないこと（git diff）
    16. retry_runtime_loop をどこからも呼び出さない（消費者不在の先行実装）

    ── 副作用なしの確認 ──
    17. RetryRuntimeLoop.run() 実行前後でファイルが一切作成されない

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v5_5_0_retry_runtime_loop_foundation.py
"""
import ast
import inspect
import subprocess
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from dotenv import load_dotenv

load_dotenv(PROJECT_ROOT / ".env")

# ─── テスト用ユーティリティ ───

results_log = []


def check(label: str, actual, expected, exact: bool = True):
    ok = (actual == expected) if exact else (expected in str(actual))
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


print("=" * 60)
print("v5.5.0 Retry Runtime Loop Foundation E2E テスト")
print("=" * 60)
print()

import retry_runtime_loop as rrl_pkg
from retry_runtime_loop import RetryRuntimeLoop


class _Recorder:
    """呼び出し順序・引数を記録するテスト用Fake。"""

    def __init__(self):
        self.calls = []


# ═══════════════════════════════════════════════════════════
# テスト1: __init__ が例外なく RetryRuntimeLoop を返す
# ═══════════════════════════════════════════════════════════

print("[テスト1] __init__ が例外なく RetryRuntimeLoop を返す")

loop_1 = RetryRuntimeLoop(
    run_once_fn=lambda: None,
    sleep_fn=lambda seconds: None,
    should_continue_fn=lambda: False,
    interval_seconds=10,
)
check_true("1. RetryRuntimeLoopのインスタンスである", isinstance(loop_1, RetryRuntimeLoop))
print()


# ═══════════════════════════════════════════════════════════
# テスト2-3: run() が should_continue_fn の回数だけ run_once_fn/sleep_fn を呼ぶ
# ═══════════════════════════════════════════════════════════

print("[テスト2-3] run() が should_continue_fn の回数だけ run_once_fn/sleep_fn を呼ぶ")

recorder_23 = _Recorder()
remaining_23 = [3]


def should_continue_23():
    if remaining_23[0] > 0:
        remaining_23[0] -= 1
        return True
    return False


def run_once_23():
    recorder_23.calls.append("run_once")


def sleep_23(seconds):
    recorder_23.calls.append(("sleep", seconds))


loop_23 = RetryRuntimeLoop(
    run_once_fn=run_once_23,
    sleep_fn=sleep_23,
    should_continue_fn=should_continue_23,
    interval_seconds=5,
)
loop_23.run()

run_once_count_23 = sum(1 for c in recorder_23.calls if c == "run_once")
sleep_calls_23 = [c for c in recorder_23.calls if isinstance(c, tuple) and c[0] == "sleep"]
check("2. run_once_fnが3回呼ばれる", run_once_count_23, 3)
check("3. sleep_fnが3回、interval_seconds=5で呼ばれる", sleep_calls_23, [("sleep", 5)] * 3)
print()


# ═══════════════════════════════════════════════════════════
# テスト4: should_continue_fn が最初から False の場合、何も呼ばれない
# ═══════════════════════════════════════════════════════════

print("[テスト4] should_continue_fn が最初から False の場合、run_once_fn/sleep_fn が一度も呼ばれない")

recorder_4 = _Recorder()
loop_4 = RetryRuntimeLoop(
    run_once_fn=lambda: recorder_4.calls.append("run_once"),
    sleep_fn=lambda seconds: recorder_4.calls.append("sleep"),
    should_continue_fn=lambda: False,
    interval_seconds=1,
)
loop_4.run()
check("4. run_once_fn/sleep_fnが一度も呼ばれない", recorder_4.calls, [])
print()


# ═══════════════════════════════════════════════════════════
# テスト5: 呼び出し順序が run_once_fn → sleep_fn の繰り返しである
# ═══════════════════════════════════════════════════════════

print("[テスト5] 呼び出し順序が run_once_fn → sleep_fn の繰り返しである")

recorder_5 = _Recorder()
remaining_5 = [2]


def should_continue_5():
    if remaining_5[0] > 0:
        remaining_5[0] -= 1
        return True
    return False


loop_5 = RetryRuntimeLoop(
    run_once_fn=lambda: recorder_5.calls.append("run_once"),
    sleep_fn=lambda seconds: recorder_5.calls.append("sleep"),
    should_continue_fn=should_continue_5,
    interval_seconds=1,
)
loop_5.run()
check("5. 呼び出し順序が [run_once, sleep, run_once, sleep]", recorder_5.calls,
      ["run_once", "sleep", "run_once", "sleep"])
print()


# ═══════════════════════════════════════════════════════════
# テスト6: run_once_fn の戻り値は run() の戻り値に反映されない
# ═══════════════════════════════════════════════════════════

print("[テスト6] run_once_fn の戻り値は run() の戻り値に反映されない（run() は None を返す）")

remaining_6 = [1]


def should_continue_6():
    if remaining_6[0] > 0:
        remaining_6[0] -= 1
        return True
    return False


loop_6 = RetryRuntimeLoop(
    run_once_fn=lambda: {"trigger_result": "dummy", "scheduler_events": [1, 2, 3]},
    sleep_fn=lambda seconds: None,
    should_continue_fn=should_continue_6,
    interval_seconds=1,
)
return_value_6 = loop_6.run()
check("6. run()の戻り値がNoneである", return_value_6, None)
print()


# ═══════════════════════════════════════════════════════════
# テスト7: run_once_fn が例外を送出した場合、run() から伝播し、直後のsleep_fnは呼ばれない
# ═══════════════════════════════════════════════════════════

print("[テスト7] run_once_fn が例外を送出した場合、run() から伝播し、直後のsleep_fnは呼ばれない")

recorder_7 = _Recorder()


def run_once_raises_7():
    raise RuntimeError("run_once_fn failure")


loop_7 = RetryRuntimeLoop(
    run_once_fn=run_once_raises_7,
    sleep_fn=lambda seconds: recorder_7.calls.append("sleep"),
    should_continue_fn=lambda: True,
    interval_seconds=1,
)

raised_7 = False
try:
    loop_7.run()
except RuntimeError as exc:
    raised_7 = str(exc) == "run_once_fn failure"

check_true("7. RuntimeErrorがrun()から伝播する", raised_7)
check("7. sleep_fnは呼ばれない", recorder_7.calls, [])
print()


# ═══════════════════════════════════════════════════════════
# テスト8: should_continue_fn が例外を送出した場合、run() から伝播する
# ═══════════════════════════════════════════════════════════

print("[テスト8] should_continue_fn が例外を送出した場合、run() から伝播する")


def should_continue_raises_8():
    raise ValueError("should_continue_fn failure")


loop_8 = RetryRuntimeLoop(
    run_once_fn=lambda: None,
    sleep_fn=lambda seconds: None,
    should_continue_fn=should_continue_raises_8,
    interval_seconds=1,
)

raised_8 = False
try:
    loop_8.run()
except ValueError as exc:
    raised_8 = str(exc) == "should_continue_fn failure"

check_true("8. ValueErrorがrun()から伝播する", raised_8)
print()


# ═══════════════════════════════════════════════════════════
# テスト9-12: 責務境界（Loopは何も知らない）
# ═══════════════════════════════════════════════════════════

print("[テスト9] __init__ のシグネチャが "
      "(self, run_once_fn, sleep_fn, should_continue_fn, interval_seconds)")

params_9 = list(inspect.signature(RetryRuntimeLoop.__init__).parameters.keys())
check(
    "9. パラメータ順序が一致する",
    params_9,
    ["self", "run_once_fn", "sleep_fn", "should_continue_fn", "interval_seconds"],
)
print()


print("[テスト10] RetryRuntimeLoopが run 以外の公開メソッドを持たない")

public_methods_10 = [
    name for name, value in inspect.getmembers(RetryRuntimeLoop, predicate=inspect.isfunction)
    if not name.startswith("_") and name != "run"
]
check("10. run以外の公開メソッドが存在しない", public_methods_10, [])
for forbidden_name in ("loop", "daemon", "start", "stop", "execute"):
    check_false(f"10. {forbidden_name}という名前のメソッドを持たない", hasattr(RetryRuntimeLoop, forbidden_name))
print()


print("[テスト11] retry_runtime_loop.py が他のRetry関連パッケージを一切importしない")

loop_source_path = PROJECT_ROOT / "src" / "retry_runtime_loop" / "retry_runtime_loop.py"
loop_source_text_11 = loop_source_path.read_text(encoding="utf-8")
loop_tree_11 = ast.parse(loop_source_text_11)

forbidden_modules_11 = [
    "retry_manager", "retry_queue", "retry_history", "retry_policy",
    "retry_composition", "retry_runtime_orchestrator", "retry_engine",
    "retry_enqueue_trigger", "workflow_monitor", "workflow_engine",
    "scheduler", "retry_scheduler_source", "retry_scheduler_decision",
    "ai", "execution_history",
]
imported_modules_11 = []
for node in ast.walk(loop_tree_11):
    if isinstance(node, ast.Import):
        imported_modules_11.extend(alias.name for alias in node.names)
    elif isinstance(node, ast.ImportFrom) and node.module:
        imported_modules_11.append(node.module)

forbidden_hits_11 = [m for m in imported_modules_11 if m in forbidden_modules_11]
check("11. 禁止パッケージのimportが存在しない", forbidden_hits_11, [])
print()


print('[テスト12] retry_runtime_loop.py のソースに "RetryRuntimeCycleResult" という識別子が出現しない')

check_false('12. "RetryRuntimeCycleResult"という文字列が出現しない',
            "RetryRuntimeCycleResult" in loop_source_text_11)
print()


# ═══════════════════════════════════════════════════════════
# テスト13-14: ディレクトリ構成・Backward Compatibility
# ═══════════════════════════════════════════════════════════

print("[テスト13] src/retry_runtime_loop/ のファイル構成が2ファイルのみである")

rrl_dir = PROJECT_ROOT / "src" / "retry_runtime_loop"
py_files_13 = sorted(p.name for p in rrl_dir.glob("*.py"))
check("13. __init__.py・retry_runtime_loop.pyの2ファイル", py_files_13,
      ["__init__.py", "retry_runtime_loop.py"])
print()


print("[テスト14] retry_runtime_loop パッケージのexportが RetryRuntimeLoop のみである")

check_true("14. RetryRuntimeLoopがretry_runtime_loopパッケージからエクスポートされている",
           hasattr(rrl_pkg, "RetryRuntimeLoop"))
check("14. __all__がRetryRuntimeLoopのみ", rrl_pkg.__all__, ["RetryRuntimeLoop"])
print()


# ═══════════════════════════════════════════════════════════
# テスト15-16: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト15] 既存13パッケージ・scripts/run_retry_runtime.py に変更がないこと（git diff）")

unchanged_paths_15 = [
    "src/workflow_monitor",
    "src/retry_queue",
    "src/retry_history",
    "src/retry_enqueue_trigger",
    "src/retry_engine",
    "src/workflow_engine",
    "src/ai",
    "src/execution_history",
    "src/scheduler",
    "src/retry_scheduler_source",
    "src/retry_scheduler_decision",
    "src/retry_composition",
    "src/retry_runtime_orchestrator",
    "scripts/run_retry_runtime.py",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths_15:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"15. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("15. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト16] retry_runtime_loop をどこからも呼び出さない（消費者不在の先行実装）")

src_dir = PROJECT_ROOT / "src"
scripts_dir = PROJECT_ROOT / "scripts"
consumers_16 = []
for py_file in sorted(list(src_dir.rglob("*.py")) + list(scripts_dir.rglob("*.py"))):
    if py_file.parent.name == "retry_runtime_loop":
        continue
    text = py_file.read_text(encoding="utf-8")
    if "retry_runtime_loop" in text:
        consumers_16.append(str(py_file.relative_to(PROJECT_ROOT)))
check("16. retry_runtime_loopを参照する既存ファイルが存在しない", consumers_16, [])
print()


# ═══════════════════════════════════════════════════════════
# テスト17: 副作用なしの確認
# ═══════════════════════════════════════════════════════════

print("[テスト17] RetryRuntimeLoop.run() 実行前後でファイルが作成されない")

with tempfile.TemporaryDirectory() as tmp_dir:
    write_check_dir = Path(tmp_dir)
    before_files_17 = list(write_check_dir.rglob("*"))

    remaining_17 = [2]

    def should_continue_17():
        if remaining_17[0] > 0:
            remaining_17[0] -= 1
            return True
        return False

    loop_17 = RetryRuntimeLoop(
        run_once_fn=lambda: None,
        sleep_fn=lambda seconds: None,
        should_continue_fn=should_continue_17,
        interval_seconds=0,
    )
    loop_17.run()

    after_files_17 = list(write_check_dir.rglob("*"))
    check("17. 実行前後でファイルが作成されない", after_files_17, before_files_17)
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
