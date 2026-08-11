"""
E2E テスト: v6.26.0 Zero-Diff Guard Registry Foundation（DEF-6.23-9）

Source of Truth:
    docs/design/zero_diff_guard_registry_foundation.md

v6.22.0 DEF-6.22-14 の継続として v6.23.0 で提起され、v6.24.0 で緊急度を
再確認された DEF-6.23-9（zero-diff guardの共有レジストリ化）の実装。
v6.21.0〜v6.24.0 の4 baseline-fixed guardが個別に重複保持していた
`_protected_paths`（22件・同一集合）・`_allowed_source_changes`・
`_allowed_test_changes` を `tests/zero_diff_guard_registry.py` へ一元化し、
GR-9（保護対象パスへ触れるReleaseは、それ以前に存在するすべての
baseline固定guardのallow-listを更新する）の維持コストを、guardファイル
N件への直接編集（O(N)）から、レジストリへの寄与追加（O(1)）へ置き換える。

本Releaseは `src/` 本番コードへは一切触れない（tests/ 配下のみ）。
実HTTP通信・実プロセス外部通信は発生しない（git・python子プロセスの
ローカル呼び出しのみ）。

Scenario構成:
    STRUCT-     レジストリの型・不変性（tuple／frozenset・追記のみ）
    PIN-        BASELINE_COMMITSと各guardファイル自身のリテラルとの転記整合（GR-2）
    SNAPSHOT-   v6.21.0〜v6.24.0の許容範囲がrefactor前に確定していた値をすべて
                含んでいる（v6.27.0修正：完全一致ではなく部分集合関係。
                下記「v6.27.0修正」参照）
    MERGE-      同一protected pathキーへの複数寄与がfrozenset unionとして合成される
                （synthetic dataによる独立検証。Architecture/Code Review Major-1対応）
    RATCHET-    release間の許容範囲がRELEASE_ORDER順に単調非増加である（GR-9 ratchet）
    NOMUT-      同一releaseへの複数回呼び出しが独立したdict/frozensetを返す
    CONSOL-     4guardファイルから重複literalが実際に除去されている
    RUNTIME-    v6.21.0〜v6.24.0の4guardを子プロセス実行し、PASS件数が不変であることを実測
    SELF-       v6.26.0自身のbaseline固定guard（v6.26.0自身は直接のsource
                contributionを持たず、tests/ allow-listはtests/配下2ファイルの
                みを許容する。v6.27.0修正：SELF-NO-OWN-SOURCE-CONTRIBUTIONは
                v6.26.0自身が直接登録したrecordのみを検査し、SELF-SRC-SCOPEは
                baseline commitからの実差分を共有レジストリのallow-list
                （v6.21.0〜v6.24.0のNOIMPACT-SCOPEと同一の意味論）で判定する。
                下記「v6.27.0修正」参照）
    CONTRACT-   現在の22 protected pathsがv6.21.0〜v6.24.0の各baseline commit時点で
                すべて追跡されている（新規path追加はO(1)自動追従の対象外。
                Architecture/Code Review Major-2対応）
    FAILCLOSED- 未知・不正なrelease文字列に対しValueErrorを送出する
                （Architecture/Code Review Suggestion対応）
    HERMETIC-   共有レジストリがネットワーク関連importを持たない

v6.27.0修正（DI-9 Image Generation Gate Value Strict Validation。Codexによる
read-only独立Architectureセカンドオピニオンで発見。ユーザーレビューにより
KI化を撤回しtest over-constraint修正へ一本化）:
    v6.26.0完了時点のSELF-ALLOWED-SOURCE-EMPTY・SELF-SRC-ZERO-DIFFおよび
    SNAPSHOT-SOURCE-*／SNAPSHOT-TESTは、いずれも共有レジストリのwindow
    semantics（release自身以降の正当な寄与を自動的に取り込むO(1)機構、
    本Releaseの本旨そのもの）と両立しない過剰制約（test over-constraint）
    だった。window semantics自体・historical BASELINE_COMMITSはいずれも
    変更せず、次のように修正した：
    (a) SELF-ALLOWED-SOURCE-EMPTY（`allowed_source_changes_for("v6.26.0")`の
    合成結果が{}であることの完全一致）は、「v6.26.0自身が直接登録した
    recordのみ」を検査するSELF-NO-OWN-SOURCE-CONTRIBUTIONへ置き換えた。
    (b) SELF-SRC-ZERO-DIFF（baseline commitからの実差分が無条件に空である
    ことの固定）は、v6.21.0〜v6.24.0のNOIMPACT-SCOPEと同一のallow-list
    意味論（「差分が共有レジストリで承認されたsource contributionの範囲を
    超えていない」）へ揃えたSELF-SRC-SCOPEへ置き換えた。v6.26.0自身は
    直接のsource contributionを持たないため、許容される差分は実質的に
    v6.27.0以降が登録した寄与のみであり、無承認の変更は引き続き検知する。
    (c) SNAPSHOT-SOURCE-KEYS／SNAPSHOT-SOURCE-VALUES／SNAPSHOT-TESTは
    完全一致から部分集合関係（golden ⊆ 現在値）へ変更した。
    いずれも旧allow-listの欠落は引き続き検知する（回帰検知力は緩和しない）。
    Known Issueとしては記録しない（テスト側の設計不備の是正であり、
    v6.26.0のProduction Codeやレジストリのwindow semanticsは無改修のため）。
    修正後、v6.26.0自身のE2Eは恒久的なFAILを一切残さない
    （248/248 PASS、実測は本Release報告参照）。

実行方法:
    cd projects/03_game_content_ai
    .\\venv\\Scripts\\python.exe tests\\test_e2e_v6_26_0_zero_diff_guard_registry_foundation.py
"""
import ast
import os
import re
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
TESTS_DIR = Path(__file__).parent
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import zero_diff_guard_registry as registry  # noqa: E402

