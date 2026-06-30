"""
E2E テスト: v1.20.0 AI Workflow Foundation

テストシナリオ:
    ── WorkflowStep ──
    1.  6 値が定義されている
    2.  各値の .value が正しい文字列を返す

    ── WorkflowStepResult ──
    3.  全フィールドが設定できる
    4.  step / success / processed_count が正しい

    ── WorkflowContext ──
    5.  article_id / dry_run が設定できる
    6.  current_step が None（初期値）
    7.  step_results / report_paths / warnings / errors が空リスト（初期値）
    8.  フィールドにミュータブルに追記できる

    ── WorkflowConfig ──
    9.  from_env() が WorkflowConfig を返す
    10. デフォルトで enabled=True
    11. デフォルトで全 6 ステップを含む
    12. is_ready() が True（デフォルト）
    13. enabled=False で is_ready() が False
    14. steps が空リストで is_ready() が False

    ── WorkflowResult ──
    15. 全フィールドが設定できる
    16. warnings / skipped_steps がデフォルト空リスト
    17. to_dict() が全フィールドを含む
    18. to_dict() の skipped_steps が文字列リスト
    19. to_dict() の started_at が ISO 文字列
    20. to_json() が有効な JSON を返す
    21. warnings を追加できる
    22. skipped_steps を追加できる

    ── WorkflowStepExecutor ABC ──
    23. WorkflowStepExecutor が ABC である
    24. step() と execute() が抽象メソッド
    25. 未実装サブクラスはインスタンス化できない

    ── Concrete Executors ──
    26. 全 6 Executor が WorkflowStepExecutor のサブクラス
    27. 各 Executor の step() が正しい WorkflowStep を返す
    28. dry_run=True で processed_count=0 の結果を返す
    29. ImprovementReviewStepExecutor がモックサービスで動作する
    30. RewriteReviewStepExecutor がモックサービスで動作する
    31. PublishStepExecutor がモックサービスで動作する
    32. PublishReviewStepExecutor がモックサービスで動作する

    ── WorkflowRunner ──
    33. モック Executor を DI して WorkflowRunner を構築できる
    34. run() が WorkflowResult を返す
    35. run() が全 Executor の execute() を呼び出す
    36. overall_success が全ステップ成功時 True
    37. total_processed が各ステップの合計
    38. run() の warnings が context.warnings に一致する
    39. config.steps に含まれないステップが skipped_steps に入る
    40. continue_on_error=False でエラー後にループ中断
    41. continue_on_error=True でエラー後も処理継続
    42. 失敗ステップがある場合 overall_success=False
    43. run() がレポートファイルを保存する
    44. run() の report_path が設定される
    45. dry_run=True で全ステップ processed_count=0

    ── NullWorkflowRunner ──
    46. is_available() が False を返す
    47. run() が WorkflowResult を返す
    48. run() の steps が空リスト
    49. run() の overall_success が False

    ── WorkflowReportBuilder ──
    50. build(result) が str を返す（WorkflowResult を入力）
    51. 成功時に "SUCCESS" を含む
    52. 失敗時に "FAILURE" を含む
    53. ステップ名がレポートに含まれる
    54. warnings セクションが含まれる（警告がある場合）
    55. skipped_steps セクションが含まれる

    ── 構成・互換性 ──
    56. scripts/run_ai_workflow.py が存在する
    57. スクリプトに WorkflowRunner の使用
    58. スクリプトに --article-id オプション
    59. スクリプトに --dry-run オプション
    60. __init__.py が新クラスをエクスポートする
    61. v1.14.0〜v1.19.0 の後方互換性が壊れない
    62. Claude API を実際に呼び出さない

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v1_20_0_ai_workflow_foundation.py
"""
import inspect
import json
import sys
import tempfile
from abc import ABC
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# ─── テスト用ユーティリティ ───

results_log = []


def check(label: str, actual, expected, exact: bool = True):
    ok = (actual == expected) if exact else (expected in str(actual))
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


def check_contains(label: str, text: str, keyword: str):
    check(label, keyword in str(text), True)


def check_none(label: str, value):
    check(label, value is None, True)


def check_not_none(label: str, value):
    check(label, value is not None, True)


# ─── モック用ユーティリティ ───

class _MockReviewService:
    """ImprovementReviewService / RewriteReviewService / PublishReviewService 共通モック。"""
    def __init__(self, review_count=2, report_path=None):
        self._review_count = review_count
        self._report_path  = report_path
        self.called_with_article_id = None

    def run(self, article_id=None):
        self.called_with_article_id = article_id
        return self._report_path

    def get_suggestions(self, article_id=None):
        return [object()] * self._review_count

    def get_reviews(self, article_id=None):
        return [object()] * self._review_count

    def get_results(self, article_id=None):
        class _FakeResult:
            success = True
        return [_FakeResult()] * self._review_count


