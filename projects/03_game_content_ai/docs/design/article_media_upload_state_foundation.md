# Release 6.28.0 Article Media Upload State Foundation 設計書（DI-6）

作成日：2026-08-14
作成者：Claude Code（Architecture Design・Architecture Review反映）／Codex（read-only独立Architecture adversarial review、Round 1〜4）／ユーザー（最終承認）
状態：**Architecture Review完了（Approved）。実装は未着手**（本ファイルはArchitecture Designの正式記録であり、`src/`実装・tests・CHANGELOG.md／ROADMAP.md／architecture.md反映は別Releaseフェーズで行う）。
分類：Architecture Release（development_workflow.md 6章）

---

## 1. Project Charter

### 1.1 目的

DI-6（Media Upload Retry／Idempotency Foundation）の実装に向けたArchitecture Design。
`ArticleFeaturedMediaOrchestrator.apply()`（`src/article_featured_media_orchestration/article_featured_media_orchestrator.py:58-74`）はWordPress media
のgenerate→upload→bindを行うが一切永続化しない。WordPress upload成功から
`log_manager.log_article()`（main.py:480）でmedia_idがディスクに書かれるまでの区間
（main.py:446〜480）に何が起きてもmedia_idはどこにも残らず、retry時の重複upload
を構造的に防げない。

本Releaseは、article単位で「upload試行開始」「upload確定成功」のみを記録・照会
できる、Consumer-lessな独立Foundationパッケージ（`src/article_media_upload_state/`）
を新設する。main.py等の既存runtimeへの実配線・重複防止の実際の判断／動作は
本Releaseのscope外とする。

### 1.2 背景

- Release 6.27.0（v6.27.0設計書 §1.2）の時点で、DI-6／DI-7（WordPress Unused
  Media Cleanup）／DI-8（Publish Composition Root）はいずれも「前提インフラ
  未整備」として次候補に留め置かれていた。
- 本Release着手前のread-only調査で、DI-7（WordPress media DELETE）はDI-6
  （idempotency）未整備のため先行不可、DI-8はDI-6と直接依存なし、と判定した。
- DI-6自体の設計段階で、「RetryQueueItemにmedia_idを追加すれば解決」という
  素朴な案は、`RetryQueueItem`（`src/retry_queue/retry_queue_item.py`）が
  run_id粒度である一方、main.pyの1回の実行が複数記事を処理するため
  「1 run_id : N記事」の粒度不一致があり、成立しないことが判明した。
- Architecture Designは4段階のCodex read-only adversarial reviewを経て
  収束した（詳細は8章）。当初案にあった`FAILED` state／`ConfirmedFailureReason`
  Enumは、既存設計書`docs/design/wordpress_media_upload_failure_reason_classification_foundation.md`
  §10.1.1（L-1：「reasonを一過性の証明として扱ってはならない」）と衝突する
  ことがRound 2レビューで判明し、削除した。

### 1.3 Non-Goal（本Releaseで実施しないこと）

- retry-safeなfailure／uncertain semanticsの表現（3.1節参照）
- exactly-once保証（12章のcrash window分析参照）
- main.py・`ArticleFeaturedMediaOrchestrator`・`RetryQueueItem`・
  `WordPressMediaUploader`等、既存productionコードへの実配線・変更
- 重複防止の実際の判断・動作（本Foundationは記録のみ行い、判断は行わない）
- DI-7（WordPress media DELETE）の実装
- reconciliation（crash window C、B/C区別不能性の解消）の実装
- cross-process serialization（lock／CAS）の実装（13章 HWP-1参照）
- article identity lifecycle policyの確定（13章 HWP-2参照）
- diagnostic reason（uncertain outcome reason等）の保持。DI-5 observability
  （`src/image_generation_fallback_policy/image_generation_fallback_policy.py`の
  `extract_safe_reason()`、`src/logger/log_entry.py`の`featured_media_reason`系
  field）が既に同種の診断ラベル記録を担っており、本Foundationでの重複保持は
  不要な複雑性と判断した（3.1節）
- `.env.example`／CHANGELOG.md／ROADMAP.md／architecture.mdの更新（実装Release
  で行う）

---

## 2. Fast Track Checklist該当確認

