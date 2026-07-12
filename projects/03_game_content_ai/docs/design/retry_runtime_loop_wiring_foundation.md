# Retry Runtime Loop Wiring Foundation（v5.9.0）

作成日：2026-07-12
作成者：GPT-5.6 Sol（Architecture Design・Architecture Review）／Claude Code（Implementation・Test・Documentation）／ユーザー（最終承認）
状態：**完成版（実装済み）**

---

## 1. Release Goal

`scripts/run_retry_runtime.py`から、Release 5.5で追加済みの`RetryRuntimeLoop`（`src/retry_runtime_loop/`）を明示的なCLI引数（`--loop` / `--interval-seconds`）で選択し、繰り返し実行できるようにする。デフォルト動作（引数なし）は従来どおり単発実行のまま維持する。

**成立させないこと**：Daemon化、Windows Service化、バックグラウンド化、Graceful Shutdown、独自Exit Code体系、Scheduler API再設計、Structured Logging。

---

## 2. Scope

- `scripts/run_retry_runtime.py`のみ

既存契約（`RetryRuntimeLoop.__init__(run_once_fn, sleep_fn, should_continue_fn, interval_seconds)`、公開メソッドは`run()`のみ）だけで配線可能であることをArchitecture Reviewで確認済みのため、`src/retry_runtime_loop/`を含む本番パッケージ側の変更は一切不要だった。

---

## 3. Out of Scope

Daemon化 / Windows Service化 / バックグラウンド化 / PIDファイル / Process Lock / 二重起動防止機構 / 自動再起動 / ログローテーション / Structured Logging / サイクル番号 / タイムスタンプ付与 / JSON Summary / 独自Signal Handler / SIGTERM対応 / Graceful Shutdownサブシステム / Error Continuation Policy / 例外後の自動継続 / 独自Exit Code体系 / Scheduler API再設計 / Summary Formatterクラス化 / intervalの環境変数化 / `RetryRuntimeLoop`のAPI変更 / `RetryRuntimeOrchestrator`の変更 / `RetryCompositionRoot`の変更 / `RetryManager`の変更

---

## 4. Architecture

### 単発実行（無変更）

```
CLI → argparse → RetryCompositionRoot.from_env() → RetryRuntimeOrchestrator.from_composition_root()
    → orchestrator.run_once(dry_run=...) → format_summary() → print()
```

### Loop実行（新設）

```
CLI → argparse（--loop, --interval-seconds）
    → RetryCompositionRoot.from_env() → RetryRuntimeOrchestrator.from_composition_root()
    → RetryRuntimeLoop(
          run_once_fn=run_cycle,      # main()内のローカル関数
          sleep_fn=time.sleep,
          should_continue_fn=lambda: True,
          interval_seconds=interval_seconds,
      )
    → loop.run()
```

`RetryRuntimeLoop`は`src/retry_runtime_loop/`の本番クラスをそのまま`from retry_runtime_loop import RetryRuntimeLoop`でimportして使用する（`RetryCompositionRoot`はLoopを組み立てないため、script層で直接構築する）。

---

## 5. CLI契約

```text
--loopなし・interval未指定   → 単発実行（従来どおり）
--loopなし・interval指定     → CLIエラー（parser.error()、非0終了）
--loopあり・interval未指定   → 60秒
--loopあり・interval指定 > 0 → 指定値を使用
--loopあり・interval指定 <= 0 → CLIエラー（parser.error()、非0終了）
```

`--interval-seconds`は`type=float`・`default=None`とし、「利用者が明示指定したか」を`None`判定で区別できるようにした。バリデーションはargparseの標準的な境界検証（`parser.error()`）のみで行い、独自Validatorクラスは追加していない。

---

## 6. interval契約

- デフォルト値：**60秒**（`--loop`指定時のみ適用。`--loop`なしでは無関係）
- 有効範囲：`interval_seconds > 0`。1秒以上を許可する。根拠のない追加の最低値（例：最低10秒）は設けない
- 環境変数化：行わない（YAGNI。既存の`--dry-run`もCLI引数のみで環境変数化していない前例と整合）
- 型検証：argparseの`type=float`によるパース失敗はargparse標準の非0終了・エラーメッセージに委ねる

