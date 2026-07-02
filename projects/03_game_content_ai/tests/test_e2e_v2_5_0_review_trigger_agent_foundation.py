"""
E2E テスト: v2.5.0 Review Trigger Agent Foundation

テストシナリオ:
    ── ReviewTriggerAgentConfig ──
    1.  from_env() のデフォルト値（enabled=False / min_interval_minutes=1440 / is_ready()=False）
    2.  REVIEW_TRIGGER_AGENT_ENABLED=true の環境変数上書き（二重ゲート、enabled=Trueのみで is_ready()=True）
    3.  REVIEW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES の環境変数上書き

    ── ReviewTriggerAgent.decide()（副作用なし）──
    4.  reports_dir が存在しない → should_act=True
    5.  reports_dir はあるが *.md ファイルなし → should_act=True
    6.  古い *.md ファイルのみ（間隔超過）→ should_act=True
    7.  新しい *.md ファイルあり（間隔内）→ should_act=False
    8.  新旧混在時は最新mtimeを優先する

    ── ReviewTriggerAgent.act() ──
    9.  ReviewPipelineRunner.run() のみを呼ぶ（params をそのまま渡す）
    10. PipelineResult成功時に AgentResult.success=True
    11. PipelineResult失敗時に AgentResult.success=False
    12. error_message が None の場合はフォールバック文言が使われる
    13. act() で workflow_result が常に None（成功時・失敗時とも）
    14. dry_run=True でのact()直接呼び出しはAssertionErrorになる

    ── ReviewPipelineRunner（AiPublishReviewService はモック）──
    15. AiPublishReviewService.from_paths が base_dir=config.project_root で呼ばれる
    16. service.run が article_id付きで呼ばれる
    17. report_pathが返る → PipelineResult.success=True
    18. report_path=None → PipelineResult.success=False（固定文言）
    19. service.get_reviews も article_id付きで呼ばれる（読み戻し確認）
    20. params=None時は article_id=None で service.run が呼ばれる
    21. from_paths() が例外を投げても success=False
    22. service.run() が例外を投げても success=False
    23. returncode / stdout_log_path / stderr_log_path は常に None
    24. 実際の AiPublishReviewService インスタンスは生成されない（from_pathsを丸ごとモック置換）

    ── AgentManager DI（二重ゲート）──
    25. REVIEW_TRIGGER_AGENT_ENABLED未設定 → NewsAgentのみ
    26. 二重ゲートを満たす → NewsAgent + ReviewTriggerAgent
    27. AI_AGENT_ENABLED=false → NullAgentManager
    28. News/Workflow/Publish/Review の4Agentすべてが有効 → 4件登録（既存3Agent登録に影響なし）

    ── scripts/run_review_trigger_agent.py（実サブプロセス、常にdry-run）──
    29. スクリプトファイルが存在する
    30. AI_AGENT_ENABLED=false --dry-run で安全に終了する
    31. REVIEW_TRIGGER_AGENT_ENABLED未設定 --dry-run では NewsAgentのみ実行される
    32. 二重ゲートON --dry-run --article-id で review_trigger_agent が実行され、
        かつ act() はスキップされる（outputs/ai_publish_review_reports/ に
        新規ファイルが作られないことで実証）
    33. run_review_trigger_agent.py が AiPublishReviewService を直接importしない（静的検査）

    ── Architecture Guard ──
    34. AiPublishReviewService本体・既存Agent
        （NewsAgent/WorkflowTriggerAgent/PublishTriggerAgent）に変更がない（git diff）
    35. review_trigger_agent.py / review_pipeline_runner.py の禁止import静的検査（まとめ）
    36. src/ai/__init__.py / src/pipeline/__init__.py からのexport確認

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v2_5_0_review_trigger_agent_foundation.py
"""
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

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


print("=" * 60)
print("v2.5.0 Review Trigger Agent Foundation E2E テスト")
print("=" * 60)
print()

from ai.review_trigger_agent_config import ReviewTriggerAgentConfig
from ai.review_trigger_agent import (
    ReviewTriggerAgent,
    REASON_NO_PREVIOUS_REPORT,
    REASON_INTERVAL_EXCEEDED,
    REASON_INTERVAL_NOT_EXCEEDED,
)
from ai.ai_publish_review_service import AiPublishReviewService
from ai.workflow_trigger_agent import WorkflowTriggerAgent
from ai.publish_trigger_agent import PublishTriggerAgent
from pipeline.pipeline_result import PipelineResult
from pipeline.review_pipeline_runner import ReviewPipelineRunner
from ai import (
    AgentContext, AgentDecision, AgentResult, AgentTask, AgentExecutor,
    AgentConfig, AgentManager, NullAgentManager, NewsAgent,
)

