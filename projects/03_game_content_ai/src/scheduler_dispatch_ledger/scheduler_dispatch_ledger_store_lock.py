"""
Scheduler Dispatch Ledger Store Lock（v6.34.0、Release 6.34）

SchedulerDispatchLedgerStoreLockError: ロック取得がタイムアウトした場合に送出される例外
SchedulerDispatchLedgerStoreLock:      SchedulerDispatchLedgerStoreの個々のmutation操作
                                        （read-check-write全体）を保護する、短時間・
                                        タイムアウト付きリトライのOS-backed排他原語

設計方針（docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md 8.5章(4)(c)）:
    - 既存 RetryLineageStoreLock（src/retry_lineage/retry_lineage_store_lock.py）と
      同型の、os.open()のO_CREAT|O_EXCLによるアトミックな排他生成＋短時間リトライを
      用いる。単一のlock pathがstore全体のmutation操作（claim() / confirm() /
      reconcile_stale_claims()の個別record書き込み）を直列化する
      （per-record locking＝reconciliationのループ内で1件ごとに取得する運用を指し、
      lock path自体は複数存在しない。retry_lineageの既存precedentと同一の設計）。
    - PIDは診断目的のみ（stale判定には使わない）。
"""
from __future__ import annotations

import os
import time
from pathlib import Path


class SchedulerDispatchLedgerStoreLockError(Exception):
    """ロック取得がタイムアウトした場合に送出される例外。"""


class SchedulerDispatchLedgerStoreLock:
    """SchedulerDispatchLedgerStoreの個々のmutation操作を保護する、短時間リトライ付きの排他制御。"""

    def __init__(self, lock_path: Path, timeout_seconds: float = 5.0, retry_interval_seconds: float = 0.05):
        self.lock_path = lock_path
        self._timeout_seconds = timeout_seconds
        self._retry_interval_seconds = retry_interval_seconds

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        deadline = time.monotonic() + self._timeout_seconds
        while True:
            try:
                fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise SchedulerDispatchLedgerStoreLockError(
                        f"SchedulerDispatchLedgerStoreLockの取得がタイムアウトしました"
                        f"（lock file: {self.lock_path}、timeout={self._timeout_seconds}s）。"
                    ) from None
                time.sleep(self._retry_interval_seconds)
                continue
            try:
                os.write(fd, str(os.getpid()).encode("utf-8"))
            except BaseException:
                os.close(fd)
                self.lock_path.unlink(missing_ok=True)
                raise
            else:
                os.close(fd)
            return

    def release(self) -> None:
        self.lock_path.unlink(missing_ok=True)

    def __enter__(self) -> "SchedulerDispatchLedgerStoreLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()