---

## 7. dry_run伝播

`RetryRuntimeLoop`へdry_run属性・引数は一切追加していない。`main()`内のクロージャ`run_cycle()`が`args.dry_run`を捕捉し、`orchestrator.run_once(dry_run=args.dry_run)`へ伝播する。

```python
def run_cycle():
    result = orchestrator.run_once(dry_run=args.dry_run)
    print(format_summary(result))
    return result
```

`RetryRuntimeLoop`は`run_once_fn`の戻り値を一切解釈しない既存契約（v5.5.0）を維持したまま、Loopはdry_runの意味を一切知らない。

---

## 8. Summary出力

`RetryRuntimeLoop`のAPIは変更せず、`run_cycle()`内で`format_summary()`を呼び出し`print()`する。サイクルごとにこの出力が自然に繰り返される。サイクル番号・タイムスタンプ・JSON出力等は追加していない（Structured Loop Logging Foundationへ申し送り）。

`RetryRuntimeCycleResult` / `format_summary()`の公開契約・単発実行時の既存出力・dry-run表示の既存形式はいずれも維持した。

---

## 9. KeyboardInterrupt方針

Loop実行（`loop.run()`）のみを囲む最小範囲で`KeyboardInterrupt`を捕捉する。

```python
try:
    loop.run()
except KeyboardInterrupt:
    print("Retry runtime loop stopped.")
```

Ctrl+Cは運用者による意図的な正常停止として扱い、短い終了メッセージを表示したうえで`main()`が正常return（結果としてexit code 0）する。捕捉対象は`KeyboardInterrupt`のみであり、それ以外の例外はこの`try/except`を通過しない（`except`節が`KeyboardInterrupt`のみを指定しているため）。単発実行パスには`try/except`を追加していない。

独自Signal Handler・SIGTERM対応は採用しなかった（12節「却下案」参照）。

---

## 10. Exception Policy

fail-fastを維持する。

```text
run_cycle()で未処理例外
  → RetryRuntimeLoop.run()から伝播（v5.5.0の既存契約）
  → 直後のsleepは実行されない
  → main()の唯一のtry/exceptはKeyboardInterruptのみを捕捉するため通過しない
  → プロセス非0終了
```

例外を握りつぶして次サイクルへ進む設計（Error Continuation Policy）は本Releaseの対象外とした。

---

## 11. External Schedulerとの使い分け

`--loop`使用時、同じRetry RuntimeをWindows タスクスケジューラ等の外部スケジューラから重複して定期起動しないこと。内部Loopと外部スケジューラを併用すると、Retry対象の二重実行につながるおそれがある。この注意事項は`scripts/run_retry_runtime.py`のdocstringに明記した。Runtime Lock・PID Lock等の二重起動防止機構は本Releaseの対象外（Out of Scope）。

---

## 12. 採用案・却下案

### 採用案

- CLIに`--loop`（`action="store_true"`）・`--interval-seconds`（`type=float`、`default=None`）を追加
- デフォルトは単発実行
- 既存`RetryRuntimeLoop`をそのまま使用（`src/retry_runtime_loop/`は無変更）
- `orchestrator.run_once(dry_run=args.dry_run)`を薄いローカル関数`run_cycle()`として注入
- 各サイクルのSummaryは`run_cycle()`内で出力
- `sleep_fn=time.sleep`、`should_continue_fn=lambda: True`
- 例外はfail-fast
- Ctrl+C（KeyboardInterrupt）のみ`main()`側で捕捉し正常終了（exit code 0）として扱う
- `--interval-seconds`はCLI引数のみ、`--loop`と併用時のみ有効、0以下は拒否

### 却下案

