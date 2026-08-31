# Retry Lineage, Eligibility & Durable Attempt State（Release 6.31）設計書

## 0. Status

**Approved（Round 11 + Cleanup版。2026-08-31、Human Gate承認済み）。** 実装（`src/`配下の変更）はまだ開始していない。

**承認記録（2026-08-31）**：本書（Round 11 + Cleanup版）について、§26 Architecture Gate Checklistの**Human Gate必須15項目すべて**をユーザーが明示的に承認した。承認にあたり、以下のトレードオフ・既知リスクを特に理解した上で受容する旨の確認を得た：(1) `NOT_ACTIONED`もbudgetを消費し、genuineな成功機会を得られないまま有限停止することを優先する設計（9.8.1.3章、25章Risk#14）／(2) lineage作成後はdurable state（`terminal_disposition`・`attempt_count`・`max_attempts`）のみをauthoritativeとし、事後のmonitor_status変化を一切参照しない設計（7.1・7.2・9.3.2・9.8.1.2章）／(3) 6.31はsingle-host限定・`retry()`/`reconcile_all()`の完全直列化（throughput低下）を受容する（9.1・9.3.3章）／(4) stale lockの手動復旧を、構造的に安全ではないoperational trust boundaryとして受容する（9.4章）／(5) `RETRY_LINEAGE_ENABLED=false`時も本書で定義したreconciliation契約（`reconcile_all()`自体は動作継続する仕様）を維持する（16章）／(6) legacy record（`action_taken`未設定）再実行によるREVIEWの日またぎ重複生成・`processed_count`二重計上リスクを受容する（11.7.4章、`workflow_step_executor.py:310-317`で確認済みの実害）／(7) scope不整合は自動修復せずfail-closedで停止する契約（11.4.5・12・13章）／(8) 17章crash matrix#14で明示した、lineage store書き込み失敗とExecution History terminal処理失敗の複合障害という残存operational gapを6.31では受容する。詳細は§26の各項目チェック状態を参照。

**Architecture Amendment（2026-08-31、Human Gate承認済み）**：Approved Design（上記）に基づく実装フェーズにおいて、`next_attempt_ordinal`（§13スキーマ）の意味論が本書内で未確定のまま残っていたこと（§12「next_eligible_at・next_attempt_ordinal更新等はRound 1〜3から変更なし」という旧版参照のまま、実際には確定した記述が本書のいずれのRoundにも存在しなかった）が判明した。§10.3.3(b)のcorrelation-fallback exact-match検証（`intended_attempt_no == lineage.next_attempt_ordinal`、「現在アクティブな（次に消費される）attempt_noとの完全一致」）を実装可能にするため、`next_attempt_ordinal`を**「`attempt_scopes[-1].attempt_no`と常に同期する、現在openなattemptのordinalの非正規化コピー」**として確定した（`create_new_lineage()`はlineage作成時に`attempt_scopes[0].attempt_no`と同じ値をsnapshotし、`open_next_attempt()`は新しいscopeを追加するのと同時にこの値も新しいattempt_noへ更新する。claim()済みだが`mark_execution_started()`が未達のorphan状態では、`attempt_scopes`は更新されないため、この値もclaim()が払い出したattempt_noのまま変化しない——`mark_execution_started()`が一度も成功していないorphanの場合、`next_attempt_ordinal`は当該attemptの試行によって一切消費されていないため、常にこの値と一致するはずである、という§10.3.3(b)の記述の前提を満たす）。この修正は、§10.3.3の既承認contractを実装可能にするための**限定的な設計整合修正**であり、`next_attempt_ordinal`という既存スキーマフィールドの意味論を確定させるのみで、新しいフィールド・新しい状態遷移・新しいHuman Gate対象トレードオフはいずれも追加しない（normative architecture・4-phase state machine・locking・attempt accounting・admission gate契約はいずれも無変更）。ユーザーはこの修正を上記の限定的な設計整合修正として承認した。実装（`src/retry_lineage/retry_lineage_manager.py`の`create_new_lineage()`・`open_next_attempt()`・`verify_orphan_correlation()`）は既にこの定義に基づいて完了・test検証済みであり、本承認記録は既存実装を追認するものである。

**Architecture Amendment（Human Gate承認済み、2026-08-31、Code Review Findings対応）**：実装完了後にCodexへ依頼した独立Code Review（`src/`配下の実コードレビュー、Architecture Designレビューとは別）で、Blocking 2件・Major 2件の指摘を受けた。ユーザー独立照合によりいずれも実コードで確認済み。本Amendmentはこれら4件について、限定的な設計整合修正として本書へ明文化した（4-phase state machine・attempt accounting・locking契約・6.31 scope境界・既承認15件のHuman Gate事項はいずれも無変更）。26章の新規Human Gate候補4件は2026-08-31にユーザーが明示的に承認した（下記トレードオフを理解の上で受容：(1) hook未ack時は外部action未開始としてCLAIMEDを解放しSUCCEEDED/Queue COMPLETEにしない、(2) `mark_terminal().acknowledged=False`は成功確定せずfail-closedでreconcile対象とする、(3) `create_new_lineage()`前にglobal membership uniquenessを検証し破損時は新規lineageを作らない、(4) `next_attempt_ordinal`と`attempt_scopes[-1].attempt_no`の不一致は自動修復せずmutation前にfail-closedする、(5) CLAIMED orphanは`RetryExecutionLock`下のreconcileで`release_claim()`により回収する、(6) EXECUTION_STARTED未到達のhook失敗/orphanはretry budgetを消費しない）。本承認をもって、実装フェーズへ進む。

- **Blocking#1（post-admission hook未ack時のdisposition誤判定）**：`disposition_from_categories()`（11.5章）は全step`NOT_APPLICABLE`（hook未ack由来の`skip_category=HOOK_NOT_ACKNOWLEDGED`/`HOOK_EXCEPTION`）の場合に`SUCCEEDED`へfall throughする。`RetryExecutor.execute()`はこれを検知せず`mark_terminal(SUCCEEDED)`を試みたまま`RetryOutcome.RETRIED`を返し、`RetryQueueUpdateDecider`が独立に同じ判定を再計算して`COMPLETE`とする。実際には`mark_execution_started()`が一度も成功しておらずlineageは`CLAIMED`のまま——外部actionは未開始にもかかわらず、Queueが完了扱いになりうる。**10.2.4章（新設）で修正を明文化する。**
- **Blocking#2（`mark_terminal()`のack=False無視）**：`retry_executor.py`は`mark_terminal()`の戻り値（`MarkTerminalResult.acknowledged`）を一切確認せず`RetryOutcome.RETRIED`を返す。12章は既にこの契約自体は明文化していた（「`_retry_locked()`内の`mark_terminal()`呼び出しが...ack=False...`RetryOutcome.SKIPPED`を返す」）が、実装ではこの呼び出しが実際には`RetryExecutor.execute()`内で行われており、責務の所在が本書とコードで食い違っていたため、この既承認契約が実装へ反映されなかった。**10.2.4章（新設）で、実際の呼び出し位置（`RetryExecutor.execute()`）を明示した上で契約を再確認する。**
- **Major#3（グローバルmembership一意性チェックの欠落）**：7.1章のコメント・25章項目16が前提とする「7.4章のグローバルmembership一意性チェック」は、本書のいずれのRoundにも実在する節として書かれたことがなく（dangling reference）、`create_new_lineage()`（7.2章）にも対応する実装がない。**7.2章へ具体的なチェックを追加し、7.1章・25章項目16の参照を修正する。**
- **Major#4（`next_attempt_ordinal`不変条件のfail-closed検証欠落）**：Architecture Amendment（上記、次段落）で確定した「`next_attempt_ordinal`は`attempt_scopes[-1].attempt_no`と常に同期する」という契約自体は、`claim()`・`open_next_attempt()`のいずれにおいても事前検証されていない（値の生成・参照はしているが、両者の一致そのものはassertされていない）。**12章へ明示的な検証を追加する。**

これらの発見自体は、既承認のnormative architecture（4-phase state machine・locking・attempt accounting・admission gate分離）そのものへの疑義ではなく、その正しい実装・実装可能性を担保するための**契約の明確化・fail-closed検証の追加**である（next_attempt_ordinal Amendmentと同種の性質）。ただし、Blocking#1/#2はQueueの誤完了という外部可視の実害を伴うため、次の実装フェーズで必ず修正する前提とする。26章に本Amendment用の新規Human Gate候補項目を追加する（未承認）。

本書はRelease 6.31のArchitecture Designであり、実装は一切行っていない。Round 8に対してCodex独立adversarial review（foreground実行、reasoning effort High、実コードとの突き合わせあり）が行われ、Major 3件（MAJ-R8-1：`open_next_attempt()`の`max_attempts`が`monitor_status`と同種の未定義変数であり、かつ「`RetryLineageRecord`のdurable state」という記述自体が実コード（`RetryPolicy`は設定値であり per-lineage state ではない）と矛盾／MAJ-R8-2：`NOT_ACTIONED`（payback）が無制限に繰り返される場合、budgetを消費しないままlineage state（attempt_no・attempt_scopes・transition_history）が無限に成長しうるliveness問題が未検討／MAJ-R8-3：「`_retry_locked()`はattempt 1のみを担当する」という記述が実コード（`claim()`はattempt 2以降でも必ず呼ばれる）と矛盾し、`open_next_attempt()`と`_retry_locked()`という2つの独立した許可ゲートが並存・矛盾しうる）・Minor 4件（MIN-R8-1：payback atomicityテストにcrash injectionがない／MIN-R8-2：`attempt_count`アンダーフロー防御が未規定／MIN-R8-3：test #40(a)の文言誤記／MIN-R8-4：stored/recomputed scope比較の順序正規化が未規定）の指摘を受けた。Round 9はそれら指摘への対応版として、retry gate契約そのものを再設計した。

Round 9に対してさらにCodex独立adversarial review（foreground実行、実コードとの突き合わせあり）が行われ、Major 2件（MAJ-R9-1：`_retry_locked()`が既存lineageの有無を問わず`self._monitor.get_status(run_id)`を無条件に呼び出しており、「initial admissionは新規lineage作成時のみ」「attempt 2以降でMonitor lookup 0回」という7.1・9.8.1章の主張と実装（9.3.2章）が矛盾していた／MAJ-R9-2：`resolve_or_create()`の分岐(1)(2)（既存lineageへの再接続）の詳細疑似コードが一度も明示されず「旧版参照」のまま残されており（Round 9自身が25章Risk#15で自認済み）、`max_attempts`が既存lineage再接続時に誤って新しいsnapshot値で上書きされないことの保証、および`max_attempts`snapshot値自体の妥当性検証（整数・非負）が未規定だった）・Minor 1件（MIN-R9-1：`attempt_scopes`の`steps_to_execute`が「保存時点でcanonical orderへ正規化される」契約が明示されておらず、`claim()`側の比較時正規化（11.4.5.2(a)）のみに依存していた）の指摘を受けた。Round 10はそれら指摘への対応版として、(1) initial admissionの完全分離（`find_existing_lineage()`／`create_new_lineage()`の二段階化）、(2) `max_attempts` snapshotのvalidation・既存lineage再接続時の不変性の明示、(3) stored scopeの保存時canonical化契約、の3点を中心に改訂した。

Round 10に対してさらにCodex独立adversarial review（実コード（`src/retry_engine/retry_policy.py`・`src/workflow_monitor/`・`src/execution_history/`等）との突き合わせあり）が行われ、Major 2件（MAJ-R10-1：§7.2の`create_new_lineage()`が`self._policy.should_retry(monitor_status, attempt=0)`を`max_attempts_snapshot`のvalidationより**前**に呼んでおり、実コード`RetryPolicy.should_retry()`（`retry_policy.py:47`、`attempt < self.max_attempts`という比較を内部で行う）が不正な`max_attempts`（文字列・`None`等）に対して`TypeError`を送出してしまうため、「structured `admission_rejected=True`でfail-closedする」という契約を例外送出に委ねる形でしか満たせていなかった／MAJ-R10-2：§7.2が`steps_confirmed_done=[]`を固定的にハードコードしており、11.4.3章が要求する「attempt 1のsteps_confirmed_doneは元のFAILED/TIMEOUT recordからGENUINE_SUCCESSと分類できたstepを初期値として含める」という契約と矛盾していた。`create_new_lineage(run_id, monitor_status)`は元の実行結果を受け取る入力経路を持っておらず、この契約を実装可能な形で満たせていなかった）・Minor 3件（MIN-R10-1：§11.4.5.2(a)の`claim()`が§7.3で「共通ヘルパー」と謳う`_canonicalize_step_order()`を実際には使わず、`canonical_order`辞書と`sorted()`をインライン構築していた／MIN-R10-2：test #49が「既存lineage再接続でMonitor/Policy呼び出し0回」をmockのcall countで示すのみで、direct-root（分岐1）・membership／multi-hop（分岐2）を区別して検証していなかった／MIN-R10-3：§9.3.4が`RetryLineageStoreLock`取得メソッド数を旧「6つ」のまま記載しており、§9.2の「7つ」（Round 10で`find_existing_lineage()`・`create_new_lineage()`追加を反映済み）と矛盾していた）、およびSuggestion 2件（test #53がvalidation-rejectionとpolicy-rejectionを区別せずに検証していた／test #50・#51が`max_attempts`フィールド単体の比較に留まり、既存lineageの完全な serialized state不変性を確認していなかった）の指摘を受けた。本書（Round 11）はそれら指摘への対応版であり、(1) `max_attempts` snapshot validationを`should_retry()`より前へ移動、(2) attempt 1のscopeを`monitor_record.steps`から導出する`compute_initial_confirmed_steps()`の新設、(3) `claim()`での共通canonicalizeヘルパー使用の徹底、(4) 上記に対応するtest改訂、の4点を中心に改訂した。

Round 11に対してさらにCodex独立adversarial reviewが行われ、**Blocking/Major指摘は0件**（「Pass with minor corrections」判定）で、MAJ-R10-1・MAJ-R10-2・MIN-R10-1・MIN-R10-2・MIN-R10-3・Suggestion 2件はすべてResolvedと確認された。ただしMinor 2件（MIN-R11-1：test #58がlegacy stepの安全性を`steps_confirmed_done`からの除外のみで検証しており、その帰結である`attempt_scopes[0].steps_to_execute`側への残存を直接assertしていなかった／MIN-R11-2：test #54の「Round 10ではstubが`create_new_lineage()`を実際に通らない」という説明が、Round 10も`compute_steps_to_execute(steps_confirmed_done=[])`を明示的に呼んでいた事実と矛盾する誤記だった）とSuggestion 3件（SUG-R11-1：test #57/#58をtest #56と同じ粒度でdurable scope全体まで検証すべき／SUG-R11-2：test #53のpolicy-rejection control caseが`max_attempts=0`＋非対象statusという、rejectionの原因が一意に定まらない組み合わせだった／SUG-R11-3：§14の`create_new_lineage()`の記述が`monitor_status`から`monitor_record`への改名を文中の挿入句として扱っており読みにくかった）の指摘を受けた。**本書はこのRound 11 Cleanupでこれら5件をすべて反映した（doc/test-spec修正のみ、normative architecture・scope・runtime semanticsの変更なし）。** 本書の内容が確定・承認されるまで、`src/`配下の変更には着手しない。

Baseline：`main` / `1a9c5e157ccb3bd83f2769308f7c5b3f95d3e3a8`（Release 6.30.0完了・commit済み）。fetch/pullは行っていない。

### 0.1 Codex Round 8指摘の対応表

| 指摘 | 内容（要約） | 対応章 |
|---|---|---|
| MAJ-R8-1 | `open_next_attempt()`の`max_attempts`が裸の未定義識別子であり、§9.8.1が「`RetryLineageRecord`に永続化されたdurable state」と主張していたのに対し、実コード（`src/retry_engine/retry_policy.py`）では`RetryPolicy`（設定値、env由来）のフィールドであることを実コード確認により指摘された | 9.8.1・13章（lineage作成時のsnapshot化、`RetryLineageRecord.max_attempts`の新設） |
| MAJ-R8-2 | `NOT_ACTIONED`のたびに`attempt_count`をpaybackし続けると、budgetを消費しないまま無制限にattemptを繰り返せてしまい、`attempt_no`／`attempt_scopes`／`transition_history`が無限に成長しうる。個々の状態はいずれも正常に見えるため`diagnose_stuck()`でも検出できない | 9.8.1章（payback廃止、`NOT_ACTIONED`も他dispositionと同様にbudgetを消費する契約への変更） |
| MAJ-R8-3 | `_retry_locked()`の`should_retry(monitor_status, ...)`呼び出しが「attempt 1のみ」という記述は、`claim()`がattempt 2以降でも必ず呼ばれる（`open_next_attempt()`後のREADY_ELIGIBLE→CLAIMED遷移）という設計と矛盾しており、実際には`open_next_attempt()`（durable state judge）と`_retry_locked()`（monitor_status judge）という2つの独立した、意味論の異なる許可ゲートが並存し、相互に矛盾しうる | 7・9.3.2・9.8.1章（retry gate統一：initial admissionのみmonitor_status/RetryPolicyを使用し、attempt 2以降はopen_next_attempt()のdurable state判定に一本化） |
| MIN-R8-1〜4 | payback廃止によりMIN-R8-1・2は不要化。MIN-R8-3はtest文言修正、MIN-R8-4はscope比較のcanonical order正規化 | 24・11.4.3章 |

### 0.2 Codex Round 9指摘の対応表

| 指摘 | 内容（要約） | 対応章 |
|---|---|---|
| MAJ-R9-1 | Round 9は「initial admission（`monitor_status`×`RetryPolicy`）は新規lineage作成分岐でのみ、1回限り」（7.1・9.8.1.2章）と主張していたが、実際の`_retry_locked()`疑似コード（9.3.2章旧版）は既存lineageへの再接続経路（attempt 2以降）でも`monitor_status = self._monitor.get_status(run_id)`を無条件に呼び出しており、「attempt 2以降でMonitor lookup 0回」という構造的保証を実装が満たしていなかった（`resolve_or_create()`内部でmonitor_statusを参照しないことと、そもそもMonitor自体を呼び出さないことは別の主張であり、後者は未達成だった） | 7.1・9.3.2・9.8.1.2章（`find_existing_lineage()`／`create_new_lineage()`への二段階分離、`_retry_locked()`からのMonitor lookup条件化） |
| MAJ-R9-2 | `resolve_or_create()`の分岐(1)(2)（既存lineageへの再接続、multi-hop含む）の詳細疑似コードが、Round 3〜9を通じて一度も本書に明示されず「旧版参照」のまま残されていた（Round 9自身が25章Risk#15で「完全な保証はできない」と自認済み）。このため、既存lineage再接続時に`max_attempts`が誤って新しいsnapshot値で上書きされないことの実装レベルの保証、および新規snapshot時点での`max_attempts`値自体（型・範囲）の妥当性検証が、いずれも未規定のまま残されていた | 7.1・7.2・9.8.1章（分岐(1)(2)の全文明示、非mutation契約の明文化、snapshot時のfail-closed validation追加） |
| MIN-R9-1 | `attempt_scopes[*].steps_to_execute`が「保存された時点でcanonical order」であるという契約が、`claim()`側の比較時正規化（11.4.5.2(a)章、Round 9）にのみ暗黙に依存しており、書き込み側（`create_new_lineage()`・`open_next_attempt()`）で明示的にcanonicalizeするという契約として独立に述べられていなかった | 7.2・12章（書き込み時の明示的canonicalize、共通ヘルパー関数化） |

### 0.3 Codex Round 10指摘の対応表

| 指摘 | 内容（要約） | 対応章 |
|---|---|---|
| MAJ-R10-1 | §7.2の`create_new_lineage()`が`self._policy.should_retry(monitor_status, attempt=0)`を`max_attempts_snapshot`のvalidationより前に呼んでおり、実コード`RetryPolicy.should_retry()`（`retry_policy.py:47`）が不正な`max_attempts`に対し`TypeError`を送出しうるため、「structured `admission_rejected=True`でfail-closedする」契約を例外送出に委ねる形でしか満たせていなかった | 7.2.1章（validationを`should_retry()`より前へ移動） |
| MAJ-R10-2 | §7.2が`steps_confirmed_done=[]`を固定的にハードコードしており、11.4.3章が要求する「attempt 1は元のFAILED/TIMEOUT recordのGENUINE_SUCCESS stepを初期値として含める」契約と矛盾していた。`create_new_lineage()`は元の実行結果を受け取る入力経路を持っていなかった | 7.2.1・7.2.2章（`monitor_record`引数への変更、`compute_initial_confirmed_steps()`新設） |
| MIN-R10-1 | §11.4.5.2(a)の`claim()`が§7.3の共通ヘルパー`_canonicalize_step_order()`を実際には使わず、`canonical_order`辞書と`sorted()`をインライン構築していた（「1つの共有関数」という契約と矛盾） | 11.4.5.2(a)章（共通ヘルパーの実使用へ変更） |
| MIN-R10-2 | test #49が既存lineage再接続でのMonitor/Policy呼び出し0回をmockのcall countのみで示し、direct-root（分岐1）・membership／multi-hop（分岐2）を区別して検証していなかった | 24章項目49（分岐別の検証に拡張） |
| MIN-R10-3 | §9.3.4が`RetryLineageStoreLock`取得メソッド数を旧「6つ」のまま記載しており、§9.2の「7つ」と矛盾していた | 9.3.4章（記述修正） |
| Suggestion 2件 | test #53がvalidation-rejectionとpolicy-rejectionを区別せずに検証していた／test #50・#51が`max_attempts`フィールド単体比較に留まり、既存lineageの完全なserialized state不変性を確認していなかった | 24章項目53・50・51（区別・拡張） |

過去のCodex Round 1〜7指摘（B1〜B5、M1〜M6、N1〜N2、S1〜S3、BL-1旧・新、BL-2、MJ-1〜MJ-6（旧）、MJ-1新〜MJ-3新、MN-1〜MN-2（旧）、MN-1新、Critical／High-1／High-2／Medium（Round 4分）、H-1〜H-3／L-1（Round 5分）、B-1／M-1〜M-4／MN-1〜3（Round 6分）、M-new-1／M-new-2／MN-new-1〜3（Round 7分））は本Roundまでにすべて反映済みである（旧版0.1節参照）。

---

## 1. Background / Motivation

（Round 1〜3から変更なし。5つの発見＋Round3レビューで判明した2つの構造的欠落は維持する。詳細は旧版参照。）

**（Round 4で追加）**：Round 3独立reviewにより、Round 3自身の設計にもさらに2つの構造的欠落があることが判明した：

- **発見8**：`decide_disposition()`が「target step自体がgenuineであり、かつ`overall_success=True`であればSUCCEEDED」と判定していたため、NEWS（元の対象step）が今回genuineに成功していても、後続のPUBLISHがinterval guardによるsilent no-opであった場合（`executed=True, success=True, action_taken=False`）、`overall_success`は依然`True`（PUBLISHも`success=True`のため）となり、**disposition判定そのものがSUCCEEDEDへ誤って倒れる**ことが、実際の疑似コードのトレースにより判明した。これはtarget再算出関数（`resolve_next_target_from_engine_result()`）の欠陥よりも根が深く、その関数が呼ばれる前の時点で誤判定が確定してしまう。
- **発見9**：`RetryExecutionLock`は`RetryManager.retry()`のみを保護する設計だったが、`reconcile_all()`（`mark_terminal()`/`open_next_attempt()`を独自に呼ぶ）はこの保護の対象外であり、in-flightな`retry()`と並行して`reconcile_all()`が同一lineageを操作しうる、狭いが実在するレースウィンドウが残っていた。

本書はこの2つの発見（および付随するMJ-2新・MJ-3新・MN-1新）を解消する。

---

## 2. Scope境界（Roadmap v1.3準拠）

（Round 1〜3から変更なし）本Releaseの責務は、6.30が生成するFAILED/TIMEOUT candidateを実際にRetry Eligibilityへ安全に引き渡すための、**lineage・attempt lifecycle・durable stateの契約確立**に限定する。新規subsystem・Queue/Execution History全体の永続化・WordPress重複防止（6.32）・Scheduler統合（6.34）・無関係なrefactorは行わない。

**（Round 4で追加）**：`src/ai/`配下の各Agent（`NewsAgent`・`ReviewTriggerAgent`・`PublishTriggerAgent`）の`decide()`/`act()`ロジック自体への変更は一切行わない。11章のstep outcome classificationは、これら既存Agentが実際に返しうる`(executed, success, action_taken)`の組み合わせを**read-onlyで分類するだけ**であり、Agent側の判断ロジックを変更・拡張するものではない。

## 3. Goals

1〜6.（Round 1〜3から変更なし。旧版参照。）

7.（**Round 4で追加**）disposition判定を、`overall_success`という集約フラグ単独ではなく、pipeline全stepの実行結果（success／action_taken／skipped_reasonの組み合わせ）を明示的に分類した上で行うことを保証する。特に、ある1つのstepが今回genuineに成功しても、**別のstepが silent no-op（実行はされたが実質的に何もしていない）である限り、lineageを`SUCCEEDED`として確定しない**ことを保証する。

## 4. Non-Goals（Out of Scope）

（Round 1〜3から変更なし）Retry Queue/Retry History自体の完全永続化、WordPress側の重複防止（6.32）、Scheduler統合（6.34）、`HUMAN_REVIEW_REQUIRED`相当のterminal disposition（6.32）、6.30が確定した`main.py` Outcome Contract・Canonical Admission・Execution History atomic save契約の変更、無関係なrefactor、Multi-host並行実行、heartbeat/leaseベースの自動stale-lock解除機構、age（経過時間）のみに基づく自動reclaim。

**（Round 4で追加、Round 6で撤回）**：~~Execution Historyへの`action_taken`相当情報の追加は6.31のスコープ外とする~~。**この判断はRound 5で撤回した**（11.7.2章）。`StepExecutionRecord.action_taken`・`skip_category`の追加はRound 5・Round 6でともに6.31スコープ内の変更として採用している（14・21・22章）。本行はRound 4→5間の判断転換の記録として残す（L-1、Round 5 review指摘の解消）。

**（Round 6で明確化）**：既存`AiPublishService.run()`（`filter_unpublished()`、11.7.4章）が持つ「投稿済み記事は対象外とする」という**既存の**冪等性ガードそのものを変更・強化することは、引き続き6.31のスコープ外とする（本Releaseは既存ガードの有無を検証・記録するのみで、新規のWordPress重複防止ロジックは実装しない、6.32スコープとの境界を維持）。

---

## 5. 用語・キー概念（**Round 4で追加**）

（Round 1〜3の用語はすべて維持。以下、Round 4で新設・変更する用語のみ記載する。旧版の全用語一覧は旧版参照。）

| 用語 | 定義 |
|---|---|
| `StepOutcomeCategory`（**Round 4で新設**） | `GENUINE_SUCCESS` / `RETRYABLE_FAILURE` / `SILENT_NO_ACTION` / `INTENTIONAL_NO_ACTION` / `NOT_APPLICABLE` / `UNKNOWN`の6値。ある1 stepの`WorkflowEngineStepResult`（または`StepExecutionRecord`）を分類した結果（11章）。 |
| `classify_step_outcome()` | `WorkflowEngineStepResult`を`StepOutcomeCategory`へ分類する純関数（11.2章）。 |
| `classify_execution_history_step()` | `StepExecutionRecord`を`StepOutcomeCategory`へ分類する純関数（reconcile_all()経路用、情報量がAgentResultより少ないため一部カテゴリを判別できない、11.5章）。 |
| `_retry_locked()` / `_reconcile_all_locked()`（**Round 4で新設**） | `RetryExecutionLock`が既に取得済みであることを前提とする内部専用メソッド。公開API（`retry()`/`reconcile_all()`）からのみ呼ばれ、それ自体は`RetryExecutionLock`を取得しない（9.3章）。 |
| `retry_lineage` namespace（**Round 4で新設**） | `correlation_metadata`内の予約済みキー（`correlation_metadata["retry_lineage"]`）。retry-lineage固有の相関情報（`root_run_id`・`intended_attempt_no`・`correlation_id`）をこのnamespace配下にのみ格納する（10.3章）。 |

---

## 6. Design Decision A：Durable Store方式（Round 1〜3から変更なし）

（旧版参照。Execution Historyとは別の、`root_run_id`キーの独立したminimal durable Retry Control Store。1 lineage = 1 JSONファイル。atomic save契約は6.30の`JsonExecutionHistoryStore`を踏襲。）

---

## 7. Design Decision B：`root_run_id`/`parent_run_id`の生成・継承・再接続（Round 1〜3から変更なし、Round 9で分岐(3)にinitial admission gateを追加、Round 10でinitial admissionを完全分離）

`find_by_member_run_id()`によるmulti-hop再接続、7.4章のグローバルmembership一意性チェック（`RetryLineageStoreLock`保護下）はRound 1〜3から変更なし。**（Round 10で変更）**：旧`resolve_or_create(run_id, monitor_status)`という単一メソッド（`monitor_status`を常に引数として要求する設計）は廃止し、7.1章の`find_existing_lineage()`（分岐(1)(2)専用、`monitor_status`を一切要求しない）と7.2章の`create_new_lineage()`（分岐(3)専用、`monitor_status`を要求する）の2メソッドへ分離する。この分離自体がMAJ-R9-1の直接的な解消手段である（9.3.2章の`_retry_locked()`改訂と対）。**（Round 11で修正）**：`create_new_lineage()`の第2引数は、`WorkflowMonitorStatus`単体ではなく`WorkflowMonitorRecord`（`monitor_status`フィールドに加え、attempt 1初期化に必要な`steps`フィールドも保持する）へ変更する（7.2.1章、MAJ-R10-2対応）。

### 7.1 `find_existing_lineage()`：分岐(1)(2)、既存lineageへの再接続（**Round 10で新設・全文明示、MAJ-R9-1・MAJ-R9-2対応**）

#### 7.1.1 Round 9の欠陥の再確認

Round 9は「initial admission（`monitor_status`×`RetryPolicy`による許可判定）は分岐(3)（新規lineage作成）の内部でのみ行う」と定義したが、これは「`resolve_or_create()`という**単一の**メソッドの内部で、分岐(1)(2)の経路では判定ロジックを呼ばない」という意味に留まっていた。呼び出し元である`_retry_locked()`（9.3.2章旧版）自身は、分岐がどちらへ倒れるかに関わらず`monitor_status = self._monitor.get_status(run_id)`を**関数の先頭で無条件に**呼び出しており、その値を`resolve_or_create()`へ引数として渡していた。したがって「既存lineageへの再接続経路（attempt 2以降）ではMonitorを一切参照しない」という7.1・9.8.1章の主張は、`resolve_or_create()`内部の判定ロジックには当てはまっても、**Monitor lookupという副作用そのものの発生有無**には当てはまっていなかった（MAJ-R9-1）。また、分岐(1)(2)自体の詳細疑似コードがRound 3〜9を通じて一度も本書に明示されておらず、既存lineage再接続時に`max_attempts`が意図せず上書きされないことの保証が示されていなかった（MAJ-R9-2、旧25章Risk#15）。

#### 7.1.2 Round 10の設計：Monitor lookup前に既存lineageの有無を判定する

**採用：`find_existing_lineage(run_id)`は、`monitor_status`を一切引数に取らず、`RetryLineageStore`に対するdurable lookupのみで完結する。呼び出し元（`_retry_locked()`、9.3.2章）は、このメソッドが`None`を返した場合に限り、初めて`self._monitor.get_status(run_id)`を呼び出す。これにより、既存lineageが見つかる経路（attempt 2以降を含む）では、Monitor lookupという副作用そのものが構造的に発生し得なくなる（呼び出し元のif分岐の外側に置かれないため、条件を満たさない限りコードパスへ到達しない）。**

```python
# retry_lineage_manager.py（Round 10新設：resolve_or_create()を分離した1つめのメソッド）
def find_existing_lineage(self, run_id: str) -> RetryLineageRecord | None:
    """分岐(1)(2)専用。durable lineage membership/rootの検索のみを行う。
    monitor_status引数を持たず、WorkflowMonitor・RetryPolicyのいずれも一切参照しない
    （呼び出しさえしない）。既存lineageが見つからない場合にのみNoneを返し、
    呼び出し元（_retry_locked()）が初めてMonitor lookup（create_new_lineage()経路）へ
    進む（9.3.2章）。"""
    with self._store_lock():
        # 分岐(1)：run_id自体が既存lineageのroot_run_idと一致するか
        # （このrun_idに対してresolve_or_create/find_existing_lineageが
        # 過去に呼ばれ、既にlineageが作成済みの場合。例：retry()が同一run_idに
        # 対して複数回呼ばれる運用パス）。
        direct = self._store.get(run_id)
        if direct is not None:
            return direct

        # 分岐(2)：run_idが既存lineageのmembership（過去のいずれかのattemptの
        # 実行run_id、open_next_attempt()後にclaim()が発行したattemptのrun_id等）
        # として記録済みか、multi-hop（A→B→Cのように、あるattemptの実行結果が
        # さらに別のrun_idを生んだ場合）を含めて検索する（10.3.3章の
        # find_by_member_run_id()と同一のメカニズムを再利用する）。
        member_root_run_id = self._find_root_by_member_run_id(run_id)
        if member_root_run_id is not None:
            record = self._store.get(member_root_run_id)
            if record is not None:
                return record
            # invariant violation：membership indexにrootが記録されているにも
            # かかわらず、対応するRetryLineageRecordが実在しない（破損）。
            # fail-closed：既存lineageとして扱わず、Noneを返す。呼び出し元は
            # 通常の新規lineage作成経路（create_new_lineage()）へフォールバックする。
            # これにより新しいlineageが二重に作られるリスクはあるが、7.2章
            # （Architecture Amendment、Code Review Major#3対応）のグローバル
            # membership一意性チェックがその場で検出しfail-closedする。
            return None

        # 分岐(1)(2)いずれにも該当しない：この呼び出し元にとって完全に新規のrun_id。
        return None
```

