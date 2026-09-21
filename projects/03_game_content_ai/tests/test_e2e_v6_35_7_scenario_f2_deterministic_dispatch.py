"""
E2E テスト: Release 6.35 Scenario F Sub-case F2 — Deterministic
Dispatch/Restart/Same-Minute Tick

Source of Truth:
    docs/design/mvp_end_to_end_hardening_validation.md 13.2章
    （restart証跡の必須化・lock所有権契約の明示・Dispatch Ledgerディレクトリの
    共有経路）。

`SchedulerDriverOrchestrator`をtest-onlyコード（tests/e2e_support/
scenario_f2_worker.py、T10）から直接構築し、固定`ClockProvider`と
`TriggerType.ONCE`の決定的Job定義を注入する（CLIスクリプト非経由）。
同一event_identityに対する`WorkflowEngineManager.run()`呼び出しが、
same-minute tick（同一プロセス内で`run_once()`を複数回）・restart
（新規プロセスとして再起動）のいずれでも1回のみであることを検証する。
production source（src/・scripts/・main.py）は一切変更しない。

Post-Codex-delta-review Amendment（Major#4対応）：dispatch ledger dirを
argv経由のdirect dataclass構築ではなく、既存の環境変数
`SCHEDULER_DISPATCH_LEDGER_DIR`（`SchedulerDispatchLedgerConfig.from_env()`）
経由でworker起動時envから渡すよう変更した。あわせて、CLAIMED→CONFIRMEDの
単一seriesであることをdispatch ledgerストアの直接読み取りでassertする
ようにした。APPDATAはscenario-owned empty directory（Major#3対応）。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_35_7_scenario_f2_deterministic_dispatch.py
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tests"))
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
    check(label, bool(value), True)


print("=" * 60)
print("Release 6.35 Scenario F2: Deterministic Dispatch / Restart / Same-Minute Tick")
print("=" * 60)
print()

from collector import RSS_FEEDS  # noqa: E402
from e2e_support.disposable_copy import (  # noqa: E402
    DisposableProjectCopy,
    capture_manifest,
    diff_manifests,
)
from e2e_support.env_contract import (  # noqa: E402
    base_windows_vars,
    cleanup_scenario_appdata_dir,
    make_scenario_appdata_dir,
)
from e2e_support.local_stub import LocalStub  # noqa: E402

from scheduler_dispatch_ledger import (  # noqa: E402
    DispatchPhase,
    JsonSchedulerDispatchLedgerStore,
    SchedulerDispatchLedgerConfig,
)

RSS_SOURCE_NAMES = list(RSS_FEEDS.keys())
ARTICLE_SOURCE = RSS_SOURCE_NAMES[0]
WORKER_SCRIPT = PROJECT_ROOT / "tests" / "e2e_support" / "scenario_f2_worker.py"
FIXED_NOW = "2026-01-01T00:00"


def read_ledger_entries(ledger_dir: Path):
    """dispatch ledgerストアを直接読み取る（Major#4対応、13.2節）。"""
    store = JsonSchedulerDispatchLedgerStore(SchedulerDispatchLedgerConfig(ledger_dir=ledger_dir).store_dir)
    return store.list_all()


before_manifest = capture_manifest(PROJECT_ROOT)

stub = LocalStub(rss_source_names=RSS_SOURCE_NAMES).start()
stub.set_wordpress_expected_auth("test-dummy-user", "test-dummy-app-password")
copy = DisposableProjectCopy(PROJECT_ROOT).build()
appdata_dir = make_scenario_appdata_dir()

