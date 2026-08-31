"""
E2E テスト: v6.31.0 Retry Lineage, Eligibility & Durable Attempt State

テストシナリオ（docs/design/retry_lineage_eligibility_durable_attempt_state.md 対応。
Round 11 + Cleanup版、Architecture Gate承認済み2026-08-31）:

    ── ロック（9.2・9.3章） ──
    1.  RetryLineageStoreLockは取得中に別ロックがacquire()を試みるとタイムアウトで
        RetryLineageStoreLockErrorを送出する
    2.  RetryLineageStoreLockはwith文でacquire/releaseが自動的に行われる
    3.  RetryExecutionLockは取得中に別ロックがacquire()を試みると即座に
        RetryExecutionLockBusyErrorを送出する（リトライなし）
    4.  RetryExecutionLock保持中はRetryLineageManager.reconcile_all()がskipped=Trueを
        返し、mutationを一切行わない（9.3.3章）

    ── JsonRetryLineageStore（6章） ──
    5.  save()→get()のラウンドトリップで全フィールドが復元される
    6.  存在しないroot_run_idに対するget()はNoneを返す
    7.  list_all()が保存済みの全レコードを返す

    ── classify_step_outcome / classify_execution_history_step（11.3・11.7章） ──
    8.  action_taken=True → GENUINE_SUCCESS、False → SILENT_NO_ACTION、
        None/非bool → UNKNOWN（closed-set fail-closed）
    9.  skip_category=GATE_CLOSED → INTENTIONAL_NO_ACTION、
        NOT_REACHED/HISTORY_WRITE_FAILED/HOOK_NOT_ACKNOWLEDGED/HOOK_EXCEPTION/
        NOT_TARGETED → NOT_APPLICABLE、None/未知値 → UNKNOWN
    10. classify_step_outcome()とclassify_execution_history_step()が対称
        （同一の閉集合判定）

    ── compute_*ヘルパー（7.2.2・7.3・11.4.3章） ──
    11. compute_steps_to_execute()は常にcanonical order（NEWS→REVIEW→PUBLISH）で返す
    12. compute_initial_confirmed_steps()はGENUINE_SUCCESSのstepのみ抽出する
        （NOT_REACHED/SILENT_NO_ACTION/legacy action_taken=Noneはいずれも除外＝再実行対象に残る）
    13. _canonicalize_step_order()はcanonical orderへ正規化する（順序破損の修復）
    14. decide_disposition()：UNKNOWN→FAILED、RETRYABLE_FAILURE→FAILED、
        SILENT_NO_ACTION→NOT_ACTIONED、それ以外→SUCCEEDED

    ── RetryLineageManager: find_existing_lineage() / create_new_lineage()（7章） ──
    15. find_existing_lineage()：分岐(1)直接一致
    16. find_existing_lineage()：分岐(2)membership一致（single-hop）
    17. find_existing_lineage()：分岐(2)multi-hop（A→B→C）
    18. find_existing_lineage()：該当なしはNone
    19. find_existing_lineage()はself._store.save()を一度も呼ばない（read-only確認）
    20. create_new_lineage()：max_attempts不正値（負値・文字列・bool・None）は
        should_retry()を呼ばずvalidation-rejectionでfail-closed（MAJ-R10-1対応）
    21. create_new_lineage()：max_attempts=1・非対象statusはpolicy-rejection
        （should_retry()呼び出し回数1、reason文言がvalidation-rejectionと異なる）
    22. create_new_lineage()：attempt 1のsteps_confirmed_doneがmonitor_record.stepsの
        GENUINE_SUCCESS stepのみから導出される（NEWS/REVIEW confirmed、PUBLISH未確定）
    23. create_new_lineage()：attempt_scopes[0].steps_to_executeがcanonical orderで保存される

    ── RetryLineageManager: claim() / release_claim()（8・11.4.5.2(a)章） ──
    24. claim()：READY_ELIGIBLEをCLAIMEDへ遷移させ、attempt_no/correlation_id/
        steps_to_executeを返す
    25. claim()：phase不一致はack=False
    26. claim()：保存済みscopeと再計算値が不一致ならinvariant violationでfail-closed
    27. release_claim()：CLAIMEDをREADY_ELIGIBLEへ戻す

    ── RetryLineageManager: mark_execution_started() / mark_terminal()（9.5・12章） ──
    28. mark_execution_started()：attempt_countを+1し、membershipへ追加する
    29. mark_terminal()：steps_confirmed_doneをunionし、attempt_scopesへは書き込まない
    30. mark_terminal()：dispositionを問わずattempt_countを一切変更しない（payback廃止）

    ── RetryLineageManager: open_next_attempt()（9.8.1・12章） ──
    31. open_next_attempt()：attempt_count<max_attemptsならREADY_ELIGIBLE へ再オープンする
    32. open_next_attempt()：attempt_count>=max_attemptsはack=False（"max_attempts exhausted"）
    33. open_next_attempt()：terminal_disposition=SUCCEEDEDはack=False（そもそも呼ばれない想定の防御）
    34. open_next_attempt()：steps_confirmed_doneが全stepを覆う場合はinvariant violationでfail-closed
    35. open_next_attempt()：next_attempt_ordinalが単調増加する

    ── 統合：RetryManager._retry_locked()（9.3.2・9.8.1.2章） ──
    36. 新規lineage作成時のみMonitor/RetryPolicyが呼ばれる
    37. 既存lineage再接続でMonitor.get_status() call count = 0（MAJ-R9-1直接検証）
    38. attempt 1 → NOT_ACTIONED（budget消費） → attempt 2 → SUCCEEDED
        （11.6章NEWS→PUBLISH driftトレース）
    39. RetryExecutionLock busy時はSKIPPEDを返す

    ── 統合：workflow_engine（10.2・11.4章） ──
    40. target_step_filterで対象外stepがskip_category=NOT_TARGETEDでスキップされる
    41. post_admission_hookがack=Falseの場合、全stepがNOT_REACHEDへ終端しhook例外は
        Execution History終端後に再raiseされる
    42. WorkflowEngineResult.run_idが実際の実行run_idと一致する

    ── RetryLineageManager.verify_orphan_correlation()（10.3.3章(b)） ──
    43. root_run_id実在・intended_attempt_no一致・correlation_id一致の3条件すべて
        満たす場合のみTrue
    44. forged（存在しないroot_run_id）はFalse
    45. stale（古いintended_attempt_no）はFalse
    46. correlation_id不一致はFalse
    47. intended_attempt_noがパース不可（非数値文字列）はFalse

    ── 統合：RetryEnqueueTrigger correlation-fallback（10.3.3・10.3.4章） ──
    48. membership-firstが優先される（membershipで見つかった場合、
        history_store.get()は呼ばれない）
    49. correlation-fallback：a/b/c全条件一致で独立候補から除外される
        （skipped_lineage_correlation計上）
    50. malformed correlation_metadata（namespace欠落・型不正）はfail-closedで
        通常の独立候補として処理される（誤って除外しない）
    51. forged root_run_id・stale attempt_no・correlation_id不一致のいずれも
        fail-closedで通常の独立候補として処理される
    52. correlation_metadataを一切持たない無関係なFAILED候補は誤って除外されない

    ── Architecture Amendment（Code Review Findings対応、10.2.4・7.2・12・16章(c)） ──
    59. hook未ack（HOOK_NOT_ACKNOWLEDGED）はSUCCEEDED/COMPLETEに到達しない
        （RetryExecutor.execute()はmark_terminal()を呼ばずclaimを解放しSKIPPEDを返し、
        RetryQueueUpdateDeciderはNOOPと判定する）。hook成功後・hook自体の例外送出時の
        再raise/claim解放契約も確認する
    60. mark_terminal()のack=FalseはRetryOutcome.SKIPPEDへ正しく伝播する
    61. reconcile_all()がphase==CLAIMEDのorphanをrelease_claim()で回収する
        （16章(c)、attempt_countは変化しない）
    62. create_new_lineage()：グローバルmembership一意性チェック
        （root_run_id衝突・membership run_id衝突のいずれも新規lineageを作成しない）
    63. claim()・open_next_attempt()：next_attempt_ordinal不一致はinvariant violationで
        fail-closed（ack=False、自動修復しない）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_31_0_retry_lineage_eligibility_durable_attempt_state.py
"""
import shutil
import sys
import tempfile
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

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
print("v6.31.0 Retry Lineage, Eligibility & Durable Attempt State E2E テスト")
print("=" * 60)
print()

