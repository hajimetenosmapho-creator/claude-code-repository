"""
E2E テスト: Release 6.35 T6 — Formal Regression 37-file rosterの静的validation

Source of Truth:
    docs/design/mvp_end_to_end_hardening_validation.md 19.1節
    （確定した37-file roster）・23.2章T6・30.11節。

本テストは、`tests/formal_regression_inventory.py`（T6、機械可読capture）が
保持するrosterについて、以下の静的な整合性のみを検証する：
    - count == 37
    - unique_count == 37（重複0）
    - missing_count == 0（全pathが実在）
    - 設計書19.1節から独立して本テストファイル自身が転記したroster
      （ARCHITECTURE_ROSTER_19_1）との差分 == 0（roster module自身の
      transcriptionミスを、独立した二重チェックで検出する）

**37ファイルを実際に`python <file>.py`として実行しexit code 0を確認する
Formal Regression本体（19.2節）は、本テストの範囲外であり、本テスト自身は
実行しない**（本テストの目的はrosterの静的整合性検証に限定される）。roster
自体は固定tupleとして直接列挙されたものであり、`glob`等によるimplicit
discoveryは行わない。事前承認されたskip/exceptionリストも存在しない
（19.3節）。Formal Regression本体の実施記録・結果は
`docs/design/mvp_end_to_end_hardening_validation.md` 30.12節を参照。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_35_8_t6_formal_regression_roster_validation.py
"""
from __future__ import annotations

import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "tests"))

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
print("Release 6.35 T6: Formal Regression roster 静的validation")
print("=" * 60)
print()

from formal_regression_inventory import (  # noqa: E402
    EXPECTED_COUNT,
    FORMAL_REGRESSION_ROSTER,
    validate_roster_statics,
)

# ── 設計書19.1節から、本テストファイル自身が独立して転記したroster
# （roster moduleとは別の場所に保持する、transcriptionミスの二重チェック用）。
# ──────────────────────────────────────────────────────────────
ARCHITECTURE_ROSTER_19_1: tuple[str, ...] = (
    "test_e2e_v1_11_0_save_result.py",
    "test_e2e_v5_9_0_retry_runtime_loop_wiring_foundation.py",
    "test_e2e_v6_0_0_retry_runtime_lock_foundation.py",
    "test_e2e_v6_1_0_retry_runtime_graceful_shutdown_foundation.py",
    "test_e2e_v6_2_0_structured_loop_logging_foundation.py",
    "test_e2e_v6_3_0_retry_metrics_foundation.py",
    "test_e2e_v6_4_0_retry_monitoring_foundation.py",
    "test_e2e_v6_5_0_retry_alert_foundation.py",
    "test_e2e_v6_6_0_retry_notification_foundation.py",
    "test_e2e_v6_7_0_retry_notification_message_foundation.py",
    "test_e2e_v6_8_0_retry_notification_cli_report_wiring_foundation.py",
    "test_e2e_v6_9_0_wordpress_media_upload_foundation.py",
    "test_e2e_v6_10_0_ai_image_generation_contract_foundation.py",
    "test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py",
    "test_e2e_v6_12_0_generated_image_wordpress_media_upload_wiring_foundation.py",
    "test_e2e_v6_13_0_article_featured_media_binding_foundation.py",
    "test_e2e_v6_14_0_article_featured_media_orchestration_foundation.py",
    "test_e2e_v6_15_0_image_generation_configuration_gate.py",
    "test_e2e_v6_16_0_generated_image_filename_policy_foundation.py",
    "test_e2e_v6_17_0_article_image_prompt_construction_foundation.py",
    "test_e2e_v6_18_0_article_featured_media_composition_root_foundation.py",
    "test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py",
    "test_e2e_v6_20_0_article_featured_media_runtime_foundation.py",
    "test_e2e_v6_21_0_article_featured_media_runtime_wiring.py",
    "test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py",
    "test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py",
    "test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_refinement_foundation.py",
    "test_e2e_v6_25_0_image_generation_fallback_observability_foundation.py",
    "test_e2e_v6_26_0_zero_diff_guard_registry_foundation.py",
    "test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py",
    "test_e2e_v6_28_0_article_media_upload_state_foundation.py",
    "test_e2e_v6_29_0_retry_observability_pipeline_foundation.py",
    "test_e2e_v6_30_0_production_canonical_run_outcome_contract_foundation.py",
    "test_e2e_v6_31_0_retry_lineage_eligibility_durable_attempt_state.py",
    "test_e2e_v6_32_0_side_effect_fail_closed_foundation.py",
    "test_e2e_v6_33_0_retry_observability_runtime_integration_foundation.py",
    "test_e2e_v6_34_0_scheduler_driver_duplicate_dispatch_safety_foundation.py",
)

check("T6-1. 設計書19.1節からの独立転記も37件である", len(ARCHITECTURE_ROSTER_19_1), 37)

stats = validate_roster_statics()
print(f"  roster統計: {stats}")

check("T6-2. rosterのcountはちょうど37", stats["count"], EXPECTED_COUNT)
check("T6-3. rosterのunique_countはちょうど37（重複0）", stats["unique_count"], 37)
check("T6-4. rosterのduplicate_countは0", stats["duplicate_count"], 0)
check("T6-5. rosterのmissing_countは0（全pathが実在）", stats["missing_count"], 0)
check("T6-6. rosterのmissingリストは空", stats["missing"], [])

roster_set = set(FORMAL_REGRESSION_ROSTER)
architecture_set = set(ARCHITECTURE_ROSTER_19_1)
diff = roster_set.symmetric_difference(architecture_set)
check("T6-7. FORMAL_REGRESSION_ROSTERとARCHITECTURE_ROSTER_19_1の差分は0件", len(diff), 0)
if diff:
    print(f"       差分: {sorted(diff)}")

check_true("T6-8. FORMAL_REGRESSION_ROSTER自体に重複が無い（list長とset長が一致）", len(FORMAL_REGRESSION_ROSTER) == len(roster_set))

print()
print("【重要】本テストはrosterの静的整合性のみを検証する。37ファイルを")
print("実際に実行するFormal Regression本体（19.2節）は、本テストの範囲外である。")


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