# ─── テスト用ユーティリティ（v6.21.0〜v6.25.0 precedentを踏襲） ───

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


print("=" * 70)
print("E2E テスト: v6.26.0 Zero-Diff Guard Registry Foundation（DEF-6.23-9）")
print("=" * 70)
print()

# =====================================================================
# STRUCT: レジストリの型・不変性
# =====================================================================

print("[STRUCT] レジストリの型・不変性")

check("STRUCT-PROTECTED-PATHS-TYPE. PROTECTED_PATHSがtuple（不変コンテナ）である",
      type(registry.PROTECTED_PATHS), tuple)
check("STRUCT-PROTECTED-PATHS-COUNT. PROTECTED_PATHSが22件である",
      len(registry.PROTECTED_PATHS), 22)

_EXPECTED_PROTECTED_PATHS = (
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
check("STRUCT-PROTECTED-PATHS-VALUE. PROTECTED_PATHSの内容・順序がv6.21.0〜v6.24.0時点と完全一致する",
      registry.PROTECTED_PATHS, _EXPECTED_PROTECTED_PATHS)

check("STRUCT-RELEASE-ORDER-TYPE. RELEASE_ORDERがtuple（不変コンテナ）である",
      type(registry.RELEASE_ORDER), tuple)
_KNOWN_RELEASES = ("v6.21.0", "v6.22.0", "v6.23.0", "v6.24.0", "v6.25.0", "v6.26.0")
check_true(
    "STRUCT-RELEASE-ORDER-MONOTONIC. 既知releaseがRELEASE_ORDER上でこの順序どおり単調増加のindexを持つ",
    [registry.release_index(r) for r in _KNOWN_RELEASES]
    == sorted(registry.release_index(r) for r in _KNOWN_RELEASES),
)

for _rel in ("v6.21.0", "v6.22.0", "v6.23.0", "v6.24.0"):
    _sample = registry.allowed_source_changes_for(_rel)
    for _path, _files in _sample.items():
        check_true(
            f"STRUCT-SOURCE-FROZENSET[{_rel}/{_path}]. allow-listのファイル集合がfrozensetである",
            isinstance(_files, frozenset),
        )
    _test_sample = registry.allowed_test_changes_for(_rel)
    check_true(f"STRUCT-TEST-FROZENSET[{_rel}]. allowed_test_changes_forの戻り値がfrozensetである",
               isinstance(_test_sample, frozenset))
print()

# =====================================================================
# PIN: BASELINE_COMMITSと各guardファイル自身のリテラルとの転記整合（GR-2）
# =====================================================================

print("[PIN] BASELINE_COMMITSと各guardファイル自身のリテラルとの転記整合（GR-2）")

_GUARD_FILES_BY_RELEASE = {
    "v6.21.0": "test_e2e_v6_21_0_article_featured_media_runtime_wiring.py",
    "v6.22.0": "test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py",
    "v6.23.0": "test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py",
    "v6.24.0":
        "test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_"
        "refinement_foundation.py",
}
_BASELINE_COMMIT_RE = re.compile(r'BASELINE_COMMIT\s*=\s*"([0-9a-f]{40})"')

_guard_sources: dict = {}
for _rel, _fname in _GUARD_FILES_BY_RELEASE.items():
    _path = TESTS_DIR / _fname
    check_true(f"PIN-FILE-EXISTS[{_rel}]. guardファイルが実在する", _path.exists())
    _source = _path.read_text(encoding="utf-8")
    _guard_sources[_rel] = _source
    _match = _BASELINE_COMMIT_RE.search(_source)
    check_true(f"PIN-BASELINE-FOUND[{_rel}]. guardファイル自身にBASELINE_COMMITリテラルが存在する（GR-2：本Releaseで削除しない）",
               _match is not None)
    if _match is not None:
        check(f"PIN-BASELINE-MATCH[{_rel}]. guardファイル自身のBASELINE_COMMITがレジストリの記録値と一致する",
              _match.group(1), registry.BASELINE_COMMITS[_rel])
print()

# =====================================================================
# SNAPSHOT: v6.21.0〜v6.24.0の計算結果がrefactor前の値と完全一致
# =====================================================================

print("[SNAPSHOT] v6.21.0〜v6.24.0の計算結果がrefactor前の値と完全一致（+v6.26自身の2件のみ）")

# refactor直前（v6.25.0完了時点＝c8ee1c7）の各guardファイルが持っていた
# _allowed_source_changes・_allowed_test_changesのリテラル値（本テストの
# golden reference。git logで復元可能だが、実測との差分読解性のためここに
# 直接埋め込む）。レジストリ（zero_diff_guard_registry.py）の計算結果から
# 生成した値ではない。Architecture/Code Review（commit前）で、
# `git show HEAD:<file>`によるAST再抽出という別経路で独立に値を再検証し、
# 完全一致を確認済み（`docs/design/zero_diff_guard_registry_foundation.md`
# §9 Suggestion-2）。
_WORDPRESS_ENTRY = frozenset({
    "src/wordpress_media/__init__.py",
    "src/wordpress_media/wordpress_media_uploader.py",
})
_OPENAI_ENTRY = frozenset({
    "src/openai_image_generation/openai_image_generator.py",
})
_FALLBACK_POLICY_ENTRY = frozenset({
    "src/image_generation_fallback_policy/image_generation_fallback_policy.py",
    "src/image_generation_fallback_policy/__init__.py",
})
_RUNTIME_ENTRY = frozenset({
    "src/article_featured_media_runtime/article_featured_media_runtime.py",
    "src/article_featured_media_runtime/__init__.py",
})
_LOGGER_ENTRY = frozenset({
    "src/logger/log_entry.py",
    "src/logger/log_manager.py",
})

_GOLDEN_SOURCE_CHANGES = {
    "v6.21.0": {
        "src/wordpress_media": _WORDPRESS_ENTRY,
        "src/openai_image_generation": _OPENAI_ENTRY,
        "src/image_generation_fallback_policy": _FALLBACK_POLICY_ENTRY,
        "src/article_featured_media_runtime": _RUNTIME_ENTRY,
        "src/logger": _LOGGER_ENTRY,
    },
    "v6.22.0": {
        "src/wordpress_media": _WORDPRESS_ENTRY,
        "src/openai_image_generation": _OPENAI_ENTRY,
        "src/image_generation_fallback_policy": _FALLBACK_POLICY_ENTRY,
        "src/article_featured_media_runtime": _RUNTIME_ENTRY,
        "src/logger": _LOGGER_ENTRY,
    },
    "v6.23.0": {
        "src/openai_image_generation": _OPENAI_ENTRY,
        "src/image_generation_fallback_policy": _FALLBACK_POLICY_ENTRY,
        "src/article_featured_media_runtime": _RUNTIME_ENTRY,
        "src/logger": _LOGGER_ENTRY,
    },
    "v6.24.0": {
        "src/openai_image_generation": _OPENAI_ENTRY,
        "src/image_generation_fallback_policy": _FALLBACK_POLICY_ENTRY,
        "src/article_featured_media_runtime": _RUNTIME_ENTRY,
        "src/logger": _LOGGER_ENTRY,
    },
}

_GOLDEN_TEST_CHANGES = {
    "v6.21.0": {
        "test_e2e_v6_13_0_article_featured_media_binding_foundation.py",
        "test_e2e_v6_20_0_article_featured_media_runtime_foundation.py",
        "test_e2e_v6_21_0_article_featured_media_runtime_wiring.py",
        "test_e2e_v6_9_0_wordpress_media_upload_foundation.py",
        "test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py",
        "test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py",
        "test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py",
        "test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py",
        "test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_"
        "refinement_foundation.py",
        "test_e2e_v6_25_0_image_generation_fallback_observability_foundation.py",
    },
    "v6.22.0": {
        "test_e2e_v6_9_0_wordpress_media_upload_foundation.py",
        "test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py",
        "test_e2e_v6_20_0_article_featured_media_runtime_foundation.py",
        "test_e2e_v6_21_0_article_featured_media_runtime_wiring.py",
        "test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py",
        "test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py",
        "test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py",
        "test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_"
        "refinement_foundation.py",
        "test_e2e_v6_25_0_image_generation_fallback_observability_foundation.py",
    },
    "v6.23.0": {
        "test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py",
        "test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py",
        "test_e2e_v6_21_0_article_featured_media_runtime_wiring.py",
        "test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py",
        "test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py",
        "test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_"
        "refinement_foundation.py",
        "test_e2e_v6_20_0_article_featured_media_runtime_foundation.py",
        "test_e2e_v6_25_0_image_generation_fallback_observability_foundation.py",
    },
}
_GOLDEN_TEST_CHANGES["v6.24.0"] = set(_GOLDEN_TEST_CHANGES["v6.23.0"])

# v6.26.0が新規追加する2ファイル。v6.21.0〜v6.24.0のいずれのwindowにも
# 含まれる（v6.26.0はRELEASE_ORDER上で最も新しいため）。
_V626_NEW_FILES = frozenset({
    "zero_diff_guard_registry.py",
    "test_e2e_v6_26_0_zero_diff_guard_registry_foundation.py",
})

# v6.27.0修正（DI-9対応）: 元実装はrefactor前の値との「完全一致」（==）で
# 固定していたが、これはallowed_source_changes_for()/allowed_test_changes_for()
# のwindow semantics（自身以降のReleaseの正当な寄与を自動的に取り込むO(1)機構、
# 本ファイル冒頭のdocstring・§3参照）と本質的に両立しない：v6.27.0以降が
# protected pathへ正当に寄与するたびに、v6.21.0〜v6.24.0視点の許容範囲にも
# その寄与が波及し、完全一致assertionが機械的にFAILしてしまう
# （window semantics自体は変更しない。RATCHET-*が示すとおり許容範囲が
# 単調非増加であることが本来の不変条件である）。
# 「refactor前に確定していた許容範囲が現在も失われていないこと」という
# 本来の目的（regression検知）は、完全一致ではなく部分集合関係
# （golden ⊆ 現在値）で表現すれば、旧allow-listの欠落は引き続き検知しつつ、
# 将来Releaseの正当な追加では壊れない安定した不変条件になる。
for _rel in ("v6.21.0", "v6.22.0", "v6.23.0", "v6.24.0"):
    _got_source = registry.allowed_source_changes_for(_rel)
    check_true(
        f"SNAPSHOT-SOURCE-KEYS[{_rel}]. refactor前に確定していたキー集合が現在もすべて"
        "含まれている（将来Releaseが追加する新規キーは許容し、旧キーの欠落のみを検知する）",
        set(_GOLDEN_SOURCE_CHANGES[_rel].keys()) <= set(_got_source.keys()),
    )
    check_true(
        f"SNAPSHOT-SOURCE-VALUES[{_rel}]. refactor前に確定していた各キーの許容ファイル集合が"
        "現在もすべて維持されている（unionによる新規ファイル追加は許容し、旧ファイルの脱落のみを検知する）",
        all(
            frozenset(_files) <= _got_source.get(_k, frozenset())
            for _k, _files in _GOLDEN_SOURCE_CHANGES[_rel].items()
        ),
    )
    _got_test = set(registry.allowed_test_changes_for(_rel))
    check_true(
        f"SNAPSHOT-TEST[{_rel}]. refactor前の値 ∪ v6.26.0新規2件が現在もすべて許容されている"
        "（将来Releaseが追加する新規test fileは許容し、旧allow-listの欠落のみを検知する）",
        (_GOLDEN_TEST_CHANGES[_rel] | _V626_NEW_FILES) <= _got_test,
    )
print()

# =====================================================================
# MERGE: 同一protected pathキーへの複数寄与がfrozenset unionとして合成される
# （Architecture/Code Review Major-1対応。初版実装は`result[path] = files`と
# いう代入で上書きしており、現在の実データには重複pathがなく実害はなかったが、
# 将来同一pathへ異なるfiles集合で再度寄与するReleaseが現れた時点で過去の
# 許可がサイレントに脱落するlatent defectだった）
# =====================================================================

print("[MERGE] 同一protected pathキーへの複数寄与がunionとして合成される")

# 実際の_SOURCE_CHANGE_CONTRIBUTIONSを一切使わず、synthetic dataのみで
# _merge_source_contributions()のunion挙動そのものを独立検証する。
_SYNTHETIC_CONTRIBUTIONS = (
    ("src/__synthetic_path__", "v6.21.0", frozenset({"src/__synthetic_path__/a.py"})),
    ("src/__synthetic_path__", "v6.23.0", frozenset({"src/__synthetic_path__/b.py"})),
    ("src/__other_path__", "v6.22.0", frozenset({"src/__other_path__/only.py"})),
)

_merged_from_v621 = registry._merge_source_contributions(
    _SYNTHETIC_CONTRIBUTIONS, registry.release_index("v6.21.0")
)
check(
    "MERGE-UNION-BOTH-CONTRIBUTIONS. v6.21.0視点でsrc/__synthetic_path__の許可ファイルが"
    "両寄与のunionになる（overwriteなら後発の寄与のみになるはず）",
    _merged_from_v621["src/__synthetic_path__"],
    frozenset({"src/__synthetic_path__/a.py", "src/__synthetic_path__/b.py"}),
)
check(
    "MERGE-OTHER-PATH-UNCHANGED. union対象と無関係な別pathのエントリはそのまま保持される",
    _merged_from_v621["src/__other_path__"],
    frozenset({"src/__other_path__/only.py"}),
)

_merged_from_v623 = registry._merge_source_contributions(
    _SYNTHETIC_CONTRIBUTIONS, registry.release_index("v6.23.0")
)
check(
    "MERGE-WINDOW-EXCLUDES-EARLIER. v6.23.0視点ではv6.21.0起点の寄与がwindow外になり、"
    "v6.23.0起点の寄与のみが残る（unionはwindow外の寄与までは合成しない）",
    _merged_from_v623["src/__synthetic_path__"],
    frozenset({"src/__synthetic_path__/b.py"}),
)
check_true(
    "MERGE-WINDOW-EXCLUDES-OTHER-PATH. v6.23.0視点ではv6.22.0起点のsrc/__other_path__も"
    "window外になり除去される",
    "src/__other_path__" not in _merged_from_v623,
)

check(
    "MERGE-REAL-DATA-NO-DUPLICATE-KEYS. 実際の_SOURCE_CHANGE_CONTRIBUTIONSには現時点で"
    "protected pathの重複が存在しない（将来重複が追加された場合、この件数比較が変化し"
    "union方針の意図的な確認を促すtrip-wireとなる）",
    len([_p for _p, _, _ in registry._SOURCE_CHANGE_CONTRIBUTIONS]),
    len({_p for _p, _, _ in registry._SOURCE_CHANGE_CONTRIBUTIONS}),
)
print()

# =====================================================================
# RATCHET: release間の許容範囲がRELEASE_ORDER順に単調非増加である（GR-9）
# =====================================================================

print("[RATCHET] release間の許容範囲が単調非増加である（GR-9 ratchet構造）")

_ORDERED_KNOWN = ["v6.21.0", "v6.22.0", "v6.23.0", "v6.24.0"]
for _earlier, _later in zip(_ORDERED_KNOWN, _ORDERED_KNOWN[1:]):
    _earlier_test = registry.allowed_test_changes_for(_earlier)
    _later_test = registry.allowed_test_changes_for(_later)
    check_true(
        f"RATCHET-TEST-SUBSET[{_earlier}->{_later}]. 新しいreleaseのtest allow-listが古いreleaseの部分集合である",
        _later_test <= _earlier_test,
    )
    _earlier_source = registry.allowed_source_changes_for(_earlier)
    _later_source = registry.allowed_source_changes_for(_later)
    check_true(
        f"RATCHET-SOURCE-KEYS-SUBSET[{_earlier}->{_later}]. 新しいreleaseのsource allow-listキー集合が古いreleaseの部分集合である",
        set(_later_source.keys()) <= set(_earlier_source.keys()),
    )
    _common_keys = set(_later_source.keys()) & set(_earlier_source.keys())
    check(
        f"RATCHET-SOURCE-VALUES-STABLE[{_earlier}->{_later}]. 共通キーの許容ファイル集合が両release間で不変である",
        {k: frozenset(_later_source[k]) for k in _common_keys},
        {k: frozenset(_earlier_source[k]) for k in _common_keys},
    )
print()

# =====================================================================
# NOMUT: 同一releaseへの複数回呼び出しが独立したdict/frozensetを返す
# =====================================================================

print("[NOMUT] 複数回呼び出しの独立性（可変stateを共有しない）")

_call_a = registry.allowed_source_changes_for("v6.21.0")
_call_b = registry.allowed_source_changes_for("v6.21.0")
check_true("NOMUT-SOURCE-FRESH-DICT. 呼び出しごとに別のdictオブジェクトが返る",
           _call_a is not _call_b)
_call_a["src/__positive_control_never_exists__"] = frozenset({"dummy.py"})
_call_c = registry.allowed_source_changes_for("v6.21.0")
check_true("NOMUT-SOURCE-NO-LEAK. 一方のdictへの変更がレジストリ内部・以後の呼び出しへ波及しない",
           "src/__positive_control_never_exists__" not in _call_c)

_test_call_a = registry.allowed_test_changes_for("v6.21.0")
_test_call_b = registry.allowed_test_changes_for("v6.21.0")
check("NOMUT-TEST-VALUE-STABLE. frozensetの値そのものは複数回呼び出しで不変である",
      _test_call_a, _test_call_b)
print()

# =====================================================================
# CONSOL: 4guardファイルから重複literalが実際に除去されている
# =====================================================================

print("[CONSOL] 4guardファイルから重複literalが実際に除去されている（DEF-6.23-9の本旨）")

for _rel, _fname in _GUARD_FILES_BY_RELEASE.items():
    _source = _guard_sources[_rel]
    check_true(
        f"CONSOL-IMPORTS-REGISTRY[{_rel}]. guardファイルがzero_diff_guard_registryをimportしている",
        "import zero_diff_guard_registry as _guard_registry" in _source,
    )
    check_false(
        f"CONSOL-NO-DUPLICATE-PROTECTED-PATHS[{_rel}]. _protected_pathsの22件literalが"
        "guardファイル自身にハードコードされていない（レジストリ側へ集約済み）",
        '"src/image_resolver.py",' in _source,
    )
    check_false(
        f"CONSOL-NO-DUPLICATE-WORDPRESS-ENTRY[{_rel}]. wordpress_mediaのallow-list literalが"
        "guardファイル自身にハードコードされていない",
        '"src/wordpress_media/wordpress_media_uploader.py",' in _source,
    )
print()

# =====================================================================
# RUNTIME: v6.21.0〜v6.24.0の4guardを子プロセス実行し、PASS件数が不変であることを実測
# =====================================================================

print("[RUNTIME] 4guardの子プロセス実行によるPASS件数の実測回帰")

# v6.21.0／v6.22.0は_allowed_source_changesのキー集合をループしない固定件数の
# guardであり、refactor前の実測値との完全一致を維持する（future contributionが
# あってもPASS件数は変化しない安定した不変条件）。
_EXPECTED_TOTALS_EXACT = {
    "v6.21.0": 170,
    "v6.22.0": 324,
}
# v6.23.0／v6.24.0は`for _rel, _allowed in _allowed_source_changes.items():`という
# coverage確認ループ（NOIMPACT-SCOPE-COVERAGE／NOIMPACT-SCOPE-EXACT）を持ち、
# その反復回数が共有レジストリの許容キー数に比例する。v6.27.0がsrc/
# image_generation_configへ正当に寄与したことで、このキー集合が1件増え、
# 2 assertion（coverage・exact各1）が新たに追加された（v6.27.0修正）。
# これはGR-9のO(1)自動追従が正しく機能している証拠であり、regressionではない。
# 完全一致ではなく「refactor前の値を下回らない」下限チェックへ変更し、
# 旧チェックの欠落（件数減少）は引き続き検知しつつ、将来の正当な追加では
# 壊れない安定した不変条件にする。
_EXPECTED_TOTALS_FLOOR = {
    "v6.23.0": 345,
    "v6.24.0": 352,
}

_child_env = dict(os.environ)
_child_env["PYTHONIOENCODING"] = "utf-8"

for _rel, _fname in _GUARD_FILES_BY_RELEASE.items():
    _proc = subprocess.run(
        [sys.executable, str(TESTS_DIR / _fname)],
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        encoding="utf-8",
        errors="replace",
        timeout=180,
        env=_child_env,
    )
    check(
        f"RUNTIME-EXIT-ZERO[{_rel}]. guardの子プロセスが終了コード0で終了する",
        _proc.returncode, 0,
    )
    _ok_count = _proc.stdout.count("[OK]")
    _ng_count = _proc.stdout.count("[NG]")
    if _rel in _EXPECTED_TOTALS_EXACT:
        check(
            f"RUNTIME-PASS-COUNT[{_rel}]. PASS件数がrefactor前の実測値と完全一致する"
            "（coverage-loop構造を持たないguardのため、将来contributionの影響を受けない）",
            _ok_count, _EXPECTED_TOTALS_EXACT[_rel],
        )
    else:
        check_true(
            f"RUNTIME-PASS-COUNT[{_rel}]. PASS件数がrefactor前の実測値を下回らない"
            "（coverage-loopの反復回数が共有レジストリの許容キー数に比例するため、"
            "将来の正当なcontributionでPASS件数が増えることは許容する。減少のみを検知する）",
            _ok_count >= _EXPECTED_TOTALS_FLOOR[_rel],
        )
    check(f"RUNTIME-NG-ZERO[{_rel}]. FAILが0件である", _ng_count, 0)
print()

# =====================================================================
# SELF: v6.26.0自身のbaseline固定guard（GR-6：自身のbaseline commitを固定した
# 完全なguardを持つ）。v6.26.0自身はsrc/へ一切触れず、直接の寄与も宣言しない
# ことは、SELF-NO-OWN-SOURCE-CONTRIBUTIONが「v6.26.0自身の直接宣言」のみを
# 検査することで確認する。baseline commitからの実差分は、無条件の空チェック
# ではなく、共有レジストリのallow-list（allowed_source_changes_for()）に
# 承認された範囲内かどうかで判定する（SELF-SRC-SCOPE、v6.27.0修正・下記参照）。
# =====================================================================

print("[SELF] v6.26.0自身のbaseline固定guard")

BASELINE_COMMIT = registry.BASELINE_COMMITS["v6.25.0"]

_rev_proc = subprocess.run(
    ["git", "rev-parse", "--verify", f"{BASELINE_COMMIT}^{{commit}}"],
    cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
)
check_true("SELF-BASELINE-RESOLVABLE. v6.26.0のbaseline commitが解決できる（vacuous pass防止）",
           _rev_proc.returncode == 0)

# v6.27.0修正（DI-9対応。Major修正、KI化を撤回）: 元実装は
# allowed_source_changes_for("v6.26.0")（v6.26.0以降＝自身を含む未来すべての
# window）が{}であることを固定していたが、これは「v6.26.0自身が新たにsrc/へ
# 寄与していない」ことと「将来のReleaseが同じwindowへ寄与する可能性」を
# 区別できていなかった。window semantics（自身以降の正当な寄与を自動的に
# 取り込むO(1)機構）は本Releaseで変更しないため、v6.27.0がsrc/
# image_generation_configへ寄与した時点でこのassertionは機械的にFAILしていた。
# 「v6.26.0自身はsrc本番コードへの変更を一切宣言していない」という本来の不変条件は、
# v6.26.0自身が直接登録したrecordの件数のみを検査すれば、将来Releaseの寄与とは
# 独立に恒久的に安定する（過去recordはGR-1により追記後変更されないため）。
_v6_26_own_source_contributions = [
    (_path, _threshold, _files)
    for _path, _threshold, _files in registry._SOURCE_CHANGE_CONTRIBUTIONS
    if _threshold == "v6.26.0"
]
check(
    "SELF-NO-OWN-SOURCE-CONTRIBUTION. v6.26.0自身はsrc本番コードへの新規寄与を"
    "宣言していない（v6.26.0が直接登録したrecordの件数のみを検査する、将来Releaseの"
    "寄与とは独立に安定した不変条件。allowed_source_changes_for()の合成結果ではなく"
    "_SOURCE_CHANGE_CONTRIBUTIONSの生recordを直接検査する）",
    _v6_26_own_source_contributions, [],
)

# v6.27.0修正（DI-9対応。Major修正）: 元実装（SELF-SRC-ZERO-DIFF）は
# baseline commitからの実差分が「無条件に空である」ことを固定しており、
# 将来Releaseが共有レジストリ経由で正当にprotected pathへ寄与した時点で
# 恒久的にFAILする欠陥があった（v6.21.0〜v6.24.0のNOIMPACT-SCOPEが
# allow-listベースであるのに対し、SELFセクションのみallow-listを経由しない
# 無条件チェックだったという非対称な設計だった）。
#
# 修正方針：「baselineから一切変わっていない」ではなく「baselineとの差分が
# 共有レジストリで承認されたsource contributionの範囲を超えていない」という、
# v6.21.0〜v6.24.0のNOIMPACT-SCOPEと同一のallow-list意味論へ揃える
# （SELF-SRC-SCOPE）。v6.26.0自身は直接のsource contributionを持たない
# （SELF-NO-OWN-SOURCE-CONTRIBUTIONで別途確認済み）ため、
# `allowed_source_changes_for("v6.26.0")`が返す許容範囲は、もっぱら
# v6.27.0以降の将来Releaseが登録した寄与のみで構成される。無承認の
# production差分（＝どのReleaseもcontributionとして登録していない変更）は、
# 引き続き`_changed - _allowed`が非空になるため検知される
# （検知力は維持。historical BASELINE_COMMITS・window semanticsは無改修）。
_self_allowed_source = registry.allowed_source_changes_for("v6.26.0")
for _rel in registry.PROTECTED_PATHS:
    _diff_proc = subprocess.run(
        ["git", "diff", "--name-only", "--relative", BASELINE_COMMIT, "--", _rel],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
    )
    _changed = {line.strip() for line in _diff_proc.stdout.splitlines() if line.strip()}
    _allowed_for_rel = _self_allowed_source.get(_rel, frozenset())
    check(
        f"SELF-SRC-SCOPE[{_rel}]. baseline commitからの差分が共有レジストリで承認された"
        "source contributionの範囲内である（無承認の変更は引き続き検知する。"
        "v6.26.0自身は直接のcontributionを持たないため、実質的にv6.27.0以降が"
        "登録した寄与のみが許容される）",
        sorted(_changed - _allowed_for_rel), [],
    )
    _status_proc = subprocess.run(
        ["git", "status", "--porcelain", "--untracked-files=all", "--", _rel],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
    )
    check(f"SELF-SRC-NO-UNTRACKED[{_rel}]. untracked集合が空である",
          [line for line in _status_proc.stdout.splitlines() if line.startswith("??")], [])

_self_allowed_test = registry.allowed_test_changes_for("v6.26.0")
_tests_diff_proc = subprocess.run(
    ["git", "diff", "--name-only", BASELINE_COMMIT, "--", "tests"],
    cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
)
_changed_tests = {
    Path(line.strip().replace("\\", "/")).name
    for line in _tests_diff_proc.stdout.splitlines() if line.strip()
}
check("SELF-TESTS-SCOPE. tests/の差分がv6.26.0自身のallow-listの範囲内である",
      sorted(_changed_tests - _self_allowed_test), [])

_tests_status_proc = subprocess.run(
    ["git", "status", "--porcelain", "--untracked-files=all", "--", "tests"],
    cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
)
_untracked_tests = {
    Path(line[3:]).name for line in _tests_status_proc.stdout.splitlines()
    if line.startswith("??")
}
check("SELF-TESTS-NO-UNTRACKED. tests/のuntracked集合がv6.26.0自身のallow-listの範囲内である",
      sorted(_untracked_tests - _self_allowed_test), [])
print()

# =====================================================================
# CONTRACT: 現在の22 protected pathsがv6.21.0〜v6.24.0の各baseline commit
# 時点ですべて追跡されている（Architecture/Code Review Major-2対応）。
# 新規path追加は本Registry FoundationのO(1)自動追従の対象外であり
# （設計書§3.4）、historical guard側への例外処理・除外listは導入しない。
# 本契約がFAILすることは「PROTECTED_PATHSへ新規pathが追加され、
# historical guardとの整合が壊れた」ことを意味の分かる形で示す。
# =====================================================================

print("[CONTRACT] protected pathsが各historical baseline commit時点で追跡されている")

for _rel in ("v6.21.0", "v6.22.0", "v6.23.0", "v6.24.0"):
    _baseline = registry.BASELINE_COMMITS[_rel]
    for _path in registry.PROTECTED_PATHS:
        _ls_proc = subprocess.run(
            ["git", "ls-tree", "-r", "--name-only", _baseline, "--", _path],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
        )
        check_true(
            f"CONTRACT-PATH-TRACKED-AT-BASELINE[{_rel}/{_path}]. protected pathが{_rel}の"
            "baseline commit時点で追跡されている（新規path追加時はこのassertionがFAILし、"
            "原因が明示される。PROTECTED_PATHS直前のコメント・設計書§3.4参照）",
            _ls_proc.returncode == 0 and bool(_ls_proc.stdout.strip()),
        )
print()

# =====================================================================
# FAILCLOSED: 未知・不正なrelease文字列に対しfail-closedである
# （Architecture/Code Review Suggestion対応）
# =====================================================================

print("[FAILCLOSED] 未知・不正なrelease文字列に対しfail-closedである")

_INVALID_RELEASES = ("v9.99.0", "V6.21.0", "v6.21", " v6.21.0", "")

for _bad in _INVALID_RELEASES:
    for _fn_name, _fn in (
        ("release_index", registry.release_index),
        ("allowed_source_changes_for", registry.allowed_source_changes_for),
        ("allowed_test_changes_for", registry.allowed_test_changes_for),
    ):
        try:
            _fn(_bad)
            _raised = False
        except ValueError:
            _raised = True
        except Exception:
            _raised = False
        check_true(
            f"FAILCLOSED-RAISES[{_fn_name}({_bad!r})]. 不正なrelease文字列に対しValueErrorを"
            "送出する（サイレントに空／誤った結果を返さない）",
            _raised,
        )
print()

# =====================================================================
# HERMETIC: 共有レジストリがネットワーク関連importを持たない
# =====================================================================

print("[HERMETIC] 共有レジストリがネットワーク関連importを持たない")

_registry_source = (TESTS_DIR / "zero_diff_guard_registry.py").read_text(encoding="utf-8")
_registry_tree = ast.parse(_registry_source, filename="zero_diff_guard_registry.py")
_imported_names = set()
for _node in ast.walk(_registry_tree):
    if isinstance(_node, ast.Import):
        for _alias in _node.names:
            _imported_names.add(_alias.name.split(".")[0])
    elif isinstance(_node, ast.ImportFrom) and _node.module:
        _imported_names.add(_node.module.split(".")[0])
check(
    "HERMETIC-NO-NETWORK-IMPORTS. requests／socket／openai等のネットワーク関連importが存在しない",
    sorted(_imported_names & {"requests", "socket", "openai", "urllib", "http"}),
    [],
)
print()

# ─── 結果サマリー ───
print("=" * 70)
total = len(results_log)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = total - passed
print("Release：v6.26.0")
print("正式名称：Zero-Diff Guard Registry Foundation")
print(f"合計: {passed}/{total} PASS  /  {failed} FAIL")
print("=" * 70)

if failed:
    print()
    print("FAILしたテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")

sys.exit(0 if failed == 0 else 1)
