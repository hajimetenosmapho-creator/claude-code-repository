# v2.7.0 Workflow Engine Foundation 設計書

作成日：2026-07-02
状態：Architecture Design 確定（Architecture Review完了・修正必須事項3点反映済み、2026-07-02）。`docs/design/workflow_engine_foundation_charter.md`（Project Charter）のOpen Questionsを本ドキュメントで確定する。

---

## 1. Goal

Scheduler（v2.6.0）が生成する`SchedulerEvent`を起点に、既存の3つのTrigger Agent（`NewsAgent` v2.2.0 → `ReviewTriggerAgent` v2.5.0 → `PublishTriggerAgent` v2.4.0）を決まった順序で実行する**Workflow Engine**を、新規パッケージ`src/workflow_engine/`として追加する。

```
Scheduler            （判断：今このJobを実行すべきか、v2.6.0、無改修）
   ↓ SchedulerEvent
Workflow Engine        （実行：登録されたステップを順序どおりに実行する、新規）
   ↓
NewsAgent             （既存、v2.2.0、無改修）
   ↓
ReviewTriggerAgent    （既存、v2.5.0、無改修）
   ↓
PublishTriggerAgent   （既存、v2.4.0、無改修）
```

Workflow Engineは既存4Agentが確立した「Agent系は互いに独立したPipelineを持つ」という2.0〜2.5系の原則を破棄せず、その**上位に「決まった順序で呼び出す」オーケストレーション層を追加する**位置づけとする（Non Goal参照）。

---

## 2. Background

`docs/design/workflow_engine_foundation_charter.md`（Project Charter）とそのChatGPTレビューを前提とする。レビューで確定した3つの前提：

1. Scheduler（v2.6.0）は「実行判定」までであり、Agent起動までは担当していない
2. 既存4Agentは独立Pipelineとして設計されており、Release 2.7はそれらを直接改造するのではなく、上位のオーケストレーション層を追加する位置づけである
3. `src/ai/`に既存の`WorkflowStep` / `WorkflowContext` / `WorkflowResult`（v1.20.0）が存在するため、名前衝突を避ける必要がある

本ドキュメント作成にあたり、追加で以下の実装済みコードを確認した：

- **`NewsAgentConfig`（v2.2.0）には有効化ゲートが存在しない**：`enabled`フィールドがなく、`AI_AGENT_ENABLED=true`であれば`AgentManager.from_config()`は無条件で`NewsAgent`を`executors`に登録する。一方`ReviewTriggerAgentConfig` / `PublishTriggerAgentConfig`は独自の`enabled`（`is_ready()`）を持つ。Workflow Engineの各ステップは、この非対称性をそのまま引き継ぐ（7章）
- **`SchedulerRepository`（v2.6.0）は`InMemorySchedulerRepository`のみ**：Job登録はプロセスメモリ上にのみ存在し、プロセス終了とともに消える（永続化は対象外、`scheduler_repository.py`のdocstringに明記）。したがって、Scheduler経由でWorkflow Engineを起動する呼び出し元（10章）は、実行のたびにJob定義を再登録する前提で設計する
- `AgentResult`（`src/ai/agent_result.py`）は`workflow_result: WorkflowResult | None`フィールドを持つが、これは既存`WorkflowTriggerAgent`が`WorkflowRunner`（v1.20.0）の結果を格納するための専用フィールドであり、`ReviewTriggerAgent` / `PublishTriggerAgent`では常に`None`。Workflow Engineはこのフィールドを使わず、独自の`WorkflowEngineResult`で結果を管理する（5章）

**用語整理（Event Driven Architectureの意味）**：本プロジェクトにおける「Event Driven Architecture」は、非同期メッセージング・pub/sub基盤を指すものではない。`SchedulerEvent`（v2.6.0）のdocstringが示すとおり、「判断（Scheduler）が実行手段を直接呼ばず、判断結果をデータ（Event）として受け渡すことで、判断と実行を構造的に分離する」ことを指す。Workflow Engineが3ステップを1プロセス内で同期的に直列実行する構造（8章）は、この「判断と実行の構造的分離」を維持したままの上位オーケストレーションであり、非同期化・並列化を意味するものではない（Architecture Reviewで指摘済み。将来Retry・並列実行を導入する際も、この用語整理を前提とする）。

Charterで残していたOpen Questionsを、本ドキュメントの5〜10章で確定する。

---

## 3. Scope

### 実装対象

- `src/workflow_engine/`：新規パッケージ（5章）
  - `WorkflowEngineStep`（Enum）・`WorkflowEngineDefinition`
  - `WorkflowEngineEvent`・`WorkflowEngineContext`
  - `WorkflowEngineStepResult`・`WorkflowEngineResult`
  - `WorkflowEngineConfig`
  - `WorkflowEngineExecutor`
  - `WorkflowEngineManager` / `NullWorkflowEngineManager`
- `scripts/run_workflow_engine.py`：Scheduler判定 → Workflow Engine実行の手動実行エントリ（10章・12章）。**Foundation Releaseでは固定・最小限（1件）のデモJobのみを扱う**（12章で範囲を明文化）
- `tests/test_e2e_v2_7_0_workflow_engine_foundation.py`：新規E2Eテスト（実装フェーズで作成）

### 対象外

- Scheduler本体（`SchedulerEngine` / `SchedulerJob` / `SchedulerManager` / `SchedulerEvent` / `SchedulerConfig` / `SchedulerRepository`、いずれもv2.6.0）の改修
- 既存4 Trigger Agent（`NewsAgent` / `WorkflowTriggerAgent` / `PublishTriggerAgent` / `ReviewTriggerAgent`）・各PipelineRunner・対象Service本体の改修
- `AgentManager` / `AgentExecutor` / `BaseAgent` / `AgentContext` / `AgentDecision` / `AgentResult` / `AgentConfig`（v2.0.0 Agent Foundation）の改修（Workflow Engineはこれらを**無改修のまま呼び出す**、8章）
- Windows タスクスケジューラ / Linux cron との実連携（v2.6.0で対象外とされたまま、引き続き対象外）
- 条件分岐・Retry・並列実行そのものの実装（拡張ポイントの予約のみ、17章）
- `WorkflowTriggerAgent`（v2.3.0）をWorkflow Engineのステップに含めること（9章で対象外と確定）
- SchedulerJobの永続化（JSON/DB化）・Job定義の外部設定ファイル化・複数Jobの動的登録（v2.6.0からの既知の未対応事項を引き継ぐ。`scripts/run_workflow_engine.py`は固定1件のデモJobのみを扱い、これらはすべてFuture Extensions行きとする、12章・17章）
- 複数実行主体（`AgentManager`経由の既存script群と`WorkflowEngineManager`経由の新script）が同時実行された場合の排他制御・ロック実装（13.1節で運用制約として明記するのみとし、コードでの対処はRelease 2.7の対象外とする）
- CHANGELOG.mdのv2.6.0未記載分の遡及調査（Release 2.7のドキュメント整備作業として別途対応）

