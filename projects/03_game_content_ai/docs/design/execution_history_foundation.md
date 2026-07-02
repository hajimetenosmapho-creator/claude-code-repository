# v2.8.0 Execution History Foundation 設計書

作成日：2026-07-02
状態：Architecture Design 確定。`docs/design/execution_history_foundation_charter.md`（Project Charter）を前提とする。

---

## 1. Goal

Workflow Engine（v2.7.0）が実行した各Workflowについて、「いつ・何が・どういう順序で・成功したか失敗したか」を**観測して記録するだけ**の最小基盤を、新規パッケージ`src/execution_history/`として追加する。

```
Scheduler        （判断、v2.6.0、無改修）
   ↓ SchedulerEvent
Workflow Engine    （実行、v2.7.0）─────観測─────→ Execution History（記録のみ、新規）
   ↓                                                    ↓
NewsAgent → ReviewTriggerAgent → PublishTriggerAgent   logs/execution_history/*.json
```

## 2. 本Releaseで確定する5つの原則（Charter補足指示）

以下はユーザーからCharterの補足として明示された方針であり、本設計書全体を貫く前提とする。

1. **Execution History は「実行の観測・記録」を担当する。** Workflowが何を実行したか・その結果どうだったかを、後から追える形で保存することのみが責務である
2. **Workflow Engine の実行判断・分岐・再試行判断には一切関与しない。** どのステップを実行するか（Gate判定）・どこで打ち切るか（8.3節の打ち切り基準）は、引き続き`WorkflowEngineExecutor`が単独で決定する。Execution Historyはその「結果」を受け取って記録するだけであり、実行結果を変える・実行順序に影響する・リトライを判断するようなコードは一切持たない
3. **Release 2.8 では履歴は記録専用とする。** Retry Engine・Workflow Monitor・Metrics Foundation・Dashboard Foundationは、いずれも本Releaseで保存した履歴データを将来消費する側であり、今回は実装しない（Charter 4章 Out of Scope）
4. **`workflow_engine` → `execution_history` の一方向依存を維持する。** `src/execution_history/`配下のいずれのモジュールも`src/workflow_engine/`・`src/ai/`・`src/pipeline/`・`src/scheduler/`を一切importしない。`WorkflowEngineStep`のような他パッケージの型を直接受け取らず、`str`（`step.value`）のみを受け取ることで結合を避ける
5. **無効時（`EXECUTION_HISTORY_ENABLED=false`）は no-op とし、既存Workflowの動作を変えない。** `NullExecutionHistoryManager`がすべてのメソッドを何もせず無視することで、Workflow Engine側の呼び出しコードを分岐させずに済む（`NullWorkflowEngineManager` / `NullLogManager`と同型のパターン）

---

## 3. Background

- `docs/design/workflow_engine_foundation.md`（v2.7.0）が既に「Workflow Engineの実行順序制御・打ち切り基準」を確定させており、本Releaseはこれを**一切変更しない**（4章）
- `src/logger/log_manager.py`（v1.8.0）は「`logs/`配下へJSON Lines形式で書き込み、失敗時は警告のみで処理継続する」という前例を持つ。Execution Historyもこれと同じ「観測・記録は失敗してもメイン処理を止めない」という考え方を踏襲する（Charter 9〜10章のリスク対策）
- `src/scheduler/scheduler_repository.py`（v2.6.0）は「`SchedulerRepository`（ABC）を切り、初期実装は`InMemorySchedulerRepository`のみ、将来永続化実装に差し替え可能」という設計を先例として持つ。Execution Historyも同型で`ExecutionHistoryStore`（ABC）を切り、初期実装は`JsonExecutionHistoryStore`のみとする（Charter 8章「将来的なDB化を見据え、Storeインターフェースを分ける」）

---

## 4. Scope（Charterの再掲・確定）

### 実装対象

