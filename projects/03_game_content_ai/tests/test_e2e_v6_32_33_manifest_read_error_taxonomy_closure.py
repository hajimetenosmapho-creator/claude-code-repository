"""
E2E テスト: Release 6.32 — Manifest Read Error Taxonomy Closure（§18 test#14）

Source of Truth: docs/design/
side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md
§9.1（Missing/Corrupt Manifest Classification）・§10（sync）・§11（restart）・
§18 test#14（Manifest read時のIOError、3種の例外subtype個別×同期路・crash路の
2経路＝6ケースを個別網羅する）

対象subtype（`ProtectedOperationManifestReadError`の3具象subclass）：
    - ProtectedOperationManifestNotFoundError（レコード非存在）
    - ProtectedOperationManifestContractViolationError（schema/identity破損）
    - ProtectedOperationManifestIOError（真のfilesystem I/O failure）

対象path：
    A. sync（RetryExecutor.execute()実チェーン）
    B. restart（RetryLineageManager.reconcile_all()→_reconcile_all_locked()実チェーン）

既存証拠との関係（重複回避）：
    - ContractViolationError × sync/restartは
      test_e2e_v6_32_32（グループC・D）で production wiring 込みで既に直接
      証明済みのため、本ファイルでは再証明しない（本ファイルはNotFoundError・
      IOErrorの4ケースのみを追加する）。
    - subtypeの型そのものの区別（store単体でNotFoundError/ContractViolation
      Error/IOErrorが正しく送出されること）はtest_e2e_v6_32_29（C3〜C6）で
      証明済みのため再利用し、本ファイルはそれをproduction wiring
      （RetryExecutor.execute() / _reconcile_all_locked()）経由で実際に駆動した
      場合の帰結のみを追加で証明する（人工stateだけでのproduction closure
      主張はしない）。

各ケースで直接確認する項目：
    - exact current manifest identityが選択されている（sync=engine_result.run_id、
      restart=record.latest_run_id）
    - read error subtypeが実際に発生している（正しいsubtypeで再現できていることの
      確認）
    - classifierへ不正入力が渡らない（classify()呼び出し回数=0）
    - fail-closed HUMAN_REVIEW_REQUIRED
    - mark_terminal()へHRRが渡る（durable terminal_dispositionで確認）
    - automatic retryが開かない（reconcile_all()のopened_count=0）
    - NotFoundケースではold orphan / unrelated manifestへfallbackしない
      （別member_run_idの既存manifestが誤って読まれない）
    - IOErrorケースはtrue filesystem I/O failure（実際のPath.read_text()の
      OSError）を用い、schema corruption（不正なJSONテキスト）とは手段を
      混同しない

production code（RetryExecutor・RetryLineageManager・
ProtectedOperationManifestStore等）は一切変更しない。
network / WordPress / 外部I/O = 0。

実行方法:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe tests/test_e2e_v6_32_33_manifest_read_error_taxonomy_closure.py
"""
from __future__ import annotations

import pathlib
import shutil
import sys
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

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
print("Manifest Read Error Taxonomy Closure（§18 test#14） — E2E テスト")
print("=" * 70)
print()

from protected_operation_manifest import (
    JsonProtectedOperationManifestStore,
    ManifestReaderFacade,
    ProtectedOperationManifestNotFoundError,
    build_manifest_entry,
)
from retry_engine import RetryExecutor, RetryRequest
from retry_lineage import (
    JsonRetryLineageStore,
    RetryLineageConfig,
    RetryLineageDisposition,
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
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus

tmp_dirs: list[Path] = []


class FakePolicy:
    def __init__(self, max_attempts: int = 3):
        self.target_statuses = frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT})
        self._max_attempts = max_attempts

    @property
    def max_attempts(self) -> int:
        return self._max_attempts

    def should_retry(self, monitor_status, attempt: int) -> bool:
        return monitor_status in self.target_statuses and attempt < self._max_attempts


class SpyClassifier:
    def __init__(self, real: SideEffectSafetyClassifier):
        self._real = real
        self.calls: list[tuple] = []

    def classify(self, root_run_id, attempt_ordinal, member_run_id, operations):
        report = self._real.classify(root_run_id, attempt_ordinal, member_run_id, operations)
        self.calls.append((root_run_id, attempt_ordinal, member_run_id, tuple(operations), report))
        return report


@dataclass
class FakeAgentResult:
    success: bool
    action_taken: bool | None = None

    def to_dict(self):
        return {"success": self.success, "action_taken": self.action_taken}