from execution_history import (
    JsonExecutionHistoryStore,
    StepExecutionRecord,
    StepExecutionStatus,
    StepSkipCategory,
    WorkflowExecutionRecord,
    WorkflowExecutionStatus,
)
from retry_enqueue_trigger import RetryEnqueueTrigger
from workflow_engine import (
    ALL_WORKFLOW_ENGINE_STEPS,
    WorkflowEngineContext,
    WorkflowEngineEvent,
    WorkflowEngineExecutor,
    WorkflowEngineResult,
    WorkflowEngineStep,
    WorkflowEngineStepResult,
    SOURCE_MANUAL,
)
from workflow_engine.workflow_engine_post_admission_hook import PostAdmissionHookResult
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus
from retry_lineage import (
    ClaimResult,
    JsonRetryLineageStore,
    RetryExecutionLock,
    RetryExecutionLockBusyError,
    RetryLineageConfig,
    RetryLineageDisposition,
    RetryLineageManager,
    RetryLineagePhase,
    RetryLineageRecord,
    RetryLineageStoreLock,
    RetryLineageStoreLockError,
    StepOutcomeCategory,
    classify_execution_history_step,
    classify_step_outcome,
    compute_initial_confirmed_steps,
    compute_newly_confirmed,
    compute_steps_to_execute,
    decide_disposition,
)
from retry_lineage import MarkTerminalResult
from retry_lineage.retry_lineage_target_resolution import _canonicalize_step_order
from retry_engine import (
    RetryExecutionResult,
    RetryManager,
    RetryOutcome,
    RetryQueueUpdateDecider,
    RetryQueueUpdateOutcome,
    RetryRequest,
)
from retry_engine.retry_executor import RetryExecutor


# ─── テスト用ユーティリティ ───

tmp_dirs: list[Path] = []


def make_lineage_manager(policy=None) -> tuple[RetryLineageManager, Path]:
    tmp_root = Path(tempfile.mkdtemp())
    tmp_dirs.append(tmp_root)
    config = RetryLineageConfig(enabled=True, lineage_dir=tmp_root)
    store = JsonRetryLineageStore(config.store_dir)
    return RetryLineageManager(store=store, config=config, policy=policy or FakePolicy()), tmp_root


class FakePolicy:
    def __init__(self, target_statuses=None, max_attempts: int = 3, retry_decision: bool | None = None):
        self.target_statuses = target_statuses if target_statuses is not None else frozenset(
            {WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT}
        )
        self._max_attempts = max_attempts
        self._retry_decision = retry_decision
        self.should_retry_calls: list[tuple] = []

    @property
    def max_attempts(self):
        return self._max_attempts

    def should_retry(self, monitor_status, attempt) -> bool:
        self.should_retry_calls.append((monitor_status, attempt))
        if self._retry_decision is not None:
            return self._retry_decision
        return monitor_status in self.target_statuses and attempt < self._max_attempts


def make_step(step: str, status: StepExecutionStatus, action_taken=None, skip_category=None) -> StepExecutionRecord:
    return StepExecutionRecord(
        step=step, status=status, started_at=None, finished_at=datetime.now(),
        action_taken=action_taken, skip_category=skip_category,
    )


def make_monitor_record(run_id: str, monitor_status: WorkflowMonitorStatus, steps=None) -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=monitor_status,
        source_status=monitor_status.value, source="manual", job_id="job-1",
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=steps or [],
    )


def make_step_result(step: WorkflowEngineStep, executed: bool, success: bool, action_taken=None,
                      skip_category=None, agent_result=None):
    ar = agent_result
    if executed and ar is None:
        ar = FakeAgentResult(success=success, action_taken=action_taken)
    return WorkflowEngineStepResult(
        step=step, executed=executed, agent_result=ar, success=success,
        skipped_reason=None if executed else "skipped", skip_category=skip_category,
    )


@dataclass
class FakeAgentResult:
    success: bool
    action_taken: bool | None
    error_message: str | None = None

    def to_dict(self):
        return {"success": self.success, "action_taken": self.action_taken}


def make_engine_result(steps: list[WorkflowEngineStepResult], run_id: str = "run-x") -> WorkflowEngineResult:
    now = datetime.now()
    return WorkflowEngineResult(
        run_id=run_id, steps=steps, overall_success=all(s.success for s in steps),
        stopped_early=False, started_at=now, finished_at=now,
    )


NEWS, REVIEW, PUBLISH = WorkflowEngineStep.NEWS, WorkflowEngineStep.REVIEW, WorkflowEngineStep.PUBLISH


# ═══════════════════════════════════════════════════════════
# テスト1-4: ロック
# ═══════════════════════════════════════════════════════════

print("[テスト1-4] RetryLineageStoreLock / RetryExecutionLock")

tmp_lock_dir = Path(tempfile.mkdtemp())
tmp_dirs.append(tmp_lock_dir)
store_lock_path = tmp_lock_dir / "store.lock"

lock_a = RetryLineageStoreLock(store_lock_path, timeout_seconds=0.3, retry_interval_seconds=0.02)
lock_a.acquire()
try:
    lock_b = RetryLineageStoreLock(store_lock_path, timeout_seconds=0.3, retry_interval_seconds=0.02)
    threw = False
    try:
        lock_b.acquire()
    except RetryLineageStoreLockError:
        threw = True
    check_true("1. RetryLineageStoreLock: 取得中の別acquire()はタイムアウトでエラー", threw)
finally:
    lock_a.release()

with RetryLineageStoreLock(store_lock_path, timeout_seconds=1.0) as lk:
    check_true("2. RetryLineageStoreLock: with文でロックファイルが作成される", store_lock_path.exists())
check_false("2. RetryLineageStoreLock: with文終了後にロックファイルが削除される", store_lock_path.exists())

exec_lock_path = tmp_lock_dir / "execution.lock"
exec_lock_a = RetryExecutionLock(exec_lock_path)
exec_lock_a.acquire()
try:
    exec_lock_b = RetryExecutionLock(exec_lock_path)
    threw2 = False
    try:
        exec_lock_b.acquire()
    except RetryExecutionLockBusyError:
        threw2 = True
    check_true("3. RetryExecutionLock: 取得中の別acquire()は即座にBusyError", threw2)

    lineage_for_busy, _ = make_lineage_manager()
    summary = lineage_for_busy.reconcile_all(resolve_status_fn=lambda run_id: None)
    # busyになるのはlineage_for_busy自身のexecution_lock_pathではないため、まず単体でBusyErrorの
    # 挙動そのものを別途確認する（4番）。
finally:
    exec_lock_a.release()

lineage_4, _ = make_lineage_manager()
with RetryExecutionLock(lineage_4.execution_lock_path):
    summary_4 = lineage_4.reconcile_all(resolve_status_fn=lambda run_id: None)
check_true("4. RetryExecutionLock保持中はreconcile_all()がskipped=Trueを返す", summary_4.skipped)
print()


# ═══════════════════════════════════════════════════════════
# テスト5-7: JsonRetryLineageStore
# ═══════════════════════════════════════════════════════════

print("[テスト5-7] JsonRetryLineageStore")

_, store_dir_root = make_lineage_manager()
store_5 = JsonRetryLineageStore(store_dir_root / "store5")
now5 = datetime.now()
record_5 = RetryLineageRecord(
    root_run_id="root-5", parent_run_id=None, latest_run_id="root-5",
    attempt_count=1, max_attempts=3, next_attempt_ordinal=2,
    phase=RetryLineagePhase.TERMINAL, terminal_disposition=RetryLineageDisposition.FAILED,
    next_eligible_at=None, owner_token=None, steps_confirmed_done=["news"],
    created_at=now5, updated_at=now5,
)
check_true("5. save()が成功する", store_5.save(record_5))
loaded_5 = store_5.get("root-5")
check_true("5. get()がNoneでない", loaded_5 is not None)
check("5. ラウンドトリップ: attempt_count", loaded_5.attempt_count, 1)
check("5. ラウンドトリップ: max_attempts", loaded_5.max_attempts, 3)
check("5. ラウンドトリップ: phase", loaded_5.phase, RetryLineagePhase.TERMINAL)
check("5. ラウンドトリップ: terminal_disposition", loaded_5.terminal_disposition, RetryLineageDisposition.FAILED)
check("5. ラウンドトリップ: steps_confirmed_done", loaded_5.steps_confirmed_done, ["news"])

check_true("6. 存在しないroot_run_idはNone", store_5.get("does-not-exist") is None)

store_5.save(RetryLineageRecord(
    root_run_id="root-5b", parent_run_id=None, latest_run_id="root-5b",
    attempt_count=0, max_attempts=3, next_attempt_ordinal=1,
    phase=RetryLineagePhase.READY_ELIGIBLE, terminal_disposition=None,
    next_eligible_at=None, owner_token=None, steps_confirmed_done=[],
    created_at=now5, updated_at=now5,
))
all_records = store_5.list_all()
check("7. list_all()が2件返す", len(all_records), 2)
print()


