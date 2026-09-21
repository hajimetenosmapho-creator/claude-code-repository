# Manual Recovery Diagnostic CLI Foundation — Architecture Design（Release 6.36候補）

## 0. Status

- **Status: Architecture Review完了（Codex `codex-readonly-review`（Codex High）Round 1〜5実施、Round 5で`VERDICT: APPROVED`取得。Blocking 0／Major 0。Human Gate（20章 Architecture Gate Checklist）承認待ち）**
- Round 1：`VERDICT: NOT APPROVED`（Blocking 1件・Major 4件・Minor 2件）。Blocking 1件（8章のstore_dir事前確認と`JsonSchedulerDispatchLedgerStore`構築の間のTOCTOU windowで、他プロセスがstore_dirを削除した場合、constructorの無条件`mkdir(parents=True, exist_ok=True)`がそれを再作成してしまう、という指摘）を、Round 1版ではAccepted Riskとして明記する形で反映したが、Round 2でこの対応自体がBlockingとして再指摘された。Major 4件（config bootstrap未規定／「point-in-time snapshot」の過大な表現／Invariant #35 manifestの件数誤り（19→実測20）／Zero-Diff計画の網羅性不足）とMinor 2件（`--limit`契約未規定／RECOVERY_REQUIRED付随フィールドのNone前提）は、6章・9章・10章・14章で反映した。
- **Round 2：`VERDICT: NOT APPROVED`（Blocking 1件・Major 2件・Minor 3件）。** Blocking 1件（Round 1のAccepted Risk対応そのものが、Safety Contract Cという絶対条件を「低確率」という確率的表現で緩和しており不十分、という再指摘）に対し、8章を全面改訂した：`JsonSchedulerDispatchLedgerStore`のconstructorを一切呼ばず、`mkdir`を含まないCLI専用read-only store adapter（`SchedulerDispatchLedgerStore` ABCの新規実装）へ置き換え、mkdirを呼ぶコードパス自体を構造的に排除した（Accepted Riskとしてではなく解消として扱う、19章R1・20章Gate 1・Gate 8を更新）。Major 2件（20章Gate 3に「point-in-time snapshot」という表現が残存していた／Zero-Diff計画がFormal Regression roster関連2ファイル（`tests/formal_regression_inventory.py`・`tests/test_e2e_v6_35_8_t6_formal_regression_roster_validation.py`）の要否に触れていなかった、また`test_e2e_v6_27_0`のstandalone guard定義の行番号引用が古かった）を、20章Gate 3・14章で反映した。Minor 3件（5章の記述が9章の「schema非強制」という正確な説明と矛盾していた／OQ4・Gate 6の表現が「条件付き」のままで14章の「確定的に必要」という結論と矛盾していた／test戦略（15章）がconfig bootstrap・`--limit`契約・AND filter・非None付随フィールド表示の4項目を明示的にカバーしていなかった）を、5章・6章・19章・20章・15章で反映した。
- **Round 3：`VERDICT: NOT APPROVED`（Blocking 1件・Major 1件・Minor 1件）。** Blocking 1件（Round 2版8章が「`_read_record_file()`をmodule-level関数として直接importする」と記述していたが、実際には`JsonSchedulerDispatchLedgerStore`のinstance method（`self`を取るクラス内定義）であり、module-levelでimportすることはできず、記述どおりでは実装不能、という指摘）に対し、8章を再訂正した：真にmodule-level（クラス外定義）な`_sanitize_event_identity()`・`_entry_from_dict()`の2関数**のみ**をimportし、`_read_record_file()`/`_ensure_store_dir_accessible()`相当のディレクトリ確認・列挙・個別ファイル読み取りという制御フローは、mkdirを一切含まない読み取り専用コードとして本adapter自身に新規実装する、という設計へ訂正した（parsing/schema検証/sanitizeという安全性の核心部分は引き続きimportで再利用し、複製するのは制御フローのみに限定する）。Major 1件（14章がFormal Regression roster（37件）を凍結・対象外とする一方、15章が「37ファイル＋本Release新規追加分」という矛盾した表現を残していた）を、15章を14章の結論と整合させる形で訂正した。Minor 1件（0章の「Working Tree clean」という記述が、本書自体の新規作成によるuntracked file 1件を暗黙に見落としているように読める、という指摘）を、0章へ明示的な注記を追加して反映した。
- **Round 4：`VERDICT: NOT APPROVED`（Blocking 1件・Major 2件・Minor 1件）。** Blocking 1件（Round 3改訂で8章・13章は訂正済みだったが、20章Gate 1に「`_read_record_file()`を直接import」という古い表現が残存しており、Human Gateの文言自体が非実装可能な設計を承認対象として提示していた、という指摘）を、20章Gate 1の文言を8章の最終版と一致させて解消した。Major 2件（8章がfilename/event_identityクロスチェックを「`_sanitize_event_identity()`が担う」とだけ述べ、`get()`相当・`list_all()`相当それぞれで再実装が必要な2種類の比較処理を明示していなかった——不一致entryを正常結果として受理しうる欠陥に繋がりうる／22章の「Round 4レビューを実施し、結果を本章・0章へ追記する」という文が、レビューを行うCodex自身に対する指示のように読める、という指摘）を、8章に2種類のcross-check要件を明示的に追加し・15章にfilename/identity不一致検出のtest項目を追加し、22章を非指示的な記述へ書き換えることで反映した。Minor 1件（9章・19章OQ3・Failure Matrix行7が、8章改訂後も「事前確認してから`list_all()`を呼ぶ」という2段階の古い構図のまま記述されていた）を、「確認は`list_all()`/`get()`内部の最初のステップである」という8章の最終設計と整合させて訂正した。
- **Round 5：`VERDICT: APPROVED`（Blocking 0件・Major 0件）。** Round 4の修正がBlocking/Major指摘をすべて解消したことを確認した上での承認。Minor 4件（6章の「20章Manual Recovery Procedure」という参照が、本書自身の20章（Architecture Gate Checklist）と紛らわしかった／14章「`PROTECTED_PATHS["scripts"]`へのsource contribution追加」という表現が、`PROTECTED_PATHS`自体はsubscript不可能なflat tupleであるため不正確だった（正しくは`_SOURCE_CHANGE_CONTRIBUTIONS`への追加）／15章が項目14追加後も「上記1〜13項目」のまま更新されていなかった／17章のZero-Diff対象リストに`scripts/run_scheduler_driver.py`が含まれる一方、14章の同等リストには含まれておらず「14章と同一」という17章の記述と矛盾していた）は、Blocking/Majorではないため追加レビューを経ずに本改訂で直接反映した（6章・14章・15章・17章）。
- 本書はRelease 6.36候補「Manual Recovery Diagnostic CLI Foundation」のArchitecture Phase成果物である。
- Baseline: branch `main`, HEAD=origin/main=`fedad93f285f5f682ff1eaa1b4f1b57fe41c10c5`, Working Tree clean（本書自体の作成に着手する直前の時点。Codex Round 3指摘：本書作成後は本ファイル自体がuntrackedとして`git status`に現れるが、これは「本書とこのファイル自体のみが成果物である」という次段落の前提どおりの想定内の差分であり、commit/pushは行わない）。Release 6.35.0（MVP End-to-End Hardening & Validation）完了・MVP COMPLETE。
- **本Releaseは最初のPost-MVP Release候補である。MVP Definition of Doneは変更・再オープンしない**（16章参照）。
- 本フェーズではProduction実装（`src/` / `scripts/` / `tests/`）・commit・pushは一切行わない。本書とこのファイル自体のみが成果物である。
- Release番号「6.36」は`docs/MVP_COMPLETION_ROADMAP.md`のForecast章（324-327行）が示す「range：Release 6.34〜6.36」の範囲内だが、**6.36の個別節（Goal/In Scope/Out of Scope等）はRoadmap本文にまだ存在しない**（6.30〜6.35のみ個別節を持つ）。本書はこの前提のもとで暫定的に「Release 6.36候補」として設計するが、正式なRelease番号・scope確定はRoadmap Governance手続き（16章）とHuman Gate（20章）を経る。scopeは今回もまだ確定しない（ユーザー指示）。

