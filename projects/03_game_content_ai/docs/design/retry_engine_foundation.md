# v3.0.0 Retry Engine Foundation 設計書

作成日：2026-07-02（Architecture Review反映：2026-07-02）
状態：Architecture Review完了（**Approve with Minor Recommendations**）。指摘事項4点を本ドキュメントへ反映済み。`docs/design/retry_engine_foundation_charter.md`（Project Charter）を前提とする。

> **Architecture Review 反映事項（2026-07-02）**：Architecture Reviewの結果、以下4点の軽微な改善を本ドキュメントへ反映した。重大な設計変更は伴わない。
> 1. Future Extensionsに `RetryDecision`（Retry可否判定を専用コンポーネントへ分離する将来拡張）を追加（11章）
> 2. Future Extensionsに `RetryReason`（Retry判定理由をEnum化する将来拡張）を追加（11章）
> 3. `RetryPolicy` が将来 Strategy Pattern（`FixedRetryPolicy` / `ExponentialBackoffPolicy` /
>    `AdaptiveRetryPolicy`）を採用できる構造であることを明記（10章 Design Decision #11）
> 4. `RetryExecutor` の責務を「`WorkflowEngineManager` の公開APIを呼び出すだけの薄いコンポーネント」に明確化し、Retry可否判定・`RetryPolicy`適用・`RetryRequest`生成を `RetryManager` に一本化（5章・6章・8章・9章・10章 Design Decision #10・12章を更新）
>
> あわせて `docs/design/retry_engine_foundation_charter.md`（Project Charter）を新規作成した。本ドキュメントとの内容整合を確認済み。

---

## 1. Background

- `docs/design/workflow_monitor_foundation.md`（v2.9.0）により、Workflowの実行状態を
  **Read Only・Stateless**に判定する基盤（Workflow Monitor）が確立した。Workflow Monitorは
  Execution History（v2.8.0）を Single Source of Truth とし、`RUNNING` / `SUCCESS` /
  `FAILED` / `TIMEOUT` の4状態を判定できる（`CANCELLED` / `WAITING` は将来拡張用の予約値、
  同設計書2章）。
- しかし、Workflowが `FAILED` または `TIMEOUT` と判定された場合に、それを検知して
  再実行する仕組みはまだ存在しない。運用者が `scripts/run_workflow_engine.py --job-id ...`
  を手動で再実行する以外に手段がなく、「半自律的なブログ運営支援」（`docs/ROADMAP.md`
  長期ビジョン）の実現には次の一歩（自動再実行）が必要である。
- 本Release（v3.0.0）は、この最後のギャップを埋める **Retry Engine Foundation**
  （新規パッケージ `src/retry_engine/`）を追加する。Release 2.6〜2.9が確立した
  「Foundation First・Single Responsibility・一方向依存・既存モジュール無改修」の
  設計思想をそのまま継承する。
- 先例：
  - `workflow_monitor` → `execution_history` の一方向依存（v2.9.0設計書5章）
  - `WorkflowEngineManager.run(event)` が Workflow Engine全体の唯一の公開エントリポイント
    であり、内部の `WorkflowEngineExecutor` は呼び出し元から一切見えない（`workflow_engine_manager.py`）
  - `WorkflowMonitorManager.get_status(run_id)` / `list_status(limit)` が Workflow Monitor
    の唯一の公開エントリポイントであり、内部の `WorkflowMonitor._judge()` は呼び出し元から
    一切見えない（`workflow_monitor_manager.py`）
  - Manager／Nullペアパターン（`AgentManager`〜`WorkflowMonitorManager`まで全Releaseで踏襲）

---

## 2. Goals

本Releaseで確立する Retry Engine Foundation は、次のことだけを行う。

1. 指定された `run_id` の現在の状態を **Workflow Monitor の公開APIを通じて** 読み取る
   （Execution History は直接解釈しない）。
2. その状態が `RetryPolicy` の再実行対象（`FAILED` / `TIMEOUT`）に該当し、かつ再試行回数が
   上限内であれば、**`WorkflowEngineManager` の公開API（`run()`）を通じて** 再実行を依頼する
   （`WorkflowEngineExecutor` 等の内部実装には一切触れない）。
3. 再実行の結果（`RetryResult`）を呼び出し元に返す。

Retry Engine 自身は次のことを **行わない**（Non Goal。詳細は
`docs/design/retry_engine_foundation_charter.md` 8章 Non-Goals・4章 対象外を参照）。

- Workflowの状態を自ら保持・キャッシュしない（Stateless。判定は毎回 Workflow Monitor に問い合わせる）
- Execution History のJSONファイルやレコード構造を直接読み書きしない
- `WorkflowEngineExecutor` ・ステップ単位の実行制御・Gate判定には一切関与しない
- 再試行のスケジューリング・キューイング・優先度付けは行わない（Retry Queue / Priority Queueは対象外）
- 失敗の原因分類・バックオフ・通知・メトリクス集計・再試行履歴の永続化は行わない

---

## 3. Architecture Overview

```
Scheduler        （判断、v2.6.0、無改修）
   ↓ SchedulerEvent
Workflow Engine    （実行、v2.7.0、無改修）─────観測─────→ Execution History（記録、v2.8.0、無改修）
   ↓          ▲                                                  ↓
NewsAgent → ReviewTriggerAgent → PublishTriggerAgent      logs/execution_history/*.json
   ↓          │                                                  ↓ 読み取り専用
（既存Agent群、無改修）                                    Workflow Monitor（状態判定、v2.9.0、無改修）
              │                                                  ↓ 公開API（get_status / list_status）
              │                                           Retry Engine（再実行判断・依頼、新規）
              └──────────────── 公開API（run） ─────────────────┘
```

Retry Engine は「Workflow Monitor から読む」→「Workflow Engine へ書く（再実行を依頼する）」
という2方向の依存を持つ、**合成の最上位層**として位置づけられる。図の下段が上段へ戻る矢印を
持つように見えるが、これは実行時の制御フロー（再実行がまた新しい `run_id` として
Execution History に記録され、Workflow Monitor から観測可能になる）であり、
**パッケージ間の import 依存としては循環していない**（7章 Dependency Diagram）。
Retry Engine が再実行した結果は、既存の観測パイプライン（Workflow Engine → Execution
History → Workflow Monitor）にそのまま乗るだけであり、Retry Engine 専用の記録経路は
持たない（Single Source of Truthの維持）。

