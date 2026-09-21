"""
E2E テスト: v6.36.0 Manual Recovery Diagnostic CLI Foundation

テストシナリオ（docs/design/manual_recovery_diagnostic_cli_foundation.md 15章
Test / E2E / Zero-Diff / Formal Regression方針 対応）:

    1.  RECOVERY_REQUIRED 0件時の正常終了（exit 0）
    2.  RECOVERY_REQUIRED N件時の一覧表示内容の正確性（claim()→reconcile_stale_claims()
        という実際のproduction経路でRECOVERY_REQUIREDを生成し、CLIが正しく表示すること）
    3.  --job-id / --event-identity filterの正確性（in-memory filter、AND条件）
    4.  store_dir未初期化時のfail-closed終了・ディレクトリ非作成の確認
    5.  store_dirが非ディレクトリ（ファイル）の場合のfail-closed終了
    6.  個別レコード破損時のSchedulerDispatchLedgerStoreReadError捕捉・診断失敗報告
    7.  CLIがSchedulerDriverのlock（.run/scheduler_driver.lock）・store lock
        （.store.lock）のいずれも作成・取得しないことの確認
    8.  _ReadOnlyDispatchLedgerStore.save()が書き込み不能なdefensive実装であることの確認
    9.  ソース静的チェック：claim()/confirm()/reconcile_stale_claims()/store.save()/
        peek()への呼び出しが本CLIのソースコード中に一切存在しないこと
    10. カスタムSCHEDULER_DISPATCH_LEDGER_DIR環境変数override確認（Config Bootstrap契約）
    11. --limitの正の整数契約・filter/ソート後に適用されることの確認
    12. confirmed_at/dispatch_run_id/outcome_summaryが非Noneの場合にそのまま表示されること
    13. filename/event_identity cross-check：get()相当・list_all()相当の両方で
        不一致entryを検出しSchedulerDispatchLedgerStoreReadErrorを送出すること
    14. JsonSchedulerDispatchLedgerStoreを一切import/使用しないことのソース静的チェック

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_36_0_manual_recovery_diagnostic_cli_foundation.py
"""
import ast
import contextlib
import importlib.util
import io
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

results_log = []


def check(label: str, actual, expected):
    ok = actual == expected
    status = "PASS" if ok else "FAIL"
    results_log.append((status, label))
    mark = "OK" if ok else "NG"
    print(f"  [{mark}] {label}")
    if not ok:
        print(f"       期待値: {expected!r}")
        print(f"       実際値: {actual!r}")


def check_true(label: str, value: bool):
    check(label, value, True)


print("=" * 60)
print("v6.36.0 Manual Recovery Diagnostic CLI Foundation E2E テスト")
print("=" * 60)
print()

from scheduler_dispatch_ledger import (
    DispatchLedgerEntry,
    DispatchPhase,
    JsonSchedulerDispatchLedgerStore,
    SchedulerDispatchLedger,
    SchedulerDispatchLedgerConfig,
    SchedulerDispatchLedgerStoreReadError,
)

SCRIPT_PATH = PROJECT_ROOT / "scripts" / "show_scheduler_recovery.py"
SCRIPT_SOURCE = SCRIPT_PATH.read_text(encoding="utf-8")

spec = importlib.util.spec_from_file_location("show_scheduler_recovery_under_test", SCRIPT_PATH)
cli_mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli_mod)


# ─── テスト用ユーティリティ ───

tmp_dirs: list[Path] = []


def make_tmp_ledger_dir() -> Path:
    tmp_root = Path(tempfile.mkdtemp())
    tmp_dirs.append(tmp_root)
    return tmp_root


@contextlib.contextmanager
def env_override(**kwargs):
    saved = {k: os.environ.get(k) for k in kwargs}
    try:
        for k, v in kwargs.items():
            os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def run_cli(argv: list[str] | None = None) -> tuple[int, str, str]:
    stdout_buf, stderr_buf = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(stdout_buf), contextlib.redirect_stderr(stderr_buf):
        try:
            code = cli_mod.main(argv or [])
        except SystemExit as e:
            code = e.code if isinstance(e.code, int) else 2
    return code, stdout_buf.getvalue(), stderr_buf.getvalue()


