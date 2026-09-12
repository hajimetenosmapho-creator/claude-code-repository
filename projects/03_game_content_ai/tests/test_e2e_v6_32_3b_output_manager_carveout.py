"""
E2E テスト: sub-milestone 3 completion gap — OutputManager.save_all() の
SideEffectExecutionModeContractError carve-out（22.3.13節(2)）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    22.3.13節(2)。

Approved Architecture上、呼び出し箇所A（NEWS WordPress draft）は
`OutputManager.save_all()`経由で到達する。`save_all()`の既存broad
`except Exception`は、output.save()が送出するあらゆる例外を
`SaveResult(success=False)`へ変換し、他出力先へcontinueする（既存・無変更の
設計方針）。本テストは、`SideEffectExecutionModeContractError`だけがこの
normalizationの対象外となり、そのまま呼び出し元へ伝播することを検証する。

実行方法:
    cd projects/03_game_content_ai
    .\\venv\\Scripts\\python.exe tests\\test_e2e_v6_32_3b_output_manager_carveout.py
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

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
print("sub-milestone 3 completion gap: OutputManager carve-out E2E テスト")
print("=" * 60)
print()

from outputs.manager import OutputManager  # noqa: E402
from outputs.base import ArticleData  # noqa: E402
from outputs.save_result import SaveResult  # noqa: E402
from collector import NewsItem  # noqa: E402
from publishing_config import PublishStatus  # noqa: E402
from side_effect_safety import (  # noqa: E402
    ExecutionModeFailureReasonCode,
    SideEffectExecutionModeContractError,
)


def make_article() -> ArticleData:
    item = NewsItem(
        title="t", url="https://x", summary="s", source="src",
        published_at="2026-07-18", image_candidates=[],
    )
    return ArticleData(
        item=item, importance="S", seo_title="t", article_body="b", x_post="x",
        slug="slug-1", publish_status=PublishStatus.DRAFT,
    )


class _ContractErrorOutput:
    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    def save(self, article):
        self.calls += 1
        raise SideEffectExecutionModeContractError(ExecutionModeFailureReasonCode.MISSING_EXECUTION_MODE)


class _RuntimeErrorOutput:
    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    def save(self, article):
        self.calls += 1
        raise RuntimeError("boom")


class _SuccessOutput:
    def __init__(self):
        self.calls = 0

    def is_available(self):
        return True

    def save(self, article):
        self.calls += 1
        return SaveResult(success=True, output_type="file")


# ─── [テスト1] contract errorはSaveResultへ変換されず伝播する ───

print("[テスト1] SideEffectExecutionModeContractErrorはSaveResultへ変換されず伝播する")

contract_output_1 = _ContractErrorOutput()
manager_1 = OutputManager([contract_output_1])

raised_1 = None
try:
    manager_1.save_all(make_article())
except SideEffectExecutionModeContractError as e:
    raised_1 = e
except Exception as e:
    raised_1 = e

check_true("1a. SideEffectExecutionModeContractErrorが送出される", isinstance(raised_1, SideEffectExecutionModeContractError))
check_true(
    "1b. 型がそのまま伝播する（一般的な例外へ変換されない）",
    type(raised_1) is SideEffectExecutionModeContractError,
)
print()


# ─── [テスト2] contract error発生時、後続の他出力先へcontinueしない（fail-fast） ───

print("[テスト2] contract error発生時は後続出力先のsave()が呼ばれない（fail-fast）")

contract_output_2 = _ContractErrorOutput()
after_output_2 = _SuccessOutput()
manager_2 = OutputManager([contract_output_2, after_output_2])

raised_2 = None
try:
    manager_2.save_all(make_article())
except SideEffectExecutionModeContractError as e:
    raised_2 = e

check_true("2a. 例外が伝播する", raised_2 is not None)
check("2b. 後続出力先のsave()は呼ばれない", after_output_2.calls, 0)
print()


# ─── [テスト3] 既存動作：通常の例外は引き続きSaveResult(success=False)へ変換される ───

print("[テスト3] 既存動作維持：一般的なExceptionは引き続きSaveResult(success=False)へ変換され、他出力先へcontinueする")

runtime_output_3 = _RuntimeErrorOutput()
after_output_3 = _SuccessOutput()
manager_3 = OutputManager([runtime_output_3, after_output_3])

results_3 = manager_3.save_all(make_article())

check("3a. 2件の結果が返る（RuntimeError出力もSaveResultとして記録される）", len(results_3), 2)
check("3b. 1件目はsuccess=False", results_3[0].success, False)
check_true("3c. 1件目のerror_messageに例外文言が含まれる", "boom" in (results_3[0].error_message or ""))
check("3d. 後続出力先のsave()は呼ばれる（既存continue動作を維持）", after_output_3.calls, 1)
check("3e. 2件目はsuccess=True", results_3[1].success, True)
print()


# ─── [テスト4] is_available()=Falseのoutputは引き続きスキップされる（zero-diff） ───

print("[テスト4] is_available()=Falseの出力先は引き続きスキップされる（既存動作、zero-diff確認）")


class _UnavailableOutput:
    def __init__(self):
        self.calls = 0

    def is_available(self):
        return False

    def save(self, article):
        self.calls += 1
        raise AssertionError("is_available()=Falseの出力先のsave()が呼ばれてはならない")


unavailable_4 = _UnavailableOutput()
success_4 = _SuccessOutput()
manager_4 = OutputManager([unavailable_4, success_4])
results_4 = manager_4.save_all(make_article())

check("4a. スキップされた出力先を除く1件のみ結果に含まれる", len(results_4), 1)
check("4b. スキップされた出力先のsave()は呼ばれない", unavailable_4.calls, 0)
print()


# ─── 結果サマリー ───

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
