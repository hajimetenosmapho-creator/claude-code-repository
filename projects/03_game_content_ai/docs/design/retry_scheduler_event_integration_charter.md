# Project Charter — Release 3.7「Retry Scheduler Event Integration」

作成日：2026-07-03
状態：ドラフト（ユーザー確認待ち）
対象：`RetrySchedulerDecision`（v3.5.0）の選択結果（`select_candidates()` /
`select_next_candidate()`）を、`SchedulerEngine.evaluate()` / `run_due()`
（v2.6.0）の判定ロジックに反映し、Retry候補を表す`SchedulerEvent`を
生成できるようにする統合。Retry Engineの起動・`dequeue()` / `remove()`の
呼び出し・Retry Queueへの書き込み（永続化を含む）はいずれも対象外とする。

> **本Releaseの位置づけについての注記**：v3.4.0（Retry Scheduler Wiring）・
> v3.6.0（Retry Scheduler Decision Wiring）はいずれも「`evaluate()` /
> `run_due()`の判定ロジックには一切組み込まない」ことを明示的な前提とし、
> `SchedulerEngine`に読み取り専用の委譲メソッドを追加するだけの統合だった。
> 本Release（v3.7.0）は、ユーザー指示の目的候補「Retry候補を`SchedulerEvent`に
> 反映する」の通り、**`evaluate()` / `run_due()`の判定ロジックそのものに
> 初めて手を加えるRelease**であり、これまでの3リリースとは性質が異なる。
> この変更は`docs/ROADMAP.md`「v3.x 以降の候補」に「選択結果を`evaluate()` /
> `run_due()`の判定ロジックへ組み込む統合」として記載済みの項目に対応する。

---

## 1. Background

* Retry Scheduler Integration（v3.3.0）：`RetrySchedulerSource` /
  `NullRetrySchedulerSource`が`RetryQueueManager`の読み取り専用API
  （`list()` / `count()`）を中継するAdapterを新設した（消費者不在の先行実装）。
* Retry Scheduler Wiring（v3.4.0）：`SchedulerEngine`が`RetrySchedulerSource`を
  Constructor Injectionで保持し、`count_pending_retries()` /
  `list_pending_retries()`への薄い委譲メソッドを追加した。`evaluate()` /
  `run_due()`は無改修のまま。
* Retry Scheduler Decision（v3.5.0）：待機中の項目一覧から「次に処理すべき候補」を
  選ぶ専用コンポーネント`RetrySchedulerDecision`
  （`select_candidates(limit)` / `select_next_candidate()`）を新設した。
  `SchedulerEngine`には一切接続しない独立コンポーネントとして完結させた。
* Retry Scheduler Decision Wiring（v3.6.0）：`SchedulerEngine`が
  `RetrySchedulerDecision`をConstructor Injectionで保持し、
  `select_candidates()` / `select_next_candidate()`への薄い委譲メソッドを
  追加した。`evaluate()` / `run_due()`は本Releaseでも無改修のまま
  （`docs/design/retry_scheduler_decision_wiring_charter.md` 4章で
  明示的に対象外と定義）。
* `docs/ROADMAP.md`「v3.x 以降の候補」に、次の未着手項目として次の記載がある：
  「選択結果を`evaluate()` / `run_due()`の判定ロジックへ組み込む統合：
  `RetrySchedulerDecision`の選択結果を使って`SchedulerEvent`を生成する等の統合
  （v3.6.0では`evaluate()` / `run_due()`を無改修に保つ方針のため意図的に対象外）」。
  本Release（v3.7.0）はこの項目に相当する。
* 同じくROADMAP.mdには、この項目の次の段階として「自動Retry実行：
  `RetrySchedulerDecision`で選ばれた候補を、`RetryQueueManager.dequeue()`で
  取り出し`RetryManager.retry()`へ渡す一連の自動化」が別項目として記載されている。
  本Releaseはこの自動実行段階には進まず、あくまで「選ばれた候補を
  `SchedulerEvent`として表現できるようにする」ところまでに留める。