try:
    stub.set_rss_fixed_items(
        ARTICLE_SOURCE,
        [
            {
                "title": "Nintendo Switch 2 発売決定、価格と発売日を発表",
                "link": "http://127.0.0.1/articles/switch2-announced",
                "description": "任天堂は新型Switchの発売を正式発表した。",
            }
        ],
    )
    stub.set_wordpress_response(
        201,
        {
            "id": 8484,
            "slug": "switch2-announced",
            "status": "draft",
            "title": {"rendered": "Nintendo Switch 2 発売決定"},
            "link": "http://127.0.0.1/?p=8484",
        },
    )

    base_env = base_windows_vars(appdata_dir)
    base_env.update(
        {
            "AI_AGENT_ENABLED": "true",
            "WORKFLOW_ENGINE_ENABLED": "true",
            "NEWS_AGENT_MIN_INTERVAL_MINUTES": "0",
            "WP_SITE_URL": stub.base_url,
            "ANTHROPIC_BASE_URL": stub.base_url,
            "NEWS_RSS_FEED_URLS_OVERRIDE": stub.rss_override_json(),
            "ANTHROPIC_API_KEY": "sk-test-dummy-0000000000000000000000000000000000000000",
            "WP_USERNAME": "test-dummy-user",
            "WP_APP_PASSWORD": "test-dummy-app-password",
            "NO_PROXY": "127.0.0.1,localhost",
            "PYTHON_DOTENV_DISABLED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )

    def run_worker(lock_path: Path, ledger_dir: Path, job_id: str, tick_count: int, result_path: Path):
        # ── Major#4対応：dispatch ledger dirはSCHEDULER_DISPATCH_LEDGER_DIR
        # 環境変数経由でworkerへ渡す（13.2節、既存の環境変数を使うだけで足りる）。
        env = dict(base_env)
        env["SCHEDULER_DISPATCH_LEDGER_DIR"] = str(ledger_dir)
        return subprocess.run(
            [str(copy.venv_python), str(WORKER_SCRIPT), str(copy.root), str(lock_path), FIXED_NOW, str(tick_count), job_id, str(result_path)],
            cwd=str(copy.root),
            env=env,
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=120,
        )

    def count_dispatched(tick: dict) -> int:
        return sum(1 for d in tick["dispatched"] if d["dispatched"])

    def count_skipped_same_identity(tick: dict) -> int:
        return len(tick["skipped"])

    # =================================================================
    # Part 1: Same-Minute Tick（同一プロセス内でrun_once()を3回）
    # =================================================================
    print("[F2-Part1] Same-Minute Tick")
    scratch = copy.root.parent / "f2_scratch"
    scratch.mkdir(parents=True, exist_ok=True)
    lock_path_a = scratch / "lock_a.lock"
    ledger_dir_a = scratch / "ledger_a"
    result_path_a = scratch / "result_a.json"

    proc_a = run_worker(lock_path_a, ledger_dir_a, "f2-tick-job", 3, result_path_a)
    if proc_a.returncode != 0:
        print("--- worker A stderr ---")
        print(proc_a.stderr)
    check("F2-1. same-minute tick workerはexit code 0で終了する", proc_a.returncode, 0)

    ticks_a = json.loads(result_path_a.read_text(encoding="utf-8"))["ticks"] if result_path_a.exists() else []
    check("F2-2. run_once()が3回分の結果を返す", len(ticks_a), 3)

    total_dispatched_a = sum(count_dispatched(t) for t in ticks_a)
    check("F2-3. 3回のtickの中で実際にdispatchされたのはちょうど1回のみ", total_dispatched_a, 1)

    check_true("F2-4. 1回目のtickでdispatchされる", ticks_a and count_dispatched(ticks_a[0]) == 1)
    check_true(
        "F2-5. 2回目・3回目のtickは同一event_identityのため重複dispatchされない（skipped扱い）",
        len(ticks_a) >= 3 and count_dispatched(ticks_a[1]) == 0 and count_dispatched(ticks_a[2]) == 0,
    )

    wp_count_after_part1 = len(stub.wordpress_requests())
    check("F2-6. WordPress Local Stubはsame-minute tick全体でちょうど1回のPOSTを受信する", wp_count_after_part1, 1)

    # ── Post-Codex-delta-review Amendment（Major#4対応）：dispatch ledger
    # ストア自体を直接読み取り、CLAIMED→CONFIRMEDの単一seriesであることを
    # assertする（13.2節）。 ─────────────────────────────────────────
    event_identity_a = f"f2-tick-job::{FIXED_NOW}"
    ledger_entries_a = read_ledger_entries(ledger_dir_a)
    matching_entries_a = [e for e in ledger_entries_a if e.event_identity == event_identity_a]
    check("F2-6a. dispatch ledgerにevent_identityあたりちょうど1件のみ存在する（単一series）", len(matching_entries_a), 1)
    if matching_entries_a:
        check("F2-6b. ledger entryの最終phaseはCONFIRMED（CLAIMED→CONFIRMEDの単一series）", matching_entries_a[0].phase, DispatchPhase.CONFIRMED)
        check_true("F2-6c. ledger entryのconfirmed_atが設定されている", matching_entries_a[0].confirmed_at is not None)
    print()

    # =================================================================
    # Part 2: Restart（2つの独立プロセス、同一lock_path/ledger_dirを再利用）
    # =================================================================
    print("[F2-Part2] Restart")
    lock_path_b = scratch / "lock_b.lock"
    ledger_dir_b = scratch / "ledger_b"
    result_path_b1 = scratch / "result_b1.json"
    result_path_b2 = scratch / "result_b2.json"

    proc_b1 = run_worker(lock_path_b, ledger_dir_b, "f2-restart-job", 1, result_path_b1)
    if proc_b1.returncode != 0:
        print("--- worker B1 stderr ---")
        print(proc_b1.stderr)
    check("F2-7. 1回目のworker（restart前）はexit code 0で終了する", proc_b1.returncode, 0)
    check_true("F2-8. 1回目のworker終了後、lockファイルは解放されている（release()実行済み）", not lock_path_b.exists())

    ticks_b1 = json.loads(result_path_b1.read_text(encoding="utf-8"))["ticks"] if result_path_b1.exists() else []
    check("F2-9. 1回目のworkerでdispatchされる", count_dispatched(ticks_b1[0]) if ticks_b1 else 0, 1)

    # ── restart：新規プロセスとして再起動し、同じdispatch ledgerを再読み込み ──
    proc_b2 = run_worker(lock_path_b, ledger_dir_b, "f2-restart-job", 1, result_path_b2)
    if proc_b2.returncode != 0:
        print("--- worker B2 stderr ---")
        print(proc_b2.stderr)
    check("F2-10. 2回目のworker（restart後、新規プロセス）もexit code 0で終了する", proc_b2.returncode, 0)

    ticks_b2 = json.loads(result_path_b2.read_text(encoding="utf-8"))["ticks"] if result_path_b2.exists() else []
    check(
        "F2-11. restart後の2回目のworkerは同一event_identityを重複dispatchしない",
        count_dispatched(ticks_b2[0]) if ticks_b2 else -1,
        0,
    )
    check_true("F2-12. restart後もlockファイルは解放されている", not lock_path_b.exists())

    wp_count_after_part2 = len(stub.wordpress_requests()) - wp_count_after_part1
    check("F2-13. restart全体（2プロセス）を通じてWordPress POSTはちょうど1回のみ", wp_count_after_part2, 1)

    event_identity_b = f"f2-restart-job::{FIXED_NOW}"
    ledger_entries_b = read_ledger_entries(ledger_dir_b)
    matching_entries_b = [e for e in ledger_entries_b if e.event_identity == event_identity_b]
    check("F2-13a. restart全体を通じてevent_identityあたりちょうど1件のみ存在する（単一series）", len(matching_entries_b), 1)
    if matching_entries_b:
        check("F2-13b. ledger entryの最終phaseはCONFIRMED（CLAIMED→CONFIRMEDの単一series）", matching_entries_b[0].phase, DispatchPhase.CONFIRMED)
        check_true("F2-13c. ledger entryのconfirmed_atが設定されている", matching_entries_b[0].confirmed_at is not None)

    check(
        "F2-13d. WordPress POSTが認証/payload検証で拒否された事例はない（Major#5対応）",
        stub.wordpress_rejections(),
        [],
    )
finally:
    stub.stop()
    copy.teardown()
    cleanup_scenario_appdata_dir(appdata_dir)

after_manifest = capture_manifest(PROJECT_ROOT)
zero_diff_issues = diff_manifests(before_manifest, after_manifest)
check("F2-14. Original Projectはシナリオ実行前後でZero-Diff（差分なし）", zero_diff_issues, [])


print()
print("=" * 60)
passed = sum(1 for s, _ in results_log if s == "PASS")
failed = sum(1 for s, _ in results_log if s == "FAIL")
print(f"結果: {passed} PASS / {failed} FAIL / 合計 {len(results_log)}")
if failed:
    print("失敗したテスト:")
    for s, label in results_log:
        if s == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
print("全テストPASS")
