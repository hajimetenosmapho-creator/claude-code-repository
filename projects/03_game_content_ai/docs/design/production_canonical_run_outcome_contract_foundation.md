# Production Canonical Run & Outcome Contract Foundation（Release 6.30）設計書

## 0. Status

Architecture Design：Claude Code設計 → Codex read-only independent review（codex-plugin-cc経由、`codex:codex-rescue`、reasoning effort High）を経て収束。

| ラウンド | Verdict | 指摘 |
|---|---|---|
| Round 8（Final Integrated Baseline提示） | - | - |
| Round 8 Codex Review | `NEEDS_REVISION` | Major 4件（M8-1〜M8-4）／Minor 3件（N8-1〜N8-3）／Suggestion 2件（S8-1・S8-2） |
| Round 9（M8-1〜S8-2反映） | - | - |
| Round 9 Codex Review | `NEEDS_REVISION` | Major 1件（M9-1：`release_run()`がCanonical Admission Failure全経路で保証されていない）／Minor 1件（N9-1：subprocess出力の正規化がcompleted stdoutを含む全ログ経路をカバーしていない） |
| Round 10（M9-1・N9-1反映） | - | - |
| **Round 10 Codex Review** | **`APPROVED`** | **Blocking 0／Major 0／Minor 0／Suggestions 0** |

Round 1〜7（本Release固有のArchitecture Revision初期ラウンド）は本ドキュメント作成セッションの対象外で実施済みであり、本ドキュメントはRound 8（Final Integrated Baseline）以降の収束過程のみを記録する。

**Human Gate承認：2026-08-20。** Round 10 APPROVED内容、および23章「Canonical Admission FailureのGovernance Exception」を人間が承認した。

**実装完了（2026-08-22）。** Codex Final Code Review `APPROVED`（Blocking 0／Major 0／Minor 0／Suggestion 0）。Formal Regression：正式Inventory33ファイル、5512/5512 PASS、FAIL 0／SKIP 0、全ファイルexit code 0。Runtime Verification：28章のE2Eシナリオに対応する全11 scenario PASS、Original Project 911ファイルZero-Diff、Disposable Copy allow-list外diff 0、外部I/Oなしを確認。**commit/pushは未実施**（Codex Final Release Review前のHuman Gate待ち）。詳細は`docs/CHANGELOG.md`「[v6.30.0]」を参照。

---

## 1. Background / Motivation

`docs/MVP_COMPLETION_ROADMAP.md`（v1.3）のArchitecture Reconciliationにより、Monitor→Trigger→Queue→RetryRuntimeの配線自体は既に完成しており（`scripts/run_retry_runtime.py --loop`による自律的な定期Retryも実行可能）、残るGapは「新規配線の構築」ではなく (a) 本番canonical runの確立、(b) 既存Retry経路の安全性強化、(c) Scheduler駆動方式の決定、の3点であることが判明した。

Release 6.30は上記(a)、すなわち既存の`WorkflowEngineExecutor`（v2.7.0）→ NEWSステップ → `main.py` subprocess経路をMVP本番canonical runとして確立し、`main.py`の終了状態が外側`WorkflowExecutionRecord`（Execution History、v2.8.0）へ安全に反映される契約を確定するReleaseである。

## 2. Scope境界（Roadmap v1.3準拠）

6.30の責務は「**canonical `WorkflowExecutionRecord` → FAILED/TIMEOUT candidateの生成**」までとする。FAILED/TIMEOUT candidateを実際にRetry Eligibilityへ渡して判定する責務は6.31に属する（Roadmap M3-1対応、6.30/6.31間の循環依存解消）。新規subsystem・大規模refactor・Retry Eligibility実装・Scheduler統合は行わない。

## 3. Goals

1. Workflow Engine経由の起動をMVP本番の唯一の実行経路として確立するための、`main.py`終了状態→`WorkflowExecutionStatus`対応契約を確定する
2. Workflow Engine経由の実行1回につき`WorkflowExecutionRecord`が1件のみ生成されること（二重record防止）を、Execution History層自身の契約として保証する
3. dry-run実行のHistory zero-write、およびcanonical non-dry-run実行のHistory-required invariantを、`WorkflowEngineExecutor`共通経路のfail-closed境界として確立する
4. abandoned RUNNING recordが既存`WorkflowMonitor`のTIMEOUT契約によりFAILED/TIMEOUT candidateとして検出可能であることを保証する

## 4. Non-Goals（Out of Scope）

Retry enqueue／execution／Eligibility consumption（6.31）、6.32 Human Review、Scheduler統合、lock/multi-writer framework、TTL/LRU/sweeper、JSON failure envelope、`main.py`直接のExecution History書き込み、Retry Runtime cycle-level `CanonicalAdmissionFailure` recovery（13章 Ruling A参照）、production gateの永続的有効化。

---

## 5. main.py Outcome Contract

shell/process outcome：`0=SUCCESS` / `1=GENERIC_FAILURE` / `20=PARTIAL` / `21=ALL_FAILED`（`2`はargparse usage errorと衝突するため使用しない）。

`main()`は`int`を返す。既存の早期`sys.exit()`（現行コード7箇所）はすべて`return`へ置換する：

| # | 現行 | 発生条件 | 変更後 |
|---|---|---|---|
| 1 | `sys.exit(1)` | `--max-articles`不正 | `return 1` |
| 2 | `sys.exit(1)` | `ANTHROPIC_API_KEY`未設定 | `return 1` |
| 3 | `sys.exit(1)` | featured-media設定不正（`ValueError`） | `return 1` |
| 4 | `sys.exit(1)` | RSS収集0件 | `return 1` |
| 5 | `sys.exit(0)` | filter後0件 | `return 0` |
| 6 | `sys.exit(0)` | importance判定後0件 | `return 0` |
| 7 | `sys.exit(0)` | generation対象0件 | `return 0` |

末尾のWordPress outcome（counterベース）：

```python
if wp_failed_count == 0:
    return 0
elif wp_success_count > 0:
    return 20
else:
    return 21
```

モジュール境界は`if __name__ == "__main__": sys.exit(main())`のみ。side effect後のuncaught exceptionは`main()`内でcatchせず、Python既定のexit 1とする。

**WordPress failed/skip counter条件の確定（旧N8-2）**：`wp_skipped_count`はPARTIAL/ALL_FAILED判定に一切関与しない。判定は`(wp_failed_count, wp_success_count)`のみに依存する。featured-media失敗による`wp_failed_count`増分（`wp_available`の値に関係なく発生）と、WordPress全体unavailableによる`wp_skipped_count`増分は同一run内で共存しうる（例：ある記事のfeatured-media処理が失敗し、かつWordPress自体が全体的にunavailable）。この共存ケースでも`wp_success_count==0`であれば`ALL_FAILED/21`となる。

---

## 6. NEWS Outcome Token・subprocess出力正規化

