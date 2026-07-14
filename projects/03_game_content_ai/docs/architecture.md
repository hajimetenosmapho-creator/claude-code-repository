# 出力アーキテクチャ設計

作成日：2026-06-26  
更新日：2026-07-14（v6.0.0 — Retry Runtime Lock Foundationを追記。新規パッケージ`src/retry_runtime_lock/`（`RetryRuntimeLock` / `RetryRuntimeLockError`）を追加し、`os.open(O_CREAT | O_EXCL)`によるファイル存在ベースの排他制御のみを行う独立コンポーネントとして、同一Retry Runtimeプロセスの多重起動を防止できるようにしたこと、`scripts/run_retry_runtime.py`が単発実行・`--loop`実行の全体を`with lock:`で包み、ロック取得済み（＝別プロセスが実行中）の場合は`RetryCompositionRoot`等を一切構築せず`RetryRuntimeLockError`を専用のtry/exceptで捕捉しエラーメッセージ（ロックファイルのパスと対処方法を含む）を表示した上でexit code 1とするよう変更したこと、`RetryRuntimeLock`は他のretry_*パッケージのいずれにも依存せず標準ライブラリ（`os` / `pathlib`）のみで実装したこと、`RetryCompositionRoot` / `RetryRuntimeOrchestrator` / `RetryRuntimeLoop` / `RetryManager`（`retry_engine`）はいずれも無改修としたこと、Code Reviewで発見した「`acquire()`内で`os.write()`が失敗した場合にロックファイルだけが残存し恒久的なstale lockになる」経路を`os.close(fd)`→ロックファイル削除→例外再送出という順序で修正したこと、stale lockの自動検出・自動復旧（PID生存確認等）は行わずプロセス強制終了時は手動削除が必要な既知のTrade-offとして受け入れたこと、`.gitignore`へ`.run/`を追加しロックファイルをGit管理対象外としたこと、本Foundationは実際のDaemon化（バックグラウンド常駐・Windows Service化）そのものではなくその前提となる最小Foundationと位置づけたことを明記）
更新日：2026-07-12（v5.9.0 — Retry Runtime Loop Wiring Foundationを追記。`scripts/run_retry_runtime.py`へ`--loop`（`action="store_true"`）・`--interval-seconds`（`type=float`、`default=None`）を追加し、既存`RetryRuntimeLoop`（v5.5.0）を使ったLoop実行に対応したこと、`--loop`省略時（デフォルト）は従来どおり1サイクルのみで終了すること、`--interval-seconds`は`--loop`と併用時のみ有効で`--loop`なしでの指定・0以下の指定はいずれもCLIエラー（`parser.error()`、非0終了）とし`--loop`指定時に省略した場合のデフォルトは60秒としたこと、`main()`内のローカル関数`run_cycle()`（`orchestrator.run_once(dry_run=args.dry_run)` → `print(format_summary(result))`）を`RetryRuntimeLoop`の`run_once_fn`として注入し`sleep_fn=time.sleep` / `should_continue_fn=lambda: True`とあわせて構築したこと（`RetryRuntimeLoop`へdry_run属性・引数は追加せずクロージャで伝播）、Loop実行中の`KeyboardInterrupt`のみを`main()`内で捕捉し短い終了メッセージを表示したうえで正常終了（exit code 0）とする一方それ以外の例外はfail-fastのまま伝播させたこと、`src/retry_runtime_loop/` / `src/retry_runtime_orchestrator/` / `src/retry_composition/` / `RetryManager`（`retry_engine`）はいずれも無改修とし本Releaseの変更対象を`scripts/run_retry_runtime.py`の1ファイルのみに限定したこと、これにより`retry_runtime_loop`（v5.5.0、消費者不在の先行実装）が初めて実際の消費者を持ったこと、`scripts/run_retry_runtime.py`無改修前提の既存Architecture Guard差分を`[KI-27]`として・`retry_runtime_loop`の消費者不在チェックの恒久差分を`[KI-21]`と同型の`[KI-28]`として記録したこと、Documentation Debtとして残っていた`scripts/run_retry_runtime.py`docstring内の「`RetryEnqueueTrigger`はdry_run非対応」という v5.8.0以前の古い記述を削除したことを明記）
更新日：2026-07-12（v5.8.0 — Retry Enqueue Trigger Dry Run Foundationを追記。`RetryEnqueueTrigger.enqueue_pending_failures()`へ`dry_run: bool = False`を呼び出し時引数として追加し、Monitor走査・History参照・Guard判定・Queue重複確認は`dry_run`の値に関わらず通常どおり実行する一方、Guardを通過しQueue重複も存在しない候補について`dry_run=True`の場合は`RetryQueueManager.enqueue()`を呼び出さず処理を終了するよう変更したこと（`enqueued` / `failed`いずれにも加算しない）、`RetryRuntimeOrchestrator.run_once()`から`trigger.enqueue_pending_failures(max_attempts=self.policy.max_attempts, dry_run=dry_run)`への伝播を追加し`--dry-run`指定時にRetry Queueへの新規enqueueが実際に抑止されるようになったこと（`[KI-23]`解消）、Architecture Review初版では`RetryEnqueueTriggerResult`へ`dry_run_planned`カウンタを追加する案（案A）を提示したが「実際に行われた結果のみを表す」という既存Result Contractの一貫性を優先する方針（案B）へユーザーレビューを経て変更したこと、`RetryEnqueueTriggerResult` / `RetryRuntimeCycleResult` / `format_summary()` / `scripts/run_retry_runtime.py` / `RetryCompositionRoot` / `RetryManager` / `RetryExecutor` / `RetryQueueManager` / `RetryHistoryManager` / `RetryEnqueueGuard` / `RetryRuntimeLoop` / `NullRetryEnqueueTrigger`はいずれも無改修とし本Releaseの変更対象を`src/retry_enqueue_trigger/retry_enqueue_trigger.py` / `src/retry_runtime_orchestrator/retry_runtime_orchestrator.py`の2ファイルのみに限定したこと、dry_run時にGuard通過かつQueue重複なしの候補が既存カウンタのいずれにも加算されないため`scanned == 各カウンタの合計`という暗黙の不変条件が成立しない場合がある点・Queue容量上限のシミュレーションができない点をKnown Limitationとして記録したことを明記）
更新日：2026-07-12（v5.7.0 — Retry Runtime Safe Dry Run Wiring Foundationを追記。`scripts/run_retry_runtime.py`の`main()`内部のみに`argparse`（ローカルimport）・`--dry-run`フラグを追加し、`RetryRuntimeOrchestrator.run_once(dry_run=...)`（v5.6.0）をCLIから呼べるようにしたこと、`--dry-run`指定時は`main()`が直接`[DRY RUN MODE]`を標準出力へ表示し`format_summary()`は経由しないこと、`format_summary()`のシグネチャ・実装（`RetryRuntimeCycleResult` → Summary文字列という既存責務）は一切変更していないこと、`RetryRuntimeCycleResult`へ`dry_run`フィールドを追加する案（CLI都合の情報をDomain側のResultクラスへ持ち込むことになるため）・`parse_args()`への関数分離案（フラグが`--dry-run`1つのみの現時点ではYAGNIに反するため）・CLI SummaryへKnown Issue説明文を表示する案（Summaryの責務を実行結果表示のみに限定する方針のため）はいずれもユーザー判断により見送ったこと、`RetryRuntimeOrchestrator` / `RetryManager` / `RetryExecutor` / `RetryCompositionRoot` / `RetryRuntimeCycleResult`はいずれも無改修で本Releaseの変更対象を`scripts/run_retry_runtime.py`の`main()`内部のみに限定したこと、`--dry-run`指定時もRetry Queueへのenqueue自体は通常どおり実行される点を新規Known Issue`[KI-23]`として、本Releaseによる`scripts/run_retry_runtime.py`変更が v5.4.0/v5.5.0/v5.6.0 の一部Architecture GuardをFAILさせる点を`[KI-24]`として記録したこと、`NullRetryEnqueueTrigger.enqueue_pending_failures()`の`max_attempts`引数不在（v5.0.0由来のシグネチャ不整合、現状到達不能で実害なし）をTechnical Debtとして記録し本Releaseでは対応しなかったことを明記）
更新日：2026-07-12（v5.6.0 — Retry Runtime Safe Dry Run Foundationを追記。`RetryOutcome`（`retry_result.py`）へ`DRY_RUN`を新設したこと、`RetryExecutor.execute()`が`request.dry_run=True`の場合に`WorkflowEngineManager.run()`の呼び出し自体は維持しつつ（Workflow Engine層のdry_run伝播は既に安全でありAgent層の`act()`が呼ばれないため実際の副作用がないこと、`workflow_engine_result`により「何が起きたはずか」を引き続き可視化できることを理由に呼び出しを維持したこと）戻り値の`outcome`を`RetryOutcome.RETRIED`ではなく`RetryOutcome.DRY_RUN`とするよう変更したこと、既存の`RetryQueueUpdateDecider` / `RetryHistoryRecordExecutor` / `RetryQueueRemovalExecutor` / `RetryQueueCleanupDecider`（v4.3.0）はいずれも「outcome==RETRIEDかどうか」またはallowlist方式で判定しているため無改修のまま`DRY_RUN`を自動的に安全側（NOOP・記録なし・除去なし）に倒せたこと、唯一`retry_outcome_terminality.py`の`classify_reason()`のみ明示列挙+`raise ValueError`という網羅チェック方式（else方式ではない）であるため改修が必須であり、Architecture Reviewでこれを怠ると`RetryQueueTerminalCleanupDecider`経由で`run_once(dry_run=True)`がクラッシュすることを発見したこと（`RetryCleanupReason.DRY_RUN`追加・`classify_reason()`分岐追加・`RETRY_OUTCOME_TERMINALITY`への`DRY_RUN → TRANSIENT`追加で対応し、恒久ルールとして「`RetryOutcome`へ新しい値を追加する場合は参照箇所を全確認すること」を設計書に明記したこと）、`RetryRuntimeOrchestrator.run_once()`に`dry_run: bool = False`引数を追加し`manager.execute_dispatchable_retries(events, dry_run=dry_run)`へ伝播させる一方`trigger.enqueue_pending_failures()`へは伝播させなかったこと（Queueへの新規登録自体はin-memoryで可逆的・外部作用を伴わないためリスクレベルが異なると判断し対象外とし、次Release候補「Retry Enqueue Trigger Dry Run Foundation」へ申し送ったこと）、CLI配線（`scripts/run_retry_runtime.py`への`argparse`・`--dry-run`導入）はChatGPTレビューを踏まえExecution ReleaseとEntry Point Releaseを分離する本プロジェクトの一貫したパターン（v5.3.0/v5.4.0と同型）に従い次Release候補「Retry Runtime Safe Dry Run Wiring」へ分離したこと、`dry_run`をRequest Object化する案はretry_engine全体が「呼び出しの都度渡すbool引数」で統一されている既存慣習とDevelopment Charter「抽象化は必要になってから行う」を理由に見送り、将来2つ目以降の振る舞い変更引数が必要になった時点で再検討する基準を設計書に残したこと、`retry_engine`（`retry_result.py` / `retry_executor.py` / `retry_outcome_terminality.py` / `__init__.py`）・`retry_runtime_orchestrator`（`retry_runtime_orchestrator.py`）の2パッケージのみ変更し、`scripts/run_retry_runtime.py`を含むそれ以外の既存パッケージはいずれも無改修であることを明記）
更新日：2026-07-09（v5.5.0 — Retry Runtime Loop Foundationを追記。`RetryRuntimeOrchestrator.run_once()`（v5.3.0）を繰り返し呼び出すだけの薄いLoop Wrapper`RetryRuntimeLoop`（`src/retry_runtime_loop/`）を新設したこと、`run_once_fn` / `sleep_fn` / `should_continue_fn` / `interval_seconds`をConstructor Injectionで保持し`run()`で`while should_continue_fn(): run_once_fn(); sleep_fn(interval_seconds)`を実行するだけのStateless Wrapperとしたこと（`RetryManager` / `RetryQueueManager` / `RetryHistoryManager` / `RetryPolicy` / `RetryRuntimeOrchestrator` / `RetryCompositionRootのいずれもimportしない）、`run_once_fn`の戻り値を一切解釈せず破棄し`run()`は`None`を返すこと、例外はtry/exceptで握りつぶさずfail-fastで伝播させること、ユーザーから当初提示された「Loop Foundation」を初回Architecture Reviewでは配線・運用まで見据えたものとして評価しdry_run未対応による安全性リスクを理由に一度は代替テーマを提案したが、再レビューの結果Loop自体がBusiness Logicを持たず`scripts/`への配線を伴わない未配線Foundationに限定すれば実運用リスクを増やさないと判断し結論を修正したこと（Option A'採用の経緯）、`scripts/run_retry_runtime.py` / `RetryRuntimeOrchestrator` / `RetryCompositionRoot`のいずれからも本Releaseでは配線しないこと（消費者不在の先行実装）、既存13パッケージ（`workflow_monitor` 〜 `retry_runtime_orchestrator`）・`scripts/run_retry_runtime.py`はいずれも無改修であり本Releaseによる新規Architecture Guard差分（KI）は発生しなかったことを明記）
更新日：2026-07-09（v5.4.0 — Retry Runtime Script Entry Point Foundationを追記。`RetryRuntimeOrchestrator.run_once()`（v5.3.0）を初めてCLIから呼び出せるEntry Point `scripts/run_retry_runtime.py`を新設したこと、`RetryCompositionRoot.from_env()` → `RetryRuntimeOrchestrator.from_composition_root()` → `run_once()`のみを呼び出す薄い構成としBusiness Logicを一切持たせなかったこと（既存script群と同じscripts層の責務）、CLI引数は持たない設計としたこと（`run_once()`自体に分岐点がなく、特に`--dry-run`は`run_once()`側がdry_run未対応のため見せかけの安全機能になることを理由に見送ったこと）、Exit Code Policyとして正常終了0（Python標準）・例外発生時はPython標準の非0（fail-fast）を採用し独自のExit Code体系は導入しなかったこと、`format_summary(result: RetryRuntimeCycleResult) -> str`という関数へ表示ロジックを局所化し、Formatterクラスの実装自体は見送りつつ将来の抽出を容易にする構造に留めたこと（Architecture Review Minor Recommendation 2件の反映）、Gate（`RETRY_ENGINE_ENABLED`等）が閉じている場合もscriptは`isinstance()`によるNull判定を一切行わず常に`run_once()`を呼び出して結果件数（すべて0件）をそのまま表示する設計としたこと（Null Object Patternの意図を保つため）、`RetryCompositionRoot` / `RetryRuntimeOrchestrator`および既存12パッケージはいずれも無改修であること、本Releaseにより`retry_runtime_orchestrator`が初めて実際の消費者を持ったことでv5.2.0の一部Architecture GuardがFAILする恒久差分が生じ`[KI-21]`として記録したことを明記）  
更新日：2026-07-09（v5.3.0 — Retry Runtime Run Once Foundationを追記。`RetryRuntimeOrchestrator`へ`run_once()`を追加し、Retry Runtimeを1サイクルだけ安全に実行できるようにした設計判断。実行順序は`trigger.enqueue_pending_failures(max_attempts=policy.max_attempts)` → `scheduler.run_due(jobs=[])` → `manager.execute_dispatchable_retries(events)`（本メソッド内でちょうど1回だけ呼び出す） → `RetryQueueUpdateDecider` / `RetryQueueRemovalExecutor` / `RetryQueueCleanupDecider` / `RetryQueueCleanupExecutor` / `RetryQueueTerminalCleanupDecider` / `RetryQueueTerminalCleanupExecutor` / `RetryHistoryRecordExecutor`（いずれも`retry_engine`が既に公開しているStateless・無引数コンストラクタのクラス）への結果配布、という固定順序としたこと、`execute_dispatchable_retries()`を1回だけ呼びその戻り値を保持したまま配布することで、v5.2.0で発見された「発見B」（同一run_idに対する`retry()`の多重実行リスク）を`retry_manager.py`を無改修のまま解消したこと、戻り値として`None`ではなく新設の`RetryRuntimeCycleResult`（`trigger_result` / `scheduler_events` / `execution_results` / `removal_results` / `cleanup_results` / `terminal_cleanup_results` / `history_results`の7フィールドを持つfrozen dataclass）を返す設計としたこと、`run_once()`に`dry_run`引数を追加しなかった理由（`RetryExecutor.execute()`が`dry_run`の値に関わらず常に`outcome=RetryOutcome.RETRIED`を返すため、`dry_run=True`でもQueue除去・History記録という実際の副作用を防げず「安全なdry_run」にならないと判明したため、Known Issueとして記録し独立Releaseへ送ったこと）、`scripts/`エントリーポイント・`loop()`・`daemon()`はいずれも本Releaseの対象外としたこと、既存11パッケージ（`workflow_monitor` 〜 `retry_scheduler_decision`）および`retry_manager.py`はいずれも無改修であることを明記）  
更新日：2026-07-09（v5.2.0 — Retry Runtime Orchestrator Foundationを追記。新規パッケージ`src/retry_runtime_orchestrator/`（`RetryRuntimeOrchestrator`）を追加し、「Retry Runtimeの実行順序を将来管理する場所」として`trigger` / `scheduler` / `manager` / `queue` / `history` / `policy`の6つをConstructor Injectionで保持するだけの設計判断。`run()` / `run_once()` / `loop()` / `daemon()`等のBusiness Logicはいずれも本Releaseの対象外とし、Composition（`RetryCompositionRoot`＝組み立て）とOrchestration（`RetryRuntimeOrchestrator`＝実行順序の置き場所）の責務分離を明確化したこと、Architecture Reviewの過程で発見した2点（Scheduler系コンポーネントがComposition Rootへ未配線のため`RetryQueueManager`に積まれた再試行候補を`SchedulerEvent`化する経路が存在しなかったこと／`RetryManager`の上位メソッド群を同一`events`に対して素朴に並べて呼び出すと`execute_dispatchable_retries()`が重複実行され`retry()`が同一run_idに対して複数回呼ばれかねないこと）を踏まえ、`RetryCompositionRoot`へ`RetrySchedulerSource` / `RetrySchedulerDecision` / `SchedulerEngine`の配線を追加する一方、後者の解決は`RetryManager`へ`run_cycle()`等の統合APIを追加せず、次Execution Releaseで`RetryRuntimeOrchestrator`が`execute_dispatchable_retries()`を1回だけ呼び出しその結果を既存の公開Decider/Executor群へ配布する方針とし`retry_manager.py`を無改修に保つ設計判断としたこと、`queue` / `history` / `policy`を本Release時点から保持する理由（次Execution Releaseで確定的に必要になることが判明したため、Constructor変更の再往復を避けた）、`workflow_monitor` / `retry_queue` / `retry_history` / `retry_enqueue_trigger` / `retry_engine` / `workflow_engine` / `ai` / `execution_history` / `scheduler` / `retry_scheduler_source` / `retry_scheduler_decision`はいずれも無改修であることを明記）  
更新日：2026-07-09（v5.1.0 — Retry Composition Root Foundationを追記。新規パッケージ`src/retry_composition/`（`RetryCompositionRoot`）を追加し、`RetryQueueManager` / `RetryHistoryManager`を1インスタンスずつ生成して`RetryEnqueueTrigger`（Enqueue側）・`RetryManager`（Execute側）の両方へ同一インスタンスとして注入する設計判断。責務は「既存の`from_env()`/`from_config()`のみを使って組み立て、属性として公開すること」に限定し、実行順序の決定（`run_once()`等）・ループ・デーモン化・起動スクリプトはいずれも本Releaseの対象外としたこと、パッケージ配置は`src/retry_composition/`（既存16パッケージと同じドメインスコープの命名。汎用`src/runtime/`・`src/application/`は2つ目の消費者が存在しない段階での先回り抽象化として不採用）、クラス名は`RetryCompositionRoot`（「Runtime」は実行責任を連想させ本Releaseの責務境界と矛盾するため不採用。Architecture Reviewで一貫して使ってきた「Composition Root」という既存語彙を採用）としたこと、`workflow_monitor` / `retry_queue` / `retry_history` / `retry_enqueue_trigger` / `retry_engine` / `workflow_engine` / `ai` / `execution_history`はいずれも無改修であることを明記）  
更新日：2026-07-09（v5.0.0 — Retry Enqueue Guard Refinement Foundationを追記。`RetryEnqueueGuard`（v4.8.0）の判定基準を「再試行履歴が1回でもあればBLOCK」の二値判定から「`next_attempt > max_attempts` ならBLOCK」の回数比較判定へ精緻化した設計判断。`decide()`のシグネチャを`decide(run_id, has_history: bool)`から`decide(run_id, next_attempt: int, max_attempts: int)`へ変更し、`RetryHistoryManager`型・`RetryPolicy`（`retry_engine`）型のいずれも一切importしないStateless性は維持したこと、`RetryEnqueueTrigger.enqueue_pending_failures()`に`max_attempts: int = 1`を末尾のデフォルト値付き引数として追加し、`RetryEnqueueTrigger.__init__`は本Releaseでも完全に無変更としたこと（`max_attempts`をConstructor Injectionで保持する当初案をChatGPTレビューで再検討し、`limit`と同じ「呼び出しの都度渡す」スタイルへ変更したことで、Backward Compatibilityがさらに強くなったこと）、`max_attempts`省略時のデフォルト値`1`はv4.8.0/v4.9.0時点と完全に同一の挙動を再現する安全側の値であり、`RetryPolicy.max_attempts`（デフォルト3）とは意図的に独立した、`retry_engine`非依存を保つための構造的セーフガードであること、`RetryEnqueueOptions`等のDTO（Immutable Value Object）導入はYAGNI・Development Charter「抽象化は必要になってから行う」に従い本Releaseでは見送り、将来Policy値が複数に増えた場合の再検討基準を設計書へ明記したこと、`retry_history` / `retry_queue` / `workflow_monitor` / `retry_engine`はいずれも無改修であることを明記）  
更新日：2026-07-09（v4.9.0 — Retry Attempt Synchronization Foundationを追記。`RetryEnqueueTrigger.enqueue_pending_failures()`が`queue.enqueue()`呼び出し時に`retry_attempt`を渡しておらず常に`1`固定でQueueへ投入していた状態（v4.8.0 Known Issue）を踏まえ、`self._history.has_history()`の呼び出しを`self._history.get()`（既存の公開API）に置き換え、その戻り値から「履歴の有無」（`RetryEnqueueGuard`判定用）と「次のattempt番号（`RetryHistoryRecord.attempt_count + 1`、履歴なしは`1`）」（Queue登録用）の両方を導出するよう変更した設計判断。`RetryQueueItem.retry_attempt` → `RetryExecutionCoordinator.execute()` → `RetryManager.retry(attempt=...)` → `RetryPolicy.should_retry()`という下流への伝播経路は既に完成しており、本Releaseで追加した配線は`RetryEnqueueTrigger`内のこの1箇所のみであることをコード調査で確認したこと、`RetryEnqueueGuard`（v4.8.0）の判定基準（「履歴が1回でもあればBLOCK」の二値）自体は本Releaseでも無変更のため、`queue.enqueue()`に実際に到達するのは履歴なし（＝attempt=1）のケースのみであり、本Release単体では観測可能な挙動変化が発生しない「消費者不在の配線」であることを明記したこと、`RetryEnqueueTrigger.__init__`のシグネチャ・`RetryEnqueueTriggerResult`のフィールド・`src/retry_enqueue_trigger/__init__.py`の`__all__`はいずれも無変更でBackward Compatibilityを維持したこと、`retry_queue` / `retry_history` / `retry_engine` / `workflow_monitor` / `retry_enqueue_guard.py`はいずれも無改修であることを明記）  
更新日：2026-07-09（v4.8.0 — Retry Enqueue Guard層を追記。v4.6.0のKnown Issue（無限再投入リスク）・v4.7.0のFuture Extension「Retry Enqueue Guard」を接続し、無限再投入対策を完成させた設計判断。`RetryEnqueueTrigger.enqueue_pending_failures()`が`queue.enqueue()`時に`retry_attempt`を渡さず常に`1`固定でQueueへ投入するため`RetryPolicy.should_retry()`の`max_attempts`判定が実質機能せず、無対策では同一`run_id`が無制限に再実行されうることをコード調査で確認したこと、この対策として`RetryHistoryManager.has_history()`を参照する新規Stateless Decider`RetryEnqueueGuard`（`src/retry_enqueue_trigger/retry_enqueue_guard.py`）を追加したこと、判定基準を`retry_engine`への新規依存を避けるため「履歴の有無」の二値のみに意図的に限定したこと、`RetryEnqueueTrigger.__init__`へ`history` / `guard`引数を末尾のデフォルト値付きで追加しBackward Compatibilityを維持したこと、`workflow_monitor` / `retry_queue` / `retry_history` / `retry_engine`はいずれも無改修であること、副作用として`RETRY_MAX_ATTEMPTS`を活かした複数回リトライが本Release後も実質使えないという新たな制約が生じたことを明記）  
更新日：2026-07-09（v4.7.0 — Retry History Foundation層を追記。v4.6.0のKnown Issue（無限再投入リスク）が対策候補として挙げていた`metadata["retried_from"]`は、`WorkflowExecutionRecord`に`metadata`フィールドが存在せず実際には参照不可能であることが判明したため、情報源を`RetryResult`（`retry_engine`自身が生成するデータ）に限定した新規独立パッケージ`src/retry_history/`（`RetryHistoryManager` / `NullRetryHistoryManager`）と`retry_engine`側のStatelessコンポーネント`RetryHistoryRecordExecutor`を追加した設計判断。`RetryManager.record_retry_history()`は`execute_dispatchable_retries()`（v4.0.0、無変更）への委譲・`RetryHistoryRecordExecutor.record_all()`への委譲の2段階のみで完結する薄い委譲であること、`history`引数省略時は`RetryQueueManager`と同じ理由（stateful store）で`NullRetryHistoryManager()`にフォールバックすること、`retry_history`は`retry_engine`を一切importしないこと、記録のみに留め`RetryEnqueueTrigger`側の消費（無限再投入対策の完成）は次Release以降に送ったことを明記）  
更新日：2026-07-09（v4.6.0 — Retry Enqueue Trigger Foundation層を追記。v3.0.0〜v4.5.0の16回のReleaseで完成した「Queueから取り出して実行する」下流パイプラインに対し、「実際にQueueへ投入する」上流が存在しなかったギャップを埋める新規独立パッケージ`src/retry_enqueue_trigger/`（`RetryEnqueueTrigger` / `NullRetryEnqueueTrigger`）を追加した設計判断。`WorkflowMonitorManager.list_status()`でFAILED/TIMEOUTを検知し`RetryQueueManager.exists()`で重複を確認したうえで`enqueue()`する薄いAdapterであること、`retry_engine`は経由せず`workflow_monitor` / `retry_queue`に直接依存する構成（`retry_scheduler_source`と同じ「下位パッケージへの直接依存」パターン）であること、Feature Gate・Configクラスは追加せずNull Object Patternのみで有効/無効を表現すること、Queueから除去された`run_id`の無限再投入リスクを意図的に対策せずKnown Issueとして明記したこと、新設Adapterを定期的に駆動する起動スクリプト（Composition Root）は対象外（Non-Goal）であることを明記）  
更新日：2026-07-08（v4.5.0 — Retry Policy Foundation層を追記。`RetryManager`が実際に依存している面（`retry()`が呼び出す`should_retry(monitor_status, attempt) -> bool`、`_skip_reason()`が参照する`target_statuses` / `max_attempts`）をProtocolとして明示化した新規コンポーネント`RetryDecisionPolicy`（最小契約）・`ExplainableRetryPolicy`（`RetryDecisionPolicy`を拡張した説明可能契約）を追加した設計判断。既存`RetryPolicy`（v3.0.0）は本Releaseでも無改修（0 diff）のまま、Protocolの性質上明示的な継承なしに構造的に両契約を満たすこと、`RetryManager`の変更は`policy` / `retry_policy`引数の型注釈のみで`retry()` / `_skip_reason()`のロジック本体は無変更であること、新しいRetry戦略（`FixedRetryPolicy` / `ExponentialBackoffPolicy` / `AdaptiveRetryPolicy`等）の実装自体は本Releaseの対象外（Non-Goal）であることを明記）  
更新日：2026-07-08（v4.3.0 — Retry Queue Cleanup Foundation層を追記。`RetryQueueUpdateDecider`（v4.1.0）が判定した`RetryQueueUpdateDecision`のうち、`outcome`が`NOOP`かつ`retry_result.outcome`が`SKIPPED`（`max_attempts`到達）の項目についてのみ`RetryQueueManager.remove()`を呼び出す新規コンポーネント`RetryQueueCleanupDecider`（判定）・`RetryQueueCleanupExecutor`（除去実行）を追加した設計判断。v4.2.0で対象外だった`SKIPPED`由来のQueue滞留に対応する一方、`COMPLETE` / `FAILED`（v4.2.0で除去済みのはず） / `NOT_FOUND` / `DISABLED`はいずれも対象外（KEEP）のまま構造的に維持したCleanup方針、Dead Letter Queue等の新しいQueueステータスを追加せず既存の`RetryQueueManager.remove()`を再利用した判断を明記）  
更新日：2026-07-06（v4.1.0 — Retry Queue Update Foundation層を追記。`RetryManager.execute_dispatchable_retries()`（v4.0.0）が集約した`RetryExecutionResult`を対象に、対応するRetry Queue項目が`RetryQueueStatus.COMPLETED` / `FAILED`のどちらへ更新されるべきか（あるいは更新しないか）を判定する新規コンポーネント`RetryQueueUpdateDecider`を追加した設計判断。「再実行が実際に実行されたか」（`RetryResult.outcome == RETRIED`）を唯一の分岐点とし、`SKIPPED` / `NOT_FOUND` / `DISABLED`はいずれも`NOOP`（更新なし）に統一する判定方針、`RetryQueueManager.remove()`等への呼び出し経路を一切持たない境界、`retry_queue`パッケージへの変更が一切不要だった設計上の理由を明記）  
更新日：2026-07-06（v4.0.0 — Retry Execution Foundation層を追記。`RetryEventDispatcher`（v3.9.0）が整理した`RetryDispatchEvent`のうち`dispatchable=True`のものだけを対象に、初めて`RetryManager.retry()`を呼び出せる基盤を追加した設計判断。判定（`RetryExecutionSelector`）と実行・結果集約（`RetryExecutionCoordinator`）を責務分離したコンポーネント構成、`dispatchable=true`を唯一の実行入口として1箇所に集約する設計、新規コンポーネントがRetry Queueへ一切依存しない境界、`retry_attempt`を`getattr`による緩いダックタイピング＋フォールバックで取得する暫定実装であることを明記。あわせて、v3.7.0〜v3.9.0（Retry Scheduler Event Integration・Retry Engine Event Consumption・Retry Engine Event Dispatch）の個別セクションが本ドキュメントに未追記のままだった既知のギャップを踏まえ、Retry Queueから`RetryManager.retry()`に至る現在の全体パイプラインを新セクションに一括して整理した）  
更新日：2026-07-03（v3.6.0 — Retry Scheduler Decision Wiring層を追記。`SchedulerEngine`が`RetrySchedulerDecision`（v3.5.0）をConstructor Injectionで保持し、`select_candidates()` / `select_next_candidate()`という判定サイクルとは独立した読み取り専用2メソッドを追加した設計判断、`SchedulerEngine`自身は`RetrySchedulerDecision`を生成しないというユーザー承認済み方針、`retry_decision=None`時にガード節で`[]` / `None`を直接返す（Null Object Patternに依らない）フォールバック方式、`evaluate()` / `run_due()`の判定ロジックが無変更であることを明記）  
更新日：2026-07-03（v3.5.0 — Retry Scheduler Decision層を追記。`RetrySchedulerSource`が返す既存順序（priority昇順・enqueue_time昇順）から「次に処理すべき候補」を選ぶだけの新規独立コンポーネント`RetrySchedulerDecision`の設計判断、`retry_scheduler_decision → retry_scheduler_source`の新規一方向依存、`SchedulerEngine`を含む既存パッケージが本Releaseでも無改修であること、プロジェクト内で初めてNull Object Patternを採用しない意図的な判断を明記）  
更新日：2026-07-03（v3.4.0 — Retry Scheduler Wiring層を追記。`SchedulerEngine`が`RetrySchedulerSource` / `NullRetrySchedulerSource`（v3.3.0）をConstructor Injectionで保持し、`count_pending_retries()` / `list_pending_retries()`という判定サイクルとは独立した読み取り専用2メソッドを追加した設計判断、`scheduler → retry_scheduler_source`の新規一方向依存、`evaluate()` / `run_due()`の判定ロジックが無変更であること、`RetryQueueManager`を直接保持しない境界を明記）  
更新日：2026-07-03（v3.3.0 — Retry Scheduler Integration層を追記。Retry Queueの状態をScheduler側の語彙で読み取る新規Adapterパッケージ`src/retry_scheduler_source/`の設計判断、`retry_scheduler_source → retry_queue`の新規一方向依存、`src/scheduler/` / `src/retry_queue/` / `src/retry_engine/`が本Releaseでも無改修であること、Feature Gate/Config/Managerパターンを追加せずNull Object Pattern（`RetrySchedulerSource` / `NullRetrySchedulerSource`）で有効/無効を表現する設計、本Releaseでは誰からも呼び出されない「消費者不在の先行実装」であることを明記）  
更新日：2026-07-02（v3.2.0 — Retry Queue Integration層を追記。`RetryManager`が`RetryQueueManager`をDependency Injectionで保持し、`enqueue_retry()` / `dequeue_retry()`という薄い委譲メソッドで再実行対象をQueueへ登録・取得できるようにした設計判断、`retry_engine → retry_queue`の新規一方向依存、`src/retry_queue/`が本Releaseでも無改修であることを明記）  
更新日：2026-07-02（v3.1.0 — Retry Queue層を追記。再実行待ちの`run_id`を保持・出し入れするだけの新規パッケージ`src/retry_queue/`の設計判断、他のどの`src/*`パッケージもimportしない独立した葉パッケージであること、Retry Engineとの実配線は本Releaseでは未実施であることを明記）  
更新日：2026-07-02（v3.0.0 — Retry Engine層を追記。Workflow Monitorの公開APIのみを読み取り、Workflow Engineの公開APIのみを通じて再実行を依頼する新規パッケージ`src/retry_engine/`の設計判断、`retry_engine → workflow_engine` / `retry_engine → workflow_monitor`の一方向依存を明記）  
更新日：2026-07-02（v2.9.0 — Workflow Monitor層を追記。Execution Historyを唯一の情報源（Single Source of Truth）としてWorkflowの実行状態を判定するだけの新規パッケージ`src/workflow_monitor/`の設計判断、`workflow_monitor → execution_history`の一方向依存を明記）  
更新日：2026-07-02（v2.8.0 — Execution History層を追記。Workflow Engineが実行したWorkflowの観測・記録を担う新規パッケージ`src/execution_history/`の設計判断、`workflow_engine → execution_history`の一方向依存を明記）  
更新日：2026-07-02（v2.7.0 — Workflow Engine層を追記。Scheduler → Workflow Engine → NewsAgent → ReviewTriggerAgent → PublishTriggerAgentの関係、既存Agentの独立性を維持したまま上位オーケストレーション層を追加した設計判断を明記）  
更新日：2026-07-02（v2.6.0 — Scheduler層を追記。v2.6.0リリース時に未実施だった本追記を、v2.7.0ドキュメント整備時にあわせて実施。`docs/CHANGELOG.md` [KI-2]参照）  
更新日：2026-07-02（v2.5.0 — ReviewTriggerAgent → ReviewPipelineRunner → AiPublishReviewService の関係を追記。ReviewTriggerAgentのみ二重ゲートである理由を明記）  
更新日：2026-07-02（v2.4.0 — PublishTriggerAgent → PublishPipelineRunner → AiPublishService の関係を追記。v2.4.0リリース時に未実施だった本追記を、v2.5.0ドキュメント整備時にあわせて実施）  
更新日：2026-07-02（v2.3.0 — WorkflowTriggerAgent → WorkflowPipelineRunner → WorkflowRunner の関係を追記。Agent → Pipeline → Runner パターンをRelease 2.x標準アーキテクチャとして整理）  
更新日：2026-07-01（v2.2.0 — Pipeline層（実行層）を追記。News Agent → NewsPipelineRunner → main.py の関係を明記）  
更新日：2026-07-01（v2.1.0 — Workflow層・Agent層を追記。全体像を「出力アーキテクチャ」から「アプリケーション全体アーキテクチャ」へ拡張）

> 本ドキュメントは元々「出力アーキテクチャ（`OutputManager`まわり）」のみを扱っていましたが、
> v1.14.0〜v2.0.0でAI系の層（Workflow層・Agent層）が追加されたため、
> 全体像を俯瞰できるよう章を追加しました。
> 各バージョンの詳細な設計意図は `docs/design/` 配下の個別設計書を参照してください。

---

## 背景・目的

v1.0 では `main.py` に `_save_as_markdown()` が直書きされており、
出力先を追加するたびに `main.py` を修正する必要があった。

WordPress REST API 連携（v1.x）を追加するにあたり、
「どこへ出力するか」を差し替えやすい構造へ変更する。

---

## 現在（v1.0）の構造

```
main.py
  └─ _save_as_markdown()  ← Markdownへの保存処理が直書き
```

---

## 変更後（v1.1〜）の構造

```
main.py
  └─ output_manager.save_all(article)
       └─ OutputManager
            ├─ MarkdownOutput     ← v1.1 実装済み
            ├─ WordPressOutput    ← v1.1 実装済み
            ├─ NotionOutput       ← 将来
            └─ DiscordOutput      ← 将来
```

`main.py` は「何を出力するか（ArticleData）」だけを知り、
「どこへ出力するか」は `OutputManager` に委ねる。

---

## ディレクトリ構成

```
src/
├── image_extractor.py       # RSSエントリーから画像URL候補を抽出（v1.3 追加）
├── image_resolver.py        # アイキャッチ画像候補URLを解決（v1.4 追加）
├── slug_generator.py        # WordPress slug を生成（v1.5 追加）
├── publishing_config.py     # PublishStatus Enum・PublishingConfig dataclass（v1.7 追加）
└── outputs/
    ├── __init__.py          # OutputManager, MarkdownOutput, ArticleData を公開
    ├── base.py              # ArticleData dataclass / BaseOutput 抽象クラス
    ├── manager.py           # OutputManager
    ├── markdown_output.py   # MarkdownOutput（実装済み）
    ├── taxonomy_config.py   # カテゴリ・タグIDの設定（v1.2 追加）
    └── wordpress_output.py  # WordPressOutput（v1.1 実装済み）
```

---

## 各クラスの責務

### ImageResolver（`image_resolver.py`）（v1.4 追加）

アイキャッチ画像候補URLと WordPress media_id を解決するモジュール。

| 関数 | 役割 |
|------|------|
| `resolve_featured_image(item)` | NewsItem から使用する画像URLを1件選んで返す（Markdown記録用） |
| `resolve_media_id(item, default_media_id)` | WordPress に設定する featured_media の ID を返す（v1.6 追加） |

`resolve_media_id()` は v1.6.0 では `image_terms_confirmed == False` のため常に `default_media_id` を返す。v1.7.0 以降で `True` の場合に `MediaUploader` 経由でアップロード結果の ID を返す拡張ポイントとして設計。

### ArticleData（`base.py`）

記事生成結果をまとめて出力処理に渡すデータクラス。

| フィールド | 型 | 内容 |
|-----------|-----|------|
| `item` | `NewsItem` | 元ニュース情報（タイトル・URL・ソース等） |
| `importance` | `str` | 重要度（S / A / B） |
| `seo_title` | `str` | AIが生成したSEOタイトル |
| `article_body` | `str` | AIが生成した記事本文 |
| `x_post` | `str` | AIが生成したX投稿文 |
| `featured_image_url` | `str` | アイキャッチ画像候補URL（v1.3 追加、空文字 = なし） |
| `excerpt` | `str` | WordPress抜粋・Markdown記録用（v1.4 追加、空文字 = なし） |
| `meta_description` | `str` | 将来のSEOプラグイン連携用（v1.4 追加、現在はexcerptと同値） |
| `slug` | `str` | WordPress slug（v1.5 追加、空文字 = なし） |
| `featured_media_id` | `int` | WordPress media_id（v1.6 追加、0 = アイキャッチなし） |
| `publish_status` | `PublishStatus` | WordPress 投稿ステータス（v1.7 追加、デフォルト = DRAFT） |

### BaseOutput（`base.py`）

全出力クラスの抽象基底クラス。

| メソッド | 返り値 | 役割 |
|---------|-------|------|
| `save(article)` | `str` | 記事を保存・投稿する。保存先を示す文字列を返す |
| `is_available()` | `bool` | この出力先が利用可能かを返す（APIキー不足などを検知） |

### MarkdownOutput（`markdown_output.py`）

`output/` フォルダへのMarkdownファイル保存を担う。
v1.0 の `_save_as_markdown()` をクラスとして移植したもの。
`is_available()` は常に `True`（ディスク書き込みは常に可能とみなす）。

### OutputManager（`manager.py`）

複数の `BaseOutput` を受け取り、`save_all()` で全出力先に一括保存する。

- 1つの出力先が失敗しても他の出力先への保存は続行する
- `is_available()` が `False` の出力先はスキップする
- 保存に成功した保存先文字列のリストを返す

---

## main.py からの呼び出し

```python
# 起動時に1回だけ初期化
output_manager = OutputManager(outputs=[
    MarkdownOutput(output_dir=OUTPUT_DIR),
    WordPressOutput.from_env(),  # .env 未設定時は is_available()=False で自動スキップ
])

# 記事生成後の保存（v1.6.0 以降）
excerpt            = _extract_excerpt(article_body)            # ルールベース・API追加なし
featured_image_url = resolve_featured_image(item)              # Markdown記録用URL（v1.4 追加）
featured_media_id  = resolve_media_id(item, default_media_id)  # WordPress media_id（v1.6 追加）
article = ArticleData(
    item=item,
    importance=importance,
    seo_title=seo_title,
    article_body=article_body,
    x_post=x_post,
    featured_image_url=featured_image_url,
    excerpt=excerpt,
    meta_description=excerpt,    # v1.4.0 では excerpt と同値
    slug=slug,                   # v1.5 追加
    featured_media_id=featured_media_id,  # v1.6 追加
)
destinations = output_manager.save_all(article)
```

---

## 将来の拡張手順

新しい出力先（Notion・Discord など）を追加する場合：

1. `src/outputs/` に新しいクラスファイルを作成し `BaseOutput` を継承する
2. `save()` と `is_available()` を実装する
3. `src/outputs/__init__.py` でエクスポートする
4. `main.py` の `OutputManager([...])` に追加する

**既存ファイルへの変更は最小限（main.py の1行追加のみ）。**

---

## 全体構成（v2.5.0 時点）

`main.py`（投稿処理）とは別に、`src/ai/` 配下に投稿後の改善サイクルおよび判断層が、
`src/pipeline/` 配下に実行層が育っている。いずれも独立して実行され、`main.py` は
Workflow層・Agent層・Pipeline層を呼び出さない（呼ばれる側に徹する）。

```
main.py（記事収集・投稿）
  └─ output_manager.save_all(article)   ← 本ドキュメント前半の「出力アーキテクチャ」

scripts/run_news_agent.py（ニュース収集の実行要否判断・main.pyとは独立実行）
  └─ AgentManager（判断）
       └─ NewsAgent                     ← Agent層（v2.2.0、判断のみ）
            └─ NewsPipelineRunner       ← Pipeline層（v2.2.0、実行のみ）
                 └─ main.py（subprocess起動。無改修）

scripts/run_workflow_trigger_agent.py（Workflowの実行要否判断・main.pyとは独立実行）
  └─ AgentManager（判断）
       └─ WorkflowTriggerAgent          ← Agent層（v2.3.0、判断のみ）
            └─ WorkflowPipelineRunner   ← Pipeline層（v2.3.0、実行のみ。subprocessは使わない）
                 └─ WorkflowRunner（直接呼び出し。無改修）
                      └─ WorkflowStepExecutor × 6（下記と同一の6ステップ）

scripts/run_publish_trigger_agent.py（Publishの実行要否判断・main.pyとは独立実行）
  └─ AgentManager（判断）
       └─ PublishTriggerAgent           ← Agent層（v2.4.0、判断のみ）
            └─ PublishPipelineRunner    ← Pipeline層（v2.4.0、実行のみ。subprocessは使わない）
                 └─ AiPublishService（直接呼び出し。無改修）

scripts/run_review_trigger_agent.py（公開前レビューレポート生成の実行要否判断・main.pyとは独立実行）
  └─ AgentManager（判断）
       └─ ReviewTriggerAgent            ← Agent層（v2.5.0、判断のみ、二重ゲート）
            └─ ReviewPipelineRunner     ← Pipeline層（v2.5.0、実行のみ。subprocessは使わない）
                 └─ AiPublishReviewService（直接呼び出し。無改修）

scripts/run_ai_workflow.py（投稿後の改善サイクルの手動一括実行・main.pyとは独立実行）
  └─ WorkflowRunner（実行）              ← Workflow層（v1.20.0）。Agent層を経由しない直接実行
       └─ WorkflowStepExecutor × 6
            ├─ Improvement       （v1.14.0 AiImprovementService）
            ├─ ImprovementReview （v1.15.0 ImprovementReviewService）
            ├─ Rewrite           （v1.16.0 RewriteService）
            ├─ RewriteReview     （v1.17.0 RewriteReviewService）
            ├─ Publish           （v1.18.0 AiPublishService）
            └─ PublishReview     （v1.19.0 AiPublishReviewService）
```

`scripts/run_ai_workflow.py`（人間が手動で一括実行）と`scripts/run_workflow_trigger_agent.py`（Agentが実行要否を判断してから実行）は、どちらも最終的に同じ`WorkflowRunner`・同じ6ステップへたどり着くが、**経路が異なる**（前者はAgent層を経由しない直接実行、後者はAgent層＋Pipeline層を経由する）。

各層の役割：

| 層 | 実装 | 責務 |
|---|---|---|
| Agent層 | `AgentManager` / `AgentExecutor` / `BaseAgent` | 「今、何かを実行すべきか」を**判断**する。実行そのものは行わない |
| Pipeline層 | `NewsPipelineRunner` / `WorkflowPipelineRunner` / `PublishPipelineRunner` / `ReviewPipelineRunner` / `PipelineResult` | Agent層から渡されたタスクを実際に**実行**する。Agent層には依存しない |
| Workflow層 | `WorkflowRunner` / `WorkflowStepExecutor` | 決まった6ステップを、決まった順序で**実行**する |
| Service層 | `AiImprovementService` 等 | 各ステップの実処理（Claude API呼び出し・WordPress投稿・レポート生成） |

詳細は次項および各 `docs/design/*.md` を参照。

---

## Workflow層（`src/ai/workflow_*.py`、v1.20.0 追加）

`WorkflowRunner` は、v1.14.0〜v1.19.0で個別に実装した6つのServiceを、決まった順序で呼び出すオーケストレーター。

- `WorkflowStep` Enum：`IMPROVEMENT` → `IMPROVEMENT_REVIEW` → `REWRITE` → `REWRITE_REVIEW` → `PUBLISH` → `PUBLISH_REVIEW`
- `WorkflowRunner` は各Serviceを直接importしない。`WorkflowStepExecutor`（ステップごとのラッパー）をコンストラクタでDIすることで、Workflow層とService層の責務を分離している
- `AI_WORKFLOW_ENABLED=false` の場合は `NullWorkflowRunner` を返す（Configuration First）
- 実行結果は `WorkflowResult`（`overall_success` / `total_processed` / `steps` / `warnings`）にまとめられ、`WorkflowReportBuilder` がMarkdownレポートを生成する

詳細設計：`docs/design/ai_workflow_foundation.md`

---

## Agent層（`src/ai/agent_*.py`、v2.0.0 追加）

`AgentManager` は、Workflow層のさらに上位に位置する「判断」レイヤー。

- **Workflowを置き換えるものではない**。「今、Workflowを実行すべきかどうか」を判断する上位概念として設計されている
- `BaseAgent`（ABC）は `decide()`（判断のみ・副作用なし）と `act()`（`should_act=True`かつ`dry_run=False`の場合のみ呼ばれる実行）に責務を分離
- `AgentExecutor` が `decide()` → `act()` の呼び出し順序・`dry_run`判定・実行時刻の計測を一括管理する（`BaseAgent`実装側はこれらを意識しなくてよい）
- `AgentManager.run()` はタスクごとに新しい `run_id` を発行し、登録された `AgentExecutor` に実行させ、`AgentResult` のリストを返す
- v2.0.0時点では `BaseAgent` の具体的な実装（News Agent等）はまだ存在せず、`AgentManager.from_config()` は `is_ready()=True` でも `executors=[]`（空リスト）を返す。**次の具体的なAgent実装（News Agent / Workflow Trigger Agent）を追加するための骨組みのみが完成した状態**
- v2.5.0時点では `NewsAgent`（v2.2.0）・`WorkflowTriggerAgent`（v2.3.0）・`PublishTriggerAgent`（v2.4.0）・`ReviewTriggerAgent`（v2.5.0）の4つの具体的なAgent実装が揃っている（後述「Agent → Pipeline → Runner パターン」参照）
- デフォルトは無効（`AI_AGENT_ENABLED=false`）。既存の `WorkflowRunner` 経由の自動実行フローには影響しない

詳細設計：`docs/design/agent_foundation.md`

### 新しいAgentを追加する場合（将来手順）

1. `src/ai/` に `BaseAgent` を継承した新しいAgentクラスを作成し、`decide()` / `act()` / `name()` を実装する
2. `AgentManager.from_config()` 内で、新しいAgentを包んだ `AgentExecutor` を `executors` リストに追加する（DI）
3. 必要であれば `AgentConfig` に判断材料となる設定値を追加する

**Workflow層・Service層への変更は不要（Agent層はWorkflowを呼び出す側であり、呼び出される側ではない）。**

---

## Pipeline層（`src/pipeline/`、v2.2.0 / v2.3.0 / v2.4.0 / v2.5.0 追加）

対応するAgentが「実行すべき」と判断した後、実際の処理を担う実行層。設計レビューの結果、
「Agentが実行手段（subprocess等）を直接扱う」設計は責務混同を招くと判断され、Agent層とは別パッケージとして分離した。

### NewsPipelineRunner（`src/pipeline/news_pipeline_runner.py`、v2.2.0 追加）

- **Agent＝判断、PipelineRunner＝実行**：`NewsAgent`は`NewsPipelineRunner.run(params) -> PipelineResult`という薄いインターフェースのみを呼び、実行方式（subprocess／将来的なimport呼び出し／API呼び出し等）を一切知らない
- `NewsPipelineRunner`は`main.py`をsubprocessとして起動する。`main.py`本体は無改修（`argparse`が`sys.argv`を読む・複数箇所で`sys.exit()`を呼ぶという既存の実装特性上、直接importして呼び出すとAgentプロセスごと道連れにするリスクがあるため、プロセスとして隔離している）

```
NewsAgent（判断）
  └─ NewsPipelineRunner.run(params)（実行）
       └─ subprocess.run([python_executable, main_py_path], cwd=working_directory, timeout=timeout_sec)
            └─ main.py（無改修。既存のニュース収集パイプラインをそのまま実行）
```

詳細設計：`docs/design/news_agent_foundation.md`

### WorkflowPipelineRunner（`src/pipeline/workflow_pipeline_runner.py`、v2.3.0 追加）

- **Agent＝判断、PipelineRunner＝実行**：`WorkflowTriggerAgent`は`WorkflowPipelineRunner.run(params) -> PipelineResult`という薄いインターフェースのみを呼び、`WorkflowRunner`のクラス名・呼び出しシグネチャを一切知らない
- `WorkflowPipelineRunner`は`WorkflowRunner.run()`を**直接呼び出す**（subprocessは使わない）。`WorkflowRunner`は通常のPythonクラスであり、`main.py`のような`argparse`/`sys.exit()`問題を持たないため、プロセス分離が不要と判断された（`NewsPipelineRunner`との実行方式の違いは、実行対象それぞれの実装特性に起因するものであり、Pipeline層の設計原則自体の違いではない）
- `ai`パッケージのimportは`run()`メソッド内に遅延させている。これにより`src/pipeline/`が`src/ai/`をimportする形になっても、`pipeline → ai → pipeline`という循環importを構造的に回避している

```
WorkflowTriggerAgent（判断）
  └─ WorkflowPipelineRunner.run(params)（実行）
       └─ WorkflowRunner.from_config(...).run(article_id=..., dry_run=...)（直接呼び出し。無改修）
            └─ WorkflowStepExecutor × 6（Improvement〜PublishReview）
```

詳細設計：`docs/design/workflow_trigger_agent_foundation.md`

### PublishPipelineRunner（`src/pipeline/publish_pipeline_runner.py`、v2.4.0 追加）

- **Agent＝判断、PipelineRunner＝実行**：`PublishTriggerAgent`は`PublishPipelineRunner.run(params) -> PipelineResult`という薄いインターフェースのみを呼び、`AiPublishService`のクラス名・呼び出しシグネチャを一切知らない
- `PublishPipelineRunner`は`AiPublishService.run()`を**直接呼び出す**（subprocessは使わない）。`WorkflowPipelineRunner`と同じ理由（`AiPublishService`が通常のPythonクラスであり`argparse`/`sys.exit()`問題を持たないため）
- `ai`パッケージのimportは`run()`メソッド内に遅延させ、`pipeline → ai → pipeline`という循環importを構造的に回避している

```
PublishTriggerAgent（判断）
  └─ PublishPipelineRunner.run(params)（実行）
       └─ AiPublishService.from_env(base_dir=...).run(article_id=...)（直接呼び出し。無改修）
```

詳細設計：`docs/design/publish_trigger_agent_foundation.md`

### ReviewPipelineRunner（`src/pipeline/review_pipeline_runner.py`、v2.5.0 追加）

- **Agent＝判断、PipelineRunner＝実行**：`ReviewTriggerAgent`は`ReviewPipelineRunner.run(params) -> PipelineResult`という薄いインターフェースのみを呼び、`AiPublishReviewService`のクラス名・呼び出しシグネチャを一切知らない
- `ReviewPipelineRunner`は`AiPublishReviewService.run()`を**直接呼び出す**（subprocessは使わない）。`PublishPipelineRunner`と同じ理由
- `ai`パッケージのimportは`run()`メソッド内に遅延させ、`pipeline → ai → pipeline`という循環importを構造的に回避している

```
ReviewTriggerAgent（判断）
  └─ ReviewPipelineRunner.run(params)（実行）
       └─ AiPublishReviewService.from_paths(base_dir=...).run(article_id=...)（直接呼び出し。無改修）
```

詳細設計：`docs/design/review_trigger_agent_foundation.md`

### 全Runnerに共通する設計原則

- **Pipeline層はAgent層に依存しない**：`src/pipeline/`配下のモジュールは`AgentContext` / `AgentDecision` / `AgentResult`等のAgent層の型を一切importしない。設定値の受け渡しは`Protocol`によるダックタイピングで行う
- 実行結果は共通の`PipelineResult`（`success` / `returncode` / `elapsed_sec` / `stdout_log_path` / `stderr_log_path` / `error_message`）にまとめられ、各Agentがこれを`AgentResult`へ変換する（`workflow_result`は常に`None`）
- `dry_run=True`の場合、`AgentExecutor`（v2.0.0の既存設計）により`act()`自体が呼ばれないため、PipelineRunnerの`run()`は構造的に発生しない（`NewsAgent` / `WorkflowTriggerAgent` / `PublishTriggerAgent` / `ReviewTriggerAgent`共通の保証）
- **`NewsAgent`系・`WorkflowTriggerAgent`系・`PublishTriggerAgent`系・`ReviewTriggerAgent`系は互いに独立したPipelineを持つ**：`NewsPipelineRunner` / `WorkflowPipelineRunner` / `PublishPipelineRunner` / `ReviewPipelineRunner`は互いをimportせず、依存関係を持たない

### 新しいPipelineRunnerを追加する場合（将来手順）

将来のScheduler Agent等も、同じ形の実行層を追加していく想定。

1. `src/pipeline/` に新しいRunnerクラスを作成し、`run(params) -> PipelineResult`を実装する
2. 対応するAgentの`act()`から、そのRunnerの`run()`のみを呼ぶ
3. 共通インターフェース（`Protocol`/ABC）への抽出は、v2.5.0時点で4実装（`NewsPipelineRunner` / `WorkflowPipelineRunner` / `PublishPipelineRunner` / `ReviewPipelineRunner`）が揃った後も引き続き見送っている（各design docのFuture Extensions参照。抽象化の必要性が具体的に生じた時点で再検討する）

**Agent層への変更は不要（Pipeline層はAgentから呼ばれる側であり、Agent層の型を知る必要がない）。**

---

## Agent → Pipeline → Runner パターン（Release 2.x 標準アーキテクチャ）

v2.2.0（News Agent Foundation）・v2.3.0（Workflow Trigger Agent Foundation）・v2.4.0（Publish Trigger Agent Foundation）・v2.5.0（Review Trigger Agent Foundation）を通じて、以下の3層パターンがRelease 2.x系のAgent実装における標準アーキテクチャとして確立した。

```
[判断] BaseAgent実装（decide() / act()）
   ↓
[実行] PipelineRunner実装（run(params) -> PipelineResult）
   ↓
[対象] 既存の資産（main.py / WorkflowRunner / AiPublishService / AiPublishReviewService等、無改修のまま呼び出される）
```

| Agent（判断） | Pipeline層（実行） | 実行対象 | 実行方式 |
|---|---|---|---|
| `NewsAgent`（v2.2.0） | `NewsPipelineRunner` | `main.py` | subprocess起動（`argparse`/`sys.exit()`問題を隔離するため） |
| `WorkflowTriggerAgent`（v2.3.0） | `WorkflowPipelineRunner` | `WorkflowRunner` | 直接呼び出し（`WorkflowRunner`にsubprocess化が必要な問題がないため） |
| `PublishTriggerAgent`（v2.4.0） | `PublishPipelineRunner` | `AiPublishService` | 直接呼び出し（`AiPublishService`にsubprocess化が必要な問題がないため） |
| `ReviewTriggerAgent`（v2.5.0） | `ReviewPipelineRunner` | `AiPublishReviewService` | 直接呼び出し（`AiPublishReviewService`にsubprocess化が必要な問題がないため） |

このパターンに共通する設計原則：

1. Agentは「判断」のみを行い、副作用（実際の起動）を持たない（`decide()`は読み取り専用）
2. Agentは実行対象（`main.py` / `WorkflowRunner` / `AiPublishService` / `AiPublishReviewService`）を直接importしない。実行方式はPipelineRunnerに完全に閉じ込める
3. PipelineRunnerはAgent層の型（`AgentContext`等）をimportしない（`ai → pipeline`の一方向依存が原則。ただし`WorkflowPipelineRunner` / `PublishPipelineRunner` / `ReviewPipelineRunner`のように実行対象自体が`ai`パッケージ内にある場合は、遅延importにより循環を避けたうえでこれを呼び出すことが許容される）
4. PipelineRunnerの実行方式（subprocessか直接呼び出しか）は、実行対象の実装特性（`sys.exit()`の有無等）によって決まる。パターン自体は変わらない
5. **各Agent系は互いに独立したPipelineを持つ**（`NewsAgent`系・`WorkflowTriggerAgent`系・`PublishTriggerAgent`系・`ReviewTriggerAgent`系）。`AgentManager`の`executors`リストにそれぞれ独立したエントリとして並び、実行層同士が依存し合うことはない
6. `dry_run=True`の場合、`AgentExecutor`の既存保証により`act()`自体が呼ばれないため、PipelineRunnerの`run()`は構造的に発生しない

### Gate方式のバリエーション

対象Serviceの性質に応じて、DI時のゲート段数が異なる。

| Agent | Gate方式 | 内訳 |
|---|---|---|
| `NewsAgent`（v2.2.0） | 単一ゲート | `AI_AGENT_ENABLED`のみ（`main.py`自体に独立した有効/無効フラグがないため） |
| `WorkflowTriggerAgent`（v2.3.0） | 三重ゲート | `AI_AGENT_ENABLED` × `WORKFLOW_TRIGGER_AGENT_ENABLED` × `AI_WORKFLOW_ENABLED`（`WorkflowConfig.is_ready()`を再利用） |
| `PublishTriggerAgent`（v2.4.0） | 三重ゲート | `AI_AGENT_ENABLED` × `PUBLISH_TRIGGER_AGENT_ENABLED` × `AiPublishConfig.is_ready()`（`AI_PUBLISH_ENABLED`＋WordPress認証情報3点） |
| `ReviewTriggerAgent`（v2.5.0） | **二重ゲート** | `AI_AGENT_ENABLED` × `REVIEW_TRIGGER_AGENT_ENABLED`のみ |

**`ReviewTriggerAgent`のみ二重ゲートである理由**：

- 対象の`AiPublishReviewService`（v1.19.0）には、`WorkflowConfig` / `AiPublishConfig`のような独自の`Config`クラス・`is_ready()`相当の判定が**存在しない**ため、3段目として再利用できる既存の判定がない
- 3段目を実現するために`AiPublishReviewService`側へ`Config`を後付けすることは、対象Service本体の改修になり「既存Service本体は改修しない」という方針に反するため行わない
- そのため`AI_AGENT_ENABLED` × `REVIEW_TRIGGER_AGENT_ENABLED`の二重ゲートで確定し、デフォルト無効（`REVIEW_TRIGGER_AGENT_ENABLED=false`）という安全側の初期状態は維持している

詳細は`docs/design/review_trigger_agent_charter.md`（Open Question #1）・`docs/design/review_trigger_agent_foundation.md` §6を参照。

将来のScheduler Agent（Windowsタスクスケジューラ統合）も同じパターンで追加していく想定。詳細は`docs/design/news_agent_foundation.md` §16、`docs/design/workflow_trigger_agent_foundation.md` §16、`docs/design/publish_trigger_agent_foundation.md` §16、`docs/design/review_trigger_agent_foundation.md` §16（各Future Extensions）を参照。

---

## Scheduler層（`src/scheduler/`、v2.6.0 追加）

> このセクションはcommit `0d28d30`時点で本ドキュメントへの追記が漏れていたため、v2.7.0ドキュメント整備作業（2026-07-02）で遡及的に追加したものです（`docs/CHANGELOG.md` [KI-2]参照）。

`src/scheduler/`は、「いつ実行すべきか」を判定するだけの独立パッケージ。`SchedulerEngine.evaluate(jobs, now)`は副作用のない純粋関数で、登録された`SchedulerJob`一覧と現在時刻から、実行対象と判定された`SchedulerJob`ごとに`SchedulerEvent`を生成して返す。

```
SchedulerJob（登録） → SchedulerManager（管理） → SchedulerRepository（保持、v2.6.0はInMemoryのみ）
    → SchedulerEngine.evaluate(jobs, now)（判定） → SchedulerEvent（生成）
```

- **Event Driven Architectureの原則**：Schedulerは`NewsAgent` / `ReviewTriggerAgent` / `PublishTriggerAgent`等の既存Trigger Agentを一切importせず、直接呼び出すこともしない。`SchedulerEvent`を生成するところで責務が終わる。「判断」と「実行」の分離を、`src/ai/` / `src/pipeline/`への依存を一切持たないパッケージ構成そのもので体現している
- v2.6.0時点では`SchedulerEvent`を受け取って実際にAgentを起動する呼び出し元が存在しなかった（Foundation Releaseのため、判定エンジンの骨組みのみ）。この接続は次項のWorkflow Engine層（v2.7.0）で実装された
- デフォルトは無効（`SCHEDULER_ENABLED=false`）
- Foundation Releaseのため、cron完全互換ではない（`TriggerType`はDAILY / INTERVAL / ONCEの3種類のみ、分単位マッチング）。永続化（`InMemorySchedulerRepository`のみ）・retry・`last_run_at`保持・Windows Task Scheduler / Linux cron連携はいずれも対象外（将来Releaseの拡張候補）

---

## Workflow Engine層（`src/workflow_engine/`、v2.7.0 追加）

Scheduler（v2.6.0）が生成する`SchedulerEvent`を起点に、既存3つのTrigger Agent（`NewsAgent` v2.2.0 → `ReviewTriggerAgent` v2.5.0 → `PublishTriggerAgent` v2.4.0）を決まった順序で実行する、Agent層のさらに上位に位置するオーケストレーション層。

```
Scheduler            （判断：今このJobを実行すべきか、v2.6.0、無改修）
   ↓ SchedulerEvent
Workflow Engine        （実行：登録されたステップを順序どおりに実行する、v2.7.0）
   ↓
NewsAgent             （既存、v2.2.0、無改修）
   ↓
ReviewTriggerAgent    （既存、v2.5.0、無改修）
   ↓
PublishTriggerAgent   （既存、v2.4.0、無改修）
```

### 既存Agentの独立性を維持していること

v2.2.0〜v2.5.0で確立した「各Agent系は互いに独立したPipelineを持つ」という原則（上記「Agent → Pipeline → Runner パターン」参照）は、Workflow Engineの追加によって破棄されていない。

- `WorkflowEngineManager`は`AgentManager`（v2.0.0）を経由せず、既存の`NewsAgent` / `ReviewTriggerAgent` / `PublishTriggerAgent`とそれぞれの`Config` / `PipelineRunner`を無改修のままimportし、独自にインスタンスを構築する（`docs/design/workflow_engine_foundation.md` 8.2節「案B」）
- `AgentManager` / `AgentExecutor` / `BaseAgent` / 既存4 Trigger Agent・Scheduler本体はいずれも無改修。`scripts/run_news_agent.py`等、`AgentManager`を経由する既存の個別実行経路は従来どおり利用できる
- Workflow Engineは「独立したAgent群」という既存モデルの**上に**「決まった順序で呼び出す」層を追加したものであり、置き換えではない

### 名前空間の分離

`src/workflow_engine/`のクラスはすべて`WorkflowEngine`接頭辞を持ち、`src/ai/workflow_*.py`（v1.20.0、AI記事改善6ステップ用の`WorkflowStep` / `WorkflowContext` / `WorkflowResult`等）とはパッケージ・クラス名の両方で分離されている（`WorkflowEngineStep` vs `WorkflowStep`等）。両者は対象が異なる別物であり、混同しないこと。

### Gate二層構造

| 層 | ゲート |
|---|---|
| Workflow Engine全体（二重ゲート） | `AI_AGENT_ENABLED`（`AgentConfig.is_ready()`） × `WORKFLOW_ENGINE_ENABLED`（`WorkflowEngineConfig.is_ready()`） |
| NEWSステップ | 常に有効（`NewsAgentConfig`にゲートが存在しないため） |
| REVIEWステップ | `ReviewTriggerAgentConfig.is_ready()`（`REVIEW_TRIGGER_AGENT_ENABLED`）を再利用 |
| PUBLISHステップ | `PublishTriggerAgentConfig.is_ready()`（`PUBLISH_TRIGGER_AGENT_ENABLED` × `AiPublishConfig.is_ready()`）を再利用 |

ステップ別ゲートが閉じている場合、そのステップは`WorkflowEngineExecutor`側で「スキップ」（`success=True`）として扱われ、後続ステップの実行は継続する。

### 打ち切り基準

「実行した結果として失敗した（`AgentResult.success=False`）」場合のみ後続ステップを打ち切る。Gate閉鎖・`decide()`による`should_act=False`判断は失敗として扱わず、後続ステップの実行を継続する。打ち切りが発生した場合も、未到達のステップは`WorkflowEngineResult.steps`に`skipped_reason=REASON_NOT_REACHED`として記録され、`steps`の件数は常に`WorkflowEngineDefinition.steps`と同じ件数になる。

### `scripts/run_workflow_engine.py` の使い方と運用上の注意

```bash
cd projects/03_game_content_ai
./venv/Scripts/python.exe scripts/run_workflow_engine.py              # Scheduler判定経由
./venv/Scripts/python.exe scripts/run_workflow_engine.py --dry-run    # dry-run（副作用なし）
./venv/Scripts/python.exe scripts/run_workflow_engine.py --job-id manual-run  # Scheduler判定を経由しない手動起動
```

前提条件（.env、二重ゲート）：`AI_AGENT_ENABLED=true` かつ `WORKFLOW_ENGINE_ENABLED=true`。Review/Publishステップを実際に動かすには、それぞれ`REVIEW_TRIGGER_AGENT_ENABLED=true` / `PUBLISH_TRIGGER_AGENT_ENABLED=true`（+ WordPress認証情報3点）も必要。

運用上、以下の点に注意すること（詳細は`docs/design/workflow_engine_foundation.md` 13.1節）。

1. **固定・最小限（1件のみ）のデモJobを扱う**：`scripts/run_workflow_engine.py`は、Scheduler経由で実行する場合に`job_id="workflow_engine_demo_daily"`（DAILY / `09:00`固定）のデモJobを1件だけ登録する。複数Jobの登録・Job定義の設定ファイル化・実行時の動的登録は現時点では対応していない（Future Extensions）
2. **既存script群との同時実行を避けること**：`scripts/run_news_agent.py` / `scripts/run_review_trigger_agent.py` / `scripts/run_publish_trigger_agent.py` / `scripts/run_workflow_trigger_agent.py`など、`AgentManager`経由の既存script群と`scripts/run_workflow_engine.py`を同時に手動実行しないこと
3. **ロック機構は未実装**：`decide()`の判断から`act()`完了（ファイル書き込みによるmtime更新）までの間、いかなるロックも存在しない。上記1・2を守らずに同時実行した場合、News収集・レビューレポート生成・**WordPress下書き投稿**などが二重に発生するリスクがある
4. **短い間隔での連続起動も避けること**：`SchedulerEngine`（v2.6.0）は`last_run_at`を保持しないため、`scripts/run_workflow_engine.py`自体を短い間隔で繰り返し起動すると、同一分内で同じ`SchedulerEvent`が繰り返し発火し、上記3のリスクをさらに増幅させる可能性がある

これらはRelease 2.7時点でロック実装を見送り、運用制約として明記するにとどめた既知の制約である（Development Charter 6章「技術的負債との向き合い方」に従い、可視化・理由・将来の解消タイミングの3条件を満たす形で`docs/design/workflow_engine_foundation.md` 17章 Future Extensionsに記録済み）。

### 新しいステップをWorkflow Engineへ追加する場合（将来手順）

1. `WorkflowEngineStep`に新しいメンバーを追加する（既存メンバーの意味は変えない）
2. 対応する既存Agent（またはPipeline構成）を、`WorkflowEngineManager.from_config()`内に他ステップと同じ形で構築するブロックを追加する
3. `ALL_WORKFLOW_ENGINE_STEPS`の並び順を、新しいステップを含めて更新する
4. Agent層・Pipeline層・Scheduler層への変更は不要（Workflow Engine層は既存資産を呼ぶ側であり、呼ばれる側ではない）

詳細は`docs/design/workflow_engine_foundation.md`（Project Charter・Architecture Design）を参照。

---

## Execution History層（`src/execution_history/`、v2.8.0 追加）

Workflow Engine（v2.7.0）が実行した各Workflowについて、「いつ・何が・どういう順序で・成功したか失敗したか」を**観測して記録するだけ**の最小基盤。

```
Scheduler        （判断、v2.6.0、無改修）
   ↓ SchedulerEvent
Workflow Engine    （実行、v2.7.0）─────観測─────→ Execution History（記録のみ、v2.8.0）
   ↓                                                    ↓
NewsAgent → ReviewTriggerAgent → PublishTriggerAgent   logs/execution_history/*.json
```

### 責務の境界（原則）

- **Execution Historyは「実行の観測・記録」のみを担当する。** Workflow Engineの実行判断・分岐・打ち切り基準（`workflow_engine_foundation.md` 8.3節）には一切関与しない。どのステップを実行するか・どこで打ち切るかは引き続き`WorkflowEngineExecutor`が単独で決定し、Execution Historyはその結果を受け取って記録するだけである
- **Release 2.8では履歴は記録専用。** Retry Engine・Workflow Monitor・Metrics Foundation・Dashboard Foundationは、いずれも本層が保存した履歴データを将来消費する側であり、v2.8.0では実装しない
- **`workflow_engine` → `execution_history`の一方向依存を維持する。** `src/execution_history/`配下のいずれのモジュールも`workflow_engine` / `ai` / `pipeline` / `scheduler`を一切importしない。`WorkflowEngineStep`のような他パッケージの型を直接受け取らず、`str`（`step.value`）のみを受け渡す
- **無効時（`EXECUTION_HISTORY_ENABLED=false`）はno-op。** `NullExecutionHistoryManager`が全メソッドを何もせず無視することで、Workflow Engine側の呼び出しコードを分岐させずに済む（`NullWorkflowEngineManager` / `NullLogManager`と同型のパターン）

### データモデルとStore

- `WorkflowExecutionRecord`（1回のWorkflow実行）：`run_id` / `workflow_name` / `source` / `job_id` / `status`（RUNNING/SUCCESS/FAILED） / `started_at` / `finished_at` / `steps` / `events` / `error_message`
- `StepExecutionRecord`（1Stepの実行）：`step` / `status`（RUNNING/SUCCESS/FAILED/SKIPPED/NOT_REACHED） / `started_at` / `finished_at` / `error_message` / `skipped_reason`
- `ExecutionHistoryStore`（ABC、`SchedulerRepository`と同型）→ `JsonExecutionHistoryStore`（初期実装。1実行=1 JSONファイル、`logs/execution_history/{run_id}.json`）。将来DB化する場合はABCを満たす新実装を追加するだけで差し替え可能
- 記録は`start_run → start_step → finish_step → finish_run`のたびに同じファイルへ**都度上書き保存**する。実行途中でプロセスが異常終了しても「RUNNINGのまま止まった記録」が残る

### Workflow Engineとの連携（最小限のDI）

`WorkflowEngineExecutor`に`history_manager`引数（省略時は`NullExecutionHistoryManager`）を追加し、既存の分岐結果（Gate閉鎖によるスキップ・打ち切りによる未到達・実行成功/失敗）をそのまま`ExecutionHistoryManager`へ横流しして記録する。`WorkflowEngineManager.from_config()`が`ExecutionHistoryConfig.from_env()` → `ExecutionHistoryManager.from_config()`を構築してDIする。既存の実行制御ロジック（Gate二層構造・打ち切り基準・`WorkflowEngineResult`の組み立て）は無変更。

デフォルトは有効（`EXECUTION_HISTORY_ENABLED=true`）。ローカルJSONファイルへの記録のみで外部への副作用を持たないため、`LOG_ENABLED`（v1.8.0）と同じ「原則有効」をデフォルトとした（Agent系ゲートのデフォルト`false`とは性質が異なる）。

### 履歴の確認方法

```bash
cd projects/03_game_content_ai
./venv/Scripts/python.exe scripts/show_execution_history.py                 # 一覧表示（新しい順）
./venv/Scripts/python.exe scripts/show_execution_history.py --run-id <ID>   # 指定run_idの詳細表示
```

読み取り専用CLI。`EXECUTION_HISTORY_ENABLED=false`（記録無効）の場合でも、過去に記録済みの履歴は閲覧できる（読み取りと書き込みのゲートを分離）。

詳細は`docs/design/execution_history_foundation.md`（Project Charter・Architecture Design）を参照。

---

## Workflow Monitor層（`src/workflow_monitor/`、v2.9.0 追加）

Execution History（v2.8.0）が記録した`WorkflowExecutionRecord`を読み取り、Workflowの実行状態を**判定するだけ**の最小基盤。Workflow Engine・Execution Historyいずれの実行・記録処理にも関与しない。

```
Scheduler        （判断、v2.6.0、無改修）
   ↓ SchedulerEvent
Workflow Engine    （実行、v2.7.0、無改修）─────観測─────→ Execution History（記録、v2.8.0、無改修）
   ↓                                                              ↓
NewsAgent → ReviewTriggerAgent → PublishTriggerAgent      logs/execution_history/*.json
                                                                   ↓ 読み取り専用
                                                            Workflow Monitor（状態判定、v2.9.0）
                                                                   ↓
                                                     scripts/show_workflow_status.py（CLI）
```

### 責務の境界（原則）

- **Execution Historyを唯一の情報源（Single Source of Truth）とする。** Workflow Engineの内部状態・メモリ上の状態・一時キャッシュには一切依存しない。すべての状態判定は`ExecutionHistoryStore`から読み取った`WorkflowExecutionRecord`から導出する
- **Workflow単位（`run_id`）の判定のみ。** `StepExecutionRecord`はExecution Historyの生データをそのままコピーして保持するのみで、Step単位の独自判定ロジックは持たない
- **`workflow_monitor` → `execution_history`の一方向依存を維持する。** `src/workflow_monitor/`配下のいずれのモジュールも`workflow_engine` / `ai` / `pipeline` / `scheduler`を一切importしない
- **読み取り専用・stateless。** Execution Historyへの書き込みは一切行わない（`ExecutionHistoryStore.save()`を呼ばない）。判定結果を独自に永続化・キャッシュせず、呼び出されるたびに最新のレコードを読み直して判定する

### 判定される状態

| 状態 | 判定方針 |
|---|---|
| `RUNNING` | `WorkflowExecutionRecord.status == RUNNING`かつTimeout未経過 |
| `SUCCESS` | `WorkflowExecutionRecord.status == SUCCESS` |
| `FAILED` | `WorkflowExecutionRecord.status == FAILED` |
| `TIMEOUT` | `status == RUNNING`のまま、`started_at`から`WorkflowMonitorConfig.timeout_seconds`（デフォルト3600秒）以上経過 |
| `CANCELLED` | **将来拡張用の予約値。** Workflow Engine・Execution Historyのいずれにも「キャンセル」を表す状態が存在しないため、判定ロジックからは到達しない |
| `WAITING` | **将来拡張用の予約値。** 実行待ちキューが現時点で存在しないため、判定ロジックからは到達しない |

### Timeoutの判定方針

Workflow Monitor自身はTimeoutの閾値を保持しない。閾値は`WorkflowMonitorConfig`（`WORKFLOW_MONITOR_TIMEOUT_SECONDS`、デフォルト3600秒）に一元化されており、Workflow Monitor本体にはハードコードされていない。この設定駆動の構造により、将来のRetry Engine・Metrics Foundation・Dashboard Foundationも同じ閾値を参照できる。

### Workflow Engine・Execution Historyとの関係

`WorkflowMonitor`は`ExecutionHistoryStore`（ABC、v2.8.0）を読み取り専用で参照するのみで、Workflow Engine（v2.7.0）・Execution History（v2.8.0）・既存4 Trigger Agent・Scheduler本体はいずれも無改修。デフォルトは有効（`WORKFLOW_MONITOR_ENABLED=true`）。Execution Historyと同じく「読み取り専用・外部副作用なし」であるため。

### 履歴の確認方法

```bash
cd projects/03_game_content_ai
./venv/Scripts/python.exe scripts/show_workflow_status.py                 # 一覧表示（新しい順）
./venv/Scripts/python.exe scripts/show_workflow_status.py --run-id <ID>   # 指定run_idの詳細表示
```

読み取り専用CLI。`WORKFLOW_MONITOR_ENABLED=false`（Feature Gate無効）の場合でも、ゲート判定をバイパスして常に判定結果を表示する（`show_execution_history.py`と同じ「読み取りと書き込みのゲート分離」の考え方）。

### 将来の拡張（Retry Engine・Metrics・Dashboardの前提基盤）

Workflow Monitorは、`WorkflowMonitorStatus.FAILED` / `TIMEOUT`を起点としたRetry Engine、`elapsed_seconds`を集計するMetrics Foundation、`list_status()`を参照するDashboard Foundationの前提基盤として位置づける。いずれもv2.9.0の対象外であり、将来Releaseで検討する。

詳細は`docs/design/workflow_monitor_foundation.md`（Project Charter・Architecture Design）を参照。

---

## Retry Engine層（`src/retry_engine/`、v3.0.0 追加）

Workflow Monitor（v2.9.0）が`FAILED` / `TIMEOUT`と判定したWorkflowを、Workflow Engine（v2.7.0）の公開APIを通じて再実行する最小基盤。Workflow Monitor・Workflow Engineいずれの判定・実行ロジックにも変更を加えない。

```
Scheduler        （判断、v2.6.0、無改修）
   ↓ SchedulerEvent
Workflow Engine    （実行、v2.7.0、無改修）─────観測─────→ Execution History（記録、v2.8.0、無改修）
   ↓          ▲                                                  ↓
NewsAgent → ReviewTriggerAgent → PublishTriggerAgent      logs/execution_history/*.json
   ↓          │                                                  ↓ 読み取り専用
（既存Agent群、無改修）                                    Workflow Monitor（状態判定、v2.9.0、無改修）
              │                                                  ↓ 公開API（get_status）
              │                                           Retry Engine（再実行判断・依頼、v3.0.0）
              └──────────────── 公開API（run） ─────────────────┘
```

### 責務の境界（原則）

- **Retry可否判定・RetryPolicy適用・RetryRequest生成はRetryManagerが担当する。** `RetryExecutor`は`WorkflowEngineManager`の公開APIを呼び出すだけの薄いコンポーネントであり、`RetryPolicy`を一切保持しない（コンストラクタに`policy`引数を持たない）
- **Workflowの状態は保持しない（Stateless）。** `RetryManager.retry(run_id)`は`run_id`のみを受け取り、その場で`WorkflowMonitorManager.get_status(run_id)`を呼んで最新状態を取得する（Read Before Retry）。Execution Historyは直接参照・解釈しない
- **`WorkflowEngineManager`の公開API（`run()`）のみを呼び出す。** `WorkflowEngineExecutor`等の内部実装には一切依存しない
- **`retry_engine` → `workflow_engine` / `workflow_monitor`の2パッケージのみへの一方向依存。** `execution_history` / `ai` / `pipeline` / `scheduler`はいずれもimportしない。`RetryManager.from_config()`は呼び出し元が構築済みの`WorkflowEngineManager` / `WorkflowMonitorManager`をDependency Injectionで受け取る（Configから再構築しない）ことでこれを実現している
- **`WorkflowMonitorStatus`はEnumとして比較する。** 文字列比較は行わない

### 再実行対象の判定（RetryPolicy）

| 項目 | 内容 |
|---|---|
| 対象ステータス | `WorkflowMonitorStatus.FAILED` / `WorkflowMonitorStatus.TIMEOUT`（固定。環境変数では変更不可） |
| 最大試行回数 | `RetryPolicy.max_attempts`（`RETRY_MAX_ATTEMPTS`、デフォルト`3`） |
| 試行回数の記憶 | Retry Engine自身は記憶しない。`RetryRequest.attempt`として呼び出し元が指定する |

### Feature Gate

デフォルトは無効（`RETRY_ENGINE_ENABLED=false`）。Retry Engineは実際にWorkflowを再実行する（News収集・WordPress下書き投稿などの外部副作用を再度発生させうる）ため、`AI_AGENT_ENABLED` / `WORKFLOW_ENGINE_ENABLED`と同じ「安全側で止める」原則を適用する。結果として`AI_AGENT_ENABLED × WORKFLOW_ENGINE_ENABLED × RETRY_ENGINE_ENABLED`の三重ゲートになる。

### 再実行イベントの識別

再実行イベントの`source`には新規定数を追加せず、既存の`SOURCE_MANUAL`（`workflow_engine`パッケージ、無改修）を再利用する。再実行由来であることは`WorkflowEngineEvent.metadata`（`retried_from` / `attempt`）で判別できる。

### Dry-run retry（追加調整）

`RetryManager.retry(run_id, attempt=1, dry_run=False)`で`dry_run`を指定できる。`dry_run=True`にすると、生成される`RetryRequest.dry_run`が`RetryExecutor`を経由して`WorkflowEngineManager.run(event, dry_run=True)`まで伝播し、実際のNews収集・WordPress下書き投稿を伴わずに「再実行が正しい経路で呼ばれるか」だけを確認できる。`dry_run`はキーワード引数でデフォルト`False`のため、既存の`retry(run_id)` / `retry(run_id, attempt=N)`という呼び出しの後方互換性は完全に維持される。`RetryExecutor`（`WorkflowEngineManager`の公開APIを呼び出すだけの薄いコンポーネント）・`RetryRequest`（データ構造）の責務はいずれも変更していない。

### Workflow Engine・Workflow Monitorとの関係

`RetryManager` / `RetryExecutor`は`WorkflowEngineManager`（v2.7.0）・`WorkflowMonitorManager`（v2.9.0）の公開APIのみを利用し、いずれも無改修。呼び出し元（将来のCLI・Scheduler連携）が両Managerを構築し、`RetryManager.from_config()`へDependency Injectionで渡す構成とする。

### 本Releaseの対象外

Retry Queue / Priority Queue・Retry History（再試行回数の永続化）・RetryDecision（Retry可否判定の専用コンポーネント化）・RetryReason Enum・Exponential Backoff・Adaptive Retry・Failure Classification・AI Retry Decision・Parallel/Distributed Retry・Circuit Breaker・Dead Letter Queue・Manual Retry UI・Notification・Metrics/Dashboard・CLIエントリスクリプト（`scripts/run_retry_engine.py`）は、いずれもv3.0.0の対象外であり、将来Releaseで検討する。Retry Queueはv3.1.0で実装した（下記参照）。

詳細は`docs/design/retry_engine_foundation.md`（Project Charter・Architecture Design）を参照。

---

## Retry Queue層（`src/retry_queue/`、v3.1.0 追加）

再実行待ちの`run_id`を保持・出し入れするだけの最小基盤。Queue管理（`enqueue` / `dequeue` / `remove` / `list` / `exists` / `count`）のみを責務とし、Retry実行・Workflow Engine呼び出し・Retry Engine呼び出し・Workflow Monitor呼び出し・Execution History呼び出しはいずれも行わない。

```
Scheduler        （判断、v2.6.0、無改修）
   │
Workflow Engine    （実行、v2.7.0、無改修）
   │
Execution History（記録、v2.8.0、無改修）
   │
Workflow Monitor（状態判定、v2.9.0、無改修）
   │
Retry Engine（再実行判断・依頼、v3.0.0、無改修）
   │
   └── Retry Queue（Queue管理、v3.1.0） ★本Release
```

Retry Queueは概念上Retry Engineの補助コンポーネントとして位置づけられるが、本Releaseのスコープは「Queue管理のみ」であり、Retry Engineとの実際の配線（`RetryManager`が`RetryQueueManager`を呼び出す等）は行わない。そのため`src/retry_queue/`は本Release時点では**どのパッケージからも呼ばれない、独立したFoundation層**として先行実装される（`WorkflowMonitorManager`・v2.9.0が実呼び出し元を持たないまま先行リリースされた前例と同型のパターン）。

### 責務の境界（原則）

- **Queue管理（出し入れ）のみを責務とする。** Retry可否判定・Retry実行はいずれも行わない（それらは`RetryPolicy` / `RetryManager`の責務のまま。責務の混在を避ける）
- **`retry_queue`は他のどの`src/*`パッケージもimportしない、標準ライブラリのみに依存する独立した葉パッケージ。** `workflow_engine` / `workflow_monitor` / `retry_engine` / `execution_history` / `ai` / `pipeline` / `scheduler`のいずれも呼び出さない。Retry Engine（`workflow_engine` / `workflow_monitor`の2パッケージに依存）よりもさらに徹底した独立性を持つ
- Queueへの出し入れの可否判定は「容量上限（`RETRY_QUEUE_MAX_SIZE`）」「`run_id`の重複」の2点のみ

### Queue操作とライフサイクル（RetryQueueStatus）

| 操作 | 遷移 | 備考 |
|---|---|---|
| `enqueue()` | （新規）→ `WAITING` | 重複`run_id`・容量超過時は登録せず`REJECTED`を返す |
| `dequeue()` | `WAITING` → `PROCESSING` | `priority`昇順（数値が小さいほど高優先）・`enqueue_time`昇順で先頭を取り出し、Queueから削除する |
| `remove()` | `WAITING` → `CANCELLED` | Queueから削除する |
| ― | ― → `COMPLETED` / `FAILED` | 将来拡張用の予約値。実際の再実行結果をQueueへフィードバックする仕組み（Retry Engineとの連携）が必要だが本Releaseの対象外。`WorkflowMonitorStatus.CANCELLED` / `WAITING`が判定ロジックから到達しない予約値として定義されている前例を踏襲 |

`dequeue()` / `remove()`で取り出された項目はQueueの内部ストア（`dict[str, RetryQueueItem]`）から削除され、以後`list()` / `exists()` / `count()`には現れない。呼び出し元へ返す`RetryQueueItem`は常にコピー（`dataclasses.replace()`）であり、呼び出し元が書き換えても内部ストアには影響しない。

### Feature Gate

デフォルトは有効（`RETRY_QUEUE_ENABLED=true`）。`RETRY_ENGINE_ENABLED`（デフォルト`false`）とは異なる判断であり、理由はRetry QueueのQueue操作（enqueue/dequeue/remove/list/exists/count）がいずれもプロセス内メモリ上の`dict`を読み書きするだけで、外部副作用（Workflowの再実行等）を一切伴わないためである。この性質は`EXECUTION_HISTORY_ENABLED` / `WORKFLOW_MONITOR_ENABLED`（いずれもデフォルト`true`、読み取り中心）と同じ分類に属すると判断した。

### 永続化しない（Stateless の再定義）

Retry Engineにおける「Stateless」は「Workflowの実行状態を自ら保持せず、毎回Workflow Monitorに問い合わせる」ことを意味していたが、Retry Queueはこの意味では成立しない（Queueに入っている項目を保持すること自体が本コンポーネントの責務であるため）。Retry Queueが保持するのは「再実行待ちの`run_id`とそのメタデータ」というQueue管理専用の状態のみであり、Workflowの実行結果・監視ステータス（`WorkflowMonitorStatus`）を独自に複製・キャッシュすることはない。Queueの内容はすべてプロセス内メモリ（`dict`）上にあり、ファイル・DBへの書き込みは一切行わない。プロセスが終了するとQueueの内容は失われる（永続化はOut of Scope）。

### Retry Engineとの関係（本Releaseでは未配線）

`RetryQueueManager`と`RetryManager`（Retry Engine、v3.0.0）の実際の配線（`RetryManager`が再実行対象を即座に実行するのではなく`RetryQueueManager.enqueue()`へ委ねる、または`dequeue()`した項目に対して`RetryManager.retry()`を呼ぶ、という統合）は本Releaseでは行っていない。`retry_engine` / `workflow_engine` / `workflow_monitor` / `execution_history`はいずれも無改修である。**登録・取得の配線自体はv3.2.0で実装した（下記「Retry Queue Integration層」参照）。ただし`dequeue()`した項目を自動的に`RetryManager.retry()`へ渡す自動実行は、v3.2.0でも引き続き行っていない。**

### 本Releaseの対象外

Retry Engineとの実配線・Scheduler連携（定期的な`dequeue()`）・Queue永続化（SQLite/Redis）・`COMPLETED` / `FAILED`への到達（`mark_completed()` / `mark_failed()`相当の結果フィードバックAPI）・Priority Queueの効率化（`heapq`ベースへの差し替え）・Dead Letter Queue・Notification・Dashboard/API/UI・並行アクセス対応（スレッド安全性）は、いずれもv3.1.0の対象外であり、将来Releaseで検討する。**Retry Engineとの実配線（登録・取得のみ）はv3.2.0で実装した（下記参照）。**

詳細は`docs/design/retry_queue_foundation.md`（Architecture Design）を参照。

---

## Retry Queue Integration層（`src/retry_engine/retry_manager.py`、v3.2.0 追加）

Retry Engine（v3.0.0）とRetry Queue（v3.1.0）の間に、片方向の配線を1本追加する最小統合。
自動実行・Scheduler連携・永続化は行わず、「登録できる」「取得できる」という配線のみを
確立する。

```
Retry Engine（再実行判断・依頼、v3.0.0）
   │
   ├── RetryManager が RetryQueueManager を保持する（DI） ★v3.2.0
   │      ├─ enqueue_retry()  … RetryQueueManager.enqueue() へ委譲
   │      └─ dequeue_retry()  … RetryQueueManager.dequeue() へ委譲
   │
   └── RetryManager.retry()（既存、無改修） ─── Queueとは独立した経路のまま

Retry Queue（Queue管理、v3.1.0、無改修）
```

### 変更範囲

- 変更ファイルは`src/retry_engine/retry_manager.py`の1点のみ。`src/retry_queue/`配下は
  本Releaseでも**無改修**（7ファイルとも1バイトも変更していない）
- `RetryManager.__init__`に`queue: RetryQueueManager | NullRetryQueueManager | None = None`
  引数を追加。省略時は`NullRetryQueueManager()`にフォールバックする
- `RetryManager.from_config()`に`retry_queue_manager`引数（デフォルト`None`）を追加。
  既存の4引数呼び出しはすべて本Release前と同じ挙動になる（後方互換性維持）
- `RetryManager.enqueue_retry(run_id, workflow_name, retry_attempt=1, priority=None)` /
  `RetryManager.dequeue_retry()`を新設。いずれも`RetryQueueManager`の対応メソッドへの
  **委譲のみ**であり、容量チェック・重複チェック・優先度ソート等のQueue管理ロジックは
  一切`retry_engine`側に複製しない（Queue管理とRetry実行の責務分離を維持）
- `NullRetryManager`にも同名2メソッドを追加。ただし`RetryQueueManager` /
  `NullRetryQueueManager`への参照は一切持たず、常に自前で`outcome=DISABLED`を返す。
  Retry Engine自体が無効な場合は、Retry Queueの有効/無効に関わらず一律で無効化される

### `retry()`との独立性

`retry()`（Workflow再実行）と`enqueue_retry()` / `dequeue_retry()`（Queue操作）は、
`RetryManager`内で状態や呼び出しを共有しない。`dequeue_retry()`が返した
`RetryQueueItem`を使って実際に再実行するかどうかは、呼び出し元が
`RetryManager.retry(item.run_id, attempt=item.retry_attempt)`を**別途明示的に**
呼ぶ運用を前提とし、`RetryManager`自身がその橋渡しを行うことは本Releaseでは行わない。

### Feature Gateの独立性

Retry EngineのFeature Gate（`RETRY_ENGINE_ENABLED`）とRetry QueueのFeature Gate
（`RETRY_QUEUE_ENABLED`）は引き続き独立している。`enqueue_retry()` /
`dequeue_retry()`の`reason`文言により、呼び出し元はどちらのゲートが閉じているかを
判別できる。

| ケース | `outcome` | `reason` |
|---|---|---|
| `RETRY_ENGINE_ENABLED=false`（`NullRetryManager`） | `DISABLED` | "Retry Engine is disabled (...)"（Retry Engine起因） |
| `RETRY_ENGINE_ENABLED=true`だが`RETRY_QUEUE_ENABLED=false` | `DISABLED` | "Retry Queue is disabled (RETRY_QUEUE_ENABLED=false)."（`retry_queue`パッケージ既存の文言、Retry Queue起因） |

### 依存関係

```
retry_engine ──→ retry_queue（公開APIのみ：RetryQueueManager / NullRetryQueueManager /
                  RetryQueueResult / RetryQueueOutcome） ★v3.2.0で新規追加
retry_engine ──→ workflow_engine（既存、無改修）
retry_engine ──→ workflow_monitor（既存、無改修）

retry_queue  ──→ （なし。標準ライブラリのみ、無改修のまま）
```

`retry_queue`が`retry_engine`を参照する辺は存在しない（`retry_queue`は本Releaseでも
無改修であり、そもそも`retry_engine`の存在を知らない）。循環importは発生しない。

### 本Releaseの対象外

Queueから取り出した項目の自動再実行・Scheduler連携（定期的な`dequeue()`処理）・
Queue永続化・優先度付けアルゴリズムの高度化・CLIエントリスクリプトは、いずれも
v3.2.0の対象外であり、将来Releaseで検討する。

詳細は`docs/design/retry_queue_integration_charter.md`（Project Charter）・
`docs/design/retry_queue_integration.md`（Architecture Design）を参照。

---

## Retry Scheduler Integration層（`src/retry_scheduler_source/`、v3.3.0 追加）

Retry Queue（v3.1.0）の状態（待機中の項目一覧・件数）を、Scheduler側の語彙で読み取るための
最小Adapter。Schedulerが将来この層を通じて「再実行待ちの項目がある」ことを把握できるように
するための土台であり、自動実行・実配線は行わない。

```
Scheduler          （判断、v2.6.0、無改修）
   │
   │  ※本Releaseでは未接続（この接続はv3.4.0 Retry Scheduler Wiring層で実装された。次節参照）
   ▼
RetrySchedulerSource / NullRetrySchedulerSource（Adapter、v3.3.0） ★本Release
   │
   └── Retry Queue （Queue管理、v3.1.0、無改修）
```

### Adapter / Bridge パターン

`RetrySchedulerSource`はSchedulerとRetry Queueの間に立つ変換層であり、Scheduler側（将来の
呼び出し元）は`RetryQueueManager`の存在・内部データ構造・メソッド名を一切知る必要がない。
`list_pending_retries(limit)` / `count_pending_retries()`という2メソッドのみを公開し、
内部では`RetryQueueManager.list()` / `count()`への薄い委譲のみを行う（判定・加工は一切
行わない）。将来`retry_queue`側のAPIが変化しても、影響は`RetrySchedulerSource`の内部実装に
閉じる。

### Null Object Pattern（Feature Gate / Config / Managerパターンは採用しない）

本層はプロジェクト全体で一貫しているNull Object Pattern（`RetryManager`/`NullRetryManager`、
`RetryQueueManager`/`NullRetryQueueManager`等、継承なしのDuck Typingペア）に合わせ、
`RetrySchedulerSource`（実装クラス）／`NullRetrySchedulerSource`（ダミー実装）の2クラス
構成とする。ただし他パッケージと異なり、`enabled`フラグ・Configクラス・`from_config()` /
`from_env()`のような起動口は**持たない**。

- `RetrySchedulerSource`は`RetryQueueManager`（実体）のみをConstructor Injectionで受け取る
- 無効化したい場合、呼び出し元は`RetrySchedulerSource`を構築せず`NullRetrySchedulerSource()`
  を選択する。`NullRetrySchedulerSource`は`retry_queue`パッケージへの参照を一切保持せず、
  `list_pending_retries()`は常に`[]`、`count_pending_retries()`は常に`0`を返す
- 「どちらのクラスを構築するか」の判定ロジック（Feature Gate相当の判断）は本パッケージの
  責務ではなく、呼び出し元の責務とする（次節「本Releaseの対象外」参照）

### Read Only（`dequeue()` / `remove()`は使用しない）

`RetrySchedulerSource`は非破壊の読み取り専用API（`list()` / `count()`）のみを使用し、Queueの
状態を変更する`dequeue()` / `remove()`は一切呼び出さない（E2Eテストでスパイオブジェクトに
より構造的に確認済み）。

### 依存関係

```
retry_scheduler_source ──→ retry_queue（公開APIのみ：RetryQueueManager / RetryQueueItem /
                            list() / count()）
    ※ NullRetrySchedulerSource は retry_queue を一切importしない

retry_queue  ──→ （なし。標準ライブラリのみ、無改修）
scheduler    ──→ （本Releaseでは retry_scheduler_source を含め、何も追加しない）
retry_engine ──→ （本Releaseでは一切関与しない）
```

`src/scheduler/`（`SchedulerEngine` / `SchedulerManager` / `SchedulerJob` / `SchedulerEvent` /
`SchedulerRepository` / `SchedulerConfig`）・`src/retry_queue/`・`src/retry_engine/`はいずれも
本Releaseでも無改修である。循環importは発生しない。

### 消費者不在の先行実装（Foundation First）

本Release（v3.3.0）時点では、`RetrySchedulerSource` / `NullRetrySchedulerSource`をどの
パッケージからも呼び出さない。`WorkflowMonitorManager`（v2.9.0）・`RetryQueue`（v3.1.0）が
実呼び出し元を持たないまま先行リリースされた前例と同型のパターンである。

**この状態はv3.4.0（Retry Scheduler Wiring）で解消された。** `SchedulerEngine`が本層を
Constructor Injectionで保持できるようになり、初めて呼び出し元を持った。詳細は次節
「Retry Scheduler Wiring層」を参照。

### 本Releaseの対象外

Scheduler本体（`SchedulerEngine.evaluate()` / `run_due()`）との実配線・Queueから取り出した
項目の自動再実行（自動Retry実行）・`dequeue()` / `remove()`の使用・Queueの永続化・優先度付け
アルゴリズムの高度化・CLIエントリスクリプトは、いずれもv3.3.0の対象外であり、将来Releaseで
検討する（実配線はv3.4.0で実装された。次節参照。それ以外は引き続き対象外）。

詳細は`docs/design/retry_scheduler_integration_charter.md`（Project Charter）・
`docs/design/retry_scheduler_integration.md`（Architecture Design）を参照。

---

## Retry Scheduler Wiring層（`src/scheduler/`、v3.4.0 追加）

v3.3.0で新設した`RetrySchedulerSource` / `NullRetrySchedulerSource`（Adapter）を、
`SchedulerEngine`へ実際に接続するWiring。Schedulerの判定サイクルがRetry Queueの状態を
**読み取れる**状態を作るところまでを範囲とし、読み取った結果を使って何かを実行する処理は
一切追加しない。

```
Scheduler（判断、v2.6.0）
   │
   │  SchedulerEngine.__init__(clock, retry_source)  ★v3.4.0で新設
   ▼
RetrySchedulerSource / NullRetrySchedulerSource（Adapter、v3.3.0、無改修）
   │
   └── Retry Queue（Queue管理、v3.1.0、無改修）
```

### Constructor Injection と Backward Compatibility

`SchedulerEngine.__init__`に`retry_source`引数（デフォルト`None`）を追加した。省略時は
`NullRetrySchedulerSource()`にフォールバックする。これはv3.2.0の`RetryManager`が
`RetryQueueManager`を同じ形でDIで受け取る設計と同一パターンであり、既存の
`SchedulerEngine()` / `SchedulerEngine(clock=...)`呼び出しは本Release前とまったく同じ
挙動になる。

### 判定サイクルとは独立した読み取り専用メソッド

`count_pending_retries()` / `list_pending_retries(limit=None)`を新設した。いずれも
`RetrySchedulerSource`（またはNull版）への1行委譲のみで、加工・分岐・例外処理を持たない。
`evaluate()` / `run_due()`（時刻ベースの判定・`SchedulerEvent`生成）は**1行も変更しておらず**、
新設2メソッドを呼び出しても判定結果には一切影響しない。

### RetryQueueManagerを直接保持しない境界

`SchedulerEngine`は`RetryQueueManager`を直接保持しない。Retry Queueへは
`RetrySchedulerSource`経由でのみ間接的に到達する（v3.3.0のAdapter境界を維持）。
`dequeue()` / `remove()`に相当するメソッドは`RetrySchedulerSource` /
`NullRetrySchedulerSource`のいずれにも存在しないため、`SchedulerEngine`からは構造的に
呼び出せない（E2Eテストでスパイオブジェクトにより確認済み）。

### 依存関係

```
scheduler              ──→ retry_scheduler_source（公開APIのみ：
                            RetrySchedulerSource / NullRetrySchedulerSource）
retry_scheduler_source ──→ retry_queue（v3.3.0のまま、無改修）
```

`scheduler`は`retry_queue` / `retry_engine`のいずれも直接importしない。`SchedulerManager` /
`SchedulerRepository` / `SchedulerJob` / `SchedulerEvent` / `SchedulerConfig`はいずれも
無改修。新規Feature Gate・Configクラス・Managerパターン（`from_config()`等）はいずれも
追加しない。

### 本Releaseの対象外

実運用のComposition Root（例：`scripts/run_scheduler.py`）・pending retryの参照結果を
使った判断（`SchedulerEvent`への反映等）・自動Retry実行・`dequeue()` / `remove()`の使用・
Queueの永続化は、いずれもv3.4.0の対象外であり、将来Releaseで検討する
（このうち「pending retryから次に処理すべき候補を選ぶロジック」はv3.5.0
「Retry Scheduler Decision層」で実装された。次節参照。それ以外は引き続き対象外）。

詳細は`docs/design/retry_scheduler_wiring_charter.md`（Project Charter）・
`docs/design/retry_scheduler_wiring.md`（Architecture Design）を参照。

---

## Retry Scheduler Decision層（`src/retry_scheduler_decision/`、v3.5.0 追加）

v3.4.0で`SchedulerEngine`が「読み取れる」ようになったRetry Queueの状態から、
「次に処理すべき候補を選ぶ」という関心事を、新規独立コンポーネント
`RetrySchedulerDecision`として切り出す。`SchedulerEngine`との実配線は行わず、
候補を選ぶロジックの新設のみを範囲とする。

```
Scheduler（判断、v2.6.0 / v3.4.0、無改修）
   │
   ├── RetrySchedulerSource（Adapter、v3.3.0、無改修）
   │        │
   │        └── Retry Queue（v3.1.0、無改修）
   │
   └── RetrySchedulerDecision（新規、v3.5.0） ★本Release
            │  ※本Releaseでは未接続。RetrySchedulerSourceを個別にDIで保持する
            │    独立コンポーネントとして先行実装する
            ▼
      RetrySchedulerSource（同上と同じインスタンスを想定するが、
                             SchedulerEngineとは独立した経路で保持される）
```

v3.4.0 Architecture Reviewで残した「`SchedulerEngine`に3つ目の異種責務（時刻判定・
pending retry参照に続く判定/選択ロジック）が入る場合は責務分割を再検討する」という
指摘を受け、`SchedulerEngine`にはこれ以上手を加えず、新規パッケージへ切り出した
（`docs/design/retry_scheduler_decision_charter.md` 1章）。

### 責務：候補選択のみ

`RetrySchedulerDecision`は`RetrySchedulerSource.list_pending_retries()`が返す
既存順序（priority昇順・enqueue_time昇順、`RetryQueueManager.list()`で整列済み）を
そのまま活用し、独自の並べ替え・優先度計算は一切行わない。

- `select_candidates(limit=None) -> list`：`list_pending_retries(limit)`への
  1行委譲のみ
- `select_next_candidate()`：`select_candidates(limit=1)`の先頭要素
  （またはNone）を返す便利メソッド

戻り値は`RetryQueueItem`（`retry_queue`の公開型）をそのまま返し、独自DTOへの変換は
行わない。型ヒント上は無型の`list`とし、`retry_scheduler_decision → retry_scheduler_source`
の一方向のみという依存方向を優先する。

### Constructor Injectionを必須引数とする判断

`retry_source`（`RetrySchedulerSource | NullRetrySchedulerSource`）はデフォルト値を
持たない必須引数とする。`SchedulerEngine.__init__`の`retry_source`（デフォルト`None`
→`NullRetrySchedulerSource()`フォールバック）とは異なり、`RetrySchedulerDecision`に
とって`retry_source`は唯一の実質的な入力であり、省略時の安全な既定値という概念自体が
存在しないため。`RetrySchedulerSource.__init__(queue)`（v3.3.0）が同じく必須引数で
ある設計と一貫している。

### Null Object Patternを採用しない判断

プロジェクト全体では「実装クラス／Nullクラス」のペア（`RetryManager`/
`NullRetryManager`、`RetryQueueManager`/`NullRetryQueueManager`、
`RetrySchedulerSource`/`NullRetrySchedulerSource`等）が一貫しているが、
`RetrySchedulerDecision`には対になる`NullRetrySchedulerDecision`を**作らない**。

* 本コンポーネント自身には対応するFeature Gate/Config軸が存在しない
* 「無効化」は、呼び出し元が`retry_source`に`NullRetrySchedulerSource()`を渡すことで
  既に完結している（この場合`select_candidates()`は常に`[]`、
  `select_next_candidate()`は常に`None`を返す）
* Null Object Patternは、これまで「呼び出し元が持つFeature Gate的な判定の結果を、
  コンポーネントの型として表現する」ために使われてきたが、本コンポーネントには
  対応する判定軸がないため、機械的に適用しない

これはプロジェクトの設計言語からの意図的な逸脱であり、`docs/design/retry_scheduler_decision.md`
13章 Design Decision #2で詳細な根拠を記録している。

### 依存関係

```
retry_scheduler_decision ──→ retry_scheduler_source（公開APIのみ：
                              RetrySchedulerSource / NullRetrySchedulerSource）
retry_scheduler_source   ──→ retry_queue（v3.3.0のまま、無改修）
```

`retry_scheduler_decision`は`scheduler` / `retry_queue` / `retry_engine`のいずれも
直接importしない。`scheduler`側も本Releaseでは`retry_scheduler_decision`を一切
importしない（相互に無関係。v3.4.0で新設された`SchedulerEngine`の`retry_source`
とは別の独立した経路）。`SchedulerManager` / `SchedulerRepository` / `SchedulerJob` /
`SchedulerEvent` / `SchedulerConfig`はいずれも無改修。新規Feature Gate・Configクラス・
Managerパターン（`from_config()`等）はいずれも追加しない。

### 消費者不在の先行実装（Foundation First）

本Release時点では、`RetrySchedulerDecision`をどのパッケージからも呼び出さない。
`WorkflowMonitorManager`（v2.9.0）・`RetryQueue`（v3.1.0）・`RetrySchedulerSource`
（v3.3.0）が実呼び出し元を持たないまま先行リリースされた前例と同型のパターンである。

**この状態はv3.6.0（Retry Scheduler Decision Wiring）で一部解消された。**
`SchedulerEngine`が`RetrySchedulerDecision`をConstructor Injectionで保持し、
`select_candidates()` / `select_next_candidate()`経由で実際に呼び出すようになった。
ただし`evaluate()` / `run_due()`の判定ロジック（`SchedulerEvent`生成）への組み込みは
v3.6.0でも行っていない（読み取れる状態を作っただけ）。詳細は次節
「Retry Scheduler Decision Wiring層」を参照。

### 本Releaseの対象外

`SchedulerEngine`との実配線・選択結果を使った実行（自動Retry実行）・
`RetryQueueManager.dequeue()` / `remove()`の使用・Retry Engineの起動・Queueの永続化は、
いずれもv3.5.0の対象外であり、将来Releaseで検討する
（このうち「`SchedulerEngine`との実配線（Constructor Injection・薄い委譲）」は
v3.6.0「Retry Scheduler Decision Wiring層」で実装された。次節参照。それ以外は
引き続き対象外）。

詳細は`docs/design/retry_scheduler_decision_charter.md`（Project Charter）・
`docs/design/retry_scheduler_decision.md`（Architecture Design）を参照。

---

## Retry Scheduler Decision Wiring層（`src/scheduler/`、v3.6.0 追加）

v3.5.0で新設した`RetrySchedulerDecision`を、`SchedulerEngine`へConstructor
Injectionで接続し、`SchedulerEngine`から候補選択結果を「読み取れる」状態を作る。
v3.4.0が`RetrySchedulerSource`に対して行った統合とまったく同型のパターンを
`RetrySchedulerDecision`に対しても適用する。

```
Scheduler（判断、v2.6.0 / v3.4.0）
   │
   ├── RetrySchedulerSource（Adapter、v3.3.0、無改修）
   │        │
   │        └── Retry Queue（v3.1.0、無改修）
   │
   └── RetrySchedulerDecision（v3.5.0、無改修） ★本Releaseで接続
            │  呼び出し元がConstructor Injectionで組み立てて渡す
            │  （SchedulerEngineは組み立てない）
            ▼
      RetrySchedulerSource（同上。RetrySchedulerDecisionが内部に保持）
```

### `SchedulerEngine`は`RetrySchedulerDecision`を自ら構築しない

ユーザー承認済みの設計方針として、`SchedulerEngine`は`RetrySchedulerDecision`
インスタンスを外部（呼び出し元・Composition Root）から直接Constructor Injection
で受け取って保持するのみで、`RetrySchedulerDecision(...)`という構築呼び出しは
`scheduler_engine.py`に一切登場しない（ASTベースで構造的に確認済み）。

### `retry_decision=None`時のフォールバック：ガード節による安全なデフォルト値

`RetrySchedulerDecision`には対になる`NullRetrySchedulerDecision`が存在しない
（v3.5.0の意図的な設計判断）。かつ`SchedulerEngine`が`RetrySchedulerDecision`を
組み立てない制約により、v3.4.0の`retry_source`（省略時に
`NullRetrySchedulerSource()`を構築してフォールバックする）とは異なる方式を
採用する。

- `select_candidates(limit=None) -> list`：`retry_decision`が`None`の場合は`[]`を
  直接返す。`None`でなければ`RetrySchedulerDecision.select_candidates()`への
  1行委譲のみ
- `select_next_candidate()`：`retry_decision`が`None`の場合は`None`を直接返す。
  `None`でなければ`RetrySchedulerDecision.select_next_candidate()`への1行委譲のみ

ガード節による直接returnは、Null Object Patternと結果的に同じ戻り値
（空リスト・`None`）を、インスタンスを1つも生成せずに実現する。「候補選択機能が
接続されていない」という状態を、オブジェクトの型ではなく`None`という値そのもので
表現する設計であり、`RetrySchedulerDecision`側の設計（Null Object Pattern不採用）
との整合性も保たれる。

### `evaluate()` / `run_due()`は無変更

判定サイクル（時刻ベースの判定・`SchedulerEvent`生成）には一切手を加えず、
`select_candidates()` / `select_next_candidate()`という完全に独立した新規メソッド
を追加する方式を採用した。既存の回帰テスト（v2.6.0・v3.4.0）は、
`SchedulerEngine`の構築方法（`retry_decision`を渡すか省略するか）に関わらず、
本Release前とまったく同じ結果を返す。

### 依存関係

```
scheduler                ──→ retry_scheduler_decision（公開APIのみ：RetrySchedulerDecision）
scheduler                ──→ retry_scheduler_source（v3.4.0のまま、無改修）
retry_scheduler_decision ──→ retry_scheduler_source（v3.5.0のまま、無改修）
retry_scheduler_source   ──→ retry_queue（v3.3.0のまま、無改修）
```

新規に追加される依存方向は`scheduler → retry_scheduler_decision`の一方向のみ。
`retry_scheduler_decision`は本Releaseでも`scheduler`を一切importしない
（逆方向依存なし）。循環importの余地は構造的に存在しない。

### 本Releaseの対象外

`evaluate()` / `run_due()`への候補選択結果の組み込み（`SchedulerEvent`生成への
反映）・Retry Engineの起動・`RetryQueueManager.dequeue()` / `remove()`の使用・
Retry Queueの更新・Retry Queueの永続化は、いずれもv3.6.0の対象外であり、
将来Releaseで検討する。

詳細は`docs/design/retry_scheduler_decision_wiring_charter.md`（Project Charter）・
`docs/design/retry_scheduler_decision_wiring.md`（Architecture Design）を参照。

---

## Retry Execution Foundation層（`src/retry_engine/`、v4.0.0 追加）

> **本節の位置づけ**：v3.7.0（Retry Scheduler Event Integration）・v3.8.0
> （Retry Engine Event Consumption）・v3.9.0（Retry Engine Event Dispatch）は
> 個別セクションが本ドキュメントへ未追記のままだった（各`docs/design/`配下の
> 個別設計書には記載済み）。本節ではそのギャップを踏まえ、Retry Queueから
> `RetryManager.retry()`に至る**現在の全体パイプライン**を一括して示したうえで、
> v4.0.0で新設した部分を詳述する。

### 全体パイプライン（v3.1.0〜v4.0.0）

```
Retry Queue（Queue管理、v3.1.0、無改修）
    ↓
RetrySchedulerSource（Adapter、v3.3.0、無改修）
    ↓
RetrySchedulerDecision（候補選択、v3.5.0、無改修）
    ↓
SchedulerEngine（判定サイクル、v2.6.0 / v3.4.0 / v3.6.0 / v3.7.0、無改修）
    ↓
SchedulerEvent（Job由来 ＋ Retry候補由来が混在、v3.7.0でRetry候補由来を追加）
    ↓
RetryEventConsumer（認識、v3.8.0、無改修） ─── job_idが"retry:"で始まるものだけを識別
    ↓
RetryCandidateEvent（run_id・candidate・source_event、v3.8.0、無改修）
    ↓
RetryEventDispatcher（整理、v3.9.0、無改修） ─── dispatchableを構造的妥当性のみで判定
    ↓
RetryDispatchEvent（candidate_event・dispatchable、v3.9.0、無改修）
    ↓
RetryExecutionSelector（判定、v4.0.0 ★新設） ─── dispatchable=Trueのみを選別
    ↓
RetryExecutionCoordinator（実行・結果集約、v4.0.0 ★新設） ─── retry_fn=RetryManager.retryを呼び出す
    ↓
RetryManager.retry()（Retry可否判定・実行、v3.0.0、無改修）
```

各矢印は「型・データを渡す」関係であり、上流のコンポーネントが下流を直接
呼び出すわけではない。実際に呼び出しグラフを構成するのは
`RetryManager.execute_dispatchable_retries(events)`（v4.0.0新設）であり、
内部で`dispatch_retry_events()`（v3.9.0）→`RetryExecutionSelector.select()`
→`RetryExecutionCoordinator.execute()`の3段階の委譲のみで完結する。
Scheduler側（`RetrySchedulerSource` 〜 `SchedulerEngine`）と、Retry Engine側
（`RetryEventConsumer` 〜 `RetryManager`）を実際につなぐComposition Root
（`SchedulerEngine.run_due()`の結果を継続的に`execute_dispatchable_retries()`
へ渡す起動スクリプト）は、v4.0.0時点でも未実装のままである
（`docs/ROADMAP.md`「自動Retry実行の実運用化（Composition Root）」参照）。

### v4.0.0で新設した部分

`RetryEventDispatcher`（v3.9.0）が返す`RetryDispatchEvent`のうち、
`dispatchable=True`のものだけを対象に、初めて`RetryManager.retry()`を
呼び出せる基盤を追加した。判定と実行を1つのコンポーネントにまとめず、
以下のように責務を分離している。

```
RetryManager
   │
   ├── execute_dispatchable_retries(events, dry_run=False)  ★新設
   │      1. self.dispatch_retry_events(events)（v3.9.0、無変更）
   │      2. self._execution_selector.select(dispatch_events)
   │      3. self._execution_coordinator.execute(selected, retry_fn=self.retry, dry_run=dry_run)
   │
   ├── RetryExecutionSelector（判定）
   │      + select(dispatch_events) -> list[RetryDispatchEvent]
   │      dispatchable=True のものだけを抽出する。「dispatchable=trueを
   │      唯一の実行入口とする」判定基準を、この1メソッドのみに集約する
   │
   └── RetryExecutionCoordinator（実行・結果集約）
          + execute(dispatch_events, retry_fn, dry_run=False) -> list[RetryExecutionResult]
          選別済みのイベントについて retry_fn（= RetryManager.retry()）を
          呼び出し、結果を RetryExecutionResult（dispatch_event・retry_result
          の2フィールドのみを持つ軽量frozen dataclass）として集約する

RetryExecutionResult
   + dispatch_event: RetryDispatchEvent（v3.9.0、分解しない）
   + retry_result: RetryResult（v3.0.0、分解しない。既存型は無変更）
```

### 責務分離の設計判断（RetryManagerを薄いままに保つ）

「メソッド追加のみ（新規コンポーネントなし）」「判定と実行を1つの
統合コンポーネントにまとめる」「判定（Selector）と実行（Coordinator）を
分離する」の3案を比較検討し、3案目を採用した
（`docs/design/retry_execution_foundation.md` 2章）。

- `RetryManager.execute_dispatchable_retries()`は3行の委譲のみで完結し、
  判定ロジック・実行ループ・結果集約のいずれも`RetryManager`自身には
  書かない（既存の`recognize_retry_events()` / `dispatch_retry_events()`と
  同じ「薄い委譲メソッド」という性質を維持する）
- `dispatchable`フィールドを参照するのは`RetryExecutionSelector.select()`
  のみであり、`RetryExecutionCoordinator`は選別済みのリストを受け取る
  だけで`dispatchable`を一切再解釈しない
- 将来、選別基準に優先度・件数上限（Retry Policy）を追加する場合、
  `RetryExecutionSelector`のみを拡張・置換すればよく、
  `RetryExecutionCoordinator` / `RetryManager`は無改修のまま拡張できる

### Queueへの非依存

`RetryExecutionSelector` / `RetryExecutionCoordinator`のいずれも
`RetryQueueManager` / `NullRetryQueueManager`への参照を一切持たない
（コンストラクタ引数にも存在しない）。入力は`RetryDispatchEvent`
（Dispatcherが返した情報）のみであり、`retry_queue`パッケージへの
importも発生しない（AST解析で確認済み）。

`RetryExecutionCoordinator`は`retry_fn`（実体は`RetryManager.retry()`）を
呼び出しごとにメソッド引数として受け取り、コンストラクタでは保持しない。
これにより`RetryManager`への逆参照を持たずに済み、Stateless性と循環参照の
回避を両立している。

### `retry_attempt`の扱い（Queue非依存を優先した暫定実装）

`RetryManager.retry(run_id, attempt, dry_run)`に渡す`attempt`値は、
`candidate_event.candidate`（実態は`RetryQueueItem`、v3.1.0）が持つ
`retry_attempt`属性から`getattr(candidate, "retry_attempt", 1)`で取得する。
`retry_queue`パッケージへの型import（`RetryQueueItem`型そのもの）は行わず、
緩いダックタイピングとフォールバック値（デフォルト`1`）で対応している。

この設計は「Queueとの型結合を避ける」ことを優先した**v4.0.0時点での暫定的な
実装**であり、`candidate`の由来が将来変化した場合に`attempt=1`へ静かに
フォールバックする残存リスクをコード内コメントとともに記録している
（`docs/design/retry_execution_foundation.md` 14章 Design Decision #5・
12章 Future Extension）。

### 本Releaseの対象外

Retry Queueの更新（`enqueue_retry()` / `dequeue_retry()`の自動呼び出しを
含む）・`RetryQueueManager.dequeue()` / `remove()`の呼び出し・Queue永続化・
Retry Policy（優先度・件数上限に基づく選別ロジック）の導入・Scheduler側の
変更・実運用のComposition Rootは、いずれもv4.0.0の対象外であり、将来
Releaseで検討する（`docs/ROADMAP.md`「v3.x 以降の候補」参照）。

詳細は`docs/design/retry_execution_foundation_charter.md`（Project Charter）・
`docs/design/retry_execution_foundation.md`（Architecture Design）を参照。

---

## Retry Queue Update Foundation層（`src/retry_engine/`、v4.1.0 追加）

`RetryExecutionSelector`（v4.0.0）・`RetryExecutionCoordinator`（v4.0.0）が
集約した`RetryExecutionResult`を対象に、対応するRetry Queue項目が
`RetryQueueStatus.COMPLETED` / `FAILED`（v3.1.0で予約値として定義済み）の
どちらへ更新されるべきかを判定する新規コンポーネント`RetryQueueUpdateDecider`
を追加した。

```
RetryManager
   │
   ├── decide_retry_queue_updates(events, dry_run=False)  ★新設
   │      1. self.execute_dispatchable_retries(events, dry_run=dry_run)（v4.0.0、無変更）
   │      2. self._queue_update_decider.decide_all(execution_results)
   │
   └── RetryQueueUpdateDecider（判定）
          + decide(execution_result) -> RetryQueueUpdateDecision
          + decide_all(execution_results) -> list[RetryQueueUpdateDecision]
          RetryQueueManager等への参照を一切持たない、コンストラクタ引数ゼロの
          完全に無状態なコンポーネント

RetryQueueUpdateDecision
   + execution_result: RetryExecutionResult（v4.0.0、分解しない）
   + outcome: RetryQueueUpdateOutcome（COMPLETE / FAIL / NOOP、★新設）
   + target_status: RetryQueueStatus | None（v3.1.0、分解しない）
   + reason: str
```

### 判定方針

「再実行が実際に実行されたか」（`RetryResult.outcome == RETRIED`）を唯一の
分岐点とする。

| `RetryResult`の状態 | 判定結果 | `target_status` |
|---|---|---|
| `RETRIED` かつ `overall_success=True` | `COMPLETE` | `RetryQueueStatus.COMPLETED` |
| `RETRIED` かつ `overall_success=False` | `FAIL` | `RetryQueueStatus.FAILED` |
| `SKIPPED` | `NOOP` | `None`（更新しない） |
| `NOT_FOUND` | `NOOP` | `None`（更新しない） |
| `DISABLED` | `NOOP` | `None`（更新しない） |

`SKIPPED` / `NOT_FOUND` / `DISABLED`はいずれも「再実行が行われていない」
という共通の性質を持つため、`NOOP`という単一の安全側の結果に統一する。
特に`SKIPPED`（`RetryPolicy`が再試行上限到達等で対象外と判定したケース）は、
`NOOP`のまま次Release（Retry Queue Removal、v4.2予定）まで Queue に
滞留し続ける可能性があり、この滞留の扱いは本Foundationの意図的な対象外
としたうえで次Releaseへ申し送っている
（`src/retry_engine/retry_queue_update_decider.py`のコード内コメント・
`docs/design/retry_queue_update_foundation.md` 12章 Future Extension・
16.3節 Recommendation 2）。

### `retry_queue`パッケージへの変更が一切不要だった理由

`RetryQueueStatus.COMPLETED` / `FAILED`はv3.1.0の時点で既に予約値として
定義済みであり、本Releaseは新しい状態値を追加する必要がなかった。「更新
しない」（`NOOP`）状態も`RetryQueueStatus`に新しい値を追加するのではなく、
`retry_engine`側の新規Enum（`RetryQueueUpdateOutcome.NOOP`）と
`target_status=None`の組み合わせで表現した。これにより`retry_queue`
パッケージは本Releaseでもゼロ改修を維持している。

### Queueへの実際の反映は行わない（Foundation First）

`RetryQueueUpdateDecider`は判定結果（`RetryQueueUpdateDecision`）を返す
のみで、`RetryQueueManager.remove()`の呼び出し・Queue内部ストアの書き換え
はいずれも行わない。`RetryQueueUpdateDecision`が`execution_result`
（→`dispatch_event`→`candidate_event`→`run_id` / `candidate`）を分解せず
保持するため、次Release（Retry Queue Removal）が`remove(run_id)`を呼び出す
際に追加の突き合わせを必要としない設計になっている。

### 本Releaseの対象外

`RetryQueueManager.remove()`の呼び出し・`RetryQueueManager.dequeue()`の
本格実装（Queueから実際に取り出して回す自動化）・Queue永続化・判定結果を
Queue内部ストアへ実際に反映する処理・Retry Policy（選別基準の拡張）・
Retry Metrics / Monitoring・実運用のComposition Rootは、いずれもv4.1.0の
対象外であり、将来Releaseで検討する（`docs/ROADMAP.md`「v3.x 以降の候補」
参照）。

詳細は`docs/design/retry_queue_update_foundation_charter.md`（Project
Charter）・`docs/design/retry_queue_update_foundation.md`（Architecture
Design・Architecture Review含む）を参照。

---

## Retry Queue Removal Foundation層（`src/retry_engine/`、v4.2.0 追加）

`RetryQueueUpdateDecider`（v4.1.0）が判定した`RetryQueueUpdateDecision`
（`COMPLETE` / `FAIL` / `NOOP`）を対象に、`outcome`が`COMPLETE`または
`FAIL`の項目についてのみ`RetryQueueManager.remove()`を呼び出し、Queueから
該当項目を除去する新規コンポーネント`RetryQueueRemovalExecutor`を追加した。
`RetryQueueManager.remove()`が本Releaseで初めて構造的に呼び出し可能になる。

```
RetryManager
   │
   ├── apply_retry_queue_removals(events, dry_run=False)  ★新設
   │      1. self.decide_retry_queue_updates(events, dry_run=dry_run)（v4.1.0、無変更）
   │      2. self._queue_removal_executor.apply_all(decisions, remove_fn=self._queue.remove)
   │
   └── RetryQueueRemovalExecutor（除去）
          + apply(decision, remove_fn) -> RetryQueueRemovalResult
          + apply_all(decisions, remove_fn) -> list[RetryQueueRemovalResult]
          RetryQueueManager型を一切importしない、コンストラクタ引数ゼロの
          完全に無状態なコンポーネント。remove操作はremove_fn:
          Callable[[str], RetryQueueResult]としてメソッド引数で受け取る
          （v4.0.0 RetryExecutionCoordinatorのretry_fnと同じパターン）

RetryQueueRemovalResult
   + decision: RetryQueueUpdateDecision（v4.1.0、分解しない）
   + attempted: bool（remove呼び出しを試行したか、★新設）
   + queue_result: RetryQueueResult | None（v3.1.0、分解しない）
   + reason: str
```

### 除去方針

`decision.outcome`が`COMPLETE` / `FAIL`のいずれでもない場合（＝`NOOP`）は
`remove_fn`を一切呼び出さない。

| `decision.outcome` | remove呼び出し | `attempted` |
|---|---|---|
| `COMPLETE` | 呼び出す | `True` |
| `FAIL` | 呼び出す | `True` |
| `NOOP`（`SKIPPED` / `NOT_FOUND` / `DISABLED`由来） | 呼び出さない | `False` |

`run_id`は`decision.execution_result.dispatch_event.candidate_event.run_id`
（v3.8.0で定義済みの既存フィールド）から取得し、追加のQueue問い合わせ
（`list()`等）は発生しない。`remove_fn`の戻り値が`NOT_FOUND` /
`DISABLED`であってもエラーとして扱わない（`RetryQueueManager.remove()`の
既存の正常な結果の範囲内）。

`SKIPPED`（`RetryPolicy`が再試行上限到達等で対象外と判定したケース）は、
本Releaseでも`NOOP`のままremove対象外であり、恒久的にQueueへ滞留し続ける
可能性がある。この滞留への対応（除去する／Dead Letter Queueへ回す等）は、
ユーザー指示により本Releaseでは意図的にスコープ外とし、次Release以降へ
申し送っている（`docs/design/retry_queue_removal_foundation.md` 12章
Future Extension）。

### `RetryQueueManager`型への直接依存を持たない設計

`RetryQueueRemovalExecutor`は`RetryQueueManager` / `NullRetryQueueManager`
型を一切importせず、remove操作は`remove_fn`としてメソッド引数で受け取る。
`RetryManager`が`self._queue.remove`（v3.2.0で既に保持しているバウンド
メソッド）を渡すのみであり、`retry_engine`パッケージ内の実行系・判定系
コンポーネントが具象Managerクラスに依存しないという既存方針
（`RetryExecutionSelector` / `RetryExecutionCoordinator` /
`RetryQueueUpdateDecider`と同じ）を、実際にQueueへ書き込みを行う本
コンポーネントでも維持している。

### 本Releaseの対象外

`SKIPPED`（`max_attempts`到達）のQueue滞留対応（除去・Dead Letter
Queue化）・Queue永続化・Retry Policy（選別基準の拡張）・Retry Metrics /
Monitoring・Queue最適化（heapqベースのPriority Queue化等）・Scheduler
改修・`RetryQueueManager.dequeue()`の本格実装・実運用のComposition Root
は、いずれもv4.2.0の対象外であり、将来Releaseで検討する
（`docs/ROADMAP.md`「v3.x 以降の候補」参照）。

詳細は`docs/design/retry_queue_removal_foundation_charter.md`（Project
Charter）・`docs/design/retry_queue_removal_foundation.md`（Architecture
Design・Architecture Review含む）を参照。

---

## Retry Queue Cleanup Foundation層（`src/retry_engine/`、v4.3.0 追加）

`RetryQueueUpdateDecider`（v4.1.0）が判定した`RetryQueueUpdateDecision`の
うち、`outcome`が`NOOP`かつ`retry_result.outcome`が`SKIPPED`
（`max_attempts`到達）の項目についてのみ`RetryQueueManager.remove()`を
呼び出し、Queueから該当項目を除去する新規コンポーネント
`RetryQueueCleanupDecider`（判定）・`RetryQueueCleanupExecutor`（除去実行）
を追加した。v4.2.0で対象外だった`SKIPPED`由来のQueue滞留に、本Releaseで
初めて対応する。

```
RetryManager
   │
   ├── decide_retry_queue_cleanup(events, dry_run=False)  ★新設
   │      1. self.decide_retry_queue_updates(events, dry_run=dry_run)（v4.1.0、無変更）
   │      2. self._queue_cleanup_decider.decide_all(update_decisions)
   │
   ├── apply_retry_queue_cleanup(events, dry_run=False)  ★新設
   │      1. self.decide_retry_queue_cleanup(events, dry_run=dry_run)
   │      2. self._queue_cleanup_executor.apply_all(cleanup_decisions, remove_fn=self._queue.remove)
   │
   ├── RetryQueueCleanupDecider（判定）
   │      + decide(update_decision) -> RetryQueueCleanupDecision
   │      + decide_all(update_decisions) -> list[RetryQueueCleanupDecision]
   │      RetryQueueManager型を一切importしない、コンストラクタ引数ゼロの
   │      完全に無状態なコンポーネント
   │
   └── RetryQueueCleanupExecutor（除去実行）
          + apply(decision, remove_fn) -> RetryQueueCleanupResult
          + apply_all(decisions, remove_fn) -> list[RetryQueueCleanupResult]
          remove操作はremove_fn: Callable[[str], RetryQueueResult]として
          メソッド引数で受け取る（v4.2.0 RetryQueueRemovalExecutorと同じパターン）

RetryQueueCleanupDecision
   + update_decision: RetryQueueUpdateDecision（v4.1.0、分解しない）
   + outcome: RetryQueueCleanupOutcome（CLEANUP / KEEP、★新設）
   + reason: str

RetryQueueCleanupResult
   + decision: RetryQueueCleanupDecision（★新設、分解しない）
   + attempted: bool（remove呼び出しを試行したか）
   + queue_result: RetryQueueResult | None（v3.1.0、分解しない）
   + reason: str
```

### Cleanup方針

| `update_decision.outcome` | `retry_result.outcome` | 判定 | remove呼び出し |
|---|---|---|---|
| `COMPLETE` | `RETRIED`（成功） | `KEEP` | 呼び出さない（v4.2.0で既に除去済みのはず） |
| `FAIL` | `RETRIED`（失敗） | `KEEP` | 呼び出さない（同上） |
| `NOOP` | `SKIPPED` | `CLEANUP` | 呼び出す |
| `NOOP` | `NOT_FOUND` | `KEEP` | 呼び出さない（本Releaseの対象外） |
| `NOOP` | `DISABLED` | `KEEP` | 呼び出さない（本Releaseの対象外） |

`update_decision.execution_result.dispatch_event.candidate_event.run_id`
（v3.8.0で定義済みの既存フィールド）から`run_id`を取得し、追加のQueue
問い合わせは発生しない。Dead Letter Queue・隔離Queueといった新しい
Queueステータスは追加せず、既存の`RetryQueueManager.remove()`
（v3.1.0、`status=CANCELLED`に更新後削除）をそのまま再利用する。

### `RetryQueueManager`型への直接依存を持たない設計

`RetryQueueCleanupDecider` / `RetryQueueCleanupExecutor`はいずれも
`RetryQueueManager` / `NullRetryQueueManager`型を一切importしない。
Decider側は既存の`RetryQueueUpdateDecision`のみを入力とし、Executor側の
remove操作は`remove_fn`としてメソッド引数で受け取る。`RetryExecutionSelector` /
`RetryExecutionCoordinator` / `RetryQueueUpdateDecider` /
`RetryQueueRemovalExecutor`と同じ既存方針を維持している。

### 本Releaseの対象外

`NOT_FOUND` / `DISABLED`由来の`NOOP`のCleanup方針・Dead Letter Queue・
Queue永続化・Retry Policy（選別基準の拡張）・Retry Metrics /
Monitoring・Queue最適化・Scheduler改修・実運用のComposition Rootは、
いずれもv4.3.0の対象外であり、将来Releaseで検討する
（`docs/ROADMAP.md`「v3.x 以降の候補」参照）。

詳細は`docs/design/retry_queue_cleanup_foundation_charter.md`（Project
Charter）・`docs/design/retry_queue_cleanup_foundation.md`（Architecture
Design・Architecture Review含む）を参照。

---

## Retry Policy Foundation層（`src/retry_engine/`、v4.5.0 追加）

`RetryManager`が`RetryPolicy`に対して実際に依存している面（`retry()`が
呼び出す`should_retry(monitor_status, attempt) -> bool`、`_skip_reason()`が
参照する`target_statuses` / `max_attempts`）を、Protocol（構造的部分型）
として明示化した。既存の`RetryPolicy`（v3.0.0、固定ルールによる実装）は
**本Releaseでも無改修（0 diff）**のまま、Protocolの性質上、明示的な継承
なしに構造的にこの契約を満たす。

```
src/retry_engine/
   │
   ├── retry_policy.py（v3.0.0、無改修・0 diff）
   │     RetryPolicy（frozen dataclass）
   │       - target_statuses / max_attempts
   │       - should_retry(monitor_status, attempt) -> bool
   │
   ├── retry_policy_protocol.py ★新設
   │     RetryDecisionPolicy（Protocol, @runtime_checkable）
   │        + should_retry(monitor_status, attempt) -> bool
   │        「再試行すべきか」を判定する、あらゆるRetry戦略に共通する最小契約
   │     ExplainableRetryPolicy（Protocol, @runtime_checkable。RetryDecisionPolicyを拡張）
   │        + target_statuses: frozenset[WorkflowMonitorStatus]
   │        + max_attempts: int
   │        RetryDecisionPolicyに加え、_skip_reason()がスキップ理由の
   │        文字列を生成するために必要とする属性を公開する契約
   │
   └── retry_manager.py（型注釈のみ変更）
         RetryManager.__init__() / from_config() の
         policy: RetryPolicy → policy: ExplainableRetryPolicy
         retry() / _skip_reason() のロジック本体は無変更
```

### 契約を2段階に分離した設計（Single Responsibility）

`should_retry()`のみを要求する`RetryDecisionPolicy`（最小契約）と、
それに`target_statuses` / `max_attempts`を加えた`ExplainableRetryPolicy`
（説明可能契約）を分けたのは、将来`target_statuses` / `max_attempts`という
概念を持たない戦略（例：`ExponentialBackoffPolicy`）が、無関係な属性
（Fixed Retry Policy固有の語彙）を持たされずに済むようにするため。
`RetryManager`は現時点で`_skip_reason()`が実際に両属性を必要とするため
`ExplainableRetryPolicy`を型注釈として使用するが、将来`_skip_reason()`の
この依存を切り離した場合は`RetryDecisionPolicy`（最小契約）まで narrow
できる余地を残している。

### `RetryManager`の変更は型注釈のみ

`__init__` / `from_config()`の`policy` / `retry_policy`引数の型を
`RetryPolicy`（具体クラス）から`ExplainableRetryPolicy`（抽象契約）へ
変更したのみで、`retry()` / `_skip_reason()`のロジック本体は1行も
変更していない。Pythonは型注釈を実行時に強制しないため、既存の
`RetryManager(policy=RetryPolicy(...), ...)`という呼び出しは本Release
前後でまったく同じ結果になる。

### 構造適合の確認方法

`RetryDecisionPolicy` / `ExplainableRetryPolicy`はいずれも
`@runtime_checkable`を付与しているため、`isinstance()`による構造適合の
確認が可能。ただしこれはメソッド・属性の**存在**のみを検証し、シグネチャ
（引数の型・個数・戻り値の型）までは検証しないため、実際の差し替え
可能性の確認には`RetryManager(policy=fake, ...).retry(...)`を呼び出す
振る舞いテストとの併用が必須（`tests/test_e2e_v4_5_0_retry_policy_foundation.py`
参照）。

### 本Releaseの対象外（Non-Goal）

`FixedRetryPolicy` / `ExponentialBackoffPolicy` / `AdaptiveRetryPolicy`
等、`RetryDecisionPolicy` / `ExplainableRetryPolicy`を満たす具体的な
新戦略の実装は**本Releaseの対象外**。本Releaseは「差し替え可能な構造」を
整備するところまでに留めた。複数戦略を実行時に選択・切り替える
Composition Rootも同様に対象外（`docs/ROADMAP.md`「v3.x 以降の候補」参照）。

詳細は`docs/design/retry_policy_foundation_charter.md`（Project
Charter）・`docs/design/retry_policy_foundation.md`（Architecture
Design・Architecture Review含む）を参照。

---

## Retry Enqueue Trigger Foundation層（`src/retry_enqueue_trigger/`、v4.6.0 追加）

v3.0.0〜v4.5.0の16回のReleaseで、Retry Queue（v3.1.0）からRetry Engine
（v3.0.0）を経てQueueの後始末（Update / Removal / Cleanup / Terminal
Cleanup、v4.1.0〜v4.4.0）に至る**下流**のパイプラインが完成した。しかし
`RetryQueueManager.enqueue()` / `RetryManager.enqueue_retry()`はコード
ベース全体のどこからも呼び出されておらず、Queueへ実際に項目を投入する
**上流**が存在しなかった。本Releaseはこの欠落を埋める新規独立パッケージ
`src/retry_enqueue_trigger/`を追加する。

```
WorkflowMonitorManager（v2.9.0、無改修）
   │  list_status() でFAILED/TIMEOUTを判定
   ▼
RetryEnqueueTrigger / NullRetryEnqueueTrigger（v4.6.0、新規） ★本Release
   │  RetryQueueManager.exists() で重複を確認
   ▼
RetryQueueManager（v3.1.0、無改修）
   │  enqueue() でWAITING状態のRetryQueueItemを追加
   ▼
（v3.3.0〜v4.5.0の既存下流パイプラインが初めて実データを受け取れる）
```

### `retry_engine`を経由しない依存方向

`RetryEnqueueTrigger`は`WorkflowMonitorManager` / `RetryQueueManager`に
Constructor Injectionで直接依存し、`retry_engine`（`RetryManager.
enqueue_retry()`）は経由しない。`RetrySchedulerSource`（v3.3.0）が
`retry_engine`を経由せず`retry_queue`に直接依存する既存パターンと同じ
判断であり、`RETRY_ENGINE_ENABLED=false`（デフォルト）の状態でも
Queueへの投入自体は可能な構造としている（Queueへの投入自体は外部副作用を
伴わないメモリ操作であり、`RetryQueueConfig.enabled`のデフォルトが`true`
である既存設計と同じ分類に属するため。実際にRetryを実行するかは引き続き
下流の`RetryConfig.enabled`で止まる）。

### Feature Gate・Configクラスを持たない設計

`RetrySchedulerSource` / `NullRetrySchedulerSource`（v3.3.0）と同じ
Null Object Patternを踏襲し、`RetryEnqueueTrigger` / `NullRetryEnqueueTrigger`
のどちらを構築するかを呼び出し元が選ぶことで有効/無効を表現する。
`RetryEnqueueTriggerConfig`のような起動口・環境変数は追加しない。

### Known Issue：Queueから除去された`run_id`の無限再投入リスク

Queue内の重複防止は`RetryQueueManager.exists()`のみで行う。`RetryExecutor`
（v3.0.0、無改修）は再実行のたびに**新しい`run_id`**を発行し、`metadata`に
`{"retried_from": 元run_id}`を記録するため、元`run_id`のExecution History
記録・Workflow Monitor判定は不変のままである。そのため、Queueから一度
除去（`COMPLETE` / `FAIL` / `CLEANUP`）された`run_id`が、Monitor上でなお
`FAILED` / `TIMEOUT`のまま観測され続けると、`enqueue_pending_failures()`
が呼ばれるたびに無限に再投入されうる。本Releaseではこの対策を意図的に
実装しない（呼び出し元＝Composition Rootが存在しないため実害はない）。

> **v4.7.0での追記**：ここで挙げていた「`metadata["retried_from"]`を
> 手掛かりにする」対策案は、調査の結果**実際には機能しないことが判明した**
> （`WorkflowExecutionRecord`に`metadata`フィールドが存在せず、
> `WorkflowEngineExecutor`もExecution Historyへ渡していないため）。
> v4.7.0（Retry History Foundation）は、情報源を`RetryResult`に
> 限定した再試行履歴の記録基盤（`RetryHistoryManager`）を新設したが、
> `RetryEnqueueTrigger`側からの参照・ガード判定（無限再投入対策の完成）は
> 次Release（Retry Enqueue Guard）に送った。詳細は次項
> 「Retry History Foundation層」を参照。

### 本Releaseの対象外（Non-Goal）

`RetryEnqueueTrigger`を定期的に駆動する起動スクリプト（Composition
Root）・無限再投入対策（Retry History）・`dequeue()`の解禁・Retry Queueの
永続化はいずれも**本Releaseの対象外**。既存の`workflow_monitor` /
`retry_queue` / `retry_engine`はいずれも無改修（ゼロ改修）。

詳細は`docs/design/retry_enqueue_trigger_foundation_charter.md`（Project
Charter）・`docs/design/retry_enqueue_trigger_foundation.md`（Architecture
Design・Architecture Review含む）を参照。

---

## Retry History Foundation層（`src/retry_history/`、v4.7.0 追加）

`original_run_id`ごとの再試行履歴（試行回数・直近記録時刻）を記録するだけの
最小基盤。前項のKnown Issue（無限再投入リスク）への対策として、v4.6.0が
挙げていた「`metadata["retried_from"]`を手掛かりにする」案が実際には
機能しないことが判明したため、情報源を`RetryResult`（`retry_engine`自身が
生成するデータ）に限定した新しい記録基盤として設計された。

```
Retry Engine（再実行判断・依頼、v3.0.0〜v4.6.0）
   │
   └── RetryManager.execute_dispatchable_retries()（v4.0.0、無変更）
          │  RetryExecutionResult（retry_result.outcomeを含む）
          ▼
   RetryHistoryRecordExecutor（retry_engine内、Stateless） ★本Release
          │  outcome=RETRIEDの項目のみ抽出
          ▼
   RetryHistoryManager（retry_history、新規独立パッケージ） ★本Release
          │  original_run_idごとにattempt_countを記録
          ▼
（次Release以降：RetryEnqueueTrigger等の消費側で無限再投入対策として利用）
```

### 情報源についての訂正：`metadata["retried_from"]`は参照不可能

v4.6.0のKnown Issueは対策候補として`metadata["retried_from"]`
（`RetryExecutor.execute()`がv3.0.0から`WorkflowEngineEvent.metadata`に
記録している）を挙げていたが、調査の結果これは実際には機能しないことが
判明した。`WorkflowEngineExecutor`はこの`metadata`を
`ExecutionHistoryManager.start_run()`へ渡しておらず、
`WorkflowExecutionRecord`（`execution_history/workflow_execution_record.py`）
自体に`metadata`フィールドが存在しない。したがって`WorkflowMonitorRecord`
（Workflow Monitorの公開データ）からも`retried_from`は一切参照できない。

本Releaseはこの事実を踏まえ、情報源を`RetryResult`（`retry_engine`自身が
`RetryManager.retry()`実行のたびに直接生成するデータ）に限定した。
`execution_history`パッケージのスキーマ変更は一切必要とせず、
`execution_history`は本Releaseでも無改修である。

### 責務の境界（原則）

- **記録のみを責務とする。** Retry可否判定・Retry実行・Queue操作・
  Enqueueガード判定はいずれも行わない（それらは`RetryPolicy` /
  `RetryManager` / 将来の消費側コンポーネントの責務のまま）
- **`retry_history`は`retry_engine`を一切importしない、独立した葉
  パッケージ。** `retry_queue`と同型（標準ライブラリのみに依存）
- **`RetryHistoryRecordExecutor`はStateless。** `RetryHistoryManager` /
  `NullRetryHistoryManager`型への直接依存を持たず、記録操作は
  `record_fn`としてメソッド引数で受け取る（`RetryQueueRemovalExecutor`、
  v4.2.0と同じ設計言語）

### Feature Gateの扱い

Configクラス・Feature Gateは追加しない。`history`引数省略時は
`NullRetryHistoryManager()`にフォールバックする。`RetryHistoryManager`は
`RetryQueueManager`と同じstateful storeであるため、Stateless系
コンポーネント（`event_consumer`等、省略時は実体へフォールバック）とは
異なり、`queue`引数と同じ「省略時はNullへフォールバックする」方式を
採用した。

### 本Releaseの対象外（Non-Goal）

記録結果を使って`RetryEnqueueTrigger.enqueue_pending_failures()`側の
再enqueueを止める判定（無限再投入対策の完成）・`RetryPolicy.max_attempts`
との統合判定・Composition Root・永続化はいずれも**本Releaseの対象外**。
`workflow_monitor` / `retry_queue` / `workflow_engine` / `scheduler` /
`retry_enqueue_trigger`はいずれも無改修（ゼロ改修）。

詳細は`docs/design/retry_history_foundation_charter.md`（Project
Charter）・`docs/design/retry_history_foundation.md`（Architecture
Design・Architecture Review含む）を参照。

---

## Retry Enqueue Guard層（`src/retry_enqueue_trigger/retry_enqueue_guard.py`、v4.8.0 追加）

v4.6.0 Known Issue（Queueから除去された`run_id`の無限再投入リスク）・
v4.7.0 Future Extension「Retry Enqueue Guard」を接続し、無限再投入対策を
完成させたRelease。`RetryHistoryManager`（v4.7.0）が記録した再試行履歴を
`RetryEnqueueTrigger`（v4.6.0）が参照できるようにした。

```
WorkflowMonitorManager（判定、v2.9.0、無改修）
   │
   ▼
RetryEnqueueTrigger（Adapter、v4.6.0、拡張） ★本Release
   │
   ├── RetryHistoryManager.has_history()（v4.7.0、無改修）を参照
   │      └── RetryEnqueueGuard.decide() で ALLOW/BLOCK を判定（新規） ★本Release
   │
   └── RetryQueueManager.enqueue()（v3.1.0、無改修）
```

### 対策が安全性上必須であることの技術的根拠

`RetryEnqueueTrigger.enqueue_pending_failures()`は`queue.enqueue()`呼び出し時に
`retry_attempt`を明示的に渡しておらず、常にデフォルト値`1`固定でQueueへ
投入される。下流の`RetryExecutionCoordinator.execute()`はQueue項目由来の
この`1`をそのまま`RetryManager.retry()`の`attempt`引数として使うため、
`RetryPolicy.should_retry()`は常に`attempt=1 < max_attempts`（デフォルト3）
という条件で判定される。つまり`attempt`は実際の累積試行回数と連動して
いない。無対策のままComposition Root（定期実行）が実装されると、同一
`run_id`のWorkflowが無制限に再実行されうる（News収集・WordPress下書き
投稿等の実際の副作用込みで）。本Releaseの`RetryEnqueueGuard`はこれを
止める唯一の現実的なセーフティネットである。

### Guard判定は「履歴の有無」の二値のみ

`RetryHistoryRecord.attempt_count`と`RetryPolicy.max_attempts`を比較する、
より精密な判定も技術的には可能だが、これは`retry_enqueue_trigger`が
`retry_engine`（`RetryPolicy`）へ新たに依存することを意味し、v4.6.0の
「`retry_engine`を経由しない」という設計方針を崩す。また`attempt`が実回数と
連動していない現状の構造では、これ以上精密な判定を導入しても正しく
機能しない。そのため`RetryEnqueueGuard.decide(run_id, has_history) ->
ALLOW/BLOCK`という単純な二値判定を採用した（`RetryEnqueueGuard`は
`RetryHistoryManager`型はもちろん`retry_history`パッケージ自体も一切
importしない。`has_history: bool`という既に解決済みの値のみを
`RetryEnqueueTrigger`から受け取る、完全にStatelessなコンポーネント）。

### 新たに生じた制約（Known Issue）

`RETRY_MAX_ATTEMPTS`（デフォルト3）を活かした複数回の自動リトライ運用は、
`RetryEnqueueTrigger`経由では本Release後も実質的に機能しないままである
（一度でも再試行履歴があれば、以後は同じ`original_run_id`が二度と自動
enqueueされないため）。安全性を最優先する意図的な設計判断であり、複数回
リトライを実現するには「`attempt`の実回数連動」（`RetryHistoryRecord.
attempt_count`をQueueへのenqueue時点の`retry_attempt`へ反映する統合）を
別Releaseで先に実装したうえで、Guardの判定基準を「履歴の有無」から
「`attempt_count >= max_attempts`」へ精緻化する必要がある。

### 本Releaseの対象外（Non-Goal）

`attempt`の実回数連動・Guard判定基準の精緻化・Composition Root・
`RetryHistoryManager`の永続化・Feature Gate/Configクラスの新設はいずれも
**本Releaseの対象外**。`workflow_monitor` / `retry_queue` / `retry_history` /
`retry_engine`はいずれも無改修（ゼロ改修）。

詳細は`docs/design/retry_enqueue_guard_charter.md`（Project Charter）・
`docs/design/retry_enqueue_guard.md`（Architecture Design・Architecture
Review含む）を参照。

---

## Retry Attempt Synchronization Foundation層（`src/retry_enqueue_trigger/retry_enqueue_trigger.py`、v4.9.0 追加）

v4.8.0 Known Issue（`RETRY_MAX_ATTEMPTS`を活かした複数回リトライが実質
機能しない制約）のうち、「`attempt`の実回数連動」（Future Extension項目1）
のみを実装したRelease。Guard判定基準の精緻化（項目2）は対象外のまま。

```
RetryEnqueueTrigger.enqueue_pending_failures()
   │
   ├── self._history.get(run_id)  ★本Release（旧: has_history()）
   │      ├── has_history = history_record is not None
   │      │      └── RetryEnqueueGuard.decide()（v4.8.0、無改修）で ALLOW/BLOCK
   │      └── next_attempt = history_record.attempt_count + 1（履歴なしは1） ★本Release
   │
   └── RetryQueueManager.enqueue(..., retry_attempt=next_attempt)  ★本Release（旧: 常に1固定）
```

### 変更対象は1メソッドのみ

コード調査の結果、`retry_attempt`を発行元から下流（`RetryQueueItem` →
`RetryExecutionCoordinator.execute()` → `RetryManager.retry(attempt=...)` →
`RetryPolicy.should_retry()`）まで正しく伝播する経路は既に完成しており、
欠けていたのは`RetryEnqueueTrigger.enqueue_pending_failures()`がその値を
解決してQueueへ渡す1箇所のみであることを確認した。`RetryQueueManager` /
`RetryHistoryManager` / `RetryEnqueueGuard` / `RetryExecutionCoordinator` /
`RetryManager` / `RetryPolicy`はいずれも無改修。

### 本Release単体では観測可能な挙動変化が発生しない

`RetryEnqueueGuard`（v4.8.0）は「履歴が1回でもあればBLOCK」の二値判定の
ままであるため、`queue.enqueue()`に実際に到達するのは`history_record is
None`（＝この`run_id`は一度もretryされていない）ケースのみであり、この
分岐における`next_attempt`は常に`1`にしかならない。これは不具合ではなく、
Guardの判定基準精緻化を将来Releaseへ送るための意図的な「消費者不在の
配線」である（v3.1.0 Retry Queue・v3.5.0 Retry Scheduler Decision・v4.7.0
Retry History Foundationと同型のFoundation First）。

### 本Releaseの対象外（Non-Goal）

Guard判定基準の精緻化（`attempt_count >= max_attempts`比較）・
`RetryPolicy` / `RetryExecutionCoordinator` / `RetryManager`への変更・
Composition Root・`.env.example`整備はいずれも**本Releaseの対象外**。

詳細は`docs/design/retry_attempt_synchronization_foundation.md`
（Project Charter / Architecture Design・Architecture Review含む）を参照。

---

## Retry Enqueue Guard Refinement Foundation層（`src/retry_enqueue_trigger/`、v5.0.0 拡張）

v4.9.0で配線済みだった「`attempt`の実回数連動」に、初めて実際の消費者を
与えたRelease。`RetryEnqueueGuard`（v4.8.0）の判定基準を「履歴の有無」の
二値から「`next_attempt > max_attempts`」の回数比較へ精緻化した。

```
RetryEnqueueTrigger.enqueue_pending_failures(limit=None, max_attempts=1)
   │                                          ★max_attemptsは呼び出し引数（__init__は無変更）
   ├── self._history.get(run_id)（v4.9.0、無改修）
   │      └── next_attempt = history_record.attempt_count + 1（履歴なしは1）
   │
   ├── RetryEnqueueGuard.decide(run_id, next_attempt, max_attempts)  ★本Release（旧: has_history）
   │      └── next_attempt > max_attempts で BLOCK、そうでなければ ALLOW
   │
   └── RetryQueueManager.enqueue(..., retry_attempt=next_attempt)（無改修）
```

### `max_attempts`はConstructor InjectionではなくMethod引数（Architecture Review Finalでの再検討）

当初のArchitecture Reviewでは`RetryEnqueueTrigger.__init__(..., max_attempts:
int = 1)`という案だったが、ChatGPTレビューで「Triggerが設定値を長期保持する
責務まで持つべきか」を再検討した結果、`enqueue_pending_failures(limit=None,
max_attempts=1)`という呼び出し引数へ変更した。既存の`limit`と同じ「呼び出し
の都度渡す」スタイルに統一したことで、`RetryEnqueueTrigger.__init__`は
本Releaseでも1文字も変わらず、Stateless性・Single Responsibility・
Backward Compatibilityのいずれも向上した。

### `max_attempts`のデフォルト値は`RetryPolicy.max_attempts`と意図的に独立

`RetryPolicy.max_attempts`（デフォルト3、環境変数`RETRY_MAX_ATTEMPTS`）は
`retry_engine`内で完結する業務ルールである。`retry_enqueue_trigger`が
これを直接参照する案（二重管理の解消）も検討したが、v4.6.0の「`retry_engine`
を経由しない」という設計方針を優先し、採用しなかった。
`enqueue_pending_failures()`の`max_attempts`デフォルト値`1`は、呼び出し元が
明示的に業務ルールを注入しなかった場合の構造的セーフガードであり、
v4.8.0/v4.9.0時点とまったく同じ安全側の挙動（履歴が1件でもあれば以降
ブロック）を再現する。両者は別の意味を持つ独立した値として扱う。

### DTO（`RetryEnqueueOptions`等）は本Releaseでは導入しない

現時点でGuard判定に渡すPolicy値は`max_attempts`の1項目のみであり、YAGNI・
Development Charter 8章「抽象化は必要になってから行う」に従い、素朴な
引数のまま維持した。将来`retry_delay` / `batch_size` / `priority`等が
具体的に2件以上必要になった時点で、`frozen=True`の`dataclass`による
Immutable Value Object導入を再検討する。

### 本Releaseの対象外（Non-Goal）

Composition Root（`RetryPolicy.from_env().max_attempts`を実際に注入する
起動導線）・`RetryEnqueueOptions`等のDTO・`.env.example`整備はいずれも
**本Releaseの対象外**。`retry_history` / `retry_queue` / `workflow_monitor` /
`retry_engine`はいずれも無改修（ゼロ改修）。

詳細は`docs/design/retry_enqueue_guard_refinement_foundation.md`
（Project Charter / Architecture Design・Architecture Review Final含む）を参照。

---

## Retry Composition Root Foundation層（`src/retry_composition/`、v5.1.0 追加）

v5.0.0までに完成した「Guard判定基準の精緻化」が実運用で意味を持つためには、
`RetryEnqueueTrigger`（Enqueue側）と`RetryManager`（Execute側）が同一の
`RetryQueueManager` / `RetryHistoryManager`インスタンスを共有している必要がある。
`RetryQueueManager` / `RetryHistoryManager`はいずれもプロセス内メモリの`dict`のみで
状態を保持するため、両者を別々に構築すると、それぞれが独立した空のQueue/Historyを
持つことになり、Guardの回数比較判定が機能しない。本Releaseはこの前提条件を整える
新規パッケージ`src/retry_composition/`（`RetryCompositionRoot`）を追加する。

```
RetryCompositionRoot.from_env()
   │
   ├─ WorkflowMonitorManager.from_config(...)（既存、無改修）
   ├─ RetryQueueManager.from_config(...)      ★1インスタンスのみ生成
   ├─ RetryHistoryManager()                    ★1インスタンスのみ生成
   ├─ RetryEnqueueGuard()（既存、無改修）
   ├─ RetryEnqueueTrigger(monitor, queue, history, guard)（既存、無改修）
   │
   ├─ RetryPolicy.from_env()（既存、無改修）
   ├─ WorkflowEngineManager.from_config(...)（既存、無改修）
   └─ RetryManager.from_config(
          ..., retry_queue_manager=queue, retry_history_manager=history,
      )（既存、無改修）★triggerと同一のqueue/historyインスタンスを注入
```

### 責務は「組み立てて公開すること」のみ

`RetryCompositionRoot`は`from_env()`以外の公開メソッドを持たない。
`enqueue_pending_failures()` / `execute_dispatchable_retries()`等を呼び出す実行順序の
決定（例：`run_once()`）・ループ・デーモン化・起動スクリプトはいずれも本Releaseの
対象外とした（「Composition（組み立て）」と「オーケストレーション（実行順序の決定）」を
明確に分離する設計判断）。既存パッケージ8つ（`workflow_monitor` / `retry_queue` /
`retry_history` / `retry_enqueue_trigger` / `retry_engine` / `workflow_engine` /
`ai` / `execution_history`）はいずれも無改修（ゼロ改修）。

### 配置・命名（Architecture Reviewでの検討）

パッケージ配置は`src/retry_composition/`とした。`src/`配下の既存16パッケージは
いずれもドメインスコープの命名であり、`src/runtime/`・`src/application/`のような
汎用Compositionレイヤは、Composition Rootが必要な系統が現時点で`retry`関連の1つに
限られる段階では時期尚早な抽象化（YAGNI）と判断し不採用とした。クラス名は
`RetryCompositionRoot`とした。「Runtime」は実行責任を連想させ「組み立てのみ・実行
しない」という責務境界と矛盾するため不採用、「Builder」「Factory」は生成後の関心を
持たない使い捨てのイメージが強く、`trigger` / `manager`への参照を保持し続ける本
クラスの性質と不一致と判断し、DI文脈で確立した「Composition Root」という語をそのまま
採用した。

### 本Releaseの対象外（Non-Goal）

実行順序の決定・ループ・デーモン化・`RetryCompositionRoot`を実際に呼び出す起動
スクリプト・`RetryQueueManager` / `RetryHistoryManager`の永続化・新規Configクラス・
Feature Gateはいずれも**本Releaseの対象外**。`workflow_monitor` / `retry_queue` /
`retry_history` / `retry_enqueue_trigger` / `retry_engine` / `workflow_engine` /
`ai` / `execution_history`はいずれも無改修（ゼロ改修）。

詳細は`docs/design/retry_composition_root_foundation.md`
（Project Charter / Architecture Design・Architecture Review Final含む）を参照。

---

## Retry Runtime Orchestrator Foundation層（`src/retry_runtime_orchestrator/`、v5.2.0 追加）

v5.1.0がQueue/History共有の前提条件を整えた後、Architecture Reviewの過程で2つの発見が
あった。（発見A）`RetryManager.execute_dispatchable_retries(events)`が要求する
`events: list[SchedulerEvent]`は`RetryQueueManager → RetrySchedulerSource →
RetrySchedulerDecision → SchedulerEngine`という経路でしか得られないが、v5.1.0の
`RetryCompositionRoot`はこの経路を配線していなかった。（発見B）`RetryManager`の
上位メソッド群（`apply_retry_queue_removals()`等）はそれぞれ独立に
`execute_dispatchable_retries()`を再計算するため、同一`events`に対して複数呼び出すと
`retry()`が重複実行されるリスクがある。

本Releaseはこの2つの発見に対応する。

```
RetryCompositionRoot.from_env()
   │
   ├─ ...（v5.1.0までの組み立て、無変更）...
   ├─ RetrySchedulerSource(queue)                          ★新規
   ├─ RetrySchedulerDecision(retry_source)                  ★新規
   ├─ SchedulerEngine(retry_source=..., retry_decision=...) ★新規
   └─ ...（policy・manager組み立て、無変更）...

RetryRuntimeOrchestrator.from_composition_root(root)
   └─ trigger / scheduler / manager / queue / history / policy を
      rootと同一インスタンスのまま保持するだけ（新規インスタンス生成なし）
```

### Composition（組み立て）とOrchestration（実行順序）の責務分離

`RetryCompositionRoot`は今後もDependency Injectionのみを責務とし、実行系メソッド
（`run()` / `run_once()`等）は追加しない。新設した`RetryRuntimeOrchestrator`は
「Retry Runtimeの実行順序を将来管理する場所」だが、本Releaseでは`run()` /
`run_once()` / `loop()` / `daemon()`等のBusiness Logicは一切実装しない。

### 保持する依存を`queue` / `history` / `policy`まで広げた理由

`RetryRuntimeOrchestrator`は`trigger` / `scheduler` / `manager`に加え、
`queue` / `history` / `policy`も本Releaseから保持する。次Execution Releaseで
`queue.remove` / `history.record`をDecider/Executorへのコールバックとして渡すこと、
`policy.max_attempts`を`enqueue_pending_failures()`へ渡すことが確定しているため、
Foundation Release完了直後に避けられるConstructor変更が発生することを防いだ
（Development Charter 8章の「使われる保証のない実装の先回り」には該当しない。
利用が確定した参照の保持のみであり、Business Logicの実装ではないため）。
`guard`（`RetryEnqueueTrigger`専属の内部コンポーネント）・`monitor`（将来依存が
未確定）は保持しない。

### 発見Bへの対応方針（`RetryManager`は無改修のまま）

`RetryManager`へ`run_cycle()`等の統合APIを追加する案は、`RetryManager`が
Trigger/Scheduler/Cleanup/Historyの呼び出し順序まで知ることになりSingle
Responsibilityから外れる可能性があるため不採用とした。代わりに、次Execution
Releaseで`RetryRuntimeOrchestrator`が`execute_dispatchable_retries()`を1回だけ
呼び出し、その結果（`RetryExecutionResult`のリスト）を保持したうえで、
`retry_engine`が既に公開しているStateless・無引数コンストラクタのDecider/Executor群
（`RetryQueueUpdateDecider` / `RetryQueueRemovalExecutor` / `RetryQueueCleanupDecider` /
`RetryQueueCleanupExecutor` / `RetryQueueTerminalCleanupDecider` /
`RetryQueueTerminalCleanupExecutor` / `RetryHistoryRecordExecutor`）へ直接配布する
方針を確定した。これにより`retry_manager.py`は本Releaseでも無改修であり、次
Execution Releaseでも無改修のまま実装できる見込みである。

### 本Releaseの対象外（Non-Goal）

`run()` / `run_once()` / `loop()` / `daemon()`の実装、発見Bの解決の実装（方針の確定
のみ）、`scripts/`層へのBusiness Flowの実装はいずれも**本Releaseの対象外**。
`workflow_monitor` / `retry_queue` / `retry_history` / `retry_enqueue_trigger` /
`retry_engine` / `workflow_engine` / `ai` / `execution_history` / `scheduler` /
`retry_scheduler_source` / `retry_scheduler_decision`はいずれも無改修（ゼロ改修）。

詳細は`docs/design/retry_runtime_orchestrator_foundation.md`
（Project Charter / Architecture Design・Architecture Review Final含む）を参照。

---

## Retry Runtime Run Once Foundation層（`src/retry_runtime_orchestrator/`、v5.3.0 追加）

v5.2.0で確定した方針どおり、`RetryRuntimeOrchestrator`へ`run_once()`を追加し、
Retry Runtimeを1サイクルだけ安全に実行できるようにした。

```
RetryRuntimeOrchestrator.run_once()
   │
   ├─ 1. self.trigger.enqueue_pending_failures(max_attempts=self.policy.max_attempts)
   ├─ 2. events = self.scheduler.run_due(jobs=[])   ← Retry候補由来のSchedulerEventのみ
   ├─ 3. execution_results = self.manager.execute_dispatchable_retries(events)  ← 必ず1回だけ
   ├─ 4. decisions = RetryQueueUpdateDecider().decide_all(execution_results)
   ├─ 5. RetryQueueRemovalExecutor().apply_all(decisions, remove_fn=self.queue.remove)
   ├─ 6. RetryQueueCleanupExecutor().apply_all(
   │        RetryQueueCleanupDecider().decide_all(decisions), remove_fn=self.queue.remove)
   ├─ 7. RetryQueueTerminalCleanupExecutor().apply_all(
   │        RetryQueueTerminalCleanupDecider().decide_all(decisions), remove_fn=self.queue.remove)
   └─ 8. RetryHistoryRecordExecutor().record_all(execution_results, record_fn=self.history.record)
        │
        └─ RetryRuntimeCycleResult（trigger_result / scheduler_events / execution_results /
           removal_results / cleanup_results / terminal_cleanup_results / history_results）を返す
```

### 発見B（多重実行リスク）の解消

`execute_dispatchable_retries()`は`run_once()`内でちょうど1回だけ呼び出され、その戻り値
（`execution_results`）を保持したまま、Queue更新・Cleanup・History記録の各Decider/Executor
へ配布する。これにより、v5.2.0で発見された「同一run_idに対する`retry()`の多重実行リスク」
（`RetryManager`の上位メソッド群を素朴に並べて呼ぶと最大4回実行されうる問題）を構造的に
解消した。`retry_manager.py`は本Releaseでも無改修のまま維持されている。

### `RetryRuntimeCycleResult`（新規）

`run_once()`は`None`ではなく`RetryRuntimeCycleResult`（frozen dataclass）を返す。
`trigger_result` / `scheduler_events` / `execution_results` / `removal_results` /
`cleanup_results` / `terminal_cleanup_results` / `history_results`の7フィールドを保持し、
1サイクルで何が起きたかを外部から確認できる。

### dry_runを追加しなかった理由

`RetryExecutor.execute()`は`dry_run`の値に関わらず常に`outcome=RetryOutcome.RETRIED`を
返すため、`dry_run`を`execute_dispatchable_retries()`へそのまま渡しても、後続の
Queue除去（`queue.remove()`）・History記録（`history.record()`）という実際の副作用は
防げない。本Releaseでは安全なdry_runにならないと判断し、`run_once()`に`dry_run`引数を
追加しなかった（Known Issueとして`docs/design/retry_runtime_run_once_foundation.md`
4章に記録）。

### 本Releaseの対象外（Non-Goal）

`loop()` / `daemon()`の実装、`run_once()`への`dry_run`引数の追加、`run_once()`を呼び出す
`scripts/`エントリーポイントの追加、`RetryManager`への統合API追加、`SchedulerEngine`への
Retry専用API追加はいずれも**本Releaseの対象外**。既存11パッケージ
（`workflow_monitor` / `retry_queue` / `retry_history` / `retry_enqueue_trigger` /
`retry_engine` / `workflow_engine` / `ai` / `execution_history` / `scheduler` /
`retry_scheduler_source` / `retry_scheduler_decision`）はいずれも無改修（ゼロ改修）。

詳細は`docs/design/retry_runtime_run_once_foundation.md`
（Project Charter / Architecture Design・Architecture Review Final含む）を参照。

---

## Retry Runtime Script Entry Point Foundation層（`scripts/run_retry_runtime.py`、v5.4.0 追加）

v5.3.0で実装した`RetryRuntimeOrchestrator.run_once()`を、初めてCLIから呼び出せる
Entry Point`scripts/run_retry_runtime.py`を新設した。

```
scripts/run_retry_runtime.py
   │
   ├─ 1. root = RetryCompositionRoot.from_env()
   ├─ 2. orchestrator = RetryRuntimeOrchestrator.from_composition_root(root)
   ├─ 3. result = orchestrator.run_once()
   └─ 4. print(format_summary(result))   ← 表示ロジックのみ。Business Logicは持たない
```

### scripts層の責務・CLI引数の設計

既存script群（`run_workflow_engine.py`等）と同じく、Business Logicを持たない薄い
Entry Pointとした。CLI引数は一切持たない。`run_once()`自体に分岐点（dry_run等）が
存在しないため、渡すべき引数がないことに加え、特に`--dry-run`は`run_once()`側が
dry_run未対応（v5.3.0 Known Issue）のため、CLIにだけ追加すると「指定したのに
実際にQueue除去・History記録が起きた」という見せかけの安全機能になり、
Development Charter 3章が警戒する誤動作を招くため見送った。

### Exit Code Policy

* 正常終了：exit code `0`（Python標準の暗黙の0）
* 例外発生時：Python標準の非0（fail-fastでそのまま伝播させる。`run_once()`自体の
  Design Policyと対称的な方針）
* 独自のExit Code体系（成功/一部失敗/異常等の多段階区分）は導入しない

### Gate（`RETRY_ENGINE_ENABLED`等）の状態を判定しない設計

`run_workflow_engine.py`は`isinstance(manager, NullWorkflowEngineManager)`を明示的に
チェックする方式だが、本scriptは`NullRetryManager.execute_dispatchable_retries()`が
常に空リストを安全に返す設計であることを踏まえ、Null判定（`isinstance()`）を
一切行わない。Gateが閉じている場合、表示される件数はすべて0件になるだけで、
エラーにも例外にもならない（Null Object Patternの意図を保つ設計）。

### `format_summary()`によるSummary Formatter Design Note

表示ロジックを`format_summary(result: RetryRuntimeCycleResult) -> str`という
独立関数へ局所化した。今回はFormatterクラスの実装は行わない（消費者が本script
1つの段階でクラス化するのは先回りの抽象化）が、引数・戻り値を最小限に絞ることで、
将来JSON出力等の複数形式が必要になった場合に本関数のロジックをそのまま
クラスへ抽出できる構造を維持している。

### 本Releaseの対象外（Non-Goal）

`--loop` / `--daemon`、安全なdry_run再設計、独自Exit Code体系、Summary Formatter
クラス化はいずれも本Releaseの対象外（将来Release候補）。`RetryCompositionRoot` /
`RetryRuntimeOrchestrator`および既存12パッケージ（`workflow_monitor` 〜
`retry_composition`）はいずれも無改修（ゼロ改修）。

詳細は`docs/design/retry_runtime_script_entry_point_foundation.md`
（Project Charter / Architecture Design・Architecture Review Final含む）を参照。

---

## Retry Runtime Loop Foundation層（`src/retry_runtime_loop/`、v5.5.0 追加）

`RetryRuntimeOrchestrator.run_once()`（v5.3.0）を繰り返し呼び出すだけの薄いLoop
Wrapper`RetryRuntimeLoop`を新設した。本Releaseは**未配線のFoundation限定**であり、
`scripts/run_retry_runtime.py`・`RetryRuntimeOrchestrator`・`RetryCompositionRoot`
のいずれからも呼び出されない（消費者不在の先行実装）。

```
RetryRuntimeLoop(run_once_fn, sleep_fn, should_continue_fn, interval_seconds)
   │
   └─ run()
        └─ while should_continue_fn():
               run_once_fn()
               sleep_fn(interval_seconds)
```

### Option A（Loop Foundation）と Option B（Safe Dry Run）の再評価

ユーザーから当初「Retry Runtime Loop Foundation」が第一候補として提示され、
初回Architecture Reviewでは「配線・運用まで見据えたLoop」として評価し、
dry_run未対応のまま導入すると安全上のリスクが増幅されることを理由に、
代替テーマ（Safe Dry Run Foundation）を提案した。

再レビューの結果、Loop自体がBusiness Logicを一切持たず、かつ`scripts/`への
配線を伴わない**未配線のFoundation**に限定すれば、v3.1.0・v3.3.0・v3.5.0・
v5.1.0・v5.2.0で繰り返してきた「消費者不在の先行実装」パターンと同型であり、
実運用リスクを増やさずにRuntime Architectureを1歩前進させられると判断した
（Option A'）。これにより初回レビューの結論を修正し、本Releaseとして採用した。
詳細な比較は`docs/design/retry_runtime_loop_foundation.md` 3章を参照。

### `RetryRuntimeLoop`の設計

* `run_once_fn` / `sleep_fn` / `should_continue_fn` / `interval_seconds`を
  Constructor Injectionで保持するだけのStatelessなWrapper
* `RetryManager` / `RetryQueueManager` / `RetryHistoryManager` / `RetryPolicy` /
  `RetryRuntimeOrchestrator` / `RetryCompositionRoot`のいずれもimportしない
* `run_once_fn`の戻り値（実運用では`RetryRuntimeCycleResult`が渡される想定だが、
  本クラスはその型を一切知らない）は破棄する。`run()`の戻り値は`None`
* 例外はtry/exceptで握りつぶさず、そのまま`run()`から呼び出し元へ伝播させる
  （fail-fast。`RetryRuntimeOrchestrator.run_once()`と対称的な方針）。
  `run_once_fn`が例外を送出した場合、直後の`sleep_fn`は呼ばれない
* `interval_seconds`のバリデーションは行わない（DIのみで完結し境界に該当しない
  ため、呼び出し元を信頼する）

### 未配線である理由

`scripts/run_retry_runtime.py`・`RetryRuntimeOrchestrator`・
`RetryCompositionRoot`のいずれからも`RetryRuntimeLoop`を参照しない。
`run_once()`自体がdry_run未対応というKnown Issue（v5.3.0・v5.4.0から継続）を
抱えたままLoopを配線すると、この未解決の安全上のギャップを「無人で繰り返す」
形に増幅させてしまうため、本Releaseでは意図的に未配線のまま留めた。配線判断
（`--loop`のCLI化）は、dry_run安全性の状況を踏まえて次Release以降に改めて
評価する。

### 本Releaseの対象外（Non-Goal）

CLI配線（`--loop` / `argparse`）、`RetryRuntimeOrchestrator`へのLoop責務追加、
`RetryCompositionRoot`へのExecution/Loop責務追加、`RetryManager`への変更、
`dry_run`対応、daemon化・signal handling、Exit Code再設計、
`RetryRuntimeCycleResult`の解釈はいずれも**本Releaseの対象外**。既存13パッケージ
（`workflow_monitor` 〜 `retry_runtime_orchestrator`）・`scripts/run_retry_runtime.py`
はいずれも無改修（ゼロ改修）。

詳細は`docs/design/retry_runtime_loop_foundation.md`
（Project Charter / Architecture Design・Architecture Review Final含む）を参照。

---

## Retry Runtime Safe Dry Run Wiring Foundation層（`scripts/run_retry_runtime.py`、v5.7.0 追加）

v5.6.0で完成した`RetryRuntimeOrchestrator.run_once(dry_run=True)`（安全なdry_run）を、CLIから
呼び出せるようにした。変更対象は`scripts/run_retry_runtime.py`の`main()`関数内部のみであり、
既存13パッケージ（`workflow_monitor` 〜 `retry_runtime_orchestrator`）はいずれも無改修。

```
main()
   │
   ├─ argparse（main()内でローカルimport）で --dry-run を解析
   ├─ --dry-run指定時、print("[DRY RUN MODE]")   ← format_summary()は経由しない
   ├─ RetryCompositionRoot.from_env()             ← 無改修
   ├─ RetryRuntimeOrchestrator.from_composition_root(root)  ← 無改修
   ├─ orchestrator.run_once(dry_run=args.dry_run) ← v5.6.0のシグネチャそのまま
   └─ format_summary(result)                      ← 無改修（シグネチャ・実装とも変更なし）
```

### 変更範囲を`main()`内部のみへ最小化した設計判断

Architecture Reviewの過程で、複数の設計選択肢についていずれも変更範囲がより小さい案を採用した
（詳細は`docs/design/retry_runtime_safe_dry_run_wiring_foundation.md` 2.2節）。

- **argparseはmain()内で直接処理**：独立関数`parse_args()`への分離は行わない（YAGNI。`--dry-run`
  1フラグのみの現時点では分離の恩恵がなく、`--loop` / `--config` / `--interval`等が増えた時点で
  再検討する）。`import argparse`もモジュールトップレベルではなく`main()`内のローカルimportとし、
  CLI関心事を`main()`内に完全に閉じ込めた
- **`format_summary()`は無改修**：dry_run表示（`[DRY RUN MODE]`）は`main()`側の`print()`で
  完結させ、`format_summary(result, dry_run)`のようなシグネチャ変更は行わない。「`RetryRuntimeCycleResult`
  → Summary文字列」という既存の単一責務を維持する
- **`RetryRuntimeCycleResult`は無改修**：CLI都合の情報（dry_runフラグ）をDomain側のResultクラスへ
  持ち込む設計は採用しない
- **CLI SummaryへKnown Issueの説明文は表示しない**：`--dry-run`指定時もEnqueueは通常どおり実行
  される制約（後述`[KI-23]`）は、CLI出力ではなくdocs（CHANGELOG.md / architecture.md / ROADMAP.md）
  で管理する。CLI Summaryの責務は「実行結果の表示のみ」に限定する

### Known Issue

- **`[KI-23]`（新規）**：`--dry-run`指定時も、`RetryEnqueueTrigger`はdry_run非対応のため、
  WorkflowMonitor上のFAILED/TIMEOUTはRetry Queueへ通常どおりenqueueされる。CLIで一般公開される
  ことに伴い正式なKnown Issueとして記録した。対応予定Release「Retry Enqueue Trigger Dry Run
  Foundation」（`docs/ROADMAP.md`）
- **`[KI-24]`（新規）**：本Releaseの`scripts/run_retry_runtime.py`変更により、v5.4.0・v5.5.0・
  v5.6.0の一部Architecture Guard（「無改修」を前提としたテスト）がFAILする。`[KI-3]`〜`[KI-22]`と
  同型の意図的な既知差分であり対応不要

### Technical Debt（本Release対象外、記録のみ）

`NullRetryEnqueueTrigger.enqueue_pending_failures()`が、v5.0.0で`RetryEnqueueTrigger`側に追加
された`max_attempts`引数を持たないシグネチャ不整合。`RetryCompositionRoot`が`RetryEnqueueTrigger`
を常に実体で構築するため（Feature Gateを持たない設計）現状は到達不能で実害はないが、将来Null経路
が使われる設計変更が入る場合に修正を検討する（`docs/design/retry_runtime_safe_dry_run_wiring_foundation.md`
6章）。

詳細は`docs/design/retry_runtime_safe_dry_run_wiring_foundation.md`
（Architecture Design・Architecture Review・ユーザーとの4点の設計判断を含む）を参照。

---

## Retry Runtime Lock Foundation層（`src/retry_runtime_lock/`、v6.0.0 追加）

同一Retry Runtimeプロセスの多重起動を防止するための、ファイル存在ベースの排他制御のみを行う
新規独立パッケージ`src/retry_runtime_lock/`（`RetryRuntimeLock` / `RetryRuntimeLockError`）を
追加した。`scripts/run_retry_runtime.py`の変更のみで配線が完結し、既存14パッケージ
（`workflow_monitor` 〜 `retry_runtime_loop`）はいずれも無改修。

Daemon化そのもの（実際のバックグラウンド常駐・Windows Service化）ではなく、いかなるDaemon化方式
であっても前提となる「同一Runtimeが多重起動していないことの保証」のみを対象とした最小Foundation。

```
CLI → argparse（既存、無変更）
    → RetryRuntimeLock(lock_path).acquire()
         ├─ [成功] → RetryCompositionRoot.from_env()          ← 無改修
         │              → RetryRuntimeOrchestrator.from_composition_root()  ← 無改修
         │              → （単発）run_cycle() 1回
         │                （--loop）RetryRuntimeLoop(...).run()            ← 無改修
         │              → 正常終了 or KeyboardInterrupt
         │              → lock.release()（with文により保証）
         │
         └─ [失敗：既に別プロセスが実行中] → RetryRuntimeLockError
                → エラーメッセージ表示（lock fileパス・対処方法） → exit code 1
                （CompositionRoot等は一切構築されない）
```

### 責務を「取得・解放のみ」に限定した設計判断

- **`RetryRuntimeLock`はRetryドメイン・実行順序・ループ・スケジューリング・Daemon化のいずれも
  関知しない**。標準ライブラリ（`os` / `pathlib`）のみで実装し、他のretry_*パッケージへは
  一切依存しない
- **`RetryCompositionRoot`へロックを組み込まない**：Composition Rootの責務（組み立てのみ）を
  超えないよう、ロックの構築・保持は`scripts/run_retry_runtime.py`側で行う
- **stale lockのPID生存確認・自動復旧は行わない**：ロックファイルの存在有無のみで排他制御を
  行い、Windows/POSIXでの生存確認実装の複雑化を避けた。プロセス強制終了時の残存は既知のTrade-off
  として受け入れ、手動削除を前提とする
- **ロックパスの環境変数化・CLIフラグによる任意化は行わない**：多重起動防止は安全性の基本であり
  常に有効とする

### os.write()失敗時のリソース解放（Code Review対応）

`acquire()`は`os.open(O_CREAT | O_EXCL)`でロックファイルを作成した後、自プロセスのPIDを
書き込む。Code Reviewで、この書き込みが失敗した場合に作成済みのロックファイルだけが残存し
恒久的なstale lockになる経路が発見されたため、`os.write()`を`try/except`で囲み、失敗時は
`os.close(fd)`→ロックファイル削除→例外再送出という順序で確実に後片付けするよう修正した。

### Known Risks（設計時点から継続）

- プロセスが強制終了（`taskkill /F`・電源断等）した場合、ロックファイルが残存し次回起動が
  誤ってブロックされる可能性がある（手動削除が必要）
- ロックはローカルファイルシステム上の存在有無のみで判定するため、単一ホスト内での多重起動
  防止のみを保証範囲とする

### Future Extension

Stale Lock Recovery Foundation・Graceful Shutdown Foundation・Windows Service Foundation /
実Daemon化・他Agent系scriptへのLock機構の横展開・Structured Loop Logging Foundation
（詳細は`docs/ROADMAP.md`）。

詳細は`docs/design/retry_runtime_lock_foundation.md`
（Architecture Design・Architecture Review・Code Reviewの経緯を含む）を参照。

---

## Graceful Shutdown Foundation層（`src/retry_runtime_shutdown/`、v6.1.0 追加）

`--loop`実行中のRetry Runtimeに対するGraceful Shutdown（実行中サイクルは完了させたうえで、次のサイクルを
開始せず終了する）のみを行う新規独立パッケージ`src/retry_runtime_shutdown/`（`RetryRuntimeShutdown`）を
追加した。`scripts/run_retry_runtime.py`の変更のみで配線が完結し、既存15パッケージ
（`workflow_monitor` 〜 `retry_runtime_lock`）はいずれも無改修。

```
CLI → argparse（既存、無変更）
    → RetryRuntimeLock(lock_path).acquire()（v6.0.0、既存）
         → [--loop の場合のみ] RetryRuntimeShutdown().install()
              → RetryCompositionRoot.from_env()                    ← 無改修
              → RetryRuntimeOrchestrator.from_composition_root()   ← 無改修
              → RetryRuntimeLoop(                                  ← 無改修
                    run_once_fn=run_cycle,
                    sleep_fn=shutdown.interruptible_sleep,   ← 差し替え
                    should_continue_fn=shutdown.should_continue, ← 差し替え
                    interval_seconds=interval_seconds,
                 ).run()
              → シグナル受信 → 実行中サイクルは完了 → 待機を早期終了
              → should_continue_fn() が False → loop.run() が正常return
              → shutdown.requested を見て終了メッセージ表示
         → lock.release()（with文により保証、v6.0.0のまま）
```

### RetryRuntimeLoopへ一切手を加えない設計判断

`RetryRuntimeLoop`（v5.5.0）は元々`should_continue_fn` / `sleep_fn`という2つのDIシームを持っていた
（`--loop`配線時点では`lambda: True` / `time.sleep`が渡されていた）。本Releaseはこの2つのシームへ
`RetryRuntimeShutdown`のメソッドをそのまま渡すだけで、**`RetryRuntimeLoop`自体には一切手を加えていない**。
`RetryRuntimeLoop`は`RetryRuntimeShutdown`の存在を一切知らず、`RetryRuntimeShutdown`も`RetryRuntimeLoop`の
存在を一切知らない。両者はDI（Constructor Injectionされた関数参照）のみで接続される。

### サイクル途中で打ち切らない設計

シグナルハンドラ（`_handle()`）はフラグを立てるのみで、例外を送出しない。これにより、Pythonの
デフォルト動作（SIGINT受信時に非同期で`KeyboardInterrupt`を送出し、`run_once_fn()`実行中を
中断しうる）を意図的に上書きし、実行中のサイクルを最後まで完了させてから停止する、という
「Graceful」な停止を実現している。

### 待機の早期終了

`sleep_fn`を`time.sleep`から`RetryRuntimeShutdown.interruptible_sleep`（ポーリング間隔0.5秒単位で
停止要求を確認する）へ差し替えたことで、シグナル受信からプロセス終了までの間、旧来の
`interval_seconds`（デフォルト60秒、長時間運用ではさらに長い場合もある）を待たされることがなくなった。
`should_continue_fn`のみを差し替えて`sleep_fn`を`time.sleep`のままにする代替案も検討したが、
応答性の悪さ（最大`interval_seconds`の待ち時間）が「Graceful」の趣旨に反するため不採用とした
（設計書§7 Alternatives Considered 2番）。

### Windowsでの強制終了は対象外（Known Risk）

Windowsの`taskkill /F`・タスクマネージャーの「タスクの終了」は`TerminateProcess`を直接呼び出すため、
いかなるプロセスもこれを検知・介入することは原理的にできない。本Foundationが確実に対応できるのは、
フォアグラウンドのCtrl+C（SIGINT）・Ctrl+Break（SIGBREAK、Windows実機での動作を実測確認済み）、
および同一プロセス内から送出されたシグナルに限られる。SIGTERMハンドラも登録するが、Windowsで
他プロセスから送出された場合は`TerminateProcess`相当となりハンドラは呼ばれない（POSIX環境への
移植性のために登録している）。

### 既存テストファイルへの影響（Known Issue）

`--loop`実行時の`sleep_fn`が`time.sleep`から`RetryRuntimeShutdown.interruptible_sleep`へ変わったため、
`scripts/run_retry_runtime.py`の`time`属性を直接monkeypatchしていた既存テスト
（`tests/test_e2e_v5_9_0_*.py` / `tests/test_e2e_v6_0_0_*.py`）の一部が実行不能になった
（`docs/CHANGELOG.md` `[KI-29]`）。本Releaseの新規テストでは、`RetryRuntimeShutdown`クラス自体を
Fakeへ差し替える方式に切り替えることでこの問題を回避している。

### Future Extension

Stale Lock Recovery Foundation・Windows Service Foundation / 実Daemon化・単発実行時のシグナル処理・
二重シグナルによる強制終了エスケープハッチ（詳細は`docs/ROADMAP.md`）。

詳細は`docs/design/retry_runtime_graceful_shutdown_foundation.md`
（Architecture Design・Architecture Review反映事項3件の経緯を含む）を参照。