| 条件 | 該当有無 | 該当する場合の内容 |
|---|---|---|
| Public API変更 | あり（新設） | `src/article_media_upload_state/`を新規追加。既存Public APIへの変更はなし |
| Constructor変更 | なし | 新規packageのみ |
| Composition Root変更 | なし | 既存Composition Rootは無変更・未参照 |
| Layer変更 | なし | 新規独立leaf package。既存layer構造への影響なし |
| Dependency変更 | なし | 標準ライブラリのみに依存する独立leaf package（`retry_queue`と同型の独立性方針） |
| 永続化変更 | あり（新設） | `logs/article_media_upload_state/`配下への新規JSON永続化。既存永続化（`logs/articles/`等）は無変更 |
| Event変更 | なし | |
| 外部I/O変更 | なし | ファイルI/Oのみ。外部API呼び出しなし |

新規Public API・新規永続化を伴うため、development_workflow.md 7章のFast Track
候補条件を満たさず、Architecture Releaseとして扱う。

---

## 3. Architecture Design

### 3.1 なぜ`FAILED`／`ConfirmedFailureReason`／`UncertainOutcomeReason`を持たないか

**`FAILED` / `ConfirmedFailureReason`（削除）**：`WordPressMediaUploadErrorReason`
（`src/wordpress_media/wordpress_media_uploader.py:29-50`）は「観測された構造の
分類」であり「根本原因の分類」ではないと、既存設計書で規範的に確定している
（`docs/design/wordpress_media_upload_failure_reason_classification_foundation.md:1115-1136`）：

> reasonは、失敗が表面化した時点でupload()が構造情報として観測できたもの
> （(a) requests例外の型、(b) HTTPステータスコード、(c) 2xx応答本文が契約を
> 満たさなかったという事実）のいずれかを、固定ラベルへ写像した値である。
> 保証しないこと：reasonと根本原因（root cause）の1対1対応

同文書L-1（同ファイル:1145）はさらに「reasonを一過性の証明として扱っては
ならない」と明示的に禁止している。加えてIL-2（同ファイル:1157）は、認証失敗
がホスティング構成次第で`AUTHENTICATION`ではなく`PERMISSION_DENIED`／
`REQUEST_REJECTED`／`INVALID_RESPONSE`として観測されうることを示しており、
「特定のHTTPステータス群＝WordPress側でmedia未作成が確定」という前提そのもの
がRepository上で反証されている。したがって、retry-safeな「確定失敗」を表現
する`FAILED` state・`ConfirmedFailureReason` Enum・`record_upload_failed()`は
いずれも採用しない。

**`UncertainOutcomeReason`（削除）**：DI-5 observability
（`image_generation_fallback_policy.py`の`extract_safe_reason()`、`log_entry.py`
の`featured_media_reason`系field）が既に同種の診断ラベル記録を別途担っており、
本Foundationでの重複保持は不要な複雑性と判断した。将来、本Foundation固有の
diagnostic metadataが真に必要になれば、review済み`schema_version`変更で追加
する（17章）。

### 3.2 state model

```python
class ArticleMediaUploadState(Enum):
    ATTEMPT_STARTED  = "attempt_started"   # 試行開始。retry-safeを意味しない
    UPLOAD_CONFIRMED = "upload_confirmed"  # 確定成功。valid media_id取得済み。protected terminal state
```

2値のみ。reason系Enumは一切持たない。**`ATTEMPT_STARTED`が持つ唯一の意味は
「試行が開始された」ことであり、「安全にretryしてよい」ことではない。**

### 3.3 配置・命名

新規パッケージ`src/article_media_upload_state/`を作成する。

```
src/article_media_upload_state/
    __init__.py
    article_media_upload_state.py        # ArticleMediaUploadState Enum
    article_media_upload_record.py       # ArticleMediaUploadRecord（frozen dataclass）
    article_media_upload_state_store.py  # ABC
    json_article_media_upload_state_store.py  # atomic write実装
    article_media_upload_state_config.py
    article_media_upload_state_manager.py
    errors.py  # ArticleMediaUploadStateCorruptedError / IOError / ConflictError / TransitionError
```

`retry_queue`（v3.1.0）と同型の「標準ライブラリのみに依存する独立した葉
パッケージ」方針を踏襲する。`NewsItem`・`ArticleData`・`collector`・
`duplicate_filter`・`WordPressMediaUploadErrorReason`のいずれもimportしない。
既存productionコード（main.py・Orchestrator・LogManager・WordPressMediaUploader）
はいずれも無変更・未参照（Consumer-less）。

---

## 4. Public API Contract

```python
class ArticleMediaUploadStateManager:
    def record_upload_started(self, article_identity: str) -> Record: ...
    def record_upload_succeeded(self, article_identity: str, media_id: int) -> Record: ...
    def get_state(self, article_identity: str) -> Record | None: ...
```

3APIのみ。

### 4.1 入口validation（store accessより前にfail-fast）

