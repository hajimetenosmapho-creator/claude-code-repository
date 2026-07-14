"""
Retry Runtime 実行スクリプト（v5.4.0、v5.7.0で--dry-run追加、v5.9.0で--loop追加、
v6.0.0でRuntime Lock追加）

RetryCompositionRoot.from_env() → RetryRuntimeOrchestrator.from_composition_root() →
run_once() を呼び出すEntry Point。Retry Runtimeの実行順序・組み立てロジックは
一切持たない（scripts層はBusiness Logicを持たない。
docs/design/retry_runtime_script_entry_point_foundation.md 2.1節・2.2節）。

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/run_retry_runtime.py
    ./venv/Scripts/python.exe scripts/run_retry_runtime.py --dry-run
    ./venv/Scripts/python.exe scripts/run_retry_runtime.py --loop
    ./venv/Scripts/python.exe scripts/run_retry_runtime.py --loop --interval-seconds 30
    ./venv/Scripts/python.exe scripts/run_retry_runtime.py --loop --dry-run

引数:
    --dry-run           RetryRuntimeOrchestrator.run_once(dry_run=True)（v5.6.0で実装済み）を
                        CLIから呼び出す。指定すると、実際にretry()を試行した結果を観測しつつ、
                        Retry Queueからの除去・再試行履歴の記録は発生しない（安全確認用）。
                        --loopと併用した場合、全サイクルへ伝播する。
                        省略時（デフォルト）は従来どおりdry_run=Falseで実行する
                        （docs/design/retry_runtime_safe_dry_run_wiring_foundation.md）。
    --loop              1サイクルだけで終了せず、RetryRuntimeLoop（v5.5.0）を使って
                        interval_seconds間隔で繰り返し実行する。省略時（デフォルト）は
                        従来どおり1サイクルのみで終了する
                        （docs/design/retry_runtime_loop_wiring_foundation.md）。
    --interval-seconds  --loop指定時のみ有効。サイクル間の待機秒数（正の数値）。
                        --loop指定時に省略した場合は60秒。--loopを指定せずに
                        --interval-secondsだけを指定するとCLIエラーになる。
                        0以下を指定した場合もCLIエラーになる。

Exit Code Policy（docs/design/retry_runtime_script_entry_point_foundation.md 2.4節、
v5.9.0でKeyboardInterrupt時の扱いを追加）:
    - 正常終了：exit code 0（Python標準の暗黙の0。--dry-run指定時も同様）
    - Loop実行中のKeyboardInterrupt（Ctrl+C）：運用者による意図的な正常停止として扱い、
      短い終了メッセージを表示したうえで exit code 0 とする（docs/design/
      retry_runtime_loop_wiring_foundation.md）
    - その他の例外発生：Python標準の非0（fail-fastでそのまま伝播させる。独自のtry/exceptで
      握りつぶさない。run_once()自体のDesign Policyと対称的な方針）
    - 独自のExit Code体系（成功/一部失敗/異常等の多段階区分）は導入しない

Runtime Lock（v6.0.0、docs/design/retry_runtime_lock_foundation.md）:
    - 実行開始時、`<project_root>/.run/retry_runtime.lock` の排他生成を試みる。
      既に別プロセスが実行中でロックファイルが存在する場合、CompositionRoot等は
      一切構築せずRetryRuntimeLockErrorを送出し、エラーメッセージを表示した上で
      exit code 1（非0終了）となる。単発実行・--loop実行の両方に適用される。
    - 正常終了・異常終了（KeyboardInterrupt含む）のいずれでもロックファイルは
      確実に解放される。
    - プロセスが強制終了（taskkill /F・電源断等）した場合、ロックファイルが
      残存し次回起動がブロックされることがある（stale lock）。二重起動でない
      ことを確認した上で、ロックファイルを手動削除すること。
    - ロックファイルはランタイム生成物であり、Git管理対象外（.gitignore登録済み）。

注意:
    - Gateが無効（RETRY_ENGINE_ENABLED=false等）の場合でもエラーにはならず、
      結果件数がすべて0件として表示される（NullRetryManager等のNull Object
      Patternにより安全に処理されるため。本scriptはGateの状態を判定しない）。
    - 他のAgent系script（scripts/run_workflow_engine.py等）と同時実行しないこと
      （Runtime Lockは本script自身の多重起動のみを防止し、他scriptとの排他制御は
      対象外。docs/design/retry_runtime_script_entry_point_foundation.md
      3章「同時実行リスク」）。
    - --loop使用時、同じRetry RuntimeをWindows タスクスケジューラ等の外部スケジューラから
      重複して定期起動しないこと。v6.0.0のRuntime Lockにより、二重起動時は
      後から起動した側がエラー終了するため、Retry対象の二重実行は防止される。
"""
import sys
import time
from pathlib import Path

_PROJECT_ROOT = Path(__file__).parent.parent

sys.path.insert(0, str(_PROJECT_ROOT / "src"))

from dotenv import load_dotenv
load_dotenv(_PROJECT_ROOT / ".env")

from retry_composition import RetryCompositionRoot
from retry_runtime_lock import RetryRuntimeLock, RetryRuntimeLockError
from retry_runtime_loop import RetryRuntimeLoop
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
    parser.add_argument("--loop", action="store_true", default=False)
    parser.add_argument("--interval-seconds", type=float, default=None)
    args = parser.parse_args()

    if args.interval_seconds is not None and not args.loop:
        parser.error("--interval-seconds can only be used together with --loop")
    if args.loop and args.interval_seconds is not None and args.interval_seconds <= 0:
        parser.error("--interval-seconds must be greater than 0")

    interval_seconds = None
    if args.loop:
        interval_seconds = args.interval_seconds if args.interval_seconds is not None else 60.0

    lock = RetryRuntimeLock(lock_path=_PROJECT_ROOT / ".run" / "retry_runtime.lock")
    try:
        with lock:
            print("=" * 50)
            if args.loop:
                print(f"Retry Runtime 開始（Loop実行、interval_seconds={interval_seconds}）")
            else:
                print("Retry Runtime 開始（1サイクルのみ実行）")
            print("=" * 50)
            print()

            if args.dry_run:
                print("[DRY RUN MODE]")
                print()

            root = RetryCompositionRoot.from_env()
            orchestrator = RetryRuntimeOrchestrator.from_composition_root(root)

            def run_cycle():
                result = orchestrator.run_once(dry_run=args.dry_run)
                print(format_summary(result))
                return result

            if not args.loop:
                run_cycle()
                return

            loop = RetryRuntimeLoop(
                run_once_fn=run_cycle,
                sleep_fn=time.sleep,
                should_continue_fn=lambda: True,
                interval_seconds=interval_seconds,
            )
            try:
                loop.run()
            except KeyboardInterrupt:
                print("Retry runtime loop stopped.")
    except RetryRuntimeLockError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