WORKFLOW_TRIGGER_ENV_KEYS = (
    "WORKFLOW_TRIGGER_AGENT_ENABLED",
    "WORKFLOW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES",
    "AI_WORKFLOW_ENABLED",
)
PUBLISH_TRIGGER_ENV_KEYS = (
    "PUBLISH_TRIGGER_AGENT_ENABLED",
    "PUBLISH_TRIGGER_AGENT_MIN_INTERVAL_MINUTES",
    "AI_PUBLISH_ENABLED",
    "WORDPRESS_URL",
    "WORDPRESS_USERNAME",
    "WORDPRESS_APP_PASSWORD",
)
REVIEW_TRIGGER_ENV_KEYS = (
    "REVIEW_TRIGGER_AGENT_ENABLED",
    "REVIEW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES",
)


def clear_review_trigger_env():
    for key in REVIEW_TRIGGER_ENV_KEYS:
        os.environ.pop(key, None)


def clear_all_trigger_env():
    for key in WORKFLOW_TRIGGER_ENV_KEYS + PUBLISH_TRIGGER_ENV_KEYS + REVIEW_TRIGGER_ENV_KEYS:
        os.environ.pop(key, None)


# ═══════════════════════════════════════════════════════════
# テスト1-3: ReviewTriggerAgentConfig
# ═══════════════════════════════════════════════════════════

print("[テスト1-3] ReviewTriggerAgentConfig.from_env()")

clear_review_trigger_env()
fake_root = Path(tempfile.mkdtemp())

cfg1 = ReviewTriggerAgentConfig.from_env(project_root=fake_root)
check_false("1. デフォルト enabled=False", cfg1.enabled)
check("1. デフォルト min_interval_minutes=1440", cfg1.min_interval_minutes, 1440)
check("1. reports_dir が project_root/outputs/ai_publish_review_reports", cfg1.reports_dir, fake_root / "outputs" / "ai_publish_review_reports")
check("1. project_root が渡した値と一致", cfg1.project_root, fake_root)
check_false("1. デフォルトは is_ready()=False（enabled=Falseのため）", cfg1.is_ready())

os.environ["REVIEW_TRIGGER_AGENT_ENABLED"] = "true"
cfg2 = ReviewTriggerAgentConfig.from_env(project_root=fake_root)
check_true("2. REVIEW_TRIGGER_AGENT_ENABLED=true で enabled=True", cfg2.enabled)
check_true("2. 二重ゲートのため enabled=True のみで is_ready()=True", cfg2.is_ready())
os.environ.pop("REVIEW_TRIGGER_AGENT_ENABLED", None)

os.environ["REVIEW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES"] = "60"
cfg3 = ReviewTriggerAgentConfig.from_env(project_root=fake_root)
check("3. 環境変数上書き min_interval_minutes=60", cfg3.min_interval_minutes, 60)
os.environ.pop("REVIEW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES", None)

clear_review_trigger_env()
print()


# ═══════════════════════════════════════════════════════════
# テスト4-8: ReviewTriggerAgent.decide()
# ═══════════════════════════════════════════════════════════

print("[テスト4-8] ReviewTriggerAgent.decide()")


def make_decide_agent(tmp_dir: Path, min_interval_minutes: int = 1440):
    cfg = ReviewTriggerAgentConfig(
        enabled=True,
        min_interval_minutes=min_interval_minutes,
        reports_dir=tmp_dir / "outputs" / "ai_publish_review_reports",
        project_root=tmp_dir,
    )
    mock_runner = MagicMock()
    return ReviewTriggerAgent(config=cfg, runner=mock_runner), mock_runner


def make_context(params=None, dry_run=False):
    return AgentContext(
        task=AgentTask(task_id="run_review", params=params or {}),
        dry_run=dry_run,
        run_id="test-run",
        agent_name="review_trigger_agent",
    )


