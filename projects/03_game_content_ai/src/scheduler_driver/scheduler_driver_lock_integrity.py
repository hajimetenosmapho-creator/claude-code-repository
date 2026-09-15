"""
Scheduler Driver Lock Integrity（v6.34.0、Release 6.34）

LockIntegrityViolationError: ownership検証に失敗した場合に送出される例外
_verify_lock_ownership():    lockファイルの中身が自プロセスのPIDのままであることを確認する
_release_if_owned():         releaseの直前に必ずownershipを再検証し、検証成功時のみ
                              lock.release()を呼ぶ

設計方針（docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md
12.1・12.2章、Codex Round 1〜4対応を経て確定）:
    - RetryRuntimeLock（src/retry_runtime_lock/）自体は無改修のまま再利用する
      （ドメイン非依存の汎用コンポーネント、6.4章Finding F3）。本モジュールは
      その上に「ownership整合性の検証」という追加の安全層を、呼び出し側の
      コードのみで実現する。
    - `lock.release()`を直接呼び出すコードはリポジトリ全体で `_release_if_owned()`
      の内部、ただ1箇所に限定する。呼び出し元（scripts/run_scheduler_driver.py の
      `main()`の`finally`節）もただ1箇所とする（12.2章）。
    - `_release_if_owned()`はException（BaseExceptionは除く、15章の既存方針と
      整合）を広く捕捉し、release可否判定自体が失敗してもfail-closed
      （何もしない、raiseしない）とする。
    - TOCTOU（Time-of-Check-Time-of-Use）残存リスク：`_verify_lock_ownership()`
      の読み取りと`lock.release()`の削除の間には、原理的にごく短い間隙が残る。
      この残存windowは「解消済み」ではなく「Accepted・Low確率・未解消」として
      25章R2に明記されている（本モジュールはこの間隙自体をゼロにはしない）。
"""
from __future__ import annotations

from pathlib import Path

from retry_runtime_lock import RetryRuntimeLock


class LockIntegrityViolationError(Exception):
    """lockファイルの中身が自プロセスのPIDと一致しない場合（Lock Integrity
    Violation）に送出される例外。"""

    def __init__(self, lock_path: Path, own_pid: int):
        self.lock_path = lock_path
        self.own_pid = own_pid
        super().__init__(
            f"Lock integrity violation: lock_path={lock_path} own_pid={own_pid} "
            "（lockファイルの中身が自プロセスのPIDと一致しません。別driverが"
            "lockを奪取した可能性があります）。"
        )


def _verify_lock_ownership(lock_path: Path, own_pid: int) -> bool:
    """lock_pathの中身が自プロセスのPIDのままであることを確認する。
    読み取れない・PIDが一致しない場合はFalse（fail-closed）。"""
    try:
        content = lock_path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return content == str(own_pid)


def _log_lock_integrity_violation_on_exit() -> None:
    print(
        "  [SCHEDULER DRIVER WARNING] lock ownershipの検証に失敗したため、"
        "release()をスキップしました（他プロセスの正当なlockを保護するため）。"
    )


def _release_if_owned(lock: RetryRuntimeLock, own_pid: int) -> None:
    """releaseの直前に必ずownershipを再検証する。検証に失敗した場合は
    releaseをスキップする（他プロセスの正当なlockを誤って削除しないため）。
    このヘルパーはscripts/run_scheduler_driver.pyのmain()のfinally節からのみ
    呼び出される（呼び出し箇所の一意性が安全性契約の実体、12.2章）。
    OSErrorに限定せずExceptionを広く捕捉する（15章のException/BaseException
    境界方針と整合。BaseExceptionは対象外）。"""
    try:
        if _verify_lock_ownership(lock.lock_path, own_pid):
            lock.release()
        else:
            _log_lock_integrity_violation_on_exit()
    except Exception:
        _log_lock_integrity_violation_on_exit()
