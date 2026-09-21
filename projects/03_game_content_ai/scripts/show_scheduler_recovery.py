"""
Manual Recovery Diagnostic CLI（v6.36.0、Release 6.36「Manual Recovery Diagnostic CLI Foundation」）

SchedulerDispatchLedger（v6.34.0）のRECOVERY_REQUIRED occurrenceを、既存contractを
一切変更せず人間が安全に確認できる読み取り専用CLI。

設計方針（docs/design/manual_recovery_diagnostic_cli_foundation.md 6〜11章）:
    - JsonSchedulerDispatchLedgerStoreは一切instantiateしない（constructorが
      mkdir(parents=True, exist_ok=True)する既存挙動を持つため、8章）。代わりに、
      mkdirを一切含まない専用のread-only store実装（_ReadOnlyDispatchLedgerStore）
      を本ファイル内に定義し、SchedulerDispatchLedgerへ注入する。ディレクトリ確認・
      列挙・個別ファイル読み取りという制御フローは本クラス自身の新規コードとして
      実装し、パース・スキーマ検証（_entry_from_dict）・filename sanitize
      （_sanitize_event_identity）はscheduler_dispatch_ledger_storeモジュールの
      module-level関数を直接importして再利用する。
    - list_recovery_required()のみを使用する。claim()/confirm()/
      reconcile_stale_claims()/store.save()/peek()はいずれも一切呼ばない（7章）。
    - --event-identity / --job-id によるfilterは、list_recovery_required()の
      結果に対するin-memory filterとして実装する（peek()/store.get()は使わない）。
    - CLIはSchedulerDriverの起動用lock（.run/scheduler_driver.lock）・store lock
      （.store.lock）のいずれも取得しない（10章）。list_recovery_required()自体が
      このlockを要求しない既存契約をそのまま継承する。
    - 出力は診断情報・既存手順の案内のみであり、復旧の実行・判定・状態変更は
      一切行わない（11章）。safe-to-retry判定・workflow自動実行はしない。

使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/show_scheduler_recovery.py
    ./venv/Scripts/python.exe scripts/show_scheduler_recovery.py --job-id <JOB_ID>
    ./venv/Scripts/python.exe scripts/show_scheduler_recovery.py --event-identity <ID>
    ./venv/Scripts/python.exe scripts/show_scheduler_recovery.py --limit 5

Exit Code Policy（設計書6章）:
    - 正常処理（該当0件／N件いずれも）: 0
    - Store Initialization Boundary違反・SchedulerDispatchLedgerStoreReadError: 1
    - argparse構文エラー: 標準のSystemExit 2
    - 予期しない例外（上記以外）: 捕捉せず伝播
"""
from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv(Path(__file__).parent.parent / ".env")

from scheduler_dispatch_ledger import (
    DispatchLedgerEntry,
    SchedulerDispatchLedger,
    SchedulerDispatchLedgerConfig,
    SchedulerDispatchLedgerStore,
    SchedulerDispatchLedgerStoreReadError,
)
from scheduler_dispatch_ledger.scheduler_dispatch_ledger_store import (
    _entry_from_dict,
    _sanitize_event_identity,
)


class _ReadOnlyDispatchLedgerStore(SchedulerDispatchLedgerStore):
    """CLI専用のread-only store実装（設計書8章）。

    JsonSchedulerDispatchLedgerStoreのconstructorが行うmkdir()を一切呼ばない。
    save()は書き込み不能なdefensive実装とし、呼ばれた場合は例外を送出する。
    get()/list_all()は、store.py本体のget()/list_all()と同一のfilename/
    event_identity cross-check（多層防御）を維持したまま、read-only APIのみ
    （os.lstat/os.scandir/Path.read_text）で構成する。
    """

    def __init__(self, store_dir: Path):
        self._store_dir = store_dir

    def save(self, entry: DispatchLedgerEntry) -> bool:
        raise NotImplementedError(
            "_ReadOnlyDispatchLedgerStore.save() is intentionally unimplemented: "
            "this CLI is strictly read-only and must never write to the dispatch ledger."
        )

    def _ensure_store_dir_accessible(self) -> None:
        try:
            st = os.lstat(self._store_dir)
        except FileNotFoundError as e:
            raise SchedulerDispatchLedgerStoreReadError(
                f"store directory does not exist: {self._store_dir}"
            ) from e
        except OSError as e:
            raise SchedulerDispatchLedgerStoreReadError(
                f"store directory inspection failed: {self._store_dir}: {e}"
            ) from e
        if not stat.S_ISDIR(st.st_mode):
            raise SchedulerDispatchLedgerStoreReadError(
                f"store directory path is not a real directory (symlink or non-directory): {self._store_dir}"
            )

    def _read_record_file(self, path: Path) -> DispatchLedgerEntry | None:
        try:
            st = os.lstat(path)
        except FileNotFoundError:
            return None
        except OSError as e:
            raise SchedulerDispatchLedgerStoreReadError(f"{path.name}: inspection failed: {e}") from e
        if not stat.S_ISREG(st.st_mode):
            raise SchedulerDispatchLedgerStoreReadError(
                f"{path.name}: unexpected filesystem entry type (not a regular file, possibly a symlink)"
            )
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return _entry_from_dict(data)
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise SchedulerDispatchLedgerStoreReadError(f"{path.name}: {e}") from e

    def get(self, event_identity: str) -> DispatchLedgerEntry | None:
        self._ensure_store_dir_accessible()
        path = self._store_dir / f"{_sanitize_event_identity(event_identity)}.json"
        result = self._read_record_file(path)
        if result is None:
            self._ensure_store_dir_accessible()
            return None
        if result.event_identity != event_identity:
            raise SchedulerDispatchLedgerStoreReadError(
                f"{path.name}: filename/event_identity mismatch "
                f"(requested {event_identity!r}, record contains {result.event_identity!r}); "
                "possible filename collision"
            )
        return result

    def list_all(self) -> list[DispatchLedgerEntry]:
        self._ensure_store_dir_accessible()
        try:
            with os.scandir(self._store_dir) as it:
                names = sorted(entry.name for entry in it if entry.name.endswith(".json"))
        except OSError as e:
            raise SchedulerDispatchLedgerStoreReadError(f"enumeration failure: {e}") from e

        entries: list[DispatchLedgerEntry] = []
        for name in names:
            path = self._store_dir / name
            result = self._read_record_file(path)
            if result is None:
                raise SchedulerDispatchLedgerStoreReadError(
                    f"{name}: record disappeared between enumeration and read"
                )
            expected_name = f"{_sanitize_event_identity(result.event_identity)}.json"
            if expected_name != name:
                raise SchedulerDispatchLedgerStoreReadError(
                    f"{name}: filename/event_identity mismatch "
                    f"(record contains {result.event_identity!r} which sanitizes to {expected_name!r}); "
                    "possible filename collision"
                )
            entries.append(result)
        return entries


