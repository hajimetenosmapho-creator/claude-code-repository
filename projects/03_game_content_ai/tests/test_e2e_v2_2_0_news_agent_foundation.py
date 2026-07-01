"""
E2E テスト: v2.2.0 News Agent Foundation

テストシナリオ:
    ── NewsAgentConfig ──
    1.  from_env() のデフォルト値
    2.  from_env() の環境変数上書き

    ── PipelineResult ──
    3.  to_dict() / to_json()

    ── NewsPipelineRunner（subprocess.run はモック化）──
    4.  成功時（returncode=0）の PipelineResult
    5.  失敗時（returncode!=0）の PipelineResult
    6.  タイムアウト時（TimeoutExpired）の PipelineResult
    7.  stdout/stderr を logs/news_agent/ に保存する
    8.  max_articles を --max-articles として main.py に渡す
    9.  Agent層の型（AgentContext等）・WorkflowRunner をimportしない

    ── NewsAgent ──
    10. name() が "news_agent" を返す
    11. decide() 履歴なし → should_act=True
    12. decide() 間隔超過 → should_act=True
    13. decide() 間隔内 → should_act=False
    14. decide() 壊れたJSON行をwarningに記録してスキップ
    14b. decide() UTF-8として壊れたログファイル全体でも例外を投げず、
         warningを記録した上でshould_act=Trueになる（Release Review指摘1の回帰テスト）
    15. act() が NewsPipelineRunner.run() のみを呼ぶ
    16. act() が PipelineResult を AgentResult に変換する
    17. act() で workflow_result が常に None

    ── AgentExecutor 経由の dry_run 保証 ──
    18. dry_run=True では NewsPipelineRunner.run() が呼ばれない

    ── AgentManager ──
    19. AI_AGENT_ENABLED=false で NullAgentManager を返す
    20. AI_AGENT_ENABLED=true で NewsAgent入りAgentManagerを返す

    ── run_news_agent.py ──
    21. --dry-run で main.py（NewsPipelineRunner経由のsubprocess）を起動しない

    ── 構成・互換性 ──
    22. src/ai/__init__.py から NewsAgent / NewsAgentConfig をimportできる
    23. src/pipeline/__init__.py から PipelineResult / NewsPipelineRunner をimportできる
    24. WorkflowRunner / main.py / 既存ニュース収集パイプラインに変更がない（git diff）

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v2_2_0_news_agent_foundation.py
"""
import json
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
print("v2.2.0 News Agent Foundation E2E テスト")
print("=" * 60)
print()

from ai.news_agent_config import NewsAgentConfig
from pipeline.pipeline_result import PipelineResult
from pipeline.news_pipeline_runner import NewsPipelineRunner
from ai.news_agent import NewsAgent
from ai import (
    AgentContext, AgentDecision, AgentResult, AgentTask, AgentExecutor,
    AgentConfig, AgentManager, NullAgentManager,
)


# ═══════════════════════════════════════════════════════════
# テスト1-2: NewsAgentConfig
# ═══════════════════════════════════════════════════════════

print("[テスト1-2] NewsAgentConfig.from_env()")

for key in ("NEWS_AGENT_MIN_INTERVAL_MINUTES", "NEWS_AGENT_TIMEOUT_SEC", "NEWS_AGENT_LOG_LOOKBACK_DAYS"):
    os.environ.pop(key, None)

fake_root = Path(tempfile.mkdtemp())
cfg_default = NewsAgentConfig.from_env(project_root=fake_root)
check("1. デフォルト min_interval_minutes=180", cfg_default.min_interval_minutes, 180)
check("1. デフォルト timeout_sec=1800", cfg_default.timeout_sec, 1800)
check("1. デフォルト log_lookback_days=2", cfg_default.log_lookback_days, 2)
check("1. main_py_path が project_root/main.py", cfg_default.main_py_path, fake_root / "main.py")
check("1. working_directory が project_root", cfg_default.working_directory, fake_root)
check_true("1. python_executable が Path型", isinstance(cfg_default.python_executable, Path))

os.environ["NEWS_AGENT_MIN_INTERVAL_MINUTES"] = "60"
os.environ["NEWS_AGENT_TIMEOUT_SEC"] = "300"
os.environ["NEWS_AGENT_LOG_LOOKBACK_DAYS"] = "5"
cfg_override = NewsAgentConfig.from_env(project_root=fake_root)
check("2. 環境変数上書き min_interval_minutes=60", cfg_override.min_interval_minutes, 60)
check("2. 環境変数上書き timeout_sec=300", cfg_override.timeout_sec, 300)
check("2. 環境変数上書き log_lookback_days=5", cfg_override.log_lookback_days, 5)

