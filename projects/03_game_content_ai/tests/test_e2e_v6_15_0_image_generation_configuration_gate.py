"""
E2E テスト: v6.15.0 Image Generation Configuration Gate Foundation

Source of Truth:
    docs/design/image_generation_configuration_gate_foundation.md
    （Architecture Review：Approved、Critical/Major/Minor/Suggestion いずれも0件、
      Blocking Issueなし）

本テストは実OpenAI API・実WordPress API・実HTTP通信・実課金のいずれも発生させない。
image_generation_configはConsumer-less Foundationであり、Production Runtime
（main.py以下13対象）のいずれからも未接続であることをAST解析で検証する。

Scenario構成（54 Scenario）:
    CFG-1〜CFG-20（Configuration Contract：environment variable値ごとのparsing結果）
    API-1〜API-6（Public API：import surface・__all__・field形状）
    IMM-1〜IMM-3（Immutability：frozen・state非共有）
    DEP-1〜DEP-14（Dependency Guard：21章R-1〜R-13・R-OUT-1のAST Guard）
    RTZ-1〜RTZ-3（Runtime Zero Diff：API非呼び出し・副作用なし）
    SEC-1〜SEC-5（Security：secret非保持・非露出）
    ENV-1〜ENV-3（.env.example：Gate変数の記載・default OFF・secret非露出）

実行方法:
    cd projects/03_game_content_ai
    python tests/test_e2e_v6_15_0_image_generation_configuration_gate.py
"""
import ast
import os
import re
import sys
from dataclasses import FrozenInstanceError, fields
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ─── テスト用ユーティリティ（v6.9.0〜v6.14.0 precedentを踏襲） ───

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
    check(label, value, True)


def check_false(label: str, value: bool):
    check(label, value, False)


def check_contains(label: str, text, keyword: str):
    check(label, keyword in str(text), True)


def check_not_contains(label: str, text, keyword: str):
    check(label, keyword in str(text), False)


def invoke(func):
    """funcを呼び出し、(戻り値, 例外)のタプルを返す。例外がなければ(結果, None)。"""
    try:
        return func(), None
    except BaseException as exc:
        return None, exc


# ─── AST解析ユーティリティ（v6.9.0〜v6.14.0 precedentを踏襲） ───


def get_import_details(file_path: Path) -> dict:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    absolute_roots = set()
    relative_imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                absolute_roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level and node.level > 0:
                relative_imports.append({"level": node.level, "module": node.module})
            elif node.module:
                absolute_roots.add(node.module.split(".")[0])
    return {"absolute_roots": absolute_roots, "relative_imports": relative_imports}


def get_call_lines(file_path: Path, func_name: str) -> list:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    lines = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == func_name
        ):
            lines.append(node.lineno)
    return lines


def get_raise_lines(file_path: Path) -> list:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    return [node.lineno for node in ast.walk(tree) if isinstance(node, ast.Raise)]


def file_references_name(file_path: Path, name: str) -> bool:
    """file_pathのソーステキストにnameという文字列が含まれるかどうかを返す
    （Production Runtime未接続Guard：importに限らずコメント等も含めた参照非存在の確認）。"""
    return name in file_path.read_text(encoding="utf-8")


ENV_KEY = "AI_IMAGE_GENERATION_ENABLED"


def set_enabled_env(value):
    """value=Noneなら環境変数を未設定にする。それ以外はその文字列を設定する。"""
    if value is None:
        os.environ.pop(ENV_KEY, None)
    else:
        os.environ[ENV_KEY] = value


print("=" * 60)
print("v6.15.0 Image Generation Configuration Gate Foundation E2E テスト")
print("Release：v6.15.0")
print("正式名称：Image Generation Configuration Gate")
print("Scenario：54")
print("=" * 60)
print()

# Environment隔離：テスト開始前の状態を保存し、finallyで完全に復元する。
# 本E2Eが実際に書き換えるのはAI_IMAGE_GENERATION_ENABLEDのみ（OPENAI_API_KEY・
# OPENAI_IMAGE_TIMEOUT_SECONDSはSEC-1／ENV-3等で.env.exampleやsourceの静的
# テキストとして参照するのみで、os.environへは一切書き込まないため対象外とする）。
_SAVED_ENV_VALUE = os.environ.get(ENV_KEY)


