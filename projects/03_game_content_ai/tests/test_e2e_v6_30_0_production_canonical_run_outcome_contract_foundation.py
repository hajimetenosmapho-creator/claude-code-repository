"""
E2E テスト: Release 6.30 Production Canonical Run & Outcome Contract Foundation

権威ドキュメント: docs/design/production_canonical_run_outcome_contract_foundation.md
（Architecture Revision Round 10、Codex read-only review APPROVED：
Blocking 0 / Major 0 / Minor 0 / Suggestions 0）

テストシナリオ（design doc 28章の番号に対応。全63項目のうち、実ネットワーク・実WordPress
サーバを必要とする一部シナリオ（N8-2の featured-media失敗×WordPress全skip共存ケース等）は
本Releaseでは対象外とし、報告時に明記する）：

    ── ExecutionHistoryManager: Recovery / Control-Flow（§18-19） ──
    1.  start_run() ack=False → StartRunWriteResult(acknowledged=False)（#22相当）
    2.  start_step() ack=False → snapshot不変・Managerは自動終端しない
    3.  finish_step()（executed step）ack=False→recovery成功 → TERMINAL(FAILED)、
        pending stepがFAILEDへ正規化される（#13, #48相当）
    4.  finish_step()（executed step）ack=False→recovery失敗 → last-known-good RUNNING
        のまま（#15相当）
    5.  finish_step()（SKIPPED/NOT_REACHED）ack=False→recovery成功 → TERMINAL(FAILED)、
        当該recordはstatus保持（#23, #24, #46, #47相当）
    6.  finish_run() TERMINAL宛て：同一status→True(no-write)、異なるstatus→False(no-write)
        （Terminal Immutability）
    7.  finish_run() ack=False→recovery成功/失敗（#14相当）
    8.  release_run() のidempotence（#29相当）
    9.  SKIPPED/NOT_REACHEDの正式recordがstarted_at=Noneで保存される（#44, #45相当）
    10. Manager snapshotのdeep copy確認：candidateのsteps/eventsを変更してもsnapshot不変
        （#54相当、S8-1）

    ── JsonExecutionHistoryStore atomic save（§22） ──
    11. mkstemp失敗時 → ack=False（#51相当の前段）
    12. os.fdopen()失敗時 → raw fdがbest-effort closeされ、tmpファイルが残らない（#61、
        M9-1後の human-directed fix対象）
    13. write/fsync失敗時 → fdはwithブロックが確実にclose、tmpファイル除去（#51）
    14. os.replace失敗時 → tmpファイルがbest-effort unlinkされ、canonical .jsonは作られない
        （#52）
    15. cleanup（unlink）自体の失敗はackを変更しない（#53）

    ── WorkflowEngineExecutor: Canonical Admission / 制御フロー（§7-19） ──
    16. history_manager省略×非dry-run → CanonicalAdmissionFailure(EXECUTION_HISTORY_DISABLED)
        （#9, #16相当、M9-1修正後もrelease_run()がfinallyで呼ばれることを確認）
    17. start_run() ack=False → CanonicalAdmissionFailure(START_RUN_ACK_FAILED)（#22相当）
    18. start_step() ack=False：Agent未実行・残stepがin-memory NOT_REACHED・
        finish_run(FAILED)がちょうど1回だけ呼ばれる（#41, #42, #43相当）
    19. finish_step() ack=False：以降History API呼び出し一切なし・finish_runも呼ばれない
        （#39, #40相当）
    20. history_write_failed のlatch確認（#13相当）
    21. release_run()がCanonicalAdmissionFailure等の例外発生時もfinallyで必ず呼ばれ、
        例外自体をマスクしない（#56、S8-2）

    ── NewsPipelineRunner: subprocess出力のbytes正規化（§6） ──
    22. completed.stdout/stderrがbytesでも安全にログ保存・診断生成される（#62相当）
    23. TimeoutExpired.stdout/stderrがbytesでも安全に処理される（#49, #63相当）
    24. Noneは空文字として扱われる（#50相当）

    ── main.py Outcome Contract（§5） ──
    25. main()内にsys.exit()呼び出しが残っていない（構造検査、#57相当）
    26. --max-articles不正 → 1
    27. ANTHROPIC_API_KEY未設定 → 1
    28. RSS収集0件 → 1
    29. フィルター後0件 → 0
    30. importance判定後0件 → 0
    31. generation対象0件（--max-articles 0） → 0
    32. 全記事WordPress成功 → 0（#1相当）
    33. 一部成功・一部失敗 → 20（#2, #58相当）
    34. 全記事WordPress失敗 → 21（#3, #59相当）
    35. WordPress全skip（未設定） → 0（#19相当）

    ── scripts/run_workflow_engine.py（§20） ──
    36. gate OFF → exit 0（#35相当）
    37. dry-run + History OFF → 早期exit1にならず正常終了（#37相当、M8-1回帰）
    38. non-dry-run + History OFF → exit 1（#38相当、N8-1）

    ── Retry Runtime: Ruling A（§21） ──
    39. RetryExecutor経由でCanonicalAdmissionFailureが変換されずそのまま伝播する
        （#56, Ruling A回帰）

    ── NewsPipelineRunner: NEWS Outcome Token（§6、human-directed addition） ──
    Round 10 APPROVED契約との照合の結果、§6のNEWS_OUTCOME_*token生成・
    subprocess起動失敗（OSError／launch failure）ハンドリングが実装に欠落していたため、
    人間の実装続行指示に基づき本Release内で追加実装した（テスト22-24のbytes正規化とは
    別観点。既存22-24はtoken方式を検証していなかった）。
    40. returncode=1 → error_messageがNEWS_OUTCOME_GENERIC_FAILURE_EXIT_1で始まる（#20相当）
    41. returncode=20 → NEWS_OUTCOME_PARTIAL_EXIT_20で始まる（#20相当）
    42. returncode=21 → NEWS_OUTCOME_ALL_FAILED_EXIT_21で始まる（#20相当）
    43. returncode=99（未知の終了コード） → NEWS_OUTCOME_ABNORMAL_EXITで始まる
    44. TimeoutExpired → error_messageがNEWS_OUTCOME_TIMEOUTで始まる（#20相当）
    45. subprocess.run()がOSErrorを送出（launch failure） → 例外を伝播させず
        success=False・returncode=None・error_messageがNEWS_OUTCOME_LAUNCH_FAILUREで
        始まる（#17相当）
    46. 成功時（returncode=0） → error_messageはNone（token付与されない）

    ── Codex read-only Code Review（Round 1、NEEDS_REVISION）対応 ──
    実装本体（main.py Outcome Contract・Execution History・WorkflowEngineExecutor・
    run_workflow_engine.py・atomic save・Retry Runtime Ruling A）はRound 10
    APPROVED契約と完全一致と判定された。指摘はすべて本E2Eハーネス自身に対する
    ものであり、実装契約は一切変更していない。
    - Major: テスト25-38（main.py import・run_we_cli）が実プロジェクト.envから
      隔離されておらず、gate OFFシナリオが非決定的・本番外部I/O到達可能性が
      あった → dotenv遮断・gate/config明示固定・ArticleFeaturedMediaRuntime
      呼び出し箇所の完全fake化で対応（テスト25-38セクション）
    - Minor: テスト10のdeep copy検証がshallow copyを検出できない → nested
      steps[0]／eventsのidentity比較・値比較へ強化
    - Minor: テスト5（SKIPPEDのみ）・テスト7（recovery成功のみ）・テスト20
      （正常runのみ）がラベルの主張する分岐を実際には検証していない → 5b
      （NOT_REACHED recovery）・7b（finish_run recovery失敗）・20b（latch確認）
      を追加
    - Minor: テスト21bがrelease_run()の実呼び出しを観測していない →
      NullExecutionHistoryManager.release_run()を一時計装して直接観測
    - Minor: テスト12のfake fdopenが自らfdをcloseしており実装のraw fd
      close経路を検証できていない → fake側はfdへ触れずraiseするのみとし、
      os.closeを計装して1回だけ呼ばれることを直接観測
    - Minor: _patch_generation_chain()が置換した関数が_restore_main_module()で
      復元されていなかった → 全関数を復元するよう修正

    ── Codex read-only Code Review（Round 2、NEEDS_REVISION）対応 ──
    Round 1の6件中4件は完全修正・外部I/O到達性は解消済みと判定された。
    残り2件を修正。
    - Minor: run_we_cli()のgate/interval/History/外部I/O関連env varが一部
      未固定で、AI_AGENT_ENABLED=true時（テスト37-38）にNEWS_AGENT_*・
      REVIEW/PUBLISH_TRIGGER_AGENT_MIN_INTERVAL_MINUTES等が実.envから
      補完されうる状態だった（実害はないが.env独立性が不完全）→
      _WE_CLI_SAFE_DEFAULTSへ全既知leak vectorを追加し、python-dotenvの
      override=False挙動を利用して実.env値の補完余地自体をなくした。
      あわせてWordPressOutputが実際に読むのはWP_URLではなくWP_SITE_URLで
      あるという変数名の取り違えも修正
    - Minor: テスト7bが「recoveryが実際に1回試行された」ことを直接証明して
      いなかった（最終stateの一致だけでは、recoveryを試みない誤実装と
      区別できない）→ store_7b.call_count==3（start_run+finish_run要求+
      recovery試行）のassertionを追加

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_30_0_production_canonical_run_outcome_contract_foundation.py
"""
import copy
import os
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "src"))

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