# ─── 1〜3: 実際のproduction claim()→reconcile_stale_claims()経路によるRECOVERY_REQUIRED生成 ───

ledger_dir_123 = make_tmp_ledger_dir()
config_123 = SchedulerDispatchLedgerConfig(ledger_dir=ledger_dir_123, store_lock_timeout_seconds=1.0)
store_123 = JsonSchedulerDispatchLedgerStore(config_123.store_dir)
ledger_123 = SchedulerDispatchLedger(store=store_123, config=config_123)

with env_override(SCHEDULER_DISPATCH_LEDGER_DIR=str(ledger_dir_123)):
    # 1. 0件時の正常終了
    code_1, stdout_1, _ = run_cli([])
    check("1a. RECOVERY_REQUIRED 0件時はexit 0", code_1, 0)
    check_true("1b. 0件時は「該当なし」メッセージを表示する", "該当するRECOVERY_REQUIRED" in stdout_1)

    # claim()→reconcile_stale_claims()でRECOVERY_REQUIREDを2件生成する
    claim_a = ledger_123.claim("job-alpha::2026-09-21T09:00", "job-alpha", "2026-09-21T09:00")
    claim_b = ledger_123.claim("job-beta::2026-09-21T09:05", "job-beta", "2026-09-21T09:05")
    check_true("setup. claim()が両方ともacknowledged=True", claim_a.acknowledged and claim_b.acknowledged)
    summary_123 = ledger_123.reconcile_stale_claims()
    check("setup. reconcile_stale_claims()が2件をRECOVERY_REQUIREDへ遷移", summary_123.recovery_marked, 2)

    # 2. N件時の一覧表示内容の正確性
    code_2, stdout_2, _ = run_cli([])
    check("2a. RECOVERY_REQUIRED 2件時はexit 0", code_2, 0)
    check_true("2b. job-alphaが表示される", "job_id=job-alpha" in stdout_2)
    check_true("2c. job-betaが表示される", "job_id=job-beta" in stdout_2)
    check_true("2d. occurrence_minuteが表示される", "occurrence_minute=2026-09-21T09:00" in stdout_2)
    check_true("2e. event_identityが表示される", "event_identity=job-alpha::2026-09-21T09:00" in stdout_2)
    check_true("2f. claimed_atが表示される", "claimed_at=" in stdout_2)
    check_true("2g. updated_atが表示される", "updated_at=" in stdout_2)
    check_true("2h. Manual Recovery Procedureの案内文が末尾に表示される", "show_execution_history.py" in stdout_2)
    check_true("2i. run_workflow_engine.py --job-id の案内が表示される", "run_workflow_engine.py --job-id" in stdout_2)
    check_true(
        "2j. 診断結果がsnapshotではない旨の限定文言が表示される",
        "best-effort read" in stdout_2 and "単一時刻の一貫したsnapshot" in stdout_2,
    )

    # 3. --job-id / --event-identity filter（AND条件）
    code_3a, stdout_3a, _ = run_cli(["--job-id", "job-alpha"])
    check("3a. --job-id filterはexit 0", code_3a, 0)
    check_true("3b. --job-id=job-alphaはjob-alphaのみ含む", "job_id=job-alpha" in stdout_3a)
    check_true("3c. --job-id=job-alphaはjob-betaを含まない", "job_id=job-beta" not in stdout_3a)

    code_3b, stdout_3b, _ = run_cli(["--event-identity", "job-beta::2026-09-21T09:05"])
    check_true("3d. --event-identityはjob-betaのみ含む", "job_id=job-beta" in stdout_3b and "job_id=job-alpha" not in stdout_3b)

    code_3c, stdout_3c, _ = run_cli(["--job-id", "job-alpha", "--event-identity", "job-beta::2026-09-21T09:05"])
    check_true(
        "3e. --job-id と --event-identity 同時指定はAND条件で該当0件になる",
        "該当するRECOVERY_REQUIRED" in stdout_3c,
    )

    # 11. --limit契約
    code_11a, stdout_11a, stderr_11a = run_cli(["--limit", "1"])
    check("11a. --limit 1 はexit 0", code_11a, 0)
    check("11b. --limit 1 は1件のみ表示する（job_id=行の出現数）", stdout_11a.count("  job_id="), 1)
    code_11c, _, _ = run_cli(["--limit", "0"])
    check("11c. --limit 0 はargparseエラー（SystemExit 2）", code_11c, 2)
    code_11d, _, _ = run_cli(["--limit", "-1"])
    check("11d. --limit -1 はargparseエラー（SystemExit 2）", code_11d, 2)


