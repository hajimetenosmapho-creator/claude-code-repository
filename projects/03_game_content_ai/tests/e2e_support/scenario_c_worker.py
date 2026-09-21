"""
T8: Scenario C単一worker subprocessエントリポイント。

docs/design/mvp_end_to_end_hardening_validation.md 10.2節・10.5節・10.5a節の
確定設計を実装するtest-only worker script。production source（src/・
scripts/・main.py）は一切変更しない——sitecustomize.pyはこのworker自身が
実行時に動的生成するtest-owned fileであり、production側には一切配置しない。

起動引数（sys.argv）:
    argv[1]: Disposable Project Copy rootの絶対パス
    argv[2]: worker result file（JSON）の出力先絶対パス
    argv[3]: crash seam evidence marker file の絶対パス（Disposable Copy外）

起動時env（10.5節1.のallowlistを起動元テストが構築して渡す。本workerは
このenvをそのまま読むのみで、自分自身では変更しない——Step2直前の
crash seam4変数のscoped設定を除く）。

exit code:
    0   正常終了（worker result fileへ書き出し完了）
    90  import解決失敗（10.5a節、WORKER_IMPORT_RESOLUTION_FAILED_EXIT_CODE）
    その他 想定外の例外（worker result fileが存在しないことでテスト側が検出する）
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from pathlib import Path

WORKER_IMPORT_RESOLUTION_FAILED_EXIT_CODE = 90

_SITECUSTOMIZE_TEMPLATE = '''
"""test-owned sitecustomize.py — WP_OUTPUT_CRASH_SEAM_ENABLED=1のときのみ発火する
Authoritative Write-Ahead Crash Injection（6.24節）。production source外。"""
import json as _json
import os
import sys
from pathlib import Path


def _crash_seam_main():
    if os.environ.get("WP_OUTPUT_CRASH_SEAM_ENABLED") != "1":
        return
    src_dir = os.environ.get("WP_OUTPUT_CRASH_SEAM_SRC_DIR")
    evidence_path = os.environ.get("WP_OUTPUT_CRASH_SEAM_EVIDENCE_PATH")
    if not src_dir or not evidence_path:
        return
    expected_src = Path(src_dir).resolve()
    sys.path.insert(0, str(expected_src))
    try:
        from wordpress_draft_state import wordpress_draft_state_manager as _target_module
    except ImportError as e:
        print(f"sitecustomize: fail-closed, cannot import target module: {e}", file=sys.stderr)
        return

    resolved = Path(_target_module.__file__).resolve()
    try:
        is_relative = resolved.is_relative_to(expected_src)
    except AttributeError:
        is_relative = str(resolved).startswith(str(expected_src))
    if not is_relative:
        print(
            f"sitecustomize: fail-closed, wordpress_draft_state_manager resolved from "
            f"{resolved}, expected under {expected_src}",
            file=sys.stderr,
        )
        return

    def _crash_record_confirmed(self, identity, member_run_id, wp_post_id):
        op_kind = identity.operation_kind
        effect_site = identity.effect_site
        payload = {
            "root_run_id": identity.root_run_id,
            "attempt_ordinal": identity.attempt_ordinal,
            "operation_kind": getattr(op_kind, "value", str(op_kind)),
            "effect_site": getattr(effect_site, "value", str(effect_site)),
            "operation_instance_key": identity.operation_instance_key,
            "member_run_id": member_run_id,
            "wp_post_id": wp_post_id,
        }
        with open(evidence_path, "w", encoding="utf-8") as f:
            f.write(_json.dumps(payload, ensure_ascii=False))
            f.flush()
            os.fsync(f.fileno())
        os._exit(91)

    _target_module.WordPressDraftStateManager.record_confirmed = _crash_record_confirmed


_crash_seam_main()
'''


def main() -> int:
    disposable_copy_root = Path(sys.argv[1]).resolve()
    worker_result_path = Path(sys.argv[2])
    evidence_path = Path(sys.argv[3])

    # ── 10.5a節: bootstrap ───────────────────────────────────────
    expected_src = (disposable_copy_root / "src").resolve()
    sys.path.insert(0, str(expected_src))

    import ai  # noqa: E402
    import workflow_engine  # noqa: E402
    import retry_composition  # noqa: E402
    import retry_runtime_orchestrator  # noqa: E402

    for _module in (ai, workflow_engine, retry_composition, retry_runtime_orchestrator):
        resolved = Path(_module.__file__).resolve()
        try:
            is_relative = resolved.is_relative_to(expected_src)
        except AttributeError:
            is_relative = str(resolved).startswith(str(expected_src))
        if not is_relative:
            print(
                f"fail-closed: {_module.__name__} resolved from {resolved}, "
                f"expected under {expected_src}",
                file=sys.stderr,
            )
            return WORKER_IMPORT_RESOLUTION_FAILED_EXIT_CODE

    from ai import AgentConfig  # noqa: E402
    from workflow_engine import (  # noqa: E402
        SOURCE_MANUAL,
        CanonicalAdmissionFailure,
        NullWorkflowEngineManager,
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

    # ── Step 1: canonical execution（crash seamなし、空RSS 2段階fixtureの
    # 1回目、main.pyのreturn 1で失敗） ────────────────────────────
    agent_config = AgentConfig.from_env(base_dir=disposable_copy_root)
    workflow_engine_config = WorkflowEngineConfig.from_env(project_root=disposable_copy_root)
    manager = WorkflowEngineManager.from_config(agent_config, workflow_engine_config)
    if isinstance(manager, NullWorkflowEngineManager):
        print("fail-closed: WorkflowEngineManager gate is closed (Step 1)", file=sys.stderr)
        return 93

    canonical_event = WorkflowEngineEvent(
        job_id="scenario-c-canonical",
        source=SOURCE_MANUAL,
        triggered_at=datetime.now(),
        trigger_reason="Scenario C canonical execution (E2E test-owned worker).",
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
        print(f"fail-closed: canonical execution CanonicalAdmissionFailure: {e.reason}", file=sys.stderr)
        return 94
    canonical_run_id = canonical_result.run_id

    # ── Step 2: RetryCompositionRoot構築・enqueue・crash-injected actual
    # retry（10.2節Step2、10.5節2.のscoped設定＋finally復元） ──────────
    composition_root = RetryCompositionRoot.from_env(base_dir=disposable_copy_root)
    orchestrator = RetryRuntimeOrchestrator.from_composition_root(composition_root)

    sitecustomize_dir = evidence_path.parent / "sitecustomize_pkg"
    sitecustomize_dir.mkdir(parents=True, exist_ok=True)
    (sitecustomize_dir / "sitecustomize.py").write_text(_SITECUSTOMIZE_TEMPLATE, encoding="utf-8")

    try:
        os.environ["PYTHONPATH"] = str(sitecustomize_dir)
        os.environ["WP_OUTPUT_CRASH_SEAM_ENABLED"] = "1"
        os.environ["WP_OUTPUT_CRASH_SEAM_SRC_DIR"] = str(expected_src)
        os.environ["WP_OUTPUT_CRASH_SEAM_EVIDENCE_PATH"] = str(evidence_path)
        cycle_result = orchestrator.run_once(dry_run=False)
    finally:
        for key in (
            "PYTHONPATH", "WP_OUTPUT_CRASH_SEAM_ENABLED",
            "WP_OUTPUT_CRASH_SEAM_SRC_DIR", "WP_OUTPUT_CRASH_SEAM_EVIDENCE_PATH",
        ):
            os.environ.pop(key, None)

    # ── Step 3: automatic retry suppressionの確認 ───────────────────
    reconcile_summary = composition_root.lineage.reconcile_all(
        resolve_status_fn=composition_root.monitor.get_status
    )

    lineage_record = composition_root.lineage.find_existing_lineage(canonical_run_id)
    execution_result = cycle_result.execution_results[0] if cycle_result.execution_results else None
    retry_result = execution_result.retry_result if execution_result is not None else None

    result_payload = {
        "canonical_run_id": canonical_run_id,
        "retry_result": (
            None
            if retry_result is None
            else {
                "outcome": retry_result.outcome.value,
                "original_run_id": retry_result.original_run_id,
                "authoritative_attempt_no": retry_result.authoritative_attempt_no,
                "workflow_engine_result_run_id": (
                    retry_result.workflow_engine_result.run_id
                    if retry_result.workflow_engine_result is not None
                    else None
                ),
                "workflow_engine_result_overall_success": (
                    retry_result.workflow_engine_result.overall_success
                    if retry_result.workflow_engine_result is not None
                    else None
                ),
            }
        ),
        "lineage": (
            None
            if lineage_record is None
            else {
                "root_run_id": lineage_record.root_run_id,
                "latest_run_id": lineage_record.latest_run_id,
                "phase": lineage_record.phase.value,
                "terminal_disposition": (
                    lineage_record.terminal_disposition.value
                    if lineage_record.terminal_disposition is not None
                    else None
                ),
            }
        ),
        "cycle": {
            "enqueued": cycle_result.trigger_result.enqueued,
            "scheduler_events": len(cycle_result.scheduler_events),
            "execution_results": len(cycle_result.execution_results),
        },
        "reconcile_summary": {
            "skipped": reconcile_summary.skipped,
            "reason": reconcile_summary.reason,
            "resolved_count": reconcile_summary.resolved_count,
            "opened_count": reconcile_summary.opened_count,
            "released_count": reconcile_summary.released_count,
        },
    }

    worker_result_path.write_text(json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