成功時：`error_message = None`。失敗時のみmachine-readable tokenを付与する：

```text
NEWS_OUTCOME_GENERIC_FAILURE_EXIT_1
NEWS_OUTCOME_PARTIAL_EXIT_20
NEWS_OUTCOME_ALL_FAILED_EXIT_21
NEWS_OUTCOME_ABNORMAL_EXIT
NEWS_OUTCOME_TIMEOUT
NEWS_OUTCOME_LAUNCH_FAILURE
```

形式：`{token}\n{diagnostic}`。JSON envelopeは6.30では導入しない。TIMEOUT診断：`NEWS_OUTCOME_TIMEOUT\nタイムアウトしました（{timeout_sec}秒）`。launch failureは`OSError`を捕捉し`NEWS_OUTCOME_LAUNCH_FAILURE\n{str(exception)}`。History persist failureはNEWS tokenへ混ぜず、`history_write_failed`（17章）で独立伝播する。

### subprocess出力のbytes正規化契約（`src/pipeline/news_pipeline_runner.py`）

`subprocess.CompletedProcess.stderr`／`subprocess.TimeoutExpired.stdout`・`.stderr`は呼び出し方法によって`bytes`になり得る。ログ保存・診断生成のいずれの経路でも、使用前に必ずstrへ正規化する：

```python
def _normalize_subprocess_output(value: bytes | str | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value
```

`errors="replace"`はCodex Round 10で妥当性確認済み（診断・ログ用途でありデータ交換用途ではないため許容）。

`NewsPipelineRunner.run()`は、`completed.stdout`／`completed.stderr`を受領直後に正規化し、以降の`_save_log()`呼び出し・`error_message`診断（既存の`[-500:]`切り詰め）は正規化済み変数のみを使用する。`except subprocess.TimeoutExpired as e:`分岐でも`e.stdout`／`e.stderr`を同じヘルパーで正規化してから`_save_log()`へ渡す：

```python
def run(self, params: dict) -> PipelineResult:
    cmd = [...]
    ...
    try:
        completed = subprocess.run(
            cmd, cwd=self._config.working_directory,
            capture_output=True, text=True, timeout=self._config.timeout_sec,
        )
    except subprocess.TimeoutExpired as e:
        elapsed = time.time() - start
        stdout_text = _normalize_subprocess_output(e.stdout)
        stderr_text = _normalize_subprocess_output(e.stderr)
        stdout_path = self._save_log(run_timestamp, "stdout", stdout_text)
        stderr_path = self._save_log(run_timestamp, "stderr", stderr_text)
        return PipelineResult(
            success=False, returncode=None, elapsed_sec=elapsed,
            stdout_log_path=stdout_path, stderr_log_path=stderr_path,
            error_message=f"タイムアウトしました（{self._config.timeout_sec}秒）",
        )

    elapsed = time.time() - start
    stdout_text = _normalize_subprocess_output(completed.stdout)
    stderr_text = _normalize_subprocess_output(completed.stderr)
    stdout_path = self._save_log(run_timestamp, "stdout", stdout_text)
    stderr_path = self._save_log(run_timestamp, "stderr", stderr_text)
    success = completed.returncode == 0
    return PipelineResult(
        success=success, returncode=completed.returncode, elapsed_sec=elapsed,
        stdout_log_path=stdout_path, stderr_log_path=stderr_path,
        error_message=None if success else stderr_text[-500:],
    )
```

（旧N9-1対応。現行`NewsPipelineRunner`は`text=True`使用のため通常運用で実害はないが、テストダブルや将来の呼び出し方変更に対する契約として正規化を必須とする。）

---

## 7. Canonical History Invariant

権威あるInvariant：**dry-run → Null History可・zero-write** ／ **canonical non-dry-run → Null History禁止**。共通経路である`WorkflowEngineExecutor.run()`が最終fail-closed boundaryとなる（19章の`try`内で判定。旧M9-1対応で`try`の外に置かない）。

```python
effective_history_manager = (
    NullExecutionHistoryManager() if context.dry_run else self._history_manager
)
```

dry-runでは実Historyが設定されていてもNullへ差し替える。これによりdry-run History zero-writeをExecutor共通経路で保証する。

## 8. Execution History expected-failure契約

`ExecutionHistoryManager`は「あらゆる例外を握りつぶす」とは規定しない。expected persistence I/O failureのみ`ack=False`へ正規化し、programming error・invariant violation・unexpected exceptionまで一律に握りつぶす契約にはしない。ただし`release_run(run_id)`だけはcleanup primitiveとして idempotent／missing-safe／non-throwing を保証する。

## 9. ExecutionHistory API

```python
start_run(run_id, workflow_name, source, job_id) -> StartRunWriteResult  # {run_id, acknowledged: bool}
start_step(run_id, step) -> bool
finish_step(run_id, step, status, error_message=None, skipped_reason=None) -> bool
finish_run(run_id, status, error_message=None) -> bool
release_run(run_id) -> None
```

`NullExecutionHistoryManager`の戻り値は規範（must）として明示する：

```python
class NullExecutionHistoryManager:
    def start_run(self, run_id, workflow_name, source, job_id) -> StartRunWriteResult:
        return StartRunWriteResult(run_id=run_id, acknowledged=True)
    def start_step(self, run_id, step) -> bool:
        return True
    def finish_step(self, run_id, step, status, error_message=None, skipped_reason=None) -> bool:
        return True
    def finish_run(self, run_id, status, error_message=None) -> bool:
        return True
    def release_run(self, run_id) -> None:
        return None
```

## 10. Manager-owned snapshot / Copy-on-write

呼び出し側はmutableな`WorkflowExecutionRecord`を保持しない。`run_id`のみを渡す。Manager内部は`self._last_acknowledged: dict[str, WorkflowExecutionRecord]`を持つ。各transition：(1) `copy.deepcopy(last_acknowledged_snapshot)`——`record`本体・`steps`リスト・`events`リストのいずれも独立コピーとする（shallow copyや`dataclasses.replace()`単体はリスト参照を共有するため不可）、(2) candidateへ1 transitionだけ適用、(3) `store.save(candidate)`、(4) ack=Trueのみsnapshotをcandidateへ置換、ack=Falseならcandidate破棄・snapshot不変。

States：`UNADMITTED` / `ADMITTED_RUNNING` / `TERMINAL(SUCCESS|FAILED)`。

## 11. start_run / Canonical Admission

ack=True → `UNADMITTED→ADMITTED_RUNNING`。ack=False → `UNADMITTED`のまま。Executorはack=Falseなら即座に`CanonicalAdmissionFailure(run_id, reason="START_RUN_ACK_FAILED")`を送出し、step loopへ入らない。NEWS未開始・Agent未開始・external side effectなしを保証する。

## 12. start_step