- `src/execution_history/`：新規パッケージ（5章）
- `WorkflowEngineExecutor` / `WorkflowEngineManager`への最小限の連携コード追加（6章）
- `scripts/show_execution_history.py`：履歴確認用CLI（7章）
- `tests/test_e2e_v2_8_0_execution_history_foundation.py`：新規E2Eテスト（実装フェーズで作成。単体テスト・E2Eテストの両方をこの1ファイルにまとめる。Charterでは`tests/test_execution_history_foundation.py`という名称だったが、既存バージョン（v2.0.0〜v2.7.0）の命名規則`test_e2e_v{version}_..._foundation.py`に統一する）

### 対象外（Charter 4章のとおり）

- Retry Engine・Web Dashboard・Slack/Discord/LINE通知・DB永続化・詳細メトリクス分析・APIコスト集計・並列Workflow実行管理・履歴検索UI・履歴削除/アーカイブ機能
- `src/ai/workflow_*.py`（v1.20.0、`WorkflowRunner`の6ステップ）からの履歴記録連携：Charter 3章の対象は「Workflow Engine」（v2.7.0、News→Review→Publishの3ステップ）のみであり、`WorkflowRunner`（AI記事改善6ステップ）は含めない。両者を混同しないという既存の設計原則（`workflow_engine_foundation.md` 5章）をそのまま踏襲する

---

## 5. Data Model

### `execution_history_config.py` — `ExecutionHistoryConfig`

```python
@dataclass
class ExecutionHistoryConfig:
    enabled: bool
    history_dir: Path

    @classmethod
    def from_env(cls, project_root: Path) -> "ExecutionHistoryConfig":
        enabled = os.environ.get("EXECUTION_HISTORY_ENABLED", "true").lower() == "true"
        dir_name = os.environ.get("EXECUTION_HISTORY_DIR", "logs/execution_history")
        return cls(enabled=enabled, history_dir=project_root / dir_name)

    def is_ready(self) -> bool:
        return self.enabled
```

**デフォルト`true`である理由（`AgentConfig` / `WorkflowEngineConfig`との違い）**：Agent系のゲート（`AI_AGENT_ENABLED`等）はデフォルト`false`である。理由は「実際に外部へ作用する処理（News収集・WordPress投稿等）を安全側で止めておく」ため。一方Execution Historyは**ローカルJSONファイルへの記録のみ**で、外部API呼び出し・投稿等の副作用を一切持たない。この性質は`LOG_ENABLED`（デフォルト`true`）と同じであり、`ANALYTICS_ENABLED`（外部API連携へ発展する基盤のため意図的にデフォルト`false`、`.env.example` 64〜72行参照）とは異なる。したがって`LOG_ENABLED`と同じ「原則有効」をデフォルトとする。

### `execution_history_event.py` — `ExecutionHistoryEvent`

```python
EVENT_WORKFLOW_STARTED  = "workflow_started"
EVENT_WORKFLOW_FINISHED = "workflow_finished"
EVENT_STEP_STARTED      = "step_started"
EVENT_STEP_FINISHED     = "step_finished"

@dataclass
class ExecutionHistoryEvent:
    event_type: str
    occurred_at: datetime
    message: str
    payload: dict = field(default_factory=dict)

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> "ExecutionHistoryEvent": ...
```

`WorkflowExecutionRecord.events`に時系列で追記される、最小の構造化イベントログ。`ExecutionHistoryManager`の各メソッド（`start_run` / `start_step` / `finish_step` / `finish_run`）が呼ばれるたびに自動生成する（呼び出し側が個別にイベントを組み立てる必要はない）。

### `step_execution_record.py` — `StepExecutionRecord` / `StepExecutionStatus`

```python
class StepExecutionStatus(Enum):
    RUNNING     = "running"
    SUCCESS     = "success"
    FAILED      = "failed"
    SKIPPED     = "skipped"       # Gate閉鎖によるスキップ（失敗ではない）
    NOT_REACHED = "not_reached"   # 前段の失敗により未到達

@dataclass
class StepExecutionRecord:
    step: str                      # WorkflowEngineStep.value（"news"/"review"/"publish"）を文字列で受け取る（4章の一方向依存）
    status: StepExecutionStatus
    started_at: datetime | None = None
    finished_at: datetime | None = None
    error_message: str | None = None
    skipped_reason: str | None = None

    def to_dict(self) -> dict: ...
    @classmethod
    def from_dict(cls, data: dict) -> "StepExecutionRecord": ...
```

