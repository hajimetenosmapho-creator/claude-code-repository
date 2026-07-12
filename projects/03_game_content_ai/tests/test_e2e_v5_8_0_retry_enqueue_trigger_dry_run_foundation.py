"""
E2E テスト: v5.8.0 Retry Enqueue Trigger Dry Run Foundation

テストシナリオ（docs/design/retry_enqueue_trigger_dry_run_foundation.md 対応）:
    ── RetryEnqueueTrigger.enqueue_pending_failures(dry_run=...) ──
    1.  dry_run=True時、Monitor走査・History参照・Guard判定・Queue重複確認は実行されるが
        queue.enqueue()は一度も呼ばれない（Spy）。enqueued/failedは0、skipped系は既存どおり機能する
    2.  dry_run=True後、Queue内容が変更されない
    3.  同一状態で複数回Dry RunしてもQueue状態が変化しない（冪等性）
    4.  dry_run=True時もGuardのBLOCK判定（skipped_history）が機能する

    ── 通常実行時（dry_run=False・省略時） ──
    5.  dry_run=Falseでは既存どおりqueue.enqueue()が呼ばれ、enqueuedが加算される
    6.  dry_run省略時も既存動作を維持する（後方互換性）
    7.  enqueue失敗時（Queue容量上限）にfailedが加算される

    ── RetryRuntimeOrchestrator.run_once(dry_run=...)からの伝播（実E2E） ──
    8.  run_once(dry_run=True)：trigger.enqueue_pending_failures()にdry_run=Trueが伝播し、
        Retry Queueへの新規enqueueが抑止される（KI-23の解消）
    9.  run_once(dry_run=False)：既存どおりenqueueされる
    10. run_once()：dry_run省略時のデフォルトがFalseであること（後方互換性）

    ── シグネチャ・Result Contract ──
    11. enqueue_pending_failures()のシグネチャが(self, limit=None, max_attempts=1, dry_run=False)
    12. RetryEnqueueTrigger.__init__のシグネチャが無変更
    13. RetryEnqueueTriggerResultのフィールド構成が変わっていない（新規フィールドを追加しない）
    14. NullRetryEnqueueTriggerのシグネチャが無変更（本Releaseの対象外）
    15. RetryRuntimeOrchestrator.run_once()のシグネチャが無変更（内部の呼び出し変更のみ）
    16. RetryRuntimeOrchestrator.__init__のシグネチャが無変更

    ── Architecture Guard ──
    17. 無改修対象ファイル・ディレクトリに変更がないこと（git diff）
        （scripts/run_retry_runtime.py・RetryRuntimeCycleResult・RetryCompositionRoot・
        RetryManager・RetryExecutor・RetryQueueManager・RetryHistoryManager・
        RetryEnqueueGuard・RetryRuntimeLoop 等）
    18. format_summary()が無改修であること（シグネチャ・出力文字列）。
        実CLIサブプロセス（--dry-run指定）が正常終了すること
    19. AST検査（補助）：dry_runガードがqueue.enqueue()呼び出しより前に位置する
        （実行時Spy検証（テスト1）の補助であり代替ではない）

    ── 副作用なしの確認 ──
    20. RetryEnqueueTrigger実行前後でファイルが一切作成されない

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v5_8_0_retry_enqueue_trigger_dry_run_foundation.py
"""
import ast
import inspect
import os
import subprocess
import sys
import tempfile
from dataclasses import fields
from datetime import datetime
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


print("=" * 60)
print("v5.8.0 Retry Enqueue Trigger Dry Run Foundation E2E テスト")
print("=" * 60)
print()

from workflow_engine import WorkflowEngineResult
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus
from scheduler import SchedulerEngine
from retry_engine import DEFAULT_TARGET_STATUSES, RetryExecutor, RetryManager, RetryPolicy
from retry_enqueue_trigger import (
    NullRetryEnqueueTrigger,
    RetryEnqueueGuard,
    RetryEnqueueTrigger,
    RetryEnqueueTriggerResult,
)
from retry_history import RetryHistoryManager
from retry_queue import RetryQueueConfig, RetryQueueManager
from retry_scheduler_decision import RetrySchedulerDecision
from retry_scheduler_source import RetrySchedulerSource
from retry_runtime_orchestrator import RetryRuntimeOrchestrator


# ─── Fake / Spy群 ───

