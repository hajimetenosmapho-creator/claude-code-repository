"""
Scheduler例外定義（v2.6.0）

Scheduler固有の例外をまとめて定義する。

設計方針:
    - SchedulerError を基底とし、呼び出し側は個別の例外型・基底型どちらでも
      捕捉できるようにする
    - 標準例外（ValueError等）ではなくScheduler固有の型にすることで、
      呼び出し側がScheduler由来のエラーであることを明確に判別できるようにする
"""
from __future__ import annotations


class SchedulerError(Exception):
    """Scheduler関連の例外基底クラス。"""


class SchedulerJobNotFoundError(SchedulerError):
    """指定されたjob_idのJobが見つからない場合に送出される。"""


class DuplicateSchedulerJobError(SchedulerError):
    """既に存在するjob_idでJobを登録しようとした場合に送出される。"""
