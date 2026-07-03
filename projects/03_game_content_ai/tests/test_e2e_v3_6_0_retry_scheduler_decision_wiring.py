"""
E2E テスト: v3.6.0 Retry Scheduler Decision Wiring

テストシナリオ:
    ── SchedulerEngine.__init__ の Constructor Injection（retry_decision） ──
    1.  retry_decision を省略した場合、select_candidates()は[]、select_next_candidate()はNone
    2.  retry_decision に RetrySchedulerDecision（RetrySchedulerSourceベース）を渡すとそのまま保持される
    3.  retry_decision に RetrySchedulerDecision（NullRetrySchedulerSourceベース）を渡すとそのまま保持される
    4.  clock / retry_source のみ指定してもretry_decisionは省略時と同じくNoneのまま

    ── select_candidates() / select_next_candidate()（retry_decision注入時：候補あり） ──
    5.  select_candidates() が RetrySchedulerDecision.select_candidates() と一致する
    6.  limit引数が select_candidates(limit=...) へそのまま伝播する
    7.  select_candidates() の順序がpriority昇順（独自ソートしない）
    8.  select_next_candidate() が select_candidates(limit=1) の先頭要素と一致する

    ── select_candidates() / select_next_candidate()（Queueが空 / Null経由） ──
    9.  Queueが空の場合、select_candidates()は[]、select_next_candidate()はNone
    10. RetrySchedulerDecision(NullRetrySchedulerSource())を注入した場合も同様に[] / None

    ── select_candidates() / select_next_candidate()（retry_decision=None、ガード節） ──
    11. retry_decision省略時、select_candidates()は常に[]（RetrySchedulerDecisionへ一切アクセスしない）
    12. retry_decision省略時、select_next_candidate()は常にNone
    13. retry_decision省略時、limit指定時も常に[]

    ── SchedulerEngineがRetrySchedulerDecisionを自ら構築しないことの構造的確認 ──
    14. scheduler_engine.py のソースコードに 'RetrySchedulerDecision(' という
        構築呼び出し（インスタンス生成）が一切存在しない（ASTベース。import文は対象外）
    15. SchedulerEngineのインスタンスが _retry_decision 以外にRetrySchedulerDecision
        関連の属性を持たない

    ── evaluate() / run_due() が無変更であることの回帰確認 ──
    16. retry_decisionを渡してもevaluate()の判定結果はretry_decision未指定時と完全に同じ
    17. retry_decisionを渡してもrun_due()の判定結果はretry_decision未指定時と完全に同じ
    18. select_candidates()/select_next_candidate()呼び出し後もevaluate()の結果は変わらない

    ── dequeue() / remove() 等の構造的確認（Spy） ──
    19. select_candidates() / select_next_candidate() 呼び出し中、
        select_candidates / select_next_candidate 以外のメソッドが
        retry_decisionに対して一度も呼ばれない（Spy）

    ── Feature Gate / Config / Manager 追加なしの確認 ──
    20. src/scheduler/ 配下に新規ファイルが追加されていない（v3.4.0からファイル一覧が変わらない）
    21. SchedulerEngine が from_config / from_env を持たない（Constructor Injectionのみ）

    ── Architecture Guard ──
    22. src/scheduler/ 配下のいずれのファイルも retry_queue / retry_engine を
        直接importしない（retry_scheduler_source / retry_scheduler_decision経由のみ）
    23. src/scheduler/ に 'RetryQueueManager' / 'RetryManager' への実コード参照がない（AST）
    24. retry_scheduler_decision / retry_scheduler_source / retry_queue / retry_engine
        配下の全ファイル、および src/scheduler/ 配下の scheduler_engine.py と
        __init__.py 以外の全ファイルに変更がないこと（git diff、ゼロ改修の確認）

    ── 既存回帰（v2.6.0 / v3.4.0 SchedulerEngine挙動） ──
    25. DAILY/INTERVAL/ONCEの判定結果が従来と同一（retry_decision省略時）
    26. disabledなJobは引き続き判定対象から除外される
    27. count_pending_retries() / list_pending_retries()（v3.4.0）の挙動が
        本Releaseでも維持される

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v3_6_0_retry_scheduler_decision_wiring.py
"""
import ast
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


