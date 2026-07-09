"""
E2E テスト: v5.2.0 Retry Runtime Orchestrator Foundation

テストシナリオ:
    ── RetryCompositionRoot拡張（Scheduler系配線） ──
    1.  from_env() が例外なく RetryCompositionRoot を返す（Scheduler系追加後も）
    2.  retry_source が RetrySchedulerSource である
    3.  retry_decision が RetrySchedulerDecision である
    4.  scheduler が SchedulerEngine である
    5.  retry_source内部のqueueとRetryCompositionRoot.queueが同一インスタンスである
    6.  retry_decision内部のretry_sourceとRetryCompositionRoot.retry_sourceが同一インスタンスである
    7.  scheduler内部のretry_source/retry_decisionがRetryCompositionRoot側と同一インスタンスである
    8.  RetryCompositionRoot.__init__ のシグネチャが新規3属性を含む

    ── RetryCompositionRootは引き続きComposition専任 ──
    9.  RetryCompositionRootが実行系メソッド（run/run_once/execute/loop等）を持たない

    ── RetryRuntimeOrchestrator ──
    10. RetryRuntimeOrchestrator.from_composition_root(root) が例外なくインスタンスを返す
    11. orchestrator.trigger が root.trigger と同一インスタンスである
    12. orchestrator.scheduler が root.scheduler と同一インスタンスである
    13. orchestrator.manager が root.manager と同一インスタンスである
    14. orchestrator.queue が root.queue と同一インスタンスである
    15. orchestrator.history が root.history と同一インスタンスである
    16. orchestrator.policy が root.policy と同一インスタンスである
    17. 全ゲート有効時でも、orchestrator.manager が実体のRetryManagerになり、
        orchestrator.queue / orchestrator.history が manager 内部と同一インスタンスである

    ── 責務境界（Orchestratorはまだ実行しない） ──
    18. RetryRuntimeOrchestratorが実行系メソッド（run/run_once/execute/loop/daemon等）を持たない
    19. RetryRuntimeOrchestrator.__init__ のシグネチャが
        (self, trigger, scheduler, manager, queue, history, policy) である
    20. RetryRuntimeOrchestrator.from_composition_root() のシグネチャが (cls, root) である
    21. RetryRuntimeOrchestratorがguard/monitorを保持しない

    ── ディレクトリ構成・Backward Compatibility ──
    22. src/retry_runtime_orchestrator/ のファイル構成が __init__.py・
        retry_runtime_orchestrator.py の2ファイルのみである
    23. retry_runtime_orchestrator パッケージのexportが RetryRuntimeOrchestrator のみである

    ── Architecture Guard ──
    24. workflow_monitor / retry_queue / retry_history / retry_enqueue_trigger /
        retry_engine / workflow_engine / ai / execution_history / scheduler /
        retry_scheduler_source / retry_scheduler_decision に変更がないこと（git diff）
    25. 本Releaseでも retry_runtime_orchestrator をどのパッケージからも呼び出さない
        （消費者不在の先行実装。scripts/を含めても未接続）

    ── 副作用なしの確認 ──
    26. RetryRuntimeOrchestrator.from_composition_root() 実行前後でファイルが一切作成されない

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v5_2_0_retry_runtime_orchestrator_foundation.py
"""
import inspect
import os
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
print("v5.2.0 Retry Runtime Orchestrator Foundation E2E テスト")
print("=" * 60)
print()

import retry_runtime_orchestrator as rro_pkg
from retry_composition import RetryCompositionRoot
from retry_engine import NullRetryManager, RetryManager, RetryPolicy
from retry_enqueue_trigger import RetryEnqueueTrigger
from retry_history import RetryHistoryManager
from retry_queue import RetryQueueManager
from retry_runtime_orchestrator import RetryRuntimeOrchestrator
from retry_scheduler_decision import RetrySchedulerDecision
from retry_scheduler_source import RetrySchedulerSource
from scheduler import SchedulerEngine


def clear_gate_env_vars():
    for name in (
        "AI_AGENT_ENABLED", "WORKFLOW_ENGINE_ENABLED", "RETRY_ENGINE_ENABLED",
        "RETRY_QUEUE_ENABLED", "WORKFLOW_MONITOR_ENABLED",
        "REVIEW_TRIGGER_AGENT_ENABLED", "PUBLISH_TRIGGER_AGENT_ENABLED",
    ):
        os.environ.pop(name, None)


# ═══════════════════════════════════════════════════════════
# テスト1-8: RetryCompositionRoot拡張（Scheduler系配線）
# ═══════════════════════════════════════════════════════════

clear_gate_env_vars()

print("[テスト1] from_env() が例外なく RetryCompositionRoot を返す")

root_1 = RetryCompositionRoot.from_env()
check_true("1. RetryCompositionRootのインスタンスである", isinstance(root_1, RetryCompositionRoot))
print()


print("[テスト2] retry_source が RetrySchedulerSource である")

