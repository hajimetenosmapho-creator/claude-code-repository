# v5.4.0 Retry Runtime Script Entry Point Foundation 設計書（Project Charter / Architecture Design）

作成日：2026-07-09
状態：確定（Architecture Review Final・ユーザー承認済み・Minor Recommendation 2件反映済み）

---

## 1. Project Charter

### 1.1 目的

`RetryRuntimeOrchestrator.run_once()`（v5.3.0）をCLIから1回だけ起動できる
Entry Point（`scripts/run_retry_runtime.py`）を追加する。v5.1.0〜v5.3.0で
積み上げた「組み立て（Composition Root）→実行順序決定（Orchestrator）」の
土台に、初めて実際に呼び出す入口を与えることが本Releaseの中核である。

### 1.2 背景

`docs/design/retry_runtime_run_once_foundation.md` 7章「Future Architecture
Consideration」・`docs/ROADMAP.md`（Retry Engine関連セクション）の両方が、
本Releaseで実装すべき内容を次の1行として既に明記していた。

> `RetryRuntimeOrchestrator.from_composition_root(RetryCompositionRoot.from_env()).run_once()`
> を1回呼び出すだけのEntry Point。

`run_once()`自体はv5.3.0で実装済みだが、これを呼び出すコードはテストコード
以外に存在せず、「消費者不在の実装」のままだった。本Releaseはこの空白を
埋めるものである。

### 1.3 Non-Goal（本Releaseで実施しないこと）

* `run_once()`への`dry_run`引数の追加（`retry_runtime_run_once_foundation.md` 4章の
  Known Issueが未解消のため。CLI側にも追加しない、8.3節で詳述）
* `--loop` / `--daemon`等、定期実行・常駐化に関するCLI引数・実装
* `RetryRuntimeOrchestrator` / `RetryCompositionRoot`への変更（いずれも無改修のまま）
* `RetryManager`・既存パッケージ（`workflow_monitor` 〜 `retry_scheduler_decision`）への変更
* 独自のExit Code体系（成功/一部失敗/異常等の多段階区分）の導入（8.4節で詳述）
* Summary Formatterクラスの実装（表示ロジックの局所化のみ行い、抽出は将来Releaseへ送る。8.8節で詳述）
* Windows タスクスケジューラへの登録作業そのもの（本Releaseはscript本体のみ）

---

## 2. Architecture Design（採用案）

### 2.1 scripts層の責務

**採用**：`scripts/run_retry_runtime.py`は「組み立てを依頼する」「1サイクル実行を
依頼する」「結果を人間向けに表示する」の3つのみを行う薄いEntry Pointとする。
既存script群（`run_workflow_engine.py`等）と同じ、Business Logicを持たない構成。

却下案：

| 案 | 却下理由 |
|---|---|
| scriptに実行順序判定・Retry対象フィルタ等を追加する | 実行順序の知識は`RetryRuntimeOrchestrator`に閉じるべき。scriptへ漏らすとSingle Responsibility違反 |

### 2.2 Entry Pointの責務 / Composition Root・Orchestratorとの責務分離

**採用**：

* scriptは`RetryCompositionRoot.from_env()`の内部構築ロジック（各Configの
  組み立て方）を一切知らない
* scriptは`RetryRuntimeOrchestrator.run_once()`の内部実行順序
  （Trigger→Scheduler→Manager→Decider/Executor群）を一切知らない
* scriptが直接importするのは`RetryCompositionRoot` / `RetryRuntimeOrchestrator`の
  2クラスのみ（`retry_engine`のDecider/Executor等は一切importしない）

却下案：

| 案 | 却下理由 |
|---|---|
| `RetryCompositionRoot` / `RetryRuntimeOrchestrator`のコンストラクタ引数を CLI引数化して細かく制御可能にする | YAGNI。消費者が本script1つの段階で先回りの柔軟性は不要（Development Charter 8章） |

### 2.3 CLI引数の必要性

