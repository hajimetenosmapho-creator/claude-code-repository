# Project Charter — Release 3.6「Retry Scheduler Decision Wiring」

作成日：2026-07-03
状態：ドラフト（ユーザー確認待ち）
対象：`RetrySchedulerDecision`（v3.5.0）を`SchedulerEngine`（v2.6.0 / v3.4.0）へ
Constructor Injectionで接続し、`SchedulerEngine`から「次に処理すべき候補」を
読み取れるようにする最小統合。`evaluate()` / `run_due()`の判定ロジック（
`SchedulerEvent`生成）には一切組み込まない。`retry_scheduler_decision` /
`retry_scheduler_source` / `retry_queue` / `retry_engine`はいずれも無改修とし、
Retry Engineの起動・`dequeue()`・自動Retry実行は一切行わない。

> **命名についての注記**：ユーザー指示のテーマ名は「Retry Scheduler Integration」
> だが、この名称はRelease 3.3（`docs/design/retry_scheduler_integration_charter.md`、
> `RetrySchedulerSource`Adapter新設）で既に使用済みである。ドキュメント・ファイル名の
> 重複を避けるため、本書ではRelease名を「Retry Scheduler Decision Wiring」とし、
> 設計文書のファイル名を`retry_scheduler_decision_wiring_charter.md` /
> `retry_scheduler_decision_wiring.md`とした（v3.4.0「Retry Scheduler Wiring」＝
> `RetrySchedulerSource`のWiring、との対比で「Decision」を明示）。
> 内容自体はユーザー指示（Scheduler と RetrySchedulerDecision の接続）と完全に一致する。
> この命名変更に問題があれば、Charter確定前に指摘してほしい。

---

## 1. Background

* Retry Scheduler Integration（v3.3.0）：`RetrySchedulerSource` /
  `NullRetrySchedulerSource`が`RetryQueueManager`の読み取り専用API（`list()` /
  `count()`）を`list_pending_retries()` / `count_pending_retries()`として中継する
  Adapterを新設した（消費者不在の先行実装）。
* Retry Scheduler Wiring（v3.4.0）：`SchedulerEngine`が`RetrySchedulerSource` /
  `NullRetrySchedulerSource`をConstructor Injectionで保持できるようにし、
  `count_pending_retries()` / `list_pending_retries()`への薄い委譲メソッドを
  追加した。`evaluate()` / `run_due()`の判定ロジックには一切組み込んでおらず、
  「読み取れる状態を作っただけ」のRelease。
* Retry Scheduler Decision（v3.5.0）：`RetrySchedulerSource`が返す待機中の項目
  一覧から「次に処理すべき候補」を選ぶ専用コンポーネント`RetrySchedulerDecision`
  （`select_candidates(limit)` / `select_next_candidate()`）を新設した。
  `SchedulerEngine`には一切接続しない「消費者不在の先行実装」として、
  独立コンポーネントのまま完結させた（`docs/design/retry_scheduler_decision_charter.md`
  8章 Open Question 1で、`SchedulerEngine`との実配線は将来Releaseへ送ることを
  明記済み）。
* `docs/ROADMAP.md`「v3.x 以降の候補」に、次の未着手項目として次の記載がある：
  「選択結果を`SchedulerEngine`との実配線へ組み込む統合：`RetrySchedulerDecision`の
  選択結果を使って`SchedulerEvent`を生成する等の統合（v3.5.0では`SchedulerEngine`を
  無改修に保つ方針のため意図的に対象外）」。本Release（v3.6.0）はこの項目に相当する。
* ただし、ROADMAP.md記載の「`SchedulerEvent`を生成する等の統合」は本Releaseの
  スコープを超える（4章参照）。本Releaseはあくまで「読み取れる状態を作る」
  Foundationのみとし、v3.4.0が`RetrySchedulerSource`に対して行ったのと同型の
  最小統合（Constructor Injection＋薄い委譲メソッドの追加のみ）に留める。
  `SchedulerEvent`生成への組み込み（候補選択結果を判定ロジックに反映すること）は
  次Release以降に送る。

```
Scheduler（判断、v2.6.0 / v3.4.0）
   │
   ├── RetrySchedulerSource（Adapter、v3.3.0、無改修）
   │        │
   │        └── Retry Queue（v3.1.0、無改修）
   │
   └── RetrySchedulerDecision（v3.5.0） ★本Releaseで接続
            │  RetrySchedulerSourceを内部に保持（v3.5.0のまま無改修）
            ▼
      RetrySchedulerSource（同上）
```

* SchedulerEngine → RetrySchedulerDecision → RetrySchedulerSource → Retry Queue、
  という一方向の参照チェーンが本Releaseで完成する（いずれも読み取り専用）。