for key in ("NEWS_AGENT_MIN_INTERVAL_MINUTES", "NEWS_AGENT_TIMEOUT_SEC", "NEWS_AGENT_LOG_LOOKBACK_DAYS"):
    os.environ.pop(key, None)
print()


# ═══════════════════════════════════════════════════════════
# テスト3: PipelineResult
# ═══════════════════════════════════════════════════════════

print("[テスト3] PipelineResult.to_dict() / to_json()")

pr = PipelineResult(
    success=True,
    returncode=0,
    elapsed_sec=1.5,
    stdout_log_path=Path("logs/news_agent/x_stdout.log"),
    stderr_log_path=Path("logs/news_agent/x_stderr.log"),
    error_message=None,
)
d = pr.to_dict()
required_keys = ["success", "returncode", "elapsed_sec", "stdout_log_path", "stderr_log_path", "error_message"]
for key in required_keys:
    check_true(f"3. to_dict() に {key} が含まれる", key in d)
check("3. to_dict() の success が正しい", d["success"], True)
check_true("3. to_dict() の stdout_log_path が str", isinstance(d["stdout_log_path"], str))

json_str = pr.to_json()
check_true("3. to_json() が str を返す", isinstance(json_str, str))
parsed = json.loads(json_str)
check("3. to_json() がパース可能で returncode が一致", parsed["returncode"], 0)

pr_none = PipelineResult(success=False, returncode=None, elapsed_sec=0.1,
                          stdout_log_path=None, stderr_log_path=None, error_message="err")
d_none = pr_none.to_dict()
check_none("3. stdout_log_path=None の場合 to_dict() も None", d_none["stdout_log_path"])
print()


# ═══════════════════════════════════════════════════════════
# テスト4-9: NewsPipelineRunner（subprocess.run はモック化）
# ═══════════════════════════════════════════════════════════

print("[テスト4-9] NewsPipelineRunner")

runner_tmp_dir = Path(tempfile.mkdtemp())
runner_cfg = NewsAgentConfig(
    min_interval_minutes=180,
    timeout_sec=1800,
    log_lookback_days=2,
    main_py_path=runner_tmp_dir / "main.py",
    working_directory=runner_tmp_dir,
    python_executable=Path(sys.executable),
)
runner = NewsPipelineRunner(runner_cfg)

# テスト4: 成功時
fake_success = MagicMock(returncode=0, stdout="collected news", stderr="")
with patch("pipeline.news_pipeline_runner.subprocess.run", return_value=fake_success) as mock_run4:
    result4 = runner.run(params={})
check_true("4. success=True（returncode=0）", result4.success)
check("4. returncode が 0", result4.returncode, 0)
check_true("4. elapsed_sec が0以上", result4.elapsed_sec >= 0)
check_none("4. error_message が None", result4.error_message)
check("4. cwd が working_directory", mock_run4.call_args.kwargs["cwd"], runner_cfg.working_directory)
check("4. timeout が timeout_sec", mock_run4.call_args.kwargs["timeout"], runner_cfg.timeout_sec)

# テスト5: 失敗時
fake_fail = MagicMock(returncode=1, stdout="", stderr="Traceback: something failed")
with patch("pipeline.news_pipeline_runner.subprocess.run", return_value=fake_fail):
    result5 = runner.run(params={})
check_false("5. success=False（returncode!=0）", result5.success)
check("5. returncode が 1", result5.returncode, 1)
check("5. error_message が stderr を含む", result5.error_message, "Traceback: something failed")

# テスト6: タイムアウト時
with patch(
    "pipeline.news_pipeline_runner.subprocess.run",
    side_effect=subprocess.TimeoutExpired(cmd="main.py", timeout=1800, output="partial", stderr=""),
):
    result6 = runner.run(params={})
check_false("6. success=False（タイムアウト）", result6.success)
check_none("6. returncode が None（タイムアウト）", result6.returncode)
check_contains("6. error_message に「タイムアウト」が含まれる", result6.error_message, "タイムアウト")