---

## 1. Background / Motivation

`SchedulerDispatchLedger`（`src/scheduler_dispatch_ledger/`, v6.34.0）は、`reconcile_stale_claims()`が`CLAIMED`のまま確認されなかったentryを`RECOVERY_REQUIRED`（終端状態）へ遷移させる（`scheduler_dispatch_ledger.py:100-129`）。この状態を人間が確認するための読み取り専用API `list_recovery_required()` / `peek()` は6.34時点で既に実装済みであり（`scheduler_dispatch_ledger.py:131-141`）、docstringにも「20章 Manual Recovery Procedure向け」と明記されている。

しかし、これを消費する人間向けCLIは存在しない。6.34 Architecture Gate Checklist item 9で「本Releaseからは除外する」とユーザーが明示的に確認済み（`MVP_COMPLETION_ROADMAP.md:240`）、6.35でも同様にOut of Scope（`mvp_end_to_end_hardening_validation.md` 32行）とされてきた。`docs/CHANGELOG.md:466`・`docs/architecture.md:5925-5927`の双方に「Future Extension」として記録済みの、既知だが未着手のgapである。

Release 6.36候補は、このgapを、既存の3-phase write-once-forward-only契約（8章、`dispatch_phase.py`）を一切変更せずに埋める、最小のread-only診断CLIを設計する。

---

## 2. Scope

### In Scope（暫定、ユーザー提示に準拠）

1. `scripts/show_scheduler_recovery.py` のread-only CLI
2. `SchedulerDispatchLedger.list_recovery_required()` によるRECOVERY_REQUIRED一覧取得
3. `event_identity` によるread-only filter（`list_recovery_required()` 結果に対するin-memory filter）
4. `job_id` / `occurrence_minute` / `claimed_at` / `updated_at` 等の診断表示
5. Execution History確認手順の案内（既存 `scripts/show_execution_history.py` への言及）
6. 必要時の `scripts/run_workflow_engine.py --job-id` による手動補完手順の案内（案内のみ、CLIからの自動実行はしない）
7. store異常時のfail-closed診断
8. E2E / Zero-Diff / Formal Regression計画
9. Architecture / Roadmap / CHANGELOG更新方針（実装完了後に反映する計画のみ、本書では未変更）

### Out of Scope（明示的除外）

- RECOVERY_REQUIRED自動復旧
- ledgerへの新規write API（reclaim / resolve / acknowledge等）
- re-claim / re-dispatch
- HUMAN_REVIEW_REQUIRED UI
- Windows Task Scheduler
- WordPress / Media Upload idempotency
- RetryQueue / RetryHistory完全永続化
- production activation
- `release_claim()` Suggestion（`src/retry_engine/retry_executor.py`、6.32 Final Review由来。Scheduler Dispatch Ledgerとは無関係の別サブシステムであり、技術的依存もない。完全に独立したFast Track候補として今後も保留する）
- Dashboard / notification

---

## 3. Goals / Non-Goals

### Goals

- **G1.** `list_recovery_required()` を消費する、人間が実行可能なread-only CLIを提供する。
- **G2.** CLIの実行が、いかなる場合も `SchedulerDispatchLedger` のdurable state（3-phase、write-once-forward-only）へ書き込みを行わないことを構造的に保証する。
- **G3.** `peek()` のNone-on-read-error契約を、authoritativeな診断経路から排除する（`list_recovery_required()` のみを一次情報源とする）。
- **G4.** store_dir未初期化・非ディレクトリ状態でCLIがディレクトリ・ファイル・lockを新規作成しないことを保証する。
- **G5.** 読み取り不能（store I/O異常）を「該当なし」に暗黙変換しない、既存store契約（8.5章）と同じ原則をCLI層でも維持する。
- **G6.** SchedulerDriverの起動用lock（`.run/scheduler_driver.lock`）・store lock（`.store.lock`）のいずれも取得せず、稼働中のSchedulerDriverや他のCLI呼び出しと安全に共存できる。
- **G7.** CLIは診断情報・既存手順の提示のみを行い、復旧の実行・判定・ledger状態変更を一切行わない。

### Non-Goals

- **N1.** RECOVERY_REQUIREDの自動復旧（reclaim的な新規write API含む）
- **N2.** `release_claim()` Suggestionの解消
- **N3.** Dashboard／外部通知／UI
- **N4.** ledgerのcleanup／保持期間管理（既存Post-MVP項目、6.34 Risk R7を継承）
- **N5.** 復旧要否の自動判定（"safe to retry"等）

---

## 4. 用語・キー概念

| 用語 | 定義 |
|---|---|
| **RECOVERY_REQUIRED** | claim済みだがconfirmされないまま`reconcile_stale_claims()`に到達したentryの終端状態（`dispatch_phase.py:23`）。自動復旧しない。 |
| **Diagnostic CLI** | 本書が設計する `scripts/show_scheduler_recovery.py`。read-only、ledgerへの書き込み一切なし。 |
| **Store Initialization Boundary** | `JsonSchedulerDispatchLedgerStore`のconstructorがstore_dirを`mkdir`する既存挙動から、CLIを構造的に隔離する境界（8章）。 |
| **Operator Decision Boundary** | CLIが診断情報の提示までを担い、復旧の要否判断・実行は常に人間が行うという境界（11章）。 |

---

## 5. Existing Architecture Facts（既存実装調査）

