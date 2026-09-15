"""
Retry Runtime Cycle Logger（v6.2.0）

RetryRuntimeCycleLogger: Retry Runtimeの1サイクル分の実行結果を、JSON Lines
                          形式で1レコードとしてログファイルへ追記するだけの、
                          Retryドメインを一切知らない汎用コンポーネント。

設計方針（docs/design/retry_runtime_structured_loop_logging_foundation.md）:
    - 本クラスの責務は「JSON Linesへ1レコード追記すること」のみに限定する。
      サイクル番号のカウント・実行順序・ループ・スケジューリングはいずれも
      関知しない（呼び出し元がcycle_numberを都度渡す）。
    - RetryRuntimeLock / RetryRuntimeShutdown / RetryRuntimeLoop /
      RetryRuntimeOrchestrator / RetryManager等、他のretry_*パッケージの
      いずれにも依存しない（RetryRuntimeCycleResultの型参照のみ）。
    - ログ書き込みの失敗（ディスク容量不足・権限エラー等）はRetry Runtime本体
      を停止させない。ベストエフォートとし、例外を送出せずstderrへWARNINGを
      出力するのみに留める（Runtime Failure Policy。Exit Code Policy
      （docs/design/retry_runtime_script_entry_point_foundation.md 2.4節）とは
      区別する）。
    - JSONスキーマは本Releaseで固定する。将来の変更はフィールド追加のみを
      基本方針とし、既存フィールドの意味変更は行わない（Logging Policy）。
    - log_cycle()の戻り値（v6.33.0で追加。docs/design/
      retry_observability_runtime_integration_foundation.md AD-3）は、書き込み
      処理（mkdir・open・write・close）がOSErrorを送出せず完了したかどうかの
      みを示すbool（Current-Cycle Inclusion Contract）。durability（fsyncに
      よるディスクへの確実な反映）や、書き込み完了後の外部プロセス・手動操作
      による変更からの保護は保証しない。WARNING出力自体の失敗も
      _warn_best_effort()でcontainし、呼び出し元へは伝播しない（Round 2 M-1対応）。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from retry_runtime_orchestrator import RetryRuntimeCycleResult


class RetryRuntimeCycleLogger:
    """
    1サイクル分の実行結果をJSON Lines形式で追記するだけの、Retryドメインを
    一切知らないログコンポーネント。
    """

    def __init__(self, log_path: Path):
        self.log_path = log_path

    def log_cycle(
        self,
        cycle_number: int,
        result: RetryRuntimeCycleResult,
        dry_run: bool = False,
    ) -> bool:
        """
        1サイクル分の実行結果を1行のJSONレコードとしてlog_pathへ追記する。

        親ディレクトリが存在しない場合は作成する。ログファイルが存在しない
        場合は新規作成し、存在する場合は末尾へ追記する。書き込みに失敗した
        場合は例外を送出せず、stderrへWARNINGメッセージを出力したうえで
        呼び出し元（Retry Runtime本体）の処理を継続させる。

        戻り値は、このメソッドの書き込み処理（mkdir・open・write・close）が
        OSError を送出せず完了したかどうかのみを示す（True＝完了、False＝
        OSError を捕捉）。durability（fsyncによるディスクへの確実な反映）は
        保証しない。書き込み完了後に他プロセス・手動操作がログファイルを
        変更・削除した場合の保護も行わない。呼び出し元はこの戻り値を用いて、
        当該cycleの書き込み呼び出し自体がOSErrorなく完了したことを確認した
        うえでのみ後続処理（Observability等）を行うことができる
        （Current-Cycle Inclusion Contract。保証範囲はここに記載の通り
        限定的であり、それ以上の意味を持たせない）。
        """
        trigger_result = result.trigger_result
        record = {
            "cycle_number": cycle_number,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "dry_run": dry_run,
            "enqueue_scanned": trigger_result.scanned,
            "enqueue_enqueued": trigger_result.enqueued,
            "enqueue_skipped_existing": trigger_result.skipped_existing,
            "enqueue_skipped_status": trigger_result.skipped_status,
            "enqueue_skipped_history": trigger_result.skipped_history,
            "enqueue_failed": trigger_result.failed,
            "scheduler_candidates": len(result.scheduler_events),
            "execution_executed": len(result.execution_results),
            "removal_removed": len(result.removal_results),
            "cleanup_cleaned": len(result.cleanup_results),
            "terminal_cleanup_cleaned": len(result.terminal_cleanup_results),
            "history_recorded": len(result.history_results),
        }

        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
            return True
        except OSError as e:
            _warn_best_effort("Failed to write runtime log", e)
            return False


def _warn_best_effort(prefix: str, exc: BaseException) -> None:
    """
    prefix と str(exc) を連結した WARNING メッセージを stderr へ出力するだけの、
    失敗しても何も再送出しない best-effort ヘルパー（Round 2 M-1対応）。

    src/retry_runtime_observability/retry_runtime_observability_reporter.py の
    同名ヘルパーと同一の実装パターン（メッセージ整形・print()を
    try/except Exception: passでcontainし、BaseExceptionは対象外）を、本ファイル
    内にモジュールプライベートな関数として複製する。2つの独立package間で
    新たな共有依存を作らないため（依存方向を変更しない）、あえて共通
    ユーティリティへ抽出しない（承認済み設計）。
    """
    try:
        print(f"WARNING: {prefix}: {exc}", file=sys.stderr)
    except Exception:  # noqa: BLE001 — 意図的な二次障害containment（Round 2 M-1対応）
        pass
