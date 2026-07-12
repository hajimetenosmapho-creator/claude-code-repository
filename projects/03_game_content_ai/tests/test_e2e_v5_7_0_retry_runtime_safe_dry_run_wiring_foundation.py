"""
E2E テスト: v5.7.0 Retry Runtime Safe Dry Run Wiring Foundation

テストシナリオ（docs/design/retry_runtime_safe_dry_run_wiring_foundation.md 対応）:
    ── スクリプトファイルの存在・モジュールロード ──
    1.  scripts/run_retry_runtime.py が存在する
    2.  importlibでモジュールをロードでき、main() / format_summary() を持つ

    ── format_summary()が無改修であること（最重要の設計制約） ──
    3.  format_summary()のシグネチャが(result)のみ（dry_run引数を持たない）
    4.  format_summary()がstrを返す
    5.  format_summary()の出力に主要カテゴリ（Enqueue/Scheduler/Execution/Removal/
        Cleanup/TerminalCleanup/History）がすべて含まれる
    6.  format_summary()の出力にtrigger_resultの各件数が反映される
    7.  format_summary()の出力に"[DRY RUN MODE]"という文字列を含む分岐が存在しない
        （dry_run表示はformat_summary()の責務ではないことの確認）

    ── RetryRuntimeCycleResultが無改修であること ──
    8.  RetryRuntimeCycleResultがdry_runフィールドを持たない

    ── CLI層の責務・argparse導入範囲（main()内で完結すること） ──
    9.  parse_args()という独立関数が存在しない（YAGNI、main()内で直接処理する方針）
    10. main()のソースコード内にargparseの使用（ArgumentParser生成・add_argument・
        parse_args呼び出し）が含まれる
    11. モジュールのトップレベルではargparseがimportされていない
        （main()内のローカルimportに限定されていることの確認）

    ── scripts層の責務・静的import検査（既存部分の非破壊確認） ──
    12. retry_engineのDecider/Executor（RetryQueueUpdateDecider等）を直接importしない
    13. retry_composition / retry_runtime_orchestrator 以外のRetry関連パッケージを
        直接importしない
    14. isinstance(...) によるGate判定コード（NullRetryManager等）を持たない

    ── main()がrun_once()へdry_runを伝播すること（配線の核心、モック検証） ──
    15. --dry-run未指定時、run_once(dry_run=False)が呼ばれる
    16. --dry-run指定時、run_once(dry_run=True)が呼ばれる
    17. --dry-run指定時、標準出力に"[DRY RUN MODE]"が含まれる
    18. --dry-run未指定時、標準出力に"[DRY RUN MODE]"が含まれない
    19. --dry-run指定の有無に関わらずformat_summary()が呼ばれ、その戻り値が
        標準出力に含まれる（Summary自体は変化しないことの確認）

    ── サブプロセス実行（実CLI呼び出し、全Gate無効） ──
    20. --dry-run未指定時、returncodeが0になり従来どおりのサマリーが出力される
    21. --dry-run指定時、returncodeが0になり[DRY RUN MODE]とサマリーの両方が出力される
    22. --dry-run指定時も、全Gate無効時はlogs/execution_history/に新規ファイルが
        作られない
    23. 不正な環境変数（RETRY_QUEUE_MAX_SIZE）指定時、--dry-run有無に関わらず
        returncodeが非0になり、標準エラー出力にtracebackが出力される（fail-fast維持）

    ── Architecture Guard（本Releaseの変更範囲がscripts/run_retry_runtime.pyのみであること） ──
    24. 既存13パッケージ（workflow_monitor 〜 retry_runtime_orchestrator）に
        変更がないこと（git diff）
    25. 既存の他scripts（run_workflow_engine.py等）に変更がないこと（git diff）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v5_7_0_retry_runtime_safe_dry_run_wiring_foundation.py
"""
import importlib.util
import inspect
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


def check_contains(label: str, text: str, keyword: str):
    check(label, keyword in str(text), True)


def check_not_contains(label: str, text: str, keyword: str):
    check(label, keyword in str(text), False)


print("=" * 60)
print("v5.7.0 Retry Runtime Safe Dry Run Wiring Foundation E2E テスト")
print("=" * 60)
print()

from retry_engine import DEFAULT_TARGET_STATUSES, RetryPolicy
from retry_enqueue_trigger import RetryEnqueueTriggerResult
from retry_runtime_orchestrator import RetryRuntimeCycleResult


# ═══════════════════════════════════════════════════════════
# テスト1-2: スクリプトファイルの存在・モジュールロード
# ═══════════════════════════════════════════════════════════

