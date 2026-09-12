"""
E2E テスト: Release 6.32 sub-milestone 6D-1
Retry Queue Update — Lineage-Authoritative Disposition Input Contract

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    22.4章（Retry Queue Update整合）・22.4a章（decide_all()バッチ経路統合）・
    28.-18節（12件）・28.-8節（8件、#4b/#4c/#5b/#5cを含む）。

本テストは、§22.4/22.4aが定めるLineage-Authoritative Disposition Input Contract
（`LineageAuthoritativeDispositionInput` / `LegacyQueueDecisionInput`の
discriminated union、`RetryQueueDecisionRequest`・`build_queue_decision_input()`・
`build_retry_queue_decision_requests()`）が、Approved Architectureどおり実装され
ていることを直接検証する。

**重要な境界（22.4節・17.3節）**：
    - RetryQueueUpdateDeciderはretry eligibility・authorization・dispatchの
      authorityではない。既に実行された再試行結果に対するpost-hoc bookkeeping
      のみを担う。
    - HRR専用のRetryQueueStatus・RetryQueueUpdateOutcomeは追加しない
      （HUMAN_REVIEW_REQUIREDは既存のFAIL/FAILEDへ合流する）。
    - HRR authorized retry自体の認可・dispatchはcomposition層の
      retry_after_human_review()（17.3節）がqueue/scheduler非経由で直接行う。
      本テストの変更対象とは独立しており、矛盾しない。
    - LineageAuthoritativeDispositionInputはHRR専用機構ではなく、SUCCEEDED/
      FAILED/NOT_ACTIONED/HUMAN_REVIEW_REQUIREDのすべてを対象とする汎用契約
      である。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_10_retry_queue_lineage_authoritative_disposition.py
"""
from __future__ import annotations

import ast
import sys
import tempfile
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

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
    check(label, bool(value), True)


print("=" * 60)
print("Retry Queue Update — Lineage-Authoritative Disposition Input Contract")
print("（sub-milestone 6D-1、§22.4・22.4a・28.-18・28.-8）E2E テスト")
print("=" * 60)
print()

from retry_queue import RetryQueueStatus
from scheduler import SchedulerEvent
from workflow_engine import WorkflowEngineResult, WorkflowEngineStep, WorkflowEngineStepResult
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus
from retry_lineage import (
    JsonRetryLineageStore,
    RetryLineageConfig,
    RetryLineageDisposition,
    RetryLineageManager,
    RetryLineagePhase,
    RetryLineageRecord,
)
from retry_engine import (
    LegacyQueueDecisionInput,
    LineageAuthoritativeDispositionInput,
    RetryCandidateEvent,
    RetryDispatchEvent,
    RetryExecutionResult,
    RetryManager,
    RetryOutcome,
    RetryQueueCleanupDecider,
    RetryQueueCleanupOutcome,
    RetryQueueDecisionRequest,
    RetryQueueRemovalExecutor,
    RetryQueueTerminalCleanupDecider,
    RetryQueueUpdateContractError,
    RetryQueueUpdateDecider,
    RetryQueueUpdateOutcome,
    RetryResult,
    build_queue_decision_input,
    build_retry_queue_decision_requests,
)
from retry_lineage.retry_lineage_target_resolution import resolve_final_disposition
from retry_lineage.retry_lineage_genuine_action import StepOutcomeCategory
from side_effect_safety.side_effect_safety_category import SideEffectSafetyCategory, SideEffectSafetyReport


tmp_dirs: list[Path] = []


class FakeCandidate:
    def __init__(self, run_id: str):
        self.run_id = run_id
        self.retry_attempt = 1


def make_execution_result(run_id: str, retry_result: RetryResult) -> RetryExecutionResult:
    candidate = FakeCandidate(run_id)
    scheduler_event = SchedulerEvent(
        job_id=f"retry-{run_id}", execute_time=datetime(2026, 9, 9, 9, 0),
        trigger_reason="Retry candidate selected.", metadata={"retry_candidate": candidate},
    )
    candidate_event = RetryCandidateEvent(run_id=run_id, candidate=candidate, source_event=scheduler_event)
    dispatch_event = RetryDispatchEvent(candidate_event=candidate_event, dispatchable=True)
    return RetryExecutionResult(dispatch_event=dispatch_event, retry_result=retry_result)


def make_unknown_step(step=WorkflowEngineStep.NEWS) -> WorkflowEngineStepResult:
    """classify_step_outcome()がStepOutcomeCategory.UNKNOWNへ分類するstep
    （executed=False・agent_result=None・skip_category=None、構造化フィールド
    未設定の防御的fail-closedケース）。disposition_from_categories()により
    RetryLineageDisposition.FAILEDを誘発する。"""
    return WorkflowEngineStepResult(
        step=step, executed=False, agent_result=None, success=False,
        skipped_reason=None, skip_category=None,
    )


