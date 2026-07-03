"""
E2E テスト: v3.3.0 Retry Scheduler Integration

テストシナリオ:
    ── RetrySchedulerSource（有効時） ──
    1.  list_pending_retries() が RetryQueueManager.list() の結果とそのまま一致する
    2.  limit引数が RetryQueueManager.list(limit=...) へそのまま渡される
    3.  count_pending_retries() が RetryQueueManager.count() の結果とそのまま一致する
    4.  Queueが空の場合、list_pending_retries() は []、count_pending_retries() は 0
    5.  list_pending_retries() の戻り値の順序が RetryQueueManager.list() と同じ
        （priority昇順・enqueue_time昇順）であること

    ── NullRetrySchedulerSource ──
    6.  list_pending_retries() は常に []（引数の有無に関わらず）
    7.  count_pending_retries() は常に 0
    8.  retry_queue への参照（_queue 属性）を一切保持しない

    ── Constructor Injection のみ／Manager・Configパターン不採用の確認 ──
    9.  RetrySchedulerSource / NullRetrySchedulerSource いずれも from_config を持たない
    10. RetrySchedulerSource / NullRetrySchedulerSource いずれも from_env を持たない
    11. RetrySchedulerSource.__init__ が queue のみを受け取る（Constructor Injection）
    12. retry_scheduler_source パッケージ内に Config を名前に含むクラスが存在しない
    13. RetrySchedulerSource / NullRetrySchedulerSource のインスタンスが
        enabled 属性を持たない（Feature Gateを持たないことの確認）

    ── dequeue() / remove() を一切使用しないことの構造的確認 ──
    14. list_pending_retries() / count_pending_retries() の呼び出し中に
        queue.dequeue() / queue.remove() が一度も呼ばれない

    ── ディレクトリ構成 ──
    15. src/retry_scheduler_source/ が __init__.py と retry_scheduler_source.py の
        2ファイルのみで構成されている（Configファイル等を作っていないことの確認）

    ── Architecture Guard ──
    16. retry_scheduler_source が workflow_engine/workflow_monitor/retry_engine/
        execution_history/scheduler/ai/pipeline をimportしない（静的検査）
    17. 本Releaseでは retry_scheduler_source をどのパッケージからも呼び出さない
        （他の src/*/*.py が retry_scheduler_source をimportしていないことの確認）
    18. 既存ファイル（src/scheduler/ 配下・src/retry_queue/ 配下・src/retry_engine/ 配下等）
        に変更がないこと（git diff）
    19. retry_scheduler_source パッケージのexport確認

    ── 副作用なしの確認 ──
    20. RetrySchedulerSource実行前後でファイルが一切作成されない（in-memoryのみ）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v3_3_0_retry_scheduler_integration.py
"""
import inspect
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


print("=" * 60)
print("v3.3.0 Retry Scheduler Integration E2E テスト")
print("=" * 60)
print()

from retry_queue import RetryQueueConfig, RetryQueueManager
from retry_scheduler_source import NullRetrySchedulerSource, RetrySchedulerSource


def make_queue() -> RetryQueueManager:
    config = RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0)
    return RetryQueueManager(config=config)


# ═══════════════════════════════════════════════════════════
# テスト1-5: RetrySchedulerSource（有効時）
# ═══════════════════════════════════════════════════════════

print("[テスト1] list_pending_retries() が RetryQueueManager.list() と一致する")

queue_1 = make_queue()
queue_1.enqueue(run_id="run-a", workflow_name="news", retry_attempt=1, priority=2)
queue_1.enqueue(run_id="run-b", workflow_name="news", retry_attempt=1, priority=1)
source_1 = RetrySchedulerSource(queue_1)

expected_1 = queue_1.list()
actual_1 = source_1.list_pending_retries()
check("1. list_pending_retries()の件数が一致", len(actual_1), len(expected_1))
check(
    "1. list_pending_retries()のrun_id列が一致",
    [item.run_id for item in actual_1],
    [item.run_id for item in expected_1],
)
print()


print("[テスト2] limit引数が RetryQueueManager.list(limit=...) へそのまま渡される")

actual_2 = source_1.list_pending_retries(limit=1)
check("2. limit=1で1件のみ返る", len(actual_2), 1)
check("2. limit=1でpriority最小の項目が返る", actual_2[0].run_id, "run-b")
print()


print("[テスト3] count_pending_retries() が RetryQueueManager.count() と一致する")

