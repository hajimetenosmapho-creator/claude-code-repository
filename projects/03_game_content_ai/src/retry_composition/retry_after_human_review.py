"""
retry_after_human_review()（Release 6.32、17.3節）

composition層に配置する、HRR authorized retryの唯一のdispatch経路。依存方向は
`retry_composition → retry_lineage`・`retry_composition → retry_engine`の一方向
のみ——`retry_lineage`パッケージ自体はこの関数を一切importしない。

queue/schedulerへの依存なし：`resolve_human_review()`・
`open_next_attempt_after_human_review()`はいずれも`RetryQueueManager`／
`retry_queue_status`への書き込みを一切行わない。Release 6.32はgeneric
non-HRR automatic re-dispatch gapを修正しない（§2 Non-Goals）——HRR authorized
retryは、本関数の明示的な呼び出しのみによってdispatchされる。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from retry_lineage import HumanReviewResolution, RetryLineagePhase

if TYPE_CHECKING:
    from retry_engine.retry_manager import RetryManager
    from retry_engine.retry_result import RetryResult
    from retry_lineage.retry_lineage_manager import RetryLineageManager
    from retry_lineage.retry_lineage_results import OpenNextAttemptResult, ResolveHumanReviewResult


def retry_after_human_review(
    lineage: "RetryLineageManager",
    manager: "RetryManager",
    root_run_id: str,
    resolution: "HumanReviewResolution",
    actor: str,
    note: str | None = None,
) -> "RetryResult | ResolveHumanReviewResult | OpenNextAttemptResult":
    """crash-resumable resume判定：resolve_human_review()を再度呼ぶ前に、既に
    authorized-openが完了しdispatch待ちの状態かどうかをread-onlyで確認する。"""
    record = lineage.peek(root_run_id)
    if (
        record is not None
        and record.phase == RetryLineagePhase.READY_ELIGIBLE
        and record.human_review_resolution is not None
        and record.human_review_resolution.resolution == HumanReviewResolution.RETRY_ALLOWED
        and record.human_review_resolution.opened_attempt_no is not None
        and record.human_review_resolution.opened_attempt_no == record.next_attempt_ordinal
    ):
        # 既にauthorized-open済み（前回呼び出しがdispatch前にクラッシュした等）——
        # resolve_human_review()・open_next_attempt()のいずれも再度呼ばず、
        # 記録済みのattempt_noでdispatchのみを再開する。
        return manager.retry(root_run_id, attempt=record.human_review_resolution.opened_attempt_no)

    result = lineage.resolve_human_review(root_run_id, resolution, actor, note)
    if not result.acknowledged or resolution != HumanReviewResolution.RETRY_ALLOWED:
        return result

    opened = lineage.open_next_attempt_after_human_review(root_run_id)
    if not opened.acknowledged:
        return opened

    return manager.retry(root_run_id, attempt=opened.attempt_no)
