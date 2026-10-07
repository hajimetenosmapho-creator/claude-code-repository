# MVP Completion Roadmap（v1.6）

Release 6.30開始前に、MVP到達までのRelease計画を正式化したドキュメント。個々のReleaseの詳細設計は各`docs/design/*.md`で別途行い、本書はスコープ全体の地図として維持する。

**v1.3（正式版）**：v1.0はCodex Architecture Review（round 1）で`NEEDS_REVISION`（Major M-1〜M-7）、v1.1はArchitecture Reconciliationを踏まえた改訂だったがCodex Review（round 2）で再度`NEEDS_REVISION`（Major A-1〜A-6）、v1.2はA-1〜A-6への対応版だったがCodex Review（round 3）で再度`NEEDS_REVISION`（Major M3-1〜M3-4、Minor N3-1/N3-2、Suggestion S3-1）と判定された。v1.3改訂時点では、M3-1〜M3-4・N3-1・N3-2・S3-1を反映し、①6.30/6.31間の循環依存解消、②retry lineage契約の追加、③attempt lifecycleのcrash boundary契約、④外部副作用のfail-closed契約、⑤段階的activation gate、を確定したもの。Codex Review（round 4）で`APPROVED_WITH_SUGGESTIONS`（Blocking 0／Major 0）となり、Minor（R4-N1）・Suggestion（R4-S1／R4-S2）を反映のうえ正式版として採用した。

**v1.4**：Release 6.35でMVP COMPLETEに到達した後、最初のPost-MVP Releaseとして6.36の個別節を新設した改訂（Roadmap Governance章の手続きに従うchange record付き）。MVP Definition of Done（Release 6.30〜6.35が定める内容）は本改訂で一切変更しない。Release 6.35のMVP COMPLETEという到達点も変更しない。6.36のArchitecture Design自体はCodex `codex-readonly-review`独立reviewを5ラウンド実施して`APPROVED`（Blocking 0／Major 0）に収束し、Human Gateで承認済み（詳細は本書末尾のChange Record・6.36節を参照）。

**v1.5**：Post-MVP 2件目のReleaseとして6.37の個別節を新設した改訂。6.37はFast Track Release（`docs/development_workflow.md` 7章のFast Track候補条件8項目をすべて満たすことを実装着手前に確認）であり、Architecture Design文書の代わりにDesign Summary（`docs/design/release_claim_diagnostic_correctness_fix.md`）を作成した。MVP Definition of Done・Release 6.35のMVP COMPLETEという到達点はいずれも本改訂で変更しない（詳細は本書末尾のChange Record・6.37節を参照）。

**v1.6**：Post-MVP 3件目のRelease候補として6.38「WordPress Server-Side Media Idempotency Foundation」の個別節を新設した改訂（Roadmap Governance章の手続きに従うchange record付き）。6.38は**Architecture Re-review APPROVED（Review #26。runtime項目は未検証）**であり、Architecture Design（`docs/design/wordpress_server_side_media_idempotency_foundation.md`）はAmendment A1適用後のCodex High独立レビュー（Review #9、NOT APPROVED）以降、各Amendment（A1〜A12）に対する独立再レビュー（Review #10〜#20）がいずれもNOT APPROVEDとなり、A13に対するReview #21はAPPROVEDとなったが、その後のImplementation Start Validation（2026-10-06）で承認済みArchitectureの前提誤りが判明し、Amendment A14を適用してArchitecture statusをRe-review Pendingへ戻した。A14に対するReview #22・A15に対するReview #23・A16に対するReview #24・A17に対するReview #25はいずれもNOT APPROVEDとなり、Amendment A15・A16・A17・A18がそれぞれの指摘に対応した。A18に対するReview #26は**APPROVED**（Blocking 0／Major 0／Minor 2。設計文書の内部整合性とsource上の事実の判定で、runtime項目は未検証。Minor 2件は文書の同期のみで対応）であり、実装未着手である（履歴の詳細は設計書19章・24章を参照）。MVP Definition of Done・Release 6.35のMVP COMPLETEという到達点は本改訂で変更・再オープンしない（詳細は本書末尾のChange Record・6.38節を参照）。

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

### Governance Exception — Canonical Admission Failure（2026-08-20 Human Gate承認）

上記「1 production invocation = 1 canonical retryable record」に対する明示的例外。Release 6.30 Architecture Design（Round 10、Codex read-only review `APPROVED`：Blocking 0／Major 0／Minor 0／Suggestions 0）の一部として確定し、人間が承認した。

`CanonicalAdmissionFailure`（`EXECUTION_HISTORY_DISABLED`・`START_RUN_ACK_FAILED`のいずれの理由でも発生しうる）では、production invocationが開始されたにもかかわらずdurable canonical recordが存在しない場合がある。結果：6.31 History scannerから不可視・Retry Eligibility対象にならない・NEWS/external side effect開始前のため重複副作用は発生しない・ただし可観測性は失われる。これは実害なしではなく、**意図的に受容するoperational gap**である。atomic admission write中、ackが返る前に親プロセスが中断した場合も同種の状態になり得るため本Exceptionの対象に含める。fallback durable admission markerやadmission failure alertはpost-MVP候補とする。

詳細契約は `docs/design/production_canonical_run_outcome_contract_foundation.md`（23章）を参照。

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
- **Architecture Design Status（2026-08-20追記）**：Architecture Revision Round 10がCodex read-only review（codex-plugin-cc、reasoning effort High）で`APPROVED`（Blocking 0／Major 0／Minor 0／Suggestions 0）となり、Human Gateで承認された（Governance Exceptionを含む）。確定した設計内容は`docs/design/production_canonical_run_outcome_contract_foundation.md`を参照。
- **Implementation Status（2026-08-22追記）**：実装完了。Codex Final Code Review `APPROVED`（Blocking 0／Major 0／Minor 0／Suggestion 0）。Formal Regression：正式Inventory33ファイル（v1.11.0＋v5.9.0＋v6.0.0〜v6.30.0）、5512/5512 PASS、FAIL 0／SKIP 0、全ファイルexit code 0。Runtime Verification：全11 scenario PASS、Original Project 911ファイルZero-Diff、Disposable Copy allow-list外diff 0、外部I/Oなしを確認。上記Completion Criteriaは全て満たされたことを実測証跡で確認済み。**commit/pushは未実施**（Codex Final Release Review前のHuman Gate待ち）。詳細は`docs/CHANGELOG.md`「[v6.30.0]」を参照。

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
- **Architecture Design Status（2026-08-31追記）**：Architecture Design（Round 8〜11+Cleanup）がCodex独立adversarial review（実コードとの突き合わせあり）を経てRound 11で`Blocking/Major指摘 0件`（Pass with minor corrections）に収束し、Round 11 CleanupでMinor/Suggestion指摘を反映した。§26 Architecture Gate ChecklistのHuman Gate必須15項目を2026-08-31にユーザーが明示的に承認し、Architecture Design Statusを`Approved`へ更新した。確定した設計内容は`docs/design/retry_lineage_eligibility_durable_attempt_state.md`を参照。
- **Implementation Status（2026-08-31追記）**：実装完了・commit済み（baseline `a4d22e34a60ae02f1231af89434f4ac8ef07e860`）。実装完了後の独立Code Review（実コードレビュー）でBlocking 2件・Major 2件を検出し、限定的な設計整合修正（4-phase state machine・locking契約・attempt accounting・admission gate分離・6.31 scope境界はいずれも無変更）として反映、追加のHuman Gate 4件を2026-08-31にユーザーが承認した。Final Release Review：**APPROVED**（Blocking 0／Major 0）。新規E2E（`test_e2e_v6_31_0_retry_lineage_eligibility_durable_attempt_state.py`）は**151/151 PASS**。Formal Regression：正式Inventory34ファイル（v1.11.0＋v5.9.0＋v6.0.0〜v6.31.0）、**5644/5644 PASS、FAIL 0／SKIP 0、全ファイルexit code 0**。上記Completion Criteriaは全て満たされたことを確認済み。詳細は`docs/CHANGELOG.md`「[v6.31.0]」を参照。

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
- **Completion Criteria**（★=実証済み。根拠は`docs/design/side_effect_fail_closed_human_review_safety_amendment_protected_operation_manifest.md` §18 Implementation Verification Record（§34）・Final Independent Codex Review & Blocking Remediation（§35）を参照）：
  - ★ partial success／既に副作用が発生したrunに対する自動Retryが、重複下書き・重複media uploadを起こさないことをE2Eで確認（`test_e2e_v6_32_21_execution_mode_propagation_call_site_ac.py`のC-A/C-Cシナリオで直接証明）
  - ★ **クラッシュ窓のfailure-path E2E**：外部副作用のPOST／upload成功後、durable結果確定前にプロセスが停止したケースで、当該runがfail-closedで`HUMAN_REVIEW_REQUIRED`へ移行し、自動Retryされないことを確認する（§18 test#5〜#9・test#22等で直接証明。「外部POST成功後、durable結果確定前に停止→自動Retry→重複副作用」の禁止を実証済み）
  - ★ 安全な再処理経路がないrunが`HUMAN_REVIEW_REQUIRED`として記録され、Retry Trigger／Eligibilityから確実に除外されることをE2Eで確認（§18各testの`opened_count=0`検証で直接証明）
  - ★ Runtime再起動後も`HUMAN_REVIEW_REQUIRED`状態が保持され、自動Retry対象へ戻らないことをE2Eで確認（restart経路の§18 testで直接証明）
  - 明示的なHuman actionなしに`HUMAN_REVIEW_REQUIRED`が自動解除されないことをE2Eで確認（`tests/test_e2e_v6_32_1_hrr_lifecycle.py`の既存範囲、本チェックポイントでの追加検証は未実施）
  - ★ 対象E2E・failure-path E2E（partial success自動Retry除外ケース・副作用クラッシュ窓ケース・再起動後保持ケース）がPASSすること（v6.32系列Full Suite 39ファイル、1270/1270 PASS）
  - ★ Formal Regressionで既存機能に回帰がないこと（正式Inventory34ファイル、5671/5671 PASS、FAIL 0）
  - ★ 未着手下流（Observability Runtime配線・Scheduler等）がZero-Diffのまま維持されること（本Releaseの変更対象は`src/retry_observability_pipeline/`・`src/scheduler/`を含まないことをgit diffで確認済み）
  - ★ 外部副作用（WordPress REST API呼び出し）の安全性が確認されること（重複POSTが発生しないこと、`test_e2e_v6_32_21`のC-A7で直接証明）