def check_none(label: str, value):
    check(label, value is None, True)


def check_contains(label: str, text: str, keyword: str):
    check(label, keyword in str(text), True)


print("=" * 60)
print("Release 6.30 Production Canonical Run & Outcome Contract Foundation E2E テスト")
print("=" * 60)
print()

from execution_history import (
    ExecutionHistoryManager,
    ExecutionHistoryStore,
    JsonExecutionHistoryStore,
    NullExecutionHistoryManager,
    StartRunWriteResult,
    StepExecutionStatus,
    WorkflowExecutionRecord,
    WorkflowExecutionStatus,
)
from ai import AgentContext, AgentDecision, AgentExecutor, AgentResult, AgentTask, BaseAgent
from workflow_engine import (
    REASON_HISTORY_WRITE_FAILED,
    REASON_NOT_REACHED,
    SOURCE_MANUAL,
    CanonicalAdmissionFailure,
    WorkflowEngineContext,
    WorkflowEngineDefinition,
    WorkflowEngineEvent,
    WorkflowEngineExecutor,
    WorkflowEngineStep,
)


# ═══════════════════════════════════════════════════════════
# テスト用ユーティリティ
# ═══════════════════════════════════════════════════════════

class FailableStore(ExecutionHistoryStore):
    """save()呼び出し回数（1始まり）を指定してack=Falseを注入できるテスト用Store。"""

    def __init__(self, fail_on_calls: set[int] | None = None, always_fail: bool = False):
        self._records: dict[str, WorkflowExecutionRecord] = {}
        self._fail_on_calls = fail_on_calls or set()
        self._always_fail = always_fail
        self.call_count = 0

    def save(self, record: WorkflowExecutionRecord) -> bool:
        self.call_count += 1
        if self._always_fail or self.call_count in self._fail_on_calls:
            return False
        self._records[record.run_id] = copy.deepcopy(record)
        return True

    def get(self, run_id: str):
        return self._records.get(run_id)

    def list_all(self):
        return sorted(self._records.values(), key=lambda r: r.started_at, reverse=True)


class FakeAgent(BaseAgent):
    def __init__(self, agent_name, decision, act_result=None):
        self._agent_name = agent_name
        self._decision = decision
        self._act_result = act_result
        self.act_call_count = 0

    def name(self):
        return self._agent_name

    def decide(self, context):
        return self._decision

    def act(self, decision, context):
        self.act_call_count += 1
        return self._act_result


def make_agent_result(agent_name, success, error_message=None):
    now = datetime.now()
    return AgentResult(
        run_id="fake-run", agent_name=agent_name, task=AgentTask(task_id="t", params={}),
        decision=AgentDecision(should_act=True, reason="fake"), action_taken=True, success=success,
        workflow_result=None, error_message=error_message, started_at=now, finished_at=now, warnings=[],
    )


def make_engine_context(run_id, dry_run=False):
    event = WorkflowEngineEvent(
        job_id="fake-job", source=SOURCE_MANUAL, triggered_at=datetime.now(), trigger_reason="test"
    )
    return WorkflowEngineContext(event=event, dry_run=dry_run, run_id=run_id)


