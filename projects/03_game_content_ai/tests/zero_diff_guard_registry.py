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
