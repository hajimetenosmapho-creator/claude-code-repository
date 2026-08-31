"""
Retry Lineage Store Lock（v6.31.0、Release 6.31）

RetryLineageStoreLockError: ロック取得がタイムアウトした場合に送出される例外
RetryLineageStoreLock:      RetryLineageStoreの個々のmutation操作（read-check-write全体）を
                             保護する、短時間・タイムアウト付きリトライのOS-backed排他原語

設計方針（docs/design/retry_lineage_eligibility_durable_attempt_state.md 9.2章）:
    - 既存 RetryRuntimeLock（src/retry_runtime_lock/）と同型の、os.open()の
      O_CREAT|O_EXCLによるアトミックな排他生成を用いる。RetryRuntimeLockとの違いは、
      取得失敗時に即座にraiseせず、短いタイムアウトまでリトライする点のみ
      （複数の短命なmutation操作が高速に連続する想定のため）。
    - RetryLineageStoreLockを取得するコードパスは、find_existing_lineage() /
      create_new_lineage() / claim() / release_claim() / mark_execution_started() /
      mark_terminal() / open_next_attempt() の7メソッドのみであり、これらはすべて
      例外なく9.3章のRetryExecutionLockが既に取得された状態からのみ呼び出される
      （9.3.4章 Lock Ordering：RetryExecutionLock → RetryLineageStoreLockの単一の
      ネスト順序のみ、逆転なし）。
    - PIDは診断目的のみ（stale判定には使わない、9.4章の運用手順に委ねる）。
"""
from __future__ import annotations

import os
import time
from pathlib import Path


class RetryLineageStoreLockError(Exception):
    """ロック取得がタイムアウトした場合に送出される例外。"""


class RetryLineageStoreLock:
    """RetryLineageStoreの個々のmutation操作を保護する、短時間リトライ付きの排他制御。"""

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
                    raise RetryLineageStoreLockError(
                        f"RetryLineageStoreLockの取得がタイムアウトしました"
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

    def __enter__(self) -> "RetryLineageStoreLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()