def all_success_step_executors():
    return {
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


# ═══════════════════════════════════════════════════════════
# テスト1-10: ExecutionHistoryManager Recovery / Control-Flow
# ═══════════════════════════════════════════════════════════

print("[テスト1-10] ExecutionHistoryManager Recovery / Control-Flow")

# テスト1: start_run() ack=False
store_1 = FailableStore(always_fail=True)
mgr_1 = ExecutionHistoryManager(store=store_1)
res_1 = mgr_1.start_run(run_id="r1", workflow_name="workflow_engine", source=SOURCE_MANUAL, job_id="j1")
check_false("1. start_run() ack=Falseが返る", res_1.acknowledged)
check("1. run_idは渡した値と一致する", res_1.run_id, "r1")

# テスト2: start_step() ack=False → snapshot不変・自動終端しない
store_2 = FailableStore()
mgr_2 = ExecutionHistoryManager(store=store_2)
mgr_2.start_run(run_id="r2", workflow_name="workflow_engine", source=SOURCE_MANUAL, job_id="j2")
store_2._fail_on_calls = {2}
ok_2 = mgr_2.start_step("r2", "news")
check_false("2. start_step() ack=Falseが返る", ok_2)
saved_2 = store_2.get("r2")
check("2. Managerは自動終端しない（statusはRUNNINGのまま）", saved_2.status, WorkflowExecutionStatus.RUNNING)
check("2. stepsは追加されない（candidate破棄）", len(saved_2.steps), 0)

# テスト3: finish_step()（executed step）ack=False → recovery成功 → TERMINAL(FAILED)
store_3 = FailableStore(fail_on_calls={3})
mgr_3 = ExecutionHistoryManager(store=store_3)
mgr_3.start_run(run_id="r3", workflow_name="workflow_engine", source=SOURCE_MANUAL, job_id="j3")
mgr_3.start_step("r3", "news")
ok_3 = mgr_3.finish_step("r3", "news", StepExecutionStatus.SUCCESS)
check_false("3. finish_step() はFalseを返す", ok_3)
saved_3 = store_3.get("r3")
check("3. recovery成功でrun全体がFAILEDへ終端する", saved_3.status, WorkflowExecutionStatus.FAILED)
check("3. pending RUNNING stepがFAILEDへ正規化される", saved_3.steps[0].status, StepExecutionStatus.FAILED)

# テスト4: finish_step()（executed step）ack=False → recovery失敗 → last-known-good RUNNING
store_4 = FailableStore(fail_on_calls={3, 4})
mgr_4 = ExecutionHistoryManager(store=store_4)
mgr_4.start_run(run_id="r4", workflow_name="workflow_engine", source=SOURCE_MANUAL, job_id="j4")
mgr_4.start_step("r4", "news")
ok_4 = mgr_4.finish_step("r4", "news", StepExecutionStatus.SUCCESS)
check_false("4. finish_step() はFalseを返す", ok_4)
saved_4 = store_4.get("r4")
check("4. recovery失敗時はlast-known-good RUNNINGのまま", saved_4.status, WorkflowExecutionStatus.RUNNING)
check("4. pending stepはRUNNINGのまま（recovery candidateは破棄）", saved_4.steps[0].status, StepExecutionStatus.RUNNING)

# テスト5: finish_step()（SKIPPED）ack=False → recovery成功 → TERMINAL(FAILED)、record保持
store_5 = FailableStore(fail_on_calls={2})
mgr_5 = ExecutionHistoryManager(store=store_5)
mgr_5.start_run(run_id="r5", workflow_name="workflow_engine", source=SOURCE_MANUAL, job_id="j5")
ok_5 = mgr_5.finish_step("r5", "review", StepExecutionStatus.SKIPPED, skipped_reason="gate closed")
check_false("5. finish_step()（SKIPPED）はFalseを返す", ok_5)
saved_5 = store_5.get("r5")
check("5. runはFAILEDへ終端する", saved_5.status, WorkflowExecutionStatus.FAILED)
check("5. SKIPPED recordはstatusを保持したまま追加される", saved_5.steps[0].status, StepExecutionStatus.SKIPPED)
check_none("5. SKIPPED recordのstarted_atはNone", saved_5.steps[0].started_at)

# テスト5b: finish_step()（NOT_REACHED）ack=False → recovery成功 → TERMINAL(FAILED)、record保持
# （Release 6.30 Code Review Minor対応：テスト5はSKIPPEDのみを検証しておりNOT_REACHEDの
# recovery分岐は未検証だったため追加）
store_5b = FailableStore(fail_on_calls={2})
mgr_5b = ExecutionHistoryManager(store=store_5b)
mgr_5b.start_run(run_id="r5b", workflow_name="workflow_engine", source=SOURCE_MANUAL, job_id="j5b")
ok_5b = mgr_5b.finish_step("r5b", "publish", StepExecutionStatus.NOT_REACHED, skipped_reason=REASON_NOT_REACHED)
check_false("5b. finish_step()（NOT_REACHED）はFalseを返す", ok_5b)
saved_5b = store_5b.get("r5b")
check("5b. runはFAILEDへ終端する", saved_5b.status, WorkflowExecutionStatus.FAILED)
check("5b. NOT_REACHED recordはstatusを保持したまま追加される", saved_5b.steps[0].status, StepExecutionStatus.NOT_REACHED)
check_none("5b. NOT_REACHED recordのstarted_atはNone", saved_5b.steps[0].started_at)

# テスト6: finish_run() Terminal Immutability
store_6 = FailableStore()
mgr_6 = ExecutionHistoryManager(store=store_6)
mgr_6.start_run(run_id="r6", workflow_name="workflow_engine", source=SOURCE_MANUAL, job_id="j6")
mgr_6.finish_run("r6", WorkflowExecutionStatus.SUCCESS)
calls_before_6 = store_6.call_count
check_true("6. 同一status要求はTrue", mgr_6.finish_run("r6", WorkflowExecutionStatus.SUCCESS))
check_false("6. 異なるstatus要求はFalse", mgr_6.finish_run("r6", WorkflowExecutionStatus.FAILED))
check("6. TERMINAL後はいずれもno-write（save()呼び出し回数が増えない）", store_6.call_count, calls_before_6)

# テスト7: finish_run() ack=False → recovery成功
store_7 = FailableStore(fail_on_calls={2})
mgr_7 = ExecutionHistoryManager(store=store_7)
mgr_7.start_run(run_id="r7", workflow_name="workflow_engine", source=SOURCE_MANUAL, job_id="j7")
ok_7 = mgr_7.finish_run("r7", WorkflowExecutionStatus.SUCCESS)
check_false("7. finish_run() ack=Falseの要求自体はFalseを返す", ok_7)
check("7. recovery成功によりFAILEDへ終端する", store_7.get("r7").status, WorkflowExecutionStatus.FAILED)

# テスト7b: finish_run() ack=False → recovery失敗 → last-known-good RUNNINGのまま
# （Release 6.30 Code Review Minor対応：テスト7はrecovery成功のみを検証しておりrecovery
# 失敗分岐は未検証だったため追加。設計書14章の「ack=False→recovery persistを1回だけ試行」
# はrecovery自体が失敗する場合を含む）
store_7b = FailableStore(fail_on_calls={2, 3})
mgr_7b = ExecutionHistoryManager(store=store_7b)
mgr_7b.start_run(run_id="r7b", workflow_name="workflow_engine", source=SOURCE_MANUAL, job_id="j7b")
ok_7b = mgr_7b.finish_run("r7b", WorkflowExecutionStatus.SUCCESS)
check_false("7b. finish_run() ack=Falseの要求自体はFalseを返す", ok_7b)
check(
    "7b. recovery自体も失敗した場合はlast-known-good RUNNINGのまま（変化しない）",
    store_7b.get("r7b").status, WorkflowExecutionStatus.RUNNING,
)
# Release 6.30 Code Review Round 2 Minor対応: 最終stateの一致だけでは「recoveryを
# 1回試行してから失敗した」実装と「call2失敗直後にrecoveryを一切試みずFalseを
# 返した」誤実装を区別できない。save()呼び出し回数を直接検証し、
# start_run(1) + finish_run要求(2) + recovery試行(3) の3回であることを証明する。
check(
    "7b. save()呼び出し回数は3回（start_run+finish_run要求+recovery試行、"
    "recoveryが実際に1回試行されたことの直接証明）",
    store_7b.call_count, 3,
)

# テスト8: release_run() のidempotence
mgr_8 = ExecutionHistoryManager(store=FailableStore())
mgr_8.start_run(run_id="r8", workflow_name="workflow_engine", source=SOURCE_MANUAL, job_id="j8")
mgr_8.release_run("r8")
try:
    mgr_8.release_run("r8")
    mgr_8.release_run("does-not-exist")
    idempotent_8 = True
except Exception:
    idempotent_8 = False
check_true("8. release_run()は複数回・未知run_idに対しても例外を出さない", idempotent_8)
check_none("8. release_run()の戻り値はNone", mgr_8.release_run("r8"))

# テスト9: SKIPPED/NOT_REACHEDの正式recordがstarted_at=None
store_9 = FailableStore()
mgr_9 = ExecutionHistoryManager(store=store_9)
mgr_9.start_run(run_id="r9", workflow_name="workflow_engine", source=SOURCE_MANUAL, job_id="j9")
mgr_9.finish_step("r9", "review", StepExecutionStatus.SKIPPED, skipped_reason="gate closed")
mgr_9.finish_step("r9", "publish", StepExecutionStatus.NOT_REACHED, skipped_reason=REASON_NOT_REACHED)
saved_9 = store_9.get("r9")
check_none("9. SKIPPED recordのstarted_atはNone", saved_9.steps[0].started_at)
check_none("9. NOT_REACHED recordのstarted_atはNone", saved_9.steps[1].started_at)
check_true("9. finished_atは設定される", saved_9.steps[0].finished_at is not None)

# テスト10: Manager snapshotのdeep copy確認（Release 6.30 Code Review Minor対応：
# 旧snapshotのnested steps[0]／eventsオブジェクトを直接捕捉し、finish_step()が
# candidate側（コピー）だけを変更し旧snapshot側の同一オブジェクトを変更しない
# ことを、identity比較と値比較の両方で検証する。shallow copyであればこれらの
# assertionは失敗する）
store_10 = FailableStore()
mgr_10 = ExecutionHistoryManager(store=store_10)
mgr_10.start_run(run_id="r10", workflow_name="workflow_engine", source=SOURCE_MANUAL, job_id="j10")
mgr_10.start_step("r10", "news")
snapshot_10 = mgr_10._last_acknowledged["r10"]
snapshot_10_step_obj = snapshot_10.steps[0]
snapshot_10_events_obj = snapshot_10.events
snapshot_10_events_len_before = len(snapshot_10_events_obj)
snapshot_10_step_status_before = snapshot_10_step_obj.status

# finish_step()内部でcandidate（deep copy）のpending stepをSUCCESSへ変更し、
# EVENT_STEP_FINISHEDイベントを追加する。
mgr_10.finish_step("r10", "news", StepExecutionStatus.SUCCESS)
new_snapshot_10 = mgr_10._last_acknowledged["r10"]

check(
    "10. 旧snapshotのsteps[0]オブジェクトのstatusは変化しない（shallow copyならSUCCESSへ"
    "書き換わってしまう）",
    snapshot_10_step_obj.status, snapshot_10_step_status_before,
)
check_false(
    "10. 旧snapshotのsteps[0]と新snapshotのsteps[0]は別オブジェクト（identity不一致=deep copy）",
    snapshot_10_step_obj is new_snapshot_10.steps[0],
)
check_false(
    "10. 旧snapshotのeventsリストと新snapshotのeventsリストは別オブジェクト（identity不一致=deep copy）",
    snapshot_10_events_obj is new_snapshot_10.events,
)
check(
    "10. 旧snapshotのevents件数は変化しない（新candidateへのEVENT_STEP_FINISHED追加が"
    "波及しない）",
    len(snapshot_10_events_obj), snapshot_10_events_len_before,
)
check_true(
    "10. 新snapshotのevents件数は旧snapshotより増えている",
    len(new_snapshot_10.events) > snapshot_10_events_len_before,
)
check(
    "10. 新snapshotのsteps[0].statusはSUCCESS（新しいcandidateが正しく反映される）",
    new_snapshot_10.steps[0].status, StepExecutionStatus.SUCCESS,
)
print()


# ═══════════════════════════════════════════════════════════
# テスト11-15: JsonExecutionHistoryStore atomic save
# ═══════════════════════════════════════════════════════════

print("[テスト11-15] JsonExecutionHistoryStore atomic save")

sample_record = WorkflowExecutionRecord(
    run_id="atomic-run", workflow_name="workflow_engine", source=SOURCE_MANUAL,
    job_id="j", status=WorkflowExecutionStatus.RUNNING, started_at=datetime.now(),
)


def _no_dot_files(d: Path) -> list[Path]:
    return list(d.glob(".*"))


# テスト11: mkstemp失敗
import tempfile as tempfile_module
tmp_dir_11 = Path(tempfile.mkdtemp()) / "history"
original_mkstemp = tempfile_module.mkstemp


def failing_mkstemp(*a, **kw):
    raise OSError("simulated mkstemp failure")


tempfile_module.mkstemp = failing_mkstemp
try:
    store_11 = JsonExecutionHistoryStore(tmp_dir_11)
    ok_11 = store_11.save(sample_record)
finally:
    tempfile_module.mkstemp = original_mkstemp
check_false("11. mkstemp失敗時はack=False", ok_11)

# テスト12: os.fdopen失敗（Release 6.30 Code Review Minor対応：fake fdopenが自ら
# fdをcloseしてしまうと、実装側のraw fd close経路を検証できない。fake側はfdへ
# 一切触れずraiseするだけにし、os.closeを計装して実装が「ちょうど1回だけ」
# raw fdをbest-effort closeすることを直接観測する）
tmp_dir_12 = Path(tempfile.mkdtemp()) / "history"
tmp_dir_12.mkdir(parents=True)
original_fdopen = os.fdopen
original_close_12 = os.close
_fdopen_fail_captured_fd_12 = []
_close_calls_12 = []


def failing_fdopen(fd, *a, **kw):
    # fdには一切触れない（ownershipはまだ実装側にある）。実際のfdopen失敗時と
    # 同じく、closeするかどうかの判断は呼び出し元（実装）に委ねる。
    _fdopen_fail_captured_fd_12.append(fd)
    raise OSError("simulated fdopen failure")


def recording_close_12(fd, *a, **kw):
    _close_calls_12.append(fd)
    return original_close_12(fd, *a, **kw)


os.fdopen = failing_fdopen
os.close = recording_close_12
try:
    store_12 = JsonExecutionHistoryStore(tmp_dir_12)
    ok_12 = store_12.save(sample_record)
finally:
    os.fdopen = original_fdopen
    os.close = original_close_12
check_false("12. os.fdopen()失敗時はack=False", ok_12)
check_true("12. os.fdopen()に渡されたraw fdが捕捉される", len(_fdopen_fail_captured_fd_12) == 1)
check(
    "12. 実装がraw fdをちょうど1回だけbest-effort closeする（二重closeなし）",
    _close_calls_12, _fdopen_fail_captured_fd_12,
)
check("12. tmpファイルが残らない（best-effort unlink）", len(_no_dot_files(tmp_dir_12)), 0)
check_false("12. canonical .jsonも作られない", (tmp_dir_12 / "atomic-run.json").exists())

# テスト13: write/fsync失敗
tmp_dir_13 = Path(tempfile.mkdtemp()) / "history"
original_fsync = os.fsync


def failing_fsync(*a, **kw):
    raise OSError("simulated fsync failure")


os.fsync = failing_fsync
try:
    store_13 = JsonExecutionHistoryStore(tmp_dir_13)
    ok_13 = store_13.save(sample_record)
finally:
    os.fsync = original_fsync
check_false("13. fsync失敗時はack=False", ok_13)
check("13. tmpファイルが残らない", len(_no_dot_files(tmp_dir_13)), 0)

# テスト14: os.replace失敗
tmp_dir_14 = Path(tempfile.mkdtemp()) / "history"
original_replace = os.replace


def failing_replace(*a, **kw):
    raise OSError("simulated replace failure")


os.replace = failing_replace
try:
    store_14 = JsonExecutionHistoryStore(tmp_dir_14)
    ok_14 = store_14.save(sample_record)
finally:
    os.replace = original_replace
check_false("14. os.replace失敗時はack=False", ok_14)
check("14. tmpファイルがbest-effort unlinkされる", len(_no_dot_files(tmp_dir_14)), 0)
check_false("14. canonical .jsonは作られない", (tmp_dir_14 / "atomic-run.json").exists())

# テスト15: cleanup（unlink）自体の失敗はackを変更しない
tmp_dir_15 = Path(tempfile.mkdtemp()) / "history"
original_replace_15 = os.replace
original_unlink = Path.unlink


def failing_replace_15(*a, **kw):
    raise OSError("simulated replace failure")


def failing_unlink(self, *a, **kw):
    raise OSError("simulated unlink failure")


os.replace = failing_replace_15
Path.unlink = failing_unlink
try:
    store_15 = JsonExecutionHistoryStore(tmp_dir_15)
    ok_15 = store_15.save(sample_record)
finally:
    os.replace = original_replace_15
    Path.unlink = original_unlink
check_false("15. replace失敗+cleanup失敗でもackはFalseのまま（変化しない）", ok_15)
print()


# ═══════════════════════════════════════════════════════════
# テスト16-21: WorkflowEngineExecutor Canonical Admission / 制御フロー
# ═══════════════════════════════════════════════════════════

print("[テスト16-21] WorkflowEngineExecutor Canonical Admission / 制御フロー")

# テスト16: history_manager省略×非dry-run → CanonicalAdmissionFailure、release_run()も呼ばれる
executor_16 = WorkflowEngineExecutor(WorkflowEngineDefinition(), all_success_step_executors())
raised_16 = None
try:
    executor_16.run(make_engine_context("r16"))
except CanonicalAdmissionFailure as e:
    raised_16 = e
check_true("16. CanonicalAdmissionFailureが送出される", raised_16 is not None)
check("16. reasonはEXECUTION_HISTORY_DISABLED", raised_16.reason, "EXECUTION_HISTORY_DISABLED")
check("16. run_idが一致する", raised_16.run_id, "r16")

# テスト17: start_run() ack=False → CanonicalAdmissionFailure(START_RUN_ACK_FAILED)
store_17 = FailableStore(always_fail=True)
mgr_17 = ExecutionHistoryManager(store=store_17)
executor_17 = WorkflowEngineExecutor(WorkflowEngineDefinition(), all_success_step_executors(), history_manager=mgr_17)
raised_17 = None
try:
    executor_17.run(make_engine_context("r17"))
except CanonicalAdmissionFailure as e:
    raised_17 = e
check_true("17. CanonicalAdmissionFailureが送出される", raised_17 is not None)
check("17. reasonはSTART_RUN_ACK_FAILED", raised_17.reason, "START_RUN_ACK_FAILED")

# テスト18: start_step() ack=False（NEWSで発生）
store_18 = FailableStore(fail_on_calls={2})
mgr_18 = ExecutionHistoryManager(store=store_18)
agents_18 = all_success_step_executors()
news_agent_18 = agents_18[WorkflowEngineStep.NEWS]._agent
executor_18 = WorkflowEngineExecutor(WorkflowEngineDefinition(), agents_18, history_manager=mgr_18)
result_18 = executor_18.run(make_engine_context("r18"))
check_false("18. overall_success=False", result_18.overall_success)
check_true("18. history_write_failed=True", result_18.history_write_failed)
check("18. NEWSはexecuted=False（Agent未実行）", result_18.steps[0].executed, False)
check("18. NEWSのskipped_reasonがREASON_HISTORY_WRITE_FAILED", result_18.steps[0].skipped_reason, REASON_HISTORY_WRITE_FAILED)
check("18. REVIEW/PUBLISHはNOT_REACHED（in-memoryのみ）", [s.skipped_reason for s in result_18.steps[1:]], [REASON_NOT_REACHED, REASON_NOT_REACHED])
check("18. NewsAgent.act()は呼ばれない", news_agent_18.act_call_count, 0)
saved_18 = store_18.get("r18")
check("18. durable recordはFAILEDへ終端する（finish_run(FAILED)が1回だけ呼ばれる）", saved_18.status, WorkflowExecutionStatus.FAILED)
check("18. durable recordのstepsは空（start_step失敗のためNEWSは一切persistされない）", len(saved_18.steps), 0)

# テスト19: finish_step() ack=False（NEWSのfinish_stepで発生・recovery成功）
store_19 = FailableStore(fail_on_calls={3})
mgr_19 = ExecutionHistoryManager(store=store_19)
executor_19 = WorkflowEngineExecutor(WorkflowEngineDefinition(), all_success_step_executors(), history_manager=mgr_19)
result_19 = executor_19.run(make_engine_context("r19"))
check_true("19. history_write_failed=True", result_19.history_write_failed)
check("19. REVIEW/PUBLISHはNOT_REACHED（in-memoryのみ、History呼び出しなし）", [s.skipped_reason for s in result_19.steps[1:]], [REASON_NOT_REACHED, REASON_NOT_REACHED])
calls_after_19 = store_19.call_count
check(
    "19. save()呼び出し回数は4回のみ（start_run+start_step+finish_step+recovery、"
    "以降finish_runは呼ばれない）",
    calls_after_19, 4,
)
saved_19 = store_19.get("r19")
check("19. durable recordはrecoveryによりFAILEDへ終端する", saved_19.status, WorkflowExecutionStatus.FAILED)

# テスト20: history_write_failed のlatch確認（正常runはFalseのまま）
store_20 = FailableStore()
mgr_20 = ExecutionHistoryManager(store=store_20)
executor_20 = WorkflowEngineExecutor(WorkflowEngineDefinition(), all_success_step_executors(), history_manager=mgr_20)
result_20 = executor_20.run(make_engine_context("r20"))
check_false("20. 正常runではhistory_write_failed=False", result_20.history_write_failed)
check_true("20. overall_success=True", result_20.overall_success)

# テスト20b: history_write_failed のlatch確認（一度Trueになった後、残りstepが
# in-memoryのみで処理される間もFalseへ戻らないこと。Release 6.30 Code Review
# Minor対応：テスト20は正常runのFalse固定のみを検証しておりlatch挙動そのもの
# （Trueになった後も最後まで保持される）は未検証だったため追加）
store_20b = FailableStore(fail_on_calls={3})
mgr_20b = ExecutionHistoryManager(store=store_20b)
executor_20b = WorkflowEngineExecutor(WorkflowEngineDefinition(), all_success_step_executors(), history_manager=mgr_20b)
result_20b = executor_20b.run(make_engine_context("r20b"))
check_true("20b. finish_step失敗直後にhistory_write_failed=True", result_20b.history_write_failed)
check(
    "20b. REVIEW/PUBLISHはin-memory NOT_REACHEDとして処理される（History呼び出しなし）",
    [s.skipped_reason for s in result_20b.steps[1:]], [REASON_NOT_REACHED, REASON_NOT_REACHED],
)
check_true(
    "20b. 残りstepがin-memory処理された最終結果でもhistory_write_failedはTrueのまま（latch）",
    result_20b.history_write_failed,
)

# テスト21: release_run()がCanonicalAdmissionFailure等でもfinallyで必ず呼ばれ、例外をマスクしない
# NullExecutionHistoryManagerを継承しない（継承するとExecutor側のNull判定が先に
# EXECUTION_HISTORY_DISABLEDでraiseしてしまい、START_RUN_ACK_FAILED経路を検証できないため）。
class _ReleaseTrackingHistoryManager:
    def __init__(self):
        self.release_calls = []

    def start_run(self, run_id, workflow_name, source, job_id):
        return StartRunWriteResult(run_id=run_id, acknowledged=False)  # START_RUN_ACK_FAILEDを誘発

    def start_step(self, run_id, step):
        return True

    def finish_step(self, run_id, step, status, error_message=None, skipped_reason=None):
        return True

    def finish_run(self, run_id, status, error_message=None):
        return True

    def release_run(self, run_id):
        self.release_calls.append(run_id)
        return None


tracking_mgr_21 = _ReleaseTrackingHistoryManager()
executor_21 = WorkflowEngineExecutor(WorkflowEngineDefinition(), all_success_step_executors(), history_manager=tracking_mgr_21)
raised_21 = None
try:
    executor_21.run(make_engine_context("r21"))
except CanonicalAdmissionFailure as e:
    raised_21 = e
check_true("21. CanonicalAdmissionFailureが送出される", raised_21 is not None)
check("21. release_run()がfinallyで1回呼ばれる", tracking_mgr_21.release_calls, ["r21"])
check(
    "21. 伝播した例外は元のCanonicalAdmissionFailureそのもの（reasonが変化しない）",
    raised_21.reason, "START_RUN_ACK_FAILED",
)

# release_run()がEXECUTION_HISTORY_DISABLED経路でも呼ばれることの確認（M9-1修正の回帰）。
# Release 6.30 Code Review Minor対応：従来はreasonのみ検証しrelease_run()の実呼び出しを
# 観測していなかったため、NullExecutionHistoryManager.release_run()をクラスレベルで
# 一時的に計装し、実際に呼ばれたことを直接観測する。
_release_calls_21b = []
_original_null_release_run = NullExecutionHistoryManager.release_run


def _tracking_null_release_run_21b(self, run_id):
    _release_calls_21b.append(run_id)
    return _original_null_release_run(self, run_id)


NullExecutionHistoryManager.release_run = _tracking_null_release_run_21b
executor_21b = WorkflowEngineExecutor(WorkflowEngineDefinition(), all_success_step_executors())
raised_21b = None
try:
    executor_21b.run(make_engine_context("r21b"))
except CanonicalAdmissionFailure as e:
    raised_21b = e
finally:
    NullExecutionHistoryManager.release_run = _original_null_release_run
check("21b. EXECUTION_HISTORY_DISABLED経路でも例外のreasonが正しい", raised_21b.reason if raised_21b else None, "EXECUTION_HISTORY_DISABLED")
check("21b. release_run()がEXECUTION_HISTORY_DISABLED経路でも実際に呼ばれる", _release_calls_21b, ["r21b"])
print()


# ═══════════════════════════════════════════════════════════
# テスト22-24: NewsPipelineRunner subprocess出力のbytes正規化
# ═══════════════════════════════════════════════════════════

print("[テスト22-24] NewsPipelineRunner subprocess出力のbytes正規化")

from pipeline import news_pipeline_runner as npr_module
from pipeline import NewsPipelineRunner


class _FakeRunnerConfig:
    def __init__(self, working_directory):
        self.python_executable = Path(sys.executable)
        self.main_py_path = Path("fake_main.py")
        self.working_directory = working_directory
        self.timeout_sec = 5


class _FakeCompleted:
    def __init__(self, stdout, stderr, returncode):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


original_subprocess_run = npr_module.subprocess.run
original_timeout_expired = npr_module.subprocess.TimeoutExpired

# テスト22: completed.stdout/stderrがbytes（不正なUTF-8シーケンス含む）
tmp_wd_22 = Path(tempfile.mkdtemp())
npr_module.subprocess.run = lambda *a, **kw: _FakeCompleted(
    stdout=b"stdout-bytes", stderr=b"stderr-bytes-\xff-invalid", returncode=1
)
try:
    runner_22 = NewsPipelineRunner(_FakeRunnerConfig(tmp_wd_22))
    no_exception_22 = True
    result_22 = runner_22.run({})
except Exception:
    no_exception_22 = False
    result_22 = None
finally:
    npr_module.subprocess.run = original_subprocess_run
check_true("22. bytes stdout/stderrでも例外を起こさない", no_exception_22)
check_false("22. returncode!=0のためsuccess=False", result_22.success)
check_true("22. error_messageはstr", isinstance(result_22.error_message, str))
check_contains("22. error_messageに正規化済みstderrが含まれる", result_22.error_message, "stderr-bytes-")
stdout_log_content_22 = result_22.stdout_log_path.read_text(encoding="utf-8")
check_contains("22. stdoutログファイルに正規化済み内容が保存される", stdout_log_content_22, "stdout-bytes")

# テスト23: TimeoutExpired.stdout/stderrがbytes
tmp_wd_23 = Path(tempfile.mkdtemp())


def raise_timeout(*a, **kw):
    raise npr_module.subprocess.TimeoutExpired(cmd=["x"], timeout=5, output=b"partial-out", stderr=b"partial-err")


npr_module.subprocess.run = raise_timeout
try:
    runner_23 = NewsPipelineRunner(_FakeRunnerConfig(tmp_wd_23))
    no_exception_23 = True
    result_23 = runner_23.run({})
except Exception:
    no_exception_23 = False
    result_23 = None
finally:
    npr_module.subprocess.run = original_subprocess_run
check_true("23. TimeoutExpiredのbytes stdout/stderrでも例外を起こさない", no_exception_23)
check_false("23. success=False", result_23.success)
check_contains("23. error_messageにタイムアウト診断が含まれる", result_23.error_message, "タイムアウトしました")
stderr_log_content_23 = result_23.stderr_log_path.read_text(encoding="utf-8")
check_contains("23. stderrログファイルに正規化済み内容が保存される", stderr_log_content_23, "partial-err")

# テスト24: Noneは空文字として扱われる
tmp_wd_24 = Path(tempfile.mkdtemp())
npr_module.subprocess.run = lambda *a, **kw: _FakeCompleted(stdout=None, stderr=None, returncode=0)
try:
    runner_24 = NewsPipelineRunner(_FakeRunnerConfig(tmp_wd_24))
    result_24 = runner_24.run({})
finally:
    npr_module.subprocess.run = original_subprocess_run
check_true("24. returncode=0でsuccess=True", result_24.success)
check("24. Noneのstdoutは空文字ログとして保存される", result_24.stdout_log_path.read_text(encoding="utf-8"), "")
print()


# ═══════════════════════════════════════════════════════════
# テスト25-35: main.py Outcome Contract
# ═══════════════════════════════════════════════════════════

print("[テスト25-35] main.py Outcome Contract")

main_source = (PROJECT_ROOT / "main.py").read_text(encoding="utf-8")
main_def_start = main_source.index("def main() -> int:")
main_body = main_source[main_def_start:main_source.index("\nif __name__ ==")]
check_false("25. main()本体にsys.exit(が残っていない", "sys.exit(" in main_body)
check_true("25. モジュール境界はsys.exit(main())のみ", "sys.exit(main())" in main_source)

sys.path.insert(0, str(PROJECT_ROOT))

_env_snapshot = dict(os.environ)
_argv_snapshot = list(sys.argv)
os.environ["ANTHROPIC_API_KEY"] = "fake-test-key-for-e2e"
os.environ["LOG_ENABLED"] = "false"
os.environ["ANALYTICS_ENABLED"] = "false"
# Release 6.30 Code Review Major対応: dotenvを遮断しても、実行プロセスの
# 既存os.environ（開発者シェル起動時点で偶然設定されていた値）は残りうる。
# main.pyが参照するWordPress・画像生成関連のgate/認証情報は、
# 「未設定（safe default）」であることを明示的に固定する（値の削除ではなく
# 既知の安全値への上書き）。
# WordPressOutputが実際に読むのはWP_SITE_URL（WP_URLではない。Round 2 Codex
# Reviewで指摘された変数名の取り違えを修正）。
for _leak_key in ("WP_SITE_URL", "WP_USERNAME", "WP_APP_PASSWORD"):
    os.environ[_leak_key] = ""
os.environ["AI_IMAGE_GENERATION_ENABLED"] = "false"
os.environ["OPENAI_IMAGE_GENERATION_ENABLED"] = "false"
sys.argv = ["main.py"]

# Release 6.30 Code Review Major対応: main.pyモジュールレベルのload_dotenv()が
# 実際のプロジェクト.envから未設定の値（WordPress認証情報・画像生成gate等）を
# 補完してしまうと、本番外部I/O（実WordPress投稿・実画像生成）に到達しうる。
# main.pyの`from dotenv import load_dotenv`がこのno-opを束縛するよう、
# importより前にdotenv.load_dotenv自体を無害化する。
import dotenv as _dotenv_module
_original_dotenv_load_dotenv = _dotenv_module.load_dotenv
_dotenv_module.load_dotenv = lambda *a, **kw: False

try:
    import main as main_module
finally:
    _dotenv_module.load_dotenv = _original_dotenv_load_dotenv

from collector import NewsItem, FeedStats
from outputs import SaveResult

FAKE_ITEM = NewsItem(
    title="Fake Game News", url="https://example.test/1", summary="s",
    source="FakeSource", published_at="2026-08-20T00:00:00Z",
)
FAKE_FEED_STATS = [FeedStats(source="FakeSource", count=1, status="ok")]


def _reset_argv(extra=None):
    sys.argv = ["main.py"] + (extra or [])


class _FakeFeaturedMediaResult:
    """ArticleFeaturedMediaRuntimeResultの最小限のstand-in（.article/.observationのみ）。"""

    def __init__(self, article):
        self.article = article
        self.observation = None


def _fake_apply_featured_media_step(runtime, article):
    # Release 6.30 Code Review Major対応: 実ArticleFeaturedMediaRuntime.apply()を
    # 一切呼び出さない（承認済みFacadeの唯一の呼び出し箇所を丸ごと差し替える）。
    # dotenvが遮断済みでも、プロセスに既に画像生成関連の環境変数が存在する
    # 可能性をゼロにするため、runtimeそのものを使わない構造的な隔離とする。
    return _FakeFeaturedMediaResult(article=article)


def _patch_generation_chain():
    main_module.generate_article = lambda client, item, importance: "本文テキスト"
    main_module.generate_seo_title = lambda client, item, importance: "SEOタイトル"
    main_module.generate_x_post = lambda client, item, importance, article_body, blog_url="": "xpost"
    main_module.resolve_featured_image = lambda item: ""
    main_module.resolve_media_id = lambda item, default_media_id: 0
    main_module.generate_slug = lambda seo_title, date_str: f"slug-{date_str}"
    main_module._apply_featured_media_step = _fake_apply_featured_media_step


def make_fake_wordpress_output_class(outcomes):
    class _FakeWordPressOutput:
        _outcomes = list(outcomes)

        def __init__(self):
            self._i = 0

        def is_available(self):
            return True

        def save(self, article):
            i = self._i
            self._i += 1
            ok = self._outcomes[i] if i < len(self._outcomes) else True
            if ok:
                return SaveResult(
                    success=True, output_type="wordpress", post_id=100 + i,
                    edit_url=f"https://example.test/wp-admin/post.php?post={100 + i}",
                    permalink=f"https://example.test/p/{100 + i}",
                )
            return SaveResult(success=False, output_type="wordpress", error_message="fake wp failure")

        @classmethod
        def from_env(cls):
            return cls()

    return _FakeWordPressOutput


_original_wordpress_output = main_module.WordPressOutput
_original_output_dir = main_module.OUTPUT_DIR
_original_collect_all_news = main_module.collect_all_news
_original_filter_news = main_module.filter_news
_original_deduplicate_news = main_module.deduplicate_news
_original_judge_all = main_module.judge_all
_original_generate_article = main_module.generate_article
_original_generate_seo_title = main_module.generate_seo_title
_original_generate_x_post = main_module.generate_x_post
_original_resolve_featured_image = main_module.resolve_featured_image
_original_resolve_media_id = main_module.resolve_media_id
_original_generate_slug = main_module.generate_slug
_original_apply_featured_media_step = main_module._apply_featured_media_step


def _restore_main_module():
    # Release 6.30 Code Review Minor対応: _patch_generation_chain()が置換した
    # 全関数をここで元へ戻す（テスト順序依存を排除する）。
    main_module.WordPressOutput = _original_wordpress_output
    main_module.OUTPUT_DIR = _original_output_dir
    main_module.collect_all_news = _original_collect_all_news
    main_module.filter_news = _original_filter_news
    main_module.deduplicate_news = _original_deduplicate_news
    main_module.judge_all = _original_judge_all
    main_module.generate_article = _original_generate_article
    main_module.generate_seo_title = _original_generate_seo_title
    main_module.generate_x_post = _original_generate_x_post
    main_module.resolve_featured_image = _original_resolve_featured_image
    main_module.resolve_media_id = _original_resolve_media_id
    main_module.generate_slug = _original_generate_slug
    main_module._apply_featured_media_step = _original_apply_featured_media_step


try:
    # テスト26: --max-articles不正
    _reset_argv(["--max-articles", "-1"])
    check("26. --max-articles不正 → 1", main_module.main(), 1)

    # テスト27: ANTHROPIC_API_KEY未設定
    _reset_argv()
    del os.environ["ANTHROPIC_API_KEY"]
    check("27. ANTHROPIC_API_KEY未設定 → 1", main_module.main(), 1)
    os.environ["ANTHROPIC_API_KEY"] = "fake-test-key-for-e2e"

    # テスト28: RSS収集0件
    main_module.collect_all_news = lambda **kwargs: ([], [])
    _reset_argv()
    check("28. RSS収集0件 → 1", main_module.main(), 1)
    main_module.collect_all_news = _original_collect_all_news

    # テスト29: フィルター後0件
    main_module.collect_all_news = lambda **kwargs: ([FAKE_ITEM], FAKE_FEED_STATS)
    main_module.filter_news = lambda news: {"pass": [], "pending": []}
    _reset_argv()
    check("29. フィルター後0件 → 0", main_module.main(), 0)
    main_module.filter_news = _original_filter_news

    # テスト30: importance判定後0件（すべて「なし」）
    main_module.filter_news = lambda news: {"pass": news, "pending": []}
    main_module.deduplicate_news = lambda news: news
    main_module.judge_all = lambda client, news: [{"item": n, "importance": "なし"} for n in news]
    _reset_argv()
    check("30. importance判定後0件 → 0", main_module.main(), 0)

    # テスト31: generation対象0件（--max-articles 0）
    main_module.judge_all = lambda client, news: [{"item": n, "importance": "S"} for n in news]
    _reset_argv(["--max-articles", "0"])
    check("31. generation対象0件（--max-articles 0） → 0", main_module.main(), 0)

    _patch_generation_chain()
    main_module.OUTPUT_DIR = Path(tempfile.mkdtemp()) / "output"

    # テスト32: 全記事WordPress成功
    main_module.WordPressOutput = make_fake_wordpress_output_class([True, True])
    main_module.collect_all_news = lambda **kwargs: ([FAKE_ITEM, FAKE_ITEM], FAKE_FEED_STATS)
    _reset_argv()
    check("32. 全記事WordPress成功 → 0", main_module.main(), 0)

    # テスト33: 一部成功・一部失敗 → PARTIAL/20
    main_module.WordPressOutput = make_fake_wordpress_output_class([True, False])
    _reset_argv()
    check("33. 一部成功・一部失敗 → 20", main_module.main(), 20)

    # テスト34: 全記事WordPress失敗 → ALL_FAILED/21
    main_module.WordPressOutput = make_fake_wordpress_output_class([False, False])
    _reset_argv()
    check("34. 全記事WordPress失敗 → 21", main_module.main(), 21)

    # テスト35: WordPress未設定（is_available()=False） → 全skip → SUCCESS/0
    main_module.WordPressOutput = _original_wordpress_output
    for key in ("WP_SITE_URL", "WP_USERNAME", "WP_APP_PASSWORD"):
        os.environ.pop(key, None)
    _reset_argv()
    check("35. WordPress全skip → 0", main_module.main(), 0)
finally:
    _restore_main_module()
    os.environ.clear()
    os.environ.update(_env_snapshot)
    sys.argv = _argv_snapshot
print()


# ═══════════════════════════════════════════════════════════
# テスト36-38: scripts/run_workflow_engine.py
# ═══════════════════════════════════════════════════════════

print("[テスト36-38] scripts/run_workflow_engine.py")

script_path_we = PROJECT_ROOT / "scripts" / "run_workflow_engine.py"


# Release 6.30 Code Review Round 2 Minor対応: run_workflow_engine.py自身も
# モジュールレベルでload_dotenv(project_root/.env)を実行する（override=False、
# 未設定キーのみ実.envから補完される）。python-dotenvのoverride=Falseの
# 挙動を利用し、CLI経路で読まれうる全てのgate/interval/History/外部I/O設定
# キーをここで明示的にos.environへ事前設定しておくことで、実.envの値が
# 補完される余地そのものをなくす（値の削除ではなく安全値への上書き）。
# PYTHON_DOTENV_DISABLED=1 も付与する（本プロジェクトのload_dotenv()自体は
# このフラグを参照しないため単独では効果を持たないが、docs/design/
# production_canonical_run_outcome_contract_foundation.md 29章の
# Verification isolation規約との一貫性のため、意図表明として設定する）。
# テストごとの上書き（env_overrides）はこのsafe defaultの後に適用され、
# 意図した値のみを上書きする。
_WE_CLI_SAFE_DEFAULTS = {
    "PYTHON_DOTENV_DISABLED": "1",
    "AI_AGENT_ENABLED": "false",
    "WORKFLOW_ENGINE_ENABLED": "false",
    "EXECUTION_HISTORY_ENABLED": "false",
    "EXECUTION_HISTORY_DIR": "logs/execution_history",
    "REVIEW_TRIGGER_AGENT_ENABLED": "false",
    "REVIEW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES": "1440",
    "PUBLISH_TRIGGER_AGENT_ENABLED": "false",
    "PUBLISH_TRIGGER_AGENT_MIN_INTERVAL_MINUTES": "1440",
    "NEWS_AGENT_MIN_INTERVAL_MINUTES": "180",
    "NEWS_AGENT_TIMEOUT_SEC": "1800",
    "NEWS_AGENT_LOG_LOOKBACK_DAYS": "2",
    "AI_PUBLISH_ENABLED": "false",
    "WORDPRESS_URL": "",
    "WORDPRESS_USERNAME": "",
    "WORDPRESS_APP_PASSWORD": "",
    # WordPressOutputが実際に読むのはWP_URLではなくWP_SITE_URL（Round 2 Codex
    # Reviewで指摘された変数名の取り違えを修正）。
    "WP_SITE_URL": "",
    "WP_USERNAME": "",
    "WP_APP_PASSWORD": "",
}


def run_we_cli(args, env_overrides):
    env = dict(os.environ)
    env.update(_WE_CLI_SAFE_DEFAULTS)
    env.update(env_overrides)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(script_path_we)] + args,
        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace", env=env, timeout=60,
    )