def make_workflow_engine_result(
    overall_success: bool, run_id: str = "wer-run", steps: "list | None" = None,
) -> WorkflowEngineResult:
    now = datetime.now()
    return WorkflowEngineResult(
        steps=steps if steps is not None else [], overall_success=overall_success, stopped_early=False,
        started_at=now, finished_at=now, run_id=run_id,
    )


def make_retried_result(run_id: str, overall_success: bool, steps: "list | None" = None) -> RetryResult:
    return RetryResult(
        original_run_id=run_id, outcome=RetryOutcome.RETRIED, attempt=1,
        monitor_status=WorkflowMonitorStatus.FAILED, reason=None,
        workflow_engine_result=make_workflow_engine_result(overall_success, run_id=run_id, steps=steps),
    )


class FakePolicy:
    def __init__(self, max_attempts: int = 3):
        self.target_statuses = frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT})
        self._max_attempts = max_attempts

    @property
    def max_attempts(self):
        return self._max_attempts

    def should_retry(self, monitor_status, attempt) -> bool:
        return monitor_status in self.target_statuses and attempt < self._max_attempts


def make_lineage_manager() -> tuple[RetryLineageManager, Path]:
    tmp_root = Path(tempfile.mkdtemp())
    tmp_dirs.append(tmp_root)
    config = RetryLineageConfig(enabled=True, lineage_dir=tmp_root)
    store = JsonRetryLineageStore(config.store_dir)
    return RetryLineageManager(store=store, config=config, policy=FakePolicy()), tmp_root


def make_record(
    root_run_id: str, phase: RetryLineagePhase = RetryLineagePhase.TERMINAL,
    terminal_disposition: "RetryLineageDisposition | None" = RetryLineageDisposition.HUMAN_REVIEW_REQUIRED,
    side_effect_contract_version: "int | None" = 1,
) -> RetryLineageRecord:
    now = datetime.now()
    return RetryLineageRecord(
        root_run_id=root_run_id, parent_run_id=None, latest_run_id=root_run_id,
        attempt_count=1, max_attempts=3, next_attempt_ordinal=1, phase=phase,
        terminal_disposition=terminal_disposition, next_eligible_at=None, owner_token=None,
        steps_confirmed_done=[], created_at=now, updated_at=now,
        side_effect_contract_version=side_effect_contract_version,
    )


# =====================================================================
# §28.-8 テスト1-2: HRR terminal_disposition → decide() → FAIL/FAILED
#                    （安全性優先の判定がQueue側の独立再計算に倒されない）
# =====================================================================

print("[28.-8 #1-2] LineageAuthoritativeDispositionInput(HUMAN_REVIEW_REQUIRED) → FAIL/FAILED")

decider = RetryQueueUpdateDecider()

# workflow step自体は全て成功（overall_success=True）＝decide_disposition()による
# 独立再計算ではSUCCEEDED相当になりうる状況を人為的に作る。
er_1 = make_execution_result("run-hrr-1", make_retried_result("run-hrr-1", overall_success=True))
decision_1 = decider.decide(er_1, LineageAuthoritativeDispositionInput(terminal_disposition=RetryLineageDisposition.HUMAN_REVIEW_REQUIRED))
check("1. HRR terminal_disposition → outcome=FAIL", decision_1.outcome, RetryQueueUpdateOutcome.FAIL)
check("1. HRR terminal_disposition → target_status=FAILED", decision_1.target_status, RetryQueueStatus.FAILED)
check_true(
    "2. 権威あるterminal_disposition=HRRが、独立再計算(SUCCEEDED相当になりうる状況)に関わらずFAILのまま",
    decision_1.outcome == RetryQueueUpdateOutcome.FAIL,
)
print()


# =====================================================================
# §28.-8 テスト3: FAIL終端のQueue項目 → RetryQueueRemovalExecutor.apply()
# =====================================================================

print("[28.-8 #3] FAIL終端 → RetryQueueRemovalExecutor.apply() → remove_fn呼び出し")

remove_calls_3: list[str] = []


def fake_remove_fn_3(run_id: str):
    remove_calls_3.append(run_id)
    return None


removal_result_3 = RetryQueueRemovalExecutor().apply(decision_1, remove_fn=fake_remove_fn_3)
check_true("3. FAIL outcomeはremove対象と判定される（attempted=True）", removal_result_3.attempted)
check("3. remove_fnが実際に呼ばれる", remove_calls_3, ["run-hrr-1"])
print()


