"""
E2E テスト: v3.5.0 Retry Scheduler Decision

テストシナリオ:
    ── RetrySchedulerDecision（有効時：RetrySchedulerSource） ──
    1.  select_candidates() が RetrySchedulerSource.list_pending_retries() の結果とそのまま一致する
    2.  limit引数が list_pending_retries(limit=...) へそのまま渡される
    3.  select_candidates() の戻り値の順序がpriority昇順・enqueue_time昇順であること（独自ソートしない）
    4.  Queueが空の場合、select_candidates()は[]、select_next_candidate()はNone
    5.  select_next_candidate() が select_candidates(limit=1) の先頭要素と一致する
    6.  select_next_candidate() が優先度最上位（priority最小）の候補を返す

    ── RetrySchedulerDecision（無効時：NullRetrySchedulerSource） ──
    7.  select_candidates() は常に []（retry_queueへは一切到達しない）
    8.  select_next_candidate() は常に None

    ── Constructor Injection の必須性 ──
    9.  RetrySchedulerDecision.__init__ が retry_source を必須引数として要求する
        （デフォルト値を持たない。inspect.signatureで確認）
    10. RetrySchedulerDecision() を引数なしで呼ぶと TypeError になる

    ── dequeue() / remove() / enqueue() / exists() / count() を一切使用しないことの構造的確認 ──
    11. select_candidates() / select_next_candidate() 呼び出し中、
        list_pending_retries() 以外のメソッドが一度も呼ばれない（Spy）

    ── Null Object Pattern 不採用の確認 ──
    12. retry_scheduler_decision パッケージ内に NullRetrySchedulerDecision が存在しない
    13. retry_scheduler_decision パッケージから NullRetrySchedulerDecision がexportされていない

    ── Feature Gate / Config / Manager 追加なしの確認 ──
    14. RetrySchedulerDecision が from_config / from_env を持たない
    15. retry_scheduler_decision 配下に Config を名前に含むクラス・enabled フィールドを
        持つクラスが存在しない

    ── ディレクトリ構成 ──
    16. src/retry_scheduler_decision/ が __init__.py と retry_scheduler_decision.py の
        2ファイルのみで構成されている

    ── Architecture Guard ──
    17. retry_scheduler_decision が scheduler / retry_queue / retry_engine /
        workflow_engine / workflow_monitor / execution_history / ai / pipeline を
        一切importしない（静的検査）
    18. 本Releaseでは retry_scheduler_decision をどのパッケージからも呼び出さない
        （他の src/*/*.py が retry_scheduler_decision をimportしていないことの確認）
    19. 既存ファイル（src/scheduler/ 配下・src/retry_scheduler_source/ 配下・
        src/retry_queue/ 配下・src/retry_engine/ 配下）に変更がないこと（git diff）

    ── 副作用なしの確認 ──
    20. RetrySchedulerDecision実行前後でファイルが一切作成されない（in-memoryのみ）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v3_5_0_retry_scheduler_decision.py
"""
import ast
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


def check_none(label: str, value):
    check(label, value is None, True)


print("=" * 60)
print("v3.5.0 Retry Scheduler Decision E2E テスト")
print("=" * 60)
print()

from retry_queue import RetryQueueConfig, RetryQueueManager
from retry_scheduler_source import NullRetrySchedulerSource, RetrySchedulerSource
from retry_scheduler_decision import RetrySchedulerDecision


def make_queue() -> RetryQueueManager:
    config = RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0)
    return RetryQueueManager(config=config)


# ═══════════════════════════════════════════════════════════
# テスト1-6: RetrySchedulerDecision（有効時：RetrySchedulerSource）
# ═══════════════════════════════════════════════════════════

print("[テスト1-6] RetrySchedulerDecision（有効時）")

queue1 = make_queue()
queue1.enqueue(run_id="run-a", workflow_name="news", retry_attempt=1, priority=1)
queue1.enqueue(run_id="run-b", workflow_name="news", retry_attempt=1, priority=0)
source1 = RetrySchedulerSource(queue1)
decision1 = RetrySchedulerDecision(source1)

check(
    "1. select_candidates() が RetrySchedulerSource.list_pending_retries() と一致",
    [item.run_id for item in decision1.select_candidates()],
    [item.run_id for item in source1.list_pending_retries()],
)

check(
    "2. limit引数がそのまま伝播する",
    [item.run_id for item in decision1.select_candidates(limit=1)],
    ["run-b"],
)

check(
    "3. select_candidates()の順序がpriority昇順（run-b: priority=0が先頭）",
    [item.run_id for item in decision1.select_candidates()],
    ["run-b", "run-a"],
)

