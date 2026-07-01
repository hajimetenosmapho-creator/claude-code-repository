# v2.0.0 AI Agent Foundation 設計書

作成日：2026-07-01（v2.1.0 Documentation Foundationにて事後作成）

> 本設計書は実装（2026-07-01, commit `b5a16ff`）から遅れて作成されたものです。
> 内容は各モジュールのDocstring（非常に詳細）・実装から再構成しています。

---

## 1. Goal

「Workflowを今実行すべきかどうか」を判断する上位レイヤー（Agent層）の骨組みを作る。
v2.0.0時点では判断ロジック本体（具体的なAgent実装）は追加せず、以降のAgent実装（News Agent等）を追加するための土台のみを完成させる。

---

## 2. Background

### 現状の問題点

- v1.20.0までで「6ステップを実行する仕組み」（`WorkflowRunner`）は完成したが、
  「いつ実行するか」は常にブロガーが手動でスクリプトを起動する必要があった。
- Release 2.x では、将来的に「ニュースの重要度に応じて自動でWorkflowを起動する」といった
  半自律的な運営支援を目指しており、そのための「判断」の置き場所がなかった。

### v2.0.0 が解決すること

- Workflowの「実行」と、実行すべきかの「判断」を明確に分離する抽象（`BaseAgent`）を導入する。
- `AgentManager` / `AgentExecutor` という実行パイプラインの骨組みを用意し、
  次のバージョン以降で具体的なAgent（News Agent、Workflow Trigger Agent等）を追加しやすくする。

---

## 3. Scope

### 実装対象

- `AgentTask`：エージェントに判断を依頼する作業単位
- `AgentDecision`：`BaseAgent.decide()`の戻り値（判断結果）
- `AgentContext`：実行時状態
- `AgentResult`：判断・実行結果
- `AgentConfig`：設定値管理
- `BaseAgent`（ABC）：全Agent実装が継承する抽象基底クラス
- `AgentExecutor`：`decide()` / `act()`を決まった順序で呼び出すパイプライン
- `AgentManager` / `NullAgentManager`：登録されたExecutorにタスクを実行させるマネージャ

### 対象外（Non Goalへ）

- 具体的なAgent実装（News Agent、Workflow Trigger Agent等）は本バージョンでは追加しない
- `WorkflowRunner`の変更（Agent層はWorkflow層を呼び出す側であり、呼び出される側ではない）

---

## 4. Non Goal

- v2.0.0時点では`BaseAgent`の具体的な実装クラスを1つも追加しない。`AgentManager.from_config()`は`is_ready()=True`でも`executors=[]`（空リスト）を返す。
- Agentは`WorkflowRunner`を**置き換えるものではない**。「6ステップを実行する」仕組みはWorkflow層にそのまま残し、Agent層はその上に「判断」だけを追加する。
- デフォルトは無効（`AI_AGENT_ENABLED=false`）。既存の`WorkflowRunner`経由の自動実行フローに影響を与えない。

---

## 5. User Workflow

### Before（v1.20.0）

- `python scripts/run_ai_workflow.py`をブロガーが手動で（あるいはタスクスケジューラで無条件に）実行する必要があった。「今実行すべきか」の判断はブロガー自身が行っていた。

### After（v2.0.0、骨組みのみ）

- v2.0.0時点ではまだ具体的なAgentが存在しないため、エンドユーザー（ブロガー）の体験は変化しない。
- 次バージョン以降でNews Agent等が追加されると、「ニュースの重要度が高い場合のみWorkflowを起動する」といった判断が自動化される想定。

---

## 6. System Workflow

```
AgentManager.run(task, dry_run=False)
  → 各 AgentExecutor ごとに新しい run_id を発行し AgentContext を生成
  → AgentExecutor.execute(context)
       1. before_execute（started_at計測、agent_name設定）
       2. BaseAgent.decide(context) → AgentDecision を context.decisions に記録
       3. should_act=False、または dry_run=True の場合
            → act() を呼ばず AgentExecutor 自身が AgentResult を組み立てる
       4. should_act=True かつ dry_run=False の場合のみ
            → BaseAgent.act(decision, context) を呼ぶ（Workflow起動等の副作用はここで発生）
       5. 例外発生時は context.errors に記録し、success=False の AgentResult を組み立てる
       6. after_execute（finished_at計測）
       7. finalize（run_id/agent_name/started_at/finished_atをcontextの値で必ず上書き）
  → AgentResult のリストを返す
```

