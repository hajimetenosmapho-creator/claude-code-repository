"""
Retry Notification Message Builder（v6.7.0）

RetryNotificationMessageBuilder: RetryNotificationDecision（v6.6.0の出力）から
                                  RetryNotificationMessageを構築するだけの、
                                  状態を持たないStateless Value Buildingコンポーネント。

設計方針（docs/design/retry_notification_message_foundation.md 10章・11章・12章・13章・17章）:
    - 入力はRetryNotificationDecisionのみ。RetryAlert・RetryAlertLevel・
      RetryHealthReport・RetryMetricsSnapshot・Runtime・Logger・JSONLのいずれも
      知らない・importしない
    - 判定（Judgment）は一切行わない。RetryNotificationEvaluator（v6.6.0）が
      既に確定したstatusを、以下の固定対応表に従ってRetryNotificationMessage
      へ変換するだけの単純な写像である
        NOTIFY           -> RetryNotificationMessage(body=<固定通知文言>)
        NO_NOTIFICATION  -> ValueError（契約違反）
    - 既知の2 Statusのみを明示的かつ網羅的（exhaustive）に分岐させる。dictの
      .get(status, デフォルト値)のような「知らない値は既定値へ丸める」形は
      採らない
    - NO_NOTIFICATIONはRetryNotificationEvaluatorにとって正常な明示値だが、
      本Builderにとっては「Messageを生成せよ」という要求自体が成立しない
      契約違反であるためValueErrorを送出する（Fail Fast契約）。「評価失敗」
      とは異なる（12章 NO_NOTIFICATION Semantics）
    - 未対応のStatus（将来RetryNotificationStatusに値が追加された場合）を
      NOTIFY・NO_NOTIFICATIONいずれの扱いへもフォールバックすることを禁止
      する。未対応のStatusを検知した場合はValueErrorを送出する（Fail Fast契約）
    - RetryAlertLevel.WARNING／CRITICALはいずれもv6.6.0でNOTIFYへ収束するため、
      本Builderは両者を区別できず区別しない。共通の固定Messageを返す
      （13章 WARNING／CRITICAL Semantics）
    - Stateless Pure Function：同一のRetryNotificationDecisionを渡した場合、
      常に同一のRetryNotificationMessage（NOTIFYの場合）または同一の例外
      （NO_NOTIFICATION／未対応値の場合）を返す
"""
from __future__ import annotations

from retry_notification import RetryNotificationDecision, RetryNotificationStatus

from .retry_notification_message import RetryNotificationMessage

_NOTIFY_MESSAGE_BODY = "Retry Runtimeで通知対象の状態が検出されました。詳細を確認してください。"


class RetryNotificationMessageBuilder:
    """RetryNotificationDecisionからRetryNotificationMessageを構築するだけの、状態を持たないコンポーネント。"""

    def build(self, decision: RetryNotificationDecision) -> RetryNotificationMessage:
        """
        decision（RetryNotificationDecision、唯一の入力）のstatusを、固定対応表に
        従ってRetryNotificationMessageへ変換して返す。

        - NO_NOTIFICATIONが渡された場合、Messageを生成できない契約違反として
          ValueErrorを送出する（呼び出し元はNOTIFYの場合のみbuild()を呼ぶこと）
        - NOTIFY / NO_NOTIFICATION 以外のstatusが渡された場合も、フォールバック
          せずValueErrorを送出する（未対応Statusの明示的失敗）
        """
        status = decision.status

        if status is RetryNotificationStatus.NOTIFY:
            return RetryNotificationMessage(body=_NOTIFY_MESSAGE_BODY)

        if status is RetryNotificationStatus.NO_NOTIFICATION:
            raise ValueError(
                "RetryNotificationMessageBuilder: "
                "RetryNotificationStatus.NO_NOTIFICATIONに対してMessageを生成することはできません"
                "（呼び出し契約違反。NOTIFYの場合のみbuild()を呼び出してください）"
            )

        raise ValueError(
            f"RetryNotificationMessageBuilder: 未対応のRetryNotificationStatusです"
            f"（フォールバックしません）: {status!r}"
        )
