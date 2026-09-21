"""
E2E テスト: Release 6.35 Scenario A — normal success → WordPress Draft

Source of Truth:
    docs/design/mvp_end_to_end_hardening_validation.md 8章（8.1/8.2節、
    Post-Round 10 Amendmentで正式契約本文を確定済み）。本テストはその
    8.1節契約（Precondition/Runtime Path/Failure Injection/Durable-
    Observable Assertions/Prohibited Outcome/Isolation-Cleanup）の実装で
    ある。P2実装・Scenario Cのproduction seam追加は範囲外（禁止事項どおり、
    本テストのみを対象とする）。

    Post-Codex-delta-review Amendment（Major#3・#5対応）：APPDATAをhost実値
    ではなくscenario-owned empty directoryへ変更し、WordPress Local Stubへ
    POST成功前の認証/payload検証を追加した。

対象：test-only helper（tests/e2e_support/）のみ。production source
（src/・scripts/・main.py）は一切変更しない。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_35_1_scenario_a_normal_success.py
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
print("Release 6.35 Scenario A: normal success -> WordPress Draft")
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

RSS_SOURCE_NAMES = list(RSS_FEEDS.keys())
ARTICLE_SOURCE = RSS_SOURCE_NAMES[0]


def build_worker_env(stub: LocalStub, appdata_dir) -> dict:
    """7.5.1/7.5.1a/7.5.2/7.5.5節のControlled Upstream Boundaryのみを満たす
    env。Scenario Aはmain.pyを直接起動するだけであり、AI_AGENT_ENABLED等の
    Retry Runtime三重ゲートは一切必要ない（main.py自身はNewsAgent/
    WorkflowEngineManagerを経由しない、単一entrypointのスクリプトである、
    docs/design/...7.5.1a節・main.py制御フロー確認済み）。

    APPDATAはscenario-owned empty directory（host実値ではない、
    Post-Codex-delta-review AmendmentのMajor#3対応、10.5節(a)）。
    インストール済みAnthropic SDKが`pathlib.Path.home()`経由で資格情報
    ディレクトリを探索する際に要求するため必要（10.5節(a)後段）。"""
    env = base_windows_vars(appdata_dir)
    env["NO_PROXY"] = "127.0.0.1,localhost"
    env["WP_SITE_URL"] = stub.base_url
    env["ANTHROPIC_BASE_URL"] = stub.base_url
    env["NEWS_RSS_FEED_URLS_OVERRIDE"] = stub.rss_override_json()
    env["ANTHROPIC_API_KEY"] = "sk-test-dummy-0000000000000000000000000000000000000000"
    env["WP_USERNAME"] = "test-dummy-user"
    env["WP_APP_PASSWORD"] = "test-dummy-app-password"
    env["PYTHON_DOTENV_DISABLED"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    # main.pyの日本語print出力をcp932（既定ロケール）ではなくUTF-8で
    # 一貫してやり取りするため（テストハーネス側のcapture_output=Trueが
    # cp932でdecodeしようとしてUnicodeDecodeErrorになるのを防ぐ）。
    env["PYTHONIOENCODING"] = "utf-8"
    return env


# ── Zero-Diff証拠契約：Original Project側の実行前manifest ──────────
before_manifest = capture_manifest(PROJECT_ROOT)

stub = LocalStub(rss_source_names=RSS_SOURCE_NAMES).start()
copy = DisposableProjectCopy(PROJECT_ROOT).build()
appdata_dir = make_scenario_appdata_dir()
try:
    # ── Failure Injection ではなく正常系fixture ──────────────────
    # filter_news()（src/keyword_filter.py）のPRIORITY_KEYWORDSを実際に
    # 通過する記事1件のみを1ソースへ配置し、残り15ソースは空のまま。
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
            "id": 4242,
            "slug": "switch2-announced",
            "status": "draft",
            "title": {"rendered": "Nintendo Switch 2 発売決定"},
            "link": "http://127.0.0.1/?p=4242",
        },
    )
    # ── Post-Codex-delta-review Amendment（Major#5対応）：POST成功前に
    # Basic認証・必須payload・status固定値を検証する（7.5.5節） ──────────
    stub.set_wordpress_expected_auth("test-dummy-user", "test-dummy-app-password")

    env = build_worker_env(stub, appdata_dir)
    proc = subprocess.run(
        [str(copy.venv_python), str(copy.main_py)],
        cwd=str(copy.root),
        env=env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=120,
    )

    print("--- main.py stdout (tail) ---")
    print("\n".join(proc.stdout.splitlines()[-20:]))
    if proc.returncode != 0:
        print("--- main.py stderr ---")
        print(proc.stderr)

    check("A1. main.pyはexit code 0（全件成功）で終了する", proc.returncode, 0)
    check(
        "A2. 記事を含む1ソースはfetchが実際に発生する（request_count>=1）",
        stub.rss_request_count(ARTICLE_SOURCE) >= 1,
        True,
    )
    check(
        "A3. 空の15ソースも1回はfetchされる（全16フィード走査、override経由）",
        all(
            stub.rss_request_count(name) >= 1
            for name in RSS_SOURCE_NAMES
            if name != ARTICLE_SOURCE
        ),
        True,
    )

    wp_requests = stub.wordpress_requests()
    check("A4. WordPress Local StubはPOSTをちょうど1回受信する", len(wp_requests), 1)
    if wp_requests:
        auth_header = wp_requests[0].headers.get("Authorization", "")
        check_true("A5. WordPress POSTにBasic認証ヘッダが付与されている", auth_header.startswith("Basic "))
        try:
            payload = json.loads(wp_requests[0].body.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            payload = {}
        check_true("A6. WordPress POST bodyにtitleが含まれる", bool(payload.get("title")))
        check(
            "A7. WordPress POST bodyのstatusはdraft固定である",
            payload.get("status"),
            "draft",
        )

    check_true(
        "A8. Anthropic Local Stubへ最低1回のリクエストが発生する（重要度判定）",
        stub.anthropic_request_count() >= 1,
    )
    check(
        "A11. WordPress POSTが認証/payload検証で拒否された事例はない（Major#5対応）",
        stub.wordpress_rejections(),
        [],
    )
finally:
    stub.stop()
    copy.teardown()
    cleanup_scenario_appdata_dir(appdata_dir)

after_manifest = capture_manifest(PROJECT_ROOT)
zero_diff_issues = diff_manifests(before_manifest, after_manifest)
check("A9. Original Projectはシナリオ実行前後でZero-Diff（差分なし）", zero_diff_issues, [])
check_true("A10. Disposable Project Copyはteardown後に削除されている", copy.root is not None and not copy.root.exists())


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
