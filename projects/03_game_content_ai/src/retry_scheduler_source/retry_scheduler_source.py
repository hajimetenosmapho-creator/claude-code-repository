"""
Retry Scheduler Source（v3.3.0）

RetrySchedulerSource:     Retry Queue の状態を Scheduler 側から読み取るための
                          Adapter（実装クラス）。
NullRetrySchedulerSource: RetrySchedulerSource のダミー実装（Null Object）。

設計方針:
    - RetrySchedulerSource は RetryQueueManager（実体）への参照を Constructor
      Injection でのみ保持し、list() / count() への薄い委譲のみを行う
      （docs/design/retry_scheduler_integration.md 4章）。dequeue() / remove()
      は一切呼び出さない。
    - Feature Gate・Configクラス・from_config()/from_env() のような起動口は
      持たない。有効／無効の表現は、呼び出し元が RetrySchedulerSource（実体）と
      NullRetrySchedulerSource のどちらを構築するかによって決まる
      （同設計書2章）。
    - RetrySchedulerSource と NullRetrySchedulerSource は継承関係を持たない
      （RetryManager/NullRetryManager、RetryQueueManager/NullRetryQueueManager
      と同じDuck Typingペア）。
    - NullRetrySchedulerSource は retry_queue パッケージへの参照を一切保持
      しない（状態を持たず、常に空リスト・0件を返す）。
    - 本Release（v3.3.0）では、本パッケージはどのパッケージからも呼び出され
      ない（Foundation First。Scheduler本体との実配線は将来Release）。
"""
from __future__ import annotations

from retry_queue import RetryQueueItem, RetryQueueManager


class RetrySchedulerSource:
    """
    Retry Queue の状態を Scheduler 側から読み取るための Adapter。

    RetryQueueManager への参照を Constructor Injection で保持し、list() /
    count() への薄い委譲のみを行う。Queueへの書き込み（enqueue / dequeue /
    remove）は一切行わない。
    """

    def __init__(self, queue: RetryQueueManager):
        self._queue = queue

    def list_pending_retries(self, limit: int | None = None) -> list[RetryQueueItem]:
        """RetryQueueManager.list() への委譲。戻り値をそのまま返す（加工しない）。"""
        return self._queue.list(limit=limit)

    def count_pending_retries(self) -> int:
        """RetryQueueManager.count() への委譲。戻り値をそのまま返す（加工しない）。"""
        return self._queue.count()


class NullRetrySchedulerSource:
    """
    RetrySchedulerSource のダミー実装（Null Object）。

    Retry Queueと接続しない場合に使う。retry_queue パッケージへの参照を一切
    保持せず、常に安全なデフォルト値（空リスト・0件）を返す。
    """

    def list_pending_retries(self, limit: int | None = None) -> list[RetryQueueItem]:
        return []

    def count_pending_retries(self) -> int:
        return 0
