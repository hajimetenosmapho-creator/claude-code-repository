"""
共有レジストリ: baseline-fixed guard（v6.21.0〜v6.24.0）の protected paths ／
allow-list 一元管理

Source of Truth:
    docs/design/zero_diff_guard_registry_foundation.md（v6.26.0）
    DEF-6.23-9（v6.22 DEF-6.22-14 の継続）の実装。GR-9「保護対象パスへ触れる
    Releaseは、それ以前に存在するすべてのbaseline固定guardのallow-listを
    更新する」を、guardファイルN件への直接編集（O(N)）から、本レジストリへの
    寄与追加1件（O(1)）へ置き換える。

設計原則:
    1. 過去に確定した寄与（_SOURCE_CHANGE_CONTRIBUTIONS／_TEST_CHANGE_CONTRIBUTIONS
       の各要素）は追記後、値を変更しない（append-only）。将来Releaseが同じ
       protected pathへ再度触れる場合も、新しい寄与record を追加するのみで、
       既存recordを書き換えない。
    2. 各guardは「自身のRelease以降（自身を含む）に確定した寄与」のみを
       合成する（allowed_source_changes_for/allowed_test_changes_for）。
       同一pathへの複数寄与はfrozenset unionとして合成する（上書きしない。
       Architecture/Code Review Major-1対応）。この合成は寄与recordの並び順に
       依存しない決定的なpure関数であり、呼び出し側へ可変stateを渡さない
       （frozenset／新規dictを都度返す）。
    3. GR-1（保護対象を削除しない）：PROTECTED_PATHS は追記のみ。ただし
       真に新規のpathの追記は、historical guardのBASELINE-TRACKED検査との
       整合が必要なため、本Registry FoundationのO(1)自動追従の対象外
       （PROTECTED_PATHS定義直前のコメント・設計書§3.4参照。
       Architecture/Code Review Major-2対応）。
       GR-2（既存guardのBASELINE_COMMITを書き換えない）：BASELINE_COMMITS は
       各guard自身が持つ文字列リテラルの記録用複製であり、guard側の
       BASELINE_COMMIT定義そのものは本Releaseで変更しない
       （MappingProxyTypeで不変性を型として保証する）。
    4. ratchet構造（GR-9）：Releaseの並びが新しいほどwindowが狭くなり、
       最新guardが最も権威的（許可される差分が最も少ない）性質は、
       RELEASE_ORDER上のindex比較のみで保たれる。

本モジュール自体はE2Eではない（test_e2e_ prefixを持たない）。
"""
from __future__ import annotations

from types import MappingProxyType

# ── Release順序（GR-1類推：追記のみ。過去のindexは変更しない） ──
RELEASE_ORDER: tuple[str, ...] = (
    "v6.21.0",
    "v6.22.0",
    "v6.23.0",
    "v6.24.0",
    "v6.25.0",
    "v6.26.0",
    "v6.27.0",
    "v6.28.0",
    "v6.29.0",
    "v6.30.0",
    "v6.31.0",
    "v6.32.0",
    "v6.33.0",
)


def release_index(release: str) -> int:
    """RELEASE_ORDER上のreleaseの位置を返す。未登録releaseはValueError。"""
    return RELEASE_ORDER.index(release)


# ── 各guard自身のbaseline commit（記録用複製。GR-2：guard側の定義が正） ──
# guardファイル自身の BASELINE_COMMIT 定数はこのRelease向けに変更しない。
# ここでの複製は、v6.26専用E2Eが「guardファイル内の文字列リテラル」と
# 「設計書が記録する値」の転記整合を確認するために用いる。
BASELINE_COMMITS: MappingProxyType[str, str] = MappingProxyType({
    "v6.21.0": "8d8950684a305bc93c824866578cb30c6b2e4fdd",
    "v6.22.0": "578af6bdaeec23dd0c145a57384369ede433e3e4",
    "v6.23.0": "8fd845348d1ee4c80db8de2942da5f99c2bcf0fd",
    "v6.24.0": "38e2487db5760034f4a994319350244960a42e1b",
    "v6.25.0": "c8ee1c74736284108bf03726ae0dbf730df904fe",
})

# ── 設計書15.3節「変更禁止範囲」（GR-1：削除しない）。
#
# 【重要】新規path追加は本Registry Foundationが提供するO(1)自動追従の対象外。
# v6.21.0〜v6.24.0の各guardはPROTECTED_PATHSをそのまま検査対象として使い、
# `NOIMPACT-BASELINE-TRACKED`（`git ls-tree` at 各guard自身のBASELINE_COMMIT）
# で「その保護対象パスが自guardのbaseline commit時点で追跡されていること」を
# 検証している。ここへ真に新規のpath（v6.21.0〜v6.24.0いずれのbaseline commit
# 時点でも存在しなかったpath）を追記すると、historical guard側は自動的に
# この新pathも検査対象へ含めてしまい、baseline commit時点では存在しないため
# `NOIMPACT-BASELINE-TRACKED`が必ずFAILする（Architecture/Code Review
# Major-2、`docs/design/zero_diff_guard_registry_foundation.md` §3.4参照）。
# 本Registry Foundationは、historical guard側への例外処理・除外listの
# 導入をあえて行わない（scope外）。新規path追加を行うRelease自身が、
# 影響を受けるhistorical guardへの対応方針（除外list導入・baseline
# commit更新の是非等）を個別に設計すること。
PROTECTED_PATHS: tuple[str, ...] = (
    "src/image_resolver.py",
    "src/outputs",
    "src/logger",
    "src/analytics",
    "src/pipeline",
    "src/ai",
    "src/scheduler",
    "src/wordpress_media",
    "src/ai_image_generation",
    "src/openai_image_generation",
    "src/generated_image_wordpress_media",
    "src/article_featured_media",
    "src/article_featured_media_orchestration",
    "src/image_generation_config",
    "src/generated_image_filename_policy",
    "src/article_image_prompt_construction",
    "src/article_featured_media_composition",
    "src/image_generation_fallback_policy",
    "src/article_featured_media_runtime",
    "scripts",
    "requirements.txt",
    ".env.example",
)