def make_step_result(step, executed, success, action_taken=None):
    ar = FakeAgentResult(success=success, action_taken=action_taken) if executed else None
    return WorkflowEngineStepResult(
        step=step, executed=executed, agent_result=ar, success=success,
        skipped_reason=None if executed else "skipped",
    )


def make_monitor_record(run_id: str, monitor_status=WorkflowMonitorStatus.FAILED, steps=None) -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=monitor_status,
        source_status=monitor_status.value, source="manual", job_id="job-1",
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=steps or [],
    )


def make_stack():
    tmp_root = Path(tempfile.mkdtemp(prefix="v6_32_33_"))
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
    real_classifier = SideEffectSafetyClassifier(media_coordinator=media_upload_coordinator, draft_state=draft_state_store)
    spy_classifier = SpyClassifier(real_classifier)

    lineage = RetryLineageManager(
        store=lineage_store, config=lineage_config, policy=FakePolicy(),
        manifest=manifest_store, side_effect_classifier=spy_classifier,
    )
    return lineage, manifest_store, draft_state_store, spy_classifier


def seed_orphan_manifest(manifest_store, root_run_id: str, orphan_member_run_id: str) -> None:
    """old orphan / unrelated manifestへのfallback非発生を確認するための、
    無関係なmember_run_idでの既存manifest。"""
    manifest_store.create_for_attempt(root_run_id, 1, orphan_member_run_id)
    manifest_store.register(
        root_run_id, 1, orphan_member_run_id,
        build_manifest_entry(ProtectedSideEffectKind.WORDPRESS_DRAFT_CREATION, SideEffectSite.NEWS_STEP, "orphan-slug"),
    )


# =====================================================================
# グループE：sync NotFoundError（現attemptのmanifestファイルが消失）
# =====================================================================
print("[グループE] sync NotFoundError（admission後にmanifestファイルが消失）")

lineage_e, manifest_e, draft_state_e, classifier_e = make_stack()
created_e = lineage_e.create_new_lineage("run-e", make_monitor_record("run-e"))
claim_e = lineage_e.claim("run-e")
check_true("E前提: claim()成功", claim_e.acknowledged)
seed_orphan_manifest(manifest_e, "run-e", "exec-orphan-e")


class NotFoundEngine:
    """呼び出し箇所Aを模す：admissionで正しい空manifestが作成された直後、
    manifestファイル自体を削除する（外部要因によるmanifest state消失、
    真のNotFoundError再現）。"""

    def __init__(self, manifest_store, member_run_id: str):
        self._manifest = manifest_store
        self._member_run_id = member_run_id
        self.calls = 0

    def run(self, event, dry_run=False, target_step_filter=None, post_admission_hook=None,
            correlation_metadata=None, side_effect_execution_provenance=None):
        self.calls += 1
        run_id = self._member_run_id
        root_run_id = event.job_id
        if post_admission_hook is not None:
            post_admission_hook(run_id)  # create_for_attempt()で正しい空manifestが作られる

        path = self._manifest._path_for(root_run_id, 1, run_id)
        check_true("E前提: 削除前はmanifestファイルが実在する", path.exists())
        path.unlink()

        steps = [make_step_result(s, executed=True, success=True, action_taken=True) for s in ALL_WORKFLOW_ENGINE_STEPS]
        return WorkflowEngineResult(
            run_id=run_id, steps=steps, overall_success=True, stopped_early=False,
            started_at=datetime.now(), finished_at=datetime.now(),
        )


engine_e = NotFoundEngine(manifest_e, member_run_id="exec-run-e")
executor_e = RetryExecutor(
    workflow_engine_manager=engine_e, lineage=lineage_e,
    manifest=ManifestReaderFacade(manifest_e), side_effect_classifier=classifier_e,
)
request_e = RetryRequest(run_id="run-e", attempt=1, requested_at=datetime.now(), dry_run=False)
executor_e.execute(request_e, created_e.lineage, claim_e)
record_e = lineage_e.peek("run-e")

raised_e = None
try:
    manifest_e.list_for_attempt("run-e", 1, "exec-run-e")
except ProtectedOperationManifestNotFoundError:
    raised_e = "NotFoundError"
