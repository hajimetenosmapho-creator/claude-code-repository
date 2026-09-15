# Scheduler Driver & Duplicate Dispatch Safety — Architecture Design（Release 6.34）

## 0. Status

- **Status: DRAFT（Codex `codex-readonly-review` Round 1〜5実施済み、Round 5で`VERDICT: APPROVED`取得。Human Gate Checklist（26章）承認待ち）**
- Round 1（2026-09-16実施）：`VERDICT: NOT APPROVED`（Blocking 2件・Major 4件・Minor 2件）。Blocking 2件（single-active-driverのstale-lock解除時の安全性未確立／durable ledgerのstore-level失敗時fail-closed契約未定義）・Major 4件（retry-candidate除外がprefix頼みで脆弱／production schedule source一元化が未確定のまま残存／Scheduler-Retry並行実行時の安全性主張が過大／crash matrixのledger I/O失敗系統の欠落）を反映した（12章・8.5節・9.2節・16章・14章・18章）。Minor 2件（Planned File Impactの内部不整合／DST境界でのidentity衝突）も反映した（7章・22章）。
- Round 2（2026-09-16実施）：Round 1修正版に対し再度`VERDICT: NOT APPROVED`（Blocking 2件・Major 2件・Minor 1件）。Blocking 2件（Ownership-Integrity Self-Checkがcycle境界のみの検証でありcycle処理中に奪われたlockを終了処理で無条件release()してしまう残存経路が未解消だった／`run_once()`擬似コードに自己検証呼び出しが欠落していた／reconciliationのrecord単位read/parse/schema検証失敗と複数CLAIMED処理時の部分失敗が未定義だった）・Major 2件（positive allowlistが`job_id`という値に依拠し続けており将来のretry候補event表現変化に対して本質的には脆弱だった／`scripts/run_workflow_engine.py`の置換仕様が型不一致で実装不能だった）を、12.1〜12.2節（Lock Lifecycle Contract新設）・8.5節(4)（read-then-write順序・per-record locking・部分失敗時の扱い明確化）・16章（`metadata["retry_candidate"]`ベースのprovenance判定への再改訂）・9.2節（登録/イベント選択/診断メッセージの具体的置換仕様確定）で反映した。Minor 1件（複数箇所の古い章番号参照）も修正した（6.1・7・14・6.4節）。
- Round 3（2026-09-16実施）：Round 2修正版に対し再度`VERDICT: NOT APPROVED`（Blocking 2件・Major 2件・Minor 2件）。Blocking 2件（起動時ownership検証が`try`ブロックの外にありcleanup保護を受けずlockをleakしうる経路が残っていた／reconciliationの書き込みフェーズがper-recordロック取得後にfresh readで鮮度を再確認しておらず、TOCTOU残存window中に他driverが正当に進めた`CONFIRMED`状態を`RECOVERY_REQUIRED`で上書きしうる欠陥があった）・Major 2件（「構造的に遮断」等の無条件表現が、同時に認めていたTOCTOU残存リスクと矛盾していた／`_release_if_owned()`の定義場所（`src/scheduler_driver/`）と唯一の呼び出し箇所（`scripts/run_scheduler_driver.py`）の関係が文書内で曖昧だった）を、12.1〜12.2節（起動時検証を`try`ブロック内側へ移動、定義場所と呼び出し箇所の区別を明記、TOCTOU残存リスクを「Accepted・Low確率・未解消」として一貫した限定付き表現へ全面統一）・8.5節(4)(c)（fresh-read-under-lock契約を`retry_lineage`既存precedentと同型で追加）で反映した。Minor 2件（8.4節の古い「1 cycle分」表現／`finally`の限界の過大な一般化）も修正した。Suggestions 2件（reconciliationのfresh read関連テスト追加／`metadata["retry_candidate"]`予約キー運用規約の明記）も反映した（16章・23章）。
- Round 4（2026-09-16実施）：Round 3修正版に対し`VERDICT: NOT APPROVED`（**Blocking 0件**・Major 1件・Minor 2件・Suggestions 1件）。Blockingは解消済みと確認された。Major 1件（8.2節・8.4節が、TOCTOU残存window中に「もう一方のdriverが真に処理中（未confirm）のCLAIMED record」をreconciliationが誤って`RECOVERY_REQUIRED`へ遷移させうる可能性を、無条件の「orphanと構造的に断定できる」という表現のまま残していた——duplicate dispatchには至らないが絶対的な主張と矛盾していた）を、8.2節・8.4節の限定付き表現への修正、およびconfirm()契約がこのケースを安全に処理する仕組みの明記で反映した。Minor 2件（12.2節にRound 2版とRound 3版のTOCTOU残存リスクの説明が2つ並存し矛盾していた／`_release_if_owned()`の例外捕捉範囲の記述がコード（`OSError`のみ）より広く書かれていた）を、重複パラグラフの削除、および捕捉範囲を`Exception`へ広げてコードと記述を一致させることで反映した。Suggestion 1件（起動直後にownership検証が失敗する稀なケースのテスト追加）は23章に反映した。
- **Round 5（2026-09-16実施）：`VERDICT: APPROVED`（Blocking 0件・Major 0件・Minor 1件・Suggestions 1件）。** Round 4の修正がBlocking/Major指摘をすべて解消したことを確認した上での承認。Minor 1件（Rejected Alternatives #7に旧版（positive allowlistが一次機構）のままの説明が残存していた／用語集「Production Schedule Source」の章番号参照が9章ではなく10章になっていた／`SchedulerDriverConfig`のgate参照が誤って11.2節（Restart Recovery）を指していた）とSuggestion 1件（Test Strategy項目13のタイトルがTOCTOU残存window外という限定を明示していなかった）は、Blocking/Majorではないため追加レビューを経ずに本改訂で直接反映した（24章#7・5章・17.2節・23章項目13）。
- 本書はRelease 6.34「Scheduler Driver & Duplicate Dispatch Safety」のArchitecture Phase成果物である。
- Baseline: branch `main`, HEAD=origin/main=`e1375161c6980c0632c0d3e7084d036dc5a24dc3`, Working Tree clean, Release 6.33.0完了済み（Formal Regression 35 files / 5853/5853 PASS）。
- 本フェーズではコード実装（`src/` / `scripts/` / `tests/`）は一切行わない。本書とこのファイル自体のみが成果物である。
- scopeは `docs/MVP_COMPLETION_ROADMAP.md` v1.3が定めるRelease 6.34の記述をユーザーが承認済み。本書はそのscope内でのArchitecture設計のみを行い、scope変更は提案しない（scope変更が必要と判明した場合は実装せずHuman Gateとして報告する。27章参照）。

---

## 1. Background / Motivation

`docs/MVP_COMPLETION_ROADMAP.md`（v1.3）は、Release 6.30〜6.33で以下を確立済みである：

- **6.30**：`WorkflowEngineManager.run()` を起点とするMVP本番canonical run契約（`CanonicalAdmissionFailure`、「1 production invocation = 1 canonical retryable record」原則、Governance Exception）
- **6.31**：`RetryLineageManager` による `root_run_id` 単位のretry lineage・4-phase attempt lifecycle（`READY_ELIGIBLE → CLAIMED → EXECUTION_STARTED → TERMINAL`）・`RetryExecutionLock` による排他境界
- **6.32**：外部副作用のwrite-ahead fail-closed契約・durable `HUMAN_REVIEW_REQUIRED` terminal disposition（Protected Operation Manifest）
- **6.33**：`RetryObservabilityPipeline` のRetry Runtimeへの実配線

一方、`SchedulerEngine`（`src/scheduler/`, v2.6.0）は判定のみを行う純粋関数として存在するが、これを**定期的に駆動しproduction workflowへ配線するdriver**は存在しない。現状の唯一の起動経路は `scripts/run_workflow_engine.py` の手動単発実行であり、かつ同スクリプトはhard-codedなデモJob（`DEMO_JOB_ID = "workflow_engine_demo_daily"`）を都度その場で登録している（本書6.3節）。

Release 6.34は、この「駆動方式の未確立」というGapを解消し、`SchedulerEngine` のpure性を保ったまま、再起動・クラッシュ・多重driverに対してもduplicate dispatchをfail-closedで防止するruntime boundaryを設計する。

---

## 2. Scope（Roadmap v1.3準拠、ユーザー承認済み）

### In Scope

1. loop driver（`scripts/run_retry_runtime.py --loop` と同系統）
2. production schedule sourceの一元化
3. stable event identity
4. durable dispatch ledger
5. fail-closed dispatch契約
6. claim→dispatch間のcrash safety契約
7. single-active-driver制約
8. Scheduler event → production workflow dispatch
9. production workflow起動配線
10. Retry Runtimeとのownership／プロセス排他の定義

### Out of Scope（本Releaseでは一切変更しない）

- Windows Task Scheduler等のOS固有統合
- `RECOVERY_REQUIRED` occurrenceの自動復旧
- `release_claim()` Suggestion（`src/retry_engine/retry_executor.py`、6.32 Final Review由来、Out of Scopeのまま）
- Retry lineage／eligibility／attempt contractの変更（`src/retry_lineage/`, `src/retry_engine/`, `src/retry_queue/`, `src/retry_history/`, `src/retry_composition/`, `src/retry_enqueue_trigger/`, `src/retry_runtime_orchestrator/` はいずれもZero-Diff）
- v6.33 Observability拡張（`src/retry_runtime_observability/`, `src/retry_observability_pipeline/` はZero-Diff）
- SNS等の新規production write
- Universal Assets / human-gate / Global settings / Remote Tunnel / plugin変更
- post-MVP機能全般

---

## 3. Goals

- G1. `SchedulerEngine.evaluate()` / `run_due()` の純粋性（副作用ゼロ・外部状態を`now`以外参照しない）を一切変更しない。
- G2. 同一の論理occurrence（`job_id` × 実行されるべき時刻）に対して、production workflowの起動（`WorkflowEngineManager.run()` の呼び出し）が二重に発生しないことを、プロセス再起動・同一分内の複数tick・複数driver同時起動のいずれに対しても保証する。
- G3. claim（占有の記録）とdispatch（実際の起動）の間でプロセスが停止した場合、自動的に再dispatchせず、fail-closedで`RECOVERY_REQUIRED`相当として観測可能な形にする。
- G4. dispatch結果が確定的に判定できない場合（ambiguous outcome）は、常に「再dispatchしない」側へ倒す。
- G5. production schedule source（Job定義の唯一の供給元）を一元化し、`scripts/run_workflow_engine.py` のhard-coded demo jobをそのまま転用しない。
- G6. Retry Runtimeの既存ownership／state machine（`retry_lineage`, `retry_engine`）を一切拡張・変更せず、Scheduler DriverとRetry Runtimeが独立したプロセスとして安全に共存できる境界を定義する。
- G7. 既存の再利用可能な汎用コンポーネント（`RetryRuntimeLock` / `RetryRuntimeLoop` / `RetryRuntimeShutdown`）を、その汎用性（ドキュメント上「Retryドメインを一切知らない」と明記済み）を根拠に転用し、車輪の再発明を避ける。

## 4. Non-Goals（Out of Scope、詳細）

- `RECOVERY_REQUIRED` になったoccurrenceを自動的に再dispatchする仕組み（N1）
- `job_id` の衝突検出・namespace管理の高度化（N2、既存 `retry_scheduler_event_integration` の `job_id` prefix衝突未解決問題と同種だが、本Releaseでは対処しない）
- Dispatch Ledgerの完全な監視UI／Dashboard／外部通知（N3。読み取り専用の診断APIは設計するが、新規CLIスクリプトの実装確約はしない）
- cron式・複数Job設定ファイル化（`SchedulerJob` / `SchedulerEngine` 自体の拡張、N4。v2.6.0の既存Non-Goalsを継承）
- WordPress側の重複防止・冪等性の強化（N5、6.32 Protected Operation Manifestの責務のまま不変）

---

## 5. 用語・キー概念

| 用語 | 定義 |
|---|---|
| **Scheduled Occurrence** | `SchedulerJob` が「実行されるべき」と判定された、特定の1分単位の時刻インスタンス。`SchedulerEngine._match_*()` はいずれも分単位マッチングのため、同一Jobの同一分内の複数回評価は同一occurrenceを指す。 |
| **Stable Event Identity** | `(job_id, occurrence_minute)` の組。プロセス再起動をまたいでも同じ入力（同じJob定義・同じ時刻）から常に同じ値が導出される（8章）。 |
| **Dispatch Ledger** | stable event identityごとのdispatch記録を保持するdurable store（新規、9章）。 |
| **Claim** | 特定のstable event identityについて「これからdispatchを試みる」ことをdispatch**前**にdurableに記録する操作。 |
| **Confirm** | dispatch（`WorkflowEngineManager.run()` 呼び出し）が完了した（成功・例外いずれも含む）ことをdurableに記録する操作。 |
| **RECOVERY_REQUIRED** | claim済みだがconfirmされないまま次回の再起動／reconciliationに到達したentryの終端状態。自動復旧しない（Out of Scope）。 |
| **Production Schedule Source** | production JobのSchedulerJob定義を保持する唯一の供給元（9章）。 |
| **Single-Active-Driver** | Scheduler Driverプロセスが同時に1つしか有効に動作しないことを保証する制約（12章）。 |

---

## 6. Existing Architecture Findings（既存実装調査）

### 6.1 `SchedulerEngine` のpure boundary

`src/scheduler/scheduler_engine.py`：

- `evaluate(jobs, now, retry_limit=None) -> list[SchedulerEvent]` はdocstring上「副作用なしの純粋関数」と明記されている（`:128-135`）。`disabled` Jobの除外、`_match()` による分単位マッチングのみを行い、ファイルI/O・状態更新を一切行わない。
- `run_due(jobs, retry_limit=None)` は `ClockProvider.now()` を取得して `evaluate()` を呼ぶだけの薄いconvenienceメソッド（`:164-170`）。
- **重要な既存事実**：`evaluate()` は v3.7.0（Retry Scheduler Event Integration）以降、`_build_retry_events()` の結果を `events.extend()` で追加連結している（`:161`）。`_retry_decision` が `None`（デフォルト）であれば空リストが返るため、通常の呼び出し（`SchedulerEngine()` を引数なしで構築するケース）では影響しないが、**`retry_decision` を注入したSchedulerEngineインスタンスを使うと、戻り値の `SchedulerEvent` に `job_id="retry:" + run_id` という形式のretry候補由来イベントが混入しうる**（`:248-257`）。これらは `metadata={"retry_candidate": <object>}` を持ち、Retry Engine起動やQueue操作へは到達しない「観測専用」の設計になっている（`scheduler_engine.py` 冒頭docstring `:57-75`）。
- **Finding F1（Critical）**：Scheduler Driverが `SchedulerEngine.evaluate()` / `run_due()` の戻り値を無条件にproduction workflow dispatch対象として扱うと、将来 `retry_decision` が注入された構成で `job_id` が `"retry:"` プレフィックスを持つイベントまでもが `WorkflowEngineManager.run()` へ渡されうる。これは、Retry Runtimeが `RetryLineageManager`（`claim()` / `mark_execution_started()` / `mark_terminal()`）を通じて既に厳密に管理しているretry実行経路の**外側**から、同じ論理的な再実行を別ルートで起動してしまうリスクを意味する。この経路は6.31/6.32のlineage・fail-closed契約を一切経由しないため、二重実行・duplicate side effectの温床になりうる（16章 Design Decision Jで対処）。