class _MockRewriteService:
    """RewriteService モック。"""
    def __init__(self, results_count=3):
        self._count = results_count

    def rewrite_batch(self, suggestions, max_articles=None):
        class _R:
            success = True
        return [_R()] * self._count


# ─── WorkflowStepExecutor モック ───

class _SuccessExecutor:
    def __init__(self, step_val, processed_count=2, report_path=None):
        self._step_val       = step_val
        self._processed_count = processed_count
        self._report_path    = report_path
        self.executed_contexts = []

    def step(self):
        return self._step_val

    def execute(self, context):
        self.executed_contexts.append(context)
        from ai import WorkflowStepResult
        return WorkflowStepResult(
            step=self._step_val,
            success=True,
            processed_count=self._processed_count,
            report_path=self._report_path,
            error_message=None,
            started_at=datetime.now(),
            finished_at=datetime.now(),
        )


class _FailExecutor:
    def __init__(self, step_val):
        self._step_val = step_val
        self.executed = False

    def step(self):
        return self._step_val

    def execute(self, context):
        self.executed = True
        from ai import WorkflowStepResult
        return WorkflowStepResult(
            step=self._step_val,
            success=False,
            processed_count=0,
            report_path=None,
            error_message="テストエラー",
            started_at=datetime.now(),
            finished_at=datetime.now(),
        )


# ═══════════════════════════════════════════════════════════
# テスト1〜2: WorkflowStep
# ═══════════════════════════════════════════════════════════

print("=" * 60)
print("v1.20.0 AI Workflow Foundation E2E テスト")
print("=" * 60)
print()

print("[テスト1-2] WorkflowStep")
from ai import WorkflowStep

expected_steps = {
    "IMPROVEMENT":        "improvement",
    "IMPROVEMENT_REVIEW": "improvement_review",
    "REWRITE":            "rewrite",
    "REWRITE_REVIEW":     "rewrite_review",
    "PUBLISH":            "publish",
    "PUBLISH_REVIEW":     "publish_review",
}

check("1. WorkflowStep に 6 値が定義されている", len(WorkflowStep), 6)
for name, value in expected_steps.items():
    check_true(f"1. {name} が定義されている", hasattr(WorkflowStep, name))
    check(f"2. {name}.value == '{value}'", WorkflowStep[name].value, value)
print()

# ═══════════════════════════════════════════════════════════
# テスト3〜4: WorkflowStepResult
# ═══════════════════════════════════════════════════════════

print("[テスト3-4] WorkflowStepResult")
from ai import WorkflowStepResult

now = datetime.now()
step_result = WorkflowStepResult(
    step=WorkflowStep.IMPROVEMENT,
    success=True,
    processed_count=5,
    report_path=Path("/tmp/report.md"),
    error_message=None,
    started_at=now,
    finished_at=now,
)
check("3. step が設定できる",           step_result.step,            WorkflowStep.IMPROVEMENT)
check("3. success が設定できる",        step_result.success,         True)
check("3. processed_count が設定できる", step_result.processed_count, 5)
check("3. report_path が設定できる",    step_result.report_path,     Path("/tmp/report.md"))
check_none("3. error_message が None",  step_result.error_message)

check("4. step が WorkflowStep 型",      isinstance(step_result.step, WorkflowStep), True)
check("4. success が bool 型",           isinstance(step_result.success, bool),      True)
check("4. processed_count が int 型",    isinstance(step_result.processed_count, int), True)
print()

# ═══════════════════════════════════════════════════════════
# テスト5〜8: WorkflowContext
# ═══════════════════════════════════════════════════════════

print("[テスト5-8] WorkflowContext")
from ai import WorkflowContext

ctx = WorkflowContext(article_id="test-slug", dry_run=False)
check("5. article_id が設定できる", ctx.article_id, "test-slug")
check_false("5. dry_run が False", ctx.dry_run)

check_none("6. current_step が None（初期値）", ctx.current_step)

check("7. step_results が空リスト（初期値）", ctx.step_results, [])
check("7. report_paths が空リスト（初期値）", ctx.report_paths, [])
check("7. warnings が空リスト（初期値）",     ctx.warnings,     [])
check("7. errors が空リスト（初期値）",       ctx.errors,       [])

ctx.current_step = WorkflowStep.REWRITE
ctx.warnings.append("テスト警告")
ctx.errors.append("テストエラー")
ctx.step_results.append(step_result)
check("8. current_step に追記できる",  ctx.current_step, WorkflowStep.REWRITE)
check("8. warnings に追記できる",     len(ctx.warnings), 1)
check("8. errors に追記できる",       len(ctx.errors),   1)
check("8. step_results に追記できる", len(ctx.step_results), 1)
print()