---

## 4. Package Structure

```
src/retry_engine/
├── __init__.py             # 公開シンボルのexport（6章）
├── retry_policy.py         # RetryPolicy（再実行対象の判定基準。env非依存の純粋な業務ルール）
├── retry_config.py         # RetryConfig（RETRY_ENGINE_ENABLED、Feature Gate）
├── retry_request.py        # RetryRequest（1回の再実行依頼を表す入力データ）
├── retry_result.py         # RetryResult, RetryOutcome（再実行試行の結果を表す出力データ）
├── retry_executor.py       # RetryExecutor（Policy判定 → WorkflowEngineManager.run()呼び出し）
└── retry_manager.py        # RetryManager, NullRetryManager（起動口。Gate・DI・Read Before Retry）
```

既存パッケージ（`src/workflow_engine/` / `src/workflow_monitor/` / `src/execution_history/` /
`src/ai/` / `src/pipeline/` / `src/scheduler/`）への変更は **一切行わない**（10章 Design
Decision #4で詳述する1点を除き、ゼロ改修を徹底する）。

---

## 5. Component Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryPolicy` | 「どの `WorkflowMonitorStatus` が再実行対象か」「最大何回まで再実行するか」という**業務ルール**を保持し、`should_retry()` で判定する。envに依存しない純粋なデータ＋ロジック（`WorkflowEngineDefinition`と同型） | 実際の再実行の実行・状態の読み取り |
| `RetryConfig` | Retry Engine全体のFeature Gate（`RETRY_ENGINE_ENABLED`）のみを保持する（`WorkflowEngineConfig`と同型） | 再実行の対象条件（それは`RetryPolicy`の責務） |
| `RetryRequest` | 1回の再実行試行に必要な入力（`run_id` / `attempt` / `requested_at` / `dry_run` / `reason`）を保持する不変データ | 状態判定・実行 |
| `RetryResult` / `RetryOutcome` | 1回の再実行試行の結果（実行したか・スキップしたか・見つからなかったか・無効化されていたか）を保持する不変データ | 結果の永続化・集計 |
| `RetryExecutor` | `RetryRequest` と `WorkflowMonitorRecord` を `WorkflowEngineEvent` に変換し、`WorkflowEngineManager.run()` を呼び出して `RetryResult` を組み立てる、**`WorkflowEngineManager` の公開APIを呼び出すだけの薄いコンポーネント**（10章 Design Decision #10） | Retry可否判定（`RetryPolicy`の適用）・`RetryRequest`の生成・`run_id`の状態取得（いずれも`RetryManager`の責務） |
| `RetryManager` / `NullRetryManager` | Retry Engine全体の起動口。Feature Gateのチェック、`WorkflowMonitorManager` から最新状態を**都度取得**（Read Before Retry、10章 Design Decision #9）、`RetryPolicy` の適用（再実行可否判定）、`RetryRequest` の生成、`RetryExecutor` への委譲を行う | `WorkflowEngineEvent` の組み立て・`WorkflowEngineManager.run()` の直接呼び出し（いずれも`RetryExecutor`に委譲） |

---

## 6. Public API

### `retry_policy.py`

```python
@dataclass(frozen=True)
class RetryPolicy:
    target_statuses: frozenset[WorkflowMonitorStatus]
    max_attempts: int

    @classmethod
    def from_env(cls) -> "RetryPolicy":
        max_attempts = int(os.environ.get("RETRY_MAX_ATTEMPTS", "3"))
        return cls(
            target_statuses=frozenset({WorkflowMonitorStatus.FAILED, WorkflowMonitorStatus.TIMEOUT}),
            max_attempts=max_attempts,
        )

    def should_retry(self, monitor_status: WorkflowMonitorStatus, attempt: int) -> bool:
        return monitor_status in self.target_statuses and attempt < self.max_attempts
```

`target_statuses` は Charter の要求（「`FAILED` または `TIMEOUT` となった場合に再実行」）に
従い固定値とし、環境変数では変更不可とする。ステータスごとに異なる再試行方針を持たせる
ことは Failure Classification（対象外）に該当するため、本Releaseでは行わない。
`max_attempts` のみ `RETRY_MAX_ATTEMPTS`（デフォルト3）で調整可能とする。

### `retry_config.py`

```python
@dataclass
class RetryConfig:
    enabled: bool

    @classmethod
    def from_env(cls) -> "RetryConfig":
        enabled = os.environ.get("RETRY_ENGINE_ENABLED", "false").lower() == "true"
        return cls(enabled=enabled)

    def is_ready(self) -> bool:
        return self.enabled
```

デフォルト `false` の根拠：Retry Engine は Execution History / Workflow Monitor と異なり
**実際に Workflow を再実行する**（News収集・WordPress下書き投稿などの外部副作用を
再度発生させうる）。この性質は `AI_AGENT_ENABLED` / `WORKFLOW_ENGINE_ENABLED`
（いずれもデフォルト`false`）と同じであり、`EXECUTION_HISTORY_ENABLED` /
`WORKFLOW_MONITOR_ENABLED`（読み取り専用のためデフォルト`true`）とは性質が異なる。

### `retry_request.py`

```python
@dataclass(frozen=True)
class RetryRequest:
    run_id: str
    attempt: int
    requested_at: datetime
    dry_run: bool = False
    reason: str | None = None
```

`attempt` は呼び出し元が指定する（Retry Engineが自ら過去の再試行回数を数えることはしない。
10章 Design Decision #6）。

### `retry_result.py`

```python
class RetryOutcome(Enum):
    RETRIED   = "retried"     # WorkflowEngineManager.run()を呼び出し、再実行した
    SKIPPED   = "skipped"     # 再実行対象外（状態不一致 or 上限到達）
    NOT_FOUND = "not_found"   # run_idがWorkflow Monitorに存在しない
    DISABLED  = "disabled"    # RETRY_ENGINE_ENABLED=false、または下位ゲートが閉じている

@dataclass(frozen=True)
class RetryResult:
    original_run_id: str
    outcome: RetryOutcome
    attempt: int
    monitor_status: WorkflowMonitorStatus | None
    reason: str | None
    workflow_engine_result: WorkflowEngineResult | None
```

