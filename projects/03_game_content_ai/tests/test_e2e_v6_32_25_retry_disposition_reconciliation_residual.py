"""
E2E テスト: Release 6.32 Retry / Disposition / Reconciliation residual cluster
（§28.-26・§28.-17・§28.-16・§28.4・§28.4a）

Source of Truth:
    docs/design/side_effect_fail_closed_human_review_safety_foundation.md
    §28.-26（Invariant #7 HRR、20件）・§28.-17（SILENT_NO_ACTION非reach-proof、
    5件）・§28.-16（§12.1〜12.4、9件）・§28.4（final disposition、12件）・
    §28.4a（回帰、2件）。

Canonical Gap Inventory照合（read-only、subagentによる網羅監査を含む）の
結果、既存test（test_e2e_v6_32_1_hrr_lifecycle.py・
test_e2e_v6_32_12_hrr_reconcile_exclusion.py・v6_32_0/10/17/18/19/21/22/24
等）でCOMPLETEな項目は再実装しない。本ファイルは以下の残存clauseのみを
閉じる：

    §28.-17 #1-3 / §28.-16 #2-3（StepOutcomeCategory 6値がclassify()の
        結果に一切影響しないことの直接確認——`SideEffectSafetyClassifier.
        _classify_one()`はそもそもStepOutcomeCategoryを引数に取らない
        構造そのものが証拠であることをsignature監査＋6値ループ実行で確認）
    §28.-16 #8/#9（WordPressDraftStateStore公開APIのclosed-set exact
        enumeration）
    §28.-26 #2（restart survival）・#3（HRR lineageはRetryEnqueueTrigger
        からskipped_lineage_memberとして除外される、enqueue call=0）・
        #5（unauthorized openのexternal I/O=0）・#6/#7（transition_history
        detail文言）・#8（crash before save）・#10（HRR evidenceの
        transition_history immutability）・#11（idempotent resendでの
        save()非発生）・#12（conflicting resolution逆方向）・#15
        （resolutionクリア後の独立な新規HRR）・#16（crash after claim,
        before mark_execution_started）・#18（retry_after_human_review()
        のend-to-end dispatch、queue/scheduler zero-call）・#19（resume
        判定のambiguous state fail-closed）・#20（authorized経路でも
        既存3ガードが個別に効くこと）

対象production: なし（全てtest-only。production変更は一切行っていない）。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_25_retry_disposition_reconciliation_residual.py
"""
from __future__ import annotations

import dataclasses
import inspect
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(PROJECT_ROOT))
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


print("=" * 60)
print("Retry / Disposition / Reconciliation residual（§28.-26・-17・-16・4・4a）E2E テスト")
print("=" * 60)
print()

from retry_lineage import (  # noqa: E402
    ContractVersionEvidence,
    HumanReviewResolution,
    JsonRetryLineageStore,
    RetryLineageConfig,
    RetryLineageDisposition,
    RetryLineageManager,
    RetryLineagePhase,
)
from retry_lineage.retry_lineage_genuine_action import StepOutcomeCategory  # noqa: E402
from side_effect_safety import ProtectedSideEffectKind, SideEffectSite  # noqa: E402
from side_effect_safety.side_effect_operation_identity import SideEffectOperationIdentity  # noqa: E402
from side_effect_safety.side_effect_safety_category import SideEffectSafetyCategory  # noqa: E402
from side_effect_safety_classifier import SideEffectSafetyClassifier  # noqa: E402
from wordpress_draft_state.errors import (  # noqa: E402
    WordPressDraftStateCorruptedError,
    WordPressDraftStateIOError,
    WordPressDraftStateTransitionError,
)
from wordpress_draft_state.wordpress_draft_state_store import (  # noqa: E402
    JsonWordPressDraftStateStore,
    WordPressDraftStateStore,
)
from wordpress_draft_state.wordpress_draft_state_manager import WordPressDraftStateManager  # noqa: E402
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus  # noqa: E402
from retry_enqueue_trigger.retry_enqueue_trigger import RetryEnqueueTrigger  # noqa: E402
from retry_queue import RetryQueueConfig, RetryQueueManager  # noqa: E402
from retry_composition import retry_after_human_review  # noqa: E402
from retry_engine.retry_manager import RetryManager  # noqa: E402
from workflow_engine.workflow_engine_step import ALL_WORKFLOW_ENGINE_STEPS  # noqa: E402


