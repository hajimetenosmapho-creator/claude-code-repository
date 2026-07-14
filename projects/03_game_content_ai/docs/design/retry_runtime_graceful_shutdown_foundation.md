# Graceful Shutdown Foundation（v6.1.0）

作成日：2026-07-14
作成者：Claude Code（Architecture Design・Documentation）／ユーザー（最終承認待ち）
状態：**Architecture Design（ドラフト・未実装）**
分類：Architecture Release（[development_workflow.md](../development_workflow.md) 6章）

> 本ドキュメントはArchitecture Designのみを対象とする。実装・テストは本ドキュメントのArchitecture Reviewが完了するまで開始しない。

---

## 0. 前提・分類根拠

### 0.1 現在のRuntime構成

```
CLI（scripts/run_retry_runtime.py）
    → RetryRuntimeLock（v6.0.0、多重起動防止）
    → RetryRuntimeLoop（v5.5.0、interval毎の繰り返し実行）
    → RetryRuntimeOrchestrator（v5.2.0／v5.3.0、1サイクルの実行順序）
    → RetryManager（retry_engine、実際のretry実行）
```

- v6.0.0設計書（[retry_runtime_lock_foundation.md](retry_runtime_lock_foundation.md) §10 Future Extension）で「Graceful Shutdown Foundation（SIGTERM相当のシグナルを受けてLoopを安全停止し、ロックを確実に解放する仕組み。本Releaseのロック機構が前提となる）」が次Release候補として明記されていた。本Releaseはこの候補に着手する。

### 0.2 Problem（現状の課題）

`RetryRuntimeLoop.run()`は以下の固定シーケンスで動く（無改修対象）。

```python
while self.should_continue_fn():
    self.run_once_fn()
    self.sleep_fn(self.interval_seconds)
```

`scripts/run_retry_runtime.py`は現在、`should_continue_fn=lambda: True`（常にTrue）を渡しており、`--loop`実行を止める手段は`loop.run()`全体を囲む`except KeyboardInterrupt`（Ctrl+C）のみである。これには2つの問題がある。

1. **Ctrl+Cがサイクル途中を中断しうる**：Pythonのデフォルト動作では、SIGINT受信時に次のbytecode境界で非同期に`KeyboardInterrupt`が送出される。これは`run_once_fn()`（＝`RetryRuntimeOrchestrator.run_once()`の実行中）の途中で発生しうるため、「Retry対象の一部だけ処理された状態」でプロセスが中断される可能性がある。これは「Graceful」ではない。
2. **Ctrl+C以外に停止手段がない**：バックグラウンド実行（`--loop`をコンソールから切り離して実行する運用や、将来のDaemon化）を見据えると、フォアグラウンドのキー入力に依存しない停止手段が必要になる。v6.0.0のRuntime Lockは「二重起動の防止」は解決したが、「安全な停止」はスコープ外としていた。

### 0.3 Goal

`--loop`実行中のRetry Runtimeに対して、シグナルによる安全な停止要求を受け付け、**実行中のサイクルは最後まで完了させたうえで、次のサイクルを開始せずに終了する**、独立した小さなFoundationを新設する。

- 対象は`--loop`実行のみとする（単発実行は対象外。理由は§6 Out of Scopeを参照）。
- 新設するコンポーネントは、Retry業務ロジック・Composition Root・Orchestrator・Loop本体のいずれにも依存しない、独立した汎用コンポーネントとする（v6.0.0の`RetryRuntimeLock`と同じ設計思想）。

### 0.4 Requirements（本Releaseに課された制約）

- Foundation First
- Zero Diff Principle
- Single Responsibility
- Composition Root（`RetryCompositionRoot`）は無改修
- `RetryManager`は無改修
- `RetryRuntimeLoop`の責務を不必要に増やさない
- 既存Runtime挙動は、Graceful Terminationに関する部分を除き変更しない

### 0.5 Fast Track Checklist該当確認

[development_workflow.md](../development_workflow.md) 7章の条件のうち、本Releaseが**満たさない**項目。