---

## 4. Non Goal

- 既存の「Agent系は互いに独立したPipelineを持つ」という2.0〜2.5系のアーキテクチャ原則そのものは破棄しない。`WorkflowEngineExecutor`は各Agentの`decide()`（実行要否の判断）をそのまま尊重し、強制的に`act()`させる経路は用意しない（8章）
- v1.20.0の`WorkflowRunner`（AI記事改善パイプライン）を置き換えるものではなく、`src/ai/workflow_*.py`には一切手を加えない。別パッケージ（`src/workflow_engine/`）・別クラス名（`WorkflowEngine*`接頭辞）で完全に分離する（5章）
- 全自動化・人間の承認ゲート撤廃を目指すものではない。Configuration First（デフォルト無効）・安全側デフォルトの原則は維持する（7章）
- 汎用的な「何でも繋げるワークフローエンジン」は目指さない。News → Review → Publishの固定3ステップで骨組みを確立するのみ

---

## 5. Package・命名設計（Open Question #1 の結論）

**結論：新規パッケージ`src/workflow_engine/`を作成し、既存`src/ai/`とは物理的に分離する。クラス名はすべて`WorkflowEngine`接頭辞で統一する。**

| 新規クラス | 既存クラス（v1.20.0、`src/ai/`） | 関係 |
|---|---|---|
| `WorkflowEngineStep` | `WorkflowStep` | 別物。前者は3ステップ（NEWS/REVIEW/PUBLISH）、後者は6ステップ（IMPROVEMENT〜PUBLISH_REVIEW） |
| `WorkflowEngineContext` | `WorkflowContext` | 別物。前者はAgent実行の順序制御用、後者はAI改善パイプラインの実行状態用 |
| `WorkflowEngineResult` | `WorkflowResult` | 別物。フィールド構成は似るが対象が異なる |
| `WorkflowEngineDefinition` | （既存に相当するものなし） | 新規概念。ステップの並びを定義する |
| `WorkflowEngineEvent` | （既存に相当するものなし） | 新規概念。`SchedulerEvent`を受けてWorkflow Engine内部で扱う実行単位 |
| `WorkflowEngineExecutor` | （既存に相当するものなし） | 新規概念。ステップを順に実行するエンジン |
| `WorkflowEngineManager` | （既存に相当するものなし） | 新規概念。Workflow Engine全体の起動口（`AgentManager`と対になる構造） |

**衝突しないことの根拠**：

1. **パッケージが別**：`from ai.workflow_step import WorkflowStep` と `from workflow_engine.workflow_engine_step import WorkflowEngineStep` は別モジュールであり、同一プロセス内で両方importしても`sys.modules`上で衝突しない
2. **クラス名自体が別**：仮に両パッケージを`from ai import *` / `from workflow_engine import *`のようにワイルドカードimportしても、`WorkflowStep`と`WorkflowEngineStep`は文字列として異なるため、`__all__`上でも衝突しない（二重の安全策）
3. `src/workflow_engine/`は`src/ai/`をimportする（8章、一方向依存）が、逆方向（`src/ai/`が`src/workflow_engine/`をimportする）は発生しない設計とする。既存の`ai → workflow_engine`という逆依存が生まれないことを、実装フェーズのArchitecture Guardテストで静的に確認する

---

## 6. Data Model

### `WorkflowEngineStep`（`src/workflow_engine/workflow_engine_step.py`）

```python
class WorkflowEngineStep(Enum):
    NEWS    = "news"
    REVIEW  = "review"
    PUBLISH = "publish"

ALL_WORKFLOW_ENGINE_STEPS = [
    WorkflowEngineStep.NEWS,
    WorkflowEngineStep.REVIEW,
    WorkflowEngineStep.PUBLISH,
]
```

`WorkflowTriggerAgent`（AI改善6ステップ）に対応するステップは含めない（9章）。

### `WorkflowEngineDefinition`（`src/workflow_engine/workflow_engine_definition.py`）

```python
@dataclass
class WorkflowEngineDefinition:
    steps: list[WorkflowEngineStep] = field(default_factory=lambda: list(ALL_WORKFLOW_ENGINE_STEPS))
```

Foundation Releaseでは`ALL_WORKFLOW_ENGINE_STEPS`固定の1種類のみを想定するが、将来の条件分岐・部分実行（例：Reviewだけ実行）に備え、`steps`を外部から差し替え可能なフィールドとして持たせる（16章）。

### `WorkflowEngineEvent`（`src/workflow_engine/workflow_engine_event.py`）

```python
SOURCE_SCHEDULER = "scheduler"
SOURCE_MANUAL = "manual"

@dataclass
class WorkflowEngineEvent:
    job_id: str
    source: str            # "scheduler" | "manual"（Open Question修正必須事項#2）
    triggered_at: datetime  # イベントが生成された日時
    trigger_reason: str
    metadata: dict = field(default_factory=dict)
```

`SchedulerEvent`（`src/scheduler/scheduler_event.py`）とフィールド構成は近いが、あえて別クラスとして定義する。理由：`src/workflow_engine/`が`src/scheduler/`をimportしない設計にするため（10章）。`SchedulerEvent → WorkflowEngineEvent`の変換は、呼び出し元（`scripts/run_workflow_engine.py`）の責務とする。

**構築方法の確定（修正必須事項#2、12章 CLI設計と対応）**：

| 起動経路 | `job_id` | `source` | `triggered_at` | `trigger_reason` |
|---|---|---|---|---|
| `SchedulerEvent`経由（デフォルト、Scheduler判定を通った場合） | `SchedulerEvent.job_id`をそのままコピー | `SOURCE_SCHEDULER`（`"scheduler"`） | `SchedulerEvent.execute_time`をそのままコピー | `SchedulerEvent.trigger_reason`をそのままコピー |
| `--job-id`指定（Scheduler判定を経由しない手動実行） | CLI引数でユーザーが指定した値をそのまま使用 | `SOURCE_MANUAL`（`"manual"`） | `datetime.now()`（呼び出し時点の時刻） | 固定文言`"Manual invocation via --job-id."` |