# テスト36: gate OFF → exit 0（gate/configは削除ではなく明示的にfalse固定。
# 実.envでAI_AGENT_ENABLED/WORKFLOW_ENGINE_ENABLEDが有効でも、決定的にgate OFF経路を通る）
completed_36 = run_we_cli([], {})
check("36. gate OFF → exit 0", completed_36.returncode, 0)

# テスト37: dry-run + History OFF → 早期exit1にならず正常終了（M8-1回帰）
completed_37 = run_we_cli(
    ["--dry-run", "--job-id", "v6-30-e2e-37"],
    {"AI_AGENT_ENABLED": "true", "WORKFLOW_ENGINE_ENABLED": "true", "EXECUTION_HISTORY_ENABLED": "false"},
)
check("37. dry-run + History OFF → exit 0", completed_37.returncode, 0)

# テスト38: non-dry-run + History OFF → exit 1（N8-1）
completed_38 = run_we_cli(
    ["--job-id", "v6-30-e2e-38"],
    {"AI_AGENT_ENABLED": "true", "WORKFLOW_ENGINE_ENABLED": "true", "EXECUTION_HISTORY_ENABLED": "false"},
)
check("38. non-dry-run + History OFF → exit 1", completed_38.returncode, 1)
check_contains("38. エラーメッセージが表示される", completed_38.stdout, "EXECUTION_HISTORY_ENABLED=true")
print()


