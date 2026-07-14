"""
E2E テスト: v6.0.0 Retry Runtime Lock Foundation

注意（Code Review Required Change対応）:
    本テストのテスト13〜18は、一時ディレクトリではなく実プロジェクトの
    `.run/retry_runtime.lock`（本番のscripts/run_retry_runtime.pyが実際に
    使用するのと同じパス）を直接作成・削除する。そのため、本テストは
    本物のRetry Runtimeプロセス（`--loop`による常駐実行等）が同時に
    稼働していない環境でのみ実行すること。同時に稼働している状態で本テストを
    実行すると、稼働中プロセスが正当に保持しているロックファイルを誤って
    削除してしまうおそれがある。

注意2（Release 6.1 Regression Test Maintenance対応、2026-07-14）:
    v6.1.0（Graceful Shutdown Foundation）で、--loop実行時にRetryRuntimeLoopへ渡す
    sleep_fnがtime.sleep直結からRetryRuntimeShutdown.interruptible_sleep経由へ変更された
    （docs/CHANGELOG.md [KI-29]）。これに伴い、本テストのrun_main_with_argv()ヘルパーは、
    run_retry_runtime.time.sleepの直接monkeypatchから、run_retry_runtime.RetryRuntimeShutdown
    クラス自体をFakeへ差し替える方式へ変更した（Implementation Detailへの追従のみ。
    テスト意図・カバレッジ・Assertion・テストシナリオは維持している。本番コードの変更なし）。

テストシナリオ（docs/design/retry_runtime_lock_foundation.md 対応）:
    ── RetryRuntimeLock 単体 ──
    1.  acquire()でロックファイルが新規作成される
    2.  acquire()で自プロセスのPIDが書き込まれる
    3.  取得済みロックへのacquire()はRetryRuntimeLockErrorを送出する
    4.  RetryRuntimeLockErrorのメッセージにロックファイルのパスが含まれる
    5.  release()でロックファイルが削除される
    6.  release()は未取得状態で呼んでもエラーにならない（べき等）
    7.  with文でacquire/releaseが自動的に行われる（正常終了時）
    8.  with文内で例外が発生してもrelease()が呼ばれる
    9.  ロックファイルの親ディレクトリが存在しない場合、acquire()が自動作成する
    9b. acquire()内でos.write()が失敗した場合でも、ロックファイルが残らない
        （Code Review Required Change対応）
    10. RetryRuntimeLockは他のretry_*パッケージに依存しない（依存方向確認）

    ── scripts/run_retry_runtime.py 配線 ──
    11. main()のソースに"with lock"が含まれる
    12. main()がRetryRuntimeLockErrorを専用に捕捉している
    13. 単発実行（Fake）が正常にロックを取得・解放し、2回連続実行できる
    14. --loop実行（Fake）でも同じロックが使われ、2回連続実行できる

    ── 実CLI ──
    15. ロックファイルが事前に存在する状態でCLIを起動すると非0終了する
    16. その際のエラーメッセージにロックファイルパスと対処方法が含まれる
    17. ロック取得失敗時はRetry Runtime本体の実行結果が出力されない（CompositionRoot等に到達しない）
    18. 正常時（ロック未保持）はCLI実行が成功し、実行後にロックファイルが残らない

    ── Backward Compatibility / Zero Diff ──
    19. RetryCompositionRoot無変更（git diff）
    20. RetryRuntimeOrchestrator無変更（git diff）
    21. RetryRuntimeLoop無変更（git diff）
    22. RetryManager（retry_engine）無変更（git diff）
    23. RetryEnqueueTrigger無変更（git diff）
    24. format_summary()の公開契約無変更（シグネチャ）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_0_0_retry_runtime_lock_foundation.py
"""
import contextlib
import importlib.util
import inspect
import io
import os
import shutil
import subprocess
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
print("v6.0.0 Retry Runtime Lock Foundation E2E テスト")
print("=" * 60)
print()

from retry_composition import RetryCompositionRoot as _RealRetryCompositionRoot
from retry_engine import RetryManager as _RealRetryManager
from retry_enqueue_trigger import RetryEnqueueTrigger as _RealRetryEnqueueTrigger
from retry_enqueue_trigger import RetryEnqueueTriggerResult
from retry_runtime_lock import RetryRuntimeLock, RetryRuntimeLockError
import retry_runtime_lock.retry_runtime_lock as _lock_module
from retry_runtime_loop import RetryRuntimeLoop as _RealRetryRuntimeLoop
from retry_runtime_orchestrator import RetryRuntimeCycleResult, RetryRuntimeOrchestrator as _RealRetryRuntimeOrchestrator


SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_retry_runtime.py"
REAL_LOCK_PATH = PROJECT_ROOT / ".run" / "retry_runtime.lock"

spec = importlib.util.spec_from_file_location("run_retry_runtime_v600", SCRIPT_PATH)
run_retry_runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_retry_runtime)


def ensure_real_lock_absent():
    REAL_LOCK_PATH.unlink(missing_ok=True)


ensure_real_lock_absent()


# ─── Fake群（Loop wiring テスト用、v5.9.0テストと同型） ───

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


class _StopLoopMarker(Exception):
    """テスト専用: Loopを能動的に止めるためのSentinel例外（本番コードには存在しない）。"""


def _make_counting_sleep(raise_after=None, raise_exc=None):
    calls: list = []

    def _sleep(seconds):
        calls.append(seconds)
        if raise_after is not None and len(calls) >= raise_after:
            raise raise_exc

    _sleep.calls = calls
    return _sleep


class _FakeShutdown:
    """
    テスト用Fake：run_retry_runtime.RetryRuntimeShutdownへ差し替える（Release 6.1
    Regression Test Maintenance、docs/CHANGELOG.md [KI-29]）。install()/uninstall()は
    記録のみのno-op。interruptible_sleep()は、run_main_with_argv()から渡された
    sleep_fn（従来どおり_make_counting_sleep()が返す関数）へそのまま委譲する。
    """

    def __init__(self, poll_interval_seconds: float = 0.5):
        self.installed = False
        self.uninstalled = False
        self.sleep_fn = None
        self._requested = False
        self._signal_name = None

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
        if self.sleep_fn is not None:
            self.sleep_fn(seconds)


def run_main_with_argv(argv, sleep_fn=None):
    """
    v6.1.0（Graceful Shutdown Foundation）で--loop実行時のsleep_fnがtime.sleep直結から
    RetryRuntimeShutdown.interruptible_sleep経由へ変更されたことに伴い、run_retry_runtime.time.sleep
    の直接monkeypatchから、run_retry_runtime.RetryRuntimeShutdownクラス自体をFakeへ差し替える
    方式へ変更した（Implementation Detailへの追従のみ。docs/CHANGELOG.md [KI-29]）。
    """
    _FakeOrchestrator.calls = []
    original_root = run_retry_runtime.RetryCompositionRoot
    original_orchestrator = run_retry_runtime.RetryRuntimeOrchestrator
    original_shutdown_cls = run_retry_runtime.RetryRuntimeShutdown
    original_argv = sys.argv

    def _shutdown_factory(*factory_args, **factory_kwargs):
        fake = _FakeShutdown(*factory_args, **factory_kwargs)
        fake.sleep_fn = sleep_fn
        return fake

    run_retry_runtime.RetryCompositionRoot = _FakeCompositionRoot
    run_retry_runtime.RetryRuntimeOrchestrator = _FakeOrchestrator
    run_retry_runtime.RetryRuntimeShutdown = _shutdown_factory
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
# テスト1-10: RetryRuntimeLock 単体
# ═══════════════════════════════════════════════════════════