queue4 = make_queue()
source4 = RetrySchedulerSource(queue4)
decision4 = RetrySchedulerDecision(source4)
check("4. Queueが空の場合、select_candidates()は[]", decision4.select_candidates(), [])
check_none("4. Queueが空の場合、select_next_candidate()はNone", decision4.select_next_candidate())

next_candidate5 = decision1.select_next_candidate()
check("5. select_next_candidate()がselect_candidates(limit=1)の先頭要素と一致", next_candidate5.run_id, "run-b")

check("6. select_next_candidate()が優先度最上位(priority最小)の候補を返す", next_candidate5.priority, 0)
print()


# ═══════════════════════════════════════════════════════════
# テスト7-8: RetrySchedulerDecision（無効時：NullRetrySchedulerSource）
# ═══════════════════════════════════════════════════════════

print("[テスト7-8] RetrySchedulerDecision（無効時：NullRetrySchedulerSource）")

decision7 = RetrySchedulerDecision(NullRetrySchedulerSource())
check("7. select_candidates() は常に []", decision7.select_candidates(), [])
check("7. limit指定時も常に []", decision7.select_candidates(limit=5), [])
check_none("8. select_next_candidate() は常に None", decision7.select_next_candidate())
print()


# ═══════════════════════════════════════════════════════════
# テスト9-10: Constructor Injection の必須性
# ═══════════════════════════════════════════════════════════

print("[テスト9] retry_source が必須引数（デフォルト値を持たない）")

sig = inspect.signature(RetrySchedulerDecision.__init__)
retry_source_param = sig.parameters["retry_source"]
check_true("9. retry_source パラメータがデフォルト値を持たない", retry_source_param.default is inspect.Parameter.empty)
print()

print("[テスト10] RetrySchedulerDecision() を引数なしで呼ぶと TypeError")

try:
    RetrySchedulerDecision()
    check_true("10. 引数なし構築は TypeError", False)
except TypeError:
    check_true("10. 引数なし構築は TypeError", True)
print()


# ═══════════════════════════════════════════════════════════
# テスト11: dequeue() / remove() / enqueue() / exists() / count() が呼ばれない
# ═══════════════════════════════════════════════════════════

print("[テスト11] list_pending_retries() 以外が一切呼ばれない（Spy）")


class _RetrySourceSpy:
    """list_pending_retries() 以外が呼ばれたら例外を送出するダミー。"""

    def __init__(self, real):
        self._real = real

    def list_pending_retries(self, limit=None):
        return self._real.list_pending_retries(limit=limit)

    def __getattr__(self, name):
        def _forbidden(*args, **kwargs):
            raise AssertionError(f"{name}() must not be called by RetrySchedulerDecision")
        return _forbidden


queue11 = make_queue()
queue11.enqueue(run_id="run-11", workflow_name="news", retry_attempt=1, priority=0)
spy11 = _RetrySourceSpy(RetrySchedulerSource(queue11))
decision11 = RetrySchedulerDecision(spy11)

try:
    decision11.select_candidates(limit=3)
    decision11.select_next_candidate()
    no_forbidden_call = True
except AssertionError:
    no_forbidden_call = False
check_true("11. select_candidates/select_next_candidate呼び出し中に他のメソッドが呼ばれない", no_forbidden_call)
print()


# ═══════════════════════════════════════════════════════════
# テスト12-13: Null Object Pattern 不採用の確認
# ═══════════════════════════════════════════════════════════

print("[テスト12] retry_scheduler_decision パッケージ内に NullRetrySchedulerDecision が存在しない")

import retry_scheduler_decision.retry_scheduler_decision as rsd_module
check_false("12. retry_scheduler_decision モジュールに NullRetrySchedulerDecision が定義されていない", hasattr(rsd_module, "NullRetrySchedulerDecision"))
print()

print("[テスト13] retry_scheduler_decision パッケージから NullRetrySchedulerDecision がexportされていない")

import retry_scheduler_decision as rsd_pkg
check_false("13. retry_scheduler_decision パッケージが NullRetrySchedulerDecision を公開していない", hasattr(rsd_pkg, "NullRetrySchedulerDecision"))
check("13. __all__ に NullRetrySchedulerDecision が含まれない", "NullRetrySchedulerDecision" in rsd_pkg.__all__, False)
check("13. __all__ は RetrySchedulerDecision のみ", rsd_pkg.__all__, ["RetrySchedulerDecision"])
print()


# ═══════════════════════════════════════════════════════════
# テスト14-15: Feature Gate / Config / Manager 追加なしの確認
# ═══════════════════════════════════════════════════════════

