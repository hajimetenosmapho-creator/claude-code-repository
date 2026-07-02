# v2.9.0 Workflow Monitor Foundation 設計書

作成日：2026-07-02
状態：Architecture Design 確定（Architecture Review完了・指摘事項3点反映済み、2026-07-02）。`docs/design/workflow_monitor_foundation_charter.md`（Project Charter）を前提とする。

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
                                                                   ↓
                                                     scripts/show_workflow_status.py（CLI）
```

---

## 2. Charter Open Questionsの確定

Charter（`workflow_monitor_foundation_charter.md` 8章）に残された5つのOpen Questionsのうち、既存パターン（Execution History / Workflow Engineの設計判断）から本Releaseの範囲内で確定できるものを以下のとおり確定する。CANCELLED / WAITINGの判定方法は、判定対象となる元データ自体（Workflow Engine・Execution Historyの状態モデル）が現時点で存在しないため、本Releaseの範囲では確定させず引き続きOpenとする（12章 Future Extensions）。

| # | Open Question | 結論 |
|---|---|---|
| 1 | 判定の粒度 | **Workflow単位（`run_id`）のみを判定する。** `StepExecutionRecord`はExecution Historyから読み取った生データのまま`WorkflowMonitorRecord.steps`に保持し、CLI詳細表示に使う。Step単位の独自判定ロジック（`StepMonitorStatus`等）は本Releaseでは実装しない（4章） |
| 2 | `CANCELLED`の正式な判定方法 | **本Releaseでは確定させない。** Execution History側に「キャンセル」を表す状態が存在しない限り判定しようがないため、Workflow Engine／Execution Historyの拡張を伴う将来Releaseの検討事項とする（12章） |
| 3 | `WAITING`の導入タイミング | **本Releaseでは確定させない。** Schedulerにキュー機構が追加された時点で再検討する（12章） |
| 4 | 命名衝突の確認 | **確認済み・衝突なし。** `grep -r "WorkflowMonitor" src/`の結果、既存コードに`WorkflowMonitor`接頭辞のクラスは存在しない。`WorkflowEngine`（v2.7.0）・`ExecutionHistory`（v2.8.0）と同じ「パッケージ分離＋専用接頭辞」の組み合わせで安全に導入できる |
| 5 | Feature Gateの初期設定 | **デフォルト有効（`WORKFLOW_MONITOR_ENABLED=true`）とする。** 理由は3章で詳述 |

---

## 3. Scope（Charterの再掲・確定）

### 実装対象

- `src/workflow_monitor/`：新規パッケージ（4章）
- `scripts/show_workflow_status.py`：読み取り専用CLI（7章、Charterで採用確定）
- `tests/test_e2e_v2_9_0_workflow_monitor_foundation.py`：新規E2Eテスト（実装フェーズで作成）

### 対象外（Charter 3章のとおり）

Retry Engine・Auto Retry・Metrics Foundation・Dashboard Foundation・Notification/Alert・SLA判定・Distributed Monitor・Parallel Workflow Management・Execution History本体の改修・Workflow Engine本体の改修・Execution Historyへの書き込み。

### Feature Gateのデフォルト値についての判断根拠（Open Question #5）

`ExecutionHistoryConfig`（v2.8.0）がデフォルト`enabled=true`である理由は、「ローカルJSONファイルへの記録のみで、外部API呼び出し・投稿等の副作用を一切持たない」ためであった（`execution_history_config.py`のdocstring）。

Workflow Monitorはこれよりもさらに副作用が小さい。**Execution Historyへの書き込みすら行わない、純粋な読み取り＋計算のみの層**である（Charter 5.1節 Single Source of Truth）。したがって、Execution Historyと同じ「原則有効」の考え方をそのまま適用し、`WORKFLOW_MONITOR_ENABLED`のデフォルトを`true`とする。Agent系ゲート（`AI_AGENT_ENABLED`等、デフォルト`false`）とは性質が異なる（実際に外部へ作用する処理を安全側で止める必要がないため）。

---

## 4. Data Model

### `workflow_monitor_status.py` — `WorkflowMonitorStatus`

```python
class WorkflowMonitorStatus(Enum):
    RUNNING   = "running"
    SUCCESS   = "success"
    FAILED    = "failed"
    TIMEOUT   = "timeout"
    CANCELLED = "cancelled"   # 予約値。判定ロジックからは到達しない（2章 Open Question #2）
    WAITING   = "waiting"     # 予約値。判定ロジックからは到達しない（2章 Open Question #3）
