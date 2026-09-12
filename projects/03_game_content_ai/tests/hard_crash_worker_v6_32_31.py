"""
Hard-crash worker process（Release 6.32、§18 test#22 + test#25 evidence専用）

Source of Truth: docs/design/
side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md
§9.2a（crash境界ごとの残存lock/durable state matrix）・§18 test#22・
Hard-Crash Test Methodology（test#25、Category B）

このファイルは単体のtestではない（`test_`始まりではないため pytest には収集
されない）。tests/test_e2e_v6_32_31_claimed_orphan_lock_state_hard_crash.py
から`subprocess.run([sys.executable, __file__, ...])`として起動される
test-owned子プロセスヘルパーであり、以下の目的にのみ使う：

    通常のPython例外catchでは`with`文の`__exit__`（lock解放処理）が
    必ず実行されてしまい、「lock fileが残存する」という主張を正しく
    検証できない（Round 9 Hard-Crash Test Methodology）。本ヘルパーは
    `os._exit()`による真のhard terminationで__exit__を一切実行させず、
    §9.2a matrixが主張するB0〜B4境界ごとの残存lock/durable state組み合わせを
    実際に再現する。

production code（RetryLineageManager・ProtectedOperationManifestStore等）は
一切変更しない——本ファイルがmonkeypatchするのは、自分自身がこのプロセス内で
新規構築したstore/manifestインスタンスのメソッドのみである（既存クラス定義
そのものは触れない）。network / WordPress / 外部I/Oは一切呼び出さない。
呼び出し元（親テストプロセス）とは、コマンドライン引数とtmp_root配下の
ファイルシステム状態のみを通じてやり取りする。

引数: <boundary> <tmp_root> <root_run_id> <member_run_id>
    boundary: B0 | B1 | B2 | B3 | B4

正常な（意図した）終了は必ず os._exit(1)。それ以外の終了コード（2/3/4）は
テストハーネス自体の前提が崩れたことを示す（§9.2aのmatrix自体の異常ではない）。
"""
from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent
SRC_DIR = PROJECT_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

from protected_operation_manifest import JsonProtectedOperationManifestStore  # noqa: E402
from retry_lineage import (  # noqa: E402
    JsonRetryLineageStore,
    RetryExecutionLock,
    RetryLineageConfig,
    RetryLineageManager,
)
from workflow_monitor import WorkflowMonitorRecord, WorkflowMonitorStatus  # noqa: E402


class _FixedPolicy:
    """本ワーカー専用の最小限のExplainableRetryPolicy互換オブジェクト。"""

    target_statuses = frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT})

    @property
    def max_attempts(self) -> int:
        return 5

    def should_retry(self, monitor_status: WorkflowMonitorStatus, attempt: int) -> bool:
        return monitor_status in self.target_statuses and attempt < self.max_attempts


def _monitor_record(run_id: str) -> WorkflowMonitorRecord:
    now = datetime.now()
    return WorkflowMonitorRecord(
        run_id=run_id, workflow_name="workflow_engine", monitor_status=WorkflowMonitorStatus.FAILED,
        source_status="FAILED", source="manual", job_id="job-1",
        started_at=now, finished_at=now, elapsed_seconds=1.0, reason=None, steps=[],
    )


def main() -> None:
    boundary, tmp_root_str, root_run_id, member_run_id = sys.argv[1:5]
    tmp_root = Path(tmp_root_str)

    lineage_config = RetryLineageConfig(enabled=True, lineage_dir=tmp_root / "lineage")
    lineage_store = JsonRetryLineageStore(lineage_config.store_dir)
    manifest_store = JsonProtectedOperationManifestStore(base_dir=tmp_root / "manifest")
    lineage = RetryLineageManager(
        store=lineage_store, config=lineage_config, policy=_FixedPolicy(), manifest=manifest_store,
    )

    created = lineage.create_new_lineage(root_run_id, _monitor_record(root_run_id))
    if created.admission_rejected:
        sys.exit(2)  # テストharness前提の破綻（§9.2a matrix自体の対象外）

    # RetryManager.retry()実運用と同じく、以後の全操作をRetryExecutionLockの
    # 内側で行う（9.2a章：retry()呼び出し全体を通じて保持）。正常終了時のみ
    # __exit__でreleaseされる——各境界のcrashでは意図的にreleaseさせない。
    lock = RetryExecutionLock(lineage_config.execution_lock_path)
    lock.acquire()

    claim_result = lineage.claim(root_run_id)
    if not claim_result.acknowledged:
        sys.exit(3)

    if boundary == "B0":
        # claim()直後・mark_execution_started()呼び出し前。
        os._exit(1)

    elif boundary == "B1":
        # with self._store_lock():進入直後〜create_for_attempt()呼び出し前。
        manifest_store.create_for_attempt = lambda *a, **kw: os._exit(1)
        lineage.mark_execution_started(root_run_id, member_run_id, claim_result.owner_token)
        os._exit(1)  # 到達しないはずだが安全側のフォールバック

    elif boundary == "B2":
        # Manifest attempt lock取得後〜atomic write完了前。
        manifest_store._write_raw = lambda record: os._exit(1)
        lineage.mark_execution_started(root_run_id, member_run_id, claim_result.owner_token)
        os._exit(1)

    elif boundary == "B3":
        # Manifest atomic write完了後〜Manifest attempt lock解放前。
        # 実際の_write_raw()を呼び出して本物のatomic writeを完了させてから
        # crashさせる（with文のブロック内、__exit__到達前）。
        original_write_raw = manifest_store._write_raw

        def _crash_after_write(record):
            original_write_raw(record)
            os._exit(1)

        manifest_store._write_raw = _crash_after_write
        lineage.mark_execution_started(root_run_id, member_run_id, claim_result.owner_token)
        os._exit(1)

    elif boundary == "B4":
        # Manifest attempt lock解放後（create_for_attempt()は正常完了・
        # manifest作成済み）〜self._store.save(record)完了前。
        lineage_store.save = lambda record: os._exit(1)
        lineage.mark_execution_started(root_run_id, member_run_id, claim_result.owner_token)
        os._exit(1)

    else:
        sys.exit(4)


if __name__ == "__main__":
    main()