print("[テスト1] scripts/run_retry_runtime.py が存在する")

SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_retry_runtime.py"
check_true("1. run_retry_runtime.py が存在する", SCRIPT_PATH.exists())
print()


print("[テスト2] importlibでモジュールをロードでき、main() / format_summary() を持つ")

spec = importlib.util.spec_from_file_location("run_retry_runtime", SCRIPT_PATH)
run_retry_runtime = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run_retry_runtime)

check_true("2. main属性を持つ", hasattr(run_retry_runtime, "main"))
check_true("2. format_summary属性を持つ", hasattr(run_retry_runtime, "format_summary"))
print()


# ═══════════════════════════════════════════════════════════
# テスト3-7: format_summary()が無改修であること
# ═══════════════════════════════════════════════════════════

print("[テスト3] format_summary()のシグネチャが(result)のみ（dry_run引数を持たない）")

params_3 = list(inspect.signature(run_retry_runtime.format_summary).parameters.keys())
check("3. パラメータがresultのみ", params_3, ["result"])
print()


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

print("[テスト4] format_summary()がstrを返す")

summary_text = run_retry_runtime.format_summary(result_sample)
check_true("4. 戻り値がstr", isinstance(summary_text, str))
print()


print("[テスト5] format_summary()の出力に主要カテゴリがすべて含まれる")

for keyword in ("Enqueue", "Scheduler", "Execution", "Removal", "Cleanup", "TerminalCleanup", "History"):
    check_contains(f"5. '{keyword}' が出力に含まれる", summary_text, keyword)
print()


print("[テスト6] format_summary()の出力にtrigger_resultの各件数が反映される")

check_contains("6. scanned=7 が含まれる", summary_text, "scanned=7")
check_contains("6. enqueued=2 が含まれる", summary_text, "enqueued=2")
check_contains("6. skipped_existing=3 が含まれる", summary_text, "skipped_existing=3")
check_contains("6. skipped_status=1 が含まれる", summary_text, "skipped_status=1")
check_contains("6. failed=1 が含まれる", summary_text, "failed=1")
check_contains("6. candidates=2 (scheduler_events件数) が含まれる", summary_text, "candidates=2")
check_contains("6. executed=1 (execution_results件数) が含まれる", summary_text, "executed=1")
print()


print("[テスト7] format_summary()にDRY RUN表示の分岐が存在しない")

format_summary_source = inspect.getsource(run_retry_runtime.format_summary)
check_not_contains("7. format_summary()のソースに'DRY RUN'が含まれない", format_summary_source, "DRY RUN")
check_not_contains("7. format_summary()のソースに'dry_run'が含まれない", format_summary_source, "dry_run")
print()


# ═══════════════════════════════════════════════════════════
# テスト8: RetryRuntimeCycleResultが無改修であること
# ═══════════════════════════════════════════════════════════

print("[テスト8] RetryRuntimeCycleResultがdry_runフィールドを持たない")

import dataclasses

field_names_8 = {f.name for f in dataclasses.fields(RetryRuntimeCycleResult)}
check_false("8. dry_runフィールドが存在しない", "dry_run" in field_names_8)
print()


# ═══════════════════════════════════════════════════════════
# テスト9-11: CLI層の責務・argparse導入範囲
# ═══════════════════════════════════════════════════════════

print("[テスト9] parse_args()という独立関数が存在しない（YAGNI）")

check_false("9. parse_args属性を持たない", hasattr(run_retry_runtime, "parse_args"))
print()


print("[テスト10] main()のソースコード内にargparseの使用が含まれる")

main_source = inspect.getsource(run_retry_runtime.main)
check_contains("10. main()内に'import argparse'が含まれる", main_source, "import argparse")
check_contains("10. main()内に'ArgumentParser'が含まれる", main_source, "ArgumentParser")
check_contains("10. main()内に'--dry-run'が含まれる", main_source, "--dry-run")
check_contains("10. main()内に'parse_args'が含まれる", main_source, "parse_args")
print()


print("[テスト11] モジュールのトップレベルではargparseがimportされていない")

script_source = SCRIPT_PATH.read_text(encoding="utf-8")
top_level_lines = "\n".join(
    line for line in script_source.splitlines()
    if (line.startswith("from ") or line.startswith("import ")) and not line.startswith(" ")
)
check_false("11. トップレベルに'import argparse'が含まれない", "import argparse" in top_level_lines)
print()


