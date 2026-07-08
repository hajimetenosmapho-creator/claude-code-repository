# Project Charter — Release 4.6「Retry Enqueue Trigger Foundation」

作成日：2026-07-09
状態：承認済み・実装完了
対象：`WorkflowMonitorManager`（v2.9.0、無改修）が判定した`FAILED` / `TIMEOUT`の
Workflowを、`RetryQueueManager`（v3.1.0、無改修）へ自動的に`enqueue`する
最小Adapter（`RetryEnqueueTrigger`）を新設する。

> **本Releaseの位置づけについての注記**：v3.0.0〜v4.5.0の16回のReleaseで、
> Retry QueueからRetry Engineを経てQueueの後始末（Update / Removal /
> Cleanup / Terminal Cleanup）に至る**下流**のパイプラインはすべて完成した。
> しかし`RetryManager.enqueue_retry()` / `RetryQueueManager.enqueue()`は
> コードベース全体のどこからも呼び出されておらず（`retry_manager.py`本体・
> `scripts/`配下を確認済み）、Queueへ実際に項目を投入する**上流**が
> 存在しない。本Releaseはこの欠落を埋める。

---

## 1. Background

* `WorkflowMonitorManager.list_status(limit=None) -> list[WorkflowMonitorRecord]`
  （v2.9.0、無改修）は、`RUNNING` / `SUCCESS` / `FAILED` / `TIMEOUT`のいずれかを
  持つ`WorkflowMonitorRecord`（`run_id` / `workflow_name` / `monitor_status`等）
  の一覧を返す、副作用のない読み取り専用メソッドである。
* `RetryQueueManager.enqueue(run_id, workflow_name, retry_attempt=1,
  priority=None) -> RetryQueueResult`（v3.1.0、無改修）は、`run_id`が既に
  Queueに存在する場合・`max_queue_size`到達時のみ`REJECTED`を返し、それ以外は
  `WAITING`状態の`RetryQueueItem`をQueueへ追加する。
* `RetryQueueManager.exists(run_id) -> bool`（v3.1.0、無改修）を使えば、
  重複投入を`enqueue()`の`REJECTED`判定に頼らず呼び出し前に回避できる。
* **重要な発見**：Queueに投入された項目は、`RetrySchedulerSource.
  list_pending_retries()`（v3.3.0）→ `RetrySchedulerDecision.
  select_candidates()`（v3.5.0）→ `SchedulerEngine`（v3.7.0でRetry候補由来の
  `SchedulerEvent`として出力）という経路で**読み取られるだけ**であり、
  `dequeue()`は現在に至るまで一度も呼び出し経路を持たない（ROADMAP.md
  v3.x以降の候補一覧、`[KI]`群を確認済み）。つまりQueue内の項目は
  `RetryQueueManager.remove()`（`COMPLETE` / `FAIL` / `CLEANUP`判定時のみ、
  v4.2.0〜v4.4.0）が呼ばれるまで`WAITING`のままQueueに残り続ける。
  本Releaseの`exists()`チェックは、この「itemは`remove()`されるまでQueueに
  残り続ける」という既存の設計上の前提に依存する。
* **もう1つの発見**：`WorkflowMonitorManager`には`FAILED` / `TIMEOUT`のみを
  絞り込むメソッドは存在しない（`list_status()`は全ステータスを返す）。
  絞り込みは呼び出し側（本Releaseの新規Adapter）の責務になる。
* 既存の同種Adapter（`RetrySchedulerSource`、v3.3.0）は、単一の依存先
  （`RetryQueueManager`）へのConstructor Injection＋薄い委譲のみで構成され、
  Feature Gate・Configクラスを持たず、有効/無効は呼び出し元がAdapter実体と
  Null実装のどちらを構築するかで表現するという設計を採用している。本Release
  もこのパターンを踏襲する（8章 Open Questions参照）。

