# v5.5.0 Retry Runtime Loop Foundation 設計書（Project Charter / Architecture Design）

作成日：2026-07-09
状態：確定（Architecture Review Final・ユーザー承認済み）

---

## 1. Project Charter

### 1.1 目的

`RetryRuntimeOrchestrator.run_once()`（v5.3.0）を繰り返し呼び出すだけの薄いLoop
Wrapper（`RetryRuntimeLoop`）を新設する。本Releaseは「Loopという実行順序の器」を
用意するところまでに限定し、実際に`scripts/run_retry_runtime.py`へ配線して
運用に乗せるところまでは行わない（Foundation First）。

### 1.2 背景

`docs/ROADMAP.md`（v5.4.0直後の候補一覧）は次Release候補として、
「安全なdry_runの再設計」「Retry専用Scheduler API」「`--loop`/`--daemon`対応」
「Exit Code設計の再検討」「Summary Formatterクラスへの抽出」の5項目を並列に挙げていた。

Architecture Reviewの過程で、ユーザーから「Retry Runtime Loop Foundation」が
第一候補として提示された。初回レビューでは「Loopを配線・運用まで見据えたもの」
として評価し、dry_run未対応の状態でLoopを導入すると安全上のリスクが増幅される
ことを理由に、代替テーマ（Safe Dry Run Foundation）を提案した。

再レビュー依頼を受け、Loop自体がBusiness Logicを一切持たない
`while should_continue_fn(): run_once_fn(); sleep_fn(interval)`という
純粋なWrapperであること、かつ**`scripts/`への配線を伴わない Foundation限定**で
あれば、本プロジェクトが v3.1.0・v3.3.0・v3.5.0・v5.1.0・v5.2.0で繰り返してきた
「消費者不在の先行実装」パターンと完全に同型であり、実運用リスクを増やさずに
Runtime Architectureを1歩前進させられることが判明した。本Releaseはこの
再評価結果（Option A'）を実装するものである。

### 1.3 Non-Goal（本Releaseで実施しないこと）

* `scripts/run_retry_runtime.py`への配線（CLI引数化・`--loop`・`argparse`含む）
* `RetryRuntimeOrchestrator`へのLoop責務の追加（`RetryRuntimeLoop`は独立パッケージとする）
* `RetryCompositionRoot`へのExecution/Loop責務の追加・変更
* `RetryManager`への変更
* `dry_run`対応
* daemon化（常駐プロセス化）・signal handling（Ctrl+C・SIGTERM等）
* 独自のExit Code体系の導入・既存Exit Code Policyの変更
* `RetryRuntimeCycleResult`の解釈・集計・ログ出力
* `interval_seconds`の環境変数化・デフォルト値の導入
* 既存13パッケージ（`workflow_monitor` 〜 `retry_runtime_orchestrator`）への変更

---

## 2. Architecture Design（採用案）

### 2.1 パッケージ配置

**採用**：新規独立パッケージ`src/retry_runtime_loop/`を追加する。

却下案：

| 案 | 却下理由 |
|---|---|
| `RetryRuntimeOrchestrator`に`loop()`メソッドを追加する | `RetryRuntimeOrchestrator`の責務を「1サイクル分の実行順序を決めること」に限定してきたv5.2.0〜v5.4.0の方針に反する。ユーザー指示「RetryRuntimeOrchestratorにLoop責務を追加しない」に合致 |
| `scripts/run_retry_runtime.py`に直接while/sleepを書く | scripts層はEntry Pointに限定する既存方針（v5.4.0設計書2.1節）に反する。加えて本Releaseはscriptsへの配線自体をNon-Goalとしている |

### 2.2 `RetryRuntimeLoop`の設計

**採用**：`run_once_fn` / `sleep_fn` / `should_continue_fn` / `interval_seconds`を
Constructor Injectionで受け取り、`run()`メソッドで
`while should_continue_fn(): run_once_fn(); sleep_fn(interval_seconds)`を
実行するだけのStatelessなWrapperとする。

```python
class RetryRuntimeLoop:
    def __init__(self, run_once_fn, sleep_fn, should_continue_fn, interval_seconds):
        ...

    def run(self) -> None:
        while self.should_continue_fn():
            self.run_once_fn()
            self.sleep_fn(self.interval_seconds)
```

