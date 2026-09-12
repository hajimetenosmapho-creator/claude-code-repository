"""
Commit-Aware Lock Helper（Release 6.32、9.9.4.2〜9.9.4.3節）

`_run_with_commit_aware_lock()`はlock取得・body実行・lock解放を統一的に扱う。
durable semantic ACK確定後（`commit_state["committed"] = True`設定後）に
発生した後続処理（lock解放・戻り値構築等）の失敗を、durable commit自体の
failureへ転嫁しない（ACK Determinism）。

`MediaUploadSafetyCoordinator`（side_effect_safety）・`WordPressDraftStateStore`
（wordpress_draft_state）の双方がこの単一ヘルパーを共有利用する（9.8・9.9.4節）。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from .side_effect_operation_identity import SideEffectOperationIdentity


def now_utc_iso() -> str:
    """canonical UTC ISO8601文字列を生成する。"""
    return datetime.now(timezone.utc).isoformat()


class CleanupFailureReasonCode(Enum):
    """cleanup_diagnosticsのreason_codeとして使う、closed-setな固定値（9.9.4.2節）。"""

    LOCK_RELEASE_FAILED = "lock_release_failed"
    POST_COMMIT_BODY_EXCEPTION = "post_commit_body_exception"
    RECOVERY_VALIDATION_FAILED = "recovery_validation_failed"


@dataclass(frozen=True)
class CleanupDiagnostic:
    """post-commit cleanup失敗のsecret-safeな診断情報（9.9.4.2・9.9.4.5節）。
    exception message本文・URL・credentials/token・API応答本文・request payload・
    記事本文・raw tracebackのいずれも保持しない。"""

    reason_code: CleanupFailureReasonCode
    exception_type: str
    operation_kind: str | None
    effect_site: str | None
    occurred_at: str


@dataclass(frozen=True)
class CommitAwareResult:
    """semantic resultとcleanup resultを分離する（9.9.4.2節）。"""

    acknowledged: bool
    value: object
    cleanup_diagnostics: tuple[CleanupDiagnostic, ...]


class CommitAwareLockContractError(Exception):
    """bodyがcommit_state["committed"]=Trueを設定せずに正常returnした場合に
    送出する（9.9.4.3節）。外部要因（I/O失敗等）ではなく、呼び出し元の実装契約
    違反（バグ）を示す。"""


def _try_release_ignoring_result(lock) -> None:
    """pre-commit failure・process-control例外経路でのcleanup。lock.release()自体の
    失敗は、元の例外の報告を妨げない。Exceptionの範囲でのみ捕捉する。"""
    try:
        lock.release()
    except Exception:
        pass


def _build_cleanup_diagnostic(
    reason_code: CleanupFailureReasonCode,
    error: BaseException,
    identity: SideEffectOperationIdentity | None,
) -> "CleanupDiagnostic | None":
    """secret-safeな診断情報を構築する（9.9.4.3・9.9.4.5節）。個々のフィールド計算が
    失敗しても例外を外部へ伝播させない。構築自体が失敗した場合は診断情報なし
    （`None`）を返す。"""
    try:
        exception_type = type(error).__name__
    except Exception:
        exception_type = "UnknownExceptionType"
    try:
        occurred_at = now_utc_iso()
    except Exception:
        occurred_at = ""
    try:
        operation_kind = identity.operation_kind.value if identity is not None else None
    except Exception:
        operation_kind = None
    try:
        effect_site = identity.effect_site.value if identity is not None else None
    except Exception:
        effect_site = None
    try:
        return CleanupDiagnostic(
            reason_code=reason_code,
            exception_type=exception_type,
            operation_kind=operation_kind,
            effect_site=effect_site,
            occurred_at=occurred_at,
        )
    except Exception:
        return None


def _try_release_capturing_diagnostic(
    lock, identity: SideEffectOperationIdentity | None,
) -> "CleanupDiagnostic | None":
    """post-commit成功経路でのcleanup。lock.release()の失敗はCleanupDiagnosticとして
    記録するのみで、semantic successを覆さない。"""
    try:
        lock.release()
        return None
    except Exception as release_error:
        return _build_cleanup_diagnostic(
            CleanupFailureReasonCode.LOCK_RELEASE_FAILED, release_error, identity,
        )


def _run_with_commit_aware_lock(
    lock, identity: SideEffectOperationIdentity | None, body: Callable[[dict], object],
) -> CommitAwareResult:
    """lock取得・body実行・lock解放を統一的に扱う（9.9.4.3節）。

    契約：
      - lock.acquire()が失敗した場合、bodyは一切実行されない（fail-closed）。
      - bodyはcommit_state（{"committed": bool, "value": object|None}）を受け取る。
        semantic commit pointに到達した時点で直ちにcommitted=Trueを設定し、その後に
        戻り値を構築してcommit_state["value"]へ格納する（呼び出し元の実装契約）。
      - bodyがcommitted=True設定後に通常のExceptionを送出した場合：
        commit_state["value"]を用いてacknowledged=TrueのCommitAwareResultを返す。
      - bodyがcommitted=Trueに到達する前にExceptionを送出した場合（pre-commit
        failure）：cleanupは試行するが、元のbody例外をそのまま送出する。
      - bodyがExceptionではないBaseExceptionを送出した場合：committed状態に関わらず
        cleanupをbest-effortで試行した上で、必ずそのまま再送出する。
      - bodyが正常returnしたがcommitted=Trueが設定されていない場合、明示的な例外
        （`assert`に依存しない、`-O`/PYTHONOPTIMIZE耐性）を送出する。
    """
    lock.acquire()
    commit_state: dict = {"committed": False, "value": None}
    try:
        result = body(commit_state)
    except Exception as exc:
        if commit_state["committed"]:
            body_diag = _build_cleanup_diagnostic(
                CleanupFailureReasonCode.POST_COMMIT_BODY_EXCEPTION, exc, identity,
            )
            release_diag = _try_release_capturing_diagnostic(lock, identity)
            diagnostics = tuple(d for d in (body_diag, release_diag) if d is not None)
            return CommitAwareResult(
                acknowledged=True, value=commit_state["value"], cleanup_diagnostics=diagnostics,
            )
        _try_release_ignoring_result(lock)
        raise
    except BaseException:
        _try_release_ignoring_result(lock)
        raise

    if not commit_state["committed"]:
        _try_release_ignoring_result(lock)
        raise CommitAwareLockContractError(
            "body returned normally without setting committed=True; "
            "this is an implementation contract violation"
        )

    release_diag = _try_release_capturing_diagnostic(lock, identity)
    diagnostics = (release_diag,) if release_diag is not None else ()
    return CommitAwareResult(acknowledged=True, value=result, cleanup_diagnostics=diagnostics)
