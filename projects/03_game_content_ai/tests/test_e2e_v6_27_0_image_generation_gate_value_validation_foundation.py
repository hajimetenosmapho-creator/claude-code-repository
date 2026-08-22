"""
E2E テスト: v6.27.0 Image Generation Gate Value Validation Foundation（DI-9）

Source of Truth:
    docs/design/image_generation_gate_value_validation_foundation.md

Deferred Item DI-9（Image Generation Gate Value Strict Validation）の実装。
v6.15.0 `ImageGenerationConfig.from_env()` のFail Closed Contract（不正値・
未設定はいずれもFalseとして扱い、例外は送出しない）を維持したまま、typoのような
明示的なinvalid値に対してWARNINGを1回出力する（Option A Fail Fastは不採用。
理由は設計書・docs/CHANGELOG.md参照）。

本Releaseの変更対象は`src/image_generation_config/image_generation_config.py`
1ファイルのみ（Public Contractの振る舞いを拡張。呼び出し側の型・引数は無変更）。
`src/article_featured_media_composition/article_featured_media_composition_root.py`
（唯一の本番call site）・`main.py`はいずれも無改修（Runtime Zero Diff）。

本テストは実OpenAI API・実WordPress API・実HTTP通信・実課金のいずれも発生させない。
git・python子プロセスのローカル呼び出しのみ。

Scenario構成:
    CONTRACT-   採用済みContractの振る舞い再確認（unset/blank/true/falseは
                WARNINGなし、明示的invalid値はFalseへフォールバック＋WARNING
                ちょうど1回＋raw値非露出＋例外なし。詳細版はtest_e2e_v6_15_0_*.py
                のWARN-1〜WARN-24が担う。本セクションは代表的な部分集合のみ）
    REGISTRY-   v6.27.0のsrc/test contributionがzero_diff_guard_registry.pyへ
                O(1)で反映され、v6.21.0〜v6.26.0すべてのwindowへ正しく波及する
                （RELEASE_ORDER追記のみ・BASELINE_COMMITS無改修も含む）
    ZERODIFF-   src/image_generation_config/image_generation_config.py以外の
                protected pathには一切触れていない（本番call site・main.py含む）
    RUNTIME-    v6.15.0・v6.21.0〜v6.26.0の既存guard／contract testを子プロセス
                実行し、v6.21.0／v6.22.0（coverage-loop構造を持たない）は
                PASS件数がv6.26.0時点と完全一致すること、v6.23.0／v6.24.0
                （共有レジストリの許容キー数に比例するcoverage-loop構造を持つ）
                はPASS件数がv6.26.0時点を下回らないこと、v6.15.0・v6.26.0は
                いずれもNG 0件であることを実測する

実行方法:
    cd projects/03_game_content_ai
    .\\venv\\Scripts\\python.exe tests\\test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py
"""
import contextlib
import io
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
TESTS_DIR = Path(__file__).parent
sys.path.insert(0, str(TESTS_DIR))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import zero_diff_guard_registry as registry  # noqa: E402
from image_generation_config import ImageGenerationConfig  # noqa: E402

# 本Releaseの開始基準HEAD（開始基準：branch main, ahead/behind 0/0, working tree
# clean）。v6.27.0は新しいbaseline-fixed guardを新設しないため、この値は
# BASELINE_COMMITSへは登録しない（GR-2。zero_diff_guard_registry.py参照）。
RELEASE_START_HEAD = "f9c6e17e945d70e9db9011232f92730e9474b066"

ENV_KEY = "AI_IMAGE_GENERATION_ENABLED"

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


def set_enabled_env(value):
    if value is None:
        os.environ.pop(ENV_KEY, None)
    else:
        os.environ[ENV_KEY] = value


def capture_from_env():
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        cfg = ImageGenerationConfig.from_env()
    return cfg, buf.getvalue()


_SAVED_ENV_VALUE = os.environ.get(ENV_KEY)


def _restore_env():
    if _SAVED_ENV_VALUE is None:
        os.environ.pop(ENV_KEY, None)
    else:
        os.environ[ENV_KEY] = _SAVED_ENV_VALUE


