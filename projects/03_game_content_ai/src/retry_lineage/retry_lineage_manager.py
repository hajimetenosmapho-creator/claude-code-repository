"""
Retry Lineage Manager（v6.31.0、Release 6.31）

RetryLineageManager: lineage・attempt lifecycle・durable stateの唯一の管理者

設計方針（docs/design/retry_lineage_eligibility_durable_attempt_state.md 7・9・12・
13・16・18章）:
    - find_existing_lineage()（分岐(1)(2)、read-only）・create_new_lineage()
      （分岐(3)、initial admission gate）へ完全分離する（7.1・7.2章、MAJ-R9-1・
      MAJ-R9-2対応）。
    - RetryLineageStoreLockを取得するコードパスは find_existing_lineage() /
      create_new_lineage() / claim() / release_claim() / mark_execution_started() /
      mark_terminal() / open_next_attempt() の7メソッドのみ（9.2章）。peek() /
      diagnose_stuck() / find_by_member_run_id()はread-onlyのためロックしない。
    - reconcile_all()（公開API）は内部でRetryExecutionLockを取得し、成功した場合
      のみ_reconcile_all_locked()（実処理）へ委譲する。RETRY_LINEAGE_ENABLED=false
      でも reconcile_all() 自体は動作継続する（claim()のみがfail-closedスイッチの
      対象、16章）。
    - resolve_status_fn引数は`Callable[[str], WorkflowMonitorRecord | None]`
      （典型的には`WorkflowMonitorManager.get_status`をそのまま渡す）。戻り値の
      `.monitor_status`で"success"/"failure"/"in_progress"相当を判定し、`.steps`を
      classify_execution_history_step()へ渡す（16章(a)）。
    - `next_attempt_ordinal`は「現在open中（READY_ELIGIBLE/CLAIMED/EXECUTION_STARTED/
      直近のTERMINAL）のattempt_scopes[-1]のattempt_no」を常に指す、
      `attempt_scopes[-1].attempt_no`の非正規化コピーとして実装する。
      10.3.3章(b)のcorrelation-fallback exact-match検証
      （`intended_attempt_no == lineage.next_attempt_ordinal`）が、
      `mark_execution_started()`未達のorphan（claim()済みだが`attempt_scopes`は
      更新されない、CLAIMEDのままの状態）に対しても、claim()が払い出した
      attempt_noと一致することを要求しているため（「`next_attempt_ordinal`は
      当該attemptの試行によって一切消費されていない」という10.3.3章(b)の記述は、
      claim()時点でこの値がまだ次のattemptへ進んでいないことを前提とする）、
      この値は`attempt_scopes[-1].attempt_no`と常に同期している必要がある。
      設計書のこのフィールドの更新規則は「Round 1〜3から変更なし」と旧版参照の
      まま明示されていなかったため、実装時にこの契約として確定した。
    - `next_eligible_at`（cooldown）は、そのduration自体が設計書25章Risk#3で
      「妥当性が未確定」の残存Open Questionとして明示されているため、本Releaseでは
      いずれの書き込み経路（create_new_lineage()・open_next_attempt()）でも常に
      Noneのままとする（cooldownを積極的に設定する新規ロジックは追加しない）。
      claim()側の`next_eligible_at`チェック自体はスキーマ・契約として維持し、
      将来Noneでない値が設定されるようになった場合に備える。
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Callable

from workflow_monitor import WorkflowMonitorStatus

from protected_operation_manifest.errors import ProtectedOperationManifestReadError
from side_effect_safety.side_effect_safety_category import ProtectedOperationContext

from .retry_execution_lock import RetryExecutionLock, RetryExecutionLockBusyError
from .retry_lineage_config import RetryLineageConfig
from .retry_lineage_disposition import RetryLineageDisposition
from .retry_lineage_genuine_action import classify_execution_history_step
from .retry_lineage_phase import RetryLineagePhase
from dataclasses import replace

from .retry_lineage_record import (
    HumanReviewResolution,
    HumanReviewResolutionRecord,
    RetryAttemptExecutionScope,
    RetryLineageMembershipEntry,
    RetryLineageRecord,
    RetryLineageTransitionEvent,
)
from .retry_lineage_results import (
    ClaimResult,
    CreateNewLineageResult,
    MarkTerminalResult,
    OpenNextAttemptResult,
    ReconcileSummary,
    ResolveHumanReviewResult,
)
from .retry_lineage_store import RetryLineageStore
from .retry_lineage_store_lock import RetryLineageStoreLock
from .retry_lineage_target_resolution import (
    SIDE_EFFECT_CONTRACT_VERSION,
    _canonicalize_step_order,
    compute_initial_confirmed_steps,
    compute_steps_to_execute,
    disposition_from_categories,
    resolve_final_disposition,
)

if TYPE_CHECKING:
    from protected_operation_manifest import ProtectedOperationManifestStore
    from retry_engine.retry_policy_protocol import ExplainableRetryPolicy
    from side_effect_safety_classifier import SideEffectSafetyClassifier
    from workflow_monitor import WorkflowMonitorRecord

ResolveStatusFn = Callable[[str], "WorkflowMonitorRecord | None"]


def _verify_owner_authority(record: "RetryLineageRecord", owner_token: str) -> bool:
    """4段階のauthority check（Architecture Amendment §9.5.1）。いずれか1つでも
    失敗すればFalse（fail-closed）。None同士の比較で通過することを禁止する。"""
    if not owner_token or not isinstance(owner_token, str):
        return False  # (1) caller owner_tokenがnon-empty strであること
    if not record.owner_token or not isinstance(record.owner_token, str):
        return False  # (2) durable record.owner_tokenがnon-empty strであること
    if record.phase != RetryLineagePhase.CLAIMED:
        return False  # (3) phase == CLAIMED
    if record.owner_token != owner_token:
        return False  # (4) caller token == durable token（exact match）
    return True


class RetryLineageManager:
    """lineage・attempt lifecycle・durable stateの唯一の管理者。"""

    def __init__(
        self,
        store: RetryLineageStore,
        config: RetryLineageConfig,
        policy: "ExplainableRetryPolicy",
        manifest: "ProtectedOperationManifestStore | None" = None,
        side_effect_classifier: "SideEffectSafetyClassifier | None" = None,
    ):
        """
        manifest / side_effect_classifier（Architecture Amendment、Protected
        Operation Manifest、§4.1・§9・§10・§11）：構造上は省略可能（デフォルト
        None、既存の直接構築互換性のため引数自体はoptionalのまま残す）。

        Codex Final Review Blocking#1対応：ただし、legacy lineage
        （`record.side_effect_contract_version is None`）でのみ、既存6.31
        以前のstep-only disposition判定（decide_disposition() /
        disposition_from_categories()）へのフォールバックを許容する。
        protected lineage（`side_effect_contract_version is not None`）で
        manifest/side_effect_classifierのいずれかが省略されている場合は、
        決してstep-only fallbackへ降格せず、`_reconcile_all_locked()`内で
        fail-closedにHUMAN_REVIEW_REQUIREDへ確定する（「composition rootが
        必ず両方構築・注入するはず」という前提のみをsafety guaranteeにしない）。
        production composition root（RetryCompositionRoot）は両方を必ず構築・
        注入し、Approved Architecture §22.1cが要求するSideEffectSafety
        Classifier接続を閉じる。"""
        self._store = store
        self._config = config
        self._policy = policy
        self._manifest = manifest
        self._side_effect_classifier = side_effect_classifier

    def _store_lock(self) -> RetryLineageStoreLock:
        return RetryLineageStoreLock(self._config.store_lock_path)

    @property
    def execution_lock_path(self):
        """RetryManager.retry()と本クラスのreconcile_all()が共有する唯一の
        RetryExecutionLockファイルパス（9.3章）。RetryManagerはこのプロパティ経由で
        同一パスを取得し、直接RetryLineageConfigへアクセスしない。"""
        return self._config.execution_lock_path

    # ------------------------------------------------------------------
    # 7.1章：分岐(1)(2)、既存lineageへの再接続（read-only）
    # ------------------------------------------------------------------
    def find_existing_lineage(self, run_id: str) -> RetryLineageRecord | None:
        """分岐(1)(2)専用。durable lineage membership/rootの検索のみを行う。
        WorkflowMonitor・RetryPolicyのいずれも一切参照しない（呼び出しさえしない）。
        いかなるフィールドも書き換えない（save()を一度も呼ばない）。"""
        with self._store_lock():
            direct = self._store.get(run_id)
            if direct is not None:
                return direct

            member_root_run_id = self._find_root_by_member_run_id(run_id)
            if member_root_run_id is not None:
                record = self._store.get(member_root_run_id)
                if record is not None:
                    return record
                # invariant violation：membership indexが指すlineageが実在しない。
                # fail-closed：既存lineageとして扱わず、新規lineage作成経路へ
                # フォールバックさせる（7.4章のグローバル一意性チェックがこの
                # 不整合を後続で検出する）。
                return None

            return None

    def _find_root_by_member_run_id(self, run_id: str) -> str | None:
        """全lineageを線形走査してmembershipを確認する（25章Risk#1：スケーラビリティは
        既知のOpen Questionとして残る。single-host・低頻度実行を前提としたFoundation
        First実装）。"""
        for record in self._store.list_all():
            if record.root_run_id == run_id:
                return record.root_run_id
            for entry in record.membership:
                if entry.run_id == run_id:
                    return record.root_run_id
        return None

    def find_by_member_run_id(self, candidate_run_id: str) -> str | None:
        """read-only公開版。RetryEnqueueTriggerのmembership-first判定（10.3.3章）から使う。"""
        return self._find_root_by_member_run_id(candidate_run_id)

    def peek(self, root_run_id: str) -> RetryLineageRecord | None:
        """read-only。ロックを取得しない（9.2章）。"""
        return self._store.get(root_run_id)

    def verify_orphan_correlation(
        self, root_run_id: str, intended_attempt_no: str, correlation_id: str,
    ) -> bool:
        """10.3.3章(b)のcorrelation-fallback exact-match検証（a・b・cの3条件）。
        read-only（ロックを取得しない、peek()と同じ扱い）。

        a. root_run_idが実在するlineageを指す。
        b. intended_attempt_no（文字列。数値としてパース可能であること）が、
           lineageの現在のnext_attempt_ordinalと厳密に一致する（range一致ではない、
           「次に消費されるattempt_no」との完全一致）。
        c. correlation_idが、transition_history内のto_phase==CLAIMEDかつ
           attempt_no==intended_attempt_noの遷移イベントに実際に記録されている
           correlation_idと完全一致する。

        いずれか1つでも満たさない場合はFalse（fail-closed、盲目的に信頼しない）。
        forged（存在しないroot_run_idを騙る）・stale（古いattempt_noを騙る）・
        malformed（型不正）のいずれもこれによりFalseとなる。
        """
        record = self.peek(root_run_id)
        if record is None:
            return False  # (a) 失敗

        try:
            intended_attempt_no_int = int(intended_attempt_no)
        except (TypeError, ValueError):
            return False  # (b) パース不可

        if intended_attempt_no_int != record.next_attempt_ordinal:
            return False  # (b) 失敗（stale/未来値のいずれも含む）

        for event in record.transition_history:
            if (
                event.to_phase == RetryLineagePhase.CLAIMED
                and event.attempt_no == intended_attempt_no_int
                and event.correlation_id is not None
                and event.correlation_id == correlation_id
            ):
                return True  # (c) 成功

        return False  # (c) 失敗

    # ------------------------------------------------------------------
    # 7.2章：分岐(3)、新規lineage作成とinitial admission gate
    # ------------------------------------------------------------------
    def create_new_lineage(
        self, run_id: str, monitor_record: "WorkflowMonitorRecord",
    ) -> CreateNewLineageResult:
        with self._store_lock():
            # max_attempts snapshotのvalidationを、should_retry()を呼ぶより前に行う
            # （Codex Round 10 review Major#1対応）。
            max_attempts_snapshot = self._policy.max_attempts
            if (
                not isinstance(max_attempts_snapshot, int)
                or isinstance(max_attempts_snapshot, bool)
                or max_attempts_snapshot < 0
            ):
                return CreateNewLineageResult(
                    lineage=None, admission_rejected=True,
                    reason=(
                        f"invalid max_attempts snapshot value: {max_attempts_snapshot!r} "
                        f"(must be a non-negative int, not bool). Refusing to create lineage "
                        f"(fail-closed; validation-rejected, should_retry() was not called)."
                    ),
                )

            if not self._policy.should_retry(monitor_record.monitor_status, attempt=0):
                return CreateNewLineageResult(
                    lineage=None, admission_rejected=True,
                    reason=self._skip_reason(monitor_record.monitor_status, 0),
                )

            # Architecture Amendment（Code Review Major#3対応）：グローバルmembership
            # 一意性チェック。find_existing_lineage()は通常このrun_idに対する既存lineageを
            # 検出済みのはずだが（9.3.2章の呼び出し順序）、membership index破損時の
            # フォールバック（7.1章、25章項目16）ではfind_existing_lineage()がNoneを
            # 返した後この経路へ到達しうる。同一store_lockの内側で再検証し、既に
            # 他のlineageのroot_run_idまたはmembershipとして記録されているrun_idに
            # 対しては、新規lineageを作成せずfail-closedで拒否する（自動マージ・
            # 自動修復は行わない）。
            for existing_record in self._store.list_all():
                if existing_record.root_run_id == run_id or any(
                    entry.run_id == run_id for entry in existing_record.membership
                ):
                    return CreateNewLineageResult(
                        lineage=None, admission_rejected=True,
                        reason=(
                            f"global membership uniqueness violation: run_id={run_id} is "
                            f"already recorded under root_run_id="
                            f"{existing_record.root_run_id} (likely membership index "
                            f"corruption). Refusing to create a duplicate lineage "
                            f"(fail-closed; validation-rejected, no auto-repair)."
                        ),
                    )

            initial_confirmed_steps = compute_initial_confirmed_steps(monitor_record.steps)
            initial_steps_to_execute = compute_steps_to_execute(initial_confirmed_steps)
            now = datetime.now()
            initial_scope = RetryAttemptExecutionScope(
                attempt_no=1,
                steps_confirmed_done_before=list(initial_confirmed_steps),
                steps_to_execute=_canonicalize_step_order(initial_steps_to_execute),
                determined_at=now,
            )
            record = RetryLineageRecord(
                root_run_id=run_id,
                parent_run_id=None,
                latest_run_id=run_id,
                attempt_count=0,
                max_attempts=max_attempts_snapshot,
                next_attempt_ordinal=1,  # attempt_scopes[0].attempt_no（1）と同期させる。
                phase=RetryLineagePhase.READY_ELIGIBLE,
                terminal_disposition=None,
                next_eligible_at=None,
                owner_token=None,
                steps_confirmed_done=list(initial_confirmed_steps),
                membership=[
                    RetryLineageMembershipEntry(
                        run_id=run_id, parent_run_id=None, attempt_no=1, recorded_at=now,
                    )
                ],
                transition_history=[
                    RetryLineageTransitionEvent(
                        attempt_no=1, from_phase=None, to_phase=RetryLineagePhase.READY_ELIGIBLE,
                        run_id=run_id, at=now, detail="lineage created",
                    )
                ],
                attempt_scopes=[initial_scope],
                created_at=now,
                updated_at=now,
                side_effect_contract_version=SIDE_EFFECT_CONTRACT_VERSION,  # Release 6.32、18.1節
            )
            ok = self._store.save(record)
            if not ok:
                return CreateNewLineageResult(
                    lineage=None, admission_rejected=True,
                    reason="lineage store save failed (fail-closed; treated as not created).",
                )
            return CreateNewLineageResult(lineage=record, admission_rejected=False)

    def _skip_reason(self, monitor_status: WorkflowMonitorStatus, attempt: int) -> str:
        if monitor_status not in self._policy.target_statuses:
            return (
                f"monitor_status={monitor_status.value} is not a retry target "
                f"({sorted(s.value for s in self._policy.target_statuses)})."
            )
        return f"attempt {attempt} has reached max_attempts={self._policy.max_attempts}."

    # ------------------------------------------------------------------
    # 8・11.4.5.2(a)章：claim() / release_claim()
    # ------------------------------------------------------------------
    def claim(self, root_run_id: str) -> ClaimResult:
        with self._store_lock():
            record = self._store.get(root_run_id)
            if record is None or record.phase != RetryLineagePhase.READY_ELIGIBLE:
                return ClaimResult(
                    acknowledged=False,
                    reason=(
                        f"phase mismatch: root_run_id={root_run_id} "
                        f"(phase={record.phase.value if record else 'not_found'})"
                    ),
                )

            if not self._config.is_ready():
                return ClaimResult(
                    acknowledged=False,
                    reason="RETRY_LINEAGE_ENABLED is false (claim gate closed, 16章).",
                )

            if record.next_eligible_at and record.next_eligible_at > datetime.now():
                return ClaimResult(acknowledged=False, reason="cooldown not elapsed")

            if not record.attempt_scopes:
                return ClaimResult(
                    acknowledged=False,
                    reason=(
                        "invariant_violation: no attempt_scopes recorded while "
                        "phase=READY_ELIGIBLE. Refusing to claim."
                    ),
                )

            stored_scope = record.attempt_scopes[-1]
            # Architecture Amendment（Code Review Major#4対応）：next_attempt_ordinal
            # 不変条件（next_attempt_ordinalはattempt_scopes[-1].attempt_noと常に
            # 同期する、10.3.3章(b)のcorrelation-fallback exact-matchの前提）を、
            # 値を使用する前に検証する。不一致は状態破損を意味し、自動修復しない。
            if record.next_attempt_ordinal != stored_scope.attempt_no:
                return ClaimResult(
                    acknowledged=False,
                    reason=(
                        f"invariant_violation: next_attempt_ordinal "
                        f"({record.next_attempt_ordinal}) != attempt_scopes[-1].attempt_no "
                        f"({stored_scope.attempt_no}). Refusing to claim (no auto-repair)."
                    ),
                )
            recomputed = compute_steps_to_execute(record.steps_confirmed_done)
            recomputed_normalized = _canonicalize_step_order(recomputed)
            stored_normalized = _canonicalize_step_order(stored_scope.steps_to_execute)
            if recomputed_normalized != stored_normalized:
                return ClaimResult(
                    acknowledged=False,
                    reason=(
                        f"invariant_violation: recomputed steps_to_execute ({recomputed}) does "
                        f"not match stored attempt_scopes[-1].steps_to_execute "
                        f"({stored_scope.steps_to_execute}). Refusing to claim (no auto-repair)."
                    ),
                )

            steps_to_execute = list(stored_scope.steps_to_execute)
            correlation_id = uuid.uuid4().hex
            now = datetime.now()
            record.phase = RetryLineagePhase.CLAIMED
            record.owner_token = uuid.uuid4().hex
            record.transition_history.append(
                RetryLineageTransitionEvent(
                    attempt_no=stored_scope.attempt_no, from_phase=RetryLineagePhase.READY_ELIGIBLE,
                    to_phase=RetryLineagePhase.CLAIMED, run_id=None, at=now,
                    correlation_id=correlation_id,
                )
            )
            record.updated_at = now
            ok = self._store.save(record)
            if not ok:
                return ClaimResult(acknowledged=False, reason="lineage store save failed")

            return ClaimResult(
                acknowledged=True, attempt_no=stored_scope.attempt_no,
                correlation_id=correlation_id, steps_to_execute=steps_to_execute,
                owner_token=record.owner_token,
            )

    def release_claim(self, root_run_id: str, expected_owner_token: str) -> bool:
        """OWNER-AUTHORIZED RELEASE（Architecture Amendment §9.5.2）。live
        claimant（RetryExecutor等）が自分自身のclaimを手放す場合専用。
        _verify_owner_authority()の4段階checkに失敗したら（mismatch・stale・
        missingのいずれであっても）絶対にreleaseしない——stale caller（既に
        reconciliationのCLAIMED orphan回収で回収され、別のclaimが確立済みの
        旧claim）が新しいclaimを誤って解除することを構造的に防ぐ。"""
        with self._store_lock():
            record = self._store.get(root_run_id)
            if record is None or not _verify_owner_authority(record, expected_owner_token):
                return False
            now = datetime.now()
            attempt_no = record.attempt_scopes[-1].attempt_no if record.attempt_scopes else 0
            record.phase = RetryLineagePhase.READY_ELIGIBLE
            record.owner_token = None
            record.transition_history.append(
                RetryLineageTransitionEvent(
                    attempt_no=attempt_no, from_phase=RetryLineagePhase.CLAIMED,
                    to_phase=RetryLineagePhase.READY_ELIGIBLE, run_id=None, at=now,
                    detail="claim released",
                )
            )
            record.updated_at = now
            return self._store.save(record)

    # ------------------------------------------------------------------
    # 9.5・10.2章：mark_execution_started()
    # ------------------------------------------------------------------
    def mark_execution_started(self, root_run_id: str, run_id: str, owner_token: str) -> bool:
        """post-admission hookから呼ばれる。attempt消費点（9.5章）：durable ack成功
        時点でattempt_countを+1する。

        Architecture Amendment（Protected Operation Manifest、§4.1・§9.5.1）：
        owner_tokenの4段階authority check（_verify_owner_authority()）に成功した
        場合のみ処理を続行する。self._manifestが構築済みでside_effect_contract_
        versionが設定されたlineageの場合、manifest作成をlineage phase遷移より
        先に行う（manifest作成失敗時、durable lineage phaseはCLAIMEDのまま
        変化しない——呼び出し元のrelease_claim(root_run_id, owner_token)が
        正しく機能する）。"""
        with self._store_lock():
            record = self._store.get(root_run_id)
            if record is None or not _verify_owner_authority(record, owner_token):
                return False
            attempt_no = record.attempt_scopes[-1].attempt_no if record.attempt_scopes else record.next_attempt_ordinal
            if record.side_effect_contract_version is not None and self._manifest is not None:
                # Round 9：create_for_attempt()はowner_tokenを受け取らない
                # （manifest自体はauthorityを保持・検証しない）。run_id
                # （=member_run_id）はWorkflowEngineManagerが生成した一意な
                # uuid4であり、この呼び出し自体が上のauthority check成功済みの
                # 文脈からのみ行われる。同一キーへの既存レコード発見（正常経路
                # では構造的に起こり得ない）はcatchせずProtectedOperation
                # ManifestContractViolationErrorとして伝播させ、既存の
                # fail-fast契約（WorkflowEngineExecutor/RetryExecutor.execute()の
                # 既存except節）へ委ねる——rebindフォールバックは存在しない。
                manifest_ok = self._manifest.create_for_attempt(root_run_id, attempt_no, run_id)
                if not manifest_ok:
                    return False  # レコードは一切変更していない。durable lineage
                                  # phaseはCLAIMEDのまま。
            now = datetime.now()
            record.phase = RetryLineagePhase.EXECUTION_STARTED
            record.latest_run_id = run_id
            record.attempt_count += 1
            record.membership.append(
                RetryLineageMembershipEntry(
                    run_id=run_id,
                    parent_run_id=root_run_id if run_id != root_run_id else None,
                    attempt_no=attempt_no, recorded_at=now,
                )
            )
            record.transition_history.append(
                RetryLineageTransitionEvent(
                    attempt_no=attempt_no, from_phase=RetryLineagePhase.CLAIMED,
                    to_phase=RetryLineagePhase.EXECUTION_STARTED, run_id=run_id, at=now,
                )
            )
            # Release 6.32、17.2節：crash-resumable HRR markerの解放。このattemptが
            # HRR authorized経路で開かれたもの（opened_attempt_noが一致）である場合
            # のみクリアする。通常のFAILED/NOT_ACTIONED経路（human_review_resolutionが
            # 元々None）では本分岐はno-opのまま。
            if (
                record.human_review_resolution is not None
                and record.human_review_resolution.opened_attempt_no == attempt_no
            ):
                record.human_review_resolution = None
            record.updated_at = now
            return self._store.save(record)

    # ------------------------------------------------------------------
    # 12章：mark_terminal() / open_next_attempt()
    # ------------------------------------------------------------------
    def mark_terminal(
        self, root_run_id: str, disposition: RetryLineageDisposition,
        executed_run_id: str, newly_confirmed_steps: list[str],
    ) -> MarkTerminalResult:
        with self._store_lock():
            record = self._store.get(root_run_id)
            if record is None or record.phase != RetryLineagePhase.EXECUTION_STARTED:
                return MarkTerminalResult(acknowledged=False, reason="phase mismatch: not EXECUTION_STARTED")

            now = datetime.now()
            record.steps_confirmed_done = sorted(set(record.steps_confirmed_done) | set(newly_confirmed_steps))
            record.phase = RetryLineagePhase.TERMINAL
            record.terminal_disposition = disposition
            record.latest_run_id = executed_run_id
            # attempt_countはここでは一切書き換えない（payback廃止、9.8.1.3章）。
            # attempt_scopesへの書き込みも一切行わない（12章、B-1対応）。
            attempt_no = record.attempt_scopes[-1].attempt_no if record.attempt_scopes else record.next_attempt_ordinal
            record.transition_history.append(
                RetryLineageTransitionEvent(
                    attempt_no=attempt_no, from_phase=RetryLineagePhase.EXECUTION_STARTED,
                    to_phase=RetryLineagePhase.TERMINAL, run_id=executed_run_id, at=now,
                    detail=f"disposition={disposition.value}",
                )
            )
            record.updated_at = now
            ok = self._store.save(record)
            if not ok:
                return MarkTerminalResult(acknowledged=False, reason="lineage store save failed")
            return MarkTerminalResult(acknowledged=True)

    def open_next_attempt(self, root_run_id: str) -> OpenNextAttemptResult:
        with self._store_lock():
            record = self._store.get(root_run_id)
            if record is None or record.phase != RetryLineagePhase.TERMINAL:
                return OpenNextAttemptResult(acknowledged=False, reason="phase mismatch: not TERMINAL")

            resolution = record.human_review_resolution
            hrr_authorized = (
                record.terminal_disposition == RetryLineageDisposition.HUMAN_REVIEW_REQUIRED
                and resolution is not None
                and resolution.resolution == HumanReviewResolution.RETRY_ALLOWED
            )
            if (
                record.terminal_disposition not in (RetryLineageDisposition.FAILED, RetryLineageDisposition.NOT_ACTIONED)
                and not hrr_authorized
            ):
                return OpenNextAttemptResult(
                    acknowledged=False,
                    reason=(
                        "terminal_disposition is not retryable (HUMAN_REVIEW_REQUIRED requires an "
                        "explicit RETRY_ALLOWED resolution via resolve_human_review(), Release 6.32 17章)."
                    ),
                )

            if record.attempt_count >= record.max_attempts:
                # durable stateのみに基づく判定（record.attempt_count・record.max_attempts）。
                # monitor_statusもRetryPolicy.max_attemptsも都度参照しない（9.8.1章）。
                return OpenNextAttemptResult(acknowledged=False, reason="max_attempts exhausted")

            # Architecture Amendment（Code Review Major#4対応）：next_attempt_ordinal
            # 不変条件の検証。この後next_attempt_ordinalへ+1した値を書き込むため、
            # 書き込み前の時点で現在値がattempt_scopes[-1].attempt_noと同期している
            # ことを確認する（claim()と同一のチェック）。
            if record.attempt_scopes and record.next_attempt_ordinal != record.attempt_scopes[-1].attempt_no:
                return OpenNextAttemptResult(
                    acknowledged=False,
                    reason=(
                        f"invariant_violation: next_attempt_ordinal "
                        f"({record.next_attempt_ordinal}) != attempt_scopes[-1].attempt_no "
                        f"({record.attempt_scopes[-1].attempt_no}). Refusing to open next "
                        f"attempt (no auto-repair)."
                    ),
                )

            steps_to_execute = compute_steps_to_execute(record.steps_confirmed_done)
            if not steps_to_execute:
                return OpenNextAttemptResult(
                    acknowledged=False,
                    reason=(
                        "invariant_violation: steps_confirmed_done covers all steps while "
                        "terminal_disposition is retryable (expected at least one unresolved "
                        "step this attempt). Refusing to open next attempt with an empty "
                        "execution scope."
                    ),
                )

            now = datetime.now()
            # next_attempt_ordinalはattempt_scopes[-1].attempt_noの非正規化コピー
            # （常に同期させる契約）。ここで初めて新しいattempt番号（現在値+1）を
            # 払い出し、新しいscope・record.next_attempt_ordinal双方へ同時に反映する。
            next_attempt_no = record.next_attempt_ordinal + 1
            next_scope = RetryAttemptExecutionScope(
                attempt_no=next_attempt_no,
                steps_confirmed_done_before=list(record.steps_confirmed_done),
                steps_to_execute=_canonicalize_step_order(steps_to_execute),
                determined_at=now,
            )
            record.attempt_scopes.append(next_scope)
            record.phase = RetryLineagePhase.READY_ELIGIBLE
            record.terminal_disposition = None
            if hrr_authorized:
                # Release 6.32、17.2節：human_review_resolutionはここではクリアしない
                # ——opened_attempt_noへ新attempt番号を記録し、crash-resumable dispatch
                # markerとして保持する。クリアはmark_execution_started()まで遅延させる。
                record.human_review_resolution = replace(resolution, opened_attempt_no=next_attempt_no)
            else:
                record.human_review_resolution = None
            record.next_eligible_at = None
            record.next_attempt_ordinal = next_attempt_no
            record.transition_history.append(
                RetryLineageTransitionEvent(
                    attempt_no=next_attempt_no, from_phase=RetryLineagePhase.TERMINAL,
                    to_phase=RetryLineagePhase.READY_ELIGIBLE, run_id=None, at=now,
                    detail=(
                        "next attempt opened via RETRY_ALLOWED human review resolution"
                        if hrr_authorized else "next attempt opened"
                    ),
                )
            )
            record.updated_at = now
            ok = self._store.save(record)
            if not ok:
                return OpenNextAttemptResult(acknowledged=False, reason="lineage store save failed")
            return OpenNextAttemptResult(acknowledged=True, attempt_no=next_attempt_no)

    def open_next_attempt_after_human_review(self, root_run_id: str) -> OpenNextAttemptResult:
        """operator-invoked専用のself-locking wrapper（`reconcile_all()`と同型、
        Release 6.32、16章）。`open_next_attempt()`自身はRetryExecutionLockを
        取得しない——呼び出し元が既に取得済みであることを前提とする既存契約
        （9.3章）。自動reconciliation sweep（`_reconcile_all_locked()`）以外から
        `open_next_attempt()`を呼ぶ経路は、本wrapperのみを経由する。"""
        try:
            with RetryExecutionLock(self.execution_lock_path):
                return self.open_next_attempt(root_run_id)
        except RetryExecutionLockBusyError:
            return OpenNextAttemptResult(acknowledged=False, reason="execution lock busy")

    # ------------------------------------------------------------------
    # 17章：Human Resolution Lifecycle
    # ------------------------------------------------------------------
    def resolve_human_review(
        self, root_run_id: str, resolution: HumanReviewResolution, actor: str, note: str | None = None,
    ) -> ResolveHumanReviewResult:
        """durable one-shot resolution（Release 6.32、17.2節）。`reconcile_all()`と
        同型のself-locking method——`RetryExecutionLock`を自ら取得してから
        `_store_lock()`でread-modify-writeを行う（9.3章Lock Ordering）。"""
        try:
            with RetryExecutionLock(self.execution_lock_path):
                return self._resolve_human_review_locked(root_run_id, resolution, actor, note)
        except RetryExecutionLockBusyError:
            return ResolveHumanReviewResult(acknowledged=False, reason="execution lock busy")

    def _resolve_human_review_locked(
        self, root_run_id: str, resolution: HumanReviewResolution, actor: str, note: str | None,
    ) -> ResolveHumanReviewResult:
        with self._store_lock():
            record = self._store.get(root_run_id)
            if (
                record is None
                or record.phase != RetryLineagePhase.TERMINAL
                or record.terminal_disposition != RetryLineageDisposition.HUMAN_REVIEW_REQUIRED
            ):
                return ResolveHumanReviewResult(acknowledged=False, reason="not in HUMAN_REVIEW_REQUIRED")

            existing = record.human_review_resolution
            if existing is not None:
                if existing.resolution == resolution:
                    # 同一decisionの再送：idempotent success。actor/note/resolved_atは
                    # 既存recordのまま上書きしない。追加のdurable writeも行わない。
                    return ResolveHumanReviewResult(acknowledged=True)
                return ResolveHumanReviewResult(
                    acknowledged=False,
                    reason=f"conflicting resolution already recorded: {existing.resolution.value}",
                )

            now = datetime.now()
            record.human_review_resolution = HumanReviewResolutionRecord(
                resolution=resolution, actor=actor, note=note, resolved_at=now,
            )
            attempt_no = record.attempt_scopes[-1].attempt_no if record.attempt_scopes else record.next_attempt_ordinal
            record.transition_history.append(
                RetryLineageTransitionEvent(
                    attempt_no=attempt_no, from_phase=RetryLineagePhase.TERMINAL,
                    to_phase=RetryLineagePhase.TERMINAL, run_id=None, at=now,
                    detail=f"human_review_resolution={resolution.value}",
                )
            )
            record.updated_at = now
            ok = self._store.save(record)
            if not ok:
                return ResolveHumanReviewResult(acknowledged=False, reason="lineage store save failed")
            return ResolveHumanReviewResult(acknowledged=True)

    # ------------------------------------------------------------------
    # 9.3・16章：reconcile_all() / _reconcile_all_locked()
    # ------------------------------------------------------------------
    def reconcile_all(self, resolve_status_fn: ResolveStatusFn) -> ReconcileSummary:
        try:
            with RetryExecutionLock(self._config.execution_lock_path):
                return self._reconcile_all_locked(resolve_status_fn)
        except RetryExecutionLockBusyError:
            return ReconcileSummary(
                skipped=True,
                reason=(
                    "execution lock busy: retry() is in flight; reconciliation deferred to "
                    "next run_once() cycle (mutation不実行)"
                ),
            )

    def _reconcile_all_locked(self, resolve_status_fn: ResolveStatusFn) -> ReconcileSummary:
        resolved_count = 0
        for record in self._store.list_all():
            if record.phase != RetryLineagePhase.EXECUTION_STARTED:
                continue
            monitor_record = resolve_status_fn(record.latest_run_id)
            if monitor_record is None:
                continue  # crash matrix#14：何もしない（残存ギャップ）
            if monitor_record.monitor_status == WorkflowMonitorStatus.RUNNING:
                continue  # in_progress：何もしない

            # "success"（SUCCESS）／"failure"（FAILED・TIMEOUT）いずれも同一ロジックへ。
            newly_confirmed = compute_initial_confirmed_steps(monitor_record.steps)
            categories = [classify_execution_history_step(s) for s in monitor_record.steps]

            # Architecture Amendment（Protected Operation Manifest、§11、production
            # closure）：self._manifest / self._side_effect_classifierが構築済みで
            # side_effect_contract_versionが設定されたlineageの場合のみ、
            # SideEffectSafetyClassifier.classify() → resolve_final_disposition()
            # の実チェーンへ接続する。
            #
            # Codex Final Review Blocking#1対応：legacy lineage
            # （side_effect_contract_version is None）の場合のみ既存6.31以前の
            # disposition_from_categories()へフォールバックしてよい（§21の
            # 実装ノート参照、Zero-Diff維持のための意図的な後方互換設計）。
            # protected lineage（side_effect_contract_version is not None）で
            # manifest/classifierのいずれかが欠落している場合は、決して
            # step-only fallbackへ降格せず、fail-closedでHUMAN_REVIEW_REQUIRED
            # へ確定する（primary blocking findingの再導入を防ぐ）。
            if record.side_effect_contract_version is None:
                disposition = disposition_from_categories(categories)
            elif self._manifest is None or self._side_effect_classifier is None:
                disposition = RetryLineageDisposition.HUMAN_REVIEW_REQUIRED
            else:
                attempt_no = record.attempt_scopes[-1].attempt_no if record.attempt_scopes else record.next_attempt_ordinal
                try:
                    manifest_entries = self._manifest.list_for_attempt(
                        record.root_run_id, attempt_no, record.latest_run_id,
                    )
                except ProtectedOperationManifestReadError:
                    disposition = RetryLineageDisposition.HUMAN_REVIEW_REQUIRED
                else:
                    operations = [
                        ProtectedOperationContext(e.operation_kind, e.effect_site, e.operation_instance_key)
                        for e in manifest_entries
                    ]
                    safety_report = self._side_effect_classifier.classify(
                        record.root_run_id, attempt_no, record.latest_run_id, operations,
                    )
                    disposition = resolve_final_disposition(categories, safety_report)

            result = self.mark_terminal(
                record.root_run_id, disposition, record.latest_run_id, newly_confirmed,
            )
            if result.acknowledged:
                resolved_count += 1

        opened_count = 0
        for record in self._store.list_all():
            if record.phase != RetryLineagePhase.TERMINAL:
                continue
            if record.terminal_disposition not in (RetryLineageDisposition.FAILED, RetryLineageDisposition.NOT_ACTIONED):
                continue
            result = self.open_next_attempt(record.root_run_id)
            if result.acknowledged:
                opened_count += 1
            # ack=Falseの場合（budget exhaustion・invariant violation）は正常/異常いずれも
            # 何もしない。9.4章と同じ運用手順・18章の診断に委ねる。

        # Architecture Amendment（Code Review Blocking#1対応、16章(c)新設）：
        # phase==CLAIMEDのorphan回収。RetryExecutionLockが retry()・reconcile_all()
        # 双方にとって唯一のグローバル排他境界であるため（9.3章）、
        # _reconcile_all_locked()実行中に発見されるphase==CLAIMEDのlineageは、
        # 現在進行中の正当なclaimではあり得ず（他のretry()は同時に進行できない）、
        # 必ずclaim()成功後・post-admission hook呼び出しに到達する前のプロセス
        # クラッシュ由来のorphanである。mark_execution_started()が一度も成功して
        # いないためattempt_countは未消費であり、release_claim()によるbudgetへの
        # 影響は一切ない。
        # Architecture Amendment（Protected Operation Manifest、§9.5.2a、Round 9
        # SIMPLIFICATION PIVOT）：readable lease機構は撤回し、既存6.31の信頼
        # モデル（RetryExecutionLock保有＝reconciliation実行権）へ回帰する。
        # owner_tokenは検証しない（回収対象は定義上誰もowner_tokenを保持して
        # いないorphanであるため）。単独で呼び出し可能な別メソッド（owner-less
        # general release API）へ切り出さず、このループ本体へ直接インライン
        # する——reconcile_all()がRetryExecutionLockを保持している間だけ
        # 実行される、という構造そのものをauthorityの根拠とする。
        released_count = 0
        for record in self._store.list_all():
            if record.phase != RetryLineagePhase.CLAIMED:
                continue
            with self._store_lock():
                fresh = self._store.get(record.root_run_id)
                if fresh is None or fresh.phase != RetryLineagePhase.CLAIMED:
                    continue
                now = datetime.now()
                attempt_no = fresh.attempt_scopes[-1].attempt_no if fresh.attempt_scopes else 0
                fresh.phase = RetryLineagePhase.READY_ELIGIBLE
                fresh.owner_token = None
                fresh.transition_history.append(
                    RetryLineageTransitionEvent(
                        attempt_no=attempt_no, from_phase=RetryLineagePhase.CLAIMED,
                        to_phase=RetryLineagePhase.READY_ELIGIBLE, run_id=None, at=now,
                        detail="claim released (reconciliation orphan recovery)",
                    )
                )
                fresh.updated_at = now
                if self._store.save(fresh):
                    released_count += 1

        return ReconcileSummary(
            skipped=False, resolved_count=resolved_count, opened_count=opened_count,
            released_count=released_count,
        )

    # ------------------------------------------------------------------
    # 18章：diagnose_stuck()（read-only）
    # ------------------------------------------------------------------
    def diagnose_stuck(self, min_age_seconds: float = 300.0) -> list[dict]:
        """読み取り専用の診断。ロックを取得しない。

        (a) phase==READY_ELIGIBLEかつ、再計算されたsteps_to_executeが保存済み
            attempt_scopes[-1].steps_to_executeと一致しないlineage（claim()側の
            invariant violation、11.4.5.2(a)章）。
        (b) phase==TERMINALかつterminal_dispositionがretryableかつ、再計算された
            steps_to_executeが空集合であるlineage（open_next_attempt()側の
            invariant violation、11.4.5.2(b)章）。
        (c) phase in (CLAIMED, EXECUTION_STARTED)のまま、updated_atからmin_age_seconds
            以上経過しているlineage（汎用の経過時間ベースstaleness検出）。

        terminal_disposition==SUCCEEDEDのlineage、およびbudget exhaustionによる
        正常なTERMINAL終端（attempt_count>=max_attempts）は、いずれも本診断の
        対象に含めない（B-1の教訓、18章）。
        """
        now = datetime.now()
        findings: list[dict] = []
        for record in self._store.list_all():
            if record.phase == RetryLineagePhase.READY_ELIGIBLE and record.attempt_scopes:
                recomputed = _canonicalize_step_order(compute_steps_to_execute(record.steps_confirmed_done))
                stored = _canonicalize_step_order(record.attempt_scopes[-1].steps_to_execute)
                if recomputed != stored:
                    findings.append({
                        "root_run_id": record.root_run_id,
                        "reason": "invariant_violation: scope_mismatch",
                    })

            if (
                record.phase == RetryLineagePhase.TERMINAL
                and record.terminal_disposition in (RetryLineageDisposition.FAILED, RetryLineageDisposition.NOT_ACTIONED)
                and record.attempt_count < record.max_attempts
            ):
                if not compute_steps_to_execute(record.steps_confirmed_done):
                    findings.append({
                        "root_run_id": record.root_run_id,
                        "reason": "invariant_violation: empty_execution_scope",
                    })

            if record.phase in (RetryLineagePhase.CLAIMED, RetryLineagePhase.EXECUTION_STARTED):
                age = (now - record.updated_at).total_seconds()
                if age >= min_age_seconds:
                    findings.append({
                        "root_run_id": record.root_run_id,
                        "reason": f"stale: phase={record.phase.value} unchanged for {age:.0f}s",
                    })

        return findings
