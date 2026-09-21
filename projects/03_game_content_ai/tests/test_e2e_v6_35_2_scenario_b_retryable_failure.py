"""
E2E テスト: Release 6.35 Scenario B — retryable failure → enqueue → actual
retry → observability

Source of Truth:
    docs/design/mvp_end_to_end_hardening_validation.md 9章（9.1/9.2節、
    Post-Round 10 Amendmentで正式契約本文を確定済み）。本テストはその9.1節
    契約（Precondition/Runtime Path/Failure Injection/Durable-Observable
    Assertions/Prohibited Outcome/Isolation-Cleanup）の実装である。
    Scenario Cのsitecustomize crash injectionは使わない（Scenario Bは
    正常に完走するactual retryのみを検証する）。

Scenario Aとは異なり、本シナリオはRetry Runtime（AI_AGENT_ENABLED /
WORKFLOW_ENGINE_ENABLED / RETRY_ENGINE_ENABLED / RETRY_LINEAGE_ENABLED）を
経由するため、テストドライバ自身のプロセス内でWorkflowEngineManager /
RetryCompositionRootを直接構築する（Scenario Cのように独立worker
subprocessへ分離する必要はない——crash seam関連のenv隔離が不要なため）。
main.py自身は既存どおりNewsPipelineRunner経由の実subprocessとして起動される
（6.19節）。production source（src/・scripts/・main.py）は一切変更しない。

Post-Codex-delta-review Amendment（Major#1/#2/#3・#5対応）：
- env構成をScopedEnv（overlay、host由来のambient変数を保持したまま一部を
  上書きするだけ）からExactEnv（os.environ完全置換）へ変更した。host由来の
  PYTHONPATH・絶対path override等がmain.py実subprocessへ`{**os.environ,...}`
  経由（6.19節）で持ち込まれる経路を遮断する。
- APPDATAをhost実値からscenario-owned empty directoryへ変更した。
- fallback非発動assertionを、検証対象として誤っていたAnthropicへの
  HTTPリクエストbody検索から、fallback文字列が実際に印字される観測可能な
  唯一のsource——main.py実subprocessのstdout（`src/importance_judge.py:74`
  の`print()`、`NewsPipelineRunner._save_log()`が`<working_directory>/
  logs/news_agent/*_stdout.log`へ保存する、`src/pipeline/
  news_pipeline_runner.py:54,205-213`で直接確認済み）へ変更した。
- WordPress Local Stubへの認証/payload検証を追加した（7.5.5節）。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_35_2_scenario_b_retryable_failure.py
"""
from __future__ import annotations

import sys
from datetime import datetime
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
print("Release 6.35 Scenario B: retryable failure -> enqueue -> actual retry")
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

from ai import AgentConfig  # noqa: E402
from workflow_engine import (  # noqa: E402
    CanonicalAdmissionFailure,
    NullWorkflowEngineManager,
    SOURCE_MANUAL,
    WorkflowEngineConfig,
    WorkflowEngineEvent,
    WorkflowEngineManager,
)
from side_effect_safety import (  # noqa: E402
    LegacyEntrypoint,
    LegacyExecutionOrigin,
    build_legacy_direct_provenance,
    complete_legacy_execution_context,
)
from retry_composition import RetryCompositionRoot  # noqa: E402
from retry_runtime_orchestrator import RetryRuntimeOrchestrator  # noqa: E402
from retry_engine import RetryOutcome  # noqa: E402
from retry_lineage import RetryLineageDisposition  # noqa: E402

RSS_SOURCE_NAMES = list(RSS_FEEDS.keys())
ARTICLE_SOURCE = RSS_SOURCE_NAMES[0]


before_manifest = capture_manifest(PROJECT_ROOT)

stub = LocalStub(rss_source_names=RSS_SOURCE_NAMES).start()
stub.set_wordpress_expected_auth("test-dummy-user", "test-dummy-app-password")
copy = DisposableProjectCopy(PROJECT_ROOT).build()
appdata_dir = make_scenario_appdata_dir()

