"""
T6: Formal Regression 37-file roster（機械可読capture）。

Source of Truth:
    docs/design/mvp_end_to_end_hardening_validation.md 19.1節
    （確定した37-file roster）・23.2章T6（「上記37ファイルのリストを、
    実装フェーズで新規に追加するtest-only候補へ必須で転記する」）。

本モジュールは、19.1節が確定した37ファイルのリストを機械可読な形で保持する
test-only helperである（`zero_diff_guard_registry.py`と同じ位置づけ、
`test_e2e_` prefixを持たないためpytestの収集対象にもFormal Regression
自身の実行対象にもならない）。

baseline commit: 15c45b9eef23a52313c12ce04663fb8652e4621d（Release 6.34.0）

roster（`FORMAL_REGRESSION_ROSTER`）は、19.1節が確定した37件のbasenameを
固定tupleとして直接列挙したものであり、`glob`等によるimplicit discoveryは
一切行わない。事前承認されたskip/exceptionリストは本モジュール・関連する
静的validation testのいずれにも存在しない（19.3節「免除は与えられない」）。

【重要】本モジュールが提供するのは、rosterの一覧性・静的な整合性（件数・
重複・実在確認）のみである。37ファイルを実際に実行してFormal Regressionを
完了させる作業（19.2節：`python <file>.py`として実行しexit code 0を
確認する）は、本モジュールの範囲外である（19.3節）。Formal Regression
本体の実施記録・結果は`docs/design/mvp_end_to_end_hardening_validation.md`
30.12節を参照。
"""
from __future__ import annotations

from pathlib import Path

TESTS_DIR = Path(__file__).parent

EXPECTED_COUNT = 37

# 設計書19.1節が確定した、正確に37ファイルのroster（tests/直下のbasenameの
# み、zero_diff_guard_registry.pyの既存規約に合わせる）。
# v1.11.0×1 + v5.9.0×1 + v6.0.0〜v6.34.0×35 = 37ファイル。
FORMAL_REGRESSION_ROSTER: tuple[str, ...] = (
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


def resolve_roster_paths() -> tuple[Path, ...]:
    """rosterの各basenameを、tests/直下の絶対Pathへ解決する。"""
    return tuple(TESTS_DIR / name for name in FORMAL_REGRESSION_ROSTER)


def validate_roster_statics() -> dict:
    """rosterの静的な整合性（実行を伴わない）を検証する：
    件数・重複・実在確認のみ。37ファイルを実際に実行するFormal Regression
    本体（19.2節）はこの関数の範囲外。"""
    names = FORMAL_REGRESSION_ROSTER
    unique_names = tuple(dict.fromkeys(names))
    missing = [name for name in names if not (TESTS_DIR / name).is_file()]
    return {
        "count": len(names),
        "unique_count": len(unique_names),
        "duplicate_count": len(names) - len(unique_names),
        "missing": missing,
        "missing_count": len(missing),
    }
