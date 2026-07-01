"""
E2E テスト: v2.0.0 AI Agent Foundation

テストシナリオ:
    ── AgentTask ──
    1.  task_id / params が設定できる（params のデフォルトは空dict）

    ── AgentDecision ──
    2.  should_act / reason が設定できる

    ── AgentContext ──
    3.  elapsed_time が started_at/finished_at 未設定時に None、設定時に正しく計算される

    ── AgentResult ──
    4.  to_dict() / to_json() が全フィールドを含み、正しくパースできる

    ── AgentConfig ──
    5.  from_env() が AgentConfig を返す／is_ready() が enabled と一致する

    ── BaseAgent ABC ──
    6.  BaseAgent が ABC であり、name() / decide() / act() が抽象メソッド

    ── MockAgent（AgentExecutor 経由）──
    7.  decide() / act() が呼ばれる（should_act=True, dry_run=False）
    8.  should_act=False の場合、act() が呼ばれない
    9.  dry_run=True の場合、act() が呼ばれない
    10. decide() 例外時に AgentResult.success=False
    11. act() 例外時に AgentResult.success=False
    12. AgentExecutor が run_id / agent_name / started_at / finished_at を finalize で保証する

    ── AgentManager / NullAgentManager ──
    13. AgentManager.from_config() が disabled 時に NullAgentManager を返す
    14. AgentManager.from_config() が enabled 時に AgentManager を返す
    15. NullAgentManager.run() が空リストを返す

    ── 構成・互換性 ──
    16. __init__.py から新規9シンボルをimportできる
    17. 既存 Workflow Foundation の代表シンボルも引き続きimportできる
    18. Claude API を実際に呼び出さない

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v2_0_0_ai_agent_foundation.py
"""
import json
import os
import sys
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


# ─── モックAgent ───

from ai import BaseAgent, AgentDecision, AgentResult


class MockAgent(BaseAgent):
    """decide() / act() の呼び出しを記録するモックAgent。"""

    def __init__(self, should_act: bool = True):
        self._should_act  = should_act
        self.decide_called = False
        self.act_called     = False

    def name(self) -> str:
        return "mock_agent"

    def decide(self, context):
        self.decide_called = True
        return AgentDecision(should_act=self._should_act, reason="mock reason")

    def act(self, decision, context):
        self.act_called = True
        now = datetime.now()
        # わざと誤った run_id / agent_name を返し、
        # AgentExecutor._finalize() が context の値で上書きすることを検証する
        return AgentResult(
            run_id="WRONG_RUN_ID",
            agent_name="WRONG_AGENT_NAME",
            task=context.task,
            decision=decision,
            action_taken=True,
            success=True,
            workflow_result=None,
            error_message=None,
            started_at=now,
            finished_at=now,
        )


class DecideFailingAgent(BaseAgent):
    """decide() で例外を送出するAgent。"""

    def name(self) -> str:
        return "decide_failing_agent"

    def decide(self, context):
        raise ValueError("decide() 内で例外発生（テスト用）")

    def act(self, decision, context):
        raise AssertionError("act() は呼ばれてはいけない")


class ActFailingAgent(BaseAgent):
    """act() で例外を送出するAgent。"""

    def name(self) -> str:
        return "act_failing_agent"

    def decide(self, context):
        return AgentDecision(should_act=True, reason="act失敗テスト")

    def act(self, decision, context):
        raise ValueError("act() 内で例外発生（テスト用）")


# ═══════════════════════════════════════════════════════════
# テスト1: AgentTask
# ═══════════════════════════════════════════════════════════

print("=" * 60)
print("v2.0.0 AI Agent Foundation E2E テスト")
print("=" * 60)
print()

print("[テスト1] AgentTask")
from ai import AgentTask

task = AgentTask(task_id="test_task", params={"key": "value"})
check("1. task_id が設定できる", task.task_id, "test_task")
check("1. params が設定できる", task.params, {"key": "value"})

task_default = AgentTask(task_id="test_task_2")
check("1. params のデフォルトが空dict", task_default.params, {})
print()

# ═══════════════════════════════════════════════════════════
# テスト2: AgentDecision
# ═══════════════════════════════════════════════════════════

print("[テスト2] AgentDecision")