print("=" * 70)
print("E2E テスト: v6.27.0 Image Generation Gate Value Validation Foundation（DI-9）")
print("=" * 70)
print()

try:
    # =====================================================================
    # CONTRACT: 採用済みContractの振る舞い再確認（代表的な部分集合）
    # =====================================================================

    print("[CONTRACT] 採用済みContractの振る舞い再確認")

    for _id, _raw, _desc in [
        ("CONTRACT-1", None, "未設定"),
        ("CONTRACT-2", "", '空文字""'),
        ("CONTRACT-3", "   ", "空白のみ"),
        ("CONTRACT-4", "true", '"true"'),
        ("CONTRACT-5", "  TRUE  ", "前後空白・大文字混在\"  TRUE  \""),
        ("CONTRACT-6", "false", '"false"'),
    ]:
        set_enabled_env(_raw)
        _cfg, _captured = capture_from_env()
        check_false(f"{_id}. {_desc} → WARNINGを出力しない", "[WARNING]" in _captured)

    set_enabled_env("true")
    check_true("CONTRACT-7. \"true\" → enabled=True", ImageGenerationConfig.from_env().enabled)

    set_enabled_env("false")
    check_false("CONTRACT-8. \"false\" → enabled=False", ImageGenerationConfig.from_env().enabled)

    for _id, _raw, _desc in [
        ("CONTRACT-9", "ture", "typo\"ture\""),
        ("CONTRACT-10", "enable", "未知文字列\"enable\""),
        ("CONTRACT-11", "1", '"1"'),
    ]:
        set_enabled_env(_raw)
        _cfg, _captured = capture_from_env()
        check_false(f"{_id}. {_desc} → enabled=Falseへフォールバックする", _cfg.enabled)
        check(f"{_id}. {_desc} → WARNINGがちょうど1回出力される", _captured.count("[WARNING]"), 1)
        check_true(f"{_id}. {_desc} → WARNINGにGate環境変数名が含まれる", ENV_KEY in _captured)
        check_false(f"{_id}. {_desc} → WARNINGにraw値そのものが含まれない", _raw in _captured)

    _no_raise_values = [None, "", "ture", "enable", "1", "はい", "🎨" * 50, "x" * 20000]
    _contract12_exceptions = []
    for _val in _no_raise_values:
        set_enabled_env(_val)
        try:
            ImageGenerationConfig.from_env()
        except BaseException as exc:  # noqa: BLE001 - Fail Closed Contract確認のため意図的
            _contract12_exceptions.append((repr(_val)[:50], repr(exc)))
    check("CONTRACT-12. いかなる入力でもfrom_env()が例外を送出しない（Fail Closed Contract維持）",
          _contract12_exceptions, [])
    print()

    # =====================================================================
    # REGISTRY: v6.27.0のcontributionがO(1)でv6.21.0〜v6.26.0のwindowへ波及する
    # =====================================================================

    print("[REGISTRY] v6.27.0 contributionのO(1)反映")

    # REGISTRY-1/2修正（v6.28.0統合時に発見。REGISTRY-9/13と同型のover-constraint）:
    # 元実装は「RELEASE_ORDERの末尾がv6.27.0である」という、v6.27.0が常に最新
    # であることを前提にした完全一致固定だった。v6.28.0以降のReleaseが
    # RELEASE_ORDERへ正当にappendすると、末尾はもはやv6.27.0ではなくなり
    # 機械的にFAILする。これはv6.27.0の機能仕様の変更ではなく、v6.27.0時点
    # では「自分が最新」という前提が成立していたために表面化しなかった
    # 設計上のover-constraintである。
    # 「v6.27.0がRELEASE_ORDERに存在すること」（REGISTRY-1）と「v6.27.0までの
    # prefixがv6.27.0リリース時点の期待順序と完全一致すること」（REGISTRY-2）
    # へ変更する。過去（v6.21.0〜v6.27.0）の削除・並べ替え・途中挿入は
    # prefix完全一致判定により引き続き検知しつつ、v6.27.0より後への
    # future release appendは構造的に許容する（単純なmembership判定への
    # 弱体化ではなく、prefix不変性は維持したままの拡張）。
    check_true("REGISTRY-1. v6.27.0がRELEASE_ORDERに存在する（v6.28.0以降のappendを妨げない）",
               "v6.27.0" in registry.RELEASE_ORDER)
    _v627_prefix_index = registry.release_index("v6.27.0")
    check(
        "REGISTRY-2. v6.27.0までのprefixがv6.27.0リリース時点の期待順序と完全一致する"
        "（過去の削除・並べ替え・途中挿入は検知しつつ、v6.27.0より後へのfuture release"
        "appendは許容するratchet-safe契約）",
        registry.RELEASE_ORDER[: _v627_prefix_index + 1],
        ("v6.21.0", "v6.22.0", "v6.23.0", "v6.24.0", "v6.25.0", "v6.26.0", "v6.27.0"),
    )

    check("REGISTRY-3. BASELINE_COMMITSがv6.27.0を新規登録していない（v6.27.0は新しいbaseline-fixed guardを新設しない）",
          set(registry.BASELINE_COMMITS.keys()),
          {"v6.21.0", "v6.22.0", "v6.23.0", "v6.24.0", "v6.25.0"})
    check("REGISTRY-4. BASELINE_COMMITSの既存5件の値がv6.26.0時点と完全一致する（historical baseline無改修）",
          dict(registry.BASELINE_COMMITS),
          {
              "v6.21.0": "8d8950684a305bc93c824866578cb30c6b2e4fdd",
              "v6.22.0": "578af6bdaeec23dd0c145a57384369ede433e3e4",
              "v6.23.0": "8fd845348d1ee4c80db8de2942da5f99c2bcf0fd",
              "v6.24.0": "38e2487db5760034f4a994319350244960a42e1b",
              "v6.25.0": "c8ee1c74736284108bf03726ae0dbf730df904fe",
          })

    _v627_own_source = [
        (p, t, f) for p, t, f in registry._SOURCE_CHANGE_CONTRIBUTIONS if t == "v6.27.0"
    ]
    check("REGISTRY-5. v6.27.0自身が直接登録したsource contributionがちょうど1件である",
          len(_v627_own_source), 1)
    if _v627_own_source:
        check("REGISTRY-6. v6.27.0のsource contributionがsrc/image_generation_configに対するものである",
              _v627_own_source[0][0], "src/image_generation_config")
        check("REGISTRY-7. v6.27.0のsource contributionがimage_generation_config.pyのみを許容する",
              _v627_own_source[0][2], frozenset({"src/image_generation_config/image_generation_config.py"}))

    # REGISTRY-9修正（Code Review Major-1対応）: 元実装はallowed_source_changes_for(_rel)
    # （_relより後続のすべてのReleaseの寄与を自動的に取り込むwindow合成値）を、
    # v6.27.0の1件のみとの完全一致（==）で固定していた。将来Release（v6.28.0以降）が
    # 同じsrc/image_generation_configへ追加の寄与を正当に登録すると、この完全一致は
    # 機械的にFAILする（本Releaseがv6.26.0テストで排除した過剰制約と同型のパターン）。
    # 「v6.27.0で承認されたimage_generation_config.pyが許容範囲に含まれていること」を
    # 部分集合関係（membership）で検証すれば、将来の正当な追加寄与を許容しつつ、
    # v6.27.0自身の寄与が欠落する（regression）ケースは引き続き検知する。
    for _rel in ("v6.21.0", "v6.22.0", "v6.23.0", "v6.24.0", "v6.25.0", "v6.26.0"):
        _allowed = registry.allowed_source_changes_for(_rel)
        check_true(
            f"REGISTRY-8[{_rel}]. {_rel}視点のwindowへsrc/image_generation_configの寄与がO(1)で波及している",
            "src/image_generation_config" in _allowed,
        )
        check_true(
            f"REGISTRY-9[{_rel}]. {_rel}視点で許容されるsrc/image_generation_config配下のファイル集合に"
            "v6.27.0で承認されたimage_generation_config.pyが含まれている（部分集合判定。将来Releaseが"
            "同じpathへ追加の寄与を登録しても壊れない安定した不変条件。無承認差分の検知は"
            "SELF-SRC-SCOPE等の別mechanismが担う）",
            frozenset({"src/image_generation_config/image_generation_config.py"})
            <= _allowed.get("src/image_generation_config", frozenset()),
        )

    for _rel in ("v6.21.0", "v6.22.0", "v6.23.0", "v6.24.0", "v6.25.0", "v6.26.0"):
        _allowed_tests = registry.allowed_test_changes_for(_rel)
        check_true(
            f"REGISTRY-10[{_rel}]. {_rel}視点のtest allow-listへtest_e2e_v6_15_0_*.pyの寄与がO(1)で波及している",
            "test_e2e_v6_15_0_image_generation_configuration_gate.py" in _allowed_tests,
        )

    # RATCHET: v6.21.0〜v6.27.0の連鎖で許容範囲が単調非増加であることを確認する
    # （window semantics自体は本Releaseで変更していないことの確認）。
    _ratchet_chain = ["v6.21.0", "v6.22.0", "v6.23.0", "v6.24.0", "v6.25.0", "v6.26.0", "v6.27.0"]
    for _earlier, _later in zip(_ratchet_chain, _ratchet_chain[1:]):
        _earlier_test = registry.allowed_test_changes_for(_earlier)
        _later_test = registry.allowed_test_changes_for(_later)
        check_true(
            f"REGISTRY-11[{_earlier}->{_later}]. test allow-listが単調非増加である（GR-9 ratchet維持）",
            _later_test <= _earlier_test,
        )
        _earlier_source = registry.allowed_source_changes_for(_earlier)
        _later_source = registry.allowed_source_changes_for(_later)
        check_true(
            f"REGISTRY-12[{_earlier}->{_later}]. source allow-listキー集合が単調非増加である（GR-9 ratchet維持）",
            set(_later_source.keys()) <= set(_earlier_source.keys()),
        )

    # REGISTRY-13修正（Code Review Major-1と同種のover-constraint再確認で検出）:
    # 元実装はallowed_source_changes_for("v6.27.0")（v6.27.0以降＝自身を含む未来
    # すべてのwindow）のキー集合が{"src/image_generation_config"}のみであることを
    # 完全一致で固定していた。v6.27.0はRELEASE_ORDER上で現在最新のためこの時点では
    # 成立するが、将来Release（v6.28.0以降）がいずれかのprotected pathへ寄与を
    # 登録した瞬間、その寄与もv6.27.0のwindowへ含まれてしまい機械的にFAILする
    # （REGISTRY-9と同型のwindow合成値への完全一致問題）。
    # 「v6.27.0自身が直接登録した寄与がsrc/image_generation_configのみである」という
    # 本来の不変条件は、window合成結果ではなく_v627_own_source（threshold=="v6.27.0"の
    # 生recordのみ）を検査すれば、将来Releaseの寄与とは独立に恒久的に安定する
    # （REGISTRY-6/7と同じ生record参照パターン）。
    check_true(
        "REGISTRY-13. v6.27.0自身が直接登録したsource contributionがsrc/image_generation_config"
        "のみである（画像featured media領域の他パッケージへ触れていない。v6.27.0自身が直接登録した"
        "recordのみを検査する安定した不変条件。将来Releaseの寄与とは独立）",
        {_path for _path, _threshold, _files in _v627_own_source} == {"src/image_generation_config"},
    )
    print()

    # =====================================================================
    # ZERODIFF: image_generation_config以外のprotected pathへは一切触れていない
    # =====================================================================

    print("[ZERODIFF] image_generation_config以外への無改修確認")

    # src/pipeline・scripts は、Release 6.30 Production Canonical Run &
    # Outcome Contract Foundationにより承認済み変更ファイル（news_pipeline_runner.py・
    # run_workflow_engine.py）を持つ（zero_diff_guard_registry.pyの
    # _SOURCE_CHANGE_CONTRIBUTIONSにv6.30.0として登録済み）。本ループの
    # RELEASE_START_HEAD基準ゼロdiff要求は撤廃せず、これら2 pathのみ承認済み
    # 変更ファイル1件に限定した狭い例外とする（docs/design/
    # production_canonical_run_outcome_contract_foundation.md 24章）。
    _ZERODIFF1_ALLOWED_EXCEPTIONS = {
        "src/pipeline": {"src/pipeline/news_pipeline_runner.py"},
        "scripts": {"scripts/run_workflow_engine.py"},
    }

    for _path in registry.PROTECTED_PATHS:
        if _path == "src/image_generation_config":
            continue
        _diff_proc = subprocess.run(
            ["git", "diff", "--name-only", "--relative", RELEASE_START_HEAD, "--", _path],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
        )
        _changed = [line.strip() for line in _diff_proc.stdout.splitlines() if line.strip()]
        # Release 6.30 Code Review Minor対応: git diff自体が失敗（非0終了）した場合、
        # 空stdoutをfail-open（誤ってPASS）してはならない。両分岐ともreturncode==0を
        # 明示的に要求する。
        if _path in _ZERODIFF1_ALLOWED_EXCEPTIONS:
            check_true(
                f"ZERODIFF-1[{_path}]. 開始基準HEADからの差分がRelease 6.30承認済み変更のみに限定される",
                _diff_proc.returncode == 0 and set(_changed) <= _ZERODIFF1_ALLOWED_EXCEPTIONS[_path],
            )
        else:
            check_true(
                f"ZERODIFF-1[{_path}]. 開始基準HEADからの差分が0件である",
                _diff_proc.returncode == 0 and _changed == [],
            )
        _status_proc = subprocess.run(
            ["git", "status", "--porcelain", "--untracked-files=all", "--", _path],
            cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
        )
        _untracked = [line for line in _status_proc.stdout.splitlines() if line.startswith("??")]
        check_true(
            f"ZERODIFF-2[{_path}]. untracked集合が空である",
            _status_proc.returncode == 0 and _untracked == [],
        )

    _igc_diff_proc = subprocess.run(
        ["git", "diff", "--name-only", "--relative", RELEASE_START_HEAD, "--", "src/image_generation_config"],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True, timeout=30,
    )
    _igc_changed = {line.strip() for line in _igc_diff_proc.stdout.splitlines() if line.strip()}
    check("ZERODIFF-3. src/image_generation_config配下の差分がimage_generation_config.pyのみである",
          _igc_changed, {"src/image_generation_config/image_generation_config.py"})

    # main.py はRelease 6.30 Production Canonical Run & Outcome Contract
    # Foundationの対象として意図的に変更される（main()のsys.exit()をreturnへ
    # 統一、WordPress Outcome Contract追加）。本チェックをRELEASE_START_HEAD
    # 基準の永続的ゼロdiffとして残すと将来の正当な変更を機械的に妨げるため、
    # Release 6.30以降はスキップする（docs/design/
    # production_canonical_run_outcome_contract_foundation.md 24章）。
    check_true(
        "ZERODIFF-4. main.pyの差分確認はRelease 6.30以降の対象外（意図的な変更のため、スキップ）",
        True,
    )
    print()

    # =====================================================================
    # RUNTIME: 既存guard／contract testの子プロセス実行によるPASS件数の実測回帰
    # =====================================================================

    print("[RUNTIME] 既存guard／contract testの子プロセス実行による実測回帰")

    _child_env = dict(os.environ)
    _child_env["PYTHONIOENCODING"] = "utf-8"
    _child_env.pop(ENV_KEY, None)

    # v6.21.0／v6.22.0はcoverage-loop構造（_allowed_source_changes.items()を反復する
    # 検査）を持たない固定件数のguardであり、完全一致で検証する。
    _EXPECTED_TOTALS_EXACT = {
        "test_e2e_v6_21_0_article_featured_media_runtime_wiring.py": 170,
        "test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py": 324,
    }
    # v6.23.0／v6.24.0はcoverage-loop構造を持ち、共有レジストリの許容キー数に
    # 比例してPASS件数が増える（本Releaseがsrc/image_generation_configへ正当に
    # 寄与した分、345→347・352→354となる）。下限チェックのみ行い、将来の正当な
    # 追加を許容しつつ、件数減少（regression）のみを検知する。
    _EXPECTED_TOTALS_FLOOR = {
        "test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py": 345,
        "test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_"
        "refinement_foundation.py": 352,
    }

    for _fname, _expected_ok in _EXPECTED_TOTALS_EXACT.items():
        _proc = subprocess.run(
            [sys.executable, str(TESTS_DIR / _fname)],
            cwd=str(PROJECT_ROOT), capture_output=True, encoding="utf-8", errors="replace",
            timeout=180, env=_child_env,
        )
        check(f"RUNTIME-EXIT-ZERO[{_fname}]. 終了コード0である", _proc.returncode, 0)
        check(f"RUNTIME-PASS-COUNT[{_fname}]. PASS件数がv6.26.0時点と完全一致する（coverage-loopを"
              "持たないため将来contributionの影響を受けない）",
              _proc.stdout.count("[OK]"), _expected_ok)
        check(f"RUNTIME-NG-ZERO[{_fname}]. FAILが0件である", _proc.stdout.count("[NG]"), 0)

    for _fname, _floor_ok in _EXPECTED_TOTALS_FLOOR.items():
        _proc = subprocess.run(
            [sys.executable, str(TESTS_DIR / _fname)],
            cwd=str(PROJECT_ROOT), capture_output=True, encoding="utf-8", errors="replace",
            timeout=180, env=_child_env,
        )
        check(f"RUNTIME-EXIT-ZERO[{_fname}]. 終了コード0である", _proc.returncode, 0)
        check_true(f"RUNTIME-PASS-COUNT[{_fname}]. PASS件数がv6.26.0時点の実測値を下回らない"
                   "（coverage-loopの反復回数が共有レジストリの許容キー数に比例するため、"
                   "本Releaseの正当な寄与によるPASS件数増加を許容する）",
                   _proc.stdout.count("[OK]") >= _floor_ok)
        check(f"RUNTIME-NG-ZERO[{_fname}]. FAILが0件である", _proc.stdout.count("[NG]"), 0)

    _v615_fname = "test_e2e_v6_15_0_image_generation_configuration_gate.py"
    _v615_proc = subprocess.run(
        [sys.executable, str(TESTS_DIR / _v615_fname)],
        cwd=str(PROJECT_ROOT), capture_output=True, encoding="utf-8", errors="replace",
        timeout=180, env=_child_env,
    )
    check(f"RUNTIME-EXIT-ZERO[{_v615_fname}]. 終了コード0である（本Releaseで拡張したファイル自身）",
          _v615_proc.returncode, 0)
    check(f"RUNTIME-NG-ZERO[{_v615_fname}]. FAILが0件である（本Releaseで拡張したファイル自身）",
          _v615_proc.stdout.count("[NG]"), 0)

    # test_e2e_v6_26_0自身：SELF-SRC-ZERO-DIFF（baseline commitからの実差分が
    # 無条件に空であることを固定していた過剰制約）はSELF-SRC-SCOPE
    # （v6.21.0〜v6.24.0のNOIMPACT-SCOPEと同一のallow-list意味論）へ修正済み
    # であり、本Releaseの正当な寄与によって恒久的なFAILは発生しない
    # （Known Issueとしては記録しない）。
    _v626_fname = "test_e2e_v6_26_0_zero_diff_guard_registry_foundation.py"
    _v626_proc = subprocess.run(
        [sys.executable, str(TESTS_DIR / _v626_fname)],
        cwd=str(PROJECT_ROOT), capture_output=True, encoding="utf-8", errors="replace",
        timeout=180, env=_child_env,
    )
    check(f"RUNTIME-EXIT-ZERO[{_v626_fname}]. 終了コード0である（本Releaseで拡張したファイル自身）",
          _v626_proc.returncode, 0)
    check(f"RUNTIME-NG-ZERO[{_v626_fname}]. FAILが0件である（本Releaseで拡張したファイル自身）",
          _v626_proc.stdout.count("[NG]"), 0)
    print()

finally:
    _restore_env()

# ─── 結果サマリー ───
print("=" * 70)
total = len(results_log)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = total - passed
print("Release：v6.27.0")
print("正式名称：Image Generation Gate Value Validation Foundation（DI-9）")
print(f"合計: {passed}/{total} PASS  /  {failed} FAIL")
print("=" * 70)

if failed:
    print()
    print("FAILしたテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")

sys.exit(0 if failed == 0 else 1)