---

## 2. Purpose

`SchedulerEngine`が`RetrySchedulerDecision`（v3.5.0）をConstructor Injectionで
保持できるようにし、`RetrySchedulerDecision.select_candidates()` /
`select_next_candidate()`への薄い委譲メソッドを追加する。

v3.4.0で`RetrySchedulerSource`に対して行った統合（Constructor Injection＋
読み取り専用の委譲メソッド追加、`evaluate()` / `run_due()`は無改修）と、
まったく同型のパターンを`RetrySchedulerDecision`に対しても適用する。

`evaluate()` / `run_due()`（時刻ベースの判定サイクル・`SchedulerEvent`生成）には
一切手を加えない。「候補を選べる状態を作る」だけに留め、選んだ候補を使って
実際に何かをする（`SchedulerEvent`の生成に反映する・Retry Engineへ渡す等）ことは
次Release以降に送る。

---

## 3. Goals

本Releaseで確立する Retry Scheduler Decision Wiring は、次のことだけを行う。

1. `SchedulerEngine.__init__`が`RetrySchedulerDecision`（またはその代替）を
   Constructor Injectionで保持できるようにする（デフォルト`None`。省略時の
   フォールバック方式は8章Open Question 1・2で確定する）
2. `SchedulerEngine`に、保持した`RetrySchedulerDecision`への薄い委譲メソッドを
   追加する（`RetrySchedulerDecision.select_candidates()` /
   `select_next_candidate()`への1行委譲。具体的なメソッド名は8章Open Question 3で
   確定する）
3. 上記の追加によっても、`evaluate()` / `run_due()`（判定ロジック・
   `SchedulerEvent`生成）は本Releaseでも無改修を維持する
4. 上記の追加によっても、`retry_scheduler_decision` / `retry_scheduler_source` /
   `retry_queue` / `retry_engine`はいずれも本Releaseでも無改修（ゼロ改修）を
   維持する
5. 既存の`SchedulerEngine()` / `SchedulerEngine(clock=...)` /
   `SchedulerEngine(retry_source=...)`呼び出しが、本Release後もすべて無変更で
   動作すること（後方互換性維持。v3.4.0と同じ方針）

---

## 4. Scope

### 対象

* `SchedulerEngine.__init__`への`RetrySchedulerDecision`（またはその代替）の
  Constructor Injection追加
* `SchedulerEngine`への読み取り専用の委譲メソッド追加（候補選択結果を返すのみ）
* 単体テスト・E2Eテスト（`tests/test_e2e_v3_6_0_retry_scheduler_decision_wiring.py`）
* 関連ドキュメント更新（CHANGELOG / ROADMAP / architecture.md）

### 対象外（今回やらないこと）

* `evaluate()` / `run_due()`の判定ロジックへの候補選択結果の組み込み
  （`SchedulerEvent`の生成に候補選択結果を反映すること。ROADMAP.md記載の
  「`SchedulerEvent`を生成する等の統合」はここに含まれるため対象外）
* Retry Engine の起動（`RetryManager.retry()`の呼び出し）
* `RetryQueueManager.dequeue()`の呼び出し
* `RetryQueueManager.remove()`の呼び出し
* Retry Queue の更新（`enqueue` / `dequeue` / `remove`を含むあらゆる書き込み）
* 自動Retry実行（選ばれた候補を実際に再試行する仕組み）
* 永続化
* `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` /
  `retry_engine`パッケージ自体の改修（いずれもゼロ改修を維持）
* 新しいFeature Gate環境変数の追加・Configクラスの追加・Managerパターン
  （`from_config()` / `from_env()`等の起動口）の採用（v3.3.0・v3.4.0・v3.5.0からの
  継続方針。10章 Non-Goals参照）

---

## 5. Design Principles

* **Foundation First**：接続（読み取れる状態を作ること）のみを行う。選択結果を
  使った実行・判定ロジックへの組み込みは後続Releaseへ送る。v3.4.0の
  `RetrySchedulerSource`統合と同型のパターンを踏襲する
* **Single Responsibility**：`SchedulerEngine`は「時刻ベースの判定」と
  「pending retryの参照（v3.4.0）・候補選択の参照（本Release）」という薄い委譲を
  担うのみ。候補選択ロジック自体（`RetrySchedulerDecision`）・Queue管理
  （`retry_queue`）・Adapterとしての中継（`retry_scheduler_source`）のいずれも
  複製・肩代わりしない
* **Stateless**：`SchedulerEngine`は候補選択結果を独自にキャッシュ・保持しない。
  委譲メソッドを呼び出すたびに`RetrySchedulerDecision`経由で最新状態を取得する