decision = AgentDecision(should_act=True, reason="テスト理由")
check_true("2. should_act が設定できる", decision.should_act)
check("2. reason が設定できる", decision.reason, "テスト理由")

decision_false = AgentDecision(should_act=False, reason="実行不要")
check_false("2. should_act=False が設定できる", decision_false.should_act)
print()

# ═══════════════════════════════════════════════════════════
# テスト3: AgentContext
# ═══════════════════════════════════════════════════════════

print("[テスト3] AgentContext elapsed_time")
from ai import AgentContext

ctx = AgentContext(task=task, dry_run=False, run_id="run-3", agent_name="agent-3")
check_none("3. elapsed_time が None（started_at/finished_at未設定）", ctx.elapsed_time)

ctx.started_at = datetime(2026, 1, 1, 10, 0, 0)
check_none("3. finished_at 未設定時は elapsed_time が None", ctx.elapsed_time)

ctx.finished_at = datetime(2026, 1, 1, 10, 0, 5)
check("3. elapsed_time が正しく計算される（5秒）", ctx.elapsed_time, 5.0)

check("3. decisions が空リスト（初期値）", ctx.decisions, [])
check("3. warnings が空リスト（初期値）", ctx.warnings, [])
check("3. errors が空リスト（初期値）", ctx.errors, [])
check("3. logs が空リスト（初期値）", ctx.logs, [])
print()

# ═══════════════════════════════════════════════════════════
# テスト4: AgentResult
# ═══════════════════════════════════════════════════════════

print("[テスト4] AgentResult to_dict() / to_json()")

now       = datetime.now()
task4     = AgentTask(task_id="t4")
decision4 = AgentDecision(should_act=True, reason="reason4")
result4   = AgentResult(
    run_id="run-4",
    agent_name="agent-4",
    task=task4,
    decision=decision4,
    action_taken=True,
    success=True,
    workflow_result=None,
    error_message=None,
    started_at=now,
    finished_at=now,
)

d = result4.to_dict()
required_keys = [
    "run_id", "agent_name", "task_id", "decision", "action_taken", "success",
    "workflow_result", "error_message", "started_at", "finished_at", "warnings",
]
for key in required_keys:
    check_true(f"4. to_dict() に {key} が含まれる", key in d)

check("4. to_dict() の task_id が正しい", d["task_id"], "t4")
check("4. to_dict() の decision.should_act が正しい", d["decision"]["should_act"], True)
check("4. to_dict() の decision.reason が正しい", d["decision"]["reason"], "reason4")
check_none("4. to_dict() の workflow_result が None", d["workflow_result"])
check_true("4. to_dict() の started_at が str（ISO形式）", isinstance(d["started_at"], str))

json_str = result4.to_json()
check_true("4. to_json() が str を返す", isinstance(json_str, str))
parsed = json.loads(json_str)
check("4. to_json() がパース可能で run_id が一致", parsed["run_id"], "run-4")
print()

# ═══════════════════════════════════════════════════════════
# テスト5: AgentConfig
# ═══════════════════════════════════════════════════════════

print("[テスト5] AgentConfig.from_env() / is_ready()")
from ai import AgentConfig

os.environ.pop("AI_AGENT_ENABLED", None)
config_default = AgentConfig.from_env()
check_true("5. from_env() が AgentConfig を返す", isinstance(config_default, AgentConfig))
check_false("5. デフォルトで enabled=False", config_default.enabled)
check_false("5. デフォルトで is_ready()=False", config_default.is_ready())

os.environ["AI_AGENT_ENABLED"] = "true"
config_enabled = AgentConfig.from_env()
check_true("5. AI_AGENT_ENABLED=true で enabled=True", config_enabled.enabled)
check_true("5. AI_AGENT_ENABLED=true で is_ready()=True", config_enabled.is_ready())

os.environ["AI_AGENT_ENABLED"] = "false"
config_disabled = AgentConfig.from_env()
check_false("5. AI_AGENT_ENABLED=false で is_ready()=False", config_disabled.is_ready())

os.environ.pop("AI_AGENT_ENABLED", None)
print()

# ═══════════════════════════════════════════════════════════
# テスト6: BaseAgent ABC
# ═══════════════════════════════════════════════════════════

print("[テスト6] BaseAgent ABC")

check_true("6. BaseAgent が ABC のサブクラス", issubclass(BaseAgent, ABC))