### 6.2 Production workflow entry point

`src/workflow_engine/workflow_engine_manager.py` `WorkflowEngineManager.run()`（`:153-183`）：

```python
def run(self, event: WorkflowEngineEvent, dry_run: bool = False,
        target_step_filter=None, post_admission_hook=None,
        correlation_metadata=None, side_effect_execution_provenance=None) -> WorkflowEngineResult:
    context = WorkflowEngineContext(
        event=event, dry_run=dry_run, run_id=self._generate_run_id(),
        ...
    )
    return self._executor.run(context)
```

- `run_id` は `run()` 呼び出しの**内部**で `uuid.uuid4().hex` により毎回新規生成される（`:186-187`）。呼び出し側（driver）は事前にrun_idを知ることができない。
- `NullWorkflowEngineManager.run()`（gate OFF時）はno-opで `None` を返す（`:190-212`）。
- `CanonicalAdmissionFailure(run_id, reason)`（`src/workflow_engine/workflow_engine_exceptions.py:20-26`）は `ExecutionHistoryManager.start_run()` のdurable ack失敗時に送出される。`reason` は `"EXECUTION_HISTORY_DISABLED"` または `"START_RUN_ACK_FAILED"` の2値（architecture.md 5712-5716行）。この例外は `run_id` 属性を保持するため、dispatch側でcatchすれば診断用のrun_idを得られる。
- **「1 production invocation = 1 canonical retryable record」原則**（`docs/MVP_COMPLETION_ROADMAP.md`）と、それに対する明示的Governance Exception（`CanonicalAdmissionFailure` 発生時、durable canonical recordが存在しない状態になりうる。6.30で承認済み、architecture.md 5730行）が既に存在する。**Scheduler Driverはこの原則・Exceptionのいずれも変更しない**。Driver側のdispatch ledgerは、この原則の"上位"（`.run()` を呼ぶかどうかの決定）を保護するものであり、`.run()` 内部のcanonical admission契約とは独立した別レイヤーの安全機構である（10章・14章）。

### 6.3 既存hard-coded schedule source

`scripts/run_workflow_engine.py`（`:99-152`）：

- `DEMO_JOB_ID = "workflow_engine_demo_daily"`、`build_demo_job()` が固定1件のJob（`TriggerType.DAILY`, `schedule="09:00"`）をその場で構築し、`InMemorySchedulerRepository` へ都度登録している。
- `resolve_event(args)` がScheduler経由・`--job-id`手動経由の2経路を切り替える。
- 本スクリプト自体は「手動実行用のCLIエントリスクリプト」と明記されており（docstring `:1-7`）、繰り返し駆動（loop）・複数Job・排他制御のいずれも持たない。docstring `:57-62` は「本スクリプトと `scripts/run_news_agent.py` 等のAgentManager経由の既存script群を同時に実行しないこと」という**運用上の制約（コードによる強制ではない）**を明記している。
- **Finding F2**：`docs/MVP_COMPLETION_ROADMAP.md` が要求する「production schedule sourceの一元化：`scripts/run_workflow_engine.py` のhard-coded demo jobをそのままproduction schedule sourceに転用しない」は、このコードの現状（デモJobがスクリプトローカルに埋め込まれている）を正確に指している。

### 6.4 既存loop driver／lock／shutdown component（再利用候補）

いずれも `src/retry_runtime_lock/`, `src/retry_runtime_loop/`, `src/retry_runtime_shutdown/` にあるが、**3クラスとも自身のdocstringで明示的に「Retryドメインを一切知らない汎用コンポーネント」と宣言している**：

- `RetryRuntimeLock`（`retry_runtime_lock.py:36-85`）：`os.open(O_CREAT|O_EXCL)` によるファイル存在ベースの排他制御のみ。他のretry_*パッケージのいずれにも依存しない（docstring `:10-11`）。PID書き込みは診断目的のみ、stale lock自動解除は行わない（`:12-14`）。`with` 文で `acquire()`/`release()`。
- `RetryRuntimeLoop`（`retry_runtime_loop.py:27-61`）：`run_once_fn` / `sleep_fn` / `should_continue_fn` を保持し `while should_continue_fn(): run_once_fn(); sleep_fn(interval)` を回すだけ。`RetryManager` 等いずれも知らない（docstring `:11-12`）。例外はfail-fastで伝播。
- `RetryRuntimeShutdown`（`retry_runtime_shutdown.py:1-25`）：SIGINT/SIGBREAK/SIGTERMハンドラを登録しフラグを立てるだけ。`RetryRuntimeLoop` とは関数参照のみで疎結合（DIのみ）。他のretry_*パッケージに依存しない。

**Finding F3（設計方針への採用）**：この3クラスは名前に`Retry`を冠するが、実装・契約ともに完全にドメイン非依存であることが自己文書化されている。Scheduler Driverはこれらを**そのままimportして再利用**し、新規に同等のクラスを複製しない（17章）。名前が`Retry`である点はミスリーディングだが、リネームは既存パッケージへの変更を意味し「scope外変更は禁止」に抵触するため、本Releaseでは行わない（25章R4のRiskとして記録し、26章のArchitecture Gate Checklistで承認確認する）。

`scripts/run_retry_runtime.py` の `main()`（`:203-281`）は、`RetryRuntimeLock` → `RetryCompositionRoot.from_env()` → `RetryRuntimeOrchestrator` → `cycle_logger` → （`--loop` 時のみ）`RetryRuntimeShutdown` + `RetryRuntimeLoop` という組み立て順序のテンプレートを提供している。Scheduler Driverの `scripts/run_scheduler_driver.py`（21章）はこの型をなぞる。

### 6.5 Retry Runtimeの既存ownership／state machine（変更しない領域）

`src/retry_lineage/retry_lineage_manager.py`：

- `RetryExecutionLock`（`retry_execution_lock.py`）：`RetryManager.retry()` と `RetryLineageManager.reconcile_all()` 双方にとって唯一の実行時排他境界。同一プロセス内の2回目取得もブロックせず即失敗（`:14-18`）。
- 4-phase state machine（`READY_ELIGIBLE → CLAIMED → EXECUTION_STARTED → TERMINAL`）、`owner_token` による4段階authority check（`_verify_owner_authority()`, `:97-108`）。
- `reconcile_all()` は `phase==EXECUTION_STARTED` のorphan解決（`:729-`）と `phase==CLAIMED` のorphan回収（`:798-836`、owner_token非依存、`RetryExecutionLock` 保有＝reconciliation実行権という別モデル）の両方を扱う。

**この一連のメカニズムはScheduler Driverから一切参照・変更しない**。Scheduler Driverの新規dispatch ledgerは、これとは独立した、より単純な（4-phaseではなく後述3-phaseの、owner_token authorityを持たない）別個のメカニズムとして設計する（8章）。両者を混同・統合しないことが本Releaseの重要な設計境界である（14章）。

### 6.6 `.env` gate命名規約

既存gateは `<DOMAIN>_ENABLED` （デフォルト`false`が安全側の原則。例外は外部I/Oを持たないもの、`.env.example:42,54-56`）の形式に統一されている。`RetryLineageConfig.from_env()`（`retry_lineage_config.py:29-36`）は `RETRY_LINEAGE_ENABLED`（デフォルトfalse）・`RETRY_LINEAGE_DIR`（デフォルト `state/retry_lineage`）という2変数パターンを取る。Scheduler Driverもこの規約を踏襲する（11章）。

---

## 7. Design Decision A：Stable Event Identity

**決定**：stable event identityを `(job_id, occurrence_minute)` の組とし、`occurrence_minute` は `SchedulerEvent.execute_time` を `"%Y-%m-%dT%H:%M"` 形式（分単位切り捨て）で文字列化した値とする。

```
event_identity = f"{job_id}::{execute_time:%Y-%m-%dT%H:%M}"
```

**根拠**：

- `SchedulerEngine._match_daily()` / `_match_interval()` / `_match_once()` はいずれも `now.strftime("%H:%M")` または同等の分単位比較のみで判定しており（`scheduler_engine.py:272-301`）、秒・マイクロ秒の情報は判定に一切使われない。`SchedulerEvent.execute_time` には呼び出し時点の `now`（多くの場合秒単位まで含む datetime）がそのまま入るため、**`execute_time` を直接キーにすると「同一分内の複数tick」が異なる identity として扱われてしまい、G2（同一分内複数tickでのduplicate suppression）を満たせない**。分単位への正規化が必須。
- `job_id` を含めることで、異なるJob間のidentity衝突を防ぐ。
- 再起動をまたいでも、同じJob定義・同じ実時刻であれば同じ `event_identity` が導出される（決定性）。driver側が独自のカウンタや前回実行時刻を保持する必要がない。
- Retry候補由来のイベント（`job_id="retry:" + run_id`）は、そもそも本ledgerの対象外とする（16章 Design Decision J）ため、identity方式の衝突を考慮する必要はない。

**却下した代案**：`execute_time` をそのまま（秒精度で）キーにする案 → 同一分内複数tickの重複防止という明示的Completion Criteria（Roadmap「同一分内の複数tickでの重複dispatch防止」）を満たせないため却下。

**Minor開示（Codex Round 1 N2対応）**：`"%Y-%m-%dT%H:%M"` はnaiveなwall-clock文字列であり、タイムゾーン・UTC offset・DST fold情報を持たない。DST切替（夏時間の終了等でwall-clockが1時間巻き戻る環境）が発生する場合、理論上は異なる2つの実時刻が同じ`occurrence_minute`文字列に収束しうる。ただし、これは本書が新規に持ち込む欠陥ではなく、`SchedulerEngine._match_daily()`/`_match_interval()`/`_match_once()`自体が既にnaive `datetime.now()`ベースの文字列比較のみで判定しており（`scheduler_engine.py:272-301`）、DST・タイムゾーンを一切考慮しない設計をv2.6.0から踏襲している（同モジュールの既存Non-Goals）。本Releaseは`SchedulerEngine`の判定ロジック自体をZero-Diffとするため、この限界を解消することはOut of Scopeとし、既存の既知の単純化を追加のドキュメント化なしに引き継ぐのではなく、ここに明示する。

---

## 8. Design Decision B：Dispatch Ledger — Schema / Lifecycle / Durability

### 8.1 新規パッケージ `src/scheduler_dispatch_ledger/`

`retry_lineage` の実装パターン（JSON per-record file、atomic save、read-check-writeをOS-backed lockで保護）を踏襲するが、**4-phaseではなく3-phase**、**owner_token authorityなし**の、より単純なモデルとする（8.4節で理由を述べる）。

```python
class DispatchPhase(Enum):
    CLAIMED = "claimed"
    CONFIRMED = "confirmed"
    RECOVERY_REQUIRED = "recovery_required"


@dataclass
class DispatchLedgerEntry:
    event_identity: str          # f"{job_id}::{occurrence_minute}"
    job_id: str
    occurrence_minute: str
    phase: DispatchPhase
    claimed_at: datetime
    confirmed_at: datetime | None = None
    dispatch_run_id: str | None = None      # best-effort診断用（8.3節）
    outcome_summary: str | None = None      # best-effort診断用
    detail: str | None = None
    updated_at: datetime = field(default_factory=datetime.now)
```

### 8.2 Lifecycle（write-once-forward-only）

```
(record absent) --claim()--> CLAIMED --confirm()--> CONFIRMED   [terminal]
                                  |
                                  +--(reconcile、次回起動/次サイクル先頭)--> RECOVERY_REQUIRED  [terminal]
```

- `claim(event_identity, job_id, occurrence_minute) -> ClaimResult(acknowledged: bool, reason: str | None)`
  - recordが**存在しない**場合のみ、`phase=CLAIMED` として新規保存を試み、保存成功（durable ack）を `acknowledged=True` として返す。
  - recordが既に存在する場合（`CLAIMED` / `CONFIRMED` / `RECOVERY_REQUIRED` いずれでも）は無条件に `acknowledged=False` を返す（re-claim禁止。これ1点だけで「同一identityの二重claim」が構造的に不可能になる）。
  - 保存自体が失敗した場合（`store.save()` がFalse）も `acknowledged=False`。
- `confirm(event_identity, run_id: str | None, outcome_summary: str) -> bool`
  - 既存recordの `phase` が `CLAIMED` であることを要求する。異なる場合（invariant violation。通常経路では発生しない）は何も書き込まずFalseを返す（no auto-repair、`retry_lineage` の `claim()` invariant violation処理と同じ哲学）。
  - 正常時は `phase=CONFIRMED`, `confirmed_at=now`, `dispatch_run_id=run_id`, `outcome_summary=outcome_summary` を書き込み、保存成功可否（bool）を返す。
  - **戻り値は呼び出し側（Orchestrator、13章）が必ず確認する**（6.32 Suggestionと同種のgapを新規に作り込まないための明示的設計原則）。`confirm()` がFalseを返した場合、そのentryは `CLAIMED` のまま残り、次回reconciliationで安全側（`RECOVERY_REQUIRED`）へ倒れる（8.2節の図の通り。過検知にはなるが安全方向の誤りである。25章で許容トレードオフとして明記）。**この`phase==CLAIMED`要求は、下記8.4節で述べるTOCTOU残存windowシナリオ（他driverが真に処理中の`CLAIMED` recordを、reconciliationが誤って`RECOVERY_REQUIRED`へ遷移させてしまうケース）に対する安全網としても機能する**：この場合、実際に処理していたdriverが後で`confirm()`を呼んでも`phase`が既に`RECOVERY_REQUIRED`（`CLAIMED`ではない）であるため`confirm()`はFalseを返し書き込まない——結果として、実際にはdispatchが成功していたにもかかわらずledger上は`RECOVERY_REQUIRED`のまま残る（診断上の過検知）が、二重dispatchやconfirmed状態の不整合な上書きは発生しない。
- `reconcile_stale_claims() -> ReconcileSummary(recovery_marked: int)`
  - 全recordを走査し、`phase==CLAIMED` のものをすべて `phase=RECOVERY_REQUIRED` へ遷移させる（confirmed_atは設定しない）。
  - **呼び出しタイミング**：driver起動時（loop開始前）、および**各cycle開始時（次のevaluate()呼び出しの前）**の両方。single-threaded・非reentrantな設計（13章）により、**単一driverプロセス内では**この2箇所以外で `CLAIMED` のrecordが「正当な処理中」である瞬間は存在しない（claim→dispatch→confirmが同一関数呼び出し内で同期的に完結するため）。**限定付きの主張（Codex Round 4 Major#1対応）**：これは「単一driverプロセスが唯一のclaimantである」という前提の下でのみ成立する。12.2節のTOCTOU残存windowの中で、もう一方のdriverが正当に`claim()`を実行し、そのentryがまだ`confirm()`に到達していない（＝真に処理中の）状態にある場合、reconciliationを実行している側のdriverから見ると、この`CLAIMED` recordは「orphanかどうか区別できない」まま存在しうる。この場合でも、8.5節(4)(c)のfresh-read-under-lock契約は「他driverが既に`CONFIRMED`まで進めていた」ケースの誤上書きは防ぐが、「他driverがまだ処理中（`CLAIMED`のまま）」のケースまでは区別できないため、**保守的に`RECOVERY_REQUIRED`へ遷移させてしまう可能性が残る**。これは安全側の誤り（duplicate dispatchには至らない）であり、後述の通りconfirm()契約自体がこの場合を安全に処理する（次段落参照）。
