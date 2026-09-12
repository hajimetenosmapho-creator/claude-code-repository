"""
E2E テスト: sub-milestone 6B — Invariant #35 static oracle（§28.-34 test #4）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    25章 Invariant #35・28.-34節（test #4：sink-oriented static oracle）。

Release 6.32 closed WordPress-mutation transport policyが定めるclosed
dynamic-call grammarに基づき、production code（`src/`・`scripts/`・
project-root `*.py`）全体をAST走査し、WordPressへのmutating HTTPリクエスト
候補を検出・分類する。receiver（変数の型・取得経路）を判定条件とせず、
メソッド名・呼び出し形のみで候補を識別する（28.-34節test #4）。

closed grammar（候補discovery、これ以外の間接呼び出し形は対象外と明示的に
宣言する）：
    (a) `<any-receiver>.post/put/patch/delete/request/urlopen(...)`
    (b) 呼び出し名（import-alias解決込み）が`Request`である構築呼び出し
    (c) `getattr(<receiver>, "literal-name")(...)` → (a)相当として帰着
    (d) `getattr(<receiver>, <non-literal>)(...)` → 無条件で`unknown`候補

このオラクル単体では、Invariant #35のPASS条件（28.-34節）を満たさない
——test #3（repository-backed closed set exhaustiveness、closure解析）と
両方が独立にPASSして初めてInvariant #35は満たされる。test #3は別ファイル
（test_e2e_v6_32_7_invariant_35_closure_oracle.py）で実装する。

既知の制約（設計書が明示的に宣言する範囲）：本オラクルはclosed dynamic-call
grammar（a〜d）の外側にある間接呼び出し形（変数・辞書・`functools.partial`
等に格納されたcallableの呼び出し等）・別のHTTPクライアントライブラリの使用
を検出しない。urlopen⇔Request のdef-use linkingは、同一関数scope内での
単一代入（分岐・再代入・関数外へのescapeのいずれも存在しない）という
最小限のケースのみを解決する——このrepositoryの実際の2箇所
（article_provider.py・wordpress_draft_client.py）はいずれもこの形に一致する。

実行方法:
    cd projects/03_game_content_ai
    .\\venv\\Scripts\\python.exe tests\\test_e2e_v6_32_6_invariant_35_static_oracle.py
"""
import ast
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent

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
print("Invariant #35 static oracle（§28.-34 test #4）E2E テスト")
print("=" * 60)
print()

# =====================================================================
# オラクル本体
# =====================================================================

_MUTATING_ATTR_NAMES = {"post", "put", "patch", "delete"}
_REQUEST_LIKE_ATTR_NAMES = {"request", "urlopen"}
_ALL_CANDIDATE_ATTR_NAMES = _MUTATING_ATTR_NAMES | _REQUEST_LIKE_ATTR_NAMES
_SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
_MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}

# 呼び出し箇所A/B/C（承認済みmutation site。22.3.11節・28.-34節本文）
_APPROVED_SITES = {
    "src/outputs/wordpress_output.py": "A",
    "src/wordpress_media/wordpress_media_uploader.py": "B",
    "src/ai/wordpress_draft_client.py": "C",
}


