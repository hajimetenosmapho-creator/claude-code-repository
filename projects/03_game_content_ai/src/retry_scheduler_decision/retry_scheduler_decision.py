"""
Retry Scheduler Decision（v3.5.0）

RetrySchedulerDecision: RetrySchedulerSource（またはNullRetrySchedulerSource）が返す
                         待機中の項目一覧から、「次に処理すべき候補」を選ぶだけの
                         専用コンポーネント。

設計方針:
    - RetrySchedulerSource.list_pending_retries() が既に返す順序
      （priority昇順・enqueue_time昇順、RetryQueueManager.list()で整列済み）を
      そのまま活用し、独自の並べ替え・優先度計算は一切行わない（選択・抽出のみ）。
    - Constructor Injectionのみ。retry_source（RetrySchedulerSource |
      NullRetrySchedulerSource）を必須引数として受け取る（デフォルト値を持たない）。
      本コンポーネントにとって retry_source は唯一の実質的な入力であり、
      SchedulerEngine.__init__ の retry_source（デフォルト None →
      NullRetrySchedulerSource() フォールバック）とは異なり、省略時の安全な
      既定値という概念自体が存在しないため（docs/design/retry_scheduler_decision.md
      13章 Design Decision #1）。
    - retry_source に None が渡された場合の防御的チェックは追加しない
      （型ヒント上サポート対象外。呼び出し元の実装ミスとして扱う。
      RetryQueueManager 等、プロジェクト内の他の全Managerクラスと同じ扱い。
      同設計書16.3節 Minor Recommendation 3）。
    - Null Object Pattern は採用しない（NullRetrySchedulerDecision は作らない）。
      本コンポーネント自身には対応するFeature Gate・Config軸が存在せず、
      「無効化」は呼び出し元が retry_source に NullRetrySchedulerSource() を
      渡すことで既に完結している（渡した場合 select_candidates() は常に [],
      select_next_candidate() は常に None を返す）。これはプロジェクト全体の
      設計言語（実装クラス／Nullクラスのペア）からの意図的な逸脱であり、
      「Feature Gate/Config軸を持たないコンポーネントにはNull Object Patternを
      機械的に適用しない」という判断による（同設計書13章 Design Decision #2）。
    - dequeue() / remove() は一切呼び出さない（RetrySchedulerSource /
      NullRetrySchedulerSource のいずれにもそれらのメソッドが存在しないため、
      構造的に呼び出しようがない）。
    - 本Release時点では、本パッケージはどのパッケージからも呼び出されない
      （Foundation First。SchedulerEngineとの実配線は将来Release）。
"""
from __future__ import annotations

from retry_scheduler_source import NullRetrySchedulerSource, RetrySchedulerSource


class RetrySchedulerDecision:
    """
    RetrySchedulerSource（またはNullRetrySchedulerSource）が返す待機中の項目一覧から、
    「次に処理すべき候補」を選ぶだけの専用コンポーネント。

    RetrySchedulerSource.list_pending_retries()の既存順序（priority昇順・
    enqueue_time昇順）をそのまま活用し、独自の並べ替え・優先度計算は行わない。
    Queueへの書き込み（enqueue / dequeue / remove）は一切行わない。
    """

    def __init__(self, retry_source: "RetrySchedulerSource | NullRetrySchedulerSource"):
        self._retry_source = retry_source

    def select_candidates(self, limit: int | None = None) -> list:
        """
        RetrySchedulerSource.list_pending_retries(limit) への委譲。
        戻り値をそのまま返す（並べ替え・加工はしない）。

        戻り値の要素はRetryQueueItem（retry_queueパッケージの公開型）だが、
        retry_scheduler_decisionはretry_queueに直接依存しない方針のため
        型ヒントとしてはimportしない。
        """
        return self._retry_source.list_pending_retries(limit=limit)

    def select_next_candidate(self):
        """
        select_candidates(limit=1)の戻り値から先頭1件を返す便利メソッド。

        「先頭1件」とは、RetrySchedulerSourceが返す順序（priority昇順・
        enqueue_time昇順。RetryQueueManager.list()で整列済み）における
        最初の項目を指す。候補が存在しない場合はNoneを返す。
        """
        candidates = self.select_candidates(limit=1)
        return candidates[0] if candidates else None