**採用**：**引数なし**（`argparse`を持たない最小構成）。

- `run_once()`自体に分岐点（dry_run等）が存在しないため、渡すべき引数がない
- 将来loop対応時に`--loop`等を追加する余地は残すが、今回は追加しない

却下案：

| 案 | 却下理由 |
|---|---|
| `--dry-run`を追加する | `run_once()`はdry_run未対応（`retry_runtime_run_once_foundation.md` 4章 Known Issue）。CLIにだけ`--dry-run`を生やすと「指定したのに実際にQueue除去・History記録が起きた」という見せかけの安全機能になり、Development Charter 3章が最も警戒する誤動作を再現する |
| `--base-dir`を追加する | `RetryCompositionRoot.from_env(base_dir=None)`は省略時に自動算出する設計済み。外部から上書きする要求が現時点でない |

### 2.4 Exit Code Policy（Architecture Review Minor Recommendation #1 反映）

**採用**：

* **正常終了**：exit code `0`（Python標準。`main()`が例外なく`return`した場合の暗黙の0）
* **例外発生時**：Python標準の非0（fail-fastでそのまま伝播させ、traceback を
  標準エラー出力に出す。独自のtry/exceptで握りつぶさない）
* **独自Exit Code体系は導入しない**（0/1/2等の多段階区分、
  `RetryRuntimeCycleResult`の中身から成否を判定して返す仕組みは、いずれも追加しない）

理由：

* `run_once()`のDesign Policy「例外はそのまま呼び出し元へ伝播させる
  （fail-fast）」（`retry_runtime_run_once_foundation.md` 2.3節#6）と対称的な
  方針をEntry Point側でも維持するため
* 既存script群（`run_workflow_engine.py`等）もいずれも独自exit codeを持たず、
  成功時は暗黙の0、例外時はPython標準の非0という同じ方針を踏襲している

却下案：

| 案 | 却下理由 |
|---|---|
| `RetryRuntimeCycleResult`の内容（NOT_FOUND件数等）から成否を判定し独自exit code（0/1/2等）を返す | 「結果を解釈して成否を判定する」のはBusiness Logicであり、Decider層が既に判定済みの結果をscriptが再解釈するのは責務逸脱（2.1節の原則に反する）。将来Windows タスクスケジューラでの成否監視が本当に必要になった時点で、独立Releaseとして再検討する（7章 Future Architecture Consideration） |

### 2.5 ログ出力方針

**採用**：既存script群（`show_execution_history.py`等）と同じ`print()`ベースの
人間向けサマリー表示。`RetryRuntimeCycleResult`の各フィールドの件数
（Enqueue件数・Scheduler候補件数・実行件数・除去/cleanup/terminal cleanup件数・
history記録件数）を表示する。

却下案：

| 案 | 却下理由 |
|---|---|
| `src/logger/`（v1.8.0 Logging Foundation）を使った構造化ログ記録を追加する | `src/logger/`は記事生成フロー向けの既存資産でRetry Runtimeとは無関係。本Releaseへの巻き込みはNon-Goal（無関係な改善を混ぜない、Charter 4章） |

### 2.6 `RetryRuntimeCycleResult`の利用方法

**採用**：scriptは戻り値を受け取り、各フィールドの**件数**をそのまま表示するのみ
（加工・判定は行わない）。

特に重要な設計判断（**Gateが閉じている場合の扱い**）：

* `run_workflow_engine.py`は`isinstance(manager, NullWorkflowEngineManager)`を
  明示的にチェックして「無効です」メッセージを出す方式だが、
  `NullRetryManager.execute_dispatchable_retries()`は常に空リストを安全に
  返す設計（`retry_manager.py`で確認済み）であるため、**本scriptはNull判定を
  一切行わず、常に`run_once()`を呼び出して結果件数をそのまま表示する**
* 理由：Null Object Patternの意図は「呼び出し元がNullかどうかを意識しなくて
  よいこと」。scriptが`isinstance()`で`retry_engine`の内部実装型を知る設計は、
  既存Null Object Patternの意図に反し、scripts層の責務も超える