- `src/scheduler_dispatch_ledger/dispatch_phase.py:20-23`：3-phase Enum（`CLAIMED` / `CONFIRMED` / `RECOVERY_REQUIRED`）。owner_token authorityなし。
- `src/scheduler_dispatch_ledger/scheduler_dispatch_ledger.py:131-134`：`list_recovery_required()`。`store.list_all()`を呼び、`phase == RECOVERY_REQUIRED`でfilterするのみ。lockを取得しない（`with self._store_lock():`を使うのは`claim()`(53-77)・`confirm()`(79-98)・`reconcile_stale_claims()`(100-129)のみ）。
- 同ファイル136-141行：`peek()`。読み取り失敗時に`SchedulerDispatchLedgerStoreReadError`を捕捉してNoneを返す、docstring自身が「安全性判断には使わない」と明記。
- `src/scheduler_dispatch_ledger/scheduler_dispatch_ledger_store.py:214-216`：`JsonSchedulerDispatchLedgerStore.__init__`が`self._store_dir.mkdir(parents=True, exist_ok=True)`を無条件実行する（Codex Round 1 Blocking対応の意図的設計）。
- 同ファイル274-304行：`_ensure_store_dir_accessible()`（private）。`os.lstat()`を使用し`Path.exists()`/`Path.is_dir()`を避ける（Python 3.14がOSErrorを握りつぶす実装のため）。
- 同ファイル360-395行：`list_all()`。列挙・個別レコード読み取りのいずれかが失敗すれば`SchedulerDispatchLedgerStoreReadError`を送出し、部分結果を返さない。
- `src/scheduler_dispatch_ledger/scheduler_dispatch_ledger_config.py:20-35`：`SchedulerDispatchLedgerConfig.from_env(project_root)`、`store_dir`プロパティ（`ledger_dir/"entries"`）、`store_lock_path`プロパティ（`ledger_dir/".store.lock"`）。
- `src/scheduler_dispatch_ledger/dispatch_ledger_entry.py:20-31`：`DispatchLedgerEntry`フィールド一覧（`event_identity` / `job_id` / `occurrence_minute` / `phase` / `claimed_at` / `confirmed_at` / `dispatch_run_id` / `outcome_summary` / `detail` / `updated_at`）。RECOVERY_REQUIRED entryは、通常のledger-owned遷移経路では`confirmed_at`/`dispatch_run_id`/`outcome_summary`が`None`となる（confirm()に到達していないため）が、これはschemaで強制された不変条件ではない（9章で詳述、Codex Round 1 Minor#2対応）。
- `src/scheduler_driver/scheduler_driver_orchestrator.py:65-88`：`run_once()`が`reconcile_stale_claims()`を呼ぶ経路。本CLIはこの経路（`SchedulerDriverOrchestrator`/`SchedulerDriverCompositionRoot`）を一切importしない。
- `scripts/show_execution_history.py`（全体）：既存の同型read-only CLIパターン。`is_ready()`チェックをスキップしhistory_dirを直接読む設計（14-16行）を先例とする。
- `scripts/show_retry_notification.py`（全体）：Exit Code Policy明記・pure format関数とI/O分離のパターンを先例とする。
- `scripts/run_workflow_engine.py:175-252`：`--job-id`手動経路。本CLIから案内するのみで、呼び出しはしない。

---

## 6. Design Decision A：CLI Interface

```
scripts/show_scheduler_recovery.py                          # 一覧表示（claimed_at昇順、表示のみの並び替え）
scripts/show_scheduler_recovery.py --job-id <JOB_ID>         # job_id完全一致でfilter
scripts/show_scheduler_recovery.py --event-identity <ID>     # event_identity完全一致でfilter
scripts/show_scheduler_recovery.py --limit N                 # 表示件数制限（show_execution_history.py同様）
```

出力（1entryあたり）：`job_id` / `occurrence_minute` / `event_identity` / `claimed_at` / `updated_at`を常に表示する。加えて、`confirmed_at`/`dispatch_run_id`/`outcome_summary`は、通常は`None`であるため既定では省略するが、**いずれかが`None`以外の値を持つ場合はその値をそのまま追加表示する**（9章のRECOVERY_REQUIRED付随フィールド非強制の議論と整合。「`None`のはず」という前提でエラー・警告・非表示化はしない）。出力の末尾に、`scheduler_driver_duplicate_dispatch_safety_foundation.md` 20章Manual Recovery Procedureの案内文（Execution History確認コマンド例・`--job-id`手動補完コマンド例）を固定テキストとして表示する（Codex Round 5 Minor対応：本書自身の20章は別内容——Architecture Gate Checklist——のため参照先を明示）。

**Config Bootstrap（Codex Round 1 Major#1対応、明確化）**：`scripts/show_execution_history.py`（21-26行）と同一のbootstrap順序を踏襲する——(1) `base_dir = Path(__file__).parent.parent` でproject_rootを解決する、(2) `sys.path.insert(0, str(base_dir / "src"))`、(3) `load_dotenv(base_dir / ".env")` を`SchedulerDispatchLedgerConfig.from_env()`呼び出しより**前**に実行する。この順序を守らない場合、`.env`で`SCHEDULER_DISPATCH_LEDGER_DIR`をカスタム設定していても反映されず、CLIが誤ったディレクトリ（デフォルトの`state/scheduler_dispatch`）を診断してしまう。

**`--limit`の契約（Codex Round 1 Minor#1対応、明確化）**：正の整数のみを許容する（0以下は`argparse`のvalidationでエラーとする、`type`引数にvalidator関数を渡すか`main()`内で明示チェックする）。適用順序は「filter（`--job-id`/`--event-identity`）→ソート（`claimed_at`昇順）→`--limit`による先頭N件切り出し」の順で固定する（`show_execution_history.py`の`records[:args.limit]`と同型）。

**filterの組み合わせ（Codex Round 1 Minor#1対応、明確化）**：`--job-id`と`--event-identity`を同時指定した場合はAND条件（両方に一致するentryのみ）として扱う。暗黙のOR・優先順位切り替えは行わない。

Exit Code Policy（`show_retry_notification.py`の先例に倣う）：

| 状況 | exit code |
|---|---|
| 正常処理（該当0件／N件いずれも） | 0 |
| Store Initialization Boundary違反検出（8章、fail-closed） | 1 |
| `SchedulerDispatchLedgerStoreReadError`（読み取り失敗） | 1 |
| argparse構文エラー | 標準の`SystemExit 2` |
| 予期しない例外 | 捕捉せず伝播 |

---

## 7. Design Decision B：read-only guarantee（Safety Contract A・B対応）

- `claim()` / `confirm()` / `reconcile_stale_claims()` を本CLIから一切importしない・呼ばない。使用する`SchedulerDispatchLedger`の公開APIは`list_recovery_required()`のみに限定する。
- `store.save()` も一切呼ばない。
- reclaim / resolve / acknowledge等の新規write APIを追加しない（18章）。
- `peek()` も一切使用しない。`--event-identity` / `--job-id` filterは、`list_recovery_required()`が返す結果に対するPython側のin-memory filter（リスト内包表記）として実装し、個別レコードを`store.get()`/`peek()`経由で再取得しない。これにより、読み取りエラーをNoneへ丸める`peek()`の契約が診断結果に一切混入しない。

---

## 8. Design Decision C：Store Initialization Boundary（Safety Contract C対応、Codex Round 2 Blocking#1対応で全面改訂）

**問題**：`JsonSchedulerDispatchLedgerStore`のconstructorは`store_dir`を`mkdir(parents=True, exist_ok=True)`する既存挙動を持つ（`scheduler_dispatch_ledger_store.py:214-216`、Codex Round 1 Blocking対応による意図的設計）。CLIがこのクラスを単純にinstantiateすると、診断のためだけに新規ディレクトリを作成してしまい、「CLI自身は`state/`配下へ新規ファイル・ディレクトリ・lockを作成してはならない」というSafety Contract Cに違反する。

**Round 1版の欠陥（Codex Round 2 Blockingで指摘）**：Round 1版は「事前に`os.lstat()`で確認してから`JsonSchedulerDispatchLedgerStore`をinstantiateする」という設計だったが、事前確認と直後のconstructor呼び出しの間には（Pythonの関数呼び出し1回分という）非ゼロのTOCTOU windowが残り、この窓の中で外部プロセスがstore_dirを削除した場合、直後のconstructorの無条件`mkdir()`が当該ディレクトリを**実際に再作成してしまう**。Safety Contract C（「診断CLI自身がstate/配下へ新規ファイル・directory・lockを作成してはならない」）は確率の多寡を問わない絶対条件であり、「低確率のAccepted Risk」として文書化するだけでは充足されない（store.py自身が持つ読み取り専用のTOCTOU——読み取り結果が不正確になりうるだけで新規に状態を作らない——とは性質が異なり、同列には扱えない）。この欠陥は本節を全面改訂して解消する。