* **Constructor Injection のみ**：セッターインジェクション・実行時の差し替え
  メソッド・ファクトリメソッド（`from_config()`等）は追加しない
* **Read Only**：`SchedulerEngine`が呼び出すのは`RetrySchedulerDecision`の
  読み取り専用メソッド（`select_candidates()` / `select_next_candidate()`）のみ。
  Queueの状態を変更する操作には一切到達しない
* **Backward Compatibility**：既存の`evaluate()` / `run_due()`の呼び出し・
  既存のConstructor呼び出し（`retry_source`まで）は、本Release前とまったく
  同じ結果になる

---

## 6. Responsibilities

| コンポーネント | 責務 | 責務でないもの |
|---|---|---|
| `RetryQueueManager`（v3.1.0、無改修） | Queueへの出し入れ・整列 | 候補選択・実行判断 |
| `RetrySchedulerSource` / `NullRetrySchedulerSource`（v3.3.0、無改修） | Retry Queueの状態の読み取り専用な中継 | 候補選択ロジック・実行判断 |
| `RetrySchedulerDecision`（v3.5.0、無改修） | `RetrySchedulerSource`が返す既存順序から「次に処理すべき候補」を選ぶ | 実行判断の確定／実行／`SchedulerEngine`との接続の起点になること（受け身の被参照のみ） |
| `SchedulerEngine`（本Releaseで変更） | 時刻ベースの判定・pending retryの件数/一覧の読み取り委譲（v3.4.0）・候補選択結果の読み取り委譲（本Release） | 候補選択ロジックの再実装／判定ロジックへの候補選択結果の反映／実行 |

---

## 7. Dependencies

```
scheduler                ──→ retry_scheduler_decision（NEW。公開APIのみ：
                              RetrySchedulerDecision / select_candidates() /
                              select_next_candidate()）
scheduler                ──→ retry_scheduler_source（v3.4.0のまま、無改修）
retry_scheduler_decision ──→ retry_scheduler_source（v3.5.0のまま、無改修）
retry_scheduler_source   ──→ retry_queue（v3.3.0のまま、無改修）
retry_engine              ──→ （本Releaseでは一切関与しない）
```

* 新規に追加される依存方向は `scheduler → retry_scheduler_decision` の一方向のみ
* `retry_scheduler_decision`は`scheduler`を一切importしない（逆方向依存なし。
  v3.5.0のまま維持）
* 循環importは発生しない

---

## 8. Open Questions（Architecture Designで確定する事項）

Project Charterの時点では確定せず、次工程のArchitecture Designで検討する。

1. **Constructor Injectionの受け方**：`SchedulerEngine`が`RetrySchedulerDecision`
   インスタンスを外部から直接受け取る（呼び出し側が`RetrySchedulerDecision(
   retry_source)`を組み立てて渡す）か、`SchedulerEngine`が自身の保持する
   `self._retry_source`から内部的に`RetrySchedulerDecision`を都度構築するか。
   前者は「`SchedulerEngine`に渡した`retry_source`」と「`RetrySchedulerDecision`に
   渡した`retry_source`」が別インスタンスになりうる二重管理のリスクがある。
   後者は`SchedulerEngine`の既存Constructor引数（`retry_source`）のみで完結し、
   新規引数が不要になる可能性がある
2. **省略時のフォールバック方式**：上記1で「外部から直接受け取る」場合、
   デフォルト`None`時のフォールバックとして`NullRetrySchedulerDecision`
   （未実装）が必要か、それとも`RetrySchedulerDecision(NullRetrySchedulerSource())`
   を都度組み立てれば足りるか（v3.5.0 Charter 8章 Open Question 2で
   「Null Object Patternは採用しない」と判断した経緯との整合性を検討する）
3. **委譲メソッド名**：`select_pending_retries(limit)` /
   `select_next_pending_retry()`のように`SchedulerEngine`内の既存命名
   （`list_pending_retries` / `count_pending_retries`）との一貫性を優先するか、
   `RetrySchedulerDecision`側の名称（`select_candidates` /
   `select_next_candidate`）をそのまま踏襲するか
4. **`evaluate()` / `run_due()`との関係の明文化**：本Releaseでは判定ロジックに
   一切組み込まないことをコード・テストの両面でどう構造的に保証するか
   （v3.4.0の`tests/test_e2e_v3_4_0_retry_scheduler_wiring.py`と同様の
   Architecture Guardパターンを踏襲する想定）

---

## 9. Acceptance Criteria

* `SchedulerEngine`が`RetrySchedulerDecision`の`select_candidates()` /
  `select_next_candidate()`以外のメソッドを一切呼び出さないこと（構造的確認。
  Spyオブジェクトによりv3.3.0・v3.4.0・v3.5.0と同じ手法で検証）