`WorkflowEngineStepResult`（`executed` / `success` / `skipped_reason`）から本レコードへの変換規則は6章で確定する。

### `workflow_execution_record.py` — `WorkflowExecutionRecord` / `WorkflowExecutionStatus`

```python
class WorkflowExecutionStatus(Enum):
    RUNNING = "running"
    SUCCESS = "success"
    FAILED  = "failed"

@dataclass
class WorkflowExecutionRecord:
    run_id: str
    workflow_name: str             # Foundation Releaseでは固定値 "workflow_engine"（4章）
    source: str                    # WorkflowEngineEvent.source をそのままコピー（"scheduler"/"manual"）
    job_id: str                    # WorkflowEngineEvent.job_id をそのままコピー
    status: WorkflowExecutionStatus
    started_at: datetime
    finished_at: datetime | None = None
    steps: list[StepExecutionRecord] = field(default_factory=list)
    events: list[ExecutionHistoryEvent] = field(default_factory=list)
    error_message: str | None = None

    def to_dict(self) -> dict: ...
    def to_json(self) -> str: ...
    @classmethod
    def from_dict(cls, data: dict) -> "WorkflowExecutionRecord": ...
```

`run_id`は`WorkflowEngineManager._generate_run_id()`（既存、`uuid.uuid4().hex`）が発行した値をそのまま再利用する。Execution History側で別のID体系を新設しない。

### `execution_history_store.py` — `ExecutionHistoryStore`（ABC）

```python
class ExecutionHistoryStore(ABC):
    @abstractmethod
    def save(self, record: WorkflowExecutionRecord) -> None:
        """recordをrun_idで保存する（新規・上書き両対応）。"""
    @abstractmethod
    def get(self, run_id: str) -> WorkflowExecutionRecord | None: ...
    @abstractmethod
    def list_all(self) -> list[WorkflowExecutionRecord]:
        """保存済み全recordを、started_atの新しい順で返す。"""
```

`SchedulerRepository`（v2.6.0）と同型のABC設計。`update()`を独立させず`save()`に統合している点のみ異なる（Execution Historyは「同一run_idへの複数回の上書き保存」が正常系であり、SchedulerJobのような「新規追加とその後の更新」を区別する必要がないため）。

### `json_execution_history_store.py` — `JsonExecutionHistoryStore`

```python
class JsonExecutionHistoryStore(ExecutionHistoryStore):
    def __init__(self, history_dir: Path):
        self._history_dir = history_dir

    def save(self, record: WorkflowExecutionRecord) -> None:
        # self._history_dir が存在しなければ作成する
        # {history_dir}/{run_id}.json へ record.to_dict() をJSON書き込みする
        # 書き込み失敗時（OSError）は警告を出力して処理を継続する（LogManager._append と同じ方針、Charter 10章）
        ...

    def get(self, run_id: str) -> WorkflowExecutionRecord | None:
        # {history_dir}/{run_id}.json を読み込みWorkflowExecutionRecord.from_dict()で復元する
        # ファイルが存在しない・壊れている場合はNoneを返す
        ...

    def list_all(self) -> list[WorkflowExecutionRecord]:
        # {history_dir}/*.json を全件読み込み、started_at降順でソートして返す
        # 個々のファイルの読み込みに失敗した場合はそのファイルのみスキップする
        ...
```

1実行（1 run_id）＝1 JSONファイルとする。Workflow実行中に`start_run` / `start_step` / `finish_step` / `finish_run`のたびに**同じファイルを毎回上書き保存**することで、途中でプロセスが異常終了した場合でも「RUNNINGのまま止まった記録」が残る（Charter 7章の成功条件「失敗時にも履歴が残る構成」）。

---

## 6. `execution_history_manager.py` — `ExecutionHistoryManager` / `NullExecutionHistoryManager`