```

`CANCELLED` / `WAITING`はCharter 4章の状態候補表のとおりEnumに定義するが、6章の判定ロジックはこの2値を一切返さない。テストでは「これらの値が実行時に到達しないこと」を確認する（11章）。

### `workflow_monitor_config.py` — `WorkflowMonitorConfig`

```python
@dataclass
class WorkflowMonitorConfig:
    enabled: bool
    timeout_seconds: int

    @classmethod
    def from_env(cls) -> "WorkflowMonitorConfig":
        enabled = os.environ.get("WORKFLOW_MONITOR_ENABLED", "true").lower() == "true"
        timeout_seconds = int(os.environ.get("WORKFLOW_MONITOR_TIMEOUT_SECONDS", "3600"))
        return cls(enabled=enabled, timeout_seconds=timeout_seconds)

    def is_ready(self) -> bool:
        return self.enabled
```

**`timeout_seconds`のデフォルト値（3600秒＝1時間）の根拠**：Workflow Engine（v2.7.0）が直列実行するNews→Review→Publishの3ステップは、いずれもRSS取得・Claude API呼び出し・WordPress投稿という比較的短時間で完了する処理であり、正常系で1時間を超えることは想定されない。保守的すぎない値として1時間を初期デフォルトとし、環境変数`WORKFLOW_MONITOR_TIMEOUT_SECONDS`で調整可能にする（Charter 5.2節）。

**命名の一貫性**：`_TIMEOUT_SECONDS`という命名は`AI_TIMEOUT_SECONDS`（v1.14.0）・`GA4_TIMEOUT_SECONDS`（v1.13.0）・`SEARCH_CONSOLE_TIMEOUT`（v1.12.0）と同系統の既存パターンを踏襲する。`NEWS_AGENT_TIMEOUT_SEC`（v2.2.0、`_SEC`）のみ表記が異なるが、より新しい`_TIMEOUT_SECONDS`系の命名に揃える。

`WorkflowMonitorConfig`は`project_root`や保存先パスを持たない。Execution Historyのデータをどこから読むかは`ExecutionHistoryConfig`（v2.8.0、無改修）の責務のままとし、Workflow Monitorは値を重複して持たない（Charter 5.1節 Single Source of Truthの帰結：保存先という「データの所在」もExecution History側の情報を唯一の情報源とする）。

### `workflow_monitor_record.py` — `WorkflowMonitorRecord`

```python
@dataclass
class WorkflowMonitorRecord:
    run_id: str
    workflow_name: str
    monitor_status: WorkflowMonitorStatus
    source_status: str                      # WorkflowExecutionRecord.status.value のコピー（"running"/"success"/"failed"）
    source: str                             # WorkflowExecutionRecord.source のコピー（"scheduler"/"manual"）
    job_id: str
    started_at: datetime
    finished_at: datetime | None
    elapsed_seconds: float                  # (finished_at または 現在時刻) - started_at
    reason: str | None                      # TIMEOUT判定時の根拠等（人が読める説明文）
    steps: list[StepExecutionRecord]        # Execution Historyの生データをそのまま保持（CLI詳細表示用、2章 Open Question #1）