| 条件 | 該当有無 | 内容 |
|---|---|---|
| Public API変更 | なし | 既存クラスのシグネチャは無改修。新規クラスの追加のみ |
| Constructor変更 | なし | 既存クラスのConstructorは無改修 |
| Composition Root変更 | なし | `RetryCompositionRoot`は無改修（要件で明示） |
| **Layer変更** | **あり** | 新規パッケージ`src/retry_runtime_shutdown/`を新設する |
| Dependency変更 | なし | 標準ライブラリ（`signal`／`time`）のみで実装し、新規外部パッケージは追加しない |
| 永続化変更 | なし | ファイル等の新しい永続化アーティファクトは発生しない |
| Event変更 | なし | 該当なし |
| 外部I/O変更 | なし | 該当なし |

Layer変更に該当するため、Architecture Releaseに分類する。

---

## 1. Architecture Overview

### 1.1 設計方針

既存の`RetryRuntimeLoop`は、以下2つの外部から注入可能な関数（DIシーム）を**既に**持っている。

```python
RetryRuntimeLoop(
    run_once_fn: Callable[[], object],
    sleep_fn: Callable[[float], None],
    should_continue_fn: Callable[[], bool],
    interval_seconds: float,
)
```

本Releaseは、この2つのシーム（`should_continue_fn`と`sleep_fn`）だけを使って停止制御を実現する。**`RetryRuntimeLoop`自体には一切手を加えない**（Zero Diff）。

新設する`RetryRuntimeShutdown`（新規パッケージ`src/retry_runtime_shutdown/`）は、

- OSシグナル（Ctrl+C／Ctrl+Break等）を受け取り、内部フラグを立てるだけの薄いコンポーネント
- `should_continue_fn`として渡せる`should_continue()`メソッド（フラグの否定を返すだけ）
- `sleep_fn`として渡せる`interruptible_sleep()`メソッド（短い間隔でフラグを確認しながら待機し、フラグが立ったら即座に返る）

の2つを提供する。これにより、

- シグナル受信時に**実行中の`run_once_fn()`を中断しない**（ハンドラは例外を送出せず、フラグを立てるだけ）→「サイクル途中で打ち切らない」というGraceful性を実現
- シグナル受信後、**待機（`sleep_fn`）を最大`interval_seconds`ではなくポーリング間隔（既定0.5秒）以内で打ち切る**→「シグナル後、次サイクルを開始せず速やかに終了する」を実現

という2つの要求を、`RetryRuntimeLoop`本体を一切変更せずに満たす。

### 1.2 DIのみによる接続（Architecture Review反映事項3）

**`RetryRuntimeLoop`は`RetryRuntimeShutdown`の存在を一切知らない。`RetryRuntimeShutdown`も`RetryRuntimeLoop`の存在を一切知らない。** 両者は`import`関係を一切持たず、`scripts/run_retry_runtime.py`が`RetryRuntimeLoop`のConstructorへ`should_continue_fn=shutdown.should_continue` / `sleep_fn=shutdown.interruptible_sleep`という2つの関数参照を渡すDI（Dependency Injection）のみで接続される。

- `RetryRuntimeLoop`から見れば、渡された`should_continue_fn`／`sleep_fn`が`RetryRuntimeShutdown`由来であることに一切依存しない。v6.0.0以前と同じく、任意の`Callable[[], bool]` / `Callable[[float], None]`を受け取れる汎用Wrapperのままである
- `RetryRuntimeShutdown`から見れば、自分のメソッドが`RetryRuntimeLoop`へ渡されることを一切前提としない。`should_continue()` / `interruptible_sleep()`は単体でも呼び出し可能な独立したメソッドである
- この関係は、v6.0.0の`RetryRuntimeLock`が`scripts/run_retry_runtime.py`の`with lock:`を通じてのみ既存フローと接続され、`RetryCompositionRoot`等を一切知らないのと同じ設計パターンである

### 1.3 Shutdown State（Architecture Review反映事項1）

概念上の状態遷移は以下の3状態として整理する。

```
RUNNING
   │  （シグナル受信）
   ▼
SHUTDOWN_REQUESTED
   │  （実行中サイクルの完了 → sleep_fnの早期終了 → should_continue_fn()がFalse）
   ▼
STOPPED
```