# テスト4: reports_dir が存在しない
tmp4 = Path(tempfile.mkdtemp())
agent4d, mock_runner4d = make_decide_agent(tmp4)
decision4 = agent4d.decide(make_context())
check_true("4. reports_dirなし → should_act=True", decision4.should_act)
check("4. reasonが固定文言と一致", decision4.reason, REASON_NO_PREVIOUS_REPORT)
check("4. runner.run は呼ばれない（副作用なし）", mock_runner4d.run.call_count, 0)
check_false("4. reports_dirが作られていない（副作用なし）", (tmp4 / "outputs" / "ai_publish_review_reports").exists())

# テスト5: reports_dir はあるが *.md ファイルなし
tmp5 = Path(tempfile.mkdtemp())
reports_dir5 = tmp5 / "outputs" / "ai_publish_review_reports"
reports_dir5.mkdir(parents=True)
agent5d, mock_runner5d = make_decide_agent(tmp5)
decision5 = agent5d.decide(make_context())
check_true("5. ファイル0件 → should_act=True", decision5.should_act)
check("5. reasonが固定文言と一致", decision5.reason, REASON_NO_PREVIOUS_REPORT)
check("5. runner.run は呼ばれない（副作用なし）", mock_runner5d.run.call_count, 0)

# テスト6: 古い *.md ファイルのみ（min_interval=1分、1時間前のファイル）
tmp6 = Path(tempfile.mkdtemp())
reports_dir6 = tmp6 / "outputs" / "ai_publish_review_reports"
reports_dir6.mkdir(parents=True)
old_file6 = reports_dir6 / "20200101_ai_publish_review_report.md"
old_file6.write_text("old report", encoding="utf-8")
old_time6 = (datetime.now() - timedelta(hours=1)).timestamp()
os.utime(old_file6, (old_time6, old_time6))
agent6d, mock_runner6d = make_decide_agent(tmp6, min_interval_minutes=1)
decision6 = agent6d.decide(make_context())
check_true("6. 間隔超過 → should_act=True", decision6.should_act)
check("6. reasonが固定文言と一致", decision6.reason, REASON_INTERVAL_EXCEEDED)

# テスト7: 新しい *.md ファイルあり（min_interval=1440分、直近作成）
tmp7 = Path(tempfile.mkdtemp())
reports_dir7 = tmp7 / "outputs" / "ai_publish_review_reports"
reports_dir7.mkdir(parents=True)
new_file7 = reports_dir7 / "20260702_ai_publish_review_report.md"
new_file7.write_text("new report", encoding="utf-8")
agent7d, mock_runner7d = make_decide_agent(tmp7, min_interval_minutes=1440)
decision7 = agent7d.decide(make_context())
check_false("7. 間隔内 → should_act=False", decision7.should_act)
check("7. reasonが固定文言と一致", decision7.reason, REASON_INTERVAL_NOT_EXCEEDED)

# テスト8: 新旧混在時は最新mtimeを優先する
tmp8 = Path(tempfile.mkdtemp())
reports_dir8 = tmp8 / "outputs" / "ai_publish_review_reports"
reports_dir8.mkdir(parents=True)
old_file8 = reports_dir8 / "20200101_ai_publish_review_report.md"
old_file8.write_text("old", encoding="utf-8")
old_time8 = (datetime.now() - timedelta(days=30)).timestamp()
os.utime(old_file8, (old_time8, old_time8))
new_file8 = reports_dir8 / "20260702_ai_publish_review_report.md"
new_file8.write_text("new", encoding="utf-8")
agent8d, mock_runner8d = make_decide_agent(tmp8, min_interval_minutes=1440)
decision8 = agent8d.decide(make_context())
check_false("8. 新旧混在時は最新（新しい方）が優先される → should_act=False", decision8.should_act)
print()


# ═══════════════════════════════════════════════════════════
# テスト9-14: ReviewTriggerAgent.act()
# ═══════════════════════════════════════════════════════════

print("[テスト9-14] ReviewTriggerAgent.act()")

act_tmp = Path(tempfile.mkdtemp())
act_cfg = ReviewTriggerAgentConfig(
    enabled=True, min_interval_minutes=1440,
    reports_dir=act_tmp / "outputs" / "ai_publish_review_reports",
    project_root=act_tmp,
)

