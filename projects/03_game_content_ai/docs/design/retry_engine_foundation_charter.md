# Project Charter — Release 3.0「Retry Engine Foundation」

作成日：2026-07-02
状態：承認済み（Architecture Review完了・**Approve with Minor Recommendations**、2026-07-02）
対象：Workflow Monitor（v2.9.0）が `FAILED` / `TIMEOUT` と判定したWorkflowを、Workflow Engine
の公開APIを通じて再実行する新しい基盤

> 本Charterは `docs/design/retry_engine_foundation.md`（Architecture Design）と対をなす。
> 両ドキュメントの間に矛盾がないことを確認済み（Architecture Review、2026-07-02）。

---

## 1. Background

Release 2.x では、以下の基盤が順次整備された。

* Scheduler Agent Foundation（v2.6.0）：実行すべきタイミングを判定するだけ（`SchedulerEvent`
  を生成、実行はしない）
* Workflow Engine Foundation（v2.7.0）：`SchedulerEvent`を起点にNews→Review→Publishを順序
  実行するオーケストレーション層
* Execution History Foundation（v2.8.0）：Workflow Engineが実行した各Workflowの開始・終了・
  各Stepの結果を`WorkflowExecutionRecord`として観測・記録する層（記録専用）
* Workflow Monitor Foundation（v2.9.0）：Execution Historyを唯一の情報源（Single Source of
  Truth）とし、`RUNNING` / `SUCCESS` / `FAILED` / `TIMEOUT` の4状態を**判定するだけ**
  （Read Only・Stateless）で、実行・記録処理には一切関与しない層

v2.9.0の設計書（`docs/design/workflow_monitor_foundation.md` 12章 Future Extensions）には、
次の段階として以下が明記されている。

> Retry Engine：`WorkflowMonitorStatus.FAILED` / `TIMEOUT`のRecordを起点に再実行を判断する
> 仕組み。Workflow Monitor自体は再実行の判断・実行を行わない（Charter 6章 Non Goal）ため、
> 別パッケージとして追加する想定

現時点では、Workflow Monitorが「このWorkflowは失敗している／タイムアウトしている」と判定
できても、それを検知して自動的に再実行する仕組みは存在しない。運用者が
`scripts/run_workflow_engine.py --job-id ...` を手動で再実行する以外に手段がなく、
`docs/ROADMAP.md`の長期ビジョン「半自律的なブログ運営支援（人間の承認ゲート付き）」の
実現には、この最後のギャップ（検知はできるが対応できない）を埋める一歩が必要である。

---

## 2. Purpose

Workflow Monitor（v2.9.0）が確立した「状態を判定するだけの層」の先に、「判定結果に基づいて
最小限の対応を取る層」を追加する。これにより、Workflowの失敗・タイムアウトに対して、人手を
介さず基本的な再実行を試みられるようにし、運用負荷を下げる。

ただし本Releaseは **Foundation** であり、高度な再試行戦略（バックオフ・優先度付け・AIによる
判断等）は目的としない。「Workflow Monitorの判定結果を読み、Workflow Engineの公開APIで
再実行を依頼する」という最小限の配線を、Release 2.6〜2.9と同じ設計思想（Foundation First・
Single Responsibility・一方向依存・既存モジュール無改修）で確立することを目的とする。

---

## 3. Goals

本Releaseで確立する Retry Engine Foundation は、次のことだけを行う。

1. 指定された `run_id` の現在の状態を、**Workflow Monitor の公開API
   （`WorkflowMonitorManager.get_status()`）を通じて** 読み取る（Execution History は
   直接解釈しない）
2. その状態が Retry Policy の再実行対象（`FAILED` / `TIMEOUT`）に該当し、かつ再試行回数が
   上限内であれば、**Workflow Engine の公開API（`WorkflowEngineManager.run()`）を通じて**
   再実行を依頼する（`WorkflowEngineExecutor` 等の内部実装には一切触れない）
3. 再実行の結果を、呼び出し元が判別可能な形（実行した／スキップした／見つからなかった／
   無効化されている）で返す