- `list_recovery_required() -> list[DispatchLedgerEntry]`（read-only、診断用。20章）
- `peek(event_identity) -> DispatchLedgerEntry | None`（read-only）

### 8.3 `dispatch_run_id` / `outcome_summary` の位置づけ

これらのフィールドは**診断・監査目的のみ**であり、安全性（duplicate suppression）は `phase` 状態のみに依拠する。`WorkflowEngineManager.run()` は `run_id` を内部生成するため、`confirm()` 時点で得られる `run_id` は次のいずれかに限られる：

- 正常完了：`WorkflowEngineResult.run_id`（`workflow_engine_manager.py` 経由で取得可能）
- `CanonicalAdmissionFailure`：例外オブジェクトの `.run_id` 属性
- その他の例外：`run_id` 不明（`None` のまま記録）

`run_id` が不明でも安全性には一切影響しない（`phase` のみが権威）。これはRetry Lineageの `mark_terminal()` が `newly_confirmed` 等の付加情報を持つのと同じく、"診断情報は権威ではない"という既存設計哲学（`retry_lineage_manager.py` docstring随所）を踏襲している。

### 8.4 4-phaseでなく3-phase、owner_token authorityなしとする理由

Retry Lineageの4-phase（`READY_ELIGIBLE → CLAIMED → EXECUTION_STARTED → TERMINAL`）とowner_token authority checkは、**同一lineageに対して複数のRetry Runtimeプロセスが並行してclaim競合しうる**ことと、**claim後に再度READY_ELIGIBLEへ戻り再claimされる**（attempt再試行）ことを前提に設計されている。

Scheduler Driverのdispatch ledgerは以下の点で性質が異なる：

1. **single-active-driver制約（12章）により、複数プロセスが同時にclaimを試みる状況は通常発生しない**（Codex Round 4 Major#1対応：「構造的に排除される」という無条件表現を撤回し、12.2節のTOCTOU残存windowを除く、という限定付きの表現へ修正）。RetryLineageの owner_token authorityは「複数の正当なclaimant候補が恒常的に存在しうる」ことへの防御だが、Scheduler Driverでは正当なclaimant候補は通常高々1プロセスであり、複数存在しうるのはTOCTOU残存windowという狭い例外的状況に限られる。
2. **1つのevent_identityは一度しかclaimされない**（Out of Scope: `RECOVERY_REQUIRED`の自動復旧なし）。Retry Lineageのように「READY_ELIGIBLEへ戻って再claim」というサイクルが存在しないため、4-phaseの`EXECUTION_STARTED`相当（attempt消費点の精密な特定）を分離する必要がない——claimからconfirmまでが単一の同期的な呼び出しの中で完結し、二度と再利用されないためである。
3. owner_token authorityを省略した残存リスク（single-active-driver lockが手動でstale-lock解除された際の理論上の二重駆動）は、12章で新設する**Ownership-Integrity Self-Check＋Lock Lifecycle Contract**（12.1・12.2節）により、無制限のエスカレーション（3台目以降のdriverが際限なく起動する事態）の発生確率を大幅に低減する。ただし完全に排除するものではなく、`_verify_lock_ownership()`の読み取りと`lock.release()`の間のTOCTOU（Time-of-Check-Time-of-Use）残存windowの中では理論上なお発生しうる。この残存リスクは「解消済み」ではなく「Accepted、低確率」として25章R2に明記する（12.2節で詳述）。

### 8.5 Store I/O Failure Semantics（Codex Round 1 Blocking#2・Major#4、Round 2 Blocking#2対応、拡充）

Round 1レビューで、durable ledgerの読み取り・列挙・書き込みが失敗した場合の挙動が未定義であり、「読めない＝安全にclaim可能」という誤った解釈の余地があるという指摘を受けた。Round 2レビューはさらに、reconciliationの**列挙**失敗（Round 1で規定済み）だけでなく、**個々のrecordの読み取り・スキーマ検証・書き込み失敗**、および**複数recordを1回のreconciliation passで処理する際の部分失敗**の扱いが未定義である点を追加指摘した。以下を明示的な契約として固定する（`retry_lineage`/`execution_history`のatomic save契約と同水準の厳密さを要求する）。

**共通原則**：ledgerの状態を確定的に判定できない場合、常に「claimしない／dispatchしない」側へ倒す（fail-closed）。「読み取りエラー」を「recordが存在しない」と暗黙に等値変換することを禁止する。「壊れたJSON」だけでなく「有効なJSONだが期待するスキーマに合致しない（必須フィールド欠落・`phase`が3値以外等）」も同じく読み取り失敗として扱う（corrupt-but-parseableを特別扱いしない）。

1. **`claim()` の読み取り段階**：`event_identity` に対応するrecordの有無を確認する際、ストアの読み取り（ファイルの存在確認・パース・**スキーマ検証**）自体が失敗した場合（壊れたJSON、スキーマ不一致、権限エラー、I/Oエラー等）は、「recordなし」とは断定せず、`acknowledged=False`・`reason="store read failure"` を返し、`.run()` を一切呼ばない。**「読み取り不能」と「recordが確実に存在しない」は異なるコードパスとして明確に分岐させる**（前者は`False`を返すのみ、後者のみが新規CLAIMED書き込みへ進む）。
2. **`claim()` の書き込み段階**：`retry_lineage`/`execution_history`と同型のatomic save契約（同一ディレクトリ内の一意な一時ファイル → write → flush → `os.fsync()` → close → `os.replace()`）を採用する。親ディレクトリが存在しない場合は`mkdir(parents=True, exist_ok=True)`で作成する（`JsonRetryLineageStore`/`JsonExecutionHistoryStore`と同じ規律）。書き込み中のいかなる段階での失敗も`acknowledged=False`として扱い、例外を`claim()`の外へ伝播させない（呼び出し元へは戻り値のみで通知する）。
3. **`confirm()` の読み取り段階**：既存recordの読み取り自体が失敗した場合、`phase==CLAIMED`であることを確認できないため、書き込みを行わず`False`を返す（8.2節の既存契約「`phase`が`CLAIMED`であることを要求する」を、読み取り失敗ケースへも一貫して適用する）。
4. **`reconcile_stale_claims()`：列挙・個別record読み取り・個別record書き込みの3段階すべてを対象とするfail-closed契約（Round 2で拡充）**：
   - **(a) 列挙段階**：ストアの列挙（ディレクトリ走査）自体が失敗した場合（ディレクトリ削除・permission・マウント断等）、`reconcile_stale_claims()`は例外を送出し、**1件の処理も行わない**。
   - **(b) 個別record読み取り段階**：列挙で見つかった各recordファイルについて、読み取り・パース・スキーマ検証を行う。**この読み取りフェーズをすべてのrecordについて先に完了させてから、次の書き込みフェーズへ進む**（読み取りと書き込みを1recordずつ交互に行わない）。読み取りフェーズの途中で1件でも読み取り失敗（壊れたJSON・スキーマ不一致・I/Oエラー）が発生した場合、`reconcile_stale_claims()`は例外を送出し、**いかなる書き込みも行わない**（読み取りが全件成功して初めて書き込みフェーズへ進む、という順序自体がRound 2指摘への回答である——読み取り失敗による部分書き込みという状態を構造的に発生させない）。
   - **(c) 個別record書き込み段階（Round 3 Blocking#2対応、fresh-read-under-lock契約を追加）**：読み取りフェーズで`phase==CLAIMED`と判定されたrecord群について、1件ずつ`SchedulerDispatchLedgerStoreLock`（8.1節、`RetryLineageStoreLock`と同型の短時間リトライ付きOS-backed排他）を取得する。**ロック取得後、書き込み前に必ずrecordを再読み込みし（fresh read）、`fresh.phase`が依然として`CLAIMED`であることを再確認してから初めて`phase=RECOVERY_REQUIRED`への遷移をatomic saveで書き込む**（`retry_lineage_manager.py:798-836`の`_reconcile_all_locked()`が個々のorphan回収時に`with self._store_lock(): fresh = self._store.get(...); if fresh is None or fresh.phase != RetryLineagePhase.CLAIMED: continue; ...`という形でロック取得後に鮮度を再確認している既存precedentと**完全に同型**のcontractとして採用する。列挙・読み取りフェーズ時点のスナップショットを、ロック取得後に無条件で信頼しない）。
     - **fresh readの結果、`phase`が既に`CLAIMED`以外（例：TOCTOU残存window中に別driverが正当に`CONFIRMED`まで進めていた場合、12.2節）へ変化していた場合**：このrecordへの書き込みをスキップする（`continue`。エラーとして扱わない——他の正当な進行を`RECOVERY_REQUIRED`で上書きしてしまう方が有害であり、これは`retry_lineage`の既存precedentと同じ「無害な競合解決」である）。
     - 各recordの書き込みは独立してatomicであり（8.5節(2)のatomic save契約を流用）、**ある1件の書き込みが失敗しても、既に成功した他のrecordの`RECOVERY_REQUIRED`遷移を取り消さない**（各遷移はそれ自体が安全な保守的操作であり、他のrecordの状態と結合された原子性を必要としない）。ただし、書き込みフェーズの中で1件でも書き込み失敗（fresh read失敗を含む、I/Oエラー等の異常系）が発生した場合、`reconcile_stale_claims()`は（既に成功した遷移を保持したまま）例外を送出して残りの処理を打ち切り、**当該cycleでの新規dispatchを一切行わない**（成功した遷移の一部を「reconciliationが完全に成功した」ことの根拠にしない。書き込みに失敗したrecordは次回cycleの列挙で再度発見され、再度書き込みが試みられる——収束は次cycle以降に持ち越される、fail-closedのままの自然な再試行）。
     - **列挙後・書き込み前に新しく出現したrecord**（読み取りフェーズのスナップショットに含まれていなかったrecord）は、本reconciliationパスの対象外とする。これは安全である——新規recordは定義上`claim()`によって作成されたばかりであり、`claim()`自身のfail-closed契約（8.5節(1)(2)）により正しい状態で存在する。次回cycleのreconciliationで（そのrecordが`CLAIMED`のまま放置されていれば）改めて対象になる。
   - **(d) `run_once()`との関係**：上記(a)(b)(c)のいずれで発生した例外も、`SchedulerDriverOrchestrator.run_once()`へそのまま伝播し、当該cycleは**いかなるeventもdispatchしない**。この例外は15章のcontainment対象（`WorkflowEngineManager.run()`呼び出しの周辺）には該当せず、`run_once()`自体から伝播してfail-fastで`RetryRuntimeLoop`経由のプロセス終了に至る（15章 Design Decision Iの「真に予期しない状況はfail-fast」という既存方針とも整合）。`main()`の`finally`節（12.2節）を経由してプロセスが終了する点は他の例外経路と同一。
5. **起動時のstore初期化**：`SchedulerDriverCompositionRoot`が`SchedulerDispatchLedger`のstore（ディレクトリ）を初期化・疎通確認できない場合、**単一起動制約ロック（12章）を取得する前に**この確認を行う。疎通確認に失敗した場合はロックを取得せずにプロセスを終了する（あるいは、ロック取得後に発覚した場合は、いかなるclaimも行っていない状態のため安全にロックを解放してから終了する）。これにより「ロックだけ保持したまま何もできない」状態を回避する。
6. **記述的スコープ外**：一度durable ackされたrecord（`claim()`が`acknowledged=True`を返した後）が、ledgerストア外部からの改変・削除（人手によるファイル削除、ディスク破損等）によって消失するケースへの防御は、本Releaseの対象外とする。これは`retry_lineage`を含む本コードベースの全てのJSONベースdurable storeに共通する既存の前提（外部改変は想定しない）であり、Scheduler Driverが新たに導入する脆弱性ではない。

---

## 9. Design Decision C：Production Schedule Source一元化

### 9.1 新規パッケージ `src/scheduler_schedule_source/`

```python
class ProductionScheduleSource:
    """production SchedulerJob定義の唯一の供給元。"""
    def jobs(self) -> list[SchedulerJob]:
        ...
```

- MVP初期実装では、`build_demo_job()` が保持していたJob定義（`job_id="workflow_engine_demo_daily"`, DAILY 09:00）を「production」の名の下に本パッケージへ**移設**する（実装フェーズでの作業。本書は設計のみ）。
- `SchedulerManager` / `SchedulerRepository`（既存 `src/scheduler/`）は無変更のまま、`ProductionScheduleSource.jobs()` が返すリストを `SchedulerManager.register_job()` へ渡す呼び出し元（Composition Root、13章）だけが新規となる。
- 将来的な複数Job・設定ファイル化（Non-Goal N4）はこのクラスの内部実装のみを変更すれば済み、呼び出し元（`ProductionScheduleSource.jobs()` のシグネチャ）は変更不要という拡張性を持たせる。

### 9.2 `scripts/run_workflow_engine.py` との関係（Codex Round 1 Major#2・Round 2 Major#2対応、確定）

**決定（Round 1で未確定だった点を確定する）**：`scripts/run_workflow_engine.py` の `build_demo_job()` 呼び出しを、実装フェーズで**必須**として `ProductionScheduleSource().jobs()` 経由へ置き換える。「新設 `scripts/run_scheduler_driver.py` だけを新しい供給元の消費者とし、`run_workflow_engine.py` は意図的に旧来のデモ動作のまま残す」という選択肢は、以下の理由により**却下**する（24章 Rejected Alternativesにも追記）：

- Roadmapの「production schedule sourceの一元化」は、単一の供給元を新設することではなく、**既存のhard-coded schedule sourceを転用しないこと**を要求している（`docs/MVP_COMPLETION_ROADMAP.md:217`「`scripts/run_workflow_engine.py`のhard-coded demo jobをそのままproduction schedule sourceに転用しない」）。この文言は、既存の`build_demo_job()`という重複した供給元を放置することを許容していない。
- `build_demo_job()` を放置したまま新規供給元を並存させると、**同一のproduction Job定義が2箇所に存在する**状態になり、将来どちらかだけを更新するとJob定義がドリフトする構造的リスクを生む。これは「唯一の供給元」というG5の目標そのものに反する。
- この変更は `scripts/run_workflow_engine.py` の `--job-id` 手動経路（`resolve_event()`の`args.job_id is not None`分岐）には一切影響しない。影響するのは Scheduler経由分岐（`resolve_event()`の`else`節、`build_demo_job()`呼び出し1箇所のみ）に限定される。したがって「main.py直接実行経路」「`--job-id`手動経路」のZero-Diff主張（19章・21章）とは矛盾しない。

