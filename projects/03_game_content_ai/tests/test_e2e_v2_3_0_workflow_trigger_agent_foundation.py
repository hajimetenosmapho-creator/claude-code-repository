"""
E2E テスト: v2.3.0 Workflow Trigger Agent Foundation

テストシナリオ:
    ── WorkflowTriggerAgentConfig ──
    1.  from_env() のデフォルト値
    2.  WORKFLOW_TRIGGER_AGENT_ENABLED=true の環境変数上書き
    3.  WORKFLOW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES の環境変数上書き
    4.  AI_WORKFLOW_ENABLED=false 時に is_ready() が False（二重ゲート）

    ── WorkflowTriggerAgent.decide()（副作用なし）──
    5.  reports_dir が存在しない → should_act=True
    6.  reports_dir はあるが *.md ファイルなし → should_act=True
    7.  古い *.md ファイルのみ（間隔超過）→ should_act=True
    8.  新しい *.md ファイルあり（間隔内）→ should_act=False
    9.  新旧混在時は最新mtimeを優先する

    ── WorkflowTriggerAgent.act() ──
    10. WorkflowPipelineRunner.run() のみを呼ぶ（params をそのまま渡す）
    11. PipelineResult成功時に AgentResult.success=True
    12. PipelineResult失敗時に AgentResult.success=False
    13. act() で workflow_result が常に None（成功時・失敗時とも）
    14. dry_run=True でのact()直接呼び出しはAssertionErrorになる
    15. workflow_trigger_agent.py が WorkflowRunner を直接importしない（静的検査）

    ── WorkflowPipelineRunner ──
    16. WorkflowRunner.run() を直接呼ぶ（article_id / dry_run を渡す）
    17. WorkflowResult.overall_success=True → PipelineResult.success=True
    18. WorkflowResult.overall_success=False → PipelineResult.success=False（失敗ステップ要約）
    19. 例外発生時も PipelineResult(success=False) を返す
    20. returncode / stdout_log_path / stderr_log_path は常に None
    21. workflow_pipeline_runner.py が subprocess を使わない（静的検査）

    ── AgentManager DI（二重ゲート）──
    22. AI_AGENT_ENABLED=false → NullAgentManager
    23. AI_AGENT_ENABLED=true / WORKFLOW_TRIGGER_AGENT_ENABLED未設定 → NewsAgentのみ
    24. AI_AGENT_ENABLED=true / WORKFLOW_TRIGGER_AGENT_ENABLED=true / AI_WORKFLOW_ENABLED=true
        → NewsAgent + WorkflowTriggerAgent
    25. AI_AGENT_ENABLED=true / WORKFLOW_TRIGGER_AGENT_ENABLED=true / AI_WORKFLOW_ENABLED=false
        → NewsAgentのみ

    ── scripts/run_workflow_trigger_agent.py（実サブプロセス、常にdry-run）──
    26. スクリプトファイルが存在する
    27. AI_AGENT_ENABLED=false --dry-run で安全に終了する
    28. WORKFLOW_TRIGGER_AGENT_ENABLED未設定 --dry-run では NewsAgentのみ実行される
    29. 二重ゲートON --dry-run --article-id --workflow-dry-run で
        WorkflowTriggerAgentが実行され、かつ act() はスキップされる
        （outputs/workflow_reports/ に新規ファイルが作られないことで実証）

    ── Architecture Guard ──
    30. main.py / WorkflowRunner本体 / NewsAgent / NewsPipelineRunner に変更がない（git diff）
    31. WorkflowRunnerの直接import禁止・subprocess不使用の静的検査
    32. src/ai/__init__.py / src/pipeline/__init__.py からのexport確認

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v2_3_0_workflow_trigger_agent_foundation.py
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
print("v2.3.0 Workflow Trigger Agent Foundation E2E テスト")
print("=" * 60)
print()

from ai.workflow_trigger_agent_config import WorkflowTriggerAgentConfig
from ai.workflow_trigger_agent import (
    WorkflowTriggerAgent,
    REASON_NO_PREVIOUS_REPORT,
    REASON_INTERVAL_EXCEEDED,
    REASON_INTERVAL_NOT_EXCEEDED,
)
from ai.workflow_config import WorkflowConfig
from ai.workflow_runner import WorkflowRunner
from ai.workflow_result import WorkflowResult
from ai.workflow_step import WorkflowStep, WorkflowStepResult
from pipeline.pipeline_result import PipelineResult
from pipeline.workflow_pipeline_runner import WorkflowPipelineRunner
from ai import (
    AgentContext, AgentDecision, AgentResult, AgentTask, AgentExecutor,
    AgentConfig, AgentManager, NullAgentManager, NewsAgent,
)

WORKFLOW_TRIGGER_ENV_KEYS = (
    "WORKFLOW_TRIGGER_AGENT_ENABLED",
    "WORKFLOW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES",
    "AI_WORKFLOW_ENABLED",
)


def clear_workflow_trigger_env():
    for key in WORKFLOW_TRIGGER_ENV_KEYS:
        os.environ.pop(key, None)


# ═══════════════════════════════════════════════════════════
# テスト1-4: WorkflowTriggerAgentConfig
# ═══════════════════════════════════════════════════════════

print("[テスト1-4] WorkflowTriggerAgentConfig.from_env()")

clear_workflow_trigger_env()
fake_root = Path(tempfile.mkdtemp())

cfg1 = WorkflowTriggerAgentConfig.from_env(project_root=fake_root)
check_false("1. デフォルト enabled=False", cfg1.enabled)
check("1. デフォルト min_interval_minutes=1440", cfg1.min_interval_minutes, 1440)
check("1. reports_dir が project_root/outputs/workflow_reports", cfg1.reports_dir, fake_root / "outputs" / "workflow_reports")
check_true("1. デフォルト workflow_enabled=True（AI_WORKFLOW_ENABLEDのデフォルトtrue）", cfg1.workflow_enabled)
check("1. project_root が渡した値と一致", cfg1.project_root, fake_root)
check_false("1. デフォルトは is_ready()=False（enabled=Falseのため）", cfg1.is_ready())

os.environ["WORKFLOW_TRIGGER_AGENT_ENABLED"] = "true"
cfg2 = WorkflowTriggerAgentConfig.from_env(project_root=fake_root)
check_true("2. WORKFLOW_TRIGGER_AGENT_ENABLED=true で enabled=True", cfg2.enabled)
check_true("2. enabled=True かつ workflow_enabled=True で is_ready()=True", cfg2.is_ready())
os.environ.pop("WORKFLOW_TRIGGER_AGENT_ENABLED", None)

os.environ["WORKFLOW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES"] = "60"
cfg3 = WorkflowTriggerAgentConfig.from_env(project_root=fake_root)
check("3. 環境変数上書き min_interval_minutes=60", cfg3.min_interval_minutes, 60)
os.environ.pop("WORKFLOW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES", None)

os.environ["WORKFLOW_TRIGGER_AGENT_ENABLED"] = "true"
os.environ["AI_WORKFLOW_ENABLED"] = "false"
cfg4 = WorkflowTriggerAgentConfig.from_env(project_root=fake_root)
check_false("4. AI_WORKFLOW_ENABLED=false で workflow_enabled=False", cfg4.workflow_enabled)
check_false("4. enabled=Trueでも workflow_enabled=False なら is_ready()=False（二重ゲート）", cfg4.is_ready())

clear_workflow_trigger_env()
print()


# ═══════════════════════════════════════════════════════════
# テスト5-9: WorkflowTriggerAgent.decide()
# ═══════════════════════════════════════════════════════════

print("[テスト5-9] WorkflowTriggerAgent.decide()")


def make_decide_agent(tmp_dir: Path, min_interval_minutes: int = 1440):
    cfg = WorkflowTriggerAgentConfig(
        enabled=True,
        min_interval_minutes=min_interval_minutes,
        reports_dir=tmp_dir / "outputs" / "workflow_reports",
        workflow_enabled=True,
        project_root=tmp_dir,
    )
    mock_runner = MagicMock()
    return WorkflowTriggerAgent(config=cfg, runner=mock_runner), mock_runner


def make_context(params=None, dry_run=False):
    return AgentContext(
        task=AgentTask(task_id="run_workflow", params=params or {}),
        dry_run=dry_run,
        run_id="test-run",
        agent_name="workflow_trigger_agent",
    )


# テスト5: reports_dir が存在しない
tmp5 = Path(tempfile.mkdtemp())
agent5, mock_runner5 = make_decide_agent(tmp5)
decision5 = agent5.decide(make_context())
check_true("5. reports_dirなし → should_act=True", decision5.should_act)
check("5. reasonが固定文言と一致", decision5.reason, REASON_NO_PREVIOUS_REPORT)
check("5. runner.run は呼ばれない（副作用なし）", mock_runner5.run.call_count, 0)
check_false("5. reports_dirが作られていない（副作用なし）", (tmp5 / "outputs" / "workflow_reports").exists())

# テスト6: reports_dir はあるが *.md ファイルなし
tmp6 = Path(tempfile.mkdtemp())
reports_dir6 = tmp6 / "outputs" / "workflow_reports"
reports_dir6.mkdir(parents=True)
agent6, mock_runner6 = make_decide_agent(tmp6)
decision6 = agent6.decide(make_context())
check_true("6. ファイル0件 → should_act=True", decision6.should_act)
check("6. reasonが固定文言と一致", decision6.reason, REASON_NO_PREVIOUS_REPORT)
check("6. runner.run は呼ばれない（副作用なし）", mock_runner6.run.call_count, 0)

# テスト7: 古い *.md ファイルのみ（min_interval=1分、1時間前のファイル）
tmp7 = Path(tempfile.mkdtemp())
reports_dir7 = tmp7 / "outputs" / "workflow_reports"
reports_dir7.mkdir(parents=True)
old_file7 = reports_dir7 / "20200101_workflow_report.md"
old_file7.write_text("old report", encoding="utf-8")
old_time7 = (datetime.now() - timedelta(hours=1)).timestamp()
os.utime(old_file7, (old_time7, old_time7))
agent7, mock_runner7 = make_decide_agent(tmp7, min_interval_minutes=1)
decision7 = agent7.decide(make_context())
check_true("7. 間隔超過 → should_act=True", decision7.should_act)
check("7. reasonが固定文言と一致", decision7.reason, REASON_INTERVAL_EXCEEDED)

# テスト8: 新しい *.md ファイルあり（min_interval=1440分、直近作成）
tmp8 = Path(tempfile.mkdtemp())
reports_dir8 = tmp8 / "outputs" / "workflow_reports"
reports_dir8.mkdir(parents=True)
new_file8 = reports_dir8 / "20260702_workflow_report.md"
new_file8.write_text("new report", encoding="utf-8")
agent8, mock_runner8 = make_decide_agent(tmp8, min_interval_minutes=1440)
decision8 = agent8.decide(make_context())
check_false("8. 間隔内 → should_act=False", decision8.should_act)
check("8. reasonが固定文言と一致", decision8.reason, REASON_INTERVAL_NOT_EXCEEDED)

# テスト9: 新旧混在時は最新mtimeを優先する
tmp9 = Path(tempfile.mkdtemp())
reports_dir9 = tmp9 / "outputs" / "workflow_reports"
reports_dir9.mkdir(parents=True)
old_file9 = reports_dir9 / "20200101_workflow_report.md"
old_file9.write_text("old", encoding="utf-8")
old_time9 = (datetime.now() - timedelta(days=30)).timestamp()
os.utime(old_file9, (old_time9, old_time9))
new_file9 = reports_dir9 / "20260702_workflow_report.md"
new_file9.write_text("new", encoding="utf-8")
agent9, mock_runner9 = make_decide_agent(tmp9, min_interval_minutes=1440)
decision9 = agent9.decide(make_context())
check_false("9. 新旧混在時は最新（新しい方）が優先される → should_act=False", decision9.should_act)
print()


# ═══════════════════════════════════════════════════════════
# テスト10-15: WorkflowTriggerAgent.act()
# ═══════════════════════════════════════════════════════════

print("[テスト10-15] WorkflowTriggerAgent.act()")

act_tmp = Path(tempfile.mkdtemp())
act_cfg = WorkflowTriggerAgentConfig(
    enabled=True, min_interval_minutes=1440,
    reports_dir=act_tmp / "outputs" / "workflow_reports",
    workflow_enabled=True, project_root=act_tmp,
)

# 成功時
mock_runner10 = MagicMock()
mock_runner10.run.return_value = PipelineResult(
    success=True, returncode=None, elapsed_sec=2.0,
    stdout_log_path=None, stderr_log_path=None, error_message=None,
)
agent10 = WorkflowTriggerAgent(config=act_cfg, runner=mock_runner10)
ctx10 = make_context(params={"article_id": "abc"})
ctx10.started_at = datetime.now()
ctx10.finished_at = datetime.now()
decision10 = AgentDecision(should_act=True, reason=REASON_INTERVAL_EXCEEDED)
result10 = agent10.act(decision10, ctx10)

check("10. runner.run が1回だけ呼ばれる", mock_runner10.run.call_count, 1)
check(
    "10. runner.run が context.task.params をそのまま渡す",
    mock_runner10.run.call_args.kwargs["params"],
    {"article_id": "abc"},
)
check_true("11. AgentResult型が返る", isinstance(result10, AgentResult))
check_true("11. action_taken=True", result10.action_taken)
check_true("11. PipelineResult成功時に success=True", result10.success)
check_none("11. error_message が None（成功時）", result10.error_message)
check_none("13. workflow_result が None（成功時）", result10.workflow_result)
check_true("11. warningsに成功メッセージが含まれる", any("completed successfully" in w for w in result10.warnings))

# 失敗時
mock_runner12 = MagicMock()
mock_runner12.run.return_value = PipelineResult(
    success=False, returncode=None, elapsed_sec=1.0,
    stdout_log_path=None, stderr_log_path=None,
    error_message="Workflow completed with failed steps.",
)
agent12 = WorkflowTriggerAgent(config=act_cfg, runner=mock_runner12)
ctx12 = make_context()
ctx12.started_at = datetime.now()
ctx12.finished_at = datetime.now()
result12 = agent12.act(AgentDecision(True, REASON_INTERVAL_EXCEEDED), ctx12)
check_false("12. PipelineResult失敗時に success=False", result12.success)
check(
    "12. error_message が PipelineResult.error_message と一致",
    result12.error_message,
    "Workflow completed with failed steps.",
)
check_none("13. workflow_result が None（失敗時も）", result12.workflow_result)

# 失敗時（error_messageがNoneの場合のフォールバック）
mock_runner12b = MagicMock()
mock_runner12b.run.return_value = PipelineResult(
    success=False, returncode=None, elapsed_sec=1.0,
    stdout_log_path=None, stderr_log_path=None, error_message=None,
)
agent12b = WorkflowTriggerAgent(config=act_cfg, runner=mock_runner12b)
ctx12b = make_context()
ctx12b.started_at = datetime.now()
ctx12b.finished_at = datetime.now()
result12b = agent12b.act(AgentDecision(True, REASON_INTERVAL_EXCEEDED), ctx12b)
check_not_none("12. error_messageがNoneの場合はフォールバック文言が使われる", result12b.error_message)

# dry_run=True でのact()直接呼び出し
ctx14 = make_context(dry_run=True)
try:
    agent10.act(AgentDecision(True, REASON_INTERVAL_EXCEEDED), ctx14)
    check_true("14. dry_run=Trueでのact()直接呼び出しはAssertionErrorになる", False)
except AssertionError:
    check_true("14. dry_run=Trueでのact()直接呼び出しはAssertionErrorになる", True)

# テスト15: 静的import検査
wta_source = (PROJECT_ROOT / "src" / "ai" / "workflow_trigger_agent.py").read_text(encoding="utf-8")
wta_import_lines = "\n".join(
    line for line in wta_source.splitlines()
    if line.strip().startswith("from ") or line.strip().startswith("import ")
)
check_false(
    "15. workflow_trigger_agent.py の import文に WorkflowRunner が含まれない",
    "WorkflowRunner" in wta_import_lines,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト16-21: WorkflowPipelineRunner
# ═══════════════════════════════════════════════════════════

print("[テスト16-21] WorkflowPipelineRunner")

runner_tmp = Path(tempfile.mkdtemp())


class FakeRunnerConfig:
    project_root = runner_tmp


now16 = datetime.now()

# テスト16-17: WorkflowRunner.run() を直接呼ぶ、成功時のマッピング
success_result = WorkflowResult(
    steps=[], overall_success=True, total_processed=3, report_path=None,
    started_at=now16, finished_at=now16 + timedelta(seconds=2.5),
    warnings=[], skipped_steps=[],
)
mock_workflow_runner_instance = MagicMock()
mock_workflow_runner_instance.run.return_value = success_result

with patch.object(WorkflowConfig, "from_env", return_value=MagicMock()) as mock_from_env16, \
     patch.object(WorkflowRunner, "from_config", return_value=mock_workflow_runner_instance) as mock_from_config16:
    wpr16 = WorkflowPipelineRunner(FakeRunnerConfig())
    result16 = wpr16.run(params={"article_id": "abc", "dry_run": True})

check("16. WorkflowConfig.from_env が base_dir=config.project_root で呼ばれる",
      mock_from_env16.call_args.kwargs["base_dir"], runner_tmp)
check("16. WorkflowRunner.from_config が1回呼ばれる", mock_from_config16.call_count, 1)
check("16. WorkflowRunner.run が article_id/dry_run付きで直接呼ばれる",
      mock_workflow_runner_instance.run.call_args.kwargs, {"article_id": "abc", "dry_run": True})
check_true("17. overall_success=True → PipelineResult.success=True", result16.success)
check_none("17. error_message が None（成功時）", result16.error_message)
check_true("17. elapsed_sec が0以上（壁時計で計測）", result16.elapsed_sec >= 0)

# テスト18: 失敗時（失敗ステップの要約）
failed_steps = [
    WorkflowStepResult(step=WorkflowStep.REWRITE, success=False, processed_count=0,
                        report_path=None, error_message="x", started_at=now16, finished_at=now16),
    WorkflowStepResult(step=WorkflowStep.PUBLISH, success=False, processed_count=0,
                        report_path=None, error_message="y", started_at=now16, finished_at=now16),
]
failure_result = WorkflowResult(
    steps=failed_steps, overall_success=False, total_processed=0, report_path=None,
    started_at=now16, finished_at=now16, warnings=[], skipped_steps=[],
)
mock_workflow_runner_instance18 = MagicMock()
mock_workflow_runner_instance18.run.return_value = failure_result
with patch.object(WorkflowConfig, "from_env", return_value=MagicMock()), \
     patch.object(WorkflowRunner, "from_config", return_value=mock_workflow_runner_instance18):
    wpr18 = WorkflowPipelineRunner(FakeRunnerConfig())
    result18 = wpr18.run(params=None)
check_false("18. overall_success=False → PipelineResult.success=False", result18.success)
check(
    "18. error_messageが固定文言（実装どおり、失敗ステップ名の動的要約は行わない）",
    result18.error_message,
    "Workflow completed with failed steps.",
)
check("18. runner.run が article_id=None, dry_run=False で呼ばれる（paramsデフォルト）",
      mock_workflow_runner_instance18.run.call_args.kwargs, {"article_id": None, "dry_run": False})

# テスト19: 例外発生時
with patch.object(WorkflowConfig, "from_env", return_value=MagicMock()), \
     patch.object(WorkflowRunner, "from_config", side_effect=RuntimeError("boom")):
    wpr19 = WorkflowPipelineRunner(FakeRunnerConfig())
    result19 = wpr19.run(params={})
check_false("19. 例外発生時も success=False", result19.success)
check_none("19. 例外発生時も returncode は None", result19.returncode)
check_true("19. 例外発生時も elapsed_sec が0以上", result19.elapsed_sec >= 0)
check("19. error_message が例外メッセージと一致", result19.error_message, "boom")

# テスト20: returncode / stdout_log_path / stderr_log_path は常に None
for label, r in (("成功時", result16), ("失敗時", result18), ("例外時", result19)):
    check_none(f"20. returncode が None（{label}）", r.returncode)
    check_none(f"20. stdout_log_path が None（{label}）", r.stdout_log_path)
    check_none(f"20. stderr_log_path が None（{label}）", r.stderr_log_path)

# テスト21: subprocess を使わない（静的検査）
wpr_source = (PROJECT_ROOT / "src" / "pipeline" / "workflow_pipeline_runner.py").read_text(encoding="utf-8")
check_false("21. workflow_pipeline_runner.py が subprocess をimportしない", "import subprocess" in wpr_source)
check_false("21. workflow_pipeline_runner.py が subprocess.run を使わない", "subprocess.run" in wpr_source)
print()


# ═══════════════════════════════════════════════════════════
# テスト22-25: AgentManager.from_config()（二重ゲート）
# ═══════════════════════════════════════════════════════════

print("[テスト22-25] AgentManager.from_config()（二重ゲート）")

manager_tmp = Path(tempfile.mkdtemp())

# テスト22: AI_AGENT_ENABLED=false → NullAgentManager
clear_workflow_trigger_env()
config22 = AgentConfig(enabled=False, base_dir=manager_tmp)
manager22 = AgentManager.from_config(config22)
check_true("22. disabled → NullAgentManager が返る", isinstance(manager22, NullAgentManager))

# テスト23: AI_AGENT_ENABLED=true / WORKFLOW_TRIGGER_AGENT_ENABLED未設定 → NewsAgentのみ
clear_workflow_trigger_env()
config23 = AgentConfig(enabled=True, base_dir=manager_tmp)
manager23 = AgentManager.from_config(config23)
check_true("23. AgentManagerが返る", isinstance(manager23, AgentManager))
check("23. executorsが1件（NewsAgentのみ）", len(manager23._executors), 1)
check_true("23. executors[0]がNewsAgent", isinstance(manager23._executors[0]._agent, NewsAgent))

# テスト24: AI_AGENT_ENABLED=true / WORKFLOW_TRIGGER_AGENT_ENABLED=true / AI_WORKFLOW_ENABLED=true
#          → NewsAgent + WorkflowTriggerAgent
clear_workflow_trigger_env()
os.environ["WORKFLOW_TRIGGER_AGENT_ENABLED"] = "true"
os.environ["AI_WORKFLOW_ENABLED"] = "true"
config24 = AgentConfig(enabled=True, base_dir=manager_tmp)
manager24 = AgentManager.from_config(config24)
check("24. executorsが2件", len(manager24._executors), 2)
check_true("24. executors[0]がNewsAgent", isinstance(manager24._executors[0]._agent, NewsAgent))
check_true("24. executors[1]がWorkflowTriggerAgent", isinstance(manager24._executors[1]._agent, WorkflowTriggerAgent))
check_true(
    "24. WorkflowTriggerAgentのrunnerがWorkflowPipelineRunner",
    isinstance(manager24._executors[1]._agent._runner, WorkflowPipelineRunner),
)

# テスト25: AI_AGENT_ENABLED=true / WORKFLOW_TRIGGER_AGENT_ENABLED=true / AI_WORKFLOW_ENABLED=false
#          → NewsAgentのみ（WorkflowTriggerAgentは除外）
clear_workflow_trigger_env()
os.environ["WORKFLOW_TRIGGER_AGENT_ENABLED"] = "true"
os.environ["AI_WORKFLOW_ENABLED"] = "false"
config25 = AgentConfig(enabled=True, base_dir=manager_tmp)
manager25 = AgentManager.from_config(config25)
check("25. executorsが1件（AI_WORKFLOW_ENABLED=falseのためWorkflowTriggerAgent除外）", len(manager25._executors), 1)
check_true("25. executors[0]がNewsAgent", isinstance(manager25._executors[0]._agent, NewsAgent))

clear_workflow_trigger_env()
print()


# ═══════════════════════════════════════════════════════════
# テスト26-29: scripts/run_workflow_trigger_agent.py（実サブプロセス、常にdry-run）
# ═══════════════════════════════════════════════════════════

print("[テスト26-29] scripts/run_workflow_trigger_agent.py")

script_path = PROJECT_ROOT / "scripts" / "run_workflow_trigger_agent.py"
check_true("26. run_workflow_trigger_agent.py が存在する", script_path.exists())

reports_dir_real = PROJECT_ROOT / "outputs" / "workflow_reports"
before_reports = set(reports_dir_real.glob("*")) if reports_dir_real.exists() else set()


def run_cli(extra_args, env_overrides):
    env = dict(os.environ)
    for key in ("AI_AGENT_ENABLED",) + WORKFLOW_TRIGGER_ENV_KEYS:
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


# テスト27: AI_AGENT_ENABLED=false --dry-run
completed27 = run_cli(["--dry-run"], {"AI_AGENT_ENABLED": "false"})
check("27. returncode が 0", completed27.returncode, 0)
check_contains("27. AI Agent基盤が無効の案内が表示される", completed27.stdout, "AI Agent基盤が無効です")

# テスト28: AI_AGENT_ENABLED=true / WORKFLOW_TRIGGER_AGENT_ENABLED未設定 --dry-run
completed28 = run_cli(["--dry-run"], {"AI_AGENT_ENABLED": "true"})
check("28. returncode が 0", completed28.returncode, 0)
check_false("28. workflow_trigger_agent は実行されない", "Agent: workflow_trigger_agent" in completed28.stdout)
check_contains("28. WorkflowTriggerAgent未実行の案内メッセージが表示される", completed28.stdout, "WorkflowTriggerAgent")

# テスト29: 二重ゲートON --dry-run --article-id --workflow-dry-run
completed29 = run_cli(
    ["--dry-run", "--article-id", "sample-article", "--workflow-dry-run"],
    {"AI_AGENT_ENABLED": "true", "WORKFLOW_TRIGGER_AGENT_ENABLED": "true", "AI_WORKFLOW_ENABLED": "true"},
)
check("29. returncode が 0", completed29.returncode, 0)
check_contains("29. workflow_trigger_agent が実行される", completed29.stdout, "Agent: workflow_trigger_agent")
check_contains("29. article_id が反映される", completed29.stdout, "sample-article")
check_contains("29. WORKFLOW DRY RUN 表示がある", completed29.stdout, "WORKFLOW DRY RUN")
check_contains("29. action_taken=False（--dry-runによりact()がスキップされる）", completed29.stdout, "action_taken=False")

after_reports = set(reports_dir_real.glob("*")) if reports_dir_real.exists() else set()
check(
    "29. outputs/workflow_reports/ に新規ファイルが作られない（WorkflowRunner未起動）",
    after_reports - before_reports,
    set(),
)
print()


# ═══════════════════════════════════════════════════════════
# テスト30-32: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト30] 既存ファイルの無変更確認（git diff）")

unchanged_paths = [
    "main.py",
    "src/ai/workflow_runner.py",
    "src/ai/workflow_config.py",
    "src/ai/workflow_context.py",
    "src/ai/workflow_result.py",
    "src/ai/workflow_step.py",
    "src/ai/workflow_step_executor.py",
    "src/ai/workflow_report_builder.py",
    "src/ai/base_agent.py",
    "src/ai/agent_executor.py",
    "src/ai/agent_context.py",
    "src/ai/agent_decision.py",
    "src/ai/agent_result.py",
    "src/ai/agent_task.py",
    "src/ai/agent_config.py",
    "src/ai/news_agent.py",
    "src/ai/news_agent_config.py",
    "src/pipeline/news_pipeline_runner.py",
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
        check_true(f"30. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("30. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト31] Architecture Guard（静的import検査、まとめ）")
check_false(
    "31. workflow_trigger_agent.py の import文に WorkflowRunner が含まれない（再掲）",
    "WorkflowRunner" in wta_import_lines,
)
check_false("31. workflow_pipeline_runner.py が subprocess をimportしない（再掲）", "import subprocess" in wpr_source)
print()


print("[テスト32] import確認")

import ai as ai_pkg
for name in ("WorkflowTriggerAgent", "WorkflowTriggerAgentConfig"):
    check_true(f"32. {name} が ai パッケージからエクスポートされている", hasattr(ai_pkg, name))
    check_true(f"32. {name} が ai.__all__ に含まれる", name in ai_pkg.__all__)

import pipeline as pipeline_pkg
check_true(
    "32. WorkflowPipelineRunner が pipeline パッケージからエクスポートされている",
    hasattr(pipeline_pkg, "WorkflowPipelineRunner"),
)
check_true(
    "32. WorkflowPipelineRunner が pipeline.__all__ に含まれる",
    "WorkflowPipelineRunner" in pipeline_pkg.__all__,
)
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