- **RUNNING**：`install()`後、シグナル未受信の通常状態。`requested = False`
- **SHUTDOWN_REQUESTED**：シグナル受信後、`RetryRuntimeLoop.run()`がまだreturnしていない状態。`requested = True`。実行中の`run_once_fn()`があれば中断せず完了させる
- **STOPPED**：`RetryRuntimeLoop.run()`が正常returnした状態。この状態自体は`RetryRuntimeShutdown`が持つのではなく、`scripts/run_retry_runtime.py`側で`loop.run()`呼び出しがreturnした後、`shutdown.requested`を見て判定する（`RetryRuntimeShutdown`はRUNNING/SHUTDOWN_REQUESTEDの2値のみを内部状態として持つ）

**実装は状態遷移の列挙型・状態機械クラスを新設せず、`RUNNING`＝`_requested is False`、`SHUTDOWN_REQUESTED`＝`_requested is True`というbool 1個のみで表現する。** STOPPEDは`RetryRuntimeShutdown`の外側（`RetryRuntimeLoop.run()`の呼び出し元）で判定される状態であり、`RetryRuntimeShutdown`自身の状態には含まれない。3状態の名称はあくまで設計上の説明・ドキュメント目的であり、コード上に対応するEnum等は導入しない（Foundation First、YAGNI）。

### 1.4 Architecture図

```
CLI → argparse（既存、無変更）
    → RetryRuntimeLock(lock_path).acquire()（v6.0.0、既存）
         → [--loop の場合のみ] RetryRuntimeShutdown().install()
              → RetryCompositionRoot.from_env()（無改修）
              → RetryRuntimeOrchestrator.from_composition_root()（無改修）
              → RetryRuntimeLoop(
                    run_once_fn=run_cycle,
                    sleep_fn=shutdown.interruptible_sleep,   ← 差し替え
                    should_continue_fn=shutdown.should_continue, ← 差し替え
                    interval_seconds=interval_seconds,
                 ).run()（RetryRuntimeLoop自体は無改修）
              → シグナル受信 → 実行中サイクルは完了 → 待機を早期終了
              → should_continue_fn() が False → loop.run() が正常return
              → shutdown.requested を見て終了メッセージ表示
         → lock.release()（with文により保証、既存のまま）
    → exit code 0
```

単発実行（`--loop`なし）の経路は本Releaseによる変更を一切受けない（§6 Out of Scope）。

---

## 2. Component Responsibilities

| コンポーネント | 責務 | 変更有無 |
|---|---|---|
| `RetryRuntimeShutdown`（新規） | シグナルの受信検知（フラグ管理）と、`should_continue_fn`／`sleep_fn`として利用可能な2つのメソッドの提供のみ。Retryドメイン・実行順序・ループ構造は一切関知しない | 新規追加 |
| `scripts/run_retry_runtime.py` | `--loop`時のみ`RetryRuntimeShutdown`を生成し、`RetryRuntimeLoop`への引数を差し替える配線のみ追加。シグナル処理の内部実装は持ち込まない | 変更（配線のみ、1ファイル） |
| `RetryRuntimeLoop` | 無変更。既存の`should_continue_fn`／`sleep_fn`という汎用インターフェースがそのまま利用される | 無改修 |
| `RetryRuntimeOrchestrator` / `RetryManager` / `RetryCompositionRoot` | 無変更 | 無改修 |
| `RetryRuntimeLock`（v6.0.0） | 無変更。本Releaseはこれを前提として利用するのみ（v6.0.0設計書§10で予告済みの関係） | 無改修 |

`RetryRuntimeShutdown`は「Retryドメインを一切知らない、汎用的な停止シグナル検知コンポーネント」として、v6.0.0の`RetryRuntimeLock`（「Retryドメインを一切知らない、汎用的な排他制御コンポーネント」）と対になる設計思想を踏襲する。

### 2.1 Signal Registration と Signal Handling の責務分離（Architecture Review反映事項2）

`RetryRuntimeShutdown`内部でも、以下2つの責務をメソッド単位で明確に分離する（クラスやモジュールを分けるほどの規模ではないため、Single Responsibilityはメソッド粒度で担保する）。

| 責務 | 該当メソッド | 内容 |
|---|---|---|
| **Signal Registration**（登録） | `install()` / `uninstall()` | プラットフォームで利用可能なシグナルへハンドラを登録・復元するのみ。「どのシグナルが送られてきたか」の解釈や、フラグの意味づけには関与しない |
| **Signal Handling**（受信時処理） | `_handle()` | シグナル受信時にフラグを立てる（`_requested = True`）のみ。I/O（`print()`等）は一切行わない。登録・復元の手続きには関与しない |

