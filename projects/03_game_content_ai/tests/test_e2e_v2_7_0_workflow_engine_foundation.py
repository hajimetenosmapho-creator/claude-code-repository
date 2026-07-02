"""
E2E テスト: v2.7.0 Workflow Engine Foundation

テストシナリオ:
    ── WorkflowEngineConfig ──
    1.  from_env() のデフォルト値（enabled=False / is_ready()=False）
    2.  WORKFLOW_ENGINE_ENABLED=true の環境変数上書き（is_ready()=True）
    3.  WORKFLOW_ENGINE_ENABLED=false の明示指定

    ── WorkflowEngineStep / ALL_WORKFLOW_ENGINE_STEPS ──
    4.  WorkflowEngineStepのメンバーがNEWS/REVIEW/PUBLISHの3種類のみ
    5.  ALL_WORKFLOW_ENGINE_STEPSの順序、WorkflowEngineDefinition()のデフォルト

    ── WorkflowEngineEvent ──
    6.  source=SOURCE_SCHEDULER（SchedulerEvent経由を想定した構築）
    7.  source=SOURCE_MANUAL（--job-id経由を想定した構築）

    ── WorkflowEngineExecutor.run()（FakeAgentによる単体テスト、副作用なし） ──
    8.  全ステップGate閉鎖 → 全スキップ、overall_success=True
    9.  News成功 → Review成功 → Publish成功（全executed=True）
    10. News失敗 → Review/Publishが未到達（REASON_NOT_REACHED）、stopped_early=True
    11. Newsがdecide()でスキップ（should_act=False）→ Reviewは実行を継続する
    12. ReviewのみGate閉鎖 → News/Publishは実行され、Reviewはカスタム理由でスキップされる
    13. いずれのケースでもWorkflowEngineResult.stepsの件数が定義ステップ数と一致する
    14. WorkflowEngineContextのstep_results / started_at / finished_atが更新される

    ── WorkflowEngineManager.from_config()（二重ゲート + ステップ別ゲート） ──
    15. 両方false → NullWorkflowEngineManager
    16. AI_AGENT_ENABLED=trueのみ → NullWorkflowEngineManager
    17. WORKFLOW_ENGINE_ENABLED=trueのみ → NullWorkflowEngineManager
    18. 両方true → WorkflowEngineManager実体
    19. Review/PublishゲートがデフォルトOFFの場合、Newsのみ実Agentとして実行される
    20. REVIEW_TRIGGER_AGENT_ENABLED=true で ReviewTriggerAgent（既存クラス）が実行される
    21. NullWorkflowEngineManager.run() はNoneを返し、is_available()=False

    ── scripts/run_workflow_engine.py（実サブプロセス、常にdry-run） ──
    22. スクリプトファイルが存在する
    23. 二重ゲートfalse --dry-run で安全に終了する
    24. 二重ゲートON --dry-run --job-id で実行され、outputs/配下に新規ファイルが作られない
    25. Scheduler経由（--job-id未指定）でも安全に完了する
    26. run_workflow_engine.py が NewsAgent/ReviewTriggerAgent/PublishTriggerAgentを直接importしない

    ── Architecture Guard ──
    27. 既存ファイル（ai/pipeline/scheduler配下・main.py）に変更がない（git diff）
    28. src/workflow_engine/ が src/scheduler/ をimportしない（静的検査）
    29. workflow_engine パッケージのexport確認

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v2_7_0_workflow_engine_foundation.py
"""
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

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


print("=" * 60)
print("v2.7.0 Workflow Engine Foundation E2E テスト")
print("=" * 60)
print()

from ai import (
    AgentConfig,
    AgentContext,
    AgentDecision,
    AgentExecutor,
    AgentResult,
    AgentTask,
    BaseAgent,
)
from workflow_engine import (
    ALL_WORKFLOW_ENGINE_STEPS,
    REASON_NOT_REACHED,
    SOURCE_MANUAL,
    SOURCE_SCHEDULER,
    NullWorkflowEngineManager,
    WorkflowEngineConfig,
    WorkflowEngineContext,
    WorkflowEngineDefinition,
    WorkflowEngineEvent,
    WorkflowEngineExecutor,
    WorkflowEngineManager,
    WorkflowEngineStep,
)