```python
def _validate_identity(article_identity: str) -> None:
    if type(article_identity) is not str or not article_identity.strip():
        raise ValueError("article_identity must be a non-empty, non-whitespace str")
```

```python
class ArticleMediaUploadStateManager:
    def record_upload_started(self, article_identity: str) -> Record:
        _validate_identity(article_identity)
        existing = self._store.get(article_identity)
        if existing is None:
            record = ArticleMediaUploadRecord(
                article_identity=article_identity,
                state=ArticleMediaUploadState.ATTEMPT_STARTED,
                media_id=None,
                updated_at=_now_utc_iso(),
            )
            self._store.save(record)
            return record
        raise ArticleMediaUploadStateTransitionError(
            f"cannot start a new attempt: existing state is {existing.state.value}"
        )

    def record_upload_succeeded(self, article_identity: str, media_id: int) -> Record:
        _validate_identity(article_identity)
        if type(media_id) is not int or media_id <= 0:
            raise ValueError("media_id must be a positive int (bool rejected)")
        existing = self._store.get(article_identity)
        if existing is None:
            raise ArticleMediaUploadStateTransitionError("no existing attempt to confirm")
        if existing.state is ArticleMediaUploadState.UPLOAD_CONFIRMED:
            if existing.media_id == media_id:
                return existing
            raise ArticleMediaUploadStateConflictError(
                f"media_id conflict: existing={existing.media_id}, new={media_id}"
            )
        record = ArticleMediaUploadRecord(
            article_identity=article_identity,
            state=ArticleMediaUploadState.UPLOAD_CONFIRMED,
            media_id=media_id,
            updated_at=_now_utc_iso(),
        )
        self._store.save(record)
        return record

    def get_state(self, article_identity: str) -> Record | None:
        _validate_identity(article_identity)
        return self._store.get(article_identity)
```

**重要**：`media_id`の`type(media_id) is int and media_id > 0`検証を、
`existing.media_id == media_id`比較の**前**に置くことで、
`record_upload_succeeded(identity, True)`は既存recordの状態に関わらず
`ValueError`で即座に拒否される。Pythonでは`1 == True`が真となるため、この
検証順序を誤ると`__post_init__`（6章）を一度も通過せずstable replayとして
誤受理される経路が生じる（Codex Round 4 M-1、Valid）。

**責務分担**：
- **Managerのvalidation**：Public API入口でのfail-fast境界。呼び出し側の
  誤用を、store accessやRecord構築より前に検出する。
- **Record `__post_init__`**（6章）：Manager外からの直接構築、および
  永続化データのdeserialize復元時の最終防衛。Managerのvalidationをすり抜けた
  経路でも同一Invariantが必ず成立することを保証する唯一の共通強制ポイント。

両者は責務が異なり、どちらか一方だけでは不十分。

### 4.2 transition table

| API | 既存state | 結果 | 備考 |
|---|---|---|---|
| `record_upload_started` | (無) | `ATTEMPT_STARTED`（新規作成） | |
| `record_upload_started` | `ATTEMPT_STARTED` | `ArticleMediaUploadStateTransitionError` | fail-closed（5章） |
| `record_upload_started` | `UPLOAD_CONFIRMED` | `ArticleMediaUploadStateTransitionError` | 保護された終端状態 |
| `record_upload_succeeded` | `ATTEMPT_STARTED` | `UPLOAD_CONFIRMED`（`media_id`確定） | |
| `record_upload_succeeded` | `UPLOAD_CONFIRMED`（同一media_id） | `UPLOAD_CONFIRMED`（stable replay、no-op） | 真の成功再送、誤用ではない |
| `record_upload_succeeded` | `UPLOAD_CONFIRMED`（異なるmedia_id） | `ArticleMediaUploadStateConflictError` | 沈黙上書きしない |
| `record_upload_succeeded` | (無) | `ArticleMediaUploadStateTransitionError` | direct success禁止 |
| `get_state` | 任意 | 変更なし | 副作用なし |

唯一のno-opは「`UPLOAD_CONFIRMED`への同一media_id再確認」のみ。それ以外の
想定外呼び出しはすべて例外として表面化する（silent no-opで誤用を隠さない）。
recovery／reconciliation用途は本Foundationの通常APIに含めず、将来必要になれば
別名の専用APIとして設計する。

---

## 5. ATTEMPT_STARTED再開始Contract（fail-closed）

既存`ATTEMPT_STARTED`はcrash window B（WordPress側にmedia未作成のままcrash）
とC（media作成済みだが未記録のままcrash）を区別できない（12章）。Foundation
は「同一attempt内の重複呼び出し」と「retry/restart」を区別できないため、
`updated_at` refresh目的の再startedも安全上の意味を持たない。

