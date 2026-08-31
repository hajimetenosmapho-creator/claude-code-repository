"""
Retry Execution Lock（v6.31.0、Release 6.31）

RetryExecutionLockBusyError: ロック取得に失敗した場合（＝別のretry()/reconcile_all()が
                              in-flight）に送出される例外
RetryExecutionLock:          RetryManager.retry()とRetryLineageManager.reconcile_all()
                              双方にとって唯一の実行時排他境界

設計方針（docs/design/retry_lineage_eligibility_durable_attempt_state.md 9.3章）:
    - os.open()のO_CREAT|O_EXCLによるアトミックな排他生成。即時fail-closed、
      リトライなし（single-flight by design、9.3.3章）。
    - 診断目的でPID:timestampをロックファイルへ書き込む（staleness判定には使わない、
      自動削除なし。手動復旧手順は9.4章）。
    - 同一プロセス内であっても2回目の取得はブロックせず即座に失敗する（誰が
      取得したかを区別しない）。これにより、_retry_locked()/_reconcile_all_locked()
      が公開API（retry()/reconcile_all()）を再帰的に呼び出さないという設計上の
      不変条件（9.3.5章）が破られた場合、ハング（真のデッドロック）ではなく
      即座にRetryExecutionLockBusyErrorが送出される形で顕在化する。
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path


class RetryExecutionLockBusyError(Exception):
    """ロック取得に失敗した場合（＝別のretry()/reconcile_all()がin-flight）に送出される例外。"""


class RetryExecutionLock:
    """RetryManager.retry()とRetryLineageManager.reconcile_all()双方にとって唯一の
    実行時排他境界。with文で使用する（__enter__でacquire()、__exit__でrelease()）。"""

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path

    def acquire(self) -> None:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise RetryExecutionLockBusyError(
                f"execution lock busy: another retry()/reconcile_all() is in flight "
                f"(lock file: {self.lock_path})."
            ) from None
        try:
            diagnostic = f"{os.getpid()}:{datetime.now().isoformat()}"
            os.write(fd, diagnostic.encode("utf-8"))
        except BaseException:
            os.close(fd)
            self.lock_path.unlink(missing_ok=True)
            raise
        else:
            os.close(fd)

    def release(self) -> None:
        self.lock_path.unlink(missing_ok=True)

    def __enter__(self) -> "RetryExecutionLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()