# 成功時
mock_runner9 = MagicMock()
mock_runner9.run.return_value = PipelineResult(
    success=True, returncode=None, elapsed_sec=2.0,
    stdout_log_path=None, stderr_log_path=None, error_message=None,
)
agent9 = ReviewTriggerAgent(config=act_cfg, runner=mock_runner9)
ctx9 = make_context(params={"article_id": "ps6-announced-20260630"})
ctx9.started_at = datetime.now()
ctx9.finished_at = datetime.now()
decision9 = AgentDecision(should_act=True, reason=REASON_INTERVAL_EXCEEDED)
result9 = agent9.act(decision9, ctx9)

check("9. runner.run が1回だけ呼ばれる", mock_runner9.run.call_count, 1)
check(
    "9. runner.run が context.task.params をそのまま渡す",
    mock_runner9.run.call_args.kwargs["params"],
    {"article_id": "ps6-announced-20260630"},
)
check_true("10. AgentResult型が返る", isinstance(result9, AgentResult))
check_true("10. action_taken=True", result9.action_taken)
check_true("10. PipelineResult成功時に success=True", result9.success)
check_none("10. error_message が None（成功時）", result9.error_message)
check_none("13. workflow_result が None（成功時）", result9.workflow_result)
check_true("10. warningsに成功メッセージが含まれる", any("completed successfully" in w for w in result9.warnings))

# 失敗時
mock_runner11 = MagicMock()
mock_runner11.run.return_value = PipelineResult(
    success=False, returncode=None, elapsed_sec=1.0,
    stdout_log_path=None, stderr_log_path=None,
    error_message="Review report was not saved.",
)
agent11 = ReviewTriggerAgent(config=act_cfg, runner=mock_runner11)
ctx11 = make_context()
ctx11.started_at = datetime.now()
ctx11.finished_at = datetime.now()
result11 = agent11.act(AgentDecision(True, REASON_INTERVAL_EXCEEDED), ctx11)
check_false("11. PipelineResult失敗時に success=False", result11.success)
check(
    "11. error_message が PipelineResult.error_message と一致",
    result11.error_message,
    "Review report was not saved.",
)
check_none("13. workflow_result が None（失敗時も）", result11.workflow_result)

# 失敗時（error_messageがNoneの場合のフォールバック）
mock_runner12 = MagicMock()
mock_runner12.run.return_value = PipelineResult(
    success=False, returncode=None, elapsed_sec=1.0,
    stdout_log_path=None, stderr_log_path=None, error_message=None,
)
agent12 = ReviewTriggerAgent(config=act_cfg, runner=mock_runner12)
ctx12 = make_context()
ctx12.started_at = datetime.now()
ctx12.finished_at = datetime.now()
result12 = agent12.act(AgentDecision(True, REASON_INTERVAL_EXCEEDED), ctx12)
check_not_none("12. error_messageがNoneの場合はフォールバック文言が使われる", result12.error_message)

# dry_run=True でのact()直接呼び出し
ctx14 = make_context(dry_run=True)
try:
    agent9.act(AgentDecision(True, REASON_INTERVAL_EXCEEDED), ctx14)
    check_true("14. dry_run=Trueでのact()直接呼び出しはAssertionErrorになる", False)
except AssertionError:
    check_true("14. dry_run=Trueでのact()直接呼び出しはAssertionErrorになる", True)
print()


# ═══════════════════════════════════════════════════════════
# テスト15-24: ReviewPipelineRunner
# ═══════════════════════════════════════════════════════════

print("[テスト15-24] ReviewPipelineRunner")

runner_tmp = Path(tempfile.mkdtemp())


class FakeRunnerConfig:
    project_root = runner_tmp


report_path15 = runner_tmp / "outputs" / "ai_publish_review_reports" / "20260702_ai_publish_review_report.md"
mock_service15 = MagicMock()
mock_service15.run.return_value = report_path15
mock_service15.get_reviews.return_value = [MagicMock(), MagicMock()]

with patch.object(AiPublishReviewService, "from_paths", return_value=mock_service15) as mock_from_paths15:
    rpr15 = ReviewPipelineRunner(FakeRunnerConfig())
    result15 = rpr15.run(params={"article_id": "ps6-announced-20260630"})

check("15. AiPublishReviewService.from_paths が base_dir=config.project_root で呼ばれる",
      mock_from_paths15.call_args.kwargs["base_dir"], runner_tmp)
check("16. service.run が article_id付きで呼ばれる",
      mock_service15.run.call_args.kwargs, {"article_id": "ps6-announced-20260630"})