* Gateが閉じている場合、表示される件数はすべて0件になるだけで、エラーにも
  例外にもならない（`NullRetryManager` / `NullRetryQueueManager`等の既存設計で
  保証済み）

### 2.7 loop / daemonへの拡張性

**採用**：本Releaseは1回きりの実行のみ。

* loop（定期実行）はscriptに`while`ループや`--interval`引数を足す形で
  将来拡張可能な構造に留め、今回は実装しない
* daemon化（常駐プロセス化）は行わない。定期実行が必要な場合はWindows
  タスクスケジューラ等の**外部プロセス管理に委ねる**方針を維持
  （既存`news_agent_foundation.md`等と同じ方針）

### 2.8 Summary FormatterのDesign Note（Architecture Review Minor Recommendation #2 反映）

**採用**：表示ロジックを`format_summary(result: RetryRuntimeCycleResult) -> str`
という独立関数へ局所化する。`main()`は「組み立て→`run_once()`呼び出し→
`format_summary()`の呼び出し→`print()`」のみを行い、文字列組み立てのロジック
自体は`format_summary()`に閉じる。

* **今回はFormatterクラスの実装は行わない**（YAGNI。消費者が本script1つの
  段階でクラス化する理由がない）
* ただし、`format_summary()`の引数を`RetryRuntimeCycleResult`単体、戻り値を
  `str`単体に絞ることで、将来複数の出力形式（JSON出力・Slack通知向け整形等）
  が必要になった場合に、本関数のロジックをそのまま`RetryRuntimeSummaryFormatter`
  等のクラスへ抽出できる構造を維持する
* `main()`内に文字列組み立てロジック（f-string等）を直接書かないことで、
  将来の抽出時に`main()`側の変更を最小限に留められるようにする

却下案：

| 案 | 却下理由 |
|---|---|
| 表示ロジックを`main()`内に直接書く（関数分離しない） | 将来Formatterへ抽出する際に`main()`自体の書き換えが必要になり、抽出コストが上がる。関数分離のコストはほぼゼロなため、今回から局所化しておく |
| 今回から`RetryRuntimeSummaryFormatter`クラスを実装する | 消費者（呼び出し元）が本script1つの段階でクラス化するのは先回りの抽象化（Development Charter 8章「抽象化は必要になってから行う」）。関数で十分に局所化の目的を達成できる |

---

## 3. Architecture Review（Final）

**結論：Approve**

| 観点 | 判定 | コメント |
|---|---|---|
| Foundation First → Execution First | ✅ | v5.1.0〜v5.3.0の土台に、初めて実際に呼び出す入口が付く。ユーザーから見て初めて価値が生まれるRelease |
| Small Release | ✅ | 新規ファイルは`scripts/run_retry_runtime.py`1本のみ。CLI引数・dry_run・loop・独自exit code・Formatterクラスはすべて対象外として明確にスコープ外にした |
| Single Responsibility | ✅ | scriptは組み立て・実行依頼・表示の3つのみ。Business Logicは持たない |
| Backward Compatibility | ✅ | 既存12パッケージ（`retry_composition` / `retry_runtime_orchestrator`含む）はいずれも無改修 |
| Composition優先 / Constructor Injection | ✅ | scriptは`from_env()` / `from_composition_root()`の呼び出しのみで完結する |
| 安全性（Development Charter最優先事項） | ✅ | `--dry-run`の見せかけの安全機能を追加しないことで、誤動作リスクを回避 |
| 検証可能性 | ✅ | `format_summary()`により1サイクルの全結果が標準出力で確認できる |

### リスク

* **実運用リスク**：本scriptを実行すると、Gateが有効な環境では実際に
  Workflowの再実行・Queue除去・History記録が発生する（dry_run非対応のため）。
  初回実行前に`.env`のGate設定（`RETRY_ENGINE_ENABLED`等）を必ず確認する必要が
  ある旨をscript docstringに明記する