**Round 2指摘（Major#2）の要旨と、具体的な置換仕様の確定**：Round 1は「`build_demo_job()`呼び出しを`ProductionScheduleSource().jobs()`へ置換する」とのみ記していたが、これは型不一致であり実装不能だった——`build_demo_job()`は`SchedulerJob`を1件返すのに対し、`ProductionScheduleSource.jobs()`は`list[SchedulerJob]`を返す（9.1節）。さらに既存コードは`register_job()`を1回しか呼ばず、`events[0]`のみを処理し、診断メッセージに`DEMO_JOB_ID`/`DEMO_JOB_SCHEDULE`という個別定数を直接埋め込んでいる（`scripts/run_workflow_engine.py:99-101,132-141`）。以下、`resolve_event()`内の該当箇所を具体的にどう置換するかを確定する：

```python
# 変更前（scripts/run_workflow_engine.py:132-134）
repository = InMemorySchedulerRepository()
scheduler_manager = SchedulerManager(repository)
scheduler_manager.register_job(build_demo_job())

# 変更後
repository = InMemorySchedulerRepository()
scheduler_manager = SchedulerManager(repository)
production_jobs = ProductionScheduleSource().jobs()
for job in production_jobs:
    scheduler_manager.register_job(job)
```

- **登録**：`ProductionScheduleSource.jobs()`が返す**全件**を`register_job()`でループ登録する（1件しか登録しない既存の型不一致を解消）。
- **event選択（`events[0]`のみを処理する既存の挙動は意図的に維持する）**：`run_workflow_engine.py`は、本Releaseにおいても「1回の起動で1つのWorkflowEngineEventを処理する単発CLIツール」のままであり（13章の新設`scripts/run_scheduler_driver.py`のような複数eventの一括dispatchループへ拡張することは、本Releaseのスコープではない——それは新設ツールの責務である）。したがって`events[0]`のみを処理する既存ロジックはそのまま維持する。**ただし、`ProductionScheduleSource.jobs()`が複数Jobを返すようになった場合（現行MVP実装は1件のみ、9.1節）、同一分に複数Jobが同時マッチしても`run_workflow_engine.py`は先頭の1件しか処理しない**という制約が新たに生じる。これは新規の欠陥ではなく、「`run_workflow_engine.py`を単発診断/手動実行ツールのまま据え置き、複数Job・複数event一括処理は新設`scripts/run_scheduler_driver.py`の責務とする」という本Releaseの意図的な責務分担の帰結であり、25章R9として明示する。
- **診断メッセージ**：`DEMO_JOB_ID`/`DEMO_JOB_SCHEDULE`のハードコード参照を、実際に登録した`production_jobs`から導出する形へ置換する（例：`", ".join(f"job_id={j.job_id}, schedule={j.schedule}" for j in production_jobs)`）。これにより`ProductionScheduleSource`の内容が変わっても診断メッセージが自動的に追従し、陳腐化した固定文言が残ることを防ぐ。`DEMO_JOB_ID`/`DEMO_JOB_SCHEDULE`定数自体は削除する（もはや`ProductionScheduleSource`側の定義が権威であるため）。

この決定に伴い、`scripts/run_workflow_engine.py` は21章のZero-Diff対象から明示的に除外し、17.3節・22章を「変更候補（任意）」から「変更対象（必須）」へ更新する。

---

## 10. Design Decision D：Fail-Closed Dispatch契約

**決定**：`claim()` のdurable ack（`acknowledged=True`）を得られない限り、`WorkflowEngineManager.run()` を呼び出さない。

```
1. event_identity を算出
2. ledger.claim(event_identity, job_id, occurrence_minute) を呼ぶ
3. acknowledged == False の場合：
   - dispatchしない（スキップ。ログにreasonを出力するのみ）
   - 次のeventへ進む
4. acknowledged == True の場合のみ：
   - WorkflowEngineManager.run(event, ...) を呼び出す
   - 完了後、必ず ledger.confirm(...) を呼ぶ（try/except Exceptionで完了を保証、15章）
```

claim前にdispatchしてから記録する順序（Roadmapが明示的に禁止する順序）は採用しない。この順序自体が、claim（durable write）とdispatch（外部へ波及しうる呼び出し）の間に必ず「durable evidenceが先に存在する」という不変条件を保証する（6.32のwrite-ahead fail-closed契約——外部副作用の**前**にdurable evidenceを残す——と同型の設計思想であり、対象領域が異なるだけで契約構造は流用している。ただし6.32のコード自体は一切変更・参照しない）。

---

## 11. Design Decision E：Claim→Dispatch Crash Safety / Ambiguous Outcome

### 11.1 対象とするcrash window

Roadmap Completion Criteria・タスク指示が要求する2つのcrash windowは、いずれも本設計では**単一の検出機構**（8.2節の`reconcile_stale_claims()`）で扱う：

- **(a) claim成功→dispatch前クラッシュ**：`claim()` のdurable ack後、`WorkflowEngineManager.run()` を呼ぶ**前**にプロセスが停止。
- **(b) dispatch開始直後→durable confirmation前クラッシュ**：`WorkflowEngineManager.run()` の呼び出し中、または呼び出しが返った直後・`confirm()` のdurable write前にプロセスが停止。

**設計判断**：この2つを見分けようとしない。理由は、(a)と(b)を区別するには「`.run()` が実際に呼ばれたかどうか」という情報を、クラッシュに耐える形でclaim時点に先んじて記録する必要があるが、`run_id` は `.run()` 内部でのみ生成されるため、driver側は`.run()` を呼ぶ**前**にrun_idを知り得ない（6.2節Finding）。したがって(a)と(b)を安全に区別する手段はなく、区別しようとすること自体が誤った判定（実際には実行されていないのに「実行済み」とみなす等）のリスクを生む。

**結論**：`phase==CLAIMED` のまま次回の `reconcile_stale_claims()` に到達したrecordは、(a)(b)いずれであるかを問わず一律 `RECOVERY_REQUIRED` へ遷移させる。これは要求される「ambiguous outcome時のfail-closed state」を、区別不能な2つのcrash windowの**和集合**として満たす設計である。

### 11.2 Restart Recovery

- driver起動時、loop開始前に必ず `reconcile_stale_claims()` を1回実行する。
- 起動直後は「前回プロセス終了時点で `CLAIMED` のまま残っていたrecord」が存在する可能性がある唯一のタイミングであり、ここで確実に回収する。
- 再起動後、同一の `event_identity` は既に `RECOVERY_REQUIRED`（recordとして存在する）ため、`claim()` は無条件に `acknowledged=False` を返す。**自動的な再dispatchは発生しない**（Roadmap要求「Runtime再起動後も同一occurrenceを自動的に二重dispatchしない」を満たす）。

---

## 12. Design Decision F：Single-Active-Driver制約

**決定**：`RetryRuntimeLock`（6.4節）をそのまま再利用し、新しいロックファイルパス `<project_root>/.run/scheduler_driver.lock` で独立したインスタンスとして使用する。加えて、Codex Round 1 Blocking#1・Round 2 Blocking#1対応として、**Ownership-Integrity Self-Check**（12.1節）と、それを**唯一のrelease経路**として全終了パスに強制する**Lock Lifecycle Contract**（12.2節）を新設し、stale-lock手動解除に伴う並行driverのエスカレーション発生確率を実務上無視できる水準まで低減する（ただしTOCTOU残存windowにより理論上完全にはゼロにならない。12.2節・25章R2）。

- `RetryRuntimeLock` はドメイン非依存であることが既に文書化されているため（6.4節Finding F3）、コード変更・サブクラス化は不要。
- 2つ目のdriverプロセスが起動を試みた場合、`RetryRuntimeLockError` が送出され、CompositionRoot等の構築前にfail-closedで拒否される（既存 `run_retry_runtime.py` の挙動と同一）。
- ロックファイルパスが `.run/retry_runtime.lock`（Retry Runtime）と `.run/scheduler_driver.lock`（Scheduler Driver）で完全に分離されているため、**両プロセスは互いのロックに干渉しない**（14章、ownership分離の直接的な帰結）。

### 12.1 Ownership-Integrity Self-Check（Codex Round 1 Blocking#1・Round 2 Blocking#1対応）

**問題**：`RetryRuntimeLock`は`os.open(O_CREAT|O_EXCL)`によるファイル存在ベースの排他制御のみであり、PIDの生存確認を行わない（`retry_runtime_lock.py:12-15`）。`release()`は「ロックが存在すれば無条件に削除する」実装であり（`:72-77`）、**呼び出し元が本当にそのロックの正当な保持者であるかを検証しない**。Codex Round 1 Blocking#1は、この既存の性質そのものを「継承済みの許容リスク」と片付けることを拒否し、以下のエスカレーションシナリオを具体的に指摘した：

1. Driver Aがlockを取得（`.run/scheduler_driver.lock`にPID_Aを書き込み）。
2. 運用者が「Aは死んでいる」と誤って判断し、lockファイルを手動削除（6.4節の既存運用手順、`RetryRuntimeLock`自体が要求する手順）。
3. Driver Bが起動しlockを取得（同ファイルにPID_Bを書き込み）。**しかしAは実際には生存中**。
4. Aが（本来の終了処理、またはクラッシュ経路以外の任意のタイミングで）`lock.release()`を呼ぶと、`release()`は中身を確認せず無条件にファイルを削除する——**結果としてBのlockを消してしまう**。
5. lockが再び空くため、Driver Cが起動できてしまう。A自身も（Bのlock削除に気づかず）動作を継続していれば、この時点でA・B・Cが並行動作しうる。

**Round 2で追加指摘された不備**：Round 1の初版は、上記シナリオへの対策として「cycle先頭で検証する」ことのみを定めていたが、（a）`run_once()`の擬似コード（旧13章）が実際にはこの検証呼び出しを含んでいなかった（記述と設計の不整合）、（b）**検証がcycle先頭でのみ行われるため、Aがcycle先頭の検証を通過した後・そのcycleの処理中にlockが奪われ、Aがそのまま正常終了（または例外による異常終了）でシャットダウンする場合、その終了処理が「cycle先頭の古い（既に無効な）検証結果」に基づいて無条件に`lock.release()`を呼んでしまう**——B1シナリオの4.がそのまま再現される、という2点の指摘を受けた。以下（12.1・12.2節）はこの両方を解消する改訂版である。

```python
def _verify_lock_ownership(lock_path: Path, own_pid: int) -> bool:
    """lock_pathの中身が自プロセスのPIDのままであることを確認する。
    読み取れない・PIDが一致しない場合はFalse（fail-closed）。"""
    try:
        content = lock_path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return content == str(own_pid)
```

**検証タイミング（Round 3改訂）**：

1. **起動時**：`lock.acquire()` 成功後、**必ず`try`ブロックの内側の最初の文として**検証する（12.2節の擬似コード参照。Round 3指摘：`try`の外側で検証すると、検証自体が予期せず失敗した場合に`finally`の保護を受けずlockがleakしうるため、検証は「`try`ブロックに入って最初に行う、保護対象の一部」として位置づける）。
2. **`SchedulerDriverOrchestrator.run_once()` の先頭**（`reconcile_stale_claims()`より前。13章の`run_once()`擬似コードで明示している）。Falseの場合、`run_once()`自体が`LockIntegrityViolationError`を送出し、`reconcile_stale_claims()`・`evaluate()`・claim・dispatchのいずれも一切実行しない。
3. **プロセスが`lock.release()`を呼ぶ、あらゆる終了経路の直前**（12.2節）。これが、cycle処理中に奪われたlockを、古い判定のまま終了処理で無条件解放してしまう経路を閉じるための追加検証である。

### 12.2 Lock Lifecycle Contract：release()の唯一の呼び出し経路（Codex Round 2 Blocking#1・Round 3 Blocking#1／Major#2対応）

**決定**：`lock.release()` を直接呼び出すコードは、リポジトリ全体で**ただ1箇所**（`_release_if_owned()` という単一のヘルパー関数の内部）に限定する。他のいかなる場所（`SchedulerDriverOrchestrator`、例外ハンドラ、シグナルハンドラを含む）からも `lock.release()` を直接呼ばない。

**コンポーネント配置（Round 3 Major#2対応、明確化）**：`_verify_lock_ownership()` と `_release_if_owned()` はいずれも `src/scheduler_driver/scheduler_driver_lock_integrity.py`（17.2節・22章、新規package内のモジュール）に**定義**する（CLI固有のI/Oに依存しない純粋関数として、ユニットテスト容易性のためライブラリ側に置く）。ただし `_release_if_owned()` を**呼び出す**コードパスは、`scripts/run_scheduler_driver.py` の `main()` の `finally` 節、**ただ1箇所のみ**とする。「定義場所（ライブラリ）」と「呼び出し箇所（CLIのfinally節、唯一）」は区別された概念であり、後者の一意性が本節の安全性契約の実体である。

```python
# src/scheduler_driver/scheduler_driver_lock_integrity.py
def _verify_lock_ownership(lock_path: Path, own_pid: int) -> bool:
    """lock_pathの中身が自プロセスのPIDのままであることを確認する。
    読み取れない・PIDが一致しない場合はFalse（fail-closed）。"""
    try:
        content = lock_path.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    return content == str(own_pid)


def _release_if_owned(lock: RetryRuntimeLock, own_pid: int) -> None:
    """releaseの直前に必ずownershipを再検証する。検証に失敗した場合は
    releaseをスキップする（他プロセスの正当なlockを誤って削除しないため）。
    このヘルパーはscripts/run_scheduler_driver.pyのmain()のfinally節からのみ
    呼び出される（呼び出し箇所の一意性が安全性契約の実体、本節参照）。
    Codex Round 4 Minor#2対応：OSErrorに限定せずExceptionを広く捕捉する
    （15章のException/BaseException境界方針と整合。BaseExceptionは対象外）。"""
    try:
        if _verify_lock_ownership(lock.lock_path, own_pid):
            lock.release()
        else:
            _log_lock_integrity_violation_on_exit()  # 診断ログのみ、raiseしない
    except Exception:
        _log_lock_integrity_violation_on_exit()  # release自体の失敗もfail-closed（何もしない、raiseしない）


# scripts/run_scheduler_driver.py
def main() -> int:
    ...
    own_pid = os.getpid()
    lock = RetryRuntimeLock(lock_path=_PROJECT_ROOT / ".run" / "scheduler_driver.lock")
    lock.acquire()
    try:
        # Round 3改訂：起動時ownership検証は、finally節による保護を受けられるよう
        # tryブロックの内側・本体処理より前に置く（12.1節タイミング1.）。
        if not _verify_lock_ownership(lock.lock_path, own_pid):
            raise LockIntegrityViolationError(lock.lock_path, own_pid)
        # --- ここから、単発実行 or --loop実行の本体 ---
        ...
    finally:
        # 正常完了・Graceful Shutdown・run_once()由来の例外（LockIntegrityViolationError含む）・
        # 予期しない例外・BaseException（KeyboardInterrupt/SystemExit）のいずれの経路でも、
        # Pythonのfinally節は実行される（ただし本節末尾の「finallyの限界」を参照）。
        # release可否の判定はこの1箇所に集約する。
        _release_if_owned(lock, own_pid)
```