```python
class ExecutionHistoryManager:
    def __init__(self, store: ExecutionHistoryStore):
        self._store = store

    @classmethod
    def from_config(cls, config: ExecutionHistoryConfig) -> "ExecutionHistoryManager | NullExecutionHistoryManager":
        if not config.is_ready():
            return NullExecutionHistoryManager()
        return cls(store=JsonExecutionHistoryStore(config.history_dir))

    def start_run(self, run_id: str, workflow_name: str, source: str, job_id: str) -> WorkflowExecutionRecord:
        """RUNNING状態のrecordを作成し、即座に保存してから返す。"""

    def start_step(self, record: WorkflowExecutionRecord, step: str) -> None:
        """StepExecutionRecord(status=RUNNING)をrecord.stepsへ追加し、再保存する。"""

    def finish_step(
        self, record: WorkflowExecutionRecord, step: str, status: StepExecutionStatus,
        error_message: str | None = None, skipped_reason: str | None = None,
    ) -> None:
        """直近のstart_step対象のStepExecutionRecordを更新（finished_at/status/error等）し、再保存する。"""

    def finish_run(
        self, record: WorkflowExecutionRecord, status: WorkflowExecutionStatus,
        error_message: str | None = None,
    ) -> None:
        """record.status/finished_atを確定し、再保存する。"""


class NullExecutionHistoryManager:
    """EXECUTION_HISTORY_ENABLED=false のときのダミー実装。すべて no-op。"""

    def start_run(self, *args, **kwargs) -> None:
        return None

    def start_step(self, *args, **kwargs) -> None:
        return None

    def finish_step(self, *args, **kwargs) -> None:
        return None

    def finish_run(self, *args, **kwargs) -> None:
        return None
```

`NullExecutionHistoryManager.start_run()`は`None`を返す。呼び出し側（`WorkflowEngineExecutor`）は戻り値を`record`という変数にそのまま束縛し、後続の`start_step` / `finish_step` / `finish_run`へ渡すだけでよい。`NullExecutionHistoryManager`側のメソッドは受け取った引数（`record=None`を含む）を一切参照せず無視するため、呼び出し側に`if`分岐を書く必要がない（原則5「無効時はno-op」の実現方法）。

### `WorkflowEngineStepResult` → `StepExecutionStatus` の変換規則

| `WorkflowEngineStepResult` | `StepExecutionStatus` |
|---|---|
| `executed=True, success=True` | `SUCCESS` |
| `executed=True, success=False` | `FAILED`（`error_message`は`AgentResult.error_message`） |
| `executed=False, success=True`（Gate閉鎖） | `SKIPPED`（`skipped_reason`をそのまま記録） |
| `executed=False, success=False`（`REASON_NOT_REACHED`） | `NOT_REACHED`（`skipped_reason=REASON_NOT_REACHED`） |

この変換は`WorkflowEngineExecutor`側で行う（7章）。`execution_history`パッケージ自身は`WorkflowEngineStepResult`という型を一切知らない（4章の一方向依存）。

---

## 7. Workflow Engineへの連携（最小限の変更）

### 7.1 変更方針

**既存の実行制御ロジック（Gate二層構造・打ち切り基準・`WorkflowEngineResult`の組み立て）は一切変更しない。** `WorkflowEngineExecutor.run()`のforループの各分岐に、`history.start_step(...)` / `history.finish_step(...)`の呼び出しを追加するのみ。戻り値・既存フィールドの意味・分岐条件はすべて現状維持する（原則2）。

### 7.2 `workflow_engine_executor.py` の変更点