# テスト7: stdout/stderr が logs/news_agent/ に保存される
check_not_none("7. stdout_log_path が設定される（成功時）", result4.stdout_log_path)
check_not_none("7. stderr_log_path が設定される（成功時）", result4.stderr_log_path)
check_true(
    "7. stdout_log_path が logs/news_agent/ 配下",
    "logs/news_agent" in str(result4.stdout_log_path).replace("\\", "/"),
)
check_true("7. stdout_log_path のファイルが実在する", result4.stdout_log_path.exists())
check(
    "7. stdout_log_path の内容が一致する",
    result4.stdout_log_path.read_text(encoding="utf-8"),
    "collected news",
)

# テスト8: max_articles が --max-articles として main.py に渡される
fake_success8 = MagicMock(returncode=0, stdout="", stderr="")
with patch("pipeline.news_pipeline_runner.subprocess.run", return_value=fake_success8) as mock_run8:
    runner.run(params={"max_articles": 3})
cmd8 = mock_run8.call_args.args[0]
check_true("8. cmd に main_py_path が含まれる", str(runner_cfg.main_py_path) in cmd8)
check_true("8. cmd に --max-articles が含まれる", "--max-articles" in cmd8)
check_true("8. cmd に 3 が含まれる", "3" in cmd8)

fake_success8b = MagicMock(returncode=0, stdout="", stderr="")
with patch("pipeline.news_pipeline_runner.subprocess.run", return_value=fake_success8b) as mock_run8b:
    runner.run(params={})
cmd8b = mock_run8b.call_args.args[0]
check_false("8. max_articles未指定時は --max-articles を含まない", "--max-articles" in cmd8b)

# テスト9: Agent層の型・WorkflowRunnerに依存していないこと
# （docstring内の説明文に単語として登場する場合があるため、実際の import / from 文のみを検査する）
runner_source = (PROJECT_ROOT / "src" / "pipeline" / "news_pipeline_runner.py").read_text(encoding="utf-8")
import_lines = "\n".join(
    line for line in runner_source.splitlines()
    if line.strip().startswith("from ") or line.strip().startswith("import ")
)
forbidden_tokens = [
    "AgentContext", "AgentDecision", "AgentResult", "AgentManager",
    "BaseAgent", "AgentExecutor", "WorkflowRunner", "from ai", "import ai",
]
for token in forbidden_tokens:
    check_false(f"9. news_pipeline_runner.py の import文に {token!r} が含まれない", token in import_lines)
print()


# ═══════════════════════════════════════════════════════════
# テスト10: NewsAgent.name()
# ═══════════════════════════════════════════════════════════

print("[テスト10] NewsAgent.name()")

agent_tmp_dir = Path(tempfile.mkdtemp())
agent_cfg = NewsAgentConfig(
    min_interval_minutes=180, timeout_sec=1800, log_lookback_days=2,
    main_py_path=agent_tmp_dir / "main.py", working_directory=agent_tmp_dir,
    python_executable=Path(sys.executable),
)
mock_runner = MagicMock()
agent = NewsAgent(agent_cfg, mock_runner)
check("10. name() が news_agent を返す", agent.name(), "news_agent")
print()


def make_context(params=None, dry_run=False):
    return AgentContext(
        task=AgentTask(task_id="collect_news", params=params or {}),
        dry_run=dry_run,
        run_id="test-run",
        agent_name="news_agent",
    )


def write_execution_log(log_dir: Path, date_str: str, lines: list):
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / f"{date_str}_execution.jsonl"
    with path.open("a", encoding="utf-8") as f:
        for line in lines:
            f.write(line + "\n")
    return path


base_execution_entry = {
    "executed_at": "", "finished_at": "", "execution_time_sec": 1.0,
    "total_collected": 1, "total_filtered": 1, "total_deduped": 1, "total_generated": 1,
    "total_wp_success": 0, "total_wp_failed": 0, "total_wp_skipped": 0,
    "api_call_count": 0, "result": "success",
}


# ═══════════════════════════════════════════════════════════
# テスト11-14: NewsAgent.decide()
# ═══════════════════════════════════════════════════════════

print("[テスト11-14] NewsAgent.decide()")

# テスト11: 履歴なし
decide_tmp11 = Path(tempfile.mkdtemp())
cfg11 = NewsAgentConfig(min_interval_minutes=180, timeout_sec=1800, log_lookback_days=2,
                         main_py_path=decide_tmp11 / "main.py", working_directory=decide_tmp11,
                         python_executable=Path(sys.executable))
agent11 = NewsAgent(cfg11, MagicMock())
decision11 = agent11.decide(make_context())
check_true("11. 履歴なし → should_act=True", decision11.should_act)
check_contains("11. reasonに初回実行の旨が含まれる", decision11.reason, "初回実行")