`workflow_engine_result` は `outcome == RETRIED` の場合のみ値を持つ。`WorkflowEngineManager.run()`
の戻り値（`overall_success` / `steps` / `warnings` 等）をそのまま透過的に返すことで、
呼び出し元は再実行の成否をこの1回の同期呼び出しの中だけで把握できる（10章 Design
Decision #5）。

### `retry_executor.py`

```python
class RetryExecutor:
    """
    WorkflowEngineManagerの公開APIを呼び出すだけの薄いコンポーネント。

    再実行の可否判定（RetryPolicyの適用）・RetryRequestの生成はRetryManagerの責務であり、
    RetryExecutorはRetryManagerによってすでに「再実行する」と判定されたRetryRequestのみを
    受け取る。ここでの唯一の仕事は、RetryRequest/WorkflowMonitorRecordをWorkflowEngineEvent
    へ変換してWorkflowEngineManager.run()を呼び出し、戻り値をRetryResultへ詰め替えて
    返すことだけである（10章 Design Decision #10）。
    """

    def __init__(self, workflow_engine_manager: WorkflowEngineManager):
        self._engine = workflow_engine_manager

    def execute(self, request: RetryRequest, record: WorkflowMonitorRecord) -> RetryResult:
        event = WorkflowEngineEvent(
            job_id=record.job_id,
            source=SOURCE_MANUAL,
            triggered_at=request.requested_at,
            trigger_reason=(
                f"Retry of run_id={request.run_id} "
                f"(monitor_status={record.monitor_status.value}, attempt={request.attempt})."
            ),
            metadata={"retried_from": request.run_id, "attempt": request.attempt},
        )
        engine_result = self._engine.run(event, dry_run=request.dry_run)
        return RetryResult(
            original_run_id=request.run_id,
            outcome=RetryOutcome.RETRIED,
            attempt=request.attempt,
            monitor_status=record.monitor_status,
            reason=None,
            workflow_engine_result=engine_result,
        )
```

`RetryExecutor`は`RetryPolicy`を一切参照しない（コンストラクタに`policy`引数を持たない）。
`execute()`が呼ばれた時点で「再実行してよい」という判定はすでに`RetryManager`側で完了して
いる前提に立つ。`source=SOURCE_MANUAL`を再利用する理由は10章 Design Decision #4 を参照。

### `retry_manager.py`

```python
class RetryManager:
    """
    Retry Engine全体の起動口。

    Retry可否判定（RetryPolicyの適用）とRetryRequestの生成はここで行い、
    RetryExecutorには「再実行する」と決まった依頼だけを渡す（10章 Design Decision #10）。
    """

    def __init__(self, policy: RetryPolicy, executor: RetryExecutor, monitor: WorkflowMonitorManager):
        self._policy = policy
        self._executor = executor
        self._monitor = monitor

    @classmethod
    def from_config(
        cls,
        retry_config: RetryConfig,
        retry_policy: RetryPolicy,
        workflow_engine_manager: "WorkflowEngineManager | NullWorkflowEngineManager",
        workflow_monitor_manager: "WorkflowMonitorManager | NullWorkflowMonitorManager",
    ) -> "RetryManager | NullRetryManager":
        """
        呼び出し元が構築済みの WorkflowEngineManager / WorkflowMonitorManager を
        Dependency Injection で受け取る（Configから再構築しない。10章 Design Decision #3）。

        RETRY_ENGINE_ENABLED が false、または workflow_engine_manager が
        NullWorkflowEngineManager（下位ゲートが閉じている）の場合は NullRetryManager を返す。
        """
        if not retry_config.is_ready():
            return NullRetryManager()
        if isinstance(workflow_engine_manager, NullWorkflowEngineManager):
            return NullRetryManager()

        executor = RetryExecutor(workflow_engine_manager=workflow_engine_manager)
        return cls(policy=retry_policy, executor=executor, monitor=workflow_monitor_manager)

    def retry(self, run_id: str, attempt: int = 1, dry_run: bool = False) -> RetryResult:
        """
        run_idの現在の状態をWorkflow Monitorから都度読み取り（Read Before Retry、
        10章 Design Decision #9）、RetryPolicyを適用して再実行可否を判定し、対象であれば
        RetryRequestを生成してRetryExecutorへ委譲する。dry_runはそのままRetryRequest.dry_run
        へ渡される（10章 Design Decision #12）。
        """
        record = self._monitor.get_status(run_id)
        if record is None:
            return RetryResult(
                original_run_id=run_id, outcome=RetryOutcome.NOT_FOUND, attempt=attempt,
                monitor_status=None, reason=f"run_id={run_id} was not found in Workflow Monitor.",
                workflow_engine_result=None,
            )

        if not self._policy.should_retry(record.monitor_status, attempt):
            return RetryResult(
                original_run_id=run_id, outcome=RetryOutcome.SKIPPED, attempt=attempt,
                monitor_status=record.monitor_status,
                reason=self._skip_reason(record.monitor_status, attempt),
                workflow_engine_result=None,
            )

        request = RetryRequest(run_id=run_id, attempt=attempt, requested_at=datetime.now(), dry_run=dry_run)
        return self._executor.execute(request, record)

    def _skip_reason(self, monitor_status: WorkflowMonitorStatus, attempt: int) -> str:
        if monitor_status not in self._policy.target_statuses:
            return (
                f"monitor_status={monitor_status.value} is not a retry target "
                f"({sorted(s.value for s in self._policy.target_statuses)})."
            )
        return f"attempt {attempt} has reached max_attempts={self._policy.max_attempts}."


class NullRetryManager:
    """RETRY_ENGINE_ENABLED=false（デフォルト）、または下位ゲートが閉じている場合のダミー実装。"""

    def retry(self, run_id: str, attempt: int = 1, dry_run: bool = False) -> RetryResult:
        return RetryResult(
            original_run_id=run_id, outcome=RetryOutcome.DISABLED, attempt=attempt,
            monitor_status=None,
            reason="Retry Engine is disabled (RETRY_ENGINE_ENABLED=false, "
                   "or AI_AGENT_ENABLED/WORKFLOW_ENGINE_ENABLED is not ready).",
            workflow_engine_result=None,
        )
```