`WorkflowEngineContext.event`は上記いずれの経路でも必ず`WorkflowEngineEvent`のインスタンスが設定される（後述のとおり`None`は許容しない）。「Scheduler経由か手動か」の区別は`event.source`で判定できるため、`event`自体をOptionalにする必要はない。

### `WorkflowEngineContext`（`src/workflow_engine/workflow_engine_context.py`）

```python
@dataclass
class WorkflowEngineContext:
    event: WorkflowEngineEvent          # Scheduler経由・手動経路のいずれも必ず設定される（event.sourceで区別）
    dry_run: bool
    run_id: str
    started_at: datetime | None = None
    finished_at: datetime | None = None
    step_results: list[WorkflowEngineStepResult] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
```

`AgentContext`と同様、設定値ではなく実行時状態のみを保持する。

### `WorkflowEngineStepResult` / `WorkflowEngineResult`（`src/workflow_engine/workflow_engine_result.py`）

```python
REASON_NOT_REACHED = "Not reached: an earlier step failed."

@dataclass
class WorkflowEngineStepResult:
    step: WorkflowEngineStep
    executed: bool                       # Gateが開いていてAgentExecutorを呼んだか
    agent_result: AgentResult | None      # 未実行（Gate閉鎖 or 前段失敗による未到達）の場合はNone
    success: bool                         # 失敗ではないか（8章の判定基準）
    skipped_reason: str | None            # 未実行の理由（Gate閉鎖時、または前段失敗により
                                           # 未到達だった場合[REASON_NOT_REACHED]に設定。修正推奨事項）


@dataclass
class WorkflowEngineResult:
    steps: list[WorkflowEngineStepResult]
    overall_success: bool
    stopped_early: bool                   # 途中失敗により後続ステップを打ち切ったか
    started_at: datetime
    finished_at: datetime
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict: ...
    def to_json(self) -> str: ...
```

`to_dict()` / `to_json()`は既存`WorkflowResult` / `AgentResult`と同じ形式（`isoformat()`変換等）を踏襲する。

### `WorkflowEngineConfig`（`src/workflow_engine/workflow_engine_config.py`）

```python
@dataclass
class WorkflowEngineConfig:
    enabled: bool          # WORKFLOW_ENGINE_ENABLED（デフォルトfalse）
    project_root: Path

    @classmethod
    def from_env(cls, project_root: Path) -> "WorkflowEngineConfig": ...

    def is_ready(self) -> bool:
        return self.enabled
```

`AgentConfig`と同じく設定値のみを保持する。Gate方式の詳細は7章。

---

## 7. Gate方式（Open Question #4 の結論）

**結論：Workflow Engine全体の有効化は二重ゲート、各ステップの実行可否はステップごとの既存ゲートに委ねる「二層構造」とする。**

### 7.1 Workflow Engine全体のゲート（二重ゲート）

```
AI_AGENT_ENABLED（AgentConfig.is_ready()）
    ×
WORKFLOW_ENGINE_ENABLED（WorkflowEngineConfig.is_ready()）
```

`ReviewTriggerAgent`（v2.5.0）と同型の二重ゲート。`WorkflowEngineManager.from_config(agent_config, workflow_engine_config)`が両方の`is_ready()`を見て、いずれかがFalseなら`NullWorkflowEngineManager`を返す（Configuration First）。

### 7.2 ステップごとのゲート（既存Configの`is_ready()`を再利用）

| ステップ | ゲート | 理由 |
|---|---|---|
| `NEWS` | 常に有効（`AI_AGENT_ENABLED`のみ） | `NewsAgentConfig`（v2.2.0）には`enabled`相当のフィールドが存在しないため（2章） |
| `REVIEW` | `ReviewTriggerAgentConfig.is_ready()`（`REVIEW_TRIGGER_AGENT_ENABLED`） | 既存の二重ゲート判定をそのまま再利用 |
| `PUBLISH` | `PublishTriggerAgentConfig.is_ready()`（`PUBLISH_TRIGGER_AGENT_ENABLED` × `AiPublishConfig.is_ready()`） | 既存の三重ゲート判定をそのまま再利用 |

`WorkflowEngineManager.from_config()`は、ステップごとのゲートがFalseの場合、そのステップに対応する`AgentExecutor`を構築せず、`WorkflowEngineExecutor`には「未構築（None）」として渡す。`WorkflowEngineExecutor`は未構築のステップを`executed=False, success=True, skipped_reason="..."`として記録し、後続ステップの実行を妨げない（8章）。

**この二層構造を選んだ理由**：Workflow Engine自体のON/OFFと、個々のAgentのON/OFFを混同しないため。`WORKFLOW_ENGINE_ENABLED=true`にしても、`REVIEW_TRIGGER_AGENT_ENABLED=false`のままであればReviewステップは自動的にスキップされる（＝既存の安全側デフォルトが保たれる）。これにより、運用者は「まずNewsだけ自動化し、Reviewは後日有効化する」といった段階的な導入ができる。

---

## 8. 実行方式：既存Agentとの連携（Open Question #3・#5 の結論）

### 8.1 既存の`decide()`を尊重する（強制`act()`は行わない）

**結論：`WorkflowEngineExecutor`は各ステップに対応する既存`AgentExecutor.execute(context)`をそのまま呼び出す。各Agentの`decide()`（mtime間隔判断）・`dry_run`制御を一切迂回しない。**

理由：

- Development Charter「意思決定原則」（13章）における最優先事項は「ユーザーへの安全性」。強制的に`act()`させる経路を用意すると、`min_interval_minutes`による間隔制御が意味をなさなくなり、Workflow Engine経由の呼び出しだけ安全策が効かなくなる
- 「Workflow Engineが定めるのは実行順序であり、実行要否の判断はAgent自身が引き続き担う」という責務分離を保つほうが、既存4Agentとの一貫性が高い

この結果、「Workflow Engineが有効になったら毎回3ステップとも必ず実行される」わけではない。News/Review/Publishそれぞれの`decide()`が`should_act=False`と判断すれば、そのステップは`AgentExecutor`の既存仕様により`act()`を呼ばずに完了する（`AgentResult.action_taken=False, success=True`）。

### 8.2 各ステップの実行主体：AgentManagerを経由せず、WorkflowEngineManagerが独自にAgent実体を構築する