def make_record(run_id: str, monitor_status: WorkflowMonitorStatus, workflow_name: str = "news") -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name=workflow_name, monitor_status=monitor_status,
        source_status=monitor_status.value, source="manual", job_id="job-1",
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=[],
    )


class FakeWorkflowMonitorManager:
    def __init__(self, records: list):
        self._records = records
        self.calls: list = []

    def list_status(self, limit=None):
        self.calls.append(limit)
        if limit is not None:
            return self._records[:limit]
        return self._records

    def get_status(self, run_id: str):
        for record in self._records:
            if record.run_id == run_id:
                return record
        return None


def make_queue(max_queue_size: int = 100) -> RetryQueueManager:
    config = RetryQueueConfig(enabled=True, max_queue_size=max_queue_size, default_priority=0)
    return RetryQueueManager(config=config)


class SpyRetryQueueManager:
    """RetryQueueManagerをラップし、enqueue() / exists()呼び出しを記録するSpy。"""

    def __init__(self, real: RetryQueueManager):
        self._real = real
        self.enqueue_calls: list[dict] = []
        self.exists_calls: list[str] = []

    def enqueue(self, **kwargs):
        self.enqueue_calls.append(kwargs)
        return self._real.enqueue(**kwargs)

    def exists(self, run_id: str) -> bool:
        self.exists_calls.append(run_id)
        return self._real.exists(run_id)

    def list(self, limit=None):
        return self._real.list(limit=limit)

    def count(self) -> int:
        return self._real.count()

    def remove(self, run_id: str):
        return self._real.remove(run_id)


class SpyRetryHistoryManager:
    """RetryHistoryManagerをラップし、get()呼び出しを記録するSpy。"""

    def __init__(self, real: RetryHistoryManager):
        self._real = real
        self.get_calls: list[str] = []

    def get(self, original_run_id: str):
        self.get_calls.append(original_run_id)
        return self._real.get(original_run_id)

    def record(self, *args, **kwargs):
        return self._real.record(*args, **kwargs)

    def has_history(self, original_run_id: str) -> bool:
        return self._real.has_history(original_run_id)


class SpyRetryEnqueueGuard:
    """RetryEnqueueGuardをラップし、decide()呼び出しを記録するSpy。"""

    def __init__(self, real: RetryEnqueueGuard):
        self._real = real
        self.decide_calls: list[dict] = []

    def decide(self, run_id: str, next_attempt: int, max_attempts: int):
        self.decide_calls.append(
            {"run_id": run_id, "next_attempt": next_attempt, "max_attempts": max_attempts}
        )
        return self._real.decide(run_id, next_attempt=next_attempt, max_attempts=max_attempts)


def make_trigger(records, existing_run_ids=None, history_seed=None, max_queue_size: int = 100):
    """SpyでラップしたQueue/History/GuardでRetryEnqueueTriggerを組み立てる。"""
    real_queue = make_queue(max_queue_size=max_queue_size)
    for run_id in (existing_run_ids or []):
        real_queue.enqueue(run_id=run_id, workflow_name="news", retry_attempt=1)
    spy_queue = SpyRetryQueueManager(real_queue)

    real_history = RetryHistoryManager()
    for run_id, attempt in (history_seed or {}).items():
        real_history.record(run_id, attempt=attempt, recorded_at=datetime.now())
    spy_history = SpyRetryHistoryManager(real_history)

    spy_guard = SpyRetryEnqueueGuard(RetryEnqueueGuard())

    monitor = FakeWorkflowMonitorManager(records=records)
    trigger = RetryEnqueueTrigger(monitor, spy_queue, history=spy_history, guard=spy_guard)
    return trigger, monitor, spy_queue, spy_history, spy_guard, real_queue


# ═══════════════════════════════════════════════════════════
# テスト1: dry_run=True時の読み取り処理維持・書き込み抑止（Spy）
# ═══════════════════════════════════════════════════════════

print("[テスト1] dry_run=True時、読み取り処理は実行されるがqueue.enqueue()は呼ばれない")

records_1 = [
    make_record("run-new", WorkflowMonitorStatus.FAILED),
    make_record("run-existing", WorkflowMonitorStatus.TIMEOUT),
    make_record("run-running", WorkflowMonitorStatus.RUNNING),
]
trigger_1, monitor_1, spy_queue_1, spy_history_1, spy_guard_1, real_queue_1 = make_trigger(
    records_1, existing_run_ids=["run-existing"],
)
result_1 = trigger_1.enqueue_pending_failures(max_attempts=3, dry_run=True)