- **Activation（Automatic Retry Activation Gate）**：本Release完了により、以下がすべてE2EでPASSした場合に限り、side-effectingなproduction workflowの自動Retryを有効化してよい（Staged Activation Gates章参照）：
  - lineage安全性（6.31）
  - attempt crash safety（6.31）
  - durable Human Review（6.32）
  - side-effect fail-closed契約（6.32）
  この有効化はHuman Gate対象とし、Release完了それ自体が自動的な本番有効化を意味しない。**Release 6.32完了時点でもこのHuman Gateは別途独立して要求されており、本Releaseの完了それ自体が自動有効化を意味しない点は変わらない。**

**Release 6.32 完了記録**：Architecture Amendment（Protected Operation Manifest）はCodex Round 10で`APPROVED`（Blocking 0／Major 0）。§18 Implementation Matrix（全25項目）はproduction wiring実チェーンでの直接証拠に基づき**25/25 PASS（PARTIAL 0・MISSING 0）**。実装完了後のFinal Independent Codex Reviewは1回目`CHANGES REQUIRED`（Blocking 2）を検出し、HUMAN GATE承認のもと限定修正（既存fail-closed semanticsのproduction反映）を実施、2回目**APPROVED WITH SUGGESTIONS**（Blocking 0／Major 0／Minor 0／Suggestion 1 non-blocking、`release_claim()`戻り値未確認によるdiagnostic gap——Release safety blockerではないためfuture improvementとして記録のみ）に収束した。v6.32系列Full Suite（39ファイル、1270/1270 PASS）・正式Formal Regression（34ファイル、5671/5671 PASS）とも完了時点のWorking Treeで完全PASSを確認した。`generic non-HRR automatic retry redispatch`等、Amendment・Approved Architectureが明示的にOut of Scopeとした事項は本Releaseで解決済みではない。

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
- **Architecture Design Status（2026-09-16追記）**：Architecture Design（`docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md`）がCodex `codex-readonly-review`による独立read-only reviewを5ラウンド実施して`APPROVED`（Blocking 0／Major 0）に収束した。26章のArchitecture Gate Checklist（9項目）をユーザーが個別にACCEPT/確認済み（Gate 9のManual Recovery専用CLIは本Releaseから除外することを確認）。R2/R3/R4/R6/R9はArchitecture記載どおりAccepted Riskとして扱う。
- **Implementation Status（2026-09-16追記）**：実装完了。Independent Code Review（同workflow、read-only、`src/scheduler_dispatch_ledger/scheduler_dispatch_ledger_store.py`を中心に6ラウンド実施）は**APPROVED**（Blocking 0／Major 0／Minor 1 cosmetic）。新規E2E（`test_e2e_v6_34_0_scheduler_driver_duplicate_dispatch_safety_foundation.py`）は**55/55 PASS**。Invariant #35 closure oracle（`test_e2e_v6_32_7_invariant_35_closure_oracle.py`）改訂後は54/54 PASS（新設`scripts/run_scheduler_driver.py`の実測sink到達性が宣言値と一致することをAST closure engineで確認）。Formal Regression：正式Inventory37ファイル実測、32/37ファイルexit code 0。残る5ファイルのFAILはいずれも新設`scripts/run_scheduler_driver.py`が本Implementation Phase完了時点でuncommittedであることのみに起因する既知差分（`docs/CHANGELOG.md` `[KI-33]`、`[KI-3]`系列と同型、commit後に自然解消見込み）。**commit/pushは未実施**（Human Gate待ち、ユーザー指示によりImplementation Phase自体ではcommitを行わない）。詳細は`docs/CHANGELOG.md`「[v6.34.0]」を参照。

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

### 6.36 — Manual Recovery Diagnostic CLI Foundation（v1.4新設、最初のPost-MVP Release）

- **位置づけ**：Release 6.35でMVP COMPLETEに到達した後の、最初のPost-MVP Release。MVP Definition of Doneは変更・再オープンしない。
- **Goal**：`SchedulerDispatchLedger.list_recovery_required()`（6.34で実装済み、read-only診断API）を消費する、人間が安全に使えるread-only診断CLIを提供し、`RECOVERY_REQUIRED`occurrenceの確認手段が存在しないというgap（6.34 Architecture Gate Checklist item 9・6.35 Out of Scopeで明示的に除外されてきた既知のgap）を、既存contractを一切変更せずに埋める。
- **In Scope**：
  - `scripts/show_scheduler_recovery.py` のread-only CLI
  - `SchedulerDispatchLedger.list_recovery_required()`によるRECOVERY_REQUIRED一覧取得
  - `event_identity`/`job_id`によるread-only filter（`list_recovery_required()`結果に対するin-memory filter、`peek()`は使用しない）
  - `job_id` / `occurrence_minute` / `claimed_at` / `updated_at` 等の診断表示
  - Execution History確認手順の案内（既存`scripts/show_execution_history.py`）・必要時の`scripts/run_workflow_engine.py --job-id`による手動補完手順の案内（いずれも案内のみ、CLIからの自動実行はしない）
  - store異常時のfail-closed診断（`JsonSchedulerDispatchLedgerStore`をinstantiateしない、read-only store adapterによる`mkdir`副作用の構造的排除を含む）
