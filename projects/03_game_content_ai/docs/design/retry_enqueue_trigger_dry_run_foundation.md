# Retry Enqueue Trigger Dry Run Foundation（v5.8.0）

作成日：2026-07-12
作成者：Claude Code（Architecture Design・Architecture Review・実装）／ユーザー（最終承認）
状態：**完成版（実装済み）**

---

## 1. Release Goal

`--dry-run`指定時に`RetryEnqueueTrigger.enqueue_pending_failures()`が実際にRetry Queueへ書き込む（`RetryQueueManager.enqueue()`を呼ぶ）副作用を抑止できるようにする。これにより、`[KI-23]`（「`--dry-run`＝完全に無害」という利用者の誤解リスク）を解消する。

**成立させないこと**：Queue容量判定（`max_queue_size`）を含む完全なシミュレーション、dry-run時の予定Enqueue件数の観測機能、Result Contractの拡張、CLI表示の変更、`--loop`対応、Daemon化。

---

## 2. Current Problem

`RetryRuntimeOrchestrator.run_once(dry_run=True)`は`RetryExecutor`以降（実行・Queue更新・Cleanup・History記録）を安全側に倒せる（v5.6.0）が、`trigger.enqueue_pending_failures()`は`dry_run`引数を持たないため、`--dry-run`指定時もWorkflowMonitor上のFAILED/TIMEOUTが実際にRetry Queueへenqueueされ続けていた（`[KI-23]`）。CLIで一般公開されている以上、これは利用者の期待（「dry-runなら何も変わらない」）を裏切る構造上のギャップだった。

---

## 3. Scope

- `RetryEnqueueTrigger.enqueue_pending_failures()`（`dry_run: bool = False`引数の追加、Queueへの書き込み抑止ロジック）
- `RetryRuntimeOrchestrator.run_once()`内の呼び出し1行（`trigger.enqueue_pending_failures(..., dry_run=dry_run)`への伝播。メソッドシグネチャ自体は無変更）

---

## 4. Out of Scope

以下はいずれも無改修：

`RetryEnqueueTriggerResult` / `RetryRuntimeCycleResult` / `scripts/run_retry_runtime.py` / `format_summary()` / `RetryCompositionRoot` / `RetryManager` / `RetryExecutor` / `RetryQueueManager` / `RetryHistoryManager` / `RetryEnqueueGuard` / `RetryRuntimeLoop` / `NullRetryEnqueueTrigger` / CLI引数解析 / Daemon関連 / Loop Wiring

`dry_run_planned`などの新規Resultフィールドは追加しない。

---

## 5. Architecture Review過程での再検討

Architecture Design初版では、`RetryEnqueueTriggerResult`へ`dry_run_planned: int = 0`を追加し、`format_summary()`にも表示を追加する案（案A）を提示したが、ユーザーレビューにより以下2点の指摘を受け、再検討した。

### 5.1 Result Contract変更の再検討

`RetryEnqueueTriggerResult`は「実際に行われた結果」のみを表す契約として一貫していた。「予定」（`dry_run_planned`）を追加すると、この契約の意味が変化し、通常実行時には常に`0`となる無関係なフィールドが増える。目的（Queueへの書き込み抑止）に対してResult Contract変更は必要条件ではないと判断し、**Result型は完全に無変更**とする方針へ変更した。

### 5.2 format_summary()変更の再検討

`RetryEnqueueTriggerResult`の構造・意味を一切変えない以上、`format_summary()`は変更せずとも、dry_run時に`enqueued=0`を正しく表示するようになる（既存ロジックが`trigger_result.enqueued`をそのまま表示するだけのため）。むしろv5.7.0時点では`--dry-run`指定時も`enqueued`が実数を表示してしまう状態（`[KI-23]`の症状そのもの）であり、本Releaseで`queue.enqueue()`自体を抑止すれば、既存の`format_summary()`が変更なしにその修正結果を正しく表示するようになる。`[DRY RUN MODE]`バナー（既存、v5.7.0）と合わせて、利用者への説明は十分と判断し、**`format_summary()`は無変更**とした。

---

## 6. Adopted Design（案B）