# ═══════════════════════════════════════════════════════════
# テスト8-10: classify_step_outcome / classify_execution_history_step
# ═══════════════════════════════════════════════════════════

print("[テスト8-10] classify_step_outcome() / classify_execution_history_step()")

sr_true = make_step_result(NEWS, executed=True, success=True, action_taken=True)
check("8. action_taken=True → GENUINE_SUCCESS", classify_step_outcome(sr_true), StepOutcomeCategory.GENUINE_SUCCESS)

sr_false = make_step_result(NEWS, executed=True, success=True, action_taken=False)
check("8. action_taken=False → SILENT_NO_ACTION", classify_step_outcome(sr_false), StepOutcomeCategory.SILENT_NO_ACTION)

sr_none = WorkflowEngineStepResult(
    step=NEWS, executed=True, agent_result=FakeAgentResult(success=True, action_taken=None),
    success=True, skipped_reason=None,
)
check("8. action_taken=None(executed=True) → UNKNOWN", classify_step_outcome(sr_none), StepOutcomeCategory.UNKNOWN)

step_true = make_step("news", StepExecutionStatus.SUCCESS, action_taken=True)
check("8. StepExecutionRecord action_taken=True → GENUINE_SUCCESS", classify_execution_history_step(step_true), StepOutcomeCategory.GENUINE_SUCCESS)
step_legacy = make_step("news", StepExecutionStatus.SUCCESS, action_taken=None)
check("8. legacy record (action_taken=None) → UNKNOWN", classify_execution_history_step(step_legacy), StepOutcomeCategory.UNKNOWN)

sr_gate = make_step_result(REVIEW, executed=False, success=True, skip_category=StepSkipCategory.GATE_CLOSED)
check("9. GATE_CLOSED → INTENTIONAL_NO_ACTION", classify_step_outcome(sr_gate), StepOutcomeCategory.INTENTIONAL_NO_ACTION)

for cat in (StepSkipCategory.NOT_REACHED, StepSkipCategory.HISTORY_WRITE_FAILED,
            StepSkipCategory.HOOK_NOT_ACKNOWLEDGED, StepSkipCategory.HOOK_EXCEPTION,
            StepSkipCategory.NOT_TARGETED):
    sr = make_step_result(REVIEW, executed=False, success=False, skip_category=cat)
    check(f"9. {cat.value} → NOT_APPLICABLE", classify_step_outcome(sr), StepOutcomeCategory.NOT_APPLICABLE)

sr_unset = make_step_result(REVIEW, executed=False, success=False, skip_category=None)
check("9. skip_category未設定 → UNKNOWN", classify_step_outcome(sr_unset), StepOutcomeCategory.UNKNOWN)

step_gate = make_step("review", StepExecutionStatus.SKIPPED, skip_category=StepSkipCategory.GATE_CLOSED)
check("10. sync/reconcile対称: GATE_CLOSED", classify_execution_history_step(step_gate), StepOutcomeCategory.INTENTIONAL_NO_ACTION)
step_unset = make_step("review", StepExecutionStatus.SKIPPED, skip_category=None)
check("10. sync/reconcile対称: skip_category未設定 → UNKNOWN", classify_execution_history_step(step_unset), StepOutcomeCategory.UNKNOWN)
print()


# ═══════════════════════════════════════════════════════════
# テスト11-14: compute_*ヘルパー
# ═══════════════════════════════════════════════════════════

print("[テスト11-14] compute_steps_to_execute() / compute_initial_confirmed_steps() / _canonicalize_step_order() / decide_disposition()")

check("11. compute_steps_to_execute([]) はcanonical order全体", compute_steps_to_execute([]), ["news", "review", "publish"])
check("11. compute_steps_to_execute(['news','review'])", compute_steps_to_execute(["news", "review"]), ["publish"])

steps_12 = [
    make_step("news", StepExecutionStatus.SUCCESS, action_taken=True),
    make_step("review", StepExecutionStatus.SUCCESS, action_taken=False),  # SILENT_NO_ACTION
    make_step("publish", StepExecutionStatus.NOT_REACHED),
]
check("12. compute_initial_confirmed_steps: GENUINE_SUCCESSのみ抽出", compute_initial_confirmed_steps(steps_12), ["news"])

steps_12b = [make_step("publish", StepExecutionStatus.SUCCESS, action_taken=None)]  # legacy
check("12. legacy action_taken=Noneは初期confirmedに含まれない", compute_initial_confirmed_steps(steps_12b), [])

check("13. _canonicalize_step_order: 順序破損の修復", _canonicalize_step_order(["publish", "news", "review"]), ["news", "review", "publish"])
check("13. _canonicalize_step_order: 既にcanonicalなら不変", _canonicalize_step_order(["news", "review", "publish"]), ["news", "review", "publish"])

engine_unknown = make_engine_result([sr_none, make_step_result(REVIEW, executed=True, success=True, action_taken=True)])
check("14. UNKNOWNを含む → FAILED", decide_disposition(engine_unknown), RetryLineageDisposition.FAILED)

engine_failure = make_engine_result([make_step_result(NEWS, executed=True, success=False)])
check("14. RETRYABLE_FAILUREを含む → FAILED", decide_disposition(engine_failure), RetryLineageDisposition.FAILED)

engine_silent = make_engine_result([
    make_step_result(NEWS, executed=True, success=True, action_taken=True),
    make_step_result(PUBLISH, executed=True, success=True, action_taken=False),
])
check("14. SILENT_NO_ACTIONを含む(UNKNOWN/FAILUREなし) → NOT_ACTIONED", decide_disposition(engine_silent), RetryLineageDisposition.NOT_ACTIONED)

engine_success = make_engine_result([
    make_step_result(NEWS, executed=True, success=True, action_taken=True),
    make_step_result(REVIEW, executed=False, success=True, skip_category=StepSkipCategory.NOT_TARGETED),
])
check("14. 全executedがGENUINE_SUCCESS → SUCCEEDED", decide_disposition(engine_success), RetryLineageDisposition.SUCCEEDED)
print()


# ═══════════════════════════════════════════════════════════
# テスト15-19: find_existing_lineage()
# ═══════════════════════════════════════════════════════════

print("[テスト15-19] find_existing_lineage()：分岐(1)(2)、read-only確認")

policy_15 = FakePolicy(max_attempts=3)
lineage_15, _ = make_lineage_manager(policy_15)
monitor_record_15 = make_monitor_record("root-15", WorkflowMonitorStatus.FAILED, steps=[
    make_step("news", StepExecutionStatus.SUCCESS, action_taken=True),
    make_step("review", StepExecutionStatus.NOT_REACHED),
    make_step("publish", StepExecutionStatus.NOT_REACHED),
])
created_15 = lineage_15.create_new_lineage("root-15", monitor_record_15)
check_true("15前提: create_new_lineage()成功", created_15.lineage is not None)

found_direct = lineage_15.find_existing_lineage("root-15")
check_true("15. 分岐(1): root_run_id直接一致でヒットする", found_direct is not None)
check("15. 分岐(1): max_attemptsが保持される", found_direct.max_attempts, 3)

# claim → mark_execution_startedで攻撃対象のattempt run_idをmembershipへ登録する
claim_15 = lineage_15.claim("root-15")
lineage_15.mark_execution_started("root-15", "member-run-16")
found_member = lineage_15.find_existing_lineage("member-run-16")
check_true("16. 分岐(2): membership（single-hop）でヒットする", found_member is not None)
check("16. 分岐(2): root_run_idが正しい", found_member.root_run_id if found_member else None, "root-15")

# multi-hop: 別のlineageのmembershipに "member-run-16" を模した孫run_idを追加する体裁で確認
lineage_15.mark_terminal("root-15", RetryLineageDisposition.FAILED, "member-run-16", [])
opened = lineage_15.open_next_attempt("root-15")
claim_17 = lineage_15.claim("root-15")
lineage_15.mark_execution_started("root-15", "grandchild-run-17")
found_multi_hop = lineage_15.find_existing_lineage("grandchild-run-17")
check_true("17. 分岐(2): multi-hop（A→B→C）でもヒットする", found_multi_hop is not None)
check("17. multi-hop: root_run_idが正しい", found_multi_hop.root_run_id if found_multi_hop else None, "root-15")

check_true("18. 該当なしの場合はNone", lineage_15.find_existing_lineage("totally-unknown-run") is None)