- **`with lock:` パターンは採用しない**（Round 1で既に決定済みの方針を維持）。`acquire()` を明示的に呼んだ直後、**`try/finally` で本体全体（起動時ownership検証を含む、単発実行・`--loop`実行いずれも）を包み、`finally` 節で必ず `_release_if_owned()` を呼ぶ**という構造に一本化する。
- **この設計により、cycle処理中にlockを奪われた場合の「古い判定のまま終了処理で無条件解放してしまう」経路は塞がる**：Aがcycle処理中にlockを奪われた場合、Aの`finally`節での`_release_if_owned()`は、その時点の（cycle先頭時点ではなく、終了直前の）lockファイルの中身を再読み込みして検証するため、既にBのPIDが書き込まれていることを正しく検出し、releaseをスキップする。**ただしこれは「TOCTOU残存window（次段落）を除けば」という限定付きの主張であり、「常に・構造的に・100%防止される」という無条件の主張ではない**（Round 3 Major#1対応：以前の版で「構造的に遮断」「削除されることはない」という無条件の表現を用いていた箇所を、本節・18章・25章・26章のすべてで、TOCTOU残存windowを明記した限定付きの表現へ統一した）。
- **TOCTOU（Time-of-Check-Time-of-Use）残存リスク（正確な特性、Round 3で明確化）**：`_verify_lock_ownership()`の読み取りと`lock.release()`の削除の間には、原理的にごく短い（ファイルシステム操作2回分の）検証と実行の間隙が残る。**この間隙の中でもう一方のdriverがlockを奪取した場合、理論上は本節の保護をすり抜け、Bシナリオの4.（AがBのlockを誤って削除し、Cが起動できてしまう）がそのまま再現しうる**。これは「別の・より小さいリスク」ではなく、**発生確率は大幅に下がったが、事象としては同一のリスクが残っている**、という性質のものである（Round 3 Major#1で指摘された通り、この2つを混同しない）。この残存windowは「1 cycle分（`interval_seconds`、通常数十秒〜数分）」から「2回のファイルI/O呼び出しの間（通常マイクロ秒〜ミリ秒オーダー）」へ縮小しており、発生確率は実務上無視できる水準まで下がるが、**ゼロではない**。真に完全な排他を求める場合は、比較・削除をアトミックに行う専用ファイルシステムプリミティブ（本OS標準APIには存在しない）が必要になるが、これは本Releaseのスコープを超える（24章 Rejected Alternatives #9で却下した「owner token化」よりもさらに大掛かりな変更を要するため）。この残存リスクは25章R2で「Accepted、Low確率だが理論上ゼロではない」として明示的に記録し、「解消済み」とは記載しない。
- **`finally`の限界（Round 3 Minor#2対応、明示）**：`finally`節は、通常のreturn・伝播する例外（`BaseException`である`KeyboardInterrupt`/`SystemExit`を含む）に対しては実行されるが、以下のケースでは実行され**ない**、または安全性を保証しない：(a) `os._exit()`やOSレベルの強制終了（`taskkill /F`、電源断等、6.4節の`RetryRuntimeLock`自体が既に認めている既知の限界と同一）、(b) `finally`節自体の実行中（`_release_if_owned()`内部）に`Exception`が発生した場合（`_release_if_owned()`自体が内部で`Exception`を広く捕捉しfail-closed（何もしない）とすることで、この経路の影響を最小化している。上記コード参照。`BaseException`（`KeyboardInterrupt`/`SystemExit`等）はcatchしない点は15章の方針と同一だが、`finally`節の実行それ自体はPythonの言語仕様上これらに対しても行われるため、`_release_if_owned()`内で万一`BaseException`が送出された場合のみ、release可否判定を経ずに伝播しうる——これは極めて稀な理論上のケースであり、`_verify_lock_ownership()`/`lock.release()`のいずれも`BaseException`を意図的に送出する実装ではない）。これらのケースでは、lockファイルが残存する（stale lock）か、あるいは（(b)の稀なケースで）ownership検証を経ずにプロセスが終了する可能性が理論上残るが、前者は`RetryRuntimeLock`が元々受容している既知の運用リスク（6.4節）であり、後者は`_release_if_owned()`内の`try/except Exception`により「releaseをスキップする」方向へ倒れるため、いずれも安全側（過剰に保守的、lockが必要以上に残存する）の誤りに留まる。
- **効果のまとめ（Round 3で表現を限定付きへ修正）**：エスカレーション（3台目Cの起動）は、TOCTOU残存windowの外では「A→B」の1段階で止まる（TOCTOU残存windowの中では理論上なお発生しうる、25章R2）。同一`event_identity`への二重dispatchについては、TOCTOU残存windowの有無に関わらず常に、`claim()`の「recordが既に存在すれば`acknowledged=False`」という契約（8章）により防止される——これは本設計の中で**唯一、無条件に成立すると主張できる**不変条件である（duplicate dispatch防止という6.34の中核目標は、lockの完全性とは独立した`claim()`の契約自体が担保している）。

---

## 13. Design Decision G：Loop Driver / Graceful Shutdown

**決定**：`RetryRuntimeLoop` と `RetryRuntimeShutdown` をそのまま再利用する。新規パッケージ `src/scheduler_driver/` は、これらをDIで組み立てるOrchestratorのみを持つ。

```python
class SchedulerDriverOrchestrator:
    def __init__(self, scheduler_engine, schedule_source, ledger, workflow_engine_manager,
                 clock, lock_path, own_pid):
        ...

    def run_once(self) -> SchedulerDriverCycleResult:
        # 12.1節：Ownership-Integrity Self-Check（Round 2で run_once() 冒頭へ明示的に組み込み）。
        # Falseの場合、reconcile_stale_claims()以降には一切進まない。
        if not _verify_lock_ownership(self._lock_path, self._own_pid):
            raise LockIntegrityViolationError(self._lock_path, self._own_pid)

        self._ledger.reconcile_stale_claims()          # 11.2節：毎cycle先頭（self-check直後）
        now = self._clock.now()
        jobs = self._schedule_source.jobs()
        events = self._scheduler_engine.evaluate(jobs, now)
        production_job_ids = frozenset(j.job_id for j in jobs)
        events = _select_dispatchable_events(events, production_job_ids)   # 16章 Design Decision J（改訂版）

        dispatched, skipped = [], []
        for event in events:
            result = self._dispatch_one(event)
            (dispatched if result.dispatched else skipped).append(result)
        return SchedulerDriverCycleResult(dispatched=dispatched, skipped=skipped, ...)
```

`run_once()` 自体は `lock.release()` を一切呼ばない（12.2節の通り、releaseは`scripts/run_scheduler_driver.py`の`main()`の`finally`節1箇所に集約する）。`LockIntegrityViolationError`は他の想定内例外（8.5節のstore失敗等）と同様、`run_once_fn`の例外としてそのまま`RetryRuntimeLoop`経由でfail-fast伝播し、最終的に`main()`の`finally`節へ到達して`_release_if_owned()`が実行される。

- `scripts/run_scheduler_driver.py`（新規、`scripts/run_retry_runtime.py` と同型、ただし12.2節のLock Lifecycle Contractに従い`with lock:`ではなく明示`acquire()`＋`try/finally`を用いる）：
  - `RetryRuntimeLock.acquire()`（12章）→ `try:` ブロック内で `SchedulerDriverCompositionRoot.from_env()` → `SchedulerDriverOrchestrator` → （`--loop` 指定時のみ）`RetryRuntimeShutdown` + `RetryRuntimeLoop(run_once_fn=orchestrator.run_once, sleep_fn=shutdown.interruptible_sleep, should_continue_fn=shutdown.should_continue, interval_seconds=...)` → `finally:` ブロックで `_release_if_owned(lock, own_pid)`（12.2節の`main()`擬似コードを参照）。
- `run_once_fn` が例外を送出した場合、`RetryRuntimeLoop` は既存契約通りfail-fastで伝播させる（15章で「想定内の失敗はrun_once内で握りつぶす／想定外はfail-fast」という方針を確定する）。この例外は`main()`の`try`ブロックを抜けて`finally`節（`_release_if_owned()`）を必ず経由してからプロセスが終了する。

---

## 14. Design Decision H：Retry Runtimeとのownership／プロセス排他の定義

**決定**：Scheduler DriverとRetry Runtimeは、**互いに一切のロック・ストア・状態を共有しない、完全に独立した2つのプロセス**として設計する。

| 観点 | Scheduler Driver | Retry Runtime |
|---|---|---|
| 単一起動制約ロック | `.run/scheduler_driver.lock`（`RetryRuntimeLock`） | `.run/retry_runtime.lock`（`RetryRuntimeLock`、既存） |
| durable state | `state/scheduler_dispatch/`（新規、dispatch ledger） | `state/retry_lineage/`（既存、無変更） |
| dispatchする対象 | `ProductionScheduleSource` 由来の genuine `SchedulerJob` occurrence のみ（16章 Design Decision J） | `RetryLineageManager` がclaimしたretryable candidateのみ |
| `WorkflowEngineManager.run()` の `event.source` | `SOURCE_SCHEDULER`（既存定数） | `SOURCE_MANUAL`（既存、`RetryExecutor` が使用） |
| 排他の粒度 | 自プロセスの多重起動のみを防止 | 自プロセスの多重起動のみを防止（既存） |

- 両プロセスが**同時に動作すること自体は許容する**（Roadmap Completion Criteria「Retry RuntimeプロセスとScheduler driverプロセスの同時実行時に競合・二重実行が発生しないことを確認」は、"排他しなければならない"ではなく"競合しないこと"を求めている）。

### 14.1 「競合・二重実行が発生しない」の精密な定義（Codex Round 1 Major#3対応）

Round 1レビューは、旧版が「独立したUUID run_id・独立したWorkflowExecutionRecordを生成するため衝突しない」ことのみを根拠に、あたかも「Scheduler DriverとRetry Runtimeの同時実行が安全全般である」かのように主張していた点を、**過大な主張**として指摘した。ここでCompletion Criteriaが要求する安全性の範囲を、以下のように**record-level**と**content-level**に明確に分離し、本Releaseが保証する範囲を精密化する。

**record-level非衝突（本Releaseが保証する範囲）**：

- 両者が同時に `WorkflowEngineManager.run()` を呼び出しても、各呼び出しは独立した `run_id`（uuid4）・独立した `WorkflowExecutionRecord` を生成するため、**Execution History上のrecordが上書き・混線することは構造的に発生しない**（6.2節、`ExecutionHistoryManager.start_run()`のcanonical admission契約は本Releaseで無変更）。
- Scheduler Driverのdispatch ledger（`state/scheduler_dispatch/`）とRetry Runtimeのlineage store（`state/retry_lineage/`）は完全に別ディレクトリであり、**ledger/lineageの状態が互いを上書きすることはない**。
- 両者の単一起動制約ロック（`.run/scheduler_driver.lock` / `.run/retry_runtime.lock`）は別ファイルであり、**一方のロック取得が他方のロック取得を妨げない／誤って解放しない**。
- **Design Decision J（16章、retry-candidate eventの除外）**により、Scheduler Driverは`RetryLineageManager`がclaim済みのretry対象を自ら再dispatchすることがない——両者は構造的に素性の異なるoccurrence集合（genuine schedule occurrence vs. retry対象）にしか作用しない。

**content-level idempotency（本Releaseが保証しない・保証すると主張しない範囲）**：

- Scheduler Driverが起動する「新規のscheduled occurrence」と、Retry Runtimeが起動する「過去に失敗したrunのretry」は、**別々の正当なworkflow実行**である。両者が時間的に重なった場合、それぞれが独立にNEWS収集・記事生成・WordPress投稿を行いうる。これは、たとえば同一の話題について内容が重複した記事が別々の`run_id`の下で生成・投稿されるという、**content-levelでの重複**を排除するものではない。
- **この種の重複は、本Release（6.34）が新たに持ち込むリスクではない**。Scheduler DriverもRetry Runtimeも存在しなかった時点（v6.33以前）でも、運用者が`scripts/run_workflow_engine.py`を手動で複数回・短時間に実行すれば同種の重複は既に発生しうる、既存のシステム特性である。加えて、`docs/MVP_COMPLETION_ROADMAP.md`のPost-MVPセクションは「`duplicate_filter`の実行間・再試行間対応への拡張」を明示的にPost-MVP項目として掲げており（既にプロジェクトとして自覚済みの、意図的に先送りされた課題である）。
- したがって、**本Releaseの「競合・二重実行が発生しないことを確認する」というCompletion Criteriaは、record-levelの非衝突（上記）を指すものと解釈し、content-level idempotencyの新規実装はDesign Decision Hのスコープに含めない**。この解釈をArchitecture Gate Checklist（26章）で明示的に確認事項とする。
- 外部副作用（WordPress下書き作成等）についても、単一run内でのdispatch重複・crash時の重複防止は、既存の6.32 Protected Operation Manifest / side-effect fail-closed契約が`WorkflowEngineExecutor`のstep実行レベルで既に担っている責務であり、**本Releaseはこれを一切変更・拡張しない**（継承するのみ）。これは「同一run内でのstep実行の冪等性」を保証するものであり、「異なる2つのrun（Scheduler DriverとRetry Runtime起源）の間のcontent-level idempotency」とは異なるレイヤーの契約である点を、本節で明確に区別した。
- **唯一の交差点はDesign Decision J（retry-candidate eventの除外）であり、これはSchedulerEngineの出力レベルでの静的なfilterであって、実行時のロック共有ではない。**

---

## 15. Design Decision I：Exception / BaseException Boundary

**方針**（既存 `retry_runtime_observability` の「Exceptionのみをcontainし、BaseExceptionは対象外」という確立済みパターンを踏襲）：

1. **`_dispatch_one(event)`**（1 event分のclaim→run→confirm）内では、`WorkflowEngineManager.run()` 呼び出しを `try/except Exception` で囲む。
   - 正常終了：`ledger.confirm(event_identity, run_id=result.run_id, outcome_summary=f"overall_success={result.overall_success}")`
   - `CanonicalAdmissionFailure` を含む `Exception` 捕捉時：`ledger.confirm(event_identity, run_id=getattr(e, "run_id", None), outcome_summary=f"EXCEPTION:{type(e).__name__}")`。例外はcontainし、**再raiseしない**（1つのeventの失敗が同一cycle内の他eventの評価・次cycleのdispatchをブロックしないようにするため。既存 `_warn_best_effort()` 等の「ベストエフォート継続」哲学と整合）。
   - `confirm()` 自体がFalse（durable ack失敗）を返した場合：WARNINGログを出力し処理継続（entryは`CLAIMED`のまま残り、次回`reconcile_stale_claims()`で安全側に倒れる。8.2節）。
2. **`BaseException`**（`KeyboardInterrupt` / `SystemExit` / `GeneratorExit`）はcatchしない。そのまま伝播させる。
   - `--loop` 実行時のSIGINT/SIGTERM/SIGBREAKは、既存 `RetryRuntimeShutdown` の契約通り、シグナルハンドラ内でフラグを立てるのみで例外を送出しない（cycle実行中に割り込まない）。したがって通常運用でループ内に`BaseException`が飛び込むことは想定しない。
   - 万一予期しない`BaseException`（例：メモリ不足による`MemoryError`はException系のため対象外だが、プロセス自体のkillは捕捉不可能）が発生した場合、`_dispatch_one` の途中で処理が中断する可能性があるが、これは11章のcrash windowとして扱われ、`reconcile_stale_claims()` によって次回起動時に安全に回収される。**BaseExceptionからの回復をコードレベルで保証する必要はなく、durable state（ledger）による回復にすべて委ねる**という設計判断を明記する。
