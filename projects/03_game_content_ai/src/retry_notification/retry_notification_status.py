"""
Retry Notification Status（v6.6.0）

RetryNotificationStatus: RetryNotificationEvaluatorが判定する通知要否の結果を
                          表すEnum。

設計方針（docs/design/retry_notification_foundation.md 8章・9章）:
    - NO_NOTIFICATION / NOTIFY の2値のみを持つ
    - NO_NOTIFICATIONは、RetryNotificationEvaluator.evaluate()が正常に実行・
      完了した結果、入力されたRetryAlertが通知対象となる状態ではないことを
      表す正常系の明示値である。評価失敗・入力不足・未対応値・処理スキップ・
      Evaluator未実行のいずれも意味しない
    - RetryAlertLevel（NONE/WARNING/CRITICAL）とは別の語彙として定義する。
      RetryAlertLevel.NONEとの名称衝突（別の型に属する同名メンバーの混同）を
      避けるため、NONEではなくNO_NOTIFICATIONという語彙を採用する
"""
from __future__ import annotations

from enum import Enum


class RetryNotificationStatus(Enum):
    """RetryNotificationEvaluatorが判定する通知要否の結果。

    NO_NOTIFICATION: RetryNotificationEvaluator.evaluate()が正常に実行・完了
                      した結果、入力されたRetryAlertが通知対象となる状態では
                      ないことを表す正常系の明示値。評価失敗・入力不足・
                      未対応値・処理スキップ・Evaluator未実行のいずれも意味
                      しない。
    NOTIFY: 入力されたRetryAlertが通知対象となる状態であることを表す。
    """

    NO_NOTIFICATION = "NO_NOTIFICATION"
    NOTIFY = "NOTIFY"
