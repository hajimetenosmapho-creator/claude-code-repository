# Project Charter — Release 4.5「Retry Policy Foundation」

作成日：2026-07-08
状態：ドラフト（ユーザー確認待ち）
対象：`RetryPolicy`（v3.0.0から無改修）が持つ`should_retry(monitor_status, attempt) -> bool`
という最小インターフェースを明確化し、Protocol（構造的部分型）として切り出す。
既存`RetryPolicy`はそのインターフェースを満たす実装の1つと位置づけ、将来
`FixedRetryPolicy` / `ExponentialBackoffPolicy` / `AdaptiveRetryPolicy`等へ
差し替え可能な構造にする。新しいRetry戦略の実装自体は本Releaseの対象外。

> **本Releaseの位置づけについての注記**：`retry_policy.py`のdocstring（v3.0.0）に
> 「`RetryManager`は本クラスを`should_retry(monitor_status, attempt) -> bool`という
> 1メソッドを持つオブジェクトとしてのみ利用する。将来Strategy Pattern
> （`FixedRetryPolicy` / `ExponentialBackoffPolicy` / `AdaptiveRetryPolicy`等）へ
> 拡張できる構造を保つが、本Foundationでは固定Retry Policyのみを実装する」と
> 明記されたまま、v3.1.0〜v4.4.0（Retry Queue / Cleanup系列）を通じて一度も
> 着手されていなかった拡張ポイントに、本Releaseで着手する。

---

## 1. Background

* `RetryPolicy`（`retry_policy.py`、v3.0.0）は`target_statuses`（固定値：
  `FAILED` / `TIMEOUT`） と `max_attempts`（環境変数`RETRY_MAX_ATTEMPTS`で
  調整可能）を保持する`frozen dataclass`であり、`should_retry(monitor_status,
  attempt) -> bool`という1メソッドを公開している。
* `RetryManager`（`retry_manager.py`）は`__init__`の第1引数として
  `policy: RetryPolicy`を**必須引数**として受け取る（他の全コンポーネント
  ——`event_consumer` / `execution_selector` / `queue_update_decider`等——は
  すべて`X | None = None`＋省略時フォールバックだが、`policy`のみこの
  パターンに含まれていない）。
* **重要な発見**：`RetryManager.retry()`は`self._policy.should_retry(...)`を
  呼ぶだけでなく、判定がFalseだった場合のメッセージ生成
  （`_skip_reason()`、`retry_manager.py`515〜521行目）で
  `self._policy.target_statuses`（membership判定・`sorted()`での列挙）と
  `self._policy.max_attempts`（メッセージ文字列への埋め込み）を**直接参照**
  している。
  つまり、`RetryManager`が実際に依存しているのは`should_retry()`1メソッドの
  みではなく、`target_statuses` / `max_attempts`という2つの属性を含む、
  事実上`RetryPolicy`の内部構造そのものである。将来
  `ExponentialBackoffPolicy`等、`target_statuses` / `max_attempts`という
  形を持たない戦略に差し替えた場合、`_skip_reason()`が構造的に破綻する
  可能性がある。この点は「最小インターフェース」を確定する際の重要な
  制約として8章 Open Questionsで扱う。
* v3.1.0〜v4.4.0（Retry Queue Foundation〜NOT_FOUND / DISABLED Cleanup
  Foundation）はいずれも「Retry Queueの後始末」に関する拡張であり、
  `RetryPolicy`自体・`RetryManager.retry()`の判定ロジック自体には一切
  手を入れていない（`__init__.py`の各バージョン注記、`retry_manager.py`
  の`retry()`本体を確認済み）。

```
RetryManager.retry(run_id, attempt, dry_run)
   │
   ├─ self._monitor.get_status(run_id)          （無改修）
   ├─ self._policy.should_retry(status, attempt) ← 唯一の判定メソッド
   ├─ self._skip_reason(status, attempt)         ← target_statuses / max_attempts に直接依存
   └─ self._executor.execute(request, record)    （無改修）

        ★本Releaseで検討
   「RetryManagerが実際に依存している面（should_retry / target_statuses /
    max_attempts）を洗い出したうえで、Protocol/ABCとして明確化し、
    既存RetryPolicyをその実装の1つと位置づける」
```