したがって、`ATTEMPT_STARTED`・`UPLOAD_CONFIRMED`いずれの既存recordに対しても
`record_upload_started()`は例外を送出する（no-opにしない、4.2節）。future
consumerは既存recordがある状態で再uploadしてよいかを必ず明示的に判断せざるを
得なくなる（13章 HWP-3）。

---

## 6. Record fields / `__post_init__`

```python
@dataclass(frozen=True)
class ArticleMediaUploadRecord:
    article_identity: str
    state: ArticleMediaUploadState
    media_id: int | None
    updated_at: str  # canonical UTC ISO8601（7章）

    def __post_init__(self) -> None:
        if type(self.article_identity) is not str or not self.article_identity.strip():
            raise ValueError("article_identity must be a non-empty, non-whitespace str")
        if not isinstance(self.state, ArticleMediaUploadState):
            raise ValueError("state must be an ArticleMediaUploadState member")

        if self.state is ArticleMediaUploadState.ATTEMPT_STARTED:
            if self.media_id is not None:
                raise ValueError("ATTEMPT_STARTED requires media_id=None")
        elif self.state is ArticleMediaUploadState.UPLOAD_CONFIRMED:
            if type(self.media_id) is not int or self.media_id <= 0:
                raise ValueError("UPLOAD_CONFIRMED requires a positive int media_id (bool rejected)")

        if not _is_canonical_utc_iso8601(self.updated_at):
            raise ValueError("updated_at must be a canonical UTC ISO8601 str (7章)")
```

既存precedent`ArticleFeaturedMediaCompositionRoot.__post_init__()`
（`src/article_featured_media_composition/article_featured_media_composition_root.py:54-58`、
frozen dataclassでのフィールド整合性検証）を踏襲する。`type(x) is int`比較
（`isinstance`ではない）で`bool`（`int`のサブクラス）を構造的に拒否する
（既存`wordpress_media_uploader.py:246-250`が同種のガードを実装済みの先例）。

---

## 7. timestamp canonical Contract

**生成方式**：`datetime.now(timezone.utc).isoformat()`

canonical UTC（オフセット`+00:00`固定）のtimezone-aware ISO8601文字列のみを
許可する。naive timestamp・非UTC offset・`Z`サフィックスは拒否する。これは
既存Repository precedent（`src/execution_history/execution_history_manager.py:54,75,95,129`
の`datetime.now()`、naive）から**意図的に逸脱する安全側の選択**である。

```python
def _is_canonical_utc_iso8601(value: str) -> bool:
    if type(value) is not str:
        return False
    if not value.endswith("+00:00"):
        return False
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return False
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        return False
    return parsed.isoformat() == value  # round-trip equality
```

`parsed.isoformat() == value`のround-trip equalityにより、
`datetime.fromisoformat()`が受理するがgeneratorが決して生成しない表現
（space separator、generatorと異なるmicrosecond精度表現等）を受理集合から
排除する。「canonical」の名にふさわしく、受理集合をgeneratorの出力集合と
厳密に一致させる。独自parserは導入せず、標準ライブラリの`fromisoformat`／
`isoformat`の対称性のみを利用する。

---

## 8. exact JSON schema / schema_version

```json
{
  "schema_version": 1,
  "article_identity": "https://example.com/news/123",
  "state": "attempt_started",
  "media_id": null,
  "updated_at": "2026-08-14T12:34:56.789012+00:00"
}
```

読み取り側は以下**すべて**を満たさない限り`ArticleMediaUploadStateCorruptedError`
を送出する（fail-closed）：

1. `type(document) is dict`
2. keyが上記5keyと**完全一致**（不足・余剰いずれも拒否）
3. `type(schema_version) is int and schema_version == 1`（`type()`比較のため
   `True`を1として誤受理しない。未知versionはsilent upgradeしない）
4. `type(article_identity) is str`、non-empty/non-whitespace
5. `type(state) is str`であり、`ArticleMediaUploadState`の定義値のいずれかに
   一致（Enum変換前にstr型チェック）
6. `media_id`：`state`が`attempt_started`なら`None`のみ、`upload_confirmed`
   なら`type(media_id) is int and media_id > 0`（bool拒否）
7. `type(updated_at) is str`
8. 上記5-7の値を`ArticleMediaUploadRecord(...)`へ渡し、`__post_init__`
   （6章）を通して最終検証（schema検証とRecord invariantを二重実装しない、
   一元化）