check("2. retry_sourceの型がRetrySchedulerSource", type(root_1.retry_source).__name__, "RetrySchedulerSource")
print()


print("[テスト3] retry_decision が RetrySchedulerDecision である")

check_true("3. retry_decisionがRetrySchedulerDecisionのインスタンスである", isinstance(root_1.retry_decision, RetrySchedulerDecision))
print()


print("[テスト4] scheduler が SchedulerEngine である")

check_true("4. schedulerがSchedulerEngineのインスタンスである", isinstance(root_1.scheduler, SchedulerEngine))
print()


print("[テスト5] retry_source内部のqueueとRetryCompositionRoot.queueが同一インスタンスである")

check_true("5. retry_source._queue is root_1.queue", root_1.retry_source._queue is root_1.queue)
print()


print("[テスト6] retry_decision内部のretry_sourceとRetryCompositionRoot.retry_sourceが同一インスタンスである")

check_true("6. retry_decision._retry_source is root_1.retry_source", root_1.retry_decision._retry_source is root_1.retry_source)
print()


print("[テスト7] scheduler内部のretry_source/retry_decisionがRetryCompositionRoot側と同一インスタンスである")

check_true("7. scheduler._retry_source is root_1.retry_source", root_1.scheduler._retry_source is root_1.retry_source)
check_true("7. scheduler._retry_decision is root_1.retry_decision", root_1.scheduler._retry_decision is root_1.retry_decision)
print()


print("[テスト8] RetryCompositionRoot.__init__ のシグネチャが新規3属性を含む")

params_8 = list(inspect.signature(RetryCompositionRoot.__init__).parameters.keys())
check(
    "8. パラメータ順序が一致する",
    params_8,
    ["self", "monitor", "queue", "history", "guard", "trigger", "policy", "manager",
     "retry_source", "retry_decision", "scheduler"],
)
print()


# ═══════════════════════════════════════════════════════════
# テスト9: RetryCompositionRootは引き続きComposition専任
# ═══════════════════════════════════════════════════════════

print("[テスト9] RetryCompositionRootが実行系メソッドを持たない（v5.1.0からの維持確認）")

public_methods_9 = [
    name for name, value in inspect.getmembers(RetryCompositionRoot, predicate=inspect.isfunction)
    if not name.startswith("_") and name != "from_env"
]
check("9. from_env以外の公開メソッドが存在しない", public_methods_9, [])
for forbidden_name in ("run", "run_once", "execute", "loop", "start", "daemon"):
    check_false(f"9. {forbidden_name}という名前のメソッドを持たない", hasattr(RetryCompositionRoot, forbidden_name))
print()


# ═══════════════════════════════════════════════════════════
# テスト10-17: RetryRuntimeOrchestrator
# ═══════════════════════════════════════════════════════════

print("[テスト10] RetryRuntimeOrchestrator.from_composition_root(root) が例外なくインスタンスを返す")

orchestrator_10 = RetryRuntimeOrchestrator.from_composition_root(root_1)
check_true("10. RetryRuntimeOrchestratorのインスタンスである", isinstance(orchestrator_10, RetryRuntimeOrchestrator))
print()


print("[テスト11] orchestrator.trigger が root.trigger と同一インスタンスである")

check_true("11. orchestrator.trigger is root_1.trigger", orchestrator_10.trigger is root_1.trigger)
print()


print("[テスト12] orchestrator.scheduler が root.scheduler と同一インスタンスである")

check_true("12. orchestrator.scheduler is root_1.scheduler", orchestrator_10.scheduler is root_1.scheduler)
print()


print("[テスト13] orchestrator.manager が root.manager と同一インスタンスである")

check_true("13. orchestrator.manager is root_1.manager", orchestrator_10.manager is root_1.manager)
print()


print("[テスト14] orchestrator.queue が root.queue と同一インスタンスである")

check_true("14. orchestrator.queue is root_1.queue", orchestrator_10.queue is root_1.queue)
print()


print("[テスト15] orchestrator.history が root.history と同一インスタンスである")

check_true("15. orchestrator.history is root_1.history", orchestrator_10.history is root_1.history)
print()


print("[テスト16] orchestrator.policy が root.policy と同一インスタンスである")

check_true("16. orchestrator.policy is root_1.policy", orchestrator_10.policy is root_1.policy)
print()


clear_gate_env_vars()
os.environ["AI_AGENT_ENABLED"] = "true"
os.environ["WORKFLOW_ENGINE_ENABLED"] = "true"
os.environ["RETRY_ENGINE_ENABLED"] = "true"

print("[テスト17] 全ゲート有効時でも、orchestrator.manager が実体のRetryManagerになり、"
      "orchestrator.queue/historyがmanager内部と同一インスタンスである")

