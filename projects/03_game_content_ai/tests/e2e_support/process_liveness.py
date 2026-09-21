"""
T9: `tasklist`/`taskkill`生存確認ヘルパー。

docs/design/mvp_end_to_end_hardening_validation.md 6.21節の通り、本プロジェクト
は`psutil`に依存しない（`requirements.txt`未記載・venv未インストール）。
Windows標準搭載の`tasklist`/`taskkill`のみで、Scenario D・F1・F2が必要とする
プロセス生存確認／終了確認／bounded pollingを提供する（Scenario Cは使用しない、
10.5節・単一専用workerによる決定的isolationのみで完結するため）。
"""

from __future__ import annotations

import subprocess
import time
from typing import Callable


def is_pid_alive(pid: int) -> bool:
    """`tasklist`の標準出力に対象PIDの行が含まれるかで生存を判定する。"""
    result = subprocess.run(
        ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"],
        capture_output=True,
        text=True,
    )
    return str(pid) in result.stdout


def wait_until(predicate: Callable[[], bool], timeout_sec: float, interval_sec: float = 0.05) -> bool:
    """predicate()がTrueになるまで、interval_sec間隔・timeout_sec上限で
    bounded pollingする。timeout内にTrueにならなければFalseを返す
    （呼び出し側がtiming failureとして明示的にテストを失敗させる責務を持つ）。

    【Post-Codex-delta-review#2 Amendment、Minor#1対応】従来はloop終了後に
    もう一度`predicate()`を評価し、それがdeadline超過後にTrueになった場合でも
    成功として扱っていた（deadline厳密性の欠如）。この「最後のボーナス評価」を
    廃止し、`timeout_sec`以内にpredicate()がTrueにならなかった場合は無条件に
    Falseを返すよう修正した。

    【Post-Codex-delta-review#3 Amendment、Minor#1対応】上記修正後も、
    deadlineの判定が`predicate()`呼び出しの**前**にしか行われていなかった
    ため、`predicate()`自体の実行（スケジューリング遅延を含む）がdeadlineを
    跨いだ場合、それでもTrueが返れば成功扱いになってしまう残存レースが
    あった。`predicate()`がTrueを返した**直後にもdeadlineを再確認し**、
    その時点で既にdeadlineを超えていれば成功として扱わない（False）よう
    修正する——predicate自体の実行時間もdeadline判定の対象に含める。"""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if predicate():
            return time.monotonic() <= deadline
        time.sleep(interval_sec)
    return False


def wait_for_pid_alive(pid: int, timeout_sec: float, interval_sec: float = 0.05) -> bool:
    return wait_until(lambda: is_pid_alive(pid), timeout_sec, interval_sec)


def wait_for_pid_exit(pid: int, timeout_sec: float, interval_sec: float = 0.05) -> bool:
    return wait_until(lambda: not is_pid_alive(pid), timeout_sec, interval_sec)


def taskkill_tree(pid: int) -> subprocess.CompletedProcess:
    """`taskkill /PID <pid> /T /F`でプロセスツリー全体を強制終了する。"""
    return subprocess.run(
        ["taskkill", "/PID", str(pid), "/T", "/F"],
        capture_output=True,
        text=True,
    )