* `run_once_fn`の戻り値（実運用では`RetryRuntimeCycleResult`が渡される想定だが、
  本クラスはその型を一切知らない）は破棄する。`run()`の戻り値は`None`
* 例外はtry/exceptで握りつぶさず、そのまま`run()`から呼び出し元へ伝播させる
  （fail-fast）。`run_once_fn`が例外を送出した場合、直後の`sleep_fn`は呼ばれない
* `interval_seconds`のバリデーション（負数・0のチェック等）は行わない。
  Development Charter「検証は境界（外部入力）でのみ行う」に基づき、本クラスは
  DIのみで完結し境界に該当しないため、呼び出し元を信頼する
* `from_env()`等のFactory Methodは追加しない。配線先（消費者）が本Release時点で
  存在しないため、環境変数から値を組み立てる経路自体が時期尚早（YAGNI）

却下案：

| 案 | 却下理由 |
|---|---|
| `run()`が実行回数・最終`run_once_fn`の戻り値等の統計情報を返す | Loopが`RetryRuntimeCycleResult`を含む実行結果を解釈・集計する責務を持つことになり、「中身を解釈しない」というユーザー指示に反する。テストで必要な呼び出し回数の検証はFake関数側での記録で十分に代替できる |
| `run_once_fn`の例外をログに記録してから再送出する | ログ出力は新たな責務（Business Logicではないが既存資産`src/logger/`との関係整理が必要）であり、本Foundation Releaseのスコープを超える |
| `interval_seconds`にデフォルト値（例：60）を設定する | 消費者が存在しない段階でのデフォルト値設定は意味を持たない先回り。呼び出し元（次Release以降）が明示的に決定すべき値である |

### 2.3 配線しない（消費者を作らない）方針

**採用**：`scripts/run_retry_runtime.py`・`RetryRuntimeOrchestrator`・
`RetryCompositionRoot`のいずれからも`RetryRuntimeLoop`を参照しない。
`src/retry_runtime_loop/`は本Release完了時点で「どこからもimportされない」
状態のまま完結させる。

理由：

* v5.2.0（`RetryRuntimeOrchestrator`）・v5.1.0（`RetryCompositionRoot`）と同じ
  「土台を用意し、次Releaseで接続を判断する」Foundation Firstパターンを踏襲する
* `run_once()`自体がdry_run未対応というKnown Issueを抱えたまま（v5.3.0・v5.4.0から
  継続）であるため、配線して実際にLoopを起動できる状態にすると、この未解決の
  安全上のギャップを「無人で繰り返す」形に増幅させてしまう。未配線であれば
  この増幅は発生しない
* 配線判断（`--loop`のCLI化）は、dry_run安全性の状況を踏まえて次Release以降に
  改めて評価する（6章）

却下案：

| 案 | 却下理由 |
|---|---|
| `scripts/run_retry_runtime.py`に`--loop`オプションとして追加し、明示的なopt-inとして提供する | 本Releaseのユーザー承認スコープが「未配線のFoundationに限定」と明確に定められているため不採用。仮に配線する場合もdry_run安全性の解決が先であるべきという前回Architecture Reviewの結論を維持する |

---

## 3. Architecture Review（Final）

**結論：Approve**

| 観点 | 判定 | コメント |
|---|---|---|
| Foundation First | ✅ | 消費者不在のまま土台のみを追加する、本プロジェクト5回目の同型パターン |
| Small Release | ✅ | 新規ファイルは`src/retry_runtime_loop/`配下2本のみ |
| Single Responsibility | ✅ | Loopは「繰り返す」ことのみを責務とし、実行内容・結果の解釈は一切持たない |
| Backward Compatibility | ✅ | 既存13パッケージ・`scripts/run_retry_runtime.py`はいずれも無改修 |
| 安全性（Development Charter最優先事項） | ✅ | 未配線のため本番のQueue/History/Managerに一切到達しない。dry_run未対応の影響範囲を増幅させない |
| 既存アーキテクチャとの整合性 | ✅ | 「Foundation→Execution→Entry Point」という確立済みパターンをLoopにも適用 |
| 検証可能性 | ✅ | Fake（`run_once_fn` / `sleep_fn` / `should_continue_fn`）による振る舞い検証で、実際のsleepを伴わずテスト可能 |