`retry()`の`dry_run`引数は、`RetryManager`の初版実装（Architecture Review反映版）では
公開APIから到達不能だった`RetryRequest.dry_run`フィールドを実際に呼び出し可能にするための
追加調整である（10章 Design Decision #12）。`NullRetryManager.retry()`にも同じ引数を
追加し、`RetryManager.from_config()`の戻り値（`RetryManager | NullRetryManager`）を
呼び出し元がduck-typingで同一に扱えるようにしている（`NullRetryManager`側は引数を
受け取って無視するのみで、挙動は変わらない）。

`RetryManager` は一括処理用のメソッド（例：`list_status()`の全件を走査して再実行する
「sweep」）を持たない。複数`run_id`の走査は呼び出し元（将来のCLI・Scheduler連携）の責務とし、
`WorkflowMonitorManager.list_status()` を直接使わせる。Retry Engine自身に走査・選別機能を
持たせると、対象外とした Retry Queue と責務が重なってしまうため（10章 Design Decision #6）。

### `__init__.py` の公開シンボル

```python
__all__ = [
    "RetryPolicy",
    "RetryConfig",
    "RetryRequest",
    "RetryOutcome",
    "RetryResult",
    "RetryExecutor",
    "RetryManager",
    "NullRetryManager",
]
```

---

## 7. Dependency Diagram

```
src/retry_engine/  ─── import ───→  src/workflow_monitor/
                                     （WorkflowMonitorManager / NullWorkflowMonitorManager /
                                      WorkflowMonitorRecord / WorkflowMonitorStatus）

src/retry_engine/  ─── import ───→  src/workflow_engine/
                                     （WorkflowEngineManager / NullWorkflowEngineManager /
                                      WorkflowEngineEvent / WorkflowEngineResult / SOURCE_MANUAL）
```

`src/retry_engine/` は上記2パッケージ**以外**（`execution_history` / `ai` / `pipeline` /
`scheduler`）を一切importしない。これは6章の `RetryManager.from_config()` が
Config群からの再構築ではなく、呼び出し元が組み立て済みの Manager インスタンスを受け取る
Dependency Injection 方式を採用しているために成立する（`WorkflowEngineManager` の構築に
必要な `ai` / `pipeline` / `execution_history` への依存は `workflow_engine` パッケージの
内部に閉じたままになる）。

- `src/workflow_engine/` ・`src/workflow_monitor/` のいずれも `src/retry_engine/` の存在を
  一切知らない（両パッケージとも無改修）
- `workflow_monitor` → `execution_history`（v2.9.0で確立済み、無改修）
- `workflow_engine` → `ai` / `pipeline` / `execution_history`（v2.7.0〜v2.8.0で確立済み、無改修）

依存関係全体は次のDAGになる（矢印は「importする」方向）。

```
retry_engine ──→ workflow_engine ──→ ai, pipeline, execution_history
      │
      └────────→ workflow_monitor ──→ execution_history
```

循環importは存在しない。3章で述べた「再実行結果がまた観測パイプラインに乗る」という
制御フローは実行時の話であり、import依存とは別軸である。

---

## 8. Data Flow

```
① 呼び出し元（将来のCLI／Scheduler連携）が run_id を指定して RetryManager.retry(run_id) を呼ぶ
        ↓
② RetryManager が WorkflowMonitorManager.get_status(run_id) を呼び、
   その時点の最新 WorkflowMonitorRecord を取得する（Read Before Retry）
        ↓
③ record が None → RetryResult(outcome=NOT_FOUND) を即座に返す（終了）
        ↓ record が存在する場合
④ RetryManager が RetryPolicy.should_retry(record.monitor_status, attempt) を判定する
   （target_statuses / max_attempts と record.monitor_status / attempt を突き合わせる）
        ↓ 対象外 ─────────────────→ RetryResult(outcome=SKIPPED, reason=...) を返す（終了）
        ↓ 対象
⑤ RetryRequest(run_id, attempt, requested_at=now()) を組み立て、RetryExecutor.execute() へ渡す
        ↓
⑥ RetryExecutor が WorkflowEngineEvent(source=SOURCE_MANUAL,
   metadata={"retried_from": run_id, ...}) を組み立てる（RetryExecutorはここで初めて
   関与する。可否判定はすでに④でRetryManagerが完了済み）
        ↓
⑦ WorkflowEngineManager.run(event) を呼ぶ（Workflow Engineが無改修のまま
   News → Review → Publish を実行し、新しい run_id で Execution History に記録する）
        ↓
⑧ WorkflowEngineResult を受け取り、RetryResult(outcome=RETRIED, workflow_engine_result=...) を
   組み立てて呼び出し元に返す
```

Retry Engine自身がファイル・DB等へ何かを書き込む処理は一切ない（Stateless。⑦の書き込みは
既存の Workflow Engine → Execution History の経路がそのまま担う）。

---

## 9. Sequence Diagram（Retry Flow）

```
Caller                RetryManager        WorkflowMonitorManager   RetryExecutor        WorkflowEngineManager
  │  retry(run_id,          │                       │                    │                       │
  │  attempt=1)             │                       │                    │                       │
  ├────────────────────────►│                       │                    │                       │
  │                         │  get_status(run_id)   │                    │                       │
  │                         ├──────────────────────►│                    │                       │
  │                         │◄──────────────────────┤                    │                       │
  │                         │  WorkflowMonitorRecord │                    │                       │
  │                         │  (monitor_status=FAILED)                   │                       │
  │                         │                       │                    │                       │
  │                         │  policy.should_retry(FAILED, 1) == True    │                       │
  │                         │  （Retry可否判定はRetryManagerがここで完了する）  │                       │
  │                         │  RetryRequest(run_id, attempt=1, ...)      │                       │
  │                         │                       │                    │                       │
  │                         │  execute(RetryRequest, record)             │                       │
  │                         ├────────────────────────────────────────────►│                       │
  │                         │                       │        WorkflowEngineEvent(source=MANUAL,    │
  │                         │                       │        metadata={retried_from: run_id, ...}) │
  │                         │                       │        （RetryExecutorはPolicyを参照せず、    │
  │                         │                       │        変換とrun()呼び出しのみを行う）        │
  │                         │                       │                    │   run(event)          │
  │                         │                       │                    ├──────────────────────►│
  │                         │                       │                    │  （News→Review→Publish │
  │                         │                       │                    │   を無改修のまま実行、  │
  │                         │                       │                    │   新run_idで観測される）│
  │                         │                       │                    │◄──────────────────────┤
  │                         │                       │                    │  WorkflowEngineResult  │
  │                         │◄────────────────────────────────────────────┤                       │
  │                         │  RetryResult(outcome=RETRIED,               │                       │
  │                         │  workflow_engine_result=...)                │                       │
  │◄────────────────────────┤                       │                    │                       │
  │  RetryResult            │                       │                    │                       │
```

