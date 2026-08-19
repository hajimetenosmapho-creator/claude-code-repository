# MVP Completion Roadmap（v1.3）

Release 6.30開始前に、MVP到達までのRelease計画を正式化したドキュメント。個々のReleaseの詳細設計は各`docs/design/*.md`で別途行い、本書はスコープ全体の地図として維持する。

**v1.3（正式版）**：v1.0はCodex Architecture Review（round 1）で`NEEDS_REVISION`（Major M-1〜M-7）、v1.1はArchitecture Reconciliationを踏まえた改訂だったがCodex Review（round 2）で再度`NEEDS_REVISION`（Major A-1〜A-6）、v1.2はA-1〜A-6への対応版だったがCodex Review（round 3）で再度`NEEDS_REVISION`（Major M3-1〜M3-4、Minor N3-1/N3-2、Suggestion S3-1）と判定された。v1.3改訂時点では、M3-1〜M3-4・N3-1・N3-2・S3-1を反映し、①6.30/6.31間の循環依存解消、②retry lineage契約の追加、③attempt lifecycleのcrash boundary契約、④外部副作用のfail-closed契約、⑤段階的activation gate、を確定したもの。Codex Review（round 4）で`APPROVED_WITH_SUGGESTIONS`（Blocking 0／Major 0）となり、Minor（R4-N1）・Suggestion（R4-S1／R4-S2）を反映のうえ正式版として採用した。

---

## Baseline

- Release 6.29.0
- main / `fce5ded`
- origin/main同期
- Working Tree clean
- Formal Regression：正式Inventory32ファイル、5376/5376 PASS

上記はRoadmap作成時点（v1.0起草時）のスナップショットであり、以降のcommitで状態が変わっている可能性がある。Release着手前に都度re-confirmすること。

---

## MVP Definition of Done

ゲームニュースを自動取得・選定し、記事本文と必要な画像を生成してWordPressへ安全に下書き投稿できること。
さらにRuntime実行状態がExecution Historyとして記録され、主要な失敗についてRetry enqueue・Retry処理・基本Observabilityが実Runtime経路で機能し、その一連のworkflowをSchedulerから実行できること。

この「Runtime実行状態の記録」は、canonical production workflow（Workflow Engine → NEWS → main.py経路）が生成する、workflow単位の唯一のretryable record（`WorkflowExecutionRecord`）を指す。main.py単体の直接実行はこの境界の対象外。

DoD自体の変更はRoadmap更新の範囲外とし、別途Human承認を要する（Roadmap Governance章参照）。

---

## Architecture Reconciliation（v1.0からの主要な事実修正）

Architecture Reconciliation（read-only investigation）により、v1.0の前提の一部が実態と異なることが判明した。

- **main.pyは現時点でExecution Historyへ一切書き込んでいない**（v1.0と同じ事実）。ただし、既に`WorkflowEngineExecutor`が「Workflow Engine → NEWSステップ → main.py subprocess」という経路でworkflow単位の`WorkflowExecutionRecord`を生成する仕組みが実装済みである（`AI_AGENT_ENABLED` / `WORKFLOW_ENGINE_ENABLED`の二重ゲート待ち・未有効化状態）。
- **Monitor→Trigger→Queue→RetryRuntimeの配線は既に完成している**（v1.0が前提としていた「6.31/6.32で新規に組み立てる」という認識は誤り）。`scripts/run_retry_runtime.py --loop`により自律的な定期Retryも既に実行可能。
- 残るGapは「新規配線の構築」ではなく、(a) 本番canonical runの確立、(b) 既存Retry経路の安全性強化、(c) Scheduler駆動方式の決定、の3点に整理される。

### canonical runの確定

- MVP本番経路では、`WorkflowEngineExecutor`が生成するworkflow単位の`WorkflowExecutionRecord`を**唯一のretryable record**とする。
- main.py自身にはExecution History書き込みを追加しない。
- `python main.py`の直接実行はMVP本番Execution History対象外（開発・手動検証用の経路として扱う）。
- **1 production invocation = 1 canonical retryable record**。二重record・二重enqueueは禁止。

---

## Release Plan

### 6.30 — Production Canonical Run & Outcome Contract

