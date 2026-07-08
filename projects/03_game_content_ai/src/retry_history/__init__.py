"""
Retry History パッケージ（v4.7.0）

original_run_idごとの再試行履歴（試行回数・直近の記録時刻）を記録・参照するだけの
最小基盤。Retry可否判定・Retry実行・Queue操作・Enqueueガード判定はいずれも行わない。

処理フロー（v4.7.0）:
    RetryHistoryManager.record(original_run_id, attempt, recorded_at)
        → 既存レコードがあればattempt_countをインクリメント、なければ新規作成
        → RetryHistoryRecord を返す

設計方針:
    - src/retry_history/ はどの既存パッケージ（workflow_engine/workflow_monitor/
      retry_engine/retry_queue/execution_history/ai/pipeline/scheduler）も
      importしない、標準ライブラリのみに依存する独立した葉パッケージ
      （docs/design/retry_history_foundation.md 5章）。
    - 「一度Retryされたrun_idを記録する」ことのみが責務であり、記録結果を使って
      再enqueueを止める・max_attemptsと比較する等の判定は本Releaseでは一切行わない
      （消費側の配線は次Release以降。Foundation First）。
    - Feature Gate・Configクラスは追加しない。RetryHistoryManager（実装クラス）／
      NullRetryHistoryManager（ダミー実装）のどちらを構築するかは呼び出し元が選ぶ
      （retry_queueのRetryQueueManager/NullRetryQueueManagerと同じNull Object
      Pattern。ただしretry_queueと異なり、そもそも本パッケージにはFeature Gate
      という概念自体が存在しない）。
"""
from .null_retry_history_manager import NullRetryHistoryManager
from .retry_history_manager import RetryHistoryManager
from .retry_history_record import RetryHistoryRecord

__all__ = [
    "RetryHistoryRecord",
    "RetryHistoryManager",
    "NullRetryHistoryManager",
]
