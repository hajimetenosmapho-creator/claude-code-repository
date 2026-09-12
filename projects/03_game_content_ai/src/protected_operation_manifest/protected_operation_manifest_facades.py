"""
Protected Operation Manifest Runtime Facades（Release 6.32 Architecture Amendment、
Round 9・Round 10設計）

Source of Truth: docs/design/
side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md 9.5.3章

concrete facadeでrawストアをラップし、公開メソッド上に危険なメソッド
（`create_for_attempt`）への参照を持たない。composition root
（`RetryCompositionRoot`）が、`RetryExecutor`・呼び出し箇所A/B/Cへは
これらのfacadeのみを配線し、フルアクセスの`ProtectedOperationManifestStore`は
`RetryLineageManager`のみへ配線する。

Contract（Codex Round 10 Minor#1指摘により正確化）：
    - rawストアをpublic／non-mangled属性としてfacadeから露出しない。
    - 通常のconsumer API surface（本ファイルの2クラスが公開するメソッド群）は
      authority-bearing method（create_for_attempt等）を一切持たない。
    - 通常のproduction wiring（composition rootの配線経路）からは、
      create/admin mutationへ到達する経路が存在しない。
    - Python reflection・vars()・malicious arbitrary-code introspection
      （name-mangled属性への意図的アクセスを含む）はthreat modelの対象外。
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .protected_operation_manifest_record import ManifestEntry
    from .protected_operation_manifest_store import ProtectedOperationManifestStore, RegisterResult


class ManifestReaderFacade:
    """RetryExecutor（同期terminalization）・RetryLineageManager
    （crash/restart reconciliation）へ渡す。list_for_attempt()のみを公開する。"""

    def __init__(self, store: "ProtectedOperationManifestStore") -> None:
        self.__store = store  # name-mangled。通常のattribute access・vars()からは
                               # 見えないが、reflectionによる意図的迂回は脅威モデル外。

    def list_for_attempt(
        self, root_run_id: str, attempt_ordinal: int, expected_member_run_id: str,
    ) -> "tuple[ManifestEntry, ...]":
        return self.__store.list_for_attempt(root_run_id, attempt_ordinal, expected_member_run_id)


class ManifestRegistrarFacade:
    """呼び出し箇所A/B/C（wordpress_output.py・main.py・ai_publish_service.py）へ
    渡す。register()のみを公開する。rawストアの非露出契約はManifestReaderFacade
    と同一。"""

    def __init__(self, store: "ProtectedOperationManifestStore") -> None:
        self.__store = store

    def register(
        self, root_run_id: str, attempt_ordinal: int, member_run_id: str, entry: "ManifestEntry",
    ) -> "RegisterResult":
        return self.__store.register(root_run_id, attempt_ordinal, member_run_id, entry)
