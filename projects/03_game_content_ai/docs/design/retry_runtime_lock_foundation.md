# Daemon Foundation — Retry Runtime Lock Foundation（v6.0.0）

作成日：2026-07-14
作成者：Claude Code（Architecture Design・Documentation）／ユーザー（最終承認待ち）
状態：**Architecture Design（ドラフト・未実装）**
分類：Architecture Release（[development_workflow.md](../development_workflow.md) 6章）

> 本ドキュメントはArchitecture Designのみを対象とする。実装・テストは本ドキュメントのArchitecture Reviewが完了するまで開始しない。

---

## 1. Background

- v5.9.0（Retry Runtime Loop Wiring Foundation）で`scripts/run_retry_runtime.py`に`--loop`/`--interval-seconds`を追加し、`RetryRuntimeLoop`（v5.5.0）を用いた繰り返し実行が可能になった。
- v5.9.0のdocstring・設計書は「`--loop`使用時、同じRetry RuntimeをWindows タスクスケジューラ等の外部スケジューラから重複して定期起動しないこと」と明記した上で、**Runtime Lock・PID Lock等の二重起動防止機構を明示的にOut of Scope**としていた。
- v5.9.0設計書 §16 Future Candidatesの筆頭に「**Daemon Foundation（本Releaseが前提条件を満たす）**」と記載されており、本Releaseはユーザーの選択により、この候補に着手する。
- 「Daemon化」という言葉は範囲が広く、過去の設計書では「バックグラウンド分離（detach）」「Windows Service化」「Graceful Shutdown（SIGTERM対応）」まで一括りに扱われてきた。Foundation Firstの原則に従い、本Releaseはこれらすべてを一度に実現するのではなく、**それらすべての前提となる最小単位（多重起動防止）のみ**を対象とする。
- **本Foundationと Daemon Foundation の関係**：本Foundation（Retry Runtime Lock）は、Daemon Foundationそのもの（実際のバックグラウンド常駐化・Windows Service化）ではない。いかなるDaemon化方式であっても「同一Runtimeが多重起動していないことを保証できる」ことが前提条件になるため、本Foundationは**Daemon Foundationが成立するための最小の前提Foundation**と位置づける。本Release単体でDaemon化そのものが完了するわけではなく、実際の常駐化・Service化は引き続き将来Releaseの対象（§10 Future Extension）とする。

---

## 2. Problem

現状、`scripts/run_retry_runtime.py`には以下の問題がある。

1. 同一マシン上で`run_retry_runtime.py`（単発実行・`--loop`実行のいずれも）を誤って二重に起動しても、それを検知・拒否する仕組みが存在しない。
2. 二重起動が発生した場合、2つのプロセスが同じ`RetryQueueManager`/`RetryHistoryManager`の永続化対象（Queue・History）に対して同時にEnqueue/Executeを行い、Retry対象の二重処理や記録の競合を招くおそれがある（v5.9.0設計書 §11で運用上の注意として明記されていたが、機構としての防止策はなかった）。
3. `--loop`実行中のプロセスを外部から明示的に停止する手段が、フォアグラウンドでの`Ctrl+C`（`KeyboardInterrupt`）以外に存在しない。将来的にバックグラウンド実行（Daemon化）を検討する際、まず「今このRuntimeが動いているか」を確認できる状態がなければ、安全な停止制御も設計できない。

Daemon化・常駐化・Graceful Shutdownはいずれも「今、他に同じRuntimeが動いていないこと（あるいは動いていること）を確実に判定できる」ことを前提とする。この前提が現状満たされていない。

---

## 3. Goal

`scripts/run_retry_runtime.py`の実行開始時に、**同一Retry Runtimeの多重起動を検知し、既に実行中であれば安全に起動を拒否する**、独立した小さなFoundation（Runtime Lock）を新設する。