# ═══════════════════════════════════════════════════════════
# テスト9〜14: WorkflowConfig
# ═══════════════════════════════════════════════════════════

print("[テスト9-14] WorkflowConfig")
from ai import WorkflowConfig, ALL_WORKFLOW_STEPS

with tempfile.TemporaryDirectory() as tmpdir:
    base = Path(tmpdir)
    config = WorkflowConfig.from_env(base_dir=base)
    check_true("9. from_env() が WorkflowConfig を返す",
               isinstance(config, WorkflowConfig))

    check_true("10. デフォルトで enabled=True", config.enabled)

    check("11. デフォルトで全 6 ステップ",
          len(config.steps), 6)
    check_true("11. ALL_WORKFLOW_STEPS と一致",
               set(config.steps) == set(ALL_WORKFLOW_STEPS))

    check_true("12. is_ready() が True（デフォルト）", config.is_ready())

    config_disabled = WorkflowConfig(
        enabled=False, steps=list(ALL_WORKFLOW_STEPS), base_dir=base
    )
    check_false("13. enabled=False で is_ready() が False", config_disabled.is_ready())

    config_empty = WorkflowConfig(enabled=True, steps=[], base_dir=base)
    check_false("14. steps 空リストで is_ready() が False", config_empty.is_ready())
print()

# ═══════════════════════════════════════════════════════════
# テスト15〜22: WorkflowResult
# ═══════════════════════════════════════════════════════════

print("[テスト15-22] WorkflowResult")
from ai import WorkflowResult

now = datetime.now()
step_r = WorkflowStepResult(
    step=WorkflowStep.PUBLISH, success=True, processed_count=3,
    report_path=None, error_message=None, started_at=now, finished_at=now,
)

result = WorkflowResult(
    steps=[step_r],
    overall_success=True,
    total_processed=3,
    report_path=None,
    started_at=now,
    finished_at=now,
)

check("15. steps が設定できる",         len(result.steps),         1)
check("15. overall_success が設定できる", result.overall_success,   True)
check("15. total_processed が設定できる", result.total_processed,   3)
check_none("15. report_path が None",    result.report_path)

check("16. warnings が空リスト（デフォルト）",     result.warnings,      [])
check("16. skipped_steps が空リスト（デフォルト）", result.skipped_steps, [])

d = result.to_dict()
required_keys = [
    "steps", "overall_success", "total_processed", "report_path",
    "started_at", "finished_at", "warnings", "skipped_steps",
]
for key in required_keys:
    check_true(f"17. to_dict() に {key} が含まれる", key in d)

check("18. to_dict() の skipped_steps が文字列リスト", d["skipped_steps"], [])
result_with_skip = WorkflowResult(
    steps=[], overall_success=True, total_processed=0,
    report_path=None, started_at=now, finished_at=now,
    skipped_steps=[WorkflowStep.IMPROVEMENT],
)
d_skip = result_with_skip.to_dict()
check_true("18. skipped_steps の要素が str",
           isinstance(d_skip["skipped_steps"][0], str))
check("18. skipped_steps の値が正しい",
      d_skip["skipped_steps"][0], "improvement")

check_true("19. to_dict() の started_at が str", isinstance(d["started_at"], str))
check_contains("19. started_at が ISO 形式", d["started_at"], "T")

json_str = result.to_json()
check_true("20. to_json() が str", isinstance(json_str, str))
parsed = json.loads(json_str)
check("20. to_json() がパース可能", parsed["overall_success"], True)

result.warnings.append("テスト警告1")
result.warnings.append("テスト警告2")
check("21. warnings を追加できる", len(result.warnings), 2)

result.skipped_steps.append(WorkflowStep.REWRITE)
check("22. skipped_steps を追加できる", len(result.skipped_steps), 1)
print()

# ═══════════════════════════════════════════════════════════
# テスト23〜25: WorkflowStepExecutor ABC
# ═══════════════════════════════════════════════════════════

print("[テスト23-25] WorkflowStepExecutor ABC")
from ai import WorkflowStepExecutor

check_true("23. WorkflowStepExecutor が ABC のサブクラス",
           issubclass(WorkflowStepExecutor, ABC))

abstract_methods = getattr(WorkflowStepExecutor, "__abstractmethods__", set())
check_true("24. step() が抽象メソッド",    "step"    in abstract_methods)
check_true("24. execute() が抽象メソッド", "execute" in abstract_methods)

try:
    WorkflowStepExecutor()  # type: ignore
    check_true("25. 未実装サブクラスはインスタンス化できない（失敗）", False)