**このメソッド自身はいかなるフィールドも書き換えない（read-only、`RetryLineageStoreLock`は`self._store.get()`の一貫性保護のためだけに取得する）。** `max_attempts`を含む`RetryLineageRecord`の全フィールドは、`find_existing_lineage()`が返す既存レコードのまま呼び出し元へ渡され、この経路を通過するだけでは一切変更されない——**分岐(1)(2)（既存lineage再接続）が`max_attempts`を絶対に変更しないという契約は、`find_existing_lineage()`が`save()`を一度も呼ばないという構造そのものによって保証される**（MAJ-R9-2対応）。

### 7.2 `create_new_lineage()`：分岐(3)、新規lineage作成とinitial admission gate（**Round 10で改訂（旧7.1章を分離・拡張）、MAJ-R9-2・MIN-R9-1対応。Round 11でvalidation順序とattempt 1初期scopeの導出元を修正、Codex Round 10 review Major#1・Major#2対応**）

#### 7.2.0 Codex Round 10 reviewの指摘再確認

Round 10のCodex独立reviewにより、本章の疑似コードに2つのMajor指摘を受けた：

- **Major#1（max_attempts validation順序）**：Round 10は`self._policy.should_retry(monitor_status, attempt=0)`を`max_attempts_snapshot`のvalidationより**前**に呼んでいた。実コード`RetryPolicy.should_retry()`（`src/retry_engine/retry_policy.py:47`）は内部で`attempt < self.max_attempts`という比較を行うため、`max_attempts`が`"3"`（文字列）や`None`のような非intの場合、`should_retry()`自身が`TypeError`を送出してしまい、「不正値はstructured `admission_rejected=True`でfail-closedする」という本章の契約を、例外に運用を委ねる形でしか満たせていなかった。
- **Major#2（attempt 1 scope初期化の入力欠落）**：Round 10は`initial_steps_to_execute = compute_steps_to_execute(steps_confirmed_done=[])`と`steps_confirmed_done=[]`をハードコードしていたが、これは11.4.3章が要求する「attempt 1のsteps_confirmed_doneは`[]`ではなく、元のFAILED/TIMEOUT recordから`classify_execution_history_step()`でGENUINE_SUCCESSと分類できたstepを初期値として含める」という契約と矛盾していた。`create_new_lineage(run_id, monitor_status)`は元の実行record（またはそこから導出されたstep結果）を受け取る入力経路を一切持っておらず、11.4.3章の契約を実装可能な形で満たせていなかった。

#### 7.2.1 Round 11の設計：validation順序の入れ替えと`monitor_record`からのattempt 1初期化

**採用：**
1. **`max_attempts_snapshot`のvalidationを、`self._policy.max_attempts`を読み取った直後、`should_retry()`を呼ぶ**前**に行う。** これにより、不正な`max_attempts`は`should_retry()`へ一切渡らず、必ず`create_new_lineage()`自身が構造化された`admission_rejected=True`として検出する（例外送出には一切依存しない）。
2. **`create_new_lineage()`の第2引数を`monitor_status: WorkflowMonitorStatus`から`monitor_record: WorkflowMonitorRecord`へ変更する。** `WorkflowMonitorRecord`（`workflow_monitor_record.py:24-35`）は既に`monitor_status: WorkflowMonitorStatus`フィールドに加えて`steps: list[StepExecutionRecord]`（元の`WorkflowExecutionRecord.steps`のコピー、`workflow_monitor.py:67`）を保持している——新しい依存を追加する必要はなく、9.3.2章の`_retry_locked()`が既に`self._monitor.get_status(run_id)`から取得済みの値をそのまま渡すだけでよい。
3. **attempt 1のscopeは、`monitor_record.steps`から`compute_initial_confirmed_steps()`（新設、7.2.2章）で導出した`initial_confirmed_steps`を用いて構築する。** `steps_confirmed_done=[]`のハードコードは廃止する。

```python
# retry_lineage_manager.py（Round 11改訂：validation順序の入れ替え、
# monitor_record引数への変更、Codex Round 10 review Major#1・Major#2対応）
@dataclass
class CreateNewLineageResult:
    lineage: RetryLineageRecord | None
    admission_rejected: bool = False
    reason: str | None = None

def create_new_lineage(
    self, run_id: str, monitor_record: WorkflowMonitorRecord,
) -> CreateNewLineageResult:
    with self._store_lock():
        # レース確認：9.3章のRetryExecutionLockにより、_retry_locked()の呼び出しは
        # プロセス全体で常に単一直列であることが既に保証されている（同時に2つの
        # _retry_locked()が走ることはない）。したがってfind_existing_lineage()が
        # Noneを返した直後にこの位置で改めて他プロセスが同一run_idのlineageを
        # 作成しているという古典的なTOCTOUレースは、9.3章の排他境界の外側
        # （single-host前提を破る場合）を除き構造的に発生しない。9.1章のsingle-host
        # 限定はこの前提の一部である。

        # Round 11で移動（Codex Round 10 review Major#1対応）：max_attempts snapshot
        # のvalidationを、should_retry()を呼ぶより前に行う。RetryPolicy.should_retry()
        # は内部でattempt < self.max_attemptsという比較を行うため（retry_policy.py:47）、
        # max_attemptsが整数でない場合should_retry()自身がTypeErrorを送出してしまい、
        # 「structured admission_rejected=Trueでfail-closedする」という本章の契約を
        # 満たせない。この順序入れ替えにより、不正なmax_attemptsはRetryPolicy.
        # should_retry()へ一切渡らず、必ずここで検出される
        # （should_retry()の呼び出し回数が0のまま構造化rejectionが返ることを、
        # 24章項目53でvalidation-rejectionとpolicy-rejectionを区別して検証する）。
        max_attempts_snapshot = self._policy.max_attempts   # 9.8.1章：作成時点でのみsnapshot
        if not isinstance(max_attempts_snapshot, int) or isinstance(max_attempts_snapshot, bool) \
                or max_attempts_snapshot < 0:
            # bool型除外：isinstance(x, bool)はisinstance(x, int)を満たしてしまう
            # Pythonの罠を明示的に除外する。int以外（str/None等）・負値のいずれも、
            # ここでself._policy.should_retry()を一度も呼び出すことなく
            # fail-closedする。
            return CreateNewLineageResult(
                lineage=None, admission_rejected=True,
                reason=f"invalid max_attempts snapshot value: {max_attempts_snapshot!r} "
                       f"(must be a non-negative int, not bool). Refusing to create lineage "
                       f"(fail-closed; validation-rejected, should_retry() was not called).",
            )

        if not self._policy.should_retry(monitor_record.monitor_status, attempt=0):
            # max_attempts_snapshotが妥当な値であることを既に確認した上での、
            # 通常のpolicy判定によるrejection（monitor_statusが対象statusでない、
            # またはmax_attempts_snapshot==0）。validation-rejectionとはreason
            # 文字列・呼び出し経路（should_retry()を実際に1回呼んだ上でのFalse）
            # の両方で区別される（24章項目53）。次回retry()呼び出し時（Read Before
            # Retryパターンにより新しいmonitor_statusで）再評価される。
            return CreateNewLineageResult(
                lineage=None, admission_rejected=True,
                reason=self._skip_reason(monitor_record.monitor_status, 0),
            )

        # Round 11で新設（Codex Round 10 review Major#2対応、11.4.3章の契約を
        # 実装可能にする）：attempt 1のsteps_confirmed_doneを、元のFAILED/TIMEOUT
        # WorkflowExecutionRecordのstep実行結果（monitor_record.steps）から導出する。
        # compute_initial_confirmed_steps()（7.2.2章）はGENUINE_SUCCESSと分類できた
        # stepのみを返す——NOT_REACHED/RETRYABLE_FAILURE/SILENT_NO_ACTION/
        # INTENTIONAL_NO_ACTION/UNKNOWN（legacy record、action_taken未設定等を含む）
        # はいずれも含まれない。
        # Architecture Amendment（Code Review Major#3対応）：グローバルmembership
        # 一意性チェック。find_existing_lineage()は通常このrun_idに対する既存lineageを
        # 検出済みのはずだが（呼び出し順序上、create_new_lineage()の前に必ず呼ばれる、
        # 9.3.2章）、membership index破損時のフォールバック（7.1章、25章項目16）では
        # find_existing_lineage()がNoneを返した後この経路へ到達しうる。同一
        # store_lock（9.2章）の内側で、これから作成するrun_idが既存のいずれかの
        # lineageのroot_run_idまたはmembershipとして既に記録されていないかを
        # 再検証する。検出した場合は新規lineageを作成せずfail-closedで拒否する
        # （自動マージ・自動修復は行わない、破損したmembership indexの手動修復を
        # 運用者に委ねる、18章診断対象）。
        for existing_record in self._store.list_all():
            if existing_record.root_run_id == run_id or any(
                entry.run_id == run_id for entry in existing_record.membership
            ):
                return CreateNewLineageResult(
                    lineage=None, admission_rejected=True,
                    reason=(
                        f"global membership uniqueness violation: run_id={run_id} is already "
                        f"recorded under root_run_id={existing_record.root_run_id} (likely "
                        f"membership index corruption, 25章項目16). Refusing to create a "
                        f"duplicate lineage (fail-closed; validation-rejected, no auto-repair)."
                    ),
                )

        initial_confirmed_steps = compute_initial_confirmed_steps(monitor_record.steps)
        initial_steps_to_execute = compute_steps_to_execute(initial_confirmed_steps)
        # Round 10から変更なし（MIN-R9-1対応）：steps_to_executeは保存する時点で
        # 明示的にcanonicalizeする（7.3章の共通ヘルパー）。
        initial_scope = RetryAttemptExecutionScope(
            attempt_no=1,
            steps_confirmed_done_before=list(initial_confirmed_steps),
            steps_to_execute=_canonicalize_step_order(initial_steps_to_execute),
            determined_at=now(),
        )
        record = RetryLineageRecord(
            root_run_id=run_id, parent_run_id=None, latest_run_id=run_id,
            attempt_count=0, max_attempts=max_attempts_snapshot,
            next_attempt_ordinal=1, phase=RetryLineagePhase.READY_ELIGIBLE,
            terminal_disposition=None, next_eligible_at=None, owner_token=None,
            steps_confirmed_done=initial_confirmed_steps, membership=[...], transition_history=[...],
            attempt_scopes=[initial_scope],
            created_at=now(), updated_at=now(),
        )
        self._store.save(record)
        return CreateNewLineageResult(lineage=record, admission_rejected=False)
```

#### 7.2.2 `compute_initial_confirmed_steps()`：attempt 1初期confirmed setの導出（**Round 11で新設、Codex Round 10 review Major#2対応**）

```python
# retry_target_resolution.py（Round 11新設）
def compute_initial_confirmed_steps(steps: list["StepExecutionRecord"]) -> list[str]:
    """元のFAILED/TIMEOUT実行のStepExecutionRecord列（WorkflowMonitorRecord.steps、
    実体はWorkflowExecutionRecord.stepsのコピー）から、GENUINE_SUCCESSと分類できた
    stepのみをattempt 1のsteps_confirmed_done初期値として返す。

    classify_execution_history_step()（11.7.3章）を再利用し、同期パス
    （11.4.3章のcompute_newly_confirmed()）と同一の「GENUINE_SUCCESSのみが
    confirmed化される」契約を保つ。NOT_APPLICABLE（NOT_REACHED等）・
    RETRYABLE_FAILURE・SILENT_NO_ACTION・INTENTIONAL_NO_ACTION・UNKNOWN
    （legacy record、action_taken未設定等を含む、11.7.2章のfail-closed契約）は、
    いずれもGENUINE_SUCCESSではないため自動的に除外される——本関数自身は
    追加のfail-closedロジックを持たず、classify_execution_history_step()の
    既存の閉集合判定にそのまま従う（新しい判定ロジックの二重実装を避ける）。
    """
    return [
        s.step for s in steps
        if classify_execution_history_step(s) == StepOutcomeCategory.GENUINE_SUCCESS
    ]
```

`compute_newly_confirmed()`（11.4.3章、同期パス用、`WorkflowEngineResult`から`classify_step_outcome()`経由でGENUINE_SUCCESS stepを抽出する）と`compute_initial_confirmed_steps()`（本関数、reconcile相当の入力である`list[StepExecutionRecord]`から`classify_execution_history_step()`経由で抽出する）は、入力の型が異なるだけで「GENUINE_SUCCESSのみを合成対象とする」という契約は完全に同一である。

**snapshot validationの契約（Human Gate対象、26章）**：`max_attempts_snapshot`が整数でない、`bool`型（`isinstance(x, bool)`は`isinstance(x, int)`を満たしてしまうPythonの罠を明示的に除外する）、または負値の場合、新規lineageは一切作成されない。**（Round 11で明確化）**このvalidationは`should_retry()`を呼び出す**前**に行われるため、`RetryPolicy.should_retry()`が不正な`max_attempts`により例外を送出することは構造的にない。この経路は「initial admission gateがmonitor_status/RetryPolicyにより許可判定を行う」経路の一部として扱い、admission_rejectedと同じ`RetryOutcome.SKIPPED`へ合流させる（9.3.2章）が、`self._policy.should_retry()`の呼び出し回数（validation-rejectionでは0、policy-rejectionでは1）によって内部的には区別可能である（24章項目53）。既存lineageの再接続（7.1章）ではこのvalidationは行われない——`max_attempts`は作成時に一度検証されて以降、そのlineageの生涯を通じて再検証も再snapshotもされない（9.8章）。

### 7.3 Canonical order正規化ヘルパー（**Round 10で新設、MIN-R9-1対応**）

**採用：`steps_to_execute`のcanonical order正規化ロジックを、書き込み側（7.2章`create_new_lineage()`・12章`open_next_attempt()`）と比較側（11.4.5.2(a)章`claim()`）の3箇所で共通の1つの関数として定義し、実装を重複させない。**

```python
# retry_target_resolution.py（Round 10新設）
def _canonicalize_step_order(steps: list[str]) -> list[str]:
    """ALL_WORKFLOW_ENGINE_STEPSの列挙順（Workflow canonical order）へ正規化する。
    compute_steps_to_execute()の戻り値は既にこの順序で構築される不変条件を持つ
    （11.4.3章）が、このヘルパーはdefense-in-depthとして、書き込み直前・比較直前の
    いずれでも独立に適用できる、順序破損に対する冪等な正規化操作として提供する。"""
    canonical_order = {s.value: i for i, s in enumerate(ALL_WORKFLOW_ENGINE_STEPS)}
    return sorted(steps, key=lambda s: canonical_order[s])
```

`RetryAttemptExecutionScope.steps_to_execute`は、**書き込まれる箇所（`create_new_lineage()`のattempt 1用scope、`open_next_attempt()`のattempt 2以降用scope）のいずれにおいても、必ずこのヘルパーを通した後の値が保存される**。これにより「stored authoritative scope自体がcanonicalである」ことが、`compute_steps_to_execute()`の内部実装規約への暗黙の依存ではなく、書き込み経路そのものの構造的契約として保証される（MIN-R9-1対応）。`claim()`側の比較時正規化（11.4.5.2(a)章）は、この契約が破られていない限り常に無操作（already sorted）になるが、`stored_scope`が万一過去のロジックで書かれた既存データ・手動修復後のデータ等、正規化されていない値を含む場合への防御として引き続き維持する。**（Round 11で修正、MIN-R10-1対応）**：Round 10時点では`claim()`（11.4.5.2(a)章）がこの`_canonicalize_step_order()`を実際には呼ばず、独自に`canonical_order`辞書と`sorted()`をインライン構築しており、本節が謳う「3箇所で共通の1つの関数」という契約に反していた。Round 11で`claim()`側の実装をこの共通ヘルパー呼び出しへ置き換え、契約と実装を一致させた。

---

## 8. Design Decision C：`RetrySchedulerSource`のread-only性維持とCLAIMの配置（Round 1〜3から変更なし）

（旧版参照。CLAIMは`RetryManager.retry()`の先頭（9.3章の`_retry_locked()`内）で行う。）

---

## 9. Design Decision G：Concurrency & Locking Contract（**9.3・9.4をRound 4で全面改訂**）

### 9.1 Concurrency Scope Decision（Round 1〜3から変更なし）

6.31がサポートする並行実行モデルを、明示的に「single-host（1台のマシン上で完結する複数プロセス・複数呼び出し経路）」に限定する。Multi-hostはOut of Scope。

### 9.2 `RetryLineageStoreLock`：read-check-write全体を保護するOS-backed排他原語（Round 1〜3から変更なし）

`RetryLineageStore`の個々のmutation操作は`RetryLineageStoreLock`（短時間・タイムアウト付きリトライ、既存`RetryRuntimeLock`と同型の例外安全な実装）で保護する。`peek()`・`diagnose_stuck()`は対象外（read-only維持）。

**（Round 4で明確化、9.3.5章の帰結として確定。Round 10で対象メソッドを更新、7.1・7.2章対応）**：`RetryLineageStoreLock`を取得するコードパスは、`claim()`・`release_claim()`・`mark_execution_started()`・`mark_terminal()`・`open_next_attempt()`・`find_existing_lineage()`・`create_new_lineage()`の**7つのみ**であり、これらは**すべて例外なく**9.3章の`RetryExecutionLock`が既に取得された状態（`_retry_locked()`または`_reconcile_all_locked()`の内部）からのみ呼び出される。`RetryLineageStoreLock`を単独で（`RetryExecutionLock`なしで）取得するコードパスは存在しない。`find_existing_lineage()`はread-only（`self._store.get()`の一貫性保護のためだけの取得）だが、`peek()`・`diagnose_stuck()`とは異なりRetry gateの一部として呼ばれるため、本節の対象コードパスに含める。

### 9.3 `RetryExecutionLock`：`retry()`と`reconcile_all()`双方を保護する単一の排他境界（**Round 4で全面改訂、BL-1新・MJ-1新対応**）

#### 9.3.1 Round 3の欠陥の再確認

Round 3は`RetryManager.retry()`のみを`RetryExecutionLock`で保護していた。しかし`reconcile_all()`（`mark_terminal()`／`open_next_attempt()`を独自に呼ぶ）はこの保護の対象外だったため、以下のレースが理論上成立した：

- 呼び出し元1：`retry()`が`.run()`から戻り、`mark_terminal()`を呼ぼうとする直前（詳細で正確な`WorkflowEngineResult`を保持）。
- 呼び出し元2：独立に動作している`reconcile_all()`が、同じlineageを`phase==EXECUTION_STARTED`として発見し、`WorkflowMonitor`の粗い状態のみから`mark_terminal()`を先に呼んでしまう。

両呼び出しとも`RetryLineageStoreLock`で個々の書き込み自体は保護されるため**データ破損は起きない**が、`mark_terminal()`のprecondition（`phase==EXECUTION_STARTED`）チェックにより、後着の呼び出しはack=Falseで拒否される。この時、**より正確な情報を持つ`retry()`側の呼び出しが後着になった場合、その正確な結果が静かに捨てられる**という劣化が起こりうる（BL-1新）。

#### 9.3.2 Round 4の設計：唯一のグローバル境界としての`RetryExecutionLock`

**採用：`RetryExecutionLock`は、`RetryManager.retry()`（dry_runでない場合）と`RetryLineageManager.reconcile_all()`の**両方**にとって唯一の実行時排他境界とする。いずれの公開APIも、内部の実処理を行う前に必ず同一の`RetryExecutionLock`（同一lockファイル）を取得する。**

**Public entry point / private locked helperの分離**（二重取得の構造的防止）：

```python
class RetryManager:
    def retry(self, run_id: str, attempt: int = 1, dry_run: bool = False) -> RetryResult:
        """公開API。RetryExecutionLockを取得し、_retry_locked()へ委譲する。
        RetryExecutionLockを取得する経路はこのメソッドのみとする。"""
        if dry_run:
            return self._dry_run_retry(run_id)  # peek()のみ、lock不要
        try:
            with RetryExecutionLock(self._execution_lock_path):
                return self._retry_locked(run_id, attempt)
        except RetryExecutionLockBusyError:
            return RetryResult(
                ..., outcome=RetryOutcome.SKIPPED,
                reason="execution lock busy: another retry()/reconcile_all() is in flight "
                       "(single-flight by design, 9.3.3節)",
            )

    def _retry_locked(self, run_id: str, attempt: int) -> RetryResult:
        """RetryExecutionLockが既に取得済みであることを前提とする内部専用メソッド。
        このメソッド自身はRetryExecutionLockを取得しない（二重取得禁止）。
        claim() -> mark_execution_started()（hook経由） -> mark_terminal()の
        全シーケンスをここで実行する。呼び出し元はretry()のみ。

        （Round 10で全面改訂、MAJ-R9-1対応。Round 11で変数名を実体に合わせて改名、
        Codex Round 10 review Major#2対応）：initial admission（monitor_status×
        RetryPolicy）だけでなく、Monitor lookupという副作用そのものを、既存lineage
        再接続経路（attempt 2以降）から構造的に排除する。Round 9まではresolve_or_create()
        内部の判定ロジックこそ分岐(3)限定だったが、呼び出し元のこのメソッドが
        self._monitor.get_status(run_id)を無条件に（if分岐の外側で）呼んでいたため、
        Monitor lookup自体は既存lineage再接続でも毎回発生していた（MAJ-R9-1）。
        Round 10は、find_existing_lineage()（7.1章、monitor_status不要）を先に呼び、
        既存lineageが見つかった場合はMonitor取得コード自体へ到達しない構造へ変更した。
        Round 11では、この分岐で受け取る戻り値が実際には`WorkflowMonitorRecord`
        （`monitor_status: WorkflowMonitorStatus`フィールドに加え、`steps: list[StepExecutionRecord]`
        も保持する、workflow_monitor_record.py:24-35）であることに合わせ、変数名を
        `monitor_status`から`monitor_record`へ改名する。`create_new_lineage()`（7.2章）が
        attempt 1のsteps_confirmed_done初期値を導出するために`monitor_record.steps`を
        必要とするため（旧来`monitor_status`という変数名のままでは`.steps`を保持している
        ことが読み手に伝わらなかった）。"""
        existing = self._lineage.find_existing_lineage(run_id)  # RetryLineageStoreLock使用。
                                                                  # WorkflowMonitor・RetryPolicyは
                                                                  # 一切参照しない（7.1章）。
        if existing is not None:
            # 分岐(1)(2)：既存lineageへの再接続。self._monitor.get_status(run_id)は
            # このifブロック内では一度も呼ばれない——コードパス上到達しないため、
            # attempt 2以降でMonitor lookup 0回であることが構造的に保証される
            # （MAJ-R9-1の直接解消。24章項目49で呼び出し回数0を直接検証する）。
            lineage = existing
        else:
            # 分岐(3)：この run_id にとって完全に新規。ここで初めてMonitorを取得する。
            monitor_record = self._monitor.get_status(run_id)   # Read Before Retry（6.30から継承）。
                                                                  # WorkflowMonitorRecordを返す
                                                                  # （workflow_monitor.py:37-42）。
            if monitor_record is None:
                return RetryResult(..., outcome=RetryOutcome.NOT_FOUND, reason=f"run_id={run_id} not found.")

            created = self._lineage.create_new_lineage(run_id, monitor_record)  # RetryLineageStoreLock使用
            if created.admission_rejected:
                # 新規lineageの作成自体が見送られた（max_attempts snapshot validation失敗、
                # またはmonitor_status不適格／max_attempts=0、7.2章）。claim()は一切呼ばれない。
                return RetryResult(..., outcome=RetryOutcome.SKIPPED, reason=created.reason)
            lineage = created.lineage

        claim = self._lineage.claim(lineage.root_run_id)       # RetryLineageStoreLock使用
        if not claim.acknowledged:
            return RetryResult(..., outcome=RetryOutcome.SKIPPED, reason=claim.reason)
        # should_retry(monitor_status, ...)の呼び出しはここには存在しない。
        # attempt 2以降の許可判定はopen_next_attempt()（9.8.1章）が既にdurable state
        # のみで行い、claim()はREADY_ELIGIBLE/invariant検証のみを行う（11.4.5.2(a)章）。
        ...（10・11章：hook経由のmark_execution_started、.run()実行、
             decide_disposition()、mark_terminal()）...


class RetryLineageManager:
    def reconcile_all(self, resolve_status_fn) -> ReconcileSummary:
        """公開API。RetryExecutionLockを取得し、_reconcile_all_locked()へ委譲する。"""
        try:
            with RetryExecutionLock(self._execution_lock_path):
                return self._reconcile_all_locked(resolve_status_fn)
        except RetryExecutionLockBusyError:
            return ReconcileSummary(
                skipped=True,
                reason="execution lock busy: retry() is in flight; "
                       "reconciliation deferred to next run_once() cycle (mutation不実行)",
            )

    def _reconcile_all_locked(self, resolve_status_fn) -> ReconcileSummary:
        """RetryExecutionLockが既に取得済みであることを前提とする内部専用メソッド。
        (a) phase==EXECUTION_STARTEDの解決、(b) phase==TERMINAL(retryable)の
        open_next_attempt()、をこの中で行う（16章）。呼び出し元はreconcile_all()のみ。"""
        ...
```

`RetryExecutionLock`自体の実装（`os.open(O_CREAT|O_EXCL)`、即時fail-closed、リトライなし、PID:timestamp診断情報、自動削除なし）はRound 3から変更しない。

#### 9.3.3 これにより解消されること

- **`reconcile_all()`は、`retry()`が`RetryExecutionLock`を保持している間、`_reconcile_all_locked()`へ一切到達できない**（`RetryExecutionLockBusyError`により即座にskipされる）。逆も同様。**したがって、9.3.1節のレースは構造的に発生し得なくなる**（BL-1新・MJ-1新の解消）。
- **「通常完了パスとreconcile pathが同一のmutation APIを使う」（12章）という主張が、名目上の一致だけでなく、実際に排他された単一の直列制御フローの上で成立するようになる**（MJ-2旧で指摘された懸念の解消）。
- `reconcile_all()`が busy によりスキップされた場合、**一切のmutationを試みない**（`_reconcile_all_locked()`へ到達しないため、`RetryLineageStoreLock`すら取得しない）。次回`run_once()`サイクルで再試行される（16章）。

#### 9.3.4 Lock Ordering（**Round 4で新設**）

**唯一許可される取得順序：`RetryExecutionLock` → `RetryLineageStoreLock`。逆順（`RetryLineageStoreLock`を先に取得してから`RetryExecutionLock`を取得する）は、いかなるコードパスにおいても行わない。**

9.2章で明記したとおり、`RetryLineageStoreLock`を取得するコードパスは`_retry_locked()`／`_reconcile_all_locked()`の内部からのみ呼ばれる7メソッド（`claim()`・`release_claim()`・`mark_execution_started()`・`mark_terminal()`・`open_next_attempt()`・`find_existing_lineage()`・`create_new_lineage()`、9.2章）に限定される。**（Round 11で修正、MIN-R10-3対応。Round 10で`find_existing_lineage()`・`create_new_lineage()`が追加され6→7になった後、本節の記述が更新されず「6メソッド」のまま矛盾していた）**この7メソッドが`RetryExecutionLock`を自ら取得することはない（二重取得禁止、9.3.2節のpublic/private分離により構造的に保証される）。したがって、**`RetryExecutionLock`を取得していない状態で`RetryLineageStoreLock`が取得されることはなく、また`RetryLineageStoreLock`を保持したまま新たに`RetryExecutionLock`を取得しようとする経路も存在しない**。2つのロックが同時に必要になるのは常に「外側に`RetryExecutionLock`、内側に`RetryLineageStoreLock`」という単一のネスト順序のみであり、逆転による古典的なlock-order-inversion型デッドロックのリスクは構造的に排除される。

#### 9.3.5 Nested / Reentrant呼び出しに対する防御

`RetryExecutionLock`は`os.open(O_CREAT|O_EXCL)`ベースであり、**同一プロセス内であっても2回目の取得はブロックせず即座に失敗する**（誰が取得したかを区別しない）。したがって、仮に将来何らかの経路で`_retry_locked()`の内部から（直接・間接を問わず）再度`retry()`（公開API）を呼び出すコードが追加された場合、それは**ハング（真のデッドロック）ではなく即座に`RetryExecutionLockBusyError`が送出される形で顕在化する**。

**採用：`_retry_locked()`・`_reconcile_all_locked()`のいずれも、内部から`retry()`／`reconcile_all()`（公開API）を呼び出さないことを設計上の不変条件とする。** 現行設計（10章のhookクロージャ、11章のdisposition決定ロジック）は、いずれも`RetryLineageManager`の個別mutationメソッド（`claim`/`mark_execution_started`/`mark_terminal`等）を直接呼ぶのみであり、公開API（`retry()`/`reconcile_all()`）を再帰的に呼び出す経路を一切持たない。この不変条件は24章のregressionテストで確認する（コードレビュー観点のcode-path監査を実装フェーズで実施する旨を26章Gate Checklistへ追加する）。

### 9.4 Manual Stale Lock Recovery Procedure（**Round 4で改訂、MN-1新対応：trust boundaryとして再定義**）

`RetryLineageStoreLock`・`RetryExecutionLock`いずれについても、クラッシュにより残存したlockファイルの復旧手順は以下のとおりである。**この手順は「構造的に安全であることが証明された」機構ではなく、single-host運用における明示的なoperational trust boundaryであり、運用者が手順を正しく実施することに依存する。** 以下の残存リスクを許容した上での運用手順として位置づける。

1. lockファイルの内容（`PID:timestamp`、診断目的で記録済み）からPIDを確認する。
2. **同一ホスト上で**、そのPIDが**現在生存していないこと**を確認する。
3. PIDの生存有無が確認できない場合（確証が持てない場合）は、削除してはならない。疑わしい場合は削除しない側に倒す。
4. 非生存が確認できた場合に**限り**、運用者がlockファイルを手動削除できる。
5. いかなる自動削除・自動reclaimロジックも実装しない。ageのみに基づく削除は行わない。Heartbeat/Lease等の追加機構も6.31では導入しない（9.3.4章旧、Round 3の却下理由を維持）。

**（Round 4で追加、MN-1新対応）残存リスクの明示**：

- **PID再利用**：ホスト再起動等により、記録されたPIDが別の（無関係な）現在生存中プロセスへ再利用されている場合、運用者は「まだ生存している」と誤って判断し、削除を見送る可能性がある。この誤りは**安全側**（削除を拒否する方向）に倒れるため、危険な誤判定（実際には生存しているプロセスのlockを削除してしまう）には直結しない。
- **破損・不正確なlockファイル内容**：lockファイルの内容が何らかの理由で破損・改変されていた場合、運用者が誤ったプロセスを検証してしまうリスクは残る。この復旧手順は、lockファイル自体の完全性を検証する機構を持たない。
- **CLAIMEDフェーズ単体には照合可能な実行証跡が存在しない**：`RetryExecutionLock`の手動復旧後、`claim()`が発見する残存`CLAIMED`状態のlineageは、`mark_execution_started()`未達のため`latest_run_id`に対応する実行がまだ存在しない場合がある。この場合、Execution Historyとの突合による追加検証は行えない（そもそも突合対象が存在しない）。`claim()`の自動stale判定（9.3.3節）は、**「`RetryExecutionLock`が正しく手動復旧された＝生存プロセスは存在しない」という、この手順自体への信頼にのみ依拠する**。

これらのリスクは、本Releaseが単一の"trust boundary"として明示的に受容するものであり、Human Gateでの承認事項とする（26章）。

### 9.5〜9.8（Round 1〜3から変更なし）