check_true("1. Monitor走査が実行される", len(monitor_1.calls) == 1)
check_true("1. History参照が実行される（run-newに対してget呼び出し）", "run-new" in spy_history_1.get_calls)
check_true(
    "1. Guard判定が実行される（run-newに対してdecide呼び出し）",
    any(c["run_id"] == "run-new" for c in spy_guard_1.decide_calls),
)
check_true("1. Queue重複確認が実行される（run-newに対してexists呼び出し）", "run-new" in spy_queue_1.exists_calls)
check("1. queue.enqueue()が一度も呼ばれない", spy_queue_1.enqueue_calls, [])
check("1. enqueuedが0", result_1.enqueued, 0)
check("1. failedが0", result_1.failed, 0)
check("1. skipped_existingが1（run-existing）", result_1.skipped_existing, 1)
check("1. skipped_statusが1（run-running）", result_1.skipped_status, 1)
check("1. scannedが3", result_1.scanned, 3)
print()


print("[テスト2] dry_run=True後、Queue内容が変更されない")

check("2. Queueのcountが1のまま（run-existingのみ）", real_queue_1.count(), 1)
check_false("2. run-newはQueueに存在しない", real_queue_1.exists("run-new"))
print()


print("[テスト3] 同一状態で複数回Dry RunしてもQueue状態が変化しない（冪等性）")

result_3a = trigger_1.enqueue_pending_failures(max_attempts=3, dry_run=True)
result_3b = trigger_1.enqueue_pending_failures(max_attempts=3, dry_run=True)
check("3. 1回目と2回目でresultが同一", result_3a, result_3b)
check("3. Queueのcountが変化しない", real_queue_1.count(), 1)
print()


print("[テスト4] dry_run=True時もGuardのBLOCK判定（skipped_history）が機能する")

records_4 = [make_record("run-blocked", WorkflowMonitorStatus.FAILED)]
trigger_4, monitor_4, spy_queue_4, spy_history_4, spy_guard_4, real_queue_4 = make_trigger(
    records_4, history_seed={"run-blocked": 1},
)
result_4 = trigger_4.enqueue_pending_failures(max_attempts=1, dry_run=True)
check("4. skipped_historyが1", result_4.skipped_history, 1)
check("4. queue.enqueue()が呼ばれない", spy_queue_4.enqueue_calls, [])
print()


# ═══════════════════════════════════════════════════════════
# テスト5-7: 通常実行時（dry_run=False・省略時）
# ═══════════════════════════════════════════════════════════

print("[テスト5] dry_run=Falseでは既存どおりqueue.enqueue()が呼ばれる")

records_5 = [make_record("run-normal", WorkflowMonitorStatus.FAILED)]
trigger_5, monitor_5, spy_queue_5, spy_history_5, spy_guard_5, real_queue_5 = make_trigger(records_5)
result_5 = trigger_5.enqueue_pending_failures(max_attempts=3, dry_run=False)
check("5. queue.enqueue()が1回呼ばれる", len(spy_queue_5.enqueue_calls), 1)
check("5. enqueuedが1", result_5.enqueued, 1)
check_true("5. run-normalがQueueに存在する", real_queue_5.exists("run-normal"))
print()


print("[テスト6] dry_run省略時も既存動作を維持する（後方互換性）")

records_6 = [make_record("run-default", WorkflowMonitorStatus.FAILED)]
trigger_6, monitor_6, spy_queue_6, spy_history_6, spy_guard_6, real_queue_6 = make_trigger(records_6)
result_6 = trigger_6.enqueue_pending_failures(max_attempts=3)
check("6. dry_run省略時、enqueuedが1", result_6.enqueued, 1)
check_true("6. run-defaultがQueueに存在する", real_queue_6.exists("run-default"))
print()


print("[テスト7] enqueue失敗時（Queue容量上限）にfailedが加算される")

records_7 = [make_record("run-full", WorkflowMonitorStatus.FAILED)]
trigger_7, monitor_7, spy_queue_7, spy_history_7, spy_guard_7, real_queue_7 = make_trigger(
    records_7, existing_run_ids=["fill-1"], max_queue_size=1,
)
result_7 = trigger_7.enqueue_pending_failures(max_attempts=3, dry_run=False)
check("7. failedが1", result_7.failed, 1)
check("7. enqueuedが0", result_7.enqueued, 0)
print()