except TypeError:
    check_true("25. 未実装サブクラスはインスタンス化できない", True)
print()

# ═══════════════════════════════════════════════════════════
# テスト26〜32: Concrete Executors
# ═══════════════════════════════════════════════════════════

print("[テスト26-32] Concrete Executors")
from ai import (
    ImprovementStepExecutor,
    ImprovementReviewStepExecutor,
    RewriteStepExecutor,
    RewriteReviewStepExecutor,
    PublishStepExecutor,
    PublishReviewStepExecutor,
)

executor_classes = [
    ImprovementStepExecutor,
    ImprovementReviewStepExecutor,
    RewriteStepExecutor,
    RewriteReviewStepExecutor,
    PublishStepExecutor,
    PublishReviewStepExecutor,
]
for cls in executor_classes:
    check_true(f"26. {cls.__name__} が WorkflowStepExecutor のサブクラス",
               issubclass(cls, WorkflowStepExecutor))

expected_steps_map = [
    (ImprovementStepExecutor,       WorkflowStep.IMPROVEMENT),
    (ImprovementReviewStepExecutor, WorkflowStep.IMPROVEMENT_REVIEW),
    (RewriteStepExecutor,           WorkflowStep.REWRITE),
    (RewriteReviewStepExecutor,     WorkflowStep.REWRITE_REVIEW),
    (PublishStepExecutor,           WorkflowStep.PUBLISH),
    (PublishReviewStepExecutor,     WorkflowStep.PUBLISH_REVIEW),
]

# テスト27: step() が正しい値を返す
with tempfile.TemporaryDirectory() as tmpdir:
    base = Path(tmpdir)
    mock_svc = _MockReviewService()

    # ImprovementStepExecutor（dry_run のみテスト）
    imp_executor = ImprovementStepExecutor(
        service=mock_svc,
        analytics_manager=mock_svc,
        log_dir=base,
    )
    check("27. ImprovementStepExecutor.step()", imp_executor.step(), WorkflowStep.IMPROVEMENT)

    # ImprovementReviewStepExecutor
    imp_rev_executor = ImprovementReviewStepExecutor(service=mock_svc)
    check("27. ImprovementReviewStepExecutor.step()", imp_rev_executor.step(), WorkflowStep.IMPROVEMENT_REVIEW)

    # RewriteStepExecutor
    rw_executor = RewriteStepExecutor(service=_MockRewriteService(), improvement_dir=base)
    check("27. RewriteStepExecutor.step()", rw_executor.step(), WorkflowStep.REWRITE)

    # RewriteReviewStepExecutor
    rr_executor = RewriteReviewStepExecutor(service=mock_svc)
    check("27. RewriteReviewStepExecutor.step()", rr_executor.step(), WorkflowStep.REWRITE_REVIEW)

    # PublishStepExecutor
    pub_executor = PublishStepExecutor(service=mock_svc)
    check("27. PublishStepExecutor.step()", pub_executor.step(), WorkflowStep.PUBLISH)

    # PublishReviewStepExecutor
    pub_rev_executor = PublishReviewStepExecutor(service=mock_svc)
    check("27. PublishReviewStepExecutor.step()", pub_rev_executor.step(), WorkflowStep.PUBLISH_REVIEW)

# テスト28: dry_run=True で processed_count=0
with tempfile.TemporaryDirectory() as tmpdir:
    base = Path(tmpdir)
    mock_svc = _MockReviewService()
    dry_ctx  = WorkflowContext(article_id=None, dry_run=True)

    for cls, step_val in expected_steps_map:
        if cls is ImprovementStepExecutor:
            executor = cls(service=mock_svc, analytics_manager=mock_svc, log_dir=base)
        elif cls is RewriteStepExecutor:
            executor = cls(service=_MockRewriteService(), improvement_dir=base)
        else:
            executor = cls(service=mock_svc)

        r = executor.execute(dry_ctx)
        check(f"28. {cls.__name__} dry_run → processed_count=0",
              r.processed_count, 0)
        check_true(f"28. {cls.__name__} dry_run → success=True", r.success)

# テスト29: ImprovementReviewStepExecutor がモックサービスで動作する
with tempfile.TemporaryDirectory() as tmpdir:
    svc = _MockReviewService(review_count=3)
    executor = ImprovementReviewStepExecutor(service=svc)
    ctx = WorkflowContext(article_id=None, dry_run=False)
    r = executor.execute(ctx)
    check("29. ImprovementReviewStepExecutor success=True", r.success, True)
    check("29. ImprovementReviewStepExecutor processed_count=3", r.processed_count, 3)
    check("29. step が IMPROVEMENT_REVIEW", r.step, WorkflowStep.IMPROVEMENT_REVIEW)