- **9.5 Attempt Consumption Point**：EXECUTION_STARTEDのdurable ack成功時点。
- **9.6 Owner Token**：診断専用、CASの根拠にしない。
- **9.7 `retry_attempt`の非authoritative性**：`RetryResult`へ`requested_attempt_argument`/`authoritative_attempt_no`/`attempt_argument_mismatch`を記録。
- **9.8 max_attempts境界値**：**（Round 9で全面改訂、MAJ-R8-1〜3対応）**`max_attempts`はlineage作成時に`RetryPolicy.max_attempts`から`RetryLineageRecord.max_attempts`へsnapshotされるdurable値であり、以後そのlineageの生涯を通じて不変（`RETRY_MAX_ATTEMPTS`環境変数の運用中変更は、既存lineageへ遡及せず新規lineageにのみ適用される）。retry可否判定の全体設計は9.8.1章で定義する。挙動変更（`max_attempts=1`で実効retry回数が0回→1回等、`NOT_ACTIONED`が以後budgetを消費するようになったこと）はHuman Gate承認事項（26章）。

（9.5〜9.7は詳細を旧版参照。）

### 9.8.1 Retry Gate統一契約：initial admission／attempt accounting／`max_attempts` snapshot（**Round 9で全面改訂、MAJ-R8-1〜3対応**）

#### 9.8.1.1 Round 8の欠陥の再確認

Round 8は`monitor_status`という未定義変数を`open_next_attempt()`から除去したが、代わりに`max_attempts`という**同種の未定義変数**（`self.`修飾も引数化もされていない裸の識別子）を残し、かつ「`RetryLineageRecord`に永続化されたdurable state」と誤って性質付けていた（MAJ-R8-1、実際は`RetryPolicy`という設定値、`src/retry_engine/retry_policy.py:34-47`）。さらに、「`_retry_locked()`の`should_retry(monitor_status, ...)`呼び出しはattempt 1のみを担当する」という記述は、`claim()`が`open_next_attempt()`後のattempt 2以降でも必ず呼ばれるという設計そのものと矛盾しており（MAJ-R8-3）、`open_next_attempt()`（durable state判定）と`_retry_locked()`（monitor_status判定）という**2つの独立した、意味論の異なる許可ゲート**が並存し、相互に矛盾しうる状態のまま残されていた。加えて、`NOT_ACTIONED`のpayback補正（`attempt_count`を`-1`し続ける）は、あるstepが恒久的に`NOT_ACTIONED`を返し続ける場合、budgetを一切消費しないまま`attempt_no`／`attempt_scopes`／`transition_history`を無制限に増やし続けるliveness問題を構造的に許容していた（MAJ-R8-2）。

#### 9.8.1.2 Round 9〜10の設計：単一のRetry Gate契約（**Round 10でMonitor lookupの副作用も含め完全分離、MAJ-R9-1対応**）

**採用：retry可否判定を、以下の3つの原則に基づき単一の一貫した契約へ統一する。**

1. **`max_attempts`はlineage作成時に一度だけsnapshotされ、`RetryLineageRecord.max_attempts`としてdurable化する（13章）。** 以後そのlineageの判定はすべて`record.max_attempts`（snapshot値）を参照し、`RetryPolicy.max_attempts`（現在の設定値）を都度参照することはない。運用中に`RETRY_MAX_ATTEMPTS`が変更されても、既存lineageのbudget判定は作成時点の値のまま不変であり、新規に作成されるlineageにのみ新しい値が適用される。**（Round 10で追加）**snapshot値は整数かつ`>=0`であることを`create_new_lineage()`が検証し、不正値はlineage作成自体をfail-closedで拒否する（7.2章）。
2. **`monitor_status`／`RetryPolicy.should_retry()`による判定（対象status × budget）は、新規lineage作成分岐（7.2章、`create_new_lineage()`）の内部でのみ、一度だけ行う。** これを**initial admission gate**と呼ぶ。既存lineageへの再接続（分岐(1)(2)、7.1章`find_existing_lineage()`）、および`open_next_attempt()`によるattempt 2以降の再オープンでは、この判定を二度と行わない。**（Round 10で強化、MAJ-R9-1対応）**この分離は判定ロジックの呼び出し有無だけでなく、`WorkflowMonitor.get_status()`という**Monitor lookupという副作用そのもの**の呼び出し有無にも及ぶ——呼び出し元`_retry_locked()`（9.3.2章）が、`find_existing_lineage()`の結果に基づき、既存lineageが見つかった場合はMonitor取得コードへ到達しないコードパス構造を取ることで、attempt 2以降でのMonitor lookup回数が構造的に0であることを保証する。
3. **`open_next_attempt()`が、attempt 2以降の唯一の許可判定（durable stateのみに基づく）を担う。** `claim()`はREADY_ELIGIBLE／invariant検証のみを行い、budgetやmonitor_statusの判定は一切行わない（11.4.5.2(a)章）。

**これにより、initial admission（lineage作成時、1回限り）とsubsequent admission（`open_next_attempt()`、attempt 2以降）が、判定ロジックだけでなくMonitor/RetryPolicyへのアクセスという副作用のレベルでも完全に分離され、二重ゲート・相互矛盾の可能性が構造的に排除される。** ある1つのlineageのある1つの時点で、budget/statusに関する判定を行う経路——そしてその判定の前提となるMonitor lookupという副作用が発生する経路——は常にただ1つしか存在しない。

**判定式（`open_next_attempt()`、attempt 2以降）**：

```
is_retryable(record) :=
    record.terminal_disposition in (FAILED, NOT_ACTIONED)
    AND record.attempt_count < record.max_attempts
```

**判定式（initial admission、`create_new_lineage()`、分岐(3)、lineage作成時に一度だけ）**：

```
is_admissible(monitor_status) :=
    self._policy.should_retry(monitor_status, attempt=0)
    # = monitor_status in target_statuses AND 0 < self._policy.max_attempts
```

#### 9.8.1.3 `NOT_ACTIONED`のpayback廃止（MAJ-R8-2対応）

**採用：`NOT_ACTIONED`（interval guard等によるgenuineなno-op）は、他のdisposition（`FAILED`）と同様に`attempt_count`を消費する。paybackは行わない。** `mark_terminal()`は、どのdispositionであっても`attempt_count`を一切書き換えない（12章、Round 8で追加したpayback補正コードを撤回する）。

`attempt_count`の更新点は、Round 1〜4から変更のない唯一の操作のみとなる：**`mark_execution_started()`のdurable ack成功時点で`+1`する（9.5章、disposition確定前、EXECUTION_STARTEDへ遷移するすべてのattemptで無条件に発生）。**

**これにより**：あるstepが恒久的に`NOT_ACTIONED`を返し続ける場合でも、`attempt_count`は毎attempt必ず増加するため、**高々`record.max_attempts`回のattemptで必ず`open_next_attempt()`がbudget exhaustionにより次attemptを拒否し、lineageは有限時間で停止する**（MAJ-R8-2の直接解消）。`attempt_no`／`next_attempt_ordinal`／`attempt_scopes`／`transition_history`の成長も、この`max_attempts`回のattemptに比例した有限量に自動的に上限が付く。

**この設計変更の運用上のトレードオフ（Human Gate承認事項、26章）**：`NOT_ACTIONED`が以後genuineなbudget消費とみなされるため、あるstepのinterval guard周期がretry cadence（reconcileサイクル間隔）より長い場合、そのlineageは**一度もgenuineに成功する機会を得ないまま**budgetを使い切り、`FAILED`と同様に停止しうる。これはRound 5〜8が前提としていた「`NOT_ACTIONED`は常に無料」という設計判断からの明示的な転換であり、運用者はinterval guard周期とretry cadenceの整合を取る責任を負う（11.6章のトレースもこの前提で更新する）。

**判定式（open_next_attempt()、Round 8改訂版からの変更点）**：

```python
# retry_lineage_manager.py（Round 9改訂：open_next_attempt()のattempt accounting判定部分）
if record.terminal_disposition not in (RetryLineageDisposition.FAILED, RetryLineageDisposition.NOT_ACTIONED):
    return OpenNextAttemptResult(acknowledged=False, reason="terminal_disposition is not retryable")
if record.attempt_count >= record.max_attempts:
    # record.max_attempts はlineage作成時にsnapshotされた値（durable state）。
    # RetryPolicy.max_attemptsを都度参照することはない（9.8.1.2章）。
    return OpenNextAttemptResult(acknowledged=False, reason="max_attempts exhausted")
# ...（以降11.4.5.2(b)章の空scope invariant violationチェックへ続く）
```

#### 9.8.1.4 `max_attempts=M`で実retry M回という契約の数値例（**Round 9で簡素化：paybackが存在しないため、disposition構成に依存しない**）

| `max_attempts` | 挙動 | 実際に消費されたretry回数 |
|---|---|---|
| `M=0` | initial admission gate（7.1章）が`0 < 0`＝偽と判定し、新規lineageがそもそも作成されない。次回`retry()`呼び出し時に再評価される | **0回** |
| `M=1` | lineage作成時に`record.max_attempts=1`をsnapshot。attempt 1実行（`attempt_count`: 0→1、`FAILED`／`NOT_ACTIONED`いずれでも同じ）。`open_next_attempt()`：`1 >= 1` → 拒否 | **1回**（`NOT_ACTIONED`であっても同様、payback廃止のため） |
| `M=2` | attempt 1（`attempt_count`: 0→1）：`1>=2`は偽 → attempt 2開く。attempt 2（`attempt_count`: 1→2）：`2>=2` → 拒否 | **2回**（内訳のFAILED/NOT_ACTIONED構成には依存しない） |
| `M=3` | 同様にattempt 1・2・3が実行され、3回目終了時点で`attempt_count=3`、`open_next_attempt()`が`3>=3`で拒否 | **3回**（内訳のFAILED/NOT_ACTIONED構成には依存しない） |

Round 8の数値例表にあった「`NOT_ACTIONED`はpaybackされ、budgetを消費しない」という行はRound 9で撤回する（9.8.1.3章、MAJ-R8-2対応）。

---

## 10. Design Decision E：EXECUTION_STARTED境界・post-admission hook・Execution History相関metadata（**10.2・10.3をRound 4で全面改訂**）

### 10.1 Round 1〜3からの継承（M1解消の要旨、変更なし）

順序は`start_run() ack → correlation_metadata永続化 → 汎用post-admission/pre-action hook → lineageのEXECUTION_STARTED ack → 実際のstep action`。`WorkflowEngineExecutor.run()`の`start_run()`ack確認の直後、step実行ループの直前にhookを挿入する。

### 10.2 hookの呼び出しと失敗時の終端処理（**Round 4で全面改訂、MJ-3新対応：既存History API規律との整合**）

#### 10.2.1 Round 3の欠陥の再確認

Round 3の疑似コードは、hook失敗時に**全stepぶん無条件に`finish_step()`を呼び続け**、さらに**無条件に`finish_run()`を呼ぶ**という実装だった。これは既存`workflow_engine_executor.py`の規律（`finish_step()`が一度でも`False`を返したら`history_closed=True`とし、以降のHistory API呼び出しを一切行わない。`finish_run()`も、`finish_step`失敗経路では呼ばない＝Managerが既にterminal recoveryを1回試行済みのため）と直接矛盾していた（MJ-3新）。

#### 10.2.2 Round 4の設計：既存`history_closed`規律との完全な同型化

**採用：hook失敗時のNOT_REACHED終端処理は、既存の`history_closed`／`owe_closing_finish_run`と全く同じ変数駆動の規律に従う。新しい規律を作らず、既存の規律をそのまま適用する。**

```python
# workflow_engine_executor.py（Round 4改訂：start_run() ack確認の直後、step loopの直前に挿入）
REASON_POST_ADMISSION_HOOK_NOT_ACKNOWLEDGED = "Not executed: post-admission hook did not acknowledge."
REASON_POST_ADMISSION_HOOK_EXCEPTION = "Not executed: post-admission hook raised an exception."

if self._post_admission_hook is not None:
    hook_exception: Exception | None = None
    try:
        hook_result = self._post_admission_hook(run_id)
        hook_ack = hook_result.acknowledged
    except Exception as exc:
        hook_ack = False
        hook_exception = exc

    if not hook_ack:
        reason = (REASON_POST_ADMISSION_HOOK_EXCEPTION if hook_exception is not None
                  else REASON_POST_ADMISSION_HOOK_NOT_ACKNOWLEDGED)
        for step in self._definition.steps:
            step_results.append(WorkflowEngineStepResult(
                step=step, executed=False, agent_result=None, success=False, skipped_reason=reason,
            ))
            if history_closed:
                continue                                    # 既存規律：一度失敗したら以降History APIを呼ばない
            ok = effective_history_manager.finish_step(
                run_id, step.value, StepExecutionStatus.NOT_REACHED, skipped_reason=reason,
            )
            if not ok:
                history_write_failed = True
                history_closed = True                        # 既存規律と同一の変数駆動

        if not history_closed:
            ok = effective_history_manager.finish_run(run_id, WorkflowExecutionStatus.FAILED)
            if not ok:
                history_write_failed = True
        # else: finish_step失敗経路。既存規律どおりManagerが既にrecovery試行済みのため
        #       finish_run は呼ばない（history_write_failedがTrueのままWorkflowEngineResultへ伝播する）。

        context.step_results = step_results
        result = WorkflowEngineResult(
            steps=step_results, overall_success=False, stopped_early=True,
            started_at=started_at, finished_at=datetime.now(),
            warnings=list(context.warnings), history_write_failed=history_write_failed,
        )
        if hook_exception is not None:
            raise hook_exception   # Execution Historyを既存規律どおり終端させた後に再raiseする（10.2.3節）。
        return result
```

この設計は、既存の`for step in self._definition.steps: if history_closed or stopped_early: ...`ループ（既存行118-140）が持つ「`history_closed`になった後は以降のstepへのHistory API呼び出しを行わず、in-memoryの`step_results`記録のみ継続する」という規律を、hook失敗時のNOT_REACHED終端処理にも**一字一句同じ変数（`history_closed`）を用いて**適用する。新しい規律・新しい変数は導入しない。

#### 10.2.3 hook例外の扱い（Round 3から維持、位置づけを明確化）

hookが例外を送出した場合、10.2.2節の規律に従いExecution Historyを（`history_closed`の状態に応じて）安全に終端させた後、**元の例外を再raiseする**。この振る舞いは、既存の`try/finally`構造（`finally: effective_history_manager.release_run(run_id)`）の内側で行われるため、`release_run()`は例外発生時も含め既存どおり必ず1回実行される。

**この設計は6.30 fail-fast原則と矛盾しない**：`CanonicalAdmissionFailure`のfail-fast（Codex Ruling A）は「Admission（`start_run()`）自体の失敗は例外で即座に伝播する」という契約であり、hook例外はAdmission**成功後**に発生するため、この契約の対象範囲を変更しない。hook例外は新たに「Execution Historyを整合させてから伝播する」という**別種の**fail-fast（Admission例外とは異なる、しかし同じく「握りつぶさず呼び出し元へ伝わる」という精神は共有する）として位置づける。`history_write_failed`ラッチ・terminal immutability契約はいずれも変更しない（既存の値がそのまま`WorkflowEngineResult`へ伝播する）。

### 10.2.4 hook未ack時の`RetryExecutor`／`RetryQueueUpdateDecider`契約（**Architecture Amendment（Draft）、Code Review Blocking#1・Blocking#2対応**）

#### 10.2.4.1 発見された欠陥

10.2.2章はWorkflow Engine内部（`workflow_engine_executor.py`）のhook失敗時終端処理を規定しているが、その戻り値を受け取る`RetryExecutor.execute()`側の契約が本書に欠落していた。実装（14章記述どおり`.run()`完了後に無条件で`decide_disposition()`→`mark_terminal()`を呼ぶ）は以下の欠陥を持つことが、実装完了後のCode Reviewで判明した：

- hook未ack時、全stepが`skip_category`＝`HOOK_NOT_ACKNOWLEDGED`／`HOOK_EXCEPTION`となり`NOT_APPLICABLE`に分類される（11.3章）。`disposition_from_categories()`（11.5章）は`UNKNOWN`／`RETRYABLE_FAILURE`／`SILENT_NO_ACTION`のいずれも含まない場合`SUCCEEDED`へfall throughする設計であるため、全`NOT_APPLICABLE`のケースが`SUCCEEDED`と誤判定される。
- `RetryExecutor.execute()`はこの`SUCCEEDED`のまま`mark_terminal()`を呼ぶ（実際には`mark_execution_started()`が未達のためlineageは`phase==CLAIMED`のままであり、`mark_terminal()`は本来phase不一致でack=Falseを返すはずだが、その戻り値を確認していない）。
- `RetryOutcome.RETRIED`のまま返却されるため、`RetryQueueUpdateDecider.decide()`（9.8.1.3章の判定と同一の`decide_disposition()`を独立に再計算）が`COMPLETE`と判定し、Queue項目が完了扱いになりうる。外部actionは実際には一切開始されていない。

12章はこの契約自体（「`mark_terminal()`がack=Falseの場合、呼び出し元は`RetryOutcome.SKIPPED`を返す」）を既に述べていたが、その呼び出し元を`_retry_locked()`と記述しており、実際の呼び出し位置（`RetryExecutor.execute()`）と一致していなかったため、実装へ反映されなかった。

#### 10.2.4.2 確定した契約

**`RetryExecutor.execute()`が、`mark_execution_started()`（post-admission hook）のdurable ack成功・`mark_terminal()`のdurable ack成功の両方を、それぞれの呼び出し直後に確認する唯一の責務を持つ。**

1. **hook未ack（`post_admission_hook`が`acknowledged=False`を返す、またはWorkflow Engineの戻り値から hook失敗が判別できる：`engine_result.stopped_early and`全stepの`skip_category in (HOOK_NOT_ACKNOWLEDGED, HOOK_EXCEPTION)`）の場合**：`decide_disposition()`／`compute_newly_confirmed()`／`mark_terminal()`のいずれも呼ばない（`mark_terminal()`はどのみち`phase==EXECUTION_STARTED`前提のため呼んでも意味を持たない、12章）。代わりに`release_claim(lineage.root_run_id)`を呼び`phase`を`READY_ELIGIBLE`へ戻し（外部actionが一切開始していないため、このattemptは「消費されなかった」ものとして扱う——`attempt_count`は`mark_execution_started()`のdurable ack成功時点でのみ+1される、9.8.1.3章の既存契約どおり、そもそも未達のため増加していない）、`RetryOutcome.SKIPPED`（診断reason付き、例："post-admission hook did not acknowledge; claim released"）を返す。**hook未ack経路は`SUCCEEDED`/`COMPLETE`に到達しない。**
2. **hookはackしたが`mark_terminal()`がack=False（`MarkTerminalResult.acknowledged=False`）を返す場合**（12章の「理論上到達しない防御的分岐」、9.2章のfail-closed経路等）：追加のretryを行わず`RetryOutcome.SKIPPED`（診断reason付き）を返す。lineageの`phase`はそのまま（`EXECUTION_STARTED`）残り、次回`reconcile_all()`サイクルの16章(a)走査で解決される（17章crash matrix行8と同一経路、12章の既存記述どおり）。**`mark_terminal()`のack確認は必須であり、確認せず`RetryOutcome.RETRIED`を返すことを禁止する。**
3. **`CLAIMED`→`TERMINAL`のphase skip禁止（既存不変条件の再確認）**：`mark_terminal()`は`phase==EXECUTION_STARTED`を前提条件として要求しており（12章、変更なし）、`CLAIMED`のまま`mark_terminal()`を呼んでもphase不一致でack=Falseとなる。上記1.により、この経路（hook未ack時）ではそもそも`mark_terminal()`を呼ばないため、`CLAIMED`から`EXECUTION_STARTED`を経由せず`TERMINAL`へ遷移することは構造的に発生しない。
4. **read-back等による推測の禁止**：`RetryExecutor.execute()`は、hook ack・`mark_terminal()` ackいずれについても、`RetryLineageManager`の各メソッドが返すdurable ack（`bool`／`MarkTerminalResult.acknowledged`）**のみ**を根拠として分岐する。`.run()`の`engine_result.overall_success`等、durable stateと独立に存在しうる値を根拠に「おそらく成功しただろう」と推測して`SUCCEEDED`/`COMPLETE`側へ倒すことは禁止する（fail-closed原則、11.5章と同じ精神）。

**`RetryQueueUpdateDecider`（9.8.1.3章）は変更しない**：`retry_result.outcome == RetryOutcome.RETRIED`のみを`COMPLETE`/`FAIL`判定対象とする既存の判定分岐自体は正しく、上記1.・2.により`RetryOutcome.SKIPPED`が返るようになることで、`NOOP`（Queue状態を変えない）へ自然に倒れる。

**16章(c)（新設）**：hook未ack経路以外（プロセスcrash等）で`phase==CLAIMED`のまま取り残されたlineageは、上記1.の`release_claim()`が同一`retry()`呼び出し内（`RetryExecutionLock`保持中）で実行できないケース（`claim()`成功後、hook呼び出し自体に到達する前にプロセスが終了した場合等）に限り発生しうる。この場合の回収は`reconcile_all()`側の責務とする（16章(c)で規定）。

### 10.3 Hook Correlation：Execution Historyへの相関metadata永続化（**Round 4で全面改訂、MJ-2新対応：namespace確定・trust model強化**）

#### 10.3.1 Round 3の欠陥の再確認

Round 3は`correlation_metadata["root_run_id"]`という平坦なキーを無条件に信頼して再接続する設計であり、(1)namespaceが未確定、(2)値の実在検証なし、(3)旧レコードの後方互換未記述、という3つの欠落があった（MJ-2新）。

#### 10.3.2 Round 4の設計：予約済みnamespace＋実在確認による信頼モデル

**採用：`correlation_metadata`は`dict[str, dict[str, str]]`（namespaceごとにネストした汎用metadata）とし、retry-lineage固有の情報は予約済みnamespace`"retry_lineage"`配下にのみ格納する。値は盲目的に信頼せず、`RetryLineageStore`に実在するlineageとの一致を確認した上でのみ再接続の根拠として使う。**

```python
# execution_history_manager.py（追加分のみ）
def start_run(
    self, run_id: str, workflow_name: str, source: str, job_id: str,
    correlation_metadata: dict[str, dict[str, str]] | None = None,
) -> StartRunResult: ...

# workflow_execution_record.py（追加分のみ）
@dataclass
class WorkflowExecutionRecord:
    ...
    correlation_metadata: dict[str, dict[str, str]] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {..., "correlation_metadata": dict(self.correlation_metadata), ...}

    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowExecutionRecord":
        return cls(
            ...,
            correlation_metadata=data.get("correlation_metadata", {}),  # 旧レコードとの後方互換
        )
```

`execution_history`パッケージは`correlation_metadata`の**キー・値のいずれも一切解釈しない**（`"retry_lineage"`という文字列も、他の任意の文字列も、`execution_history`にとっては等価な、意味を持たない辞書エントリである）。この点でgeneric性を保ち、6章却下代案1の原則（Retry判定ロジックをExecution Historyへ持ち込まない）を破らない。

**namespace衝突規則**：`correlation_metadata`配下の各namespaceキーは、それを書き込むsubsystemが専有する。あるsubsystemは自身のnamespaceキー配下にのみ読み書きし、他のnamespaceキーを読み書きしない。本Releaseでは`"retry_lineage"`のみを予約する。将来他のsubsystemが独自のnamespace（例：`"scheduler"`）を追加する場合も、既存の`"retry_lineage"`namespaceには一切干渉しない。

`RetryExecutor`は`.run()`呼び出し時に以下を渡す：

```python
correlation_metadata = {
    "retry_lineage": {
        "root_run_id": lineage.root_run_id,
        "intended_attempt_no": str(claim.attempt_no),
        "correlation_id": claim.correlation_id,   # claim()時点で新規発行される、owner_tokenとは独立の永続ID（後述）
    }
}
```

**（Round 5で変更）**：`correlation_id`は`owner_token`を再利用しない。`owner_token`は`release_claim()`/`mark_terminal()`時にクリアされる**一時的**な診断値であり、後から相関を検証する時点（候補discovery時、claimからかなり時間が経過している可能性がある）には既に失われている。**`correlation_id`は`claim()`が新規発行し（`uuid.uuid4().hex`）、`transition_history`のCLAIMED遷移イベントへ`detail`とは別の専用フィールドとして永続的に記録する**（append-only、`release_claim()`/`mark_terminal()`によっても消去されない）。

```python
@dataclass
class RetryLineageTransitionEvent:
    attempt_no: int
    from_phase: RetryLineagePhase | None
    to_phase: RetryLineagePhase
    run_id: str | None
    at: datetime
    detail: str | None = None
    correlation_id: str | None = None   # Round 5で新設。to_phase==CLAIMEDの遷移イベントにのみ設定される
```

`scripts/run_workflow_engine.py`等の既存（非retry）呼び出し元は`correlation_metadata`を渡さない（`None`→`{}`、既存出力に対しては新規キーが1つ増えるのみ）。

#### 10.3.3 `RetryEnqueueTrigger`の改訂：membership-first・correlation-fallback・exact-match検証（**Round 5で改訂、intended_attempt_noの正確な述語を確定**）

**2段階構成（Round 4から維持、Round 5で明文化）**：

1. **membership-first**：候補run_idについて、まず`RetryLineageManager.find_by_member_run_id(candidate_run_id)`（7章のB1解消メカニズム）を試みる。`mark_execution_started()`が成功していれば、この候補run_idは既に`membership`へ記録されているため、**相関metadataを一切参照せず**、直接かつ厳密に既存lineageへ再接続される。これが常に優先される、より強い経路である。
2. **correlation-fallback**：1で見つからなかった場合（＝`mark_execution_started()`が一度も成功しなかった、hook ack失敗由来のorphan候補、10.2章）に**限り**、`correlation_metadata["retry_lineage"]`による、以下の**3条件すべての完全一致（exact match）**を検証する：

   a. `root_run_id`が存在し、`RetryLineageManager.peek(root_run_id)`が実在するlineageレコードを返す。
   b. `intended_attempt_no`（数値としてパース可能であること）が、bで取得したlineageレコードの**現在の**`next_attempt_ordinal`と**厳密に等しい**（`intended_attempt_no == lineage.next_attempt_ordinal`）。これは「範囲一致」ではなく「現在アクティブな（次に消費される）attempt_noとの完全一致」を要求する正確な述語である。`mark_execution_started()`が一度も成功していないorphanの場合、`next_attempt_ordinal`は当該attemptの試行によって一切消費されていないため、常にこの値と一致するはずである（12章）。
   c. `correlation_id`が、当該lineageの`transition_history`内に、**`to_phase==CLAIMED`かつ`attempt_no==intended_attempt_no`**の遷移イベントとして実際に記録されている`correlation_id`と**完全一致**する。

   a・b・cの**すべて**が満たされた場合にのみ、この候補run_idを「既存lineageの一部（hook失敗由来のorphan）」として扱い、独立候補としての新規lineage作成対象から除外する。**いずれか1つでも満たさない場合は、相関情報が存在しない場合と全く同じ扱い**（通常の独立候補として処理、fail-closed、盲目的に信頼しない）とする。

**この3条件同時一致（root_run_id実在＋attempt_no厳密一致＋transition_history上のcorrelation_id一致）により、forged（存在しないroot_run_idを騙る）・stale（古いattempt_noを騙る、既にlineageが先へ進んでいる）・malformed（型不正）のいずれの偽装・誤り値も再接続の根拠として採用されない**。

#### 10.3.4 malformedな相関情報の扱い

`"retry_lineage"`namespaceの値が期待する型・構造でない場合（例：文字列ではない、`root_run_id`キーが欠落している等）、これを**authoritativeな相関情報として一切扱わない**（fail-closed）。この場合、当該候補run_idは相関情報が存在しない場合と同一の経路（通常の独立候補処理）へフォールバックする。**これにより、無関係な独立FAILED候補を誤って除外することはない**（10.3.1節の要件を維持）。

#### 10.3.5 6.30既存canonical呼び出し元・後方互換への影響

- `correlation_metadata`省略時（既存の全ての非retry呼び出し元）は`{}`となり、既存の振る舞い・既存のシリアライズ出力の値には一切影響しない（新規キーが1つ増えるのみ、21章）。
- **旧レコード（`correlation_metadata`フィールドが存在しないJSON、本フィールド導入前に保存されたもの）を読み込む際**、`from_dict()`は`data.get("correlation_metadata", {})`により空dictへフォールバックする（10.3.2節のコード例）。これにより、既存の`JsonExecutionHistoryStore`のatomic save/recovery契約・パースロジックへの変更は不要であり、旧レコードのロードは失敗しない。
- `CanonicalAdmissionFailure`／`history_write_failed`ラッチ／terminal immutability／fail-fast原則は、いずれも本フィールド追加によって一切変更されない（`correlation_metadata`は`start_run()`の引数・`WorkflowExecutionRecord`のフィールドとして受け渡されるだけの、意味非解釈のデータであり、制御フローには一切関与しない）。

### 10.4 却下した代案（Round 1〜3から維持、Round 4で追加）

（Round 1〜3の却下代案は旧版参照。）

- **（Round 4で追加）代案：`correlation_metadata["root_run_id"]`のような平坦なキーのまま、値の実在確認のみ追加する（namespace化しない）。** 却下理由：平坦なキー名は将来の別subsystemによる意図しない上書き・衝突のリスクを構造的に排除できない。namespace化（10.3.2節）はこのリスクをゼロコストで解消する。
- **（Round 4で追加）代案：Execution Historyへ`action_taken`相当の情報を追加し、`StepExecutionRecord`をAgentResultと同等の情報量にする。** 却下理由：`action_taken`はAgent/Retryドメインの概念であり、6章却下代案1が拒否した「Retry判定ロジックをExecution Historyへ持ち込む」ことと同種の越境になる。`correlation_metadata`（意味非解釈の汎用metadata）とは性質が異なり、6.31のスコープを超える。reconcile_all()経由でのsilent-no-action検出精度の限界（11.5章）は、既知の残存ギャップとして開示するに留める。

---

## 11. Design Decision F：Step Outcome Classification・実行制御・Genuine Action判定（**Round 5で全面改訂、Round 6で追加修正（H-1〜H-3対応）**）

> **Human Gate候補（未承認）**：本章が導入する`StepExecutionRecord.action_taken`・`skip_category`フィールド追加（Execution Historyスキーマの追加拡張）、`target_step_filter`によるWorkflow Engine実行制御の追加、および11.4.5章（Round 6新設）の空scope invariant violation fail-closed設計は、**いずれもまだHuman Gateで承認されていない**。26章Gate Checklistに明示の承認事項として追加する。

### 11.1 Round 3の欠陥の再確認

Round 3の`decide_disposition()`は「target step（`attempt_targets[-1]`）がgenuineに動作し、かつ`engine_result.overall_success==True`であれば`SUCCEEDED`」と判定していた。しかし`overall_success`は`all(step.success for step in steps)`であり、`success=True`は「stepが実行され例外なく完了した」ことしか意味せず、「実質的な行動（action）を伴ったか」（`action_taken`）とは独立である。このため、**target step（NEWS）自体は今回genuineに成功していても、別のstep（PUBLISH）がinterval guardによるsilent no-opであった場合、`overall_success`は依然`True`のままとなり、disposition判定が`SUCCEEDED`へ誤って倒れる**ことを、実際の疑似コードのトレースにより確認した（BL-1新）。

### 11.2 実コード確認による既存Agentのstep outcome分類（**Round 4で新設、ユーザー指示のread-only確認**）

`src/ai/news_agent.py`・`src/ai/review_trigger_agent.py`・`src/ai/publish_trigger_agent.py`（NEWS/REVIEW/PUBLISHの3ステップに対応する既存Agent、`src/workflow_engine/workflow_engine_manager.py:90-126`）を確認した結果、3 Agentすべてが以下の同一パターンに従っていることを確認した：

- `decide()`は、実行間隔（`min_interval_minutes`）のみに基づき`should_act`を判定する（副作用なし）。`should_act=False`は常に「前回実行からの経過時間が基準未満」という**時間経過により自己解消する一時的な**理由であり、恒久的に`should_act=False`であり続けるロジックは存在しない。
- `act()`は常に`action_taken=True`を設定し、`success=result.success`（実処理パイプラインの結果をそのまま反映、失敗しうる）を返す。`act()`が`action_taken=False`を返す経路は存在しない。

さらに`AgentExecutor.execute()`（`src/ai/agent_executor.py:36-98`）を確認した結果、`AgentResult`が取りうる`(action_taken, success)`の組み合わせは以下の3つに限定されることを確認した：

| 経路 | action_taken | success | 発生条件 |
|---|---|---|---|
| `should_act=False`（decide()判断） | `False` | `True` | interval未経過（自己解消型） |
| `should_act=True, dry_run=False`, `act()`正常完了 | `True` | `result.success`（True/False） | 実処理パイプラインの成否をそのまま反映 |
| `decide()`/`act()`中の例外 | `False` | `False` | AgentExecutorが例外を捕捉し失敗として記録 |