- 単発実行・`--loop`実行の両方に適用する（単発実行の多重起動もProblem 2の対象であるため）。
- 新設するコンポーネントは、Retry業務ロジック・Composition Root・Orchestrator・Loopのいずれにも依存しない、独立した汎用コンポーネントとする。
- 既存コンポーネント（`RetryCompositionRoot`／`RetryRuntimeOrchestrator`／`RetryRuntimeLoop`／`RetryManager`等）は無改修とする（Zero Diff Principle）。
- デフォルト動作（コマンドライン引数）は変更しない。ロック機構は新しいCLI引数を必要とせず、常に有効とする（多重起動防止は「オプトインで有効化する機能」ではなく「常に守られるべき安全性」であるため）。

### 成立させないこと（Non-Goal）

実際のバックグラウンド分離（detach）／Windows Service化／Graceful Shutdown（SIGTERM対応）／自動再起動／Process Supervision／stale lockの自動検出・自動復旧／Structured Logging。これらは§10 Future Extensionへ申し送る。

### Architecture Release分類根拠

[development_workflow.md](../development_workflow.md) 7章のFast Track該当条件（8項目）のうち、本Releaseは以下に該当するため、Architecture Releaseに分類する。

| 条件 | 該当有無 | 内容 |
|---|---|---|
| Layer変更 | **あり** | 新規パッケージ`src/retry_runtime_lock/`を新設する |
| Public API変更 | なし | 既存クラスのシグネチャは無改修。新規クラスの追加のみ |
| Constructor変更 | なし | 既存クラスのConstructorは無改修 |
| Composition Root変更 | なし | `RetryCompositionRoot`は無改修（後述） |
| Dependency変更 | なし | 標準ライブラリのみで実装し、新規外部パッケージは追加しない |
| 永続化変更 | **あり（小）** | ロックファイル（1ファイル）という新しい永続化アーティファクトが増える |
| Event変更 | なし | 該当なし |
| 外部I/O変更 | なし | ファイルI/Oのみで、外部サービス通信は発生しない |

---

## 4. Architecture

### 4.1 配置・命名

新規パッケージ：`src/retry_runtime_lock/`

- クラス名：`RetryRuntimeLock`（既存の`Retry*`命名規則に合わせる）
- 例外名：`RetryRuntimeLockError`（既存パッケージの例外命名規則に合わせる想定。既存コードでの命名規則は実装時にArchitecture Reviewで最終確認する）

既存の`retry_runtime_loop`パッケージが「Stateless・Business Logicなし」の薄いラッパーであるのと同じ設計思想を踏襲し、`retry_runtime_lock`も**Retryドメインを一切知らない、汎用的な排他制御コンポーネント**として設計する。

### 4.2 採用案

- ロックの実体は、固定パスのロックファイル1つ（例：`<project_root>/.run/retry_runtime.lock`）とする。
- ロック取得（`acquire()`）は、OSのアトミックな排他生成（`os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)`相当）を用いる。ファイルが既に存在する場合は生成に失敗し、「既に別プロセスが実行中」とみなして`RetryRuntimeLockError`を送出する。
- ロック取得に成功した場合、診断用に自プロセスのPIDをファイルへ書き込む（後述の通り、本Releaseではこの値をstaleness判定には使わない。あくまで運用者が`cat`/`type`でロック保持者を確認するための情報）。
- ロック解放（`release()`）は、ロックファイルの削除のみ。`try/finally`で正常終了・異常終了（`KeyboardInterrupt`含む）の両方で確実に解放されるようにする。
- `RetryRuntimeLock`は`with`文で使えるコンテキストマネージャとして実装し（`__enter__`で`acquire()`、`__exit__`で`release()`）、`scripts/run_retry_runtime.py`側の変更を最小化する。
- `scripts/run_retry_runtime.py`の`main()`内で、既存の実行ロジック（単発実行・Loop実行の両方）全体を`with lock:`で包む。`RetryCompositionRoot.from_env()`より前にロックを取得することで、ロック取得に失敗した場合は既存コンポーネントを一切構築しない。

### 4.3 却下案

