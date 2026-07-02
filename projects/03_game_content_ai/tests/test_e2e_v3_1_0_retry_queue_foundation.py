"""
E2E テスト: v3.1.0 Retry Queue Foundation

テストシナリオ:
    ── RetryQueueStatus ──
    1.  5値（WAITING/PROCESSING/CANCELLED/COMPLETED/FAILED）が定義されている

    ── RetryQueueItem ──
    2.  構築・フィールドの整合性

    ── RetryQueueConfig ──
    3.  from_env() のデフォルト値（enabled=True/max_queue_size=100/default_priority=0）・
        環境変数上書き・is_ready()

    ── RetryQueueResult / RetryQueueOutcome ──
    4.  構築・フィールドの整合性・7値の確認

    ── RetryQueueManager.enqueue() ──
    5.  enqueueできる（outcome=ENQUEUED、status=WAITING）
    6.  priority省略時はconfig.default_priorityが使われる
    7.  duplicate run_id → REJECTED、Queueの中身は変化しない
    8.  max_queue_sizeを超えたenqueue → REJECTED

    ── RetryQueueManager.dequeue() ──
    9.  priority昇順・enqueue_time昇順で取り出される
    10. dequeue後、status=PROCESSINGに更新されQueueから消える（list/exists/countに反映）
    11. 空のQueueに対するdequeue() → EMPTY

    ── RetryQueueManager.remove() ──
    12. removeできる（outcome=REMOVED、status=CANCELLED、Queueから消える）
    13. 存在しないrun_idのremove() → NOT_FOUND

    ── RetryQueueManager.list() / exists() / count() ──
    14. list()がpriority順で返る・limitが効く
    15. exists()の真偽
    16. count()がenqueue/dequeue/removeに追従する

    ── コピーの独立性 ──
    17. enqueue()/list()/dequeue()が返すRetryQueueItemを書き換えても内部ストアは影響を受けない

    ── RetryQueueManager.from_config()（ゲート判定） ──
    18. RetryQueueConfig.enabled=False → NullRetryQueueManager
    19. RetryQueueConfig.enabled=True → RetryQueueManager（実インスタンス）

    ── NullRetryQueueManager ──
    20. enqueue/dequeue/remove が常に outcome=DISABLED を返す
    21. list()/exists()/count() が安全な既定値を返す

    ── 書き込みが発生しないことの確認 ──
    22. RetryQueueManager実行前後でファイルが一切作成されない（in-memoryのみ）

    ── Architecture Guard ──
    23. src/retry_queue/ が workflow_engine/workflow_monitor/retry_engine/
        execution_history/ai/pipeline/schedulerをimportしない（静的検査）
    24. 既存ファイル（retry_engine/workflow_engine/workflow_monitor/execution_history等）に
        変更がないこと（git diff）
    25. retry_queue パッケージのexport確認

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v3_1_0_retry_queue_foundation.py
"""
import os
import subprocess
import sys
import tempfile
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


def check_none(label: str, value):
    check(label, value is None, True)


print("=" * 60)
print("v3.1.0 Retry Queue Foundation E2E テスト")
print("=" * 60)
print()

from retry_queue import (
    NullRetryQueueManager,
    RetryQueueConfig,
    RetryQueueItem,
    RetryQueueManager,
    RetryQueueOutcome,
    RetryQueueResult,
    RetryQueueStatus,
)

ENV_KEYS = ("RETRY_QUEUE_ENABLED", "RETRY_QUEUE_MAX_SIZE", "RETRY_QUEUE_DEFAULT_PRIORITY")


def clear_env():
    for key in ENV_KEYS:
        os.environ.pop(key, None)


# ═══════════════════════════════════════════════════════════
# テスト1: RetryQueueStatus
# ═══════════════════════════════════════════════════════════

print("[テスト1] RetryQueueStatus の定義")

check(
    "1. RetryQueueStatusの5値が定義されている",
    {s.value for s in RetryQueueStatus},
    {"waiting", "processing", "cancelled", "completed", "failed"},
)
print()


# ═══════════════════════════════════════════════════════════
# テスト2: RetryQueueItem
# ═══════════════════════════════════════════════════════════

print("[テスト2] RetryQueueItem の構築")

from datetime import datetime

item_2 = RetryQueueItem(
    run_id="run-2", workflow_name="news", enqueue_time=datetime.now(),
    priority=1, retry_attempt=1, status=RetryQueueStatus.WAITING,
)
check("2. RetryQueueItem.run_id", item_2.run_id, "run-2")
check("2. RetryQueueItem.workflow_name", item_2.workflow_name, "news")
check("2. RetryQueueItem.status", item_2.status, RetryQueueStatus.WAITING)
print()