# ═══════════════════════════════════════════════════════════
# テスト39: Retry Runtime Ruling A
# ═══════════════════════════════════════════════════════════

print("[テスト39] Retry Runtime Ruling A（CanonicalAdmissionFailureのfail-fast伝播）")

from retry_engine import RetryManager
from retry_engine.retry_executor import RetryExecutor
from retry_engine.retry_policy import RetryPolicy
from workflow_engine import WorkflowEngineManager
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus


class _AdmissionFailingWorkflowEngineManager:
    """WorkflowEngineManager.run()がCanonicalAdmissionFailureを送出するFake。"""

    def is_available(self):
        return True

    def run(self, event, dry_run=False):
        raise CanonicalAdmissionFailure(run_id="retry-r1", reason="EXECUTION_HISTORY_DISABLED")


class _FixedStatusMonitor:
    def get_status(self, run_id):
        return WorkflowMonitorRecord(
            run_id=run_id, workflow_name="workflow_engine",
            monitor_status=WorkflowMonitorStatus.FAILED, source_status="failed",
            source=SOURCE_MANUAL, job_id="job-retry-39",
            started_at=datetime.now(), finished_at=datetime.now(),
            elapsed_seconds=1.0, reason="boom", steps=[],
        )


retry_manager_39 = RetryManager(
    policy=RetryPolicy(target_statuses={WorkflowMonitorStatus.FAILED}, max_attempts=3),
    executor=RetryExecutor(workflow_engine_manager=_AdmissionFailingWorkflowEngineManager()),
    monitor=_FixedStatusMonitor(),
)
raised_39 = None
try:
    retry_manager_39.retry(run_id="retry-r1", attempt=1)
