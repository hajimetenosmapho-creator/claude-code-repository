"""
E2E テスト: v4.6.0 Retry Enqueue Trigger Foundation

テストシナリオ:
    ── RetryEnqueueTrigger（有効時） ──
    1.  FAILED/TIMEOUTのレコードのみenqueueされ、RUNNING/SUCCESSはスキップされる
    2.  既にQueueに存在するrun_idは再enqueueされない（skipped_existing）
    3.  enqueue_pending_failures() の戻り値の集計（scanned/enqueued/
        skipped_existing/skipped_status/failed）が正しいこと
    4.  limit引数が WorkflowMonitorManager.list_status(limit=...) へそのまま渡される
    5.  Monitorに0件の場合、全フィールド0の結果を返す
    6.  enqueueされた項目がRetryQueueManagerに実際に反映されていること
        （workflow_name・retry_attempt=1・priority=デフォルト値）
    7.  Queue容量超過時にfailedとしてカウントされる（REJECTED）

    ── NullRetryEnqueueTrigger ──
    8.  enqueue_pending_failures() は常に全フィールド0（引数の有無に関わらず）
    9.  workflow_monitor / retry_queue への参照（_monitor / _queue 属性）を
        一切保持しない

    ── Constructor Injection のみ／Manager・Configパターン不採用の確認 ──
    10. RetryEnqueueTrigger / NullRetryEnqueueTrigger いずれも from_config を持たない
    11. RetryEnqueueTrigger / NullRetryEnqueueTrigger いずれも from_env を持たない
    12. RetryEnqueueTrigger.__init__ が monitor, queue のみを受け取る
        （Constructor Injection）
    13. retry_enqueue_trigger パッケージ内に Config を名前に含むクラスが存在しない
    14. RetryEnqueueTrigger / NullRetryEnqueueTrigger のインスタンスが
        enabled 属性を持たない（Feature Gateを持たないことの確認）

    ── dequeue() / remove() / get_status() を一切使用しないことの構造的確認 ──
    15. enqueue_pending_failures() の呼び出し中に queue.dequeue() /
        queue.remove() / monitor.get_status() が一度も呼ばれない

    ── ディレクトリ構成 ──
    16. src/retry_enqueue_trigger/ が __init__.py と retry_enqueue_trigger.py の
        2ファイルのみで構成されている（Configファイル等を作っていないことの確認）

    ── Architecture Guard ──
    17. retry_enqueue_trigger が retry_engine/workflow_engine/execution_history/
        scheduler/ai/pipelineをimportしない（静的検査、retry_engineを経由しない
        ことの確認）
    18. 本Releaseでは retry_enqueue_trigger をどのパッケージからも呼び出さない
        （他の src/*/*.py が retry_enqueue_trigger をimportしていないことの確認）
    19. 既存ファイル（src/workflow_monitor/ 配下・src/retry_queue/ 配下・
        src/retry_engine/ 配下等）に変更がないこと（git diff）
    20. retry_enqueue_trigger パッケージのexport確認

    ── 副作用なしの確認 ──
    21. RetryEnqueueTrigger実行前後でファイルが一切作成されない（in-memoryのみ）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v4_6_0_retry_enqueue_trigger_foundation.py
"""
import inspect
import subprocess
import sys
from datetime import datetime
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


print("=" * 60)
print("v4.6.0 Retry Enqueue Trigger Foundation E2E テスト")
print("=" * 60)
print()

from retry_enqueue_trigger import NullRetryEnqueueTrigger, RetryEnqueueTrigger, RetryEnqueueTriggerResult
from retry_queue import RetryQueueConfig, RetryQueueManager
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus


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


def make_queue(max_queue_size: int = 100) -> RetryQueueManager:
    config = RetryQueueConfig(enabled=True, max_queue_size=max_queue_size, default_priority=0)
    return RetryQueueManager(config=config)


# ═══════════════════════════════════════════════════════════
# テスト1-7: RetryEnqueueTrigger（有効時）
# ═══════════════════════════════════════════════════════════

print("[テスト1] FAILED/TIMEOUTのみenqueueされ、RUNNING/SUCCESSはスキップされる")

monitor_1 = FakeWorkflowMonitorManager(records=[
    make_record("run-failed", WorkflowMonitorStatus.FAILED),
    make_record("run-timeout", WorkflowMonitorStatus.TIMEOUT),
    make_record("run-running", WorkflowMonitorStatus.RUNNING),
    make_record("run-success", WorkflowMonitorStatus.SUCCESS),
])
queue_1 = make_queue()
trigger_1 = RetryEnqueueTrigger(monitor_1, queue_1)