def _restore_env():
    if _SAVED_ENV_VALUE is None:
        os.environ.pop(ENV_KEY, None)
    else:
        os.environ[ENV_KEY] = _SAVED_ENV_VALUE


try:
    from image_generation_config import ImageGenerationConfig

    IGC_DIR = PROJECT_ROOT / "src" / "image_generation_config"
    IGC_FILES = {
        "__init__": IGC_DIR / "__init__.py",
        "image_generation_config": IGC_DIR / "image_generation_config.py",
    }

    # =====================================================================
    # CFG: Configuration Contract（20 Scenario）
    # =====================================================================

    print("[CFG] Configuration Contract")

    _CFG_CASES = [
        ("CFG-1", None, False, "未設定時"),
        ("CFG-2", "", False, '空文字""'),
        ("CFG-3", "   ", False, "空白のみ"),
        ("CFG-4", "true", True, '"true"'),
        ("CFG-5", "TRUE", True, '"TRUE"'),
        ("CFG-6", "True", True, '"True"'),
        ("CFG-7", "  true  ", True, "前後空白付き\"  true  \""),
        ("CFG-8", "false", False, '"false"'),
        ("CFG-9", "FALSE", False, '"FALSE"'),
        ("CFG-10", "1", False, '"1"'),
        ("CFG-11", "0", False, '"0"'),
        ("CFG-12", "yes", False, '"yes"'),
        ("CFG-13", "no", False, '"no"'),
        ("CFG-14", "on", False, '"on"'),
        ("CFG-15", "off", False, '"off"'),
        ("CFG-16", "enable", False, "未知文字列\"enable\""),
        ("CFG-17", "はい", False, "非ASCII文字列\"はい\""),
    ]
    for _id, _raw, _expected, _desc in _CFG_CASES:
        set_enabled_env(_raw)
        _cfg = ImageGenerationConfig.from_env()
        check(f"{_id}. {_desc} → enabled={_expected}", _cfg.enabled, _expected)

    # CFG-18: from_env()複数回呼び出しで独立したインスタンスを返す
    set_enabled_env("true")
    _cfg_a = ImageGenerationConfig.from_env()
    _cfg_b = ImageGenerationConfig.from_env()
    check_true("CFG-18. from_env()を2回呼び出すと別々のインスタンスを返す（is比較）", _cfg_a is not _cfg_b)
    check("CFG-18. 2つのインスタンスのenabled値が一致する", _cfg_a.enabled, _cfg_b.enabled)

    # CFG-19: environment変更後の再読み込みで新しい値を反映する（都度読み込み）
    set_enabled_env("true")
    _cfg_before = ImageGenerationConfig.from_env()
    set_enabled_env("false")
    _cfg_after = ImageGenerationConfig.from_env()
    check_true("CFG-19. environment変更前はenabled=True", _cfg_before.enabled)
    check_false("CFG-19. environment変更後の再読み込みでenabled=Falseに更新される（都度読み込み）", _cfg_after.enabled)

    # CFG-20: いかなる入力でも例外を送出しない（Fail Closed Contract確認）
    # 注: Windowsの環境変数は32767文字までという制約があるため、それより
    # 十分小さい20000文字を「非常に長い文字列」として使用する。
    _long_string = "x" * 20000
    _exception_test_values = [
        None, "", "   ", "true", "TRUE", "false", "1", "0", "yes", "no", "on", "off",
        "enable", "はい", _long_string, "\t\n", "null", "None", "NULL", "🎨" * 50,
    ]
    _cfg20_exceptions = []
    for _val in _exception_test_values:
        set_enabled_env(_val)
        _result, _exc = invoke(ImageGenerationConfig.from_env)
        if _exc is not None:
            _cfg20_exceptions.append((repr(_val)[:50], repr(_exc)))
    check("CFG-20. いかなる入力でもfrom_env()が例外を送出しない（Fail Closed Contract確認）", _cfg20_exceptions, [])
    print()

    # =====================================================================
    # API: Public API（6 Scenario）
    # =====================================================================

    print("[API] Public API")

    import image_generation_config as _igc_module

    check_true("API-1. package rootからImageGenerationConfigをimportできる", hasattr(_igc_module, "ImageGenerationConfig"))
    check("API-2. __all__がImageGenerationConfigのみを含む", list(_igc_module.__all__), ["ImageGenerationConfig"])

    _star_namespace = {}
    exec("from image_generation_config import *", _star_namespace)
    _star_imported_names = sorted(k for k in _star_namespace if not k.startswith("__"))
    check(
        "API-3. `from image_generation_config import *`で束縛される名前がImageGenerationConfigのみ"
        "（privateなhelperがpackage rootからimportできない）",
        _star_imported_names,
        ["ImageGenerationConfig"],
    )

    _field_names = [f.name for f in fields(ImageGenerationConfig)]
    check("API-4. ImageGenerationConfigのfieldがenabledのみ", _field_names, ["enabled"])

    _enabled_field = fields(ImageGenerationConfig)[0]
    check("API-5. enabledフィールドの型がbool", _enabled_field.type, bool)

    check_true("API-6. from_envがclassmethodとして呼び出し可能", callable(ImageGenerationConfig.from_env))
    check_true(
        "API-6. from_env呼び出し結果がImageGenerationConfigのインスタンス",
        isinstance(ImageGenerationConfig.from_env(), ImageGenerationConfig),
    )
    print()

    # =====================================================================
    # IMM: Immutability（3 Scenario）
    # =====================================================================

    print("[IMM] Immutability")

    _imm_cfg = ImageGenerationConfig(enabled=True)
    _imm_result, _imm_exc = invoke(lambda: setattr(_imm_cfg, "enabled", False))
    check_true("IMM-1. frozen=Trueによりenabled再代入がFrozenInstanceErrorになる", isinstance(_imm_exc, FrozenInstanceError))

    set_enabled_env("true")
    _imm_a = ImageGenerationConfig.from_env()
    _imm_b = ImageGenerationConfig.from_env()
    check_true("IMM-2. 2つのfrom_env()呼び出し結果のinstance間でstateが共有されない（別オブジェクト）", _imm_a is not _imm_b)
    check("IMM-2. 別オブジェクトでもenabled値は一致する（値としての等価性）", _imm_a == _imm_b, True)

    _imm_c = ImageGenerationConfig(enabled=True)
    check("IMM-3. instanceが保持する属性がenabledのみ（request単位のmutable stateを保持しない）", sorted(vars(_imm_c).keys()), ["enabled"])
    print()

    # =====================================================================
    # DEP: Dependency Guard（14 Scenario、21章R-1〜R-13・R-OUT-1に対応）
    # =====================================================================

    print("[DEP] Dependency Guard")

    _ALLOWED_STDLIB = {"os", "dataclasses"}
    _igc_import_details = {name: get_import_details(path) for name, path in IGC_FILES.items()}
    for _name, _details in _igc_import_details.items():
        check_true(
            f"DEP-1. {_name}の絶対importが許可集合（os, dataclasses）の部分集合（R-OUT-1）",
            _details["absolute_roots"].issubset(_ALLOWED_STDLIB),
        )

    _dep_file_targets = {
        "DEP-2": ("main.py（R-1）", PROJECT_ROOT / "main.py"),
        "DEP-3": ("src/image_resolver.py（R-2）", PROJECT_ROOT / "src" / "image_resolver.py"),
        "DEP-4": ("src/outputs/manager.py（OutputManager、R-3）", PROJECT_ROOT / "src" / "outputs" / "manager.py"),
        "DEP-5": ("src/outputs/wordpress_output.py（WordPressOutput、R-4）", PROJECT_ROOT / "src" / "outputs" / "wordpress_output.py"),
    }
    for _id, (_label, _path) in _dep_file_targets.items():
        check_true(f"{_id}. {_label}が存在する", _path.is_file())
        _details = get_import_details(_path)
        check_false(f"{_id}. {_label}がimage_generation_configをimportしない（AST）", "image_generation_config" in _details["absolute_roots"])
        check_false(f"{_id}. {_label}にImageGenerationConfigという文字列が含まれない", file_references_name(_path, "ImageGenerationConfig"))

    _dep_dir_targets = {
        "DEP-6": ("src/openai_image_generation/（OpenAIImageGenerator、R-5）", PROJECT_ROOT / "src" / "openai_image_generation"),
        "DEP-7": ("src/article_featured_media_orchestration/（ArticleFeaturedMediaOrchestrator、R-6）", PROJECT_ROOT / "src" / "article_featured_media_orchestration"),
        "DEP-8": ("src/generated_image_wordpress_media/（GeneratedImageWordPressMediaUploader、R-7）", PROJECT_ROOT / "src" / "generated_image_wordpress_media"),
        "DEP-9": ("src/wordpress_media/（WordPressMediaUploader、R-8）", PROJECT_ROOT / "src" / "wordpress_media"),
        "DEP-11": ("src/pipeline/（R-10）", PROJECT_ROOT / "src" / "pipeline"),
        "DEP-12": ("src/workflow_engine/（R-11）", PROJECT_ROOT / "src" / "workflow_engine"),
        "DEP-13": ("src/scheduler/（R-12）", PROJECT_ROOT / "src" / "scheduler"),
        "DEP-14": ("scripts/（R-13）", PROJECT_ROOT / "scripts"),
    }
    for _id, (_label, _dir_path) in _dep_dir_targets.items():
        check_true(f"{_id}. {_label}ディレクトリが存在する", _dir_path.is_dir())
        _py_files = sorted(_dir_path.glob("*.py"))
        check_true(f"{_id}. {_label}配下の.pyファイル一覧が1件以上存在する（vacuous pass防止）", len(_py_files) >= 1)
        _violating = []
        for _py_file in _py_files:
            _details = get_import_details(_py_file)
            if "image_generation_config" in _details["absolute_roots"]:
                _violating.append(_py_file.name)
        check(f"{_id}. {_label}配下にimage_generation_configをimportしているファイルがない（AST）", _violating, [])

    # DEP-10: retry_*（R-9、globで動的取得、vacuous pass防止）
    _retry_dirs = sorted(p for p in PROJECT_ROOT.glob("src/retry_*") if p.is_dir())
    check_true("DEP-10. retry_*ディレクトリが1件以上存在する（vacuous pass防止、R-9）", len(_retry_dirs) >= 1)
    _retry_violating = []
    for _retry_dir in _retry_dirs:
        for _py_file in sorted(_retry_dir.glob("*.py")):
            _details = get_import_details(_py_file)
            if "image_generation_config" in _details["absolute_roots"]:
                _retry_violating.append(f"{_retry_dir.name}/{_py_file.name}")
    check(
        f"DEP-10. retry_*配下（{len(_retry_dirs)}package）にimage_generation_configをimportしているファイルがない（AST）",
        _retry_violating,
        [],
    )
    print()

    # =====================================================================
    # RTZ: Runtime Zero Diff（3 Scenario）
    # =====================================================================

    print("[RTZ] Runtime Zero Diff")

    for _name, _details in _igc_import_details.items():
        check_false(f"RTZ-1. {_name}がopenaiをimportしない（OpenAI API非呼び出し）", "openai" in _details["absolute_roots"])

    for _name, _details in _igc_import_details.items():
        check_true(
            f"RTZ-2. {_name}がrequests等HTTPクライアントをimportしない（WordPress API非呼び出し）",
            _details["absolute_roots"].isdisjoint({"requests", "urllib", "http", "httpx"}),
        )

    for _name, _path in IGC_FILES.items():
        check(f"RTZ-3. {_name}にopen()呼出がない（ファイル書き込み副作用なし）", get_call_lines(_path, "open"), [])
    print()

    # =====================================================================
    # SEC: Security（5 Scenario）
    # =====================================================================

    print("[SEC] Security")

    for _name, _path in IGC_FILES.items():
        check_false(f'SEC-1. {_name}に"OPENAI_API_KEY"という文字列が出現しない', file_references_name(_path, "OPENAI_API_KEY"))

    _sec2_cfg = ImageGenerationConfig(enabled=True)
    check("SEC-2. instanceが保持するfieldがenabledのみ（enabled以外をinstance stateへ保持しない）", sorted(vars(_sec2_cfg).keys()), ["enabled"])

    set_enabled_env("true")
    _sec3_cfg = ImageGenerationConfig.from_env()
    check_not_contains(
        'SEC-3. repr(instance)に環境変数名"AI_IMAGE_GENERATION_ENABLED"の生文字列が含まれない',
        repr(_sec3_cfg),
        "AI_IMAGE_GENERATION_ENABLED",
    )
    check_contains("SEC-3. repr(instance)はenabled値のみを含む（dataclass自動repr、secretを含まない）", repr(_sec3_cfg), "enabled=True")

    _sec4_result, _sec4_exc = invoke(ImageGenerationConfig.from_env)
    check_true("SEC-4. from_env()呼び出しが例外を送出しない", _sec4_exc is None)
    for _name, _path in IGC_FILES.items():
        check(f"SEC-4. {_name}にraise文が存在しない（AST、例外発生経路が存在しないことの構造的確認）", get_raise_lines(_path), [])

    # 実在するAPI keyらしき値（"sk-"に続き16文字以上の英数字）のみを検出する。
    # 本checkの説明文自体に含まれる単なる"sk-"という短い文字列表記とは
    # 自己一致しないよう、十分な長さの英数字が後続する場合のみ検出する。
    _this_file_source = Path(__file__).read_text(encoding="utf-8")
    _sk_like_matches = re.findall(r"sk-[A-Za-z0-9]{16,}", _this_file_source)
    check("SEC-5. 本Test file自身にsecretらしき実値（sk-に続く長い英数字列）が直書きされていない", _sk_like_matches, [])
    print()

    # =====================================================================
    # ENV: .env.example（3 Scenario）
    # =====================================================================

    print("[ENV] .env.example")

    _env_example_path = PROJECT_ROOT / ".env.example"
    _env_example_text = _env_example_path.read_text(encoding="utf-8")
    check_true("ENV-1. .env.exampleにAI_IMAGE_GENERATION_ENABLEDという正式なGate環境変数名が記載される", "AI_IMAGE_GENERATION_ENABLED" in _env_example_text)

    check_true("ENV-2. .env.exampleにAI_IMAGE_GENERATION_ENABLED=falseというdefault OFF表現が存在する", "AI_IMAGE_GENERATION_ENABLED=false" in _env_example_text)
    # "true"という文字列だけで判定すると、ファイル内の無関係な既存設定
    # （例：LOG_ENABLED=true）で自明にPASSしてしまうため、新規Gateセクション
    # 固有のコメント文言で判定する。
    check_true(
        "ENV-2. .env.exampleのコメントから有効化にはtrueだけが有効と理解できる"
        "（Gateセクション固有の説明文の存在）",
        "true以外の値" in _env_example_text,
    )

    check_true("ENV-3. .env.exampleにOPENAI_API_KEYのplaceholder行が存在する", "OPENAI_API_KEY" in _env_example_text)
    check_true("ENV-3. .env.exampleにOPENAI_IMAGE_TIMEOUT_SECONDSの記載が存在する", "OPENAI_IMAGE_TIMEOUT_SECONDS" in _env_example_text)
    check_false('ENV-3. .env.exampleのplaceholderが実secretらしき値（"sk-"で始まる文字列）を含まない', "sk-" in _env_example_text)
    print()

finally:
    _restore_env()

# ─── 結果サマリー ───
print("=" * 60)
total = len(results_log)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = total - passed
print(f"Release：v6.15.0")
print(f"正式名称：Image Generation Configuration Gate")
print(f"Scenario：54")
print(f"Assertion合計：{total}")
print(f"合計: {passed}/{total} PASS  /  {failed} FAIL")
print("=" * 60)

if failed > 0:
    print()
    print("FAILしたテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
else:
    print("全テスト PASS")
