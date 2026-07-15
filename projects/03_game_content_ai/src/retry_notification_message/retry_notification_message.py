"""
Retry Notification Message（v6.7.0）

RetryNotificationMessage: RetryNotificationMessageBuilderの構築結果を表す、
                           Immutable（読み取り専用）な値オブジェクト。

設計方針（docs/design/retry_notification_message_foundation.md 9章）:
    - frozen=Trueのdataclassとして実装し、フィールドの再代入自体を構造的に
      禁止する（生成後は変更しない）
    - bodyのみを保持する。RetryAlert・RetryAlertLevel・RetryNotificationDecision・
      RetryNotificationStatusは保持・複製しない。title／channel／timestamp／
      reason等も本Releaseでは追加しない（Foundation First）
    - 重大度（WARNING/CRITICAL）が必要な将来の消費者は、呼び出し元が保持する
      元のRetryAlertを別途参照する（Release 6.6のTechnical Debt方針を継続）
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RetryNotificationMessage:
    """RetryNotificationMessageBuilderの構築結果を表すImmutableな値オブジェクト。"""

    body: str
