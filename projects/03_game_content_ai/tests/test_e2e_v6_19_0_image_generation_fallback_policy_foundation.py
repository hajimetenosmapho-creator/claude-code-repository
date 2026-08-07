"""
E2E テスト: v6.19.0 Image Generation Fallback Policy Foundation

Source of Truth:
    docs/design/image_generation_fallback_policy_foundation.md
    （Architecture Review 4：Approved with Suggestions、Blocking 0・Major 0）

本テストは実OpenAI API・実WordPress API・実HTTP通信・実課金のいずれも発生させない。
`image_generation_fallback_policy` はConsumer-lessであり、`main.py`・
`image_resolver.py`・`outputs`・`pipeline`・`scripts`・既存Orchestrator・
Composition Root関連の既存コードのいずれからも参照されていないことを
RUNTIME-Scenarioで確認する。

openai未import確認はclean subprocessで決定的に検証し、skipを一切用いない。
network遮断はsubprocessとは独立したtest本体プロセス内でsocket.getaddrinfo／
socket.socket.connectを直接patchして検証する（v6.18 precedent踏襲）。

callerによる元例外の無変換再送出（PROPAGATE_ORIGINAL_ERROR の呼び出し側義務）、
および再送出後の上位Runtimeの扱いは、本E2Eの保証対象に含めない。これは
DI-4 Runtime WiringのProduction Implementation／Code Review／E2Eで検証する
契約である（設計書21.6節 V-1〜V-5／W-1〜W-4）。

Scenario構成:
    API-       Public API：__all__・export面・decide()のsignature
    ACTION-    ImageGenerationFallbackAction 2値
    CAT-       ImageGenerationFailureCategory 5値
    MAP-       Category→Action写像・分類表の呼び出し前後不変性
    IMM-       Immutability：frozen・fields()件数・action非field
    CONT-      継続対象：4 reasonのみ（allow-list）
    UNCLS-     INVALID_RESPONSE／UNKNOWN → UNCLASSIFIED（回帰防止）
    REJECT-    REQUEST_REJECTED → IMAGE_GENERATION_REQUEST_REJECTED
    PROP-      伝播対象の網羅
    WPUP-      WordPress Media Upload失敗 → 安全側（message非依存）
    REASON-    reason 9値の網羅的4/1/2/2分割
    NOPARSE-   message非解析のbehavioral証明
    UNK-       未知Exception → UNCLASSIFIED
    DEFENSE-   reason属性欠落／未知値の防御的処理（ValueError非送出）
    TYPEERR-   Exceptionでない入力 → TypeError
    BASE-      BaseException系 → TypeError（決定として扱われない）
    PURE-      pure decision（==／hash一致）
    SEC-       secret非保持・例外非到達・action非露出
    NOEXC-     AST検証：ExceptHandler0件・Raise1箇所のみ・__post_init__なし
    DEP-       AST検証：禁止import・汎用型isinstanceなし
    IMPORT-    clean subprocessによるopenai非import検証
    SOCKET-    in-process socket遮断検証
    RUNTIME-   Runtime Zero Diff（既存Runtimeからの非参照）
    COMPAT-    既存Public API不変（v6.9〜v6.18）
    ENV-       environment isolation

実行方法:
    cd projects/03_game_content_ai
    venv\\Scripts\\python.exe tests/test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py
"""
import ast
import dataclasses
import inspect
import os
import socket
import subprocess
import sys
import types
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

# ─── テスト用ユーティリティ（v6.9.0〜v6.18.0 precedentを踏襲） ───

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


# ─── AST解析ユーティリティ（v6.9.0〜v6.18.0 precedentを踏襲・一部本Release向けに追加） ───


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


def get_raise_from_count(file_path: Path) -> int:
    """`raise ... from ...`（ast.Raise.cause が非None）の件数を返す（0件であるべき）。"""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    return sum(
        1 for node in ast.walk(tree)
        if isinstance(node, ast.Raise) and node.cause is not None
    )


def get_class_bases(file_path: Path) -> dict:
    """file_path内の各ClassDefについて、base class名のリストを返す。"""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    result = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            bases = []
            for b in node.bases:
                if isinstance(b, ast.Name):
                    bases.append(b.id)
                elif isinstance(b, ast.Attribute):
                    bases.append(b.attr)
            result[node.name] = bases
    return result


def get_class_method_names(file_path: Path, class_name: str) -> list:
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return [
                n.name for n in node.body
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            ]
    return []


def get_isinstance_second_arg_names(file_path: Path) -> list:
    """isinstance(x, T) または isinstance(x, (T1, T2)) のT（Name）の名前を集める。"""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    names = []
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id == "isinstance"
            and len(node.args) >= 2
        ):
            arg = node.args[1]
            if isinstance(arg, ast.Name):
                names.append(arg.id)
            elif isinstance(arg, ast.Tuple):
                for elt in arg.elts:
                    if isinstance(elt, ast.Name):
                        names.append(elt.id)
    return names


def get_mutating_call_lines(file_path: Path, target_names: set) -> list:
    """target_names（module-level分類表の変数名集合）に対する
    代入・添字代入・破壊的メソッド呼び出しの行番号を、module-level定義文自身を除いて返す。
    0件であるべき（AC-28）。"""
    source = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(file_path))
    hits = []

    module_level_assign_lines = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in target_names:
                    module_level_assign_lines.add(node.lineno)

    mutating_methods = {"update", "pop", "clear", "setdefault", "add", "discard"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and node.lineno not in module_level_assign_lines:
            for t in node.targets:
                if isinstance(t, ast.Name) and t.id in target_names:
                    hits.append(node.lineno)
                if isinstance(t, ast.Subscript) and isinstance(t.value, ast.Name) \
                        and t.value.id in target_names:
                    hits.append(node.lineno)
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr in mutating_methods
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id in target_names
        ):
            hits.append(node.lineno)
    return hits


def file_references_name(file_path: Path, name: str) -> bool:
    return name in file_path.read_text(encoding="utf-8")


print("=" * 60)
print("v6.19.0 Image Generation Fallback Policy Foundation E2E テスト")
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
_SAVED_ENVIRON_SNAPSHOT = dict(os.environ)


def _restore_env():
    for key, value in _SAVED_ENV.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value


