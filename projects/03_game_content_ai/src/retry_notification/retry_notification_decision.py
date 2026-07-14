"""
Retry Notification Decision（v6.6.0）

RetryNotificationDecision: RetryNotificationEvaluatorの判定結果を表す、
                            Immutable（読み取り専用）な値オブジェクト。

設計方針（docs/design/retry_notification_foundation.md 8章）:
    - frozen=Trueのdataclassとして実装し、フィールドの再代入自体を構造的に
      禁止する（生成後は変更しない）
    - statusのみを保持する。RetryAlert・RetryAlertLevelは保持・複製しない
      （Foundation First。呼び出し元は既にRetryAlertを保持しているため、
      Decision側で複製保持する必要性が薄い）
    - message・channel・timestamp等は追加しない（Release 6.6ではstatusのみを
      扱う最小構成）
"""
from __future__ import annotations

from dataclasses import dataclass

from .retry_notification_status import RetryNotificationStatus


@dataclass(frozen=True)
class RetryNotificationDecision:
    """RetryNotificationEvaluatorの判定結果を表すImmutableな値オブジェクト。"""

    status: RetryNotificationStatus