# ─── 4: store_dir未初期化時のfail-closed終了・ディレクトリ非作成 ───

ledger_dir_4 = make_tmp_ledger_dir()
store_dir_4 = ledger_dir_4 / "entries"
check_true("setup. テスト4のstore_dirはまだ存在しない", not store_dir_4.exists())
with env_override(SCHEDULER_DISPATCH_LEDGER_DIR=str(ledger_dir_4)):
    code_4, stdout_4, stderr_4 = run_cli([])
check("4a. store_dir未初期化時はexit 1", code_4, 1)
check_true("4b. エラーメッセージがstderrに出力される", "does not exist" in stderr_4)
check_true("4c. store_dirは実行後も作成されていない（mkdir回避の直接証拠）", not store_dir_4.exists())
check_true("4d. ledger_dir自体も作成されていない", not ledger_dir_4.exists() or not any(ledger_dir_4.iterdir()))


# ─── 5: store_dirが非ディレクトリ（ファイル）の場合のfail-closed終了 ───

ledger_dir_5 = make_tmp_ledger_dir()
store_dir_5 = ledger_dir_5 / "entries"
store_dir_5.parent.mkdir(parents=True, exist_ok=True)
store_dir_5.write_text("not a directory", encoding="utf-8")
with env_override(SCHEDULER_DISPATCH_LEDGER_DIR=str(ledger_dir_5)):
    code_5, _, stderr_5 = run_cli([])
check("5a. store_dirが非ディレクトリの場合はexit 1", code_5, 1)
check_true("5b. エラーメッセージがstderrに出力される", "not a real directory" in stderr_5)


# ─── 6: 個別レコード破損時のfail-closed診断 ───

ledger_dir_6 = make_tmp_ledger_dir()
config_6 = SchedulerDispatchLedgerConfig(ledger_dir=ledger_dir_6, store_lock_timeout_seconds=1.0)
config_6.store_dir.mkdir(parents=True, exist_ok=True)
(config_6.store_dir / "corrupt.json").write_text("{not valid json", encoding="utf-8")
with env_override(SCHEDULER_DISPATCH_LEDGER_DIR=str(ledger_dir_6)):
    code_6, _, stderr_6 = run_cli([])
check("6a. 破損recordが存在する場合はexit 1（部分結果を返さない）", code_6, 1)
check_true("6b. エラーメッセージがstderrに出力される", len(stderr_6.strip()) > 0)


# ─── 7: CLIがlockを一切作成・取得しないことの確認 ───

with env_override(SCHEDULER_DISPATCH_LEDGER_DIR=str(ledger_dir_123)):
    run_cli([])
check_true(
    "7a. store lock（.store.lock）が作成されていない",
    not (ledger_dir_123 / ".store.lock").exists(),
)
check_true(
    "7b. SchedulerDriverの起動用lock（.run/scheduler_driver.lock）が作成されていない",
    not (PROJECT_ROOT / ".run" / "scheduler_driver.lock").exists(),
)


# ─── 8: _ReadOnlyDispatchLedgerStore.save()の防御的実装 ───

ledger_dir_8 = make_tmp_ledger_dir()
store_8 = cli_mod._ReadOnlyDispatchLedgerStore(ledger_dir_8 / "entries")
dummy_entry_8 = DispatchLedgerEntry(
    event_identity="dummy::2026-09-21T00:00", job_id="dummy", occurrence_minute="2026-09-21T00:00",
    phase=DispatchPhase.RECOVERY_REQUIRED, claimed_at=datetime(2026, 9, 21), updated_at=datetime(2026, 9, 21),
)
threw_8 = False
try:
    store_8.save(dummy_entry_8)
except NotImplementedError:
    threw_8 = True