**改訂後の設計：CLI専用のread-only store adapter（`JsonSchedulerDispatchLedgerStore`のconstructorを一切呼ばない）**

`SchedulerDispatchLedgerStore`は抽象基底クラス（ABC、`save()`/`get()`/`list_all()`の3メソッド、`scheduler_dispatch_ledger_store.py:179-200`）であり、`SchedulerDispatchLedger`（5章）はconstructorで任意の適合実装を受け取る依存性注入設計になっている（`scheduler_dispatch_ledger.py:44`：`def __init__(self, store: SchedulerDispatchLedgerStore, config: ...)`）。本CLIは、この既存の拡張点をそのまま使い、`scripts/show_scheduler_recovery.py`内に**`mkdir`を一切呼ばない独自のread-only実装**を新設する：

- `class _ReadOnlyDispatchLedgerStore(SchedulerDispatchLedgerStore)`：
  - `__init__(self, store_dir: Path)`：`self._store_dir = store_dir`を保持するのみ。**`mkdir`呼び出しを一切含まない。**
  - `save(self, entry) -> bool`：呼ばれた場合は`NotImplementedError`を送出する（CLIから絶対に呼ばれないことのコード上の証明として機能する）。
  - **インポートして再利用する部分（Codex Round 3 Blocking#1対応、対象を正確化）**：store.pyの中で真にmodule-level（クラス外定義）の純粋関数、`_sanitize_event_identity()`（store.py:57-96）と`_entry_from_dict()`（store.py:114-176）の2つ**のみ**を`from scheduler_dispatch_ledger.scheduler_dispatch_ledger_store import _sanitize_event_identity, _entry_from_dict`としてimportする。加えて公開例外`SchedulerDispatchLedgerStoreReadError`をimportする。
  - **CLI側で新規に実装する部分（Round 3で訂正・明確化）**：`_read_record_file()`（store.py:306-328）・`_ensure_store_dir_accessible()`（store.py:274-304）は、`JsonSchedulerDispatchLedgerStore`の**instance method**（`self`を第一引数に取るクラス内定義）であり、module-level関数として直接importすることはできない（Round 2版の記載は誤りだった、Codex Round 3で指摘）。したがって本adapterの`get()`/`list_all()`は、これらのメソッドの**アルゴリズム（`os.lstat()`によるディレクトリ確認・`os.scandir()`による列挙・regular-file検査・`json.loads()`読み取り）そのものを、本adapter自身の新規コードとして再実装**し、パース・スキーマ検証（`_entry_from_dict()`）とfilename sanitize（`_sanitize_event_identity()`）の部分だけを、上記のimportした module-level関数へ委譲する。この新規実装は、いかなる分岐においても`mkdir`・`open(..., "w")`・`os.replace()`等の書き込み系API呼び出しを一切含まない（読み取り専用APIのみで構成する：`os.lstat()`・`os.scandir()`・`Path.read_text()`）。

この設計により、CLI自身が持つコードのうち「複製」となるのはディレクトリ確認・列挙・個別ファイル読み取りという**制御フロー**のみであり、安全性の核心（parsing・schema検証・sanitize）は既存の`_entry_from_dict()`/`_sanitize_event_identity()`を直接importして再利用するため、本体（store.py）が将来これらの関数を改修した場合でもCLI側が自動的に追従する。制御フロー部分の重複は、mkdirを一切含まない読み取り専用の逐次処理であるため、Round 1版が抱えていた「安全性判断そのものが将来乖離するリスク」とは性質が異なる、より限定的なリスクである。module-privateな名前を跨モジュールでimportするという設計自体は通常の慣行から外れるため、20章Gate 1で明示的な承認を求める。

**呼び出し側**：`ledger = SchedulerDispatchLedger(store=_ReadOnlyDispatchLedgerStore(config.store_dir), config=config)` としたうえで、5章と同じ`ledger.list_recovery_required()`をそのまま呼ぶ（`SchedulerDispatchLedger`自体は無変更、店員が変わるだけで店の運営方法自体は変わらない、という比喩どおりpolymorphic dispatchにより`list_recovery_required()`内部の`self._store.list_all()`呼び出しが自動的に本adapterへ向かう）。

**必須のcross-check 2種（Codex Round 4 Major#1対応、明示化）**：本adapterの`get()`/`list_all()`は、単に`_entry_from_dict()`でパースするだけでなく、store.py本体が行っている以下2種類のfilename/event_identityクロスチェック（多層防御、store.py 8.5章・16章）を**両方とも**再実装する。片方でも欠けると、正当な安全性チェックを迂回した不正な・衝突したentryを正常結果として返してしまう：
1. `get()`相当のチェック（store.py:346-357が実装する契約と同型）：要求された`event_identity`から`_sanitize_event_identity()`で導出したファイル名で読んだrecordの、record自身が主張する`event_identity`フィールドが、要求した`event_identity`と一致することを確認する。不一致なら`SchedulerDispatchLedgerStoreReadError`。
2. `list_all()`相当のチェック（store.py:387-393が実装する契約と同型）：列挙で見つかった各ファイル名が、そのファイルを読んで得たrecordの`event_identity`を`_sanitize_event_identity()`でエンコードした結果と一致することを確認する。不一致なら`SchedulerDispatchLedgerStoreReadError`。

**結果**：CLIの実行経路上、いかなるタイミング・いかなる外部プロセスの競合が起きても、`mkdir`を呼び出すコードパスがコード上に一切存在しない。8章冒頭で述べた問題（constructorのmkdir副作用）は、TOCTOU windowを縮小するのではなく、**mkdirを呼ぶ経路そのものを構造的に排除する**ことで解消する。Round 1版で許容していたAccepted Risk（19章旧R1）は本改訂により解消済みとする。

**store_dir確認のタイミング（Codex Round 4 Minor対応、明確化）**：本adapterの`get()`/`list_all()`は、それぞれの処理冒頭で（store.py自身の`get()`/`list_all()`と同じ順序で）ディレクトリ確認を行ってから列挙・読み取りへ進む。したがって「事前確認してから呼び出す」という2段階の外部手順ではなく、**確認は`list_all()`/`get()`という単一の呼び出しの内部の最初のステップである**。残存するTOCTOU（このディレクトリ確認と直後の`os.scandir()`/ファイル読み取りの間の窓）は、store.py自身が内部に持つ同型のTOCTOU（store.py:335-344の設計と同一原理）と同一線上のread-side risk（読み取り結果に影響するだけで、新規に状態を作らない）であり、8章冒頭のmkdir問題（Safety Contract C違反）とは別種のリスクである。9章・19章OQ3の記述はこの整理と整合させる。

