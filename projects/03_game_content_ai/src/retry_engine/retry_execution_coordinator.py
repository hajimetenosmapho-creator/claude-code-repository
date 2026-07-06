"""
Retry Execution Coordinator（v4.0.0）

RetryExecutionResult:      1件のRetryDispatchEventに対するretry()呼び出し結果を保持する軽量データ
RetryExecutionCoordinator: 実行対象として選別済みのRetryDispatchEventのリストを受け取り、
                            retry_fn（RetryManager.retry()）を各件に対して呼び出し、
                            結果を集約するコンポーネント

設計方針:
    - Queueに一切依存しない。入力は RetryDispatchEvent（Dispatcherが返した情報）のみで、
      RetryQueueManager への参照・retry_queue パッケージへのimportは一切持たない。
    - retry_fn は呼び出しごとにメソッド引数として受け取り、コンストラクタでは保持しない
      （Stateless。RetryManagerへの逆参照を持たないことで循環参照を避ける。
      docs/design/retry_execution_foundation.md 14章 Design Decision #4）。
    - retry_attempt は candidate_event.candidate から取得する。candidate の型は Any であり、
      retry_attempt 属性を持たない場合はデフォルト値 1 にフォールバックする。
      v4.0では Queue 非依存を優先した暫定実装であり、getattr による緩い取得＋
      フォールバックを採用している（retry_queue パッケージへの型依存は発生させない。
      docs/design/retry_execution_foundation.md 14章 Design Decision #5）。
    - retry_fn が例外を送出した場合は、そのまま呼び出し元へ伝播させる（fail-fast）。
      本Releaseでは部分失敗時の継続処理は導入しない（同設計書14章 Design Decision #7）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .retry_event_dispatcher import RetryDispatchEvent
from .retry_result import RetryResult

RetryFn = Callable[..., RetryResult]


@dataclass(frozen=True)
class RetryExecutionResult:
    """1件のRetryDispatchEventに対するretry()呼び出し結果を保持する軽量データ。"""

    dispatch_event: RetryDispatchEvent
    retry_result: RetryResult


class RetryExecutionCoordinator:
    """選別済みのRetryDispatchEventのリストを対象に、retry_fnを呼び出し結果を集約するコンポーネント。"""

    def execute(
        self,
        dispatch_events: list[RetryDispatchEvent],
        retry_fn: RetryFn,
        dry_run: bool = False,
    ) -> list[RetryExecutionResult]:
        """
        選別済みのRetryDispatchEventのリストについて、それぞれrun_id・attemptを取り出し
        retry_fn(run_id, attempt=attempt, dry_run=dry_run) を呼び出す。結果は
        RetryExecutionResult として dispatch_event と対にして返す。
        """
        results: list[RetryExecutionResult] = []
        for dispatch_event in dispatch_events:
            candidate = dispatch_event.candidate_event.candidate
            # v4.0では Queue 非依存を優先した暫定実装。retry_queue パッケージへの
            # 型依存を避けるため、getattr による緩い取得＋フォールバック（デフォルト1）とする。
            attempt = getattr(candidate, "retry_attempt", 1)
            retry_result = retry_fn(
                dispatch_event.candidate_event.run_id, attempt=attempt, dry_run=dry_run
            )
            results.append(RetryExecutionResult(dispatch_event=dispatch_event, retry_result=retry_result))
        return results