この分離により、「シグナルをどう登録するか（プラットフォーム依存の関心事）」と「シグナルを受けて何をするか（フラグを立てるだけという単純な関心事）」が互いに独立して変更・テスト可能になる。将来、対応シグナルの一覧（`install()`側）を拡張する場合でも、`_handle()`の実装（1行）には影響しない。

---

## 3. Runtime Flow

### 3.1 正常系（シグナルなし、`--loop`）

```
1. main() 開始、RetryRuntimeLock.acquire() 成功
2. RetryRuntimeShutdown().install()（SIGINT等のハンドラ登録）
3. RetryCompositionRoot.from_env() → RetryRuntimeOrchestrator 構築
4. RetryRuntimeLoop(...).run() 開始
   while shutdown.should_continue():   # True
       run_cycle()                      # 通常どおり実行
       shutdown.interruptible_sleep(interval_seconds)  # 通常はinterval_seconds待機
5. （ユーザーが自然終了させない限り）3〜4を継続
```

### 3.2 シグナル受信（サイクル実行中に受信）

```
1. run_once_fn() 実行中に SIGINT/SIGBREAK 受信
2. ハンドラが shutdown._requested = True を設定（例外は送出しない）
3. run_once_fn() はそのまま最後まで実行を継続（中断されない）
4. run_once_fn() 完了
5. interruptible_sleep(interval_seconds) 呼び出し
   → 内部ループの最初のポーリングで requested=True を検知 → ほぼ即座にreturn
6. while shutdown.should_continue(): が False → loop.run() が正常return
7. main() が shutdown.requested を見て終了メッセージを表示
8. with lock: のスコープを抜け、lock.release()（既存のまま保証）
9. 正常終了（exit code 0）
```

### 3.3 シグナル受信（待機中に受信）

```
1. interruptible_sleep() のポーリング待機中に SIGINT/SIGBREAK 受信
2. ハンドラが requested=True を設定
3. 次のポーリングチェック（既定0.5秒以内）で requested=True を検知 → 即座にreturn
4. while shutdown.should_continue(): が False → loop.run() が正常return
5〜6. §3.2と同じ（終了メッセージ → lock解放 → exit code 0）
```

### 3.4 単発実行（`--loop`なし）

`RetryRuntimeShutdown`は生成・`install()`されない。既存どおり、シグナルに対する特別な処理は行わない（Python標準の挙動のまま。§6 Out of Scope）。

---

## 4. API Design

```python
# src/retry_runtime_shutdown/retry_runtime_shutdown.py
from __future__ import annotations

import signal
import time


class RetryRuntimeShutdown:
    """
    停止シグナルの受信検知と、RetryRuntimeLoopへ渡すための
    should_continue_fn / sleep_fn の提供のみを行う、Retryドメインを
    一切知らない汎用コンポーネント。
    """

    def __init__(self, poll_interval_seconds: float = 0.5):
        self._requested = False
        self._signal_name: str | None = None
        self._poll_interval_seconds = poll_interval_seconds
        self._previous_handlers: dict[int, object] = {}

    def install(self) -> None:
        """
        プラットフォームで利用可能な停止シグナル（SIGINT、及び対応する
        場合はSIGBREAK／SIGTERM）にハンドラを登録する。

        個々のシグナルが登録できない場合（プラットフォーム非対応等）は
        そのシグナルの登録のみスキップし、他のシグナルの登録は継続する
        （ベストエフォート。全滅した場合でも例外は送出しない）。
        """
        ...

    def uninstall(self) -> None:
        """
        install() 前のシグナルハンドラへ復元する。主にテストでの
        グローバル状態リークを防ぐために使用する。
        """
        ...

    @property
    def requested(self) -> bool:
        """停止要求を受信済みかどうか。"""
        return self._requested

    @property
    def signal_name(self) -> str | None:
        """受信したシグナル名（未受信の場合はNone）。終了メッセージ表示用。"""
        return self._signal_name

    def should_continue(self) -> bool:
        """RetryRuntimeLoopのshould_continue_fnとしてそのまま渡す。"""
        return not self._requested

    def interruptible_sleep(self, seconds: float) -> None:
        """
        RetryRuntimeLoopのsleep_fnとしてそのまま渡す。poll_interval_seconds
        単位でrequestedを確認しながら待機し、requestedがTrueになった時点で
        残り時間を待たずに即座にreturnする。requestedが立たない場合の
        合計待機時間はseconds（time.sleepとほぼ同一、ポーリング粒度分の
        誤差を除く）。
        """
        ...
```