# ── production allow-list への寄与（GR-9・GR-4）。1要素 = 「保護対象パスP
# に対し、release Rが（自身または過去のReleaseに対する再宣言として）意図的な
# 変更を許可した」という事実。3要素目のfrozensetは、そのRelease時点で
# 許容される「Pの下で変更してよいファイル集合」全体（union後の最終形）。
# 複数Releaseが同じPathへ重ねて宣言する場合、最も新しいReleaseのrecordを
# 追加する（過去recordは書き換えない。append-only）。
_SOURCE_CHANGE_CONTRIBUTIONS: tuple[tuple[str, str, frozenset], ...] = (
    ("src/wordpress_media", "v6.22.0", frozenset({
        "src/wordpress_media/__init__.py",
        "src/wordpress_media/wordpress_media_uploader.py",
    })),
    ("src/openai_image_generation", "v6.24.0", frozenset({
        "src/openai_image_generation/openai_image_generator.py",
    })),
    ("src/image_generation_fallback_policy", "v6.25.0", frozenset({
        "src/image_generation_fallback_policy/image_generation_fallback_policy.py",
        "src/image_generation_fallback_policy/__init__.py",
    })),
    ("src/article_featured_media_runtime", "v6.25.0", frozenset({
        "src/article_featured_media_runtime/article_featured_media_runtime.py",
        "src/article_featured_media_runtime/__init__.py",
    })),
    ("src/logger", "v6.25.0", frozenset({
        "src/logger/log_entry.py",
        "src/logger/log_manager.py",
    })),
    ("src/image_generation_config", "v6.27.0", frozenset({
        "src/image_generation_config/image_generation_config.py",
    })),
    # v6.30.0（Production Canonical Run & Outcome Contract Foundation）：
    # subprocess出力のbytes正規化（src/pipeline/news_pipeline_runner.py）と、
    # run_workflow_engine.py の Outcome Contract対応（scripts/run_workflow_engine.py）。
    ("src/pipeline", "v6.30.0", frozenset({
        "src/pipeline/news_pipeline_runner.py",
    })),
    ("scripts", "v6.30.0", frozenset({
        "scripts/run_workflow_engine.py",
    })),
    # v6.32.0（Side-Effect Fail-Closed & Human Review Safety）：Explicit
    # Side-Effect Execution Mode専用channelの新設・伝播に伴う承認済み変更
    # （docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    # 22.1f節）。
    ("src/ai", "v6.32.0", frozenset({
        "src/ai/agent_context.py",
        "src/ai/agent_manager.py",
        # sub-milestone 6C（§28.-36節test#8、22.3.12節）：agent_executor.pyへの
        # SideEffectExecutionModeContractError carve-out追加。
        "src/ai/agent_executor.py",
        "src/ai/news_agent.py",
        "src/ai/publish_trigger_agent.py",
        "src/ai/workflow_trigger_agent.py",
        "src/ai/workflow_runner.py",
        "src/ai/workflow_context.py",
        "src/ai/workflow_step_executor.py",
        "src/ai/ai_publish_service.py",
    })),
    ("src/pipeline", "v6.32.0", frozenset({
        "src/pipeline/news_pipeline_runner.py",
        "src/pipeline/publish_pipeline_runner.py",
        "src/pipeline/workflow_pipeline_runner.py",
    })),
    ("scripts", "v6.32.0", frozenset({
        "scripts/run_news_agent.py",
        "scripts/run_workflow_trigger_agent.py",
        "scripts/run_publish_trigger_agent.py",
        "scripts/run_review_trigger_agent.py",
        "scripts/run_ai_publish.py",
        "scripts/run_ai_workflow.py",
        "scripts/run_workflow_engine.py",
    })),
    # v6.32.0 sub-milestone 3（呼び出し箇所A：NEWS / WordPressOutput.save()）：
    # __init__()へside_effect_execution_context（必須）・draft_state_manager
    # （Optional）引数を追加し、save()をExplicit Execution Mode対応へ改修した
    # （15.7・22.3.1節）。
    # v6.32.0 sub-milestone 3・completion gap（22.3.13節(2)）：wordpress_output.py
    # （呼び出し箇所A本体）＋manager.py（OutputManager.save_all()の
    # SideEffectExecutionModeContractError carve-out）の承認済み変更。
    ("src/outputs", "v6.32.0", frozenset({
        "src/outputs/wordpress_output.py",
        "src/outputs/manager.py",
    })),
    # v6.33.0（Retry Observability Runtime Integration）：Retry Runtimeへの
    # RetryObservabilityPipeline配線（scripts/run_retry_runtime.py）と、
    # scripts/show_retry_notification.pyのPipelineへの薄い委譲統一
    # （docs/design/retry_observability_runtime_integration_foundation.md
    # AD-2・AD-6）に伴う承認済み変更。
    ("scripts", "v6.33.0", frozenset({
        "scripts/run_retry_runtime.py",
        "scripts/show_retry_notification.py",
    })),
)

