# MVP End-to-End Hardening & Validation — Architecture Design（Release 6.35）

## 0. Status

- **Status: Architecture Gate PASS（Round 10 editorial cleanup版）**。Codex `codex-readonly-review`（Codex High、fresh-thread独立レビュー）による独立レビューの経緯：Round 1 `NOT APPROVED`（Blocking 5／Major 7／Minor 2）→Round 1改訂→Round 2 `NOT APPROVED`（Blocking 3／Major 6／Minor 1）→Round 2改訂（Round 3版）→Round 3 `NOT APPROVED`（Blocking 2／Major 6／Minor 0）→Round 3改訂（Round 4版）→Round 4 `NOT APPROVED`（Blocking 2／Major 2／Minor 3）→Round 4改訂（Round 5版）→Round 5 `NOT APPROVED`（Blocking 2／Major 4／Minor 1）→Round 5改訂（Round 6版）→Round 6 `NOT APPROVED`（Blocking 1／Major 2／Minor 3）→Round 6改訂（Round 7版）→Round 7 `NOT APPROVED`（Blocking 0／Major 4／Minor 1）→Round 7改訂（Round 8版）→Round 8 `NOT APPROVED`（Blocking 0／Major 2／Minor 1）→Round 8改訂（Round 9版）→**Round 9 `APPROVED`（Blocking 0／Major 0／Minor 3）**。
- Round 9 Minor 3件（いずれも編集上の事実誤認で設計・scope・contractの変更を要しない）：(1) canonical execution（空RSS）が実行ログを書き込みinterval gateを起動しうるという10.2節・10.5節の記述が不正確（main.pyは実行ログ書き込み前に`return 1`する）。(2) exit code 1の名称誤り（`NEWS_OUTCOME_ABNORMAL_EXIT`ではなく`NEWS_OUTCOME_GENERIC_FAILURE_EXIT_1`が正しい）。(3) 23.1節P1テーブルの「既定動作への影響：ゼロ」が、同節「表現の訂正」段落（外部入力への影響はゼロではない）と矛盾していた。
- **Round 10改訂は、この3件のみをArchitecture semantics・scope・仕様を一切変更せずにeditorial correctionとして反映した**（10.2節・10.5節・23.1節）。Production/Testコード変更・Codex実行・commit/pushはいずれも行っていない。
- Baseline: branch `main`, HEAD=origin/main=`15c45b9eef23a52313c12ce04663fb8652e4621d`（Release 6.34.0、Working Tree clean、変更なし）。
- **現在の状態（Round 10時点、歴史的記録として維持。実装完了後の現在の状態は本節末尾の「Current Status」箇条書きを参照——0章が本書のCurrent Statusの正本である）**：Architecture Gate Checklist（26章）9条件・Acceptance Criteria（27章）はいずれもPASS（read-only最終確認済み）。Blocking／Major／Open Issueは残存しない（25.2節）。本書はArchitecture Releaseとして開始可能な状態にあり、次段階はP1（23.1節・7.5.1a節）実装着手前の独立Human Gate承認、およびScenario A〜Fのtest実装フェーズ（別フェーズ・別Human Gate）である。
- **Post-Round 10 Implementation Reconciliation Amendment（Human-directed、着手当初はCodex未実施だった）**：P1実装、およびScenario A〜Fのtest実装フェーズが完了し、その実装結果とArchitecture本文とのread-only照合（Human-directed reconciliation）を経て、8章・9章・7.5.4節・10.5節(a)・13.1節を本Amendmentで更新した。変更点の要旨と根拠は30章「Release 6.35 Implementation Reconciliation Amendment」に記録する。**本Amendment着手時点（30章起筆時）では、これまでの10 Roundとは異なりCodex `codex-readonly-review`による独立レビューをまだ経ていなかった**——実装が先行して明らかにした事実（8章・9章の契約本文欠落、Windows env実測差異、F1のPID実測差異）をArchitecture本文へ反映しただけの、read-only investigationに基づく編集だった。Architecture semantics・scope（2章の境界）はいずれも変更していない：Production Implementation候補は引き続きP1のみ、新規Foundation・P2実装・scope拡張のいずれも行っていない。
- **Current Status（本節が本書のCurrent Statusの正本である。30章はRelease 6.35着手からの時系列履歴であり、特定のsectionを「現在の状態」の参照先とすることはしない——current statusは常に本節を直接更新する）**：P1実装、およびScenario A〜Fのtest実装フェーズは完了している。targeted E2E（P1＋Scenario A〜F＋T6の9ファイル）は**163/163 PASS**。Formal Regression（Inventory 37ファイル）は**37/37 PASS**（FAIL 0／SKIP 0／全ファイルexit code 0）。Release 6.35全体を対象としたInitial Final Independent Codex Reviewは`NOT APPROVED`（Blocking 0／Major 2／Minor 1、いずれも本設計書の記述整合性に関する指摘であり実装内容への疑義ではない）であり、その文書整合修正を反映したFinal Re-Review #1も`NOT APPROVED`（Blocking 0／Major 1）だった——Major 1件は、修正後もなお本節（当時の記述）が特定sectionへの可変pointer（「現在（30.12節時点）」等）を含んでいたことによる、current-state記述自体の文書整合性の問題であり、実装・test・rosterへの疑義ではない。本節は、その指摘を受けて可変pointerを完全に削除し、現在の事実を直接記載する形へ更新した。この更新を反映したFinal Independent Codex Re-Review #2は`APPROVED`（Blocking 0／Major 0／Minor 0／Suggestions 0）であり、Release 6.35のFinal technical gateを通過した。**commit／pushは、本節執筆時点ではいずれも未実施（pending）である。**

---

## 1. Background / Motivation

`docs/MVP_COMPLETION_ROADMAP.md`（v1.3）は、Release 6.30〜6.34で個別の安全契約を確立済みである。Release 6.35は、新機能を追加せず、これらの契約を実Runtime経路で結合し、MVP Definition of Doneの達成をシナリオA〜Fで証明する。

Round 1レビューは初版設計の外部境界・プロセスモデル・crash injection手法の不備を指摘した。Round 1改訂はこれらに対応したが、Round 2レビューは改訂の一部が「解決したと主張しているが実際には別の弱い経路を証明しているに過ぎない」（Scenario C）、「レースが残っている」（Scenario D）、「候補止まりで仕様が確定していない」（RSS境界）、「既存実装が存在しない前提に依拠している」（Disposable Copy）、といった、改訂そのものの具体化不足を指摘した。Round 3改訂はこれらについて実際のコードを再調査したが、Scenario Cの2層（Tier 1／Tier 2）構成そのものが「別々の弱い経路の証拠を足しても1つの強い合成claimの証拠にはならない」とRound 3 Blocking 1で指摘された。Round 4改訂は、Scenario Cを2層構成から単一の統合設計（test-owned`sitecustomize.py`によるproduction seamレスのcrash injection）へ全面的に置き換えたが、Round 4レビューは、そのcrash発火をassertする経路（`PipelineResult.returncode`）が既存production契約上どこにも公開されていないこと（B1）、およびRetryExecutorとmain.pyが同一のDisposable Project Copy state領域を参照する結び付けが未規定であること（B2）を指摘した。Round 5改訂は、Scenario Cの根幹設計（sitecustomize方式・production seamレス）を維持したまま、crash発火の証拠をtest-owned durable marker fileへ置き換え、`RetryCompositionRoot.from_env(base_dir=...)`によるstate結合を明示的に規定したが、その統合実行アーキテクチャとして「テストハーネスが2つの独立したtest-only worker subprocessを順に起動する」という2-worker/Phase handoff構成を採用した。Round 5レビューは、このhandoffが前提とする`RetryQueueManager`/`RetryHistoryManager`が実際にはプロセスローカルのin-memory実装であり別プロセス間で共有され得ないこと（B1）、および`RetryCompositionRoot.from_env(base_dir=...)`が内部で読む2つの環境変数がhostから絶対パスとして継承された場合にDisposable Copy外のstateを参照しうること（B2）を指摘した。Round 6改訂は、2-worker/Phase handoff構成そのものを撤回し、単一の専用test worker process内でcanonical execution→enqueue→actual retry（RetryExecutor経由）を連続実行し、in-memory `RetryQueue`/`RetryHistory`をプロセス境界を越えずにそのまま保持する統合設計へ置き換えた（10章）。Round 6レビューは、この単一worker化自体は否定しなかったが、worker起動時のenv allowlistが必須Feature Gate・stub認証情報を欠いておりend-to-end chainが実行不能であること（B1）、6.24節・10.5節間のenv付与タイミング記述の矛盾（M1）、「attempt 2」という物理実行回数の呼称とlineageのauthoritative attempt_ordinal（実際は`1`）の食い違い（M2）、およびP1のhostname/port検証・RSS参照経路citation・`reconcile_all()`の`reason`期待値に関するMinor 3件を指摘した。Round 7改訂は、`src/`の該当Config/gateロジックを再読し、single-worker E2Eに必要な環境変数を漏れなく列挙してworker起動時env allowlistへ組み込み（10.5節、B1解決）、6.24節の記述を10.5節の設計と統一し（M1解決）、「canonical execution」と「retry execution（authoritative attempt_ordinal=1）」という2つの語を明確に区別して全文の呼称を統一した（10.2節、M2解決）。Round 7レビューは、Blockingこそ0件になったものの、worker自身がDisposable Project Copy外に存在するにもかかわらずその`src/`配下のproduction moduleをどう`import`するかが未規定であること（Major 1）、Local Stub契約が要求する`NO_PROXY`がworker起動時env allowlistから漏れておりWindows system proxy経由での迂回を排除できていないこと（Major 2）、P1のhostname/port grammarが自身のProhibited Outcome（`999.999.999.999`・明示的空port）を実際には拒否できていない内部矛盾（Major 3）、および26章Architecture Gate Checklist・29章の記述が本書自身のAcceptance Criteria（レビュー主体へ向けたmeta-text禁止）と矛盾していたこと（Major 4）を指摘した。Round 8改訂は、workerが`<Disposable Copy>/src`を最優先でimport解決しoriginal tree／installed packageへの誤解決をfail-closedに検出するbootstrap契約を新設し（10.5a節、Major 1解決）、worker起動時env allowlistへ`NO_PROXY=127.0.0.1,localhost`を追加し実クライアント挙動（`urllib.request.getproxies()`の短絡評価）に基づきloopback通信の隔離を確定し（10.5節、Major 2解決）、P1のhostname grammarをIPv4形状の先行判定へ改め明示的な空portを拒否する条件を追加し（7.5.1a節、Major 3解決）、26章・29章のreviewer向け設問・process指示を客観的なacceptance conditions／状態記述へ書き換え（Major 4解決）、Windows worker envの基盤変数を`SystemRoot`・`PATH`の2つに確定した（Minor解決）。Round 8レビューは、Blockingこそ0件のままだったが、P1のhostname grammarが`127.1`・`2130706433`・`0x7f.0.0.1`のような代替IPv4表記を依然として通してしまうこと（Major 1）、Scenario Cのcanonical NEWS失敗fixtureが自己完結的に規定されておらず未記載の「シナリオB（9章）の手順」に委ねていた上、`NewsAgent`の既定180分interval gateによりretry execution側のNEWS step実行が「成功扱いのno-op」としてスキップされうる構造的リスク（Major 2）、および`NO_PROXY`の効き方に関する`requests`固有の説明の不正確さ（Minor）を指摘した。本改訂（Round 9）は、P1のhostname grammarへ「数字のみラベル」「`0x`prefixラベル」の拒否を追加しstrict decimal dotted-quad以外のIPv4代替表記を閉じ（7.5.1a節、Major 1解決）、Scenario Cのcanonical failure injectionをScenario Bへの依存なしに自己完結させる2段階RSS fixture（canonical executionは全16パス0件→main.pyの既存`return 1`経路で失敗、retry executionは1パスのみ1件）を規定し、`NEWS_AGENT_MIN_INTERVAL_MINUTES=0`をworker起動時envへ追加してinterval gateを無効化し（10.2節・10.5節、Major 2解決）、`NO_PROXY`の説明を`requests`の`should_bypass_proxies()`と`httpx`/`urllib`の`getproxies()`短絡評価とで書き分ける（10.5節、Minor解決）。

---

## 2. Scope（Roadmap v1.3準拠、変更なし）

### In Scope
1. シナリオA〜Fの独立End-to-End検証
2. MVP最終検証としてのfailure-path E2E再実行（5項目）
3. Formal Regressionでの最終確認
4. 承認済みA〜Fを成立させる最小testability seamの設計

### Out of Scope（変更なし）
Post-MVP項目全般、新規Foundation、`release_claim()` Suggestion、Accepted Risk R2/R3/R4/R6/R9の解消、Manual Recovery専用CLI、production activation、Universal Assets／human-gate／Global settings／Remote Tunnel／plugin変更。

**境界の明確化**：23章で示すtestability seam候補は、既存の公開API・既存の環境変数機構・既存ライブラリの標準機能を組み合わせるだけで、production側の意思決定ロジック・durable authority・既存contractを一切変更しないものに限定する。この境界を超える変更が必要と判明した場合は、本書に取り込まずscope-change Gateとして26章で報告する。

---

## 3. Goals（変更なし）

G1〜G6：MVP DoDの実Runtime経路証明、契約結合点の検証、genuine concurrency、外部writeなし、hidden state非共有、Windows決定性。

## 4. Non-Goals（変更なし）

---

## 5. 用語・キー概念

| 用語 | 定義 |
|---|---|
| **Controlled Upstream Boundary** | シナリオA〜Cがmain.pyを実subprocessとして起動する際に、RSS・Anthropic・WordPressの3つの外部通信先すべてを、test-owned local stub HTTPサーバーへ決定的に差し替える設計（7.5章）。 |
| **Disposable Project Copy** | 本書が新規に定義するtest-only helper（7.5.3章）。既存の`docs/design/production_canonical_run_outcome_contract_foundation.md` §29が「Verification isolation」として文章化した設計思想を踏襲するが、その実行可能な実装はリポジトリ内に存在しないことをRound 2レビューで確認済みであるため、**「既存実装の再利用」ではなく「新規test-only helperとしての新規構築」**と正確に位置づける。 |
| **Authoritative Write-Ahead Crash Injection（Scenario C、Round 6で単一worker化）** | Tier 1/Tier 2の2層分離（Round 2〜Round 3）、および2-worker/Phase handoff構成（Round 4〜Round 5、Round 6で撤回）のいずれも用いず、単一の専用test worker process内で、実RetryExecutorが駆動する単一の統合経路の中で、main.py実subprocess自身の解釈系（Python interpreter）に対し、test-owned`sitecustomize.py`（標準Python起動機構＋`PYTHONPATH`のみで発火、production source変更ゼロ）が`WordPressDraftStateManager.record_confirmed()`呼び出しをPOST成功後・原処理実行前にhard-crashへ置き換える、タイミング非依存の決定的設計。crash発火の証拠は、production APIを経由しないtest-owned durable marker file（6.24節）で確立し、実RetryExecutorは`RetryCompositionRoot.from_env(base_dir=<Disposable Project Copy root>)`（6.25節）でmain.pyと同一のstate領域を参照するよう明示的に結合する。crash seam用の4環境変数は、専用worker自身のプロセス内`os.environ`に対し、actual retry呼び出し直前にのみscopedに設定し`try`/`finally`で完全復元する（10.5節）。test harnessプロセス自身の`os.environ`は変更しない（10章）。 |
| **Two-Way Blocking Handshake（Scenario D）** | hookがsentinel書き込み後にtest-owned release signalを待ってblockし、親プロセスがready確認・durable state確認を経てから対象プロセスをkillする、双方向の同期機構（11章）。 |

---

## 6. Existing Architecture Findings

### 6.1〜6.15：Round 1・Round 2版から維持

（6.30〜6.34の既存契約・API、main.pyの外部呼び出し面、Anthropic SDK／python-dotenvの環境変数機構、Legacy/Protected context分岐、既存crash worker precedent、既存test 22 Category Aの経路、Workflow Engineプロセスモデル、durable APIフィールド、Scheduler Driver clock DI、Formal Regression実態、既存6.34テスト12の性質。詳細はRound 1改訂版から変更なし。）

### 6.16 RetryExecutorの内部制御フロー（Round 3調査、B1解決の根拠として維持）

`src/retry_engine/retry_executor.py`の`RetryExecutor.execute(request, lineage, claim)`（`:179-`）を再調査した結果：

- `RetryExecutor`は**自分専用のクロージャ**`post_admission_hook(run_id)`（`:219-222`）を定義し、`self._engine.run(event, ..., post_admission_hook=post_admission_hook, ...)`（`:234-241`）へ渡す。このクロージャは`self._lineage.mark_execution_started(lineage.root_run_id, run_id, claim.owner_token)`を呼ぶだけであり、`run_id`（＝member_run_id）を外部へ公開する経路を持たない。
- `run_id`（member_run_id）は`WorkflowEngineManager.run()`内部で毎回新規生成され（既存事実）、`WorkflowEngineExecutor.run()`の`_complete_side_effect_execution_context(provenance, run_id)`（`workflow_engine_executor.py:90-107`）が、RetryExecutorから渡された`RetryLineageProtectedProvenance`（pre-context、member_run_id未確定）へこの`run_id`を補完し、`build_protected_execution_context(root_run_id=..., attempt_ordinal=..., member_run_id=run_id, side_effect_contract_version=...)`（`side_effect_execution_mode.py:167-176`）で完成形の`RetryLineageProtectedExecutionContext`を構築する。この完成形が`agent_context.side_effect_execution_context`としてNEWS stepの実行（`executor.execute(agent_context)`、`workflow_engine_executor.py:361`）へ渡り、最終的にmain.py実subprocessの環境変数へシリアライズされる。
- `engine_result = self._engine.run(...)`が返す`WorkflowEngineResult`は`run_id`フィールドを持つ（`workflow_engine_executor.py`冒頭docstring 50-51行目で確認済み）。したがって**実行完了後**であれば、`RetryExecutor.execute()`の呼び出し元は`engine_result.run_id`（＝`RetryResult.workflow_engine_result.run_id`）から genuine member_run_id を取得できる。
- **結論（B1への直接的示唆）**：`RetryExecutor`は外部から追加のcrash-injectionフックを差し込める公開の拡張点を持たない（`post_admission_hook`は`RetryExecutor`自身が内部で専有する）。genuine member_run_idは実行完了後にしか安定して取得できないため、実行の**途中**にcrashを注入しつつ、それが真にRetryExecutorが駆動した実行であることを証明するには、`post_admission_hook`の流用ではなく別の仕組みが必要である（6.19・6.20・6.24節で具体化する）。

### 6.16a `RetryQueueManager`/`RetryHistoryManager`の永続化契約（Round 6新規調査、B1解決の中核）

`src/retry_queue/retry_queue_manager.py`・`src/retry_queue/retry_queue_config.py`・`src/retry_history/retry_history_manager.py`・`src/retry_composition/retry_composition_root.py`・`src/retry_enqueue_trigger/retry_enqueue_trigger.py`・`src/retry_engine/retry_manager.py`・`src/retry_runtime_orchestrator/retry_runtime_orchestrator.py`を直接確認した：