- **Goal**：既存のWorkflow Engine → NEWS → main.py経路をMVP本番canonical runとして定義・成立させ、main.pyの主要終了状態が外側`WorkflowExecutionRecord`へ安全に反映される契約を確定する。
- **境界（v1.3で明確化）**：6.30の責務は`canonical WorkflowExecutionRecord → FAILED/TIMEOUT candidateの生成`までとする。FAILED/TIMEOUT candidateを実際にRetry Eligibilityへ渡して判定する責務は**6.31**に属する（M3-1対応。6.30がRetry判定の実装・E2Eを完了条件に含めることを禁止し、6.30↔6.31の循環依存を解消する）。
- **Precondition（Architecture Gate）**：canonical production pathを有効化する前に、以下をArchitecture Gateとして確認する：
  - `AI_AGENT_ENABLED` / `WORKFLOW_ENGINE_ENABLED`を有効化した場合の影響範囲の確認
  - NEWS以外のworkflow step（REVIEW／PUBLISH等）について、**gate combination（有効／無効の組み合わせ）ごとに、期待されるexecuted有無・action_taken・external side effectを明示した検証表**を作成し、実際の挙動と照合した証跡を残す（「影響範囲を確認した」という記録のみでは不可。組み合わせごとの期待値と実測結果の対応表を要求する）
  - 上記Gateを通過するまで、ゲート有効化を含む実装には着手しない
- **In Scope**：
  - Workflow Engine経由の起動をMVP本番の唯一の実行経路として確立（ゲート有効化含む、Precondition通過後）
  - main.pyの終了状態を`WorkflowExecutionStatus`（RUNNING/SUCCESS/FAILED）へ対応させる契約の確定。最低限、以下の終了経路について**期待statusを明記したdecision table**を作成する：
    - config error → FAILED
    - uncaught exception → FAILED
    - 対象0件 → 期待statusを本Release設計時に決定・明記（SUCCESS扱いかFAILED扱いかを決定table化する。「未確定のまま実装へ委ねる」ことを禁止する）
    - normal success → SUCCESS
    - WordPress全失敗 → FAILED
    - partial success → 期待statusを同様にdecision table化する（6.32のHuman Review判定の入力になるため、本Releaseで確定必須）
    - side effect発生後failure → 同様にdecision table化する
    - forced terminationは以下2種を明確に分離し、**normal completion（SUCCESS/FAILED分類）とは別カテゴリとして扱う**：
      - **main.py child process abnormal termination**：Workflow Engine側が検知可能な終了として扱い、FAILEDに分類する
      - **parent/runtime interruptionによるabandoned RUNNING record**：SUCCESS/FAILEDへ分類しない。RUNNINGのまま残し、既存`WorkflowMonitor`のTIMEOUT契約（RUNNINGかつ経過時間超過→TIMEOUT）による検出に委ねる
  - abandoned RUNNING recordが、既存`WorkflowMonitor`のTIMEOUT契約により**FAILED/TIMEOUT candidateとして検出可能であること**を実装・E2Eで保証する（TIMEOUT判定の実装・検出までが6.30の責務。判定結果をRetry Eligibilityへ実際に引き渡す実装・E2Eは6.31の責務）
- **Out of Scope**：Retry enqueue、Retry execution、Retry Eligibilityへの実引渡し（6.31のスコープ）、Scheduler連携。main.py自身へのExecution History書き込み追加。
- **Dependency**：なし（6.29.0までのFoundation群の上に直接乗る）。Precondition（Architecture Gate）の通過が実装着手の前提。
- **Completion Criteria**：
  - Precondition（Architecture Gate）：gate combinationごとの検証表が作成され、NEWS以外のworkflow stepのexecuted／action_taken／external side effectにZero-Diffがあることの実測証跡が残っていること
  - Workflow Engine経由の実行1回につき、`WorkflowExecutionRecord`が1件のみ生成されること（二重record防止の確認を含む）
  - 上記decision tableの各終了経路（対象0件／partial success／side effect後failure含む）について、外側recordが期待するSUCCESS/FAILEDへ正しく分類されることをE2Eで確認
  - **child process abnormal termination**と**abandoned RUNNING→TIMEOUT**を、別々のE2Eシナリオとして検証すること（同一シナリオでの代替を禁止）。ただし本Releaseで検証するのは「TIMEOUTとして検出可能であること」までであり、Retry Eligibilityへの実引渡し検証は6.31のCompletion Criteriaに属する
  - Formal Regressionで既存機能に回帰がないこと（証跡は「Regression / Zero-Diff Evidence」章の共通要件に従う）
  - 未着手下流（Retry Enqueue／Scheduler等）がZero-Diffのまま維持されること
  - main.pyの直接実行（Execution History対象外の経路）が引き続き無影響で動作すること