| # | 案 | 却下理由 |
|---|---|---|
| 1 | `RetryCompositionRoot`にロックを組み込む | Composition Rootの責務（組み立てのみ）を超え、Execution前提条件の検証という別の関心事を持ち込むことになる。Composition Root維持（Zero Diff）に反する |
| 2 | PIDの生存確認（プロセスが実際に生きているか）まで実装し、stale lockを自動解除する | Windows/POSIXでプロセス生存確認の実装が異なり複雑化する。Foundation Firstの原則上、まず「ロックの存在有無による排他」のみを確立し、stale lock対応は独立したFuture Extensionとする |
| 3 | OSファイルロック（`fcntl`／`msvcrt.locking`）をプロセス生存期間中保持し続ける方式 | クロスプラットフォームで実装が分岐し複雑になる。ファイル存在ベースの方式より初期実装のリスクが高く、Foundation規模を超える |
| 4 | `--enable-lock`のようなCLIフラグでロックを任意化する | 多重起動防止は安全性の基本であり、任意で無効化できる機能にすべきではない。既存の`--dry-run`等とは性質が異なる |
| 5 | ロック機構と同時にGraceful Shutdown（SIGTERM対応）も実装する | Small Release／Foundation Firstに反する。v5.9.0の却下案6（Loop WiringとDaemon化の同時実施を却下）と同じ理由 |
| 6 | ロックパスを環境変数で設定可能にする | 現時点で複数環境・複数インスタンスを同一マシンで並行運用する要件が確認できていない（YAGNI） |

### 4.4 Architecture図

```
CLI → argparse（既存、無変更）
    → RetryRuntimeLock(lock_path).acquire()
         ├─ [成功] → RetryCompositionRoot.from_env()
         │              → RetryRuntimeOrchestrator.from_composition_root()
         │              → （単発）run_cycle() 1回
         │                （--loop）RetryRuntimeLoop(...).run()
         │              → 正常終了 or KeyboardInterrupt
         │              → lock.release()（finally、既存の"with"機構により保証）
         │
         └─ [失敗：既に別プロセスが実行中] → RetryRuntimeLockError
                → エラーメッセージ表示 → 非0終了（Composition Root等は一切構築されない）
```

---

## 5. Responsibility

| コンポーネント | 責務 | 変更有無 |
|---|---|---|
| `RetryRuntimeLock`（新規） | ロックファイルの取得・解放のみ。Retryドメイン・実行順序・ループ・スケジューリングは一切関知しない | 新規追加 |
| `scripts/run_retry_runtime.py` | 既存の実行フロー全体を`with lock:`で包む配線のみ追加。ロックの内部実装（ファイルI/O）は持ち込まない | 変更（配線のみ、1ファイル） |
| `RetryCompositionRoot` | 無変更。ロックの組み立て・保持を行わない | 無改修 |
| `RetryRuntimeOrchestrator` / `RetryRuntimeLoop` / `RetryManager` 等既存クラス | 無変更 | 無改修 |

---

## 6. Dependency

- 新規の外部パッケージ依存は追加しない。標準ライブラリ（`os`, `pathlib`）のみで実装する。
- `requirements.txt`等の変更は発生しない。
- `retry_runtime_lock`パッケージは他の`retry_*`パッケージに一切依存しない（単方向：`scripts/run_retry_runtime.py`が`retry_runtime_lock`をimportするのみ）。

---

## 7. Sequence

### 正常系（単発実行・ロック未保持）

```
1. main() 開始
2. RetryRuntimeLock(lock_path).acquire() 成功（ロックファイル新規作成）
3. RetryCompositionRoot.from_env()
4. RetryRuntimeOrchestrator.from_composition_root()
5. run_cycle() 実行 → format_summary() 出力
6. lock.release()（ロックファイル削除）
7. 正常終了（exit code 0）
```

### 正常系（--loop・ロック未保持）

```
1〜4. 同上
5. RetryRuntimeLoop(...).run() 開始（サイクル毎にrun_cycle()を実行）
6-a. KeyboardInterrupt受信 → 既存の"Retry runtime loop stopped."表示 → lock.release() → exit code 0
6-b. 未処理例外発生 → lock.release()（finallyで保証） → 例外伝播 → 非0終了
```

### 異常系（ロック取得失敗＝多重起動検知）