check_true("17. report_pathが返る → PipelineResult.success=True", result15.success)
check_none("17. error_message が None（成功時）", result15.error_message)
check("19. service.get_reviews が article_id付きで呼ばれる（読み戻し確認）",
      mock_service15.get_reviews.call_args.kwargs, {"article_id": "ps6-announced-20260630"})
check_true("15. elapsed_sec が0以上（壁時計で計測）", result15.elapsed_sec >= 0)

mock_service18 = MagicMock()
mock_service18.run.return_value = None
mock_service18.get_reviews.return_value = []
with patch.object(AiPublishReviewService, "from_paths", return_value=mock_service18):
    rpr18 = ReviewPipelineRunner(FakeRunnerConfig())
    result18 = rpr18.run(params={})
check_false("18. report_path=None → PipelineResult.success=False", result18.success)
check("18. error_messageが固定文言", result18.error_message, "Review report was not saved.")

mock_service20 = MagicMock()
mock_service20.run.return_value = report_path15
mock_service20.get_reviews.return_value = []
with patch.object(AiPublishReviewService, "from_paths", return_value=mock_service20):
    rpr20 = ReviewPipelineRunner(FakeRunnerConfig())
    result20 = rpr20.run(params=None)
check("20. params=None時は article_id=None で service.run が呼ばれる",
      mock_service20.run.call_args.kwargs, {"article_id": None})

with patch.object(AiPublishReviewService, "from_paths", side_effect=RuntimeError("from_paths boom")):
    rpr21 = ReviewPipelineRunner(FakeRunnerConfig())
    result21 = rpr21.run(params={})
check_false("21. from_paths() が例外を投げても success=False", result21.success)
check("21. error_message に例外文言", result21.error_message, "from_paths boom")

mock_service22 = MagicMock()
mock_service22.run.side_effect = RuntimeError("service.run boom")
with patch.object(AiPublishReviewService, "from_paths", return_value=mock_service22):
    rpr22 = ReviewPipelineRunner(FakeRunnerConfig())
    result22 = rpr22.run(params={})
check_false("22. service.run() が例外を投げても success=False", result22.success)
check("22. error_message に例外文言", result22.error_message, "service.run boom")

for label, r in (("成功時", result15), ("失敗時", result18), ("例外時", result21)):
    check_none(f"23. returncode が None（{label}）", r.returncode)
    check_none(f"23. stdout_log_path が None（{label}）", r.stdout_log_path)
    check_none(f"23. stderr_log_path が None（{label}）", r.stderr_log_path)

with patch.object(AiPublishReviewService, "from_paths", return_value=mock_service15) as mock_from_paths24:
    rpr24 = ReviewPipelineRunner(FakeRunnerConfig())
    rpr24.run(params={"article_id": "dummy"})