**検討した代替案**：
1. `scheduler_dispatch_ledger_store.py`側に新規の「非mkdirコンストラクタ」を追加する案 → 却下（18章#1）。`src/scheduler_dispatch_ledger/`のZero-Diff原則に反する。
2. Round 1版：事前`os.lstat()`確認＋通常の`JsonSchedulerDispatchLedgerStore`instantiate → 却下（Codex Round 2 Blocking#1指摘）。TOCTOU windowが残り、Safety Contract Cの絶対条件を満たさない。
3. Round 2版：`_read_record_file()`をmodule-level関数として直接importする案 → 却下（Codex Round 3 Blocking#1指摘）。実際にはinstance methodでありimport不可能、記述どおりでは実装不能。
4. `_sanitize_event_identity()`/`_entry_from_dict()`もimportせず、パース・スキーマ検証・sanitizeロジックをCLI側へ完全に独自実装する案 → 却下。安全性が本質的に同一のコードを2箇所で保守することになり、将来の乖離リスクをより大きな範囲へ拡大するだけで、mkdir回避という目的に対して追加の安全性を何ら提供しない。

---

## 9. Design Decision D：read failure semantics（Safety Contract B対応）

- `list_recovery_required()`は内部で`store.list_all()`を呼ぶ。列挙・個別レコード読み取り・パース・スキーマ検証のいずれかが失敗した場合、`SchedulerDispatchLedgerStoreReadError`が送出され、部分結果は返らない（`scheduler_dispatch_ledger_store.py:360-395`）。
- CLIはこの例外を捕捉し、「該当0件でした」ではなく明確な診断失敗として報告し、exit 1で終了する。読み取り不能を「存在しない」へ変換しない。
- 8章で述べたとおり、本adapterの`list_all()`/`get()`はそれぞれの呼び出し内部の最初のステップとしてディレクトリ確認を行う（外部の2段階手順ではない、Codex Round 4対応）。この内部確認と直後の`os.scandir()`/ファイル読み取りの間には、依然としてゼロではないTOCTOU残存可能性がある。ただしこれはstore.py自身が内部的に持つ同型の残存リスク（store.py:335-344、8.5章のAccepted Riskモデルと同一線上、read-side riskであり新規に状態を作らない）であり、CLIが新たなリスクを持ち込むものではない（19章OQ3）。

**RECOVERY_REQUIRED entryの付随フィールドについて（Codex Round 1 Minor#2対応、明確化）**：通常のledger-owned遷移（`reconcile_stale_claims()`は`phase==CLAIMED`のentryのみを対象とし、`confirmed_at`/`dispatch_run_id`/`outcome_summary`は`confirm()`でのみ設定されるため、`scheduler_dispatch_ledger.py:121-123`）では、RECOVERY_REQUIRED entryのこれら3フィールドは`None`のままとなる。ただし、これは**schemaレベルで強制された不変条件ではない**——`_entry_from_dict()`（store.py:114-176）はphaseと付随フィールドの整合性を検証しない。したがってCLIの表示ロジックは、これらのフィールドが（手動改変・想定外の経路等により）`None`以外の値を持っていた場合でも、単にそのまま表示するのみとし、エラー・警告・非表示化のいずれも行わない（「`None`のはず」という前提に基づく分岐ロジックを持たない）。

---

## 10. Design Decision E：concurrency / snapshot semantics（Safety Contract D対応）

- CLIはSchedulerDriverの起動用lock（`.run/scheduler_driver.lock`）を取得しない。`SchedulerDriverCompositionRoot`/`SchedulerDriverOrchestrator`のいずれもimportしない。
- CLIはstore lock（`.store.lock`、`SchedulerDispatchLedgerStoreLock`）も取得しない。`list_recovery_required()`自体がこのlockを要求しない既存契約（5章参照、`with self._store_lock():`を使うのは`claim`/`confirm`/`reconcile_stale_claims`のみ）であるため、CLIはこの既存契約をそのまま継承するだけでよく、新たな回避策の実装は不要である。
- **出力は「point-in-time snapshot」ではなく、`list_all()`呼び出しの実行時間幅にわたるnon-atomicなbest-effort readである（Codex Round 1 Major#2対応、表現訂正）**：`list_all()`（store.py:360-395）はstore lockを取得せず、(a)ディレクトリを列挙して名前一覧を確定し、(b)各ファイルを順に読む、という2段階を単一のatomic操作としてではなく逐次実行する。このため、列挙から最後のファイル読み取りまでの間にconcurrent writer（SchedulerDriverの`claim()`/`confirm()`/`reconcile_stale_claims()`）がentryを追加・遷移させた場合、CLIが得る結果は「単一時刻の一貫したsnapshot」ではなく、「列挙開始時点で存在した名前集合を、実行時間幅にわたって順次読み取った結果」である。ある1件のentryが遷移の前後どちらの状態で読まれるかはタイミング次第であり、CLIはこれを保証しない。
- CLI実行後に新たなRECOVERY_REQUIREDが生成されないこと、および実行**中**に生成されたentryが結果に反映される保証も、いずれも与えない。この限定を出力メッセージ末尾にも明記する。
- concurrent writerと読み取りが競合した場合でも、9章のfail-closed契約（partial/corrupt readを正常結果として扱わない）はそのまま適用される。store.py自身のatomic write契約（`tempfile.mkstemp`→`fsync`→`os.replace`）により、CLIが読む**個々のファイル**は常にある時点の完全な書き込み済みJSONか、まだ存在しない状態のいずれかであり、1ファイル単位で見た場合に破損した中間状態を読むことは構造的にない——ただし、この保証はファイル単位のものであり、複数ファイルにまたがる集合としての一貫性（上記のnon-atomic性）までは保証しない、という区別を明確にする。

---

## 11. Design Decision F：operator decision boundary（Safety Contract E対応）

- CLIが表示するのは診断情報（一覧・詳細）と、`scheduler_driver_duplicate_dispatch_safety_foundation.md` 20章 Manual Recovery Procedureの案内文言のみ。
- 自動判断・自動実行しないもの：safe to retry判定、workflow再実行、ledger state変更、recovery完了認定。いずれもコード上、判定ロジック・呼び出しを一切持たない。
- 案内文言は、既存`scripts/show_execution_history.py`・`scripts/run_workflow_engine.py --job-id`の実行コマンド例を固定文字列として表示するのみであり、`subprocess`等による自動実行は行わない。

---

## 12. Failure Matrix

| # | 状況 | CLIの挙動 | exit code |
|---|---|---|---|
| 1 | store_dirが存在しない（初回未初期化） | fail-closedで終了、メッセージ表示、ディレクトリ作成なし | 1 |
| 2 | store_dirがディレクトリでない（ファイル等） | fail-closedで終了 | 1 |
| 3 | store_dir権限エラー等のOSError | fail-closedで終了 | 1 |
| 4 | store_dirは正常、RECOVERY_REQUIRED該当0件 | 「該当なし」と表示（正常系） | 0 |
| 5 | store_dirは正常、RECOVERY_REQUIRED該当N件 | 一覧表示 | 0 |
| 6 | 個別レコードの破損（JSON不正／スキーマ不正） | `SchedulerDispatchLedgerStoreReadError`を捕捉し診断失敗として報告 | 1 |
| 7 | 列挙中の消失（他プロセスとの競合） | 同上（本adapter自身がraiseする、8章。store.py自身は呼ばれない） | 1 |
| 8 | `--event-identity`/`--job-id`指定で該当0件 | 「該当なし」と表示（filter結果が空、正常系） | 0 |
| 9 | argparse構文エラー | 標準の`SystemExit` | 2 |
| 10 | 想定外の例外 | 捕捉せず伝播 | 非0（Python標準） |

