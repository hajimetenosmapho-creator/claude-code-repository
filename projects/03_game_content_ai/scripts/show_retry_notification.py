"""
Retry Notification CLI Report Wiring Foundation（v6.8.0）

Release 6.3〜6.7で完成した以下5つの「消費者不在の先行実装」を、単一CLIスクリプトから
初めて連続実行し、人間可読なReportとして標準出力へ表示する（docs/design/
retry_notification_cli_report_wiring_foundation.md）。

    RetryRuntimeLogReader
        -> RetryMetricsCalculator
        -> RetryHealthEvaluator
        -> RetryAlertEvaluator
        -> RetryNotificationEvaluator
        -> RetryNotificationMessageBuilder
        -> Retry Notification CLI Report

Runtime Pipelineへの本組み込みは行わない。RetryCompositionRoot / RetryRuntimeOrchestrator /
scripts/run_retry_runtime.py はいずれも無改修（本スクリプトから依存しない・依存されない）。

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/show_retry_notification.py
    ./venv/Scripts/python.exe scripts/show_retry_notification.py --log-path <path>

Exit Code Policy（設計書20章）:
    - 正常処理（NOTIFY／NO_NOTIFICATION問わず）: 0
    - OSError（ログファイル読取不能）: 1
    - ValueError（未対応Enum相当値）: 1
    - argparse構文エラー: 標準のSystemExit 2
    - 予期しない例外（上記以外）: 捕捉せず伝播（Python標準の非0終了）

NO_NOTIFICATION Contract（設計書16章）:
    RetryNotificationStatus.NO_NOTIFICATION は正常系である。この場合、
    RetryNotificationMessageBuilder は呼び出さず、message は None とする。
    既存の RetryNotificationMessageBuilder へ NO_NOTIFICATION 対応は追加しない。
"""
from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent
_SRC_ROOT = _PROJECT_ROOT / "src"

if str(_SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(_SRC_ROOT))

from retry_alert import RetryAlert, RetryAlertEvaluator
from retry_metrics import (
    RetryMetricsCalculator,
    RetryMetricsSnapshot,
    RetryRuntimeLogReader,
)
from retry_monitoring import RetryHealthEvaluator, RetryHealthReport
from retry_notification import (
    RetryNotificationDecision,
    RetryNotificationEvaluator,
    RetryNotificationStatus,
)
from retry_notification_message import (
    RetryNotificationMessage,
    RetryNotificationMessageBuilder,
)

_DEFAULT_LOG_PATH = _PROJECT_ROOT / ".run" / "retry_runtime_log.jsonl"

_TITLE = "Retry Notification Report"
_SEPARATOR = "=" * 50


@dataclass(frozen=True)
class RetryNotificationCliReport:
    """
    Metrics〜Notification Messageまでの評価結果を集約する、
    scripts.show_retry_notificationモジュール固有のPublic Model。

    src FoundationのPublic APIには追加しない。値集約のみを責務とし、
    Builder／Evaluator／Formatterの責務は持たない（設計書15章）。
    """

    metrics: RetryMetricsSnapshot
    health_report: RetryHealthReport
    alert: RetryAlert
    notification_decision: RetryNotificationDecision
    message: RetryNotificationMessage | None


def build_report(log_path: Path) -> RetryNotificationCliReport:
    """
    log_path（.run/retry_runtime_log.jsonl等）を読み取り、Metrics -> Health ->
    Alert -> Notification -> Message の順に評価し、RetryNotificationCliReport を返す。

    NOTIFY の場合のみ RetryNotificationMessageBuilder.build() を呼び出す。
    NO_NOTIFICATION の場合は message=None とし、Builderを呼び出さない（設計書16章）。
    """
    reader = RetryRuntimeLogReader(log_path=log_path)
    calculator = RetryMetricsCalculator()
    health_evaluator = RetryHealthEvaluator()
    alert_evaluator = RetryAlertEvaluator()
    notification_evaluator = RetryNotificationEvaluator()
    message_builder = RetryNotificationMessageBuilder()

    records = reader.read()
    metrics = calculator.calculate(records)
    health_report = health_evaluator.evaluate(metrics)
    alert = alert_evaluator.evaluate(health_report)
    notification_decision = notification_evaluator.evaluate(alert)

    if notification_decision.status is RetryNotificationStatus.NOTIFY:
        message = message_builder.build(notification_decision)
    elif notification_decision.status is RetryNotificationStatus.NO_NOTIFICATION:
        message = None
    else:
        # 構造上到達不能。RetryNotificationStatusが将来拡張された場合の
        # 防御的フォールバック禁止分岐（既存5パッケージの網羅分岐パターンを継承）。
        raise ValueError(
            "show_retry_notification: "
            f"未対応のRetryNotificationStatusです: {notification_decision.status!r}"
        )

    return RetryNotificationCliReport(
        metrics=metrics,
        health_report=health_report,
        alert=alert,
        notification_decision=notification_decision,
        message=message,
    )


def format_report(report: RetryNotificationCliReport) -> str:
    """
    RetryNotificationCliReport を人間可読な文字列へ変換する（Pure Function）。

    ファイルI/O・stdout/stderr出力・環境変数参照・現在時刻参照・CWD参照・
    Network I/O はいずれも行わない。戻り値には末尾改行を含めない
    （設計書17章 CLI Output Contract）。
    """
    metrics = report.metrics

    period_start_text = (
        metrics.period_start if metrics.period_start is not None else "（記録なし）"
    )
    period_end_text = (
        metrics.period_end if metrics.period_end is not None else "（記録なし）"
    )
    ratio_text = (
        f"{metrics.enqueue_success_ratio:.2f}"
        if metrics.enqueue_success_ratio is not None
        else "（算出不能）"
    )

    lines = [_SEPARATOR, _TITLE, _SEPARATOR, "[Metrics]"]
    if metrics.cycle_count == 0:
        lines.append("  （Retry Runtimeの実行記録がありません）")
    lines.append(f"  対象サイクル数     : {metrics.cycle_count}")
    lines.append(f"  記録開始           : {period_start_text}")
    lines.append(f"  記録終了           : {period_end_text}")
    lines.append(f"  Enqueue成功率      : {ratio_text}")
    lines.append("")
    lines.append("[Health]")
    lines.append(f"  ステータス         : {report.health_report.status.value}")
    lines.append("")
    lines.append("[Alert]")
    lines.append(f"  レベル             : {report.alert.level.value}")
    lines.append("")
    lines.append("[Notification]")
    lines.append(f"  ステータス         : {report.notification_decision.status.value}")
    lines.append("")
    lines.append("[Message]")
    if report.message is not None:
        lines.append(f"  {report.message.body}")
    else:
        lines.append("  （通知対象ではないため、Messageは生成されません）")
    lines.append(_SEPARATOR)

    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log-path", type=Path, default=_DEFAULT_LOG_PATH)
    args = parser.parse_args(argv)

    try:
        report = build_report(args.log_path)
    except (OSError, ValueError) as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1

    print(format_report(report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