また`WorkflowEngineExecutor`（`src/workflow_engine/workflow_engine_manager.py:95-126`、`step_executors`／`step_skip_reasons`の構築ロジック）を確認した結果、REVIEW/PUBLISHステップは`config.is_ready()`が`False`の場合、**プロセス構築時点で固定的に**`executor=None`（gate closed）となり、`WorkflowEngineExecutor`は該当stepを`executed=False, agent_result=None, success=True, skipped_reason=<gate closed reason>`として扱う（既存行144-156）。この`skipped_reason`文字列は`step_skip_reasons`辞書経由で呼び出し元が自由に設定できる汎用文字列であり、特定の定数と一致するかどうかでは判定できない（デフォルト値は`f"{step.value} step is not configured (gate closed)."`という動的生成文字列）。

### 11.3 `StepOutcomeCategory`：構造化された`skip_category`に基づくstep outcome contract（**Round 5で改訂：自由文字列判定を廃止、MN-新1対応**）

#### 11.3.1 Round 4の欠陥の再確認

Round 4の`classify_step_outcome()`は、`executed=False`の場合の分類を`skipped_reason`という**自由文字列**の一致判定に依存していた。しかし`step_skip_reasons`辞書は呼び出し元が任意の文字列を設定でき、既定値も`f"{step.value} step is not configured (gate closed)."`という動的生成文字列であるため、「既知の3つの構造的理由に一致しない場合は`INTENTIONAL_NO_ACTION`」という残余分類ロジックの下では、**`UNKNOWN`へ到達する経路が実質存在しなかった**（自分自身が24章で謳っていた「想定外のskipped_reason文字列→UNKNOWN」というテスト主張と矛盾していた、MN-新1）。

#### 11.3.2 Round 5の設計：構造化`skip_category`フィールドの導入

**採用：`WorkflowEngineStepResult`（および対応する`StepExecutionRecord`、11.7章）へ、人間可読の`skipped_reason`文字列とは別に、内部専用の構造化フィールド`skip_category`を追加する。分類は`skip_category`の値のみを見て行い、`skipped_reason`文字列の内容は一切参照しない。**

```python
class StepSkipCategory(Enum):
    GATE_CLOSED           = "gate_closed"             # 設定起因、恒久的スキップ
    NOT_REACHED           = "not_reached"              # cascade（前段の失敗による未到達）
    HISTORY_WRITE_FAILED  = "history_write_failed"      # 構造的スキップ（既存6.30契約）
    HOOK_NOT_ACKNOWLEDGED = "hook_not_acknowledged"      # 構造的スキップ（10.2章）
    HOOK_EXCEPTION        = "hook_exception"             # 構造的スキップ（10.2章）
    NOT_TARGETED          = "not_targeted"               # 11.4章で新設：既にconfirmed doneのため今回スキップ

@dataclass
class WorkflowEngineStepResult:
    step: WorkflowEngineStep
    executed: bool
    agent_result: AgentResult | None
    success: bool
    skipped_reason: str | None       # 既存、人間可読の診断文字列（変更なし）
    skip_category: StepSkipCategory | None = None   # Round 5で新設。executed=Trueなら常にNone
```

`workflow_engine_executor.py`の各構築箇所（gate-closed分岐・NOT_REACHED cascade分岐・`start_step()`失敗分岐・hook失敗分岐・11.4章で新設するnot-targeted分岐）は、それぞれ対応する`skip_category`を**明示的に**設定する（既存の`skipped_reason`文字列はそのまま人間可読の診断情報として維持する）。

```python
class StepOutcomeCategory(Enum):
    GENUINE_SUCCESS       = "genuine_success"
    RETRYABLE_FAILURE     = "retryable_failure"
    SILENT_NO_ACTION      = "silent_no_action"
    INTENTIONAL_NO_ACTION = "intentional_no_action"
    NOT_APPLICABLE        = "not_applicable"
    UNKNOWN               = "unknown"

def classify_step_outcome(step_result: WorkflowEngineStepResult) -> StepOutcomeCategory:
    if not step_result.executed:
        if step_result.agent_result is not None:
            return StepOutcomeCategory.UNKNOWN                # 構造的に到達しないはずだが防御的にfail-closed
        if step_result.skip_category is None:
            return StepOutcomeCategory.UNKNOWN                # 構造化フィールド未設定＝防御的にfail-closed
        if step_result.skip_category == StepSkipCategory.GATE_CLOSED:
            return StepOutcomeCategory.INTENTIONAL_NO_ACTION
        if step_result.skip_category in (
            StepSkipCategory.NOT_REACHED,
            StepSkipCategory.HISTORY_WRITE_FAILED,
            StepSkipCategory.HOOK_NOT_ACKNOWLEDGED,
            StepSkipCategory.HOOK_EXCEPTION,
            StepSkipCategory.NOT_TARGETED,
        ):
            return StepOutcomeCategory.NOT_APPLICABLE
        return StepOutcomeCategory.UNKNOWN                     # 将来のenum拡張に対する防御的fail-closed
    # executed=True
    if step_result.agent_result is None:
        return StepOutcomeCategory.UNKNOWN
    if not step_result.success:
        return StepOutcomeCategory.RETRYABLE_FAILURE
    if step_result.agent_result.action_taken is True:
        return StepOutcomeCategory.GENUINE_SUCCESS
    if step_result.agent_result.action_taken is False:
        return StepOutcomeCategory.SILENT_NO_ACTION
    return StepOutcomeCategory.UNKNOWN   # Round 7：防御的fail-closed。AgentResultの
                                          # action_takenは型としてはbool固定（11.2章）だが、
                                          # truthy判定を廃し恒等比較のみで分類することで、
                                          # reconcile経路（11.7.2章）とclosed-set semanticsを
                                          # 統一する（M-1・M-2対応）。
```

**これにより`UNKNOWN`は実際に到達可能になる**（`skip_category`が未設定、または`StepOutcomeCategory`側が把握していない将来の列挙値を持つ場合）。MN-新1で指摘された自己矛盾を解消する。

### 11.4 実行制御：step間の実データ依存分析と`target_step_filter`の採用（**Round 5で新設**）

#### 11.4.1 実コード確認によるstep間データ依存の分析（ユーザー指示のread-only確認）

`src/pipeline/news_pipeline_runner.py`・`src/pipeline/review_pipeline_runner.py`・`src/pipeline/publish_pipeline_runner.py`、および`workflow_engine_executor.py`の`AgentContext`構築箇所（`params=dict(context.event.metadata)`、既存行183-186）を確認した結果、以下を確認した：

- **全stepの`AgentContext.task.params`は、同一の静的`context.event.metadata`から都度構築される**。あるstepの実行結果が、後続stepの入力として直接（in-memoryで）渡される経路は一切存在しない。
- NEWSは`main.py`をsubprocessとして起動し、収集した記事をファイルシステムへ書き出す（`NewsPipelineRunner`）。
- REVIEWは`AiPublishReviewService.run(article_id=...)`を呼ぶ（`ReviewPipelineRunner`）。このサービスは`outputs/`配下のレビュー未了記事を独自に走査する（設計方針コメント「過去のレビュー履歴を含め走査する」）。
- PUBLISHは`AiPublishService.run(article_id=...)`を呼ぶ（`PublishPipelineRunner`）。同様に独自にpublish対象を走査する。
- REVIEW/PUBLISHいずれも、`decide()`は自分自身の出力ディレクトリ（レビューレポート／publishレポート）のmtimeのみを根拠に`should_act`を判定しており、「NEWSが**今回の同一実行内で**新しい記事を書いたかどうか」を一切参照しない。

**結論：NEWS→REVIEW→PUBLISHは、同一`WorkflowEngineExecutor.run()`呼び出し内でのin-memoryなデータ受け渡しに一切依存せず、各stepが独立に永続化されたファイルシステム状態（記事ファイル・レビューレポート・publishレポート）を走査する、疎結合な設計である。** あるstepが過去のいずれかのattemptで一度genuineに成功していれば、その成果はファイルシステム上に永続化済みであり、後続stepは「NEWSが今回のattemptでも実行されたか」に一切依存せず、既存の永続化状態を正しく発見・処理できる。

#### 11.4.2 検討した3方式の比較

| 方式 | 内容 | 評価 |
|---|---|---|
| (a) target-only実行（対象stepのみ実行、他は無条件skip） | `resolve_next_target_from_*()`が返す単一のtarget setのみを実行し、他のstepは常にskip | 11.4.1節の分析により**安全**（依存なし）。ただし、Round 4の設計のように「target」を**単一の集合を都度置き換える**モデルにすると、NOT_REACHED（一度も実行機会がなかったstep）を誤って除外するリスクがある（後述） |
| (b) dependency closure（依存関係の推移閉包に基づき、targetに加えてその依存先も再実行） | 11.4.1節の分析により、**実データ依存関係自体が存在しない**ため、closureを計算する意味がない | 却下（該当する依存関係がなく、無用な複雑さを追加するだけ） |
| (c) 全step再実行（フィルタなし、Round 1〜4の現状） | 常に全stepを再実行する | 11.4.1節の分析上は安全（副作用の二重実行にはならない）が、**各stepが持つ独自のinterval guardが複数重なることで、SUCCEEDEDへ到達できないliveness問題**を引き起こす（Round 4 review、独自発見） |

**採用：(a)を採用するが、Round 4の「単一のtarget集合を都度置き換える」モデルではなく、`steps_confirmed_done`という**累積的（monotonic）な集合**を用いる。**

#### 11.4.3 `steps_confirmed_done`モデル

**設計**：lineageは`steps_confirmed_done: list[str]`（append-only、一度追加されたstep名は除去されない）を保持する。あるattemptで`StepOutcomeCategory.GENUINE_SUCCESS`と分類されたstepは、そのattemptのdisposition（`SUCCEEDED`/`FAILED`/`NOT_ACTIONED`のいずれであっても）に関わらず、**都度`steps_confirmed_done`へ追加**される。次attemptの`steps_to_execute`（＝`WorkflowEngineManager.run()`へ渡す`target_step_filter`）は、常に`ALL_WORKFLOW_ENGINE_STEPS - steps_confirmed_done`として算出する。

```python
# retry_target_resolution.py（Round 5で拡張）

def compute_newly_confirmed(
    engine_result: WorkflowEngineResult,
) -> list[str]:
    """このattemptでGENUINE_SUCCESSと分類されたstep名を返す（steps_confirmed_doneへ追加する対象）。"""
    return [s.step.value for s in engine_result.steps
            if classify_step_outcome(s) == StepOutcomeCategory.GENUINE_SUCCESS]


def compute_steps_to_execute(steps_confirmed_done: list[str]) -> list[str]:
    """次attemptで実際に実行すべきstep（既にconfirmed doneのものを除く全step）を返す。

    不変条件（Round 9で明記、MIN-R8-4対応）：戻り値は常にALL_WORKFLOW_ENGINE_STEPS
    の列挙順（Workflow canonical order、NEWS→REVIEW→PUBLISHの固定順）で並ぶ。
    setやdictの反復順に依存する実装へ変更してはならない。この関数はstoredの
    attempt_scopes[-1].steps_to_execute（lineage作成時またはopen_next_attempt()が
    書き込む値）とclaim()の再計算値（11.4.5.2(a)章）の両方を生成する唯一の関数
    であるため、両者は常に同一のcanonical orderで比較可能である。
    """
    return [s.value for s in ALL_WORKFLOW_ENGINE_STEPS if s.value not in steps_confirmed_done]
```

`WorkflowEngineManager.run()`/`WorkflowEngineExecutor`は新規オプション引数`target_step_filter: list[WorkflowEngineStep] | None = None`を受け取る。`None`（省略、既存の全非retry呼び出し元）の場合は従来どおり全stepを対象とする（Zero-Diff）。`target_step_filter`が指定されている場合、`self._definition.steps`のループにおいて、**gate-closed判定より前**に「このstepは`target_step_filter`に含まれるか」を確認し、含まれない場合は`skip_category=StepSkipCategory.NOT_TARGETED`、`success=True`、`skipped_reason="Not targeted for this retry attempt (already confirmed done)."`として（gate-closed skipと同型のパターンで）スキップする。`finish_step(..., StepExecutionStatus.SKIPPED, skipped_reason=...)`を呼ぶ点も既存のgate-closedパターンと同一とする。

`RetryExecutor`は、`claim()`が返す（`RetryLineageManager`が計算した）`steps_to_execute`を`target_step_filter`として`.run()`へ渡す。**attempt 1（lineage作成時）を含む全attemptが同一のロジックに従う**：`steps_confirmed_done`は初期値`[]`ではなく、**元のFAILED/TIMEOUT recordから`classify_execution_history_step()`（11.7章）でGENUINE_SUCCESSと分類できたstepがあれば、それらを初期値として含める**（元の正常canonical run時点で既にgenuineに成功していたstepを、attempt 1から不要に再実行しない）。**（Round 11で実装経路を確定、MAJ-R10-2対応）**この導出は`create_new_lineage()`（7.2章）内で`compute_initial_confirmed_steps()`（7.2.2章新設）が行う。入力は`monitor_record.steps`（`WorkflowMonitorRecord.steps`、元の`WorkflowExecutionRecord.steps`のコピー）であり、`_retry_locked()`（9.3.2章）が`self._monitor.get_status(run_id)`で取得済みの値をそのまま`create_new_lineage()`へ渡す——`create_new_lineage()`自身がExecution Historyストアへ別途アクセスすることはない。

#### 11.4.4 NOT_REACHED・cascadeとの整合

`steps_confirmed_done`は`GENUINE_SUCCESS`のみによって増加するため、一度も実行機会がなかった（`NOT_APPLICABLE`／`NOT_REACHED`）step、`RETRYABLE_FAILURE`だったstep、`SILENT_NO_ACTION`だったstepは、いずれも次attemptで`steps_to_execute`（＝実行対象）に**残り続ける**。Round 4の「単一target置き換え」モデルが持っていた「NOT_REACHED stepを誤って除外するリスク」（Round 4完了報告時点では気付いていなかった潜在的欠陥）は、累積モデルにより構造的に排除される。

#### 11.4.5 空`steps_to_execute`：invariant violation fail-closedの契約（**Round 7で全面改訂：terminal/scope責務の分離、Round 6 review B-1対応**）

#### 11.4.5.1 Round 6の欠陥の再確認（B-1）

Round 6は「`mark_terminal()`が`attempt_scopes`へ次attempt用のscopeを追加する際、同一の防御的チェックを行い、空になる場合は`disposition`を強制的に`FAILED`へ倒す（write-time defense in depth）」としていた。しかしこの記述は、**`mark_terminal()`が`disposition`の値（SUCCEEDED／FAILED／NOT_ACTIONED）を問わず無条件に「次attempt用scope」を計算する**ことを前提にしていた（§12旧版：「`mark_terminal()`は…`attempt_scopes`へ次attempt用の`steps_to_execute`…を記録する」に条件分岐がなかった）。

このため、**全stepがそのattemptでgenuineに完了した正常なSUCCEEDED終端**（例：`steps_confirmed_done_before=["news","review"]`、`newly_confirmed_steps=["publish"]`→union=全step）でも、「次attempt用scope」を計算すると当然空になる。これは破損ではなく正常終了だが、write-time defenseが字義通りに適用されると、この正常な`SUCCEEDED`が`FAILED`へ強制変換され、`open_next_attempt()`後の次`claim()`が恒久的にack=Falseを返す——**H-1が解消したはずのfail-openと同型の、しかし逆方向の重大な欠陥**（正常終了が異常終了に化ける）を生んでいた。加えて、「scopeは`claim()`時点で追加されるのか、`mark_terminal()`時点で追加されるのか」という記述自体が§11.4.5（旧）・§12・§13間で矛盾しており、実装可能な精度に達していなかった。

#### 11.4.5.2 Round 7の設計：terminal化とscope生成の責務分離

**採用：`mark_terminal()`は現在attemptをTERMINAL化しconfirmed stateを保存するだけとし、`attempt_scopes`へは一切書き込まない。次attempt用scopeの生成は`open_next_attempt()`の専管責務とし、`terminal_disposition`がretryable（`FAILED`／`NOT_ACTIONED`）かつbudget残ありの場合に限り行う。** 詳細な責務分離は12章で定義する。本節はこの分離を前提とした、2箇所の独立したinvariant violation fail-closedチェックを定義する。

**(a) `claim()`時点でのチェック（Round 6から維持、Round 8で保存済みscopeをauthoritative化、MN-new-1対応）**：

Round 7までの`claim()`は`compute_steps_to_execute(record.steps_confirmed_done)`の再計算結果をそのまま`steps_to_execute`として採用し、空集合の場合のみfail-closedしていた。しかしこれは「再計算値が保存済み`attempt_scopes[-1].steps_to_execute`と一致するはず」という前提を検証しておらず、**空集合ではないが値が食い違う**（`steps_confirmed_done`の部分的破損等）ケースが未規定のまま看過されうる欠陥だった（MN-new-1）。

**採用：保存済み`attempt_scopes[-1].steps_to_execute`（lineage作成時または`open_next_attempt()`が書き込んだ値）をauthoritativeとする。`steps_confirmed_done`からの再計算は、この保存済み値の整合性を検証するためだけのvalidation専用処理とし、両者が完全一致しない場合は（空集合であるか否かを問わず）fail-closedする。自動修復は行わない。**

```python
def claim(self, root_run_id: str) -> ClaimResult:
    with self._store_lock():
        record = self._store.get(root_run_id)
        if record is None or record.phase != READY_ELIGIBLE:
            return ClaimResult(acknowledged=False, reason=...)
        if record.next_eligible_at and record.next_eligible_at > now():
            return ClaimResult(acknowledged=False, reason="cooldown not elapsed")
        if not record.attempt_scopes:
            # invariant violation：READY_ELIGIBLEであるにもかかわらずattempt_scopesが
            # 一度も書き込まれていない（lineage作成分岐またはopen_next_attempt()の
            # いずれかが本来書くはずの値が欠落している）。.run()を一切呼ばずfail-closedで停止する。
            return ClaimResult(
                acknowledged=False,
                reason="invariant_violation: no attempt_scopes recorded while "
                       "phase=READY_ELIGIBLE. Refusing to claim.",
            )

        stored_scope = record.attempt_scopes[-1]
        # Architecture Amendment（Draft、Code Review Major#4対応）：next_attempt_ordinal
        # 不変条件（next_attempt_ordinalはattempt_scopes[-1].attempt_noと常に同期する、
        # §0 Amendment・25章項目「next_attempt_ordinal」参照）を、値を使う前に検証する。
        # これまでは両者が一致する前提で一方（stored_scope.attempt_no）のみを使っており、
        # 不一致（状態破損）を検出する経路がなかった。
        if record.next_attempt_ordinal != stored_scope.attempt_no:
            return ClaimResult(
                acknowledged=False,
                reason=(
                    f"invariant_violation: next_attempt_ordinal ({record.next_attempt_ordinal}) "
                    f"!= attempt_scopes[-1].attempt_no ({stored_scope.attempt_no}). "
                    f"Refusing to claim (no auto-repair)."
                ),
            )
        recomputed = compute_steps_to_execute(record.steps_confirmed_done)
        # Round 9で明記（MIN-R8-4対応）：比較はWorkflow canonical order
        # （ALL_WORKFLOW_ENGINE_STEPSの列挙順、11.4.3章）で行う。compute_steps_to_execute()
        # は常にこの順序で返すという不変条件（11.4.3章）により、recomputed・
        # stored_scope.steps_to_executeのいずれも同一のcanonical orderで生成されているはずだが、
        # defense-in-depthとして、比較直前に両者を明示的に正規化してから比較し、意味的に
        # 同一だが順序破損由来の値によって誤ってfail-closedしないようにする。
        # Round 11で修正（MIN-R10-1対応）：7.3章の共通ヘルパー_canonicalize_step_order()を
        # ここでも使う（Round 10まではcanonical_order辞書とsorted()をこの箇所だけ独自に
        # インライン構築しており、7.3章が謳う「create_new_lineage()・open_next_attempt()・
        # claim()の3箇所で共有される1つの関数」という契約と矛盾していた）。
        recomputed_normalized = _canonicalize_step_order(recomputed)
        stored_normalized = _canonicalize_step_order(stored_scope.steps_to_execute)
        if recomputed_normalized != stored_normalized:
            # validation-only：保存済みscope（authoritative）と再計算値が完全一致しない場合、
            # 空集合であるか否かを問わずinvariant violationとしてfail-closedする。
            # 自動修復（どちらか一方を正として採用する等）は行わない。
            return ClaimResult(
                acknowledged=False,
                reason=f"invariant_violation: recomputed steps_to_execute ({recomputed}) does not "
                       f"match stored attempt_scopes[-1].steps_to_execute "
                       f"({stored_scope.steps_to_execute}). Refusing to claim (no auto-repair).",
            )

        steps_to_execute = stored_scope.steps_to_execute   # 保存済み値をauthoritativeとして採用
        # ...（以降、通常のCLAIMED遷移・9.2章のRetryLineageStoreLock保護下）
```

`claim()`がack=Falseを返すため、`RetryExecutor`は`.run()`を一切呼ばない（`RetryManager._retry_locked()`は`RetryOutcome.SKIPPED`を返す、9.3.2章）。これにより、旧版が「空集合のみ」を検出していたのに対し、Round 8では「保存済みscopeとの完全一致」を要求する、より広いfail-closed条件へ一般化された（空集合ケースは`compute_steps_to_execute()`が`[]`を返し、これが非空の`stored_scope.steps_to_execute`と一致しないため、引き続き同じ経路でfail-closedする）。

**(b) `open_next_attempt()`時点でのチェック（Round 7新設、B-1の根本解消。Round 8で判定式を9.8.1章のdurable-state-only契約へ差し替え、M-new-1対応）**：`open_next_attempt()`はまず9.8.1章の判定式（`terminal_disposition in (FAILED, NOT_ACTIONED)`かつ`attempt_count < max_attempts`、いずれも`monitor_status`のような実行時専用の値に依存しないdurable state判定）でretryable性を確認した後、次attempt用scopeを計算する。この計算が空になる場合、`steps_confirmed_done`の破損によるinvariant violationとして扱い、`READY_ELIGIBLE`への遷移を拒否する（詳細な疑似コードは12章）。**`terminal_disposition==SUCCEEDED`の場合、`open_next_attempt()`はそもそも呼ばれない**（§16(b)の走査条件、および9.8.1章の判定式により、retryableでないdispositionに対して次attemptを開くことはない）ため、**全stepがconfirmed済みの正常なSUCCEEDED終端はこのチェックの対象に一切ならない**。これによりB-1（正常なSUCCEEDED終端が誤ってFAILEDへ変換される問題）を構造的に解消する。

**いずれのチェックも、`next_eligible_at`によるcooldown待ちとは異なり、時間経過によって自然解消しない**（`steps_confirmed_done`の破損、または`attempt_scopes`の保存値の破損・不一致が解消されない限り、`claim()`／`open_next_attempt()`は恒久的にack=Falseを返し続ける）。このため、18章Observabilityの`diagnose_stuck()`へ、この2つの状態を検出する診断を追加する。運用者は`steps_confirmed_done`・`attempt_scopes`の内容を手動で検証し、破損が確認できた場合のみ、9.4章と同種の明示的な手動修復手順（Architecture外の運用手順）を要する。自動修復は行わない（11.4.5.2(a)章）。

### 11.5 `decide_disposition()`（**Round 5で改訂：11.3・11.4の変更を反映**）

`decide_disposition()`自体のロジック（優先順位：`UNKNOWN`→`FAILED`、`RETRYABLE_FAILURE`→`FAILED`、`SILENT_NO_ACTION`→`NOT_ACTIONED`、それ以外→`SUCCEEDED`）はRound 4から変更しない。**変更点は評価対象の母集団**：`target_step_filter`により`NOT_TARGETED`となったstepは`NOT_APPLICABLE`に分類されるため、`decide_disposition()`の判定は自然と「今回実際に実行された（＝まだconfirmed doneでない）step群」のみに基づくようになる。

```python
def decide_disposition(engine_result: WorkflowEngineResult) -> RetryLineageDisposition:
    categories = [classify_step_outcome(s) for s in engine_result.steps]
    if any(c == StepOutcomeCategory.UNKNOWN for c in categories):
        return RetryLineageDisposition.FAILED
    if any(c == StepOutcomeCategory.RETRYABLE_FAILURE for c in categories):
        return RetryLineageDisposition.FAILED
    if any(c == StepOutcomeCategory.SILENT_NO_ACTION for c in categories):
        return RetryLineageDisposition.NOT_ACTIONED
    return RetryLineageDisposition.SUCCEEDED   # 全executed stepがGENUINE_SUCCESS、残りはNOT_APPLICABLE/INTENTIONAL_NO_ACTION
```

### 11.6 NEWS→PUBLISH target driftの具体値トレース（**Round 5で再トレース、liveness問題の解消確認**）

**前提**：`root_run_id=A`。元のcanonical runでNEWS・REVIEWは`GENUINE_SUCCESS`、PUBLISHは`RETRYABLE_FAILURE`だった（`WorkflowExecutionRecord`に`action_taken`が正しく記録されている前提、11.7章）。lineage作成時：`steps_confirmed_done=["news","review"]`（初期値）、`steps_to_execute=["publish"]`、`record.max_attempts`は作成時点の`RetryPolicy.max_attempts`をsnapshot（9.8.1章）。**このトレースは`max_attempts>=2`を前提とする**（Round 9でNOT_ACTIONEDのpayback廃止、9.8.1.3章）。

**attempt 1**：`target_step_filter=["publish"]`で`.run()`を呼ぶ。NEWS・REVIEWは`skip_category=NOT_TARGETED`で即座にスキップ（`NOT_APPLICABLE`）。PUBLISHが実行され、`executed=True, success=True, action_taken=False`（interval guardによりsilent no-op）→`SILENT_NO_ACTION`。`attempt_count`は`mark_execution_started()`時点で0→1に消費済み（9.5章）。

**`decide_disposition()`**：`categories=[NOT_APPLICABLE, NOT_APPLICABLE, SILENT_NO_ACTION]` → `SILENT_NO_ACTION`が1件 → **`NOT_ACTIONED`**。**（Round 9で変更）**paybackは行われない——`attempt_count=1`のまま`mark_terminal()`が終端する（9.8.1.3章）。`steps_confirmed_done`は変化なし（PUBLISHはGENUINE_SUCCESSでないため追加されない）。

**attempt 2**：`open_next_attempt()`は`attempt_count(1) < record.max_attempts`であることを確認した上で（`max_attempts=1`の場合はここでbudget exhaustionによりlineageが停止する。9.8.1.4章の数値例参照）、`steps_to_execute`は変わらず`["publish"]`（NEWS・REVIEWは既にconfirmed done、再度evaluate対象にすらならない）。PUBLISHのinterval guardが経過していれば、今回は`executed=True, success=True, action_taken=True`→`GENUINE_SUCCESS`。`attempt_count`は1→2に消費される。

**`decide_disposition()`**：`categories=[NOT_APPLICABLE, NOT_APPLICABLE, GENUINE_SUCCESS]` → `UNKNOWN`なし・`RETRYABLE_FAILURE`なし・`SILENT_NO_ACTION`なし → **`SUCCEEDED`**。

**確認事項**：
1. attempt 1でSUCCEEDEDへ誤判定されないこと（Round 4のBL-1修正が維持されていること）を確認。
2. **NEWS・REVIEWがattempt 2で再実行されず、両者自身のinterval guardによる`SILENT_NO_ACTION`がdisposition判定へ一切混入しないこと**（Round 4 reviewで独自発見したliveness問題の解消）を確認。
3. PUBLISH単独の実行が`target_step_filter`によって実際に実装レベルで保証されること（Round 4 reviewの「PUBLISH単独実行という主張が裏付けられていない」指摘の解消）を確認。
4. **（Round 9で追加）**`max_attempts=1`の場合、このトレースはattempt 1のNOT_ACTIONEDでbudgetが尽き、attempt 2（genuineな成功の機会）が一度も与えられないままlineageが停止することを確認する（9.8.1.3章のトレードオフ、Human Gate承認事項）。PUBLISHのinterval guard周期がretry cadenceより長い運用では、`max_attempts`をこの周期に対して十分大きく設定する必要がある。

### 11.7 reconcile_all()経路：`action_taken`の永続化による情報量ギャップの解消（**Round 5で全面改訂、Blocking Finding対応**）

#### 11.7.1 Round 4の欠陥の再確認

Round 4は、`StepExecutionRecord`が`action_taken`相当の情報を持たないため、`reconcile_all()`が`WorkflowMonitorStatus.SUCCESS`を根拠に`mark_terminal(SUCCEEDED)`を呼ぶ際、crash直前のsilent no-actionを検出できないことを「意図的に受容する残存ギャップ」として位置づけていた。しかしこれは6.31自身のGoal 7（「別のstepがsilent no-opである限りSUCCEEDEDとして確定しない」）に直接違反するため、単なる開示では不十分と判断した。

#### 11.7.2 Round 5の設計、Round 6で拡張、Round 7で厳密化：`StepExecutionRecord.action_taken`と`skip_category`の追加（closed-set semanticsの統一、Round 6 review M-1・M-2対応）

**採用：`StepExecutionRecord`へ`action_taken: bool | None = None`（Round 5）に加え、`skip_category: StepSkipCategory | None = None`（Round 6で追加、11.3.2章の`skip_category`をExecution History側にも実際に反映する）を追加する。旧レコード（本フィールド導入前に保存されたJSON）はいずれも`None`となり、`classify_execution_history_step()`はこれを`UNKNOWN`（fail-closed）として扱う。**

```python
# step_execution_record.py（追加分のみ）
@dataclass
class StepExecutionRecord:
    step: str
    status: StepExecutionStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    skipped_reason: str | None = None
    action_taken: bool | None = None                       # Round 5で新設。旧record読込時は必ずNone（後方互換）
    skip_category: StepSkipCategory | None = None            # Round 6で新設。旧record読込時は必ずNone（後方互換）

    def to_dict(self) -> dict:
        return {..., "action_taken": self.action_taken,
                "skip_category": self.skip_category.value if self.skip_category else None}

    @classmethod
    def from_dict(cls, data: dict) -> "StepExecutionRecord":
        raw_action_taken = data.get("action_taken")
        raw_skip_category = data.get("skip_category")
        return cls(
            ...,
            action_taken=(raw_action_taken if isinstance(raw_action_taken, bool) else None),
            # Round 7で追加（M-2対応）：action_takenはTrue/False/Noneの3値のみ許可する。
            # bool以外の型（文字列"false"・整数0・空list等、破損JSONに由来しうる値）は
            # 型不正としてすべてNoneへ正規化する。isinstance(x, bool)はPythonの
            # bool<int継承関係の落とし穴（0/1がintとして混入すること）を正しく排除する。
            # これによりclassify_execution_history_step()のUNKNOWN分岐へ確実にfail-closedする。
            skip_category=(StepSkipCategory(raw_skip_category)
                           if raw_skip_category in {c.value for c in StepSkipCategory}
                           else None),                        # 旧record・未知の値はいずれもNone
        )
```

`ExecutionHistoryManager.finish_step()`へ`action_taken: bool | None = None`・`skip_category: StepSkipCategory | None = None`の2引数を追加する。`WorkflowEngineExecutor`は、SUCCESS経路（`agent_result.success=True`の場合、既存行204-207）で`finish_step(..., StepExecutionStatus.SUCCESS, action_taken=agent_result.action_taken)`を渡す。SKIPPED経路（gate-closed・not-targetedいずれも既存行144-163・11.4.3章）では`finish_step(..., StepExecutionStatus.SKIPPED, skipped_reason=..., skip_category=<対応するStepSkipCategory>)`を渡す。NOT_REACHED・FAILED・RUNNING経路はいずれの引数も渡さない（`None`のまま、これらのstatusでは概念自体が無意味なため）。

**この追加は「Retry判定ロジックをExecution Historyへ持ち込む」ことには当たらないと判断する**：`action_taken`は`AgentResult`（`src/ai/agent_result.py`、retry概念の導入以前から存在するAgent実行層の型）が既に持つフィールドであり、`skip_category`もその値自体はWorkflow Engine実行層（gate closed／not targeted等）の構造的事実であり、retry・lineageドメイン固有の判定ロジックではない。`error_message`/`skipped_reason`と同格の、「実行時に何が起きたか」という事実の記録に留まる（10.4章の却下代案18の判断を、Round 5で撤回・修正した）。