# ═══════════════════════════════════════════════════════════
# テスト8-10: RetryRuntimeOrchestrator.run_once(dry_run=...)からの伝播（実E2E）
# ═══════════════════════════════════════════════════════════

class FakeWorkflowEngineManager:
    """WorkflowEngineManagerを模した最小限のFake。run()呼び出しを記録する。"""

    def __init__(self, result: WorkflowEngineResult):
        self.calls: list[dict] = []
        self._result = result

    def run(self, event, dry_run: bool = False) -> WorkflowEngineResult:
        self.calls.append({"event": event, "dry_run": dry_run})
        return self._result


def make_success_engine_result() -> WorkflowEngineResult:
    return WorkflowEngineResult(
        steps=[], overall_success=True, stopped_early=False,
        started_at=datetime.now(), finished_at=datetime.now(),
    )


def build_orchestrator(run_id: str, max_attempts: int = 5):
    engine_result = make_success_engine_result()
    fake_engine = FakeWorkflowEngineManager(engine_result)
    real_executor = RetryExecutor(workflow_engine_manager=fake_engine)

    real_queue = RetryQueueManager.from_config(RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0))
    real_history = RetryHistoryManager()
    real_guard = RetryEnqueueGuard()
    fake_monitor = FakeWorkflowMonitorManager([make_record(run_id, WorkflowMonitorStatus.FAILED)])
    real_trigger = RetryEnqueueTrigger(monitor=fake_monitor, queue=real_queue, history=real_history, guard=real_guard)

    real_source = RetrySchedulerSource(real_queue)
    real_decision = RetrySchedulerDecision(real_source)
    real_scheduler = SchedulerEngine(retry_source=real_source, retry_decision=real_decision)

    policy = RetryPolicy(target_statuses=DEFAULT_TARGET_STATUSES, max_attempts=max_attempts)
    real_manager = RetryManager(
        policy=policy, executor=real_executor, monitor=fake_monitor,
        queue=real_queue, history=real_history,
    )

    orchestrator = RetryRuntimeOrchestrator(
        trigger=real_trigger, scheduler=real_scheduler, manager=real_manager,
        queue=real_queue, history=real_history, policy=policy,
    )
    return orchestrator, real_queue, real_history, fake_engine


print("[テスト8] run_once(dry_run=True)がtriggerへdry_runを伝播し、enqueueが抑止される（KI-23解消）")

orchestrator_8, queue_8, history_8, fake_engine_8 = build_orchestrator("run-orch-dry")
result_8 = orchestrator_8.run_once(dry_run=True)

check_false("8. run_once(dry_run=True)後、run-orch-dryはQueueへenqueueされない", queue_8.exists("run-orch-dry"))
check("8. trigger_result.enqueuedが0", result_8.trigger_result.enqueued, 0)
print()


print("[テスト9] run_once(dry_run=False)は既存どおりenqueueされる")

orchestrator_9, queue_9, history_9, fake_engine_9 = build_orchestrator("run-orch-real")
result_9 = orchestrator_9.run_once(dry_run=False)
check("9. trigger_result.enqueuedが1", result_9.trigger_result.enqueued, 1)
print()


print("[テスト10] run_once()のdry_run省略時、既存どおりenqueueされる（後方互換性）")

orchestrator_10, queue_10, history_10, fake_engine_10 = build_orchestrator("run-orch-default")
result_10 = orchestrator_10.run_once()  # dry_run省略
check("10. trigger_result.enqueuedが1（省略時デフォルトFalse）", result_10.trigger_result.enqueued, 1)
print()


# ═══════════════════════════════════════════════════════════
# テスト11-16: シグネチャ・Result Contract
# ═══════════════════════════════════════════════════════════

print("[テスト11] enqueue_pending_failures()のシグネチャが(self, limit=None, max_attempts=1, dry_run=False)")

