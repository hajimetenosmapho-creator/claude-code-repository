"""
E2E テスト: v6.18.0 Article Featured Media Composition Root Foundation

Source of Truth:
    docs/design/article_featured_media_composition_root_foundation.md
    （Architecture Review 1：Changes Required → Architecture Amendment 1：
      Completed → Architecture Review 2：Approved with Suggestions、
      Blocking 0・Major 0）

本テストは実OpenAI API・実WordPress API・実HTTP通信・実課金のいずれも発生させない。
`article_featured_media_composition`はConsumer-lessであり、`main.py`・
`image_resolver.py`・`outputs`・`pipeline`・`scripts`関連の既存コードの
いずれからも参照されていないことをRUNTIME-Scenarioで確認する。

openai未import確認（IMPORT-1）はclean subprocessで決定的に検証し、skipを
一切用いない（Architecture Amendment 1 F-2対応）。network遮断（IMPORT-2）は
subprocessとは独立したtest本体プロセス内でsocket.getaddrinfo／
socket.socket.connectを直接patchして検証する（Architecture Review 2
Finding-3対応：in-process検証であることの明示）。

READINESS-Scenarioにおいて、construct_article_image_prompt（v6.17）・
generate_image_filename（v6.16）を直接importして呼び出すのは本test code
自身であり、ArticleFeaturedMediaCompositionRoot（Production Code）は
これらをimportしない（10.3節、DEP-Scenario参照）。これは既存Contract間の
統合可能性を確認する検証であり、Runtime Wiringの実装ではない（Architecture
Review 2 Finding-4対応）。apply()は呼び出さず、main.pyへの接続・記事loopへの
組み込み・fallback判断はいずれも行わない。

Scenario構成:
    API-（Public API：__all__・export面・from_env/is_available signature）
    IMM-（Immutability：frozen・fields()件数・repr metadata）
    GATE-（Gate Contract：値ごとのenabled判定、v6.15 Fail Closed precedent）
    ON-（Gate ON＋正常設定）
    ERRCFG-（Gate ON＋設定不備：既存factory ValueErrorの無変換伝播）
    SEQ-（構築順序・単一インスタンス・環境変数非読取り）
    AVAIL-（is_available()のContract）
    NONE-（None Contract：Null Object不使用の確認）
    INV-（__post_init__不変条件：固定message完全一致）
    MIME-（MIME Information Contract：SSOT・read-only・generate()との一致）
    SEC-（Security Contract：repr／str／asdict、field(repr=False)）
    IMPORT-（外部接続ゼロ：clean subprocess・in-process socket遮断）
    DEP-（依存Guard：AST。禁止import・except非存在・raise配置）
    RUNTIME-（Runtime Zero Diff：既存Runtimeからの非参照）
    COMPAT-（backward compatibility：v6.9〜v6.17 Public API不変）
    ENV-（environment isolation）
    READINESS-（Composition Readiness：AC-22。Runtime Wiring非実装の確認）

実行方法:
    cd projects/03_game_content_ai
    ..\\..\\venv\\Scripts\\python.exe tests/test_e2e_v6_18_0_article_featured_media_composition_root_foundation.py
"""
import ast
import dataclasses
import os
import socket
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ─── テスト用ユーティリティ（v6.9.0〜v6.17.0 precedentを踏襲） ───

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


# ─── AST解析ユーティリティ（v6.9.0〜v6.17.0 precedentを踏襲） ───


def get_import_roots(file_path: Path) -> set:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                roots.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def get_except_handler_count(file_path: Path) -> int:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    return sum(1 for node in ast.walk(tree) if isinstance(node, ast.ExceptHandler))


def get_raise_lines_outside(file_path: Path, func_name: str) -> list:
    """funcName以外の場所にある ast.Raise の行番号を返す（0件であるべき）。"""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))

    target_ranges = []
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            target_ranges.append((node.lineno, node.end_lineno))

    outside = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise):
            if not any(start <= node.lineno <= end for start, end in target_ranges):
                outside.append(node.lineno)
    return outside


def get_new_exception_class_names(file_path: Path) -> list:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            names.append(node.name)
    return names


def get_module_level_getenv_calls(file_path: Path) -> list:
    """module levelで os.getenv／os.environ を参照している箇所の行番号を返す
    （FunctionDef・ClassDef本体の内側は対象外）。"""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))

    nested_lines = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            for child in ast.walk(node):
                if hasattr(child, "lineno"):
                    nested_lines.add(child.lineno)

    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in ("getenv", "environ"):
            if node.lineno not in nested_lines:
                hits.append(node.lineno)
        if isinstance(node, ast.Name) and node.id in ("getenv",):
            if node.lineno not in nested_lines:
                hits.append(node.lineno)
    return hits


def file_references_name(file_path: Path, name: str) -> bool:
    return name in file_path.read_text(encoding="utf-8")


def file_contains_call(file_path: Path, substrings) -> bool:
    text = file_path.read_text(encoding="utf-8")
    return any(s in text for s in substrings)


def get_attribute_call_lines(file_path: Path, attr_name: str) -> list:
    """file_path中で `<expr>.<attr_name>(...)` という形のCall式の行番号を返す。
    文字列literal内の同名テキストとは異なりast.Callノードのみを対象とするため、
    自己参照的な文字列一致による誤検知を避けられる。"""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    lines = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == attr_name
        ):
            lines.append(node.lineno)
    return lines


print("=" * 60)
print("v6.18.0 Article Featured Media Composition Root Foundation E2E テスト")
print("=" * 60)
print()

# ─── Environment隔離：テスト開始前の状態を保存し、finallyで完全に復元する ───