AGENT_ENV_KEYS = ("AI_AGENT_ENABLED",)
WORKFLOW_ENGINE_ENV_KEYS = ("WORKFLOW_ENGINE_ENABLED",)
REVIEW_TRIGGER_ENV_KEYS = (
    "REVIEW_TRIGGER_AGENT_ENABLED",
    "REVIEW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES",
)
PUBLISH_TRIGGER_ENV_KEYS = (
    "PUBLISH_TRIGGER_AGENT_ENABLED",
    "PUBLISH_TRIGGER_AGENT_MIN_INTERVAL_MINUTES",
    "AI_PUBLISH_ENABLED",
    "WORDPRESS_URL",
    "WORDPRESS_USERNAME",
    "WORDPRESS_APP_PASSWORD",
)
ALL_ENV_KEYS = AGENT_ENV_KEYS + WORKFLOW_ENGINE_ENV_KEYS + REVIEW_TRIGGER_ENV_KEYS + PUBLISH_TRIGGER_ENV_KEYS


def clear_all_env():
    for key in ALL_ENV_KEYS:
        os.environ.pop(key, None)


# ═══════════════════════════════════════════════════════════
# テスト1-3: WorkflowEngineConfig
# ═══════════════════════════════════════════════════════════

print("[テスト1-3] WorkflowEngineConfig.from_env()")

clear_all_env()
fake_root_cfg = Path(tempfile.mkdtemp())

cfg1 = WorkflowEngineConfig.from_env(project_root=fake_root_cfg)
check_false("1. デフォルト enabled=False", cfg1.enabled)
check("1. project_root が渡した値と一致", cfg1.project_root, fake_root_cfg)
check_false("1. デフォルトは is_ready()=False", cfg1.is_ready())

os.environ["WORKFLOW_ENGINE_ENABLED"] = "true"
cfg2 = WorkflowEngineConfig.from_env(project_root=fake_root_cfg)
check_true("2. WORKFLOW_ENGINE_ENABLED=true で enabled=True", cfg2.enabled)
check_true("2. is_ready()=True", cfg2.is_ready())
os.environ.pop("WORKFLOW_ENGINE_ENABLED", None)

os.environ["WORKFLOW_ENGINE_ENABLED"] = "false"
cfg3 = WorkflowEngineConfig.from_env(project_root=fake_root_cfg)
check_false("3. WORKFLOW_ENGINE_ENABLED=false で enabled=False", cfg3.enabled)
os.environ.pop("WORKFLOW_ENGINE_ENABLED", None)
print()


# ═══════════════════════════════════════════════════════════
# テスト4-5: WorkflowEngineStep / ALL_WORKFLOW_ENGINE_STEPS
# ═══════════════════════════════════════════════════════════

print("[テスト4-5] WorkflowEngineStep / ALL_WORKFLOW_ENGINE_STEPS")

check("4. WorkflowEngineStepのメンバーが3種類", len(list(WorkflowEngineStep)), 3)
check(
    "4. メンバー名がNEWS/REVIEW/PUBLISHの3種類のみ",
    {m.name for m in WorkflowEngineStep},
    {"NEWS", "REVIEW", "PUBLISH"},
)
check("5. ALL_WORKFLOW_ENGINE_STEPSが3件", len(ALL_WORKFLOW_ENGINE_STEPS), 3)
check(
    "5. ALL_WORKFLOW_ENGINE_STEPSの順序がNEWS→REVIEW→PUBLISH",
    ALL_WORKFLOW_ENGINE_STEPS,
    [WorkflowEngineStep.NEWS, WorkflowEngineStep.REVIEW, WorkflowEngineStep.PUBLISH],
)
check(
    "5. WorkflowEngineDefinition()のデフォルトがALL_WORKFLOW_ENGINE_STEPSと一致",
    WorkflowEngineDefinition().steps,
    list(ALL_WORKFLOW_ENGINE_STEPS),
)
print()


# ═══════════════════════════════════════════════════════════
# テスト6-7: WorkflowEngineEvent
# ═══════════════════════════════════════════════════════════

print("[テスト6-7] WorkflowEngineEvent")