### decide() と act() の責務分離

- `decide()`は**判断専用**。ファイル書き込み・Workflow起動・外部API呼び出しなどの副作用を持たない。
- `act()`は`decision.should_act=True`かつ`context.dry_run=False`の場合のみ`AgentExecutor`から呼ばれる。実際の副作用（Workflow起動等）はここでのみ発生する。
- この分離により、`dry_run=True`で「何をすべきかだけ確認する」実行が安全に行える。

---

## 7. Data Model

### `AgentTask`（`agent_task.py`）

| フィールド | 型 | 内容 |
|---|---|---|
| `task_id` | `str` | 自由記述の識別子（解釈は各`BaseAgent`実装に委ねる） |
| `params` | `dict` | タスクパラメータ |

`WorkflowStep`のような固定Enumにはしていない。Workflowのステップは実行順序が確定した6ステップだが、Agentのタスク種別は将来のAgent追加ごとに増減しうるため。

### `AgentDecision`（`agent_decision.py`）

| フィールド | 型 | 内容 |
|---|---|---|
| `should_act` | `bool` | Actionを実行すべきか |
| `reason` | `str` | 判断理由 |

### `AgentContext`（`agent_context.py`）

| フィールド | 型 | 内容 |
|---|---|---|
| `task` | `AgentTask` | 実行パラメータ |
| `dry_run` | `bool` | 実行パラメータ |
| `run_id` / `agent_name` | `str` | Execution Metadata（`AgentExecutor`が設定） |
| `started_at` / `finished_at` | `datetime \| None` | 実行時刻 |
| `decisions` / `warnings` / `errors` / `logs` | `list` | ランタイム状態 |

`elapsed_time`はプロパティとして計算する（保存しない）。`started_at`/`finished_at`との不整合を構造的に防ぐため。

### `AgentResult`（`agent_result.py`）

| フィールド | 型 | 内容 |
|---|---|---|
| `run_id` / `agent_name` | `str` | 実行識別情報 |
| `task` | `AgentTask` | 依頼されたタスク |
| `decision` | `AgentDecision` | 判断結果 |
| `action_taken` | `bool` | `act()`を実際に実行したか |
| `success` | `bool` | Agent自身の判断・実行プロセスが例外なく完了したか |
| `workflow_result` | `WorkflowResult \| None` | `act()`がWorkflowを起動した場合の参照 |
| `error_message` | `str \| None` | 例外発生時のメッセージ |
| `warnings` | `list[str]` | dry_runによるAction省略等の記録 |

**設計上の重要な区別**：`success`は「Agent自身の判断・実行が完了したか」を表し、呼び出したWorkflowが失敗したかどうかは`workflow_result.overall_success`を別途参照する。両者を混同しない。また`workflow_result`は`WorkflowResult`のフィールドをコピーせず、参照のみ保持する。

---

## 8. Directory Structure

```
src/ai/
├── agent_task.py       # AgentTask
├── agent_decision.py   # AgentDecision
├── agent_context.py    # AgentContext
├── agent_result.py     # AgentResult
├── agent_config.py     # AgentConfig
├── base_agent.py       # BaseAgent（ABC）
├── agent_executor.py   # AgentExecutor
└── agent_manager.py    # AgentManager / NullAgentManager
```

`scripts/`配下に本バージョン用のエントリスクリプトは追加されていない（具体的なAgent実装が存在しないため、まだ呼び出し口がない）。

---

## 9. Module Design

### `AgentConfig`（`agent_config.py`）

| フィールド | デフォルト |
|---|---|
| `enabled` | `False`（`AI_AGENT_ENABLED`） |

`is_ready()`は`enabled`のみを見る。デフォルト無効とすることで、既存の`WorkflowRunner`経由の自動実行フローに影響を与えない設計。

### `BaseAgent`（ABC、`base_agent.py`）

```python
class BaseAgent(ABC):
    def name(self) -> str: ...
    def decide(self, context: AgentContext) -> AgentDecision: ...
    def act(self, decision: AgentDecision, context: AgentContext) -> AgentResult: ...
```

`BaseAgent`は`AgentExecutor`をimportしない（責務を混同しないため）。実際のWorkflow起動・副作用の実行は`AgentExecutor`ではなく、各Agent実装の`act()`内で行う想定。