# ── tests/ allow-list への寄与（GR-9）。1要素 = 「このtest fileが、
# 記載されたreleaseの時点（またはそれ以前のReleaseへの遡及）で最後に
# 変更された」という事実。ファイル名はbasenameのみ（既存guardの
# Path(...).name正規化と揃える）。 ──
_TEST_CHANGE_CONTRIBUTIONS: tuple[tuple[str, str], ...] = (
    ("test_e2e_v6_13_0_article_featured_media_binding_foundation.py", "v6.21.0"),
    ("test_e2e_v6_9_0_wordpress_media_upload_foundation.py", "v6.22.0"),
    ("test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py", "v6.24.0"),
    ("test_e2e_v6_20_0_article_featured_media_runtime_foundation.py", "v6.25.0"),
    ("test_e2e_v6_21_0_article_featured_media_runtime_wiring.py", "v6.24.0"),
    (
        "test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py",
        "v6.24.0",
    ),
    ("test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py", "v6.24.0"),
    (
        "test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py",
        "v6.24.0",
    ),
    (
        "test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_"
        "refinement_foundation.py",
        "v6.24.0",
    ),
    ("test_e2e_v6_25_0_image_generation_fallback_observability_foundation.py", "v6.25.0"),
    # v6.26.0（DEF-6.23-9）自身。共有レジストリの新設と、v6.21.0〜v6.24.0の
    # 4ファイルを本レジストリ参照へ切り替える改修（値・判定結果は不変）。
    ("zero_diff_guard_registry.py", "v6.26.0"),
    ("test_e2e_v6_26_0_zero_diff_guard_registry_foundation.py", "v6.26.0"),
    ("test_e2e_v6_21_0_article_featured_media_runtime_wiring.py", "v6.26.0"),
    (
        "test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py",
        "v6.26.0",
    ),
    (
        "test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py",
        "v6.26.0",
    ),
    (
        "test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_"
        "refinement_foundation.py",
        "v6.26.0",
    ),
    # v6.27.0（DI-9 Image Generation Gate Value Strict Validation）自身。
    # v6.15.0 Gate ContractのE2Eへ新規WARNシナリオを追加し、共有レジストリ
    # （本ファイル）とv6.26.0自身のE2E（future-fragileだったSELF/SNAPSHOT
    # assertionの修正）を変更した。
    ("test_e2e_v6_15_0_image_generation_configuration_gate.py", "v6.27.0"),
    ("zero_diff_guard_registry.py", "v6.27.0"),
    ("test_e2e_v6_26_0_zero_diff_guard_registry_foundation.py", "v6.27.0"),
    ("test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py", "v6.27.0"),
    # v6.28.0（DI-6 Article Media Upload State Foundation）自身。新規独立
    # パッケージ（src/article_media_upload_state）はPROTECTED_PATHS対象外の
    # ためsource contributionは不要。tests/への新規E2E追加、その追加を
    # 許容するための本レジストリ自身の編集、および将来Releaseのappendを
    # 拒否するover-constraintだったv6.27.0自身のREGISTRY-1/2をratchet-safe
    # 契約へ修正したためのtest_e2e_v6_27_0_*.py自身の編集の3件を登録する。
    ("test_e2e_v6_28_0_article_media_upload_state_foundation.py", "v6.28.0"),
    ("zero_diff_guard_registry.py", "v6.28.0"),
    ("test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py", "v6.28.0"),
    # v6.29.0（Retry Observability Pipeline Foundation）自身。新規独立パッケージ
    # （src/retry_observability_pipeline）はPROTECTED_PATHS対象外のためsource
    # contributionは不要。tests/への新規E2E追加と、その追加を許容するための
    # 本レジストリ自身の編集（RELEASE_ORDERへの"v6.29.0"追記本体）の2件を登録する。
    ("test_e2e_v6_29_0_retry_observability_pipeline_foundation.py", "v6.29.0"),
    ("zero_diff_guard_registry.py", "v6.29.0"),
    # v6.30.0（Production Canonical Run & Outcome Contract Foundation）自身。
    # 新規E2E追加と、その追加・上記2件のsource contributionを許容するための
    # 本レジストリ自身の編集（RELEASE_ORDERへの"v6.30.0"追記本体）を登録する。
    (
        "test_e2e_v6_30_0_production_canonical_run_outcome_contract_foundation.py",
        "v6.30.0",
    ),
    ("zero_diff_guard_registry.py", "v6.30.0"),
    # v6.30.0：execution_history / workflow_engine のrun_idベースAPI移行に伴い、
    # 既存E2E（v2.7.0 / v2.8.0 / v2.9.0）もあわせて改訂した3件を登録する。
    ("test_e2e_v2_7_0_workflow_engine_foundation.py", "v6.30.0"),
    ("test_e2e_v2_8_0_execution_history_foundation.py", "v6.30.0"),
    ("test_e2e_v2_9_0_workflow_monitor_foundation.py", "v6.30.0"),
    # v6.30.0：main.py（Outcome Contract）・src/pipeline/news_pipeline_runner.py
    # （bytes正規化・NEWS Outcome Token）・src/execution_history/*・
    # src/workflow_engine/*（run_idベースAPI移行）の承認済み変更により、
    # これらpathへの「無変更」を独自にhardcodeしていた既存E2E（registry導入
    # 以前の各Releaseが個別に持つ、本registryを参照しないstandalone guard）が
    # 副作用として壊れるため、正規のRelease 6.30 Human-directed continuation
    # としてPROTECTED_PATHS側のcontribution（本ファイル冒頭）とは別に、
    # 該当pathの検査を狭く除外する改訂を行った既存E2E一式を登録する
    # （個々の除外方法・対象pathは各ファイル内のコメントを参照）。
    ("test_e2e_v2_2_0_news_agent_foundation.py", "v6.30.0"),
    ("test_e2e_v2_3_0_workflow_trigger_agent_foundation.py", "v6.30.0"),
    ("test_e2e_v2_4_0_publish_trigger_agent_foundation.py", "v6.30.0"),
    ("test_e2e_v2_5_0_review_trigger_agent_foundation.py", "v6.30.0"),
    ("test_e2e_v2_6_0_scheduler_agent_foundation.py", "v6.30.0"),
    ("test_e2e_v3_0_0_retry_engine_foundation.py", "v6.30.0"),
    ("test_e2e_v3_1_0_retry_queue_foundation.py", "v6.30.0"),
    ("test_e2e_v3_2_0_retry_queue_integration.py", "v6.30.0"),
    ("test_e2e_v3_3_0_retry_scheduler_integration.py", "v6.30.0"),
    ("test_e2e_v3_8_0_retry_engine_event_consumption.py", "v6.30.0"),
    ("test_e2e_v3_9_0_retry_engine_event_dispatch.py", "v6.30.0"),
    ("test_e2e_v4_0_0_retry_execution_foundation.py", "v6.30.0"),
    ("test_e2e_v4_1_0_retry_queue_update_foundation.py", "v6.30.0"),
    ("test_e2e_v4_2_0_retry_queue_removal_foundation.py", "v6.30.0"),
    ("test_e2e_v4_3_0_retry_queue_cleanup_foundation.py", "v6.30.0"),
    ("test_e2e_v4_4_0_retry_queue_notfound_disabled_cleanup_foundation.py", "v6.30.0"),
    ("test_e2e_v4_5_0_retry_policy_foundation.py", "v6.30.0"),
    ("test_e2e_v4_6_0_retry_enqueue_trigger_foundation.py", "v6.30.0"),
    ("test_e2e_v4_7_0_retry_history_foundation.py", "v6.30.0"),
    ("test_e2e_v4_8_0_retry_enqueue_guard.py", "v6.30.0"),
    ("test_e2e_v4_9_0_retry_attempt_synchronization_foundation.py", "v6.30.0"),
    ("test_e2e_v5_0_0_retry_enqueue_guard_refinement_foundation.py", "v6.30.0"),
    ("test_e2e_v5_1_0_retry_composition_root_foundation.py", "v6.30.0"),
    ("test_e2e_v5_2_0_retry_runtime_orchestrator_foundation.py", "v6.30.0"),
    ("test_e2e_v5_3_0_retry_runtime_run_once_foundation.py", "v6.30.0"),
    ("test_e2e_v5_4_0_retry_runtime_script_entry_point_foundation.py", "v6.30.0"),
    ("test_e2e_v5_5_0_retry_runtime_loop_foundation.py", "v6.30.0"),
    ("test_e2e_v5_6_0_retry_runtime_safe_dry_run_foundation.py", "v6.30.0"),
    ("test_e2e_v5_7_0_retry_runtime_safe_dry_run_wiring_foundation.py", "v6.30.0"),
    ("test_e2e_v5_8_0_retry_enqueue_trigger_dry_run_foundation.py", "v6.30.0"),
    ("test_e2e_v5_9_0_retry_runtime_loop_wiring_foundation.py", "v6.30.0"),
    ("test_e2e_v6_28_0_article_media_upload_state_foundation.py", "v6.30.0"),
    # v6.27.0自身のZERODIFF-4（main.pyのRELEASE_START_HEAD基準ゼロdiff検査）も、
    # 既存のv6.28.0での前例と同一パターンでRelease 6.30以降スキップへ改訂した
    # ため登録する。
    ("test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py", "v6.30.0"),
    # v6.31.0（Retry Lineage, Eligibility & Durable Attempt State）自身。新規独立
    # パッケージ（src/retry_lineage）はPROTECTED_PATHS対象外のためsource
    # contributionは不要（v6.29.0と同じ扱い）。tests/への新規E2E追加と、その追加を
    # 許容するための本レジストリ自身の編集（RELEASE_ORDERへの"v6.31.0"追記本体）の
    # 2件を登録する。
    ("test_e2e_v6_31_0_retry_lineage_eligibility_durable_attempt_state.py", "v6.31.0"),
    ("zero_diff_guard_registry.py", "v6.31.0"),
    # v6.31.0：Release 6.31の承認済み変更（src/retry_engine・src/retry_composition・
    # src/retry_enqueue_trigger・src/retry_runtime_orchestrator・
    # src/workflow_engine・src/execution_historyの一部ファイル）により、これらpathへの
    # 「無変更」を独自にhardcodeしていた既存E2E（registry導入以前の各Releaseが個別に
    # 持つ、本registryを参照しないstandalone guard）が副作用として壊れるため、
    # 6.30の§32 Historical Zero-Diff Guard Migrationと同一パターンで、該当pathの
    # 検査を狭く除外する改訂を行った既存E2E一式を登録する（個々の除外方法・対象path
    # は各ファイル内のコメントを参照）。
    ("test_e2e_v5_9_0_retry_runtime_loop_wiring_foundation.py", "v6.31.0"),
    ("test_e2e_v6_0_0_retry_runtime_lock_foundation.py", "v6.31.0"),
    ("test_e2e_v6_1_0_retry_runtime_graceful_shutdown_foundation.py", "v6.31.0"),
    ("test_e2e_v6_2_0_structured_loop_logging_foundation.py", "v6.31.0"),
    ("test_e2e_v6_3_0_retry_metrics_foundation.py", "v6.31.0"),
    ("test_e2e_v6_4_0_retry_monitoring_foundation.py", "v6.31.0"),
    # v6.31.0：test_e2e_v6_30_0自身のテスト#39（Retry Runtime Ruling A）が
    # RetryManager/RetryExecutorを旧APIで直接構築していたため、新しい必須引数
    # （lineage）を満たす最小限のFakeを追加する改訂を行った。
    (
        "test_e2e_v6_30_0_production_canonical_run_outcome_contract_foundation.py",
        "v6.31.0",
    ),
    # v6.32.0（Side-Effect Fail-Closed & Human Review Safety）自身。新規独立
    # パッケージ（src/side_effect_safety・src/wordpress_draft_state）と
    # src/retry_lineage・src/retry_engine・src/retry_composition配下の変更は
    # いずれもPROTECTED_PATHS対象外のためsource contributionは不要。
    # tests/への新規E2E追加（sub-milestone 0・1）と、その追加・上記
    # src/ai・src/pipeline・scriptsのsource contributionを許容するための
    # 本レジストリ自身の編集（RELEASE_ORDERへの"v6.32.0"追記本体）を登録する。
    ("test_e2e_v6_32_0_side_effect_fail_closed_foundation.py", "v6.32.0"),
    ("test_e2e_v6_32_1_hrr_lifecycle.py", "v6.32.0"),
    ("test_e2e_v6_32_2_provenance_propagation.py", "v6.32.0"),
    ("zero_diff_guard_registry.py", "v6.32.0"),
    # v6.32.0：Explicit Side-Effect Execution Mode専用channelの新設・伝播に伴い、
    # これらpathへの「無変更」を独自にhardcodeしていた既存E2E（registry導入
    # 以前の各Releaseが個別に持つ、本registryを参照しないstandalone guard）が
    # 副作用として壊れるため、v6.30.0のHistorical Zero-Diff Guard Migrationと
    # 同一パターンで、該当pathの検査を狭く除外する改訂を行った既存E2E一式を
    # 登録する（個々の除外方法・対象pathは各ファイル内のコメントを参照）。
    ("test_e2e_v2_2_0_news_agent_foundation.py", "v6.32.0"),
    ("test_e2e_v2_3_0_workflow_trigger_agent_foundation.py", "v6.32.0"),
    ("test_e2e_v2_4_0_publish_trigger_agent_foundation.py", "v6.32.0"),
    ("test_e2e_v2_5_0_review_trigger_agent_foundation.py", "v6.32.0"),
    ("test_e2e_v2_6_0_scheduler_agent_foundation.py", "v6.32.0"),
    ("test_e2e_v2_7_0_workflow_engine_foundation.py", "v6.32.0"),
    ("test_e2e_v2_8_0_execution_history_foundation.py", "v6.32.0"),
    ("test_e2e_v2_9_0_workflow_monitor_foundation.py", "v6.32.0"),
    ("test_e2e_v3_0_0_retry_engine_foundation.py", "v6.32.0"),
    ("test_e2e_v3_1_0_retry_queue_foundation.py", "v6.32.0"),
    ("test_e2e_v3_2_0_retry_queue_integration.py", "v6.32.0"),
    ("test_e2e_v6_26_0_zero_diff_guard_registry_foundation.py", "v6.32.0"),
    ("test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py", "v6.32.0"),
    ("test_e2e_v5_9_0_retry_runtime_loop_wiring_foundation.py", "v6.32.0"),
    ("test_e2e_v5_1_0_retry_composition_root_foundation.py", "v6.32.0"),
    ("test_e2e_v5_2_0_retry_runtime_orchestrator_foundation.py", "v6.32.0"),
    ("test_e2e_v5_4_0_retry_runtime_script_entry_point_foundation.py", "v6.32.0"),
    ("test_e2e_v5_5_0_retry_runtime_loop_foundation.py", "v6.32.0"),
    ("test_e2e_v5_7_0_retry_runtime_safe_dry_run_wiring_foundation.py", "v6.32.0"),
    # v6.32.0 sub-milestone 3（呼び出し箇所A：NEWS / WordPressOutput.save()）自身。
    # 新規E2E追加（test_e2e_v6_32_3_*）と、WordPressOutput.__init__()への必須引数
    # 追加に伴うtest_e2e_v1_11_0自身の構築箇所の改訂（side_effect_execution_context
    # を明示供給するよう変更）、RetryExecutor.execute()→WorkflowEngineManager.run()
    # のprotected context実配線に伴うFakeWorkflowEngineManager群のrun()署名改訂
    # （test_e2e_v6_30_0・test_e2e_v6_31_0）を登録する。
    ("test_e2e_v6_32_3_call_site_a_news_wordpress.py", "v6.32.0"),
    ("test_e2e_v1_11_0_save_result.py", "v6.32.0"),
    (
        "test_e2e_v6_30_0_production_canonical_run_outcome_contract_foundation.py",
        "v6.32.0",
    ),
    ("test_e2e_v6_31_0_retry_lineage_eligibility_durable_attempt_state.py", "v6.32.0"),
    # v6.32.0：src/outputs/wordpress_output.py（呼び出し箇所A、15.7節）の変更に伴い、
    # main.pyのWordPressOutputをFakeへ差し替えて実行する既存E2E（v6.25.0・v6.28.0）
    # のFake側もfrom_env()→from_env_with_context()追従・src/outputsの
    # unchanged_paths除外を行った。
    ("test_e2e_v6_25_0_image_generation_fallback_observability_foundation.py", "v6.32.0"),
    ("test_e2e_v6_28_0_article_media_upload_state_foundation.py", "v6.32.0"),
    # v6.32.0：src/retry_engine/retry_executor.py（RetryExecutor.execute()→
    # WorkflowEngineManager.run()のprotected context実配線、22.1f節）の承認済み
    # 変更に伴い、"src/retry_engine/retry_executor.py"を独自のunchanged_paths型
    # ハードコードlistへ含めていた既存E2E一式（Release 3.x〜5.x、registry導入
    # 以前のstandalone guard）から当該1行を除外する改訂を行った。
    ("test_e2e_v3_3_0_retry_scheduler_integration.py", "v6.32.0"),
    ("test_e2e_v3_4_0_retry_scheduler_wiring.py", "v6.32.0"),
    ("test_e2e_v3_5_0_retry_scheduler_decision.py", "v6.32.0"),
    ("test_e2e_v3_6_0_retry_scheduler_decision_wiring.py", "v6.32.0"),
    ("test_e2e_v3_7_0_retry_scheduler_event_integration.py", "v6.32.0"),
    ("test_e2e_v3_8_0_retry_engine_event_consumption.py", "v6.32.0"),
    ("test_e2e_v3_9_0_retry_engine_event_dispatch.py", "v6.32.0"),
    ("test_e2e_v4_0_0_retry_execution_foundation.py", "v6.32.0"),
    ("test_e2e_v4_1_0_retry_queue_update_foundation.py", "v6.32.0"),
    ("test_e2e_v4_2_0_retry_queue_removal_foundation.py", "v6.32.0"),
    ("test_e2e_v4_3_0_retry_queue_cleanup_foundation.py", "v6.32.0"),
    ("test_e2e_v4_4_0_retry_queue_notfound_disabled_cleanup_foundation.py", "v6.32.0"),
    ("test_e2e_v4_5_0_retry_policy_foundation.py", "v6.32.0"),
    ("test_e2e_v4_6_0_retry_enqueue_trigger_foundation.py", "v6.32.0"),
    ("test_e2e_v4_7_0_retry_history_foundation.py", "v6.32.0"),
    ("test_e2e_v4_8_0_retry_enqueue_guard.py", "v6.32.0"),
    ("test_e2e_v4_9_0_retry_attempt_synchronization_foundation.py", "v6.32.0"),
    ("test_e2e_v5_0_0_retry_enqueue_guard_refinement_foundation.py", "v6.32.0"),
    # v6.32.0 sub-milestone 4（呼び出し箇所B：NEWS / ArticleFeaturedMediaRuntime
    # 経由のmedia upload）自身。新規E2E追加（test_e2e_v6_32_4_*）と、
    # _apply_featured_media_step()のside_effect_binding方式への変更に伴う
    # test_e2e_v6_21_0自身の改訂（TEST MIGRATION HUMAN GATE承認済み。PROP系
    # シナリオ・LOOP系構造アサーションをFeaturedMediaPropagatedFailure契約へ
    # 追従）を登録する。test_e2e_v6_25_0の1行修正は既存v6.32.0登録で充足する
    # ため重複追加しない。
    ("test_e2e_v6_32_4_call_site_b_media_upload.py", "v6.32.0"),
    ("test_e2e_v6_21_0_article_featured_media_runtime_wiring.py", "v6.32.0"),
    # v6.32.0 sub-milestone 5（呼び出し箇所C：PUBLISH / AiPublishService._post()）
    # 自身。新規E2E追加（test_e2e_v6_32_5_*）と、AiPublishService.run()/_process()/
    # _post()がside_effect_execution_contextを必須引数化したことに伴う
    # test_e2e_v1_18_0・test_e2e_v1_20_0自身の改訂（TEST MIGRATION HUMAN GATE
    # 承認済み。固定legacy contextの追加のみ、security semanticsは無変更）を
    # 登録する。test_e2e_v2_4_0はPublishPipelineRunnerの条件付きkwargs転送を
    # 維持したため無変更・未登録（承認済み方針）。
    ("test_e2e_v6_32_5_call_site_c_publish_wordpress.py", "v6.32.0"),
    ("test_e2e_v1_18_0_ai_publish_foundation.py", "v6.32.0"),
    ("test_e2e_v1_20_0_ai_workflow_foundation.py", "v6.32.0"),
    # sub-milestone 3 completion gap（22.3.13節(2)）自身。新規E2E追加のみ。
    ("test_e2e_v6_32_3b_output_manager_carveout.py", "v6.32.0"),
    # sub-milestone 6B（§28.-34節 Invariant #35 test#4 sink-oriented static
    # oracle）自身。新規E2E追加のみ、srcへの変更なし。
    ("test_e2e_v6_32_6_invariant_35_static_oracle.py", "v6.32.0"),
    # sub-milestone 6B（§28.-34節 Invariant #35 test#3 closure oracle）自身。
    # 新規E2E追加のみ、srcへの変更なし。
    ("test_e2e_v6_32_7_invariant_35_closure_oracle.py", "v6.32.0"),
    # sub-milestone 6C（§28.-37節 Invariant #37 Authoritative Completion
    # Boundary）自身。src/retry_engine/retry_executor.py（PROTECTED_PATHS対象外）
    # へのconsistency validation boundary新設に伴う新規E2E追加。
    ("test_e2e_v6_32_8_invariant_37_boundary_tests.py", "v6.32.0"),
    # v6.32.0：test_e2e_v6_30_0のFake（_fake_apply_featured_media_step）を
    # side_effect_binding方式（22.3.2節）へ追従させた改訂（sub-milestone 4の
    # 見落としを本sub-milestoneのregression sweepで発見・修正）。
    (
        "test_e2e_v6_30_0_production_canonical_run_outcome_contract_foundation.py",
        "v6.32.0",
    ),
    # sub-milestone 6C（§28.-36節 WorkflowRunner Chain Invariant #37 direct
    # closure）自身。新規E2E追加のみ。src/pipeline/workflow_pipeline_runner.py
    # へのcarve-out追加は既存"src/pipeline" v6.32.0 contributionで既に許容済み。
    ("test_e2e_v6_32_9_invariant_37_workflowrunner_chain.py", "v6.32.0"),
    # sub-milestone 6D（Canonical Gap Inventory解消クラスタ群）自身。以下17件は
    # いずれも新規E2E追加のみであり、対応するsrc/配下の変更はすべて既存の
    # PROTECTED_PATHS対象外パッケージ（src/retry_lineage・src/retry_engine・
    # src/side_effect_safety・src/wordpress_draft_state等）またはFormal
    # Regression remediationターン時点で別途登録済みのcontributionの範囲内で
    # あるため、追加のsource contributionは不要（v6.29.0・v6.31.0と同型の扱い）。
    ("test_e2e_v6_32_10_retry_queue_lineage_authoritative_disposition.py", "v6.32.0"),
    ("test_e2e_v6_32_11_recovery_policy_static_contract.py", "v6.32.0"),
    ("test_e2e_v6_32_12_hrr_reconcile_exclusion.py", "v6.32.0"),
    ("test_e2e_v6_32_13_media_upload_store_composition_root_closure.py", "v6.32.0"),
    ("test_e2e_v6_32_14_design_doc_pseudocode_syntax.py", "v6.32.0"),
    ("test_e2e_v6_32_15_coordinator_lock_race_prevention.py", "v6.32.0"),
    ("test_e2e_v6_32_16_commit_aware_lock_helper_primitives.py", "v6.32.0"),
    ("test_e2e_v6_32_17_ack_determinism_post_commit_cleanup.py", "v6.32.0"),
    ("test_e2e_v6_32_18_record_prepared_recovery_policy_fault_matrix.py", "v6.32.0"),
    ("test_e2e_v6_32_19_wordpress_draft_state_store_contract.py", "v6.32.0"),
    ("test_e2e_v6_32_20_agent_manager_fanout_trusted_composition.py", "v6.32.0"),
    ("test_e2e_v6_32_21_execution_mode_propagation_call_site_ac.py", "v6.32.0"),
    ("test_e2e_v6_32_22_hrr_guard_batch_media_runtime_residual.py", "v6.32.0"),
    ("test_e2e_v6_32_23_news_subprocess_contract_error_residual.py", "v6.32.0"),
    ("test_e2e_v6_32_24_media_safety_residual_cluster.py", "v6.32.0"),
    ("test_e2e_v6_32_25_retry_disposition_reconciliation_residual.py", "v6.32.0"),
    ("test_e2e_v6_32_26_invariant_21_shared_coordination_residual.py", "v6.32.0"),
    # v6.32.0 Phase 2（Protected Operation Manifest Architecture Amendment、
    # production remediation）：primary blocking finding closure・owner_token
    # authority・immutable manifest generation・facade API surface・
    # reconciliation administrative recoveryを検証する新規E2Eと、
    # create_for_attempt()呼び出し箇所を検証するstatic oracleを追加した。
    ("test_e2e_v6_32_27_protected_operation_manifest_production_closure.py", "v6.32.0"),
    ("test_e2e_v6_32_28_protected_operation_manifest_static_oracle.py", "v6.32.0"),
    # Phase 2継続：呼び出し箇所A/C direct evidence（実production class駆動）と、
    # manifest store自体のdirect evidence（冪等性・IOError 3種・vacuous manifest）
    # を追加。
    ("test_e2e_v6_32_29_protected_operation_manifest_call_site_evidence.py", "v6.32.0"),
    # Phase 2継続：呼び出し箇所B（main.py、MEDIA_UPLOAD）のGate ON/OFF manifest
    # registration direct evidence。
    ("test_e2e_v6_32_30_protected_operation_manifest_call_site_b_evidence.py", "v6.32.0"),
    # v6.32.0 §18 CLAIMED Orphan Lock-State Matrix & Hard-Crash Durability
    # Closure（test#22 + test#25）。新規E2E追加と、実際にhard crashする
    # child process用のtest-owned helper（test_ prefixを持たずpytest収集対象外、
    # subprocess経由でのみ起動される）を追加した。srcへの変更なし。
    ("hard_crash_worker_v6_32_31.py", "v6.32.0"),
    ("test_e2e_v6_32_31_claimed_orphan_lock_state_hard_crash.py", "v6.32.0"),
    # §18 test#7 + test#8（Confirmed-Mismatch & Manifest-Corruption Path
    # Closure）自身。新規E2E追加のみ、srcへの変更なし。
    ("test_e2e_v6_32_32_confirmed_mismatch_manifest_corruption_closure.py", "v6.32.0"),
    # §18 test#14（Manifest Read Error Taxonomy Closure）自身。新規E2E追加のみ、
    # srcへの変更なし。
    ("test_e2e_v6_32_33_manifest_read_error_taxonomy_closure.py", "v6.32.0"),
    # §18 test#16（Admission Precheck Regression）自身。新規E2E追加のみ、srcへの
    # 変更なし。
    ("test_e2e_v6_32_34_admission_precheck_regression.py", "v6.32.0"),
    # §18 test#13 + test#17（Admission Failure / Durable Save Failure
    # Closure）自身。新規E2E追加のみ、srcへの変更なし。
    ("test_e2e_v6_32_35_admission_failure_durable_save_failure_closure.py", "v6.32.0"),
    # §18 test#6 + test#9（Terminalization Completeness Closure）自身。
    # 新規E2E追加のみ、srcへの変更なし。
    ("test_e2e_v6_32_36_media_upload_terminalization_and_vacuous_manifest_closure.py", "v6.32.0"),
    # §18 test#23（_reconcile_all_locked() static oracle）自身。新規E2E追加のみ、
    # srcへの変更なし。
    ("test_e2e_v6_32_37_reconcile_all_locked_static_oracle.py", "v6.32.0"),
    # v6.33.0（Retry Observability Runtime Integration）自身。新規独立package
    # （src/retry_runtime_observability）はPROTECTED_PATHS対象外のためsource
    # contributionは不要。新規E2E追加と、その追加・上記scripts source
    # contributionを許容するための本レジストリ自身の編集
    # （RELEASE_ORDERへの"v6.33.0"追記本体）を登録する。
    ("test_e2e_v6_33_0_retry_observability_runtime_integration_foundation.py", "v6.33.0"),
    ("zero_diff_guard_registry.py", "v6.33.0"),
    # v6.33.0：scripts/show_retry_notification.py::build_report()のPipelineへの
    # 委譲統一（AD-6）に伴い、CLIローカルのEvaluator/Builderクラス参照を
    # monkeypatchしていた既存テスト4箇所（PI-5A/PI-5B/EX-1/EX-2）のpatch対象を、
    # 実際にクラス参照を解決するretry_observability_pipeline.retry_observability_pipeline
    # モジュールへ再配置した（AD-6a。アサーション内容自体は無変更）。
    ("test_e2e_v6_8_0_retry_notification_cli_report_wiring_foundation.py", "v6.33.0"),
    # v6.33.0（Independent Code Review Round 1 MAJOR-2/Round 2 MINOR-4対応）：
    # src/retry_runtime_logging（log_cycle()のbool化）・scripts/run_retry_runtime.py
    # （RetryObservabilityPipeline配線）の承認済み変更により、これらpathの
    # 無変更を独自にhardcodeしていた既存E2E（registry導入以前の各Releaseが
    # 個別に持つ、本registryを参照しないstandalone guard）3ファイルが副作用として
    # 壊れるため、v6.30.0/v6.31.0/v6.32.0のHistorical Zero-Diff Guard Migrationと
    # 同一パターンで、該当pathの検査を狭く除外する改訂を行った既存E2E一式を
    # 登録する（個々の除外方法・対象pathは各ファイル内のコメントを参照。
    # `docs/CHANGELOG.md` `[KI-32]`参照）。
    ("test_e2e_v5_5_0_retry_runtime_loop_foundation.py", "v6.33.0"),
    ("test_e2e_v6_3_0_retry_metrics_foundation.py", "v6.33.0"),
    ("test_e2e_v6_4_0_retry_monitoring_foundation.py", "v6.33.0"),
    # v6.33.0（正式Formal Regression検証時に発見された[KI-32]対応漏れ）：
    # test_e2e_v6_27_0自身が持つ独自の_ZERODIFF1_ALLOWED_EXCEPTIONS["scripts"]
    # （本registryを参照しないstandalone guard）が、上記3ファイルと同型の
    # 理由（scripts/run_retry_runtime.py・scripts/show_retry_notification.pyへの
    # 承認済み変更）でFAILしていたため、同一パターンの狭い除外編集を追加登録する。
    ("test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py", "v6.33.0"),
)


