"""
E2E テスト: Release 6.35 Scenario E — Runtime restart → attempt/terminal
state維持・再投入安全（Sub-case E1・E2）

Source of Truth:
    docs/design/mvp_end_to_end_hardening_validation.md 12章
    （12.1節`_reconcile_all_locked()`再確認結果・12.2節E1/E2確定設計）。

E1・E2はいずれも`RetryLineageManager.reconcile_all()`という単一の公開APIの
直接呼び出しのみで完結する（main.py実subprocess・Local Stub・Disposable
Project Copyはいずれも不要）。fixture構築パターンは
`tests/test_e2e_v6_31_0_retry_lineage_eligibility_durable_attempt_state.py`
の既存idiom（RetryLineageConfig直接構築・JsonRetryLineageStore・FakePolicy）
をそのまま踏襲する。production source（src/）は一切変更しない。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_35_5_scenario_e_runtime_restart.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

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
    check(label, bool(value), True)


def check_false(label: str, value: bool):
    check(label, bool(value), False)


print("=" * 60)
print("Release 6.35 Scenario E: Runtime restart -> attempt/terminal state維持")
print("=" * 60)
print()

from retry_lineage import (  # noqa: E402
    JsonRetryLineageStore,
    RetryLineageConfig,
    RetryLineageDisposition,
    RetryLineageManager,
    RetryLineagePhase,
)
from retry_lineage.retry_lineage_record import (  # noqa: E402
    RetryAttemptExecutionScope,
    RetryLineageRecord,
)
from workflow_engine import ALL_WORKFLOW_ENGINE_STEPS  # noqa: E402
from execution_history.step_execution_record import (  # noqa: E402
    StepExecutionRecord,
    StepExecutionStatus,
)
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus  # noqa: E402

tmp_dirs: list[Path] = []


class _FakePolicy:
    target_statuses = frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT})
    max_attempts = 5

    def should_retry(self, monitor_status, attempt) -> bool:
        return monitor_status in self.target_statuses and attempt < self.max_attempts


def make_lineage_manager() -> tuple[RetryLineageManager, JsonRetryLineageStore]:
    tmp_root = Path(tempfile.mkdtemp())
    tmp_dirs.append(tmp_root)
    config = RetryLineageConfig(enabled=True, lineage_dir=tmp_root)
    store = JsonRetryLineageStore(config.store_dir)
    manager = RetryLineageManager(store=store, config=config, policy=_FakePolicy())
    return manager, store


def make_monitor_record(run_id: str, status: WorkflowMonitorStatus, steps=None) -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=status,
        source_status=status.value, source="manual", job_id="job-e",
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None,
        steps=steps or [],
    )


def make_step(step_value: str, status: StepExecutionStatus) -> StepExecutionRecord:
    return StepExecutionRecord(step=step_value, status=status, started_at=None, finished_at=datetime.now())


ALL_STEP_VALUES = [s.value for s in ALL_WORKFLOW_ENGINE_STEPS]


# =====================================================================
# Sub-case E1: 意図的に未解決のまま残るケース（RUNNINGはスキップされる）
# =====================================================================
print("[E1] EXECUTION_STARTED + monitor RUNNING -> no-op（意図的に未解決）")

lineage_e1, store_e1 = make_lineage_manager()
run_id_e1 = "run-e1"
now_e1 = datetime.now()
record_e1 = RetryLineageRecord(
    root_run_id=run_id_e1,
    parent_run_id=None,
    latest_run_id=run_id_e1,
    attempt_count=1,
    max_attempts=3,
    next_attempt_ordinal=1,
    phase=RetryLineagePhase.EXECUTION_STARTED,
    terminal_disposition=None,
    next_eligible_at=None,
    owner_token=None,
    steps_confirmed_done=[],
    attempt_scopes=[
        RetryAttemptExecutionScope(
            attempt_no=1, steps_confirmed_done_before=[], steps_to_execute=list(ALL_STEP_VALUES),
            determined_at=now_e1,
        )
    ],
    created_at=now_e1,
    updated_at=now_e1,
)
store_e1.save(record_e1)

monitor_e1 = make_monitor_record(run_id_e1, WorkflowMonitorStatus.RUNNING)
summary_e1 = lineage_e1.reconcile_all(resolve_status_fn=lambda rid: monitor_e1 if rid == run_id_e1 else None)

check_false("E1-1. skipped=False（lockは占有されていない）", summary_e1.skipped)
check("E1-2. resolved_count=0（RUNNINGはスキップされmark_terminal()されない）", summary_e1.resolved_count, 0)
check("E1-3. opened_count=0", summary_e1.opened_count, 0)
check("E1-4. released_count=0", summary_e1.released_count, 0)

final_e1 = lineage_e1.peek(run_id_e1)
check("E1-5. phaseはEXECUTION_STARTEDのまま変更されない", final_e1.phase, RetryLineagePhase.EXECUTION_STARTED)
check("E1-6. attempt_countは1のまま不変", final_e1.attempt_count, 1)
check("E1-7. terminal_dispositionはNoneのまま（mark_terminal()が呼ばれていない証拠）", final_e1.terminal_disposition, None)
print()


# =====================================================================
# Sub-case E2: legacy lineageで実際に解決されるケース
# =====================================================================
print("[E2] EXECUTION_STARTED + monitor FAILED(legacy) -> resolved & reopened")

lineage_e2, store_e2 = make_lineage_manager()
run_id_e2 = "run-e2"
now_e2 = datetime.now()
record_e2 = RetryLineageRecord(
    root_run_id=run_id_e2,
    parent_run_id=None,
    latest_run_id=run_id_e2,
    attempt_count=1,
    max_attempts=2,
    next_attempt_ordinal=1,
    phase=RetryLineagePhase.EXECUTION_STARTED,
    terminal_disposition=None,
    next_eligible_at=None,
    owner_token=None,
    steps_confirmed_done=[],
    attempt_scopes=[
        RetryAttemptExecutionScope(
            attempt_no=1, steps_confirmed_done_before=[], steps_to_execute=list(ALL_STEP_VALUES),
            determined_at=now_e2,
        )
    ],
    created_at=now_e2,
    updated_at=now_e2,
    side_effect_contract_version=None,  # legacy lineage（12.2節の確定選択）
)
store_e2.save(record_e2)

monitor_e2 = make_monitor_record(
    run_id_e2,
    WorkflowMonitorStatus.FAILED,
    steps=[
        make_step("news", StepExecutionStatus.FAILED),
        make_step("review", StepExecutionStatus.NOT_REACHED),
        make_step("publish", StepExecutionStatus.NOT_REACHED),
    ],
)
summary_e2 = lineage_e2.reconcile_all(resolve_status_fn=lambda rid: monitor_e2 if rid == run_id_e2 else None)

check_false("E2-1. skipped=False", summary_e2.skipped)
check("E2-2. resolved_count=1（NEWS FAILED->RETRYABLE_FAILURE->disposition=FAILED->mark_terminal）", summary_e2.resolved_count, 1)
check("E2-3. opened_count=1（同一reconcile呼び出し内でopen_next_attempt()まで進む）", summary_e2.opened_count, 1)
check("E2-4. released_count=0", summary_e2.released_count, 0)

final_e2 = lineage_e2.peek(run_id_e2)
check("E2-5. phaseはREADY_ELIGIBLEへ遷移する", final_e2.phase, RetryLineagePhase.READY_ELIGIBLE)
check("E2-6. terminal_dispositionはクリアされNoneに戻る", final_e2.terminal_disposition, None)
check("E2-7. attempt_countは1のまま不変（open_next_attempt()は変更しない）", final_e2.attempt_count, 1)
check("E2-8. next_attempt_ordinalは2へ進む", final_e2.next_attempt_ordinal, 2)
check("E2-9. attempt_scopesに新しいattempt_no=2が追加される", [s.attempt_no for s in final_e2.attempt_scopes], [1, 2])
check(
    "E2-10. 新attempt_scopeのsteps_to_executeは3step全てを含む（steps_confirmed_doneが空のため）",
    sorted(final_e2.attempt_scopes[-1].steps_to_execute),
    sorted(ALL_STEP_VALUES),
)
print()


# =====================================================================
# 後始末
# =====================================================================
for d in tmp_dirs:
    shutil.rmtree(d, ignore_errors=True)


print("=" * 60)
passed = sum(1 for s, _ in results_log if s == "PASS")
failed = sum(1 for s, _ in results_log if s == "FAIL")
print(f"結果: {passed} PASS / {failed} FAIL / 合計 {len(results_log)}")
if failed:
    print("失敗したテスト:")
    for s, label in results_log:
        if s == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
print("全テストPASS")