---

## 13. Component Inventory（Codex Round 2対応、8章改訂に合わせて更新）

**既存再利用（無変更のままimport）**：`SchedulerDispatchLedgerConfig`、`SchedulerDispatchLedgerStore`（ABC、CLI専用の新規実装が継承する）、`SchedulerDispatchLedger`（constructor・`list_recovery_required()`）、`DispatchLedgerEntry`、`DispatchPhase`、`SchedulerDispatchLedgerStoreReadError`、および`scheduler_dispatch_ledger_store`モジュールのmodule-level private関数`_sanitize_event_identity()`・`_entry_from_dict()`（8章、Codex Round 3対応でimport対象を訂正——`_read_record_file()`はinstance methodのため対象外）。**`JsonSchedulerDispatchLedgerStore`自体はCLIから一切importも使用もしない**（8章、`mkdir`副作用を持つため）。

**新規**：`scripts/show_scheduler_recovery.py` 1ファイルのみ（内部に`_ReadOnlyDispatchLedgerStore`クラスを含む）。新規package・`src/`配下への新規ファイルはゼロ。

---

## 14. Planned File Impact（実装フェーズでの変更対象候補一覧、本Architecture Phaseでは未変更）

### 新規作成候補

- `scripts/show_scheduler_recovery.py`
- `tests/test_e2e_v6_36_0_manual_recovery_diagnostic_cli_foundation.py`（仮称、正式Release番号確定後に確定）

### 変更対象（必須、実装フェーズ）

- `tests/zero_diff_guard_registry.py`（Codex Round 1 Major#4対応、明確化・網羅化）：
  1. `RELEASE_ORDER`タプルへ`"v6.36.0"`を追記する（`zero_diff_guard_registry.py:43-59`、既存慣行どおり末尾に追加。これ自体が本レジストリの「自己編集」であり、`_TEST_CHANGE_CONTRIBUTIONS`への自己登録が別途必要になる、v6.34.0/v6.35.0の先例と同型）。
  2. `_SOURCE_CHANGE_CONTRIBUTIONS`（`PROTECTED_PATHS`が列挙する保護対象パス「`scripts`」に対する寄与record一覧、Codex Round 5 Minor対応：`PROTECTED_PATHS`自体はパス文字列のflat tupleでありsubscriptできない点を訂正）への新規タプル追加：`("scripts", "v6.36.0", frozenset({"scripts/show_scheduler_recovery.py"}))`（`zero_diff_guard_registry.py:94-115, 209-216`「scripts」パターン、v6.30/v6.32/v6.33/v6.34の先例と同型）。
  3. `_TEST_CHANGE_CONTRIBUTIONS`へ、本Releaseで変更される**すべての**testファイルを登録する（新規追加分だけでなく既存ファイルへの変更も含む）：
     - 新規E2Eファイル自身（`tests/test_e2e_v6_36_0_manual_recovery_diagnostic_cli_foundation.py`）
     - `tests/test_e2e_v6_32_7_invariant_35_closure_oracle.py`（下記4.の変更に伴う登録）
     - `tests/test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py`（下記5.の変更に伴う登録）
     - `tests/zero_diff_guard_registry.py`自身（上記1.・2.の編集本体）
  4. **`tests/test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py`のstandalone guard対応は「可能性」ではなく確定的に必要（Codex Round 1・Round 2指摘：v6.32→v6.33→v6.34と3リリース連続で発生している同一メカニズムであり、確率的事象ではなく機械的帰結）**：同ファイルが持つ独立guard（本レジストリを参照しないstandalone allow-list `_ZERODIFF1_ALLOWED_EXCEPTIONS["scripts"]`、`zero_diff_guard_registry.py:577-581, 590-595`のコメントが指す先例、当該guard自体の定義は`test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py:304`（`_ZERODIFF1_ALLOWED_EXCEPTIONS`辞書本体）、`330`（`"scripts"`キー配下のfrozenset）、`363-367`（allow-listとの突き合わせ処理）——Codex Round 2で当初の行番号引用（154/205/213）が誤りと指摘され訂正した）は、baseline HEADからの`scripts/`配下の差分を許可リストと突き合わせる方式であるため、`scripts/show_scheduler_recovery.py`という新規trackedファイルの追加は、これをallow-listへ追加登録しない限り必ずFAILする。実装フェーズの初回Formal Regression実行前に対応する（19章OQ4）。
- `tests/test_e2e_v6_32_7_invariant_35_closure_oracle.py`（Codex Round 1 Major#3対応、件数を実測値へ訂正）：
  - Stage A candidate root列挙（scripts/配下の全`*.py`ファイルを再帰列挙、同ファイル19-25行）が、新設`scripts/show_scheduler_recovery.py`を新たなcandidateとして検出する。
  - **manifest件数の訂正**：同ファイル98-148行を実測した結果、現在の`SIDE_EFFECT_CAPABLE_MANIFEST`は10エントリ、`NON_SIDE_EFFECT_CAPABLE_MANIFEST`は10エントリ（`assert len(...) == 10`が2箇所、143-145行）の**計20エントリ**であり、本書が当初参照した同ファイル冒頭docstring（1-50行）の「SIDE_EFFECT_CAPABLE 9エントリ＋NON_SIDE_EFFECT_CAPABLE 10エントリ、計19エントリ」という記述は、v6.34.0で`scripts/run_scheduler_driver.py`が10番目のSIDE_EFFECT_CAPABLEエントリとして追加された後に更新されていない古い記述であった（本書の誤り、Codex Round 1で指摘）。
  - 本CLI（`scripts/show_scheduler_recovery.py`）は`WorkflowEngineManager.run()`を含むsink A/B/Cのいずれにも到達しないため、`NON_SIDE_EFFECT_CAPABLE_MANIFEST`の**11番目のエントリ（全体では21番目）**として追加する（実装フェーズでAST closure解析により実測確認する。closed classification manifestの排他性assertion・件数assertionの期待値更新も必須）。

### 変更対象ではない（Codex Round 2 Major#2対応、根拠を示して明確化）

- `tests/formal_regression_inventory.py`（`FORMAL_REGRESSION_ROSTER`、37-file roster）・`tests/test_e2e_v6_35_8_t6_formal_regression_roster_validation.py`（roster静的validator）は、**本Releaseでは変更しない**。根拠：`docs/design/mvp_end_to_end_hardening_validation.md` 19.1章（726-766行）が定めるrosterは`v1.11.0`〜`v6.34.0`の37ファイルに固定されたhistorical snapshotであり、**6.35自身の新規E2Eファイル（`test_e2e_v6_35_0`〜`_8`の9ファイル）ですらこのrosterに含まれていない**（architecture.md:5941「Formal Regression 37/37 PASSへ到達した」——roster件数は37のまま増えていない）。6.35の新規E2Eは「targeted E2E」として別途独立に検証されている（architecture.md:5933「targeted E2E...163/163 PASS」、Formal Regression 37/37とは別枠）。この先例に倣い、本Release（6.36）の新規E2Eファイルも「Formal Regression」ではなく本Release自身の「targeted E2E」として検証し、37-file rosterへは追加しない。

### 変更対象（実装完了後、別タイミング）