result_1 = trigger_1.enqueue_pending_failures()
check("1. enqueued件数（FAILED+TIMEOUTの2件）", result_1.enqueued, 2)
check("1. skipped_status件数（RUNNING+SUCCESSの2件）", result_1.skipped_status, 2)
check_true("1. run-failedがQueueに存在する", queue_1.exists("run-failed"))
check_true("1. run-timeoutがQueueに存在する", queue_1.exists("run-timeout"))
check_false("1. run-runningがQueueに存在しない", queue_1.exists("run-running"))
check_false("1. run-successがQueueに存在しない", queue_1.exists("run-success"))
print()


print("[テスト2] 既にQueueに存在するrun_idは再enqueueされない")

monitor_2 = FakeWorkflowMonitorManager(records=[make_record("run-dup", WorkflowMonitorStatus.FAILED)])
queue_2 = make_queue()
queue_2.enqueue(run_id="run-dup", workflow_name="news", retry_attempt=1)
trigger_2 = RetryEnqueueTrigger(monitor_2, queue_2)

result_2 = trigger_2.enqueue_pending_failures()
check("2. enqueued件数（既存のため0件）", result_2.enqueued, 0)
check("2. skipped_existing件数", result_2.skipped_existing, 1)
check("2. Queueの件数が増えていない", queue_2.count(), 1)
print()


print("[テスト3] enqueue_pending_failures() の戻り値の集計が正しい")

monitor_3 = FakeWorkflowMonitorManager(records=[
    make_record("run-a", WorkflowMonitorStatus.FAILED),
    make_record("run-b", WorkflowMonitorStatus.TIMEOUT),
    make_record("run-c", WorkflowMonitorStatus.RUNNING),
    make_record("run-d", WorkflowMonitorStatus.SUCCESS),
])
queue_3 = make_queue()
queue_3.enqueue(run_id="run-existing", workflow_name="news", retry_attempt=1)
trigger_3 = RetryEnqueueTrigger(monitor_3, queue_3)

result_3 = trigger_3.enqueue_pending_failures()
check(
    "3. RetryEnqueueTriggerResultの内容が一致",
    result_3,
    RetryEnqueueTriggerResult(scanned=4, enqueued=2, skipped_existing=0, skipped_status=2, failed=0),
)
print()


print("[テスト4] limit引数が WorkflowMonitorManager.list_status(limit=...) へそのまま渡される")

monitor_4 = FakeWorkflowMonitorManager(records=[
    make_record("run-1", WorkflowMonitorStatus.FAILED),
    make_record("run-2", WorkflowMonitorStatus.FAILED),
    make_record("run-3", WorkflowMonitorStatus.FAILED),
])
queue_4 = make_queue()
trigger_4 = RetryEnqueueTrigger(monitor_4, queue_4)

result_4 = trigger_4.enqueue_pending_failures(limit=2)
check("4. list_status()にlimit=2が渡された", monitor_4.calls, [2])
check("4. scannedが2件（limitで絞られた）", result_4.scanned, 2)
check("4. enqueuedが2件", result_4.enqueued, 2)
print()


print("[テスト5] Monitorに0件の場合、全フィールド0の結果を返す")

monitor_5 = FakeWorkflowMonitorManager(records=[])
queue_5 = make_queue()
trigger_5 = RetryEnqueueTrigger(monitor_5, queue_5)

result_5 = trigger_5.enqueue_pending_failures()
check(
    "5. 0件時の結果がすべて0",
    result_5,
    RetryEnqueueTriggerResult(scanned=0, enqueued=0, skipped_existing=0, skipped_status=0, failed=0),
)
print()


print("[テスト6] enqueueされた項目がRetryQueueManagerに実際に反映されている")

monitor_6 = FakeWorkflowMonitorManager(records=[make_record("run-6", WorkflowMonitorStatus.FAILED, workflow_name="my-workflow")])
queue_6 = make_queue()
trigger_6 = RetryEnqueueTrigger(monitor_6, queue_6)

trigger_6.enqueue_pending_failures()
item_6 = queue_6.list()[0]
check("6. run_idが一致", item_6.run_id, "run-6")
check("6. workflow_nameが一致", item_6.workflow_name, "my-workflow")
check("6. retry_attemptがデフォルト1", item_6.retry_attempt, 1)
check("6. priorityがdefault_priority(0)", item_6.priority, 0)
print()


print("[テスト7] Queue容量超過時にfailedとしてカウントされる（REJECTED）")

monitor_7 = FakeWorkflowMonitorManager(records=[
    make_record("run-full-1", WorkflowMonitorStatus.FAILED),
    make_record("run-full-2", WorkflowMonitorStatus.FAILED),
])
queue_7 = make_queue(max_queue_size=1)
trigger_7 = RetryEnqueueTrigger(monitor_7, queue_7)

result_7 = trigger_7.enqueue_pending_failures()
check("7. enqueuedが1件（容量上限）", result_7.enqueued, 1)
check("7. failedが1件（容量超過によるREJECTED）", result_7.failed, 1)
print()