# ═══════════════════════════════════════════════════════════
# テスト12-14: scripts層の責務・静的import検査（既存部分の非破壊確認）
# ═══════════════════════════════════════════════════════════

import_lines = "\n".join(
    line for line in script_source.splitlines()
    if line.strip().startswith("from ") or line.strip().startswith("import ")
)

print("[テスト12] retry_engineのDecider/Executorを直接importしない")

for forbidden in (
    "RetryQueueUpdateDecider", "RetryQueueRemovalExecutor", "RetryQueueCleanupDecider",
    "RetryQueueCleanupExecutor", "RetryQueueTerminalCleanupDecider",
    "RetryQueueTerminalCleanupExecutor", "RetryHistoryRecordExecutor", "RetryManager",
):
    check_false(f"12. {forbidden} がimportされていない", forbidden in import_lines)
print()


print("[テスト13] retry_composition / retry_runtime_orchestrator 以外のRetry関連パッケージを直接importしない")

for forbidden_module in (
    "retry_engine", "retry_queue", "retry_history", "retry_enqueue_trigger",
    "retry_scheduler_source", "retry_scheduler_decision", "scheduler", "workflow_monitor",
    "workflow_engine",
):
    check_false(
        f"13. 'from {forbidden_module}' がimportされていない",
        f"from {forbidden_module} " in import_lines or f"from {forbidden_module}\n" in import_lines,
    )
check_contains("13. retry_composition はimportされている", import_lines, "from retry_composition import")
check_contains("13. retry_runtime_orchestrator はimportされている", import_lines, "from retry_runtime_orchestrator import")
print()


print("[テスト14] isinstance(...) によるGate判定コードを持たない")

check_false("14. isinstance(が使われていない（コード本体にGate判定を持たない）", "isinstance(" in script_source)
check_false("14. NullRetryManagerがimportされていない（型そのものを知らない）", "NullRetryManager" in import_lines)
print()


# ═══════════════════════════════════════════════════════════
# テスト15-19: main()がrun_once()へdry_runを伝播すること（モック検証）
# ═══════════════════════════════════════════════════════════

print("[テスト15-19] main()の配線検証（RetryCompositionRoot / RetryRuntimeOrchestratorをFakeへ差し替え）")

import io
import contextlib


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


def run_main_with_argv(argv: list) -> str:
    _FakeOrchestrator.calls = []
    original_root = run_retry_runtime.RetryCompositionRoot
    original_orchestrator = run_retry_runtime.RetryRuntimeOrchestrator
    original_argv = sys.argv
    run_retry_runtime.RetryCompositionRoot = _FakeCompositionRoot
    run_retry_runtime.RetryRuntimeOrchestrator = _FakeOrchestrator
    sys.argv = ["run_retry_runtime.py"] + argv
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            run_retry_runtime.main()
    finally:
        run_retry_runtime.RetryCompositionRoot = original_root
        run_retry_runtime.RetryRuntimeOrchestrator = original_orchestrator
        sys.argv = original_argv
    return buf.getvalue()


stdout_no_flag = run_main_with_argv([])
check("15. --dry-run未指定時、run_once(dry_run=False)が呼ばれる", _FakeOrchestrator.calls, [False])

stdout_with_flag = run_main_with_argv(["--dry-run"])
check("16. --dry-run指定時、run_once(dry_run=True)が呼ばれる", _FakeOrchestrator.calls, [True])

check_contains("17. --dry-run指定時、標準出力に'[DRY RUN MODE]'が含まれる", stdout_with_flag, "[DRY RUN MODE]")
check_not_contains("18. --dry-run未指定時、標準出力に'[DRY RUN MODE]'が含まれない", stdout_no_flag, "[DRY RUN MODE]")

check_contains("19. format_summary()の戻り値が標準出力に含まれる（--dry-runなし）", stdout_no_flag, "Retry Runtime 実行結果")
check_contains("19. format_summary()の戻り値が標準出力に含まれる（--dry-runあり）", stdout_with_flag, "Retry Runtime 実行結果")
check_contains("19. Summary内容自体は変化しない（scanned=7）", stdout_with_flag, "scanned=7")
print()


# ═══════════════════════════════════════════════════════════
# テスト20-23: サブプロセス実行（実CLI呼び出し）
# ═══════════════════════════════════════════════════════════

ALL_GATE_ENV_KEYS = (
    "AI_AGENT_ENABLED", "WORKFLOW_ENGINE_ENABLED", "RETRY_ENGINE_ENABLED",
    "RETRY_QUEUE_ENABLED", "WORKFLOW_MONITOR_ENABLED",
    "REVIEW_TRIGGER_AGENT_ENABLED", "PUBLISH_TRIGGER_AGENT_ENABLED",
)


