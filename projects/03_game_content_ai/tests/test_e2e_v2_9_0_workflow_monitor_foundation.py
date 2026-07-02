"""
E2E テスト: v2.9.0 Workflow Monitor Foundation

テストシナリオ:
    ── WorkflowMonitorConfig ──
    1.  from_env() のデフォルト値（enabled=True / timeout_seconds=3600 / is_ready()=True）
    2.  WORKFLOW_MONITOR_ENABLED=false の明示指定
    3.  WORKFLOW_MONITOR_TIMEOUT_SECONDS の環境変数上書き

    ── WorkflowMonitorStatus ──
    4.  6値（RUNNING/SUCCESS/FAILED/TIMEOUT/CANCELLED/WAITING）が定義されている

    ── WorkflowMonitor 判定ロジック ──
    5.  WorkflowExecutionStatus.SUCCESS → WorkflowMonitorStatus.SUCCESS
    6.  WorkflowExecutionStatus.FAILED → WorkflowMonitorStatus.FAILED（reasonにerror_message）
    7.  RUNNINGかつtimeout未経過 → WorkflowMonitorStatus.RUNNING
    8.  RUNNINGかつtimeout経過済み → WorkflowMonitorStatus.TIMEOUT（reasonに経過秒数・閾値）
    9.  CANCELLED/WAITINGはいずれの入力パターンでも返らない

    ── WorkflowMonitor.get_status() / list_status() ──
    10. get_status() が存在しないrun_idでNoneを返す
    11. get_status() が正しくWorkflowMonitorRecordへ変換する
    12. list_status() が started_at の新しい順で返す
    13. list_status(limit=N) で件数が制限される

    ── steps コピー渡しの確認（Architecture Review指摘事項#1） ──
    14. WorkflowMonitorRecord.steps が元のWorkflowExecutionRecord.stepsとは別オブジェクトである

    ── 書き込みが発生しないことの確認（Charter 7章 成功条件） ──
    15. WorkflowMonitor実行前後でJSONファイルのmtimeが変化しない

    ── WorkflowMonitorManager ──
    16. from_config()：enabled/disabledの分岐
    17. NullWorkflowMonitorManager：全メソッドがno-opで動作する

    ── scripts/show_workflow_status.py ──
    18. スクリプトが存在する
    19. 履歴0件時に安全に終了する
    20. run_workflow_engine.py実行後の履歴を --run-id で参照できる
    21. WORKFLOW_MONITOR_ENABLED=false でもCLIが動作する（ゲート分離の確認）

    ── Architecture Guard ──
    22. src/workflow_monitor/ が workflow_engine/ai/pipeline/schedulerをimportしない（静的検査）
    23. src/execution_history/ 配下の既存ファイルに変更がない（git diff）
    24. workflow_monitor パッケージのexport確認

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v2_9_0_workflow_monitor_foundation.py
"""
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
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
print("v2.9.0 Workflow Monitor Foundation E2E テスト")
print("=" * 60)
print()

from execution_history import (
    ExecutionHistoryConfig,
    ExecutionHistoryStore,
    JsonExecutionHistoryStore,
    StepExecutionRecord,
    StepExecutionStatus,
    WorkflowExecutionRecord,
    WorkflowExecutionStatus,
)
from workflow_monitor import (
    NullWorkflowMonitorManager,
    WorkflowMonitor,
    WorkflowMonitorConfig,
    WorkflowMonitorManager,
    WorkflowMonitorStatus,
)

ENV_KEYS = ("WORKFLOW_MONITOR_ENABLED", "WORKFLOW_MONITOR_TIMEOUT_SECONDS")
EH_ENV_KEYS = ("EXECUTION_HISTORY_ENABLED", "EXECUTION_HISTORY_DIR")


def clear_env():
    for key in ENV_KEYS + EH_ENV_KEYS:
        os.environ.pop(key, None)


class InMemoryExecutionHistoryStore(ExecutionHistoryStore):
    """テスト専用のExecutionHistoryStore実装（メモリ保持、JSON round-tripを行わない）。"""

    def __init__(self):
        self._records: dict[str, WorkflowExecutionRecord] = {}

    def save(self, record: WorkflowExecutionRecord) -> None:
        self._records[record.run_id] = record

    def get(self, run_id: str):
        return self._records.get(run_id)

    def list_all(self):
        return sorted(self._records.values(), key=lambda r: r.started_at, reverse=True)