例外メッセージには**persisted rawコンテンツを含めない**（ファイルパスと
検証失敗の種類ラベルのみ）。

---

## 9. identity integrity

`get_state(requested_identity)`は、schema検証・Record構築後、
`record.article_identity == requested_identity`を必須検証する。不一致の
場合は`ArticleMediaUploadStateCorruptedError`を送出する。ファイル名の
SHA-256ハッシュ一致だけをauthorityにしない（ハッシュ衝突・ファイル取り
違え・手動改変等で誤ったarticleのretry判断に使われることを防ぐ）。

---

## 10. article identity Contract

- callerが`normalize_url()`（`src/duplicate_filter.py:11-34`）で正規化した
  文字列をopaque stringとして渡す。本パッケージ自体は中身を解釈しない
  （`duplicate_filter`をimportしない、3.3節の独立性方針）。
- empty / whitespace-onlyは全APIで`ValueError`（4.1節）。
- ファイル名にはSHA-256ハッシュを使用する（URLに含まれる文字がファイル
  システム上安全でない可能性があるため）。
- 同一normalized URLは同一identityとして扱われる。再投稿・更新時に同一
  identityを再利用すべきかの判断（policy）は本Foundation責務外とし、
  将来のwiring Releaseに委譲する（13章 HWP-2）。

---

## 11. Atomic write / filesystem I/O failure Contract

```python
def _save(self, path: Path, record: ArticleMediaUploadRecord) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ArticleMediaUploadStateIOError(
            "failed to create parent directory for state file"
        ) from exc

    payload = json.dumps(_to_schema_dict(record))

    try:
        fd, tmp_path_str = tempfile.mkstemp(
            dir=str(path.parent), prefix=f"{path.name}.", suffix=".tmp"
        )
    except OSError as exc:
        raise ArticleMediaUploadStateIOError(
            "failed to create temporary state file"
        ) from exc

    tmp_path = Path(tmp_path_str)
    try:
        try:
            f = os.fdopen(fd, "w", encoding="utf-8")
        except OSError as exc:
            with contextlib.suppress(OSError):
                os.close(fd)  # fdopen失敗時、raw fdの所有権はfile objectへ
                                # 移っていないため明示close
            raise ArticleMediaUploadStateIOError(
                "failed to open temporary state file"
            ) from exc

        try:
            with f:
                # withブロック終了時のclose()失敗も、write/flush/fsync失敗と
                # 同じexcept OSErrorで捕捉され、同一のIOError Contractへ変換される
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
        except OSError as exc:
            raise ArticleMediaUploadStateIOError(
                f"failed to write temporary state file {tmp_path}"
            ) from exc

        try:
            os.replace(tmp_path, path)
        except OSError as exc:
            raise ArticleMediaUploadStateIOError(
                f"failed to replace state file {path}"
            ) from exc
    except BaseException:
        with contextlib.suppress(OSError):
            tmp_path.unlink(missing_ok=True)  # cleanupはbest-effort。
                                                 # cleanup失敗はprimary failureを上書きしない
        raise
```

- directory creation・`mkstemp`・`fdopen`・write/flush/fsync/close・
  `os.replace`の**すべての段階**で、Public APIから漏れる例外は
  `ArticleMediaUploadStateIOError`に統一される。raw `OSError`がPublic API
  境界を越えることはない
- parent directory作成責務はwrite側（`_save()`）のみが持つ。read側
  （`get()`）はディレクトリ非存在を「未記録」として扱い作成しない
- `os.replace()`失敗・プロセスcrash時のorphan tempファイル残存は許容する
  （実害なし、定期clean-upは本Foundationのscope外）
- **atomicity ≠ complete durability**：本手順が保証するのは「他プロセス
  から見てファイルが書き込み前か書き込み後のいずれかにしか見えない」こと
  のみ。`fsync(file)`はファイル内容の確定に寄与するが、directory entryの
  durability（親ディレクトリのメタデータ確定）までは保証しない。電源断等
  を含む完全durabilityは主張しない
- 例外メッセージにsecret・raw persisted contentを含めない

---

## 12. crash window A〜E