```python
class WorkflowEngineExecutor:
    def __init__(
        self,
        definition: WorkflowEngineDefinition,
        step_executors: dict[WorkflowEngineStep, AgentExecutor | None],
        step_skip_reasons: dict[WorkflowEngineStep, str] | None = None,
        history_manager: "ExecutionHistoryManager | NullExecutionHistoryManager | None" = None,  # 追加（省略時はNull）
    ):
        self._definition = definition
        self._step_executors = step_executors
        self._step_skip_reasons = step_skip_reasons or {}
        self._history_manager = history_manager or NullExecutionHistoryManager()  # 追加

    def run(self, context: WorkflowEngineContext) -> WorkflowEngineResult:
        ...
        record = self._history_manager.start_run(          # 追加
            run_id=context.run_id, workflow_name="workflow_engine",
            source=context.event.source, job_id=context.event.job_id,
        )

        for step in self._definition.steps:
            if stopped_early:
                step_results.append(...)                                      # 既存のまま
                self._history_manager.finish_step(                            # 追加
                    record, step.value, StepExecutionStatus.NOT_REACHED, skipped_reason=REASON_NOT_REACHED
                )
                continue

            executor = self._step_executors.get(step)
            if executor is None:
                step_results.append(...)                                      # 既存のまま
                self._history_manager.finish_step(                            # 追加
                    record, step.value, StepExecutionStatus.SKIPPED, skipped_reason=reason
                )
                continue

            self._history_manager.start_step(record, step.value)              # 追加
            agent_result = executor.execute(agent_context)                    # 既存のまま
            step_results.append(...)                                          # 既存のまま
            if agent_result.success:
                self._history_manager.finish_step(record, step.value, StepExecutionStatus.SUCCESS)  # 追加
            else:
                self._history_manager.finish_step(                            # 追加
                    record, step.value, StepExecutionStatus.FAILED, error_message=agent_result.error_message
                )
                stopped_early = True

        ...
        overall_success = all(r.success for r in step_results)                # 既存のまま
        self._history_manager.finish_run(                                     # 追加
            record,
            WorkflowExecutionStatus.SUCCESS if overall_success else WorkflowExecutionStatus.FAILED,
        )
        return WorkflowEngineResult(...)                                      # 既存のまま
```

既存の`WorkflowEngineExecutor(definition, step_executors)`という2引数呼び出し（`tests/test_e2e_v2_7_0_workflow_engine_foundation.py`のテスト8〜14が使用）は、`history_manager`が`None`扱い（＝`NullExecutionHistoryManager()`）になるだけで、動作・戻り値は完全に既存のまま変わらない。

### 7.3 `workflow_engine_manager.py` の変更点

`WorkflowEngineManager.from_config()`の末尾、`WorkflowEngineExecutor(...)`を構築する箇所で、`ExecutionHistoryConfig.from_env(project_root=project_root)` → `ExecutionHistoryManager.from_config(...)`を呼び、`WorkflowEngineExecutor`のコンストラクタへ渡す（追加2〜3行）。呼び出し元（`scripts/run_workflow_engine.py`）のシグネチャ変更は不要。

---

## 8. `scripts/show_execution_history.py` のCLI設計

```
使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/show_execution_history.py                 # 一覧表示（新しい順）
    ./venv/Scripts/python.exe scripts/show_execution_history.py --run-id <ID>   # 指定run_idの詳細表示（steps・events含む）
    ./venv/Scripts/python.exe scripts/show_execution_history.py --limit 5       # 一覧の表示件数を制限（デフォルト10）
```

- 本スクリプトは`ExecutionHistoryConfig.from_env(project_root)`から`history_dir`のみを取得し、`JsonExecutionHistoryStore(history_dir)`を直接構築して読み取り専用で使う。`EXECUTION_HISTORY_ENABLED=false`（記録無効）の場合でも、**過去に記録済みの履歴を閲覧できる**ようにするため、`is_ready()`のチェックはスキップする（読み取りと書き込みのゲートを分離する設計判断）
- 保存済み履歴が0件の場合は「履歴がありません」と案内して正常終了する
- 指定`--run-id`が存在しない場合はエラーメッセージを表示して終了する（`sys.exit(1)`にはしない。読み取り専用ツールであるため）

---

## 9. Error Handling

