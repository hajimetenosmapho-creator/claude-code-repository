"""
JSON Execution History Store（v2.8.0）

JsonExecutionHistoryStore: WorkflowExecutionRecordをJSONファイルへ保存する最小実装

設計方針:
    - 1実行（1 run_id）= 1 JSONファイル（{history_dir}/{run_id}.json）とする。
    - start_run/start_step/finish_step/finish_run のたびに同じファイルを毎回上書き保存する。
      これにより、実行途中でプロセスが異常終了した場合でも「RUNNINGのまま止まった記録」が
      残る（docs/design/execution_history_foundation.md 5章「失敗時にも履歴が残る構成」）。
    - 書き込み失敗時（OSError）は警告を出力して処理を継続する。src/logger/log_manager.py
      の _append() と同じ方針（同設計書9章）：履歴記録の失敗がWorkflow本体の成否に
      影響してはならない。
    - 読み込み失敗（壊れたJSON）はそのファイルのみスキップし、警告を出力する。
"""
from __future__ import annotations

import json
from pathlib import Path

from .execution_history_store import ExecutionHistoryStore
from .workflow_execution_record import WorkflowExecutionRecord


class JsonExecutionHistoryStore(ExecutionHistoryStore):
    """{history_dir}/{run_id}.json へJSON形式で保存する最小実装。"""

    def __init__(self, history_dir: Path):
        self._history_dir = history_dir

    def _path_for(self, run_id: str) -> Path:
        return self._history_dir / f"{run_id}.json"

    def save(self, record: WorkflowExecutionRecord) -> None:
        try:
            self._history_dir.mkdir(parents=True, exist_ok=True)
            self._path_for(record.run_id).write_text(record.to_json(), encoding="utf-8")
        except OSError as e:
            print(f"  [EXECUTION HISTORY WARNING] 履歴保存に失敗しました（処理は継続します）: {e}")

    def get(self, run_id: str) -> WorkflowExecutionRecord | None:
        path = self._path_for(run_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return WorkflowExecutionRecord.from_dict(data)
        except (OSError, ValueError, KeyError) as e:
            print(f"  [EXECUTION HISTORY WARNING] 履歴読み込みに失敗しました（{path.name}）: {e}")
            return None

    def list_all(self) -> list[WorkflowExecutionRecord]:
        if not self._history_dir.exists():
            return []

        records: list[WorkflowExecutionRecord] = []
        for path in sorted(self._history_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                records.append(WorkflowExecutionRecord.from_dict(data))
            except (OSError, ValueError, KeyError) as e:
                print(f"  [EXECUTION HISTORY WARNING] 履歴読み込みに失敗しました（{path.name}）: {e}")

        records.sort(key=lambda r: r.started_at, reverse=True)
        return records