```
Scheduler（判断、v2.6.0 / v3.4.0 / v3.6.0）
   │
   ├── evaluate() / run_due()（時刻ベースの判定） ★本Releaseで変更
   │        │
   │        └── SchedulerEvent 生成（Job由来 ＋ Retry候補由来 ★新規）
   │
   └── select_candidates() / select_next_candidate()（v3.6.0、無改修）
            │  RetrySchedulerDecision（v3.5.0、無改修）を委譲呼び出し
            ▼
      RetrySchedulerSource → Retry Queue（いずれも無改修）
```

---

## 2. Purpose

`SchedulerEngine.evaluate()` / `run_due()`が、時刻ベースの`SchedulerJob`判定に加えて、
`RetrySchedulerDecision`（v3.5.0、v3.6.0でDI済み）が選んだRetry候補を
`SchedulerEvent`として表現できるようにする。これにより、Scheduler経由で
「今すぐ処理すべきもの」の一覧に、定時Jobだけでなく待機中のRetry候補も
含まれるようになる。

ただし、生成されるのはあくまで`SchedulerEvent`（判断結果を表すデータ）のみであり、
そのイベントを受け取って実際に何かを実行する仕組み（Retry Engine起動・
Workflow Engine起動等）は本Releaseの対象外とする。

---

## 3. Goals

本Releaseで確立する Retry Scheduler Event Integration は、次のことだけを行う。

1. `SchedulerEngine.evaluate()` / `run_due()`が、`RetrySchedulerDecision`の
   選択結果（Retry候補）を`SchedulerEvent`として出力に含められるようにする
   （具体的な組み込み方式・呼び出し条件は8章 Open Questionsで確定する）
2. `retry_decision`が`None`の場合（v3.6.0までのデフォルト動作）、
   `evaluate()` / `run_due()`の出力はv3.6.0時点と完全に同一であること
   （後方互換性維持。既存の`SchedulerEngine()` / `SchedulerEngine(clock=...)` /
   `SchedulerEngine(retry_source=...)`呼び出しへの影響ゼロ）
3. Retry候補由来の`SchedulerEvent`は「選ばれた」という事実のみを表現し、
   Retry Queueの状態を変更しない（`dequeue()` / `remove()`への到達経路を
   構造的に持たない）
4. `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` /
   `retry_engine`はいずれも本Releaseでも無改修（ゼロ改修）を維持する
5. `SchedulerJob`の時刻ベース判定ロジック（`_match*()`系メソッド）自体は
   変更しない（Job判定とRetry候補判定は独立したロジックのまま共存する）

---

## 4. Scope

### 対象

* `SchedulerEngine.evaluate()` / `run_due()`への、Retry候補を`SchedulerEvent`
  として含める変更
* Retry候補由来の`SchedulerEvent`を識別するための`trigger_reason`定数の追加
  （例：`REASON_RETRY_CANDIDATE_SELECTED`。具体名は次工程で確定）
* 単体テスト・E2Eテスト（`tests/test_e2e_v3_7_0_retry_scheduler_event_integration.py`）
* 関連ドキュメント更新（CHANGELOG / ROADMAP / architecture.md）

### 対象外（今回やらないこと）

* Retry Engine の起動（`RetryManager.retry()`の呼び出し）
* `RetryQueueManager.dequeue()`の呼び出し
* `RetryQueueManager.remove()`の呼び出し
* Retry Queue の更新（`enqueue` / `dequeue` / `remove`を含むあらゆる書き込み）
* 自動Retry実行（生成された`SchedulerEvent`を実際に消費して再試行する仕組み）
* Retry Queue・Scheduler判定結果の永続化
* `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` /
  `retry_engine`パッケージ自体の改修（いずれもゼロ改修を維持）
* `SchedulerJob`の時刻ベース判定ロジック（`_match_daily` / `_match_interval` /
  `_match_once`）の変更
* 新しいFeature Gate環境変数の追加・Configクラスの追加・Managerパターン
  （`from_config()` / `from_env()`等の起動口）の採用（v3.3.0〜v3.6.0からの
  継続方針。10章 Non-Goals参照）

