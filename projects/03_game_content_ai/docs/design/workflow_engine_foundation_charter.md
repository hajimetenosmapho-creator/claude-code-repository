# Project Charter — Release 2.7「Workflow Engine Foundation」

作成日：2026-07-02
状態：ドラフト（Claude Code作成、ChatGPTレビュー前）
対象：Scheduler（v2.6.0）と既存4Agentを接続する新しいオーケストレーション層

---

## 1. Goal

Scheduler（v2.6.0）が生成する`SchedulerEvent`を起点に、既存の3つのTrigger Agent（News Agent v2.2.0 → Review Trigger Agent v2.5.0 → Publish Trigger Agent v2.4.0）を決まった順序で実行する**Workflow Engine**を新設する。

```
Scheduler          （判断：今このJobを実行すべきか）
   ↓
Workflow Engine     （実行：登録されたステップを順序どおりに実行する）
   ↓
News Agent          （既存、v2.2.0）
   ↓
Review Trigger      （既存、v2.5.0）
   ↓
Publish Trigger     （既存、v2.4.0）
```

Workflow Engineは、`WorkflowDefinition` / `WorkflowContext` / `WorkflowExecutor` / `WorkflowManager` / `WorkflowStep` / `WorkflowResult` / `WorkflowEvent` を中心に構成し、将来の条件分岐・Retry・並列実行・Agent追加へ拡張可能な設計を目指す（今回のFoundation Releaseでは骨組みの確立のみを対象とし、これらの拡張自体は実装しない）。

---

## 2. Background

- **Schedulerは「判定するだけ」で止まっている**：`SchedulerEngine.evaluate()` / `run_due()` は`SchedulerEvent`のリストを返す純粋関数であり、`SchedulerManager`もNewsAgent等の既存Trigger Agentを一切importしない設計（`scheduler_manager.py`のdocstringに明記）。v2.6.0時点では、生成された`SchedulerEvent`を受け取って実際にAgentを起動する経路がどこにも存在しない。
- **既存4Agentは「互いに独立」という設計原則で確立している**：`docs/architecture.md`には「各Agent系は互いに独立したPipelineを持つ」「実行層同士が依存し合うことはない」と明記されており、`AgentManager.from_config()`のexecutorsリストも各Agentが自分のmtime間隔で独立に`decide()`する設計（前段の成否を見て後段を制御する仕組みはない）。今回のWorkflow Engineは、この独立モデルの**上に**「決まった順序で実行する」オーケストレーション層を新設するものであり、既存の独立性原則そのものを破棄するものではない（4章）。
- **クラス名の衝突**：`src/ai/workflow_context.py` / `workflow_step.py` / `workflow_result.py`には、v1.20.0の`WorkflowRunner`（Improvement→ImprovementReview→Rewrite→RewriteReview→Publish→PublishReviewの6ステップ）が使う`WorkflowContext` / `WorkflowStep` / `WorkflowResult`が既に存在する。今回新設する同名クラス（`WorkflowContext` / `WorkflowStep` / `WorkflowResult`）は対象が全く異なる（AI記事改善パイプライン vs Agent実行オーケストレーション）ため、同一パッケージ（`src/ai/`）に置くと名前が衝突する。名前空間の分離方法はArchitecture Designで確定する（6章 Open Questions）。
- **CHANGELOG.mdにv2.6.0のエントリが未記載**：直近のcommit（`0d28d30`）はScheduler Agent Foundationだが、CHANGELOG.mdには反映されていない模様（本Charter作成時点でgrep未検出）。Release 2.7のドキュメント整備時に合わせて確認・追記する（Scope外の既存負債として3章に記録）。

---

## 3. Scope

### 実装対象（想定、Architecture Designで確定）

- `WorkflowStep`：Workflow Engineが実行するステップの列挙（News → Review → Publish の3ステップを想定）
- `WorkflowDefinition`：ステップの並び・依存関係を定義するデータ
- `WorkflowContext`：Workflow実行中の状態を保持するデータクラス（v1.20.0の同名クラスとは別物、名前空間はOpen Question）
- `WorkflowEvent`：Scheduler側の`SchedulerEvent`を受け取り、Workflow Engine内部の実行単位に変換したイベント
- `WorkflowExecutor`：`WorkflowDefinition`に従い、各ステップ（既存Trigger Agent）を順序どおりに呼び出す実行エンジン
- `WorkflowManager`：Workflow Engine全体の起動口（`SchedulerEvent`を受け取り`WorkflowExecutor`に処理を委譲する）
- `WorkflowResult`：Workflow全体の実行結果（各ステップの成否をまとめたもの。v1.20.0の同名クラスとは別物）
- 将来の条件分岐・Retry・並列実行・Agent追加のための拡張ポイント（コメント・構造上の予約のみ。実装はしない、8章と同じ考え方）

### 対象外（今回のRelease 2.7では扱わない）