`RetryEnqueueTrigger.enqueue_pending_failures()`へ`dry_run: bool = False`を呼び出し時引数として追加する。`dry_run=True`の場合も以下は通常どおり実行する：

- Workflow Monitorの走査
- Retry Historyの参照
- next_attemptの算出
- RetryEnqueueGuardの判定
- Retry Queueの重複確認

Guardを通過し、Queue重複も存在しない候補についてのみ、`RetryQueueManager.enqueue()`を呼び出さず、その候補の処理を終了する（`enqueued` / `failed`いずれにも加算しない）。

```python
if guard_decision.outcome == RetryEnqueueGuardOutcome.BLOCK:
    skipped_history += 1
    continue

if self._queue.exists(record.run_id):
    skipped_existing += 1
    continue

if dry_run:
    continue

result = self._queue.enqueue(...)
```

`RetryRuntimeOrchestrator.run_once()`内では、既存の`dry_run`値をTriggerへ伝播する：

```python
trigger_result = self.trigger.enqueue_pending_failures(
    max_attempts=self.policy.max_attempts, dry_run=dry_run,
)
```

---

## 7. API Design

```python
def enqueue_pending_failures(
    self,
    limit: int | None = None,
    max_attempts: int = 1,
    dry_run: bool = False,
) -> RetryEnqueueTriggerResult:
```

`max_attempts`と同じ「呼び出し時引数、コンストラクタ非保持」パターンを踏襲する（v5.0.0 Architecture Review Finalの確定方針）。`RetryEnqueueTrigger.__init__`は本Releaseでも完全に無変更。

---

## 8. Side Effect Boundary

| 処理 | Dry Run時 |
|---|---|
| Scheduler Event読み取り | 対象外（Triggerはschedulerに触れない） |
| Retry History読み取り（`history.get()`） | 許可（読み取り専用） |
| Retry Queue読み取り（`queue.exists()`） | 許可（読み取り専用） |
| RetryEnqueueGuard判定 | 許可（読み取り専用の判定ロジック） |
| Retry Queueへの書き込み（`queue.enqueue()`） | **禁止**（本Releaseの抑止対象そのもの） |
| Retry Historyへの書き込み | 対象外（`RetryEnqueueTrigger`は元々historyに書き込まない） |
| Retry実行 | 対象外（v5.6.0で対応済み、無改修） |
| Queue Removal / Cleanup / Terminal Cleanup | 対象外（Enqueueより下流、無改修） |

---

## 9. Result Contract

`RetryEnqueueTriggerResult`の構造・各フィールドの意味は完全に維持する。

- `enqueued`：dry_run=Trueの場合は加算しない（「実際に書き込まれた件数」という既存の意味を変えない。常に`0`）
- `failed`：dry_run=Trueの場合は加算しない（`queue.enqueue()`を呼ばないため、REJECTED判定自体が発生しない）
- `skipped_existing` / `skipped_status` / `skipped_history`：dry_run=True/Falseに関わらず、既存の判定結果に応じて従来どおり加算する

予定Enqueue件数を表す新しいカウンタは追加しない。

---

## 10. Rejected Alternatives

