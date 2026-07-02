# Project Charter — Release 2.9「Workflow Monitor Foundation」

作成日：2026-07-02
状態：ドラフト（Claude Code作成、レビュー反映済み。Timeout方針・CLI採否・Design Principlesを確定）
対象：Execution History（v2.8.0）を読み取り、Workflow実行状態を監視・判定する新しい基盤

---

## 1. Goal

Execution History（v2.8.0、`src/execution_history/`）が記録した`WorkflowExecutionRecord`を読み取り、Workflowの実行状態を**判定するだけ**の最小基盤を、新規パッケージ`src/workflow_monitor/`として追加する。

```
Scheduler        （判断、v2.6.0、無改修）
   ↓ SchedulerEvent
Workflow Engine    （実行、v2.7.0、無改修）─────観測─────→ Execution History（記録、v2.8.0、無改修）
   ↓                                                              ↓
NewsAgent → ReviewTriggerAgent → PublishTriggerAgent      logs/execution_history/*.json
                                                                   ↓ 読み取り専用
                                                            Workflow Monitor（状態判定、新規）
```

Workflow Monitorは、Execution Historyが保存した記録を**読み取り、加工して状態を判定するだけ**の層であり、Workflow Engine・Execution Historyいずれの実行・記録処理にも関与しない。将来のRetry Engine・Metrics Foundation・Dashboard Foundationが「今どのWorkflowが失敗しているか／滞留しているか」を判断するための前提基盤として位置づける。

---

## 2. 背景

Release 2.x では、以下の基盤が順次整備された。

* Scheduler Agent Foundation（v2.6.0）：実行すべきタイミングを判定するだけ（`SchedulerEvent`を生成、実行はしない）
* Workflow Engine Foundation（v2.7.0）：`SchedulerEvent`を起点にNews→Review→Publishを順序実行するオーケストレーション層
* Execution History Foundation（v2.8.0）：Workflow Engineが実行した各Workflowの開始・終了・各Stepの結果を`WorkflowExecutionRecord`として観測・記録する層（記録専用、`ExecutionHistoryStore.list_all()` / `get(run_id)`で読み取り可能）

v2.8.0の設計書（`docs/design/execution_history_foundation.md` 12章 Future Extensions）には、次の段階として以下が明記されている。

> Workflow Monitor：`ExecutionHistoryStore.list_all()`を使った実行状況の可視化（一覧・検索）

現時点では、保存された`WorkflowExecutionRecord`を「人間が`scripts/show_execution_history.py`で個別に閲覧する」ことはできるが、「このWorkflowは正常に進行しているか、それとも異常（タイムアウト・想定外の中断）なのか」を体系的に判定する仕組みは存在しない。`WorkflowExecutionRecord.status`は`RUNNING` / `SUCCESS` / `FAILED`の3値のみであり、「`RUNNING`のまま長時間放置されている（プロセス異常終了の可能性）」を検知する手段がない（v2.8.0設計書 9章 Error Handlingで明記済みの既知の制約）。

Workflow Monitorは、この「記録はあるが状態を判定する層がない」というギャップを埋める。

---

## 3. Scope

### 実装対象（想定、Architecture Designで確定）

* `WorkflowMonitorStatus`：Workflowの監視上の状態を表すEnum（4章の状態候補）
* `WorkflowMonitorRecord`：1 Workflowの監視結果（`run_id` / 判定された`WorkflowMonitorStatus` / 判定根拠等）を保持するデータクラス
* `WorkflowMonitorConfig`：Monitorの設定値（有効化ゲート・Timeout判定の閾値等。5章参照）
* `WorkflowMonitor`（または`WorkflowMonitorEngine`）：`ExecutionHistoryStore`から`WorkflowExecutionRecord`を読み取り、`WorkflowMonitorStatus`を判定するロジック本体
* `WorkflowMonitorManager` / `NullWorkflowMonitorManager`：既存Manager群（`AgentManager` / `WorkflowEngineManager` / `ExecutionHistoryManager`）と同型の起動口・ゲート制御
* `scripts/show_workflow_status.py`：Workflow監視状態を表示する読み取り専用CLI（**採用確定**。Release 2.7の`run_workflow_engine.py`・Release 2.8の`show_execution_history.py`との一貫性を保つため、Release 2.9のDeliverablesに含める。詳細仕様はArchitecture Designで確定）
* 単体テスト・E2Eテスト
* 関連ドキュメント更新（CHANGELOG / ROADMAP / architecture.md）

### 対象外（今回のRelease 2.9では扱わない）