def make_record(
    run_id: str,
    status: WorkflowExecutionStatus,
    started_at: datetime,
    finished_at: datetime | None = None,
    error_message: str | None = None,
    steps: list | None = None,
) -> WorkflowExecutionRecord:
    return WorkflowExecutionRecord(
        run_id=run_id,
        workflow_name="workflow_engine",
        source="manual",
        job_id="job-1",
        status=status,
        started_at=started_at,
        finished_at=finished_at,
        error_message=error_message,
        steps=steps or [],
    )


# ═══════════════════════════════════════════════════════════
# テスト1-3: WorkflowMonitorConfig
# ═══════════════════════════════════════════════════════════

print("[テスト1-3] WorkflowMonitorConfig.from_env()")

clear_env()

cfg1 = WorkflowMonitorConfig.from_env()
check_true("1. デフォルト enabled=True", cfg1.enabled)
check("1. デフォルト timeout_seconds=3600", cfg1.timeout_seconds, 3600)
check_true("1. デフォルトは is_ready()=True", cfg1.is_ready())

os.environ["WORKFLOW_MONITOR_ENABLED"] = "false"
cfg2 = WorkflowMonitorConfig.from_env()
check_false("2. WORKFLOW_MONITOR_ENABLED=false で enabled=False", cfg2.enabled)
check_false("2. is_ready()=False", cfg2.is_ready())
os.environ.pop("WORKFLOW_MONITOR_ENABLED", None)

os.environ["WORKFLOW_MONITOR_TIMEOUT_SECONDS"] = "120"
cfg3 = WorkflowMonitorConfig.from_env()
check("3. WORKFLOW_MONITOR_TIMEOUT_SECONDS の環境変数上書き", cfg3.timeout_seconds, 120)
os.environ.pop("WORKFLOW_MONITOR_TIMEOUT_SECONDS", None)
print()


# ═══════════════════════════════════════════════════════════
# テスト4: WorkflowMonitorStatus
# ═══════════════════════════════════════════════════════════

print("[テスト4] WorkflowMonitorStatus")

expected_values = {"running", "success", "failed", "timeout", "cancelled", "waiting"}
actual_values = {s.value for s in WorkflowMonitorStatus}
check("4. 6値が定義されている", actual_values, expected_values)
print()


# ═══════════════════════════════════════════════════════════
# テスト5-9: WorkflowMonitor 判定ロジック
# ═══════════════════════════════════════════════════════════

print("[テスト5-9] WorkflowMonitor 判定ロジック")

judge_store = InMemoryExecutionHistoryStore()
judge_monitor = WorkflowMonitor(store=judge_store, config=WorkflowMonitorConfig(enabled=True, timeout_seconds=60))

now = datetime.now()

# テスト5: SUCCESS
judge_store.save(make_record("run-success", WorkflowExecutionStatus.SUCCESS, now - timedelta(seconds=10), now))
r5 = judge_monitor.get_status("run-success")
check("5. SUCCESS → WorkflowMonitorStatus.SUCCESS", r5.monitor_status, WorkflowMonitorStatus.SUCCESS)
check_none("5. reasonはNone", r5.reason)

# テスト6: FAILED
judge_store.save(make_record("run-failed", WorkflowExecutionStatus.FAILED, now - timedelta(seconds=10), now, error_message="boom"))
r6 = judge_monitor.get_status("run-failed")
check("6. FAILED → WorkflowMonitorStatus.FAILED", r6.monitor_status, WorkflowMonitorStatus.FAILED)
check("6. reasonにerror_messageが入る", r6.reason, "boom")

# テスト7: RUNNINGかつtimeout未経過（timeout_seconds=60、経過5秒）
judge_store.save(make_record("run-running", WorkflowExecutionStatus.RUNNING, now - timedelta(seconds=5)))
r7 = judge_monitor.get_status("run-running")
check("7. RUNNINGかつtimeout未経過 → WorkflowMonitorStatus.RUNNING", r7.monitor_status, WorkflowMonitorStatus.RUNNING)
check_none("7. reasonはNone", r7.reason)