except CanonicalAdmissionFailure as e:
    raised_39 = e
check_true("39. RetryManager.retry()経由でCanonicalAdmissionFailureが変換されず伝播する", raised_39 is not None)
check("39. reasonが変化しない", raised_39.reason if raised_39 else None, "EXECUTION_HISTORY_DISABLED")
print()


# ═══════════════════════════════════════════════════════════
# テスト40-46: NewsPipelineRunner NEWS Outcome Token（§6、human-directed addition）
# ═══════════════════════════════════════════════════════════

print("[テスト40-46] NewsPipelineRunner NEWS Outcome Token")

from pipeline.news_pipeline_runner import (
    NEWS_OUTCOME_ABNORMAL_EXIT,
    NEWS_OUTCOME_ALL_FAILED_EXIT_21,
    NEWS_OUTCOME_GENERIC_FAILURE_EXIT_1,
    NEWS_OUTCOME_LAUNCH_FAILURE,
    NEWS_OUTCOME_PARTIAL_EXIT_20,
    NEWS_OUTCOME_TIMEOUT,
)


def _run_with_fake_completed(returncode):
    tmp_wd = Path(tempfile.mkdtemp())
    npr_module.subprocess.run = lambda *a, **kw: _FakeCompleted(
        stdout="out", stderr="stderr-detail", returncode=returncode
    )
    try:
        runner = NewsPipelineRunner(_FakeRunnerConfig(tmp_wd))
        return runner.run({})
    finally:
        npr_module.subprocess.run = original_subprocess_run