**結論：`WorkflowEngineManager`は`AgentManager`を呼び出さず、`NewsAgent` / `ReviewTriggerAgent` / `PublishTriggerAgent`とそれぞれの`PipelineRunner`を、既存の`Config.from_env()`をそのまま使って自前で構築する。**

```python
# WorkflowEngineManager.from_config() 内（イメージ）
news_agent_config = NewsAgentConfig.from_env(project_root=agent_config.base_dir)
news_executor = AgentExecutor(
    NewsAgent(config=news_agent_config, runner=NewsPipelineRunner(news_agent_config))
)  # NewsAgentConfigにゲートがないため常に構築（7章）

review_trigger_agent_config = ReviewTriggerAgentConfig.from_env(project_root=agent_config.base_dir)
review_executor = None
if review_trigger_agent_config.is_ready():
    review_executor = AgentExecutor(
        ReviewTriggerAgent(config=review_trigger_agent_config, runner=ReviewPipelineRunner(review_trigger_agent_config))
    )

publish_trigger_agent_config = PublishTriggerAgentConfig.from_env(project_root=agent_config.base_dir)
publish_executor = None
if publish_trigger_agent_config.is_ready():
    publish_executor = AgentExecutor(
        PublishTriggerAgent(config=publish_trigger_agent_config, runner=PublishPipelineRunner(publish_trigger_agent_config))
    )
```

**なぜ`AgentManager`を経由しないか（比較検討）**：

| 案 | 内容 | 採否 |
|---|---|---|
| A. `AgentManager`に「特定のAgentだけ実行する」APIを追加 | `AgentManager.get_executor(name)`等を新設し、`WorkflowEngineManager`がそれ経由でNews/Review/Publishの`AgentExecutor`を取得する | 不採用。`AgentExecutor` / `AgentManager`（v2.0.0 Agent Foundation）への改修が必要になり、3章「対象外」の趣旨（既存Agent関連コードは無改修）に反する |
| B. `WorkflowEngineManager`が独自にAgent実体を構築する（採用） | 各Trigger Agentの`Config.from_env()` / `PipelineRunner` / `Agent`クラスをそのままimportし、`AgentManager.from_config()`内の構築コードと同じ形を独自に組み立てる | 採用。既存`ai` / `pipeline`パッケージのクラスは一切改修せず、importして使うだけで済む |

案Bは`AgentManager.from_config()`と構築ロジックが一部重複するが、既存コードベースでも「4つのTrigger Agentそれぞれの構築ブロックがコピーに近い形で並ぶ」設計が既に採用されており（`agent_manager.py`参照）、Development Charter 8章「抽象化は必要になってから行う」の方針とも整合する。共通化は、将来Workflow Engineが増えた場合に改めて検討する（16章）。

**`AgentManager`経由で登録されるAgent実体とは別インスタンスになる点について**：`scripts/run_news_agent.py`等が使う`AgentManager`内の`NewsAgent`と、`WorkflowEngineManager`が構築する`NewsAgent`は別オブジェクトになる。両者とも`decide()`はファイルシステムの状態（`outputs/`配下のmtime等）を都度読みに行う設計であり、インスタンス間で共有すべき状態を持たないため、実行結果に矛盾は生じない。

### 8.3 ステップ実行順序と失敗時の打ち切り（Open Question #5 の結論）

**結論：「実行した結果として失敗した（`success=False`）」場合のみ後続ステップを打ち切る。「Gate閉鎖によるスキップ」「`decide()`による実行不要判断」は失敗として扱わず、後続ステップの実行を継続する。**

```
WorkflowEngineExecutor.run():
    stopped_early = False

    for step in definition.steps:
        if stopped_early:
            # 前段の失敗により、以降のステップは実行せず「未到達」として記録する（修正推奨事項）
            record StepResult(step, executed=False, agent_result=None,
                               success=False, skipped_reason=REASON_NOT_REACHED)
            continue

        executor = step_executors.get(step)  # None の場合あり（7章）

        if executor is None:
            record StepResult(step, executed=False, agent_result=None,
                               success=True, skipped_reason="<ゲート閉鎖の理由>")
            continue  # 後続ステップは実行を継続する

        agent_result = executor.execute(AgentContext(...))  # 既存AgentExecutor、無改修

        record StepResult(step, executed=True, agent_result=agent_result,
                           success=agent_result.success, skipped_reason=None)

        if not agent_result.success:
            stopped_early = True  # 以降のステップは上記の分岐で「未到達」として記録される

    overall_success = all(r.success for r in step_results)
```

`WorkflowEngineResult.steps`は、この設計により**常に`definition.steps`と同じ件数**になる（Gate閉鎖によるスキップ・前段失敗による未到達のいずれも、`executed=False`のエントリとして必ず記録される）。これにより、途中で打ち切られた場合でも「どのステップが何の理由で動かなかったか」を`WorkflowEngineResult`単体から監査できる（修正推奨事項、Architecture Review §5-1）。未到達ステップの`success`はGate閉鎖時（`True`）とは異なり`False`とする。前段の失敗を受けて実行されなかった状態は「問題なくスキップされた」わけではないため、`overall_success`の算出に正しく反映させる。

**打ち切り基準を「Gate閉鎖・decide()スキップ」ではなく「実行失敗」に限定した理由**：

- 各ステップは独立した判断材料（mtime間隔）を持つ。Newsが「間隔内でスキップ」されたとしても、Reviewが実行すべきタイミングにある可能性は独立して存在する。前段のスキップを理由に後段まで止めると、既存4Agent時代（互いに独立）の挙動から不必要に後退する
- 一方、Newsが**実際に失敗**した場合（例：RSS取得中の例外、`main.py`のタイムアウト等）は、収集された記事データの整合性が保証できない状態でReview/Publishを進めるのは安全性の観点から避けるべきである（Development Charter 13章「安全性」最優先）

---

## 9. `WorkflowTriggerAgent`をスコープに含めるか（Open Question #2 の結論）

**結論：Release 2.7では対象外とする。**

理由：

1. ユーザーが提示した実行基盤図（Scheduler → Workflow Engine → News Agent → Review Trigger → Publish Trigger）に`WorkflowTriggerAgent`（v2.3.0、AI Improvement/Rewrite/Publishの6ステップ）は含まれていない
2. `WorkflowTriggerAgent`が最終的に呼び出す`WorkflowRunner`の6ステップには`PUBLISH`（WordPress下書き投稿）が含まれており、`PublishTriggerAgent`（`AiPublishService`を直接起動）と役割が重複する。両方を同一のWorkflow Engine定義に含めると、「どちらの経路でWordPress投稿が行われたか」が曖昧になり、Charter「Non Goal」の安全性方針に反するおそれがある
3. 実装済みの3Agent（News/Review/Publish）だけでもFoundation Releaseとして意味のある区切りになる。`WorkflowTriggerAgent`を含めるかどうかは、両者の役割整理（Publish系統の一本化）を別途検討したうえで将来Releaseで判断する（16章 Future Extensions）