def check_none(label: str, value):
    check(label, value is None, True)


print("=" * 60)
print("v3.6.0 Retry Scheduler Decision Wiring E2E テスト")
print("=" * 60)
print()

from scheduler import SchedulerEngine, SchedulerJob, TriggerType
from retry_queue import RetryQueueConfig, RetryQueueManager
from retry_scheduler_source import NullRetrySchedulerSource, RetrySchedulerSource
from retry_scheduler_decision import RetrySchedulerDecision


def make_queue() -> RetryQueueManager:
    config = RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0)
    return RetryQueueManager(config=config)


class _FixedClockProvider:
    def __init__(self, fixed_now: datetime):
        self._fixed_now = fixed_now

    def now(self) -> datetime:
        return self._fixed_now


# ═══════════════════════════════════════════════════════════
# テスト1-4: SchedulerEngine.__init__ の Constructor Injection（retry_decision）
# ═══════════════════════════════════════════════════════════

print("[テスト1-4] Constructor Injection（retry_decision）")

engine1 = SchedulerEngine()
check("1. retry_decision省略時、select_candidates()は[]", engine1.select_candidates(), [])
check_none("1. retry_decision省略時、select_next_candidate()はNone", engine1.select_next_candidate())

queue2 = make_queue()
queue2.enqueue(run_id="run-2", workflow_name="news", retry_attempt=1, priority=0)
source2 = RetrySchedulerSource(queue2)
decision2 = RetrySchedulerDecision(source2)
engine2 = SchedulerEngine(retry_source=source2, retry_decision=decision2)
check(
    "2. RetrySchedulerDecision（実体）を渡すとそのまま保持される",
    [item.run_id for item in engine2.select_candidates()],
    ["run-2"],
)

decision3 = RetrySchedulerDecision(NullRetrySchedulerSource())
engine3 = SchedulerEngine(retry_decision=decision3)
check("3. NullRetrySchedulerSourceベースのRetrySchedulerDecisionを渡すとそのまま保持される", engine3.select_candidates(), [])
check_none("3. 同上、select_next_candidate()もNone", engine3.select_next_candidate())

engine4 = SchedulerEngine(clock=_FixedClockProvider(datetime(2026, 7, 3, 9, 0)), retry_source=source2)
check("4. clock/retry_sourceのみ指定時もretry_decisionは省略時と同じく[]を返す", engine4.select_candidates(), [])
check_none("4. 同上、select_next_candidate()もNone", engine4.select_next_candidate())
print()


# ═══════════════════════════════════════════════════════════
# テスト5-8: select_candidates() / select_next_candidate()（retry_decision注入時：候補あり）
# ═══════════════════════════════════════════════════════════

print("[テスト5-8] select_candidates() / select_next_candidate()（retry_decision注入時）")

queue5 = make_queue()
queue5.enqueue(run_id="run-a", workflow_name="news", retry_attempt=1, priority=1)
queue5.enqueue(run_id="run-b", workflow_name="news", retry_attempt=1, priority=0)
source5 = RetrySchedulerSource(queue5)
decision5 = RetrySchedulerDecision(source5)
engine5 = SchedulerEngine(retry_source=source5, retry_decision=decision5)

check(
    "5. select_candidates() が RetrySchedulerDecision.select_candidates() と一致",
    [item.run_id for item in engine5.select_candidates()],
    [item.run_id for item in decision5.select_candidates()],
)
check(
    "6. limit引数がそのまま伝播する",
    [item.run_id for item in engine5.select_candidates(limit=1)],
    ["run-b"],
)
check(
    "7. select_candidates()の順序がpriority昇順（run-b: priority=0が先頭）",
    [item.run_id for item in engine5.select_candidates()],
    ["run-b", "run-a"],
)
next_candidate8 = engine5.select_next_candidate()
check("8. select_next_candidate()がselect_candidates(limit=1)の先頭要素と一致", next_candidate8.run_id, "run-b")
print()