check(
    "24. 本物の AiPublishReviewService インスタンスは一度も生成されない（from_pathsを丸ごと置換）",
    mock_from_paths24.call_count >= 1,
    True,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト25-28: AgentManager.from_config()（二重ゲート）
# ═══════════════════════════════════════════════════════════

print("[テスト25-28] AgentManager.from_config()（二重ゲート）")

manager_tmp = Path(tempfile.mkdtemp())

# テスト25: REVIEW_TRIGGER_AGENT_ENABLED未設定 → NewsAgentのみ
clear_all_trigger_env()
config25 = AgentConfig(enabled=True, base_dir=manager_tmp)
manager25 = AgentManager.from_config(config25)
check_true("25. AgentManagerが返る", isinstance(manager25, AgentManager))
check("25. executorsが1件（NewsAgentのみ）", len(manager25._executors), 1)
check_true("25. executors[0]がNewsAgent", isinstance(manager25._executors[0]._agent, NewsAgent))

# テスト26: 二重ゲートを満たす → NewsAgent + ReviewTriggerAgent
clear_all_trigger_env()
os.environ["REVIEW_TRIGGER_AGENT_ENABLED"] = "true"
config26 = AgentConfig(enabled=True, base_dir=manager_tmp)
manager26 = AgentManager.from_config(config26)
check("26. executorsが2件", len(manager26._executors), 2)
check_true("26. executors[0]がNewsAgent", isinstance(manager26._executors[0]._agent, NewsAgent))
check_true("26. executors[1]がReviewTriggerAgent", isinstance(manager26._executors[1]._agent, ReviewTriggerAgent))
check_true(
    "26. ReviewTriggerAgentのrunnerがReviewPipelineRunner",
    isinstance(manager26._executors[1]._agent._runner, ReviewPipelineRunner),
)

# テスト27: AI_AGENT_ENABLED=false → NullAgentManager
clear_all_trigger_env()
config27 = AgentConfig(enabled=False, base_dir=manager_tmp)
manager27 = AgentManager.from_config(config27)
check_true("27. disabled → NullAgentManager が返る", isinstance(manager27, NullAgentManager))

# テスト28: News/Workflow/Publish/Review の4Agentすべてが有効
clear_all_trigger_env()
os.environ["WORKFLOW_TRIGGER_AGENT_ENABLED"] = "true"
os.environ["AI_WORKFLOW_ENABLED"] = "true"
os.environ["PUBLISH_TRIGGER_AGENT_ENABLED"] = "true"
os.environ["AI_PUBLISH_ENABLED"] = "true"
os.environ["WORDPRESS_URL"] = "https://example.com"
os.environ["WORDPRESS_USERNAME"] = "user"
os.environ["WORDPRESS_APP_PASSWORD"] = "app-password"
os.environ["REVIEW_TRIGGER_AGENT_ENABLED"] = "true"
config28 = AgentConfig(enabled=True, base_dir=manager_tmp)
manager28 = AgentManager.from_config(config28)
check("28. executorsが4件（NewsAgent + WorkflowTriggerAgent + PublishTriggerAgent + ReviewTriggerAgent）", len(manager28._executors), 4)
check_true("28. executors[0]がNewsAgent", isinstance(manager28._executors[0]._agent, NewsAgent))
check_true("28. executors[1]がWorkflowTriggerAgent", isinstance(manager28._executors[1]._agent, WorkflowTriggerAgent))
check_true("28. executors[2]がPublishTriggerAgent", isinstance(manager28._executors[2]._agent, PublishTriggerAgent))
check_true("28. executors[3]がReviewTriggerAgent", isinstance(manager28._executors[3]._agent, ReviewTriggerAgent))

clear_all_trigger_env()
print()


# ═══════════════════════════════════════════════════════════
# テスト29-33: scripts/run_review_trigger_agent.py（実サブプロセス、常にdry-run）
# ═══════════════════════════════════════════════════════════

print("[テスト29-33] scripts/run_review_trigger_agent.py")

script_path = PROJECT_ROOT / "scripts" / "run_review_trigger_agent.py"
check_true("29. run_review_trigger_agent.py が存在する", script_path.exists())

reports_dir_real = PROJECT_ROOT / "outputs" / "ai_publish_review_reports"
before_reports = set(reports_dir_real.glob("*")) if reports_dir_real.exists() else set()


def run_cli(extra_args, env_overrides):
    env = dict(os.environ)
    for key in (
        ("AI_AGENT_ENABLED",)
        + WORKFLOW_TRIGGER_ENV_KEYS
        + PUBLISH_TRIGGER_ENV_KEYS
        + REVIEW_TRIGGER_ENV_KEYS
    ):
        env.pop(key, None)
    env.update(env_overrides)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(script_path)] + extra_args,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=60,
    )


# テスト30: AI_AGENT_ENABLED=false --dry-run
completed30 = run_cli(["--dry-run"], {"AI_AGENT_ENABLED": "false"})
check("30. returncode が 0", completed30.returncode, 0)
check_contains("30. AI Agent基盤が無効の案内が表示される", completed30.stdout, "AI Agent基盤が無効です")

# テスト31: AI_AGENT_ENABLED=true / REVIEW_TRIGGER_AGENT_ENABLED未設定 --dry-run
completed31 = run_cli(["--dry-run"], {"AI_AGENT_ENABLED": "true"})
check("31. returncode が 0", completed31.returncode, 0)
check_false("31. review_trigger_agent は実行されない", "Agent: review_trigger_agent" in completed31.stdout)
check_contains("31. ReviewTriggerAgent未実行の案内メッセージが表示される", completed31.stdout, "ReviewTriggerAgent")

# テスト32: 二重ゲートON --dry-run --article-id
completed32 = run_cli(
    ["--dry-run", "--article-id", "sample-article"],
    {
        "AI_AGENT_ENABLED": "true",
        "REVIEW_TRIGGER_AGENT_ENABLED": "true",
    },
)
check("32. returncode が 0", completed32.returncode, 0)
check_contains("32. review_trigger_agent が実行される", completed32.stdout, "Agent: review_trigger_agent")
check_contains("32. article_id が反映される", completed32.stdout, "sample-article")
check_contains("32. action_taken=False（--dry-runによりact()がスキップされる）", completed32.stdout, "action_taken=False")