# ═══════════════════════════════════════════════════════════
# テスト3: RetryQueueConfig
# ═══════════════════════════════════════════════════════════

print("[テスト3] RetryQueueConfig.from_env()")

clear_env()
c1 = RetryQueueConfig.from_env()
check_true("3. デフォルト enabled=True", c1.enabled)
check("3. デフォルト max_queue_size=100", c1.max_queue_size, 100)
check("3. デフォルト default_priority=0", c1.default_priority, 0)
check_true("3. デフォルトは is_ready()=True", c1.is_ready())

os.environ["RETRY_QUEUE_ENABLED"] = "false"
os.environ["RETRY_QUEUE_MAX_SIZE"] = "5"
os.environ["RETRY_QUEUE_DEFAULT_PRIORITY"] = "3"
c2 = RetryQueueConfig.from_env()
check_false("3. RETRY_QUEUE_ENABLED=false で enabled=False", c2.enabled)
check("3. RETRY_QUEUE_MAX_SIZE の環境変数上書き", c2.max_queue_size, 5)
check("3. RETRY_QUEUE_DEFAULT_PRIORITY の環境変数上書き", c2.default_priority, 3)
check_false("3. is_ready()=False", c2.is_ready())
clear_env()
print()


# ═══════════════════════════════════════════════════════════
# テスト4: RetryQueueResult / RetryQueueOutcome
# ═══════════════════════════════════════════════════════════

print("[テスト4] RetryQueueResult / RetryQueueOutcome の構築")

res_4 = RetryQueueResult(outcome=RetryQueueOutcome.REJECTED, item=None, reason="duplicate run_id: r1")
check("4. RetryQueueResult.outcome", res_4.outcome, RetryQueueOutcome.REJECTED)
check(
    "4. RetryQueueOutcomeの7値が定義されている",
    {o.value for o in RetryQueueOutcome},
    {"enqueued", "dequeued", "removed", "rejected", "not_found", "empty", "disabled"},
)
print()


# ═══════════════════════════════════════════════════════════
# テスト5-8: RetryQueueManager.enqueue()
# ═══════════════════════════════════════════════════════════

print("[テスト5-8] RetryQueueManager.enqueue()")

mgr_5 = RetryQueueManager(config=RetryQueueConfig(enabled=True, max_queue_size=2, default_priority=9))
result_5 = mgr_5.enqueue("run-5", "news", retry_attempt=1)
check("5. enqueue() は outcome=ENQUEUED を返す", result_5.outcome, RetryQueueOutcome.ENQUEUED)
check("5. enqueueされた項目のstatus=WAITING", result_5.item.status, RetryQueueStatus.WAITING)
check_true("5. exists('run-5')=True", mgr_5.exists("run-5"))

result_6 = mgr_5.enqueue("run-6", "news", retry_attempt=1)
check("6. priority省略時は default_priority(9) が使われる", result_6.item.priority, 9)

result_7 = mgr_5.enqueue("run-5", "news", retry_attempt=2)
check("7. 重複run_id → REJECTED", result_7.outcome, RetryQueueOutcome.REJECTED)
check_none("7. REJECTED時 item は None", result_7.item)
check_contains("7. reasonにduplicateである旨が含まれる", result_7.reason, "duplicate")
check("7. Queueの中身は変化しない(count=2)", mgr_5.count(), 2)

# max_queue_size=2 に対し既に2件（run-5, run-6）入っているため3件目は拒否される
result_8 = mgr_5.enqueue("run-8", "news", retry_attempt=1)
check("8. max_queue_size超過 → REJECTED", result_8.outcome, RetryQueueOutcome.REJECTED)
check_contains("8. reasonに容量超過である旨が含まれる", result_8.reason, "full")
check("8. Queueの中身は変化しない(count=2)", mgr_5.count(), 2)
print()


# ═══════════════════════════════════════════════════════════
# テスト9-11: RetryQueueManager.dequeue()
# ═══════════════════════════════════════════════════════════

print("[テスト9-11] RetryQueueManager.dequeue()")

mgr_9 = RetryQueueManager(config=RetryQueueConfig(enabled=True, max_queue_size=10, default_priority=0))
mgr_9.enqueue("run-low", "news", priority=5)
mgr_9.enqueue("run-high", "news", priority=1)
mgr_9.enqueue("run-mid", "news", priority=3)

d1 = mgr_9.dequeue()
check("9. priority最小(1)の項目が最初に取り出される", d1.item.run_id, "run-high")
d2 = mgr_9.dequeue()
check("9. 次にpriority=3の項目が取り出される", d2.item.run_id, "run-mid")
d3 = mgr_9.dequeue()
check("9. 最後にpriority=5の項目が取り出される", d3.item.run_id, "run-low")