abstract_methods = getattr(BaseAgent, "__abstractmethods__", set())
check_true("6. name() が抽象メソッド", "name" in abstract_methods)
check_true("6. decide() が抽象メソッド", "decide" in abstract_methods)
check_true("6. act() が抽象メソッド", "act" in abstract_methods)

try:
    BaseAgent()  # type: ignore
    check_true("6. 未実装サブクラスはインスタンス化できない（失敗）", False)
except TypeError:
    check_true("6. 未実装サブクラスはインスタンス化できない", True)
print()

# ═══════════════════════════════════════════════════════════
# テスト7〜12: AgentExecutor
# ═══════════════════════════════════════════════════════════

print("[テスト7-12] AgentExecutor")
from ai import AgentExecutor

# テスト7: decide() / act() が呼ばれる（should_act=True, dry_run=False）
mock_agent = MockAgent(should_act=True)
executor   = AgentExecutor(mock_agent)
ctx7       = AgentContext(task=AgentTask(task_id="t7"), dry_run=False, run_id="run-7", agent_name="")
result7    = executor.execute(ctx7)
check_true("7. decide() が呼ばれた", mock_agent.decide_called)
check_true("7. act() が呼ばれた", mock_agent.act_called)
check_true("7. action_taken=True", result7.action_taken)
check_true("7. success=True", result7.success)

# テスト8: should_act=False の場合、act() が呼ばれない
mock_agent8 = MockAgent(should_act=False)
executor8   = AgentExecutor(mock_agent8)
ctx8        = AgentContext(task=AgentTask(task_id="t8"), dry_run=False, run_id="run-8", agent_name="")
result8     = executor8.execute(ctx8)
check_true("8. decide() が呼ばれた", mock_agent8.decide_called)
check_false("8. act() が呼ばれない（should_act=False）", mock_agent8.act_called)
check_false("8. action_taken=False", result8.action_taken)
check_true("8. success=True（判断プロセスは正常完了）", result8.success)

# テスト9: dry_run=True の場合、act() が呼ばれない
mock_agent9 = MockAgent(should_act=True)
executor9   = AgentExecutor(mock_agent9)
ctx9        = AgentContext(task=AgentTask(task_id="t9"), dry_run=True, run_id="run-9", agent_name="")
result9     = executor9.execute(ctx9)
check_true("9. decide() が呼ばれた", mock_agent9.decide_called)
check_false("9. act() が呼ばれない（dry_run=True）", mock_agent9.act_called)
check_false("9. action_taken=False", result9.action_taken)
check_true("9. success=True（判断プロセスは正常完了）", result9.success)
check_true("9. dry_runスキップの警告が記録される", len(ctx9.warnings) == 1)

# テスト10: decide() 例外時に success=False
decide_failing = DecideFailingAgent()
executor10     = AgentExecutor(decide_failing)
ctx10          = AgentContext(task=AgentTask(task_id="t10"), dry_run=False, run_id="run-10", agent_name="")
result10       = executor10.execute(ctx10)
check_false("10. decide()例外時 success=False", result10.success)
check_contains("10. error_message に例外内容が含まれる", result10.error_message, "decide() 内で例外発生")
check_true("10. context.errors に記録される", len(ctx10.errors) == 1)
check_false("10. action_taken=False", result10.action_taken)

# テスト11: act() 例外時に success=False
act_failing = ActFailingAgent()
executor11  = AgentExecutor(act_failing)
ctx11       = AgentContext(task=AgentTask(task_id="t11"), dry_run=False, run_id="run-11", agent_name="")
result11    = executor11.execute(ctx11)
check_false("11. act()例外時 success=False", result11.success)
check_contains("11. error_message に例外内容が含まれる", result11.error_message, "act() 内で例外発生")
check_true("11. context.errors に記録される", len(ctx11.errors) == 1)