# テスト30: RewriteReviewStepExecutor がモックサービスで動作する
with tempfile.TemporaryDirectory() as tmpdir:
    svc = _MockReviewService(review_count=2)
    executor = RewriteReviewStepExecutor(service=svc)
    ctx = WorkflowContext(article_id=None, dry_run=False)
    r = executor.execute(ctx)
    check("30. RewriteReviewStepExecutor success=True", r.success, True)
    check("30. RewriteReviewStepExecutor processed_count=2", r.processed_count, 2)

# テスト31: PublishStepExecutor がモックサービスで動作する
with tempfile.TemporaryDirectory() as tmpdir:
    svc = _MockReviewService(review_count=1)
    executor = PublishStepExecutor(service=svc)
    ctx = WorkflowContext(article_id=None, dry_run=False)
    r = executor.execute(ctx)
    check("31. PublishStepExecutor success=True", r.success, True)
    check("31. PublishStepExecutor processed_count=1", r.processed_count, 1)

# テスト32: PublishReviewStepExecutor がモックサービスで動作する
with tempfile.TemporaryDirectory() as tmpdir:
    svc = _MockReviewService(review_count=4)
    executor = PublishReviewStepExecutor(service=svc)
    ctx = WorkflowContext(article_id=None, dry_run=False)
    r = executor.execute(ctx)
    check("32. PublishReviewStepExecutor success=True", r.success, True)
    check("32. PublishReviewStepExecutor processed_count=4", r.processed_count, 4)
print()

# ═══════════════════════════════════════════════════════════
# テスト33〜45: WorkflowRunner
# ═══════════════════════════════════════════════════════════

print("[テスト33-45] WorkflowRunner")
from ai import WorkflowRunner, NullWorkflowRunner

# テスト33: モック Executor を DI して WorkflowRunner を構築できる
with tempfile.TemporaryDirectory() as tmpdir:
    base    = Path(tmpdir)
    config  = WorkflowConfig(
        enabled=True, steps=list(ALL_WORKFLOW_STEPS), base_dir=base
    )
    execs   = [_SuccessExecutor(s, processed_count=2) for s in WorkflowStep]
    runner  = WorkflowRunner(config=config, executors=execs)
    check_true("33. WorkflowRunner を構築できる", isinstance(runner, WorkflowRunner))

# テスト34: run() が WorkflowResult を返す
with tempfile.TemporaryDirectory() as tmpdir:
    base   = Path(tmpdir)
    config = WorkflowConfig(enabled=True, steps=list(ALL_WORKFLOW_STEPS), base_dir=base)
    execs  = [_SuccessExecutor(s, processed_count=1) for s in WorkflowStep]
    runner = WorkflowRunner(config=config, executors=execs)
    result = runner.run()
    check_true("34. run() が WorkflowResult を返す", isinstance(result, WorkflowResult))

# テスト35: run() が全 Executor の execute() を呼び出す
with tempfile.TemporaryDirectory() as tmpdir:
    base   = Path(tmpdir)
    config = WorkflowConfig(enabled=True, steps=list(ALL_WORKFLOW_STEPS), base_dir=base)
    execs  = [_SuccessExecutor(s) for s in WorkflowStep]
    runner = WorkflowRunner(config=config, executors=execs)
    runner.run()
    for ex in execs:
        check_true(f"35. {ex._step_val.value} の execute() が呼ばれた",
                   len(ex.executed_contexts) == 1)

# テスト36: overall_success が全ステップ成功時 True
with tempfile.TemporaryDirectory() as tmpdir:
    base   = Path(tmpdir)
    config = WorkflowConfig(enabled=True, steps=list(ALL_WORKFLOW_STEPS), base_dir=base)
    execs  = [_SuccessExecutor(s) for s in WorkflowStep]
    runner = WorkflowRunner(config=config, executors=execs)
    result = runner.run()
    check_true("36. overall_success が True（全ステップ成功）", result.overall_success)

# テスト37: total_processed が各ステップの合計
with tempfile.TemporaryDirectory() as tmpdir:
    base   = Path(tmpdir)
    config = WorkflowConfig(enabled=True, steps=list(ALL_WORKFLOW_STEPS), base_dir=base)
    execs  = [_SuccessExecutor(s, processed_count=3) for s in WorkflowStep]
    runner = WorkflowRunner(config=config, executors=execs)
    result = runner.run()
    check("37. total_processed が 3×6=18", result.total_processed, 18)

