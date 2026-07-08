# v4.4.0 NOT_FOUND / DISABLED Cleanup Foundation 設計書（Architecture Design）

作成日：2026-07-08
状態：確定（Architecture Review完了・Approve with Recommendations、
Recommendation 4件反映済み）。
`docs/design/retry_queue_notfound_disabled_cleanup_foundation_charter.md`
（Project Charter、承認済み）を前提とする。

> **本設計書の方針転換について**：Charterでは論点を「`NOT_FOUND`を
> Cleanupするか」「`DISABLEDをCleanupするか」という個別の是非として整理したが、
> ユーザー指示により、本設計書では**各`RetryOutcome`が「Terminal（終端状態）」か
> 「Transient（一時状態）」か**という一段抽象化した判断基準をまず定義し、
> Cleanup方針（CLEANUP／KEEP）はその分類から機械的に導出する設計とする
> （3章）。これにより、将来`RetryOutcome`に新しい値が追加された場合も、
> 「その値はTerminalかTransientか」を1箇所（3.2節の分類表）に追記するだけで
> Cleanup方針が定まる構造になる。

---

## 1. Architecture Overview

Release 4.3（`docs/design/retry_queue_cleanup_foundation.md`）までで、以下が
確立した。

* `RetryQueueUpdateDecider`（v4.1.0）が`RetryExecutionResult`から
  `RetryQueueUpdateDecision`（`outcome`：`COMPLETE` / `FAIL` / `NOOP`）を判定する
* `RetryQueueRemovalExecutor`（v4.2.0）が`COMPLETE` / `FAIL`の項目について
  `RetryQueueManager.remove(run_id)`を呼び出す
* `RetryQueueCleanupDecider` / `RetryQueueCleanupExecutor`（v4.3.0）が
  `NOOP`のうち`retry_result.outcome == SKIPPED`の項目についてのみremoveを
  呼び出す。`NOT_FOUND` / `DISABLED`由来の`NOOP`はいずれもKEEPのまま
  据え置かれ、Cleanup方針の検討はFuture Extensionとして持ち越された

本Release（v4.4.0）は、`retry_engine`パッケージに**Terminal/Transient分類を
唯一の判断基準とする新規Cleanup層**を追加する。まず`RetryOutcome`の各値が
Terminal（今後その状態が変化する見込みがなく、恒久的にQueueに滞留し得る）か
Transient（判定条件が将来変化しうる、一時的な状態）かを分類する
（3.2節）。そのうえで、`NOT_FOUND` / `DISABLED`由来の`NOOP`について、この
分類結果に従ってCLEANUP／KEEPを判定し、CLEANUPと判定された項目のみ
`RetryQueueManager.remove(run_id)`を呼び出す。

```
Retry Engine（受信・整理・実行・判定・除去・Cleanup、v3.0.0〜v4.3.0）
   │
   ├── decide_retry_queue_updates()（v4.1.0、無改修）
   ├── apply_retry_queue_removals()（v4.2.0、無改修）
   │      → COMPLETE/FAILのみ remove_fn を呼び出す
   ├── apply_retry_queue_cleanup()（v4.3.0、無改修）
   │      → NOOPのうちSKIPPED由来のみ remove_fn を呼び出す
   │
   └── decide_retry_queue_terminal_cleanup() ★新設
          │
          ├─► RetryOutcomeTerminality分類表 ★新設（3.2節。v4.4.0の新規Deciderに
      │      対してのみSingle Source of Truth。v4.1.0〜v4.3.0は参照しない）
          │
          └─► RetryQueueTerminalCleanupDecider ★新設
                 （判定：NOOPのうちNOT_FOUND/DISABLED由来のみ、
                   分類表を参照してCLEANUP/KEEPを判定。それ以外はKEEP）
                 │
                 ▼
             RetryQueueTerminalCleanupDecision ★新設データ構造

      apply_retry_queue_terminal_cleanup() ★新設
          │
          ├── decide_retry_queue_terminal_cleanup() を呼び出す
          │
          └─► RetryQueueTerminalCleanupExecutor ★新設（CLEANUPのみ remove_fn を呼び出す）
                 │
                 ▼
             RetryQueueTerminalCleanupResult ★新設データ構造