- **Activation**：本Release完了時点では、automatic production RetryとScheduler unattended production dispatchはOFFのまま（Staged Activation Gates章参照）。

### 6.31 — Retry Lineage, Eligibility & Durable Attempt State

- **Goal**：既存のMonitor→Trigger→Queue→RetryRuntime配線を前提に、6.30が検出したFAILED/TIMEOUT candidateを実際にRetry Eligibilityへ引き渡す実装を確立し、retryの親子関係（lineage）とattemptのcrash boundaryを安全な契約として確定する。
- **In Scope**：
  1. **6.30からの実引渡し（M3-1対応で本Releaseへ移管）**：
     - abandoned RUNNING→TIMEOUT検出後、当該recordが実際にRetry Eligibility判定へ引き渡されることを実装・E2Eで検証する
  2. **Retry lineage契約（M3-2対応）**：Durable Retry Control Stateの権威キーを単一`run_id`からroot lineageへ拡張する。
     - 初回canonical runでは`root_run_id = run_id`とする
     - Retry実行では新しい`run_id`を生成してよいが、retry派生runは同じ`root_run_id`をdurableに継承する
     - 必要に応じて`parent_run_id`もdurableに保持する
     - Retry attempt／eligibility／terminal disposition／next eligible条件は**`root_run_id`単位**で管理する
     - retry失敗により新しい`run_id`が生成されても、`root_run_id`のattemptがattempt=1へ戻ることを禁止する
     - lineage情報はRuntime再起動後も復元可能であること
     - Execution History再走査時も、既存lineageへ再接続すること（新規lineageとして扱わない）
     - 具体的な保存先・record拡張方式（`WorkflowExecutionRecord`拡張か別storageか等）は6.31 Architecture設計時に決定する
  3. **Retry state transition契約**（具体的なbypass実装方式は本Release設計時に決定可能だが、以下の契約はRoadmapで固定する）：
     - Retry対象では、NewsAgent interval guardによる**silent success（実行せずにsuccess扱いされる状態）を禁止**する
     - main.py実行前にguard等により実行不能と判定された場合、success扱いにしない
     - その場合attemptを消費せず、Queueから成功除去もしない
     - loopごとに同一項目を即座に再実行し続ける「hot retry」を防ぐため、明示的な**next eligible condition／time**を持つ
     - 実際にRetryが行われた場合、main.pyが実際に再起動・再実行されたことをE2Eで証明する
  4. **Attempt lifecycle / crash boundary契約（M3-3対応）**：claimとattempt消費を分離する。最低限、以下4 phaseを区別する（名称はArchitecture設計時に変更可、意味は固定）：
     - `READY/ELIGIBLE`：Retry対象として認識されているが、まだclaimされていない
     - `CLAIMED`：Retry実行のために占有されたが、まだ実行開始していない
     - `EXECUTION_STARTED`：実際にretry executionへ制御が渡された
     - `TERMINAL`：最終結果（成功／失敗／Human Review行き等）が確定した
     契約：
     - `CLAIMED`の時点ではattemptを消費しない
     - `CLAIMED`後、`EXECUTION_STARTED`前にプロセスが停止した場合：attemptは非消費のまま扱う。Runtime再起動後、当該claimを安全に回収・再評価できること
     - actual retry executionへ制御を渡す直前に`EXECUTION_STARTED`をdurableに確定し、その時点でattemptを1消費する
     - `EXECUTION_STARTED`確定後にクラッシュした場合：実処理が開始された可能性があるものとして、attempt消費済みの状態に倒す（安全側）
     - terminal outcomeが確定した時点で`TERMINAL`へ更新する
     - guard等により実行が開始されなかった場合はattempt非消費・success扱い禁止（3.の契約と整合）
     - **通常のRetry実行では、`READY/ELIGIBLE → CLAIMED → EXECUTION_STARTED → TERMINAL`の4 phaseをこの順序で必ず経由する（R4-S1対応）**。`CLAIMED`を経由せず`READY/ELIGIBLE`から`EXECUTION_STARTED`へ直行する実装は本契約違反とする
  5. **Minimal Durable Retry Control State**：MVPではQueue／History全体の完全永続化は要求しないが、`root_run_id`をキーとする最小durable stateを必須とする。最低保持項目：
     - `root_run_id`（権威キー）／`parent_run_id`（必要に応じて）
     - attempt count
     - lifecycle phase（`READY/ELIGIBLE`／`CLAIMED`／`EXECUTION_STARTED`／`TERMINAL`）
     - terminal disposition
     - next eligible condition／time
     - 必要な最終更新情報（updated_at等）
     契約：
     - terminal dispositionはQueue除去／再走査より先にdurableに確定する
     - Runtime再起動時はこのdurable stateを読み込んでから、Execution HistoryのFAILED/TIMEOUTを再評価する
     - Retry eligibility／attempt上限についてはこのdurable stateを権威（authoritative source）とする
     - 過去FAILEDが再起動後にattempt=1へ戻ることを禁止する（lineage契約と整合）