`SKIPPED` / `NOT_FOUND` / `DISABLED` のいずれの場合も、`RetryExecutor.execute()` は
一切呼ばれず、`WorkflowEngineManager.run()`（＝実際の再実行）にも到達しない。Retry可否判定が
`RetryManager` 1箇所に集約されているため、これにより「再実行してよいか分からない状態で
実行してしまう」事故を構造的に防ぐ（10章 Design Decision #10）。

---

## 10. Design Decisions

1. **`RetryPolicy`（業務ルール）と `RetryConfig`（Feature Gate）を分離する。**
   `RetryPolicy` は `WorkflowEngineDefinition`（envに依存しない業務ルールオブジェクト）と
   同型、`RetryConfig` は `WorkflowEngineConfig`（Feature Gateのみを持つ設定オブジェクト）と
   同型とする。「再実行してよいか（Gate）」と「何を再実行対象とするか（Policy）」を型で
   分けることで、将来 Failure Classification 等でPolicyだけが複雑化しても Gateには
   影響しない構成にする。

2. **`RETRY_ENGINE_ENABLED` のデフォルトは `false`。** Execution History /
   Workflow Monitor（読み取り専用、デフォルト`true`）とは異なり、Retry Engineは実際に
   Workflowを再実行する（外部副作用を伴いうる）ため、`AI_AGENT_ENABLED` /
   `WORKFLOW_ENGINE_ENABLED` と同じ「安全側で止める」原則を適用する。結果として
   実質的に `AI_AGENT_ENABLED × WORKFLOW_ENGINE_ENABLED × RETRY_ENGINE_ENABLED` の
   三重ゲートになる。

3. **`RetryManager.from_config()` は Config群からの再構築ではなく、構築済みの
   `WorkflowEngineManager` / `WorkflowMonitorManager` を Dependency Injection で受け取る。**
   もし Config群（`AgentConfig` / `WorkflowEngineConfig` / `ExecutionHistoryConfig` /
   `WorkflowMonitorConfig`）から Retry Engine 自身が Manager を再構築する設計にすると、
   `retry_engine` パッケージが `ai` / `pipeline` / `execution_history` にも間接的に
   依存することになり、Charterで明示された「Workflow Engineの内部実装へ直接依存しない」
   「Execution Historyを直接解釈しない」という要求を import レベルで満たせなくなる。
   呼び出し元（将来のCLI等）が各パッケージの `from_config()` で Manager を構築し、
   それを Retry Engine に渡す構成にすることで、`retry_engine` の依存先を
   `workflow_engine` と `workflow_monitor` の2パッケージだけに限定できる（7章）。

4. **再実行イベントの `source` は新規定数を追加せず、既存の `SOURCE_MANUAL` を再利用する。**
   当初「`SOURCE_RETRY = "retry"` を `workflow_engine_event.py` に追加する」案も検討したが、
   「既存モジュールの責務を変更しない」「後方互換性を維持する」というCharterの原則を
   最優先し、`workflow_engine` パッケージを1バイトも変更しない設計を採る。再実行由来の
   実行であることは `WorkflowEngineEvent.metadata`（既存のfree-formな `dict` フィールド）に
   `{"retried_from": run_id, "attempt": N}` を積むことで判別可能にする。`source` による
   専用の分離が必要になった場合は、Future Extensions（11章）で `workflow_engine` 側の
   変更として再検討する。

5. **`RetryResult` は新しい `run_id`（再実行によってExecution Historyに新規記録される
   run_id）を保持しない。** `WorkflowEngineManager.run()` の戻り値 `WorkflowEngineResult`
   （`workflow_engine_result.py`）は現状 `run_id` を公開フィールドとして持たない
   （`run_id` は `WorkflowEngineManager._generate_run_id()` が内部生成し
   `WorkflowEngineContext` にのみ保持される、非公開の実装詳細）。これを取得可能にするには
   `WorkflowEngineResult` へのフィールド追加（`workflow_engine` パッケージの変更）が
   必要になるため、本Foundationでは行わない。`RetryResult.workflow_engine_result` に
   `WorkflowEngineResult` そのもの（`overall_success` / `steps` / `warnings` 等）を
   同期的に埋め込むことで、呼び出し元は「この1回の再実行が何をしたか」を
   `run()` 呼び出しの戻り値だけから把握できるため、Foundationの範囲では実用上の支障はない。
   「元の `run_id` と再実行後の `run_id` を明示的に紐付ける」機能は、Retry History
   （対象外）を実装する将来Releaseで、`WorkflowEngineResult.run_id` の追加とあわせて
   再検討する（11章）。

6. **`RetryManager` は複数`run_id`を一括で走査する「sweep」的なメソッドを持たない。**
   `WorkflowMonitorManager.list_status()` の全件を自動的に走査して再実行対象を選別する
   機能を Retry Engine 自身に持たせると、対象外と明記された Retry Queue / Priority Queue
   と責務が重なる。本Foundationでは「1つの `run_id` について、再実行してよいか判定し、
   よければ実行する」という最小単位のAPI（`retry(run_id, attempt)`）のみを提供し、
   複数`run_id`の選別・走査は呼び出し元の責務とする。

7. **再試行回数（`attempt`）はRetry Engine自身が記憶せず、呼び出し元が指定する。**
   Retry History（過去の再試行回数の永続化・参照）は対象外であるため、Retry Engineは
   「これまでに何回再試行したか」をExecution History等から逆算する機能を持たない。
   `RetryPolicy.max_attempts` という上限値の概念だけを本Foundationで定義し、実際に
   何回目の試行かは `RetryRequest.attempt` として呼び出し元に委ねる。これにより
   Retry Engine は文字通り Stateless であり続ける。

