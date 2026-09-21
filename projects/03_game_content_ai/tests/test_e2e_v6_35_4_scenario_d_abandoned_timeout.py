"""
E2E テスト: Release 6.35 Scenario D — abandoned RUNNING → TIMEOUT →
eligibility判定

Source of Truth:
    docs/design/mvp_end_to_end_hardening_validation.md 11章
    （11.1節 Two-Way Blocking Handshake・11.2節 シナリオContract）。

実`WorkflowEngineManager`を単一専用worker subprocess
（tests/e2e_support/scenario_d_worker.py、T5）内で構築し、`post_admission_hook`
がready-sentinel書き込み後にblockする間に、親（本テスト）がready検出＋durable
state二重確認＋`taskkill`直前liveness確認を経て、release-signalを送らずに
`taskkill /PID <pid> /T /F`する。`WorkflowMonitor`のTIMEOUT判定は
`WorkflowMonitorConfig.timeout_seconds`と`started_at`の経過時間の純粋な計算
（`src/workflow_monitor/workflow_monitor.py:_judge()`で直接確認済み）である
ため、`WORKFLOW_MONITOR_TIMEOUT_SECONDS`を小さい値に設定するだけで、実際に
1時間待つことなくTIMEOUT判定を決定的に再現できる（新しいproduction機構は
使わない、既存の設定可能な閾値をそのまま利用する）。production source
（src/・scripts/・main.py）は一切変更しない。

Post-Codex-delta-review Amendment（Major#1/#3・Minor#2対応）：retry
eligibility判定フェーズをScopedEnv（overlay）からExactEnv（os.environ完全
置換）へ変更し、APPDATAをscenario-owned empty directoryへ変更した。durable
RUNNING確認をPARENT_READY_DEADLINE_SECの残り時間内でboundedにpollし
started_atの設定も明示的に確認するよう変更し、readiness/durable state確認が
deadline内に完了しなかった場合はtaskkillを発行しないよう変更した。

Post-Codex-delta-review#2 Amendment（残存Minor#1対応）：上記の
「taskkillを発行しない」契約が、メインフローでは守られていたものの
`finally`ブロックでは`timing_ok`を見ずに無条件でtaskkillしていたため
実質的に破られていたことが判明した。`finally`も`timing_ok`でgateする
よう修正した。あわせて、`tests/e2e_support/process_liveness.py`の
`wait_until()`自体が、loop終了後にもう一度predicateを評価し、それが
deadline超過後にTrueになった場合でも成功として扱っていた
（deadline厳密性の欠如）ため、この「最後のボーナス評価」を廃止した。

Post-Codex-delta-review#3 Amendment（残存Minor 2件対応）：
`wait_until()`のdeadline判定が`predicate()`呼び出しの**前**にしか
行われておらず、`predicate()`自体の実行がdeadlineを跨いだ場合に成功扱いに
なりうる残存レースを解消した（`predicate()`成功直後にdeadlineを再確認）。
また、`tests/e2e_support/scenario_d_worker.py`が、readiness到達前
（import・gate判定・`manager.run()`呼び出し自体等）で停止・ハングした場合に
worker自身の安全弁が一切発火せず無期限のorphanになりうる欠陥を解消した
——process起動直後（`main()`の最初の行）からprocess-wide watchdog
（`threading.Timer`、test-owned）を起動し、hook自身の待機deadlineも
process起動時刻を起点とする同一のdeadlineへ統一した。「readiness/durable
確認失敗時にtest側がtaskkillしない」という親側の既存契約は変更していない
——worker自身の自律終了のみを強化した。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_35_4_scenario_d_abandoned_timeout.py
"""
from __future__ import annotations

import subprocess
import sys
import time
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
print("Release 6.35 Scenario D: abandoned RUNNING -> TIMEOUT -> eligibility")
print("=" * 60)
print()

