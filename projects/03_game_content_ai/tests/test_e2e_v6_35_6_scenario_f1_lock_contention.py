"""
E2E テスト: Release 6.35 Scenario F Sub-case F1 — Lock Contention

Source of Truth:
    docs/design/mvp_end_to_end_hardening_validation.md 13.1章
    （Disposable Project Copy必須化・Triple-Gate必須化・Polling Contract）。

実`scripts/run_scheduler_driver.py`をDisposable Project Copy内で2回起動する
（1つ目は`--loop`付き、三重ゲート全て`true`）。1つ目がlockファイルを取得した
ことをexclusive file creation＋PID書き込みの2段階操作に耐えるPolling
Contract（13.1節）で確認してから、2つ目を起動しlock contentionを検証する。
production source（src/・scripts/・main.py）は一切変更しない。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_35_6_scenario_f1_lock_contention.py
"""
from __future__ import annotations

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
print("Release 6.35 Scenario F1: Lock Contention")
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
from e2e_support.process_liveness import (  # noqa: E402
    is_pid_alive,
    taskkill_tree,
    wait_for_pid_exit,
    wait_until,
)

RSS_SOURCE_NAMES = list(RSS_FEEDS.keys())

before_manifest = capture_manifest(PROJECT_ROOT)

stub = LocalStub(rss_source_names=RSS_SOURCE_NAMES).start()
stub.set_wordpress_expected_auth("test-dummy-user", "test-dummy-app-password")
copy = DisposableProjectCopy(PROJECT_ROOT).build()
appdata_dir = make_scenario_appdata_dir()
driver1_pid = None
proc1 = None
try:
    driver_script = copy.root / "scripts" / "run_scheduler_driver.py"
    lock_path = copy.root / ".run" / "scheduler_driver.lock"

    # APPDATAはscenario-owned empty directory（host実値ではない、
    # Post-Codex-delta-review AmendmentのMajor#3対応）。
    env = base_windows_vars(appdata_dir)
    env.update(
        {
            # ── Triple-Gate（13.1節、M5解決） ─────────────────────
            "SCHEDULER_DRIVER_ENABLED": "true",
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

    proc1 = subprocess.Popen(
        [str(copy.venv_python), str(driver_script), "--loop"],
        cwd=str(copy.root),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
    )
    driver1_pid = proc1.pid

    # ── Polling Contract（13.1節）：ファイル存在→内容が数値PID→PID生存の
    # 3点をリトライ付きpollingで確認してから2つ目を起動する ──────────
    def _lock_ready() -> bool:
        if not lock_path.exists():
            return False
        content = lock_path.read_text(encoding="utf-8").strip()
        if not content.isdigit():
            return False
        return is_pid_alive(int(content))

    lock_ready = wait_until(_lock_ready, timeout_sec=15, interval_sec=0.1)
    check_true("F1-1. 1つ目のdriverがlockファイルを取得する（Polling Contract）", lock_ready)

    lock_pid_text = lock_path.read_text(encoding="utf-8").strip() if lock_path.exists() else None
    # 【環境依存の実測結果・要報告】このvenvでは`subprocess.Popen`が返す
    # PID（proc1.pid）と、lockファイルへ実際に書き込まれるPID（起動された
    # python.exe自身のos.getpid()）が一致しない事例を実測した（Windows、
    # このvenvのpython.exe起動特性に起因すると見られる）。F1が実際に要求する
    # のは「lockファイルが実在のalive PIDを保持していること」のみであり、
    # `proc1.pid`との一致は本節の必須条件ではないため、厳密一致チェックは
    # 行わず、lock保持者自身のPIDが生存していることのみを確認する。
    check_true("F1-2. lockファイルの内容は生存中のPIDである", bool(lock_pid_text) and lock_pid_text.isdigit() and is_pid_alive(int(lock_pid_text)))

    proc2 = subprocess.run(
        [str(copy.venv_python), str(driver_script)],
        cwd=str(copy.root),
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )

    print("--- 2つ目のdriver stdout ---")
    print(proc2.stdout)

    check("F1-3. 2つ目のdriverはexit code 1でfail-closedに終了する", proc2.returncode, 1)
    check_true("F1-4. 2つ目のdriverのstdoutに[ERROR]が現れる", "[ERROR]" in proc2.stdout)
    check_true(
        "F1-5. 2つ目のdriverのstdoutにlock contentionを示す文言が現れる",
        ("既に別の" in proc2.stdout) or ("lock file:" in proc2.stdout),
    )
    check_true("F1-6. 2つ目のdriverはdispatchを行わない（exit 1で即終了、Prohibited Outcome対）", proc2.returncode != 0)

    check_true("F1-7. 1つ目のdriverはlock contention後も生存を続ける（早期解放されていない）", is_pid_alive(driver1_pid))
    # ── Post-Codex-delta-review Amendment（Minor#1対応）：lockファイルの
    # 内容を2つ目のdriver起動後にも再読し、記載PIDが生存し続けていることを
    # 確認する（proc1.pidとの一致は使わない、13.1節PID contract）。 ──────
    lock_pid_text_after = lock_path.read_text(encoding="utf-8").strip() if lock_path.exists() else None
    check(
        "F1-8a. lockファイルの内容は2つ目のdriver起動前後で変化しない（lock所有者が変わっていない）",
        lock_pid_text_after,
        lock_pid_text,
    )
    check_true(
        "F1-8b. 2つ目のdriver起動後も、lockファイル記載PIDは再読して生存していることを確認する",
        bool(lock_pid_text_after) and lock_pid_text_after.isdigit() and is_pid_alive(int(lock_pid_text_after)),
    )
finally:
    if driver1_pid is not None and is_pid_alive(driver1_pid):
        taskkill_tree(driver1_pid)
        wait_for_pid_exit(driver1_pid, timeout_sec=10)
    if proc1 is not None:
        try:
            proc1.communicate(timeout=5)
        except Exception:
            pass
    stub.stop()
    copy.teardown()
    cleanup_scenario_appdata_dir(appdata_dir)

after_manifest = capture_manifest(PROJECT_ROOT)
zero_diff_issues = diff_manifests(before_manifest, after_manifest)
check("F1-9. Original Projectはシナリオ実行前後でZero-Diff（差分なし）", zero_diff_issues, [])


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