# テスト12: 間隔超過（250分前）
decide_tmp12 = Path(tempfile.mkdtemp())
cfg12 = NewsAgentConfig(min_interval_minutes=180, timeout_sec=1800, log_lookback_days=2,
                         main_py_path=decide_tmp12 / "main.py", working_directory=decide_tmp12,
                         python_executable=Path(sys.executable))
old_time = (datetime.now().astimezone() - timedelta(minutes=250)).isoformat()
entry12 = dict(base_execution_entry, executed_at=old_time, finished_at=old_time)
log_dir12 = decide_tmp12 / "logs" / "execution"
date_str12 = datetime.now().strftime("%Y%m%d")
write_execution_log(log_dir12, date_str12, [json.dumps(entry12, ensure_ascii=False)])
agent12 = NewsAgent(cfg12, MagicMock())
decision12 = agent12.decide(make_context())
check_true("12. 250分経過（基準180分）→ should_act=True", decision12.should_act)
check_contains("12. reasonに経過分数が含まれる", decision12.reason, "250.0分")
check_contains("12. reasonに基準分数が含まれる", decision12.reason, "180分")

# テスト13: 間隔内（30分前）
decide_tmp13 = Path(tempfile.mkdtemp())
cfg13 = NewsAgentConfig(min_interval_minutes=180, timeout_sec=1800, log_lookback_days=2,
                         main_py_path=decide_tmp13 / "main.py", working_directory=decide_tmp13,
                         python_executable=Path(sys.executable))
recent_time = (datetime.now().astimezone() - timedelta(minutes=30)).isoformat()
entry13 = dict(base_execution_entry, executed_at=recent_time, finished_at=recent_time)
log_dir13 = decide_tmp13 / "logs" / "execution"
date_str13 = datetime.now().strftime("%Y%m%d")
write_execution_log(log_dir13, date_str13, [json.dumps(entry13, ensure_ascii=False)])
agent13 = NewsAgent(cfg13, MagicMock())
decision13 = agent13.decide(make_context())
check_false("13. 30分経過（基準180分未満）→ should_act=False", decision13.should_act)
check_contains("13. reasonに経過分数が含まれる", decision13.reason, "30.0分")
check_contains("13. reasonに残り分数が含まれる", decision13.reason, "150.0分")
check_contains("13. reasonに基準分数が含まれる", decision13.reason, "180分")

# テスト14: 壊れたJSON行をwarningに記録してスキップ
decide_tmp14 = Path(tempfile.mkdtemp())
cfg14 = NewsAgentConfig(min_interval_minutes=180, timeout_sec=1800, log_lookback_days=2,
                         main_py_path=decide_tmp14 / "main.py", working_directory=decide_tmp14,
                         python_executable=Path(sys.executable))
recent_time14 = (datetime.now().astimezone() - timedelta(minutes=30)).isoformat()
entry14 = dict(base_execution_entry, executed_at=recent_time14, finished_at=recent_time14)
log_dir14 = decide_tmp14 / "logs" / "execution"
date_str14 = datetime.now().strftime("%Y%m%d")
write_execution_log(log_dir14, date_str14, ["{broken json", json.dumps(entry14, ensure_ascii=False)])
agent14 = NewsAgent(cfg14, MagicMock())
ctx14 = make_context()
decision14 = agent14.decide(ctx14)
check_false("14. 壊れた行があっても正常な行から判断（30分経過→False）", decision14.should_act)
check_true("14. 壊れた行が context.warnings に記録される", len(ctx14.warnings) >= 1)
check_true(
    "14. decide()は書き込みを行わない（ファイル数が増えない）",
    len(list(log_dir14.iterdir())) == 1,
)

# テスト14b: UTF-8として壊れたログファイル全体（Release Review指摘1の回帰テスト）
decide_tmp14b = Path(tempfile.mkdtemp())
cfg14b = NewsAgentConfig(min_interval_minutes=180, timeout_sec=1800, log_lookback_days=2,
                          main_py_path=decide_tmp14b / "main.py", working_directory=decide_tmp14b,
                          python_executable=Path(sys.executable))
log_dir14b = decide_tmp14b / "logs" / "execution"
log_dir14b.mkdir(parents=True, exist_ok=True)
date_str14b = datetime.now().strftime("%Y%m%d")
broken_path14b = log_dir14b / f"{date_str14b}_execution.jsonl"
broken_path14b.write_bytes(b"\xff\xfe\x00\x01invalid utf-8 bytes \x80\x81\xfe")