- **Out of Scope**：Queue/History全体の完全永続化（post-MVP可）。WordPress側の重複防止（6.32のスコープ）。
- **Dependency**：6.30（canonical retryable recordとFAILED/TIMEOUT candidate検出契約が存在すること）。
- **Completion Criteria**：
  - abandoned RUNNING→TIMEOUT candidateが、実際にRetry Eligibility判定へ引き渡されることをE2Eで確認（6.30からの実引渡し）
  - retry派生runが元runと同じ`root_run_id`を継承し、attempt数・eligibility判定が`root_run_id`単位で正しく積算されることをE2Eで確認
  - Runtime再起動後、Execution History再走査時に既存lineageへ再接続され、新規lineageとして扱われないことをE2Eで確認
  - NewsAgent interval guard等により実行不能と判定されたRetry対象が、success扱いされずattemptも消費せずQueueから除去されないことをE2Eで確認
  - hot retry（同一項目の即時連続再試行）が発生しないことをE2Eで確認（next eligible condition/timeの検証）
  - **Attempt lifecycle crash boundary**について、以下3ケースを独立したE2Eとして検証する：
    - A. `CLAIMED`後・`EXECUTION_STARTED`前に停止した場合、attemptが非消費のまま安全に再評価されること
    - B. `EXECUTION_STARTED`直後に停止した場合、attemptが消費済みとして扱われること
    - C. 正常なretry executionが完了し、main.pyが実際に再起動・再実行されたことが証明されること。**このシナリオでは`READY/ELIGIBLE → CLAIMED → EXECUTION_STARTED → TERMINAL`の遷移履歴が記録され、`CLAIMED`が省略されていないことも合わせて確認する（R4-S1対応）**
  - Runtime再起動後、durable Retry Control Stateからattempt count／lifecycle phase／terminal dispositionが正しく復元されることをE2Eで確認
  - 対象E2E・failure-path E2E（silent success禁止・hot retry防止・lineage継承・crash boundary A/B/C・再起動後state復元の各ケース）がPASSすること
  - Formal Regressionで既存機能に回帰がないこと（共通要件に従う）
  - 未着手下流（Observability Runtime配線・Scheduler等）がZero-Diffのまま維持されること
- **Activation**：本Release完了時点では、lineage／eligibility／attempt安全性は利用可能になるが、side-effectingなworkflow（WordPress投稿等を伴うworkflow）のautomatic RetryはまだOFFのまま（Staged Activation Gates章参照）。

### 6.32 — Side-Effect Fail-Closed & Human Review Safety