# テスト8: RUNNINGかつtimeout経過済み（timeout_seconds=60、経過120秒）
judge_store.save(make_record("run-timeout", WorkflowExecutionStatus.RUNNING, now - timedelta(seconds=120)))
r8 = judge_monitor.get_status("run-timeout")
check("8. RUNNINGかつtimeout経過済み → WorkflowMonitorStatus.TIMEOUT", r8.monitor_status, WorkflowMonitorStatus.TIMEOUT)
check_contains("8. reasonに閾値(60秒)が含まれる", r8.reason, "60")
check_contains("8. reasonにTIMEOUTという語が含まれる", r8.reason, "TIMEOUT")

# テスト9: CANCELLED/WAITINGはいずれの入力パターンでも返らない
observed_statuses = {r5.monitor_status, r6.monitor_status, r7.monitor_status, r8.monitor_status}
check_false("9. CANCELLEDは判定結果に含まれない", WorkflowMonitorStatus.CANCELLED in observed_statuses)
check_false("9. WAITINGは判定結果に含まれない", WorkflowMonitorStatus.WAITING in observed_statuses)
print()


# ═══════════════════════════════════════════════════════════
# テスト10-13: get_status() / list_status()
# ═══════════════════════════════════════════════════════════

print("[テスト10-13] WorkflowMonitor.get_status() / list_status()")

check_none("10. 存在しないrun_idはNoneを返す", judge_monitor.get_status("does-not-exist"))

r11 = judge_monitor.get_status("run-success")
check("11. run_idが正しく変換される", r11.run_id, "run-success")
check("11. workflow_nameが正しく変換される", r11.workflow_name, "workflow_engine")
check("11. source_statusがWorkflowExecutionStatusの値と一致する", r11.source_status, "success")
check_true("11. elapsed_secondsが計算されている", r11.elapsed_seconds >= 0)

list_store = InMemoryExecutionHistoryStore()
list_monitor = WorkflowMonitor(store=list_store, config=WorkflowMonitorConfig(enabled=True, timeout_seconds=3600))
list_store.save(make_record("run-old", WorkflowExecutionStatus.SUCCESS, datetime(2026, 7, 1, 0, 0, 0), datetime(2026, 7, 1, 0, 1, 0)))
list_store.save(make_record("run-new", WorkflowExecutionStatus.SUCCESS, datetime(2026, 7, 3, 0, 0, 0), datetime(2026, 7, 3, 0, 1, 0)))
list_store.save(make_record("run-mid", WorkflowExecutionStatus.SUCCESS, datetime(2026, 7, 2, 0, 0, 0), datetime(2026, 7, 2, 0, 1, 0)))

all_status = list_monitor.list_status()
check("12. list_status() が started_at の新しい順で返す", [r.run_id for r in all_status], ["run-new", "run-mid", "run-old"])

limited_status = list_monitor.list_status(limit=2)
check("13. list_status(limit=2) で件数が制限される", len(limited_status), 2)
check("13. limit適用後も新しい順が保たれる", [r.run_id for r in limited_status], ["run-new", "run-mid"])
print()


# ═══════════════════════════════════════════════════════════
# テスト14: steps コピー渡しの確認
# ═══════════════════════════════════════════════════════════

print("[テスト14] WorkflowMonitorRecord.steps のコピー渡し確認")

copy_store = InMemoryExecutionHistoryStore()
copy_monitor = WorkflowMonitor(store=copy_store, config=WorkflowMonitorConfig(enabled=True, timeout_seconds=3600))
original_steps = [StepExecutionRecord(step="news", status=StepExecutionStatus.SUCCESS)]
original_record = make_record("run-copy", WorkflowExecutionStatus.SUCCESS, now - timedelta(seconds=5), now, steps=original_steps)
copy_store.save(original_record)

r14 = copy_monitor.get_status("run-copy")
check_false("14. steps が元のリストと同一オブジェクトではない", r14.steps is original_steps)
check("14. steps の内容は一致する", r14.steps, original_steps)
print()


# ═══════════════════════════════════════════════════════════
# テスト15: 書き込みが発生しないことの確認
# ═══════════════════════════════════════════════════════════