```
WorkflowMonitorManager.list_status()  （無改修、既存）
        │  FAILED / TIMEOUT のみ抽出
        ▼
   ★本Releaseで新設：RetryEnqueueTrigger
        │  RetryQueueManager.exists(run_id) で重複を確認
        ▼
RetryQueueManager.enqueue(run_id, workflow_name, ...)  （無改修、既存）
        │
        ▼
  （v3.3.0〜v4.5.0の既存パイプラインが初めて実データを受け取れる）
```

---

## 2. Purpose

`WorkflowMonitorManager`が判定した`FAILED` / `TIMEOUT`のWorkflowを検知し、
まだQueueに存在しないものだけを`RetryQueueManager.enqueue()`へ渡す、
最小責務のAdapterを新設する。これにより、v3.0.0〜v4.5.0で構築された
Retry Queue〜Retry Engineの下流パイプラインが、初めて実運用のデータで
動作しうる状態になる。

`WorkflowMonitorManager` / `RetryQueueManager` / `RetryManager`本体、
および両者を仲介する既存パッケージ（`retry_scheduler_source`等）への
変更は一切行わない。

---

## 3. Goals

1. `WorkflowMonitorManager.list_status()`の結果から`monitor_status`が
   `FAILED`または`TIMEOUT`の`WorkflowMonitorRecord`のみを抽出する
2. 抽出した各`run_id`について`RetryQueueManager.exists()`で重複を確認し、
   まだQueueに存在しないものだけを`enqueue()`する
3. 一括処理の結果（何件検知し・何件enqueueし・何件スキップしたか）を
   呼び出し元が把握できる戻り値を設計する
4. `RetrySchedulerSource`（v3.3.0）と同様のNull Object Pattern
   （`RetryEnqueueTrigger` / `NullRetryEnqueueTrigger`）を採用し、
   Feature Gate・Configクラスは新設しない方針を基本としつつ、
   Architecture Designで最終確認する（8章 Open Questions #1）
5. `workflow_monitor` / `retry_queue` / `retry_engine`本体はいずれも
   無改修のまま実現する
6. 本Releaseでは、新設したAdapterをどこからも定期的に呼び出さない
   （Foundation First。実運用の起動導線——Composition Root——は将来Release）

---

## 4. Scope

### 対象

* 新規パッケージ`src/retry_enqueue_trigger/`の新設
  （`RetryEnqueueTrigger` / `NullRetryEnqueueTrigger`）
* `WorkflowMonitorManager.list_status()`の結果を`FAILED` / `TIMEOUT`で
  絞り込むロジック
* `RetryQueueManager.exists()`による重複投入の回避
* `RetryQueueManager.enqueue()`への委譲
* 一括処理結果を表す軽量な戻り値（新規`frozen dataclass`、他のRelease
  ——`RetryDispatchEvent`・`RetryQueueUpdateDecision`等——と同じ設計言語）
* テスト（新規Fake `WorkflowMonitorManager` / 実際の`RetryQueueManager`を
  使ったE2Eテスト）
* 関連ドキュメント更新（CHANGELOG / ROADMAP / architecture.md）

### 対象外（今回やらないこと）

* `WorkflowMonitorManager` / `RetryQueueManager` / `RetryManager`本体
  および既存Adapter（`retry_scheduler_source`等）への変更
* 新設Adapterを定期的に呼び出す起動スクリプト・Composition Root
  （`scripts/run_retry_enqueue_trigger.py`等。Non-Goal）
* `dequeue()`の解禁・自動Retry実行そのもの（引き続きv3.x以降の候補として
  対象外のまま）
* Retry Queueの永続化
* 再enqueue時の`retry_attempt`の増分ロジック（本Releaseは`retry_attempt=1`
  固定で初回投入のみを扱う。2回目以降の試行回数管理は8章 Open Questions
  #3で扱う）
* Retry Strategy（`FixedRetryPolicy`等）の実装

---

## 5. Design Principles

* **Foundation First**：Queueへ実際にデータを投入できる経路を作るところまでに
  留め、これを定期的に駆動する仕組み（Composition Root）は後続Releaseへ送る
* **Single Responsibility**：「検知して投入するか判定する」責務のみを持つ。
  Retry可否判定（`RetryPolicy`の責務）・Retry実行・Queueの後始末はいずれも
  行わない