```python
def classify_execution_history_step(step: "StepExecutionRecord") -> StepOutcomeCategory:
    if step.status == StepExecutionStatus.FAILED:
        return StepOutcomeCategory.RETRYABLE_FAILURE
    if step.status == StepExecutionStatus.RUNNING:
        return StepOutcomeCategory.RETRYABLE_FAILURE       # abandoned TIMEOUTの対象
    if step.status == StepExecutionStatus.NOT_REACHED:
        return StepOutcomeCategory.NOT_APPLICABLE
    if step.status == StepExecutionStatus.SKIPPED:
        if step.skip_category is None:
            return StepOutcomeCategory.UNKNOWN               # 構造化フィールド未設定＝防御的fail-closed
        if step.skip_category == StepSkipCategory.GATE_CLOSED:
            return StepOutcomeCategory.INTENTIONAL_NO_ACTION  # 同期パス（11.3.2章）との分類対称性
        if step.skip_category in (
            StepSkipCategory.NOT_REACHED,
            StepSkipCategory.HISTORY_WRITE_FAILED,
            StepSkipCategory.HOOK_NOT_ACKNOWLEDGED,
            StepSkipCategory.HOOK_EXCEPTION,
            StepSkipCategory.NOT_TARGETED,
        ):
            return StepOutcomeCategory.NOT_APPLICABLE
        return StepOutcomeCategory.UNKNOWN               # Round 7で追加（M-1対応）：既知enumを
                                                            # 明示的に列挙し尽くした残余（将来のenum
                                                            # 拡張等）はUNKNOWNへ防御的fail-closed。
                                                            # 同期パス（11.3.2章）の
                                                            # 「in (...)で列挙し、それ以外はUNKNOWN」
                                                            # というclosed-set semanticsと一字一句対称にする。
    if step.status == StepExecutionStatus.SUCCESS:
        if step.action_taken is True:
            return StepOutcomeCategory.GENUINE_SUCCESS
        if step.action_taken is False:
            return StepOutcomeCategory.SILENT_NO_ACTION
        return StepOutcomeCategory.UNKNOWN               # Round 7で改訂（M-2対応）：Noneはもちろん、
                                                            # 万一bool以外の値が直接構築等で紛れ込んだ
                                                            # 場合も、truthy判定ではなく恒等比較の
                                                            # 消去法でUNKNOWNへfail-closedする。
    return StepOutcomeCategory.UNKNOWN
```

**Round 6での変更点（Round 5 review H-3の解消）**：Round 5時点では`StepExecutionStatus.SKIPPED`を`skip_category`を一切参照せず一律`NOT_APPLICABLE`へ分類しており、(a) 同期パスが持つ`GATE_CLOSED→INTENTIONAL_NO_ACTION`という分類との非対称性、(b) 将来の未知の`skip_category`値に対する防御的`UNKNOWN`フォールバックの欠如、という2点の自己矛盾があった（11.3.2章で「`StepExecutionRecord`へも追加する」と述べていたにもかかわらず、11.7.2章では実際には追加していなかった）。Round 6で`skip_category`を実際に`StepExecutionRecord`へ追加し、同期パスと**構造的に対称な**分類ロジックへ修正した。`decide_disposition()`（11.5章）・`compute_newly_confirmed()`（11.4.3章）はいずれも`INTENTIONAL_NO_ACTION`と`NOT_APPLICABLE`を同一に扱う（判定に影響しない）ため、**この修正はdisposition決定という機能面には実害を持たなかったが**、防御的一貫性・将来の未知skip理由への耐性という点で必要な修正だった。

**Round 7での変更点（Round 6 review M-1・M-2の解消）**：Round 6の`classify_execution_history_step()`は、`SKIPPED`分岐で「`GATE_CLOSED`でなければ無条件に`NOT_APPLICABLE`」という**開いた集合（open-set）**の判定になっており、同期パス`classify_step_outcome()`（11.3.2章）が採用する「既知の5値を`in (...)`で明示的に列挙し、それ以外はUNKNOWN」という**閉じた集合（closed-set）**の判定と非対称だった。このため、将来`StepSkipCategory`へ新しい列挙値が追加された場合、同期パスはUNKNOWN（fail-closed）、reconcile経路はNOT_APPLICABLE（fail-open寄り）という食い違いが生じうる（M-1）。Round 7で両経路のロジックを一字一句対称な列挙＋UNKNOWNフォールバックへ統一した。

また`SUCCESS`分岐は、Round 6まで`if step.action_taken: ... else ...`というtruthy判定であり、`action_taken`に型不正な永続値（文字列`"false"`・整数`0`・空list等）が紛れ込んだ場合、`None`チェックをすり抜けて誤って`GENUINE_SUCCESS`／`SILENT_NO_ACTION`に分類されてしまう経路が存在した（M-2）。Round 7では`from_dict()`側で`action_taken`を`bool`型のみ許可（それ以外はNoneへ正規化、11.7.2章冒頭）した上で、分類ロジック自体も`is True`／`is False`の恒等比較＋消去法UNKNOWNへ改め、truthy判定を排除した。この2点の改訂は、同期パス（11.3.2章・11.4.5章直前で同様に改訂済み）と完全に対称なclosed-set semanticsを両経路で実現する。

**この設計により**：`reconcile_all()`は、`action_taken`・`skip_category`が記録されている（＝6.31導入後に生成された）recordについては、同期パス（11.5章）と**完全に同一のロジック**でSILENT_NO_ACTIONを検出できるようになり、17章crash matrix#17（reconcile経由のsilent-success誤判定）が解消される。旧record（`action_taken=None`）については`UNKNOWN`→`decide_disposition()`は`FAILED`（fail-closed、no payback）を返す。**これはRound 4までの「SUCCESS扱いしてしまう」という危険側の挙動から、「fail-closedでFAILEDとして扱い再試行する」という安全側の挙動への変更である**（旧recordに対する挙動変化そのものは意図的かつ安全側）。

#### 11.7.3 `resolve_next_target_from_execution_history()`との統合

`resolve_next_target_from_execution_history()`は、`classify_execution_history_step()`の結果を用いて11.4章と同一の`compute_newly_confirmed()`/`compute_steps_to_execute()`ロジックを適用する（`action_taken`ベースのGENUINE_SUCCESS判定が可能になったため、同期パスと同じ関数を共有できる。実装フェーズで`WorkflowEngineStepResult`/`StepExecutionRecord`いずれからも`classify_step_outcome()`相当の結果を得られるアダプタとして統合するか確認する）。

#### 11.7.4 Legacy Contract：旧record再実行の安全性の事実確認（**Round 6で新設、Round 7で事実訂正：Round 6 review M-3・M-4対応**）

Round 5は「旧record（`action_taken=None`）に対応するstepはUNKNOWNとして扱われ、`steps_confirmed_done`の初期値に含まれず、再実行対象になる」ことについて「実害はない」と根拠なく述べていた。Round 6では、実際にNEWS/REVIEW/PUBLISHの各実行対象サービスを確認し、再実行が引き起こす影響を事実ベースで記載したが、Codex Round 6 reviewにより、PUBLISHの戻り値に関する記述の事実誤り（M-3）と、REVIEWリスクの過小評価（M-4：「未確認」としていたが実際にはread-onlyコード確認で確定可能だった）が指摘された。Round 7でいずれも訂正する：

| step | 再実行時の挙動（実コード確認、Round 7で訂正） | 評価 |
|---|---|---|
| **PUBLISH** | `AiPublishService.run()`（`src/ai/ai_publish_service.py:90-117`）は`filter_unpublished()`（`src/ai/ai_publish_repository.py:106-127`）を必ず経由し、**既に`success=True`のAiPublishResultが存在するarticle_idを対象から除外する既存の冪等性ガードを持つ**。旧recordに対応するlineageのPUBLISHが既にgenuineに成功していた場合、再実行では`targets`が空になり、**WordPressへの重複投稿は発生しない**。**（Round 7で訂正）**ただし`targets`が空であっても`run()`は`report_content = self._builder.build([])`（空レポート）を無条件に構築し、`_save_report()`が成功すればそのPathを返す——`report_path=None`にはならない。`run()`自体は`success`という戻り値を持たない（成否は個々の`AiPublishResult`が持つ概念であり、`run()`全体の戻り値ではない）。Round 6版の「対象記事が存在しないため`report_path=None`（`success=False`）となる」という記述は**事実誤りであり削除する**。 | **安全（重複投稿なし）、ただし戻り値の記述をRound 7で訂正**：外部副作用の重複は発生しない。実際の戻り値（空レポートのPath）を正確に記述する。 |
| **REVIEW** | `AiPublishReviewService.run()`（`src/ai/ai_publish_review_service.py:81-103`）は`load_publish_results()`が返す**全件**を対象に`save_review()`を呼ぶ。`save_review()`（`src/ai/ai_publish_review_repository.py:83-106`）は`outputs/ai_publish_reviews/{reviewed_at:%Y%m%d}_{article_id}_publish_review.json`というファイル名で保存する——**article_id単独キーの真のupsertではなく、「日付＋article_id」キーの疑似冪等**である。同一日内の再実行は同一ファイルを上書きするが、**日をまたいだ再実行は別ファイルとして残る（重複生成）**。さらに`load_reviews()`（同ファイル108-128行）は`review_dir`配下の`*_publish_review.json`を**article_idによるdedupなしで全件読み込む**。**（Round 8で具体的根拠を追加、M-new-2対応）**この重複が実際に生産コードで二重計上される経路を`workflow_step_executor.py`で確認した：`PublishReviewStepExecutor.execute()`（`src/ai/workflow_step_executor.py:295-321`、特に`reviews = self._service.get_reviews(article_id=context.article_id)` → `processed_count=len(reviews)`、l.310-317）は、`AiPublishReviewService.get_reviews(article_id=...)`（`ai_publish_review_service.py:105-117`）→`AiPublishReviewRepository.load_reviews_by_article_id(article_id)`（`ai_publish_review_repository.py:130-140`、`load_reviews()`をarticle_idでフィルタするのみでdedupしない）という経路を通り、`WorkflowStepResult.processed_count`（`PUBLISH_REVIEW` stepの実行結果としてExecution Historyへ記録される値）を実際に水増しする。この`PublishReviewStepExecutor`は`workflow_runner.py:100-102`で`AiPublishReviewService.from_paths(...)`として実際に本番配線されていることも確認済み。一方、この重複が過去の人間のレビュー判断を実際に上書き・無効化するかどうか（downstreamでの判断消費ロジックの詳細）は、本reviewのコード確認範囲を超えて**断定しない**。 | **確認済みの残存リスク**：外部副作用（WordPress等）ではなく内部データストアの重複だが、「日またぎ重複生成＋dedupなしの二重計上」という実害は`workflow_step_executor.py:310-317`の`processed_count`水増しとして具体的に確認済みの事実である。人間判断への影響は未確定のままHuman Gateへ明示する（26章）。 |
| **NEWS** | `NewsPipelineRunner`は`main.py`を再度subprocessとして起動し、ニュース収集を再実行する。収集済み記事の重複防止は`main.py`側の既存ロジックに依存する（本書のスコープ外、変更なし）。 | **既存の許容範囲内**：NEWSの重複収集防止は6.31以前から`main.py`側の責務であり、本Releaseによる新規リスクではない。 |

**結論**：旧record再実行による外部副作用の重複は、**PUBLISHについては`filter_unpublished()`ガードにより実質的に発生しない**（ただし戻り値の記述はRound 7で訂正した——空report保存・Path返却はあり得る）。REVIEWについては、**日またぎ重複ファイル生成＋`load_reviews()`側のdedupなし二重計上**という内部データの実害を、確認済みの事実として26章Human Gateへ明記する（人間判断そのものへの影響は未断定）。NEWSは既存スコープの範囲内。4章Non-Goalsが明記するとおり、これら既存ガードの新規強化は6.31のスコープ外である。

### 11.8 却下した代案（Round 1〜4から維持、Round 5で追加・一部撤回）

（Round 1〜4の却下代案は旧版参照。**10.4章の却下代案18（Execution Historyへの`action_taken`追加）は、11.7.2章の理由により本Roundで撤回する**。）

- **（Round 5で追加）代案：dependency closureモデル（11.4.2章 (b)）を採用する。** 却下理由：11.4.1章の実コード確認により、step間の実データ依存が存在しないことを確認した。依存が存在しない以上、closure計算は無用な複雑さを追加するのみ。
- **（Round 5で追加）代案：target集合を都度置き換える単一targetモデル（Round 4の設計）を維持する。** 却下理由：11.4.4章のとおり、NOT_REACHED stepを誤って実行対象から除外するリスクを構造的に持つ。累積的な`steps_confirmed_done`モデルはこのリスクを持たない。
- **（Round 5で追加）代案：全step再実行（フィルタなし）を維持し、liveness問題は運用（cooldown調整等）で緩和する。** 却下理由：Round 4 reviewで発見したとおり、各stepのinterval guardの組み合わせ次第では理論上無期限にSUCCEEDEDへ到達できない場合があり、運用パラメータ調整では根本解決にならない。
- **（Round 7で追加）代案：`mark_terminal()`が引き続き無条件に次attempt用scopeを計算・記録する（Round 5〜6の設計を維持する）。** 却下理由：B-1（12章）。全stepがgenuineに完了した正常なSUCCEEDED終端で空scope防御が誤発火し、dispositionが誤って`FAILED`へ変換される。terminal化とscope生成の責務を分離することでのみ構造的に解消できる。
- **（Round 7で追加）代案：`action_taken`／`skip_category`の型不正値・未知値をtruthy判定や緩い包含判定（`!= GATE_CLOSED`等）のまま扱い続ける。** 却下理由：M-1・M-2（11.7.2章）。将来のenum拡張や永続データの型破損に対してfail-openしうる。同期経路が既に採用している「既知値を列挙し、それ以外はUNKNOWN」という閉集合判定へ両経路を統一する。

---

## 12. State Machine（**Round 5で軽微改訂：11章の`steps_confirmed_done`モデルを反映。Round 7でterminal/scope責務を分離**）

状態機械そのもの（`READY_ELIGIBLE → CLAIMED → EXECUTION_STARTED → TERMINAL`、disposition不問でのTERMINAL到達、12.3節のformal invariants）はRound 3から変更しない（旧版参照）。**Round 5での変更点は入力の出所のみ**：

- `mark_terminal(root_run_id, disposition, executed_run_id, newly_confirmed_steps)`へ渡す`disposition`・`newly_confirmed_steps`は、**11.5章の`decide_disposition(engine_result)`／11.4.3章の`compute_newly_confirmed(engine_result)`**（同期パス）または**11.7.2〜11.7.3章の`classify_execution_history_step()`ベースの同一ロジック**（reconcile_all()パス）から導出する。

**（Round 7で全面改訂：B-1対応）`mark_terminal()`と`open_next_attempt()`の責務分離**：Round 5〜6は「`mark_terminal()`が`steps_confirmed_done`の更新に加えて、`attempt_scopes`へ次attempt用のscopeも記録する」としていたが、これがB-1（disposition不問の無条件scope計算により、正常なSUCCEEDED終端が誤ってFAILEDへ変換されうる欠陥）の原因だった。Round 7で以下のとおり責務を明確に分離する：

- **`mark_terminal()`の責務は、現在attemptをTERMINAL化し、confirmed stateを保存することのみに限定される。** `newly_confirmed_steps`を`lineage.steps_confirmed_done`へ合成（`set`union）し、`phase=TERMINAL`・`terminal_disposition=disposition`・`latest_run_id=executed_run_id`を記録する。**`attempt_scopes`への書き込みは一切行わない。**
- **`open_next_attempt()`のみが、attempt 2以降の次attempt用の`RetryAttemptExecutionScope`を`attempt_scopes`へ追加する責務を持つ**（attempt 1用のscopeは`create_new_lineage()`（7.2章）が書く、11.4.3・13章。以下「唯一の書き手」と述べる場合は常にこのattempt 2以降を指す）。この生成は9.8.1章の判定式（`terminal_disposition in (FAILED, NOT_ACTIONED)`かつ`attempt_count < max_attempts`、いずれもdurable stateのみに基づく）を満たす場合に**限り**行われる。`terminal_disposition==SUCCEEDED`の場合、`open_next_attempt()`は16章(b)の走査条件（`terminal_disposition in (FAILED, NOT_ACTIONED)`）によりそもそも呼ばれないため、**SUCCEEDED終端において全stepがconfirmed済みであり次scopeが概念上「空」であることは、構造的に一切問題にならない（正常）**。これによりB-1を構造的に解消する。
- **retryable terminalで次scopeが空になる場合（11.4.5.2章）**：`open_next_attempt()`は`compute_steps_to_execute(lineage.steps_confirmed_done)`が空集合を返す場合、これを`steps_confirmed_done`破損によるinvariant violationとして扱い、`READY_ELIGIBLE`への遷移を拒否する（ack=False、`phase`は`TERMINAL`のまま）。理論上、retryable dispositionは「今回のattemptで少なくとも1つのstepがGENUINE_SUCCESS以外だった」ことを意味するため、この経路への到達は正常運用では起こらないはずだが、`steps_confirmed_done`の破損等により万一到達した場合の防御である。

```python
# retry_lineage_manager.py（Round 9改訂：mark_terminal()、payback補正を撤回、9.8.1.3章対応）
def mark_terminal(
    self, root_run_id: str, disposition: RetryLineageDisposition,
    executed_run_id: str, newly_confirmed_steps: list[str],
) -> MarkTerminalResult:
    with self._store_lock():
        record = self._store.get(root_run_id)
        if record is None or record.phase != RetryLineagePhase.EXECUTION_STARTED:
            return MarkTerminalResult(acknowledged=False, reason="phase mismatch: not EXECUTION_STARTED")
        record.steps_confirmed_done = sorted(set(record.steps_confirmed_done) | set(newly_confirmed_steps))
        record.phase = RetryLineagePhase.TERMINAL
        record.terminal_disposition = disposition
        record.latest_run_id = executed_run_id
        # attempt_countはここでは一切書き換えない（Round 9でpayback補正を撤回、
        # MAJ-R8-2対応）。FAILED/NOT_ACTIONED/SUCCEEDEDいずれのdispositionでも、
        # mark_execution_started()時点で消費済みの値（9.5章）がそのまま残る。
        # attempt_scopesへの書き込みも一切行わない（Round 7、B-1対応）。
        # 次attempt用scopeの生成はopen_next_attempt()の専管責務とする。
        self._store.save(record)
        return MarkTerminalResult(acknowledged=True)


# retry_lineage_manager.py（Round 9改訂：open_next_attempt()、record.max_attemptsを参照、9.8.1章対応。
# Round 10改訂：steps_to_execute書き込み時にcanonicalize、MIN-R9-1対応）
def open_next_attempt(self, root_run_id: str) -> OpenNextAttemptResult:
    with self._store_lock():
        record = self._store.get(root_run_id)
        if record is None or record.phase != RetryLineagePhase.TERMINAL:
            return OpenNextAttemptResult(acknowledged=False, reason="phase mismatch: not TERMINAL")
        if record.terminal_disposition not in (RetryLineageDisposition.FAILED, RetryLineageDisposition.NOT_ACTIONED):
            # SUCCEEDEDはここへ到達しない設計（16章(b)の走査条件）だが、defense-in-depthとして明示的に拒否する。
            return OpenNextAttemptResult(acknowledged=False, reason="terminal_disposition is not retryable")
        if record.attempt_count >= record.max_attempts:
            # 9.8.1.2章の判定式：durable state（record.attempt_count・record.max_attempts、
            # いずれもRetryLineageRecord自身のフィールド）のみで判定する。monitor_statusは
            # もちろん、RetryPolicy.max_attempts（設定値）すら都度参照しない
            # （Round 9でMAJ-R8-1・MAJ-R8-3を解消、7.1・9.8.1章）。
            return OpenNextAttemptResult(acknowledged=False, reason="max_attempts exhausted")

        # Architecture Amendment（Draft、Code Review Major#4対応）：next_attempt_ordinal
        # 不変条件の検証。open_next_attempt()はこの後next_attempt_ordinalへ+1した値を
        # 書き込むため、書き込み前の時点で現在値がattempt_scopes[-1].attempt_noと
        # 同期していることを確認する（claim()と同一のチェック、12章）。
        if record.attempt_scopes and record.next_attempt_ordinal != record.attempt_scopes[-1].attempt_no:
            return OpenNextAttemptResult(
                acknowledged=False,
                reason=(
                    f"invariant_violation: next_attempt_ordinal ({record.next_attempt_ordinal}) "
                    f"!= attempt_scopes[-1].attempt_no ({record.attempt_scopes[-1].attempt_no}). "
                    f"Refusing to open next attempt (no auto-repair)."
                ),
            )

        steps_to_execute = compute_steps_to_execute(record.steps_confirmed_done)
        if not steps_to_execute:
            # invariant violation：retryable dispositionにもかかわらずsteps_confirmed_doneが
            # 全stepをカバーしている（本来ここへは到達しないはず）。READY_ELIGIBLEへは遷移せず、
            # phase=TERMINALのままfail-closedで停止する（11.4.5.2章）。
            return OpenNextAttemptResult(
                acknowledged=False,
                reason="invariant_violation: steps_confirmed_done covers all steps while "
                       "terminal_disposition is retryable (expected at least one unresolved "
                       "step this attempt). Refusing to open next attempt with an empty "
                       "execution scope.",
            )

        # Architecture Amendment（2026-08-31、Human Gate承認済み。§0参照）：
        # next_attempt_ordinalはattempt_scopes[-1].attempt_noと常に同期する
        # 非正規化コピーとして確定した。新しいattempt番号（現在値+1）をここで
        # 払い出し、新しいscope・record.next_attempt_ordinal双方へ同時に反映する。
        next_attempt_no = record.next_attempt_ordinal + 1
        next_scope = RetryAttemptExecutionScope(
            attempt_no=next_attempt_no,
            steps_confirmed_done_before=list(record.steps_confirmed_done),
            # Round 10で追加（MIN-R9-1対応）：保存直前に明示的にcanonicalizeする。
            # compute_steps_to_execute()自体が既にcanonical orderで返す不変条件
            # （11.4.3章）を持つが、7.3章の共通ヘルパーをここでも通すことで、
            # 「stored authoritative scope自体がcanonicalである」契約を
            # create_new_lineage()（7.2章）と同一の構造で保証する。
            steps_to_execute=_canonicalize_step_order(steps_to_execute),
            determined_at=now(),
        )
        record.attempt_scopes.append(next_scope)
        record.phase = RetryLineagePhase.READY_ELIGIBLE
        record.terminal_disposition = None
        record.next_eligible_at = None  # 9.8.1章：本Releaseでは常にNone（25章Risk#3参照）
        record.next_attempt_ordinal = next_attempt_no
        self._store.save(record)
        return OpenNextAttemptResult(acknowledged=True, attempt_no=next_scope.attempt_no)
```

- `mark_terminal()`／`open_next_attempt()`はいずれも、9.3章で確立した**唯一のグローバル境界（`RetryExecutionLock`）の内側**からのみ呼ばれる（`_retry_locked()`または`_reconcile_all_locked()`経由、Round 4から変更なし）。これにより、Round 3レビューで指摘された「同一mutation APIを使うことと、実際に直列化された制御フローであることの乖離」（MJ-2旧）が解消される。

**`mark_terminal()`のack=False時の扱い（Round 4で明文化、Round 7で対象を明確化、Architecture Amendment（Draft、Code Review Blocking#2対応）で呼び出し元を訂正）**：9.3.3章の排他統一により、`retry()`実行中に`reconcile_all()`が同一lineageを操作することは構造的に発生しなくなったため、`mark_terminal()`呼び出しが「phase不一致によりack=False」を返す事態は、正常運用下では**理論上到達しない防御的分岐**となる。**この呼び出しは`_retry_locked()`自身ではなく`RetryExecutor.execute()`内で行われる（10.2.4章）**——Round 4〜11は誤って`_retry_locked()`と記述していたため、この契約が実装へ反映されなかった（Blocking#2）。万一到達した場合（`RetryLineageStoreLock`書き込み失敗等、9.2章のfail-closed経路）、`RetryExecutor.execute()`は追加のretryを行わず、`RetryOutcome.SKIPPED`（診断reasonつき）を返す。実行済みの副作用（`.run()`の結果）はExecution History側に既に記録されているため、次回`reconcile_all()`サイクルで`phase==EXECUTION_STARTED`のまま検出され、17章crash matrixのケース8と同一経路で解消される。

**`open_next_attempt()`のack=False時の扱い（Round 7で新設、Round 8でbudget exhaustion経路を明確化、Round 9で`record.max_attempts`参照へ更新、Architecture Amendment（Draft、Code Review Major#4対応）で(d)を追加）**：ack=Falseとなる経路は4つある。(a) phase不一致（TERMINALでない）または`terminal_disposition`がretryableでない——正常運用下で16章(b)の走査条件により理論上到達しない防御的分岐。(b) **（9.8.1章の判定式による、正常かつ意図された終端）**`record.attempt_count >= record.max_attempts`——`steps_confirmed_done`等の破損とは無関係の、budget消費契約どおりの正常な終端であり、異常ではない（`NOT_ACTIONED`のpayback廃止により、`FAILED`・`NOT_ACTIONED`を問わず一様にこの経路へ到達しうる、9.8.1.3章）。lineageは`phase==TERMINAL`のまま残り、以後`open_next_attempt()`は再試行されない（`reconcile_all()`の16章(b)走査は、この場合もack=Falseを受けて何もしない。再試行してもattempt_countが変わらない限り結果は同じであり、無害だが無益なので、実装は同一lineageへの重複走査を避けてよい）。(c) 11.4.5.2(b)章のinvariant violation（次scopeが空）——`steps_confirmed_done`が破損している場合にのみ到達し、cooldownとは異なり時間経過で自然解消しない。(c)の場合、lineageは`phase==TERMINAL`のまま恒久的に残り、`reconcile_all()`は次回`run_once()`サイクルでも`open_next_attempt()`を再試行するが、破損が解消されない限り毎回同じくack=Falseとなる（純粋な再計算のみで書き込みは発生しないため、この繰り返し自体は無害）。(d) **（Architecture Amendment新設）**`next_attempt_ordinal != attempt_scopes[-1].attempt_no`のinvariant violation（12章）——(c)と同様`steps_confirmed_done`/`attempt_scopes`/`next_attempt_ordinal`いずれかの破損時にのみ到達し、時間経過で自然解消しない。18章の診断機能は(c)・(d)の状態を異常として検出する（(b)は正常終端のため診断対象に含めない）。

---

## 13. Minimal Durable Retry Control State スキーマ（**Round 5で改訂：`steps_confirmed_done`モデルへの移行**）

**採用：`RetryAttemptTargetSnapshot`（単一target置き換えモデル、Round 3〜4）を廃止し、`steps_confirmed_done`（累積・monotonic）＋attempt単位の実行scope記録へ置き換える（11.4章）。**

```python
@dataclass
class RetryLineageMembershipEntry:            # Round 1〜4から変更なし
    run_id: str
    parent_run_id: str | None
    attempt_no: int
    recorded_at: datetime

@dataclass
class RetryLineageTransitionEvent:            # Round 5で`correlation_id`追加
    attempt_no: int
    from_phase: RetryLineagePhase | None
    to_phase: RetryLineagePhase
    run_id: str | None
    at: datetime
    detail: str | None = None
    correlation_id: str | None = None          # Round 5で新設（10.3.2章）。to_phase==CLAIMEDでのみ設定

@dataclass
class RetryAttemptExecutionScope:              # Round 5で新設（RetryAttemptTargetSnapshotを置き換え）
    attempt_no: int
    steps_confirmed_done_before: list[str]      # このattempt開始時点で既にGENUINE_SUCCESS確定済みのstep
    steps_to_execute: list[str]                  # このattemptでtarget_step_filterとして渡すstep集合
    determined_at: datetime

@dataclass
class RetryLineageRecord:
    root_run_id: str
    parent_run_id: str | None
    latest_run_id: str
    attempt_count: int                            # Round 9で意味を再確定：mark_execution_started()ack時にのみ
                                                    # +1する（9.5章）。dispositionを問わず一切減算されない
                                                    # （Round 8のNOT_ACTIONED payback補正はRound 9で撤回、
                                                    # MAJ-R8-2対応、9.8.1.3章）。「実行を開始した試行回数」＝
                                                    # 「budgetを消費した試行回数」を表すdurable値。
    max_attempts: int                              # Round 9で新設（MAJ-R8-1対応）。lineage作成時に
                                                    # RetryPolicy.max_attemptsからsnapshotされ、以後不変
                                                    # （7.2・9.8.1章）。RETRY_MAX_ATTEMPTS環境変数の運用中
                                                    # 変更は既存lineageへ遡及しない。Round 10で追加
                                                    # （MAJ-R9-2対応）：snapshot時点でcreate_new_lineage()が
                                                    # 整数かつ>=0であることを検証済み（不正値はlineage自体を
                                                    # 作成しない、fail-closed）。既存lineage再接続
                                                    # （find_existing_lineage()、7.1章）はこのフィールドへ
                                                    # 一切書き込まないため、再snapshot・再検証は行われない。
    next_attempt_ordinal: int  # Architecture Amendment（2026-08-31、Human Gate承認済み。§0参照）：
                                # attempt_scopes[-1].attempt_noと常に同期する非正規化コピー
                                # として確定。「次に払い出すordinal」ではなく「現在openな
                                # attemptのordinal」を表す（10.3.3章(b)のexact-match要件の前提）。
    phase: RetryLineagePhase
    terminal_disposition: RetryLineageDisposition | None
    next_eligible_at: datetime | None
    owner_token: str | None
    steps_confirmed_done: list[str]              # Round 5で新設：append-only、monotonic（11.4.3章）
    membership: list[RetryLineageMembershipEntry]
    transition_history: list[RetryLineageTransitionEvent]
    attempt_scopes: list[RetryAttemptExecutionScope]   # Round 5で新設（RetryAttemptTargetSnapshotの置き換え）
    created_at: datetime
    updated_at: datetime
```

**（Round 7で明確化、B-1対応。Round 10で対象メソッド名を更新、7.2章対応）**：`attempt_scopes`へ`RetryAttemptExecutionScope`エントリを追加するコードパスは、(1) `create_new_lineage()`（attempt 1用、7.2・11.4.3章）と、(2) `open_next_attempt()`（attempt 2以降用、12章）の**2箇所のみ**である。`mark_terminal()`は`attempt_scopes`を一切書き込まない（12章）。**（Round 10で追加、MIN-R9-1対応）**この2箇所はいずれも、保存直前に7.3章の`_canonicalize_step_order()`を通した値を`steps_to_execute`として書き込む——stored valueが常にcanonicalであることは、書き込み経路そのものの契約である。`find_existing_lineage()`（分岐(1)(2)）はこの2箇所に含まれず、`attempt_scopes`を含む`RetryLineageRecord`のいかなるフィールドも書き換えない。

`claim()`の戻り値`ClaimResult`は`attempt_no`（このattemptに割り当てられるordinal）・`correlation_id`（このCLAIMEDイベント用に新規発行、10.3.2章）・`steps_to_execute`（`target_step_filter`としてそのまま利用可能）を含む。**（Round 8で明確化、MN-new-1対応）**：`steps_to_execute`は`attempt_scopes[-1].steps_to_execute`（保存済み値）を**authoritative**として採用する。`claim()`は`record.steps_confirmed_done`から`steps_to_execute`を独立に再計算するが、これは保存済み値の整合性を検証するためだけのvalidation専用処理であり、再計算値そのものを採用することはない。両者が完全一致しない場合（空集合か否かを問わない）、`claim()`は自動修復を行わずfail-closedする（11.4.5.2章(a)）。

`RetryLineageConfig`・保存先パス・lockファイルパス（`.lock`＝`RetryLineageStoreLock`、`.execution.lock`＝`RetryExecutionLock`）はRound 3から変更なし。

```python
class StepOutcomeCategory(Enum):    # 11.3章
    GENUINE_SUCCESS       = "genuine_success"
    RETRYABLE_FAILURE     = "retryable_failure"
    SILENT_NO_ACTION      = "silent_no_action"
    INTENTIONAL_NO_ACTION = "intentional_no_action"
    NOT_APPLICABLE        = "not_applicable"
    UNKNOWN               = "unknown"

class StepSkipCategory(Enum):        # Round 5で新設（11.3.2章）
    GATE_CLOSED           = "gate_closed"
    NOT_REACHED           = "not_reached"
    HISTORY_WRITE_FAILED  = "history_write_failed"
    HOOK_NOT_ACKNOWLEDGED = "hook_not_acknowledged"
    HOOK_EXCEPTION        = "hook_exception"
    NOT_TARGETED          = "not_targeted"
```

---

## 14. コンポーネント別変更内容（**Round 5で改訂**）

> **Human Gate候補（未承認）**：`StepExecutionRecord.action_taken`・`skip_category`追加、`target_step_filter`によるWorkflow Engine実行制御の追加、`mark_terminal()`／`open_next_attempt()`間のterminal/scope責務分離（Round 7、B-1対応）は、いずれも26章で明示の承認事項とする。

### 新設：`src/retry_lineage/`（Round 3から変更なし、旧版参照）

### 変更：`src/retry_engine/`

