"""
Retry Lineage Store（v6.31.0、Release 6.31）

RetryLineageStore:     RetryLineageRecordの永続化方式を抽象化するインターフェース
JsonRetryLineageStore: {store_dir}/{root_run_id}.json へJSON形式でatomicに保存する実装

設計方針（docs/design/retry_lineage_eligibility_durable_attempt_state.md 6章）:
    - Execution Historyとは別の、root_run_idキーの独立したminimal durable Retry
      Control Store。1 lineage = 1 JSONファイル。
    - atomic save契約は6.30の JsonExecutionHistoryStore（execution_history）を
      踏襲する（tempfile.mkstemp → write → flush → fsync → close → os.replace）。
"""
from __future__ import annotations

import json
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

from .retry_lineage_record import RetryLineageRecord


class RetryLineageStore(ABC):
    """RetryLineageRecordの永続化方式を抽象化するインターフェース。"""

    @abstractmethod
    def save(self, record: RetryLineageRecord) -> bool:
        """recordをroot_run_idで保存する（新規・上書き両対応）。保存に成功したか
        （acknowledged）を返す。"""
        ...

    @abstractmethod
    def get(self, root_run_id: str) -> RetryLineageRecord | None:
        """root_run_idに対応するrecordを返す。存在しない場合はNoneを返す。"""
        ...

    @abstractmethod
    def list_all(self) -> list[RetryLineageRecord]:
        """保存されているすべてのrecordを返す。"""
        ...


class JsonRetryLineageStore(RetryLineageStore):
    """{store_dir}/{root_run_id}.json へJSON形式でatomicに保存する実装。"""

    def __init__(self, store_dir: Path):
        self._store_dir = store_dir

    def _path_for(self, root_run_id: str) -> Path:
        return self._store_dir / f"{root_run_id}.json"

    def save(self, record: RetryLineageRecord) -> bool:
        try:
            self._store_dir.mkdir(parents=True, exist_ok=True)
            fd, tmp_path_str = tempfile.mkstemp(
                prefix=f".{record.root_run_id}.", suffix=".tmp", dir=str(self._store_dir)
            )
        except OSError as e:
            print(f"  [RETRY LINEAGE WARNING] lineage保存に失敗しました（処理は継続します）: {e}")
            return False

        tmp_path = Path(tmp_path_str)
        try:
            try:
                f = os.fdopen(fd, "w", encoding="utf-8")
            except OSError as e:
                try:
                    os.close(fd)
                except OSError:
                    pass
                print(f"  [RETRY LINEAGE WARNING] lineage保存に失敗しました（処理は継続します）: {e}")
                return False

            try:
                with f:
                    f.write(record.to_json())
                    f.flush()
                    os.fsync(f.fileno())
            except OSError as e:
                print(f"  [RETRY LINEAGE WARNING] lineage保存に失敗しました（処理は継続します）: {e}")
                return False

            try:
                os.replace(tmp_path, self._path_for(record.root_run_id))
            except OSError as e:
                print(f"  [RETRY LINEAGE WARNING] lineage保存に失敗しました（処理は継続します）: {e}")
                return False

            return True
        finally:
            if tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass

    def get(self, root_run_id: str) -> RetryLineageRecord | None:
        path = self._path_for(root_run_id)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return RetryLineageRecord.from_dict(data)
        except (OSError, ValueError, KeyError) as e:
            print(f"  [RETRY LINEAGE WARNING] lineage読み込みに失敗しました（{path.name}）: {e}")
            return None

    def list_all(self) -> list[RetryLineageRecord]:
        if not self._store_dir.exists():
            return []

        records: list[RetryLineageRecord] = []
        for path in sorted(self._store_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                records.append(RetryLineageRecord.from_dict(data))
            except (OSError, ValueError, KeyError) as e:
                print(f"  [RETRY LINEAGE WARNING] lineage読み込みに失敗しました（{path.name}）: {e}")
        return records