def run_cli(env_overrides: dict, extra_args: list = None, timeout: int = 60):
    env = dict(os.environ)
    for key in ALL_GATE_ENV_KEYS:
        env.pop(key, None)
    env.update(env_overrides)
    env["PYTHONIOENCODING"] = "utf-8"
    args = [sys.executable, str(SCRIPT_PATH)] + (extra_args or [])
    return subprocess.run(
        args,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
    )


print("[テスト20] --dry-run未指定時、returncodeが0になり従来どおりのサマリーが出力される")

completed_20 = run_cli({
    "AI_AGENT_ENABLED": "false", "WORKFLOW_ENGINE_ENABLED": "false", "RETRY_ENGINE_ENABLED": "false",
})
check("20. returncodeが0", completed_20.returncode, 0)
check_contains("20. 'Retry Runtime 実行結果' が標準出力に含まれる", completed_20.stdout, "Retry Runtime 実行結果")
check_not_contains("20. '[DRY RUN MODE]' は含まれない", completed_20.stdout, "[DRY RUN MODE]")
print()


print("[テスト21] --dry-run指定時、returncodeが0になり[DRY RUN MODE]とサマリーの両方が出力される")

completed_21 = run_cli({
    "AI_AGENT_ENABLED": "false", "WORKFLOW_ENGINE_ENABLED": "false", "RETRY_ENGINE_ENABLED": "false",
}, extra_args=["--dry-run"])
check("21. returncodeが0", completed_21.returncode, 0)
check_contains("21. '[DRY RUN MODE]' が標準出力に含まれる", completed_21.stdout, "[DRY RUN MODE]")
check_contains("21. 'Retry Runtime 実行結果' が標準出力に含まれる", completed_21.stdout, "Retry Runtime 実行結果")
print()


print("[テスト22] --dry-run指定時も、全Gate無効時はlogs/execution_history/に新規ファイルが作られない")

history_dir = PROJECT_ROOT / "logs" / "execution_history"
before_history_files = set(history_dir.glob("*")) if history_dir.exists() else set()

completed_22 = run_cli({
    "AI_AGENT_ENABLED": "false", "WORKFLOW_ENGINE_ENABLED": "false", "RETRY_ENGINE_ENABLED": "false",
}, extra_args=["--dry-run"])

after_history_files = set(history_dir.glob("*")) if history_dir.exists() else set()
check("22. logs/execution_history/ に新規ファイルが作られない", after_history_files - before_history_files, set())
print()


print("[テスト23] 不正な環境変数指定時、--dry-run有無に関わらずreturncodeが非0になりtracebackが出力される")

completed_23a = run_cli({
    "AI_AGENT_ENABLED": "false", "WORKFLOW_ENGINE_ENABLED": "false", "RETRY_ENGINE_ENABLED": "false",
    "RETRY_QUEUE_MAX_SIZE": "not_a_number",
})
check_false("23. --dry-runなし: returncodeが0ではない", completed_23a.returncode == 0)
check_contains("23. --dry-runなし: ValueErrorがstderrに含まれる（fail-fast）", completed_23a.stderr, "ValueError")

completed_23b = run_cli({
    "AI_AGENT_ENABLED": "false", "WORKFLOW_ENGINE_ENABLED": "false", "RETRY_ENGINE_ENABLED": "false",
    "RETRY_QUEUE_MAX_SIZE": "not_a_number",
}, extra_args=["--dry-run"])
check_false("23. --dry-runあり: returncodeが0ではない", completed_23b.returncode == 0)
check_contains("23. --dry-runあり: ValueErrorがstderrに含まれる（fail-fast）", completed_23b.stderr, "ValueError")
print()


# ═══════════════════════════════════════════════════════════
# テスト24-25: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト24] 既存13パッケージに変更がないこと（git diff）")

unchanged_dirs_24 = [
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
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_dirs_24:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"24. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("24. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト25] 既存の他scriptsに変更がないこと（git diff）")

unchanged_scripts_25 = [
    "scripts/run_workflow_engine.py",
    "scripts/run_news_agent.py",
    "scripts/run_publish_trigger_agent.py",
    "scripts/run_review_trigger_agent.py",
    "scripts/run_workflow_trigger_agent.py",
    "scripts/show_execution_history.py",
]

if git_available:
    for rel_path in unchanged_scripts_25:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"25. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("25. gitが利用できないため無変更確認をスキップ", True)
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