# =====================================================================
# §28.-8 テスト4b: Layer 2（既存sibling stageとしてのexact確認）
# =====================================================================

print("[28.-8 #4b] HRR由来decision(FAIL)をsibling stage群（Removal/Cleanup/TerminalCleanup）へ個別に流す")

remove_calls_4b: list[str] = []


def fake_remove_fn_4b(run_id: str):
    remove_calls_4b.append(run_id)
    return None


removal_results_4b = RetryQueueRemovalExecutor().apply_all([decision_1], remove_fn=fake_remove_fn_4b)
check_true("4b(i). RetryQueueRemovalExecutorがHRR由来FAILを除去対象と判定する", removal_results_4b[0].attempted)
check("4b(i). remove_fnが呼ばれる", remove_calls_4b, ["run-hrr-1"])

cleanup_decision_4b = RetryQueueCleanupDecider().decide(decision_1)
check(
    "4b(ii). RetryQueueCleanupDeciderはFAIL outcomeに対し常にKEEP（NOOPではないため対象外）",
    cleanup_decision_4b.outcome, RetryQueueCleanupOutcome.KEEP,
)

terminal_cleanup_decision_4b = RetryQueueTerminalCleanupDecider().decide(decision_1)
check(
    "4b(iii). RetryQueueTerminalCleanupDeciderもFAIL outcomeに対し常にKEEP",
    terminal_cleanup_decision_4b.outcome, RetryQueueCleanupOutcome.KEEP,
)
print()


# =====================================================================
# §28.-8 テスト4c: Layer 3（defense-in-depth、claim()のphaseチェックによる最終防御）
# =====================================================================

print("[28.-8 #4c] Layer 1バイパスを模擬（HRR run_idが誤ってenqueueされた状態）→ RetryManager.retry()がclaim()で拒否")

lineage_4c, _ = make_lineage_manager()
record_4c = lineage_4c.create_new_lineage(
    "run-hrr-4c", WorkflowMonitorRecord(
        run_id="run-hrr-4c", workflow_name="workflow_engine", monitor_status=WorkflowMonitorStatus.FAILED,
        source_status="failed", source="manual", job_id="job-1",
        started_at=datetime.now(), finished_at=datetime.now(), elapsed_seconds=1.0, reason=None, steps=[],
    ),
).lineage
claim_hrr_4c = lineage_4c.claim("run-hrr-4c")
lineage_4c.mark_execution_started("run-hrr-4c", "run-hrr-4c", claim_hrr_4c.owner_token)
lineage_4c.mark_terminal(
    "run-hrr-4c", disposition=RetryLineageDisposition.HUMAN_REVIEW_REQUIRED,
    executed_run_id="run-hrr-4c", newly_confirmed_steps=[],
)
peeked_4c = lineage_4c.peek("run-hrr-4c")
check("4c. HRR確定lineageのphaseはTERMINALのまま", peeked_4c.phase, RetryLineagePhase.TERMINAL)

claim_result_4c = lineage_4c.claim("run-hrr-4c")
check_true(
    "4c. Layer 1が何らかの理由でバイパスされretry()が呼ばれても、claim()がphase!=READY_ELIGIBLEでfail-closedする",
    not claim_result_4c.acknowledged,
)
print()


# =====================================================================
# §28.-8 テスト5: legacy lineage → decide()にLegacyQueueDecisionInput() → 6.31 semantics無変更
# =====================================================================

print("[28.-8 #5] LegacyQueueDecisionInput() → 既存decide_disposition()ベース判定（回帰確認）")

er_5_success = make_execution_result("run-legacy-5a", make_retried_result("run-legacy-5a", overall_success=True))
decision_5a = decider.decide(er_5_success, LegacyQueueDecisionInput())
check("5. legacy+success=True → outcome=COMPLETE（6.31 semantics無変更）", decision_5a.outcome, RetryQueueUpdateOutcome.COMPLETE)

er_5_fail = make_execution_result(
    "run-legacy-5b",
    make_retried_result("run-legacy-5b", overall_success=False, steps=[make_unknown_step()]),
)
decision_5b = decider.decide(er_5_fail, LegacyQueueDecisionInput())
check("5. legacy+success=False → outcome=FAIL（6.31 semantics無変更）", decision_5b.outcome, RetryQueueUpdateOutcome.FAIL)
print()


# =====================================================================
# §28.-8 テスト5b: protected lineage、terminal_disposition未確定 → RetryQueueUpdateContractError
# =====================================================================