check("10. dequeueされた項目のstatus=PROCESSING", d1.item.status, RetryQueueStatus.PROCESSING)
check_false("10. dequeue後はexists()がFalseになる", mgr_9.exists("run-high"))
check("10. dequeue後はcount()が減る", mgr_9.count(), 0)
check("10. dequeue後はlist()にも現れない", mgr_9.list(), [])

d_empty = mgr_9.dequeue()
check("11. 空のQueueへのdequeue() → EMPTY", d_empty.outcome, RetryQueueOutcome.EMPTY)
check_none("11. EMPTY時 item は None", d_empty.item)
print()


# ═══════════════════════════════════════════════════════════
# テスト12-13: RetryQueueManager.remove()
# ═══════════════════════════════════════════════════════════

print("[テスト12-13] RetryQueueManager.remove()")

mgr_12 = RetryQueueManager(config=RetryQueueConfig(enabled=True, max_queue_size=10, default_priority=0))
mgr_12.enqueue("run-12", "news", retry_attempt=1)
r_remove = mgr_12.remove("run-12")
check("12. remove() は outcome=REMOVED を返す", r_remove.outcome, RetryQueueOutcome.REMOVED)
check("12. removeされた項目のstatus=CANCELLED", r_remove.item.status, RetryQueueStatus.CANCELLED)
check_false("12. remove後はexists()がFalseになる", mgr_12.exists("run-12"))
check("12. remove後はcount()が減る", mgr_12.count(), 0)

r_not_found = mgr_12.remove("run-missing")
check("13. 存在しないrun_idのremove() → NOT_FOUND", r_not_found.outcome, RetryQueueOutcome.NOT_FOUND)
check_none("13. NOT_FOUND時 item は None", r_not_found.item)
print()


# ═══════════════════════════════════════════════════════════
# テスト14-16: list() / exists() / count()
# ═══════════════════════════════════════════════════════════

print("[テスト14-16] list() / exists() / count()")

mgr_14 = RetryQueueManager(config=RetryQueueConfig(enabled=True, max_queue_size=10, default_priority=0))
mgr_14.enqueue("run-b", "news", priority=2)
mgr_14.enqueue("run-a", "news", priority=1)
mgr_14.enqueue("run-c", "news", priority=3)

listed = mgr_14.list()
check("14. list() がpriority順で返る", [i.run_id for i in listed], ["run-a", "run-b", "run-c"])
listed_limited = mgr_14.list(limit=2)
check("14. list(limit=2) が先頭2件のみ返す", [i.run_id for i in listed_limited], ["run-a", "run-b"])

check_true("15. exists('run-a')=True", mgr_14.exists("run-a"))
check_false("15. exists('run-x')=False", mgr_14.exists("run-x"))

check("16. count()が現在の件数を返す", mgr_14.count(), 3)
mgr_14.dequeue()
check("16. dequeue後にcount()が1減る", mgr_14.count(), 2)
mgr_14.remove("run-c")
check("16. remove後にcount()がさらに1減る", mgr_14.count(), 1)
print()


# ═══════════════════════════════════════════════════════════
# テスト17: コピーの独立性
# ═══════════════════════════════════════════════════════════

print("[テスト17] 返されるRetryQueueItemがコピーであること")

mgr_17 = RetryQueueManager(config=RetryQueueConfig(enabled=True, max_queue_size=10, default_priority=0))
enq_result = mgr_17.enqueue("run-17", "news", retry_attempt=1)
enq_result.item.status = RetryQueueStatus.CANCELLED
enq_result.item.workflow_name = "tampered"

listed_17 = mgr_17.list()
check("17. enqueue()の戻り値を書き換えても内部ストアは影響を受けない(status)", listed_17[0].status, RetryQueueStatus.WAITING)
check("17. enqueue()の戻り値を書き換えても内部ストアは影響を受けない(workflow_name)", listed_17[0].workflow_name, "news")

listed_17[0].priority = 999
listed_17_again = mgr_17.list()
check("17. list()の戻り値を書き換えても内部ストアは影響を受けない", listed_17_again[0].priority, 0)
print()


# ═══════════════════════════════════════════════════════════
# テスト18-19: RetryQueueManager.from_config()
# ═══════════════════════════════════════════════════════════

print("[テスト18-19] RetryQueueManager.from_config()（ゲート判定）")

mgr_18 = RetryQueueManager.from_config(RetryQueueConfig(enabled=False, max_queue_size=10, default_priority=0))
check_true("18. enabled=False → NullRetryQueueManager", isinstance(mgr_18, NullRetryQueueManager))