```

`source_status`を`str`として保持する理由：`WorkflowMonitorRecord`は`workflow_monitor`パッケージの型であり、`WorkflowExecutionStatus`（`execution_history`パッケージのEnum）をそのまま公開フィールドの型にはしない。ただし`execution_history`は5章のとおりimport自体は許可されるため、内部実装では`WorkflowExecutionStatus`を扱い、`WorkflowMonitorRecord`構築時に`.value`へ変換する（Execution Historyが`WorkflowEngineStep`を`str`として受け取る設計（v2.8.0設計書4章 原則4）と対称的な配慮）。

### `workflow_monitor.py` — `WorkflowMonitor`

```python
class WorkflowMonitor:
    """ExecutionHistoryStoreを読み取り、WorkflowMonitorStatusを判定するロジック本体。"""

    def __init__(self, store: ExecutionHistoryStore, config: WorkflowMonitorConfig):
        self._store = store
        self._config = config

    def get_status(self, run_id: str) -> WorkflowMonitorRecord | None:
        """指定run_idのWorkflowMonitorRecordを返す。存在しない場合はNoneを返す。"""
        record = self._store.get(run_id)
        if record is None:
            return None
        return self._to_monitor_record(record)

    def list_status(self, limit: int | None = None) -> list[WorkflowMonitorRecord]:
        """全WorkflowExecutionRecordを判定し、started_atの新しい順で返す。"""
        records = self._store.list_all()
        monitor_records = [self._to_monitor_record(r) for r in records]
        if limit is not None:
            return monitor_records[:limit]
        return monitor_records

    def _to_monitor_record(self, record: WorkflowExecutionRecord) -> WorkflowMonitorRecord:
        monitor_status, reason = self._judge(record)
        now = datetime.now()
        elapsed = ((record.finished_at or now) - record.started_at).total_seconds()
        return WorkflowMonitorRecord(
            run_id=record.run_id,
            workflow_name=record.workflow_name,
            monitor_status=monitor_status,
            source_status=record.status.value,
            source=record.source,
            job_id=record.job_id,
            started_at=record.started_at,
            finished_at=record.finished_at,
            elapsed_seconds=elapsed,
            reason=reason,
            steps=list(record.steps),  # コピーを渡す（Architecture Review指摘事項#3。下記コラム参照）
        )

    def _judge(self, record: WorkflowExecutionRecord) -> tuple[WorkflowMonitorStatus, str | None]:
        """Charter 4章の判定方針をそのまま実装する。"""
        if record.status == WorkflowExecutionStatus.SUCCESS:
            return WorkflowMonitorStatus.SUCCESS, None
        if record.status == WorkflowExecutionStatus.FAILED:
            return WorkflowMonitorStatus.FAILED, record.error_message

        # record.status == WorkflowExecutionStatus.RUNNING
        elapsed = (datetime.now() - record.started_at).total_seconds()
        if elapsed >= self._config.timeout_seconds:
            reason = (
                f"started_at から {int(elapsed)}秒経過し、"
                f"閾値（{self._config.timeout_seconds}秒）を超過したため TIMEOUT と判定"
            )
            return WorkflowMonitorStatus.TIMEOUT, reason
        return WorkflowMonitorStatus.RUNNING, None
```

`_judge()`は`WorkflowExecutionRecord.status`（Execution Historyが確定した値）のみを入力とし、Workflow Engine側の型・内部状態には一切アクセスしない（Charter 5.1節 Single Source of Truthの直接的な実装）。`CANCELLED` / `WAITING`を返す分岐は存在しない（2章）。

---

## 5. パッケージ依存方向（一方向依存の確認）

**結論：`workflow_monitor` → `execution_history` の一方向依存とする。** `src/execution_history/`が確立した「上位層が下位層をimportし、下位層は上位層を一切知らない」というパターン（v2.8.0設計書 4章 原則4）をそのまま踏襲する。

```
src/workflow_monitor/  ─── import ───→  src/execution_history/
                                          （ExecutionHistoryStore / ExecutionHistoryConfig /
                                           JsonExecutionHistoryStore / WorkflowExecutionRecord /
                                           WorkflowExecutionStatus / StepExecutionRecord）
