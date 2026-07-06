"""
Retry Execution Selector（v4.0.0）

RetryExecutionSelector: RetryDispatchEventのリストから、dispatchable=Trueのものだけを
                         実行対象として選別するコンポーネント

設計方針:
    - dispatchable=True を「実行対象として扱う」ための唯一の判定基準とする。
      本コンポーネントが、その判定を行う唯一の場所である
      （docs/design/retry_execution_foundation.md 2章・3章 Design Policy 2）。
    - Stateless。RetryDispatchEvent のリストを受け取り、選別結果のリストを返すだけの
      純粋関数的なメソッドのみを持つ。
    - RetryQueueManager 等への参照は一切持たない（コンストラクタ引数にも存在しない）。
"""
from __future__ import annotations

from .retry_event_dispatcher import RetryDispatchEvent


class RetryExecutionSelector:
    """RetryDispatchEventのリストから、実行対象（dispatchable=True）だけを選別するコンポーネント。"""

    def select(self, dispatch_events: list[RetryDispatchEvent]) -> list[RetryDispatchEvent]:
        """dispatchable=Trueのものだけを実行対象として選別する。"""
        return [event for event in dispatch_events if event.dispatchable]