---

## 2. Purpose

`RetryPolicy`が現在暗黙的に満たしているインターフェース
（`should_retry(monitor_status, attempt) -> bool`、および`RetryManager`が
直接参照している`target_statuses` / `max_attempts`）を、Protocol（または
ABC）として明示的に定義する。既存の`RetryPolicy`はこのインターフェースを
満たす具体実装（Fixed Retry Policy）の1つと位置づけ、`RetryManager`の
Constructor Injectionはこのインターフェースを満たす任意のオブジェクトを
受け取れる構造にする。

既存`RetryPolicy`の動作・判定結果・環境変数仕様は一切変更しない。新しい
Retry戦略（Exponential Backoff等）の実装は行わない。

---

## 3. Goals

1. `RetryManager`が`RetryPolicy`に対して実際に依存している面
   （`should_retry()` / `target_statuses` / `max_attempts`）を`retry_manager.py`
   の既存コードから洗い出し、インターフェースとして過不足なく定義する
   （1章の発見を踏まえ、`should_retry()`だけでは不十分な可能性がある点を
   Architecture Designで確定する）
2. Protocol（`typing.Protocol`）またはABC（`abc.ABC`）として、上記
   インターフェースを新規ファイルに定義する（既存`retry_policy.py`は
   無改修とする方針を基本としつつ、採用する仕組みによって既存ファイルへの
   影響有無が変わりうるためArchitecture Designで確定する。8章 Open
   Questions参照）
3. 既存`RetryPolicy`が新しいインターフェースを構造的に（Protocolの場合）
   または明示的に（ABCの場合）満たすことを保証する
4. `RetryManager.__init__` / `from_config()`の`policy`引数の型注釈を、
   新しいインターフェース型で受け取れるようにする（型注釈のみの変更であり、
   実行時の挙動には影響しない）
5. 既存の`RetryManager(policy=RetryPolicy(...), ...)` /
   `RetryManager.from_config(retry_policy=RetryPolicy(...), ...)`という
   既存呼び出しが本Release後も無変更で動作することを保証する
6. インターフェースを満たせば`FixedRetryPolicy` /
   `ExponentialBackoffPolicy` / `AdaptiveRetryPolicy`等へ差し替え可能で
   あることを、テスト用のダミー実装（本Release用の最小限のFake/Stub）で
   構造的に確認する（本物の戦略実装は行わない）

---

## 4. Scope

### 対象

* `RetryManager`が`RetryPolicy`に対して実際に依存している面の洗い出し
  （`should_retry()` / `target_statuses` / `max_attempts`）
* 上記を満たすProtocol／ABCの新規定義（新規ファイル）
* 既存`RetryPolicy`が新しいインターフェースを満たすことの確認
  （Protocol採用時は構造的に自動満足、ABC採用時は明示的な継承が必要
  ——8章で確定）
* `RetryManager.__init__` / `from_config()`の`policy`引数の型注釈更新
* インターフェースを満たす最小限のFake/Stub実装によるテスト
  （差し替え可能であることの構造的確認。本物のRetry戦略ではない）
* 関連ドキュメント更新（CHANGELOG / ROADMAP / architecture.md）

### 対象外（今回やらないこと）

* `FixedRetryPolicy` / `ExponentialBackoffPolicy` / `AdaptiveRetryPolicy`
  等、新しいRetry戦略の実装（Non-Goal。本Releaseは差し替え可能な構造の
  整備のみ）
* `RetryPolicy`自体の判定ロジック・環境変数仕様（`RETRY_MAX_ATTEMPTS`等）
  の変更
* `RetryManager.retry()` / `_skip_reason()`の判定ロジック・メッセージ内容
  の変更（型注釈以外は無変更）
* Retry Queue / Cleanup系列（v4.1.0〜v4.4.0）への変更
* `retry_config.py`（`RetryConfig`、Feature Gate）の変更
* Composition Root（実際に複数戦略を選択・切り替える仕組み）の実装
* `scheduler` / `retry_scheduler_decision` / `retry_scheduler_source` /
  `retry_queue`パッケージの改修