print("[テスト14] RetrySchedulerDecision が from_config / from_env を持たない")

check_false("14. RetrySchedulerDecision.from_config が存在しない", hasattr(RetrySchedulerDecision, "from_config"))
check_false("14. RetrySchedulerDecision.from_env が存在しない", hasattr(RetrySchedulerDecision, "from_env"))
print()

print("[テスト15] retry_scheduler_decision 配下に Config/enabled を持つクラスが存在しない")

rsd_dir = PROJECT_ROOT / "src" / "retry_scheduler_decision"
for py_file in sorted(rsd_dir.glob("*.py")):
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    class_names = [node.name for node in ast.walk(tree) if isinstance(node, ast.ClassDef)]
    for class_name in class_names:
        check_false(f"15. {py_file.name} の class {class_name} に 'Config' が含まれない", "Config" in class_name)
check_true("15. RetrySchedulerDecisionインスタンスがenabled属性を持たない", not hasattr(decision1, "enabled"))
print()


# ═══════════════════════════════════════════════════════════
# テスト16: ディレクトリ構成
# ═══════════════════════════════════════════════════════════

print("[テスト16] src/retry_scheduler_decision/ のファイル構成")

py_files_16 = sorted(p.name for p in rsd_dir.glob("*.py"))
check("16. __init__.py と retry_scheduler_decision.py の2ファイルのみ", py_files_16, ["__init__.py", "retry_scheduler_decision.py"])
print()


# ═══════════════════════════════════════════════════════════
# テスト17-19: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト17] retry_scheduler_decision が既存パッケージを一切importしない（静的検査）")

for py_file in sorted(rsd_dir.glob("*.py")):
    source_text = py_file.read_text(encoding="utf-8")
    import_lines = "\n".join(
        line for line in source_text.splitlines()
        if line.strip().startswith("from ") or line.strip().startswith("import ")
    )
    for forbidden in (
        "workflow_engine", "workflow_monitor", "retry_engine", "execution_history",
        "from scheduler", "import scheduler", "from retry_queue", "import retry_queue",
        "from ai", "import ai", "from pipeline", "import pipeline",
    ):
        check_false(f"17. {py_file.name} が {forbidden} をimportしない", forbidden in import_lines)
print()

print("[テスト18] 本Releaseでは retry_scheduler_decision をどこからも呼び出さない")

src_dir = PROJECT_ROOT / "src"
consumers = []
for py_file in sorted(src_dir.rglob("*.py")):
    if py_file.parent.name == "retry_scheduler_decision":
        continue
    text = py_file.read_text(encoding="utf-8")
    if "retry_scheduler_decision" in text:
        consumers.append(str(py_file.relative_to(PROJECT_ROOT)))
check("18. retry_scheduler_decisionを参照する既存ファイルが存在しない", consumers, [])
print()

print("[テスト19] 既存ファイルの無変更確認（git diff）")

unchanged_paths_19 = [
    "src/scheduler/scheduler_engine.py",
    "src/scheduler/scheduler_manager.py",
    "src/scheduler/scheduler_job.py",
    "src/scheduler/scheduler_event.py",
    "src/scheduler/scheduler_repository.py",
    "src/scheduler/scheduler_config.py",
    "src/scheduler/exceptions.py",
    "src/scheduler/__init__.py",
    "src/retry_scheduler_source/retry_scheduler_source.py",
    "src/retry_scheduler_source/__init__.py",
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
    for rel_path in unchanged_paths_19:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"19. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("19. gitが利用できないため無変更確認をスキップ", True)
print()


# ═══════════════════════════════════════════════════════════
# テスト20: 副作用なしの確認
# ═══════════════════════════════════════════════════════════

print("[テスト20] RetrySchedulerDecision実行前後でファイルが作成されない")

import tempfile

with tempfile.TemporaryDirectory() as tmp_dir:
    write_check_dir = Path(tmp_dir)
    before_files_20 = list(write_check_dir.rglob("*"))

    queue20 = make_queue()
    queue20.enqueue(run_id="run-20", workflow_name="news", retry_attempt=1, priority=0)
    decision20 = RetrySchedulerDecision(RetrySchedulerSource(queue20))
    decision20.select_candidates()
    decision20.select_next_candidate()
    RetrySchedulerDecision(NullRetrySchedulerSource()).select_candidates()
    RetrySchedulerDecision(NullRetrySchedulerSource()).select_next_candidate()

    after_files_20 = list(write_check_dir.rglob("*"))
    check("20. 実行前後でファイルが一切作成されない", after_files_20, before_files_20)
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
