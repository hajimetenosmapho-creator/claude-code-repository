"""
JSON Execution History Store（v2.8.0、Release 6.30でatomic save化）

JsonExecutionHistoryStore: WorkflowExecutionRecordをJSONファイルへ保存する実装

設計方針:
    - 1実行（1 run_id）= 1 JSONファイル（{history_dir}/{run_id}.json）とする。
    - start_run/start_step/finish_step/finish_run のたびに同じファイルを毎回上書き保存する。
      これにより、実行途中でプロセスが異常終了した場合でも「RUNNINGのまま止まった記録」が
      残る（docs/design/execution_history_foundation.md 5章「失敗時にも履歴が残る構成」）。
    - 読み込み失敗（壊れたJSON）はそのファイルのみスキップし、警告を出力する。

Release 6.30での変更（docs/design/production_canonical_run_outcome_contract_foundation.md 22章）:
    - save() は bool（acknowledged）を返す。tempfile.mkstemp → write → flush → fsync →
      close → os.replace のatomic writeへ変更した。
    - os.fdopen() 自体が失敗した場合は、file objectへownershipが移っていないため
      raw fdをbest-effort closeする（os.fdopen成功後のwith文経路とは排他的、二重closeなし）。
    - 失敗時はfdのcloseとtemp fileのbest-effort unlinkを保証する。cleanup自体の失敗は
      戻り値（ack）を変更しない。
    - Invariant：`.json` 拡張子を持つのはcanonical History recordだけ。tempファイルは
      `.{run_id}.{unique}.tmp` 命名とし、list_all() の既存 glob("*.json") から
      構造的に除外される。
"""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from .execution_history_store import ExecutionHistoryStore
from .workflow_execution_record import WorkflowExecutionRecord


class JsonExecutionHistoryStore(ExecutionHistoryStore):
    """{history_dir}/{run_id}.json へJSON形式でatomicに保存する実装。"""

    def __init__(self, history_dir: Path):
        self._history_dir = history_dir

    def _path_for(self, run_id: str) -> Path:
        return self._history_dir / f"{run_id}.json"

    def save(self, record: WorkflowExecutionRecord) -> bool:
        try:
            self._history_dir.mkdir(parents=True, exist_ok=True)
            fd, tmp_path_str = tempfile.mkstemp(
                prefix=f".{record.run_id}.", suffix=".tmp", dir=str(self._history_dir)
            )
        except OSError as e:
            print(f"  [EXECUTION HISTORY WARNING] 履歴保存に失敗しました（処理は継続します）: {e}")
            return False

        tmp_path = Path(tmp_path_str)
        try:
            try:
                f = os.fdopen(fd, "w", encoding="utf-8")
            except OSError as e:
                # os.fdopen() 自体の失敗：file objectへownershipが移っていないため、
                # raw fdを自前でbest-effort closeする（以降の with f: 経路とは排他的）。
                try:
                    os.close(fd)
                except OSError:
                    pass
                print(f"  [EXECUTION HISTORY WARNING] 履歴保存に失敗しました（処理は継続します）: {e}")
                return False

            try:
                with f:
                    # 以降、fd closeはfile objectの __exit__ が保証する。os.close(fd)を重ねない。
                    f.write(record.to_json())
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as e:
                print(f"  [EXECUTION HISTORY WARNING] 履歴保存に失敗しました（処理は継続します）: {e}")
                return False

            try:
                os.replace(tmp_path, self._path_for(record.run_id))
            except OSError as e:
                print(f"  [EXECUTION HISTORY WARNING] 履歴保存に失敗しました（処理は継続します）: {e}")
                return False

            return True
        finally:
            # best-effort cleanup。cleanup失敗はackを一切変更しない（returnは既に確定済み）
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

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