# ── env契約（Post-Codex-delta-review Amendment、Major#1/#3対応）：
# ExactEnvでos.environを完全に置換する（overlayではない）。authority
# containment（6.26節）としてEXECUTION_HISTORY_DIR・RETRY_LINEAGE_DIRは
# この閉じた集合に含めないため、置換された時点で構造的に未設定となる。
# APPDATAはscenario-owned empty directory（Major#3対応）。 ─────────────
env_updates = base_windows_vars(appdata_dir)
env_updates.update(
    {
        "AI_AGENT_ENABLED": "true",
        "WORKFLOW_ENGINE_ENABLED": "true",
        "RETRY_ENGINE_ENABLED": "true",
        "RETRY_LINEAGE_ENABLED": "true",
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

try:
    with ExactEnv(env_updates):
        # ── Step 1: canonical execution（crash seamなし、10.2節Step1と同型の
        # 空RSS 2段階fixture。全16パスとも1回目は0件 → main.pyがreturn 1） ──
        for name in RSS_SOURCE_NAMES:
            stub.set_rss_sequence(name, [[], []])
        stub.set_rss_sequence(
            ARTICLE_SOURCE,
            [
                [],
                [
                    {
                        "title": "Nintendo Switch 2 発売決定、価格と発売日を発表",
                        "link": "http://127.0.0.1/articles/switch2-announced",
                        "description": "任天堂は新型Switchの発売を正式発表した。",
                    }
                ],
            ],
        )
        stub.set_wordpress_response(
            201,
            {
                "id": 5252,
                "slug": "switch2-announced",
                "status": "draft",
                "title": {"rendered": "Nintendo Switch 2 発売決定"},
                "link": "http://127.0.0.1/?p=5252",
            },
        )

        agent_config = AgentConfig.from_env(base_dir=copy.root)
        workflow_engine_config = WorkflowEngineConfig.from_env(project_root=copy.root)
        manager = WorkflowEngineManager.from_config(agent_config, workflow_engine_config)
        check_true("B1. 二重ゲートが開きWorkflowEngineManagerが実体化する", not isinstance(manager, NullWorkflowEngineManager))

        canonical_event = WorkflowEngineEvent(
            job_id="scenario-b-canonical",
            source=SOURCE_MANUAL,
            triggered_at=datetime.now(),
            trigger_reason="Scenario B canonical execution (E2E test-owned).",
        )
        provenance = complete_legacy_execution_context(
            build_legacy_direct_provenance(LegacyEntrypoint.RUN_WORKFLOW_ENGINE_DIRECT),
            LegacyExecutionOrigin.WORKFLOW_ENGINE_DIRECT,
        )
        try:
            canonical_result = manager.run(
                canonical_event, dry_run=False, side_effect_execution_provenance=provenance
            )
        except CanonicalAdmissionFailure as e:
            canonical_result = None
            check_true(f"B2. canonical executionがCanonicalAdmissionFailureで失敗しない（reason={e.reason}）", False)
        else:
            check_true("B2. canonical execution（空RSS）はoverall_success=Falseで終わる", not canonical_result.overall_success)

        check("B3. Step1完了時点でAnthropic Local Stubは1回も呼ばれない（空RSSでWP到達前に失敗）", stub.anthropic_request_count(), 0)
        check("B4. Step1完了時点でWordPress Local Stubも1回も呼ばれない", len(stub.wordpress_requests()), 0)

        # ── Step 2: RetryCompositionRoot構築・enqueue・actual retry（crash
        # 注入なし。10.2節Step2と同一の単一composition rootだが、Scenario B
        # ではsitecustomize4変数を一切設定せず、record_confirmed()まで
        # 正常に到達させる） ──
        composition_root = RetryCompositionRoot.from_env(base_dir=copy.root)
        orchestrator = RetryRuntimeOrchestrator.from_composition_root(composition_root)
        cycle_result = orchestrator.run_once(dry_run=False)

        check("B5. reconcile_all()はcanonical実行のlineageが1件も無くno-op", cycle_result.reconcile_summary.resolved_count, 0)
        check("B6. FAILEDなcanonical run run_idがちょうど1件enqueueされる", cycle_result.trigger_result.enqueued, 1)
        check("B7. schedulerがちょうど1件のretry候補eventを生成する", len(cycle_result.scheduler_events), 1)
        check("B8. actual retryがちょうど1件実行される", len(cycle_result.execution_results), 1)

        if cycle_result.execution_results:
            retry_result = cycle_result.execution_results[0].retry_result
            check("B9. retry_result.outcomeはRETRIED（実際に再実行された）", retry_result.outcome, RetryOutcome.RETRIED)
            check_true("B10. retry executionは成功する（retry execution自体もWorkflowEngineResult.overall_success=True）", retry_result.workflow_engine_result is not None and retry_result.workflow_engine_result.overall_success)

        # ── Post-Codex Full Independent Review Amendment（Major#2対応）：
        # Prohibited Outcome「terminal_disposition == HUMAN_REVIEW_REQUIRED
        # になること（Scenario Cの結果との混同を意味する）」を、2回目
        # reconcile_all()のopened_count==0という間接証拠だけに頼らず、
        # lineageのterminal_dispositionを直接読み取って実効的にassertする
        # （HRRはreopenを抑制する性質があり、opened_count==0はHRRの場合にも
        # 成立してしまうため、それ単体ではCの結果との混同を検出できない）。──
        lineage_record = (
            composition_root.lineage.find_existing_lineage(canonical_result.run_id)
            if canonical_result is not None
            else None
        )
        check_true("B9b. retry成功後のlineageレコードが存在する", lineage_record is not None)
        if lineage_record is not None:
            check(
                "B9c. terminal_dispositionはSUCCEEDED（HUMAN_REVIEW_REQUIREDではない、Scenario Cとの混同防止）",
                lineage_record.terminal_disposition,
                RetryLineageDisposition.SUCCEEDED,
            )

        wp_requests = stub.wordpress_requests()
        check("B11. WordPress Local Stubはretry実行でちょうど1回のPOSTを受信する", len(wp_requests), 1)

        check("B12. Anthropic Local Stubはretry実行で4回呼ばれる（重要度判定+記事+SEO+X投稿）", stub.anthropic_request_count(), 4)

        # ── Post-Codex-delta-review Amendment（Major#2対応）：fallback
        # 発動を示す警告文字列（「判定エラー」）は`src/importance_judge.py:74`
        # が`print()`でstdoutへ出力するものであり、Anthropicへの
        # HTTPリクエストbodyには一切現れない（検証対象の誤り、Major#2）。
        # 唯一の観測可能なsourceは、main.py実subprocess自身のstdoutが
        # `NewsPipelineRunner._save_log()`（`src/pipeline/
        # news_pipeline_runner.py:54,205-213`）により保存される
        # `<copy.root>/logs/news_agent/*_stdout.log`である。retry
        # execution（Step2）はこのディレクトリへの唯一のNEWS実行であり
        # （canonical executionは空RSSでWordPress到達前に失敗しimportance_
        # judgeへ到達しない、B3で確認済み）、曖昧さなく対応付けられる。
        # このsourceで検出できない場合は、推測でPASS/FAILを断定せず
        # 明示的に「検出不能」として報告する。 ──────────────────────────
        # 実測の結果、canonical execution（Step1）自身も`NewsPipelineRunner.
        # run()`のreturn直前に`_save_log()`でstdout logを保存するため（空RSSで
        # `return 1`する場合も含む、news_pipeline_runner.py:186-187）、
        # `logs/news_agent/`にはcanonical execution分・retry execution分の
        # 計2ファイルが存在しうる。fallback文字列の検出という目的上は、
        # 存在する全stdout logを対象に検索すれば十分（canonical execution側は
        # importance_judgeへ到達しないため元々fallback文字列を含まない）。
        stdout_log_dir = copy.root / "logs" / "news_agent"
        stdout_log_files = sorted(stdout_log_dir.glob("*_stdout.log")) if stdout_log_dir.is_dir() else []
        if not stdout_log_files:
            check_true(
                "B13. fallback非発動assertionの観測可能source（stdout log）が見つからず検証不能——停止報告（Major#2対応）",
                False,
            )
        else:
            stdout_log_text = "\n".join(
                p.read_text(encoding="utf-8", errors="replace") for p in stdout_log_files
            )
            check_true("B13a. main.py実subprocessのstdout logが最低1件生成される", len(stdout_log_files) >= 1)
            check_true(
                "B13b. fallback発動を示す警告文字列（判定エラー）がmain.py実subprocessのstdout logに出現しない",
                "判定エラー" not in stdout_log_text,
            )

        # ── Step 3: automatic retry suppressionの確認（12.1節/10.2節Step3と
        # 同型。もう1回reconcile_all()を呼び、新規lineageが誤って再度開かれ
        # ないことを確認する） ──
        second_reconcile = composition_root.lineage.reconcile_all(
            resolve_status_fn=composition_root.monitor.get_status
        )
        check_true("B14. retry成功後の2回目reconcile_all()はskipped=False", not second_reconcile.skipped)
        check("B15. 2回目reconcile_all()はopened_count=0（誤った追加retryが開かれない）", second_reconcile.opened_count, 0)

        check(
            "B17. WordPress POSTが認証/payload検証で拒否された事例はない（Major#5対応）",
            stub.wordpress_rejections(),
            [],
        )
finally:
    stub.stop()
    copy.teardown()
    cleanup_scenario_appdata_dir(appdata_dir)

after_manifest = capture_manifest(PROJECT_ROOT)
zero_diff_issues = diff_manifests(before_manifest, after_manifest)
check("B16. Original Projectはシナリオ実行前後でZero-Diff（差分なし）", zero_diff_issues, [])


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