save_calls_before = len(list(lineage_15._store.list_all()))
_ = lineage_15.find_existing_lineage("root-15")
_ = lineage_15.find_existing_lineage("member-run-16")
save_calls_after = len(list(lineage_15._store.list_all()))
check("19. find_existing_lineage()はレコード件数を変化させない（save()を呼ばない）", save_calls_after, save_calls_before)
print()


# ═══════════════════════════════════════════════════════════
# テスト20-23: create_new_lineage()
# ═══════════════════════════════════════════════════════════

print("[テスト20-23] create_new_lineage()：validation順序・attempt 1 scope導出")

for bad_value in (-1, "3", True, None):
    policy_20 = FakePolicy(max_attempts=bad_value)
    lineage_20, _ = make_lineage_manager(policy_20)
    result_20 = lineage_20.create_new_lineage("run-20", make_monitor_record("run-20", WorkflowMonitorStatus.FAILED))
    check_true(f"20. max_attempts={bad_value!r}: admission_rejected=True", result_20.admission_rejected)
    check("20. max_attempts不正値: should_retry()は呼ばれない（call count=0）", len(policy_20.should_retry_calls), 0)

policy_21 = FakePolicy(target_statuses=frozenset({WorkflowMonitorStatus.TIMEOUT}), max_attempts=1)
lineage_21, _ = make_lineage_manager(policy_21)
result_21 = lineage_21.create_new_lineage("run-21", make_monitor_record("run-21", WorkflowMonitorStatus.SUCCESS))
check_true("21. policy-rejection: admission_rejected=True", result_21.admission_rejected)
check("21. policy-rejection: should_retry()が1回呼ばれる", len(policy_21.should_retry_calls), 1)
check_true("21. reasonがvalidation文言と異なる（is not a retry target）", "is not a retry target" in (result_21.reason or ""))

policy_22 = FakePolicy(max_attempts=3)
lineage_22, _ = make_lineage_manager(policy_22)
monitor_22 = make_monitor_record("run-22", WorkflowMonitorStatus.FAILED, steps=[
    make_step("news", StepExecutionStatus.SUCCESS, action_taken=True),
    make_step("review", StepExecutionStatus.SUCCESS, action_taken=True),
    make_step("publish", StepExecutionStatus.FAILED),
])
result_22 = lineage_22.create_new_lineage("run-22", monitor_22)
check_true("22. attempt 1: create成功", result_22.lineage is not None)
check("22. steps_confirmed_doneはNEWS/REVIEWのみ", sorted(result_22.lineage.steps_confirmed_done), ["news", "review"])
check("23. attempt_scopes[0].steps_to_executeはPUBLISHのみ", result_22.lineage.attempt_scopes[0].steps_to_execute, ["publish"])

policy_23b = FakePolicy(max_attempts=3)
lineage_23b, _ = make_lineage_manager(policy_23b)
monitor_23b = make_monitor_record("run-23b", WorkflowMonitorStatus.FAILED, steps=[
    make_step("publish", StepExecutionStatus.SUCCESS, action_taken=True),
    make_step("news", StepExecutionStatus.SUCCESS, action_taken=True),
])
result_23b = lineage_23b.create_new_lineage("run-23b", monitor_23b)
check("23. steps_to_executeはcanonical order（REVIEWのみ残存）", result_23b.lineage.attempt_scopes[0].steps_to_execute, ["review"])
print()


# ═══════════════════════════════════════════════════════════
# テスト24-27: claim() / release_claim()
# ═══════════════════════════════════════════════════════════

print("[テスト24-27] claim() / release_claim()")

policy_24 = FakePolicy(max_attempts=3)
lineage_24, _ = make_lineage_manager(policy_24)
monitor_24 = make_monitor_record("run-24", WorkflowMonitorStatus.FAILED)
created_24 = lineage_24.create_new_lineage("run-24", monitor_24)
claim_24 = lineage_24.claim("run-24")
check_true("24. claim()成功", claim_24.acknowledged)
check("24. attempt_no=1", claim_24.attempt_no, 1)
check_true("24. correlation_idが発行される", claim_24.correlation_id is not None)
after_claim = lineage_24.peek("run-24")
check("24. phaseがCLAIMEDへ遷移", after_claim.phase, RetryLineagePhase.CLAIMED)

claim_25 = lineage_24.claim("run-24")  # 既にCLAIMED
check_false("25. phase不一致（既にCLAIMED）はack=False", claim_25.acknowledged)

policy_26 = FakePolicy(max_attempts=3)
lineage_26, _ = make_lineage_manager(policy_26)
monitor_26 = make_monitor_record("run-26", WorkflowMonitorStatus.FAILED)
created_26 = lineage_26.create_new_lineage("run-26", monitor_26)
corrupted = lineage_26._store.get("run-26")
corrupted.attempt_scopes[-1].steps_to_execute = ["publish"]  # 破損させる（本来は全step）
lineage_26._store.save(corrupted)
claim_26 = lineage_26.claim("run-26")
check_false("26. stored/recomputed scope不一致はack=False", claim_26.acknowledged)
check_true("26. reasonにinvariant_violationが含まれる", "invariant_violation" in (claim_26.reason or ""))

check_true("27. release_claim()成功", lineage_24.release_claim("run-24"))
after_release = lineage_24.peek("run-24")
check("27. phaseがREADY_ELIGIBLEへ戻る", after_release.phase, RetryLineagePhase.READY_ELIGIBLE)
print()


# ═══════════════════════════════════════════════════════════
# テスト28-30: mark_execution_started() / mark_terminal()
# ═══════════════════════════════════════════════════════════

print("[テスト28-30] mark_execution_started() / mark_terminal()")

policy_28 = FakePolicy(max_attempts=3)
lineage_28, _ = make_lineage_manager(policy_28)
lineage_28.create_new_lineage("run-28", make_monitor_record("run-28", WorkflowMonitorStatus.FAILED))
lineage_28.claim("run-28")
check_true("28. mark_execution_started()成功", lineage_28.mark_execution_started("run-28", "run-28"))
rec_28 = lineage_28.peek("run-28")
check("28. attempt_countが1へ", rec_28.attempt_count, 1)
check("28. phaseがEXECUTION_STARTEDへ", rec_28.phase, RetryLineagePhase.EXECUTION_STARTED)
check_true("28. membershipへ追加される", any(m.run_id == "run-28" for m in rec_28.membership))

scopes_before = len(rec_28.attempt_scopes)
result_29 = lineage_28.mark_terminal("run-28", RetryLineageDisposition.NOT_ACTIONED, "run-28", [])
check_true("29. mark_terminal()成功", result_29.acknowledged)
rec_29 = lineage_28.peek("run-28")
check("29. attempt_scopesの長さが不変", len(rec_29.attempt_scopes), scopes_before)
check("30. NOT_ACTIONEDでもattempt_countは1のまま（payback廃止）", rec_29.attempt_count, 1)
print()


# ═══════════════════════════════════════════════════════════
# テスト31-35: open_next_attempt()
# ═══════════════════════════════════════════════════════════

print("[テスト31-35] open_next_attempt()")

opened_31 = lineage_28.open_next_attempt("run-28")
check_true("31. attempt_count(1)<max_attempts(3): ack=True", opened_31.acknowledged)
check("31. attempt_no=2", opened_31.attempt_no, 2)
rec_31 = lineage_28.peek("run-28")
check("31. phaseがREADY_ELIGIBLEへ", rec_31.phase, RetryLineagePhase.READY_ELIGIBLE)

policy_32 = FakePolicy(max_attempts=1)
lineage_32, _ = make_lineage_manager(policy_32)
lineage_32.create_new_lineage("run-32", make_monitor_record("run-32", WorkflowMonitorStatus.FAILED))
lineage_32.claim("run-32")
lineage_32.mark_execution_started("run-32", "run-32")
lineage_32.mark_terminal("run-32", RetryLineageDisposition.FAILED, "run-32", [])
opened_32 = lineage_32.open_next_attempt("run-32")
check_false("32. attempt_count(1)>=max_attempts(1): ack=False", opened_32.acknowledged)
check_true("32. reasonにmax_attempts exhaustedが含まれる", "max_attempts exhausted" in (opened_32.reason or ""))

policy_33 = FakePolicy(max_attempts=3)
lineage_33, _ = make_lineage_manager(policy_33)
lineage_33.create_new_lineage("run-33", make_monitor_record("run-33", WorkflowMonitorStatus.FAILED))
lineage_33.claim("run-33")
lineage_33.mark_execution_started("run-33", "run-33")
lineage_33.mark_terminal("run-33", RetryLineageDisposition.SUCCEEDED, "run-33", ["news", "review", "publish"])
opened_33 = lineage_33.open_next_attempt("run-33")
check_false("33. terminal_disposition=SUCCEEDEDはack=False", opened_33.acknowledged)

