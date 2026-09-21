"""
T5: Scenario D用 Two-Way Blocking Handshake worker（単一専用subprocess）。

docs/design/mvp_end_to_end_hardening_validation.md 11.1節の確定設計を実装する
test-only worker。実`WorkflowEngineManager`を直接構築し、`post_admission_hook`
（6.18節、start_run()のdurable ack後・NEWS step着手前に同期的に呼ばれる）へ
ready-sentinel書き込み→release-signal待ちのblocking hookを渡す。production
source（src/・scripts/・main.py）は一切変更しない。

起動引数（sys.argv）:
    argv[1]: Disposable Project Copy rootの絶対パス
    argv[2]: ready-sentinel file の絶対パス（hookが書き込む、親がpollingで待つ）
    argv[3]: release-signal file の絶対パス（crash経路では親は書き込まない）

exit code:
    0   release-signalが検出されhookが正常続行した場合（通常はcrash経路では
        到達しない、hookのHOOK_SAFETY_TIMEOUT_SEC安全弁テスト専用）
    2   HOOK_SAFETY_TIMEOUT_SEC（30秒）に到達（親のkillが遅すぎたこと、
        または後述のprocess-wide watchdogが発火したことを示す診断用
        exit code、11.1節）
    93  WorkflowEngineManagerゲートが閉じている
    94  CanonicalAdmissionFailure

【Post-Codex-delta-review#3 Amendment、Minor#2対応】従来、`HOOK_SAFETY_
TIMEOUT_SEC`の30秒はpost_admission_hookが実際に呼ばれた時点（＝ready-
sentinel書き込み後）からしか計測されていなかった。そのため、hookに到達する
**前**（gate判定・`WorkflowEngineEvent`構築・`manager.run()`呼び出し自体等）
で何らかの理由でworkerが停止・ハングした場合、readinessが失敗し（親は
taskkillを発行しない、11.1節の既存契約）、かつworker自身の安全弁も一切
発火しないため、workerが無期限のorphanプロセスとして残存しうる欠陥が
あった。これを軽減するため、`threading.Timer`によるprocess-wide watchdogを
`main()`の**最初の行**で起動する。このwatchdogは、`main()`開始から
`HOOK_SAFETY_TIMEOUT_SEC`秒後に、その時点で`main()`がまだ正常return
（0/93/94のいずれか）していなければ`os._exit(2)`する（daemon threadの
ため、`main()`が先に正常returnした場合はprocess終了とともに自動的に消滅
し、`finally`での明示的`cancel()`と合わせて安全側へ倒す）。hook自身の
待機loopも、hook到達時点から新たに30秒を計測するのではなく、**`main()`
開始時刻を起点とする同一のdeadline**を共有するよう変更した。

**（Post-Codex-delta-review#4 / Full Independent Review Amendmentで表現を
訂正、設計書11.1節・30.10節と整合）** 上記watchdogは**通常のPython
interpreter scheduling下でのbest-effort safety timeout**であり、無条件の
hard boundではない：①`main()`より前に発生するmodule-levelのimport解決
処理自体はwatchdogの計測対象外である。②`threading.Timer`のコールバックは
Python GILを介して実行されるため、native codeがGILを長時間占有し続ける
ような病的なケースでは、コールバック自体の実行が遅延しうる。`os._exit(2)`
は、timer callbackが実際に実行された時点でprocessを終了させる、という
契約である。「readiness/durable確認失敗時にtest側がtaskkillしない」という
既存契約（親側）は変更しない——本watchdogはworker自身の自律終了を、通常
想定される範囲のhang・失敗に対してbest-effortで補強するtest-only機構
であり、external watchdog processのようなhardな上限保証の追加（production
変更を要する）はscopeに含めない。
"""
from __future__ import annotations

import os
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

HOOK_SAFETY_TIMEOUT_SEC = 30
POLL_INTERVAL_SEC = 0.05


def main() -> int:
    # ── process-wide watchdog（Post-Codex-delta-review#3 Amendment、
    # Minor#2対応）：main()の最初の行で起動する。main()開始後いかなる
    # 時点でworkerが停止・ハングしても、通常のPython interpreter
    # scheduling下ではHOOK_SAFETY_TIMEOUT_SEC秒以内の自律終了をbest-effort
    # で図る（無条件のhard boundではない、モジュール冒頭のdocstring参照）。 ─
    process_start = time.monotonic()
    watchdog = threading.Timer(HOOK_SAFETY_TIMEOUT_SEC, lambda: os._exit(2))
    watchdog.daemon = True
    watchdog.start()

    try:
        disposable_copy_root = Path(sys.argv[1]).resolve()
        ready_sentinel_path = Path(sys.argv[2])
        release_signal_path = Path(sys.argv[3])

        expected_src = (disposable_copy_root / "src").resolve()
        sys.path.insert(0, str(expected_src))

        from ai import AgentConfig
        from workflow_engine import (
            SOURCE_MANUAL,
            CanonicalAdmissionFailure,
            NullWorkflowEngineManager,
            PostAdmissionHookResult,
            WorkflowEngineConfig,
            WorkflowEngineEvent,
            WorkflowEngineManager,
        )
        from side_effect_safety import (
            LegacyEntrypoint,
            LegacyExecutionOrigin,
            build_legacy_direct_provenance,
            complete_legacy_execution_context,
        )

        agent_config = AgentConfig.from_env(base_dir=disposable_copy_root)
        workflow_engine_config = WorkflowEngineConfig.from_env(project_root=disposable_copy_root)
        manager = WorkflowEngineManager.from_config(agent_config, workflow_engine_config)
        if isinstance(manager, NullWorkflowEngineManager):
            print("fail-closed: WorkflowEngineManager gate is closed", file=sys.stderr)
            return 93

        # hook自身の待機deadlineも、hook到達時刻からの新規30秒ではなく、
        # process起動時刻を起点とする同一のdeadlineを共有する。
        shared_deadline = process_start + HOOK_SAFETY_TIMEOUT_SEC

        def post_admission_hook(run_id: str):
            tmp_path = ready_sentinel_path.with_suffix(".tmp")
            tmp_path.write_text(run_id, encoding="utf-8")
            os.replace(tmp_path, ready_sentinel_path)

            while time.monotonic() < shared_deadline:
                if release_signal_path.exists():
                    return PostAdmissionHookResult(acknowledged=True)
                time.sleep(POLL_INTERVAL_SEC)
            os._exit(2)

        event = WorkflowEngineEvent(
            job_id="scenario-d-abandoned",
            source=SOURCE_MANUAL,
            triggered_at=datetime.now(),
            trigger_reason="Scenario D abandoned RUNNING worker (E2E test-owned).",
        )
        provenance = complete_legacy_execution_context(
            build_legacy_direct_provenance(LegacyEntrypoint.RUN_WORKFLOW_ENGINE_DIRECT),
            LegacyExecutionOrigin.WORKFLOW_ENGINE_DIRECT,
        )
        try:
            manager.run(
                event, dry_run=False, post_admission_hook=post_admission_hook,
                side_effect_execution_provenance=provenance,
            )
        except CanonicalAdmissionFailure as e:
            print(f"fail-closed: CanonicalAdmissionFailure: {e.reason}", file=sys.stderr)
            return 94
        return 0
    finally:
        watchdog.cancel()


if __name__ == "__main__":
    sys.exit(main())