print("[28.-8 #5b] protected lineageでterminal_disposition未確定 → build_queue_decision_input()がContractError")

record_5b = make_record("run-5b", phase=RetryLineagePhase.TERMINAL, terminal_disposition=None, side_effect_contract_version=1)
try:
    build_queue_decision_input(record_5b)
    check_true("5b. RetryQueueUpdateContractErrorが送出される", False)
except RetryQueueUpdateContractError:
    check_true("5b. RetryQueueUpdateContractErrorが送出される（terminal_disposition未確定、legacyへ推測しない）", True)
print()


# =====================================================================
# §28.-8 テスト5c: side_effect_contract_versionがINVALID → RetryQueueUpdateContractError
# =====================================================================

print("[28.-8 #5c] side_effect_contract_version=0/負値/非int → build_queue_decision_input()がContractError")

for bad_version, label in ((0, "0"), (-1, "負値"), ("not-an-int", "非int")):
    record_5c = make_record("run-5c", side_effect_contract_version=bad_version)
    try:
        build_queue_decision_input(record_5c)
        check_true(f"5c. side_effect_contract_version={label} → RetryQueueUpdateContractError", False)
    except RetryQueueUpdateContractError:
        check_true(f"5c. side_effect_contract_version={label} → RetryQueueUpdateContractError（legacyにもprotectedにもならない）", True)
print()


# =====================================================================
# §28.-8 テスト6: restart + reconcile_all()複数回実行 → Queue/lineage整合維持
# =====================================================================

print("[28.-8 #6] restart後、HRR lineageに対しreconcile_all()を複数回実行しても状態が不変")

lineage_6, _ = make_lineage_manager()
lineage_6.create_new_lineage(
    "run-hrr-6", WorkflowMonitorRecord(
        run_id="run-hrr-6", workflow_name="workflow_engine", monitor_status=WorkflowMonitorStatus.FAILED,
        source_status="failed", source="manual", job_id="job-1",
        started_at=datetime.now(), finished_at=datetime.now(), elapsed_seconds=1.0, reason=None, steps=[],
    ),
)
claim_hrr_6 = lineage_6.claim("run-hrr-6")
lineage_6.mark_execution_started("run-hrr-6", "run-hrr-6", claim_hrr_6.owner_token)
lineage_6.mark_terminal(
    "run-hrr-6", disposition=RetryLineageDisposition.HUMAN_REVIEW_REQUIRED,
    executed_run_id="run-hrr-6", newly_confirmed_steps=[],
)


class _NoneMonitor:
    def get_status(self, run_id):
        return None


lineage_6.reconcile_all(resolve_status_fn=_NoneMonitor().get_status)
snapshot_after_1st_6 = lineage_6.peek("run-hrr-6")
lineage_6.reconcile_all(resolve_status_fn=_NoneMonitor().get_status)
snapshot_after_2nd_6 = lineage_6.peek("run-hrr-6")

check(
    "6. reconcile_all()を複数回実行してもterminal_dispositionはHUMAN_REVIEW_REQUIREDのまま",
    (snapshot_after_1st_6.terminal_disposition, snapshot_after_2nd_6.terminal_disposition),
    (RetryLineageDisposition.HUMAN_REVIEW_REQUIRED, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED),
)
check(
    "6. reconcile_all()を複数回実行してもphaseはTERMINALのまま（自動retryされない）",
    (snapshot_after_1st_6.phase, snapshot_after_2nd_6.phase),
    (RetryLineagePhase.TERMINAL, RetryLineagePhase.TERMINAL),
)

decision_after_reconcile_6 = decider.decide(
    make_execution_result("run-hrr-6", make_retried_result("run-hrr-6", overall_success=True)),
    LineageAuthoritativeDispositionInput(terminal_disposition=snapshot_after_2nd_6.terminal_disposition),
)
check(
    "6. restart後もQueue側がFAILED（lineage側HRRと整合したまま）",
    decision_after_reconcile_6.target_status, RetryQueueStatus.FAILED,
)
print()


# =====================================================================
# §28.-8 テスト7-8: resolve_final_disposition()の優先順位1（13章、既存ロジックの
#                    HRR/queue回帰確認）
# =====================================================================

print("[28.-8 #7-8] resolve_final_disposition()：優先順位1（worst_case()優先、既存13章ロジック）")

categories_all_unknown_7 = [StepOutcomeCategory.UNKNOWN]
disposition_7 = resolve_final_disposition(
    categories_all_unknown_7, SideEffectSafetyReport(entries=()),
)
check(
    "7. 全stepUNKNOWN + worst_case()=NOT_APPLICABLE(evidence無し) → FAILED（HRRにならない）",
    disposition_7, RetryLineageDisposition.FAILED,
)