after_reports = set(reports_dir_real.glob("*")) if reports_dir_real.exists() else set()
check(
    "32. outputs/ai_publish_review_reports/ に新規ファイルが作られない（AiPublishReviewService未起動）",
    after_reports - before_reports,
    set(),
)

# テスト33: 静的import検査
script_source = script_path.read_text(encoding="utf-8")
script_import_lines = "\n".join(
    line for line in script_source.splitlines()
    if line.strip().startswith("from ") or line.strip().startswith("import ")
)
check_false(
    "33. run_review_trigger_agent.py の import文に AiPublishReviewService が含まれない",
    "AiPublishReviewService" in script_import_lines,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト34-36: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト34] 既存ファイルの無変更確認（git diff）")

unchanged_paths = [
    "main.py",
    "src/ai/ai_publish_review_service.py",
    "src/ai/ai_publish_review_repository.py",
    "src/ai/ai_publish_review_report_builder.py",
    "src/ai/ai_publish_review_result.py",
    "src/ai/ai_publish_service.py",
    "src/ai/ai_publish_config.py",
    "src/ai/workflow_runner.py",
    "src/ai/workflow_config.py",
    "src/ai/base_agent.py",
    "src/ai/agent_executor.py",
    "src/ai/agent_context.py",
    "src/ai/agent_decision.py",
    "src/ai/agent_result.py",
    "src/ai/agent_task.py",
    "src/ai/agent_config.py",
    "src/ai/news_agent.py",
    "src/ai/news_agent_config.py",
    "src/ai/workflow_trigger_agent.py",
    "src/ai/workflow_trigger_agent_config.py",
    "src/ai/publish_trigger_agent.py",
    "src/ai/publish_trigger_agent_config.py",
    "src/pipeline/news_pipeline_runner.py",
    "src/pipeline/workflow_pipeline_runner.py",
    "src/pipeline/publish_pipeline_runner.py",
    "src/pipeline/pipeline_result.py",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            timeout=10,
        )
        check_true(f"34. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("34. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト35] Architecture Guard（静的import検査、まとめ）")
rta_source = (PROJECT_ROOT / "src" / "ai" / "review_trigger_agent.py").read_text(encoding="utf-8")
rta_import_lines = "\n".join(
    line for line in rta_source.splitlines()
    if line.strip().startswith("from ") or line.strip().startswith("import ")
)
check_false(
    "35. review_trigger_agent.py の import文に AiPublishReviewService が含まれない（再掲）",
    "AiPublishReviewService" in rta_import_lines,
)
check_false(
    "35. review_trigger_agent.py の import文に AiPublishService が含まれない",
    "AiPublishService" in rta_import_lines,
)
check_false(
    "35. review_trigger_agent.py の import文に WorkflowRunner が含まれない",
    "WorkflowRunner" in rta_import_lines,
)

rpr_source = (PROJECT_ROOT / "src" / "pipeline" / "review_pipeline_runner.py").read_text(encoding="utf-8")
check_false("35. review_pipeline_runner.py が subprocess をimportしない", "import subprocess" in rpr_source)
check_false("35. review_pipeline_runner.py が subprocess.run を使わない", "subprocess.run" in rpr_source)
print()


print("[テスト36] import確認")

import ai as ai_pkg
for name in ("ReviewTriggerAgent", "ReviewTriggerAgentConfig"):
    check_true(f"36. {name} が ai パッケージからエクスポートされている", hasattr(ai_pkg, name))
    check_true(f"36. {name} が ai.__all__ に含まれる", name in ai_pkg.__all__)

import pipeline as pipeline_pkg
check_true(
    "36. ReviewPipelineRunner が pipeline パッケージからエクスポートされている",
    hasattr(pipeline_pkg, "ReviewPipelineRunner"),
)
check_true(
    "36. ReviewPipelineRunner が pipeline.__all__ に含まれる",
    "ReviewPipelineRunner" in pipeline_pkg.__all__,
)
print()


# ─── 結果サマリー ───
print("=" * 60)
total = len(results_log)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = total - passed
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