root_17 = RetryCompositionRoot.from_env()
orchestrator_17 = RetryRuntimeOrchestrator.from_composition_root(root_17)
check("17. orchestrator.managerの型がRetryManager", type(orchestrator_17.manager).__name__, "RetryManager")
check_true("17. orchestrator.queue is orchestrator.manager._queue", orchestrator_17.queue is orchestrator_17.manager._queue)
check_true("17. orchestrator.history is orchestrator.manager._history", orchestrator_17.history is orchestrator_17.manager._history)
check_true("17. orchestrator.trigger._queue is orchestrator.queue", orchestrator_17.trigger._queue is orchestrator_17.queue)
print()

clear_gate_env_vars()


# ═══════════════════════════════════════════════════════════
# テスト18-21: 責務境界（Orchestratorはまだ実行しない）
# ═══════════════════════════════════════════════════════════

print("[テスト18] RetryRuntimeOrchestratorが実行系メソッドを持たない")

public_methods_18 = [
    name for name, value in inspect.getmembers(RetryRuntimeOrchestrator, predicate=inspect.isfunction)
    if not name.startswith("_") and name != "from_composition_root"
]
check("18. from_composition_root以外の公開メソッドが存在しない", public_methods_18, [])
for forbidden_name in ("run", "run_once", "execute", "loop", "start", "daemon"):
    check_false(f"18. {forbidden_name}という名前のメソッドを持たない", hasattr(RetryRuntimeOrchestrator, forbidden_name))
print()


print("[テスト19] __init__ のシグネチャが (self, trigger, scheduler, manager, queue, history, policy)")

params_19 = list(inspect.signature(RetryRuntimeOrchestrator.__init__).parameters.keys())
check(
    "19. パラメータ順序が一致する",
    params_19,
    ["self", "trigger", "scheduler", "manager", "queue", "history", "policy"],
)
print()


print("[テスト20] from_composition_root() のシグネチャが (cls, root)")

params_20 = list(inspect.signature(RetryRuntimeOrchestrator.from_composition_root).parameters.keys())
check("20. パラメータがrootのみ", params_20, ["root"])
print()


print("[テスト21] RetryRuntimeOrchestratorがguard/monitorを保持しない")

check_false("21. guard属性を持たない", hasattr(orchestrator_10, "guard"))
check_false("21. monitor属性を持たない", hasattr(orchestrator_10, "monitor"))
print()


# ═══════════════════════════════════════════════════════════
# テスト22-23: ディレクトリ構成・Backward Compatibility
# ═══════════════════════════════════════════════════════════

print("[テスト22] src/retry_runtime_orchestrator/ のファイル構成が2ファイルのみである")

rro_dir = PROJECT_ROOT / "src" / "retry_runtime_orchestrator"
py_files_22 = sorted(p.name for p in rro_dir.glob("*.py"))
check("22. __init__.py・retry_runtime_orchestrator.pyの2ファイル", py_files_22,
      ["__init__.py", "retry_runtime_orchestrator.py"])
print()


print("[テスト23] retry_runtime_orchestrator パッケージのexportが RetryRuntimeOrchestrator のみである")

check_true("23. RetryRuntimeOrchestratorがretry_runtime_orchestratorパッケージからエクスポートされている",
           hasattr(rro_pkg, "RetryRuntimeOrchestrator"))
check("23. __all__がRetryRuntimeOrchestratorのみ", rro_pkg.__all__, ["RetryRuntimeOrchestrator"])
print()


# ═══════════════════════════════════════════════════════════
# テスト24-25: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト24] 既存パッケージ（scheduler / retry_scheduler_source / retry_scheduler_decision を含む）に"
      "変更がないこと（git diff）")

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


print("[テスト25] 本Releaseでも retry_runtime_orchestrator をどこからも呼び出さない")

src_dir = PROJECT_ROOT / "src"
scripts_dir = PROJECT_ROOT / "scripts"
consumers_25 = []
for py_file in sorted(list(src_dir.rglob("*.py")) + list(scripts_dir.rglob("*.py"))):
    if py_file.parent.name == "retry_runtime_orchestrator":
        continue
    text = py_file.read_text(encoding="utf-8")
    if "retry_runtime_orchestrator" in text:
        consumers_25.append(str(py_file.relative_to(PROJECT_ROOT)))
check("25. retry_runtime_orchestratorを参照する既存ファイルが存在しない", consumers_25, [])
print()


# ═══════════════════════════════════════════════════════════
# テスト26: 副作用なしの確認
# ═══════════════════════════════════════════════════════════

print("[テスト26] RetryRuntimeOrchestrator.from_composition_root() 実行前後でファイルが作成されない")

with tempfile.TemporaryDirectory() as tmp_dir:
    write_check_dir = Path(tmp_dir)
    before_files_26 = list(write_check_dir.rglob("*"))

    clear_gate_env_vars()
    root_26 = RetryCompositionRoot.from_env()
    RetryRuntimeOrchestrator.from_composition_root(root_26)

    after_files_26 = list(write_check_dir.rglob("*"))
    check("26. 実行前後でファイルが作成されない", after_files_26, before_files_26)
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