* **同時実行リスク**：`run_workflow_engine.py`同様、他のAgent系scriptと
  同時実行した場合の二重実行リスクはKnown Issueとして踏襲（ロック機構は
  引き続き対象外）
* **Architecture Guard恒久差分**：本scriptが`retry_runtime_orchestrator`を
  importする初めての実消費者になるため、v5.2.0の既存テスト
  （`tests/test_e2e_v5_2_0_retry_runtime_orchestrator_foundation.py`テスト25
  「`retry_runtime_orchestrator`を参照する既存ファイルが存在しない」）が
  恒久的にFAILする。`[KI-4]`・`[KI-19]`と同型の既知差分であり、
  CHANGELOG.mdへ`[KI-21]`として記録する

### 将来影響

* 次の自然な拡張は「loop対応」または「安全なdry_run再設計」のどちらか。
  本Releaseの実運用結果を踏まえて優先順位を決めるべきで、今の時点でどちらを
  次にするか決め打ちしない
* Exit Code設計を見送ったことで、Windows タスクスケジューラでの成否監視は
  現状「標準出力の目視確認」に留まる。これは意図的な先送り（Known Issueとして
  記録）
* `format_summary()`を関数として局所化したことで、将来JSON出力や別形式の
  表示が必要になった場合の移行コストを低く抑えられる

### Recommendation

**Approve。** Minor Recommendation 2件（Exit Code Policy明文化・Summary Formatter
Design Note追加）を本設計書へ反映済み。Implementationへ進む。

---

## 4. Compatibility

* `RetryCompositionRoot` / `RetryRuntimeOrchestrator`のシグネチャ・実装は無変更
* 既存12パッケージ（`workflow_monitor` / `retry_queue` / `retry_history` /
  `retry_enqueue_trigger` / `retry_engine` / `workflow_engine` / `ai` /
  `execution_history` / `scheduler` / `retry_scheduler_source` /
  `retry_scheduler_decision` / `retry_composition`）はいずれも無改修
* `src/retry_runtime_orchestrator/`も無改修
* `tests/test_e2e_v5_2_0_retry_runtime_orchestrator_foundation.py`のテスト25は
  本Releaseにより恒久的にFAILする（`[KI-21]`として記録、上記3章参照）

---

## 5. Known Issue（本Releaseでも未解消）

* **`dry_run`は未対応**（`run_once()`自体の制約を継承）。安全なdry_runの設計は
  将来の独立Releaseへ送る
* **Exit Codeによる成否監視は不可**。現状は標準出力の目視確認のみ
* **同時実行の排他制御なし**：他のAgent系script（`run_workflow_engine.py`等）と
  同時実行した場合の二重実行リスクは対象外のまま
* **Windows タスクスケジューラへの登録作業自体は対象外**（script本体の提供のみ）
* `RetryQueueManager` / `RetryHistoryManager`の永続化は引き続き対象外

---

## 6. Future Architecture Consideration

* **`--loop` / `--daemon`対応**：本Releaseの実運用結果を踏まえて必要性を再判断する
* **安全なdry_run再設計**：Decider/Executor層が`dry_run`を認識できるように
  なった段階で、CLI側にも`--dry-run`を追加する独立Releaseとして再設計する
* **Exit Code設計の再検討**：Windows タスクスケジューラでの成否監視が
  実運用上必要になった時点で、`RetryRuntimeCycleResult`のどのフィールドを
  もって「成功」とみなすかを含めて独立Releaseとして検討する
* **Summary Formatterクラスへの抽出**：JSON出力・Slack通知等、表示形式の
  複数化が必要になった時点で、`format_summary()`のロジックをクラスへ抽出する

---

## 7. Status

- [x] Architecture Review 完了（Final、ユーザー承認済み。Minor Recommendation 2件反映済み）
- [x] Implementation
- [x] Unit / E2E Test
- [x] Regression確認
- [x] Documentation更新