8. **本FoundationにはCLIスクリプト（`scripts/run_retry_engine.py`等）を含めない。**
   Release 2.7〜2.9はいずれも読み取り・実行確認用のCLIスクリプトを実装対象に含めていたが、
   本Releaseの実装対象として明示されたのは `src/retry_engine/` 配下の6コンポーネント
   （Policy / Request / Result / Executor / Manager / Config）のみである。CLIエントリ
   ポイントの追加は「Manual Retry UI」（対象外）と隣接する領域であり、スコープを
   厳密に保つため本Foundationでは見送る。`RetryManager` は `WorkflowEngineManager` /
   `WorkflowMonitorManager` 同様、DIしたFakeを使って直接テスト可能であるため、
   CLIがなくてもTesting Strategy（12章）・Acceptance Criteria（13章）は成立する。

9. **「Read Before Retry」は `RetryManager.retry()` のシグネチャで構造的に強制する。**
   `RetryManager.retry()` は `WorkflowMonitorRecord` を引数に取らず、`run_id`
   （文字列）のみを受け取り、その場で `WorkflowMonitorManager.get_status(run_id)` を
   呼んで最新状態を取得する。呼び出し元が事前に取得した（古いかもしれない）
   `WorkflowMonitorRecord` を直接渡せる余地をAPIレベルで排除することで、
   「一覧表示した時点では`FAILED`だったが、実際に再実行しようとした時点ではすでに
   誰かが再実行して`RUNNING`になっていた」といったレース条件下でも、常に呼び出し
   直前の最新状態に基づいて判定される。

10. **`RetryExecutor` は `WorkflowEngineManager` の公開APIを呼び出すだけの薄いコンポーネント
    とする（Architecture Review 2026-07-02 反映）。** 初版設計では `RetryExecutor.execute()`
    が `RetryPolicy` の判定（対象ステータス・上限回数のチェック）まで担っていたが、
    Architecture Reviewの指摘を受け、Retry可否判定（`RetryPolicy`の適用）・
    `RetryRequest`の生成は `RetryManager` の責務に一本化した。`RetryExecutor` は
    `RetryManager` からすでに「再実行する」と判定された `RetryRequest` のみを受け取り、
    `WorkflowEngineEvent` への変換と `WorkflowEngineManager.run()` の呼び出し、戻り値の
    `RetryResult` への詰め替えのみを行う。これに伴い `RetryExecutor` のコンストラクタから
    `policy: RetryPolicy` 引数を削除した（6章）。判定ロジックが `RetryManager` の
    `retry()` 1箇所に集約されることで、「どの条件で再実行が却下されたか」を追跡する際に
    見るべき場所が一意になり、`RetryExecutor` を「WorkflowEngineManagerへの薄い
    アダプタ」として単体テストしやすくなる（12章）。

11. **`RetryPolicy` は現時点で単一の `dataclass` だが、将来 Strategy Pattern
    （`FixedRetryPolicy` / `ExponentialBackoffPolicy` / `AdaptiveRetryPolicy` 等）へ
    拡張できる構造を保つ（Architecture Review 2026-07-02 反映）。** `RetryManager` は
    `RetryPolicy` を「`should_retry(monitor_status, attempt) -> bool` という1メソッドを
    持つオブジェクト」としてのみ利用しており（`retry()` 内で `self._policy.should_retry(...)`
    を呼ぶ1箇所と、reason文字列生成で `target_statuses` / `max_attempts` を参照する
    `_skip_reason()` のみ）、`RetryPolicy` の具体的な内部実装には依存しない。将来
    `RetryPolicy` を抽象基底クラス（Protocol または ABC）へ変換し、`FixedRetryPolicy`
    （本Foundationの実装をそのままリネームしたもの）を既定実装としつつ
    `ExponentialBackoffPolicy`（再試行間隔つき）・`AdaptiveRetryPolicy`（過去の失敗傾向に
    応じて動的に調整）等を追加する場合も、変更が必要になるのは `RetryManager.retry()` の
    呼び出し方法（現状すでにインターフェース越しの呼び出しに近い形）程度に留まる想定である。
    **本Foundationでは固定Retry Policy（`RetryPolicy`単体、6章）のみを実装し、
    Strategy Pattern化そのものは行わない**（11章 Future Extensions）。

12. **`RetryManager.retry()` は `dry_run: bool = False` を受け取り、生成する
    `RetryRequest.dry_run` へそのまま渡す（実装後の追加調整、2026-07-02反映）。**
    初版実装では `RetryRequest.dry_run` フィールドが定義されているにもかかわらず、
    `RetryManager.retry(run_id, attempt)` のシグネチャに `dry_run` が存在せず、
    `RetryManager` が生成する `RetryRequest` は常に `dry_run=False` 固定であった。
    そのため `RetryRequest.dry_run=True` は `RetryExecutor.execute()` を直接呼ぶ
    ユニットテスト以外の経路（＝公開APIである `RetryManager.retry()`）からは
    到達不能という構造上のギャップがあった。この状態のままでは、`RetryManager`
    経由で「Workflowを実際には再実行せず、`WorkflowEngineManager.run()` が
    呼ばれる経路だけを確認したい」という用途（動作確認・ステージング環境での
    検証等）に応えられない。`RetryRequest.dry_run` フィールド自体は初版から
    Architecture Design 6章で定義済みであり、これは新しい概念の追加ではなく、
    既存フィールドを公開APIから使えるようにする最小の追加調整であるため、
    `RetryManager.retry()` / `NullRetryManager.retry()` のシグネチャに
    `dry_run: bool = False`（キーワード引数、デフォルト値あり）を追加した。
    **既存呼び出し（`retry(run_id)` / `retry(run_id, attempt=N)`）の互換性は
    完全に維持される**（デフォルト値により既存コードの変更は不要）。
    `RetryExecutor.execute()` の内部実装（`self._engine.run(event, dry_run=request.dry_run)`
    をそのまま呼ぶだけ）・`RetryRequest` のデータ構造（フィールド追加なし）は
    いずれも変更していない。責務分離の原則（10章 Design Decision #10：Retry可否判定・
    RetryRequest生成はRetryManagerが担当し、RetryExecutorはAPIを呼ぶだけの薄い
    コンポーネントであること）にも矛盾しない変更である。

---

## 11. Future Extensions

