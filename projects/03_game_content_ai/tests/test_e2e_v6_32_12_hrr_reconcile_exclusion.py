"""
E2E テスト: Release 6.32 sub-milestone 6D cluster 3
Invariant #5 — unresolved HRRからの`open_next_attempt()`禁止（二重ガード、呼び出し元フィルタ層）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    28.-31節（3件）。

Invariant #5（25章）は、16章冒頭の「呼び出し元での二重ガード」が主張する2層
（(a) `_reconcile_all_locked()`自身のopened_countループが持つ呼び出し元フィルタ・
(b) `open_next_attempt()`自身のhrr_authorizedチェック）から成る。本テストは
(a)の呼び出し元フィルタ層を`open_next_attempt()`へのspy/mockで直接検証する
（(b)の関数自身のチェック層は28.-9節#1・21章シナリオ25が別途検証する）。

production側（src/retry_lineage/retry_lineage_manager.py）は変更しない。
test-onlyでApproved Architectureの主張を直接証明する。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_12_hrr_reconcile_exclusion.py
"""
from __future__ import annotations

import sys
import tempfile
from datetime import datetime
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

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
print("Invariant #5 — HRR reconcile除外（呼び出し元フィルタ層、28.-31）E2E テスト")
print("=" * 60)
print()

from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus
from retry_lineage import (
    JsonRetryLineageStore,
    RetryLineageConfig,
    RetryLineageDisposition,
    RetryLineageManager,
    RetryLineagePhase,
)

tmp_dirs: list[Path] = []


class FakePolicy:
    def __init__(self, max_attempts: int = 3):
        self.target_statuses = frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT})
        self._max_attempts = max_attempts

    @property
    def max_attempts(self):
        return self._max_attempts

    def should_retry(self, monitor_status, attempt) -> bool:
        return monitor_status in self.target_statuses and attempt < self._max_attempts


def make_lineage_manager() -> RetryLineageManager:
    tmp_root = Path(tempfile.mkdtemp())
    tmp_dirs.append(tmp_root)
    config = RetryLineageConfig(enabled=True, lineage_dir=tmp_root)
    store = JsonRetryLineageStore(config.store_dir)
    return RetryLineageManager(store=store, config=config, policy=FakePolicy())


def make_terminal_lineage(
    lineage: RetryLineageManager, root_run_id: str, disposition: RetryLineageDisposition,
) -> None:
    """create_new_lineage() → claim() → mark_execution_started() → mark_terminal()
    を経由し、phase=TERMINAL・指定terminal_dispositionのlineageを構築する。"""
    lineage.create_new_lineage(
        root_run_id, WorkflowMonitorRecord(
            run_id=root_run_id, workflow_name="workflow_engine", monitor_status=WorkflowMonitorStatus.FAILED,
            source_status="failed", source="manual", job_id="job-1",
            started_at=datetime.now(), finished_at=datetime.now(), elapsed_seconds=1.0, reason=None, steps=[],
        ),
    )
    claim_result = lineage.claim(root_run_id)
    lineage.mark_execution_started(root_run_id, root_run_id, claim_result.owner_token)
    lineage.mark_terminal(root_run_id, disposition=disposition, executed_run_id=root_run_id, newly_confirmed_steps=[])


def _unexpected_resolve_status_fn(run_id):
    """全lineageがTERMINAL phaseで構築されるため（EXECUTION_STARTEDではない）、
    _reconcile_all_locked()の第1ループはresolve_status_fn()を一切呼ばないはず。
    呼ばれた場合はテスト前提が崩れていることを示すため例外を送出する。"""
    raise AssertionError(f"resolve_status_fn()が予期せず呼ばれた（run_id={run_id!r}）")


def _spy_open_next_attempt(lineage: RetryLineageManager):
    """lineage.open_next_attempt()をspyへ差し替え、呼び出し引数を記録した
    リストを返す。実装は無変更のまま呼び出す（結果は本物のまま）。"""
    original = lineage.open_next_attempt
    calls: list[str] = []

    def spy(root_run_id: str):
        calls.append(root_run_id)
        return original(root_run_id)

    lineage.open_next_attempt = spy
    return calls


# =====================================================================
# テスト1: HRR lineage単体 → open_next_attempt()呼び出し回数=0
# =====================================================================

print("[テスト1] terminal_disposition=HUMAN_REVIEW_REQUIREDのlineageに対し"
      "_reconcile_all_locked()を直接呼ぶ → open_next_attempt()呼び出し回数=0")

lineage_1 = make_lineage_manager()
make_terminal_lineage(lineage_1, "run-hrr-1", RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)

calls_1 = _spy_open_next_attempt(lineage_1)
summary_1 = lineage_1._reconcile_all_locked(_unexpected_resolve_status_fn)