### Option A（Loop Foundation・未配線）と Option B（Safe Dry Run）の比較

Development Charterの判断軸（Safety / Maintainability / Simplicity / Existing
Architecture Consistency / Extensibility）で比較した結果、未配線に限定した
Option A（Option A'）はSafety面で実質的なリスクを負わずに Extensibility・
Existing Architecture Consistencyの利点を得られると判断した（詳細な比較表は
本Release検討時の会話記録を参照。要旨は以下）。

* **Safety**：未配線のため実害ゼロ。Option Bのように既存7個のExecutor/Deciderへ
  横断的に変更を加える必要もなく、既存コードへの影響範囲はむしろ本Releaseの方が小さい
* **Maintainability / Simplicity**：新規独立ファイルのみで完結し、既存コードへの
  影響評価が不要
* **Existing Architecture Consistency**：未配線である限り、Windows タスク
  スケジューラへの委任という既存運用方針とも衝突しない
* **Extensibility**：Daemon化・定期実行という将来像への土台が前進する

### リスク

* **将来の配線判断を誤ると、前回レビューで指摘した安全上のリスクがそのまま
  顕在化する**。次Release以降で`--loop`等の配線を検討する際は、dry_run安全性の
  状況を必ず踏まえて判断すること（6章）
* 本Release単体では、ユーザーから見て動く機能は増えない（v5.1.0・v5.2.0と同型の
  Known Issue）

### 将来影響

* 次の配線判断（`--loop`のCLI化）は、Safe Dry Run Foundationの実施状況を
  前提条件として改めて評価する
* `RetryRuntimeLoop`は`run_once_fn`を受け取るだけの汎用的なWrapperであるため、
  将来`run_once()`以外の周期実行（他のAgent系script等）にも転用できる可能性が
  あるが、本Releaseではその汎用化を目的にしない（YAGNI。あくまで結果として
  持つ性質）

### Recommendation

**Approve。** Option A'（未配線Foundation限定）としてImplementationへ進む。

---

## 4. Compatibility

* 既存13パッケージ（`workflow_monitor` / `retry_queue` / `retry_history` /
  `retry_enqueue_trigger` / `retry_engine` / `workflow_engine` / `ai` /
  `execution_history` / `scheduler` / `retry_scheduler_source` /
  `retry_scheduler_decision` / `retry_composition` / `retry_runtime_orchestrator`）・
  `scripts/run_retry_runtime.py`はいずれも無改修
* `src/retry_runtime_loop/`を参照する既存コードは存在しない（消費者不在の
  先行実装）。本Releaseでは、これに起因する既存テストへの新規Architecture
  Guard差分（`[KI-19]`〜`[KI-21]`のような恒久FAIL）は**発生しない見込み**である
  （既存ファイルへの変更が一切ないため）

---

## 5. Known Issue（本Releaseでも未解消）

* `RetryRuntimeLoop`を実際に呼び出す消費者（`scripts/`配線）は存在しない
* Loop配線時に必要となる`dry_run`安全性は引き続き未解決（v5.3.0 Known Issueを継続）
* interval設定方法（環境変数/CLI）・停止方法（signal handling）は未設計

---

## 6. Future Architecture Consideration

* **Loop配線（`scripts/run_retry_runtime.py`への`--loop`追加）**：本Releaseの
  次候補。ただし、dry_run安全性（Safe Dry Run Foundation）の状況を踏まえて
  着手要否を改めて判断する
* **Safe Dry Run Foundation**：Decider/Executor層が`dry_run`を認識できるように
  なった段階で独立Releaseとして設計する。Loop配線の前提条件として引き続き重要
* **interval設定方法・停止方法（signal handling）**：Loop配線時に合わせて設計する
* **Retry専用Scheduler API・Exit Code再検討・Summary Formatterクラス化**：
  引き続きROADMAP候補として保持（v5.4.0設計書6章から継続）

---

## 7. Status

- [x] Architecture Review 完了（Final、ユーザー承認済み。Option A' vs Option B比較を反映済み）
- [x] Implementation
- [x] Unit / E2E Test
- [x] Regression確認
- [x] Documentation更新