ack=True → snapshot更新、Agent実行。ack=False → candidate破棄・snapshot不変。**Managerはrunを自動的にTERMINALへ遷移させない**（recoveryを一切試みない）。durable snapshotは直前の`last_acknowledged`のまま変化しない。runを終端させる責務はExecutor側にあり、ループ終了後に`finish_run(FAILED)`を1回だけ明示的に呼ぶ（19章）。Executorは実際のdurable stateを推測・検査せず、呼び出し経路（start_step失敗）のみに基づく固定のcontrol-flow rule として行動する。

## 13. finish_step recovery

### executed RUNNING step

persist失敗時：pre-failure snapshotからfresh copy → pending RUNNING stepをFAILEDへ正規化 → run自体をFAILED → finished_at設定 → terminal event 1個 → recovery persistを1回だけ試行。recovery成功→`TERMINAL(FAILED)`。recovery失敗→last-known-good RUNNINGのままWorkflowMonitor TIMEOUT契約へ委ねる。`finish_step()`自体のreturnはいずれもFalse。

### SKIPPED / NOT_REACHED

pending RUNNINGが存在しない通常経路（gate-closed SKIPPED、または後続のNOT_REACHED）では、正式な`StepExecutionRecord`を作成する（既存v2.8.0契約を維持）が、`started_at=None`とする（v2.8.0の`started_at=now`から修正——ステップは実際には開始していないため）：

```python
StepExecutionRecord(
    step=step, status=status,  # SKIPPED または NOT_REACHED
    started_at=None, finished_at=now,
    error_message=error_message, skipped_reason=skipped_reason,
)
```

このrecordのpersist失敗時recoveryは、executed stepのケースと異なり、**recordのstatusを変更しない**（FAILEDへ変換しない。実行されなかった事実を実行失敗として誤表現しないため）。run自体のみFAILEDへ終端する recoveryを1回試行する。`finish_step()`のreturnはFalse。

### Executor側の後続挙動（旧M8-2対応）

`finish_step()`がFalseを返した時点で、Managerは（recoveryが成功したか失敗したかに関わらず）terminal recoveryを既に1回試行済みである。Executorはこの結果を問い合わせない・推測しない。以降、当該run内でいかなるHistory API呼び出しも行わない（`finish_run`も含む）。残りのstepはin-memoryでのみNOT_REACHEDとして記録する。`finally`ブロックで`release_run()`のみを呼ぶ。

## 14. finish_run recovery

TERMINAL runへの呼び出し：同一status要求→`True`（no write）、異なるstatus要求→`False`（no write）。terminal後は新規persist禁止（判定はcandidate作成前）。`ADMITTED_RUNNING`：fresh snapshot → requested terminal status → finished_at → terminal event 1個 → persist。ack=True→`TERMINAL(requested status)`・`True`。ack=False→recovery persistを1回だけ試行（常にFAILED方向）。recoveryが成功しても、元の要求persist自体は失敗したため`finish_run() -> False`を返す。

## 15. Terminal immutability

Once durably terminal, always terminal。durable snapshot内のterminal eventは最大1個。terminal後、start_step／finish_step／finish_runによる追加persistは禁止（同一terminal finish requestだけidempotent success・no-write）。

## 16. release_run lifecycle

`release_run(run_id)`は`self._last_acknowledged.pop(run_id, None)`相当の最小cleanup。idempotent・missing-safe・non-throwing。`WorkflowEngineExecutor.run()`全体を`try/finally`で囲み、`finally`で呼ぶ（19章）。**この`finally`呼び出しは、`try`ブロック内で発生した例外（`CanonicalAdmissionFailure`等）をマスク・置換しない**（旧S8-2対応）。TTL・LRU・background sweep・generic eviction framework・multi-writer lockは延期。

## 17. history_write_failed（Option B）

`WorkflowEngineResult.history_write_failed: bool = False`（latch semantics：一度Trueになったら当該run中はFalseへ戻らない）。`overall_success`の既存意味は変更しない（Agent/step outcomeのみ）。History integrityは`history_write_failed`で分離管理する。Outer success = `overall_success == True AND history_write_failed == False`。

---

## 18. Recovery / Control-Flow Table

| 呼び出し | ack | Manager内部動作 | Executorの後続動作 |
|---|---|---|---|
| `start_run()` | True | `UNADMITTED→ADMITTED_RUNNING` | step loop開始 |
| `start_run()` | False | `UNADMITTED`のまま | `CanonicalAdmissionFailure`即時raise。step loop不進入。NEWS/Agent未開始 |
| `start_step()` | True | RUNNING step追加 | `executor.execute()`実行 |
| `start_step()` | False | snapshot不変（自動recoveryなし） | Agent未実行。残stepをin-memory NOT_REACHEDへ。ループ終了後`finish_run(FAILED)`を1回だけ明示呼び出し |
| `finish_step()`（executed step） | True | step=(SUCCESS\|FAILED) | 次stepへ継続（FAILEDならstopped_early=True） |
| `finish_step()`（executed step） | False | recovery 1回試行→成功:`TERMINAL(FAILED)`／失敗:last-known-good RUNNING | 以降History API呼び出し一切なし（finish_run含む）。残stepはin-memory NOT_REACHEDのみ。finallyで`release_run()`のみ |
| `finish_step()`（SKIPPED/NOT_REACHED） | True | `started_at=None`の正式record追加 | 次stepへ継続 |
| `finish_step()`（SKIPPED/NOT_REACHED） | False | recovery 1回試行（recordのstatusは保持したまま run→FAILED） | 同上：History API呼び出し一切なし。finallyで`release_run()`のみ |
| `finish_run()`（TERMINAL宛て） | True/False（no-op write） | 変化なし | - |
| `finish_run()`（ADMITTED_RUNNING宛て） | True | `TERMINAL(requested status)` | run完了 |
| `finish_run()`（ADMITTED_RUNNING宛て） | False | recovery 1回試行（常にFAILED方向） | `finish_run()`自体はFalseを返す（recovery成否に関わらず） |
| `release_run()` | - | idempotent pop | 常に`finally`で1回呼ぶ。元例外をマスクしない |

## 19. Executor制御フロー（確定版・`WorkflowEngineExecutor.run()`）