```
1. main() 開始
2. RetryRuntimeLock(lock_path).acquire() 失敗（ロックファイルが既に存在）
3. RetryRuntimeLockError送出
4. RetryCompositionRoot等は一切構築されない
5. main()側でエラーメッセージを表示（例："別のRetry Runtimeプロセスが既に実行中です"）
6. 非0終了
```

---

## 8. Public API

```python
# src/retry_runtime_lock/retry_runtime_lock.py

class RetryRuntimeLockError(Exception):
    """
    ロック取得に失敗した場合（＝既に別プロセスが実行中）に送出される例外。

    メッセージにはロックファイルのパスと対処方法を含め、main()側が
    そのまま表示するだけで運用者向けの分かりやすいエラーメッセージに
    なるようにする（例：「既に別のRetry Runtimeプロセスが実行中です
    （lock file: <path>）。二重起動でない場合は、対象プロセスが異常終了
    していないか確認した上で、このロックファイルを手動削除してください。」）。
    """


class RetryRuntimeLock:
    def __init__(self, lock_path: Path):
        ...

    def acquire(self) -> None:
        """
        ロックファイルをアトミックに新規作成する。
        既にロックファイルが存在する場合はRetryRuntimeLockErrorを送出する。
        """
        ...

    def release(self) -> None:
        """
        ロックファイルを削除する。ロックが存在しない状態で呼び出しても
        エラーにしない（べき等）。
        """
        ...

    def __enter__(self) -> "RetryRuntimeLock":
        self.acquire()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.release()
```

`scripts/run_retry_runtime.py`側の変更イメージ（配線のみ、詳細は実装時にArchitecture Reviewで確定）：

```python
lock = RetryRuntimeLock(lock_path=project_root / ".run" / "retry_runtime.lock")
try:
    with lock:
        root = RetryCompositionRoot.from_env()
        orchestrator = RetryRuntimeOrchestrator.from_composition_root(root)
        ...（既存ロジック、無変更）
except RetryRuntimeLockError as e:
    print(f"[ERROR] {e}")
    sys.exit(1)
```

`main()`は`RetryRuntimeLockError`のみを対象とした、既存の`KeyboardInterrupt`捕捉（Loop実行時）とは別個のtry/exceptで個別に捕捉する。捕捉した例外オブジェクトのメッセージ（ロックファイルのパスと対処方法を含む）をそのまま表示し、`sys.exit(1)`により非0終了する。それ以外の例外は、このtry/exceptを一切通過せず、既存のfail-fast方針のまま伝播する。

---

## 9. Failure Handling

- ロック取得失敗（`RetryRuntimeLockError`）は、既存のfail-fast方針と整合する形で扱う。`main()`は`RetryRuntimeLockError`のみを対象とした専用のtry/exceptでこれを捕捉し（§8 Public API参照）、例外メッセージ（ロックファイルのパスと対処方法を含む）をそのまま表示した上で`sys.exit(1)`により非0終了する。例外を握りつぶすわけではなく、捕捉範囲を`RetryRuntimeLockError`のみに限定した上で、表示形式だけを整えるものであり、それ以外の例外は無関係に既存の伝播経路をそのまま通る。
- ロック取得失敗時は`RetryCompositionRoot`／`RetryRuntimeOrchestrator`が一切構築されないため、Retry業務ロジックへは到達しない（安全側に倒す設計）。
- ロック取得成功後に発生する例外（`run_cycle()`内の未処理例外等）は、`with`文の`__exit__`により**必ず**`release()`が呼ばれる。これにより、既存のfail-fast方針（例外を握りつぶさず伝播させる）とロック解放の両立を保証する。
- `KeyboardInterrupt`（Ctrl+C）についても同様に`with`文のスコープを抜ける際に`release()`が呼ばれるため、v5.9.0で確立した「Ctrl+Cはexit code 0」という方針に影響を与えない。
- 独自のExit Code体系は導入しない。ロック取得失敗も含め、既存の「正常終了0・異常終了非0」の二値方針を維持する。

---

## 10. Future Extension