`scripts/run_retry_runtime.py`側の変更イメージ（配線のみ、詳細は実装時にArchitecture Reviewで確定）：

```python
shutdown = RetryRuntimeShutdown()

lock = RetryRuntimeLock(lock_path=_PROJECT_ROOT / ".run" / "retry_runtime.lock")
try:
    with lock:
        ...
        root = RetryCompositionRoot.from_env()
        orchestrator = RetryRuntimeOrchestrator.from_composition_root(root)

        def run_cycle():
            ...

        if not args.loop:
            run_cycle()
            return

        shutdown.install()
        loop = RetryRuntimeLoop(
            run_once_fn=run_cycle,
            sleep_fn=shutdown.interruptible_sleep,
            should_continue_fn=shutdown.should_continue,
            interval_seconds=interval_seconds,
        )
        loop.run()
        if shutdown.requested:
            print(f"Retry runtime loop stopped by signal ({shutdown.signal_name}).")
except RetryRuntimeLockError as e:
    print(f"[ERROR] {e}")
    sys.exit(1)
```

既存の`except KeyboardInterrupt`（`loop.run()`を囲む）は**削除せず残す**（§7 Alternatives Considered 4番を参照。SIGINTハンドラが正しく`install()`されなかった場合等のフェイルセーフとして機能する）。

---

## 5. Failure Handling

- シグナルハンドラ自体はI/Oを行わず、フラグ設定のみを行う（再入・シグナルセーフ性への配慮。終了メッセージの表示は`main()`側で`loop.run()`のreturn後に行う）。
- `install()`は個々のシグナル登録の失敗（プラットフォーム非対応等）に対してベストエフォートとし、例外を送出しない。1つも登録できなかった場合でも、既存の`except KeyboardInterrupt`が引き続きフォールバックとして機能する。
- Exit Code Policyは既存方針を維持する：シグナルによるGraceful Shutdownも「意図的な正常停止」として扱い、exit code 0とする（v5.9.0で確立した「Ctrl+Cはexit code 0」という方針の拡張）。
- ロック解放は本Releaseの変更範囲外であり、既存の`with lock:`機構（v6.0.0）がそのまま保証する。
- 実行中サイクル（`run_once_fn()`内の`RetryRuntimeOrchestrator.run_once()`）自体の例外処理方針は無変更。シグナル受信はサイクルの実行結果・例外伝播に一切影響を与えない。

---

## 6. Out of Scope

- 単発実行（`--loop`なし）時のシグナル処理（既存どおり、Python標準のKeyboardInterrupt伝播のまま。対応する場合は将来Release）
- 二重シグナル（例：Ctrl+Cを2回押す）による強制即時終了のエスケープハッチ
- `RetryRuntimeOrchestrator.run_once()` / `RetryManager`内部での協調的キャンセル（サイクル途中でのキャンセル）
- 実際のバックグラウンド分離（detach）／Windows Service化／実Daemon化（v6.0.0設計書§10 Future Extensionの範囲のまま）
- `taskkill /F`・タスクマネージャーの「タスクの終了」・強制的なプロセスKillの検知（原理的に不可能。§8 Known Risks参照）
- Stale Lock Recovery（v6.0.0から持ち越しのFuture Extension、本Releaseでは対応しない）
- シグナル受信・停止処理の構造化ログ出力（既存の`print()`ベースの方式を踏襲）
- 複数マシン・複数プロセスにまたがる協調停止
- 実行中サイクルのタイムアウト強制終了（監視スレッドによる「N秒経過したら強制終了」等）
- `RetryRuntimeLoop` / `RetryRuntimeOrchestrator` / `RetryManager` / `RetryCompositionRoot` / `RetryRuntimeLock`の変更

---

## 7. Alternatives Considered

