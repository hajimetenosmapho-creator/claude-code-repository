"""
T10: F2用lock所有権付与ハーネス（Scenario F2、単一worker subprocess）。

docs/design/mvp_end_to_end_hardening_validation.md 13.2節の確定設計を実装する
test-only worker。`SchedulerDriverCompositionRoot`/CLIスクリプトを経由せず、
`SchedulerDriverOrchestrator`をtest-onlyコードから直接構築し、固定
`ClockProvider`実装と`TriggerType.ONCE`の決定的Job定義を注入する
（production/script変更ゼロ）。`RetryRuntimeLock.acquire()`をtest-onlyコード
から明示的に呼び、`own_pid`/`lock_path`を渡す（lock所有権契約の明示）。

起動引数（sys.argv）:
    argv[1]: Disposable Project Copy rootの絶対パス
    argv[2]: lock file の絶対パス
    argv[3]: 固定now（"YYYY-MM-DDTHH:MM"形式、TriggerType.ONCEのschedule文字列と一致させる）
    argv[4]: 同一プロセス内でrun_once()を呼ぶ回数（same-minute tick検証用、通常1）
    argv[5]: job_id
    argv[6]: 結果JSON出力先の絶対パス

dispatch ledger dirは、argvではなく既存の環境変数`SCHEDULER_DISPATCH_LEDGER_DIR`
（`SchedulerDispatchLedgerConfig.from_env(project_root)`、13.2節）経由で
worker起動時envから受け取る（Post-Codex-delta-review Amendment、Major#4
対応：13.2節が明示する「既存の環境変数を2回、同じ値で設定するだけで足りる」
という契約どおりに、direct dataclass構築ではなくfrom_env()を使う）。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path


def main() -> int:
    disposable_copy_root = Path(sys.argv[1]).resolve()
    lock_path = Path(sys.argv[2])
    fixed_now_str = sys.argv[3]
    tick_count = int(sys.argv[4])
    job_id = sys.argv[5]
    result_path = Path(sys.argv[6])

    expected_src = (disposable_copy_root / "src").resolve()
    sys.path.insert(0, str(expected_src))

    from ai import AgentConfig
    from workflow_engine import NullWorkflowEngineManager, WorkflowEngineConfig, WorkflowEngineManager
    from scheduler import ClockProvider, SchedulerEngine, SchedulerJob, TriggerType
    from scheduler_dispatch_ledger import SchedulerDispatchLedger, SchedulerDispatchLedgerConfig
    from scheduler_dispatch_ledger.scheduler_dispatch_ledger_store import JsonSchedulerDispatchLedgerStore
    from scheduler_driver import SchedulerDriverOrchestrator
    from retry_runtime_lock import RetryRuntimeLock, RetryRuntimeLockError

    class _FixedScheduleSource:
        def __init__(self, jobs):
            self._jobs = list(jobs)

        def jobs(self):
            return list(self._jobs)

    class _FixedClockProvider(ClockProvider):
        def __init__(self, fixed_now: datetime):
            self._fixed_now = fixed_now

        def now(self) -> datetime:
            return self._fixed_now

    agent_config = AgentConfig.from_env(base_dir=disposable_copy_root)
    workflow_engine_config = WorkflowEngineConfig.from_env(project_root=disposable_copy_root)
    manager = WorkflowEngineManager.from_config(agent_config, workflow_engine_config)
    if isinstance(manager, NullWorkflowEngineManager):
        print("fail-closed: WorkflowEngineManager gate is closed", file=sys.stderr)
        return 93

    fixed_now = datetime.strptime(fixed_now_str, "%Y-%m-%dT%H:%M")
    job = SchedulerJob(job_id=job_id, name="Scenario F2 Job", trigger_type=TriggerType.ONCE, schedule=fixed_now_str)
    schedule_source = _FixedScheduleSource([job])
    scheduler_engine = SchedulerEngine()
    # ── Major#4対応：SCHEDULER_DISPATCH_LEDGER_DIR環境変数（worker起動時env
    # 経由で親テストが設定する）からfrom_env()でledger_configを構築する。
    # direct dataclass構築は行わない（13.2節の契約どおり）。 ─────────────
    ledger_config = SchedulerDispatchLedgerConfig.from_env(disposable_copy_root)
    ledger = SchedulerDispatchLedger(JsonSchedulerDispatchLedgerStore(ledger_config.store_dir), ledger_config)
    clock = _FixedClockProvider(fixed_now)

    lock = RetryRuntimeLock(lock_path)
    try:
        lock.acquire()
    except RetryRuntimeLockError as e:
        print(f"fail-closed: lock contention: {e}", file=sys.stderr)
        return 1

    ticks = []
    try:
        import os as _os

        orchestrator = SchedulerDriverOrchestrator(
            scheduler_engine=scheduler_engine,
            schedule_source=schedule_source,
            ledger=ledger,
            workflow_engine_manager=manager,
            lock_path=lock_path,
            own_pid=_os.getpid(),
            clock=clock,
        )
        for _ in range(tick_count):
            cycle = orchestrator.run_once()
            ticks.append(
                {
                    "dispatched": [
                        {"event_identity": d.event_identity, "job_id": d.job_id, "dispatched": d.dispatched, "reason": d.reason, "run_id": d.run_id}
                        for d in cycle.dispatched
                    ],
                    "skipped": [
                        {"event_identity": d.event_identity, "job_id": d.job_id, "dispatched": d.dispatched, "reason": d.reason, "run_id": d.run_id}
                        for d in cycle.skipped
                    ],
                    "recovery_marked": cycle.recovery_marked,
                }
            )
    finally:
        lock.release()

    result_path.write_text(json.dumps({"ticks": ticks}, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