3. **`RetryRuntimeLoop.run()`** 自体の既存契約（`run_once_fn` が例外を送出した場合はfail-fastで伝播）は変更しない。ただし上記1.の設計により、`run_once_fn`（＝`SchedulerDriverOrchestrator.run_once()`）が個々のevent dispatch失敗で例外を送出することは想定しない（すべてcontainする）。`run_once()` 自体が例外を送出するのは、`reconcile_stale_claims()` やイベント列挙などlogic自体のバグ・真に予期しない状況に限られ、その場合はfail-fastで`RetryRuntimeLoop`経由でプロセスごと終了する（既存`RetryRuntimeOrchestrator.run_once()`と対称的な既存方針を踏襲、6.4節）。

---

## 16. Design Decision J：Retry-candidate SchedulerEvent除外契約

**決定（Codex Round 1 Major#1・Round 2 Major#1対応、再改訂）**：`SchedulerDriverOrchestrator.run_once()` は、以下**2層のAND条件**をいずれも満たすイベントのみをdispatch対象とする：

1. **一次機構（provenance-based、Round 2で新設）**：`event.metadata` に `"retry_candidate"` キーが**含まれていない**こと。
2. **二次機構（allowlist-based、Round 1で新設・維持）**：`event.job_id` が `ProductionScheduleSource.jobs()` が返す `job_id` 集合に含まれること。

```python
def _select_dispatchable_events(
    events: list[SchedulerEvent], production_job_ids: frozenset[str],
) -> list[SchedulerEvent]:
    """一次：'retry_candidate'メタデータキーの不在（SchedulerEngine自身が発する
    構造的provenance signal）。二次：production_job_idsのメンバーシップ
    （allowlist、defense-in-depth）。両方を満たすイベントのみ残す。"""
    def _is_dispatchable(e: SchedulerEvent) -> bool:
        if "retry_candidate" in e.metadata:
            return False
        return e.job_id in production_job_ids
    return [e for e in events if _is_dispatchable(e)]
```

**Round 2指摘（Major#1）の要旨**：Round 1で採用したpositive allowlist（`job_id`集合メンバーシップのみ）は、`job_id`という**値**に依拠する判定である点でRound 1旧版（prefix除外）と本質的に同じ弱点を抱えていた——**「あるeventが、仮に将来retry候補由来のまま、たまたま何らかの理由でproduction job_idと同一の`job_id`値を持つ表現へ変化した場合」に、allowlistだけではそれを弾けない**、という指摘である。Round 2はこの残存ギャップを、`job_id`という値ベースの判定ではなく、**SchedulerEngine自身が既に発している構造的な出自シグナル**を用いることで閉じる。

**一次機構（`"retry_candidate" not in event.metadata`）が本質的に優れている理由**：

- `_build_retry_events()`（`scheduler_engine.py:224-258`）は、生成するすべてのretry候補eventに対して無条件に `metadata={"retry_candidate": candidate}` を設定する（`:255`）。これは`job_id`の命名規則（prefix等）とは独立した、**SchedulerEngine自身のコードが構造的に保証する出自マーカー**である——「`job_id`が将来どう表現されるか」という前提を一切必要としない。
- 一方、genuine Job由来のeventは、`evaluate()`のJob判定ループ（`scheduler_engine.py:144-159`）で`metadata=dict(job.metadata)`として構築される（`:157`）。これは`SchedulerJob.metadata`（`scheduler_job.py`、デフォルト`field(default_factory=dict)`）をそのままコピーしたものであり、`ProductionScheduleSource`が登録するJob定義が`metadata`に`"retry_candidate"`という予約キーを含めない限り、genuine eventがこのキーを持つことは構造的にない。
- したがって一次機構は、**「retry候補eventの`job_id`表現が将来どう変わっても」「production Jobの`job_id`が偶然どんな文字列であっても」、いずれの軸にも依存せずに正しく判定できる**——Round 1・Round 2で指摘された両方向の脆弱性（値ベースのFalse Negative/False Positive）を、値ではなく構造（キーの有無）で判定することにより解消する。

**二次機構（allowlist）の役割**：一次機構はあくまで「`SchedulerEngine`が現在実装している`_build_retry_events()`由来のマーカー」に依拠するため、**将来 `SchedulerEngine` に全く別の第三のevent生成経路が追加された場合**（本Releaseの想定外だが、pure boundaryを保つ`SchedulerEngine`への将来の拡張は排除できない）への備えとして、`ProductionScheduleSource`ベースのallowlistを引き続き二次防御として維持する。`"retry:"`prefix判定（Round 1の一次機構）は、二次機構内でのさらに副次的なログ用ヒントとしてのみ残し（`ProductionScheduleSource`に`"retry:"`prefixのJobを登録しないという運用規約、25章R3）、安全性の主張には用いない。

**予約済みmetadataキー（Codex Round 3 SUGGESTIONS対応）**：一次機構が`"retry_candidate"`キーの不在に依拠するため、`ProductionScheduleSource`が登録するJob定義の`metadata`に、この文字列をキーとして含めてはならないという運用規約を追加する。これは`"retry:"`prefix予約（`job_id`側）と対をなす、`metadata`側の予約キー規約である——正当なproduction Jobが誤ってこのキーを`metadata`に含めてしまうと、一次機構によってそのJobのイベントが常に除外される（サイレントな機能不全）ため、`ProductionScheduleSource`の実装・レビュー時に確認すべき事項として23章のテスト観点にも追加する。

- この判定は `SchedulerEngine` 自体（pure boundary）には一切変更を加えず、Orchestrator側（呼び出し元）でのみ行う（Round 1から変更なし）。
- Retry候補由来のイベントをdispatch対象にしてしまうと、Retry Lineageの厳密なclaim/lifecycle管理（6.5節）を経由しない別ルートでの再実行が発生し、6.31/6.32が確立した安全契約を実質的に迂回することになる。これは本Releaseの Out of Scope「Retry lineage／eligibility／attempt contractの変更」に抵触する重大な設計リスクであるため、上記の二重の防御（provenance-based一次機構＋allowlist二次機構）で固定する。

---

## 17. Component Inventory：既存再利用 vs 新規

### 17.1 既存component再利用（無変更のままimport）

| Component | Package | 再利用方法 |
|---|---|---|
| `RetryRuntimeLock` | `src/retry_runtime_lock/` | 新しいlock pathで新規インスタンス化（12章） |
| `RetryRuntimeLoop` | `src/retry_runtime_loop/` | `run_once_fn=orchestrator.run_once` としてDI（13章） |
| `RetryRuntimeShutdown` | `src/retry_runtime_shutdown/` | そのままinstall()（13章） |
| `SchedulerEngine` / `SchedulerManager` / `SchedulerJob` / `SchedulerEvent` / `InMemorySchedulerRepository` | `src/scheduler/` | `evaluate()`/`run_due()`を呼ぶのみ、無変更 |
| `WorkflowEngineManager` / `WorkflowEngineEvent` / `SOURCE_SCHEDULER` / `CanonicalAdmissionFailure` | `src/workflow_engine/` | `.run()`を呼ぶのみ、無変更 |

### 17.2 新規package候補

| Package | 責務 |
|---|---|
| `src/scheduler_dispatch_ledger/` | `DispatchLedgerEntry` / `DispatchPhase` / `SchedulerDispatchLedger`（`claim()`/`confirm()`/`reconcile_stale_claims()`/`list_recovery_required()`/`peek()`）/ Store抽象＋JSON実装 / `SchedulerDispatchLedgerConfig`（8章） |
| `src/scheduler_schedule_source/` | `ProductionScheduleSource`（9章） |
| `src/scheduler_driver/` | `SchedulerDriverConfig`（6.6節のgate命名規約に倣う新規gate、`SCHEDULER_DRIVER_ENABLED`等）/ `SchedulerDriverCompositionRoot` / `SchedulerDriverOrchestrator`（`run_once()`）/ `SchedulerDriverCycleResult`（13・16章）/ `LockIntegrityViolationError`・`_verify_lock_ownership()`・`_release_if_owned()`（12.1〜12.2章 Lock Lifecycle Contract） |
| `scripts/run_scheduler_driver.py` | 新規CLIエントリスクリプト（13章） |

### 17.3 変更候補（既存ファイル、要Architecture Gate確認）

| ファイル | 変更内容 | 必須性 |
|---|---|---|
| `scripts/run_workflow_engine.py` | `build_demo_job()` を `ProductionScheduleSource().jobs()` 経由へ置換 | **必須**（9.2節で確定。`--job-id`手動経路には影響しない） |
| `.env.example` | `SCHEDULER_DRIVER_ENABLED` / `SCHEDULER_DISPATCH_LEDGER_DIR` 等の新規gate変数を追記 | 実装フェーズで対応（本Releaseのdocs更新方針、27章） |
| `docs/architecture.md` / `docs/ROADMAP.md` / `docs/CHANGELOG.md` | 実装完了後に新規セクション追記 | 本Architecture Phaseでは変更しない（成果物制約、27章） |

---

## 18. Crash-Window Safety Matrix

| # | Crash Window | Ledger状態（クラッシュ時点） | 検出タイミング | 結果 | 安全性の根拠 |
|---|---|---|---|---|---|
| 1 | `evaluate()` 呼び出し中 | record未作成 | — | 何も記録されない。次回tick/起動時に同じoccurrenceが再評価されクリーンにdispatchされる（正常、副作用未発生） | `evaluate()`はpure、副作用なし（6.1節） |
| 2 | `claim()`のdurable write中（fsync/os.replace未完了） | record未作成 or 部分書き込み（atomic saveのため実質未作成扱い） | 次回evaluate/起動 | 同一occurrenceを再度claim可能（安全、まだ`.run()`は呼ばれていない） | atomic save契約（tempfile→fsync→os.replace、`execution_history`/`retry_lineage`と同型を新規実装） |
| 3 | **claim成功 → `.run()`呼び出し前** | `CLAIMED` | 次回`reconcile_stale_claims()` | `RECOVERY_REQUIRED`。自動再dispatchなし | 11.1節(a)。`.run()`未着手のため副作用なし、fail-closedのみで十分 |
| 4 | **`.run()`実行中（内部でCanonicalAdmissionFailure等が発生する前にプロセス停止）** | `CLAIMED` | 次回`reconcile_stale_claims()` | `RECOVERY_REQUIRED`。自動再dispatchなし | 11.1節(b)。副作用が発生したか不明なためfail-closed必須 |
| 5 | `.run()`が例外を送出（プロセスは生存） | `CLAIMED`→`confirm()`で`CONFIRMED`（outcome=`EXCEPTION:...`） | 即時（同一cycle内） | 正常な記録完了。再dispatchされない（`CONFIRMED`は終端） | プロセス生存のため15章のcontainmentがそのまま機能 |
| 6 | `.run()`正常完了 → `confirm()`のdurable write前にプロセス停止 | `CLAIMED` | 次回`reconcile_stale_claims()` | `RECOVERY_REQUIRED`（過検知：実際には成功していた） | 8.2節で明記した意図的な安全側トレードオフ。`WorkflowExecutionRecord`自体は既に正しく記録されているため、workflow実行結果の正しさには影響しない。影響は「driverが同じoccurrenceを二度と自動dispatchしない」という保守的な扱いのみ |
| 7 | `confirm()`のdurable write中（fsync未完了） | 同上（#6と同型） | 次回`reconcile_stale_claims()` | `RECOVERY_REQUIRED` | 同上 |
| 8 | `confirm()`完了後 | `CONFIRMED` | — | 終端。再dispatchされない | `CONFIRMED`は`claim()`のacknowledged=False条件に含まれる |
| 9 | single-active-driver lock取得前に2つ目のdriverが起動 | — | 起動時 | 2つ目のdriverは`RetryRuntimeLockError`でCompositionRoot構築前に終了（fail-closed） | `RetryRuntimeLock`の既存契約（12章） |
| 10 | 1つ目のdriver(A)が生存中に運用者が誤ってlockファイルを削除し、2つ目のdriver(B)が起動 | AはPID_A、lockはPID_Bへ上書き | Aの次cycle先頭（run_once()冒頭）、または遅くともAが終了しようとする`finally`節（12.2節） | TOCTOU残存windowの外では、AがLock Integrity Violationを検知し`_release_if_owned()`が`release()`をスキップしてfatal終了。Bはそのまま単独driverとして継続動作。**TOCTOU残存windowの中では理論上Bのlockが削除されCが起動しうる（25章R2、未解消の低確率残存リスク）** | 12.1・12.2節。同一occurrenceへの二重dispatchはclaim()のacknowledged=False条件（8章）により、いずれの場合でも発生しない |
| 11 | `claim()`のストア読み取り自体が失敗（壊れたJSON・スキーマ不一致・権限エラー等） | 不明（読めない） | 即時 | `acknowledged=False`。`.run()`は呼ばれない | 8.5節(1)。「読めない」を「存在しない」と等値変換しない |
| 12 | `reconcile_stale_claims()`のディレクトリ列挙自体が失敗 | 不明（列挙できない） | 即時 | 当該cycleは**いかなるeventもdispatchしない**。例外が`run_once()`から伝播しfail-fast | 8.5節(4)(a)。部分的な結果での続行を禁止 |
| 13 | `reconcile_stale_claims()`の個別record読み取りフェーズ中、いずれか1件が読み取り失敗（壊れたJSON・スキーマ不一致） | 一部recordはCLAIMEDのまま（未遷移） | 即時 | いかなる書き込みも行わず例外送出。当該cycleは**いかなるeventもdispatchしない** | 8.5節(4)(b)。読み取り全件成功後にのみ書き込みフェーズへ進む順序設計 |
| 14 | `reconcile_stale_claims()`の個別record書き込みフェーズ中、いずれか1件の`RECOVERY_REQUIRED`書き込みが失敗 | 一部recordは`RECOVERY_REQUIRED`へ遷移済み、残りはCLAIMEDのまま | 即時（当該cycle） | 既に成功した遷移は保持（取り消さない）。例外送出により当該cycleは**いかなるeventもdispatchしない**。失敗したrecordは次回cycleで再試行される | 8.5節(4)(c)。各record遷移は独立してatomic・安全であり、group原子性は不要 |
| 15 | driver起動時、ledger storeの疎通確認自体に失敗（ディスク未マウント等） | — | 起動時 | 単一起動制約ロックを取得する前（または取得直後、claim前）に安全に終了 | 8.5節(5) |

---

## 19. Duplicate Suppression Summary（Completion Criteriaとの対応）

