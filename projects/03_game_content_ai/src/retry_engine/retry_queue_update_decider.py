"""
Retry Queue Update Decider（v4.1.0）

RetryQueueUpdateOutcome: RetryExecutionResult 1件に対する判定結果の種別
RetryQueueUpdateDecision: 判定結果を保持する軽量データ
RetryQueueUpdateDecider:  RetryExecutionResult のリストを受け取り、各要素について
                          対応するRetry Queue項目の更新先状態を判定するコンポーネント

設計方針:
    - Queueへの書き込みは一切行わない。RetryQueueManager / NullRetryQueueManager への
      参照を持たない（コンストラクタ引数にも存在しない）。判定のみを行う
      （docs/design/retry_queue_update_foundation.md 3章・10章）。
    - Stateless。RetryExecutionResult を受け取り、判定結果を返すだけの
      純粋関数的なメソッドのみを持つ。
    - RetryQueueStatus（retry_queue の公開シンボル）は型として参照するが、
      RetryQueueManager 等の操作系シンボルは一切importしない
      （同設計書4章の判定方針を参照）。
    - 判定は「再実行が実際に実行されたか」（RetryResult.outcome == RETRIED）を
      唯一の分岐点とする。SKIPPED / NOT_FOUND / DISABLED はいずれも
      「Queueの状態を変える根拠がない」という共通の性質を持つため、NOOP という
      単一の安全側の結果に統一する（同設計書4章・14章 Design Decision #2）。
      とりわけ SKIPPED（RetryPolicy が再試行上限到達等で対象外と判定したケース）は
      NOOP のまま次Releaseまで Queue に滞留し続ける可能性がある。この滞留の扱いは
      本Foundationの対象外とし、Release 4.2「Retry Queue Removal」の検討事項として
      申し送る（同設計書12章 Future Extension・16.3節 Recommendation 2）。

Release 6.31での変更（docs/design/retry_lineage_eligibility_durable_attempt_state.md
9.8.1.3・11.5章）:
    - RETRIEDの場合のCOMPLETE/FAIL判定を、`workflow_engine_result.overall_success`
      （SILENT_NO_ACTIONなstepもsuccess=Trueのため、NOT_ACTIONED dispositionを
      誤ってCOMPLETEに倒してしまう）から、`retry_lineage.decide_disposition()`
      （lineageのmark_terminal()が実際に使うのと同一の判定ロジック）へ変更した。
      `SUCCEEDED`→COMPLETE、`FAILED`／`NOT_ACTIONED`→FAIL（いずれもlineage側では
      retryableとして扱われるため、Queue側もCOMPLETEにはしない）。

Release 6.32での変更（docs/design/side_effect_fail_closed_human_review_safety_foundation.md
22.4・22.4a章、28.-18・28.-8節。§29 Architecture Classification Register #1・#4が
Normative Contractとして分類。HRR専用ではなく、SUCCEEDED/FAILED/NOT_ACTIONED/
HUMAN_REVIEW_REQUIREDのすべてを対象とする汎用のLineage-Authoritative Disposition
Input Contract）:
    - `decide()`の第2引数を、独立再計算のみに基づく暗黙のOptional推測ではなく、
      discriminated union `RetryQueueDecisionInput`
      （`LineageAuthoritativeDispositionInput` | `LegacyQueueDecisionInput`）を
      必須引数として受け取るよう変更した。6.32 contract対象lineage
      （side_effect_contract_version is not None、18章）では、mark_terminal()が
      確定させた権威あるterminal_dispositionをそのまま使い、
      decide_disposition()による独立再計算（優先順位1・24章の安全性保証を
      失いうる）を行わない。pre-6.32 legacy lineageでは従来どおり
      decide_disposition()ベースの判定を維持する（6.31 semantics無変更）。
    - `HUMAN_REVIEW_REQUIRED`を含むterminal_dispositionは、既存の
      `RetryQueueUpdateOutcome.FAIL` / `RetryQueueStatus.FAILED`へそのまま合流する。
      新しいoutcome/status値は追加しない（HRR専用のQueue状態は追加しない、22.4節）。
      `RetryQueueUpdateDecider`はretry eligibility・authorization・dispatchの
      authorityではなく、既に実行された再試行結果に対するpost-hoc bookkeeping
      のみを担う（17.3節）。HRR authorized retry自体の認可・dispatchは
      composition層の`retry_after_human_review()`（17.3節）が
      queue/scheduler非経由で直接行う——本節の変更はこれと独立であり、
      矛盾しない。
    - `decide_all()`を、typed `RetryQueueDecisionRequest`の列を受け取るbatch API
      へ改修した（旧1引数`decide_all(execution_results)`は残さない、22.1d節）。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Sequence

from retry_queue import RetryQueueStatus

from retry_lineage import (
    ContractVersionEvidence,
    RetryLineageDisposition,
    classify_contract_version_evidence,
    decide_disposition,
)

from .retry_execution_coordinator import RetryExecutionResult
from .retry_result import RetryOutcome

if TYPE_CHECKING:
    from retry_lineage import RetryLineageManager, RetryLineageRecord


class RetryQueueUpdateOutcome(Enum):
    COMPLETE = "complete"  # 再実行成功 → RetryQueueStatus.COMPLETED
    FAIL = "fail"          # 再実行失敗 → RetryQueueStatus.FAILED
    NOOP = "noop"          # 再実行が行われていない → 更新しない


@dataclass(frozen=True)
class RetryQueueUpdateDecision:
    """1件のRetryExecutionResultに対する判定結果を保持する軽量データ。"""

    execution_result: RetryExecutionResult
    outcome: RetryQueueUpdateOutcome
    target_status: RetryQueueStatus | None
    reason: str


class RetryQueueUpdateContractError(Exception):
    """`queue_decision_input`が未知の型である場合、または
    `build_queue_decision_input()`/`build_retry_queue_decision_requests()`が
    lineageのcontract-version異常・権威あるterminal_disposition欠落を検出した
    場合に送出する（22.4・22.4a節）。legacyへもprotectedへも推測しない
    fail-closed規律の一部（9.6節と同型の実装契約違反例外）。"""


@dataclass(frozen=True)
class LineageAuthoritativeDispositionInput:
    """6.32 contract対象lineage用（side_effect_contract_version is not None、18章）。
    mark_terminal()が確定させた権威あるterminal_dispositionを必須で保持する。
    このフィールドが欠落した状態は型として存在しない。"""

    terminal_disposition: RetryLineageDisposition


@dataclass(frozen=True)
class LegacyQueueDecisionInput:
    """pre-6.32 legacy lineage用（side_effect_contract_version is None、18章）。
    フィールドを持たない——「legacyとして扱う」という選択自体を型として明示する。
    decide_disposition()による従来のstep-only再計算を選択したことの直接的な証跡。"""


RetryQueueDecisionInput = "LineageAuthoritativeDispositionInput | LegacyQueueDecisionInput"


def build_queue_decision_input(record: "RetryLineageRecord") -> "RetryQueueDecisionInput":
    """単一lineageのRetryLineageRecordからRetryQueueDecisionInputを構築する唯一の
    関数（22.4節）。contract versionの妥当性判定は
    `retry_lineage.classify_contract_version_evidence()`のみを唯一のpredicateと
    して使う——値の欠落からの推測はここでも行わない。"""
    evidence = classify_contract_version_evidence(record)
    if evidence == ContractVersionEvidence.INVALID:
        # invalid contract-version evidence：legacyへ推測せずcontract failureとする
        # （18.1節と同一のfail-closed規律）。
        raise RetryQueueUpdateContractError(
            f"lineage {record.root_run_id!r} has invalid side_effect_contract_version="
            f"{record.side_effect_contract_version!r}; refusing to infer legacy behavior."
        )
    if evidence == ContractVersionEvidence.PROTECTED:
        if record.terminal_disposition is None:
            # 6.32 contract対象lineageのはずが、この呼び出し時点でmark_terminal()が
            # 未確定——15.1〜15.2節の契約上発生しないはずだが、発生した場合は
            # legacyへ推測せずcontract failureとしてfail-closedする。
            raise RetryQueueUpdateContractError(
                "6.32 contract lineage reached queue-update without an authoritative "
                "terminal_disposition; refusing to infer legacy behavior."
            )
        return LineageAuthoritativeDispositionInput(terminal_disposition=record.terminal_disposition)
    return LegacyQueueDecisionInput()  # evidence == LEGACY、明示的にlegacy経路を選択（18章）


@dataclass(frozen=True)
class RetryQueueDecisionRequest:
    """decide_all()の各要素。execution_resultとdecision_inputを単一の型でbindする
    ことで、2つのparallel listをインデックスで対応付ける設計（順序不一致・要素数
    不一致によりmember/run identityが取り違えられるリスクを持つ）を構造的に
    排除する（22.4a節）。"""

    execution_result: RetryExecutionResult
    decision_input: "RetryQueueDecisionInput"  # 22.4節のdiscriminated union
                                                 # （LineageAuthoritativeDispositionInput
                                                 #  | LegacyQueueDecisionInput）


def build_retry_queue_decision_requests(
    execution_results: "Sequence[RetryExecutionResult]",
    lineage: "RetryLineageManager",
) -> list[RetryQueueDecisionRequest]:
    """RetryManager.decide_retry_queue_updates()が、取得済みのexecution_results
    から構築する唯一の関数（22.4a節）。lineage引数はRetryManagerがコンストラクタで
    保持するself._lineageをそのまま渡す。parallel listのインデックス対応には
    一切依存しない。"""
    requests: list[RetryQueueDecisionRequest] = []
    for execution_result in execution_results:
        retry_result = execution_result.retry_result

        if retry_result.workflow_engine_result is None:
            # retry_result.outcome != RETRIED（SKIPPED/NOT_FOUND/DISABLED/DRY_RUN）
            # の場合、member_run_id自体が存在しない。decide()はこのケースを
            # queue_decision_inputを一切参照せずNOOPへ倒す（22.4節decide()の
            # 最初の分岐、retry_result.outcome != RetryOutcome.RETRIEDチェック）
            # ため、lineage lookupを行わず安全なプレースホルダを渡す
            # （decision_inputの値はこの経路の判定結果に一切影響しない）。
            requests.append(RetryQueueDecisionRequest(
                execution_result=execution_result,
                decision_input=LegacyQueueDecisionInput(),
            ))
            continue

        member_run_id = retry_result.workflow_engine_result.run_id
        root_run_id = lineage.find_by_member_run_id(member_run_id)  # 既存API、str | None

        if root_run_id is None:
            # 正式なpre-6.32/legacy：いかなるlineageのmemberでもないrun_idは、
            # legacy execution（Retry Lineage契約外）として明示的に
            # LegacyQueueDecisionInputを選択する（18章、22.4節と同一原則）。
            requests.append(RetryQueueDecisionRequest(
                execution_result=execution_result,
                decision_input=LegacyQueueDecisionInput(),
            ))
            continue

        record = lineage.peek(root_run_id)  # 既存API、read-only
        if record is None:
            # find_by_member_run_id()がroot_run_idを解決した直後にpeek()がNoneを
            # 返すことは、一意性前提（lineage作成時グローバルチェック＋UUID4
            # 再利用なし）がdurable data corruption等で崩れた場合にのみ発生
            # しうる。legacyへ推測せずcontract failureとする（No Automatic
            # Repair、26章と同型の規律）。
            raise RetryQueueUpdateContractError(
                f"find_by_member_run_id({member_run_id!r}) resolved root_run_id="
                f"{root_run_id!r}, but peek({root_run_id!r}) returned None; "
                "refusing to infer legacy behavior."
            )

        requests.append(RetryQueueDecisionRequest(
            execution_result=execution_result,
            decision_input=build_queue_decision_input(record),
        ))
    return requests


class RetryQueueUpdateDecider:
    """RetryExecutionResultを対象に、対応するQueue項目の更新先状態を判定するコンポーネント。"""

    def decide_all(
        self, requests: "Sequence[RetryQueueDecisionRequest]"
    ) -> list[RetryQueueUpdateDecision]:
        """各requestについて、既存のdecide()相当のロジック（22.4節）を
        request.execution_result・request.decision_inputへ適用する。parallel
        listの単純zipは行わない——各requestは自己完結した単一の単位として
        扱う（22.4a節）。"""
        return [
            self.decide(request.execution_result, request.decision_input)
            for request in requests
        ]

    def decide(
        self,
        execution_result: RetryExecutionResult,
        queue_decision_input: "RetryQueueDecisionInput",
    ) -> RetryQueueUpdateDecision:
        """1件のRetryExecutionResultについて、更新先のRetryQueueStatusを判定する。

        queue_decision_inputのisinstance分岐のみで経路を決定する。Optional値の
        有無からcontract種別を推測するロジックは持たない（discriminated union
        によりその種の推測が構造的に不要になった、2章と同型の規律、22.4節）。
        """
        retry_result = execution_result.retry_result

        if retry_result.outcome != RetryOutcome.RETRIED:
            # SKIPPED / NOT_FOUND / DISABLED / DRY_RUN: 再実行が行われていない
            # ため、Queueの更新先を確定させない（NOOP）。
            return RetryQueueUpdateDecision(
                execution_result=execution_result,
                outcome=RetryQueueUpdateOutcome.NOOP,
                target_status=None,
                reason=f"no retry was executed (retry_result.outcome={retry_result.outcome.value}).",
            )

        if isinstance(queue_decision_input, LineageAuthoritativeDispositionInput):
            disposition = queue_decision_input.terminal_disposition  # lineageのmark_terminal()確定値（権威）
        elif isinstance(queue_decision_input, LegacyQueueDecisionInput):
            disposition = decide_disposition(retry_result.workflow_engine_result)  # legacy、無変更
        else:
            raise RetryQueueUpdateContractError(
                f"unknown queue_decision_input type: {type(queue_decision_input)!r}"
            )

        if disposition == RetryLineageDisposition.SUCCEEDED:
            return RetryQueueUpdateDecision(
                execution_result=execution_result,
                outcome=RetryQueueUpdateOutcome.COMPLETE,
                target_status=RetryQueueStatus.COMPLETED,
                reason="retry was executed and disposition==SUCCEEDED.",
            )
        return RetryQueueUpdateDecision(  # FAILED / NOT_ACTIONED / HUMAN_REVIEW_REQUIRED、
            # いずれも既存のFAIL outcomeへ合流する（新しいoutcome値は追加しない）。
            execution_result=execution_result,
            outcome=RetryQueueUpdateOutcome.FAIL,
            target_status=RetryQueueStatus.FAILED,
            reason=f"retry was executed but disposition=={disposition.value}.",
        )
