"""
WordPress Draft State Store Lock（Release 6.32、27.1〜27.4節）

identity-scoped、短時間タイムアウト付きリトライのOS-backed排他制御。実装パターンは
`src/retry_lineage/retry_lineage_store_lock.py`（`RetryLineageStoreLock`）と同型。

Lock Scope：`get()`（read-only）はこのロックを取得しない（27.3節、authoritative）。
durable mutationを行う`create_attempted()`/`transition_to_confirmed()`のみが、
対象identityのロックを取得する。
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path

from side_effect_safety.side_effect_operation_identity import SideEffectOperationIdentity


class WordPressDraftStateStoreLockError(Exception):
    """ロック取得がタイムアウトした場合に送出される例外。"""


class WordPressDraftStateStoreLock:
    """`WordPressDraftStateStore`の対象identityへのdurable mutationを保護する
    identity-scopedロック（27.5節）。"""

    def __init__(
        self, lock_path: Path, timeout_seconds: float = 5.0, retry_interval_seconds: float = 0.05,
    ):
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
                    raise WordPressDraftStateStoreLockError(
                        f"WordPressDraftStateStoreLockの取得がタイムアウトしました"
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

    def __enter__(self) -> "WordPressDraftStateStoreLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()


def build_wordpress_draft_state_store_lock(
    locks_dir: Path, identity: SideEffectOperationIdentity,
) -> WordPressDraftStateStoreLock:
    """`{locks_dir}/{sha256(identity.as_store_key())}.lock`をlock_pathとする
    identity-scopedロックを構築する（27.5節）。"""
    digest = hashlib.sha256(identity.as_store_key().encode("utf-8")).hexdigest()
    return WordPressDraftStateStoreLock(locks_dir / f"{digest}.lock")
