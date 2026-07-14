"""
Retry Runtime Lock（v6.0.0）

RetryRuntimeLock: 同一Retry Runtimeプロセスの多重起動を防止するための、
                   ファイル存在ベースの排他制御のみを行う薄いコンポーネント。

設計方針（docs/design/retry_runtime_lock_foundation.md）:
    - 本クラスの責務は「ロックファイルの取得・解放」のみに限定する。Retryドメイン・
      実行順序・ループ・スケジューリング・Daemon化はいずれも関知しない（4.1節）。
    - RetryCompositionRoot / RetryRuntimeOrchestrator / RetryRuntimeLoop /
      RetryManager等、他のretry_*パッケージのいずれにも依存しない（6章 Dependency）。
    - ロック取得はos.open()のO_CREAT|O_EXCLによるアトミックな排他生成のみで実現する。
      PIDの生存確認によるstale lock自動解除は行わない（4.3節却下案2、Out of Scope）。
      書き込むPIDは診断目的（運用者がロック保持者を確認するため）に限定し、
      本Releaseではstaleness判定には使わない（4.2節、12章 Known Risks）。
    - ロックファイルの親ディレクトリが存在しない場合はacquire()が作成する
      （Architecture Review後にImplementation Detailとして確定）。
    - ロックファイル自体はランタイム生成物であり、Git管理対象外とする
      （13章 ロックファイルの運用方針）。
"""
from __future__ import annotations

import os
from pathlib import Path


class RetryRuntimeLockError(Exception):
    """
    ロック取得に失敗した場合（＝既に別プロセスが実行中）に送出される例外。

    メッセージにはロックファイルのパスと対処方法を含み、呼び出し側（main()）が
    そのまま表示するだけで運用者向けの分かりやすいエラーメッセージになる。
    """


class RetryRuntimeLock:
    """
    ロックファイルの取得・解放のみを行う、Retryドメインを一切知らない排他制御コンポーネント。

    with文で使用することを想定する（__enter__でacquire()、__exit__でrelease()）。
    """

    def __init__(self, lock_path: Path):
        self.lock_path = lock_path

    def acquire(self) -> None:
        """
        ロックファイルをアトミックに新規作成し、自プロセスのPIDを書き込む。

        親ディレクトリが存在しない場合は作成する。ロックファイルが既に存在する
        場合は、既に別プロセスが実行中とみなしRetryRuntimeLockErrorを送出する
        （stale lockかどうかの判定は行わない）。
        """
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            fd = os.open(str(self.lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            raise RetryRuntimeLockError(
                f"既に別のRetry Runtimeプロセスが実行中です（lock file: {self.lock_path}）。"
                "二重起動でない場合は、対象プロセスが異常終了していないか確認した上で、"
                "このロックファイルを手動削除してください。"
            ) from None
        try:
            os.write(fd, str(os.getpid()).encode("utf-8"))
        except BaseException:
            os.close(fd)
            self.lock_path.unlink(missing_ok=True)
            raise
        else:
            os.close(fd)

    def release(self) -> None:
        """
        ロックファイルを削除する。ロックが存在しない状態で呼び出してもエラーに
        しない（べき等）。
        """
        self.lock_path.unlink(missing_ok=True)

    def __enter__(self) -> "RetryRuntimeLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()