* `SchedulerEngine`が`RetryQueueManager.dequeue()` / `remove()`・
  `RetryManager.retry()`へ到達する呼び出し経路が構造的に存在しないこと
* `evaluate()` / `run_due()`が、本Release前とまったく同じ入力に対して
  まったく同じ`SchedulerEvent`列を返すこと（既存回帰テストで確認。
  候補選択結果が判定ロジックに一切影響しないことの確認）
* `src/retry_scheduler_decision/` / `src/retry_scheduler_source/` /
  `src/retry_queue/` / `src/retry_engine/`配下の全ファイルに差分がないこと
  （`git diff`で確認、ゼロ改修）
* 既存の`SchedulerEngine()` / `SchedulerEngine(clock=...)` /
  `SchedulerEngine(retry_source=...)`呼び出しが本Release後も無変更で動作すること
  （後方互換性の回帰確認）
* `scheduler`配下に新しいFeature Gate環境変数・`Config`を名前に含むクラス・
  `enabled`フィールドを持つクラスが追加されていないこと
* E2Eテスト全PASS・既存回帰（`v2.0.0`〜`v3.5.0`）全PASS
  （ただし、`src/scheduler/scheduler_engine.py`に変更差分が生じることに伴う
  既存Architecture Guard（`git diff`ベースのテスト）のFAILは、`[KI-3]` /
  `[KI-4]`と同型の既知差分として許容し、Test工程でCHANGELOG.mdへ記録する）

---

## 10. Non-Goals

* `evaluate()` / `run_due()`の判定ロジックへの候補選択結果の組み込み
  （`SchedulerEvent`生成への反映）
* Retry Engine（`RetryManager`）の起動・呼び出し
* `RetryQueueManager.dequeue()` / `remove()`の呼び出し
* 選ばれた候補を実際に再試行すること（自動Retry実行）
* Retry Queueの永続化
* `retry_scheduler_decision` / `retry_scheduler_source` / `retry_queue` /
  `retry_engine`パッケージ自体の変更（いずれもゼロ改修を維持）
* 新しいFeature Gate環境変数の追加
* Configクラスの追加
* Managerパターン（`from_config()` / `from_env()`等の起動口）の採用

---

## 11. Directory Structure（想定）

```text
src/scheduler/
├── scheduler_engine.py     # 変更：retry_decision Constructor Injection追加
│                            # ＋読み取り専用の委譲メソッド追加
└── __init__.py              # 変更（docstringのみ想定）

src/retry_scheduler_decision/  # 全ファイル無改修
src/retry_scheduler_source/    # 全ファイル無改修
src/retry_queue/               # 全ファイル無改修
src/retry_engine/              # 全ファイル無改修

tests/
└── test_e2e_v3_6_0_retry_scheduler_decision_wiring.py   # 新規
```

---

## 12. Risks and Mitigations

| リスク | 対策 |
|---|---|
| `SchedulerEngine`が`retry_source`と`retry_decision`を別々に保持する設計（8章Open Question 1）を採った場合、両者に異なるインスタンスが渡され状態が食い違う | Architecture Designで「`SchedulerEngine`内部で`self._retry_source`から`RetrySchedulerDecision`を構築する」案を優先的に検討し、二重管理を避ける方針を確定する |
| `src/scheduler/scheduler_engine.py`の変更により、v2.7.0〜v3.5.0の一部Architecture Guard（`git diff`ベースのテスト）が`[KI-3]` / `[KI-4]`と同様にFAILする | Charter承認時点で許容済みのリスクとして扱う。Test工程でFAIL内容を確認し、CHANGELOG.mdのKnown Issuesへ記録する（本質的な制約は新規テストで別途構造的に確認する） |
| 候補選択結果を「読み取れるだけ」で終える本Releaseの価値が、`SchedulerEvent`生成へ組み込む次Releaseまで実運用に結びつかない | v3.3.0・v3.4.0でも同様の「消費者不在／未接続」を経て段階的に統合してきた前例がある。本Releaseも同じFoundation Firstパターンとして扱う |
| ユーザー指示のテーマ名「Retry Scheduler Integration」とRelease 3.3の既存テーマ名が重複する | 本書冒頭の注記のとおり、ファイル名・Release名を「Retry Scheduler Decision Wiring」に変更する提案をした。Charter確定前にユーザーへ確認する |

---

## 13. Status

- [x] Project Charter ドラフト作成（本文書、Claude Code作成）
- [ ] ユーザー確認・フィードバック反映
- [ ] Project Charter 確定
- [ ] Architecture Design（次工程。本Releaseでは着手しない）