- **Goal**：partial success・外部副作用発生済み等、安全にworkflow全体をRetryできないrunを、write-aheadのfail-closed契約とdurableなHuman Review terminal dispositionにより安全に扱う。
- **In Scope**：
  1. partial success、あるいは既に外部副作用（WordPress下書き作成・media upload等）が発生済みのrunを、無条件にworkflow全体自動Retry対象にしない方針の実装（MVP基本方針）
  2. **外部副作用のwrite-ahead fail-closed契約（M3-4対応）**：
     - WordPress draft作成・media upload等、外部副作用を**実行する前に**、「副作用が発生する可能性がある／進行中（`side effect possible / in progress`相当）」の状態をdurableに記録する
     - 副作用の結果が安全に確定できた場合のみ、当該状態を解決（成功確定 or 未発生確定）する
     - `possible / in-progress / unknown`のまま停止・timeout・Runtime再起動が発生したrunは、**fail-closedで`HUMAN_REVIEW_REQUIRED`相当へ移行**する（自動的にRetryへ進めない）
  3. 安全な再処理経路（重複を起こさずに未完了分のみを補完できる手段）が存在しない場合、当該runを**durableな`HUMAN_REVIEW_REQUIRED`相当のterminal disposition**として記録する（6.31のAttempt lifecycle `TERMINAL`の一種として扱う）。最低契約：
     - 再起動後も保持される（6.31のDurable Retry Control Stateの一部として記録する）
     - Retry Trigger／Retry Eligibility判定が、`HUMAN_REVIEW_REQUIRED`状態のrunを必ず除外する
     - `root_run_id`／理由（reason）／side-effect context／timestampが観測可能な形で記録される
     - 自動解除は禁止する（明示的なHuman actionがない限り、自動Retry対象へ戻らない）
- **Out of Scope**：完全なidempotency key・既存draft照合等の高度な冪等性実装（post-MVP可）。`HUMAN_REVIEW_REQUIRED`の解除・対応を行うUIや高度な人手workflow（post-MVP可。本Releaseでは、write-ahead fail-closed契約とdurableな状態記録・Retry遮断契約までを扱う）。
- **Dependency**：6.31（`root_run_id`ベースのDurable Retry Control State・Attempt lifecycleが存在すること）。
- **Completion Criteria**：
  - partial success／既に副作用が発生したrunに対する自動Retryが、重複下書き・重複media uploadを起こさないことをE2Eで確認
  - **クラッシュ窓のfailure-path E2E**：外部副作用のPOST／upload成功後、durable結果確定前にプロセスが停止したケースで、当該runがfail-closedで`HUMAN_REVIEW_REQUIRED`へ移行し、自動Retryされないことを確認する（「外部POST成功後、durable結果確定前に停止→自動Retry→重複副作用」の禁止を実証する）
  - 安全な再処理経路がないrunが`HUMAN_REVIEW_REQUIRED`として記録され、Retry Trigger／Eligibilityから確実に除外されることをE2Eで確認
  - Runtime再起動後も`HUMAN_REVIEW_REQUIRED`状態が保持され、自動Retry対象へ戻らないことをE2Eで確認
  - 明示的なHuman actionなしに`HUMAN_REVIEW_REQUIRED`が自動解除されないことをE2Eで確認
  - 対象E2E・failure-path E2E（partial success自動Retry除外ケース・副作用クラッシュ窓ケース・再起動後保持ケース）がPASSすること
  - Formal Regressionで既存機能に回帰がないこと（共通要件に従う）
  - 未着手下流（Observability Runtime配線・Scheduler等）がZero-Diffのまま維持されること
  - 外部副作用（WordPress REST API呼び出し）の安全性が確認されること（重複POSTが発生しないこと）
- **Activation（Automatic Retry Activation Gate）**：本Release完了により、以下がすべてE2EでPASSした場合に限り、side-effectingなproduction workflowの自動Retryを有効化してよい（Staged Activation Gates章参照）：
  - lineage安全性（6.31）
  - attempt crash safety（6.31）
  - durable Human Review（6.32）
  - side-effect fail-closed契約（6.32）
  この有効化はHuman Gate対象とし、Release完了それ自体が自動的な本番有効化を意味しない。

### 6.33 — Retry Observability Runtime Integration

- **Goal**：`RetryObservabilityPipeline`（v6.29.0）をRetry Runtimeへ実配線し、`scripts/show_retry_notification.py`の重複ロジックを解消する。
- **In Scope**：
  - Runtime側での`RetryRuntimeLogRecord`調達順序の明確化
  - `RetryObservabilityPipeline.evaluate()`の呼出順序・failure policyの明確化
  - `RetryObservabilityReport`の観測先（コンソール出力／ログ記録等）の明確化
  - CLI（`scripts/show_retry_notification.py`）側の委譲統一