* Retry Engine（失敗Workflowの自動再実行）
* Auto Retry
* Metrics Foundation（実行時間集計・成功率等の統計処理）
* Dashboard Foundation（Web UI）
* Notification / Alert（Slack / Discord / LINE等への通知）
* SLA判定（応答時間・稼働率等の目標値管理）
* Distributed Monitor（複数プロセス・複数ホストにまたがる監視）
* Parallel Workflow Management（並列Workflow実行の管理）
* Execution History本体（`src/execution_history/`）の改修
* Workflow Engine本体（`src/workflow_engine/`）の改修・挙動変更
* Execution Historyへの書き込み（Workflow Monitorは読み取り専用）

これらは後続Releaseの対象、またはそもそもFoundation Releaseの範囲外とする。

---

## 4. 状態候補（判定対象）

| 状態 | 判定方針（案、Architecture Designで確定） | 今回の扱い |
|---|---|---|
| `RUNNING` | `WorkflowExecutionRecord.status == RUNNING`かつTimeout未経過 | 判定対象 |
| `SUCCESS` | `WorkflowExecutionRecord.status == SUCCESS` | 判定対象 |
| `FAILED` | `WorkflowExecutionRecord.status == FAILED` | 判定対象 |
| `TIMEOUT` | `status == RUNNING`のまま、`started_at`から`WorkflowMonitorConfig`の閾値以上経過（プロセス異常終了の疑い、v2.8.0設計書9章で既知の制約として記録済み）。判定方針は5章、閾値の具体値はArchitecture Designで確定 | 判定対象 |
| `CANCELLED` | 現時点でWorkflow Engine・Execution Historyのいずれにも「キャンセル」を表す状態・操作が存在しない | **実行判定対象外**。Enumには含めるが、判定ロジックは持たない（正式な判定方法はOpen Question） |
| `WAITING` | 実行待ちキューが現時点で存在しない（Scheduler・Workflow Engineいずれも「即時実行 or 実行しない」の二択で、キュー待ち状態を持たない） | **実行判定対象外**。Enumには含めるが、将来拡張用の予約値とする（導入タイミングはOpen Question） |

---

## 5. Design Principles

### 5.1 Single Source of Truth

Workflow Monitorは、**Execution Historyを唯一の情報源（Single Source of Truth）として状態を判定する。**

* Workflow Engineの内部状態・メモリ上の状態・一時キャッシュなど、Execution History以外の情報源には一切依存しない
* すべての状態判定は、`ExecutionHistoryStore`から読み取った`WorkflowExecutionRecord` / `StepExecutionRecord`から導出する
* Workflow Monitor自身は判定結果を独自に永続化・キャッシュしない（3章Non Goal「stateless」の裏付け）。呼び出されるたびにExecution Historyを読み直し、その場で判定する

この原則により、Workflow Monitorの判定結果は常にExecution Historyの記録内容と一致することが保証される（判定ロジックとデータソースが分離した場合に起きがちな「Monitor側の情報が古い」という不整合を構造的に防ぐ）。

### 5.2 Timeoutの判定方針

* **Workflow Monitor自身はTimeoutの閾値を保持しない。** 閾値は`WorkflowMonitorConfig`に定義された設定値として外部化する
* Timeout判定ロジック（`started_at`からの経過時間と閾値を比較する処理）はWorkflow Monitor内に置くが、「何分でTimeoutとみなすか」という具体的な数値はConfigの責務とし、判定ロジックとハードコードしない
* 実際のデフォルト値（例：3600秒等）はArchitecture Designで決定する
* この設定駆動の構造により、将来のRetry Engine・Metrics Foundation・Dashboard Foundationが同じ`WorkflowMonitorConfig`の閾値を参照でき、「Monitorでは3600秒、Retry Engineでは別の値」といった値の二重管理・不整合を防ぐ

---

## 6. Non Goal

* Workflow Engineの実行制御ロジック（Gate二層構造・打ち切り基準）を変更しない（`docs/design/workflow_engine_foundation.md` 8章の設計はそのまま維持）
* Execution Historyへの書き込み・更新は一切行わない（Workflow Monitorは`ExecutionHistoryStore`の`save()`を呼ばない。読み取り専用）
* Workflow Monitorが判定した結果をもとに自動的に何かを実行する（Retry・通知等）仕組みは持たない。判定するだけで、その先の対応は行わない
* Monitorはstateless（状態を独自に保持・永続化しない）。呼び出されるたびに`ExecutionHistoryStore`から最新のレコードを読み直し、その場で判定する（5.1節 Single Source of Truthの直接的な帰結）

---

## 7. 成功条件（Architecture Design以降で検証）