check_true("8a. save()呼び出しはNotImplementedErrorを送出する", threw_8)
check_true("8b. save()呼び出し後もディレクトリを作成していない", not (ledger_dir_8 / "entries").exists())


# ─── 9・14: ソース静的チェック（AST解析、docstring中の説明文を誤検出しない） ───

_AST_TREE = ast.parse(SCRIPT_SOURCE, filename=str(SCRIPT_PATH))


def _collect_all_referenced_names(tree: ast.AST) -> set[str]:
    """Name参照（呼び出しの有無を問わない）・Attribute参照（呼び出しの有無を
    問わない）・import対象名をすべて集める（docstring中の文字列は対象外、
    defの関数名自体はast.FunctionDef.nameという別属性でありast.Name/
    ast.Attributeノードとしては現れないため対象外——Codex Round 2対応：
    Callノード×Attributeのみに限定していた旧版は、`f = obj.claim; f(...)`の
    ようなbound-alias経由の呼び出しやast.Name経由の呼び出しを見逃しうる
    ため、Call有無を問わずNameのid・Attributeのattrをすべて収集する方式へ
    強化した）。"""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            names.add(node.id)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
        elif isinstance(node, (ast.ImportFrom, ast.Import)):
            for alias in node.names:
                names.add(alias.name)
    return names


_referenced_names = _collect_all_referenced_names(_AST_TREE)

check_true("9a. ソース中に claim という識別子参照が存在しない", "claim" not in _referenced_names)
check_true("9b. ソース中に confirm という識別子参照が存在しない", "confirm" not in _referenced_names)
check_true(
    "9c. ソース中に reconcile_stale_claims という識別子参照が存在しない",
    "reconcile_stale_claims" not in _referenced_names,
)
check_true(
    "9d. ソース中に save という識別子参照が存在しない"
    "（_ReadOnlyDispatchLedgerStore.save()自身のFunctionDef名は"
    "ast.Name/ast.Attributeノードとして現れないためこの集合に含まれない）",
    "save" not in _referenced_names,
)
check_true("9e. ソース中に peek という識別子参照が存在しない", "peek" not in _referenced_names)


# ─── 10: カスタムSCHEDULER_DISPATCH_LEDGER_DIR環境変数override（Config Bootstrap契約） ───

check_true(
    "10. 環境変数SCHEDULER_DISPATCH_LEDGER_DIRを設定した場合、CLIが正しくそのディレクトリを"
    "診断していること（テスト1〜3が全てledger_dir_123へ書いたentryを正しく検出できていた"
    "こと自体が、main()内でload_dotenv()前にSchedulerDispatchLedgerConfig.from_env()を"
    "呼んでいない、または呼ぶ順序が正しいことの実証的証拠となる）",
    "job_id=job-alpha" in stdout_2,
)


# ─── 12: confirmed_at等の非None付随フィールド表示 ───

ledger_dir_12 = make_tmp_ledger_dir()
store_12 = JsonSchedulerDispatchLedgerStore((ledger_dir_12 / "entries"))
entry_12 = DispatchLedgerEntry(
    event_identity="job-gamma::2026-09-21T10:00", job_id="job-gamma", occurrence_minute="2026-09-21T10:00",
    phase=DispatchPhase.RECOVERY_REQUIRED, claimed_at=datetime(2026, 9, 21, 10, 0),
    confirmed_at=datetime(2026, 9, 21, 10, 1), dispatch_run_id="run-xyz", outcome_summary="overall_success=True",
    updated_at=datetime(2026, 9, 21, 10, 1),
)
check_true("setup. 非None付随フィールドを持つentryの保存に成功", store_12.save(entry_12))
with env_override(SCHEDULER_DISPATCH_LEDGER_DIR=str(ledger_dir_12)):
    code_12, stdout_12, _ = run_cli([])
check("12a. 非None付随フィールドを持つentryでもexit 0（エラーにしない）", code_12, 0)
check_true("12b. confirmed_atがそのまま表示される", "confirmed_at=2026-09-21T10:01:00" in stdout_12)
check_true("12c. dispatch_run_idがそのまま表示される", "dispatch_run_id=run-xyz" in stdout_12)
check_true("12d. outcome_summaryがそのまま表示される", "outcome_summary=overall_success=True" in stdout_12)