| Roadmap Completion Criteria | 対応するDesign Decision |
|---|---|
| loop driverによりScheduler eventからproduction workflowが起動・完走する | 13章（Orchestrator + 既存Loop再利用） |
| Runtime再起動後の重複dispatch防止（durable dispatch ledgerが再起動をまたいで同一eventの再dispatchを防ぐ） | 8章・11.2節（`claim()`のacknowledged=False条件、record永続） |
| 同一分内の複数tickでの重複dispatch防止 | 7章（occurrence_minuteへの正規化）+ 8章（claim once） |
| second driverの同時起動がfail-closedで拒否され、dispatchが行われない | 12章（`RetryRuntimeLock`再利用） |
| claim確定後・dispatch前の停止（failure-path）：`RECOVERY_REQUIRED`として識別、再起動後も二重dispatchされない | 11章・18章（行3・4） |
| Retry RuntimeプロセスとScheduler driverプロセスの同時実行時に競合・二重実行が発生しない | 14章（完全に独立したlock/store/対象） |
| Retry Runtime既存挙動（6.29.0〜6.33）がZero-Diffのまま維持される | 21章 |
| main.py直接実行経路がZero-Diffのまま維持される | 21章（`scripts/run_workflow_engine.py`の変更は`--job-id`手動経路に影響しない設計、9.2節） |

---

## 20. Manual Recovery Procedure（`RECOVERY_REQUIRED`診断・運用手順、Draft）

`retry_lineage_eligibility_durable_attempt_state.md` 9.4章（Manual Stale Lock Recovery Procedure）に相当する運用手順を、実装フェーズで以下の方針に沿って文書化する（本書ではプレースホルダとして方針のみ示す。Out of Scope: 自動復旧そのものは行わない）：

1. `SchedulerDispatchLedger.list_recovery_required()` で `RECOVERY_REQUIRED` のentry一覧（`job_id` / `occurrence_minute` / `claimed_at`）を取得する読み取り専用の診断手段を提供する（新規CLIスクリプトの実装は本Releaseでは確約しない。4章N3参照）。
2. 運用者は、対象の `job_id` と `claimed_at` 付近の時刻をキーに、Execution History（`scripts/show_execution_history.py`、既存）を照会し、該当する `WorkflowExecutionRecord` が実際に生成されているか（＝`.run()`が実際に呼ばれ、canonical recordが作られたか）を確認する。
3. 記録が見つからない場合：dispatchは実質的に発生しなかったとみなせる。次回の同一Jobのスケジュールで自然にカバーされる（DAILY/INTERVALの場合）か、手動で `--job-id` 経由（`scripts/run_workflow_engine.py`）で補完実行するかを運用者が判断する。
4. 記録が見つかる場合：dispatchは実際に発生していた（過検知だった、18章行6/7に相当）。追加対応は不要。

---

## 21. Backward Compatibility / Zero-Diff対象

以下は本Releaseで**一切変更しない**（git diff 0であることを実装フェーズのE2Eで機械的に確認する対象）：

- `src/scheduler/`（`SchedulerEngine.evaluate()`/`run_due()`の判定ロジック本体。呼び出し元の追加のみが許容され、本パッケージ自体への変更はゼロ）
- `src/workflow_engine/`（`WorkflowEngineManager.run()`のシグネチャ・内部動作）
- `src/execution_history/`
- `src/workflow_monitor/`
- `src/retry_lineage/`, `src/retry_engine/`, `src/retry_queue/`, `src/retry_history/`, `src/retry_composition/`, `src/retry_enqueue_trigger/`, `src/retry_runtime_orchestrator/`
- `src/retry_runtime_observability/`, `src/retry_observability_pipeline/`, `src/retry_runtime_logging/`
- `src/retry_runtime_lock/`, `src/retry_runtime_loop/`, `src/retry_runtime_shutdown/`（**参照のみ、コード変更ゼロ**）
- `scripts/run_retry_runtime.py`
- `side_effect_safety` / `protected_operation_manifest` 関連パッケージ

`scripts/run_workflow_engine.py` は9.2節で述べた通り**必須の変更対象**であり、Zero-Diff対象ではない（`build_demo_job()`呼び出し1箇所の置換のみ。`--job-id`手動経路・その他の挙動はZero-Diffのまま維持する）。

---

## 22. Planned File Impact（実装フェーズでの変更対象候補一覧、本Architecture Phaseでは未変更）

### 新規作成候補

- `src/scheduler_dispatch_ledger/__init__.py`
- `src/scheduler_dispatch_ledger/dispatch_phase.py`
- `src/scheduler_dispatch_ledger/dispatch_ledger_entry.py`
- `src/scheduler_dispatch_ledger/scheduler_dispatch_ledger.py`
- `src/scheduler_dispatch_ledger/scheduler_dispatch_ledger_store.py`（ABC + JSON実装）
- `src/scheduler_dispatch_ledger/scheduler_dispatch_ledger_store_lock.py`
- `src/scheduler_dispatch_ledger/scheduler_dispatch_ledger_config.py`
- `src/scheduler_dispatch_ledger/scheduler_dispatch_ledger_results.py`（`ClaimResult`/`ReconcileSummary`等）
- `src/scheduler_schedule_source/__init__.py`
- `src/scheduler_schedule_source/production_schedule_source.py`
- `src/scheduler_driver/__init__.py`
- `src/scheduler_driver/scheduler_driver_config.py`
- `src/scheduler_driver/scheduler_driver_composition_root.py`
- `src/scheduler_driver/scheduler_driver_orchestrator.py`
- `src/scheduler_driver/scheduler_driver_cycle_result.py`
- `src/scheduler_driver/scheduler_driver_lock_integrity.py`（12.1節 Ownership-Integrity Self-Check）
- `scripts/run_scheduler_driver.py`
- `tests/test_e2e_v6_34_0_scheduler_driver_duplicate_dispatch_safety_foundation.py`

### 変更対象（必須）

- `scripts/run_workflow_engine.py`（9.2節で確定。`build_demo_job()`呼び出しを`ProductionScheduleSource().jobs()`へ置換）
- `.env.example`（新規gate変数の追記）
- `tests/zero_diff_guard_registry.py`（`RELEASE_ORDER`へ`"v6.34.0"`追記、既存慣行）

### 変更対象（実装完了後、別タイミング）

- `docs/architecture.md` / `docs/ROADMAP.md` / `docs/CHANGELOG.md`（17.3節の通り、実装完了後に新規セクション追記。本Architecture Phaseでは変更しない）

### 変更しない（21章の通り）

- 上記21章に列挙した全パッケージ

---

## 23. Test / Architecture Guard / Formal Regression方針

実装フェーズで以下を新規E2Eとして検証する（本Architecture Phaseでは未実装・未実行）：

1. **Stable Event Identity**：同一Job・同一分内の複数回`evaluate()`呼び出しが同一`event_identity`を導出すること。異なるJob／異なる分では異なることを確認。
2. **Fail-Closed Dispatch**：`claim()`が`acknowledged=False`を返した場合、`WorkflowEngineManager.run()`が一切呼ばれないこと（Fake WorkflowEngineManagerの呼び出し回数で検証）。
3. **Duplicate Suppression — Restart**：`claim()`→`confirm()`完了後、プロセスを模した新規`SchedulerDispatchLedger`インスタンスで同一`event_identity`を`claim()`すると`acknowledged=False`になること。
4. **Duplicate Suppression — Same-minute multi-tick**：同一cycle内で`evaluate()`が同一occurrenceを複数回返す状況（テスト用に人為的に構成）で、2回目以降の`claim()`が`acknowledged=False`になること。
5. **Claim→Dispatch Crash（failure-path）**：`claim()`成功後、`.run()`呼び出し前に例外を模した中断を発生させ、`reconcile_stale_claims()`実行後に該当entryが`RECOVERY_REQUIRED`になること。再度`claim()`しても`acknowledged=False`であること（自動再dispatchなしの確認）。
6. **Second Driver Fail-Closed**：`RetryRuntimeLock`を先に取得した状態で2つ目の取得を試み、`RetryRuntimeLockError`が送出されCompositionRoot等が一切構築されないこと（既存`RetryRuntimeLock`の契約テストパターンを踏襲）。
7. **Retry-candidate除外（16章）**：`job_id="retry:xxx"`を含む`SchedulerEvent`がOrchestratorの`_dispatch_one`へ渡らないこと（Fake WorkflowEngineManagerが呼ばれないことで検証）。
8. **Exception containment（15章）**：`.run()`が`CanonicalAdmissionFailure`を送出しても、`run_once()`全体が例外を伝播させず、他eventの処理・次cycleが継続すること。
9. **`confirm()`戻り値の確認（8.2節）**：`confirm()`がFalseを返すケースで、entryが`CLAIMED`のまま残り、次回reconciliationで`RECOVERY_REQUIRED`になること（6.32 Suggestionと同種のgapを新規コードで再発させていないことの直接的な回帰防止テスト）。
10. **既存Zero-Diff確認**：`git diff --quiet` による21章列挙パッケージの無変更確認（既存Architecture Guardパターンを踏襲）。
11. **Ownership-Integrity Self-Check（12.1節、Codex Round 1 Blocking#1対応）**：lockファイルの中身を人為的に別PIDへ書き換えた状態で`run_once()`を呼び出し、（a）`reconcile_stale_claims()`/`evaluate()`/claim/dispatchのいずれも実行されないこと、（b）`LockIntegrityViolationError`が送出されること、を検証する。
12. **Lock Lifecycle Contract／`finally`節でのrelease判定（12.2節、Codex Round 2 Blocking#1・Round 4 SUGGESTIONS対応）**：(a) cycle先頭の検証は通過したが、cycle処理の途中でlockファイルの中身が別PIDへ書き換わるケース（例：`_dispatch_one`実行中に人為的にlockファイルを書き換える）で、`main()`の`finally`節に到達した際に`_release_if_owned()`が`lock.release()`を呼ばない（lockファイルの中身が書き換え後のPIDのまま残る）ことを検証する。(b) 正常終了・想定内例外（8.5節のstore失敗等）・`RetryRuntimeShutdown`によるGraceful Shutdown・未捕捉の予期しない例外、のいずれの終了経路でも`_release_if_owned()`が必ず呼ばれる（`finally`節の網羅性）ことを検証する。(c) 起動直後（`lock.acquire()`成功・自プロセスが正しくPIDを書き込んだ直後）の`try`ブロック内側での初回ownership検証について、正常系（自PIDと一致し`LockIntegrityViolationError`が送出されずそのまま本体処理へ進む）を検証する。(d) 起動直後の検証がまれに失敗するケース（lockファイルの読み取り自体が失敗する場合、PIDが一致しない場合）をそれぞれ人為的に再現し、`LockIntegrityViolationError`が送出され、`finally`節の`_release_if_owned()`がその時点のownership（この場合は不一致）を再検証してreleaseをスキップし、lockファイルを変更せずに残すことを検証する。
13. **3台目driverのエスカレーション遮断（TOCTOU残存window外のケース、12.1・12.2節、Codex Round 1 SUGGESTIONS・Round 5 SUGGESTIONS対応）**：Driver A起動→lockファイル手動削除→Driver B起動→（Bのlockが生存する状態で、かつAの次回ownership検証タイミングとBによる上書きの間に十分な時間差があるケース＝TOCTOU残存windowの外）Aに次cycle（またはシャットダウン処理）を実行させ、AがLock Integrity Violationを検知しBのlockを削除せずに終了すること、その後Driver Cの起動を試みても引き続きBがlockを保持しているため`RetryRuntimeLockError`で拒否されること、をシナリオE2Eとして検証する。**本テストが検証するのはTOCTOU残存window外での保証であり、25章R2で明示する通りTOCTOU残存window内でのエスカレーション遮断は保証範囲外であることに注意する**（本テスト自体はTOCTOU window内の挙動を再現・検証するものではない）。
14. **Ledger Store I/O失敗（8.5節、Codex Round 1 Blocking#2・Round 2/Round 3 Blocking#2対応）**：(a) 破損したrecordファイルを人為的に配置した状態で`claim()`を呼び、`acknowledged=False`になり`.run()`が呼ばれないこと。(b) ledgerディレクトリを列挙不能にした状態で`reconcile_stale_claims()`を呼び、例外が`run_once()`から伝播し当該cycleで一切dispatchされないこと。(c) 複数の`CLAIMED`recordが存在する状況で、うち1件が読み取り不能（壊れたJSON）な場合、いかなる書き込みも行われないまま例外が送出されること（読み取り全件成功後にのみ書き込みへ進む順序の検証）。(d) 複数の`CLAIMED`recordのうち1件の書き込みのみを失敗するよう仕込み、他のrecordは正しく`RECOVERY_REQUIRED`へ遷移し、かつ当該cycleでは新規eventが一切dispatchされないことを検証する。(e) **（Round 3 Blocking#2対応）** reconciliationの読み取りフェーズがrecordを`CLAIMED`と読み取った後、per-recordロック取得前に、当該recordを（テストコードから直接）`CONFIRMED`へ書き換え、書き込みフェーズのfresh readがこの変化を検出して当該recordへの書き込みをスキップする（`RECOVERY_REQUIRED`で上書きしない）ことを検証する。(f) 読み取りフェーズのスナップショット後・書き込みフェーズ前に、新規recordを追加した場合、reconciliationが当該recordに一切触れないことを検証する。
15. **Provenance-based Retry除外（16章、Codex Round 1 Major#1・Round 2/Round 3 Major#1対応）**：(a) `metadata["retry_candidate"]`キーを持つevent（`job_id`がproduction job_idと偶然一致するよう細工したケースを含む）がdispatch対象から除外されること。(b) `job_id`が`ProductionScheduleSource.jobs()`に含まれないevent（一次機構をすり抜けたと仮定した場合でも）が二次防御（allowlist）で除外されること。(c) `ProductionScheduleSource`に`"retry:"`prefixを持つJobを誤って登録しても、`metadata["retry_candidate"]`キーを持たない限り正しくdispatch対象に含まれること（allowlist側は`"retry:"`prefixを特別扱いしない）。(d) `ProductionScheduleSource`が返すJob定義の`metadata`に予約キー`"retry_candidate"`が含まれていないことを確認する静的チェック（構成テスト）を追加する。
16. **Scheduler Driver / Retry Runtime 構造的非干渉（14.1節、Codex Round 1 Major#3対応）**：Scheduler Driverの`.run/scheduler_driver.lock`とRetry Runtimeの`.run/retry_runtime.lock`を同時に保持できること（互いのlock取得を妨げないこと）、および双方の`WorkflowEngineManager.run()`呼び出しが独立した`run_id`を生成し互いのExecution History recordを上書きしないことを確認する（content-level idempotencyは対象外と明記した上でのrecord-level非衝突テスト）。
17. **`scripts/run_workflow_engine.py`変更の実装整合性確認（9.2節、Codex Round 2 Major#2対応）**：(a) `--job-id`手動経路の挙動（`resolve_event()`の`args.job_id is not None`分岐）が変更前後で完全に同一であること。(b) `ProductionScheduleSource.jobs()`が返す全件が`register_job()`で登録されること。(c) 診断メッセージが`ProductionScheduleSource`の実際の内容から導出され、削除済みの`DEMO_JOB_ID`/`DEMO_JOB_SCHEDULE`定数への参照が残っていないこと。

Formal Regressionは既存の「正式Inventory」方式（現行35ファイル、5853/5853 PASS基準）を維持し、新規E2Eファイル追加後の全体PASSを実装完了時に確認する。

---

## 24. Rejected Alternatives