```

- `src/workflow_monitor/`配下のいずれのモジュールも`src/workflow_engine/` / `src/ai/` / `src/pipeline/` / `src/scheduler/`を一切importしない（`execution_history`が確立した一方向依存パターンと同じ検証をArchitecture Guardで行う、10章）
- `src/execution_history/`側は`src/workflow_monitor/`の存在を一切知らない（`execution_history`は既存のまま無改修）
- `WorkflowMonitor`は`ExecutionHistoryStore`（ABC）を受け取るため、将来Execution History側のStore実装が`JsonExecutionHistoryStore`から差し替わっても、Workflow Monitor側の変更は不要

---

## 6. `workflow_monitor_manager.py` — `WorkflowMonitorManager` / `NullWorkflowMonitorManager`

```python
class WorkflowMonitorManager:
    """Workflow Monitor全体の起動口。"""

    def __init__(self, monitor: WorkflowMonitor):
        self._monitor = monitor

    @classmethod
    def from_config(
        cls,
        execution_history_config: ExecutionHistoryConfig,
        workflow_monitor_config: WorkflowMonitorConfig,
    ) -> "WorkflowMonitorManager | NullWorkflowMonitorManager":
        """
        ExecutionHistoryConfig と WorkflowMonitorConfig から WorkflowMonitorManager を構築する。

        WORKFLOW_MONITOR_ENABLED が false の場合は NullWorkflowMonitorManager を返す。
        Execution History自体が無効（EXECUTION_HISTORY_ENABLED=false）であっても、
        過去に記録済みのJSONファイルが history_dir に残っていれば読み取れるため、
        ここでは execution_history_config.is_ready() をチェックしない
        （show_execution_history.py と同じ「読み取りと書き込みのゲート分離」の考え方、7章）。
        """
        if not workflow_monitor_config.is_ready():
            return NullWorkflowMonitorManager()

        store = JsonExecutionHistoryStore(execution_history_config.history_dir)
        monitor = WorkflowMonitor(store=store, config=workflow_monitor_config)
        return cls(monitor=monitor)

    def get_status(self, run_id: str) -> WorkflowMonitorRecord | None:
        return self._monitor.get_status(run_id)

    def list_status(self, limit: int | None = None) -> list[WorkflowMonitorRecord]:
        return self._monitor.list_status(limit=limit)


class NullWorkflowMonitorManager:
    """WORKFLOW_MONITOR_ENABLED=false のときのダミー実装。すべて no-op。"""

    def get_status(self, run_id: str) -> None:
        return None

    def list_status(self, limit: int | None = None) -> list:
        return []
```

`WorkflowEngineManager` / `ExecutionHistoryManager`と同型のManager／Nullペアパターンを踏襲する。

---

## 7. `scripts/show_workflow_status.py` のCLI設計

```
使い方:
    cd projects/03_game_content_ai
    ./venv/Scripts/python.exe scripts/show_workflow_status.py                 # 一覧表示（新しい順）
    ./venv/Scripts/python.exe scripts/show_workflow_status.py --run-id <ID>   # 指定run_idの詳細表示（steps含む）
    ./venv/Scripts/python.exe scripts/show_workflow_status.py --limit 5       # 一覧の表示件数を制限（デフォルト10）
