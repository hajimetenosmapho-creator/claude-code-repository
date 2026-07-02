"""
Workflow Monitor 確認スクリプト（v2.9.0）

Execution History（v2.8.0、logs/execution_history/*.json）を読み取り、Workflow Monitor
（v2.9.0）が判定した監視状態（RUNNING/SUCCESS/FAILED/TIMEOUT）を一覧・詳細表示する
読み取り専用CLI。

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/show_workflow_status.py                 # 一覧表示（新しい順）
    ./venv/Scripts/python.exe scripts/show_workflow_status.py --limit 5       # 表示件数を制限（デフォルト10）
    ./venv/Scripts/python.exe scripts/show_workflow_status.py --run-id <ID>   # 指定run_idの詳細表示

注意:
    - 本スクリプトは WORKFLOW_MONITOR_ENABLED のゲート判定をスキップし、常に判定結果を
      表示する。Workflow Monitorは読み取り専用で副作用を一切持たないため、
      show_execution_history.py（v2.8.0）と同じ「読み取りと書き込みのゲート分離」の
      考え方を踏襲する（docs/design/workflow_monitor_foundation.md 7章）。
    - 本スクリプトは読み取り専用。Execution History・Workflow Engineへの書き込みは
      一切行わない。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from execution_history import ExecutionHistoryConfig, JsonExecutionHistoryStore
from workflow_monitor import WorkflowMonitor, WorkflowMonitorConfig, WorkflowMonitorRecord


def print_summary(record: WorkflowMonitorRecord) -> None:
    print(
        f"  run_id={record.run_id}  monitor_status={record.monitor_status.value:<8}"
        f"  (source_status={record.source_status})  source={record.source:<10}  job_id={record.job_id}"
    )
    print(
        f"    started_at={record.started_at.isoformat()}"
        f"  finished_at={record.finished_at.isoformat() if record.finished_at else '(未完了)'}"
        f"  elapsed={record.elapsed_seconds:.1f}秒"
    )
    if record.reason:
        print(f"    reason: {record.reason}")


def print_detail(record: WorkflowMonitorRecord) -> None:
    print("=" * 50)
    print(f"run_id         : {record.run_id}")
    print(f"workflow_name  : {record.workflow_name}")
    print(f"monitor_status : {record.monitor_status.value}")
    print(f"source_status  : {record.source_status}")
    print(f"source         : {record.source}")
    print(f"job_id         : {record.job_id}")
    print(f"started_at     : {record.started_at.isoformat()}")
    print(f"finished_at    : {record.finished_at.isoformat() if record.finished_at else '(未完了)'}")
    print(f"elapsed_seconds: {record.elapsed_seconds:.1f}")
    if record.reason:
        print(f"reason         : {record.reason}")
    print("=" * 50)

    print("steps:")
    for step in record.steps:
        print(f"  - step={step.step:<10} status={step.status.value}")
        print(f"      started_at={step.started_at.isoformat() if step.started_at else '-'}"
              f"  finished_at={step.finished_at.isoformat() if step.finished_at else '-'}")
        if step.skipped_reason:
            print(f"      skipped_reason: {step.skipped_reason}")
        if step.error_message:
            print(f"      error_message: {step.error_message}")


def main():
    parser = argparse.ArgumentParser(description="Workflow Monitor 確認スクリプト（v2.9.0）")
    parser.add_argument("--run-id", default=None, metavar="RUN_ID", help="指定run_idの監視状態を詳細表示する")
    parser.add_argument("--limit", type=int, default=10, help="一覧表示の件数（デフォルト10）")
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent
    execution_history_config = ExecutionHistoryConfig.from_env(project_root=base_dir)
    workflow_monitor_config = WorkflowMonitorConfig.from_env()

    store = JsonExecutionHistoryStore(execution_history_config.history_dir)
    monitor = WorkflowMonitor(store=store, config=workflow_monitor_config)

    if args.run_id is not None:
        record = monitor.get_status(args.run_id)
        if record is None:
            print(f"[情報] run_id '{args.run_id}' の履歴は見つかりませんでした。")
            return
        print_detail(record)
        return

    records = monitor.list_status(limit=args.limit)
    if not records:
        print("[情報] 履歴がありません。")
        print(f"  保存先: {execution_history_config.history_dir}")
        return

    print("=" * 50)
    print(f"Workflow Monitor 一覧（新しい順、最大{args.limit}件）")
    print("=" * 50)
    for record in records:
        print_summary(record)


if __name__ == "__main__":
    main()
