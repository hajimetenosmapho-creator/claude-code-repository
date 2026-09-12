"""
E2E テスト: Release 6.32 sub-milestone 6D cluster 4b
Invariant #33 — 設計書中の擬似コードの構文的妥当性

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    28.-25節「Invariant #33」#1。

本設計書自身（side_effect_fail_closed_human_review_safety_foundation.md）内の
全```pythonコードフェンスを機械的に抽出し、各ブロックをtextwrap.dedent()した上で
ast.parse()（構文解析のみ、実行しない）を実行する、documentation-level static
syntax testである。オラクルは自己参照的——discovered_count（抽出されたブロック
総数）を実行のたびに動的に数え直し、特定時点のブロック総数を固定値として
埋め込まない（設計書の編集でブロック数が増減しても本テスト自体は無改修のまま
機能する）。

production側は変更しない（設計書自体を対象とするdocumentation-level test）。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_14_design_doc_pseudocode_syntax.py
"""
from __future__ import annotations

import ast
import re
import sys
import textwrap
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
DESIGN_DOC_PATH = PROJECT_ROOT / "docs" / "design" / "side_effect_fail_closed_human_review_safety_foundation.md"

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
print("Invariant #33 — 設計書擬似コードの構文的妥当性（28.-25節）E2E テスト")
print("=" * 60)
print()


# =====================================================================
# テスト1（オラクルは自己参照化）：
#   全```pythonコードフェンスを機械的に抽出し、ast.parse()で構文検証する
# =====================================================================

print("[テスト1] 設計書内の全```pythonコードフェンスを抽出し、ast.parse()で構文検証する"
      "（discovered_countは実行のたびに動的に数え直す）")

design_doc_text = DESIGN_DOC_PATH.read_text(encoding="utf-8")


def _extract_python_fences(text: str) -> list[str]:
    """```python ... ``` フェンスを行単位で抽出する。Markdownのlist item・
    blockquote内では、フェンス開始・終了マーカー自体が行頭空白を伴うことがある
    （例：`  \\`\\`\\`python` 〜 `  \\`\\`\\``）ため、開始マーカーの行頭空白量を
    記録し、終了マーカーは「同じ行頭空白量＋\\`\\`\\`のみ」で判定する
    （単純な`\\n\\`\\`\\``のみを終了条件とする素朴な正規表現は、インデントされた
    終了フェンスを見逃し、後続の無関係な別フェンスまで1ブロックとして誤結合
    してしまう）。"""
    lines = text.splitlines()
    blocks: list[str] = []
    i = 0
    open_pattern = re.compile(r"^(\s*)```python\s*$")
    while i < len(lines):
        m = open_pattern.match(lines[i])
        if not m:
            i += 1
            continue
        indent = m.group(1)
        close_pattern = re.compile(rf"^{re.escape(indent)}```\s*$")
        body_lines = []
        i += 1
        while i < len(lines) and not close_pattern.match(lines[i]):
            body_lines.append(lines[i])
            i += 1
        # i時点でclose_patternに一致する行（またはEOF）。一致した場合のみ
        # 正式なブロックとして採用する（未閉鎖フェンスは対象外＝本文の一部）。
        if i < len(lines):
            blocks.append("\n".join(body_lines))
            i += 1  # 終了フェンス行を消費
    return blocks


code_blocks = _extract_python_fences(design_doc_text)

discovered_count = len(code_blocks)
print(f"    discovered_count（実測）: {discovered_count}")
check_true("1. discovered_count > 0（```pythonフェンスが実際に検出される）", discovered_count > 0)

pass_count = 0
syntax_error_blocks: list[tuple[int, str]] = []
for idx, block in enumerate(code_blocks, start=1):
    # クラス本体を伴わない単独メソッド定義等、意図的にインデントされた部分snippetを
    # 単なるインデント起因のIndentationErrorで誤ってfailさせないため、
    # textwrap.dedent()してからast.parse()する。
    dedented = textwrap.dedent(block)
    try:
        ast.parse(dedented)
        pass_count += 1
    except SyntaxError as e:
        syntax_error_blocks.append((idx, f"{type(e).__name__}: {e}"))

print(f"    pass_count（実測）: {pass_count}")
if syntax_error_blocks:
    print("    SyntaxErrorが発生したブロック:")
    for idx, err in syntax_error_blocks:
        print(f"      block#{idx}: {err}")

check(
    "1. pass_count == discovered_count（SyntaxErrorが0件、設計書中の擬似コードは全て構文的に妥当）",
    pass_count, discovered_count,
)
check("1. SyntaxErrorが発生したブロック = 0件", syntax_error_blocks, [])
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