- `retry_manager.py`：`retry()`（公開API、`RetryExecutionLock`取得のみ）と`_retry_locked()`（内部専用、実処理）へ分離（9.3.2章）。**（Round 10で全面改訂、MAJ-R9-1対応）**`_retry_locked()`は`find_existing_lineage()`（7.1章、Monitor不要）を先に呼び、既存lineageが見つかった場合は`self._monitor.get_status(run_id)`自体を呼ばない。見つからなかった場合にのみ`self._monitor.get_status(run_id)`を取得し`create_new_lineage()`（7.2章）へ渡す。`RetryPolicy.should_retry()`は直接呼ばない（`create_new_lineage()`内部でのみ、新規lineage作成時に一度だけ行う）。`release_claim()`の呼び出し箇所（旧: should_retry失敗時）は、admission判定がclaim()より前へ移動したことに伴い不要のまま。**（Round 11で改訂、SUG-R11-3対応でRound 11 Cleanupにて記述を整理）**`self._monitor.get_status(run_id)`の戻り値を保持する変数は、旧`monitor_status`という名から`monitor_record`（型は`WorkflowMonitorRecord`、`.monitor_status`・`.steps`の両フィールドを持つ）へ改名した。`create_new_lineage()`の第2引数も同じ`monitor_record`をそのまま受け取る（9.3.2章）。
- `retry_executor.py`：post-admission hookクロージャの構築（`correlation_metadata`のnamespace化・`correlation_id`受け渡しを含む、10.3.2章）。`claim()`が返す`steps_to_execute`を`target_step_filter`として`.run()`へ渡す（11.4章）。**（Architecture Amendment（Draft）、Code Review Blocking#1・#2対応で確定）**`.run()`完了後、まずhookのdurable ack成否を確認する。未ackの場合は`decide_disposition()`／`mark_terminal()`のいずれも呼ばず`release_claim()`＋`RetryOutcome.SKIPPED`を返す。ackの場合のみ`decide_disposition()`（11.5章）でdispositionを、`compute_newly_confirmed()`（11.4.3章）で`steps_confirmed_done`への追加分を算出し`mark_terminal()`を呼ぶ——`mark_terminal()`のdurable ack（`MarkTerminalResult.acknowledged`）を必ず確認し、False時は`RetryOutcome.SKIPPED`を返す（10.2.4章）。
- `retry_genuine_action.py`：`StepOutcomeCategory`・`StepSkipCategory`・`classify_step_outcome()`・`classify_execution_history_step()`を提供する（11.3・11.7章）。
- `retry_target_resolution.py`：**（Round 5で拡張）**`decide_disposition()`（11.5章）・`compute_newly_confirmed()`・`compute_steps_to_execute()`（11.4.3章）・`resolve_next_target_from_execution_history()`は廃止し`classify_execution_history_step()`＋共通の`compute_*`関数へ統合（11.7.3章）。**（Round 10で追加）**`_canonicalize_step_order()`（7.3章）。**（Round 11で追加、MAJ-R10-2対応）**`compute_initial_confirmed_steps()`（7.2.2章、`create_new_lineage()`のattempt 1初期化専用）。
- `retry_runtime_orchestrator.py`：Round 3〜4から変更なし。

### 変更：`src/retry_lineage/`

- `retry_lineage_manager.py`：`reconcile_all()`（公開API）と`_reconcile_all_locked()`（内部専用）の分離（9.3.2章、Round 4から変更なし）。**（Round 5で追加）**`claim()`が`steps_to_execute`・`correlation_id`を算出し`ClaimResult`へ含める（13章、Round 8で保存済み`attempt_scopes[-1]`をauthoritativeとする形へ改訂）。**（Round 7で明確化、B-1対応）**`mark_terminal()`は`steps_confirmed_done`の更新とTERMINAL化のみを行い、`attempt_scopes`へは書き込まない。`open_next_attempt()`が`attempt_scopes`へattempt 2以降の次attempt用scopeを追加する唯一の責務を持つ（attempt 1用は`create_new_lineage()`が書く、7.2・11.4.5・12・13章）。**（Round 8で追加、Round 9で確定、M-new-1・MAJ-R8-1〜3対応）**`open_next_attempt()`のretry可否判定は`record.terminal_disposition`・`record.attempt_count`・`record.max_attempts`という、いずれも`RetryLineageRecord`自身が持つdurable stateのみに基づく判定式（9.8.1章）で行い、`monitor_status`にも外部の`RetryPolicy`にも一切依存しない。**（Round 9で撤回）**Round 8で導入した`mark_terminal()`の`NOT_ACTIONED`時payback補正（`attempt_count`の-1）は、無制限retryのliveness問題（MAJ-R8-2）を招くため撤回した——`mark_terminal()`は`attempt_count`をいかなるdispositionでも書き換えない（9.8.1.3章）。**（Round 10で全面改訂、MAJ-R9-1・MAJ-R9-2・MIN-R9-1対応）**旧`resolve_or_create()`は`find_existing_lineage()`（分岐(1)(2)専用、read-only、`monitor_status`不要）と`create_new_lineage()`（分岐(3)専用、`monitor_status`を受け取りinitial admission判定・`max_attempts`のsnapshot・validationを行う）へ分離する（7.1・7.2章）。`create_new_lineage()`・`open_next_attempt()`はいずれも`attempt_scopes`書き込み時に`_canonicalize_step_order()`（7.3章）を通す。**（Round 11で改訂、MAJ-R10-1・MAJ-R10-2・MIN-R10-1対応）**`create_new_lineage()`の第2引数を`monitor_status`から`monitor_record`（`WorkflowMonitorRecord`）へ変更し、`max_attempts` snapshotのvalidationを`should_retry()`より前へ移動、attempt 1の`steps_confirmed_done`を`monitor_record.steps`から`compute_initial_confirmed_steps()`（7.2.2章）で導出する（7.2章）。`claim()`（11.4.5.2(a)章）は独自インライン実装ではなく`_canonicalize_step_order()`を実際に呼ぶ形へ修正する。**（Architecture Amendment（Draft）、Code Review Major#3・#4対応で追加）**`create_new_lineage()`はグローバルmembership一意性チェック（7.2章）を追加する。`claim()`・`open_next_attempt()`はいずれも`next_attempt_ordinal == attempt_scopes[-1].attempt_no`のinvariant検証を追加する（12章）。`reconcile_all()`（`_reconcile_all_locked()`）は`phase==CLAIMED`のorphan回収走査（16章(c)）を追加する。

### 変更：`src/retry_enqueue_trigger/`

- `retry_enqueue_trigger.py`：**（Round 5で変更）**membership-first・correlation-fallback・exact-match（10.3.3章）の2段階ロジックへ改訂。

### 変更：`src/workflow_engine/`

- `workflow_engine_executor.py`：hook失敗時の`history_closed`規律（10.2.2章）に加え、**（Round 5で追加）**`target_step_filter`によるnot-targeted skip分岐（`skip_category=NOT_TARGETED`、11.4.3章）、および全skip分岐への`skip_category`明示的設定（11.3.2章）。`correlation_metadata`を`start_run()`へ渡す。
- `workflow_engine_manager.py`：**（Round 5で追加）**`run()`へ`target_step_filter: list[WorkflowEngineStep] | None = None`を追加。
- `workflow_engine_result.py`：**（Round 5で追加）**`WorkflowEngineStepResult`へ`skip_category: StepSkipCategory | None = None`フィールドを追加。
- 他ファイル（`workflow_engine_context.py`・`workflow_engine_post_admission_hook.py`）：Round 3〜4から変更なし。

### 変更：`src/execution_history/`

- `execution_history_manager.py`：`start_run()`の`correlation_metadata: dict[str, dict[str, str]] | None`（Round 4から維持）。`finish_step()`へ`action_taken: bool | None = None`引数を追加（Round 5）。**（Round 6で追加）**`finish_step()`へ`skip_category: StepSkipCategory | None = None`引数を追加（11.7.2章）。
- `step_execution_record.py`：`action_taken: bool | None = None`フィールドを追加（Round 5）。**（Round 6で追加）**`skip_category: StepSkipCategory | None = None`フィールドを追加。`from_dict()`は`data.get("action_taken")`／未知値を`None`とする`skip_category`パース（いずれもキー欠落・旧record後方互換）。
- `workflow_execution_record.py`：`correlation_metadata`フィールドの型・`from_dict()`後方互換（Round 4から維持）。

### 変更：`src/retry_composition/`（Round 1〜3から変更なし）

---

## 15. 6.30 Inherited Contracts（継承必須契約）（**Round 4で更新**）

| 6.30契約 | 6.31での扱い |
|---|---|
| canonical retryable recordは`WorkflowExecutionRecord`のみ | 変更なし。`correlation_metadata`は意味非解釈の汎用フィールドであり、この契約を破らない（10.3.2章）。 |
| Canonical Admission Failure Governance Exception | 変更なし。 |
| `history_write_failed`／terminal immutability | 変更なし。**（Round 4で強化）**hook失敗時のNOT_REACHED終端処理を既存`history_closed`変数駆動の規律と完全に同型化したことで、この契約との整合がより厳密に保証されるようになった（10.2.2章、MJ-3新の解消）。 |
| Retry RuntimeのCanonicalAdmissionFailure fail-fast（Codex Ruling A） | 変更なし。hook例外はAdmission例外とは別種の、Execution History整合後に再raiseするfail-fastとして位置づける（10.2.3章）。 |
| dry-run zero-write | 変更なし。 |

---

## 16. Reconciliation（**Round 4で改訂：`_reconcile_all_locked()`への統一**）

`RetryRuntimeOrchestrator.run_once()`の冒頭で`RetryLineageManager.reconcile_all(resolve_status_fn)`（公開API）を呼ぶ。**（Round 4で変更）**：`reconcile_all()`は内部で`RetryExecutionLock`を取得し（9.3.2章）、取得に成功した場合のみ`_reconcile_all_locked()`（実処理）へ委譲する。取得に失敗した場合（`retry()`が in-flight）、**一切のmutationを試みず**`ReconcileSummary(skipped=True, ...)`を返し、次回`run_once()`サイクルへ委ねる。

`_reconcile_all_locked()`は以下の3つの走査を行う（(a)(b)はRound 3から機能自体は変更なし、(c)はArchitecture Amendment（Draft、Code Review Blocking#1対応）で新設）：

### (a) `phase==EXECUTION_STARTED`の解決

`resolve_status_fn(record.latest_run_id)`の結果に応じて：`"success"`／`"failure"`いずれも、`classify_execution_history_step()`（11.7.2章）による全stepの分類結果から`decide_disposition()`相当の判定（`FAILED`/`NOT_ACTIONED`/`SUCCEEDED`）を導出し、`compute_newly_confirmed()`で`steps_confirmed_done`への追加分を算出した上で`mark_terminal(disposition, ...)`を呼ぶ。`"in_progress"`→何もしない、`None`→何もしない（残存ギャップ、25章）。

**（Round 5で更新）**：11.7.2章の`StepExecutionRecord.action_taken`追加により、この経路も同期パス（11.5章）と同一のロジックでSILENT_NO_ACTIONを検出できるようになった。旧record（`action_taken=None`）については`UNKNOWN`として扱われ、`disposition=FAILED`（fail-closed、no payback）となる（17章crash matrix#17参照、Round 4までの「SUCCESS扱いしてしまう」という危険側挙動から解消）。

### (b) `phase==TERMINAL and terminal_disposition in (FAILED, NOT_ACTIONED)`の開始

該当する全lineageに対し`open_next_attempt(root_run_id)`を呼ぶ。通常の同期完了パスとクラッシュ復旧パスが同一コードで処理される（Round 3から変更なし）。**（Round 7で追加）**`open_next_attempt()`が11.4.5.2章のinvariant violation（次scopeが空）によりack=Falseを返した場合、当該lineageは`phase==TERMINAL`のまま残り、`READY_ELIGIBLE`へは遷移しない。`reconcile_all()`はこれを異常終了として扱わず、次回`run_once()`サイクルで同一lineageに対し`open_next_attempt()`を再試行する（`steps_confirmed_done`の破損が解消されない限り、恒久的に同じ結果を繰り返す。18章の診断で検出する）。

### (c) `phase==CLAIMED`のorphan回収（**Architecture Amendment（Draft）、Code Review Blocking#1対応で新設**）

10.2.4章のとおり、hook未ack由来の`CLAIMED`orphanは`RetryExecutor.execute()`内の`release_claim()`により同一`retry()`呼び出し内（`RetryExecutionLock`保持中）で回収される。しかし、`claim()`成功後・hook呼び出しに到達する前にプロセスが終了した場合（`RetryExecutionLock`はOSレベルのファイルロックであり、プロセス終了時にOSが自動解放する、9.3・9.4章）、この同期的回収は発生せず、lineageは`phase==CLAIMED`のまま取り残される。

`RetryExecutionLock`が`retry()`・`reconcile_all()`双方にとって唯一のグローバル排他境界であること（9.3章）により、`_reconcile_all_locked()`実行中は他のいかなる`retry()`呼び出しも同時に進行し得ない。したがって、`_reconcile_all_locked()`が走査を開始した時点で発見される`phase==CLAIMED`のlineageは、**現在進行中の正当なclaimではあり得ず**、必ず上記のプロセスクラッシュ由来のorphanである（構造的な保証、9.3章と同じ排他性に基づく）。

**採用：`_reconcile_all_locked()`は、走査対象に`phase==CLAIMED`の全lineageを追加する。該当する全lineageに対し`release_claim(root_run_id)`を呼び、`phase`を`READY_ELIGIBLE`へ戻す。** `mark_execution_started()`が一度も成功していないため`attempt_count`は消費されておらず（9.8.1.3章、`attempt_count`は`mark_execution_started()`のdurable ack成功時点でのみ+1される）、`release_claim()`によるbudgetへの影響は一切ない。回収後のlineageは通常のcooldown/claim経路（`RetryEnqueueTrigger`・`claim()`）で次回自然に再claimされる。

`RETRY_LINEAGE_ENABLED=false`の間も、`reconcile_all()`（公開API）自体は呼ばれ続け、`RetryExecutionLock`取得・(a)(b)(c)走査も継続する（`claim()`のみがfail-closedスイッチの対象、Round 1〜3から変更なし）。

---

## 17. Crash Matrix（**Round 4で拡張**）

| # | crash timing | 直前のdurable state | 直後の状態 | 復旧契約 |
|---|---|---|---|---|
| 1〜13 | （Round 3から変更なし） | | | 旧版参照。`RetryExecutionLock`関連のケース2・3・10、post-admission hook関連のケース12・13は、9.3.2章の`_retry_locked()`統一・10.2.2章の`history_closed`規律化により、記述内容がより正確になった以外は本質的に変更なし。 |
| 14（**Round 4で更新**） | lineage store書き込み失敗 **かつ** Execution Historyのterminal終端処理も失敗（複合障害） | 両者とも不整合な中間状態で残りうる | 同左 | **（Round 4で更新）**10.2.2章の`history_closed`規律化により、少なくともExecution History側の内部矛盾（多重recovery試行等）は解消された。`correlation_metadata`は`start_run()`時点（複合障害の発生タイミングより前）に書き込み済みのため、この経路でも相関は残る。lineage側の最終状態（成功/失敗）が未確定のままになりうる点は残存し、25章Open Questionsに明記する。 |
| 15（**Round 4新設**） | `retry()`実行中に、別プロセスが`reconcile_all()`を試行 | `RetryExecutionLock`は`retry()`側が保持中 | `reconcile_all()`は`RetryExecutionLockBusyError`により即座にskip、mutation不実行 | **正常**。次回`run_once()`サイクルで再試行される（9.3.3章）。BL-1新・MJ-1新の直接的な解消確認。 |
| 16（**Round 4新設**） | `reconcile_all()`実行中に、別プロセスが`retry()`を試行 | `RetryExecutionLock`は`reconcile_all()`側が保持中 | `retry()`は即座にSKIPPEDを返す、state mutation不実行 | 正常。呼び出し元（Queue/Scheduler）は次サイクルで再試行する。 |
| 17（**Round 5で解消を確認**） | reconcile_all()経由でSUCCESS判定した対象に、実際にはcrash直前のsilent no-actionが隠れていた（11.7章） | Execution Historyは全step`SUCCESS`、`action_taken`は6.31導入後のrecordなら記録済み | `action_taken`が記録されていれば`SILENT_NO_ACTION`を正しく検出し`mark_terminal(SUCCEEDED)`を誤って呼ばない（11.7.2章）。**旧record（`action_taken=None`）に限り**`UNKNOWN`→`FAILED`（fail-closed、安全側）として扱われる | Round 4までのBlocking級ギャップを解消。旧record限定の残存差分（危険側ではなく安全側への挙動変化）のみ25章Risksに記載。 |
| 18（**Round 4新設**） | post-admission hook失敗時、`finish_step()`が一部成功し途中で失敗（`history_closed`が途中で立つ） | 既存規律どおり、失敗以降のstepはin-memoryのみ記録、History API呼び出しなし | `history_write_failed=True`、`finish_run()`は呼ばれない | 既存6.30規律（`workflow_engine_executor.py`既存コード）とhook失敗パスが完全に同型であることの直接確認（10.2.2章、MJ-3新の解消）。 |
| 19（**Round 5新設**） | `target_step_filter`適用attempt中にcrash | 一部stepが`NOT_TARGETED`でskip済み、残りは実行中 | `EXECUTION_STARTED`のまま | ケース3〜4と同一、reconcile_all()に委ねる。`skip_category=NOT_TARGETED`のstepはExecution History上も`SKIPPED`として記録されるため、reconcile経路でも整合する分類が可能。 |
| 20（**Round 6新設、Round 7で位置づけ改訂、Round 8で検出条件を一般化**） | `steps_confirmed_done`または`attempt_scopes`の破損等により、`claim()`時点の再計算値が保存済み`attempt_scopes[-1].steps_to_execute`と一致しない（空集合になるケースを含むが、それに限らない） | `phase==READY_ELIGIBLE`、再計算値と保存済みscopeが不一致 | `claim()`が恒久的にinvariant violationでack=False（11.4.5.2章(a)）、`.run()`は一切呼ばれない。自動修復は行わない | 正常運用ではRound 7の責務分離（12章）により行21（`open_next_attempt()`側）で先に検出されるはずだが、`claim()`もvalidation専用の独立した検証を行う（MN-new-1対応）。cooldownとは異なり時間経過で自然解消しない。18章の診断で検出し、運用者が`steps_confirmed_done`・`attempt_scopes`を手動検証・修復する。 |
| 21（**Round 7新設、B-1対応**） | `steps_confirmed_done`の破損等により、`open_next_attempt()`時点の再計算で次attempt用scopeが空集合になる | `phase==TERMINAL`、`terminal_disposition`がretryable（FAILED/NOT_ACTIONED）、`steps_confirmed_done`が全stepをカバー | `open_next_attempt()`が恒久的にinvariant violationでack=False（11.4.5.2章(b)）、`phase`は`TERMINAL`のまま、`READY_ELIGIBLE`へ遷移しない | 正常なSUCCEEDED終端（`terminal_disposition==SUCCEEDED`では`open_next_attempt()`自体が呼ばれない、12章）とは構造的に区別される。B-1が指摘した「正常終了とinvariant violationの混同」はこの責務分離により解消される。18章の診断で検出する。 |
| 22（**Architecture Amendment（Draft）新設、Code Review Blocking#1対応**） | `claim()`成功後・post-admission hook呼び出しに到達する前にプロセスが終了する | `phase==CLAIMED`、`mark_execution_started()`は一度も呼ばれていない（`attempt_count`未消費） | `RetryExecutionLock`はOSにより自動解放される（9.3・9.4章）が、lineageは`phase==CLAIMED`のまま残る | 次回`reconcile_all()`サイクルの16章(c)走査（新設）が、`RetryExecutionLock`保持中に発見した全`phase==CLAIMED`lineageを構造的にorphanと判定し`release_claim()`で`READY_ELIGIBLE`へ戻す。budgetへの影響なし（`attempt_count`未消費のため）。 |
| 23（**Architecture Amendment（Draft）新設、Code Review Blocking#1対応**） | post-admission hookが`acknowledged=False`を返す（`HOOK_NOT_ACKNOWLEDGED`/`HOOK_EXCEPTION`、10.2.2章）、プロセスはcrashしない | `phase==CLAIMED`のまま、全stepが`NOT_APPLICABLE`分類 | `RetryExecutor.execute()`（10.2.4章）が`decide_disposition()`/`mark_terminal()`を呼ばず、同一`retry()`呼び出し内で`release_claim()`により即座に`READY_ELIGIBLE`へ戻し`RetryOutcome.SKIPPED`を返す | クラッシュケース22とは異なり同期的に解消される。`RetryQueueUpdateDecider`は`outcome!=RETRIED`のためQueueを`COMPLETE`にしない（Blocking#1の直接解消）。 |
| 24（**Architecture Amendment（Draft）新設、Code Review Major#4対応**） | `next_attempt_ordinal`と`attempt_scopes[-1].attempt_no`が不一致になる状態破損（原因は`steps_confirmed_done`/`attempt_scopes`破損と同種、行20・21参照） | `phase`は`READY_ELIGIBLE`または`TERMINAL`（破損タイミングによる） | `claim()`／`open_next_attempt()`（いずれも12章）が恒久的にinvariant violationでack=False。自動修復は行わない | 行20・21と同じ性質の防御的検証。18章の診断で検出する。 |

---

## 18. Observability（**Round 6で拡張、Round 7で対象範囲を拡張、Round 8で検出条件を一般化**）

`RetryLineageManager.diagnose_stuck(min_age_seconds)`（読み取り専用）はRound 1〜5から変更なし。**（Round 6で追加、Round 7で対象を拡張、Round 8で検出条件を一般化、Architecture Amendment（Draft）で3.を追加）**：`diagnose_stuck()`（または新規の読み取り専用診断関数）は、以下**3つ**の独立したinvariant violation状態を検出対象に含める：

1. **（Round 6由来、Round 8で条件を一般化、Architecture Amendment（Draft）で`next_attempt_ordinal`不一致を追加）**`phase==READY_ELIGIBLE`かつ、`compute_steps_to_execute(steps_confirmed_done)`の再計算値が保存済み`attempt_scopes[-1].steps_to_execute`と一致しない、**または**`next_attempt_ordinal != attempt_scopes[-1].attempt_no`であるlineage（空集合になるケースを含むが、それに限らない、11.4.5.2章(a)・12章、`claim()`時点の防御に対応、17章crash matrix行20・24）。
2. **（Round 7で新設、Architecture Amendment（Draft）で`next_attempt_ordinal`不一致を追加）**`phase==TERMINAL`かつ`terminal_disposition in (FAILED, NOT_ACTIONED)`かつ、`compute_steps_to_execute(steps_confirmed_done)`が空集合、**または**`next_attempt_ordinal != attempt_scopes[-1].attempt_no`であるlineage（11.4.5.2章(b)・12章、`open_next_attempt()`時点の防御に対応、17章crash matrix行21・24）。
3. **（Architecture Amendment（Draft）新設、Code Review Blocking#1対応）**`phase==CLAIMED`のlineage全件（17章crash matrix行22）。上記1.・2.とは異なり、これ自体は「invariant violation」ではなく「16章(c)による次回`reconcile_all()`サイクルでの自動回収を待っている正常な過渡状態」である。運用者向けの可視化目的（同一lineageが複数サイクルにわたり`CLAIMED`のまま残っていないかの確認）として区別された理由文字列（例：`"pending_reconcile: claimed_orphan"`）を付与し、1.・2.の`"invariant_violation: ..."`とは異なる重大度で報告してよい。

いずれも`age`（経過時間）を問わない即時検出とし、通常のREADY_ELIGIBLE（cooldown待ち）・通常のTERMINAL（次回reconcileサイクルでの正常な`open_next_attempt()`待ち、または9.8.1章のbudget exhaustionによる正常終端）と区別できる専用の理由文字列（例：claim側は`"invariant_violation: scope_mismatch"`または`"invariant_violation: ordinal_mismatch"`、open_next_attempt側は`"invariant_violation: empty_execution_scope"`または`"invariant_violation: ordinal_mismatch"`）を付与する。**`terminal_disposition==SUCCEEDED`のlineage、および`attempt_count >= max_attempts`による正常なbudget exhaustion終端（12章、ack=False経路(b)）は、この診断の対象に一切含めない**（いずれも異常ではないため。B-1の教訓を踏まえ、診断ロジック自体もdisposition不問・budget不問の判定にしないことを設計上の不変条件とする）。`peek()`・`diagnose_stuck()`いずれも読み取り専用のまま変更しない。

---

## 19. Duplicate Enqueue / Duplicate Execution防止（**Round 4で更新**）

- **Duplicate enqueue**：`RetryEnqueueTrigger`は`lineage.phase`が`READY_ELIGIBLE`でない場合はenqueueをスキップする。**（Round 4で更新）**：`correlation_metadata["retry_lineage"]`namespaceの実在確認込みの相関判定（10.3.3章）が、hook失敗由来の孤立run_idが独立候補としてenqueueされることを、namespace衝突・偽の値のリスクを抑えた形で防ぐ。
- **Duplicate execution**：`claim()`のREADY_ELIGIBLE→CLAIMEDのatomic遷移が単一勝者を保証する。**（Round 4で強化）**：`RetryExecutionLock`が`retry()`・`reconcile_all()`双方にとって唯一のグローバル境界となったことで（9.3章）、BL-1（旧・新）双方の指摘した経路がいずれも構造的に閉じられた。

---

## 20. Hot Retry防止（Round 1〜3から変更なし）

---

## 21. 6.30 Runtime/Zero-Diffへの影響範囲（**Round 5で更新**）

Round 4の6点（`run_id`追加、`WorkflowEngineResult.run_id`、`WorkflowEngineExecutor`の1行追加、`post_admission_hook`追加、`correlation_metadata`追加×2箇所）に加え、**Round 5は以下2点を追加する**：

7. `StepExecutionRecord`への`action_taken: bool | None = None`追加、`ExecutionHistoryManager.finish_step()`への`action_taken`引数追加（11.7.2章）。
8. `WorkflowEngineManager.run()`／`WorkflowEngineExecutor`への`target_step_filter: list[WorkflowEngineStep] | None = None`追加、`WorkflowEngineStepResult`への`skip_category`追加（11.3.2・11.4.3章）。
9. **（Round 6で追加）**`StepExecutionRecord`への`skip_category: StepSkipCategory | None = None`追加、`ExecutionHistoryManager.finish_step()`への`skip_category`引数追加（11.7.2章、H-3対応）。

**いずれも省略時（`None`）は既存の全非retry呼び出し元に対して完全にZero-Diff**（`target_step_filter=None`は従来どおり全step対象、`action_taken`/`skip_category`未指定の`finish_step()`呼び出しは従来どおり`None`のまま記録される）。

hook失敗時の終端処理（10.2.2章）を既存`history_closed`規律と同型化したことは、既存の非retry呼び出し元の振る舞いには一切影響しない。

MN-1（旧）で訂正した「新規フィールドを除く既存フィールド値が不変」という主張（bit-for-bit一致ではない）は、Round 5でも変わらず正しい主張として維持する（新規フィールドが2つ増えた点を除く）。

`src/execution_history/`への変更は、Round 5で`action_taken`の追加により拡大した。26章Gate Checklistにて、この拡大自体をHuman Gateの明示承認事項とする。

---

## 22. Exact Implementation Scope（実装フェーズで変更するファイル一覧）（**Round 5で改訂**）

**新規（`src/retry_lineage/`、11ファイル、Round 3から変更なし）**：旧版参照。

**新規（`src/retry_engine/`、2ファイル、内容はRound 5で改訂、Round 11で追加）**：`retry_genuine_action.py`（`StepOutcomeCategory`・`StepSkipCategory`・分類関数群）, `retry_target_resolution.py`（`decide_disposition()`・`compute_newly_confirmed()`・`compute_steps_to_execute()`・`_canonicalize_step_order()`・`compute_initial_confirmed_steps()`）。

**新規（`src/workflow_engine/`、1ファイル）**：`workflow_engine_post_admission_hook.py`（Round 3から変更なし）。

**変更**：
- `src/retry_engine/retry_manager.py`（**Round 4**：`retry()`/`_retry_locked()`分離。**Round 9**：`_retry_locked()`から`should_retry()`直接呼び出しを除去。**Round 10**：`_retry_locked()`を`find_existing_lineage()`優先呼び出しへ改訂し、既存lineage再接続時のMonitor lookupを構造的に排除、MAJ-R9-1対応）
- `src/retry_engine/retry_executor.py`
- `src/retry_engine/retry_request.py`
- `src/retry_engine/retry_queue_update_decider.py`（**Round 4**：`decide_disposition()`由来の判定を利用するよう整合）
- `src/retry_engine/__init__.py`
- `src/retry_lineage/retry_lineage_manager.py`（**Round 4**：`reconcile_all()`/`_reconcile_all_locked()`分離。**Round 9**：`open_next_attempt()`は`record.max_attempts`を参照。`mark_terminal()`のpayback補正コードを撤回、MAJ-R8-1〜3対応。**Round 10**：`resolve_or_create()`を`find_existing_lineage()`（分岐(1)(2)、read-only）と`create_new_lineage()`（分岐(3)、`CreateNewLineageResult`戻り値型・`max_attempts`snapshot validation）へ分離。`create_new_lineage()`／`open_next_attempt()`の`attempt_scopes`書き込みへ`_canonicalize_step_order()`を追加、MAJ-R9-1・MAJ-R9-2・MIN-R9-1対応。**Round 11**：`create_new_lineage()`の第2引数を`monitor_record`（`WorkflowMonitorRecord`）へ変更し、`max_attempts` snapshot validationを`should_retry()`より前へ移動、`compute_initial_confirmed_steps()`によるattempt 1初期化を追加。`claim()`を`_canonicalize_step_order()`の実使用へ修正、MAJ-R10-1・MAJ-R10-2・MIN-R10-1対応）
- `src/retry_enqueue_trigger/retry_enqueue_trigger.py`（**Round 4**：namespace対応の相関判定）
- `src/workflow_engine/workflow_engine_manager.py`
- `src/workflow_engine/workflow_engine_result.py`
- `src/workflow_engine/workflow_engine_executor.py`（**Round 4**：`history_closed`規律に沿ったhook失敗処理）
- `src/workflow_engine/workflow_engine_context.py`
- `src/execution_history/execution_history_manager.py`（**Round 4**：`correlation_metadata`型変更。**Round 5**：`finish_step()`へ`action_taken`引数追加。**Round 6**：`finish_step()`へ`skip_category`引数追加）
- `src/execution_history/workflow_execution_record.py`（**Round 4**：`correlation_metadata`型変更、`from_dict()`後方互換明記）
- `src/execution_history/step_execution_record.py`（**Round 5で新規に変更対象化**：`action_taken`フィールド追加。**Round 6**：`skip_category`フィールド追加。いずれも`from_dict()`後方互換）
- `src/retry_composition/retry_composition_root.py`
- `src/retry_enqueue_trigger/retry_enqueue_guard.py`（変更なし、シグネチャ不変）
- `src/retry_engine/retry_policy.py`（変更なし、シグネチャ不変）

**新規テスト**：`tests/test_e2e_v6_31_0_retry_lineage_eligibility_durable_attempt_state.py`（24章）

**無改修（明示）**：`main.py`、`scripts/run_workflow_engine.py`、`src/ai/news_agent.py`・`src/ai/review_trigger_agent.py`・`src/ai/publish_trigger_agent.py`（**Round 4で明記**：11.2章の分類は既存Agentのロジックを一切変更しないread-only分類であることの再確認）、`src/retry_scheduler_source/`、`src/retry_scheduler_decision/`、`src/scheduler/`、`src/retry_queue/`、`src/retry_history/`、`src/workflow_monitor/`、`src/retry_runtime_lock/`、`src/execution_history/json_execution_history_store.py`。

---

## 23. Rejected Alternatives（まとめ、Round 1〜8）

Round 1〜3の却下代案（16件）は旧版参照。Round 4で追加した却下代案：

| # | 検討した代案 | 却下理由 |
|---|---|---|
| 17 | `correlation_metadata`を平坦なキーのまま値の実在確認のみ追加（namespace化しない） | 10.4章。将来の衝突リスクを構造的に排除できない。 |
| 18 | ~~Execution Historyへ`action_taken`相当の情報を追加する~~ | **（Round 5で撤回、11.7.2・11.8章参照）**当初はRetry/Agentドメイン概念の越境と判断したが、`action_taken`は`AgentResult`（retry導入以前から存在するAgent実行層の型）の既存フィールドであり、`error_message`/`skipped_reason`と同格の実行事実の記録として、6.31スコープ内で追加することを採用に転じた。 |
| 19 | `decide_disposition()`にtarget-scoped評価を主軸として残す | 11.8章。BL-1新の根本原因（target単独評価とpipeline全体評価の食い違い）を再導入するリスク。 |

Round 5で追加した却下代案（11.4.2・11.8章に既出、ここに集約）：

| # | 検討した代案 | 却下理由 |
|---|---|---|
| 20 | dependency closureモデル（targetに加えその依存先も再実行） | 11.4.1章の実コード確認により、step間の実データ依存が存在しないことを確認。無用な複雑さ。 |
| 21 | Round 4の単一target置き換えモデルを維持する | 11.4.4章。NOT_REACHED stepを誤って実行対象から除外するリスクを構造的に持つ。 |
| 22 | 全step再実行を維持し、livenessは運用パラメータ調整で緩和する | Round 4 review発見のliveness問題は運用調整では根本解決にならない。 |
| 23 | `intended_attempt_no`をrange一致（`1<=N<=next_attempt_ordinal`）で検証する | 10.3.3章。exact matchより弱く、stale値の誤った再接続を許容しうる。membership-first・correlation-fallbackの2段階構成の下では、fallback対象はorphanに限定されるため、exact matchで十分かつより安全。 |