event_scheduler = WorkflowEngineEvent(
    job_id="daily-job",
    source=SOURCE_SCHEDULER,
    triggered_at=datetime(2026, 7, 2, 9, 0),
    trigger_reason="Daily schedule matched.",
    metadata={"foo": "bar"},
)
check("6. source=SOURCE_SCHEDULER", event_scheduler.source, SOURCE_SCHEDULER)
check("6. SOURCE_SCHEDULERの実値が'scheduler'", SOURCE_SCHEDULER, "scheduler")
check("6. metadataが保持される", event_scheduler.metadata, {"foo": "bar"})

event_manual = WorkflowEngineEvent(
    job_id="manual-1",
    source=SOURCE_MANUAL,
    triggered_at=datetime.now(),
    trigger_reason="Manual invocation via --job-id.",
)
check("7. source=SOURCE_MANUAL", event_manual.source, SOURCE_MANUAL)
check("7. SOURCE_MANUALの実値が'manual'", SOURCE_MANUAL, "manual")
check("7. metadataのデフォルトが空dict", event_manual.metadata, {})
print()


# ═══════════════════════════════════════════════════════════
# テスト8-14: WorkflowEngineExecutor.run()（FakeAgent、副作用なし）
# ═══════════════════════════════════════════════════════════

print("[テスト8-14] WorkflowEngineExecutor.run()（FakeAgent）")


class FakeAgent(BaseAgent):
    """decide() / act() の戻り値を固定できるテスト専用のBaseAgent実装。"""

    def __init__(self, agent_name: str, decision: AgentDecision, act_result: AgentResult | None = None):
        self._agent_name = agent_name
        self._decision = decision
        self._act_result = act_result

    def name(self) -> str:
        return self._agent_name

    def decide(self, context: AgentContext) -> AgentDecision:
        return self._decision

    def act(self, decision: AgentDecision, context: AgentContext) -> AgentResult:
        return self._act_result


def make_agent_result(agent_name: str, success: bool, error_message: str | None = None) -> AgentResult:
    now = datetime.now()
    return AgentResult(
        run_id="fake-run",
        agent_name=agent_name,
        task=AgentTask(task_id="fake-task", params={}),
        decision=AgentDecision(should_act=True, reason="fake"),
        action_taken=True,
        success=success,
        workflow_result=None,
        error_message=error_message,
        started_at=now,
        finished_at=now,
        warnings=[],
    )


def make_engine_context(dry_run: bool = False) -> WorkflowEngineContext:
    event = WorkflowEngineEvent(
        job_id="fake-job", source=SOURCE_MANUAL, triggered_at=datetime.now(), trigger_reason="test"
    )
    return WorkflowEngineContext(event=event, dry_run=dry_run, run_id="fake-run-id")


# テスト8: 全ステップGate閉鎖
step_executors_8 = {
    WorkflowEngineStep.NEWS: None,
    WorkflowEngineStep.REVIEW: None,
    WorkflowEngineStep.PUBLISH: None,
}
executor_8 = WorkflowEngineExecutor(WorkflowEngineDefinition(), step_executors_8)
result_8 = executor_8.run(make_engine_context())
check_true("8. 全ステップGate閉鎖 → overall_success=True", result_8.overall_success)
check_false("8. stopped_early=False", result_8.stopped_early)
check("8. steps件数が3", len(result_8.steps), 3)
for sr in result_8.steps:
    check_false(f"8. {sr.step.value} executed=False", sr.executed)
    check_true(f"8. {sr.step.value} success=True（スキップは失敗ではない）", sr.success)

# テスト9: 全ステップ成功
step_executors_9 = {
    WorkflowEngineStep.NEWS: AgentExecutor(
        FakeAgent("news_agent", AgentDecision(True, "go"), make_agent_result("news_agent", True))
    ),
    WorkflowEngineStep.REVIEW: AgentExecutor(
        FakeAgent("review_trigger_agent", AgentDecision(True, "go"), make_agent_result("review_trigger_agent", True))
    ),
    WorkflowEngineStep.PUBLISH: AgentExecutor(
        FakeAgent("publish_trigger_agent", AgentDecision(True, "go"), make_agent_result("publish_trigger_agent", True))
    ),
}
executor_9 = WorkflowEngineExecutor(WorkflowEngineDefinition(), step_executors_9)
result_9 = executor_9.run(make_engine_context())
check_true("9. 全ステップ成功 → overall_success=True", result_9.overall_success)
check_false("9. stopped_early=False", result_9.stopped_early)
check("9. steps件数が3", len(result_9.steps), 3)
for sr in result_9.steps:
    check_true(f"9. {sr.step.value} executed=True", sr.executed)
    check_true(f"9. {sr.step.value} success=True", sr.success)