class _RecordingSafetyReport:
    def __init__(self):
        self.worst_case_calls = 0

    def worst_case(self):
        self.worst_case_calls += 1
        return SideEffectSafetyCategory.IN_PROGRESS_OR_UNKNOWN


categories_all_unknown_8 = [StepOutcomeCategory.UNKNOWN]
report_8 = _RecordingSafetyReport()
disposition_8 = resolve_final_disposition(categories_all_unknown_8, report_8)
check(
    "8. あるstepUNKNOWN + worst_case()=IN_PROGRESS_OR_UNKNOWN → HUMAN_REVIEW_REQUIRED",
    disposition_8, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED,
)
check_true("8. worst_case()が呼ばれる（優先順位1の判定に使われる）", report_8.worst_case_calls >= 1)
print()


# =====================================================================
# §28.-18 テスト1-2: run_once()のexecute_dispatchable_retries()呼び出し回数・
#                     decide_retry_queue_updates()への直接伝播
# =====================================================================

print("[28.-18 #1-2] run_once(): execute_dispatchable_retries()正確に1回・"
      "decide_retry_queue_updates()へexecution_resultsをそのまま渡す")

orchestrator_source = (PROJECT_ROOT / "src" / "retry_runtime_orchestrator" / "retry_runtime_orchestrator.py").read_text(encoding="utf-8")
orchestrator_tree = ast.parse(orchestrator_source)


def _count_calls(tree, attr_name: str) -> int:
    count = 0
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == attr_name:
            count += 1
    return count


check(
    "1. run_once()ソース内でexecute_dispatchable_retries()の呼び出しがちょうど1箇所",
    _count_calls(orchestrator_tree, "execute_dispatchable_retries"), 1,
)
check_true(
    "2. run_once()ソース内で旧bypassパターン「RetryQueueUpdateDecider().decide_all(execution_results)」が存在しない",
    "RetryQueueUpdateDecider().decide_all(execution_results)" not in orchestrator_source,
)
check_true(
    "2. run_once()ソース内でself.manager.decide_retry_queue_updates(execution_results)を経由する",
    "self.manager.decide_retry_queue_updates(execution_results)" in orchestrator_source,
)
print()


# =====================================================================
# §28.-18 テスト3-4: RetryManager.decide_retry_queue_updates()がbuild_retry_queue_
#                     decision_requests()経由で1 execution_result→1 requestを構築
# =====================================================================

print("[28.-18 #3-4] decide_retry_queue_updates(): 1 execution_result → 1 request、"
      "protected lineageでLineageAuthoritativeDispositionInputが構築される")

lineage_34, _ = make_lineage_manager()
lineage_34.create_new_lineage(
    "run-34", WorkflowMonitorRecord(
        run_id="run-34", workflow_name="workflow_engine", monitor_status=WorkflowMonitorStatus.FAILED,
        source_status="failed", source="manual", job_id="job-1",
        started_at=datetime.now(), finished_at=datetime.now(), elapsed_seconds=1.0, reason=None, steps=[],
    ),
)
claim_run_34 = lineage_34.claim("run-34")
lineage_34.mark_execution_started("run-34", "run-34", claim_run_34.owner_token)
lineage_34.mark_terminal(
    "run-34", disposition=RetryLineageDisposition.HUMAN_REVIEW_REQUIRED,
    executed_run_id="run-34", newly_confirmed_steps=[],
)
record_34 = lineage_34.peek("run-34")

er_34a = make_execution_result("run-34", make_retried_result("run-34", overall_success=True))
er_34b = make_execution_result("run-legacy-34", make_retried_result("run-legacy-34", overall_success=True))
execution_results_34 = [er_34a, er_34b]

requests_34 = build_retry_queue_decision_requests(execution_results_34, lineage_34)
check("3. execution_results 2件 → RetryQueueDecisionRequest 2件", len(requests_34), 2)
check_true("3. 各requestのexecution_resultが対応するinputと同一", requests_34[0].execution_result is er_34a and requests_34[1].execution_result is er_34b)

check_true(
    "4. protected lineage(run-34) → LineageAuthoritativeDispositionInputが構築される",
    isinstance(requests_34[0].decision_input, LineageAuthoritativeDispositionInput),
)
check(
    "4. terminal_dispositionがlineageのdurable stateと一致する",
    requests_34[0].decision_input.terminal_disposition, record_34.terminal_disposition,
)
check_true(
    "8. いかなるlineageのmemberでもないrun_id(run-legacy-34) → LegacyQueueDecisionInputが明示選択される",
    isinstance(requests_34[1].decision_input, LegacyQueueDecisionInput),
)