print("[テスト15] Workflow Monitor実行前後でファイルが変更されないこと")

mtime_dir = Path(tempfile.mkdtemp()) / "history"
mtime_store = JsonExecutionHistoryStore(mtime_dir)
mtime_store.save(make_record("run-mtime", WorkflowExecutionStatus.SUCCESS, now - timedelta(seconds=5), now))

mtime_file = mtime_dir / "run-mtime.json"
mtime_before = mtime_file.stat().st_mtime_ns

mtime_monitor = WorkflowMonitor(store=mtime_store, config=WorkflowMonitorConfig(enabled=True, timeout_seconds=3600))
mtime_monitor.get_status("run-mtime")
mtime_monitor.list_status()
mtime_monitor.get_status("run-mtime")

mtime_after = mtime_file.stat().st_mtime_ns
check("15. Monitor実行前後でJSONファイルのmtimeが変化しない", mtime_after, mtime_before)
print()


# ═══════════════════════════════════════════════════════════
# テスト16-17: WorkflowMonitorManager
# ═══════════════════════════════════════════════════════════

print("[テスト16-17] WorkflowMonitorManager")

clear_env()
tmp_mgr_root = Path(tempfile.mkdtemp())
eh_cfg = ExecutionHistoryConfig.from_env(project_root=tmp_mgr_root)

wm_cfg_enabled = WorkflowMonitorConfig.from_env()
mgr_enabled = WorkflowMonitorManager.from_config(eh_cfg, wm_cfg_enabled)
check_true("16. デフォルト(enabled=True)で WorkflowMonitorManager 実体が返る", isinstance(mgr_enabled, WorkflowMonitorManager))

os.environ["WORKFLOW_MONITOR_ENABLED"] = "false"
wm_cfg_disabled = WorkflowMonitorConfig.from_env()
mgr_disabled = WorkflowMonitorManager.from_config(eh_cfg, wm_cfg_disabled)
check_true("16. WORKFLOW_MONITOR_ENABLED=false で NullWorkflowMonitorManager が返る", isinstance(mgr_disabled, NullWorkflowMonitorManager))
os.environ.pop("WORKFLOW_MONITOR_ENABLED", None)

null_mgr = NullWorkflowMonitorManager()
check_none("17. get_status() はNoneを返す", null_mgr.get_status("any"))
check("17. list_status() は空リストを返す", null_mgr.list_status(), [])
print()


# ═══════════════════════════════════════════════════════════
# テスト18-21: scripts/show_workflow_status.py
# ═══════════════════════════════════════════════════════════

print("[テスト18-21] scripts/show_workflow_status.py")

script_path_show = PROJECT_ROOT / "scripts" / "show_workflow_status.py"
check_true("18. show_workflow_status.py が存在する", script_path_show.exists())


def run_show_cli(extra_args, env_overrides):
    env = dict(os.environ)
    for key in ENV_KEYS + EH_ENV_KEYS:
        env.pop(key, None)
    env.update(env_overrides)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(script_path_show)] + extra_args,
        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env, timeout=60,
    )


empty_history_dir = Path(tempfile.mkdtemp()) / "empty_history"
completed_19 = run_show_cli([], {"EXECUTION_HISTORY_DIR": str(empty_history_dir)})
check("19. returncode が 0（履歴0件でも安全終了）", completed_19.returncode, 0)
check_contains("19. 履歴なしの案内が表示される", completed_19.stdout, "履歴がありません")

script_path_we = PROJECT_ROOT / "scripts" / "run_workflow_engine.py"
shared_history_dir = Path(tempfile.mkdtemp()) / "shared_history"
env_we = dict(os.environ)
for key in ("AI_AGENT_ENABLED", "WORKFLOW_ENGINE_ENABLED") + EH_ENV_KEYS:
    env_we.pop(key, None)
env_we.update({
    "AI_AGENT_ENABLED": "true", "WORKFLOW_ENGINE_ENABLED": "true",
    "EXECUTION_HISTORY_DIR": str(shared_history_dir), "PYTHONIOENCODING": "utf-8",
})
completed_run = subprocess.run(
    [sys.executable, str(script_path_we), "--dry-run", "--job-id", "show-status-e2e"],
    cwd=str(PROJECT_ROOT), capture_output=True, text=True, encoding="utf-8", errors="replace", env=env_we, timeout=60,
)
check("20. run_workflow_engine.py が正常終了する", completed_run.returncode, 0)