# テスト10: News失敗 → Review/Publishが未到達
step_executors_10 = {
    WorkflowEngineStep.NEWS: AgentExecutor(
        FakeAgent("news_agent", AgentDecision(True, "go"), make_agent_result("news_agent", False, "boom"))
    ),
    WorkflowEngineStep.REVIEW: AgentExecutor(
        FakeAgent("review_trigger_agent", AgentDecision(True, "go"), make_agent_result("review_trigger_agent", True))
    ),
    WorkflowEngineStep.PUBLISH: AgentExecutor(
        FakeAgent("publish_trigger_agent", AgentDecision(True, "go"), make_agent_result("publish_trigger_agent", True))
    ),
}
executor_10 = WorkflowEngineExecutor(WorkflowEngineDefinition(), step_executors_10)
result_10 = executor_10.run(make_engine_context())
check_false("10. News失敗 → overall_success=False", result_10.overall_success)
check_true("10. stopped_early=True", result_10.stopped_early)
news_sr_10, review_sr_10, publish_sr_10 = result_10.steps
check_true("10. Newsはexecuted=True", news_sr_10.executed)
check_false("10. Newsはsuccess=False", news_sr_10.success)
check_false("10. Reviewは未到達 executed=False", review_sr_10.executed)
check_false("10. Reviewはsuccess=False（未到達）", review_sr_10.success)
check("10. Reviewのskipped_reasonがREASON_NOT_REACHED", review_sr_10.skipped_reason, REASON_NOT_REACHED)
check_false("10. Publishは未到達 executed=False", publish_sr_10.executed)
check("10. Publishのskipped_reasonがREASON_NOT_REACHED", publish_sr_10.skipped_reason, REASON_NOT_REACHED)
check("10. steps件数が3（打ち切り後も記録される）", len(result_10.steps), 3)

# テスト11: Newsがdecide()でスキップ（should_act=False）→ Reviewは実行を継続する
step_executors_11 = {
    WorkflowEngineStep.NEWS: AgentExecutor(
        FakeAgent("news_agent", AgentDecision(False, "interval not exceeded"), None)
    ),
    WorkflowEngineStep.REVIEW: AgentExecutor(
        FakeAgent("review_trigger_agent", AgentDecision(True, "go"), make_agent_result("review_trigger_agent", True))
    ),
    WorkflowEngineStep.PUBLISH: AgentExecutor(
        FakeAgent("publish_trigger_agent", AgentDecision(True, "go"), make_agent_result("publish_trigger_agent", True))
    ),
}
executor_11 = WorkflowEngineExecutor(WorkflowEngineDefinition(), step_executors_11)
result_11 = executor_11.run(make_engine_context())
check_true("11. Newsがdecide()スキップでもoverall_success=True", result_11.overall_success)
check_false("11. stopped_early=False", result_11.stopped_early)
news_sr_11, review_sr_11, _ = result_11.steps
check_true("11. Newsはexecuted=True（Executorは呼ばれた）", news_sr_11.executed)
check_true("11. Newsはsuccess=True（action_taken=Falseだが失敗ではない）", news_sr_11.success)
check_true("11. Reviewは実行を継続する executed=True", review_sr_11.executed)
check_true("11. Reviewはsuccess=True", review_sr_11.success)

# テスト12: Reviewのみ Gate閉鎖 → News/Publishは実行、Reviewはカスタム理由でスキップ
step_executors_12 = {
    WorkflowEngineStep.NEWS: AgentExecutor(
        FakeAgent("news_agent", AgentDecision(True, "go"), make_agent_result("news_agent", True))
    ),
    WorkflowEngineStep.REVIEW: None,
    WorkflowEngineStep.PUBLISH: AgentExecutor(
        FakeAgent("publish_trigger_agent", AgentDecision(True, "go"), make_agent_result("publish_trigger_agent", True))
    ),
}
executor_12 = WorkflowEngineExecutor(
    WorkflowEngineDefinition(),
    step_executors_12,
    step_skip_reasons={WorkflowEngineStep.REVIEW: "custom skip reason"},
)
result_12 = executor_12.run(make_engine_context())
news_sr_12, review_sr_12, publish_sr_12 = result_12.steps
check_true("12. Newsはexecuted=True", news_sr_12.executed)
check_false("12. Reviewのみスキップ executed=False", review_sr_12.executed)
check("12. Reviewのskipped_reasonがカスタム理由と一致", review_sr_12.skipped_reason, "custom skip reason")
check_true("12. Publishはexecuted=True", publish_sr_12.executed)
check_true("12. overall_success=True", result_12.overall_success)
check("12. steps件数が3", len(result_12.steps), 3)