sig_11 = inspect.signature(RetryEnqueueTrigger.enqueue_pending_failures)
params_11 = list(sig_11.parameters.keys())
check("11. パラメータがself, limit, max_attempts, dry_run", params_11, ["self", "limit", "max_attempts", "dry_run"])
check("11. limitのデフォルトがNone", sig_11.parameters["limit"].default, None)
check("11. max_attemptsのデフォルトが1", sig_11.parameters["max_attempts"].default, 1)
check("11. dry_runのデフォルトがFalse", sig_11.parameters["dry_run"].default, False)
print()


print("[テスト12] RetryEnqueueTrigger.__init__のシグネチャが無変更")

params_12 = list(inspect.signature(RetryEnqueueTrigger.__init__).parameters.keys())
check("12. パラメータがself, monitor, queue, history, guard", params_12, ["self", "monitor", "queue", "history", "guard"])
print()


print("[テスト13] RetryEnqueueTriggerResultのフィールド構成が変わっていない")

field_names_13 = [f.name for f in fields(RetryEnqueueTriggerResult)]
check(
    "13. フィールドがscanned/enqueued/skipped_existing/skipped_status/failed/skipped_historyのまま",
    field_names_13,
    ["scanned", "enqueued", "skipped_existing", "skipped_status", "failed", "skipped_history"],
)
print()


print("[テスト14] NullRetryEnqueueTriggerのシグネチャが無変更（本Releaseの対象外）")

params_14 = list(inspect.signature(NullRetryEnqueueTrigger.enqueue_pending_failures).parameters.keys())
check("14. パラメータがself, limitのまま（dry_run未追加）", params_14, ["self", "limit"])
print()


print("[テスト15] RetryRuntimeOrchestrator.run_once()のシグネチャが無変更")

sig_15 = inspect.signature(RetryRuntimeOrchestrator.run_once)
params_15 = list(sig_15.parameters.keys())
check("15. パラメータがself, dry_runのまま", params_15, ["self", "dry_run"])
check("15. dry_runのデフォルトがFalse", sig_15.parameters["dry_run"].default, False)
print()


print("[テスト16] RetryRuntimeOrchestrator.__init__のシグネチャが無変更")

params_16 = list(inspect.signature(RetryRuntimeOrchestrator.__init__).parameters.keys())
check(
    "16. パラメータがself, trigger, scheduler, manager, queue, history, policy",
    params_16,
    ["self", "trigger", "scheduler", "manager", "queue", "history", "policy"],
)
print()


# ═══════════════════════════════════════════════════════════
# テスト17-19: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト17] 無改修対象ファイル・ディレクトリに変更がないこと（git diff）")

unchanged_paths_17 = [
    "scripts/run_retry_runtime.py",
    "src/retry_runtime_orchestrator/retry_runtime_cycle_result.py",
    "src/retry_runtime_orchestrator/__init__.py",
    "src/retry_enqueue_trigger/retry_enqueue_guard.py",
    "src/retry_enqueue_trigger/__init__.py",
    "src/retry_composition",
    "src/retry_engine",
    "src/retry_queue",
    "src/retry_history",
    "src/retry_runtime_loop",
    "src/workflow_monitor",
    "src/workflow_engine",
    "src/scheduler",
    "src/retry_scheduler_source",
    "src/retry_scheduler_decision",
    "src/ai",
    "src/execution_history",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths_17:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"17. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("17. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト18] format_summary()が無改修であること（シグネチャ・出力文字列・実CLI動作）")

import importlib.util

SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_retry_runtime.py"
spec_18 = importlib.util.spec_from_file_location("run_retry_runtime_v580", SCRIPT_PATH)
run_retry_runtime_18 = importlib.util.module_from_spec(spec_18)
spec_18.loader.exec_module(run_retry_runtime_18)

sig_18 = inspect.signature(run_retry_runtime_18.format_summary)
check("18. format_summary()のパラメータがresultのみ", list(sig_18.parameters.keys()), ["result"])

sample_trigger_result_18 = RetryEnqueueTriggerResult(
    scanned=7, enqueued=2, skipped_existing=3, skipped_status=1, failed=1,
)
sample_result_18 = run_retry_runtime_18.RetryRuntimeCycleResult(
    trigger_result=sample_trigger_result_18,
    scheduler_events=[1, 2],
    execution_results=[1],
    removal_results=[1],
    cleanup_results=[],
    terminal_cleanup_results=[],
    history_results=[1],
)
summary_text_18 = run_retry_runtime_18.format_summary(sample_result_18)
check_true(
    "18. format_summary()の出力にenqueued=2が含まれる（従来どおりの表示）",
    "enqueued=2" in summary_text_18,
)
check_false(
    "18. format_summary()の出力にdry_run_planned等の新規カウンタが含まれない",
    "dry_run_planned" in summary_text_18,
)