# テスト12: finalize が run_id / agent_name / started_at / finished_at を保証する
# MockAgent.act() はわざと "WRONG_RUN_ID" / "WRONG_AGENT_NAME" を返す（上のテスト7で使用済み）
check("12. run_id が context の値で上書きされる", result7.run_id, "run-7")
check("12. agent_name が context の値（agent.name()）で上書きされる", result7.agent_name, "mock_agent")
check("12. started_at が context の値と一致する", result7.started_at, ctx7.started_at)
check("12. finished_at が context の値と一致する", result7.finished_at, ctx7.finished_at)
check_not_none("12. started_at が設定されている", result7.started_at)
check_not_none("12. finished_at が設定されている", result7.finished_at)
# should_act=False / dry_run=True / 例外発生時も同様に保証される
for label, r, c in [
    ("should_act=False", result8, ctx8),
    ("dry_run=True", result9, ctx9),
    ("decide()例外", result10, ctx10),
    ("act()例外", result11, ctx11),
]:
    check(f"12. {label} でも run_id が一致", r.run_id, c.run_id)
    check(f"12. {label} でも agent_name が一致", r.agent_name, c.agent_name)
print()

# ═══════════════════════════════════════════════════════════
# テスト13〜15: AgentManager / NullAgentManager
# ═══════════════════════════════════════════════════════════

print("[テスト13-15] AgentManager / NullAgentManager")
from ai import AgentManager, NullAgentManager
from pathlib import Path as _Path

# テスト13: disabled 時に NullAgentManager を返す
config_disabled13 = AgentConfig(enabled=False, base_dir=_Path("."))
manager13 = AgentManager.from_config(config_disabled13)
check_true("13. disabled → NullAgentManager が返る", isinstance(manager13, NullAgentManager))
check_false("13. is_available() が False", manager13.is_available())

# テスト14: enabled 時に AgentManager を返す
config_enabled14 = AgentConfig(enabled=True, base_dir=_Path("."))
manager14 = AgentManager.from_config(config_enabled14)
check_true("14. enabled → AgentManager が返る", isinstance(manager14, AgentManager))
check_true("14. is_available() が True", manager14.is_available())

# テスト15: NullAgentManager.run() が空リストを返す
null_manager = NullAgentManager()
run_result = null_manager.run(AgentTask(task_id="t15"))
check("15. run() が空リストを返す", run_result, [])
check_true("15. 戻り値が list 型", isinstance(run_result, list))
print()

# ═══════════════════════════════════════════════════════════
# テスト16〜18: 構成・互換性
# ═══════════════════════════════════════════════════════════

print("[テスト16-18] 構成・互換性")

# テスト16: __init__.py から新規9シンボルをimportできる
import ai as ai_pkg

new_exports = [
    "AgentTask",
    "AgentDecision",
    "AgentContext",
    "AgentResult",
    "AgentConfig",
    "BaseAgent",
    "AgentExecutor",
    "AgentManager",
    "NullAgentManager",
]
for name in new_exports:
    check_true(f"16. {name} が __init__.py からエクスポートされている", hasattr(ai_pkg, name))
    check_true(f"16. {name} が __all__ に含まれる", name in ai_pkg.__all__)

# テスト17: 既存 Workflow Foundation の代表シンボルも引き続き import できる
try:
    from ai import (
        WorkflowStep, WorkflowContext, WorkflowConfig, WorkflowResult,
        WorkflowStepExecutor, WorkflowRunner, NullWorkflowRunner,
    )
    check_true("17. Workflow Foundation の代表クラスが import できる", True)
except ImportError as e:
    check_true(f"17. Workflow Foundation の代表クラスが import できる（失敗: {e}）", False)

try:
    from ai import (
        AiImprovementConfig, ClaudeClient, NullClaudeClient,
        RewriteService, NullRewriteService,
        AiPublishService, NullAiPublishService,
    )
    check_true("17. v1.14〜v1.18 の代表クラスが import できる", True)
except ImportError as e:
    check_true(f"17. v1.14〜v1.18 の代表クラスが import できる（失敗: {e}）", False)

# テスト18: Claude API を実際に呼び出さない
new_files = [
    "agent_task.py",
    "agent_decision.py",
    "agent_context.py",
    "agent_result.py",
    "agent_config.py",
    "base_agent.py",
    "agent_executor.py",
    "agent_manager.py",
]
for filename in new_files:
    src_path = Path(__file__).parent.parent / "src" / "ai" / filename
    if src_path.exists():
        content = src_path.read_text(encoding="utf-8")
        check_false(f"18. {filename}: urllib.request を使わない", "urllib.request" in content)
        check_false(f"18. {filename}: ClaudeClient を使わない", "ClaudeClient" in content)
    else:
        check_true(f"18. {filename} が存在する（確認失敗）", False)
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
