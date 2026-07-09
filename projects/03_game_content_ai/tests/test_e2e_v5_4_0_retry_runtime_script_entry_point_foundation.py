"""
E2E テスト: v5.4.0 Retry Runtime Script Entry Point Foundation

テストシナリオ（docs/design/retry_runtime_script_entry_point_foundation.md 対応）:
    ── スクリプトファイルの存在・モジュールロード ──
    1.  scripts/run_retry_runtime.py が存在する
    2.  importlibでモジュールをロードでき、main() / format_summary() を持つ

    ── format_summary()（Summary Formatter Design Note、2.8節） ──
    3.  format_summary()のシグネチャが(result)のみ
    4.  format_summary()がstrを返す
    5.  format_summary()の出力に主要カテゴリ（Enqueue/Scheduler/Execution/Removal/
        Cleanup/TerminalCleanup/History）がすべて含まれる
    6.  format_summary()の出力にtrigger_resultの各件数が反映される

    ── scripts層の責務・静的import検査（2.1節・2.2節・2.3節） ──
    7.  argparseをimportしない（CLI引数なし設計の確認）
    8.  retry_engineのDecider/Executor（RetryQueueUpdateDecider等）を直接importしない
    9.  retry_composition / retry_runtime_orchestrator 以外のRetry関連パッケージを
        直接importしない

    ── Null判定を行わない方針の確認（2.6節） ──
    10. isinstance(...) によるGate判定コード（NullRetryManager等）を持たない

    ── サブプロセス実行（実CLI呼び出し） ──
    11. 全Gate無効時、returncodeが0になる
    12. 標準出力にサマリーの主要行が含まれる
    13. 全Gate無効時、Retry Runtime以外のファイルが新規作成されない
        （logs/execution_history/ に新規ファイルが作られない）
    14. 不正な環境変数（RETRY_QUEUE_MAX_SIZE）指定時、returncodeが非0になり、
        標準エラー出力にtracebackが出力される（Exit Code Policy、2.4節）

    ── Architecture Guard ──
    15. 既存12パッケージ（workflow_monitor 〜 retry_composition、
        retry_runtime_orchestrator含む）に変更がないこと（git diff）
    16. 既存の他scripts（run_workflow_engine.py等）に変更がないこと（git diff）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v5_4_0_retry_runtime_script_entry_point_foundation.py
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


def check_contains(label: str, text: str, keyword: str):
    check(label, keyword in str(text), True)


print("=" * 60)
print("v5.4.0 Retry Runtime Script Entry Point Foundation E2E テスト")
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
# テスト3-6: format_summary()
# ═══════════════════════════════════════════════════════════

print("[テスト3] format_summary()のシグネチャが(result)のみ")

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


# ═══════════════════════════════════════════════════════════
# テスト7-9: scripts層の責務・静的import検査
# ═══════════════════════════════════════════════════════════

script_source = SCRIPT_PATH.read_text(encoding="utf-8")
import_lines = "\n".join(
    line for line in script_source.splitlines()
    if line.strip().startswith("from ") or line.strip().startswith("import ")
)

print("[テスト7] argparseをimportしない（CLI引数なし設計の確認）")

check_false("7. argparseがimportされていない", "argparse" in import_lines)
print()


print("[テスト8] retry_engineのDecider/Executorを直接importしない")

for forbidden in (
    "RetryQueueUpdateDecider", "RetryQueueRemovalExecutor", "RetryQueueCleanupDecider",
    "RetryQueueCleanupExecutor", "RetryQueueTerminalCleanupDecider",
    "RetryQueueTerminalCleanupExecutor", "RetryHistoryRecordExecutor", "RetryManager",
):
    check_false(f"8. {forbidden} がimportされていない", forbidden in import_lines)
print()


print("[テスト9] retry_composition / retry_runtime_orchestrator 以外のRetry関連パッケージを直接importしない")

for forbidden_module in (
    "retry_engine", "retry_queue", "retry_history", "retry_enqueue_trigger",
    "retry_scheduler_source", "retry_scheduler_decision", "scheduler", "workflow_monitor",
    "workflow_engine",
):
    check_false(
        f"9. 'from {forbidden_module}' がimportされていない",
        f"from {forbidden_module} " in import_lines or f"from {forbidden_module}\n" in import_lines,
    )
check_contains("9. retry_composition はimportされている", import_lines, "from retry_composition import")
check_contains("9. retry_runtime_orchestrator はimportされている", import_lines, "from retry_runtime_orchestrator import")
print()


# ═══════════════════════════════════════════════════════════
# テスト10: Null判定を行わない方針の確認
# ═══════════════════════════════════════════════════════════

print("[テスト10] isinstance(...) によるGate判定コードを持たない")

check_false("10. isinstance(が使われていない（コード本体にGate判定を持たない）", "isinstance(" in script_source)
check_false("10. NullRetryManagerがimportされていない（型そのものを知らない）", "NullRetryManager" in import_lines)
print()


# ═══════════════════════════════════════════════════════════
# テスト11-14: サブプロセス実行
# ═══════════════════════════════════════════════════════════

ALL_GATE_ENV_KEYS = (
    "AI_AGENT_ENABLED", "WORKFLOW_ENGINE_ENABLED", "RETRY_ENGINE_ENABLED",
    "RETRY_QUEUE_ENABLED", "WORKFLOW_MONITOR_ENABLED",
    "REVIEW_TRIGGER_AGENT_ENABLED", "PUBLISH_TRIGGER_AGENT_ENABLED",
)


def run_cli(env_overrides: dict, timeout: int = 60):
    env = dict(os.environ)
    for key in ALL_GATE_ENV_KEYS:
        env.pop(key, None)
    env.update(env_overrides)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(SCRIPT_PATH)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=timeout,
    )


print("[テスト11-13] 全Gate無効時、正常終了しサマリーが表示され、副作用が発生しない")

history_dir = PROJECT_ROOT / "logs" / "execution_history"
before_history_files = set(history_dir.glob("*")) if history_dir.exists() else set()

completed_11 = run_cli({
    "AI_AGENT_ENABLED": "false", "WORKFLOW_ENGINE_ENABLED": "false", "RETRY_ENGINE_ENABLED": "false",
})

check("11. returncodeが0", completed_11.returncode, 0)
check_contains("12. 'Retry Runtime 実行結果' が標準出力に含まれる", completed_11.stdout, "Retry Runtime 実行結果")
check_contains("12. 'Enqueue' が標準出力に含まれる", completed_11.stdout, "Enqueue")
check_contains("12. 'History' が標準出力に含まれる", completed_11.stdout, "History")

after_history_files = set(history_dir.glob("*")) if history_dir.exists() else set()
check("13. logs/execution_history/ に新規ファイルが作られない", after_history_files - before_history_files, set())
print()


print("[テスト14] 不正な環境変数指定時、returncodeが非0になりtracebackが出力される")

completed_14 = run_cli({
    "AI_AGENT_ENABLED": "false", "WORKFLOW_ENGINE_ENABLED": "false", "RETRY_ENGINE_ENABLED": "false",
    "RETRY_QUEUE_MAX_SIZE": "not_a_number",
})

check_false("14. returncodeが0ではない", completed_14.returncode == 0)
check_contains("14. ValueErrorがstderrに含まれる（fail-fast）", completed_14.stderr, "ValueError")
print()


# ═══════════════════════════════════════════════════════════
# テスト15-16: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト15] 既存12パッケージに変更がないこと（git diff）")

unchanged_dirs_15 = [
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
    for rel_path in unchanged_dirs_15:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"15. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("15. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト16] 既存の他scriptsに変更がないこと（git diff）")

unchanged_scripts_16 = [
    "scripts/run_workflow_engine.py",
    "scripts/run_news_agent.py",
    "scripts/run_publish_trigger_agent.py",
    "scripts/run_review_trigger_agent.py",
    "scripts/run_workflow_trigger_agent.py",
    "scripts/show_execution_history.py",
]

if git_available:
    for rel_path in unchanged_scripts_16:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"16. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("16. gitが利用できないため無変更確認をスキップ", True)
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