def _positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"invalid positive int value: {value!r}")
    if parsed <= 0:
        raise argparse.ArgumentTypeError(f"--limit must be a positive integer, got {parsed}")
    return parsed


def _filter_entries(
    entries: list[DispatchLedgerEntry], job_id: str | None, event_identity: str | None,
) -> list[DispatchLedgerEntry]:
    """list_recovery_required()の結果に対するin-memory filter（peek()/store.get()は使わない、設計書7章）。
    job_id・event_identityを同時指定した場合はAND条件として扱う。"""
    result = entries
    if job_id is not None:
        result = [e for e in result if e.job_id == job_id]
    if event_identity is not None:
        result = [e for e in result if e.event_identity == event_identity]
    return result


def _print_entry(entry: DispatchLedgerEntry) -> None:
    print(f"  job_id={entry.job_id}")
    print(f"    occurrence_minute={entry.occurrence_minute}")
    print(f"    event_identity={entry.event_identity}")
    print(f"    claimed_at={entry.claimed_at.isoformat()}")
    print(f"    updated_at={entry.updated_at.isoformat()}")
    # RECOVERY_REQUIRED entryは通常これら3フィールドがNoneだが、schemaで強制
    # された不変条件ではないため（設計書9章）、Noneでない場合のみ追加表示する。
    if entry.confirmed_at is not None:
        print(f"    confirmed_at={entry.confirmed_at.isoformat()}")
    if entry.dispatch_run_id is not None:
        print(f"    dispatch_run_id={entry.dispatch_run_id}")
    if entry.outcome_summary is not None:
        print(f"    outcome_summary={entry.outcome_summary}")


_GUIDANCE = """\
Manual Recovery Procedure（詳細: docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md 20章）:
  1. 上記の job_id / claimed_at 付近の時刻をキーに、Execution History を確認してください:
       ./venv/Scripts/python.exe scripts/show_execution_history.py
  2. 該当する WorkflowExecutionRecord の有無・内容を踏まえ、次のいずれの対応が適切かは
     運用者が判断してください（本CLIは判断を行いません）:
       - 記録が見つからない場合: 次回の同一Jobのスケジュールで自然にカバーされるか、
         以下のコマンドで手動補完実行するか
           ./venv/Scripts/python.exe scripts/run_workflow_engine.py --job-id <JOB_ID>
       - 記録が見つかる場合: 追加対応が必要かどうか

本CLIは診断情報の表示のみを行います。復旧の実行・判定（対応要否の判断を含む）・ledger状態の
変更は一切行いません。
本結果は実行時点のbest-effort readであり、単一時刻の一貫したsnapshotではありません
（実行中・実行後のRECOVERY_REQUIRED状態の変化は反映されません）。"""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Manual Recovery Diagnostic CLI（v6.36.0）: RECOVERY_REQUIRED occurrenceの読み取り専用診断"
    )
    parser.add_argument("--job-id", default=None, metavar="JOB_ID", help="job_id完全一致でfilterする")
    parser.add_argument(
        "--event-identity", default=None, metavar="EVENT_IDENTITY", help="event_identity完全一致でfilterする",
    )
    parser.add_argument("--limit", type=_positive_int, default=None, metavar="N", help="表示件数を制限する（正の整数）")
    args = parser.parse_args(argv)

    base_dir = Path(__file__).parent.parent
    config = SchedulerDispatchLedgerConfig.from_env(project_root=base_dir)

    store = _ReadOnlyDispatchLedgerStore(config.store_dir)
    ledger = SchedulerDispatchLedger(store=store, config=config)

    try:
        entries = ledger.list_recovery_required()
    except SchedulerDispatchLedgerStoreReadError as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        return 1

    entries = _filter_entries(entries, args.job_id, args.event_identity)
    entries = sorted(entries, key=lambda e: e.claimed_at)
    if args.limit is not None:
        entries = entries[: args.limit]

    print("=" * 50)
    print("Scheduler Recovery Diagnostic（RECOVERY_REQUIRED occurrence一覧）")
    print("=" * 50)
    if not entries:
        print("  該当するRECOVERY_REQUIRED occurrenceはありません。")
    else:
        for entry in entries:
            _print_entry(entry)
            print()

    print(_GUIDANCE)
    return 0


if __name__ == "__main__":
    sys.exit(main())