# ─── 13: filename/event_identity cross-check（get()相当・list_all()相当の両方） ───

ledger_dir_13 = make_tmp_ledger_dir()
store_dir_13 = ledger_dir_13 / "entries"
store_dir_13.mkdir(parents=True, exist_ok=True)
adapter_13 = cli_mod._ReadOnlyDispatchLedgerStore(store_dir_13)

# 13a: list_all()相当 — ファイル名とrecord内容のevent_identityが不一致
mismatched_record = {
    "event_identity": "job-real::2026-09-21T11:00", "job_id": "job-real", "occurrence_minute": "2026-09-21T11:00",
    "phase": "recovery_required", "claimed_at": "2026-09-21T11:00:00", "confirmed_at": None,
    "dispatch_run_id": None, "outcome_summary": None, "detail": None, "updated_at": "2026-09-21T11:00:00",
}
# 単射なsanitize結果とは異なる、意図的に誤ったファイル名で保存する
(store_dir_13 / "wrong_filename.json").write_text(json.dumps(mismatched_record), encoding="utf-8")
threw_13a = False
try:
    adapter_13.list_all()
except SchedulerDispatchLedgerStoreReadError:
    threw_13a = True
check_true("13a. list_all()相当：filename/event_identity不一致をfail-closedで検出する", threw_13a)
(store_dir_13 / "wrong_filename.json").unlink()

# 13b: get()相当 — 要求したevent_identityのファイルパスに、別のevent_identityを名乗るrecordが存在する
from scheduler_dispatch_ledger.scheduler_dispatch_ledger_store import _sanitize_event_identity

requested_identity = "job-requested::2026-09-21T12:00"
path_for_requested = store_dir_13 / f"{_sanitize_event_identity(requested_identity)}.json"
other_record = {
    "event_identity": "job-other::2026-09-21T12:00", "job_id": "job-other", "occurrence_minute": "2026-09-21T12:00",
    "phase": "recovery_required", "claimed_at": "2026-09-21T12:00:00", "confirmed_at": None,
    "dispatch_run_id": None, "outcome_summary": None, "detail": None, "updated_at": "2026-09-21T12:00:00",
}
path_for_requested.write_text(json.dumps(other_record), encoding="utf-8")
threw_13b = False
try:
    adapter_13.get(requested_identity)
except SchedulerDispatchLedgerStoreReadError:
    threw_13b = True
check_true("13b. get()相当：要求identityとrecord内容の不一致をfail-closedで検出する", threw_13b)


# ─── 13c/13d: 非regular-fileの拒否（Codex Independent Code Review Major対応、新規） ───
# Windows環境ではsymlink作成に管理者権限/Developer Modeを要することがあるため、
# 移植性の高い「ファイルを期待する場所にディレクトリが存在する」ケースで
# stat.S_ISREG()検査（store.py既存契約と同型）を直接検証する。

ledger_dir_13c = make_tmp_ledger_dir()
store_dir_13c = ledger_dir_13c / "entries"
store_dir_13c.mkdir(parents=True, exist_ok=True)
# "*.json"という名前だが実体はディレクトリ（regular fileではない）
(store_dir_13c / "not_a_real_file.json").mkdir()
adapter_13c = cli_mod._ReadOnlyDispatchLedgerStore(store_dir_13c)
threw_13c = False
try:
    adapter_13c.list_all()
except SchedulerDispatchLedgerStoreReadError:
    threw_13c = True
check_true(
    "13c. list_all()相当：regular fileでないエントリ（ディレクトリ）をfail-closedで拒否する",
    threw_13c,
)

ledger_dir_13d = make_tmp_ledger_dir()
store_dir_13d = ledger_dir_13d / "entries"
store_dir_13d.mkdir(parents=True, exist_ok=True)
requested_identity_13d = "job-nonregular::2026-09-21T13:00"
path_13d = store_dir_13d / f"{_sanitize_event_identity(requested_identity_13d)}.json"
path_13d.mkdir()
adapter_13d = cli_mod._ReadOnlyDispatchLedgerStore(store_dir_13d)
threw_13d = False
try:
    adapter_13d.get(requested_identity_13d)