# テスト13: いずれのケースでもsteps件数が定義ステップ数と一致する（8-12の再確認）
for label, result in (
    ("8", result_8), ("9", result_9), ("10", result_10), ("11", result_11), ("12", result_12),
):
    check(f"13. テスト{label}のsteps件数がdefinition.steps数と一致", len(result.steps), 3)

# テスト14: WorkflowEngineContextの更新確認
context_14 = make_engine_context()
executor_14 = WorkflowEngineExecutor(WorkflowEngineDefinition(), step_executors_9)
result_14 = executor_14.run(context_14)
check("14. context.step_resultsがresult.stepsと一致", context_14.step_results, result_14.steps)
check(
    "14. context.started_at/finished_atが設定される",
    (context_14.started_at is not None, context_14.finished_at is not None),
    (True, True),
)
print()


# ═══════════════════════════════════════════════════════════
# テスト15-21: WorkflowEngineManager.from_config()
# ═══════════════════════════════════════════════════════════

print("[テスト15-21] WorkflowEngineManager.from_config()")

clear_all_env()
tmp_mgr = Path(tempfile.mkdtemp())


def make_configs():
    return AgentConfig.from_env(base_dir=tmp_mgr), WorkflowEngineConfig.from_env(project_root=tmp_mgr)


# テスト15: 両方false
clear_all_env()
ac15, wc15 = make_configs()
m15 = WorkflowEngineManager.from_config(ac15, wc15)
check_true(
    "15. AI_AGENT_ENABLED=false かつ WORKFLOW_ENGINE_ENABLED=false → NullWorkflowEngineManager",
    isinstance(m15, NullWorkflowEngineManager),
)

# テスト16: AI_AGENT_ENABLED=trueのみ
clear_all_env()
os.environ["AI_AGENT_ENABLED"] = "true"
ac16, wc16 = make_configs()
m16 = WorkflowEngineManager.from_config(ac16, wc16)
check_true("16. WORKFLOW_ENGINE_ENABLED=false → NullWorkflowEngineManager", isinstance(m16, NullWorkflowEngineManager))

# テスト17: WORKFLOW_ENGINE_ENABLED=trueのみ
clear_all_env()
os.environ["WORKFLOW_ENGINE_ENABLED"] = "true"
ac17, wc17 = make_configs()
m17 = WorkflowEngineManager.from_config(ac17, wc17)
check_true("17. AI_AGENT_ENABLED=false → NullWorkflowEngineManager", isinstance(m17, NullWorkflowEngineManager))

# テスト18: 両方true → WorkflowEngineManager実体
clear_all_env()
os.environ["AI_AGENT_ENABLED"] = "true"
os.environ["WORKFLOW_ENGINE_ENABLED"] = "true"
ac18, wc18 = make_configs()
m18 = WorkflowEngineManager.from_config(ac18, wc18)
check_true("18. 二重ゲート両方true → WorkflowEngineManager実体が返る", isinstance(m18, WorkflowEngineManager))
check_true("18. is_available()=True", m18.is_available())

# テスト19: Review/PublishゲートがデフォルトOFFの場合、Newsのみ実Agentとして実行される
event_19 = WorkflowEngineEvent(job_id="j19", source=SOURCE_MANUAL, triggered_at=datetime.now(), trigger_reason="t")
result_19 = m18.run(event_19, dry_run=True)
check("19. steps件数が3", len(result_19.steps), 3)
check_true("19. newsはexecuted=True（実Agentが構築されている）", result_19.steps[0].executed)
check(
    "19. newsのagent_nameがnews_agent（既存NewsAgentをそのままimportして使っている証跡）",
    result_19.steps[0].agent_result.agent_name,
    "news_agent",
)
check_false("19. reviewはgate閉鎖でexecuted=False", result_19.steps[1].executed)
check_false("19. publishはgate閉鎖でexecuted=False", result_19.steps[2].executed)