```python
def run(self, context: WorkflowEngineContext) -> WorkflowEngineResult:
    started_at = datetime.now()
    context.started_at = started_at
    run_id = context.run_id

    effective_history_manager = (
        NullExecutionHistoryManager() if context.dry_run else self._history_manager
    )

    try:
        # Canonical History Invariant判定は try の内側に置く（旧M9-1対応）。
        # これにより EXECUTION_HISTORY_DISABLED を含む全ての CanonicalAdmissionFailure
        # 経路で finally の release_run() が必ず実行される。
        if not context.dry_run and isinstance(effective_history_manager, NullExecutionHistoryManager):
            raise CanonicalAdmissionFailure(run_id, reason="EXECUTION_HISTORY_DISABLED")

        start_result = effective_history_manager.start_run(
            run_id=run_id, workflow_name=WORKFLOW_NAME,
            source=context.event.source, job_id=context.event.job_id,
        )
        if not start_result.acknowledged:
            raise CanonicalAdmissionFailure(run_id, reason="START_RUN_ACK_FAILED")

        step_results: list[WorkflowEngineStepResult] = []
        stopped_early = False
        history_write_failed = False
        history_closed = False          # True以降は当該run内で追加のHistory API呼び出しをしない
        owe_closing_finish_run = False  # control-flow専用フラグ。start_step ack失敗経路でのみTrue。
                                         # 実際のdurable terminal状態を推測・claimしない。

        for step in self._definition.steps:
            if history_closed or stopped_early:
                step_results.append(WorkflowEngineStepResult(
                    step=step, executed=False, agent_result=None,
                    success=False, skipped_reason=REASON_NOT_REACHED,
                ))
                if history_closed:
                    continue  # in-memoryのみ。History API呼び出しなし
                ok = effective_history_manager.finish_step(
                    run_id, step.value, StepExecutionStatus.NOT_REACHED,
                    skipped_reason=REASON_NOT_REACHED,
                )
                if not ok:
                    history_write_failed = True
                    history_closed = True
                continue

            executor = self._step_executors.get(step)
            if executor is None:
                reason = self._step_skip_reasons.get(step, f"{step.value} step is not configured (gate closed).")
                step_results.append(WorkflowEngineStepResult(
                    step=step, executed=False, agent_result=None,
                    success=True, skipped_reason=reason,
                ))
                ok = effective_history_manager.finish_step(
                    run_id, step.value, StepExecutionStatus.SKIPPED, skipped_reason=reason,
                )
                if not ok:
                    history_write_failed = True
                    history_closed = True
                continue

            ok = effective_history_manager.start_step(run_id, step.value)
            if not ok:
                history_write_failed = True
                step_results.append(WorkflowEngineStepResult(
                    step=step, executed=False, agent_result=None,
                    success=False, skipped_reason=REASON_HISTORY_WRITE_FAILED,
                ))
                history_closed = True
                stopped_early = True
                owe_closing_finish_run = True  # start_step失敗：Managerは自動終端しない
                continue

            agent_context = AgentContext(
                task=AgentTask(task_id=f"workflow_engine_{step.value}", params=dict(context.event.metadata)),
                dry_run=context.dry_run, run_id=run_id, agent_name="",
            )
            agent_result = executor.execute(agent_context)
            context.warnings.extend(agent_context.warnings)
            step_results.append(WorkflowEngineStepResult(
                step=step, executed=True, agent_result=agent_result,
                success=agent_result.success, skipped_reason=None,
            ))

            if agent_result.success:
                ok = effective_history_manager.finish_step(run_id, step.value, StepExecutionStatus.SUCCESS)
            else:
                ok = effective_history_manager.finish_step(
                    run_id, step.value, StepExecutionStatus.FAILED,
                    error_message=agent_result.error_message,
                )
                stopped_early = True
            if not ok:
                history_write_failed = True
                history_closed = True

        context.step_results = step_results
        finished_at = datetime.now()
        context.finished_at = finished_at
        overall_success = all(r.success for r in step_results)

        if not history_closed:
            ok = effective_history_manager.finish_run(
                run_id,
                WorkflowExecutionStatus.SUCCESS if overall_success else WorkflowExecutionStatus.FAILED,
            )
            if not ok:
                history_write_failed = True
        elif owe_closing_finish_run:
            # start_step失敗経路のみ：Executorが負っていた最後の1回の終端呼び出しを行う
            effective_history_manager.finish_run(run_id, WorkflowExecutionStatus.FAILED)
        # else: finish_step失敗経路。Managerが既にrecovery試行済みのため finish_run は呼ばない。

        return WorkflowEngineResult(
            steps=step_results, overall_success=overall_success, stopped_early=stopped_early,
            started_at=started_at, finished_at=finished_at, warnings=list(context.warnings),
            history_write_failed=history_write_failed,
        )
    finally:
        effective_history_manager.release_run(run_id)
```

`REASON_HISTORY_WRITE_FAILED`は新規定数。既存`REASON_NOT_REACHED`とスコープが衝突しない（Codex Round 9で妥当性確認済み）。

---

## 20. scripts/run_workflow_engine.py 契約