- **Out of Scope**：外部Sender（Slack等）への実送信。
- **Dependency**：6.32（Retry Runtimeが安全に実行され、実際にログを生成していることが前提）。
- **Completion Criteria**：
  - Retry Runtime稼働中に`RetryObservabilityReport`が生成され、CLIとFacadeの出力が一致すること（Parity維持）
  - 対象E2E・failure-path E2E（評価失敗時の方針含む）がPASSすること
  - Formal Regressionで既存機能に回帰がないこと（共通要件に従う）
  - 未着手下流（Scheduler等）がZero-Diffのまま維持されること

### 6.34 — Scheduler Driver & Duplicate Dispatch Safety

- **Goal**：`SchedulerEngine`のpure性を維持したまま、MVP本番workflowを定期実行できる、再起動・多重driverに対しても安全な駆動方式を確立する。
- **In Scope**：
  - `scripts/run_retry_runtime.py --loop`と同系統のWorkflow Engine用loop driverをMVP第一案として実装（`SchedulerEngine`自体には状態やloop制御を持たせない）
  - **production schedule sourceの一元化**：`scripts/run_workflow_engine.py`のhard-coded demo jobをそのままproduction schedule sourceに転用しない。authoritativeなschedule source（Job定義の唯一の供給元）を1つ定義する
  - **stable event identity**：`(job_id, scheduled occurrence)`等から一意に定まる、再起動をまたいでも安定したevent識別子を定義する
  - **durable dispatch ledger**：event識別子ごとのdispatch記録を永続化し、Runtime再起動後も同一eventの再dispatchを防ぐ
  - **fail-closed dispatch契約**：dispatch実行前にclaim（占有記録）をdurableに行い、claim失敗時はdispatchしない（fail-closed。claim前にdispatchしてから記録する順序は禁止）
  - **claim-dispatch間のcrash safety契約（S3-1対応）**：durable claimが確定した後、実際のdispatchが行われる前にdriverが停止した場合、MVPでは自動的に再dispatchして重複リスクを取らない。当該occurrenceを`RECOVERY_REQUIRED`相当としてdurableに識別し、Runtime再起動後も同一occurrenceを自動的に二重dispatchしない。観測可能な形で記録する（recovery自体の自動化はpost-MVP可）
  - **single-active-driver制約**：MVPでは同時に有効なdriverプロセスを1つに制限する正式制約とする。複数driver同時起動はfail-closedで拒否する（後発driverがclaimに失敗し、dispatchを行わずに終了する）
  - Scheduler event dispatchの実装
  - production workflow（canonical run）の起動配線
  - Retry Runtimeとのownership／プロセス排他の定義
- **Out of Scope**：Windows Task Scheduler等のOS固有統合（post-MVP）。`RECOVERY_REQUIRED`occurrenceの自動復旧（post-MVP）。
- **Dependency**：6.30〜6.33。
- **Completion Criteria**：
  - loop driverによりScheduler eventからproduction workflowが起動・完走することをE2Eで確認
  - **Runtime再起動後の重複dispatch防止**をE2Eで確認（durable dispatch ledgerが再起動をまたいで同一eventの再dispatchを防ぐこと）
  - **同一分内の複数tick**での重複dispatch防止をE2Eで確認
  - **second driverの同時起動**がfail-closedで拒否され、dispatchが行われないことをE2Eで確認
  - **claim確定後・dispatch前の停止（failure-path）**：durable claim確定後、実dispatch前にdriverが停止したケースで、当該occurrenceが`RECOVERY_REQUIRED`として識別され、Runtime再起動後も自動的に二重dispatchされないことをE2Eで確認
  - Retry RuntimeプロセスとScheduler driverプロセスの同時実行時に競合・二重実行が発生しないことを確認
  - Retry Runtime既存挙動（6.29.0〜6.33のRetry Observability配線含む）がZero-Diffのまま維持されることを確認
  - main.py直接実行経路がZero-Diffのまま維持されることを確認
  - 対象E2E・failure-path E2E（dispatch失敗・起動失敗・claim失敗・claim-dispatch間crashケース）がPASSすること
  - Formal Regressionで既存機能に回帰がないこと（共通要件に従う）
- **Activation**：本Release完了により、Scheduler unattended production activationを許可可能となる（Staged Activation Gates章参照。ここでもHuman Gateを経る）。

### 6.35 — MVP End-to-End Hardening & Validation

