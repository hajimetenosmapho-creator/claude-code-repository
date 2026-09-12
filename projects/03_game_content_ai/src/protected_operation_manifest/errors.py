"""
Protected Operation Manifest 例外定義（Release 6.32 Architecture Amendment、Round 9設計）

Source of Truth: docs/design/
side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md 8章
"""
from __future__ import annotations


class ProtectedOperationManifestError(Exception):
    """パッケージ全体の共通祖先（分類目的のみ。catchには通常使わない）。"""


class ProtectedOperationManifestReadError(ProtectedOperationManifestError):
    """list_for_attempt()（読み取り経路）が送出しうる例外の共通基底。
    terminalization（RetryExecutor.execute() / _reconcile_all_locked()）はこれをcatchする。"""


class ProtectedOperationManifestNotFoundError(ProtectedOperationManifestReadError):
    """レコードが存在しない。admissionが正しく完了していれば本来あり得ない状態
    ——検出された場合は実装バグまたは想定外の破損として扱う。"""


class ProtectedOperationManifestContractViolationError(ProtectedOperationManifestReadError):
    """schema不正・member_run_id不一致・不明なenum値等の破損。Round 9追加：
    create_for_attempt()が同一キー（root_run_id・attempt_ordinal・member_run_idの
    3要素）に対する既存レコードを発見した場合（正常経路では構造的に発生し得ない）
    にもこの例外を送出する——create専用の別exceptionは設けない。呼び出し元は
    catchせず、既存のfail-fast契約へ伝播させる（rebindフォールバックという分岐は
    存在しない）。"""


class ProtectedOperationManifestIOError(ProtectedOperationManifestReadError):
    """真のfilesystem I/O failure。"""