```

`RetryQueueUpdateDecider` / `RetryQueueRemovalExecutor` /
`RetryQueueCleanupDecider` / `RetryQueueCleanupExecutor` / `RetryQueueManager`
はいずれも無改修。新しいQueueステータス（Dead Letter・隔離Queue等）は
導入しない。

---

## 2. Design Policy

* **Foundation First**：Terminal/Transient分類表を確立し、`NOT_FOUND` /
  `DISABLED`由来の`NOOP`についてその分類からCLEANUP／KEEPを導出できる
  ところまでを行う。分類の動的な切り替え（運用者が設定でTerminal/Transient
  判定を上書きする等）は対象外
* **Single Responsibility**：`RetryQueueTerminalCleanupDecider`は判定のみ、
  `RetryQueueTerminalCleanupExecutor`は除去実行のみを担う。v4.3.0の
  Decider/Executor分離パターンを踏襲する
* **Stateless**：両コンポーネントとも内部状態を一切保持しない
* **単一の判断基準（Single Source of Truth、権威範囲を限定）**：
  `RetryQueueTerminalCleanupDecider`（本Release新設）のCleanup方針は
  `RetryOutcomeTerminality`分類表（3.2節）からのみ導出し、`Decider`の
  コード内に個々の`RetryOutcome`値の判定を直接ハードコードしない。
  **ただしこの「Single Source of Truth」は本Release新設コンポーネントに
  対してのみ権威を持つ**：v4.1.0`RetryQueueUpdateDecider`・v4.2.0
  `RetryQueueRemovalExecutor`・v4.3.0`RetryQueueCleanupDecider`は
  ゼロ改修方針（Charter）のため本表を参照せず、`COMPLETE` / `FAIL` /
  `SKIPPED`の判定ロジックを引き続き自コード内に個別に保持する
  （Architecture Review 12.1節）。将来`RetryOutcome`に新しい値が
  追加された場合、v4.4.0新規Deciderが扱う範囲については分類表に1行
  追加するだけでCleanup方針が定まるが、v4.1.0〜v4.3.0が扱う既存outcome
  （COMPLETE/FAIL/SKIPPED）については本表を変更しても既存コンポーネントの
  挙動には影響しない。この不一致を検知するため、実装時に
  「`RETRY_OUTCOME_TERMINALITY`がCOMPLETE/FAIL/SKIPPEDについて返す分類と、
  v4.2.0/v4.3.0が実際にremoveを実行する範囲が一致すること」を確認する
  整合性ガードテストを追加する（6章・Architecture Review Recommendation 1）
* **既存コンポーネントの再利用**：既存の`RetryQueueManager.remove()`を
  再利用し、`RetryQueueUpdateDecider` / `RetryQueueCleanupDecider`等が
  既に判定済みの`RetryQueueUpdateDecision`を入力とする

---

## 3. Terminal/Transient分類

### 3.1 定義

| 分類 | 定義 |
|---|---|
| **Terminal（終端状態）** | 判定条件そのものが将来変化する見込みがなく、同じ`run_id`に対して同じ判定を再実行しても結果が変わらないと合理的に言える状態。Queueに滞留し続けても、状況が好転する余地がない |
| **Transient（一時状態）** | 判定条件（設定値・外部システムの状態等）が将来変化しうる状態。現時点ではCleanup対象外と判定されても、条件が変われば異なる結果になりうる |

### 3.2 各`RetryOutcome`の分類（v4.4.0新規Deciderに対するSingle Source of Truth）

`RetryOutcome`（`retry_result.py`）の4値、および`RetryQueueUpdateDecision.outcome`
（`COMPLETE` / `FAIL`、いずれも`RETRIED`由来）を含めた5区分について、
実装（`retry_manager.py` / `workflow_monitor.py` / `execution_history_store.py`）を
根拠に分類する。

> **権威範囲の明示（Architecture Review 12.1節 Recommendation 1反映）**：
> 本表は`RetryQueueTerminalCleanupDecider`（v4.4.0新設）が`NOT_FOUND` /
> `DISABLED`由来の`NOOP`を判定する際の唯一の判断基準である。`COMPLETE` /
> `FAIL` / `SKIPPED`の行は「本表の分類方式を適用した場合の参考値」として
> 記載しているに過ぎず、v4.1.0〜v4.3.0の既存コンポーネントは本表を
> 参照せず、それぞれのファイル内に個別の判定ロジックを保持したままである
> （ゼロ改修方針）。

| Outcome（判定の起源） | Terminal? | 根拠 | Cleanup方針 |
|---|---|---|---|
| `COMPLETE`（`RETRIED`＋成功） | **Yes** | 実行が確定的に完了した事実は覆らない。v4.2.0で既にremove済みのはず | Remove（v4.2.0で確立済み、本Release対象外） |
| `FAIL`（`RETRIED`＋失敗） | **Yes** | 同上 | Remove（v4.2.0で確立済み、本Release対象外） |
| `SKIPPED` | **Yes** | `RetryPolicy.max_attempts`到達は試行回数という後戻りしない事実に基づく判定であり、再評価しても結果は変わらない | Remove（v4.3.0で確立済み、本Release対象外） |
| `DISABLED` | **No（Transient）** | `RetryOutcome.DISABLED`は`RETRY_ENGINE_ENABLED=false`または下位ゲート閉鎖という**判定時点の設定値のスナップショット**（`retry_manager.py` `NullRetryManager._DISABLED_REASON`：`"RETRY_ENGINE_ENABLED=false, or AI_AGENT_ENABLED/WORKFLOW_ENGINE_ENABLED is not ready"`）。設定は運用者が後から変更しうるため、同じQueue項目が将来的に有効な再試行対象へ戻る余地がある。**この判断は`RetryQueueManager`（v3.1.0）がメモリ上の`dict`のみで構成され、Queue永続化が本Release時点でもNon-Goalのままであること（プロセス再起動でQueueがリセットされるため無制限な永続的肥大化は起こらない）を前提とする（Architecture Review 12.4節 Recommendation 4、9章Future Extension参照）** | **Keep**（本Releaseで確定。Queue永続化導入時は要再評価） |
| `NOT_FOUND` | **Yes（条件付きTerminal）** | 4章で詳述 | **Remove**（本Releaseで確定。4.3節の残存リスクを Known Limitationとして明記） |

### 3.3 拡張性

将来`RetryOutcome`に新しい値（例：`ABORTED`・`RATE_LIMITED`等）が追加された
場合、本表に1行追加し、その値がTerminalかTransientかを判断するだけで
Cleanup方針が定まる。`RetryQueueTerminalCleanupDecider`のコード自体を
変更する必要はない（5章 Package Structure・6章 Public APIで、分類表を
`Decider`が参照するデータとして分離する設計とする）。

---

## 4. `NOT_FOUND`のTerminal/Transient判定根拠（Workflow Monitor仕様確認）

Charterで指示された「Workflow Monitorの仕様を確認し、`NOT_FOUND`が
Transientになり得るか」について、以下のコードを根拠に判定する。

### 4.1 `NOT_FOUND`は削除のない読み取り専用ストアからの欠落

* `WorkflowMonitor.get_status(run_id)`（`workflow_monitor.py`37〜42行目）は
  `self._store.get(run_id)`（`ExecutionHistoryStore.get()`）への単純な
  委譲であり、キャッシュ・独自状態を一切持たない（Stateless、同ファイル
  9〜10行目のdocstring）。`record is None`の場合にのみ`RetryManager.retry()`
  側で`NOT_FOUND`が生成される（`retry_manager.py`271〜277行目）。
* `ExecutionHistoryStore`（ABC、`execution_history_store.py`）が公開する
  メソッドは`save()` / `get()` / `list_all()`の3つのみで、**削除
  （delete）操作は存在しない**。`save()`のdocstring
  （`execution_history_store.py`10〜12行目）は「同一run_idへの複数回の
  上書き保存が正常系」と明記しており、レコードは`start_run()`で作成された
  後、`finish_run()`等で上書き更新されるのみで、消えることはない。
* したがって、**一度でも`run_id`のレコードが作成されれば、以後
  `get_status()`が`None`を返すことは二度とない**（Terminalの根拠その1：
  「found」は不可逆）。

### 4.2 「NOT_FOUNDから見つかる状態へ」遷移する経路が現時点で存在しない

* 残る問題は逆方向、すなわち「現時点で`NOT_FOUND`の`run_id`が、後から
  レコードを獲得して見つかるようになる」経路が存在するかである。
* `RetryManager.enqueue_retry(run_id, workflow_name, ...)`
  （`retry_manager.py`）は`RetryQueueManager.enqueue()`への薄い委譲のみで、
  `run_id`がExecution Historyに実在するかの検証を一切行わない
  （`docs/design/retry_queue_integration.md`11.2節「バリデーション（型・値の
  妥当性チェック）は既存どおり`RetryQueueManager`側の責務のままとする」と
  明記。`RetryQueueManager`側にもExecution History参照は存在しない）。
* `RetryEventConsumer.recognize()`（`retry_event_consumer.py`）は
  Scheduler側の`"retry:"`プレフィックス付き`SchedulerEvent`から
  `RetryQueueItem`（＝手動または将来のComposition Rootで`enqueue_retry()`
  された項目）を素通しするだけであり、Execution Historyとの突き合わせは
  行わない。
* 「Workflow Monitorが`FAILED`/`TIMEOUT`と判定した`run_id`を自動的に
  Retry Queueへenqueueする」という自動配線（Composition Root）は、
  v3.3.0〜v4.3.0のいずれのCharterでも一貫して**Non-Goal**として持ち越されて
  いる（`docs/design/retry_queue_removal_foundation_charter.md`10章
  「実運用のComposition Root」等）。つまり**現時点のコードベースには、
  レコード未作成の`run_id`が後から自動的にExecution Historyへ記録される
  自己修復的な経路が存在しない**。
* 概念上も、「Retry」とは既に実行され失敗/タイムアウトと判定された
  `run_id`を再実行する行為であり、その判定が成立するためには当該`run_id`の
  レコードが判定時点で既に存在している必要がある（`WorkflowMonitor._judge()`
  はレコードが存在する前提でのみ`FAILED`/`TIMEOUT`を返す）。したがって
  正当な運用下でのRetry候補は、Queueに投入される時点で既にレコードを
  持っているはずである。

### 4.3 結論と残存リスク（Known Limitation）

以上より、**`NOT_FOUND`はTerminalとして扱う**。根拠：(a)
一度foundになったレコードが再びNOT_FOUNDに戻ることはない（不可逆）、
(b) 現在のコードベースには、NOT_FOUNDだった`run_id`が後から自動的に
foundへ遷移する経路が存在しない、(c) 正当な運用下でのRetry候補は
概念上レコードを既に持っているはずである。

ただし、`enqueue_retry()`が`run_id`の妥当性検証を行わない構造上、
理論上は「Workflow Engineがまだ実行・記録していない`run_id`」を誤って
enqueueするケース（オペレーションミス・外部システムからの誤ったID連携等）が
構造的に排除されてはいない。この場合、Cleanupで当該Queue項目を除去した
直後に、たまたま同じ`run_id`でWorkflow Engineが実行されても、その実行結果と
Retry Queueとの関連付けは失われる。これは**本Releaseが新たに生むリスクでは
なく、v3.2.0（Retry Queue Integration）以来`enqueue_retry()`が無検証で
あることに由来する既存のリスク**であり、9章 Boundaryおよび11章
Risks and Mitigationsに既知の限界（Known Limitation）として明記し、
Cleanup実行を妨げない。

> **`NOT_FOUND`分類の見直し条件（Architecture Review 12.3節 Recommendation 3
> 反映）**：将来、以下のいずれかがコードベースに追加された場合、本節の
> 分類を再評価する必要がある。
> 1. `enqueue_retry()`にExecution Historyとの参照整合性チェック
>    （enqueue時に`run_id`の実在を検証する処理）が追加された場合
>    （＝レースの可能性自体が構造的に排除されるため、Terminalの結論は
>    むしろ強化される方向の見直しになる）
> 2. 「Workflow Engineがまだ実行していない`run_id`」を正当なRetry候補として
>    扱う新機能（先行enqueue・予約実行等）が追加された場合（＝この場合は
>    NOT_FOUNDがTransientになりうる方向への見直しが必要になる）
>
> なお、Workflow MonitorのFAILED/TIMEOUT判定を自動的にRetry Queueへ
> enqueueする「Composition Root」の整備は、上記1の実施如何にかかわらず、
> 「Retry候補としてenqueueされるrun_idは事前にExecution Historyへ
> 記録済みである」という前提を強化する方向に働く。したがって
> **Composition Rootの整備自体はNOT_FOUND＝Terminalという結論を揺るがす
> 要因ではなく、むしろ裏付ける要因である**（Composition Root整備を
> 見直しの契機として扱わない）。

---

## 5. Package Structure（変更差分）

```
src/retry_engine/
├── retry_outcome_terminality.py          ★新規
│     RetryOutcomeTerminality（TERMINAL / TRANSIENT）
│     RETRY_OUTCOME_TERMINALITY: dict     ← 3.2節の分類表を実体化した定数
│     classify_terminality(reason) -> RetryOutcomeTerminality
├── retry_queue_terminal_cleanup_decider.py   ★新規
│     RetryQueueCleanupOutcome（v4.3.0 と同じ CLEANUP / KEEP を再利用）
│     RetryQueueTerminalCleanupDecision（update_decision / outcome / reason）
│     RetryQueueTerminalCleanupDecider（decide() / decide_all()）
├── retry_queue_terminal_cleanup_executor.py  ★新規
│     RetryQueueTerminalCleanupResult（decision / attempted / queue_result / reason）
│     RetryQueueTerminalCleanupExecutor（apply() / apply_all()）
├── retry_manager.py                       ★変更
│     RetryManager.__init__ / from_config() に
│         terminal_cleanup_decider / terminal_cleanup_executor 引数を追加（末尾・デフォルトNone）
│     RetryManager.decide_retry_queue_terminal_cleanup() ★新設
│     RetryManager.apply_retry_queue_terminal_cleanup()  ★新設
│     NullRetryManager に同名2メソッド ★新設（常に[]を返す）
└── __init__.py                            ★変更（新規7シンボルexport）
```

`retry_queue_update_decider.py` / `retry_queue_removal_executor.py` /
`retry_queue_cleanup_decider.py` / `retry_queue_cleanup_executor.py`を
含む既存ファイルは無改修（ゼロ改修）。

`RetryQueueCleanupOutcome`（v4.3.0で定義済みの`CLEANUP` / `KEEP`の2値
Enum）は本Releaseでも同じ意味で再利用する。新しいEnumとして重複定義は
しない（`retry_queue_terminal_cleanup_decider.py`が
`retry_queue_cleanup_decider.py`から`RetryQueueCleanupOutcome`をimportする）。

> **命名の相互参照（Architecture Review 12.2節 Recommendation 2反映）**：
> `retry_queue_terminal_cleanup_decider.py` / `retry_queue_terminal_cleanup_executor.py`
> のモジュールdocstring冒頭に、以下を明記する。
> 「本ファイルはv4.3.0の`RetryQueueCleanupDecider`（`retry_queue_cleanup_decider.py`、
> `SKIPPED`由来の`NOOP`専用）とは別の新規コンポーネントである。名称が
> 似ている（`RetryQueueCleanupDecider` vs `RetryQueueTerminalCleanupDecider`）
> ため混同しないこと。本コンポーネントの対象は`NOT_FOUND` / `DISABLED`由来の
> `NOOP`のみであり、`SKIPPED`由来の`NOOP`は`RetryQueueCleanupDecider`
> （v4.3.0、無改修）の責務のまま変わらない。」
> `retry_queue_cleanup_decider.py`自体はゼロ改修方針のため変更しないが、
> 本設計書・実装コメントの双方で上記の対比を明示することで、命名の
> 視認性の懸念（Architecture Review 12.2節）に対応する。

---

## 6. Public API

```python
# retry_outcome_terminality.py

