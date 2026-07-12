"""
Retry Runtime 実行スクリプト（v5.4.0、v5.7.0で--dry-run追加）

RetryCompositionRoot.from_env() → RetryRuntimeOrchestrator.from_composition_root() →
run_once() を1回だけ呼び出すEntry Point。Retry Runtimeの実行順序・組み立てロジックは
一切持たない（scripts層はBusiness Logicを持たない。
docs/design/retry_runtime_script_entry_point_foundation.md 2.1節・2.2節）。

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/run_retry_runtime.py
    ./venv/Scripts/python.exe scripts/run_retry_runtime.py --dry-run

引数:
    --dry-run   RetryRuntimeOrchestrator.run_once(dry_run=True)（v5.6.0で実装済み）を
                CLIから呼び出す。指定すると、実際にretry()を試行した結果を観測しつつ、
                Retry Queueからの除去・再試行履歴の記録は発生しない（安全確認用）。
                省略時（デフォルト）は従来どおりdry_run=Falseで実行する
                （docs/design/retry_runtime_safe_dry_run_wiring_foundation.md）。

Exit Code Policy（docs/design/retry_runtime_script_entry_point_foundation.md 2.4節）:
    - 正常終了：exit code 0（Python標準の暗黙の0。--dry-run指定時も同様）
    - 例外発生：Python標準の非0（fail-fastでそのまま伝播させる。独自のtry/exceptで
      握りつぶさない。run_once()自体のDesign Policyと対称的な方針）
    - 独自のExit Code体系（成功/一部失敗/異常等の多段階区分）は導入しない

注意:
    - --dry-run指定時も、RetryEnqueueTriggerはdry_run非対応のため、WorkflowMonitor上の
      FAILED/TIMEOUTをRetry Queueへenqueueする処理自体は通常どおり実行される
      （Known Issue。docs/CHANGELOG.md参照。対応予定Release「Retry Enqueue Trigger
      Dry Run Foundation」）。
    - Gateが無効（RETRY_ENGINE_ENABLED=false等）の場合でもエラーにはならず、
      結果件数がすべて0件として表示される（NullRetryManager等のNull Object
      Patternにより安全に処理されるため。本scriptはGateの状態を判定しない）。
    - 他のAgent系script（scripts/run_workflow_engine.py等）と同時実行しないこと
      （排他制御は対象外。docs/design/retry_runtime_script_entry_point_foundation.md
      3章「同時実行リスク」）。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from retry_composition import RetryCompositionRoot
from retry_runtime_orchestrator import RetryRuntimeCycleResult, RetryRuntimeOrchestrator


def format_summary(result: RetryRuntimeCycleResult) -> str:
    """
    RetryRuntimeCycleResult 1回分の実行結果を、人間向けのサマリー文字列に変換する。

    引数をRetryRuntimeCycleResult単体、戻り値をstr単体に絞ることで、将来
    出力形式（JSON出力等）が複数必要になった場合に、本関数のロジックをそのまま
    Formatterクラスへ抽出できる構造を維持している。今回はFormatterクラスの
    実装は行わない（docs/design/retry_runtime_script_entry_point_foundation.md
    2.8節 Design Note）。
    """
    trigger_result = result.trigger_result
    lines = [
        "=" * 50,
        "Retry Runtime 実行結果",
        "=" * 50,
        "  Enqueue         : "
        f"scanned={trigger_result.scanned}, enqueued={trigger_result.enqueued}, "
        f"skipped_existing={trigger_result.skipped_existing}, "
        f"skipped_status={trigger_result.skipped_status}, failed={trigger_result.failed}",
        f"  Scheduler       : candidates={len(result.scheduler_events)}",
        f"  Execution       : executed={len(result.execution_results)}",
        f"  Removal         : removed={len(result.removal_results)}",
        f"  Cleanup         : cleaned={len(result.cleanup_results)}",
        f"  TerminalCleanup : cleaned={len(result.terminal_cleanup_results)}",
        f"  History         : recorded={len(result.history_results)}",
        "=" * 50,
    ]
    return "\n".join(lines)


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", default=False)
    args = parser.parse_args()

    print("=" * 50)
    print("Retry Runtime 開始（1サイクルのみ実行）")
    print("=" * 50)
    print()

    if args.dry_run:
        print("[DRY RUN MODE]")
        print()

    root = RetryCompositionRoot.from_env()
    orchestrator = RetryRuntimeOrchestrator.from_composition_root(root)

    result = orchestrator.run_once(dry_run=args.dry_run)

    print(format_summary(result))


if __name__ == "__main__":
    main()