| ケース | 対応 |
|---|---|
| `EXECUTION_HISTORY_ENABLED=false`（デフォルトは`true`のため明示的に設定した場合のみ） | `NullExecutionHistoryManager`が返り、記録は一切行われない。Workflow Engine本体の動作には影響しない |
| JSON書き込み失敗（ディスク容量不足・権限エラー等） | `JsonExecutionHistoryStore.save()`内で`OSError`を捕捉し、警告を出力して処理を継続する。`WorkflowEngineExecutor`側の実行は失敗させない（原則1・2、履歴記録はWorkflow本体の成否に影響してはならない） |
| 保存済みJSONファイルが壊れている（手動編集等） | `get()` / `list_all()`は該当ファイルを読み飛ばし、警告を出力する。他ファイルの読み込みには影響しない |
| Workflow実行中にプロセスが異常終了した | 直近の`start_run` / `start_step` / `finish_step`時点で保存済みのJSONファイルが残る（`status=running`のまま）。Release 2.8では「RUNNINGのまま残ったrecordを自動検知・修復する」機能は持たない（Future Extensions） |

---

## 10. Directory Structure

```
src/
├── ai/                                    # 無変更
├── pipeline/                              # 無変更
├── scheduler/                             # 無変更
├── workflow_engine/                       # 最小限の変更（7章）
│   ├── workflow_engine_executor.py        # history_manager引数の追加、finish_step/start_step呼び出しの追加
│   └── workflow_engine_manager.py         # ExecutionHistoryManager構築・DIの追加
│
└── execution_history/                     # 新規パッケージ
    ├── __init__.py
    ├── execution_history_config.py        # ExecutionHistoryConfig
    ├── execution_history_event.py         # ExecutionHistoryEvent、EVENT_*定数
    ├── step_execution_record.py           # StepExecutionRecord, StepExecutionStatus
    ├── workflow_execution_record.py       # WorkflowExecutionRecord, WorkflowExecutionStatus
    ├── execution_history_store.py         # ExecutionHistoryStore（ABC）
    ├── json_execution_history_store.py    # JsonExecutionHistoryStore
    └── execution_history_manager.py       # ExecutionHistoryManager, NullExecutionHistoryManager

scripts/
└── show_execution_history.py              # 新規（読み取り専用CLI）

tests/
└── test_e2e_v2_8_0_execution_history_foundation.py   # 新規（実装フェーズで作成）
```

---

## 11. Testing Strategy

- `ExecutionHistoryConfig.from_env()`：デフォルト`enabled=True`・環境変数上書き・`is_ready()`判定
- `ExecutionHistoryEvent` / `StepExecutionRecord` / `WorkflowExecutionRecord`：構築・`to_dict()`・`from_dict()`によるラウンドトリップ
- `JsonExecutionHistoryStore`：`save()` → `get()`で内容が一致すること、`list_all()`の新しい順ソート、存在しない`run_id`は`None`、書き込み失敗時に例外を送出せず処理を継続すること
- `ExecutionHistoryManager`：`start_run` → `start_step` → `finish_step` → `finish_run`の一連の呼び出しで、`Store`に保存された`WorkflowExecutionRecord`の`status` / `steps` / `events`が期待どおりに更新されること
- `NullExecutionHistoryManager`：全メソッドが例外を出さず`None`を返し、ファイルが一切作成されないこと
- `WorkflowEngineExecutor`統合（既存のFakeAgent戦略を再利用）：v2.7.0のテスト8〜12と同じ5シナリオ（全Gate閉鎖／全成功／News失敗による打ち切り／News decide()スキップ／ReviewのみGate閉鎖）を、`history_manager`にテスト用`ExecutionHistoryManager`（一時ディレクトリの`JsonExecutionHistoryStore`）を注入して実行し、保存された`WorkflowExecutionRecord.steps`の`status`が6章の変換規則どおりになることを確認する
- 既存`WorkflowEngineExecutor`2引数呼び出し（`history_manager`省略）が引き続き動作すること（後方互換の確認）
- `scripts/show_execution_history.py`：スクリプト存在確認、履歴0件時の安全終了、`run_workflow_engine.py --dry-run --job-id`実行後に生成された履歴を`--run-id`で表示できること
- Architecture Guard：`src/execution_history/`配下のいずれのファイルも`workflow_engine` / `ai` / `pipeline` / `scheduler`をimportしないこと（静的検査）。`src/ai/` / `src/pipeline/` / `src/scheduler/`配下の既存ファイルに変更がないこと（`git diff`。`src/workflow_engine/`は7章の変更のみ許容）