| # | 案 | 却下理由 |
|---|---|---|
| 1 | scriptへ直接whileループを書く | 既存`RetryRuntimeLoop`（v5.5.0）の投資を活かせず車輪の再発明になる |
| 2 | `RetryRuntimeOrchestrator`へloopメソッドを追加 | Orchestratorの責務（1サイクル分の実行順序）を超えてCLI/運用の関心事を持ち込むことになる |
| 3 | `RetryCompositionRoot`へrun_loopを追加 | Composition Rootの責務（組み立てのみ）を超え、Execution責務を持ち込むことになる |
| 4 | `RetryRuntimeLoop`へdry_run属性を追加 | LoopのStateless性・Business Logic皆無という核心的価値を損なう。クロージャで完全に代替可能 |
| 5 | Loopをデフォルト動作にする | Backward Compatibilityを破壊する。既存の単発運用（外部スケジューラからの都度起動）が突然常駐動作に変わる重大な非互換変更になる |
| 6 | Loop WiringとDaemon化を同時に行う | Small Release / Foundation Firstに反する。Release肥大化・レビュー困難化を招く |
| 7 | 例外発生後も自動継続する | fail-fast方針からの転換は安全性への影響が大きく、独立したError Continuation Policyとして扱うべき |
| 8 | Loop APIを変更してSummary出力機能を追加 | 注入関数内で`format_summary()`を呼べば同じ結果を得られ、Loop APIを変更する必要がない |
| 9 | intervalをEnvironment Variable化する | 現時点で必要性が確認できていない（YAGNI） |
| 10 | 独自Signal Handlerを追加する | Windows/POSIXの挙動差・複雑性に見合う価値が本Releaseの範囲にはない。KeyboardInterrupt捕捉で当面の運用要求を満たせる |

---

## 13. トレードオフ

**利点**：`RetryRuntimeLoop`（v5.5.0）が初めて実際の消費者を持ち、2リリース分の先行投資が活用される。変更対象が`scripts/run_retry_runtime.py`の1ファイルに限定され、レビュー・検証が容易。単発実行の後方互換性を完全に維持したまま、新しい運用モード（定期実行）を追加できる。

**欠点・将来負債**：
- KeyboardInterrupt捕捉によりExit Code Policyに小さな例外（Ctrl+C時のみ0終了）が生じる。将来のExit Code Policy Refinementで正式に整理する余地がある
- `interval_seconds`のデフォルト値（60秒）は運用判断であり、実運用データに基づく調整が将来必要になる可能性がある
- 下限値を「0以下拒否」のみに留めたため、過度に短い正のinterval（例：1秒）を防げない。実運用で問題が生じた場合は別Releaseで再検討する
- サイクルごとの出力にサイクル番号・タイムスタンプがなく、長時間運用時のログ追跡性はStructured Loop Logging Foundationまで限定的

---

## 14. Known Issues

- `[KI-27]`（新規）：`scripts/run_retry_runtime.py`の無改修を前提とする既存Architecture Guard差分（3ファイル：v5.5.0テスト15・v5.6.0テスト25・v5.8.0テスト17）。git diffベースの既知差分（`[KI-3]`〜`[KI-26]`と同型）
- `[KI-28]`（新規）：`retry_runtime_loop`が本Releaseで初めて実際の消費者（`scripts/run_retry_runtime.py`）を持ったことにより、v5.5.0テスト16（「retry_runtime_loopをどこからも呼び出さない」という消費者不在の確認）が恒久的に成立しなくなった。`[KI-21]`（`retry_runtime_orchestrator`が初めて消費者を持った際の同型差分）と同じパターン

---

## 15. Technical Debt

- `interval_seconds`の下限値が「0以下拒否」のみであり、過度に短い正の値を防ぐ仕組みがない（13節）
- KeyboardInterrupt時のexit code 0という扱いが、既存の「正常終了0・例外発生時非0」という二値のExit Code Policyに小さな例外を加えている。将来のExit Code Policy Refinementで正式に整理する必要がある

---

## 16. Future Candidates

- Daemon Foundation（本Releaseが前提条件を満たす）
- Graceful Shutdown Foundation（SIGTERM対応等、本格的な停止処理）
- Loop Error Continuation Policy Foundation（例外後の継続方針）
- Structured Loop Logging Foundation（サイクル番号・タイムスタンプ・JSON出力）
- Exit Code Policy Refinement（KeyboardInterrupt時の扱いを含む正式な整理）
- Retry Enqueue Trigger側のdry_run観測性向上（v5.8.0 Technical Debt、本Releaseとは独立）
