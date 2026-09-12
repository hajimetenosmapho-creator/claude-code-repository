"""
Protected Operation Manifest Store Lock（Release 6.32 Architecture Amendment、Round 9設計）

attempt-execution-scoped、短時間タイムアウト付きリトライのOS-backed排他制御。
実装パターンは`wordpress_draft_state/wordpress_draft_state_store_lock.py`と同型。

Source of Truth: docs/design/
side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md 7章
"""
from __future__ import annotations

import hashlib
import os
import time
from pathlib import Path


class ProtectedOperationManifestStoreLockError(Exception):
    """ロック取得がタイムアウトした場合に送出される例外。"""


class ProtectedOperationManifestStoreLock:
    """create_for_attempt()・register()の対象キーへのdurable mutationを保護する、
    (root_run_id, attempt_ordinal, member_run_id)スコープのロック。"""

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
                    raise ProtectedOperationManifestStoreLockError(
                        f"ProtectedOperationManifestStoreLockの取得がタイムアウトしました"
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

    def __enter__(self) -> "ProtectedOperationManifestStoreLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()


def build_protected_operation_manifest_store_lock(
    locks_dir: Path, root_run_id: str, attempt_ordinal: int, member_run_id: str,
) -> ProtectedOperationManifestStoreLock:
    """`{locks_dir}/{sha256(f"{root_run_id}:{attempt_ordinal}:{member_run_id}")}.lock`を
    lock_pathとするキー-scopedロックを構築する。"""
    key = f"{root_run_id}:{attempt_ordinal}:{member_run_id}"
    digest = hashlib.sha256(key.encode("utf-8")).hexdigest()
    return ProtectedOperationManifestStoreLock(locks_dir / f"{digest}.lock")