- **Exponential Backoff**：`RetryPolicy` に再試行間隔の概念を追加する（現状は間隔の概念を持たない）
- **Retry Queue / Priority Queue**：`WorkflowMonitorManager.list_status()` の走査・
  優先度付け・スケジューリングを行う、Retry Engineの上位に位置する別パッケージ
- **Notification**：`RetryResult.outcome` を起点としたSlack/Discord/LINE通知
- **Metrics / Retry Analytics**：再試行回数・成功率の集計
- **Dashboard**：`RetryResult` の履歴をWeb UIから参照する
- **Retry History**：`attempt` の永続化（現状は呼び出し元が都度指定、design decision #7）。
  実現時には `WorkflowEngineResult` への `run_id` フィールド追加（design decision #5）も
  あわせて必要になる
- **Failure Classification**：`monitor_status` だけでなく `WorkflowMonitorRecord.reason` /
  `steps` の内容に基づいて再試行可否を判定する、より高度な `RetryPolicy`
- **RetryReason（Retry判定理由のEnum化）**：現状 `RetryResult.reason` は自由記述の
  `str | None` だが、将来的に構造化された `RetryReason` Enumへ置き換えられる設計とする。
  想定する値の例：`FAILED`（Workflow Monitorの判定がFAILED）・`TIMEOUT`（判定がTIMEOUT）・
  `NETWORK_ERROR`（ネットワーク起因の失敗）・`TEMPORARY_FAILURE`（一時的な失敗、再試行で
  回復見込みあり）・`PERMANENT_FAILURE`（恒久的な失敗、再試行非対象）。Failure
  Classification（前項）と密接に関連し、その実現とあわせて導入を検討する。
  **本Foundationでは実装しない。**
- **RetryDecision（Retry可否判定の専用コンポーネントへの分離）**：現状は
  `RetryManager.retry()` 内でその場限りの判定（`RetryPolicy.should_retry()`の呼び出しと
  `_skip_reason()`によるreason文字列生成）として実装しているが、将来 Exponential Backoff・
  Retry History・Failure Classification 等と組み合わせて判定ロジックが複雑化した場合、
  判定結果を表す独立した値オブジェクト `RetryDecision` として切り出すことを想定する。
  想定する責務：(1) Retry可否判定そのもの、(2) Retry理由（前述の`RetryReason`）の保持、
  (3) これまでのRetry回数、(4) 次回Retry時刻（Exponential Backoff実現後）、
  (5) `RetryDecision`オブジェクト自体の生成。**本Foundationでは実装対象外とし、
  `RetryManager`内のインライン判定のみを提供する。**
- **AI Retry Decision**：Claude APIによる再試行要否・再試行タイミングの判断
- **Parallel Retry / Distributed Retry**：複数`run_id`の並列・分散再実行
- **Circuit Breaker**：連続失敗時に一定期間再実行を自動停止する
- **Dead Letter Queue**：上限到達後も回復しない`run_id`の退避先
- **Manual Retry UI**：人が失敗一覧から選んで再実行を指示するダッシュボード
- **`scripts/run_retry_engine.py`（CLIエントリポイント）**：`--run-id` 指定での単発再実行、
  または `WorkflowMonitorManager.list_status()` と組み合わせた手動走査ツール
  （design decision #8で本Releaseからは見送ったもの）
- **Scheduler連携**：`SchedulerEngine` の定期実行に乗せて、`FAILED` / `TIMEOUT` の
  `run_id` を定期的に再実行する自動運用
- **`source="retry"` 専用定数の追加**：`workflow_engine` パッケージ側の変更を伴うため、
  Execution History上で再実行由来の実行を`source`列だけで判別する必要が生じた時点で再検討する
  （design decision #4）

---

## 12. Testing Strategy

- `RetryPolicy.should_retry()`（真理値表）：
  - `FAILED` かつ `attempt < max_attempts` → `True`
  - `FAILED` かつ `attempt >= max_attempts` → `False`
  - `TIMEOUT` かつ `attempt < max_attempts` → `True`
  - `SUCCESS` / `RUNNING` → `False`（`attempt`によらず）
  - `CANCELLED` / `WAITING`（Workflow Monitorの判定ロジックからは現状到達しないが、
    Enum値としては存在するため防御的にテストする）→ `False`
  - `RetryPolicy.from_env()`：デフォルト`max_attempts=3`・環境変数`RETRY_MAX_ATTEMPTS`上書き・
    `target_statuses`が`{FAILED, TIMEOUT}`固定であること
- `RetryConfig.from_env()`：デフォルト`enabled=False`・環境変数`RETRY_ENGINE_ENABLED`上書き・
  `is_ready()`判定
- `RetryRequest` / `RetryResult` / `RetryOutcome`：構築・フィールドの整合性
- `RetryExecutor.execute()`（Fakeの`WorkflowEngineManager`を注入）：
  - `RetryExecutor`はPolicy判定を行わないため、`execute()`が呼ばれた場合は**常に**
    Fakeの`run()`が1回だけ呼ばれ、`RetryResult.outcome == RETRIED`になること
    （SKIPPEDに相当するケースは`RetryManager`側で止まるため、`RetryExecutor`単体テストには
    存在しない。10章 Design Decision #10）
  - 渡された`WorkflowEngineEvent`の`source == SOURCE_MANUAL`、`job_id == record.job_id`、
    `metadata == {"retried_from": request.run_id, "attempt": request.attempt}`であること
  - `request.dry_run=True`が`self._engine.run(event, dry_run=True)`にそのまま伝播すること
  - 戻り値の`workflow_engine_result`にFakeの`run()`の戻り値がそのまま格納されていること
  - `RetryExecutor`のコンストラクタが`policy`引数を持たないこと（`RetryPolicy`を一切
    保持しないことの型レベルの確認）