decisions_34 = RetryManager.__new__(RetryManager)  # decide_retry_queue_updates()は
# self._lineage・self._queue_update_deciderのみに依存するため、フル構築を避けて
# 直接attributeを設定する（他コンストラクタ依存を持ち込まない単体テスト）。
decisions_34._lineage = lineage_34
decisions_34._queue_update_decider = RetryQueueUpdateDecider()
result_decisions_34 = RetryManager.decide_retry_queue_updates(decisions_34, execution_results_34)
check("3. decide_retry_queue_updates()の戻り値件数がexecution_results件数と一致", len(result_decisions_34), 2)
print()


# =====================================================================
# §28.-18 テスト5: protected lineage、terminal_disposition未確定 → ContractError（batch版）
# =====================================================================

print("[28.-18 #5] protected lineageでterminal_disposition未確定 → batch経路でもContractError")

lineage_5, _ = make_lineage_manager()
lineage_5.create_new_lineage(
    "run-b5", WorkflowMonitorRecord(
        run_id="run-b5", workflow_name="workflow_engine", monitor_status=WorkflowMonitorStatus.FAILED,
        source_status="failed", source="manual", job_id="job-1",
        started_at=datetime.now(), finished_at=datetime.now(), elapsed_seconds=1.0, reason=None, steps=[],
    ),
)
claim_run_b5 = lineage_5.claim("run-b5")
lineage_5.mark_execution_started("run-b5", "run-b5", claim_run_b5.owner_token)
# mark_terminal()を呼ばない＝terminal_disposition未確定のまま。

er_b5 = make_execution_result("run-b5", make_retried_result("run-b5", overall_success=True))
try:
    build_retry_queue_decision_requests([er_b5], lineage_5)
    check_true("5. RetryQueueUpdateContractErrorが送出される（batch経路）", False)
except RetryQueueUpdateContractError:
    check_true("5. RetryQueueUpdateContractErrorが送出される（batch経路、terminal_disposition未確定）", True)
print()


# =====================================================================
# §28.-18 テスト6: side_effect_contract_versionがINVALID → ContractError（batch版）
# =====================================================================

print("[28.-18 #6] side_effect_contract_versionが0/負値 → batch経路でもContractError")

for bad_version, label in ((0, "0"), (-1, "負値")):
    lineage_6b, _ = make_lineage_manager()
    lineage_record_6b = lineage_6b.create_new_lineage(
        f"run-b6-{label}", WorkflowMonitorRecord(
            run_id=f"run-b6-{label}", workflow_name="workflow_engine", monitor_status=WorkflowMonitorStatus.FAILED,
            source_status="failed", source="manual", job_id="job-1",
            started_at=datetime.now(), finished_at=datetime.now(), elapsed_seconds=1.0, reason=None, steps=[],
        ),
    ).lineage
    # store経由でside_effect_contract_versionを直接malformedへ書き換える
    # （create_new_lineage()自体は常に正当な値をスタンプするため、durable data
    # corruptionを模擬するには保存後に直接改変する必要がある）。
    corrupted_record_6b = lineage_record_6b
    object.__setattr__(corrupted_record_6b, "side_effect_contract_version", bad_version)
    lineage_6b._store.save(corrupted_record_6b)

    er_b6 = make_execution_result(f"run-b6-{label}", make_retried_result(f"run-b6-{label}", overall_success=True))
    try:
        build_retry_queue_decision_requests([er_b6], lineage_6b)
        check_true(f"6. side_effect_contract_version={label} → RetryQueueUpdateContractError（batch経路）", False)
    except RetryQueueUpdateContractError:
        check_true(f"6. side_effect_contract_version={label} → RetryQueueUpdateContractError（batch経路）", True)
print()


# =====================================================================
# §28.-18 テスト7: find_by_member_run_id()解決後、peek()がNoneを返す（durable data
#                    corruption模擬）→ ContractError
# =====================================================================

print("[28.-18 #7] find_by_member_run_id()解決後にpeek()がNoneを返す状況 → ContractError")


class _FakeLineageForOrphanRootRunId:
    def find_by_member_run_id(self, member_run_id):
        return "orphan-root-run-id"

    def peek(self, root_run_id):
        return None


er_7 = make_execution_result("run-7", make_retried_result("run-7", overall_success=True))
try:
    build_retry_queue_decision_requests([er_7], _FakeLineageForOrphanRootRunId())
    check_true("7. RetryQueueUpdateContractErrorが送出される（peek()がNone）", False)
