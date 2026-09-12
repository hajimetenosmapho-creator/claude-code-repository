"""
E2E テスト: Release 6.32 — Admission Failure / Durable Save Failure Closure
（§18 test#13 + test#17）

Source of Truth: docs/design/
side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md
§4.1・§9.3（Combination Table、行2・行5）・§18 test#13・test#17・
Hard-Crash Test Methodology（test#25）

## read-only事前確認で判明した実コードの因果関係（本ファイル作成前に実施）

`RetryLineageManager.mark_execution_started()`
（src/retry_lineage/retry_lineage_manager.py:453-510）は、
`self._manifest.create_for_attempt(...)`の戻り値が falsy（`if not manifest_ok:`）
なら例外を発生させず素通しで`return False`する——一方、抽象契約上
`create_for_attempt()`が実際に「失敗」を表現する主要な手段は例外
（`ProtectedOperationManifestContractViolationError`／`IOError`）であり、
具象実装`JsonProtectedOperationManifestStore.create_for_attempt()`は
Falseを返す経路を持たない（成功→True、失敗→例外、のいずれかのみ）。

`RetryExecutor.execute()`（retry_executor.py:172-330）は、
`post_admission_hook`（`mark_execution_started()`を包む）の失敗を2つの
互いに独立した経路で扱う：

    (経路1) hookが**例外を送出**した場合：`WorkflowEngineExecutor`
    （`self._engine.run()`）内部の`except Exception as exc:`
    （workflow_engine_executor.py:206）が**先に**これを捕捉し、
    `StepSkipCategory.HOOK_EXCEPTION`としてstepをskip扱いに変換した上で
    `run()`は正常return する。この場合、`hook_ack_state["acknowledged"]`は
    初期値`None`のまま（`ack = mark_execution_started(...)`行自体が例外で
    中断するため代入されない）。`RetryExecutor.execute()`側の
    `hook_ack_state["acknowledged"] is False`チェック（line 244）は
    `None`にはmatchしないため**この経路ではrelease_claim()は呼ばれず**、
    後続の`mark_terminal()`が`phase != EXECUTION_STARTED`によりacknowledged=False
    を返し、`RetryResult(outcome=SKIPPED, reason="mark_terminal() did not
    acknowledge...deferring to reconcile_all()")`として、CLAIMED orphan
    回収（既存reconcile_all()、test#22で証明済み）へ回収を委ねる。

    (経路2) hookが**素直にFalseを返した**場合（`mark_execution_started()`が
    例外なくFalseを返す——owner_token precheck失敗、または
    `create_for_attempt()`がFalseを返す場合）：`hook_ack_state["acknowledged"]`
    は確実に`False`となり、`RetryExecutor.execute()`のline 244-245が
    **同期的に`release_claim()`を呼び**、`RetryOutcome.SKIPPED`を返す。

§18 test#13の文言（「mark_execution_started()がFalseを返す」
「後続のrelease_claim()呼び出しが実際にTrueを返す」）は明確に**経路2**を
指しており、プロセスは生存する（§9.3表2行目「安全（プロセス生存、lockは
正常解放される）」とも整合）。したがって**test#13はCategory A
（fault-injection、mock/fakeで再現可能）であり、Category B
（hard-crash）は不要**と結論する——test#25の文中に残る「test#13・15・22は
hard-crash対象」という記述は、Round 9以前の版から残った**stale
cross-reference**であり、architecture semantics自体の変更を要する指摘では
ない（Sub-milestone Cでdocumentation cleanupとして扱う）。

§18 test#17は、manifest createは成功した**後**（§9.3表・行5）に
`self._store.save(record)`（lineage側、JsonRetryLineageStore.save()、
retry_lineage_store.py:53-96）が明示的Falseを返す場合を扱う。これも
経路2に合流する（`mark_execution_started()`の最終行`return self._store
.save(record)`がFalseを返すのみで、例外は発生しない）。

## 因果関係の切り分け（duplicate side-effect safetyへの影響有無）

release_claim()の戻り値をRetryExecutor.execute()（line 244-245）が
checkしていないという既存6.31由来のgapは、以下の理由により**Release 6.32
のduplicate side-effect safetyを破らない**と判断した（read-onlyの
コード確認に基づく検証であり、単なる「既存limitationだから」という
機械的waiveではない）：

    1. hook_ack_state["acknowledged"] is Falseの経路は、
       `WorkflowEngineExecutor`のHOOK_NOT_ACKNOWLEDGED skip処理により、
       呼び出し箇所A/B/C（write-ahead・外部I/O）へ一切到達しない
       （本ファイルのグループM/Nで直接確認する、呼び出し回数=0）。
       つまりrelease_claim()が実際に失敗しても、**再現され得る側面効果が
       そもそも一切発生していない**——「二重実行」という前提事象がない。
    2. release_claim()が失敗した場合でもdurable lineage phaseはCLAIMEDの
       まま変化しない（fail-closed、本ファイルのグループNで直接確認）。
    3. CLAIMEDのまま取り残されたlineageは、release_claim()の成否や
       RetryResult.reasonの文言に一切依存しない既存の
       `_reconcile_all_locked()`のCLAIMED orphan回収ロジック
       （test#22・test_e2e_v6_32_31で実証済み）により、次回の
       `reconcile_all()`呼び出しで確実に回収される（本ファイルのグループNで
       この回収チェーンまで直接確認する）。

以上により、この既存gapは「診断メッセージの精度」の問題であり、
durable stateやduplicate side-effect safetyそのものを損なわない。
NEEDS HUMAN GATEでの停止は不要と判断する。

## 必須確認項目

グループM（§18 test#13）：
    (a) mark_execution_started()がFalseを返す
    (b) durable lineage phaseがCLAIMEDのまま変化しない
    (c) 後続のrelease_claim()呼び出しが実際にTrueを返しREADY_ELIGIBLEへ戻る
    (d) 呼び出し箇所A/B/Cのいずれも一度も呼ばれず外部I/Oも一切発生しない
        （RetryExecutor.execute()の実チェーンで確認）
    (e) 後続recovery/reclaimが安全（新しいmember_run_idで正常に進む）

グループN（§18 test#17 (a)-(d)・(f)）：
    (a) durable lineageはCLAIMEDのまま
    (b) manifest generationはorphanとして残る（削除されない）
    (c) 呼び出し箇所A/B/Cのいずれも一度も呼ばれず外部I/O=0
    (d) release_claim()のactual result/handling：
        - 通常ケース（release_claim()自体は成功する）でのRetryResult.reason
          文言と実際のdurable phaseの一致を直接確認する
        - release_claim()自体も失敗する最悪ケースを構成し、
          durable phaseがCLAIMEDのまま（破損しない）こと、かつ
          既存reconcile_all()のCLAIMED orphan回収で最終的に安全に
          回収されることまで直接確認する（duplicate side-effect
          safetyへの影響がないことの実証）
    (f) 後続recovery/reclaimでold orphan manifestを再利用しない
        （新しいmember_run_idで新規manifestが作られ、旧orphanは不変のまま
        共存する）

§18 test#17(e)（stale A/current B protection）は
test_e2e_v6_32_27（グループ2、3e〜3i）・test_e2e_v6_32_34（グループL）で
既に直接証明済みのため、本ファイルでは再証明しない。

production code（RetryLineageManager・RetryExecutor・
JsonRetryLineageStore・ProtectedOperationManifestStore等）は
一切変更しない。network / WordPress / 外部I/O = 0。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_35_admission_failure_durable_save_failure_closure.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from dataclasses import dataclass
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


def check_false(label: str, value: bool):
    check(label, bool(value), False)


print("=" * 70)
print("Admission Failure / Durable Save Failure Closure（§18 #13+#17） — E2E テスト")
print("=" * 70)
print()

from protected_operation_manifest import (
    JsonProtectedOperationManifestStore,
    ManifestReaderFacade,
)
from retry_engine import RetryExecutor, RetryOutcome, RetryRequest
from retry_lineage import (
    JsonRetryLineageStore,
    RetryLineageConfig,
    RetryLineageManager,
    RetryLineagePhase,
)
from side_effect_safety import ProtectedSideEffectKind, SideEffectSite
from side_effect_safety_classifier import SideEffectSafetyClassifier
from side_effect_safety.media_upload_applicability_store import JsonMediaUploadApplicabilityStore
from side_effect_safety.media_upload_attempt_context_store import JsonMediaUploadAttemptContextStore
from side_effect_safety.media_upload_safety_coordinator import build_media_upload_safety_coordinator
from article_media_upload_state import ArticleMediaUploadStateManager, JsonArticleMediaUploadStateStore
from wordpress_draft_state import JsonWordPressDraftStateStore
from workflow_engine import ALL_WORKFLOW_ENGINE_STEPS, WorkflowEngineResult, WorkflowEngineStepResult
from workflow_monitor import WorkflowMonitorStatus

tmp_dirs: list[Path] = []


class FakePolicy:
    def __init__(self, max_attempts: int = 5):
        self.target_statuses = frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT})
        self._max_attempts = max_attempts

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    def should_retry(self, monitor_status, attempt: int) -> bool:
        return monitor_status in self.target_statuses and attempt < self._max_attempts


def make_monitor_record(run_id: str):
    from workflow_monitor import WorkflowMonitorRecord
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=WorkflowMonitorStatus.FAILED,
        source_status="FAILED", source="manual", job_id="job-1",
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=[],
    )


def make_stack():
    tmp_root = Path(tempfile.mkdtemp(prefix="v6_32_35_"))
    tmp_dirs.append(tmp_root)
    lineage_config = RetryLineageConfig(enabled=True, lineage_dir=tmp_root / "lineage")
    lineage_store = JsonRetryLineageStore(lineage_config.store_dir)
    manifest_store = JsonProtectedOperationManifestStore(base_dir=tmp_root / "manifest")
    draft_state_store = JsonWordPressDraftStateStore(base_dir=tmp_root / "wordpress_draft_state")
    media_upload_coordinator = build_media_upload_safety_coordinator(
        media_upload_manager=ArticleMediaUploadStateManager(
            JsonArticleMediaUploadStateStore(tmp_root / "article_media_upload_state")
        ),
        applicability_store=JsonMediaUploadApplicabilityStore(tmp_root / "media_upload_applicability"),
        attempt_context_store=JsonMediaUploadAttemptContextStore(tmp_root / "media_upload_attempt_context"),
        locks_dir=tmp_root / "media_upload_locks",
    )
    classifier = SideEffectSafetyClassifier(media_coordinator=media_upload_coordinator, draft_state=draft_state_store)
    lineage = RetryLineageManager(
        store=lineage_store, config=lineage_config, policy=FakePolicy(),
        manifest=manifest_store, side_effect_classifier=classifier,
    )
    return lineage, manifest_store, lineage_store, draft_state_store


@dataclass
class FakeAgentResult:
    success: bool
    action_taken: bool | None = None

    def to_dict(self):
        return {"success": self.success, "action_taken": self.action_taken}


class HookAckAwareEngine:
    """実WorkflowEngineExecutorのHOOK_NOT_ACKNOWLEDGED挙動を模す：
    post_admission_hook()のack結果を見て、acknowledged=Falseならどの
    call-site write-ahead（draft_state等）も一切呼ばずに全stepをskip
    扱いで返す。acknowledged=Trueの場合のみ、call-site相当の処理
    （draft_state.create_attempted呼び出し）を行う。write_ahead_calls
    （呼び出し元から渡すlist）でcall-site write-ahead呼び出し回数を
    観測できる。"""

    def __init__(self, draft_state_store, member_run_id: str, write_ahead_calls: list, slug: str = "article"):
        self._draft_state = draft_state_store
        self._member_run_id = member_run_id
        self._write_ahead_calls = write_ahead_calls
        self._slug = slug
        self.calls = 0

    def run(self, event, dry_run=False, target_step_filter=None, post_admission_hook=None,
            correlation_metadata=None, side_effect_execution_provenance=None):
        self.calls += 1
        run_id = self._member_run_id
        root_run_id = event.job_id
        acked = True
        if post_admission_hook is not None:
            hook_result = post_admission_hook(run_id)
            acked = bool(hook_result.acknowledged)

        if not acked:
            steps = [
                WorkflowEngineStepResult(step=s, executed=False, agent_result=None, success=False, skipped_reason="hook not acknowledged")
                for s in ALL_WORKFLOW_ENGINE_STEPS
            ]
            return WorkflowEngineResult(
                run_id=run_id, steps=steps, overall_success=False, stopped_early=True,
                started_at=datetime.now(), finished_at=datetime.now(),
            )

        from side_effect_safety import SideEffectOperationIdentity
        identity = SideEffectOperationIdentity(
            root_run_id=root_run_id, attempt_ordinal=1,
            operation_kind=ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION,
            effect_site=SideEffectSite.NEWS_STEP, operation_instance_key=self._slug,
        )
        self._write_ahead_calls.append((root_run_id, run_id))
        self._draft_state.create_attempted(identity, run_id, datetime.now().isoformat())
        steps = [WorkflowEngineStepResult(step=s, executed=True, agent_result=FakeAgentResult(True, True), success=True) for s in ALL_WORKFLOW_ENGINE_STEPS]
        return WorkflowEngineResult(
            run_id=run_id, steps=steps, overall_success=True, stopped_early=False,
            started_at=datetime.now(), finished_at=datetime.now(),
        )


# =====================================================================
# グループM：§18 test#13 — admission時 create_for_attempt() 失敗（Category A）
# =====================================================================
print("[グループM] §18 test#13: create_for_attempt()が明示的にFalseを返す（プロセス生存）")

lineage_m, manifest_m, store_m, draft_state_m = make_stack()
created_m = lineage_m.create_new_lineage("run-m", make_monitor_record("run-m"))
claim_m = lineage_m.claim("run-m")
check_true("M前提: claim()成功", claim_m.acknowledged)

# create_for_attempt()を明示的Falseへfault injection（例外ではなく、通常の
# falsy return——production契約上ありうる失敗モードを直接模す）。
manifest_m.create_for_attempt = lambda *a, **kw: False

# --- (a)(b): mark_execution_started()を直接呼び、isolatedに確認 ---
before_m = lineage_m.peek("run-m")
result_m1 = lineage_m.mark_execution_started("run-m", "exec-run-m1", claim_m.owner_token)
check_false("M1(a). mark_execution_started()はFalseを返す", result_m1)
after_fail_m = lineage_m.peek("run-m")
check("M2(b). durable lineage phaseはCLAIMEDのまま変化しない", after_fail_m.phase, RetryLineagePhase.CLAIMED)
check("M3(b). durable recordの他フィールドも不変（attempt_count等）",
      (after_fail_m.attempt_count, after_fail_m.latest_run_id), (before_m.attempt_count, before_m.latest_run_id))

# --- (c): 後続のrelease_claim()が実際にTrueを返しREADY_ELIGIBLEへ戻る ---
result_release_m = lineage_m.release_claim("run-m", claim_m.owner_token)
check_true("M4(c). 後続release_claim()は実際にTrueを返す", result_release_m)
check("M5(c). release_claim()後、phase=READY_ELIGIBLE", lineage_m.peek("run-m").phase, RetryLineagePhase.READY_ELIGIBLE)

# --- (d): RetryExecutor.execute()の実チェーンでA/B/C write-ahead=0・外部I/O=0 ---
lineage_m2, manifest_m2, store_m2, draft_state_m2 = make_stack()
manifest_m2.create_for_attempt = lambda *a, **kw: False
created_m2 = lineage_m2.create_new_lineage("run-m2", make_monitor_record("run-m2"))
claim_m2 = lineage_m2.claim("run-m2")
write_ahead_calls_m2: list = []
engine_m2 = HookAckAwareEngine(draft_state_m2, member_run_id="exec-run-m2", write_ahead_calls=write_ahead_calls_m2)
executor_m2 = RetryExecutor(
    workflow_engine_manager=engine_m2, lineage=lineage_m2,
    manifest=ManifestReaderFacade(manifest_m2), side_effect_classifier=None,
)
request_m2 = RetryRequest(run_id="run-m2", attempt=1, requested_at=datetime.now(), dry_run=False)
result_full_m2 = executor_m2.execute(request_m2, created_m2.lineage, claim_m2)

check("M6(d). RetryExecutor.execute()の結果はSKIPPED", result_full_m2.outcome, RetryOutcome.SKIPPED)
check_true("M7(d). reasonに'post-admission hook did not acknowledge'を含む", "post-admission hook did not acknowledge" in (result_full_m2.reason or ""))
check("M8(d). 呼び出し箇所write-ahead相当（draft_state.create_attempted）の呼び出し回数=0", len(write_ahead_calls_m2), 0)
check("M9(d). execute()完了後、phase=READY_ELIGIBLE（同期的にrelease_claim()成功）", lineage_m2.peek("run-m2").phase, RetryLineagePhase.READY_ELIGIBLE)

# --- (e): 後続recovery/reclaimが安全 ---
claim_m2b = lineage_m2.claim("run-m2")
check_true("M10(e). release後の再claim()は正常に成功する", claim_m2b.acknowledged)
del manifest_m2.create_for_attempt  # fault除去：instance override削除→本来のclass実装へ復帰
mark_ok_m2b = lineage_m2.mark_execution_started("run-m2", "exec-run-m2b", claim_m2b.owner_token)
check_true("M11(e). fault除去後の再claimでは正常にmark_execution_started()が成功する", mark_ok_m2b)
print()


# =====================================================================
# グループN：§18 test#17(a)-(d)(f) — manifest成功後のlineage save明示的False
# =====================================================================
print("[グループN] §18 test#17(a)-(d)(f): manifest成功後、lineage save()が明示的Falseを返す")

lineage_n, manifest_n, store_n, draft_state_n = make_stack()
created_n = lineage_n.create_new_lineage("run-n", make_monitor_record("run-n"))
claim_n = lineage_n.claim("run-n")
check_true("N前提: claim()成功", claim_n.acknowledged)

store_n.save = lambda record: False  # manifest createは実行させたまま、lineage save()のみ失敗させる

result_n1 = lineage_n.mark_execution_started("run-n", "exec-run-n1", claim_n.owner_token)
check_false("N1(a). mark_execution_started()はFalseを返す（save失敗）", result_n1)
check("N2(a). durable lineage phaseはCLAIMEDのまま", lineage_n.peek("run-n").phase, RetryLineagePhase.CLAIMED)

# (b) manifestはorphanとして実在する（durableに作成済み、save失敗の影響を受けない）。
entries_orphan_n = manifest_n.list_for_attempt("run-n", 1, "exec-run-n1")
check("N3(b). manifestはorphanとしてdurableに実在する（entries=()）", entries_orphan_n, ())

# --- (c): RetryExecutor.execute()実チェーンでA/B/C write-ahead=0・外部I/O=0 ---
lineage_n2, manifest_n2, store_n2, draft_state_n2 = make_stack()
created_n2 = lineage_n2.create_new_lineage("run-n2", make_monitor_record("run-n2"))
claim_n2 = lineage_n2.claim("run-n2")
store_n2.save = lambda record: False
write_ahead_calls_n2: list = []
engine_n2 = HookAckAwareEngine(draft_state_n2, member_run_id="exec-run-n2", write_ahead_calls=write_ahead_calls_n2)
executor_n2 = RetryExecutor(
    workflow_engine_manager=engine_n2, lineage=lineage_n2,
    manifest=ManifestReaderFacade(manifest_n2), side_effect_classifier=None,
)
request_n2 = RetryRequest(run_id="run-n2", attempt=1, requested_at=datetime.now(), dry_run=False)
result_full_n2 = executor_n2.execute(request_n2, created_n2.lineage, claim_n2)
check("N4(c). RetryExecutor.execute()の結果はSKIPPED", result_full_n2.outcome, RetryOutcome.SKIPPED)
check("N5(c). engine.run()自体は1回呼ばれる（post_admission_hookまで到達）", engine_n2.calls, 1)
check("N6(c). 呼び出し箇所write-ahead相当（draft_state.create_attempted）の呼び出し回数=0", len(write_ahead_calls_n2), 0)

# --- (d) release_claim()のactual result/handling ---
# (d-通常ケース) reason文言と実際のdurable phaseの一致を確認する。
# この時点でexecute()は既にline244-245でrelease_claim()を呼んでいるはず。
check_true("N7(d). RetryResult.reasonは'claim released back to READY_ELIGIBLE'を含む（既存の無条件文言）",
           "released back to READY_ELIGIBLE" in (result_full_n2.reason or ""))
# store_n2.save()は依然としてFalseを返すfaultが有効なため、release_claim()内部の
# self._store.save(record)も失敗するはず——「無条件の文言」と「実際のdurable
# phase」が一致しないケースを直接構成する。
actual_phase_after_n2 = lineage_n2.peek("run-n2").phase
check(
    "N8(d). 【重要】無条件のreason文言とは裏腹に、実際のdurable phaseはCLAIMEDのまま"
    "（release_claim()自体もsave失敗で失敗しているため。既存6.31由来のdiagnostic gapを"
    "直接再現・証明する）",
    actual_phase_after_n2, RetryLineagePhase.CLAIMED,
)

# release_claim()自体の戻り値も直接確認する（execute()内部では未チェックだが、
# ここでは同条件でrelease_claim()を独立に呼び、実際にFalseになることを確認）。
result_release_n2_direct = lineage_n2.release_claim("run-n2", claim_n2.owner_token)
check_false("N9(d). release_claim()自体を直接呼んでも、save失敗によりFalseが返る（診断文言との乖離の原因を直接特定）", result_release_n2_direct)

# --- 安全性への影響がないことの直接確認：既存reconcile_all()のCLAIMED orphan回収へ委ねる ---
# faultを取り除き（instance override削除→本来のclass実装へ復帰）、既存の
# reconcile_all()経路で安全に回収されることを直接確認する。
del store_n2.save
summary_n2 = lineage_n2.reconcile_all(lambda run_id: None)
check_false("N10. fault除去後、reconcile_all()はskipped=Falseで正常動作する", summary_n2.skipped)
check("N11. 既存CLAIMED orphan回収により1件回収される（duplicate side-effect safetyを損なわず安全に収束）", summary_n2.released_count, 1)
check("N12. 回収後phase=READY_ELIGIBLE", lineage_n2.peek("run-n2").phase, RetryLineagePhase.READY_ELIGIBLE)

# --- (f) 後続recloseがold orphan manifestを再利用しないことの確認 ---
claim_n2c = lineage_n2.claim("run-n2")
check_true("N13(f). 回収後の再claim()は成功する", claim_n2c.acknowledged)
mark_ok_n2c = lineage_n2.mark_execution_started("run-n2", "exec-run-n2c", claim_n2c.owner_token)
check_true("N14(f). 新member_run_idでmark_execution_started()が成功する", mark_ok_n2c)
new_manifest_n2 = manifest_n2.list_for_attempt("run-n2", 1, "exec-run-n2c")
check("N15(f). 新manifestはentries=()で新規キーに作成される", new_manifest_n2, ())
old_manifest_n2_still_there = manifest_n2.list_for_attempt("run-n2", 1, "exec-run-n2")
check("N16(f). 旧orphan manifest（exec-run-n2）は削除・変更されず引き続き存在する（非再利用の直接証拠）",
      old_manifest_n2_still_there, ())
print()


# =====================================================================
# 後始末
# =====================================================================
for d in tmp_dirs:
    shutil.rmtree(d, ignore_errors=True)


# =====================================================================
# サマリー
# =====================================================================
print("=" * 70)
total = len(results_log)
passed = sum(1 for status, _ in results_log if status == "PASS")
failed = total - passed
print(f"合計: {total}件 / PASS: {passed}件 / FAIL: {failed}件")
if failed:
    print()
    print("FAILしたテスト:")
    for status, label in results_log:
        if status == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
print("すべてPASSしました。")