- `RetryManager.retry()`（Fakeの`WorkflowMonitorManager` / `RetryExecutor`を注入）：
  - `get_status()`が`None`を返す場合 → `NOT_FOUND`、`RetryPolicy.should_retry()`も
    `RetryExecutor.execute()`も呼ばれないこと
  - `record.monitor_status`が対象外（`SUCCESS` / `RUNNING`）→ `SKIPPED`、
    `RetryExecutor.execute()`が呼ばれないこと（Policy判定が`RetryManager`側で完結する
    ことの確認、10章 Design Decision #10）
  - `attempt >= max_attempts` → `SKIPPED`、`RetryExecutor.execute()`が呼ばれないこと
  - `record.monitor_status`が`FAILED` / `TIMEOUT`かつ`attempt < max_attempts` →
    `RetryExecutor.execute()`へ委譲され、その戻り値がそのまま`retry()`の戻り値になること
  - 同一`run_id`に対し複数回`retry()`を呼んだ際、毎回`get_status()`が呼び出されること
    （Read Before Retryの確認、10章 design decision #9）
  - `retry(run_id, attempt, dry_run=True)` → 生成される`RetryRequest.dry_run=True`が
    `RetryExecutor.execute()`（ひいては`WorkflowEngineManager.run(event, dry_run=True)`）
    まで伝播すること（10章 Design Decision #12）
  - `dry_run`省略時は従来どおり`False`のまま伝播すること（既存呼び出しの後方互換性の確認）
- `RetryManager.from_config()`（ゲート判定）：
  - `RetryConfig.enabled=False` → `NullRetryManager`
  - `RetryConfig.enabled=True`かつ`workflow_engine_manager`が`NullWorkflowEngineManager`
    → `NullRetryManager`
  - 両方満たす場合 → `RetryManager`（実インスタンス）
- `NullRetryManager.retry()`：常に`outcome=DISABLED`を返し、`WorkflowMonitorManager` /
  `WorkflowEngineManager`のいずれのメソッドも一切呼ばれないこと。`dry_run=True`を渡しても
  エラーにならず同じ結果を返すこと（10章 Design Decision #12）
- **書き込みが発生しないことの確認**：`RetryManager` / `RetryExecutor`実行前後で、
  `retry_engine`パッケージ自身がファイル・DBへの書き込みを一切行わないこと
  （`SKIPPED` / `NOT_FOUND` / `DISABLED`の場合は当然、`RETRIED`の場合も書き込みは
  既存の`WorkflowEngineManager.run()`経由でのみ発生し、`retry_engine`自身は書き込まない）
- Architecture Guard：`src/retry_engine/`配下のいずれのファイルも`execution_history` /
  `ai` / `pipeline` / `scheduler`をimportしないこと（静的検査、`workflow_monitor`の
  Architecture Guardと同型）。`src/workflow_engine/` / `src/workflow_monitor/` /
  `src/execution_history/`配下の既存ファイルに変更がないこと（`git diff`で確認。
  本Releaseはゼロ改修のため、差分がないことそのものが合格基準になる）

### 既存回帰確認（実装フェーズで実施）

- `tests/test_e2e_v2_9_0_workflow_monitor_foundation.py`（最重要。Retry Engine追加により
  `WorkflowMonitor` / `WorkflowMonitorManager`の既存入出力仕様が壊れていないことの確認。
  ただし本Releaseでは`workflow_monitor`パッケージ自体は無改修のため、通常は影響がないはずである）
- `tests/test_e2e_v2_8_0_execution_history_foundation.py`〜`tests/test_e2e_v2_0_0_ai_agent_foundation.py`、
  `tests/test_e2e_v1_20_0_ai_workflow_foundation.py`

---

## 13. Acceptance Criteria

### コード（未着手）

- [ ] `RetryPolicy`（`src/retry_engine/retry_policy.py`）
- [ ] `RetryConfig`（`src/retry_engine/retry_config.py`）
- [ ] `RetryRequest`（`src/retry_engine/retry_request.py`）
- [ ] `RetryResult` / `RetryOutcome`（`src/retry_engine/retry_result.py`）
- [ ] `RetryExecutor`（`src/retry_engine/retry_executor.py`）
- [ ] `RetryManager` / `NullRetryManager`（`src/retry_engine/retry_manager.py`）
- [ ] `src/retry_engine/__init__.py`（新規シンボルのexport）

### テスト（未着手）

- [ ] `tests/test_e2e_v3_0_0_retry_engine_foundation.py`（12章の全ケース）
- [ ] 既存回帰確認：`v2.9.0`（最重要）・`v2.0.0`〜`v2.8.0`・`v1.20.0`（全件PASS）
- [ ] Architecture Guard（一方向依存の静的検査・`workflow_engine` / `workflow_monitor` /
      `execution_history`が無改修であることの`git diff`確認）

### 満たすべき性質（機能要件）

- [ ] `RetryManager.retry(run_id)`が、`WorkflowMonitorStatus.FAILED` / `TIMEOUT`の
      `run_id`に対してのみ実際に再実行し、それ以外（`SUCCESS` / `RUNNING`）では
      再実行しないこと
- [ ] `attempt >= max_attempts`の場合に再実行しないこと（無限リトライの防止）
- [ ] `RETRY_ENGINE_ENABLED=false`（デフォルト）の場合、`NullRetryManager`が返り、
      いかなる`run_id`に対しても実際の再実行が発生しないこと
- [ ] `RetryManager` / `RetryExecutor`が`src/execution_history/`のJSONファイルを
      直接読み書きしていないこと（Workflow Monitor経由のみで状態を取得していること）
- [ ] `RetryManager` / `RetryExecutor`が`WorkflowEngineExecutor`を直接importまたは
      構築していないこと（`WorkflowEngineManager.run()`のみを呼び出していること）
- [ ] 再実行後、新しい実行がExecution History / Workflow Monitorから通常のWorkflow実行と
      同様に観測できること（Retry Engine専用の記録経路を持たないことの確認）
- [ ] `RetryExecutor`が`RetryPolicy`型を一切参照・保持していないこと（コンストラクタに
      `policy`引数を持たないことの構造的確認。Retry可否判定が`RetryManager`に一本化されて
      いることの確認、10章 Design Decision #10）

### ドキュメント

- [x] 本設計書（Architecture Design、Architecture Review指摘事項4点反映済み）
- [x] `docs/design/retry_engine_foundation_charter.md`（Project Charter、新規作成）
- [ ] `docs/CHANGELOG.md` / `docs/ROADMAP.md`への記載（実装完了後）
- [ ] `docs/architecture.md`への追記（Retry Engine層の追加。実装完了後）

### リリース

- [ ] コミット（実装完了・テストPASS後、ユーザー確認を経て実施）
- [ ] push（コミット後、別途ユーザー確認を経て実施）