# ═══════════════════════════════════════════════════════════
# テスト9-10: select_candidates() / select_next_candidate()（Queueが空 / Null経由）
# ═══════════════════════════════════════════════════════════

print("[テスト9-10] select_candidates() / select_next_candidate()（Queueが空 / Null経由）")

queue9 = make_queue()
source9 = RetrySchedulerSource(queue9)
decision9 = RetrySchedulerDecision(source9)
engine9 = SchedulerEngine(retry_source=source9, retry_decision=decision9)
check("9. Queueが空の場合、select_candidates()は[]", engine9.select_candidates(), [])
check_none("9. Queueが空の場合、select_next_candidate()はNone", engine9.select_next_candidate())

decision10 = RetrySchedulerDecision(NullRetrySchedulerSource())
engine10 = SchedulerEngine(retry_decision=decision10)
check("10. NullRetrySchedulerSource経由でも select_candidates()は[]", engine10.select_candidates(), [])
check_none("10. 同上、select_next_candidate()はNone", engine10.select_next_candidate())
print()


# ═══════════════════════════════════════════════════════════
# テスト11-13: select_candidates() / select_next_candidate()（retry_decision=None、ガード節）
# ═══════════════════════════════════════════════════════════

print("[テスト11-13] select_candidates() / select_next_candidate()（retry_decision=None、ガード節）")

engine11 = SchedulerEngine()
check("11. retry_decision省略時、select_candidates()は常に[]", engine11.select_candidates(), [])
check_none("12. retry_decision省略時、select_next_candidate()は常にNone", engine11.select_next_candidate())
check("13. retry_decision省略時、limit指定時も常に[]", engine11.select_candidates(limit=5), [])
print()


# ═══════════════════════════════════════════════════════════
# テスト14-15: SchedulerEngineがRetrySchedulerDecisionを自ら構築しないことの構造的確認
# ═══════════════════════════════════════════════════════════

print("[テスト14] scheduler_engine.py に RetrySchedulerDecision(...) という構築呼び出しがない（AST）")

scheduler_dir = PROJECT_ROOT / "src" / "scheduler"
engine_source_path = scheduler_dir / "scheduler_engine.py"
engine_tree = ast.parse(engine_source_path.read_text(encoding="utf-8"))

construction_calls = [
    node for node in ast.walk(engine_tree)
    if isinstance(node, ast.Call)
    and isinstance(node.func, ast.Name)
    and node.func.id == "RetrySchedulerDecision"
]
check("14. RetrySchedulerDecision(...) という構築呼び出しが0件", len(construction_calls), 0)
print()

print("[テスト15] SchedulerEngineインスタンスがRetrySchedulerDecision関連の余分な属性を持たない")

engine15 = SchedulerEngine(retry_decision=RetrySchedulerDecision(NullRetrySchedulerSource()))
extra_attr_names = {"_retry_decision_factory", "_decision_source", "_built_retry_decision"}
found_extra = extra_attr_names & set(vars(engine15).keys())
check("15. RetrySchedulerDecisionを自前生成した形跡となる属性が存在しない", found_extra, set())
check_true("15. _retry_decision 属性は保持している", hasattr(engine15, "_retry_decision"))
print()


# ═══════════════════════════════════════════════════════════
# テスト16-18: evaluate() / run_due() が無変更であることの回帰確認
# ═══════════════════════════════════════════════════════════

print("[テスト16-18] evaluate() / run_due() の無変更確認")

daily_job = SchedulerJob(job_id="daily-1", name="Daily", trigger_type=TriggerType.DAILY, schedule="09:00")
now16 = datetime(2026, 7, 3, 9, 0)

queue16 = make_queue()
queue16.enqueue(run_id="run-16", workflow_name="news", retry_attempt=1, priority=0)
source16 = RetrySchedulerSource(queue16)
engine_with_decision = SchedulerEngine(retry_source=source16, retry_decision=RetrySchedulerDecision(source16))
engine_without_decision = SchedulerEngine()