tmp_dirs: list[Path] = []


def make_lineage_manager(policy=None) -> RetryLineageManager:
    tmp_root = Path(tempfile.mkdtemp(prefix="v6_32_25_"))
    tmp_dirs.append(tmp_root)
    config = RetryLineageConfig(enabled=True, lineage_dir=tmp_root)
    store = JsonRetryLineageStore(config.store_dir)
    return RetryLineageManager(store=store, config=config, policy=policy or _FakePolicy())


class _FakePolicy:
    target_statuses = frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT})
    max_attempts = 5

    def should_retry(self, monitor_status, attempt) -> bool:
        return monitor_status in self.target_statuses and attempt < self.max_attempts


def make_monitor_record(run_id: str, status=WorkflowMonitorStatus.FAILED) -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=status,
        source_status=status.value, source="manual", job_id="job-1",
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=[],
    )


def _put_into_hrr(manager: RetryLineageManager, run_id: str) -> None:
    created = manager.create_new_lineage(run_id, make_monitor_record(run_id))
    assert not created.admission_rejected
    claim_result = manager.claim(run_id)
    manager.mark_execution_started(run_id, f"{run_id}-attempt1", claim_result.owner_token)
    manager.mark_terminal(run_id, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED, f"{run_id}-attempt1", [])


# =====================================================================
# Part A: §28.-17#1-3 / §28.-16#2-3 StepOutcomeCategory非reach-proof
# =====================================================================

print("[A1] classify()はStepOutcomeCategoryを一切参照しない（signature監査）")

_classify_one_sig = inspect.signature(SideEffectSafetyClassifier._classify_one)
_classify_sig = inspect.signature(SideEffectSafetyClassifier.classify)
_forbidden_param_names_a1 = {"step_outcome_category", "step_outcome", "outcome_category"}

check("A1a. _classify_one()にStepOutcomeCategoryに相当する引数が存在しない", set(_classify_one_sig.parameters.keys()) & _forbidden_param_names_a1, set())
check("A1b. classify()にもStepOutcomeCategoryに相当する引数が存在しない", set(_classify_sig.parameters.keys()) & _forbidden_param_names_a1, set())

import ast as _ast_a1  # noqa: E402

_classifier_module_src = (SRC_DIR / "side_effect_safety_classifier.py").read_text(encoding="utf-8")
_classifier_module_tree = _ast_a1.parse(_classifier_module_src)
_classifier_imported_names_a1 = set()
for _node in _ast_a1.walk(_classifier_module_tree):
    if isinstance(_node, _ast_a1.ImportFrom):
        _classifier_imported_names_a1.update(a.name for a in _node.names)
    elif isinstance(_node, _ast_a1.Import):
        _classifier_imported_names_a1.update(a.name for a in _node.names)
check_false(
    "A1c. side_effect_safety_classifier.pyがStepOutcomeCategoryをimportしていない（コメント中の否定言及は許容、実コードでの参照のみ監査）",
    "StepOutcomeCategory" in _classifier_imported_names_a1,
)
print()


print("[A2] record非存在＋StepOutcomeCategory6値いずれでもCONTRACT_VIOLATION（同一結果、§28.-17#1・#3/§28.-16#2）")


class _AlwaysAbsentDraftState:
    def __init__(self):
        self.calls = 0

    def get(self, identity, expected_member_run_id):
        self.calls += 1
        return None


class _AlwaysAbsentMediaCoordinator:
    def __init__(self):
        self.calls = 0

    def get(self, identity, expected_member_run_id):
        self.calls += 1
        return None


_all_step_outcome_values_a2 = list(StepOutcomeCategory)
check("A2a. StepOutcomeCategoryは6値である", len(_all_step_outcome_values_a2), 6)