with tempfile.TemporaryDirectory() as tmp_dir:
    tmp_path = Path(tmp_dir) / "sub" / "retry_runtime.lock"

    print("[テスト1] acquire()でロックファイルが新規作成される")
    lock_1 = RetryRuntimeLock(lock_path=tmp_path)
    check_false("1. 事前にロックファイルが存在しない", tmp_path.exists())
    lock_1.acquire()
    check_true("1. acquire()後にロックファイルが存在する", tmp_path.exists())
    print()

    print("[テスト2] acquire()で自プロセスのPIDが書き込まれる")
    content_2 = tmp_path.read_text(encoding="utf-8")
    check("2. ロックファイルの内容が自プロセスのPID", content_2, str(os.getpid()))
    print()

    print("[テスト3] 取得済みロックへのacquire()はRetryRuntimeLockErrorを送出する")
    lock_3 = RetryRuntimeLock(lock_path=tmp_path)
    raised_3 = None
    try:
        lock_3.acquire()
    except RetryRuntimeLockError as e:
        raised_3 = e
    check_true("3. RetryRuntimeLockErrorが送出される", raised_3 is not None)
    print()

    print("[テスト4] RetryRuntimeLockErrorのメッセージにロックファイルのパスが含まれる")
    check_contains("4. エラーメッセージにパスが含まれる", str(raised_3), str(tmp_path))
    print()

    print("[テスト5] release()でロックファイルが削除される")
    lock_1.release()
    check_false("5. release()後にロックファイルが存在しない", tmp_path.exists())
    print()

    print("[テスト6] release()は未取得状態で呼んでもエラーにならない（べき等）")
    raised_6 = None
    try:
        lock_1.release()
        lock_1.release()
    except Exception as e:  # noqa: BLE001
        raised_6 = e
    check("6. 例外が発生しない", raised_6, None)
    print()

    print("[テスト7] with文でacquire/releaseが自動的に行われる（正常終了時）")
    lock_7 = RetryRuntimeLock(lock_path=tmp_path)
    with lock_7:
        check_true("7. with文内でロックファイルが存在する", tmp_path.exists())
    check_false("7. with文を抜けるとロックファイルが削除される", tmp_path.exists())
    print()

    print("[テスト8] with文内で例外が発生してもrelease()が呼ばれる")

    class _CustomError8(Exception):
        pass

    lock_8 = RetryRuntimeLock(lock_path=tmp_path)
    raised_8 = None
    try:
        with lock_8:
            raise _CustomError8("boom")
    except _CustomError8 as e:
        raised_8 = e
    check_true("8. 例外がwith文の外へ伝播する", isinstance(raised_8, _CustomError8))
    check_false("8. 例外発生時もロックファイルが削除される", tmp_path.exists())
    print()

    print("[テスト9] ロックファイルの親ディレクトリが存在しない場合、acquire()が自動作成する")
    nested_path_9 = Path(tmp_dir) / "not_yet_created" / "nested" / "retry_runtime.lock"
    check_false("9. 事前に親ディレクトリが存在しない", nested_path_9.parent.exists())
    lock_9 = RetryRuntimeLock(lock_path=nested_path_9)
    lock_9.acquire()
    check_true("9. acquire()が親ディレクトリごと作成する", nested_path_9.exists())
    lock_9.release()
    print()

    print("[テスト9b] acquire()内でos.write()が失敗した場合でも、ロックファイルが残らない")
    nested_path_9b = Path(tmp_dir) / "write_failure" / "retry_runtime.lock"
    lock_9b = RetryRuntimeLock(lock_path=nested_path_9b)
    original_os_write = _lock_module.os.write

    def _raise_on_write(fd, data):
        # fdのcloseは行わない。production側のacquire()がexcept節でos.close(fd)を
        # 行う想定であり、ここで先にcloseすると二重closeになってしまうため。
        raise OSError("simulated write failure")

    _lock_module.os.write = _raise_on_write
    raised_9b = None
    try:
        lock_9b.acquire()
    except OSError as e:
        raised_9b = e
    finally:
        _lock_module.os.write = original_os_write
    check_true("9b. os.write失敗時は例外が伝播する", raised_9b is not None)
    check_false("9b. os.write失敗時もロックファイルが残らない", nested_path_9b.exists())
    print()

    print("[テスト10] RetryRuntimeLockは他のretry_*パッケージに依存しない（依存方向確認）")
    lock_source_10 = inspect.getsource(_lock_module)
    for forbidden in ("retry_composition", "retry_runtime_orchestrator", "retry_runtime_loop", "retry_engine"):
        check_not_contains(f"10. retry_runtime_lockが{forbidden}をimportしない", lock_source_10, forbidden)
    print()


# ═══════════════════════════════════════════════════════════
# テスト11-14: scripts/run_retry_runtime.py 配線
# ═══════════════════════════════════════════════════════════

print("[テスト11] main()のソースに\"with lock\"が含まれる")

main_source_11 = inspect.getsource(run_retry_runtime.main)
check_contains("11. main()が\"with lock:\"を含む", main_source_11, "with lock:")
print()


print("[テスト12] main()がRetryRuntimeLockErrorを専用に捕捉している")

check_contains("12. main()が\"except RetryRuntimeLockError\"を含む", main_source_11, "except RetryRuntimeLockError")
check_contains("12. ロック失敗時にsys.exit(1)する", main_source_11, "sys.exit(1)")
print()


print("[テスト13] 単発実行（Fake）が正常にロックを取得・解放し、2回連続実行できる")