class RetryOutcomeTerminality(Enum):
    TERMINAL = "terminal"
    TRANSIENT = "transient"


class RetryCleanupReason(Enum):
    """Cleanup判定のための、判定起源を表す軽量な識別子。
    RetryQueueUpdateDecision.outcome と retry_result.outcome の組から一意に導出する。"""
    COMPLETE = "complete"
    FAIL = "fail"
    SKIPPED = "skipped"
    NOT_FOUND = "not_found"
    DISABLED = "disabled"


RETRY_OUTCOME_TERMINALITY: dict[RetryCleanupReason, RetryOutcomeTerminality] = {
    RetryCleanupReason.COMPLETE: RetryOutcomeTerminality.TERMINAL,
    RetryCleanupReason.FAIL: RetryOutcomeTerminality.TERMINAL,
    RetryCleanupReason.SKIPPED: RetryOutcomeTerminality.TERMINAL,
    RetryCleanupReason.NOT_FOUND: RetryOutcomeTerminality.TERMINAL,
    RetryCleanupReason.DISABLED: RetryOutcomeTerminality.TRANSIENT,
}


def classify_reason(update_decision: RetryQueueUpdateDecision) -> RetryCleanupReason: ...
def classify_terminality(reason: RetryCleanupReason) -> RetryOutcomeTerminality: ...