---

## 5. Design Principles

* **Foundation First**：Retry候補を`SchedulerEvent`として「表現できる」ように
  するところまでを行う。生成された`SchedulerEvent`を使った実行
  （Retry Engine起動・自動再試行）は後続Releaseへ送る
* **Single Responsibility**：`SchedulerEngine`は「時刻ベースの判定」と
  「Retry候補の選択結果を`SchedulerEvent`として表現すること」を担うのみ。
  候補選択ロジック自体（`RetrySchedulerDecision`）・Queue管理
  （`retry_queue`）・実行判断（`retry_engine`）のいずれも複製・肩代わりしない
* **Stateless**：`SchedulerEngine`はRetry候補由来の`SchedulerEvent`を
  独自にキャッシュ・保持しない。`evaluate()` / `run_due()`を呼び出すたびに
  `RetrySchedulerDecision`経由で最新状態を取得する
* **Constructor Injection のみ**：セッターインジェクション・実行時の差し替え
  メソッド・ファクトリメソッド（`from_config()`等）は追加しない
  （v3.6.0で確定済みの`retry_decision`引数をそのまま利用する）
* **Read Only（Retry Queueに対して）**：`SchedulerEngine`が呼び出すのは
  `RetrySchedulerDecision`の読み取り専用メソッド（`select_candidates()` /
  `select_next_candidate()`）のみ。Queueの状態を変更する操作には一切到達しない
* **Backward Compatibility**：`retry_decision`が`None`の場合、`evaluate()` /
  `run_due()`の出力はv3.6.0時点とまったく同じ`SchedulerEvent`列になる。
  既存の全Constructor呼び出しパターンは本Release後も無変更で動作する

---

## 6. Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryQueueManager`（v3.1.0、無改修） | Queueへの出し入れ・整列 | 候補選択・実行判断・イベント生成 |
| `RetrySchedulerSource` / `NullRetrySchedulerSource`（v3.3.0、無改修） | Retry Queueの状態の読み取り専用な中継 | 候補選択ロジック・実行判断・イベント生成 |
| `RetrySchedulerDecision`（v3.5.0、無改修） | 待機中の項目一覧から「次に処理すべき候補」を選ぶ | イベント生成・実行判断・`SchedulerEngine`との接続の起点になること |
| `SchedulerEngine`（本Releaseで変更） | 時刻ベースの判定＋Retry候補選択結果の`SchedulerEvent`への反映 | 候補選択ロジックの再実装／Retry実行／Queueの変更 |
| Retry Engine・Workflow Engine等（本Releaseでは無関係） | （本Releaseの`SchedulerEvent`を将来消費する側） | 本Releaseの対象外 |

---

## 7. Dependencies

```
scheduler                ──→ retry_scheduler_decision（v3.6.0のまま、無改修）
scheduler                ──→ retry_scheduler_source（v3.4.0のまま、無改修）
retry_scheduler_decision ──→ retry_scheduler_source（v3.5.0のまま、無改修）
retry_scheduler_source   ──→ retry_queue（v3.3.0のまま、無改修）
retry_engine              ──→ （本Releaseでは一切関与しない）
```

* 本Releaseで新規に追加される依存方向はない（`scheduler → retry_scheduler_decision`
  はv3.6.0で確立済み。本Releaseはその依存を`evaluate()` / `run_due()`内部の
  ロジックで「利用する」変更であり、依存グラフ自体は変わらない）
* `retry_scheduler_decision`は`scheduler`を一切importしない（逆方向依存なし。
  v3.5.0のまま維持）
* 循環importは発生しない

---

## 8. Open Questions（Architecture Designで確定する事項）

Project Charterの時点では確定せず、次工程のArchitecture Designで検討する。
本Releaseは`evaluate()` / `run_due()`の判定ロジックそのものに初めて手を加えるため、
過去4リリースよりも論点が多い。

