# CHANGELOG

このファイルはプロジェクトの変更履歴を記録します。
フォーマットは [Keep a Changelog](https://keepachangelog.com/ja/) に準拠。

---

## Known Issues（現在判明している既知の問題）

> このセクションは「いつ・何がリリースされたか」というリリース履歴とは別に、
> **現時点（2026-07-01, v2.1.0 Documentation Foundation作業時点）で判明している未解決の問題**をまとめたものです。
> 各バージョンの`### Tested`欄はリリース当時の記録として維持し、現在の状況はここに集約します。

### [KI-1] v1.10.0 Analytics Foundation のE2Eテストが現環境で失敗する

- **発見日**：2026-07-01（v2.1.0 ドキュメント整備作業中）
- **対象**：`tests/test_e2e_v1_10_0_analytics_foundation.py`
- **症状**：`logs/analytics/` サブディレクトリが未作成のまま書き込もうとして `FileNotFoundError` が発生する（`src/analytics/`側の問題と推測される）
- **v1.10.0実装当時の状況**：`docs/design/analytics_foundation.md` の「Definition of Done」は全項目未チェック（`[ ]`）のままであり、実装当時に本当にテストがPASSしていたかを裏付ける記録は見つからなかった。実装当時の成否は不明。
- **対応状況**：未修正。`src/`はv2.1.0（本ドキュメント整備リリース）の変更対象外のため、コード修正は行っていない
- **今後の対応**：別リリースで`src/analytics/analytics_manager.py`側のディレクトリ作成漏れを調査・修正する想定
- **2026-07-02追記（v3.1.0 Retry Queue Foundation 回帰確認時に再確認）**：より正確な原因を特定した。テスト内で保存先ファイル名が`"20260630_analytics.jsonl"`のように**日付をハードコード**して期待値としているが、実際に保存されるファイルは`datetime.now()`ベースの当日日付（例：`20260702_analytics.jsonl`）になるため、システム日付が`2026-06-30`を過ぎた時点でファイル名が一致せず`FileNotFoundError`になる（`logs/analytics/`サブディレクトリ自体は作成されている可能性がある）。Release 3.1（Retry Queue Foundation）はこの問題と無関係であり、本Releaseでは対応しない（Out of Scope）。対応は別リリースで検討する

### [KI-2] v2.6.0 Scheduler Agent Foundation のCHANGELOG記載漏れ（解消済み）

- **発見日**：2026-07-02（v2.7.0 Workflow Engine Foundation ドキュメント整備作業中）
- **症状**：commit `0d28d30`（v2.6.0 Scheduler Agent Foundation）にCHANGELOG.md / ROADMAP.mdへの記載が伴っていなかった
- **対応状況**：解消済み。本ドキュメント整備作業（2026-07-02）で、実装済みコード（`src/scheduler/`配下・`tests/test_e2e_v2_6_0_scheduler_agent_foundation.py`）の内容を確認し、下記「[v2.6.0]」として遡及的に追記した
- **今後の対応**：不要（本エントリで解消済み）

### [KI-3] v3.1.0テストの「retry_engine無改修」チェックがv3.2.0以降でFAILする（設計上の既知差分）

- **発見日**：2026-07-02（v3.2.0 Retry Queue Integration 実装時）
- **対象**：`tests/test_e2e_v3_1_0_retry_queue_foundation.py`のテスト24（`src/retry_engine/retry_manager.py`に変更がないことを確認する`git diff`チェック）
- **症状**：v3.2.0で`retry_manager.py`を意図的に変更したため、本チェック1件がFAILする（151/152 PASS）
- **原因**：v3.1.0のテストは「v3.1.0時点でretry_engineが無改修だった」という当時の事実をArchitecture Guardとして固定していたものであり、将来のRelease全体にわたって成立し続けることを意図した制約ではなかった
- **対応状況**：対応しない。v3.2.0のProject Charter / Architecture Design / Architecture Reviewで`retry_manager.py`の変更は正式に承認済みである。本質的な制約である「`src/retry_queue/`配下の無改修」は、v3.1.0テストの残り151件（`retry_queue`パッケージ自体・その公開APIの挙動）と、v3.2.0の新規テスト（`test_e2e_v3_2_0_retry_queue_integration.py`のテスト14）の両方で別途確認済み。ユーザー確認の結果、v3.1.0テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした
- **今後の対応**：不要（本エントリで説明を確定）。将来Releaseで`retry_engine`側に変更が入るたびに同様のFAILが起こりうるが、その都度Charter/Design側で「どのファイルが変更対象として承認されているか」を確認すればよく、個別のFAILは許容する

### [KI-4] v3.4.0でのScheduler Wiringにより、v2.7.0〜v3.3.0の一部Architecture GuardがFAILする（設計上の既知差分）

- **発見日**：2026-07-03（v3.4.0 Retry Scheduler Wiring Test工程実施時）
- **対象**：
  - `tests/test_e2e_v2_7_0_workflow_engine_foundation.py`〜`tests/test_e2e_v3_2_0_retry_queue_integration.py`（計6ファイル）：それぞれ1件ずつ、`src/scheduler/scheduler_engine.py`に変更がないことを確認する`git diff`チェック
  - `tests/test_e2e_v3_3_0_retry_scheduler_integration.py`：3件（`src/scheduler/scheduler_engine.py` / `src/scheduler/__init__.py`に変更がないことを確認する`git diff`チェック2件、および`retry_scheduler_source`を参照する既存ファイルが存在しないことを確認するチェック1件）
- **症状**：上記7ファイル・計9件のテストがFAILする（他はすべてPASS。v2.7.0は162/163、v2.8.0は181/182、v2.9.0は102/103、v3.0.0は129/130、v3.1.0は151/152、v3.2.0は101/102、v3.3.0は69/72）
- **原因**：v3.4.0（Retry Scheduler Wiring）で`SchedulerEngine`が`RetrySchedulerSource` / `NullRetrySchedulerSource`をConstructor Injectionで保持できるようにし、`count_pending_retries()` / `list_pending_retries()`を追加した（`docs/design/retry_scheduler_wiring.md`）。これに伴い`src/scheduler/scheduler_engine.py`・`src/scheduler/__init__.py`（docstringのみ）が変更され、`retry_scheduler_source`が初めて`scheduler`パッケージから参照されるようになった。v2.7.0〜v3.3.0の各テストは「その時点でschedulerが無改修だった／retry_scheduler_sourceが誰からも参照されていなかった」という当時の事実をArchitecture Guardとして固定していたものであり、`[KI-3]`と同種の既知差分である
- **対応状況**：対応しない。v3.4.0のProject Charter / Architecture Design / Architecture Reviewで`scheduler_engine.py`の変更（Constructor Injection追加・読み取り専用2メソッド追加）は正式に承認済みである。本質的な制約（`evaluate()` / `run_due()`の判定ロジック無変更、`retry_scheduler_source` / `retry_queue` / `retry_engine`のゼロ改修、dequeue/remove/Retry Engine起動が混入しないこと）は、v3.4.0の新規テスト（`tests/test_e2e_v3_4_0_retry_scheduler_wiring.py`、94件）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした（`[KI-3]`と同じ扱い）
- **今後の対応**：不要（本エントリで説明を確定）。なお、これらの`git diff`チェックはコミット時点の差分を見る性質上、本Releaseをcommitすれば大部分は自然に解消する（`[KI-3]`が`retry_manager.py`のcommit後に非再現となったのと同じ挙動）。将来Releaseで`scheduler`側に変更が入るたびに同様のFAILが起こりうるが、その都度Charter/Design側で「どのファイルが変更対象として承認されているか」を確認すればよく、個別のFAILは許容する
- **2026-07-03追記（v3.5.0 Retry Scheduler Decision Test工程実施時に再確認）**：`tests/test_e2e_v3_3_0_retry_scheduler_integration.py`のテスト17（「`retry_scheduler_source`を参照する既存ファイルが存在しない」）について、本チェックの性質を訂正する。テスト18（`git diff --quiet`ベース）は**コミット時点の差分**を見る性質上、v3.4.0のcommit後に自然解消したが、テスト17は`git diff`を使わず`src/`配下の全ファイルを走査して「`retry_scheduler_source`という文字列を含むファイルが1つも存在しないこと」を確認する**恒久的な静的検査**であり、v3.4.0で`scheduler_engine.py` / `scheduler/__init__.py`が`retry_scheduler_source`を参照するようになった時点で、コミットの有無に関わらず**恒久的に成立しなくなっていた**（v3.4.0時点でのFAILの記述時に「大部分は自然に解消する」とした「大部分」からテスト17は除外される）。v3.5.0（Retry Scheduler Decision）で新規追加した`src/retry_scheduler_decision/`が`retry_scheduler_source`の2人目の消費者として加わったことで、本チェックの実際値（FAILしたファイル一覧）に`retry_scheduler_decision/__init__.py` / `retry_scheduler_decision.py`が追加されたが、これは新規の不具合ではなく、v3.4.0時点で既に恒久化していた本項目の自然な延長である。`RetrySchedulerDecision`自体が`scheduler`等の既存ファイルから参照されない「消費者不在の先行実装」であることは、v3.5.0の新規テスト（`tests/test_e2e_v3_5_0_retry_scheduler_decision.py`のテスト18）で別途確認済み。新規Known Issue（`[KI-5]`）は追加せず、本エントリの説明補強で対応する
- **2026-07-03追記（v3.6.0 Retry Scheduler Decision Wiring Test工程実施時に再確認）**：v3.6.0で`src/scheduler/scheduler_engine.py`（および`__init__.py`）を再度変更したことに伴い、本項目（`[KI-4]`）が対象とする「`git diff --quiet`ベースのArchitecture Guard」が、これまでの対象（`v2.7.0`〜`v3.3.0`の計7ファイル・9件）に加えて**一時的に**FAILする範囲が広がった。Test工程実施時点（v3.6.0未commit）では、`v2.7.0`・`v2.8.0`・`v2.9.0`・`v3.0.0`・`v3.1.0`・`v3.2.0`・`v3.3.0`（`scheduler_engine.py` / `__init__.py`の2件）の計7ファイル・8件が新たにFAILしたが、`git stash`でv3.6.0の変更を一時退避したベースラインとの比較により、原因が本項目と同一（コミット時点の差分を見る`git diff --quiet`が、未commitの本Release変更を検知しているだけ）であることを確認済み。本Releaseをcommitすれば、これらは`[KI-3]`・`[KI-4]`の前例（`retry_manager.py`のcommit後・`scheduler_engine.py`のv3.4.0時commit後にそれぞれ非再現となった挙動）と同様に自然解消する見込みである
- **2026-07-03追記（v3.6.0 Test工程実施時、恒久差分の新規発生）**：上記の一時差分とは別に、`tests/test_e2e_v3_5_0_retry_scheduler_decision.py`のテスト18（「`retry_scheduler_decision`を参照する既存ファイルが存在しない」）が、v3.6.0で`scheduler_engine.py`が`retry_scheduler_decision`を正式にimportするようになったことにより、コミットの有無に関わらず**恒久的に**成立しなくなった。これは`v3.3.0`のテスト17が`v3.4.0`で恒久FAIL化した現象（本項目2026-07-03追記）と完全に同型であり、`RetrySchedulerDecision`が本Releaseで初めて実際の消費者（`SchedulerEngine`）を持ったことの自然な帰結である。本現象についても新規Known Issue（`[KI-6]`）は追加せず、本エントリの説明補強で対応する

### [KI-5] 既存のCLI表示・returncode系テストの一部が現環境でFAILする（v3.6.0以前から存在、本Releaseとは無関係）

- **発見日**：2026-07-03（v3.6.0 Retry Scheduler Decision Wiring Test工程実施時。既存回帰の全件実行で偶発的に発見した）
- **対象**：`tests/test_e2e_v2_2_0_news_agent_foundation.py`（2件）・`tests/test_e2e_v2_3_0_workflow_trigger_agent_foundation.py`（9件）・`tests/test_e2e_v2_4_0_publish_trigger_agent_foundation.py`（8件）・`tests/test_e2e_v2_5_0_review_trigger_agent_foundation.py`（8件）・`tests/test_e2e_v2_7_0_workflow_engine_foundation.py`（9件）・`tests/test_e2e_v2_8_0_execution_history_foundation.py`（4件）・`tests/test_e2e_v2_9_0_workflow_monitor_foundation.py`（6件）
- **症状**：`--dry-run`等でCLIスクリプトをsubprocess実行するテストにおいて、`returncode`が0にならない、または期待する案内メッセージ（「DRY RUN」表示・「〜が無効の案内」等）が標準出力に含まれない
- **対応状況**：未修正。`git stash`でv3.6.0の変更（`src/scheduler/`配下2ファイルのみ）を一時退避したベースラインでも同数・同項目のFAILが再現することを確認済みであり、v3.6.0（`scheduler` / `retry_scheduler_decision`）とは無関係と判断した。対象パッケージ（`news_agent` / `workflow_trigger_agent` / `publish_trigger_agent` / `review_trigger_agent` / `workflow_engine`のCLIエントリスクリプト）はv3.6.0の変更対象外であり、本Releaseでの修正は行わない
- **今後の対応**：別リリースで該当CLIスクリプト側（dry-run時のreturncode・標準出力メッセージ）を調査・修正する想定。原因はAPIキー未設定等の実行環境要因の可能性があるが、本Release時点では未特定

### [KI-6] v3.7.0でのRetry Scheduler Event Integrationにより、v3.6.0の「retry_decision有無で結果完全一致」テスト2件がFAILする（設計上の意図的な差分）

- **発見日**：2026-07-03（v3.7.0 Retry Scheduler Event Integration Test工程実施時）
- **対象**：`tests/test_e2e_v3_6_0_retry_scheduler_decision_wiring.py`のテスト16（「retry_decision有無でevaluate()の結果が完全一致」）・テスト17（「retry_decision有無でrun_due()の結果が完全一致」）
- **症状**：上記2件がFAILする（102/104 PASS）
- **原因**：v3.6.0時点では`evaluate()` / `run_due()`が`retry_decision`の有無に関わらず常に同じ結果を返すことがArchitecture Guardとして固定されていた。v3.7.0（Retry Scheduler Event Integration）は、ユーザー指示「Retry候補を`SchedulerEvent`に反映する」を実現するため、`retry_decision`が注入されている場合に限り、Retry候補由来の`SchedulerEvent`を意図的に追加するようになった（Additive方式。`docs/design/retry_scheduler_event_integration.md` 13章 Design Decision #1）。したがって「有無で完全一致」という前提はv3.7.0以降成立しなくなる
- **対応状況**：対応しない。v3.7.0のProject Charter / Architecture Design / Architecture Reviewで`evaluate()` / `run_due()`への統合（`retry_decision`が`None`でない場合にのみ出力が変わること）は正式に承認済みである。本質的な後方互換性の制約（`retry_decision=None`の場合に限り、本Release前とまったく同じ結果を返すこと）は、v3.7.0の新規テスト（`tests/test_e2e_v3_7_0_retry_scheduler_event_integration.py`のテスト1〜4）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした（`[KI-3]`・`[KI-4]`と同じ扱い）
- **今後の対応**：不要（本エントリで説明を確定）。将来Release（自動Retry実行等）で`evaluate()` / `run_due()`にさらに変更が入る場合も、その都度Charter/Design側で承認済みの変更範囲を確認すればよく、個別のFAILは許容する

### [KI-7] v3.8.0でのRetry Engine Event Consumptionにより、v3.0.0〜v3.7.0の一部Architecture GuardがFAILする（設計上の意図的な差分）

- **発見日**：2026-07-03（v3.8.0 Retry Engine Event Consumption Test工程実施時）
- **対象と症状**：
  - `tests/test_e2e_v3_0_0_retry_engine_foundation.py`（134/136 PASS）：テスト21「`retry_event_consumer.py` / `retry_manager.py`が`scheduler`をimportしない」が2件FAIL
  - `tests/test_e2e_v3_1_0_retry_queue_foundation.py`（151/152 PASS）：テスト24「`src/retry_engine/retry_manager.py`に変更がない（`git diff`）」が1件FAIL
  - `tests/test_e2e_v3_2_0_retry_queue_integration.py`（99/102 PASS）：テスト14「`src/retry_engine/__init__.py`に変更がない（`git diff`）」・テスト16「`retry_engine.__all__`が本Release前と同一」・テスト17「`from_config()`の第5引数が`retry_queue_manager`」の3件FAIL
  - `tests/test_e2e_v3_3_0_retry_scheduler_integration.py`（69/72 PASS）：テスト18「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」2件FAIL（テスト17は`[KI-4]`の既存差分で本Releaseとは無関係）
  - `tests/test_e2e_v3_4_0_retry_scheduler_wiring.py`（92/94 PASS）：テスト20「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」2件FAIL
  - `tests/test_e2e_v3_5_0_retry_scheduler_decision.py`（69/72 PASS）：テスト19「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」2件FAIL（テスト18は`[KI-4]`の既存差分で本Releaseとは無関係）
  - `tests/test_e2e_v3_6_0_retry_scheduler_decision_wiring.py`（100/104 PASS）：テスト24「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」2件FAIL（テスト16・17は`[KI-6]`の既存差分で本Releaseとは無関係）
  - `tests/test_e2e_v3_7_0_retry_scheduler_event_integration.py`（72/74 PASS）：テスト21「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」2件FAIL
- **原因**：v3.8.0（Retry Engine Event Consumption）で`src/retry_engine/`に`retry_event_consumer.py`を新規追加し、`retry_manager.py`（`event_consumer`引数・`recognize_retry_events()`追加）・`__init__.py`（新規シンボルexport）を変更した（`docs/design/retry_engine_event_consumption.md`）。これにより`retry_engine`パッケージが初めて`scheduler`パッケージ（`SchedulerEvent`型のみ）に依存するようになった。v3.0.0〜v3.7.0の各テストは「その時点で`retry_engine`が無改修だった／`scheduler`をimportしていなかった」という当時の事実をArchitecture Guardとして固定していたものであり、`[KI-3]`・`[KI-4]`と同種の既知差分である
- **対応状況**：対応しない。v3.8.0のProject Charter / Architecture Design / Architecture Reviewで`retry_event_consumer.py`の新規追加・`retry_manager.py`の変更（`event_consumer`引数・`recognize_retry_events()`追加）・`__init__.py`の`__all__`更新はいずれも正式に承認済みである。本質的な制約（`scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue`のゼロ改修、`dequeue()` / `remove()` / Retry実行に到達しないこと、`retry_engine → scheduler`の依存が`SchedulerEvent`型のみに限定されること、`RetryManager` / `NullRetryManager`の既存4メソッドの後方互換性）は、v3.8.0の新規テスト（`tests/test_e2e_v3_8_0_retry_engine_event_consumption.py`、70件）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした（`[KI-3]`・`[KI-4]`・`[KI-6]`と同じ扱い）
- **今後の対応**：不要（本エントリで説明を確定）。`git diff --quiet`ベースのチェック（v3.1.0テスト24・v3.2.0テスト14・v3.3.0〜v3.7.0の各`git diff`チェック）はコミット時点の差分を見る性質上、本Releaseをcommitすれば自然に解消する（`[KI-3]`・`[KI-4]`と同じ挙動）。一方、v3.0.0テスト21（`scheduler`非import確認）・v3.2.0テスト16（`__all__`不変確認）・テスト17（`from_config()`第5引数確認）は`git diff`を使わない恒久的な静的検査であり、コミットの有無に関わらず本Release以降も成立しなくなる（`[KI-4]`2026-07-03追記のv3.3.0テスト17と同型）。将来Releaseで`retry_engine`側にさらに変更が入るたびに同様のFAILが起こりうるが、その都度Charter/Design側で承認済みの変更範囲を確認すればよく、個別のFAILは許容する

### [KI-8] v3.9.0でのRetry Engine Event Dispatchにより、v3.0.0〜v3.8.0の一部Architecture GuardがFAILする（設計上の意図的な差分）

- **発見日**：2026-07-06（v3.9.0 Retry Engine Event Dispatch Test工程実施時）
- **対象と症状**：
  - `tests/test_e2e_v3_0_0_retry_engine_foundation.py`（140/142 PASS）：テスト21「`retry_event_consumer.py` / `retry_manager.py`が`scheduler`をimportしない」が2件FAIL（`[KI-7]`から継続する既存差分。本Releaseで新たに壊したものではない）
  - `tests/test_e2e_v3_1_0_retry_queue_foundation.py`（151/152 PASS）：テスト24「`src/retry_engine/retry_manager.py`に変更がない（`git diff`）」が1件FAIL
  - `tests/test_e2e_v3_2_0_retry_queue_integration.py`（99/102 PASS）：テスト14「`src/retry_engine/__init__.py`に変更がない（`git diff`）」・テスト16「`retry_engine.__all__`が本Release前と同一」・テスト17「`from_config()`の第5引数が`retry_queue_manager`」の3件FAIL
  - `tests/test_e2e_v3_3_0_retry_scheduler_integration.py`（69/72 PASS）：テスト18「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」2件FAIL（テスト17は`[KI-4]`の既存差分で本Releaseとは無関係）
  - `tests/test_e2e_v3_4_0_retry_scheduler_wiring.py`（92/94 PASS）：テスト20「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」2件FAIL
  - `tests/test_e2e_v3_5_0_retry_scheduler_decision.py`（69/72 PASS）：テスト19「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」2件FAIL（テスト18は`[KI-4]`の既存差分で本Releaseとは無関係）
  - `tests/test_e2e_v3_6_0_retry_scheduler_decision_wiring.py`（100/104 PASS）：テスト24「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」2件FAIL（テスト16・17は`[KI-6]`の既存差分で本Releaseとは無関係）
  - `tests/test_e2e_v3_7_0_retry_scheduler_event_integration.py`（72/74 PASS）：テスト21「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」2件FAIL
  - `tests/test_e2e_v3_8_0_retry_engine_event_consumption.py`（67/70 PASS）：テスト24「`retry_engine.__all__`が既存シンボル＋新規2シンボルの構成になっている」・テスト25「`__init__` / `from_config()`の最終引数が`event_consumer`」の3件FAIL（本Releaseで`event_dispatcher`を新たな最終引数として追加したため、`event_consumer`が最終引数ではなくなった）
- **原因**：v3.9.0（Retry Engine Event Dispatch）で`src/retry_engine/`に`retry_event_dispatcher.py`を新規追加し、`retry_manager.py`（`event_dispatcher`引数・`dispatch_retry_events()`追加）・`__init__.py`（新規シンボルexport）を変更した（`docs/design/retry_engine_event_dispatch.md`）。v3.0.0〜v3.8.0の各テストは「その時点で`retry_engine`が無改修だった／`event_consumer`が最終引数だった」という当時の事実をArchitecture Guardとして固定していたものであり、`[KI-3]`・`[KI-4]`・`[KI-7]`と同種の既知差分である
- **対応状況**：対応しない。v3.9.0のProject Charter / Architecture Design / Architecture Reviewで`retry_event_dispatcher.py`の新規追加・`retry_manager.py`の変更（`event_dispatcher`引数・`dispatch_retry_events()`追加）・`__init__.py`の`__all__`更新はいずれも正式に承認済みである。本質的な制約（`scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_event_consumer.py`のゼロ改修、`dequeue()` / `remove()` / Retry実行に到達しないこと、`retry_event_dispatcher.py`が`scheduler` / `retry_queue`いずれも新規importしないこと、`RetryManager` / `NullRetryManager`の既存メソッドの後方互換性）は、v3.9.0の新規テスト（`tests/test_e2e_v3_9_0_retry_engine_event_dispatch.py`、73件）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした（`[KI-3]`・`[KI-4]`・`[KI-7]`と同じ扱い）
- **今後の対応**：不要（本エントリで説明を確定）。`git diff --quiet`ベースのチェックは本Releaseをcommitすれば自然に解消する。一方、v3.0.0テスト21・v3.2.0テスト16-17・v3.8.0テスト24-25は`git diff`を使わない恒久的な静的検査であり、コミットの有無に関わらず本Release以降も成立しなくなる。将来Release（Retry Execution）で`retry_engine`側にさらに変更が入るたびに同様のFAILが起こりうるが、その都度Charter/Design側で承認済みの変更範囲を確認すればよく、個別のFAILは許容する

### [KI-9] v4.0.0でのRetry Execution Foundationにより、v3.1.0〜v3.9.0の一部Architecture GuardがFAILする（設計上の意図的な差分）

- **発見日**：2026-07-06（v4.0.0 Retry Execution Foundation Test工程実施時）
- **検証方法**：`git stash`で本Release（`retry_manager.py` / `__init__.py`の変更）を一時退避したベースラインと、本Release適用後を比較し、差分の原因が本Releaseの変更であることを構造的に確認した
- **対象と症状（ベースライン → 本Release適用後）**：
  - `tests/test_e2e_v3_0_0_retry_engine_foundation.py`：152/154 PASS → 152/154 PASS（変化なし。テスト21の2件FAILは`[KI-7]`から継続する既存差分で本Releaseとは無関係）
  - `tests/test_e2e_v3_1_0_retry_queue_foundation.py`：152/152 PASS → 151/152 PASS（新規1件FAIL：テスト24「`retry_manager.py`に変更がない（`git diff`）」）
  - `tests/test_e2e_v3_2_0_retry_queue_integration.py`：100/102 PASS → 99/102 PASS（新規1件FAIL：テスト14「`__init__.py`に変更がない（`git diff`）」。テスト16-17は`[KI-7]`/`[KI-8]`から継続する既存差分）
  - `tests/test_e2e_v3_3_0_retry_scheduler_integration.py`：71/72 PASS → 69/72 PASS（新規2件FAIL：テスト18「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」。テスト17は`[KI-4]`の既存差分で無関係）
  - `tests/test_e2e_v3_4_0_retry_scheduler_wiring.py`：94/94 PASS → 92/94 PASS（新規2件FAIL：テスト20「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」）
  - `tests/test_e2e_v3_5_0_retry_scheduler_decision.py`：71/72 PASS → 69/72 PASS（新規2件FAIL：テスト19「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」。テスト18は`[KI-4]`の既存差分で無関係）
  - `tests/test_e2e_v3_6_0_retry_scheduler_decision_wiring.py`：102/104 PASS → 100/104 PASS（新規2件FAIL：テスト24「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」。テスト16-17は`[KI-6]`の既存差分で無関係）
  - `tests/test_e2e_v3_7_0_retry_scheduler_event_integration.py`：74/74 PASS → 72/74 PASS（新規2件FAIL：テスト21「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」）
  - `tests/test_e2e_v3_8_0_retry_engine_event_consumption.py`：67/70 PASS → 67/70 PASS（変化なし。テスト24「`__all__`が既存＋新規2シンボルの構成」・テスト25「最終引数が`event_consumer`」の3件FAILは`[KI-8]`から継続する既存差分で本Releaseとは無関係）
  - `tests/test_e2e_v3_9_0_retry_engine_event_dispatch.py`：73/73 PASS → 70/73 PASS（新規3件FAIL：テスト20「`__all__`が既存＋新規2シンボルの構成」・テスト21「`__init__` / `from_config()`の最終引数が`event_dispatcher`」×2）
- **原因**：v4.0.0（Retry Execution Foundation）で`src/retry_engine/`に`retry_execution_selector.py` / `retry_execution_coordinator.py`を新規追加し、`retry_manager.py`（`execution_selector` / `execution_coordinator`引数・`execute_dispatchable_retries()`追加）・`__init__.py`（新規シンボルexport）を変更した（`docs/design/retry_execution_foundation.md`）。v3.1.0〜v3.7.0の`git diff --quiet`ベースの検査は「本Releaseがcommitされる前の一時的な検知」であり、v3.9.0の`__all__` / 最終引数検査は「その時点で`event_dispatcher`が最終引数だった」という当時の事実をArchitecture Guardとして固定していたものである。いずれも`[KI-3]`・`[KI-4]`・`[KI-6]`・`[KI-7]`・`[KI-8]`と同種の既知差分である
- **対応状況**：対応しない。v4.0.0のProject Charter / Architecture Design / Architecture Reviewで`retry_execution_selector.py` / `retry_execution_coordinator.py`の新規追加・`retry_manager.py`の変更（`execution_selector` / `execution_coordinator`引数・`execute_dispatchable_retries()`追加）・`__init__.py`の`__all__`更新はいずれも正式に承認済みである。本質的な制約（`scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_event_consumer.py` / `retry_event_dispatcher.py`のゼロ改修、`enqueue_retry()` / `dequeue_retry()` / `RetryQueueManager.dequeue()` / `remove()`に到達しないこと、`dispatchable=True`が唯一の実行入口であること、`RetryManager` / `NullRetryManager`の既存メソッドの後方互換性）は、v4.0.0の新規テスト（`tests/test_e2e_v4_0_0_retry_execution_foundation.py`、88件）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした（`[KI-3]`〜`[KI-8]`と同じ扱い）
- **今後の対応**：不要（本エントリで説明を確定）。`git diff --quiet`ベースのチェック（v3.1.0〜v3.7.0）は本Releaseをcommitすれば自然に解消する。一方、v3.9.0テスト20-21は`git diff`を使わない恒久的な静的検査であり、コミットの有無に関わらず本Release以降も成立しなくなる。将来Release（Retry Queue Update等）で`retry_engine`側にさらに変更が入るたびに同様のFAILが起こりうるが、その都度Charter/Design側で承認済みの変更範囲を確認すればよく、個別のFAILは許容する

### [KI-10] v4.1.0でのRetry Queue Update Foundationにより、v3.1.0〜v4.0.0の一部Architecture GuardがFAILする（設計上の意図的な差分）

- **発見日**：2026-07-06（v4.1.0 Retry Queue Update Foundation Test工程実施時）
- **検証方法**：`git stash`で本Release（`retry_manager.py` / `__init__.py`の変更、`retry_queue_update_decider.py`の新規追加）を一時退避したベースラインと、本Release適用後を比較し、差分の原因が本Releaseの変更であることを構造的に確認した
- **対象と症状（ベースライン → 本Release適用後）**：
  - `tests/test_e2e_v3_0_0_retry_engine_foundation.py`：158/160 PASS → 158/160 PASS（変化なし。テスト21の2件FAILは`[KI-7]`から継続する既存差分で本Releaseとは無関係）
  - `tests/test_e2e_v3_1_0_retry_queue_foundation.py`：152/152 PASS → 151/152 PASS（新規1件FAIL：テスト24「`retry_manager.py`に変更がない（`git diff`）」）
  - `tests/test_e2e_v3_2_0_retry_queue_integration.py`：100/102 PASS → 99/102 PASS（新規1件FAIL：テスト14「`__init__.py`に変更がない（`git diff`）」。テスト16-17は`[KI-7]`/`[KI-8]`から継続する既存差分）
  - `tests/test_e2e_v3_3_0_retry_scheduler_integration.py`：71/72 PASS → 69/72 PASS（新規2件FAIL：テスト18「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」。テスト17は`[KI-4]`の既存差分で無関係）
  - `tests/test_e2e_v3_4_0_retry_scheduler_wiring.py`：94/94 PASS → 92/94 PASS（新規2件FAIL：テスト20「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」）
  - `tests/test_e2e_v3_5_0_retry_scheduler_decision.py`：71/72 PASS → 69/72 PASS（新規2件FAIL：テスト19「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」。テスト18は`[KI-4]`の既存差分で無関係）
  - `tests/test_e2e_v3_6_0_retry_scheduler_decision_wiring.py`：102/104 PASS → 100/104 PASS（新規2件FAIL：テスト24「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」。テスト16-17は`[KI-6]`の既存差分で無関係）
  - `tests/test_e2e_v3_7_0_retry_scheduler_event_integration.py`：74/74 PASS → 72/74 PASS（新規2件FAIL：テスト21「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」）
  - `tests/test_e2e_v3_8_0_retry_engine_event_consumption.py`：67/70 PASS → 67/70 PASS（変化なし。テスト24「`__all__`が既存＋新規2シンボルの構成」・テスト25「最終引数が`event_consumer`」の3件FAILは`[KI-8]`から継続する既存差分で本Releaseとは無関係）
  - `tests/test_e2e_v3_9_0_retry_engine_event_dispatch.py`：70/73 PASS → 70/73 PASS（変化なし。テスト20「`__all__`が既存＋新規2シンボルの構成」・テスト21「最終引数が`event_dispatcher`」×2の3件FAILは`[KI-9]`から継続する既存差分で本Releaseとは無関係）
  - `tests/test_e2e_v4_0_0_retry_execution_foundation.py`：88/88 PASS → 83/88 PASS（新規5件FAIL：テスト25「`__all__`が既存＋新規3シンボルの構成」・テスト26「`__init__` / `from_config()`の最終引数が`execution_coordinator`、最後から2番目が`execution_selector`」×4）
- **原因**：v4.1.0（Retry Queue Update Foundation）で`src/retry_engine/`に`retry_queue_update_decider.py`を新規追加し、`retry_manager.py`（`queue_update_decider`引数・`decide_retry_queue_updates()`追加）・`__init__.py`（新規シンボルexport）を変更した（`docs/design/retry_queue_update_foundation.md`）。v3.1.0〜v3.7.0の`git diff --quiet`ベースの検査は「本Releaseがcommitされる前の一時的な検知」であり、v4.0.0の`__all__` / 最終引数検査は「その時点で`execution_selector` / `execution_coordinator`が最終2引数だった」という当時の事実をArchitecture Guardとして固定していたものである。いずれも`[KI-3]`〜`[KI-9]`と同種の既知差分である
- **対応状況**：対応しない。v4.1.0のProject Charter / Architecture Design / Architecture Reviewで`retry_queue_update_decider.py`の新規追加・`retry_manager.py`の変更（`queue_update_decider`引数・`decide_retry_queue_updates()`追加）・`__init__.py`の`__all__`更新はいずれも正式に承認済みである。本質的な制約（`scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_event_consumer.py` / `retry_event_dispatcher.py` / `retry_execution_selector.py` / `retry_execution_coordinator.py`のゼロ改修、`RetryQueueManager.remove()` / `dequeue()`に到達しないこと、`RetryQueueUpdateDecider`が判定のみを担い`RetryQueueManager` / `NullRetryQueueManager`への参照を一切持たないこと、`RetryManager` / `NullRetryManager`の既存メソッドの後方互換性）は、v4.1.0の新規テスト（`tests/test_e2e_v4_1_0_retry_queue_update_foundation.py`、87件）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした（`[KI-3]`〜`[KI-9]`と同じ扱い）
- **今後の対応**：不要（本エントリで説明を確定）。`git diff --quiet`ベースのチェック（v3.1.0〜v3.7.0）は本Releaseをcommitすれば自然に解消する。一方、v4.0.0テスト25-26は`git diff`を使わない恒久的な静的検査であり、コミットの有無に関わらず本Release以降も成立しなくなる。将来Release（Retry Queue Removal等）で`retry_engine`側にさらに変更が入るたびに同様のFAILが起こりうるが、その都度Charter/Design側で承認済みの変更範囲を確認すればよく、個別のFAILは許容する

### [KI-11] v4.2.0でのRetry Queue Removal Foundationにより、v3.1.0〜v4.1.0の一部Architecture GuardがFAILする（設計上の意図的な差分）

- **発見日**：2026-07-06（v4.2.0 Retry Queue Removal Foundation Test工程実施時）
- **検証方法**：`git stash`で本Release（`retry_manager.py` / `__init__.py`の変更、`retry_queue_removal_executor.py`の新規追加）を一時退避したベースラインと、本Release適用後を比較し、差分の原因が本Releaseの変更であることを構造的に確認した
- **対象と症状（ベースライン → 本Release適用後）**：
  - `tests/test_e2e_v3_0_0_retry_engine_foundation.py`：164/166 PASS → 164/166 PASS（変化なし。テスト21の2件FAILは`[KI-7]`から継続する既存差分で本Releaseとは無関係）
  - `tests/test_e2e_v3_1_0_retry_queue_foundation.py`：152/152 PASS → 151/152 PASS（新規1件FAIL：テスト24「`retry_manager.py`に変更がない（`git diff`）」）
  - `tests/test_e2e_v3_2_0_retry_queue_integration.py`：100/102 PASS → 99/102 PASS（新規1件FAIL：テスト14「`__init__.py`に変更がない（`git diff`）」。テスト16-17は`[KI-7]`/`[KI-8]`から継続する既存差分）
  - `tests/test_e2e_v3_3_0_retry_scheduler_integration.py`：71/72 PASS → 69/72 PASS（新規2件FAIL：テスト18「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」。テスト17は`[KI-4]`の既存差分で無関係）
  - `tests/test_e2e_v3_4_0_retry_scheduler_wiring.py`：94/94 PASS → 92/94 PASS（新規2件FAIL：テスト20「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」）
  - `tests/test_e2e_v3_5_0_retry_scheduler_decision.py`：71/72 PASS → 69/72 PASS（新規2件FAIL：テスト19「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」。テスト18は`[KI-4]`の既存差分で無関係）
  - `tests/test_e2e_v3_6_0_retry_scheduler_decision_wiring.py`：102/104 PASS → 100/104 PASS（新規2件FAIL：テスト24「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」。テスト16-17は`[KI-6]`の既存差分で無関係）
  - `tests/test_e2e_v3_7_0_retry_scheduler_event_integration.py`：74/74 PASS → 72/74 PASS（新規2件FAIL：テスト21「`retry_manager.py` / `__init__.py`に変更がない（`git diff`）」）
  - `tests/test_e2e_v3_8_0_retry_engine_event_consumption.py`：67/70 PASS → 67/70 PASS（変化なし。テスト24「`__all__`が既存＋新規2シンボルの構成」・テスト25「最終引数が`event_consumer`」の3件FAILは`[KI-8]`から継続する既存差分で本Releaseとは無関係）
  - `tests/test_e2e_v3_9_0_retry_engine_event_dispatch.py`：70/73 PASS → 70/73 PASS（変化なし。テスト20「`__all__`が既存＋新規2シンボルの構成」・テスト21「最終引数が`event_dispatcher`」×2の3件FAILは`[KI-9]`から継続する既存差分で本Releaseとは無関係）
  - `tests/test_e2e_v4_0_0_retry_execution_foundation.py`：83/88 PASS → 83/88 PASS（変化なし。テスト25「`__all__`が既存＋新規3シンボルの構成」・テスト26「最終引数が`execution_coordinator`、最後から2番目が`execution_selector`」×4の5件FAILは`[KI-10]`から継続する既存差分で本Releaseとは無関係）
  - `tests/test_e2e_v4_1_0_retry_queue_update_foundation.py`：87/87 PASS → 84/87 PASS（新規3件FAIL：テスト22「`__all__`が既存＋新規3シンボルの構成」・テスト23「`__init__` / `from_config()`の最終引数が`queue_update_decider`」×2）
- **原因**：v4.2.0（Retry Queue Removal Foundation）で`src/retry_engine/`に`retry_queue_removal_executor.py`を新規追加し、`retry_manager.py`（`queue_removal_executor`引数・`apply_retry_queue_removals()`追加）・`__init__.py`（新規シンボルexport）を変更した（`docs/design/retry_queue_removal_foundation.md`）。v3.1.0〜v3.7.0の`git diff --quiet`ベースの検査は「本Releaseがcommitされる前の一時的な検知」であり、v4.1.0の`__all__` / 最終引数検査は「その時点で`queue_update_decider`が最終引数だった」という当時の事実をArchitecture Guardとして固定していたものである。いずれも`[KI-3]`〜`[KI-10]`と同種の既知差分である
- **対応状況**：対応しない。v4.2.0のProject Charter / Architecture Design / Architecture Reviewで`retry_queue_removal_executor.py`の新規追加・`retry_manager.py`の変更（`queue_removal_executor`引数・`apply_retry_queue_removals()`追加）・`__init__.py`の`__all__`更新はいずれも正式に承認済みである。本質的な制約（`scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_event_consumer.py` / `retry_event_dispatcher.py` / `retry_execution_selector.py` / `retry_execution_coordinator.py` / `retry_queue_update_decider.py`のゼロ改修、`outcome`が`NOOP`の項目は`remove()`を呼び出さないこと、`RetryQueueRemovalExecutor`が`RetryQueueManager` / `NullRetryQueueManager`型への直接依存を持たないこと、`RetryManager` / `NullRetryManager`の既存メソッドの後方互換性）は、v4.2.0の新規テスト（`tests/test_e2e_v4_2_0_retry_queue_removal_foundation.py`、94件）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした（`[KI-3]`〜`[KI-10]`と同じ扱い）
- **今後の対応**：不要（本エントリで説明を確定）。`git diff --quiet`ベースのチェック（v3.1.0〜v3.7.0）は本Releaseをcommitすれば自然に解消する。一方、v4.1.0テスト22-23は`git diff`を使わない恒久的な静的検査であり、コミットの有無に関わらず本Release以降も成立しなくなる。将来Release（`SKIPPED`のQueue滞留対応等）で`retry_engine`側にさらに変更が入るたびに同様のFAILが起こりうるが、その都度Charter/Design側で承認済みの変更範囲を確認すればよく、個別のFAILは許容する

### [KI-12] v4.3.0でのRetry Queue Cleanup Foundationにより、v4.1.0〜v4.2.0の一部Architecture GuardがFAILする（設計上の意図的な差分）

- **発見日**：2026-07-08（v4.3.0 Retry Queue Cleanup Foundation Test工程実施時）
- **検証方法**：`git stash`で本Release（`retry_manager.py` / `__init__.py`の変更、`retry_queue_cleanup_decider.py` / `retry_queue_cleanup_executor.py`の新規追加）を一時退避したベースラインと、本Release適用後を比較し、差分の原因が本Releaseの変更であることを構造的に確認した
- **対象と症状（ベースライン → 本Release適用後）**：
  - `tests/test_e2e_v4_1_0_retry_queue_update_foundation.py`：84/87 PASS → 84/87 PASS（変化なし。テスト22「`__all__`が既存＋新規3シンボルの構成」・テスト23「最終引数が`queue_update_decider`」×2の3件FAILは`[KI-11]`から継続する既存差分で本Releaseとは無関係）
  - `tests/test_e2e_v4_2_0_retry_queue_removal_foundation.py`：94/94 PASS → 91/94 PASS（新規3件FAIL：テスト24「`__all__`が既存＋新規2シンボルの構成」・テスト25「`__init__` / `from_config()`の最終引数が`queue_removal_executor`」×2）
- **原因**：v4.3.0（Retry Queue Cleanup Foundation）で`src/retry_engine/`に`retry_queue_cleanup_decider.py` / `retry_queue_cleanup_executor.py`を新規追加し、`retry_manager.py`（`queue_cleanup_decider` / `queue_cleanup_executor`引数・`decide_retry_queue_cleanup()` / `apply_retry_queue_cleanup()`追加）・`__init__.py`（新規シンボルexport）を変更した（`docs/design/retry_queue_cleanup_foundation.md`）。v4.2.0の`__all__` / 最終引数検査は「その時点で`queue_removal_executor`が最終引数だった」という当時の事実をArchitecture Guardとして固定していたものであり、`[KI-3]`〜`[KI-11]`と同種の既知差分である
- **対応状況**：対応しない。v4.3.0のProject Charter / Architecture Design / Architecture Reviewで`retry_queue_cleanup_decider.py` / `retry_queue_cleanup_executor.py`の新規追加・`retry_manager.py`の変更・`__init__.py`の`__all__`更新はいずれも正式に承認済みである。本質的な制約（`scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_queue_update_decider.py` / `retry_queue_removal_executor.py`等のゼロ改修、`outcome`が`KEEP`の項目は`remove()`を呼び出さないこと、`RetryQueueCleanupDecider` / `RetryQueueCleanupExecutor`が`RetryQueueManager` / `NullRetryQueueManager`型への直接依存を持たないこと、`RetryManager` / `NullRetryManager`の既存メソッドの後方互換性）は、v4.3.0の新規テスト（`tests/test_e2e_v4_3_0_retry_queue_cleanup_foundation.py`、108件）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした（`[KI-3]`〜`[KI-11]`と同じ扱い）
- **今後の対応**：不要（本エントリで説明を確定）。将来Release（`NOT_FOUND` / `DISABLED`由来のCleanup方針検討等）で`retry_engine`側にさらに変更が入るたびに同様のFAILが起こりうるが、その都度Charter/Design側で承認済みの変更範囲を確認すればよく、個別のFAILは許容する

### [KI-13] v4.4.0でのNOT_FOUND / DISABLED Cleanup Foundationにより、v4.3.0の一部Architecture GuardがFAILする（設計上の意図的な差分）

- **発見日**：2026-07-08（v4.4.0 NOT_FOUND / DISABLED Cleanup Foundation Test工程実施時）
- **検証方法**：`git stash`で本Release（`retry_manager.py` / `__init__.py`の変更、`retry_outcome_terminality.py` / `retry_queue_terminal_cleanup_decider.py` / `retry_queue_terminal_cleanup_executor.py`の新規追加）を一時退避したベースラインと、本Release適用後を比較し、差分の原因が本Releaseの変更であることを構造的に確認した
- **対象と症状（ベースライン → 本Release適用後）**：
  - `tests/test_e2e_v4_1_0_retry_queue_update_foundation.py`：84/87 PASS → 84/87 PASS（変化なし。`[KI-11]`から継続する既存差分で本Releaseとは無関係）
  - `tests/test_e2e_v4_2_0_retry_queue_removal_foundation.py`：91/94 PASS → 91/94 PASS（変化なし。`[KI-12]`から継続する既存差分で本Releaseとは無関係）
  - `tests/test_e2e_v4_3_0_retry_queue_cleanup_foundation.py`：108/108 PASS → 105/108 PASS（新規3件FAIL：テスト32「`__all__`が既存＋新規5シンボルの構成」・テスト33「`__init__` / `from_config()`の最終2引数が`queue_cleanup_decider`/`queue_cleanup_executor`」×2）
- **原因**：v4.4.0（NOT_FOUND / DISABLED Cleanup Foundation）で`src/retry_engine/`に`retry_outcome_terminality.py` / `retry_queue_terminal_cleanup_decider.py` / `retry_queue_terminal_cleanup_executor.py`を新規追加し、`retry_manager.py`（`terminal_cleanup_decider` / `terminal_cleanup_executor`引数・`decide_retry_queue_terminal_cleanup()` / `apply_retry_queue_terminal_cleanup()`追加）・`__init__.py`（新規シンボルexport）を変更した（`docs/design/retry_queue_notfound_disabled_cleanup_foundation.md`）。v4.3.0の`__all__` / 最終引数検査は「その時点で`queue_cleanup_decider` / `queue_cleanup_executor`が最終引数だった」という当時の事実をArchitecture Guardとして固定していたものであり、`[KI-3]`〜`[KI-12]`と同種の既知差分である
- **対応状況**：対応しない。v4.4.0のProject Charter / Architecture Design / Architecture Reviewで`retry_outcome_terminality.py` / `retry_queue_terminal_cleanup_decider.py` / `retry_queue_terminal_cleanup_executor.py`の新規追加・`retry_manager.py`の変更・`__init__.py`の`__all__`更新はいずれも正式に承認済みである。本質的な制約（`scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_queue_update_decider.py` / `retry_queue_removal_executor.py` / `retry_queue_cleanup_decider.py` / `retry_queue_cleanup_executor.py`のゼロ改修、`outcome`が`KEEP`の項目は`remove()`を呼び出さないこと、`RetryQueueTerminalCleanupDecider` / `RetryQueueTerminalCleanupExecutor`が`RetryQueueManager` / `NullRetryQueueManager`型への直接依存を持たないこと、`RetryManager` / `NullRetryManager`の既存メソッドの後方互換性）は、v4.4.0の新規テスト（`tests/test_e2e_v4_4_0_retry_queue_notfound_disabled_cleanup_foundation.py`、123件）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした（`[KI-3]`〜`[KI-12]`と同じ扱い）
- **今後の対応**：不要（本エントリで説明を確定）。将来Release（Retry Policy Foundation・Queue永続化等）で`retry_engine`側にさらに変更が入るたびに同様のFAILが起こりうるが、その都度Charter/Design側で承認済みの変更範囲を確認すればよく、個別のFAILは許容する

### [KI-14] v4.5.0でのRetry Policy Foundationにより、v4.4.0の一部Architecture GuardがFAILする（設計上の意図的な差分）

- **発見日**：2026-07-08（v4.5.0 Retry Policy Foundation Test工程実施時）
- **検証方法**：`git stash`で本Release（`retry_manager.py` / `__init__.py`の変更、`retry_policy_protocol.py`の新規追加）を一時退避したベースラインと、本Release適用後を比較し、差分の原因が本Releaseの変更であることを構造的に確認した
- **対象と症状（ベースライン → 本Release適用後）**：
  - `tests/test_e2e_v4_4_0_retry_queue_notfound_disabled_cleanup_foundation.py`：123/123 PASS → 122/123 PASS（新規1件FAIL：テスト38「`retry_engine.__all__`が既存シンボル＋新規シンボルの構成になっている」）
- **原因**：v4.5.0（Retry Policy Foundation）で`src/retry_engine/`に`retry_policy_protocol.py`を新規追加し、`retry_manager.py`（`policy` / `retry_policy`引数の型注釈を`RetryPolicy`から`ExplainableRetryPolicy`へ変更）・`__init__.py`（新規シンボルexport）を変更した（`docs/design/retry_policy_foundation.md`）。v4.4.0の`__all__`検査は「その時点で`__all__`が36シンボルちょうどだった」という当時の事実をArchitecture Guardとして固定していたものであり、`[KI-3]`〜`[KI-13]`と同種の既知差分である
- **対応状況**：対応しない。v4.5.0のProject Charter / Architecture Design / Architecture Reviewで`retry_policy_protocol.py`の新規追加・`retry_manager.py`の変更（型注釈のみ）・`__init__.py`の`__all__`更新はいずれも正式に承認済みである。本質的な制約（`retry_policy.py`自体が0 diffであること、`retry()` / `_skip_reason()`のロジック本体が1行も変更されていないこと、`RetryManager` / `NullRetryManager`の既存メソッドの後方互換性）は、v4.5.0の新規テスト（`tests/test_e2e_v4_5_0_retry_policy_foundation.py`、64件）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした（`[KI-3]`〜`[KI-13]`と同じ扱い）
- **今後の対応**：不要（本エントリで説明を確定）。将来Release（新しいRetry戦略の実装等）で`retry_engine`側にさらに変更が入るたびに同様のFAILが起こりうるが、その都度Charter/Design側で承認済みの変更範囲を確認すればよく、個別のFAILは許容する

### [KI-15] v4.7.0でのRetry History Foundationにより、v4.4.0の一部Architecture GuardがFAILする（設計上の意図的な差分）

- **発見日**：2026-07-09（v4.7.0 Retry History Foundation Test工程実施時）
- **検証方法**：`git stash`で本Release（`retry_manager.py` / `__init__.py`の変更、`src/retry_history/`・`retry_history_recorder.py`の新規追加）を一時退避したv4.6.0ベースラインと、本Release適用後を比較し、差分の原因が本Releaseの変更であることを構造的に確認した
- **対象と症状（ベースライン → 本Release適用後）**：
  - `tests/test_e2e_v4_4_0_retry_queue_notfound_disabled_cleanup_foundation.py`：122/123 PASS → 120/123 PASS（新規2件FAIL：テスト39「`__init__`の最終2引数が`terminal_cleanup_decider`/`terminal_cleanup_executor`」・「`from_config()`の最終2引数が`terminal_cleanup_decider`/`terminal_cleanup_executor`」）
  - `tests/test_e2e_v4_5_0_retry_policy_foundation.py`：64/64 PASS → 63/64 PASS（新規1件FAIL：テスト11「`retry_engine.__all__`が「既存36シンボル＋新規2シンボル」ちょうどで構成されている」）
  - `tests/test_e2e_v3_1_0_retry_queue_foundation.py`〜`tests/test_e2e_v4_6_0_retry_enqueue_trigger_foundation.py`のうち`retry_manager.py` / `__init__.py`の無変更を`git diff --quiet`で確認する各テスト（`[KI-3]`〜`[KI-4]`等と同型）：本Release分の新規未コミット差分により一時的にFAILする
- **原因**：v4.7.0（Retry History Foundation）で新規独立パッケージ`src/retry_history/`（`RetryHistoryRecord` / `RetryHistoryManager` / `NullRetryHistoryManager`）と`src/retry_engine/retry_history_recorder.py`（`RetryHistoryRecordExecutor`）を追加し、`retry_manager.py`（`history` / `history_recorder`引数・`record_retry_history()`追加）・`__init__.py`（新規シンボルexport）を変更した（`docs/design/retry_history_foundation.md`）。v4.4.0の「最終2引数」検査・v4.5.0の`__all__`件数検査は「その時点で`terminal_cleanup_decider`/`terminal_cleanup_executor`が最終引数だった」「`__all__`が38シンボルちょうどだった」という当時の事実をArchitecture Guardとして固定していたものであり、`[KI-3]`〜`[KI-14]`と同種の既知差分である
- **対応状況**：対応しない。v4.7.0のProject Charter / Architecture Design / Architecture Reviewで`src/retry_history/`の新規追加・`retry_history_recorder.py`の新規追加・`retry_manager.py`の変更（`history` / `history_recorder`引数・`record_retry_history()`追加）・`__init__.py`の`__all__`更新はいずれも正式に承認済みである。本質的な制約（`scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_event_consumer.py` / `retry_event_dispatcher.py` / `retry_execution_selector.py` / `retry_execution_coordinator.py` / `retry_queue_update_decider.py` / `retry_queue_removal_executor.py` / `retry_queue_cleanup_decider.py` / `retry_queue_cleanup_executor.py` / `retry_queue_terminal_cleanup_decider.py` / `retry_queue_terminal_cleanup_executor.py` / `retry_outcome_terminality.py` / `retry_policy.py` / `retry_policy_protocol.py` / `retry_enqueue_trigger`のゼロ改修、`retry_history`が`retry_engine`を一切importしないこと、`RetryManager` / `NullRetryManager`の既存メソッドの後方互換性）は、v4.7.0の新規テスト（`tests/test_e2e_v4_7_0_retry_history_foundation.py`、178件）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした（`[KI-3]`〜`[KI-14]`と同じ扱い）
- **今後の対応**：不要（本エントリで説明を確定）。`git diff --quiet`ベースのチェックは本Releaseをcommitすれば自然に解消する。一方、v4.4.0の最終引数検査・v4.5.0の`__all__`件数検査は`git diff`を使わない恒久的な静的検査であり、コミットの有無に関わらず本Release以降も成立しなくなる。将来Release（Retry Enqueue Guard等）で`retry_engine`側にさらに変更が入るたびに同様のFAILが起こりうるが、その都度Charter/Design側で承認済みの変更範囲を確認すればよく、個別のFAILは許容する
- **無限再投入対策との関係**：本Releaseは`[KI]`ではないが、`docs/design/retry_enqueue_trigger_foundation.md` 11章 Known Issue（Queueから除去された`run_id`の無限再投入リスク）は本Releaseでは未解消のままである。本Releaseは再試行履歴を記録する土台（`RetryHistoryManager`）のみを整備し、`RetryEnqueueTrigger`側からの参照・ガード判定は次Release（Retry Enqueue Guard）に送った

### [KI-16] v4.8.0でのRetry Enqueue Guardにより、v4.6.0の一部Architecture GuardがFAILする（設計上の意図的な差分）

- **発見日**：2026-07-09（v4.8.0 Retry Enqueue Guard Test工程実施時）
- **対象と症状**：
  - `tests/test_e2e_v4_6_0_retry_enqueue_trigger_foundation.py`：98/100 PASS（新規2件FAIL：テスト12「`RetryEnqueueTrigger.__init__`のパラメータが`self, monitor, queue`のみ」・テスト16「`src/retry_enqueue_trigger/`が`__init__.py` / `retry_enqueue_trigger.py`の2ファイルのみ」）
  - `tests/test_e2e_v4_7_0_retry_history_foundation.py`：176/178 PASS（新規2件FAIL：テスト29「`src/retry_enqueue_trigger/retry_enqueue_trigger.py` / `__init__.py`に変更がない（`git diff`）」。いずれも本Release分の未コミット差分による一時的な検知であり、`[KI-3]`等と同型。本Releaseをcommitすれば自然に解消する見込み）
- **原因**：v4.8.0（Retry Enqueue Guard）で`src/retry_enqueue_trigger/`に`retry_enqueue_guard.py`を新規追加し、`retry_enqueue_trigger.py`（`history` / `guard`引数・`skipped_history`フィールド追加）・`__init__.py`（新規シンボルexport）を変更した（`docs/design/retry_enqueue_guard.md`）。v4.6.0のテスト12・16は「その時点で`__init__`が2引数だった」「`src/retry_enqueue_trigger/`が2ファイルだった」という当時の事実をArchitecture Guardとして固定していたものであり、`[KI-3]`〜`[KI-15]`と同種の既知差分である
- **対応状況**：対応しない。v4.8.0のProject Charter / Architecture Design / Architecture Reviewで`retry_enqueue_guard.py`の新規追加・`retry_enqueue_trigger.py`の変更（`history` / `guard`引数・`skipped_history`フィールド追加）・`__init__.py`の`__all__`更新はいずれも正式に承認済みである。本質的な制約（`workflow_monitor` / `retry_queue` / `retry_history` / `retry_engine`のゼロ改修、`history`省略時は`NullRetryHistoryManager()`にフォールバックしGuardが常にALLOWを返すこと＝v4.6.0時点と完全に同一の挙動を維持すること、`RetryEnqueueGuard`が`retry_history`等の外部パッケージ型を一切importしないこと）は、v4.8.0の新規テスト（`tests/test_e2e_v4_8_0_retry_enqueue_guard.py`、129件）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした（`[KI-3]`〜`[KI-15]`と同じ扱い）
- **今後の対応**：不要（本エントリで説明を確定）。`tests/test_e2e_v4_7_0_retry_history_foundation.py`テスト29の`git diff --quiet`ベースのチェックは本Releaseをcommitすれば自然に解消する。一方、`tests/test_e2e_v4_6_0_retry_enqueue_trigger_foundation.py`テスト12・16は`git diff`を使わない恒久的な静的検査であり、コミットの有無に関わらず本Release以降も成立しなくなる。将来Release（`attempt`の実回数連動等）で`retry_enqueue_trigger`側にさらに変更が入るたびに同様のFAILが起こりうるが、その都度Charter/Design側で承認済みの変更範囲を確認すればよく、個別のFAILは許容する

### [KI-17] v4.9.0でのRetry Attempt Synchronization Foundationにより、v4.7.0の一部Architecture GuardがFAILする（設計上の意図的な差分）

- **発見日**：2026-07-09（v4.9.0 Retry Attempt Synchronization Foundation Test工程実施時）
- **対象と症状**：`tests/test_e2e_v4_7_0_retry_history_foundation.py`：177/178 PASS（新規1件FAIL：テスト29「`src/retry_enqueue_trigger/retry_enqueue_trigger.py`に変更がない（`git diff`）」）
- **原因**：v4.9.0（Retry Attempt Synchronization Foundation）で`src/retry_enqueue_trigger/retry_enqueue_trigger.py`の`enqueue_pending_failures()`を変更した（`docs/design/retry_attempt_synchronization_foundation.md`）。v4.7.0のテスト29は「その時点で`retry_enqueue_trigger.py`が無改修だった」という当時の事実をArchitecture Guardとして固定していたものであり、`[KI-3]`〜`[KI-16]`と同種の既知差分である
- **対応状況**：対応しない。v4.9.0のArchitecture Reviewで`retry_enqueue_trigger.py`の変更（`enqueue_pending_failures()`内で`self._history.has_history()`を`self._history.get()`に置き換え、`retry_attempt`に実際の`attempt_count + 1`を渡すよう変更）は正式に承認済みである。本質的な制約（`retry_queue` / `retry_history` / `retry_engine` / `workflow_monitor` / `retry_enqueue_guard.py`のゼロ改修、`RetryEnqueueTrigger.__init__`のシグネチャ・`RetryEnqueueTriggerResult`のフィールド・`__all__`がいずれも無変更であること）は、v4.9.0の新規テスト（`tests/test_e2e_v4_9_0_retry_attempt_synchronization_foundation.py`、96件）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした（`[KI-3]`〜`[KI-16]`と同じ扱い）
- **今後の対応**：不要（本エントリで説明を確定）。`git diff --quiet`ベースのチェックは本Releaseをcommitすれば自然に解消する。将来Release（Guard判定基準の精緻化等）で`retry_enqueue_trigger`側にさらに変更が入るたびに同様のFAILが起こりうるが、その都度Charter/Design側で承認済みの変更範囲を確認すればよく、個別のFAILは許容する

### [KI-18] v5.0.0でのRetry Enqueue Guard Refinementにより、v4.8.0/v4.9.0の既存テストが例外で中断する（設計上の意図的な差分）

- **発見日**：2026-07-09（v5.0.0 Retry Enqueue Guard Refinement Foundation Test工程実施時）
- **対象と症状**：
  - `tests/test_e2e_v4_8_0_retry_enqueue_guard.py`：テスト1（`guard.decide("run-x", has_history=True)`）で`TypeError: RetryEnqueueGuard.decide() got an unexpected keyword argument 'has_history'`が発生し、以降のテストが実行されないまま中断する
  - `tests/test_e2e_v4_9_0_retry_attempt_synchronization_foundation.py`：テスト2（カスタムGuard `_AlwaysAllowGuard.decide(self, run_id, has_history)` を注入するシナリオ）で`TypeError: _AlwaysAllowGuard.decide() got an unexpected keyword argument 'next_attempt'`が発生し、以降のテストが実行されないまま中断する
  - `tests/test_e2e_v4_7_0_retry_history_foundation.py`：テスト29（`src/retry_enqueue_trigger/retry_enqueue_trigger.py`に変更がないことを確認する`git diff`チェック）が1件FAILする（`[KI-17]`と同型の、本Release分の未コミット差分による一時的な検知）
- **原因**：v5.0.0（Retry Enqueue Guard Refinement Foundation）で`RetryEnqueueGuard.decide()`のシグネチャを`decide(run_id, has_history: bool)`から`decide(run_id, next_attempt: int, max_attempts: int)`へ変更した（`docs/design/retry_enqueue_guard_refinement_foundation.md`）。v4.8.0・v4.9.0の既存テストは旧シグネチャ（`has_history`キーワード引数）を前提にGuardを直接呼び出しているため、`[KI-3]`〜`[KI-17]`のような「assertionレベルのFAILカウント」ではなく、Python自体の`TypeError`によりテストスクリプトが即座に中断するという、従来とは異なる形で現れる
- **対応状況**：対応しない。v5.0.0のArchitecture Review（Final、ユーザー承認済み）で`RetryEnqueueGuard.decide()`のシグネチャ変更（`has_history: bool`の廃止、`next_attempt: int` / `max_attempts: int`の新設）は正式に承認済みである。`RetryEnqueueGuard`は`RetryEnqueueTrigger`専属の内部コンポーネントであり他パッケージから単独参照される想定がないため（v4.8.0設計書5章）、影響範囲は`RetryEnqueueTrigger`自身とv4.8.0/v4.9.0の既存テストに閉じる。本質的な制約（`RetryEnqueueTrigger.__init__`が完全に無変更であること、`max_attempts`省略時はv4.8.0/v4.9.0時点と完全に同一の挙動になること、`retry_history` / `retry_queue` / `workflow_monitor` / `retry_engine`のゼロ改修）は、v5.0.0の新規テスト（`tests/test_e2e_v5_0_0_retry_enqueue_guard_refinement_foundation.py`、110件）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした（`[KI-3]`〜`[KI-17]`と同じ扱い）
- **今後の対応**：不要（本エントリで説明を確定）。v4.7.0テスト29の`git diff --quiet`ベースのチェックは本Releaseをcommitすれば自然に解消する。v4.8.0・v4.9.0の`TypeError`による中断は、Guardのシグネチャが将来さらに変わらない限り恒久的に残る（`[KI-4]`2026-07-03追記のテスト17と同種の「恒久化した既知差分」）。将来Release（Composition Root等）で`retry_enqueue_trigger`側にさらに変更が入るたびに同様の差分が起こりうるが、その都度Charter/Design側で承認済みの変更範囲を確認すればよく、個別のFAILは許容する

### [KI-19] v5.2.0でのRetry Runtime Orchestrator Foundationにより、v5.1.0の一部Architecture GuardがFAILする（設計上の意図的な差分）

- **発見日**：2026-07-09（v5.2.0 Retry Runtime Orchestrator Foundation Test工程実施時）
- **対象と症状**：`tests/test_e2e_v5_1_0_retry_composition_root_foundation.py`：36/38 PASS（新規2件FAIL）
  - テスト15「`RetryCompositionRoot.__init__`のパラメータが`(self, monitor, queue, history, guard, trigger, policy, manager)`のみ」
  - テスト20「`retry_composition`を参照する既存ファイルが存在しない」（本Releaseで新設した`src/retry_runtime_orchestrator/retry_runtime_orchestrator.py`が`RetryCompositionRoot`をimportする、`retry_composition`の初めての実消費者となったため）
- **原因**：v5.2.0（Retry Runtime Orchestrator Foundation）で`RetryCompositionRoot.__init__`へ`retry_source` / `retry_decision` / `scheduler`の3パラメータを追加し、新規パッケージ`src/retry_runtime_orchestrator/`を追加した（`docs/design/retry_runtime_orchestrator_foundation.md`）。v5.1.0のテスト15・テスト20は「その時点で`__init__`が7パラメータだった」「`retry_composition`がどこからも参照されていなかった」という当時の事実をArchitecture Guardとして固定していたものであり、`[KI-3]`〜`[KI-18]`と同種の既知差分である
- **対応状況**：対応しない。v5.2.0のArchitecture Review（Final、ユーザー承認済み）で`RetryCompositionRoot.__init__`への3パラメータ追加（末尾追加、既存7パラメータの並び順は無変更）・`src/retry_runtime_orchestrator/`の新規追加はいずれも正式に承認済みである。本質的な制約（`workflow_monitor` / `retry_queue` / `retry_history` / `retry_enqueue_trigger` / `retry_engine` / `workflow_engine` / `ai` / `execution_history` / `scheduler` / `retry_scheduler_source` / `retry_scheduler_decision`のゼロ改修、`RetryCompositionRoot`が`from_env()`以外の公開メソッドを持たないこと、`RetryRuntimeOrchestrator`が参照保持以外のBusiness Logicを持たないこと）は、v5.2.0の新規テスト（`tests/test_e2e_v5_2_0_retry_runtime_orchestrator_foundation.py`、54件）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした（`[KI-3]`〜`[KI-18]`と同じ扱い）
- **今後の対応**：不要（本エントリで説明を確定）。テスト20（「`retry_composition`を参照する既存ファイルが存在しない」）は`git diff`を使わない恒久的な静的検査であり、コミットの有無に関わらず本Release以降も成立しなくなる（`[KI-4]`2026-07-03追記のv3.3.0テスト17と同型。`retry_composition`が本Releaseで初めて実際の消費者（`RetryRuntimeOrchestrator`）を持ったことの自然な帰結）。将来Release（Execution Release等）で`retry_composition`側にさらに変更が入るたびに同様の差分が起こりうるが、その都度Charter/Design側で承認済みの変更範囲を確認すればよく、個別のFAILは許容する

### [KI-20] v5.3.0でのRetry Runtime Run Once Foundationにより、v5.2.0の一部Architecture GuardがFAILする（設計上の意図的な差分）

- **発見日**：2026-07-09（v5.3.0 Retry Runtime Run Once Foundation Test工程実施時）
- **対象と症状**：`tests/test_e2e_v5_2_0_retry_runtime_orchestrator_foundation.py`：50/54 PASS（新規4件FAIL）
  - テスト18「`from_composition_root`以外の公開メソッドが存在しない」「`run_once`という名前のメソッドを持たない」の2アサーション
  - テスト22「`src/retry_runtime_orchestrator/`のファイル構成が`__init__.py`・`retry_runtime_orchestrator.py`の2ファイルのみ」
  - テスト23「`retry_runtime_orchestrator`パッケージのexportが`RetryRuntimeOrchestrator`のみ」
- **原因**：v5.3.0（Retry Runtime Run Once Foundation）で`RetryRuntimeOrchestrator`へ`run_once()`という新規公開メソッドを追加し、`src/retry_runtime_orchestrator/retry_runtime_cycle_result.py`を新規追加、`__init__.py`のexportへ`RetryRuntimeCycleResult`を追加した（`docs/design/retry_runtime_run_once_foundation.md`）。v5.2.0のテスト18・22・23は「その時点でrun_once()等の実行系メソッドが存在しないこと」「ファイル構成が2ファイルのみであること」「exportが1シンボルのみであること」を当時の事実としてArchitecture Guardに固定していたものであり、`[KI-3]`〜`[KI-19]`と同種の既知差分である
- **対応状況**：対応しない。v5.3.0のArchitecture Review（Final、ユーザー承認済み）で`run_once()`の追加・`RetryRuntimeCycleResult`の新設・それに伴うファイル構成/export変更はいずれも正式に承認済みである。本質的な制約（`RetryManager`・既存11パッケージのゼロ改修、`execute_dispatchable_retries()`が1回だけ呼ばれること等）は、v5.3.0の新規テスト（`tests/test_e2e_v5_3_0_retry_runtime_run_once_foundation.py`、54件）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした（`[KI-3]`〜`[KI-19]`と同じ扱い）
- **今後の対応**：不要（本エントリで説明を確定）。`RetryRuntimeOrchestrator`が本Releaseで初めて実行系メソッド（`run_once()`）を持つ実装段階へ移行したことの自然な帰結であり、将来Release（`loop()`/`daemon()`追加等）でさらに変更が入るたびに同様の差分が起こりうるが、その都度Charter/Design側で承認済みの変更範囲を確認すればよく、個別のFAILは許容する

### [KI-21] v5.4.0でのRetry Runtime Script Entry Point Foundationにより、v5.2.0の一部Architecture GuardがFAILする（設計上の意図的な差分）

- **発見日**：2026-07-09（v5.4.0 Retry Runtime Script Entry Point Foundation Test工程実施時）
- **対象と症状**：`tests/test_e2e_v5_2_0_retry_runtime_orchestrator_foundation.py`：49/54 PASS（新規1件FAIL、`[KI-20]`による既存4件FAILと合わせて計5件）
  - テスト25「`retry_runtime_orchestrator`を参照する既存ファイルが存在しない」（本Releaseで新設した`scripts/run_retry_runtime.py`が`retry_runtime_orchestrator`をimportする、`retry_runtime_orchestrator`の初めての実消費者となったため）
- **原因**：v5.4.0（Retry Runtime Script Entry Point Foundation）で`scripts/run_retry_runtime.py`を新規追加し、`RetryCompositionRoot.from_env()` → `RetryRuntimeOrchestrator.from_composition_root()` → `run_once()`を呼び出すEntry Pointとした（`docs/design/retry_runtime_script_entry_point_foundation.md`）。v5.2.0のテスト25は「その時点で`retry_runtime_orchestrator`をどこからも呼び出していないこと」を当時の事実としてArchitecture Guardに固定していたものであり、`[KI-4]`2026-07-03追記のv3.3.0テスト17・`[KI-19]`と同型の既知差分である
- **対応状況**：対応しない。v5.4.0のArchitecture Review（Final、ユーザー承認済み）で`scripts/run_retry_runtime.py`の新規追加・`retry_runtime_orchestrator`の初回消費は正式に承認済みである。本質的な制約（`RetryCompositionRoot` / `RetryRuntimeOrchestrator`・既存12パッケージのゼロ改修、scriptがBusiness Logicを持たないこと、CLI引数を持たないこと）は、v5.4.0の新規テスト（`tests/test_e2e_v5_4_0_retry_runtime_script_entry_point_foundation.py`、67件）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした（`[KI-3]`〜`[KI-20]`と同じ扱い）
- **今後の対応**：不要（本エントリで説明を確定）。本チェックは`git diff`を使わず`src/` / `scripts/`配下の全ファイルを走査する恒久的な静的検査であり、コミットの有無に関わらず本Release以降も成立しなくなる（`[KI-4]`2026-07-03追記・`[KI-19]`と同型。`retry_runtime_orchestrator`が本Releaseで初めて実際の消費者（`scripts/run_retry_runtime.py`）を持ったことの自然な帰結）

### [KI-22] v5.6.0でのRetry Runtime Safe Dry Run Foundationにより、v3.0.0〜v5.5.0の一部Architecture GuardがFAILする（設計上の意図的な差分）

- **発見日**：2026-07-12（v5.6.0 Retry Runtime Safe Dry Run Foundation Test工程実施時。変更前後で全48件のE2Eテストを実行し差分を機械的に比較して確認）
- **対象と症状**：
  - `tests/test_e2e_v3_0_0_retry_engine_foundation.py`：204/208 PASS（新規2件FAIL）。テスト4「RetryOutcomeが4値で定義されている」（本Releaseで5値目の`DRY_RUN`を追加したため）、テスト24「dry_run=True指定時 outcome=RETRIED」（本Releaseの意図的な仕様変更によりoutcome=DRY_RUNへ変更したため）
  - `tests/test_e2e_v3_1_0_*.py`〜`tests/test_e2e_v5_0_0_*.py`（`retry_result.py` / `retry_executor.py` / `retry_engine/__init__.py`を参照する多数のテスト）：各テストの「`src/retry_engine`（または個別ファイル）に変更がない（git diff）」チェックが新規FAILする（本Releaseが`retry_result.py` / `retry_executor.py` / `retry_outcome_terminality.py` / `retry_engine/__init__.py`を変更したため）。特に`retry_outcome_terminality.py`を参照する`tests/test_e2e_v4_5_0_*.py`・`tests/test_e2e_v4_7_0_*.py`は同ファイルの変更も新規FAILとして検出される
  - `tests/test_e2e_v5_1_0_*.py`・`tests/test_e2e_v5_2_0_*.py`：「`src/retry_engine`に変更がない（git diff）」が新規FAIL
  - `tests/test_e2e_v5_3_0_*.py`：テスト2「`run_once()`のパラメータが`self`のみ」が新規FAIL（本Releaseで`dry_run`引数を追加したため）。加えて「`src/retry_engine`に変更がない」も新規FAIL
  - `tests/test_e2e_v5_4_0_*.py`・`tests/test_e2e_v5_5_0_*.py`：「`src/retry_engine`に変更がない」「`src/retry_runtime_orchestrator`に変更がない」が新規FAIL（`run_once()`への`dry_run`引数追加のため）
- **原因**：v5.6.0（Retry Runtime Safe Dry Run Foundation）で、`RetryOutcome`へ`DRY_RUN`を追加し（`retry_result.py`）、`RetryExecutor.execute()`が`dry_run=True`の場合に`outcome=DRY_RUN`を返すよう変更し（`retry_executor.py`）、`retry_outcome_terminality.py`の`classify_reason()`へ`DRY_RUN`分岐を追加し（明示列挙+raiseの網羅チェック方式であるため追従が必須だった）、`RetryRuntimeOrchestrator.run_once()`へ`dry_run: bool = False`引数を追加した。いずれもRelease 5.6のArchitecture Review（ChatGPT/Claude Code/ユーザーの3者協業レビューを経て確定）でユーザー承認済みの設計である
- **対応状況**：対応しない。「無改修」を前提としたArchitecture Guardは、当時（各リリース時点）の事実をテストとして固定したものであり、それ以降のFoundation Releaseが正当な理由で同じファイルへ手を入れるたびに恒久的な既知差分として積み上がっていく（`[KI-7]`〜`[KI-21]`と同型のパターン）。本Releaseの新機能自体は`tests/test_e2e_v5_6_0_retry_runtime_safe_dry_run_foundation.py`（49件、全PASS）で独立して検証済み
- **今後の対応**：不要（本エントリで説明を確定）

### [KI-23] `--dry-run`指定時でも、Retry QueueへのEnqueueは通常どおり実行される

- **発見日**：2026-07-12（v5.6.0 Retry Runtime Safe Dry Run Foundation Architecture Design時点で判明。v5.7.0 Retry Runtime Safe Dry Run Wiring FoundationでCLIから`--dry-run`が一般利用可能になったことに伴い、正式なKnown Issueへ格上げ）
- **対象**：`scripts/run_retry_runtime.py --dry-run`、`RetryEnqueueTrigger.enqueue_pending_failures()`
- **症状**：`--dry-run`指定時、`RetryRuntimeOrchestrator.run_once(dry_run=True)`はRetry実行（`execute_dispatchable_retries()`）以降を安全側（NOOP・記録なし・除去なし）に倒すが、`trigger.enqueue_pending_failures()`はdry_run引数を受け取らないため通常どおり実行される。WorkflowMonitor上のFAILED/TIMEOUTは`--dry-run`指定時もRetry Queueへ実際にenqueueされる
- **原因**：`RetryEnqueueTrigger`（v4.6.0〜v5.0.0）はdry_run引数を持たない設計のまま。v5.6.0のArchitecture Reviewで、Queueへの追加はin-memoryで可逆的・外部作用を伴わないためExecution/Removal/Historyとはリスクレベルが異なると判断し、意図的に対象外とした（`docs/design/retry_runtime_safe_dry_run_foundation.md` 4節）
- **対応状況**：解消済み
- **今後の対応**：不要（本エントリで解消済み）
- **2026-07-12追記（v5.8.0 Retry Enqueue Trigger Dry Run Foundationで解消）**：`RetryEnqueueTrigger.enqueue_pending_failures()`へ`dry_run: bool = False`を呼び出し時引数として追加した。Monitor走査・History参照・Guard判定・Queue重複確認は`dry_run`の値に関わらず通常どおり実行するが、Guardを通過しQueue重複も存在しない候補について、`dry_run=True`の場合は`RetryQueueManager.enqueue()`を呼び出さず処理を終了するよう変更した（`enqueued` / `failed`いずれにも加算しない）。`RetryRuntimeOrchestrator.run_once()`から`trigger.enqueue_pending_failures(max_attempts=self.policy.max_attempts, dry_run=dry_run)`への伝播も追加し、`--dry-run`指定時にRetry Queueへの新規enqueueが実際に抑止されるようになった。`RetryEnqueueTriggerResult` / `format_summary()` / `scripts/run_retry_runtime.py`はいずれも無改修（`docs/design/retry_enqueue_trigger_dry_run_foundation.md`）

### [KI-24] v5.7.0でのRetry Runtime Safe Dry Run Wiring Foundationにより、v5.4.0/v5.5.0/v5.6.0の一部Architecture GuardがFAILする（設計上の意図的な差分）

- **発見日**：2026-07-12（v5.7.0 Retry Runtime Safe Dry Run Wiring Foundation Test工程実施時）
- **対象と症状**：
  - `tests/test_e2e_v5_4_0_retry_runtime_script_entry_point_foundation.py`：66/67 PASS（新規1件FAIL）。テスト7「argparseをimportしない」（本Releaseで`main()`内に`argparse`のローカルimportを追加したため）
  - `tests/test_e2e_v5_5_0_retry_runtime_loop_foundation.py`：36/37 PASS（新規1件FAIL）。テスト15「`scripts/run_retry_runtime.py`に変更がない（git diff）」
  - `tests/test_e2e_v5_6_0_retry_runtime_safe_dry_run_foundation.py`：48/49 PASS（新規1件FAIL）。テスト25「`scripts/run_retry_runtime.py`に変更がない（git diff）」
- **原因**：v5.7.0（Retry Runtime Safe Dry Run Wiring Foundation）で`scripts/run_retry_runtime.py`の`main()`へ`argparse`・`--dry-run`解析・`run_once(dry_run=...)`への伝播を追加した（`docs/design/retry_runtime_safe_dry_run_wiring_foundation.md`）。v5.4.0・v5.5.0・v5.6.0の該当テストは「その時点で`scripts/run_retry_runtime.py`が無改修・CLI引数を持たなかった」という当時の事実をArchitecture Guardとして固定していたものであり、`[KI-3]`〜`[KI-22]`と同型の既知差分である
- **対応状況**：対応しない。v5.7.0のArchitecture Review（ユーザー承認済み）で`main()`内部のみへの変更（`RetryRuntimeOrchestrator` / `RetryManager` / `RetryExecutor` / `RetryCompositionRoot` / `RetryRuntimeCycleResult` / `format_summary()`はいずれも無改修）は正式に承認済みである。本質的な制約（既存13パッケージのゼロ改修、`format_summary()`のシグネチャ・実装が無改修であること、`parse_args()`等の関数分離を行わないこと）は、v5.7.0の新規テスト（`tests/test_e2e_v5_7_0_retry_runtime_safe_dry_run_wiring_foundation.py`、86件）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした（`[KI-3]`〜`[KI-22]`と同じ扱い）
- **今後の対応**：不要（本エントリで説明を確定）

### [KI-25] v5.8.0でのRetry Enqueue Trigger Dry Run Foundationにより、一部Architecture GuardがFAILする（設計上の意図的な差分）

- **発見日**：2026-07-12（v5.8.0 Retry Enqueue Trigger Dry Run Foundation Test工程実施時）
- **対象と症状**：
  - `tests/test_e2e_v5_0_0_retry_enqueue_guard_refinement_foundation.py`：テスト16「`enqueue_pending_failures()`のパラメータが`self, limit, max_attempts`」が新規FAIL（本Releaseで`dry_run`を追加したため）
  - `tests/test_e2e_v5_1_0_retry_composition_root_foundation.py`：テスト19（`src/retry_enqueue_trigger`に変更がないことを確認する`git diff`チェック）が新規FAIL
  - `tests/test_e2e_v5_2_0_retry_runtime_orchestrator_foundation.py`：テスト24（同上）が新規FAIL
  - `tests/test_e2e_v5_3_0_retry_runtime_run_once_foundation.py`：テスト28（同上、`unchanged_paths_28`の一部）が新規FAIL（52/54 PASS。残り1件はテスト2、`[KI-22]`による既存差分）
  - `tests/test_e2e_v5_4_0_retry_runtime_script_entry_point_foundation.py`：テスト15の2件（`src/retry_enqueue_trigger` / `src/retry_runtime_orchestrator`に変更がないことを確認する`git diff`チェック）が新規FAIL
  - `tests/test_e2e_v5_6_0_retry_runtime_safe_dry_run_foundation.py`：テスト23（`src/retry_enqueue_trigger`に変更がないことを確認する`git diff`チェック、`unchanged_dirs_23`の一部）が新規FAIL
  - `tests/test_e2e_v5_7_0_retry_runtime_safe_dry_run_wiring_foundation.py`：テスト24の2件（`src/retry_enqueue_trigger` / `src/retry_runtime_orchestrator`に変更がないことを確認する`git diff`チェック、`unchanged_dirs_24`の一部）が新規FAIL
- **原因**：v5.8.0（Retry Enqueue Trigger Dry Run Foundation）で`src/retry_enqueue_trigger/retry_enqueue_trigger.py` / `src/retry_runtime_orchestrator/retry_runtime_orchestrator.py`の2ファイルを変更した（`docs/design/retry_enqueue_trigger_dry_run_foundation.md`）。上記の各テストは「その時点でこれらのファイル・パッケージが無改修だった」という当時の事実をArchitecture Guardとして固定していたものであり、`[KI-3]`〜`[KI-24]`と同型の既知差分である
- **対応状況**：対応しない。v5.8.0のArchitecture Review（ユーザー承認済み）で対象2ファイルへの変更は正式に承認済みである。本質的な制約（`RetryEnqueueTriggerResult` / `RetryRuntimeCycleResult` / `format_summary()` / `scripts/run_retry_runtime.py` / `RetryCompositionRoot` / `RetryManager` / `RetryExecutor` / `RetryQueueManager` / `RetryHistoryManager` / `RetryEnqueueGuard` / `RetryRuntimeLoop` / `NullRetryEnqueueTrigger`のゼロ改修、`enqueue_pending_failures()` / `run_once()`双方のシグネチャの意図した形）は、v5.8.0の新規テスト（`tests/test_e2e_v5_8_0_retry_enqueue_trigger_dry_run_foundation.py`、20テスト・64アサーション）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした（`[KI-3]`〜`[KI-24]`と同じ扱い）
- **今後の対応**：不要（本エントリで説明を確定）

### [KI-26] v5.8.0でのRetry Enqueue Trigger Dry Run Foundationにより、v5.6.0の一部テストが仕様変更により新規FAILする（`[KI-23]`解消に伴う意図的な挙動変化）

- **発見日**：2026-07-12（v5.8.0 Retry Enqueue Trigger Dry Run Foundation Test工程実施時）
- **対象と症状**：`tests/test_e2e_v5_6_0_retry_runtime_safe_dry_run_foundation.py`の以下4件が新規FAILする
  - テスト16「`run_once(dry_run=True)`後もQueueに`run-e2e-dry`が残っている」
  - テスト18「`execution_results[0].retry_result.outcome`が`DRY_RUN`」
  - テスト19「`WorkflowEngineManager.run()`に`dry_run=True`が伝播している」
  - テスト20「`trigger.enqueue_pending_failures`は通常どおり実行されQueueへ登録される」
- **原因**：これら4件は、v5.6.0時点で`RetryEnqueueTrigger`が`dry_run`非対応だったこと（`[KI-23]`の症状そのもの）を前提に、「`run_once(dry_run=True)`を呼んでも対象run_idはQueueへenqueueされ続ける」ことを期待値として固定していた。v5.8.0で`[KI-23]`を解消した結果、`run_once(dry_run=True)`は対象run_idをそもそもQueueへenqueueしなくなったため、Queueへ残る項目が存在せず、Scheduler候補・Execution対象にもならない（`execution_results`が空リストになる）。これによりテスト16・18・19・20の期待値が本Releaseの目的そのものによって反転した
- **対応状況**：対応しない。これは通常のArchitecture Guard差分（無改修前提の`git diff`チェック等）とは異なり、**Result（挙動）そのものの意図的な仕様変更**によるものである。v5.6.0時点で「Enqueue側は対象外」と明記されていた設計上の制約（`docs/design/retry_runtime_safe_dry_run_foundation.md` 4節）が、v5.8.0で解消されたことの自然な帰結であり、v5.8.0のArchitecture Review（ユーザー承認済み）で想定済みである。`run_once(dry_run=True)`が引き続き安全であること自体は、v5.8.0の新規テスト（テスト8「`run_once(dry_run=True)`がtriggerへdry_runを伝播し、enqueueが抑止される」）で別途確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした
- **今後の対応**：不要（本エントリで説明を確定）

### [KI-27] v5.9.0でのRetry Runtime Loop Wiring Foundationにより、`scripts/run_retry_runtime.py`無改修を前提とする一部Architecture GuardがFAILする（設計上の意図的な差分）

- **発見日**：2026-07-12（v5.9.0 Retry Runtime Loop Wiring Foundation Test工程実施時）
- **対象と症状**：
  - `tests/test_e2e_v5_5_0_retry_runtime_loop_foundation.py`：テスト15（`unchanged_paths_15`の一部として`scripts/run_retry_runtime.py`の`git diff`無変更確認）が新規FAIL
  - `tests/test_e2e_v5_6_0_retry_runtime_safe_dry_run_foundation.py`：テスト25（`scripts/run_retry_runtime.py`の`git diff`無変更確認、専用チェック）が新規FAIL
  - `tests/test_e2e_v5_8_0_retry_enqueue_trigger_dry_run_foundation.py`：テスト17（`unchanged_paths_17`の一部として`scripts/run_retry_runtime.py`の`git diff`無変更確認）が新規FAIL
- **原因**：v5.9.0（Retry Runtime Loop Wiring Foundation）で`scripts/run_retry_runtime.py`へ`--loop` / `--interval-seconds`引数、`RetryRuntimeLoop`の組み立て・実行、`KeyboardInterrupt`処理を追加した（`docs/design/retry_runtime_loop_wiring_foundation.md`）。上記の各テストは「その時点で`scripts/run_retry_runtime.py`が無改修だった」という当時の事実をArchitecture Guardとして固定していたものであり、`[KI-3]`〜`[KI-26]`と同型の既知差分である
- **対応状況**：対応しない。v5.9.0のArchitecture Design/Review（GPT-5.6 Sol）・ユーザー承認済みで`scripts/run_retry_runtime.py`単独への変更は正式に承認済みである。本質的な制約（`src/retry_runtime_loop/` / `src/retry_runtime_orchestrator/` / `src/retry_composition/` / `RetryManager`（`retry_engine`）等のゼロ改修、単発実行の後方互換性、`format_summary()`の公開契約無変更）は、v5.9.0の新規テスト（`tests/test_e2e_v5_9_0_retry_runtime_loop_wiring_foundation.py`、64アサーション）で別途構造的に確認済み。既存テストファイル自体は書き換えず、Release間の前提差分として本エントリに記録する方針とした
- **今後の対応**：不要（本エントリで説明を確定）
- **2026-07-14追記（v6.0.0 Retry Runtime Lock Foundation Test工程実施時に再確認）**：v6.0.0で`scripts/run_retry_runtime.py`へRuntime Lock（`with lock:`ラップ）を追加したことにより、本項目が対象とする3ファイルへ改めて変更が加わったが、実測の結果FAIL件数・対象は変化していない（`tests/test_e2e_v5_5_0_*.py`：35/37、`tests/test_e2e_v5_6_0_*.py`：44/49、`tests/test_e2e_v5_8_0_*.py`：63/64。いずれもv5.9.0時点の記録と同一件数）。これは`scripts/run_retry_runtime.py`が既にv5.9.0の変更により「無改修」という前提を満たさなくなっており、v6.0.0による追加変更は同じ既知差分の範囲内に留まるため、新規Known Issueの追加は不要と判断した

### [KI-28] v5.9.0でのRetry Runtime Loop Wiring Foundationにより、`retry_runtime_loop`が初めて実際の消費者を持ったことでv5.5.0の一部Architecture GuardがFAILする（`[KI-21]`と同型の恒久差分）

- **発見日**：2026-07-12（v5.9.0 Retry Runtime Loop Wiring Foundation Test工程実施時）
- **対象と症状**：`tests/test_e2e_v5_5_0_retry_runtime_loop_foundation.py`：テスト16「`retry_runtime_loop`を参照する既存ファイルが存在しない（消費者不在の先行実装）」が新規FAIL
- **原因**：v5.9.0で`scripts/run_retry_runtime.py`が`from retry_runtime_loop import RetryRuntimeLoop`を追加し、`retry_runtime_loop`パッケージ（v5.5.0、Foundation Release時点では「消費者不在の先行実装」として意図的に未配線だった）が初めて実際の消費者を持った。v5.5.0テスト16は「本Releaseでは誰からも呼び出されない」という当時の事実を`src/` / `scripts/`双方を対象にした恒久的な静的検査として固定していたものであり、`[KI-21]`（`retry_runtime_orchestrator`がv5.4.0で初めて消費者を持った際の同型差分）と完全に同じパターンである
- **対応状況**：対応しない。「消費者不在の先行実装」というFoundation Release（v5.5.0）の性質上、後続Releaseで実際に配線されれば本チェックは恒久的に成立しなくなることは`[KI-21]`の前例で確立済みの許容パターンである。`retry_runtime_loop`が正しく配線されていること自体は、v5.9.0の新規テスト（テスト11「既存`RetryRuntimeLoop`（本番クラス）がそのまま使用される」等）で別途確認済み
- **今後の対応**：不要（本エントリで説明を確定）

### [KI-29] v6.1.0でのGraceful Shutdown Foundationにより、`tests/test_e2e_v5_9_0_*.py`が全面的に、`tests/test_e2e_v6_0_0_*.py`が一部実行不能になる（`[KI-27]`より深刻な既知差分、解消済み）

- **発見日**：2026-07-14（v6.1.0 Graceful Shutdown Foundation Test工程実施時）
- **対象と症状**：
  - `tests/test_e2e_v5_9_0_retry_runtime_loop_wiring_foundation.py`：テスト1（最初の`run_main_with_argv([])`呼び出し）の時点で`AttributeError: module 'run_retry_runtime_v590' has no attribute 'time'`が送出され、以降のテストが一切実行されない（0/64相当で停止）
  - `tests/test_e2e_v6_0_0_retry_runtime_lock_foundation.py`：テスト1〜12（22アサーション）はPASSするが、テスト13（`run_main_with_argv([])`呼び出し）の時点で同じ`AttributeError`が送出され、テスト13〜24（Backward Compatibility確認を含む）が実行されない
- **原因**：本Releaseで`scripts/run_retry_runtime.py`の`--loop`実行時の`sleep_fn`を`time.sleep`から`RetryRuntimeShutdown.interruptible_sleep`へ差し替えたこと（Architecture Design・Architecture Review承認済み、シグナル受信後に最大`interval_seconds`待たされる問題の解消が目的）に伴い、`time`モジュールを直接使う箇所が`scripts/run_retry_runtime.py`から無くなったため、`import time`を削除した。両テストファイルの`run_main_with_argv()`ヘルパーは、Loop関連のテストか否かに関わらず無条件に`original_sleep = run_retry_runtime.time.sleep`を実行しており、この行で例外が発生する
- **`[KI-27]`との違い**：`[KI-27]`系列の既知差分は「`git diff`無変更確認テストがFAILする」という、ファイル全体の実行は継続したままの部分的な差分だった。本件は`AttributeError`によりテストスクリプト自体が停止するため、影響範囲がより広い（v5.9.0ファイルは全滅、v6.0.0ファイルは半分弱が未実行）
- **検討した代替策**：`import time`を削除せず残す案も検討したが、この場合`AttributeError`は回避できるものの、Loop関連テストが注入する`sleep_fn`（`run_retry_runtime.time.sleep`への差し替え）は`RetryRuntimeLoop`が実際に使う`sleep_fn`（`shutdown.interruptible_sleep`）と無関係になり、テストのSentinel例外が送出されずLoopが停止しない（無限ループ・ハング）。即座に失敗する`AttributeError`の方が、ハングよりも安全と判断し`import time`削除を採用した
- **対応状況**：**解消済み。** Release 6.1 Regression Test Maintenance（2026-07-14、Documentation/テストのみのFast Track、本番コード変更なし）で、`tests/test_e2e_v5_9_0_retry_runtime_loop_wiring_foundation.py` / `tests/test_e2e_v6_0_0_retry_runtime_lock_foundation.py`双方の`run_main_with_argv()`ヘルパーを、`run_retry_runtime.time.sleep`の直接monkeypatchから、`run_retry_runtime.RetryRuntimeShutdown`クラス自体をFake（`_FakeShutdown`）へ差し替える方式へ変更した（本Releaseの新規テストと同じ方式）。`_FakeShutdown.interruptible_sleep()`が従来の`sleep_fn`（`_make_counting_sleep()`が返す関数）へそのまま委譲するため、テスト意図・カバレッジ・Assertion・テストシナリオはいずれも変更していない（v5.9.0テスト13のみ、確認対象の文字列リテラルを`sleep_fn=time.sleep`から`sleep_fn=shutdown.interruptible_sleep`へ実装詳細の変更に追従して更新した）。実測の結果、`tests/test_e2e_v5_9_0_*.py`：**64/64 PASS**（元の記録どおり）、`tests/test_e2e_v6_0_0_*.py`：**43/43 PASS**（元の記録どおり）と、いずれもクラッシュなく完走し、元のPASS件数が回復したことを確認した
- **今後の対応**：不要（本エントリで解消済み）

---

## [v6.8.0] - 2026-07-15 ★ Retry Notification CLI Report Wiring Foundation

### Added

- 新規スクリプト`scripts/show_retry_notification.py`：v6.3.0（Metrics）〜v6.7.0（Notification
  Message）の5パッケージを初めて連続実行し、人間可読なReportとして標準出力へ表示するRead Only
  CLI。新規`src/`パッケージは追加していない
  - `RetryNotificationCliReport`（frozen dataclass、`scripts.show_retry_notification`モジュール
    固有のPublic Model。`metrics` / `health_report` / `alert` / `notification_decision` /
    `message`の5フィールドのみ、`src/*`のPublic APIには追加しない）
  - `build_report(log_path: Path) -> RetryNotificationCliReport`：
    `RetryRuntimeLogReader → RetryMetricsCalculator → RetryHealthEvaluator →
    RetryAlertEvaluator → RetryNotificationEvaluator → RetryNotificationMessageBuilder`
    をCLIスクリプト内で直接Composition
  - `format_report(report) -> str`：Pure Function。固定タイトル・区切り線（`"=" * 50`）・
    Metrics/Health/Alert/Notification/Messageの5セクション・Metrics4項目
    （`cycle_count` / `period_start` / `period_end` / `enqueue_success_ratio`）のみを表示
  - `main(argv: list[str] | None = None) -> int`：`--log-path`のみを独自CLI引数とする
- `tests/test_e2e_v6_8_0_retry_notification_cli_report_wiring_foundation.py`新規作成
  （30シナリオ・197アサーション）
- `docs/design/retry_notification_cli_report_wiring_foundation.md`新規作成：Architecture
  Design・Test Design（Changes Required×2を経て3回目Approved）・Code Review指摘反映の経緯を含む

### Architecture／Behavior

- CLIスクリプト内直接Composition：5コンポーネントはいずれもStateless（内部状態を持たない）
  ため、`RetryCompositionRoot`への配線を経ずCLIスクリプトが独自にインスタンスを生成しても
  状態の重複・不整合は発生しない。将来Runtime Integrationが同じコンポーネントを配線する
  場合も、独立した呼び出し元として競合しない
- `RetryNotificationStatus.NOTIFY`の場合のみ`RetryNotificationMessageBuilder.build()`を
  呼び出し、`NO_NOTIFICATION`の場合はMessage Builderを呼び出さず`message=None`とする。
  既存`RetryNotificationMessageBuilder`へのNO_NOTIFICATION対応追加は行っていない
- 未対応の`RetryNotificationStatus`相当値は、既存5パッケージと同型の網羅分岐＋フォールバック
  禁止パターンに従い`ValueError`を送出する（構造上到達不能な防御的分岐）
- Exit Code Policy：正常処理（NOTIFY／NO_NOTIFICATION問わず）は0、`OSError`（ログファイル
  読取不能）／`ValueError`（未対応値）は1、argparse構文エラーは標準のSystemExit 2。
  `except Exception`は使用せず、想定済みエラー（`OSError` / `ValueError`）のみを`main()`で
  捕捉しTracebackを表示しない。それ以外の例外は捕捉せずPython標準の伝播に委ねる
  （`RuntimeError`等が握り潰されないことを新規E2Eで確認済み）
- Reader由来の`WARNING:`（既存`RetryRuntimeLogReader`契約、行単位のJSONパース失敗時）と
  CLI由来の`[ERROR]`（`main()`が捕捉した`OSError` / `ValueError`）は明確に区別する
- `--log-path`のみを独自CLI引数とし、既定値`_DEFAULT_LOG_PATH`はスクリプト位置基準
  （`_PROJECT_ROOT = Path(__file__).parent.parent`）で、Current Working Directoryに依存しない
- 分類はArchitecture Release。新規Public API・CLI Entry Pointから5パッケージへの新規依存
  方向の確立を伴うため
- 対象外（今回は未実装）：Retry Notification Channel Foundation、Retry Notification
  Delivery／Sender Foundation、実送信（Slack／メール等）、Network I/O、Runtime／Scheduler
  Integration、`RetryCompositionRoot`配線、Severity-aware Message、Suppression／
  Deduplication／Rate Limit、JSON出力、`.env` / `python-dotenv`（同設計書8章）
- `RetryRuntimeLock` / `RetryRuntimeShutdown` / `RetryRuntimeLoop` / `RetryRuntimeOrchestrator` /
  `RetryManager`（`retry_engine`）/ `RetryCompositionRoot` / `RetryRuntimeCycleLogger`、
  `src/retry_metrics/` / `src/retry_monitoring/` / `src/retry_alert/` / `src/retry_notification/` /
  `src/retry_notification_message/`、`scripts/run_retry_runtime.py`はいずれも無改修。本Release
  におけるproduction codeの変更は、新規スクリプト`scripts/show_retry_notification.py`の追加のみ
- 新規Known Issueなし

### Tested

- `tests/test_e2e_v6_8_0_retry_notification_cli_report_wiring_foundation.py`：30シナリオ・
  197アサーション・197/197 PASS（終了コード0、意図しない警告なし、Tracebackなし）
- 既存回帰確認（いずれもベースラインと同一件数、新規差分なし）：
  - `tests/test_e2e_v5_9_0_*.py`：64/64 PASS
  - `tests/test_e2e_v6_0_0_*.py`：43/43 PASS
  - `tests/test_e2e_v6_1_0_*.py`：44/44 PASS
  - `tests/test_e2e_v6_2_0_*.py`：64/64 PASS
  - `tests/test_e2e_v6_3_0_*.py`：174/174 PASS
  - `tests/test_e2e_v6_4_0_*.py`：171/171 PASS
  - `tests/test_e2e_v6_5_0_*.py`：131/131 PASS
  - `tests/test_e2e_v6_6_0_*.py`：135/135 PASS
  - `tests/test_e2e_v6_7_0_*.py`：117/117 PASS
- Regression合計：943/943 PASS。全Suite終了コード0、ベースライン差なし、警告なし
- 新規E2E（197）＋Regression（943）＝1140/1140 PASS
- Test Review：1回目「Changes Required」（Counter Fakeの可観測性・`main(None)`実行・
  `sys.modules`未登録・ratio計算式の確認不足・Scenario数の定義不整合）、2回目「Changes
  Required」（Fake戻り値と正式Message確認の両立不能）、3回目「Approved」。Code Review
  「Approved」（Output Contractの検証精度・sys.modules復元の堅牢性に関する軽微な指摘を
  E2E修正で解消、196→197アサーション、production code無改修）
- 本Releaseによる新規Known Issue：なし。既存最新Known Issueは`[KI-29]`のまま（解消済み）

### Scope

- Runtime Wiringなし・実送信なし・Channel／Senderなし・外部I/Oなし・既存production code無改修

---

## [v6.7.0] - 2026-07-15 ★ Retry Notification Message Foundation

### Added

- 新規パッケージ`src/retry_notification_message/`：v6.6.0が生成する`RetryNotificationDecision`
  **のみ**を入力として受け取り、固定の通知Message Value Object（`RetryNotificationMessage`）を
  構築するだけのValue Building Only Foundation。判定（Judgment）は一切行わない。
  `RetryNotificationMessage`（frozen dataclass、`body`のみ保持）・`RetryNotificationMessageBuilder`
  （`build(decision) -> RetryNotificationMessage`、Stateless）の2コンポーネントで構成
  - `src/retry_notification_message/__init__.py`
  - `src/retry_notification_message/retry_notification_message.py`
  - `src/retry_notification_message/retry_notification_message_builder.py`
- 固定対応表（Design Contract）：`NOTIFY → RetryNotificationMessage(body="Retry Runtimeで通知対象の
  状態が検出されました。詳細を確認してください。")` / `NO_NOTIFICATION → ValueError`（Message生成
  契約への違反として明示的に失敗させる。「評価失敗」とは異なる） / 未対応Status相当値 → `ValueError`
- `tests/test_e2e_v6_7_0_retry_notification_message_foundation.py`新規作成（21シナリオ・
  117アサーション）
- `docs/design/retry_notification_message_foundation.md`新規作成：Architecture Design・ChatGPT
  Architecture Review（1回目「Changes Required」・指摘反映・2回目「Approved」）・Design Freeze・
  Test Review・Code Reviewの経緯を含む

### Architecture／Behavior

- `RetryNotificationMessage`は`body`のみを保持するImmutable（frozen dataclass）。`RetryAlert` /
  `RetryAlertLevel` / `RetryNotificationDecision` / `RetryNotificationStatus` / `title` / `channel` /
  `timestamp` / `reason`はいずれも保持・複製しない。重大度（WARNING/CRITICAL）が必要な将来の消費者
  は、呼び出し元が保持する元の`RetryAlert`を参照する（v6.6.0のTechnical Debt方針を継続）
- `RetryNotificationMessageBuilder`は`RetryNotificationDecision`のみを入力とするStateless Pure
  Function。`RetryAlert` / `RetryAlertLevel`は一切参照しない。`RetryAlertLevel.WARNING` /
  `CRITICAL`はいずれも`NOTIFY`へ収束するため区別できず、共通の固定Messageを生成する
- `retry_notification_message`が唯一importする自作パッケージは`retry_notification`のみ。
  `retry_alert` / `retry_monitoring` / `retry_metrics` / Runtime系 / `RetryManager` / Logger /
  CLI（`scripts/`） / 外部ライブラリはいずれもimportしない。`retry_notification`側（`__init__.py`
  含む全productionモジュール）も`retry_notification_message`をimportしない（逆依存禁止）。これら
  の契約は新規E2Eテストのソースコード走査（AST解析）で機械的に保証した
- 分類はArchitecture Release。新規パッケージ追加（Layer変更）に加え`retry_notification`への新規
  import（Dependency変更）を伴うため
- **Architecture Reviewの経緯**：初版では入力を`RetryAlert`単独・Domain Modelを`level`保持・
  Dependencyを`retry_alert`直接依存として提示したが、1回目のArchitecture Review「Changes
  Required」で「Message層がNotification Decisionを迂回する」「重大度非保持の責務境界を実質的に
  変更する」「直前Layerだけへ依存する既存Architectureの一貫性を崩す」との指摘を受け、入力を
  `RetryNotificationDecision`単独・Domain Modelを`body`のみ・Dependencyを`retry_notification`
  のみへそれぞれ修正し、2回目のArchitecture Reviewで「Approved」となった
- 対象外（今回は未実装）：実際の通知送信（Slack／メール等）、チャネル選択、Suppression／重複排除／
  レート制限、Recovery通知、履歴・永続化、Runtime Wiring、Composition Root Wiring、CLI表示、
  WARNING／CRITICAL別Message（同設計書19章・20章）
- `RetryRuntimeLock` / `RetryRuntimeShutdown` / `RetryRuntimeLoop` / `RetryRuntimeOrchestrator` /
  `RetryManager`（`retry_engine`）/ `RetryCompositionRoot` / `RetryRuntimeCycleLogger`
  （`retry_runtime_logging`）、`src/retry_metrics/` / `src/retry_monitoring/` / `src/retry_alert/` /
  `src/retry_notification/`はいずれも無改修。本Releaseにおけるproduction codeの変更は、新規
  パッケージ`src/retry_notification_message/`の追加のみ
- 新規Known Issueなし

### Tested

- `tests/test_e2e_v6_7_0_retry_notification_message_foundation.py`：21シナリオ・117アサーション・
  117/117 PASS（終了コード0、警告なし）
- 既存回帰確認（いずれもベースラインと同一件数、新規差分なし）：
  - `tests/test_e2e_v5_9_0_*.py`：64/64 PASS
  - `tests/test_e2e_v6_0_0_*.py`：43/43 PASS
  - `tests/test_e2e_v6_1_0_*.py`：44/44 PASS
  - `tests/test_e2e_v6_2_0_*.py`：64/64 PASS
  - `tests/test_e2e_v6_3_0_*.py`：174/174 PASS
  - `tests/test_e2e_v6_4_0_*.py`：171/171 PASS
  - `tests/test_e2e_v6_5_0_*.py`：131/131 PASS
  - `tests/test_e2e_v6_6_0_*.py`：135/135 PASS
- Regression合計：826/826 PASS。全Suite終了コード0、ベースライン差なし、警告なし
- 新規E2E（117）＋Regression（826）＝943/943 PASS
- 本Releaseによる新規Known Issue：なし。既存最新Known Issueは`[KI-29]`のまま（解消済み）

### Scope

- Runtime Wiringなし・CLI Wiringなし・Channel／Senderなし・外部I/Oなし・既存production code無改修

---

## [v6.6.0] - 2026-07-15 ★ Retry Notification Foundation

### Added

- 新規パッケージ`src/retry_notification/`：v6.5.0が生成する`RetryAlert`**のみ**を入力として
  受け取り、通知要否（`RetryNotificationDecision`）を判定するだけのJudgment Only Foundation。
  `RetryNotificationStatus`（`NO_NOTIFICATION` / `NOTIFY`のEnum）・`RetryNotificationDecision`
  （判定結果、Immutable、`status`のみ保持）・`RetryNotificationEvaluator`（判定、Stateless Pure
  Function）の3コンポーネントで構成
- 変換規則（Design Contract）：`NONE → NO_NOTIFICATION` / `WARNING → NOTIFY` /
  `CRITICAL → NOTIFY`の固定対応表に従って変換するのみで、閾値判定は行わない
- `tests/test_e2e_v6_6_0_retry_notification_foundation.py`新規作成（20テストシナリオ・
  135アサーション。ChatGPT Code Review指摘反映：①`retry_alert`の逆依存検査へ`__init__.py`を
  追加、②AST解析による親パッケージ方向の相対import（level>=2）の検出を追加、③Fail Fast
  テストの重複アサーションを1シナリオへ統合、④package rootの`__all__`を直接検証するテストを
  追加）
- `docs/design/retry_notification_foundation.md`新規作成：Architecture Design・ChatGPT
  Architecture Review（1回目「Request Changes」・2回目「Approve with Minor Corrections」）・
  Design Freezeの経緯を含む

### Architecture／Behavior

- `RetryNotificationStatus.NO_NOTIFICATION`は「`RetryNotificationEvaluator.evaluate()`が
  正常に実行・完了した結果、入力された`RetryAlert`が通知対象となる状態ではないことを表す
  正常系の明示値」。評価失敗・入力不足・未対応値・処理スキップ・Evaluator未実行のいずれも
  意味しない（同設計書9章）
- `RetryNotificationDecision`はfrozen dataclassであり、`status`のみを保持する。`RetryAlert`・
  `RetryAlertLevel`は保持・複製しない
- `RetryNotificationEvaluator`は`RetryAlert`のみを入力とするStateless Pure Function。閾値判定は
  行わない
- 未対応の`RetryAlertLevel`はフォールバックせず`ValueError`を送出する（Fail Fast契約）
- `retry_notification`が唯一importする自作パッケージは`retry_alert`のみ。`retry_monitoring` /
  `retry_metrics` / Runtime系 / `RetryManager` / Logger / CLI（`scripts/`） / 外部ライブラリは
  いずれもimportしない。`retry_alert`側（`__init__.py`含む全productionモジュール）も
  `retry_notification`をimportしない（逆依存禁止）。これらの契約は新規E2Eテストのソースコード
  走査（AST解析。level>=2の親パッケージ方向の相対importも検出対象、ChatGPT Code Review指摘
  反映）で機械的に保証した
- 外部I/O・実送信・Runtime Wiring・Composition Root Wiringはいずれも行わない
- 分類はArchitecture Release。新規パッケージ追加（Layer変更）に加え`retry_alert`への新規import
  （Dependency変更）を伴うため（`docs/design/retry_notification_foundation.md` 4章）
- 対象外（今回は未実装）：実際の通知送信（Slack／メール等）、Message生成、Channel選択、
  Suppression／重複排除／レート制限、Recovery通知、履歴・永続化、Runtime Wiring、
  Composition Root Wiring、CLI表示（同設計書14章・15章）
- `RetryRuntimeLock` / `RetryRuntimeShutdown` / `RetryRuntimeLoop` / `RetryRuntimeOrchestrator` /
  `RetryManager`（`retry_engine`）/ `RetryCompositionRoot` / `RetryRuntimeCycleLogger`
  （`retry_runtime_logging`）、`src/retry_metrics/` / `src/retry_monitoring/` / `src/retry_alert/`
  はいずれも無改修。本Releaseにおけるproduction codeの変更は、新規パッケージ
  `src/retry_notification/`の追加のみ
- 新規Known Issueなし

### Tested

- `tests/test_e2e_v6_6_0_retry_notification_foundation.py`: 20シナリオ・135アサーション・
  135/135 PASS（終了コード0、警告なし）
- 既存回帰確認（いずれもベースラインと同一件数、新規差分なし）：
  - `tests/test_e2e_v5_9_0_*.py`：64/64 PASS
  - `tests/test_e2e_v6_0_0_*.py`：43/43 PASS
  - `tests/test_e2e_v6_1_0_*.py`：44/44 PASS
  - `tests/test_e2e_v6_2_0_*.py`：64/64 PASS
  - `tests/test_e2e_v6_3_0_*.py`：174/174 PASS
  - `tests/test_e2e_v6_4_0_*.py`：171/171 PASS
  - `tests/test_e2e_v6_5_0_*.py`：131/131 PASS
- Regression合計：691/691 PASS。全Suite終了コード0、ベースライン差なし、警告なし
- 本Releaseによる新規Known Issue：なし。既存最新Known Issueは`[KI-29]`のまま

---

## [v6.5.0] - 2026-07-14 ★ Retry Alert Foundation

### Added

- 新規パッケージ`src/retry_alert/`：v6.4.0が生成する`RetryHealthReport`**のみ**を入力として
  受け取り、アラートの度合い（`RetryAlert`）を判定するだけのJudgment Only Foundation。
  `RetryAlertLevel`（`NONE` / `WARNING` / `CRITICAL`のEnum）・`RetryAlert`（判定結果、Immutable、
  `level`のみ保持）・`RetryAlertEvaluator`（判定、Stateless Pure Function）の3コンポーネントで構成
- 変換規則（Design Contract）：`HEALTHY → NONE` / `DEGRADED → WARNING` / `UNHEALTHY → CRITICAL`の
  固定対応表に従って変換するのみで、閾値判定は行わない
- `tests/test_e2e_v6_5_0_retry_alert_foundation.py`新規作成（15テストシナリオ・131アサーション。
  Code Review指摘反映：既存コンポーネントの無改修確認（Zero Diff、`git diff --quiet`ベース）は
  恒久的なE2Eテストに含めず、Release Reviewにおいて`git diff --name-status` / `git status --short`
  で個別に確認する方針へ変更した）

### Note

- **Judgment Only Foundationである。** Runtime・Metrics・Monitoring側へ一切フィードバックを行わない
  （Retry Queueの更新・`RetryManager`等の変更・Runtime Pipeline各コンポーネントの変更・Schedulerへの
  通知・Retry実行可否の判断・通知の送信のいずれも行わない、`docs/design/retry_alert_foundation.md`
  1章）
- **`RetryRuntimeLock` / `RetryRuntimeShutdown` / `RetryRuntimeLoop` / `RetryRuntimeOrchestrator` /
  `RetryManager`（`retry_engine`）/ `RetryCompositionRoot` / `RetryRuntimeCycleLogger`
  （`retry_runtime_logging`）および`src/retry_metrics/` / `src/retry_monitoring/`はいずれも無改修。**
  本Releaseにおけるproduction codeの変更は、新規パッケージ`src/retry_alert/`の追加のみ。既存の
  `src/`配下のコードは無改修（Code Review指摘反映：ドキュメント・テストファイルの追加/更新は
  別途`docs/CHANGELOG.md`の他項目・`tests/`欄で記載する）
- **`retry_alert`が唯一importする自作パッケージは`retry_monitoring`（`RetryHealthReport` /
  `RetryHealthStatus`型の参照のみ）。** `retry_metrics`・Runtime系パッケージ・Loggerはいずれも
  importしない。`retry_monitoring`側も`retry_alert`をimportしない（逆依存禁止）。これらの契約は
  新規E2Eテストのソースコード走査（import文の検出、`open(` / `pathlib.Path` / `.jsonl`という
  文字列リテラルの不在確認）で機械的に保証した
- **`RetryAlertLevel.NONE`は「健康状態の評価は正常に完了したが、通知対象となるAlertは存在しない」
  ことを表す正常系の明示値。** 評価失敗・データ不足・不明な状態・処理スキップのいずれも意味しない。
  将来のNotification実装は`level == NONE`の場合に通知を送信してはならない（ChatGPT Architecture
  Review「条件付きPASS」指摘反映、同設計書4.2節）
- **未対応のStatus（既知の3値以外）はフォールバックせず`ValueError`を送出する（Fail Fast契約）。**
  `RetryHealthStatus`拡張への追従漏れという契約違反を、あたかも正常系（アラートなし）であるかの
  ように隠蔽しないための設計判断（ChatGPT Architecture Review「条件付きPASS」指摘反映、同設計書
  4.3節）
- **`RetryAlertEvaluator`はStateless Pure Function。** 同一の`RetryHealthReport`を渡した場合、常に
  同一の`RetryAlert`（既知Statusの場合）または同一の例外（未対応Statusの場合）を返すことを新規
  E2Eテストで確認した
- 分類はArchitecture Release。新規パッケージ追加（Layer変更）に加え`retry_monitoring`への新規import
  （Dependency変更）を伴うため（`docs/design/retry_alert_foundation.md` 表紙）
- 対象外（今回は未実装）：Notification本体（Slack／メール等への実際の通知）、CLI表示・
  ダッシュボード化、アラートの抑制・重複排除・レート制限、アラート履歴の永続化、
  `RetryCompositionRoot`への配線。データフロー（実行順序）は`Alert → Notification`だが、import依存
  方向はこれと逆向きであり、`retry_notification → retry_alert`（NotificationがAlertの`RetryAlert`型を
  importする方向）が許可される正しい依存、`retry_alert → retry_notification`（Alertが逆にNotification
  をimportする方向）が禁止される依存であると設計書で確定済み（Code Review指摘反映、同設計書2.3節）
- 新規Known Issueなし

### Tested

- `tests/test_e2e_v6_5_0_retry_alert_foundation.py`: 131/131 PASS
  （`RetryAlertLevel`の3値確認、`RetryAlert`のImmutability・保持フィールドが`level`のみである
  ことの確認、変換規則の網羅的確認（`HEALTHY→NONE` / `DEGRADED→WARNING` / `UNHEALTHY→CRITICAL`）、
  未対応Statusに対する`ValueError`送出確認（フォールバックしないことの確認を含む）、
  `RetryAlertLevel.NONE`がTotal Functionとして返ることの確認、Stateless Pure Function確認
  （同一Reportへの複数回呼び出し・複数インスタンス間での結果一致）、Dependency Rule確認
  （`retry_metrics`/Runtime/Logger系パッケージへの非依存・ファイルI/O関連コードの不在・
  `retry_monitoring`からの逆依存不在）、`RetryRuntimeLogReader` → `RetryMetricsCalculator` →
  `RetryHealthEvaluator` → `RetryAlertEvaluator`の統合確認。既存コンポーネントの無改修確認
  （Zero Diff）はCode Review指摘によりE2Eテストから削除し、下記Release Reviewの`git diff
  --name-status` / `git status --short`で別途確認する
- 既存回帰確認（いずれもベースラインと同一件数、新規差分なし）：
  - `tests/test_e2e_v5_9_0_*.py`：64/64 PASS
  - `tests/test_e2e_v6_0_0_*.py`：43/43 PASS
  - `tests/test_e2e_v6_1_0_*.py`：44/44 PASS
  - `tests/test_e2e_v6_2_0_*.py`：64/64 PASS
  - `tests/test_e2e_v6_3_0_*.py`：174/174 PASS
  - `tests/test_e2e_v6_4_0_*.py`：171/171 PASS
- 本Releaseによる新規Known Issue：なし

---

## [v6.4.0] - 2026-07-14 ★ Retry Monitoring Foundation

### Added

- 新規パッケージ`src/retry_monitoring/`：v6.3.0が生成する`RetryMetricsSnapshot`**のみ**を入力として
  受け取り、健全性ステータス（`RetryHealthReport`）を判定するだけのJudgment Only Foundation。
  `RetryHealthStatus`（`HEALTHY` / `DEGRADED` / `UNHEALTHY`のEnum）・`RetryHealthThresholds`
  （閾値、Immutable Value Object／Domain Value）・`RetryHealthReport`（判定結果、Immutable）・
  `RetryHealthEvaluator`（判定、Stateless Pure Function）の4コンポーネントで構成
- 判定基準：`enqueue_success_ratio`が`unhealthy_below`（デフォルト0.5）未満なら`UNHEALTHY`、
  `degraded_below`（デフォルト0.8）未満なら`DEGRADED`、それ以外は`HEALTHY`。`ratio`が`None`
  （対象サイクル0件等で算出不能）の場合は閾値判定を行わず`HEALTHY`を返す
- `tests/test_e2e_v6_4_0_retry_monitoring_foundation.py`新規作成（20テストシナリオ・171アサーション）

### Note

- **Judgment Only Foundationである。** Runtime・Metrics側へ一切フィードバックを行わない（Retry
  Queueの更新・`RetryManager`等の変更・Runtime Pipeline各コンポーネントの変更・Schedulerへの通知・
  Retry実行可否の判断・通知の送信のいずれも行わない、`docs/design/retry_monitoring_foundation.md`
  4.1節）
- **`RetryRuntimeLock` / `RetryRuntimeShutdown` / `RetryRuntimeLoop` / `RetryRuntimeOrchestrator` /
  `RetryManager`（`retry_engine`）/ `RetryCompositionRoot` / `RetryRuntimeCycleLogger`
  （`retry_runtime_logging`）および`src/retry_metrics/`はいずれも無改修。** 本Releaseの変更対象は
  新規パッケージ`src/retry_monitoring/`のみ
- **`retry_monitoring`が唯一importする自作パッケージは`retry_metrics`（`RetryMetricsSnapshot`型の
  参照のみ）。** Runtime系パッケージ・Loggerはいずれもimportせず、`.run/retry_runtime_log.jsonl`
  というファイルパスの存在自体を一切知らない。`retry_metrics`側も`retry_monitoring`をimportしない
  （逆依存禁止）。これらの契約は新規E2Eテストのソースコード走査（import文の検出、`open(` /
  `pathlib.Path` / `.jsonl`という文字列リテラルの不在確認）で機械的に保証した
- **`RetryHealthThresholds`はConfigではなくDomain Value。** `frozen=True`のdataclassとして実装し、
  Foundationは固定値を保持する責務のみを持つ。`RetryHealthEvaluator`はThresholdを自ら生成せず、
  Constructor Injectionで外部から受け取るか未指定時はDefault Thresholdを使用するのみとした
  （Architecture Review反映、`docs/design/retry_monitoring_foundation.md` 6.5節 Architecture
  Decision AD-1・AD-2）
- **`RetryHealthReport`はRelease 6.4では`status`のみを保持する。** `reason` / `warnings` /
  `details`（または`violations`）等の診断情報は将来拡張の対象とし、本Releaseでは追加実装しない
  （Architecture Review反映、同設計書11.5節）
- **`RetryHealthEvaluator`はStateless Pure Function。** 同一の`RetryMetricsSnapshot`を渡した場合、
  常に同一の`RetryHealthReport`を返すことを新規E2Eテストで確認した（Architecture Review反映）
- 分類はArchitecture Release。新規パッケージ追加（Layer変更）に加え`retry_metrics`への新規import
  （Dependency変更）を伴うため（`docs/design/retry_monitoring_foundation.md` 0章）
- 対象外（今回は未実装）：`scripts/`エントリーポイント・CLI表示、Alert本体（Slack／メール等への
  通知）、閾値の外部設定化・動的変更、複数指標に基づく総合判定、`RetryHealthReport`への
  `reason`/`warnings`/`details`追加。Retry Alert Foundationは`Monitoring → Alert`の一方向依存のみを
  許可する境界を設計書で確定済み（同設計書11.1節）
- 新規Known Issueなし

### Tested

- `tests/test_e2e_v6_4_0_retry_monitoring_foundation.py`: 171/171 PASS
  （`RetryHealthStatus`の3値確認、`RetryHealthThresholds`のデフォルト値・Immutability確認、
  `RetryHealthReport`のImmutability・保持フィールドが`status`のみであることの確認、
  `RetryHealthEvaluator`の閾値境界値確認（`ratio=None` / 境界値0.8・0.5前後 / カスタム
  Thresholds / デフォルトThreshold）、Stateless Pure Function確認（同一Snapshotへの複数回呼び出し・
  複数インスタンス間での結果一致）、Dependency Rule確認（Runtime/Logger系パッケージへの非依存・
  ファイルI/O関連コードの不在・`retry_metrics`からの逆依存不在）、`RetryRuntimeLogReader` →
  `RetryMetricsCalculator` → `RetryHealthEvaluator`の統合確認、Runtime Pipeline・`retry_metrics`
  計9コンポーネントの無改修確認）
- 既存回帰確認（いずれもベースラインと同一件数、新規差分なし）：
  - `tests/test_e2e_v5_9_0_*.py`：64/64 PASS
  - `tests/test_e2e_v6_0_0_*.py`：43/43 PASS
  - `tests/test_e2e_v6_1_0_*.py`：44/44 PASS
  - `tests/test_e2e_v6_2_0_*.py`：64/64 PASS
  - `tests/test_e2e_v6_3_0_*.py`：174/174 PASS
- 本Releaseによる新規Known Issue：なし

---

## [v6.3.0] - 2026-07-14 ★ Retry Metrics Foundation

### Added

- 新規パッケージ`src/retry_metrics/`：`.run/retry_runtime_log.jsonl`（v6.2.0が書き込むJSON Linesログ）
  を読み取り、集計値（`RetryMetricsSnapshot`）を計算するだけのRead Only Foundation。
  `RetryRuntimeLogRecord`（1行分の値オブジェクト）・`RetryRuntimeLogReader`（読み取り専用）・
  `RetryMetricsCalculator`（集計、Stateless）・`RetryMetricsSnapshot`（Immutable、frozen dataclass）
  の4コンポーネントで構成
- `RetryMetricsSnapshot`は、対象サイクル数（`cycle_count`）・記録期間（`period_start` /
  `period_end`、timestampのmin/max）・dry_run実行サイクル数・各段階（Enqueue/Scheduler/Execution/
  Removal/Cleanup/TerminalCleanup/History）の合計値・Enqueue段階の成功率（`enqueue_success_ratio`
  = `enqueue_enqueued_total / enqueue_scanned_total`）を保持する
- `tests/test_e2e_v6_3_0_retry_metrics_foundation.py`新規作成（27テストシナリオ・174アサーション）

### Note

- **Read Only Foundationである。** Retry Runtimeへ一切フィードバックを行わない（Retry Queueの
  更新・`RetryManager` / `RetryRuntimeOrchestrator` / `RetryRuntimeLoop` / `RetryRuntimeShutdown` /
  `RetryRuntimeLock`の変更・Schedulerへの通知・Retry実行可否の判断・Alert判定・Monitoring Policyの
  いずれも行わない、`docs/design/retry_metrics_foundation.md` 4.1節）
- **`RetryRuntimeLock` / `RetryRuntimeShutdown` / `RetryRuntimeLoop` / `RetryRuntimeOrchestrator` /
  `RetryManager`（`retry_engine`）/ `RetryCompositionRoot` / `RetryRuntimeCycleLogger`
  （`retry_runtime_logging`）はいずれも無改修。** 本Releaseの変更対象は新規パッケージ
  `src/retry_metrics/`のみ
- **`retry_metrics`は他のどの`retry_*`パッケージもimportしない。** `.run/retry_runtime_log.jsonl`の
  ファイルパスとJSON Schemaの「形」のみを契約として扱う、型参照ではなく契約（shape一致）による
  疎結合を採用した
- **`RetryMetricsSnapshot`はImmutable。** 生成後は変更されず、将来のRetry Monitoring Foundationは
  これを参照するだけで更新しない
- 分類はArchitecture Release。新規パッケージ追加（Layer変更）に該当するため、当初想定されていた
  Fast Track Releaseから変更した（`docs/design/retry_metrics_foundation.md` 0章）
- 対象外（今回は未実装）：`scripts/`エントリーポイント・CLI表示、Retry Monitoring Foundation本体
  （閾値判定・Alert）、JSON Schema拡張（真の成功率・試行回数分布の算出）、Queue滞留時間の算出
  （`RetryQueueManager`がenqueue時刻を保持しないため算出不能）。Retry Monitoring Foundationは
  `Metrics → Monitoring → Alert`の一方向依存のみを許可する境界を設計書で確定済み（`docs/design/
  retry_metrics_foundation.md` 11.1節）
- 新規Known Issueなし

### Tested

- `tests/test_e2e_v6_3_0_retry_metrics_foundation.py`: 174/174 PASS
  （`RetryRuntimeLogRecord` / `RetryMetricsSnapshot`のImmutability確認、存在しないログファイルへの
  `read()`が空リストを返すことの確認、正常なJSONL・壊れたJSON行・フィールド欠落行・空行それぞれの
  読み取り挙動確認、ファイル自体が読めない場合に`OSError`を送出すること（fail-fast）の確認、
  `calculate([])`が`cycle_count=0`のSnapshotを返すことの確認、各合計フィールド・
  `enqueue_success_ratio`・`period_start`/`period_end`（min/max）・`dry_run_cycle_count`の計算確認、
  他`retry_*`パッケージへの非依存確認、`RetryRuntimeCycleLogger`が書き込む実際のJSONL形式を
  読み取り集計まで一貫して行える統合確認、Runtime Pipeline関連8コンポーネントの無改修確認）
- 既存回帰確認（いずれもベースラインと同一件数、新規差分なし）：
  - `tests/test_e2e_v5_9_0_*.py`：64/64 PASS
  - `tests/test_e2e_v6_0_0_*.py`：43/43 PASS
  - `tests/test_e2e_v6_1_0_*.py`：44/44 PASS
  - `tests/test_e2e_v6_2_0_*.py`：64/64 PASS
- 本Releaseによる新規Known Issue：なし

---

## [v6.2.0] - 2026-07-14 ★ Structured Loop Logging Foundation

### Added

- 新規パッケージ`src/retry_runtime_logging/`（`RetryRuntimeCycleLogger`）：Retry Runtimeの1サイクル
  分の実行結果を、JSON Lines形式で1レコードとしてログファイル（`.run/retry_runtime_log.jsonl`）へ
  追記するだけの独立コンポーネント。記録内容はサイクル番号・タイムスタンプ（ISO8601、UTC）・
  `--dry-run`指定有無・`RetryRuntimeCycleResult`由来の各件数（Enqueue/Scheduler/Execution/Removal/
  Cleanup/TerminalCleanup/History）。ログ書き込みに失敗した場合は例外を送出せず、stderrへ
  `WARNING: Failed to write runtime log: ...`を出力したうえでRetry Runtime本体の処理を継続する
  （ベストエフォート、Runtime Failure Policy）
- `scripts/run_retry_runtime.py`：`RetryRuntimeCycleLogger`を構築し、`run_cycle()`クロージャ内で
  `orchestrator.run_once()`の結果を得るたびに`log_cycle()`を呼び出す配線を追加。サイクル番号
  （`cycle_count`）はクロージャのローカル変数として保持し、`RetryRuntimeLoop`のStateless性は
  維持した
- `docs/design/retry_runtime_structured_loop_logging_foundation.md`新規作成（Architecture Design・
  比較検討（Stale Lock Recovery Foundationとの比較）・Architecture Review反映事項（Runtime Failure
  Policy・JSON Schema固定）を含む）
- `tests/test_e2e_v6_2_0_structured_loop_logging_foundation.py`新規作成（25テストシナリオ・
  64アサーション）

### Note

- **`RetryRuntimeLock` / `RetryRuntimeShutdown` / `RetryRuntimeLoop` / `RetryRuntimeOrchestrator` /
  `RetryManager`（`retry_engine`）/ `RetryCompositionRoot`はいずれも無改修。** 本Releaseの変更対象は
  `src/retry_runtime_logging/`（新規）と`scripts/run_retry_runtime.py`の配線のみ
- **Runtime Pipeline（CLI → Lock → Shutdown → Loop → Orchestrator → RetryManager）の縦の実行順序は
  一切変更していない。** ログ出力は`run_cycle()`クロージャ内でのみ発生する横方向の追加であり、
  `RetryRuntimeLoop`のConstructor Injection（`run_once_fn` / `sleep_fn` / `should_continue_fn`）は
  無変更
- **JSON Schemaは本Releaseで固定した。** 将来の変更はフィールド追加のみを基本方針とし、既存
  フィールドの意味変更は行わない（`docs/design/retry_runtime_structured_loop_logging_foundation.md`
  1.3節）
- **ログ書き込み失敗はRetry Runtime本体を停止させない。** ディスク容量不足・権限エラー等の
  `OSError`は例外を送出せずstderrへWARNINGを出力するのみに留める。Exit Code Policy
  （`docs/design/retry_runtime_script_entry_point_foundation.md` 2.4節）とは区別する
- Architecture Design段階で「Stale Lock Recovery Foundation」との比較検討を行った。stale判定が
  `RetryRuntimeLock`の責務そのものに本質的に食い込み「Lockへの責務追加禁止」制約と構造的に
  衝突するため見送り、本Foundationを採用した（設計比較の詳細は設計書0.1節）
- 対象外（今回は未実装）：ログローテーション、Metrics集計・Dashboard化、ログ出力先の環境変数化、
  Stale Lock Recovery Foundation（いずれも将来Release候補または対象外。`docs/design/
  retry_runtime_structured_loop_logging_foundation.md` 6章 Out of Scope）
- 新規Known Issueなし

### Tested

- `tests/test_e2e_v6_2_0_structured_loop_logging_foundation.py`: 64/64 PASS
  （JSON Lines新規作成・append動作、全行JSONパース可能、必須フィールド網羅確認、cycle_numberの
  記録確認、dry_run True/False双方の記録確認、`RetryRuntimeCycleResult`由来の各件数の記録確認、
  書き込み失敗時に例外を送出せずstderrへWARNINGを出力し処理継続することの確認、他retry_*
  パッケージへの非依存確認、`scripts/run_retry_runtime.py`配線のソース確認、Fake経由での
  `--loop`実行時cycle_numberの連番確認・単発実行時1回のみ呼び出し確認・`--dry-run`伝播確認、
  `format_summary()`公開契約の無変更確認・出力内容へのログ関連文言非混入確認、主要コンポーネント
  の無改修確認）
- 既存回帰確認（いずれもベースラインと同一件数、新規差分なし）：
  - `tests/test_e2e_v5_5_0_*.py`：35/37 PASS（既存差分のみ、`[KI-27]`・`[KI-28]`。件数不変）
  - `tests/test_e2e_v5_6_0_*.py`：44/49 PASS（既存差分のみ。件数不変）
  - `tests/test_e2e_v5_7_0_*.py`：86/86 PASS（新規差分なし）
  - `tests/test_e2e_v5_8_0_*.py`：63/64 PASS（既存差分のみ、`[KI-27]`。件数不変）
  - `tests/test_e2e_v5_9_0_*.py`：64/64 PASS（`[KI-29]`解消後のベースラインを維持）
  - `tests/test_e2e_v6_0_0_*.py`：43/43 PASS（`[KI-29]`解消後のベースラインを維持）
  - `tests/test_e2e_v6_1_0_*.py`：44/44 PASS（Windows実機でのCtrl+Break確認含む）
- 本Releaseによる新規Known Issue：なし

---

## [v6.1.0] - 2026-07-14 ★ Graceful Shutdown Foundation

### Added

- 新規パッケージ`src/retry_runtime_shutdown/`（`RetryRuntimeShutdown`）：`--loop`実行中のRetry Runtimeに
  対するGraceful Shutdown（実行中サイクルは完了させたうえで、次のサイクルを開始せず終了する）を実現する
  独立コンポーネント。SIGINT・SIGTERM（POSIX）・SIGBREAK（Windows）へのハンドラ登録（`install()`/
  `uninstall()`、ベストエフォート）、`RetryRuntimeLoop`へそのまま渡せる`should_continue()`（フラグの否定を
  返す）、`interruptible_sleep()`（ポーリング間隔0.5秒単位で停止要求を確認しながら待機し、要求受信時は
  早期returnする）を提供する
- `scripts/run_retry_runtime.py`：`--loop`実行時のみ`RetryRuntimeShutdown`を生成・`install()`し、
  `RetryRuntimeLoop`への`sleep_fn` / `should_continue_fn`を`shutdown.interruptible_sleep` /
  `shutdown.should_continue`へ差し替え。既存の`except KeyboardInterrupt`はフェイルセーフとして維持。
  終了時、シグナルによる停止であれば`shutdown.signal_name`を含む終了メッセージを表示する
- `docs/design/retry_runtime_graceful_shutdown_foundation.md`新規作成（Architecture Design・
  Architecture Review反映事項3件（Shutdown State／Signal Registration-Handling分離／DIのみによる
  接続の明文化）を含む）
- `tests/test_e2e_v6_1_0_retry_runtime_graceful_shutdown_foundation.py`新規作成（32テストシナリオ・
  44アサーション。Windows実機でのCtrl+Break（`CTRL_BREAK_EVENT`）送出による実CLIサブプロセスの
  Graceful Shutdown確認を含む）

### Note

- **`RetryCompositionRoot` / `RetryRuntimeOrchestrator` / `RetryRuntimeLoop` / `RetryManager`
  （`retry_engine`）/ `RetryRuntimeLock`（v6.0.0）はいずれも無改修。** 本Releaseの変更対象は
  `src/retry_runtime_shutdown/`（新規）と`scripts/run_retry_runtime.py`の配線のみ
- **`RetryRuntimeLoop`と`RetryRuntimeShutdown`は互いの存在を一切知らない。** 両者は
  `RetryRuntimeLoop`が既に持っていた`should_continue_fn` / `sleep_fn`というDIシームのみで接続される
  （`RetryRuntimeLoop`自体への変更は不要だった）
- **シグナル受信時、実行中のサイクルを中断しない。** シグナルハンドラはフラグを立てるのみで例外を
  送出しないため、`run_once_fn()`実行中にシグナルを受けても現在のサイクルは最後まで完了する
- **待機（`sleep_fn`）はポーリング間隔（既定0.5秒）以内で早期returnする。** これにより、シグナル
  受信からプロセス終了までの間、旧来の`interval_seconds`（デフォルト60秒）を待たされることがなくなった
- **`import time`を`scripts/run_retry_runtime.py`から削除した。** `--loop`実行時の待機がすべて
  `RetryRuntimeShutdown.interruptible_sleep`経由になり、同ファイルが直接`time`モジュールを
  使用する箇所がなくなったための整理（Code Review対応）
- **Windowsでの強制終了（`taskkill /F`・タスクマネージャーの「タスクの終了」）は本機構の対象外。**
  OSの`TerminateProcess`を用いる強制終了はいかなるプロセスも検知・介入できないため、本機構は
  あくまで協調的な停止要求（Ctrl+C／Ctrl+Break／SIGTERM）への対応に限定される
- 対象外（今回は未実装）：単発実行時のシグナル処理、二重シグナルによる強制終了エスケープハッチ、
  Stale Lock Recovery、実際のバックグラウンド分離・Windows Service化（いずれも将来Release候補または
  対象外。`docs/design/retry_runtime_graceful_shutdown_foundation.md` 6章 Out of Scope）
- 新規Known Issue：`[KI-29]`（本Releaseの`sleep_fn`差し替えにより、`tests/test_e2e_v5_9_0_*.py` /
  `tests/test_e2e_v6_0_0_*.py`のLoop関連テストが実行不能になる）

### Tested

- `tests/test_e2e_v6_1_0_retry_runtime_graceful_shutdown_foundation.py`: 44/44 PASS
  （シグナル受信によるrequested/should_continue/signal_nameの変化、KeyboardInterruptが送出されない
  ことの確認、SIGBREAK対応、`interruptible_sleep()`の通常時待機・早期return、`install()`の
  べき等性・メインスレッド以外からのベストエフォート、他retry_*パッケージへの非依存、
  `RetryRuntimeLoop`とのDIのみによる非依存関係（双方向）、`scripts/run_retry_runtime.py`配線の
  ソース確認、Fake経由でのLoop正常終了・終了メッセージ確認、単発実行時に`RetryRuntimeShutdown`が
  生成されないことの確認、**Windows実機でのCtrl+Break送出による実CLIサブプロセスのGraceful
  Shutdown確認（exit code 0）**、主要コンポーネントの無改修確認（`RetryRuntimeLock`含む）、
  `format_summary()`公開契約の無変更確認）
- 既存回帰確認：
  - `tests/test_e2e_v5_5_0_*.py`：35/37 PASS（既存差分のみ、`[KI-27]`・`[KI-28]`。件数不変）
  - `tests/test_e2e_v5_6_0_*.py`：44/49 PASS（既存差分のみ。件数不変）
  - `tests/test_e2e_v5_7_0_*.py`：86/86 PASS（新規差分なし）
  - `tests/test_e2e_v5_8_0_*.py`：63/64 PASS（既存差分のみ、`[KI-27]`。件数不変）
  - `tests/test_e2e_v5_9_0_*.py`：実行不能（`[KI-29]`、新規）
  - `tests/test_e2e_v6_0_0_*.py`：テスト1〜12（22アサーション）PASS、テスト13以降は実行不能（`[KI-29]`、新規）
- 本Releaseによる新規Known Issue：`[KI-29]`

---

## [v6.0.0] - 2026-07-14 ★ Retry Runtime Lock Foundation（Daemon Foundation 前提）

### Added

- 新規パッケージ`src/retry_runtime_lock/`（`RetryRuntimeLock` / `RetryRuntimeLockError`）：
  同一Retry Runtimeプロセスの多重起動を防止するための、ファイル存在ベースの排他制御のみを行う
  独立コンポーネント。`os.open(O_CREAT | O_EXCL)`によるアトミックなロックファイル生成・
  自プロセスPIDの書き込み・`with`文（`__enter__` / `__exit__`）による自動解放を提供する
- `scripts/run_retry_runtime.py`：単発実行・`--loop`実行の全体を`with lock:`で包み、
  実行開始時に`<project_root>/.run/retry_runtime.lock`のロック取得を試みるよう変更。
  取得失敗時（＝別プロセスが実行中）は`RetryCompositionRoot`等を一切構築せず、
  `RetryRuntimeLockError`を専用に捕捉してエラーメッセージ（ロックファイルのパスと
  対処方法を含む）を表示した上でexit code 1とする
- `.gitignore`（リポジトリルート）へ`.run/`を追加（ロックファイルはランタイム生成物のためGit管理対象外）
- `docs/design/retry_runtime_lock_foundation.md`新規作成（Architecture Design・Architecture Review・
  Code Reviewの経緯を含む）
- `tests/test_e2e_v6_0_0_retry_runtime_lock_foundation.py`新規作成（24テストシナリオ・43アサーション）

### Note

- **`RetryCompositionRoot` / `RetryRuntimeOrchestrator` / `RetryRuntimeLoop` / `RetryManager`
  （`retry_engine`）はいずれも無改修。** 本Releaseの変更対象は`src/retry_runtime_lock/`（新規）と
  `scripts/run_retry_runtime.py`の配線のみ
- **`RetryRuntimeLock`は他のretry_*パッケージのいずれにも依存しない。** 標準ライブラリ
  （`os` / `pathlib`）のみで実装し、Retryドメイン・実行順序・ループ・Daemon化のいずれも関知しない
- **ロック取得失敗時は`RetryCompositionRoot`等を一切構築しない。** Retry業務ロジックへは到達せず、
  安全側に倒れる設計とした
- **`acquire()`内で`os.write()`が失敗した場合でも、ロックファイルを残さない。** Code Reviewで
  発見した「書き込み失敗時にロックファイルだけが残存し恒久的なstale lockになる」経路を修正し、
  `os.close(fd)` → ロックファイル削除 → 例外再送出という順序を徹底した
- **stale lockの自動検出・自動復旧（PID生存確認等）は行わない。** プロセスが強制終了した場合、
  ロックファイルが残存し次回起動がブロックされることがある（手動削除が必要。既知のTrade-off）
- 対象外（今回は未実装）：実際のバックグラウンド分離（detach）、Windows Service化、
  Graceful Shutdown（SIGTERM対応）、自動再起動、Process Supervision、Structured Logging、
  ロックパスの環境変数化（いずれも将来Release候補または対象外。`docs/design/retry_runtime_lock_foundation.md` 10章）

### Tested

- `tests/test_e2e_v6_0_0_retry_runtime_lock_foundation.py`: 43/43 PASS
  （`acquire()`/`release()`/`with`文の基本動作、取得済みロックへの`acquire()`失敗、
  エラーメッセージへのパス含有、べき等な`release()`、例外発生時の解放、親ディレクトリ自動作成、
  `os.write()`失敗時の解放（Code Review対応分）、他retry_*パッケージへの非依存、
  `scripts/run_retry_runtime.py`配線・専用例外捕捉、単発実行/`--loop`実行それぞれ2回連続実行できる
  ことによる解放の実証、実CLIでの多重起動拒否・エラーメッセージ内容・CompositionRoot未到達の確認、
  主要コンポーネントの無改修確認（git diff）、`format_summary()`公開契約の無変更確認）
- 既存回帰確認：
  - `tests/test_e2e_v5_9_0_*.py`：64/64 PASS（新規差分なし）
  - `tests/test_e2e_v5_7_0_*.py`：86/86 PASS（新規差分なし）
  - `tests/test_e2e_v5_5_0_*.py`：35/37（既存差分のみ、`[KI-27]`・`[KI-28]`。件数不変）
  - `tests/test_e2e_v5_6_0_*.py`：44/49（既存差分のみ、`[KI-26]`・`[KI-27]`。件数不変）
  - `tests/test_e2e_v5_8_0_*.py`：63/64（既存差分のみ、`[KI-27]`。件数不変）
- 本Releaseによる新規Known Issueはなし（`[KI-27]`へ追記のみ）

---

## [v5.9.0] - 2026-07-12 ★ Retry Runtime Loop Wiring Foundation

### Added

- `scripts/run_retry_runtime.py`へ`--loop`（`action="store_true"`）・`--interval-seconds`
  （`type=float`、`default=None`）引数を追加：`--loop`指定時、既存`RetryRuntimeLoop`（v5.5.0）を
  使ってinterval_seconds間隔で繰り返し実行する。`--loop`省略時（デフォルト）は従来どおり1サイクルのみ
- `--interval-seconds`は`--loop`と併用時のみ有効。`--loop`なしでの指定・0以下の指定はいずれも
  `parser.error()`によるCLIエラー（非0終了）とした。`--loop`指定時に省略した場合のデフォルトは60秒
- `main()`内のローカル関数`run_cycle()`（`orchestrator.run_once(dry_run=args.dry_run)` →
  `print(format_summary(result))`）を`RetryRuntimeLoop`の`run_once_fn`として注入し、
  `sleep_fn=time.sleep` / `should_continue_fn=lambda: True`とあわせて`RetryRuntimeLoop`を構築、
  `loop.run()`を呼び出す
- Loop実行中の`KeyboardInterrupt`（Ctrl+C）のみを`main()`内の`try/except`で捕捉し、短い終了メッセージ
  （`Retry runtime loop stopped.`）を表示したうえで正常終了（exit code 0）とする
- `docs/design/retry_runtime_loop_wiring_foundation.md`新規作成（Architecture Design（GPT-5.6 Sol）/
  Architecture Review（GPT-5.6 Sol）/ Implementation（Claude Code）の経緯を含む）
- `tests/test_e2e_v5_9_0_retry_runtime_loop_wiring_foundation.py`新規作成（32テストシナリオ・64アサーション）

### Note

- **`src/retry_runtime_loop/` / `src/retry_runtime_orchestrator/` / `src/retry_composition/` /
  `RetryManager`（`retry_engine`）はいずれも無改修。** 本Releaseの変更対象は
  `scripts/run_retry_runtime.py`の1ファイルのみ
- **`RetryRuntimeLoop`へdry_run属性・引数は追加していない。** dry_runは`run_cycle()`のクロージャから
  `orchestrator.run_once(dry_run=args.dry_run)`へ伝播する。Loopはdry_runの意味を一切知らない
- **`RetryRuntimeCycleResult` / `format_summary()`の公開契約は無変更。** サイクルごとの出力は
  `run_cycle()`内で`format_summary()`を呼ぶことで実現し、Loop APIの変更は行っていない
- **KeyboardInterrupt以外の例外はfail-fastを維持。** `run_cycle()`内の未処理例外は`RetryRuntimeLoop.run()`
  から伝播し、直後のsleepは実行されず、プロセスは非0終了する（例外を握りつぶして次サイクルへ進む設計は
  不採用）
- **`--loop`使用時の外部スケジューラとの重複起動リスクをdocstringへ明記した。** Runtime Lock・PID Lock等の
  二重起動防止機構は本Releaseの対象外
- Documentation Debt解消：`scripts/run_retry_runtime.py`のdocstringにあった「`RetryEnqueueTrigger`は
  dry_run非対応」という v5.8.0以前の古い記述を削除した（`[KI-23]`はv5.8.0で解消済み）
- 対象外（今回は未実装）：Daemon化、Windows Service化、PIDファイル・二重起動防止機構、自動再起動、
  ログローテーション、Structured Logging（サイクル番号・タイムスタンプ・JSON出力）、独自Signal Handler、
  SIGTERM対応、Error Continuation Policy、独自Exit Code体系、Scheduler API再設計、
  Summary Formatterクラス化、intervalの環境変数化（いずれも将来Release候補または対象外）

### Tested

- `tests/test_e2e_v5_9_0_retry_runtime_loop_wiring_foundation.py`: 64/64 PASS
  （単発実行・`--dry-run`単独の後方互換性確認、`--loop`経路への分岐確認、`--loop --dry-run`の
  全サイクル伝播確認、interval未指定時60秒・指定値伝播・0以下拒否・非数値拒否・`--loop`なし指定拒否の
  各CLIバリデーション確認、既存`RetryRuntimeLoop`の identity確認、run_once_fn/sleep_fn/
  should_continue_fnの配線確認、各サイクルのSummary出力確認、通常例外のfail-fast伝播とsleep未呼び出し確認、
  KeyboardInterruptの捕捉・終了メッセージ・正常終了確認（run_once_fn内・sleep_fn内の両方）、
  KeyboardInterrupt以外の例外による実CLI非0終了確認、`format_summary()`出力形式・公開契約の無変更確認、
  主要コンポーネントの無改修確認（git diff））
- 既存回帰確認：`git stash`によるベースライン比較で新規FAILを特定し分類した
  - `tests/test_e2e_v5_5_0_*.py`：37/37 → 35/37（新規2件、`[KI-27]`・`[KI-28]`）
  - `tests/test_e2e_v5_6_0_*.py`：既存4件FAIL（`[KI-26]`）→ 既存4件＋新規1件（`[KI-27]`）
  - `tests/test_e2e_v5_8_0_*.py`：64/64 → 63/64（新規1件、`[KI-27]`）
  - `tests/test_e2e_v5_1_0_*.py`・`tests/test_e2e_v5_2_0_*.py`・`tests/test_e2e_v5_3_0_*.py`・
    `tests/test_e2e_v5_4_0_*.py`・`tests/test_e2e_v5_7_0_*.py`：いずれも既存差分のみ（新規差分なし）
- 本Releaseによる新規Known Issueは`[KI-27]`・`[KI-28]`の2件

---

## [v5.8.0] - 2026-07-12 ★ Retry Enqueue Trigger Dry Run Foundation

### Added

- `RetryEnqueueTrigger.enqueue_pending_failures()`へ`dry_run: bool = False`を呼び出し時引数として追加：
  Monitor走査・History参照・Guard判定・Queue重複確認は`dry_run`の値に関わらず通常どおり実行するが、
  Guardを通過しQueue重複も存在しない候補について、`dry_run=True`の場合は`RetryQueueManager.enqueue()`を
  呼び出さず処理を終了する（`enqueued` / `failed`いずれにも加算しない）
- `RetryRuntimeOrchestrator.run_once()`から`trigger.enqueue_pending_failures(max_attempts=self.policy.max_attempts,
  dry_run=dry_run)`への伝播を追加：`run_once()`自体のシグネチャは無変更（v5.6.0のまま）
- `docs/design/retry_enqueue_trigger_dry_run_foundation.md`新規作成（Architecture Design / Architecture Review。
  Result Contract・CLI表示のいずれも変更しない方針（案B）を採用した経緯を含む）
- `tests/test_e2e_v5_8_0_retry_enqueue_trigger_dry_run_foundation.py`新規作成（20テスト・64アサーション）

### Note

- **`RetryEnqueueTriggerResult`は無改修。** `dry_run_planned`等の新規フィールドは追加していない。「実際に行われた
  結果のみを表す」という既存Result Contractの一貫性を優先した（Architecture Review過程での再検討。設計書5節）
- **`format_summary()` / `scripts/run_retry_runtime.py`は無改修。** `RetryEnqueueTriggerResult`の構造を変えない
  ため、既存の`format_summary()`が変更なしにdry_run時の`enqueued=0`を正しく表示するようになる
- **`RetryRuntimeCycleResult` / `RetryCompositionRoot` / `RetryManager` / `RetryExecutor` / `RetryQueueManager` /
  `RetryHistoryManager` / `RetryEnqueueGuard` / `RetryRuntimeLoop` / `NullRetryEnqueueTrigger`はいずれも無改修。**
  本Releaseの変更対象は`src/retry_enqueue_trigger/retry_enqueue_trigger.py` /
  `src/retry_runtime_orchestrator/retry_runtime_orchestrator.py`の2ファイルのみ
- **Known Limitation：** dry_run時、Guard通過かつQueue重複なしの候補は既存カウンタのいずれにも加算されないため、
  `scanned == enqueued + skipped_existing + skipped_status + skipped_history + failed`という暗黙の合計不変条件が
  dry_run時には成立しない場合がある。既存フィールドの意味を偽らないための意図的なトレードオフ（設計書12節）
- 対象外（今回は未実装）：Dry Run時の予定Enqueue件数の観測機能、Queue容量上限を考慮したシミュレーション、
  `--loop`のCLI配線、Daemon化（いずれも将来Release候補または対象外として設計書15節に記録）
- `[KI-23]`（v5.6.0で記録）を本Releaseで解消した（詳細は`[KI-23]`の2026-07-12追記を参照）

### Tested

- `tests/test_e2e_v5_8_0_retry_enqueue_trigger_dry_run_foundation.py`: 64/64 PASS
  （Spyによるqueue.enqueue()呼び出し有無の構造的検証、dry_run=True/False/省略時の挙動確認、
  RetryRuntimeOrchestrator.run_once(dry_run=...)からの実E2E伝播確認、シグネチャ・Result Contract無変更確認、
  無改修対象のgit diff確認、format_summary()の出力文字列確認・実CLIサブプロセス確認、AST検査による補助確認、
  副作用なしの確認）
- 既存回帰確認：関連する既存テストファイルを`git stash`によるベースライン比較で検証し、新規FAILを
  「本Releaseの意図的な仕様変更（`[KI-26]`）」「Architecture Guard差分（`[KI-25]`）」
  「既存Known Issue（本Releaseと無関係、確認済み）」に分類した
- `tests/test_e2e_v5_3_0_retry_runtime_run_once_foundation.py`のローカルFake`FakeTrigger`（本番`RetryEnqueueTrigger`
  の代役）が`dry_run`引数を持たないため、`enqueue_pending_failures(..., dry_run=dry_run)`呼び出し時に
  `TypeError`が発生し、同テストファイル全体（54件）がテスト3以降実行不能になっていたことを確認した。
  `FakeTrigger.enqueue_pending_failures()`へ`dry_run: bool = False`を追加（シグネチャ互換性の確保のみ。
  アサーション・期待値・戻り値・その他の挙動は無変更）し、52/54 PASSまで回復させた（残り2件はテスト2
  `[KI-22]`・テスト28`[KI-25]`のいずれも既存差分と同型）。テストダブルの互換性不足であり製品仕様上の
  問題ではないため、新規Known Issueとしては記録していない
- 本Releaseによる新規Known Issueは`[KI-25]`・`[KI-26]`の2件

---

## [v5.7.0] - 2026-07-12 ★ Retry Runtime Safe Dry Run Wiring Foundation

### Added

- `scripts/run_retry_runtime.py`の`main()`に`--dry-run`フラグを追加：`argparse`を`main()`内でローカルimportし、
  `ArgumentParser`で`--dry-run`（`action="store_true"`、デフォルト`False`）を解析する
- `--dry-run`指定時、`main()`が`[DRY RUN MODE]`を標準出力へ表示する（`format_summary()`は経由しない）
- `orchestrator.run_once(dry_run=args.dry_run)`（v5.6.0で実装済みの`dry_run`引数）への伝播
- `docs/design/retry_runtime_safe_dry_run_wiring_foundation.md`新規作成（Architecture Design / Architecture Review。
  変更範囲を`main()`内部のみへ最小化する4点のユーザー方針判断を含む）
- `tests/test_e2e_v5_7_0_retry_runtime_safe_dry_run_wiring_foundation.py`新規作成（86件）

### Note

- **`format_summary()`は無改修。** シグネチャ（`(result)`のみ）・実装とも一切変更していない。dry_run表示は
  `main()`側の`print("[DRY RUN MODE]")`に限定し、Summary生成の責務（`RetryRuntimeCycleResult` → Summary文字列）
  にCLI都合の情報を持ち込まない設計とした
- **`RetryRuntimeCycleResult`は無改修。** `dry_run`フィールドは追加していない。CLI都合の情報をDomain側の
  Resultクラスへ持ち込む設計を避けた
- **`RetryRuntimeOrchestrator` / `RetryManager` / `RetryExecutor` / `RetryCompositionRoot`はいずれも無改修。**
  本Releaseの変更対象は`scripts/run_retry_runtime.py`の`main()`内部のみ
- **`parse_args()`等の関数分離は行わなかった。** `--dry-run`1フラグのみの現時点ではYAGNIを優先し、`main()`内で
  直接処理する構成を採用した。`--loop` / `--config` / `--interval`等、フラグが複数に増えた時点で再検討する
- **CLI SummaryへKnown Issueの説明文は表示しない。** `--dry-run`指定時もEnqueueは通常どおり実行される制約
  （`[KI-23]`）は、CLI出力ではなくdocs（本ファイル・architecture.md・ROADMAP.md）で管理する方針とした
- 既存13パッケージ（`workflow_monitor` 〜 `retry_runtime_orchestrator`）・他scriptsはいずれも本Releaseでも無改修
- Technical Debtとして記録（本Release対象外）：`NullRetryEnqueueTrigger.enqueue_pending_failures()`が
  `max_attempts`引数を持たないシグネチャ不整合。現状`RetryCompositionRoot`が`RetryEnqueueTrigger`を常に実体で
  構築するため到達不能で実害はないが、将来Null経路が使われる設計変更が入る場合に修正を検討する
  （`docs/design/retry_runtime_safe_dry_run_wiring_foundation.md` 6章）
- 対象外（今回は未実装）：Enqueue側のdry_run対応、`--loop`のCLI配線、Exit Code再設計、Summary Formatter抽出
  （いずれも将来Release候補）

### Tested

- `tests/test_e2e_v5_7_0_retry_runtime_safe_dry_run_wiring_foundation.py`: 86/86 PASS
  （format_summary()無改修確認、RetryRuntimeCycleResult無改修確認、parse_args()不在確認（YAGNI）、
  argparseがmain()内のみでimportされることの確認、main()の配線検証（Fake差し替えによるdry_run伝播の
  モック検証）、`[DRY RUN MODE]`表示の有無確認、実CLIサブプロセス呼び出し（--dry-run有無両方）、
  副作用ファイル未作成確認、不正環境変数指定時のfail-fast維持確認、Architecture Guard）
- 既存回帰確認：`tests/test_e2e_v5_4_0_*.py`（66/67 PASS）・`tests/test_e2e_v5_5_0_*.py`（36/37 PASS）・
  `tests/test_e2e_v5_6_0_*.py`（48/49 PASS）は、いずれも新規1件FAILが`[KI-24]`に記録した意図的なものであることを
  確認。それ以外の既存46件のE2Eテストファイルはすべて変更前と同一の結果（本Releaseと無関係な既存事象
  （`[KI-1]`、`v4.8.0`/`v4.9.0`のv5.0.0由来の既存シグネチャ不整合）を除く）
- 本Releaseによる新規Known Issueは`[KI-23]`・`[KI-24]`の2件

---

## [v5.6.0] - 2026-07-12 ★ Retry Runtime Safe Dry Run Foundation

### Added

- `RetryOutcome.DRY_RUN`を追加（`src/retry_engine/retry_result.py`）：`dry_run=True`で
  再実行を試行したことを表す新しいOutcome値
- `RetryExecutor.execute()`（`src/retry_engine/retry_executor.py`）を変更：
  `request.dry_run=True`の場合、`WorkflowEngineManager.run()`の呼び出し自体は維持しつつ
  （dry_run=Trueが伝播しAgent層の`act()`が呼ばれないため実際の副作用はない。
  `workflow_engine_result`により「何が起きたはずか」を引き続き可視化する）、戻り値の
  `outcome`を`RetryOutcome.RETRIED`ではなく`RetryOutcome.DRY_RUN`とするよう変更
- `retry_outcome_terminality.py`を変更：`RetryCleanupReason.DRY_RUN`追加、
  `classify_reason()`へDRY_RUN分岐追加、`RETRY_OUTCOME_TERMINALITY`へ
  `DRY_RUN → TRANSIENT`（KEEP、Queueから消さない）を追加
- `RetryRuntimeOrchestrator.run_once()`（`src/retry_runtime_orchestrator/retry_runtime_orchestrator.py`）に
  `dry_run: bool = False`引数を追加し、`manager.execute_dispatchable_retries(events, dry_run=dry_run)`へ伝播
- `docs/design/retry_runtime_safe_dry_run_foundation.md`新規作成（Architecture Design /
  Architecture Review。ChatGPT（GPT-5.6 Sol）レビューを経た4点の修正検討事項と、
  それぞれの採用可否の判断を含む）
- `tests/test_e2e_v5_6_0_retry_runtime_safe_dry_run_foundation.py`新規作成（49件）

### Note

- **既存のDecider/Executor（`RetryQueueUpdateDecider` / `RetryHistoryRecordExecutor` /
  `RetryQueueRemovalExecutor` / `RetryQueueCleanupDecider`）はいずれも無改修。**
  「outcome==RETRIEDかどうか」またはallowlist方式で判定しているため、`DRY_RUN`は
  無改修のまま自動的に安全側（NOOP・記録なし・除去なし）に倒れる
- **`retry_outcome_terminality.py`のみ改修が必須だった。** `classify_reason()`が
  明示列挙+`raise ValueError`の網羅チェック方式（else方式ではない）であるため、
  改修を怠ると`RetryQueueTerminalCleanupDecider`経由で`run_once(dry_run=True)`が
  クラッシュすることをArchitecture Reviewで発見した（4点の修正検討事項の1つ、
  設計書参照）。**恒久ルールとして、`RetryOutcome`へ新しい値を追加する場合は
  リポジトリ全体で参照箇所を確認し、明示列挙・例外送出・永続化・表示・
  シリアライズへの影響をレビューすることを設計書に明記した**
- **CLI変更（`scripts/run_retry_runtime.py`への`--dry-run`・`argparse`配線）は
  今回対象外とした。** ChatGPTレビューを踏まえ、`run_once()`本体の追加（Execution
  Release）とCLIからの配線（Entry Point Release）を別Releaseに分けるという
  このプロジェクトの一貫したパターン（v5.3.0/v5.4.0と同型）を踏襲し、次Release候補
  「Retry Runtime Safe Dry Run Wiring」（`docs/ROADMAP.md`）へ申し送った
- **Enqueue側（`RetryEnqueueTrigger.enqueue_pending_failures()`）のdry_run対応は
  今回対象外。** `run_once(dry_run=True)`を呼んでも、WorkflowMonitor上のFAILED/TIMEOUTを
  Retry Queueへenqueueする処理自体は通常どおり実行される（Queueへの追加はin-memoryで
  可逆的・外部作用を伴わないためリスクレベルが異なると判断）。次Release候補
  「Retry Enqueue Trigger Dry Run Foundation」（`docs/ROADMAP.md`）へ申し送った
- **`run_once()`の`dry_run`をRequest Object化する案は見送った。** `RetryManager.retry()` /
  `execute_dispatchable_retries()`等、retry_engine全体が「呼び出しの都度渡すbool引数」で
  統一されているため、単一の振る舞い変更フラグのためにRequest Objectを導入するのは
  Development Charter「抽象化は必要になってから行う」に反すると判断した。将来、
  実行の振る舞いを変える引数（表示専用の`verbose`/`json`等ではなく）が2つ目以上
  必要になった時点でRequest Object化を再検討する、という基準を設計書に明記した
- 既存13パッケージ（`workflow_monitor` 〜 `retry_runtime_orchestrator`）のうち、
  本Releaseで変更したのは`retry_engine`（`retry_result.py` / `retry_executor.py` /
  `retry_outcome_terminality.py` / `__init__.py`）・`retry_runtime_orchestrator`
  （`retry_runtime_orchestrator.py`）の2パッケージのみ。`scripts/run_retry_runtime.py`
  を含むそれ以外の既存パッケージ・scriptsはいずれも無改修
- 対象外（今回は未実装）：CLI配線（`--dry-run` / `argparse`）、Enqueue側のdry_run対応、
  `--loop`のCLI配線、Exit Code再設計、Summary Formatter抽出（いずれも将来Release候補）

### Tested

- `tests/test_e2e_v5_6_0_retry_runtime_safe_dry_run_foundation.py`: 49/49 PASS
  （`RetryOutcome.DRY_RUN`の追加確認、`RetryExecutor.execute()`のdry_run分岐（単体）、
  Decider/Executor群がDRY_RUNを無改修のまま安全側に倒すことの確認（単体）、
  未知のRetryOutcomeに対するfail-fast動作の維持確認、`run_once(dry_run=True/False)`
  の実End-to-Endシナリオ、Architecture Guard）
- 既存回帰確認：変更前後で全48件のE2Eテストを機械的に比較。新規に発生した差分は
  すべて`[KI-22]`に記録した意図的なもの（`src/retry_engine` / `src/retry_runtime_orchestrator`
  の変更に起因するArchitecture Guard差分、および`RetryOutcome`5値化・`run_once()`
  シグネチャ変更という仕様変更そのもの）であり、それ以外の予期しない回帰は
  発見されなかった
- 本Releaseによる新規Known Issueは`[KI-22]`のみ

---

## [v5.5.0] - 2026-07-09 ★ Retry Runtime Loop Foundation

### Added

- `src/retry_runtime_loop/`新規パッケージ作成：`RetryRuntimeOrchestrator.run_once()`
  （v5.3.0）を繰り返し呼び出すだけの薄いWrapper`RetryRuntimeLoop`
  - `run_once_fn` / `sleep_fn` / `should_continue_fn` / `interval_seconds`を
    Constructor Injectionで保持し、`run()`で
    `while should_continue_fn(): run_once_fn(); sleep_fn(interval_seconds)`を
    実行するだけのStateless Wrapper。Business Logicは一切持たない
  - `RetryManager` / `RetryQueueManager` / `RetryHistoryManager` / `RetryPolicy` /
    `RetryRuntimeOrchestrator` / `RetryCompositionRoot`のいずれもimportしない
- `docs/design/retry_runtime_loop_foundation.md`新規作成（Project Charter /
  Architecture Design。Architecture Review Final・ユーザー承認済み。
  Option A（Loop Foundation）とOption B（Safe Dry Run Foundation）の比較評価を含む）
- `tests/test_e2e_v5_5_0_retry_runtime_loop_foundation.py`新規作成（37件）

### Note

- **本Releaseは未配線のFoundationに限定した。** `scripts/run_retry_runtime.py` /
  `RetryRuntimeOrchestrator` / `RetryCompositionRoot`のいずれからも
  `RetryRuntimeLoop`を呼び出さない（消費者不在の先行実装。v3.1.0・v3.3.0・
  v3.5.0・v5.1.0・v5.2.0と同型のパターン）
- **Architecture Reviewを2回実施した。** 初回レビューでは「Loop Foundation」を
  配線・運用まで見据えたものとして評価し、`run_once()`のdry_run未対応
  （v5.3.0 Known Issue）による安全性リスクが配線によって増幅されることを理由に、
  代替テーマ（Safe Dry Run Foundation）を提案した。ユーザーからの再レビュー依頼
  （Loop自体がBusiness Logicを持たない前提での再評価）を受け、未配線の
  Foundationに限定すれば実運用リスクを増やさずに導入できると判断し、結論を
  修正した（Option A'として採用。`docs/design/retry_runtime_loop_foundation.md`
  3章に比較評価を記録）
- **`run_once_fn`の戻り値は一切解釈しない。** 実運用では`RetryRuntimeCycleResult`
  が渡される想定だが、`RetryRuntimeLoop`はその型自体を知らず、戻り値を破棄する。
  `run()`の戻り値は`None`
- **例外はfail-fastで伝播させる。** `run_once_fn`が例外を送出した場合、そのまま
  `run()`から呼び出し元へ伝播し、直後の`sleep_fn`は呼ばれない
  （`RetryRuntimeOrchestrator.run_once()`と対称的な方針）
- **既存13パッケージ（`workflow_monitor` 〜 `retry_runtime_orchestrator`）・
  `scripts/run_retry_runtime.py`はいずれも本Releaseでも無改修。** 変更は
  `src/retry_runtime_loop/`の新規追加のみ
- Known Issue（未解消）：`RetryRuntimeLoop`を呼び出す消費者が存在しない、Loop配線時
  に必要となる`dry_run`安全性は引き続き未解決、interval設定方法（環境変数/CLI）・
  停止方法（signal handling）は未設計（詳細は
  `docs/design/retry_runtime_loop_foundation.md` 5章）
- 対象外（今回は未実装）：CLI配線（`--loop` / `argparse`）、`dry_run`対応、
  daemon化・signal handling、Exit Code再設計、Summary Formatter、
  `RetryRuntimeCycleResult`の解釈（いずれも将来Release候補）

### Tested

- `tests/test_e2e_v5_5_0_retry_runtime_loop_foundation.py`: 37/37 PASS
  （Fakeによる振る舞い確認：呼び出し回数・引数・順序・例外伝播・戻り値の破棄、
  責務境界の静的確認：禁止パッケージのimportなし・`RetryRuntimeCycleResult`
  識別子の不出現、ディレクトリ構成・export確認、既存13パッケージ・
  `scripts/run_retry_runtime.py`の無変更確認、消費者不在の確認、副作用なしの確認）
- 既存回帰確認：`v5.3.0`（54/54）・`v5.4.0`（67/67）：全PASS。`v5.1.0`（36/38、
  既存の`[KI-19]`による既知差分のみ）・`v5.2.0`（49/54、既存の`[KI-20]`・`[KI-21]`
  による既知差分のみ）：いずれも本Releaseによる新規差分はない
- **本Releaseでは新規Known Issue（KI）は発生しなかった。** 既存ファイルへの
  変更が一切なく、`retry_runtime_loop`を参照する既存ファイルも存在しないため、
  過去のFoundation Release（`[KI-19]`〜`[KI-21]`等）で恒常的に発生していた
  Architecture Guardの恒久差分は本Releaseでは生じていない

---

## [v5.4.0] - 2026-07-09 ★ Retry Runtime Script Entry Point Foundation

### Added

- `scripts/run_retry_runtime.py`新規作成：`RetryCompositionRoot.from_env()` →
  `RetryRuntimeOrchestrator.from_composition_root()` → `run_once()`を1回だけ呼び出す
  Entry Point。CLI引数は持たない
  - `format_summary(result: RetryRuntimeCycleResult) -> str`：`RetryRuntimeCycleResult`を
    人間向けサマリー文字列へ変換する関数。表示ロジックを`main()`から分離し、
    将来Formatterクラスへ抽出しやすい構造に留めた（Architecture Review Minor
    Recommendation #2）
- `docs/design/retry_runtime_script_entry_point_foundation.md`新規作成（Project
  Charter / Architecture Design。Architecture Review Final・ユーザー承認済み）
- `tests/test_e2e_v5_4_0_retry_runtime_script_entry_point_foundation.py`新規作成（67件）

### Note

- **`RetryRuntimeOrchestrator.run_once()`（v5.3.0）に初めての実際の呼び出し口が
  できた。** v5.1.0〜v5.3.0で積み上げたComposition Root / Orchestratorの土台が、
  本Releaseで初めてCLIから実行可能になった
- **Exit Code Policyを明文化した（Architecture Review Minor Recommendation #1）。**
  正常終了はexit code 0（Python標準）、例外発生時はPython標準の非0（fail-fast
  でそのまま伝播）。独自のExit Code体系は導入していない
- **`--dry-run`は追加しなかった。** `run_once()`自体がdry_run未対応
  （v5.3.0 Known Issue）のため、CLI側にだけ`--dry-run`を追加すると「指定したのに
  実際にQueue除去・History記録が起きた」という見せかけの安全機能になり、
  Development Charter 3章が警戒する誤動作を招くため見送った
  （`docs/design/retry_runtime_script_entry_point_foundation.md` 2.3節）
- **Gate（`RETRY_ENGINE_ENABLED`等）の状態を判定しない設計とした。**
  `NullRetryManager.execute_dispatchable_retries()`が常に空リストを安全に返す
  設計（既存実装で確認済み）であるため、scriptは`isinstance()`によるNull判定を
  一切行わず、常に`run_once()`を呼び出して結果件数をそのまま表示する
  （同設計書2.6節）
- **`RetryCompositionRoot` / `RetryRuntimeOrchestrator`・既存12パッケージ
  （`workflow_monitor` 〜 `retry_composition`）はいずれも本Releaseでも無改修。**
  変更は`scripts/run_retry_runtime.py`の新規追加のみ
- Known Issue（未解消）：`dry_run`未対応（継続）、Exit Codeによる成否監視は不可
  （標準出力の目視確認のみ）、他のAgent系scriptとの同時実行に対する排他制御なし
  （詳細は`docs/design/retry_runtime_script_entry_point_foundation.md` 5章）
- 対象外（今回は未実装）：`--loop` / `--daemon`、安全なdry_run再設計、独自Exit Code
  体系、Summary Formatterクラス化（いずれも将来Release候補）

### Tested

- `tests/test_e2e_v5_4_0_retry_runtime_script_entry_point_foundation.py`: 67/67 PASS
  （スクリプトの存在・`format_summary()`の構造と出力内容・scripts層の責務に関する
  静的import検査・Null判定を行わない方針の確認・サブプロセス実行によるGate無効時の
  正常終了と副作用なしの確認・Exit Code Policy（不正環境変数によるfail-fast）の確認・
  Architecture Guardを確認）
- 既存回帰確認：`v5.3.0`（54/54）・`v4.7.0`（178/178）・`v2.0.0`（118/118）：全PASS
- `v5.1.0`（36/38、既存の`[KI-19]`による既知差分のみ）・`v5.0.0`（109/110、既存の
  既知差分のみ）・`v4.9.0`（既存の`[KI-18]`による`TypeError`が引き続き再現）・
  `v4.1.0`（84/87、既存の`[KI-11]`による既知差分のみ）・`v3.0.0`（206/208、既存の
  既知差分のみ）：いずれも本Releaseによる新規差分はない
- `v5.2.0`（49/54、新規1件は`[KI-21]`参照。`[KI-20]`の既存4件と合わせて計5件FAIL）：
  本Releaseで想定済みの差分
- 既存12パッケージ（`retry_composition` / `retry_runtime_orchestrator`含む）は
  いずれも`git diff --quiet`で無変更を確認済み。既存の他scripts
  （`run_workflow_engine.py`等6本）も無変更を確認済み

---

## [v5.3.0] - 2026-07-09 ★ Retry Runtime Run Once Foundation

### Added

- `src/retry_runtime_orchestrator/retry_runtime_cycle_result.py`新規作成（`RetryRuntimeCycleResult`）
  - `trigger_result` / `scheduler_events` / `execution_results` / `removal_results` /
    `cleanup_results` / `terminal_cleanup_results` / `history_results`の7フィールドを持つ
    frozen dataclass
- `docs/design/retry_runtime_run_once_foundation.md`新規作成（Project Charter / Architecture Design。Architecture Review Final・ユーザー承認済み）
- `tests/test_e2e_v5_3_0_retry_runtime_run_once_foundation.py`新規作成（54件）

### Changed

- `src/retry_runtime_orchestrator/retry_runtime_orchestrator.py`：`RetryRuntimeOrchestrator`へ`run_once()`を追加した
  - 実行順序：`trigger.enqueue_pending_failures(max_attempts=self.policy.max_attempts)` →
    `scheduler.run_due(jobs=[])` → `manager.execute_dispatchable_retries(events)`
    （本メソッド内でちょうど1回だけ呼び出す） → `RetryQueueUpdateDecider` /
    `RetryQueueRemovalExecutor` / `RetryQueueCleanupDecider` / `RetryQueueCleanupExecutor` /
    `RetryQueueTerminalCleanupDecider` / `RetryQueueTerminalCleanupExecutor` /
    `RetryHistoryRecordExecutor`（いずれも`retry_engine`が既に公開しているStateless・
    無引数コンストラクタのクラス）への結果配布
  - 戻り値は`None`ではなく`RetryRuntimeCycleResult`
- `src/retry_runtime_orchestrator/__init__.py`：`RetryRuntimeCycleResult`をexportへ追加
  （`__all__`が`RetryRuntimeOrchestrator` / `RetryRuntimeCycleResult`の2シンボルになった）

### Note

- **発見B（v5.2.0で発見された多重実行リスク）を解消した。** `execute_dispatchable_retries()`
  は`run_once()`内でちょうど1回だけ呼び出され、その戻り値（`execution_results`）を保持した
  まま各Decider/Executorへ配布する。これにより、`RetryManager`の上位メソッド群を素朴に
  並べて呼ぶと最大4回`retry()`が実行されうるリスクを構造的に解消した
  （`docs/design/retry_runtime_run_once_foundation.md` 1.2節・2.1節）
- **`RetryManager`（`retry_manager.py`）は本Releaseでも無改修のまま維持した。**
  `run_cycle()`等の統合APIは追加せず、実行順序の知識は`RetryRuntimeOrchestrator.run_once()`
  だけに閉じた（Single Responsibility）
- **`RetryQueueUpdateDecider`が生成する`decisions`は、Removal / Cleanup / TerminalCleanupの
  3系統に共有される。** COMPLETE/FAIL（Removal対象）・SKIPPED由来のNOOP（Cleanup対象）・
  NOT_FOUND由来のNOOP（TerminalCleanup対象）は構造的に排他であり、同一run_idに対して
  `queue.remove()`が二重に呼ばれることはない（実コード・E2Eテストで確認済み）
- **`dry_run`引数は追加しなかった。** `RetryExecutor.execute()`は`dry_run`の値に関わらず
  常に`outcome=RetryOutcome.RETRIED`を返すため、`dry_run`を`execute_dispatchable_retries()`
  へそのまま渡しても、後続のQueue除去（`queue.remove()`）・History記録
  （`history.record()`）という実際の副作用は防げない。「安全なはずのdry_runが実は副作用を
  起こす」という誤動作を避けるため、本Releaseでは`dry_run`引数を追加せず、Known Issueとして
  記録した（`docs/design/retry_runtime_run_once_foundation.md` 4章）
- **`scripts/`エントリーポイントは追加しなかった。** `run_once()`本体の設計・実装・テストに
  集中し、起動スクリプトは次Release候補とした
- **`scheduler.run_due(jobs=[])`を利用した。** `jobs=[]`によりJob判定は行わず、Retry候補由来の
  `SchedulerEvent`のみを取得する。将来Retry専用Scheduler API（例：`run_retry_due()`）が
  `scheduler`パッケージへ追加された場合は置き換え可能とする（Future Architecture Consideration）
- **既存11パッケージ（`workflow_monitor` / `retry_queue` / `retry_history` /
  `retry_enqueue_trigger` / `retry_engine` / `workflow_engine` / `ai` / `execution_history` /
  `scheduler` / `retry_scheduler_source` / `retry_scheduler_decision`）はいずれも本Releaseでも
  無改修（ゼロ改修）。** 変更は`src/retry_runtime_orchestrator/`配下のみ
- Known Issue（未解消）：同一サイクル内での即時再試行（バックオフなし）、
  `scheduler.run_due()`が常にシステム時刻を使うこと（clock注入経路の未整備）、
  `RetryQueueManager` / `RetryHistoryManager`の永続化、`scripts/`エントリーポイントの未整備
  （詳細は`docs/design/retry_runtime_run_once_foundation.md` 6章）
- 対象外（今回は未実装）：`dry_run`・`loop()` / `daemon()`・`scripts/`エントリーポイント・
  Retry専用Scheduler API（いずれも将来Release候補）

### Tested

- `tests/test_e2e_v5_3_0_retry_runtime_run_once_foundation.py`: 54/54 PASS
  （呼び出し順序・`execute_dispatchable_retries()`が1回だけ呼ばれること・
  `RetryRuntimeCycleResult`の内容・Decider/Executorへの配布ロジック・実コンポーネントによる
  End-to-Endシナリオ（Enqueue→Retry→Queue除去→History記録）・NullRetryManager経路の安全性・
  Architecture Guardを確認）
- 既存回帰確認：`v4.7.0`（178/178）・`v2.0.0`（118/118）：全PASS
- `v5.1.0`（36/38、既存の`[KI-19]`による既知差分のみ）・`v5.0.0`（既存の既知差分のみ）・
  `v4.9.0`（既存の`[KI-18]`による`TypeError`が引き続き再現）・`v4.1.0`（既存の既知差分のみ）・
  `v3.0.0`（既存の`[KI-4]`系による既知差分のみ）：いずれも本Releaseによる新規差分はない
- `v5.2.0`（50/54、新規4件は`[KI-20]`参照。`run_once()`追加・ファイル構成/export変更による
  恒久的な既知差分）：本Releaseで想定済みの差分
- `retry_manager.py`を含む既存11パッケージはいずれも`git diff --quiet`で無変更を確認済み

---

## [v5.2.0] - 2026-07-09 ★ Retry Runtime Orchestrator Foundation

### Added

- `src/retry_runtime_orchestrator/`新規パッケージ作成（`RetryRuntimeOrchestrator`）
  - `retry_runtime_orchestrator.py`：`RetryRuntimeOrchestrator`（`__init__.py`は`RetryRuntimeOrchestrator`のみexport）
- `docs/design/retry_runtime_orchestrator_foundation.md`新規作成（Project Charter / Architecture Design。Architecture Review Final・ユーザー承認済み）
- `tests/test_e2e_v5_2_0_retry_runtime_orchestrator_foundation.py`新規作成（54件）

### Changed

- `src/retry_composition/retry_composition_root.py`：`RetryCompositionRoot`にScheduler系3コンポーネントの配線を追加した
  - `__init__`へ`retry_source: RetrySchedulerSource | NullRetrySchedulerSource` / `retry_decision: RetrySchedulerDecision` / `scheduler: SchedulerEngine`の3属性を末尾に追加（既存7属性の並び順は無変更）
  - `from_env()`内で`RetrySchedulerSource(queue)` → `RetrySchedulerDecision(retry_source)` → `SchedulerEngine(retry_source=..., retry_decision=...)`の順に組み立て、`queue`はtrigger/managerと同一インスタンスを注入する
  - 新規business logicは追加しない（既存の公開コンストラクタへの委譲のみ）

### Note

- **Architecture Reviewで2つの重要な発見があった。** （発見A）`RetryManager.execute_dispatchable_retries()`が要求する`events: list[SchedulerEvent]`は`RetryQueueManager → RetrySchedulerSource → RetrySchedulerDecision → SchedulerEngine`という経路でしか得られないが、v5.1.0の`RetryCompositionRoot`はこの経路を配線しておらず、「Queueに積まれた再試行候補を実行可能にする」ことが構造的にできなかった。（発見B）`RetryManager`の上位メソッド群（`apply_retry_queue_removals()` / `apply_retry_queue_cleanup()` / `apply_retry_queue_terminal_cleanup()` / `record_retry_history()`）はそれぞれ独立に`execute_dispatchable_retries()`を再計算するため、同一`events`に対して素朴に並べて呼び出すと`retry()`が同一run_idに対して最大4回呼ばれるリスクがある（`docs/design/retry_runtime_orchestrator_foundation.md` 1.2節）
- **ChatGPTレビューを経て、Scheduler配線単独のReleaseではなく「Composition（組み立て）とOrchestration（実行順序）の責務分離を確立するRelease」へテーマを再定義した。** `RetryCompositionRoot`は今後もDependency Injectionのみを責務とし、実行系メソッド（`run()` / `run_once()`等）は追加しない方針を維持する。新設した`RetryRuntimeOrchestrator`は「Retry Runtimeの実行順序を将来管理する場所」だが、本Releaseでは`run()` / `run_once()` / `loop()` / `daemon()`等のBusiness Logicは一切実装しない（同設計書2.1節・2.2節）
- **`RetryRuntimeOrchestrator`は`trigger` / `scheduler` / `manager`に加え、`queue` / `history` / `policy`も本Releaseから保持する。** これはDevelopment Charter 8章が禁じる「使われる保証のない実装の先回り」ではなく、次Execution Releaseで確定的に必要になることが判明した参照の保持のみである。`queue.remove` / `history.record`はDecider/Executorへのコールバックとして、`policy.max_attempts`は`enqueue_pending_failures()`への引数として、次Releaseで確実に使われる（同設計書2.4節）。`guard`（`RetryEnqueueTrigger`専属の内部コンポーネント）・`monitor`（将来依存が未確定）は保持しない
- **発見Bの解決は`RetryManager`への統合API（`run_cycle()`等）の追加ではなく、Orchestrator側での直接構成とした。** ChatGPTレビューにより「`RetryManager`が実行順序（Trigger/Scheduler/Cleanup/Historyの呼び出し順）まで知ることになりSingle Responsibilityから外れる」という懸念が指摘され、代替として、次Execution Releaseで`RetryRuntimeOrchestrator`が`execute_dispatchable_retries()`を1回だけ呼び出しその結果を保持したうえで、`retry_engine`が既に公開しているStateless・無引数コンストラクタのDecider/Executor群（`RetryQueueUpdateDecider` / `RetryQueueRemovalExecutor` / `RetryQueueCleanupDecider` / `RetryQueueCleanupExecutor` / `RetryQueueTerminalCleanupDecider` / `RetryQueueTerminalCleanupExecutor` / `RetryHistoryRecordExecutor`）へ直接配布する方針を確定した。これにより`retry_manager.py`は本Releaseでも、次Execution Releaseでも無改修のまま維持できる見込みである（同設計書1.2節・2.5節）
- **`scripts/`層へのBusiness Flowの実装は行わない。** scriptsはEntry Pointのみに限定する方針とし、本Releaseではscriptsの追加自体を行わない
- **既存11パッケージ（`workflow_monitor` / `retry_queue` / `retry_history` / `retry_enqueue_trigger` / `retry_engine` / `workflow_engine` / `ai` / `execution_history` / `scheduler` / `retry_scheduler_source` / `retry_scheduler_decision`）はいずれも本Releaseでも無改修（ゼロ改修）。** `retry_manager.py`を含め、変更は`src/retry_composition/retry_composition_root.py`の拡張と`src/retry_runtime_orchestrator/`の新規追加のみ
- **本Release単体では何も実行されない。** `RetryRuntimeOrchestrator`は`from_composition_root()`で組み立てられるだけであり、ユーザーから見て動く機能が増えるわけではない。次Execution Releaseで`run_once()`が実装されて初めて実運用上の価値が生まれる（同設計書5章 Known Issue）
- 対象外（今回は未実装）：`run()` / `run_once()` / `loop()` / `daemon()`・発見Bの解決の実装・scripts層のEntry Point（いずれも将来Release候補）

### Tested

- `tests/test_e2e_v5_2_0_retry_runtime_orchestrator_foundation.py`: 54/54 PASS（Scheduler系配線のインスタンス共有・`RetryRuntimeOrchestrator`が保持する6属性すべての同一インスタンス確認・責務境界（実行系メソッド不在）を`is`比較・シグネチャ検査で確認）
- 既存回帰確認：`workflow_monitor` / `retry_queue` / `retry_history` / `retry_enqueue_trigger` / `retry_engine` / `workflow_engine` / `ai` / `execution_history` / `scheduler` / `retry_scheduler_source` / `retry_scheduler_decision`のいずれも`git diff --quiet`で無変更を確認済み（本Releaseの新規テスト24）
- `v2.6.0`・`v2.7.0`（163/163）・`v2.9.0`（103/103）・`v3.1.0`（152/152）・`v3.4.0`（94/94）・`v3.7.0`（74/74）・`v4.7.0`（178/178）：全PASS
- `v3.0.0`（206/208）・`v3.2.0`（100/102）・`v3.3.0`（71/72）・`v3.5.0`（71/72）・`v3.6.0`（102/104）・`v3.8.0`（67/70）・`v3.9.0`（70/73）・`v4.0.0`（83/88）・`v4.1.0`（84/87）・`v4.2.0`（91/94）・`v4.3.0`（105/108）・`v4.4.0`（120/123）・`v4.5.0`（63/64）・`v4.6.0`（97/100）：いずれも既存の`[KI-3]`〜`[KI-18]`による既知差分のみで、本Releaseによる新規差分はない（対象パッケージを一切変更していないため）
- `v4.8.0`・`v4.9.0`：既存の`[KI-18]`（Guardシグネチャ変更による`TypeError`中断）が引き続き再現。本Releaseによる新規差分ではない
- `v5.0.0`（109/110、既存差分。`retry_composition`が既に`retry_enqueue_trigger`を参照していることに起因する消費者スキャン検知で、v5.1.0時点から継続する差分）：本Releaseによる新規差分ではない
- `v5.1.0`（36/38、新規2件は`[KI-19]`参照。`RetryCompositionRoot.__init__`のパラメータ追加・`retry_composition`の初の実消費者化による恒久的な既知差分）：本Releaseで想定済みの差分
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v5.1.0] - 2026-07-09 ★ Retry Composition Root Foundation

### Added

- `src/retry_composition/`新規パッケージ作成（`RetryCompositionRoot`）
  - `retry_composition_root.py`：`RetryCompositionRoot`（`__init__.py`は`RetryCompositionRoot`のみexport）
- `docs/design/retry_composition_root_foundation.md`新規作成（Project Charter / Architecture Design。Architecture Review Final・ユーザー承認済み）
- `tests/test_e2e_v5_1_0_retry_composition_root_foundation.py`新規作成（38件）

### Changed

- なし（既存パッケージへの変更は一切ない。新規パッケージ追加のみ）

### Note

- **v5.0.0までのGuard判定基準精緻化が実運用で意味を持つための前提条件（Queue/Historyインスタンスの共有）を整備した。** `RetryQueueManager` / `RetryHistoryManager`はいずれもプロセス内メモリの`dict`のみで状態を保持するため、`RetryEnqueueTrigger`（Enqueue側）と`RetryManager`（Execute側）を別々に構築すると、それぞれが独立した空のQueue/Historyを持つことになり、v4.7.0〜v5.0.0で構築したGuardの回数比較判定が実運用上意味を持たない、というアーキテクチャ上のリスクがArchitecture Reviewの過程で判明した（`docs/design/retry_composition_root_foundation.md` 1.2節）
- **Enqueue単体のComposition Rootではなく、Enqueue・Execute双方を対象にしたComposition Rootへとテーマを見直した。** 当初は`RetryEnqueueTrigger`のみを配線する限定スコープの案を検討していたが、Runtime全体を組む段階になった時点で書き直しが発生する「使い捨てComposition Root」になるリスクを指摘され、`RetryQueueManager` / `RetryHistoryManager`を1インスタンスずつ生成して`trigger`と`manager`の両方へ注入する設計に変更した
- **責務は「既存の`from_env()`/`from_config()`のみを使って組み立て、属性として公開すること」に限定した。** `RetryCompositionRoot`は`from_env()`以外の公開メソッドを持たない。`enqueue_pending_failures()` / `execute_dispatchable_retries()`等を呼び出す実行順序の決定（`run_once()`等）・ループ・デーモン化・起動スクリプトはいずれも本Releaseの対象外とした。新規business logicはゼロ（同設計書2.3節 Design Policy #1・#4）
- **パッケージ配置・クラス名をArchitecture Reviewで再検討した。** `src/retry_composition/`（既存16パッケージと同じドメインスコープの命名。汎用`src/runtime/`・`src/application/`は2つ目の消費者が存在しない段階での先回り抽象化として不採用）、`RetryCompositionRoot`（「Runtime」は実行責任を連想させ本Releaseの責務境界と矛盾するため不採用。「Builder」「Factory」は生成後の参照を保持し続ける性質と不一致のため不採用。DI文脈で確立した「Composition Root」という語を採用）（同設計書2.1節）
- **`workflow_monitor` / `retry_queue` / `retry_history` / `retry_enqueue_trigger` / `retry_engine` / `workflow_engine` / `ai` / `execution_history`はいずれも本Releaseでも無改修（ゼロ改修）。** 変更は`src/retry_composition/`配下2ファイルの新規追加のみ
- **本Release単体では何も実行されない。** `RetryCompositionRoot.from_env()`を呼び出して終わりであり、ユーザーから見て動く機能が増えるわけではない。次Release以降の「1サイクル実行」の起動スクリプトが実装されて初めて実運用上の価値が生まれる（同設計書5章 Known Issue）
- 対象外（今回は未実装）：起動スクリプト・1サイクル実行・ループ・デーモン化・`RetryQueueManager` / `RetryHistoryManager`の永続化・新規Configクラス（いずれも将来Release候補）

### Tested

- `tests/test_e2e_v5_1_0_retry_composition_root_foundation.py`: 38/38 PASS（`RETRY_ENGINE_ENABLED`等の全ゲート無効時・全ゲート有効時の両方で、`trigger`と`manager`が同一のQueue/Historyインスタンスを参照していることを`is`比較で確認）
- 既存回帰確認：`workflow_monitor` / `retry_queue` / `retry_history` / `retry_enqueue_trigger` / `retry_engine` / `workflow_engine` / `ai` / `execution_history`のいずれも`git diff --quiet`で無変更を確認済み（本Releaseの新規テスト19）
- `v2.7.0`（163/163）・`v2.9.0`（103/103）・`v3.1.0`（152/152）・`v3.4.0`（94/94）・`v3.7.0`（74/74）・`v4.7.0`（178/178）：全PASS
- `v3.0.0`（206/208）・`v3.2.0`（100/102）・`v3.3.0`（71/72）・`v3.5.0`（71/72）・`v3.6.0`（102/104）・`v3.8.0`（67/70）・`v3.9.0`（70/73）・`v4.0.0`（83/88）・`v4.1.0`（84/87）・`v4.2.0`（91/94）・`v4.3.0`（105/108）・`v4.4.0`（120/123）・`v4.5.0`（63/64）・`v4.6.0`（97/100）：いずれも既存の`[KI-3]`〜`[KI-17]`による既知差分のみで、本Releaseによる新規差分はない（対象パッケージを一切変更していないため）
- `v4.8.0`・`v4.9.0`：既存の`[KI-18]`（Guardシグネチャ変更による`TypeError`中断）が引き続き再現。本Releaseによる新規差分ではない
- `v5.0.0`（109/110、`[KI-18]`のv4.7.0テスト29 `git diff`一時検知）：本Releaseによる新規差分ではない
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v5.0.0] - 2026-07-09 ★ Retry Enqueue Guard Refinement Foundation

### Added

- `docs/design/retry_enqueue_guard_refinement_foundation.md`新規作成（Project Charter / Architecture Design。Architecture Review Final・ユーザー承認済み）
- `tests/test_e2e_v5_0_0_retry_enqueue_guard_refinement_foundation.py`新規作成（110件）

### Changed

- `src/retry_enqueue_trigger/retry_enqueue_guard.py`：`RetryEnqueueGuard.decide()`のシグネチャ・判定式を変更した
  - `decide(self, run_id: str, has_history: bool)` → `decide(self, run_id: str, next_attempt: int, max_attempts: int)`
  - 判定基準を「履歴が1回でもあればBLOCK」の二値から「`next_attempt > max_attempts`ならBLOCK」の回数比較へ精緻化した
  - `RetryHistoryManager`型・`RetryPolicy`（`retry_engine`）型のいずれも一切importしないStateless性は維持した
- `src/retry_enqueue_trigger/retry_enqueue_trigger.py`：`RetryEnqueueTrigger.enqueue_pending_failures()`を変更した
  - `max_attempts: int = 1`を末尾のデフォルト値付き引数として追加した（`limit`と同じ「呼び出しの都度渡す」スタイル）
  - `next_attempt`の算出をGuard判定の直前に確定させ、Guard判定・Queue登録の両方に同じ値を使うようにした（v4.9.0時点はGuard判定後にQueue登録用として別途算出していた）
  - `RetryEnqueueTrigger.__init__`は**本Releaseでも完全に無変更**（`max_attempts`はインスタンス状態として保持しない）

### Note

- **v4.9.0 Known Issue（Guard判定基準の精緻化）を解消した。** `RetryEnqueueGuard`の判定基準を「履歴の有無」の二値から「`next_attempt > max_attempts`」の回数比較へ精緻化し、v4.9.0で配線済みだった`retry_attempt`の実回数連動に初めて実際の消費者を与えた（`docs/design/retry_enqueue_guard_refinement_foundation.md` 1章・5章）
- **`max_attempts`をConstructor InjectionではなくMethod引数として設計した（Architecture Review Finalでの再検討結果）。** 当初のArchitecture Reviewでは`RetryEnqueueTrigger.__init__(..., max_attempts: int = 1)`という案だったが、ChatGPTレビューを受けて「Triggerが設定値を長期保持する責務まで持つべきか」を再検討し、`enqueue_pending_failures(limit=None, max_attempts=1)`という呼び出し引数へ変更した。これにより`RetryEnqueueTrigger.__init__`は本Releaseでも1文字も変わらず、Backward Compatibilityがさらに強くなった（同設計書2.2節 Design Policy #2）
- **`max_attempts`のデフォルト値`1`は、`RetryPolicy.max_attempts`（デフォルト3）とは意図的に独立した値である。** 二重管理の解消（`retry_enqueue_trigger`が`RetryPolicy`を直接参照する案）も検討したが、v4.6.0 Design Policy #2（`retry_engine`を経由しない）との整合性を優先し、採用しなかった。両者は「業務ルールとしての正式な再試行上限」と「設定未注入時の構造的セーフガード」という別の意味を持つ値として明確に区別する（同設計書5章 Known Issue、2.2節 Design Policy #4）
- **`RetryEnqueueOptions`等のDTO（Immutable Value Object）は本Releaseでは導入しない。** 現時点でGuard判定に渡すPolicy値は`max_attempts`の1項目のみであり、YAGNI・Development Charter 8章「抽象化は必要になってから行う」に従い、素朴な引数のまま維持した。将来Policy値が複数へ増えた場合の再検討基準を設計書6章「Future Architecture Consideration」に明記した
- **Backward Compatibility を強く維持。** `RetryEnqueueTrigger.__init__`は完全に無変更。`enqueue_pending_failures()`への引数追加は末尾のデフォルト値付きのみであり、既存の呼び出し（`enqueue_pending_failures()` / `enqueue_pending_failures(limit=10)`）は本Release後もまったく同じ結果になる
- **`retry_history` / `retry_queue` / `workflow_monitor` / `retry_engine`はいずれも本Releaseでも無改修。** 変更は`src/retry_enqueue_trigger/`配下2ファイルのみ（新規ファイルなし）
- **新たな制約（Known Issue）が本Releaseでも残る。** Composition Root未接続のため、`max_attempts`を明示的に注入する呼び出し元が存在しない限り、本Release後も実運用では実質1回しかリトライされないままである（`docs/design/retry_enqueue_guard_refinement_foundation.md` 5章 Known Issue）
- 対象外（今回も未実装）：Composition Root・`RetryEnqueueOptions`等のDTO・`.env.example`整備（いずれも将来Release候補）

### Tested

- `tests/test_e2e_v5_0_0_retry_enqueue_guard_refinement_foundation.py`: 110/110 PASS
- 既存回帰確認：`v1.9.0`〜`v2.9.0`（Analytics Foundation `[KI-1]`除く）全PASS
- `v3.0.0`〜`v4.6.0`：いずれも既存の`[KI-3]`〜`[KI-16]`による既知差分のみで、本Releaseによる新規差分はない（`retry_engine` / `scheduler`等、`retry_enqueue_trigger`以外のパッケージを一切変更していないため）
- `v4.7.0`（177/178、新規1件は`[KI-18]`参照。`git diff`ベースの一時的な検知で、commit後に解消見込み）
- `v4.8.0`・`v4.9.0`：いずれもGuardのシグネチャ変更により`TypeError`でテストスクリプトが中断する（新規、`[KI-18]`参照。恒久的な既知差分として記録）
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v4.9.0] - 2026-07-09 ★ Retry Attempt Synchronization Foundation

### Added

- `docs/design/retry_attempt_synchronization_foundation.md`新規作成（Project Charter / Architecture Design。Architecture Review完了・**Approve**・ユーザー承認済み）
- `tests/test_e2e_v4_9_0_retry_attempt_synchronization_foundation.py`新規作成（96件）

### Changed

- `src/retry_enqueue_trigger/retry_enqueue_trigger.py`：`RetryEnqueueTrigger.enqueue_pending_failures()`を変更した
  - `self._history.has_history(record.run_id)`の呼び出しを`self._history.get(record.run_id)`（既存の公開API）に置き換え、1回の呼び出しで「履歴の有無」（Guard判定用）と「次のattempt番号」（Queue登録用）の両方を導出するようにした
  - `next_attempt = history_record.attempt_count + 1 if history_record is not None else 1`を算出し、`self._queue.enqueue()`の`retry_attempt`引数へ明示的に渡すようにした（これまでは省略され常に`1`固定だった）
  - `RetryEnqueueTrigger.__init__`のシグネチャ・`RetryEnqueueTriggerResult`のフィールド・`src/retry_enqueue_trigger/__init__.py`の`__all__`はいずれも無変更

### Note

- **本Release単体では観測可能な挙動変化は発生しない。** `RetryEnqueueGuard`（v4.8.0）は「履歴が1回でもあれば無条件でBLOCK」という二値判定のままのため、`self._queue.enqueue()`に実際に到達するのは`history_record is None`（＝この`run_id`は一度もretryされていない）ケースのみであり、この分岐における`next_attempt`は常に`1`にしかならない。これは不具合ではなく、Guardの判定基準精緻化（`attempt_count >= max_attempts`比較への変更）を将来Releaseへ送るための意図的な「消費者不在の配線」である（`docs/design/retry_attempt_synchronization_foundation.md` 2.3節）
- **`retry_attempt`を下流まで正しく伝播させる経路は既に完成していたことをコード調査で確認した。** `RetryQueueItem.retry_attempt` → `RetryExecutionCoordinator.execute()`（`candidate.retry_attempt`を`getattr`で取得） → `RetryManager.retry(attempt=...)` → `RetryPolicy.should_retry(status, attempt)`という経路は無改修のまま機能しており、欠けていたのは`RetryEnqueueTrigger`がその値を解決してQueueへ渡す1箇所のみだった
- **`has_history()`ではなく`get()`のみを使用する設計とした。** `RetryHistoryManager` / `NullRetryHistoryManager`はいずれも`get()`を既に実装済みであり、新規依存は発生しない
- **Backward Compatibility を維持。** `RetryEnqueueTrigger.__init__`・`RetryEnqueueTriggerResult`・`__all__`はいずれも無変更であり、`history` / `guard`を渡さない既存の呼び出しは本Release前後でまったく同じ結果になる
- **`retry_queue` / `retry_history` / `retry_engine` / `workflow_monitor` / `retry_enqueue_guard.py`はいずれも本Releaseでも無改修。** 変更は`src/retry_enqueue_trigger/retry_enqueue_trigger.py`の1ファイルのみ
- **新たな制約（Known Issue）は本Releaseでも未解消のまま。** `RETRY_MAX_ATTEMPTS`（デフォルト3）を活かした複数回の自動リトライ運用は、本Release後も`RetryEnqueueTrigger`経由では実質的に機能しないままである。Guard判定基準の精緻化と組み合わせて初めて解消する（`docs/design/retry_attempt_synchronization_foundation.md` 4章 Known Issue）
- 対象外（今回も未実装）：`RetryEnqueueGuard`判定基準の精緻化・Composition Root・`.env.example`整備（いずれも将来Release候補。詳細は`docs/design/retry_attempt_synchronization_foundation.md` 1.3節）

### Tested

- `tests/test_e2e_v4_9_0_retry_attempt_synchronization_foundation.py`: 96/96 PASS
- 既存回帰確認：`v1.9.0`〜`v2.9.0`（Analytics Foundation `[KI-1]`除く）全PASS
- `v3.0.0`（206/208）・`v3.1.0`（152/152）・`v3.2.0`（100/102）・`v3.3.0`（71/72）・`v3.4.0`（94/94）・`v3.5.0`（71/72）・`v3.6.0`（102/104）・`v3.7.0`（74/74）・`v3.8.0`（67/70）・`v3.9.0`（70/73）・`v4.0.0`（83/88）・`v4.1.0`（84/87）・`v4.2.0`（91/94）・`v4.3.0`（105/108）・`v4.4.0`（120/123）・`v4.5.0`（63/64）・`v4.6.0`（98/100）：いずれも既存の`[KI-3]`〜`[KI-16]`による既知差分のみで、本Releaseによる新規差分はない
- `v4.7.0`（177/178、新規1件は`[KI-17]`参照）：`[KI-17]`にて説明
- `v4.8.0`（129/129 PASS）：本Releaseによる新規差分なし
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v4.8.0] - 2026-07-09 ★ Retry Enqueue Guard

### Added

- `src/retry_enqueue_trigger/retry_enqueue_guard.py`（新規）：再試行履歴（`has_history`）の有無から、enqueueを許可するか拒否するかを判定するだけの最小Deciderコンポーネント
  - `RetryEnqueueGuardOutcome`（`ALLOW` / `BLOCK`の2値Enum）
  - `RetryEnqueueGuardDecision`（`frozen=True`の`dataclass`）：`run_id` / `outcome` / `reason`の3フィールドのみを持つ
  - `RetryEnqueueGuard`：`decide(run_id, has_history) -> RetryEnqueueGuardDecision`の1メソッドのみを持つStatelessなコンポーネント。`RetryHistoryManager` / `NullRetryHistoryManager`型を一切importせず、`has_history: bool`という既に解決済みの値のみを入力とする（`RetryQueueUpdateDecider` / `RetryQueueCleanupDecider`と同じ設計言語）
  - `decide_all()`（バッチ版）・`NullRetryEnqueueGuard`はいずれも追加しない（呼び出し元は元々1件ずつループしており、Guardを無効化したい場合は`history`を省略することで既に完結しているため）
- `src/retry_enqueue_trigger/retry_enqueue_trigger.py`（変更）：`RetryEnqueueTrigger`が`RetryHistoryManager` / `NullRetryHistoryManager`・`RetryEnqueueGuard`をConstructor Injectionで保持できるようにし、以下を追加した
  - `RetryEnqueueTrigger.__init__`に`history` / `guard`引数（いずれもデフォルト`None`）を末尾に追加。省略時は`history`は`NullRetryHistoryManager()`（stateful storeのため`RetryManager`の`history`引数と同じ理由でNullへフォールバック）、`guard`は`RetryEnqueueGuard()`（Stateless・害のない実体のためデフォルトで実体を使う）にそれぞれ自動フォールバックする
  - `enqueue_pending_failures()`のループへ、`monitor_status`判定の直後・`queue.exists()`判定の直前に`self._history.has_history(record.run_id)` → `self._guard.decide(...)`の判定を追加した。`BLOCK`と判定された`run_id`は`queue.exists()` / `queue.enqueue()`のいずれにも到達しない
  - `RetryEnqueueTriggerResult`に`skipped_history: int = 0`フィールドを末尾のデフォルト値付きで追加した
  - `NullRetryEnqueueTrigger`は`skipped_history=0`を明示的に返すよう更新した（既存5フィールドと同じスタイルを踏襲）
- `src/retry_enqueue_trigger/__init__.py`（変更）：`RetryEnqueueGuard` / `RetryEnqueueGuardOutcome` / `RetryEnqueueGuardDecision`を新規export。既存の3シンボルは維持（計6シンボル）
- `tests/test_e2e_v4_8_0_retry_enqueue_guard.py`新規作成（129件）
- `docs/design/retry_enqueue_guard_charter.md`新規作成（Project Charter、ユーザー承認済み）
- `docs/design/retry_enqueue_guard.md`新規作成（Architecture Design。Architecture Review完了・**Approve**・ユーザー承認済み）

### Note

- **v4.6.0 Known Issue（無限再投入リスク）を解消した。** `RetryEnqueueTrigger`は`RetryQueueManager.exists()`による「Queue内に現在存在するか」の確認に加え、v4.8.0で`RetryHistoryManager.has_history()`を参照する`RetryEnqueueGuard`（「再試行履歴が1回でもあればブロック」の二値判定）を追加した。これにより、Queueから除去（`COMPLETE` / `FAIL` / `CLEANUP`）された後もWorkflow Monitor上で`FAILED` / `TIMEOUT`のまま観測され続ける`run_id`が、`enqueue_pending_failures()`が呼ばれるたびに無限に再enqueueされる問題を解消した（`docs/design/retry_enqueue_guard.md` 1章・11章）
- **対策が単なる改善ではなく安全性上必須であることをコード調査で確認した。** `RetryEnqueueTrigger.enqueue_pending_failures()`は`queue.enqueue()`呼び出し時に`retry_attempt`を渡しておらず常に`1`固定でQueueへ投入される。下流の`RetryExecutionCoordinator.execute()`はQueue項目由来のこの`1`をそのまま`RetryManager.retry()`の`attempt`引数として使うため、`RetryPolicy.should_retry()`は常に`attempt=1 < max_attempts（デフォルト3）`という条件で判定される。つまり`attempt`は実際の累積試行回数と連動しておらず、無対策のままComposition Root（定期実行）が実装されると、同一`run_id`のWorkflowが無制限に再実行されうる（News収集・WordPress下書き投稿等の実際の副作用込みで）。本Releaseの`RetryEnqueueGuard`はこれを止める唯一の現実的なセーフティネットである（`docs/design/retry_enqueue_guard_charter.md` 1章1.1節、ユーザー承認済み）
- **Guard判定は「履歴の有無」の二値のみとした（ユーザー承認済み方針）。** `RetryHistoryRecord.attempt_count`と`RetryPolicy.max_attempts`を比較する、より精密な判定も技術的には可能だが、`retry_enqueue_trigger`が`retry_engine`（`RetryPolicy`）へ新たに依存することになり、v4.6.0 Design Policy #2（`retry_engine`を経由しない）との整合性を崩す。また`attempt`が実回数と連動していない現状の構造では、これ以上精密な判定を導入しても正しく機能しない
- **新たな制約（Known Issue）が生じたことを明記する。** `RETRY_MAX_ATTEMPTS`（デフォルト3）を活かした複数回の自動リトライ運用は、`RetryEnqueueTrigger`経由では本Release後も実質的に機能しないままである（一度でも再試行履歴があれば以後は二度と自動enqueueされないため）。安全性を最優先する意図的な設計判断であり、複数回リトライを実現するには`attempt`の実回数連動を別Releaseで先に実装する必要がある（`docs/design/retry_enqueue_guard.md` 11章 Known Issue）
- **`history`省略時は`NullRetryHistoryManager()`にフォールバックし、Guardは常に`ALLOW`を返す。** これにより、本Releaseの新規引数を渡さない既存の呼び出し（v4.6.0時点の2引数コンストラクタ呼び出し）は、本Release後もv4.6.0時点とまったく同じ挙動になる
- **`RetryEnqueueGuard`は完全にStateless。** `RetryHistoryManager`等の外部パッケージ型を一切importせず、`has_history: bool`という既に解決済みの値のみを受け取る。外部ストアへの問い合わせ（`history.has_history()`の呼び出し）は`RetryEnqueueTrigger`側の責務として残した
- **Backward Compatibility を維持。** `RetryEnqueueTrigger.__init__`への引数追加・`RetryEnqueueTriggerResult`へのフィールド追加はいずれも末尾のデフォルト値付きのみであり、既存の呼び出し（新規引数を渡さない場合）は本Release後もまったく同じ結果になる
- **`workflow_monitor` / `retry_queue` / `retry_history` / `retry_engine`はいずれも本Releaseでも無改修。** 変更は`src/retry_enqueue_trigger/`配下3ファイル（新規1・変更2）のみ
- 対象外（今回も未実装）：`attempt`の実回数連動・Guard判定基準の精緻化（`max_attempts`比較）・Composition Root・`RetryHistoryManager`の永続化・Feature Gate/Configクラスの新設（いずれも将来Release候補。詳細は`docs/design/retry_enqueue_guard_charter.md` 10章、`docs/design/retry_enqueue_guard.md` 12章 Future Extension）

### Tested

- `tests/test_e2e_v4_8_0_retry_enqueue_guard.py`: 129/129 PASS
- 既存回帰確認：`v1.9.0`〜`v2.9.0`（Analytics Foundation `[KI-1]`除く）全PASS
- `v3.0.0`（206/208）・`v3.1.0`（152/152）・`v3.2.0`（100/102）・`v3.3.0`（71/72）・`v3.4.0`（94/94）・`v3.5.0`（71/72）・`v3.6.0`（102/104）・`v3.7.0`（74/74）・`v3.8.0`（67/70）・`v3.9.0`（70/73）・`v4.0.0`（83/88）・`v4.1.0`（84/87）・`v4.2.0`（91/94）・`v4.3.0`（105/108）・`v4.4.0`（120/123）・`v4.5.0`（63/64）：いずれも既存の`[KI-3]`〜`[KI-15]`による既知差分のみで、本Releaseによる新規差分はない（`retry_engine` / `retry_queue` / `retry_history` / `workflow_monitor` / `scheduler`等を一切変更していないため）
- `v4.6.0`（98/100、新規2件は`[KI-16]`参照）・`v4.7.0`（176/178、新規2件は`[KI-16]`参照）：`[KI-16]`にて説明
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v4.7.0] - 2026-07-09 ★ Retry History Foundation

### Added

- `src/retry_history/`（新規独立パッケージ）：`original_run_id`ごとの再試行履歴（試行回数・直近記録時刻）を記録・参照するだけの最小基盤
  - `RetryHistoryRecord`（`frozen=True`の`dataclass`）：`original_run_id` / `attempt_count` / `last_attempt` / `last_recorded_at`の4フィールドのみを持つ
  - `RetryHistoryManager`：`original_run_id`ごとの再試行履歴をin-memory dictで保持し、`record(original_run_id, attempt, recorded_at)` / `get(original_run_id)` / `has_history(original_run_id)`の3操作のみを提供する
  - `NullRetryHistoryManager`：Feature Gate・Configを持たず、Null Object Patternで無効状態を表現するダミー実装（`record()`は`None`を返す。`NullExecutionHistoryManager.start_run()`と同じ方針）
  - `retry_queue`と同型の独立した葉パッケージ。他のどの`src/*`パッケージ（`retry_engine`を含む）も一切importしない
- `src/retry_engine/retry_history_recorder.py`（新規）：`RetryExecutionResult`（v4.0.0）のリストを受け取り、`outcome`が`RETRIED`の項目についてのみ`record_fn`を呼び出し再試行履歴を記録する最小コンポーネント
  - `RetryHistoryRecordResult`（`frozen=True`の`dataclass`）：`execution_result` / `recorded` / `history_record` / `reason`の4フィールド
  - `RetryHistoryRecordExecutor`：`record(execution_result, record_fn)` / `record_all(execution_results, record_fn)`の2メソッドのみを持つStatelessなコンポーネント。`RetryHistoryManager` / `NullRetryHistoryManager`型を一切importせず、記録操作は`record_fn: Callable[[str, int, datetime], RetryHistoryRecord | None]`としてメソッド引数で受け取る（`RetryQueueRemovalExecutor`、v4.2.0と同じ設計言語）
- `src/retry_engine/retry_manager.py`（変更）：`RetryManager`が`RetryHistoryManager` / `NullRetryHistoryManager`・`RetryHistoryRecordExecutor`をConstructor Injectionで保持できるようにし、以下を追加した
  - `RetryManager.__init__` / `from_config()`に`history` / `history_recorder`（`from_config()`では`retry_history_manager` / `history_recorder`）引数（デフォルト`None`）を追加。省略時は`history`は`NullRetryHistoryManager()`（stateful storeのため`queue`と同じ理由でNullへフォールバック）、`history_recorder`は`RetryHistoryRecordExecutor()`にそれぞれ自動フォールバックする
  - `record_retry_history(events, dry_run=False) -> list[RetryHistoryRecordResult]`：`execute_dispatchable_retries()`（v4.0.0、無変更）への委譲・`RetryHistoryRecordExecutor.record_all()`への委譲の2段階のみで完結する
  - `NullRetryManager`にも同名`record_retry_history(events, dry_run=False)`を追加。専用コンポーネントを一切構築・参照せず、常に空リスト`[]`を返す
- `src/retry_engine/__init__.py`（変更）：`RetryHistoryRecordResult` / `RetryHistoryRecordExecutor`を新規export。既存の38シンボルは維持
- `tests/test_e2e_v4_7_0_retry_history_foundation.py`新規作成（178件）
- `docs/design/retry_history_foundation_charter.md`新規作成（Project Charter、承認済み）
- `docs/design/retry_history_foundation.md`新規作成（Architecture Design。Architecture Review完了・**Approve**）

### Note

- **`metadata["retried_from"]`は情報源として使用しない。** v4.6.0 Known Issue（`docs/design/retry_enqueue_trigger_foundation.md` 11章）が対策候補として挙げていた「`metadata["retried_from"]`を手掛かりにする」方式は、調査の結果**実際には機能しないことが判明した**。`RetryExecutor.execute()`（v3.0.0、無改修）は`WorkflowEngineEvent.metadata`に`retried_from` / `attempt`を積むが、`WorkflowEngineExecutor`はこの`metadata`を`ExecutionHistoryManager.start_run()`へ渡しておらず、`WorkflowExecutionRecord`（`execution_history/workflow_execution_record.py`）自体に`metadata`フィールドが存在しないため、`WorkflowMonitorRecord`からも参照できない。本Releaseはこの事実を踏まえ、情報源を`RetryResult`（`retry_engine`自身が生成するデータ）に限定し、`execution_history`パッケージには一切触れない設計とした
- **記録基盤のみ。無限再投入対策は本Releaseでは未解消のまま。** `record_retry_history()`はどこからも呼ばれない（`RetryEnqueueTrigger`、v4.6.0は本Releaseでも無改修）。記録結果を使って`RetryEnqueueTrigger.enqueue_pending_failures()`側の再enqueueを止める判定（無限再投入対策の完成）は次Release（Retry Enqueue Guard）に送った（Foundation First、`docs/design/retry_history_foundation.md` 7.1節・10章）
- **Feature Gate・Configクラスは追加しない。** `retry_history`パッケージにはそもそもFeature Gateという概念自体を持たせなかった。`history`引数省略時のフォールバック先（`NullRetryHistoryManager()`）は、`RetryHistoryManager`がstateful storeであることから`RetryQueueManager`（`queue`引数）と同じ扱いとした
- **`retry_history`は`retry_engine`を一切importしない。** 循環importは発生しない
- **`RetryManager`の変更は薄い委譲に留めた。** `record_retry_history()`は2行の委譲のみで完結し、記録ロジック自体は`RetryManager`に書いていない
- **Backward Compatibility を維持。** `RetryManager.__init__` / `from_config()`への引数追加は末尾のデフォルト値付きのみであり、既存の呼び出し（新規引数を渡さない場合）は本Release後もまったく同じ結果になる。`retry()` 〜 `apply_retry_queue_terminal_cleanup()`までの既存メソッド（`RetryManager` / `NullRetryManager`とも）は1行も変更していない
- **`scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_event_consumer.py` / `retry_event_dispatcher.py` / `retry_execution_selector.py` / `retry_execution_coordinator.py` / `retry_queue_update_decider.py` / `retry_queue_removal_executor.py` / `retry_queue_cleanup_decider.py` / `retry_queue_cleanup_executor.py` / `retry_queue_terminal_cleanup_decider.py` / `retry_queue_terminal_cleanup_executor.py` / `retry_outcome_terminality.py` / `retry_policy.py` / `retry_policy_protocol.py` / `retry_enqueue_trigger`はいずれも本Releaseでも無改修。** 変更は`retry_engine`配下2ファイル（新規1・変更1）と`__init__.py`、および新規独立パッケージ`src/retry_history/`（3ファイル）のみ
- 対象外（今回も未実装）：`RetryEnqueueTrigger`側の消費（無限再投入ガード）・`RetryPolicy.max_attempts`との統合判定・Composition Root・永続化（いずれも将来Release候補。詳細は`docs/design/retry_history_foundation_charter.md` 10章、`docs/design/retry_history_foundation.md` 10章 Future Extension）

### Tested

- `tests/test_e2e_v4_7_0_retry_history_foundation.py`: 178/178 PASS
- 既存回帰確認：`v1.9.0`〜`v2.9.0`（Analytics Foundation `[KI-1]`除く）全PASS
- `git stash`によるベースライン比較（v4.6.0時点の状態と本Release適用後を比較し、本Release固有の新規差分のみを特定済み）：
  - `v3.1.0`（151/152、新規1件は`git diff`ベースの一時差分）・`v3.2.0`（99/102、新規1件は同上）・`v3.3.0`（69/72、新規2件は同上）・`v3.4.0`（92/94、新規2件は同上）・`v3.5.0`（69/72、新規2件は同上）・`v3.6.0`（100/104、新規2件は同上）・`v3.7.0`（72/74、新規2件は同上）：いずれも`retry_manager.py` / `__init__.py`の未コミット差分による一時的なFAILのみで、commit後は自然解消する見込み
  - `v3.0.0`（206/208）・`v3.8.0`（67/70）・`v3.9.0`（70/73）・`v4.0.0`（83/88）・`v4.1.0`（84/87）・`v4.2.0`（91/94）・`v4.3.0`（105/108）：本Releaseによる新規差分なし（既存の`[KI-3]`〜`[KI-14]`による既知差分のみ）
  - `v4.4.0`（120/123、新規2件）・`v4.5.0`（63/64、新規1件）：`[KI-15]`参照（本Release固有の恒久差分）
  - `v4.6.0`（87/89、新規2件は`git diff`ベースの一時差分）
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v4.6.0] - 2026-07-09 ★ Retry Enqueue Trigger Foundation

### Added

- `src/retry_enqueue_trigger/`（新規パッケージ）：`WorkflowMonitorManager`（v2.9.0、無改修）が判定した`FAILED` / `TIMEOUT`のWorkflowを検知し、まだ`RetryQueueManager`（v3.1.0、無改修）に存在しないものだけを`enqueue()`する最小Adapter
  - `RetryEnqueueTriggerResult`（`frozen=True`の`dataclass`）：`scanned` / `enqueued` / `skipped_existing` / `skipped_status` / `failed`の5フィールドのみを持つ集計結果
  - `RetryEnqueueTrigger`：`WorkflowMonitorManager` / `RetryQueueManager`をConstructor Injectionで保持し、`enqueue_pending_failures(limit=None) -> RetryEnqueueTriggerResult`の1メソッドのみを公開するStatelessなコンポーネント
  - `NullRetryEnqueueTrigger`：Feature Gate・Configを持たず、Null Object Patternで無効状態を表現するダミー実装（`RetrySchedulerSource` / `NullRetrySchedulerSource`、v3.3.0と同じ設計言語）。`workflow_monitor` / `retry_queue`への参照を一切保持せず、常に全フィールド0の結果を返す
  - `retry_engine`は経由せず、`workflow_monitor` / `retry_queue`の2パッケージに直接依存する新規構成（`retry_scheduler_source → retry_queue`と同じ「下位パッケージへの直接依存」パターン）
- `tests/test_e2e_v4_6_0_retry_enqueue_trigger_foundation.py`新規作成（89件）
- `docs/design/retry_enqueue_trigger_foundation_charter.md`新規作成（Project Charter、承認済み）
- `docs/design/retry_enqueue_trigger_foundation.md`新規作成（Architecture Design。Architecture Review完了・**Approve**）

### Note

- **v3.0.0〜v4.5.0の16回のReleaseで構築されたRetry Queue〜Retry Engineの下流パイプラインは、`RetryQueueManager.enqueue()` / `RetryManager.enqueue_retry()`がコードベースのどこからも呼び出されておらず、実データを一度も受け取ったことがなかった。** 本Releaseはこの「Queueへ実際に投入する主体がいない」というギャップを埋める新規Adapterを追加した（`docs/design/retry_enqueue_trigger_foundation_charter.md` 1章）
- **Feature Gate・Configクラスは追加しない。** `RetryEnqueueTrigger` / `NullRetryEnqueueTrigger`のどちらを構築するかを呼び出し元が選ぶ、既存の`RetrySchedulerSource`（v3.3.0）と同じNull Object Patternを踏襲した
- **`retry_engine`を経由しない設計とした。** `RetryQueueManager.enqueue()`へ直接依存することで、`RETRY_ENGINE_ENABLED=false`（デフォルト）の状態でもQueueへの投入自体は可能な構造とした（Queueへの投入自体は外部副作用を伴わないメモリ操作であるため。実際にRetryを実行するかは引き続き下流の`RetryConfig.enabled`で止まる）
- **Queue内の重複防止は`RetryQueueManager.exists()`のみ。** 一度Queueから除去された`run_id`が、Workflow Monitor上でなお`FAILED` / `TIMEOUT`のまま観測され続けるケースへの対策（無限再投入リスク）は、本Releaseでは意図的に実装しない（ユーザー確定方針）。原因（`RetryExecutor`が再実行のたびに新しい`run_id`を発行するため、元`run_id`のExecution History記録・Monitor判定は不変であること）と将来の対策候補（`metadata["retried_from"]`を手掛かりにした「Retry History」コンポーネントの新設等）は`docs/design/retry_enqueue_trigger_foundation.md` 11章 Known Issueに記録した
- **一括処理結果は最小の集計`dataclass`のみ。** 理由文字列の列挙・例外的なケース分岐は追加しない（ユーザー確定方針）
- **`workflow_monitor` / `retry_queue` / `retry_engine`はいずれも本Releaseでも無改修（ゼロ改修）。** 新規パッケージの追加のみ
- 対象外（今回も未実装）：新設Adapterを定期的に駆動する起動スクリプト（Composition Root）・無限再投入対策（Retry History）・`dequeue()`の解禁・Retry Queueの永続化・Retry Strategy（`FixedRetryPolicy`等）の実装（いずれも将来Release候補。詳細は`docs/design/retry_enqueue_trigger_foundation_charter.md` 10章、`docs/design/retry_enqueue_trigger_foundation.md` 12章 Future Extension）

### Tested

- `tests/test_e2e_v4_6_0_retry_enqueue_trigger_foundation.py`: 89/89 PASS
- 既存回帰確認：`v1.9.0`〜`v2.9.0`（Analytics Foundation `[KI-1]`除く）全PASS、`v3.1.0`（152/152）・`v3.4.0`（94/94）・`v3.7.0`（74/74）・`v4.5.0`（64/64）全PASS
- `v3.0.0`（200/202）・`v3.2.0`（100/102）・`v3.3.0`（71/72）・`v3.5.0`（71/72）・`v3.6.0`（102/104）・`v3.8.0`（67/70）・`v3.9.0`（70/73）・`v4.0.0`（83/88）・`v4.1.0`（84/87）・`v4.2.0`（91/94）・`v4.3.0`（105/108）・`v4.4.0`（122/123）：いずれも既存の`[KI-3]`〜`[KI-14]`による既知差分のみで、`git stash`によるベースライン比較（本Release適用前と適用後で件数・FAIL内容が完全一致）により本Releaseによる新規差分がないことを確認済み
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v4.5.0] - 2026-07-08 ★ Retry Policy Foundation

### Added

- `src/retry_engine/retry_policy_protocol.py`（新規）：`RetryManager`が実際に依存している面（`retry()`が呼び出す`should_retry()`、`_skip_reason()`が参照する`target_statuses` / `max_attempts`）をProtocolとして明示化した新規モジュール
  - `RetryDecisionPolicy`（`Protocol`、`@runtime_checkable`）：`should_retry(monitor_status, attempt) -> bool`のみを要求する最小契約
  - `ExplainableRetryPolicy`（`Protocol`、`@runtime_checkable`。`RetryDecisionPolicy`を拡張）：`target_statuses` / `max_attempts`を追加した、スキップ理由の説明に必要な属性を公開する契約
- `src/retry_engine/retry_manager.py`（変更）：`RetryManager.__init__` / `from_config()`の`policy` / `retry_policy`引数の型注釈を、具体クラス`RetryPolicy`から抽象契約`ExplainableRetryPolicy`へ変更した
  - `retry()` / `_skip_reason()`のロジック本体は1行も変更していない
  - 不要になった`from .retry_policy import RetryPolicy`のimportを削除した
- `src/retry_engine/__init__.py`（変更）：`RetryDecisionPolicy` / `ExplainableRetryPolicy`を新規export。既存の36シンボルは維持
- `tests/test_e2e_v4_5_0_retry_policy_foundation.py`新規作成（64件）
- `docs/design/retry_policy_foundation_charter.md`新規作成（Project Charter、承認済み）
- `docs/design/retry_policy_foundation.md`新規作成（Architecture Design。Architecture Review完了・**Approve with Recommendations**、指摘事項4点をすべて反映済み）

### Note

- **既存`RetryPolicy`（`retry_policy.py`）は本Releaseでも無改修（0 diff）。** Protocolの性質上、明示的な継承なしに構造的に`RetryDecisionPolicy` / `ExplainableRetryPolicy`の両方を満たす（テスト1-3で確認済み）
- **契約を2段階に分離した（Architecture Design 4章 案C）。** `RetryDecisionPolicy`（`should_retry()`のみ）と`ExplainableRetryPolicy`（`RetryDecisionPolicy`を拡張し、`_skip_reason()`が実際に依存する`target_statuses` / `max_attempts`を追加）に分けることで、将来`target_statuses` / `max_attempts`という概念を持たない戦略（例：`ExponentialBackoffPolicy`）は`RetryDecisionPolicy`のみを満たせばよい構造にした（テスト5-6で確認済み）
- **新しいRetry戦略（`FixedRetryPolicy` / `ExponentialBackoffPolicy` / `AdaptiveRetryPolicy`等）の実装は本Releaseの対象外（Non-Goal）。** 本Releaseは差し替え可能な構造の整備のみを行った（テスト14で確認済み）
- **`RetryManager`の変更は型注釈のみ。** `retry()` / `_skip_reason()`の本体は1行も変更していない。Pythonは型注釈を実行時に強制しないため、既存の`RetryManager(policy=RetryPolicy(...), ...)`呼び出しは本Release前後でまったく同じ結果になる（テスト10で回帰的に確認済み）
- **`@runtime_checkable`を付与し、`isinstance()`による構造適合確認を可能にした。** ただし`isinstance()`はメソッド・属性の存在のみを検証しシグネチャまでは検証しないため、`RetryManager(policy=fake, ...).retry(...)`を実際に呼び出す振る舞いテストを併用した（テスト7-9、Architecture Review 12.5節 Recommendation 3）
- **`scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_engine`配下の既存ファイル（v4.4.0までに追加されたもの含む）はいずれも本Releaseでも無改修。** 変更は`retry_engine`配下2ファイル（新規1・変更1）のみ
- 対象外（今回も未実装）：新しいRetry戦略の実装・複数戦略を切り替えるComposition Root・`_skip_reason()`の`target_statuses` / `max_attempts`依存の解消・Retry Queue / Cleanup系列への変更（いずれも将来Release候補。詳細は`docs/design/retry_policy_foundation_charter.md` 10章、`docs/design/retry_policy_foundation.md` 8章 Boundary・9章 Future Extension）

### Architecture Review Recommendations（反映済み）

- **Recommendation 1**：`retry_policy_protocol.py`のモジュールdocstringに、既存`RetryPolicy`（具体実装）との関係・混同注意を明記した
- **Recommendation 2**：`retry_manager.py`実装時、型注釈変更に伴い不要になった`RetryPolicy`のimportを削除した
- **Recommendation 3**：`isinstance()`は構造確認のみであり、振る舞いテストと併用することを設計書・テストの両方に明記した
- **Recommendation 4**：`retry_manager.py` / `__init__.py`のモジュールdocstringにv4.5.0分の設計メモを追記した

### Tested

- `tests/test_e2e_v4_5_0_retry_policy_foundation.py`: 64/64 PASS
- 既存回帰確認：`v1.9.0`〜`v2.9.0`（Analytics Foundation `[KI-1]`除く）全PASS
- `v3.0.0`（200/202）・`v3.1.0`（151/152）・`v3.2.0`（99/102）・`v4.0.0`（83/88）・`v4.1.0`（84/87）・`v4.2.0`（91/94）・`v4.3.0`（105/108）：いずれも既存の`[KI-3]`〜`[KI-13]`による既知差分のみで、本Releaseで変化なし
- `v4.4.0`（122/123、新規1件は`[KI-14]`参照）：`git stash`によるベースライン比較（`v4.4.0`は本Release適用前123/123 PASSであったことを確認済み）で、本Release固有の新規差分を特定済み
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v4.4.0] - 2026-07-08 ★ NOT_FOUND / DISABLED Cleanup Foundation

### Added

- `src/retry_engine/retry_outcome_terminality.py`（新規）：各`RetryOutcome`が「Terminal（終端状態）」か「Transient（一時状態）」かを分類する、v4.4.0新規Deciderに対するSingle Source of Truth
  - `RetryOutcomeTerminality`（`TERMINAL` / `TRANSIENT`の2値Enum）
  - `RetryCleanupReason`（`COMPLETE` / `FAIL` / `SKIPPED` / `NOT_FOUND` / `DISABLED`の5値Enum。Cleanup判定のための判定起源を表す）
  - `RETRY_OUTCOME_TERMINALITY`（`RetryCleanupReason`ごとの分類表。`NOT_FOUND`は`TERMINAL`、`DISABLED`は`TRANSIENT`）
  - `classify_reason(update_decision) -> RetryCleanupReason` / `classify_terminality(reason) -> RetryOutcomeTerminality`の2関数
  - **権威範囲の限定**：本モジュールはv4.4.0新規Deciderに対してのみ権威を持つ。v4.1.0〜v4.3.0の既存コンポーネントはゼロ改修方針のため本モジュールを参照しない（Architecture Review 12.1節 Recommendation 1）
- `src/retry_engine/retry_queue_terminal_cleanup_decider.py`（新規）：`RetryQueueUpdateDecider`（v4.1.0）が判定した`RetryQueueUpdateDecision`のリストを受け取り、`outcome`が`NOOP`かつ対応する`retry_result.outcome`が`NOT_FOUND` / `DISABLED`の項目のみを対象に、`RETRY_OUTCOME_TERMINALITY`分類表を参照して`CLEANUP`/`KEEP`を判定する新規コンポーネント（`COMPLETE` / `FAIL` / `SKIPPED`由来は構造的にKEEPとして対象外）
  - `RetryQueueTerminalCleanupDecision`（`frozen=True`の`dataclass`）：`update_decision`・`outcome`（v4.3.0`RetryQueueCleanupOutcome`を再利用）・`reason`の3フィールド
  - `RetryQueueTerminalCleanupDecider`：`decide(update_decision) -> RetryQueueTerminalCleanupDecision` / `decide_all(update_decisions) -> list[RetryQueueTerminalCleanupDecision]`の2メソッドのみを持つStatelessなコンポーネント。`RetryQueueManager` / `NullRetryQueueManager`型を一切importしない
- `src/retry_engine/retry_queue_terminal_cleanup_executor.py`（新規）：`RetryQueueTerminalCleanupDecider`が判定した`RetryQueueTerminalCleanupDecision`のリストを受け取り、`outcome`が`CLEANUP`の項目についてのみ`RetryQueueManager.remove()`を呼び出し、Queueから該当項目を除去する新規コンポーネント
  - `RetryQueueTerminalCleanupResult`（`frozen=True`の`dataclass`）：`decision`・`attempted`・`queue_result`・`reason`の4フィールド
  - `RetryQueueTerminalCleanupExecutor`：`apply(decision, remove_fn) -> RetryQueueTerminalCleanupResult` / `apply_all(decisions, remove_fn) -> list[RetryQueueTerminalCleanupResult]`の2メソッドのみを持つStatelessなコンポーネント。remove操作は`remove_fn: Callable[[str], RetryQueueResult]`としてメソッド引数で受け取る
- `src/retry_engine/retry_manager.py`（変更）：`RetryManager`が`RetryQueueTerminalCleanupDecider` / `RetryQueueTerminalCleanupExecutor`をConstructor Injectionで保持できるようにし、以下を追加した
  - `RetryManager.__init__` / `from_config()`に`terminal_cleanup_decider` / `terminal_cleanup_executor`引数（デフォルト`None`）を追加。省略時はそれぞれ自動フォールバックする
  - `decide_retry_queue_terminal_cleanup(events, dry_run=False) -> list[RetryQueueTerminalCleanupDecision]`：`decide_retry_queue_updates()`（v4.1.0、無変更）への委譲・`RetryQueueTerminalCleanupDecider.decide_all()`への委譲の2段階のみで完結する
  - `apply_retry_queue_terminal_cleanup(events, dry_run=False) -> list[RetryQueueTerminalCleanupResult]`：`decide_retry_queue_terminal_cleanup()`への委譲・`RetryQueueTerminalCleanupExecutor.apply_all(decisions, remove_fn=self._queue.remove)`への委譲の2段階のみで完結する。これにより、v4.3.0では対象外だった`NOT_FOUND`由来の`NOOP`項目についても、初めて`RetryQueueManager.remove()`が呼び出し可能になった
  - `NullRetryManager`にも同名2メソッドを追加。専用コンポーネントを一切構築・参照せず、常に空リスト`[]`を返す
- `src/retry_engine/__init__.py`（変更）：`RetryOutcomeTerminality` / `RetryCleanupReason` / `RETRY_OUTCOME_TERMINALITY` / `classify_reason` / `classify_terminality` / `RetryQueueTerminalCleanupDecision` / `RetryQueueTerminalCleanupDecider` / `RetryQueueTerminalCleanupResult` / `RetryQueueTerminalCleanupExecutor`を新規export。既存の26シンボルは維持
- `tests/test_e2e_v4_4_0_retry_queue_notfound_disabled_cleanup_foundation.py`新規作成（123件）
- `docs/design/retry_queue_notfound_disabled_cleanup_foundation_charter.md`新規作成（Project Charter、承認済み）
- `docs/design/retry_queue_notfound_disabled_cleanup_foundation.md`新規作成（Architecture Design。Architecture Review完了・**Approve with Recommendations**、指摘事項4点をすべて反映済み）

### Note

- **v4.3.0のCharter・設計書で次Release以降の検討事項として持ち越されていた「`NOT_FOUND` / `DISABLED`由来の`NOOP`のCleanup方針の検討」に、本Releaseで着手した。** 個別のoutcomeごとの是非ではなく、「Terminal（終端状態）かTransient（一時状態）か」という上位概念でまず分類し、Cleanup方針（CLEANUP/KEEP）をその分類から機械的に導出する設計とした（ユーザー指示）
- **`NOT_FOUND`はTerminalと判定し、CLEANUP対象とした。** 根拠：(1) `ExecutionHistoryStore`に削除操作が存在せず、一度foundになったレコードが再びNOT_FOUNDに戻ることはない（不可逆）、(2) `enqueue_retry()`の無検証・自動Composition Root未整備という現状のコードベースには、NOT_FOUNDだった`run_id`が後から自動的にfoundへ遷移する経路が存在しない、(3) 正当な運用下でのRetry候補は概念上既にレコードを持っているはずである（テスト7・31で回帰的に確認済み）
- **`DISABLED`はTransientと判定し、KEEPのまま据え置いた。** `RETRY_ENGINE_ENABLED`という判定時点の設定値のスナップショットに過ぎず、運用者が後から変更しうるため。この判断は`RetryQueueManager`がメモリ上の`dict`のみで構成されQueue永続化がNon-Goalのままであることを前提としており、将来Queue永続化が実装された場合は要再評価（テスト8・33で回帰的に確認済み）
- **`RetryOutcomeTerminality`分類表を、v4.4.0新規Deciderに対してのみ権威を持つSingle Source of Truthとして導入した。** v4.1.0〜v4.3.0の既存コンポーネント（`COMPLETE` / `FAIL` / `SKIPPED`の判定）はゼロ改修方針のため本表を参照しないが、整合性ガードテスト（テスト5-6）で両者の分類結果が一致することを確認済み（Architecture Review 12.1節 Recommendation 1）
- **命名の相互参照をdocstringに明記した。** `RetryQueueTerminalCleanupDecider` / `Executor`は、v4.3.0の`RetryQueueCleanupDecider` / `Executor`（`SKIPPED`専用）とは別の新規コンポーネントであり、混同しないことをモジュールdocstring冒頭に明記した（Architecture Review 12.2節 Recommendation 2）
- **新しいQueueステータス（Dead Letter Queue・隔離Queue等）は追加しなかった。** 既存の`RetryQueueManager.remove()`をそのまま再利用した
- **`RetryManager`の変更は薄い委譲に留めた。** `decide_retry_queue_terminal_cleanup()` / `apply_retry_queue_terminal_cleanup()`はいずれも2行の委譲のみで完結し、判定・除去ロジック自体は`RetryManager`に書いていない
- **Backward Compatibility を維持。** `RetryManager.__init__` / `from_config()`への引数追加は末尾のデフォルト値付き引数のみであり、既存の呼び出し（新規引数を渡さない場合）は本Release後もまったく同じ結果になる。`retry()` 〜 `apply_retry_queue_cleanup()`までの既存メソッド（`RetryManager` / `NullRetryManager`とも）は1行も変更していない（テスト41で回帰的に確認済み）
- **`scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_queue_update_decider.py` / `retry_queue_removal_executor.py` / `retry_queue_cleanup_decider.py` / `retry_queue_cleanup_executor.py`はいずれも本Releaseでも無改修。** 変更は`retry_engine`配下4ファイル（新規3・変更1）と`__init__.py`のみ
- 対象外（今回も未実装）：Dead Letter Queue・Queue永続化・Retry Policy拡張・Retry Metrics・Queue最適化・Scheduler改修・実運用のComposition Root・`DISABLED`解消後の自動再試行（いずれも将来Release候補。詳細は`docs/design/retry_queue_notfound_disabled_cleanup_foundation_charter.md` 10章、同設計書9章 Future Extension）

### Architecture Review Recommendations（反映済み）

- **Recommendation 1**：`RETRY_OUTCOME_TERMINALITY`の「Single Source of Truth」の権威範囲をv4.4.0新規Deciderに限定する旨をdocstring・設計書に明記し、`COMPLETE` / `FAIL` / `SKIPPED`について本分類表とv4.2.0 / v4.3.0の実際の挙動が一致することを確認する整合性ガードテスト（テスト5-6）を追加した
- **Recommendation 2**：`RetryQueueTerminalCleanupDecider` / `Executor`のモジュールdocstringに、v4.3.0`RetryQueueCleanupDecider` / `Executor`との相互参照（混同注意）を明記した
- **Recommendation 3**：`NOT_FOUND`分類の見直し条件を「Composition Root整備時」ではなく、「`enqueue_retry()`への参照整合性チェック追加」または「未実行run_idを正当な候補とする新機能追加」時として、設計書4.3節・`retry_outcome_terminality.py`docstringの両方に正確に記載した
- **Recommendation 4**：`DISABLED`＝Keepの判断が`RetryQueueManager`のin-memory dict実装を前提とすることを明記し、将来Queue永続化導入時の再評価が必要であることを設計書3.2節・9章の両方に記録した

### Tested

- `tests/test_e2e_v4_4_0_retry_queue_notfound_disabled_cleanup_foundation.py`: 123/123 PASS
- 既存回帰確認：`v1.9.0`〜`v2.9.0`（Analytics Foundation `[KI-1]`除く）全PASS
- `v4.1.0`（84/87、`[KI-11]`による既存差分のみ、本Releaseで変化なし）・`v4.2.0`（91/94、`[KI-12]`による既存差分のみ、本Releaseで変化なし）・`v4.3.0`（105/108、新規3件は`[KI-13]`参照）：`git stash`によるベースライン比較（`v4.3.0`は本Release適用前108/108 PASSであったことを確認済み）で、本Release固有の新規差分を特定済み
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v4.3.0] - 2026-07-08 ★ Retry Queue Cleanup Foundation

### Added

- `src/retry_engine/retry_queue_cleanup_decider.py`（新規）：`RetryQueueUpdateDecider`（v4.1.0）が判定した`RetryQueueUpdateDecision`のリストを受け取り、`outcome`が`NOOP`かつ対応する`retry_result.outcome`が`SKIPPED`の項目のみを`CLEANUP`、それ以外（`COMPLETE` / `FAIL`、および`NOOP`でも`NOT_FOUND` / `DISABLED`由来）を`KEEP`と判定する最小コンポーネント
  - `RetryQueueCleanupOutcome`（`CLEANUP` / `KEEP`の2値Enum）
  - `RetryQueueCleanupDecision`（`frozen=True`の`dataclass`）：`update_decision`（元の`RetryQueueUpdateDecision`をそのまま保持）・`outcome`・`reason`の3フィールド
  - `RetryQueueCleanupDecider`：`decide(update_decision) -> RetryQueueCleanupDecision` / `decide_all(update_decisions) -> list[RetryQueueCleanupDecision]`の2メソッドのみを持つStatelessなコンポーネント。`RetryQueueManager` / `NullRetryQueueManager`型を一切importしない
- `src/retry_engine/retry_queue_cleanup_executor.py`（新規）：`RetryQueueCleanupDecider`が判定した`RetryQueueCleanupDecision`のリストを受け取り、`outcome`が`CLEANUP`の項目についてのみ`RetryQueueManager.remove()`を呼び出し、Queueから該当項目を除去する最小コンポーネント
  - `RetryQueueCleanupResult`（`frozen=True`の`dataclass`）：`decision`・`attempted`・`queue_result`・`reason`の4フィールド（v4.2.0`RetryQueueRemovalResult`と同型）
  - `RetryQueueCleanupExecutor`：`apply(decision, remove_fn) -> RetryQueueCleanupResult` / `apply_all(decisions, remove_fn) -> list[RetryQueueCleanupResult]`の2メソッドのみを持つStatelessなコンポーネント。remove操作は`remove_fn: Callable[[str], RetryQueueResult]`としてメソッド引数で受け取る（v4.2.0`RetryQueueRemovalExecutor`と同じパターン）
- `src/retry_engine/retry_manager.py`（変更）：`RetryManager`が`RetryQueueCleanupDecider` / `RetryQueueCleanupExecutor`をConstructor Injectionで保持できるようにし、以下を追加した
  - `RetryManager.__init__` / `from_config()`に`queue_cleanup_decider` / `queue_cleanup_executor`引数（デフォルト`None`）を追加。省略時はそれぞれ自動フォールバックする
  - `decide_retry_queue_cleanup(events, dry_run=False) -> list[RetryQueueCleanupDecision]`：`decide_retry_queue_updates()`（v4.1.0、無変更）への委譲・`RetryQueueCleanupDecider.decide_all()`への委譲の2段階のみで完結する
  - `apply_retry_queue_cleanup(events, dry_run=False) -> list[RetryQueueCleanupResult]`：`decide_retry_queue_cleanup()`への委譲・`RetryQueueCleanupExecutor.apply_all(decisions, remove_fn=self._queue.remove)`への委譲の2段階のみで完結する。これにより、v4.2.0では対象外だった`SKIPPED`由来の`NOOP`項目についても、初めて`RetryQueueManager.remove()`が呼び出し可能になった
  - `NullRetryManager`にも同名2メソッドを追加。専用コンポーネントを一切構築・参照せず、常に空リスト`[]`を返す
- `src/retry_engine/__init__.py`（変更）：`RetryQueueCleanupOutcome` / `RetryQueueCleanupDecision` / `RetryQueueCleanupDecider` / `RetryQueueCleanupResult` / `RetryQueueCleanupExecutor`を新規export。既存の21シンボルは維持
- `tests/test_e2e_v4_3_0_retry_queue_cleanup_foundation.py`新規作成（108件）
- `docs/design/retry_queue_cleanup_foundation_charter.md`新規作成（Project Charter、承認済み）
- `docs/design/retry_queue_cleanup_foundation.md`新規作成（Architecture Design。Architecture Review完了・**Approve with Recommendations**、指摘事項1点を記録）

### Note

- **v4.2.0のCharterで次Release以降の検討事項として持ち越されていた「`SKIPPED`のQueue滞留対応」に、本Releaseで着手した。** `SKIPPED`（`max_attempts`到達）由来の`NOOP`項目は、本Release後は`apply_retry_queue_cleanup()`経由でQueueから除去できる（テスト25で回帰的に確認済み）
- **Cleanup対象は`SKIPPED`のみに意図的に限定した。** `COMPLETE` / `FAILED`（v4.2.0で既に除去済みのはず）、および`NOOP`でも`NOT_FOUND` / `DISABLED`由来の項目は、いずれも本Releaseでも`KEEP`のままQueueに残り続ける（テスト26-27で回帰的に確認済み）。ユーザー承認済みのProject Charterに基づくスコープ限定であり、見落としではない
- **新しいQueueステータス（Dead Letter Queue・隔離Queue等）は追加しなかった。** 既存の`RetryQueueManager.remove()`（v3.1.0、`status=CANCELLED`に更新後削除）をそのまま再利用した
- **`RetryQueueCleanupDecider` / `RetryQueueCleanupExecutor`はいずれも`RetryQueueManager`型への直接依存を一切持たない。** Decider側は`RetryQueueUpdateDecision`（既存データ）のみを入力とし、Executor側のremove操作は`remove_fn: Callable[[str], RetryQueueResult]`としてメソッド引数で受け取る。v4.0.0`RetryExecutionCoordinator`・v4.2.0`RetryQueueRemovalExecutor`と同じ設計言語を継承した
- **`RetryManagerの変更は薄い委譲に留めた。** `decide_retry_queue_cleanup()` / `apply_retry_queue_cleanup()`はいずれも2行の委譲のみで完結し、判定・除去ロジック自体は`RetryManager`に書いていない
- **Backward Compatibility を維持。** `RetryManager.__init__` / `from_config()`への引数追加は末尾のデフォルト値付き引数のみであり、既存の呼び出し（新規引数を渡さない場合）は本Release後もまったく同じ結果になる。`retry()` 〜 `apply_retry_queue_removals()`までの既存メソッド（`RetryManager` / `NullRetryManager`とも）は1行も変更していない
- **`scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_queue_update_decider.py` / `retry_queue_removal_executor.py`はいずれも本Releaseでも無改修。** 変更は`retry_engine`配下3ファイル（新規2・変更1）と`__init__.py`のみ
- 対象外（今回も未実装）：`NOT_FOUND` / `DISABLED`由来の`NOOP`のCleanup方針・Dead Letter Queue・Queue永続化・Retry Policy拡張・Retry Metrics・Queue最適化・Scheduler改修・実運用のComposition Root（いずれも将来Release候補。詳細は`docs/design/retry_queue_cleanup_foundation_charter.md` 9章、`docs/design/retry_queue_cleanup_foundation.md` 8章）

### Architecture Review Recommendations（反映済み）

- **`CLEANUP`パターンと`KEEP`パターン双方の独立した単体テスト**：`CLEANUP`（テスト1・10・25）、`KEEP`のうち`COMPLETE`（テスト4・11・26）・`FAIL`（テスト5）・`NOT_FOUND`由来（テスト2・27）・`DISABLED`由来（テスト3）をそれぞれ独立したテストとして固定化し、Spyオブジェクト（`FakeRetryQueueManager`）・実`RetryQueueManager`の両方で`remove_fn`の呼び出し有無を確認済み

### Tested

- `tests/test_e2e_v4_3_0_retry_queue_cleanup_foundation.py`: 108/108 PASS
- 既存回帰確認：`v1.9.0`〜`v2.9.0`（Analytics Foundation `[KI-1]`除く）全PASS
- `v4.1.0`（84/87、`[KI-11]`による既存差分のみ）・`v4.2.0`（91/94、新規3件は`[KI-12]`参照）：`git stash`によるベースライン比較（`v4.2.0`は本Release適用前94/94 PASSであったことを確認済み）で、本Release固有の新規差分を特定済み
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v4.2.0] - 2026-07-06 ★ Retry Queue Removal Foundation

### Added

- `src/retry_engine/retry_queue_removal_executor.py`（新規）：`RetryQueueUpdateDecider`（v4.1.0）が判定した`RetryQueueUpdateDecision`のリストを受け取り、`outcome`が`COMPLETE`または`FAIL`の項目についてのみ`RetryQueueManager.remove()`を呼び出し、Queueから該当項目を除去する最小コンポーネント
  - `RetryQueueRemovalResult`（`frozen=True`の`dataclass`）：`decision`（元の`RetryQueueUpdateDecision`をそのまま保持）・`attempted`（remove呼び出しを試行したか）・`queue_result`（`remove_fn`の戻り値、未試行時は`None`）・`reason`の4フィールド
  - `RetryQueueRemovalExecutor`：`apply(decision, remove_fn) -> RetryQueueRemovalResult` / `apply_all(decisions, remove_fn) -> list[RetryQueueRemovalResult]`の2メソッドのみを持つStatelessなコンポーネント。コンストラクタ引数を一切取らず、`RetryQueueManager` / `NullRetryQueueManager`型を一切importしない。remove操作は`remove_fn: Callable[[str], RetryQueueResult]`としてメソッド引数で受け取る（v4.0.0`RetryExecutionCoordinator`の`retry_fn`と同じパターン）。`run_id`は`decision.execution_result.dispatch_event.candidate_event.run_id`から取得する。`outcome`が`NOOP`（`SKIPPED` / `NOT_FOUND` / `DISABLED`いずれかに由来）の場合は`remove_fn`を一切呼び出さない
- `src/retry_engine/retry_manager.py`（変更）：`RetryManager`が`RetryQueueRemovalExecutor`をConstructor Injectionで保持できるようにし、以下を追加した
  - `RetryManager.__init__` / `from_config()`に`queue_removal_executor`引数（デフォルト`None`）を追加。省略時は`RetryQueueRemovalExecutor()`に自動フォールバックする
  - `apply_retry_queue_removals(events, dry_run=False) -> list[RetryQueueRemovalResult]`：`decide_retry_queue_updates()`（v4.1.0、無変更）への委譲・`RetryQueueRemovalExecutor.apply_all(decisions, remove_fn=self._queue.remove)`への委譲の2段階のみで完結する。これにより`RetryQueueManager.remove()`が本Releaseで初めて呼び出し可能になった
  - `NullRetryManager`にも同名`apply_retry_queue_removals(events, dry_run=False)`を追加。`RetryQueueRemovalExecutor`を一切構築・参照せず、常に空リスト`[]`を返す（「受け取れるが何もしない」）
- `src/retry_engine/__init__.py`（変更）：`RetryQueueRemovalResult` / `RetryQueueRemovalExecutor`を新規export。既存の19シンボルは維持
- `tests/test_e2e_v4_2_0_retry_queue_removal_foundation.py`新規作成（94件）
- `docs/design/retry_queue_removal_foundation_charter.md`新規作成（Project Charter、承認済み）
- `docs/design/retry_queue_removal_foundation.md`新規作成（Architecture Design。Architecture Review完了・**Approve with Recommendations**、指摘事項1点を記録）

### Note

- **`RetryQueueManager.remove()`が本Releaseで初めて構造的に呼び出し可能になった。** v3.1.0〜v4.1.0のいずれのRelease（本ファイル`[KI-3]`〜`[KI-10]`が扱ってきた各回）でも、`remove()`は実装済みでありながら呼び出し経路が構造的に存在しないことがAcceptance Criteriaとして確認され続けてきた。本Releaseはその制約を初めて解除する
- **`COMPLETE` / `FAIL`のみをremove対象とし、`NOOP`（`SKIPPED` / `NOT_FOUND` / `DISABLED`いずれも含む）はremove対象外のまま構造的に維持した。** `RetryQueueRemovalExecutor.apply()`は`decision.outcome`が`_REMOVABLE_OUTCOMES = (COMPLETE, FAIL)`に含まれない場合、`remove_fn`を一切呼び出さずに`attempted=False`を返す（Spyオブジェクトによる呼び出し回数確認で構造的に検証済み）
- **`SKIPPED`（`max_attempts`到達）のQueue滞留対応は、ユーザー指示により本Releaseでは意図的にスコープ外とした。** 当該項目は本Release後もQueueに滞留し続ける（テスト19で回帰的に確認済み）。ROADMAP.mdに記載済みの次Release検討事項として据え置く
- **`RetryQueueRemovalExecutor`は`RetryQueueManager`型への直接依存を一切持たない。** remove操作は`remove_fn: Callable[[str], RetryQueueResult]`としてメソッド引数で受け取り、`RetryManager`が`self._queue.remove`（v3.2.0で既に保持しているバウンドメソッド）を渡すのみ。v4.0.0`RetryExecutionCoordinator`の`retry_fn`パターンと同じ設計言語を継承し、実行系・判定系コンポーネントは具象Managerクラスに依存しないという既存方針を維持した（`docs/design/retry_queue_removal_foundation.md` 2章）
- **`run_id`の取得は既存データの分解のみで、追加のQueue問い合わせを発生させない。** `decision.execution_result.dispatch_event.candidate_event.run_id`という既存フィールドへの単純なアクセスであり、`RetryQueueManager.list()`等の追加の突き合わせは発生しない
- **`RetryQueueResult.outcome`が`NOT_FOUND` / `DISABLED`であってもエラーとして扱わない。** `enqueue_retry()`を経由せずに`retry()`が実行されたケース（`run_id`がQueueに存在しない）や`RETRY_QUEUE_ENABLED=false`のケースは、いずれも`RetryQueueManager.remove()`の既存の正常な結果の範囲内であり、`RetryQueueRemovalExecutor`は特別扱い・例外処理を追加しない
- **`RetryManagerの変更は薄い委譲に留めた。** `apply_retry_queue_removals()`は`decide_retry_queue_updates()`（無変更）→`RetryQueueRemovalExecutor.apply_all()`の2行の委譲のみで完結し、除去ロジック自体は`RetryManager`に書いていない
- **Backward Compatibility を維持。** `RetryManager.__init__` / `from_config()`への`queue_removal_executor`引数追加は末尾のデフォルト値付き引数のみであり、既存の呼び出し（新規引数を渡さない場合）は本Release後もまったく同じ結果になる。`retry()` / `enqueue_retry()` / `dequeue_retry()` / `recognize_retry_events()` / `dispatch_retry_events()` / `execute_dispatchable_retries()` / `decide_retry_queue_updates()`（`RetryManager` / `NullRetryManager`とも）は1行も変更していない
- **`scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_event_consumer.py` / `retry_event_dispatcher.py` / `retry_execution_selector.py` / `retry_execution_coordinator.py` / `retry_queue_update_decider.py`はいずれも本Releaseでも無改修。** 変更は`retry_engine`配下2ファイル（新規1・変更1）と`__init__.py`のみ
- 対象外（今回も未実装）：`SKIPPED`（`max_attempts`到達）のQueue滞留対応（除去・Dead Letter Queue化）・Queue永続化・Retry Policy（選別基準の拡張）・Retry Metrics / Monitoring・Queue最適化（heapqベースのPriority Queue化等）・Scheduler改修・`RetryQueueManager.dequeue()`の本格実装・実運用のComposition Root（いずれも将来Release候補。詳細は`docs/design/retry_queue_removal_foundation_charter.md` 4章・10章、`docs/design/retry_queue_removal_foundation.md` 12章）

### Architecture Review Recommendations（反映済み）

- **`COMPLETE` / `FAIL` / `NOT_FOUND` / `DISABLED` / `NOOP`の5パターンの独立したテスト**：それぞれ独立した単体テスト（テスト1〜5）として固定化し、Spyオブジェクト（`FakeRetryQueueManager`）で`remove_fn`の呼び出し有無・引数を確認済み

### Tested

- `tests/test_e2e_v4_2_0_retry_queue_removal_foundation.py`: 94/94 PASS
- 既存回帰確認：`v1.9.0`〜`v2.9.0`（Analytics Foundation `[KI-1]`除く）全PASS
- `v3.0.0`（164/166）・`v3.1.0`（151/152）・`v3.2.0`（99/102）・`v3.3.0`（69/72）・`v3.4.0`（92/94）・`v3.5.0`（69/72）・`v3.6.0`（100/104）・`v3.7.0`（72/74）・`v3.8.0`（67/70）・`v3.9.0`（70/73）・`v4.0.0`（83/88）・`v4.1.0`（84/87）：いずれも`[KI-11]`（本Releaseによる意図的な変更）を含む。うち`v3.0.0`テスト21・`v3.8.0`テスト24-25・`v3.9.0`テスト20-21・`v4.0.0`テスト25-26（`[KI-7]`〜`[KI-10]`）は本Releaseと無関係な既存差分。`git stash`によるベースライン比較で、本Release固有の新規差分を特定済み（`[KI-11]`参照）
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v4.1.0] - 2026-07-06 ★ Retry Queue Update Foundation

### Added

- `src/retry_engine/retry_queue_update_decider.py`（新規）：`RetryManager.execute_dispatchable_retries()`（v4.0.0）が集約した`RetryExecutionResult`のリストを受け取り、各要素について対応するRetry Queue項目の更新先状態を判定する最小コンポーネント
  - `RetryQueueUpdateOutcome`（Enum）：`COMPLETE`（再実行成功）/ `FAIL`（再実行失敗）/ `NOOP`（再実行が行われていない＝更新なし）の3値
  - `RetryQueueUpdateDecision`（`frozen=True`の`dataclass`）：`execution_result`（元の`RetryExecutionResult`をそのまま保持）・`outcome`・`target_status`（`RetryQueueStatus.COMPLETED` / `FAILED` / `None`）・`reason`の4フィールド
  - `RetryQueueUpdateDecider`：`decide(execution_result) -> RetryQueueUpdateDecision` / `decide_all(execution_results) -> list[RetryQueueUpdateDecision]`の2メソッドのみを持つStatelessなコンポーネント。コンストラクタ引数を一切取らず、`RetryQueueManager` / `NullRetryQueueManager`への参照を持たない。判定基準は「再実行が実際に実行されたか」（`RetryResult.outcome == RETRIED`）のみを分岐点とし、`RETRIED`かつ`overall_success=True`は`COMPLETE`、`RETRIED`かつ`overall_success=False`は`FAIL`、`SKIPPED` / `NOT_FOUND` / `DISABLED`はいずれも`NOOP`に統一する
- `src/retry_engine/retry_manager.py`（変更）：`RetryManager`が`RetryQueueUpdateDecider`をConstructor Injectionで保持できるようにし、以下を追加した
  - `RetryManager.__init__` / `from_config()`に`queue_update_decider`引数（デフォルト`None`）を追加。省略時は`RetryQueueUpdateDecider()`に自動フォールバックする
  - `decide_retry_queue_updates(events, dry_run=False) -> list[RetryQueueUpdateDecision]`：`execute_dispatchable_retries()`（v4.0.0、無変更）への委譲・`RetryQueueUpdateDecider.decide_all()`への委譲の2段階のみで完結する
  - `NullRetryManager`にも同名`decide_retry_queue_updates(events, dry_run=False)`を追加。`RetryQueueUpdateDecider`を一切構築・参照せず、常に空リスト`[]`を返す（「受け取れるが何もしない」）
- `src/retry_engine/__init__.py`（変更）：`RetryQueueUpdateOutcome` / `RetryQueueUpdateDecision` / `RetryQueueUpdateDecider`を新規export。既存の16シンボルは維持
- `tests/test_e2e_v4_1_0_retry_queue_update_foundation.py`新規作成（87件）
- `docs/design/retry_queue_update_foundation_charter.md`新規作成（Project Charter、承認済み）
- `docs/design/retry_queue_update_foundation.md`新規作成（Architecture Design。Architecture Review完了・**Approve with Recommendations**、指摘事項2点を記録）

### Note

- **RetryQueueUpdateDeciderの責務は「判定のみ」に限定した。** コンストラクタ引数を一切取らず、`RetryQueueManager` / `NullRetryQueueManager`への参照を持たない。`RetryQueueManager.remove()` / `dequeue()`へ到達する呼び出し経路は構造的に存在しない（AST解析・Spyオブジェクトの両面でテスト済み）
- **`RetryQueueUpdateDecision`は次Release（Retry Queue Removal）に接続できる情報を保持する。** `execution_result`（→`dispatch_event`→`candidate_event`→`run_id` / `candidate`）を分解せず保持するため、`RetryQueueManager.remove(run_id)`に必要な`run_id`へ追加の突き合わせなしに到達できる。`retry_scheduler_source.py`（v3.3.0）の実装を確認した結果、Queue項目は`RetryQueueManager.list()`（非破壊的な読み取り）経由でCandidate化されており`dequeue()`によって既にQueueから取り除かれてはいないため、次Releaseがこの`run_id`とともに`remove()`を呼び出す設計は現在のQueue状態モデルと矛盾しない
- **SKIPPED / NOT_FOUND / DISABLEDはいずれもNOOPに統一し、安全側の判定とした。** 「再実行が実際に実行されたか」のみを分岐点とし、実行されなかったケースでQueue状態を動かす根拠を持たないため、誤って`COMPLETE` / `FAIL`と判定するリスクを構造的に排除している。3パターンそれぞれについて独立した単体テストでNOOPへの写像を固定化した（Minor Recommendation 1の反映）
- **SKIPPEDによるQueue内滞留リスクは、コード内コメント・設計書の双方に明記し、Release 4.2「Retry Queue Removal」への申し送り事項として記録した（Minor Recommendation 2の反映）。** `max_attempts`到達等で`SKIPPED`と判定された項目は、本Releaseでは`NOOP`のまま次Releaseまで恒久的にQueueに残り続ける可能性がある
- **`RetryManagerの変更は薄い委譲に留めた。** `decide_retry_queue_updates()`は`execute_dispatchable_retries()`（無変更）→`RetryQueueUpdateDecider.decide_all()`の2行の委譲のみで完結し、判定ロジック自体は`RetryManager`に書いていない（v4.0.0の3行委譲よりもさらに薄い）
- **retry_queueパッケージへの変更は一切不要だった。** `RetryQueueStatus.COMPLETED` / `FAILED`はv3.1.0で既に予約値として定義済みであり、新しい状態値の追加すら不要だった。「更新しない」は`retry_engine`側の新規Enum（`RetryQueueUpdateOutcome.NOOP`）と`target_status=None`の組み合わせで表現し、`RetryQueueStatus`自体には一切手を加えていない
- **Backward Compatibility を維持。** `RetryManager.__init__` / `from_config()`への`queue_update_decider`引数追加は末尾のデフォルト値付き引数のみであり、既存の呼び出し（新規引数を渡さない場合）は本Release後もまったく同じ結果になる。`retry()` / `enqueue_retry()` / `dequeue_retry()` / `recognize_retry_events()` / `dispatch_retry_events()` / `execute_dispatchable_retries()`（`RetryManager` / `NullRetryManager`とも）は1行も変更していない
- **`scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_event_consumer.py` / `retry_event_dispatcher.py` / `retry_execution_selector.py` / `retry_execution_coordinator.py`はいずれも本Releaseでも無改修。** 変更は`retry_engine`配下2ファイル（新規1・変更1）と`__init__.py`のみ
- 対象外（今回も未実装）：`RetryQueueManager.remove()`の呼び出し・`RetryQueueManager.dequeue()`の本格実装・Queue永続化・判定結果をQueue内部ストアへ実際に反映する処理・Retry Policy（選別基準の拡張）・Retry Metrics / Monitoring・Scheduler側の変更（いずれも将来Release候補。詳細は`docs/design/retry_queue_update_foundation_charter.md` 4章・10章、`docs/design/retry_queue_update_foundation.md` 12章）

### Architecture Review Recommendations（反映済み）

- **NOOP3パターンの区別テスト**：`SKIPPED` / `NOT_FOUND` / `DISABLED`をそれぞれ独立した単体テスト（テスト5〜8）として固定化し、`reason`文字列で区別可能であることを確認済み
- **SKIPPEDによるQueue内滞留リスク**：`retry_queue_update_decider.py`のdocstring・設計書16.3節の両方に、Release 4.2「Retry Queue Removal」への申し送り事項として明記済み（テスト25で明記されていることを確認）

### Tested

- `tests/test_e2e_v4_1_0_retry_queue_update_foundation.py`: 87/87 PASS
- 既存回帰確認：`v1.9.0`〜`v2.9.0`（Analytics Foundation `[KI-1]`除く）全PASS
- `v3.0.0`（158/160）・`v3.1.0`（151/152）・`v3.2.0`（99/102）・`v3.3.0`（69/72）・`v3.4.0`（92/94）・`v3.5.0`（69/72）・`v3.6.0`（100/104）・`v3.7.0`（72/74）・`v3.8.0`（67/70）・`v3.9.0`（70/73）・`v4.0.0`（83/88）：いずれも`[KI-10]`（本Releaseによる意図的な変更）を含む。うち`v3.0.0`テスト21・`v3.8.0`テスト24-25・`v3.9.0`テスト20-21（`[KI-7]`〜`[KI-9]`）は本Releaseと無関係な既存差分。`git stash`によるベースライン比較で、本Release固有の新規差分を特定済み（`[KI-10]`参照）
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v4.0.0] - 2026-07-06 ★ Retry Execution Foundation

### Added

- `src/retry_engine/retry_execution_selector.py`（新規）：`RetryEventDispatcher`（v3.9.0）が整理した`RetryDispatchEvent`のうち、`dispatchable=True`のものだけを実行対象として選別する最小コンポーネント
  - `RetryExecutionSelector`：`select(dispatch_events) -> list[RetryDispatchEvent]`の1メソッドのみを持つStatelessなコンポーネント。`dispatchable`を参照する箇所をこの1メソッドのみに集約し、「`dispatchable=true`を唯一の実行入口とする」判定基準を1箇所に閉じ込める
- `src/retry_engine/retry_execution_coordinator.py`（新規）：選別済みの`RetryDispatchEvent`について、初めて`RetryManager.retry()`を呼び出し結果を集約する最小コンポーネント
  - `RetryExecutionResult`（`frozen=True`の`dataclass`）：`dispatch_event`（元の`RetryDispatchEvent`をそのまま保持）・`retry_result`（`RetryManager.retry()`が返した既存の`RetryResult`をそのまま保持）の2フィールドのみを持つ軽量ラッパー。既存の`RetryResult`（v3.0.0）自体は一切変更しない
  - `RetryExecutionCoordinator`：`execute(dispatch_events, retry_fn, dry_run=False) -> list[RetryExecutionResult]`の1メソッドのみを持つStatelessなコンポーネント。`retry_fn`は呼び出しごとに引数として受け取り、コンストラクタでは保持しない（`RetryManager`への逆参照を持たず循環参照を避ける）。`retry_attempt`は`candidate_event.candidate`から`getattr(candidate, "retry_attempt", 1)`で取得する（**v4.0ではQueue非依存を優先した暫定実装**であり、`retry_queue`パッケージへの型依存を避けるための緩いダックタイピング＋フォールバックである旨をコード内コメントに明記）
- `src/retry_engine/retry_manager.py`（変更）：`RetryManager`が`RetryExecutionSelector` / `RetryExecutionCoordinator`をConstructor Injectionで保持できるようにし、以下を追加した
  - `RetryManager.__init__` / `from_config()`に`execution_selector` / `execution_coordinator`引数（デフォルト`None`）を追加。省略時はそれぞれ`RetryExecutionSelector()` / `RetryExecutionCoordinator()`に自動フォールバックする
  - `execute_dispatchable_retries(events, dry_run=False) -> list[RetryExecutionResult]`：`dispatch_retry_events()`（v3.9.0）への委譲・`RetryExecutionSelector.select()`（判定を1箇所に集約）・`RetryExecutionCoordinator.execute()`（`retry_fn=self.retry`を渡し、実行と結果集約を委譲）の3段階のみで完結する。これにより`RetryManager.retry()`が、Dispatch結果（`dispatchable=True`のもの）を起点に初めて呼び出せるようになった
  - `NullRetryManager`にも同名`execute_dispatchable_retries(events, dry_run=False)`を追加。`RetryExecutionSelector` / `RetryExecutionCoordinator`を一切構築・参照せず、常に空リスト`[]`を返す（「受け取れるが何もしない」）
- `src/retry_engine/__init__.py`（変更）：`RetryExecutionSelector` / `RetryExecutionCoordinator` / `RetryExecutionResult`を新規export。既存の13シンボルは維持
- `tests/test_e2e_v4_0_0_retry_execution_foundation.py`新規作成（88件）
- `docs/design/retry_execution_foundation_charter.md`新規作成（Project Charter、承認済み）
- `docs/design/retry_execution_foundation.md`新規作成（Architecture Design。Architecture Review完了・**Approve with Recommendations**、指摘事項2点を記録）

### Note

- **RetryManagerの責務は委譲のみに維持した。** `execute_dispatchable_retries()`は「dispatch → select → execute」の3行の委譲のみで完結し、判定ロジック（`dispatchable`の解釈）・実行ループ・結果集約のいずれも`RetryManager`自身には書かない。判定（`RetryExecutionSelector`）と実行・集約（`RetryExecutionCoordinator`）を別コンポーネントに分離する設計を、「メソッド追加のみ」「単一の統合コンポーネント」との比較検討のうえで採用した（`docs/design/retry_execution_foundation.md` 2章）
- **`dispatchable=true`を唯一の実行入口とし、判定を1箇所に集約した。** `dispatchable`フィールドを参照するのは`RetryExecutionSelector.select()`のみであり、`RetryExecutionCoordinator`・`RetryManager`のいずれも`dispatchable`を再解釈しない。`execute()`に渡された時点で全件が実行対象であることは、呼び出しグラフの構造によって保証される
- **Queueには一切依存しない。** `RetryExecutionSelector` / `RetryExecutionCoordinator`のいずれも`RetryQueueManager` / `NullRetryQueueManager`への参照を持たず（コンストラクタ引数にも存在しない）、`retry_queue`パッケージへのimportも発生しない（AST解析で確認済み）。入力は`RetryDispatchEvent`（Dispatcherが返した情報）のみであり、Queueへの読み書きは一切行わない
- **実行結果は専用の軽量ラッパー型（`RetryExecutionResult`）で返す。** 既存の`RetryResult`は変更せず、`dispatch_event`と`retry_result`を対にして保持することで、将来のRetry Queue Update（どのQueue項目由来かの突き合わせ）に備えた拡張点を残した
- **`retry_attempt`はQueue非依存を優先した暫定実装。** `candidate_event.candidate`（実態は`RetryQueueItem`）への型importを避け、`getattr(candidate, "retry_attempt", 1)`という緩いダックタイピング＋フォールバックで取得する。この設計判断はコード内コメントに明記し、将来`RetryCandidateEvent` / `RetryDispatchEvent`への正式なフィールド追加を検討する余地として`docs/design/retry_execution_foundation.md` 12章 Future Extensionに記録した
- **Backward Compatibility を維持。** `RetryManager.__init__` / `from_config()`への`execution_selector` / `execution_coordinator`引数追加は末尾のデフォルト値付き引数のみであり、既存の呼び出し（新規引数を渡さない場合）は本Release後もまったく同じ結果になる。`retry()` / `enqueue_retry()` / `dequeue_retry()` / `recognize_retry_events()` / `dispatch_retry_events()`（`RetryManager` / `NullRetryManager`とも）は1行も変更していない
- **`scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_event_consumer.py` / `retry_event_dispatcher.py`はいずれも本Releaseでも無改修。** 変更は`retry_engine`配下3ファイル（新規2・変更1）と`__init__.py`のみ
- 対象外（今回も未実装）：Retry Queueの更新・`enqueue_retry()` / `dequeue_retry()`の自動呼び出し・`RetryQueueManager.dequeue()` / `remove()`の呼び出し・Queue永続化・Retry Policy（優先度・件数上限に基づく選別ロジックの導入）・Scheduler側の変更（いずれも将来Release候補。詳細は`docs/design/retry_execution_foundation_charter.md` 4章・10章、`docs/design/retry_execution_foundation.md` 12章）

### Architecture Review Recommendations（今後の課題として維持）

- **`retry_attempt`のダックタイピング依存**：`candidate.retry_attempt`への`getattr`アクセスは、`retry_queue`パッケージへの型結合を避けるための意図的な選択だが、`candidate`の由来が将来変化した場合に静かに`attempt=1`へフォールバックするリスクを残す。実装時、単体テストでこの挙動を明示的に固定化済み（テスト6・7）。将来`RetryCandidateEvent`への正式なフィールド追加を検討する際の判断材料として記録する
- **`RetryExecutionCoordinator.execute()`のfail-fast方針**：現時点では該当する例外シナリオが存在しないため妥当な判断だが、将来複数件のバッチ実行が実運用で使われる段階（Composition Root導入時）で、1件の失敗が残り全件の実行を止めてしまう影響範囲を再評価することを推奨する

### Tested

- `tests/test_e2e_v4_0_0_retry_execution_foundation.py`: 88/88 PASS
- 既存回帰確認：`v1.9.0`〜`v2.9.0`（Analytics Foundation `[KI-1]`除く）全PASS
- `v3.0.0`（152/154）・`v3.1.0`（151/152）・`v3.2.0`（99/102）・`v3.3.0`（69/72）・`v3.4.0`（92/94）・`v3.5.0`（69/72）・`v3.6.0`（100/104）・`v3.7.0`（72/74）・`v3.8.0`（67/70）・`v3.9.0`（70/73）：いずれも`[KI-9]`（本Releaseによる意図的な変更）を含む。うち`v3.0.0`テスト21・`v3.8.0`テスト24-25（`[KI-7]`/`[KI-8]`）・`v3.3.0`テスト17（`[KI-4]`）・`v3.5.0`テスト18（`[KI-4]`）・`v3.6.0`テスト16-17（`[KI-6]`）は本Releaseと無関係な既存差分。`git stash`によるベースライン比較で、本Release固有の新規差分を特定済み（`[KI-9]`参照）
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v3.9.0] - 2026-07-06 ★ Retry Engine Event Dispatch

### Added

- `src/retry_engine/retry_event_dispatcher.py`（新規）：`RetryEventConsumer`（v3.8.0）が認識した`RetryCandidateEvent`を、Retry Engine側がDispatch対象として整理するための最小コンポーネント
  - `RetryDispatchEvent`（`frozen=True`の`dataclass`）：`candidate_event`（元の`RetryCandidateEvent`をそのまま保持、分解しない）・`dispatchable`（Dispatch対象として扱えるかの判定結果）の2フィールドのみを持つ軽量な整理結果
  - `RetryEventDispatcher`：`dispatch_one(candidate_event)`（1件）・`dispatch(candidate_events)`（複数件）の2メソッドのみを持つStatelessなコンポーネント。`dispatchable`は`candidate_event.run_id`が空でないかという構造的妥当性のみで判定し、優先度・件数上限に基づく選別は行わない。`dispatchable=False`と判定されたイベントもリストから除外せず、そのまま返す（Dispatch対象かどうかの判定結果を可視化する）
- `src/retry_engine/retry_manager.py`（変更）：`RetryManager`が`RetryEventDispatcher`をConstructor Injectionで保持できるようにし、以下を追加した
  - `RetryManager.__init__` / `from_config()`に`event_dispatcher`引数（デフォルト`None`）を追加。省略時は`RetryEventDispatcher()`に自動フォールバックする（`RetryEventConsumer`と同じ「省略時は安全な実装へ自動フォールバックする」方式）
  - `dispatch_retry_events(events) -> list[RetryDispatchEvent]`：`recognize_retry_events()`（v3.8.0）への委譲、続けて`RetryEventDispatcher.dispatch()`への薄い委譲、の2段階のみで完結する。既存の`retry()` / `enqueue_retry()` / `dequeue_retry()`とは呼び出しグラフ上で完全に独立しており、Dispatch結果を使って自動的に何かを実行する処理は持たない（自動実行はしない）
  - `NullRetryManager`にも同名`dispatch_retry_events(events)`を追加。`RetryEventDispatcher`を一切構築・参照せず、常に空リスト`[]`を返す（「受け取れるが何もしない」）
- `src/retry_engine/__init__.py`（変更）：`RetryDispatchEvent` / `RetryEventDispatcher`を新規export。既存の11シンボルは維持
- `tests/test_e2e_v3_9_0_retry_engine_event_dispatch.py`新規作成（73件）
- `docs/design/retry_engine_event_dispatch_charter.md`新規作成（Project Charter、承認済み）
- `docs/design/retry_engine_event_dispatch.md`新規作成（Architecture Design。Architecture Review完了・**Approve with Minor Recommendations**、指摘事項1点を記録）

### Note

- **通常イベントとRetryイベントの振り分けは二段階構成とした。** 第1段階（`recognize_retry_events()`、v3.8.0、無改修）がJob由来の`SchedulerEvent`を除外し、第2段階（本Release、`dispatch_retry_events()`）はRetry候補由来の`RetryCandidateEvent`のみを入力とする。`RetryEventDispatcher`は生の`SchedulerEvent`を一切扱わない
- **Dispatch対象の判定基準は構造的妥当性（`run_id`の非空判定）のみに限定した。** ROADMAP.mdが将来候補として例示する「優先度・件数上限に基づく選別」は、Retry Executionとの責務境界を曖昧にしないため、本Releaseではあえて導入しない
- **整理のみで、実行・Queue操作は一切行わない。** `RetryEventDispatcher`・`dispatch_retry_events()`のいずれも`RetryQueueManager.dequeue()` / `remove()`・`RetryManager.retry()`・`enqueue_retry()` / `dequeue_retry()`へ到達する経路を構造的に持たない（Spy・静的検査の両方で確認済み）
- **新規の外部パッケージ依存を追加しない。** `retry_event_dispatcher.py`がimportするのは`.retry_event_consumer`（`retry_engine`パッケージ内）と標準ライブラリのみ。`scheduler` / `retry_queue`への新規importは発生しない（AST解析で確認済み）
- **Stateless。** `RetryEventDispatcher`は内部状態を一切持たず、呼び出しごとに渡された`candidate_events`のみから結果を導出する。`RetryDispatchEvent`のキャッシュ・永続化は行わない
- **Backward Compatibility を維持。** `RetryManager.__init__` / `from_config()`への`event_dispatcher`引数追加は末尾のデフォルト値付き引数のみであり、既存の呼び出し（新規引数を渡さない場合）は本Release後もまったく同じ結果になる。`retry()` / `enqueue_retry()` / `dequeue_retry()` / `recognize_retry_events()`（`RetryManager` / `NullRetryManager`とも）は1行も変更していない
- **`scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` / `retry_event_consumer.py`はいずれも本Releaseでも無改修。** 変更は`retry_engine`配下2ファイル（新規1・変更1）と`__init__.py`のみ
- 対象外：Dispatch結果（`RetryDispatchEvent`）を使った自動Retry実行（Retry Execution）・優先度・件数上限に基づく選別ロジック・実運用のComposition Root・`job_id`プレフィックス衝突の構造的な防止（いずれも将来Release候補。詳細は`docs/design/retry_engine_event_dispatch_charter.md` 4章・10章、`docs/design/retry_engine_event_dispatch.md` 11章）

### Architecture Review Minor Recommendations（今後の課題として維持）

- **`dispatchable`の判定基準が最小限であること**：現状は`run_id`の非空チェックのみであり、実運用上の意味のある「Dispatch対象かどうか」の判断（優先度・件数上限・重複排除等）は一切行わない。次Release（Retry Execution）で実際に必要となる判定基準が本設計の想定と異なる可能性があり、その設計段階で再検討することを推奨する

### Tested

- `tests/test_e2e_v3_9_0_retry_engine_event_dispatch.py`: 73/73 PASS
- 既存回帰確認：`v1.20.0`（170/170）・`v2.0.0`（118/118）・`v2.6.0`（118/118）・`v2.7.0`（163/163）・`v2.8.0`（182/182）・`v2.9.0`（103/103）全PASS
- `v3.0.0`（140/142）・`v3.1.0`（151/152）・`v3.2.0`（99/102）・`v3.3.0`（69/72）・`v3.4.0`（92/94）・`v3.5.0`（69/72）・`v3.6.0`（100/104）・`v3.7.0`（72/74）・`v3.8.0`（67/70）：いずれも`[KI-8]`（本Releaseによる意図的な変更）を含む。うち`v3.3.0`のテスト17（`[KI-4]`）・`v3.5.0`のテスト18（`[KI-4]`）・`v3.6.0`のテスト16-17（`[KI-6]`）は本Releaseと無関係な既存差分
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v3.8.0] - 2026-07-03 ★ Retry Engine Event Consumption

### Added

- `src/retry_engine/retry_event_consumer.py`（新規）：Scheduler（v3.7.0）が生成したRetry候補由来の`SchedulerEvent`を、Retry Engine側が受け取って認識するための最小コンポーネント
  - `RETRY_JOB_ID_PREFIX = "retry:"`：`job_id`の予約プレフィックス定数（`scheduler_engine.py`のリテラルと値は同じだが、`retry_engine`側で独立して定数化。11章参照）
  - `RetryCandidateEvent`（`frozen=True`の`dataclass`）：`run_id` / `candidate`（元の候補オブジェクトをそのまま保持、分解しない） / `source_event`（元の`SchedulerEvent`）の3フィールドのみを持つ軽量な認識結果
  - `RetryEventConsumer`：`recognize(event)`（1件）・`recognize_all(events)`（複数件）の2メソッドのみを持つStatelessなコンポーネント。`job_id`が`"retry:"`で始まらないものは無視し、`"retry:"`で始まっていても`metadata["retry_candidate"]`が存在しない場合は防御的に無視する（例外を送出しない）
- `src/retry_engine/retry_manager.py`（変更）：`RetryManager`が`RetryEventConsumer`をConstructor Injectionで保持できるようにし、以下を追加した
  - `RetryManager.__init__` / `from_config()`に`event_consumer`引数（デフォルト`None`）を追加。省略時は`RetryEventConsumer()`に自動フォールバックする（`RetrySchedulerSource`と同じ「省略時は安全な実装へ自動フォールバックする」方式。`RetryEventConsumer`はConfig不要のStatelessなコンポーネントのため、`RetrySchedulerDecision`のような必須DIは採用しない）
  - `recognize_retry_events(events) -> list[RetryCandidateEvent]`：`RetryEventConsumer.recognize_all()`への薄い委譲のみ。既存の`retry()` / `enqueue_retry()` / `dequeue_retry()`とは呼び出しグラフ上で完全に独立しており、認識結果を使って自動的に何かを実行する処理は持たない（自動実行はしない）
  - `NullRetryManager`にも同名`recognize_retry_events(events)`を追加。`RetryEventConsumer`を一切構築・参照せず、常に空リスト`[]`を返す（「受け取れるが何もしない」）
- `src/retry_engine/__init__.py`（変更）：`RetryCandidateEvent` / `RetryEventConsumer`を新規export。既存の9シンボルは維持
- `tests/test_e2e_v3_8_0_retry_engine_event_consumption.py`新規作成（70件）
- `docs/design/retry_engine_event_consumption_charter.md`新規作成（Project Charter、承認済み）
- `docs/design/retry_engine_event_consumption.md`新規作成（Architecture Design。Architecture Review完了・**Approve with Minor Recommendations**、指摘事項2点を記録）

### Note

- **本Releaseは、v3.3.0〜v3.7.0までの「Scheduler側（発信側）」の統合とは異なり、初めて「Retry Engine側（受信側）」に手を入れるRelease。** `SchedulerEngine`（v3.7.0）が生成したRetry候補由来の`SchedulerEvent`を、`retry_engine`が受け取って認識できるようにする
- **`retry_engine`が`scheduler`パッケージへ依存する初めてのReleaseだが、importするのは`SchedulerEvent`型のみ。** `SchedulerEngine` / `SchedulerManager`等の実行系クラスは一切importしない（`retry_event_consumer.py`のAST解析で構造的に確認済み）。`scheduler`側（逆方向）は本Releaseでも一切変更しない
- **認識のみで、実行・Queue操作は一切行わない。** `RetryEventConsumer`・`recognize_retry_events()`のいずれも`RetryQueueManager.dequeue()` / `remove()`・`RetryManager.retry()`・`enqueue_retry()` / `dequeue_retry()`へ到達する経路を構造的に持たない（Spy・ASTの両方で確認済み）
- **候補オブジェクトは分解せず`RetryCandidateEvent.candidate`にそのまま格納する。** v3.7.0 Design Decision #3（`metadata["retry_candidate"]`を分解しない方針）を受信側でも踏襲する。`candidate`の型は`Any`とし、`retry_engine`が`retry_queue`（`RetryQueueItem`）の内部構造に依存しないようにした
- **Stateless。** `RetryEventConsumer`は内部状態を一切持たず、呼び出しごとに渡された`events`のみから結果を導出する。`RetryCandidateEvent`のキャッシュ・永続化は行わない
- **Backward Compatibility を維持。** `RetryManager.__init__` / `from_config()`への`event_consumer`引数追加は末尾のデフォルト値付き引数のみであり、既存の`RetryManager(policy, executor, monitor)` / `RetryManager(policy, executor, monitor, queue=...)` / `RetryManager.from_config(...)`（新規引数を渡さない場合）は本Release後もまったく同じ結果になる。`retry()` / `enqueue_retry()` / `dequeue_retry()`（`RetryManager` / `NullRetryManager`とも）は1行も変更していない
- **`scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue`はいずれも本Releaseでも無改修。** 変更は`retry_engine`配下2ファイル（新規1・変更1）と`__init__.py`のみ
- **`"retry:"`プレフィックスは`retry_engine`側で独立して定数化した（`scheduler`側は無改修のため重複定義）。** 将来`scheduler`側がこの文字列を公開定数化した場合、`retry_engine`側はそれを参照する形に置き換えられる余地を残す（Minor Recommendation、下記参照）
- 対象外：認識結果（`RetryCandidateEvent`）を使った自動Retry実行・実運用のComposition Root（`SchedulerEngine.run_due()`の結果を実際に`RetryManager.recognize_retry_events()`へ渡して回す起動スクリプト）・`job_id`プレフィックス衝突の構造的な防止・`RetryCandidateEvent.candidate`の型安全な公開（いずれも将来Release候補。詳細は`docs/design/retry_engine_event_consumption_charter.md` 4章・10章、`docs/design/retry_engine_event_consumption.md` 11章）

### Architecture Review Minor Recommendations（今後の課題として維持）

- **`"retry:"`プレフィックスの重複定義**：`scheduler_engine.py`のリテラルと`retry_event_consumer.py`の`RETRY_JOB_ID_PREFIX`が同じ値を独立に持つ。どちらか一方だけを変更すると認識が壊れるサイレントな結合が生じる。次Release以降で`scheduler`側の公開定数化を検討する余地がある
- **`RetryCandidateEvent.candidate`が`Any`型であること**：型安全性は犠牲になるが、`retry_engine`が`retry_queue`の内部構造（`RetryQueueItem`のフィールド）に依存しないための意図的な選択。将来、認識結果を実際に消費する側（自動Retry実行）が現れた時点で、必要な型情報をどこまで公開するか再設計を推奨する

### Tested

- `tests/test_e2e_v3_8_0_retry_engine_event_consumption.py`: 70/70 PASS
- 既存回帰確認：`v2.6.0`（118/118）・`v2.7.0`（163/163）・`v2.8.0`（182/182）・`v2.9.0`（103/103）全PASS
- `v3.0.0`（134/136）・`v3.1.0`（151/152）・`v3.2.0`（99/102）・`v3.3.0`（69/72）・`v3.4.0`（92/94）・`v3.5.0`（69/72）・`v3.6.0`（100/104）・`v3.7.0`（72/74）：いずれも`[KI-7]`（本Releaseによる意図的な変更）を含む。うち`v3.3.0`のテスト17（`[KI-4]`）・`v3.5.0`のテスト18（`[KI-4]`）・`v3.6.0`のテスト16-17（`[KI-6]`）は本Releaseと無関係な既存差分
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v3.7.0] - 2026-07-03 ★ Retry Scheduler Event Integration

### Added

- `src/scheduler/scheduler_engine.py`（変更）：`evaluate()` / `run_due()`が、`RetrySchedulerDecision`の選択結果（`select_candidates()`、v3.6.0）をRetry候補由来の`SchedulerEvent`として出力に含められるようになった
  - `evaluate(jobs, now, retry_limit=None)`：既存のJob判定ループは1行も変更せず、新設の`_build_retry_events(now, retry_limit)`が返すリストを`events.extend(...)`で追加連結する（Additive方式）
  - `run_due(jobs, retry_limit=None)`：`evaluate()`への委譲は無変更。`retry_limit`をそのまま中継するのみ
  - `_build_retry_events(now, retry_limit)`（新設、private）：`self.select_candidates(limit=retry_limit)`（v3.6.0）への委譲のみ。Retry候補ごとに`job_id="retry:" + run_id`・`execute_time=now`・`trigger_reason=REASON_RETRY_CANDIDATE_SELECTED`・`metadata={"retry_candidate": 候補オブジェクト}`という`SchedulerEvent`を生成する
  - `REASON_RETRY_CANDIDATE_SELECTED`定数を追加
- `src/scheduler/__init__.py`（変更）：モジュールdocstringにv3.7.0の変更点を追記のみ。`__all__`は無変更
- `tests/test_e2e_v3_7_0_retry_scheduler_event_integration.py`新規作成（74件）
- `docs/design/retry_scheduler_event_integration_charter.md`新規作成（Project Charter、承認済み）
- `docs/design/retry_scheduler_event_integration.md`新規作成（Architecture Design。Architecture Review完了・**Approve with Minor Recommendations**、指摘事項2点を記録。ユーザー承認時のMinor Recommendation追記1件を含む）

### Note

- **既存のJob判定ループ（`_match*()`系）は1行も変更していない。** Retry候補の反映は、Job判定ループとは完全に独立した`_build_retry_events()`の結果を`events.extend()`で追加連結するだけのAdditive方式を採用した
- **`retry_decision=None`の場合は既存動作と完全互換。** `_build_retry_events()`は`self.select_candidates()`（v3.6.0のガード節）への委譲のみで、`retry_decision`が`None`の場合は常に空リストを返す。新たな`None`チェックを`evaluate()`側に追加していないため、`retry_decision`省略時の出力はv3.6.0時点とまったく同一になる（後方互換性維持。v3.7.0新規テストのテスト1〜4で確認済み）
- **`retry_decision`ありの場合、Retry候補が`SchedulerEvent`として追加されるため、v3.6.0の「結果完全一致」系テスト2件（テスト16・17）は既知差分となる。** これは`evaluate()` / `run_due()`への統合というv3.7.0の目的そのものによる意図的な差分であり、`[KI-6]`として記録した
- **Retry Engineは起動しない。** `_build_retry_events()`が呼び出すのは`select_candidates()`（読み取り専用）のみで、`retry_engine`パッケージは一切importしない
- **`RetryQueueManager.dequeue()` / `remove()`は使用しない。** `_build_retry_events()`から到達できる経路は`select_candidates()`のみで、Queueの状態を変更する操作へは構造的に到達できない
- **Queueの更新・Retry Queueの永続化はいずれも行わない。** `SchedulerEngine`はRetry候補由来の`SchedulerEvent`を保持せず（Stateless）、呼び出しのたびに`select_candidates()`で再取得する
- **`job_id`欠如問題への対処**：`RetryQueueItem`には`job_id`相当のフィールドが存在しないため、`run_id`属性に`"retry:"`という予約プレフィックスを付けた文字列を採用した。`scheduler`は`retry_queue`を直接importせず、`run_id`という1属性への構造的な期待（Duck Typing）のみに依存する
- **`metadata["retry_candidate"]`は候補オブジェクトを分解せずそのまま格納する。** `metadata`のキーは`"retry_candidate"`の1つのみで、`workflow_name` / `priority`等を個別展開しない
- **`metadata["retry_candidate"]`は本Release（v3.7.0）ではin-memoryの観測用途に限定する。** 永続化・JSON serialization（`RetryQueueItem`は`datetime` / Enumフィールドを含み標準の`json.dumps()`ではそのままシリアライズできない）・外部I/O契約とはしない（ユーザー承認時のMinor Recommendation）
- 対象外：生成された`SchedulerEvent`（Retry候補由来）を消費する仕組み（Retry Engine起動・Workflow Engine起動等）・自動Retry実行・`job_id`プレフィックス衝突の構造的な防止・`metadata["retry_candidate"]`の型安全な公開（いずれも将来Release候補。詳細は`docs/design/retry_scheduler_event_integration_charter.md` 4章・10章、`docs/design/retry_scheduler_event_integration.md` 11章）

### Tested

- `tests/test_e2e_v3_7_0_retry_scheduler_event_integration.py`: 74/74 PASS
- 既存回帰確認：`v2.6.0`（118/118）・`v3.4.0`（94/94）・`v1.20.0`（170/170）全PASS
- `v3.6.0`（102/104 PASS）：2件FAILは`[KI-6]`（本Releaseによる意図的な変更。`retry_decision`ありの場合にRetry候補由来の`SchedulerEvent`が追加されるようになったため）
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v3.6.0] - 2026-07-03 ★ Retry Scheduler Decision Wiring

### Added

- `src/scheduler/scheduler_engine.py`（変更）：`SchedulerEngine`が`RetrySchedulerDecision`（v3.5.0）をConstructor Injectionで保持できるようにし、以下2メソッドを追加した
  - `select_candidates(limit=None) -> list`：`RetrySchedulerDecision.select_candidates()`への薄い委譲のみ。`retry_decision`が`None`の場合は`[]`を返す
  - `select_next_candidate()`：`RetrySchedulerDecision.select_next_candidate()`への薄い委譲のみ。`retry_decision`が`None`の場合は`None`を返す
- `SchedulerEngine.__init__`に`retry_decision`引数（デフォルト`None`）を追加。既存の`SchedulerEngine()` / `SchedulerEngine(clock=...)` / `SchedulerEngine(retry_source=...)`呼び出しは無変更で動作する（後方互換性維持）
- `src/scheduler/__init__.py`（変更）：モジュールdocstringにv3.6.0の変更点を追記のみ。`__all__`は無変更
- `tests/test_e2e_v3_6_0_retry_scheduler_decision_wiring.py`新規作成（104件）
- `docs/design/retry_scheduler_decision_wiring_charter.md`新規作成（Project Charter、承認済み）
- `docs/design/retry_scheduler_decision_wiring.md`新規作成（Architecture Design。Architecture Review完了・**Approve with Minor Recommendations**、指摘事項2点を記録）

### Note

- **`SchedulerEngine`は`RetrySchedulerDecision`を自ら生成しない。** ユーザー承認済みの設計方針として、`SchedulerEngine`は外部（呼び出し元・Composition Root）から`RetrySchedulerDecision`インスタンスをConstructor Injectionで受け取って保持するのみで、`RetrySchedulerDecision(...)`という構築呼び出しは`scheduler_engine.py`に一切登場しない（ASTベースで構造的に確認済み）
- **`retry_decision=None`の場合はガード節で安全なデフォルトを返す。** `RetrySchedulerDecision`には対になる`NullRetrySchedulerDecision`が存在しない（v3.5.0の意図的な設計判断）。かつ`SchedulerEngine`が`RetrySchedulerDecision`を組み立てない制約により、v3.4.0の`retry_source`（省略時に`NullRetrySchedulerSource()`を構築してフォールバック）とは異なる方式を採用し、`select_candidates()` / `select_next_candidate()`内のガード節（`if self._retry_decision is None`）で`[]` / `None`を直接返す。オブジェクトを1つも生成せずに同じ安全な結果を得る
- **`evaluate()` / `run_due()`はいずれも無変更。** 判定サイクル（時刻ベースの判定・`SchedulerEvent`生成）には一切手を加えず、`select_candidates()` / `select_next_candidate()`という完全に独立した新規メソッドを追加する方式を採用した（v3.4.0と同型のパターン）
- **`SchedulerEngine`は`RetryQueueManager`を直接保持しない。** Retry Queueへは`RetrySchedulerSource`（v3.4.0）または`RetrySchedulerDecision`（本Release）経由でのみ間接的に到達する。`dequeue()` / `remove()`に相当するメソッドは`RetrySchedulerDecision`にも存在しないため、`SchedulerEngine`からは構造的に呼び出せない
- 対象外：`evaluate()` / `run_due()`への候補選択結果の組み込み（`SchedulerEvent`生成への反映）・Retry Engineの起動・`RetryQueueManager.dequeue()` / `remove()`の使用・Retry Queueの更新・Retry Queueの永続化（いずれも将来Release候補。詳細は`docs/design/retry_scheduler_decision_wiring_charter.md` 4章・10章）

### Tested

- `tests/test_e2e_v3_6_0_retry_scheduler_decision_wiring.py`: 104/104 PASS
- 既存回帰確認：`v2.0.0`（118/118）・`v2.6.0`（118/118）・`v3.4.0`（94/94）・`v1.20.0`（170/170）全PASS
- `v2.7.0`（153/163）・`v2.8.0`（174/179）・`v2.9.0`（93/100）・`v3.0.0`（129/130）・`v3.1.0`（151/152）・`v3.2.0`（101/102）・`v3.3.0`（69/72）：いずれも`[KI-4]`の延長（本Release未commitに伴う一時的なArchitecture Guard FAIL。commit後に解消見込み）が含まれる。加えて`v2.7.0`・`v2.8.0`・`v2.9.0`は本Releaseと無関係な既存問題（`[KI-5]`）を含む（`git stash`によるベースライン比較で確認済み）
- `v3.5.0`（69/72）：`[KI-4]`の延長2件（一時的、commit後解消見込み）に加え、テスト18の恒久差分1件（新規。`[KI-4]`2026-07-03追記参照）
- `v2.2.0`（118/120）・`v2.3.0`（101/110）・`v2.4.0`（112/120）・`v2.5.0`（110/118）：いずれも本Releaseと無関係な既存問題（`[KI-5]`、新規追加）。`git stash`によるベースライン比較で、本Release前後で件数・項目が完全一致することを確認済み
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v3.5.0] - 2026-07-03 ★ Retry Scheduler Decision

### Added

- `src/retry_scheduler_decision/`（新規パッケージ）：`RetrySchedulerSource`（またはNullRetrySchedulerSource）が返す待機中の項目一覧から、「次に処理すべき候補」を選ぶだけの最小コンポーネント
  - `retry_scheduler_decision.py`: `RetrySchedulerDecision`（`retry_source`をConstructor Injectionで**必須引数として**保持し、`select_candidates(limit)` / `select_next_candidate()`への薄い委譲のみを行う）
  - `__init__.py`: `RetrySchedulerDecision`をexport
- `tests/test_e2e_v3_5_0_retry_scheduler_decision.py`新規作成（72件）
- `docs/design/retry_scheduler_decision_charter.md`新規作成（Project Charter、承認済み）
- `docs/design/retry_scheduler_decision.md`新規作成（Architecture Design。Architecture Review完了・**Approve with Minor Recommendations**、指摘事項3点を記録）

### Note

- **`RetrySchedulerSource.list_pending_retries()`の既存順序（priority昇順・enqueue_time昇順）をそのまま活用し、独自の並べ替え・優先度計算は一切行わない。** `select_candidates(limit)`は`list_pending_retries(limit)`への1行委譲、`select_next_candidate()`は`select_candidates(limit=1)`の先頭要素（またはNone）を返す便利メソッド
- **`retry_source`はデフォルト値を持たない必須引数とする。** `SchedulerEngine.__init__`の`retry_source`（デフォルト`None`）とは異なり、本コンポーネントにとって`retry_source`は唯一の実質的な入力であるため、省略時の安全な既定値という概念自体を持たない（`RetrySchedulerSource.__init__(queue)`がv3.3.0から必須引数であるのと同じ判断）
- **Null Object Pattern（`NullRetrySchedulerDecision`）は採用しない。** プロジェクト全体で一貫している「実装クラス／Nullクラス」ペアからの意図的な逸脱。本コンポーネント自身には対応するFeature Gate/Config軸が存在せず、「無効化」は呼び出し元が`retry_source`に`NullRetrySchedulerSource()`を渡すことで既に完結している（その場合`select_candidates()`は常に`[]`、`select_next_candidate()`は常に`None`を返す）ため
- **`SchedulerEngine`（`src/scheduler/`配下の全ファイル）は本Releaseでも無改修。** `retry_scheduler_decision`は`scheduler`を一切importせず、`scheduler`も本Releaseでは`retry_scheduler_decision`を一切importしない（相互に無関係）
- **`retry_scheduler_source` / `retry_queue` / `retry_engine`はいずれも本Releaseでも無改修。** 新規の依存方向は`retry_scheduler_decision → retry_scheduler_source`の一方向のみ
- **本Releaseでは`RetrySchedulerDecision`をどこからも呼び出さない。** `v3.3.0`の`RetrySchedulerSource`と同じ「消費者不在の先行実装」パターン
- 対象外：`SchedulerEngine`との実配線・選択結果を使った実行（自動Retry実行）・`RetryQueueManager.dequeue()` / `remove()`の使用・Retry Engineの起動・Queueの永続化（いずれも将来Release候補。詳細は`docs/design/retry_scheduler_decision_charter.md` 4章・10章）

### Tested

- `tests/test_e2e_v3_5_0_retry_scheduler_decision.py`: 72/72 PASS
- 既存回帰確認：`v2.0.0`（118/118）・`v2.2.0`（120/120）・`v2.3.0`（110/110）・`v2.4.0`（120/120）・`v2.5.0`（118/118）・`v2.6.0`（118/118）・`v2.7.0`（163/163）・`v2.8.0`（182/182）・`v2.9.0`（103/103）・`v3.0.0`（130/130）・`v3.1.0`（152/152）・`v3.2.0`（102/102）・`v3.4.0`（94/94）・`v1.20.0`（170/170）全PASS
- `v3.3.0`（71/72 PASS）：1件FAILは`[KI-4]`の延長（2026-07-03追記参照。新規Known Issueは追加していない）
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v3.4.0] - 2026-07-03 ★ Retry Scheduler Wiring

### Added

- `src/scheduler/scheduler_engine.py`（変更）：`SchedulerEngine`が`RetrySchedulerSource` / `NullRetrySchedulerSource`（v3.3.0）をConstructor Injectionで保持できるようにし、以下2メソッドを追加した
  - `count_pending_retries() -> int`：`RetrySchedulerSource.count_pending_retries()`への薄い委譲のみ
  - `list_pending_retries(limit: int | None = None) -> list`：`RetrySchedulerSource.list_pending_retries()`への薄い委譲のみ
- `SchedulerEngine.__init__`に`retry_source`引数（デフォルト`None`）を追加。省略時は`NullRetrySchedulerSource()`にフォールバックし、既存の`SchedulerEngine()` / `SchedulerEngine(clock=...)`呼び出しは無変更で動作する（後方互換性維持）
- `src/scheduler/__init__.py`（変更）：モジュールdocstringにv3.4.0の変更点を追記のみ。`__all__`は無変更
- `tests/test_e2e_v3_4_0_retry_scheduler_wiring.py`新規作成（94件）
- `docs/design/retry_scheduler_wiring_charter.md`新規作成（Project Charter、承認済み）
- `docs/design/retry_scheduler_wiring.md`新規作成（Architecture Design。Architecture Review完了・**Approve with Minor Recommendations**、指摘事項3点を記録）

### Note

- **`evaluate()` / `run_due()` / `_match*()`はいずれも無変更。** 判定サイクル（時刻ベースの判定・`SchedulerEvent`生成）には一切手を加えず、`count_pending_retries()` / `list_pending_retries()`という完全に独立した新規メソッドを追加する方式を採用した
- **`SchedulerEngine`は`RetryQueueManager`を直接保持しない。** Retry Queueへは`RetrySchedulerSource`経由でのみ間接的に到達する（v3.3.0のAdapter境界を維持）。`dequeue()` / `remove()`に相当するメソッドは`RetrySchedulerSource` / `NullRetrySchedulerSource`のいずれにも存在しないため、`SchedulerEngine`からは構造的に呼び出せない
- **`SchedulerManager`・新規Wrapperクラスは追加しない。** Constructor Injectionの受け口は`SchedulerEngine`に一本化した（Job CRUD責務の`SchedulerManager`とは責務が異なるため）
- **新規Feature Gate・Configクラス・Managerパターンはいずれも追加しない。** 有効/無効は呼び出し元が`RetrySchedulerSource`（実体）と`NullRetrySchedulerSource`のどちらを構築するかによって決まる、v3.3.0から一貫した設計を踏襲する
- **Retry Engineの起動・`dequeue()`・Retry Queueの更新・自動Retry実行・永続化はいずれも対象外。** 本Releaseは「Schedulerの判定サイクルがRetry Queueの状態を読み取れる」状態を作る接続（Wiring）のみを範囲とする（詳細は`docs/design/retry_scheduler_wiring_charter.md` 4章・8章）

### Tested

- `tests/test_e2e_v3_4_0_retry_scheduler_wiring.py`: 94/94 PASS
- 既存回帰確認：`v2.0.0`（118/118）・`v2.2.0`（120/120）・`v2.3.0`（110/110）・`v2.4.0`（120/120）・`v2.5.0`（118/118）・`v2.6.0`（118/118）・`v1.20.0`（170/170）全PASS
- `v2.7.0`（162/163）・`v2.8.0`（181/182）・`v2.9.0`（102/103）・`v3.0.0`（129/130）・`v3.1.0`（151/152）・`v3.2.0`（101/102）・`v3.3.0`（69/72）：各1〜3件のFAILは`[KI-4]`（本Releaseによる意図的な変更）を参照
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v3.3.0] - 2026-07-03 ★ Retry Scheduler Integration

### Added

- `src/retry_scheduler_source/`（新規パッケージ）：Retry Queue（v3.1.0）の状態（待機中の項目一覧・件数）を、Scheduler側の語彙で読み取るための最小Adapter
  - `retry_scheduler_source.py`: `RetrySchedulerSource`（`RetryQueueManager`をConstructor Injectionで保持し、`list_pending_retries(limit)` / `count_pending_retries()`への薄い委譲のみを行う）、`NullRetrySchedulerSource`（`retry_queue`への参照を一切保持せず、常に`[]` / `0`を返すダミー実装。継承関係を持たないDuck Typingペア）
  - `__init__.py`: `RetrySchedulerSource` / `NullRetrySchedulerSource`をexport
- `tests/test_e2e_v3_3_0_retry_scheduler_integration.py`新規作成（72件）
- `docs/design/retry_scheduler_integration_charter.md`新規作成（Project Charter、承認済み）
- `docs/design/retry_scheduler_integration.md`新規作成（Architecture Design。Architecture Review完了・**Approve with Minor Recommendations**、指摘事項3点を反映済み）

### Note

- **Feature Gate・Configクラス・Managerパターン（`from_config()` / `from_env()`等の起動口）はいずれも追加しない。** プロジェクト全体で一貫しているNull Object Pattern（`RetryManager`/`NullRetryManager`、`RetryQueueManager`/`NullRetryQueueManager`等と同じ、継承なしのDuck Typingペア）を踏襲し、有効/無効は呼び出し元が`RetrySchedulerSource`（実体）と`NullRetrySchedulerSource`のどちらを構築するかによって決まる
- **Constructor Injectionのみを採用。** `RetrySchedulerSource.__init__`は`RetryQueueManager`（実体）のみを受け取り、セッターインジェクション・Configからの再構築・ファクトリメソッドは持たない
- **`list()` / `count()`（非破壊の読み取り専用API）のみを使用。** `RetryQueueManager.dequeue()` / `remove()`は一切呼び出さない（構造的にテストで確認済み）
- **`src/scheduler/` / `src/retry_queue/` / `src/retry_engine/`はいずれも本Releaseでも無改修。** 新規の依存方向は`retry_scheduler_source → retry_queue`の一方向のみ（`NullRetrySchedulerSource`は`retry_queue`を一切importしない）
- **本Releaseでは`RetrySchedulerSource` / `NullRetrySchedulerSource`をどこからも呼び出さない。** `src/scheduler/`（`SchedulerEngine` / `SchedulerManager` / `SchedulerJob` / `SchedulerEvent`）からの実配線は行わない。`v2.9.0`のWorkflowMonitorManager・`v3.1.0`のRetryQueueと同じ「消費者不在のまま先行実装するFoundation」パターンを踏襲する
- 対象外：Scheduler本体（`SchedulerEngine.evaluate()` / `run_due()`）との実配線・Queueから取り出した項目の自動再実行（自動Retry実行）・`dequeue()` / `remove()`の使用・Queueの永続化・優先度付けアルゴリズムの高度化・CLIエントリスクリプト（いずれも将来Release候補。詳細は`docs/design/retry_scheduler_integration_charter.md` 4章・8章）

### Tested

- `tests/test_e2e_v3_3_0_retry_scheduler_integration.py`: 72/72 PASS
- 既存回帰確認：`v2.0.0`（118/118）・`v2.2.0`（120/120）・`v2.3.0`（110/110）・`v2.4.0`（120/120）・`v2.5.0`（118/118）・`v2.6.0`（118/118）・`v2.7.0`（163/163）・`v2.8.0`（182/182）・`v2.9.0`（103/103）・`v3.0.0`（130/130）・`v3.1.0`（152/152）・`v3.2.0`（102/102）全PASS
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）のため今回は実行対象外

---

## [v3.2.0] - 2026-07-02 ★ Retry Queue Integration

### Added

- `src/retry_engine/retry_manager.py`（変更）：`RetryManager`が`RetryQueueManager` / `NullRetryQueueManager`をDependency Injectionで保持できるようにし、以下2メソッドを追加した
  - `enqueue_retry(run_id, workflow_name, retry_attempt=1, priority=None)`: `RetryQueueManager.enqueue()`への薄い委譲のみ（判定・加工は一切行わない）
  - `dequeue_retry()`: `RetryQueueManager.dequeue()`への薄い委譲のみ
  - `RetryManager.from_config()`に`retry_queue_manager`引数（デフォルト`None`）を追加。省略時は`RetryManager.__init__`内で`NullRetryQueueManager()`にフォールバックするため、既存の4引数呼び出しは無変更で動作する
  - `NullRetryManager`にも同名2メソッドを追加。ただし`RetryQueueManager` / `NullRetryQueueManager`への参照は一切保持せず、常に自前で`outcome=DISABLED`を返す（Retry Engine自体が無効な場合は、Retry Queueの有効/無効に関わらず一律で無効化するため）
- `tests/test_e2e_v3_2_0_retry_queue_integration.py`新規作成（102件）
- `docs/design/retry_queue_integration_charter.md`新規作成（Project Charter、承認済み）
- `docs/design/retry_queue_integration.md`新規作成（Architecture Design。Architecture Review完了・**Approve with Minor Recommendations**、指摘事項3点をテスト観点へ反映済み）

### Note

- **Queue管理とRetry実行の責務分離を維持。** `enqueue_retry()` / `dequeue_retry()`は`RetryQueueManager`の対応メソッドへの委譲のみであり、容量チェック・重複チェック・優先度ソート等のQueue管理ロジックは一切`retry_engine`側に複製していない
- **`retry()`（Retry実行）と`enqueue_retry()` / `dequeue_retry()`（Queue操作）は呼び出しグラフ上で完全に独立。** `dequeue_retry()`が取り出した`RetryQueueItem`を自動的に`retry()`へ渡す変換ロジックは持たない（自動実行はしない。Scheduler連携も本Releaseの対象外）
- **`src/retry_queue/`は本Releaseでも無改修。** `retry_engine`が`retry_queue`の公開シンボル（`RetryQueueManager` / `NullRetryQueueManager` / `RetryQueueResult` / `RetryQueueOutcome`）をimportする片方向の依存が新規に追加された（`retry_engine → retry_queue`）
- `NullRetryManager`の`reason`文言（"Retry Engine is disabled..."）と、Retry Engineは有効だがQueueだけが無効な場合の`reason`文言（`NullRetryQueueManager`由来の"Retry Queue is disabled (RETRY_QUEUE_ENABLED=false)."）は意図的に区別されており、呼び出し元はどちらのゲートが閉じているかを`reason`文字列から判別できる
- 対象外：Queueから取り出した項目の自動再実行・Scheduler連携・Queue永続化・優先度付けアルゴリズムの高度化・CLIエントリスクリプト（いずれも将来Release候補）

### Tested

- `tests/test_e2e_v3_2_0_retry_queue_integration.py`: 102/102 PASS
- 既存回帰確認：`v2.0.0`（118/118）・`v2.2.0`（120/120）・`v2.3.0`（110/110）・`v2.4.0`（120/120）・`v2.5.0`（118/118）・`v2.6.0`（118/118）・`v2.7.0`（163/163）・`v2.8.0`（182/182）・`v2.9.0`（103/103）・`v3.0.0`（130/130）・`v1.20.0`（170/170）全PASS
- `v3.1.0`（151/152 PASS）：1件FAILは既知の差分（`[KI-3]`参照）。`retry_queue`パッケージ自体・その公開APIの挙動を検証する残り151件はすべてPASSしており、「`src/retry_queue/`無改修」は本Releaseの新規テスト（テスト14）でも別途確認済み
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題、本Releaseと無関係）によりFAIL。本Releaseのcommit対象には含めない

---

## [v3.1.0] - 2026-07-02 ★ Retry Queue Foundation

### Added

- `src/retry_queue/`（新規パッケージ）：再実行待ちの`run_id`を保持・出し入れするだけの最小基盤。Retry実行・Workflow Engine呼び出し・Retry Engine呼び出し・Workflow Monitor呼び出し・Execution History呼び出しはいずれも行わない
  - `retry_queue_status.py`: `RetryQueueStatus`（`WAITING` / `PROCESSING` / `CANCELLED` / `COMPLETED` / `FAILED`の5値。`COMPLETED` / `FAILED`は将来拡張用の予約値で本Releaseの操作からは到達しない。`WorkflowMonitorStatus.CANCELLED` / `WAITING`の前例を踏襲）
  - `retry_queue_item.py`: `RetryQueueItem`（`run_id` / `workflow_name` / `enqueue_time` / `priority` / `retry_attempt` / `status`。`frozen=True`にせず、`WorkflowMonitorRecord`と同様「Manager内部で書き換えられる記録」として設計）
  - `retry_queue_result.py`: `RetryQueueOutcome`（`ENQUEUED` / `DEQUEUED` / `REMOVED` / `REJECTED` / `NOT_FOUND` / `EMPTY` / `DISABLED`の7値）、`RetryQueueResult`
  - `retry_queue_config.py`: `RetryQueueConfig`（`RETRY_QUEUE_ENABLED`、デフォルト`true`。`RETRY_QUEUE_MAX_SIZE`、デフォルト`100`。`RETRY_QUEUE_DEFAULT_PRIORITY`、デフォルト`0`）
  - `retry_queue_manager.py`: `RetryQueueManager`（`enqueue` / `dequeue` / `remove` / `list` / `exists` / `count` の6操作のみを提供。内部に`dict[str, RetryQueueItem]`を保持する）
  - `null_retry_queue_manager.py`: `NullRetryQueueManager`（`RETRY_QUEUE_ENABLED=false`時のダミー実装。Charterで明示的にファイル分離が指定されているため、`retry_engine`の`NullRetryManager`（`retry_manager.py`に同居）とは異なり独立ファイルとした）
- `tests/test_e2e_v3_1_0_retry_queue_foundation.py`新規作成（152件）
- `docs/design/retry_queue_foundation.md`新規作成（Architecture Design。Project Charterはチャット上で提示された内容をSource of Truthとし、別ファイル化は本Releaseでは行っていない）

### Note

- **Queue管理（出し入れ）のみを責務とする。** Retry可否判定・Retry実行はいずれも行わない（それらは`RetryPolicy` / `RetryManager`の責務のまま）
- **`src/retry_queue/`は他のどの`src/*`パッケージもimportしない、標準ライブラリのみに依存する独立した葉パッケージ。** `workflow_engine` / `workflow_monitor` / `retry_engine` / `execution_history` / `ai` / `pipeline` / `scheduler`のいずれも呼び出さない。Retry Engine（`workflow_engine` / `workflow_monitor`の2パッケージに依存）よりもさらに徹底した独立性を持つ
- `dequeue()`は`priority`昇順（数値が小さいほど高優先。Unix `nice`と同じ向き）・`enqueue_time`昇順で先頭の項目を取り出す。取り出された項目は`status=PROCESSING`に更新された上でQueueから削除される（以後`list()` / `exists()` / `count()`には現れない）
- `remove()`で取り消された項目は`status=CANCELLED`に更新された上でQueueから削除される
- `enqueue()`は重複`run_id`・容量超過（`RETRY_QUEUE_MAX_SIZE`）のいずれも例外ではなく`RetryQueueResult(outcome=REJECTED)`で表現する（業務上想定される分岐は例外を投げない方針。`retry_engine`と同じ）
- 呼び出し元へ返す`RetryQueueItem`は常にコピー（`dataclasses.replace()`）であり、呼び出し元が書き換えても内部ストアには影響しない
- **`RETRY_QUEUE_ENABLED`のデフォルトは`true`**（`RETRY_ENGINE_ENABLED`のデフォルト`false`とは異なる判断）。Queue操作（enqueue/dequeue/remove/list/exists/count）はプロセス内メモリ上の`dict`を読み書きするだけで外部副作用を一切伴わないため、`EXECUTION_HISTORY_ENABLED` / `WORKFLOW_MONITOR_ENABLED`（読み取り中心、デフォルト`true`）と同じ分類とした
- Retry Queue自身はファイル・DBへの書き込みを一切行わない（完全にin-memory。プロセスが終了するとQueueの内容は失われる。永続化はOut of Scope）
- **本Releaseでは`RetryQueueManager`と`RetryManager`（Retry Engine）の実配線は行っていない。** `src/retry_queue/`はどのパッケージからもimportされない、消費者不在のまま先行リリースされるFoundation層（`WorkflowMonitorManager`・v2.9.0と同型のパターン）
- 対象外：Retry Engineとの実配線・Scheduler連携・Queue永続化（SQLite/Redis）・`COMPLETED` / `FAILED`への到達（結果フィードバックAPI）・Priority Queueの効率化（heapqベース）・Dead Letter Queue・Notification・Dashboard/API/UI（いずれも将来Release候補）

### Tested

- `tests/test_e2e_v3_1_0_retry_queue_foundation.py`: 152/152 PASS
- 既存回帰確認：`v2.0.0`（118/118 PASS）・`v2.2.0`（120/120 PASS）・`v2.3.0`（110/110 PASS）・`v2.4.0`（120/120 PASS）・`v2.5.0`（118/118 PASS）・`v2.6.0`（118/118 PASS）・`v2.7.0`（163/163 PASS）・`v2.8.0`（182/182 PASS）・`v2.9.0`（103/103 PASS）・`v3.0.0`（130/130 PASS）・`v1.20.0`（170/170 PASS）
- `v1.10.0`（Analytics Foundation）は`[KI-1]`（既知の問題。日付ハードコードによるテスト不具合、Release 3.1とは無関係）によりFAIL。本Releaseのcommit対象には含めない

---

## [v3.0.0] - 2026-07-02 ★ Retry Engine Foundation

### Added

- `src/retry_engine/`（新規パッケージ）：Workflow Monitor（v2.9.0）が`FAILED` / `TIMEOUT`と判定したWorkflowを、Workflow Engineの公開APIを通じて再実行する最小基盤
  - `retry_policy.py`: `RetryPolicy`（再実行対象の状態と最大試行回数を保持する、env非依存の業務ルール。`target_statuses`は`{FAILED, TIMEOUT}`固定、`max_attempts`は`RETRY_MAX_ATTEMPTS`、デフォルト`3`）
  - `retry_config.py`: `RetryConfig`（`RETRY_ENGINE_ENABLED`、デフォルト`false`）
  - `retry_request.py`: `RetryRequest`（`run_id` / `attempt` / `requested_at` / `dry_run` / `reason`）
  - `retry_result.py`: `RetryResult`、`RetryOutcome`（`RETRIED` / `SKIPPED` / `NOT_FOUND` / `DISABLED`の4値）
  - `retry_executor.py`: `RetryExecutor`（`WorkflowEngineManager`の公開APIを呼び出すだけの薄いコンポーネント。`RetryPolicy`を一切保持しない）
  - `retry_manager.py`: `RetryManager` / `NullRetryManager`（Retry可否判定・`RetryRequest`生成・`RetryExecutor`への委譲を担う起動口。`retry(run_id, attempt=1, dry_run=False)`）
- `tests/test_e2e_v3_0_0_retry_engine_foundation.py`新規作成（130件）
- `docs/design/retry_engine_foundation_charter.md`新規作成（Project Charter）
- `docs/design/retry_engine_foundation.md`新規作成（Architecture Design。Architecture Review完了・指摘事項4点反映済み。実装後の追加調整として`RetryManager.retry()`への`dry_run`引数追加を反映）

### Note

- **Retry判定・Retry Policy適用・RetryRequest生成はRetryManagerが担当し、RetryExecutorはWorkflowEngineManagerの公開APIを呼び出すだけの薄いコンポーネントとする**（Architecture Review反映）。`RetryExecutor`のコンストラクタは`policy`引数を持たない
- **`RetryManager.retry(run_id, attempt=1, dry_run=False)`でdry-run retryが可能**：`dry_run=True`を指定すると、生成される`RetryRequest.dry_run`が`RetryExecutor`経由で`WorkflowEngineManager.run(event, dry_run=True)`まで伝播し、実際のNews収集・WordPress下書き投稿を伴わずに再実行経路のみを確認できる。`dry_run`はキーワード引数でデフォルト`False`のため、既存の`retry(run_id)` / `retry(run_id, attempt=N)`という呼び出しの後方互換性は完全に維持される。`RetryExecutor` / `RetryRequest`の責務・データ構造はいずれも変更していない（`RetryRequest.dry_run`は初版から定義済みのフィールドを公開APIから使えるようにしただけ）
- **Workflowの状態を自ら保持しない（Stateless）**：状態判定は`WorkflowMonitorManager.get_status()`（v2.9.0の公開API）を毎回呼び出して取得する（Read Before Retry）。Execution Historyは直接参照・解釈しない
- **`WorkflowEngineManager`の公開API（`run()`）のみを呼び出す**：`WorkflowEngineExecutor`等の内部実装には一切依存しない
- `RetryManager.from_config()`は、呼び出し元が構築済みの`WorkflowEngineManager` / `WorkflowMonitorManager`をDependency Injectionで受け取る（Configから再構築しない）。これにより`src/retry_engine/`は`execution_history` / `ai` / `pipeline` / `scheduler`を一切importせず、`workflow_engine`と`workflow_monitor`の2パッケージのみに依存する
- `WorkflowMonitorStatus`はEnumとして比較する（文字列比較は行わない）
- デフォルトは無効（`RETRY_ENGINE_ENABLED=false`）。実際にWorkflowを再実行する（外部副作用を伴いうる）ため、`AI_AGENT_ENABLED` / `WORKFLOW_ENGINE_ENABLED`と同じ「安全側で止める」原則を適用（結果として三重ゲート）
- 再実行イベントの`source`は新規定数を追加せず、既存の`SOURCE_MANUAL`を再利用する（`workflow_engine`パッケージは無改修）。再実行由来であることは`WorkflowEngineEvent.metadata`（`retried_from` / `attempt`）で判別可能にする
- **Workflow Engine（v2.7.0）・Workflow Monitor（v2.9.0）・Execution History（v2.8.0）はいずれも無改修**
- 対象外：Retry Queue・Retry History・RetryDecision・RetryReason Enum・Exponential Backoff・Adaptive Retry・Metrics・Dashboard・Notification・Circuit Breaker・AI Retry Decision・Parallel Retry・Distributed Retry・Manual Retry UI・CLIエントリスクリプト（いずれも将来Release候補）

### Tested

- `tests/test_e2e_v3_0_0_retry_engine_foundation.py`: 130/130 PASS（`dry_run`引数追加分5件を含む）
- 既存回帰確認：`v2.0.0`（118/118 PASS）・`v2.2.0`（120/120 PASS）・`v2.3.0`（110/110 PASS）・`v2.4.0`（120/120 PASS）・`v2.5.0`（118/118 PASS）・`v2.6.0`（118/118 PASS）・`v2.7.0`（163/163 PASS）・`v2.8.0`（182/182 PASS）・`v2.9.0`（103/103 PASS）・`v1.20.0`（170/170 PASS）

---

## [v2.9.0] - 2026-07-02 ★ Workflow Monitor Foundation

### Added

- `src/workflow_monitor/`（新規パッケージ）：Execution History（v2.8.0）が記録した`WorkflowExecutionRecord`を読み取り、Workflowの実行状態を判定するだけの最小基盤
  - `workflow_monitor_status.py`: `WorkflowMonitorStatus`（RUNNING/SUCCESS/FAILED/TIMEOUT/CANCELLED/WAITINGの6値。CANCELLED/WAITINGは将来拡張用の予約値で判定ロジックからは到達しない）
  - `workflow_monitor_config.py`: `WorkflowMonitorConfig`（`WORKFLOW_MONITOR_ENABLED`、デフォルト`true`。`WORKFLOW_MONITOR_TIMEOUT_SECONDS`、デフォルト`3600`秒）
  - `workflow_monitor_record.py`: `WorkflowMonitorRecord`（`run_id` / `monitor_status` / `source_status` / `elapsed_seconds` / `reason` / `steps`等）
  - `workflow_monitor.py`: `WorkflowMonitor`（`ExecutionHistoryStore`を読み取り専用で参照し状態を判定するロジック本体）
  - `workflow_monitor_manager.py`: `WorkflowMonitorManager` / `NullWorkflowMonitorManager`
- `scripts/show_workflow_status.py`新規作成（読み取り専用CLI。`--run-id` / `--limit`対応。`WORKFLOW_MONITOR_ENABLED=false`でもゲートをバイパスして常に判定結果を表示）
- `tests/test_e2e_v2_9_0_workflow_monitor_foundation.py`新規作成（103件）
- `docs/design/workflow_monitor_foundation_charter.md`新規作成（Project Charter）
- `docs/design/workflow_monitor_foundation.md`新規作成（Architecture Design。Architecture Review完了・指摘事項3点反映済み）

### Note

- **Execution Historyを唯一の情報源（Single Source of Truth）とする**：Workflow Engineの内部状態・メモリ上の状態・一時キャッシュには一切依存せず、すべての状態判定は`ExecutionHistoryStore`から読み取った`WorkflowExecutionRecord`から導出する
- 判定対応は`RUNNING` / `SUCCESS` / `FAILED` / `TIMEOUT`の4状態。`TIMEOUT`は`status=RUNNING`のまま`WorkflowMonitorConfig.timeout_seconds`（デフォルト3600秒）を超過した場合に判定される。`CANCELLED` / `WAITING`はEnumに定義されるが、判定対象となる元データがWorkflow Engine・Execution Historyのいずれにも存在しないため、将来拡張用の予約値として判定ロジックには組み込まれていない
- Workflow Monitorは読み取り専用。Execution Historyへの書き込みは一切行わない（`ExecutionHistoryStore.save()`を呼ばない）。stateless設計で、判定結果を独自に永続化・キャッシュしない
- `src/workflow_monitor/`は`src/execution_history/`のみをimportする一方向依存。`workflow_engine` / `ai` / `pipeline` / `scheduler`はいずれもimportしない
- **Workflow Engine（v2.7.0）・Execution History（v2.8.0）はいずれも無改修**
- 将来のRetry Engine・Metrics Foundation・Dashboard Foundationの前提基盤として位置づける。これらはいずれも本Releaseの対象外
- デフォルトは有効（`WORKFLOW_MONITOR_ENABLED=true`）。Execution History（v2.8.0）と同じ「読み取り専用・外部副作用なし」の理由による

### Tested

- `tests/test_e2e_v2_9_0_workflow_monitor_foundation.py`: 103/103 PASS
- 既存回帰確認：`v2.0.0`（118/118 PASS）・`v2.2.0`（120/120 PASS）・`v2.3.0`（110/110 PASS）・`v2.4.0`（120/120 PASS）・`v2.5.0`（118/118 PASS）・`v2.6.0`（118/118 PASS）・`v2.7.0`（163/163 PASS）・`v2.8.0`（182/182 PASS）・`v1.20.0`（170/170 PASS）

---

## [v2.8.0] - 2026-07-02 ★ Execution History Foundation

### Added

- `src/execution_history/`（新規パッケージ）：Workflow Engine（v2.7.0）が実行した各Workflowについて、実行の開始・終了・各Stepの結果を観測して記録するだけの最小基盤
  - `execution_history_config.py`: `ExecutionHistoryConfig`（`EXECUTION_HISTORY_ENABLED`、デフォルト`true`。`EXECUTION_HISTORY_DIR`、デフォルト`logs/execution_history`）
  - `execution_history_event.py`: `ExecutionHistoryEvent`、`EVENT_WORKFLOW_STARTED` / `EVENT_WORKFLOW_FINISHED` / `EVENT_STEP_STARTED` / `EVENT_STEP_FINISHED`
  - `step_execution_record.py`: `StepExecutionRecord`、`StepExecutionStatus`（RUNNING/SUCCESS/FAILED/SKIPPED/NOT_REACHED）
  - `workflow_execution_record.py`: `WorkflowExecutionRecord`、`WorkflowExecutionStatus`（RUNNING/SUCCESS/FAILED）
  - `execution_history_store.py`: `ExecutionHistoryStore`（ABC、`SchedulerRepository`と同型）
  - `json_execution_history_store.py`: `JsonExecutionHistoryStore`（1実行=1 JSONファイル、`logs/execution_history/{run_id}.json`）
  - `execution_history_manager.py`: `ExecutionHistoryManager` / `NullExecutionHistoryManager`
- `scripts/show_execution_history.py`新規作成（読み取り専用CLI。`--run-id` / `--limit`対応。`EXECUTION_HISTORY_ENABLED=false`でも過去の履歴を閲覧可能）
- `tests/test_e2e_v2_8_0_execution_history_foundation.py`新規作成（182件）
- `docs/design/execution_history_foundation_charter.md`新規作成（Project Charter）
- `docs/design/execution_history_foundation.md`新規作成（Architecture Design）

### Changed

- `src/workflow_engine/workflow_engine_executor.py`：`history_manager`引数を追加（省略時は`NullExecutionHistoryManager`）。各ステップの分岐結果を`ExecutionHistoryManager`へ横流しして記録する呼び出しを追加。既存の実行制御ロジック（Gate二層構造・打ち切り基準・`WorkflowEngineResult`の組み立て）は無変更
- `src/workflow_engine/workflow_engine_manager.py`：`from_config()`内で`ExecutionHistoryConfig.from_env()` → `ExecutionHistoryManager.from_config()`を構築し、`WorkflowEngineExecutor`へDIする処理を追加

### Note

- **Execution Historyは「実行の観測・記録」専任**：Workflow Engineの実行判断・分岐・再試行判断には一切関与しない。どのステップを実行するか・どこで打ち切るかは引き続き`WorkflowEngineExecutor`が単独で決定し、Execution Historyはその結果を受け取って記録するのみ
- Release 2.8では履歴は**記録専用**。Retry Engine・Workflow Monitor・Metrics Foundation・Dashboard Foundationはいずれも対象外（将来Release）
- `src/execution_history/`は`src/workflow_engine/` / `src/ai/` / `src/pipeline/` / `src/scheduler/`のいずれもimportしない。**`workflow_engine` → `execution_history`の一方向依存**を維持する（`WorkflowEngineStep`型を直接渡さず、`step.value`という`str`のみを受け渡す）
- デフォルトは有効（`EXECUTION_HISTORY_ENABLED=true`）。`LOG_ENABLED`（v1.8.0）と同じく、ローカルJSONファイルへの記録のみで外部への副作用を持たないため「原則有効」とした（Agent系ゲートのデフォルト`false`とは性質が異なる）
- 無効時（`EXECUTION_HISTORY_ENABLED=false`）は`NullExecutionHistoryManager`が全メソッドをno-opで処理し、Workflow Engine本体の動作・戻り値は一切変わらない
- JSON書き込み失敗時は警告を出力して処理を継続する（履歴記録の失敗がWorkflow本体の成否に影響しない設計）
- E2Eテスト182/182 PASS、既存回帰（`v2.0.0` 118/118・`v2.2.0` 120/120・`v2.3.0` 110/110・`v2.4.0` 120/120・`v2.5.0` 118/118・`v2.6.0` 118/118・`v2.7.0` 163/163・`v1.20.0` 170/170）PASS

---

## [v2.7.0] - 2026-07-02 ★ Workflow Engine Foundation

### Added

- `src/workflow_engine/`（新規パッケージ）：Scheduler（v2.6.0）が生成する`SchedulerEvent`を起点に、既存3つのTrigger Agent（`NewsAgent` v2.2.0 → `ReviewTriggerAgent` v2.5.0 → `PublishTriggerAgent` v2.4.0）を決まった順序で実行するオーケストレーション層
  - `workflow_engine_step.py`: `WorkflowEngineStep`（NEWS / REVIEW / PUBLISHの3種類）、`ALL_WORKFLOW_ENGINE_STEPS`
  - `workflow_engine_definition.py`: `WorkflowEngineDefinition`（実行するステップの並びを定義）
  - `workflow_engine_event.py`: `WorkflowEngineEvent`（`job_id` / `source` / `triggered_at` / `trigger_reason` / `metadata`）、`SOURCE_SCHEDULER` / `SOURCE_MANUAL`
  - `workflow_engine_context.py`: `WorkflowEngineContext`
  - `workflow_engine_result.py`: `WorkflowEngineStepResult` / `WorkflowEngineResult`、`REASON_NOT_REACHED`
  - `workflow_engine_config.py`: `WorkflowEngineConfig`（`WORKFLOW_ENGINE_ENABLED`、デフォルト`false`）
  - `workflow_engine_executor.py`: `WorkflowEngineExecutor`（既存`AgentExecutor.execute()`を無改修のまま順に呼び出す実行エンジン）
  - `workflow_engine_manager.py`: `WorkflowEngineManager` / `NullWorkflowEngineManager`
- `scripts/run_workflow_engine.py`新規作成（`--dry-run` / `--job-id`対応。固定・最小限（1件）のデモSchedulerJobのみを扱う）
- `tests/test_e2e_v2_7_0_workflow_engine_foundation.py`新規作成（163件、`FakeAgent`によるExecutor単体テストを含む）
- `docs/design/workflow_engine_foundation_charter.md`新規作成（Project Charter）
- `docs/design/workflow_engine_foundation.md`新規作成（Architecture Design。Architecture Review完了・修正必須事項3点反映済み）

### Note

- パッケージ・クラス名（`WorkflowEngine`接頭辞）の両方を`src/ai/workflow_*.py`（v1.20.0、AI記事改善6ステップ用）と分離し、名前衝突を回避した
- Gate二層構造：Workflow Engine全体は二重ゲート（`AI_AGENT_ENABLED` × `WORKFLOW_ENGINE_ENABLED`）、各ステップ（NEWS/REVIEW/PUBLISH）の実行可否は既存Trigger AgentのConfigの`is_ready()`をそのまま再利用する
- 打ち切り基準：実行した結果として失敗した（`AgentResult.success=False`）場合のみ後続ステップを打ち切る。Gate閉鎖・`decide()`によるスキップは失敗として扱わず、後続ステップの実行を継続する。打ち切り発生時も未到達ステップは`WorkflowEngineResult.steps`に`REASON_NOT_REACHED`として記録され、常に`len(definition.steps)`件になる
- `WorkflowEngineManager`は`AgentManager`（v2.0.0）を経由せず、既存の`NewsAgent` / `ReviewTriggerAgent` / `PublishTriggerAgent`とそれぞれの`Config` / `PipelineRunner`を無改修のままimportして独自に構築する（既存4 Trigger Agent・`AgentManager` / `AgentExecutor`・Scheduler本体はいずれも無改修）
- `WorkflowTriggerAgent`（v2.3.0、AI改善6ステップ）は`PublishTriggerAgent`との役割重複を理由に今回のステップには含めない（将来Releaseで再検討）
- **運用上の制約**：`AgentManager`経由の既存script群（`run_news_agent.py`等）と`scripts/run_workflow_engine.py`を同時実行しないこと。`decide()`から`act()`完了までロック機構がないため、同時実行するとNews収集・レビューレポート生成・WordPress下書き投稿等が二重に発生するリスクがある（ロック実装はRelease 2.7の対象外、`docs/design/workflow_engine_foundation.md` 13.1節）
- `scripts/run_workflow_engine.py`は固定・最小限（1件のみ）のデモSchedulerJobを扱う。複数Job・設定ファイル化・動的登録・SchedulerRepositoryの永続化はいずれも対象外（Future Extensions）
- デフォルトは無効（`WORKFLOW_ENGINE_ENABLED=false`）。既存フローに影響なし

### Tested

- `tests/test_e2e_v2_7_0_workflow_engine_foundation.py`: 163/163 PASS
- 既存回帰確認：`v2.0.0`（118/118 PASS）・`v2.2.0`（120/120 PASS）・`v2.3.0`（110/110 PASS）・`v2.4.0`（120/120 PASS）・`v2.5.0`（118/118 PASS）・`v2.6.0`（118/118 PASS）・`v1.20.0`（170/170 PASS）

---

## [v2.6.0] - 2026-07-02 ★ Scheduler Agent Foundation

> 本エントリはcommit `0d28d30`時点でCHANGELOG.mdへの記載が漏れていたため、v2.7.0ドキュメント整備作業（2026-07-02）で実装済みコードを確認のうえ遡及的に追記したものです（[KI-2]参照）。

### Added

- `src/scheduler/`（新規パッケージ）：`SchedulerJob` / `TriggerType` / `SchedulerEvent` / `SchedulerRepository` / `InMemorySchedulerRepository` / `SchedulerManager` / `SchedulerEngine` / `ClockProvider` / `SystemClockProvider` / `SchedulerConfig` / Scheduler例外群（`SchedulerError` / `SchedulerJobNotFoundError` / `DuplicateSchedulerJobError`）を新規実装
  - `scheduler_job.py`: `TriggerType`（DAILY / INTERVAL / ONCEの3種類のみ、cron完全互換ではない）、`SchedulerJob`（`job_id` / `name` / `trigger_type` / `schedule` / `enabled` / `metadata`）
  - `scheduler_event.py`: `SchedulerEvent`（`job_id` / `execute_time` / `trigger_reason` / `metadata`）。Schedulerは判断結果としてこのEventを生成するのみで、実際のAgent起動・処理実行は一切行わない
  - `scheduler_repository.py`: `SchedulerRepository`（ABC）/ `InMemorySchedulerRepository`（Foundation Releaseではメモリ管理のみ、永続化は対象外）
  - `scheduler_manager.py`: `SchedulerManager`（Jobの登録・削除・取得・一覧・enable/disable。`NewsAgent`等の既存Trigger Agentは一切importしない）
  - `scheduler_engine.py`: `SchedulerEngine`（`evaluate(jobs, now)`は副作用のない純粋関数。`run_due(jobs)`は`ClockProvider`経由で現在時刻を取得する便利メソッド）、`ClockProvider` / `SystemClockProvider`
  - `scheduler_config.py`: `SchedulerConfig`（`SCHEDULER_ENABLED`、デフォルト`false`）
  - `exceptions.py`: `SchedulerError` / `SchedulerJobNotFoundError` / `DuplicateSchedulerJobError`
- `tests/test_e2e_v2_6_0_scheduler_agent_foundation.py`新規作成（118件）

### Note

- `src/scheduler/`は`src/ai/` / `src/pipeline/`を一切importしない独立パッケージとして設計されている（Event Driven Architecture：Schedulerは判断のみを行い、実際の処理起動はSchedulerEventを受け取る側の責務とする）
- 本バージョン時点では、`SchedulerEvent`を受け取ってAgentを起動する呼び出し元は未実装（Foundation Releaseのため、判定エンジンの骨組みのみ）。この接続はv2.7.0（Workflow Engine Foundation）で実装された
- Foundation Releaseのため、cron完全互換ではない（TriggerTypeはDAILY / INTERVAL / ONCEの3種類のみ、分単位マッチング）。retry・last_run_at保持・永続化・Windows Task Scheduler / Linux cron連携はいずれも対象外（将来Releaseの拡張候補）
- デフォルトは無効（`SCHEDULER_ENABLED=false`）
- 設計書（Project Charter / Architecture Design）は本リリースでは作成されなかった（[KI-2]参照。既知のドキュメント負債。詳細な設計判断は各クラスのdocstringに記録されている）

### Tested

- `tests/test_e2e_v2_6_0_scheduler_agent_foundation.py`: 118/118 PASS（v2.7.0ドキュメント整備作業時に再実行し確認）

---

## [v2.5.0] - 2026-07-02 ★ Review Trigger Agent Foundation

### Added

- `src/ai/review_trigger_agent_config.py`: `ReviewTriggerAgentConfig`（`enabled` / `min_interval_minutes` / `reports_dir` / `project_root`。`REVIEW_TRIGGER_AGENT_ENABLED`（デフォルト`false`）・`REVIEW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES`（デフォルト`1440`分＝24時間）の環境変数から`from_env(project_root)`で構築。`is_ready()`は`enabled`のみを返す二重ゲート方式）
- `src/ai/review_trigger_agent.py`: `ReviewTriggerAgent`（`BaseAgent`継承）。`decide()`は`outputs/ai_publish_review_reports/`配下のレポートファイル（読み取り専用）のmtimeから経過時間を判断し、`act()`は`ReviewPipelineRunner.run()`のみを呼ぶ
- `src/pipeline/review_pipeline_runner.py`: `ReviewPipelineRunner`。`AiPublishReviewService.from_paths()` / `service.run()` / `service.get_reviews()`を`run()`メソッド内で直接呼び出す薄いラッパー（`PublishPipelineRunner`と同じくsubprocess不使用）
- `scripts/run_review_trigger_agent.py`新規作成（`--dry-run` / `--article-id`対応の手動実行エントリ）
- `tests/test_e2e_v2_5_0_review_trigger_agent_foundation.py`新規作成（118件）
- `docs/design/review_trigger_agent_charter.md`新規作成（Project Charter）
- `docs/design/review_trigger_agent_foundation.md`新規作成（Architecture Design。実装完了後に内容整合を確認済み）

### Changed

- `src/ai/agent_manager.py`: `AgentManager.from_config()`の`executors`構築部分を更新。二重ゲート方式（1段目：`AI_AGENT_ENABLED`、2段目：`ReviewTriggerAgentConfig.is_ready()`＝`REVIEW_TRIGGER_AGENT_ENABLED`）が揃った場合のみ、`ReviewPipelineRunner` / `ReviewTriggerAgent`を生成し`AgentExecutor(ReviewTriggerAgent(...))`を`executors`に追加登録する（`NewsAgent` / `WorkflowTriggerAgent` / `PublishTriggerAgent`のDIは無変更のまま維持）
- `src/ai/__init__.py`: `ReviewTriggerAgent` / `ReviewTriggerAgentConfig`を新規export
- `src/pipeline/__init__.py`: `ReviewPipelineRunner`を新規export

### Note

- `ReviewTriggerAgent`＝「判断」、`ReviewPipelineRunner`＝「実行」、`AiPublishReviewService`＝「公開前レビューレポート生成処理」という3層の責務分離を徹底（`NewsAgent`・`WorkflowTriggerAgent`・`PublishTriggerAgent`と同じAgent → Pipeline → Runnerパターンの4例目）
- **二重ゲート方式（他3Agentとの違い）**：`WorkflowTriggerAgent` / `PublishTriggerAgent`は三重ゲート（対象Service側の`is_ready()`相当を3段目として再利用）だが、`ReviewTriggerAgent`は二重ゲート（`AI_AGENT_ENABLED` × `REVIEW_TRIGGER_AGENT_ENABLED`）で確定している。理由は、対象の`AiPublishReviewService`（v1.19.0）に`Config`クラス・`is_ready()`相当の判定が存在しないため。3段目を実現するために`AiPublishReviewService`側へ`Config`を後付けすることは対象Service本体の改修になるため行わず、二重ゲートのまま安全側（デフォルト無効）に倒す設計とした（Project Charter・Architecture Designで合意済み。`docs/design/review_trigger_agent_foundation.md` §6参照）
- `dry_run=True`の場合、`AgentExecutor`（v2.0.0の既存設計）により`ReviewTriggerAgent.act()`自体が呼ばれないため、`ReviewPipelineRunner.run()`（＝レビューレポート生成）は構造的に発生しない
- デフォルトは無効（`REVIEW_TRIGGER_AGENT_ENABLED=false`）。既存フローに影響なし
- 詳細設計は`docs/design/review_trigger_agent_foundation.md`を参照

### Tested

- `tests/test_e2e_v2_5_0_review_trigger_agent_foundation.py`: 118/118 PASS
- 既存回帰確認：`v2.0.0`（118/118 PASS）・`v2.2.0`（120/120 PASS）・`v2.3.0`（110/110 PASS）・`v2.4.0`（120/120 PASS）・`v1.20.0`（170/170 PASS）

---

## [v2.4.0] - 2026-07-02 ★ Publish Trigger Agent Foundation

### Added

- `src/ai/publish_trigger_agent_config.py`: `PublishTriggerAgentConfig`（`enabled` / `min_interval_minutes` / `reports_dir` / `publish_enabled` / `project_root`。`PUBLISH_TRIGGER_AGENT_ENABLED`（デフォルト`false`）・`PUBLISH_TRIGGER_AGENT_MIN_INTERVAL_MINUTES`（デフォルト`1440`分＝24時間）の環境変数、および既存`AiPublishConfig.from_env().is_ready()`（`AI_PUBLISH_ENABLED`＋WordPress認証情報3点）を再利用した`publish_enabled`判定から`from_env(project_root)`で構築）
- `src/ai/publish_trigger_agent.py`: `PublishTriggerAgent`（`BaseAgent`継承）。`decide()`は`outputs/ai_publish_reports/`配下のレポートファイル（読み取り専用）のmtimeから経過時間を判断し、`act()`は`PublishPipelineRunner.run()`のみを呼ぶ
- `src/pipeline/publish_pipeline_runner.py`: `PublishPipelineRunner`。`AiPublishService.from_env()` / `service.run()` / `service.get_results()`を`run()`メソッド内で直接呼び出す薄いラッパー（`WorkflowPipelineRunner`と同じくsubprocess不使用）
- `scripts/run_publish_trigger_agent.py`新規作成（`--dry-run` / `--article-id`対応の手動実行エントリ）
- `tests/test_e2e_v2_4_0_publish_trigger_agent_foundation.py`新規作成（39件）
- `docs/design/publish_trigger_agent_foundation.md`新規作成（本リリースで追加。実装完了後の事後整備）

### Changed

- `src/ai/agent_manager.py`: `AgentManager.from_config()`の`executors`構築部分を更新。三重ゲート方式（1段目：`AI_AGENT_ENABLED`、2・3段目：`PublishTriggerAgentConfig.is_ready()`＝`PUBLISH_TRIGGER_AGENT_ENABLED`かつ`AiPublishConfig.is_ready()`）が揃った場合のみ、`PublishPipelineRunner` / `PublishTriggerAgent`を生成し`AgentExecutor(PublishTriggerAgent(...))`を`executors`に追加登録する（`NewsAgent` / `WorkflowTriggerAgent`のDIは無変更のまま維持）
- `src/ai/__init__.py`: `PublishTriggerAgent` / `PublishTriggerAgentConfig`を新規export
- `src/pipeline/__init__.py`: `PublishPipelineRunner`を新規export

### Note

- `PublishTriggerAgent`＝「判断」、`PublishPipelineRunner`＝「実行」、`AiPublishService`＝「WordPress下書き投稿処理」という3層の責務分離を徹底（`NewsAgent`・`WorkflowTriggerAgent`と同じAgent → Pipeline → Runnerパターンの3例目）
- **三重ゲート方式**：`AI_AGENT_ENABLED=true`にしただけではPublishは自動実行されない。`PUBLISH_TRIGGER_AGENT_ENABLED=true`（デフォルト`false`）を明示的に設定し、かつ既存の`AI_PUBLISH_ENABLED=true`＋WordPress認証情報3点（`WORDPRESS_URL` / `WORDPRESS_USERNAME` / `WORDPRESS_APP_PASSWORD`）が揃っている場合にのみ`PublishTriggerAgent`がDIされる
- `dry_run=True`の場合、`AgentExecutor`（v2.0.0の既存設計）により`PublishTriggerAgent.act()`自体が呼ばれないため、`PublishPipelineRunner.run()`（＝WordPressへの実書き込み）は構造的に発生しない
- デフォルトは無効（`PUBLISH_TRIGGER_AGENT_ENABLED=false`）。既存フローに影響なし
- 詳細設計は`docs/design/publish_trigger_agent_foundation.md`を参照

### Tested

- `tests/test_e2e_v2_4_0_publish_trigger_agent_foundation.py`: 120/120 PASS
- 既存回帰確認：`v2.0.0`（118/118 PASS）・`v2.2.0`（120/120 PASS）・`v2.3.0`（110/110 PASS）・`v1.20.0`（170/170 PASS）

---

## [v2.3.0] - 2026-07-02 ★ Workflow Trigger Agent Foundation

### Added

- `src/ai/workflow_trigger_agent_config.py`: `WorkflowTriggerAgentConfig`（`enabled` / `min_interval_minutes` / `reports_dir` / `workflow_enabled` / `project_root`。`WORKFLOW_TRIGGER_AGENT_ENABLED`（デフォルト`false`）・`WORKFLOW_TRIGGER_AGENT_MIN_INTERVAL_MINUTES`（デフォルト`1440`分＝24時間）の環境変数、および既存`WorkflowConfig.from_env(base_dir=project_root).is_ready()`を再利用した`AI_WORKFLOW_ENABLED`判定から`from_env(project_root)`で構築）
- `src/ai/workflow_trigger_agent.py`: `WorkflowTriggerAgent`（`BaseAgent`継承）。`decide()`は`outputs/workflow_reports/`配下のレポートファイル（読み取り専用）のmtimeから経過時間を判断し、`act()`は`WorkflowPipelineRunner.run()`のみを呼ぶ
- `src/pipeline/workflow_pipeline_runner.py`: `WorkflowPipelineRunner`。`WorkflowConfig.from_env()` / `WorkflowRunner.from_config()` / `WorkflowRunner.run()`を`run()`メソッド内で直接呼び出す薄いラッパー（`NewsPipelineRunner`と異なりsubprocessは使わない。`WorkflowRunner`には`main.py`のような`sys.exit()`/`argparse`問題がなく、直接呼び出しで安全に実装できるため）
- `scripts/run_workflow_trigger_agent.py`新規作成（`--dry-run` / `--article-id` / `--workflow-dry-run`対応の手動実行エントリ）
- `tests/test_e2e_v2_3_0_workflow_trigger_agent_foundation.py`新規作成（110件）
- `docs/design/workflow_trigger_agent_foundation.md`新規作成（本リリースで追加）

### Changed

- `src/ai/agent_manager.py`: `AgentManager.from_config()`の`executors`構築部分を更新。二重ゲート方式（1段目：`AI_AGENT_ENABLED`、2段目：`WorkflowTriggerAgentConfig.is_ready()`＝`WORKFLOW_TRIGGER_AGENT_ENABLED`かつ`AI_WORKFLOW_ENABLED`）が両方成立した場合のみ、`WorkflowPipelineRunner` / `WorkflowTriggerAgent`を生成し`AgentExecutor(WorkflowTriggerAgent(...))`を`executors`に追加登録する（`NewsAgent`のDIは無変更のまま維持）
- `src/ai/__init__.py`: `WorkflowTriggerAgent` / `WorkflowTriggerAgentConfig`を新規export
- `src/pipeline/__init__.py`: `WorkflowPipelineRunner`を新規export

### Note

- `WorkflowTriggerAgent`＝「判断」、`WorkflowPipelineRunner`＝「実行」、`WorkflowRunner`＝「オーケストレーション」という3層の責務分離を徹底。`WorkflowTriggerAgent`は`WorkflowRunner`を一切importせず、`WorkflowPipelineRunner.run(params) -> PipelineResult`という薄いインターフェースのみに依存する
- **二重ゲート方式**：`AI_AGENT_ENABLED=true`にしただけではPublishを含むWorkflowは自動実行されない。`WORKFLOW_TRIGGER_AGENT_ENABLED=true`（デフォルト`false`）を明示的に設定し、かつ`AI_WORKFLOW_ENABLED=true`（デフォルト`true`）である場合にのみ`WorkflowTriggerAgent`がDIされる。News収集（`NewsAgent`）とWorkflow自動実行を独立して制御できる、安全側の設計判断
- `WorkflowPipelineRunner`が`WorkflowRunner`を直接importすることは、`src/pipeline/`が`src/ai/`をimportする形になるが、`ai`パッケージのimportを`run()`メソッド内に遅延させることで`pipeline → ai → pipeline`という循環importを構造的に回避している
- `main.py`本体・`WorkflowRunner`本体（`workflow_runner.py`等）・`NewsAgent` / `NewsPipelineRunner`・`BaseAgent` / `AgentExecutor` / `AgentContext` / `AgentDecision` / `AgentResult` / `AgentConfig`は無変更（`git diff`で確認済み）
- `dry_run=True`の場合、`AgentExecutor`（v2.0.0の既存設計）により`WorkflowTriggerAgent.act()`自体が呼ばれないため、`WorkflowPipelineRunner.run()`（＝`WorkflowRunner.run()`起動、Publishを含む）は構造的に発生しない
- デフォルトは無効（`WORKFLOW_TRIGGER_AGENT_ENABLED=false`）。既存フローに影響なし

### Tested

- `tests/test_e2e_v2_3_0_workflow_trigger_agent_foundation.py`: 110/110 PASS
- 既存回帰確認：`v2.0.0`（118/118 PASS）・`v2.2.0`（120/120 PASS）・`v1.20.0`（170/170 PASS）

---

## [v2.2.0] - 2026-07-01 ★ News Agent Foundation

### Added

- `src/ai/news_agent_config.py`: `NewsAgentConfig`（`min_interval_minutes` / `timeout_sec` / `log_lookback_days` / `main_py_path` / `working_directory` / `python_executable`。`NEWS_AGENT_MIN_INTERVAL_MINUTES`等の環境変数から`from_env(project_root)`で構築）
- `src/ai/news_agent.py`: `NewsAgent`（`BaseAgent`継承）。`decide()`は`logs/execution/`配下の実行ログ（読み取り専用）から経過時間を判断し、`act()`は`NewsPipelineRunner.run()`のみを呼ぶ
- `src/pipeline/`（新規パッケージ、実行層）
  - `pipeline_result.py`: `PipelineResult`（`success` / `returncode` / `elapsed_sec` / `stdout_log_path` / `stderr_log_path` / `error_message`）
  - `news_pipeline_runner.py`: `NewsPipelineRunner`。`main.py`をsubprocessとして起動し、timeout・stdout/stderr保存・returncode判定を担う
- `scripts/run_news_agent.py` 新規作成（`--dry-run` / `--max-articles`対応の手動実行エントリ）
- `tests/test_e2e_v2_2_0_news_agent_foundation.py` 新規作成
- `docs/design/news_agent_foundation.md` 新規作成（本リリースで追加）

### Changed

- `src/ai/agent_manager.py`: `AgentManager.from_config()`の`executors`構築部分のみ更新。`AI_AGENT_ENABLED=true`の場合に`NewsAgentConfig` / `NewsPipelineRunner` / `NewsAgent`を生成し、`AgentExecutor(NewsAgent(...))`を`executors`に登録する（v2.0.0時点の`executors=[]`から初めて実体を持つ）
- `src/ai/__init__.py`: `NewsAgent` / `NewsAgentConfig`を新規export（既存のimport/exportは変更なし）

### Note

- Agent＝「判断」、PipelineRunner＝「実行」の責務分離を徹底。`NewsAgent`はsubprocessも`main.py`のパスも知らず、`NewsPipelineRunner.run(params) -> PipelineResult`という薄いインターフェースのみに依存する
- `NewsPipelineRunner`（`src/pipeline/`）はAgent層の型・`WorkflowRunner`を一切importしない（`ai → pipeline`の一方向依存）。将来のWorkflow Trigger Agent / Publish Agent / Scheduler Agentが同じ実行層の形を再利用できる想定
- `main.py`本体・既存ニュース収集パイプライン（`collector.py`等）・`WorkflowRunner`・`BaseAgent` / `AgentExecutor` / `AgentContext` / `AgentDecision` / `AgentResult`は無変更（`git diff`で確認済み）
- `dry_run=True`の場合、`AgentExecutor`（v2.0.0の既存設計）により`NewsAgent.act()`自体が呼ばれないため、`NewsPipelineRunner.run()`（＝`main.py`起動）は構造的に発生しない
- デフォルトは無効（`AI_AGENT_ENABLED=false`）。既存フローに影響なし

### Tested

- `tests/test_e2e_v2_2_0_news_agent_foundation.py`: 117/117 PASS
- 既存回帰確認：v1.9.0〜v1.20.0・v2.0.0の既存E2Eテスト13ファイル合計 1153/1153 PASS（`test_e2e_v1_10_0_analytics_foundation.py`はKnown Issues [KI-1]により対象外。本リリースの変更とは無関係であることを確認済み）

---

## [v2.0.0] - 2026-07-01 ★ AI Agent Foundation

### Added

- `src/ai/` に Agent基盤（8ファイル）を新規追加
  - `agent_task.py`: `AgentTask`（エージェントに判断を依頼する作業単位。`task_id` は自由記述）
  - `agent_decision.py`: `AgentDecision`（`should_act` / `reason` を持つ判断結果）
  - `agent_context.py`: `AgentContext`（実行時状態。`elapsed_time` は計算プロパティ）
  - `agent_result.py`: `AgentResult`（判断・実行結果。`workflow_result` は参照のみ保持しコピーしない）
  - `agent_config.py`: `AgentConfig`（`AI_AGENT_ENABLED` を読む。Configuration First）
  - `base_agent.py`: `BaseAgent`（ABC）。`decide()`（判断・副作用なし）と `act()`（実行）を分離
  - `agent_executor.py`: `AgentExecutor`。`decide()` → `should_act`かつ`dry_run=False`の場合のみ`act()`を呼ぶパイプライン
  - `agent_manager.py`: `AgentManager` / `NullAgentManager`（`AI_AGENT_ENABLED=false`時のダミー実装）
- `docs/design/agent_foundation.md` 新規作成（本リリースで追加、v2.1.0 Documentation Foundationにて作成）

### Note

- Agent は Workflow（`WorkflowRunner`）を置き換えるものではなく、「Workflowを今実行すべきか判断する」上位レイヤーとして設計されている
- v2.0.0時点では具体的な `BaseAgent` 実装は追加されていない。`AgentManager.from_config()` は `is_ready()=True` でも `executors=[]`（空リスト）を返す
- デフォルトは無効（`AI_AGENT_ENABLED=false`）。既存の `WorkflowRunner` 経由の自動実行フローに影響を与えない

### Tested

- `tests/test_e2e_v2_0_0_ai_agent_foundation.py`: 118/118 PASS

---

## [v1.20.0] - 2026-07-01 ★ AI Workflow Foundation

### Added

- `src/ai/` にWorkflow実行エンジン（7ファイル）を新規追加
  - `workflow_step.py`: `WorkflowStep` Enum（`improvement` / `improvement_review` / `rewrite` / `rewrite_review` / `publish` / `publish_review` の6ステップ）、`WorkflowStepResult`
  - `workflow_config.py`: `WorkflowConfig`（`AI_WORKFLOW_ENABLED` デフォルトtrue、`AI_WORKFLOW_CONTINUE_ON_ERROR`）
  - `workflow_context.py`: `WorkflowContext`
  - `workflow_step_executor.py`: 6ステップ分の `WorkflowStepExecutor` 実装（DIで各Serviceを注入）
  - `workflow_result.py`: `WorkflowResult`（`overall_success` / `total_processed` / `warnings` / `skipped_steps`）
  - `workflow_report_builder.py`: `WorkflowReportBuilder`
  - `workflow_runner.py`: `WorkflowRunner` / `NullWorkflowRunner`
- `scripts/run_ai_workflow.py` 新規作成
- `docs/design/ai_workflow_foundation.md` 新規作成（本リリースで追加）

### Note

- v1.14.0〜v1.19.0で個別に実装したImprovement→ImprovementReview→Rewrite→RewriteReview→Publish→PublishReviewの6ステップを、決まった順序で実行するオーケストレーターとして統合
- `WorkflowRunner` は各ステップのServiceを直接知らず、`WorkflowStepExecutor` 経由でDIする
- `AI_WORKFLOW_ENABLED=false` → `NullWorkflowRunner` を返す（Configuration First）

### Tested

- `tests/test_e2e_v1_20_0_ai_workflow_foundation.py`: 170/170 PASS

---

## [v1.19.0] - 2026-07-01 ★ AI Publish Review Foundation

### Added

- `src/ai/`: `ai_publish_review_result.py`（`PublishReviewStatus` Enum、`AiPublishReviewResult`）、`ai_publish_review_repository.py`、`ai_publish_review_report_builder.py`、`ai_publish_review_service.py`（`NullAiPublishReviewService`含む）
- `scripts/run_ai_publish_review.py` 新規作成

### Note

- Claude API・WordPress API（書き込み）は呼び出さない（読み取り・確認のみ、非破壊）
- 元記事・WordPress下書きの変更は行わない
- `NullAiPublishReviewService` は明示的な無効化時のみ使用（対象なしの場合は通常のServiceが「対象なし」レポートを生成する）
- 詳細設計書は見送り（v1.18.0 `ai_publish_foundation.md` の一部として今後扱う。必要度が上がった時点で個別設計書を追加）

### Tested

- `tests/test_e2e_v1_19_0_ai_publish_review_foundation.py`: 124/124 PASS

---

## [v1.18.0] - 2026-06-30 ★ AI Publish Foundation

### Added

- `src/ai/` にWordPress自動公開（6ファイル）を新規追加
  - `ai_publish_config.py`: `AiPublishConfig`（`AI_PUBLISH_ENABLED`、`WORDPRESS_URL`/`WORDPRESS_USERNAME`/`WORDPRESS_APP_PASSWORD`）
  - `ai_publish_result.py`: `AiPublishResult`（`wp_post_id` / `wp_edit_url` / `success` / `skipped` / `skip_reason`）
  - `wordpress_draft_client.py`: `WordPressDraftClient` / `NullWordPressDraftClient`
  - `ai_publish_repository.py`, `ai_publish_report_builder.py`, `ai_publish_service.py`（`NullAiPublishService`含む）
- `scripts/run_ai_publish.py` 新規作成
- `docs/design/ai_publish_foundation.md` 新規作成（本リリースで追加）

### Note

- v1.17.0で採用（adopted）されたリライト結果を重複チェックした上でWordPressへ投稿する
- 投稿は常に下書き（draft）のみ。publishは行わない（誤公開防止、v1.1.0以来の方針を踏襲）
- `AI_PUBLISH_ENABLED=false` または WordPress認証情報未設定 → `NullAiPublishService`

### Tested

- `tests/test_e2e_v1_18_0_ai_publish_foundation.py`: 109/109 PASS

---

## [v1.17.0] - 2026-06-30 ★ AI Rewrite Review Foundation

### Added

- `src/ai/`: `rewrite_review_result.py`（`ReviewStatus` Enum、`RewriteReviewResult`）、`rewrite_review_repository.py`、`rewrite_review_report_builder.py`、`rewrite_review_service.py`（`NullRewriteReviewService`含む）
- `scripts/run_ai_rewrite_review.py` 新規作成

### Note

- Claude APIを呼び出さない（リライト前後の差分サマリー生成のみ）
- `NullRewriteReviewService` は対象ファイルが存在しない・レビュー不要なケース用のno-op実装（Claude APIのON/OFFとは無関係）
- 詳細設計書は見送り（v1.16.0 `ai_rewrite_foundation.md` の一部として今後扱う）

### Tested

- `tests/test_e2e_v1_17_0_ai_rewrite_review_foundation.py`: 123/123 PASS

---

## [v1.16.0] - 2026-06-30 ★ AI Rewrite Foundation

### Added

- `src/ai/` にAIリライト機能（7ファイル）を新規追加
  - `rewrite_config.py`: `RewriteConfig`（`AI_REWRITE_ENABLED`、`AI_REWRITE_MODEL`、`AI_REWRITE_MAX_ARTICLES`等）
  - `rewrite_result.py`: `RewriteResult`（`rewrite_draft` / `improvement_summary` / `changes` / `success`）
  - `article_provider.py`: `ArticleProvider` / `WordPressArticleProvider` / `NullArticleProvider`
  - `rewrite_prompt_builder.py`, `rewrite_parser.py`, `rewrite_repository.py`, `rewrite_service.py`（`NullRewriteService`含む）
  - `prompts/v1_rewrite.py`
- `scripts/run_ai_rewrite.py` 新規作成
- `docs/design/ai_rewrite_foundation.md` 新規作成（本リリースで追加）

### Note

- v1.14.0の改善提案（`ImprovementSuggestion`）を受け取り、Claude APIで記事を実際に書き換える
- `AI_REWRITE_ENABLED=false` → `NullRewriteService`（Configuration First）
- 結果は `outputs/ai_rewrites/` にMarkdown＋JSONで保存（元記事は変更しない）

### Tested

- `tests/test_e2e_v1_16_0_ai_rewrite_foundation.py`: 81/81 PASS

---

## [v1.15.0] - 2026-06-30 ★ AI Improvement Review Foundation

### Added

- `src/ai/`: `improvement_report_builder.py`、`improvement_repository.py`、`improvement_review_service.py`
- `scripts/run_ai_improvement_report.py` 新規作成

### Note

- Claude APIを呼び出さない（`ImprovementRepository`が保存済みJSONを読み込み、Markdownレポート化するのみ）
- 詳細設計書は見送り（v1.14.0 `ai_improvement_foundation.md` の一部として今後扱う）

### Tested

- `tests/test_e2e_v1_15_0_ai_improvement_review_foundation.py`: 62/62 PASS

---

## [v1.14.0] - 2026-06-30 ★ AI Improvement Foundation

### Added

- `src/ai/` パッケージを新規作成（AI系機能全体の起点、8ファイル）
  - `claude_client.py`: `ClaudeClient` / `NullClaudeClient`
  - `ai_improvement_config.py`: `AiImprovementConfig`（`AI_IMPROVEMENT_ENABLED`、`AI_IMPROVEMENT_MODEL`、`AI_IMPROVEMENT_MAX_ARTICLES`等）
  - `improvement_suggestion.py`: `ImprovementSuggestion`（`priority` / `issues` / `suggestions` / `seo_title_suggestion`等）
  - `improvement_suggestion_parser.py`, `prompt_builder.py`, `ai_improvement_service.py`（`NullAiImprovementService`含む）
  - `prompts/v1_improvement.py`
- `scripts/run_ai_improvement.py` 新規作成（記事投稿フローとは独立したバッチ実行スクリプト）
- `docs/design/ai_improvement_foundation.md` 新規作成（本リリースで追加）

### Note

- v1.10.0で設計した `AiInputRecord`（Analytics Foundation）を入力とし、Claude APIで改善提案を生成する
- `main.py`（投稿処理）からは呼び出さない設計。SC/GA4データ取得後に別スクリプトとして実行する
- `AI_IMPROVEMENT_ENABLED=false`（デフォルト）→ `NullAiImprovementService`

### Tested

- `tests/test_e2e_v1_14_0_ai_improvement_foundation.py`: 74/74 PASS

---

## [v1.13.0] - 2026-06-30 ★ Google Analytics Foundation

### Added

- `src/analytics/`: `google_analytics_client.py`、`google_analytics_config.py`、`google_analytics_fetcher.py`
- `scripts/fetch_google_analytics_metrics.py` 新規作成
- `.env.example` に `GOOGLE_ANALYTICS_ENABLED` / `GA4_PROPERTY_ID` / `GA4_APPLICATION_CREDENTIALS` / `GA4_TIMEOUT_SECONDS` を追加

### Note

- GA4 APIエラーは `[GA4 WARNING]` プレフィックスで表示しゼロ値継続（Search Consoleの`[SC WARNING]`と区別）
- Google API への直接通信は `GoogleAnalyticsClient` の責務、変換・ゼロ値フォールバックは `GoogleAnalyticsFetcher` の責務に分離
- 詳細設計書は見送り（Search Console Foundationと同一パターンのため、必要になった時点で追加）

### Tested

- `tests/test_e2e_v1_13_0_google_analytics_foundation.py`: 70/70 PASS

---

## [v1.12.0] - 2026-06-30 ★ Search Console Foundation

### Added

- `src/analytics/`: `search_console_client.py`、`search_console_config.py`、`search_console_fetcher.py`
- `scripts/fetch_search_console_metrics.py` 新規作成
- `.env.example` に `SEARCH_CONSOLE_ENABLED` / `SEARCH_CONSOLE_PROPERTY` / `GOOGLE_APPLICATION_CREDENTIALS` / `SEARCH_CONSOLE_TIMEOUT` を追加
- `.gitignore` に `credentials/` を追加（Service Account鍵の除外）

### Note

- 投稿直後はSearch Consoleデータが存在しないため、`main.py`とは独立したバッチスクリプトとして設計
- 429（レート制限）・その他HTTPエラー・予期せぬ例外はすべてWARNING表示してゼロ値の`SearchConsoleMetrics`を返し、システム全体を停止させない
- 詳細設計書は見送り（必要になった時点で追加）

### Tested

- `tests/test_e2e_v1_12_0_search_console_foundation.py`: 47/47 PASS

---

## [v1.11.0] - 2026-06-30 ★ SaveResult Foundation

### Added

- `src/outputs/save_result.py` 新規作成（`SaveResult` dataclass）

### Changed

- `WordPressOutput.save()` / `MarkdownOutput.save()` の戻り値を文字列から `SaveResult` に変更
  - WordPress REST APIレスポンスの `"id"` フィールドから直接 `post_id` を取得する方式に変更（v1.8.0までの、`edit_url`文字列からの正規表現抽出という暫定実装を廃止）
- `OutputManager.save_all()` / `main.py` / `src/logger/log_manager.py` を `SaveResult` ベースの呼び出しに更新

### Note

- Single Source of Truthの原則：post_idはAPIレスポンスから直接取得し、他の文字列から推測しない
- 詳細設計書は見送り（内部データ構造の整理が中心のため）

### Tested

- `tests/test_e2e_v1_11_0_save_result.py`: 43/43 PASS

---

## [v1.10.0] - 2026-06-30 ★ Analytics Foundation

### Added

- `src/analytics/` パッケージ新規作成
  - `analytics_entry.py`: `AnalyticsEntry` / `ArticleAnalysisRecord` / `AiInputRecord` dataclass
  - `analytics_config.py`: `AnalyticsConfig`（`ANALYTICS_ENABLED`デフォルトfalse、`ANALYTICS_DIR`、`ANALYTICS_PERIOD_DAYS`）
  - `analytics_manager.py`: `AnalyticsManager`
- `docs/design/analytics_foundation.md` 新規作成（v1.10.0 設計書）
- `.env.example` に `ANALYTICS_ENABLED` / `ANALYTICS_DIR` / `ANALYTICS_PERIOD_DAYS` を追加

### Note

- v1.10.0時点では外部API連携（Search Console・Google Analytics）は行わない。将来のパフォーマンスデータ・AI改善提案の入力データ構造のみを設計
- Logging Foundation（`LOG_ENABLED`）と異なり、外部連携へ発展する基盤のため意図的にデフォルト無効（`ANALYTICS_ENABLED=false`）

### Tested

- `tests/test_e2e_v1_10_0_analytics_foundation.py` が実装時に追加されている。実装当時にPASSしていたことを裏付ける記録（設計書のチェック欄・実行ログ等）は見つからなかった
- 現在の環境で本テストを実行すると失敗する既知の問題がある。詳細は本ファイル冒頭の **Known Issues [KI-1]** を参照

---

## [v1.9.0] - 2026-06-30 ★ SNS Foundation

### Added

- `src/sns_config.py` 新規作成（`SnsConfig`：`BLOG_BASE_URL`解決、`SNS_ENABLED`、`SnsPostStatus` Enum）
- `docs/design/sns_foundation.md` 新規作成（v1.9.0 設計書）
- `.env.example` に `BLOG_BASE_URL` / `SNS_ENABLED` を追加

### Changed

- `src/logger/log_entry.py` / `log_manager.py`: SNS関連フィールド（`wp_public_url`、`x_post_status`）を追加
- `main.py`: X投稿文生成より先にslugを計算するよう処理順を変更（API呼び出し回数は変化なし）

### Note

- X API自動投稿は行わない。将来のX API連携・他SNS対応のための管理基盤のみを整備
- `BLOG_BASE_URL`未設定時は`WP_SITE_URL`にフォールバック、両方未設定なら`"[ブログURL]"`のプレースホルダーのまま

### Tested

- `tests/test_e2e_v1_9_0_sns_foundation.py`: 15/15 PASS

---

## [v1.8.0] - 2026-06-30 ★ Release 1.1 — Epic 2 Logging Foundation

### Added

- `src/logger/` パッケージ新規作成
  - `log_entry.py`: `ArticleLogEntry` / `ExecutionLogEntry` / `ErrorLogEntry` dataclass
  - `log_manager.py`: `LogManager` / `NullLogManager`
- `docs/design/logging_foundation.md` 新規作成（v1.8.0 設計書）
- `.env.example` に `LOG_ENABLED`（デフォルトtrue） / `LOG_DIR` を追加

### Changed

- `main.py`: 記事保存後・エラー発生時・全処理完了後にJSON Linesログを記録する処理を追加（`try/except`を新規追加）

### Note

- ログはJSON Lines形式で`logs/`配下に保存。`LOG_ENABLED=false`でv1.7.0以前と同じ動作（ログなし）
- 将来のCSVエクスポート・集計レポート・DB移行・AI改善提案の基盤として設計

### Tested

- 専用のE2Eテストファイルは作成されていない（設計書内の手動確認のみ。以降のバージョンから自動テストファイルが整備されている）

---

## [v1.7.0] - 2026-06-30  ★ Release 1.1 — Epic 1 Publishing Automation

### Added

- `src/publishing_config.py` 新規作成（Release 1.1 — Publishing Automation の中核モジュール）
  - `PublishStatus` Enum（`str` 継承）：`DRAFT` / `PENDING` / `FUTURE` / `PUBLISH` の4値
    - `FUTURE` / `PUBLISH` は将来実装用の予約定義
    - `str` 継承により `PublishStatus.DRAFT == "draft"` が True になり、ログ出力・JSON変換がそのまま使える
  - `PublishingConfig` dataclass：`status_s` / `status_a` フィールド
    - `from_env()`: `PUBLISH_STATUS_S` / `PUBLISH_STATUS_A` を環境変数から読み込む
    - `resolve_status(importance)`: 重要度 → `PublishStatus` を解決
    - Validation: 許可値外（`publish` / `future` / 任意の不正値）は `DRAFT` にフォールバック + WARNING出力
    - 将来拡張フィールドのコメント予約：`publish_time` / `timezone` / `review_required` / `priority`
- `docs/design/publishing_automation.md` 新規作成（v1.7.0 設計書）
- `ArticleData` に `publish_status: PublishStatus = PublishStatus.DRAFT` フィールドを追加（`base.py` 修正）

### Changed

- `src/outputs/wordpress_output.py`
  - `"status": "draft"`（ハードコード）を `"status": article.publish_status.value` に変更
  - コンソールログに `ステータス: <値>` を追加（投稿ID・slug・編集URLと並んで表示）
- `main.py`
  - `from publishing_config import PublishingConfig` をインポート追加
  - `publishing_config = PublishingConfig.from_env()` を起動時に1回呼び出す
  - 記事ループ内で `publish_status = publishing_config.resolve_status(importance)` を呼び出し `ArticleData` に設定
- `.env.example`
  - `PUBLISH_STATUS_S=draft` / `PUBLISH_STATUS_A=draft` を追加（使用可能な値・設定例付き）

### Note

- API呼び出し回数は増加なし（1記事あたり引き続き3回）
- 外部ライブラリ追加なし
- **Release 1.0 と完全後方互換**：`PUBLISH_STATUS_S/A` 未設定の場合は全記事 `draft` で動作（従来と同じ）

### Tested

- E2Eテスト①：`PUBLISH_STATUS_S=draft`（未設定・デフォルト）→ WordPress API で `status='draft'` 確認（post 10337）
- E2Eテスト②：`PUBLISH_STATUS_S=pending` → WordPress API で `status='pending'` 確認（post 10338）
- E2Eテスト③：`PUBLISH_STATUS_S=publish` / `PUBLISH_STATUS_A=abc`（不正値）→ WARNING 出力 + `status='draft'` でフォールバック確認（post 10339）

---

## [v1.6.0] - 2026-06-30

### Added

- `ArticleData` に `featured_media_id: int = 0` フィールドを追加（`base.py` 修正）
  - 0 の場合はアイキャッチなし（従来動作と同じ）
  - WordPress `featured_media` フィールドの値として使用
- `image_resolver.py` に `resolve_media_id(item, default_media_id)` 関数を追加
  - `image_terms_confirmed == False`（全RSS画像が未確認）の間は常に `default_media_id` を返す
  - 将来（v1.7.0）の権利確認済み画像アップロード対応のための拡張ポイント
- `main.py` に `DEFAULT_MEDIA_ID` の読み込みを追加（`os.getenv("DEFAULT_MEDIA_ID", "0")`）
  - `resolve_media_id(item, default_media_id)` を呼び出して `ArticleData.featured_media_id` に設定
- `.env.example` に `DEFAULT_MEDIA_ID` の設定例を追記（コメントアウト形式・設定方法の説明付き）
- `docs/blog_strategy.md` に画像利用ポリシーを追記（v1.6.0 確定版）
  - RSS画像・OGP画像のアップロード禁止ルールを明文化
  - デフォルト画像の WordPress 設定手順（Media ID 確認方法）

### Changed

- `wordpress_output.py` の payload に `featured_media` 条件付き追加
  - `article.featured_media_id > 0` の場合のみ `payload["featured_media"]` を設定
  - 0 の場合はキーごと省略（WordPress の既定値が優先される）

### Note

- API呼び出し回数は増加なし（1記事あたり引き続き3回）
- 外部ライブラリ追加なし
- `.env` の実ファイル変更不要（`DEFAULT_MEDIA_ID` 未設定の場合は 0 として動作）
- WordPress Media API（`/wp-json/wp/v2/media`）は使用しない（v1.7.0 以降の予定）

### Tested

- E2Eテスト成功（`python main.py --max-articles 1`、`DEFAULT_MEDIA_ID=0`）
  - featured_media が payload に含まれないことを確認（従来動作）
  - API呼び出し回数: 3回（変化なし）

---

## [v1.5.0] - 2026-06-30

### Added

- `slug_generator.py` 新規作成（`src/slug_generator.py`）
  - `generate_slug(seo_title: str, date_str: str) -> str`
  - ASCII英数字部分を抽出・小文字化・ケバブケース変換・最大30文字 + 日付付加
  - 英字が取れない場合は `article-YYYYMMDD` にフォールバック
  - 新規パッケージ追加なし・API呼び出しなし
- `ArticleData` に `slug: str = ""` フィールドを追加（`base.py` 修正）
- `main.py` で `generate_slug(seo_title, date_str)` を呼び出して `ArticleData.slug` を設定
- `main.py` に実行時間計測を追加（`time.time()` による計測、完了サマリーに `実行時間: XX.X秒` を表示）
- WordPress 投稿後の投稿 ID・slug・編集 URL をコンソールに表示（`wordpress_output.py` 修正）

### Changed

- `wordpress_output.py` の payload に `"slug": article.slug` を追加
- `markdown_output.py` の YAML front matter に `slug` フィールドを追記
- 完了サマリーの表示に実行時間を追加

### Note

- API呼び出し回数は増加なし（1記事あたり引き続き3回）
- 外部ライブラリ追加なし
- `.env` 変更不要

### Tested

- slug 生成の単体テスト（7ケース）：PS6/Switch混在・英字のみ・日本語のみ・記号のみ・長文・全英語
- E2Eテスト成功（`python main.py --max-articles 1`）

---

## [v1.4.0] - 2026-06-30

### Added

- `image_resolver.py` 新規作成（`src/image_resolver.py`）
  - `resolve_featured_image(item: NewsItem) -> str`：image_candidates の先頭URLを返す
  - 候補なしの場合は空文字を返す（例外を発生させない安全設計）
  - v1.5.0以降でデフォルト画像・権利確認済み画像・AI生成画像への拡張に対応可能
- `ArticleData` に `excerpt: str = ""` / `meta_description: str = ""` フィールドを追加（`base.py` 修正）
  - `excerpt`：WordPress抜粋・Markdown記録用
  - `meta_description`：将来のSEOプラグイン連携用（v1.4.0では excerpt と同値）
- `_extract_excerpt()` を `main.py` に追加
  - 記事本文の先頭段落からMarkdown記法（見出し・太字・斜体）を除去してルールベースで生成
  - 最大150字。句点（。）・読点（、）で自然に切れる位置を自動検出
  - APIを呼び出さない（API呼び出し回数は v1.3.0 と同じ1記事3回のまま）
- `WordPressOutput.save()` の payload に `"excerpt": article.excerpt` を追加
- `markdown_output.py` の YAML front matter に `excerpt` / `meta_description` を追記

### Changed

- `main.py` の `item.image_candidates[0] if item.image_candidates else ""` を `resolve_featured_image(item)` に差し替え（ImageResolver 経由に統一）

### Note

- API呼び出し回数は増加なし（1記事あたり引き続き3回）
- 著作権リスクは増加なし（画像のダウンロード・アップロードは行わない）
- `meta_description` は将来のSEOプラグイン（Rank Math等）連携の準備フィールド。v1.4.0では excerpt と同値を設定

### Tested

- E2Eテスト成功（`python main.py --max-articles 1`）
  - excerpt が Markdown YAML に記録されること
  - meta_description が excerpt と同値で記録されること
  - WordPress 下書きに excerpt フィールドが送信されること（post ID: 10331 で確認）
  - ImageResolver が candidates[0] を正しく返すこと
  - image_candidates が空でも空文字を返して正常終了すること

---

## [v1.3.0] - 2026-06-27

### Added

- `image_extractor.py` 新規作成（RSSエントリーから画像URLを抽出するモジュール）
  - `extract_image_url(entry) -> str`：media:thumbnail → enclosures → media:content の順に画像URLを探索
  - 取得できない場合は空文字を返す（例外を発生させない安全設計）
- `NewsItem.image_candidates` への画像URL格納（`collector.py` 修正）
- `ArticleData` に `featured_image_url: str = ""` フィールドを追加（`base.py` 修正）
- Markdownファイルの末尾に `<!-- アイキャッチ候補: URL -->` コメントを記録（`markdown_output.py` 修正）
- Markdownの `image_candidates` YAMLフィールドに実際の候補URLを出力

### Note

- 画像のWordPressアップロードは著作権リスクのため実装しない（v1.4.0 以降で検討）
- 取得した画像URLは候補として記録するのみ。利用前に著作権を確認すること

### Tested

- E2Eテスト成功（画像URLあり・なし両方のニュースで正常動作確認）

---

## [v1.2.0] - 2026-06-27

### Added

- `taxonomy_config.py` 新規作成（カテゴリ・タグIDの一元管理）
  - `GAME_NEWS_CATEGORY_ID`：「ゲームニュース」カテゴリIDの定数
  - `_TAG_ID_BY_IMPORTANCE`：重要度別タグIDの辞書（S→注目 / A→速報 / B→なし）
  - `resolve_taxonomy(importance)`：重要度からカテゴリID・タグIDを解決する関数
    - ID が 0（未設定）の場合は自動的にスキップ
- `WordPressOutput.save()` にカテゴリ・タグ設定を追加
  - `resolve_taxonomy()` を呼び出し、`categories` / `tags` をペイロードに追加
  - カテゴリ・タグが空リストの場合はペイロードから省略（WordPress標準に準拠）

### Tested

- カテゴリ・タグID設定済み環境でのE2Eテスト成功
  - RSS収集 → フィルター → 重複排除 → 重要度判定 → 記事生成 → Markdown保存 → WordPress下書き投稿（カテゴリ・タグ付き）の全工程を確認

---

## [v1.1.0] - 2026-06-26

### Added

- OutputManager アーキテクチャ導入（`src/outputs/` パッケージ新設）
  - `BaseOutput` 抽象クラス（`save()` / `is_available()` インターフェース）
  - `ArticleData` データクラス（記事生成結果をまとめて出力処理へ渡す）
  - `OutputManager.save_all()`: 全出力先に一括保存、1つ失敗しても他を続行
- `MarkdownOutput` クラス: v1.0 の `_save_as_markdown()` をクラスとして分離
- `WordPressOutput` クラス: WordPress REST API による下書き投稿対応
  - Application Password 認証
  - 投稿状態は `draft` 固定（誤公開防止）
  - `.env` 未設定時は `is_available()` が `False` を返し自動スキップ
  - エンドポイント: `/wp-json/wp/v2/posts`
- `.env.example` に WordPress設定項目を追加（`WP_SITE_URL` / `WP_USERNAME` / `WP_APP_PASSWORD`）

### Fixed

- `importance_judge.py` のプロンプト展開を `.format()` から `.replace()` に変更
  - `prompts/importance_prompt.md` のJSON例に含まれる `{}` を `str.format()` がプレースホルダーと誤認識する問題を修正

### Tested

- 実際のゲームニュース1件でE2Eテスト成功
  - RSS収集 → キーワードフィルター → 重複排除 → Claude重要度判定 → 記事生成 → Markdown保存 → WordPress下書き投稿の全工程を確認

---

## [v1.0] - 2026-06-26

### Added

- Steam News フィード追加（`https://store.steampowered.com/feeds/news/?l=japanese`）
  - 「公式」カテゴリに追加（PlayStation公式・Nintendo公式・Xbox公式・Steam）
  - 合計16サイトからのRSS収集に対応
- RSS取得サマリー表示（カテゴリ別の取得件数・成否を一覧表示）
  - `FeedStats` データクラスによる取得結果の構造化
  - `FEED_GROUPS` によるカテゴリ別グルーピング
  - 取得合計・フィルター通過・重複除去後・記事生成の件数を末尾に表示

---

## [v0.9] - 2026-06-26

### Added

- RSSニュース取得（15サイト対応）
  - 日本語：4Gamer、Game\*Spark
  - 公式：PlayStation公式、Nintendo公式、Xbox公式
  - 総合英語：IGN、GameSpot、Eurogamer、Gematsu、VGC、Insider Gaming、PC Gamer
  - プラットフォーム特化：Nintendo Life、Push Square、Pure Xbox
- キーワードフィルター（API節約のための事前スクリーニング）
- Claude APIによる重要度判定（S / A / B / なし）
- 日本語記事下書き生成
- SEOタイトル生成
- X（旧Twitter）投稿文生成
- Markdownファイル保存（output/ フォルダ）
- 重複ニュース排除（`duplicate_filter.py`、URLの正規化付き）

### Fixed

- JSON抽出処理を正規表現ベースに変更し、APIレスポンス形式の変化に対応
- Windows環境でのUTF-8文字コード問題を修正（起動時にstdout/stderrを設定）