except RetryQueueUpdateContractError:
    check_true("7. RetryQueueUpdateContractErrorが送出される（peek()がNone、legacyへ推測しない）", True)
print()


# =====================================================================
# §28.-18 テスト9: parallel list zip禁止の直接確認
#                    （順序入れ替え・要素数変更に対する非取り違え確認）
# =====================================================================

print("[28.-18 #9] 順序入れ替え・要素数変更したRetryQueueDecisionRequest列でも取り違えが発生しない")

er_9a = make_execution_result("run-9a", make_retried_result("run-9a", overall_success=True))
er_9b = make_execution_result(
    "run-9b", make_retried_result("run-9b", overall_success=False, steps=[make_unknown_step()]),
)

requests_order1_9 = [
    RetryQueueDecisionRequest(execution_result=er_9a, decision_input=LineageAuthoritativeDispositionInput(RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)),
    RetryQueueDecisionRequest(execution_result=er_9b, decision_input=LegacyQueueDecisionInput()),
]
requests_order2_9 = [
    RetryQueueDecisionRequest(execution_result=er_9b, decision_input=LegacyQueueDecisionInput()),
    RetryQueueDecisionRequest(execution_result=er_9a, decision_input=LineageAuthoritativeDispositionInput(RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)),
]

decisions_order1_9 = decider.decide_all(requests_order1_9)
decisions_order2_9 = decider.decide_all(requests_order2_9)

check(
    "9. 順序1: run-9a(HRR)→FAIL, run-9b(legacy+失敗)→FAIL",
    [d.outcome for d in decisions_order1_9],
    [RetryQueueUpdateOutcome.FAIL, RetryQueueUpdateOutcome.FAIL],
)
check(
    "9. 順序2（入れ替え）でも各要素は自身のexecution_result/decision_inputのみに基づく（取り違えなし）",
    [decisions_order2_9[0].execution_result is er_9b, decisions_order2_9[1].execution_result is er_9a],
    [True, True],
)
check(
    "9. 順序2のdecisions[1](run-9a、HRR)は順序1のdecisions[0]と同一結果",
    decisions_order2_9[1].outcome, decisions_order1_9[0].outcome,
)
print()


# =====================================================================
# §28.-18 テスト10: production全体でdecide_all()の呼び出し箇所監査
#                     （RetryManager.decide_retry_queue_updates()内部の1箇所のみ）
# =====================================================================

print("[28.-18 #10] production全体でRetryQueueUpdateDecider.decide_all()の直接呼び出しは"
      "RetryManager.decide_retry_queue_updates()内の1箇所のみ")


def _is_retry_queue_update_decider_receiver(receiver) -> bool:
    """receiver式が`RetryQueueUpdateDecider()`の直接構築、または
    `self._queue_update_decider`（RetryManagerが保持するRetryQueueUpdateDecider
    インスタンス、22.1d節）のいずれかであるかを判定する。
    RetryQueueCleanupDecider・RetryQueueTerminalCleanupDecider等、
    同名decide_all()を持つ別クラスのインスタンスは対象外とする。"""
    if isinstance(receiver, ast.Call) and isinstance(receiver.func, ast.Name):
        return receiver.func.id == "RetryQueueUpdateDecider"
    if isinstance(receiver, ast.Attribute):
        return receiver.attr == "_queue_update_decider"
    return False


def _find_decide_all_call_sites() -> list[str]:
    sites = []
    for py_file in list(SRC_DIR.rglob("*.py")) + list((PROJECT_ROOT / "scripts").rglob("*.py")) + list(PROJECT_ROOT.glob("*.py")):
        if "__pycache__" in py_file.parts:
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "decide_all"
                and _is_retry_queue_update_decider_receiver(node.func.value)
            ):
                sites.append(f"{py_file.relative_to(PROJECT_ROOT).as_posix()}:{node.lineno}")
    return sites


all_decide_all_sites_10 = _find_decide_all_call_sites()
retry_queue_update_decider_source = (SRC_DIR / "retry_engine" / "retry_queue_update_decider.py").read_text(encoding="utf-8")
retry_manager_source_10 = (SRC_DIR / "retry_engine" / "retry_manager.py").read_text(encoding="utf-8")