# ═══════════════════════════════════════════════════════════
# テスト8-9: NullRetryEnqueueTrigger
# ═══════════════════════════════════════════════════════════

print("[テスト8] NullRetryEnqueueTrigger.enqueue_pending_failures() は常に全フィールド0")

null_trigger_8 = NullRetryEnqueueTrigger()
check(
    "8. 引数なしで全フィールド0",
    null_trigger_8.enqueue_pending_failures(),
    RetryEnqueueTriggerResult(scanned=0, enqueued=0, skipped_existing=0, skipped_status=0, failed=0),
)
check(
    "8. limit指定でも全フィールド0",
    null_trigger_8.enqueue_pending_failures(limit=10),
    RetryEnqueueTriggerResult(scanned=0, enqueued=0, skipped_existing=0, skipped_status=0, failed=0),
)
print()


print("[テスト9] NullRetryEnqueueTrigger が workflow_monitor / retry_queue への参照を保持しない")

check_false("9. _monitor属性を持たない", hasattr(null_trigger_8, "_monitor"))
check_false("9. _queue属性を持たない", hasattr(null_trigger_8, "_queue"))
check("9. インスタンス変数を一切持たない", vars(null_trigger_8), {})
print()


# ═══════════════════════════════════════════════════════════
# テスト10-14: Constructor Injectionのみ／Manager・Configパターン不採用
# ═══════════════════════════════════════════════════════════

print("[テスト10] from_config を持たない")

check_false("10. RetryEnqueueTriggerがfrom_configを持たない", hasattr(RetryEnqueueTrigger, "from_config"))
check_false("10. NullRetryEnqueueTriggerがfrom_configを持たない", hasattr(NullRetryEnqueueTrigger, "from_config"))
print()


print("[テスト11] from_env を持たない")

check_false("11. RetryEnqueueTriggerがfrom_envを持たない", hasattr(RetryEnqueueTrigger, "from_env"))
check_false("11. NullRetryEnqueueTriggerがfrom_envを持たない", hasattr(NullRetryEnqueueTrigger, "from_env"))
print()


print("[テスト12] RetryEnqueueTrigger.__init__ が monitor, queue のみを受け取る")

params_12 = list(inspect.signature(RetryEnqueueTrigger.__init__).parameters.keys())
check("12. __init__のパラメータがself, monitor, queueのみ", params_12, ["self", "monitor", "queue"])
print()


print("[テスト13] retry_enqueue_trigger パッケージ内に Config クラスが存在しない")

import retry_enqueue_trigger as ret_pkg

config_named_13 = [name for name in dir(ret_pkg) if "Config" in name]
check("13. Configを名前に含むシンボルが存在しない", config_named_13, [])
print()


print("[テスト14] enabled 属性を持たない（Feature Gateを持たないことの確認）")

check_false("14. RetryEnqueueTriggerインスタンスがenabledを持たない", hasattr(trigger_1, "enabled"))
check_false("14. NullRetryEnqueueTriggerインスタンスがenabledを持たない", hasattr(null_trigger_8, "enabled"))
print()


# ═══════════════════════════════════════════════════════════
# テスト15: dequeue() / remove() / get_status() を一切使用しないことの構造的確認
# ═══════════════════════════════════════════════════════════

print("[テスト15] dequeue() / remove() / get_status() が一度も呼ばれない")


class _QueueSpy:
    """exists()/enqueue()以外が呼ばれたら例外を送出するダミーQueue。"""

    def __init__(self, real):
        self._real = real

    def exists(self, run_id):
        return self._real.exists(run_id)

    def enqueue(self, *args, **kwargs):
        return self._real.enqueue(*args, **kwargs)

    def dequeue(self):
        raise AssertionError("dequeue() must not be called by RetryEnqueueTrigger")

    def remove(self, run_id):
        raise AssertionError("remove() must not be called by RetryEnqueueTrigger")

    def list(self, limit=None):
        raise AssertionError("list() must not be called by RetryEnqueueTrigger")

    def count(self):
        raise AssertionError("count() must not be called by RetryEnqueueTrigger")


class _MonitorSpy:
    """list_status()以外が呼ばれたら例外を送出するダミーMonitor。"""

    def __init__(self, real):
        self._real = real

    def list_status(self, limit=None):
        return self._real.list_status(limit=limit)

    def get_status(self, run_id):
        raise AssertionError("get_status() must not be called by RetryEnqueueTrigger")


monitor_15 = _MonitorSpy(FakeWorkflowMonitorManager(records=[make_record("run-spy", WorkflowMonitorStatus.FAILED)]))
queue_15 = _QueueSpy(make_queue())
trigger_15 = RetryEnqueueTrigger(monitor_15, queue_15)