- **Out of Scope**：RECOVERY_REQUIRED自動復旧・ledgerへの新規write API・re-claim/re-dispatch・HUMAN_REVIEW_REQUIRED UI・Windows Task Scheduler・WordPress/Media Upload idempotency・RetryQueue/RetryHistory完全永続化・production activation・`release_claim()` Suggestion（`src/retry_engine/retry_executor.py`、独立Fast Track候補のまま維持）・Dashboard/notification。
- **Dependency**：6.34（`SchedulerDispatchLedger.list_recovery_required()`の提供元）。
- **Completion Criteria**：
  - CLIが`RECOVERY_REQUIRED`のentry一覧・filterを正しく処理することをtargeted E2Eで確認
  - CLIが`JsonSchedulerDispatchLedgerStore`を一切instantiateせず、`state/`配下へ新規ディレクトリ・ファイル・lockを一切作成しないことを確認
  - CLIが`claim()`/`confirm()`/`reconcile_stale_claims()`/`store.save()`のいずれも呼ばないことを確認
  - filename/event_identity cross-checkが維持され、read不能・破損状態を正常な空結果へ丸めないことを確認
  - targeted E2E・Architecture/Zero-Diff guards・Formal Regressionで既存機能に回帰がないこと（共通要件に従う）
  - Independent Codex High code reviewが`APPROVED`（Blocking 0／Major 0）に到達すること
- **Architecture Design Status（2026-09-21追記）**：Architecture Design（`docs/design/manual_recovery_diagnostic_cli_foundation.md`）がCodex `codex-readonly-review`（Codex High）による独立read-only reviewを5ラウンド実施して`APPROVED`（Blocking 0／Major 0）に収束した。Architecture Gate Checklist（8項目）をユーザーが個別にACCEPT済み（Human Gate承認 2026-09-21）。private helper（`_sanitize_event_identity()`/`_entry_from_dict()`、`src/scheduler_dispatch_ledger/scheduler_dispatch_ledger_store.py`）の跨モジュールimportを、本Release限定のArchitecture exceptionとして承認済み（E2Eで依存を固定し、silent breakを防止する）。

### 6.37 — release_claim() Diagnostic Correctness Fix（Fast Track、Post-MVP 2件目）

- **位置づけ**：Release 6.35でMVP COMPLETEに到達した後の、Post-MVP 2件目のRelease（6.36に続く）。MVP Definition of Doneは変更・再オープンしない。
- **分類**：Fast Track Release（`docs/development_workflow.md` 6〜7章）。Architecture Contract Change: NO。
- **Goal**：Release 6.32 Final Review由来の非blocking Suggestion——`RetryExecutor.execute()`が`RetryLineageManager.release_claim()`の戻り値を確認せず、release失敗時（durable store save失敗等）に`RetryResult.reason`が実durable state（CLAIMEDのまま）とずれ得た既存6.31由来のgap——を、既存Retry Lineage / attempt lifecycle / reconciliation契約を一切変更せずに解消する。durable safety改善ではなくdiagnostic correctness改善として扱う。
- **In Scope**：
  - `RetryExecutor.execute()`の`hook_ack_state["acknowledged"] is False`経路で`release_claim()`のbool戻り値を取得し、`RetryResult.reason`へ実際の解放成否を反映する
  - `test_e2e_v6_32_35_admission_failure_durable_save_failure_closure.py`のN7(d)/N8(d)のTEST MIGRATION（意図transplant）
  - success/failure coverageの確認と、不足分（M9b(d)・N7b(d)）の最小targeted test追加
  - Design Summary（`docs/design/release_claim_diagnostic_correctness_fix.md`）・CHANGELOG／本Roadmap／architecture.mdの整合更新
  - targeted validation・関連Architecture Guard・Formal Regression全37ファイル
  - Independent Codex `codex-readonly-review`（Codex High）レビュー
- **Out of Scope**：`release_claim()`本体・authority contract変更、例外再raise側call site（対応するreason文言自体が存在しないため無変更）のロジック/ログ変更、`reconcile_all()`変更、自動修復・自動再claim・自動retry、新state／phase／retry policy、Queue/History persistence、WordPress/Media idempotency、Scheduler関連。
- **Dependency**：6.32（`release_claim()` Suggestion提起元）。
- **Completion Criteria**：
  - targeted test・関連Architecture Guard・Formal Regression（正式Inventory37ファイル）で既存機能に回帰がないこと
  - Independent Codex High code reviewの結果を記録すること
  - `docs/development_workflow.md` 7章のFast Track候補条件8項目をすべて満たすことを実装着手前に確認すること
- **実装結果（2026-09-21追記）**：`src/retry_engine/retry_executor.py`を変更（Zero-Diff対象・変更内容は`docs/CHANGELOG.md` `[v6.37.0]`参照）。targeted test 31/31 PASS（従来29件＋新規2件）。関連Architecture Guard（`test_e2e_v6_3*.py`系列54ファイル）53/54 PASS、唯一のFAILは`test_e2e_v6_33_0`テスト43（commit前のuncommitted状態にのみ起因する既知差分、`docs/CHANGELOG.md` `[KI-36]`参照）。Formal Regression（正式Inventory37ファイル）36/37 exit code 0（同一原因）。

### 6.38 — WordPress Server-Side Media Idempotency Foundation（Post-MVP 3件目候補、Architecture Re-review APPROVED（Review #26））

- **位置づけ**：Release 6.35でMVP COMPLETEに到達した後のPost-MVP候補（6.36・6.37に続く）。MVP Definition of Doneは変更・再オープンしない。本節は**Release候補の登録**であり、実装着手・Release scope確定を意味しない（Release scopeの確定・変更はHuman Gate対象）。
- **分類**：Architecture Design Release（Architecture Contract Change: YES。Fast Track対象外）。**Consumer-less Foundation**。
- **Goal**：WordPress側（PHP plugin `wordpress/gca-media-idempotency/`）に、authoritativeなserver-side idempotency／duplicate suppression境界を作る。v6.32でPython側のwrite-ahead／fail-closed／`HUMAN_REVIEW_REQUIRED`が既に配線済みであり自動retryによる重複は遮断済みのため、解く問題は「manual recovery後を含む、WordPress側のduplicate suppression不足」である。
- **In Scope（設計上の候補）**：
  - WordPress plugin（repoへの配置のみ）、`/wp/v2/media`のroute callback置換によるGCA-taggedリクエストへのat-most-once authorization
  - logical identity契約（`article_identity`＋`media_role`＋`content_revision`＋schema version。image bytes digest・`attempt_ordinal`・`root_run_id`はkeyに使わない）。**stable identity sourceは6.38では実装せず、後続Integration Releaseの必須precondition**（現行Pythonの`ArticleMediaUploadRecord.article_identity`は`as_store_key()`由来のattempt-scopedな値であり、安定identityではない。既存attempt-scoped identityから導出してはならない）
  - claim前／claim後のHTTP・error contract（`gca_claim_state`。診断情報であり、identity未消費の証拠でもretry authorizationでもない）、3接続のAuthoritative Binding（claim確立後は`none`へ戻らない）、closed allowlist（body size上限33,554,432バイトを含め設計時点で確定）、multisiteの実行時fail-closed、`claim_token`仕様（`random_bytes(32)`相当）
  - Claims Tableの`PROCESSING`／`CONFIRMED`状態機械（`CONFIRMED` duplicateは既存mediaをreplay、`PROCESSING` duplicateはfail-closed、stale `PROCESSING`の自動reclaim禁止）
  - Stable Authoritative DB Epoch内に限定した保証と、検出可能なepoch mismatchのfail-closed
  - GCA wire contract、Final Response Finalizer、kill switch、非GCAのZero-Diff
  - テスト設計（L1 static／L2 PHP unit／L3 staging fault matrixの責務分離）