1. **組み込み方式**：`evaluate()`の既存シグネチャ（`jobs, now`）はそのままに、
   Job由来の`SchedulerEvent`リストへRetry候補由来の`SchedulerEvent`を
   追加で連結する（Additive）方式にするか、Retry候補の反映を独立した新規メソッド
   （例：`evaluate_with_retries()`）に切り出し、既存`evaluate()`は無改修のまま
   維持するか。後者であれば「`evaluate()` / `run_due()`は無改修」という
   v3.4.0〜v3.6.0の不変条件をそのまま延長できる可能性がある一方、
   ユーザー指示の目的候補「`evaluate()` / `run_due()`とRetrySchedulerDecisionの
   統合設計」との整合を要確認
2. **呼び出し条件**：Retry候補由来の`SchedulerEvent`を、`retry_decision`が
   注入されている場合は常に生成するか、明示的な引数（例：
   `evaluate(jobs, now, include_retries=True)`）で呼び出し側が都度選択できる
   ようにするか
3. **`job_id`相当フィールドの決め方**：`SchedulerEvent.job_id`は`SchedulerJob`
   由来の文字列を想定した設計だが、`RetryQueueItem`には`job_id`に相当する
   フィールドが存在しない（`run_id` / `workflow_name`等）。Retry候補由来の
   `SchedulerEvent.job_id`に何を格納するか（例：`run_id`をそのまま使う、
   `"retry:{run_id}"`のようなプレフィックス付き文字列にする等）
4. **`metadata`の組み立て方**：`scheduler`パッケージは`retry_queue`に
   直接依存しない方針（v3.4.0〜v3.6.0で確立済み）のため、`RetryQueueItem`を
   型としてimportできない。`RetrySchedulerDecision`が返すオブジェクトの
   属性（`run_id` / `workflow_name` / `priority` / `retry_attempt` / `status`）を
   `metadata`辞書にどこまで・どう反映するか（Duck Typing前提でのアクセス方法を含む）
5. **件数の扱い**：`select_candidates()`（複数件）と`select_next_candidate()`
   （1件）のどちらを`evaluate()` / `run_due()`から使うか。複数件反映する場合、
   件数上限（`limit`）をどう決めるか（固定値・引数化・Job数と無関係に独立管理等）
6. **`trigger_reason`の命名**：Job由来の`REASON_DAILY_MATCHED`等と一貫性を
   持たせた命名にする（例：`REASON_RETRY_CANDIDATE_SELECTED`）
7. **`evaluate()` / `run_due()`が無改修だった過去のAcceptance Criteriaとの関係**：
   v3.4.0・v3.6.0のAcceptance Criteriaには「`evaluate()` / `run_due()`が
   本Release前とまったく同じ`SchedulerEvent`列を返すこと」という文言があった。
   本Releaseではこれを「`retry_decision`が`None`の場合に限り」という条件付きに
   読み替える必要があり、その条件をコード・テストの両面でどう構造的に保証するか
   （Architecture Guardパターンの踏襲を含む）

---

## 9. Acceptance Criteria

* `retry_decision`が`None`の場合、`evaluate()` / `run_due()`が
  v3.6.0時点とまったく同じ`SchedulerEvent`列を返すこと（既存回帰テストで確認）
* `retry_decision`が注入されている場合、`RetrySchedulerDecision`が選んだ候補が
  `SchedulerEvent`として出力に反映されること
* `SchedulerEngine`が`RetrySchedulerDecision`の`select_candidates()` /
  `select_next_candidate()`以外のメソッドを一切呼び出さないこと（構造的確認。
  Spyオブジェクトによりv3.3.0〜v3.6.0と同じ手法で検証）
* `SchedulerEngine`が`RetryQueueManager.dequeue()` / `remove()`・
  `RetryManager.retry()`へ到達する呼び出し経路が構造的に存在しないこと
* `SchedulerJob`の時刻ベース判定（`_match_daily` / `_match_interval` /
  `_match_once`）が本Release前後で完全に同一の結果を返すこと