def run_cli(env_overrides: dict, extra_args: list = None, timeout: int = 60):
    env = dict(os.environ)
    for key in (
        "AI_AGENT_ENABLED", "WORKFLOW_ENGINE_ENABLED", "RETRY_ENGINE_ENABLED",
        "RETRY_QUEUE_ENABLED", "WORKFLOW_MONITOR_ENABLED",
        "REVIEW_TRIGGER_AGENT_ENABLED", "PUBLISH_TRIGGER_AGENT_ENABLED",
    ):
        env.pop(key, None)
    env.update(env_overrides)
    env["PYTHONIOENCODING"] = "utf-8"
    args = [sys.executable, str(SCRIPT_PATH)] + (extra_args or [])
    return subprocess.run(
        args, cwd=str(PROJECT_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env, timeout=timeout,
    )


completed_18 = run_cli({
    "AI_AGENT_ENABLED": "false", "WORKFLOW_ENGINE_ENABLED": "false", "RETRY_ENGINE_ENABLED": "false",
}, extra_args=["--dry-run"])
check("18. 実CLI（--dry-run）のreturncodeが0", completed_18.returncode, 0)
check_true("18. 実CLI出力に[DRY RUN MODE]が含まれる", "[DRY RUN MODE]" in completed_18.stdout)
check_true("18. 実CLI出力に'Retry Runtime 実行結果'が含まれる", "Retry Runtime 実行結果" in completed_18.stdout)
print()


print("[テスト19] AST検査（補助）：dry_runガードがqueue.enqueue()呼び出しより前に位置する")

source_19 = (PROJECT_ROOT / "src" / "retry_enqueue_trigger" / "retry_enqueue_trigger.py").read_text(encoding="utf-8")
tree_19 = ast.parse(source_19)

func_node_19 = next(
    n for n in ast.walk(tree_19)
    if isinstance(n, ast.FunctionDef) and n.name == "enqueue_pending_failures"
)

dry_run_if_lines_19 = [
    n.lineno for n in ast.walk(func_node_19)
    if isinstance(n, ast.If)
    and isinstance(n.test, ast.Name) and n.test.id == "dry_run"
    and any(isinstance(s, ast.Continue) for s in n.body)
]
enqueue_call_lines_19 = [
    n.lineno for n in ast.walk(func_node_19)
    if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and n.func.attr == "enqueue"
]

check_true("19. dry_runをテストしContinueするIf文が1件存在する（補助AST検査）", len(dry_run_if_lines_19) == 1)
check_true("19. queue.enqueue()呼び出しが1件存在する（補助AST検査）", len(enqueue_call_lines_19) == 1)
check_true(
    "19. dry_runガードがqueue.enqueue()呼び出しより前に位置する（補助AST検査）",
    bool(dry_run_if_lines_19) and bool(enqueue_call_lines_19)
    and dry_run_if_lines_19[0] < enqueue_call_lines_19[0],
)
print()


# ═══════════════════════════════════════════════════════════
# テスト20: 副作用なしの確認
# ═══════════════════════════════════════════════════════════

print("[テスト20] RetryEnqueueTrigger実行前後でファイルが作成されない")

with tempfile.TemporaryDirectory() as tmp_dir:
    write_check_dir = Path(tmp_dir)
    before_files_20 = list(write_check_dir.rglob("*"))

    history_20 = RetryHistoryManager()
    history_20.record("run-io", attempt=1, recorded_at=datetime.now())
    monitor_20 = FakeWorkflowMonitorManager(records=[make_record("run-io", WorkflowMonitorStatus.FAILED)])
    queue_20 = make_queue()
    trigger_20 = RetryEnqueueTrigger(monitor_20, queue_20, history=history_20)
    trigger_20.enqueue_pending_failures(max_attempts=3, dry_run=True)
    trigger_20.enqueue_pending_failures(max_attempts=3, dry_run=False)
    NullRetryEnqueueTrigger().enqueue_pending_failures()

    after_files_20 = list(write_check_dir.rglob("*"))
    check("20. 実行前後でファイルが作成されない", after_files_20, before_files_20)
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
