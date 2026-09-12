"""
Retry Executor（v3.0.0、Release 6.31でRetry Lineage統合）

RetryExecutor: WorkflowEngineManagerの公開APIを呼び出すだけの薄いコンポーネント

設計方針:
    - 再実行の可否判定（RetryPolicyの適用）・RetryRequestの生成は RetryManager の責務であり、
      RetryExecutorはRetryManagerによってすでに「再実行する」と判定された RetryRequest の
      みを受け取る。ここでの唯一の仕事は、RetryRequest / lineage / claim情報を
      WorkflowEngineEvent へ変換して WorkflowEngineManager.run() を呼び出し、戻り値を
      RetryResult へ詰め替えて返すことだけである
      （docs/design/retry_engine_foundation.md 10章 Design Decision #10、Architecture Review反映）。
    - RetryPolicy を一切参照・保持しない（コンストラクタに policy 引数を持たない）。
    - source は新規定数を追加せず、既存の SOURCE_MANUAL を再利用する。再実行由来である
      ことは WorkflowEngineEvent.metadata に積む（同設計書10章 Design Decision #4）。
    - WorkflowEngineExecutor 等の内部実装には一切触れない。WorkflowEngineManager.run()の
      みを公開APIとして呼び出す。
    - （v5.6.0）request.dry_run=Trueの場合、WorkflowEngineManager.run()の呼び出し自体は
      維持する（Workflow Engine層のdry_run伝播は既に安全であり、workflow_engine_resultを
      通じて「何が起きたはずか」を可視化する価値があるため）が、戻り値のRetryResult.outcome
      はRetryOutcome.RETRIEDではなくRetryOutcome.DRY_RUNとする。これにより、後続の
      Decider/Executor群（RetryQueueUpdateDecider等）が「実際に再実行された」と誤判定し
      Queue除去・履歴記録という副作用を発生させることを防ぐ
      （docs/design/retry_runtime_safe_dry_run_foundation.md 参照）。

Release 6.31での変更（docs/design/retry_lineage_eligibility_durable_attempt_state.md
9.3.2・9.7・10.1〜10.3・11.4〜11.5章）:
    - execute()のシグネチャを`(request, record)`（WorkflowMonitorRecord）から
      `(request, lineage, claim)`（RetryLineageRecord・ClaimResult）へ変更した。
    - claim.steps_to_executeを`target_step_filter`として`.run()`へ渡す（11.4章）。
    - post-admission hookを構築し、`self._lineage.mark_execution_started()`へ委譲する
      （10.2章）。hookは`claim`ごとに新しいクロージャとして構築され、
      WorkflowEngineManagerのコンストラクタではなく`.run()`の呼び出しごとの引数として
      渡される（workflow_engine_post_admission_hook.py参照）。
    - correlation_metadataを"retry_lineage"namespace配下に構築し`.run()`へ渡す（10.3章）。
    - dry_runでない場合、`.run()`完了後に`decide_disposition()`/`compute_newly_confirmed()`
      でdispositionを算出し、`self._lineage.mark_terminal()`を呼ぶ。dry_runの場合は
      lineageのdurable stateを一切変更しない（既存のdry-run zero-write契約を維持）。
    - `RetryExecutor.__init__`が`lineage: RetryLineageManager`を新たに保持する。

Architecture Amendment（Code Review Blocking#1・Blocking#2対応、10.2.4章）:
    - post-admission hookのdurable ack（`mark_execution_started()`の戻り値）を
      closureが捕捉し、未ack（`False`）の場合は`decide_disposition()`/`mark_terminal()`
      を一切呼ばずに`release_claim()`でCLAIMEDを解放し`RetryOutcome.SKIPPED`を返す。
      hookが例外を送出した場合（`.run()`自体が例外を送出、10.2.3章の既存fail-fast契約）
      も、durable ackがTrueに達していなければ再raise前にclaimを解放する。
    - `mark_terminal()`の戻り値（`MarkTerminalResult.acknowledged`）を必ず確認し、
      Falseの場合は`RetryOutcome.RETRIED`を返さず`RetryOutcome.SKIPPED`を返す
      （`reconcile_all()`側の16章(a)走査に解決を委ねる）。

Release 6.32での変更（docs/design/side_effect_fail_closed_human_review_safety_foundation.md
22.1f節）:
    - `.run()`呼び出し箇所へ`side_effect_execution_provenance`
      （`RetryLineageProtectedProvenance`、member_run_id未確定のpre-context）を
      追加で構築・伝播する。`member_run_id`の補完・完成形contextへの完成は
      `WorkflowEngineExecutor`のprotected factory呼び出しでのみ行われる。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from workflow_engine import (
    SOURCE_MANUAL,
    PostAdmissionHookResult,
    WorkflowEngineEvent,
    WorkflowEngineManager,
    WorkflowEngineStep,
)

from protected_operation_manifest.errors import ProtectedOperationManifestReadError
from retry_lineage import (
    RetryLineageDisposition,
    classify_step_outcome,
    compute_newly_confirmed,
    decide_disposition,
    resolve_final_disposition,
)
from side_effect_safety import ProtectedOperationContext, RetryLineageProtectedProvenance
from side_effect_safety.side_effect_execution_mode import (
    ExecutionModeFailureReasonCode,
    SideEffectExecutionModeContractError,
    _is_well_formed_attempt_ordinal,
    _is_well_formed_contract_version,
    _is_well_formed_root_run_id,
)

from .retry_request import RetryRequest
from .retry_result import RetryOutcome, RetryResult

if TYPE_CHECKING:
    from protected_operation_manifest import ManifestReaderFacade
    from retry_lineage import ClaimResult, RetryLineageManager, RetryLineageRecord
    from side_effect_safety_classifier import SideEffectSafetyClassifier


def _validate_provenance_consistency(
    provenance: "RetryLineageProtectedProvenance",
    lineage: "RetryLineageRecord",
    claim: "ClaimResult",
) -> None:
    """Release 6.32（2.2a節(1)）: Consistency Validation Boundary。

    `RetryExecutor.execute()`が構築した`RetryLineageProtectedProvenance`の
    3フィールドが、構築元の`lineage`/`claim`参照と一致することを照合する。
    新しいidentity field・理由コードは追加せず、2.1b節の既存well-formedness
    検証を先に適用してから（malformed値はconsistency照合に到達させない、
    28.-37節#5）、個別にwell-formedな値同士の一致のみを照合する。

    通常の実行では`provenance`は`lineage`/`claim`自身の値から直接構築される
    ため一致は自明に成立する——本関数は将来の実装変更（別変数の誤参照等）に
    対する構造的な防御（defense-in-depth）である。

    `lineage.side_effect_contract_version is None`（pre-6.32 legacy lineage、
    18章）の場合、6.32の判定機構自体が適用対象外であるため、本検証は行わない
    （2.3節「既存6.31以前のlegacy behaviorのまま動作する」）。
    """
    if lineage.side_effect_contract_version is None:
        return

    if not _is_well_formed_root_run_id(provenance.root_run_id):
        raise SideEffectExecutionModeContractError(
            ExecutionModeFailureReasonCode.MISSING_LINEAGE_CONTEXT,
        )
    if not _is_well_formed_attempt_ordinal(provenance.attempt_ordinal):
        raise SideEffectExecutionModeContractError(
            ExecutionModeFailureReasonCode.CONTEXT_MISMATCH,
        )
    if not _is_well_formed_contract_version(provenance.side_effect_contract_version):
        raise SideEffectExecutionModeContractError(
            ExecutionModeFailureReasonCode.CONTRACT_VERSION_MISMATCH,
        )

    if provenance.root_run_id != lineage.root_run_id:
        raise SideEffectExecutionModeContractError(
            ExecutionModeFailureReasonCode.MISSING_LINEAGE_CONTEXT,
        )
    if provenance.attempt_ordinal != claim.attempt_no:
        raise SideEffectExecutionModeContractError(
            ExecutionModeFailureReasonCode.CONTEXT_MISMATCH,
        )
    if provenance.side_effect_contract_version != lineage.side_effect_contract_version:
        raise SideEffectExecutionModeContractError(
            ExecutionModeFailureReasonCode.CONTRACT_VERSION_MISMATCH,
        )


class RetryExecutor:
    """WorkflowEngineManagerの公開APIを呼び出すだけの薄いコンポーネント。"""

    def __init__(
        self,
        workflow_engine_manager: WorkflowEngineManager,
        lineage: "RetryLineageManager",
        manifest: "ManifestReaderFacade | None" = None,
        side_effect_classifier: "SideEffectSafetyClassifier | None" = None,
    ):
        """
        manifest / side_effect_classifier（Architecture Amendment、Protected
        Operation Manifest、§10）：構造上は省略可能（デフォルトNone、既存の
        直接構築互換性のため引数自体はoptionalのまま残す）。

        Codex Final Review Blocking#1対応：ただし、legacy lineage
        （`lineage.side_effect_contract_version is None`）でのみ、既存6.31
        以前のdecide_disposition()（step-only）へのフォールバックを許容する。
        protected lineage（`side_effect_contract_version is not None`）で
        manifest/side_effect_classifierのいずれかが省略されている場合は、
        決してstep-only fallbackへ降格せず、fail-closedでHUMAN_REVIEW_REQUIRED
        へ確定する（execute()内で強制する。「composition rootが必ず両方
        構築・注入するはず」という前提のみをsafety guaranteeにしない）。
        production composition root（RetryCompositionRoot）は両方を必ず構築・
        注入する。manifestは読み取り専用のManifestReaderFacade（フルアクセスの
        ProtectedOperationManifestStoreではない、§9.5.3）。
        """
        self._engine = workflow_engine_manager
        self._lineage = lineage
        self._manifest = manifest
        self._side_effect_classifier = side_effect_classifier

    def execute(
        self, request: RetryRequest, lineage: "RetryLineageRecord", claim: "ClaimResult",
    ) -> RetryResult:
        """RetryRequest・lineage・claimをWorkflowEngineEventへ変換し、再実行を依頼する。

        Architecture Amendment（Code Review Blocking#1・Blocking#2対応、
        docs/design/retry_lineage_eligibility_durable_attempt_state.md 10.2.4章）：
        post-admission hook（mark_execution_started()）のdurable ack、および
        mark_terminal()のdurable ackを、いずれも必ず確認する。hook未ack時は
        disposition計算・mark_terminal()呼び出しを一切行わずclaimを解放し、
        SUCCEEDED/COMPLETEへ到達しないfail-closed経路を通す。
        """
        correlation_metadata = {
            "retry_lineage": {
                "root_run_id": lineage.root_run_id,
                "intended_attempt_no": str(claim.attempt_no),
                "correlation_id": claim.correlation_id or "",
            }
        }
        target_step_filter = [WorkflowEngineStep(s) for s in (claim.steps_to_execute or [])]

        # Release 6.32（22.1f節）：この段階ではmember_run_idが未確定のため、
        # 完成形のSideEffectExecutionContextではなく、root_run_id・attempt_no・
        # side_effect_contract_versionの3フィールドのみを持つ
        # RetryLineageProtectedProvenance（pre-context）を構築する。member_run_id
        # の補完はWorkflowEngineExecutorのprotected factory呼び出しでのみ行う。
        side_effect_execution_provenance = RetryLineageProtectedProvenance(
            root_run_id=lineage.root_run_id,
            attempt_ordinal=claim.attempt_no,
            side_effect_contract_version=lineage.side_effect_contract_version,
        )
        # Release 6.32（2.2a節(1)）: consistency validation boundary。
        # external I/O（self._engine.run()）より前にfail-closedする。
        _validate_provenance_consistency(side_effect_execution_provenance, lineage, claim)

        # hookのdurable ack結果は、WorkflowEngineResult側からは（hook例外時は
        # 戻り値自体が得られないため）安定して取得できない。closureが捕捉した
        # 値（durable ackそのもの）を唯一の真実として使う（10.2.4.2章）。
        hook_ack_state: dict[str, bool | None] = {"acknowledged": None}

        def post_admission_hook(run_id: str) -> PostAdmissionHookResult:
            ack = self._lineage.mark_execution_started(lineage.root_run_id, run_id, claim.owner_token)
            hook_ack_state["acknowledged"] = ack
            return PostAdmissionHookResult(acknowledged=ack)

        event = WorkflowEngineEvent(
            job_id=lineage.root_run_id,
            source=SOURCE_MANUAL,
            triggered_at=request.requested_at,
            trigger_reason=(
                f"Retry of root_run_id={lineage.root_run_id} (attempt={claim.attempt_no})."
            ),
            metadata={"retried_from": lineage.root_run_id, "attempt": claim.attempt_no},
        )
        try:
            engine_result = self._engine.run(
                event,
                dry_run=request.dry_run,
                target_step_filter=target_step_filter,
                post_admission_hook=post_admission_hook,
                correlation_metadata=correlation_metadata,
                side_effect_execution_provenance=side_effect_execution_provenance,
            )
        except Exception:
            # hook例外経路（10.2.3・10.2.4.2章）：既存のfail-fast契約どおり例外は
            # 再raiseする。durable ackが得られていない（True未達）場合のみ、
            # 再raiseの前にclaimを解放し、CLAIMEDのまま取り残さない
            # （17章crash matrix行23、16章(c)のクラッシュ経路と対をなす同期回収）。
            if not request.dry_run and hook_ack_state["acknowledged"] is not True:
                self._lineage.release_claim(lineage.root_run_id, claim.owner_token)
            raise

        if not request.dry_run and hook_ack_state["acknowledged"] is False:
            self._lineage.release_claim(lineage.root_run_id, claim.owner_token)
            return RetryResult(
                original_run_id=lineage.root_run_id,
                outcome=RetryOutcome.SKIPPED,
                attempt=claim.attempt_no or request.attempt,
                monitor_status=None,
                reason=(
                    "post-admission hook did not acknowledge (mark_execution_started() "
                    "failed); claim released back to READY_ELIGIBLE (Architecture "
                    "Amendment, Blocking#1)."
                ),
                workflow_engine_result=engine_result,
                requested_attempt_argument=request.attempt,
                authoritative_attempt_no=claim.attempt_no,
                attempt_argument_mismatch=(
                    claim.attempt_no is not None and request.attempt != claim.attempt_no
                ),
            )

        outcome = RetryOutcome.DRY_RUN if request.dry_run else RetryOutcome.RETRIED

        if not request.dry_run:
            newly_confirmed = compute_newly_confirmed(engine_result)

            # Architecture Amendment（Protected Operation Manifest、§10、primary
            # production closure）：self._manifest / self._side_effect_classifierが
            # 構築済みでside_effect_contract_versionが設定されたlineageの場合のみ、
            # SideEffectSafetyClassifier.classify() → resolve_final_disposition()
            # の実チェーンへ接続する（旧6.31 step-onlyなdecide_disposition()を
            # protected final authorityとして使わない）。
            #
            # Codex Final Review Blocking#1対応：legacy lineage
            # （side_effect_contract_version is None）の場合のみ既存6.31以前の
            # decide_disposition()へフォールバックしてよい。protected lineage
            # （side_effect_contract_version is not None）でmanifest/classifier
            # のいずれかが欠落している場合は、決してstep-only fallbackへ
            # 降格せず、fail-closedでHUMAN_REVIEW_REQUIREDへ確定する
            # （primary blocking findingの再導入を防ぐ。「composition rootが
            # 必ず依存を注入するはず」という前提のみをsafety guaranteeにしない
            # ——production class自身がここでfail-closedを強制する）。
            if lineage.side_effect_contract_version is None:
                disposition = decide_disposition(engine_result)
            elif self._manifest is None or self._side_effect_classifier is None:
                disposition = RetryLineageDisposition.HUMAN_REVIEW_REQUIRED
            else:
                step_categories = [classify_step_outcome(s) for s in engine_result.steps]
                try:
                    manifest_entries = self._manifest.list_for_attempt(
                        lineage.root_run_id, claim.attempt_no, engine_result.run_id,
                    )
                except ProtectedOperationManifestReadError:
                    disposition = RetryLineageDisposition.HUMAN_REVIEW_REQUIRED
                else:
                    operations = [
                        ProtectedOperationContext(e.operation_kind, e.effect_site, e.operation_instance_key)
                        for e in manifest_entries
                    ]
                    safety_report = self._side_effect_classifier.classify(
                        lineage.root_run_id, claim.attempt_no, engine_result.run_id, operations,
                    )
                    disposition = resolve_final_disposition(step_categories, safety_report)

            mark_result = self._lineage.mark_terminal(
                lineage.root_run_id, disposition, engine_result.run_id, newly_confirmed,
            )
            if not mark_result.acknowledged:
                return RetryResult(
                    original_run_id=lineage.root_run_id,
                    outcome=RetryOutcome.SKIPPED,
                    attempt=claim.attempt_no or request.attempt,
                    monitor_status=None,
                    reason=(
                        f"mark_terminal() did not acknowledge ({mark_result.reason}); "
                        f"deferring to reconcile_all() (Architecture Amendment, Blocking#2)."
                    ),
                    workflow_engine_result=engine_result,
                    requested_attempt_argument=request.attempt,
                    authoritative_attempt_no=claim.attempt_no,
                    attempt_argument_mismatch=(
                        claim.attempt_no is not None and request.attempt != claim.attempt_no
                    ),
                )

        return RetryResult(
            original_run_id=lineage.root_run_id,
            outcome=outcome,
            attempt=claim.attempt_no or request.attempt,
            monitor_status=None,
            reason=None,
            workflow_engine_result=engine_result,
            requested_attempt_argument=request.attempt,
            authoritative_attempt_no=claim.attempt_no,
            attempt_argument_mismatch=(
                claim.attempt_no is not None and request.attempt != claim.attempt_no
            ),
        )

    def preview(self, event: WorkflowEngineEvent, target_step_filter: list[WorkflowEngineStep] | None):
        """RetryManager._dry_run_retry()専用のread-onlyプレビュー。post_admission_hookを
        渡さない（Noneのため、mark_execution_started()は一切呼ばれない）ことで、
        Execution History・Retry Lineage双方についてzero-writeを構造的に保証する。"""
        return self._engine.run(
            event, dry_run=True, target_step_filter=target_step_filter,
            post_admission_hook=None, correlation_metadata=None,
        )