# テスト20: REVIEW_TRIGGER_AGENT_ENABLED=true で既存ReviewTriggerAgentが実行される
os.environ["REVIEW_TRIGGER_AGENT_ENABLED"] = "true"
ac20, wc20 = make_configs()
m20 = WorkflowEngineManager.from_config(ac20, wc20)
event_20 = WorkflowEngineEvent(job_id="j20", source=SOURCE_MANUAL, triggered_at=datetime.now(), trigger_reason="t")
result_20 = m20.run(event_20, dry_run=True)
check_true("20. REVIEW_TRIGGER_AGENT_ENABLED=true → reviewはexecuted=True", result_20.steps[1].executed)
check(
    "20. reviewのagent_nameがreview_trigger_agent（既存ReviewTriggerAgentをそのままimportして使っている証跡）",
    result_20.steps[1].agent_result.agent_name,
    "review_trigger_agent",
)
check_false("20. publishは引き続きgate閉鎖", result_20.steps[2].executed)
os.environ.pop("REVIEW_TRIGGER_AGENT_ENABLED", None)

# テスト21: NullWorkflowEngineManagerの挙動
check_none("21. NullWorkflowEngineManager.run() はNoneを返す", m15.run(event_19, dry_run=True))
check_false("21. NullWorkflowEngineManager.is_available()=False", m15.is_available())

clear_all_env()
print()


# ═══════════════════════════════════════════════════════════
# テスト22-26: scripts/run_workflow_engine.py（実サブプロセス、常にdry-run）
# ═══════════════════════════════════════════════════════════

print("[テスト22-26] scripts/run_workflow_engine.py")

script_path_we = PROJECT_ROOT / "scripts" / "run_workflow_engine.py"
check_true("22. run_workflow_engine.py が存在する", script_path_we.exists())

review_reports_dir = PROJECT_ROOT / "outputs" / "ai_publish_review_reports"
publish_reports_dir = PROJECT_ROOT / "outputs" / "ai_publish_reports"
before_review = set(review_reports_dir.glob("*")) if review_reports_dir.exists() else set()
before_publish = set(publish_reports_dir.glob("*")) if publish_reports_dir.exists() else set()


def run_we_cli(extra_args, env_overrides):
    env = dict(os.environ)
    for key in ALL_ENV_KEYS:
        env.pop(key, None)
    env.update(env_overrides)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(script_path_we)] + extra_args,
        cwd=str(PROJECT_ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        timeout=60,
    )


# テスト23: 二重ゲートfalse --dry-run
completed23 = run_we_cli(["--dry-run"], {"AI_AGENT_ENABLED": "false", "WORKFLOW_ENGINE_ENABLED": "false"})
check("23. returncode が 0", completed23.returncode, 0)
check_contains("23. Workflow Engineが無効の案内が表示される", completed23.stdout, "Workflow Engineが無効です")

# テスト24: 二重ゲートON --dry-run --job-id
completed24 = run_we_cli(
    ["--dry-run", "--job-id", "e2e-manual-test"],
    {"AI_AGENT_ENABLED": "true", "WORKFLOW_ENGINE_ENABLED": "true"},
)
check("24. returncode が 0", completed24.returncode, 0)
check_contains("24. Workflow Engine 完了 が表示される", completed24.stdout, "Workflow Engine 完了")
check_contains("24. newsステップが表示される", completed24.stdout, "ステップ: news")
check_contains("24. reviewステップが表示される（gate閉鎖でスキップ表示）", completed24.stdout, "ステップ: review")
check_contains("24. publishステップが表示される（gate閉鎖でスキップ表示）", completed24.stdout, "ステップ: publish")

after_review = set(review_reports_dir.glob("*")) if review_reports_dir.exists() else set()
after_publish = set(publish_reports_dir.glob("*")) if publish_reports_dir.exists() else set()
check("24. outputs/ai_publish_review_reports/ に新規ファイルが作られない", after_review - before_review, set())
check("24. outputs/ai_publish_reports/ に新規ファイルが作られない", after_publish - before_publish, set())