ensure_real_lock_absent()
stdout_13a, raised_13a = run_main_with_argv([])
check("13. 1回目: 例外が伝播しない", raised_13a, None)
check_false("13. 1回目実行後にロックファイルが残らない", REAL_LOCK_PATH.exists())
stdout_13b, raised_13b = run_main_with_argv([])
check("13. 2回目: 例外が伝播しない（ロックが解放されている証拠）", raised_13b, None)
check_false("13. 2回目実行後もロックファイルが残らない", REAL_LOCK_PATH.exists())
print()


print("[テスト14] --loop実行（Fake）でも同じロックが使われ、2回連続実行できる")

sleep_14a = _make_counting_sleep(raise_after=1, raise_exc=_StopLoopMarker())
stdout_14a, raised_14a = run_main_with_argv(["--loop"], sleep_fn=sleep_14a)
check_true("14. 1回目: Sentinel例外が伝播する（Loop停止）", isinstance(raised_14a, _StopLoopMarker))
check_false("14. 1回目実行後にロックファイルが残らない", REAL_LOCK_PATH.exists())

sleep_14b = _make_counting_sleep(raise_after=1, raise_exc=_StopLoopMarker())
stdout_14b, raised_14b = run_main_with_argv(["--loop"], sleep_fn=sleep_14b)
check_true("14. 2回目: Sentinel例外が伝播する（ロックが解放されている証拠）", isinstance(raised_14b, _StopLoopMarker))
check_false("14. 2回目実行後もロックファイルが残らない", REAL_LOCK_PATH.exists())
print()


# ═══════════════════════════════════════════════════════════
# テスト15-18: 実CLI
# ═══════════════════════════════════════════════════════════

print("[テスト15] ロックファイルが事前に存在する状態でCLIを起動すると非0終了する")

ensure_real_lock_absent()
REAL_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
REAL_LOCK_PATH.write_text("999999999", encoding="utf-8")
try:
    completed_15 = run_cli([])
    check_true("15. returncodeが0ではない", completed_15.returncode != 0)
finally:
    ensure_real_lock_absent()
print()


print("[テスト16] その際のエラーメッセージにロックファイルパスと対処方法が含まれる")

REAL_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
REAL_LOCK_PATH.write_text("999999999", encoding="utf-8")
try:
    completed_16 = run_cli([])
    check_contains("16. 標準出力にlock fileパスが含まれる", completed_16.stdout, str(REAL_LOCK_PATH))
    check_contains("16. 標準出力に手動削除の案内が含まれる", completed_16.stdout, "手動削除")
finally:
    ensure_real_lock_absent()
print()


print("[テスト17] ロック取得失敗時はRetry Runtime本体の実行結果が出力されない")

REAL_LOCK_PATH.parent.mkdir(parents=True, exist_ok=True)
REAL_LOCK_PATH.write_text("999999999", encoding="utf-8")
try:
    completed_17 = run_cli([])
    check_not_contains("17. 標準出力に\"Retry Runtime 実行結果\"が含まれない", completed_17.stdout, "Retry Runtime 実行結果")
    check_not_contains("17. 標準出力に単発実行の見出しも含まれない（CompositionRoot構築前に失敗）", completed_17.stdout, "1サイクルのみ実行")
finally:
    ensure_real_lock_absent()
print()


print("[テスト18] 正常時（ロック未保持）はCLI実行が成功し、実行後にロックファイルが残らない")

ensure_real_lock_absent()
completed_18 = run_cli([])
check("18. returncodeが0", completed_18.returncode, 0)
check_false("18. 実行後にロックファイルが残らない", REAL_LOCK_PATH.exists())
print()


# ═══════════════════════════════════════════════════════════
# テスト19-24: Backward Compatibility / Zero Diff
# ═══════════════════════════════════════════════════════════

print("[テスト19-23] 既存主要コンポーネントに変更がないこと（git diff）")

unchanged_paths_19_23 = [
    "src/retry_composition",
    "src/retry_runtime_orchestrator",
    "src/retry_runtime_loop",
    "src/retry_engine",
    "src/retry_enqueue_trigger",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths_19_23:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"19-23. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("19-23. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト24] format_summary()の公開契約が無変更（シグネチャ）")

sig_24 = inspect.signature(run_retry_runtime.format_summary)
check("24. パラメータがresultのみ", list(sig_24.parameters.keys()), ["result"])
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