1. **RetryEnqueueTriggerへ`dry_run: bool = False`を追加**（＝採用案）
2. **RetryEnqueueGuardへdry_run責務を持たせる**：却下。Guardの責務は「`next_attempt`が上限を超えるか」の判定のみであり、Queueへの書き込み可否とは無関係。Single Responsibilityに反する
3. **RetryQueueManager.enqueue()へdry_runを追加**：却下。`retry_queue`はv3.1.0以降ほぼ全Releaseで「無改修」を維持してきた独立した葉パッケージであり、CLI都合の概念を汎用Queueプリミティブへ持ち込むことは「既存資産は無改修で呼び出す」「最小変更原則」に反する
4. **RetryRuntimeOrchestrator側でTrigger自体を呼ばない**：却下。呼ばないと`scanned` / `skipped_status` / `skipped_history`等の診断情報が一切得られず、観測性が低下する。v5.6.0で確立した「読み取りは維持し副作用のみ抑止する」という設計哲学とも矛盾する
5. **Composition RootでDry Run用Null Objectを差し替える**：却下。既存`NullRetryEnqueueTrigger`は「スキャンすら行わない」実装であり、dry-runで必要な「スキャン＋判定は行うが書き込みだけ止める」動作とは性質が異なる。Composition Rootの責務（組み立てのみ）とも矛盾する
6. **Dry Run PolicyまたはExecution Contextを新設する**：却下。v5.6.0で既に同種の判断（`dry_run`のRequest Object化）が見送られており、本Releaseの`dry_run`はretry_enqueue_trigger内で2つ目の呼び出し時引数（`max_attempts`に次ぐ）に過ぎず、Policy Object化の閾値には未到達
7. **（Architecture Review初版で提示、ユーザーレビューにより却下）`RetryEnqueueTriggerResult`へ`dry_run_planned`追加＋`format_summary()`変更（案A）**：却下。目的（Queueへの書き込み抑止）に対してResult Contract変更・CLI表示変更は必要条件ではなく、「実際に行われた結果のみを表す」という既存契約の一貫性を崩すコストに見合わない（5節参照）

---

## 11. Trade-offs

**利点**：`[KI-23]`を構造的に解消。既存呼び出し・既存Constructor・`RetryEnqueueGuard`・`RetryQueueManager`・`RetryEnqueueTriggerResult`・`format_summary()`・`scripts/run_retry_runtime.py`はいずれも無改修。読み取り処理を維持するため、dry-runと実実行で「どの候補が選ばれるか」の一貫性が保たれる。

**欠点・将来負債**：Guardを通過しQueue重複も存在しない候補は、dry-run時にどのカウンタにも加算されない。そのため`scanned == enqueued + skipped_existing + skipped_status + skipped_history + failed`という暗黙の合計不変条件が、dry-run時には成立しない場合がある（12節参照）。

---

## 12. Known Limitation

Dry Run時は、Guard通過かつQueue重複なしの候補が既存カウンタのいずれにも加算されない。そのため、Dry Run時には以下のような暗黙の合計不変条件が成立しない場合がある：

```text
scanned == enqueued + skipped_existing + skipped_status + skipped_history + failed
```

これは、既存フィールドの意味を偽らず、Result Contractを変更しないことを優先した意図的なトレードオフである。Dry Run時の予定Enqueue件数の観測機能は、本Releaseでは実装しない（15節「将来のDry Run観測性に関するTechnical Debt」参照）。

また、`dry_run_planned`相当の概算値を仮に提供したとしても、Queue容量上限（`max_queue_size`）による`REJECTED`判定は`queue.enqueue()`内部でのみ行われるため、Dry Run時にはシミュレートできない（`RetryQueueManager`を無改修に保つ制約による）。将来この観測性が必要になった場合も、この近似性は残る。

---

## 13. Architecture Review

### Design Policyとの整合性

| 観点 | 判定 |
|---|---|
| Foundation First | ✅ bool引数1つの追加のみ、運用配線を伴わない |
| Small Release | ✅ 本体変更2ファイルのみ |
| Stateless | ✅ `dry_run`はConstructor状態化しない |
| Single Responsibility | ✅ Guardの責務は不変、Triggerの責務範囲内で完結 |
| Constructor Injection | ✅ `__init__`無変更 |
| Composition優先 | ✅ `RetryCompositionRoot`無改修 |
| Business Logicをscriptsへ置かない | ✅ `scripts/run_retry_runtime.py`無改修 |
| OrchestratorへCLI責務を追加しない | ✅ 既存の`dry_run`パラメータを1箇所へ伝播するのみ |
| RetryManagerを肥大化させない | ✅ 無改修 |
| Composition RootへExecution責務を戻さない | ✅ 無改修 |

### Risks