---

## 10. SchedulerEventとの接続方式（Open Question #6 の結論）

**結論：新規スクリプト`scripts/run_workflow_engine.py`を、SchedulerとWorkflow Engineを橋渡しする「呼び出し元」として新設する。`SchedulerEngine` / `SchedulerManager`本体は無改修。**

```
1. SchedulerConfig.from_env() でScheduler設定を読み込む（v2.6.0、無改修）
2. InMemorySchedulerRepository() を生成し、SchedulerManager 経由でデモ用SchedulerJobを登録する
   （v2.6.0はメモリ管理のみのため、プロセス起動のたびに登録し直す。2章参照）
3. SchedulerEngine().run_due(jobs) で実行対象のSchedulerEventリストを取得する（v2.6.0、無改修）
4. 各SchedulerEventを WorkflowEngineEvent に変換する（本スクリプトの責務。5章）
5. WorkflowEngineManager.from_config(agent_config, workflow_engine_config)
     .run(event, dry_run=args.dry_run) を呼び出す
```

**Scheduler本体を無改修のまま、`SchedulerEvent`を消費できる理由**：`SchedulerEngine.evaluate()` / `run_due()`は既に「`SchedulerEvent`のリストを返すだけ」の純粋関数として設計されており（`scheduler_engine.py`のdocstring）、呼び出し元が結果を使って何をするかはScheduler側の関心事ではない。本スクリプトはその「呼び出し元」の役割を新たに担うだけであり、Scheduler側のインターフェース変更は発生しない。

**Job定義の永続化が対象外であることの影響**：v2.6.0の制約（2章）により、本スクリプトは実行のたびにJob一覧を自前で（ハードコードまたは簡易設定として）用意する前提とする。「登録されたJobが次回起動時にも残っている」という運用は、SchedulerRepositoryの永続化実装（将来Release）を待って初めて実現する。Foundation Releaseでは、Windowsタスクスケジューラ等の外部スケジューラから本スクリプトを定期的に起動する運用を想定しても、Job定義自体は起動のたびに再構築される（Charter・v2.6.0双方の既知の制約として記録するのみで、Release 2.7では解消しない）。

**責務範囲の明文化（修正必須事項#1）**：上記の制約を踏まえ、`scripts/run_workflow_engine.py`が自前で用意するJob一覧は、Foundation Releaseでは**固定・最小限（1件のデモJobのみ）**に限定する（具体的な内容は12章）。複数Jobの登録、Job定義の設定ファイル化（YAML/JSON等）、実行時の動的登録・削除といった機能は、本スクリプトの責務に含めない。これらはすべてFuture Extensions（17章）として送り、SchedulerRepositoryの永続化実装（将来Release）と合わせて再設計する。この境界を明記する理由は、本スクリプトが「Scheduler判定とWorkflow Engineを橋渡しする」という単一責務を超えて、Job管理機能そのものを肥大化させて抱え込むことを防ぐため（Architecture Review §3懸念点(E)・§4修正必須事項#1）。

---

## 11. Directory Structure

```
src/
├── ai/                                    # 無変更
├── pipeline/                              # 無変更
├── scheduler/                             # 無変更
│
└── workflow_engine/                       # 新規パッケージ
    ├── __init__.py
    ├── workflow_engine_step.py            # WorkflowEngineStep, ALL_WORKFLOW_ENGINE_STEPS
    ├── workflow_engine_definition.py      # WorkflowEngineDefinition
    ├── workflow_engine_event.py           # WorkflowEngineEvent
    ├── workflow_engine_context.py         # WorkflowEngineContext
    ├── workflow_engine_result.py          # WorkflowEngineStepResult, WorkflowEngineResult
    ├── workflow_engine_config.py          # WorkflowEngineConfig
    ├── workflow_engine_executor.py        # WorkflowEngineExecutor
    └── workflow_engine_manager.py         # WorkflowEngineManager, NullWorkflowEngineManager

scripts/
└── run_workflow_engine.py                 # Scheduler → Workflow Engine 手動実行エントリ（新規）

tests/
└── test_e2e_v2_7_0_workflow_engine_foundation.py   # 新規（実装フェーズで作成）
```

`src/ai/` / `src/pipeline/` / `src/scheduler/`配下の既存ファイルはいずれも無変更とする想定（実装フェーズで`git diff`により確認する）。

---

## 12. `scripts/run_workflow_engine.py` のCLI設計

```
使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/run_workflow_engine.py
    ./venv/Scripts/python.exe scripts/run_workflow_engine.py --dry-run
    ./venv/Scripts/python.exe scripts/run_workflow_engine.py --job-id manual-run

引数:
    --dry-run    Workflow Engine全体をdry_run実行する
                 （各ステップのAgentは decide() のみ行い、act() は呼ばれない）
    --job-id     Scheduler判定をスキップし、指定したjob_idでWorkflowEngineEventを
                 その場で合成し、直接WorkflowEngineManager.run()を呼び出す
                 （動作確認・手動起動用。SchedulerEngineの評価を経由しない）

動作の流れ（デフォルト、Scheduler経由）:
    1. SchedulerConfig.from_env() / SchedulerManager(InMemorySchedulerRepository()) を用意する
    2. 固定・最小限のデモ用SchedulerJobを1件だけ登録する
       （job_id="workflow_engine_demo_daily", trigger_type=DAILY, schedule="09:00" 固定。
       複数Job・設定ファイル化・動的登録はFuture Extensions、10章「責務範囲の明文化」参照）
    3. SchedulerEngine().run_due(jobs) で対象SchedulerEventを取得する
    4. 対象がなければ「実行対象なし」を表示して終了する
    5. 対象があれば、SchedulerEventの各フィールドをそのままコピーして
       WorkflowEngineEvent(source=SOURCE_SCHEDULER, ...) を構築し（6章の対応表）、
       WorkflowEngineManager.from_config(...).run(event, dry_run=args.dry_run) を実行する

動作の流れ（--job-id指定時、Scheduler判定を経由しない）:
    1. WorkflowEngineEvent(job_id=args.job_id, source=SOURCE_MANUAL,
       triggered_at=datetime.now(),
       trigger_reason="Manual invocation via --job-id.") を直接構築する（6章の対応表）
    2. SchedulerConfig / SchedulerManager / SchedulerEngine はいずれも呼び出さない
    3. WorkflowEngineManager.from_config(...).run(event, dry_run=args.dry_run) を実行する

前提条件（.env設定、二重ゲート）:
    AI_AGENT_ENABLED=true
    WORKFLOW_ENGINE_ENABLED=true

    加えて、Review/Publishステップを実際に動かす場合は以下も必要（7章）:
    REVIEW_TRIGGER_AGENT_ENABLED=true
    PUBLISH_TRIGGER_AGENT_ENABLED=true（+ AiPublishConfigの認証情報3点）

注意:
    - 本スクリプトは NewsAgent / ReviewTriggerAgent / PublishTriggerAgent を
      直接importしない。WorkflowEngineManager経由でのみ間接的に利用する。
    - SCHEDULER_ENABLED は本スクリプトの動作条件には含めない
      （v2.6.0のSchedulerConfigはSchedulerEngine/SchedulerManager自体の有効・無効を
      制御するものではなく将来のOS連携機能向けの設定であるため。詳細はv2.6.0設計書参照）。
    - --dry-run を指定した場合、実際のNews収集・レビューレポート生成・
      WordPress下書き投稿はいずれも行われない。
    - 本スクリプトと scripts/run_news_agent.py 等の既存Trigger Agent系scriptを
      同時に実行しないこと（13.1節「運用上の制約」参照。WordPress下書き等の二重生成リスクがある）。
```