* **Stateless**：新設Adapterは状態を持たない。呼び出しごとに
  `WorkflowMonitorManager` / `RetryQueueManager`の現在の状態を読み取って
  判定する
* **Composition over Inheritance**：`RetrySchedulerSource` /
  `NullRetrySchedulerSource`と同じ、継承関係を持たないDuck Typingペアを
  採用する
* **Backward Compatibility**：`workflow_monitor` / `retry_queue` /
  `retry_engine`はいずれも無改修。既存の呼び出し元・既存テストに影響しない
* **既存コンポーネントへの影響最小化**：新規ファイルのみで完結させる
* **依存方向**：`retry_enqueue_trigger → workflow_monitor` /
  `retry_enqueue_trigger → retry_queue`の新規一方向依存のみを追加する
  （`retry_scheduler_source → retry_queue`と同じ「下位パッケージへの
  直接依存」パターンを踏襲し、`retry_engine`は経由しない。8章 Open
  Questions #2）

---

## 6. Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryEnqueueTrigger`（新設） | `WorkflowMonitorManager`からFAILED/TIMEOUTを検知し、未投入のものだけ`RetryQueueManager.enqueue()`へ渡す | Retry可否判定・Retry実行・Queueの後始末・定期実行 |
| `NullRetryEnqueueTrigger`（新設） | 無効時のダミー実装。常に「何も検知せず何もenqueueしなかった」結果を返す | `workflow_monitor` / `retry_queue`への参照保持 |
| `WorkflowMonitorManager`（v2.9.0、無改修） | 引き続きWorkflowの状態判定のみを行う | Retry Queueへの関与 |
| `RetryQueueManager`（v3.1.0、無改修） | 引き続きQueue管理のみを行う | 検知・判定ロジック |

---

## 7. Dependencies

```
retry_enqueue_trigger  ──→ workflow_monitor（新規。WorkflowMonitorManager / WorkflowMonitorStatus / WorkflowMonitorRecord型の参照のみ）
retry_enqueue_trigger  ──→ retry_queue（新規。RetryQueueManager / NullRetryQueueManager型の参照のみ）
```

既存の依存方向（`retry_engine → workflow_engine / workflow_monitor / retry_queue / scheduler`、
`retry_scheduler_source → retry_queue`等）はいずれも無変更。循環importは
発生しない（`workflow_monitor` / `retry_queue`のいずれも`retry_enqueue_trigger`
を知らない）。

---

## 8. Open Questions（Architecture Designで確定する事項）

1. **Feature Gate・Configクラスを持たせるか**：
   - `RetrySchedulerSource`（v3.3.0）に倣い、Configクラスを持たず
     Null Object Patternのみで有効/無効を表現する案
   - Retry Queueへの書き込みという新しい種類の副作用（メモリ上のみだが、
     下流のRetry実行を誘発しうる最初の起点）を持つことを踏まえ、独自の
     `RetryEnqueueTriggerConfig`（例：`RETRY_ENQUEUE_TRIGGER_ENABLED`）を
     新設する案
   - いずれを選んでも本Releaseでは呼び出し元が存在しないため実害はないが、
     将来のComposition Root実装時にどちらが自然かを踏まえて確定する
2. **`retry_engine`を経由するか、`retry_queue`に直接依存するか**：
   - `RetryManager.enqueue_retry()`は`RetryQueueManager.enqueue()`への
     薄い委譲のみであり判定を加えないが、`NullRetryManager.enqueue_retry()`
     は`RETRY_ENGINE_ENABLED`ゲートに応じて常に`DISABLED`を返す
   - `retry_queue`に直接依存する場合、`RETRY_ENGINE_ENABLED=false`
     （デフォルト）でもQueueへの投入自体は行われる（`RetryQueueConfig`が
     独自ゲート`RETRY_QUEUE_ENABLED`——デフォルトtrue——を持つ既存設計と
     整合する）
   - `retry_engine`経由にする場合、Enqueue自体も`RETRY_ENGINE_ENABLED`に
     連動する（三重ゲートの一貫性は高まるが、`retry_scheduler_source`が
     `retry_engine`を経由しない既存パターンとは非対称になる）
