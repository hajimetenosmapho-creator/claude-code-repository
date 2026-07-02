"""
Execution History 確認スクリプト（v2.8.0）

Workflow Engine（v2.7.0）が記録したWorkflow実行履歴（logs/execution_history/*.json）を
一覧・詳細表示する読み取り専用CLI。

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/show_execution_history.py                 # 一覧表示（新しい順）
    ./venv/Scripts/python.exe scripts/show_execution_history.py --limit 5       # 表示件数を制限（デフォルト10）
    ./venv/Scripts/python.exe scripts/show_execution_history.py --run-id <ID>   # 指定run_idの詳細表示

注意:
    - EXECUTION_HISTORY_ENABLED=false（記録無効）の場合でも、過去に記録済みの履歴を
      閲覧できるようにするため、本スクリプトは is_ready() のチェックをスキップし、
      history_dir を直接読み取る（docs/design/execution_history_foundation.md 8章）。
    - 本スクリプトは読み取り専用。履歴の作成・更新・削除は一切行わない。
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from execution_history import ExecutionHistoryConfig, JsonExecutionHistoryStore, WorkflowExecutionRecord


def print_summary(record: WorkflowExecutionRecord) -> None:
    print(
        f"  run_id={record.run_id}  status={record.status.value:<8}"
        f"  source={record.source:<10}  job_id={record.job_id}"
    )
    print(f"    started_at={record.started_at.isoformat()}  finished_at={record.finished_at.isoformat() if record.finished_at else '(未完了)'}")


def print_detail(record: WorkflowExecutionRecord) -> None:
    print("=" * 50)
    print(f"run_id       : {record.run_id}")
    print(f"workflow_name: {record.workflow_name}")
    print(f"status       : {record.status.value}")
    print(f"source       : {record.source}")
    print(f"job_id       : {record.job_id}")
    print(f"started_at   : {record.started_at.isoformat()}")
    print(f"finished_at  : {record.finished_at.isoformat() if record.finished_at else '(未完了)'}")
    if record.error_message:
        print(f"error_message: {record.error_message}")
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

    print()
    print("events:")
    for event in record.events:
        print(f"  - [{event.occurred_at.isoformat()}] {event.event_type}: {event.message}")


def main():
    parser = argparse.ArgumentParser(description="Execution History 確認スクリプト（v2.8.0）")
    parser.add_argument("--run-id", default=None, metavar="RUN_ID", help="指定run_idの詳細を表示する")
    parser.add_argument("--limit", type=int, default=10, help="一覧表示の件数（デフォルト10）")
    args = parser.parse_args()

    base_dir = Path(__file__).parent.parent
    config = ExecutionHistoryConfig.from_env(project_root=base_dir)
    store = JsonExecutionHistoryStore(config.history_dir)

    if args.run_id is not None:
        record = store.get(args.run_id)
        if record is None:
            print(f"[情報] run_id '{args.run_id}' の履歴は見つかりませんでした。")
            return
        print_detail(record)
        return

    records = store.list_all()
    if not records:
        print("[情報] 履歴がありません。")
        print(f"  保存先: {config.history_dir}")
        return

    print("=" * 50)
    print(f"Execution History 一覧（新しい順、最大{args.limit}件）")
    print("=" * 50)
    for record in records[: args.limit]:
        print_summary(record)


if __name__ == "__main__":
    main()
