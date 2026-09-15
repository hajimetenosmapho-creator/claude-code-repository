"""
Retry Runtime Observability Reporter（v6.33.0）

RetryRuntimeObservabilityReporter: Retry Runtimeの1サイクル実行完了後、
                                    RetryRuntimeLogReader.read()が返す全件の
                                    RetryRuntimeLogRecordからRetryObservabilityPipeline
                                    を呼び出し、結果を整形してコンソールへ出力
                                    するだけの、Retry業務ロジックを一切知らない
                                    Runtime Integrationコンポーネント。

設計方針（docs/design/retry_observability_runtime_integration_foundation.md
          6章・7章・AD-1・AD-4・AD-5）:
    - ファイルI/Oは RetryRuntimeLogReader への委譲のみで行う（自前のopen()は持たない）
    - windowingは行わない。RetryMetricsCalculatorが前提とするcross-cycle
      cumulative semanticsを、CLI（show_retry_notification.py）と同一の
      「全件入力」でRuntime側からも維持する（AD-1）
    - observe()自体は失敗を一切捕捉しない（raw契約。単体テストで
      「例外がそのまま伝播すること」を直接検証できるようにするため）
    - 失敗包含（Runtime Failure Policy。RetryRuntimeCycleLogger.log_cycle()と
      対称的な方針）は observe_and_report() のみが担う単一境界とする（AD-4）。
      Exceptionのみをcontainし、BaseException（SystemExit・KeyboardInterrupt・
      GeneratorExit等）は対象外とする（Loop実行中のGraceful Shutdown割込みを
      誤って握りつぶさないため）
    - WARNING出力自体（メッセージ整形・print()）の失敗も_warn_best_effort()で
      containし、observe_and_report()の外へは一切伝播しない（Round 2 M-1対応）
    - dry_run引数は持たない（読み取り専用・観測専用のため、dry_runによる
      挙動分岐が存在しない）
    - 既存のretry判断コンポーネント（Manager系）・Composition Root・
      Orchestrator・scheduler・scriptsのいずれにも依存しない（retry_metricsと
      retry_observability_pipelineのみに依存する葉パッケージ）
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, TextIO

from retry_metrics import RetryRuntimeLogReader
from retry_observability_pipeline import RetryObservabilityPipeline, RetryObservabilityReport


class RetryRuntimeObservabilityReporter:
    """
    RetryRuntimeLogReader.read()が返す全件のRetryRuntimeLogRecordから、
    RetryObservabilityPipelineを呼び出してRetryObservabilityReportを得るだけの、
    Retry業務ロジックを一切知らないRuntime Integrationコンポーネント。
    """

    def __init__(
        self,
        log_path: Path,
        pipeline: RetryObservabilityPipeline | None = None,
    ):
        self.log_path = log_path
        self._pipeline = pipeline if pipeline is not None else RetryObservabilityPipeline()

    def observe(self) -> RetryObservabilityReport:
        """
        log_path から全件のRetryRuntimeLogRecordを取得し、
        RetryObservabilityPipeline.evaluate() を呼び出してRetryObservabilityReport
        を返す。例外は一切捕捉せずそのまま伝播する（失敗包含は
        observe_and_report()の責務。AD-4）。
        """
        records = RetryRuntimeLogReader(log_path=self.log_path).read()
        return self._pipeline.evaluate(records)

    def observe_and_report(
        self,
        formatter: Callable[[RetryObservabilityReport], str],
        out: TextIO | None = None,
    ) -> None:
        """
        読み取り（RetryRuntimeLogReader.read()）・評価（Pipeline.evaluate()）・
        整形（formatter）・コンソール出力（print）までの全段階を、ひとつの
        失敗包含境界として実行する（AD-4）。

        いずれかの段階で Exception 派生の例外が発生した場合（BaseException・
        SystemExit・KeyboardInterrupt・GeneratorExitは対象外、そのまま伝播する）、
        WARNING出力を試みたうえで戻り、呼び出し元（Retry Runtime本体）へは
        一切伝播しない。WARNING出力自体（メッセージ整形・print()）が失敗しても、
        それもこのメソッドの外へは伝播しない（_warn_best_effort()。Round 2 M-1対応）。

        out は呼び出し時点（call time）で解決する。省略時は本メソッドが実際に
        呼ばれた瞬間の sys.stdout を参照する（import時点で束縛しない。
        Round 2 MINOR対応。contextlib.redirect_stdout 等での capture を可能にする）。
        """
        try:
            report = self.observe()
            text = formatter(report)
            print(text, file=out if out is not None else sys.stdout)
        except Exception as e:  # noqa: BLE001 — 意図的な単一失敗包含境界（AD-4）
            _warn_best_effort("Failed to produce retry observability report", e)


def _warn_best_effort(prefix: str, exc: BaseException) -> None:
    """
    prefix と str(exc) を連結した WARNING メッセージを stderr へ出力するだけの、
    失敗しても何も再送出しない best-effort ヘルパー（Round 2 M-1対応）。

    str(exc)（カスタム例外の __str__ 実装バグ等）や print() 自体（stderrが
    閉じている等）が失敗しても、その例外はこの関数の外へは伝播しない
    （Exceptionのみをcontainする。BaseExceptionは対象外——呼び出し元
    observe_and_report()・log_cycle()と同じ方針）。呼び出し元は「WARNINGが
    出力される保証」ではなく「WARNING出力の失敗が呼び出し元へ波及しない保証」
    のみをこの関数から得る。
    """
    try:
        print(f"WARNING: {prefix}: {exc}", file=sys.stderr)
    except Exception:  # noqa: BLE001 — 意図的な二次障害containment（Round 2 M-1対応）
        pass