3. **`retry_attempt`の扱い**：同一`run_id`が一度Queueから除去された後
   （`COMPLETE` / `FAIL` / `CLEANUP`）、Monitor上でなお`FAILED`のまま
   観測され続けた場合（＝再試行後もなお失敗、または全く別要因での
   `FAILED`）、本Adapterは再度`retry_attempt=1`として再投入してしまう
   可能性がある。試行回数の正式な追跡は`RetryQueueItem.retry_attempt`
   （Queueが保持）にのみ存在し、Monitor側にもExecution History側にも
   「これまで何回Retryしたか」を保持する場所がない。本Releaseでこの
   問題を解消するか、既知の制約として明記し将来Releaseへ送るかを
   Architecture Designで確定する
4. **一括処理結果の型**：検知件数・enqueue成功件数・スキップ件数・
   REJECTED件数をどう表現するか（既存の`RetryQueueResult`をそのまま
   リストで返すか、専用の集約`frozen dataclass`を新設するか）

---

## 9. Acceptance Criteria

* `RetryEnqueueTrigger`が、`WorkflowMonitorManager.list_status()`の結果から
  `FAILED` / `TIMEOUT`のみを対象とすること（`RUNNING` / `SUCCESS`は対象外）
* 既にQueueに存在する`run_id`（`RetryQueueManager.exists()`が`True`を返す
  もの）は再enqueueされないこと
* `NullRetryEnqueueTrigger`は`workflow_monitor` / `retry_queue`のいずれも
  参照せず、常に「検知0件・enqueue 0件」の結果を返すこと
* `workflow_monitor` / `retry_queue` / `retry_engine`本体がいずれも
  本Releaseで無改修であること（`git diff`で確認）
* 新設Adapterがどこからも呼び出されない（Composition Rootが存在しない）
  ことを構造的に確認する
* E2Eテスト全PASS、既存回帰（v2.0.0〜v4.5.0）全PASS

---

## 10. Non-Goals

* 新設Adapterを定期的に駆動する起動スクリプト（Composition Root）
* `dequeue()`の解禁・自動Retry実行の実運用化
* Retry Queueの永続化
* 試行回数（`retry_attempt`）の正式な追跡機構の新設（8章 Open Questions #3
  の結論次第で、既知の制約として明記するに留める可能性がある）
* Retry Strategy（`FixedRetryPolicy`等）の実装
* Retry Metrics・Notification・Dashboard

---

## 11. Risks and Mitigations

| リスク | 対策 |
|---|---|
| Queueから除去された`run_id`がMonitor上でなお`FAILED`のまま観測され続けると、無限にQueueへ再投入されうる（8章 Open Questions #3） | 本Releaseでは呼び出し元（Composition Root）が存在しないため実害は発生しない。Architecture Designで、本Releaseの対象内で軽減するか、既知の制約として明記し将来Releaseへ送るかを明確に選択する |
| `retry_queue`に直接依存するか`retry_engine`経由にするかで、将来のGate設計の一貫性に差が生じる（8章 Open Questions #2） | 既存の`retry_scheduler_source`の前例（`retry_queue`に直接依存し`retry_engine`を経由しない）を第一候補としつつ、Architecture Designで比較検討のうえ選択理由を明記する |
| `list_status()`に`limit`を指定しない場合、Execution History件数の増加とともに毎回の走査コストが増える可能性がある | 本Releaseでは呼び出し頻度・件数が未確定（呼び出し元が存在しないFoundation Release）のため許容する。Composition Root実装時に`limit`の要否を再評価する |

---

## 12. Status

- [x] Project Charter ドラフト作成（本文書、Claude Code作成）
- [x] ユーザー確認・フィードバック反映（Open Questions 4点の方針確定）
- [x] Project Charter 確定
- [x] Architecture Design
- [x] Implementation
- [x] Test（E2Eテスト89件・既存回帰確認、いずれも完了）