- **Out of Scope**：Python client integration（`WordPressMediaUploader`変更・idempotency metadata送出）・stable article/content identity sourceの定義・実装・永続化（後続Integration Releaseの必須precondition）・`main.py`／Retry／HRR／`side_effect_safety`／`article_media_upload_state`への配線・production deployment・automatic orphan cleanup・DB rollback／restore／lossy failoverをまたぐ完全保証・外部epoch anchor・stale `PROCESSING`の自動reclaim・manual reconciliation tooling・Human Recovery UI・multisite・multi-node ingress・WordPress Unused Media Cleanup（DI-7）。
- **Dependency**：6.32（write-ahead／HRRの前提、server側状態機械とは接続しない）、6.28.0（`article_media_upload_state`、参照のみ）。将来のIntegration Releaseは6.38の完了を前提とする（Integration Release自体は本Roadmapでは未登録）。
- **Completion Criteria（案）**：
  - **最新のArchitecture Design（`docs/design/wordpress_server_side_media_idempotency_foundation.md`の現行版）が、独立Architecture Reviewで`APPROVED`（Blocking 0／Major 0）に到達し、Human Gateでユーザーが個別にACCEPTすること**（特定のAmendment番号には依存しない。Amendmentを重ねた場合は、その時点の最新版が対象）
  - 実装開始前に、設計書18章のImplementation Start Validation Checklistを完了すること（設計書17章の台帳に載る未確認事項のすべて、すなわちS-1と、現時点でのU-1〜U-21の確認とpin（U-22は廃止済みのnon-actionable gapで、active validation inputに含めない。設計書17.6節のReview #24で独立に照合できなかったsource依存の主張も、verifiedではなくvalidation-requiredとして含む）。U-13以降は設計書のAmendmentで追加されたもので、今後追加される場合も台帳が正本。2026-10-06のValidation結果は設計書17.5節。**デプロイ先のWordPress version・approved plugin set・PHP／MySQL環境が未確定であり、これらに依存する項目は未確認**）。**このチェックリストは、実装前に確認できるarchitecture・environment・source前提のみ**であり、実装が存在して初めて確認できる適合検証（identity contractのL1 golden-vector実装適合等）は含まない。それらは設計書20章の実装フェーズgate（Completion Criteria）で扱う
  - **設計書15章でmandatoryと定義された全validation scenario**（現行版ではT-01〜T-38。claim後Core非success正規化、Authoritative Binding、multisite fail-closed、**claim／`CONFIRMED`のcommit後のDB restart durability（T-25）**、`INSERT`結果不確定、`CONFIRMED` duplicateのVerification、body size contract等を含む）を、各シナリオに割り当てられた層（L1 Static／Contract E2E・L2 PHP unit・L3 Staging fault matrix）で完了し、evidenceが得られること。シナリオの件数・範囲は設計書が正本であり、本Roadmapは固定の件数を定めない。**PHP／MySQL／WordPress stagingはローカルに存在しないため、L2／L3は人手環境のevidenceに依存する。得られない場合は完了を主張せず「Foundation実装済み・実環境検証待ち」と限定して宣言する**
  - Python側（`src/`・`main.py`・`scripts/`）のZero-Diff、Formal Regressionで既存機能に回帰がないこと（共通要件に従う）