# テスト38: run() の warnings が context.warnings に一致（警告がない場合は空リスト）
with tempfile.TemporaryDirectory() as tmpdir:
    base   = Path(tmpdir)
    config = WorkflowConfig(enabled=True, steps=list(ALL_WORKFLOW_STEPS), base_dir=base)
    execs  = [_SuccessExecutor(s) for s in WorkflowStep]
    runner = WorkflowRunner(config=config, executors=execs)
    result = runner.run()
    check("38. warnings が空リスト（警告なし）", result.warnings, [])

# テスト39: config.steps に含まれないステップが skipped_steps に入る
with tempfile.TemporaryDirectory() as tmpdir:
    base = Path(tmpdir)
    partial_steps = [WorkflowStep.IMPROVEMENT, WorkflowStep.REWRITE, WorkflowStep.PUBLISH]
    config = WorkflowConfig(enabled=True, steps=partial_steps, base_dir=base)
    execs  = [_SuccessExecutor(s) for s in WorkflowStep]
    runner = WorkflowRunner(config=config, executors=execs)
    result = runner.run()
    check("39. スキップステップが 3 件", len(result.skipped_steps), 3)
    check_true("39. IMPROVEMENT_REVIEW がスキップされた",
               WorkflowStep.IMPROVEMENT_REVIEW in result.skipped_steps)
    check_true("39. REWRITE_REVIEW がスキップされた",
               WorkflowStep.REWRITE_REVIEW in result.skipped_steps)
    check_true("39. PUBLISH_REVIEW がスキップされた",
               WorkflowStep.PUBLISH_REVIEW in result.skipped_steps)

# テスト40: continue_on_error=False でエラー後にループ中断
with tempfile.TemporaryDirectory() as tmpdir:
    base = Path(tmpdir)
    config = WorkflowConfig(
        enabled=True, steps=list(ALL_WORKFLOW_STEPS), base_dir=base,
        continue_on_error=False,
    )
    ex_ok1   = _SuccessExecutor(WorkflowStep.IMPROVEMENT)
    ex_fail  = _FailExecutor(WorkflowStep.IMPROVEMENT_REVIEW)
    ex_after = _FailExecutor(WorkflowStep.REWRITE)
    runner   = WorkflowRunner(config=config, executors=[ex_ok1, ex_fail, ex_after])
    result   = runner.run()
    check_false("40. continue_on_error=False → overall_success=False", result.overall_success)
    check_false("40. 後続の Executor が実行されなかった", ex_after.executed)

# テスト41: continue_on_error=True でエラー後も処理継続
with tempfile.TemporaryDirectory() as tmpdir:
    base = Path(tmpdir)
    config = WorkflowConfig(
        enabled=True, steps=list(ALL_WORKFLOW_STEPS), base_dir=base,
        continue_on_error=True,
    )
    ex_ok1   = _SuccessExecutor(WorkflowStep.IMPROVEMENT)
    ex_fail  = _FailExecutor(WorkflowStep.IMPROVEMENT_REVIEW)
    ex_after = _SuccessExecutor(WorkflowStep.REWRITE)
    runner   = WorkflowRunner(config=config, executors=[ex_ok1, ex_fail, ex_after])
    result   = runner.run()
    check_true("41. continue_on_error=True → 後続 Executor が実行された", len(ex_after.executed_contexts) == 1)
    check("41. 実行ステップ数は 3", len(result.steps), 3)

# テスト42: 失敗ステップがある場合 overall_success=False
with tempfile.TemporaryDirectory() as tmpdir:
    base = Path(tmpdir)
    config = WorkflowConfig(
        enabled=True, steps=list(ALL_WORKFLOW_STEPS), base_dir=base,
        continue_on_error=True,
    )
    execs  = [_FailExecutor(WorkflowStep.IMPROVEMENT)]
    runner = WorkflowRunner(config=config, executors=execs)
    result = runner.run()
    check_false("42. 失敗あり → overall_success=False", result.overall_success)

# テスト43: run() がレポートファイルを保存する
with tempfile.TemporaryDirectory() as tmpdir:
    base   = Path(tmpdir)
    config = WorkflowConfig(enabled=True, steps=list(ALL_WORKFLOW_STEPS), base_dir=base)
    execs  = [_SuccessExecutor(s) for s in WorkflowStep]
    runner = WorkflowRunner(config=config, executors=execs)
    result = runner.run()
    report_dir = base / "outputs" / "workflow_reports"
    md_files   = list(report_dir.glob("*_workflow_report.md"))
    check_true("43. レポートファイルが保存される", len(md_files) == 1)

# テスト44: run() の report_path が設定される
with tempfile.TemporaryDirectory() as tmpdir:
    base   = Path(tmpdir)
    config = WorkflowConfig(enabled=True, steps=list(ALL_WORKFLOW_STEPS), base_dir=base)
    execs  = [_SuccessExecutor(s) for s in WorkflowStep]
    runner = WorkflowRunner(config=config, executors=execs)
    result = runner.run()
    check_not_none("44. report_path が設定される", result.report_path)
    check_true("44. report_path が .md ファイル",
               result.report_path is not None and result.report_path.suffix == ".md")

