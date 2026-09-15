"""
Scheduler Driver 実行スクリプト（v6.34.0、Release 6.34）

Approved Architecture: docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md

ProductionScheduleSource（唯一のproduction Job定義供給元） -> SchedulerEngine.evaluate()
（無改修） -> Design Decision J filter（retry候補除外） -> SchedulerDispatchLedger経由の
fail-closed claim -> WorkflowEngineManager.run()（dispatch） -> confirm() という一連の
サイクルを、単発またはloopで駆動するCLIエントリスクリプト。

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/run_scheduler_driver.py
    ./venv/Scripts/python.exe scripts/run_scheduler_driver.py --loop
    ./venv/Scripts/python.exe scripts/run_scheduler_driver.py --loop --interval-seconds 30

前提条件（.env設定、三重ゲート）:
    SCHEDULER_DRIVER_ENABLED=true（本Driver自身のゲート）
    AI_AGENT_ENABLED=true
    WORKFLOW_ENGINE_ENABLED=true

Single-Active-Driver制約（12章）:
    実行開始時、`<project_root>/.run/scheduler_driver.lock` の排他生成を試みる
    （RetryRuntimeLockをそのまま再利用、コード変更ゼロ）。既に別プロセスが実行中の
    場合、CompositionRoot等は一切構築せずRetryRuntimeLockErrorが送出されエラー終了する。

Lock Lifecycle Contract（12.2章）:
    lock.release() を直接呼び出すコードは、本スクリプトの _release_if_owned()
    呼び出し（finally節、ただ1箇所）に限定する。acquire() 直後・本体処理より前に
    ownership自己検証を行い（try節の最初の文）、finally節でも release 直前に必ず
    再検証する。検証に失敗した場合（Lock Integrity Violation）は release をスキップし、
    他プロセスの正当なlockを誤って削除しない。

Retry Runtimeとの関係（14章）:
    Scheduler DriverとRetry Runtimeは、lock・durable state・dispatch対象のいずれも
    完全に独立した2プロセスである。本スクリプトは scripts/run_retry_runtime.py と
    同時に実行してよい（互いのlockに干渉しない）。record-level非衝突は保証するが、
    content-level idempotencyは対象外（14.1章、既存Post-MVP `duplicate_filter`
    項目へ委ねる）。

Exit Code Policy:
    - 正常終了・gate OFF・二重起動拒否のいずれも、既存 scripts/run_retry_runtime.py /
      scripts/run_workflow_engine.py の慣例を踏襲する（正常系0、lock取得失敗1）。
    - Loop実行中のKeyboardInterrupt・停止シグナル（SIGINT/SIGTERM/SIGBREAK）は、
      既存RetryRuntimeShutdownの契約通り、意図的な正常停止として扱う（exit code 0）。
"""
import os
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent

sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from retry_runtime_lock import RetryRuntimeLock, RetryRuntimeLockError
from retry_runtime_loop import RetryRuntimeLoop
from retry_runtime_shutdown import RetryRuntimeShutdown
from scheduler_driver import (
    LockIntegrityViolationError,
    SchedulerDriverCompositionRoot,
    SchedulerDriverConfig,
    SchedulerDriverOrchestrator,
    SchedulerDriverStoreInitializationError,
    _release_if_owned,
    _verify_lock_ownership,
)
from workflow_engine import NullWorkflowEngineManager