* `src/retry_scheduler_decision/` / `src/retry_scheduler_source/` /
  `src/retry_queue/` / `src/retry_engine/`配下の全ファイルに差分がないこと
  （`git diff`で確認、ゼロ改修）
* 既存の`SchedulerEngine()` / `SchedulerEngine(clock=...)` /
  `SchedulerEngine(retry_source=...)` / `SchedulerEngine(retry_decision=...)`
  呼び出しが本Release後も無変更で動作すること（後方互換性の回帰確認）
* `scheduler`配下に新しいFeature Gate環境変数・`Config`を名前に含むクラス・
  `enabled`フィールドを持つクラスが追加されていないこと
* E2Eテスト全PASS・既存回帰（`v2.0.0`〜`v3.6.0`）全PASS（`evaluate()` /
  `run_due()`変更に伴う既存Architecture Guardの扱いはOpen Question 7で
  確定した方針に従い、Test工程でCHANGELOG.mdへ記録する）

---

## 10. Non-Goals

* Retry Engine（`RetryManager`）の起動・呼び出し
* `RetryQueueManager.dequeue()` / `remove()`の呼び出し
* 生成された`SchedulerEvent`を実際に消費して再試行すること（自動Retry実行）
* Retry Queue・Scheduler判定結果の永続化
* `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` /
  `retry_engine`パッケージ自体の変更（いずれもゼロ改修を維持）
* `SchedulerJob`の時刻ベース判定ロジックの変更
* 新しいFeature Gate環境変数の追加
* Configクラスの追加
* Managerパターン（`from_config()` / `from_env()`等の起動口）の採用

---

## 11. Directory Structure（想定）

```text
src/scheduler/
├── scheduler_engine.py     # 変更：evaluate() / run_due()がRetry候補を
│                            #        SchedulerEventへ反映できるようにする
├── scheduler_event.py       # 変更なし想定（8章 Open Question次第で見直す可能性あり）
└── __init__.py              # 変更（docstringのみ想定）

src/retry_scheduler_decision/  # 全ファイル無改修
src/retry_scheduler_source/    # 全ファイル無改修
src/retry_queue/               # 全ファイル無改修
src/retry_engine/              # 全ファイル無改修

tests/
└── test_e2e_v3_7_0_retry_scheduler_event_integration.py   # 新規
```

---

## 12. Risks and Mitigations

| リスク | 対策 |
|---|---|
| `evaluate()` / `run_due()`を変更する初めてのReleaseであり、「無改修」を前提にしていた過去のAcceptance Criteria・Architecture Guardとの不整合が生じる | Open Question 7で「`retry_decision=None`時のみ既存動作と同一」という条件を明文化し、Architecture Designで構造的な保証方法（回帰テスト・Guardパターン）を確定する |
| `SchedulerEvent.job_id`が本来`SchedulerJob`由来を想定した設計であり、Retry候補（`run_id`ベース）を無理に当てはめると、将来Retry Engineが`SchedulerEvent`を消費する際の解釈が曖昧になる | Open Question 3・4として明示し、Architecture Designで`job_id` / `metadata`の具体的な組み立て方を確定してから実装に進む |
| Retry候補反映の組み込み方式（Open Question 1）次第で、`evaluate()`のシグネチャ変更が既存呼び出し元（テスト等）に影響する可能性がある | Additive方式（既存シグネチャ維持＋出力へ追加）を優先候補とし、シグネチャ変更が必要な場合はデフォルト引数で後方互換性を維持する方針をArchitecture Designで確認する |
| 「`SchedulerEvent`として表現できるだけ」で終える本Releaseの価値が、自動Retry実行を行う次Releaseまで実運用に結びつかない | v3.3.0〜v3.6.0でも同様の「消費者不在／未接続」を経て段階的に統合してきた前例がある。本Releaseも同じFoundation Firstパターンとして扱う |

---

## 13. Status

- [x] Project Charter ドラフト作成（本文書、Claude Code作成）
- [ ] ユーザー確認・フィードバック反映
- [ ] Project Charter 確定
- [ ] Architecture Design（次工程。本Releaseでは着手しない）