### 既存回帰確認（実装フェーズで実施）

- `tests/test_e2e_v2_7_0_workflow_engine_foundation.py`（v2.8.0の変更後も163件全PASSを確認する。Execution History連携追加により`WorkflowEngineExecutor` / `WorkflowEngineManager`の既存の入出力仕様が壊れていないことの最重要な確認対象）
- `tests/test_e2e_v2_0_0_ai_agent_foundation.py` 〜 `tests/test_e2e_v2_6_0_scheduler_agent_foundation.py`、`tests/test_e2e_v1_20_0_ai_workflow_foundation.py`

---

## 12. Future Extensions

- Workflow Monitor：`ExecutionHistoryStore.list_all()`を使った実行状況の可視化（一覧・検索）
- Retry Engine：`WorkflowExecutionRecord.status=FAILED`のrecordを起点に、失敗したステップから再実行する仕組み。Execution History自体は再実行の判断・実行を行わない（原則2）ため、別パッケージとして追加する想定
- Metrics Foundation：`steps`の`started_at`/`finished_at`差分から実行時間を集計する
- Dashboard Foundation：`list_all()`をWeb UIから参照する
- RUNNINGのまま残ったrecordの自動検知・異常終了マーキング（9章）
- `JsonExecutionHistoryStore`から`SqliteExecutionHistoryStore`等への差し替え（`ExecutionHistoryStore`のABCインターフェースを満たすクラスを追加するだけで済む設計、Charter 8章）
- 履歴の削除・アーカイブ（Charter 4章で対象外としたもの）
- `WorkflowRunner`（`src/ai/workflow_*.py`、v1.20.0）側からの履歴記録連携（4章で対象外とした理由のとおり、対象範囲の整理が前提）

---

## 13. Definition of Done

### コード（未着手）

- [ ] `ExecutionHistoryConfig`（`src/execution_history/execution_history_config.py`）
- [ ] `ExecutionHistoryEvent`（`src/execution_history/execution_history_event.py`）
- [ ] `StepExecutionRecord` / `StepExecutionStatus`（`src/execution_history/step_execution_record.py`）
- [ ] `WorkflowExecutionRecord` / `WorkflowExecutionStatus`（`src/execution_history/workflow_execution_record.py`）
- [ ] `ExecutionHistoryStore`（`src/execution_history/execution_history_store.py`）
- [ ] `JsonExecutionHistoryStore`（`src/execution_history/json_execution_history_store.py`）
- [ ] `ExecutionHistoryManager` / `NullExecutionHistoryManager`（`src/execution_history/execution_history_manager.py`）
- [ ] `src/execution_history/__init__.py`（新規シンボルのexport）
- [ ] `workflow_engine_executor.py` / `workflow_engine_manager.py`への最小連携追加（7章）
- [ ] `scripts/show_execution_history.py`

### テスト（未着手）

- [ ] `tests/test_e2e_v2_8_0_execution_history_foundation.py`
- [ ] 既存回帰確認：`v2.7.0`（最重要）・`v2.0.0`〜`v2.6.0`・`v1.20.0`
- [ ] Architecture Guard（一方向依存の静的検査・既存ファイル無変更確認）

### ドキュメント

- [x] `docs/design/execution_history_foundation_charter.md`（Project Charter、作成済み）
- [x] 本設計書（Architecture Design、本タスクで作成）
- [ ] `docs/CHANGELOG.md` / `docs/ROADMAP.md`への記載（実装完了後）
- [ ] `docs/architecture.md`への追記（Execution History層の追加。実装完了後）

### リリース

- [ ] コミット（実装完了・テストPASS後、ユーザー確認を経て実施）
- [ ] push（コミット後、別途ユーザー確認を経て実施）