Round 6で追加した却下代案（11.4.5・11.7.4章に既出、ここに集約）：

| # | 検討した代案 | 却下理由 |
|---|---|---|
| 24 | 空`steps_to_execute`を「防御的にSUCCEEDEDへ倒す」現状（Round 5）のまま維持する | 11.4.5章（H-1）。fail-closed方針全体と矛盾し、`steps_confirmed_done`破損を隠蔽する。 |
| 25 | legacy record再実行の安全性を検証せず「実害なし」という記述のまま維持する | 11.7.4章（H-2）。無検証の安全性主張はArchitecture文書として不適切。実コード確認（`filter_unpublished()`）により根拠を明示する方針へ転換。 |
| 26 | `StepExecutionRecord`へ`skip_category`を追加せず、`StepExecutionStatus.SKIPPED`のみで代替する | 11.7.2章（H-3）。disposition決定への機能的実害は小さいが、同期パスとの分類対称性・将来の未知skip理由へのfail-closed耐性を保つため、構造化フィールドを実際に追加する方を採用。 |

Round 7で追加した却下代案（11.4.5・11.7.2章に既出、ここに集約）：

| # | 検討した代案 | 却下理由 |
|---|---|---|
| 27 | `mark_terminal()`が引き続き無条件に次attempt用scopeを計算・記録する（Round 5〜6の設計を維持する） | 12章（B-1）。全stepがgenuineに完了した正常なSUCCEEDED終端で空scope防御が誤発火し、dispositionが誤って`FAILED`へ変換される。terminal化とscope生成の責務を分離することでのみ構造的に解消できる。 |
| 28 | `action_taken`／`skip_category`の型不正値・未知値をtruthy判定や緩い包含判定（`!= GATE_CLOSED`等）のまま扱い続ける | 11.7.2章（M-1・M-2）。将来のenum拡張や永続データの型破損に対してfail-openしうる。同期経路が既に採用している「既知値を列挙し、それ以外はUNKNOWN」という閉集合判定へ両経路を統一する。 |

Round 8で追加した却下代案（9.8.1・11.4.5.2(a)章に既出、ここに集約）：

| # | 検討した代案 | 却下理由 |
|---|---|---|
| 29 | `open_next_attempt()`の`should_retry(monitor_status, ...)`呼び出しをそのまま維持し、`monitor_status`の出所を実装フェーズで解決する | 9.8.1章（M-new-1）。Architecture Design段階で実装不能な契約を残すことは、Round 5〜6が禁じた「無検証の安全性主張」（H-2の教訓）と同種の問題を再導入する。durable stateのみで判定式を確定できる以上、実装フェーズへ先送りする理由がない。 |
| 30 | `claim()`の再計算値と保存済み`attempt_scopes[-1]`が不一致な場合、いずれか一方（例：再計算値）を正として自動的に採用し、処理を継続する | 11.4.5.2(a)章（MN-new-1）。自動修復は、`steps_confirmed_done`または`attempt_scopes`のどちらが実際に破損しているかを判別する根拠を持たないまま片方を正としてしまうため、破損の種類によっては誤ったstep集合でattemptを実行してしまうリスクを構造的に排除できない。fail-closed（手動修復必須）の方が安全側に倒れる。 |

Round 9で追加した却下代案（7.1・9.8.1章に既出、ここに集約）：

| # | 検討した代案 | 却下理由 |
|---|---|---|
| 31 | `open_next_attempt()`の`max_attempts`を`RetryPolicy.max_attempts`（現在の設定値）から都度読み取る（`RetryLineageRecord`へsnapshotしない） | 9.8.1章（MAJ-R8-1）。運用中の`RETRY_MAX_ATTEMPTS`変更が既存lineageへ遡及し、既にexhaustedのはずのlineageが復活する、または逆に途中でbudgetが縮小するという予測不能な挙動を招く。lineage作成時点のsnapshotのみが、そのlineageの生涯にわたる一貫した契約を保証する。 |
| 32 | `NOT_ACTIONED`のpaybackを維持し、liveness問題（MAJ-R8-2）は`diagnose_stuck()`側の追加診断や運用上のcooldown調整で緩和する | 9.8.1.3章。個々の状態（READY_ELIGIBLE・TERMINAL）がいずれも正常に見えるため、無制限成長そのものを検出する診断を追加で作り込む必要があり、根本解決にならない。budgetを一様に消費させることで、診断機構に頼らず構造的に有限停止を保証できる。 |
| 33 | `_retry_locked()`の`should_retry(monitor_status, ...)`をattempt 2以降にも残し、`open_next_attempt()`の判定と「両方通れば許可」という形で併用する | 9.8.1.2章（MAJ-R8-3）。2つの独立した判定基準（durable stateベース／monitor_statusベース）を併用すると、両者が異なる結論を出す状態（例：`open_next_attempt()`は許可したがmonitor_statusベースでは拒否）が原理的に排除できず、システムの挙動がどちらの判定に依存するか読み手に自明でなくなる。単一の判定契約に一本化する方が検証可能性が高い。 |

---

## 24. Test Strategy（**Round 6で更新、Round 8でattempt accounting・scope authorityテストを追加、Round 9で改訂、Round 10でinitial admission分離・max_attempts validation・stored scope canonical性のテストを追加、Round 11でvalidation順序・attempt 1 scope導出・分岐別reconnectテストを改訂**）

### 24.1 新規E2E（`test_e2e_v6_31_0_...py`）で検証する項目

**Step outcome classification（`skip_category`構造化、MN-新1系）**
1. **（Round 5改訂）**`skip_category`全分類テーブルテスト：`GATE_CLOSED`/`NOT_REACHED`/`HISTORY_WRITE_FAILED`/`HOOK_NOT_ACKNOWLEDGED`/`HOOK_EXCEPTION`/`NOT_TARGETED`それぞれが正しい`StepOutcomeCategory`（`INTENTIONAL_NO_ACTION`／`NOT_APPLICABLE`）へ分類されること。
2. **（Round 5新設）**unknown step outcomeはfail-closed：`skip_category=None`（`executed=False`にもかかわらず未設定）、および将来の未知enum値を注入した場合、`classify_step_outcome()`が`UNKNOWN`を返し`decide_disposition()`が`FAILED`（no payback）となることを確認する（MN-新1の直接解消、Round 4では実質到達不能だった経路）。
3. **（Round 9で訂正）**genuineなNOT_ACTIONED（interval guard等）は`decide_disposition()`が`NOT_ACTIONED`を正しく返す（Round 1〜4から維持）が、**paybackはされない**——`attempt_count`は他のretryable disposition（`FAILED`）と同様に消費されたままであることを確認する（9.8.1.3章、MAJ-R8-2対応、Round 8まで存在したpayback契約からの変更点）。

**Target / dependency execution（BL-新2系）**
4. **（Round 5新設）**target/dependency execution：`target_step_filter`が指定された場合、対象外stepが`skip_category=NOT_TARGETED`で実際にスキップされ、Agent（NewsAgent/ReviewTriggerAgent/PublishTriggerAgent）の`decide()`/`act()`が一切呼ばれないことをmock/spyで確認する。
5. **（Round 5新設）**NEWS→PUBLISH drift：11.6章のトレースをE2Eで再現。attempt 1でNEWS・REVIEWがGENUINE_SUCCESS・PUBLISHがSILENT_NO_ACTIONとなった後、`steps_confirmed_done`が`["news","review"]`へ更新され、attempt 2の`target_step_filter`が`["publish"]`のみとなること。
6. **（Round 5新設）**multi-interval-guard liveness：NEWS・REVIEW・PUBLISHそれぞれ異なる`min_interval_minutes`を設定した状態でattempt 1〜Nを進行させ、**NEWS・REVIEWの再発火するinterval guardによってSUCCEEDEDへの到達が妨げられないこと**（Round 4 review発見のliveness問題の解消確認）を、有限回のattempt内で`SUCCEEDED`へ到達することとして検証する。
7. **（Round 5新設）**NOT_REACHEDのstepがsteps_confirmed_doneに誤って含まれないこと：元のcanonical runでNEWSのみFAILEDだった場合（REVIEW/PUBLISHはNOT_REACHED）、lineage作成時の`steps_confirmed_done`が空であり、attempt 1でREVIEW/PUBLISHも実行対象に含まれること。
8. genuine failure優先・intentional no-opはretryしない（Round 4から維持）。

**Execution ownership / locking（MJ-1新系、Round 4から維持）**
9〜16. `retry()` vs `reconcile_all()`のmulti-process concurrency、reconcile busy skip、nested/reentrant呼び出しでのdeadlock防止、lock ordering検証、terminal ack=False処理、live CLAIMED横取り防止、direct retry()同時呼出し、multi-process Execution Lock競合、stale lock manual recovery（旧版参照、内容変更なし）。

**correlation_metadata（MJ-2新系、Round 5でexact-match対応拡張）**
17. correlation namespace valid/malformed/unknown（Round 4から維持）。
18. **（Round 5改訂）**forged/stale correlation metadata拒否：(a)存在しない`root_run_id`を騙る値、(b)実在する`root_run_id`だが`intended_attempt_no`が現在の`next_attempt_ordinal`と一致しない（過去の値・未来の値）、(c)`root_run_id`・`intended_attempt_no`は正しいが`correlation_id`が`transition_history`上の記録と一致しない、の3パターンいずれもauthoritativeな相関として扱われず、通常の独立候補として処理されることを確認する。
19. **（Round 5新設）**attempt_no exact-match境界：`intended_attempt_no == next_attempt_ordinal`の境界（一致／±1のずれ）をパラメタライズドテストで確認する。
20. old Execution History record metadataなしload（Round 4から維持）。
21. unrelated FAILED recordを誤除外しない（Round 3〜4から維持）。

**Hook failure / History規律（MJ-3新系、Round 4から維持）**
22〜24. hook failure中のfinish_step failure injection、history_closed後のHistory API zero-call、hook exception + terminal recovery（旧版参照）。

**Reconciliation / action_taken（Round 5新設、Blocking Finding対応）**
25. **（Round 5新設）**crash後reconcileでもsilent no-opをSUCCEEDEDにしない：`.run()`完了後・`mark_terminal()`前でプロセスクラッシュを模擬し、`action_taken`が正しく記録されたExecution Historyから`reconcile_all()`が再起動後に解決する際、PUBLISHがsilent no-opだった場合に`SUCCEEDED`ではなく`NOT_ACTIONED`（または`FAILED`）となることを確認する（17章crash matrix#17の直接解消確認）。
26. **（Round 5新設）**old record `action_taken=None`：`action_taken`フィールドを持たない旧JSON recordを`reconcile_all()`が処理する場合、`classify_execution_history_step()`が`UNKNOWN`を返し`disposition=FAILED`（fail-closed、危険側のSUCCEEDED誤判定への転落なし）となることを確認する。

**max_attempts / membership（Round 1〜4から維持）**
27. max_attempts境界値等価性・max_attempts=0/1/2/3の実効retry回数（9.8章）。**（Round 8で具体化）**`open_next_attempt()`側のdurable-state判定式に基づく詳細版は項目40へ統合する。
28. global membership uniqueness、A→B→C multi-hop再接続。

**6.30回帰**
29. 6.30 inherited contract regression：`CanonicalAdmissionFailure`fail-fast、`history_write_failed`ラッチ、terminal immutabilityが、hook失敗パス・`action_taken`/`skip_category`追加後も一切変化していないことの回帰（既存`test_e2e_v2_7_0_workflow_engine_foundation.py`等の再実行含む）。
30. 4-phase invariant、TERMINAL後/次READY前crash recovery、dry-run zero-write、`RETRY_LINEAGE_ENABLED=false`時の`claim()`/`reconcile_all()`挙動、hot retry防止、abandoned RUNNING→TIMEOUT一気通貫E2E、persistence failure fail-closed（いずれもRound 1〜4から維持、旧版参照）。

**Round 6で新設（H-1〜H-3・L-1対応）、Round 7で#31・#32を改訂**
31. **（Round 6新設、Round 7で範囲を拡張）空scope invariant violation（H-1・B-1対応）**：(a) `claim()`側：`steps_confirmed_done`が全stepをカバーする状態を`phase==READY_ELIGIBLE`に人為的に注入し、`claim()`が`.run()`を一切呼ばずに恒久的にack=False（`invariant_violation`理由）を返すことを確認する（11.4.5.2章(a)）。(b) `open_next_attempt()`側（**Round 7新設**）：`terminal_disposition`がretryable（FAILED/NOT_ACTIONED）かつ`steps_confirmed_done`が全stepをカバーする状態を`phase==TERMINAL`に人為的に注入し、`open_next_attempt()`が恒久的にack=Falseを返し`phase`が`TERMINAL`のまま変化しないことを確認する（11.4.5.2章(b)）。(c) **正常系の対照テスト（Round 7新設、B-1の直接的な再発防止）**：最後の1つの未確認stepが今回のattemptでgenuineに成功し、`steps_confirmed_done`が全stepをカバーするに至った場合、`mark_terminal()`が正しく`disposition=SUCCEEDED`のまま確定し、`open_next_attempt()`が一切呼ばれず、`FAILED`へ誤って変換されないことを確認する。`diagnose_stuck()`（18章）が(a)(b)いずれの状態も検出できることも確認する。
32. **（Round 5新設、Round 7で事実訂正）legacy recordのPUBLISH安全性・REVIEW残存リスク（H-2・M-3・M-4対応）**：`action_taken`を持たない旧`WorkflowExecutionRecord`（PUBLISH=SUCCESS）からlineageを作成し、attempt 1でPUBLISHが再実行された場合に、`AiPublishService`の`filter_unpublished()`により対象記事が0件となり**重複投稿が発生しないこと**を確認する。**（Round 7で訂正）**このとき`run()`の戻り値は`None`ではなく、空レポートの`Path`が返ることを実際にアサートする（Round 6版の`success=False`/`report_path=None`という誤った期待値を修正）。同様の旧recordでREVIEWが再実行された場合、`save_review()`が実際に呼ばれ、同日再実行では同一ファイルが上書きされること、日をまたいだ再実行では別ファイルとして重複生成されること、`load_reviews()`がdedupなしで両方を読み込み件数が二重計上されることを確認する（外部I/O重複ではないことの確認と、確認済みリスクの実証）。
33. **skip_category後方互換・UNKNOWN（H-3対応）**：`skip_category`フィールドを持たない旧`StepExecutionRecord`（`status=SKIPPED`）が`classify_execution_history_step()`により`UNKNOWN`へ分類されること、および`GATE_CLOSED`保持record が`INTENTIONAL_NO_ACTION`（同期パスと対称）へ分類されることを確認する。
34. **§4 Non-Goals整合（L-1対応）**：ドキュメントlintまたはレビューチェックリストとして、§4・§11.7・§14・§21・§22間で`action_taken`/`skip_category`スコープ記述の矛盾がないことを実装着手前に確認する（テストコードではなくレビュー手順として26章Gate Checklistに記載）。

**Round 7で新設（B-1・M-1〜M-4対応、上記#31・#32の改訂に加えて）**
35. **terminal/scope責務分離の直接確認（B-1対応）**：`mark_terminal()`呼び出し前後で`attempt_scopes`のリスト長が変化しないこと（`mark_terminal()`が`attempt_scopes`へ一切書き込まないこと）を直接アサートする。次attempt用scopeの追加は`open_next_attempt()`呼び出し後にのみ発生することを確認する。
36. **sync/reconcile closed-set対称性（M-1対応）**：`StepSkipCategory`に存在しない未知の文字列値（enumに定義されていない値）を`WorkflowEngineStepResult.skip_category`および`StepExecutionRecord.skip_category`双方へ人為的に注入し、`classify_step_outcome()`と`classify_execution_history_step()`が**いずれも**`UNKNOWN`を返すこと（一方だけが`NOT_APPLICABLE`へfail-openしないこと）をパラメタライズドテストで確認する。
37. **malformed `action_taken`のfail-closed（M-2対応）**：`action_taken`に`"false"`（文字列）・`0`・`[]`・`"true"`等の非bool値を持つ`StepExecutionRecord`のJSONを`from_dict()`で読み込み、いずれも`action_taken=None`へ正規化され、`classify_execution_history_step()`が`UNKNOWN`を返すことを確認する（truthy判定であれば誤って`GENUINE_SUCCESS`/`SILENT_NO_ACTION`になっていたはずの値を明示的に含める）。同期パス`classify_step_outcome()`側も、`AgentResult.action_taken`が仮に`True`/`False`以外の値を持つ場合に`UNKNOWN`を返すことをあわせて確認する。
38. **PUBLISH対象0件時の実際の戻り値（M-3対応）**：上記#32の一部として、`AiPublishService.run()`を`targets=[]`となる状況で直接呼び出し、戻り値が`None`ではなく実際に保存された空レポートの`Path`であることを確認する。
39. **（Round 8で根拠を具体化）REVIEW同日上書き・日跨ぎ重複・`load_reviews()`のdedupなし（M-4対応）**：`save_review()`を同一`article_id`・同一日で2回呼び出した場合に`review_dir`配下のファイル数が1のまま（上書き）であること、日付を変えて2回呼び出した場合にファイル数が2になる（重複）ことを確認する。`load_reviews()`がこの2ファイルを両方読み込むことに加え、**`PublishReviewStepExecutor.execute()`（`workflow_step_executor.py:295-321`）を実際に呼び出し、`WorkflowStepResult.processed_count`が2（本来1であるべき値の水増し）になることを直接アサートする**（M-new-2対応、11.7.4章）。

**Round 8で新設、Round 9で改訂（M-new-1・MN-new-1・MN-new-2・MAJ-R8-1〜3対応）**
40. **（Round 9で文言修正・payback関連分岐を除去、MIN-R8-3対応）`open_next_attempt()`のattempt accounting判定式**：`terminal_disposition`×`record.attempt_count`×`record.max_attempts`の組み合わせをパラメタライズドテストで網羅する：(a) `terminal_disposition=SUCCEEDED`なら、`record.attempt_count`・`record.max_attempts`の値によらず常にack=False・mutationなし（disposition単独で決まる、旧文言「disposition不問」の誤記を修正）。(b) `terminal_disposition=FAILED`かつ`attempt_count<max_attempts`ならack=True・`attempt_scopes`へ次scope追加・`phase→READY_ELIGIBLE`。(c) `terminal_disposition=FAILED`かつ`attempt_count>=max_attempts`ならack=False（`"max_attempts exhausted"`）・`phase`は`TERMINAL`のまま。(d) `terminal_disposition=NOT_ACTIONED`でも(b)(c)と**同一の**境界式・**同一の**`attempt_count`（payback補正なし、Round 9で撤回）で判定されることを確認する。(e) `max_attempts=0/1/2/3`それぞれについて9.8.1.4章の数値例表のとおりの実retry回数になることを、`FAILED`のみの構成・`NOT_ACTIONED`のみの構成・両者混在の構成すべてで同一の結果になることを含めてE2Eで確認する（旧項目27を本項目へ統合・具体化する）。
41. **（Round 9で全面改訂、MAJ-R8-2対応）persistent `NOT_ACTIONED`の有限停止**：あるstep（例：PUBLISH）が`min_interval_minutes`を満たさず常に`NOT_ACTIONED`を返す状況を人為的に構成し、`max_attempts`回のattemptを経た時点で`open_next_attempt()`がbudget exhaustionによりack=Falseを返し、lineageが`phase==TERMINAL`のまま恒久的に停止することを確認する。`attempt_no`／`next_attempt_ordinal`／`attempt_scopes`の要素数が、いずれも`max_attempts`に比例した有限値で頭打ちになり、無制限に増加しないことをアサートする（MAJ-R8-2の直接解消確認）。
42. **（Round 9で文言修正、MIN-R8-4対応）stored scope vs recomputed scopeの不一致**：`attempt_scopes[-1].steps_to_execute`を人為的に破損させた（`steps_confirmed_done`からの再計算値と食い違う、かつ非空である）状態で`claim()`を呼び、空集合ケースと同様にack=False（`invariant_violation`理由）となり、自動修復（どちらか一方の値を正として採用する等）が行われないことを確認する。`attempt_scopes`が空（一度も書き込まれていない）状態でも同様にack=Falseとなることを確認する。**Workflow canonical orderのみが異なる**（要素集合は同一だが順序が異なる）ケースでは、11.4.5.2(a)章の正規化比較により**誤ってfail-closedしない**ことも確認する（意味的に同一なscopeを破損として誤検出しないことの確認）。
43. **reconcile full-successでの`open_next_attempt()`非呼出し（MN-new-2対応）**：`phase==EXECUTION_STARTED`のlineageを、`resolve_status_fn`が全stepの`classify_execution_history_step()`結果を`GENUINE_SUCCESS`と判定する状態で`reconcile_all()`（16章(a)）に処理させ、(i) `mark_terminal(SUCCEEDED, ...)`のみが呼ばれること、(ii) 同一`reconcile_all()`呼び出し内の16章(b)走査がこのlineageを対象に含めないこと（`terminal_disposition==SUCCEEDED`のため）、(iii) `open_next_attempt()`が一切呼ばれないことをspyで直接証明する。
44. **`open_next_attempt(SUCCEEDED)`の直接呼出し（MN-new-2対応）**：`terminal_disposition==SUCCEEDED`のlineageに対し`open_next_attempt()`を（テストコードから）直接呼び出し、ack=False（`"terminal_disposition is not retryable"`）を返し、`attempt_scopes`・`phase`・`steps_confirmed_done`のいずれにも変更（mutation）が生じないことを確認する。

**Round 9で新設（MAJ-R8-1〜3・MIN-R8-1・MIN-R8-2対応）**
45. **`max_attempts` snapshotの不変性（MAJ-R8-1対応）**：lineage作成時の`RETRY_MAX_ATTEMPTS`環境変数（またはそれに基づく`RetryPolicy.max_attempts`）が例えば`3`だった場合、`record.max_attempts=3`としてsnapshotされることを確認する。その後、環境変数を`1`または`10`へ変更した状態で同一lineageに対し`open_next_attempt()`／`claim()`を実行しても、判定は依然`record.max_attempts=3`（snapshot時点の値）に基づくことを確認する。新規に作成される別のlineageは、変更後の新しい値をsnapshotすることも確認する。
46. **initial admission gateはlineage作成時のみ（MAJ-R8-3対応、Round 10で`create_new_lineage()`へ用語更新）**：(a) 新規lineage作成時（`create_new_lineage()`、分岐(3)）に`monitor_status`が対象statusでない、または`RetryPolicy.max_attempts=0`の場合、lineageが一切作成されず（`admission_rejected=True`）、`claim()`が一度も呼ばれないことを確認する。(b) `open_next_attempt()`によりREADY_ELIGIBLEへ再オープンされた既存lineage（attempt 2以降）に対し`_retry_locked()`が呼ばれた際、`RetryPolicy.should_retry()`や`monitor_status`の取得・参照が一切発生しない（mockのcall countが0）ことを確認する（二重ゲートが残っていないことの直接証明。**Round 10で項目49がMonitor lookupの副作用自体の呼び出し回数0まで検証を拡張する**）。(c) attempt 2以降で`monitor_status`が仮に対象statusでなくなっていても（例：元のcanonical runの状態が変化したように見えても）、`open_next_attempt()`のdurable state判定のみでattempt可否が決まり、`_retry_locked()`側の判定に一切影響されないことを確認する。
47. **`mark_terminal()`のatomic save failure injection（MIN-R8-1対応）**：`self._store.save(record)`が例外を送出する状況を注入し、`phase=TERMINAL`・`terminal_disposition`・`steps_confirmed_done`の更新（Round 9では`attempt_count`の書き換えは存在しない）のいずれもディスクへ反映されず、記録が更新前の状態（`phase==EXECUTION_STARTED`）のまま残ることを確認する（部分書き込みが発生しないことの直接証明）。次回`reconcile_all()`サイクルで`phase==EXECUTION_STARTED`のまま正しく検出・復旧されることも確認する。
48. **（Round 9で不要化、MIN-R8-2対応）`attempt_count`アンダーフロー**：Round 9でpaybackが撤回されたため、`mark_terminal()`は`attempt_count`を一切減算しない。したがってアンダーフローという事象自体が構造的に発生し得ないことを、`mark_terminal()`のいかなる呼び出しパターンでも`attempt_count`が減少しないことを確認する回帰テストとして位置づける（Round 8時点のMIN-R8-2はこれにより不要化）。

**Round 10で新設（MAJ-R9-1・MAJ-R9-2・MIN-R9-1対応）、Round 11で改訂（MAJ-R10-1・MAJ-R10-2・MIN-R10-1・MIN-R10-2対応）**
49. **既存lineage再接続でMonitor/Policy call count=0（MAJ-R9-1対応、Round 11で分岐別に拡張、MIN-R10-2対応）**：`WorkflowMonitor.get_status()`・`RetryPolicy.should_retry()`双方をmock/spyし、既存lineageが存在するrun_idに対して`_retry_locked()`を呼んだ際、**両方の呼び出し回数が0であること**を直接アサートする。**（Round 11で拡張）**単一の「attempt 2以降」ケースにまとめず、(a) 分岐(1)（`run_id`自体が既存`root_run_id`と一致、`find_existing_lineage()`が`self._store.get(run_id)`で直接ヒットする経路）、(b) 分岐(2)-単一hop（`find_by_member_run_id()`が1段のmembership一致で解決する経路）、(c) 分岐(2)-multi-hop（A→B→Cのように複数段のmembership解決を要する経路）の3つを独立したパラメタライズドケースとして検証し、mockのcall countだけでなく、各ケースで`_retry_locked()`のelseブロック（Monitor取得コード自体）へ到達していないことをカバレッジ計測または実装内部のフラグ注入で確認する（Round 10版はcall count確認のみで、分岐を区別していなかった）。
50. **分岐(1)(2)再接続後の完全なstate不変性（MAJ-R9-2対応、Round 11でfull state比較へ拡張、Suggestion対応）**：lineageを作成し（`max_attempts=3`・`steps_confirmed_done`・`attempt_scopes`・`membership`・`transition_history`等、全フィールドに非自明な値を持たせる）、そのシリアライズ済みdict（`to_dict()`相当）をスナップショットとして保存した上で、`find_existing_lineage()`を(a) 分岐(1)、(b) 分岐(2)単一hop、(c) 分岐(2)multi-hopの3経路で呼び出す。**（Round 11で拡張）**戻り値および`self._store.get()`で再取得した永続化済みレコードのシリアライズ済みdictが、`max_attempts`単体ではなく**全フィールド**でスナップショットとbit-for-bit一致すること、かつ呼び出し前後で`self._store.save()`が一度も呼ばれないことをspyで確認する。
51. **config変更非遡及（Round 9から維持、45章参照。Round 11でfull state確認を追加）**：既存lineageの`max_attempts`snapshotが`RETRY_MAX_ATTEMPTS`環境変数の事後変更に追従しないことを確認する（項目45と同一）。**（Round 11で追加）**`find_existing_lineage()`経由の再接続についても、項目50と同様に`max_attempts`以外の全フィールドを含めたfull state不変性を、環境変数変更の前後で確認する。
52. **新規lineageのみMonitor/Policy使用（Round 9から維持、46章参照）**：`create_new_lineage()`が呼ばれる経路（`find_existing_lineage()`がNoneを返す場合）に限り`WorkflowMonitor.get_status()`・`RetryPolicy.should_retry()`が呼ばれることを、項目46(a)の一部として`_retry_locked()`のif/elseブロック単位のカバレッジで確認する。**（Round 11で明確化）**`create_new_lineage()`の第2引数が`monitor_record`（`WorkflowMonitorRecord`）へ変更されたことに伴い、テストのmock/stubも`WorkflowMonitorRecord`（`monitor_status`・`steps`両フィールドを持つ）を返すよう更新する。
53. **`max_attempts`負値・不正型のfail-closed、validation-rejectionとpolicy-rejectionの区別（MAJ-R9-2対応、Round 11で全面改訂、MAJ-R10-1対応・Suggestion対応。Round 11 Cleanupでcontrol caseの曖昧さを解消）**：`RetryPolicy.max_attempts`が`-1`（負値）・`"3"`（文字列）・`True`（bool）・`None`のそれぞれについて、`create_new_lineage()`が例外を送出せず`admission_rejected=True`を返し、`RetryLineageRecord`が一切保存されないこと（`self._store.save()`の呼び出し回数0）を確認する。**（Round 11で追加、MAJ-R10-1対応）**これら4パターンいずれについても、`RetryPolicy.should_retry()`をmockし、**呼び出し回数が0であること**（validationがこれより前で完結し、`should_retry()`へ一切到達しないこと）を直接アサートする。これにより、Round 10レビューで指摘された「負値がvalidatorではなく`should_retry()`側のpolicy判定で先に弾かれてしまい、validatorが実際に実行されたことを証明できない」というギャップを解消する。**（Round 11 Cleanupで修正、SUG-R11-2対応）**対照のpolicy-rejection控制ケースは、`max_attempts=1`（validationを通過する妥当な値）かつ`monitor_status`が非対象status（例：`SUCCESS`）という組み合わせに固定する——`max_attempts`が`should_retry()`の`attempt < max_attempts`側の条件では絶対にFalseにならない値（`attempt=0 < 1`は常にTrue）であるため、rejectionの原因が`monitor_status`の不一致であることが一意に定まる（旧`max_attempts=0`＋非対象statusの組み合わせは、`0 < 0`がFalseになる経路と`monitor_status`不一致の経路のどちらが実際にFalseの原因になったのか区別できない、という曖昧さがあった）。このケースでは`should_retry()`の呼び出し回数が**1**であり、`reason`文字列がvalidation-rejection（`"invalid max_attempts snapshot value..."`）とは異なるpolicy-rejection文言（`_skip_reason()`由来、"monitor_status=... is not a retry target"）であることを確認し、両rejection経路を明確に区別する。`_retry_locked()`側は両ケースいずれも`RetryOutcome.SKIPPED`を返すことも確認する。
54. **stored scope保存値のcanonical性（MIN-R9-1対応、Round 11で全面改訂：実際にout-of-order値を注入する形へ、MAJ-R10-2に伴う入力経路変更を反映。Round 11 Cleanupでhistorical justificationを訂正、MIN-R11-2対応）**：`compute_steps_to_execute()`をstubし、`ALL_WORKFLOW_ENGINE_STEPS`の列挙順とは異なる順序のリスト（例：`["publish", "news", "review"]`）を返すよう差し替える。**（Round 11 Cleanupで訂正）**Round 10版の`create_new_lineage()`も`compute_steps_to_execute(steps_confirmed_done=[])`を明示的に呼んでいたため（§7.2.0参照）、このstub自体はRound 10のコードパス上でも到達可能であり、「stubを注入してもRound 10のcreate_new_lineage()を実際には通らない」という記述は事実誤りだった。Round 10とRound 11の本質的な違いは、stubの到達可能性ではなく**`compute_steps_to_execute()`へ渡される入力の出所**にある：Round 10は常にハードコードされた`[]`を渡していたため、canonicalize契約の検証はできても「元recordのGENUINE_SUCCESS stepから導出された、現実的なconfirmed setを経由した上でのcanonicalize」という、Round 11が新設した`compute_initial_confirmed_steps(monitor_record.steps)`の実際のデータフローは検証できなかった。Round 11では`create_new_lineage()`が`compute_initial_confirmed_steps(monitor_record.steps)`の結果を経て`compute_steps_to_execute()`を呼ぶため、`monitor_record.steps`に適当なGENUINE_SUCCESS混じりのstepを持たせた上で本stubを有効にすれば、`create_new_lineage()`・`open_next_attempt()`の両write pathで確実にout-of-order値がstubから注入される。両者それぞれについて、保存直後に`RetryLineageStore`から直接読み出した`attempt_scopes[-1].steps_to_execute`が、`_canonicalize_step_order()`を通した後のcanonical order（`ALL_WORKFLOW_ENGINE_STEPS`の列挙順）になっていることを、`claim()`を一切経由せず直接アサートする（`_canonicalize_step_order()`を書き込み経路から取り除いた場合にこのテストが確実にfailすることを、実装レビュー時に反転確認する）。
55. **`create_new_lineage()`・`open_next_attempt()`のatomic save failure injectionと前後状態（Round 8項目47の対象拡大）**：(a) `create_new_lineage()`内の`self._store.save(record)`が例外を送出する状況を注入し、`admission_rejected`判定・`max_attempts` snapshot計算・`compute_initial_confirmed_steps()`によるattempt 1初期化計算がいずれもメモリ上でのみ行われ、ディスクには一切反映されず、後続の`find_existing_lineage(run_id)`が引き続き`None`を返すこと（＝lineageが実質的に「作成されなかった」ことと区別できないこと）を確認する。(b) `open_next_attempt()`内の`self._store.save(record)`が例外を送出する状況を注入し、`phase`・`terminal_disposition`・`attempt_scopes`のいずれも更新前の状態（`phase==TERMINAL`、旧`attempt_scopes`のまま）で残ることを確認する。いずれも部分書き込みが発生しないことの直接証明であり、既存項目47（`mark_terminal()`）と合わせて、7.2・12章で新設・改訂した2つの書き込み経路すべてをカバーする。