| Window | 内容 | retry時にget_state()で分かること | 重複可能性 | v6.28単体で解決可 |
|---|---|---|---|---|
| A | record前・upload前にcrash | `None` | なし | 可（`record_upload_started()`が正常に新規作成） |
| B | ATTEMPT_STARTED記録後・upload前にcrash | `ATTEMPT_STARTED` | なし（WordPress側に実体なし） | 可（future consumerは`record_upload_started()`を再呼びできず、必ずHWP-3のPolicyに従う） |
| C | upload成功・永続化前にcrash | `ATTEMPT_STARTED`（Bと区別不能） | **あり** | **不可**（reconciliation委譲、HWP-3） |
| D | UPLOAD_CONFIRMED永続化後・bind前にcrash | `UPLOAD_CONFIRMED` | 将来consumerがUPLOAD_CONFIRMEDをduplicate-prevention authorityとして正しく参照する場合、再upload回避に必要な確定情報は存在する（無条件の「重複なし」は主張しない） | 記録は正しく残る |
| E | bind後・後続処理前にcrash | `UPLOAD_CONFIRMED` | 同上 | 記録は正しく残る |

`ATTEMPT_STARTED`はretry-safeを意味しない。B/Cは区別不能のまま。**exactly-once
は保証しない**（1.3節 Non-Goal）。window Cの解消は将来のreconciliation
Foundationへ明示的に委譲する。

---

## 13. Hard Wiring Prerequisites（3本）

いずれも単なるSuggestion／Deferredではなく、**future wiring Releaseの着手
そのものをブロックするblocking condition**として扱う。

### HWP-1 Concurrency

v6.28 package自体はconcurrent-writer safeであることを保証しない。atomic
`os.replace()`はファイル置換自体をatomicにするのみで、read-modify-write
全体のraceを解決しない。cross-process serialization機構（lock／CAS／同等）
がArchitecture Reviewで承認されるまで、本packageをmain.py等のruntimeへ
配線してはならない。最初のwiring Release着手時には、既存Repository
precedent`src/retry_runtime_lock/`（`RetryRuntimeLock`、
`os.open(os.O_CREAT|os.O_EXCL)`によるアトミックなロックファイル取得、
`retry_runtime_lock.py:36-84`、v6.0.0）を調査対象とするが、これはRetry
Runtimeプロセス全体を対象とした単一ロックであり、本Foundationが必要と
する`article_identity`単位の粒度とは異なるため、そのまま流用可能かは
別途検証が必要。

### HWP-2 Identity Lifecycle

`normalize_url()`の将来変更によるidentity drift、同一URLの再投稿、article
更新、`UPLOAD_CONFIRMED`が永続terminal stateであることとの整合、
migration/versioning要否を含むPolicyがArchitecture Reviewで承認される
まで、runtime wiring禁止。

### HWP-3 Unresolved ATTEMPT_STARTED Handling / Reconciliation Policy

`ATTEMPT_STARTED`はcrash window B（WordPress側にmedia未作成）とC（media
作成済みだが未記録）を区別できない。future consumerが`ATTEMPT_STARTED`を
検出した際に、①自動再upload可否、②B/Cをどう扱うか、③reconciliationが
存在しない現状で処理を停止し人間確認を要求するか、を含むPolicyが
Architecture Reviewで承認されるまで、runtime wiring禁止。

---

## 14. corruption / security policy

8〜9章の閉じたschema検証＋identity一致検証によりmalformed JSON・型混入
（bool/int）・unknown schema_version・unknown state・invalid media_id・
unexpected/missing keyをすべてfail-closedで検出する。保持fieldは
`article_identity`（正規化URL）・`state`・`media_id`（int、UPLOAD_CONFIRMED
のみ）・`updated_at`のみ。raw exception・HTTP body・WordPress応答本文・
credential・token等は型システム上構造的に保持不可能。例外メッセージに
persisted raw contentを含めない。idempotency表現：「`record_upload_succeeded()`
の同一media_id再呼び出しのみが安定なno-opであり、それ以外の想定外呼び出し
はすべて例外として表面化する」。

---

## 15. backward compatibility / zero-diff

新規独立パッケージであり`PROTECTED_PATHS`（`tests/zero_diff_guard_registry.py:86-109`）
に含まれない。`retry_queue`初回リリース時の前例を踏襲し、本Releaseでも
`PROTECTED_PATHS`への新規登録・`_SOURCE_CHANGE_CONTRIBUTIONS`への寄与追加は
行わない。既存`src/logger`・`src/outputs`・`src/retry_queue`・
`src/wordpress_media`・`src/retry_runtime_lock`・`main.py`・v6.21.0〜v6.27.0の
既存test本体・historical guard本体はいずれも無変更。