- **Dry Runなのに書き込みが残る可能性**：`queue.enqueue()`呼び出し自体をガードすることで解消。Spy（実行時）＋AST検査（補助）の両方で構造的に確認済み（14節）
- **既存summaryの意味が変わる可能性**：`format_summary()`は無変更のため意味は変わらない。dry_run時の`enqueued`表示が「実数」から「常に0」へ変わる点は、`[KI-23]`解消そのものであり意図した挙動
- **既存テストとの互換性**：`enqueue_pending_failures()`のシグネチャ検証系Guard・`src/retry_enqueue_trigger`ディレクトリの無改修前提Guardが新規FAILする（KI-25、17節参照）。加えて、`[KI-23]`の症状自体を「期待値」として固定していたv5.6.0の一部テストが、本Releaseの意図的な仕様変更により新規FAILする（KI-26、17節参照）

### Future Impact

- **Retry Runtime Loop Wiring / CLI `--loop`**：無関係。`dry_run`はcall-time引数のため両方の将来像に対して中立
- **複数Dry Runサイクル**：Enqueue側の全処理が読み取り専用（書き込みのみ抑止）のため、複数回のdry-run実行は冪等
- **Dry Run結果の観測性**：本Releaseでは向上しない（15節）

### Recommendation

**Approve（実装完了）**

---

## 14. Test Strategy

`tests/test_e2e_v5_8_0_retry_enqueue_trigger_dry_run_foundation.py`（20テスト・64アサーション、全PASS）で以下を確認した。

1. dry_run=True時、Monitor走査・History参照・Guard判定・Queue重複確認は実行されるが、Spyにより`queue.enqueue()`が一度も呼ばれないことを構造的に確認
2. dry_run=True時、`enqueued` / `failed`が0のまま、`skipped_existing` / `skipped_status` / `skipped_history`は既存どおり機能すること
3. dry_run=True後、Queue内容が変更されないこと・複数回のdry-runで結果が冪等であること
4. dry_run=False・省略時は既存どおり`queue.enqueue()`が呼ばれ、`enqueued` / `failed`が正しく加算されること
5. `RetryRuntimeOrchestrator.run_once(dry_run=...)`からの伝播をFake実装を使わない実コンポーネントによるE2Eで確認（dry_run=True/False/省略の3パターン）
6. シグネチャ・Result Contract（`RetryEnqueueTriggerResult`のフィールド構成、`NullRetryEnqueueTrigger`のシグネチャ、`RetryRuntimeOrchestrator`のシグネチャ）が無変更であること
7. 無改修対象ファイル・ディレクトリ（`scripts/run_retry_runtime.py`・`RetryRuntimeCycleResult`・`RetryCompositionRoot`・`RetryManager`・`RetryExecutor`・`RetryQueueManager`・`RetryHistoryManager`・`RetryEnqueueGuard`・`RetryRuntimeLoop`等）に変更がないこと（git diff）
8. `format_summary()`のシグネチャ・出力文字列が無変更であること、実CLIサブプロセス（`--dry-run`指定）が正常終了すること
9. AST検査（補助）：`dry_run`をテストし`continue`するIf文が`queue.enqueue()`呼び出しより前に位置すること（実行時Spy検証の補助）
10. 実行前後でファイルが一切作成されないこと（副作用なしの確認）

既存回帰確認として、変更前後で関連する既存テストファイルを機械的に比較し、新規に発生した差分を「本Releaseの仕様変更による意図的な差分」「Architecture Guard差分（KI-25）」「既存Known Issue（本Releaseと無関係）」に分類した（`docs/CHANGELOG.md` `[KI-25]` `[KI-26]`参照）。

---

## 15. 将来のDry Run観測性に関するTechnical Debt

Dry Run時に「実際にはenqueueしていないが、enqueue予定だった項目」の件数を観測する機能は、本Releaseでは提供しない。将来必要になった場合の再検討候補：

- `RetryEnqueueTriggerResult`への専用フィールド追加（本Releaseで一度は検討し、Result Contractの一貫性を優先して見送った案。10節#7参照）
- Queue容量上限（`max_queue_size`）を考慮した正確なシミュレーションには、`RetryQueueManager`側に非破壊の容量確認API（例：`can_enqueue()`）が必要になる可能性がある（現状は`queue.enqueue()`内部でのみ判定されるため、Dry Run時は容量超過を検出できない。12節参照）

いずれも「必要になった時点で再検討する」（Development Charter「抽象化は必要になってから行う」）に従い、本Releaseでは対応しない。