| # | 案 | 却下理由 |
|---|---|---|
| 1 | `RetryRuntimeLoop`自体に停止チェック機構（`run_once_fn`と`sleep_fn`の間のチェック等）を追加する | 要件「RetryRuntimeLoopの責務を不必要に増やさない」に反する。既存のDIシーム（`should_continue_fn`／`sleep_fn`）だけで同等のことが実現できるため不要 |
| 2 | `time.sleep`をそのまま使い、`should_continue_fn`のみ差し替える（`interruptible_sleep`を導入しない） | シグナル受信から実際のプロセス終了まで最大`interval_seconds`（デフォルト60秒、長い運用では数千秒）待たされ、「Graceful」の名に反する応答性の悪さが残る |
| 3 | `signal.signal()`ではなく`threading.Event` + 監視用バックグラウンドスレッドで停止検知する | 現在シングルスレッド・同期実行のRuntimeに新しい並行性モデルを持ち込むことになり複雑化する。標準ライブラリの`signal`のみで同等の効果が得られ、v6.0.0（標準ライブラリのみで実装）の方針とも整合する |
| 4 | SIGINTは既存の`except KeyboardInterrupt`に任せたままとし、新規シグナル（SIGTERM／SIGBREAK）のみ本Foundationで扱う（より保守的・小さい差分） | 検討したが不採用。SIGINT（Ctrl+C）こそが「サイクル途中で中断されうる」という本Releaseが解決すべき本来の課題（§0.2）であり、これを対象外にすると本Foundationの主目的（Graceful Termination）が達成できない。ただし差分の大きさを懸念する場合の保守的な代替案として記録する（Architecture Reviewでの論点） |
| 5 | `RetryRuntimeOrchestrator.run_once()`にキャンセルトークンを渡し、サイクル途中でも中断可能にする | 「RetryManagerは無改修」「Composition Rootは無改修」という明示要件に反する。Foundation Firstの原則からも範囲過大 |
| 6 | 停止シグナル処理をCLIオプション（例：`--enable-graceful-shutdown`）で任意化する | v6.0.0の却下案4（ロックの任意化）と同じ理由で却下。安全な停止は「常に有効であるべき」性質のものであり、`--loop`使用時は無条件に有効とする |

---

## 8. Known Risks

- **Windows環境での強制終了は検知不可能（最重要）**：本プロジェクトの実行環境はWindows。`taskkill /F`やタスクマネージャーの「タスクの終了」はOSの`TerminateProcess` APIを直接呼び出すため、いかなるプロセスもこれを検知・介入することは原理的にできない。さらにPython公式ドキュメントの記載どおり、Windowsで`os.kill(pid, signal.SIGTERM)`を**他プロセスから**呼び出した場合も同様に`TerminateProcess`相当の強制終了となり、対象プロセス内で`signal.signal(signal.SIGTERM, ...)`により登録したハンドラは呼び出されない。したがって本Foundationが確実に検知できるのは、フォアグラウンドのCtrl+C（SIGINT）・Ctrl+Break（SIGBREAK）、および同一プロセス内から`signal.raise_signal()`等で自発的に送出されたシグナルに限られる。SIGTERMハンドラの登録自体はPOSIX環境への移植性のために行うが、Windows運用における実質的な効果は限定的である。
- **タスクスケジューラからの停止操作の挙動が未検証**：Windows タスクスケジューラの「タスクの終了」操作がSIGINT／SIGBREAK相当のイベントとして本プロセスへ届くかどうかは、タスクの起動設定（コンソールの有無等）に依存し、本ドキュメント作成時点では未検証。実装・テスト時に実機で確認する必要がある。
- **CTRL_CLOSE_EVENT等の扱いはCPython実装依存**：CPythonはWindowsのコンソール制御イベント（`CTRL_CLOSE_EVENT`／`CTRL_LOGOFF_EVENT`／`CTRL_SHUTDOWN_EVENT`）を内部的にSIGBREAKハンドラへ委譲する実装になっている可能性があるが、これはPythonバージョン依存の実装詳細であり、本Releaseでは仕様として保証しない。実装時に動作検証のうえ、ドキュメント（docstring）へ実測結果を記録する。
- **二重Ctrl+Cへの応答性**：実行中サイクルが長時間かかる場合（Retry対象が多い等）、シグナル受信後もそのサイクルが完了するまでプロセスは終了しない。強制終了のエスケープハッチがない（§6 Out of Scope）ため、ユーザーが連打しても効果はない。
- **`interruptible_sleep`のタイミング誤差**：ポーリング間隔（既定0.5秒）単位での確認になるため、シグナルが発生しない通常時でも、厳密な`time.sleep(interval_seconds)`との間に最大でポーリング間隔未満の誤差が生じる。Retry Runtimeの用途上、実害はないと判断する。
- **シグナルハンドラのグローバル状態**：`signal.signal()`はプロセス全体に対するグローバルな登録である。E2Eテストで`install()`を呼ぶ場合、`uninstall()`による確実な復元、またはサブプロセスでの実行分離が必要になる（テスト設計は実装時に確定）。
- **メインスレッド制約**：`signal.signal()`はメインスレッドからのみ呼び出し可能というPythonの制約がある。現状のRuntimeはシングルスレッド実行のため問題ないが、将来マルチスレッド化する場合は再設計が必要になる。