---

## 4. Scope

### 実装対象

新規パッケージ `src/retry_engine/` として、以下6コンポーネントを実装する。

* **Retry Policy**：再実行対象の状態（`FAILED` / `TIMEOUT`）と最大試行回数を保持し、
  再実行してよいか判定する、envに依存しない業務ルール
* **Retry Config**：Retry Engine全体のFeature Gate（`RETRY_ENGINE_ENABLED`、デフォルト
  `false`）
* **Retry Request**：1回の再実行依頼を表す入力データ（`run_id` / `attempt` /
  `requested_at` / `dry_run` / `reason`）
* **Retry Result**：1回の再実行試行の結果を表す出力データ（`RetryOutcome`：
  `RETRIED` / `SKIPPED` / `NOT_FOUND` / `DISABLED`）
* **Retry Executor**：`WorkflowEngineManager` の公開APIを呼び出すだけの薄いコンポーネント
  （Architecture Review反映。5章 Responsibilities参照）
* **Retry Manager**：Retry Engine全体の起動口。Feature Gate判定・Workflow Monitorからの
  状態取得（Read Before Retry）・Retry Policyの適用・Retry Requestの生成・Retry Executor
  への委譲を担う

および、単体テスト・E2Eテスト（`tests/test_e2e_v3_0_0_retry_engine_foundation.py`）。

### 対象外

以下は本Releaseの対象外とする。いずれも後続Release、またはそもそもFoundation Releaseの
範囲外とする（詳細は`docs/design/retry_engine_foundation.md` 11章 Future Extensions）。

* Exponential Backoff
* Retry Queue / Priority Queue
* Notification（Slack / Discord / LINE等）
* Metrics / Retry Analytics
* Dashboard
* Retry History（過去の再試行回数・結果の永続化）
* Failure Classification（失敗原因の分類に基づく判定の高度化）
* RetryReason（Retry判定理由のEnum化。現状は自由記述の`reason: str | None`のまま）
* RetryDecision（Retry可否判定の専用コンポーネントへの分離）
* AI Retry Decision（Claude APIによる再試行要否・タイミングの判断）
* Parallel Retry / Distributed Retry
* Circuit Breaker
* Dead Letter Queue
* Manual Retry UI
* CLIエントリスクリプト（`scripts/run_retry_engine.py`等）：Release 2.7〜2.9はいずれも
  CLIを実装対象に含めていたが、本Releaseの実装対象は上記6コンポーネントに限定し、CLIの
  追加は見送る（Manual Retry UIと隣接する領域であり、スコープを厳密に保つため）
* Scheduler連携（定期的な自動スイープ）
* Workflow Engine / Workflow Monitor / Execution History / Scheduler / 既存4 Trigger Agent
  本体の改修

---

## 5. Design Principles

* **Single Responsibility**：各コンポーネントは1つの責務のみを持つ（Policy＝再実行対象の
  判定基準、Config＝Feature Gate、Request/Result＝データ、Executor＝APIの呼び出し、
  Manager＝起動口・DI・ゲート判定・Policy適用）
* **Foundation First**：高度な再試行戦略（バックオフ・優先度・AI判断等）より先に、最小限の
  「判定→依頼」の配線を確立する。4章 対象外リストのとおり、拡張機能はすべて後続Releaseへ
  送る
* **Stateless**：Retry Engineは Workflow の状態も、再試行回数の履歴も自らは保持・永続化
  しない。状態は毎回 Workflow Monitor に問い合わせ、再試行回数（`attempt`）は呼び出し元が
  指定する
* **Read Before Retry**：再実行するかどうかの判定は、必ず直前に取得した最新の
  `WorkflowMonitorRecord`に基づいて行う。事前に取得した（古いかもしれない）状態を使い回さ
  ない。`RetryManager.retry(run_id)`が`run_id`のみを受け取り、内部で都度
  `WorkflowMonitorManager.get_status(run_id)`を呼ぶ構造でこれを強制する