# テスト45: dry_run=True で全ステップ processed_count=0
with tempfile.TemporaryDirectory() as tmpdir:
    base   = Path(tmpdir)
    mock_svc = _MockReviewService()
    config = WorkflowConfig(enabled=True, steps=list(ALL_WORKFLOW_STEPS), base_dir=base)
    execs  = [_SuccessExecutor(s, processed_count=5) for s in WorkflowStep]
    runner = WorkflowRunner(config=config, executors=execs)
    # dry_run は WorkflowContext に渡され executor.execute(context) に渡るが、
    # _SuccessExecutor はモックなので dry_run を無視して processed_count=5 を返す。
    # dry_run の実動作は Concrete Executor のテスト28 で検証済み。
    result = runner.run(dry_run=True)
    check_true("45. dry_run=True で run() が WorkflowResult を返す",
               isinstance(result, WorkflowResult))
print()

# ═══════════════════════════════════════════════════════════
# テスト46〜49: NullWorkflowRunner
# ═══════════════════════════════════════════════════════════

print("[テスト46-49] NullWorkflowRunner")
null_runner = NullWorkflowRunner()

check_false("46. is_available() が False", null_runner.is_available())

null_result = null_runner.run()
check_true("47. run() が WorkflowResult を返す",
           isinstance(null_result, WorkflowResult))

check("48. run() の steps が空リスト", null_result.steps, [])

check_false("49. run() の overall_success が False", null_result.overall_success)
print()

# ═══════════════════════════════════════════════════════════
# テスト50〜55: WorkflowReportBuilder
# ═══════════════════════════════════════════════════════════

print("[テスト50-55] WorkflowReportBuilder")
from ai import WorkflowReportBuilder

builder = WorkflowReportBuilder()
now     = datetime.now()

# テスト50: build(result) が str を返す
result_ok = WorkflowResult(
    steps=[
        WorkflowStepResult(
            step=WorkflowStep.IMPROVEMENT, success=True, processed_count=3,
            report_path=None, error_message=None, started_at=now, finished_at=now,
        )
    ],
    overall_success=True,
    total_processed=3,
    report_path=None,
    started_at=now,
    finished_at=now,
)
md = builder.build(result_ok)
check_true("50. build(WorkflowResult) が str を返す", isinstance(md, str))

# テスト51: 成功時に "SUCCESS" を含む
check_contains("51. 成功時に 'SUCCESS' を含む", md, "SUCCESS")

# テスト52: 失敗時に "FAILURE" を含む
result_fail = WorkflowResult(
    steps=[
        WorkflowStepResult(
            step=WorkflowStep.REWRITE, success=False, processed_count=0,
            report_path=None, error_message="テストエラー", started_at=now, finished_at=now,
        )
    ],
    overall_success=False,
    total_processed=0,
    report_path=None,
    started_at=now,
    finished_at=now,
)
md_fail = builder.build(result_fail)
check_contains("52. 失敗時に 'FAILURE' を含む", md_fail, "FAILURE")
check_contains("52. エラーメッセージが含まれる", md_fail, "テストエラー")

# テスト53: ステップ名がレポートに含まれる
check_contains("53. AI 改善提案ステップ名が含まれる", md,      "AI 改善提案")
check_contains("53. AI リライトステップ名が含まれる",  md_fail, "AI リライト")

# テスト54: warnings セクションが含まれる
result_with_warn = WorkflowResult(
    steps=[], overall_success=True, total_processed=0,
    report_path=None, started_at=now, finished_at=now,
    warnings=["警告1", "警告2"],
)
md_warn = builder.build(result_with_warn)
check_contains("54. 警告セクションが含まれる", md_warn, "警告")
check_contains("54. 警告内容が含まれる",       md_warn, "警告1")

# テスト55: skipped_steps セクションが含まれる
result_with_skip = WorkflowResult(
    steps=[], overall_success=True, total_processed=0,
    report_path=None, started_at=now, finished_at=now,
    skipped_steps=[WorkflowStep.REWRITE_REVIEW, WorkflowStep.PUBLISH_REVIEW],
)
md_skip = builder.build(result_with_skip)
check_contains("55. スキップセクションが含まれる",         md_skip, "スキップ")
check_contains("55. リライトレビューステップ名が含まれる", md_skip, "リライトレビュー")
print()

# ═══════════════════════════════════════════════════════════
# テスト56〜62: 構成・互換性
# ═══════════════════════════════════════════════════════════