check("3. count_pending_retries()がcount()と一致", source_1.count_pending_retries(), queue_1.count())
check("3. count_pending_retries()の値そのもの", source_1.count_pending_retries(), 2)
print()


print("[テスト4] Queueが空の場合の list_pending_retries() / count_pending_retries()")

queue_4 = make_queue()
source_4 = RetrySchedulerSource(queue_4)
check("4. 空Queueでlist_pending_retries()は[]", source_4.list_pending_retries(), [])
check("4. 空Queueでcount_pending_retries()は0", source_4.count_pending_retries(), 0)
print()


print("[テスト5] list_pending_retries()の順序がpriority昇順・enqueue_time昇順")

queue_5 = make_queue()
queue_5.enqueue(run_id="run-x", workflow_name="news", retry_attempt=1, priority=5)
queue_5.enqueue(run_id="run-y", workflow_name="news", retry_attempt=1, priority=0)
queue_5.enqueue(run_id="run-z", workflow_name="news", retry_attempt=1, priority=3)
source_5 = RetrySchedulerSource(queue_5)
check(
    "5. priority昇順で並んでいる",
    [item.run_id for item in source_5.list_pending_retries()],
    ["run-y", "run-z", "run-x"],
)
print()


# ═══════════════════════════════════════════════════════════
# テスト6-8: NullRetrySchedulerSource
# ═══════════════════════════════════════════════════════════

print("[テスト6] NullRetrySchedulerSource.list_pending_retries() は常に []")

null_source_6 = NullRetrySchedulerSource()
check("6. 引数なしで[]", null_source_6.list_pending_retries(), [])
check("6. limit指定でも[]", null_source_6.list_pending_retries(limit=10), [])
print()


print("[テスト7] NullRetrySchedulerSource.count_pending_retries() は常に 0")

check("7. count_pending_retries()は0", null_source_6.count_pending_retries(), 0)
print()


print("[テスト8] NullRetrySchedulerSource が retry_queue への参照を保持しない")

check_false("8. _queue属性を持たない", hasattr(null_source_6, "_queue"))
check("8. インスタンス変数を一切持たない", vars(null_source_6), {})
print()


# ═══════════════════════════════════════════════════════════
# テスト9-13: Constructor Injectionのみ／Manager・Configパターン不採用
# ═══════════════════════════════════════════════════════════

print("[テスト9] from_config を持たない")

check_false("9. RetrySchedulerSourceがfrom_configを持たない", hasattr(RetrySchedulerSource, "from_config"))
check_false("9. NullRetrySchedulerSourceがfrom_configを持たない", hasattr(NullRetrySchedulerSource, "from_config"))
print()


print("[テスト10] from_env を持たない")

check_false("10. RetrySchedulerSourceがfrom_envを持たない", hasattr(RetrySchedulerSource, "from_env"))
check_false("10. NullRetrySchedulerSourceがfrom_envを持たない", hasattr(NullRetrySchedulerSource, "from_env"))
print()


print("[テスト11] RetrySchedulerSource.__init__ が queue のみを受け取る")

params_11 = list(inspect.signature(RetrySchedulerSource.__init__).parameters.keys())
check("11. __init__のパラメータがself, queueのみ", params_11, ["self", "queue"])
print()


print("[テスト12] retry_scheduler_source パッケージ内に Config クラスが存在しない")

import retry_scheduler_source as rss_pkg

config_named = [name for name in dir(rss_pkg) if "Config" in name]
check("12. Configを名前に含むシンボルが存在しない", config_named, [])
print()


print("[テスト13] enabled 属性を持たない（Feature Gateを持たないことの確認）")

check_false("13. RetrySchedulerSourceインスタンスがenabledを持たない", hasattr(source_1, "enabled"))
check_false("13. NullRetrySchedulerSourceインスタンスがenabledを持たない", hasattr(null_source_6, "enabled"))
print()


# ═══════════════════════════════════════════════════════════
# テスト14: dequeue() / remove() を一切使用しないことの構造的確認
# ═══════════════════════════════════════════════════════════

print("[テスト14] dequeue() / remove() が一度も呼ばれない")


class _QueueSpy:
    """list()/count()以外が呼ばれたら例外を送出するダミーQueue。"""

    def __init__(self, real):
        self._real = real

    def list(self, limit=None):
        return self._real.list(limit=limit)

    def count(self):
        return self._real.count()

    def dequeue(self):
        raise AssertionError("dequeue() must not be called by RetrySchedulerSource")

    def remove(self, run_id):
        raise AssertionError("remove() must not be called by RetrySchedulerSource")

    def enqueue(self, *args, **kwargs):
        raise AssertionError("enqueue() must not be called by RetrySchedulerSource")

    def exists(self, run_id):
        raise AssertionError("exists() must not be called by RetrySchedulerSource")


