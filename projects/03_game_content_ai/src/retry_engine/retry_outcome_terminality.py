"""
Retry Outcome Terminality（v4.4.0）

RetryOutcomeTerminality:   各Outcomeの性質を表すEnum（TERMINAL / TRANSIENT）
RetryCleanupReason:        Cleanup判定のための、判定起源を表す軽量な識別子
RETRY_OUTCOME_TERMINALITY: RetryCleanupReasonごとのTerminal/Transient分類表
classify_reason():         RetryQueueUpdateDecisionから起源（RetryCleanupReason）を導出する
classify_terminality():    RetryCleanupReasonからTerminal/Transientを導出する

設計方針:
    - Terminal（終端状態）：判定条件そのものが将来変化する見込みがなく、同じrun_idに
      対して同じ判定を再実行しても結果が変わらないと合理的に言える状態。
    - Transient（一時状態）：判定条件（設定値・外部システムの状態等）が将来変化しうる
      状態。現時点ではCleanup対象外と判定されても、条件が変われば異なる結果になりうる。
    - 【権威範囲の限定】本モジュールは v4.4.0 の RetryQueueTerminalCleanupDecider に
      対してのみ Single Source of Truth（唯一の判断基準）として機能する。v4.1.0
      RetryQueueUpdateDecider・v4.2.0 RetryQueueRemovalExecutor・v4.3.0
      RetryQueueCleanupDecider はいずれもゼロ改修方針のため本モジュールを参照せず、
      COMPLETE / FAIL / SKIPPEDの判定ロジックを引き続き各ファイル内に個別に保持
      している。本モジュールのCOMPLETE/FAIL/SKIPPEDに対する分類（いずれもTERMINAL）
      は、既存コンポーネントが実際にどう振る舞うかの参考値として記載しているに
      過ぎず、それらのコンポーネントの実際の挙動を左右するものではない
      （docs/design/retry_queue_notfound_disabled_cleanup_foundation.md
      2章・3.2節、Architecture Review 12.1節 Recommendation 1）。
    - Stateless。RETRY_OUTCOME_TERMINALITYはモジュールレベルの不変な辞書であり、
      実行時に書き換えられることを想定しない。
    - 拡張性：将来RetryOutcomeに新しい値が追加された場合、classify_reason()に対応する
      RetryCleanupReasonを1行追加したうえでRETRY_OUTCOME_TERMINALITYにも1行追加すれば
      v4.4.0新規Deciderの Cleanup方針が定まる。RetryQueueTerminalCleanupDecider自体の
      コード変更は不要（同Deciderはclassify_reason() / classify_terminality()への委譲の
      みで完結しているため）。
    - （v5.6.0 教訓）classify_reason()は「明示列挙＋raise ValueError」という網羅チェック
      方式であり、else方式（未知の値を自動的に安全側へ倒す方式）ではない。そのため、
      RetryOutcomeへ新しい値を追加した際にRetryCleanupReason・classify_reason()・
      RETRY_OUTCOME_TERMINALITYのいずれか一つでも追従を忘れると、その値がNOOPとして
      RetryQueueTerminalCleanupDeciderに渡された際にValueErrorでrun_once()全体が
      クラッシュする（v5.6.0 Architecture ReviewでRetryOutcome.DRY_RUN追加時に発見）。
      【恒久ルール】RetryOutcomeへ新しい値を追加する場合は、リポジトリ全体で
      RetryOutcomeの参照箇所を確認し、明示列挙・例外送出・永続化・表示・シリアライズへの
      影響をレビューすること（docs/design/retry_runtime_safe_dry_run_foundation.md 参照）。
    - NOT_FOUNDの分類（TERMINAL）の見直し条件：
      (1) enqueue_retry()にExecution Historyとの参照整合性チェックが追加された場合
          （この場合はTerminalの結論がむしろ強化される）
      (2) 「Workflow Engineがまだ実行していないrun_id」を正当なRetry候補として扱う
          新機能（先行enqueue・予約実行等）が追加された場合（この場合はTransientへの
          見直しが必要になりうる）
      Composition Root（Workflow MonitorのFAILED/TIMEOUT判定を自動でRetry Queueへ
      enqueueする仕組み）の整備自体は、上記(1)(2)のいずれにも該当しないため、
      NOT_FOUNDの分類を見直す契機とはしない（同設計書4.3節）。
    - DISABLEDの分類（TRANSIENT）は、RetryQueueManager（v3.1.0）がメモリ上の
      dictのみで構成され、Queue永続化が本Release時点でもNon-Goalのままである
      （プロセス再起動でQueueがリセットされる）ことを前提とする。将来Queue永続化が
      実装された場合はこの前提が崩れるため、Queue永続化のCharter作成時に本分類の
      再評価が必要になる（同設計書9章 Future Extension）。
"""
from __future__ import annotations