# retry_queue_update_decider.py自身のdecide_all()定義内のself.decide()呼び出しは対象外
# （decide_allメソッドの実装自体）。production productionコードから
# 「RetryQueueUpdateDecider系インスタンス.decide_all(...)」という形の外部呼び出しを
# 数える。
_external_call_sites_10 = [
    s for s in all_decide_all_sites_10
    if not s.startswith("src/retry_engine/retry_queue_update_decider.py")
]
check("10. production全体でのRetryQueueUpdateDecider系.decide_all()外部呼び出しはちょうど1箇所", len(_external_call_sites_10), 1)
check_true(
    "10. その1箇所がsrc/retry_engine/retry_manager.py内である（production direct bypass = 0）",
    bool(_external_call_sites_10) and _external_call_sites_10[0].startswith("src/retry_engine/retry_manager.py:"),
)
check_true(
    "10. self._queue_update_decider.decide_all(requests)を経由する（22.1d節の唯一のproduction entry point）",
    "self._queue_update_decider.decide_all(requests)" in retry_manager_source_10,
)
print()


# =====================================================================
# §28.-18 テスト11: HRR確定lineage → decide_retry_queue_updates()（batch）→ FAIL/FAILED
#                     （28.-8節#1-2のbatch経路統合確認）
# =====================================================================

print("[28.-18 #11] HRR確定lineage → decide_retry_queue_updates()（batch）→ FAIL/FAILED")

lineage_11, _ = make_lineage_manager()
lineage_11.create_new_lineage(
    "run-11", WorkflowMonitorRecord(
        run_id="run-11", workflow_name="workflow_engine", monitor_status=WorkflowMonitorStatus.FAILED,
        source_status="failed", source="manual", job_id="job-1",
        started_at=datetime.now(), finished_at=datetime.now(), elapsed_seconds=1.0, reason=None, steps=[],
    ),
)
claim_run_11 = lineage_11.claim("run-11")
lineage_11.mark_execution_started("run-11", "run-11", claim_run_11.owner_token)
lineage_11.mark_terminal(
    "run-11", disposition=RetryLineageDisposition.HUMAN_REVIEW_REQUIRED,
    executed_run_id="run-11", newly_confirmed_steps=[],
)

manager_stub_11 = RetryManager.__new__(RetryManager)
manager_stub_11._lineage = lineage_11
manager_stub_11._queue_update_decider = RetryQueueUpdateDecider()
er_11 = make_execution_result("run-11", make_retried_result("run-11", overall_success=True))
decisions_11 = RetryManager.decide_retry_queue_updates(manager_stub_11, [er_11])
check("11. batch経路でもHRR確定lineage → outcome=FAIL", decisions_11[0].outcome, RetryQueueUpdateOutcome.FAIL)
check("11. batch経路でもHRR確定lineage → target_status=FAILED", decisions_11[0].target_status, RetryQueueStatus.FAILED)
print()


# =====================================================================
# §28.-18 テスト12: 6.31 semantics回帰確認（SUCCEEDED→COMPLETE、
#                     FAILED/NOT_ACTIONED→FAIL、legacy/protected双方）
# =====================================================================

print("[28.-18 #12] 6.31 semantics回帰確認：SUCCEEDED→COMPLETE、FAILED/NOT_ACTIONED→FAIL")

for disposition_12, expected_outcome_12, label_12 in (
    (RetryLineageDisposition.SUCCEEDED, RetryQueueUpdateOutcome.COMPLETE, "SUCCEEDED"),
    (RetryLineageDisposition.FAILED, RetryQueueUpdateOutcome.FAIL, "FAILED"),
    (RetryLineageDisposition.NOT_ACTIONED, RetryQueueUpdateOutcome.FAIL, "NOT_ACTIONED"),
):
    er_12 = make_execution_result(f"run-12-{label_12}", make_retried_result(f"run-12-{label_12}", overall_success=True))
    decision_12 = decider.decide(er_12, LineageAuthoritativeDispositionInput(terminal_disposition=disposition_12))
    check(f"12. protected lineage, disposition={label_12} → outcome={expected_outcome_12.value}", decision_12.outcome, expected_outcome_12)
print()


# =====================================================================
# unknown queue_decision_input型 → ContractError（decide()自体のfail-closed規律）
# =====================================================================

print("[decide()自体のfail-closed] 未知のqueue_decision_input型 → RetryQueueUpdateContractError")

try:
    decider.decide(
        make_execution_result("run-unknown", make_retried_result("run-unknown", overall_success=True)),
        "not-a-valid-decision-input",
    )
    check_true("未知のqueue_decision_input型 → RetryQueueUpdateContractError", False)
except RetryQueueUpdateContractError:
    check_true("未知のqueue_decision_input型 → RetryQueueUpdateContractError", True)
print()


# =====================================================================
# 結果サマリー
# =====================================================================

print("=" * 60)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = sum(1 for status, _ in results_log if status == "FAIL")
print(f"結果: {passed} PASS / {failed} FAIL / 合計 {len(results_log)}")
if failed:
    print("失敗したテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
print("全テストPASS")