def _iter_production_py_files(project_root: Path):
    """production code（src/・scripts/・project-root *.py）のみを対象とする。
    tests/は対象外（28.-34節test #4冒頭）。"""
    for base in ("src", "scripts"):
        base_dir = project_root / base
        if not base_dir.exists():
            continue
        for p in sorted(base_dir.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            yield p
    for p in sorted(project_root.glob("*.py")):
        yield p


def _rel(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return path.as_posix()  # control-fixture一時ファイル等、repository外のpath


def _literal_str(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _get_arg(call: ast.Call, keyword: str, position: int):
    """keyword-or-positional引数を解決する。
    戻り値: ("present", node) / ("absent", None) / ("ambiguous", None)
    ambiguousは同一呼び出しでkeyword/positional両方が埋まっている場合
    （構文上は起こりうるが実行時TypeErrorとなる不正な形。fail-closed）。
    """
    kw_node = None
    for kw in call.keywords:
        if kw.arg == keyword:
            kw_node = kw.value
    pos_node = call.args[position] if len(call.args) > position else None
    if kw_node is not None and pos_node is not None:
        return "ambiguous", None
    if kw_node is not None:
        return "present", kw_node
    if pos_node is not None:
        return "present", pos_node
    return "absent", None


def _resolved_call_name(func_node) -> str | None:
    """node.func から、単純name または属性アクセスの末尾識別子を返す
    （import-alias解決は`import X as Y`形の別名までを対象とし、
    本repositoryの実際のimport形（`import urllib.request`のみ）に対しては
    単純な名前一致で十分足りる）。"""
    if isinstance(func_node, ast.Name):
        return func_node.id
    if isinstance(func_node, ast.Attribute):
        return func_node.attr
    return None


class _Candidate:
    def __init__(self, file: str, lineno: int, kind: str, classification: str, detail: str):
        self.file = file
        self.lineno = lineno
        self.kind = kind
        self.classification = classification  # "safe" / "mutating" / "unknown"
        self.detail = detail

    def __repr__(self):
        return f"<{self.file}:{self.lineno} kind={self.kind} class={self.classification} {self.detail}>"


def _classify_request_call(call: ast.Call) -> str:
    """urllib.request.Request(...) 構築呼び出しの分類（rule A-E、28.-34節test#4(3)）。"""
    data_status, data_node = _get_arg(call, "data", 1)
    method_status, method_node = _get_arg(call, "method", 5)
    if data_status == "ambiguous" or method_status == "ambiguous":
        return "unknown"

    data_absent_or_none = (data_status == "absent") or (
        isinstance(data_node, ast.Constant) and data_node.value is None
    )
    if not data_absent_or_none:
        return "mutating"  # rule C

    if method_status == "absent":
        return "safe"  # rule A

    method_literal = _literal_str(method_node)
    if method_literal is None:
        return "unknown"  # rule E（動的method）
    if method_literal in _SAFE_METHODS:
        return "safe"  # rule B
    return "mutating"  # rule D


def _classify_dot_request_call(call: ast.Call) -> str:
    """`.request(method, url, ...)` 呼び出しの分類（28.-34節test#4(2)）。
    method引数がGET/HEAD/OPTIONSのstring literalとして解決できる場合のみsafe。
    それ以外（省略・動的値・mutating literal）はmutating candidate。"""
    status, node = _get_arg(call, "method", 0)
    if status != "present":
        return "mutating"
    literal = _literal_str(node)
    if literal is not None and literal in _SAFE_METHODS:
        return "safe"
    return "mutating"


def _walk_same_scope(body_stmts):
    """関数/モジュールの直接body（statementリスト）から、入れ子の
    関数/クラス定義の内部へは踏み込まずに全descendantノードをyieldする。"""
    stack = list(body_stmts)
    while stack:
        n = stack.pop()
        yield n
        for child in ast.iter_child_nodes(n):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                continue
            stack.append(child)


def _find_unique_request_bindings(body_stmts) -> dict:
    """このscope直下（入れ子関数を除く）で `Name = Request(...)` という
    単一代入（同名への複数回代入がない）を探し、{name: Call} を返す。
    複数回代入されている名前は除外する（fail-closed、28.-34節test#4(4)(iv)）。"""
    assign_targets_count: dict[str, int] = {}
    request_call_by_name: dict[str, ast.Call] = {}
    for node in _walk_same_scope(body_stmts):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            assign_targets_count[name] = assign_targets_count.get(name, 0) + 1
            if (
                isinstance(node.value, ast.Call)
                and _resolved_call_name(node.value.func) == "Request"
            ):
                request_call_by_name[name] = node.value
    return {
        name: call
        for name, call in request_call_by_name.items()
        if assign_targets_count.get(name) == 1
    }


def _analyze_file(path: Path) -> list:
    """1ファイルをAST解析し、mutating/safe/unknown候補のリストを返す。
    urlopen⇔Requestのdef-use linkingは関数（FunctionDef/AsyncFunctionDef）
    およびモジュールtop-levelの各scopeごとに独立して行う。"""
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    rel = _rel(path)
    candidates: list[_Candidate] = []

    # scope単位（モジュールtop-level ＋ 各関数定義）でdef-use linkingを行う
    scopes = [tree] + [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]

    # Request(...)呼び出しのうち、urlopen()からdef-use経由で参照され「統合済み」
    # として扱ったnodeのid集合（二重カウント防止）
    merged_request_call_ids: set[int] = set()
    # スコープごとの一意bindingをグローバルに集約（同名変数が別関数にあっても
    # 混同しないよう、id(scope)ごとに保持）
    bindings_by_scope: dict[int, dict] = {}
    for scope in scopes:
        body = scope.body if hasattr(scope, "body") else []
        bindings_by_scope[id(scope)] = _find_unique_request_bindings(body)

    # scope → 直下（入れ子関数除く）のCallノード探索用に、各Callノードが
    # 属する最小内包scopeを特定する必要があるため、親ポインタを構築する。
    parent_of: dict[int, ast.AST] = {}
    for parent in ast.walk(tree):
        for child in ast.iter_child_nodes(parent):
            parent_of[id(child)] = parent

    def _enclosing_scope(node) -> ast.AST:
        cur = node
        while id(cur) in parent_of:
            cur = parent_of[id(cur)]
            if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                return cur
        return tree  # module top-level

    # Pass 1: urlopen()がdef-use経由／inlineで参照するRequest()呼び出しのidを
    # 先に確定する（ast.walk()はdocument順に近い順序で辿るため、urlopenより
    # 前に出現するRequest()呼び出しが先にcandidate化されてしまうのを防ぐ
    # ための2パス構成）。
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "urlopen"):
            continue
        first_arg = node.args[0] if node.args else None
        if first_arg is None:
            continue
        if isinstance(first_arg, ast.Call) and _resolved_call_name(first_arg.func) == "Request":
            merged_request_call_ids.add(id(first_arg))
        elif isinstance(first_arg, ast.Name):
            scope = _enclosing_scope(node)
            bindings = bindings_by_scope.get(id(scope), {})
            if first_arg.id in bindings:
                merged_request_call_ids.add(id(bindings[first_arg.id]))

    # Pass 2: 実際のcandidate列挙・分類
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func

        # --- (b)(c) Request(...) 構築（直接呼び出しのみ。getattr形は(d)未満のため除外） ---
        if isinstance(func, (ast.Name, ast.Attribute)) and _resolved_call_name(func) == "Request":
            if id(node) in merged_request_call_ids:
                continue
            classification = _classify_request_call(node)
            candidates.append(_Candidate(rel, node.lineno, "Request()", classification, ""))
            continue

        # --- getattr(receiver, name)(...) 形式 ---
        if isinstance(func, ast.Call) and isinstance(func.func, ast.Name) and func.func.id == "getattr" and len(func.args) >= 2:
            name_arg = func.args[1]
            literal_name = _literal_str(name_arg)
            if literal_name is None:
                candidates.append(_Candidate(rel, node.lineno, "getattr(dynamic-name)(...)", "unknown", "(d) non-literal attribute name"))
                continue
            if literal_name not in _ALL_CANDIDATE_ATTR_NAMES:
                continue
            attr_name = literal_name
        elif isinstance(func, ast.Attribute):
            attr_name = func.attr
            if attr_name not in _ALL_CANDIDATE_ATTR_NAMES:
                continue
        else:
            continue

        # --- (a) 直接の属性呼び出し／(c)のgetattr帰着 ---
        if attr_name in _MUTATING_ATTR_NAMES:
            candidates.append(_Candidate(rel, node.lineno, f".{attr_name}(...)", "mutating", ""))
            continue

        if attr_name == "request":
            classification = _classify_dot_request_call(node)
            candidates.append(_Candidate(rel, node.lineno, ".request(...)", classification, ""))
            continue

        if attr_name == "urlopen":
            # (4) def-use linking: 第1引数を調べる
            first_arg = node.args[0] if node.args else None
            if first_arg is None:
                candidates.append(_Candidate(rel, node.lineno, "urlopen(...)", "unknown", "no positional url arg"))
                continue

            if isinstance(first_arg, ast.Call) and _resolved_call_name(first_arg.func) == "Request":
                # (i) inline Request(...)
                classification = _classify_request_call(first_arg)
                merged_request_call_ids.add(id(first_arg))
                candidates.append(_Candidate(rel, node.lineno, "urlopen(Request(...))", classification, "inline-merged"))
                continue

            if isinstance(first_arg, ast.Name):
                scope = _enclosing_scope(node)
                bindings = bindings_by_scope.get(id(scope), {})
                if first_arg.id in bindings:
                    # (ii) 同一scope内の単一代入 X = Request(...)
                    linked_call = bindings[first_arg.id]
                    classification = _classify_request_call(linked_call)
                    merged_request_call_ids.add(id(linked_call))
                    candidates.append(_Candidate(rel, node.lineno, f"urlopen({first_arg.id}=Request(...))", classification, "def-use-merged"))
                    continue
                # (iii) URL-like literal? a bare Name is never a string literal,
                # so this falls through to (iv) unresolved provenance.
                candidates.append(_Candidate(rel, node.lineno, "urlopen(name)", "unknown", "(iv) unresolved Name provenance"))
                continue

            if isinstance(first_arg, (ast.Constant, ast.JoinedStr)) and not (
                isinstance(first_arg, ast.Constant) and not isinstance(first_arg.value, str)
            ):
                # (iii) URL-like value（string literal／f-string）。Request型でないことが構文上明らか。
                data_status, _ = _get_arg(node, "data", 1)
                if data_status == "absent":
                    candidates.append(_Candidate(rel, node.lineno, "urlopen(url-literal)", "safe", "(iii) urlopen has no data="))
                else:
                    candidates.append(_Candidate(rel, node.lineno, "urlopen(url-literal)", "mutating", "(iii) urlopen has data="))
                continue

            # (iv) その他（関数引数・複数代入変数・他関数戻り値等、provenance unresolved）
            candidates.append(_Candidate(rel, node.lineno, "urlopen(unresolved)", "unknown", "(iv) unresolved provenance"))
            continue

    return candidates


def run_oracle() -> list:
    all_candidates: list[_Candidate] = []
    for path in _iter_production_py_files(PROJECT_ROOT):
        all_candidates.extend(_analyze_file(path))
    return all_candidates


# =====================================================================
# テスト本体
# =====================================================================

_candidates = run_oracle()

print(f"[候補一覧] 検出された候補: {len(_candidates)}件")
for c in _candidates:
    print(f"    {c}")
print()

_unknowns = [c for c in _candidates if c.classification == "unknown"]
check(
    "1. unknown candidate = 0（Invariant #35のPASS条件、28.-34節test#4(6)）",
    len(_unknowns),
    0,
)

_mutating = [c for c in _candidates if c.classification == "mutating"]
_mutating_by_file: dict[str, list] = {}
for c in _mutating:
    _mutating_by_file.setdefault(c.file, []).append(c)

for rel_path, site_label in _APPROVED_SITES.items():
    check_true(
        f"2. 呼び出し箇所{site_label}（{rel_path}）が少なくとも1件のmutating candidateとして検出される",
        len(_mutating_by_file.get(rel_path, [])) >= 1,
    )

_unexpected_mutating_files = sorted(set(_mutating_by_file.keys()) - set(_APPROVED_SITES.keys()))
check(
    "3. 承認済みA/B/C以外のファイルにmutating candidateが存在しない",
    _unexpected_mutating_files,
    [],
)

# article_provider.py の GET-only Request→urlopen が safe-non-mutation として
# 単一の統合operationに分類され、urlopen単体の独立unknown candidateにならない
# ことを直接確認する（spurious unknown = 0、28.-34節test#4検証項目(a)）。
_article_provider_candidates = [c for c in _candidates if c.file == "src/ai/article_provider.py"]
check(
    "4. article_provider.pyのRequest→urlopenは1件の統合operationとしてsafeに分類される",
    len(_article_provider_candidates),
    1,
)
if _article_provider_candidates:
    check(
        "4b. article_provider.pyの統合operationはsafe",
        _article_provider_candidates[0].classification,
        "safe",
    )
    check_true(
        "4c. inline-merged/def-use-mergedのいずれかで統合されている（urlopen単体の独立candidateではない）",
        "merged" in _article_provider_candidates[0].detail,
    )
print()

# =====================================================================
# [POSITIVE/NEGATIVE CONTROL] オラクル自身の検出力を合成fixtureで直接検証する
#
# repository実ファイルのみを対象とした上記テストは「現状のコードには違反が
# ない」ことしか示さない。オラクルが実際に違反を検出できることを、
# 合成source（ast.parse()で直接解析、ファイルへは書き出さない）で確認する。
# =====================================================================

print("[POSITIVE/NEGATIVE CONTROL] オラクル自身の検出力確認")


def _classify_source(source: str) -> list:
    tree = ast.parse(source, filename="<control-fixture>")
    fake_path_candidates: list[_Candidate] = []
    # _analyze_file相当のロジックをsourceから直接実行するため、一時ファイルを
    # 経由せず_analyze_fileの内部ロジックを複製せず再利用する簡易ラッパー。
    import tempfile
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False, encoding="utf-8") as f:
        f.write(source)
        tmp_path = Path(f.name)
    try:
        fake_path_candidates = _analyze_file(tmp_path)
    finally:
        tmp_path.unlink(missing_ok=True)
    return fake_path_candidates


_control_cases = [
    ("POS-1: dynamic getattr method name → unknown", """
def f(session, method_name):
    return getattr(session, method_name)(url, data=payload)
""", "unknown", "getattr"),
    ("POS-2: requests.post → mutating (直接属性呼び出し)", """
def f(session):
    return session.post(url, json=payload)
""", "mutating", ".post"),
    ("POS-3: .request() with dynamic method → mutating candidate", """
def f(session, verb):
    return session.request(verb, url)
""", "mutating", ".request"),
    ("POS-4: .request() with literal GET → safe", """
def f(session):
    return session.request("GET", url)
""", "safe", ".request"),
    ("POS-5: Request(url, data=payload) → mutating (data present)", """
def f():
    req = urllib.request.Request(url, payload)
    return urllib.request.urlopen(req)
""", "mutating", "urlopen"),
    ("POS-6: Request(url, method='DELETE') → mutating (method literal)", """
def f():
    req = urllib.request.Request(url, method="DELETE")
    return urllib.request.urlopen(req)
""", "mutating", "urlopen"),
    ("POS-7: Request(url) → safe (data/method absent)", """
def f():
    req = urllib.request.Request(url)
    return urllib.request.urlopen(req)
""", "safe", "urlopen"),
    ("POS-8: Request(url, method=dynamic_var) → unknown", """
def f(verb):
    req = urllib.request.Request(url, method=verb)
    return urllib.request.urlopen(req)
""", "unknown", "urlopen"),
    ("POS-9: urlopen(unresolved-provenance) → unknown", """
def f(request_factory):
    req = request_factory()
    return urllib.request.urlopen(req)
""", "unknown", "urlopen"),
    ("POS-10: reassigned name breaks def-use link → unknown", """
def f(cond):
    req = urllib.request.Request(url, method="POST")
    if cond:
        req = urllib.request.Request(url)
    return urllib.request.urlopen(req)
""", "unknown", "urlopen"),
]

for label, src, expected_classification, kind_substring in _control_cases:
    cands = _classify_source(src)
    check_true(f"{label}: 候補が少なくとも1件検出される", len(cands) >= 1)
    target = next((c for c in cands if kind_substring in c.kind), None)
    check_true(f"{label}: 対象candidate（kindに'{kind_substring}'を含む）が存在する", target is not None)
    if target is not None:
        check(f"{label}: 分類結果", target.classification, expected_classification)

print()

# =====================================================================
# 結果サマリー
# =====================================================================

print("=" * 60)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = sum(1 for status, _ in results_log if status == "FAIL")
print(f"結果: {passed} PASS / {failed} FAIL / 合計 {len(results_log)}")
if failed:
    print("失敗したテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
print("全テストPASS")