* **Single Source of Truth**：Workflowの状態そのものはExecution Historyが唯一の情報源で
  あり、Retry EngineはそれをWorkflow Monitor経由でしか参照しない。Retry Engine自身が
  「今どのWorkflowが失敗しているか」を独自に記録・キャッシュすることはない
* **既存モジュールの責務を変更しない**：`workflow_engine` / `workflow_monitor` /
  `execution_history` / `ai` / `pipeline` / `scheduler` のいずれも無改修とする
* **後方互換性を維持する**：既存の公開API（`WorkflowEngineManager.run()` /
  `WorkflowMonitorManager.get_status()` 等）のシグネチャ・戻り値の意味を一切変更しない

---

## 6. Responsibilities

| コンポーネント | 責務 |
|---|---|
| Retry Policy | 「どの状態が再実行対象か」「最大何回まで再実行するか」という業務ルールを保持し、判定する |
| Retry Config | Retry Engine全体のFeature Gate（`RETRY_ENGINE_ENABLED`）のみを保持する |
| Retry Request | 1回の再実行試行に必要な入力を保持する不変データ |
| Retry Result | 1回の再実行試行の結果を保持する不変データ |
| Retry Executor | Retry Requestを`WorkflowEngineEvent`に変換し、`WorkflowEngineManager.run()`を呼び出すだけの薄いコンポーネント。Retry可否判定は行わない（Architecture Review反映） |
| Retry Manager | Feature Gate判定、Workflow Monitorからの状態取得（Read Before Retry）、Retry Policyの適用（可否判定）、Retry Requestの生成、Retry Executorへの委譲を行う起動口 |

Retry可否判定・Retry Requestの生成が Retry Manager に一本化され、Retry Executor は
「WorkflowEngineManagerの公開APIを呼び出すだけ」という薄い責務に限定される点は、
Architecture Review（2026-07-02）で明確化された（詳細は Architecture Design 5章・10章）。

---

## 7. Dependencies

```
retry_engine ──→ workflow_engine（公開APIのみ：WorkflowEngineManager / WorkflowEngineEvent /
                  WorkflowEngineResult / SOURCE_MANUAL）
      │
      └────────→ workflow_monitor（公開APIのみ：WorkflowMonitorManager / WorkflowMonitorRecord /
                  WorkflowMonitorStatus）
```

* `retry_engine` は `execution_history` / `ai` / `pipeline` / `scheduler` を**一切
  importしない**。`WorkflowEngineManager`の構築に必要なこれらへの依存は`workflow_engine`
  パッケージの内部に閉じたままとする（呼び出し元が構築済みの`WorkflowEngineManager` /
  `WorkflowMonitorManager`をDependency Injectionで`RetryManager`へ渡す設計とする。
  Architecture Design 10章 Design Decision #3）
* `workflow_engine` ・`workflow_monitor` のいずれも `retry_engine` の存在を一切知らない
  （両パッケージとも無改修）
* 循環importは存在しない（Architecture Design 7章 Dependency Diagram）

---

## 8. Non-Goals

* Workflowの状態を自ら保持・キャッシュしない（判定は毎回Workflow Monitorに問い合わせる）
* Execution Historyのレコード構造・JSONファイルを直接読み書きしない
* `WorkflowEngineExecutor`・ステップ単位の実行制御・Gate判定には一切関与しない
* 再試行のスケジューリング・キューイング・優先度付けは行わない
* 失敗の原因分類・バックオフ・通知・メトリクス集計・再試行履歴の永続化は行わない
* 複数`run_id`を一括で走査・選別する機能は持たない（Retry Queueと責務が重なるため。
  走査は呼び出し元が`WorkflowMonitorManager.list_status()`を直接使って行う）
* 再試行回数（`attempt`）を自ら記憶・逆算しない（呼び出し元が指定する）

---

## 9. Acceptance Criteria

* `RetryManager.retry(run_id)`が、`WorkflowMonitorStatus.FAILED` / `TIMEOUT`の`run_id`に
  対してのみ実際に再実行し、それ以外（`SUCCESS` / `RUNNING`）では再実行しないこと