```python
def main() -> int:
    ...
    manager = WorkflowEngineManager.from_config(agent_config, workflow_engine_config)

    # 1. gate OFF -> successful no-op -> exit 0
    if isinstance(manager, NullWorkflowEngineManager):
        print("[情報] Workflow Engineが無効です。")
        return 0

    # 2. resolve_event() 対象なし -> no-op -> exit 0
    event = resolve_event(args)
    if event is None:
        return 0

    # 3. canonical non-dry-run かつ History disabled -> early diagnostic -> exit 1
    #    dry-runは History OFF でも通す
    history_enabled = ExecutionHistoryConfig.from_env(project_root=base_dir).is_ready()
    if not args.dry_run and not history_enabled:
        print("[エラー] canonical non-dry-run実行には EXECUTION_HISTORY_ENABLED=true が必要です。")
        return 1

    # 4. Executor側 Invariant（CanonicalAdmissionFailure）が権威。3.は早期診断にすぎない。
    try:
        result = manager.run(event, dry_run=args.dry_run)
    except CanonicalAdmissionFailure as e:
        print(f"[エラー] Canonical Admission Failure: run_id={e.run_id}, reason={e.reason}")
        print("  NEWS/Agentは開始されていません。")
        return 1

    print_result(result)

    # 6. overall_success AND NOT history_write_failed のみ 0
    if result.overall_success and not result.history_write_failed:
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

## 21. Retry Runtime（Codex Ruling A）

実在経路：`run_retry_runtime.py → RetryCompositionRoot → RetryManager → WorkflowEngineManager → WorkflowEngineExecutor`。同一Managerが`--loop`中に複数runへ再利用されるため、19章のExecutor共通History invariantと`release_run()`はRetry Runtimeにも適用される。

**Codex Ruling A（確定・変更なし）：`CanonicalAdmissionFailure`はRetry Runtimeの既存fail-fastを維持し、プロセスへ伝播させる。`RetryExecutor`／`RetryManager`への新規catch/変換ロジックは6.30に追加しない。**

## 22. JsonExecutionHistoryStore atomic save

```python
def save(self, record: WorkflowExecutionRecord) -> bool:
    try:
        self._history_dir.mkdir(parents=True, exist_ok=True)
        fd, tmp_path_str = tempfile.mkstemp(
            prefix=f".{record.run_id}.", suffix=".tmp", dir=str(self._history_dir)
        )
    except OSError as e:
        print(f"  [EXECUTION HISTORY WARNING] 履歴保存に失敗しました（処理は継続します）: {e}")
        return False

    tmp_path = Path(tmp_path_str)
    try:
        try:
            f = os.fdopen(fd, "w", encoding="utf-8")
        except OSError as e:
            # os.fdopen() 自体の失敗：file objectへownershipが移っていないため、
            # raw fdを自前でbest-effort closeする（以降の with f: 経路とは排他的）。
            try:
                os.close(fd)
            except OSError:
                pass
            print(f"  [EXECUTION HISTORY WARNING] 履歴保存に失敗しました（処理は継続します）: {e}")
            return False

        try:
            with f:
                # 以降、fd closeはfile objectの __exit__ が保証する。os.close(fd)を重ねない。
                f.write(record.to_json())
                f.flush()
                os.fsync(f.fileno())
        except OSError as e:
            print(f"  [EXECUTION HISTORY WARNING] 履歴保存に失敗しました（処理は継続します）: {e}")
            return False

        try:
            os.replace(tmp_path, self._path_for(record.run_id))
        except OSError as e:
            print(f"  [EXECUTION HISTORY WARNING] 履歴保存に失敗しました（処理は継続します）: {e}")
            return False

        return True
    finally:
        # best-effort cleanup。cleanup失敗はackを一切変更しない（returnは既に確定済み）
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass
```

Invariant：`.json`拡張子を持つのはcanonical History recordだけ。temp名は`.{run_id}.{unique}.tmp`で`list_all()`の既存`glob("*.json")`から構造的に除外される。directory fsync等によるfull power-loss durabilityまでは6.30で保証しない。

---

## 23. Governance Exception — Canonical Admission Failure

Roadmap v1.3の「**1 production invocation = 1 canonical retryable record**」に対する明示的例外。

`CanonicalAdmissionFailure`ではproduction invocationが開始されたにもかかわらず、durable canonical recordが存在しない場合がある（`EXECUTION_HISTORY_DISABLED`・`START_RUN_ACK_FAILED`のいずれの理由でも起こりうる）。結果：

- 6.31 History scannerから不可視
- Retry Eligibility対象にならない
- NEWS / external side effect開始前なので重複副作用は発生しない
- ただし可観測性・追跡可能性は失われる

これは「実害なし」ではなく、**意図的に受容するoperational gap**である。atomic admission write中、ackが返る前に親プロセスが中断した場合も同種の状態になり得るため、本Governance Exceptionの対象に含める。fallback durable admission markerやadmission failure alertはpost-MVP候補とする。

**本Governance Exceptionは2026-08-20にHuman Gateで承認された（Round 10 APPROVED内容の一部として）。** `docs/MVP_COMPLETION_ROADMAP.md`の「Architecture Reconciliation」章にも本Exceptionへの参照を追記した。

---

## 24. Zero-Diff境界

`main.py`直接実行について、Zero-Diff維持：generated content・WordPress等の外部副作用・`main.py`自身によるExecution History write追加なし。意図的変更：PARTIAL / ALL_FAILED shell exit outcome（5章）——これは6.30のOutcome Contract変更であり回帰ではない。

---

## 25. In Scope

main.py Outcome Contract／shell outcome 0/1/20/21／NEWS failure token（bytes正規化含む）／`ExecutionHistoryStore`のbool ack（Null実装の明示的戻り値含む）／atomic History save（fd-close/cleanup契約含む）／manager-owned snapshot・copy-on-write（deep copy契約含む）／History API run_id化／Canonical Admission fail-closed／`finish_step`・`finish_run`のrecovery（SKIPPED/NOT_REACHED記録契約含む）／terminal immutability／`history_write_failed`／`release_run`（非マスキング契約含む）／dry-run History zero-write／canonical non-dry-run History-required invariant／`run_workflow_engine.py`外側exit contract／Governance Exception／既存test/API migration。

## 26. Out of Scope

Retry enqueue／execution／Eligibility consumption（6.31）、6.32 Human Review、Scheduler統合、lock/multi-writer framework、TTL/LRU/sweeper、JSON failure envelope、`main.py`直接のExecution History書き込み、Retry Runtime cycle-level `CanonicalAdmissionFailure` recovery（Ruling A）、production gate永続的有効化。

## 27. 既存test/API migration inventory

既存test callerもAPI変更対象。少なくとも：

- `tests/test_e2e_v2_8_0_execution_history_foundation.py`：`ExecutionHistoryManager`旧record-based APIを直接使用
- `tests/test_e2e_v2_9_0_workflow_monitor_foundation.py`：`InMemoryExecutionHistoryStore.save()`がNone返却

いずれも実装時に新ack APIへmigrationし、既存意味を維持する。加えて（Round 10 Codex Reviewでの確認事項）：

- `WorkflowEngineResult`へ`history_write_failed`フィールドを追加する際、その明示的`to_dict()`実装も合わせて更新する（同フィールドが公開result contractの一部である場合）
- 新規dataclassフィールドは`default=False`を維持することで、既存呼び出し元はsource-compatibleのまま

## 28. Runtime Verification / Completion E2E baseline

Case Eハーネス（config error・side effect後failure等の実行系シナリオ）は、Git root外のdisposable filesystem copy・local fixture RSS・deterministic fake Anthropic・loopback fake WordPress・successful POST count確認・non-loopback egress denied・`_load_prompt_template()` counting wrapper shim・production sourceへのtest hook追加なし、を前提とする。

E2E一覧（#1〜32はRelease 6.30 Architecture Revision Round 8で確定、#33〜63はRound 9〜10で追加）：

1. normal WordPress success
2. PARTIAL
3. ALL_FAILED
4. target 0 SUCCESS paths
5. config failure
6. side effect後uncaught exception / Case E
7. abnormal child termination
8. abandoned RUNNING → TIMEOUT
9. Canonical Admission Failure
10. one invocation → one canonical record
11. Gate combinations
12. start_step ack failure
13. finish_step ack failure
14. finish_run(SUCCESS) failure → FAILED recovery
15. terminal + recovery双方失敗 → last-known-good RUNNING
16. History disabled canonical run rejection
17. subprocess launch failure
18. no scheduled/target event → exit 0
19. WordPress all skip
20. token / diagnostic separation
21. in-process `main.main()` call
22. start_run ack failure → Agent未開始
23. SKIPPED finish_step persist failure
24. NOT_REACHED finish_step persist failure
25. finish_run(FAILED) persist failure recovery
26. argparse exit 2 vs generic exit 1
27. TIMEOUT diagnostic
28. WordPress failed + skip counter case
29. release_run idempotence
30. old API test migration
31. dry-run zero History write
32. Retry Runtime経路でHistory invariantが有効
33. Null History明示的戻り値（start_run ack=True／start_step・finish_step・finish_run=True／release_run no-op）を直接検証
34. dry-run実行時、EXECUTION_HISTORY_ENABLED=trueでも実Historyへゼロwriteかつeffective managerがNull相当になること
35. run_workflow_engine.py: gate OFF → exit 0（dry-run/non-dry-run両方）
36. run_workflow_engine.py: resolve_event=None → exit 0
37. run_workflow_engine.py: dry-run + History OFF → 早期exit1にならず正常実行される
38. run_workflow_engine.py: non-dry-run + History OFF → exit 1
39. finish_step()==False（executed step）後、後続stepでstart_step/finish_stepが一切呼ばれない
40. finish_step()==False後、finish_runも呼ばれずrelease_runのみ呼ばれる
41. start_step()==False後、AgentExecutor.execute()が呼ばれない
42. start_step()==False後、finish_run(FAILED)がちょうど1回だけ呼ばれる
43. start_step()==False後、残stepがWorkflowEngineResult.steps上でNOT_REACHEDとして記録されるが、Historyには一切persistされない
44. gate-closed SKIPPEDのfinish_stepが`started_at=None`の正式StepExecutionRecordとして保存される
45. NOT_REACHEDのfinish_stepが`started_at=None`の正式StepExecutionRecordとして保存される
46. SKIPPED記録のpersist失敗時、recovery後もSKIPPEDステータスのままrun全体がFAILEDへ終端する
47. NOT_REACHED記録のpersist失敗時も同様
48. executed RUNNING stepのfinish_step失敗はstep FAILEDへ正規化される
49. TimeoutExpired.stdout/stderrがbytesの場合でも例外を起こさず正規化後の文字列として扱われる
50. TimeoutExpired.stdout/stderrがNoneの場合、空文字として扱われる
51. atomic save: write中のOSErrorでfdが確実にcloseされ、tmpファイルがunlinkされる
52. atomic save: os.replace失敗時もfdはcloseされ、tmpファイルがbest-effort unlinkされる
53. atomic save: cleanup（unlink）自体が失敗しても、save()の戻り値（ack=False）が変化しない
54. Manager snapshotのdeep copy検証：candidateのsteps/eventsリストを変更してもsnapshot側のリストが変化しない
55. featured-media失敗（wp_failed_count>0）とWordPress unavailable（wp_skipped_count>0）が同一run内で共存 → outcomeがALL_FAILED/21になる
56. **（Round 10で改訂）** `EXECUTION_HISTORY_DISABLED`・`START_RUN_ACK_FAILED`の両方の`CanonicalAdmissionFailure`理由について、`release_run()`が呼ばれた上で、Retry Runtime `--loop`経路も含め伝播する例外が元の例外そのもの（型・run_id・reason不変）であることを確認する
57. main.pyの7箇所の早期returnが`sys.exit()`を経由せず、`sys.exit(main())`のみで終了コードに反映される
58. main.py: `wp_failed_count>0 && wp_success_count>0` → exit 20
59. main.py: `wp_failed_count>0 && wp_success_count==0` → exit 21
60. main.py: side effect後のuncaught exceptionがPython既定exit 1になる
61. atomic save: `os.fdopen()`自体がOSErrorを送出した場合、raw fdが`os.close(fd)`でbest-effort・1回だけcloseされ、二重closeが発生しない
62. **（Round 10新規）** `NewsPipelineRunner`: `completed.stdout`/`completed.stderr`がbytesの場合でも、`_save_log()`保存内容・`error_message`診断がstrとして安全に処理される（例外を起こさない）
63. **（Round 10新規）** `NewsPipelineRunner`: `TimeoutExpired.stdout`/`.stderr`がbytesの場合でも同様に安全に処理される

## 29. Verification isolation

Runtime Verificationでは、Git root外のdisposable copy（`.git`・production `.env`・production logs/outputはコピーしない）・official existing project venvをabsolute pathで利用・`PYTHON_DOTENV_DISABLED=1`・`PYTHONDONTWRITEBYTECODE=1`・top-level `-B`・History/log/output pathをcopy内部へ固定、を用いる。Original Projectはbefore/after manifest（relative path・size・SHA-256、ignored runtime dirsも含める）で完全Zero-Diffを要求する。Disposable Copy側はallow-listed verification artifact以外のdiffをfailとする。

## 30. Architecture Scope Freeze

Release分割なし。6.30で必要なものは既存subsystem内のcontained changeとして実施する。延期維持：lock・multi-writer・generic eviction・JSON envelope・Retry Runtime continuation semantics。Release 6.30はあくまで「Production Canonical Run & Outcome Contract／FAILED・TIMEOUT candidate生成まで」に留める。

---

## 31. 参照

- `docs/MVP_COMPLETION_ROADMAP.md`（v1.3）— Release 6.30の公式Goal/Completion Criteria、Governance Exception参照元
- Codex Review：codex-plugin-cc（`codex:codex-rescue`、reasoning effort High、read-only）、Round 9・Round 10で使用

---

## 32. Historical Zero-Diff Guard Migration Verification（Appendix、2026-08-22追記）

**位置づけ**：本章は27章「既存test/API migration inventory」および`docs/CHANGELOG.md` `[KI-30]`で言及した、Release 6.30の承認済み変更（`main.py` / `src/execution_history/` / `src/workflow_engine/` / `scripts/run_workflow_engine.py`）により無変更前提のArchitecture Guardが構造的にFAILする状態となった既存E2E36ファイル（本Releaseで`tests/`配下を変更した全ファイル、`test_e2e_v6_30_0`自身・`zero_diff_guard_registry.py`自身を除く）について、狭い除外編集を適用した後の実行結果を個別に記録するEvidence Appendixである。

**28章のFormal Regression Inventory（正式33ファイル、v1.11.0＋v5.9.0＋v6.0.0〜v6.30.0、5512/5512 PASS）とは別枠の記録であり、Formal Regression Inventory自体・その集計結果は本章により変更されない。** 本章は「Regression / Zero-Diff Evidence（共通要件）」（`docs/MVP_COMPLETION_ROADMAP.md` 303章）が求める「対象E2Eの一覧とPASS結果」「結果証跡」を、guard migration対象36ファインについて個別に補強するものである。

**実行環境**：`venv/Scripts/python.exe -B tests/<file>`（`PYTHONDONTWRITEBYTECODE=1`）。各ファイルは pytest ではなく独立実行スクリプト（`sys.exit(1)` on FAIL、実装内`print()`による結果サマリー）であり、コマンドはすべて同一パターン。実行日：2026-08-22。

**判定方法**：各ファイルの標準出力ログから合計PASS/FAIL件数とexit codeを記録した。「6.30 guard自体の結果」列は、当該ファイルのFAILメッセージ一覧に`main.py` / `execution_history` / `workflow_engine` / `run_workflow_engine.py`への言及が含まれるかを確認し、含まれない場合を「除外編集により当該guardはFAILしていないことを確認（PASS相当）」とした。「pre-existing FAIL原因分類」列は、FAILしたassertionが検証するsourceファイルがRelease 6.30の変更対象（`git status --short`）に含まれないことを個別に確認し、含まれない場合を「pre-existing、v6.30とは無関係」と分類した。

### 32.1 実行結果一覧（36ファイル）

| # | test file | 実行command | PASS/Total | FAIL | exit | v6.30 guard自体の結果 | pre-existing FAIL原因分類 |
|---|---|---|---|---|---|---|---|
| 1 | `test_e2e_v2_2_0_news_agent_foundation.py` | `python -B tests/test_e2e_v2_2_0_news_agent_foundation.py` | 121/121 | 0 | 0 | 除外編集によりFAILせず（テスト24「main.pyの差分確認はRelease 6.30以降の対象外」で明示スキップ） | 該当なし |
| 2 | `test_e2e_v2_3_0_workflow_trigger_agent_foundation.py` | 同上パターン | 108/108 | 0 | 0 | 除外編集によりFAILせず | 該当なし |
| 3 | `test_e2e_v2_4_0_publish_trigger_agent_foundation.py` | 同上パターン | 118/118 | 0 | 0 | 除外編集によりFAILせず | 該当なし |
| 4 | `test_e2e_v2_5_0_review_trigger_agent_foundation.py` | 同上パターン | 116/116 | 0 | 0 | 除外編集によりFAILせず | 該当なし |
| 5 | `test_e2e_v2_6_0_scheduler_agent_foundation.py` | 同上パターン | 117/117 | 0 | 0 | 除外編集によりFAILせず | 該当なし |
| 6 | `test_e2e_v2_7_0_workflow_engine_foundation.py` | 同上パターン | 162/162 | 0 | 0 | run_idベースAPIへ全面改訂済み（27章参照）、既存意味は維持 | 該当なし |
| 7 | `test_e2e_v2_8_0_execution_history_foundation.py` | 同上パターン | 199/199 | 0 | 0 | run_idベースAPIへ全面改訂済み（27章参照）、既存意味は維持 | 該当なし |
| 8 | `test_e2e_v2_9_0_workflow_monitor_foundation.py` | 同上パターン | 98/98 | 0 | 0 | run_idベースAPIへ全面改訂済み（27章参照）、既存意味は維持 | 該当なし |
| 9 | `test_e2e_v3_0_0_retry_engine_foundation.py` | 同上パターン | 198/202 | 4 | 1 | 除外編集によりFAILせず（テスト22相当） | pre-existing、v6.30とは無関係。テスト4（`RetryOutcome`4値定義）・テスト21×2（`retry_event_consumer.py`/`retry_manager.py`のscheduler非import）・テスト24（`dry_run=True`時`outcome`）。いずれも`src/retry_engine/`起因、本Releaseの変更対象外 |
| 10 | `test_e2e_v3_1_0_retry_queue_foundation.py` | 同上パターン | 148/148 | 0 | 0 | 除外編集によりFAILせず | 該当なし |
| 11 | `test_e2e_v3_2_0_retry_queue_integration.py` | 同上パターン | 94/96 | 2 | 1 | 除外編集によりFAILせず（テスト14相当） | pre-existing、`[KI-7]`既存差分（テスト16・17：`__all__`不変・`from_config()`第5引数） |
| 12 | `test_e2e_v3_3_0_retry_scheduler_integration.py` | 同上パターン | 70/71 | 1 | 1 | 除外編集によりFAILせず | pre-existing、v6.30とは無関係（未文書化）。テスト17（`retry_scheduler_source`参照先ファイル不存在）、`src/retry_scheduler_source/`系起因、本Releaseの変更対象外 |
| 13 | `test_e2e_v3_8_0_retry_engine_event_consumption.py` | 同上パターン | 66/69 | 3 | 1 | 除外編集によりFAILせず（テスト23相当） | pre-existing、v6.30とは無関係。テスト24（`__all__`構成）・テスト25×2（`__init__`/`from_config()`最終引数） |
| 14 | `test_e2e_v3_9_0_retry_engine_event_dispatch.py` | 同上パターン | 69/72 | 3 | 1 | 除外編集によりFAILせず（テスト19相当） | pre-existing、v6.30とは無関係。テスト20（`__all__`構成）・テスト21×2（`__init__`/`from_config()`最終引数） |
| 15 | `test_e2e_v4_0_0_retry_execution_foundation.py` | 同上パターン | 82/87 | 5 | 1 | 除外編集によりFAILせず（テスト24相当） | pre-existing、v6.30とは無関係。テスト25（`__all__`構成）・テスト26×4（`__init__`/`from_config()`の末尾・末尾から2番目引数） |
| 16 | `test_e2e_v4_1_0_retry_queue_update_foundation.py` | 同上パターン | 83/86 | 3 | 1 | 除外編集によりFAILせず（テスト21相当） | pre-existing、v6.30とは無関係。テスト22（`__all__`構成）・テスト23×2（`__init__`/`from_config()`最終引数） |
| 17 | `test_e2e_v4_2_0_retry_queue_removal_foundation.py` | 同上パターン | 90/93 | 3 | 1 | 除外編集によりFAILせず（テスト23相当） | pre-existing、v6.30とは無関係。テスト24（`__all__`構成）・テスト25×2（`__init__`/`from_config()`最終引数） |
| 18 | `test_e2e_v4_3_0_retry_queue_cleanup_foundation.py` | 同上パターン | 104/107 | 3 | 1 | 除外編集によりFAILせず（テスト31相当） | pre-existing、v6.30とは無関係。テスト32（`__all__`構成）・テスト33×2（`__init__`/`from_config()`末尾2引数） |
| 19 | `test_e2e_v4_4_0_retry_queue_notfound_disabled_cleanup_foundation.py` | 同上パターン | 119/122 | 3 | 1 | 除外編集によりFAILせず（テスト37相当） | pre-existing、v6.30とは無関係。テスト38（`__all__`構成）・テスト39×2（`__init__`/`from_config()`末尾2引数） |
| 20 | `test_e2e_v4_5_0_retry_policy_foundation.py` | 同上パターン | 62/63 | 1 | 1 | 除外編集によりFAILせず（テスト4相当） | pre-existing、v6.30とは無関係。テスト11（`__all__`構成） |
| 21 | `test_e2e_v4_6_0_retry_enqueue_trigger_foundation.py` | 同上パターン | 96/99 | 3 | 1 | 除外編集によりFAILせず | pre-existing、v6.30とは無関係（未文書化）。テスト12（`__init__`パラメータ）・テスト16（`__init__.py`/`retry_enqueue_trigger.py`構成）・テスト18（参照先ファイル不存在）、`src/retry_enqueue_trigger/`起因、本Releaseの変更対象外 |
| 22 | `test_e2e_v4_7_0_retry_history_foundation.py` | 同上パターン | 177/177 | 0 | 0 | 除外編集によりFAILせず（テスト29相当） | 該当なし |
| 23 | `test_e2e_v4_8_0_retry_enqueue_guard.py` | 同上パターン | クラッシュ（テスト1到達前に例外） | N/A | 1 | **guard未到達**（`git diff`関連テストへ到達する前に無関係の例外でクラッシュするため、除外編集の効果自体は本実行では検証できていない。静的には`unchanged_paths`から`main.py`が除外されていることをgit diffで確認済み） | pre-existing、v6.30とは無関係（未文書化）。`RetryEnqueueGuard.decide()`（`src/retry_enqueue_trigger/retry_enqueue_guard.py`、本Releaseの変更対象外）が`has_history`引数を受け付けず`TypeError`。同ソースはgit statusで無変更を確認済み |
| 24 | `test_e2e_v4_9_0_retry_attempt_synchronization_foundation.py` | 同上パターン | クラッシュ（テスト2で例外） | N/A | 1 | **guard未到達**（同上、`git diff`関連テスト到達前にクラッシュするため除外編集の効果自体は本実行では検証できていない。静的な除外編集の適用自体はgit diffで確認済み） | pre-existing、v6.30とは無関係（未文書化）。テスト内Fake`_AlwaysAllowGuard.decide()`が`next_attempt`引数を受け付けず`TypeError`（`src/retry_enqueue_trigger/retry_enqueue_trigger.py`起因、本Releaseの変更対象外） |
| 25 | `test_e2e_v5_0_0_retry_enqueue_guard_refinement_foundation.py` | 同上パターン | 107/109 | 2 | 1 | 除外編集によりFAILせず | pre-existing、v6.30とは無関係（未文書化）。テスト16（パラメータ構成）・テスト22（参照先ファイル不存在） |
| 26 | `test_e2e_v5_1_0_retry_composition_root_foundation.py` | 同上パターン | 36/38 | 2 | 1 | 除外編集によりFAILせず（テスト19相当） | pre-existing、v6.30とは無関係。テスト15（パラメータ構成）・テスト20（参照先ファイル不存在） |
| 27 | `test_e2e_v5_2_0_retry_runtime_orchestrator_foundation.py` | 同上パターン | 49/54 | 5 | 1 | 除外編集によりFAILせず（テスト24相当） | pre-existing、v6.30とは無関係。テスト18×2（公開メソッド構成）・テスト22（ファイル構成）・テスト23（`__all__`）・テスト25（参照先ファイル不存在） |
| 28 | `test_e2e_v5_3_0_retry_runtime_run_once_foundation.py` | 同上パターン | 53/54 | 1 | 1 | 除外編集によりFAILせず（テスト28相当） | pre-existing、v6.30とは無関係。テスト2（パラメータ構成） |
| 29 | `test_e2e_v5_4_0_retry_runtime_script_entry_point_foundation.py` | 同上パターン | 65/66 | 1 | 1 | 除外編集によりFAILせず（テスト15・16相当） | pre-existing、v6.30とは無関係。テスト7（`argparse`未import） |
| 30 | `test_e2e_v5_5_0_retry_runtime_loop_foundation.py` | 同上パターン | 36/37 | 1 | 1 | 除外編集によりFAILせず | pre-existing、v6.30とは無関係（未文書化）。テスト16（参照先ファイル不存在） |
| 31 | `test_e2e_v5_6_0_retry_runtime_safe_dry_run_foundation.py` | 同上パターン | 45/49 | 4 | 1 | 除外編集によりFAILせず（テスト23相当） | pre-existing、v6.30とは無関係。テスト16・18・19・20（`dry_run`関連の別問題） |
| 32 | `test_e2e_v5_7_0_retry_runtime_safe_dry_run_wiring_foundation.py` | 同上パターン | 85/85 | 0 | 0 | 除外編集によりFAILせず | 該当なし |
| 33 | `test_e2e_v5_8_0_retry_enqueue_trigger_dry_run_foundation.py` | 同上パターン | 64/64 | 0 | 0 | 除外編集によりFAILせず（テスト17相当） | 該当なし |
| 34 | `test_e2e_v5_9_0_retry_runtime_loop_wiring_foundation.py` | 同上パターン | 64/64 | 0 | 0 | 除外編集によりFAILせず | 該当なし |
| 35 | `test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py` | 同上パターン | 119/119 | 0 | 0 | 除外編集によりFAILせず（ZERODIFF-4「main.pyの差分確認はRelease 6.30以降の対象外」で明示スキップ） | 該当なし |
| 36 | `test_e2e_v6_28_0_article_media_upload_state_foundation.py` | 同上パターン | 187/187 | 0 | 0 | 除外編集によりFAILせず | 該当なし |

参考（新規ファイル、本表の対象外）：`test_e2e_v6_30_0_production_canonical_run_outcome_contract_foundation.py`は120/120 PASS・exit 0（`docs/CHANGELOG.md` [v6.30.0] Tested節に記載、2026-08-22の再実行で確認）。

### 32.2 検証手法の限界

- 本章の実行はRelease 6.30のcommit前・working tree状態（未commit差分を含む）に対して行った。commit後の再実行は本章の対象外。
- 「pre-existing、v6.30とは無関係」の分類は、当該FAILが検証するsourceファイルが本Releaseの`git status --short`に現れないことの確認に基づく（`[KI-4]` 2026-07-03追記と同型の手法。ただし本章では`git stash`によるベースライン再現は環境上の制約により実施しておらず、source無変更の確認のみで判定した）。
- 「未文書化」と付記した項目（v3.3.0テスト17・v4.6.0テスト12/16/18・v4.8.0テスト1・v4.9.0テスト2・v5.0.0テスト16/22・v5.5.0テスト16）は、既存`[KI-1]`〜`[KI-29]`のいずれにも対応しない新規発見のpre-existing差分であり、本Releaseの対応範囲外として別途整理を要する課題に留める（`[KI-30]`今後の対応、参照）。
- **訂正履歴（2026-08-22）**：Codex Final Release Review（独立新規スレッド、read-only、reasoning effort High）の指摘を受け、以下を訂正した。(1) 32.1表のv4.8.0・v4.9.0行について、「除外編集によりFAILせず」という表現が、guardへ実行が到達していないにもかかわらず「FAILしていない」と断定的に読めるとの指摘を受け、「guard未到達（除外編集の効果自体は本実行では検証できていない）」へ訂正した。(2) 本Releaseの承認済み変更対象に含まれない`src/workflow_engine/workflow_engine_manager.py`へdocstringのみの編集を追加したことで、本章が前提とするguard許容リスト（v2.9.0・v3.0.0等の個別ファイルチェック、v5.1.0〜v5.9.0の`_ALLOWED_WORKFLOW_ENGINE_CHANGES_32`集合、計13ファイル）が新たにFAILする状態を検出したが、当該docstring編集自体を取り消すことで本章の32.1表（reversion前に実行・記録した内容）が正しい状態に復帰することを確認した（`workflow_engine_manager.py`はRelease 6.30の変更対象に含まれないため、本章のガード許容リスト自体の変更は不要と判断した）。
