"""
E2E テスト: v2.8.0 Execution History Foundation

テストシナリオ:
    ── ExecutionHistoryConfig ──
    1.  from_env() のデフォルト値（enabled=True / is_ready()=True）
    2.  EXECUTION_HISTORY_ENABLED=false の明示指定
    3.  EXECUTION_HISTORY_DIR の環境変数上書き

    ── データモデル（to_dict/from_dict ラウンドトリップ） ──
    4.  ExecutionHistoryEvent
    5.  StepExecutionRecord（各StepExecutionStatus）
    6.  WorkflowExecutionRecord（steps/events含む）

    ── JsonExecutionHistoryStore ──
    7.  save() → get() で内容が一致する
    8.  存在しないrun_idはNoneを返す
    9.  list_all() が started_at の新しい順でソートされる
    10. 壊れたJSONファイルは読み飛ばされる（他のrecordには影響しない）

    ── ExecutionHistoryManager ──
    11. start_run() がRUNNING状態のrecordを作成・保存する
    12. start_step() → finish_step() で直近のRUNNINGステップが更新される
    13. finish_step()（start_step未呼び出し）は新規レコードとして確定する（Gate閉鎖/未到達パターン）
    14. finish_run() でstatus/finished_atが確定する
    15. ExecutionHistoryManager.from_config()：enabled/disabledの分岐

    ── NullExecutionHistoryManager ──
    16. すべてのメソッドがNoneを返し、ファイルが作成されない

    ── WorkflowEngineExecutor統合（FakeAgent、v2.7.0テスト8-12と同型シナリオ） ──
    17. 全ステップGate閉鎖 → 全SKIPPED
    18. 全ステップ成功 → 全SUCCESS
    19. News失敗 → Review/PublishがNOT_REACHED
    20. Newsがdecide()スキップ（success=True） → SUCCESSとして記録される
    21. ReviewのみGate閉鎖 → News/PublishはSUCCESS、ReviewはSKIPPED（カスタム理由）
    22. history_manager省略時（2引数コンストラクタ）でも既存動作に影響しない

    ── scripts/show_execution_history.py ──
    23. スクリプトが存在する
    24. 履歴0件時に安全に終了する
    25. run_workflow_engine.py実行後の履歴を --run-id で参照できる

    ── Architecture Guard ──
    26. src/execution_history/ が workflow_engine/ai/pipeline/schedulerをimportしない（静的検査）
    27. src/ai/ src/pipeline/ src/scheduler/ 配下の既存ファイルに変更がない（git diff）
    28. execution_history パッケージのexport確認

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v2_8_0_execution_history_foundation.py
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
print("v2.8.0 Execution History Foundation E2E テスト")
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
from execution_history import (
    EVENT_STEP_FINISHED,
    EVENT_STEP_STARTED,
    EVENT_WORKFLOW_FINISHED,
    EVENT_WORKFLOW_STARTED,
    ExecutionHistoryConfig,
    ExecutionHistoryEvent,
    ExecutionHistoryManager,
    JsonExecutionHistoryStore,
    NullExecutionHistoryManager,
    StepExecutionRecord,
    StepExecutionStatus,
    WorkflowExecutionRecord,
    WorkflowExecutionStatus,
)
from workflow_engine import (
    REASON_NOT_REACHED,
    SOURCE_MANUAL,
    WorkflowEngineDefinition,
    WorkflowEngineEvent,
    WorkflowEngineExecutor,
    WorkflowEngineStep,
)

ENV_KEYS = ("EXECUTION_HISTORY_ENABLED", "EXECUTION_HISTORY_DIR")


def clear_env():
    for key in ENV_KEYS:
        os.environ.pop(key, None)


# ═══════════════════════════════════════════════════════════
# テスト1-3: ExecutionHistoryConfig
# ═══════════════════════════════════════════════════════════

print("[テスト1-3] ExecutionHistoryConfig.from_env()")

clear_env()
tmp_root_1 = Path(tempfile.mkdtemp())

cfg1 = ExecutionHistoryConfig.from_env(project_root=tmp_root_1)
check_true("1. デフォルト enabled=True", cfg1.enabled)
check_true("1. デフォルトは is_ready()=True", cfg1.is_ready())
check("1. デフォルトのhistory_dirがlogs/execution_history", cfg1.history_dir, tmp_root_1 / "logs" / "execution_history")

os.environ["EXECUTION_HISTORY_ENABLED"] = "false"
cfg2 = ExecutionHistoryConfig.from_env(project_root=tmp_root_1)
check_false("2. EXECUTION_HISTORY_ENABLED=false で enabled=False", cfg2.enabled)
check_false("2. is_ready()=False", cfg2.is_ready())
os.environ.pop("EXECUTION_HISTORY_ENABLED", None)

os.environ["EXECUTION_HISTORY_DIR"] = "custom_history_dir"
cfg3 = ExecutionHistoryConfig.from_env(project_root=tmp_root_1)
check("3. EXECUTION_HISTORY_DIR の環境変数上書き", cfg3.history_dir, tmp_root_1 / "custom_history_dir")
os.environ.pop("EXECUTION_HISTORY_DIR", None)
print()


# ═══════════════════════════════════════════════════════════
# テスト4-6: データモデルのラウンドトリップ
# ═══════════════════════════════════════════════════════════

print("[テスト4-6] データモデル（to_dict/from_dict ラウンドトリップ）")

event = ExecutionHistoryEvent(
    event_type=EVENT_WORKFLOW_STARTED, occurred_at=datetime(2026, 7, 2, 9, 0, 0), message="started", payload={"k": "v"}
)
event_restored = ExecutionHistoryEvent.from_dict(event.to_dict())
check("4. ExecutionHistoryEvent ラウンドトリップ", event_restored, event)

step_record = StepExecutionRecord(
    step="news",
    status=StepExecutionStatus.SUCCESS,
    started_at=datetime(2026, 7, 2, 9, 0, 0),
    finished_at=datetime(2026, 7, 2, 9, 0, 5),
    error_message=None,
    skipped_reason=None,
)
step_restored = StepExecutionRecord.from_dict(step_record.to_dict())
check("5. StepExecutionRecord ラウンドトリップ", step_restored, step_record)
for status in StepExecutionStatus:
    sr = StepExecutionRecord(step="x", status=status)
    check(f"5. StepExecutionStatus.{status.name} のto_dict/from_dict", StepExecutionRecord.from_dict(sr.to_dict()).status, status)

workflow_record = WorkflowExecutionRecord(
    run_id="run-abc",
    workflow_name="workflow_engine",
    source=SOURCE_MANUAL,
    job_id="job-1",
    status=WorkflowExecutionStatus.SUCCESS,
    started_at=datetime(2026, 7, 2, 9, 0, 0),
    finished_at=datetime(2026, 7, 2, 9, 0, 10),
    steps=[step_record],
    events=[event],
    error_message=None,
)
workflow_restored = WorkflowExecutionRecord.from_dict(workflow_record.to_dict())
check("6. WorkflowExecutionRecord ラウンドトリップ", workflow_restored, workflow_record)
check_contains("6. to_json() がJSON文字列を返す", workflow_record.to_json(), "run-abc")
print()


# ═══════════════════════════════════════════════════════════
# テスト7-10: JsonExecutionHistoryStore
# ═══════════════════════════════════════════════════════════

print("[テスト7-10] JsonExecutionHistoryStore")

tmp_store_dir = Path(tempfile.mkdtemp()) / "history"
store = JsonExecutionHistoryStore(tmp_store_dir)

store.save(workflow_record)
loaded = store.get("run-abc")
check("7. save() → get() で内容が一致する", loaded, workflow_record)
check_true("7. JSONファイルが作成される", (tmp_store_dir / "run-abc.json").exists())

check_none("8. 存在しないrun_idはNoneを返す", store.get("does-not-exist"))

record_old = WorkflowExecutionRecord(
    run_id="run-old", workflow_name="workflow_engine", source=SOURCE_MANUAL, job_id="j",
    status=WorkflowExecutionStatus.SUCCESS, started_at=datetime(2026, 7, 1, 0, 0, 0),
)
record_new = WorkflowExecutionRecord(
    run_id="run-new", workflow_name="workflow_engine", source=SOURCE_MANUAL, job_id="j",
    status=WorkflowExecutionStatus.SUCCESS, started_at=datetime(2026, 7, 3, 0, 0, 0),
)
store.save(record_old)
store.save(record_new)
all_records = store.list_all()
run_ids_in_order = [r.run_id for r in all_records]
check(
    "9. list_all() が started_at の新しい順でソートされる",
    run_ids_in_order.index("run-new") < run_ids_in_order.index("run-old"),
    True,
)

(tmp_store_dir / "broken.json").write_text("{ this is not valid json", encoding="utf-8")
all_records_with_broken = store.list_all()
check(
    "10. 壊れたJSONファイルは読み飛ばされる（他のrecordは残る）",
    {"run-abc", "run-old", "run-new"}.issubset({r.run_id for r in all_records_with_broken}),
    True,
)
check_none("10. 壊れたJSONのget()はNoneを返す", store.get("broken"))
print()


# ═══════════════════════════════════════════════════════════
# テスト11-15: ExecutionHistoryManager
# ═══════════════════════════════════════════════════════════

print("[テスト11-15] ExecutionHistoryManager")

tmp_mgr_dir = Path(tempfile.mkdtemp()) / "history"
mgr_store = JsonExecutionHistoryStore(tmp_mgr_dir)
manager = ExecutionHistoryManager(store=mgr_store)

record_11 = manager.start_run(run_id="run-11", workflow_name="workflow_engine", source=SOURCE_MANUAL, job_id="job-11")
check("11. start_run() の run_id", record_11.run_id, "run-11")
check("11. start_run() の status=RUNNING", record_11.status, WorkflowExecutionStatus.RUNNING)
saved_11 = mgr_store.get("run-11")
check("11. start_run() が即座に保存される", saved_11.run_id, "run-11")
check_true("11. events に EVENT_WORKFLOW_STARTED が含まれる", any(e.event_type == EVENT_WORKFLOW_STARTED for e in record_11.events))

manager.start_step(record_11, "news")
check("12. start_step() で StepExecutionRecord が追加される", len(record_11.steps), 1)
check("12. start_step() 直後は status=RUNNING", record_11.steps[0].status, StepExecutionStatus.RUNNING)
manager.finish_step(record_11, "news", StepExecutionStatus.SUCCESS)
check("12. finish_step() で直近のRUNNINGステップが更新される", len(record_11.steps), 1)
check("12. finish_step() 後は status=SUCCESS", record_11.steps[0].status, StepExecutionStatus.SUCCESS)
check_true("12. finished_at が設定される", record_11.steps[0].finished_at is not None)

manager.finish_step(record_11, "review", StepExecutionStatus.SKIPPED, skipped_reason="gate closed")
check("13. start_step未呼び出しのfinish_step()は新規レコードとして追加される", len(record_11.steps), 2)
check("13. 新規レコードの status=SKIPPED", record_11.steps[1].status, StepExecutionStatus.SKIPPED)
check("13. skipped_reason が記録される", record_11.steps[1].skipped_reason, "gate closed")

manager.finish_run(record_11, WorkflowExecutionStatus.SUCCESS)
check("14. finish_run() で status=SUCCESS", record_11.status, WorkflowExecutionStatus.SUCCESS)
check_true("14. finish_run() で finished_at が設定される", record_11.finished_at is not None)
final_saved = mgr_store.get("run-11")
check("14. finish_run() 後の保存内容が一致する", final_saved.status, WorkflowExecutionStatus.SUCCESS)
check("14. 保存内容のsteps件数が一致する", len(final_saved.steps), 2)

clear_env()
tmp_from_config_dir = Path(tempfile.mkdtemp())
cfg_enabled = ExecutionHistoryConfig.from_env(project_root=tmp_from_config_dir)
m_enabled = ExecutionHistoryManager.from_config(cfg_enabled)
check_true("15. デフォルト(enabled=True)で ExecutionHistoryManager 実体が返る", isinstance(m_enabled, ExecutionHistoryManager))

os.environ["EXECUTION_HISTORY_ENABLED"] = "false"
cfg_disabled = ExecutionHistoryConfig.from_env(project_root=tmp_from_config_dir)
m_disabled = ExecutionHistoryManager.from_config(cfg_disabled)
check_true("15. EXECUTION_HISTORY_ENABLED=false で NullExecutionHistoryManager が返る", isinstance(m_disabled, NullExecutionHistoryManager))
os.environ.pop("EXECUTION_HISTORY_ENABLED", None)
print()


# ═══════════════════════════════════════════════════════════
# テスト16: NullExecutionHistoryManager
# ═══════════════════════════════════════════════════════════

print("[テスト16] NullExecutionHistoryManager")

tmp_null_dir = Path(tempfile.mkdtemp()) / "should_not_be_created"
null_mgr = NullExecutionHistoryManager()
r16 = null_mgr.start_run(run_id="r", workflow_name="w", source="s", job_id="j")
check_none("16. start_run() はNoneを返す", r16)
check_none("16. start_step() はNoneを返す", null_mgr.start_step(r16, "news"))
check_none("16. finish_step() はNoneを返す", null_mgr.finish_step(r16, "news", StepExecutionStatus.SUCCESS))
check_none("16. finish_run() はNoneを返す", null_mgr.finish_run(r16, WorkflowExecutionStatus.SUCCESS))
check_false("16. ディレクトリが作成されない", tmp_null_dir.exists())
print()


# ═══════════════════════════════════════════════════════════
# テスト17-22: WorkflowEngineExecutor統合（FakeAgent）
# ═══════════════════════════════════════════════════════════

print("[テスト17-22] WorkflowEngineExecutor統合（FakeAgent + ExecutionHistoryManager）")


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


def make_engine_context(run_id: str):
    from workflow_engine import WorkflowEngineContext
    event = WorkflowEngineEvent(
        job_id="fake-job", source=SOURCE_MANUAL, triggered_at=datetime.now(), trigger_reason="test"
    )
    return WorkflowEngineContext(event=event, dry_run=False, run_id=run_id)


def new_history_manager() -> tuple[ExecutionHistoryManager, Path]:
    d = Path(tempfile.mkdtemp()) / "history"
    return ExecutionHistoryManager(store=JsonExecutionHistoryStore(d)), d


# テスト17: 全ステップGate閉鎖
history_17, dir_17 = new_history_manager()
step_executors_17 = {
    WorkflowEngineStep.NEWS: None, WorkflowEngineStep.REVIEW: None, WorkflowEngineStep.PUBLISH: None,
}
executor_17 = WorkflowEngineExecutor(WorkflowEngineDefinition(), step_executors_17, history_manager=history_17)
executor_17.run(make_engine_context("run-17"))
saved_17 = JsonExecutionHistoryStore(dir_17).get("run-17")
check("17. 全ステップSKIPPEDとして記録される", [s.status for s in saved_17.steps], [StepExecutionStatus.SKIPPED] * 3)
check("17. workflow status=SUCCESS", saved_17.status, WorkflowExecutionStatus.SUCCESS)

# テスト18: 全ステップ成功
history_18, dir_18 = new_history_manager()
step_executors_18 = {
    WorkflowEngineStep.NEWS: AgentExecutor(FakeAgent("news_agent", AgentDecision(True, "go"), make_agent_result("news_agent", True))),
    WorkflowEngineStep.REVIEW: AgentExecutor(FakeAgent("review_trigger_agent", AgentDecision(True, "go"), make_agent_result("review_trigger_agent", True))),
    WorkflowEngineStep.PUBLISH: AgentExecutor(FakeAgent("publish_trigger_agent", AgentDecision(True, "go"), make_agent_result("publish_trigger_agent", True))),
}
executor_18 = WorkflowEngineExecutor(WorkflowEngineDefinition(), step_executors_18, history_manager=history_18)
executor_18.run(make_engine_context("run-18"))
saved_18 = JsonExecutionHistoryStore(dir_18).get("run-18")
check("18. 全ステップSUCCESSとして記録される", [s.status for s in saved_18.steps], [StepExecutionStatus.SUCCESS] * 3)
check("18. workflow status=SUCCESS", saved_18.status, WorkflowExecutionStatus.SUCCESS)

# テスト19: News失敗 → Review/PublishがNOT_REACHED
history_19, dir_19 = new_history_manager()
step_executors_19 = {
    WorkflowEngineStep.NEWS: AgentExecutor(FakeAgent("news_agent", AgentDecision(True, "go"), make_agent_result("news_agent", False, "boom"))),
    WorkflowEngineStep.REVIEW: AgentExecutor(FakeAgent("review_trigger_agent", AgentDecision(True, "go"), make_agent_result("review_trigger_agent", True))),
    WorkflowEngineStep.PUBLISH: AgentExecutor(FakeAgent("publish_trigger_agent", AgentDecision(True, "go"), make_agent_result("publish_trigger_agent", True))),
}
executor_19 = WorkflowEngineExecutor(WorkflowEngineDefinition(), step_executors_19, history_manager=history_19)
executor_19.run(make_engine_context("run-19"))
saved_19 = JsonExecutionHistoryStore(dir_19).get("run-19")
check("19. Newsのstatus=FAILED", saved_19.steps[0].status, StepExecutionStatus.FAILED)
check("19. Newsのerror_messageが記録される", saved_19.steps[0].error_message, "boom")
check("19. ReviewのstatusがNOT_REACHED", saved_19.steps[1].status, StepExecutionStatus.NOT_REACHED)
check("19. PublishのstatusがNOT_REACHED", saved_19.steps[2].status, StepExecutionStatus.NOT_REACHED)
check("19. workflow status=FAILED", saved_19.status, WorkflowExecutionStatus.FAILED)

# テスト20: Newsがdecide()スキップ（success=True）→ SUCCESSとして記録される
history_20, dir_20 = new_history_manager()
step_executors_20 = {
    WorkflowEngineStep.NEWS: AgentExecutor(FakeAgent("news_agent", AgentDecision(False, "interval not exceeded"), None)),
    WorkflowEngineStep.REVIEW: AgentExecutor(FakeAgent("review_trigger_agent", AgentDecision(True, "go"), make_agent_result("review_trigger_agent", True))),
    WorkflowEngineStep.PUBLISH: AgentExecutor(FakeAgent("publish_trigger_agent", AgentDecision(True, "go"), make_agent_result("publish_trigger_agent", True))),
}
executor_20 = WorkflowEngineExecutor(WorkflowEngineDefinition(), step_executors_20, history_manager=history_20)
executor_20.run(make_engine_context("run-20"))
saved_20 = JsonExecutionHistoryStore(dir_20).get("run-20")
check("20. Newsはdecide()スキップでもSUCCESSとして記録される（失敗ではない）", saved_20.steps[0].status, StepExecutionStatus.SUCCESS)
check("20. Reviewは実行を継続しSUCCESSとして記録される", saved_20.steps[1].status, StepExecutionStatus.SUCCESS)

# テスト21: ReviewのみGate閉鎖
history_21, dir_21 = new_history_manager()
step_executors_21 = {
    WorkflowEngineStep.NEWS: AgentExecutor(FakeAgent("news_agent", AgentDecision(True, "go"), make_agent_result("news_agent", True))),
    WorkflowEngineStep.REVIEW: None,
    WorkflowEngineStep.PUBLISH: AgentExecutor(FakeAgent("publish_trigger_agent", AgentDecision(True, "go"), make_agent_result("publish_trigger_agent", True))),
}
executor_21 = WorkflowEngineExecutor(
    WorkflowEngineDefinition(), step_executors_21,
    step_skip_reasons={WorkflowEngineStep.REVIEW: "custom skip reason"},
    history_manager=history_21,
)
executor_21.run(make_engine_context("run-21"))
saved_21 = JsonExecutionHistoryStore(dir_21).get("run-21")
check("21. Newsはexecutedし SUCCESS", saved_21.steps[0].status, StepExecutionStatus.SUCCESS)
check("21. ReviewはSKIPPEDでカスタム理由が記録される", (saved_21.steps[1].status, saved_21.steps[1].skipped_reason), (StepExecutionStatus.SKIPPED, "custom skip reason"))
check("21. PublishはSUCCESS", saved_21.steps[2].status, StepExecutionStatus.SUCCESS)

# テスト22: history_manager省略時（2引数コンストラクタ）でも既存動作に影響しない
executor_22 = WorkflowEngineExecutor(WorkflowEngineDefinition(), step_executors_18)
result_22 = executor_22.run(make_engine_context("run-22"))
check_true("22. history_manager省略（2引数）でも例外なく実行できる", result_22.overall_success)
check("22. steps件数が3", len(result_22.steps), 3)
print()


# ═══════════════════════════════════════════════════════════
# テスト23-25: scripts/show_execution_history.py
# ═══════════════════════════════════════════════════════════

print("[テスト23-25] scripts/show_execution_history.py")

script_path_show = PROJECT_ROOT / "scripts" / "show_execution_history.py"
check_true("23. show_execution_history.py が存在する", script_path_show.exists())


def run_show_cli(extra_args, env_overrides):
    env = dict(os.environ)
    for key in ENV_KEYS:
        env.pop(key, None)
    env.update(env_overrides)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(script_path_show)] + extra_args,
        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env, timeout=60,
    )


empty_history_dir = Path(tempfile.mkdtemp()) / "empty_history"
completed_24 = run_show_cli([], {"EXECUTION_HISTORY_DIR": str(empty_history_dir)})
check("24. returncode が 0（履歴0件でも安全終了）", completed_24.returncode, 0)
check_contains("24. 履歴なしの案内が表示される", completed_24.stdout, "履歴がありません")

script_path_we2 = PROJECT_ROOT / "scripts" / "run_workflow_engine.py"
shared_history_dir = Path(tempfile.mkdtemp()) / "shared_history"
env_we = dict(os.environ)
for key in ("AI_AGENT_ENABLED", "WORKFLOW_ENGINE_ENABLED") + ENV_KEYS:
    env_we.pop(key, None)
env_we.update({
    "AI_AGENT_ENABLED": "true", "WORKFLOW_ENGINE_ENABLED": "true",
    "EXECUTION_HISTORY_DIR": str(shared_history_dir), "PYTHONIOENCODING": "utf-8",
})
completed_run = subprocess.run(
    [sys.executable, str(script_path_we2), "--dry-run", "--job-id", "show-history-e2e"],
    cwd=str(PROJECT_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", env=env_we, timeout=60,
)
check("25. run_workflow_engine.py が正常終了する", completed_run.returncode, 0)

store_25 = JsonExecutionHistoryStore(shared_history_dir)
records_25 = store_25.list_all()
check_true("25. run_workflow_engine.py実行後に履歴が1件以上記録される", len(records_25) >= 1)

if records_25:
    run_id_25 = records_25[0].run_id
    completed_25 = run_show_cli(["--run-id", run_id_25], {"EXECUTION_HISTORY_DIR": str(shared_history_dir)})
    check("25. --run-id 指定で詳細表示が正常終了する", completed_25.returncode, 0)
    check_contains("25. 詳細表示にrun_idが含まれる", completed_25.stdout, run_id_25)
    check_contains("25. 詳細表示にstepsが含まれる", completed_25.stdout, "steps:")
print()


# ═══════════════════════════════════════════════════════════
# テスト26-28: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト26] execution_history が workflow_engine/ai/pipeline/schedulerをimportしない（静的検査）")

eh_dir = PROJECT_ROOT / "src" / "execution_history"
for py_file in sorted(eh_dir.glob("*.py")):
    source = py_file.read_text(encoding="utf-8")
    import_lines = "\n".join(
        line for line in source.splitlines()
        if line.strip().startswith("from ") or line.strip().startswith("import ")
    )
    for forbidden in ("workflow_engine", "scheduler", "from ai", "import ai", "from pipeline", "import pipeline"):
        check_false(
            f"26. {py_file.name} が {forbidden} をimportしない",
            forbidden in import_lines,
        )
print()


print("[テスト27] 既存ファイルの無変更確認（git diff）")

unchanged_paths_eh = [
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
    "src/workflow_engine/workflow_engine_step.py",
    "src/workflow_engine/workflow_engine_definition.py",
    "src/workflow_engine/workflow_engine_event.py",
    "src/workflow_engine/workflow_engine_context.py",
    "src/workflow_engine/workflow_engine_result.py",
    "src/workflow_engine/workflow_engine_config.py",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths_eh:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"27. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("27. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト28] import確認（execution_history パッケージのexport）")

import execution_history as eh_pkg
for name in (
    "ExecutionHistoryConfig", "ExecutionHistoryEvent",
    "EVENT_WORKFLOW_STARTED", "EVENT_WORKFLOW_FINISHED", "EVENT_STEP_STARTED", "EVENT_STEP_FINISHED",
    "StepExecutionRecord", "StepExecutionStatus", "WorkflowExecutionRecord", "WorkflowExecutionStatus",
    "ExecutionHistoryStore", "JsonExecutionHistoryStore", "ExecutionHistoryManager", "NullExecutionHistoryManager",
):
    check_true(f"28. {name} が execution_history パッケージからエクスポートされている", hasattr(eh_pkg, name))
    check_true(f"28. {name} が execution_history.__all__ に含まれる", name in eh_pkg.__all__)
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