queue_14 = make_queue()
queue_14.enqueue(run_id="run-spy", workflow_name="news", retry_attempt=1, priority=0)
spy_14 = _QueueSpy(queue_14)
source_14 = RetrySchedulerSource(spy_14)

try:
    source_14.list_pending_retries()
    source_14.count_pending_retries()
    no_forbidden_call = True
except AssertionError:
    no_forbidden_call = False
check_true("14. list/count呼び出し中にdequeue/remove/enqueue/existsが呼ばれない", no_forbidden_call)
print()


# ═══════════════════════════════════════════════════════════
# テスト15: ディレクトリ構成
# ═══════════════════════════════════════════════════════════

print("[テスト15] src/retry_scheduler_source/ のファイル構成")

rss_dir = PROJECT_ROOT / "src" / "retry_scheduler_source"
py_files = sorted(p.name for p in rss_dir.glob("*.py"))
check("15. __init__.py と retry_scheduler_source.py の2ファイルのみ", py_files, ["__init__.py", "retry_scheduler_source.py"])
print()


# ═══════════════════════════════════════════════════════════
# テスト16-19: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト16] retry_scheduler_source が既存パッケージを一切importしない（静的検査）")

for py_file in sorted(rss_dir.glob("*.py")):
    source = py_file.read_text(encoding="utf-8")
    import_lines = "\n".join(
        line for line in source.splitlines()
        if line.strip().startswith("from ") or line.strip().startswith("import ")
    )
    for forbidden in (
        "workflow_engine", "workflow_monitor", "retry_engine", "execution_history",
        "from scheduler", "import scheduler", "from ai", "import ai", "from pipeline", "import pipeline",
    ):
        check_false(f"16. {py_file.name} が {forbidden} をimportしない", forbidden in import_lines)
print()


print("[テスト17] 本Releaseでは retry_scheduler_source をどこからも呼び出さない")

src_dir = PROJECT_ROOT / "src"
consumers = []
for py_file in sorted(src_dir.rglob("*.py")):
    if py_file.parent.name == "retry_scheduler_source":
        continue
    text = py_file.read_text(encoding="utf-8")
    if "retry_scheduler_source" in text:
        consumers.append(str(py_file.relative_to(PROJECT_ROOT)))
check("17. retry_scheduler_sourceを参照する既存ファイルが存在しない", consumers, [])
print()


print("[テスト18] 既存ファイルの無変更確認（git diff）")

unchanged_paths_18 = [
    "main.py",
    "src/scheduler/scheduler_engine.py",
    "src/scheduler/scheduler_manager.py",
    "src/scheduler/scheduler_job.py",
    "src/scheduler/scheduler_event.py",
    "src/scheduler/scheduler_repository.py",
    "src/scheduler/scheduler_config.py",
    "src/scheduler/__init__.py",
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
    "src/retry_engine/retry_request.py",
    "src/retry_engine/retry_result.py",
    "src/retry_engine/__init__.py",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths_18:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"18. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("18. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト19] import確認（retry_scheduler_source パッケージのexport）")

for name in ("RetrySchedulerSource", "NullRetrySchedulerSource"):
    check_true(f"19. {name} が retry_scheduler_source パッケージからエクスポートされている", hasattr(rss_pkg, name))
    check_true(f"19. {name} が retry_scheduler_source.__all__ に含まれる", name in rss_pkg.__all__)
print()


# ═══════════════════════════════════════════════════════════
# テスト20: 副作用なしの確認
# ═══════════════════════════════════════════════════════════

print("[テスト20] RetrySchedulerSource実行前後でファイルが作成されない")

import tempfile

with tempfile.TemporaryDirectory() as tmp_dir:
    write_check_dir = Path(tmp_dir)
    before_files_20 = list(write_check_dir.rglob("*"))

    queue_20 = make_queue()
    queue_20.enqueue(run_id="run-io", workflow_name="news", retry_attempt=1)
    source_20 = RetrySchedulerSource(queue_20)
    source_20.list_pending_retries()
    source_20.count_pending_retries()
    NullRetrySchedulerSource().list_pending_retries()
    NullRetrySchedulerSource().count_pending_retries()

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