policy_34 = FakePolicy(max_attempts=5)
lineage_34, _ = make_lineage_manager(policy_34)
lineage_34.create_new_lineage("run-34", make_monitor_record("run-34", WorkflowMonitorStatus.FAILED))
lineage_34.claim("run-34")
lineage_34.mark_execution_started("run-34", "run-34")
lineage_34.mark_terminal("run-34", RetryLineageDisposition.FAILED, "run-34", ["news", "review", "publish"])
opened_34 = lineage_34.open_next_attempt("run-34")
check_false("34. steps_confirmed_doneが全stepを覆う: invariant violationでack=False", opened_34.acknowledged)
check_true("34. reasonにinvariant_violationが含まれる", "invariant_violation" in (opened_34.reason or ""))

check("35. next_attempt_ordinalがattempt_scopes[-1].attempt_noと同期して単調増加(1→2)", lineage_28.peek("run-28").next_attempt_ordinal, 2)
print()


# ═══════════════════════════════════════════════════════════
# テスト36-39: 統合、RetryManager._retry_locked()
# ═══════════════════════════════════════════════════════════

print("[テスト36-39] 統合：RetryManager._retry_locked()")


class SpyWorkflowMonitorManager:
    def __init__(self, records: dict):
        self._records = records
        self.get_status_calls: list[str] = []

    def get_status(self, run_id: str):
        self.get_status_calls.append(run_id)
        return self._records.get(run_id)


class FakeWorkflowEngineManagerForRetry:
    """steps_confirmed_doneに応じてSILENT_NO_ACTION→GENUINE_SUCCESSへ推移する
    PUBLISHステップをシミュレートするFake。"""

    def __init__(self):
        self.calls: list[dict] = []
        self._publish_calls = 0

    def run(self, event, dry_run=False, target_step_filter=None, post_admission_hook=None,
            correlation_metadata=None):
        self.calls.append({
            "target_step_filter": target_step_filter, "correlation_metadata": correlation_metadata,
            "dry_run": dry_run,
        })
        run_id = f"exec-run-{len(self.calls)}"
        if post_admission_hook is not None:
            post_admission_hook(run_id)

        steps = []
        for s in target_step_filter:
            if s == PUBLISH:
                self._publish_calls += 1
                action_taken = self._publish_calls >= 2  # 1回目はSILENT_NO_ACTION、2回目でGENUINE_SUCCESS
                steps.append(make_step_result(PUBLISH, executed=True, success=True, action_taken=action_taken))
            else:
                steps.append(make_step_result(s, executed=True, success=True, action_taken=True))
        for s in ALL_WORKFLOW_ENGINE_STEPS:
            if s not in target_step_filter:
                steps.append(make_step_result(s, executed=False, success=True, skip_category=StepSkipCategory.NOT_TARGETED))
        return WorkflowEngineResult(
            run_id=run_id, steps=steps, overall_success=all(s.success for s in steps),
            stopped_early=False, started_at=datetime.now(), finished_at=datetime.now(),
        )


policy_36 = FakePolicy(max_attempts=3)
lineage_36, _ = make_lineage_manager(policy_36)
monitor_36 = SpyWorkflowMonitorManager({
    "run-36": make_monitor_record("run-36", WorkflowMonitorStatus.FAILED, steps=[
        make_step("news", StepExecutionStatus.SUCCESS, action_taken=True),
        make_step("review", StepExecutionStatus.SUCCESS, action_taken=True),
        make_step("publish", StepExecutionStatus.FAILED),
    ]),
})
engine_36 = FakeWorkflowEngineManagerForRetry()
executor_36 = RetryExecutor(workflow_engine_manager=engine_36, lineage=lineage_36)
manager_36 = RetryManager(policy=policy_36, executor=executor_36, monitor=monitor_36, lineage=lineage_36)

result_attempt1 = manager_36.retry("run-36", attempt=1)
check("36. attempt1: 新規lineage作成でMonitorが1回呼ばれる", len(monitor_36.get_status_calls), 1)
check("36. attempt1: should_retry()が1回呼ばれる", len(policy_36.should_retry_calls), 1)
check("38. attempt1: outcome=RETRIED", result_attempt1.outcome, RetryOutcome.RETRIED)
check("38. attempt1: disposition=NOT_ACTIONED相当（PUBLISH silent no-op）",
      lineage_36.peek("run-36").terminal_disposition, RetryLineageDisposition.NOT_ACTIONED)
check("38. attempt1: attempt_countは1（budget消費、payback無し）", lineage_36.peek("run-36").attempt_count, 1)

reopen_36 = lineage_36.open_next_attempt("run-36")
check_true("38前提: open_next_attempt()が成功しattempt2をREADY_ELIGIBLEへ開く", reopen_36.acknowledged)

monitor_calls_before_attempt2 = len(monitor_36.get_status_calls)
should_retry_calls_before_attempt2 = len(policy_36.should_retry_calls)
result_attempt2 = manager_36.retry("run-36", attempt=2)
check("37. attempt2（既存lineage再接続）: Monitor.get_status()の追加呼び出し=0", len(monitor_36.get_status_calls) - monitor_calls_before_attempt2, 0)
check("37. attempt2: should_retry()の追加呼び出し=0", len(policy_36.should_retry_calls) - should_retry_calls_before_attempt2, 0)
check("38. attempt2: outcome=RETRIED", result_attempt2.outcome, RetryOutcome.RETRIED)
check("38. attempt2: disposition=SUCCEEDED（PUBLISHが今回はgenuine成功）",
      lineage_36.peek("run-36").terminal_disposition, RetryLineageDisposition.SUCCEEDED)
check_true("38. attempt2: target_step_filterはPUBLISHのみ（NEWS/REVIEWは再実行されない）",
           engine_36.calls[1]["target_step_filter"] == [PUBLISH])

with RetryExecutionLock(lineage_36.execution_lock_path):
    result_busy = manager_36.retry("run-36", attempt=3)
check("39. RetryExecutionLock busy時はSKIPPED", result_busy.outcome, RetryOutcome.SKIPPED)
print()


# ═══════════════════════════════════════════════════════════
# テスト40-42: 統合、workflow_engine
# ═══════════════════════════════════════════════════════════

print("[テスト40-42] 統合：workflow_engine (target_step_filter / post_admission_hook / run_id)")


class RecordingHistoryManager:
    def __init__(self):
        self.finish_step_calls: list[dict] = []

    def start_run(self, run_id, workflow_name, source, job_id, correlation_metadata=None):
        from execution_history import StartRunWriteResult
        return StartRunWriteResult(run_id=run_id, acknowledged=True)

    def start_step(self, run_id, step):
        return True

    def finish_step(self, run_id, step, status, error_message=None, skipped_reason=None,
                     action_taken=None, skip_category=None):
        self.finish_step_calls.append({"step": step, "status": status, "skip_category": skip_category})
        return True

    def finish_run(self, run_id, status, error_message=None):
        return True

    def release_run(self, run_id):
        return None


class AlwaysSuccessExecutor:
    def execute(self, agent_context):
        return FakeAgentResult(success=True, action_taken=True)


definition_stub = type("D", (), {"steps": [NEWS, REVIEW, PUBLISH]})()
history_40 = RecordingHistoryManager()
executor_40 = WorkflowEngineExecutor(
    definition=definition_stub,
    step_executors={NEWS: AlwaysSuccessExecutor(), REVIEW: AlwaysSuccessExecutor(), PUBLISH: AlwaysSuccessExecutor()},
    history_manager=history_40,
)
context_40 = WorkflowEngineContext(
    event=WorkflowEngineEvent(job_id="j1", source=SOURCE_MANUAL, triggered_at=datetime.now(), trigger_reason="t"),
    dry_run=False, run_id="wf-run-40", target_step_filter=[PUBLISH],
)
result_40 = executor_40.run(context_40)
skipped_steps_40 = [s for s in result_40.steps if not s.executed]
check("40. target_step_filter=[PUBLISH]: NEWS/REVIEWがskip_category=NOT_TARGETED",
      all(s.skip_category == StepSkipCategory.NOT_TARGETED for s in skipped_steps_40), True)
check("40. target_step_filter外stepはexecutorへ委譲されない（Agentが呼ばれない）",
      sum(1 for s in result_40.steps if s.executed), 1)