* `attempt >= max_attempts`の場合に再実行しないこと（無限リトライの防止）
* `RETRY_ENGINE_ENABLED=false`（デフォルト）の場合、`NullRetryManager`が返り、いかなる
  `run_id`に対しても実際の再実行が発生しないこと
* `RetryManager` / `RetryExecutor`が`src/execution_history/`のJSONファイルを直接読み書き
  していないこと（Workflow Monitor経由のみで状態を取得していること）
* `RetryManager` / `RetryExecutor`が`WorkflowEngineExecutor`を直接importまたは構築して
  いないこと（`WorkflowEngineManager.run()`のみを呼び出していること）
* `RetryExecutor`が`RetryPolicy`型を一切参照・保持していないこと（Retry可否判定が
  `RetryManager`に一本化されていることの構造的確認）
* 再実行後、新しい実行がExecution History / Workflow Monitorから通常のWorkflow実行と
  同様に観測できること（Retry Engine専用の記録経路を持たないことの確認）
* `src/workflow_engine/` / `src/workflow_monitor/` / `src/execution_history/`配下の
  既存ファイルに変更がないこと（`git diff`で確認。本Releaseはゼロ改修）
* E2Eテスト全PASS・既存回帰（`v2.0.0`〜`v2.9.0`・`v1.20.0`）全PASS

---

## 10. Directory Structure（想定）

```text
src/retry_engine/
├── __init__.py
├── retry_policy.py
├── retry_config.py
├── retry_request.py
├── retry_result.py
├── retry_executor.py
└── retry_manager.py

tests/
└── test_e2e_v3_0_0_retry_engine_foundation.py
```

---

## 11. Risks and Mitigations

| リスク | 対策 |
|---|---|
| `RETRY_ENGINE_ENABLED`の設定ミスにより、意図せず実際の再実行（News収集・WordPress下書き投稿等）が発生する | デフォルトを`false`とし、`AI_AGENT_ENABLED` × `WORKFLOW_ENGINE_ENABLED` × `RETRY_ENGINE_ENABLED`の三重ゲートとする（Architecture Design 10章 Design Decision #2） |
| `max_attempts`の管理漏れにより無限リトライが発生する | `RetryPolicy.should_retry()`が`attempt >= max_attempts`を必ずチェックする。ただし`attempt`自体の永続化はRetry History（対象外）に委ねるため、呼び出し元が`attempt`を正しく増分しない運用ミスは本Foundationの範囲では防げない（Acceptance Criteriaと合わせてテストで確認する範囲を明確化する） |
| `retry_engine`が誤って`execution_history` / `ai` / `pipeline`を直接importしてしまい、一方向依存が崩れる | Architecture Guard（静的検査）でimport制約をテスト化する（Architecture Design 12章） |
| Retry Executorに可否判定ロジックが残存し、Retry Managerとの責務境界が曖昧になる | Architecture Reviewで明確化した設計（Executorはpolicy引数を持たない）を単体テストで型レベル・振る舞いレベルの両方から確認する（Architecture Design 10章 Design Decision #10、12章） |
| 元の`run_id`と再実行後の`run_id`が紐付けられず、追跡が難しい | 本Foundationでは`RetryResult.workflow_engine_result`に実行結果全体を同期的に埋め込むことで実用上の支障を避ける。恒久対応（`WorkflowEngineResult`への`run_id`追加）はRetry History実装時に再検討する（Architecture Design 10章 Design Decision #5） |

---

## 12. Status

- [x] Project Charter ドラフト作成（Architecture Designの内容から逆算して作成）
- [x] Architecture Design（`docs/design/retry_engine_foundation.md`）
- [x] Architecture Review（Approve with Minor Recommendations、指摘事項4点を反映済み）
- [x] Project Charter 確定（本ドキュメント。Architecture Designとの整合を確認済み）
- [ ] 実装開始（ユーザー確認待ち）