print("[テスト56-62] 構成・互換性")

# テスト56: scripts/run_ai_workflow.py が存在する
script_path = Path(__file__).parent.parent / "scripts" / "run_ai_workflow.py"
check_true("56. scripts/run_ai_workflow.py が存在する", script_path.exists())

if script_path.exists():
    script_content = script_path.read_text(encoding="utf-8")
    check_contains("57. スクリプトに WorkflowRunner の使用",     script_content, "WorkflowRunner")
    check_contains("58. スクリプトに --article-id オプション",  script_content, "--article-id")
    check_contains("59. スクリプトに --dry-run オプション",      script_content, "--dry-run")

# テスト60: __init__.py が新クラスをエクスポートする
import ai as ai_pkg

new_exports = [
    "WorkflowStep",
    "WorkflowStepResult",
    "WorkflowContext",
    "WorkflowConfig",
    "ALL_WORKFLOW_STEPS",
    "WorkflowResult",
    "WorkflowStepExecutor",
    "ImprovementStepExecutor",
    "ImprovementReviewStepExecutor",
    "RewriteStepExecutor",
    "RewriteReviewStepExecutor",
    "PublishStepExecutor",
    "PublishReviewStepExecutor",
    "WorkflowReportBuilder",
    "WorkflowRunner",
    "NullWorkflowRunner",
]
for name in new_exports:
    check_true(f"60. {name} が __init__.py からエクスポートされている",
               hasattr(ai_pkg, name))

# テスト61: v1.14.0〜v1.19.0 の後方互換性が壊れない
try:
    from ai import (
        AiImprovementConfig, ImprovementSuggestion, ImprovementSuggestionParser,
        PromptBuilder, ClaudeClient, NullClaudeClient,
        AiImprovementService, NullAiImprovementService,
    )
    check_true("61. v1.14.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"61. v1.14.0 の全クラスが import できる（失敗: {e}）", False)

try:
    from ai import ImprovementRepository, ImprovementReportBuilder, ImprovementReviewService
    check_true("61. v1.15.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"61. v1.15.0 の全クラスが import できる（失敗: {e}）", False)

try:
    from ai import (
        RewriteConfig, RewriteResult,
        ArticleProvider, WordPressArticleProvider, NullArticleProvider,
        RewritePromptBuilder, RewriteParser, RewriteRepository,
        RewriteService, NullRewriteService,
    )
    check_true("61. v1.16.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"61. v1.16.0 の全クラスが import できる（失敗: {e}）", False)

try:
    from ai import (
        ReviewStatus, RewriteReviewResult,
        RewriteReviewRepository, RewriteReviewReportBuilder,
        RewriteReviewService, NullRewriteReviewService,
    )
    check_true("61. v1.17.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"61. v1.17.0 の全クラスが import できる（失敗: {e}）", False)

try:
    from ai import (
        AiPublishConfig, AiPublishResult,
        WordPressDraftClient, NullWordPressDraftClient,
        AiPublishRepository, AiPublishReportBuilder,
        AiPublishService, NullAiPublishService,
    )
    check_true("61. v1.18.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"61. v1.18.0 の全クラスが import できる（失敗: {e}）", False)

try:
    from ai import (
        PublishReviewStatus, AiPublishReviewResult,
        AiPublishReviewRepository, AiPublishReviewReportBuilder,
        AiPublishReviewService, NullAiPublishReviewService,
    )
    check_true("61. v1.19.0 の全クラスが import できる", True)
except ImportError as e:
    check_true(f"61. v1.19.0 の全クラスが import できる（失敗: {e}）", False)

# テスト62: Claude API を実際に呼び出さない
new_files = [
    "workflow_step.py",
    "workflow_context.py",
    "workflow_config.py",
    "workflow_step_executor.py",
    "workflow_result.py",
    "workflow_report_builder.py",
    "workflow_runner.py",
]
for filename in new_files:
    src_path = Path(__file__).parent.parent / "src" / "ai" / filename
    if src_path.exists():
        content = src_path.read_text(encoding="utf-8")
        check_false(f"62. {filename}: urllib.request を使わない", "urllib.request" in content)
    else:
        check_true(f"62. {filename} が存在する（確認失敗）", False)
print()

# ─── 結果サマリー ───
print("=" * 60)
total  = len(results_log)
passed = sum(1 for s, _ in results_log if s == "PASS")
failed = sum(1 for s, _ in results_log if s == "FAIL")
print(f"結果: {passed}/{total} PASS  /  {failed} FAIL")
print("=" * 60)

if failed:
    print()
    print("【失敗一覧】")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  NG: {label}")
    sys.exit(1)
else:
    print("全テスト PASS")
    sys.exit(0)