**Round 11で新設（MAJ-R10-2対応、7.2.2章の`compute_initial_confirmed_steps()`）**
56. **attempt 1のsteps_confirmed_doneが元recordのGENUINE_SUCCESS stepから導出される**：元のFAILED/TIMEOUT`WorkflowExecutionRecord`について、NEWS=SUCCESS（`action_taken=True`）・REVIEW=SUCCESS（`action_taken=True`）・PUBLISH=FAILEDという構成の`monitor_record.steps`を用意し、`create_new_lineage()`を呼ぶ。保存された`record.steps_confirmed_done`が`["news","review"]`（PUBLISHを含まない）であり、`attempt_scopes[0].steps_to_execute`が`["publish"]`のみであることを確認する（11.4.3章のNEWS→PUBLISH driftトレース、11.6章と整合することの、lineage作成時点での直接確認）。
57. **NOT_REACHED・RETRYABLE_FAILURE・SILENT_NO_ACTION・INTENTIONAL_NO_ACTIONはattempt 1のconfirmed setに含まれない（Round 11 Cleanupでdurable scope全体の検証へ拡張、SUG-R11-1対応）**：元recordがNEWS=FAILED（REVIEW/PUBLISHはstatus=NOT_REACHED）の構成、および NEWS=SUCCESS(`action_taken=True`)・REVIEW=SUCCESS(`action_taken=False`、silent no-op)・PUBLISH=SKIPPED(`skip_category=GATE_CLOSED`)の構成のそれぞれについて、`create_new_lineage()`後の`record.steps_confirmed_done`にNOT_REACHED／SILENT_NO_ACTION／INTENTIONAL_NO_ACTIONと分類されるstepが一切含まれないこと（GENUINE_SUCCESSのstepのみが含まれること）を確認する。**（Round 11 Cleanupで追加）**項目56と同一のパターンで、`attempt_scopes[0].steps_to_execute`についても、confirmed setから除外された各step（NOT_REACHED・SILENT_NO_ACTION・INTENTIONAL_NO_ACTIONのいずれの構成でも）が正しく含まれている（＝attempt 1で再実行対象として残っている）ことを、`steps_confirmed_done`の否定確認だけでなく直接アサートする。
58. **legacy record（`action_taken=None`）はattempt 1のconfirmed setから除外される（既存UNKNOWN/fail-closed契約の維持確認。Round 11 Cleanupでdurable scope全体の検証へ拡張、MIN-R11-1・SUG-R11-1対応）**：`action_taken`フィールドを持たない（`None`のままの）旧`StepExecutionRecord`をSUCCESS statusで含む`monitor_record.steps`から`create_new_lineage()`を呼び、`classify_execution_history_step()`が当該stepを`UNKNOWN`と分類する結果、`compute_initial_confirmed_steps()`がこのstepをconfirmed setに含めないこと（＝attempt 1で当該stepが不要に「confirmed済み」として再実行スキップされることはなく、safe側＝再実行される側へfail-closedすること）を確認する。11.7.2章のlegacy record fail-closed契約（`action_taken=None`→`UNKNOWN`）が、reconcile経路だけでなくattempt 1初期化経路でも一貫して適用されることの確認。**（Round 11 Cleanupで追加、MIN-R11-1対応）**この安全性の実質的な帰結——legacy stepが不要にスキップされず実際に再実行対象へ残ること——を、`record.steps_confirmed_done`に当該stepが含まれないことの確認だけに留めず、保存された`attempt_scopes[0].steps_to_execute`に当該stepが**実際に含まれている**ことを直接アサートすることまで含めて検証する（§26 Human Gateが承認を求める「legacy record（`action_taken`未設定）はfail-closedで再実行対象に残る」という主張の、durable state上での直接的な裏付け）。

**Architecture Amendment（Draft）で新設（Code Review Findings対応、実装フェーズで追加すること）**
59. **（Blocking#1対応）hook未ack時、SUCCEEDED/COMPLETEに到達しない**：post-admission hookが`acknowledged=False`を返す状況（`HOOK_NOT_ACKNOWLEDGED`）を注入し、`RetryExecutor.execute()`が`mark_terminal()`を一切呼ばない（spyで呼び出し回数0を確認）こと、`release_claim()`が呼ばれ`lineage.phase`が`READY_ELIGIBLE`へ戻ること、戻り値が`RetryOutcome.SKIPPED`（`RETRIED`ではない）であることを確認する。さらに`RetryQueueUpdateDecider.decide()`にこの`RetryResult`を渡し、`RetryQueueUpdateOutcome.NOOP`（`COMPLETE`ではない）になることを直接確認する（Blocking#1の外部可視の実害そのものの解消確認）。hook例外（`HOOK_EXCEPTION`）についても同一の結果になることを確認する。
60. **（Blocking#2対応）`mark_terminal()`のack=Falseが`RetryOutcome.SKIPPED`へ正しく伝播する**：`mark_terminal()`をstubし`MarkTerminalResult(acknowledged=False)`を返すよう差し替えた状態で`RetryExecutor.execute()`を呼び、戻り値が`RetryOutcome.SKIPPED`であること（`RETRIED`のまま返らないこと）を確認する。
61. **（Blocking#1対応、17章crash matrix行22・16章(c)対応）`phase==CLAIMED`のorphan回収**：`claim()`を呼んだ後、hookを一切呼ばずに（＝クラッシュを模擬して）`reconcile_all()`を呼び、当該lineageが`release_claim()`により`READY_ELIGIBLE`へ戻ること、`attempt_count`が変化しないこと（budget未消費）を確認する。同一store内に他phaseのlineageも混在させ、(a)(b)(c)の3走査が互いに干渉しないことを確認する。
62. **（Major#3対応）グローバルmembership一意性チェック**：既存lineageのmembershipに含まれるrun_idを引数に`create_new_lineage()`を直接呼び出し（`find_existing_lineage()`を経由しない、7.1章のmembership index破損フォールバック相当の状況を模擬）、`admission_rejected=True`が返り、新しい`RetryLineageRecord`が保存されない（`self._store.save()`の呼び出し回数が0のまま）ことを確認する。root_run_id自体が既存lineageと衝突するケースも同様に確認する。
63. **（Major#4対応）`next_attempt_ordinal`不変条件のfail-closed検証**：`record.next_attempt_ordinal`のみを直接改変（`attempt_scopes[-1].attempt_no`とは不一致にする）した状態で`claim()`・`open_next_attempt()`をそれぞれ呼び、いずれも`acknowledged=False`（`reason`に`"invariant_violation"`を含む）を返し、`self._store.save()`が呼ばれない（読み取り専用の検証で終わる）ことを確認する。

### 24.2〜24.4（Round 1〜4から変更なし）

限定回帰（Zero-Diff Guard影響ファイル）・Formal Regression（33ファイル、5512テスト、baseline `1a9c5e15...`）・Runtime Verification（旧版参照。multi-interval-guard livenessテスト（項目6）はRuntime Verification環境でも実データ（複数`min_interval_minutes`設定）で再現する）。

---

## 25. Risks / Open Questions（**Round 6で更新、Round 7で確定・追加、Round 8で根拠を具体化、Round 9でretry gate関連を確定、Round 10でRisk#15を解消、Round 11でRound 10 review指摘を解消**）

1〜4.（Round 1〜4から維持：`find_by_member_run_id()`スケーラビリティ、真のGovernance Exceptionによる`EXECUTION_STARTED`無期限残存、cooldown/lock timeout既定値の妥当性、`RetryExecutionLock`によるthroughput全直列化。）

5.（Round 5から維持）17章crash matrix#14（lineage store書き込み失敗とExecution History terminal処理失敗の複合障害）は、`history_closed`規律化（10.2.2章）によりExecution History側の内部矛盾は解消されたが、lineage側の最終状態未確定という残存ギャップ自体は変わらず残る。

6.（Round 1〜4から維持：hook例外のtraceback実装詳細）

7.（Round 5から維持）**11.7.3章の`resolve_next_target_from_execution_history()`と同期パスの関数統合**は、実装フェーズで`WorkflowEngineStepResult`/`StepExecutionRecord`間のアダプタとして具体化する必要がある。

8.（Round 5から維持）**9.3.5章のnested/reentrant呼び出し禁止**は設計上の不変条件として明記したが、実装フェーズでのコードレビュー・静的解析による継続的な監査が必要（26章Gate Checklist）。

9.（**Round 6で更新、Round 7で確定、Round 8で具体的根拠を追加**）**旧record（`action_taken=None`）への挙動変化**：11.7.4章の事実確認により、PUBLISHについては再実行の安全性を確認済み（ただし戻り値の記述はRound 7で訂正、M-3）。REVIEWについては、**日またぎ重複ファイル生成＋`load_reviews()`側のdedupなし二重計上という実害**を、`workflow_step_executor.py:310-317`（`PublishReviewStepExecutor.execute()`の`processed_count=len(reviews)`）という具体的な生産コードconsumerとともに確認済みの事実として26章Human Gateへ明記する（M-new-2対応）。この重複が過去の人間のレビュー判断を実際に上書き・無効化するかどうかは、本reviewのコード確認範囲を超えて**断定しない**（未確認のまま、実装フェーズでdownstreamの判断消費ロジックを追加確認する）。NEWSの重複収集リスクは既存スコープ内（4章）。

10.（**Round 6で解消したため削除**）：`steps_to_execute`が空集合になる縮退ケースは、11.4.5章のinvariant violation fail-closedにより構造的に対処した（H-1解消）。同ケースを許容する記述だったRound 5の本項目は撤回する。

11.（**Round 6で新設、Round 7で確定、Round 8で根拠を具体化**）**`save_review()`の冪等性**：`save_review()`は「日付＋article_id」キーの疑似冪等であり、article_id単独の真のupsertではないことを実コード確認（`ai_publish_review_repository.py:83-106`）により確定した（11.7.4章）。同日再実行は上書き、日をまたいだ再実行は重複ファイルを生成し、`load_reviews()`はdedupなしで両方を読み込む。**（Round 8で確定）**この重複が実際に`WorkflowStepResult.processed_count`（`workflow_step_executor.py:310-317`）を水増しすることを確認した（M-new-2対応）。残る未確認事項は、この水増しが人間オペレーターの判断へどう影響するかというdownstream側の挙動のみであり、これは実装フェーズでの追加確認事項として残す。

12.（**Round 7で新設、Round 8で判定条件を修正、Round 9で`record.max_attempts`参照へ更新**）**`open_next_attempt()`側invariant violationの運用手順**：12章の責務分離により、`open_next_attempt()`もretryable terminalで次scopeが空の場合に恒久的にack=Falseを返しうる（17章crash matrix行21）。これは`claim()`側の既存invariant violation（行20）と同種の、時間経過で自然解消しない停止状態であり、9.4章のtrust boundaryと同じ運用上の手動修復手順に依存する。新規のリスク種別というより、既存の適用範囲がscope生成箇所の分離に伴い2箇所へ拡大したものである。この停止状態は、9.8.1章のbudget exhaustion（`record.attempt_count >= record.max_attempts`）による**正常**な終端とは明確に区別される別種の状態であり、両者を混同しないことを18章Observabilityの設計上の不変条件とする。

13.（**Round 8で「解消」と誤って記載、Round 9で訂正・最終解消**）Round 8は`monitor_status`の出所未定義（M-new-1）を解消したと述べていたが、Codex Round 8 reviewにより、代わりに`max_attempts`という同種の未定義変数を持ち込んでいたこと（MAJ-R8-1）、および「`_retry_locked()`はattempt 1のみ」という記述が実コードと矛盾し二重ゲートが残っていたこと（MAJ-R8-3）が判明し、Partial評価だった。Round 9で、(a)`max_attempts`をlineage作成時に`RetryLineageRecord.max_attempts`へsnapshotするdurable値とし（7.1・9.8.1章）、(b)`monitor_status`/`RetryPolicy`による判定をinitial admission（lineage作成時、1回限り）に一本化し、`open_next_attempt()`はdurable stateのみで判定する（9.8.1.2章）ことで、二重ゲート・未定義変数のいずれも構造的に解消した。

14.（**Round 9で新設**）**`NOT_ACTIONED`のbudget消費というトレードオフ**：9.8.1.3章のとおり、`NOT_ACTIONED`のpaybackを廃止したことで、interval guard周期がretry cadenceより長いstepを持つlineageは、genuineに成功する機会を得ないまま`max_attempts`を使い切りうる。これはMAJ-R8-2（無制限retryのliveness問題）を解消するために意図的に受け入れたトレードオフであり、運用者はinterval guard周期とretry cadence・`max_attempts`の整合を取る責任を負う（26章Human Gate承認事項）。

15.（**Round 9で新設、Round 10で解消**）~~`max_attempts` snapshotのライフサイクルに関する未確認事項~~：Round 9時点では、分岐(1)(2)自体の詳細疑似コードが「旧版参照」のまま明示されておらず、既存lineage再接続が`max_attempts`を誤って上書きしないことの実装レベルの保証ができないとしていた。**Round 10で`find_existing_lineage()`（7.1章）として全文を明示し、このメソッドが`self._store.save()`を一度も呼ばない（read-onlyである）という構造そのものによって、`max_attempts`を含む`RetryLineageRecord`の全フィールドが分岐(1)(2)経路を通過するだけでは一切変更され得ないことを、Architecture Design段階で構造的に保証した（MAJ-R9-2対応、24章項目50でテストによる裏付けも追加）。** 本項目は解消済みとして扱う。

16.（**Round 10で新設、Architecture Amendment（Code Review Major#3対応）で7.2章へ具体化**）**`find_existing_lineage()`のmembership index破損時のフォールバック挙動**：7.1章`find_existing_lineage()`は、membership index（`find_by_member_run_id()`相当）がrootを指しているにもかかわらず対応する`RetryLineageRecord`が実在しない場合、fail-closedで`None`を返し呼び出し元を新規lineage作成経路へフォールバックさせる設計とした。この場合、7.2章（Architecture Amendment）のグローバルmembership一意性チェックが後続の`create_new_lineage()`内でこの不整合を検出する。`create_new_lineage()`が一意性チェックで拒否した場合の`_retry_locked()`側の最終的なユーザー可視結果は`CreateNewLineageResult(admission_rejected=True)`経由の`RetryOutcome.SKIPPED`（既存の`admission_rejected`分岐、9.3.2章）であり、新規の分岐は不要と確定した。

17.（**Round 11で新設、解消済みとして記録**）Round 10のCodex独立reviewが指摘したMAJ-R10-1（`max_attempts` validationが`should_retry()`より後に行われ、実コードの`should_retry()`が不正値に対し`TypeError`を送出しうる）・MAJ-R10-2（attempt 1の`steps_confirmed_done`が`[]`固定で、11.4.3章の「元recordのGENUINE_SUCCESS stepを初期値に含める」契約を実装できていない）は、Round 11で(a) validationの呼び出し順序を`should_retry()`より前へ移動（7.2.1章）、(b) `create_new_lineage()`の引数を`monitor_record`（`WorkflowMonitorRecord`）へ変更し`compute_initial_confirmed_steps()`（7.2.2章）でattempt 1の初期confirmed setを導出、の2点により解消した。MIN-R10-1（`claim()`が共通canonicalizeヘルパーを使っていなかった）・MIN-R10-3（§9.3.4のメソッド数記述の矛盾）も同様にRound 11で解消した。MIN-R10-2（test #49の分岐別カバレッジ不足）・Suggestion 2件（test #53・#50・#51の検証粒度）はいずれも24章のテスト項目改訂で対応した。

---

## 26. Architecture Gate Checklist（**Round 11で更新、7章の要求どおりHuman Gate項目を維持。2026-08-31にHuman Gate必須15項目すべて承認済み**）

- [x] 本書（Round 11 + Cleanup版）のCodex独立review（reasoning effort High）を実施し、Blocking/Major指摘を収束させた（Round 10 review→Round 11で全解消、Round 11 review→Blocking/Major 0件「Pass with minor corrections」、指摘されたMinor/SuggestionはCleanupで解消済み）。
- [x] **（Human Gate必須・Round 9で全面改訂、Round 10でvalidation追加、Round 11で呼び出し順序を確定、7.2・9.8・9.8.1章。2026-08-31承認済み）**`max_attempts` snapshot semantics：`max_attempts`はlineage作成時に`RetryPolicy.max_attempts`から`RetryLineageRecord.max_attempts`へsnapshotされ、以後そのlineageの生涯にわたり不変であること、および`RETRY_MAX_ATTEMPTS`環境変数の運用中変更が既存lineageへ一切遡及せず新規lineageにのみ適用されることを、既存運用への影響として明示的に承認する（MAJ-R8-1対応）。**（Round 10で追加）**snapshot値が整数かつ`>=0`でない場合、lineage作成自体をfail-closedで拒否する挙動（`create_new_lineage()`、MAJ-R9-2対応）を承認する。**（Round 11で追加）**このvalidationは`RetryPolicy.should_retry()`を呼び出す**前**に行われ、不正な`max_attempts`が例外送出（`TypeError`）に頼らず必ず構造化された`admission_rejected=True`として検出されることを承認する（MAJ-R10-1対応）。
- [x] **（Human Gate必須・Round 11で新規、7.2.1・7.2.2・11.4.3章。2026-08-31承認済み）**attempt 1初期scopeのauthoritative data flow：lineage作成時（`create_new_lineage()`）のattempt 1の`steps_confirmed_done`初期値は、`[]`固定ではなく、`_retry_locked()`が`self._monitor.get_status(run_id)`で取得した`monitor_record.steps`（元のFAILED/TIMEOUT`WorkflowExecutionRecord`のstep実行結果のコピー）から`compute_initial_confirmed_steps()`（`classify_execution_history_step()`によりGENUINE_SUCCESSと分類できたstepのみを抽出）で導出されることを明示的に承認する（MAJ-R10-2対応）。これにより、元のcanonical run時点で既にgenuineに成功していたstepはattempt 1から`target_step_filter`によって除外され再実行されない。legacy record（`action_taken`未設定）はUNKNOWN判定によりfail-closedで再実行対象に残る（除外されない）ことも合わせて承認する。
- [x] **（Human Gate必須・Round 9で新規、9.8.1.3章。2026-08-31承認済み）**`NOT_ACTIONED`のbudget消費：`NOT_ACTIONED`（interval guard等によるgenuineなno-op）が、Round 5〜8の「payback（budgetを消費しない）」から「`FAILED`と同様にbudgetを消費する」へ変更されたことを明示的に承認する。この結果、interval guard周期がretry cadenceより長いstepを持つlineageは、genuineに成功する機会を得ないまま`max_attempts`を使い切りうるというトレードオフ（MAJ-R8-2解消のために意図的に受容）を承認する（25章Risk#14）。
- [x] **（Human Gate必須・Round 9で新規、Round 10で副作用レベルまで強化、7.1・7.2・9.3.2・9.8.1.2章。2026-08-31承認済み）**initial-only monitor-policy gate：`monitor_status`／`RetryPolicy.should_retry()`による判定が、新規lineage作成時（`create_new_lineage()`、分岐(3)）の1回限りに縮小され、attempt 2以降（`open_next_attempt()`経由の再オープン）では二度と評価されなくなったことを明示的に承認する。**（Round 10で追加）**この分離は判定ロジックだけでなく、`WorkflowMonitor.get_status()`というMonitor lookup自体の呼び出し有無にも及ぶ——既存lineage再接続（`find_existing_lineage()`）経路ではMonitorへのアクセス自体が構造的に発生しないことを承認する（MAJ-R9-1対応）。既存lineageのattempt 2以降は、元のcanonical runの`monitor_status`が事後的にどう変化して見えても、durable state（`terminal_disposition`・`attempt_count`・`max_attempts`）のみで許可判定される（MAJ-R8-3対応）。
- [x] **（Human Gate必須、9.1章。2026-08-31承認済み）**single-host限定を明示的に承認する。
- [x] **（Human Gate必須、9.3.3章。2026-08-31承認済み）**`RetryExecutionLock`による`retry()`/`reconcile_all()`双方の完全直列化とthroughput低下を明示的に承認する。
- [x] **（Human Gate必須、9.4章。2026-08-31承認済み）**手動stale-lock recoveryの運用上のtrust boundary（構造的に安全ではなく、正しい手順の実施に依存すること、PID再利用・破損metadata等の残存リスク）を明示的に承認する。
- [x] **（Human Gate必須、16章。2026-08-31承認済み）**`RETRY_LINEAGE_ENABLED=false`時も`reconcile_all()`が動作継続する仕様を明示的に承認する。
- [x] **（Human Gate必須、10.3章。2026-08-31承認済み）**Execution Historyへの`correlation_metadata`スキーマ追加（namespace化された最終形）を明示的に承認する。
- [x] **（Human Gate必須、11.7.2章。2026-08-31承認済み）**Execution Historyへの`StepExecutionRecord.action_taken`・`skip_category`追加（第2・第3のスキーマ拡張）を明示的に承認する。
- [x] **（Human Gate必須、11.4章。2026-08-31承認済み）**`target_step_filter`によるWorkflow Engine実行制御の追加（6.30 Executorの中核ロジックへの踏み込んだ変更）を明示的に承認する。
- [x] **（Human Gate必須・Round 6新規、Round 7で記述訂正、Round 8で根拠を具体化、11.7.4章。2026-08-31承認済み）**legacy record（`action_taken=None`）再実行によるREVIEWリスクを明示的に承認する：PUBLISHは`filter_unpublished()`により重複投稿なしと確認済み（ただし対象0件でも空report保存・Path返却があり得る、M-3訂正）。REVIEWは`save_review()`の日またぎ重複生成＋`load_reviews()`のdedupなしによる二重計上を、**`workflow_step_executor.py:310-317`の`processed_count`水増しという確認済みの具体的事実**として承認を求める（M-new-2対応、人間のレビュー判断への影響そのものは未断定）。
- [x] **（Human Gate必須・Round 6新規、Round 7で範囲拡張、Round 8でscope authority契約を追加、11.4.5・12・13章。2026-08-31承認済み）**terminal/scope責務分離の契約を明示的に承認する：`mark_terminal()`は次attempt用scopeを一切生成せず、`open_next_attempt()`（attempt 2以降）のみが生成する。**（Round 8で追加）**保存済み`attempt_scopes[-1]`をauthoritativeとし、`claim()`時点の再計算はvalidation専用（不一致は空集合に限らずfail-closedし、自動修復しない）。空scope・scope不一致のinvariant violation fail-closedは`claim()`・`open_next_attempt()`の2箇所で独立に行われ、いずれも恒久的にack=Falseを返し手動修復を要する（B-1・MN-new-1対応）。
- [x] **（Human Gate必須・Round 7新規、11.7.2章。2026-08-31承認済み）**`action_taken`の型不正値・`skip_category`の未知enum値をいずれもUNKNOWNへfail-closedする閉集合判定（sync/reconcile対称）への変更を明示的に承認する（M-1・M-2対応、Round 5〜6は一部fail-openだった）。
- [x] **（Human Gate必須、17章crash matrix#14。2026-08-31承認済み）**lineage store書き込み失敗とExecution History terminal処理失敗の複合障害という残存operational gapを明示的に承認する。

**以下はArchitecture Amendment（Code Review Findings対応）が追加した新規Human Gate項目である。§0参照。2026-08-31にユーザーが明示的に承認した：**

- [x] **（Human Gate必須・Architecture Amendment新規、10.2.4・16章(c)。2026-08-31承認済み）**hook未ack時のattempt outcome契約を明示的に承認する：hook未ack（`HOOK_NOT_ACKNOWLEDGED`/`HOOK_EXCEPTION`）およびプロセスクラッシュ由来の`phase==CLAIMED`orphanは、いずれも`SUCCEEDED`/`COMPLETE`に到達せず、`RetryOutcome.SKIPPED`（同期経路）または`reconcile_all()`の16章(c)走査による`release_claim()`（クラッシュ経路）で`READY_ELIGIBLE`へ回収されること。回収時、消費されていない`attempt_count`は変化しないこと。EXECUTION_STARTED未到達のhook失敗/orphanはretry budgetを消費しないというトレードオフを含めて承認する。
- [x] **（Human Gate必須・Architecture Amendment新規、10.2.4章。2026-08-31承認済み）**`mark_terminal()`のdurable ack確認義務：`mark_terminal()`を呼ぶ全ての呼び出し元（`RetryExecutor.execute()`）は`MarkTerminalResult.acknowledged`を必ず確認し、False時は`RetryOutcome.RETRIED`ではなく`RetryOutcome.SKIPPED`を返すこと。
- [x] **（Human Gate必須・Architecture Amendment新規、7.2章。2026-08-31承認済み）**グローバルmembership一意性チェックの追加：`create_new_lineage()`は同一store_lock内で既存の全root_run_id・membershipを走査し、作成しようとしているrun_idが既に他のlineageに属している場合はfail-closedで新規lineage作成を拒否すること（自動マージ・自動修復は行わない）。
- [x] **（Human Gate必須・Architecture Amendment新規、12章。2026-08-31承認済み）**`next_attempt_ordinal`不変条件のfail-closed検証追加：`claim()`・`open_next_attempt()`はいずれも、値を使用する前に`next_attempt_ordinal == attempt_scopes[-1].attempt_no`を検証し、不一致の場合はfail-closedでack=Falseを返すこと（自動修復しない）。

**以下4項目は「Human Gate必須」（設計判断の承認）ではなく、実装フェーズで実施すべき検証タスクである。§26の対象外ではないが、2026-08-31時点で未実施のまま残る（実装着手時・着手前に必ず実施すること）：**

- [ ] `WorkflowEngineResult`・`WorkflowExecutionRecord`・`StepExecutionRecord`・`start_run()`/`finish_step()`シグネチャ変更による既存テストへの影響を実装前に個別ファイルで確認する。
- [ ] 9.3.5章の「`_retry_locked()`/`_reconcile_all_locked()`は公開API（`retry()`/`reconcile_all()`）を再帰的に呼び出さない」という不変条件を、実装フェーズでコードレビュー観点のcode-path監査により確認する。
- [ ] **（Round 6追加、Round 7で対象拡大、Round 8でattempt accounting整合を追加、Round 9でretry gate契約を追加、Round 10でinitial admission分離を追加、Round 11でattempt 1 scope導出・validation順序を追加）**§4・§7・§7.1・§7.2・§7.2.1・§7.2.2・§7.3・§9.3.2・§9.8・§9.8.1・§11.4.3・§11.4.5・§11.7・§12・§13・§14・§21・§22間の記述（`action_taken`/`skip_category`スコープ、terminal/scope責務分離、attempt accounting判定式、retry gate統一契約）に矛盾がないことを実装着手前にレビューで確認する（L-1の再発防止、Round 7でB-1由来の§11.4.5/§12/§13間矛盾も対象に追加、Round 9で§7.1・§9.3.2・§9.8.1間のretry gate契約——`max_attempts`のsnapshot・initial admission・durable state判定——が完全に整合することの確認を追加、Round 10で§7.1・§7.2間の`find_existing_lineage()`/`create_new_lineage()`分離と§7.3の`_canonicalize_step_order()`共通化が全書き込み・比較箇所で一貫していることの確認を追加、Round 11で§7.2の`max_attempts`validation順序と§7.2.2/§11.4.3のattempt 1 scope導出契約が矛盾なく整合することの確認を追加）。
- [ ] Formal Regression baseline（33ファイル、5512テスト、commit `1a9c5e15...`）を実装着手前に再確認する。

## 27. Architecture Releaseとして開始可能かの判定（**Round 11で更新、Round 11 Cleanupで最終判定を追加、2026-08-31にArchitecture Gate承認を反映**）

**判定：本書（Round 11）はCodex Round 10指摘（MAJ-R10-1：`create_new_lineage()`が`RetryPolicy.should_retry()`を`max_attempts` snapshotのvalidationより前に呼んでおり、実コードの`should_retry()`が不正な`max_attempts`に対し`TypeError`を送出しうるため、「structured `admission_rejected=True`でfail-closedする」契約を例外送出に委ねる形でしか満たせていなかった／MAJ-R10-2：attempt 1の`steps_confirmed_done`が`[]`固定でハードコードされており、11.4.3章が要求する「元recordのGENUINE_SUCCESS stepを初期値に含める」契約と矛盾し、かつそれを満たすための入力経路自体が存在しなかった／MIN-R10-1：`claim()`が§7.3の共通canonicalizeヘルパーを実際には使わずインライン実装していた／MIN-R10-2：test #49が分岐を区別せずcall countのみで検証していた／MIN-R10-3：§9.3.4のメソッド数記述が§9.2と矛盾していた）への対応を反映した改訂版である。(1) `max_attempts` snapshotのvalidationを`should_retry()`より前へ移動し例外送出への依存を排除、(2) `create_new_lineage()`の引数を`monitor_record`（`WorkflowMonitorRecord`）へ変更し`compute_initial_confirmed_steps()`でattempt 1のsteps_confirmed_doneを元recordのGENUINE_SUCCESS stepから導出、(3) `claim()`を含む3箇所すべてで`_canonicalize_step_order()`を実際に共有、という3本柱で再設計した。Round 10で残っていた指摘はすべて解消した（25章項目17）。**

**Round 11 Cleanup追記：** 本書（Round 11）はCodex独立reviewを受け、**Blocking/Major指摘0件**（「Pass with minor corrections」判定）を確認した。Round 10のMAJ-R10-1・MAJ-R10-2・MIN-R10-1・MIN-R10-2・MIN-R10-3・Suggestion 2件は全てResolvedと再確認された。指摘されたMinor 2件（MIN-R11-1：test #58のdurable scope検証不足／MIN-R11-2：test #54のhistorical justification誤記）とSuggestion 3件（SUG-R11-1〜3：test #57/#58のdurable scope拡張・test #53のcontrol case曖昧さ・§14の記述整理）は、本Cleanupですべて反映した（24章項目53・54・57・58、14章）。**いずれもdocument/test-spec上の修正であり、normative architecture・スコープ・runtime semanticsは一切変更していない。**

**Architecture Gate承認（2026-08-31）追記：** 本書（Round 11 + Cleanup版）について、§26 Architecture Gate Checklistの**Human Gate必須15項目すべてをユーザーが明示的に承認した**（承認記録は§0・§26の各項目に記載）。**Architecture Design Statusを`Draft`から`Approved`へ更新する。** `src/`配下の実装着手はこのユーザー承認をもって解禁されるが、**本会話ではまだ実装に着手しない**（ユーザー明示指示による）。実装フェーズ開始前には、§26に残る非Human-Gate項目4件（既存テストへのシグネチャ変更影響確認・9.3.5章不変条件のcode-path監査・章間整合性の最終レビュー・Formal Regression baseline再確認）を実施すること。

**Architecture Amendment（Human Gate承認済み、2026-08-31）追記：** 実装完了・Formal Regression Inventory全件PASS確認後にCodexへ依頼した独立Code Review（実コードレビュー）で、Blocking 2件（post-admission hook未ack時のdisposition誤判定によるQueue誤完了／`mark_terminal()`のack=False無視）・Major 2件（グローバルmembership一意性チェックの欠落／`next_attempt_ordinal`不変条件のfail-closed検証欠落）の指摘を受け、ユーザー独立照合によりいずれも実コードで確認された。本書は上記の指摘に対する**限定的な設計整合修正**（10.2.4章新設、7.2・12・16章(c)・17章crash matrix行22〜24・18章・14章の該当箇所改訂、24章test項目59〜63追加、26章に新規Human Gate 4件追加）を反映した。**Architecture Design全体のStatusは引き続き`Approved`のままであり、次段落変更しない**——本Amendmentが対象とするのは実装済みコードの4箇所の欠陥修正のみであり、4-phase state machine・locking契約・attempt accounting・admission gate分離・6.31 scope境界・既承認15件のHuman Gate事項はいずれも無変更である。26章に追加した新規Human Gate 4件は2026-08-31にユーザーが明示的に承認し、実装フェーズが解禁された。

---

## 28. Roadmap/architecture 更新提案（未反映・提案のみ）

（旧版参照。Change Record訂正提案、6.31 Architecture Design Status追記提案（**Round 6で更新**：Round 1〜6の作成日・Codex Round 1〜5 review受領・反映済み・Round 6 review未実施である旨）、`docs/architecture.md`への6.31セクション新設提案、`docs/ROADMAP.md`への実装完了後のv6.31.0エントリ追記提案。いずれも本会話では適用せず提案として提示するのみとする。）