def _merge_source_contributions(contributions, min_index: int) -> dict:
    """(path, threshold_release, files)のtupleを、min_index以上のwindowで
    frozenset unionとして合成する（Architecture/Code Review Major-1対応）。

    同一pathへの寄与が複数件existする場合、後発の寄与が先発の寄与を
    上書きするのではなく、両方のfiles集合の和集合が許容される。
    _TEST_CHANGE_CONTRIBUTIONS側（flat frozensetのunion）とunion方針を揃える。
    releaseに紐付かない純粋関数として切り出し、v6.26 E2Eから合成dataを
    差し替えてunion挙動そのものを独立検証できるようにする。
    """
    result: dict = {}
    for path, threshold_release, files in contributions:
        if release_index(threshold_release) >= min_index:
            result[path] = result.get(path, frozenset()) | files
    return result


def allowed_source_changes_for(release: str) -> dict:
    """release自身のguardが許容すべき protected path → 許容ファイル集合を返す。

    releaseのwindow（自身を含みRELEASE_ORDER上で自身以降）に閾値が
    含まれる寄与のみを合成する。同一pathへの複数寄与はfrozenset unionと
    なる（_merge_source_contributions）。呼び出しごとに新しいdictを返す
    （可変stateを共有しない）。
    """
    return _merge_source_contributions(_SOURCE_CHANGE_CONTRIBUTIONS, release_index(release))


def allowed_test_changes_for(release: str) -> frozenset:
    """release自身のguardが許容すべき tests/ 配下の許容ファイル名集合を返す。"""
    i = release_index(release)
    return frozenset(
        name
        for name, threshold_release in _TEST_CHANGE_CONTRIBUTIONS
        if release_index(threshold_release) >= i
    )