history_41 = RecordingHistoryManager()
executor_41 = WorkflowEngineExecutor(
    definition=definition_stub,
    step_executors={NEWS: AlwaysSuccessExecutor(), REVIEW: AlwaysSuccessExecutor(), PUBLISH: AlwaysSuccessExecutor()},
    history_manager=history_41,
)


def failing_hook(run_id: str) -> PostAdmissionHookResult:
    return PostAdmissionHookResult(acknowledged=False)


context_41 = WorkflowEngineContext(
    event=WorkflowEngineEvent(job_id="j1", source=SOURCE_MANUAL, triggered_at=datetime.now(), trigger_reason="t"),
    dry_run=False, run_id="wf-run-41", post_admission_hook=failing_hook,
)
result_41 = executor_41.run(context_41)
check("41. hook ack=False: 全stepがexecuted=False", all(not s.executed for s in result_41.steps), True)
check("41. hook ack=False: 全stepがskip_category=HOOK_NOT_ACKNOWLEDGED",
      all(s.skip_category == StepSkipCategory.HOOK_NOT_ACKNOWLEDGED for s in result_41.steps), True)
check_true("41. hook ack=False: overall_success=False", not result_41.overall_success)

history_41b = RecordingHistoryManager()
executor_41b = WorkflowEngineExecutor(
    definition=definition_stub,
    step_executors={NEWS: AlwaysSuccessExecutor(), REVIEW: AlwaysSuccessExecutor(), PUBLISH: AlwaysSuccessExecutor()},
    history_manager=history_41b,
)


def raising_hook(run_id: str) -> PostAdmissionHookResult:
    raise ValueError("boom")


context_41b = WorkflowEngineContext(
    event=WorkflowEngineEvent(job_id="j1", source=SOURCE_MANUAL, triggered_at=datetime.now(), trigger_reason="t"),
    dry_run=False, run_id="wf-run-41b", post_admission_hook=raising_hook,
)
raised = False
try:
    executor_41b.run(context_41b)
except ValueError:
    raised = True
check_true("41. hook例外はExecution History終端後に再raiseされる", raised)
check_true("41. hook例外経路でもfinish_step()が呼ばれている（history終端済み）", len(history_41b.finish_step_calls) > 0)

check("42. WorkflowEngineResult.run_idが実際のrun_idと一致する", result_40.run_id, "wf-run-40")
print()


# ═══════════════════════════════════════════════════════════
# テスト43-47: RetryLineageManager.verify_orphan_correlation()
# ═══════════════════════════════════════════════════════════

print("[テスト43-47] verify_orphan_correlation()：10.3.3章(b)のexact-match検証")

policy_43, _ = FakePolicy(max_attempts=3), None
lineage_43, _ = make_lineage_manager(policy_43)
lineage_43.create_new_lineage("root-43", make_monitor_record("root-43", WorkflowMonitorStatus.FAILED))
claim_43 = lineage_43.claim("root-43")  # next_attempt_ordinal=1のままCLAIMEDへ、correlation_id発行

check_true(
    "43. root_run_id実在・attempt_no一致・correlation_id一致の3条件すべて満たす場合はTrue",
    lineage_43.verify_orphan_correlation("root-43", "1", claim_43.correlation_id),
)
check_false("44. forged（存在しないroot_run_id）はFalse", lineage_43.verify_orphan_correlation("does-not-exist-43", "1", claim_43.correlation_id))
check_false("45. stale（古いintended_attempt_no）はFalse", lineage_43.verify_orphan_correlation("root-43", "99", claim_43.correlation_id))
check_false("46. correlation_id不一致はFalse", lineage_43.verify_orphan_correlation("root-43", "1", "wrong-correlation-id"))
check_false("47. intended_attempt_noがパース不可（非数値文字列）はFalse", lineage_43.verify_orphan_correlation("root-43", "not-a-number", claim_43.correlation_id))
print()


# ═══════════════════════════════════════════════════════════
# テスト48-52: 統合、RetryEnqueueTrigger correlation-fallback
# ═══════════════════════════════════════════════════════════

print("[テスト48-52] 統合：RetryEnqueueTrigger membership-first / correlation-fallback")


class FakeQueueForTrigger:
    def __init__(self):
        self.enqueued = []

    def exists(self, run_id):
        return False

    def enqueue(self, run_id, workflow_name, retry_attempt):
        self.enqueued.append(run_id)
        from retry_queue import RetryQueueOutcome, RetryQueueResult
        return RetryQueueResult(outcome=RetryQueueOutcome.ENQUEUED, item=None, reason=None)


class FakeMonitorForTrigger:
    def __init__(self, records):
        self._records = records

    def list_status(self, limit=None):
        return self._records


class FakeHistoryStoreForTrigger:
    """execution_history.ExecutionHistoryStoreのread-onlyなFake（get()のみ使用）。"""

    def __init__(self, records: dict):
        self._records = records

    def get(self, run_id):
        return self._records.get(run_id)

    def save(self, record):
        raise NotImplementedError("read-onlyのFakeのため呼ばれないはず")

    def list_all(self):
        return list(self._records.values())


def make_exec_record(run_id, correlation_metadata=None):
    now = datetime.now()
    return WorkflowExecutionRecord(
        run_id=run_id, workflow_name="workflow_engine", source="manual", job_id="job-1",
        status=WorkflowExecutionStatus.FAILED, started_at=now, finished_at=now,
        correlation_metadata=correlation_metadata or {},
    )


# テスト48：membership-firstが優先され、history_store.get()は呼ばれない
policy_48 = FakePolicy(max_attempts=3)
lineage_48, _ = make_lineage_manager(policy_48)
lineage_48.create_new_lineage("root-48", make_monitor_record("root-48", WorkflowMonitorStatus.FAILED))
lineage_48.claim("root-48")
lineage_48.mark_execution_started("root-48", "member-run-48")  # membershipへ登録

get_calls_48 = []
history_store_48 = FakeHistoryStoreForTrigger({})
_orig_get_48 = history_store_48.get
def _tracking_get_48(run_id):
    get_calls_48.append(run_id)
    return _orig_get_48(run_id)
history_store_48.get = _tracking_get_48

monitor_48 = FakeMonitorForTrigger([make_monitor_record("member-run-48", WorkflowMonitorStatus.FAILED)])
trigger_48 = RetryEnqueueTrigger(
    monitor=monitor_48, queue=FakeQueueForTrigger(), lineage=lineage_48, history_store=history_store_48,
)
result_48 = trigger_48.enqueue_pending_failures()
check("48. membership-firstでskipped_lineage_member=1", result_48.skipped_lineage_member, 1)
check("48. membership-firstが成立した場合history_store.get()は呼ばれない", len(get_calls_48), 0)
check("48. enqueueされない", result_48.enqueued, 0)

# テスト49：correlation-fallbackで正しくexact-match除外される
policy_49 = FakePolicy(max_attempts=3)
lineage_49, _ = make_lineage_manager(policy_49)
lineage_49.create_new_lineage("root-49", make_monitor_record("root-49", WorkflowMonitorStatus.FAILED))
claim_49 = lineage_49.claim("root-49")  # attempt_no=1、まだmark_execution_started()していない＝orphan
exec_record_49 = make_exec_record("orphan-run-49", correlation_metadata={
    "retry_lineage": {
        "root_run_id": "root-49",
        "intended_attempt_no": "1",
        "correlation_id": claim_49.correlation_id,
    }
})
history_store_49 = FakeHistoryStoreForTrigger({"orphan-run-49": exec_record_49})
monitor_49 = FakeMonitorForTrigger([make_monitor_record("orphan-run-49", WorkflowMonitorStatus.FAILED)])
trigger_49 = RetryEnqueueTrigger(
    monitor=monitor_49, queue=FakeQueueForTrigger(), lineage=lineage_49, history_store=history_store_49,
)
result_49 = trigger_49.enqueue_pending_failures()
check("49. correlation-fallback exact-matchでskipped_lineage_correlation=1", result_49.skipped_lineage_correlation, 1)
check("49. enqueueされない", result_49.enqueued, 0)

# テスト50：malformed correlation_metadata（namespace欠落）はfail-closedで通常処理される
policy_50 = FakePolicy(max_attempts=3)
lineage_50, _ = make_lineage_manager(policy_50)
lineage_50.create_new_lineage("root-50", make_monitor_record("root-50", WorkflowMonitorStatus.FAILED))
lineage_50.claim("root-50")
exec_record_50 = make_exec_record("orphan-run-50", correlation_metadata={"unrelated_namespace": {"foo": "bar"}})
history_store_50 = FakeHistoryStoreForTrigger({"orphan-run-50": exec_record_50})
monitor_50 = FakeMonitorForTrigger([make_monitor_record("orphan-run-50", WorkflowMonitorStatus.FAILED)])
queue_50 = FakeQueueForTrigger()
trigger_50 = RetryEnqueueTrigger(
    monitor=monitor_50, queue=queue_50, lineage=lineage_50, history_store=history_store_50,
)
result_50 = trigger_50.enqueue_pending_failures()
check("50. malformed（namespace欠落）はskipped_lineage_correlation=0（除外されない）", result_50.skipped_lineage_correlation, 0)
check("50. malformedな候補は通常どおりenqueueされる", result_50.enqueued, 1)