check("1. HRR lineageに対するopen_next_attempt()呼び出し回数 = 0", len(calls_1), 0)
check("1. run-hrr-1を引数とする呼び出しは一度も発生しない", "run-hrr-1" in calls_1, False)
check_true("1. _reconcile_all_locked()自体は正常に完了する（skipped=False）", not summary_1.skipped)
check("1. opened_count = 0（HRR lineageのみのため、開かれたattemptは0件）", summary_1.opened_count, 0)
print()


# =====================================================================
# テスト2: FAILED/NOT_ACTIONED/HUMAN_REVIEW_REQUIREDの混在 → HRRのみ除外される対比確認
# =====================================================================

print("[テスト2] FAILED・NOT_ACTIONED・HUMAN_REVIEW_REQUIREDのlineageを混在させ、"
      "HRRのみが呼び出し元フィルタで除外されることを対比確認")

lineage_2 = make_lineage_manager()
make_terminal_lineage(lineage_2, "run-failed-2", RetryLineageDisposition.FAILED)
make_terminal_lineage(lineage_2, "run-not-actioned-2", RetryLineageDisposition.NOT_ACTIONED)
make_terminal_lineage(lineage_2, "run-hrr-2", RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)

calls_2 = _spy_open_next_attempt(lineage_2)
summary_2 = lineage_2._reconcile_all_locked(_unexpected_resolve_status_fn)

check("2. FAILEDのlineageはopen_next_attempt()が1回呼ばれる", calls_2.count("run-failed-2"), 1)
check("2. NOT_ACTIONEDのlineageはopen_next_attempt()が1回呼ばれる", calls_2.count("run-not-actioned-2"), 1)
check("2. HUMAN_REVIEW_REQUIREDのlineageはopen_next_attempt()が呼ばれない（0回）", calls_2.count("run-hrr-2"), 0)
check("2. 呼び出し総数は2件のみ（FAILED+NOT_ACTIONEDの合計、HRRを含まない）", len(calls_2), 2)
check("2. opened_count = 2（FAILED・NOT_ACTIONEDの2件のみ開かれる）", summary_2.opened_count, 2)

# open_next_attempt()呼び出し後の実際の状態も確認する（呼ばれたものはREADY_ELIGIBLEへ
# 遷移し、呼ばれなかったHRRのみTERMINALのまま残ることの直接裏付け）。
record_failed_after_2 = lineage_2.peek("run-failed-2")
record_not_actioned_after_2 = lineage_2.peek("run-not-actioned-2")
record_hrr_after_2 = lineage_2.peek("run-hrr-2")
check("2. FAILED lineageはopen_next_attempt()経由でREADY_ELIGIBLEへ遷移する", record_failed_after_2.phase, RetryLineagePhase.READY_ELIGIBLE)
check("2. NOT_ACTIONED lineageも同様にREADY_ELIGIBLEへ遷移する", record_not_actioned_after_2.phase, RetryLineagePhase.READY_ELIGIBLE)
check("2. HRR lineageはTERMINALのまま変化しない（呼び出し元フィルタにより除外された直接証拠）", record_hrr_after_2.phase, RetryLineagePhase.TERMINAL)
check("2. HRR lineageのterminal_dispositionもHUMAN_REVIEW_REQUIREDのまま", record_hrr_after_2.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
print()


# =====================================================================
# テスト3: 呼び出し元フィルタが万一欠落した場合の第2層単独exercise
#          （open_next_attempt()自身がHRRに対しacknowledged=Falseを返す、28.-9#1と同一趣旨）
# =====================================================================

print("[テスト3] open_next_attempt()自身を（呼び出し元フィルタを経由せず）直接HRR lineageへ呼ぶ"
      "→ 第2層（関数自身のチェック）が単独でもacknowledged=Falseを返す")

lineage_3 = make_lineage_manager()
make_terminal_lineage(lineage_3, "run-hrr-3", RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)

# 呼び出し元フィルタ（_reconcile_all_locked()）を経由せず、open_next_attempt()自身を
# 直接呼ぶ——呼び出し元フィルタが万一欠落・バイパスされた場合を想定した第2層単独確認。
direct_result_3 = lineage_3.open_next_attempt("run-hrr-3")
check_true(
    "3. open_next_attempt()自身がHUMAN_REVIEW_REQUIREDに対しacknowledged=Falseを返す"
    "（呼び出し元フィルタなしでも第2層が独立に機能する）",
    not direct_result_3.acknowledged,
)
record_hrr_after_3 = lineage_3.peek("run-hrr-3")
check("3. 直接呼び出し後もphaseはTERMINALのまま（次attemptは開かれない）", record_hrr_after_3.phase, RetryLineagePhase.TERMINAL)
print()


# =====================================================================
# 結果サマリー
# =====================================================================

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