except SchedulerDispatchLedgerStoreReadError:
    threw_13d = True
check_true(
    "13d. get()相当：regular fileでないエントリ（ディレクトリ）をfail-closedで拒否する",
    threw_13d,
)


# ─── 13e: S_ISREG検査自体が拒否の根拠であることの直接証明 ───
# （Codex Independent Code Review Round 2 Major対応：13c/13dはディレクトリを
# 使うため、Path.read_text()自体がOSErrorを送出し、S_ISREG検査を削除しても
# 別経路（OSError捕捉）で同じ結果になってしまい、S_ISREG検査自体の有無を
# 判別できないという指摘を受けた。os.lstat()をmockし、実体は正常に読み取り
# 可能な正当なJSONファイルでありながらst_modeだけを非regular値に差し替える
# ことで、read_text()自体は成功しうる状況下でもS_ISREG検査が拒否の唯一の
# 根拠であることを直接証明する。）

ledger_dir_13e = make_tmp_ledger_dir()
store_dir_13e = ledger_dir_13e / "entries"
store_dir_13e.mkdir(parents=True, exist_ok=True)
fake_identity_13e = "job-fakenonregular::2026-09-21T14:00"
valid_record_13e = {
    "event_identity": fake_identity_13e, "job_id": "job-fakenonregular",
    "occurrence_minute": "2026-09-21T14:00", "phase": "recovery_required",
    "claimed_at": "2026-09-21T14:00:00", "confirmed_at": None, "dispatch_run_id": None,
    "outcome_summary": None, "detail": None, "updated_at": "2026-09-21T14:00:00",
}
record_path_13e = store_dir_13e / f"{_sanitize_event_identity(fake_identity_13e)}.json"
record_path_13e.write_text(json.dumps(valid_record_13e), encoding="utf-8")

import stat as stat_module

_original_lstat = cli_mod.os.lstat


def _fake_lstat_non_regular(path, *args, **kwargs):
    result = _original_lstat(path, *args, **kwargs)
    if Path(path) == record_path_13e:
        # st_modeのファイル種別ビットのみをS_IFCHR（キャラクタデバイス、
        # regular fileではない値）へ差し替えた偽のstat_resultを返す
        # （ファイル自体は変更しない、read_text()は引き続き成功しうる）。
        fake_mode = (result.st_mode & ~stat_module.S_IFMT(result.st_mode)) | stat_module.S_IFCHR
        return os.stat_result((fake_mode,) + tuple(result)[1:])
    return result


adapter_13e = cli_mod._ReadOnlyDispatchLedgerStore(store_dir_13e)
cli_mod.os.lstat = _fake_lstat_non_regular
try:
    threw_13e = False
    try:
        adapter_13e.list_all()
    except SchedulerDispatchLedgerStoreReadError:
        threw_13e = True
finally:
    cli_mod.os.lstat = _original_lstat
check_true(
    "13e. list_all()相当：st_modeが非regularを示す場合、実体が正当な"
    "読み取り可能JSONであってもS_ISREG検査によりfail-closedで拒否される"
    "（S_ISREG検査自体が拒否の根拠であることの直接証明）",
    threw_13e,
)


# ─── 14: JsonSchedulerDispatchLedgerStoreを一切import/使用せず、mkdir呼び出しも持たないことのAST静的チェック ───

check_true(
    "14a. ソース中でJsonSchedulerDispatchLedgerStoreをimport/参照していない",
    "JsonSchedulerDispatchLedgerStore" not in _referenced_names,
)
check_true(
    "14b. ソース中にmkdir/mkdirsという識別子参照が存在しない（_ReadOnlyDispatchLedgerStoreがmkdirを呼ばないことの直接証拠）",
    "mkdir" not in _referenced_names and "mkdirs" not in _referenced_names,
)


# ─── 後片付け ───
for d in tmp_dirs:
    shutil.rmtree(d, ignore_errors=True)


# ─── 結果サマリー ───
print()
print("=" * 60)
total = len(results_log)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = total - passed
print(f"合計: {passed}/{total} PASS  /  {failed} FAIL")
print("=" * 60)

if failed > 0:
    print()
    print("FAILしたテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
else:
    print("全テスト PASS")