# テスト51：forged root_run_id・stale attempt_no・correlation_id不一致のいずれもfail-closed
policy_51 = FakePolicy(max_attempts=3)
lineage_51, _ = make_lineage_manager(policy_51)
lineage_51.create_new_lineage("root-51", make_monitor_record("root-51", WorkflowMonitorStatus.FAILED))
claim_51 = lineage_51.claim("root-51")

forged_cases = [
    ("orphan-forged-51", {"root_run_id": "does-not-exist-51", "intended_attempt_no": "1", "correlation_id": claim_51.correlation_id}),
    ("orphan-stale-51", {"root_run_id": "root-51", "intended_attempt_no": "99", "correlation_id": claim_51.correlation_id}),
    ("orphan-wrongcorr-51", {"root_run_id": "root-51", "intended_attempt_no": "1", "correlation_id": "wrong-id"}),
]
records_51 = {run_id: make_exec_record(run_id, correlation_metadata={"retry_lineage": ns}) for run_id, ns in forged_cases}
history_store_51 = FakeHistoryStoreForTrigger(records_51)
monitor_51 = FakeMonitorForTrigger([make_monitor_record(run_id, WorkflowMonitorStatus.FAILED) for run_id, _ in forged_cases])
queue_51 = FakeQueueForTrigger()
trigger_51 = RetryEnqueueTrigger(
    monitor=monitor_51, queue=queue_51, lineage=lineage_51, history_store=history_store_51,
)
result_51 = trigger_51.enqueue_pending_failures()
check("51. forged/stale/不一致の3件いずれもskipped_lineage_correlation=0", result_51.skipped_lineage_correlation, 0)
check("51. forged/stale/不一致の3件とも通常どおりenqueueされる（fail-closed=再実行対象に残る）", result_51.enqueued, 3)

# テスト52：correlation_metadataを一切持たない無関係なFAILED候補は誤って除外されない
policy_52 = FakePolicy(max_attempts=3)
lineage_52, _ = make_lineage_manager(policy_52)
history_store_52 = FakeHistoryStoreForTrigger({"unrelated-run-52": make_exec_record("unrelated-run-52")})
monitor_52 = FakeMonitorForTrigger([make_monitor_record("unrelated-run-52", WorkflowMonitorStatus.FAILED)])
queue_52 = FakeQueueForTrigger()
trigger_52 = RetryEnqueueTrigger(
    monitor=monitor_52, queue=queue_52, lineage=lineage_52, history_store=history_store_52,
)
result_52 = trigger_52.enqueue_pending_failures()
check("52. 無関係な独立FAILED候補が誤除外されない（skipped_lineage_correlation=0）", result_52.skipped_lineage_correlation, 0)
check("52. 無関係な独立FAILED候補は通常どおりenqueueされる", result_52.enqueued, 1)
print()


# ═══════════════════════════════════════════════════════════
# テスト59-63: Architecture Amendment（Code Review Findings対応）
# ═══════════════════════════════════════════════════════════

print("[テスト59-63] Architecture Amendment（Code Review Findings対応）")


class FakeWorkflowEngineManagerHookNotAck:
    """post_admission_hookを呼び、ackがFalseなら全stepNOT_REACHED相当の
    engine_resultを返す（実際のworkflow_engine_executorの挙動を模擬）。"""

    def __init__(self):
        self.calls = 0

    def run(self, event, dry_run=False, target_step_filter=None, post_admission_hook=None,
            correlation_metadata=None):
        self.calls += 1
        run_id = f"exec-hooknotack-{self.calls}"
        hook_result = post_admission_hook(run_id) if post_admission_hook is not None else None
        if hook_result is not None and not hook_result.acknowledged:
            steps = [
                make_step_result(s, executed=False, success=False,
                                  skip_category=StepSkipCategory.HOOK_NOT_ACKNOWLEDGED)
                for s in ALL_WORKFLOW_ENGINE_STEPS
            ]
            return WorkflowEngineResult(
                run_id=run_id, steps=steps, overall_success=False,
                stopped_early=True, started_at=datetime.now(), finished_at=datetime.now(),
            )
        steps = [
            make_step_result(s, executed=True, success=True, action_taken=True)
            for s in (target_step_filter or ALL_WORKFLOW_ENGINE_STEPS)
        ]
        return WorkflowEngineResult(
            run_id=run_id, steps=steps, overall_success=True,
            stopped_early=False, started_at=datetime.now(), finished_at=datetime.now(),
        )


# 59(a). hook未ack（プロセスはクラッシュしない）：SUCCEEDED/COMPLETEに到達しない
policy_59, lineage_59 = FakePolicy(max_attempts=3), None
lineage_59, _ = make_lineage_manager(policy_59)
lineage_59.create_new_lineage("run-59", make_monitor_record("run-59", WorkflowMonitorStatus.FAILED))
claim_59 = lineage_59.claim("run-59")
check_true("59前提: claim()成功", claim_59.acknowledged)
lineage_59.release_claim("run-59")  # hookが「未ack」を経験するよう、意図的にCLAIMEDから外す

mark_terminal_calls_59 = []
_orig_mark_terminal_59 = lineage_59.mark_terminal
def _spy_mark_terminal_59(*args, **kwargs):
    mark_terminal_calls_59.append((args, kwargs))
    return _orig_mark_terminal_59(*args, **kwargs)
lineage_59.mark_terminal = _spy_mark_terminal_59

engine_59 = FakeWorkflowEngineManagerHookNotAck()
executor_59 = RetryExecutor(workflow_engine_manager=engine_59, lineage=lineage_59)
request_59 = RetryRequest(run_id="run-59", attempt=1, requested_at=datetime.now(), dry_run=False)
result_59 = executor_59.execute(request_59, lineage_59.peek("run-59"), claim_59)

check("59. hook未ack: outcome=SKIPPED（SUCCEEDED/COMPLETEに到達しない）", result_59.outcome, RetryOutcome.SKIPPED)
check("59. hook未ack: mark_terminal()は一切呼ばれない", len(mark_terminal_calls_59), 0)
check("59. hook未ack: lineageはREADY_ELIGIBLEのまま（解放済み）", lineage_59.peek("run-59").phase, RetryLineagePhase.READY_ELIGIBLE)
check("59. hook未ack: attempt_countは変化しない(0のまま)", lineage_59.peek("run-59").attempt_count, 0)

decision_59 = RetryQueueUpdateDecider().decide(RetryExecutionResult(dispatch_event=None, retry_result=result_59))
check("59. hook未ack: RetryQueueUpdateDeciderはNOOP（COMPLETEにしない）", decision_59.outcome, RetryQueueUpdateOutcome.NOOP)

# 59(b). hookは成功（ack=True）したが、その後.run()自体が例外を送出する
#        （既存fail-fast契約、10.2.3章：例外は再raiseされる。durable ackはTrueに
#        達しているため、claimは解放せずEXECUTION_STARTEDのままreconcileへ委ねる）
class FakeWorkflowEngineManagerRaisesAfterHook:
    def run(self, event, dry_run=False, target_step_filter=None, post_admission_hook=None,
            correlation_metadata=None):
        if post_admission_hook is not None:
            post_admission_hook("exec-59exc")
        raise RuntimeError("simulated .run() exception after hook ack succeeded")


lineage_59exc, _ = make_lineage_manager(FakePolicy(max_attempts=3))
lineage_59exc.create_new_lineage("run-59exc", make_monitor_record("run-59exc", WorkflowMonitorStatus.FAILED))
claim_59exc = lineage_59exc.claim("run-59exc")
engine_59exc = FakeWorkflowEngineManagerRaisesAfterHook()
executor_59exc = RetryExecutor(workflow_engine_manager=engine_59exc, lineage=lineage_59exc)
request_59exc = RetryRequest(run_id="run-59exc", attempt=1, requested_at=datetime.now(), dry_run=False)

raised_59exc = False
try:
    executor_59exc.execute(request_59exc, lineage_59exc.peek("run-59exc"), claim_59exc)
except RuntimeError:
    raised_59exc = True