check("E1. current manifest identity（exec-run-e）は実際に非存在（NotFoundError）", raised_e, "NotFoundError")
check("E2. classifierは一度も呼ばれない", len(classifier_e.calls), 0)
check("E3. final disposition=HUMAN_REVIEW_REQUIRED", record_e.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("E4. mark_terminal()へ渡されたdispositionもHRR（durable記録で確認）", record_e.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("E5. phaseはTERMINAL", record_e.phase, RetryLineagePhase.TERMINAL)

entries_orphan_e = manifest_e.list_for_attempt("run-e", 1, "exec-orphan-e")
check_true("E6. old orphan（exec-orphan-e）は無傷のまま存在する（fallback読み出しされていない証拠）",
           len(entries_orphan_e) == 1 and entries_orphan_e[0].operation_instance_key == "orphan-slug")

summary_e = lineage_e.reconcile_all(lambda run_id: None)
check("E7. next automatic retryが開かない（opened_count=0）", summary_e.opened_count, 0)
print()


# =====================================================================
# グループF：restart NotFoundError
# =====================================================================
print("[グループF] restart NotFoundError（admission後にmanifestファイルが消失）")

lineage_f, manifest_f, draft_state_f, classifier_f = make_stack()
created_f = lineage_f.create_new_lineage("run-f", make_monitor_record("run-f"))
claim_f = lineage_f.claim("run-f")
seed_orphan_manifest(manifest_f, "run-f", "exec-orphan-f")
mark_ok_f = lineage_f.mark_execution_started("run-f", "exec-run-f", claim_f.owner_token)
check_true("F前提: mark_execution_started()成功（空manifest作成済み）", mark_ok_f)

path_f = manifest_f._path_for("run-f", 1, "exec-run-f")
check_true("F前提: 削除前はmanifestファイルが実在する", path_f.exists())
path_f.unlink()

monitor_f = make_monitor_record(
    "run-f",
    steps=[make_step_result(s, executed=True, success=True, action_taken=True) for s in ALL_WORKFLOW_ENGINE_STEPS],
)


def _to_execution_history_steps(monitor_record):
    from execution_history import StepExecutionRecord, StepExecutionStatus
    return [
        StepExecutionRecord(step=s.step.value, status=StepExecutionStatus.SUCCESS, action_taken=True)
        for s in monitor_record.steps
    ]


monitor_f_for_restart = make_monitor_record("run-f", steps=_to_execution_history_steps(monitor_f))
summary_f = lineage_f.reconcile_all(lambda run_id: monitor_f_for_restart if run_id == "exec-run-f" else None)
record_f = lineage_f.peek("run-f")

raised_f = None
try:
    manifest_f.list_for_attempt("run-f", 1, "exec-run-f")
except ProtectedOperationManifestNotFoundError:
    raised_f = "NotFoundError"
check("F1. current manifest identity（record.latest_run_id=exec-run-f）は実際に非存在", raised_f, "NotFoundError")
check("F2. classifierは一度も呼ばれない", len(classifier_f.calls), 0)
check("F3. final disposition=HUMAN_REVIEW_REQUIRED", record_f.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("F4. mark_terminal()へ渡されたdispositionもHRR（durable記録で確認）", record_f.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("F5. next automatic retryが開かない（同一reconcile_all()呼び出し内でopened_count=0）", summary_f.opened_count, 0)
check("F6. phaseはTERMINAL", record_f.phase, RetryLineagePhase.TERMINAL)

entries_orphan_f = manifest_f.list_for_attempt("run-f", 1, "exec-orphan-f")
check_true("F7. old orphan（exec-orphan-f）は無傷のまま存在する（fallback読み出しされていない証拠）",
           len(entries_orphan_f) == 1 and entries_orphan_f[0].operation_instance_key == "orphan-slug")
print()


# =====================================================================
# グループG：sync IOError（真のfilesystem I/O failure、schema corruptionと区別）
# =====================================================================
print("[グループG] sync IOError（真のfilesystem I/O failure）")

lineage_g, manifest_g, draft_state_g, classifier_g = make_stack()
created_g = lineage_g.create_new_lineage("run-g", make_monitor_record("run-g"))
claim_g = lineage_g.claim("run-g")
check_true("G前提: claim()成功", claim_g.acknowledged)

_real_read_text = pathlib.Path.read_text


def _make_selective_io_failure(target_path: Path):
    def _selective_read_text(self, *args, **kwargs):
        if self == target_path:
            raise OSError("simulated true filesystem I/O failure (not a schema/content corruption)")
        return _real_read_text(self, *args, **kwargs)
    return _selective_read_text


class IOFailureEngine:
    """呼び出し箇所Aを模す：admission成功後、当該manifestファイルへの
    読み取りのみを真のOSError（真のfilesystem I/O failure）で失敗させる
    （ファイル内容自体は正常なJSONのまま——schema corruptionとは手段を区別する）。"""

    def __init__(self, manifest_store, member_run_id: str):
        self._manifest = manifest_store
        self._member_run_id = member_run_id
        self.calls = 0

    def run(self, event, dry_run=False, target_step_filter=None, post_admission_hook=None,
            correlation_metadata=None, side_effect_execution_provenance=None):
        self.calls += 1
        run_id = self._member_run_id
        root_run_id = event.job_id
        if post_admission_hook is not None:
            post_admission_hook(run_id)

        steps = [make_step_result(s, executed=True, success=True, action_taken=True) for s in ALL_WORKFLOW_ENGINE_STEPS]
        return WorkflowEngineResult(
            run_id=run_id, steps=steps, overall_success=True, stopped_early=False,
            started_at=datetime.now(), finished_at=datetime.now(),
        )


engine_g = IOFailureEngine(manifest_g, member_run_id="exec-run-g")
executor_g = RetryExecutor(
    workflow_engine_manager=engine_g, lineage=lineage_g,
    manifest=ManifestReaderFacade(manifest_g), side_effect_classifier=classifier_g,
)
request_g = RetryRequest(run_id="run-g", attempt=1, requested_at=datetime.now(), dry_run=False)

target_path_g = manifest_g._path_for("run-g", 1, "exec-run-g")
with patch.object(pathlib.Path, "read_text", _make_selective_io_failure(target_path_g)):
    executor_g.execute(request_g, created_g.lineage, claim_g)
record_g = lineage_g.peek("run-g")

check_true("G前提: manifestファイル自体はvalidなJSONのまま残っている（内容破損ではない証拠）",
           target_path_g.exists() and target_path_g.read_text(encoding="utf-8").startswith("{\"schema_version\""))
check("G1. classifierは一度も呼ばれない（read errorで短絡）", len(classifier_g.calls), 0)
check("G2. final disposition=HUMAN_REVIEW_REQUIRED（真のI/O failure単体でHRR）",
      record_g.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("G3. mark_terminal()へ渡されたdispositionもHRR（durable記録で確認）", record_g.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("G4. phaseはTERMINAL", record_g.phase, RetryLineagePhase.TERMINAL)

summary_g = lineage_g.reconcile_all(lambda run_id: None)
check("G5. next automatic retryが開かない（opened_count=0）", summary_g.opened_count, 0)
print()


# =====================================================================
# グループH：restart IOError
# =====================================================================
print("[グループH] restart IOError（真のfilesystem I/O failure）")

lineage_h, manifest_h, draft_state_h, classifier_h = make_stack()
created_h = lineage_h.create_new_lineage("run-h", make_monitor_record("run-h"))
claim_h = lineage_h.claim("run-h")
mark_ok_h = lineage_h.mark_execution_started("run-h", "exec-run-h", claim_h.owner_token)
check_true("H前提: mark_execution_started()成功（空manifest作成済み）", mark_ok_h)

monitor_h = make_monitor_record(
    "run-h", steps=_to_execution_history_steps(make_monitor_record(
        "run-h", steps=[make_step_result(s, executed=True, success=True, action_taken=True) for s in ALL_WORKFLOW_ENGINE_STEPS],
    )),
)

target_path_h = manifest_h._path_for("run-h", 1, "exec-run-h")
with patch.object(pathlib.Path, "read_text", _make_selective_io_failure(target_path_h)):
    summary_h = lineage_h.reconcile_all(lambda run_id: monitor_h if run_id == "exec-run-h" else None)
record_h = lineage_h.peek("run-h")

check_true("H前提: manifestファイル自体はvalidなJSONのまま残っている（内容破損ではない証拠）",
           target_path_h.exists() and target_path_h.read_text(encoding="utf-8").startswith("{\"schema_version\""))
check("H1. classifierは一度も呼ばれない（read errorで短絡）", len(classifier_h.calls), 0)
check("H2. final disposition=HUMAN_REVIEW_REQUIRED（真のI/O failure単体でHRR）",
      record_h.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("H3. mark_terminal()へ渡されたdispositionもHRR（durable記録で確認）", record_h.terminal_disposition, RetryLineageDisposition.HUMAN_REVIEW_REQUIRED)
check("H4. next automatic retryが開かない（同一reconcile_all()呼び出し内でopened_count=0）", summary_h.opened_count, 0)
check("H5. phaseはTERMINAL", record_h.phase, RetryLineagePhase.TERMINAL)
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