---

## 9. Technical Debt

- Stale Lock Recovery Foundation（v6.0.0から持ち越し）は本Releaseでも引き続き未着手。本Releaseにより「シグナルによる正常終了」経路でのstale lock発生率は改善される（プロセスが確実に`with lock:`のスコープを抜けるため）が、強制終了（`taskkill /F`）経路のstale lockリスクは変わらず残る。
- 単発実行時の割り込み処理は本Releaseでも対象外のままであり、「未捕捉KeyboardInterruptが非0終了する」という既存挙動が残る。Loop実行と単発実行とで停止時の挙動が非対称になる点は、将来的な一貫性向上の余地として記録する。
- 二重シグナルによる強制終了エスケープハッチの欠如は、運用上の要望が実際に出た場合にFuture Extensionとして検討する。
- Windows タスクスケジューラからの実際の停止操作がどのイベントとして届くかの検証結果は、実装・テストフェーズで得られ次第、本設計書または`scripts/run_retry_runtime.py`のdocstringへ追記する（現時点では未検証というリスクを許容してArchitecture Releaseを進める判断）。

---

## 10. Recommendation

- 新規独立パッケージ`src/retry_runtime_shutdown/`（`RetryRuntimeShutdown`）を新設し、`scripts/run_retry_runtime.py`の`--loop`分岐にのみ配線する本設計を推奨する。`RetryRuntimeLoop`が既に持つ2つのDIシーム（`should_continue_fn`／`sleep_fn`）だけで実現できるため、要件（Foundation First／Zero Diff／Single Responsibility／Composition Root無改修／RetryManager無改修／RetryRuntimeLoop責務不増加）をすべて満たしながら、「シグナル受信後、実行中サイクルは完了させ、次サイクルは開始せず速やかに終了する」という真の意味でのGraceful Terminationを実現できる。
- 唯一のOpen Questionは§7の代替案4（SIGINTを新機構に統合するか、既存の`except KeyboardInterrupt`に残すか）である。統合する案（本ドキュメントの採用案）はより小さな差分ではないが、本Releaseの目的（サイクル途中で中断させない）を達成するには統合が必須と考える。Architecture Reviewでこの判断の妥当性を確認してほしい。
- Windows環境における強制終了（`taskkill /F`等）が検知不可能であることは、実装より前に必ず人間・ChatGPTの双方に明確に伝え、期待値をすり合わせるべき最重要事項として位置づける（本Foundationは「Graceful」の名の通り、あくまで協調的な停止要求への対応であり、強制終了への対処ではない）。

---

## Status

- [x] ドラフト作成
- [x] ChatGPT Architecture Review（Approved。推奨事項3件を§1.2〜§2.1へ反映）
- [x] 人間の独立した実装承認
- [x] 実装着手（`src/retry_runtime_shutdown/`新設、`scripts/run_retry_runtime.py`配線）
- [x] Code Review（セルフレビュー。Known Issue `[KI-29]`を発見・記録）
- [x] Test Review（新規E2E 44/44 PASS。既存回帰：v5.5.0 35/37・v5.6.0 44/49・v5.7.0 86/86・
      v5.8.0 63/64（いずれも既存差分の範囲内、件数不変）。v5.9.0は実行不能・v6.0.0はテスト13以降
      実行不能（`[KI-29]`、新規Known Issue）
- [ ] Release Review
- [ ] commit／push