- `docs/architecture.md` / `docs/MVP_COMPLETION_ROADMAP.md` / `docs/CHANGELOG.md`（実装完了後に新規セクション追記。本Architecture Phaseでは変更しない）

### 変更しない（Zero-Diff、必須）

- `src/scheduler_dispatch_ledger/` 配下全ファイル
- `src/scheduler_driver/`, `src/scheduler_schedule_source/` 配下全ファイル
- `scripts/show_execution_history.py`, `scripts/run_workflow_engine.py`, `scripts/run_scheduler_driver.py`（Codex Round 5 Minor対応：17章のリストと一致させる）
- `.env.example`（本CLIは新規gate変数を導入しない。`scripts/show_execution_history.py`同様、`is_ready()`判定を経由しない設計のため）

---

## 15. Test / E2E / Zero-Diff / Formal Regression方針

実装フェーズで以下を新規E2Eとして検証する（本Architecture Phaseでは未実装・未実行）：

1. RECOVERY_REQUIRED 0件時の正常終了（exit 0）
2. RECOVERY_REQUIRED N件時の一覧表示内容の正確性（`job_id`/`occurrence_minute`/`claimed_at`/`updated_at`）
3. `--event-identity`/`--job-id` filterの正確性（`list_recovery_required()`結果に対するin-memory filterであることをコード上・テスト上両方で確認し、`store.get()`/`peek()`が一切呼ばれないことをモック等で確認）
4. store_dir未初期化時のfail-closed終了・ディレクトリ非作成の確認（テスト実行後にディレクトリが存在しないことをassertする）
5. store_dirが非ディレクトリ（ファイル）の場合のfail-closed終了
6. 個別レコード破損時の`SchedulerDispatchLedgerStoreReadError`捕捉・診断失敗報告
7. CLIがSchedulerDriverの起動用lock（`.run/scheduler_driver.lock`）・store lock（`.store.lock`）のいずれも取得しないことの確認（lockファイルの有無・mtimeで検証、または別プロセスがlockを保持していてもCLIが正常終了することを確認）
8. CLIが`claim()`/`confirm()`/`reconcile_stale_claims()`/`store.save()`を一切呼ばないことのAST静的解析またはモックによる確認（既存Invariant #35 closure oracleと同系統の手法）。8章改訂後の設計では`_ReadOnlyDispatchLedgerStore.save()`が`NotImplementedError`を送出する実装自体がこの契約の追加的な実行時保証になる。
9. 既存`scheduler_dispatch_ledger`・`scheduler_driver`・`scripts`配下の既存挙動がZero-Diffのまま維持されることの確認
10.（Codex Round 2 Minor対応、新規）カスタム`.env`（`SCHEDULER_DISPATCH_LEDGER_DIR`を独自設定したケース）でCLIが正しいディレクトリを診断することの確認（6章Config Bootstrap契約の検証）
11.（Codex Round 2 Minor対応、新規）`--limit`に0以下の値を渡した場合にエラーとなること、および`--limit`がfilter・ソート後の件数に対して適用されることの確認
12.（Codex Round 2 Minor対応、新規）`--job-id`と`--event-identity`を同時指定した場合にAND条件として動作することの確認
13.（Codex Round 2 Minor対応、新規）`confirmed_at`/`dispatch_run_id`/`outcome_summary`のいずれかが`None`以外の値を持つentryを人工的に用意し、CLIがエラーにせずそのまま表示することの確認
14.（Codex Round 4 Major#1対応、新規）filename/event_identity不一致（8章の2種類のcross-check）の検出確認：(a) 要求した`event_identity`から導出されるファイル名のrecord内容が異なる`event_identity`を主張しているケースで`get()`相当の処理が`SchedulerDispatchLedgerStoreReadError`を送出すること、(b) 列挙されたファイル名が、そのrecordの`event_identity`から`_sanitize_event_identity()`で導出される期待ファイル名と一致しないケースで`list_all()`相当の処理が同エラーを送出すること。いずれもCLIが「正常結果」として静かに受理しないことを確認する。

Formal Regression（Codex Round 3 Major#1対応、14章「変更対象ではない」との整合を取り訂正）：既存37-file roster（`tests/formal_regression_inventory.py`、本Releaseでは変更しない、14章参照）を対象とした既存機能への回帰確認と、本Release新規E2Eファイル（上記1〜14項目、Codex Round 5 Minor対応：項目14追加分を含めて訂正）を対象とした独立のtargeted E2E実行の、両方を実施する。両者は6.35の先例（architecture.md:5933・5941、Formal Regressionとtargeted E2Eを別枠として扱う）と同じ扱いであり、37-file roster自体へ新規E2Eファイルを追加することはしない。Invariant #35 closure oracle・Zero-Diff Guard Registry更新反映済みでの両者のPASS確認を実施する。

---

## 16. Roadmap Governance

- 現状、`docs/MVP_COMPLETION_ROADMAP.md`のForecast章（324-327行）は「中心：Release 6.35（MVP COMPLETE）、range：Release 6.34〜6.36」とするのみで、**6.36の個別節（Goal/In Scope/Out of Scope/Dependency/Completion Criteria）はRoadmap本文にまだ存在しない**（6.30〜6.35のみ個別節を持つ）。
- Roadmap Governance章（350-361行）の原則に従い、実装フェーズ着手前に以下を含む短いchange recordを`MVP_COMPLETION_ROADMAP.md`へ追記することを提案する（**本Architecture Phaseでは追記しない、Human Gate承認後に別途実施**）：
  - date：（承認日）
  - reason：Release 6.35でMVP COMPLETEに到達したため、最初のPost-MVP Releaseとして6.36個別節を新設する
  - affected releases：6.36（新設）
  - human approval status：承認待ち
- 併せて、Roadmap本文への6.36個別節（Goal/In Scope/Out of Scope/Dependency/Completion Criteria、本書2〜3章の内容を転記）の追加を提案する。文書バージョンはv1.4への改訂を想定する。
- **MVP Definition of Doneの条項自体への変更は本Releaseで一切提案しない**（0章・Non-Goals N5参照）。「MVP運用原則」（381-383行）はMVP COMPLETEまでの判断基準であり、MVP COMPLETE後の本Releaseに機械的に適用されるかは、Human Gateでの確認事項として20章に記録する。

---

## 17. Backward Compatibility / Zero-Diff対象

以下は本Releaseで**一切変更しない**（14章「変更しない」と同一。git diff 0であることを実装フェーズのE2Eで機械的に確認する対象）：

- `src/scheduler_dispatch_ledger/`
- `src/scheduler_driver/`, `src/scheduler_schedule_source/`
- `scripts/show_execution_history.py`, `scripts/run_workflow_engine.py`, `scripts/run_scheduler_driver.py`
- `.env.example`
- `tests/formal_regression_inventory.py`, `tests/test_e2e_v6_35_8_t6_formal_regression_roster_validation.py`（14章「変更対象ではない」参照、37-file rosterは本Releaseの対象外）
- Retry Runtime関連全パッケージ（`src/retry_*`, `src/side_effect_safety/`等、6.34/6.35のZero-Diff対象を継承）

---

## 18. Rejected Alternatives