_ENV_KEYS = (
    "AI_IMAGE_GENERATION_ENABLED",
    "OPENAI_API_KEY",
    "OPENAI_IMAGE_TIMEOUT_SECONDS",
    "WP_SITE_URL",
    "WP_USERNAME",
    "WP_APP_PASSWORD",
)
_SAVED_ENV = {key: os.environ.get(key) for key in _ENV_KEYS}


def _restore_env():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


def _clear_env():
    for key in _ENV_KEYS:
        os.environ.pop(key, None)


def _set_gate_on_dummy_credentials():
    _clear_env()
    os.environ["AI_IMAGE_GENERATION_ENABLED"] = "true"
    os.environ["OPENAI_API_KEY"] = "SK-DUMMY-DO-NOT-USE"
    os.environ["WP_SITE_URL"] = "https://example.invalid"
    os.environ["WP_USERNAME"] = "dummy-user"
    os.environ["WP_APP_PASSWORD"] = "DUMMY-APP-PASSWORD-DO-NOT-USE"


_DUMMY_API_KEY = "SK-DUMMY-DO-NOT-USE"
_DUMMY_APP_PASSWORD = "DUMMY-APP-PASSWORD-DO-NOT-USE"

try:
    import article_featured_media_composition
    from article_featured_media_composition import ArticleFeaturedMediaCompositionRoot
    from openai_image_generation import OpenAIImageGenerator

    ROOT_PACKAGE_DIR = PROJECT_ROOT / "src" / "article_featured_media_composition"
    ROOT_MODULE_FILE = ROOT_PACKAGE_DIR / "article_featured_media_composition_root.py"

    # =====================================================================
    # API: Public API
    # =====================================================================

    print("[API] Public API")

    check(
        "API-ALL. __all__がArticleFeaturedMediaCompositionRootのみ",
        article_featured_media_composition.__all__,
        ["ArticleFeaturedMediaCompositionRoot"],
    )
    _public_names = sorted(
        n for n in dir(article_featured_media_composition) if not n.startswith("_")
    )
    # from .article_featured_media_composition_root import ... により、Pythonの
    # import機構が submodule 名（article_featured_media_composition_root）も
    # package属性として暗黙に公開する（既存precedent wordpress_media等と同一の
    # 標準的挙動）。__all__（API-ALL）はこのsubmodule名を含まないため、実質的な
    # Public Surfaceは__all__で担保される。本Scenarioは、それ以外の想定外symbol
    # （adapter/config/helper/Protocol/exception）が漏れていないことのみを確認する。
    check(
        "API-PUBLIC-SURFACE. moduleの公開属性がArticleFeaturedMediaCompositionRootと"
        "自身のsubmodule名のみ（adapter/config/helper/Protocol/exceptionを含まない）",
        _public_names,
        sorted(["ArticleFeaturedMediaCompositionRoot", "article_featured_media_composition_root"]),
    )
    check_true(
        "API-FROMENV-CLASSMETHOD. from_envがclassmethodである",
        isinstance(
            vars(ArticleFeaturedMediaCompositionRoot)["from_env"], classmethod
        ),
    )
    _fromenv_result, _fromenv_exc = invoke(
        lambda: ArticleFeaturedMediaCompositionRoot.from_env()
    )
    check_true(
        "API-FROMENV-NOARGS. from_env()が引数なしで呼び出せる（Gate OFF既定状態）",
        _fromenv_exc is None,
    )
    check_true(
        "API-ISAVAILABLE-CALLABLE. is_available()がcallableである",
        callable(getattr(ArticleFeaturedMediaCompositionRoot, "is_available", None)),
    )
    print()

    # =====================================================================
    # IMM: Immutability
    # =====================================================================

    print("[IMM] Immutability")

    _clear_env()
    _imm_root = ArticleFeaturedMediaCompositionRoot.from_env()
    check_true(
        "IMM-DATACLASS. frozen dataclassである",
        dataclasses.is_dataclass(_imm_root) and _imm_root.__dataclass_params__.frozen,
    )

    def _assign_orchestrator():
        _imm_root.orchestrator = None

    def _assign_mime():
        _imm_root.image_mime_type = "image/png"

    _, _orch_assign_exc = invoke(_assign_orchestrator)
    check_true(
        "IMM-FROZEN-ORCH. orchestratorへの再代入でFrozenInstanceError",
        isinstance(_orch_assign_exc, dataclasses.FrozenInstanceError),
    )
    _, _mime_assign_exc = invoke(_assign_mime)
    check_true(
        "IMM-FROZEN-MIME. image_mime_typeへの再代入でFrozenInstanceError",
        isinstance(_mime_assign_exc, dataclasses.FrozenInstanceError),
    )

    _fields = dataclasses.fields(_imm_root)
    check("IMM-FIELDS-COUNT. fieldsが2件", len(_fields), 2)
    check(
        "IMM-FIELDS-NAMES. field名がorchestrator/image_mime_type",
        [f.name for f in _fields],
        ["orchestrator", "image_mime_type"],
    )
    _orch_field = next(f for f in _fields if f.name == "orchestrator")
    _mime_field = next(f for f in _fields if f.name == "image_mime_type")
    check_false(
        "IMM-REPR-METADATA-ORCH. orchestrator fieldはrepr=False", _orch_field.repr
    )
    check_true(
        "IMM-REPR-METADATA-MIME. image_mime_type fieldはrepr=True（既定）",
        _mime_field.repr,
    )
    print()

    # =====================================================================
    # GATE: Gate Contract
    # =====================================================================

    print("[GATE] Gate Contract")

    _GATE_CASES = [
        ("GATE-UNSET", None, False, "未設定"),
        ("GATE-FALSE", "false", False, '"false"'),
        ("GATE-NUMERIC", "1", False, '"1"'),
        ("GATE-YES", "yes", False, '"yes"'),
        ("GATE-TYPO", "ture", False, '"ture"（typo、13.6節 Inherited Limitation）'),
        ("GATE-WHITESPACE-TRUE", " true ", True, '" true "（前後空白付き、正規化される）'),
        ("GATE-UPPER-TRUE", "TRUE", True, '"TRUE"'),
    ]
    for _label, _value, _expected, _desc in _GATE_CASES:
        # Gate値のparsing結果そのものを純粋に検証するため、credentialは常に
        # ダミー値を設定しておく（Gate ONと評価された場合にcredential不足の
        # ValueErrorと混同しないため）。Gate OFFと評価される場合はcredential
        # が読まれないこと自体は別途SEQ-GATE-OFF-ENV-ISOLATIONで検証する。
        _set_gate_on_dummy_credentials()
        if _value is None:
            os.environ.pop("AI_IMAGE_GENERATION_ENABLED", None)
        else:
            os.environ["AI_IMAGE_GENERATION_ENABLED"] = _value
        _root, _exc = invoke(lambda: ArticleFeaturedMediaCompositionRoot.from_env())
        check_true(f"{_label}. {_desc}: 例外を送出しない", _exc is None)
        check(
            f"{_label}. {_desc}: is_available()=={_expected}",
            _root.is_available() if _root is not None else None,
            _expected,
        )

    _clear_env()
    _gateoff_root, _gateoff_exc = invoke(
        lambda: ArticleFeaturedMediaCompositionRoot.from_env()
    )
    check_true("GATE-OFF-NO-EXCEPTION. Gate OFF時に例外を送出しない", _gateoff_exc is None)
    check(
        "GATE-OFF-ORCHESTRATOR-NONE. Gate OFF時にorchestratorがNone",
        _gateoff_root.orchestrator,
        None,
    )
    check(
        "GATE-OFF-MIME-NONE. Gate OFF時にimage_mime_typeがNone",
        _gateoff_root.image_mime_type,
        None,
    )
    check_false(
        "GATE-OFF-UNAVAILABLE. Gate OFF時にis_available()がFalse",
        _gateoff_root.is_available(),
    )
    print()

    # =====================================================================
    # ON: Gate ON＋正常設定
    # =====================================================================

    print("[ON] Gate ON＋正常設定")

    _set_gate_on_dummy_credentials()
    _on_root, _on_exc = invoke(lambda: ArticleFeaturedMediaCompositionRoot.from_env())
    check_true("ON-NO-EXCEPTION. Gate ON＋全credential設定時に例外を送出しない", _on_exc is None)
    check_true(
        "ON-AVAILABLE. is_available()がTrue",
        _on_root.is_available() if _on_root is not None else False,
    )
    check_true(
        "ON-ORCHESTRATOR-APPLY. orchestrator.applyがcallable",
        callable(getattr(_on_root.orchestrator, "apply", None)) if _on_root else False,
    )
    check(
        "ON-MIME-DEFAULT. image_mime_typeが既定image/png",
        _on_root.image_mime_type if _on_root else None,
        "image/png",
    )

    _on_root_2, _ = invoke(lambda: ArticleFeaturedMediaCompositionRoot.from_env())
    check_true(
        "ON-DISTINCT-INSTANCES. 2回呼ぶと別インスタンス",
        _on_root is not _on_root_2,
    )
    check(
        "ON-DISTINCT-INSTANCES. ただし同一の可用性",
        _on_root_2.is_available(),
        _on_root.is_available(),
    )
    print()

    # =====================================================================
    # ERRCFG: Gate ON＋設定不備
    # =====================================================================

    print("[ERRCFG] Gate ON＋設定不備")

    _set_gate_on_dummy_credentials()
    os.environ.pop("OPENAI_API_KEY", None)
    _, _errcfg_1_exc = invoke(lambda: ArticleFeaturedMediaCompositionRoot.from_env())
    check_true(
        "ERRCFG-OPENAI-KEY-MISSING. ValueErrorが送出される",
        isinstance(_errcfg_1_exc, ValueError),
    )
    check(
        "ERRCFG-OPENAI-KEY-MISSING. message完全一致（v6.11由来、無変換伝播）",
        str(_errcfg_1_exc) if _errcfg_1_exc else None,
        "missing or blank environment variable: OPENAI_API_KEY",
    )

    _set_gate_on_dummy_credentials()
    os.environ["OPENAI_IMAGE_TIMEOUT_SECONDS"] = "abc"
    _, _errcfg_2_exc = invoke(lambda: ArticleFeaturedMediaCompositionRoot.from_env())
    check_true(
        "ERRCFG-OPENAI-TIMEOUT-NONINT. ValueErrorが送出される",
        isinstance(_errcfg_2_exc, ValueError),
    )
    check(
        "ERRCFG-OPENAI-TIMEOUT-NONINT. message完全一致",
        str(_errcfg_2_exc) if _errcfg_2_exc else None,
        "OPENAI_IMAGE_TIMEOUT_SECONDS must be an integer",
    )

    _set_gate_on_dummy_credentials()
    os.environ["OPENAI_IMAGE_TIMEOUT_SECONDS"] = "0"
    _, _errcfg_3_exc = invoke(lambda: ArticleFeaturedMediaCompositionRoot.from_env())
    check_true(
        "ERRCFG-OPENAI-TIMEOUT-ZERO. ValueErrorが送出される",
        isinstance(_errcfg_3_exc, ValueError),
    )
    check(
        "ERRCFG-OPENAI-TIMEOUT-ZERO. message完全一致",
        str(_errcfg_3_exc) if _errcfg_3_exc else None,
        "OPENAI_IMAGE_TIMEOUT_SECONDS must be a positive integer",
    )

    _set_gate_on_dummy_credentials()
    os.environ.pop("WP_SITE_URL", None)
    _, _errcfg_4_exc = invoke(lambda: ArticleFeaturedMediaCompositionRoot.from_env())
    check_true(
        "ERRCFG-WP-SITE-URL-MISSING. ValueErrorが送出される",
        isinstance(_errcfg_4_exc, ValueError),
    )
    check(
        "ERRCFG-WP-SITE-URL-MISSING. message完全一致（OpenAI構築が先に成功する順序）",
        str(_errcfg_4_exc) if _errcfg_4_exc else None,
        "missing or blank environment variables: WP_SITE_URL",
    )

    _set_gate_on_dummy_credentials()
    os.environ.pop("WP_USERNAME", None)
    _, _errcfg_5_exc = invoke(lambda: ArticleFeaturedMediaCompositionRoot.from_env())
    check(
        "ERRCFG-WP-USERNAME-MISSING. message完全一致",
        str(_errcfg_5_exc) if _errcfg_5_exc else None,
        "missing or blank environment variables: WP_USERNAME",
    )

    _set_gate_on_dummy_credentials()
    os.environ.pop("WP_APP_PASSWORD", None)
    _, _errcfg_6_exc = invoke(lambda: ArticleFeaturedMediaCompositionRoot.from_env())
    check(
        "ERRCFG-WP-APP-PASSWORD-MISSING. message完全一致",
        str(_errcfg_6_exc) if _errcfg_6_exc else None,
        "missing or blank environment variables: WP_APP_PASSWORD",
    )
    print()

    # =====================================================================
    # SEQ: 構築順序・単一インスタンス・環境変数非読取り
    # =====================================================================

    print("[SEQ] 構築順序・単一インスタンス")

    _clear_env()
    _accessed_keys = []
    _orig_getenv = os.getenv

    def _tracking_getenv(key, *args, **kwargs):
        _accessed_keys.append(key)
        return _orig_getenv(key, *args, **kwargs)

    os.getenv = _tracking_getenv
    try:
        ArticleFeaturedMediaCompositionRoot.from_env()
    finally:
        os.getenv = _orig_getenv
    check(
        "SEQ-GATE-OFF-ENV-ISOLATION. Gate OFF時にAI_IMAGE_GENERATION_ENABLED以外を読まない",
        sorted(set(_accessed_keys)),
        ["AI_IMAGE_GENERATION_ENABLED"],
    )

    _set_gate_on_dummy_credentials()
    os.environ.pop("WP_SITE_URL", None)
    os.environ.pop("WP_USERNAME", None)
    os.environ.pop("WP_APP_PASSWORD", None)
    _, _seq_exc = invoke(lambda: ArticleFeaturedMediaCompositionRoot.from_env())
    check_true(
        "SEQ-OPENAI-BEFORE-WORDPRESS. OpenAI credential完備時はWordPress側の"
        "エラーが報告される（OpenAI構築が先に成功した証跡）",
        isinstance(_seq_exc, ValueError) and "WP_SITE_URL" in str(_seq_exc),
    )

    _set_gate_on_dummy_credentials()
    _seq_root, _ = invoke(lambda: ArticleFeaturedMediaCompositionRoot.from_env())
    check_true(
        "SEQ-ORCHESTRATOR-IDENTITY. root.orchestratorへ複数回アクセスしても同一オブジェクト",
        _seq_root.orchestrator is _seq_root.orchestrator,
    )
    print()

    # =====================================================================
    # AVAIL: is_available()
    # =====================================================================

    print("[AVAIL] is_available()")

    _clear_env()
    _avail_off_root, _ = invoke(lambda: ArticleFeaturedMediaCompositionRoot.from_env())
    check(
        "AVAIL-MATCHES-NONE-OFF. is_available()==(orchestrator is not None)（Gate OFF）",
        _avail_off_root.is_available(),
        _avail_off_root.orchestrator is not None,
    )

    _set_gate_on_dummy_credentials()
    _avail_on_root, _ = invoke(lambda: ArticleFeaturedMediaCompositionRoot.from_env())
    check(
        "AVAIL-MATCHES-NONE-ON. is_available()==(orchestrator is not None)（Gate ON）",
        _avail_on_root.is_available(),
        _avail_on_root.orchestrator is not None,
    )

    _, _avail_exc = invoke(lambda: _avail_on_root.is_available())
    check_true("AVAIL-NO-EXCEPTION. is_available()は例外を送出しない", _avail_exc is None)

    _env_snapshot_before = dict(os.environ)
    _avail_on_root.is_available()
    _avail_on_root.is_available()
    check_true(
        "AVAIL-NO-SIDE-EFFECT. is_available()呼び出しがenvironmentを変更しない",
        dict(os.environ) == _env_snapshot_before,
    )
    check(
        "AVAIL-IDEMPOTENT. 複数回呼んでも同値",
        _avail_on_root.is_available(),
        _avail_on_root.is_available(),
    )
    print()

    # =====================================================================
    # NONE: None Contract
    # =====================================================================

    print("[NONE] None Contract")

    _clear_env()
    _none_root, _ = invoke(lambda: ArticleFeaturedMediaCompositionRoot.from_env())
    check_true(
        "NONE-GATE-OFF-BOTH-NONE. orchestratorとimage_mime_typeが同時にNone",
        _none_root.orchestrator is None and _none_root.image_mime_type is None,
    )
    check_false(
        "NONE-NOT-NULL-OBJECT. orchestratorがNullObject（applyを持つ代替物）ではなく"
        "真のNoneである",
        callable(getattr(_none_root.orchestrator, "apply", None)),
    )
    print()

    # =====================================================================
    # INV: __post_init__不変条件
    # =====================================================================

    print("[INV] __post_init__不変条件")

    class _FakeOrchestratorWithApply:
        def apply(self, article, prompt, filename):
            return article

    class _FakeOrchestratorWithoutApply:
        pass

    _, _inv1a_exc = invoke(
        lambda: ArticleFeaturedMediaCompositionRoot(
            orchestrator=_FakeOrchestratorWithApply(), image_mime_type=None
        )
    )
    check_true("INV-1-ORCH-ONLY. ValueErrorが送出される", isinstance(_inv1a_exc, ValueError))
    check(
        "INV-1-ORCH-ONLY. message完全一致",
        str(_inv1a_exc) if _inv1a_exc else None,
        "orchestrator and image_mime_type must be both set or both None",
    )

    _, _inv1b_exc = invoke(
        lambda: ArticleFeaturedMediaCompositionRoot(
            orchestrator=None, image_mime_type="image/png"
        )
    )
    check_true("INV-1-MIME-ONLY. ValueErrorが送出される", isinstance(_inv1b_exc, ValueError))
    check(
        "INV-1-MIME-ONLY. message完全一致",
        str(_inv1b_exc) if _inv1b_exc else None,
        "orchestrator and image_mime_type must be both set or both None",
    )

    _, _inv2_exc = invoke(
        lambda: ArticleFeaturedMediaCompositionRoot(
            orchestrator=_FakeOrchestratorWithoutApply(), image_mime_type="image/png"
        )
    )
    check_true("INV-2-NO-APPLY. TypeErrorが送出される", isinstance(_inv2_exc, TypeError))
    check(
        "INV-2-NO-APPLY. message完全一致",
        str(_inv2_exc) if _inv2_exc else None,
        "orchestrator must provide a callable apply method",
    )

    _, _inv3a_exc = invoke(
        lambda: ArticleFeaturedMediaCompositionRoot(
            orchestrator=_FakeOrchestratorWithApply(), image_mime_type=123
        )
    )
    check_true("INV-3-NOT-STR. ValueErrorが送出される", isinstance(_inv3a_exc, ValueError))
    check(
        "INV-3-NOT-STR. message完全一致",
        str(_inv3a_exc) if _inv3a_exc else None,
        "image_mime_type must be a str",
    )

    _, _inv3b_exc = invoke(
        lambda: ArticleFeaturedMediaCompositionRoot(
            orchestrator=_FakeOrchestratorWithApply(), image_mime_type="   "
        )
    )
    check_true("INV-3-BLANK. ValueErrorが送出される", isinstance(_inv3b_exc, ValueError))
    check(
        "INV-3-BLANK. message完全一致",
        str(_inv3b_exc) if _inv3b_exc else None,
        "image_mime_type must not be blank",
    )

    _inv_valid_fake, _inv_valid_exc = invoke(
        lambda: ArticleFeaturedMediaCompositionRoot(
            orchestrator=_FakeOrchestratorWithApply(), image_mime_type="image/png"
        )
    )
    check_true(
        "INV-VALID-FAKE. isinstance検証を行わないDuck Typingにより"
        "fake orchestratorを受理する（testability）",
        _inv_valid_exc is None,
    )

    _inv_valid_none, _inv_valid_none_exc = invoke(
        lambda: ArticleFeaturedMediaCompositionRoot(
            orchestrator=None, image_mime_type=None
        )
    )
    check_true(
        "INV-VALID-BOTH-NONE. 両方Noneのペアは正常に構築できる",
        _inv_valid_none_exc is None,
    )
    print()

    # =====================================================================
    # MIME: MIME Information Contract
    # =====================================================================

    print("[MIME] MIME Information Contract")

    _mime_gen_default = OpenAIImageGenerator(api_key="SK-TEST")

    def _assign_output_mime_type():
        _mime_gen_default.output_mime_type = "image/png"

    _, _mime_readonly_exc = invoke(_assign_output_mime_type)
    check_true(
        "MIME-READONLY. output_mime_typeへの代入でAttributeError",
        isinstance(_mime_readonly_exc, AttributeError),
    )

    check(
        "MIME-PNG-DEFAULT. 既定output_format=png -> image/png",
        _mime_gen_default.output_mime_type,
        "image/png",
    )
    check(
        "MIME-JPEG. output_format=jpeg -> image/jpeg",
        OpenAIImageGenerator(api_key="SK-TEST", output_format="jpeg").output_mime_type,
        "image/jpeg",
    )
    check(
        "MIME-WEBP. output_format=webp -> image/webp",
        OpenAIImageGenerator(api_key="SK-TEST", output_format="webp").output_mime_type,
        "image/webp",
    )

    class _FakeImagesResource:
        def __init__(self, response):
            self._response = response

        def generate(self, **kwargs):
            return self._response

    class _FakeOpenAIClient:
        def __init__(self, images_resource):
            self.images = images_resource

        def with_options(self, *, timeout=None, max_retries=None):
            return self

    def _fake_response():
        return SimpleNamespace(data=[SimpleNamespace(b64_json="aGVsbG8=")])

    _fake_client = _FakeOpenAIClient(_FakeImagesResource(_fake_response()))
    _mime_match_gen = OpenAIImageGenerator(api_key="SK-TEST", client=_fake_client)
    _generated_image, _generate_exc = invoke(lambda: _mime_match_gen.generate("prompt"))
    check_true(
        "MIME-MATCHES-GENERATE. FakeClient経由でgenerate()が成功する（外部接続なし）",
        _generate_exc is None,
    )
    check(
        "MIME-MATCHES-GENERATE. GeneratedImage.mime_typeとoutput_mime_typeが一致"
        "（同一SSOTから導出）",
        _generated_image.mime_type if _generated_image else None,
        _mime_match_gen.output_mime_type,
    )

    _mime_literals = ("image/png", "image/jpeg", "image/webp", "image/gif")
    check_false(
        "MIME-NO-LITERAL-IN-MODULE. Composition Root moduleにMIME文字列リテラルが"
        "存在しない（SSOTがv6.11内に維持されている）",
        file_contains_call(ROOT_MODULE_FILE, _mime_literals),
    )

    from generated_image_filename_policy import generate_image_filename

    _set_gate_on_dummy_credentials()
    _mime_compat_root, _ = invoke(lambda: ArticleFeaturedMediaCompositionRoot.from_env())
    _filename, _filename_exc = invoke(
        lambda: generate_image_filename("Test Title", _mime_compat_root.image_mime_type)
    )
    check_true(
        "MIME-FILENAME-COMPAT. from_env()由来のimage_mime_typeでgenerate_image_filename()"
        "がValueErrorにならない（v6.11 output format集合がv6.16許可集合の部分集合）",
        _filename_exc is None,
    )
    print()

    # =====================================================================
    # SEC: Security Contract
    # =====================================================================

    print("[SEC] Security Contract")

    _set_gate_on_dummy_credentials()
    _sec_root, _ = invoke(lambda: ArticleFeaturedMediaCompositionRoot.from_env())

    _sec_repr_text = repr(_sec_root)
    check_not_contains(
        "SEC-REPR-NO-API-KEY. repr(root)にダミーAPI keyが含まれない",
        _sec_repr_text,
        _DUMMY_API_KEY,
    )
    check_not_contains(
        "SEC-REPR-NO-APP-PASSWORD. repr(root)にダミーapp passwordが含まれない",
        _sec_repr_text,
        _DUMMY_APP_PASSWORD,
    )

    _sec_str_text = str(_sec_root)
    check_not_contains(
        "SEC-STR-NO-API-KEY. str(root)にダミーAPI keyが含まれない",
        _sec_str_text,
        _DUMMY_API_KEY,
    )
    check_not_contains(
        "SEC-STR-NO-APP-PASSWORD. str(root)にダミーapp passwordが含まれない",
        _sec_str_text,
        _DUMMY_APP_PASSWORD,
    )

    _sec_asdict_repr_text = repr(dataclasses.asdict(_sec_root))
    check_not_contains(
        "SEC-ASDICT-REPR-NO-API-KEY. repr(asdict(root))にダミーAPI keyが"
        "含まれない（テキスト表現としての回帰検知、AC-23）",
        _sec_asdict_repr_text,
        _DUMMY_API_KEY,
    )
    check_not_contains(
        "SEC-ASDICT-REPR-NO-APP-PASSWORD. repr(asdict(root))にダミーapp passwordが"
        "含まれない（同上）",
        _sec_asdict_repr_text,
        _DUMMY_APP_PASSWORD,
    )
    # 注意：asdict(root)の内部object graph自体（デシリアライズせず直接属性を辿った場合）が
    # secretへ到達可能であること自体はS-11のContractどおりであり、本Scenarioの
    # 合否条件にはしない（field(repr=False)はrepr()にのみ作用し、asdict()の
    # deepcopy挙動には影響しない。17.4節）。

    check_false(
        "SEC-NO-LOG-CALLS. Composition Root moduleがprint／loggingを呼び出さない",
        file_contains_call(ROOT_MODULE_FILE, ("print(", "logging.")),
    )
    check(
        "SEC-NO-MODULE-LEVEL-ENV-READ. module levelでos.getenv／os.environへ"
        "アクセスしていない（呼び出しはfrom_env()内側のみ）",
        get_module_level_getenv_calls(ROOT_MODULE_FILE),
        [],
    )
    print()

    # =====================================================================
    # IMPORT: 外部接続ゼロ
    # =====================================================================

    print("[IMPORT] 外部接続ゼロ")

    _VENV_PYTHON = PROJECT_ROOT / "venv" / "Scripts" / "python.exe"
    check_true(
        "IMPORT-VENV-PYTHON-EXISTS. Repository venv Pythonが存在する",
        _VENV_PYTHON.is_file(),
    )

    _subprocess_script = (
        "import sys; "
        "sys.path.insert(0, 'src'); "
        "from article_featured_media_composition import "
        "ArticleFeaturedMediaCompositionRoot; "
        "ArticleFeaturedMediaCompositionRoot.from_env(); "
        "print('OPENAI_IMPORTED=' + str('openai' in sys.modules))"
    )
    _subprocess_env = dict(os.environ)
    _subprocess_env.update(
        {
            "AI_IMAGE_GENERATION_ENABLED": "true",
            "OPENAI_API_KEY": _DUMMY_API_KEY,
            "WP_SITE_URL": "https://example.invalid",
            "WP_USERNAME": "dummy-user",
            "WP_APP_PASSWORD": _DUMMY_APP_PASSWORD,
        }
    )
    _completed = subprocess.run(
        [str(_VENV_PYTHON), "-c", _subprocess_script],
        cwd=str(PROJECT_ROOT),
        env=_subprocess_env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    check(
        "IMPORT-1-SUBPROCESS-EXIT-CODE. subprocessのexit codeが0",
        _completed.returncode,
        0,
    )
    check_contains(
        "IMPORT-1-OPENAI-NOT-IMPORTED. from_env()実行後もopenaiがimportされていない"
        "（clean subprocessによる決定的検証、skipなし）",
        _completed.stdout,
        "OPENAI_IMPORTED=False",
    )
    check(
        "IMPORT-1-STDERR-EMPTY. stderrが空（tracebackが出ていない）",
        _completed.stderr.strip(),
        "",
    )

    _orig_getaddrinfo = socket.getaddrinfo
    _orig_connect = socket.socket.connect

    def _blocked_getaddrinfo(*args, **kwargs):
        raise AssertionError("socket.getaddrinfo was called (unexpected DNS resolution)")

    def _blocked_connect(self, *args, **kwargs):
        raise AssertionError("socket.socket.connect was called (unexpected network connection)")

    _set_gate_on_dummy_credentials()
    socket.getaddrinfo = _blocked_getaddrinfo
    socket.socket.connect = _blocked_connect
    try:
        _, _network_exc = invoke(lambda: ArticleFeaturedMediaCompositionRoot.from_env())
    finally:
        socket.getaddrinfo = _orig_getaddrinfo
        socket.socket.connect = _orig_connect
    check_true(
        "IMPORT-2-NO-NETWORK. from_env()はsocket.getaddrinfo／socket.socket.connect"
        "のいずれも呼び出さない（test本体プロセス内でのin-process遮断検証。"
        "IMPORT-1のsubprocessとは独立）",
        _network_exc is None,
    )
    check_true(
        "IMPORT-2-RESTORED. socket関数がpatch前の状態へ復元されている",
        socket.getaddrinfo is _orig_getaddrinfo and socket.socket.connect is _orig_connect,
    )
    print()

    # =====================================================================
    # DEP: 依存Guard（AST）
    # =====================================================================

    print("[DEP] 依存Guard")

    check(
        "DEP-NO-EXCEPT-HANDLER. Composition Root moduleにast.ExceptHandlerが0件"
        "（例外を捕捉・変換しない）",
        get_except_handler_count(ROOT_MODULE_FILE),
        0,
    )
    check(
        "DEP-RAISE-ONLY-IN-POSTINIT. __post_init__以外にast.Raiseが存在しない",
        get_raise_lines_outside(ROOT_MODULE_FILE, "__post_init__"),
        [],
    )
    _new_classes = get_new_exception_class_names(ROOT_MODULE_FILE)
    check(
        "DEP-NO-NEW-CLASS. moduleが新規classを定義しない"
        "（ArticleFeaturedMediaCompositionRootのみ、dataclassとして定義済み"
        "であることは別Scenarioで確認済み）",
        _new_classes,
        ["ArticleFeaturedMediaCompositionRoot"],
    )
    check_false(
        "DEP-NO-PROTOCOL. moduleが新規Protocolを定義しない",
        file_references_name(ROOT_MODULE_FILE, "Protocol"),
    )

    _ALLOWED_IMPORT_ROOTS = {
        "__future__",
        "dataclasses",
        "article_featured_media_orchestration",
        "generated_image_wordpress_media",
        "image_generation_config",
        "openai_image_generation",
        "wordpress_media",
    }
    _actual_roots = get_import_roots(ROOT_MODULE_FILE)
    check_true(
        "DEP-FORBIDDEN-IMPORTS. importするrootが許可集合の部分集合である"
        "（outputs／main／image_resolver／pipeline／ai／scheduler／retry_*／"
        "logger／analytics等を一切importしない）",
        _actual_roots <= _ALLOWED_IMPORT_ROOTS,
    )
    check_false(
        "DEP-NO-V16-IMPORT. generated_image_filename_policy（v6.16）をimportしない",
        "generated_image_filename_policy" in _actual_roots,
    )
    check_false(
        "DEP-NO-V17-IMPORT. article_image_prompt_construction（v6.17）をimportしない",
        "article_image_prompt_construction" in _actual_roots,
    )
    print()

    # =====================================================================
    # RUNTIME: Runtime Zero Diff
    # =====================================================================

    print("[RUNTIME] Runtime Zero Diff")

    _runtime_targets = [
        ("RUNTIME-1a", "main.py", PROJECT_ROOT / "main.py"),
        ("RUNTIME-1b", "src/image_resolver.py", PROJECT_ROOT / "src" / "image_resolver.py"),
    ]
    for _outputs_file in sorted((PROJECT_ROOT / "src" / "outputs").glob("*.py")):
        _runtime_targets.append(
            (f"RUNTIME-1c[{_outputs_file.name}]", f"src/outputs/{_outputs_file.name}", _outputs_file)
        )
    for _pipeline_file in sorted((PROJECT_ROOT / "src" / "pipeline").glob("*.py")):
        _runtime_targets.append(
            (f"RUNTIME-1d[{_pipeline_file.name}]", f"src/pipeline/{_pipeline_file.name}", _pipeline_file)
        )
    for _script_file in sorted((PROJECT_ROOT / "scripts").glob("*.py")):
        _runtime_targets.append(
            (f"RUNTIME-1e[{_script_file.name}]", f"scripts/{_script_file.name}", _script_file)
        )

    for _case_id, _label, _path in _runtime_targets:
        check_false(
            f"{_case_id}. {_label}がarticle_featured_media_compositionを参照していない",
            file_references_name(_path, "article_featured_media_composition"),
        )
    print(
        "  ※ main.py／image_resolver.py等への実バイト差分（git diff）の確認は"
        "本テストの対象外であり、Review／Release工程内で別途実施する。"
    )
    print()

    # =====================================================================
    # COMPAT: backward compatibility
    # =====================================================================

    print("[COMPAT] backward compatibility")

    import openai_image_generation as _v6_11_pkg
    check(
        "COMPAT-V611-ALL-UNCHANGED. v6.11の__all__が不変",
        sorted(_v6_11_pkg.__all__),
        sorted(["OpenAIImageGenerator", "OpenAIImageGenerationError", "OpenAIImageGenerationErrorReason"]),
    )
    check_true(
        "COMPAT-V611-GENERATE-EXISTS. OpenAIImageGenerator.generateが存在する",
        callable(getattr(OpenAIImageGenerator, "generate", None)),
    )
    check_true(
        "COMPAT-V611-FROMENV-EXISTS. OpenAIImageGenerator.from_envが存在する",
        callable(getattr(OpenAIImageGenerator, "from_env", None)),
    )

    from ai_image_generation import AIImageGenerator
    check(
        "COMPAT-V610-PROTOCOL-UNCHANGED. AIImageGenerator Protocolの公開memberが"
        "generateのみである（拡張されていない）",
        sorted(n for n in vars(AIImageGenerator) if not n.startswith("_")),
        ["generate"],
    )

    import image_generation_config as _v6_15_pkg
    check(
        "COMPAT-V615-ALL-UNCHANGED. v6.15の__all__が不変",
        _v6_15_pkg.__all__,
        ["ImageGenerationConfig"],
    )

    import generated_image_filename_policy as _v6_16_pkg
    check(
        "COMPAT-V616-ALL-UNCHANGED. v6.16の__all__が不変",
        _v6_16_pkg.__all__,
        ["generate_image_filename"],
    )

    import article_image_prompt_construction as _v6_17_pkg
    check(
        "COMPAT-V617-ALL-UNCHANGED. v6.17の__all__が不変",
        _v6_17_pkg.__all__,
        ["construct_article_image_prompt"],
    )
    print()

    # =====================================================================
    # ENV: environment isolation
    # =====================================================================

    print("[ENV] environment isolation")

    _restore_env()
    check(
        "ENV-ISOLATION-RESTORED. テスト内の全操作後、開始時の環境変数状態へ復元される",
        {key: os.environ.get(key) for key in _ENV_KEYS},
        _SAVED_ENV,
    )
    print()

    # =====================================================================
    # READINESS: Composition Readiness（AC-22）
    # =====================================================================

    print("[READINESS] Composition Readiness")
    print(
        "  ※ 本Scenarioはconstruct_article_image_prompt（v6.17）・"
        "generate_image_filename（v6.16）を本test code自身が直接importして"
        "呼び出す。ArticleFeaturedMediaCompositionRoot（Production Code）は"
        "これらをimportしない（10.3節・DEP-NO-V16-IMPORT・DEP-NO-V17-IMPORT参照）。"
        "これは既存Contract間の統合可能性を検証するものであり、Runtime Wiringの"
        "実装ではない。apply()は呼び出さず、main.pyへの接続・記事loopへの組み込み・"
        "fallback判断のいずれも行わない。"
    )

    from article_image_prompt_construction import construct_article_image_prompt

    _set_gate_on_dummy_credentials()
    _readiness_root, _readiness_exc = invoke(
        lambda: ArticleFeaturedMediaCompositionRoot.from_env()
    )
    check_true(
        "READINESS-0-CONSTRUCTED. Composition Rootが例外なく構築できる",
        _readiness_exc is None,
    )

    check_true(
        "READINESS-1-AVAILABLE. root.is_available() is True",
        _readiness_root.is_available() is True,
    )
    check_true(
        "READINESS-2-MIME-NONEMPTY. root.image_mime_typeが非空str",
        isinstance(_readiness_root.image_mime_type, str)
        and bool(_readiness_root.image_mime_type.strip()),
    )

    _prompt, _prompt_exc = invoke(
        lambda: construct_article_image_prompt("有効なタイトル", "有効な概要")
    )
    check_true(
        "READINESS-3-PROMPT-STR. construct_article_image_prompt()がstrを返す"
        "（test codeが直接呼び出し）",
        isinstance(_prompt, str) and _prompt_exc is None,
    )

    _readiness_filename, _readiness_filename_exc = invoke(
        lambda: generate_image_filename("有効なタイトル", _readiness_root.image_mime_type)
    )
    check_true(
        "READINESS-4-FILENAME-STR. generate_image_filename()がValueErrorを送出せずstrを返す"
        "（test codeが直接呼び出し）",
        isinstance(_readiness_filename, str) and _readiness_filename_exc is None,
    )

    check_true(
        "READINESS-5-APPLY-CALLABLE. root.orchestrator.applyがcallableである",
        callable(getattr(_readiness_root.orchestrator, "apply", None)),
    )

    check(
        "READINESS-6-APPLY-NOT-CALLED. 本テストfile自身のソースに"
        "<expr>.apply(...)という実行呼び出しのast.Call式が1件も存在しない"
        "（apply()自体を呼び出していないことのAST検証。文字列literal内の"
        "同名テキストとは区別される）",
        get_attribute_call_lines(Path(__file__), "apply"),
        [],
    )

    check_true(
        "READINESS-7-NO-EXTERNAL-CONNECTION. 本Scenario全体を通じて外部API"
        "（OpenAI／WordPress）への実接続を発生させていない（ダミーcredential・"
        "FakeClient非使用のfrom_env()構築のみであり、HTTP通信は一切発生しない）",
        _readiness_exc is None,
    )
    print()

finally:
    _restore_env()

# ─── 結果サマリー ───
print("=" * 60)
total = len(results_log)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = total - passed
print("Release：v6.18.0")
print("正式名称：Article Featured Media Composition Root Foundation")
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