from enum import Enum

from .retry_queue_update_decider import RetryQueueUpdateDecision, RetryQueueUpdateOutcome
from .retry_result import RetryOutcome


class RetryOutcomeTerminality(Enum):
    """各Outcomeが終端状態（TERMINAL）か一時状態（TRANSIENT）かを表す。"""

    TERMINAL = "terminal"
    TRANSIENT = "transient"


class RetryCleanupReason(Enum):
    """Cleanup判定のための、RetryQueueUpdateDecisionの判定起源を表す軽量な識別子。"""

    COMPLETE = "complete"
    FAIL = "fail"
    SKIPPED = "skipped"
    NOT_FOUND = "not_found"
    DISABLED = "disabled"
    DRY_RUN = "dry_run"  # v5.6.0追加


RETRY_OUTCOME_TERMINALITY: dict[RetryCleanupReason, RetryOutcomeTerminality] = {
    RetryCleanupReason.COMPLETE: RetryOutcomeTerminality.TERMINAL,
    RetryCleanupReason.FAIL: RetryOutcomeTerminality.TERMINAL,
    RetryCleanupReason.SKIPPED: RetryOutcomeTerminality.TERMINAL,
    RetryCleanupReason.NOT_FOUND: RetryOutcomeTerminality.TERMINAL,
    RetryCleanupReason.DISABLED: RetryOutcomeTerminality.TRANSIENT,
    # DRY_RUNは呼び出し時のdry_runフラグという一時的な条件に由来し、同じrun_idを
    # 次回dry_run=Falseで呼べば結果が変わりうるためTRANSIENT（KEEP）に分類する
    # （v5.6.0。同じrun_idに対するdry_run結果でQueue候補が誤って消えないようにするため）。
    RetryCleanupReason.DRY_RUN: RetryOutcomeTerminality.TRANSIENT,
}


def classify_reason(update_decision: RetryQueueUpdateDecision) -> RetryCleanupReason:
    """RetryQueueUpdateDecisionから、Cleanup判定のための起源（RetryCleanupReason）を導出する。"""
    if update_decision.outcome == RetryQueueUpdateOutcome.COMPLETE:
        return RetryCleanupReason.COMPLETE
    if update_decision.outcome == RetryQueueUpdateOutcome.FAIL:
        return RetryCleanupReason.FAIL

    retry_outcome = update_decision.execution_result.retry_result.outcome
    if retry_outcome == RetryOutcome.SKIPPED:
        return RetryCleanupReason.SKIPPED
    if retry_outcome == RetryOutcome.NOT_FOUND:
        return RetryCleanupReason.NOT_FOUND
    if retry_outcome == RetryOutcome.DISABLED:
        return RetryCleanupReason.DISABLED
    if retry_outcome == RetryOutcome.DRY_RUN:
        return RetryCleanupReason.DRY_RUN

    raise ValueError(f"unexpected retry_outcome for NOOP decision: {retry_outcome!r}")


def classify_terminality(reason: RetryCleanupReason) -> RetryOutcomeTerminality:
    """RetryCleanupReasonから、RETRY_OUTCOME_TERMINALITY分類表を参照してTerminal/Transientを返す。"""
    return RETRY_OUTCOME_TERMINALITY[reason]