### `AgentExecutor`（`agent_executor.py`）

- `dry_run`判定・`started_at`/`finished_at`の計測は`AgentExecutor`側の責務。`BaseAgent`実装はこれらを気にしなくてよい
- `_finalize()`で、経路（should_act=False / dry_run / act()実行 / 例外）によらず`run_id`/`agent_name`/`started_at`/`finished_at`がcontextの値と必ず一致するよう最後に上書きする（`BaseAgent.act()`が独自に`AgentResult`を構築するケースでも整合性を保証するため）

### `AgentManager` / `NullAgentManager`（`agent_manager.py`）

- `from_config()`：`AgentConfig.is_ready()`が`False`なら`NullAgentManager`を返す。v2.0.0時点では具体的なAgent実装が存在しないため、`is_ready()=True`の場合でも`executors=[]`（空リスト）を返す
- `run(task, dry_run=False)`：タスク実行のたびに新しい`run_id`（`uuid.uuid4().hex`）を発行し、登録された各`AgentExecutor`に実行させる。`AgentContext`の構築は`AgentManager`の責務
- `NullAgentManager.run()`は`[AGENT] AI Agent基盤が無効です`を表示して空リストを返す

---

## 10. Configuration Design

`.env.example` への追記は本バージョンでは未実施。

```
AI_AGENT_ENABLED=false
```

### Configuration First の設計意図

`AI_AGENT_ENABLED=false`（デフォルト）の場合、`AgentManager.from_config()`は`NullAgentManager`を返す。呼び出し側は「Agent基盤が有効かどうか」の分岐を書かずに済む。v2.0.0時点では有効化しても`executors=[]`のため実質的な動作は変わらない（次バージョン以降でAgent実装を追加した時点で意味を持つ）。

---

## 11. AI Workflow Foundation との関係

- Agent層は`WorkflowRunner`（v1.20.0）を**呼び出す側**として設計されている。`AgentResult.workflow_result`フィールドは`WorkflowResult`型を参照する構造になっており、将来Agentの`act()`が`WorkflowRunner.run()`を呼び出した結果をそのまま格納する想定
- v2.0.0時点ではこの接続はまだ実装されていない（`executors=[]`のため、`act()`が呼ばれるAgent自体が存在しない）
- Workflow層・Service層への変更は不要（Agent層の追加はWorkflowを呼び出す新しい上位レイヤーの追加であり、既存層の責務は変わらない）

---

## 12. Error Handling

| ケース | 対応 |
|---|---|
| `decide()`実行中の例外 | `context.errors`に記録。`decision`が未確定の場合は`should_act=False`の`AgentDecision`を代わりに生成し、`success=False`の`AgentResult`を返す |
| `act()`実行中の例外 | 同上（`AgentExecutor.execute()`内の`try/except`で一括捕捉） |
| `AI_AGENT_ENABLED=false` | `NullAgentManager`が空リストを返す（例外は発生しない） |

---

## 13. Future Extensions

- Phase 1：News Agent（ゲームニュース収集の実行要否を判断するAgent）の実装
- Phase 2：Workflow Trigger Agent（`WorkflowRunner`の起動タイミングを判断するAgent）の実装
- Phase 3：上記Agentを`AgentManager.from_config()`内で`AgentExecutor`としてDIし、`executors`リストを実際に埋める
- Phase 4：半自律的なブログ運営支援（人間の承認ゲート付き、長期ビジョンとして`docs/ROADMAP.md`に記載）

---

## 14. Definition of Done

### コード

- [x] `AgentTask` / `AgentDecision` / `AgentContext` / `AgentResult` / `AgentConfig` / `BaseAgent` / `AgentExecutor` / `AgentManager` の実装

### テスト

- [x] `tests/test_e2e_v2_0_0_ai_agent_foundation.py`: 118/118 PASS

### ドキュメント

- [x] 本設計書（v2.1.0にて事後作成）
- [x] CHANGELOG.md / ROADMAP.md への記載
- [x] `docs/architecture.md`にAgent層として追記

### リリース

- [x] 2026-07-01 コミット済み（`b5a16ff`）

---

## 15. 備考：本ドキュメントの位置づけについて

既存の設計書（`publishing_automation.md`等）は15章構成ですが、本ドキュメントは章立ての都合上14章構成になっています（「7. Data Model」に複数クラスをまとめたため）。内容の網羅性は他の設計書と同等です。