from collector import RSS_FEEDS  # noqa: E402
from e2e_support.disposable_copy import (  # noqa: E402
    DisposableProjectCopy,
    capture_manifest,
    diff_manifests,
)
from e2e_support.env_contract import (  # noqa: E402
    ExactEnv,
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

from execution_history import ExecutionHistoryConfig, JsonExecutionHistoryStore  # noqa: E402
from workflow_monitor import WorkflowMonitor, WorkflowMonitorConfig, WorkflowMonitorStatus  # noqa: E402
from retry_composition import RetryCompositionRoot  # noqa: E402
from retry_runtime_orchestrator import RetryRuntimeOrchestrator  # noqa: E402
from retry_engine import RetryOutcome  # noqa: E402

RSS_SOURCE_NAMES = list(RSS_FEEDS.keys())
ARTICLE_SOURCE = RSS_SOURCE_NAMES[0]
WORKER_SCRIPT = PROJECT_ROOT / "tests" / "e2e_support" / "scenario_d_worker.py"

PARENT_READY_DEADLINE_SEC = 5.0
POLL_INTERVAL_SEC = 0.05


before_manifest = capture_manifest(PROJECT_ROOT)

stub = LocalStub(rss_source_names=RSS_SOURCE_NAMES).start()
stub.set_wordpress_expected_auth("test-dummy-user", "test-dummy-app-password")
copy = DisposableProjectCopy(PROJECT_ROOT).build()
appdata_dir = make_scenario_appdata_dir()
ready_sentinel_path = copy.root.parent / "scenario_d_ready.sentinel"
release_signal_path = copy.root.parent / "scenario_d_release.signal"

worker_pid = None
release_signal_was_created = False
timing_ok = False
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
            "id": 7373,
            "slug": "switch2-announced",
            "status": "draft",
            "title": {"rendered": "Nintendo Switch 2 発売決定"},
            "link": "http://127.0.0.1/?p=7373",
        },
    )

    worker_env = base_windows_vars(appdata_dir)
    worker_env.update(
        {
            "AI_AGENT_ENABLED": "true",
            "WORKFLOW_ENGINE_ENABLED": "true",
            "NEWS_AGENT_MIN_INTERVAL_MINUTES": "0",
            "PYTHON_DOTENV_DISABLED": "1",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
        }
    )

    wait_start = time.monotonic()
    proc = subprocess.Popen(
        [str(copy.venv_python), str(WORKER_SCRIPT), str(copy.root), str(ready_sentinel_path), str(release_signal_path)],
        cwd=str(copy.root),
        env=worker_env,
    )
    worker_pid = proc.pid

    ready_ok = wait_until(lambda: ready_sentinel_path.exists(), PARENT_READY_DEADLINE_SEC, POLL_INTERVAL_SEC)
    check_true("D1. ready-sentinelがPARENT_READY_DEADLINE_SEC以内に出現する", ready_ok)

    run_id = ready_sentinel_path.read_text(encoding="utf-8").strip() if (ready_ok and ready_sentinel_path.exists()) else None
    check_true("D2. ready-sentinelにrun_idが書き込まれている", bool(run_id))

    # ── Post-Codex-delta-review Amendment（Minor#2対応）：durable RUNNING
    # 確認を、readyセンチネル検出に使った時間を差し引いた「残りdeadline」内で
    # boundedにpollし、started_atが設定済みであることも明示的にassertする
    # （11.1節：ready検出＋durable state確認の合計がPARENT_READY_DEADLINE_SEC
    # 以内に完了した場合のみtaskkillへ進む）。 ───────────────────────
    history_store = None
    monitor_normal = None
    monitor_record_before_kill = None
    durable_ok = False
    if ready_ok and run_id:
        # ── Post-Codex Full Independent Review Amendment（Major#1対応）：
        # ExecutionHistoryConfig.from_env()はhostのos.environから
        # EXECUTION_HISTORY_DIRを読みうるため（6.26節のpathlib `/`演算子の
        # 絶対path上書き挙動）、テストハーネス自身のos.environがまだhost
        # ambient環境のままのこの時点（ExactEnvブロックへ入る前）で呼ぶと、
        # durable state確認がDisposable Project Copy外を参照しうる
        # authority containmentの穴になっていた。`.from_env()`を使わず、
        # `ExecutionHistoryConfig`（plain dataclass）を直接構築し、
        # `.from_env()`のhost環境変数未設定時の既定値と同一の相対パス
        # （`<project_root>/logs/execution_history`）へ、host環境変数を
        # 一切経由せずハードコードする。これにより、hostに
        # `EXECUTION_HISTORY_DIR`が何らかの値で設定されていても、本読み取り
        # は常にDisposable Project Copy配下のみを参照する。 ─────────────
        history_config = ExecutionHistoryConfig(enabled=True, history_dir=copy.root / "logs" / "execution_history")
        history_store = JsonExecutionHistoryStore(history_config.history_dir)
        monitor_normal = WorkflowMonitor(history_store, WorkflowMonitorConfig(enabled=True, timeout_seconds=3600))

        def _durable_running_ready() -> bool:
            rec = monitor_normal.get_status(run_id)
            return rec is not None and rec.monitor_status == WorkflowMonitorStatus.RUNNING and rec.started_at is not None

        remaining = max(0.0, PARENT_READY_DEADLINE_SEC - (time.monotonic() - wait_start))
        durable_ok = wait_until(_durable_running_ready, remaining, POLL_INTERVAL_SEC)
        monitor_record_before_kill = monitor_normal.get_status(run_id)

    check_true(
        "D3. durable state二重確認：残りdeadline内にRUNNING（started_at設定済み）を確認する",
        durable_ok,
    )
    check_true(
        "D3b. durable stateレコードのstarted_atが実際に設定されている",
        monitor_record_before_kill is not None and monitor_record_before_kill.started_at is not None,
    )

    # ── taskkill直前の最終liveness確認は、ready検出＋durable state確認の
    # 両方がdeadline内に完了した場合のみ行う（11.1節：deadline超過時は
    # taskkillを発行せずtiming failureとして明示的に失敗させる） ─────────
    timing_ok = ready_ok and durable_ok
    alive_before_kill = is_pid_alive(worker_pid) if timing_ok else False
    check_true(
        "D4. taskkill直前の最終liveness確認：workerは生存している（timing failure時は実施しない）",
        alive_before_kill if timing_ok else False,
    )

    killed = False
    if timing_ok and alive_before_kill:
        taskkill_tree(worker_pid)
        killed = True
    exited = wait_for_pid_exit(worker_pid, timeout_sec=10) if killed else False
    check_true("D5. taskkill後、workerプロセスツリーの終了を確認する（timing failure時は実施しない）", exited if timing_ok else False)

    observed_returncode = None
    if killed:
        try:
            proc.wait(timeout=10)
            observed_returncode = proc.returncode
        except subprocess.TimeoutExpired:
            observed_returncode = None
    check_true(
        "D6. hookの安全弁タイムアウト（exit code 2）は観測されない（timing failureではない）",
        observed_returncode != 2,
    )

    monitor_record_after = None
    if timing_ok and monitor_normal is not None:
        # ── WorkflowMonitorのTIMEOUT判定（既存のWORKFLOW_MONITOR_TIMEOUT_SECONDS
        # 閾値を小さくするだけで、実時間1時間を待たずに決定的に再現する） ──
        monitor_short = WorkflowMonitor(history_store, WorkflowMonitorConfig(enabled=True, timeout_seconds=0))
        monitor_record_after = monitor_short.get_status(run_id)
    check(
        "D7. WorkflowMonitor.get_status(run_id)はTIMEOUTを返す",
        monitor_record_after.monitor_status if monitor_record_after else None,
        WorkflowMonitorStatus.TIMEOUT if timing_ok else None,
    )

    # ── Retry Eligibility判定への引き渡し・新規lineage作成の確認（Major#1
    # 対応：ScopedEnv（overlay）ではなくExactEnv（os.environ完全置換）を使い、
    # host由来のPYTHONPATH・絶対path override等を一切持ち込まない。APPDATAは
    # scenario-owned empty directory、Major#3対応） ────────────────────
    env_updates = base_windows_vars(appdata_dir)
    env_updates.update(
        {
            "AI_AGENT_ENABLED": "true",
            "WORKFLOW_ENGINE_ENABLED": "true",
            "RETRY_ENGINE_ENABLED": "true",
            "RETRY_LINEAGE_ENABLED": "true",
            "NEWS_AGENT_MIN_INTERVAL_MINUTES": "0",
            "WORKFLOW_MONITOR_TIMEOUT_SECONDS": "0",
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

    new_lineage = None
    cycle_result = None
    if timing_ok:
        with ExactEnv(env_updates):
            composition_root = RetryCompositionRoot.from_env(base_dir=copy.root)
            orchestrator = RetryRuntimeOrchestrator.from_composition_root(composition_root)
            cycle_result = orchestrator.run_once(dry_run=False)
            new_lineage = composition_root.lineage.find_existing_lineage(run_id)

    check("D8. TIMEOUTなrun_idがちょうど1件enqueueされる", cycle_result.trigger_result.enqueued if cycle_result else None, 1 if timing_ok else None)
    check("D9. actual retryがちょうど1件実行される（新規lineage経由）", len(cycle_result.execution_results) if cycle_result else None, 1 if timing_ok else None)

    check_true("D10. 新規lineageがroot_run_id=run_idで作成される", new_lineage is not None if timing_ok else False)
    if new_lineage is not None:
        check("D11. 新規lineageのroot_run_idはabandoned run_idと一致する", new_lineage.root_run_id, run_id)

    if cycle_result is not None and cycle_result.execution_results:
        retry_result = cycle_result.execution_results[0].retry_result
        check("D12. retry_result.outcomeはRETRIED（二重lineage作成ではなく単一lineageでの実retry）", retry_result.outcome, RetryOutcome.RETRIED)

    wp_requests = stub.wordpress_requests()
    check("D13. WordPress Local Stubはretryでちょうど1回のPOSTを受信する", len(wp_requests), 1 if timing_ok else 0)
    check(
        "D13b. WordPress POSTが認証/payload検証で拒否された事例はない（Major#5対応）",
        stub.wordpress_rejections(),
        [],
    )

    release_signal_was_created = release_signal_path.exists()
finally:
    # ── Post-Codex-delta-review#2 Amendment（Minor#1対応）：timing failure時
    # （timing_ok=False、readinessまたはdurable state確認がdeadline内に
    # 完了しなかった場合）はcleanupにおいてもtaskkillを一切発行しない
    # （11.1節の契約と矛盾しない形にする）。この場合、workerはhookの
    # HOOK_SAFETY_TIMEOUT_SEC（30秒、scenario_d_worker.py）という既存の
    # process-wide watchdog（threading.Timer、test-owned）に終了を委ねる——
    # production機構は使わない。ただしこのwatchdogは11.1節が明記する
    # とおりbest-effort safety watchdogであり、通常のPythonインタプリタ
    # scheduling下での終了を意図したものであって、timing非依存・無条件の
    # 保証ではない（module-level importはwatchdog起動前に実行される、
    # GIL contention下でthreading.Timerコールバックが遅延しうる、等の
    # 限界がある）。
    # timing_ok=Trueの場合のみ、万一まだ生存していれば安全網として
    # taskkillする（通常経路では既に終了しているはず、D5で確認済み）。
    if timing_ok and worker_pid is not None and is_pid_alive(worker_pid):
        taskkill_tree(worker_pid)
    stub.stop()
    copy.teardown()
    cleanup_scenario_appdata_dir(appdata_dir)
    for p in (ready_sentinel_path, release_signal_path, ready_sentinel_path.with_suffix(".tmp")):
        if p.exists():
            p.unlink(missing_ok=True)

check_true(
    "D14. release-signalは一度も送られていない（crash経路のみを検証、ファイル未作成のまま）",
    not release_signal_was_created,
)

after_manifest = capture_manifest(PROJECT_ROOT)
zero_diff_issues = diff_manifests(before_manifest, after_manifest)
check("D15. Original Projectはシナリオ実行前後でZero-Diff（差分なし）", zero_diff_issues, [])


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