try:
    import image_generation_fallback_policy as _pkg
    from image_generation_fallback_policy import (
        ImageGenerationFailureCategory,
        ImageGenerationFallbackAction,
        ImageGenerationFallbackDecision,
        decide_image_generation_fallback,
    )
    from openai_image_generation import (
        OpenAIImageGenerationError,
        OpenAIImageGenerationErrorReason,
    )
    from wordpress_media import WordPressMediaUploadError

    PACKAGE_DIR = PROJECT_ROOT / "src" / "image_generation_fallback_policy"
    MODULE_FILE = PACKAGE_DIR / "image_generation_fallback_policy.py"
    INIT_FILE = PACKAGE_DIR / "__init__.py"

    _ALL_REASONS = list(OpenAIImageGenerationErrorReason)
    _CONTINUABLE_REASON_NAMES = frozenset(
        {"TIMEOUT", "CONNECTION", "RATE_LIMIT", "SERVER_ERROR"}
    )

    # =====================================================================
    # API: Public API
    # =====================================================================

    print("[API] Public API")

    check(
        "API-ALL-EXACT. __all__ が4 symbolのみである",
        sorted(_pkg.__all__),
        sorted([
            "ImageGenerationFailureCategory",
            "ImageGenerationFallbackAction",
            "ImageGenerationFallbackDecision",
            "decide_image_generation_fallback",
        ]),
    )
    for _name in _pkg.__all__:
        check_true(f"API-EXPORT-EXISTS[{_name}]. {_name} がpackage直下からimportできる", hasattr(_pkg, _name))

    _sig = inspect.signature(decide_image_generation_fallback)
    _params = list(_sig.parameters.values())
    check(
        "API-SIGNATURE-PARAM-COUNT. decide()の引数が1件のみ",
        len(_params),
        1,
    )
    check(
        "API-SIGNATURE-PARAM-NAME. 引数名がerrorである",
        _params[0].name,
        "error",
    )
    check_false(
        "API-SIGNATURE-NOT-KEYWORD-ONLY. 引数がkeyword-onlyでない（位置引数で渡せる）",
        _params[0].kind is inspect.Parameter.KEYWORD_ONLY,
    )
    check_true(
        "API-RETURN-TYPE. decide()の戻り値が常にImageGenerationFallbackDecisionである"
        "（Noneを返さない。AC-6）",
        isinstance(
            decide_image_generation_fallback(ValueError("probe")),
            ImageGenerationFallbackDecision,
        ),
    )
    print()

    # =====================================================================
    # ACTION: ImageGenerationFallbackAction 2値
    # =====================================================================

    print("[ACTION] ImageGenerationFallbackAction")

    check(
        "ACTION-COUNT-EXACT. Action Enumの値集合が2件で過不足ない",
        sorted(a.name for a in ImageGenerationFallbackAction),
        sorted(["CONTINUE_WITHOUT_FEATURED_MEDIA", "PROPAGATE_ORIGINAL_ERROR"]),
    )
    check(
        "ACTION-VALUE-CONTINUE. valueが名前と一致する",
        ImageGenerationFallbackAction.CONTINUE_WITHOUT_FEATURED_MEDIA.value,
        "CONTINUE_WITHOUT_FEATURED_MEDIA",
    )
    check(
        "ACTION-VALUE-PROPAGATE. valueが名前と一致する",
        ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR.value,
        "PROPAGATE_ORIGINAL_ERROR",
    )
    print()

    # =====================================================================
    # CAT: ImageGenerationFailureCategory 5値
    # =====================================================================

    print("[CAT] ImageGenerationFailureCategory")

    check(
        "CAT-COUNT-EXACT. Category Enumの値集合が5件で過不足ない",
        sorted(c.name for c in ImageGenerationFailureCategory),
        sorted([
            "IMAGE_GENERATION_FAILED",
            "IMAGE_GENERATION_REQUEST_REJECTED",
            "IMAGE_GENERATION_NOT_AUTHORIZED",
            "MEDIA_UPLOAD_FAILED",
            "UNCLASSIFIED",
        ]),
    )
    check_false(
        "CAT-NO-ENVIRONMENT-ERROR. ENVIRONMENT_ERRORが存在しない（m-1回帰防止）",
        "ENVIRONMENT_ERROR" in [c.name for c in ImageGenerationFailureCategory],
    )
    check_true(
        "CAT-HAS-REQUEST-REJECTED. IMAGE_GENERATION_REQUEST_REJECTEDが存在する",
        "IMAGE_GENERATION_REQUEST_REJECTED" in [c.name for c in ImageGenerationFailureCategory],
    )
    for _c in ImageGenerationFailureCategory:
        check(f"CAT-VALUE-MATCHES-NAME[{_c.name}]. valueが名前と一致する", _c.value, _c.name)
    print()

    # =====================================================================
    # MAP: Category→Action写像・分類表の不変性
    # =====================================================================

    print("[MAP] Category→Action写像")

    from image_generation_fallback_policy.image_generation_fallback_policy import (
        _ACTION_BY_CATEGORY,
        _CONTINUABLE_REASONS,
    )

    check(
        "MAP-COVERAGE. _ACTION_BY_CATEGORYがCategory全memberを鍵として持つ（AC-12）",
        set(_ACTION_BY_CATEGORY.keys()),
        set(ImageGenerationFailureCategory),
    )
    check_false(
        "MAP-NO-GET-DEFAULT. _ACTION_BY_CATEGORYへの.get(既定値)呼び出しがソース中に"
        "存在しない（未登録キーへの丸め込みを行わない。AC-12）",
        file_references_name(MODULE_FILE, "_ACTION_BY_CATEGORY.get("),
    )

    # Code Review Finding s-1対応：分類表の型契約を検証する。
    # _ACTION_BY_CATEGORYは設計書11.4.1節が確定した「素のdict」でなければならず、
    # MappingProxyType（不採用と明記）へ未承認で変更されていないことを確認する。
    check_true(
        "MAP-TYPE-ACTION-BY-CATEGORY-IS-DICT. _ACTION_BY_CATEGORYが素のdictである"
        "（s-1対応、設計書11.4.1節）",
        isinstance(_ACTION_BY_CATEGORY, dict),
    )
    check_false(
        "MAP-TYPE-ACTION-BY-CATEGORY-NOT-MAPPINGPROXY. _ACTION_BY_CATEGORYが"
        "未承認のMappingProxyTypeへ変更されていない（s-1対応、設計書11.4.1節で不採用）",
        isinstance(_ACTION_BY_CATEGORY, types.MappingProxyType),
    )
    check_true(
        "MAP-TYPE-CONTINUABLE-REASONS-IS-FROZENSET. _CONTINUABLE_REASONSが"
        "frozensetである（s-1対応、設計書13.5節）",
        isinstance(_CONTINUABLE_REASONS, frozenset),
    )
    for _cat in ImageGenerationFailureCategory:
        _decision = ImageGenerationFallbackDecision(category=_cat)
        _expected_action = (
            ImageGenerationFallbackAction.CONTINUE_WITHOUT_FEATURED_MEDIA
            if _cat is ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED
            else ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR
        )
        check(
            f"MAP-ACTION[{_cat.name}]. actionがcategoryから正しく導出される",
            _decision.action,
            _expected_action,
        )

    _map_snapshot_before = dict(_ACTION_BY_CATEGORY)
    _reasons_snapshot_before = frozenset(_CONTINUABLE_REASONS)
    for _reason in _ALL_REASONS:
        decide_image_generation_fallback(OpenAIImageGenerationError("x", _reason))
    decide_image_generation_fallback(WordPressMediaUploadError("y"))
    decide_image_generation_fallback(ValueError("z"))
    check(
        "MAP-DICT-UNCHANGED. decide()呼び出し前後で_ACTION_BY_CATEGORYの内容が不変（AC-28）",
        dict(_ACTION_BY_CATEGORY),
        _map_snapshot_before,
    )
    check(
        "MAP-FROZENSET-UNCHANGED. decide()呼び出し前後で_CONTINUABLE_REASONSの内容が不変（AC-28）",
        frozenset(_CONTINUABLE_REASONS),
        _reasons_snapshot_before,
    )
    print()

    # =====================================================================
    # IMM: Immutability
    # =====================================================================

    print("[IMM] Immutability")

    _fields = dataclasses.fields(ImageGenerationFallbackDecision)
    check(
        "IMM-FIELDS-COUNT. fields()がcategory1件のみを返す",
        [f.name for f in _fields],
        ["category"],
    )
    check_false(
        "IMM-ACTION-NOT-FIELD. actionがfields()に含まれない",
        "action" in [f.name for f in _fields],
    )
    check_true(
        "IMM-IS-DATACLASS. frozen dataclassである",
        dataclasses.is_dataclass(ImageGenerationFallbackDecision),
    )

    _imm_decision = ImageGenerationFallbackDecision(
        category=ImageGenerationFailureCategory.UNCLASSIFIED
    )
    _, _frozen_exc = invoke(lambda: setattr(_imm_decision, "category", ImageGenerationFailureCategory.MEDIA_UPLOAD_FAILED))
    check_true(
        "IMM-FROZEN-REASSIGN. 再代入でFrozenInstanceErrorが送出される",
        isinstance(_frozen_exc, dataclasses.FrozenInstanceError),
    )

    _d1 = ImageGenerationFallbackDecision(category=ImageGenerationFailureCategory.MEDIA_UPLOAD_FAILED)
    _d2 = ImageGenerationFallbackDecision(category=ImageGenerationFailureCategory.MEDIA_UPLOAD_FAILED)
    _d3 = ImageGenerationFallbackDecision(category=ImageGenerationFailureCategory.UNCLASSIFIED)
    check_true("IMM-EQ-SAME-CATEGORY. 同一categoryのDecisionは等しい", _d1 == _d2)
    check_false("IMM-EQ-DIFF-CATEGORY. 異なるcategoryのDecisionは等しくない", _d1 == _d3)
    check(
        "IMM-HASH-DETERMINISTIC. 同一categoryのDecisionはhashが一致する",
        hash(_d1),
        hash(_d2),
    )
    print()

    # =====================================================================
    # CONT: 継続対象は4 reasonのみ（allow-list）
    # =====================================================================

    print("[CONT] 継続対象（allow-list）")

    _continuing_reason_names = sorted(
        r.name for r in _ALL_REASONS
        if decide_image_generation_fallback(
            OpenAIImageGenerationError("x", r)
        ).action is ImageGenerationFallbackAction.CONTINUE_WITHOUT_FEATURED_MEDIA
    )
    check(
        "CONT-EXACTLY-4. CONTINUEとなるreasonが正確に4値ちょうどである",
        _continuing_reason_names,
        sorted(_CONTINUABLE_REASON_NAMES),
    )
    for _reason in _ALL_REASONS:
        _decision = decide_image_generation_fallback(OpenAIImageGenerationError("x", _reason))
        if _reason.name in _CONTINUABLE_REASON_NAMES:
            check(
                f"CONT-CATEGORY[{_reason.name}]. IMAGE_GENERATION_FAILEDへ分類される",
                _decision.category,
                ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED,
            )
        else:
            check_false(
                f"CONT-NOT-CONTINUE[{_reason.name}]. CONTINUEにならない",
                _decision.action is ImageGenerationFallbackAction.CONTINUE_WITHOUT_FEATURED_MEDIA,
            )
    print()

    # =====================================================================
    # UNCLS: INVALID_RESPONSE／UNKNOWN → UNCLASSIFIED
    # =====================================================================

    print("[UNCLS] INVALID_RESPONSE／UNKNOWN の安全側分類")

    # v6.24.0（DI-11後半）で追加された2 reasonも、既存2値と同じくUNCLASSIFIED（安全側）へ
    # 落ちる。UNCLS-NOT-FAILED（IMAGE_GENERATION_FAILEDへ落ちないことの回帰防止）を
    # 新2値へも及ぼすため、本セクションの対象へ追加する（設計書13.2節・案X）。
    for _reason_name in ("INVALID_RESPONSE", "UNKNOWN",
                         "UNEXPECTED_EXCEPTION", "INVALID_RESPONSE_STRUCTURE"):
        _reason = OpenAIImageGenerationErrorReason[_reason_name]
        _decision = decide_image_generation_fallback(OpenAIImageGenerationError("x", _reason))
        check(
            f"UNCLS-CATEGORY[{_reason_name}]. UNCLASSIFIEDへ分類される",
            _decision.category,
            ImageGenerationFailureCategory.UNCLASSIFIED,
        )
        check(
            f"UNCLS-ACTION[{_reason_name}]. PROPAGATE_ORIGINAL_ERRORとなる",
            _decision.action,
            ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR,
        )
        check_false(
            f"UNCLS-NOT-FAILED[{_reason_name}]. IMAGE_GENERATION_FAILEDへ落ちない（回帰防止）",
            _decision.category is ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED,
        )

    # UNCLASSIFIEDの3系統（10.7節 C-16）が同一Categoryへ落ちることの確認
    check(
        "UNCLS-SYSTEM-A-UNKNOWN-TYPE. 未知Exceptionも同一UNCLASSIFIEDへ落ちる",
        decide_image_generation_fallback(RuntimeError("boom")).category,
        ImageGenerationFailureCategory.UNCLASSIFIED,
    )
    print()

    # =====================================================================
    # REJECT: REQUEST_REJECTED → IMAGE_GENERATION_REQUEST_REJECTED
    # =====================================================================

    print("[REJECT] REQUEST_REJECTED の分類")

    _reject_messages = [
        "OpenAI APIへのリクエストが不正です（Content Policy等による生成拒否を含む）",
        "model 'gpt-image-2-2099-01-01' does not exist or you do not have access to it",
        "",
        "HTTP 404 model_not_found",
    ]
    _reject_decisions = [
        decide_image_generation_fallback(
            OpenAIImageGenerationError(m, OpenAIImageGenerationErrorReason.REQUEST_REJECTED)
        )
        for m in _reject_messages
    ]
    for _i, _d in enumerate(_reject_decisions):
        check(
            f"REJECT-CATEGORY[{_i}]. IMAGE_GENERATION_REQUEST_REJECTEDへ分類される",
            _d.category,
            ImageGenerationFailureCategory.IMAGE_GENERATION_REQUEST_REJECTED,
        )
        check(
            f"REJECT-ACTION[{_i}]. PROPAGATE_ORIGINAL_ERRORとなる",
            _d.action,
            ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR,
        )
        check_false(
            f"REJECT-NOT-FAILED[{_i}]. IMAGE_GENERATION_FAILEDへ落ちない（回帰防止）",
            _d.category is ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED,
        )
    check_true(
        "REJECT-MESSAGE-INDEPENDENT. 全messageバリエーションで結果が同一（message非解析の証明）",
        all(d == _reject_decisions[0] for d in _reject_decisions),
    )
    print()

    # =====================================================================
    # PROP: 伝播対象の網羅
    # =====================================================================

    print("[PROP] 伝播対象")

    for _reason_name in ("AUTHENTICATION", "PERMISSION_DENIED"):
        _reason = OpenAIImageGenerationErrorReason[_reason_name]
        _decision = decide_image_generation_fallback(OpenAIImageGenerationError("x", _reason))
        check(
            f"PROP-CATEGORY[{_reason_name}]. IMAGE_GENERATION_NOT_AUTHORIZEDへ分類される",
            _decision.category,
            ImageGenerationFailureCategory.IMAGE_GENERATION_NOT_AUTHORIZED,
        )
        check(
            f"PROP-ACTION[{_reason_name}]. PROPAGATE_ORIGINAL_ERRORとなる",
            _decision.action,
            ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR,
        )

    _generic_exceptions = [
        ValueError("invalid"),
        TypeError("bad type"),
        AttributeError("missing attr"),
        RuntimeError("generic runtime error"),
    ]
    for _exc in _generic_exceptions:
        _decision = decide_image_generation_fallback(_exc)
        check(
            f"PROP-UNCLASSIFIED[{type(_exc).__name__}]. UNCLASSIFIEDへ分類される",
            _decision.category,
            ImageGenerationFailureCategory.UNCLASSIFIED,
        )
        check(
            f"PROP-UNCLASSIFIED-ACTION[{type(_exc).__name__}]. PROPAGATE_ORIGINAL_ERRORとなる",
            _decision.action,
            ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR,
        )
    print()

    # =====================================================================
    # WPUP: WordPress Media Upload失敗
    # =====================================================================

    print("[WPUP] WordPress Media Upload失敗")

    _wpup_messages = [
        "WordPress Media API returned HTTP 401 (code=rest_cannot_create, message=SECRETMARKER)",
        "WordPress Media API returned HTTP 403 (code=rest_forbidden, message=insufficient permission)",
        "WordPress Media API returned HTTP 500",
        "WordPress Media APIへの通信に失敗しました",
        "",
    ]
    _wpup_decisions = [
        decide_image_generation_fallback(WordPressMediaUploadError(m))
        for m in _wpup_messages
    ]
    for _i, _d in enumerate(_wpup_decisions):
        check(
            f"WPUP-CATEGORY[{_i}]. MEDIA_UPLOAD_FAILEDへ分類される",
            _d.category,
            ImageGenerationFailureCategory.MEDIA_UPLOAD_FAILED,
        )
        check(
            f"WPUP-ACTION[{_i}]. PROPAGATE_ORIGINAL_ERRORとなる",
            _d.action,
            ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR,
        )
    check_true(
        "WPUP-MESSAGE-INDEPENDENT. 全messageバリエーションで結果が同一（message非解析の証明）",
        all(d == _wpup_decisions[0] for d in _wpup_decisions),
    )
    print()

    # =====================================================================
    # REASON: reason 9値の網羅的4/1/2/2分割
    # =====================================================================

    print("[REASON] reason 9値の網羅的分類")

    _expected_category_by_reason_name = {
        "TIMEOUT": ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED,
        "CONNECTION": ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED,
        "RATE_LIMIT": ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED,
        "SERVER_ERROR": ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED,
        "REQUEST_REJECTED": ImageGenerationFailureCategory.IMAGE_GENERATION_REQUEST_REJECTED,
        "AUTHENTICATION": ImageGenerationFailureCategory.IMAGE_GENERATION_NOT_AUTHORIZED,
        "PERMISSION_DENIED": ImageGenerationFailureCategory.IMAGE_GENERATION_NOT_AUTHORIZED,
        "INVALID_RESPONSE": ImageGenerationFailureCategory.UNCLASSIFIED,
        "UNKNOWN": ImageGenerationFailureCategory.UNCLASSIFIED,
        # v6.23.0（DI-11前半）で追加された4 reason。いずれもREQUEST_REJECTEDと
        # 同一のcategoryへ写像される（設計書7.5.1節の全数写像表）。
        "BAD_REQUEST": ImageGenerationFailureCategory.IMAGE_GENERATION_REQUEST_REJECTED,
        "RESOURCE_NOT_FOUND": ImageGenerationFailureCategory.IMAGE_GENERATION_REQUEST_REJECTED,
        "CONFLICT": ImageGenerationFailureCategory.IMAGE_GENERATION_REQUEST_REJECTED,
        "UNPROCESSABLE_ENTITY": ImageGenerationFailureCategory.IMAGE_GENERATION_REQUEST_REJECTED,
        # v6.24.0（DI-11後半）で追加された2 reason。いずれもallow-list2集合のどちらにも
        # 属さないため、C-17の安全側性質によりUNCLASSIFIEDへ自動的に落ちる
        # （policy側は無改修＝設計書7.5節）。
        "UNEXPECTED_EXCEPTION": ImageGenerationFailureCategory.UNCLASSIFIED,
        "INVALID_RESPONSE_STRUCTURE": ImageGenerationFailureCategory.UNCLASSIFIED,
    }
    check(
        "REASON-ENUM-COUNT. OpenAIImageGenerationErrorReasonが15値である（v6.24.0で13→15）",
        len(_ALL_REASONS),
        15,
    )
    check(
        "REASON-COVERAGE-COMPLETE. 全15値が期待分類表と過不足なく一致する",
        {r.name for r in _ALL_REASONS},
        set(_expected_category_by_reason_name.keys()),
    )
    for _reason in _ALL_REASONS:
        _decision = decide_image_generation_fallback(OpenAIImageGenerationError("x", _reason))
        check(
            f"REASON-MATCH[{_reason.name}]. Decision Tableと一致する",
            _decision.category,
            _expected_category_by_reason_name[_reason.name],
        )

    # Code Review Finding m-2対応：集計元をテスト自身の期待表
    # （_expected_category_by_reason_name）ではなく、decide()のactual戻り値へ
    # 変更する。これによりProduction Codeの分類が誤っていた場合、本assertion
    # 自体が検出できる（自己参照的assertionの解消）。
    # 上記REASON-MATCH（個別9 reason検証）はそのまま維持し、本Scenarioは
    # 実測結果の独立した網羅的集計として別途確認する。
    _actual_category_by_reason = {
        _reason: decide_image_generation_fallback(
            OpenAIImageGenerationError("x", _reason)
        ).category
        for _reason in _ALL_REASONS
    }
    _actual_by_category_count = {}
    for _actual_cat in _actual_category_by_reason.values():
        _actual_by_category_count[_actual_cat] = _actual_by_category_count.get(_actual_cat, 0) + 1

    check(
        "REASON-SPLIT-4-1-2-2. decide()の実測結果を集計した結果、"
        "reason 15値がFAILED/REQUEST_REJECTED/NOT_AUTHORIZED/UNCLASSIFIED = "
        "4/5/2/4で分割される（v6.23.0でREQUEST_REJECTED側が1→5、"
        "v6.24.0でUNCLASSIFIED側が2→4。"
        "FAILED側は4のまま不変＝CONTINUE非拡大の直接証拠。"
        "m-2対応：自己参照ではなく実測値を集計。Scenario IDは据え置き）",
        {
            ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED:
                _actual_by_category_count.get(ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED, 0),
            ImageGenerationFailureCategory.IMAGE_GENERATION_REQUEST_REJECTED:
                _actual_by_category_count.get(ImageGenerationFailureCategory.IMAGE_GENERATION_REQUEST_REJECTED, 0),
            ImageGenerationFailureCategory.IMAGE_GENERATION_NOT_AUTHORIZED:
                _actual_by_category_count.get(ImageGenerationFailureCategory.IMAGE_GENERATION_NOT_AUTHORIZED, 0),
            ImageGenerationFailureCategory.UNCLASSIFIED:
                _actual_by_category_count.get(ImageGenerationFailureCategory.UNCLASSIFIED, 0),
        },
        {
            ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED: 4,
            ImageGenerationFailureCategory.IMAGE_GENERATION_REQUEST_REJECTED: 5,
            ImageGenerationFailureCategory.IMAGE_GENERATION_NOT_AUTHORIZED: 2,
            ImageGenerationFailureCategory.UNCLASSIFIED: 4,
        },
    )
    check(
        "REASON-SPLIT-TOTAL-9. 実測分類の合計が15件であり、欠落・重複がない"
        "（v6.23.0で9→13、v6.24.0で13→15。m-2対応。Scenario IDは据え置き）",
        sum(_actual_by_category_count.values()),
        15,
    )
    check(
        "REASON-SPLIT-NO-STRAY-CATEGORY. 実測分類が上記4 Category以外へ"
        "分類されていない（欠落・重複の網羅確認、m-2対応）",
        set(_actual_by_category_count.keys()),
        {
            ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED,
            ImageGenerationFailureCategory.IMAGE_GENERATION_REQUEST_REJECTED,
            ImageGenerationFailureCategory.IMAGE_GENERATION_NOT_AUTHORIZED,
            ImageGenerationFailureCategory.UNCLASSIFIED,
        },
    )
    print()

    # =====================================================================
    # NOPARSE: message非解析のbehavioral証明
    # =====================================================================

    print("[NOPARSE] message非解析の証明")

    _noparse_variants = [
        "",
        "HTTP 500 Internal Server Error",
        "code=rest_forbidden",
        "予期しないエラーが発生しました（日本語テキスト）",
        "Unexpected error occurred (English text)",
    ]
    for _variant in _noparse_variants:
        _d_reject = decide_image_generation_fallback(
            OpenAIImageGenerationError(_variant, OpenAIImageGenerationErrorReason.REQUEST_REJECTED)
        )
        check(
            f"NOPARSE-REJECT[{_variant!r}]. messageに関わらずIMAGE_GENERATION_REQUEST_REJECTED",
            _d_reject.category,
            ImageGenerationFailureCategory.IMAGE_GENERATION_REQUEST_REJECTED,
        )
        _d_wpup = decide_image_generation_fallback(WordPressMediaUploadError(_variant))
        check(
            f"NOPARSE-WPUP[{_variant!r}]. messageに関わらずMEDIA_UPLOAD_FAILED",
            _d_wpup.category,
            ImageGenerationFailureCategory.MEDIA_UPLOAD_FAILED,
        )
        _d_unknown = decide_image_generation_fallback(
            OpenAIImageGenerationError(_variant, OpenAIImageGenerationErrorReason.UNKNOWN)
        )
        check(
            f"NOPARSE-UNCLS[{_variant!r}]. messageに関わらずUNCLASSIFIED",
            _d_unknown.category,
            ImageGenerationFailureCategory.UNCLASSIFIED,
        )
    print()

    # =====================================================================
    # UNK: 未知Exception
    # =====================================================================

    print("[UNK] 未知Exception")

    class _TestOnlyCustomException(Exception):
        """テスト内定義の独自例外（Repositoryのいずれの型とも無関係）。"""

    _unknown_exceptions = [
        _TestOnlyCustomException("custom"),
        ModuleNotFoundError("no such module"),
        AttributeError("no such attribute"),
        KeyError("missing key"),
    ]
    for _exc in _unknown_exceptions:
        _decision = decide_image_generation_fallback(_exc)
        check(
            f"UNK-CATEGORY[{type(_exc).__name__}]. UNCLASSIFIEDへ分類される",
            _decision.category,
            ImageGenerationFailureCategory.UNCLASSIFIED,
        )
        check(
            f"UNK-ACTION[{type(_exc).__name__}]. PROPAGATE_ORIGINAL_ERRORとなる",
            _decision.action,
            ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR,
        )
    print()

    # =====================================================================
    # DEFENSE: reason属性欠落／未知値の防御的処理
    # =====================================================================

    print("[DEFENSE] reason属性欠落／未知値")

    # ケース1: reason属性が完全に欠落したOpenAIImageGenerationError相当object
    _no_reason_error = OpenAIImageGenerationError.__new__(OpenAIImageGenerationError)
    RuntimeError.__init__(_no_reason_error, "boom")
    check_false(
        "DEFENSE-PRECONDITION-NO-REASON. テスト用objectがreason属性を持たない",
        hasattr(_no_reason_error, "reason"),
    )
    _decision_no_reason, _no_reason_exc = invoke(
        lambda: decide_image_generation_fallback(_no_reason_error)
    )
    check_true(
        "DEFENSE-NO-VALUEERROR-1. reason属性欠落時にValueErrorを送出しない",
        _no_reason_exc is None,
    )
    check(
        "DEFENSE-CATEGORY-1. reason属性欠落時はUNCLASSIFIEDへ倒れる",
        _decision_no_reason.category if _decision_no_reason else None,
        ImageGenerationFailureCategory.UNCLASSIFIED,
    )

    # ケース2: reasonがOpenAIImageGenerationErrorReasonのmemberでない
    _bad_reason_error = OpenAIImageGenerationError("boom", OpenAIImageGenerationErrorReason.TIMEOUT)
    _bad_reason_error.reason = "not-a-real-reason-enum-member"
    _decision_bad_reason, _bad_reason_exc = invoke(
        lambda: decide_image_generation_fallback(_bad_reason_error)
    )
    check_true(
        "DEFENSE-NO-VALUEERROR-2. reasonが未知値の場合にValueErrorを送出しない",
        _bad_reason_exc is None,
    )
    check(
        "DEFENSE-CATEGORY-2. reasonが未知値の場合はUNCLASSIFIEDへ倒れる",
        _decision_bad_reason.category if _decision_bad_reason else None,
        ImageGenerationFailureCategory.UNCLASSIFIED,
    )

    # ケース3: reasonがハッシュ不可能な値（list／dict／set）
    # Code Review Finding m-1対応：frozenset membership testが素の
    # `reason in _CONTINUABLE_REASONS` だと TypeError（unhashable type）を
    # 送出しうる。設計書13.4節「memberでない場合、UNCLASSIFIEDへ倒す」の
    # 「member でない」はEnum member以外のあらゆる値を含むため、
    # ハッシュ不可能な値も安全側へ倒れなければならない。
    for _unhashable_reason in ([], {}, set()):
        _unhashable_error = OpenAIImageGenerationError(
            "boom", OpenAIImageGenerationErrorReason.TIMEOUT
        )
        _unhashable_error.reason = _unhashable_reason
        _decision_unhashable, _unhashable_exc = invoke(
            lambda: decide_image_generation_fallback(_unhashable_error)
        )
        check_true(
            f"DEFENSE-NO-TYPEERROR-3[{type(_unhashable_reason).__name__}]. "
            "reasonがハッシュ不可能な値でも、policy自身から予期しないTypeError"
            "（入力型違反以外のTypeError）を送出しない（m-1対応）",
            _unhashable_exc is None,
        )
        check(
            f"DEFENSE-CATEGORY-3[{type(_unhashable_reason).__name__}]. "
            "reasonがハッシュ不可能な値の場合はUNCLASSIFIEDへ倒れる（m-1対応）",
            _decision_unhashable.category if _decision_unhashable else None,
            ImageGenerationFailureCategory.UNCLASSIFIED,
        )
        check(
            f"DEFENSE-ACTION-3[{type(_unhashable_reason).__name__}]. "
            "reasonがハッシュ不可能な値の場合はPROPAGATE_ORIGINAL_ERRORとなる（m-1対応）",
            _decision_unhashable.action if _decision_unhashable else None,
            ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR,
        )
    print()

    # =====================================================================
    # TYPEERR: Exceptionでない入力
    # =====================================================================

    print("[TYPEERR] Exceptionでない入力")

    _non_exception_inputs = [None, "a string", 42, 3.14, [], {}]
    for _bad_input in _non_exception_inputs:
        _result, _exc = invoke(lambda v=_bad_input: decide_image_generation_fallback(v))
        check_true(
            f"TYPEERR-RAISED[{type(_bad_input).__name__}]. TypeErrorが送出される",
            isinstance(_exc, TypeError),
        )
        check(
            f"TYPEERR-MESSAGE[{type(_bad_input).__name__}]. message完全一致",
            str(_exc) if _exc else None,
            "error must be an Exception",
        )
        check_true(
            f"TYPEERR-NO-DECISION[{type(_bad_input).__name__}]. 決定が返されない",
            _result is None,
        )
    print()

    # =====================================================================
    # BASE: BaseException系
    # =====================================================================

    print("[BASE] BaseException系")

    for _base_exc_cls in (KeyboardInterrupt, SystemExit, GeneratorExit):
        _result, _exc = invoke(lambda c=_base_exc_cls: decide_image_generation_fallback(c()))
        check_true(
            f"BASE-TYPEERROR[{_base_exc_cls.__name__}]. TypeErrorとなる（決定として扱われない）",
            isinstance(_exc, TypeError),
        )
        check_true(
            f"BASE-NO-DECISION[{_base_exc_cls.__name__}]. 決定が返されない",
            _result is None,
        )
    print()

    # =====================================================================
    # PURE: pure decision
    # =====================================================================

    print("[PURE] pure decision")

    _pure_a = decide_image_generation_fallback(
        OpenAIImageGenerationError("message A", OpenAIImageGenerationErrorReason.TIMEOUT)
    )
    _pure_b = decide_image_generation_fallback(
        OpenAIImageGenerationError("message B（異なるmessage・別インスタンス）", OpenAIImageGenerationErrorReason.TIMEOUT)
    )
    check_true(
        "PURE-EQ. 同一reasonの異なる例外インスタンスに対し同じDecisionを返す（==）",
        _pure_a == _pure_b,
    )
    check(
        "PURE-HASH. hash()も一致する",
        hash(_pure_a),
        hash(_pure_b),
    )

    _pure_c1 = decide_image_generation_fallback(WordPressMediaUploadError("first call"))
    _pure_c2 = decide_image_generation_fallback(WordPressMediaUploadError("second call"))
    check_true(
        "PURE-REPEATED-CALL. 同一型の例外を2回渡しても同じDecisionを返す",
        _pure_c1 == _pure_c2,
    )
    print()

    # =====================================================================
    # SEC: Security（secret非保持・例外非到達）
    # =====================================================================

    print("[SEC] Security")

    _SECRET_MARKER = "SECRETMARKER_UNIQUE_TOKEN_0x9f3c"
    _secret_bearing_error = WordPressMediaUploadError(
        f"WordPress Media API returned HTTP 401 (code=rest_cannot_create, message={_SECRET_MARKER})"
    )
    _secret_decision = decide_image_generation_fallback(_secret_bearing_error)

    check_not_contains(
        "SEC-REPR-NO-MARKER. repr(decision)にsecret markerが含まれない",
        repr(_secret_decision),
        _SECRET_MARKER,
    )
    check_not_contains(
        "SEC-STR-NO-MARKER. str(decision)にsecret markerが含まれない",
        str(_secret_decision),
        _SECRET_MARKER,
    )
    _asdict_result = dataclasses.asdict(_secret_decision)
    check_not_contains(
        "SEC-ASDICT-NO-MARKER. asdict(decision)にsecret markerが含まれない",
        str(_asdict_result),
        _SECRET_MARKER,
    )
    _astuple_result = dataclasses.astuple(_secret_decision)
    check_not_contains(
        "SEC-ASTUPLE-NO-MARKER. astuple(decision)にsecret markerが含まれない",
        str(_astuple_result),
        _SECRET_MARKER,
    )
    check_false(
        "SEC-ASDICT-NO-ACTION-KEY. asdict(decision)にactionキーが含まれない",
        "action" in _asdict_result,
    )
    check_not_contains(
        "SEC-REPR-NO-ACTION-WORD. repr(decision)に'action='という文字列が含まれない",
        repr(_secret_decision),
        "action=",
    )
    check_true(
        "SEC-NO-EXCEPTION-REFERENCE. decisionの全属性値の中に元例外オブジェクトが存在しない",
        _secret_bearing_error not in vars(_secret_decision).values(),
    )
    check_false(
        "SEC-NO-ERROR-ATTRIBUTE. decisionが元例外への参照属性を持たない",
        any(hasattr(_secret_decision, n) for n in ("error", "exception", "original_error", "cause")),
    )
    print()

    # =====================================================================
    # NOEXC: AST検証（例外構造）
    # =====================================================================

    print("[NOEXC] 例外構造のAST検証")

    check(
        "NOEXC-NO-EXCEPT-HANDLER. moduleにast.ExceptHandlerが0件（例外を捕捉しない）",
        get_except_handler_count(MODULE_FILE),
        0,
    )
    check(
        "NOEXC-RAISE-ONLY-IN-DECIDE. decide_image_generation_fallback以外にast.Raiseが存在しない",
        get_raise_lines_outside(MODULE_FILE, "decide_image_generation_fallback"),
        [],
    )
    check(
        "NOEXC-NO-RAISE-FROM. raise ... from ...（ast.Raise.cause非None）が0件",
        get_raise_from_count(MODULE_FILE),
        0,
    )
    check_false(
        "NOEXC-NO-POST-INIT. ImageGenerationFallbackDecisionが__post_init__を定義しない",
        "__post_init__" in get_class_method_names(MODULE_FILE, "ImageGenerationFallbackDecision"),
    )

    _class_bases = get_class_bases(MODULE_FILE)
    check(
        "NOEXC-NO-NEW-EXCEPTION-CLASS. moduleが定義するclassがEnum2件とdataclass1件のみで、"
        "例外型（Exception／RuntimeError等を継承するclass）を新規定義しない",
        _class_bases,
        {
            "ImageGenerationFallbackAction": ["Enum"],
            "ImageGenerationFailureCategory": ["Enum"],
            "ImageGenerationFallbackDecision": [],
        },
    )
    check_false(
        "NOEXC-NO-PROTOCOL. moduleが新規Protocolを定義しない",
        file_references_name(MODULE_FILE, "Protocol"),
    )
    print()

    # =====================================================================
    # DEP: 依存Guard（AST）
    # =====================================================================

    print("[DEP] 依存Guard")

    _ALLOWED_IMPORT_ROOTS = {
        "__future__",
        "dataclasses",
        "enum",
        "openai_image_generation",
        "wordpress_media",
    }
    _actual_roots = get_import_roots(MODULE_FILE)
    check_true(
        "DEP-FORBIDDEN-IMPORTS. importするrootが許可集合の部分集合である"
        "（outputs／main／image_resolver／pipeline／ai／scheduler／retry_*／"
        "logger／analytics／ai_image_generation等を一切importしない）",
        _actual_roots <= _ALLOWED_IMPORT_ROOTS,
    )
    for _forbidden in ("os", "logging", "requests", "socket", "openai"):
        check_false(
            f"DEP-NO-{_forbidden.upper()}-IMPORT. {_forbidden}をmodule-levelでimportしない",
            _forbidden in _actual_roots,
        )

    _isinstance_targets = set(get_isinstance_second_arg_names(MODULE_FILE))
    check_true(
        "DEP-ISINSTANCE-TARGETS-LIMITED. isinstance判定の対象型がRepository内の3型＋Exceptionのみ"
        "（m-1対応でOpenAIImageGenerationErrorReasonへのisinstance判定を追加。"
        "汎用組み込み例外型ではなくRepository内で公開済みのEnum型であり、"
        "設計書13.5節が禁じる汎用型判定には該当しない）",
        _isinstance_targets <= {
            "Exception",
            "OpenAIImageGenerationError",
            "OpenAIImageGenerationErrorReason",
            "WordPressMediaUploadError",
        },
    )
    for _generic_type in ("ImportError", "ValueError", "TypeError", "ModuleNotFoundError"):
        check_false(
            f"DEP-NO-GENERIC-ISINSTANCE[{_generic_type}]. 汎用型への isinstance 判定が存在しない（m-1対応）",
            _generic_type in _isinstance_targets,
        )

    check(
        "DEP-NO-MUTATION-ACTION-BY-CATEGORY. _ACTION_BY_CATEGORYへの代入・破壊的メソッド呼び出しがmodule-level定義以外に0件",
        get_mutating_call_lines(MODULE_FILE, {"_ACTION_BY_CATEGORY"}),
        [],
    )
    check(
        "DEP-NO-MUTATION-CONTINUABLE-REASONS. _CONTINUABLE_REASONSへの代入・破壊的メソッド呼び出しがmodule-level定義以外に0件",
        get_mutating_call_lines(MODULE_FILE, {"_CONTINUABLE_REASONS"}),
        [],
    )

    # Code Review Finding m-3対応：__init__.py（package root）も
    # 禁止import AST検証の対象へ含める。既存の許可された相対import
    # （.image_generation_fallback_policy）は失敗扱いにしない。
    _init_actual_roots = get_import_roots(INIT_FILE)
    _ALLOWED_INIT_IMPORT_ROOTS = {"image_generation_fallback_policy"}
    check_true(
        "DEP-INIT-FORBIDDEN-IMPORTS. __init__.pyがimportするrootが許可集合"
        "（自パッケージへの相対importのみ）の部分集合である（m-3対応）",
        _init_actual_roots <= _ALLOWED_INIT_IMPORT_ROOTS,
    )
    for _forbidden in ("os", "logging", "requests", "socket", "openai"):
        check_false(
            f"DEP-INIT-NO-{_forbidden.upper()}-IMPORT. __init__.pyが{_forbidden}を"
            "importしない（m-3対応）",
            _forbidden in _init_actual_roots,
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
        "from image_generation_fallback_policy import decide_image_generation_fallback; "
        "print('OPENAI_IMPORTED=' + str('openai' in sys.modules))"
    )
    _completed = subprocess.run(
        [str(_VENV_PYTHON), "-c", _subprocess_script],
        cwd=str(PROJECT_ROOT),
        env=dict(os.environ),
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
        "IMPORT-1-OPENAI-NOT-IMPORTED. import後もopenaiがimportされていない"
        "（clean subprocessによる決定的検証、skipなし）",
        _completed.stdout,
        "OPENAI_IMPORTED=False",
    )
    check(
        "IMPORT-1-STDERR-EMPTY. stderrが空（tracebackが出ていない）",
        _completed.stderr.strip(),
        "",
    )
    print()

    # =====================================================================
    # SOCKET: in-process network遮断検証
    # =====================================================================

    print("[SOCKET] in-process network遮断")

    _orig_getaddrinfo = socket.getaddrinfo
    _orig_connect = socket.socket.connect

    def _blocked_getaddrinfo(*args, **kwargs):
        raise AssertionError("socket.getaddrinfo was called (unexpected DNS resolution)")

    def _blocked_connect(self, *args, **kwargs):
        raise AssertionError("socket.socket.connect was called (unexpected network connection)")

    socket.getaddrinfo = _blocked_getaddrinfo
    socket.socket.connect = _blocked_connect
    try:
        _, _network_exc = invoke(
            lambda: decide_image_generation_fallback(
                OpenAIImageGenerationError("x", OpenAIImageGenerationErrorReason.TIMEOUT)
            )
        )
        _, _network_exc2 = invoke(
            lambda: decide_image_generation_fallback(WordPressMediaUploadError("x"))
        )
    finally:
        socket.getaddrinfo = _orig_getaddrinfo
        socket.socket.connect = _orig_connect

    check_true(
        "SOCKET-NO-NETWORK. decide()はsocket.getaddrinfo／socket.socket.connectの"
        "いずれも呼び出さない（test本体プロセス内でのin-process遮断検証。"
        "IMPORT-1のsubprocessとは独立）",
        _network_exc is None and _network_exc2 is None,
    )
    check_true(
        "SOCKET-RESTORED. socket関数がpatch前の状態へ復元されている",
        socket.getaddrinfo is _orig_getaddrinfo and socket.socket.connect is _orig_connect,
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
            f"{_case_id}. {_label}がimage_generation_fallback_policyを参照していない",
            file_references_name(_path, "image_generation_fallback_policy"),
        )
    print(
        "  ※ main.py／image_resolver.py等への実バイト差分（git diff）の確認は"
        "本テストの対象外であり、Release工程内で別途実施する。"
    )
    print()

    # =====================================================================
    # COMPAT: backward compatibility
    # =====================================================================

    print("[COMPAT] backward compatibility")

    import openai_image_generation as _v611_pkg
    check(
        "COMPAT-V611-ALL-UNCHANGED. v6.11の__all__が不変",
        sorted(_v611_pkg.__all__),
        sorted(["OpenAIImageGenerator", "OpenAIImageGenerationError", "OpenAIImageGenerationErrorReason"]),
    )
    check(
        "COMPAT-V611-REASON-COUNT-9. OpenAIImageGenerationErrorReasonが15値である"
        "（v6.23.0 DI-11前半で9→13、v6.24.0 DI-11後半で13→15。Scenario IDは据え置き）",
        len(list(OpenAIImageGenerationErrorReason)),
        15,
    )

    import wordpress_media as _v69_pkg
    check(
        "COMPAT-V69-ALL-WITH-REASON. v6.9の__all__がDI-10のreason分類Enumを含む",
        sorted(_v69_pkg.__all__),
        sorted([
            "MediaUploadResult",
            "WordPressMediaUploadError",
            "WordPressMediaUploadErrorReason",
            "WordPressMediaUploader",
        ]),
    )

    _wp_error_instance = WordPressMediaUploadError("compat check")
    check_true(
        "COMPAT-WP-NO-REASON-ATTR. WordPressMediaUploadErrorインスタンスにreason属性が"
        "追加されている（DI-10実施済み。本Scenarioは既知差分としてN-17の遵守から"
        "反転した。20章 DI-10参照）",
        hasattr(_wp_error_instance, "reason"),
    )

    _openai_error_sig = inspect.signature(OpenAIImageGenerationError.__init__)
    check(
        "COMPAT-OPENAI-ERROR-SIGNATURE. OpenAIImageGenerationError.__init__のパラメータ名が不変",
        list(_openai_error_sig.parameters.keys()),
        ["self", "message", "reason"],
    )

    from ai_image_generation import AIImageGenerator
    check(
        "COMPAT-V610-PROTOCOL-UNCHANGED. AIImageGenerator Protocolの公開memberが"
        "generateのみである（拡張されていない）",
        sorted(n for n in vars(AIImageGenerator) if not n.startswith("_")),
        ["generate"],
    )

    import image_generation_config as _v615_pkg
    check(
        "COMPAT-V615-ALL-UNCHANGED. v6.15の__all__が不変",
        _v615_pkg.__all__,
        ["ImageGenerationConfig"],
    )

    import generated_image_filename_policy as _v616_pkg
    check(
        "COMPAT-V616-ALL-UNCHANGED. v6.16の__all__が不変",
        _v616_pkg.__all__,
        ["generate_image_filename"],
    )

    import article_image_prompt_construction as _v617_pkg
    check(
        "COMPAT-V617-ALL-UNCHANGED. v6.17の__all__が不変",
        _v617_pkg.__all__,
        ["construct_article_image_prompt"],
    )

    import article_featured_media_composition as _v618_pkg
    check(
        "COMPAT-V618-ALL-UNCHANGED. v6.18の__all__が不変",
        _v618_pkg.__all__,
        ["ArticleFeaturedMediaCompositionRoot"],
    )
    print(
        "  ※ requirements.txt／.env.example／main.pyの実バイト差分（git diff）の"
        "確認（AC-26）は本テストの対象外であり、Production Implementation報告内で"
        "git statusにより別途確認する。"
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
    check(
        "ENV-FULL-ENVIRON-UNCHANGED. os.environ全体が開始時のスナップショットと一致する"
        "（本packageは環境変数を一切読み書きしないため）",
        dict(os.environ),
        _SAVED_ENVIRON_SNAPSHOT,
    )
    print()

finally:
    _restore_env()

# ─── 結果サマリー ───
print("=" * 60)
total = len(results_log)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = total - passed
print("Release：v6.19.0")
print("正式名称：Image Generation Fallback Policy Foundation")
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