---

## 5. Design Principles

* **Foundation First**：差し替え可能な「構造」を用意するところまでを行い、
  実際の新戦略実装・切り替え機構は後続Releaseへ送る
* **Single Responsibility**：「何を再試行対象とするか」の判断はインター
  フェースを満たす戦略オブジェクト側の責務のまま。`RetryManager`は
  「戦略オブジェクトを呼び出す」責務のみを持ち続ける
* **Stateless**：新しいインターフェース自体は状態を持たない。既存
  `RetryPolicy`（frozen dataclass）のStateless性も変更しない
* **Backward Compatibility**：`RetryManager()` /
  `RetryManager.from_config(...)`の既存呼び出し（`RetryPolicy`インスタンスを
  渡す既存コード）は本Release後もまったく同じ結果で動作する。型注釈の
  変更のみで、実行時の挙動（Pythonは型注釈を実行時に強制しない）に影響は
  ない
* **既存コンポーネントへの影響最小化**：`retry_policy.py`本体への変更は
  必要最小限に留める（採用する仕組み——Protocol／ABC——によって「無改修」
  が可能かどうかが変わるため、8章 Open Questionsで確定する）
* **依存の事実に基づく設計**：1章で発見した「`RetryManager`は
  `should_retry()`だけでなく`target_statuses` / `max_attempts`にも直接
  依存している」という事実を無視せず、インターフェース定義に反映する

---

## 6. Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| 新規Protocol／ABC（本Releaseで追加） | `RetryManager`が再試行判定に必要とするインターフェース（`should_retry()`、および必要であれば`target_statuses` / `max_attempts`）を定義する | 判定ロジックの実装・具体的な戦略の提供 |
| `RetryPolicy`（v3.0.0、原則無改修） | 固定ルール（`target_statuses`固定・`max_attempts`環境変数）による再試行可否判定を実装する | 新インターフェースの定義・他戦略との切り替え |
| `RetryManager`（本Releaseで型注釈のみ変更） | 新インターフェースを満たす戦略オブジェクトを呼び出す | 戦略の選択・切り替え・具体的な判定ロジック |

---

## 7. Dependencies

```
retry_engine  ──→ workflow_engine（無改修）
retry_engine  ──→ workflow_monitor（無改修。WorkflowMonitorStatusを型として参照）
retry_engine  ──→ retry_queue（v3.2.0のまま、無改修）
retry_engine  ──→ scheduler（SchedulerEvent型の参照のみ、無改修）
```

新規の依存方向は追加しない。循環importは発生しない。新規Protocol／ABCは
`retry_engine`パッケージ内に閉じる。

---

## 8. Open Questions（Architecture Designで確定する事項）

1. **Protocol（`typing.Protocol`）か ABC（`abc.ABC`）か**：
   - Protocolを採用した場合、既存`RetryPolicy`は**無改修**のまま構造的に
     インターフェースを満たす（このプロジェクトがv4.4.0まで一貫して
     採用してきた「既存コンポーネントへの変更を避ける」パターンと親和性が
     高い）
   - ABCを採用した場合、既存`RetryPolicy`が明示的にそのABCを継承する
     **1行の変更**が必要になる（frozen dataclassとABCの併用は可能だが、
     「既存RetryPolicyの動作は変更しない」という指示を「1行たりとも
     変更しない」まで含むかどうかは要確認）
   - いずれを選ぶかを、既存パターンとの整合性・型チェッカー（mypy等）での
     検出力の観点から比較し確定する
2. **インターフェースの範囲**：1章で発見した`_skip_reason()`の
   `target_statuses` / `max_attempts`への直接依存をどう扱うか
   - (a) インターフェースに`target_statuses` / `max_attempts`を含める
     （3メンバーのインターフェースになるが、`_skip_reason()`は無改修で
     動作する）
   - (b) インターフェースは`should_retry()`のみとし、`_skip_reason()`の
     この依存は「今回のFoundationでは対象外の既知の制約」として明記し、
     将来戦略を追加するReleaseで個別に解消する
   - どちらを選んでも本Releaseの既存動作（`RetryPolicy`のみが実際に
     注入される）に変化はないため、本質的にはドキュメント上の誠実さと
     将来の拡張しやすさのトレードオフの問題である