【訂正】当初「`tests/zero_diff_guard_registry.py`も無変更」としていたが、
これは誤りだった（v6.28 Formal Regression実測で判明）。`retry_queue`初回
リリース時点では`zero_diff_guard_registry.py`自体がまだ存在せず
（v6.26.0で新設）、この前例は「registryが無変更で済む」根拠にならない。
`tests/`配下への新規E2E追加は、`RELEASE_ORDER`・`_TEST_CHANGE_CONTRIBUTIONS`
（`tests/zero_diff_guard_registry.py:43-51, 146-193`）による許容集合の対象外
であるため、tracked/untracked/stagedいずれの状態でもv6.21.0〜v6.24.0の
baseline-fixed guard（`NOIMPACT-TESTS-SCOPE`／`NOIMPACT-NO-UNTRACKED-TESTS`）
と、それらを子プロセスとして再検証するv6.26.0／v6.27.0のRUNTIME系assertionが
連鎖的にFAILする。本Releaseは`RELEASE_ORDER`へ`"v6.28.0"`を追記し、
`_TEST_CHANGE_CONTRIBUTIONS`へ新規E2E自身・`zero_diff_guard_registry.py`
自身・（後述のforward-compatibility修正に伴う）`test_e2e_v6_27_0_*.py`
自身の3件をappend-onlyで追加する（`BASELINE_COMMITS`・`PROTECTED_PATHS`・
`_SOURCE_CHANGE_CONTRIBUTIONS`・過去のrecordはいずれも無変更）。
「protected source pathへの新規登録は不要」「`_SOURCE_CHANGE_CONTRIBUTIONS`
への寄与は不要」という判断自体は変わらず正しい（新規パッケージが
`PROTECTED_PATHS`対象外であるため）。

【追加訂正：v6.27.0 historical guardのforward-compatibility修正】
上記の`RELEASE_ORDER`追記の結果、`test_e2e_v6_27_0_*.py`自身が持つ
`REGISTRY-1`／`REGISTRY-2`（「自分がRELEASE_ORDERの末尾である」という
自己参照の完全一致固定）が構造的にFAILすることが実測で判明した。これは
v6.27.0の**機能仕様の変更ではなく**、v6.27.0リリース時点では「自分が最新」
という前提が常に成立していたために表面化しなかった、REGISTRY-9/13と同型の
over-constraintである。`test_e2e_v6_27_0_*.py`のREGISTRY-1/2を、
「v6.27.0がRELEASE_ORDERに存在すること」＋「v6.27.0までのprefixがv6.27.0
リリース時点の期待順序と完全一致すること」という、過去（v6.21.0〜v6.27.0）
の削除・並べ替え・途中挿入は引き続き検知しつつv6.27.0より後へのfuture
release appendは許容するratchet-safe契約へ修正した（単純なmembership判定
への弱体化ではない）。この編集自体がtests/への変更であるため、
`test_e2e_v6_27_0_*.py`自身も`_TEST_CHANGE_CONTRIBUTIONS`へv6.28.0の
contributionとして登録した（v6.28.0の直接test contributionは新規E2E自身・
`zero_diff_guard_registry.py`自身・`test_e2e_v6_27_0_*.py`自身の3件）。

---

## 16. 想定変更ファイル（実装Release時）

新規：`src/article_media_upload_state/__init__.py` / `article_media_upload_state.py`
/ `article_media_upload_record.py` / `article_media_upload_state_store.py`
（ABC）/ `json_article_media_upload_state_store.py` / `article_media_upload_state_config.py`
/ `article_media_upload_state_manager.py` / `errors.py`
（`ArticleMediaUploadStateCorruptedError` / `ArticleMediaUploadStateIOError` /
`ArticleMediaUploadStateConflictError` / `ArticleMediaUploadStateTransitionError`）
/ `tests/test_e2e_v6_28_0_article_media_upload_state_foundation.py`

変更：`tests/zero_diff_guard_registry.py`（`RELEASE_ORDER`へ`"v6.28.0"`追記、
`_TEST_CHANGE_CONTRIBUTIONS`へ3件追記。append-onlyのみ。15章参照）／
`tests/test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py`
（REGISTRY-1/2をratchet-safe契約へforward-compatibility修正。v6.27.0の
機能仕様は無変更。15章参照）

ドキュメントのみ変更（実装Release時）：CHANGELOG.md／ROADMAP.md／architecture.md
無変更：main.py／`src/retry_queue`／`src/article_featured_media*`／
`src/logger`／`src/outputs`／`src/wordpress_media`／`src/retry_runtime_lock`／
v6.21.0〜v6.26.0の既存test本体・historical guard本体（v6.27.0のみ上記の
forward-compatibility修正が例外）
（`PROTECTED_PATHS`・`_SOURCE_CHANGE_CONTRIBUTIONS`・`BASELINE_COMMITS`は
`tests/zero_diff_guard_registry.py`内でも無変更）

---

## 17. test strategy（実装Release時）

