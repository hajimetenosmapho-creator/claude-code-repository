"""
E2E テスト: Release 6.35 Scenario C — partial/side-effect済み failure →
Human Review → automatic retryなし

Source of Truth:
    docs/design/mvp_end_to_end_hardening_validation.md 10章
    （10.2節 統合設計・10.5節 Environment isolation・10.5a節 import解決契約・
    6.24節 crash injection機構）。

単一の専用test worker subprocess（tests/e2e_support/scenario_c_worker.py、
T8）を1回だけ起動し、そのプロセス内でcanonical execution→enqueue→
crash-injected actual retryを連続実行する。crash injectionは
test-owned`sitecustomize.py`（production source変更ゼロ）が
`WordPressDraftStateManager.record_confirmed`をPOST成功後・原処理実行前に
hard-crashへ置き換えることで実現する。production source
（src/・scripts/・main.py）は一切変更しない。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_35_3_scenario_c_human_review.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
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


def check_false(label: str, value: bool):
    check(label, bool(value), False)


print("=" * 60)
print("Release 6.35 Scenario C: partial failure -> Human Review Required")
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
from side_effect_safety import (  # noqa: E402
    ProtectedSideEffectKind,
    SideEffectOperationIdentity,
    SideEffectSite,
)
from wordpress_draft_state import JsonWordPressDraftStateStore, WordPressDraftStateManager  # noqa: E402
from protected_operation_manifest import JsonProtectedOperationManifestStore  # noqa: E402

RSS_SOURCE_NAMES = list(RSS_FEEDS.keys())
ARTICLE_SOURCE = RSS_SOURCE_NAMES[0]
WORKER_SCRIPT = PROJECT_ROOT / "tests" / "e2e_support" / "scenario_c_worker.py"
WP_POST_ID = 6363

before_manifest = capture_manifest(PROJECT_ROOT)

stub = LocalStub(rss_source_names=RSS_SOURCE_NAMES).start()
copy = DisposableProjectCopy(PROJECT_ROOT).build()
scratch_dir = Path(tempfile.mkdtemp(prefix="scenario_c_scratch_"))
evidence_path = scratch_dir / "crash_evidence.json"
worker_result_path = scratch_dir / "worker_result.json"
appdata_dir = make_scenario_appdata_dir()

try:
    # ── 10.2節Step1/Step2の2段階RSS fixture（canonical=全16件0、
    # retry=1パスのみ1件） ──────────────────────────────────────
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
            "id": WP_POST_ID,
            "slug": "switch2-announced",
            "status": "draft",
            "title": {"rendered": "Nintendo Switch 2 発売決定"},
            "link": f"http://127.0.0.1/?p={WP_POST_ID}",
        },
    )
    # ── Post-Codex-delta-review Amendment（Major#5対応） ────────────
    stub.set_wordpress_expected_auth("test-dummy-user", "test-dummy-app-password")

    # ── 10.5節1. worker起動時env（allowlist方式、crash seam4変数・
    # EXECUTION_HISTORY_DIR/RETRY_LINEAGE_DIRはいずれも含めない。APPDATAは
    # scenario-owned empty directory、Major#3対応） ─────────────────
    worker_env = base_windows_vars(appdata_dir)
    worker_env.update(
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

    proc = subprocess.run(
        [str(copy.venv_python), str(WORKER_SCRIPT), str(copy.root), str(worker_result_path), str(evidence_path)],
        cwd=str(copy.root),
        env=worker_env,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
    )
    print("--- worker stdout (tail) ---")
    print("\n".join(proc.stdout.splitlines()[-20:]) if proc.stdout else "(empty)")
    if proc.returncode != 0:
        print("--- worker stderr ---")
        print(proc.stderr)

    check("C0. workerはexit code 0で終了する", proc.returncode, 0)
    check_true("C1. worker result fileが生成される", worker_result_path.exists())

    worker_result = json.loads(worker_result_path.read_text(encoding="utf-8")) if worker_result_path.exists() else {}
    check_true("C2. crash seam evidence markerが存在する（crash hook発火の証拠、Assertion1）", evidence_path.exists())
    evidence = json.loads(evidence_path.read_text(encoding="utf-8")) if evidence_path.exists() else {}

    # ── Assertion 2: POST成功の独立確認（ちょうど1回、200/201） ─────
    wp_requests = stub.wordpress_requests()
    check("C3. WordPress Local StubはPOSTをちょうど1回受信する（Assertion2）", len(wp_requests), 1)

    # ── Assertion 3: durable draft stateの直接確認（ATTEMPTEDのまま） ──
    if evidence:
        identity = SideEffectOperationIdentity(
            root_run_id=evidence["root_run_id"],
            attempt_ordinal=evidence["attempt_ordinal"],
            operation_kind=ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION,
            effect_site=SideEffectSite.NEWS_STEP,
            operation_instance_key=evidence["operation_instance_key"],
        )
        draft_manager = WordPressDraftStateManager(
            JsonWordPressDraftStateStore(base_dir=copy.root / "state" / "wordpress_draft_state")
        )
        draft_record = draft_manager.get_state(identity, evidence["member_run_id"])
        check_true("C4. durable draft stateレコードが存在する（Assertion3）", draft_record is not None)
        if draft_record is not None:
            state_value = getattr(draft_record, "state", getattr(draft_record, "status", None))
            state_name = getattr(state_value, "name", state_value)
            check("C5. draft stateはATTEMPTEDのまま（CONFIRMEDへ遷移していない、Assertion3）", state_name, "ATTEMPTED")
            check("C6. wp_post_idは記録されていない（Assertion3）", getattr(draft_record, "wp_post_id", None), None)

        # ── Assertion 4: marker/draft-state/manifest/lineage/WorkflowEngineResultの
        # member_run_id相互照合＋attempt_ordinal=1確認 ─────────────
        manifest_store = JsonProtectedOperationManifestStore(
            base_dir=copy.root / "state" / "protected_operation_manifest"
        )
        try:
            manifest_entries = manifest_store.list_for_attempt(
                evidence["root_run_id"], evidence["attempt_ordinal"], evidence["member_run_id"]
            )
        except Exception:
            manifest_entries = ()
        check_true("C7. manifestレコードが存在する（Assertion4c）", len(manifest_entries) > 0)
        check("C8. manifestキーのattempt_ordinalは1（Assertion4c）", evidence["attempt_ordinal"], 1)

        retry_result = worker_result.get("retry_result") or {}
        lineage = worker_result.get("lineage") or {}
        member_run_ids = {
            "evidence": evidence.get("member_run_id"),
            "workflow_engine_result": retry_result.get("workflow_engine_result_run_id"),
            "lineage_latest_run_id": lineage.get("latest_run_id"),
        }
        check_true(
            "C9. marker/WorkflowEngineResult/lineage.latest_run_idのmember_run_idが全て一致（Assertion4）",
            len(set(member_run_ids.values())) == 1 and None not in member_run_ids.values(),
        )
        check("C10. retry_result.authoritative_attempt_noは1（Assertion4後段）", retry_result.get("authoritative_attempt_no"), 1)

        # ── Assertion 5: marker wp_post_idの期待値一致 ─────────────
        check("C11. evidenceのwp_post_idはLocal Stub応答のidと完全一致（Assertion5）", evidence.get("wp_post_id"), WP_POST_ID)

    # ── Assertion 6: disposition確認 ──────────────────────────────
    lineage = worker_result.get("lineage") or {}
    check("C12. terminal_dispositionはHUMAN_REVIEW_REQUIRED（Assertion6）", lineage.get("terminal_disposition"), "human_review_required")

    # ── Assertion 7: automatic retry suppressionの確認（Step3、全5field） ──
    reconcile = worker_result.get("reconcile_summary") or {}
    check(
        "C13. Step3のReconcileSummaryは全field一致（skipped=False,reason=None,resolved=0,opened=0,released=0、Assertion7）",
        reconcile,
        {"skipped": False, "reason": None, "resolved_count": 0, "opened_count": 0, "released_count": 0},
    )

    # ── Assertion 9: enqueue/dispatch/executionがちょうど1件 ──────────
    cycle = worker_result.get("cycle") or {}
    check("C14. enqueuedはちょうど1件（Assertion9）", cycle.get("enqueued"), 1)
    check("C15. scheduler_eventsはちょうど1件（Assertion9）", cycle.get("scheduler_events"), 1)
    check("C16. execution_resultsはちょうど1件（Assertion9）", cycle.get("execution_results"), 1)

    # ── Assertion 10: RetryOutcome.RETRIED・3経路のroot run ID一致 ──────
    check("C17. retry_result.outcomeはRETRIED（Assertion10）", retry_result.get("outcome"), "retried")
    root_run_ids = {
        "canonical_run_id": worker_result.get("canonical_run_id"),
        "retry_original_run_id": retry_result.get("original_run_id"),
        "lineage_root_run_id": lineage.get("root_run_id"),
    }
    check_true(
        "C18. canonical run_id・retry_result.original_run_id・lineage.root_run_idが完全一致（Assertion10）",
        len(set(root_run_ids.values())) == 1 and None not in root_run_ids.values(),
    )

    # ── Assertion8: NEWS stepの失敗確認（retry executionのNEWS stepは
    # main.py実subprocessがcrash injectionでexit 91、非ゼロ終了となる。
    # WorkflowEngineResult.overall_successは記事1件がPOST成功に到達した
    # 直後にcrashするため、NEWS step自体としては異常終了扱いになる） ──
    check_false(
        "C19. retry executionのWorkflowEngineResult.overall_successはFalse（NEWS stepがcrashで異常終了、Assertion8）",
        retry_result.get("workflow_engine_result_overall_success"),
    )
    check(
        "C21. WordPress POSTが認証/payload検証で拒否された事例はない（Major#5対応）",
        stub.wordpress_rejections(),
        [],
    )
finally:
    stub.stop()
    copy.teardown()
    shutil.rmtree(scratch_dir, ignore_errors=True)
    cleanup_scenario_appdata_dir(appdata_dir)

after_manifest = capture_manifest(PROJECT_ROOT)
zero_diff_issues = diff_manifests(before_manifest, after_manifest)
check("C20. Original Projectはシナリオ実行前後でZero-Diff（差分なし）", zero_diff_issues, [])


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
