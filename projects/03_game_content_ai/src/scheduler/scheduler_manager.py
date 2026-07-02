"""
Scheduler Manager（v2.6.0）

SchedulerManager: SchedulerJobの登録・削除・取得・一覧・enable/disableを担当する管理API

設計方針:
    - SchedulerManagerはSchedulerRepositoryへ処理を委譲するだけの薄い管理層とし、
      Job永続化の実装詳細（メモリ管理か将来のJSON/DB管理か）を知らない
      （SchedulerRepositoryをコンストラクタでDIすることで差し替え可能にする）
    - enable_job / disable_job は既存Jobを dataclasses.replace() で複製し、
      enabledフィールドのみを変更したうえで Repository.update() に渡す
      （SchedulerJobを直接書き換えない。既存Jobオブジェクトの不変性を保つ設計）
    - SchedulerManager は NewsAgent / ReviewAgent / PublishAgent 等の
      既存Trigger Agentを一切importしない（Job管理の責務のみを持つ）
"""
from __future__ import annotations

from dataclasses import replace

from .exceptions import SchedulerJobNotFoundError
from .scheduler_job import SchedulerJob
from .scheduler_repository import SchedulerRepository


class SchedulerManager:
    """SchedulerJobの登録・削除・取得・一覧・enable/disableを担当する管理API。"""

    def __init__(self, repository: SchedulerRepository):
        self._repository = repository

    def register_job(self, job: SchedulerJob) -> None:
        """Jobを新規登録する。job_idが重複する場合はDuplicateSchedulerJobErrorを送出する。"""
        self._repository.add(job)

    def remove_job(self, job_id: str) -> None:
        """Jobを削除する。存在しない場合はSchedulerJobNotFoundErrorを送出する。"""
        self._repository.remove(job_id)

    def get_job(self, job_id: str) -> SchedulerJob | None:
        """job_idに対応するJobを返す。存在しない場合はNoneを返す。"""
        return self._repository.get(job_id)

    def list_jobs(self) -> list[SchedulerJob]:
        """登録されているすべてのJobを返す。"""
        return self._repository.list_all()

    def enable_job(self, job_id: str) -> SchedulerJob:
        """Jobをenabled=Trueにする。存在しない場合はSchedulerJobNotFoundErrorを送出する。"""
        return self._set_enabled(job_id, enabled=True)

    def disable_job(self, job_id: str) -> SchedulerJob:
        """Jobをenabled=Falseにする。存在しない場合はSchedulerJobNotFoundErrorを送出する。"""
        return self._set_enabled(job_id, enabled=False)

    def _set_enabled(self, job_id: str, enabled: bool) -> SchedulerJob:
        job = self._repository.get(job_id)
        if job is None:
            raise SchedulerJobNotFoundError(f"job_id '{job_id}' は登録されていません。")

        updated_job = replace(job, enabled=enabled)
        self._repository.update(updated_job)
        return updated_job