# テスト40: returncode=1 → NEWS_OUTCOME_GENERIC_FAILURE_EXIT_1
result_40 = _run_with_fake_completed(1)
check_true(
    "40. returncode=1のerror_messageがNEWS_OUTCOME_GENERIC_FAILURE_EXIT_1で始まる",
    result_40.error_message.startswith(NEWS_OUTCOME_GENERIC_FAILURE_EXIT_1 + "\n"),
)
check_contains("40. token行の後にstderr診断が続く", result_40.error_message, "stderr-detail")

# テスト41: returncode=20 → NEWS_OUTCOME_PARTIAL_EXIT_20
result_41 = _run_with_fake_completed(20)
check_true(
    "41. returncode=20のerror_messageがNEWS_OUTCOME_PARTIAL_EXIT_20で始まる",
    result_41.error_message.startswith(NEWS_OUTCOME_PARTIAL_EXIT_20 + "\n"),
)

# テスト42: returncode=21 → NEWS_OUTCOME_ALL_FAILED_EXIT_21
result_42 = _run_with_fake_completed(21)
check_true(
    "42. returncode=21のerror_messageがNEWS_OUTCOME_ALL_FAILED_EXIT_21で始まる",
    result_42.error_message.startswith(NEWS_OUTCOME_ALL_FAILED_EXIT_21 + "\n"),
)