# retry_queue_terminal_cleanup_decider.py

@dataclass(frozen=True)
class RetryQueueTerminalCleanupDecision:
    update_decision: RetryQueueUpdateDecision
    outcome: RetryQueueCleanupOutcome        # v4.3.0のEnumを再利用（CLEANUP / KEEP）
    reason: str


class RetryQueueTerminalCleanupDecider:
    """NOT_FOUND / DISABLED由来のNOOPのみを対象に、RETRY_OUTCOME_TERMINALITY分類表を
    参照してCLEANUP/KEEPを判定する。COMPLETE/FAIL/SKIPPED（他コンポーネントの責務範囲）
    はKEEPのまま素通しする（対象外）。"""
    def decide(self, update_decision: RetryQueueUpdateDecision) -> RetryQueueTerminalCleanupDecision: ...
    def decide_all(self, update_decisions: list[RetryQueueUpdateDecision]) -> list[RetryQueueTerminalCleanupDecision]: ...


# retry_queue_terminal_cleanup_executor.py

RemoveFn = Callable[[str], RetryQueueResult]

@dataclass(frozen=True)
class RetryQueueTerminalCleanupResult:
    decision: RetryQueueTerminalCleanupDecision
    attempted: bool
    queue_result: RetryQueueResult | None
    reason: str


