"""
E2E テスト: v2.4.0 Publish Trigger Agent Foundation

テストシナリオ:
    ── PublishTriggerAgentConfig ──
    1.  from_env() のデフォルト値
    2.  PUBLISH_TRIGGER_AGENT_ENABLED=true の環境変数上書き（三重ゲート、2段目のみでは is_ready()=False）
    3.  PUBLISH_TRIGGER_AGENT_MIN_INTERVAL_MINUTES の環境変数上書き
    4.  AI_PUBLISH_ENABLED=false 時に publish_enabled=False（三重ゲート、3段目）
    5.  三重ゲートすべて満たすと is_ready()=True

    ── PublishTriggerAgent.decide()（副作用なし）──
    6.  reports_dir が存在しない → should_act=True
    7.  reports_dir はあるが *.md ファイルなし → should_act=True
    8.  古い *.md ファイルのみ（間隔超過）→ should_act=True
    9.  新しい *.md ファイルあり（間隔内）→ should_act=False
    10. 新旧混在時は最新mtimeを優先する

    ── PublishTriggerAgent.act() ──
    11. PublishPipelineRunner.run() のみを呼ぶ（params をそのまま渡す）
    12. PipelineResult成功時に AgentResult.success=True
    13. PipelineResult失敗時に AgentResult.success=False
    14. error_message が None の場合はフォールバック文言が使われる
    15. act() で workflow_result が常に None（成功時・失敗時とも）
    16. dry_run=True でのact()直接呼び出しはAssertionErrorになる

    ── PublishPipelineRunner（AiPublishService はモック）──
    17. AiPublishService.from_env が base_dir=config.project_root で呼ばれる
    18. service.run が article_id付きで呼ばれる
    19. report_pathが返る → PipelineResult.success=True
    20. report_path=None → PipelineResult.success=False（固定文言）
    21. service.get_results も article_id付きで呼ばれる（読み戻し確認）
    22. params=None時は article_id=None で service.run が呼ばれる
    23. from_env() が例外を投げても success=False
    24. service.run() が例外を投げても success=False
    25. returncode / stdout_log_path / stderr_log_path は常に None
    26. 実際の AiPublishService インスタンス（WordPress投稿処理）は生成されない（from_envを丸ごとモック置換）

    ── AgentManager DI（三重ゲート）──
    27. PUBLISH_TRIGGER_AGENT_ENABLED未設定 → NewsAgentのみ
    28. 三重ゲートすべて満たす → NewsAgent + PublishTriggerAgent
    29. PUBLISH_TRIGGER_AGENT_ENABLED=true だが AI_PUBLISH_ENABLED未設定 → NewsAgentのみ（除外）
    30. WorkflowTriggerAgent と PublishTriggerAgent の両方が有効 → 3件登録（既存Workflow登録に影響なし）
    31. AI_AGENT_ENABLED=false → NullAgentManager

    ── scripts/run_publish_trigger_agent.py（実サブプロセス、常にdry-run）──
    32. スクリプトファイルが存在する
    33. AI_AGENT_ENABLED=false --dry-run で安全に終了する
    34. PUBLISH_TRIGGER_AGENT_ENABLED未設定 --dry-run では NewsAgentのみ実行される
    35. 三重ゲートON --dry-run --article-id で publish_trigger_agent が実行され、
        かつ act() はスキップされる（outputs/ai_publish_reports/ に
        新規ファイルが作られないことで実証）
    36. run_publish_trigger_agent.py が AiPublishService を直接importしない（静的検査）

    ── Architecture Guard ──
    37. AiPublishService本体・AiPublishConfig・WorkflowRunner・既存Agent
        （NewsAgent/WorkflowTriggerAgent）に変更がない（git diff）
    38. publish_trigger_agent.py / publish_pipeline_runner.py の禁止import静的検査（まとめ）
    39. src/ai/__init__.py / src/pipeline/__init__.py からのexport確認

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v2_4_0_publish_trigger_agent_foundation.py
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
print("v2.4.0 Publish Trigger Agent Foundation E2E テスト")
print("=" * 60)
print()

from ai.publish_trigger_agent_config import PublishTriggerAgentConfig
from ai.publish_trigger_agent import (
    PublishTriggerAgent,
    REASON_NO_PREVIOUS_REPORT,
    REASON_INTERVAL_EXCEEDED,
    REASON_INTERVAL_NOT_EXCEEDED,
)
from ai.ai_publish_service import AiPublishService
from ai.workflow_trigger_agent import WorkflowTriggerAgent
from pipeline.pipeline_result import PipelineResult
from pipeline.publish_pipeline_runner import PublishPipelineRunner
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


def clear_publish_trigger_env():
    for key in PUBLISH_TRIGGER_ENV_KEYS:
        os.environ.pop(key, None)


def clear_all_trigger_env():
    for key in WORKFLOW_TRIGGER_ENV_KEYS + PUBLISH_TRIGGER_ENV_KEYS:
        os.environ.pop(key, None)


# ═══════════════════════════════════════════════════════════
# テスト1-5: PublishTriggerAgentConfig
# ═══════════════════════════════════════════════════════════

print("[テスト1-5] PublishTriggerAgentConfig.from_env()")

clear_publish_trigger_env()
fake_root = Path(tempfile.mkdtemp())

cfg1 = PublishTriggerAgentConfig.from_env(project_root=fake_root)
check_false("1. デフォルト enabled=False", cfg1.enabled)
check("1. デフォルト min_interval_minutes=1440", cfg1.min_interval_minutes, 1440)
check("1. reports_dir が project_root/outputs/ai_publish_reports", cfg1.reports_dir, fake_root / "outputs" / "ai_publish_reports")
check_false("1. デフォルト publish_enabled=False（AI_PUBLISH_ENABLEDのデフォルトfalse）", cfg1.publish_enabled)
check("1. project_root が渡した値と一致", cfg1.project_root, fake_root)
check_false("1. デフォルトは is_ready()=False（enabled=Falseのため）", cfg1.is_ready())

os.environ["PUBLISH_TRIGGER_AGENT_ENABLED"] = "true"
cfg2 = PublishTriggerAgentConfig.from_env(project_root=fake_root)
check_true("2. PUBLISH_TRIGGER_AGENT_ENABLED=true で enabled=True", cfg2.enabled)
check_false("2. enabled=Trueでも publish_enabled=False なら is_ready()=False（三重ゲート）", cfg2.is_ready())
os.environ.pop("PUBLISH_TRIGGER_AGENT_ENABLED", None)

os.environ["PUBLISH_TRIGGER_AGENT_MIN_INTERVAL_MINUTES"] = "60"
cfg3 = PublishTriggerAgentConfig.from_env(project_root=fake_root)
check("3. 環境変数上書き min_interval_minutes=60", cfg3.min_interval_minutes, 60)
os.environ.pop("PUBLISH_TRIGGER_AGENT_MIN_INTERVAL_MINUTES", None)

os.environ["AI_PUBLISH_ENABLED"] = "false"
cfg4 = PublishTriggerAgentConfig.from_env(project_root=fake_root)
check_false("4. AI_PUBLISH_ENABLED=false で publish_enabled=False", cfg4.publish_enabled)
check_false("4. publish_enabled=False なら is_ready()=False（三重ゲート）", cfg4.is_ready())

clear_publish_trigger_env()
os.environ["PUBLISH_TRIGGER_AGENT_ENABLED"] = "true"
os.environ["AI_PUBLISH_ENABLED"] = "true"
os.environ["WORDPRESS_URL"] = "https://example.com"
os.environ["WORDPRESS_USERNAME"] = "user"
os.environ["WORDPRESS_APP_PASSWORD"] = "app-password"
cfg5 = PublishTriggerAgentConfig.from_env(project_root=fake_root)
check_true("5. 三重ゲートすべて満たす → publish_enabled=True", cfg5.publish_enabled)
check_true("5. enabled=True かつ publish_enabled=True で is_ready()=True", cfg5.is_ready())

clear_publish_trigger_env()
print()


# ═══════════════════════════════════════════════════════════
# テスト6-10: PublishTriggerAgent.decide()
# ═══════════════════════════════════════════════════════════

print("[テスト6-10] PublishTriggerAgent.decide()")


def make_decide_agent(tmp_dir: Path, min_interval_minutes: int = 1440):
    cfg = PublishTriggerAgentConfig(
        enabled=True,
        min_interval_minutes=min_interval_minutes,
        reports_dir=tmp_dir / "outputs" / "ai_publish_reports",
        publish_enabled=True,
        project_root=tmp_dir,
    )
    mock_runner = MagicMock()
    return PublishTriggerAgent(config=cfg, runner=mock_runner), mock_runner


def make_context(params=None, dry_run=False):
    return AgentContext(
        task=AgentTask(task_id="run_publish", params=params or {}),
        dry_run=dry_run,
        run_id="test-run",
        agent_name="publish_trigger_agent",
    )


# テスト6: reports_dir が存在しない
tmp6 = Path(tempfile.mkdtemp())
agent6d, mock_runner6d = make_decide_agent(tmp6)
decision6 = agent6d.decide(make_context())
check_true("6. reports_dirなし → should_act=True", decision6.should_act)
check("6. reasonが固定文言と一致", decision6.reason, REASON_NO_PREVIOUS_REPORT)
check("6. runner.run は呼ばれない（副作用なし）", mock_runner6d.run.call_count, 0)
check_false("6. reports_dirが作られていない（副作用なし）", (tmp6 / "outputs" / "ai_publish_reports").exists())

# テスト7: reports_dir はあるが *.md ファイルなし
tmp7 = Path(tempfile.mkdtemp())
reports_dir7 = tmp7 / "outputs" / "ai_publish_reports"
reports_dir7.mkdir(parents=True)
agent7d, mock_runner7d = make_decide_agent(tmp7)
decision7 = agent7d.decide(make_context())
check_true("7. ファイル0件 → should_act=True", decision7.should_act)
check("7. reasonが固定文言と一致", decision7.reason, REASON_NO_PREVIOUS_REPORT)
check("7. runner.run は呼ばれない（副作用なし）", mock_runner7d.run.call_count, 0)

# テスト8: 古い *.md ファイルのみ（min_interval=1分、1時間前のファイル）
tmp8 = Path(tempfile.mkdtemp())
reports_dir8 = tmp8 / "outputs" / "ai_publish_reports"
reports_dir8.mkdir(parents=True)
old_file8 = reports_dir8 / "20200101_ai_publish_report.md"
old_file8.write_text("old report", encoding="utf-8")
old_time8 = (datetime.now() - timedelta(hours=1)).timestamp()
os.utime(old_file8, (old_time8, old_time8))
agent8d, mock_runner8d = make_decide_agent(tmp8, min_interval_minutes=1)
decision8 = agent8d.decide(make_context())
check_true("8. 間隔超過 → should_act=True", decision8.should_act)
check("8. reasonが固定文言と一致", decision8.reason, REASON_INTERVAL_EXCEEDED)

# テスト9: 新しい *.md ファイルあり（min_interval=1440分、直近作成）
tmp9 = Path(tempfile.mkdtemp())
reports_dir9 = tmp9 / "outputs" / "ai_publish_reports"
reports_dir9.mkdir(parents=True)
new_file9 = reports_dir9 / "20260702_ai_publish_report.md"
new_file9.write_text("new report", encoding="utf-8")
agent9d, mock_runner9d = make_decide_agent(tmp9, min_interval_minutes=1440)
decision9 = agent9d.decide(make_context())
check_false("9. 間隔内 → should_act=False", decision9.should_act)
check("9. reasonが固定文言と一致", decision9.reason, REASON_INTERVAL_NOT_EXCEEDED)

# テスト10: 新旧混在時は最新mtimeを優先する
tmp10 = Path(tempfile.mkdtemp())
reports_dir10 = tmp10 / "outputs" / "ai_publish_reports"
reports_dir10.mkdir(parents=True)
old_file10 = reports_dir10 / "20200101_ai_publish_report.md"
old_file10.write_text("old", encoding="utf-8")
old_time10 = (datetime.now() - timedelta(days=30)).timestamp()
os.utime(old_file10, (old_time10, old_time10))
new_file10 = reports_dir10 / "20260702_ai_publish_report.md"
new_file10.write_text("new", encoding="utf-8")
agent10d, mock_runner10d = make_decide_agent(tmp10, min_interval_minutes=1440)
decision10 = agent10d.decide(make_context())
check_false("10. 新旧混在時は最新（新しい方）が優先される → should_act=False", decision10.should_act)
print()


# ═══════════════════════════════════════════════════════════
# テスト11-16: PublishTriggerAgent.act()
# ═══════════════════════════════════════════════════════════

print("[テスト11-16] PublishTriggerAgent.act()")

act_tmp = Path(tempfile.mkdtemp())
act_cfg = PublishTriggerAgentConfig(
    enabled=True, min_interval_minutes=1440,
    reports_dir=act_tmp / "outputs" / "ai_publish_reports",
    publish_enabled=True, project_root=act_tmp,
)

# 成功時
mock_runner11 = MagicMock()
mock_runner11.run.return_value = PipelineResult(
    success=True, returncode=None, elapsed_sec=2.0,
    stdout_log_path=None, stderr_log_path=None, error_message=None,
)
agent11 = PublishTriggerAgent(config=act_cfg, runner=mock_runner11)
ctx11 = make_context(params={"article_id": "ps6-announced-20260630"})
ctx11.started_at = datetime.now()
ctx11.finished_at = datetime.now()
decision11 = AgentDecision(should_act=True, reason=REASON_INTERVAL_EXCEEDED)
result11 = agent11.act(decision11, ctx11)

check("11. runner.run が1回だけ呼ばれる", mock_runner11.run.call_count, 1)
check(
    "11. runner.run が context.task.params をそのまま渡す",
    mock_runner11.run.call_args.kwargs["params"],
    {"article_id": "ps6-announced-20260630"},
)
check_true("12. AgentResult型が返る", isinstance(result11, AgentResult))
check_true("12. action_taken=True", result11.action_taken)
check_true("12. PipelineResult成功時に success=True", result11.success)
check_none("12. error_message が None（成功時）", result11.error_message)
check_none("15. workflow_result が None（成功時）", result11.workflow_result)
check_true("12. warningsに成功メッセージが含まれる", any("completed successfully" in w for w in result11.warnings))

# 失敗時
mock_runner13 = MagicMock()
mock_runner13.run.return_value = PipelineResult(
    success=False, returncode=None, elapsed_sec=1.0,
    stdout_log_path=None, stderr_log_path=None,
    error_message="Publish report was not saved.",
)
agent13 = PublishTriggerAgent(config=act_cfg, runner=mock_runner13)
ctx13 = make_context()
ctx13.started_at = datetime.now()
ctx13.finished_at = datetime.now()
result13 = agent13.act(AgentDecision(True, REASON_INTERVAL_EXCEEDED), ctx13)
check_false("13. PipelineResult失敗時に success=False", result13.success)
check(
    "13. error_message が PipelineResult.error_message と一致",
    result13.error_message,
    "Publish report was not saved.",
)
check_none("15. workflow_result が None（失敗時も）", result13.workflow_result)

# 失敗時（error_messageがNoneの場合のフォールバック）
mock_runner14 = MagicMock()
mock_runner14.run.return_value = PipelineResult(
    success=False, returncode=None, elapsed_sec=1.0,
    stdout_log_path=None, stderr_log_path=None, error_message=None,
)
agent14 = PublishTriggerAgent(config=act_cfg, runner=mock_runner14)
ctx14 = make_context()
ctx14.started_at = datetime.now()
ctx14.finished_at = datetime.now()
result14 = agent14.act(AgentDecision(True, REASON_INTERVAL_EXCEEDED), ctx14)
check_not_none("14. error_messageがNoneの場合はフォールバック文言が使われる", result14.error_message)

# dry_run=True でのact()直接呼び出し
ctx16 = make_context(dry_run=True)
try:
    agent11.act(AgentDecision(True, REASON_INTERVAL_EXCEEDED), ctx16)
    check_true("16. dry_run=Trueでのact()直接呼び出しはAssertionErrorになる", False)
except AssertionError:
    check_true("16. dry_run=Trueでのact()直接呼び出しはAssertionErrorになる", True)
print()


# ═══════════════════════════════════════════════════════════
# テスト17-26: PublishPipelineRunner
# ═══════════════════════════════════════════════════════════

print("[テスト17-26] PublishPipelineRunner")

runner_tmp = Path(tempfile.mkdtemp())


class FakeRunnerConfig:
    project_root = runner_tmp


report_path17 = runner_tmp / "outputs" / "ai_publish_reports" / "20260702_ai_publish_report.md"
mock_service17 = MagicMock()
mock_service17.run.return_value = report_path17
mock_service17.get_results.return_value = [MagicMock(success=True), MagicMock(success=True)]

with patch.object(AiPublishService, "from_env", return_value=mock_service17) as mock_from_env17:
    ppr17 = PublishPipelineRunner(FakeRunnerConfig())
    result17 = ppr17.run(params={"article_id": "ps6-announced-20260630"})

check("17. AiPublishService.from_env が base_dir=config.project_root で呼ばれる",
      mock_from_env17.call_args.kwargs["base_dir"], runner_tmp)
check("18. service.run が article_id付きで呼ばれる",
      mock_service17.run.call_args.kwargs, {"article_id": "ps6-announced-20260630"})
check_true("19. report_pathが返る → PipelineResult.success=True", result17.success)
check_none("19. error_message が None（成功時）", result17.error_message)
check("21. service.get_results が article_id付きで呼ばれる（読み戻し確認）",
      mock_service17.get_results.call_args.kwargs, {"article_id": "ps6-announced-20260630"})
check_true("17. elapsed_sec が0以上（壁時計で計測）", result17.elapsed_sec >= 0)

mock_service20 = MagicMock()
mock_service20.run.return_value = None
mock_service20.get_results.return_value = []
with patch.object(AiPublishService, "from_env", return_value=mock_service20):
    ppr20 = PublishPipelineRunner(FakeRunnerConfig())
    result20 = ppr20.run(params={})
check_false("20. report_path=None → PipelineResult.success=False", result20.success)
check("20. error_messageが固定文言", result20.error_message, "Publish report was not saved.")

mock_service22 = MagicMock()
mock_service22.run.return_value = report_path17
mock_service22.get_results.return_value = []
with patch.object(AiPublishService, "from_env", return_value=mock_service22):
    ppr22 = PublishPipelineRunner(FakeRunnerConfig())
    result22 = ppr22.run(params=None)
check("22. params=None時は article_id=None で service.run が呼ばれる",
      mock_service22.run.call_args.kwargs, {"article_id": None})

with patch.object(AiPublishService, "from_env", side_effect=RuntimeError("from_env boom")):
    ppr23 = PublishPipelineRunner(FakeRunnerConfig())
    result23 = ppr23.run(params={})
check_false("23. from_env() が例外を投げても success=False", result23.success)
check("23. error_message に例外文言", result23.error_message, "from_env boom")

mock_service24 = MagicMock()
mock_service24.run.side_effect = RuntimeError("service.run boom")
with patch.object(AiPublishService, "from_env", return_value=mock_service24):
    ppr24 = PublishPipelineRunner(FakeRunnerConfig())
    result24 = ppr24.run(params={})
check_false("24. service.run() が例外を投げても success=False", result24.success)
check("24. error_message に例外文言", result24.error_message, "service.run boom")

for label, r in (("成功時", result17), ("失敗時", result20), ("例外時", result23)):
    check_none(f"25. returncode が None（{label}）", r.returncode)
    check_none(f"25. stdout_log_path が None（{label}）", r.stdout_log_path)
    check_none(f"25. stderr_log_path が None（{label}）", r.stderr_log_path)

with patch.object(AiPublishService, "from_env", return_value=mock_service17) as mock_from_env26:
    ppr26 = PublishPipelineRunner(FakeRunnerConfig())
    ppr26.run(params={"article_id": "dummy"})
check(
    "26. 本物の AiPublishService インスタンスは一度も生成されない（from_env自体を丸ごと置換）",
    mock_from_env26.call_count >= 1,
    True,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト27-31: AgentManager.from_config()（三重ゲート）
# ═══════════════════════════════════════════════════════════

print("[テスト27-31] AgentManager.from_config()（三重ゲート）")

manager_tmp = Path(tempfile.mkdtemp())

# テスト27: PUBLISH_TRIGGER_AGENT_ENABLED未設定 → NewsAgentのみ
clear_all_trigger_env()
config27 = AgentConfig(enabled=True, base_dir=manager_tmp)
manager27 = AgentManager.from_config(config27)
check_true("27. AgentManagerが返る", isinstance(manager27, AgentManager))
check("27. executorsが1件（NewsAgentのみ）", len(manager27._executors), 1)
check_true("27. executors[0]がNewsAgent", isinstance(manager27._executors[0]._agent, NewsAgent))

# テスト28: 三重ゲートすべて満たす → NewsAgent + PublishTriggerAgent
clear_all_trigger_env()
os.environ["PUBLISH_TRIGGER_AGENT_ENABLED"] = "true"
os.environ["AI_PUBLISH_ENABLED"] = "true"
os.environ["WORDPRESS_URL"] = "https://example.com"
os.environ["WORDPRESS_USERNAME"] = "user"
os.environ["WORDPRESS_APP_PASSWORD"] = "app-password"
config28 = AgentConfig(enabled=True, base_dir=manager_tmp)
manager28 = AgentManager.from_config(config28)
check("28. executorsが2件", len(manager28._executors), 2)
check_true("28. executors[0]がNewsAgent", isinstance(manager28._executors[0]._agent, NewsAgent))
check_true("28. executors[1]がPublishTriggerAgent", isinstance(manager28._executors[1]._agent, PublishTriggerAgent))
check_true(
    "28. PublishTriggerAgentのrunnerがPublishPipelineRunner",
    isinstance(manager28._executors[1]._agent._runner, PublishPipelineRunner),
)

# テスト29: PUBLISH_TRIGGER_AGENT_ENABLED=true だが AI_PUBLISH_ENABLED未設定 → NewsAgentのみ
clear_all_trigger_env()
os.environ["PUBLISH_TRIGGER_AGENT_ENABLED"] = "true"
config29 = AgentConfig(enabled=True, base_dir=manager_tmp)
manager29 = AgentManager.from_config(config29)
check("29. executorsが1件（AI_PUBLISH_ENABLED未設定のためPublishTriggerAgent除外）", len(manager29._executors), 1)
check_true("29. executors[0]がNewsAgent", isinstance(manager29._executors[0]._agent, NewsAgent))

# テスト30: WorkflowTriggerAgent と PublishTriggerAgent の両方が有効
clear_all_trigger_env()
os.environ["WORKFLOW_TRIGGER_AGENT_ENABLED"] = "true"
os.environ["AI_WORKFLOW_ENABLED"] = "true"
os.environ["PUBLISH_TRIGGER_AGENT_ENABLED"] = "true"
os.environ["AI_PUBLISH_ENABLED"] = "true"
os.environ["WORDPRESS_URL"] = "https://example.com"
os.environ["WORDPRESS_USERNAME"] = "user"
os.environ["WORDPRESS_APP_PASSWORD"] = "app-password"
config30 = AgentConfig(enabled=True, base_dir=manager_tmp)
manager30 = AgentManager.from_config(config30)
check("30. executorsが3件（NewsAgent + WorkflowTriggerAgent + PublishTriggerAgent）", len(manager30._executors), 3)
check_true("30. executors[0]がNewsAgent", isinstance(manager30._executors[0]._agent, NewsAgent))
check_true("30. executors[1]がWorkflowTriggerAgent", isinstance(manager30._executors[1]._agent, WorkflowTriggerAgent))
check_true("30. executors[2]がPublishTriggerAgent", isinstance(manager30._executors[2]._agent, PublishTriggerAgent))

# テスト31: AI_AGENT_ENABLED=false → NullAgentManager
clear_all_trigger_env()
config31 = AgentConfig(enabled=False, base_dir=manager_tmp)
manager31 = AgentManager.from_config(config31)
check_true("31. disabled → NullAgentManager が返る", isinstance(manager31, NullAgentManager))

clear_all_trigger_env()
print()


# ═══════════════════════════════════════════════════════════
# テスト32-36: scripts/run_publish_trigger_agent.py（実サブプロセス、常にdry-run）
# ═══════════════════════════════════════════════════════════

print("[テスト32-36] scripts/run_publish_trigger_agent.py")

script_path = PROJECT_ROOT / "scripts" / "run_publish_trigger_agent.py"
check_true("32. run_publish_trigger_agent.py が存在する", script_path.exists())

reports_dir_real = PROJECT_ROOT / "outputs" / "ai_publish_reports"
before_reports = set(reports_dir_real.glob("*")) if reports_dir_real.exists() else set()


def run_cli(extra_args, env_overrides):
    env = dict(os.environ)
    for key in ("AI_AGENT_ENABLED",) + WORKFLOW_TRIGGER_ENV_KEYS + PUBLISH_TRIGGER_ENV_KEYS:
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


# テスト33: AI_AGENT_ENABLED=false --dry-run
completed33 = run_cli(["--dry-run"], {"AI_AGENT_ENABLED": "false"})
check("33. returncode が 0", completed33.returncode, 0)
check_contains("33. AI Agent基盤が無効の案内が表示される", completed33.stdout, "AI Agent基盤が無効です")

# テスト34: AI_AGENT_ENABLED=true / PUBLISH_TRIGGER_AGENT_ENABLED未設定 --dry-run
completed34 = run_cli(["--dry-run"], {"AI_AGENT_ENABLED": "true"})
check("34. returncode が 0", completed34.returncode, 0)
check_false("34. publish_trigger_agent は実行されない", "Agent: publish_trigger_agent" in completed34.stdout)
check_contains("34. PublishTriggerAgent未実行の案内メッセージが表示される", completed34.stdout, "PublishTriggerAgent")

# テスト35: 三重ゲートON --dry-run --article-id
completed35 = run_cli(
    ["--dry-run", "--article-id", "sample-article"],
    {
        "AI_AGENT_ENABLED": "true",
        "PUBLISH_TRIGGER_AGENT_ENABLED": "true",
        "AI_PUBLISH_ENABLED": "true",
        "WORDPRESS_URL": "https://example.com",
        "WORDPRESS_USERNAME": "user",
        "WORDPRESS_APP_PASSWORD": "app-password",
    },
)
check("35. returncode が 0", completed35.returncode, 0)
check_contains("35. publish_trigger_agent が実行される", completed35.stdout, "Agent: publish_trigger_agent")
check_contains("35. article_id が反映される", completed35.stdout, "sample-article")
check_contains("35. action_taken=False（--dry-runによりact()がスキップされる）", completed35.stdout, "action_taken=False")

after_reports = set(reports_dir_real.glob("*")) if reports_dir_real.exists() else set()
check(
    "35. outputs/ai_publish_reports/ に新規ファイルが作られない（AiPublishService未起動）",
    after_reports - before_reports,
    set(),
)

# テスト36: 静的import検査
script_source = script_path.read_text(encoding="utf-8")
script_import_lines = "\n".join(
    line for line in script_source.splitlines()
    if line.strip().startswith("from ") or line.strip().startswith("import ")
)
check_false(
    "36. run_publish_trigger_agent.py の import文に AiPublishService が含まれない",
    "AiPublishService" in script_import_lines,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト37-39: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト37] 既存ファイルの無変更確認（git diff）")

unchanged_paths = [
    "main.py",
    "src/ai/ai_publish_service.py",
    "src/ai/ai_publish_config.py",
    "src/ai/ai_publish_result.py",
    "src/ai/ai_publish_repository.py",
    "src/ai/ai_publish_report_builder.py",
    "src/ai/wordpress_draft_client.py",
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
    "src/pipeline/news_pipeline_runner.py",
    "src/pipeline/workflow_pipeline_runner.py",
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
        check_true(f"37. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("37. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト38] Architecture Guard（静的import検査、まとめ）")
pta_source = (PROJECT_ROOT / "src" / "ai" / "publish_trigger_agent.py").read_text(encoding="utf-8")
pta_import_lines = "\n".join(
    line for line in pta_source.splitlines()
    if line.strip().startswith("from ") or line.strip().startswith("import ")
)
check_false(
    "38. publish_trigger_agent.py の import文に AiPublishService が含まれない（再掲）",
    "AiPublishService" in pta_import_lines,
)
check_false(
    "38. publish_trigger_agent.py の import文に WorkflowRunner が含まれない",
    "WorkflowRunner" in pta_import_lines,
)

ppr_source = (PROJECT_ROOT / "src" / "pipeline" / "publish_pipeline_runner.py").read_text(encoding="utf-8")
check_false("38. publish_pipeline_runner.py が subprocess をimportしない", "import subprocess" in ppr_source)
check_false("38. publish_pipeline_runner.py が subprocess.run を使わない", "subprocess.run" in ppr_source)
print()


print("[テスト39] import確認")

import ai as ai_pkg
for name in ("PublishTriggerAgent", "PublishTriggerAgentConfig"):
    check_true(f"39. {name} が ai パッケージからエクスポートされている", hasattr(ai_pkg, name))
    check_true(f"39. {name} が ai.__all__ に含まれる", name in ai_pkg.__all__)

import pipeline as pipeline_pkg
check_true(
    "39. PublishPipelineRunner が pipeline パッケージからエクスポートされている",
    hasattr(pipeline_pkg, "PublishPipelineRunner"),
)
check_true(
    "39. PublishPipelineRunner が pipeline.__all__ に含まれる",
    "PublishPipelineRunner" in pipeline_pkg.__all__,
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