- Scheduler本体（`SchedulerEngine` / `SchedulerJob` / `SchedulerManager` / `SchedulerEvent` / `SchedulerConfig`、いずれもv2.6.0）の改修
- 既存4 Trigger Agent（`NewsAgent` / `WorkflowTriggerAgent` / `PublishTriggerAgent` / `ReviewTriggerAgent`）・各PipelineRunner・対象Service本体の改修
- Windows タスクスケジューラ / Linux cron との実連携（v2.6.0で対象外とされたまま、引き続き対象外）
- 条件分岐・Retry・並列実行そのものの実装（設計上の拡張余地を残すのみ）
- `WorkflowTriggerAgent`（v2.3.0、AI Improvement/Rewrite/Publish 6ステップ全体）をWorkflow Engineの直列ステップに含めるかどうか（ユーザー提示の実行基盤図には含まれていないため対象外と仮定するが、確定はOpen Questionとする）
- CHANGELOG.mdのv2.6.0未記載分の遡及調査・追記（Release 2.7のドキュメント整備作業として別途対応）

---

## 4. Non Goal

- 既存の「Agent系は互いに独立したPipelineを持つ」という2.0〜2.5系のアーキテクチャ原則そのものは破棄しない。Workflow Engineはこの独立モデルの上に「決まった順序で実行する」オーケストレーション層を追加するものであり、既存4Agentが個別に（`scripts/run_*.py`経由で）手動実行できる経路を壊さない
- v1.20.0の`WorkflowRunner`（AI記事改善パイプライン）を置き換えるものではない。別物として共存させる
- 全自動化・人間の承認ゲート撤廃を目指すものではない。Configuration First（デフォルト無効）・安全側デフォルトの原則は維持する
- 汎用的な「何でも繋げるワークフローエンジン」を目指さない。まずはNews→Review→Publishの固定3ステップで骨組みを確立し、抽象化・汎用化は必要になった時点で検討する（Development Charter 8章と同じ考え方）

---

## 5. Success Criteria（Architecture Design以降で検証）

- Workflow Engine自体の有効化ゲート（デフォルト無効）で挙動が一切変わらないこと
- 新設される`WorkflowContext` / `WorkflowStep` / `WorkflowResult`が、既存`src/ai/workflow_*.py`（v1.20.0）のクラスと名前空間上衝突しない（同一プロセスで両方importできる）こと
- Scheduler（v2.6.0）本体・既存4 Trigger Agent・各PipelineRunner・対象Serviceが無改修であること
- `dry_run=True`で副作用（News収集・レビューレポート生成・WordPress下書き投稿）が構造的に発生しないこと
- 各ステップ（News → Review → Publish）の成否が`WorkflowResult`として記録され、実行順序が保証されていること
- E2Eテスト全PASS・既存回帰（v2.0.0〜v2.6.0・v1.20.0）全PASS

---

## 6. Open Questions（Architecture Designフェーズで決定）

1. **名前空間**：新設する`WorkflowContext` / `WorkflowStep` / `WorkflowResult`は、`src/ai/`にある既存v1.20.0クラスと同名になる。新しいパッケージ（例：`src/workflow_engine/`）に分離するか、既存クラスをリネームするか（後者は既存資産への変更が発生するため、Development Charter「最小変更原則」の観点では前者が有力）
2. **スコープ確認**：ユーザー提示の実行基盤図（Scheduler → Workflow Engine → News Agent → Review Trigger → Publish Trigger）には`WorkflowTriggerAgent`（v2.3.0、AI改善6ステップ）が含まれていない。これは意図的な対象外か、記載漏れか
3. **実行方式**：`WorkflowExecutor`は既存の`AgentExecutor.execute()`（Agent単位のdecide/act、mtime間隔判断）をそのまま順に呼び出す薄いオーケストレーターとするか、それとも各Trigger Agentの`decide()`判断を無視して強制的に`act()`させる新しい呼び出し経路を用意するか。後者は既存の「安全側デフォルト・mtime間隔判断」を迂回する可能性があるため、採用する場合は安全性への影響を明確にする
4. **Gate方式**：Workflow Engine自体の有効化ゲート（例：`WORKFLOW_ENGINE_ENABLED`）を、既存4Agentの個別ゲートとどう関係させるか（Workflow Engine有効化時に各Agentの個別ゲートを上書きするのか、両方揃って初めて動くのか）
5. **失敗時・非実行時の扱い**：News Agentが失敗、または`decide()`が「実行不要」と判断した場合、後続のReview Trigger / Publish Triggerを実行するかスキップするか。現状の独立Agentモデルには存在しない「前段の結果に応じた分岐」という概念の導入要否
6. **SchedulerEventとの接続方式**：`SchedulerEngine`は副作用のない純粋関数として維持する設計のため、`run_due()`の戻り値をpollingして`WorkflowManager`に渡す呼び出し元（新規script、または既存scriptの拡張）をどこに置くか

---

## 7. Status

- [x] Project Charter ドラフト作成（本ドキュメント）
- [ ] ChatGPTレビュー
- [ ] Architecture Design
- [ ] Architecture Review
- [ ] 実装開始