agent14b = NewsAgent(cfg14b, MagicMock())
ctx14b = make_context()
decision14b = None
try:
    decision14b = agent14b.decide(ctx14b)
    check_true("14b. UTF-8として壊れたログファイルでも decide() が例外を投げない", True)
except Exception as e:
    check_true(f"14b. UTF-8として壊れたログファイルでも decide() が例外を投げない（失敗: {e!r}）", False)

if decision14b is not None:
    check_true("14b. 判断不能時は should_act=True になる", decision14b.should_act)
    check_true("14b. 壊れたログファイルが context.warnings に記録される", len(ctx14b.warnings) >= 1)
print()


# ═══════════════════════════════════════════════════════════
# テスト15-17: NewsAgent.act()
# ═══════════════════════════════════════════════════════════

print("[テスト15-17] NewsAgent.act()")

act_tmp = Path(tempfile.mkdtemp())
cfg_act = NewsAgentConfig(min_interval_minutes=180, timeout_sec=1800, log_lookback_days=2,
                          main_py_path=act_tmp / "main.py", working_directory=act_tmp,
                          python_executable=Path(sys.executable))

# 成功時
mock_runner15 = MagicMock()
mock_runner15.run.return_value = PipelineResult(
    success=True, returncode=0, elapsed_sec=5.0,
    stdout_log_path=act_tmp / "stdout.log", stderr_log_path=act_tmp / "stderr.log",
    error_message=None,
)
agent15 = NewsAgent(cfg_act, mock_runner15)
ctx15 = make_context(params={"max_articles": 3})
ctx15.started_at = datetime.now()
ctx15.finished_at = datetime.now()
decision15 = AgentDecision(should_act=True, reason="テスト用")
result15 = agent15.act(decision15, ctx15)

check("15. runner.run が1回だけ呼ばれる", mock_runner15.run.call_count, 1)
check(
    "15. runner.run が context.task.params を渡す",
    mock_runner15.run.call_args.kwargs["params"],
    {"max_articles": 3},
)
check_true("16. AgentResult型が返る", isinstance(result15, AgentResult))
check_true("16. action_taken=True", result15.action_taken)
check_true("16. success が PipelineResult.success と一致", result15.success)
check_none("17. workflow_result が None（成功時）", result15.workflow_result)
check_true("16. warningsにstdoutログパスが含まれる", any("stdout" in w for w in result15.warnings))
check_true("16. warningsにstderrログパスが含まれる", any("stderr" in w for w in result15.warnings))

# 失敗時
mock_runner16 = MagicMock()
mock_runner16.run.return_value = PipelineResult(
    success=False, returncode=1, elapsed_sec=1.0,
    stdout_log_path=None, stderr_log_path=None, error_message="boom",
)
agent16 = NewsAgent(cfg_act, mock_runner16)
ctx16 = make_context()
ctx16.started_at = datetime.now()
ctx16.finished_at = datetime.now()
result16 = agent16.act(AgentDecision(True, "テスト用"), ctx16)
check_false("16. success=False（PipelineResult.success=False）", result16.success)
check("16. error_message が PipelineResult.error_message と一致", result16.error_message, "boom")
check_none("17. workflow_result が None（失敗時も）", result16.workflow_result)

# act() が dry_run=True の context で呼ばれた場合、assertで契約違反を検出する
ctx_dry = make_context(dry_run=True)
try:
    agent15.act(AgentDecision(True, "テスト"), ctx_dry)
    check_true("15. dry_run=Trueでのact()直接呼び出しはAssertionErrorになる", False)
except AssertionError:
    check_true("15. dry_run=Trueでのact()直接呼び出しはAssertionErrorになる", True)
print()


# ═══════════════════════════════════════════════════════════
# テスト18: dry_run=True では NewsPipelineRunner.run() が呼ばれない
# ═══════════════════════════════════════════════════════════

print("[テスト18] dry_run=True の保証（AgentExecutor経由）")

dryrun_tmp = Path(tempfile.mkdtemp())
cfg18 = NewsAgentConfig(min_interval_minutes=180, timeout_sec=1800, log_lookback_days=2,
                         main_py_path=dryrun_tmp / "main.py", working_directory=dryrun_tmp,
                         python_executable=Path(sys.executable))
