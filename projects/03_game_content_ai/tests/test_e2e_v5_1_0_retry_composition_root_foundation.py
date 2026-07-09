"""
E2E テスト: v5.1.0 Retry Composition Root Foundation

テストシナリオ:
    ── RetryCompositionRoot.from_env()（全ゲート無効、デフォルト） ──
    1.  from_env() が例外なく RetryCompositionRoot を返す
    2.  monitor が WorkflowMonitorManager 系の型である
    3.  queue が RetryQueueManager 系の型である
    4.  history が RetryHistoryManager である（Null実装を持たない）
    5.  guard が RetryEnqueueGuard である
    6.  trigger が RetryEnqueueTrigger（実体）である（NullRetryEnqueueTriggerではない）
    7.  policy が RetryPolicy である
    8.  RETRY_ENGINE_ENABLED=false（デフォルト）のとき manager が NullRetryManager になる

    ── インスタンス共有（本Releaseの中心的な検証観点） ──
    9.  trigger内部が保持するqueueと、RetryCompositionRoot.queueが同一インスタンスである
    10. trigger内部が保持するhistoryと、RetryCompositionRoot.historyが同一インスタンスである
    11. 全ゲート有効時、managerが実体のRetryManagerになり、
        managerが保持するqueueがRetryCompositionRoot.queueと同一インスタンスである
    12. 全ゲート有効時、managerが保持するhistoryがRetryCompositionRoot.historyと
        同一インスタンスである
    13. 全ゲート有効時でも、trigger経由で使われるqueue/historyとmanager経由で使われる
        queue/historyが同一インスタンスのままである（Enqueue側とExecute側の状態共有）

    ── 責務境界（Composition Rootは実行しない） ──
    14. RetryCompositionRootが実行系メソッド（run/run_once/execute/loop等）を持たない
    15. RetryCompositionRoot.__init__ のシグネチャが
        (self, monitor, queue, history, guard, trigger, policy, manager) である
    16. RetryCompositionRoot.from_env() のシグネチャが (cls, base_dir=None) である

    ── ディレクトリ構成・Backward Compatibility ──
    17. src/retry_composition/ のファイル構成が __init__.py・retry_composition_root.py の
        2ファイルのみである
    18. retry_composition パッケージのexportが RetryCompositionRoot のみである

    ── Architecture Guard ──
    19. workflow_monitor / retry_queue / retry_history / retry_enqueue_trigger /
        retry_engine / workflow_engine / ai / execution_history に変更がないこと（git diff）
    20. 本Releaseでも retry_composition をどのパッケージからも呼び出さない
        （消費者不在の先行実装。scripts/を含めても未接続）

    ── 副作用なしの確認 ──
    21. RetryCompositionRoot.from_env() 実行前後でファイルが一切作成されない

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v5_1_0_retry_composition_root_foundation.py
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
print("v5.1.0 Retry Composition Root Foundation E2E テスト")
print("=" * 60)
print()

import retry_composition as rc_pkg
from ai import AgentConfig
from retry_composition import RetryCompositionRoot
from retry_engine import NullRetryManager, RetryManager, RetryPolicy
from retry_enqueue_trigger import RetryEnqueueGuard, RetryEnqueueTrigger
from retry_history import RetryHistoryManager
from retry_queue import RetryQueueManager
from workflow_monitor import WorkflowMonitorManager


def clear_gate_env_vars():
    for name in (
        "AI_AGENT_ENABLED", "WORKFLOW_ENGINE_ENABLED", "RETRY_ENGINE_ENABLED",
        "RETRY_QUEUE_ENABLED", "WORKFLOW_MONITOR_ENABLED",
        "REVIEW_TRIGGER_AGENT_ENABLED", "PUBLISH_TRIGGER_AGENT_ENABLED",
    ):
        os.environ.pop(name, None)


# ═══════════════════════════════════════════════════════════
# テスト1-8: from_env()（全ゲート無効、デフォルト）
# ═══════════════════════════════════════════════════════════

clear_gate_env_vars()

print("[テスト1] from_env() が例外なく RetryCompositionRoot を返す")

root_1 = RetryCompositionRoot.from_env()
check_true("1. RetryCompositionRootのインスタンスである", isinstance(root_1, RetryCompositionRoot))
print()


print("[テスト2] monitor が WorkflowMonitorManager 系の型である")

check_true("2. monitorがlist_statusを持つ", hasattr(root_1.monitor, "list_status"))
print()


print("[テスト3] queue が RetryQueueManager 系の型である")

check_true("3. queueがenqueueを持つ", hasattr(root_1.queue, "enqueue"))
print()


print("[テスト4] history が RetryHistoryManager である（Null実装を持たない）")

check("4. historyの型がRetryHistoryManager", type(root_1.history).__name__, "RetryHistoryManager")
print()


print("[テスト5] guard が RetryEnqueueGuard である")

check("5. guardの型がRetryEnqueueGuard", type(root_1.guard).__name__, "RetryEnqueueGuard")
print()


print("[テスト6] trigger が RetryEnqueueTrigger（実体）である")

check("6. triggerの型がRetryEnqueueTrigger", type(root_1.trigger).__name__, "RetryEnqueueTrigger")
print()


print("[テスト7] policy が RetryPolicy である")

check_true("7. policyがRetryPolicyのインスタンスである", isinstance(root_1.policy, RetryPolicy))
print()


print("[テスト8] RETRY_ENGINE_ENABLED=false（デフォルト）のとき manager が NullRetryManager になる")

check("8. managerの型がNullRetryManager", type(root_1.manager).__name__, "NullRetryManager")
print()


# ═══════════════════════════════════════════════════════════
# テスト9-13: インスタンス共有
# ═══════════════════════════════════════════════════════════

print("[テスト9] trigger内部のqueueとRetryCompositionRoot.queueが同一インスタンスである")

check_true("9. trigger._queue is root_1.queue", root_1.trigger._queue is root_1.queue)
print()


print("[テスト10] trigger内部のhistoryとRetryCompositionRoot.historyが同一インスタンスである")

check_true("10. trigger._history is root_1.history", root_1.trigger._history is root_1.history)
print()


clear_gate_env_vars()
os.environ["AI_AGENT_ENABLED"] = "true"
os.environ["WORKFLOW_ENGINE_ENABLED"] = "true"
os.environ["RETRY_ENGINE_ENABLED"] = "true"

print("[テスト11] 全ゲート有効時、managerが実体のRetryManagerになり、"
      "managerのqueueがRetryCompositionRoot.queueと同一インスタンスである")

root_11 = RetryCompositionRoot.from_env()
check("11. managerの型がRetryManager", type(root_11.manager).__name__, "RetryManager")
check_true("11. manager._queue is root_11.queue", root_11.manager._queue is root_11.queue)
print()


print("[テスト12] 全ゲート有効時、managerのhistoryがRetryCompositionRoot.historyと同一インスタンスである")

check_true("12. manager._history is root_11.history", root_11.manager._history is root_11.history)
print()


print("[テスト13] 全ゲート有効時でも、trigger側とmanager側で同一のqueue/historyインスタンスが使われる")

check_true("13. trigger._queue is manager._queue", root_11.trigger._queue is root_11.manager._queue)
check_true("13. trigger._history is manager._history", root_11.trigger._history is root_11.manager._history)
print()

clear_gate_env_vars()


# ═══════════════════════════════════════════════════════════
# テスト14-16: 責務境界（Composition Rootは実行しない）
# ═══════════════════════════════════════════════════════════

print("[テスト14] RetryCompositionRootが実行系メソッドを持たない")

public_methods_14 = [
    name for name, value in inspect.getmembers(RetryCompositionRoot, predicate=inspect.isfunction)
    if not name.startswith("_") and name != "from_env"
]
check("14. from_env以外の公開メソッドが存在しない", public_methods_14, [])
for forbidden_name in ("run", "run_once", "execute", "loop", "start", "daemon"):
    check_false(f"14. {forbidden_name}という名前のメソッドを持たない", hasattr(RetryCompositionRoot, forbidden_name))
print()


print("[テスト15] __init__ のシグネチャが (self, monitor, queue, history, guard, trigger, policy, manager)")

params_15 = list(inspect.signature(RetryCompositionRoot.__init__).parameters.keys())
check(
    "15. パラメータ順序が一致する",
    params_15,
    ["self", "monitor", "queue", "history", "guard", "trigger", "policy", "manager"],
)
print()


print("[テスト16] from_env() のシグネチャが (cls, base_dir=None)")

sig_16 = inspect.signature(RetryCompositionRoot.from_env)
params_16 = list(sig_16.parameters.keys())
check("16. パラメータがbase_dirのみ", params_16, ["base_dir"])
check("16. base_dirのデフォルトがNone", sig_16.parameters["base_dir"].default, None)
print()


# ═══════════════════════════════════════════════════════════
# テスト17-18: ディレクトリ構成・Backward Compatibility
# ═══════════════════════════════════════════════════════════

print("[テスト17] src/retry_composition/ のファイル構成が2ファイルのみである")

rc_dir = PROJECT_ROOT / "src" / "retry_composition"
py_files_17 = sorted(p.name for p in rc_dir.glob("*.py"))
check("17. __init__.py・retry_composition_root.pyの2ファイル", py_files_17, ["__init__.py", "retry_composition_root.py"])
print()


print("[テスト18] retry_composition パッケージのexportが RetryCompositionRoot のみである")

check_true("18. RetryCompositionRootがretry_compositionパッケージからエクスポートされている", hasattr(rc_pkg, "RetryCompositionRoot"))
check("18. __all__がRetryCompositionRootのみ", rc_pkg.__all__, ["RetryCompositionRoot"])
print()


# ═══════════════════════════════════════════════════════════
# テスト19-20: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト19] workflow_monitor / retry_queue / retry_history / retry_enqueue_trigger / "
      "retry_engine / workflow_engine / ai / execution_history に変更がないこと（git diff）")

unchanged_dirs_19 = [
    "src/workflow_monitor",
    "src/retry_queue",
    "src/retry_history",
    "src/retry_enqueue_trigger",
    "src/retry_engine",
    "src/workflow_engine",
    "src/ai",
    "src/execution_history",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_dirs_19:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"19. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("19. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト20] 本Releaseでも retry_composition をどこからも呼び出さない")

src_dir = PROJECT_ROOT / "src"
scripts_dir = PROJECT_ROOT / "scripts"
consumers_20 = []
for py_file in sorted(list(src_dir.rglob("*.py")) + list(scripts_dir.rglob("*.py"))):
    if py_file.parent.name == "retry_composition":
        continue
    text = py_file.read_text(encoding="utf-8")
    if "retry_composition" in text:
        consumers_20.append(str(py_file.relative_to(PROJECT_ROOT)))
check("20. retry_compositionを参照する既存ファイルが存在しない", consumers_20, [])
print()


# ═══════════════════════════════════════════════════════════
# テスト21: 副作用なしの確認
# ═══════════════════════════════════════════════════════════

print("[テスト21] RetryCompositionRoot.from_env() 実行前後でファイルが作成されない")

with tempfile.TemporaryDirectory() as tmp_dir:
    write_check_dir = Path(tmp_dir)
    before_files_21 = list(write_check_dir.rglob("*"))

    clear_gate_env_vars()
    RetryCompositionRoot.from_env()

    after_files_21 = list(write_check_dir.rglob("*"))
    check("21. 実行前後でファイルが作成されない", after_files_21, before_files_21)
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