- **Stale Lock Recovery Foundation**：プロセスが強制終了（`taskkill /F`・電源断等）した場合にロックファイルが残存する問題への対応（PID生存確認、または最終更新時刻に基づくタイムアウト判定）
- **Graceful Shutdown Foundation**：SIGTERM相当のシグナルを受けてLoopを安全停止し、ロックを確実に解放する仕組み（本Releaseのロック機構が前提となる）
- **Windows Service Foundation / 実Daemon化**：実際にバックグラウンドプロセスとして常駐させる仕組み（本Releaseのロック機構が前提となる）
- **他Agent系scriptへのLock機構の横展開**：`scripts/run_workflow_engine.py`等、同様の多重起動リスクを持つ他のEntry Pointへの適用
- **Lock状態の可視化**：現在ロックを保持しているPID・取得時刻等を確認するための補助コマンド（運用性向上）

---

## 11. Out of Scope

実際のバックグラウンド分離（detach）／Windows Service化／Graceful Shutdown（SIGTERM対応）／自動再起動／Process Supervision／stale lockの自動検出・自動復旧（PID生存確認・タイムアウト）／ロックパスの環境変数化／CLIフラグによるロックの任意化／複数マシン間の排他制御／他Agent系scriptへの横展開／Structured Logging／独自Exit Code体系／`RetryCompositionRoot`・`RetryRuntimeOrchestrator`・`RetryRuntimeLoop`・`RetryManager`の変更。

---

## 12. Known Risks

- **stale lockリスク**：プロセスが`release()`を経由せず終了した場合（強制終了・電源断・OSクラッシュ等）、ロックファイルが残存し、次回起動が誤ってブロックされる可能性がある。本Releaseでは自動復旧を行わないため、運用者による手動削除が必要になる。この制約は`scripts/run_retry_runtime.py`のdocstringおよびエラーメッセージに明記し、Future ExtensionのStale Lock Recovery Foundationで解消する方針とする。
- **単一ホスト内限定の排他制御**：ロックはローカルファイルシステム上のファイル存在有無のみで判定するため、共有ストレージ越しに複数マシンから同じ`project_root`を参照するような構成での多重起動までは防止できない。単一ホスト内での多重起動防止のみを保証範囲とする。
- **診断情報としてのPIDの限界**：ロックファイルに書き込むPIDは、本Releaseでは生存確認に使わず診断目的に限定する。ロックファイルの内容とプロセスの実在が乖離する可能性がある点を明示しておく必要がある。
- **常に有効という設計判断のリスク**：ロックを任意化しない設計としたため、正当な理由で意図的に多重起動したい特殊な運用（存在する場合）が今後見つかった場合、その要求は本Foundationの前提と衝突する。現時点ではそのような要求は確認されていない。

---

## 13. ロックファイルの運用方針

- ロックファイル（`<project_root>/.run/retry_runtime.lock`等）は、Retry Runtimeの実行のたびに生成・削除される**ランタイム生成物**であり、ソースコードでも設定ファイルでもない。
- ロックファイルは**Git管理対象外**とする。内容（PID等）は実行環境固有の一時情報であり、リポジトリにコミットする対象ではない。
- ロックファイルの配置ディレクトリ（`.run/`等）は、実装時に`.gitignore`へ追加する方針とする。具体的なパス・エントリ内容は実装（Code Review）時に確定する。
- この方針は、CLAUDE.mdのセキュリティルールでログファイル等の運用生成物のアップロードを禁止している既存方針と一貫させる。

---

## Status

- [x] ドラフト作成
- [x] Architecture Review（Required Changes 3件反映済み、Quick Reviewで実装着手可と判定）
- [x] 実装着手（`src/retry_runtime_lock/`新設、`scripts/run_retry_runtime.py`配線、`.gitignore`更新）
- [x] Code Review（Required Changes 2件反映済み。`os.write()`失敗時のロック解放漏れを修正、
      テストへ同時実行に関する注意書きを追記。Quick Code Reviewで Implementation Ready for Commit = Yes と判定）
- [x] Test Review（新規E2E 43件PASS。既存回帰 v5.9.0：64/64、v5.7.0：86/86、
      v5.5.0：35/37・v5.6.0：44/49・v5.8.0：63/64（いずれも既存差分`[KI-27]`等の範囲内、件数不変）PASS）
- [ ] Release Review
- [ ] commit／push
