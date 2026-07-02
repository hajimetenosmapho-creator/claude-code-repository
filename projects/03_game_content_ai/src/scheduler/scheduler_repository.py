"""
Scheduler Repository（v2.6.0）

SchedulerRepository:      SchedulerJobの永続化方式を抽象化するインターフェース
InMemorySchedulerRepository: メモリ上のdictのみで完結する最小実装

設計方針:
    - Foundation Releaseではまず InMemorySchedulerRepository のみを提供する。
      JSON / SQLite / DB等への永続化（persistence）は将来Releaseの拡張候補とし、
      本バージョンでは対象外とする（プロセス終了とともにJobは消える）
    - 将来の永続化実装は、本インターフェース（SchedulerRepository）を満たす
      クラスを新規追加するだけで差し替え可能な設計にする
      （SchedulerManager側の変更は不要）
    - job_id の一意性はRepository側で保証する
      （add()でjob_idが重複していればDuplicateSchedulerJobErrorを送出する）
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from .exceptions import DuplicateSchedulerJobError, SchedulerJobNotFoundError
from .scheduler_job import SchedulerJob


class SchedulerRepository(ABC):
    """SchedulerJobの永続化方式を抽象化するインターフェース。"""

    @abstractmethod
    def add(self, job: SchedulerJob) -> None:
        """Jobを新規追加する。job_idが既に存在する場合はDuplicateSchedulerJobErrorを送出する。"""
        ...

    @abstractmethod
    def remove(self, job_id: str) -> None:
        """Jobを削除する。存在しない場合はSchedulerJobNotFoundErrorを送出する。"""
        ...

    @abstractmethod
    def get(self, job_id: str) -> SchedulerJob | None:
        """job_idに対応するJobを返す。存在しない場合はNoneを返す。"""
        ...

    @abstractmethod
    def list_all(self) -> list[SchedulerJob]:
        """登録されているすべてのJobを返す。"""
        ...

    @abstractmethod
    def update(self, job: SchedulerJob) -> None:
        """既存Jobを置き換える。存在しない場合はSchedulerJobNotFoundErrorを送出する。"""
        ...


class InMemorySchedulerRepository(SchedulerRepository):
    """メモリ上のdictのみでSchedulerJobを管理する最小実装。"""

    def __init__(self):
        self._jobs: dict[str, SchedulerJob] = {}

    def add(self, job: SchedulerJob) -> None:
        if job.job_id in self._jobs:
            raise DuplicateSchedulerJobError(
                f"job_id '{job.job_id}' は既に登録されています。"
            )
        self._jobs[job.job_id] = job

    def remove(self, job_id: str) -> None:
        if job_id not in self._jobs:
            raise SchedulerJobNotFoundError(
                f"job_id '{job_id}' は登録されていません。"
            )
        del self._jobs[job_id]

    def get(self, job_id: str) -> SchedulerJob | None:
        return self._jobs.get(job_id)

    def list_all(self) -> list[SchedulerJob]:
        return list(self._jobs.values())

    def update(self, job: SchedulerJob) -> None:
        if job.job_id not in self._jobs:
            raise SchedulerJobNotFoundError(
                f"job_id '{job.job_id}' は登録されていません。"
            )
        self._jobs[job.job_id] = job