mock_runner18 = MagicMock()
agent18 = NewsAgent(cfg18, mock_runner18)
executor18 = AgentExecutor(agent18)
ctx18 = AgentContext(task=AgentTask(task_id="collect_news"), dry_run=True, run_id="run-18", agent_name="")
result18 = executor18.execute(ctx18)

check("18. runner.run が呼ばれない（call_count=0）", mock_runner18.run.call_count, 0)
check_false("18. action_taken=False", result18.action_taken)
check_true("18. success=True（判断プロセスは正常完了）", result18.success)
print()


# ═══════════════════════════════════════════════════════════
# テスト19-20: AgentManager.from_config()
# ═══════════════════════════════════════════════════════════

print("[テスト19-20] AgentManager.from_config()")

manager_tmp = Path(tempfile.mkdtemp())

config19 = AgentConfig(enabled=False, base_dir=manager_tmp)
manager19 = AgentManager.from_config(config19)
check_true("19. disabled → NullAgentManager が返る", isinstance(manager19, NullAgentManager))
check_false("19. is_available() が False", manager19.is_available())

config20 = AgentConfig(enabled=True, base_dir=manager_tmp)
manager20 = AgentManager.from_config(config20)
check_true("20. enabled → AgentManager が返る", isinstance(manager20, AgentManager))
check_true("20. is_available() が True", manager20.is_available())
check("20. executors が1件", len(manager20._executors), 1)
check_true("20. executors[0] が AgentExecutor", isinstance(manager20._executors[0], AgentExecutor))
check_true("20. Agent が NewsAgent", isinstance(manager20._executors[0]._agent, NewsAgent))
check("20. NewsAgent.name() が news_agent", manager20._executors[0]._agent.name(), "news_agent")
check_true(
    "20. NewsAgentのrunnerがNewsPipelineRunner",
    isinstance(manager20._executors[0]._agent._runner, NewsPipelineRunner),
)
print()


# ═══════════════════════════════════════════════════════════
# テスト21: scripts/run_news_agent.py --dry-run
# ═══════════════════════════════════════════════════════════

print("[テスト21] scripts/run_news_agent.py --dry-run")

news_agent_log_dir = PROJECT_ROOT / "logs" / "news_agent"
before_files = set(news_agent_log_dir.glob("*")) if news_agent_log_dir.exists() else set()

env21 = dict(os.environ)
env21["AI_AGENT_ENABLED"] = "true"
env21["PYTHONIOENCODING"] = "utf-8"
completed21 = subprocess.run(
    [sys.executable, str(PROJECT_ROOT / "scripts" / "run_news_agent.py"), "--dry-run"],
    cwd=str(PROJECT_ROOT),
    capture_output=True,
    text=True,
    encoding="utf-8",
    errors="replace",
    env=env21,
    timeout=60,
)
check("21. returncode が 0", completed21.returncode, 0)
check_contains("21. 標準出力に DRY RUN の表示がある", completed21.stdout, "DRY RUN")

after_files = set(news_agent_log_dir.glob("*")) if news_agent_log_dir.exists() else set()
check("21. logs/news_agent/ に新規ファイルが作られない（main.py未起動）", after_files - before_files, set())
print()


# ═══════════════════════════════════════════════════════════
# テスト22-23: 構成・互換性（import）
# ═══════════════════════════════════════════════════════════

print("[テスト22-23] import確認")

import ai as ai_pkg
for name in ("NewsAgent", "NewsAgentConfig"):
    check_true(f"22. {name} が ai パッケージからエクスポートされている", hasattr(ai_pkg, name))
    check_true(f"22. {name} が ai.__all__ に含まれる", name in ai_pkg.__all__)

import pipeline as pipeline_pkg
for name in ("PipelineResult", "NewsPipelineRunner"):
    check_true(f"23. {name} が pipeline パッケージからエクスポートされている", hasattr(pipeline_pkg, name))
    check_true(f"23. {name} が pipeline.__all__ に含まれる", name in pipeline_pkg.__all__)
print()


# ═══════════════════════════════════════════════════════════
# テスト24: WorkflowRunner / main.py / 既存パイプラインに変更がないこと
# ═══════════════════════════════════════════════════════════

print("[テスト24] 既存ファイルの無変更確認（git diff）")

unchanged_paths = [
    "main.py",
    "src/collector.py",
    "src/keyword_filter.py",
    "src/duplicate_filter.py",
    "src/importance_judge.py",
    "src/article_generator.py",
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
        check_true(f"24. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("24. gitが利用できないため無変更確認をスキップ", True)
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