def format_summary(result) -> str:
    """SchedulerDriverCycleResult 1回分の実行結果を、人間向けのサマリー文字列に変換する。"""
    lines = [
        "=" * 50,
        "Scheduler Driver 実行結果",
        "=" * 50,
        f"  Dispatched      : {len(result.dispatched)}",
        f"  Skipped         : {len(result.skipped)}",
        f"  Reconcile       : recovery_marked={result.recovery_marked}",
    ]
    for outcome in result.dispatched:
        lines.append(f"    [DISPATCHED] {outcome.event_identity} -> {outcome.reason}")
    for outcome in result.skipped:
        lines.append(f"    [SKIPPED]    {outcome.event_identity}: {outcome.reason}")
    lines.append("=" * 50)
    return "\n".join(lines)


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(
        description="Scheduler Driver 実行スクリプト（v6.34.0、production workflowの定期駆動）"
    )
    parser.add_argument("--loop", action="store_true", default=False)
    parser.add_argument("--interval-seconds", type=float, default=None)
    args = parser.parse_args()

    if args.interval_seconds is not None and not args.loop:
        parser.error("--interval-seconds can only be used together with --loop")
    if args.loop and args.interval_seconds is not None and args.interval_seconds <= 0:
        parser.error("--interval-seconds must be greater than 0")

    interval_seconds = None
    if args.loop:
        interval_seconds = args.interval_seconds if args.interval_seconds is not None else 60.0

    # SCHEDULER_DRIVER_ENABLEDゲート：lock取得・CompositionRoot構築のいずれよりも前に確認する
    # （scripts/run_workflow_engine.pyのNullWorkflowEngineManager早期returnパターンを踏襲）。
    driver_config = SchedulerDriverConfig.from_env()
    if not driver_config.is_ready():
        print("[情報] Scheduler Driverが無効です（SCHEDULER_DRIVER_ENABLED=true が必要です）。")
        return 0

    lock_path = _PROJECT_ROOT / ".run" / "scheduler_driver.lock"
    lock = RetryRuntimeLock(lock_path=lock_path)
    try:
        lock.acquire()
    except RetryRuntimeLockError as e:
        print(f"[ERROR] {e}")
        return 1

    own_pid = os.getpid()
    try:
        # 12.1章タイミング1：起動時ownership自己検証はtryブロックの内側・本体処理より前
        # （finally節の保護を受けるため。検証自体が予期せず失敗してもlockがleakしない）。
        if not _verify_lock_ownership(lock_path, own_pid):
            raise LockIntegrityViolationError(lock_path, own_pid)

        print("=" * 50)
        if args.loop:
            print(f"Scheduler Driver 開始（Loop実行、interval_seconds={interval_seconds}）")
        else:
            print("Scheduler Driver 開始（1サイクルのみ実行）")
        print("=" * 50)
        print()

        try:
            root = SchedulerDriverCompositionRoot.from_env(_PROJECT_ROOT)
        except SchedulerDriverStoreInitializationError as e:
            print(f"[ERROR] {e}")
            return 1

        if isinstance(root.workflow_engine_manager, NullWorkflowEngineManager):
            print("[情報] Workflow Engineが無効です。")
            print(
                "  AI_AGENT_ENABLED=true と WORKFLOW_ENGINE_ENABLED=true を"
                " .env に設定してください（二重ゲート）。"
            )
            return 0

        orchestrator = SchedulerDriverOrchestrator(
            scheduler_engine=root.scheduler_engine,
            schedule_source=root.schedule_source,
            ledger=root.ledger,
            workflow_engine_manager=root.workflow_engine_manager,
            lock_path=lock_path,
            own_pid=own_pid,
        )

        def run_cycle():
            result = orchestrator.run_once()
            print(format_summary(result))
            return result

        if not args.loop:
            run_cycle()
            return 0

        shutdown = RetryRuntimeShutdown()
        shutdown.install()
        loop = RetryRuntimeLoop(
            run_once_fn=run_cycle,
            sleep_fn=shutdown.interruptible_sleep,
            should_continue_fn=shutdown.should_continue,
            interval_seconds=interval_seconds,
        )
        try:
            loop.run()
        except KeyboardInterrupt:
            print("Scheduler driver loop stopped.")
            return 0
        if shutdown.requested:
            print(f"Scheduler driver loop stopped by signal ({shutdown.signal_name}).")
        return 0
    finally:
        # 12.2章 Lock Lifecycle Contract：正常完了・Graceful Shutdown・run_once()由来の
        # 例外（LockIntegrityViolationError含む）・予期しない例外・BaseException
        # （KeyboardInterrupt/SystemExit）のいずれの経路でも、release可否の判定は
        # この1箇所（_release_if_owned()）に集約する。
        _release_if_owned(lock, own_pid)


if __name__ == "__main__":
    sys.exit(main())