3. **新規ファイルの配置**：`retry_policy.py`に追記するか、
   `retry_policy_protocol.py`のような新規ファイルに分離するか
   （v4.4.0の`retry_outcome_terminality.py`が新規ファイル分離パターンを
   踏襲している例を参考にする）
4. **`RetryManager`の型注釈の更新範囲**：`__init__` / `from_config()`の
   `policy`引数の型を新インターフェース型に変更するか、`RetryPolicy`型の
   まま据え置き新インターフェースは「ドキュメント上の契約」に留めるか
5. **テスト用Fake/Stubの設計**：差し替え可能性を確認するための最小限の
   Fake実装をどこまで作り込むか（`should_retry()`が固定でTrue/Falseを
   返すだけの最小Stubで十分か）

---

## 9. Acceptance Criteria

* 新しいインターフェース（Protocol／ABC）が定義され、`RetryManager`が
  実際に依存している面（8章Open Question 2の結論に基づく）を過不足なく
  表現していること
* 既存`RetryPolicy`が新しいインターフェースを満たすこと
  （Protocol採用時は構造的に、ABC採用時は明示的な継承で確認）
* 既存の`RetryManager()` / `RetryManager.from_config(...)`（`RetryPolicy`
  インスタンスを渡す既存呼び出し）が本Release後もまったく同じ結果で
  動作すること（既存回帰テスト全PASS）
* インターフェースを満たす最小限のFake/Stubを`RetryManager`に注入しても
  構造的に動作すること（差し替え可能性の確認。本物の戦略実装は伴わない）
* `retry()` / `_skip_reason()`の判定ロジック・メッセージ内容が本Release
  前後で一切変わらないこと
* 新しいRetry戦略（`ExponentialBackoffPolicy`等）が実装されていないこと
  （Non-Goalの遵守確認）
* E2Eテスト全PASS、既存回帰（v2.0.0〜v4.4.0）全PASS

---

## 10. Non-Goals

* `FixedRetryPolicy` / `ExponentialBackoffPolicy` / `AdaptiveRetryPolicy`
  等の具体的な新戦略の実装
* 複数戦略を実行時に選択・切り替えるComposition Root
* `RetryPolicy`の判定ロジック・環境変数仕様の変更
* Retry Queue / Cleanup系列（v4.1.0〜v4.4.0）への変更
* Retry Metrics・Notification・Dashboard

---

## 11. Risks and Mitigations

| リスク | 対策 |
|---|---|
| `should_retry()`のみを最小インターフェースとした場合、将来`target_statuses` / `max_attempts`を持たない戦略を注入すると`_skip_reason()`が`AttributeError`等で破綻する | Architecture Design（Open Question 2）で、インターフェースに含めるか／既知の制約として明記するかを明確に選択し、選択理由をドキュメントに残す。本Releaseでは`RetryPolicy`以外は注入されないため、選択のいずれでも既存動作は壊れない |
| Protocol／ABCどちらを選んでも、型注釈の変更だけでは実行時の安全性を保証できない（Pythonは型を強制しない） | 型チェック（mypy等が導入されていれば）に加えて、Fake/Stub注入によるテストで構造的な互換性を実際に確認する（9章 Acceptance Criteria） |
| 「最小インターフェース」を定義したことで、将来の戦略実装時に「結局`RetryPolicy`固有の属性が必要だった」という手戻りが起きる可能性がある | 本Releaseでは新戦略を実装しないため実際の手戻りは発生しないが、1章の発見（`_skip_reason()`の依存）を明記しておくことで、次にExponential Backoff等を実装するReleaseが同じ調査をやり直さずに済むようにする |

---

## 12. Status

- [x] Project Charter ドラフト作成（本文書、Claude Code作成）
- [ ] ユーザー確認・フィードバック反映
- [ ] Project Charter 確定
- [ ] Architecture Design
