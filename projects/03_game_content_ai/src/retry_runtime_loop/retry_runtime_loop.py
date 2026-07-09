"""
Retry Runtime Loop（v5.5.0）

RetryRuntimeLoop: run_once_fn を interval ごとに繰り返し呼び出すだけの薄いWrapper。
                   Business Logicは一切持たない。

設計方針:
    - 本クラスの責務は「run_once_fn / sleep_fn / should_continue_fn への参照を保持すること」
      と「while should_continue_fn(): run_once_fn(); sleep_fn(interval) を実行すること」の
      2つに限定する（docs/design/retry_runtime_loop_foundation.md 2.2節）。
    - RetryManager / RetryQueueManager / RetryHistoryManager / RetryPolicyのいずれも
      知らない（import・参照しない）。run_once_fn の戻り値（型は問わない。本クラスは
      その中身を一切解釈しない）は破棄し、run() は None を返す。
    - 例外はtry/exceptで握りつぶさず、そのまま run() から呼び出し元へ伝播させる
      （fail-fast。RetryRuntimeOrchestrator.run_once()と対称的な方針）。
      run_once_fn が例外を送出した場合、直後の sleep_fn は呼ばれない。
    - interval_secondsのバリデーションは行わない（DIのみで完結し、外部入力の境界に
      該当しないため。Development Charter「検証は境界でのみ行う」）。
    - 本Release時点では、本クラスを呼び出す既存コード（scripts/を含む）は存在しない
      （消費者不在の先行実装。docs/design/retry_runtime_loop_foundation.md 2.3節）。
"""
from __future__ import annotations

from typing import Callable


class RetryRuntimeLoop:
    """
    run_once_fn を interval_seconds ごとに繰り返し呼び出すだけのStateless Wrapper。

    run_once_fn / sleep_fn / should_continue_fn への参照をConstructor Injectionで
    保持し、run()で以下の順序を繰り返す。

        while should_continue_fn():
            run_once_fn()
            sleep_fn(interval_seconds)
    """

    def __init__(
        self,
        run_once_fn: Callable[[], object],
        sleep_fn: Callable[[float], None],
        should_continue_fn: Callable[[], bool],
        interval_seconds: float,
    ):
        self.run_once_fn = run_once_fn
        self.sleep_fn = sleep_fn
        self.should_continue_fn = should_continue_fn
        self.interval_seconds = interval_seconds

    def run(self) -> None:
        """
        should_continue_fn() が True である限り、run_once_fn() の呼び出しと
        sleep_fn(interval_seconds) を交互に繰り返す。

        run_once_fn() の戻り値は型を問わず解釈・保持せず破棄する。run_once_fn() が
        例外を送出した場合は、そのまま呼び出し元へ伝播させる（sleep_fn は呼ばれない）。
        """
        while self.should_continue_fn():
            self.run_once_fn()
            self.sleep_fn(self.interval_seconds)