* Workflow Monitorは`ExecutionHistoryStore`（v2.8.0、無改修）のみを読み取り専用で使用し、`src/workflow_engine/` / `src/ai/` / `src/pipeline/` / `src/scheduler/`をimportしない（Execution Historyが確立した一方向依存パターンを踏襲）
* Execution History・Workflow Engine・既存4 Trigger Agent・Scheduler本体・`main.py`が無改修であること
* `RUNNING` / `SUCCESS` / `FAILED` / `TIMEOUT`の4状態が、保存済み`WorkflowExecutionRecord`から正しく判定できること
* Timeoutの閾値が`WorkflowMonitorConfig`から取得され、Workflow Monitor本体にハードコードされていないこと
* `CANCELLED` / `WAITING`はEnumに定義されるが、判定ロジックには組み込まれない（実行時に到達しないことをテストで確認）
* Monitor自体が状態を書き換えない（`ExecutionHistoryStore.save()`を一切呼ばないことをArchitecture Guardで静的検査）
* `scripts/show_workflow_status.py`が、保存済み履歴から判定結果（`WorkflowMonitorStatus`）を表示できること
* E2Eテスト全PASS・既存回帰（v2.0.0〜v2.8.0・v1.20.0）全PASS

---

## 8. Open Questions（Architecture Designフェーズで決定）

1. **判定の粒度**：`WorkflowExecutionRecord`単位（Workflow全体で1状態）のみを判定するか、`steps`単位の状態も集約・保持するか
2. **`CANCELLED`の正式な判定方法**：現時点でWorkflow Engine・Execution Historyのいずれにも「キャンセル」を表す状態・操作が存在しないため、Enumには含めるが判定ロジックを持たない（4章）。将来Workflow Engine側にキャンセル機構が追加された場合、どのような判定方法（記録の追加項目・別の仕組み等）を採るか
3. **`WAITING`の導入タイミング**：現時点で実行待ちキューが存在しないため判定対象外とするが、将来Schedulerにキュー機構が追加された場合、どの時点で`WAITING`判定を導入するか
4. **命名衝突の確認**：既存の`WorkflowEngine`接頭辞（v2.7.0）・`ExecutionHistory`接頭辞（v2.8.0）にならい、`WorkflowMonitor`接頭辞で統一する想定だが、`src/ai/`の既存クラスとの衝突がないことを改めて確認する
5. **Feature Gateの初期設定（有効／無効）**：Monitorは読み取り専用で外部への副作用を持たないため、Execution Historyと同じ「デフォルト有効」とするか、Agent系ゲートと同じ「デフォルト無効」とするか

---

## 9. 想定ディレクトリ構成（暫定、Architecture Designで確定）

```text
src/workflow_monitor/
├── __init__.py
├── workflow_monitor_config.py
├── workflow_monitor_status.py
├── workflow_monitor_record.py
├── workflow_monitor.py
└── workflow_monitor_manager.py

scripts/
└── show_workflow_status.py

tests/
└── test_e2e_v2_9_0_workflow_monitor_foundation.py
```

---

## 10. リスクとリスク対策

| リスク | 対策 |
|---|---|
| Workflow Monitorの判定ロジックが、Workflow Engineの打ち切り基準（`REASON_NOT_REACHED`等）と矛盾する解釈をしてしまう | Workflow Monitorは`WorkflowExecutionRecord.status`・`StepExecutionRecord.status`をそのまま参照するのみとし、独自の実行成否判定ロジックは持たない（Execution Historyが確定した値を信頼する。5.1節） |
| Timeoutの閾値をWorkflow Monitor本体にハードコードしてしまい、将来Retry Engine等との値の不整合が生じる | 閾値は`WorkflowMonitorConfig`に一元化し、Monitor本体は保持しない（5.2節）。Architecture Guardで判定ロジック内にリテラルな時間値が埋め込まれていないことを確認する |
| `src/workflow_monitor/`が誤って`src/workflow_engine/`等を直接importしてしまい、一方向依存が崩れる | Execution Historyと同じくArchitecture Guard（静的検査）でimport制約をテスト化する |
| 読み取り専用のはずが、誤って`ExecutionHistoryStore.save()`を呼び出してしまう | 単体テストで「Monitor実行後もJSON履歴ファイルのmtimeが変化しない」ことを確認する |

---

## 11. Status

- [x] Project Charter ドラフト作成
- [x] Project Charter 修正（Timeout方針の確定・CLI採用確定・Design Principles追加）
- [x] Architecture Design（`docs/design/workflow_monitor_foundation.md`、Open Questions 5件のうち3件を確定）
- [x] Architecture Review（指摘事項3点を反映済み）
- [ ] 実装開始（ユーザー確認待ち）