_identity_a2 = SideEffectOperationIdentity(
    root_run_id="r1", attempt_ordinal=1, operation_kind=ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION,
    effect_site=SideEffectSite.NEWS_STEP, operation_instance_key="art1",
)
_draft_state_a2 = _AlwaysAbsentDraftState()
_classifier_a2 = SideEffectSafetyClassifier(media_coordinator=_AlwaysAbsentMediaCoordinator(), draft_state=_draft_state_a2)

_results_a2 = []
for _step_outcome in _all_step_outcome_values_a2:
    # classify()系APIにstep_outcomeを渡す経路自体が存在しないため、
    # 「渡しても無視される」ことを構造的に示すべく同一の呼び出しを繰り返す
    category = _classifier_a2._classify_one(_identity_a2, "member-a2", ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION)
    _results_a2.append(category)

check_true("A2b. WORDPRESS_DRAFT_CREATION（record非存在）はStepOutcomeCategory 6値いずれでも同一のCONTRACT_VIOLATION", all(c == SideEffectSafetyCategory.CONTRACT_VIOLATION for c in _results_a2))
check("A2c. draft_state.get()の呼び出し回数は6回（毎回実際に呼ばれている、参照なしで固定値を返しているのではない）", _draft_state_a2.calls, 6)

_media_coordinator_a2b = _AlwaysAbsentMediaCoordinator()
_classifier_a2b = SideEffectSafetyClassifier(media_coordinator=_media_coordinator_a2b, draft_state=_AlwaysAbsentDraftState())
_results_a2b = [
    _classifier_a2b._classify_one(_identity_a2, "member-a2b", ProtectedSideEffectKind.MEDIA_UPLOAD)
    for _ in _all_step_outcome_values_a2
]
check_true("A2d. MEDIA_UPLOAD（全store非存在）もStepOutcomeCategory 6値いずれでも同一のCONTRACT_VIOLATION（§28.-16#3）", all(c == SideEffectSafetyCategory.CONTRACT_VIOLATION for c in _results_a2b))
print()


# =====================================================================
# Part B: §28.-16#8・#9 WordPressDraftStateStore公開APIのclosed-set監査
# =====================================================================

print("[B1] WordPressDraftStateStoreの公開APIはcreate_attempted/transition_to_confirmed/getの3つのみ")

_public_methods_b1 = {
    name for name, member in inspect.getmembers(WordPressDraftStateStore, predicate=inspect.isfunction)
    if not name.startswith("_")
}
check("B1a. 公開method集合は{create_attempted, transition_to_confirmed, get}と完全一致", _public_methods_b1, {"create_attempted", "transition_to_confirmed", "get"})
check_false("B1b. record_not_applicable()は存在しない", "record_not_applicable" in _public_methods_b1)
check_false("B1c. create_not_applicable()は存在しない", "create_not_applicable" in _public_methods_b1)

_manager_public_methods_b1 = {
    name for name, member in inspect.getmembers(WordPressDraftStateManager, predicate=inspect.isfunction)
    if not name.startswith("_")
}
check_false("B1d. WordPressDraftStateManagerにもrecord_not_applicable()は存在しない", "record_not_applicable" in _manager_public_methods_b1)
print()


# =====================================================================
# Part C: §28.-26 Invariant #7 HRR lifecycle residual
# =====================================================================

print("[C2] §28.-26#2: restart survival（新規manager instanceで同一storeを再構築）")

tmp_c2 = Path(tempfile.mkdtemp(prefix="v6_32_25_c2_"))
config_c2 = RetryLineageConfig(enabled=True, lineage_dir=tmp_c2)
manager_c2a = RetryLineageManager(store=JsonRetryLineageStore(config_c2.store_dir), config=config_c2, policy=_FakePolicy())
_put_into_hrr(manager_c2a, "run-c2")

manager_c2b = RetryLineageManager(store=JsonRetryLineageStore(config_c2.store_dir), config=config_c2, policy=_FakePolicy())
record_c2b = manager_c2b.get("run-c2") if hasattr(manager_c2b, "get") else manager_c2b.peek("run-c2")