- `RetryQueueManager.__init__(self, config)`（`retry_queue_manager.py:39-41`）：`self._items: dict[str, RetryQueueItem] = {}`。ファイルI/O・DB接続・その他いかなる永続化storeも保持しない。`enqueue()`・`dequeue()`・`remove()`・`list()`・`exists()`・`count()`のいずれも、このプロセスローカルなdictへの読み書きのみで完結する（同ファイルdocstring「Queue管理のみを責務とする...永続化はいずれも行わない」）。
- `RetryHistoryManager.__init__(self)`（`retry_history_manager.py:32-33`）：`self._records: dict[str, RetryHistoryRecord] = {}`。同じくプロセスローカルなdictのみ。同ファイルdocstringは「他のどのsrc/*パッケージもimportしない、標準ライブラリのみに依存する」「スレッド安全性は保証しない（既存Manager群と同じく単一プロセス・単一スレッドでの利用を前提とする）」と明記する。
- `RetryCompositionRoot.from_env(base_dir=...)`（`retry_composition_root.py:136-137`）は`queue = RetryQueueManager.from_config(RetryQueueConfig.from_env())`・`history = RetryHistoryManager()`という**引数なしのin-memoryコンストラクタ**を呼ぶだけであり、`base_dir`はこの2つのインスタンス生成には一切関与しない——同じ`base_dir`を渡して`RetryCompositionRoot.from_env()`を2回（＝2プロセスで）呼んでも、2回目の`queue`/`history`はいずれも空の新規インスタンスになる。これがRound 5 B1（2-worker/Phase handoffの構造的断絶）の直接的な技術的根拠である。
- 一方、`RetryManager.retry(run_id, ...)`→`_retry_locked()`（`retry_manager.py:456-494`）は、`self._lineage.find_existing_lineage(run_id)`（disk-backed、`JsonRetryLineageStore`経由）と`self._monitor.get_status(run_id)`（disk-backed、`ExecutionHistoryConfig`経由）のみを参照し、`self._queue`／`self._history`のいずれも一切参照しない（grep範囲`retry_manager.py:456-494`に`self._queue`・`self._history`の出現なしを確認済み）。**`retry()`自体の実行に必要な状態はすべてdisk-backedであり、queue/historyはretry()の実行可否には影響しない。**
- `RetryEnqueueTrigger.enqueue_pending_failures()`（`retry_enqueue_trigger.py:168-263`）は`self._monitor.list_status()`（disk-backed）を走査し、`self._queue.enqueue()`（in-memory）へ書き込む。これは「FAILED/TIMEOUTのrun_idをQueueへ登録した」という**bookkeeping**であり、後続の`retry()`呼び出しの必須の前提ではない（`_retry_locked()`が`existing is None`の場合に自ら`self._lineage.create_new_lineage(run_id, monitor_record)`でlineageを新規作成するため、queueへのenqueueを経由しなくても`retry(run_id)`は単独で機能する、6.16節・上記）。
- 本番の唯一の正規経路である`RetryRuntimeOrchestrator.run_once()`（`retry_runtime_orchestrator.py:159-222`）は、`trigger.enqueue_pending_failures()`（1.）→`scheduler.run_due(jobs=[])`（2.）→`manager.execute_dispatchable_retries(events, dry_run=dry_run)`（3.、内部で`retry_fn=self.retry`として実`RetryManager.retry()`を呼ぶ）→Queue更新/Cleanup/History記録（4.）を**単一プロセス内・単一メソッド呼び出しの中で同期的に**実行する。すなわち、production自身が想定する「enqueueされた候補を実際にretryする」という一連の流れも、常に単一プロセス内で完結する設計であり、2プロセス構成はいかなる既存呼び出し経路にも存在しない。

**結論（B1への直接的示唆）**：
1. `RetryQueueManager`/`RetryHistoryManager`はプロセス境界を越えて共有できない（設計上共有されることを想定していない）。2-worker/Phase handoff構成は、この2つのコンポーネントについて「Worker Phase 1のenqueue結果をWorker Phase 2が引き継ぐ」ことを暗黙に要求しており、実コード上成立しない。
2. Scenario Cが「canonical execution/enqueue」ののち「同じqueue/historyを使ってactual RetryExecutor」を駆動する、という要求（Round 6指示1.）は、**単一の専用test worker process内で完結させることによってのみ、実コード上成立する**。単一プロセス内であれば、同一の`RetryCompositionRoot`インスタンス（＝同一の`queue`/`history`/`lineage`/`manager`オブジェクト参照）を、canonical run後のenqueueブックキーピングと、その後の実`RetryManager.retry()`呼び出しの両方へそのまま使い回せる（10.2節で仕様化する）。
3. `retry()`自体はqueue/historyに依存しないため（上記4点目）、durable queue等の新設は不要である——単一worker内でのin-memoryオブジェクト保持のみで、Round 6指示1.の要求（「durable queue等を新設せず」）を満たしたまま成立する。

### 6.17 `build_protected_execution_context()`の既存呼び出し規約（Round 3調査、維持）

`src/side_effect_safety/side_effect_execution_mode.py:167-176`のdocstringは「protected factory。RetryLineageRecordのauthoritative valueからのみ呼び出してよい（2.2節）」と記す。しかし、既存の出荷済み・Codex承認済み（v6.32.0 Final Review APPROVED）テストである`tests/test_e2e_v6_32_21_execution_mode_propagation_call_site_ac.py`のPart C（`:299-419`、コメント見出し「実call site直接検証」）は、実際には`RetryLineageManager`のlineage recordを一切経由せず、`build_protected_execution_context(root_run_id="root-21ca", attempt_ordinal=1, member_run_id="member-21ca", side_effect_contract_version=1)`（`:328-330`）という手打ちの定数値で直接呼び出している（直接確認済み）。

**結論**：このdocstringの制約は、productionの`WorkflowEngineExecutor`が従うべき運用規約であり、実行時に強制されるinvariantではない。**（Round 4注記）** 10章のScenario Cは、Round 4でこの「lineageを経由しない自己完結callサイト検証」パターン（旧Tier 2）の転用を撤回し、実`RetryExecutor`が実際に駆動する単一の統合経路を直接使う設計へ置き換えた（10章）。本節の事実自体は、`build_protected_execution_context()`のdocstring制約が実行時強制ではないという記録として維持する。

### 6.18 `post_admission_hook`の正確な発火位置・戻り値契約（Round 3調査、B2解決の根拠として維持）

`workflow_engine_executor.py:180-256`を直接確認した：

- `start_result = _call_start_run(...)`（`:180-187`）→ ackチェック（`:188-189`、失敗時`CanonicalAdmissionFailure`）が**先に**完了する。
- その直後（`:201`）、`context.post_admission_hook is not None`の場合のみ、`hook_result = context.post_admission_hook(run_id)`（`:204`）を**同期的に**呼び出し、`hook_ack = hook_result.acknowledged`（`:205`）を取得する。
- hookが例外を送出した場合は`hook_ack = False`（`:206-208`）としてNOT_REACHED終端処理へ進む。
- hookが`acknowledged=True`を返した場合のみ、`:257`の`for step in self._definition.steps:`ループ（NEWS step実行、main.py起動を含む）へ進む。
- **重要な事実確認**：hook呼び出し（`:204`）は`self._engine.run()`と同一スレッド・同一プロセス内で完全に同期的に実行される。hookが**戻らない限り**、`:205`以降のコードは一切実行されない——これはコードの実際の制御フローから直接導かれる不変条件であり、タイミング推測や競合状態に依存しない。
- hookが受け取る引数は`run_id`（`:204`、`context.run_id`と同一値）のみ。追加のcompanion parameterは不要。

### 6.19 main.py実subprocessの起動経路・env継承・同期実行（Round 4で再構成、B1解決の根拠）

`src/pipeline/news_pipeline_runner.py`の`NewsPipelineRunner.run()`（:101-203）を直接確認した：

- main.py実subprocessは`subprocess.run(cmd, cwd=..., capture_output=True, text=True, timeout=self._config.timeout_sec, env=env)`（:138-145）で起動される。`cmd = [str(python_executable), str(main_py_path)]`（:121-124）であり、**`-S`（site処理skip）・`-I`（isolated mode）等のフラグは一切付与されない**——Pythonの通常のsite初期化（`sitecustomize`の自動import含む）がそのまま働く。
- `subprocess.run()`は`Popen`生成後`communicate()`完了まで**呼び出し元スレッドを同期的にblockする**薄いwrapperである。`NewsPipelineRunner.run()`はWorkflowEngineExecutorのNEWS step実行の内部から、Retry Lineageやテストオーケストレータの制御が一切介在しない同一コールスタック上で呼ばれるため、この子プロセスの親プロセスは、**`RetryManager.retry()`を呼び出したテストオーケストレータ自身のプロセス**と同一である。
- **env継承（Round 4の中核的事実）**：`side_effect_execution_context is not None`の場合、`env = {**os.environ, **_serialize_execution_context(side_effect_execution_context)}`（:130）——**テストオーケストレータ自身の`os.environ`が丸ごとmain.py実subprocessへ継承され**、その上にexecution context由来の値がmergeされるだけである。既存コードに、production側が意図的に環境変数をフィルタする「allowlist」実装は、この経路には存在しない（7.5.4節の「Child Env Allowlist」は、テストオーケストレータ自身が自らの`os.environ`をどう構成するかというtest側の運用規約であり、production側の強制フィルタではないことをここで確定する）。
- **例外時の扱い**：`completed.returncode == SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE`（`side_effect_execution_mode.py:148`で`3`と確定、直接確認済み）の場合のみ、`NewsPipelineRunner.run()`は`PipelineResult`を返さず`SideEffectExecutionModeContractError`を**送出する**（:175-184）。それ以外の非ゼロreturncode（`_EXIT_CODE_TOKENS`は`1`・`20`・`21`のみ既知token、それ以外は`NEWS_OUTCOME_ABNORMAL_EXIT`、:63-75）は、例外を送出せず`success=False`の`PipelineResult`として正常に返る（:186-203）。**したがって、Scenario Cのcrash injectionが使うexit codeは`3`（および既知token`0`/`1`/`20`/`21`）と衝突しない値を選ぶ必要がある**（6.24節で`91`を確定する）。
- **結論（B1への直接的示唆）**：main.py実subprocessが（内部で意図的にhard-crashすることで）異常終了しても、これは`subprocess.run()`が観測する「非ゼロreturncode」でしかなく、`RetryExecutor.execute()`・`RetryManager.retry()`を呼び出したテストオーケストレータ自身のプロセスは一切クラッシュしない。`engine.run()`は例外を送出せず正常に戻り値を返す。

### 6.20 WordPress Draft State Storeの書き込み順序とrecord_confirmed()呼び出しの構造的ゲート（Round 4で再確認・拡充、B1解決の根拠）

`src/outputs/wordpress_output.py`・`src/wordpress_draft_state/wordpress_draft_state_manager.py`・`src/side_effect_safety_classifier.py`・`src/retry_lineage/retry_lineage_target_resolution.py`を直接確認した：

- `WordPressOutput.save()`（`wordpress_output.py:82-201`）のwrite-ahead順序は正確に：①`manifest_registrar.register(...)`（durable、:126-134）→②`draft_state_manager.record_attempted(identity, member_run_id)`（durable、:135）→③`requests.post(...)`（実I/O、:159-164）→**④ステータスコード200/201チェック（:166-169、以外なら`RuntimeError`を送出しここで処理が止まる——`record_confirmed()`へは絶対に進まない）**→⑤`response.json()`解析（:171-183）→⑥`draft_state_manager.record_confirmed(identity, context.member_run_id, post_id)`（durable、:186）。
- **この④の存在により、`record_confirmed()`の呼び出し（:186）は、POSTが実際にHTTPステータス200/201で成功したことが構造的に保証された後にしか到達しない**——コードの制御フローそのものが保証する不変条件であり、タイミング観測や外部からのポーリングに依存しない。
- `identity = SideEffectOperationIdentity(root_run_id=context.root_run_id, attempt_ordinal=context.attempt_ordinal, operation_kind=WORDPRESS_DRAFT_CREATION, effect_site=NEWS_STEP, operation_instance_key=article.slug)`（:104-111）。`identity`自体は`member_run_id`を含まない。
- `JsonWordPressDraftStateStore._path_for(identity)`（`wordpress_draft_state_store.py:154-156`）：`{base_dir}/{sha256(identity.as_store_key())}.json`——ファイルパスは`identity`のみから決定的に導出される。
- `SideEffectSafetyClassifier.classify()`（`side_effect_safety_classifier.py:111-112`）：対応するWordPress draft stateが`SideEffectOperationState.ATTEMPTED`の場合、`SideEffectSafetyCategory.IN_PROGRESS_OR_UNKNOWN`を返す。
- `resolve_final_disposition()`（`retry_lineage_target_resolution.py:101-107`）：`worst_case()`が`IN_PROGRESS_OR_UNKNOWN`の場合、無条件に`RetryLineageDisposition.HUMAN_REVIEW_REQUIRED`を返す。
- `RetryExecutor.execute()`内部（`retry_executor.py:292-312`）：`lineage.side_effect_contract_version is not None`かつ`self._manifest`・`self._side_effect_classifier`双方が構築済みの場合、`engine_result.run_id`をkeyにmanifest entriesを取得し`classify()`→`resolve_final_disposition()`の結果を`disposition`として採用する。この一連の呼び出しは`engine.run()`が**正常に戻った直後**、**同一プロセス・同一メソッド呼び出しの中で同期的に**実行される（reconcile_all()やプロセス再起動を経由しない）。
- **結論（B1への直接的示唆）**：`record_confirmed()`（:186）を「原処理を実行させずにcrashへ置き換える」ことができれば、write-ahead stateは`ATTEMPTED`のまま確定し、かつそれは構造的に「POST成功後」の時点でしか起こりえない。main.py実subprocessがこの時点でhard-crashしても、`RetryExecutor.execute()`自身のプロセスは生存し続けており、`engine.run()`から正常に戻った直後、上記の同期的classifier呼び出し経路が`HUMAN_REVIEW_REQUIRED`を導く。真のauthoritative `engine_result.run_id`を使って、である。

### 6.21 プロセス生存確認手段の実態（Round 3調査、維持——Scenario D・F1向け）

- リポジトリ全体を`psutil`でgrepした結果、`src/`・`scripts/`・`tests/`のいずれにも`psutil`の使用箇所は存在しない。`requirements.txt`にも記載されておらず、プロジェクトの`venv`（`venv/Scripts/python.exe`）に`import psutil`を試みると`ModuleNotFoundError`となることを確認した。新規依存追加（test-only用途であっても）は本書のOut of Scope境界（2章）を踏み越える可能性があるため追加しない。Windows標準搭載の`tasklist`・`taskkill`のみを用いる（6.11節既存設計と同じ技術カテゴリ）。
  - 生存確認：`subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV"], capture_output=True, text=True)`の標準出力に対象PIDの行が含まれるかで判定する。
  - 終了確認（cleanup）：同様に`tasklist`で対象PIDの不在を確認する。
  - **Round 4での適用範囲の確定**：この手法はScenario D（11章）・Scenario F1（13.1章）が使う外部`taskkill`の生存確認手段としてのみ必要である。**Scenario C（10章）はRound 4で採用する設計（6.24節）において外部からのプロセスkillを一切行わないため、`tasklist`/`taskkill`のいずれにも依存しない**（Round 3以前の設計からの重要な簡素化）。

### 6.22 Scheduler Driver：Triple-GateとLock解放タイミング（Round 3調査、維持——F1向け、M5解決の根拠）

`scripts/run_scheduler_driver.py`を直接確認した：

- lock取得（`lock.acquire()`、:120）は`SCHEDULER_DRIVER_ENABLED`ゲートチェック（:112-115）の**後**、かつ`SchedulerDriverCompositionRoot.from_env()`呼び出し（:141、Workflow Engine gate評価を含む）の**前**に行われる。
- `SchedulerDriverCompositionRoot.from_env()`が返す`root.workflow_engine_manager`が`NullWorkflowEngineManager`のインスタンスである場合（:146）、`main()`はメッセージを表示して**即座に`return 0`する**（:147-152）。
- `main()`全体は`try/finally`（:126, :188-193）で囲まれており、`finally`節の`_release_if_owned(lock, own_pid)`（:193）は、上記`return 0`を含む**あらゆる終了経路で必ず実行される**。すなわち、`NullWorkflowEngineManager`が構築された場合、lockは取得直後（1サイクル未満の間）に確実に解放される。
- `NullWorkflowEngineManager`が構築される条件は、`workflow_engine_manager.py:94-95`（`if not agent_config.is_ready() or not workflow_engine_config.is_ready(): return NullWorkflowEngineManager()`）が判定する**三重ゲート**——`SCHEDULER_DRIVER_ENABLED`（`scheduler_driver_config.py:31,34-35`）・`AI_AGENT_ENABLED`（`agent_config.py:35,43`）・`WORKFLOW_ENGINE_ENABLED`（`workflow_engine_config.py:31,34`）——いずれも`os.environ.get(X, "false").lower() == "true"`という純粋なbool env var判定であり、実credential（Anthropic API key等）の有無は一切問わない。3つ全てが`true`でなければ`NullWorkflowEngineManager`分岐へ進む。
- **結論（M5への直接的示唆）**：F1が`SCHEDULER_DRIVER_ENABLED=true`のみを設定した場合、1つ目のdriverは`NullWorkflowEngineManager`経路を通り、lockをほぼ即座に解放してしまうため、2つ目のdriverとのlock contentionが構造的に保証されない。F1のfixtureは**三重ゲート全て**（`SCHEDULER_DRIVER_ENABLED=true`・`AI_AGENT_ENABLED=true`・`WORKFLOW_ENGINE_ENABLED=true`）を設定し、かつ1つ目のdriverを`--loop`付きで起動する必要がある——`--loop`の場合、`NullWorkflowEngineManager`分岐チェック自体は`--loop`分岐より前（:146 < :168）にあるため`--loop`の有無に関わらず必ず通過し、三重ゲートを満たしていればこの分岐を通らず、`RetryRuntimeLoop`が`interval_seconds`（既定60秒）ごとにsleepしながらlockを保持し続ける。

### 6.23 SchedulerDriverOrchestrator.run_once()のlock所有権契約とdispatch ledger共有経路（Round 3調査、維持——F2向け、M6/OI-9解決の根拠）

`src/scheduler_driver/scheduler_driver_orchestrator.py`・`src/scheduler_driver/scheduler_driver_lock_integrity.py`・`src/retry_runtime_lock/retry_runtime_lock.py`・`src/scheduler_dispatch_ledger/scheduler_dispatch_ledger_config.py`を直接確認した：

- `SchedulerDriverOrchestrator.run_once()`（`scheduler_driver_orchestrator.py:65-68`）の**最初の文**は`if not _verify_lock_ownership(self._lock_path, self._own_pid): raise LockIntegrityViolationError(...)`である。`run_once()`自身は`RetryRuntimeLock.acquire()`を一切呼ばない——lock取得は`Orchestrator`の外側の責務である。
- `_verify_lock_ownership(lock_path, own_pid)`（`scheduler_driver_lock_integrity.py:47-54`）：`lock_path.read_text().strip() == str(own_pid)`の一致のみを見るfail-closedな検証。
- `RetryRuntimeLock.acquire()`（`retry_runtime_lock.py:46-70`）：`os.open(lock_path, O_CREAT|O_EXCL|O_WRONLY)`でアトミックに新規作成した直後、同一fdへ`str(os.getpid())`を書き込む（作成とPID書き込みが別syscallの2段階操作）。`release()`は`lock_path.unlink(missing_ok=True)`。`with`文にも対応する。
- **結論（M6への直接的示唆）**：F2がCLIスクリプトを経由せず`SchedulerDriverOrchestrator.run_once()`を直接構築・呼び出す場合、呼び出し元（test-only直接構築ハーネス）は`run_once()`呼び出しの**前**に自ら`RetryRuntimeLock(lock_path=...).acquire()`を呼び、取得できた`own_pid=os.getpid()`と同じ`lock_path`を`Orchestrator`コンストラクタへ渡し、呼び出し完了後に`lock.release()`を呼ぶ必要がある。
- `SchedulerDispatchLedgerConfig.from_env(project_root)`（`scheduler_dispatch_ledger_config.py:24-27`）：環境変数`SCHEDULER_DISPATCH_LEDGER_DIR`（**既存の、本Releaseが新設しないproduction設定サーフェス**）が設定されていれば`project_root / <その値>`を、未設定なら既定値`state/scheduler_dispatch`を`ledger_dir`として使う。restartの2プロセス間で同一の`SCHEDULER_DISPATCH_LEDGER_DIR`（絶対パス）を設定すれば、双方が同一のdispatch ledgerディレクトリを参照する——新しいproduction seamは不要である。

### 6.24 Scenario C crash injection機構：test-owned `sitecustomize.py`＋durable evidence markerによるproduction seamレス設計（B1解決の中核、Round 5でevidence契約を刷新）

Round 3までの2つの候補——（a）`wordpress_output.py`へのproduction seam追加、（b）main.py実subprocessを外部からタイミング依存でpollingし`taskkill`する方式——のいずれとも異なる、**production source変更ゼロかつタイミング非依存**の第三の方式（test-owned`sitecustomize.py`）をRound 4で確定した。Round 4 Blocking 1は、この方式自体ではなく、「crash hookが実際に発火したことをどう証拠として取り出すか」の設計——`PipelineResult.returncode==91`をauthoritative統合経路からassertする——が、既存production契約（`NewsAgent`が`returncode`を破棄し`RetryResult`が`WorkflowEngineResult`しか公開しない、`news_agent.py:91-107`・`retry_result.py:41-55`で直接確認済み）と整合しないことを指摘した。本節では、production APIの戻り値に一切依存しない、test-owned durable evidence markerへ置き換える。

**方式の要旨（変更なし）**：main.py実subprocess自身のPython interpreterに対し、標準の`sitecustomize`自動import機構（Python起動時、`site`モジュール初期化の一部として、`sys.path`上に`sitecustomize.py`が見つかれば自動的にimportされる。`-S`/`-I`フラグで無効化されない限り常に働く既存の言語機構）を用いて、test-owned・production source外のフックコードを注入し、`WordPressDraftStateManager.record_confirmed`メソッドをtest-scopeでhard-crashへ置き換える。

**確認した技術的前提（6.19節の事実に基づく、変更なし）**：
1. main.py実subprocessはテストオーケストレータ自身の`os.environ`を丸ごと継承する（6.19節）。
2. main.py起動コマンドに`-S`/`-I`は付与されない（6.19節）ため、通常のsite初期化（`sitecustomize`自動import）が働く。
3. main.py自身は`sys.path.insert(0, str(Path(__file__).parent / "src"))`（`main.py:35`）を実行するが、これは**site初期化（＝`sitecustomize`のimportタイミング）より後**、main.pyのスクリプト本体が実行されてから行われる。したがって`sitecustomize.py`が`wordpress_draft_state.wordpress_draft_state_manager`を早期にimportするには、`src/`ディレクトリ自体のパスを別途明示的に受け取る必要がある。

**確定した設計（test-only、production source変更ゼロ、Round 5でevidence marker契約とimport解決検証を追加、Round 6でenv付与タイミングの記述を10.5節と統一）**：
- 新設env var（**Round 6訂正**：worker起動時のenv（10.5節1.のallowlist）には含めない。10.2節Step 2・10.5節2.で規定する通り、単一の専用worker自身が、`run_once()`呼び出し直前にのみ自身の`os.environ`へscopedに設定し、呼び出し完了後`finally`で除去する4変数として与える。テストハーネス自身の`os.environ`には一切設定しない。`.env`ファイルには一切書かない）：
  - `PYTHONPATH`：test-owned`sitecustomize.py`を格納する専用ディレクトリの絶対パス（1エントリのみでよい）。
  - `WP_OUTPUT_CRASH_SEAM_ENABLED`：`"1"`のときのみ発火。未設定時は`sitecustomize.py`内の分岐が丸ごとスキップされ、production挙動へのdiffはゼロ。
  - `WP_OUTPUT_CRASH_SEAM_SRC_DIR`：patch対象module（`wordpress_draft_state.wordpress_draft_state_manager`）を`import`可能にするため、`src/`ディレクトリ自体の絶対パス（**この値はDisposable Copyの`src/`パスを指す**、7.5.3節）。
  - **（Round 5新規）`WP_OUTPUT_CRASH_SEAM_EVIDENCE_PATH`**：crash hookが実際に発火したことを示すdurable marker fileの絶対パス（シナリオ専用の一時ディレクトリ内、Disposable Copyの外——このファイル自体はDisposable Copyの成果物ではなく、テストハーネスが直接読むevidenceであるため、Zero-Diff検証（7.5.3節）の対象外の場所に置く）。
- `sitecustomize.py`（test-owned、production source外）の内容契約：
  1. `WP_OUTPUT_CRASH_SEAM_ENABLED`が`"1"`でなければ何もしない（即return）。
  2. `WP_OUTPUT_CRASH_SEAM_SRC_DIR`の値を`Path(...).resolve()`で正規化し、`sys.path.insert(0, str(expected_src))`（末尾に`append`するのではなく先頭へ`insert`し、同名のinstalled packageより優先させる）。
  3. `from wordpress_draft_state import wordpress_draft_state_manager as _target_module`をimportした直後、**`Path(_target_module.__file__).resolve()`が`expected_src`配下にあることを検証する**（`Path.is_relative_to()`、Python 3.9+で標準、対象venvは3.14.6で対応済み）。一致しない場合（同名moduleが別の場所——例えばinstalled package・別プロジェクト——から誤って解決された場合）は、**patchを適用せず**、診断のため標準エラー出力へ理由を書いて終了する（fail-closed：patch未適用のままmain.pyの処理が続行されるため、後述のevidence markerが生成されず、10.2節のAssertion「marker fileが存在すること」が構造的に失敗し、テスト全体が明示的に失敗する——「hookが発火したはず」という推定に基づく成功判定を構造的に排除する）。
  4. 検証を通過した場合のみ、`_target_module.WordPressDraftStateManager.record_confirmed`を、**原メソッドを一切呼ばずに**以下を行う関数へクラス属性として直接差し替える：
     a. `WP_OUTPUT_CRASH_SEAM_EVIDENCE_PATH`が指すファイルを新規作成し、`identity`・`member_run_id`・`wp_post_id`（呼び出し引数からそのまま取得できる値）をJSONとして書き込む。
     b. `f.flush()`→`os.fsync(f.fileno())`→`f.close()`（または`with`文でのcontext manager終了）を、`os._exit()`を呼ぶ**前に同期的に完了させる**——単一スレッド・単一プロセス内の逐次実行であるため、書き込み完了とプロセス終了の間にrace窓は存在しない。
     c. `os._exit(91)`する（`91`は`_EXIT_CODE_TOKENS`の既知token`{0,1,20,21}`にも`SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE`（`3`）にも衝突しない値として確定、6.19節。ただし本節の中心的なevidenceはこのexit codeではなく上記a/bのmarker fileであり、exit codeは内部的な整合性確認としてのみ扱う——10.2節）。
- main.py自身が後で（site初期化より後に）`sys.path.insert(0, ...)`で同じ`src/`を挿入し、内部的に`from outputs import WordPressOutput`（→`WordPressDraftStateManager`をimport）しても、Pythonの`sys.modules`キャッシュにより**既にsitecustomizeが早期import・patch済みの同一module/classオブジェクトが再利用される**——再import は発生せず、patchはそのまま有効に保たれる。

**実証実験（Round 4実施、read-onlyの範囲でプロジェクト外に構成、Round 5でも設計変更なしのため再実施不要）**：対象プロジェクトのvenv（Python 3.14.6、`venv/Scripts/python.exe`）を使い、プロジェクト外のscratchpad上に上記と同型の最小再現を構成し、トリガーenv var未設定時は既定動作ゼロ差分、設定時はsitecustomizeが早期importでpatchを適用し、main.pyの`sys.path.insert`を模した遅延importが同一の既patch済みオブジェクトを取得すること（原処理未実行・`os._exit(91)`での即座終了）を実測確認済み（Round 4記録を維持）。

**結論**：
1. **production source変更は一切不要**（`src/`・`scripts/`・`main.py`のいずれも1バイトも変更しない）。標準Python起動機構と、専用worker自身が`run_once()`呼び出し直前にscopedに設定する（10.5節）環境変数のみで成立する。
2. `record_confirmed()`呼び出しは6.20節の通り構造的にPOST成功後にしか到達しないため、**crash injectionのタイミングはPOST成功後・原処理（durable confirm）実行前という正確な窓に、レースなしで決定的に一致する**——タイミング推測・pollingを一切必要としない。
3. WordPress Local Stubへのリクエスト回数は、この設計では構造的に「ちょうど1回」（POSTが成功しなければcrashが発火する地点にすら到達しない）——事後観測ではなく設計上の保証である。
4. **crash hookが実際に発火したことの証拠は、production APIの戻り値（`returncode`等）に一切依存しない、test-owned durable marker fileのみに基づく**（B1解決）。marker fileの存在は、patchされた関数以外のいかなるコードパスからも生成されえないため、「crash hookが実際に到達した」ことの直接証拠となる。

### 6.25 `RetryCompositionRoot`のbase_dir結合とmain.pyのstate path解決の一致（Round 5新規調査、B2解決の中核）

`src/retry_composition/retry_composition_root.py`を直接確認した：

- `RetryCompositionRoot.from_env(cls, base_dir: Path | None = None)`（`:121-216`）は、`project_root = base_dir if base_dir is not None else _PROJECT_ROOT`（`:129`）という**単一のパラメータ**から、以下の**全て**を導出する：
  - `execution_history_config = ExecutionHistoryConfig.from_env(project_root=project_root)`（`:130`）
  - `lineage_config = RetryLineageConfig.from_env(project_root=project_root)`（`:141`）→ `lineage = RetryLineageManager(store=JsonRetryLineageStore(lineage_config.store_dir), ...)`（`:164-170`）
  - `state_dir = project_root / "state"`（`:148`）→ `draft_state_store = JsonWordPressDraftStateStore(base_dir=state_dir / "wordpress_draft_state")`（`:149`）、`manifest_store = JsonProtectedOperationManifestStore(base_dir=state_dir / "protected_operation_manifest")`（`:161`）、`media_upload_coordinator`一式（`:150-157`）
  - `agent_config = AgentConfig.from_env(base_dir=project_root)`（`:187`）、`workflow_engine_manager = WorkflowEngineManager.from_config(agent_config, WorkflowEngineConfig.from_env(project_root=project_root))`（`:188-191`）
  - 上記`manifest_store`・`side_effect_classifier`（`draft_state_store`を内包）は、最終的に`RetryManager.from_config(..., manifest=manifest_reader_facade, side_effect_classifier=side_effect_classifier, ...)`（`:192-202`）へ注入され、`RetryExecutor`（`RetryManager`内部）が実際に使うインスタンスとなる。
- main.py自身が独立に解決する固定パス（`main.py:94,96,104`）：`WORDPRESS_DRAFT_STATE_DIR = Path(__file__).parent / "state" / "wordpress_draft_state"`、`PROTECTED_OPERATION_MANIFEST_DIR = Path(__file__).parent / "state" / "protected_operation_manifest"`——いずれも`__file__`（main.py自身の位置）基準。
- **結論（B2への直接的示唆）**：Scenario Cを実行するmain.pyがDisposable Project Copy内に存在する場合、`Path(__file__).parent`はDisposable Copyのルートと一致する。したがって、テストオーケストレータが実`RetryExecutor`を`RetryCompositionRoot.from_env(base_dir=<Disposable Project Copy root>)`（**この1パラメータのみ**）で構築すれば、`state_dir / "wordpress_draft_state"`・`state_dir / "protected_operation_manifest"`は、main.pyが独立に解決する`WORDPRESS_DRAFT_STATE_DIR`・`PROTECTED_OPERATION_MANIFEST_DIR`と**バイト単位で同一のパス**になる（`<copy>/state/wordpress_draft_state`・`<copy>/state/protected_operation_manifest`）。`lineage_config`・`execution_history_config`・`agent_config`・`workflow_engine_config`も同じ`base_dir`から導出されるため、RetryExecutor・lineage・manifest・draft state・workflow engine管理のいずれも同一のDisposable Copy配下を参照することが、追加の配線なしに単一パラメータで保証される。
- この結合により、10.2節のRetryExecutorは、main.pyが実際に書き込んだWordPress Draft State／Protected Operation Manifestレコードを**同一ディスク上の同一ファイル**として読み取る。`manifest`/`side_effect_classifier`が省略されていない限り（10.2節Precondition）、disposition判定は「manifest欠如によるfail-closed HRR」（`retry_executor.py:294-295`の別分岐）ではなく、実際にmain.pyが書き込んだ`ATTEMPTED`状態を`classify()`が読んだ結果として`HUMAN_REVIEW_REQUIRED`に到達する。

### 6.26 `RetryCompositionRoot`構築が依存するpath override環境変数の網羅（Round 6新規調査、B2解決の中核）

`src/execution_history/execution_history_config.py`・`src/retry_lineage/retry_lineage_config.py`・`src/ai/agent_config.py`・`src/workflow_engine/workflow_engine_config.py`・`src/retry_composition/retry_composition_root.py`・`src/article_media_upload_state/article_media_upload_state_config.py`を直接確認し、リポジトリ全体を`os.environ.get("..._DIR"`で網羅的に`grep`した：

- **`RetryCompositionRoot.from_env(base_dir=...)`（6.25節）の呼び出しグラフ上でpath override機能を持つ環境変数は、正確に2つだけである**：
  1. `EXECUTION_HISTORY_DIR`（`execution_history_config.py:32`、`ExecutionHistoryConfig.from_env(project_root)`内、既定値`"logs/execution_history"`）。
  2. `RETRY_LINEAGE_DIR`（`retry_lineage_config.py:33`、`RetryLineageConfig.from_env(project_root)`内、既定値`"state/retry_lineage"`）。
  - いずれも`return cls(..., history_dir=project_root / dir_name)` / `lineage_dir=project_root / dir_name`という、`project_root`（`Path`）と`dir_name`（`os.environ`由来の`str`）を`pathlib`の`/`演算子で結合する実装である。
- **`AgentConfig.from_env(base_dir=...)`（`agent_config.py:28-41`）・`WorkflowEngineConfig.from_env(project_root=...)`（`workflow_engine_config.py`）はいずれも、ブール値Feature Gate（`AI_AGENT_ENABLED`・`WORKFLOW_ENGINE_ENABLED`）以外の環境変数を一切読まない**——path override機構自体を持たない。
- `RetryCompositionRoot.from_env()`が構築するWordPress Draft State／Protected Operation Manifest／Media Upload関連のstore（`draft_state_store`・`manifest_store`・`media_upload_coordinator`一式）は、`state_dir = project_root / "state"`（`retry_composition_root.py:148`）というハードコードされた相対パスのみから導出され、対応する環境変数を一切読まない。
- **重大な既存の`pathlib`挙動（Round 6新規確認）**：`Path.__truediv__`（`/`演算子）は、右辺（本件では`dir_name`、`os.environ`から取得した生文字列）が絶対パスの場合、**左辺（`project_root`）を無条件に破棄し、右辺の絶対パスをそのまま返す**（Python標準ライブラリの文書化された挙動）。したがって、`EXECUTION_HISTORY_DIR`または`RETRY_LINEAGE_DIR`が host（テストハーネスを起動するシェル・CI環境等）から**絶対パス**として継承された場合、`project_root`に`<Disposable Project Copy root>`を渡していても、実際に構築される`history_dir`/`lineage_dir`はその絶対パス（例えば開発者が手動検証のためシェルに設定していたoriginal projectの`logs/execution_history`）へ無条件にすり替わる——`base_dir`パラメータによる隔離契約（6.25節）を迂回する、fail-openな抜け道である。
- `ArticleMediaUploadStateConfig.from_env()`（`article_media_upload_state_config.py:30`）は`ARTICLE_MEDIA_UPLOAD_STATE_DIR`を読むが、このクラス自体は`src/`・`scripts/`のいずれからも呼び出されていない（`grep -rn "ArticleMediaUploadStateConfig" src/ scripts/`の一致箇所は定義ファイルと`__init__.py`のみ）——`RetryCompositionRoot.from_env()`は`ArticleMediaUploadStateManager`を`state_dir / "article_media_upload_state"`というハードコードされたパスで直接構築しており（6.25節参照箇所と同型）、この設定クラスを経由しない。したがって**Scenario Cの呼び出しグラフには現れず、authority containmentの対象外**であることを確認した。
- `SCHEDULER_DISPATCH_LEDGER_DIR`（`scheduler_dispatch_ledger_config.py`、6.23節既出）も同様に`RetryCompositionRoot.from_env()`の構築グラフには現れない（Scenario F専用、`SchedulerDispatchLedgerConfig`は`scripts/run_scheduler_driver.py`/`SchedulerDriverCompositionRoot`側のみが参照する）。Scenario Cのauthority containment対象には含めない。
- main.py自身は、`EXECUTION_HISTORY_DIR`・`RETRY_LINEAGE_DIR`のいずれも読まない（0章・6.19節既出の通り、main.pyが参照する環境変数はWordPress/Anthropic/RSSの外部通信先差し替えとexecution context由来の値に限られ、`grep`で該当なしを確認済み）——これら2変数はScenario Cの**専用test worker process自身**（`RetryCompositionRoot.from_env()`を呼ぶ側）にのみ関係し、main.py実subprocess側の隔離契約（7.5.3節）には影響しない。

**結論（B2への直接的示唆）**：Scenario Cの専用test worker process（10.2節）は、`RetryCompositionRoot.from_env(base_dir=<Disposable Project Copy root>)`を呼び出す**前**に、自身が構築するprocess environment（10.5節で規定する明示的なenv dict）が`EXECUTION_HISTORY_DIR`・`RETRY_LINEAGE_DIR`のいずれも含まないこと（未設定のまま＝各Configの既定値`"logs/execution_history"`・`"state/retry_lineage"`が`project_root`（Disposable Copy）からの相対パスとして正しく解決されること）を保証しなければならない。これにより、host環境からの偶発的なpath override経路が構造的に排除される（10.5節で完全仕様化する）。

---

## 7. Design Decision A：シナリオContract共通フォーマット（変更なし）

## 7.5 Design Decision A'：Controlled Upstream Boundary for A–C（Round 3で完全仕様化）

### 7.5.1 3つの外部通信先の扱い（Round 1版から維持、変更なし）

| 対象 | 差し替え手段 | production変更要否 | 根拠 |
|---|---|---|---|
| WordPress | `WP_SITE_URL`環境変数 | 不要 | 6.6/6.7節 |
| Anthropic | `ANTHROPIC_BASE_URL`環境変数（SDKソース直接確認済み） | 不要 | 6.7節 |
| RSS | 既存の差し替え機構なし | **必要**（P1、7.5.1a節で完全仕様化） | 6.6節 |

### 7.5.1a Production Implementation候補 P1：RSS Feed URL Override（完全仕様、B3/Round4 M1/Round5 M1/Round5 M4/Round7 Major3/Round8 Major1解決）

Round 2 B3は「P1は必須だが例示のみの候補で、env値スキーマ・validation・空/不正値時挙動・source-nameマッピング・承認済み実装のいずれも未定義」と指摘した。Round 3 Major 1は「validationがnon-empty文字列とprefixのみのチェックであり、scheme-onlyのような不正URLを許容してしまう」と指摘した。Round 4はこれを`urllib.parse.urlparse()`ベースへ改めたが、Round 4 Major 1は「`urlparse()`は大文字schemeを小文字へ正規化するため`HTTPS://...`が"case-sensitive"チェックを素通りする」「`hostname`非空チェックのみでは空白混入・不正percent-escape・`.port`未検証（不正/範囲外ポート）を防げない」と指摘した。Round 5はこれらのedge caseを塞いだが、Round 5 Major 4（M4）は「Python標準の`json.loads()`は既定でJSON重複キーを検出せず後勝ちで上書きするため、`{"4Gamer": "<正当なURL>", "4Gamer": "<攻撃者が意図するURL>"}`のような重複キー入力が無警告で通過してしまう」「Unicode制御文字チェックが`ord(c) < 0x20`（C0域）のみであり、C1域（`0x7F`〜`0x9F`）およびUnicode書式文字（`Cf`カテゴリ、双方向テキスト制御文字等によるhostname表示偽装に悪用されうる）を見落としている」「検証を通過した値をそのまま（`.strip()`前の生文字列のまま）返しており、trimmed値をcanonical resultとして返す契約がない」と指摘した。以下、Python標準ライブラリのみで実装可能な、これらのedge caseをすべて塞いだ最終仕様として確定する。**P1はRelease 6.35のシナリオA〜C（Controlled Upstream Boundary、7.5.1節）を成立させるために必要な、Release 6.35 implementation phaseの一部である。本Architecture Phase（本書）自体はP1を実装しないが、これはP1をRelease 6.35のスコープ外へ先送りすることを意味しない——P1専用のHuman Gate承認を得た上で、Release 6.35のimplementation phase内で実施する（26章）。**

- **対象ファイル**：`src/collector.py`
- **対象箇所**：モジュールレベル定数`RSS_FEEDS`（`:36-53`、`dict[str, str]`、16キー：`"4Gamer"`, `"Game*Spark"`, `"IGN"`, `"GameSpot"`, `"Eurogamer"`, `"PlayStation公式"`, `"Nintendo公式"`, `"Xbox公式"`, `"Gematsu"`, `"VGC"`, `"Insider Gaming"`, `"PC Gamer"`, `"Nintendo Life"`, `"Push Square"`, `"Pure Xbox"`, `"Steam"`）が定義された直後に、この定数を参照する既存箇所——**唯一の実行時参照経路である`collector.py`内の`collect_all_news()`（`:132-149`、`for source_name, feed_url in RSS_FEEDS.items():`、`:146`）**——が**直接`RSS_FEEDS`を参照するのをやめ、新設する解決関数の戻り値を参照するよう変更する（Round 7で参照経路を訂正：`main.py:484`は`collect_all_news(max_items_per_feed=20)`を呼び出すだけであり、`RSS_FEEDS`自体を直接参照しない）**。`FEED_GROUPS`（`collector.py:55-61`）は16キーの文字列のみを参照しURL自体は保持しないため、変更不要。
- **新設関数**：`_resolve_rss_feeds() -> dict[str, str]`
  - 環境変数`NEWS_RSS_FEED_URLS_OVERRIDE`が**未設定**の場合：`RSS_FEEDS`（既存定数）をそのまま返す。**この分岐が唯一の意思決定ロジックであり、既存のproduction挙動を1バイトも変更しない。**
  - 環境変数が設定されている場合：
    1. **JSON重複キーをfail-closedに拒否した上でparseする（Round 6で追加、M4解決）**：`json.loads(value, object_pairs_hook=_reject_duplicate_keys)`という形で、`object_pairs_hook`（Python標準`json`モジュールの公開パラメータ）に、`list[tuple[str, Any]]`（key-valueペアの出現順そのままのリスト）を受け取り、同一キーが2回以上出現していれば`ValueError`を送出し、そうでなければ通常どおり`dict(pairs)`を返す小関数を渡す。これにより、`json.loads()`の既定挙動（重複キーを後勝ちで無警告に上書きする）を経由せず、重複キー自体を検出可能にする。parse失敗（不正なJSON、または上記の重複キー検出）→ `ValueError`を送出する（fail-closed、silent fallbackしない）。
    2. parse結果が`dict`でない、またはキー集合が`RSS_FEEDS.keys()`と**完全一致しない**（過不足いずれも許容しない）場合 → `ValueError`を送出する。source-name mappingは既存の16キー文字列と厳密に一致させることで、`FEED_GROUPS`側の変更を一切不要にする。
    3. **各値のURL validation（Python標準ライブラリ`urllib`・`re`・`unicodedata`・`ipaddress`のみで実装可能。Release 6.35が必要とするHTTP(S) feed URL contractに限定し、汎用URL validatorへは拡張しない）**：各値`v`について、以下の手順で検証し、いずれかに該当すれば`ValueError`を送出する（1つでも不正な値があれば全体を拒否する、部分許容しない）：
       a. `type(v) is not str`（bool等の紛れ込みも拒否）→ 拒否。
       b. `trimmed = v.strip()`。`trimmed == ""`（空文字列・空白のみ）→ 拒否。
       c. **空白・Unicode制御文字チェック（Round 6でC1域・書式文字を追加、M4解決）**：`trimmed`中のいずれかの文字が、(i) `str.isspace()`（内部の空白、`.strip()`は先頭・末尾のみ除去するため別途必要）、(ii) `ord(c) < 0x20`（C0制御文字）、(iii) `ord(c) == 0x7F`（DEL）、(iv) `unicodedata.category(c) in ("Cc", "Cf")`（`Cc`＝C1域を含む全制御文字カテゴリ、`Cf`＝ゼロ幅スペース・双方向テキスト制御文字（`U+202E` RIGHT-TO-LEFT OVERRIDE等）を含む書式文字カテゴリ——hostnameの見た目を偽装しうる非表示文字を包括的に排除する）のいずれかに該当する場合 → 拒否（例：`"https://exam ple.com"`のようなhost中の空白混入、および`"https://exa‮mple.com"`のような双方向制御文字によるhostname偽装を、`urlparse`のhostname抽出結果に依拠せず直接排除する）。
       d. **schemeの大文字小文字を区別した検証（Major 1解決、維持）**：`trimmed.startswith("http://")`または`trimmed.startswith("https://")`のいずれか（**小文字のprefixとの生文字列比較**、`urlparse().scheme`の正規化結果には依拠しない——`urlparse()`は`scheme`を小文字へ正規化して返すため、この属性だけを見ると`"HTTPS://..."`のような大文字schemeも通過してしまうことが判明したため、生の入力文字列に対するprefix比較へ置き換える）に該当しない場合 → 拒否。
       e. `parsed = urllib.parse.urlsplit(trimmed)`で構造解析する。
       f. **hostname/IPv4 literalの構文検証（Round 9で代替IPv4表記の混入を遮断、Round 8 Major 1解決）**：`parsed.hostname`が`None`または空文字列 → 拒否（`urlsplit("https:///path").hostname`は`None`となるため、scheme-onlyやhost欠落のURLはここで拒否される）。非空の場合、`urlsplit()`が返す`hostname`（既に小文字正規化済み、Python標準ライブラリの文書化された挙動）を、以下の**優先順位付きの2分岐**で判定する（Round 8版はこの2分岐自体は導入したが、分岐2のRFC 1123正規表現が数字のみのラベルも構文上合法として受理してしまうため、`127.1`・`2130706433`・`0x7f.0.0.1`のような、正準的な4-octet dotted-quad表記ではないがWindowsの`getaddrinfo`をはじめ多くのsocket実装がIPv4の代替表記として解釈しうる値が、DNS hostname判定を素通りしてしまうことをRound 8 Codexレビューが指摘した——Round 9でこの穴を塞ぐ）：
          - **分岐1（strict decimal dotted-quad IPv4のみをIPv4 literalとして受理する）**：`hostname`が正規表現`^\d{1,3}(\.\d{1,3}){3}$`（4つのドット区切りグループ、各グループ1〜3桁の10進数字のみ、DNS hostnameのラベル構文チェックより前に判定する）に一致する場合、**この時点で「IPv4 literalとして解釈する」ことが確定し、DNS hostname分岐へは一切fallbackしない**。続けて`ipaddress.IPv4Address(hostname)`の構築を試み、例外が送出されなければ受理、例外が送出されれば（各octetが0〜255の範囲外等）**即座に拒否**する（例：`999.999.999.999`は分岐1でIPv4形状と判定された時点でDNS分岐の対象から外れ、`ipaddress.IPv4Address("999.999.999.999")`が`ValueError`を送出するため拒否される）。この分岐が受理するのは、4つの10進グループがドットで区切られた**strict decimal dotted-quad表記のみ**であり、短縮形（`127.1`、2グループしかないため分岐1の正規表現自体に一致せずここでは扱われない）・10進整数一括表記（`2130706433`、ドットを含まないため同様に分岐1の正規表現に一致しない）・16進octet表記（`0x7f.0.0.1`、`\d`は10進数字のみを表しアルファベットの`x`・`f`を含む文字列には一致しないため同様）は、分岐1では一切IPv4として解釈されない。
          - **分岐2（分岐1に該当しない場合のみDNS hostname形式を判定、Round 9で数字のみラベル・16進prefixラベルの拒否を追加）**：正規表現 `^[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)*$`（RFC 1123準拠のラベル構文：各ラベルは英数字で始まり英数字で終わる、ラベル内部はハイフン可、ラベル長1〜63文字）に完全一致し、かつ`hostname`全体の長さが253文字以内であることをまず要求する（一致しなければ拒否）。この正規表現一致に加え、`hostname.split(".")`で得られる**各ラベル**について、以下のいずれかに該当する場合は追加でfail-closedに拒否する（分岐1が正準表記のIPv4を既に受理済みであるため、分岐2に到達したラベルが数字のみ・16進prefix付きである場合は、代替IPv4表記の疑いがあるものとして一律拒否する。正当な英字を含むドメインラベルはこの追加チェックの対象外）：
            - ラベルが`^[0-9]+$`（10進数字のみで構成される）に一致する場合 → 拒否する（例：`127.1`の各ラベル`127`・`1`、単一ラベルの`2130706433`——いずれも分岐1のstrict dotted-quad形式には一致しないためここに到達するが、数字のみのラベルはIPv4の短縮/整数表記の疑いがあるため、通常のDNSホスト名としては受理しない）。
            - ラベルが`^0x[0-9a-f]+$`（`0x`prefixに続く16進数字のみ）に一致する場合 → 拒否する（例：`0x7f.0.0.1`の各ラベル`0x7f`・`0`・`0`・`1`——`0`単体は上記「数字のみ」規則で既に拒否されるが、`0x7f`はこの規則で個別に拒否する）。
          - **`localhost`の扱い（Round 9で明示）**：文字列`"localhost"`は英字のみの単一ラベルであり、上記のいずれの追加拒否規則にも該当しないため、分岐2のRFC 1123正規表現一致により通常のDNS hostnameとして問題なく受理される——特例分岐は不要である。ただし、既存のLocal Stub運用（7.5.5節）は一貫して`127.0.0.1`（分岐1のIPv4 literal）をURLのhostとして使う設計であり、`localhost`という文字列自体がLocal Stub URLとして使われることは想定していない。
          - IPv6 literal（`[::1]`等）・その他の形式は、分岐1にも分岐2にも一致しないため自動的に拒否される（Release 6.35が必要とするHTTP(S) feed URL contractの範囲外、2章のスコープ境界、汎用URL validatorへは拡張しない）。
       g. **percent-escapeの妥当性チェック（維持）**：`re.search(r"%(?![0-9A-Fa-f]{2})", trimmed)`が一致する場合（＝`%`の直後に2桁の16進数が続かない箇所が1つでもある場合）→ 拒否（不正なpercent-encoding）。
       h. **portの妥当性チェック（Round 8で明示的な空portの拒否を追加、Round 7 Major 3解決）**：まず、`parsed.netloc.rpartition("@")[2]`（userinfoを除いたhost:port部分。分岐fで`parsed.hostname`はIPv4/DNS hostname形式に既に限定されているため、ここでの`@`・`:`はuserinfo区切り・port区切りとしてのみ現れる）が`":"`で終わる場合（＝`https://example.com:/feed`のように、コロンの直後にport数字が一切ない**明示的な空port**の場合）→ **拒否する**（`urlsplit("https://example.com:/feed").port`は`None`を返すため、これを`ValueError`捕捉やNone-as-omitted判定だけに頼ると「省略」と誤って同一視してしまう——Round 7版の抜け道）。この明示的空portチェックを通過した場合のみ、続けて`parsed.port`への属性アクセスを`try`で囲む。`urllib.parse.SplitResult.port`は、ポート部分が非数値または`0`〜`65535`の範囲外の場合に`ValueError`を送出する（Python標準ライブラリの文書化された挙動）。この`ValueError`を捕捉した場合 → 拒否。**さらに、`ValueError`が送出されず`parsed.port`が正常に取得できた場合でも、`parsed.port`が`None`（コロン自体が存在しない、真にポートが省略された場合のみ有効な省略として受理する）でなく、かつ`parsed.port == 0`である場合 → 拒否する**（`urllib.parse`は`0`を数値として有効に許容するが、port `0`は接続先として意味を持たない予約値であり、本契約が受理する有効なport値は「コロンを伴わない真の省略（既定80/443を使う）」または`1`〜`65535`の整数のいずれかに限定する）。
       i. 上記a〜hのいずれにも該当しない場合のみ妥当な値として受理し、**`trimmed`（`.strip()`後の値）をこの値のcanonical resultとして採用する**（元の生文字列`v`ではなく`trimmed`を後続処理へ渡す。末尾のpath/query/fragmentの形式は問わない——RSS fetch自体の成否は既存の`fetch_from_feed()`のHTTP層に委ねる）。
    4. **全て妥当な場合のみ、キーはそのまま・値は3.で確定した`trimmed`値に置き換えた新しいdictを返す（Round 6で明確化、M4解決）**：元のparse結果dict（`.strip()`前の生の値を保持する）をそのまま返すのではなく、`{key: trimmed_value for key, trimmed_value in ...}`という形で、検証を通過した`trimmed`値のみからなる新規dictを構築して返す（全16件を置き換える、部分置換は許容しない）。これにより、`_resolve_rss_feeds()`の戻り値は常に「先頭・末尾に空白を含まない、validationを通過した値」という不変条件を満たす。
  - **fail-closed の意味**：不正・不完全な設定は、production defaultへの静かなフォールバックではなく、明示的な例外として即座に失敗する。
  - **Local Stub URLとの整合性確認（Round 9でstrict dotted-quad判定に基づき再確認）**：`http://127.0.0.1:<動的port>/rss/...`という形式は、上記a〜iの全チェックを問題なく通過する（`hostname="127.0.0.1"`は分岐1のstrict decimal dotted-quad形式に一致し、`ipaddress.IPv4Address("127.0.0.1")`が例外を送出しないため受理される。動的に払い出されるportは`1`〜`65535`の有効範囲内（`0`は使われない）、コロンの直後が必ず数字であるため明示的空portにも該当せず、空白・Unicode制御文字・不正percent-escapeも含まない）——Local Stub運用に追加の特例分岐は不要。
  - **Prohibited Outcome（Round 9で代替IPv4表記の拒否を追加、Round 8 Major 1解決）**：`"https://"`（scheme-only）・`"https:///path"`（host欠落）・`"ftp://example.com/feed"`（非対応scheme）・`"HTTPS://example.com/feed"`（大文字scheme）・`"https://exam ple.com"`（host中の空白）・`"https://example.com:99999"`（範囲外port）・`"https://example.com:0"`（port `0`）・`"https://example.com:/feed"`（明示的な空port——`parsed.port is None`だが真の省略ではない）・`"https://example.com:abc"`（非数値port）・`"https://999.999.999.999/feed"`（IPv4形状だがoctet範囲外、分岐1が確実にDNS分岐へのfallbackを禁止することにより拒否を保証）・`"https://127.1/feed"`（**IPv4の短縮表記、Round 9で追加——分岐1のstrict dotted-quad正規表現には一致せず分岐2へ進むが、ラベル`127`・`1`がいずれも数字のみのため分岐2の追加規則で拒否される**）・`"https://2130706433/feed"`（**IPv4の10進整数一括表記、Round 9で追加——単一の数字のみラベルとして分岐2の追加規則で拒否される**）・`"https://0x7f.0.0.1/feed"`（**IPv4の16進octet表記、Round 9で追加——`0x7f`ラベルが16進prefix規則で拒否される**）・`"https://exa_mple.com/feed"`（アンダースコア等RFC 1123ラベル構文外の文字を含むhostname）・`"https://example.com/%zz"`（不正percent-escape）・`""`／空白のみ・非文字列値・**JSON中の重複キー（例：同一source-name文字列が2回出現するJSONオブジェクト）**・**C1域制御文字またはUnicode書式文字（`Cf`カテゴリ、双方向テキスト制御文字を含む）を含む値**のいずれもが、validationを通過してしまうこと。**戻り値の各URLが`.strip()`前の生文字列のままである**（trimmed値がcanonical resultとして採用されていない）こと。
- **Local Stubとの対応**：実装フェーズでは、シナリオA〜Cの各テストが、Local Stub HTTPサーバー上の16個の個別パス（例：`http://127.0.0.1:<port>/rss/4gamer`等、source-name→pathの対応はtest側で1対1に固定する）を指す16キー全てを含むJSON文字列を`NEWS_RSS_FEED_URLS_OVERRIDE`へ設定する。これらのURLは完全なscheme+host形式であり、上記validationをそのまま通過する。
- **opt-in性**：この環境変数は本番運用では設定されない。設定されない限り、`_resolve_rss_feeds()`は`RSS_FEEDS`をそのまま返す一本道であり、新しい分岐によるproduction挙動への影響はゼロ。
- **Human Gate**：この変更（新設関数の追加、既存参照箇所の1箇所の書き換え）は、Release 6.35 implementation phase内でのP1着手前に独立したHuman Gate承認を要する（26章）。本書はこの承認を代替しない。

### 7.5.2 `.env`実値の混入防止（変更なし）

`PYTHON_DOTENV_DISABLED`環境変数（python-dotenv標準機能、6.6/6.7節で検証済み）で`main.py`の`load_dotenv()`を無効化する。main.pyの設定読み取り箇所（`:92-104`,`:423-476`）はいずれも`load_dotenv()`より後に実行されるため、`load_dotenv()`を無効化した上でChild Env Allowlist（7.5.4節）が渡す値のみが有効になる。missed readのgapはない（Round 2 focus 1で確認済み）。

### 7.5.3 固定出力/状態パスの隔離：Disposable Project Copy（Round 4でexact whitelistへ確定、M2解決）

**Round 2の指摘を受け、Round 1版の「既存Disposable Copyパターンを再利用する」という記述を撤回する。** リポジトリ全体を検索した結果、`docs/design/production_canonical_run_outcome_contract_foundation.md` §29が言及する「Disposable Copy」は**散文としてのみ存在し、実行可能な実装はリポジトリ内のどこにも存在しない**ことを確認した。

**Disposable Project Copyは、本Releaseが新規に構築するtest-only helperとして正確に位置づける**（T7候補、23.2章）。Round 3は「`at least`という表現でwhitelistがopen-endedになっている」とMajor 2で指摘した。以下、`03_game_content_ai`のプロジェクトルート直下を実際に列挙した結果（Round 4で`ls`により直接確認済み）に基づき、**「その他」の余地を残さない、閉じた（closed-world）whitelist**として確定する。

**プロジェクトルート直下の実際の構成**：`.claude/`・`.env`・`.env.example`・`.pytest_cache/`・`.run/`・`__pycache__/`・`docs/`・`logs/`・`main.py`・`output/`・`prompts/`・`README.md`・`requirements.txt`・`scripts/`・`src/`・`state/`・`tests/`・`venv/`。`.gitignore`はプロジェクト直下には存在しない（リポジトリルートの`.gitignore`のみ）。`pyproject.toml`・`setup.py`・`setup.cfg`・`Pipfile`はいずれも存在しない。

- **コピー対象（exact whitelist、これ以外は一切コピーしない）**：
  1. `src/` 配下の全ての `*.py` ファイル（再帰的、ディレクトリ構造を保持。`src/__pycache__/`以下は除く）
  2. `scripts/` 配下の全ての `*.py` ファイル（現状フラット構成、18ファイル。将来サブディレクトリが追加された場合は本whitelistの再確認が必要）
  3. `main.py`（プロジェクトルート直下、単一ファイル）
  4. `.env.example`（プロジェクトルート直下、単一ファイル。実`.env`は対象外）
  5. `requirements.txt`（プロジェクトルート直下、単一ファイル。他の依存関係設定ファイルは現状存在しないため対象なし）
  6. `prompts/` 配下の全ての `*.md` ファイル（4ファイル：`article_prompt.md`・`importance_prompt.md`・`seo_prompt.md`・`x_post_prompt.md`。`src/importance_judge.py:12`・`article_generator.py:11`・`seo_title_generator.py:10`・`x_post_generator.py:10`がいずれも`PROMPT_FILE = Path(__file__).parent.parent / "prompts" / "..."`という`__file__`基準の相対解決でこれらを参照することを直接確認済み——コピー内でも自動的に正しく解決される）
- **明示的除外（プロジェクトルート直下の残り全項目、1つずつ理由を明示する）**：
  - `.git/`：バージョン管理データ（プロジェクトルート自体には存在しないが、リポジトリルートの`.git/`を指すため対象外）
  - 実`.env`：credentials
  - `.claude/`：Claude Code local設定（機械固有、シナリオ実行に無関係）
  - `.pytest_cache/`：pytestのtool cache
  - `.run/`：実行時lock/ログ（`retry_runtime_log.jsonl`等）
  - `state/`：実行時durable state（`state/retry_lineage/`等）
  - `output/`：実行時生成物
  - `logs/`：実行時生成ログ
  - `__pycache__/`：バイトコードキャッシュ（どの階層に存在しても除外）
  - `venv/`：コピーしない。既存プロジェクトのvenvをabsolute pathで参照する
  - `README.md`：シナリオ実行に不要なドキュメント
  - `tests/`：Disposable Project Copyを**駆動する側**（テストオーケストレータ）のコードであり、コピー**される**側には含めない
  - `docs/`：本設計書を含むArchitecture文書一式。シナリオ実行に不要
  - production credentials・secrets類（実`.env`以外に存在しないことを`ls`で確認済み）
- **venv**：コピーしない。既存プロジェクトのvenvをabsolute pathで参照する。
- **環境**：`PYTHONDONTWRITEBYTECODE=1`、Python起動時`-B`オプション、`PYTHON_DOTENV_DISABLED=1`（7.5.2節）を併用する。**6.24節のScenario C crash seamが使う`PYTHONPATH`エントリ（test-owned`sitecustomize.py`格納ディレクトリ）は、この`-B`指定とは独立した別のenv var（`PYTHONPATH`）であり競合しない。**
- **Zero-Diff証拠契約（Round 4でOriginal Project側をfull-tree検査へ強化、M2解決）**：Round 3は「target setだけでなく、out-of-scope新規ファイル生成も検出できるようにする」と指摘した。この指摘に対応し、Original Project側の比較を「コピー対象ファイルのみ」から「プロジェクトルート全体（`.git/`・`venv/`を除く）」へ拡張する——`.git/`・`venv/`の除外は、シナリオ実行中に正当に変更されうる余地が本来ゼロである以上比較しても意味がなく、かつ再帰的ハッシュ計算のコストが大きいため、純粋に実務上の理由で除外する：
  1. コピー**前**に、Original Project（実リポジトリ）の**プロジェクトルート全体**（`.git/`・`venv/`を除く）のbefore-manifest（相対パス・サイズ・SHA-256ハッシュの一覧、`os.walk()`等で再帰的に収集）を作成する。
  2. Disposable Copy内でシナリオ実行を完了させる。
  3. 実行**後**、同じ範囲でOriginal Projectのafter-manifestを再作成し、before-manifestと**パス集合・ハッシュ値の両方が完全一致**することを確認する（新規ファイルの出現はafter-manifestにbefore-manifestにないパスが増えることで検出され、コピー対象の6項目に限定しないことで**out-of-scope新規ファイルも同じ仕組みで検出できる**）。
  4. Disposable Copy側は、シナリオが期待するartifact以外のdiffがないことを、allow-listと照合して確認する。
- **Disposable Copy自体の破棄条件**：各シナリオテストの完了時（成功・失敗いずれの場合も）、Disposable Copyディレクトリは既定でテスト終了時に`shutil.rmtree()`等で削除する（teardown）。診断目的で明示的に保持したい場合のみ、test-only環境変数（例：`DISPOSABLE_COPY_KEEP=1`）で削除をスキップできるオプトイン機構を設ける——既定は削除、保持は明示的opt-inのみ。
- **A〜C・F1での利用方法**：シナリオA・B・C・F1（13.1節）は、いずれもこのDisposable Project Copyの中でmain.py（またはF1の場合は`scripts/run_scheduler_driver.py`）を実subprocessとして起動する。main.pyの固定パス・`scripts/run_scheduler_driver.py`の固定lockパスは、いずれもコピー内のファイル自身の位置を基準に解決されるため、コピー内で実行するだけで自動的に隔離される（production code変更不要）。

### 7.5.4 Child Env Allowlist（Round 6でシナリオC向け記述を10.5節へ委譲、Post-Round 10 Amendmentでシナリオ別に実装実態へ整理）

**（Round 4注記、維持）** 6.19節で確認した通り、main.py実subprocessへ渡される`env`は`{**os.environ, **_serialize_execution_context(...)}`であり、production側（`NewsPipelineRunner`）が能動的にフィルタする仕組みは存在しない。したがって「Child Env Allowlist」とは、**test側が主体的にどう`env`を構成するかという運用規約の総称**であり、production側の強制メカニズムではない。

**（Round 6訂正、維持）** シナリオCについては crash seam4変数の扱いおよびauthority containment（`EXECUTION_HISTORY_DIR`・`RETRY_LINEAGE_DIR`の除外を含む）を10.5節で完全に再規定する。

**（Post-Round 10 Amendment：Round 6版の「シナリオA・B・F1を一括りに、テストハーネス自身の`os.environ`を構成する」という記述を撤回し、実装が実際に採った3つの異なる方式へ分離する）** P1・Scenario A〜Fのtest実装フェーズの結果、この一括りの記述は実態と一致しないことが判明した。テストオーケストレータが実subprocessへ`env=`を明示的に渡せる場合（`subprocess.run`/`subprocess.Popen`の`env`引数）と、実行対象を同一プロセス内で直接構築する場合とで、必要な方式が異なるためである。以下、シナリオ単位で確定する：

- **A・F1（closed allowlist subprocess env）**：main.py（A）または`scripts/run_scheduler_driver.py`（F1）を実subprocessとして起動する際、`subprocess.run`/`subprocess.Popen`の`env=`引数へ、**hostの`os.environ`を無条件コピーせず、必要な変数のみを列挙して都度新規に構築したdict**を渡す（10.5節1.のallowlist方式と同型）。この方式では、テストハーネス自身の`os.environ`は一切変更されない。allowlistの内容は10.5節(a)〜(f)に準じ、A・F1固有のFeature Gate（F1のみ`SCHEDULER_DRIVER_ENABLED`を追加、13.1節Triple-Gate）を除き共通である。
- **B（`ExactEnv`：test process envの完全置換＋`try`/`finally`復元。Post-Round 10 Amendment第2回でoverlay方式から変更、Codex delta review Major#1解決）**：Scenario Bは`WorkflowEngineManager`・`RetryCompositionRoot`をテストドライバ自身のプロセス内で直接構築する（Scenario Cのような専用worker subprocessへの分離を必要としない、6.16a節）ため、`env=`引数を渡す対象subprocessが存在しない。**当初の実装（第1回Amendment）はテストハーネス自身の`os.environ`へ必要な変数をoverlay（上書き）するだけの方式（`ScopedEnv`）を採っていたが、これではhost由来のambient変数（`PYTHONPATH`・絶対path override等）が保持されたまま残り、main.py実subprocessが`{**os.environ,...}`経由（6.19節）でそれらを継承しうる、という閉じたallowlist（A・C・D・F1・F2）と同水準の隔離になっていない欠陥をCodex delta reviewが指摘した（Major#1）。** 第2回Amendmentでは`ExactEnv`——`os.environ`を丸ごと退避した上で指定した閉じた集合のみへ完全に置換し、シナリオ完了後（正常終了・例外いずれの経路でも）`try`/`finally`で元の状態へ完全復元する方式——へ変更した。main.py実subprocessは、この置換後のテストハーネスの`os.environ`を`{**os.environ, ...}`経由でそのまま継承する（6.19節）——Bはこの経路を通じて初めてmain.pyへ環境変数を伝える、A・F1とは異なる間接的な経路だが、`ExactEnv`により実質的にA・F1と同水準の閉じた集合となる。`EXECUTION_HISTORY_DIR`・`RETRY_LINEAGE_DIR`はこの閉じた集合に含めないため、置換された時点で構造的に未設定となる（6.26節のauthority containmentを、overlayより強い置換で満たす）。
- **C・D・F2（既存worker契約）**：Scenario Cは10.5節（単一専用worker process方式）、Scenario Dは11.1節（Two-Way Blocking Handshake worker）、Scenario F2は13.2節（lock所有権付与ハーネス）が、それぞれ独立したworker起動時envの完全契約を持つ。本節はこれらを変更しない。

この整理により、7.5.4節（本節）は「A・F1のclosed allowlist方式とBの`ExactEnv`方式の使い分け」を扱う節として再定義され、C・D・F2固有の契約はそれぞれの節（10.5・11.1・13.2）が権威を持つ、という章構成が確定する。

### 7.5.5 Local Stub HTTPサーバーの要件（Round 3でOI-7を完全仕様化、Round 4でOI-7をResolvedへ格上げ）

- `127.0.0.1`の動的ポートへ明示bind、`serve_forever()`開始後にのみreadiness公開、`NO_PROXY=127.0.0.1,localhost`設定、`finally`での確実な`shutdown()`/`server_close()`（Round 1版から維持）。
- **WordPress**：`/wp-json/wp/v2/posts`への正確なpath/auth/draft payload検証、`WordPressOutput`が消費するJSONフィールド（`id`・`slug`・`status`・`title`・`link`等）を返す。**（Post-Round 10 Amendment、Codex delta review Major#5対応で明文化）** 「auth/draft payload検証」とは、POST受理・200/201応答の**前**に、以下をfail-closedに検証することを指す（従来の実装はリクエストを記録するのみで、実際の検証を行っていなかった）：①`Authorization`ヘッダがシナリオ設定済みのBasic認証値と一致すること（不一致ならHTTP 401を返す）。②`WordPressOutput.save()`が送るpayload（`src/outputs/wordpress_output.py:145-151`で直接確認済み：`title`・`content`・`status`・`excerpt`・`slug`の5キー、`excerpt`以外は非空）が全て存在すること（欠落・空ならHTTP 400を返す）。③`status`フィールドがシナリオが期待する固定値（既定`"draft"`）と一致すること（不一致ならHTTP 400を返す）。これらの検証に失敗した場合、Local Stubは設定済みの成功レスポンスを返さず、拒否理由を記録する（テストハーネスが`wordpress_rejections()`等で参照できる）。**（Post-Codex Full Independent Review Amendment、Minor#1対応）** ①のBasic認証検証について、シナリオが期待認証情報を一度も設定していない（未設定の）場合、当初の実装は検証自体をskipするfail-open挙動になっていた。これをfail-closedへ訂正する——期待認証情報が未設定であること自体を拒否理由とし、WordPress成功経路を使う全てのシナリオは`set_wordpress_expected_auth()`相当のAPIを明示的に呼ぶ契約とする。
- **RSS**：7.5.1a節のP1が有効化された場合、16の個別パスそれぞれに固定のRSS XML fixtureを返す。**（Round 9追加）** Scenario C（10.2節）は、この「固定fixture」に加え、Local Stubが各パスごとにリクエスト回数を数え、回数に応じて異なる（が決定的な）レスポンスを返す機能を必要とする——1回目のリクエスト（canonical execution由来）には空の`<channel>`（0件）、2回目のリクエスト（retry execution由来）には特定の1パスのみ1件のNewsItemを含むXMLを返す、という単純なcounter-basedのレスポンス切り替えであり、Local Stub自身が保持する状態（test-owned、production非依存）のみで実現できる。**（Post-Round 10 Amendment#2、Codex delta review#2 Minor#3で訂正）** 「シナリオA・Bは従来どおり固定fixtureのみを使用し、この機能を必要としない」という記述は誤りだった。実際には**Scenario Aのみ**固定fixtureを使用する（正常系1回のみの実行のため、counter-basedの切り替えが不要）。**Scenario Bは、Scenario Cのcanonical/retry 2段階fixtureをそのまま転用する**（9.1節・9.2節で明示：canonical executionは全16パス0件、retry executionは1パスのみ1件という同一のcounter-basedレスポンス切り替えを必要とする——Bのfailure injection手法自体がCのfixtureの転用であるため）。この機能を必要としないのはScenario Aのみである。
- **Anthropic（Round 4でOI-7をResolved化）**：main.pyの実際の呼び出し箇所を直接確認した結果：
  - `src/importance_judge.py:56-60`：`client.messages.create(model=JUDGE_MODEL, max_tokens=256, messages=[{"role": "user", "content": prompt}])`（非streaming）。レスポンスは`message.content[0].text`としてアクセスされ（`:61`）、テキストの中に`_extract_json()`が解釈できるJSON（`{"importance": "S"|"A"|"B"|"なし", "reason": str}`形状）を含む必要がある。
  - **（Round 4で直接再確認、OI-7解決）** `src/article_generator.py:48,53`・`src/seo_title_generator.py:40,45`・`src/x_post_generator.py:53,58`のいずれも`message = client.messages.create(...)`→`message.content[0].text.strip()`という、`importance_judge.py`と完全に同型の非streaming呼び出しパターンであることを、grepによる該当行の直接確認で裏付けた。Round 3までの「推定に留める」扱いを撤回する。
  - stubの成功応答は、インストール済みAnthropic SDKの`Message`モデル（`id`・`type`・`role`・`model`・`content`（textブロックを含むリスト）・`stop_reason`等・`usage`のtoken数フィールド）を満たす必要がある。
  - **fallback握りつぶしの検出可能性**：`importance_judge.py:73-75`で確認した通り、`client.messages.create()`が例外を送出した場合、または応答が期待形状でない場合、アプリ側は広範な`except Exception`で捕捉し、`print(f"  [警告] 重要度判定エラー...")`（`:74`）→`{"importance": "B", "reason": "判定エラーのためデフォルトBを適用"}`という**サイレントなfallback**を返す。ここでいう「ログ」とは、fallback文字列がPythonの`print()`により**main.py実subprocess自身のstdout**（`src/importance_judge.py:74`）へ出力されることを指す——**Anthropicへ送信するHTTPリクエストのbodyには一切現れない**。main.py実subprocessのstdoutは`NewsPipelineRunner._save_log()`（`src/pipeline/news_pipeline_runner.py:54,205-213`）が`<working_directory>/logs/news_agent/<run_timestamp>_stdout.log`として保存し、`PipelineResult.stdout_log_path`として公開する——テストハーネスはこのファイル（または`working_directory`配下の`logs/news_agent/*_stdout.log`を走査した結果）を読み、fallback文字列の不在を確認する。

    **（Post-Round 10 Amendment#2、Codex delta review#2 Minor#2で訂正）** 「シナリオA〜CのDurable/Observable Assertionsには、fallback発動の不在とstubへの実際のリクエスト回数の確認を**同じ強度で**含める」という趣旨の記述は不正確だった。実際に各シナリオが要求するassertionの強度はシナリオごとに異なり、8.2節・9.1節が個別に確定した契約が権威を持つ：
    - **Scenario A**（8.1節Assertion⑤）：Anthropic Local Stubへの実リクエストが**最低1回**発生することのみを確認する（重要度判定の実行証跡）。fallback文字列の不在・厳密なリクエスト回数の確認は**含まない**——8.2節が「A/B間の検証厳密度の意図的な不揃い」として明示的に記録している判断であり、Bと同水準の厳密さを要求しない。
    - **Scenario B**（9.1節Assertion⑦）：Anthropicがちょうど4回呼ばれること（重要度判定・記事生成・SEOタイトル・X投稿文）、かつfallback文字列がstdout logに一切出現しないことの**両方**を厳密に確認する。本項が説明する観測source（main.py実subprocessのstdout log）は、この9.1節Assertion⑦のために規定するものである。
    - **Scenario C**：fallback発動の不在・Anthropicリクエスト回数のいずれも、10.2節のDurable/Observable Assertionsには含まれない——Scenario Cの検証対象はWordPress write-ahead状態・crash injection証跡・disposition確定であり、Anthropic呼び出し自体の観測は本Releaseのスコープに含めない。
  - **SDKリトライ挙動**：インストール済みAnthropic SDKは既定で接続/timeout失敗、およびHTTP 408/409/429/5xxをbackoff付きで最大2回リトライする。stubは常に有効な200レスポンスを返す設計とし、リトライ経路の検証は本Releaseのスコープに含めない。

---

## 8. シナリオA — normal success → WordPress Draft（Round 1版から維持、Disposable Project Copy命名のみ訂正。Post-Round 10 Amendmentで正式契約本文を追加）

（8章はRound 1版以来、「Round 1版から維持」という参照のみが記載され、契約本文自体は本書に再掲されていなかった。P1・Scenario A〜Fのtest実装フェーズにおいて、この空白のまま実装へ進むことができないことが判明したため、7章（シナリオContract共通フォーマット）・7.5節（Controlled Upstream Boundary）・6.19/6.20節（main.py実subprocess起動・WordPress write-ahead順序）から導出し、実装により実際に検証した契約を、以下Post-Round 10 Amendmentとして正式本文に確定する。**8章本文はこのAmendmentで初めて具体的に書き起こされたものであり、執筆当初はCodex独立レビューを経ていなかったが、その後Codex delta review #1（30.6節）を含む後続レビューで確認された**（30章参照）。)

### 8.1 シナリオContract（Post-Round 10 Amendment、正式本文）

- **Precondition**：Disposable Project Copy構築済み（7.5.3節exact whitelist）。Local Stub起動済み（7.5.5節）：`NEWS_RSS_FEED_URLS_OVERRIDE`（P1、7.5.1a節）経由で、16個の個別RSSパスのうち1パスに`filter_news()`（`src/keyword_filter.py`のPRIORITY_KEYWORDS）を実際に通過する記事1件、残り15パスは0件のfixtureを配置する。WordPress Local Stub（`/wp-json/wp/v2/posts`）は、7.5.5節が定めるfail-closed検証（Basic認証一致・必須payload存在・`status`固定値一致）を通過した場合のみ200/201を返す設定。Anthropic Local Stub（`/v1/messages`）はimportance判定プロンプトに対し記事化対象のimportance（例：`"A"`）を、それ以外のプロンプト（記事生成・SEOタイトル・X投稿文）に対し非空のtextを返す設定。**専用worker subprocessは使わない**（7.5.4節、Scenario AはA・F1のclosed allowlist subprocess env方式に分類される）。worker/test env契約（allowlist）：`SystemRoot`・`PATH`・`APPDATA`（**scenario-owned empty directory、host実値ではない**、10.5節(a)）・`NO_PROXY=127.0.0.1,localhost`・`WP_SITE_URL`・`ANTHROPIC_BASE_URL`・`NEWS_RSS_FEED_URLS_OVERRIDE`・`ANTHROPIC_API_KEY`/`WP_USERNAME`/`WP_APP_PASSWORD`（test-only dummy値）・`PYTHON_DOTENV_DISABLED`・`PYTHONDONTWRITEBYTECODE`・`PYTHONIOENCODING=utf-8`（10.5節(a)後段）。`RETRY_LINEAGE_*`等のprotected execution envelope用環境変数は一切設定しない——main.pyはこれを検出せず`LegacyDirectExecutionContext`を自己生成する（`side_effect_safety`パッケージ、6.19節関連）。
- **Runtime Path**：`subprocess.run([venv_python, <copy>/main.py], cwd=<copy root>, env=<上記allowlist>)`を単発で起動する。main.pyの唯一のCLI経路（RSS収集→キーワードフィルター→重複排除→重要度判定→記事生成→WordPress POST、main.py:399-782）を1回通す。
- **Failure Injection**：なし（正常系）。
- **Durable/Observable Assertions**：①main.pyのexit codeが`0`（全件成功、main.py:767）。②記事を含む1ソースについて、Local Stubへの実際のfetchが発生する（request_count≥1）。③空の15ソースについても、override経由で全16フィードが走査されたことの証拠として、それぞれ最低1回のfetchが発生する。④WordPress Local Stubが受信するPOSTがちょうど1回であり、Basic認証ヘッダを伴い、bodyの`status`が`draft`固定であること、かつ7.5.5節のfail-closed検証で拒否された事例が無いこと。⑤Anthropic Local Stubへ最低1回のリクエストが発生すること（重要度判定の実行証跡）。⑥Zero-Diff証拠契約（7.5.3節）：Original Project側がシナリオ実行前後で完全に無変更であること。⑦Disposable Project Copyがteardown後に削除されていること。
- **Prohibited Outcome**：main.pyのexit codeが`0`以外になること。WordPress Local StubへのPOSTが0回または2回以上になること。Local Stub以外の宛先（Controlled Upstream Boundaryの外側）への通信が発生すること。Original Projectへの差分が生じること。
- **Isolation/Cleanup**：Disposable Project Copyの既定削除（7.5.3節、`DISPOSABLE_COPY_KEEP=1`のみが保持のopt-in）。Local Stubの`stop()`（`shutdown()`/`server_close()`を`finally`で確実に実行）。Zero-Diff manifest（before/after）比較。

### 8.2 8.1がArchitectureから直接導出できる部分と、新規設計判断の部分（Post-Round 10 Amendment、透明性のための記録）

- **Architectureから直接導出できる部分**：Precondition・Runtime Pathの大半（env変数名・write-ahead順序・専用worker不要の分類）は、7.5.1/7.5.1a/7.5.2/7.5.4/7.5.5節・6.19/6.20節が確定済みの事実からそのまま導出される。
- **新規設計判断（8.1で初めて具体化した部分）**：①fixture本文（記事タイトル・キーワード選定）の具体的な文言——10.2節がScenario Cについて「実装フェーズで確定する」と明言しているのと同種の、test側の裁量事項。②Anthropicリクエスト回数assertionを「最低1回」という緩い条件にとどめたこと——9章が明記するB向けの「fallback非発動・リクエスト回数の完全一致」assertionをAへそのまま類推適用しなかった（9.2節参照、A/B間の検証厳密度の意図的な不揃いとして記録する）。

---

## 9. シナリオB — retryable failure → enqueue → actual retry → observability（Round 1版から維持、7.5.5節のfallback非発動assertionを追加。Post-Round 10 Amendmentで正式契約本文を追加）

（9章もRound 1版以来、「Round 1版から維持」という参照とfallback非発動assertionの追加のみが記載され、契約本文自体は本書に再掲されていなかった。8章と同じ経緯（P1・Scenario A〜Fのtest実装フェーズでの空白発覚）により、以下Post-Round 10 Amendmentとして正式本文を確定する。**9章本文もこのAmendmentで初めて具体的に書き起こされたものであり、執筆当初はCodex独立レビューを経ていなかったが、その後Codex delta review #1（30.6節）を含む後続レビューで確認された**（30章参照）。)

### 9.1 シナリオContract（Post-Round 10 Amendment、正式本文）

- **Precondition**：Disposable Project Copy・Local StubはScenario Aと同様に構成する（WordPress Local Stubのfail-closed検証を含む、7.5.5節）。加えて、Retry Runtime二重・三重ゲート（`AI_AGENT_ENABLED`・`WORKFLOW_ENGINE_ENABLED`・`RETRY_ENGINE_ENABLED`・`RETRY_LINEAGE_ENABLED`、いずれも`true`）・`NEWS_AGENT_MIN_INTERVAL_MINUTES=0`・`SystemRoot`/`PATH`/`APPDATA`（scenario-owned empty directory、10.5節(a)）・`NO_PROXY`・`WP_SITE_URL`/`ANTHROPIC_BASE_URL`/`NEWS_RSS_FEED_URLS_OVERRIDE`・test-only dummy credentials・`PYTHON_DOTENV_DISABLED`/`PYTHONDONTWRITEBYTECODE`/`PYTHONIOENCODING=utf-8`を、**テストハーネス自身の`os.environ`へ`ExactEnv`方式（7.5.4節、Post-Round 10 Amendmentで`ScopedEnv`から変更）で完全に置換する**（Scenario Bは専用worker subprocessを持たない、6.16a節：`RetryQueueManager`/`RetryHistoryManager`がプロセスローカルのin-memory実装であるため、canonical execution→enqueue→actual retryを単一プロセス内で完結させる必要があり、かつcrash seam等のprocess分離を必要としないため、テストドライバ自身のプロセス内での直接構築が成立する）。`ExactEnv`は`os.environ`をこの閉じた集合へ完全に置換する（overlayではない）ため、host由来のPYTHONPATH・絶対path override等は構造的に持ち込まれず、`EXECUTION_HISTORY_DIR`・`RETRY_LINEAGE_DIR`も置換された時点で未設定となる（6.26節のauthority containmentを、overlayより強い置換で満たす、Codex delta review Major#1解決）。RSS Local Stubは2段階fixtureを持つ：1回目のリクエストは全16パスとも0件、2回目のリクエストは1パスのみ1件（10.2節Step1/Step2のcanonical/retry fixtureをそのまま転用する、9.2節参照）。
- **Runtime Path**：①テストドライバ自身のプロセス内で`AgentConfig.from_env(base_dir=<copy root>)`・`WorkflowEngineConfig.from_env(project_root=<copy root>)`から`WorkflowEngineManager.from_config()`を直接構築し、canonical execution（1回目のRSS取得、空のため`collect_all_news()`が空リストを返し、main.pyが`return 1`——`NEWS_OUTCOME_GENERIC_FAILURE_EXIT_1`、WordPress/Anthropicへ到達する遥か手前で失敗する、main.py:484-487）を実行する。②同一プロセス内で`RetryCompositionRoot.from_env(base_dir=<copy root>)`（6.25/6.26節）→`RetryRuntimeOrchestrator.from_composition_root()`→`run_once(dry_run=False)`を1回呼び出す。これが内部で`reconcile_all()`（no-op）→`enqueue_pending_failures()`（canonical executionのFAILED run_idを検知しenqueue）→`scheduler.run_due()`→`execute_dispatchable_retries()`（実`RetryManager.retry()`→実`RetryExecutor.execute()`→実`WorkflowEngineManager.run()`→NEWS step→2回目のmain.py実subprocess、RSSに記事1件あり→WordPress POST成功→`record_confirmed()`まで正常到達）を同期的に駆動する。crash seam（Scenario C、10章）は一切使わない。
- **Failure Injection**：Scenario Cのcanonical execution fixture（10.2節：空RSS 2段階レスポンス）をそのまま転用する（9.2節「新規設計判断」参照）。
- **Durable/Observable Assertions**：①Step1（canonical execution）完了時点で、Anthropic・WordPress Local Stubへのリクエストがいずれも0回であること（空RSSでWordPress到達前に失敗する構造的証明、main.py:476-487）。②`cycle_result.trigger_result.enqueued == 1`。③`len(cycle_result.scheduler_events) == 1`。④`len(cycle_result.execution_results) == 1`。⑤`retry_result.outcome == RetryOutcome.RETRIED`であり、かつretry executionの`WorkflowEngineResult.overall_success == True`であること。⑥WordPress Local Stubがretry実行でちょうど1回のPOSTを受信すること（fail-closed検証で拒否された事例が無いことを含む、7.5.5節）。⑦**（7.5.5節OI-7対応、fallback非発動assertion。Post-Round 10 Amendment、Codex delta review Major#2で観測sourceを訂正）** Anthropic Local Stubがretry実行でちょうど4回呼ばれること（重要度判定・記事生成・SEOタイトル・X投稿文の4呼び出し）、かつfallback発動を示す警告文字列（「判定エラーのためデフォルトBを適用」、`src/importance_judge.py:75`。同ファイル`:74`が`print()`する）が、**main.py実subprocessのstdout log**（`NewsPipelineRunner._save_log()`が保存する`<copy root>/logs/news_agent/*_stdout.log`、`src/pipeline/news_pipeline_runner.py:54,205-213`）に一切出現しないこと——Anthropicへ送信するHTTPリクエストのbodyではない（当初、検証source を誤っていたことをCodex delta reviewが指摘した）。⑧retry成功後、**automatic retry suppressionの確認**として2回目の`reconcile_all()`を明示的に呼び出し、`skipped=False`かつ`opened_count=0`であること（誤った追加retryが開かれないことの確認、10.2節Step3と同型）。
- **Prohibited Outcome**：`terminal_disposition == HUMAN_REVIEW_REQUIRED`になること（Scenario Cの結果との混同を意味する）。**（Post-Codex Full Independent Review Amendment、Major#2対応）** この項目は、`composition_root.lineage.find_existing_lineage(canonical_result.run_id)`が返すlineageレコードの`terminal_disposition`を直接読み取り、`RetryLineageDisposition.SUCCEEDED`と一致すること（＝`HUMAN_REVIEW_REQUIRED`ではないこと）を明示的にassertする。2回目の`reconcile_all()`の`opened_count==0`だけを代替証拠にしない——`HUMAN_REVIEW_REQUIRED`はreopenを抑制する性質を持つため、`opened_count==0`は`HUMAN_REVIEW_REQUIRED`の場合にも成立してしまい、それ単体ではScenario Cの結果との混同を検出できないことをCodex Full Independent Reviewが指摘した。WordPress POST回数が1以外になること。`enqueued`・`scheduler_events`・`execution_results`のいずれかが1以外になること。fallback警告文字列がstdout logに出現すること。2回目の`reconcile_all()`が`opened_count≥1`を返すこと（誤った追加retryの発生）。Local Stub以外の宛先への通信が発生すること。
- **Isolation/Cleanup**：Scenario Aと同様（Disposable Project Copy既定削除・Local Stub `stop()`・Zero-Diff比較・scenario-owned APPDATAディレクトリの削除）。加えて、`ExactEnv`（7.5.4節）による`os.environ`の確実な復元を、シナリオ完了後（正常終了・例外いずれの経路でも）`try`/`finally`で保証する。

### 9.2 9.1がArchitectureから直接導出できる部分と、新規設計判断の部分（Post-Round 10 Amendment、透明性のための記録）

- **Architectureから直接導出できる部分**：単一プロセス完結の必然性（6.16a節）・`RetryCompositionRoot`のbase_dir結合（6.25/6.26節）・fallback非発動とリクエスト回数一致のassertion（7.5.5節OI-7、9章既存追加分）は、いずれもArchitectureが既に確定済みの事実からそのまま導出される。
- **新規設計判断（9.1で初めて具体化した部分）**：①**失敗注入手法としてScenario Cの空RSS fixtureを転用する判断**——WordPress層での失敗（POST失敗）は意図的に不採用とした。理由：protected contextでのWordPress POST失敗はdraft state=`ATTEMPTED`のまま`SideEffectSafetyCategory.IN_PROGRESS_OR_UNKNOWN`に分類され、`resolve_final_disposition()`により無条件で`HUMAN_REVIEW_REQUIRED`となる（6.20節）。これはScenario Cの結果であり、Scenario Bの題意（「クリーンなactual retry」）と構造的に矛盾するため、WordPress層以前（RSS収集段階）での失敗を選んだ。②2回目の`reconcile_all()`によるautomatic retry suppressionの確認（Assertion⑧）——10.2節Step3の構成をBへ類推適用したものであり、9章の従前記述には明記されていなかった。③Anthropicリクエスト回数を「ちょうど4回」と厳密に固定したこと（main.pyの4つのLLM呼び出し箇所——重要度判定・記事生成・SEOタイトル・X投稿文——に基づく、production側の既知の呼び出し構成からの導出）。

---

## 10. シナリオC — partial/side-effect済み failure → Human Review → automatic retryなし（Round 6で単一worker化、Round 7でenv allowlist完全化・attempt呼称統一、Round 8でworker import契約・NO_PROXY・assertion拡充、Round 9でcanonical failure fixture自己完結化・interval gate無効化）

### 10.1 Round 5 B1/B2が指摘した問題と、Round 6の判断過程

Round 4は、Scenario CをTier 1/Tier 2の2層構成から、test-owned`sitecustomize.py`によるproduction seamレスのcrash injection（6.24節）へ全面的に置き換えた。Round 5は、crash発火の証拠をtest-owned durable marker fileへ置き換え（B1解決）、`RetryCompositionRoot.from_env(base_dir=...)`によるstate結合を明示的に規定した（B2解決）が、この統合実行を「テストハーネスが2つの独立したtest-only worker subprocessを順に起動する」という**2-worker/Phase handoff構成**（Worker Phase 1：canonical run＋enqueue、Worker Phase 2：crash-injected retry）として実現した。Round 5レビューは、この2-worker構成自体に新たな2件のBlockingを指摘した：

- **B1（queue/historyの断絶）**：Worker Phase 1が`RetryCompositionRoot.from_env(base_dir=...)`で構築する`queue`（`RetryQueueManager`）・`history`（`RetryHistoryManager`）は、いずれもプロセスローカルのin-memory dict実装であり（6.16a節で新規確認）、永続化storeを一切持たない。Worker Phase 2は別プロセスとして新規に`RetryCompositionRoot.from_env()`を呼ぶため、そのqueue/historyインスタンスはWorker Phase 1のenqueue結果を一切引き継げない——「Worker Phase 1が書き込んだdurable state（queue・lineage等）を、ディスク上の同一ファイルから正しく読み込む」というRound 5版10.2節の記述は、lineageについては正しい（disk-backed）が、queueについては誤り（in-memoryはdiskに書かれない）だった。
- **B2（authority containmentの欠落）**：`RetryCompositionRoot.from_env(base_dir=...)`が内部で構築する`ExecutionHistoryConfig.from_env(project_root=...)`・`RetryLineageConfig.from_env(project_root=...)`は、それぞれ`EXECUTION_HISTORY_DIR`・`RETRY_LINEAGE_DIR`環境変数をhostから継承しうるが、`project_root / dir_name`という`pathlib`の`/`演算は`dir_name`が絶対パスの場合`project_root`を無条件に破棄する（6.26節で新規確認）。Round 5版はWorker Phase 1/2起動時のenv構築を「`os.environ`のコピーをベースに」とのみ記述しており、この2変数を明示的に除去する契約を欠いていた。

**Round 6の判断（指示1.への回答）**：6.16a節で確認した事実——`RetryManager.retry()`自体はqueue/historyに一切依存せず（disk-backed lineage/monitorのみで機能する）、production自身の唯一の正規経路である`RetryRuntimeOrchestrator.run_once()`も「enqueue→dispatch→execute」を単一プロセス内で完結させる設計である——に基づき、**2-worker/Phase handoff構成を撤回し、単一の専用test worker process内でcanonical execution→enqueue→actual retry（RetryExecutor経由）を連続実行し、in-memory `RetryQueue`/`RetryHistory`をプロセス境界を越えずにそのまま保持する方式へ置き換える**。この方式は実コード上成立する（新設のdurable queue等は不要）。Scenario Cの根幹設計（test-owned`sitecustomize.py`、production seamレス、タイミング非依存の決定的crash injection）はRound 4・Round 5から変更しない。

### 10.2 統合設計：単一worker内でのAuthoritative Write-Ahead Crash Injection（B1/B2解決）

**用語定義（Round 6で新規追加、M2解決）**：Round 6 Codexレビューは、Round 6改訂前の本節が「attempt 1」「attempt 2」という呼称を、main.py実subprocessの**物理的な起動回数**（1回目・2回目）を指す意味で使っており、これが`RetryLineageRecord`の**authoritative `attempt_ordinal`**（`claim.attempt_no`・`identity.attempt_ordinal`・manifestキー等に実際に使われる値）と食い違うと指摘した（M2）。実際に`src/retry_lineage/retry_lineage_manager.py`の`create_new_lineage()`（`:294-303`）を確認すると、lineage作成時点で`initial_scope = RetryAttemptExecutionScope(attempt_no=1, ...)`・`next_attempt_ordinal=1`が設定され、この後`claim()`が返す`claim.attempt_no`もこの`1`のままである（`retry_lineage_manager.py`の`claim()`は`attempt_scopes[-1].attempt_no`をそのまま返す）。`RetryExecutor.execute()`（`retry_executor.py:207`）は`attempt_ordinal=claim.attempt_no`をそのまま`RetryLineageProtectedProvenance`へ渡すため、**crash-injected retryのauthoritative `attempt_ordinal`は常に`1`である**（lineageが作成されて以降ただ1回だけ行われる retry であるため）。本節では以降、以下の2つの語を明確に区別して使う：
- **canonical execution**：Step 1で実行する、lineage作成前のmain.py実subprocessの1回目の物理実行（root_run_id自体を生成する、retry lineageの外側の実行）。
- **retry execution**：Step 2で`RetryExecutor`が駆動する、main.py実subprocessの2回目の物理実行。lineage内では最初の（かつ唯一の）retryであり、**authoritative `attempt_ordinal`（`claim.attempt_no`・`identity.attempt_ordinal`・manifestキー）は`1`**である（「2回目の物理実行」という事実と「lineage内のattempt_ordinal＝1」という事実は別軸であり、両者を混同しない）。

**実行アーキテクチャ（Round 6で確定）**：Scenario Cは、テストハーネス（pytest等）が**単一の専用test worker subprocessを1回だけ**起動し、そのプロセス内でcanonical execution・enqueue・retry execution（crash-injected）を順に連続実行する。テストハーネス自身の`os.environ`は一切変更しない。worker自身は`subprocess.run([sys.executable, worker_script, ...], env=<明示的に構築・sanitizeされたdict>, ...)`で起動する（authority containment、10.5節で詳述）。workerは単一プロセス・単一スレッドで、以下の3ステップを**同一プロセス内・同一オブジェクトグラフ上で**順に実行する：

- **Step 1（canonical execution、crash seamなし。Round 9でScenario C自己完結のfixtureへ確定、Round 8 Major 2解決）**：Round 8までは、canonical executionの失敗注入を「シナリオB（9章）が確立済みの手順」に委ねていたが、9章は「Round 1版から維持、変更なし」という要約に留まり、実際の失敗注入手順・レスポンス系列・イベントメタデータのいずれも本書には記載されていないことをRound 8 Codexレビューが指摘した（Major 2）。Round 9は、Scenario B（9章）への依存を撤回し、**Scenario C自身が完結するfixtureを直接規定する**：
  - workerは`agent_config = AgentConfig.from_env(base_dir=<Disposable Project Copy root>)`・`workflow_engine_config = WorkflowEngineConfig.from_env(project_root=<同root>)`を構築し、`WorkflowEngineManager.from_config(agent_config, workflow_engine_config)`（`scripts/run_workflow_engine.py`と同型の構築）で**canonical run専用の独立インスタンス**を構築する。
  - **failure injection（Round 9で確定、Round 10でexit code token名称を訂正）**：Local Stub上の16個のRSS個別パスは、いずれも自身への**1回目**のリクエストに対し、0件のNewsItemを含む空の`<channel>`（正常なRSS XML構造だが`<item>`要素を1つも含まない）を返す。main.pyの`collect_all_news(max_items_per_feed=20)`（`src/collector.py:132-149`）は16フィード全ての結果を集約するため、この時点で`all_news`は空リストになる。main.py（`:485-487`、6.19節・7.5.1a節既出）は`if not all_news: print(...); return 1`という既存の制御フローにより、**WordPress POSTへ到達する遥か手前のRSS収集段階**で`returncode=1`を返して終了する。`returncode=1`は`_EXIT_CODE_TOKENS`（`src/pipeline/news_pipeline_runner.py:64`）が明示的にマッピングする既知tokenであり、対応する名称は**`NEWS_OUTCOME_GENERIC_FAILURE_EXIT_1`**である（`NEWS_OUTCOME_ABNORMAL_EXIT`は、`_EXIT_CODE_TOKENS`に含まれない未知のreturncode——signalによる異常終了等——に対するfallback名称であり、`returncode=1`には該当しない、`news_pipeline_runner.py:73-75`で直接確認済み）。これは`NewsPipelineRunner`により例外を送出しない`success=False`の`PipelineResult`（`NEWS_OUTCOME_GENERIC_FAILURE_EXIT_1`相当）へ変換され、Execution History/Workflow Monitorへ`WorkflowMonitorStatus.FAILED`として記録される（`_RETRY_TARGET_STATUSES`に含まれるステータス、`retry_enqueue_trigger.py:99`既出）——後続のenqueue判定（Step 2）が着目する対象と一致する。
  - この時点でcrash seam用4変数はworker自身の`os.environ`に一切設定されていないため、main.py実subprocess（canonical execution用）はcrash seamを一切認識しない。この結果は`ExecutionHistoryConfig.from_env(project_root=<同root>)`が指すdisk上のExecution History/Workflow Monitor storeへ記録される（`WorkflowEngineManager.from_config()`が内部でこの同じConfigを使って構築するため、後続のcomposition rootと同一ディスク領域を共有する）。
  - **NewsAgent interval gateの無効化（Round 9新規、Round 10で根拠を訂正）**：`NewsAgent.decide()`（`src/ai/news_agent.py:42-77`）は、`logs/execution/`配下の直近実行ログの`finished_at`と`min_interval_minutes`（`NewsAgentConfig`、既定`180`分、`src/ai/news_agent_config.py:43`）を比較し、間隔が経過していなければ`should_act=False`を返す。`AgentExecutor.execute()`（`src/ai/agent_executor.py:59-67`）は`should_act=False`の場合`act()`を一切呼ばず、`action_taken=False, success=True`という**成功扱いのno-op**として`AgentResult`を組み立てる。**（Round 10訂正）** canonical execution（Step 1、空RSS）はmain.pyの`return 1`（`:487`）で即座に終了するため、実行ログ書き込み（`log_manager.log_execution(...)`、`main.py:725`）に到達する遥か手前で処理が終わっており、Step 1自身はexecution logを一切書き込まない（Round 9版の「Step 1が書き込む実行ログにより...」という記述は誤りだったため撤回する）。したがって、Disposable Project Copyが常に新規（`logs/execution/`が空の状態から開始する、7.5.3節）である限り、Step 2のNEWS step実行時点でも`_find_latest_execution()`は実行ログを発見できず、`decide()`は`latest_finished_at is None`の分岐（「実行履歴が見つからないため初回実行と判断」、`news_agent.py:55-58`）を通り`should_act=True`を返す——この経路だけでもretry executionのNEWS step実行は妨げられない。それでも、worker起動時envへ**`NEWS_AGENT_MIN_INTERVAL_MINUTES=0`を追加する**（10.5節（b')として新設）——これは、canonical execution以外の経路（他ステップの実行ログ・将来のfixture変更・Disposable Copy構築手順の変更等）によって`logs/execution/`配下に実行ログが存在してしまう場合に備えたdefense-in-depthであり、`decide()`の判定式`elapsed_minutes >= min_interval`（`news_agent.py:64`）を、既存ログの有無・経過時間の長さに関わらず常に真とすることで、interval gateがretry executionを妨げる可能性を構造的にゼロにする。この設定はStep 1の`WorkflowEngineManager`・Step 2の`composition_root.manager`が内部で構築するインスタンスの両方に同一のworker起動時envとして適用される（both呼び出しが同一プロセス内・同一`os.environ`を参照するため、追加の配線は不要）。
  - **retry execution向けfixture（Round 9新規、Codex suggestion「one-article fixture」に対応）**：Local Stub上の16個のRSS個別パスのうち、あらかじめ固定した1パス（例：`/rss/4gamer`）のみが自身への**2回目**のリクエストに対し、ちょうど1件のNewsItemを含むRSS XMLを返す（残り15パスは2回目のリクエストでも引き続き0件を返す）。このNewsItemのタイトル・本文は、既存の`filter_news()`（`main.py`、production側キーワードフィルタ、無改修）を実際に通過する内容として、実装フェーズでfixtureとして確定する（Architecture Phase自体は正確な文言を規定しない——キーワードフィルタのロジック自体を変更しないテスト側のfixture選定作業であり、production側の判断ロジックには一切触れない）。これにより、Step 2（下記）の`collect_all_news()`は正確に1件のNewsItemを返し、`filter_news()`通過後も1件のまま、importance判定（Anthropic stub、常に`"A"`等の記事化対象importanceを返すよう固定）・記事生成・WordPress POSTへと1件のみが進む——Assertion 9（enqueue/dispatch/executionがちょうど1件）が要求する「ちょうど1件」という前提と構造的に一致する。
- **Step 2（RetryCompositionRoot構築、enqueue、crash-injected actual retry）**：workerは`composition_root = RetryCompositionRoot.from_env(base_dir=<同じDisposable Project Copy root>)`（6.25節）を**この1回だけ**構築し、`orchestrator = RetryRuntimeOrchestrator.from_composition_root(composition_root)`（`retry_runtime_orchestrator.py:139-152`）を構築する。以降、`composition_root.queue`／`composition_root.history`／`composition_root.lineage`／`composition_root.manager`はいずれも同一インスタンスとして、enqueueとactual retryの両方から参照される（6.16a節）。
  - workerは、`orchestrator.run_once(dry_run=False)`を呼び出す**直前**に、自身の`os.environ`へcrash seam用4変数（`PYTHONPATH`・`WP_OUTPUT_CRASH_SEAM_ENABLED=1`・`WP_OUTPUT_CRASH_SEAM_SRC_DIR`・`WP_OUTPUT_CRASH_SEAM_EVIDENCE_PATH`、6.24節）を`try`ブロック内でscopedに設定する（10.5節で完全仕様化）。
  - `orchestrator.run_once()`（`retry_runtime_orchestrator.py:159-222`）は、単一の呼び出しの中で`self.lineage.reconcile_all(...)`（0.、この時点ではlineageが1件も存在しないためno-op）→`self.trigger.enqueue_pending_failures(max_attempts=self.policy.max_attempts, dry_run=False)`（1.、Step 1のFAILED monitor recordを検知し`composition_root.queue`へenqueueする——**同じqueueインスタンスへの書き込み**）→`self.scheduler.run_due(jobs=[])`（2.、`RetrySchedulerSource(queue)`経由で同じqueueの内容をSchedulerEventへ変換する——**同じqueueインスタンスからの読み取り**）→`self.manager.execute_dispatchable_retries(events, dry_run=False)`（3.、`retry_fn=self.retry`として実`RetryManager.retry()`を呼び出す）→Queue更新/Cleanup/History記録（4.、同じqueue/historyインスタンスへの書き込み）を実行する。
  - 3.の`retry()`呼び出しが実`RetryExecutor.execute()`→`WorkflowEngineManager.run()`（`composition_root.manager`内部が保持する、Step 1とは別のインスタンス）→NEWS step→`NewsPipelineRunner.run()`→`subprocess.run()`を同期的に駆動する。**このworker自身の`os.environ`（直前にscoped設定した4変数を含む）が、6.19節の継承経路でmain.py実subprocess（retry execution用）へそのまま伝わる。**
  - main.py実subprocess内では、通常どおりmanifest登録→`record_attempted()`→POST（Local Stubへ実際に到達、200/201で成功）→ステータスチェック通過→（本来ならここで`record_confirmed()`が呼ばれるはずが）**sitecustomizeによりpatchされた関数が呼ばれ、evidence markerを書き込み、原処理を一切実行せず`os._exit(91)`する**（6.24節）。
  - `subprocess.run()`は非ゼロreturncode（`91`）でその場から復帰し、`NewsPipelineRunner`は`NEWS_OUTCOME_ABNORMAL_EXIT`を含む`PipelineResult(success=False, ...)`を返す（例外は送出されない）。これはstep失敗として`WorkflowEngineResult`に記録されるのみで、`engine.run()`自体は例外を送出せず正常に戻る。
  - worker（main.pyの親）は、`RetryExecutor.execute()`内で6.20節の同期的disposition決定ロジック（`retry_executor.py:292-312`）へ進み、`HUMAN_REVIEW_REQUIRED`を`mark_terminal()`へ渡す。`orchestrator.run_once()`はこの一連の処理を終えた`RetryRuntimeCycleResult`（内部に`execution_results`としてこの`RetryExecutionResult`／`RetryResult`を含む）をworkerへ同期的に返す。
  - `run_once()`呼び出しが（正常終了・例外いずれの経路でも）完了した直後、`finally`ブロックでworkerは自身の`os.environ`からcrash seam用4変数を除去し、Step 2開始前の状態へ完全復元する（10.5節）。
- **Step 3（automatic retry suppressionの確認）**：env復元後（crash seam変数が一切残っていない状態で）、workerは`composition_root.lineage.reconcile_all(resolve_status_fn=composition_root.monitor.get_status)`を**明示的にもう1回**呼び出す。この時点で当該lineageは既に`phase=TERMINAL`・`terminal_disposition=HUMAN_REVIEW_REQUIRED`（Step 2内でRetryExecutorが確定済み）であるため、`_reconcile_all_locked()`の第1ループ（`phase==EXECUTION_STARTED`が対象）・第2ループ（`terminal_disposition in (FAILED, NOT_ACTIONED)`が対象）のいずれにも該当せず、`open_next_attempt()`は呼ばれない（12.1節）。

workerは、同一プロセス内で直接保持しているオブジェクト（Step 1のExecution History run_id、Step 2の`RetryRuntimeCycleResult`／`composition_root.lineage`、Step 3の`ReconcileSummary`）から、production APIの戻り値仕様に一切新規依存を追加せずに、以下をtest-owned worker result file（JSON、テストハーネスが指定するパス）へ書き出し、正常終了する（main.pyだけがcrashし、workerは`subprocess.run()`から正常に復帰するため——6.19節）：
`retry_result.workflow_engine_result.run_id`（authoritative member_run_id）、`retry_result.original_run_id`、`retry_result.outcome`（`RetryOutcome`、`retry_result.py:33-37`で確認済みの既存enum）、`retry_result.authoritative_attempt_no`（`retry_result.py:53`で確認済みの既存フィールド）、`composition_root.lineage.find_existing_lineage(retry_result.original_run_id)`の`root_run_id`・`terminal_disposition`・`latest_run_id`（`retry_lineage_manager.py:158`・`mark_execution_started()`が確定させる`latest_run_id`、同一プロセス内のPythonオブジェクトとして直接取得——シリアライズやIPCを介さない）、`cycle_result.trigger_result.enqueued`（`RetryEnqueueTriggerResult.enqueued`、`retry_enqueue_trigger.py:128-138`で確認済みの既存フィールド）、`len(cycle_result.scheduler_events)`、`len(cycle_result.execution_results)`（いずれも`RetryRuntimeCycleResult`、`retry_runtime_orchestrator.py`で確認済みの既存フィールドの長さ）、Step 3の`ReconcileSummary`の全フィールド（`skipped`・`reason`・`resolved_count`・`opened_count`・`released_count`）。

**Durable/Observable Assertions（テストハーネスが検証する内容。いずれもproduction APIの戻り値の新規拡張に依存しない、Round 6でM2・M3解決・Round 8でCodex suggestion反映のため強化）**：
1. **crash hook発火の証拠（B1解決、維持）**：`WP_OUTPUT_CRASH_SEAM_EVIDENCE_PATH`が指すmarker fileが存在し、その内容（`identity`一式・`member_run_id`・`wp_post_id`）が読み取れること。このファイルは、patchされた関数以外のいかなるコードパスからも生成されないため、「patchされた`record_confirmed()`へ実際に到達した」ことの直接証拠である。
2. **POST成功の独立確認（維持）**：WordPress Local Stub自身のリクエストログを見て、実POSTが**ちょうど1回**受信され、200/201で応答したことを確認する（6.24節の設計上、POST成功なしにcrash seamへ到達しえないため構造的に保証されるが、Local Stub側からも独立に確認する）。
3. **durable draft stateの直接確認（B2解決、自明化排除、維持）**：テストハーネス自身が、Disposable Project Copyの`state/wordpress_draft_state/`配下（main.py・worker・composition_rootいずれも同じパスを参照する、6.25節）を直接readし、当該identityのレコードが`ATTEMPTED`のまま（`CONFIRMED`に遷移していない）こと、`wp_post_id`が記録されていないことを確認する。
4. **marker/draft state/manifest/lineage/WorkflowEngineResultの5点相互照合（Round 6でM2解決、cross-field一致を必須化）**：以下の5つの値が**すべて同一のmember_run_id文字列**であることを確認する：(a) marker fileの`member_run_id`、(b) 3.のdraft stateレコードの`member_run_id`、(c) Disposable Copyの`state/protected_operation_manifest/`配下の、`(root_run_id, attempt_ordinal=1, member_run_id)`をキーとするmanifestレコード（**`attempt_ordinal`は前掲の用語定義どおり常に`1`**、OI-8対応、25.2節）、(d) worker result fileが報告する`retry_result.workflow_engine_result.run_id`、(e) worker result fileが報告するlineageの`latest_run_id`（`mark_execution_started()`がdurableに確定させた値、6.16a節・`retry_lineage_manager.py:490`）。あわせて、(c)のmanifestレコードのキーに含まれる`attempt_ordinal`自体が`1`であること（`0`や`2`など他の値になっていないこと）も独立に確認する（Round 6でM2解決、attempt_ordinalの権威値がlineage作成時に固定される事実——`retry_lineage_manager.py:298`の`initial_scope.attempt_no=1`——との一致確認）。**（Round 8で追加）**さらに、worker result fileが報告する`retry_result.authoritative_attempt_no`（`retry_result.py:53`の既存フィールド、`RetryExecutor.execute()`が`claim.attempt_no`をそのまま設定する、`retry_executor.py:265,329,343`）が`1`であることも直接確認する——(c)のmanifestキーの`attempt_ordinal`と、production APIが公開する`authoritative_attempt_no`という独立した2つの経路から同じ`1`が得られることを確認する。5つのmember_run_id、および2つの`attempt_ordinal`/`authoritative_attempt_no`のいずれか1つでも不一致であれば、実際にRetryExecutorが払い出した真のmember_run_id・attempt_ordinalに基づく判定ではなく、何らかの取り違え（例：「manifest欠如によるfail-closed HRR」`retry_executor.py:294-295`の無条件HRR分岐、または別attemptのレコードの誤参照）が疑われるものとしてテストを失敗させる。
5. **marker wp_post_idの期待値一致（Round 6新規、M2解決）**：markerファイルが報告する`wp_post_id`が、WordPress Local Stubが当該POSTに対し実際に応答したJSON中の`id`フィールド（テスト自身がfixtureとして事前に固定する、正のint値）と**完全一致**すること。これにより、marker fileが「どこかのPOSTの残骸」ではなく「この特定のPOSTに対応する`record_confirmed()`呼び出し引数」であることを、production APIの戻り値ではなくLocal Stub側の独立した観測点から確認する。
6. **disposition確認（維持）**：worker result fileが報告する`terminal_disposition`が`HUMAN_REVIEW_REQUIRED`であること。
7. **automatic retry suppressionの確認（Round 6でM3解決、Round 7で`reason`を追加し全field一致を完全化）**：Step 3の`ReconcileSummary`について、`opened_count == 0`だけでなく、**`skipped is False`であることを必須assertion対象に追加**する（`skipped=True`の場合、`RetryExecutionLock`が他の保持者にbusyであることを意味し、`resolved_count`/`opened_count`/`released_count`がいずれも0のまま返る既存contract、9.3節——これを`opened_count==0`のみで判定すると、lock busyによる「たまたまopened_count=0」を成功と誤判定するfalse successのリスクがある）。あわせて、`skipped=False, resolved_count=0, opened_count=0, released_count=0, reason is None`という`ReconcileSummary`の**全5フィールドを一意に**assertする（`reason`は`_reconcile_all_locked()`の成功時return文が`reason`引数を渡さず`ReconcileSummary`の既定値`None`（`retry_lineage_results.py:69`）に委ねるため、成功時は常に`None`であることを直接確認済み——`resolved_count`/`released_count`が`0`であるのは、このDisposable Copy内に他のlineageが存在しない単一シナリオ専有の前提下での期待値）。
8. **NEWS stepの失敗確認（維持）**：worker result fileまたはExecution Historyレコードから、retry execution（authoritative `attempt_ordinal=1`）のNEWS stepの結果が失敗（`NEWS_OUTCOME_ABNORMAL_EXIT`相当）であることを確認する。
9. **enqueue/dispatch/executionがちょうど1件であることの確認（Round 8新規、Codex suggestion反映）**：worker result fileが報告する`cycle_result.trigger_result.enqueued == 1`（`RetryEnqueueTriggerResult.enqueued`、`retry_enqueue_trigger.py:128-138`）、`len(cycle_result.scheduler_events) == 1`、`len(cycle_result.execution_results) == 1`（いずれも単一の`orchestrator.run_once()`呼び出しの結果、`retry_runtime_orchestrator.py:159-222`）を確認する。これにより、canonical executionの失敗が意図せず複数回enqueueされたり、複数のretryが誤って同時にdispatchされたりしていないことを、production APIが公開する既存フィールドから直接確認する。
10. **`RetryOutcome`と3経路のroot run ID一致の確認（Round 8新規、Codex suggestion反映）**：worker result fileが報告する`cycle_result.execution_results[0].retry_result.outcome`が`RetryOutcome.RETRIED`（`retry_result.py:33`、実際にWorkflowEngineManager.run()を呼び出し再実行したことを示す既存enum値）であることを確認する。あわせて、Step 1のExecution History run_id（canonical executionの実行結果として記録されたrun_id）・`retry_result.original_run_id`（`retry_executor.py:254,319,336`で`lineage.root_run_id`がそのまま設定されることを直接確認済み）・`composition_root.lineage.find_existing_lineage(...).root_run_id`の**3つが完全に同一の文字列**であることを確認する（`RetryExecutor`がcanonical executionのrun_idをlineageのroot_run_idとしてそのまま引き継いでいることの直接証明）。

**Precondition（自明化回避、維持）**：workerが構築するRetryExecutor（`composition_root.manager`経由）は、`manifest`/`side_effect_classifier`が実装として注入されていること（`RetryCompositionRoot.from_env()`は既定でこれらを実装として構築するため、追加の配線変更は不要——6.25節）。

**Prohibited Outcome（Round 6でB1/B2解決分を追加、Round 7で`reason`不一致・attempt_ordinal不一致・worker起動時env不備を追加、Round 8でimport解決失敗・enqueue/execution件数不一致・outcome/root ID不一致を追加）**：`WP_OUTPUT_CRASH_SEAM_EVIDENCE_PATH`のmarker fileが存在しないこと（crash seam未発火、または6.24節のimport解決検証失敗によるfail-closed停止を意味する）、WordPress stubへのPOSTが0回または2回以上発生すること、draft stateが`CONFIRMED`に遷移していること、Assertion 4の5値または2つの`attempt_ordinal`系フィールドのいずれかが不一致であること、manifestレコードの`attempt_ordinal`が`1`以外であること、marker wp_post_idがLocal Stub応答の`id`と不一致であること、`terminal_disposition`が`HUMAN_REVIEW_REQUIRED`以外になること、Step 3の`ReconcileSummary`が`skipped=True`または`opened_count`が1以上または`resolved_count`/`released_count`が`0`以外または`reason`が`None`以外になること、`cycle_result.trigger_result.enqueued`/`len(cycle_result.scheduler_events)`/`len(cycle_result.execution_results)`のいずれかが`1`以外になること、`retry_result.outcome`が`RetryOutcome.RETRIED`以外になること、Step 1のExecution History run_id・`retry_result.original_run_id`・lineageの`root_run_id`の3値が不一致であること、workerが参照するstate領域がmain.pyの参照するDisposable Copy rootと異なること、Step 1完了後もworkerの`os.environ`にcrash seam用4変数が（scoped設定前に）残存していること、Step 2完了後もworkerの`os.environ`にcrash seam用4変数が（`finally`復元後に）残存していること、worker起動時のenv（10.5節1.）に10.5節(b)〜(e)の必須Feature Gate・credentials・`NO_PROXY`のいずれかが欠落し`NullWorkflowEngineManager`/`NullRetryManager`/`claim()`失敗／Windows system proxy経由での通信のいずれかに帰着すること、worker自身の`src`-rooted importが`<Disposable Copy>/src`以外（original tree・installed package）から解決されること（10.5a節）。

### 10.3 タイミング特性（レースが存在しないことの明示）

本設計は、Scenario D（11章）やRound 1〜3までのScenario Cの各案とは異なり、**外部プロセスの状態を推測してタイミングよくkillする、という要素を一切含まない**。crash seam自体は、main.py実subprocessの内部で、`record_confirmed()`が実際に呼ばれる正確なその瞬間に、Pythonの通常のメソッド解決（class属性の参照）として発火する——これはOSレベルの外部killとは異なるカテゴリの決定性であり、**コードの制御フローそのものによる論理的な決定性**である（6.18節のpost_admission_hookが持つ決定性と同じ性質）。唯一の非決定性の余地は、`os._exit()`自体がOSレベルで即座にプロセスを終了させる標準保証（atexit・finally等をbypassする、Pythonの文書化された挙動）に依存する点のみであり、これはタイミングレースではなくPython言語仕様上の保証である。evidence marker（6.24節）自体も、書き込み→flush→fsync→closeが`os._exit()`より**前**に同期的に完了することを設計として規定しているため、marker fileの内容そのものにもrace窓は存在しない。単一worker化（10.2節）はこのタイミング特性に一切影響しない——crash seamの発火機構自体（sitecustomizeの`import`時点でのclass属性差し替え）は、workerがcanonical execution・enqueue・actual retryのどのステップを何回実行するかとは独立している。

### 10.4 Test-only Componentの位置づけ（scope-change Gate不要の理由）

本設計が新設するtest-only component（test-owned`sitecustomize.py`、それを指す`PYTHONPATH`・`WP_OUTPUT_CRASH_SEAM_ENABLED`・`WP_OUTPUT_CRASH_SEAM_SRC_DIR`・`WP_OUTPUT_CRASH_SEAM_EVIDENCE_PATH`の4 env var、単一worker用のtest-onlyエントリポイント、`RetryCompositionRoot.from_env(base_dir=...)`・`RetryRuntimeOrchestrator.from_composition_root(...)`・`WorkflowEngineManager.from_config(...)`という既存public API呼び出しの組み合わせ）は、いずれも：
- production source（`src/`・`scripts/`・`main.py`）を1バイトも変更しない。
- Python標準の起動機構（`sitecustomize`自動import）と、既存の`RetryCompositionRoot.from_env(base_dir=...)`という**既に存在する公開パラメータ**（新設ではない、6.25節）、既存の`RetryRuntimeOrchestrator.from_composition_root()`（production自身の正規経路、6.16a節）、およびworker自身のプロセス内`os.environ`へのscoped設定（新規のproduction依存追加を伴わない）のみで完結する。
- 既存のTier 2（Round 3以前）が既に採用していた「production classのメソッドをtest-scopeでmonkeypatchする」という技術カテゴリの延長であり、唯一の新規性は「同一プロセス内でのmock.patch.objectではなく、別プロセス（main.py実subprocess）自身の起動時にsitecustomize経由でpatchする」という適用範囲の拡張のみである。

**したがって、本設計は23章のProduction Implementation候補（Human Gate対象）には該当しない。新規Foundationでも、durable authority変更でも、既存contractの変更でもない（2章の境界内）。** production seamは不要である。T4（23.2章）は「Authoritative Write-Ahead Crash Injectionヘルパー（単一worker・sitecustomize＋evidence marker方式）」として再定義する。T8（23.2章）は「単一worker用Scenario Cエントリポイント」として再定義する。

### 10.5 Environment isolation：単一専用worker process方式（authority containment・M1解決）

Round 4・Round 5は、crash seam用env varの扱いを段階的に強化した（Round 4：テストオーケストレータ自身の`os.environ`へ直接設定・restoration契約なし→Round 5：2つの専用worker subprocessへ個別に`env=`を渡す）。Round 5 B1により2-worker構成自体が撤回されたため、Round 6は単一worker内での新しいenvironment isolation契約を確定する。あわせてRound 5 B2（authority containment欠落）にも本節で対応する。

**（Round 6 Codexレビュー B1への対応）** Round 6のCodexレビューは、当時の1.の allowlist案が、既定falseのFeature Gate（`AI_AGENT_ENABLED`・`WORKFLOW_ENGINE_ENABLED`・`RETRY_ENGINE_ENABLED`・`RETRY_LINEAGE_ENABLED`）とstub認証情報（`ANTHROPIC_API_KEY`・`WP_USERNAME`・`WP_APP_PASSWORD`）を含んでおらず、記載どおりのenvではStep 1が`NullWorkflowEngineManager`、Step 2が`NullRetryManager`またはlineage claim失敗となり、main.pyがWordPress POSTへ到達できないとBlockingで指摘した。以下、`src/`配下の該当Config/gateロジックを再読し、single-worker E2Eの完走に必要な環境変数を漏れなく列挙する。

**Round 6で確定する設計**：

1. **worker起動時のenv（authority containment・B1/B2解決）**：テストハーネス（親プロセス）自身の`os.environ`は**一切変更しない**。テストハーネスは、単一の専用worker subprocessを`subprocess.run([sys.executable, worker_script, ...], env=<明示的に構築したallowlistベースのdict>, cwd=..., ...)`で起動する。この`env`辞書は、`os.environ`の無条件コピーではなく、**必要な変数のみを列挙するallowlist方式**で都度新規に構築する。以下がexact contractである（このリストに含まれない変数は、host側の値が何であれworker自身の`os.environ`には一切出現せず、各Configは自身のコード上の既定値を使う）：

   **(a) Windows subprocess起動に必須の基盤変数（Round 8でexact 2変数へ確定、Minor解決。Post-Round 10 Amendmentで3変数へ訂正、第2回AmendmentでAPPDATAの供給元を訂正）**：`SystemRoot`（Windowsのソケット初期化・暗号乱数生成系APIが内部的に参照する、CPython自身がWindows上で動作するために要求する既知の必須変数）・`PATH`（venv配下のPython拡張モジュール（`.pyd`）が依存するDLLの検索に必要）の2変数はhostの値をそのまま使用する。**`APPDATA`（Post-Round 10 Amendment第1回で追加）は、hostの実値ではなく、シナリオ専用に新規作成する空ディレクトリ（scenario-owned empty directory）を使用する**（第2回Amendment、Codex delta review Major#3解決、根拠は次段落）。

   **（Post-Round 10 Amendment第1回：`APPDATA`追加の根拠）** P1・Scenario A〜Fのtest実装フェーズで、Round 8確定のexact 2変数（`SystemRoot`・`PATH`のみ）のallowlistでmain.py実subprocessを起動したところ、`anthropic.Anthropic(api_key=api_key)`呼び出し（main.py:476）が`RuntimeError("Could not determine home directory.")`で即座にクラッシュする事象を実測した。原因を追跡した結果、インストール済みAnthropic SDKの`Anthropic.__init__`が`_warn_env_shadow()`→`_has_auto_discoverable_credentials()`→`_read_active_config_pointer()`→`_config_dir()`という経路で、資格情報の自動探索先ディレクトリを解決するために`pathlib.Path.home()`を呼び出しており（`_config_dir()`は`APPDATA`が設定されていればそれを優先し、未設定の場合のみ`Path.home()`にfallbackする実装）、`APPDATA`が欠落しているとWindows上で`Path.home()`自体が`RuntimeError`を送出することを確認した。この事象は`ANTHROPIC_BASE_URL`の設定有無・実際のAPI呼び出しの成否とは無関係に、**クライアントの構築（コンストラクタ呼び出し）の時点で**発生する。Round 8時点でこの2変数を確定した際の分析（本節冒頭）はAnthropic SDKの資格情報自動探索機能を考慮していなかった（同機能がRound 8以降にSDKへ追加された可能性が高いが、未検証）。

   **（第2回Amendment：APPDATAの供給元をhost実値からscenario-owned empty directoryへ訂正、Codex delta review Major#3解決）** 第1回Amendmentは「`APPDATA`はディレクトリ探索にのみ使われ、credentialの真正性検証には使われないため、hostの実値をそのまま渡してもcontainment/safetyへの影響はない」と評価していたが、この評価は誤りだった。`_config_dir()`が解決するディレクトリには、Anthropic CLIの実際のactive configポインタ（`active_config`ファイル）が存在しうる——hostの実際の`APPDATA`をそのまま渡すと、SDKがこのファイルを実際に読みに行き、host側の実configuration（別のAPI keyやbase URL設定等）を意図せず参照しうる。これは`SystemRoot`・`PATH`（システムパス情報でありconfiguration実体を持たない）とは性質が異なり、containment境界に影響しうる。訂正後の契約：`APPDATA`には、シナリオ開始時に新規作成し中身が空の、シナリオ専用の一時ディレクトリを設定する（`tempfile.mkdtemp()`等、test-only）。これにより、SDKの`_config_dir()`がディレクトリ自体の存在は要求する一方、その中に`active_config`等の実ファイルが一切存在しないため、host側の実際の設定を読みに行く経路が構造的に排除される（`Path.home()`のRuntimeErrorも同様に回避される）。シナリオ終了時にこの一時ディレクトリを削除する（test-only、production側への影響なし）。

   この3変数（`SystemRoot`・`PATH`・`APPDATA`）以外（`TEMP`/`TMP`等）は本プロジェクトの該当コード（`src/retry_lineage/retry_lineage_store.py`等の`tempfile.mkstemp(..., dir=<明示的なstore dir>)`呼び出しを`grep`で確認）がいずれも`dir=`引数を明示的に渡しており、システム既定の一時ディレクトリ（`TEMP`/`TMP`環境変数依存）を一切参照しないため、allowlistに含める根拠がなく含めない。

   **（Post-Round 10 Amendment：`PYTHONIOENCODING=utf-8`をtest subprocess契約へ追加）** main.pyの日本語print出力を、テストハーネス側の`subprocess.run(..., capture_output=True)`が既定ロケール（Windows上のcp932）でdecodeしようとすると`UnicodeDecodeError`が発生することを実測した。この事象は本Releaseで新規に発見されたものではなく、リポジトリ内の既存17ファイル（`tests/test_e2e_v2_2_0_news_agent_foundation.py`ほか、`test_e2e_v2_3_0`〜`test_e2e_v6_30_0`まで）が既に`env["PYTHONIOENCODING"] = "utf-8"`という同一の対処を採用済みであることをgrepで確認した——本節がこれを明記していなかったのは既存の記述漏れであり、本Amendmentはこれを正式なworker/test subprocess env契約の一部として明文化するものである。`PYTHONIOENCODING`はI/Oエンコーディング設定のみであり、containment/safetyへの影響はない。本変数は、main.py実subprocessを起動する全シナリオ（A・B・C・D・F1・F2）のenv契約へ共通して含める（Bについては7.5.4節のScopedEnv、それ以外はallowlistまたは各worker契約の一部として含める）。

   **(b) 二重ゲート（Step 1のcanonical execution・Step 2内部の`WorkflowEngineManager`いずれにも必要）**：
   - `AI_AGENT_ENABLED=true`（既定`false`、`src/ai/agent_config.py:35`）
   - `WORKFLOW_ENGINE_ENABLED=true`（既定`false`、`src/workflow_engine/workflow_engine_config.py:31`）——いずれか一方でもfalseだと`WorkflowEngineManager.from_config()`は`NullWorkflowEngineManager`を返す（`src/workflow_engine/workflow_engine_manager.py:94-95`、二重ゲートいずれかFalseで即Null）。NEWS stepは二重ゲートが開いていれば無条件で構築される（同ファイル`:91`のdocstring、REVIEW/PUBLISH側の個別gateはScenario Cでは不要——NEWS step内でWordPress POSTまで完結するため）。

   **(b') NewsAgent interval gateの無効化（Round 9新規、Codex Round 8 Major 2解決）**：
   - `NEWS_AGENT_MIN_INTERVAL_MINUTES=0`（既定`180`、`src/ai/news_agent_config.py:43`）——`NewsAgent.decide()`（`src/ai/news_agent.py:60-68`）の判定式`elapsed_minutes >= min_interval`を、既存の実行ログの有無・経過時間の長さに関わらず常に真とするための設定。canonical execution（空RSS、Step 1）はmain.pyの`return 1`で即座に終了し実行ログを書き込まないため、新規のDisposable Project Copyであれば本設定がなくてもStep 2のNEWS step実行は`decide()`の「実行履歴が見つからないため初回実行」分岐により`should_act=True`となるが、本設定はそれ以外の経路で実行ログが存在してしまう場合に備えたdefense-in-depthである（10.2節Step 1で詳述）。

   **(c) Retry Runtime側の三重ゲート＋lineage claimゲート（Step 2で`composition_root.manager`が実`RetryManager`になり、かつ`claim()`が成功するために必要）**：
   - `RETRY_ENGINE_ENABLED=true`（既定`false`、`src/retry_engine/retry_config.py:33`）——`RetryManager.from_config()`は`RETRY_ENGINE_ENABLED`がfalse、または渡された`workflow_engine_manager`が`NullWorkflowEngineManager`（＝(b)未成立）の場合に`NullRetryManager`を返す（`src/retry_engine/retry_manager.py:312-340`のdocstring、実質的に`AI_AGENT_ENABLED × WORKFLOW_ENGINE_ENABLED × RETRY_ENGINE_ENABLED`の三重ゲート）。
   - `RETRY_LINEAGE_ENABLED=true`（既定`false`、`src/retry_lineage/retry_lineage_config.py:32`）——`RetryLineageManager.claim()`（`src/retry_lineage/retry_lineage_manager.py:362-366`）は、`self._config.is_ready()`がFalseの場合`acknowledged=False`（reason=`"RETRY_LINEAGE_ENABLED is false (claim gate closed, 16章)."`）を返し、`RetryManager._retry_locked()`はこの時点で`RetryOutcome.SKIPPED`として処理を打ち切る（`retry_manager.py:486-491`）——実`RetryExecutor.execute()`へ到達する前に終わってしまうため必須。

   **(d) 外部通信先の差し替え（7.5.1節Controlled Upstream Boundary、既存部分は変更なし。`NO_PROXY`はRound 8で新規追加、Round 9で各HTTPスタック別の根拠へ訂正、Round 8 Minor解決）**：`WP_SITE_URL`・`ANTHROPIC_BASE_URL`・`NEWS_RSS_FEED_URLS_OVERRIDE`（P1有効化時）に加え、**`NO_PROXY=127.0.0.1,localhost`を必須で追加する**。main.py実subprocessが行う3つの外部通信は、ライブラリごとに異なるが、いずれもLocal Stubへのloopback通信をsystem proxyへ迂回させない経路を持つことをそれぞれ直接確認した：
   - **`requests`によるWordPress POST**（`src/outputs/wordpress_output.py:15`で`import requests`を直接確認）：`requests`自身が`should_bypass_proxies(url, no_proxy)`（`venv/Lib/site-packages/requests/utils.py:810-870`）という専用の判定を持つ。この関数は`no_proxy`（`os.environ.get("no_proxy") or os.environ.get("NO_PROXY")`、大文字小文字いずれの表記も直接読む）の値を解析し、宛先hostnameがIPv4の場合（`127.0.0.1`は該当）、`no_proxy`中の各エントリと**厳密一致**するかを確認する（`:839-847`）。`NO_PROXY=127.0.0.1,localhost`を設定すると、この一致判定により`should_bypass_proxies()`は**`urllib.request.getproxies()`を呼び出す前に**`True`を返し、`get_environ_proxies()`（`:873-882`）は空dict`{}`をそのまま返す——Windows System Registryへは一切到達しない、`requests`自身が持つ最も直接的な保証である。
   - **`feedparser`によるRSS取得**（内部で`urllib.request`を使用）、および**Anthropic SDKが使う`httpx`**：いずれも標準ライブラリ`urllib.request.getproxies()`（`getproxies_environment() or getproxies_registry()`、Python標準ライブラリのソースを直接確認済み）へ到達する経路を持つ。`getproxies_environment()`は環境変数名の末尾が`_proxy`（大文字小文字を区別しない）であるものを走査するため、`NO_PROXY`（任意の大文字小文字表記）は確実に拾われる。`getproxies_environment()`が**空でない**dict（`{"no": "127.0.0.1,localhost"}`）を返した場合、Pythonの`or`演算子により`getproxies_registry()`（Windows System Registryのproxy設定を読む経路）は**一切呼ばれない**。
   - 以上より、`NO_PROXY=127.0.0.1,localhost`を設定するだけで、`requests`は自身の`should_bypass_proxies()`により、`feedparser`（`urllib`）・`httpx`は`getproxies()`の短絡評価により、それぞれ異なる経路でではあるが、host機に設定されている可能性のあるWindows system proxyの参照そのものを構造的に遮断できる（`HTTP_PROXY`/`HTTPS_PROXY`を未設定のままにできる理由）。これにより、Local Stubへのloopback通信（`127.0.0.1`宛）がsystem proxyへ迂回する経路が、ライブラリ別の実クライアント挙動の直接確認に基づき排除される。

   **(e) stub向けdummy認証情報（Round 6で新規追加、B1解決）**：main.py実subprocess・Step 1のcanonical execution用`WorkflowEngineManager`インスタンスいずれも、以下が空だと途中で処理を継続できない：
   - `ANTHROPIC_API_KEY=<test-only dummy値>`（例：`"sk-test-dummy-0000000000000000000000000000000000000000"`のような形式のダミー文字列。実credentialへは一切依存しない）——main.py（`:425-429`）は`os.getenv("ANTHROPIC_API_KEY")`が空の場合エラーメッセージを出力し`return 1`する（main.py実subprocess全体が即座に終了し、NEWS収集にすら到達しない）。`client = anthropic.Anthropic(api_key=api_key)`（`main.py:476`）はこの`api_key`をそのままSDKへ渡すのみであり、`ANTHROPIC_BASE_URL`（(d)）によりLocal Stubへ向くため、値の真正性は検証されない——形式的に非空文字列であれば足りる。
   - `WP_USERNAME=<test-only dummy値>`・`WP_APP_PASSWORD=<test-only dummy値>`——`WordPressOutput.is_available()`（`src/outputs/wordpress_output.py:79-80`）は`site_url`・`username`・`app_password`の3つすべてが非空の場合のみ`True`を返す（`bool(self.site_url and self.username and self.app_password)`）。いずれかが空だとWordPress出力自体がスキップされ、`record_attempted()`/POST/`record_confirmed()`のいずれにも到達しない。Local StubはBasic Auth値の真正性を検証しない前提（7.5.5節、既存Local Stub仕様）のため、ダミー値で足りる。

   **(f) `.env`実値混入防止・バイトコード抑止（既存、変更なし）**：`PYTHON_DOTENV_DISABLED`（7.5.2節）・`PYTHONDONTWRITEBYTECODE`（7.5.3節）。

   **(g) authority containmentのためのexclusion（B2解決、変更なし）**：**`EXECUTION_HISTORY_DIR`・`RETRY_LINEAGE_DIR`はこのallowlistに一切含めない**（6.26節）。これにより、`ExecutionHistoryConfig.from_env(project_root=<Disposable Copy>)`・`RetryLineageConfig.from_env(project_root=<Disposable Copy>)`は既定値（`project_root`相対）を使い、host環境からの絶対パス継承によるauthority漏洩が構造的に排除される。

   **(h) crash seam4変数は含めない**：`PYTHONPATH`・`WP_OUTPUT_CRASH_SEAM_ENABLED`・`WP_OUTPUT_CRASH_SEAM_SRC_DIR`・`WP_OUTPUT_CRASH_SEAM_EVIDENCE_PATH`は、worker起動時点のこのenvには**含めない**（10.2節Step 1のcanonical executionがcrash seamを認識してはならないため。2.で規定するとおりStep 2直前にのみscoped設定する）。

   **(i) 上記(a)〜(h)以外の変数を明示的に設定しない理由**：`RETRY_QUEUE_ENABLED`（既定`true`）・`WORKFLOW_MONITOR_ENABLED`（既定`true`）・`EXECUTION_HISTORY_ENABLED`（既定`true`）等、既定値が「有効」であるゲートは、allowlist方式によりworker自身の`os.environ`にそもそもキーが存在しないため、各`from_env()`内の`os.environ.get(KEY, "true")`が確実にコード上の既定値へフォールバックする——host側でこれらを明示的に`false`へ上書きしていたとしても、allowlist方式（`os.environ`の無条件コピーを使わない）である以上、その値がworkerへ継承されることは構造的にない。
2. **worker内でのscoped crash seam設定（M1解決）**：worker（単一プロセス・単一スレッド、10.2節）は、Step 2で`orchestrator.run_once()`を呼び出す**直前**にのみ、自身の`os.environ`へcrash seam用4変数を設定し、`run_once()`呼び出し完了後（正常終了・例外いずれの経路でも）に`finally`ブロックで**設定前の状態へ完全復元する**（該当4キーを`os.environ`から削除する。Step 2開始前は未設定だったため、削除で完全復元となる）。
   ```
   try:
       os.environ["PYTHONPATH"] = ...
       os.environ["WP_OUTPUT_CRASH_SEAM_ENABLED"] = "1"
       os.environ["WP_OUTPUT_CRASH_SEAM_SRC_DIR"] = ...
       os.environ["WP_OUTPUT_CRASH_SEAM_EVIDENCE_PATH"] = ...
       cycle_result = orchestrator.run_once(dry_run=False)
   finally:
       for key in (
           "PYTHONPATH", "WP_OUTPUT_CRASH_SEAM_ENABLED",
           "WP_OUTPUT_CRASH_SEAM_SRC_DIR", "WP_OUTPUT_CRASH_SEAM_EVIDENCE_PATH",
       ):
           os.environ.pop(key, None)
   ```
   Pythonの`subprocess.run()`の`env`引数省略時（既定）は呼び出し元プロセス（＝worker自身）の`os.environ`をそのまま子プロセスへ継承する（標準ライブラリの文書化された挙動、6.19節の`{**os.environ, ...}`パターンもこの継承を前提とする）。したがって、`run_once()`が内部でmain.py実subprocessを起動する瞬間（Step 2、retry execution）にはworkerの`os.environ`に4変数が存在し継承されるが、Step 1（canonical execution）の時点および`finally`復元後は存在しないため継承されない。
3. **単一worker・単一スレッドによる無関係childへの漏洩防止**：workerは単一プロセス・単一スレッドであり、Step 1〜3を順に同期実行する（並行して他のsubprocessを起動しない）。したがって、crash seam用4変数がscoped設定されている時間窓（Step 2内、`run_once()`呼び出し中）に、main.py実subprocess（retry execution用）以外のいかなる子プロセスもworkerから起動されない——「無関係childへの漏洩」はArchitecture上発生し得ない。
4. **テストハーネスが起動する他のプロセス**：Local Stub HTTPサーバー等、worker以外にテストハーネスが起動する可能性のあるプロセスは、テストハーネスが個別に`env=`を指定して起動するか、`env=None`（既定、テストハーネス自身の未変更の`os.environ`を継承）で起動するため、crash seam関連の変数を受け取ることは構造的にない。
5. **旧7.5.4節（Child Env Allowlist）の記述との関係**：7.5.4節は「テストオーケストレータ自身が、自らの`os.environ`をどう構成するか」という記述だったが、Round 6ではテストハーネス自身の`os.environ`を変更しない（1.のallowlist方式でworker起動時の`env`辞書を都度構築する）ため、7.5.4節は本節の内容へ置き換える（7.5.4節側にも本節への参照を追記する）。

この設計により、「無関係なPython childがsitecustomizeを読む」可能性、および「host環境のpath override変数がDisposable Copyの隔離契約を迂回する」可能性の両方が、Architecture上構造的に排除される——crash seam関連の環境変数は、単一workerプロセスの`os.environ`のうち`run_once()`呼び出し中という限定された時間窓にのみ存在し、`EXECUTION_HISTORY_DIR`・`RETRY_LINEAGE_DIR`はworker起動時のallowlistに含まれないため常に既定値（Disposable Copy相対）が使われる。

### 10.5a Worker自身のimport解決契約（Round 8新規、Round 7 Major 1解決）

**指摘の要旨**：Round 7 Major 1は、worker自身が`src/`配下のproduction module（`AgentConfig`・`WorkflowEngineConfig`・`RetryCompositionRoot`・`RetryRuntimeOrchestrator`等）をどう`import`するかが未規定であり、worker自身はDisposable Project Copy外（7.5.3節、`tests/`配下——コピー**される**側には含まれない）に存在するため、記載どおりでは`import`が失敗するか、意図せずoriginal projectの`src/`やinstalled packageを誤って解決しうる、と指摘した。

**確定した設計（production source変更ゼロ、6.24節のsitecustomize import解決検証と同型のパターンを踏襲）**：

1. **worker起動時の引数**：テストハーネスは、worker script起動コマンドの**第1位置引数**として`<Disposable Project Copy root>`の絶対パス文字列を渡す（`subprocess.run([sys.executable, worker_script, str(disposable_copy_root), ...], env=<10.5節1.のallowlist>)`）。`PYTHONPATH`環境変数には一切依存しない——`PYTHONPATH`はcrash seam4変数の1つとして10.5節2.でStep 2直前にのみscoped使用される予約済みの経路であり、worker自身のimport解決とは完全に独立した別の仕組みである。
2. **worker scriptの先頭で行うbootstrap**（worker自身のコード内、他のいかなる`src`-rooted importより前に実行する）：
   ```python
   import sys
   from pathlib import Path

   disposable_copy_root = Path(sys.argv[1]).resolve()
   expected_src = (disposable_copy_root / "src").resolve()
   sys.path.insert(0, str(expected_src))  # 先頭insert、他の解決より優先させる
   ```
3. **import解決の検証（fail-closed）**：worker自身が直接importする`src/`配下の各top-level package——`ai`（`AgentConfig`）・`workflow_engine`（`WorkflowEngineConfig`・`WorkflowEngineManager`）・`retry_composition`（`RetryCompositionRoot`）・`retry_runtime_orchestrator`（`RetryRuntimeOrchestrator`）——について、importした直後に以下を検証する（6.24節の`sitecustomize.py`が`wordpress_draft_state.wordpress_draft_state_manager`に対して行う検証と同一のパターン）：
   ```python
   for _module in (ai, workflow_engine, retry_composition, retry_runtime_orchestrator):
       resolved = Path(_module.__file__).resolve()
       if not resolved.is_relative_to(expected_src):
           print(
               f"fail-closed: {_module.__name__} resolved from {resolved}, "
               f"expected under {expected_src}",
               file=sys.stderr,
           )
           sys.exit(WORKER_IMPORT_RESOLUTION_FAILED_EXIT_CODE)
   ```
   （`WORKER_IMPORT_RESOLUTION_FAILED_EXIT_CODE`は、main.pyの既知token`{0, 1, 20, 21}`・`SIDE_EFFECT_CONTRACT_VIOLATION_EXIT_CODE`（`3`）・crash seamの`91`のいずれとも衝突しない、worker専用の診断用exit code値として実装フェーズで確定する。）4パッケージのうち1つでも`expected_src`配下から解決されなかった場合（同名moduleが別の場所——installed package・original project——から誤って解決された場合）、workerはStep 1へ一切進まず即座に終了する。これにより、テストハーネスはworker result fileの不在／worker exit codeの不一致という構造的な失敗として、import誤解決を確実に検出できる（「importが成功したはず」という推定に基づく成功判定を排除する）。
4. **`sys.path.insert(0, ...)`により、以降のPythonの`sys.modules`キャッシュ機構を通じて、worker自身が構築する`AgentConfig`・`WorkflowEngineConfig`・`RetryCompositionRoot`・`RetryRuntimeOrchestrator`等のインスタンスは、すべてDisposable Project Copyの`src/`から解決されたクラス定義に基づく**ことが、3.の検証により保証される。main.py実subprocess自身も、`sys.path.insert(0, str(Path(__file__).parent / "src"))`（`main.py:35`、6.19節既出）により同じDisposable Copyの`src/`から自身のモジュールを解決するため、workerとmain.pyの双方が同一のコード領域（Disposable Copyの`src/`）を参照する一貫性が保たれる。

---

## 11. シナリオD — abandoned RUNNING → TIMEOUT → eligibility判定（Round 4で決定的なtiming contractへ確定、B2解決）

### 11.1 Two-Way Blocking Handshake（Round 3が指摘したtiming未規定を解消）

6.18節で確認した通り、`post_admission_hook`は`WorkflowEngineExecutor.run()`と完全に同期的に実行され、hookが**戻らない限り**NEWS step（main.py起動）は構造的に着手されない。Round 3は、この設計自体は妥当としつつも、hookのself-timeout（30秒）と親側pollingのdeadlineの関係が未規定であり、「workerがtaskkillより先に自己終了しうる」レースをBlocking 2で指摘した。以下、hook self-timeoutと親側deadlineの関係、および`taskkill`直前の最終liveness確認まで含めて完全に決定的なcontractとして確定する。

**タイミング定数（本節で確定する値、および採用根拠）**：

| 定数 | 値 | 根拠 |
|---|---|---|
| `HOOK_SAFETY_TIMEOUT_SEC` | 30秒 | workerのtest-only self-timeout。**正常なcrashテスト経路では絶対に到達しない安全弁**——親が期待どおりkillしていれば、workerはこのタイムアウトに到達する前に強制終了される。Round 1〜3を通じて採用されてきた値を、本節のdeadline関係の中で正式に位置づけ直す。**（Post-Codex-delta-review#3 Amendment、Minor#2対応）** 当初はhookが実際に呼ばれた時点（＝ready-sentinel書き込み後）からのみ計測する「hook側のself-timeout」だったが、これではhookに到達する前（import・gate判定・`manager.run()`呼び出し自体等）でworkerが停止・ハングした場合、安全弁が一切発火せずworkerが無期限のorphanになりうる欠陥があった。`tests/e2e_support/scenario_d_worker.py`の`main()`の最初の行で起動する**process-wide watchdog**（`threading.Timer`、daemon thread、test-owned）へ変更し、`main()`開始時刻を起点に計測するよう改めた——hook自身の待機loopも、hook到達時刻からの新規計測ではなく、この同一のdeadlineを共有する。**（Post-Codex-delta-review#4 Amendment、Minor#1対応：表現の訂正）** 「workerプロセス全体のworst-case生存時間が常に本値以内に収まる」という無条件の保証としてこれを記述するのは正確ではない。本watchdogは`main()`が実行を開始した**後**に設定されるtest-only機構であり、①`main()`より前に発生するmodule-levelのimport解決処理自体は計測対象外である、②`threading.Timer`のコールバックはPythonのGILを介して実行されるため、native codeがGILを長時間占有し続けるような病的なケースでは、コールバック自体の実行が遅延しうる、という2点で「無条件のhard bound」ではない。正確には、**通常のPython interpreter scheduling下でのbest-effort safety timeout**であり、`os._exit(2)`はtimer callbackが実際に実行された時点でprocessを終了させる、という契約として位置づける。external watchdog process等によるhardな上限保証は、本Releaseのscopeに含めない（production変更を要するため）。 |
| `PARENT_READY_DEADLINE_SEC` | 5秒 | 親がready-sentinel出現＋durable RUNNING確認の両方を完了させるための上限。`HOOK_SAFETY_TIMEOUT_SEC`の1/6であり、通常のファイルI/O・durable read所要時間（ミリ秒オーダー）に対して数桁の安全マージンを持つ——CI環境等での一時的な遅延を吸収しつつ、hookの安全弁より確実に先に完了する値として採用する。 |
| `POLL_INTERVAL_SEC` | 0.05秒 | ready-sentinel・durable state・最終liveness確認、いずれのpollingにも共通で使う短間隔。`PARENT_READY_DEADLINE_SEC`（5秒）に対し100回のpolling機会を確保する。 |

**Worker側の実装（test-only worker内、Post-Codex-delta-review#3 Amendmentでprocess-wide化）**：
0. **（第3回Amendmentで追加）** `main()`の最初の行で、process起動時刻を起点とする`threading.Timer`（daemon thread、`HOOK_SAFETY_TIMEOUT_SEC`＝30秒）を起動する。`main()`が正常return（0/93/94のいずれか）すればこのwatchdogは`finally`で`cancel()`される。以降のhookの待機deadlineも、hook到達時刻からの新規計測ではなく、この同一のprocess起動起点のdeadlineを共有する。
1. hookが呼ばれたら、まずready-sentinelファイルを書き込む（durable、`os.replace()`によるatomic write）。
2. 続けて、release-signalファイルの出現、またはStep 0で確定した共有deadline（process起動から`HOOK_SAFETY_TIMEOUT_SEC`秒後）のいずれかまで、`POLL_INTERVAL_SEC`間隔のpollingでblockする。
3. release-signalが出現した場合：`PostAdmissionHookResult(acknowledged=True)`を返す（正常続行、通常はテストのdry-run経路でのみ使う。crash経路では到達しない）。
4. 共有deadlineに達した場合：診断可能なexit code（`2`）で`os._exit(2)`する（親が誤ってkillし忘れた場合の安全弁）。**正常系では発火しないことをテスト自身がPresence Assertionとして確認する**——このexit codeが観測された場合、親側のkillが`PARENT_READY_DEADLINE_SEC`以内に完了しなかったことを意味し、timing failureとして明示的にテストを失敗させる。
5. **（第3回Amendmentで追加、第4回Amendmentで表現を訂正）** hookに到達する前（gate判定・`manager.run()`呼び出し自体等、`main()`開始後の処理）でworkerが停止・ハングした場合、Step 0のwatchdogが`main()`開始から`HOOK_SAFETY_TIMEOUT_SEC`秒後に`os._exit(2)`する——ただしこれは**通常のPython interpreter scheduling下でのbest-effort safety timeout**であり、無条件のhard boundではない（`main()`より前のmodule-level import解決処理自体は計測対象外であり、native codeによるGIL長時間占有下ではtimer callbackの実行自体が遅延しうる）。この設計はあくまで、通常想定される範囲のhang・失敗に対して、workerが有限時間で自律終了する可能性を高めるtest-only機構である。親側が「readiness/durable state確認失敗時はtaskkillを発行しない」という契約（本節・11.2節）を維持したまま、workerの自律終了をこの範囲で補強する——external watchdog processのような、production変更を要するhardな上限保証の追加はscopeに含めない。

**親側の実装（テストオーケストレータ）**：
1. worker（新規test-only Pythonエントリポイント、実`WorkflowEngineManager`を直接構築し上記hookを`post_admission_hook`として渡す）を`subprocess.Popen`で起動し、`proc.pid`を直接取得する（親が自ら`Popen`で起動するため、PID捕捉のための追加機構は不要）。
2. ready-sentinelファイルの出現を`POLL_INTERVAL_SEC`間隔・`PARENT_READY_DEADLINE_SEC`上限のbounded pollingで待つ。deadline超過時はtiming failureとして即座にテストを失敗させる（`taskkill`を発行しない——中途半端な状態のまま強制終了して見かけ上成功させることを避ける）。
3. **durable state二重確認**：ready-sentinel検出後、追加で共有Execution Historyストアを直接読み、当該`run_id`の`WorkflowExecutionRecord.status == RUNNING`かつ`started_at`が設定されていることを、同じく`PARENT_READY_DEADLINE_SEC`の残り時間内で確認する（sentinelファイルの存在だけに依拠しない、defense-in-depth）。**（Post-Codex Full Independent Review Amendment、Major#1対応：authority containment）** このExecution Historyストアの参照先（`history_dir`）は、`ExecutionHistoryConfig.from_env()`（host環境変数`EXECUTION_HISTORY_DIR`を読みうる、6.26節）を使わず、`ExecutionHistoryConfig`（plain dataclass）を直接構築し、`<Disposable Project Copy root>/logs/execution_history`という固定の相対パスをhost環境変数を一切経由せずに指定する。この読み取りはテストハーネス自身のプロセス内（`ExactEnv`等のenv隔離ブロックに入る前）で行われるため、`.from_env()`を使うとhostに`EXECUTION_HISTORY_DIR`が設定されていた場合にDisposable Project Copy外を参照しうる（6.26節のpathlib `/`演算子の絶対path上書き挙動）——直接構築によりこの経路を構造的に排除する。
4. **`taskkill`直前の最終liveness確認**：上記2点が確認できた直後、`taskkill`発行の直前に、`tasklist /FI "PID eq <pid>"`（6.21節）で対象PIDが依然として生存していることを再確認する。生存していなければ、timing failureとして明示的にテストを失敗させる。
5. 生存確認できた場合のみ（release-signalは**送らない**）、worker（＝Workflow Engineプロセス）のPIDに対し`taskkill /PID <pid> /T /F`（プロセスツリー全体、6.11節）を発行する。
6. `taskkill`発行後、`tasklist`で対象PID（およびプロセスツリー）の不在を確認する（cleanup、6.21節）。

**この設計により、Round 3が指摘したタイミング未規定が解消される理由**：
- hookが戻らない限りNEWS step（main.py起動）は着手されない（6.18節、変更なし）。
- 親のready確認＋durable state確認の合計時間上限（`PARENT_READY_DEADLINE_SEC`=5秒）は、hookのself-timeout（`HOOK_SAFETY_TIMEOUT_SEC`=30秒）の約1/6であり（Round 5訂正：「数桁の安全マージン」という表現は不正確だったため撤回する。正確には6倍のbounded deadline関係である）、かつ`taskkill`直前に独立した最終liveness確認を挟むため、「hookが安全弁タイムアウトで自己終了した後に親がkillを発行する」という順序逆転は、発生すれば必ず検出され、テストの明示的な失敗として報告される（黙って見かけ上成功しない）。この設計はfalse success（本来レースに負けているのに成功と誤判定すること）を許さない——deadline超過・liveness確認失敗・hook安全弁タイムアウト発火のいずれも、timing failureとして明示的にテストを失敗させる（false failureが増える可能性はscheduler負荷等の外的要因により残るが、false successは構造的に排除される）。
- release-signalを送る経路が存在しない（crashパスでは常にkillで終わる）ため、「hookがacknowledged=Trueを返してNEWS/main.pyが先に完了してしまう」というレースそのものが発生しえない。

### 11.2 シナリオContract（Round 1版から維持、11.1節の設計に更新）

- **Precondition**：シナリオAの前提。
- **実Runtime経路**：11.1節のtwo-way blocking handshake（timing contract確定版）。
- **Failure Injection**：ready-sentinel検出＋durable state確認＋`taskkill`直前の最終liveness確認、全て`PARENT_READY_DEADLINE_SEC`以内に完了した場合のみ、release-signalを送らずに`taskkill /PID <pid> /T /F`。
- **Durable/Observable Assertions**：`WorkflowMonitor.get_status(run_id)`が`TIMEOUT`を返すこと、当該recordがRetry Eligibility判定へ実際に引き渡され新規lineageが作成されること。
- **Prohibited Outcome**：TIMEOUT判定なしでのRetry Eligibility引き渡し、二重lineage作成、main.py孫プロセスの孤児残存（テスト終了時に対象PIDが存在しないことを確認）、hookの安全弁タイムアウト（exit code 2）が観測されること（timing failureとして報告する）。
- **Test Isolation/Cleanup**：Round 1版から維持。

---

## 12. シナリオE — Runtime restart → attempt/terminal state維持・再投入安全（全面確定、M3解決）

### 12.1 実装ロジックの再確認結果（`_reconcile_all_locked()`、`retry_lineage_manager.py:729-841`）

直接re-readにより以下を確認した：

- `phase==EXECUTION_STARTED`：`resolve_status_fn(record.latest_run_id)`（`:734`）。`monitor_status==RUNNING`→**スキップ**（`:737-738`、`resolved_count`に加算されない）。それ以外（SUCCESS/FAILED/TIMEOUT）→`disposition`決定→`mark_terminal()`→ack時`resolved_count+=1`（`:780-784`）。
- `disposition`決定：`record.side_effect_contract_version is None`（**legacy lineage**）の場合のみ`disposition_from_categories(categories)`（`:759`）。protected lineageでmanifest/classifier欠如の場合は無条件`HUMAN_REVIEW_REQUIRED`（`:761`）。
- `disposition_from_categories()`（`retry_lineage_target_resolution.py:82-91`）：`categories`に`RETRYABLE_FAILURE`が1つでもあれば`FAILED`を返す（`:87-88`）。
- `classify_execution_history_step()`（`retry_lineage_genuine_action.py:72-96`）：`step.status == StepExecutionStatus.FAILED`→`RETRYABLE_FAILURE`（`:74-75`）。
- 同一`_reconcile_all_locked()`呼び出し内で、直後の第2ループ（`:786-796`）が`phase==TERMINAL`かつ`terminal_disposition in (FAILED, NOT_ACTIONED)`のrecordに対し`open_next_attempt()`を呼ぶ。
- `open_next_attempt()`（`:550-619`）：`phase==TERMINAL`必須、`terminal_disposition`が`FAILED`/`NOT_ACTIONED`（またはHRR+RETRY_ALLOWED）であることを確認、attempt上限・invariantチェック通過後、ack時`phase=READY_ELIGIBLE`・`terminal_disposition=None`（**クリアされる**、`:618-619`）・新しい`attempt_scope`を追加（`:610-617`）。
- **（Major 3解決の根拠）** `reconcile_all()`（`:716-719`）は、本体（`_reconcile_all_locked()`）を呼ぶ前に`RetryExecutionLock(self._config.execution_lock_path)`（`RetryExecutionLockBusyError`時は`skipped=True`を返す、9.3章既存contract）を取得する——E1・E2いずれのfixtureも、このlockが他の保持者によって占有されていない状態でテストが`reconcile_all()`を呼び出す必要がある（占有されたまま呼び出すと`skipped=True`となり`resolved_count`/`opened_count`いずれも0のまま返る——E1と誤認しうる偽陽性を避けるため、fixtureのsetup手順としてlockの非占有を明示する）。
- `ReconcileSummary`（`retry_lineage_results.py:66-76`）の全フィールド：`skipped: bool`・`reason: str | None`・`resolved_count: int`・`opened_count: int`・`released_count: int`。
- `RetryLineageRecord`（`retry_lineage_record.py:168-188`）の関連フィールド：`attempt_count: int`（`mark_execution_started()`が`:491`で+1、`mark_terminal()`・`open_next_attempt()`はいずれも変更しない）・`max_attempts: int`（lineage作成時に`RetryPolicy.max_attempts`からsnapshot、以後不変）・`next_attempt_ordinal: int`・`phase`・`terminal_disposition`・`attempt_scopes: list[RetryAttemptExecutionScope]`（各要素`attempt_no`を持つ）・`steps_confirmed_done: list[str]`。
- `open_next_attempt()`が要求する正確な前提条件（`:550-604`、`ack=False`で拒否される場合の条件式）：①`record.phase == TERMINAL`。②`terminal_disposition in (FAILED, NOT_ACTIONED)`、またはHRR+`human_review_resolution.resolution == RETRY_ALLOWED`。③`record.attempt_count < record.max_attempts`（`:574`、attempt上限）。④`record.next_attempt_ordinal == record.attempt_scopes[-1].attempt_no`（`:583`、invariant、不一致ならauto-repairせず拒否）。⑤`compute_steps_to_execute(record.steps_confirmed_done)`が**非空**であること（`:594-604`、`ALL_WORKFLOW_ENGINE_STEPS`のうち`steps_confirmed_done`に含まれない残りstep。全stepがconfirmed doneだと空になり拒否される）。
- 「unresolved steps」の正確なコード表現：`compute_steps_to_execute(steps_confirmed_done)`（`retry_lineage_target_resolution.py:126-132`）＝`ALL_WORKFLOW_ENGINE_STEPS`（NEWS→REVIEW→PUBLISHの固定順）のうち`steps_confirmed_done`に含まれないstep名のリスト。`steps_confirmed_done`自体は、`mark_terminal()`呼び出し時に`compute_initial_confirmed_steps(monitor_record.steps)`（`classify_execution_history_step()`が`GENUINE_SUCCESS`と分類したstepのみ）が既存値へmergeされる（`:530`）。

### 12.2 Sub-case E1・E2の確定設計（single configuration、あいまいさ排除、Major 3解決）

Round 2が指摘した「1つの構成と正確な結果を選ぶべき」という要求に応え、E2は**legacy lineage（`side_effect_contract_version=None`）のみ**を使用する（manifest/classifier依存の分岐は使わない——protected lineageでのHRR永続性の検証はシナリオCが別途担う、10章）。Round 3 Major 3は「E2の期待値が、残attempt budget・整合したnext_attempt_ordinal・非空のunresolved steps・利用可能なreconciliation lockという必須条件を欠いている」と指摘した。以下、12.1節で確認した事実に基づき、E1・E2それぞれのfixtureをdurable stateの全フィールド値まで一意に固定する。

**Sub-case E1（意図的に未解決のまま残るケース）**：
- **Fixture（初期durable state）**：`RetryLineageRecord`：`phase=EXECUTION_STARTED`・`side_effect_contract_version=None`・`attempt_count=1`・`max_attempts=3`（任意の`>1`の値で良いが、E1はattempt上限判定へ到達しないため値自体は結果に影響しない）・`next_attempt_ordinal=1`・`attempt_scopes=[scope(attempt_no=1)]`・`terminal_disposition=None`・`latest_run_id=<run_id>`。対応する`WorkflowMonitor.get_status(<run_id>)`が`monitor_status=RUNNING`を返すこと。`reconcile_all()`呼び出し時点で`RetryExecutionLock`が他の保持者に占有されていないこと（上記lock前提）。
- 期待`ReconcileSummary`：`skipped=False, resolved_count=0, opened_count=0, released_count=0`
- 期待final record state：変更なし（`phase==EXECUTION_STARTED`のまま、`attempt_count`・`terminal_disposition`・`attempt_scopes`いずれも不変）
- Prohibited Outcome：`mark_terminal()`が呼ばれること。

**Sub-case E2（legacy lineageで実際に解決されるケース）**：
- **Fixture（初期durable state）**：`RetryLineageRecord`：`phase=EXECUTION_STARTED`・`side_effect_contract_version=None`・`attempt_count=1`（`max_attempts`未満であること自体が前提条件③を満たす）・`max_attempts=2`（`attempt_count(1) < max_attempts(2)`を満たす最小構成として確定）・`next_attempt_ordinal=1`・`attempt_scopes=[scope(attempt_no=1)]`（前提条件④`next_attempt_ordinal(1) == attempt_scopes[-1].attempt_no(1)`を満たす）・`steps_confirmed_done=[]`（前提条件⑤：NEWS stepがFAILEDのため`compute_initial_confirmed_steps()`はNEWSを含めず、REVIEW/PUBLISHは`NOT_REACHED`→`classify_execution_history_step()`が`NOT_APPLICABLE`でありGENUINE_SUCCESSではないため、いずれも`steps_confirmed_done`へ追加されない。`mark_terminal()`後も`steps_confirmed_done=[]`のままであり、`compute_steps_to_execute([])`は3 step全てを返す＝非空）・`terminal_disposition=None`・`latest_run_id=<run_id>`。対応するExecution History（`WorkflowMonitorRecord.steps`）：NEWS stepが`StepExecutionStatus.FAILED`、REVIEW/PUBLISHが`StepExecutionStatus.NOT_REACHED`。`WorkflowMonitor.get_status(<run_id>)`が`monitor_status=FAILED`を返すこと。`reconcile_all()`呼び出し時点で`RetryExecutionLock`が他の保持者に占有されていないこと（E1と同じ前提）。
- **中間経路（`_reconcile_all_locked()`内部、テスト自身は呼ばない）**：第1ループで`classify_execution_history_step()`がNEWS stepを`RETRYABLE_FAILURE`に分類→`disposition_from_categories()`が`FAILED`を返す→`mark_terminal(disposition=FAILED, ...)`が`phase=TERMINAL`・`terminal_disposition=FAILED`へ遷移させ`resolved_count+=1`。第2ループで同じrecordが`phase==TERMINAL`かつ`terminal_disposition==FAILED`の条件に合致し`open_next_attempt()`が呼ばれ、前提条件①〜⑤を全て満たすため`acknowledged=True`・`opened_count+=1`。
- 期待`ReconcileSummary`：`skipped=False, resolved_count=1, opened_count=1, released_count=0`
- 期待final record state：`phase=READY_ELIGIBLE`、`terminal_disposition=None`（クリア済み）、`attempt_count=1`（不変、`open_next_attempt()`は変更しない）、`next_attempt_ordinal=2`、`attempt_scopes`に`attempt_no=2`の新しいscopeが追加され`steps_to_execute`が3 step全てを含むこと。
- Prohibited Outcome：attempt countのリセット、`terminal_disposition`が`FAILED`のまま残ること、新規lineageとして誤認識されること、`max_attempts`未満条件・`next_attempt_ordinal`整合条件・非空unresolved steps条件のいずれかを欠いたfixtureで「たまたま」`opened_count=1`になること。

### 12.3 CLAIMED回収・restart後のattempt/terminal state維持（Round 1版から維持）

### 12.4 実Runtime経路・Test Isolation（Round 1版から維持）

---

## 13. シナリオF — Scheduler restart/same-minute tick/second driver → duplicate production dispatchなし（Round 4でTriple-Gate・lock所有権契約を確定）

### 13.1 Sub-case F1：Lock Contention（Disposable Project Copy必須化、Triple-Gate必須化、M5解決）

Round 2が指摘した通り、F1が使う実CLIスクリプト（`scripts/run_scheduler_driver.py`）の lockパスは`_PROJECT_ROOT = Path(__file__).parent.parent`（`:51`）を基準としており、cwdではなくスクリプト自身のファイル位置に固定される。したがって、F1が主張する「シナリオ専有のlockディレクトリ」を実現するには、**F1もDisposable Project Copy（7.5.3節）内で実行する必要がある**。

Round 3 Major 5は「`SCHEDULER_DRIVER_ENABLED=true`のみでは、Workflow Engine gateが`NullWorkflowEngineManager`を生成した場合に1つ目のCLIがlockをほぼ即座に解放してしまい、lock contentionが保証されない」と指摘した。6.22節で`scripts/run_scheduler_driver.py`を確認した結果、この指摘は正確である。以下、この指摘を反映してPreconditionを確定する：

- **Precondition（Triple-Gate必須化）**：Disposable Project Copy内。`.env`（またはchild env）に**三重ゲート全て**——`SCHEDULER_DRIVER_ENABLED=true`・`AI_AGENT_ENABLED=true`・`WORKFLOW_ENGINE_ENABLED=true`——を設定する。1つ目のdriverは必ず`--loop`付きで起動する（既定`interval_seconds=60`で足りる。三重ゲートを満たしていれば`NullWorkflowEngineManager`分岐自体を通らないため、lock保持期間の心配は不要）。7.5.1節のControlled Upstream Boundary（RSS/Anthropic/WordPress stub）は、実際のdispatchが本sub-caseの検証対象ではないため必須ではないが、Composition Root構築時の予期しない失敗を避けるため、A〜Cと同じstub設定を一貫して適用することを推奨する。
- **実Runtime経路**：Disposable Project Copy内の実`scripts/run_scheduler_driver.py`を上記Precondition・`--loop`付きで先に起動し、lockファイル（コピー内の`.run/scheduler_driver.lock`）の出現をbounded pollingで待ち、そのファイルに記載されたPIDのプロセス生存を確認してから、2つ目の（同じコピー内の）`scripts/run_scheduler_driver.py`を起動する。
- **Polling Contract（exclusive file creationとPID書き込みの間隔に耐える）**：`RetryRuntimeLock.acquire()`はlockファイルを作成した**直後**にPIDを書き込む2段階の操作である（`retry_runtime_lock.py:56-70`、`os.open(O_CREAT|O_EXCL)`直後に同一fdへ`os.write()`する構造を直接確認済み）。単に「lockファイルが存在するか」だけを確認するのではなく、（a）ファイルが存在し、かつ（b）ファイル内容が空でなくPIDとして解釈可能な値を含み、かつ（c）そのPIDが実際に生存しているプロセスであること（`tasklist`、6.21節）の3点を、短間隔のリトライ付きpollingで確認してから2つ目のdriverを起動する。
- **Durable/Observable Assertions**：2つ目のdriverプロセスが`RetryRuntimeLockError`相当でfail-closedに終了し、標準出力（`scripts/run_scheduler_driver.py:121-123`、stdout）にlockエラーメッセージが現れ、exit codeが1であること。加えて、**lockファイルに記載されたPIDが（2つ目のdriver起動の前後を通じて）生存し続けていること**、および**lockファイルの内容自体が2つ目のdriver起動前後で変化しないこと**（lock所有者が入れ替わっていないことの確認）。
- **Prohibited Outcome**：2つ目のdriverがdispatchを行うこと。1つ目のdriverが`NullWorkflowEngineManager`分岐（三重ゲート不備）を通ってしまい、lockが早期解放されること。

**（Post-Round 10 Amendment：PID contractの確定）** P1・Scenario A〜Fのtest実装フェーズにおいて、`subprocess.Popen`が返すPID（`proc.pid`）と、lockファイルへ実際に書き込まれるPID（起動された`python.exe`自身の`os.getpid()`）が一致しない事例を、あるvenv環境で実測した（`scripts/run_scheduler_driver.py --loop`起動時）。根本原因は特定していない（このvenvの`python.exe`起動特性に起因すると推測されるが未検証）。

既存のlock contractを再確認した結果、この事象はF1の安全性検証には影響しないと判断する：
- `RetryRuntimeLock.acquire()`の排他性は`os.open(O_CREAT|O_EXCL|O_WRONLY)`によるOSレベルのatomic生成のみに依拠し、**書き込まれるPIDの値には一切依存しない**。2つ目のdriverの`acquire()`は、1つ目が書いたPIDが何であれ、ファイルが既に存在する時点で`FileExistsError`→`RetryRuntimeLockError`により即座に失敗する。
- lockファイルへ書き込まれるPIDは、人間が手動復旧の要否を判断するための診断情報としてのみ使われる（`RetryRuntimeLockError`のメッセージ本文が「対象プロセスが異常終了していないか確認した上で...手動削除してください」と案内する）。F1が検証する自動化された安全機構（lock取得の排他性、6.22節のgate順序）は、このPID値を読み取って判定するロジックを一切持たない。
- **（設計書の誤記訂正、Codex delta review Minor#1で指摘）** `_verify_lock_ownership(lock_path, own_pid)`は「`SchedulerDriverOrchestrator.run_once()`内部（F2の直接構築経路）でのみ使われる」という記述は誤りだった。実際には`scripts/run_scheduler_driver.py`自身（F1が起動する実CLIスクリプト）も、lock取得直後・`SchedulerDriverCompositionRoot`構築より前に`_verify_lock_ownership(lock_path, own_pid)`を明示的に呼んでいる（`scripts/run_scheduler_driver.py:129`、`own_pid = os.getpid()`は同一プロセス内の値であるため、この自己検証は常に一致する）。加えて、その後呼ばれる`SchedulerDriverOrchestrator.run_once()`自身も冒頭で同じ関数を再度呼ぶ（6.23節）。したがって`_verify_lock_ownership`はF1のCLIスクリプト経路・F2の直接構築経路の**両方**から呼ばれる共通関数であり、F2専用ではない。この事実は、今回観測された`proc.pid`とlockファイル記載PIDの不一致（テストハーネス側の`subprocess.Popen`の見え方の問題）とは無関係である——`_verify_lock_ownership`が比較する`own_pid`は常にドライバ自身の`os.getpid()`であり、外部の`Popen.pid`とは比較されない。

したがって、**F1のDurable/Observable Assertionsは「`proc.pid`とlockファイル内容の一致」を要求しない**（上記assertion本文を確定：「lockファイルに記載されたPIDが2つ目のdriver起動の前後とも再読して生存していること」「2つ目のdriver起動前後でlock所有者が変わっていないこと」の2点で足りる）。今回観測されたPID不一致は、**test-environment varianceとして記録し、Release blockerとしては扱わない**——duplicate-driver safetyの証拠強度（2つ目のdriverがfail-closedに終了し、dispatchへ到達しないことの構造的証明）は、この事象によって低下していない。
- **Test Isolation/Cleanup**：Disposable Project Copy自体がシナリオ専用のlock/ledgerディレクトリを保証する。

### 13.2 Sub-case F2：Deterministic Dispatch/Restart/Same-Minute Tick（restart証跡を必須化、lock所有権契約を明示、M6/OI-9解決）

Round 2は「F2がfresh process/reconstructionを任意扱いにしているが、Scenario Fはrestart証跡を明示的に要求している」と指摘した。Round 3 Major 6は「F2は`run_once()`をdirect constructionで直接呼び出しているが、PID所有lockの取得手順が specify されていない。`run_once()`はlock所有権が欠落/不一致の場合即座に拒否する」と指摘した。6.23節で`SchedulerDriverOrchestrator.run_once()`・`RetryRuntimeLock`を確認した結果、この指摘は正確である——`run_once()`自身は`RetryRuntimeLock.acquire()`を一切呼ばず、冒頭で`_verify_lock_ownership(lock_path, own_pid)`を行うのみであり、lock取得は呼び出し元の責務である。以下、この指摘を反映してF2の設計を確定する：

- **採用する設計選択肢**：`SchedulerDriverCompositionRoot`/`SchedulerDriverOrchestrator`をtest-only Pythonコードから直接構築し、固定`ClockProvider`実装（既存の確立済み抽象化、6.13節）と`TriggerType.ONCE`の決定的Job定義を注入する（production/script変更ゼロ）。
- **Lock所有権契約の明示**：test-only直接構築ハーネスは、`run_once()`を呼び出す**前**に必ず自ら`RetryRuntimeLock(lock_path=<シナリオ専用lockパス>)`を構築し`acquire()`を呼ぶ（既存`RetryRuntimeLock`のpublic APIをそのまま呼ぶだけであり、production code変更は不要）。取得した`own_pid=os.getpid()`と同じ`lock_path`を`SchedulerDriverOrchestrator`のコンストラクタへ渡す。same-minute tick（同一プロセス内で`run_once()`を複数回呼ぶ場合）は、1回の`acquire()`で複数回の`run_once()`呼び出しを覆ってよい。restart（新規プロセス）の場合は、**新しいプロセスが自分自身の`RetryRuntimeLock(lock_path=同一パス).acquire()`を呼ぶ**——1回目のプロセスが`lock.release()`で確実にlockを解放してから終了することが前提となる。
- **restart証跡の必須化**：same-minute tick（同一プロセス内で`run_once()`を複数回呼ぶ）と、restart（**新規プロセスとして**test-only workerを再度起動し、durable dispatch ledgerを再読み込みさせた上で`run_once()`を呼ぶ）の両方を、**いずれも省略不可の必須sub-caseとして**実施する。restartについては、1回目のworkerプロセスを正常終了させた後（lock解放を確認した後）、**別の新しいプロセス**（同じdispatch ledgerディレクトリ・同じlockパスを指す）を起動することで、プロセス間でのdispatch ledger永続化を実際に証明する。
- **Dispatch Ledgerディレクトリの共有経路（OI-9解決）**：既存の環境変数`SCHEDULER_DISPATCH_LEDGER_DIR`（`SchedulerDispatchLedgerConfig.from_env(project_root)`、`scheduler_dispatch_ledger_config.py:26`——本Releaseが新設しない、既存のproduction設定サーフェス）に、シナリオ専用の絶対パスを設定する。1回目・2回目（restart）のプロセスの**双方**が、同一の`SCHEDULER_DISPATCH_LEDGER_DIR`値を（child env経由で）受け取ることで、同一ディレクトリを共有する。新しいproduction seamの追加は不要——既存の環境変数を2回、同じ値で設定するだけで足りる。
- **P2（Scheduler Driver test clock/scheduleフック）への非依存**：F2はCLIスクリプトを経由しない直接構築方式を採用するため、23章のP2候補は本Releaseの実装スコープに含めない。
- **Durable/Observable Assertions**：同一event_identityに対する`WorkflowEngineManager.run()`呼び出しが1回のみ（same-minute tick複数回でも、プロセスを跨いだrestart後でも）。dispatch ledgerの`CLAIMED→CONFIRMED`の1系列のみ。1回目のプロセス終了時にlockが確実に解放されていること（`tasklist`/lockファイル不在で確認）。
- **Prohibited Outcome**：同一event_identityに対する複数回のdispatch。`run_once()`が`LockIntegrityViolationError`を送出すること（lock所有権契約の設定漏れを意味する）。
- **Test Isolation/Cleanup**：dispatch ledger格納ディレクトリ・lockパスをいずれもシナリオ専用に限定する。

---

## 14. Design Decision B：Second-Driver Genuine Concurrency（Round 4でTriple-Gate反映）

### 14.1 Lock Contention（13.1節F1、OI-2最終判定、Triple-Gate必須化）

production pause hookは不要。lockファイルのbounded polling＋PID生存確認（`tasklist`、6.21節）による手法を採用する。lock contentionを確実に成立させるため、1つ目のdriverには三重ゲート（`SCHEDULER_DRIVER_ENABLED`・`AI_AGENT_ENABLED`・`WORKFLOW_ENGINE_ENABLED`いずれも`true`）と`--loop`を必須とする（6.22節、13.1節、M5解決）。

### 14.2 Deterministic Dispatch（13.2節F2）

P2は本Release（6.35）の実装スコープから除外し、別Human Gate対象として23章に残す。F2は直接構築方式のみで、CLIスクリプトを経由しない構成を採用する。

---

## 15. Boundary-Specific Crash Contract（Round 6で単一worker反映）

| 境界 | 対象シナリオ | crash手法 | handshake | durable precondition | 期待状態 | cleanup |
|---|---|---|---|---|---|---|
| 6.32 write-ahead（POST成功後・`record_confirmed()`前） | C（統合設計、10章） | main.py実subprocess自身の内部での`os._exit(91)`（test-owned`sitecustomize.py`による`WordPressDraftStateManager.record_confirmed`のクラス属性差し替え、原処理は一切実行しない、6.24節） | なし（外部pollingや外部killを一切使わない。`record_confirmed()`のcall siteそのものにコードレベルで到達した瞬間に発火する、タイミング非依存の決定的機構） | manifest登録・`record_attempted()`・POST成功（ステータス200/201確認込み）が実際に発生していること——コードの制御フロー自体が保証する（6.20節） | durable stateが`ATTEMPTED`のまま、実RetryExecutor（単一の専用test worker process内で`RetryCompositionRoot.from_env(base_dir=<Disposable Copy>)`でmain.pyと同一state領域に結合、6.25節）経由で`terminal_disposition=HUMAN_REVIEW_REQUIRED`が確定 | test-owned durable evidence marker file（crash hook到達の直接証拠、production API戻り値に非依存、6.24節）の存在確認、単一workerの正常終了確認、durable store・manifestディレクトリのシナリオ専用隔離、worker`os.environ`からのcrash seam4変数の`finally`復元確認（10.5節） |
| abandoned RUNNING（`start_run()` ack後・NEWS step着手前） | D | 外部`taskkill /PID <pid> /T /F`（プロセスツリー全体） | **Two-Way Blocking Handshake**（11.1節、hookがready-sentinel書き込み後にblock、release signalを送らずkillすることで着手前クラッシュを構造的に保証。`PARENT_READY_DEADLINE_SEC`=5秒 ≪ `HOOK_SAFETY_TIMEOUT_SEC`=30秒、`taskkill`直前の最終liveness確認込み） | `start_run()`のdurable ackが確定していること、かつready-sentinel検出＋durable state二重確認＋直前liveness確認 | `WorkflowExecutionRecord`が`RUNNING`のまま | プロセスツリー全体の終了確認（`tasklist`でPID不在を確認、6.21節） |
| 6.34 claim確定後・dispatch前 | F（15章の失敗path再検証とは別に、F2内で必要になった場合のみ） | 既存6.34テスト10と同型の状態操作（`confirm()`呼び出しスキップ→`reconcile_stale_claims()`直接呼び出し） | なし（同一プロセス内の呼び出し順序制御のみ） | `claim()`が実際にackされていること | `RECOVERY_REQUIRED`への遷移 | dispatch ledgerディレクトリのシナリオ専用隔離 |

**Scenario Cは、外部プロセスのタイミングを推測する要素を一切持たない、コード制御フロー由来の決定的crash injectionへ刷新された（10章・6.24節）。Scenario Dのみが外部killに依存するが、タイミング関係が数値で確定しており（11.1節）、raceに万一負けた場合は明示的にtiming failureとして検出・失敗させる自己検証を組み込んでいる。`psutil`はこのプロジェクトに存在しない依存であるため使用せず、Windows標準の`tasklist`/`taskkill`のみで完結させる（6.21節、D・F1・F2で使用、Scenario Cは使用しない）。**

---

## 16. MVP最終検証としてのfailure-path E2E再実行（Round 1版から維持、変更なし）

（16章の表・判定はRound 1版から維持。Round 2 focus 9で「Category Aのみ採用、`v6_32_31`除外」の判断が正しいことを確認済み。）

---

## 17. MVP Definition of Done Traceability Matrix（変更なし）

---

## 18. Test Isolation / Hidden State Segregation原則（Disposable Project Copy命名を反映、内容は概ね維持）

Round 1版の内容を維持。「Disposable Copy」は全て「Disposable Project Copy」（7.5.3節）に読み替える。F1（13.1節）もDisposable Project Copyを使用する点を追加する。

---

## 19. Formal Regression / Zero-Diff / Runtime Artifact Evidence（全面確定、M4解決）

### 19.1 確定した37-file roster（機械的に再構築・検証済み、変更なし）

`tests/`配下を`glob`で実測した結果、以下の**正確に37ファイル**が「正式Inventory」に一致することを確認した：

- `tests/test_e2e_v1_11_0_save_result.py`
- `tests/test_e2e_v5_9_0_retry_runtime_loop_wiring_foundation.py`
- `tests/test_e2e_v6_0_0_retry_runtime_lock_foundation.py`
- `tests/test_e2e_v6_1_0_retry_runtime_graceful_shutdown_foundation.py`
- `tests/test_e2e_v6_2_0_structured_loop_logging_foundation.py`
- `tests/test_e2e_v6_3_0_retry_metrics_foundation.py`
- `tests/test_e2e_v6_4_0_retry_monitoring_foundation.py`
- `tests/test_e2e_v6_5_0_retry_alert_foundation.py`
- `tests/test_e2e_v6_6_0_retry_notification_foundation.py`
- `tests/test_e2e_v6_7_0_retry_notification_message_foundation.py`
- `tests/test_e2e_v6_8_0_retry_notification_cli_report_wiring_foundation.py`
- `tests/test_e2e_v6_9_0_wordpress_media_upload_foundation.py`
- `tests/test_e2e_v6_10_0_ai_image_generation_contract_foundation.py`
- `tests/test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py`
- `tests/test_e2e_v6_12_0_generated_image_wordpress_media_upload_wiring_foundation.py`
- `tests/test_e2e_v6_13_0_article_featured_media_binding_foundation.py`
- `tests/test_e2e_v6_14_0_article_featured_media_orchestration_foundation.py`
- `tests/test_e2e_v6_15_0_image_generation_configuration_gate.py`
- `tests/test_e2e_v6_16_0_generated_image_filename_policy_foundation.py`
- `tests/test_e2e_v6_17_0_article_image_prompt_construction_foundation.py`
- `tests/test_e2e_v6_18_0_article_featured_media_composition_root_foundation.py`
- `tests/test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py`
- `tests/test_e2e_v6_20_0_article_featured_media_runtime_foundation.py`
- `tests/test_e2e_v6_21_0_article_featured_media_runtime_wiring.py`
- `tests/test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py`
- `tests/test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py`
- `tests/test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_refinement_foundation.py`
- `tests/test_e2e_v6_25_0_image_generation_fallback_observability_foundation.py`
- `tests/test_e2e_v6_26_0_zero_diff_guard_registry_foundation.py`
- `tests/test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py`
- `tests/test_e2e_v6_28_0_article_media_upload_state_foundation.py`
- `tests/test_e2e_v6_29_0_retry_observability_pipeline_foundation.py`
- `tests/test_e2e_v6_30_0_production_canonical_run_outcome_contract_foundation.py`
- `tests/test_e2e_v6_31_0_retry_lineage_eligibility_durable_attempt_state.py`
- `tests/test_e2e_v6_32_0_side_effect_fail_closed_foundation.py`
- `tests/test_e2e_v6_33_0_retry_observability_runtime_integration_foundation.py`
- `tests/test_e2e_v6_34_0_scheduler_driver_duplicate_dispatch_safety_foundation.py`

（`v1.11.0`×1 + `v5.9.0`×1 + `v6.0.0`〜`v6.34.0`×35 = 37ファイル。`glob`実測により重複・欠番がないことを確認済み。）

**機械可読capture（必須）**：上記37ファイルのリストを、実装フェーズで新規に追加するtest-only候補（23.2章T6、`tests/formal_regression_inventory.py`のような単純な文字列リストファイル）へ**必須で**転記する。これにより、将来の再導出の曖昧さを排除する。**（Post-Codex Full Independent Review Amendmentで実装完了、30.11節）** `tests/formal_regression_inventory.py`（`FORMAL_REGRESSION_ROSTER`、`tuple[str, ...]`、basename 37件）として実装し、`tests/test_e2e_v6_35_8_t6_formal_regression_roster_validation.py`が、件数（37）・重複0・全path実在・設計書からの独立転記との差分0を静的に検証済みである。**37ファイルを実際に実行するFormal Regression本体（19.2節・19.3節）は、本Amendmentの時点ではまだ実施していない**——別のHuman Gateでの実施を待つ。

### 19.2 実行コマンド・判定規則（変更なし）

各ファイルを`python <file>.py`として実行、exit code 0=PASS。baseline commit：`15c45b9eef23a52313c12ce04663fb8652e4621d`。

### 19.3 SKIP/exception（Round 4でKI-33の扱いを単一contractへ統一、M4解決）

Round 2は「CHANGELOGから暗黙推定するのではなく、既存承認済みのものだけを明示的に列挙すべき」と指摘した。Round 3 Major 4は「§19.3が『免除は与えられない』とする一方、24章Resolution Matrix・26章Gate Checklistが『例外はKI-33に限る』としており、自己矛盾している」と指摘した。

**`docs/CHANGELOG.md`の`[KI-33]`エントリ（`:411-418`）およびFuture Extension節（`:462`）を直接read-onlyで確認した結果、以下の事実を確認した：**

- `[KI-33]`原エントリ（発見日2026-09-16、Release 6.34.0 Implementation Phase）：`scripts/run_scheduler_driver.py`がuncommittedであることに起因して`v6_22_0`・`v6_23_0`・`v6_24_0`・`v6_26_0`・`v6_27_0`の5ファイルがFAILする既知差分。「commit自体が解消条件」であり、「commit後のFormal Regression再実行で0 FAILになることを確認すること」と明記されている（`:417`）。
- `:462`（Future Extension節）：「`docs/CHANGELOG.md` `[KI-33]`（untrackedファイルに起因するFormal Regression 5ファイルのFAIL）：本Releaseのcommit自体が解消条件であり...commit実施時に必ず再確認すること。post-commit再確認の結果、4ファイルは自然解消を確認したが、`test_e2e_v6_27_0`のみ別種のhistorical guard mapping漏れ（`ZERODIFF-1[scripts]`）が判明し、`[KI-33]`のpost-commit追記が記録する狭い補正で解消済み。」と明記されている。この記述は本baseline commit（`15c45b9...`）に含まれる形でCHANGELOG.mdへ記録されている（本記述がbaseline HEAD時点のワーキングツリーに存在することそのものが証拠）。
- **結論**：`[KI-33]`は、baseline commit `15c45b9...`の時点で**5ファイル全てについて完全に解消済みの、過去のKnown Issueである**。これは「Formal Regression実行時に適用すべき現役のSKIP/exceptionカテゴリ」ではなく、**単なる履歴的コンテキスト**である。

**この事実に基づき、19.3節・24章・26章の記述を以下の単一contractへ統一する（矛盾の解消）**：

- **baseline `15c45b9...`におけるFormal Regressionの期待結果は、37ファイル全てについてSKIPなし・exceptionなしの37/37 PASSである。**`[KI-33]`を含め、事前に許容されるSKIP/exceptionカテゴリは1つも存在しない。
- `[KI-33]`は、37-file rosterのうち5ファイルが過去に一時的にFAILしていた理由を理解するための履歴的注記としてのみ本書に残す——「例外として許容する」対象ではない。
- 万一、Release 6.35のFormal Regression実行時にこれら5ファイル（またはそれ以外のいずれか）がFAILした場合、それは`[KI-33]`の再発として扱わず、**新規の問題として原因調査を行う**（既知差分としての免除は一切適用しない、fail-closed）。
- 上記以外のSKIP/exceptionが必要と判明した場合も、実装フェーズでその都度、根拠となるCHANGELOGエントリ（`[KI-*]`番号）を明示した上で個別承認を得る。事前に一括で許容するexceptionテーブルは設けない。

### 19.4 Artifact / Redaction / Cleanup / Retention（変更なし）

---

## 20. Accepted Risks（変更なし）

## 21. Staged Activation Gateとの分離（変更なし）

## 22. `docs/CHANGELOG.md` `[v6.34.0]` commit/push記述の最小訂正方針（変更なし）

---

## 23. Production/Test Implementation Candidate Matrix（Round 6で更新）

### 23.1 Production Implementation候補

| # | 候補 | 対象 | 変更内容 | 既定動作への影響 | Human Gate位置 |
|---|---|---|---|---|---|
| **P1** | `src/collector.py` | RSS feed URLのenv override（7.5.1a節で完全仕様化） | `NEWS_RSS_FEED_URLS_OVERRIDE`環境変数が設定されている場合のみ、JSON validationを経た16キー完全一致のURL群で`RSS_FEEDS`を置換。未設定時は現行`RSS_FEEDS`のまま完全に無変更 | **未設定時：ゼロ**（既存コードパスと100%同一）。**設定時：production側の意思決定ロジックへの影響はゼロだが、外部入力（どのURLを叩くか）そのものへの影響はゼロではない**（下記「表現の訂正」参照。Round 10で本欄をこの区別と整合させた） | Release 6.35 implementation phase内でのP1着手前に、独立Human Gate承認必須（26章）。**承認後はRelease 6.35自身のimplementationとして実施する（P2とは異なり、Release 6.35のスコープ外へ先送りするものではない）** |

**確定事項（Round 4〜5で維持）**：Scenario Cのcrash injection（10章・6.24〜6.25節）は、production seamを新設しない（10.4節）。したがってP1が唯一のProduction Implementation候補である（Round 1〜3から変更なし）。

**P2の扱い（確定）**：Round 1版で「条件付き・優先度低」としていたScheduler Driver test clock/scheduleフックは、13.2節でF2が直接構築方式（CLIスクリプト非経由）を正式採用したことに伴い、**本Release（6.35）の実装スコープからは完全に除外する**。将来、CLIスクリプト自体の決定的検証が別途必要になった場合にのみ、独立したHuman Gate・別Architecture判断の対象として扱う。

**表現の訂正**：Round 1版の「有効時もproduction decision logic不変」という表現は不正確であったため撤回する。P1は有効化時、**外部入力（どのURLを叩くか）を変更する**——これはproduction側の**意思決定ロジック**を変更するものではないが、外部入力そのものへの影響はゼロではない、と正確に表現する。

### 23.2 Test-only候補（Round 4で更新）

| # | 候補 | 対応シナリオ | 根拠章 |
|---|---|---|---|
| T1 | シナリオA〜F個別のE2Eテストファイル（新規） | A〜F | 8〜13章 |
| T2 | Local Stub HTTPサーバー（WordPress/Anthropic/RSS 3系統対応） | A, B, C | 7.5.5章 |
| T3 | Lock Contention待ち受けヘルパー（lockファイルpolling＋PID生存確認、Polling Contract含む） | F1 | 13.1章 |
| T4（**Round 6で単一worker向けに更新**） | Authoritative Write-Ahead Crash Injectionヘルパー（test-owned`sitecustomize.py`＋`PYTHONPATH`/`WP_OUTPUT_CRASH_SEAM_ENABLED`/`WP_OUTPUT_CRASH_SEAM_SRC_DIR`/`WP_OUTPUT_CRASH_SEAM_EVIDENCE_PATH` env var、`WordPressDraftStateManager.record_confirmed`のclass属性差し替え＋durable evidence marker書き込み、import解決検証込み。単一worker自身の`os.environ`へscoped設定・`finally`復元される4変数として渡される、10.5節。外部polling・`taskkill`は不使用） | C | 10.2章・10.5章・6.24章 |
| T5 | Two-Way Blocking Handshakeワーカー（Scenario D用、`WorkflowEngineManager`直接構築、timing contract確定版） | D | 11.1章 |
| T6（**必須**） | Formal Regression roster機械可読化ファイル（37ファイルの確定リスト） | Formal Regression | 19.1章 |
| T7 | Disposable Project Copy構築ヘルパー（新規構築、既存実装なしと確認済み、exact whitelistベース） | A, B, C, F1 | 7.5.3章 |
| T8（**Round 9でcanonical failure fixture自己完結化を反映**） | Scenario C単一worker subprocessエントリポイント（起動直後に第1位置引数`<Disposable Copy root>`から`sys.path.insert(0, .../src)`＋import解決検証を行うbootstrap（10.5a節）→`AgentConfig`/`WorkflowEngineConfig`から独立構築した`WorkflowEngineManager`でStep 1 canonical run実行（Local Stubが全16 RSSパス0件を返す1回目のレスポンスにより`main.py`が`return 1`で失敗、9章への委譲なし）→`RetryCompositionRoot.from_env(base_dir=<Disposable Copy>)`を1回構築→`RetryRuntimeOrchestrator.from_composition_root()`経由でStep 2 enqueue＋crash-injected actual retryを`run_once()`1回で駆動（Local Stubが1パスのみ1件を返す2回目のレスポンス、crash seam4変数をStep 2直前にscoped設定・`finally`復元）→Step 3で`lineage.reconcile_all()`を再度呼びsuppressionを確認、`RetryRuntimeCycleResult`・`lineage.find_existing_lineage()`・`ReconcileSummary`・`retry_result.outcome`/`authoritative_attempt_no`の結果をtest-owned result fileへ書き出す） | C | 10.2章・10.5章・10.5a章 |
| T9 | `tasklist`/`taskkill`生存確認ヘルパー（追加依存なし。Dの`taskkill`直前liveness確認、F1のlock保持者PID生存確認、F2の1回目のworkerプロセス終了時lock解放確認（`tasklist`でのPID不在確認、13.2節の用語に統一。Scenario Cの旧Worker Phase用語とは無関係）で共有。**Scenario Cは使用しない**（10.5節、単一専用workerによる決定的isolationのみで完結するため）） | D, F1, F2 | 6.21章 |
| T10 | F2用lock所有権付与ハーネス（`RetryRuntimeLock.acquire()`をtest-onlyコードから明示的に呼び、`SchedulerDriverOrchestrator`へ`own_pid`/`lock_path`を渡す） | F2 | 13.2章 |

---

## 24. Round 10 Finding Resolution Matrix

### 24.1 Round 9 Findingsの解決（本改訂の主対象、Round 9は`VERDICT: APPROVED`・Blocking 0／Major 0／Minor 3）

Round 9独立レビューは`APPROVED`（Blocking 0／Major 0）であり、Round 10はMinor 3件のみをeditorial correctionとして反映した。Architecture semantics・scope・仕様の変更はいずれも伴わない。

| Finding | Severity（Round 9） | 解決章 | 解決方法概要 |
|---|---|---|---|
| Minor(1) | Minor | 10.2, 10.5 | canonical execution（空RSS、Step 1）はmain.pyの`return 1`（`:487`）で実行ログ書き込み（`:725`）到達前に終了するため、interval gateを起動しうる実行ログを書き込まないという事実へ訂正した。`NEWS_AGENT_MIN_INTERVAL_MINUTES=0`自体は、他経路での実行ログ存在に備えたdefense-in-depthとして維持した |
| Minor(2) | Minor | 10.2 | exit code 1のtoken名称を`NEWS_OUTCOME_ABNORMAL_EXIT`（誤り）から`NEWS_OUTCOME_GENERIC_FAILURE_EXIT_1`（`_EXIT_CODE_TOKENS`が明示的にマッピングする正しい名称、`news_pipeline_runner.py:56-75`で直接確認）へ訂正した |
| Minor(3) | Minor | 23.1 | P1テーブルの「既定動作への影響：ゼロ」を、「未設定時：ゼロ」「設定時：意思決定ロジックへの影響はゼロだが外部入力への影響はゼロではない」という表現へ書き換え、同節「表現の訂正」段落との矛盾を解消した |

### 24.2 Round 8 Findingsの解決（Round 9で対応済み、記録として維持）

| Finding | Severity（Round 8） | 解決章 | 解決方法概要 |
|---|---|---|---|
| Major 1 | Major | 7.5.1a | hostname分岐2（DNS hostname判定）へ、`hostname.split(".")`の各ラベルが`^[0-9]+$`（数字のみ）または`^0x[0-9a-f]+$`（16進prefix）に一致する場合に拒否する追加規則を導入した。分岐1（strict decimal dotted-quad）は正準表記のIPv4のみを受理し、`127.1`・`2130706433`・`0x7f.0.0.1`のような代替表記はいずれも分岐1の正規表現に一致せず分岐2へ進むが、追加規則により数字のみ・16進prefixのラベルとして拒否される |
| Major 2 | Major | 10.2, 10.5 | `src/collector.py`の`collect_all_news()`・`main.py`の空RSS時`return 1`経路・`src/ai/news_agent.py`の`decide()`interval判定・`src/ai/agent_executor.py`の`should_act=False`時no-op処理を直接確認した上で、Scenario Bへの委譲を撤回し、Local Stubの16パスがcanonical executionでは全て0件・retry executionでは1パスのみ1件を返す2段階fixtureを直接規定した。あわせて`NEWS_AGENT_MIN_INTERVAL_MINUTES=0`をworker起動時envへ追加し、interval gateがretry executionのNEWS step実行を妨げないことを確定した |
| Minor | Minor | 10.5 | `venv/Lib/site-packages/requests/utils.py`の`should_bypass_proxies()`/`get_environ_proxies()`を直接確認し、`requests`は`NO_PROXY`一致時に`getproxies()`を呼ぶ前に自身のbypass判定で完結することを確認した上で、`requests`と`httpx`/`urllib`とで根拠を書き分けた |

### 24.3 Round 7 Findingsの解決（Round 8で対応済み、記録として維持）

| Finding | Severity（Round 7） | 解決章 | 解決方法概要 |
|---|---|---|---|
| Major 1 | Major | 10.5a | workerがDisposable Project Copy外（`tests/`配下）に存在する一方、`src/`配下のproduction moduleを`import`する必要があるという構造を踏まえ、worker script起動時の第1位置引数として`<Disposable Copy root>`を渡し、worker自身の先頭コードで`sys.path.insert(0, str(<root>/"src"))`を行った上で、直接importする4パッケージ（`ai`・`workflow_engine`・`retry_composition`・`retry_runtime_orchestrator`）それぞれについて`Path(module.__file__).resolve().is_relative_to(expected_src)`を検証し、不一致の場合はfail-closedにworkerを終了させる契約を新設した。`PYTHONPATH`には一切依存しない（crash seam専用の予約用途と完全分離） |
| Major 2 | Major | 10.5 | main.py実subprocessが行う3つの外部通信（`requests`・`feedparser`（内部`urllib.request`）・Anthropic SDKの`httpx`）がいずれも標準ライブラリ`urllib.request.getproxies()`（`getproxies_environment() or getproxies_registry()`）へ到達することをソース直接確認し、worker起動時env allowlistへ`NO_PROXY=127.0.0.1,localhost`を追加した。`getproxies_environment()`が非空dictを返すと`or`の短絡評価により`getproxies_registry()`（Windows System Registry参照）が一切呼ばれないという実装を確認し、これによりhost側のsystem proxy設定の有無に関わらずLocal Stubへのloopback通信が保護されることを確定した |
| Major 3 | Major | 7.5.1a | P1のhostname grammarを、「IPv4形状（`^\d{1,3}(\.\d{1,3}){3}$`）の判定を最初に行い、該当すれば`ipaddress.IPv4Address()`でのみ判定しDNS正規表現へは一切fallbackしない」という優先順位付き2分岐へ改めた（`999.999.999.999`がDNS正規表現側を誤って通過する経路を構造的に排除）。あわせて、`parsed.netloc`のuserinfo除去後の残り部分が`":"`で終わる場合（明示的な空port）を、`parsed.port is None`（真の省略）と区別して拒否する条件を追加した |
| Major 4 | Major | 26, 29 | 26章Architecture Gate Checklistを「〜に同意するか」という設問形式から、本書が規定する内容を客観的に記述するacceptance conditionsの形式へ全面的に書き換えた。29章の「次の段階は...ユーザー確認を得ること」という記述を、DRAFTとしての状態を記述する事実文（「本書は現時点でDRAFTであり、Human Gate承認前の状態にある」）へ置き換えた |
| Minor | Minor | 10.5 | Windows subprocess起動に必須の基盤変数を、実際に本プロジェクトのコードが依存する経路（`SystemRoot`・`PATH`の2つ）にexact化した。`TEMP`/`TMP`については、`src/retry_lineage/retry_lineage_store.py`等の`tempfile.mkstemp(..., dir=<明示的なstore dir>)`呼び出しがいずれも`dir=`引数を明示しシステム既定の一時ディレクトリを参照しないことをソース確認し、allowlistに含める根拠がないことを明示した |

### 24.4 Round 6 Findingsの解決（Round 7で対応済み、記録として維持）

| Finding | Severity（Round 6） | 解決章 | 解決方法概要 |
|---|---|---|---|
| B1 | Blocking | 10.5 | `src/ai/agent_config.py`・`src/workflow_engine/workflow_engine_config.py`・`src/workflow_engine/workflow_engine_manager.py`（二重ゲート）・`src/retry_engine/retry_config.py`・`src/retry_engine/retry_manager.py`（三重ゲート）・`src/retry_lineage/retry_lineage_config.py`・`src/retry_lineage/retry_lineage_manager.py`（`claim()`のgate判定）・`main.py`（`ANTHROPIC_API_KEY`必須）・`src/outputs/wordpress_output.py`（`is_available()`の3値AND）を直接確認し、worker起動時env allowlistへ`AI_AGENT_ENABLED`・`WORKFLOW_ENGINE_ENABLED`・`RETRY_ENGINE_ENABLED`・`RETRY_LINEAGE_ENABLED`（いずれも`true`）と`ANTHROPIC_API_KEY`・`WP_USERNAME`・`WP_APP_PASSWORD`（test-only dummy値）を追加した。allowlist方式のため、これら以外の変数（既定「有効」のゲート等）はhost側の値に関わらずコード上の既定値へフォールバックすることも明示した |
| M1 | Major | 6.24, 10.5 | 6.24節の「crash seam4変数はworker自身の起動時環境としてのみ与える」という記述を、10.5節の設計（worker起動時のenvには含めず、`run_once()`呼び出し直前にのみscoped設定し`finally`で復元する）と統一する形へ訂正した。24.5章（Round 5時点の解決記録）にも、その内容がRound 5当時の2-worker構成を指す過去の記録であることを明示する注記を追加した |
| M2 | Major | 10.2 | 「main.py実subprocessの2回目の物理実行」を意味する「attempt 2」という呼称を廃止し、`src/retry_lineage/retry_lineage_manager.py`の`create_new_lineage()`（`:298`、`initial_scope.attempt_no=1`）・`claim()`（`attempt_scopes[-1].attempt_no`をそのまま返す）・`src/retry_engine/retry_executor.py`（`:207`、`attempt_ordinal=claim.attempt_no`）を直接確認した上で、「canonical execution」（lineage作成前の1回目の物理実行）と「retry execution（authoritative `attempt_ordinal=1`）」（lineage内で唯一のretry、2回目の物理実行）という2つの語を新たに定義し、全文の呼称をこれに統一した。Assertion 4のmanifestキー照合にも`attempt_ordinal=1`である旨を明記した |
| m1 | Minor | 7.5.1a | hostname検証を「非空チェックのみ」から、RFC 1123 DNS hostname正規表現またはIPv4 literal（`ipaddress.IPv4Address`）への完全一致のみを受理する閉じたgrammarへ強化し、それ以外（IPv6 literal等）を明示的に拒否した。port検証も、`0`〜`65535`の範囲チェックに加え`port == 0`を明示的に拒否し、有効値を「省略」または`1`〜`65535`に限定した |
| m2 | Minor | 7.5.1a | `main.py:484`が直接`RSS_FEEDS`を参照するかのような記述を、実際の唯一の参照経路である`collector.py`内`collect_all_news()`（`:132-149`、`RSS_FEEDS.items()`を直接iterateする`:146`）を参照する記述へ訂正した |
| m3 | Minor | 10.2 | `src/retry_lineage/retry_lineage_manager.py`の`_reconcile_all_locked()`の成功時return文（`reason`引数を渡さない）と`src/retry_lineage/retry_lineage_results.py`の`ReconcileSummary.reason: str | None = None`という既定値を直接確認し、Assertion 7へ`reason is None`を成功時の必須期待値として追加した |

### 24.5 Round 5 Findingsの解決（Round 6で対応済み、記録として維持）

| Finding | Severity（Round 5） | 解決章 | 解決方法概要 |
|---|---|---|---|
| B1 | Blocking | 10.1, 10.2, 6.16a | Scenario Cの2-worker/Phase handoff構成を撤回。`RetryQueueManager`/`RetryHistoryManager`がプロセスローカルのin-memory dict実装であり別プロセス間で共有され得ないことを実コード（`retry_queue_manager.py:39-41`・`retry_history_manager.py:32-33`）で直接確認し、単一の専用test worker process内でcanonical execution→enqueue→actual retryを連続実行し、in-memory queue/historyをプロセス境界を越えずにそのまま保持する方式へ置き換えた。`retry()`自体はqueue/historyに依存しない（disk-backed lineage/monitorのみ）ことも確認し、durable queue等の新設なしで成立することを示した |
| B2 | Blocking | 6.26, 10.5 | `RetryCompositionRoot.from_env(base_dir=...)`の構築グラフ上でpath override可能な環境変数を`EXECUTION_HISTORY_DIR`・`RETRY_LINEAGE_DIR`の2つに網羅的に絞り込み、`pathlib`の`/`演算子が右辺絶対パスで左辺を破棄する挙動を確認した。単一worker起動時のenvをallowlist方式で構築しこの2変数を含めない契約（10.5節）により、host環境からの絶対パス継承によるauthority漏洩を構造的に排除した |
| M1 | Major | 10.5 | crash seam用4変数の環境分離を、2-worker構成（Round 5）から単一worker内でのscoped設定＋`try`/`finally`復元へ再設計した。worker自身は単一プロセス・単一スレッドであり、Step 2（`run_once()`呼び出し中）以外の時間窓・他の子プロセスへは4変数が到達しない |
| M2 | Major | 10.2 | marker/draft state/manifest/lineage/`WorkflowEngineResult`の5値（member_run_id）を相互照合するAssertion 4へ強化し、marker自身が報告する`wp_post_id`をLocal Stubの実際の応答`id`と突き合わせるAssertion 5を新設した。いずれもproduction APIの戻り値の新規拡張に依存しない |
| M3 | Major | 10.2 | Step 3の`reconcile_all()`呼び出し結果について、`opened_count==0`に加え`skipped is False`を必須assertion対象へ追加し、`ReconcileSummary`の全フィールド（`resolved_count`・`released_count`含む）を一意にassertする契約へ強化した。`RetryExecutionLock` busyによる`skipped=True`（9.3節既存contract）とのfalse success混同を排除した |
| M4 | Major | 7.5.1a | JSON重複キーを`object_pairs_hook`で検出しfail-closedに拒否する契約を追加、Unicode制御文字チェックをC1域（`0x7F`〜`0x9F`）・`Cf`書式文字（双方向テキスト制御文字等）まで拡張、validationを通過した値を`.strip()`後のtrimmed値としてcanonical resultに採用する契約を追加した |
| Minor 1 | Minor | 10.2 | crash seam用env varの個数表記を全文で4個（`PYTHONPATH`・`WP_OUTPUT_CRASH_SEAM_ENABLED`・`WP_OUTPUT_CRASH_SEAM_SRC_DIR`・`WP_OUTPUT_CRASH_SEAM_EVIDENCE_PATH`）に統一した。2-worker構成自体の撤回（B1解決）に伴い、「Worker Phase 1には含めない」という記述自体も本文から除去した |

### 24.6 Round 4 Findingsの解決（Round 5時点の記録として維持）

**（Round 6注記、Round 7・Round 8・Round 9・Round 10でも維持）** 以下はRound 4指摘に対しRound 5が採用した解決内容の**当時の記録**である。B2・M2行が言及する「Worker Phase 2」・「Worker Phase 1/2 subprocess」は、いずれもRound 5時点で採用されていた2-worker/Phase handoff構成（Round 6で撤回、24.4章B1参照）を指す**過去の設計**であり、現行設計（単一専用worker process、10.2節・10.5節・10.5a節、Round 7でworker起動時env allowlistを完全化、Round 8でworker import契約・`NO_PROXY`を追加、Round 9でcanonical failure fixture自己完結化・interval gate無効化・hostname grammar閉包を追加、Round 10でeditorial correctionのみ実施）を表すものではない。現行の解決内容は24.1章（Round 9・APPROVED）・24.2章（Round 8）・24.3章（Round 7）・24.4章（Round 6）を参照すること。

| Finding | Severity（Round 4） | 解決章（Round 5時点） | 解決方法概要（Round 5時点、履歴として維持） |
|---|---|---|---|
| B1 | Blocking | 10.2, 6.24 | 「`PipelineResult.returncode==91`をauthoritative統合経路からassertする」契約を撤回（`NewsAgent`が`returncode`を破棄し`RetryResult`が`WorkflowEngineResult`しか公開しないことを直接確認済み）。代わりに、crash hookがpatch対象の関数へ到達した時点でのみ生成するtest-owned durable evidence marker file（flush/fsync/close完了後に`os._exit(91)`）を確立し、production APIの戻り値に一切依存しない発火証拠とした（この評価点自体はRound 6・Round 7・Round 8・Round 9でも維持。24.4章M2参照） |
| B2 | Blocking | 6.25, 10.2（Round 5時点） | `RetryCompositionRoot.from_env(base_dir=...)`の実装を直接確認し、`base_dir`単一パラメータからexecution_history/lineage/state_dir（draft state・manifest）/agent_config/workflow_engine_configの全てが導出されることを確認。main.pyの`__file__`基準state path解決と`base_dir=<Disposable Copy root>`が導出するpathがバイト単位で一致することを確認し、**（Round 5当時）**Scenario CのWorker Phase 2がこの単一パラメータでRetryExecutorを構築する契約として明示した。durable draft state・manifestの直接照合をAssertionへ追加し「manifest欠如によるfail-closed HRR」という自明化経路を排除した |
| M1 | Major | 7.5.1a | `urlparse()`のscheme正規化（大文字小文字非区別）を回避するため、生の入力文字列に対するcase-sensitiveなprefix比較へ変更。空白・制御文字の直接スキャン、percent-escape正規表現チェック、`.port`アクセスによるポート範囲検証を追加し、Round 4で指摘された全edge caseを塞いだ |
| M2 | Major | 10.5（Round 5時点） | crash seam用env varをテストハーネス自身の`os.environ`へ設定する設計を撤回。**（Round 5当時）**専用のWorker Phase 1/2 subprocessを`subprocess.run(..., env=<明示的に構築したdict>)`で起動し、crash seam関連の4変数はWorker Phase 2自身の起動時environment blockにのみ存在する設計へ変更した。テストハーネス自身の`os.environ`を変更しないという方針自体はRound 6・Round 7・Round 8・Round 9でも維持しているが、具体的な機構は単一worker内でのscoped設定・`finally`復元（10.5節、24.4章M1）へ置き換わっている |
| Minor 1 | Minor | 11.1 | 「`PARENT_READY_DEADLINE_SEC`（5秒）は`HOOK_SAFETY_TIMEOUT_SEC`（30秒）より数桁小さい」という表現を撤回し、正確には約1/6（6倍）であることを明記。false success（レース負けを成功と誤判定すること）を構造的に許さない設計である点を明示的に追加した |
| Minor 2 | Minor | 6.24 | sitecustomize契約に、`sys.path.insert(0, expected_src)`（末尾追加ではなく先頭挿入）、import後の`Path(module.__file__).resolve()`が`expected_src`配下であることの検証、不一致時のfail-closed（patch未適用、evidence marker不在によりAssertionが構造的に失敗する）を追加した |
| Minor 3 | Minor | 23.2, 15 | T9のscenario coverageをD・F1・F2の3シナリオへ統一し、「D/F1のみ」という記述を全文から除去した |

### 24.7 Round 3 Findingsの解決（Round 4から維持）

| Finding | Severity（Round 3） | 解決章 | 解決方法概要 |
|---|---|---|---|
| M3 | Major | 12.1, 12.2 | `open_next_attempt()`の全前提条件（phase・terminal_disposition・attempt_count<max_attempts・next_attempt_ordinal整合・非空unresolved steps）と`reconcile_all()`のlock取得を実コード再読で確認し、E1・E2それぞれのdurable state初期値を`RetryLineageRecord`の全関連フィールドまで一意に固定した |
| M4 | Major | 19.3 | `docs/CHANGELOG.md`の`[KI-33]`エントリおよびFuture Extension節（`:462`）を確認し、baseline `15c45b9...`時点で5ファイル全てが解消済みの過去のKnown Issueであることを確認。「事前に許容されるSKIP/exceptionは1つもない、37/37 PASSが期待値」という単一contractへ19.3・24・26章を統一し、自己矛盾を解消 |
| M5 | Major | 6.22, 13.1, 14.1 | `scripts/run_scheduler_driver.py`を再読し、`NullWorkflowEngineManager`検出時にlockが`finally`節で即座に解放される制御フローを直接確認。F1のPreconditionへ三重ゲート（`SCHEDULER_DRIVER_ENABLED`・`AI_AGENT_ENABLED`・`WORKFLOW_ENGINE_ENABLED`いずれも`true`）を必須化し、lock contentionを構造的に保証する構成へ更新 |
| M6 | Major | 6.23, 13.2 | `SchedulerDriverOrchestrator.run_once()`が`RetryRuntimeLock.acquire()`を自ら呼ばず、lock取得は呼び出し元責務であることを直接確認。F2のtest-only直接構築ハーネスが`run_once()`呼び出し前に自ら`RetryRuntimeLock.acquire()`を呼ぶ契約を明示。既存環境変数`SCHEDULER_DISPATCH_LEDGER_DIR`でdispatch ledgerディレクトリをrestart間で共有する経路を確定し、OI-9も同時に解決 |
| OI-7 | Minor（Round 3 SUGGESTIONS） | 7.5.5, 25.2 | `article_generator.py`・`seo_title_generator.py`・`x_post_generator.py`の3ファイルを直接grep確認し、いずれも`importance_judge.py`と同型の非streaming`client.messages.create(...)`→`.content[0].text`パターンであることを確認。Resolvedへ格上げ |
| OI-8 | Minor（Round 3 SUGGESTIONS） | 6.20, 10.2, 25.2 | `ManifestReaderFacade.list_for_attempt()`が3要素complete keyでファイルを直接特定し、非存在時は例外を送出する構造であることを踏まえ、`engine_result.run_id`を`expected_member_run_id`として渡した呼び出しが成功すること自体が一致の構造的証明になることを確認。Resolvedへ格上げ |
| OI-9 | Minor（Round 3 MAJOR#6内で言及） | 6.23, 13.2 | 既存環境変数`SCHEDULER_DISPATCH_LEDGER_DIR`をrestart間で同一絶対パスに設定する経路を確認。新規production seam不要。Resolvedへ格上げ |

---

## 25. Rejected Alternatives / Open Issues

### 25.1 Rejected（Round 4〜Round 6でScenario Cの検討過程を追加）

- **Scenario C：外部`subprocess.Popen`のtest-scope monkeypatch＋WordPress Draft Stateディレクトリの外部pollingによるkill方式**（Round 4検討・不採用）：`state=="ATTEMPTED"`はwrite-ahead順序上POSTより前に真になるため（6.20節）、この方式ではPOST送信前にkillしてしまうタイミング依存の欠陥がある（10.1節）。10.4節で確定したtest-owned`sitecustomize.py`方式（コード制御フロー由来の決定的機構）を採用する。
- **Scenario C：`PipelineResult.returncode`をauthoritative統合経路（`RetryResult`）からassertする方式**（Round 4採用・Round 5で撤回）：`NewsAgent`が`PipelineResult.returncode`を破棄し（`news_agent.py:91-107`）、`RetryResult`が`WorkflowEngineResult`のみを公開する（`retry_result.py:41-55`）という既存production契約上、この値は統合経路のどこからも観測できないことをRound 4レビュー・Round 5の直接確認で確定した。既存production APIの拡張（新しいフィールドの追加等）による解決は、2章の境界（既存契約を変更しない）に反するため検討しない。10.2節で確定したtest-owned durable evidence marker file方式を採用する。
- **Scenario C：crash seam用env varを2つの専用worker subprocessへ`subprocess.run(..., env=<dict>)`で個別に渡す2-worker/Phase handoff方式**（Round 5採用・Round 6で撤回）：`RetryQueueManager`/`RetryHistoryManager`がプロセスローカルのin-memory実装（6.16a節）であるため、Worker Phase 2が新規構築するqueue/historyはWorker Phase 1のenqueue結果を一切引き継げず、「同じqueue/historyを使う」という要求を実コード上満たせないことをRound 6で確定した（B1）。また2プロセス構成は、`RetryCompositionRoot.from_env(base_dir=...)`が読む`EXECUTION_HISTORY_DIR`/`RETRY_LINEAGE_DIR`のauthority containmentという別の複雑さも抱えていた（B2）。10.2節で確定した単一専用test worker process方式（canonical execution→enqueue→actual retryを同一プロセス内で連続実行）を採用する。
- **Scenario C：crash seam用env varをテストハーネス自身の`os.environ`へ設定しtry/finallyで復元する方式**（Round 4黙示・Round 5で検討・不採用）：テストハーネス自身（pytestプロセス等）へ直接設定する場合、復元漏れ・並行実行時の競合・無関係な子プロセスへの漏洩リスクをtry/finallyだけで完全には排除できない。10.5節で確定した、**単一の専用worker subprocess自身**の`os.environ`へ、そのworkerが単一プロセス・単一スレッドで完結する短い時間窓（Step 2、`run_once()`呼び出し中）にのみscoped設定し`try`/`finally`で復元する方式（テストハーネス自身の`os.environ`は不変のまま）を採用する。テストハーネス自身ではなく専用workerに限定することで、「無関係な子プロセスへの漏洩」を単一プロセス・単一スレッドという構造で排除できる。

### 25.2 Open Issues（Round 4から変更なし）

- **OI-5〜OI-6**：24.7章の通りResolved（維持）。
- **OI-7**：**Resolved（Round 4）**。`article_generator.py`・`seo_title_generator.py`・`x_post_generator.py`の3ファイルを直接grepで再確認し、いずれも`importance_judge.py`と同型の`client.messages.create(model=..., max_tokens=..., messages=[{"role":"user","content":prompt}])`（非streaming）→`message.content[0].text`パターンであることを確認した。
- **OI-8**：**Resolved（Round 4）**。`engine_result.run_id`を`expected_member_run_id`として渡した`get_state()`/`list_for_attempt()`呼び出しが例外を送出せず成功すること自体が、"このmanifestエントリ・draft stateレコードが真にRetryExecutorの払い出した`member_run_id`に紐づく"ことの構造的証明であり、別途フィールド比較を行う事後照合ロジックを新規に組む必要はない。Round 5の10.2節Assertion 4は、この構造的証明に加え、durable draft state/manifestの内容を直接readする追加照合を規定した。
- **OI-9**：**Resolved（Round 4）**。13.2節・6.23節の通り、既存環境変数`SCHEDULER_DISPATCH_LEDGER_DIR`に、restartの1回目・2回目双方が同一の絶対パスを設定することで、新しいproduction seamを追加せずにdispatch ledgerディレクトリを共有できることを確認した。

**（Round 10時点で残存するOpen Issueなし。Round 9はCodex `VERDICT: APPROVED`（Blocking 0／Major 0／Minor 3）であり、そのMinor 3件は24.1章のResolution Matrixでeditorial correctionとして解決済み。Round 8のMajor/Minorは24.2章の、Round 7のMajor/Minorは24.3章の、Round 6のBlocking/Major/Minorは24.4章の、Round 5のBlocking/Major/Minorは24.5章のResolution Matrixで解決済み。）**

---

## 26. Architecture Gate Checklist（Round 8で客観的acceptance conditionsへ書き換え、Round 9で内容更新）

以下は、本書がArchitecture Releaseとして満たすべきacceptance conditionsを列挙したものである（Round 7までの「〜に同意するか」という設問形式から、本書自身が満たす／満たさないを機械的に判定できる客観的条件の記述へRound 8で書き換えた。各条件の成否はHuman Gateでの承認判断の材料となる）。

1. **P1仕様の完全性**：7.5.1a節は、P1（RSS feed URL override）の完全仕様（env名・schema・JSON重複キーの`object_pairs_hook`によるfail-closed拒否・`urllib`/`re`/`unicodedata`/`ipaddress`ベースのvalidation——case-sensitiveなscheme prefix比較・空白/Unicode制御文字（C0・C1・`Cf`書式文字）チェック・IPv4形状判定を先行させたIPv4 literal／RFC 1123 DNS hostname正規表現への閉じたgrammar一致（それ以外全拒否）・percent-escape検証・port `1`〜`65535`限定（`0`および明示的空port拒否）・trimmed値のcanonical result採用を含む・fail-closed挙動）を規定している。本条件はArchitecture設計としての内容の完全性を指すものであり、P1の実装自体は別途独立したHuman Gateを要する（本条件はその代替ではない）。
2. **Disposable Project Copyの位置づけ**：7.5.3節は、Disposable Project Copyを「既存実装の再利用」ではなく「新規test-only helperとして新規構築する」という訂正済みの位置づけ、closed-world exact whitelist（`src/`・`scripts/`・`main.py`・`.env.example`・`requirements.txt`・`prompts/`の6項目のみ）、およびOriginal Project側をfull-tree検査へ拡張したZero-Diff証拠契約・Disposable Copy自体の破棄条件を規定している。
3. **Scenario Cの単一worker統合設計**：10章は、Tier 1/Tier 2の2層分離（Round 3以前）、および2-worker/Phase handoff構成（Round 5）をいずれも撤回し、**単一の専用test worker process内でcanonical execution→enqueue→actual retryを連続実行し、test-owned`sitecustomize.py`＋durable evidence marker＋`RetryCompositionRoot.from_env(base_dir=<Disposable Copy>)`によるproduction seamレスの単一統合設計**（main.py実subprocess自身の内部で`record_confirmed()`呼び出しをhard-crashへ置き換え、crash hook自身が到達証拠をtest-owned marker fileへ残す、コード制御フロー由来の決定的機構）を規定している。あわせて、当該workerが同一の`RetryCompositionRoot`インスタンス（in-memory queue/history含む）をenqueueとactual retryの両方で共有する設計（6.16a節・10.2節）、crash seam用4変数をworker自身の`os.environ`へStep 2直前にscopedに設定し`try`/`finally`で復元することでテストハーネス自身の`os.environ`を変更しないenvironment isolation設計（10.5節）、`EXECUTION_HISTORY_DIR`/`RETRY_LINEAGE_DIR`をworker起動時envのallowlistから除外するauthority containment契約（6.26節・10.5節）、worker起動時env allowlistが必須Feature Gate4個・`NEWS_AGENT_MIN_INTERVAL_MINUTES=0`（interval gate無効化）・stub認証情報3個・`NO_PROXY`を明示的に含むexact contract（10.5節）、workerが`<Disposable Copy>/src`を最優先でimport解決しoriginal tree／installed packageへの誤解決をfail-closedに検出するbootstrap契約（10.5a節）、Scenario B（9章）への依存を撤回しScenario C自身が完結する2段階RSS fixture（canonical executionは全16パス0件、retry executionは1パスのみ1件）を規定するcanonical failure injection契約（10.2節）、および「canonical execution」と「retry execution（authoritative `attempt_ordinal=1`）」を区別する呼称統一（10.2節）を規定している。
4. **Scenario Dのtiming contract**：11章は、Scenario DのTwo-Way Blocking Handshake設計、および`PARENT_READY_DEADLINE_SEC`（5秒）が`HOOK_SAFETY_TIMEOUT_SEC`（30秒）の約1/6であるというbounded deadline関係・`taskkill`直前の最終liveness確認を規定している。
5. **Scenario Eのfixture確定**：12章は、Scenario Eをlegacy lineageのみの単一構成に固定する判断、およびE1/E2のfixture前提条件（`max_attempts`・`attempt_scopes`・`steps_confirmed_done`等の全フィールド値）を規定している。
6. **Scenario Fの分離**：13〜14章は、Scenario FのF1（Disposable Project Copy内での実CLI/lock検証、**三重ゲート必須化**）／F2（direct-injection、restart証跡必須、**test-only直接構築ハーネスによる`RetryRuntimeLock`明示取得**）分離、既存環境変数`SCHEDULER_DISPATCH_LEDGER_DIR`によるdispatch ledger共有、およびP2を6.35スコープから除外する判断を規定している。
7. **Formal Regressionの単一contract**：19章は、確定した37-file roster、機械可読capture必須化、および**`[KI-33]`を含め事前に許容されるSKIP/exceptionが1つもない（37/37 PASSが期待値）という単一contract**を規定している。
8. **Production Implementation候補の確定**：23.1節は、P1を**Release 6.35 implementation phaseの一部として**Human Gate承認後に実施するProduction Implementation候補として残し（Release 6.35スコープ外への先送りではない）、P2を本Release（6.35）自体のスコープから完全に除外するという区別された最終判断、およびScenario Cが新規production seamを一切要しない（production変更候補はP1のみ）という結論を確定している。
9. **Open Issuesの解消状態**：25.2節は、OI-7・OI-8・OI-9がいずれもResolvedである（実装フェーズでの追加確認は不要）という判断を記録している。

---

## 27. Acceptance Criteria（Round 1版を維持、Round 9の変更を反映）

- シナリオA〜Fそれぞれが7章の6項目フォーマットに沿った個別contractとして定義されていること
- 各シナリオが実Runtime経路を使用し、production側の意思決定ロジックを変更しないtestability seam（P1、opt-in・既定動作不変）以外でproduction codeを変更していないこと
- Scenario Cが、**単一の専用test worker process内**で完結する統合実行チェーン（10.2節のcanonical execution→enqueue→actual retry）で「RetryExecutor所有attemptがwrite-ahead crash windowでcrashし、durable HUMAN_REVIEW_REQUIREDへ到達し自動retryが抑止される」という合成claimを、**外部プロセスのタイミング推測にも既存production APIの戻り値の新規拡張にも依存しない決定的機構**（test-owned durable evidence marker、`RetryCompositionRoot.from_env(base_dir=...)`による同一state領域への結合、同一queue/historyインスタンスの単一プロセス内共有）で直接証明し、production seamを新設しないこと（Tier 1/Tier 2の2層分離、および2-worker/Phase handoff構成はいずれも撤回済み）
- Scenario Cのcrash seam用4環境変数が、テストハーネス自身の`os.environ`ではなく単一の専用worker process自身の`os.environ`に対し、actual retry呼び出し直前という限定された時間窓にのみscoped設定・`try`/`finally`で復元され、無関係な子プロセスへ漏洩しないこと（10.5節）
- Scenario Cのworker起動時envが、`EXECUTION_HISTORY_DIR`/`RETRY_LINEAGE_DIR`をallowlistから除外し、host環境からの絶対パス継承によるDisposable Project Copy外へのauthority漏洩を排除すること（6.26節・10.5節）
- Scenario Cのmarker/draft state/manifest/lineage/`WorkflowEngineResult`の5値相互照合、およびmarker `wp_post_id`とLocal Stub応答の一致確認が、Durable/Observable Assertionsに含まれること（10.2節）
- Scenario Cのautomatic retry suppression確認が、`reconcile_all()`の`opened_count==0`だけでなく`skipped is False`を含む`ReconcileSummary`全フィールドの一致で行われ、`RetryExecutionLock` busyによるfalse successを排除すること（10.2節）
- Scenario Cのworkerが、`<Disposable Copy>/src`を最優先でimport解決し、original tree・installed packageへの誤解決をfail-closedに検出するbootstrap契約を持つこと（10.5a節）
- Scenario Cのworker起動時env allowlistが`NO_PROXY=127.0.0.1,localhost`を含み、Local Stubへのloopback通信がWindows system proxy経由で迂回されないことが実クライアント挙動に基づき確定していること（10.5節）
- Scenario Cのenqueue/dispatch/execution件数がちょうど1件であることの確認、`RetryOutcome.RETRIED`の確認、canonical run IDと`RetryResult.original_run_id`・lineage root IDの一致確認が、Durable/Observable Assertionsに含まれること（10.2節）
- Scenario Cのcanonical NEWS失敗fixtureが、未記載のScenario B手順への委譲なしに自己完結的に規定されており、Local Stub側の決定的な2段階レスポンス（canonical executionは全16パス0件、retry executionは1パスのみ1件）として実装可能であること（10.2節）
- Scenario Cのworker起動時envが`NEWS_AGENT_MIN_INTERVAL_MINUTES=0`を含み、`NewsAgent`のinterval gateによりretry execution側のNEWS step実行が成功扱いのno-opとしてスキップされる可能性が構造的に排除されていること（10.5節）
- P1のhostname grammarが、strict decimal dotted-quad以外のIPv4代替表記（短縮形・10進整数一括表記・16進octet表記）をDNS hostname分岐へfallbackさせず一貫して拒否すること（7.5.1a節）
- Scenario Dのcrash injectionが、コードの制御フローから直接導かれるrace-freeな設計（Two-Way Blocking Handshake、hook self-timeoutと親deadlineの数値関係が明確）であること
- Scenario Dのtaskkillベースのcrash injectionが、raceに負けた場合を検出してtiming failureとして明示的にテストを失敗させる自己検証を含むこと（黙って無関係な成功を報告しないこと）
- failure-path再検証5項目（16章）が、既存の正確なテストファイル・テスト番号・機構・アサーションで裏付けられていること
- シナリオFのF1がgenuine concurrency（lockファイルpolling手法、三重ゲート必須）でsecond driver同時起動を検証し、F2がrestart証跡・明示的なlock所有権取得を含む決定的なdispatch検証を行うこと
- MVP Definition of DoneとシナリオA〜Fの対応関係（17章）に漏れがないこと
- Accepted Risk（20章）・Staged Activation Gate（21章）との関係が明示され、いずれも本Releaseで変更されないことが明記されていること
- Production Implementation候補（23.1節）がP1のみに確定し、実装フェーズ着手前に独立のHuman Gate承認が必要であることが明記されていること
- Windows環境でのプロセス協調・crash injection・cleanupが、POSIX前提の暗黙の仮定なしに決定的であること、かつ`psutil`のような本プロジェクトに存在しない依存へ暗黙に依拠していないこと（`tasklist`/`taskkill`はD・F1・F2で使用、Scenario Cは専用worker subprocessによるproduction seamレスのcrash injectionのため使用しない）が、各該当シナリオのcontractで明示されていること
- 各シナリオのDurable/Observable Assertionsが、そのシナリオの実Runtime経路が実際に主張する境界へ到達したことを直接証明する項目を含むこと
- Formal Regressionの期待結果が、事前に許容されるSKIP/exceptionのない37/37 PASSであり、`[KI-33]`が単なる履歴的コンテキストとしてのみ扱われ、現役の免除カテゴリとして扱われていないこと
- 本書自体が`src`/`scripts`/`tests`のいずれも変更していないこと（0章）
- 本書の記述に、レビュー主体へ向けたtask-directedなmeta-textが含まれていないこと

---

## 28. 参照

- `docs/design/production_canonical_run_outcome_contract_foundation.md` §29「Verification isolation」（Disposable Project Copyの設計思想の一次情報源、実装は存在しないことを確認済み）
- インストール済みAnthropic SDK・python-dotenvのソース（`inspect.getsource()`による直接確認）
- `src/importance_judge.py`・`src/article_generator.py`・`src/seo_title_generator.py`・`src/x_post_generator.py`（Anthropic呼び出しの直接確認、OI-7）
- `src/retry_engine/retry_executor.py`・`src/workflow_engine/workflow_engine_executor.py`・`src/workflow_engine/workflow_engine_result.py`・`src/side_effect_safety/side_effect_execution_mode.py`（RetryExecutor制御フロー・post_admission_hook契約・disposition決定ロジックの直接確認）
- `src/retry_lineage/retry_lineage_manager.py`・`retry_lineage_target_resolution.py`・`retry_lineage_genuine_action.py`・`retry_lineage_record.py`・`retry_lineage_results.py`（reconcile_all()ロジック・record/summary schemaの直接確認）
- `src/pipeline/news_pipeline_runner.py`（main.py実subprocess起動経路・env継承・reserved exit codeの直接確認、Round 4、B1）
- `src/outputs/wordpress_output.py`・`src/wordpress_draft_state/wordpress_draft_state_manager.py`・`wordpress_draft_state_store.py`・`src/side_effect_safety_classifier.py`（write-ahead書き込み順序・POST成功ゲート・key構造・IN_PROGRESS_OR_UNKNOWN判定の直接確認、Round 4、B1）
- `main.py`（`sys.path.insert()`のタイミング・`-S`/`-I`フラグ不使用・state path解決（`:94,96,104`）の直接確認、Round 4/5、B1/B2）
- プロジェクトのvenv（Python 3.14.6）上でプロジェクト外に構成した`sitecustomize.py`最小再現実験（PYTHONPATH経由の自動import・class属性monkeypatch・`os._exit()`の実測確認、Round 4、B1）
- `src/retry_composition/retry_composition_root.py`（`RetryCompositionRoot.from_env(base_dir=...)`の全構築ロジックの直接確認、Round 5、B2）
- `src/retry_engine/retry_result.py`（`RetryResult`が`returncode`を公開しないことの直接確認、Round 5、B1）
- `src/retry_engine/retry_manager.py`（`RetryManager.retry()`のシグネチャ直接確認、Round 5）
- `src/retry_lineage/retry_lineage_manager.py`（`find_existing_lineage()`の直接確認、Round 5、B1）
- `src/ai/news_agent.py`（`NewsAgent`が`PipelineResult.returncode`を保持しないことの直接確認の根拠、Round 4 Codexレビューで指摘、Round 5、B1）
- `src/protected_operation_manifest/protected_operation_manifest_facades.py`・`protected_operation_manifest_store.py`（manifest key構造・`list_for_attempt()`の直接確認、OI-8）
- `scripts/run_scheduler_driver.py`・`src/scheduler_driver/scheduler_driver_orchestrator.py`・`scheduler_driver_lock_integrity.py`・`src/retry_runtime_lock/retry_runtime_lock.py`・`src/scheduler_dispatch_ledger/scheduler_dispatch_ledger_config.py`（lock取得タイミング・Triple-Gate・`run_once()`所有権契約・dispatch ledger共有経路の直接確認、M5/M6/OI-9）
- `docs/CHANGELOG.md`（`[KI-33]`エントリおよびFuture Extension節`:462`の直接確認、M4）
- `requirements.txt`・プロジェクトvenv（`psutil`が依存として存在しないことの直接確認、B2・D/F1/F2の`tasklist`/`taskkill`採用根拠）
- プロジェクトルート直下の実ディレクトリ構成（`ls`による直接確認、M2）
- `src/retry_queue/retry_queue_manager.py`・`src/retry_queue/retry_queue_config.py`（`RetryQueueManager`がin-memory dict実装であることの直接確認、Round 6、B1）
- `src/retry_history/retry_history_manager.py`（`RetryHistoryManager`がin-memory dict実装であることの直接確認、Round 6、B1）
- `src/retry_enqueue_trigger/retry_enqueue_trigger.py`（`enqueue_pending_failures()`のmonitor走査・queue書き込み経路の直接確認、Round 6、B1）
- `src/retry_engine/retry_manager.py`（`retry()`/`_retry_locked()`がqueue/historyに依存しないことの直接確認、Round 6、B1）
- `src/retry_runtime_orchestrator/retry_runtime_orchestrator.py`（production正規経路`run_once()`が単一プロセス内でenqueue→dispatch→executeを完結させることの直接確認、Round 6、B1）
- `src/execution_history/execution_history_config.py`・`src/retry_lineage/retry_lineage_config.py`（`EXECUTION_HISTORY_DIR`/`RETRY_LINEAGE_DIR`のpath override機構、および`project_root / dir_name`の絶対パス優先挙動の直接確認、Round 6、B2）
- `src/ai/agent_config.py`・`src/workflow_engine/workflow_engine_config.py`（path override機構を持たないことの直接確認、Round 6、B2）
- `src/article_media_upload_state/article_media_upload_state_config.py`（`ARTICLE_MEDIA_UPLOAD_STATE_DIR`がScenario Cの呼び出しグラフに現れないことの直接確認、Round 6、B2）
- `src/wordpress_draft_state/wordpress_draft_state_manager.py`（`record_confirmed(identity, member_run_id, wp_post_id)`のシグネチャ直接確認、Round 6、M2）
- `src/retry_lineage/retry_lineage_manager.py`（`mark_execution_started()`が`record.latest_run_id`をdurableに確定させることの直接確認、Round 6、M2）
- `src/workflow_engine/workflow_engine_manager.py`（`from_config()`の二重ゲート判定・NEWS step無条件構築の直接確認、Round 7、B1）
- `src/retry_engine/retry_config.py`・`src/retry_engine/retry_manager.py`（`from_config()`の三重ゲート判定の直接確認、Round 7、B1）
- `src/retry_lineage/retry_lineage_manager.py`（`claim()`が`RETRY_LINEAGE_ENABLED`のfail-closedゲートを持つことの直接確認、Round 7、B1）
- `main.py`（`ANTHROPIC_API_KEY`未設定時の`return 1`・`anthropic.Anthropic(api_key=...)`構築箇所の直接確認、Round 7、B1）
- `src/outputs/wordpress_output.py`（`is_available()`が`site_url`/`username`/`app_password`の3値ANDであることの直接確認、Round 7、B1）
- `src/retry_lineage/retry_lineage_manager.py`（`create_new_lineage()`の`initial_scope.attempt_no=1`初期化の直接確認、Round 7、M2）
- `src/retry_engine/retry_executor.py`（`attempt_ordinal=claim.attempt_no`の伝播の直接確認、Round 7、M2）
- `src/collector.py`（`collect_all_news()`内`RSS_FEEDS.items()`参照箇所の直接確認、Round 7、m2）
- `src/retry_lineage/retry_lineage_results.py`（`ReconcileSummary.reason`の既定値`None`の直接確認、Round 7、m3）
- `main.py`（`sys.path.insert(0, str(Path(__file__).parent / "src"))`の直接確認、Round 8、Major 1）
- `src/retry_engine/retry_result.py`（`RetryOutcome`enum・`RetryResult.original_run_id`/`authoritative_attempt_no`フィールドの直接確認、Round 8、Codex suggestion）
- `src/retry_engine/retry_executor.py`（`original_run_id=lineage.root_run_id`の直接確認、Round 8、Codex suggestion）
- `src/retry_engine/retry_execution_coordinator.py`（`RetryExecutionResult.retry_result`フィールドの直接確認、Round 8、Codex suggestion）
- `src/retry_enqueue_trigger/retry_enqueue_trigger.py`（`RetryEnqueueTriggerResult.enqueued`フィールドの直接確認、Round 8、Codex suggestion）
- `src/retry_lineage/retry_lineage_store.py`（`tempfile.mkstemp(..., dir=...)`が明示的`dir`引数を渡すことの直接確認、Round 8、Minor）
- `src/outputs/wordpress_output.py`（`import requests`の直接確認、Round 8、Major 2）
- `src/collector.py`（`feedparser`使用の直接確認、Round 8、Major 2）
- インストール済み`venv/Lib/site-packages/httpx/_utils.py`（`get_environment_proxies()`の直接確認、Round 8、Major 2）
- Python標準ライブラリ`urllib.request`（`getproxies()`・`getproxies_environment()`のソース直接確認、`getproxies_environment() or getproxies_registry()`の短絡評価の直接確認、Round 8、Major 2）
- インストール済み`venv/Lib/site-packages/anthropic/_base_client.py`（`trust_env`のkwarg受け渡し箇所の直接確認、Round 8、Major 2）
- `src/collector.py`（`collect_all_news()`の16フィード集約ロジックの直接確認、Round 9、Major 2）
- `main.py`（空RSS時の`return 1`経路の直接確認、Round 9、Major 2）
- `src/ai/news_agent.py`（`NewsAgent.decide()`のinterval判定ロジックの直接確認、Round 9、Major 2）
- `src/ai/news_agent_config.py`（`NEWS_AGENT_MIN_INTERVAL_MINUTES`既定値`180`の直接確認、Round 9、Major 2）
- `src/ai/agent_executor.py`（`should_act=False`時の成功扱いno-op処理の直接確認、Round 9、Major 2）
- `src/retry_enqueue_trigger/retry_enqueue_trigger.py`（`_RETRY_TARGET_STATUSES`定義の直接確認、Round 9、Major 2）
- `venv/Lib/site-packages/requests/utils.py`（`should_bypass_proxies()`・`get_environ_proxies()`のソース直接確認、Round 9、Minor）
- （Round 1版の参照は全て維持）

---

## 29. Architecture Releaseとして開始可能かの判定

Round 9改訂は、Round 8レビュー（`VERDICT: NOT APPROVED`、Blocking 0／Major 2／Minor 1）で指摘された全項目（Major 1〜2・Minor 1）への対応を反映した。P1のhostname grammarへ、`hostname.split(".")`の各ラベルが数字のみ（`^[0-9]+$`）または16進prefix（`^0x[0-9a-f]+$`）である場合の追加拒否規則を導入し、`127.1`・`2130706433`・`0x7f.0.0.1`のような、strict decimal dotted-quad以外のIPv4代替表記がDNS hostname分岐を素通りする経路を閉じた（7.5.1a節、Major 1解決）。Scenario Cのcanonical NEWS失敗fixtureを、未記載のScenario B（9章）手順への委譲を撤回し、Local Stubの16個のRSSパスがcanonical executionでは全て0件・retry executionでは1パスのみ1件を返すという2段階レスポンスとして自己完結的に規定した。あわせて、`NewsAgent.decide()`の既定180分interval gateがretry execution側のNEWS step実行を「成功扱いのno-op」としてスキップさせてしまうリスクを`src/ai/news_agent.py`・`src/ai/agent_executor.py`の直接確認により特定し、`NEWS_AGENT_MIN_INTERVAL_MINUTES=0`をworker起動時envへ追加してこのリスクを構造的に排除した（10.2節・10.5節、Major 2解決）。`NO_PROXY`の効き方に関する説明を、`requests`固有の`should_bypass_proxies()`（`getproxies()`呼び出し前にbypassを確定させる）と、`httpx`/`urllib`が依拠する`getproxies()`の短絡評価とで書き分け、過度な一般化を解消した（10.5節、Minor解決）。

**Round 9独立レビュー（Codex `codex-readonly-review`、Codex High、fresh-thread）の結果：`VERDICT: APPROVED`（Blocking 0／Major 0／Minor 3）。** Minor 3件はいずれも編集上の事実誤認であり、設計・scope・contractの変更を要しないものだった：(1) canonical execution（空RSS）が実行ログを書き込みinterval gateを起動しうるという記述の不正確さ（main.pyは実行ログ書き込み前に`return 1`する）、(2) exit code 1の名称誤り（正しくは`NEWS_OUTCOME_GENERIC_FAILURE_EXIT_1`）、(3) P1の「既定動作への影響：ゼロ」という表現が、同節内の「表現の訂正」段落（外部入力への影響はゼロではない）と矛盾していたこと。Round 10改訂は、この3件をArchitecture semantics・scope・仕様を一切変更せずにeditorial correctionとして反映した（10.2節・10.5節・23.1節）。

**現在の状態**：Architecture Gate Checklist（26章）9条件・Acceptance Criteria（27章）はいずれもPASS（Round 10でのread-only最終確認済み）。Blocking／Major／Open Issueは残存しない（25.2節）。Production Implementation候補はP1のみに確定しており、P1実装着手前の独立Human Gate承認が必須である（23.1節・7.5.1a節）。scope-change Gateは不要（新規Foundation・durable authority変更・既存contractの変更のいずれにも該当しない、10.4節）。実装フェーズ（P1・Scenario A〜Fのtest実装を含む）は、本書に対するHuman Gate承認を得た後、別フェーズとして開始する。

**（Post-Round 10 Amendmentによる追記）** 上記の実装フェーズはその後Human Gate承認を得て実施され、完了した。その実装結果とArchitecture本文とのread-only reconciliationを経た本Amendmentの内容は30章に記録する。29章本文（本節）自体はRound 10時点の判定として歴史的記録のまま維持し、書き換えない。

---

## 30. Release 6.35 Implementation Reconciliation Amendment（Post-Architecture-Approval；本章はRelease 6.35着手からの時系列履歴を記録する。各節はその節が執筆された時点の状態を記す歴史的記録であり、本章内のいずれの節も「現在の状態」の参照先としない——Current Statusの正本は常に0章である）

### 30.1 本章の位置づけ

P1（7.5.1a節）およびScenario A〜Fのtest実装フェーズ（8〜13章）は、いずれも独立Human Gate承認を得た上で実施され、完了した。本章は、その実装結果とArchitecture本文（本書）とのread-only reconciliation（Human-directed、実装コード・設計書のいずれも変更しない照合作業）の結果、Architecture本文側に反映が必要と判明した差分を、Amendmentとして確定した記録である。

**本章起筆時点（30.1節執筆時）では、本章およびこのAmendmentが変更した各節（7.5.4節・8章・9章・10.5節(a)・13.1節・本節）は、Round 1〜10とは異なり、Codex `codex-readonly-review`による独立レビューをまだ経ていなかった。** 実装が先行して明らかにした事実をArchitecture本文へ反映しただけの、read-only investigationに基づく編集だった。30.5節は、その時点で未解決だったCodex独立レビュー対象の懸念事項を記録したものであり、これらは後続のCodex delta review #1（30.6節）で確認された。

### 30.2 Amendmentの経緯

1. P1・Scenario A〜Fのtest実装（すべてtest-only、production側は`src/collector.py`のP1実装のみ）が完了し、全139件のtargeted E2E checkがPASSした。
2. 実装結果を設計書と照合するread-only reconciliationを実施し、以下4点の差分を確認した：①8章・9章の契約本文が実際には本書に存在しなかったこと（Round 1版以来の空白）、②Windows worker/test env allowlistの実測不足（`APPDATA`欠落によるAnthropic SDKクラッシュ）、③`PYTHONIOENCODING=utf-8`が本書に明記されないまま必要だったこと（ただし既存17ファイルで確立済みの慣行であり本Releaseの新規発見ではない）、④Scenario F1でのPID実測差異。
3. 本Amendmentは、上記4点をArchitecture本文へ反映する。

### 30.3 Architecture semantics/scopeへの影響（変更なし）

本Amendmentは、2章が定める境界（新規Foundation・`release_claim()` Suggestion・Accepted Risk解消・Manual Recovery専用CLI・production activation等は対象外）を一切変更しない。具体的に：

- **Production Implementation候補は引き続きP1のみ**（23.1節）。本Amendmentでもこれ以外のproduction変更（P2・新規Foundation・既存contractの変更）は一切行っていない。`git diff --stat`で確認した限り、tracked fileへの変更は`src/collector.py`（P1実装そのもの、110行追加・1行削除）のみである。
- 本Amendmentが変更した7.5.4節・8章・9章・10.5節(a)・13.1節は、いずれも**test-onlyの契約記述**（worker/test env allowlistの構成・E2Eシナリオの契約本文・F1のassertion本文）であり、production側の意思決定ロジック・durable authority・既存contractのいずれも変更しない。
- したがって10.4節の判定（scope-change Gate不要）は本Amendmentにも引き続き適用される。

### 30.4 Amendment内容の要約

| # | 対象節 | 変更内容 | 根拠 |
|---|---|---|---|
| 1 | 8章 | Scenario Aの契約本文（Precondition/Runtime Path/Failure Injection/Durable-Observable Assertions/Prohibited Outcome/Isolation-Cleanup）を新規に確定 | 7章・7.5節・6.19/6.20節からの導出＋実装による実証 |
| 2 | 9章 | Scenario Bの契約本文を新規に確定（空RSS→retry成功fixtureの転用・ScopedEnv方式・observability/automatic retry suppressionのassertionを明文化） | 同上＋6.16a/6.25/6.26節 |
| 3 | 7.5.4節 | 「A・B・F1を一括り」という記述を撤回し、A/F1（closed allowlist subprocess env）・B（ScopedEnvによるtest process envの一時変更＋`try`/`finally`復元）・C/D/F2（既存worker契約、10.5/11.1/13.2節）の3方式へ整理 | 実装実態の確認 |
| 4 | 10.5節(a) | Windows基盤変数を`SystemRoot`・`PATH`の2変数から`SystemRoot`・`PATH`・`APPDATA`の3変数へ訂正。`PYTHONIOENCODING=utf-8`をtest subprocess契約として明記 | Anthropic SDK資格情報自動探索機能の実測クラッシュ／既存17ファイルでの確立済み慣行の確認 |
| 5 | 13.1節 | F1のDurable/Observable Assertionsを「lockファイル記載PIDの生存」＋「2つ目のdriverのfail-closed終了」へ確定し、`proc.pid`との一致を安全性contractの要件から除外。PID実測不一致をtest-environment varianceとして記録 | lock contract（`RetryRuntimeLock.acquire()`のOSレベル排他性）の再確認 |
| 6 | 0章・29章・本節 | 本Amendmentの履歴化 | — |

### 30.5（当時の記録）30.1〜30.4節執筆時点でCodex独立レビュー未実施のまま残っていた懸念事項（後にdelta review #1で確認、30.6節参照）

30.1〜30.4節執筆時点（Codex delta review #1着手前）で、以下がCodex独立レビュー未実施のまま残っていた懸念事項だった：

1. **8章・9章の契約本文全体**——今回初めて具体的に書き起こされたものであり、Round 1〜10のいずれの独立レビューも経ていなかった。
2. **10.5節(a)への`APPDATA`追加の妥当性**——containment/safety境界に影響しないという評価が、独立レビューで未検証だった。
3. **7.5.4節の3方式整理**——特にB方式のScopedEnvが、A/F1のclosed allowlist方式と同等の安全性を持つかどうかが未評価だった（Bは`{**os.environ,...}`経由の間接継承であり、A/F1の直接allowlistよりホスト環境漏洩の可能性がわずかに大きい非対称性があった）。
4. **13.1節のF1 PID contract変更**——duplicate-driver safetyの証拠強度が実際に低下していないかが未評価だった。
5. Scenario C・D・F2の契約自体（10章・11章・13.2章）は本Amendmentで変更していなかったが、実装済みコードとの1:1対応については未レビューだった。

これらの懸念事項は、A〜F全体を対象として実施されたCodex delta review #1（30.6節）で確認された。

### 30.6 第2回Reconciliation（Codex delta review #1の結果を反映）

30.5節が記録した懸念事項に基づき、`codex-readonly-review`（Codex High、fresh-thread）によるdelta reviewを実施した結果は`VERDICT: NOT APPROVED`（Blocking 0／Major 5／Minor 4）だった。以下、指摘事項ごとの対応内容を記録する。**本節執筆時点では、本節が記録する対応自体はまだ独立したCodex delta reviewを経ていなかった**（当時の懸念事項は30.7節に記録し、これらは後にdelta review #2で確認された、30.8節参照）。

**Major対応**：
1. **Scenario B/DのExactEnv化**：Scenario Bのenv方式を`ScopedEnv`（overlay）から`ExactEnv`（`os.environ`の完全置換、7.5.4節で確定）へ変更した。Scenario Dのretry eligibility判定フェーズ（11.1節のhandshake自体ではなく、その後のretry実行部分）も同様に`ExactEnv`へ変更した。
2. **Scenario Bのfallback非発動assertionの観測source訂正**：Anthropicへの HTTPリクエストbody検索を撤回し、main.py実subprocess自身のstdout log（`<copy root>/logs/news_agent/*_stdout.log`）を検索する方式へ変更した（7.5.5節・9.1節に反映済み）。
3. **APPDATAの供給元訂正**：host実値からscenario-owned empty directoryへ変更した（10.5節(a)に反映済み）。全シナリオ（A・C・D・F1・F2の各env構築、およびB・Dの`ExactEnv`構成）に適用した。
4. **Scenario F2のdispatch ledger dir構成訂正**：`SchedulerDispatchLedgerConfig`のdirect dataclass構築を撤回し、`SCHEDULER_DISPATCH_LEDGER_DIR`環境変数経由の`from_env()`へ変更した（13.2節の既存契約どおり）。あわせて、dispatch ledgerストア自体を直接読み取り、対象event_identityについてCLAIMED→CONFIRMEDの単一entryのみが存在することを明示的にassertするよう変更した。
5. **Local Stub（WordPress）の認証/payload検証追加**：POST受理・成功応答の返却前に、Basic認証ヘッダの一致・必須payload（`title`・`content`・`status`・`excerpt`・`slug`）の存在・`status`固定値の一致をfail-closedに検証するよう変更した（7.5.5節に反映済み）。不一致の場合は401（認証）または400（payload）を返し、拒否理由を記録する。全シナリオ（A・B・C・D・F2）が、この検証で拒否された事例が無いことを明示的にassertするよう変更した。

**Minor対応**：
1. **F1のPID contract整合**：lockファイル記載PIDを、2つ目のdriver起動の**前後とも**再読して生存確認するよう変更した（従来は起動前のみ）。あわせて、設計書側の「`_verify_lock_ownership`はF2専用」という誤記を訂正した（13.1節に反映済み、実際は`scripts/run_scheduler_driver.py`自身も同関数を直接呼ぶ）。
2. **Scenario Dのdurable RUNNING確認強化**：durable state確認を、readyセンチネル検出に要した時間を差し引いた「残りdeadline」内でbounded pollingするよう変更し、`started_at`が設定済みであることも明示的にassertするよう変更した。あわせて、readiness確認またはdurable state確認のいずれかがdeadline内に完了しなかった場合はtaskkillを発行しないよう変更した（11.1節の既存契約どおりに実装を訂正した——この点は設計書自体に誤りはなく、実装が設計書の契約を満たしていなかった）。
3. **P1 test assertion 8dの実効化**：fetch呼び出し記録用のlistが2つに分かれており、検証対象と記録対象が一致していなかったため（`_fetch_calls_2`が常に空のまま検証されていた）、単一の共有listに対する増分（差分）で検証する方式へ修正した。
4. **A/B docstringの訂正**：8章・9章の契約本文が本Amendment（第1回）で追加済みであることを反映し、「本文が存在しない」という趣旨の記述を除去した。

**Architecture semantics/scopeへの影響**：本節が記録する対応もすべてtest-only（`tests/`・`tests/e2e_support/`配下）であり、Production Implementation候補は引き続きP1（`src/collector.py`）のみである。新規Foundation・P2・scope拡張のいずれも行っていない（`git diff --stat`で再確認済み）。

### 30.7（当時の記録）30.6節執筆時点でCodex独立レビュー未実施のまま残っていた懸念事項（後にdelta review #2で確認、30.8節参照）

30.6節執筆時点で、以下がCodex独立レビュー未実施のまま残っていた懸念事項だった：

1. 30.6節が記録した5件のMajor対応・4件のMinor対応それぞれが、実装済みコード（該当テストファイル・`tests/e2e_support/env_contract.py`・`tests/e2e_support/local_stub.py`・`tests/e2e_support/scenario_f2_worker.py`）と1:1対応しているかが未検証だった。
2. `ExactEnv`（`os.environ`の完全置換）が、Scenario B・Dの実行中に予期しない副作用（テストハーネス自身の動作に必要な他の環境変数の欠落等）を生んでいないかが未検証だった——targeted E2Eでは全て成功していたが、これは「ExactEnvが安全である」ことの網羅的な証明ではなかった。
3. Local StubのWordPress検証が、fail-closedとして十分に厳密かが未検証だった（例えば`content`フィールドの長さ・形式チェック等）。
4. 30.5節が挙げた項目のうち、本節時点の対応で解消されていない残存部分（8章・9章契約本文全体の初回レビュー等）があった。

これらの懸念事項は、Codex delta review #2（30.8節）で確認された。

### 30.8 Codex delta review #2の結果反映（Minor 3件、Blocking/Major 0）

30.7節に基づき実施したCodex delta review #2（`codex-readonly-review`、Codex High、fresh-thread）の結果は`VERDICT: APPROVED`（Blocking 0／Major 0／Minor 3）だった——30.6節が記録した5件のMajor対応・4件のMinor対応は、すべて独立に確認され解消が認められた。以下、新たに指摘されたMinor 3件への対応を記録する。

1. **Scenario Dのdeadline/no-kill契約の厳密化**：`tests/e2e_support/process_liveness.py`の`wait_until()`が、bounded polling loop終了後にもう一度predicateを評価し、それがdeadline超過後にTrueになった場合でも成功として扱っていた（deadline厳密性の欠如）ため、この「最後のボーナス評価」を廃止し、`timeout_sec`以内に成立しなければ無条件に`False`を返すよう修正した。あわせて、`test_e2e_v6_35_4_scenario_d_abandoned_timeout.py`の`finally`ブロックが、`timing_ok`（readiness/durable state確認がdeadline内に完了したか）を見ずに無条件で`taskkill_tree()`を呼んでいたため、11.1節の「taskkillを発行しない」契約と矛盾していた。`finally`も`timing_ok`でgateするよう修正し、timing failure時はworker自身のHOOK_SAFETY_TIMEOUT_SEC（30秒）自己安全弁による自律終了に委ねる（production機構は使わない、既存hook設計のまま）。
2. **7.5.5節のA〜C fallback/リクエスト回数assertion記述の訂正**：「シナリオA〜Cが同じ強度でfallback非発動・リクエスト回数を確認する」という趣旨の記述を撤回し、実装どおりA（最低1回のみ）・B（ちょうど4回＋fallback不在の両方を厳密確認）・C（いずれも確認しない、対象外）という個別の強度を正確に記載した（7.5.5節に反映済み）。
3. **7.5.5節のScenario B RSS fixture記述の訂正**：「シナリオBは固定fixtureのみを使用する」という誤りを訂正し、実装・9.1節どおりScenario Cのcanonical/retry 2段階counter-based fixtureを転用することを明記した（7.5.5節に反映済み）。

**Architecture semantics/scopeへの影響**：本節の対応もすべてtest-only（`tests/e2e_support/process_liveness.py`・`test_e2e_v6_35_4_scenario_d_abandoned_timeout.py`・設計書7.5.5節）であり、Production Implementation候補は引き続きP1（`src/collector.py`）のみである。scope拡張・新規Foundation・P2実装のいずれも行っていない。Formal Regression・Codex delta review #3・commit/pushは、本節の時点ではいずれも未実施である。

### 30.9 Codex delta review #3の結果反映（Minor 2件、Blocking/Major 0）

30.8節の対応を経て実施したCodex delta review #3（`codex-readonly-review`、Codex High、fresh-thread）の結果は`VERDICT: APPROVED`（Blocking 0／Major 0／Minor 2）だった——30.8節が記録した3件の対応は、すべて独立に確認され解消が認められた。以下、新たに指摘されたMinor 2件への対応を記録する（両者とも、30.8節「Scenario Dのdeadline/no-kill契約の厳密化」と同一テーマの、より精緻な残存課題だった）。

1. **`wait_until()`のdeadline判定の残存レース**：deadlineの判定が`predicate()`呼び出しの**前**にしか行われておらず、`predicate()`自体の実行（スケジューリング遅延を含む）がdeadlineを跨いだ場合、それでもTrueが返れば成功扱いになってしまう残存レースがあった。`predicate()`がTrueを返した直後にもdeadlineを再確認し、既に超過していれば成功として扱わない（`False`を返す）よう修正した（`tests/e2e_support/process_liveness.py`）。
2. **timing failure時のworker orphan化**：`HOOK_SAFETY_TIMEOUT_SEC`の30秒が、post_admission_hookが実際に呼ばれた時点（＝ready-sentinel書き込み後）からしか計測されていなかったため、hookに到達する前（import・gate判定・`manager.run()`呼び出し自体等）でworkerが停止・ハングした場合、readinessが失敗し（親はtaskkillを発行しない、11.1節の既存契約）、かつworker自身の安全弁も一切発火せず、無期限のorphanプロセスとして残存しうる欠陥があった。`tests/e2e_support/scenario_d_worker.py`の`main()`の最初の行でprocess-wide watchdog（`threading.Timer`、daemon thread、test-owned）を起動し、`main()`開始時刻を起点に計測するよう変更した（11.1節に反映済み。**Post-Codex-delta-review#4 Amendmentで「保証」という無条件の表現を「通常のPython interpreter scheduling下でのbest-effort safety timeout」へ訂正、30.10節参照**）。hook自身の待機deadlineも、この同一の起点のdeadlineを共有するよう統一した。「readiness/durable確認失敗時にtest側がtaskkillしない」という親側の既存契約（11.1節・11.2節）は変更していない——worker自身の自律終了のみを強化した。

**Architecture semantics/scopeへの影響**：本節の対応もすべてtest-only（`tests/e2e_support/process_liveness.py`・`tests/e2e_support/scenario_d_worker.py`・`test_e2e_v6_35_4_scenario_d_abandoned_timeout.py`・設計書11.1節）であり、Production Implementation候補は引き続きP1（`src/collector.py`）のみである。scope拡張・新規Foundation・P2実装のいずれも行っていない。Formal Regression・Codex delta review #4・commit/pushは、本節の時点ではいずれも未実施である。

### 30.10 Codex delta review #4の結果反映（Minor 1件、Blocking/Major 0、設計書のみの訂正）

30.9節の対応を経て実施したCodex delta review #4（`codex-readonly-review`、Codex High、fresh-thread）の結果は`VERDICT: APPROVED`（Blocking 0／Major 0／Minor 1）だった——30.9節が記録した2件の対応は、いずれも独立に確認され解消が認められた（Codex自身がread-onlyで遅延predicateプローブを実行し`wait_until()`の修正を直接検証した）。以下、新たに指摘されたMinor 1件（コード自体の欠陥ではなく、設計書の表現精度の問題）への対応を記録する。**本節の対応は設計書のみであり、コード・testはいずれも変更していない。**

1. **watchdogの「無条件の30秒保証」という表現の訂正**：11.1節・30.9節が、process-wide watchdogについて「workerプロセス全体のworst-case生存時間は常に本値以内に収まる」「process起動時刻を起点に`HOOK_SAFETY_TIMEOUT_SEC`秒以内の自律終了を保証する」という趣旨の、無条件のhard boundであるかのような表現を含んでいたが、これは正確ではなかった。実際には：①`main()`より前に発生するmodule-levelのimport解決処理自体はwatchdogの計測対象外である（watchdogは`main()`開始後に設定されるtest-only機構であるため）。②`threading.Timer`のコールバックはPythonのGILを介して実行されるため、native codeがGILを長時間占有し続けるような病的なケースでは、コールバック自体の実行が遅延しうる。したがって、本watchdogは「通常のPython interpreter scheduling下でのbest-effort safety timeout」として位置づけるのが正確であり、`os._exit(2)`は「timer callbackが実際に実行された時点で」processを終了させる、という契約として11.1節を訂正した。external watchdog process等によるhardな上限保証の追加は、production変更を要するため本Releaseのscopeに含めない。
2. **親側no-taskkill契約は変更なし**：「readiness/durable state確認失敗時にtest側がtaskkillしない」という親側の既存契約（11.1節・11.2節）は、本節の訂正によって一切変更されない——訂正対象はworker自身の自律終了に関する表現の精度のみである。

**Architecture semantics/scopeへの影響**：本節の対応は設計書（11.1節・30.9節の該当箇所）のみであり、コード（`tests/`・`tests/e2e_support/`）・Production（`src/`）のいずれも変更していない。Production Implementation候補は引き続きP1（`src/collector.py`）のみである。scope拡張・新規Foundation・P2実装のいずれも行っていない。Formal Regression・Codex delta review #5・commit/pushは、本節の時点ではいずれも未実施である。

### 30.11 Release 6.35 Full Independent Review（whole-implementation）の結果反映（Blocking 1・Major 2・Minor 2・Suggestion 1）

30.10節までの累積4回のdelta review（Architecture Amendment文書に対するCodex delta review）はいずれも`VERDICT: APPROVED`（Blocking 0／Major 0）で完了していたが、これらはいずれも**差分レビュー**（前回からの変更点のみを対象とする）だった。本節は、Release 6.35のimplementation全体（P1・Scenario A〜F・test helpers・設計書全文）を対象とした**独立した whole-implementation review**（`codex-readonly-review`、Codex High、fresh-thread）の結果を反映する。この結果は`VERDICT: NOT APPROVED`（Blocking 1／Major 2／Minor 2／Suggestion 1）だった。以下、指摘事項ごとの対応を記録する。

**Blocking（1件、対応は別のHuman Gate、本節では未実施）**：
- 設計書自身が要求するT6（Formal Regression 37-fileの機械可読roster）が実装されておらず、19.2/19.3節が定める37/37 no-skip Formal Regression本体も未実施だった。これはRelease acceptanceの別個の完了ゲートであり、targeted E2E（153/153、その後163/163）では代替できない、とCodexは指摘した。**本節ではT6（roster自体の実装・静的validation）のみを完了させ、Formal Regression本体（37ファイルの実行）はスコープ外のまま、次のHuman Gateでの実施を待つ**（詳細は下記「T6 roster」項）。

**Major対応（2件）**：
1. **Scenario D authority containmentの穴**：`test_e2e_v6_35_4_scenario_d_abandoned_timeout.py`の「durable state二重確認」が、`ExecutionHistoryConfig.from_env(project_root=copy.root)`をテストハーネス自身のプロセス内（`ExactEnv`等のenv隔離ブロックへ入る前、host ambient環境のまま）で呼んでいたため、hostに`EXECUTION_HISTORY_DIR`が設定されていた場合、Disposable Project Copy外を参照しうる欠陥があった（6.26節のpathlib `/`演算子の絶対path上書き挙動）。`.from_env()`を使わず、`ExecutionHistoryConfig`（plain dataclass）を直接構築し、`<copy.root>/logs/execution_history`という固定相対パスへhost環境変数を一切経由せずに解決するよう修正した（11.1節に反映済み）。
2. **Scenario BのProhibited Outcome未実装**：「`terminal_disposition == HUMAN_REVIEW_REQUIRED`になること（Scenario Cとの混同）」というProhibited Outcomeを、2回目の`reconcile_all()`の`opened_count==0`という間接証拠だけに頼っており、`HUMAN_REVIEW_REQUIRED`自体がreopenを抑制するため、混同があっても検出できない構造的な欠落があった。`composition_root.lineage.find_existing_lineage(canonical_result.run_id)`でlineageレコードを直接取得し、`terminal_disposition == RetryLineageDisposition.SUCCEEDED`を明示的にassertするよう修正した（9.1節に反映済み）。

**Minor対応（2件）**：
1. **LocalStubの認証検証がfail-open**：`set_wordpress_expected_auth()`が一度も呼ばれていない場合、認証検証自体がskipされ無条件許可になっていた。期待認証情報の未設定自体を拒否理由とするfail-closedへ修正した（`tests/e2e_support/local_stub.py`、7.5.5節に反映済み）。WordPress成功経路を使う既存シナリオ（A・B・C・D・F2）は全て`set_wordpress_expected_auth()`を呼び出し済みであることを確認し、回帰は発生していない。
2. **`scenario_d_worker.py`のコード内コメントの不整合**：設計書側（§11.1・§30.10）は既にwatchdogを「best-effort safety timeout」と訂正済みだったが、`scenario_d_worker.py`自身のdocstring・コメントは「無条件の30秒保証」という古い表現のままだった。実装semantics（watchdogの動作自体）を一切変更せず、コメントのみを設計書の表現と整合させた。

**Suggestion対応（1件）**：
- `_RssPathState.next_response()`（内部counterの読み取り・更新）を`LocalStub`の`lock`の内側で行うよう変更した（`tests/e2e_support/local_stub.py`の`do_GET`）。従来はlockの外側で呼んでいたため、`ThreadingHTTPServer`が同一RSS pathへ並行リクエストを受けた場合にcounterのincrementが競合しうる理論上の余地があった。test-onlyの変更であり、実装semantics（各リクエストへのレスポンス内容の決定則）は変更していない。

**T6 roster（Blocking項目のうち、roster自体の実装完了分）**：
`tests/formal_regression_inventory.py`を新規作成し、19.1節が確定した37ファイルのbasenameを`FORMAL_REGRESSION_ROSTER`（`tuple[str, ...]`）として機械可読に保持する。`tests/test_e2e_v6_35_8_t6_formal_regression_roster_validation.py`を新規作成し、以下を静的に検証した（結果：8/8 PASS）：
- count＝37、unique_count＝37（重複0）、missing_count＝0（全path実在）
- 設計書19.1節から独立して当該テストファイル自身が転記したroster（`ARCHITECTURE_ROSTER_19_1`）との対称差分＝0件

**この静的validationは、rosterという名簿自体の整合性を確認したものであり、37ファイルを実際に`python <file>.py`として実行しexit code 0を確認するFormal Regression本体（19.2節・19.3節）は、本節の時点でもまだ実施していない。** Formal Regression本体の実施は、本節で解消したBlocking項目の一部のみであり、残りは次のHuman Gateでの実施を待つ。

**Architecture semantics/scopeへの影響**：本節の対応はすべてtest-only（`tests/`・`tests/e2e_support/`）および設計書（本文の該当箇所）に限られる。Production Implementation候補は引き続きP1（`src/collector.py`）のみであり、本節でも一切変更していない。scope拡張・新規Foundation・P2実装のいずれも行っていない。**Formal Regression本体の実行・Codexへの再照会（delta review #5等）・commit/pushは、本節の時点ではいずれも未実施である。**

### 30.12 Pre-Formal-Regression Closure Review・残存Minor修正・Formal Regression本体の実施（初回32/37 PASS→根本原因是正→最終37/37 PASS）

30.11節までの対応後、Formal Regression本体（19.2節・19.3節）を実際に実行する前段階として、以下を順に実施した。

**(1) Pre-Formal-Regression Closure Review**：30.11節の対応（T6 roster新設含む）を踏まえ、「Formal Regressionを次に実行してよい状態か」を確認する目的の独立review（`codex-readonly-review`、Codex High、fresh-thread、read-only）を実施した。結果は`VERDICT: APPROVED`（Blocking 0／Major 0／Minor 1）。指摘されたMinor 1件は、`tests/test_e2e_v6_35_4_scenario_d_abandoned_timeout.py`の`finally`ブロック内、parent-test側のcleanupコメントが、watchdogを「timing非依存で確実に終了させる」かのように記述しており、30.10節で既に訂正済みの設計書側「best-effort safety watchdog」という表現と矛盾している、というものだった。

**(2) 残存Minor修正**：上記コメントを、30.10節の訂正済み表現（「通常のPythonインタプリタscheduling下でのbest-effort safety watchdogであり、timing非依存・無条件の保証ではない」）と整合する内容へ書き換えた。runtime behavior・test semantics・Productionコードは変更していない（`py_compile`で構文確認済み）。

**(3) Formal Regression本体・初回実行（結果：32/37 PASS、5 FAIL）**：`tests/formal_regression_inventory.py`の`FORMAL_REGRESSION_ROSTER`（37ファイル、roster外の追加・implicit discoveryなし）を対象に、各ファイルをproject venv Pythonで個別subprocess実行し、exit codeとPASS/FAIL/SKIPを機械的に集計した。結果は`TOTAL=37 PASS=32 FAIL=5 SKIP=0 MISSING=0`。FAILしたのは以下5ファイル：`test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py`／`test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py`／`test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_refinement_foundation.py`／`test_e2e_v6_26_0_zero_diff_guard_registry_foundation.py`／`test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py`。

**(4) 根本原因調査（read-only）**：`tests/zero_diff_guard_registry.py`（DEF-6.23-9、v6.26.0で新設された共有allow-list registry。GR-9「保護対象パスへ触れるReleaseは、それ以前に存在するすべてのbaseline固定guardのallow-listを更新する」の実装）を精査した結果、以下を確定した。
- `RELEASE_ORDER`タプルの末尾が`"v6.34.0"`で止まっており、`"v6.35.0"`が未登録だった。
- `_TEST_CHANGE_CONTRIBUTIONS`タプルに、Release 6.35が`tests/`配下へ新規追加したファイル群に対応するエントリが1件も存在しなかった。
- これにより`allowed_test_changes_for()`が返す許容集合にRelease 6.35の新規untrackedファイルが含まれず、v6.22／v6.23／v6.24の`NOIMPACT-NO-UNTRACKED-TESTS`チェックが検出・FAILし、これを子プロセスとして再実行するv6.26（`SELF-TESTS-NO-UNTRACKED`含む）／v6.27へcascadeしていた。単一の根本原因（GR-9登録漏れ）であり、Production側（`src/collector.py`のP1）に起因する回帰ではないことを確認した。
- 過去v6.26.0〜v6.34.0の`_TEST_CHANGE_CONTRIBUTIONS`を確認し、新規独立package・PROTECTED_PATHS対象外のReleaseであっても`tests/`への新規追加は必ず自己登録している先例（v6.29.0・v6.31.0・v6.34.0等）、および`zero_diff_guard_registry.py`自身を編集した回は例外なく自己を登録している先例（v6.26.0〜v6.34.0の9件全て）を確認した。

**(5) GR-9既存conventionに従った最小修正**：`tests/zero_diff_guard_registry.py`のみへ、先例と完全に同型の2箇所を追記した。
- `RELEASE_ORDER`末尾へ`"v6.35.0"`を追加。
- `_TEST_CHANGE_CONTRIBUTIONS`へ、Release 6.35の新規untrackedファイル18件（`tests/e2e_support/`配下8件：`__init__.py`・`disposable_copy.py`・`env_contract.py`・`local_stub.py`・`process_liveness.py`・`scenario_c_worker.py`・`scenario_d_worker.py`・`scenario_f2_worker.py`、`tests/formal_regression_inventory.py`、`test_e2e_v6_35_0`〜`_8`の9ファイル）＋registry自身の自己登録1件（`zero_diff_guard_registry.py`）＝計19エントリを`"v6.35.0"`として追記した。
- `PROTECTED_PATHS`／`_SOURCE_CHANGE_CONTRIBUTIONS`／`BASELINE_COMMITS`は変更していない（`src/collector.py`はPROTECTED_PATHS対象外であり、変更の根拠がないため）。
- 修正後、`allowed_test_changes_for()`のexact-set検証をread-onlyで実施し、v6.22.0〜v6.35.0の全windowで「未許可のuntracked」が0件であることを確認した。

**(6) 影響5-file再検証（結果：5/5 PASS）**：上記修正後、直接影響を受けた5ファイル（v6.22／v6.23／v6.24／v6.26／v6.27）のみを再実行し、全て`exit=0`・FAIL 0件を確認した（v6.22: 324/324、v6.23: 355/355、v6.24: 362/362、v6.26: 264/264、v6.27: 119/119）。

**(7) Formal Regression本体・最終実行（結果：37/37 PASS）**：`FORMAL_REGRESSION_ROSTER`の37ファイル全件を再実行し、`TOTAL=37 PASS=37 FAIL=0 SKIP=0 MISSING=0`（`ALL_PASS_37_OF_37=True`）を確認した。19.2節・19.3節が定めるFormal Regression本体の合格条件（37/37 PASS・全exit code 0・FAIL 0・SKIP 0・roster missing/extra 0・implicit discoveryなし・roster外ファイル追加なし・修正中のcode変更なし）を満たした。

**(8) targeted E2E最終再確認（結果：163/163 PASS）**：P1＋Scenario A〜F＋T6のexact 9ファイル（`test_e2e_v6_35_0`〜`_8`）のみを最終working treeで再実行し、`37+11+20+22+17+17+10+21+8 = 163`件全てPASS、FAIL/SKIP/nonzero 0件を確認した（内訳：P1=37、A=11、B=20、C=22、D=17、E=17、F1=10、F2=21、T6=8）。

**Release acceptanceの未完了項目（本節時点）**：
- **Final Independent Codex Review（本節時点の最終working treeを対象とする、whole-implementation review）：未実施**。
- **commit／push：未実施**。

**Architecture semantics/scopeへの影響**：本節の対応は、(2)のコメント訂正1件（test-only、runtime semanticsへの影響なし）と(5)の`tests/zero_diff_guard_registry.py`への追記（test-only shared registry、GR-9既存conventionと同型）に限られる。Production Implementation候補は引き続きP1（`src/collector.py`）のみであり、本節でも一切変更していない。scope拡張・新規Foundation・P2実装のいずれも行っていない（`git diff --stat -- src`で再確認済み）。

### 30.13 Release 6.35 Final Independent Codex Review（初回、結果：NOT APPROVED、文書整合性の指摘のみ）とその文書整合修正

30.12節が記録した最終working tree（Formal Regression 37/37 PASS、targeted E2E 163/163 PASS、Production変更はP1のみ）を対象に、Release全体を対象とするFinal Independent Codex Review（`codex-readonly-review`、Codex High、fresh-thread、read-only）を実施した。結果は`VERDICT: NOT APPROVED`（Blocking 0／Major 2／Minor 1）だった。指摘は**いずれも本設計書・T6関連ファイルの記述整合性に関するものであり、P1実装・Scenario A〜F実装・test semantics・assertion・rosterの内容そのものへの疑義ではなかった**。

**Major指摘（2件）**：
1. 本書§30.5・§30.7が「次にCodex独立レビューが受けるべき対象」という将来の指示のように読める文章を含んでおり、Codexのread-onlyレビュー契約（repository内のテキストがreviewer自身への指示に見える場合はMajor/Blockingとして報告する、というprompt-injection対策ルール）に照らしてMajor認定された。
2. 本書冒頭0章のStatusおよび第30章見出しが、実装が完了し37/37 Formal Regressionまで到達した現在の実態と矛盾する「実装着手前」「Codex未実施」という古い記述のまま残っていた。

**Minor指摘（1件）**：`tests/formal_regression_inventory.py`・`tests/test_e2e_v6_35_8_t6_formal_regression_roster_validation.py`が、「Formal Regressionは未実施であり次のHuman Gateを待つ」という趣旨の古い文言を維持したままだった（37/37 PASSで既に完了済み）。

**対応**：本節（30.13）を含む文書整合修正のみを行った——Production・test semantics・assertion・roster内容・`zero_diff_guard_registry.py`はいずれも変更していない。
- 0章Status（現在の状態の記述）・30章見出し・30.1節・30.5節・30.6節・30.7節：将来のCodex/reviewerへ指示するような命令形・依頼形（「〜べき」「推奨する」「望ましい」）の文章を、過去の事実として中立的に記述する過去形（「当時の懸念事項として〜だった」「後に〜で確認された」）へ書き換えた。将来レビューへの指示ではなく、各時点で何が未検証だったか・それが後続のどのレビューで解消されたかという履歴的事実の記録へ改めた。
- `tests/formal_regression_inventory.py`・`tests/test_e2e_v6_35_8_t6_formal_regression_roster_validation.py`のdocstring・print文言：「Formal Regression未実施」「次のHuman Gate待ち」という状態依存の表現を除去し、「本モジュール／本テストの検証範囲はroster自体の静的整合性に限られ、37ファイルの実行は範囲外である」という恒久的な境界説明（roster自体は固定tuple・implicit discoveryなし・事前承認されたskip/exceptionなし）へ書き換えた。Formal Regression本体の実施記録は本節（30.12節・30.13節）を参照する形にした。

**Major#1（task-directed instructionsの指摘）への対応方針**：§30.5・§30.7の内容自体（Codex delta review #1・#2の着手前に何が懸念事項だったか）は、Release 6.35のレビュー経緯を追跡する上で必要な履歴情報と判断し、削除ではなく**中立的な過去形の記述への書き換え**で対応した。将来のCodex呼び出しや人間のreviewerに対して「次はこれを確認せよ」と指示する文言は残していない。

**Architecture semantics/scopeへの影響**：本節の対応は文書整合修正のみであり、コード（`src/`・`tests/`のtest semantics・assertion）・roster内容・`zero_diff_guard_registry.py`のいずれも変更していない。Production Implementation候補は引き続きP1（`src/collector.py`）のみである。**本節の時点で、修正後の内容に対する再度のFinal Independent Codex Reviewはpendingである。commit／pushもpendingである。**「Release完了」「Final Approved」は、本節を含む本書のいずれにも記載しない。

### 30.14 Release 6.35 Final Independent Codex Re-Review #1（結果：NOT APPROVED、§0/30章のstale current-state pointerの指摘のみ）とその文書整合修正

30.13節が記録した文書整合修正後のworking treeを対象に、Release全体を対象とするFinal Independent Codex Re-Review #1（`codex-readonly-review`、Codex High、fresh-thread、read-only）を実施した。WRAPPER_STATUSはOKであり、結果は`VERDICT: NOT APPROVED`（Blocking 0／Major 1／Minor 0）だった。

**Major指摘（1件）**：30.13節の修正後もなお、本書冒頭0章の記述が、特定のsection（例：「現在（30.12節時点）」等）を指す可変のcurrent-state pointerを含んでおり、実装・レビューが進むにつれて当該pointerが指す節がずれていく（stale化する）構造上の問題が指摘された。この指摘はProduction実装（`src/collector.py`）・test semantics・assertion・rosterのいずれの内容にも及ばず、本書のcurrent-state記述方法そのものに関する文書整合性の指摘だった。

**Production/Test/rosterへのfinding**：なし。

**対応**：本節（30.14）を含む文書整合修正のみを行った。0章のCurrent Status記述を、特定sectionへの可変pointerを含まない形へ書き換え、0章を本書のCurrent Status唯一の正本と位置づけた。第30章は、Release 6.35着手からの時系列履歴を記録する章であり、本章内のいずれの節も「現在の状態」の参照先としないことを明記した。Production・test semantics・assertion・roster内容・`zero_diff_guard_registry.py`はいずれも変更していない。

**Architecture semantics/scopeへの影響**：本節の対応は文書整合修正のみであり、コード（`src/`・`tests/`のtest semantics・assertion）・roster内容・`zero_diff_guard_registry.py`のいずれも変更していない。Production Implementation候補は引き続きP1（`src/collector.py`）のみである。**本節の執筆時点で、Final Independent Codex Re-Review #2は未実施（pending）である。**commit／pushもpendingである。「Release完了」「Final Approved」は、本節を含む本書のいずれにも記載しない。

### 30.15 Release 6.35 Final Independent Codex Re-Review #2（結果：APPROVED）とFinal technical gate通過の記録

30.14節が記録した文書整合修正後のworking treeを対象に、Release全体を対象とするFinal Independent Codex Re-Review #2（`codex-readonly-review`、Codex High、fresh-thread、read-only）を実施した。WRAPPER_STATUSはOKであり、結果は`VERDICT: APPROVED`（Blocking 0／Major 0／Minor 0／Suggestions 0）だった。

**確認内容**：30.13節・30.14節が記録した過去のMajor指摘（Initial Reviewの文書記述整合性2件、Re-Review #1のstale current-state pointer1件）がいずれも解消されていること、0章がCurrent Status唯一の正本になっており可変pointerが残存していないこと、第30章が各節執筆時点の過去形記述として一貫していること、task-directedなreviewer/Codex向け文言が再発していないこと、targeted E2E 163/163 PASS・Formal Regression 37/37 PASSのevidenceが対象ファイル群と静的に整合していること、Production変更が`src/collector.py`のP1のみに限定されていること、27章Acceptance Criteriaが満たされていることを、それぞれ独立に確認した。commit／push自体の可否はこのレビューの対象外だった。

**対応**：新規のBlocking／Major／Minorがいずれも0件だったため、本節（30.15）の追記以外の修正は行っていない。Production・test semantics・assertion・roster内容・`zero_diff_guard_registry.py`はいずれも変更していない。

**Architecture semantics/scopeへの影響**：本節の対応は文書への履歴追記のみであり、コード（`src/`・`tests/`のtest semantics・assertion）・roster内容・`zero_diff_guard_registry.py`のいずれも変更していない。Production Implementation候補は引き続きP1（`src/collector.py`）のみである。**本節の執筆時点で、Release 6.35はFinal technical gateを通過した状態であり、commit／pushはpendingである。**