# テスト43: returncode=99（未知） → NEWS_OUTCOME_ABNORMAL_EXIT
result_43 = _run_with_fake_completed(99)
check_true(
    "43. returncode=99（未知）のerror_messageがNEWS_OUTCOME_ABNORMAL_EXITで始まる",
    result_43.error_message.startswith(NEWS_OUTCOME_ABNORMAL_EXIT + "\n"),
)

# テスト44: TimeoutExpired → NEWS_OUTCOME_TIMEOUT
tmp_wd_44 = Path(tempfile.mkdtemp())
npr_module.subprocess.run = raise_timeout
try:
    runner_44 = NewsPipelineRunner(_FakeRunnerConfig(tmp_wd_44))
    result_44 = runner_44.run({})
finally:
    npr_module.subprocess.run = original_subprocess_run
check_true(
    "44. TimeoutExpiredのerror_messageがNEWS_OUTCOME_TIMEOUTで始まる",
    result_44.error_message.startswith(NEWS_OUTCOME_TIMEOUT + "\n"),
)
check_contains("44. token行の後にタイムアウト診断が続く", result_44.error_message, "タイムアウトしました")

# テスト45: subprocess.run()がOSErrorを送出（launch failure）
tmp_wd_45 = Path(tempfile.mkdtemp())


def raise_launch_failure(*a, **kw):
    raise FileNotFoundError("simulated: python executable not found")


npr_module.subprocess.run = raise_launch_failure
try:
    runner_45 = NewsPipelineRunner(_FakeRunnerConfig(tmp_wd_45))
    no_exception_45 = True
    result_45 = runner_45.run({})
except Exception:
    no_exception_45 = False
    result_45 = None
finally:
    npr_module.subprocess.run = original_subprocess_run
check_true("45. launch failure（OSError）でも例外を起こさない", no_exception_45)
check_false("45. success=False", result_45.success)
check_none("45. returncodeはNone", result_45.returncode)
check_true(
    "45. error_messageがNEWS_OUTCOME_LAUNCH_FAILUREで始まる",
    result_45.error_message.startswith(NEWS_OUTCOME_LAUNCH_FAILURE + "\n"),
)
check_contains("45. launch failureの診断に元の例外メッセージが含まれる", result_45.error_message, "python executable not found")

# テスト46: 成功時（returncode=0） → error_messageはNone
result_46 = _run_with_fake_completed(0)
check_true("46. returncode=0でsuccess=True", result_46.success)
check_none("46. 成功時のerror_messageはNone（tokenは付与されない）", result_46.error_message)
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