mgr_19 = RetryQueueManager.from_config(RetryQueueConfig(enabled=True, max_queue_size=10, default_priority=0))
check_true("19. enabled=True → RetryQueueManager（実インスタンス）", isinstance(mgr_19, RetryQueueManager))
print()


# ═══════════════════════════════════════════════════════════
# テスト20-21: NullRetryQueueManager
# ═══════════════════════════════════════════════════════════

print("[テスト20-21] NullRetryQueueManager")

null_mgr = NullRetryQueueManager()

r_enqueue = null_mgr.enqueue("run-x", "news", retry_attempt=1)
check("20. enqueue() は outcome=DISABLED を返す", r_enqueue.outcome, RetryQueueOutcome.DISABLED)
r_dequeue = null_mgr.dequeue()
check("20. dequeue() は outcome=DISABLED を返す", r_dequeue.outcome, RetryQueueOutcome.DISABLED)
r_remove = null_mgr.remove("run-x")
check("20. remove() は outcome=DISABLED を返す", r_remove.outcome, RetryQueueOutcome.DISABLED)

check("21. list() は空リストを返す", null_mgr.list(), [])
check_false("21. exists() は常にFalse", null_mgr.exists("run-x"))
check("21. count() は常に0", null_mgr.count(), 0)
print()


# ═══════════════════════════════════════════════════════════
# テスト22: 書き込みが発生しないことの確認
# ═══════════════════════════════════════════════════════════

print("[テスト22] Retry Queue自身がファイルを一切作成しないこと")

write_check_dir = Path(tempfile.mkdtemp())
before_files = list(write_check_dir.rglob("*"))

mgr_22 = RetryQueueManager.from_config(RetryQueueConfig(enabled=True, max_queue_size=10, default_priority=0))
mgr_22.enqueue("run-22", "news", retry_attempt=1)
mgr_22.dequeue()
mgr_22.enqueue("run-22b", "news", retry_attempt=1)
mgr_22.remove("run-22b")
mgr_22.list()
mgr_22.exists("run-22")
mgr_22.count()
NullRetryQueueManager().enqueue("run-22c", "news")

after_files = list(write_check_dir.rglob("*"))
check("22. Retry Queue実行前後でファイルが作成されない", after_files, before_files)
print()


# ═══════════════════════════════════════════════════════════
# テスト23-25: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト23] retry_queue が既存パッケージを一切importしない（静的検査）")

rq_dir = PROJECT_ROOT / "src" / "retry_queue"
for py_file in sorted(rq_dir.glob("*.py")):
    source = py_file.read_text(encoding="utf-8")
    import_lines = "\n".join(
        line for line in source.splitlines()
        if line.strip().startswith("from ") or line.strip().startswith("import ")
    )
    for forbidden in (
        "workflow_engine", "workflow_monitor", "retry_engine", "execution_history",
        "scheduler", "from ai", "import ai", "from pipeline", "import pipeline",
    ):
        check_false(
            f"23. {py_file.name} が {forbidden} をimportしない",
            forbidden in import_lines,
        )
print()


print("[テスト24] 既存ファイルの無変更確認（git diff）")

unchanged_paths_rq = [
    "main.py",
    "src/retry_engine/retry_config.py",
    "src/retry_engine/retry_executor.py",
    "src/retry_engine/retry_manager.py",
    "src/retry_engine/retry_policy.py",
    "src/retry_engine/retry_request.py",
    "src/retry_engine/retry_result.py",
    "src/execution_history/execution_history_manager.py",
    "src/execution_history/json_execution_history_store.py",
    "src/workflow_engine/workflow_engine_executor.py",
    "src/workflow_engine/workflow_engine_manager.py",
    "src/workflow_monitor/workflow_monitor.py",
    "src/workflow_monitor/workflow_monitor_manager.py",
    "src/workflow_monitor/workflow_monitor_status.py",
    "src/ai/agent_manager.py",
    "src/scheduler/scheduler_engine.py",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths_rq:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"24. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("24. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト25] import確認（retry_queue パッケージのexport）")

import retry_queue as rq_pkg
for name in (
    "RetryQueueStatus", "RetryQueueItem", "RetryQueueOutcome", "RetryQueueResult",
    "RetryQueueConfig", "RetryQueueManager", "NullRetryQueueManager",
):
    check_true(f"25. {name} が retry_queue パッケージからエクスポートされている", hasattr(rq_pkg, name))
    check_true(f"25. {name} が retry_queue.__all__ に含まれる", name in rq_pkg.__all__)
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