---

## 13. Error Handling

| ケース | 対応 |
|---|---|
| `AI_AGENT_ENABLED=false` または `WORKFLOW_ENGINE_ENABLED=false`（デフォルト） | `NullWorkflowEngineManager`が返り、`run()`は何も実行せずログのみ出力する |
| `REVIEW_TRIGGER_AGENT_ENABLED=false`（デフォルト） | `REVIEW`ステップは`executed=False, success=True, skipped_reason="..."`として記録され、後続の`PUBLISH`は実行を継続する |
| `PUBLISH_TRIGGER_AGENT_ENABLED=false`（デフォルト） | 同上（`PUBLISH`ステップがスキップされる） |
| `NEWS`ステップで`AgentResult.success=False`（例外・Pipeline失敗） | `stopped_early=True`として`REVIEW` / `PUBLISH`を実行せずに打ち切る（8.3節） |
| `REVIEW`ステップで`AgentResult.success=False` | 同様に`PUBLISH`を実行せず打ち切る |
| いずれかのステップで`decide()`が`should_act=False`と判断 | 失敗ではない（`AgentResult.success=True, action_taken=False`）。後続ステップの実行を継続する |
| Scheduler側で対象`SchedulerEvent`が0件（`run_due()`が空リスト） | 「実行対象なし」を表示し、Workflow Engineは起動しない |
| `WorkflowEngineEvent`への変換に失敗（想定外の`SchedulerEvent`形式） | 本Foundation Releaseでは`SchedulerEvent`のフィールドをそのままコピーするだけのため、変換失敗は想定しない（フィールド構成が同一のため） |

### 13.1 運用上の制約：複数実行主体による重複実行リスク（修正必須事項#3）

**リスクの内容**：8.2節で採用した設計（`WorkflowEngineManager`が既存Agentを独自に再構築する「案B」）により、以下2種類の実行主体が、それぞれ独立した`NewsAgent` / `ReviewTriggerAgent` / `PublishTriggerAgent`インスタンスを持つことになる。

1. `AgentManager`経由の既存script群（`scripts/run_news_agent.py` / `scripts/run_review_trigger_agent.py` / `scripts/run_publish_trigger_agent.py`）
2. `WorkflowEngineManager`経由の新script（`scripts/run_workflow_engine.py`）

両者は同じファイルシステム状態（`outputs/`配下の各種レポートファイルのmtime）を根拠に`decide()`を行うが、**`decide()`の判断から`act()`完了（＝ファイル書き込みによるmtime更新）までの間に、いかなるロック機構も存在しない**。したがって、人間による手動script実行とWorkflow Engineの自動実行が時間的に重なった場合、両方が独立に「実行すべき」と判断し、同一のNews収集・レビューレポート生成・**WordPress下書き投稿**が二重に発生する可能性がある。特にWordPress下書きの二重投稿は、読者向けブログ運営という実運用上の実害を伴う（重複記事の公開誤操作等につながりうる）。

加えて、v2.6.0の`SchedulerEngine`は`last_run_at`（前回判定済みかどうか）を保持しない設計であるため（`scheduler_engine.py`のdocstring参照）、`scripts/run_workflow_engine.py`自体を短い間隔で複数回起動した場合も、同一分内で同じ`SchedulerEvent`が繰り返し発火し、上記の重複実行リスクをさらに増幅させる可能性がある。

**Release 2.7での対応方針**：ロック機構の実装は本Releaseの対象外とする（3章「対象外」）。かわりに、以下を**運用制約として明記する**ことで対応する。

- `scripts/run_workflow_engine.py`を稼働させる場合、`scripts/run_news_agent.py` / `scripts/run_review_trigger_agent.py` / `scripts/run_publish_trigger_agent.py` / `scripts/run_workflow_trigger_agent.py`など、`AgentManager`経由の既存script群を**同時に手動実行しないこと**を運用ルールとする
- `scripts/run_workflow_engine.py`自体も、外部スケジューラ（将来のWindowsタスクスケジューラ連携等）から**短い間隔で重複起動しないこと**を運用ルールとする（目安として、`min_interval_minutes`系の設定値より十分短い間隔での再起動は避ける）
- これらの制約は、SchedulerRepositoryの永続化・`last_run_at`によるロック相当の仕組みが将来Releaseで導入されるまでの暫定的なものであり、17章 Future Extensionsに解消条件として記録する

この扱いはDevelopment Charter 6章「技術的負債との向き合い方」（可視化されている・理由が説明できる・将来の解消タイミングを検討できる、の3条件）に従うものであり、安全性（同13章の意思決定原則で最優先とされる項目）に関わる既知のリスクを黙って進めるのではなく、明示的な運用制約として残す（Architecture Review §4修正必須事項#3）。

---

## 14. 既存Releaseへの影響範囲