- **Architecture Design Status（2026-10-07記録）**：**Architecture Re-review APPROVED（Review #26。設計文書の内部整合性とsource上の事実の判定で、runtime項目は未検証）**。旧Draft（2026-09-22）の「APPROVED」はAmendment A1で撤回した。旧Round 1〜13／Codex計8回のレビュー記録はrepo内で再現できないhistorical self-recorded contextであり、承認根拠として扱わない。Amendment A1テキストに対するCodex High独立レビュー（Review #9）は**NOT APPROVED**（Blocking 0／Major 7（M1〜M7）／Minor 1／Suggestion 1）。Amendment A2がその指摘に最小修正で対応した。以降、A2〜A12の各テキストに対する独立再レビュー（Review #10〜#20）はいずれも**NOT APPROVED**であり（Blocking数：2→0→1→0→1→1→1→1→0→0→0）、各レビューの指摘に対して、Amendment A3〜A13が対応した。**A13テキストに対する独立再レビュー（Review #21）は APPROVED**（Blocking／Major／Minor／Suggestion＝0。設計文書の内部整合性の判定）であり、commit `2513ae5`でdocs-only checkpointとして確定し、**Release scopeはユーザーが承認した**。**しかし、その後のImplementation Start Validation（2026-10-06、WordPress 7.1.1 tag sourceのread-only確認）で、承認済みArchitectureの前提誤り（設計書17.5節のU-18・U-2・U-19）が判明し、Architecture Amendment A14が必要となった**。A14を適用し、**Architecture statusをRe-review Pending（Re-review Required）へ戻した**。**A14に対するReview #22はNOT APPROVED**（Blocking 1／Major 3／Minor 2）で、**Amendment A15がその指摘に対応した**。**A15に対するReview #23もNOT APPROVED**（Blocking 1／Major 4／Minor 1）で、**Amendment A16がその指摘に対応した**。**A16に対するReview #24もNOT APPROVED**（Blocking 0／Major 2／Minor 1）で、**Amendment A17（2026-10-07）がその指摘に対応した**。**A17に対するReview #25もNOT APPROVED**（Blocking 0／Major 2／Minor 1。Review #24の3 FindingはCLOSED）で、**Amendment A18（2026-10-07）がその指摘に対応した**。A18に対するReview #26は**APPROVED**（Blocking 0／Major 0／Minor 2。Review #25の3 FindingはCLOSED。Minor 2件は文書の同期のみで対応）。ただしこのAPPROVEDは、設計文書の内部整合性とsource上の事実への照合の判定であり、Implementation Start Validationのruntime項目（デプロイ先version・approved plugin topology・PHP／SAPI・L2／L3等）は未検証のまま。 Production code・testsは未着手で、**実装は開始しない**（各指摘と対応の詳細、契約の内容は設計書19章・24章・12章が正本であり、本Roadmapは再記述しない）。
- **既知の未解決事項**：再試行をまたいで安定な`article_identity`／`content_revision`の供給元が現行Pythonに存在しない点（Integration Releaseの必須precondition、設計書7.7節）、`PROCESSING`のmanual reconciliation手段の不在、L2／L3実行環境の確保、`tests/zero_diff_guard_registry.py`の`RELEASE_ORDER`が`v6.36.0`止まりである点の整理（実装フェーズのHuman Gateで決定。詳細は設計書26章）。

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
| 2026-08-20 | Release 6.30 Architecture Design（Architecture Revision Round 8〜10）がCodex read-only review（codex-plugin-cc、reasoning effort High）を経てRound 10で`APPROVED`（Blocking 0／Major 0／Minor 0／Suggestions 0）となった。Canonical Admission FailureのGovernance Exception（「Architecture Reconciliation」章）を含めHuman Gateで承認。設計内容を`docs/design/production_canonical_run_outcome_contract_foundation.md`へ保存。本行はRoadmap本文（Release境界・DoD・Completion Criteria）の変更を伴わないため、文書バージョンはv1.3のまま据え置く | 6.30（本体）、6.31（Governance Exceptionを前提として参照） | 承認済み（Human Gate承認 2026-08-20。実装はまだ未着手） |
| 2026-08-22 | Release 6.30 実装完了。Codex Final Code Review `APPROVED`（Blocking 0／Major 0／Minor 0／Suggestion 0）。Formal Regression：正式Inventory33ファイル、5512/5512 PASS、FAIL 0／SKIP 0。Runtime Verification：全11 scenario PASS、Original Project 911ファイルZero-Diff。本行もRoadmap本文の変更を伴わないため、文書バージョンはv1.3のまま据え置く | 6.30（本体） | 実装・検証完了（**commit/push未実施、Codex Final Release Review前のHuman Gate待ち**） |
| 2026-08-31 | Release 6.31 Architecture Design（Round 8〜11+Cleanup）がCodex独立adversarial reviewを経てRound 11で`Blocking/Major指摘 0件`に収束した。§26 Architecture Gate Checklist Human Gate必須15項目をHuman Gateで承認（Architecture Design Status: Approved）。設計内容を`docs/design/retry_lineage_eligibility_durable_attempt_state.md`へ保存。本行はRoadmap本文（Release境界・DoD・Completion Criteria）の変更を伴わないため、文書バージョンはv1.3のまま据え置く | 6.31（本体） | 承認済み（Human Gate承認 2026-08-31） |
| 2026-08-31 | Release 6.31 実装完了・commit済み（baseline `a4d22e34a60ae02f1231af89434f4ac8ef07e860`）。実装後の独立Code ReviewでBlocking 2件・Major 2件を検出し限定的設計整合修正として反映、追加Human Gate 4件を承認。Final Release Review `APPROVED`（Blocking 0／Major 0）。新規E2E 151/151 PASS。Formal Regression：正式Inventory34ファイル、5644/5644 PASS、FAIL 0／SKIP 0、全ファイルexit code 0。本行もRoadmap本文の変更を伴わないため、文書バージョンはv1.3のまま据え置く | 6.31（本体） | 実装・検証完了・commit済み |
| 2026-09-16 | Release 6.34 Architecture Design（`docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md`）がCodex `codex-readonly-review`独立read-only reviewを5ラウンド実施して`APPROVED`（Blocking 0／Major 0）に収束した。§26 Architecture Gate Checklist（9項目）をユーザーが個別にACCEPT（Gate 9のManual Recovery専用CLIは本Releaseから除外）。本行はRoadmap本文の変更を伴わないため、文書バージョンはv1.3のまま据え置く | 6.34（本体） | 承認済み（Human Gate承認 2026-09-16） |
| 2026-09-16 | Release 6.34 実装完了。Independent Code Review（`src/scheduler_dispatch_ledger/scheduler_dispatch_ledger_store.py`を中心に6ラウンド）は`APPROVED`（Blocking 0／Major 0／Minor 1 cosmetic）。新規E2E 55/55 PASS。Invariant #35 closure oracle改訂後54/54 PASS。Formal Regression：正式Inventory37ファイル実測、32/37ファイルexit code 0（残る5ファイルは新設`scripts/run_scheduler_driver.py`のuncommitted状態にのみ起因する既知差分、`docs/CHANGELOG.md` `[KI-33]`参照、commit後に自然解消見込み）。本行もRoadmap本文の変更を伴わないため、文書バージョンはv1.3のまま据え置く | 6.34（本体） | 実装・検証完了（**commit/push未実施、Human Gate待ち**） |
| 2026-09-21 | v1.4改訂：Release 6.35でMVP COMPLETEに到達した後、最初のPost-MVP Releaseとして6.36「Manual Recovery Diagnostic CLI Foundation」の個別節を新設した（本行がその変更本体）。Architecture Design（`docs/design/manual_recovery_diagnostic_cli_foundation.md`）はCodex `codex-readonly-review`独立read-only reviewを5ラウンド実施して`APPROVED`（Blocking 0／Major 0）に収束し、Architecture Gate Checklist（8項目）をユーザーが個別にACCEPT。private helper（`_sanitize_event_identity()`/`_entry_from_dict()`）の跨モジュールimportを本Release限定のArchitecture exceptionとして承認。MVP Definition of Done・Release 6.35のMVP COMPLETEという到達点は、いずれも本改訂で変更しない | 6.36（新設） | 承認済み（Human Gate承認 2026-09-21。Implementation Phase開始承認済み、commit/pushは未承認） |
| 2026-09-21 | v1.5改訂：Post-MVP 2件目のReleaseとして6.37「release_claim() Diagnostic Correctness Fix」の個別節を新設した（本行がその変更本体）。6.37はFast Track Release（Architecture Contract Change: NO）であり、`docs/development_workflow.md` 7章のFast Track候補条件8項目をすべて満たすことを実装着手前に確認済み。Architecture Design文書の代わりにDesign Summary（`docs/design/release_claim_diagnostic_correctness_fix.md`）を作成。MVP Definition of Done・Release 6.35のMVP COMPLETEという到達点は、いずれも本改訂で変更しない | 6.37（新設） | 承認済み（Human Gate承認 2026-09-21。Implementation Phase開始承認済み、commit/pushは未承認） |
| 2026-10-06 | v1.6改訂：Post-MVP 3件目のRelease候補として6.38「WordPress Server-Side Media Idempotency Foundation」の個別節を新設した（本行がその変更本体）。Architecture Design（`docs/design/wordpress_server_side_media_idempotency_foundation.md`）は旧Draft（2026-09-22）の「APPROVED」記述をAmendment A1で撤回し、**Architecture Re-review Pending**として登録する（旧Round／Codexレビュー記録はrepo内で再現不能なhistorical self-recorded context）。6.38はConsumer-less Foundationであり、Python client integration・main.py／Retry／HRR配線・production deploymentはOut of Scope。MVP Definition of Done・Release 6.35のMVP COMPLETEという到達点は、いずれも本改訂で変更・再オープンしない | 6.38（新設・候補） | **Release scope・実装着手は未承認**（Architecture Re-review Pending。本docs変更は未commit、commit/pushはHuman Gate待ち） |
| 2026-10-06 | 6.38 Amendment A2：A1テキストに対するCodex High独立レビュー（Review #9）がNOT APPROVED（Blocking 0／Major 7／Minor 1／Suggestion 1）であったため、指摘（M1〜M7＋Minor＋Suggestion）に最小修正で対応するAmendment A2を設計書に適用した。主な変更：現行Pythonの`ArticleMediaUploadRecord.article_identity`がattempt-scopedであるという事実の訂正とstable identity sourceのIntegration Release必須precondition化、claim前／claim後のHTTP contract、3接続のAuthoritative Binding、closed allowlistの設計時確定、multisite実行時fail-closed、DB restart durabilityのstaging fault matrix追加。6.38のscope（Consumer-less Foundation、Python integration・production deploymentはOut of Scope）は変更していない。本行はRoadmap本文のRelease境界・MVP DoDの変更を伴わないため、文書バージョンはv1.6のまま据え置く。MVP Definition of Done・Release 6.35のMVP COMPLETEは変更・再オープンしない | 6.38（候補） | **Architecture Re-review Pending**（A2に対するReview #10はNOT APPROVEDとなりA3を適用。Release scope・実装着手は未承認。本docs変更は未commit、commit/pushはHuman Gate待ち） |
| 2026-10-06 | 6.38 Amendment A3：A2テキストに対するCodex High独立再レビュー（Review #10）がNOT APPROVED（Blocking 2（B1・B2）／Major 3（M-A〜M-C）／Minor 3（N1〜N3）／Suggestion 0）であったため、指摘に最小修正で対応するAmendment A3を設計書に適用した。主な変更：`gca_claim_state = none`を「identity未消費の証拠」とする定義の撤回（`none`は当該requestがclaimを確立せずCoreを呼んでいないことだけを示し、retry authorizationではない）、claim確立後は`none`へ戻らないBinding再確認規則（R1／R2／R3）、成功／error応答の形の一義化、claim前body size上限33,554,432バイトの確定、claim後・Core呼出前の障害の追加、`claim_token`長の厳密化、filename長さ記述の訂正。Implementation Start Validation対象をU-1〜U-16へ更新（N3）。6.38のscope（Consumer-less Foundation、Python integration・production deploymentはOut of Scope）は変更していない。本行はRoadmap本文のRelease境界・MVP DoDの変更を伴わないため、文書バージョンはv1.6のまま据え置く。MVP Definition of Done・Release 6.35のMVP COMPLETEは変更・再オープンしない | 6.38（候補） | **Architecture Re-review Pending**（A3に対するReview #11はNOT APPROVEDとなりA4を適用。Release scope・実装着手は未承認。本docs変更は未commit、commit/pushはHuman Gate待ち） |
| 2026-10-06 | 6.38 Amendment A4：A3テキストに対する独立再レビュー（Review #11）がNOT APPROVED（Blocking 0／Major 5（M1〜M5）／Minor 2）であったため、指摘に最小修正で対応するAmendment A4を設計書に適用した。主な変更：HTTP応答表の不足2ケース（`INSERT`がACK済みだがaffected rows≠1かつduplicate-keyでない→503 `unknown`、`CONFIRMED` duplicateのMedia Verification完遂不能→503 `confirmed`／欠落確定→409 `confirmed_inconsistent`、いずれもCore再実行禁止）の追加、成功応答を初回・replay同一のcanonical payload（5 field）に統一しCore response全文を透過・永続化しない旨の確定、32 MiB body上限の保証範囲の訂正（plugin独自v1 policy、正当な画像でも超過すれば413で拒否されうる）、filename最大長の算出（65文字）、設計書25章のメタ記述の削除。**本Roadmapの6.38節のGate記述を、特定のAmendment番号や固定のシナリオ件数に依存しない条件（「最新のArchitecture Designが独立ReviewでAPPROVED」「設計書でmandatoryと定義された全validation scenarioの完了」「17章台帳の全未確認事項の確認」）へ更新**した。6.38のscope（Consumer-less Foundation、Python integration・production deploymentはOut of Scope）は変更していない。本行はRoadmap本文のRelease境界・MVP DoDの変更を伴わないため、文書バージョンはv1.6のまま据え置く。MVP Definition of Done・Release 6.35のMVP COMPLETEは変更・再オープンしない | 6.38（候補） | **Architecture Re-review Pending**（A4に対するReview #12はNOT APPROVEDとなりA5を適用。Release scope・実装着手は未承認。本docs変更は未commit、commit/pushはHuman Gate待ち） |
| 2026-10-06 | 6.38 Amendment A5：A4テキストに対する独立再レビュー（Review #12）がNOT APPROVED（Blocking 1（A4-B1）／Major 2（A4-M1・A4-M2）／Minor 3／Suggestion 0）であったため、指摘に最小修正で対応するAmendment A5を設計書に適用した。主な変更：**finalizationの所有者・順序の統一**（route callbackがCore成功→snapshot 4項目の検証→snapshot保存・`CONFIRMED`化のdurable ACK確認→success responseを担い、`rest_pre_echo_response`のFinalizerはstate変更・検証・DB I/Oを持たず永続化済みsnapshotから5-field canonical payloadへ全置換するだけ）、Core成功後のsnapshot検証失敗（`source_url`欠落・不正等）の応答表・crash tableへの追加（409 `processing`）、Goal G2の修正（idempotency結果・claim stateとstable identityの分離）、T-23eのR3でのfault injectionへの修正と静的別schema構成（T-23f）の分離、23章へのC9追記、T-29 L3の前提条件の追加。6.38のscope（Consumer-less Foundation、Python integration・production deploymentはOut of Scope）とRoadmap Gate条件は変更していない。本行はRoadmap本文のRelease境界・MVP DoDの変更を伴わないため、文書バージョンはv1.6のまま据え置く。MVP Definition of Done・Release 6.35のMVP COMPLETEは変更・再オープンしない | 6.38（候補） | **Architecture Re-review Pending**（A5に対するReview #13はNOT APPROVEDとなりA6を適用。Release scope・実装着手は未承認。本docs変更は未commit、commit/pushはHuman Gate待ち） |
| 2026-10-06 | 6.38 Amendment A6：A5テキストに対する独立再レビュー（Review #13）がNOT APPROVED（Blocking 0／Major 3（M1〜M3）／Minor 0／Suggestion 0。Review #12の全Findingsは閉鎖と判定）であったため、指摘に最小修正で対応するAmendment A6を設計書に適用した。主な変更：**Finalizerをcanonical success responseの最終所有者**として、応答の**dataとHTTP statusの両方**（first success＝201、confirmed replay＝200）を置換する契約と、**plugin-private・write-onceのrequest-local contextを、exact requestのinstance identity・idempotency identity・success mode・expected status・durable snapshotに束縛**し、不一致・欠落・不正はcanonical successを返さずfail-closedとする契約（偶発的混入の防止であり、co-resident malicious codeは脅威モデルに加えない）、T-22の「claim後はすべて409」という旧一般化の削除と応答表に従うmatrix testへの変更、**実装開始前のgate（18章）から、実装後でなければ確認できないL1 golden-vector実装適合を削除し、実装フェーズのgate（20章）へ移動**。6.38のscope（Consumer-less Foundation、Python integration・production deploymentはOut of Scope）とRoadmap Gate条件の方針は変更していない（Gate記述に、18章の範囲が「実装前に確認できる前提のみ」であることを追記）。本行はRoadmap本文のRelease境界・MVP DoDの変更を伴わないため、文書バージョンはv1.6のまま据え置く。MVP Definition of Done・Release 6.35のMVP COMPLETEは変更・再オープンしない | 6.38（候補） | **Architecture Re-review Pending**（A6に対するReview #14はNOT APPROVEDとなりA7を適用。Release scope・実装着手は未承認。本docs変更は未commit、commit/pushはHuman Gate待ち） |
| 2026-10-06 | 6.38 Amendment A7：A6テキストに対する独立再レビュー（Review #14）がNOT APPROVED（Blocking 1（B1）／Major 1（M1）／Minor 1（N1）／Suggestion 0。Review #13のM3は閉鎖、M1・M2は部分的閉鎖と判定）であったため、指摘に最小修正で対応するAmendment A7を設計書に適用した。主な変更：**Finalizerの発動判定をcontextの有無ではなくresponse classで規定**（GCA-tagged requestの最終応答に対する3分岐：class A＝2xx→valid success context必須（欠落・不一致・不正は503 `confirmed`）／class B＝non-2xxのcanonical error→contextを要求せずそのまま通す／class C＝canonical errorとして検証できないnon-2xx→503 `unknown`へfail-closed）、23章と設計判断の索引に残っていた旧一般化「claim後の失敗はすべて409 `processing`」の削除、**canonical error表（E1〜E9：status・error code・固定message・`gca_claim_state`の組合せの閉集合）の正本化**とT-22での完全一致検証。6.38のscope（Consumer-less Foundation、Python integration・production deploymentはOut of Scope）とRoadmap Gate条件は変更していない。本行はRoadmap本文のRelease境界・MVP DoDの変更を伴わないため、文書バージョンはv1.6のまま据え置く。MVP Definition of Done・Release 6.35のMVP COMPLETEは変更・再オープンしない | 6.38（候補） | **Architecture Re-review Pending**（A7に対するReview #15はNOT APPROVEDとなりA8を適用。Release scope・実装着手は未承認。本docs変更は未commit、commit/pushはHuman Gate待ち） |
| 2026-10-06 | 6.38 Amendment A8：A7テキストに対する独立再レビュー（Review #15）がNOT APPROVED（Blocking 1（B1）／Major 2（M1・M2）／Minor 1（N1）／Suggestion 0。Review #14のM1・N1は閉鎖、B1は部分的閉鎖と判定）であったため、指摘に対応するAmendment A8を設計書に適用した。主な変更：**A7のresponse-class 3-way dispatchの廃止**と、**plugin control path（ラップしたpermission_callbackとroute callback）が各GCA requestについて確定するplugin-private・write-once・request-localのauthoritative outcome marker（`SUCCESS_FIRST`／`SUCCESS_REPLAY`／`E1`〜`E9`）に基づく設計への置換**（Finalizerはpre-Finalizerの応答のstatus・data・種別を判断材料にせず、markerだけから最終responseのstatusとdataを新規構築・完全置換。`SUCCESS_FIRST`はdurable ACK後のみ、`SUCCESS_REPLAY`はVerification成功後のみ設定。marker欠落・不正・二重設定・別requestはE5へfail-closed。co-resident malicious codeは脅威モデル外のまま）、`X-GCA-Identity-Schema`のclient供給値の不一致をE1／400へ統一（server内部のschema／DB／epoch／configurationの不一致はE4／503）、Finalizerが出力するexact key setの契約（成功＝5 key、error＝3 key・`data`は2 key）、1xx／3xxを含むpre-Finalizer応答の改変のテスト（T-34）。6.38のscope（Consumer-less Foundation、Python integration・production deploymentはOut of Scope）とRoadmap Gate条件は変更していない。本行はRoadmap本文のRelease境界・MVP DoDの変更を伴わないため、文書バージョンはv1.6のまま据え置く。MVP Definition of Done・Release 6.35のMVP COMPLETEは変更・再オープンしない | 6.38（候補） | **Architecture Re-review Pending**（A8に対するReview #16はNOT APPROVEDとなりA9を適用。Release scope・実装着手は未承認。本docs変更は未commit、commit/pushはHuman Gate待ち） |
| 2026-10-06 | 6.38 Amendment A9：A8テキストに対する独立再レビュー（Review #16）がNOT APPROVED（Blocking 1（B1）／Major 1（M1）／Minor 2（N1・N2）／Suggestion 0。Review #15のM1・M2・N1は閉鎖、B1は部分的閉鎖と判定）であったため、指摘に最小修正で対応するAmendment A9を設計書に適用した。主な変更：Finalizerの失敗に関する契約の整理（詳細は設計書12章・24.9節を参照。A9の一部の記述はA10・A11で訂正された）、T-22(4)・未検証範囲・用語集の同期。6.38のscope（Consumer-less Foundation、Python integration・production deploymentはOut of Scope）とRoadmap Gate条件は変更していない。本行はRoadmap本文のRelease境界・MVP DoDの変更を伴わないため、文書バージョンはv1.6のまま据え置く。MVP Definition of Done・Release 6.35のMVP COMPLETEは変更・再オープンしない | 6.38（候補） | **Architecture Re-review Pending**（A9に対するReview #17はNOT APPROVEDとなりA10を適用。Release scope・実装着手は未承認。本docs変更は未commit、commit/pushはHuman Gate待ち） |
| 2026-10-06 | 6.38 Amendment A10：A9テキストに対する独立再レビュー（Review #17）がNOT APPROVED（Blocking 1（B1）／Major 1（M1）／Minor 0／Suggestion 0。Review #16のM1・N1・N2は閉鎖、B1は部分的閉鎖と判定）であったため、指摘に対応するAmendment A10を設計書に適用した。主な変更：Finalizerの適用runtime failureの契約を設計書12章を唯一の正本とする整理（詳細は設計書12章・24.10節を参照）、旧記述の削除・訂正。6.38のscope（Consumer-less Foundation、Python integration・production deploymentはOut of Scope）とRoadmap Gate条件は変更していない。本行はRoadmap本文のRelease境界・MVP DoDの変更を伴わないため、文書バージョンはv1.6のまま据え置く。MVP Definition of Done・Release 6.35のMVP COMPLETEは変更・再オープンしない | 6.38（候補） | **Architecture Re-review Pending**（A10に対するReview #18はNOT APPROVEDとなりA11を適用。Release scope・実装着手は未承認。本docs変更は未commit、commit/pushはHuman Gate待ち） |
| 2026-10-06 | 6.38 Amendment A11：A10テキストに対する独立再レビュー（Review #18）がNOT APPROVED（Blocking 0／Major 2（M1・M2）／Minor 2（N1・N2）／Suggestion 0。Review #17のM1は閉鎖、B1は部分的閉鎖と判定）であったため、指摘に対応するAmendment A11を設計書に適用した。主な変更：Finalizerの適用runtime failureの契約を設計書12章のみとし、他の章・両Roadmapの再記述を参照のみへ整理、T-07の検証方法と層分離の精密化、T-32のE8経路の修正、設計書26章の見出しの更新（詳細は設計書24.11節を参照）。6.38のscope（Consumer-less Foundation、Python integration・production deploymentはOut of Scope）とRoadmap Gate条件は変更していない。本行はRoadmap本文のRelease境界・MVP DoDの変更を伴わないため、文書バージョンはv1.6のまま据え置く。MVP Definition of Done・Release 6.35のMVP COMPLETEは変更・再オープンしない | 6.38（候補） | **Architecture Re-review Pending**（A11に対するReview #19はNOT APPROVEDとなりA12を適用。Release scope・実装着手は未承認。本docs変更は未commit、commit/pushはHuman Gate待ち） |
| 2026-10-06 | 6.38 Amendment A12：A11テキストに対する独立再レビュー（Review #19）がNOT APPROVED（Blocking 0／Major 1（M1）／Minor 0／Suggestion 0。Review #18のM2・N1・N2は閉鎖、M1は部分的閉鎖と判定）であったため、指摘に対応するAmendment A12を設計書に適用した。主な変更：設計書12章の表の各行に識別子（F-1〜F-6）を付与し、他の章・テストは識別子で参照するのみとする整理、C11・T-22・T-07の参照化、本Roadmapの記述の圧縮（契約の内容は設計書が正本。詳細は設計書24.12節を参照）。6.38のscope（Consumer-less Foundation、Python integration・production deploymentはOut of Scope）とRoadmap Gate条件は変更していない。本行はRoadmap本文のRelease境界・MVP DoDの変更を伴わないため、文書バージョンはv1.6のまま据え置く。MVP Definition of Done・Release 6.35のMVP COMPLETEは変更・再オープンしない | 6.38（候補） | **Architecture Re-review Pending**（A12に対するReview #20はNOT APPROVEDとなりA13を適用。Release scope・実装着手は未承認。本docs変更は未commit、commit/pushはHuman Gate待ち） |
| 2026-10-06 | 6.38 Amendment A13：A12テキストに対する独立再レビュー（Review #20）がNOT APPROVED（Blocking 0／Major 1（M1）／Minor 1／Suggestion 0。Review #19のM1は部分的閉鎖と判定）であったため、指摘だけに対応するAmendment A13を設計書に適用した。主な変更：設計書26章のR-10に残っていた旧一般化（claim後の失敗の一律409）の削除と8.3節の正本matrixへの参照への訂正、26章の見出しの更新、全文の残存確認（詳細は設計書24.13節を参照）。新しい設計判断・scope変更は行っていない。6.38のscope（Consumer-less Foundation、Python integration・production deploymentはOut of Scope）とRoadmap Gate条件は変更していない。本行はRoadmap本文のRelease境界・MVP DoDの変更を伴わないため、文書バージョンはv1.6のまま据え置く。MVP Definition of Done・Release 6.35のMVP COMPLETEは変更・再オープンしない | 6.38（候補） | **Architecture Re-review Pending**（A13に対するReview #21は未実施。Release scope・実装着手は未承認。本docs変更は未commit、commit/pushはHuman Gate待ち） |
| 2026-10-06 | 6.38 Amendment A14：A13テキストに対するReview #21は**APPROVED**（Blocking／Major／Minor／Suggestion＝0）であり、commit `2513ae5`でdocs-only checkpointとして確定、Release scopeはユーザーが承認した。しかし、その後の**Implementation Start Validation（設計書18章、WordPress 7.1.1 tag sourceのread-only確認）で、承認済みArchitectureの前提誤り（設計書17.5節のU-18・U-2・U-19）が判明し、Implementation Start Readiness＝NOT READY・Architecture Amendment必要となった**ため、設計書にAmendment A14を適用した（投影位置・response header・投影後の改変点・control pathの網羅範囲・batchの扱いの再設計。契約の内容と詳細は設計書12章・17.5節・24.14節が正本で、本Roadmapは再記述しない）。**Architecture statusをRe-review Pending（Re-review Required）へ戻した**。6.38のscope（Consumer-less Foundation、Python integration・production deploymentはOut of Scope）とRoadmap Gate条件は変更していない。Roadmap Gateの文言は、台帳のU-ID範囲（U-1〜U-21）とシナリオ範囲（T-01〜T-37）の現行値への更新のみ（Gateの考え方・Amendment番号に依存しない定めは不変）。本行はRelease境界・MVP DoDの変更を伴わないため、文書バージョンはv1.6のまま据え置く。MVP Definition of Done・Release 6.35のMVP COMPLETEは変更・再オープンしない | 6.38（候補） | **Architecture Re-review Pending**（A14に対するReview #22は未実施。Production実装は開始しない。本docs変更は未commit、commit/pushはHuman Gate待ち） |
| 2026-10-06 | 6.38 Amendment A15：A14テキストに対するReview #22が**NOT APPROVED**（Blocking 1（B1）／Major 3（M1〜M3）／Minor 2（N1・N2）／Suggestion 0。A14の投影位置の設計は、7.1.1 sourceの実行順序上で成立すると判定。U-18＝解消、U-2・U-19＝部分的に解消）であったため、指摘だけに対応するAmendment A15を設計書に適用した。新しい設計判断・scope変更は行っていない。契約の内容と詳細は設計書12章・24.15節が正本で、本Roadmapは再記述しない。Roadmap Gateの文言は、台帳のU-ID範囲（U-1〜U-22）とシナリオ範囲（T-01〜T-38）の現行値への更新のみ。本行はRelease境界・MVP DoDの変更を伴わないため、文書バージョンはv1.6のまま据え置く。MVP Definition of Done・Release 6.35のMVP COMPLETEは変更・再オープンしない | 6.38（候補） | **Architecture Re-review Pending**（A15に対するReview #23は未実施。Production実装は開始しない。本docs変更は未commit、commit/pushはHuman Gate待ち） |
| 2026-10-06 | 6.38 Amendment A16：A15テキストに対するReview #23が**NOT APPROVED**（Blocking 1（B-01）／Major 4（M-01〜M-04）／Minor 1（N-01）／Suggestion 0。Review #22のM2・N1・N2はCLOSED、B1・M1はPARTIALLY CLOSED、M3はOPEN）であったため、指摘だけに対応するAmendment A16を設計書に適用した。主な変更は、`permission_callback`をmarkerから切り離すこと、side-effect safetyとHTTP投影を分離すること、canonical保証の範囲（CS-1）を限定すること、source証拠の範囲を再現可能な事実に限定することである（契約の内容と詳細は設計書12章・24.16節が正本で、本Roadmapは再記述しない）。6.38のscope（Consumer-less Foundation、Python integration・production deploymentはOut of Scope）とRoadmap Gate条件は変更していない。Roadmap Gateの文言は、台帳のU-ID範囲（U-1〜U-21。U-22は欠番）とシナリオ範囲（T-01〜T-38）の現行値への更新のみ。本行はRelease境界・MVP DoDの変更を伴わないため、文書バージョンはv1.6のまま据え置く。MVP Definition of Done・Release 6.35のMVP COMPLETEは変更・再オープンしない | 6.38（候補） | **Architecture Re-review Pending**（A16に対するReview #24は未実施。Production実装は開始しない。本docs変更は未commit、commit/pushはHuman Gate待ち） |
| 2026-10-07 | 6.38 Amendment A17：A16テキストに対するReview #24が**NOT APPROVED**（Blocking 0／Major 2（M-A16-01・M-A16-02）／Minor 1（N-A16-01）／Suggestion 0。Review #23のB-01・M-01・M-03・N-01はCLOSED、M-02・M-04はPARTIALLY CLOSED）であったため、指摘だけに対応するAmendment A17を設計書に適用した。主な変更は、method境界（effective method基準）を設計書12章に正本化すること、テスト節・索引・リスクの再記述を12章の識別子による参照のみへ整理すること、台帳・見出し・Amendment番号をA17現在へ同期することである。**WordPress source evidenceの追加・取得・repo保存は行っていない**。Review #24で独立に照合できなかったsource依存の主張は、verifiedへ格上げせず、validation-requiredとして設計書17.6節・18章（Implementation Start Validation gate）に残した（契約の内容と詳細は設計書12章・17.6節・24.17節が正本で、本Roadmapは再記述しない）。6.38のscope（Consumer-less Foundation、Python integration・production deploymentはOut of Scope）とRoadmap Gate条件は変更していない。Roadmap Gateの文言は、台帳のU-ID範囲（U-1〜U-21。U-22は廃止済みでactive inputに含めない）とシナリオ範囲（T-01〜T-38）のとおりで、数値の変更はない。本行はRelease境界・MVP DoDの変更を伴わないため、文書バージョンはv1.6のまま据え置く。MVP Definition of Done・Release 6.35のMVP COMPLETEは変更・再オープンしない | 6.38（候補） | **Architecture Re-review Pending**（A17に対するReview #25は未実施。Production実装は開始しない。本docs変更は未commit、commit/pushはHuman Gate待ち） |
| 2026-10-07 | 6.38 Amendment A18：A17テキストに対するReview #25（canonical WordPress 7.1.1 source evidenceをread-onlyで照合）が**NOT APPROVED**（Blocking 0／Major 2（M-25-01・M-25-02）／Minor 1（N-25-01）／Suggestion 0。Review #24の3 Finding（M-A16-01・M-A16-02・N-A16-01）はCLOSED）であったため、指摘だけに対応するAmendment A18を設計書に適用した。Review #25でCLOSEDとなったA17の項目は再変更していない。主な変更は、`rest_post_dispatch`の全call-siteの分類と、`status_header`filterのtopology・契約を設計書12章に正本化すること、`status_header()`の本体が供給sourceに存在することへ訂正すること、dispatch文脈別のテストを拡張すること、台帳・見出し・Amendment番号をA18現在へ同期することである。**source確認だけでruntime（実環境）の項目をPASSにしない**（契約の内容と詳細は設計書12章・17.6節・24.18節が正本で、本Roadmapは再記述しない）。6.38のscope（Consumer-less Foundation、Python integration・production deploymentはOut of Scope）とRoadmap Gate条件は変更していない。Roadmap Gateの文言は、台帳のU-ID範囲（U-1〜U-21。U-22は廃止済みでactive inputに含めない）とシナリオ範囲（T-01〜T-38）のとおりで、数値の変更はない。本行はRelease境界・MVP DoDの変更を伴わないため、文書バージョンはv1.6のまま据え置く。MVP Definition of Done・Release 6.35のMVP COMPLETEは変更・再オープンしない | 6.38（候補） | **Architecture Re-review Pending**（A18に対するReview #26は未実施。Production実装は開始しない。本docs変更は未commit、commit/pushはHuman Gate待ち） |
| 2026-10-07 | 6.38 Review #26 APPROVED後のdocumentation sync：A18に対するReview #26（Codex High。canonical・auxiliaryのWordPress 7.1.1 source evidenceをread-onlyで照合）が**APPROVED**（Blocking 0／Major 0／Minor 2／Suggestion 0。Review #25の3 FindingはCLOSED）であった。Minor 2件（設計書V-16の記述の同期、現在地表記の同期）を、**文書の同期のみ**で対応した。**Architecture contract・ID・scope・テスト・台帳の内容は変更していない**。**このAPPROVEDは、設計文書の内部整合性とsource上の事実への照合の判定であり、Implementation Start Validationのruntime項目（デプロイ先version・approved plugin topology・PHP／SAPI・L2／L3等）は未検証のまま**（設計書17.6節）。Human Gate（設計書21章）の承認、commit、pushは未実施。6.38のscopeとRoadmap Gate条件は変更していない。本行はRelease境界・MVP DoDの変更を伴わないため、文書バージョンはv1.6のまま据え置く。MVP Definition of Done・Release 6.35のMVP COMPLETEは変更・再オープンしない（契約の内容と詳細は設計書12章・19章・24.18節が正本で、本Roadmapは再記述しない） | 6.38（候補） | **Architecture Re-review APPROVED**（Review #26。runtime項目は未検証・実装未着手。本docs変更は未commit、commit/pushはHuman Gate待ち） |

---

## MVP運用原則

MVP COMPLETEまでは「MVP DoD達成に必要か」をRelease scope判断基準とし、不要なFoundation追加は原則post-MVPへ送る。