# テスト25: Scheduler経由（--job-id未指定）でも安全に完了する
completed25 = run_we_cli(["--dry-run"], {"AI_AGENT_ENABLED": "true", "WORKFLOW_ENGINE_ENABLED": "true"})
check("25. returncode が 0", completed25.returncode, 0)
if "実行対象のJobはありません" not in completed25.stdout:
    check_contains("25. 09:00台の実行だったためWorkflow Engineが起動した", completed25.stdout, "Workflow Engine 完了")
else:
    check_contains("25. 実行対象なしの案内が表示される", completed25.stdout, "実行対象のJobはありません")

# テスト26: 静的import検査
script_source_we = script_path_we.read_text(encoding="utf-8")
script_import_lines_we = "\n".join(
    line for line in script_source_we.splitlines()
    if line.strip().startswith("from ") or line.strip().startswith("import ")
)
for forbidden in ("NewsAgent", "ReviewTriggerAgent", "PublishTriggerAgent"):
    check_false(
        f"26. run_workflow_engine.py の import文に {forbidden} が含まれない",
        forbidden in script_import_lines_we,
    )
print()


# ═══════════════════════════════════════════════════════════
# テスト27-29: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト27] 既存ファイルの無変更確認（git diff）")

unchanged_paths_we = [
    "main.py",
    "src/ai/base_agent.py",
    "src/ai/agent_executor.py",
    "src/ai/agent_manager.py",
    "src/ai/agent_context.py",
    "src/ai/agent_decision.py",
    "src/ai/agent_result.py",
    "src/ai/agent_task.py",
    "src/ai/agent_config.py",
    "src/ai/news_agent.py",
    "src/ai/news_agent_config.py",
    "src/ai/review_trigger_agent.py",
    "src/ai/review_trigger_agent_config.py",
    "src/ai/publish_trigger_agent.py",
    "src/ai/publish_trigger_agent_config.py",
    "src/ai/workflow_trigger_agent.py",
    "src/ai/workflow_trigger_agent_config.py",
    "src/ai/workflow_step.py",
    "src/ai/workflow_context.py",
    "src/ai/workflow_result.py",
    "src/pipeline/news_pipeline_runner.py",
    "src/pipeline/review_pipeline_runner.py",
    "src/pipeline/publish_pipeline_runner.py",
    "src/pipeline/workflow_pipeline_runner.py",
    "src/pipeline/pipeline_result.py",
    "src/scheduler/scheduler_engine.py",
    "src/scheduler/scheduler_job.py",
    "src/scheduler/scheduler_event.py",
    "src/scheduler/scheduler_manager.py",
    "src/scheduler/scheduler_repository.py",
    "src/scheduler/scheduler_config.py",
    "src/scheduler/exceptions.py",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths_we:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT),
            capture_output=True,
            timeout=10,
        )
        check_true(f"27. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("27. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト28] workflow_engine が scheduler をimportしない（静的検査）")

we_dir = PROJECT_ROOT / "src" / "workflow_engine"
for py_file in sorted(we_dir.glob("*.py")):
    source = py_file.read_text(encoding="utf-8")
    import_lines = "\n".join(
        line for line in source.splitlines()
        if line.strip().startswith("from ") or line.strip().startswith("import ")
    )
    check_false(
        f"28. {py_file.name} が scheduler をimportしない",
        ("from scheduler" in import_lines) or ("import scheduler" in import_lines),
    )
print()


print("[テスト29] import確認（workflow_engine パッケージのexport）")

import workflow_engine as we_pkg
for name in (
    "WorkflowEngineStep", "ALL_WORKFLOW_ENGINE_STEPS", "WorkflowEngineDefinition",
    "WorkflowEngineEvent", "SOURCE_SCHEDULER", "SOURCE_MANUAL",
    "WorkflowEngineStepResult", "WorkflowEngineResult", "REASON_NOT_REACHED",
    "WorkflowEngineContext", "WorkflowEngineConfig", "WorkflowEngineExecutor",
    "WorkflowEngineManager", "NullWorkflowEngineManager",
):
    check_true(f"29. {name} が workflow_engine パッケージからエクスポートされている", hasattr(we_pkg, name))
    check_true(f"29. {name} が workflow_engine.__all__ に含まれる", name in we_pkg.__all__)
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