check_true("59. hook成功後.run()が例外送出: 既存fail-fast契約どおり再raiseされる", raised_59exc)
check("59. hook成功後.run()が例外送出: ack済みのためEXECUTION_STARTEDのまま残る（reconcileへ委譲）",
      lineage_59exc.peek("run-59exc").phase, RetryLineagePhase.EXECUTION_STARTED)


# 59(c). hook自体が例外を送出する（HOOK_EXCEPTION相当）：claimを解放してから再raiseする
class _RaisingHookLineageProxy:
    def __init__(self, real):
        self._real = real

    def mark_execution_started(self, root_run_id, run_id):
        raise RuntimeError("simulated HOOK_EXCEPTION")

    def release_claim(self, root_run_id):
        return self._real.release_claim(root_run_id)

    def mark_terminal(self, *args, **kwargs):
        raise AssertionError("mark_terminal() must not be called when the hook itself raised")


class FakeWorkflowEngineManagerCallsHookThenPropagates:
    def run(self, event, dry_run=False, target_step_filter=None, post_admission_hook=None,
            correlation_metadata=None):
        post_admission_hook("exec-59hookexc")  # このhook自体が例外を送出する


lineage_59hookexc, _ = make_lineage_manager(FakePolicy(max_attempts=3))
lineage_59hookexc.create_new_lineage("run-59hookexc", make_monitor_record("run-59hookexc", WorkflowMonitorStatus.FAILED))
claim_59hookexc = lineage_59hookexc.claim("run-59hookexc")
proxy_59hookexc = _RaisingHookLineageProxy(lineage_59hookexc)
executor_59hookexc = RetryExecutor(workflow_engine_manager=FakeWorkflowEngineManagerCallsHookThenPropagates(), lineage=proxy_59hookexc)
request_59hookexc = RetryRequest(run_id="run-59hookexc", attempt=1, requested_at=datetime.now(), dry_run=False)

raised_59hookexc = False
try:
    executor_59hookexc.execute(request_59hookexc, lineage_59hookexc.peek("run-59hookexc"), claim_59hookexc)
except RuntimeError:
    raised_59hookexc = True
check_true("59. hook自体が例外送出: 既存fail-fast契約どおり再raiseされる", raised_59hookexc)
check("59. hook自体が例外送出: claimは解放されREADY_ELIGIBLEへ戻る",
      lineage_59hookexc.peek("run-59hookexc").phase, RetryLineagePhase.READY_ELIGIBLE)
print()


# テスト60：mark_terminal()のack=FalseはRetryOutcome.SKIPPEDへ正しく伝播する
class _MarkTerminalFailingProxy:
    def __init__(self, real):
        self._real = real

    def mark_execution_started(self, root_run_id, run_id):
        return self._real.mark_execution_started(root_run_id, run_id)

    def release_claim(self, root_run_id):
        return self._real.release_claim(root_run_id)

    def mark_terminal(self, *args, **kwargs):
        return MarkTerminalResult(acknowledged=False, reason="simulated lineage store save failure")


lineage_60, _ = make_lineage_manager(FakePolicy(max_attempts=3))
lineage_60.create_new_lineage("run-60", make_monitor_record("run-60", WorkflowMonitorStatus.FAILED))
claim_60 = lineage_60.claim("run-60")
proxy_60 = _MarkTerminalFailingProxy(lineage_60)
executor_60 = RetryExecutor(workflow_engine_manager=FakeWorkflowEngineManagerHookNotAck(), lineage=proxy_60)
request_60 = RetryRequest(run_id="run-60", attempt=1, requested_at=datetime.now(), dry_run=False)
result_60 = executor_60.execute(request_60, lineage_60.peek("run-60"), claim_60)

check("60. mark_terminal() ack=False: outcome=SKIPPED（RETRIEDにならない）", result_60.outcome, RetryOutcome.SKIPPED)
check_true("60. mark_terminal() ack=False: reasonにmark_terminal()の理由が含まれる",
           "simulated lineage store save failure" in (result_60.reason or ""))
print()


# テスト61：reconcile_all()がphase==CLAIMEDのorphanをrelease_claim()で回収する（16章(c)）
lineage_61, _ = make_lineage_manager(FakePolicy(max_attempts=3))
lineage_61.create_new_lineage("run-61", make_monitor_record("run-61", WorkflowMonitorStatus.FAILED))
claim_61 = lineage_61.claim("run-61")
check_true("61前提: claim()成功", claim_61.acknowledged)
check("61前提: phase=CLAIMED", lineage_61.peek("run-61").phase, RetryLineagePhase.CLAIMED)

summary_61 = lineage_61.reconcile_all(lambda run_id: None)
check_false("61. reconcile_all()はskipped=Falseで実行される", summary_61.skipped)
check("61. reconcile_all(): released_count=1（CLAIMED orphanを回収）", summary_61.released_count, 1)
check("61. reconcile_all()後、lineageはREADY_ELIGIBLEへ戻る", lineage_61.peek("run-61").phase, RetryLineagePhase.READY_ELIGIBLE)
check("61. reconcile_all()後もattempt_countは0のまま（budget未消費）", lineage_61.peek("run-61").attempt_count, 0)
print()


# テスト62：create_new_lineage()：グローバルmembership一意性チェック（Major#3対応）
lineage_62, _ = make_lineage_manager(FakePolicy(max_attempts=3))
created_62a = lineage_62.create_new_lineage("run-62a", make_monitor_record("run-62a", WorkflowMonitorStatus.FAILED))
check_true("62前提: run-62aのlineage作成成功", created_62a.lineage is not None)

# root_run_id自体が既存lineageと衝突するケース
created_62b = lineage_62.create_new_lineage("run-62a", make_monitor_record("run-62a", WorkflowMonitorStatus.FAILED))
check_true("62. root_run_id衝突: admission_rejected=True", created_62b.admission_rejected)
check_true("62. root_run_id衝突: reasonにuniquenessが含まれる", "uniqueness" in (created_62b.reason or ""))

# membershipのrun_idが既存lineageに属しているケース（find_existing_lineage()を経由せず
# create_new_lineage()を直接呼ぶ、membership index破損フォールバック相当の状況を模擬）
lineage_62.claim("run-62a")
lineage_62.mark_execution_started("run-62a", "exec-62a-1")
created_62c = lineage_62.create_new_lineage("exec-62a-1", make_monitor_record("exec-62a-1", WorkflowMonitorStatus.FAILED))
check_true("62. membership衝突: admission_rejected=True", created_62c.admission_rejected)
check_true("62. membership衝突: reasonに既存root_run_idが含まれる", "run-62a" in (created_62c.reason or ""))
check("62. membership衝突: exec-62a-1は新規rootとして作成されない（peek()はNone）",
      lineage_62.peek("exec-62a-1"), None)
print()


# テスト63：claim()・open_next_attempt()：next_attempt_ordinal不一致はinvariant violationでfail-closed（Major#4対応）
lineage_63, _ = make_lineage_manager(FakePolicy(max_attempts=3))
lineage_63.create_new_lineage("run-63", make_monitor_record("run-63", WorkflowMonitorStatus.FAILED))
corrupted_63 = lineage_63._store.get("run-63")
corrupted_63.next_attempt_ordinal = 99  # attempt_scopes[-1].attempt_no=1のまま、意図的に不一致を注入
lineage_63._store.save(corrupted_63)

claim_63 = lineage_63.claim("run-63")
check_false("63. next_attempt_ordinal不一致: claim()はack=False", claim_63.acknowledged)
check_true("63. next_attempt_ordinal不一致: reasonにinvariant_violationが含まれる", "invariant_violation" in (claim_63.reason or ""))

lineage_63b, _ = make_lineage_manager(FakePolicy(max_attempts=3))
lineage_63b.create_new_lineage("run-63b", make_monitor_record("run-63b", WorkflowMonitorStatus.FAILED))
lineage_63b.claim("run-63b")
lineage_63b.mark_execution_started("run-63b", "run-63b")
lineage_63b.mark_terminal("run-63b", RetryLineageDisposition.FAILED, "run-63b", [])
corrupted_63b = lineage_63b._store.get("run-63b")
corrupted_63b.next_attempt_ordinal = 42
lineage_63b._store.save(corrupted_63b)
opened_63b = lineage_63b.open_next_attempt("run-63b")
check_false("63. next_attempt_ordinal不一致: open_next_attempt()はack=False", opened_63b.acknowledged)
check_true("63. next_attempt_ordinal不一致: reasonにinvariant_violationが含まれる", "invariant_violation" in (opened_63b.reason or ""))
print()


# ─── 後片付け ───
for d in tmp_dirs:
    shutil.rmtree(d, ignore_errors=True)


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