- **Goal**：新機能追加を原則行わず、MVP Definition of Doneの達成を独立したシナリオ群でEnd-to-End証明する。
- **In Scope**：End-to-Endの結合検証、Formal Regressionでの最終確認。単一の成功路線ではなく、以下6シナリオを最低限、独立して検証する：
  - **A. normal success → WordPress Draft**：正常系の収集〜記事生成〜WordPress下書き投稿
  - **B. retryable failure → enqueue → actual retry → observability**：失敗検知からRetry実行・main.py実再実行・Observability記録までの一連の流れ
  - **C. partial/side-effect済み failure → Human Review → automatic retryなし**：6.32の`HUMAN_REVIEW_REQUIRED`が自動Retryを確実に遮断すること
  - **D. abandoned RUNNING → TIMEOUT → eligibility判定**：6.30のabandoned RUNNING検出から6.31のRetry Eligibility判定への実引渡し
  - **E. Runtime restart → attempt/terminal state維持・再投入安全**：6.31のDurable Retry Control State（lineage・attempt lifecycle含む）が再起動をまたいで正しく機能すること
  - **F. Scheduler restart/same-minute tick/second driver → duplicate production dispatchなし**：6.34のdurable dispatch ledgerとsingle-active-driver制約の統合検証。**second driverを実際に同時起動し、single-active-driver契約によりfail-closedで拒否されることを含む**（restart・same-minute tickの確認だけでなく、second driver同時起動の実地検証を必須とする。N3-1対応）
- **Out of Scope**：Post-MVP項目全般。新規Foundationの追加。
- **Dependency**：6.30〜6.34。
- **MVP最終検証としてのfailure-path E2E再実行（R4-S2対応）**：以下は各Releaseで新規に定義済みのfailure-path E2Eだが、MVP最終検証として本Releaseで改めて再実行し、A〜Fのシナリオ群と合わせてPASSを確認する：
  - 6.31 crash boundary A（`CLAIMED`後／`EXECUTION_STARTED`前のcrash）
  - 6.31 crash boundary B（`EXECUTION_STARTED`直後のcrash）
  - 6.32 external side-effect成功後／durable結果確定前のcrash
  - 6.34 scheduler claim確定後／dispatch前のcrash
  - 6.34 second-driver fail-closed
- **Completion Criteria**：
  - 上記A〜Fの6シナリオがそれぞれ独立したE2Eとして存在し、全てPASSすること（Fはsecond driver同時起動のE2Eを含む）
  - 上記「MVP最終検証としてのfailure-path E2E再実行」の5項目が、本Release時点でも全てPASSすることを再確認すること
  - MVP Definition of Doneの全条件が、A〜Fのシナリオ群を通じて実Runtime経路で確認できること
  - Formal Regressionで既存機能に回帰がないこと（共通要件に従う）

---

## Staged Activation Gates

MVP到達までの各Releaseは、完了＝本番での自動有効化を意味しない。危険な自動動作（自動Retry・無人Scheduler本番稼働）は、安全契約が積み上がった段階でのみ、都度Human Gateを経て有効化する。

### After 6.30

- canonical workflowの検証は可能
- automatic production RetryはOFF
- unattended Scheduler production dispatchはOFF

### After 6.31

- lineage／eligibility／attempt安全性は利用可能
- side-effectingなworkflowのautomatic RetryはまだOFF

### After 6.32（Automatic Retry Activation Gate）

- lineage安全性・attempt crash safety・durable Human Review・side-effect fail-closed契約のE2EがすべてPASSした場合のみ、side-effectingなproduction workflowの自動Retryを有効化可能

### After 6.34

- Scheduler unattended production activationを許可可能

各activationはHuman Gate対象とし、Release完了＝自動的な本番有効化、とはしない。

### Production Activation Audit Trail（最小監査証跡、R4-N1対応）

上記いずれのactivation（Automatic Retry Activation Gate・Scheduler unattended production activation等）についても、Human Gate承認時に最低限以下を記録する。Release完了それ自体で自動的にactivationされないという既存契約は変更しない：

- approver（承認者）
- approval date/time（承認日時）
- target environment（対象環境）
- activation前設定値
- 根拠となるE2E evidence（対応するCompletion Criteria／Regression証跡への参照）
- activation後設定値

この監査証跡はActivation Gateごとに1回、承認記録として残す。

---

## Regression / Zero-Diff Evidence（共通要件）