| 対象 | 影響 |
|---|---|
| v1.20.0（`WorkflowRunner`・`src/ai/workflow_*.py`） | 無変更 |
| v2.0.0（Agent Foundation：`BaseAgent` / `AgentExecutor` / `AgentContext` / `AgentDecision` / `AgentResult` / `AgentConfig` / `AgentManager`） | 無変更。`WorkflowEngineManager`から`AgentExecutor` / `AgentContext`等を無改修のままimportして使うのみ |
| v2.2.0（`NewsAgent` / `NewsAgentConfig` / `NewsPipelineRunner`） | 無変更 |
| v2.3.0（`WorkflowTriggerAgent`関連） | 無変更。Workflow Engineのステップにも含めない（9章） |
| v2.4.0（`PublishTriggerAgent`関連） | 無変更 |
| v2.5.0（`ReviewTriggerAgent`関連） | 無変更 |
| v2.6.0（Scheduler関連） | 無変更。`SchedulerEvent`を読み取る呼び出し元が新設されるのみ |
| `main.py` | 無変更 |

**影響範囲のまとめ**：新規パッケージ1式（8ファイル）＋新規スクリプト1本＋新規テスト1本の追加のみ。既存パッケージ（`src/ai/` / `src/pipeline/` / `src/scheduler/`）配下のファイルは一切変更しない。

---

## 15. Testing Strategy（実装フェーズで実施予定）

### `WorkflowEngineExecutor`単体テストにおけるFake Agent戦略（修正推奨事項、Architecture Review §5-3）

`WorkflowEngineExecutor.run()`のロジック（Gate二層構造の分岐・打ち切り基準・`WorkflowEngineResult.steps`の件数保証）は、実際の`NewsAgent` / `ReviewTriggerAgent` / `PublishTriggerAgent`（ひいては`main.py`起動・WordPress API呼び出し等）を経由せずに検証できる必要がある。`SchedulerEngine`のテストが`ClockProvider`を`FakeClockProvider`に差し替えて時刻を固定するのと同じ考え方で、以下のテスト用ダブルを用意する。

- `FakeAgent(BaseAgent)`：`decide()` / `act()`の戻り値をコンストラクタ引数で固定できるテスト専用実装（`src/ai/base_agent.py`を継承するが、実装先は`tests/`配下に置き、`src/`側には追加しない）
- `FakeAgent`を`AgentExecutor`でラップしたものを`WorkflowEngineExecutor`の`step_executors`に直接注入し、以下を実Agent・実ファイルI/Oなしに検証する：
  - 全ステップ成功／News失敗による打ち切り／Gate閉鎖によるスキップ／打ち切り後の未到達記録（`REASON_NOT_REACHED`）の4パターン
  - `WorkflowEngineResult.steps`の件数が常に`len(definition.steps)`と一致すること
- `WorkflowEngineManager.from_config()`が実際の`NewsAgent`等を正しく構築できることの確認は、上記とは別に「既存クラスをそのままimportしていること」を検証する結合テスト（Architecture Guard）として分離し、`WorkflowEngineExecutor`単体のロジックテストとは独立させる

### 新規E2Eテスト（想定シナリオ）

- `WorkflowEngineConfig.from_env()`のデフォルト値・環境変数上書き・`is_ready()`判定
- `WorkflowEngineStep` / `ALL_WORKFLOW_ENGINE_STEPS`：3ステップ固定であること
- `WorkflowEngineEvent`の構築：`SchedulerEvent`経由（`source=SOURCE_SCHEDULER`）／`--job-id`経由（`source=SOURCE_MANUAL`）の2パターン（6章の対応表どおりのフィールド設定になること）
- `WorkflowEngineExecutor.run()`（上記Fake Agent戦略を用いた単体テスト）：
  - 全ステップGate閉鎖時（すべてスキップ、`overall_success=True`）
  - News成功 → Review成功 → Publish成功（全ステップ`executed=True`）
  - News失敗（`success=False`）→ Review/Publishが呼ばれず`stopped_early=True`になり、両ステップとも`skipped_reason=REASON_NOT_REACHED`として記録されること
  - News`should_act=False`（スキップ）→ Reviewは実行を継続すること（8.3節の打ち切り基準の確認）
  - Reviewステップのみ`REVIEW_TRIGGER_AGENT_ENABLED=false`でスキップ、News/Publishは実行されること
  - いずれのケースでも`WorkflowEngineResult.steps`の件数が`len(definition.steps)`と一致すること
- `WorkflowEngineManager.from_config()`の二重ゲート分岐：`AI_AGENT_ENABLED` × `WORKFLOW_ENGINE_ENABLED`の4パターン、および`NullWorkflowEngineManager`が返るケース
- `WorkflowEngineManager`が構築する`NewsAgent` / `ReviewTriggerAgent` / `PublishTriggerAgent`が、既存クラスをそのままimportして使っていること（Architecture Guard：`src/workflow_engine/`が`src/ai/` / `src/pipeline/`の既存クラス定義を改変していないことの静的検査）
- `dry_run=True`で全ステップの`act()`が呼ばれない（副作用ゼロ）ことの確認
- `scripts/run_workflow_engine.py`（実サブプロセス、常にdry-run）：スクリプト存在確認・無効時の安全終了・`--job-id`指定時の単発実行確認
- Architecture Guard：`src/scheduler/` / `src/ai/` / `src/pipeline/`配下の既存ファイルに変更がないこと（`git diff`）、`src/workflow_engine/`が`src/scheduler/`をimportしないこと（10章の設計方針の静的検査）

### 既存回帰確認（実装フェーズで実施予定）

- `tests/test_e2e_v2_0_0_ai_agent_foundation.py`
- `tests/test_e2e_v2_2_0_news_agent_foundation.py`
- `tests/test_e2e_v2_3_0_workflow_trigger_agent_foundation.py`
- `tests/test_e2e_v2_4_0_publish_trigger_agent_foundation.py`
- `tests/test_e2e_v2_5_0_review_trigger_agent_foundation.py`
- `tests/test_e2e_v2_6_0_scheduler_agent_foundation.py`
- `tests/test_e2e_v1_20_0_ai_workflow_foundation.py`

いずれも実装フェーズで実際に実行し、実測したPASS件数をCHANGELOG・本ドキュメントの更新に反映する（本ドキュメント作成時点ではまだ実装していないため、件数の記載はしない）。

---

## 16. Architecture Reviewでの確認事項（承認済み）