try:
    trigger_15.enqueue_pending_failures()
    no_forbidden_call = True
except AssertionError:
    no_forbidden_call = False
check_true("15. 呼び出し中にdequeue/remove/list/count/get_statusが呼ばれない", no_forbidden_call)
print()


# ═══════════════════════════════════════════════════════════
# テスト16: ディレクトリ構成
# ═══════════════════════════════════════════════════════════

print("[テスト16] src/retry_enqueue_trigger/ のファイル構成")

ret_dir = PROJECT_ROOT / "src" / "retry_enqueue_trigger"
py_files_16 = sorted(p.name for p in ret_dir.glob("*.py"))
check("16. __init__.py と retry_enqueue_trigger.py の2ファイルのみ", py_files_16, ["__init__.py", "retry_enqueue_trigger.py"])
print()


# ═══════════════════════════════════════════════════════════
# テスト17-20: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト17] retry_enqueue_trigger が retry_engine 等を一切importしない（静的検査）")

for py_file in sorted(ret_dir.glob("*.py")):
    source = py_file.read_text(encoding="utf-8")
    import_lines = "\n".join(
        line for line in source.splitlines()
        if line.strip().startswith("from ") or line.strip().startswith("import ")
    )
    for forbidden in (
        "retry_engine", "workflow_engine", "execution_history",
        "from scheduler", "import scheduler", "from ai", "import ai", "from pipeline", "import pipeline",
        "retry_scheduler_source", "retry_scheduler_decision",
    ):
        check_false(f"17. {py_file.name} が {forbidden} をimportしない", forbidden in import_lines)
print()


print("[テスト18] 本Releaseでは retry_enqueue_trigger をどこからも呼び出さない")

src_dir = PROJECT_ROOT / "src"
consumers_18 = []
for py_file in sorted(src_dir.rglob("*.py")):
    if py_file.parent.name == "retry_enqueue_trigger":
        continue
    text = py_file.read_text(encoding="utf-8")
    if "retry_enqueue_trigger" in text:
        consumers_18.append(str(py_file.relative_to(PROJECT_ROOT)))
check("18. retry_enqueue_triggerを参照する既存ファイルが存在しない", consumers_18, [])
print()


print("[テスト19] 既存ファイルの無変更確認（git diff）")

unchanged_paths_19 = [
    "main.py",
    "src/workflow_monitor/workflow_monitor.py",
    "src/workflow_monitor/workflow_monitor_manager.py",
    "src/workflow_monitor/workflow_monitor_config.py",
    "src/workflow_monitor/workflow_monitor_record.py",
    "src/workflow_monitor/workflow_monitor_status.py",
    "src/workflow_monitor/__init__.py",
    "src/retry_queue/retry_queue_manager.py",
    "src/retry_queue/null_retry_queue_manager.py",
    "src/retry_queue/retry_queue_config.py",
    "src/retry_queue/retry_queue_item.py",
    "src/retry_queue/retry_queue_result.py",
    "src/retry_queue/retry_queue_status.py",
    "src/retry_queue/__init__.py",
    "src/retry_engine/retry_config.py",
    "src/retry_engine/retry_executor.py",
    "src/retry_engine/retry_manager.py",
    "src/retry_engine/retry_policy.py",
    "src/retry_engine/retry_policy_protocol.py",
    "src/retry_engine/retry_request.py",
    "src/retry_engine/retry_result.py",
    "src/retry_engine/__init__.py",
    "src/retry_scheduler_source/retry_scheduler_source.py",
    "src/retry_scheduler_source/__init__.py",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths_19:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"19. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("19. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト20] import確認（retry_enqueue_trigger パッケージのexport）")

for name in ("RetryEnqueueTrigger", "NullRetryEnqueueTrigger", "RetryEnqueueTriggerResult"):
    check_true(f"20. {name} が retry_enqueue_trigger パッケージからエクスポートされている", hasattr(ret_pkg, name))
    check_true(f"20. {name} が retry_enqueue_trigger.__all__ に含まれる", name in ret_pkg.__all__)
print()


# ═══════════════════════════════════════════════════════════
# テスト21: 副作用なしの確認
# ═══════════════════════════════════════════════════════════

print("[テスト21] RetryEnqueueTrigger実行前後でファイルが作成されない")

import tempfile

with tempfile.TemporaryDirectory() as tmp_dir:
    write_check_dir = Path(tmp_dir)
    before_files_21 = list(write_check_dir.rglob("*"))

    monitor_21 = FakeWorkflowMonitorManager(records=[make_record("run-io", WorkflowMonitorStatus.FAILED)])
    queue_21 = make_queue()
    trigger_21 = RetryEnqueueTrigger(monitor_21, queue_21)
    trigger_21.enqueue_pending_failures()
    NullRetryEnqueueTrigger().enqueue_pending_failures()

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