```

- 本スクリプトは`ExecutionHistoryConfig.from_env(project_root)`から`history_dir`を取得し、`WorkflowMonitorConfig.from_env()`とあわせて`WorkflowMonitor`を直接構築して使う。`show_execution_history.py`（v2.8.0）と同じく、**Feature Gate（`WORKFLOW_MONITOR_ENABLED`）のチェックをスキップし、`is_ready()`に関わらず常に判定結果を表示する**（読み取り専用CLIであり、副作用が一切ないため。7章）
- 一覧表示では、`run_id` / `monitor_status`（`source_status`との対比） / `source` / `job_id` / `elapsed_seconds` / `started_at` / `finished_at`を表示する。`TIMEOUT`判定の場合は`reason`もあわせて表示する
- 詳細表示（`--run-id`指定時）では、上記に加えて`steps`（`show_execution_history.py`と同じ形式）を表示する
- 保存済み履歴が0件の場合は「履歴がありません」と案内して正常終了する
- 指定`--run-id`が存在しない場合はエラーメッセージを表示して終了する（`sys.exit(1)`にはしない。読み取り専用ツールであるため、`show_execution_history.py`と同じ方針）

---

## 8. Error Handling

| ケース | 対応 |
|---|---|
| `WORKFLOW_MONITOR_ENABLED=false`（デフォルトは`true`のため明示的に設定した場合のみ） | `WorkflowMonitorManager.from_config()`が`NullWorkflowMonitorManager`を返す。プログラムから`WorkflowMonitorManager`経由で利用する将来の呼び出し元（Retry Engine等）には影響するが、CLI（`show_workflow_status.py`）はゲートを経由せず常に動作する（7章） |
| `logs/execution_history/`配下に保存済みJSONが存在しない | `list_status()`は空リストを返す。`get_status(run_id)`は該当run_idがなければ`None`を返す（`ExecutionHistoryStore.get()`の既存契約をそのまま継承） |
| 保存済みJSONファイルが壊れている | `JsonExecutionHistoryStore`（無改修）が該当ファイルを読み飛ばし警告を出力する（v2.8.0の既存動作のまま）。Workflow Monitor側で追加のエラーハンドリングは行わない |
| `WorkflowExecutionRecord.status == RUNNING`のまま`started_at`が未来時刻（時計のずれ等、通常発生しない） | `elapsed`が負値になり得るが、`elapsed >= timeout_seconds`の判定は`False`側に倒れるため`RUNNING`と判定される（安全側）。本Releaseでは追加のバリデーションは行わない（Foundation Releaseとして必要最小限の判定のみ） |

---

## 9. Directory Structure

```
src/
├── ai/                                    # 無変更
├── pipeline/                              # 無変更
├── scheduler/                             # 無変更
├── workflow_engine/                       # 無変更
├── execution_history/                     # 無変更（読み取られる側）
│
└── workflow_monitor/                      # 新規パッケージ
    ├── __init__.py
    ├── workflow_monitor_status.py         # WorkflowMonitorStatus
    ├── workflow_monitor_config.py         # WorkflowMonitorConfig
    ├── workflow_monitor_record.py         # WorkflowMonitorRecord
    ├── workflow_monitor.py                # WorkflowMonitor
    └── workflow_monitor_manager.py        # WorkflowMonitorManager, NullWorkflowMonitorManager

scripts/
└── show_workflow_status.py                # 新規（読み取り専用CLI）