6.30〜6.35の各Releaseは、Completion Criteriaの一部として以下を必ず提示する：

- baseline commit（Release着手時点のcommit hash）
- Formal Regression対象inventory（対象ファイル数・一覧）
- PASS／FAIL／SKIP件数とexit code
- 上記の結果証跡（実行ログ・出力の記録）
- 対象E2E／failure-path E2Eの一覧とPASS結果
- scope外Runtime ActionのZero-Diff確認結果

この共通要件は各Releaseの個別Completion Criteria内で「共通要件に従う」として参照される。

---

## Forecast

- 中心：Release 6.35（MVP COMPLETE）
- range：Release 6.34〜6.36

Release番号はForecastであり固定約束ではない（Roadmap Governance章参照）。

---

## Post-MVP

- SNS実投稿
- Analytics／feedback／Agent高度化
- 自動公開（重要度別の公開制御）
- 高度な通知制御（Suppression／Deduplication／Rate Limit）
- 閾値の外部設定化
- Windows Task Scheduler統合
- RetryQueue／RetryHistoryの完全永続化
- `duplicate_filter`の実行間・再試行間対応への拡張
- WordPress／Media Uploadの本格的な冪等性実装（既存draft照合・idempotency key等）
- 永続化された履歴に基づく高度なattempt上限管理
- `HUMAN_REVIEW_REQUIRED`の解除・対応を行うUIおよび高度な人手workflow
- `RECOVERY_REQUIRED`occurrenceの自動復旧

---

## Roadmap Governance

- Release番号はForecastであり固定約束ではない。
- MVP COMPLETEはRelease番号ではなく、MVP Definition of Doneの達成で判定する。
- Architecture調査で新たな依存関係・安全要件が判明した場合、理由を記録した上でRoadmapを更新してよい。更新の際は、最低限以下を含む短いchange recordを残す：
  - date（更新日）
  - reason（更新理由）
  - affected releases（影響を受けるRelease）
  - human approval status（人間承認の有無・状態）
- MVP Definition of Done自体の変更は、本原則の対象外とし、別途Human承認を要する。
- MVP Definition of Doneの達成に不要な新規Foundationの追加は、原則post-MVPへ送る。
- Production activation（Staged Activation Gates章の各Gate）については、Roadmap更新のchange recordとは別に、「Production Activation Audit Trail」（approver／approval date-time／target environment／activation前設定値／根拠E2E evidence／activation後設定値）をGateごとに記録する。

### Change Record

| date | reason | affected releases | human approval status |
|---|---|---|---|
| 2026-08-19 | v1.0起草：Release 6.30着手前のMVP Roadmap正式化 | 6.30〜6.35 | 承認待ち（Codex Review round 1 NEEDS_REVISION） |
| 2026-08-19 | v1.1改訂：Codex Review round 1 M-1〜M-7への対応、Architecture Reconciliationの事実反映 | 6.30〜6.35 | 承認待ち（Codex Review round 2 NEEDS_REVISION） |
| 2026-08-19 | v1.2改訂：Codex Review round 2 A-1〜A-6への対応、安全契約の確定 | 6.30〜6.35 | 承認待ち（Codex Review round 3 NEEDS_REVISION） |
| 2026-08-19 | v1.3改訂：Codex Review round 3 M3-1〜M3-4・N3-1・N3-2・S3-1への対応（6.30/6.31境界修正、retry lineage契約、attempt lifecycle crash boundary、外部副作用fail-closed契約、Staged Activation Gates新設） | 6.30〜6.35 | 正式化前（Codex Review round 4 APPROVED_WITH_SUGGESTIONS） |
| 2026-08-19 | v1.3正式化：Codex Review round 4 APPROVED_WITH_SUGGESTIONS（Blocking 0／Major 0）を受け正式採用。Minor R4-N1（Production Activation Audit Trail新設）、Suggestion R4-S1（通常retry lifecycleの必須遷移明記）・R4-S2（6.35でのfailure-path E2E再実行明記）を反映 | 6.30〜6.35 | 正式採用（Codex Review round 4 APPROVED_WITH_SUGGESTIONS、以降Codexレビューなし） |

---

## MVP運用原則

MVP COMPLETEまでは「MVP DoD達成に必要か」をRelease scope判断基準とし、不要なFoundation追加は原則post-MVPへ送る。