class RetryQueueTerminalCleanupExecutor:
    def apply(self, decision: RetryQueueTerminalCleanupDecision, remove_fn: RemoveFn) -> RetryQueueTerminalCleanupResult: ...
    def apply_all(self, decisions: list[RetryQueueTerminalCleanupDecision], remove_fn: RemoveFn) -> list[RetryQueueTerminalCleanupResult]: ...


# RetryManager（追加分のみ）
def decide_retry_queue_terminal_cleanup(self, events: list[SchedulerEvent], dry_run: bool = False) -> list[RetryQueueTerminalCleanupDecision]: ...
def apply_retry_queue_terminal_cleanup(self, events: list[SchedulerEvent], dry_run: bool = False) -> list[RetryQueueTerminalCleanupResult]: ...
```

`RetryQueueTerminalCleanupDecider`の内部判定ロジックは、`COMPLETE` /
`FAIL` / `SKIPPED`由来の項目についても`classify_reason()` /
`classify_terminality()`を通せば同じくTERMINALという結果が得られる
（3.2節表の整合性）。ただし本Releaseでは**構造的に**`NOT_FOUND` /
`DISABLED`由来の項目のみをCLEANUP判定の対象とし、それ以外
（`COMPLETE` / `FAIL` / `SKIPPED`）は「他コンポーネントの責務範囲」という
理由でKEEPのまま素通しする（v4.2.0 / v4.3.0との重複除去・二重remove呼び出しを
避けるため。8章 Boundaryで詳述）。

---

## 7. Sequence（apply_retry_queue_terminal_cleanup()）

```
呼び出し元
   │
   ▼
RetryManager.apply_retry_queue_terminal_cleanup(events, dry_run)
   │
   ├─► self.decide_retry_queue_terminal_cleanup(events, dry_run)
   │        │
   │        ├─► self.decide_retry_queue_updates(events, dry_run)（v4.1.0、無変更）
   │        │        → list[RetryQueueUpdateDecision]
   │        │
   │        └─► self._terminal_cleanup_decider.decide_all(update_decisions)
   │                 │
   │                 ├─ classify_reason(decision) で起源を特定
   │                 ├─ COMPLETE/FAIL/SKIPPED → KEEP（対象外）で即返す
   │                 └─ NOT_FOUND/DISABLED → classify_terminality(reason) を参照
   │                        ├─ TERMINAL（NOT_FOUND）→ CLEANUP
   │                        └─ TRANSIENT（DISABLED）→ KEEP
   │                 → list[RetryQueueTerminalCleanupDecision]
   │
   └─► self._terminal_cleanup_executor.apply_all(decisions, remove_fn=self._queue.remove)
            → CLEANUPの項目（NOT_FOUND由来）のみ remove_fn(run_id) を呼び出す
            → list[RetryQueueTerminalCleanupResult]