tests/
└── test_e2e_v2_9_0_workflow_monitor_foundation.py   # 新規（実装フェーズで作成）
```

---

## 10. Testing Strategy

- `WorkflowMonitorConfig.from_env()`：デフォルト`enabled=True`・`timeout_seconds=3600`・環境変数上書き・`is_ready()`判定
- `WorkflowMonitorStatus`：6値（`RUNNING`/`SUCCESS`/`FAILED`/`TIMEOUT`/`CANCELLED`/`WAITING`）が定義されていること
- `WorkflowMonitorRecord`：構築・フィールドの整合性
- `WorkflowMonitor._judge()`（単体テスト、`ExecutionHistoryStore`のFakeまたは一時ディレクトリの`JsonExecutionHistoryStore`を使用）：
  - `WorkflowExecutionStatus.SUCCESS` → `WorkflowMonitorStatus.SUCCESS`
  - `WorkflowExecutionStatus.FAILED` → `WorkflowMonitorStatus.FAILED`（`reason`に`error_message`が入ること）
  - `WorkflowExecutionStatus.RUNNING`かつ`timeout_seconds`未経過 → `WorkflowMonitorStatus.RUNNING`
  - `WorkflowExecutionStatus.RUNNING`かつ`timeout_seconds`経過済み → `WorkflowMonitorStatus.TIMEOUT`（`reason`に経過秒数・閾値が含まれること）
  - `CANCELLED` / `WAITING`がいずれの入力パターンでも返らないこと（全網羅的な分岐確認）
- `WorkflowMonitor.get_status()` / `list_status()`：`ExecutionHistoryStore.get()` / `list_all()`の結果をそのまま`WorkflowMonitorRecord`へ変換していること、`list_status(limit=N)`の件数制限
- `WorkflowMonitorManager.from_config()`：ゲート分岐（`WORKFLOW_MONITOR_ENABLED`のtrue/false）、`NullWorkflowMonitorManager`が返るケースで全メソッドが例外を出さないこと
- **書き込みが発生しないことの確認（Charter 7章 成功条件）**：`WorkflowMonitor`実行前後で`logs/execution_history/`配下のJSONファイルのmtimeが変化しないこと
- `scripts/show_workflow_status.py`：スクリプト存在確認、履歴0件時の安全終了、`show_execution_history.py`と同様のフローで生成した履歴を`--run-id`で表示できること、`WORKFLOW_MONITOR_ENABLED=false`でもCLIが動作すること（7章のゲート分離方針の確認）
- Architecture Guard：`src/workflow_monitor/`配下のいずれのファイルも`workflow_engine` / `ai` / `pipeline` / `scheduler`をimportしないこと（静的検査、`test_e2e_v2_8_0_execution_history_foundation.py`のテスト26と同型）。`src/execution_history/`配下の既存ファイルに変更がないこと（`git diff`）

### 既存回帰確認（実装フェーズで実施）

- `tests/test_e2e_v2_8_0_execution_history_foundation.py`（最重要。Workflow Monitor追加により`ExecutionHistoryStore` / `JsonExecutionHistoryStore`等の既存入出力仕様が壊れていないことの確認。ただし本Releaseでは`execution_history`パッケージ自体は無改修のため、通常は影響がないはずである）
- `tests/test_e2e_v2_7_0_workflow_engine_foundation.py`〜`tests/test_e2e_v2_0_0_ai_agent_foundation.py`、`tests/test_e2e_v1_20_0_ai_workflow_foundation.py`

---

## 11. Architecture Review所見（確認事項）

2026-07-02、本ドキュメントのドラフト版に対してArchitecture Reviewを実施した。指摘事項3点は本ドキュメントへ反映済みである。

1. ✅ **`steps`フィールドのコピー渡し（反映済み、4章）**：`WorkflowMonitorRecord.steps`に`WorkflowExecutionRecord.steps`のリスト参照をそのまま渡すと、Workflow Monitor側で意図せず元のリストを変更した場合にExecution History側のデータへ影響してしまう可能性があった。読み取り専用（Charter 5.1節 Single Source of Truth）という設計意図を実装レベルでも明確にするため、`list(record.steps)`でコピーを渡す方針に修正した
2. ✅ **時刻取得方式の確定（`ClockProvider`は導入しない）**：`SchedulerEngine`（v2.6.0）は`ClockProvider` / `FakeClockProvider`による時刻注入の仕組みを持つが、`WorkflowMonitor._judge()`ではこれを導入せず、`datetime.now()`を直接呼び出す方式のまま確定する。理由：TIMEOUT判定のテストは「`started_at`を`timeout_seconds`より過去の時刻に設定したレコードを用意する」ことで、時刻注入なしでも十分再現可能である。`ClockProvider`相当の抽象化は、Foundation Releaseの最小主義（Development Charter 8章「抽象化は必要になってから行う」）に照らして必要性が低いと判断し、見送る
3. ✅ **`WorkflowMonitorManager`の呼び出し元が本Release時点で存在しないことの明記**：`scripts/show_workflow_status.py`（7章）は`WorkflowMonitorManager`を経由せず、`WorkflowMonitor`を直接構築して使う設計とした（Gate判定をバイパスし常に読み取れるようにするため）。したがって本Release時点では`WorkflowMonitorManager` / `NullWorkflowMonitorManager`はテスト以外の実呼び出し元を持たない。これは、v2.0.0（AI Agent Foundation）の`AgentManager`が`executors=[]`のまま先行してリリースされ、後続Releaseで具体的なAgentが追加された前例と同型の「Foundation層を先に確立し、消費者は後続Releaseで追加する」パターンであり、設計上問題ないと判断した。将来のRetry Engine等が`WorkflowMonitorManager.from_config()`を呼び出す最初の消費者になる想定（12章 Future Extensions）

---

## 12. Future Extensions

- Step単位の監視状態（2章 Open Question #1）：`StepMonitorStatus`のような専用の判定ロジックを設ける
- `CANCELLED`の実判定（2章 Open Question #2）：Workflow Engine側にキャンセル機構が追加された時点で、Execution Historyのデータモデル拡張とあわせて設計する
- `WAITING`の実判定（2章 Open Question #3）：Schedulerにキュー機構が追加された時点で設計する
- Retry Engine：`WorkflowMonitorStatus.FAILED` / `TIMEOUT`のRecordを起点に再実行を判断する仕組み。Workflow Monitor自体は再実行の判断・実行を行わない（Charter 6章 Non Goal）ため、別パッケージとして追加する想定
- Metrics Foundation：`elapsed_seconds`の集計・統計処理
- Dashboard Foundation：`list_status()`をWeb UIから参照する
- Notification / Alert：`TIMEOUT` / `FAILED`検知時のSlack / Discord / LINE通知
- 複数`WorkflowMonitorConfig`利用箇所（将来のRetry Engine等）が同じ`timeout_seconds`を参照する設計（Charter 5.2節で明示した意図）の実現

---

## 13. Definition of Done

### コード（未着手）

- [ ] `WorkflowMonitorStatus`（`src/workflow_monitor/workflow_monitor_status.py`）
- [ ] `WorkflowMonitorConfig`（`src/workflow_monitor/workflow_monitor_config.py`）
- [ ] `WorkflowMonitorRecord`（`src/workflow_monitor/workflow_monitor_record.py`）
- [ ] `WorkflowMonitor`（`src/workflow_monitor/workflow_monitor.py`）
- [ ] `WorkflowMonitorManager` / `NullWorkflowMonitorManager`（`src/workflow_monitor/workflow_monitor_manager.py`）
- [ ] `src/workflow_monitor/__init__.py`（新規シンボルのexport）
- [ ] `scripts/show_workflow_status.py`

### テスト（未着手）

- [ ] `tests/test_e2e_v2_9_0_workflow_monitor_foundation.py`
- [ ] 既存回帰確認：`v2.8.0`（最重要）・`v2.0.0`〜`v2.7.0`・`v1.20.0`
- [ ] Architecture Guard（一方向依存の静的検査・既存ファイル無変更確認・書き込み非発生確認）

### ドキュメント

- [x] `docs/design/workflow_monitor_foundation_charter.md`（Project Charter、修正済み）
- [x] 本設計書（Architecture Design、本タスクで作成）
- [x] Architecture Review（2026-07-02完了、指摘事項3点を本ドキュメントへ反映済み、11章）
- [ ] `docs/CHANGELOG.md` / `docs/ROADMAP.md`への記載（実装完了後）
- [ ] `docs/architecture.md`への追記（Workflow Monitor層の追加。実装完了後）

### リリース

- [ ] コミット（実装完了・テストPASS後、ユーザー確認を経て実施）
- [ ] push（コミット後、別途ユーザー確認を経て実施）