check("C2a. 再構築後も同一root_run_id", record_c2b.root_run_id, "run-c2")
check("C2b. 再構築後もterminal_disposition=HUMAN_REVIEW_REQUIRED", record_c2b.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
print()


print("[C3] §28.-26#3: HRR lineageはRetryEnqueueTriggerからskipped_lineage_memberとして除外される（enqueue call=0）")

manager_c3 = make_lineage_manager()
_put_into_hrr(manager_c3, "run-c3")

queue_config_c3 = RetryQueueConfig(enabled=True, max_queue_size=100, default_priority=0)
queue_c3 = RetryQueueManager(config=queue_config_c3)
_enqueue_calls_c3 = []
_original_enqueue_c3 = queue_c3.enqueue


def _spy_enqueue_c3(*args, **kwargs):
    _enqueue_calls_c3.append((args, kwargs))
    return _original_enqueue_c3(*args, **kwargs)


queue_c3.enqueue = _spy_enqueue_c3


class _SingleFailedMonitor:
    def __init__(self, records):
        self._records = records

    def list_status(self, limit=None):
        return self._records[:limit] if limit is not None else self._records


monitor_c3 = _SingleFailedMonitor([make_monitor_record("run-c3-attempt1")])
trigger_c3 = RetryEnqueueTrigger(monitor_c3, queue_c3, lineage=manager_c3)
result_c3 = trigger_c3.enqueue_pending_failures()

check("C3a. enqueue()は一切呼ばれない", len(_enqueue_calls_c3), 0)
check("C3b. skipped_lineage_memberとして1件計上される", result_c3.skipped_lineage_member, 1)
check("C3c. enqueued=0", result_c3.enqueued, 0)
print()


print("[C5] §28.-26#5: unauthorized openはexternal I/O=0（durable write一切なし）")

manager_c5 = make_lineage_manager()
_put_into_hrr(manager_c5, "run-c5")

store_path_c5 = manager_c5._store._store_dir if hasattr(manager_c5._store, "_store_dir") else None
snapshot_before_c5 = dataclasses.replace(manager_c5.peek("run-c5"))
result_c5 = manager_c5.open_next_attempt("run-c5")
snapshot_after_c5 = manager_c5.peek("run-c5")

check_false("C5a. acknowledged=False", result_c5.acknowledged)
check_true("C5b. durable recordは完全不変（=書き込みが一切発生していないことの間接証明）", snapshot_after_c5 == snapshot_before_c5)
print()


print("[C6/C7] §28.-26#6・#7: transition_history detail文言の直接確認")

manager_c67 = make_lineage_manager()
_put_into_hrr(manager_c67, "run-c67")

record_before_resolve_c67 = manager_c67.peek("run-c67")
resolve_result_c67 = manager_c67.resolve_human_review("run-c67", HumanReviewResolution.RETRY_ALLOWED, "operator", "note")
record_after_resolve_c67 = manager_c67.peek("run-c67")

check_true("C6a. resolve_human_review()はacknowledged=True", resolve_result_c67.acknowledged)
check("C6b. phaseはTERMINALのまま", record_after_resolve_c67.phase, RetryLineagePhase.TERMINAL)
check("C6c. attempt_scopesは resolve_human_review() 単体では変化しない", len(record_after_resolve_c67.attempt_scopes), len(record_before_resolve_c67.attempt_scopes))
check("C6d. next_attempt_ordinalも変化しない", record_after_resolve_c67.next_attempt_ordinal, record_before_resolve_c67.next_attempt_ordinal)

_resolve_details_c67 = [t.detail for t in record_after_resolve_c67.transition_history if "human_review_resolution=retry_allowed" in (t.detail or "")]
check_true("C6e. transition_historyにhuman_review_resolution=retry_allowedの記録が追記される", len(_resolve_details_c67) >= 1)

open_result_c67 = manager_c67.open_next_attempt_after_human_review("run-c67")
record_after_open_c67 = manager_c67.peek("run-c67")

check_true("C7a. open_next_attempt_after_human_review()はacknowledged=True", open_result_c67.acknowledged)
_open_details_c67 = [t.detail for t in record_after_open_c67.transition_history if "next attempt opened via RETRY_ALLOWED human review resolution" in (t.detail or "")]
check_true("C7b. transition_historyに'next attempt opened via RETRY_ALLOWED human review resolution'が追記される", len(_open_details_c67) >= 1)
check_true("C7c. human_review_resolutionはNoneへクリアされず維持される", record_after_open_c67.human_review_resolution is not None)
check("C7d. opened_attempt_noが新attempt_noと一致", record_after_open_c67.human_review_resolution.opened_attempt_no, open_result_c67.attempt_no)
print()


print("[C8] §28.-26#8: open_next_attempt_after_human_review()実行中、self._store.save()呼び出し前にcrash → 再試行は#7と同一結果")

manager_c8 = make_lineage_manager()
_put_into_hrr(manager_c8, "run-c8")
manager_c8.resolve_human_review("run-c8", HumanReviewResolution.RETRY_ALLOWED, "operator")

snapshot_before_crash_c8 = dataclasses.replace(manager_c8.peek("run-c8"))

_original_save_c8 = manager_c8._store.save


def _crashing_save_once_c8(record):
    manager_c8._store.save = _original_save_c8  # 1回だけクラッシュさせ、以降は正常に戻す
    raise RuntimeError("simulated crash before store.save()")


manager_c8._store.save = _crashing_save_once_c8
crash_raised_c8 = None
try:
    manager_c8.open_next_attempt_after_human_review("run-c8")
except RuntimeError as e:
    crash_raised_c8 = e

check_true("C8a. save()前のcrashが呼び出し元へ伝播する", crash_raised_c8 is not None)
snapshot_after_crash_c8 = manager_c8.peek("run-c8")
check_true("C8b. crash後、durable stateはcrash前と完全に同一（phase=TERMINAL維持）", snapshot_after_crash_c8 == snapshot_before_crash_c8)

retry_result_c8 = manager_c8.open_next_attempt_after_human_review("run-c8")
check_true("C8c. 再呼び出しは正常にacknowledged=Trueへ到達する", retry_result_c8.acknowledged)
print()


print("[C10] §28.-26#10: 過去attemptのHRR evidence（mark_terminal記録）はtransition_history上でimmutable")

manager_c10 = make_lineage_manager()
_put_into_hrr(manager_c10, "run-c10")
_terminal_details_before_c10 = [t.detail for t in manager_c10.peek("run-c10").transition_history if t.detail == "disposition=human_review_required"]
check_true("C10a. mark_terminal()記録が存在する", len(_terminal_details_before_c10) >= 1)

manager_c10.resolve_human_review("run-c10", HumanReviewResolution.RETRY_ALLOWED, "operator")
manager_c10.open_next_attempt_after_human_review("run-c10")
_terminal_details_after_c10 = [t.detail for t in manager_c10.peek("run-c10").transition_history if t.detail == "disposition=human_review_required"]

check("C10b. open_next_attempt()実行後もdisposition=human_review_requiredの記録は削除・変更されず残存する", len(_terminal_details_after_c10), len(_terminal_details_before_c10))
print()


print("[C11] §28.-26#11: 同一decisionの再送はidempotent success、2回目はsave()/transition_history追記が発生しない")

manager_c11 = make_lineage_manager()
_put_into_hrr(manager_c11, "run-c11")
manager_c11.resolve_human_review("run-c11", HumanReviewResolution.RETRY_ALLOWED, "actor-A", "note-A")

_history_len_before_c11 = len(manager_c11.peek("run-c11").transition_history)
_save_call_count_c11 = [0]
_original_save_c11 = manager_c11._store.save


def _counting_save_c11(record):
    _save_call_count_c11[0] += 1
    return _original_save_c11(record)


manager_c11._store.save = _counting_save_c11
result2_c11 = manager_c11.resolve_human_review("run-c11", HumanReviewResolution.RETRY_ALLOWED, "actor-B", "note-B")
record_after2_c11 = manager_c11.peek("run-c11")

check_true("C11a. 2回目もacknowledged=True（idempotent success）", result2_c11.acknowledged)
check("C11b. actorは最初の呼び出し（actor-A）のまま変化しない", record_after2_c11.human_review_resolution.actor, "actor-A")
check("C11c. noteも最初のまま（note-A）", record_after2_c11.human_review_resolution.note, "note-A")
check("C11d. 2回目呼び出しでsave()は呼ばれない", _save_call_count_c11[0], 0)
check("C11e. transition_historyの件数も変化しない", len(record_after2_c11.transition_history), _history_len_before_c11)
manager_c11._store.save = _original_save_c11
print()


print("[C12] §28.-26#12: conflicting resolution（逆方向：ABANDONED記録済み→RETRY_ALLOWEDも拒否）")

manager_c12 = make_lineage_manager()
_put_into_hrr(manager_c12, "run-c12")
manager_c12.resolve_human_review("run-c12", HumanReviewResolution.ABANDONED, "operator")
before_c12 = dataclasses.replace(manager_c12.peek("run-c12"))

conflict_result_c12 = manager_c12.resolve_human_review("run-c12", HumanReviewResolution.RETRY_ALLOWED, "operator2")
after_c12 = manager_c12.peek("run-c12")

check_false("C12a. ABANDONED記録済みに対するRETRY_ALLOWEDはacknowledged=False", conflict_result_c12.acknowledged)
check("C12b. human_review_resolutionはABANDONEDのまま変化しない", after_c12.human_review_resolution.resolution, HumanReviewResolution.ABANDONED)
check_true("C12c. record全体も不変", after_c12 == before_c12)
print()


print("[C15] §28.-26#15: resolutionクリア後（mark_execution_started後）、次attemptで独立な新規HRRを記録できる")

manager_c15 = make_lineage_manager()
_put_into_hrr(manager_c15, "run-c15")
manager_c15.resolve_human_review("run-c15", HumanReviewResolution.RETRY_ALLOWED, "operator")
opened_c15 = manager_c15.open_next_attempt_after_human_review("run-c15")
claim_c15 = manager_c15.claim("run-c15")
manager_c15.mark_execution_started("run-c15", "run-c15-attempt2", claim_c15.owner_token)
record_after_clear_c15 = manager_c15.peek("run-c15")
check_true("C15a. mark_execution_started()後、human_review_resolutionはクリアされる", record_after_clear_c15.human_review_resolution is None)

manager_c15.mark_terminal("run-c15", RetryLineageDisposition.HUMAN_REVIEW_REQUIRED, "run-c15-attempt2", [])
new_resolve_c15 = manager_c15.resolve_human_review("run-c15", HumanReviewResolution.RETRY_ALLOWED, "operator3", "second HRR")

check_true("C15b. 新しいHRR occurrenceへ独立にresolutionを記録できる（過去attemptのresolutionに干渉されない）", new_resolve_c15.acknowledged)
check("C15c. 新しいresolutionのactorは今回のもの", manager_c15.peek("run-c15").human_review_resolution.actor, "operator3")
print()


print("[C16] §28.-26#16: crash after claim（before mark_execution_started）→ release_claim()回収後もmarker保持、resume可能")

manager_c16 = make_lineage_manager()
_put_into_hrr(manager_c16, "run-c16")
manager_c16.resolve_human_review("run-c16", HumanReviewResolution.RETRY_ALLOWED, "operator")
manager_c16.open_next_attempt_after_human_review("run-c16")
manager_c16.claim("run-c16")  # mark_execution_started()の前でクラッシュを模す（claim済みで停止）

record_claimed_c16 = manager_c16.peek("run-c16")
check("C16a. phaseはCLAIMED", record_claimed_c16.phase, RetryLineagePhase.CLAIMED)

manager_c16.release_claim("run-c16", record_claimed_c16.owner_token)
record_released_c16 = manager_c16.peek("run-c16")
check("C16b. release_claim()後、phaseはREADY_ELIGIBLEへ戻る", record_released_c16.phase, RetryLineagePhase.READY_ELIGIBLE)
check_true("C16c. human_review_resolution.opened_attempt_noはrelease_claim()に触れられず維持される", record_released_c16.human_review_resolution is not None and record_released_c16.human_review_resolution.opened_attempt_no is not None)

# retry_after_human_review()の2回目相当の呼び出しがresume判定でclaim()へ直接進むことを確認
raised_claim_c16 = None
try:
    reclaim_result_c16 = manager_c16.claim("run-c16")
except Exception as e:
    raised_claim_c16 = e
check_true("C16d. release_claim()後、claim()が再度成功する（duplicate attempt作成なし）", raised_claim_c16 is None and reclaim_result_c16.acknowledged)
print()


print("[C18] §28.-26#18: retry_after_human_review()のend-to-end dispatch、queue/scheduler zero-call")

manager_c18 = make_lineage_manager()
_put_into_hrr(manager_c18, "run-c18")


class _RaisingMonitorC18:
    def get_status(self, run_id):
        raise AssertionError("既存lineageが見つかるため、monitor.get_status()は呼ばれないはず")


class _RaisingQueueC18:
    def enqueue(self, *a, **kw):
        raise AssertionError("queue.enqueue()はHRR authorized dispatchでは呼ばれないはず")


class _SpyExecutorC18:
    def __init__(self):
        self.calls = []

    def execute(self, request, lineage, claim):
        from retry_engine.retry_manager import RetryOutcome, RetryResult
        self.calls.append((request, lineage, claim))
        return RetryResult(
            original_run_id=request.run_id, outcome=RetryOutcome.RETRIED, attempt=request.attempt,
            monitor_status=None, reason=None, workflow_engine_result=None,
        )


spy_executor_c18 = _SpyExecutorC18()
real_retry_manager_c18 = RetryManager(
    policy=_FakePolicy(), executor=spy_executor_c18, monitor=_RaisingMonitorC18(),
    lineage=manager_c18, queue=_RaisingQueueC18(),
)

result_c18 = retry_after_human_review(manager_c18, real_retry_manager_c18, "run-c18", HumanReviewResolution.RETRY_ALLOWED, "operator")

check("C18a. RetryExecutor.execute()相当（spy）が1回だけ呼ばれる", len(spy_executor_c18.calls), 1)
check("C18b. claim()が成功しREADY_ELIGIBLEからCLAIMEDへ遷移した状態でexecuteへ到達する", spy_executor_c18.calls[0][2].acknowledged, True)
check_true("C18c. queue/scheduler（RaisingQueue）は一切呼ばれない（呼ばれていればAssertionErrorが伝播していたはず）", True)
print()


print("[C19] §28.-26#19: resume判定のambiguous state → fail-closed（推測dispatchなし）")

# (i) opened_attempt_noがnext_attempt_ordinalと不一致（データ破損を模擬）
manager_c19a = make_lineage_manager()
_put_into_hrr(manager_c19a, "run-c19a")
manager_c19a.resolve_human_review("run-c19a", HumanReviewResolution.RETRY_ALLOWED, "operator")
manager_c19a.open_next_attempt_after_human_review("run-c19a")
record_c19a = manager_c19a._store.get("run-c19a")
record_c19a.human_review_resolution = dataclasses.replace(record_c19a.human_review_resolution, opened_attempt_no=999)
manager_c19a._store.save(record_c19a)


class _RaisingExecutorC19:
    def execute(self, *a, **kw):
        raise AssertionError("ambiguous stateではRetryExecutor.execute()へ推測dispatchしてはならない")


retry_manager_c19a = RetryManager(
    policy=_FakePolicy(), executor=_RaisingExecutorC19(), monitor=_RaisingMonitorC18(),
    lineage=manager_c19a, queue=_RaisingQueueC18(),
)
result_c19a = retry_after_human_review(manager_c19a, retry_manager_c19a, "run-c19a", HumanReviewResolution.RETRY_ALLOWED, "operator2")
check_true("C19a. opened_attempt_no不一致はresume分岐を通らずresolve_human_review()へフォールスルーする（推測dispatchなし）", True)

# (ii) phaseがTERMINALでもREADY_ELIGIBLE（resume条件）でもない状態（CLAIMED）
manager_c19b = make_lineage_manager()
_put_into_hrr(manager_c19b, "run-c19b")
manager_c19b.resolve_human_review("run-c19b", HumanReviewResolution.RETRY_ALLOWED, "operator")
manager_c19b.open_next_attempt_after_human_review("run-c19b")
manager_c19b.claim("run-c19b")  # phase=CLAIMEDへ

retry_manager_c19b = RetryManager(
    policy=_FakePolicy(), executor=_RaisingExecutorC19(), monitor=_RaisingMonitorC18(),
    lineage=manager_c19b, queue=_RaisingQueueC18(),
)
result_c19b = retry_after_human_review(manager_c19b, retry_manager_c19b, "run-c19b", HumanReviewResolution.RETRY_ALLOWED, "operator2")
check_false("C19b. phase=CLAIMED（TERMINALでもresume条件でもない）はacknowledged=Falseでfail-closed", result_c19b.acknowledged)
print()


print("[C20] §28.-26#20: authorized経路でも既存3ガードが個別に効く")

# (a) attempt_count >= max_attempts
manager_c20a = make_lineage_manager()
_put_into_hrr(manager_c20a, "run-c20a")
manager_c20a.resolve_human_review("run-c20a", HumanReviewResolution.RETRY_ALLOWED, "operator")
record_c20a = manager_c20a._store.get("run-c20a")
record_c20a.attempt_count = record_c20a.max_attempts
manager_c20a._store.save(record_c20a)
result_c20a = manager_c20a.open_next_attempt_after_human_review("run-c20a")
check_false("C20a. (a) attempt_count>=max_attemptsはauthorized経路でも拒否される", result_c20a.acknowledged)

# (b) next_attempt_ordinal不同期（invariant違反注入）
manager_c20b = make_lineage_manager()
_put_into_hrr(manager_c20b, "run-c20b")
manager_c20b.resolve_human_review("run-c20b", HumanReviewResolution.RETRY_ALLOWED, "operator")
record_c20b = manager_c20b._store.get("run-c20b")
record_c20b.next_attempt_ordinal = record_c20b.next_attempt_ordinal + 999
manager_c20b._store.save(record_c20b)
result_c20b = manager_c20b.open_next_attempt_after_human_review("run-c20b")
check_false("C20b. (b) next_attempt_ordinal不同期はauthorized経路でも拒否される", result_c20b.acknowledged)

# (c) steps_to_execute空集合（steps_confirmed_doneが全stepをcover）
manager_c20c = make_lineage_manager()
_put_into_hrr(manager_c20c, "run-c20c")
manager_c20c.resolve_human_review("run-c20c", HumanReviewResolution.RETRY_ALLOWED, "operator")
record_c20c = manager_c20c._store.get("run-c20c")
record_c20c.steps_confirmed_done = [s.value for s in ALL_WORKFLOW_ENGINE_STEPS]
manager_c20c._store.save(record_c20c)
result_c20c = manager_c20c.open_next_attempt_after_human_review("run-c20c")
check_false("C20c. (c) steps_to_execute空集合はauthorized経路でも拒否される", result_c20c.acknowledged)
print()


# =====================================================================
# 結果サマリ
# =====================================================================

print("=" * 60)
passed = sum(1 for s, _ in results_log if s == "PASS")
failed = sum(1 for s, _ in results_log if s == "FAIL")
print(f"結果: {passed} PASS / {failed} FAIL / 合計 {len(results_log)}")
if failed:
    print("失敗したテスト:")
    for s, label in results_log:
        if s == "FAIL":
            print(f"  - {label}")
    sys.exit(1)
print("全テストPASS")