```

v4.3.0の`apply_retry_queue_cleanup()`と同様、`decide_retry_queue_updates()`が
内部で`execute_dispatchable_retries()`（再実行の実行を含む）を呼び出すため、
`apply_retry_queue_removals()` / `apply_retry_queue_cleanup()` /
`apply_retry_queue_terminal_cleanup()`を同じ`events`に対して複数回呼び出すと
再実行が複数回実行される点は、v4.0.0〜v4.3.0の既存の呼び出しグラフ構造を
そのまま踏襲する（本Releaseで新たに導入する性質ではない）。

---

## 8. Boundary（今回入れない境界線）

* `RetryQueueTerminalCleanupDecider` / `Executor`は`RetryQueueManager` /
  `NullRetryQueueManager`型への直接依存を持たない
* `COMPLETE` / `FAIL` / `SKIPPED`由来の項目の再判定・二重remove呼び出しは
  行わない（v4.2.0 / v4.3.0の責務のまま）。`classify_terminality()`は
  これらに対してもTERMINALを返しうるが、`RetryQueueTerminalCleanupDecider`は
  構造的にこれらをKEEP（対象外）として素通しし、remove_fnを呼び出さない
* `DISABLED`由来の`NOOP`のCleanupは対象外のまま（3.2節でTransientと分類。
  `RETRY_ENGINE_ENABLED`再有効化後の自動再試行・自動再enqueueの仕組みは
  導入しない）
* `NOT_FOUND`のCleanup実行前に、Execution Historyへの記録タイミングとの
  厳密な整合性検証（例：一定時間の猶予期間を設ける、再度`get_status()`を
  呼び直して確認する等）は行わない（4.3節のKnown Limitationとして許容する）
* Dead Letter Queue・隔離Queueといった新しいQueueステータスの追加は
  行わない
* Cleanup基準のカスタマイズ（猶予期間・優先度に基づく選別等）は行わない

---

## 9. Future Extension

* `RETRY_OUTCOME_TERMINALITY`分類表を、将来`RetryOutcome`に新しい値
  （`ABORTED`・`RATE_LIMITED`等）が追加された際にそのまま拡張する
* `DISABLED`由来のQueue項目について、`RETRY_ENGINE_ENABLED`再有効化を
  検知して自動的に再試行・再enqueueする仕組み（3.2節でTransientと
  分類したことの裏返しとして、「有効化されたら再試行できる」という
  積極的な仕組み自体は本Releaseでは作らない）
* **Queue永続化との依存関係（Architecture Review 12.4節 Recommendation 4
  反映）**：`DISABLED`をKeepとする本Releaseの判断は、`RetryQueueManager`
  （v3.1.0）がメモリ上の`dict`のみで構成され、プロセス再起動でQueueが
  リセットされることを前提としている。将来Queue永続化（SQLite/Redis等、
  v3.1.0以来一貫してNon-Goal）が実装された場合、`DISABLED`由来項目は
  再起動を挟んでも消えずに残り続けることになり、「無制限肥大化のリスクは
  現状小さい」という3.2節の前提が崩れる。**Queue永続化のCharter作成時に、
  本Release（v4.4.0）の`DISABLED`＝Keep判断を必ず再評価すること**
* `NOT_FOUND`のCleanupに猶予期間（grace period）を設け、直近enqueueされた
  項目はレースの可能性を考慮して即座にはCLEANUPしない、といった精密化
* v4.2.0`RetryQueueRemovalExecutor` / v4.3.0`RetryQueueCleanupDecider`を
  本Releaseの`RETRY_OUTCOME_TERMINALITY`分類表を参照する形に統合する
  リファクタリング（本Releaseではゼロ改修方針のため見送り）
* Cleanup実行の定期スケジューリング（Composition Root）
* Cleanup件数・滞留時間のMetrics化

---

## 10. Compatibility

* `RetryManager.__init__` / `from_config()`への
  `terminal_cleanup_decider` / `terminal_cleanup_executor`引数追加は
  末尾のデフォルト値付き引数のみであり、既存呼び出し（新規引数を渡さない
  場合）は本Release後もまったく同じ結果になる
* `retry()` / `enqueue_retry()` / `dequeue_retry()` /
  `recognize_retry_events()` / `dispatch_retry_events()` /
  `execute_dispatchable_retries()` / `decide_retry_queue_updates()` /
  `apply_retry_queue_removals()` / `decide_retry_queue_cleanup()` /
  `apply_retry_queue_cleanup()`（`RetryManager` / `NullRetryManager`とも）は
  1行も変更していない

---

## 11. Risks and Mitigations

| リスク | 対策 |
|---|---|
| `NOT_FOUND`をTerminalとしてCLEANUPした直後に、誤って/後から同一`run_id`でWorkflow Engineが実行されると、Retry Queueとの関連付けが失われる（4.3節Known Limitation） | `enqueue_retry()`の無検証という既存のリスクに由来するものであり、本Releaseで新たに生むリスクではないことをドキュメントに明記する。運用上はrun_idの生成規則（重複しないID体系）を前提とする |
| `DISABLED`をTransientとしてKeepし続けることで、`RETRY_ENGINE_ENABLED=false`のまま長期間運用された場合にQueueが際限なく滞留する | 本Releaseでは検知・自動対応の仕組みは作らないが、Future Extension（9章）に「再有効化検知による自動再試行」を明記し、次Release以降の検討事項として可視化する |
| `RETRY_OUTCOME_TERMINALITY`分類表と、既存v4.2.0/v4.3.0のハードコードされた判定ロジックが将来ズレる（分類表を更新しても既存Deciderには反映されない） | 5章で明記のとおり、v4.2.0/v4.3.0は無改修のまま維持し、本分類表はv4.4.0の新規Deciderのみが参照する。将来の統合（9章）まではこの二重管理状態を許容し、`RETRY_OUTCOME_TERMINALITY`のコメントに「v4.2.0/v4.3.0は本表を参照していない」旨を明記する |

---

## 12. Architecture Review

**結論：Approve with Recommendations**

ユーザー指定の5観点それぞれについて、既存コード（`retry_queue_cleanup_decider.py` /
`retry_manager.py`のコンストラクタ）を確認したうえで評価する。

### 12.1 観点1：`RetryOutcomeTerminality`は既存Cleanup系コンポーネントと責務が重複しないか

**評価：軽微な重複あり（Approve、ただしドキュメント修正を推奨）**

`retry_queue_cleanup_decider.py`58〜79行目を確認したところ、
`RetryQueueCleanupDecider.decide()`は`update_decision.outcome != NOOP`を
KEEP、`retry_result.outcome == SKIPPED`をCLEANUPと**その場でハードコード
判定**しており、外部の分類テーブルを一切参照していない。同様に
`RetryQueueRemovalExecutor`（v4.2.0）もCOMPLETE/FAILを直接判定する。

つまり、「SKIPPEDはTerminal」「COMPLETE/FAILはTerminal」という**知識は
既にv4.2.0/v4.3.0のコード内に暗黙的に埋め込まれている**。本Releaseの
`RETRY_OUTCOME_TERMINALITY`テーブルは、この知識をNOT_FOUND/DISABLEDを
含めて明示的に一覧化するが、**v4.2.0/v4.3.0のコード自体はこのテーブルを
参照しない**（ゼロ改修方針のため）。したがって5章の「Single Source of
Truth」という表現は、v4.4.0の新規Deciderに対しては正確だが、
プロジェクト全体で見ると字義通りには成立していない。

これは設計上の欠陥ではなく、「既存コンポーネント無改修」という
Charterの制約から必然的に生じる二重管理状態であり、11章Risksでも
既に一部言及されている。ただし、将来`RETRY_OUTCOME_TERMINALITY`の
分類を変更した際にv4.2.0/v4.3.0の実際の挙動とズレる可能性がある点は、
ドキュメントの記述だけでなく**テストで検知できるようにすべき**。

> **Recommendation 1**：実装時、`RETRY_OUTCOME_TERMINALITY`が
> `COMPLETE` / `FAIL` / `SKIPPED`に対して返す分類結果（いずれもTERMINAL）
> と、実際にv4.2.0`RetryQueueRemovalExecutor`・v4.3.0
> `RetryQueueCleanupDecider`がCLEANUP/removeを実行する範囲が一致することを
> 確認する「整合性ガードテスト」を追加する。また`retry_outcome_terminality.py`
> のモジュールdocstringに「本表はv4.4.0の新規Deciderに対してのみ権威を持つ。
> v4.1.0〜v4.3.0は本表を参照しない（ゼロ改修）」と明記し、「Single Source
> of Truth」という表現の適用範囲を限定する。

### 12.2 観点2：`RetryQueueTerminalCleanupDecider` / `Executor`という命名は`RetryQueueCleanupDecider`と混同されないか

**評価：構造的な衝突はないが、視認性の懸念あり（Approve、命名は維持しつつ注記を推奨）**

クラス名・ファイル名・importパスはいずれも異なり（`retry_queue_cleanup_decider.py`
vs `retry_queue_terminal_cleanup_decider.py`）、Python上の名前衝突・
`__init__.py`でのexport衝突は発生しない（`__init__.py`122行目以降の
`__all__`を確認、重複なし）。

一方で、「Cleanup」と「Terminal Cleanup」という名称は目視・タイプミス・
grep検索で混同されやすい。CLAUDE.mdに「私はプログラミング初心者です」と
明記されている運用者にとって、この種の近似した命名は将来の保守時に
誤ったファイルを編集するリスクを高める。Charter Open Question 4は
「対象outcomeを名称に含める」という代替案も提示していたが、本設計は
抽象化（Terminal/Transient）を主題とするため「Terminal」を採用した
判断自体は本Releaseの目的（ユーザー指示）と整合しており、変更は不要と
判断する。

> **Recommendation 2**：`retry_queue_terminal_cleanup_decider.py` /
> `retry_queue_terminal_cleanup_executor.py`のモジュールdocstring冒頭に、
> 「v4.3.0の`RetryQueueCleanupDecider`（SKIPPED専用）とは別の新規
> コンポーネントであり、混同しないこと。対象はNOT_FOUND/DISABLED由来の
> `NOOP`のみ」という一文を明記する（他ファイルが既に採用している
> 「本ファイルとv4.x.0の関係」を明示する既存の記法パターンを踏襲する）。

### 12.3 観点3：`NOT_FOUND`をTerminalとする判断は、現行コードの制約に基づくものであり、将来のComposition Root整備時に見直し可能か

**評価：見直し可能な設計だが、見直し条件の記述をより正確にすべき（Approve with Recommendation）**

`RETRY_OUTCOME_TERMINALITY[RetryCleanupReason.NOT_FOUND]`は辞書の1エントリ
であり、これを`TRANSIENT`に変更するだけで`RetryQueueTerminalCleanupDecider`
のコード自体には手を入れずに挙動を反転できる（5章・9章で確認）。この点は
設計として妥当。

ただし、4.3節・9章に書かれている「将来のComposition Root整備時に見直す」
という表現はやや不正確である。Composition Root（Workflow MonitorのFAILED/
TIMEOUT判定を自動でRetry Queueへenqueueする仕組み）が整備されれば、
「Retry候補としてenqueueされるrun_idは必ず事前にExecution Historyへ
記録済みである」という前提がむしろ**強化**され、NOT_FOUND＝Terminalという
結論はより強く支持される。

NOT_FOUNDの分類を実際に見直すべき条件は、Composition Rootの整備ではなく、
以下のいずれかがコードベースに追加された場合である。

* `enqueue_retry()`にExecution Historyとの参照整合性チェック（enqueue時に
  `run_id`の実在を検証する）が追加された場合（＝レースの可能性自体が
  構造的に排除される。この場合はTerminalの結論がさらに強まる方向）
* 「Workflow Engineがまだ実行していない`run_id`」を正当なRetry候補として
  扱う新機能（先行enqueue・予約実行等）が追加された場合（＝この場合は
  逆にNOT_FOUNDがTransientになりうる方向への変更が必要）

> **Recommendation 3**：4.3節・9章の「将来のComposition Root整備時に
> 見直す」という記述を、上記2条件（enqueue時検証の追加／先行enqueue機能の
> 追加）に置き換える。Composition Root自体はNOT_FOUND＝Terminalの結論を
> 揺るがす要因ではなく、むしろ裏付ける要因であることを明記する。

### 12.4 観点4：`DISABLED`をKeepとする判断は、Queue滞留リスクよりも安全性を優先する判断として妥当か

**評価：妥当（Approve）**

`DISABLED`をCLEANUPしてしまうと、`RETRY_ENGINE_ENABLED`を再度`true`に
戻した運用者が気づかないうちに再試行機会を恒久的に失う（誤って消えた
Queue項目は二度と復元できない）。一方、Keepし続けることによる実害は
「Queueに項目が残り続ける」ことのみであり、以下の理由で現時点では実害が
限定的である。

* `RetryQueueManager`（v3.1.0）はメモリ上の`dict`のみで構成され、Queue
  永続化（SQLite/Redis等）は本Release時点でも一貫してNon-Goalのまま
  （`docs/ROADMAP.md` v3.1.0の記載）。プロセスを再起動すればQueueは
  リセットされるため、無制限な永続的肥大化は現状の実装では起こらない
* `RETRY_ENGINE_ENABLED=false`は運用者が意図的に切り替える設定であり、
  高頻度で発生する状態ではないと想定される

「削除して復元不能になるリスク」と「残り続けて多少のメモリを使うリスク」
を比較すれば、後者を許容する判断は安全側に倒す設計として妥当である。

> **Recommendation 4**：9章Future Extensionに、「Queue永続化
> （将来Release候補）が実装された場合、DISABLED由来項目のKeep方針は
> 前提（プロセス再起動でリセットされる）が崩れるため、Queue永続化の
> Charter作成時に本Release（v4.4.0）のDISABLED Keep判断を再評価する
> 必要がある」という依存関係を明記する。

### 12.5 観点5：既存テスト・既存API・既存挙動を壊さないか

**評価：問題なし（Approve）**

* `RetryManager.__init__` / `from_config()`（`retry_manager.py`150〜163行目・
  191〜206行目）を確認したところ、v4.1.0〜v4.3.0で追加された引数は
  いずれも末尾・デフォルト`None`・`__init__`内でのフォールバック生成という
  一貫したパターンを採っている。本Releaseの`terminal_cleanup_decider` /
  `terminal_cleanup_executor`も同じ末尾追加とすることで、既存の位置引数
  呼び出し・キーワード引数呼び出しのいずれにも影響しない
* 新規メソッド名`decide_retry_queue_terminal_cleanup()` /
  `apply_retry_queue_terminal_cleanup()`は既存メソッド名
  （`decide_retry_queue_cleanup()` / `apply_retry_queue_cleanup()`等）と
  重複しないことを確認済み
* `__init__.py`（`__all__`）への追加はexportの追加のみで、既存シンボルの
  変更・削除は伴わない
* `retry_queue_update_decider.py` / `retry_queue_removal_executor.py` /
  `retry_queue_cleanup_decider.py` / `retry_queue_cleanup_executor.py`は
  いずれも本設計で変更対象に含まれておらず、実装時は`git diff`で
  無改修であることを機械的に確認できる（Charter Acceptance Criteria
  で既に要求済み）
* 既存回帰テスト（`test_e2e_v4_0_0` 〜 `test_e2e_v4_3_0`等）は本Releaseの
  新規メソッドを呼び出さない限り実行経路が変わらないため、影響を受けない

### 12.6 総括

5観点すべてでApprove。Recommendation 1〜4はいずれも実装の妨げになる
指摘ではなく、ドキュメント精度の向上・将来の一貫性検証テストの追加・
将来Releaseとの依存関係の明記に関するものである。Implementationへ進む
前に、これら4件を設計書へ反映することを推奨する。

---

## 13. Status

- [x] Project Charter 確定（ユーザー承認済み）
- [x] Architecture Design（本文書）確定
- [x] Architecture Review（Approve with Recommendations、4件）
- [x] Recommendation の設計書への反映（ユーザー承認済み）
- [x] 実装（`retry_outcome_terminality.py` / `retry_queue_terminal_cleanup_decider.py` /
      `retry_queue_terminal_cleanup_executor.py` / `retry_manager.py` / `__init__.py`）
- [x] 単体テスト（`tests/test_e2e_v4_4_0_retry_queue_notfound_disabled_cleanup_foundation.py`、
      123件、整合性ガードテスト含む）全PASS
- [x] ドキュメント更新（CHANGELOG `[v4.4.0]` / `[KI-13]`・ROADMAP.md）