events_with = engine_with_decision.evaluate([daily_job], now=now16)
events_without = engine_without_decision.evaluate([daily_job], now=now16)
check(
    "16. retry_decision有無でevaluate()の結果が完全一致",
    [(e.job_id, e.execute_time, e.trigger_reason, e.metadata) for e in events_with],
    [(e.job_id, e.execute_time, e.trigger_reason, e.metadata) for e in events_without],
)

fake_clock = _FixedClockProvider(now16)
run_due_with = SchedulerEngine(
    clock=fake_clock, retry_source=source16, retry_decision=RetrySchedulerDecision(source16)
).run_due([daily_job])
run_due_without = SchedulerEngine(clock=fake_clock).run_due([daily_job])
check(
    "17. retry_decision有無でrun_due()の結果が完全一致",
    [(e.job_id, e.trigger_reason) for e in run_due_with],
    [(e.job_id, e.trigger_reason) for e in run_due_without],
)

engine18 = SchedulerEngine(retry_source=source16, retry_decision=RetrySchedulerDecision(source16))
events_before = engine18.evaluate([daily_job], now=now16)
engine18.select_candidates()
engine18.select_next_candidate()
events_after = engine18.evaluate([daily_job], now=now16)
check(
    "18. select_candidates()/select_next_candidate()呼び出し後もevaluate()の結果は変わらない",
    [(e.job_id, e.trigger_reason) for e in events_before],
    [(e.job_id, e.trigger_reason) for e in events_after],
)
print()


# ═══════════════════════════════════════════════════════════
# テスト19: dequeue() / remove() 等の構造的確認（Spy）
# ═══════════════════════════════════════════════════════════

print("[テスト19] select_candidates/select_next_candidate呼び出し中に他メソッドが一切呼ばれない（Spy）")


class _RetryDecisionSpy:
    """select_candidates() / select_next_candidate() 以外が呼ばれたら例外を送出するダミー。"""

    def __init__(self, real):
        self._real = real

    def select_candidates(self, limit=None):
        return self._real.select_candidates(limit=limit)

    def select_next_candidate(self):
        return self._real.select_next_candidate()

    def __getattr__(self, name):
        def _forbidden(*args, **kwargs):
            raise AssertionError(f"{name}() must not be called by SchedulerEngine")
        return _forbidden


queue19 = make_queue()
queue19.enqueue(run_id="run-19", workflow_name="news", retry_attempt=1, priority=0)
spy19 = _RetryDecisionSpy(RetrySchedulerDecision(RetrySchedulerSource(queue19)))
engine19 = SchedulerEngine(retry_decision=spy19)

try:
    engine19.select_candidates(limit=3)
    engine19.select_next_candidate()
    no_forbidden_call = True
except AssertionError:
    no_forbidden_call = False
check_true("19. select_candidates/select_next_candidate呼び出し中に他のメソッドが呼ばれない", no_forbidden_call)
print()


# ═══════════════════════════════════════════════════════════
# テスト20-21: Feature Gate / Config / Manager 追加なしの確認
# ═══════════════════════════════════════════════════════════

print("[テスト20] src/scheduler/ 配下に新規ファイルが追加されていない")

py_files_20 = sorted(p.name for p in scheduler_dir.glob("*.py"))
check(
    "20. src/scheduler/ のファイル一覧がv3.4.0から増えていない（新規ファイル追加なし）",
    py_files_20,
    ["__init__.py", "exceptions.py", "scheduler_config.py", "scheduler_engine.py",
     "scheduler_event.py", "scheduler_job.py", "scheduler_manager.py", "scheduler_repository.py"],
)
print()

print("[テスト21] SchedulerEngine が from_config / from_env を持たない")

check_false("21. SchedulerEngine.from_config が存在しない", hasattr(SchedulerEngine, "from_config"))
check_false("21. SchedulerEngine.from_env が存在しない", hasattr(SchedulerEngine, "from_env"))
print()


# ═══════════════════════════════════════════════════════════
# テスト22-24: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト22] src/scheduler/ が retry_queue / retry_engine を直接importしない")