1. `JsonSchedulerDispatchLedgerStore`へ新規の「非mkdirコンストラクタ」を追加する案 → 却下（8章）。`src/scheduler_dispatch_ledger/`のZero-Diff原則に反する。
2. `peek()`を`--event-identity`/`--job-id` filter機能の実装に使う案 → 却下（Safety Contract B、7章）。読み取りエラーをNoneへ丸める契約がauthoritativeな診断と相容れない。
3. store lockを診断目的でも念のため取得する案 → 却下（10章）。`list_recovery_required()`自体がlockを要求しない既存契約であり、CLIが独自にlockを取得すると、稼働中のSchedulerDriverとの不要な競合（lock待ち・timeout）を新たに持ち込むリスクがある。
4. 復旧の実行（`--job-id`経由の手動実行）をCLIから直接`subprocess`で起動するオプションを設ける案 → 却下（Safety Contract E、11章）。operator decision boundaryを越え、実質的な書き込み経路をCLIが持つことになる。
5. `RECOVERY_REQUIRED`をCONFIRMED等へ戻すresolve/acknowledge APIを新設する案 → 却下（2章Out of Scope）。8.4章相当の既存write-once-forward-only契約を維持する。6.34 Rejected Alternatives #1と同じ理由。

---

## 19. Risks / Open Questions

| # | 内容 | 深刻度 | 対応方針 |
|---|---|---|---|
| R1（解消済み） | Round 1版：store_dir事前確認と`JsonSchedulerDispatchLedgerStore`構築の間のTOCTOU windowで、constructorの無条件`mkdir()`がstore_dirを再作成しうる（Codex Round 1 Blocking#1指摘） | — | **Round 2で解消**（8章全面改訂）：`JsonSchedulerDispatchLedgerStore`のconstructorを一切呼ばず、`mkdir`を含まないCLI専用read-only store adapterへ置き換えた。mkdirを呼ぶコードパス自体が存在しないため、Accepted Riskとしてではなく構造的排除として解決する |
| OQ1 | Roadmap 6.36個別節の未存在（16章） | — | Human Gate（20章）で方針確認 |
| OQ2 | MVP運用原則のPost-MVP Releaseへの適用可否（16章） | — | Human Gateで確認 |
| OQ3 | 本adapter`list_all()`/`get()`内部のディレクトリ確認ステップと、直後の`os.scandir()`/ファイル読み取りとの間のTOCTOU残存（9章、Codex Round 4対応で「事前確認」ではなく「内部の最初のステップ」へ表現訂正） | Low | 既存store.py自身が持つ同型リスク（read-side、新規に状態を作らない）と同一線上、CLI固有の新規リスクではない |
| OQ4 | `zero_diff_guard_registry.py`のstandalone guard（`test_e2e_v6_27_0`）への追加登録（14章、Codex Round 1・Round 2で確定的に必要と判定済み。要否の判断ではなく実装フェーズでの作業手順のみが残る） | Low（作業量のみ） | 実装フェーズ初回Formal Regression実行前に、14章4.の手順で対応する |
| OQ5 | 「Operator Control」という名称が今回のread-only診断範囲を超える期待を生んでいないか | — | Human Gateで確認（20章） |

---

## 20. Architecture Gate Checklist（Human Gate必須確認事項、未承認）

1. Design Decision C（8章、Codex Round 2 Blocking#1・Round 3 Blocking#1対応で全面改訂）：`JsonSchedulerDispatchLedgerStore`のconstructorを一切呼ばず、`mkdir`を含まないCLI専用read-only store adapter（`SchedulerDispatchLedgerStore` ABCの新規実装）を設ける設計、真にmodule-level（クラス外定義）な`_sanitize_event_identity()`・`_entry_from_dict()`の2関数のみを直接importして再利用する一方、ディレクトリ確認・列挙・個別ファイル読み取りという制御フロー（`_read_record_file()`相当。instance methodのためimport不可、Round 3で訂正）は本adapter自身の新規コードとして再実装するという、通常の慣行から外れる設計判断に同意するか。
2. Design Decision B（7章）：`peek()`を一切使用せず、`list_recovery_required()`結果へのin-memory filterのみで`event_identity`/`job_id` filterを実装する設計に同意するか。
3. Design Decision D（10章）：CLIがSchedulerDriverのlock・store lockのいずれも取得しないこと、および出力が単一時刻の一貫したsnapshotではなく`list_all()`実行時間幅にわたるnon-atomicなbest-effort readであり（Codex Round 1 Major#2対応）、実行後の新規RECOVERY_REQUIRED発生も、実行中の遷移が結果へ反映されることも、いずれも保証しないことに同意するか。
4. Design Decision F（11章）：CLIが診断情報と既存手順の案内のみを行い、復旧実行・判定・状態変更を一切行わないという境界（Release名を「Diagnostic CLI」とする判断根拠を含む）に同意するか。
5. Roadmap Governance（16章）：Release 6.36を最初のPost-MVP Releaseとしてchange record付きでRoadmap本文へ新設する提案の方針に同意するか（実際の追記はArchitecture承認後に別途実施）。
6. OQ4（19章）：`zero_diff_guard_registry.py`のstandalone guard対応（14章4.、v6.33.0/v6.34.0と同型の機械的帰結として確定的に必要）を、同型の狭い除外編集として実装フェーズで処理することに同意するか。
7. `release_claim()` Suggestionは本Releaseに一切含めず、独立したFast Track候補として今後も保留し続けることに同意するか（2章Out of Scope）。
8. （Round 2で解消・撤回）Round 1版で提起していたR1 Accepted Risk Gateは、8章の全面改訂（mkdirを呼ぶコードパスの構造的排除）により不要となった。

---

## 21. Roadmap / architecture 整合性チェック（報告のみ、doc変更なし）

- `docs/MVP_COMPLETION_ROADMAP.md`に6.36個別節は存在しない（16章）。Forecast章のrange記載とのみ整合。
- `docs/architecture.md`の5925-5927行「Future Extension」記述、`docs/CHANGELOG.md:466`の記述と、本書の目的（`list_recovery_required()`を消費するCLI）は完全に整合している。
- `docs/design/scheduler_driver_duplicate_dispatch_safety_foundation.md` 20章のManual Recovery Procedure（Draft）と、本書11章の案内内容に矛盾は見つからなかった。
- 不整合・要修正事項は見つからなかった。

---

## 22. Architecture Releaseとして開始可能かの判定

本書はCodex `codex-readonly-review`（Codex High）によるRound 1〜5のレビュー（Round 1：NOT APPROVED、Blocking 1／Major 4／Minor 2。Round 2：NOT APPROVED、Blocking 1／Major 2／Minor 3。Round 3：NOT APPROVED、Blocking 1／Major 1／Minor 1。Round 4：NOT APPROVED、Blocking 1／Major 2／Minor 1。**Round 5：APPROVED、Blocking 0／Major 0／Minor 4**）を経て、指摘事項をいずれも改訂で反映した（0章・5章・6章・8章・9章・10章・13章・14章・15章・17章・19章・20章・22章）。Round 5でCodex独立read-only reviewは`VERDICT: APPROVED`（Blocking 0／Major 0）に到達した。残るのはユーザーによるArchitecture Gate Checklist（20章、8項目）の明示的承認のみであり、これが完了するまで実装フェーズには着手しない。

**現時点の判定：NOT READY（Architecture Review自体は完了・APPROVED。ユーザーによるHuman Gate Checklist（20章）承認待ちのため実装は未着手）**