store_20 = JsonExecutionHistoryStore(shared_history_dir)
records_20 = store_20.list_all()
check_true("20. run_workflow_engine.py実行後に履歴が1件以上記録される", len(records_20) >= 1)

if records_20:
    run_id_20 = records_20[0].run_id
    completed_20 = run_show_cli(["--run-id", run_id_20], {"EXECUTION_HISTORY_DIR": str(shared_history_dir)})
    check("20. --run-id 指定で詳細表示が正常終了する", completed_20.returncode, 0)
    check_contains("20. 詳細表示にrun_idが含まれる", completed_20.stdout, run_id_20)
    check_contains("20. 詳細表示にmonitor_statusが含まれる", completed_20.stdout, "monitor_status")

completed_21 = run_show_cli([], {
    "EXECUTION_HISTORY_DIR": str(shared_history_dir), "WORKFLOW_MONITOR_ENABLED": "false",
})
check("21. WORKFLOW_MONITOR_ENABLED=false でもCLIが正常終了する（ゲート分離）", completed_21.returncode, 0)
check_contains("21. ゲート無効時も一覧が表示される", completed_21.stdout, "Workflow Monitor 一覧")
print()


# ═══════════════════════════════════════════════════════════
# テスト22-24: Architecture Guard
# ═══════════════════════════════════════════════════════════

print("[テスト22] workflow_monitor が workflow_engine/ai/pipeline/schedulerをimportしない（静的検査）")

wm_dir = PROJECT_ROOT / "src" / "workflow_monitor"
for py_file in sorted(wm_dir.glob("*.py")):
    source = py_file.read_text(encoding="utf-8")
    import_lines = "\n".join(
        line for line in source.splitlines()
        if line.strip().startswith("from ") or line.strip().startswith("import ")
    )
    for forbidden in ("workflow_engine", "scheduler", "from ai", "import ai", "from pipeline", "import pipeline"):
        check_false(
            f"22. {py_file.name} が {forbidden} をimportしない",
            forbidden in import_lines,
        )
print()


print("[テスト23] 既存ファイルの無変更確認（git diff）")

unchanged_paths_wm = [
    "main.py",
    "src/execution_history/execution_history_config.py",
    "src/execution_history/execution_history_event.py",
    "src/execution_history/execution_history_manager.py",
    "src/execution_history/execution_history_store.py",
    "src/execution_history/json_execution_history_store.py",
    "src/execution_history/step_execution_record.py",
    "src/execution_history/workflow_execution_record.py",
    "src/workflow_engine/workflow_engine_executor.py",
    "src/workflow_engine/workflow_engine_manager.py",
    "src/ai/agent_manager.py",
    "src/scheduler/scheduler_engine.py",
]

git_available = True
try:
    subprocess.run(["git", "--version"], capture_output=True, cwd=str(PROJECT_ROOT), timeout=10)
except Exception:
    git_available = False

if git_available:
    for rel_path in unchanged_paths_wm:
        completed = subprocess.run(
            ["git", "diff", "--quiet", "--", rel_path],
            cwd=str(PROJECT_ROOT), capture_output=True, timeout=10,
        )
        check_true(f"23. {rel_path} に変更がない（git diff）", completed.returncode == 0)
else:
    check_true("23. gitが利用できないため無変更確認をスキップ", True)
print()


print("[テスト24] import確認（workflow_monitor パッケージのexport）")

import workflow_monitor as wm_pkg
for name in (
    "WorkflowMonitorStatus", "WorkflowMonitorConfig", "WorkflowMonitorRecord",
    "WorkflowMonitor", "WorkflowMonitorManager", "NullWorkflowMonitorManager",
):
    check_true(f"24. {name} が workflow_monitor パッケージからエクスポートされている", hasattr(wm_pkg, name))
    check_true(f"24. {name} が workflow_monitor.__all__ に含まれる", name in wm_pkg.__all__)
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