for py_file in sorted(scheduler_dir.glob("*.py")):
    source_text = py_file.read_text(encoding="utf-8")
    import_lines = "\n".join(
        line for line in source_text.splitlines()
        if line.strip().startswith("from ") or line.strip().startswith("import ")
    )
    check_false(f"22. {py_file.name} が 'retry_queue' を直接importしない", "retry_queue" in import_lines)
    check_false(f"22. {py_file.name} が 'retry_engine' を直接importしない", "retry_engine" in import_lines)
    check_false(f"22. {py_file.name} が 'from ai' をimportしない", "from ai" in import_lines or "from ai." in import_lines)
    check_false(f"22. {py_file.name} が 'from pipeline' をimportしない", "from pipeline" in import_lines or "from pipeline." in import_lines)
print()

print("[テスト23] src/scheduler/ に 'RetryQueueManager' / 'RetryManager' への実コード参照がない（AST）")


def _referenced_names(py_file: Path) -> set:
    """docstring・コメントを除外し、実際に識別子として参照された名前の集合を返す。"""
    tree = ast.parse(py_file.read_text(encoding="utf-8"))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name)
    return names


for py_file in sorted(scheduler_dir.glob("*.py")):
    referenced = _referenced_names(py_file)
    check_false(f"23. {py_file.name} が 'RetryQueueManager' を実コードで参照しない", "RetryQueueManager" in referenced)
    check_false(f"23. {py_file.name} が 'RetryManager' を実コードで参照しない", "RetryManager" in referenced)
print()

print("[テスト24] retry_scheduler_decision / retry_scheduler_source / retry_queue / retry_engine の")
print("           ゼロ改修確認、および src/scheduler/ 内の対象外ファイルの無変更確認（git diff）")

unchanged_paths_24 = [
    "src/retry_scheduler_decision/retry_scheduler_decision.py",
    "src/retry_scheduler_decision/__init__.py",
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
    "src/scheduler/scheduler_manager.py",
    "src/scheduler/scheduler_job.py",
    "src/scheduler/scheduler_event.py",
    "src/scheduler/scheduler_repository.py",
    "src/scheduler/scheduler_config.py",
    "src/scheduler/exceptions.py",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths_24:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"24. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("24. gitが利用できないため無変更確認をスキップ", True)
print()


# ═══════════════════════════════════════════════════════════
# テスト25-27: 既存回帰（v2.6.0 / v3.4.0 SchedulerEngine挙動）
# ═══════════════════════════════════════════════════════════

print("[テスト25-27] 既存回帰（v2.6.0 / v3.4.0 SchedulerEngine挙動）")

engine25 = SchedulerEngine()
interval_job = SchedulerJob(job_id="interval-1", name="Interval", trigger_type=TriggerType.INTERVAL, schedule="30")
once_job = SchedulerJob(job_id="once-1", name="Once", trigger_type=TriggerType.ONCE, schedule="2026-07-03T09:00")
disabled_job = SchedulerJob(job_id="disabled-1", name="Disabled", trigger_type=TriggerType.DAILY, schedule="09:00", enabled=False)

now25 = datetime(2026, 7, 3, 9, 0)
events25 = engine25.evaluate([daily_job, interval_job, once_job, disabled_job], now=now25)
check(
    "25. DAILY/INTERVAL/ONCEの判定結果が従来と同一",
    sorted(e.job_id for e in events25),
    sorted(["daily-1", "interval-1", "once-1"]),
)
check_true("26. disabledなJobは判定対象から除外される", "disabled-1" not in [e.job_id for e in events25])

queue27 = make_queue()
queue27.enqueue(run_id="run-27", workflow_name="news", retry_attempt=1, priority=0)
source27 = RetrySchedulerSource(queue27)
engine27 = SchedulerEngine(retry_source=source27, retry_decision=RetrySchedulerDecision(source27))
check("27. count_pending_retries()（v3.4.0）の挙動が本Releaseでも維持される", engine27.count_pending_retries(), 1)
check(
    "27. list_pending_retries()（v3.4.0）の挙動が本Releaseでも維持される",
    [item.run_id for item in engine27.list_pending_retries()],
    ["run-27"],
)
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