1. **`RetryLineageManager`と同一の4-phase+owner_token authorityモデルをそのままdispatch ledgerへ複製する案** → 却下（8.4節）。single-active-driver制約下では過剰な複雑さであり、「retry側のownership/state machineを勝手に拡張しない」という設計原則にも反する（模倣ではなく別モデルとして独立させる）。
2. **`execute_time`を秒精度のままevent identityに使う案** → 却下（7章）。同一分内複数tickの重複防止要件を満たせない。
3. **claim/dispatch/confirmをRetry Runtimeと同一の`RetryExecutionLock`ファイルで直列化する案** → 却下（14章）。Scheduler DriverとRetry Runtimeの独立性（ownership分離）という明示的要求に反する。両者は別々のロックを持つべきである。
4. **claim成功後、`.run()`実行中の例外を再raiseしてcycle全体を失敗させる案** → 却下（15章）。1つのJobの一時的な失敗が他のJob・以降のcycle全体をブロックすることは、production運用上望ましくない（既存Retry Runtimeの「ベストエフォート継続」哲学とも整合しない）。
5. **claim成功→dispatch前クラッシュとdispatch中クラッシュを区別して記録する案（例：`DISPATCHING`という中間phaseを追加）** → 却下（11.1節）。`run_id`はdriver側で事前に取得できないため、区別する情報的根拠がなく、区別しようとすること自体が誤判定リスクを生む。単純に両者をまとめて`RECOVERY_REQUIRED`とする方が安全側に振れる。
6. **`RetryRuntimeLock`/`RetryRuntimeLoop`/`RetryRuntimeShutdown`を`Scheduler*`名へリネームして再利用する案** → 却下（6.4節Finding F3）。既存パッケージへの変更はZero-Diff対象への侵犯となり「scope外変更は禁止」に抵触する。命名の不整合は許容し、Open Issueとして記録する（26章）。
7. **`job_id`の`"retry:"`prefix判定のみをretry-candidate除外の唯一の安全機構とする案（旧版の設計）** → 却下（16章、Codex Round 1 Major#1・Round 2 Major#1対応）。将来のretry候補event表現変更に追従できない（False Negative）・偶然prefixが一致した正当なJobを永久に除外してしまう（False Positive）という双方向の脆弱性を持つため、`job_id`という値ベースの判定そのものを一次機構から外した。現行設計（16章）では`metadata["retry_candidate"]`キーの不在（provenance-based）を一次機構、`ProductionScheduleSource`ベースのallowlistを二次防御、prefix判定を二次機構内の副次的ログ用ヒントへ格下げしている。
8. **`scripts/run_workflow_engine.py`を変更せず、新設`scripts/run_scheduler_driver.py`だけを新しいproduction schedule sourceの消費者とする案** → 却下（9.2節、Codex Round 1 Major#2対応）。同一のproduction Job定義が2箇所に残存し、Roadmapが求める「一元化」に反する。
9. **single-active-driver lockの整合性違反検知に、`RetryRuntimeLock`自体を改修してowner tokenを持たせる案** → 却下（12.1節、Codex Round 1 Blocking#1対応）。`RetryRuntimeLock`は既存Retry Runtimeが依存するZero-Diff対象であり、改修は本Releaseのscope外。呼び出し側（新規`src/scheduler_driver/`）だけで完結するOwnership-Integrity Self-Checkを新設する方式を採用した。
10. **Ownership-Integrity Self-Checkをcycle境界のみで検証し、`release()`は従来通り無条件に呼ぶ案（Round 1初版）** → 却下（12.2節、Codex Round 2 Blocking#1対応）。cycle処理中に奪われたlockを、終了処理が古い（cycle先頭時点の）検証結果のまま無条件release()してしまう経路が残ることが判明したため、`release()`の唯一の呼び出し経路を`main()`の`finally`節へ集約し、release直前に必ず再検証するLock Lifecycle Contractへ改訂した。
11. **retry-candidate除外を`job_id`（prefix または allowlistメンバーシップ）のみで判定し続ける案（Round 1改訂版）** → 却下（16章、Codex Round 2 Major#1対応）。`job_id`という値に依拠する限り、将来の表現変化に対する本質的な脆弱性が残ることが判明したため、`SchedulerEngine`自身が構造的に発する`metadata["retry_candidate"]`キーの有無を一次機構へ格上げした。
12. **`ProductionScheduleSource.jobs()`を導入しつつ、`scripts/run_workflow_engine.py`の`register_job()`呼び出し・`events[0]`選択・診断メッセージの具体的な置換方法を実装フェーズの裁量に委ねる案（Round 1版）** → 却下（9.2節、Codex Round 2 Major#2対応）。型不一致（1件返却 vs list返却）を放置すると実装不能であることが判明したため、Architecture Phaseの時点で置換仕様（全件ループ登録・`events[0]`選択ロジックの意図的維持・診断メッセージの導出元変更）を具体的に確定した。
13. **reconciliationの書き込みフェーズで、列挙・読み取りフェーズ時点のスナップショットを無条件に信頼してそのまま書き込む案（Round 2版）** → 却下（8.5節(4)(c)、Codex Round 3 Blocking#2対応）。TOCTOU残存window（12.2節）の中で別driverが正当に`CONFIRMED`まで進めていた場合、スナップショットのまま書き込むと正当な状態を`RECOVERY_REQUIRED`で上書きしてしまう。per-recordロック取得後に必ずfresh readで`phase`を再確認する契約（`retry_lineage_manager.py`の既存precedentと同型）へ改訂した。
14. **起動時のownership検証を`try`ブロックの外（`acquire()`の直後・`try`の前）で行う案（Round 2版）** → 却下（12.2節、Codex Round 3 Blocking#1対応）。検証自体が予期せず失敗した場合に`finally`の保護を受けずlockがleakするリスクがあるため、検証を`try`ブロックの内側・本体処理の直前へ移動した。

---

## 25. Risks / Open Questions

| # | 内容 | 深刻度 | 対応方針 |
|---|---|---|---|
| R1 | `confirm()`のdurable write失敗時、実際には成功したdispatchが`RECOVERY_REQUIRED`として過検知される（18章行6/7） | Low | 意図的な安全側トレードオフとして許容（8.2節）。20章のManual Recovery Procedureで運用者が確認可能 |
| R2 | Ownership-Integrity Self-Check＋Lock Lifecycle Contract（12.1・12.2節）導入後も残る、`_verify_lock_ownership()`の読み取りと`lock.release()`の削除の間のTOCTOU（Time-of-Check-Time-of-Use）残存window。この窓の中では、12.1節のシナリオ（Aが誤ってBのlockを削除しCが起動する）が理論上なお発生しうる——**Accepted（許容）、Low確率、ただし未解消**であり「解消済み」とは記載しない（Codex Round 3 Major#1対応：以前の版の「構造的に遮断」という無条件の表現を撤回）。**加えて（Codex Round 4 Major#1対応で追記）**：この残存windowの中で、reconciliationを実行する側のdriverが、もう一方のdriverが真に処理中（`claim()`済みだがまだ`confirm()`未到達）の`CLAIMED` recordを、区別できずに`RECOVERY_REQUIRED`へ誤って遷移させてしまう可能性がある（8.2節・8.4節）。これは診断上の過検知（R1と同種）であり、`confirm()`側の`phase==CLAIMED`要求（8.2節）により、実際に処理していたdriverの`confirm()`が単にFalseを返すだけで、状態の不整合な上書きやduplicate dispatchには至らない | Low（発生確率はfile I/O呼び出し2回分の間隙まで縮小したが、理論上ゼロではない） | 3台目以降へのエスカレーションの発生確率は、cycle境界だけでなく全終了経路（12.2節`finally`節）でのownership再検証により実務上無視できる水準まで低減したが、完全には排除されない。**一方、同一occurrenceへの二重dispatchは、lockの完全性とは独立した`claim()`のacknowledged=False条件（8章）により、この残存window内でも無条件に防止される**——lockの役割は「driver多重化そのものを防ぐ」ことであり、「duplicate dispatchを防ぐ」役割はlockではなくledgerの`claim()`契約が担っている、という責務分離を明記する |
| R3 | `ProductionScheduleSource`に`"retry:"`prefixを持つJobが誤って登録された場合、16章の二次防御（prefix除外ヒント）により当該Jobの扱いが紛らわしくなる | Low | 16章のRound 2改訂により、一次機構が`metadata["retry_candidate"]`キーの有無というprovenance signalへ移行したため、`"retry:"`prefixの扱いは安全性の根拠から完全に外れた。運用規約として`"retry:"`prefixのJob命名を避けることをドキュメント化する（既存`retry_scheduler_event_integration`と同じprefix予約を踏襲） |
| R4 | `RetryRuntimeLock`/`RetryRuntimeLoop`/`RetryRuntimeShutdown`の名称が`Retry`ドメインを示唆するが実際は汎用（6.4節） | Low（命名のみ、機能影響なし） | リネームはscope外。Open Issueとして記録し、将来リネームする場合は独立Releaseとして扱う |
| R5 | （解消済み、Codex Round 1 Major#2対応）`scripts/run_workflow_engine.py`の変更要否 | — | 9.2節で「必須」として確定済み。旧R5は削除し、Architecture Gate Checklist（26章）からも該当項目を除去した |
| R6 | Scheduler DriverとRetry Runtimeが同時に大量のproduction workflowを起動した場合のリソース競合（プロセス数・WordPress API rate limit等）、および同時実行時のcontent-level重複（14.1節） | Medium | 本Releaseのrecord-level duplicate dispatch防止契約の対象外（14.1節で明確化）。`duplicate_filter`拡張は既存Post-MVP項目であり本Releaseの対象外。運用ドキュメントでの注意書きに留める |
| R7 | dispatch ledgerの`state/scheduler_dispatch/`が無限に増え続ける（cleanup機構なし） | Low（MVP） | `retry_lineage`同様、完全な永続化戦略・cleanupはOut of Scope／post-MVP候補として明記する |
| R8 | ledgerストアが一度durable ackされたrecordを外部改変・削除された場合の防御なし（8.5節(6)） | Low | 本コードベースの全JSONベースdurable storeに共通する既存前提。新規脆弱性ではない |
| R9 | `ProductionScheduleSource.jobs()`が将来複数Jobを返すようになった場合、`scripts/run_workflow_engine.py`は`events[0]`のみを処理し続けるため、同一分に複数Jobが同時マッチしても先頭の1件しか処理しない（9.2節） | Low（現行MVPは1件のみのため顕在化しない） | 意図的な責務分担（`run_workflow_engine.py`は単発診断ツールのまま、複数event一括処理は新設`scripts/run_scheduler_driver.py`が担う）。`ProductionScheduleSource`が複数Jobを返すよう拡張される際に、本リスクを再評価することをドキュメント化する |

---

## 26. Architecture Gate Checklist（Human Gate必須確認事項、未承認）

実装着手前に、以下をユーザーが明示的に承認すること（`retry_lineage_eligibility_durable_attempt_state.md` 26章の precedent に倣う）：

1. Design Decision B（8章・8.5節）：3-phase・owner_token authorityなしのdispatch ledgerモデルと、そのstore-level failure semantics——特に`reconcile_stale_claims()`の読み取り全件成功後にのみ書き込みへ進む順序設計、per-record locking、部分書き込み時の扱い（8.5節(4)、Codex Round 2 Blocking#2対応）に同意するか。
2. Design Decision E（11章）：claim成功→dispatch前クラッシュとdispatch中クラッシュを区別せず一律`RECOVERY_REQUIRED`とする設計（11.1節）に同意するか。
3. Design Decision F・12.1〜12.2節：Ownership-Integrity Self-Check＋Lock Lifecycle Contract（Codex Round 1 Blocking#1・Round 2 Blocking#1対応）——「`lock.release()`の唯一の呼び出し経路を`main()`の`finally`節1箇所に集約し、releaseの直前に必ずownershipを再検証する」という設計、および残存するTOCTOU窓（25章R2）に同意するか。
4. Design Decision J（16章、Codex Round 1 Major#1・Round 2 Major#1対応）：`metadata["retry_candidate"]`キーの不在をprovenance-basedな一次機構とし、`ProductionScheduleSource`ベースのallowlistを二次防御とする改訂設計に同意するか。
5. Design Decision H・14.1節（Codex Round 1 Major#3対応）：Roadmap Completion Criteria「競合・二重実行が発生しない」を、record-level非衝突（本Release保証範囲）とcontent-level idempotency（本Release対象外、既存Post-MVP `duplicate_filter`項目へ委ねる）に分離して解釈することに同意するか。
6. 9.2節（Codex Round 1 Major#2・Round 2 Major#2対応、確定済み）：`scripts/run_workflow_engine.py`の`build_demo_job()`を`ProductionScheduleSource().jobs()`（全件ループ登録）へ置換し、`events[0]`のみを処理する既存挙動は意図的に維持する（25章R9）、という結論を追認するか。
7. R4（25章）：`RetryRuntimeLock`等の`Retry`命名を冠する汎用コンポーネントを、Scheduler Driverの文脈でそのまま再利用すること（リネームなし）に同意するか。
8. 8.3節：`dispatch_run_id`/`outcome_summary`が診断専用であり安全性の権威ではないという設計上の位置づけに同意するか。
9. 20章：Manual Recovery Procedureの新規CLIスクリプト実装（`list_recovery_required()`を消費する専用CLI）を本Release実装フェーズのスコープに含めるか、含めないか（本書は含めないことを前提に設計しているが、確認を要する）。

---

## 27. Roadmap / architecture 整合性チェック（報告のみ、doc変更なし）

- `docs/MVP_COMPLETION_ROADMAP.md` の6.34節（212-239行）記載のIn Scope／Out of Scope／Completion Criteriaと、本書2章・19章の対応関係に矛盾は見つからなかった。
- `docs/architecture.md` には現時点でRelease 6.34に関する記述は存在しない（本Architecture Phaseでは追記しない。実装完了後、既存の「〜Foundation層」形式に倣って追記する）。
- `docs/CHANGELOG.md` にも6.34エントリは存在しない（同上、実装完了後に追記）。
- 不整合・要修正事項は見つからなかった。

---

## 28. Architecture Releaseとして開始可能かの判定

本書はDraft段階であり、Codex `codex-readonly-review` によるRound 1〜5のレビュー（Round 1: NOT APPROVED、Blocking 2/Major 4/Minor 2。Round 2: NOT APPROVED、Blocking 2/Major 2/Minor 1。Round 3: NOT APPROVED、Blocking 2/Major 2/Minor 2。Round 4: NOT APPROVED、Blocking 0/Major 1/Minor 2/Suggestions 1。**Round 5: APPROVED、Blocking 0/Major 0/Minor 1/Suggestions 1**）を実施し、指摘事項をいずれも本改訂（8.2節・8.4節・8.5節・9.2節・12.1〜12.2節・13章・14.1節・16章・17.2節・18章・22章・23章・24章・25章・26章・5章）で反映した。Round 5でCodex独立read-only reviewは`VERDICT: APPROVED`（Blocking 0／Major 0）に到達した。残るのはユーザーによるHuman Gate Checklist（26章）の明示的承認のみであり、これが完了するまで実装フェーズには着手しない。

**現時点の判定：NOT READY（Architecture Review自体は完了・APPROVED。ユーザーによるHuman Gate Checklist（26章）承認待ちのため実装は未着手）**