- 4.2節のtransition table全組み合わせ（`ArticleMediaUploadStateTransitionError`・
  `ArticleMediaUploadStateConflictError`が正しいケースで送出されることを含む）
- 4.1節：全Public APIへのinvalid identity（非str、空文字、空白のみ）が
  `ValueError`かつstore accessが一切発生しないことの確認。
  `record_upload_succeeded(identity, True)` / `False` / `0` / 負数 / `float`
  / `str`がいずれも`existing`取得前に`ValueError`で拒否されることの確認
  （既存`UPLOAD_CONFIRMED(media_id=1)`に対する`True`渡しケースを明示的に
  テスト）
- 6章：`__post_init__`の全invariant違反拒否（bool media_id、state-field
  不一致、空identity、非canonical timestamp）をManager経由・直接構築の
  両方でテスト
- 8章：closed schema検証（欠落/余剰key・`schema_version`のbool混入拒否・
  未知state文字列・型不一致の各パターン）
- 7章：timestamp検証（naive timestamp拒否、非UTC offset拒否、`Z`サフィックス
  拒否、round-trip equality違反表現の拒否、canonical `+00:00`のみ受理）
- 9章：identity mismatch検証
- 11章：`mkdir`失敗・`mkstemp`失敗・`fdopen`失敗（raw fd leakなし）・
  write/flush/fsync失敗・close失敗・`os.replace`失敗の全パスで
  `ArticleMediaUploadStateIOError`が送出され、raw`OSError`が漏れないこと
  の確認
- concurrencyストレステストは実施しない（HWP-1に基づき対象外）
- Formal Regression（既存baseline全件維持）

---

## 18. Deferred / future

main.py wiring（HWP-1〜3すべてが満たされるまで着手禁止）／DI-7／
reconciliation（window C、HWP-3）／cross-process serialization機構
（HWP-1）／Identity Lifecycle Policy確定（HWP-2）／diagnostic reason
再導入（将来のschema_version変更として、真の消費者要件が生じた時点で
再検討）／`PROTECTED_PATHS`登録

---

## 19. Architecture Review記録

本Architecture Designは、以下の4段階のCodex read-only独立adversarial
reviewを経て収束した。実装は行わず、Architecture本文のみを対象とした
反復レビューである。

| Round | 主な指摘 | 対応 |
|---|---|---|
| Round 1（初回設計時点の内部Architecture Review） | Consumer-less Foundationとしての骨格・crash window分析・persistence方式比較 | `ExecutionHistoryStore`型のStoreパターン採用 |
| Round 2 | B-1 confirmed-failure taxonomyの根拠不足／B-2 Record invariant未強制／B-3 identity整合性未検証／M-1〜M-4（permissive transition、identity lifecycle未Hard化、schema非closed、crash window D/E無条件断定） | `FAILED`/`ConfirmedFailureReason`削除、`__post_init__`導入、identity一致検証追加、strict lifecycle API化、Hard Wiring Prerequisite導入 |
| Round 3 | A-1 ATTEMPT_STARTED再開始の危険性／B-1 uncertain reasonのDI-5重複／C-1 strict schema types不足／C-2 timestamp Contract未定義／D-1 fd leak／D-2 directory/orphan policy未記載 | ATTEMPT_STARTED再開始のfail-closed化、`UncertainOutcomeReason`完全削除（state 2値化、Public API 3つへ縮小）、exact type schema検証、canonical UTC timestamp契約新設、fd leak対策 |
| Round 4（最終ラウンド） | M-1 Public Manager API入口validation欠落（bool/int混同経路）／M-2 filesystem write例外のPublic Contract不統一／m-1 timestamp round-trip equality不足 | Manager入口でのfail-fast validation追加（media_id型検証をexisting比較より前に配置）、filesystem write全段階のIOError統一、timestampのround-trip equality追加 |

**Round 4終了時点の判定**：Blocking 0・Major 0・Minor 0・Suggestion 0。
Round 2〜4で指摘された全項目にregressionなし。**Verdict: Approved**。
追加のCodex adversarial reviewは実施せず、Architecture Review工程を
終了した。

---

## 20. 次のステップ

本設計書はArchitecture Designの正式記録であり、実装（`src/`配下の実コード
作成）・tests作成・CHANGELOG.md／ROADMAP.md／architecture.mdへの反映は、
別途Implementationフェーズとして実施する。HWP-1〜HWP-3（13章）は
Implementationフェーズの対象外（main.py等へのruntime wiring着手条件）
であり、本Foundation自体の実装はこれらの充足を待たずに進めてよい。