以下4点は、実装前にChatGPTへ確認すべき論点として本ドキュメント作成時点で挙げていたものである。2026-07-02のArchitecture Reviewにおいて、ChatGPTから該当する設計判断（Architecture Review §2「良い点」1〜7の判断）が明示的に承認されたため、Open Questionsとしては解消済みとして記録する。

1. ✅ **Gate方式の二層構造（7章）**：承認済み。Workflow Engine全体のゲート（二重）とステップごとのゲート（既存Config再利用）を分離する設計、および「News はゲートなしで常に有効」という非対称性の踏襲を承認
2. ✅ **打ち切り基準（8.3節）**：承認済み。「実行失敗のみ打ち切り、Gate閉鎖・decide()スキップは継続」という基準を承認
3. ✅ **`WorkflowTriggerAgent`を対象外とする判断（9章）**：承認済み。将来Releaseでの役割整理（`WorkflowTriggerAgent`との重複解消）は17章 Future Extensionsに記録し、Release 2.7の対象外として確定
4. ✅ **`AgentManager`を経由しない設計（8.2節）**：承認済み。構築ロジックの一部重複を許容し、既存`AgentManager` / `AgentExecutor`を完全に無改修のまま保つ案Bを採用することを承認

なお、Architecture Reviewでは上記に加えて3件の修正必須事項（12章「責務範囲の明文化」・6章「WorkflowEngineEvent構築方法」・13.1節「運用上の制約」）が指摘され、いずれも本ドキュメントへ反映済みである。

---

## 17. Future Extensions

- 条件分岐（例：Newsの収集件数によってReviewをスキップする等）：`WorkflowEngineDefinition`に条件式を追加する形を想定
- Retry（ステップ失敗時の再試行）：`WorkflowEngineExecutor`にリトライ回数・バックオフの設定を追加する形を想定。既存Agentの`decide()`結果は変えず、`act()`呼び出しのみ再試行対象にする方向で検討
- 並列実行：現在の直列モデル（News → Review → Publish）から、依存関係のないステップを並列化する拡張。`WorkflowEngineDefinition`に依存関係グラフを持たせる設計変更が必要になるため、必要性が明確になった時点で再検討する
- `WorkflowTriggerAgent`の統合（9章）：`PublishTriggerAgent`との役割重複整理後、Workflow Engineのステップとして追加するかを再検討する
- SchedulerJobの永続化（10章・v2.6.0からの既知の未対応事項）：`SchedulerRepository`の永続化実装が追加された時点で、`scripts/run_workflow_engine.py`のJob登録方式を見直す（固定1件のデモJobから、複数Job・設定ファイル化への拡張を含む）
- 複数実行主体の排他制御（13.1節）：`AgentManager`経由の既存script群と`WorkflowEngineManager`経由のscriptが同時実行された場合の重複実行を防ぐロック機構（例：ファイルロック・`last_run_at`の永続化）。SchedulerRepositoryの永続化実装と合わせて検討する
- 共通Runner Interface・共通Agent構築ロジックの抽出（8.2節）：`AgentManager.from_config()`と`WorkflowEngineManager.from_config()`の構築ロジック重複を、将来的に共通化するかどうかの検討
- 専用実行ログ基盤（例：`logs/workflow_engine/`）の追加
- `.env.example`のドキュメント負債解消（既存の複数バージョンにまたがる未対応事項、Charter §3参照）

---

## 18. Definition of Done

### コード（未着手）

- [ ] `WorkflowEngineStep` / `ALL_WORKFLOW_ENGINE_STEPS`（`src/workflow_engine/workflow_engine_step.py`）
- [ ] `WorkflowEngineDefinition`（`src/workflow_engine/workflow_engine_definition.py`）
- [ ] `WorkflowEngineEvent`（`src/workflow_engine/workflow_engine_event.py`）
- [ ] `WorkflowEngineContext`（`src/workflow_engine/workflow_engine_context.py`）
- [ ] `WorkflowEngineStepResult` / `WorkflowEngineResult`（`src/workflow_engine/workflow_engine_result.py`）
- [ ] `WorkflowEngineConfig`（`src/workflow_engine/workflow_engine_config.py`）
- [ ] `WorkflowEngineExecutor`（`src/workflow_engine/workflow_engine_executor.py`、既存`AgentExecutor`を無改修のまま呼び出す）
- [ ] `WorkflowEngineManager` / `NullWorkflowEngineManager`（`src/workflow_engine/workflow_engine_manager.py`、二重ゲート＋ステップ別ゲート）
- [ ] `src/workflow_engine/__init__.py`（新規シンボルのexport）
- [ ] `scripts/run_workflow_engine.py`（`--dry-run` / `--job-id`対応）

### テスト（未着手）

- [ ] `tests/test_e2e_v2_7_0_workflow_engine_foundation.py`
- [ ] 既存回帰確認：`v2.0.0` / `v2.2.0` / `v2.3.0` / `v2.4.0` / `v2.5.0` / `v2.6.0` / `v1.20.0`
- [ ] `dry_run=True`で全ステップの`act()`が呼ばれないことの実測確認
- [ ] Gate二層構造（Workflow Engine全体×ステップ別）の分岐確認
- [ ] 打ち切り基準（実行失敗のみ打ち切り、スキップは継続、未到達ステップの記録）の確認
- [ ] `WorkflowEngineEvent`構築方法（`SchedulerEvent`経由 / `--job-id`経由、6章の対応表）の確認
- [ ] `FakeAgent`によるテスト用ダブルを用いた`WorkflowEngineExecutor`単体テストの実装（15章）
- [ ] Architecture Guard：`src/workflow_engine/`が`src/scheduler/`をimportしないこと・`src/ai/` / `src/pipeline/` / `src/scheduler/`配下の既存ファイルが無変更であることの`git diff`確認

### ドキュメント

- [x] `docs/design/workflow_engine_foundation_charter.md`（Project Charter、作成済み）
- [x] 本設計書（Architecture Design、本タスクで作成）
- [x] Architecture Review・ChatGPTレビュー（2026-07-02完了、修正必須事項3点・修正推奨事項3点を本ドキュメントへ反映済み）
- [ ] `scripts/run_workflow_engine.py`の運用制約（13.1節：既存script群との同時実行禁止）を、実装完了後にREADME等の実行手順にも明記する
- [ ] `docs/CHANGELOG.md` / `docs/ROADMAP.md`への記載（実装完了後。v2.6.0未記載分の確認も合わせて実施）
- [ ] `docs/architecture.md`への追記（Workflow Engine層の追加。実装完了後）

### リリース

- [ ] コミット・push（実装完了・Architecture Review承認後）
