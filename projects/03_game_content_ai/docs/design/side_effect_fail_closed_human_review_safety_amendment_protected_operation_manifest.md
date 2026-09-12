# Architecture Amendment — Protected Operation Manifest
## Release 6.32「Side-Effect Fail-Closed & Human Review Safety」

**Status**: APPROVED（Codex Round 1〜8＝NEEDS_REVISION、いずれも対応済み・Codex Round 9＝NEEDS_REVISION Blocking4／Major3／Minor1、SIMPLIFICATION PIVOT——rebind機構・RetryExecutionLock lease機構を全面撤廃し、`member_run_id`（`WorkflowEngineManager`が生成する既存の一意なuuid4）をmanifest永続化キーへ組み込むIMMUTABLE EXECUTION/MEMBER GENERATION設計へ移行、対応済み・Codex Round 10＝**APPROVED** Blocking0／Major0／Minor1／Suggestions2、非機能的な文書表現の整理のみ実施（architecture semantics変更なし）・Codex Round 11レビュー未実施（ユーザー指示により自動実行しない）・**Human Gate承認済み（実装フェーズ・§18 Implementation Matrix・Final Independent Codex Review Blocking remediationを経て、詳細は§35参照）**）
**Amends**: `docs/design/side_effect_fail_closed_human_review_safety_foundation.md`
**Motivating finding**: Final Release Review中にCodexが指摘し、Claude Codeが独立検証で確認したBlocking finding——`RetryExecutor.execute()`（同期terminalization）・`RetryLineageManager._reconcile_all_locked()`（crash/restart reconciliation）のいずれも`SideEffectSafetyClassifier.classify()`／`resolve_final_disposition()`を呼んでおらず、6.31時代のstep-onlyな`decide_disposition()`／`disposition_from_categories()`のみでdispositionを確定している。Approved Architecture §22.1c（L2812）はこの配線を断定的な義務として明記しており、In Scope。

**このAmendmentが解決する未解決の実装詳細**: Approved Architecture §29 Architecture Classification Register 項目8「`operation_instance_key`（article_identity）の具体的な導出方法と既存ロジックとの整合」。

---

## 0. 問題の再定式化

`classify()`が受け取る`operations: list[ProtectedOperationContext]`の各要素は、`(operation_kind, effect_site, operation_instance_key)`の3要素組である。既存の呼び出し箇所A/B/Cでの`operation_instance_key`の実際の値は：

| 呼び出し箇所 | operation_kind | effect_site | operation_instance_key |
|---|---|---|---|
| A（`wordpress_output.py:102`） | WORDPRESS_DRAFT_CREATION | NEWS_STEP | `article.slug` |
| B（`main.py:270`） | MEDIA_UPLOAD | NEWS_STEP | `article.slug` |
| C（`ai_publish_service.py:227`） | WORDPRESS_DRAFT_CREATION | PUBLISH_STEP | `review.article_id` |

この値は`RetryExecutor.execute()`／`_reconcile_all_locked()`が参照できる既存データ構造のいずれにも存在しない：

- `WorkflowEngineResult`／`WorkflowEngineStepResult`（`src/workflow_engine/workflow_engine_result.py`）：step名・成功可否・skip理由のみ。記事識別子なし。
- `StepExecutionRecord`（`src/execution_history/step_execution_record.py`）：同上。加えてstep粒度（NEWS/REVIEW/PUBLISHの3値のみ）であり、NEWS stepが複数記事を処理する場合の記事単位識別子を原理的に格納できない。
- `AgentResult`（`src/ai/agent_result.py`）：`WorkflowResult`（v1.20.0系、別物）への参照のみ。

推測・slug再生成・ambient metadata復元は明示的に禁止されているため、正規の値を**新しいdurable経路**で伝播する必要がある。

---

## 1. 代替案比較

### 案A：WorkflowEngineResult / StepExecutionRecordへidentity伝播

**構成**：`WorkflowEngineStepResult`・`StepExecutionRecord`へ`article_identities: list[str]`相当のフィールドを追加し、記事処理の都度追記する。

| 評価軸 | 評価 |
|---|---|
| crash after external I/O before result completion | **不可**。`WorkflowEngineResult`はin-memoryかつ`.run()`の戻り値としてのみ存在し、`.run()`内でのクラッシュ時は一度も構築されない。crash/restart時の一次情報源は`_reconcile_all_locked()`が読む`StepExecutionRecord`（durable）のみだが、これもstep単位の粒度しか持たない。 |
| restart recoverability | **不可**（上記と同根）。NEWS stepが記事Aの処理中にクラッシュした場合、StepExecutionRecordの1レコードに記事A・B・C…の識別子を後から追記する経路は現状存在せず、新設するにはexecution_history自体のschema変更（`action_taken`/`skip_category`と同型の追加）が必要——それ自体が新Architecture判断。 |
| exact identity authority | 不可（値の出所が不明） |
| duplicate prevention | 不可（識別子を復元できないため判定不能） |
| store closed-set invariantsへの影響 | 影響なし（既存storeに触れない） |
| concurrency/locking | 該当なし |
| ACK ordering | 該当なし（そもそも到達しない） |
| schema/versioning | execution_history package（Release 6.31で`action_taken`/`skip_category`を追加した実績あり）へさらなる破壊的変更が必要 |
| migration/legacy zero-diff | 旧レコード読込時の後方互換処理が必要になり、影響範囲が拡大 |
| minimality | **最悪**。NEWS stepの記事バッチ処理という既存の粒度不一致を解消するには、WorkflowEngineStep自体を記事単位へ分解するか、StepExecutionRecordを1:N構造へ変更するかのいずれかが必要で、いずれも6.32のスコープを大きく超える |

**結論：棄却**（Codex Round 1指摘により表現を訂正：「原理的に不可能」ではなく「達成には追加のschema変更——durable child-record構造の新設等——が必要であり、これ自体が新Architecture判断に該当し、案Cより広い変更範囲になる」）。`StepExecutionRecord`・`WorkflowEngineStepResult`は現状どちらも記事識別子フィールドを持たず、これを追加するには1:N構造への変更が必要で、案Cの「新規store1つの追加」よりも侵襲性が高い。

### 案B：既存side-effect storesへenumerate/list API追加

**構成**：`WordPressDraftStateStore`・`MediaUploadSafetyCoordinator`（の背後にある各store）へ`list_for_attempt(root_run_id, attempt_ordinal) -> list[...]`を追加する。

| 評価軸 | 評価 |
|---|---|
| crash after external I/O before result completion | 部分的に可能（既にATTEMPTED/CONFIRMEDへ到達した分は見える） |
| restart recoverability | **不完全**（Codex Round 1指摘に対する補足：既存のexternal I/O順序契約（write-ahead ACK→I/O）自体は、write-ahead未到達の操作について重複I/Oを発生させないため、それ自体は安全である。問題はduplicate preventionではなく**identity discovery**にある——`operation_instance_key`（記事slug／article_id）を確定するための唯一の手がかりが、案Bでは「既にstoreへ書き込まれた」operationのみであり、「これから確認すべきoperationの完全な集合」を決定する手段がない。案Cのmanifestは、この「確認すべき集合」自体を明示的に宣言する——existing storeの単なるenumerateでは代替できない、本質的に異なる情報を提供する） |
| exact identity authority | 部分的（現存するevidenceの範囲のみ） |
| duplicate prevention | 既存のcreate系APIの重複検出機構は維持される（変更不要） |
| store closed-set invariantsへの影響 | **抵触**（Codex Round 1指摘により訂正：この「3操作のみ」というclosed API契約は`WordPressDraftStateStore`固有のもの——§9.3——であり、`MediaUploadSafetyCoordinator`は既に4つのrecord_*メソッド＋`get()`の計5メソッドを公開しているため、両storeへ一律に「3メソッドのみ」と述べたのは不正確だった。正確な論点は、**いずれのstoreも現状enumerate系APIを一切持たない**という点であり、新規追加はどちらのstoreにとっても契約の拡張になる。特に`WordPressDraftStateStore`はユーザー制約で名指しされたstoreであり、ここへのenumerate追加は避けるべき） |
| concurrency/locking | enumerate自体はlock-freeで実装可能だが、file名がidentityのSHA256ハッシュであるため、対象を絞ったenumerateには非効率なフルスキャンが必要（O(N)、Nは全履歴の全operation数） |
| ACK ordering | 影響なし |
| schema/versioning | 既存schemaへの変更は不要（新APIのみ） |
| migration/legacy zero-diff | 影響なし |
| minimality | 新規storeを作らずに済む点は魅力的だが、上記の「未着手操作を表現できない」という原理的欠陥が致命的 |

**結論：棄却**。「期待されていたが一度も試行されなかった」ケースを表現できないという原理的欠陥に加え、closed API契約への抵触というユーザー制約違反が確定的。

### 案C：専用durable Protected Operation Manifest／Registry（採用）

呼び出し箇所A/B/Cが、自分自身の既存write-ahead呼び出し（`record_attempted()`等）よりも**さらに前**に、新設のManifest storeへ自分自身のidentityをdurable登録する。terminalization/reconciliationは、既存の安全store群ではなく、このManifestを「このattemptで何を確認すべきか」の一次情報源として使う。

| 評価軸 | 評価 |
|---|---|
| crash after external I/O before result completion | **可**。Manifest登録が既存write-aheadよりも先行するため、既存write-ahead自体が持つ「crashしても既にATTEMPTED相当」という保証をそのまま継承しつつ、さらに早い段階（record_attempted自体が未着手の段階）までカバー範囲を広げる |
| restart recoverability | **可**。Manifestにidentityが存在し、かつ対応する安全store側にrecordが存在しない場合は、既存の`_classify_one()`が持つ「record非存在＝CONTRACT_VIOLATION」ロジックがそのまま機能する（12.2節の既存規定を変更しない） |
| exact identity authority | **可**。値は呼び出し箇所自身が確定させた本物の`article.slug`／`review.article_id`そのものであり、推測・復元を一切含まない |
| duplicate prevention | Manifestへの登録はidentity集合への冪等追加として定義（同一identityの再登録は無害なno-op）。実際の副作用の重複防止は既存の安全store群（`allow_absent_only=True`等）が引き続き担い、責務を混同しない |
| store closed-set invariantsへの影響 | **なし**。既存store（WordPressDraftStateStore・MediaUploadSafetyCoordinator）のAPIは一切変更しない。Manifestは全く新しい独立コンポーネントであり、自分自身のclosed APIを新規に定義する（既存契約を壊すという制約には抵触しない） |
| concurrency/locking | identity-scoped commit-aware lockと同型のパターンを、`(root_run_id, attempt_ordinal)`スコープのlockとして新規に踏襲する（既存の`_run_with_commit_aware_lock()`をそのまま再利用） |
| ACK ordering | Manifest登録の失敗はcall site自身の即時失敗（I/O未実施のままraise）とする——既存のwrite-ahead失敗時の挙動と同一のfail-closed posture |
| schema/versioning | 新規schema。`_SCHEMA_VERSION`によるバージョニングは既存store群と同型の慣例を踏襲する |
| migration/legacy zero-diff | legacy lineage（`side_effect_contract_version is None`）では一切使用しない（既存のprotected/legacy分岐へ自然に統合） |
| minimality | 新規store 1つの追加で済み、既存の記事バッチ処理・既存API・既存schemaのいずれにも変更を要求しない。触れるファイルは呼び出し箇所A/B/C（6.32で既に変更対象）＋新規manifestパッケージ＋RetryExecutor／RetryLineageManagerに限定される |

**結論：採用**。

**Codex Round 2 Major指摘への補足（B/D棄却の安全性論証を精緻化、Round 3 Major指摘によりさらに訂正）**：Round 2は「案C自身も、呼び出し箇所がmanifestへentryを登録する前のわずかな窓を持つ点はB/Dと同じではないか」と指摘した。Round 3は、この論点を「窓を検出できるか」と述べたRound 2時点の訂正自体が過大な主張であったことを指摘した——**個別operation登録前の窓（§4.2 Step 1到達前）は、案Cにおいても検出不可能**であり、「genuinely 0件の正常attempt」と区別がつかない（いずれもmanifestが空のまま観測される）。

正確な安全性プロパティは以下のとおりである：

- 案B：「一度も試行されなかった操作」はstore側に一切の痕跡を残しようがなく、**expected setそのものを構成する手段がない**——identity discoveryが原理的に不可能（§1、既述）。
- 案D：既存write-aheadと同時書き込みのため、案Cが§4.1で導入した「admission成立＝manifest存在」という**admissionレベルの**検出可能な保証を持たない。
- 案C（§4.1改訂後）：
  - **admissionレベルの窓**（manifest作成そのものの成否）は、§9.3のcombination tableで全状態を列挙し、いずれの帰結も安全側（`CLAIMED`のまま孤児化して既存の手動lock復旧手順を経て回収されるか、`EXECUTION_STARTED`到達後は必ずmanifestが存在する）に収束することを**証明できる**——これは案B/Dのいずれも持たない性質である。
  - **個別operationレベルの窓**（§4.2 Step 1到達前の、特定の記事に対する処理未着手）は、案Cにおいても検出不可能だが、これは**外部I/Oより前に登録が必ず先行する**という既存の順序契約（Invariant #1の直接的帰結）により、**duplicate外部I/Oのリスクという観点では無害**である——この窓に落ちた操作は、外部I/Oが一切発生していないことがexternal I/O順序契約自体によって保証されるため、次のattemptで通常のworkflow step再実行機構により安全に再処理される（side-effect-safety機構の対象外として扱われることそのものが安全）。

3案の違いは「窓が検出可能か」ではなく、**「admissionレベルで、manifestという情報源自体の存在をdurableに保証できるか」**（案Cのみ持つ性質）、および**「未検出の窓が、副作用重複リスクという観点で無害であることを構造的に説明できるか」**（案Cは外部I/O順序契約により説明できるが、案B/Dは"expected set"自体を構成できないため、この議論の土台にすら立てない）という2点である。

### 案D（比較検討・棄却）：既存write-ahead managers内部への自動index化

**構成**：`WordPressDraftStateStore.create_attempted()`・`MediaUploadSafetyCoordinator.record_prepared()`等、既存の4メソッドが、自分自身の既存durable writeの副作用として、共有per-attempt indexへも自動的に書き込む。呼び出し箇所A/B/Cが新規APIを追加で呼ぶ必要がない。

**棄却理由**：この方式は「crash-before-first-existing-write-ahead」という、案Cが解決しようとしている本質的な空白窓を閉じられない——indexへの書き込みが既存write-aheadと**同時**に行われる以上、「操作Xを行うと決定した」時点から「`record_attempted()`自身のdurable writeが完了する」時点までの間にcrashした場合、indexにも既存storeにも一切痕跡が残らない、という問題がそのまま残る。加えて、2つの独立したclosed-API store（`WordPressDraftStateStore`・`MediaUploadSafetyCoordinator`）が、ドキュメント化されていない3つ目のstoreへの書き込みという隠れた副作用を持つことになり、closed API契約の趣旨（公開契約に書かれた以上のことをしない）にも反する。後述する「admission時点での空manifest作成」（§4）の方がこの空白窓をより早い段階で閉じられるため、案Dは不要。

---

## 2. Record Schema — **Codex Round 9 Blocking#1〜4指摘によりIMMUTABLE EXECUTION/MEMBER GENERATION設計へ全面改訂**

新規パッケージ `src/protected_operation_manifest/` を新設する（既存の`side_effect_safety`・`wordpress_draft_state`と同格の独立パッケージ。PROTECTED_PATHS対象外、v6.29.0/v6.31.0の新規独立パッケージと同型の扱い）。

```python
@dataclass(frozen=True)
class ManifestEntry:
    operation_kind: ProtectedSideEffectKind
    effect_site: SideEffectSite
    operation_instance_key: str
    registered_at: str  # ISO8601 UTC

@dataclass(frozen=True)
class ProtectedOperationManifestRecord:
    root_run_id: str
    attempt_ordinal: int
    member_run_id: str
    entries: "tuple[ManifestEntry, ...]"
    contract_version: int  # _SCHEMA_VERSION
```

**永続化キー（Round 9で`member_run_id`をキーへ追加）**：`{base_dir}/{sha256(f"{root_run_id}:{attempt_ordinal}:{member_run_id}")}.json`。Round 8までのキー（`root_run_id`＋`attempt_ordinal`の2要素のみ、`member_run_id`はpayload内フィールド）は、同一attempt_ordinalに対する複数回のexecution試行（crash→再claim→再execution）が**同一ファイルを上書き**することを前提としており、これが「孤児manifestのrebind」という概念自体の発生源だった。Round 9はこの前提を撤回し、`member_run_id`をキーの一部とすることで、**各execution試行が必ず独立したファイルを持つ**設計へ変更する。

### Round 9 §1: member_run_idの4性質の確認（read-only investigation）

ユーザー指示（Round 9 §1）に従い、`member_run_id`が以下4点を満たすかを実コード読み取りのみで確認した：

1. **各executionで一意か**：`WorkflowEngineManager._generate_run_id()`（`src/workflow_engine/workflow_engine_manager.py:186-187`）が`uuid.uuid4().hex`を`.run()`呼び出しごとに新規生成する。`RetryExecutor.execute()`の1回の呼び出しは`self._engine.run(...)`を1回だけ呼ぶため（`retry_executor.py:200-207`）、1回のexecution試行＝1つの新しい`uuid4`である。**確認済み：一意**。
2. **mark_execution_started()時点で確定しているか**：`WorkflowEngineExecutor.run()`（`workflow_engine_executor.py:165`）が`run_id = context.run_id`をpost-admission hook呼び出し（`context.post_admission_hook(run_id)`、`:204`）より**先に**ローカル変数として確定させる。`RetryExecutor`のhookクロージャ（`retry_executor.py:185-188`）はこの`run_id`をそのまま`self._lineage.mark_execution_started(lineage.root_run_id, run_id)`へ渡す。**確認済み：mark_execution_started()呼び出し時点で既に確定済みの値として渡される**。
3. **sync/restart双方でdurable lineageからauthoritatively取得可能か**：①`mark_execution_started()`が同一の`run_id`を`record.latest_run_id`へdurableに保存する（`retry_lineage_manager.py:421`）。②sync終端側（`WorkflowEngineResult.run_id`、`workflow_engine_executor.py:246`・`:414`）は同一のローカル変数`run_id`をそのまま返すため、`RetryExecutor.execute()`が受け取る`engine_result.run_id`は①と同一値である。③restart/reconciliation側（`_reconcile_all_locked()`）は`record.latest_run_id`（①でdurable化された同一値）を読む——既存6.31ロジック、変更なし。**確認済み：sync・restart双方が同一の値を、それぞれ独立した経路（戻り値／durable lineage）から一致して取得できる**。
4. **A/B/Cへ既にlosslessに伝播可能か**：`_complete_side_effect_execution_context()`（`workflow_engine_executor.py:90-107`）が、同じローカル変数`run_id`を`member_run_id=run_id`として`RetryLineageProtectedExecutionContext`へ組み込み、呼び出し箇所A/B/Cへ既存の6.32配線（変更なし）で到達させる。**確認済み：追加の伝播経路を新設する必要はない**。

4点すべてが成立するため、**案A（`member_run_id`ベースのimmutable per-execution manifest）を採用する**。案B（`manifest_id`を独立発行する代替案）は不要——`member_run_id`自体が、案Bが提供しようとしていた性質（executionごとに一意で、admission時点で確定し、durable lineageから両経路で権威的に再取得できるidentity）をすでに構造的に満たしている。新しいtoken/identity種別を追加しない、という既存のAmendment全体の方針（§9.5、既存フィールド再利用の原則）とも一致する。

`root_run_id`・`attempt_ordinal`・`member_run_id`の3要素キーの帰結：**同一キーへの2度目の書き込みは、`member_run_id`が正しく一意である限り、正常経路では構造的に発生し得ない**（`create_for_attempt()`が「既存レコードがあるので上書き/rebindする」という分岐を持つ必要自体がなくなる——詳細は§4.1・§8）。既存の5要素identity（`SideEffectOperationIdentity`）とは異なる、attempt-execution粒度の別schemaであることを明示する。

---

## 3. Authority / Ownership — **Codex Round 7 Minor#1指摘によりwriter authorityを明示分離、Round 9でrebind writerを廃止**

Manifestへの書き込み権限は、**書き込む対象フィールドに応じて2種類のwriterへ明確に分離される**（closed-set）。Round 9で`_rebind_orphaned_attempt()`を廃止したため、Step 0 writerは**新規作成のみ**を行う：

| Writer | 対象メソッド | 書き込み可能なフィールド | 呼び出し元 |
|---|---|---|---|
| **Step 0 admission metadata writer（新規作成専用、Round 9でrebind廃止）** | `create_for_attempt()` | `root_run_id`・`attempt_ordinal`・`member_run_id`（新規作成時のみ、以後一切変更なし。`entries`は`()`で初期化されるのみ） | `RetryLineageManager.mark_execution_started()`側（§9.5.1、owner_token authority検証済みの文脈からのみ。ただし本Amendment全体としては§9.5.3のfacade設計が構造的にこれを保証する） |
| **Step 1 operation-entry writer** | `register()` | `entries`（追記のみ、既存フィールドは変更しない） | 呼び出し箇所A/B/Cの実装コード（`wordpress_output.py`・`main.py`のmedia upload orchestration・`ai_publish_service.py`）。いずれもRetryLineageProtectedExecutionContext時のみ書き込む（legacy分岐では一切触れない） |

**いずれのwriterも、他方のwriterが専有するフィールドを変更しない**（`register()`は`member_run_id`を変更せず、`create_for_attempt()`は`entries`を（初期化以外）変更しない）。**レコード作成後、`member_run_id`フィールド自体が変更されることは金輪際ない**（Round 9、rebind writerの廃止により、この不変条件はメソッドレベルで構造的に保証される——「rebindしない」という規約ではなく、rebindする手段自体が存在しない）。

Manifestの読み取り権限を持つのは、`RetryExecutor.execute()`（同期路）・`RetryLineageManager._reconcile_all_locked()`（crash/restart路）のみ。

Manifest自体は、既存の`SideEffectSafetyClassifier`・`WordPressDraftStateStore`・`MediaUploadSafetyCoordinator`のいずれにも依存せず、それらからも依存されない（一方向：呼び出し箇所→Manifest、terminalization→Manifest、いずれも片方向読み書き）。`RetryLineageManager`からmanifestへの依存（Step 0 writer経由）は例外的に許容する——これは既存の一方向性原則が想定する「安全store間の対等な独立性」ではなく、「adminssion authorityを持つ唯一の主体が、その配下のmetadataを書き込む」という異なる関係であり、§9.5.3で比較した案C（manifest storeがlineageに依存する方向）とは**逆方向**であることに注意（lineageがmanifestに依存するのは許容、manifestがlineageに依存するのは§3・§9.5.3の原則により禁止、のまま）。

---

## 4. Create Timing（登録タイミング）— **Codex Round 1指摘により全面改訂**

登録は2段階に分かれる。

### 4.1 Step 0（新設）：admission時点での空Manifest作成 — **Codex Round 2 Blocking指摘により順序を反転**

**Round 2でのCodex指摘（Blocking）**：Round 1修正版は「`self._store.save(record)`（lineage phase→EXECUTION_STARTED）→ `create_for_attempt()`」の順で書いており、後者が失敗した場合に「claimを解放する」と主張していた。しかし`release_claim()`（`src/retry_lineage/retry_lineage_manager.py:388-393`）は`record.phase != RetryLineagePhase.CLAIMED`の場合に無条件で`False`を返す実装であり、既にphaseが`EXECUTION_STARTED`へ遷移済みの状態では機能しない。結果として、manifest作成失敗時に「claimを解放してREADY_ELIGIBLEへ戻す」という主張が事実に反し、attemptが消費されたまま`EXECUTION_STARTED`に取り残される、という新しい欠陥を作り込んでいた。

**改訂**：**manifest作成をlineage phase遷移よりも先に行う**よう順序を反転する。さらにRound 5対応として、`claim()`が既にdurableに生成している**既存の`owner_token`フィールド**（`retry_lineage_record.py:179`）をexact match検証する（§9.5で全面改訂・詳述）。

```python
def mark_execution_started(self, root_run_id: str, run_id: str, owner_token: str) -> bool:
    with self._store_lock():
        record = self._store.get(root_run_id)
        if record is None or not _verify_owner_authority(record, owner_token):
            # §9.5.1：4段階authority check（non-empty str・非null・phase==CLAIMED・
            # exact match）。missing/empty/malformed/mismatchはすべてfail-closed。
            return False
        if record.side_effect_contract_version is not None:
            attempt_no = record.attempt_scopes[-1].attempt_no if record.attempt_scopes else record.next_attempt_ordinal
            # Round 9：create_for_attempt()はowner_tokenを受け取らない（manifest自体は
            # authorityを保持・検証しない、§8）。run_id（=member_run_id）は§2確認済みの
            # とおりWorkflowEngineManagerが生成した一意なuuid4であり、この呼び出し自体が
            # authority-verified文脈（上のcheckに成功済み）からのみ行われる。
            manifest_ok = self._manifest.create_for_attempt(root_run_id, attempt_no, run_id)
            # 戻り値False＝通常のACK失敗（I/O失敗等）。同一キーへの既存レコード発見
            # （§2確認済みのとおり正常経路では構造的に起こり得ない）はcatchしない
            # ProtectedOperationManifestContractViolationErrorとして伝播させ、既存の
            # fail-fast契約（RetryExecutor.execute()のexcept Exception:節）へ委ねる——
            # 「rebindして復旧を試みる」という分岐自体が存在しない（Round 9、Blocking#1〜4）。
            if not manifest_ok:
                return False  # レコードは一切変更していない。durable lineage phaseはCLAIMEDのまま。
                              # 呼び出し元のrelease_claim(root_run_id, owner_token)が正しく機能する。
        # ...既存の記録更新（phase/latest_run_id/attempt_count/membership/transition_history）...
        return self._store.save(record)
```

この順序であれば、`mark_execution_started()`が`False`を返す場合、**durable lineage phase**は**常に**`CLAIMED`のまま変化していない（既存の事前チェックと同じ不変条件——「ackがFalseならphase遷移は一切発生していない」——が回復される。in-memoryで取得した`record`オブジェクト自体が一時的に変更される可能性と、durable（ファイルへ書き込まれた）stateとは区別する——後者のみが安全性の根拠である）。既存の`RetryExecutor.execute()`側の`hook_ack_state["acknowledged"] is False`分岐（`retry_executor.py:217`）が呼ぶ`release_claim()`は、この不変条件のもとで正しく機能する。

**孤児manifestの扱い（Round 9で全面簡素化：再利用・rebindを一切行わない）**：manifest作成成功後・lineage save失敗前にcrashした場合（§9.3行3）、当該execution試行に対応する`(root_run_id, attempt_ordinal, member_run_id)`キーのmanifestレコードが作成済みのまま、durable lineageの`record.latest_run_id`はこの`member_run_id`を一度も指さない（lineage saveが未完了のため）——このmanifestは**永久に参照されない孤児として残り続ける**。同じlineageが§9.3行1・行3のrecovery chainを経て再claim・再実行された場合、`WorkflowEngineManager.run()`が**新しい**`uuid4`（新しい`member_run_id`）を生成する（§2 Round 9確認済み）ため、`create_for_attempt()`は**新しいキー**に対して呼ばれ、古い孤児manifestとは一切衝突しない。孤児manifestの再利用・rebind・cleanupのいずれも行わない（§17、既存store群の「明示的なretention機構を持たない」という既存の一貫性と整合）——**rebind authorityという概念自体が本Amendmentから削除された**（Round 9 Blocking#1〜4）。

**「manifestが存在しない」状態の到達可能性**：この改訂により、`_reconcile_all_locked()`が処理する`record.phase == EXECUTION_STARTED`のlineageについては、「manifestは必ず存在する」という主張が、Round 1版より狭いが正しいクラッシュ窓の範囲で成立する（残存する窓は§9.3で明示的に扱う）。`_reconcile_all_locked()`が処理するのは`record.phase == EXECUTION_STARTED`のlineageのみ（`retry_lineage_manager.py:663`）であり、admission未完了（`CLAIMED`のまま）のlineageは別経路（既存のphase==CLAIMED orphan回収、`retry_lineage_manager.py:693`以降）で扱われ、本Amendmentの分類ロジックには到達しない。

### 4.2 Step 1（既存踏襲）：各operationの個別登録

各呼び出し箇所は、**自分自身の既存write-ahead呼び出し（`record_attempted()`／`create_attempted()`／`record_not_applicable()`等）の直前**に、Step 0で作成済みのManifestレコードへ自分自身のentryを追記登録する：

```
[Step 0] admission時点でManifestレコードをentries=()で作成（durable ACK、mark_execution_started()に統合）
  → [Step 1] 各呼び出し箇所が自分自身のentryをManifestへ追記（durable ACK）
    → 既存の record_attempted() / create_attempted() / record_not_applicable()（durable ACK）
      → 外部I/O（WordPress POST / media upload）
```

外部I/Oより前という既存の不変条件（Invariant #1）は、Manifest登録がさらに手前に挿入されるだけなので、そのまま維持される。

---

## 5. Durability / ACK Contract

- 既存store群と同一のatomic write契約（tempfile → fsync → os.replace）を踏襲する。
- **Step 0（admission時の空Manifest作成）**：失敗した場合、`mark_execution_started()`自体がfalseを返し、admission全体をfail-closedに倒す（§4.1）。以後Step 1・呼び出し箇所A/B/C・外部I/Oのいずれも実行されない。
- **Step 1（個別operationの登録）**：失敗（I/O error）はcall site自身の即時例外送出とし、外部I/Oへは一切進まない（fail-closed、既存write-ahead失敗時と同一posture）。
- Manifest登録自体（Step 0・Step 1のいずれも）はACK Determinism（Commit-Aware Lock Helper、§9.9.4）を適用する。durable ACK（tempfile置換完了）後の後続処理失敗（lock解放失敗等）は、登録の成功を覆さない。

---

## 6. Duplicate / Conflict Semantics — **Codex Round 3 Major指摘により§4.1・§17との矛盾を解消、Round 9でrebind関連を全面削除**

- **同一identityの重複登録**（`register()`）：冪等no-op（既存entriesに同一の`(operation_kind, effect_site, operation_instance_key)`が既に存在する場合、新しいentryを追加しない。重複防止責務は既存の安全store群が引き続き担う）。
- **member_run_idの不一致**（`register()`）：登録時に指定された`member_run_id`が、既存レコードの`member_run_id`と異なる場合は`ProtectedOperationManifestContractViolationError`を送出する（既存store群のidentity/member_run_id不一致検出と同型）。
- **`create_for_attempt()`の役割（Round 9で新規作成専用として確定、rebind機能を完全削除）**：永続化キーが`(root_run_id, attempt_ordinal, member_run_id)`の3要素になったこと（§2）により、**正常経路では同一キーへの2回目の`create_for_attempt()`呼び出しは構造的に発生し得ない**（`member_run_id`は毎回新しいuuid4であるため）。ゆえに「既存レコードが見つかった場合の役割分離」という論点自体が不要になった——`create_for_attempt()`が万一（実装バグ・uuid衝突等）同一キーの既存レコードを発見した場合は、常に`ProtectedOperationManifestContractViolationError`を送出し、**rebind・上書き・復旧のいずれも一切試みず**、そのまま呼び出し元へ伝播させfail-closedとする（既存のfail-fast契約、`RetryExecutor.execute()`の`except Exception:`節へ委ねる）。旧`_rebind_orphaned_attempt()`メソッド・旧`ProtectedOperationManifestAlreadyExistsError`例外は本Amendmentから完全に削除した（§8・§9.5.3）。
- **不明なoperation_kind／effect_site**（deserialize時にclosed set外の値）：`ProtectedOperationManifestContractViolationError`を送出する（既存store群のenum検証と同型）。
- **破損レコード**（JSON parse失敗・schema不正）：`ProtectedOperationManifestContractViolationError`を送出する（真のfilesystem I/O failureは別途`ProtectedOperationManifestIOError`として区別する——既存の`WordPressDraftStateIOError`/`*CorruptedError`分離と同型、本Release自身が先に確立したproduction defect fix #2のパターンをそのまま踏襲）。

---

## 7. Lock Identity

`(root_run_id, attempt_ordinal)`スコープの identity-scoped lock（`{base_dir}/.locks/{sha256(f"{root_run_id}:{attempt_ordinal}")}.lock`）。既存の`_run_with_commit_aware_lock()`をそのまま再利用し、`identity`引数には`None`を渡す（診断ログの`operation_kind`/`effect_site`は複数operationにまたがるため単一値を持てず、既存コードが`identity is None`を正しく処理する分岐に委ねる）。

---

## 8. Read / Enumeration API — **Codex Round 1指摘により改訂、Round 8 Minor#2によりhierarchy整理、Round 9でrebind関連APIを完全削除**

**Exception hierarchyの設計方針**：「create時のcontrol-flow signal」と「read時のread/corruption/I/O failure」を、**別々のcatch domain**として明確に分離する方針（Round 8）自体は維持するが、Round 9で`create_for_attempt()`がrebind機能を持たない新規作成専用APIになったことにより、**create専用のcontrol-flow signal（`AlreadyExistsError`）自体が不要になった**——正常経路で同一キーへの重複作成が構造的に起こり得ない（§2・§6）ため、万一発生した場合は他の破損検出と同じ`ContractViolationError`として一律fail-closedに扱えばよい。terminalization（§10・§11）は引き続き`ProtectedOperationManifestReadError`のみをcatchする。

```python
class ProtectedOperationManifestError(Exception):
    """パッケージ全体の共通祖先（分類目的のみ。catchには通常使わない）。"""


class ProtectedOperationManifestReadError(ProtectedOperationManifestError):
    """list_for_attempt()（読み取り経路）が送出しうる例外の共通基底。
    terminalization（§10・§11）はこれをcatchする。"""

class ProtectedOperationManifestNotFoundError(ProtectedOperationManifestReadError):
    """レコードが存在しない。admissionが正しく完了していれば本来あり得ない状態
    （§4.1・§9）——検出された場合は実装バグまたは想定外の破損として扱う。"""

class ProtectedOperationManifestContractViolationError(ProtectedOperationManifestReadError):
    """schema不正・member_run_id不一致・不明なenum値等の破損。**Round 9追加**：
    `create_for_attempt()`が同一キー（`root_run_id`・`attempt_ordinal`・`member_run_id`
    の3要素、§2）に対する既存レコードを発見した場合（正常経路では構造的に
    発生し得ない、§2・§6）にも、この例外を送出する——create専用の別exception
    （旧`AlreadyExistsError`）は設けない。create_for_attempt()の呼び出し元は
    この例外をcatchせず、既存のfail-fast契約へ伝播させる（Round 9、rebind
    フォールバックという分岐自体を削除）。"""

class ProtectedOperationManifestIOError(ProtectedOperationManifestReadError):
    """真のfilesystem I/O failure。"""


class ProtectedOperationManifestStore(ABC):
    def create_for_attempt(
        self, root_run_id: str, attempt_ordinal: int, member_run_id: str,
    ) -> bool:
        """Step 0・新規作成専用（§4.1）。entries=()の空レコードをdurableに
        作成する。**Round 9でrebind機能・owner_token引数を完全削除**——
        `member_run_id`が毎回新しいuuid4であること（§2 Round 9確認済み）により、
        正常経路で既存レコードと衝突することは構造的にない。万一既存レコードを
        発見した場合（well-formed・破損問わず）は常にProtectedOperationManifestContractViolationError
        を送出する（fail-closed、呼び出し元はcatchしない、rebindは一切試みない）。
        本メソッド自体はauthorityを検証しない（dumb writer）——呼び出し元
        （`RetryLineageManager.mark_execution_started()`）が直前に`_verify_owner_authority()`
        （§9.5.1）へ成功していることを前提とする。このメソッドへの参照は、
        composition root（§21）のinterface scopingにより`RetryLineageManager`
        以外へ配線されない（§9.5.3）。"""

    def register(
        self, root_run_id: str, attempt_ordinal: int, member_run_id: str,
        entry: ManifestEntry,
    ) -> RegisterResult:
        """Step 1（§4.2）。既存レコード（Step 0で作成済みのはず）へentryを冪等追記する。
        レコードが存在しない場合はProtectedOperationManifestNotFoundErrorを送出する
        （Step 0が失敗していればadmission自体が失敗しているはずであり、本来到達しない
        経路——防御的検証）。"""

    def list_for_attempt(
        self, root_run_id: str, attempt_ordinal: int, expected_member_run_id: str,
    ) -> "tuple[ManifestEntry, ...]":
        """read専用・lock-free（既存store群のget()と同一posture、§27.3）。
        レコード非存在時はProtectedOperationManifestNotFoundErrorを送出する
        （空tupleを返さない——§9参照、これが本Amendmentの核心的な訂正点）。
        レコードは存在するがentriesが空の場合のみ、空tupleを正常に返す。"""
```

---

## 9. Expected-Operation Completeness Check（Missing / Corrupt Manifest Classification）— **Codex Round 1 Blocking指摘により全面改訂**

### 9.0 Round 1でのCodex指摘（Blocking）

初版は「`list_for_attempt()`が空tupleを返す」を「レコード自体が存在しない」場合と「レコードは存在するがentries登録0件」の場合の**両方**に割り当て、いずれも安全（NOT_APPLICABLE）として扱っていた。Codex Independent Architecture Reviewはこれを正しくBlockingとして指摘した：

> a nonexistent manifest and a genuinely empty manifest are collapsed into the same safe empty tuple — omission of registration, wrong manifest path, wiring defects, or lost manifest state can silently produce `NOT_APPLICABLE`

これは既存**Invariant #6**（reconciliationに「marker absence=safe」defaultを置かない）および**Invariant #18**（No Automatic Repair：矛盾検出時は常にCONTRACT_VIOLATION、推測補完なし）と直接矛盾する。初版のInvariant #41提案（§19）も同じ誤りを踏襲しており、撤回する。

### 9.1 改訂後の設計：「存在」と「空」を構造的に分離する

§4.1（admission時点での空Manifest作成）により、以下が**durableに保証**される：

> `_reconcile_all_locked()`／`RetryExecutor.execute()`の同期路が処理する時点（record.phase == EXECUTION_STARTED、または同期路でengine_result.run_idが確定した時点）では、Manifestレコードは**必ず存在する**（admission自体が空Manifest作成の成否と一体化しているため）。

したがって、この時点で`list_for_attempt()`が`ProtectedOperationManifestNotFoundError`を送出するという事態は、**正常経路では論理的に到達不可能**であり、到達した場合は実装バグ・想定外の破損（例：Manifest storeのファイルが外部要因で削除された等）を意味する。ゆえに、初版のような「安全側の推定」ではなく、Invariant #6・#18が要求するとおり、**無条件にCONTRACT_VIOLATION相当（HRR）として扱う**——これはもはや「manifest absenceをsafeと推定する」設計ではなく、「manifest absenceは（到達しうる限り）常にunsafe」という、既存Invariantと完全に整合した設計になっている。

分類は以下の3ケースに整理される：

| `list_for_attempt()`の結果 | 意味 | 扱い |
|---|---|---|
| 正常return、`entries`が非空 | Step 0成功＋Step 1で1件以上登録済み | 各entryを`SideEffectSafetyClassifier.classify()`へ渡す（通常経路） |
| 正常return、`entries=()`（空） | Step 0成功、Step 1が一度も呼ばれなかった＝**このattemptでは保護対象operationが1件も発生しなかった**（例：NEWS stepが0件の候補記事だった正常系） | `operations=[]`→既存の`SideEffectSafetyReport.worst_case()`vacuous-case規定（`entries`が空ならNOT_APPLICABLE、`side_effect_safety_category.py:52-58`）がそのまま適用され、HRRを発火しない |
| `ProtectedOperationManifestError`（`NotFoundError`／`ContractViolationError`／`IOError`のいずれも共通基底でcatch） | Step 0が完了していない、またはレコードが破損・読み取り不能 | **無条件にHUMAN_REVIEW_REQUIRED**（3種の例外を区別せず一律に扱う。Major指摘#1「IOErrorが未catchのため経路によっては例外がそのまま伝播しdispositionが不定になる」への対応でもある） |

### 9.2 「正常runを恒常的にHRRへ落とさない」ことの証明（改訂版）

NEWS stepが0件の候補記事しか持たなかった通常運用では：
1. admission（`mark_execution_started()`）が成功し、空のManifestレコードがdurableに作成される（§4.1）。
2. 呼び出し箇所A/B/Cはいずれも発火しない（記事が0件のため、そもそもループ本体に入らない）。
3. `list_for_attempt()`は正常returnで`entries=()`を返す（表の2行目、レコードは存在する）。
4. `worst_case()`は既存実装のままNOT_APPLICABLEを返し、HRRは発火しない。

この経路は「レコードが存在しない」ケース（表の3行目）を一切経由しないため、Invariant #6・#18との矛盾は生じない。逆に、admission自体が何らかの理由で失敗した場合は、呼び出し箇所A/B/Cのいずれも実行されない（§4.1）ため、「保護対象操作が実行されたのにManifestが存在しない」という状態そのものが構造的に作れない。

**個別operationレベルの残存窓についての補足（Codex Round 3指摘、§1参照）**：admission成立後・Step 1（個別operation登録）到達前に特定の記事の処理が中断した場合、その記事のentryはmanifestへ一切現れない。この状態は「genuinely 0件」と**観測上区別がつかない**（vacuous-safeとして扱われる）。これは「検出できるから安全」なのではなく、**外部I/Oより前に登録が必ず先行するという既存の順序契約（Invariant #1）により、この窓に落ちた操作では外部I/Oが一切発生していないことが構造的に保証される**ため安全である、という点を明確にしておく（§1参照、Round 2時点の「検出可能性」という表現は過大な主張だった。complete detectabilityは主張しない）。

この論証が成立するための前提は以下の3点であり、いずれも§18のtest matrixで直接証明する（前提として仮定するだけでなく検証する）：
1. 呼び出し箇所A/B/Cすべてにおいて、Manifest registrationが既存write-ahead呼び出しより先に完了する（§18 test#2）。
2. これは既存のexternal I/O順序契約（write-ahead ACK確認→外部I/O、Invariant #1）と矛盾しない——Manifest登録はこの既存順序のさらに手前に挿入されるだけである（§4.2）。
3. 上記2点により、Step 1未到達の操作については外部I/Oが一切発生していないことが構造的に保証される（推測ではなく、順序契約からの論理的帰結）。

### 9.2a `mark_execution_started()`臨界区間のlock構造 — **Codex Round 5 Major#1指摘により新設、Round 9でOR matrixを削除・B matrixの帰結を全面簡素化**

**Round 5での指摘**：「`RetryExecutionLock`だけ復旧すればよい」という記述は不正確。`mark_execution_started()`の臨界区間では、複数の独立したlockが入れ子になっており、crashのタイミングによって残存するlockの組み合わせが異なる。

**実コード確認済みのlock nesting構造**：

1. `RetryExecutionLock`（`retry_manager.py:429-431`、`retry()`呼び出し全体を通じて保持、既存6.31）
2. → `RetryLineageStoreLock`（`_store_lock()`、`mark_execution_started()`の`with self._store_lock():`区間のみ、既存6.31。`retry_lineage_store_lock.py`のdocstringで「RetryExecutionLock → RetryLineageStoreLockの単一のネスト順序のみ」と明記されているLock Ordering契約どおり）
3. → **Manifest attempt lock**（本Amendment新設、§7。`create_for_attempt()`実行中のみ、上記2つのさらに内側にネストする）

いずれも同一の設計慣例（`os.open(..., O_CREAT|O_EXCL)`、staleness自動判定なし、PIDは診断目的のみ）に従う——1と2は`retry_lineage_store_lock.py`・`retry_execution_lock.py`のdocstringで確認済みの既存6.31仕様、3は本Amendmentが同じ慣例を踏襲する新設lock。

**scope（Round 9でOR matrix自体を削除）**：永続化キーへ`member_run_id`を組み込んだ結果（§2）、`create_for_attempt()`が既存レコードと衝突する経路（Round 8までの「孤児rebind sub-path」）は正常系で構造的に発生し得なくなった。したがって、以下のB0〜B6が**唯一の**crash境界表であり、Codex Round 7・8が要求した「orphan rebind sub-path固有のmatrix（旧§9.2b、OR0〜OR4）」は**この設計変更により対象自体が消滅したため削除した**（B matrixとOR matrixを分離する、という要求ではなく、OR matrixが扱っていた状況そのものが本Amendmentからなくなった、という関係——旧Round 7 Major#2・Round 8 Major#3/#4は本改訂により解消済み）。

**crash境界ごとの残存lock/file/durable record matrix**：

| 境界 | 説明 | 残存し得るlock | durable lineage state | durable manifest state |
|---|---|---|---|---|
| B0 | `mark_execution_started()`呼び出し前（`claim()`直後〜hook呼び出しまで） | RetryExecutionLockのみ | `CLAIMED`（claim()由来） | 非存在（このexecution試行のキーに対応するレコードはまだない） |
| B1 | `with self._store_lock():`進入直後〜`create_for_attempt()`呼び出し前 | RetryExecutionLock + RetryLineageStoreLock | `CLAIMED`（変化なし） | 非存在（同上） |
| B2 | `create_for_attempt()`内、Manifest attempt lock取得後〜atomic write完了前 | RetryExecutionLock + RetryLineageStoreLock + **Manifest attempt lock** | `CLAIMED`（変化なし） | 未完了（非存在のまま、atomic replace未到達） |
| B3 | Manifest atomic write完了後〜Manifest attempt lock解放前 | RetryExecutionLock + RetryLineageStoreLock + **Manifest attempt lock** | `CLAIMED`（変化なし） | **新規作成済み**（entries=()、このexecution試行の`member_run_id`キーで確定） |
| B4 | Manifest attempt lock解放後〜`self._store.save(record)`完了前 | RetryExecutionLock + RetryLineageStoreLock | `CLAIMED`（変化なし） | 作成済み（**durable lineageからは未参照**——`record.latest_run_id`がこの`member_run_id`を指す前にcrashしたため） |
| B5 | `self._store.save(record)`完了後〜`with`ブロック終了（`_store_lock()`解放）前 | RetryExecutionLock + RetryLineageStoreLock | `EXECUTION_STARTED`（**成功済み**、`record.latest_run_id`がこのmanifestの`member_run_id`を指す） | 作成済み・参照済み |
| B6 | `with`ブロック正常終了後（`RetryLineageStoreLock`解放済み） | RetryExecutionLockのみ | `EXECUTION_STARTED` | 作成済み・参照済み |

**B0・B1・B2・B3・B4**（durable lineageが`CLAIMED`のまま）は、後述する§9.3のrecovery chainの対象。**ただしB0のみRetryLineageStoreLockを保持しない**（`with self._store_lock():`へ進入する前の境界であるため）——B1〜B4は「RetryExecutionLockに加え、RetryLineageStoreLockも残存し得る」、B2・B3では**Manifest attempt lockも同時に残存し得る**。

**B2〜B4で作成されたmanifest（Round 9、rebind廃止による帰結の一元化）**：これらの境界でcrashした場合、当該manifestは**durable lineageから一度も参照されないまま、永久に孤児として残る**（§4.1）。再claim・再実行時、`WorkflowEngineManager`が新しい`member_run_id`（新しいuuid4）を生成するため、次のexecution試行は**必ず異なるキー**に対して`create_for_attempt()`を呼ぶ——古い孤児manifestと衝突することも、それを再利用・rebindすることもない。孤児manifestのcleanup機構は新設しない（§17、既存store群との整合）。

**B5**（durable lineageは既に`EXECUTION_STARTED`へ成功済みだが、RetryLineageStoreLockがまだ解放されていない状態でcrash）は新しい観察点である：この場合、lineageのdurable stateは既に安全（manifestも存在し、§9.1の表が適用可能）だが、**RetryLineageStoreLockファイルが残存する**。これは後続の`mark_terminal()`・`release_claim()`等、`_store_lock()`を必要とする**あらゆる**操作を、このlockが手動復旧されるまでブロックする（`RetryLineageStoreLockError`、5秒timeout後）。これも既存6.31から存在するRetryLineageStoreLockの仕様の直接的帰結であり、本Amendmentが新規に持ち込むものではないが、recovery chainの記述に含める必要がある。

**`RetryExecutionLock`と`RetryLineageStoreLock`の伝播挙動の非対称性（Codex Round 6 Major#4指摘への対応として実コード確認）**：
- `reconcile_all()`（公開API、`retry_lineage_manager.py:647-658`）は`RetryExecutionLockBusyError`を**内部でcatchし**、`ReconcileSummary(skipped=True, reason="execution lock busy: ...")`という**通常の戻り値**として呼び出し元へ返す（例外として外部へ伝播しない）。`RetryManager.retry()`（`retry_manager.py:429-440`）も同様に`RetryExecutionLockBusyError`を内部でcatchし`RetryResult(outcome=SKIPPED, ...)`を返す。
- 一方、`RetryLineageStoreLockError`（`RetryLineageStoreLock.acquire()`が5秒timeout後に送出）を**catchする箇所はコード全体に存在しない**（`retry_lineage_manager.py`のimport文でも`RetryExecutionLockBusyError`のみがcatch対象としてimportされている）。したがって、`_reconcile_all_locked()`内のCLAIMED orphan回収（本Amendmentでは変更しない既存6.31の内部処理、§9.5.2a）がこの例外を送出した場合、`reconcile_all()`の`with RetryExecutionLock(...):`ブロックを（`RetryExecutionLock`自体は正常に解放されつつ）**生の例外として突き抜けて呼び出し元へ伝播する**。

この非対称性はRelease 6.31から存在する既存の挙動であり、本Amendmentは変更しない。recovery chain・test matrixの記述はこの非対称性を正確に反映する必要がある（§9.3・§18 test#22で対応）。

**手動lock復旧の前提条件（Codex Round 9 §4指摘により明記）**：残存lock（`RetryExecutionLock`・`RetryLineageStoreLock`・Manifest attempt lockのいずれも）の手動削除は、**旧holder processが実際に終了していることを人間が確認した後にのみ**行う既存の運用手順である（6.31由来、9.3.3・9.4章の既存運用ドキュメントの前提をここでも明示する）。**生存中の旧holder processが存在する状態でlockファイルを手動削除することは、正常なrecovery scenarioとして扱わない**——この場合、旧holderと新しいclaimant/reconciliationが同一のdurable stateへ同時に書き込む可能性があり、既存のlock機構自体の前提（single-flight）を人間の操作が壊すことになる。本Amendmentはこの既存運用前提を変更しない。

### 9.3 残存crash窓の明示的なCombination Table — **Codex Round 2 Blocking指摘への対応、Round 9でrebind関連の帰結を削除**

Round 2は「2つの独立して原子的なファイル（lineage store・manifest store）にまたがる論理的operationは、それ自体atomicではない」という一般的批判を提示した。これは正しい——真のcross-store transactionはこのRelease全体を通じて一度も導入されておらず（既存Invariant #16が明記するとおり）、本Amendmentもこれを新設しない。したがって、2つのdurable writeの間には必ず何らかのcrash窓が残る。重要なのは、この窓を**ゼロにする**ことではなく、既存の`MediaUploadSafetyCoordinator`の9.9.7節 Cross-Store Combination Table（18通り）と同型の手法で、**本節が対象とする範囲（manifest createとlineage saveのdurable result combinations）を明示的に列挙し、その範囲について安全側の帰結を証明する**ことである。

§4.1改訂後（manifest作成→lineage save の順）における、`(manifest作成, lineage save)`の状態空間：

| # | manifest作成 | lineage save | 到達するphase | 帰結 |
|---|---|---|---|---|
| 1（§9.2a B0/B1に対応） | 未着手（crash） | 未着手 | `CLAIMED`のまま | 正確なrecovery chainは：①lineageは`CLAIMED`のまま、②crash境界がB0なら`RetryExecutionLock`のみ、B1なら**`RetryExecutionLock`と`RetryLineageStoreLock`の両方**が残存し得る（§9.2a matrix参照）。③既存の運用手順（6.31由来、9.3.3・9.4章、旧holder process終了確認が前提）に従い人間が**残存する全てのlockファイル**を手動削除する（`RetryExecutionLock`のみでは不十分な場合がある）。④その後の`reconcile_all()`呼び出し自体は、`RetryExecutionLock`が正常に取得できれば（`RetryExecutionLockBusyError`は`reconcile_all()`内部でcatchされ`ReconcileSummary(skipped=True)`という通常の戻り値に変換される——例外として外部へは伝播しない、§9.2a）成功し、`_reconcile_all_locked()`実行時、既存のCLAIMED orphan回収ロジック（`retry_lineage_manager.py:693-707`、本Amendmentでは変更しない、§9.5.2a）が、このlineageを`list_all()`で検出し解放する。⑤この解放処理自体も`_store_lock()`（`RetryLineageStoreLock`）を新たに取得するため、③でこのlockが復旧されていなければ、ここで`RetryLineageStoreLockError`が**catchされずに`reconcile_all()`呼び出し元まで生の例外として伝播する**（§9.2a、`RetryExecutionLockBusyError`との非対称性）——この場合、人間は追加でこの例外を観測し、`RetryLineageStoreLock`の手動復旧を行った上で`reconcile_all()`を再試行する必要がある。⑥両lockが復旧済みであれば解放成功により`READY_ELIGIBLE`へ遷移。⑦以後の`claim()`呼び出しがこのlineageを正常に取得できる。この7段階のchainのうち①②④⑤⑥⑦は**Release 6.31から変更のない既存メカニズム**、③（手動lock復旧）はRelease 6.31から存在する既存の運用手順を、対象となり得るlockの種類について正確に適用する必要があることを明記したのみである。本Amendmentは一切のlock機構を変更しない。安全。 |
| 2 | 失敗（`ProtectedOperationManifestError`） | 未着手（`mark_execution_started()`がFalseを返す） | `CLAIMED`のまま | 呼び出し元が`release_claim()`で正しくREADY_ELIGIBLEへ戻す（§4.1で解消済み）。安全（プロセス生存、lockは正常解放される）。 |
| 3（§9.2a B2/B3/B4に対応） | 成功（durable） | 未着手（crash） | `CLAIMED`のまま（manifestは作成済みだが孤児） | **行1と同型のrecovery chainに従うが、残存し得るlockの種類が境界により異なる**：crashがB2（Manifest write未完了）なら`RetryExecutionLock`＋`RetryLineageStoreLock`＋**Manifest attempt lock**の3つ全てが残存し得る。B3（Manifest write完了済み、lock未解放）も同様に3つ全て。B4（Manifest attempt lock解放済み、lineage save未完了）なら`RetryExecutionLock`＋`RetryLineageStoreLock`の2つ。既存の手動復旧手順は、**残存する可能性のある3種のlockすべてを対象に含める**必要がある（§9.2a matrix参照）。**lockが全て解放され、CLAIMED orphanがREADY_ELIGIBLEへ回収された後、当該manifestは永久に孤児のまま残る**（Round 9、rebind廃止）——再claim・再実行時は新しい`member_run_id`で新しいmanifestが作られるのみであり、この孤児への参照・再利用は一切発生しない。 |
| 4 | 成功（durable） | 成功（durable） | `EXECUTION_STARTED` | Manifestが確実に存在する状態でterminalization/reconciliationに到達する。§9.1の表が適用される。安全。 |
| 5（Codex Round 3 Major指摘により追加、Round 4 Major#3指摘により4点を明示分離） | 成功（durable） | **明示的に`False`を返す**（クラッシュではなく、通常のfilesystem書き込み失敗等。プロセスは生存） | `CLAIMED`のまま（durable、`_store.save()`はatomic replaceのため未完了時は旧内容のまま。既存lineage storeのACK Determinism contract——durable writeが完了しない限りdurable stateは変化しない、という既存の保証そのものが根拠であり、「atomic replaceだから」という一般論のみを根拠にしない） | 以下の4点を明確に区別する：<br>(1) **durable lineage phase**：`CLAIMED`のまま（安全側、fail-closed）。<br>(2) **`RetryExecutor`側の挙動**：既存の`hook_ack_state["acknowledged"] is False`分岐（`retry_executor.py:217`）が制御を受け取り`release_claim()`を呼ぶが、既存コード（Release 6.31から変更なし）は`release_claim()`自身の戻り値をcheckせず、`RetryResult.reason`は無条件に「claim released back to READY_ELIGIBLE」と報告する——これは**自動的な成功扱いではなく、既存の診断精度に関する制約**である。<br>(3) **安全性への影響**：`release_claim()`自体が失敗した場合でも、durable lineage phaseは`CLAIMED`のまま変化しない（fail-closed、durable stateは(1)のとおり安全側を維持する）ため、diagnostic messageの不正確さは安全性そのものを損なわない。<br>(4) **本Amendmentのscope**：この既存diagnostic gap（`release_claim()`の戻り値未チェック）自体の修正は、6.31由来の既存productionコード（`retry_executor.py`の既存分岐）への変更を要し、本Amendmentのscope外とする——本AmendmentはこのgapがRound 3で指摘された新シナリオ（manifest作成成功後のlineage save失敗）にも同様に及ぶことを明記するに留める。 |

行3が、Round 2が指摘した「manifest作成後・lineage save前のcrash」に対応する。この場合、lineageのphaseは`CLAIMED`のまま変化していないため、**`_reconcile_all_locked()`のterminalizationロジック（§11）はこのlineageに一切到達しない**——到達するのは既存のphase==CLAIMED orphan回収ロジック（`retry_lineage_manager.py:693`以降、本Amendmentでは変更しない）のみである。したがって、Round 2 Blocking「manifest absent かつ EXECUTION_STARTED」という状態は、この5通りのいずれにも出現しない（行1〜3・行5はいずれも`CLAIMED`のまま、行4は必ずmanifestが存在する）。

### 9.4 `monitor_status == RUNNING`早期continueとの相互作用（Codex Round 2指摘・スコープ整理）

Round 2は、`_reconcile_all_locked()`の既存コード（`retry_lineage_manager.py:668-669`、6.31時代からの既存ロジック、`if monitor_record.monitor_status == WorkflowMonitorStatus.RUNNING: continue`）が、monitor recordが恒久的に`RUNNING`のまま更新されないケース（プロセスが実行中に完全にクラッシュし、terminal statusが一度も書き込まれない場合）で、本Amendmentの新しいclassify()/manifest判定ロジックへ**到達する前に**reconciliationがスキップし続けてしまう可能性を指摘した。

**スコープの整理**：この「monitor recordが恒久的にRUNNINGのまま更新されない」という状態は、**side-effect安全機構とは無関係に、Release 6.31から存在する既存のRetry Runtime crash-recovery設計の特性**である——本Amendmentが新設した`classify()`/manifest判定ロジックの前段（既存の`if monitor_record is None: continue`・`if ... RUNNING: continue`という既存2行）に到達する前でreconciliationが停止する点は、本Amendmentの変更前後で同一である（6.31時代の`decide_disposition()`も同じくこの2行を通過しなければ実行されない）。**本Amendmentはこの既存の潜在的ギャップを悪化させも改善させもしない**——manifest判定ロジックが「到達すれば正しく機能する」ことと、「到達自体をRelease 6.31から保証していない」ことは別の関心事である。

この既存ギャップ自体（stale RUNNING状態からの回復）の解消は、本Amendmentのスコープ外（Release 6.32のOut of Scope、§20参照）とする。ただし、Formal Regression・Release Reviewの記録として、この既存ギャップの存在を透明性のため明記する。

### 9.5 owner_tokenによるAdmission Authority — **Codex Round 4 Major#2により新設、Round 5 Major#2により全面改訂（owner_token採用）、Round 9でrebind関連の節題を除去**

**Round 9での位置づけの変化**：本節はもともと「孤児manifestのrebind可否」の根拠として`owner_token`を導入した（§9.5、旧題）。Round 9でrebind機構自体を削除した結果（§2・§4.1）、`owner_token`の役割は**admission（`mark_execution_started()`）自体のlive authority検証**に純化される——rebindの可否判定という用途はもはや存在しない。以下の`owner_token`発見の経緯・§9.5.1（4段階check）・§9.5.2（owner-authorized release）は、この純化されたadmission authorityとしてそのまま維持する。

**Round 4での指摘（歴史的経緯）**：「`entries == empty`であることだけを理由に、異なる`member_run_id`への再bindを許可する」という初版の規則は、「emptyだからorphanだったはず」という**未検証の推論**に依存しており、authoritativeな根拠がなかった（この規則自体はRound 9で完全に削除された——§2のimmutable per-execution key設計により、rebindという操作自体が不要になったため）。

**Round 4での対応（案A：CLAIMED phase + lock + caller discipline）は、Round 5独立レビューにより「authorityとして不十分」と判定された。** 呼び出し規約（module-private、caller disciplineに依存）は、コード変更・将来のrefactoringに対して脆弱であり、durable dataによる検証可能な証明になっていなかった。

**Round 5での再調査（read-only）**：既存`RetryLineageRecord`のschemaを確認した結果、**`owner_token`という既存フィールドが既に存在する**ことを確認した：

- `retry_lineage_record.py:179`：`owner_token: str | None`（既存フィールド、durable、`to_dict()`/`from_dict()`で永続化される）。
- `retry_lineage_manager.py:370`：`claim()`が`record.owner_token = uuid.uuid4().hex`を生成し、phase遷移（`CLAIMED`へ）と**同一のdurable write**（`self._store.save(record)`）で永続化する。
- `retry_lineage_manager.py:397`：`release_claim()`が`record.owner_token = None`へクリアする（同じくphase遷移と同一のdurable write）。
- **ただし、`ClaimResult`（`retry_lineage_results.py:32-37`）は現状`owner_token`を呼び出し元へ返していない**（`acknowledged`・`reason`・`attempt_no`・`correlation_id`・`steps_to_execute`のみ）。`mark_execution_started()`も現状owner_tokenを受け取らず、検証しない。

この`owner_token`は「現在のclaimを一意に識別する、durableな既存フィールド」であり、**正確にユーザーのPreferred directionが求める性質を満たす**。新規token/schemaの追加ではなく、**既存フィールドの検証経路を新設する**（「既存fieldだけで安全に認証できるなら新tokenを増やさない」を字義通り満たす）。

### 9.5.1 owner_token非null性の厳密化 — **Codex Round 6 Major#1指摘により新設**

**Round 6での指摘**：Round 5の`if record.owner_token != owner_token: return False`は、両辺が`None`の場合（caller側owner_tokenが未設定、かつdurable owner_tokenも`None`）に**通過してしまう**——`None == None`はPythonで`True`であるため、このcheckだけでは「未claim状態」同士が誤って一致認定される。

**採用する厳密なauthority check（4段階、いずれか1つでも失敗すればfail-closed）**：

```python
def _verify_owner_authority(record: "RetryLineageRecord", owner_token: str) -> bool:
    """4段階のauthority check。いずれか1つでも失敗すればFalse（fail-closed）。
    None同士の比較で通過することを禁止する（Codex Round 6 Major#1）。"""
    if not owner_token or not isinstance(owner_token, str):
        return False  # (1) caller owner_tokenがnon-empty strであること
    if not record.owner_token or not isinstance(record.owner_token, str):
        return False  # (2) durable record.owner_tokenがnon-empty strであること
    if record.phase != RetryLineagePhase.CLAIMED:
        return False  # (3) phase == CLAIMED
    if record.owner_token != owner_token:
        return False  # (4) caller token == durable token（exact match）
    return True
```

`mark_execution_started()`（§4.1）・後述の`release_claim()`（§9.5.2）のいずれも、この共通ヘルパーを経由する。missing（`None`）・empty文字列（`""`）・malformed（str以外の型）のいずれも、明示的にfail-closedとして扱う。

**`ClaimResult.owner_token`の契約**：`claim()`がACK=True（`acknowledged=True`）を返す場合、`ClaimResult.owner_token`は**常にnon-empty strである**ことを契約として明記する（`claim()`は`uuid.uuid4().hex`を生成するため、実装上`None`や空文字列になることは元々ない——本節はこの既存の実質的保証を、呼び出し元が依拠してよい明文化されたcontractへ格上げする）。`acknowledged=False`の場合、`owner_token`は意味を持たない（`None`のままでよい）。

**必須テストケース（§18 test#18へ統合）**：
- caller側owner_tokenが`None` → reject。
- durable側`record.owner_token`が`None`（未claim状態） → reject。
- caller側owner_tokenが空文字列`""` → reject。
- caller/durable両方とも値を持つが不一致 → reject。
- caller/durable完全一致（両方non-empty str）のみ許可。

### 9.5.2 Release Authorityの二層分離 — **Codex Round 6 Major#2指摘により新設（最重要）**

**Round 6での指摘**：既存の`release_claim(root_run_id) -> bool`（`retry_lineage_manager.py:388-406`）はowner authorityを一切検証しないため、**stale caller（既にorphan化・再claimされ、もはや正当な所有者ではないはずの旧claimに由来する処理経路）が、新しいclaimのCLAIMED状態を誤って解除できてしまう**。一方、`_reconcile_all_locked()`のCLAIMED orphan回収（`retry_lineage_manager.py:702-707`）は、live ownerではなくreconciliation自体の権限（`RetryExecutionLock`のグローバル排他性）に基づくadministrative recoveryであり、これにowner_tokenを要求すると**正当な回収そのものができなくなる**（回収対象は定義上、誰もowner_tokenを保持していないクラッシュ由来のorphanである）。したがって、release authorityを**用途の異なる2つの操作へ明示的に分離する**。

**採用するAPI形状**（比較した2案のうち、既存`release_claim()`呼び出し元への影響が最小である案1を採用）：

```python
def release_claim(self, root_run_id: str, expected_owner_token: str) -> bool:
    """OWNER-AUTHORIZED RELEASE。live claimant（RetryExecutor等）が自分自身の
    claimを手放す場合専用。§9.5.1の4段階authority checkに失敗したら、
    （mismatch・stale・missingのいずれであっても）絶対にreleaseしない。"""
    with self._store_lock():
        record = self._store.get(root_run_id)
        if record is None or not _verify_owner_authority(record, expected_owner_token):
            return False
        record.phase = RetryLineagePhase.READY_ELIGIBLE
        record.owner_token = None
        # ...既存の記録更新（transition_history等）...
        return self._store.save(record)
```

**RECONCILIATION ORPHAN RELEASEの詳細は§9.5.2aで定義する（Round 9で全面簡素化：lease機構を撤回し、既存6.31のRetryExecutionLock単独の信頼モデルへ回帰）。**

### 9.5.2a Reconciliation Orphan Release — **Codex Round 8 Blocking#1で新設したlease機構をRound 9 §3・§4指摘により撤回、既存6.31設計へ回帰**

**Round 9での指摘（撤回の理由）**：Round 8はreadable bearer lease（`RetryExecutionLock`の内容を読めれば誰でも提示できる文字列）をsecurity authorityとして扱ったが、これは真の暗号学的な証明ではなく、**「`RetryExecutionLock`のファイル内容を読める」という条件を「`RetryExecutionLock`を保持している」という条件の代用にしていただけ**であり、それ自体が既存の6.31設計（`RetryExecutionLock`保有＝reconciliation実行権）が最初から持っていた信頼モデルを、複雑な形で再実装したに過ぎなかった。ユーザーの指摘どおり、readable leaseをauthorityとして扱う設計そのものを撤回する。

**採用する設計（Round 9 §3、既存6.31設計への回帰）**：`reconcile_all()`（公開API）自体を**administrative recovery boundary**とする——`reconcile_all()`が`RetryExecutionLock`を取得し、そのlock保有scope内で`_reconcile_all_locked()`を実行する、という既存6.31の構造をそのまま信頼の根拠とする（Round 7・8で追加した「この構造だけでは不十分」という懸念は、下記の理由により撤回する）。CLAIMED orphan releaseのmutationは、`_reconcile_all_locked()`のループ本体へ**直接インライン**する——`_release_orphan_claim_for_reconciliation()`のような、独立して呼び出し可能な名前付きメソッド（たとえprivateな命名であっても）は一切作らない：

```python
def _reconcile_all_locked(self, resolve_status_fn: ResolveStatusFn) -> ReconcileSummary:
    # ...既存の走査ロジック...
    for record in self._store.list_all():
        if record.phase == RetryLineagePhase.CLAIMED:
            # CLAIMED orphan release：owner_tokenを検証しない（回収対象は定義上
            # 誰もowner_tokenを保持していないorphanであるため）。単独で呼び出し
            # 可能な別メソッドへ切り出さない——このループ本体自身が、
            # reconcile_all()がRetryExecutionLockを保持している間だけ実行される、
            # という既存6.31の構造そのものをauthorityの根拠とする（Round 9、
            # readable lease機構を撤回、Round 8 Blocking#1の再修正）。
            with self._store_lock():
                fresh = self._store.get(record.root_run_id)
                if fresh is not None and fresh.phase == RetryLineagePhase.CLAIMED:
                    fresh.phase = RetryLineagePhase.READY_ELIGIBLE
                    fresh.owner_token = None
                    # ...既存の記録更新（transition_history等）...
                    if self._store.save(fresh):
                        released_count += 1
        # ...既存のEXECUTION_STARTED分類ロジック（§11）...
```

**なぜこれで十分か（Round 9 §3の要求への回答）**：`reconcile_all()`は`RetryExecutionLock`を取得できなければ`_reconcile_all_locked()`自体を一切呼ばない（既存6.31、`RetryExecutionLockBusyError`は`reconcile_all()`内部でcatchされ`ReconcileSummary(skipped=True)`を返す、変更なし）。上記のCLAIMED orphan release処理は`_reconcile_all_locked()`という**単一のprivateメソッドの内部**にのみ存在し、このメソッド自体が`reconcile_all()`以外から呼ばれることは（Pythonの言語機能悪用を除き）ない——独立した「owner-less release API」を外部へ一切公開しない、というユーザー要求（Round 9 §3）をこの構造そのもので満たす。これは`_reconcile_all_locked()`が「呼び出し元が本当にlockを保持しているか」を検証しない、という点でRound 7・8が懸念した構造と同じだが、**この懸念自体が、既存6.31が最初から採用していた信頼モデル（`RetryExecutionLock`保有はプロセス全体でsingle-flightであり、`_reconcile_all_locked()`という名前のprivateメソッドへの到達経路は`reconcile_all()`の1箇所のみである、という構造的事実）に対する過剰な疑いだった**、というのがRound 9の判断である。static oracle（呼び出し箇所が`reconcile_all()`内1箇所のみであることの検証、§18）は補助的なrepository integrity invariantとして引き続き有効。

**RetryExecutionLockの設計（Round 9 §4、lease機構を削除し既存6.31 semanticsへ回帰）**：`acquire()`の戻り値・診断用PID文字列書き込み（stale判定には使わない）・`is_current_holder()`メソッドは**すべて削除**する。既存6.31の`RetryExecutionLock`クラス（`retry_execution_lock.py`）は本Amendmentによる変更を一切受けない。

**既存の`RetryExecutor.execute()`呼び出し元への影響（§9.5.2、owner-authorized releaseは維持）**：`release_claim()`のシグネチャ変更（`expected_owner_token`必須化、§9.5.2）自体はRound 6の指摘どおり維持する——これは**live caller（RetryExecutor）が自分自身のclaimを手放す経路**専用の変更であり、stale A/current Bレースの防止に必要（§9.5.2のstale caller normative contract、下記）。既存（Release 6.31由来）の2つの呼び出し箇所（`retry_executor.py:214`の`except Exception:`節、`retry_executor.py:218`の`hook_ack_state["acknowledged"] is False`節）も、`self._lineage.release_claim(lineage.root_run_id, claim.owner_token)`へ更新する。`claim.owner_token`は§9.5.1により`acknowledged=True`の場合は常にnon-empty strであることが保証されているため、この変更はowner_token authorityの検証を、既存の全release_claim()呼び出し経路へ一律に適用する——**stale caller脆弱性の修正は、6.32-protected/legacy lineageを問わず、全lineageに対する一般的なsecurity強化**である（owner_tokenフィールド自体が6.31から全lineage共通のフィールドであるため）。`_reconcile_all_locked()`のCLAIMED orphan release（上記インライン処理）は、この`release_claim()`とは**別の**経路であり、owner_tokenを一切要求しない（回収対象は定義上誰もowner_tokenを保持していないため）——これは意図的な非対称性であり、バグではない。

**stale caller scenarioのnormative contract化**：

```
1. claim()がowner_token=A（durableに保存）でCLAIMEDを確立する。
2. 何らかの理由でこのclaimがorphan化し、reconciliationのRECONCILIATION ORPHAN
   RELEASE（owner_token非依存）によりREADY_ELIGIBLEへ回収される（record.owner_token=None）。
3. 別のclaim()がowner_token=B（新しいuuid）で新たにCLAIMEDを確立する。
4. 古いcaller（owner_token=Aを保持したまま）が、今更mark_execution_started()を
   呼んでも、§9.5.1のauthority check（record.owner_token=B != A）により必ずreject
   される。
5. 古いcallerが、今更release_claim(root_run_id, expected_owner_token=A)を呼んでも、
   同じくauthority check（record.owner_token=B != A）により必ずreject——新しい
   claim（owner_token=B）を誤って解除することは絶対にない。
```

**必須テストケース（§18 test#17・test#18へ統合）**：このA→B stale caller raceをend-to-endで直接検証する（モックでなく、実際に2回のclaim()サイクルを構成する）。

### 9.5.3 Role-scoped Runtime Facades — **Codex Round 6 Major#3・Round 7 Blocking#1・Round 8 Blocking#2で扱った「rebind authority」課題は、Round 9のrebind廃止（§2・§4.1）により対象そのものが消滅。本節はconsumer-facing facade設計として再構成**

**Round 9での位置づけの変化**：Round 6〜8は「孤児manifestのrebindを、authorityを検証できない呼び出し元から防ぐにはどうするか」という問題を扱っていた。Round 9で`_rebind_orphaned_attempt()`自体を削除した結果（§2・§8）、`create_for_attempt()`は**新規作成専用**になり、正常経路で既存レコードと衝突すること自体が構造的に起こり得ない（§2確認済みの`member_run_id`一意性）。したがって、`create_for_attempt()`の直接誤用がもたらすblast radiusは、**「新しい・無害な・永久に孤児のままのmanifestレコードが1件増える」以上のものではない**——rebindという上書き操作が存在しないため、既存の正当なmanifest（特にdurable lineageから参照されている進行中のmanifest）を誤って書き換えることは、そもそも手段として存在しない。

**Round 9 §5の脅威モデル明文化（Codex Round 10 Minor#1指摘によりcontractを正確化）**：本節が守る対象と、意図的に対象外とする範囲を明記する。正確なcontractは以下の4点である：

- rawストア（フルアクセスの`ProtectedOperationManifestStore`インスタンス）を、public／non-mangled属性としてfacadeから露出しない。
- 通常のconsumer API surface（`ManifestReaderFacade`・`ManifestRegistrarFacade`が公開するメソッド群）は、authority-bearing method（`create_for_attempt`等）を一切持たない。
- 通常のproduction wiring（composition rootの配線経路）からは、create/admin mutationへ到達する経路が存在しない。
- Python reflection・`vars()`・malicious arbitrary-code introspection（name-mangled属性への意図的アクセスを含む）はthreat modelの対象外とする——これらはPython言語自体の一般的な性質であり、本Amendment固有の脆弱性ではない。

この明文化の上で、以下のfacade設計は「意図しない誤用・配線ミスに対する構造的な防御（defense-in-depth）」として位置づける——Round 8までのように「唯一の・十分なsecurity boundary」としては主張しない（そもそもcreate-onlyになった現在、防ぐべき実害自体が大幅に縮小している）。

**採用する設計（concrete facade、Round 8のtyping.Protocolから変更）**：Round 9 §5「Protocol typingだけをauthorityとは呼ばない」「consumer-facing objectからraw storeをpublic attributeとして露出しない」という要求に従い、`typing.Protocol`（構造的部分型、実行時には何も強制しない）ではなく、**具象クラスでrawストアをラップし、公開するメソッド上に危険なメソッドへの参照を持たないfacade**を定義する：

```python
class ManifestReaderFacade:
    """RetryExecutorへ渡す。list_for_attempt()のみを公開する。rawの
    ProtectedOperationManifestStoreインスタンスは、public／non-mangled
    属性としては公開しない（Codex Round 10指摘：name-mangling
    （`self.__store` → `_ManifestReaderFacade__store`）は通常の属性
    アクセス・vars()走査からは隠れるが、Pythonのreflectionを用いれば
    技術的には到達可能——この事実を「到達不可能」と表現しない。本facadeが
    保証するのは、公開メソッドの集合にauthority-bearing methodが
    含まれないこと、および通常のconsumer codeが`create_for_attempt`
    等へ到達する経路を持たないことであり、意図的なreflection迂回への
    耐性ではない（脅威モデル外、上記参照）。"""
    def __init__(self, store: "ProtectedOperationManifestStore") -> None:
        self.__store = store  # name-mangled。通常のattribute access・vars()からは
                               # 見えないが、reflectionによる意図的迂回は脅威モデル外。

    def list_for_attempt(
        self, root_run_id: str, attempt_ordinal: int, expected_member_run_id: str,
    ) -> "tuple[ManifestEntry, ...]":
        return self.__store.list_for_attempt(root_run_id, attempt_ordinal, expected_member_run_id)


class ManifestRegistrarFacade:
    """呼び出し箇所A/B/Cへ渡す。register()のみを公開する。rawストアの
    非露出契約はManifestReaderFacadeと同一（上記docstring参照）。"""
    def __init__(self, store: "ProtectedOperationManifestStore") -> None:
        self.__store = store

    def register(
        self, root_run_id: str, attempt_ordinal: int, member_run_id: str, entry: "ManifestEntry",
    ) -> "RegisterResult":
        return self.__store.register(root_run_id, attempt_ordinal, member_run_id, entry)
```

`RetryLineageManager`のみが、フルアクセスの`ProtectedOperationManifestStore`インスタンス（`create_for_attempt`・`register`・`list_for_attempt`のすべてを持つ、ラップされていない具象クラス）を直接保持する——composition root（`RetryCompositionRoot`、§21）は、`RetryExecutor`・呼び出し箇所A/B/Cへは上記facadeのみを配線し、通常の配線経路上にフルアクセスstoreへの参照を一切含めない。

**`RetryLineageManager.mark_execution_started()`内でのruntime fresh-check（既存設計を維持）**：`RetryLineageManager`自身も、`mark_execution_started()`の**単一の**`_store_lock()`臨界区間内で、`_verify_owner_authority()`（§9.5.1、fresh re-readされた`record`に対する4段階check）に成功した場合**のみ**、`create_for_attempt()`へ到達する。このcheckとmutationの間にauthorityの根拠（`record.owner_token`）が変化する余地はない（§9.5.1のTOCTOUなし論証、無変更）。

**static oracleの位置づけ（補助）**：`create_for_attempt()`への呼び出し箇所が`retry_lineage_manager.py`内の許可された1箇所（`mark_execution_started()`）のみであることを検証するstatic oracle（§18）は、repository integrity invariantとして補助的に維持する。

**「production wiring mistake／意図しない直接使用からの保護」の証明（Round 9版）**：`RetryExecutor`・呼び出し箇所A/B/Cは、facade経由でのみmanifestへアクセスするため、`create_for_attempt()`という属性自体を持たない参照しか保有しない——通常のコード経路・通常のテストでは`create_for_attempt()`へ到達しない。万一facade配線がバグにより誤ってフルアクセスstoreを直接渡してしまった場合（production wiring mistake）でも、`create_for_attempt()`自体は新規作成専用でありrebind機能を持たないため、**最悪でも無害な孤児manifestレコードが1件作られるのみ**であり、既存の進行中manifest・durable lineageのいずれも書き換えられない（§2のimmutable per-execution key設計）。この結論はRound 9の脅威モデル明文化（上記）とも整合する——「rawコードによる意図的なreflection」までは対象としない。

---

## 10. Synchronous Terminalization Algorithm（RetryExecutor.execute()）

```python
if not request.dry_run:
    newly_confirmed = compute_newly_confirmed(engine_result)
    step_categories = [classify_step_outcome(s) for s in engine_result.steps]

    if lineage.side_effect_contract_version is None:
        # legacy lineage: 既存6.31以前の挙動を完全維持
        disposition = decide_disposition(engine_result)
    else:
        try:
            # ProtectedOperationManifestReadError（NotFound/ContractViolation/IOErrorの
            # 共通基底、§8、Round 8でread専用hierarchyへ分離）を一律catchする。
            # 3種を区別しない——§9.1表の3行目。
            manifest_entries = self._manifest.list_for_attempt(
                lineage.root_run_id, claim.attempt_no, engine_result.run_id,
            )
        except ProtectedOperationManifestReadError:
            disposition = RetryLineageDisposition.HUMAN_REVIEW_REQUIRED
        else:
            operations = [
                ProtectedOperationContext(e.operation_kind, e.effect_site, e.operation_instance_key)
                for e in manifest_entries
            ]
            safety_report = self._side_effect_classifier.classify(
                lineage.root_run_id, claim.attempt_no, engine_result.run_id, operations,
            )
            disposition = resolve_final_disposition(step_categories, safety_report)

    mark_result = self._lineage.mark_terminal(
        lineage.root_run_id, disposition, engine_result.run_id, newly_confirmed,
    )
```

`member_run_id`引数は`engine_result.run_id`（既存Amendment調査時点の§10.2記述と一致）。

`self._manifest`・`self._side_effect_classifier`は`RetryExecutor.__init__()`への新規コンストラクタ引数として追加する。

---

## 11. Reconciliation Algorithm（`_reconcile_all_locked()`）

同期路と対称。`member_run_id`は`record.latest_run_id`（`RetryLineageRecord`が保持する、当該attemptの権威あるmember_run_id）。

```python
newly_confirmed = compute_initial_confirmed_steps(monitor_record.steps)
step_categories = [classify_execution_history_step(s) for s in monitor_record.steps]

if record.side_effect_contract_version is None:
    disposition = disposition_from_categories(step_categories)
else:
    attempt_no = record.attempt_scopes[-1].attempt_no if record.attempt_scopes else record.next_attempt_ordinal
    try:
        manifest_entries = self._manifest.list_for_attempt(
            record.root_run_id, attempt_no, record.latest_run_id,
        )
    except ProtectedOperationManifestReadError:
        disposition = RetryLineageDisposition.HUMAN_REVIEW_REQUIRED
    else:
        operations = [...]  # 同期路と同一の変換
        safety_report = self._side_effect_classifier.classify(
            record.root_run_id, attempt_no, record.latest_run_id, operations,
        )
        disposition = resolve_final_disposition(step_categories, safety_report)

result = self.mark_terminal(record.root_run_id, disposition, record.latest_run_id, newly_confirmed)
```

`RetryLineageManager`のコンストラクタへ`self._manifest`・`self._side_effect_classifier`を新規追加する（`RetryLineageManager`は既に`_reconcile_all_locked()`を実装しており、依存追加の影響範囲は composition root のみ）。

**HRR時にopen_next_attempt()へ進まないことの二重ガードとの関係**：本Amendmentは`mark_terminal()`へ渡す`disposition`の**入力**を変更するのみであり、既存の`open_next_attempt()`の二重ガード（`_reconcile_all_locked()`の`terminal_disposition not in (FAILED, NOT_ACTIONED)`フィルタ、および`open_next_attempt()`自身の`hrr_authorized`チェック）には一切触れない。disposition=HUMAN_REVIEW_REQUIREDが正しく`mark_terminal()`へ渡るようになることで、既存の二重ガードがより頻繁に正しく機能するようになるだけである。

---

## 12. Classifier Input Construction

`operations: list[ProtectedOperationContext]`の構築は、manifestの`entries`をそのまま`ProtectedOperationContext`へ変換するのみ（§15.3の`_STEP_TO_PROTECTED_OPERATIONS`表は、呼び出し箇所A/B/C自身が「どのoperation_kind/effect_siteをmanifestへ登録するか」を決定する際の参照表として引き続き使用する。terminalization側では表を直接参照せず、manifestに実際に登録された内容のみを信頼する——これにより「stepが実行されたら機械的にN個のoperationを期待する」という静的な仮定を排除し、実際に記事単位で何が起きたかという動的な事実のみをauthorityとする）。

---

## 13. Missing / Corrupt Manifest Classification

9章に統合済み。

---

## 14. Legacy Behavior

`side_effect_contract_version is None`（pre-6.32 lineage）の場合：

- 呼び出し箇所A/B/C：既存のlegacy分岐（`else`節）を一切変更しない。Manifestへは触れない。
- `RetryExecutor.execute()`／`_reconcile_all_locked()`：`decide_disposition()`／`disposition_from_categories()`をそのまま使用する（既存6.31以前の挙動を完全維持、Zero-Diff）。Manifestの`list_for_attempt()`は呼び出されない。

---

## 15. Gate OFF Behavior

MEDIA_UPLOADのGate OFF時、呼び出し箇所Bは既存どおり`record_not_applicable()`を呼ぶ**前**に、Manifestへ`(MEDIA_UPLOAD, NEWS_STEP, article.slug)`を登録する。`_classify_one()`は既存ロジックのまま`NotApplicableMediaUploadSafetyRecord`を検出し`NOT_APPLICABLE`を返す（安全、HRRを誘発しない）。Manifest登録の有無とGate ON/OFFは独立した軸であり、Gate OFFであってもManifestへの登録自体は必ず行われる（「この記事についてMEDIA_UPLOAD operationの判定対象であることは事実であり、その結果がNOT_APPLICABLEだった」という記録を残すため）。

---

## 16. Subprocess / Provenance Interaction

NEWS実行はsubprocess境界を持つ（14.6節）。Manifestの書き込みは既存の`MediaUploadSafetyCoordinator`・`WordPressDraftStateStore`と同一のsubprocess内（NEWS子プロセス自身）から行われ、同一のdurable filesystem（親プロセスとも共有される`base_dir`）へ書き込む。新しいsubprocess境界・新しいprovenance伝播経路は発生しない——既存の呼び出し箇所A/B自体が既にこの境界の内側で動作しているため、Manifest登録もその内側にそのまま追加されるのみである。

---

## 17. Cleanup / Recovery Semantics — **Round 9でrebind例外を削除、Round 10でimmutable/append-onlyの語義衝突を修正**

Manifestレコードの不変性は、**対象によって性質が異なる**（Codex Round 10 Minor#1指摘：「完全に不変」と「append-only」を無限定に併記すると語義が衝突する）：

- **generation identity**（`root_run_id`・`attempt_ordinal`・`member_run_id`の3要素、§2）：作成された瞬間から**immutable**——一度確定したら二度と変更されない（§3、Step 0 writerが新規作成時のみ書き込み、以後一切触れない）。
- **既存の各`entry`**（`ManifestEntry`、一度`entries`へ追加されたもの）：**immutable**——追加後に内容が変更・削除されることはない。
- **`entries`コレクション全体**：**append-only**——新しい`entry`が追記されることで内容が増える（削除・上書きは一切ない）。
- **レコード全体**：上記を総合すると、**append-only evolution**を持つ（初期状態`entries=()`から、`entry`の追記のみによって育つ）という性質であり、「完全に不変」ではない——generation identityは不変だが、`entries`は時間とともに増える。

永続化キーが`(root_run_id, attempt_ordinal, member_run_id)`の3要素になったため（§2）、新しいexecution試行は必ず新しい`member_run_id`を持ち、必ず新しいManifestキーとなる——既存recordの再利用・recycleは構造的に発生しない（Invariant #8 Non-Recycleと完全に整合）。

**Round 8までの「唯一の例外」（孤児レコードのrebind）は、Round 9で完全に削除された**——`entries=()`のまま孤児化したレコードは、cleanup・再利用のいずれも行わず、**永久にそのまま残る**（§4.1・§9.2a）。次回のexecution試行は新しい`member_run_id`で新しいレコードを作るのみであり、古い孤児レコードには一切触れない。これは真の意味で「例外のない」不変性である。

明示的なretention/cleanup機構は本Release・既存store群のいずれにも実装されていないため、本Amendmentでも新設しない（既存の一貫性を維持）。孤児レコードが蓄積し続けることは許容する——既存store群（`WordPressDraftStateStore`等）も同様にretention機構を持たず、この点で本Amendmentは既存の一貫性から逸脱しない。

---

## 18. Exact Test Matrix — **PLANNED IMPLEMENTATION TEST MATRIX（Round 9注記：production closure済みとは主張しない。実装フェーズで実施する予定のtest群であり、現時点では未実施）**

**Round 9での全面差し替え**：旧rebind/lease関連のtest（旧#18の一部・#20の一部・#21・#22）を惰性で残さず、新設計（immutable per-execution manifest・facade・reconciliation inline）に必要なdirect evidenceのみを再定義する。旧method名（`_rebind_orphaned_attempt()`・`_release_orphan_claim_for_reconciliation()`）・旧例外（`ProtectedOperationManifestAlreadyExistsError`）・旧lease expectation（`is_current_holder()`）への言及は、本節から完全に除去した。

1. **登録の冪等性**：同一identityを2回登録してもentriesが1件のまま。
2. **登録の順序保証（呼び出し箇所A/B/Cすべてを個別に検証、§1・§9.2の安全性論証の前提を直接証明する）**：呼び出し箇所A（`wordpress_output.py`）・B（`main.py`のmedia upload orchestration）・C（`ai_publish_service.py`）それぞれについて個別に、Manifest登録が既存write-ahead呼び出し（`record_attempted()`／`create_attempted()`／`record_not_applicable()`）より先に完了することをモック/spy呼び出し順序で検証する（3箇所すべてを網羅し、1箇所の検証で他を代表させない）。
3. **legacy lineageでの不使用**：legacy contextでの`apply()`/`save()`/`_post()`実行時、Manifestへの呼び出し回数が常に0。
4. **同期路：正常系（exact manifest、Round 9 §8）**：WP POST成功シナリオでmanifest→分類→`resolve_final_disposition()`→`mark_terminal()`の実チェーンを通し、`RetryExecutor.execute()`が`list_for_attempt()`へ渡す`member_run_id`が、実際に`self._engine.run()`が生成した`engine_result.run_id`と厳密に一致することを直接確認した上で、期待disposition（SUCCEEDED）を得る。
5. **同期路：crash直前**：`transition_to_confirmed()`直前crashを模擬し、restart後の`_reconcile_all_locked()`実チェーンでHRRを得る（mockでHRRを直接`mark_terminal()`しない）。
6. **crash路：media upload confirm直前**：`record_confirmed()`直前crash→restart reconcile→HRR→`open_next_attempt()`が自動発火しないことを確認（呼び出し回数0）。
7. **confirmed side effect + failed/not_actioned step**：`resolve_final_disposition()`のCONFIRMED_SUCCESS-mismatch分岐が実チェーンで正しく発火することを確認。
8. **Manifest破損**：schema不正なJSONを注入し、同期路・crash路の両方でHRRへ倒れることを確認。
9. **Manifest空（正常0件）**：0記事のNEWS run（genuinely vacuous）でHRRが発火しないことを確認——「正常runを恒常的にHRRへ落とさない」ことの直接的な回帰テスト。
10. **member_run_id不一致**：異なるmember_run_idでの登録試行が拒否されることを確認。
11. **queue bookkeeping写像**：実チェーンで確定したHRRが既存の`RetryQueueUpdateOutcome.FAIL`/`RetryQueueStatus.FAILED`へ写像され、新しいqueue/scheduler状態が追加されていないことを確認（既存`RetryQueueUpdateDecider`のテストを流用・拡張）。
12. **Gate OFF登録**：Gate OFF時もMEDIA_UPLOAD operationがmanifestへ登録され、NOT_APPLICABLE経由でHRRを誘発しないことを確認。
13. **admission時Manifest作成失敗（durable phase検証込み）**：`create_for_attempt()`を失敗させ、(a)`mark_execution_started()`がFalseを返す、(b)`record.phase`がdurableに`CLAIMED`のまま変化していないことをstore直接読み込みで確認する、(c)後続の`release_claim()`呼び出しが実際にTrueを返しREADY_ELIGIBLEへ戻ることを確認する、(d)呼び出し箇所A/B/Cのいずれも一度も呼ばれず外部I/Oも一切発生しないことをspy/mockで確認する——の4点をすべて直接検証する。
14. **Manifest read時のIOError（同期路・crash路・3種の例外subtype個別）**：`ProtectedOperationManifestNotFoundError`・`ProtectedOperationManifestContractViolationError`・`ProtectedOperationManifestIOError`のそれぞれを個別に注入し、`RetryExecutor.execute()`（同期路）・`_reconcile_all_locked()`（crash路）の両方で、3種すべてが無条件にHRRへ倒れることを個別テストケースとして検証する（3種×2経路＝6ケースを個別網羅する）。
15. **manifest作成→lineage save間のcrash＋孤児manifest非再利用（Round 9で全面書き直し：rebindではなくnon-reuseを検証）**：`create_for_attempt()`を成功させた直後、`self._store.save(record)`が呼ばれる前にプロセスがクラッシュした状態を模擬する。その後、(a)lineageが`CLAIMED`のまま（孤児化したmanifestが存在しても`_reconcile_all_locked()`には一切到達しないこと）、(b)当該孤児manifest（`(root_run_id, attempt_ordinal, 旧member_run_id)`キー）が、以後**一切参照・変更されない**ことを確認する、(c)同じlineageが再度claim・再度`mark_execution_started()`された際、`WorkflowEngineManager`が生成する新しい`member_run_id`（新しいuuid4、旧member_run_idとは異なる値であることを直接assertする）により、**新しいキー**で`create_for_attempt()`が呼ばれ成功することを確認する、(d)古い孤児manifestファイルと新しいmanifestファイルが同時に存在し、互いに独立していることをディスク上で直接確認する。
16. **既存admission事前チェックとの整合回帰**：`record is None`・`record.phase != CLAIMED`という既存の事前チェック（変更なし）が、manifest作成呼び出しより先に評価され続けることを確認する（順序反転による既存契約の意図しない後退がないことの回帰確認）。
17. **manifest成功後のlineage save明示的False（§9.3表・行5）＋stale owner race**：
    - (a)〜(d)：durable state=CLAIMED／`release_claim()`自体も失敗させた場合のreturn/diagnostic不一致／safety上のfail-closed／diagnostics accuracyは既存6.31 limitation。これらの`release_claim()`呼び出しはすべて`release_claim(root_run_id, expected_owner_token)`（§9.5.2、owner_token必須のシグネチャ）で行う。
    - (e) **stale owner race**：owner_token=Aで確立したclaimがorphan化・`_reconcile_all_locked()`内のインライン処理（§9.5.2a）で回収され、owner_token=Bで新たにclaimされた状態を構成する。その後、owner_token=Aを保持したままの古いcallerが`release_claim(root_run_id, expected_owner_token=A)`を呼んでも、`False`が返り、durable recordの`owner_token`が`B`のまま・phaseが`CLAIMED`のまま変化しないこと（新しいclaim Bが誤って解除されないこと）を直接確認する。
18. **owner_token admission negative cases（Round 9 §2、§9.5.1参照）**：
    - **非null性**：caller側owner_tokenが`None`→reject。caller側owner_tokenが空文字列`""`→reject。durable側`record.owner_token`が`None`→reject。caller/durable両方とも値を持つが不一致→reject。caller/durable完全一致（両方non-empty str）のみ許可。**`None == None`で通過しないことを明示的に確認する**。
    - **正常経路**：`_verify_owner_authority()`成功後の`create_for_attempt()`が、正しい3要素キー（`root_run_id`・`attempt_ordinal`・`member_run_id`）で新規manifestを作成することを確認する。
19. **Manifest generation uniqueness（Round 9 §1、新設、Codex Round 10 Suggestion指摘により代表ケースを明記）**：**「同一`root_run_id`・同一`attempt_ordinal`・異なる`member_run_id`」を検証する代表ケースは、claim→crash（進行中のexecutionを完了させず、release_claimも呼ばずに放棄——test harness上は状態構築でよく、実プロセスのhard terminationは必須ではない。Category A、§18末尾参照）→reconcile（`reconcile_all()`による既存CLAIMED orphan回収）→再claim→再`mark_execution_started()`、という**同一attempt内での複数execution試行**である。通常の複数attempt（`open_next_attempt()`による`attempt_ordinal`のインクリメント）は`attempt_ordinal`自体が異なるため、そもそも「同一attempt_ordinal」という前提を満たさず、本testの根拠として混同しない。上記の代表ケースで、各execution試行が生成する`member_run_id`が毎回異なるuuid4であること、および各execution試行に対応する`create_for_attempt()`呼び出しが、それぞれ独立した3要素キーで成功すること（衝突が一切発生しないこと）を直接確認する。
20. **Facade API surface（Round 9 §5、concrete facade、旧Protocol typing testを置換、Codex Round 10 Minor#1指摘によりcontractを正確化）**：composition root（`RetryCompositionRoot`）が`RetryExecutor`へ渡すオブジェクトが実際に`ManifestReaderFacade`のインスタンスであり`create_for_attempt`属性を一切持たないこと、呼び出し箇所A/B/Cへ渡すオブジェクトが実際に`ManifestRegistrarFacade`のインスタンスであり`create_for_attempt`属性を一切持たないことを検証する。あわせて、両facadeのpublic／non-mangled属性の集合（`dir(facade)`で列挙される名前のうち、`_`始まりのmangled名を除いたもの）に生の`ProtectedOperationManifestStore`インスタンスが含まれないこと、通常のconsumer API surface（各facadeが公開するメソッド）にauthority-bearing methodが一切含まれないことを確認する——`vars(facade)`にraw storeへの参照が一切存在しないことは要求しない（name-mangled属性としては存在し、これはPython reflectionで到達可能であり、脅威モデル外である旨を§9.5.3で明文化済み）。`RetryLineageManager`のみがフルアクセスstoreを直接保持することも確認する。
21. **A/B/Cそれぞれのmanifest registration durable ACK failure → zero downstream calls（exact call countで検証、Category A、下記参照）**：呼び出し箇所A・B・Cそれぞれについて**個別**のfault injectionテストとして、`register()`（Step 1）自体が失敗する状態を構成し、以下をexact call count（0であること）で直接検証する：
    - **A**（`wordpress_output.py`）：既存write-ahead呼び出し`record_attempted()`の呼び出し回数=0、外部I/O（`requests.post()`）の呼び出し回数=0。
    - **B**（`main.py`のmedia upload orchestration、**Gate ON/OFF両方を個別に検証**）：
      - Gate ON：`record_prepared()`の呼び出し回数=0、`record_attempted()`の呼び出し回数=0、外部upload I/Oの呼び出し回数=0。
      - Gate OFF：`record_not_applicable()`の呼び出し回数=0、外部upload I/Oの呼び出し回数=0。
    - **C**（`ai_publish_service.py`）：既存write-ahead呼び出し（`record_attempted()`相当）の呼び出し回数=0、`post_draft()`の呼び出し回数=0。
22. **CLAIMED orphan回収のfull chain（§9.2a matrix参照、actual codeへ正確に整合、Round 9でlease参照を削除）**：B0・B1・B2・B3・B4の**それぞれを個別のtestケースとして**（「いずれか」で代表させない）、`mark_execution_started()`の実際の実行を各境界で中断させて構成する。各境界で以下をexact matrixとして§9.2aの表と直接照合する：
    - 残存する`RetryExecutionLock`・`RetryLineageStoreLock`・（B2/B3のみ）Manifest attempt lockの有無。
    - durable manifest state（非存在／未完了／作成済み）。
    - durable lineage phase（`CLAIMED`）。
    その上で、recovery自体は以下のactual public behaviorに正確に整合させて検証する（モックで例外を仮定しない）：
    - `reconcile_all()`は`RetryExecutionLock`競合時、`RetryExecutionLockBusyError`を内部でcatchし`ReconcileSummary(skipped=True, reason=...)`という**通常の戻り値**を返す（例外として外へは伝播しない、§9.2a）。
    - `RetryLineageStoreLock`が残存している場合、`_reconcile_all_locked()`内のCLAIMED orphan回収インライン処理（§9.5.2a）が`RetryLineageStoreLockError`を**catchされない生の例外として**呼び出し元へ伝播することを確認する（`RetryExecutionLockBusyError`との非対称性を直接証明する）。
    - 残存する**すべての**lock（該当境界に応じてRetryExecutionLock・RetryLineageStoreLock・Manifest attempt lock）を、**旧holder processの終了を確認した上で**手動削除した後にのみ、`reconcile_all()`が成功し、`_reconcile_all_locked()`の既存CLAIMED orphan回収ロジック（§9.5.2a、インライン処理）が対象lineageを検出し、`READY_ELIGIBLE`への遷移、後続`claim()`によるlineage取得までを確認する。
23. **reconcile_all() administrative recovery boundary + raw owner-less release API = 0（Round 9 §3、新設）**：`RetryLineageManager`のpublic/private属性を走査し、`_release_orphan_claim_for_reconciliation()`のような、CLAIMED orphan releaseを単独で実行できる名前付きメソッドが**存在しない**ことを直接確認する（§9.5.2aのインライン設計の構造的証拠）。あわせて、`_reconcile_all_locked()`が`reconcile_all()`以外から呼ばれる経路が存在しないことをstatic oracle（補助的）で確認する。
24. **restart reconciliation exact manifest（Round 9 §8、新設）**：`_reconcile_all_locked()`が`list_for_attempt()`へ渡す`member_run_id`が、durable lineageの`record.latest_run_id`と厳密に一致することを直接確認する。

### Hard-Crash Test Methodology（Category A/B分離、Round 9でも維持）

25. **testを2種類に明確分離する**：
    - **Category A（state-machine/fault-injection tests）**：通常のPython例外・falsy return（mock・monkeypatch等）で検証可能なもの。test#1〜12・14・16〜21・23〜24の大半に加え、**test#13もここに属する**（`create_for_attempt()`が素直にFalseを返す、または`ProtectedOperationManifestError`を送出する場合であり、いずれもプロセスは生存し、`with`ブロックは正常に`__exit__`する。§9.3表・行2「安全（プロセス生存、lockは正常解放される）」と整合。実装評価時に確認済み：`RetryExecutor.execute()`の`hook_ack_state["acknowledged"] is False`分岐が同期的に`release_claim()`を呼ぶ既存経路のみを通り、lock file残存を主張しないため、hard-crashは不要）。
    - **Category B（hard-crash durability tests）**：`with`文の`__exit__`（lock解放処理・cleanup処理）が実行されないことを本質的な前提とするもの——通常のmock例外はPythonの例外送出・catch機構を経由するため、`with`ブロックの`__exit__`は必ず呼ばれてしまい、「lock fileが残存する」という主張を正しく検証できない。**test#15・22**（lock file残存を主張する箇所）は、**別プロセスを起動し、対象のcrash境界で`os._exit()`（または実装時に安全と判断される同等の強制終了手段）によるhard terminationを行った上で、親プロセスから残存lock fileの存在を確認する**、という契約で実装する。通常のmock例外だけで残存lockを証明したことにしない。external/network I/Oは0を維持する（安全性チェック済み、本Amendment冒頭の既存確認を参照）。

    **documentation cleanup（2026年、実装評価時の訂正）**：旧版の本節は「test#13・15・22」をまとめてCategory B対象と記載していたが、これはtest#13の実際の意味論（プロセス生存を前提とする通常のfault injection）を正確に反映していなかった。実装時の直接検証（`test_e2e_v6_32_35_admission_failure_durable_save_failure_closure.py`グループM）により、test#13はCategory Aへ、test#15・22（`test_e2e_v6_32_31_claimed_orphan_lock_state_hard_crash.py`）は引き続きCategory Bへ、と訂正した。architecture semantics（既存lock機構・recovery chain）自体への変更は一切ない。

---

## 19. Invariant #1〜#40への影響

既存40件のInvariantのうち、本Amendmentが**変更**するものはない（disposition解決の「入力」を正しく配線するのみで、write-ahead・ACK Determinism・Commit-Aware Lock Helper・exception taxonomy等の既存契約はすべてそのまま踏襲・再利用する）。

影響を精査すべき既存Invariantと、本Amendmentとの整合性：

- **#1（write-ahead ACK確認前にexternal I/O禁止）**：Manifest登録はさらに手前に追加されるのみで、既存の順序契約を弱めない。維持。
- **#15（MEDIA_UPLOADの全durable state変更は単一のMediaUploadSafetyCoordinator経由）**：Manifestは「状態変更」ではなく「意図の事前宣言」であり、MEDIA_UPLOADの実際のstate machine（NOT_APPLICABLE/ATTEMPTED/CONFIRMED_SUCCESS）はMediaUploadSafetyCoordinatorが引き続き単独で管理する。抵触なし。
- **#16（Shared Coordination Lockはcross-store transactionではない）**：Manifestのlockは独自のattempt-scoped lockであり、既存の安全store群のlockとの間にcross-store atomicityを主張しない（既存の緩やかな整合性モデルをそのまま踏襲）。
- **#18（No Automatic Repair）**：Manifest破損時にCONTRACT_VIOLATIONへ倒す設計（9章）は、この原則をそのまま新コンポーネントへ拡張したものであり、抵触なし、むしろ補強。

### 新規Invariantの要否 — **Codex Round 1 Blocking指摘により全面訂正**

初版はここで「Manifestの非存在＝vacuous-safe」というInvariant #41を提案していたが、Codex Independent Architecture Reviewにより、これが既存**Invariant #6**（reconciliationにmarker absence=safeというdefaultを置かない）・**Invariant #18**（No Automatic Repair：矛盾検出時は常にCONTRACT_VIOLATION）と**直接矛盾する**ことが指摘された。§9を全面改訂し、「admission成立時点でManifest存在をdurableに保証する」設計（§4.1）へ変更した結果、正しい主張は以下の通りである。

**要否：YES、1件の新規Invariant（#41候補）を提案する（内容を訂正）。**

> **Invariant #41（提案・訂正版）**：Protected Operation Manifestの非存在は、いかなる到達可能な経路においても安全（safe）とは推定されない——常にCONTRACT_VIOLATION相当（HRR発火）として扱われる。「保護対象操作が1件も発生しなかった」という正当な状態は、Manifestレコード自体は存在するが`entries`が空である、という構造的に区別可能な別の状態として表現される。この区別を可能にするのは、admission（`mark_execution_started()`）がManifest作成の成否と不可分に統合されていること（§4.1）であり、Manifest作成が失敗した場合はadmission自体が失敗し、いかなる保護対象operationも実行されない。

これは既存Invariant #6・#18と**矛盾しない**——むしろ両者を新コンポーネントへ正しく拡張したものである（「absence=safe」という推定を一切置かず、"absence"が到達可能な経路では発生しないことをadmission設計自体で構造的に保証する、という既存原則の忠実な適用）。独立したtest evidence（§18 test#9・#13〜25）を持つ。

---

## 20. 制約充足の確認

- **既存Approved Architectureを可能な限り維持**：write-ahead順序・ACK Determinism・Commit-Aware Lock Helper・exception taxonomy・identity schemaをすべて再利用。新しい設計原則は「admission成立とManifest存在を不可分にする」という1点のみ（既存の「absence=safeを置かない」原則をそのまま踏襲するための構造的手段であり、原則自体の変更ではない）。
- **generic non-HRR redispatch gapはOut of Scope維持**：本Amendmentは`mark_terminal()`への入力（disposition算出）のみを変更し、`RetryQueueUpdateDecider`・`retry_after_human_review()`・`_reconcile_all_locked()`のHRR用二重ガード自体には一切変更を加えない。
- **HRR-specific queue/scheduler status追加禁止**：`RetryLineageDisposition.HUMAN_REVIEW_REQUIRED`という既存の値をより正確に・より頻繁に正しく発火させるだけであり、新しいdisposition値・queue値は一切追加しない。
- **WordPressDraftStateStoreのclosed API契約を維持**：本Amendmentはこのstoreへのいかなる変更も提案しない。
- **暫定値・推測identity・「key不明ならとりあえず続行」の禁止**：Manifestに登録された正規の値のみを使用し、フォールバック値・デフォルト値による代替は一切行わない（9章の破損時分岐も、代替値を使わずHRRへ倒すのみ）。
- **「key不明なら常にHRR」の不採用証明**：§9.2で、genuinely 0記事のNEWS runがHRRを発火させないことを、admission成功→空Manifest作成→`worst_case()`vacuous-case実装（変更不要）という具体的な経路で示した。

---

## 21. 実装スコープ（Phase 2で変更対象となる見込みファイル）— **Round 9でlease/rebind関連ファイル変更を削除、facade定義を追加**

- 新規：`src/protected_operation_manifest/`（`__init__.py`・`errors.py`・`protected_operation_manifest_record.py`・`protected_operation_manifest_store.py`・`protected_operation_manifest_store_lock.py`・**Round 9追加：concrete facade定義（`ManifestReaderFacade`・`ManifestRegistrarFacade`、§9.5.3。Round 8の`typing.Protocol`版は削除）**）
- 変更：`src/retry_lineage/retry_lineage_results.py`（`ClaimResult`へ`owner_token: str | None = None`フィールドを追加、§9.5.1）
- （**Round 9で削除**：`src/retry_lineage/retry_execution_lock.py`への変更は不要になった——lease機構を撤回し既存6.31 semanticsへ回帰したため、§9.5.2a）
- 変更：`src/retry_engine/retry_executor.py`（`__init__`への依存追加（`ManifestReaderFacade`型で受け取る、フルアクセスstoreではない）・`execute()`のdisposition算出ロジック差し替え・post_admission_hookクロージャが`claim.owner_token`を`mark_execution_started()`へ渡すよう変更・既存2箇所の`release_claim()`呼び出し（`retry_executor.py:214`の`except Exception:`節、`:218`の`hook_ack_state["acknowledged"] is False`節）を`release_claim(root_run_id, claim.owner_token)`へ更新、§9.5.1・9.5.2）
- 変更：`src/retry_lineage/retry_lineage_manager.py`（`__init__`への依存追加（フルアクセスの`ProtectedOperationManifestStore`）・`_reconcile_all_locked()`のdisposition算出ロジック差し替え・`mark_execution_started()`シグネチャへの`owner_token`引数追加とexact match検証・`release_claim()`シグネチャへの`expected_owner_token`必須化・`_reconcile_all_locked()`ループ本体内へのCLAIMED orphan release処理のインライン化（独立メソッドへ切り出さない、§9.5.2a、Round 9）・`reconcile_all()`は既存6.31のまま変更なし（lease引数の受け渡しは撤回、§9.5.2a）、§4.1・§9.5.1・9.5.2a）
- 変更：`src/outputs/wordpress_output.py`（呼び出し箇所A：`ManifestRegistrarFacade`型の依存追加、manifest登録呼び出し追加）
- 変更：`main.py`（呼び出し箇所B：`ManifestRegistrarFacade`型の依存追加、manifest登録呼び出し追加）
- 変更：`src/ai/ai_publish_service.py`（呼び出し箇所C：`ManifestRegistrarFacade`型の依存追加、manifest登録呼び出し追加）
- 変更：`src/retry_composition/retry_composition_root.py`（`RetryCompositionRoot`：`ProtectedOperationManifestStore`（フルアクセス実体）・`SideEffectSafetyClassifier`のインスタンス化、`RetryLineageManager`へフルアクセスstoreを配線、`RetryExecutor`へは`ManifestReaderFacade`、呼び出し箇所A/B/Cへは`ManifestRegistrarFacade`のみを配線する（§9.5.3のfacade設計をcomposition rootで実現する唯一の箇所））
- 新規：static oracleテスト（既存`test_e2e_v6_32_6_invariant_35_static_oracle.py`と同型のAST解析手法を用い、`create_for_attempt()`への呼び出し箇所が`retry_lineage_manager.py`内の唯一の許可された呼び出し元（`mark_execution_started()`）1箇所のみであることを検証する。§9.5.3が言及する補助的repository integrity invariantであり、Round 9以降の§18 test matrix再編（本ドキュメント本文）では専用のtest番号を付与していない——**documentation cleanup（cross-reference訂正）**：旧版で本項目を指していた「§18 test#23」という番号は、Round 9の全面差し替え後は「reconcile_all() administrative recovery boundary + raw owner-less release API=0」（現行§18本文の項目23）を指す別内容へ再割当てされている。実装済みテストは`test_e2e_v6_32_28_protected_operation_manifest_static_oracle.py`（`create_for_attempt()`側）・`test_e2e_v6_32_37_reconcile_all_locked_static_oracle.py`（`_reconcile_all_locked()`側、現行§18 test#23の該当証拠）の2ファイルに分離されている）

上記はDraft段階の見込みであり、Human Gate承認後の実装フェーズで確定する。

---

## 22. Claude Self-Review（Draft段階、Codex独立reviewの前段）

- §11のpseudocode（`record.attempt_scopes[-1].attempt_no`の直接参照）は、同ファイル内`mark_terminal()`が採用する防御的パターン（`record.attempt_scopes[-1].attempt_no if record.attempt_scopes else record.next_attempt_ordinal`）と表記を揃えるべき。設計判断そのものへの影響はなく、実装時のpseudocode精緻化事項。
- §21の実装スコープに`src/retry_composition/retry_composition_root.py`への言及が当初欠落していたため追記した。

## Round History（§23〜32） — **HISTORICAL / SUPERSEDED（Codex Round 7 Major#1指摘により明示、Round 9・Round 10で更新）**

以下§23〜§32は、各ラウンドで指摘された**当時の**findingsと、その時点での対応内容を時系列で記録するhistorical logである。個々のfindingが引用する設計・API名・メソッド名は、**指摘された時点のもの**であり、後続ラウンドで更に修正されている場合がある（例：§26のRound 4ログが言及する「案A：CLAIMED phase + lock + caller discipline」はRound 5で撤回済み、§28のRound 6ログが言及する「`rebind_orphaned_attempt()`」（アンダースコアなし）はRound 7で`_rebind_orphaned_attempt()`へ改名済み、§29のRound 7ログが言及する「static oracleがdirect invocation resistanceの主たる根拠」という結論はRound 8で撤回され、§30のRound 8ログが言及する「RetryExecutionLock lease機構」「`_rebind_orphaned_attempt()`によるrebind」「role-scoped `typing.Protocol`」はいずれも**Round 9で完全に撤回・削除**され、immutable per-execution manifest（`member_run_id`をキーに含める）・reconciliationのinline処理・concrete facadeへ置き換わった。§32のRound 10ログはRound 9設計自体をAPPROVEDとした上で、facade/immutable wordingの過大表現・test#19代表ケースの明確化という非機能的な文書表現の修正のみを記録する）。**本文中の正式な規範（normative）となる設計は、§1〜§22の本文（特に最新版の§2・§9.5.1〜9.5.3・§9.5.2a・§17）のみである。** §23〜§32はいずれもnormative sectionではなく、変更履歴の記録としてのみ参照すること。

## 23. Codex Independent Architecture Review — Round 1（HISTORICAL）

**Verdict**: NEEDS_REVISION

**Blocking（3件、いずれも本版で対応済み）**:
1. `RetryExecutor.execute()`が`decide_disposition()`のみを呼びclassifier未接続（Blocking finding自体の再確認、対応不要——motivating findingそのもの）。
2. `_reconcile_all_locked()`が`disposition_from_categories()`のみを呼びclassifier未接続（同上）。
3. 初版§9の「manifest非存在＝空tuple＝安全」という設計が、既存Invariant #6・#18と直接矛盾する（→§4.1「admission時点での空Manifest作成」・§9全面改訂・§19 Invariant #41訂正で対応）。

**Major（3件、いずれも本版で対応済み）**:
1. `ProtectedOperationManifestIOError`が定義されていたが同期路・crash路のいずれもcatchしていなかった（→§8・§10・§11で共通基底`ProtectedOperationManifestError`を一律catchする設計へ変更）。
2. 案A棄却の「原理的に不可能」という表現が過度に断定的（→§1で「達成には追加schema変更が必要で案Cより侵襲的」という正確な表現へ訂正）。
3. 案B棄却の「3操作のみのclosed API」という一般化が`MediaUploadSafetyCoordinator`（実際は5メソッド公開）には不正確（→§1で対象を`WordPressDraftStateStore`固有の契約として訂正し、論点を「enumerate機能の不在」へ正確化）。

**Minor（2件、いずれも本版で対応済み）**:
1. `worst_case()`の引用行番号が古い（→§9.1で修正済み引用に差し替え）。
2. Test matrixにmanifest登録失敗時のzero-call検証・manifest read I/O failure検証が欠落（→§18 test#13〜15を追加）。

**Suggestions（3件）**:
1. 「absent」と「present and empty」の区別を、execution admission時点で作成するacknowledged attempt-level manifestにより行うべき（→§4.1として全面採用）。
2. `commit_aware_lock.py`への`identity=None`再利用は技術的に健全（→§7、変更なしで維持）。
3. 案Cを、admission時点で初期化するattempt-level manifest、および既存write-ahead managers内部での自動index化（案D）とも比較すべき（→§1に案Dとして追加、admission-time初期化は§4.1として採用）。

Round 2のCodex独立レビューを次に実施する。

## 24. Codex Independent Architecture Review — Round 2（HISTORICAL）

**Verdict**: NEEDS_REVISION——「the revision introduces a non-atomic two-store admission transition whose partial-failure and crash states contradict §4.1's claimed guarantees and are not recovered or adequately tested.」

**Blocking（3件、いずれも本版で対応済み）**:
1. manifest作成失敗時、`release_claim()`が`phase==CLAIMED`のみを受け付けるため（`retry_lineage_manager.py:388-393`、実コードで確認済み）、既にphaseが`EXECUTION_STARTED`へ遷移済みの状態では機能せず、「claim解放」という初版の主張が事実に反していた（→§4.1で操作順序を反転：manifest作成を先、lineage phase遷移を後に変更。これにより`ack=False`時は常にphase==CLAIMEDのまま、という不変条件を回復した）。
2. lineage save成功後・manifest作成前のcrashで、`EXECUTION_STARTED`かつmanifest非存在という状態が生じうる（→順序反転により、この組み合わせ自体が到達不可能になった。新たな残存crash窓——manifest作成後・lineage save前——は§9.3のcombination tableで全状態を明示的に列挙し、いずれも`CLAIMED`のまま孤児化するため`_reconcile_all_locked()`に到達しないことを証明した）。
3. 2つの独立したstoreにまたがる論理的操作の非atomicityに対する明示的なcombination tableが欠落していた（→§9.3として新設、既存`MediaUploadSafetyCoordinator`の9.9.7節Cross-Store Combination Tableと同型の手法で4状態を列挙）。

**Major（3件、いずれも本版で対応済み）**:
1. test #13・#15がdurable phase・release_claim実成功・crash-timing自体を検証していなかった（→§18 test#13を拡充、test#15をmanifest作成後・lineage save前のcrash-timingを直接構築する内容へ全面差し替え、test#16を追加）。
2. 案B/D棄却の安全性論証が「窓の有無」を論拠にしており不十分だった（→§1に「窓を構造的に検出・収束できるか」という精密な安全性プロパティを追加）。
3. 共通基底例外のcatchが3 subtype×2経路で個別に検証されていなかった（→§18 test#14を3subtype×2経路の6ケース明示検証へ拡充）。

**Minor（1件）**：
1. `release_claim()`の既存診断メッセージ（「READY_ELIGIBLEへ戻す」）が、manifest失敗時には事実に反していた（→§4.1の順序反転により、この診断メッセージは常に事実と一致するようになったため、追加の言い換えは不要になった。副次的に解消）。

**Suggestions（2件）**：
1. 明示的なrecoverable admission sub-state／durable pending-manifest markerの導入（→§4.1の順序反転（manifest→lineage save）自体が、追加のsub-stateを新設せずに同じ安全性を達成する、より単純な代替案として採用した。追加markerは不要と判断）。
2. 各境界でのfault-injection testの追加（→§18 test#13・#15・#16として反映）。

Round 3のCodex独立レビューを次に実施する。

## 25. Codex Independent Architecture Review — Round 3（HISTORICAL）

**Verdict**: NEEDS_REVISION

**Blocking（1件、既存6.31仕様のスコープ明確化で対応）**:
1. §9.3表・行3の「次回自動的に回収される」という記述が、`RetryExecutionLock`（`src/retry_lineage/retry_execution_lock.py`）が「staleness判定には使わない、自動削除なし」という**Release 6.31から変更のない既存仕様**（手動復旧手順は既存の9.3.3・9.4章）を持つことと矛盾する、との指摘。実コードを確認し、これは事実であり、かつ**本Amendment固有の問題ではなく、Retry Runtime全体の既存の運用前提**であることを確認した（→§9.3行3の記述を「既存の手動lock復旧手順を前提として回収される」へ訂正。本Amendmentが新たにこの制約を持ち込んだわけではないことを明記した）。

**Major（4件、いずれも本版で対応済み）**:
1. combination tableが「manifest成功・lineage save**明示的False**（crashではなく通常の失敗、プロセス生存）」という行を欠いていた（→§9.3行5として追加）。
2. `RetryExecutor`が`release_claim()`自身の戻り値をcheckせず、常に「解放成功」と報告する既存（6.31由来）のgapが、本Amendmentの新シナリオにも及ぶ（→§9.3行5でsafety-relevant事実（durable phase）と診断メッセージの正確性を切り分けて説明。§18 test#17へ両ケースの直接検証を追加）。
3. `create_for_attempt()`の冪等再利用規則が§6（member_run_id不一致は例外）・§17（レコード不変）と内部矛盾していた（→§6・§17へ明示的な例外規定を追加し、`register()`と`create_for_attempt()`のduplicate/conflict規則を分離した）。
4. B/D棄却の「検出可能性」論証が、個別operationレベルの窓については過大な主張だった（→§1・§9.2で「検出可能だから安全」から「外部I/O順序契約により無害だから安全」という正確な安全性プロパティへ訂正）。

**Minor（2件）**：
1. 「`mark_execution_started()`がFalseを返す時、record.phaseは常に不変」という記述が、durable state（正）とin-memory object（誤解を招く）を区別していなかった（→§9.3行5で「durable」を明示）。
2. test#13〜16が明示的save失敗（crashではない）を検証していなかった（→§18 test#17・#18を追加）。

Round 4のCodex独立レビューを次に実施する。

## 26. Codex Independent Architecture Review — Round 4（HISTORICAL、ユーザーがPowerShellから手動実行）

**Verdict**: NEEDS_REVISION（Blocking 0／Major 3／Minor 2）

**Major（3件、いずれも本版で対応済み）**:
1. §9.3行1「次回claim()が直接拾える」という記述が、実際のrecovery chain（`RetryExecutionLock`残存→既存の手動lock復旧手順→`reconcile_all()`→`_reconcile_all_locked()`の既存CLAIMED orphan回収ロジック（`retry_lineage_manager.py:702-707`）→`release_claim()`→`READY_ELIGIBLE`→後続`claim()`）を正確に反映していなかった（→行1・行3を実際のコード（`retry_lineage_manager.py:702-707`の既存設計コメント）に基づく5段階chainへ書き換え。「claim()が直接拾う」という表現を全文から除去。§18 test#19として full chain の直接検証を追加）。
2. `entries==empty`のみを理由とした`member_run_id`再bindの許可規則が、「emptyだからorphanだったはず」という未検証の推論に依存していた（→§9.5「Empty Manifest Rebind Authority」を新設。3案（A：現在durableなCLAIMED lineageをauthorityとする／B：既存claim/member identityで区別／C：新token追加）を比較し、案Aを採用——`create_for_attempt()`はmodule-private相当の協調APIであり、呼び出し元が`_store_lock()`保持下でCLAIMEDを直前確認済み・`RetryExecutionLock`による単一実行という構造的事実そのものをauthorityとする。新token（案C）は不採用（既存fieldで十分）。`media_upload_applicability_store.py`の既存前例（重複検出責務は呼び出し元が担う）と同型であることを明記。§18 test#18を3ケース（非空→reject、pre-check未通過→呼び出し0回、正当なorphan→rebind許可）へ具体化）。
3. §9.3行5と§18 test#17が同期しておらず、「durable state=CLAIMED」「return/diagnosticとの不一致」「safety上のfail-closed」「diagnostics accuracyの既存6.31 limitation」の4点が未分離だった（→行5・test#17を4点個別のassertionへ分離。この既存diagnostic gap自体の修正はscope外であることを明記）。

**Minor（2件、いずれも本版で対応済み）**:
1. 「6.31以前から」という表現が不正確（→「Release 6.31から」へ全箇所訂正）。
2. `_store.save()==False`時の説明が「atomic replaceだから」という一般論のみに依存していた（→既存lineage storeのACK Determinism contractを根拠として明記）。

Round 5のCodex独立レビューは自動実行しない（ユーザー指示）。PowerShell手動review用promptを求められるまで待機する。

## 27. Codex Independent Architecture Review — Round 5（HISTORICAL、ユーザーがPowerShellから手動実行）

**Verdict**: NEEDS_REVISION（Blocking 0／Major 3／Minor 1）

**Major（3件、いずれも本版で対応済み）**:
1. §9.3行1・行3のrecovery chainが「`RetryExecutionLock`だけ復旧すればよい」と誤読され得る記述だった。実際は`mark_execution_started()`臨界区間で`RetryExecutionLock`・`RetryLineageStoreLock`・（本Amendment新設の）Manifest attempt lockが入れ子になっており、crash境界によって残存するlockの組み合わせが異なる（→§9.2aとして、実コード確認済みの3種のlockのnesting構造と、7つのcrash境界（B0〜B6）ごとの残存lock/durable state matrixを新設。行1・行3をこのmatrixを参照する形へ書き換え。§18 test#20（旧test#19）をmark_execution_started()の実際のcrash境界から開始する設計へ変更）。
2. **最重要**：Round 4の「CLAIMED phase + lock + caller discipline」というauthorityは不十分と判定された。read-only調査の結果、既存`RetryLineageRecord.owner_token`フィールド（`retry_lineage_record.py:179`）が、`claim()`（`retry_lineage_manager.py:370`）によってdurableに生成されるにもかかわらず、`ClaimResult`（`retry_lineage_results.py:32-37`）が呼び出し元へ返していない、既存の未活用フィールドであることを発見した（→§9.5を全面改訂。`ClaimResult`へowner_tokenを追加し、`RetryExecutor`が保持、`mark_execution_started()`へ渡し、durable owner_tokenとのexact matchをmanifest作成前に検証する設計を採用。新token/schemaの追加ではなく既存fieldの検証経路新設であり、ユーザーのPreferred directionと「既存fieldだけで安全に認証できるなら新tokenを増やさない」制約の両方を満たす。§18 test#18を5ケースへ拡充）。
3. §18のtest matrixが、A/B/Cそれぞれについてmanifest registration失敗時のzero-call保証（既存write-ahead呼び出し=0、外部I/O=0）を個別に要求していなかった（→§18 test#19として新設、A/B/C個別のfault injectionを要求）。

**Minor（1件、対応済み）**:
1. §4.1の「record.phaseはCLAIMEDのまま」という記述が、in-memory objectとdurable stateを区別していなかった（→「durable lineage phaseはCLAIMEDのまま」へ訂正し、区別を明記）。

Codex Round 6は自動実行しない（ユーザー指示）。

## 28. Codex Independent Architecture Review — Round 6（HISTORICAL、ユーザーがPowerShellから手動実行）

**Verdict**: NEEDS_REVISION（Blocking 0／Major 4／Minor 1）

**Major（4件、いずれも本版で対応済み）**:
1. §9.5のowner_token authority checkが`if record.owner_token != owner_token`のみであり、両辺`None`で通過してしまう欠陥（→§9.5.1として新設、`_verify_owner_authority()`という4段階check（caller側non-empty str・durable側non-empty str・phase==CLAIMED・exact match）へ厳密化。`ClaimResult.owner_token`のnon-empty str契約も明記）。
2. **最重要**：既存`release_claim(root_run_id)`がowner authorityを検証しないため、stale callerがcurrent claimを誤って解除できる。ただし`_reconcile_all_locked()`のCLAIMED orphan回収はlive owner tokenを持たないadministrative recoveryであり、一律にowner_token必須化はできない（→§9.5.2として新設。release authorityを`release_claim(root_run_id, expected_owner_token)`（OWNER-AUTHORIZED RELEASE、live claimant専用）と`_release_orphan_claim_for_reconciliation(root_run_id)`（RECONCILIATION ORPHAN RELEASE、`_reconcile_all_locked()`専用、owner_token非依存、既存の正当化根拠をそのまま継承）へ明示的に分離。既存の`RetryExecutor.execute()`の2つのrelease_claim()呼び出し箇所も新シグネチャへ更新。stale caller A→B raceをnormative contractとして明記し、§18 test#17(e)・test#18で直接検証）。
3. `create_for_attempt()`を直接呼べばempty manifest rebind authorityを迂回できる（「module-private相当だから安全」という主張は言語仕様上強制力がない）（→§9.5.3として新設。3案（A：create/rebind完全分離／B：capability object／C：manifest storeがlineageへ依存）を評価軸表で比較し、案A（`create_for_attempt()`はrebind機能を持たず、既存レコードがあれば常にreject。`rebind_orphaned_attempt()`という別メソッドへ完全分離）を採用。direct misuseのblast radiusが構造的にゼロであること（rebindが変更できるのはmetadata=member_run_id/owner_tokenのみで、実際の安全性に関与する`entries`へは一切触れられない）を、手続き的主張ではなくデータフローの構造的論拠として提示）。
4. test matrixがA/B/Cのfault injection・crash boundary検証を「いずれか」で代表させており、B0〜B4個別の検証・Bのrecord_prepared()明示・reconcile_all()のactual public behavior（RetryExecutionLockBusyErrorではなくReconcileSummary(skipped=True)）との整合が不十分だった（→§18 test#19・test#20を全面書き換え。B0〜B4個別のexact matrix照合、reconcile_all()のactual behaviorへの整合、RetryLineageStoreLockErrorの非catch・生伝播の直接証明を追加）。

**Minor（1件、対応済み）**:
1. §9.2aの総括文が、B0（RetryLineageStoreLock取得前）を誤って「RetryLineageStoreLockも残存し得る」グループへ含めていた（→B0を除外し、B1〜B4のみを対象とするよう訂正）。

Codex Round 7は自動実行しない（ユーザー指示）。

## 29. Codex Independent Architecture Review — Round 7（HISTORICAL、ユーザーがPowerShellから手動実行）

**Verdict**: NEEDS_REVISION（Blocking 2／Major 3／Minor 2）

**Blocking（2件、いずれも本版で対応済み）**:
1. `rebind_orphaned_attempt(new_owner_token: str)`がraw文字列のみを引数に取る一般store APIのままでは、authority bypassを構造的に閉じたことにならない。「metadataのみだからblast radiusゼロ」という主張も、`member_run_id`が下流で認可用途に使われる以上撤回すべき（→§9.5.3を全面改訂。Pythonにcapability強制機構がないという言語仕様上の制約を直視した上で、既存Invariant #35と同型のstatic oracle（AST解析による呼び出し箇所の継続検証）を採用。`_rebind_orphaned_attempt()`への呼び出しがsrc/配下で`mark_execution_started()`内の1箇所のみであることを機械的に証明する設計へ変更。exception taxonomyも是正し、`ProtectedOperationManifestAlreadyExistsError`を新設して genuine corruptionとの混同を解消（Minor#2も同時対応））。
2. **最重要**：`_release_orphan_claim_for_reconciliation()`という独立callable helperが一般に呼び出し可能なままでは、stale live claimant／ordinary callerがadministrative orphan releaseを悪用できる（→§9.5.2へstatic oracle保護を追加。`_reconcile_all_locked()`本体1箇所のみからの呼び出しであることを継続検証する設計とした）。

**Major（3件、いずれも本版で対応済み）**:
1. 旧規則（`create_for_attempt()`が空レコードをrebindする、という初期設計）の残骸が§4.1・§9.3行3・§18 test#15に残存していた（→全箇所を新しいcreate/rebind分離・新例外taxonomyへ同期）。
2. B0〜B6だけで「あらゆる組み合わせ」と主張していたが、orphan rebind sub-path固有のcrash境界が未定義だった（→§9.2bとして新設、OR0〜OR4の5境界を初回create pathとは独立したmatrixとして定義。§18 test#21として初回create path（test#20）とは別のtestケースへ分離）。
3. test#18がRound 6版のauthority設計（raw token rebind）のままだった（→direct unauthorized rebind attempt・wrong owner・stale owner A/current owner B・missing/empty authority・non-empty manifest・legitimate orphanのみ成功・rebind後もentries不変・static oracleによるbypass経路の不在証明、をすべて統合）。

**Minor（2件、いずれも本版で対応済み）**:
1. §3がwriter authorityを分離していなかった（→§3を全面改訂、Step 0 admission/orphan recovery metadata writer（RetryLineageManager側）とStep 1 operation-entry writer（A/B/C）をclosed-setとして明記）。
2. `create_for_attempt()`の`ContractViolationError`が「既存recordがある」制御フローとschema corruptionを混同していた（→Blocking#1対応と統合して解消：`ProtectedOperationManifestAlreadyExistsError`を新設し、corruptionは`ContractViolationError`のまま`mark_execution_started()`がcatchしない設計とした）。

Codex Round 8は自動実行しない（ユーザー指示）。

## 30. Codex Independent Architecture Review — Round 8（HISTORICAL、ユーザーがPowerShellから手動実行）

**Verdict**: NEEDS_REVISION（Blocking 2／Major 6／Minor 2）

**Fundamental decision**：static oracleはrepository integrity invariant（許可された呼び出しパターン以外の増加を検出する）としてのみ有効であり、**runtime authority（direct invocation時のmutation前reject）の代替にはならない**。Round 7の設計はこの2つを混同していた。以後、authority-bearing mutationは必ずruntime自身で検証・拒否できる設計とする（本版で全面反映）。

**Blocking（2件、いずれも本版で対応済み）**:
1. reconciliation orphan releaseがowner-token-less administrative helperのまま一般に呼び出し可能だった（→§9.5.2aとして新設。`RetryExecutionLock`へlease semantics（`acquire()`が一意なlease識別子を返す、`is_current_holder(lease)`でruntime検証）を追加。`_release_orphan_claim_for_reconciliation()`は有効なleaseなしでは一切mutationしない設計へ変更。static oracleは補助的位置づけへ後退）。
2. `_rebind_orphaned_attempt()`がraw owner_tokenのみでmutation可能な一般store APIのままだった（→§9.5.3を全面改訂。manifest storeがlineage authorityを直接参照できない制約（§3）の下、composition root（§21）でrole-scoped interface（`ProtectedOperationManifestReader`・`ProtectedOperationManifestRegistrar`）を導入し、フルアクセスstoreを`RetryLineageManager`以外へ一切配線しない設計とした。既存`MediaUploadSafetyCoordinator`が生storeを外部非公開とする前例と同型）。

**Major（6件、いずれも本版で対応済み）**:
1-2. §18 test#18を新しいexception taxonomy（`AlreadyExistsError`）・新API名（`_rebind_orphaned_attempt`）へ完全同期し、「direct rebindはregister authorityへ影響しない」という誤った主張を削除（member_run_idが認可入力であることを踏まえ訂正）。
3. OR0〜OR4の「durable lineage owner_token=まだdurable未反映」という誤記を、「claim()時点で既にdurable確定済み」という正しい記述へ訂正（§9.2b）。
4. §9.2a B0〜B6から孤児/rebind由来の内容（B1の「または再claim時は既存orphan」）を除去し、true初回create pathのみを扱うscope宣言を明記。B matrixとOR matrix（§9.2b）の責務を完全分離。
5. §18のcrash tests（test#13・15・20・21）を、通常exceptionで検証するCategory Aと、実プロセスのhard termination（`os._exit()`等）を要するCategory Bへ明確分離するmethodologyを新設（test#24）。
6. test#19のMedia（B）ケースをGate ON/OFF両方へ拡張（Gate OFFでは`record_not_applicable()`のzero-call検証を追加）。

**Minor（2件、いずれも本版で対応済み）**:
1. 「あらゆる組み合わせ」という表現を§9.2a・§9.2b・§9.3から除去し、各表の対象範囲を限定して明記。
2. exception hierarchyを整理：`ProtectedOperationManifestReadError`（read path専用の共通基底）を新設し、`AlreadyExistsError`をこのhierarchyから除外。terminalization（§10・§11）のcatch節を`ProtectedOperationManifestReadError`へ変更。

Codex Round 9は自動実行しない（ユーザー指示）。

## 31. Codex Independent Architecture Review — Round 9（HISTORICAL、ユーザーがPowerShellから手動実行、SIMPLIFICATION PIVOT）

**Verdict**: NEEDS_REVISION（Blocking 4／Major 3／Minor 1）

**Fundamental decision**：readable bearer lease（`RetryExecutionLock`の内容を読めれば誰でも提示できる文字列）をsecurity authorityとして扱う設計（Round 8）を撤回する。Round 8までの累積的パッチ（rebind + readable lease + Protocol authority）を積み重ねる前に、そもそも設計を簡素化できないかをread-onlyで再評価した結果、Protected Operation Manifestの永続化キーへ`member_run_id`（`WorkflowEngineManager`が生成する既存の一意なuuid4）を組み込むことで、rebind機構自体を完全に不要化できることを確認した（IMMUTABLE EXECUTION/MEMBER GENERATION設計、§2）。

**Blocking（4件、いずれも本版で対応済み）**:
1. Rebind eliminationの成立可否を読み取り専用で確認する要求（§1）→ `member_run_id`の一意性・admission時点での確定・sync/restart双方でのdurable lineageからの取得可能性・A/B/Cへのlossless伝播の4点をすべて実コード読み取りで確認し（§2 Round 9投資確認）、案A（member_run_idベース）を採用。旧案B（独立manifest_id発行）は不要と判断。
2. mark_execution_started() adminssionのordering厳密化要求（§2）→ §4.1のpseudocodeから`AlreadyExistsError`catch＋rebindフォールバック分岐を削除し、create-onlyの単純なordering（authority check→create_for_attempt()→lineage save）へ整理。manifest create成功後・lineage save前crashの帰結を「孤児として永久に放置、rebindしない」へ明記。
3. Reconciliation authority simplification要求（§3）→ §9.5.2aを全面改訂。RetryExecutionLock leaseを撤回し、CLAIMED orphan release処理を`_reconcile_all_locked()`のループ本体へ直接インライン化（独立した名前付きメソッドを作らない）。既存6.31の「RetryExecutionLock保有＝reconciliation実行権」という信頼モデルへ回帰。
4. RetryExecutionLockからlease機構を削除する要求（§4）→ §9.5.2aで`acquire()`の戻り値変更・`is_current_holder()`をすべて削除し、既存6.31 semanticsを完全に維持することを明記。手動stale-lock復旧の前提条件（旧holder process終了確認）を§9.2aへ明記。

**Major（3件、いずれも本版で対応済み）**:
1. Role-scoped runtime objectsをconcrete facadeにする要求（§5）→ §9.5.3を全面改訂。`typing.Protocol`ベースのrole-scoped interfaceを、rawストアへの参照を一切公開しない具象facadeクラス（`ManifestReaderFacade`・`ManifestRegistrarFacade`）へ置き換え。脅威モデル（守る対象／対象外）を明文化。
2. Crash modelの再構築要求（§6）→ §9.2aのB0〜B6の帰結をimmutable per-execution key前提で書き直し、§9.2b（OR0〜OR4）を完全削除（対象自体が消滅したため）。§9.3のcombination table行1・行3からrebind recoveryの記述を削除。
3. Test matrixの作り直し要求（§8）→ §18を全面差し替え。旧rebind/lease関連test（旧#18の一部・#21・#22）を削除し、owner_token admission negative cases・manifest generation uniqueness・orphan manifest non-reuse・facade API surface・reconcile_all administrative recovery boundary・raw owner-less release API=0等の新testを追加。§18冒頭に「PLANNED IMPLEMENTATION TEST MATRIX」であり「production closure済み」とは主張しない旨を明記。

**Minor（1件、本版で対応済み）**:
1. Major cleanup要求（§9）→ 旧method名（`_rebind_orphaned_attempt()`・`_release_orphan_claim_for_reconciliation()`）・旧exception（`ProtectedOperationManifestAlreadyExistsError`）・旧lease expectation（`is_current_holder()`）への言及を、§3・§4.1・§6・§8・§17・§18・§21から完全に除去した。

Codex Round 10は自動実行しない（ユーザー指示）。

## 32. Codex Independent Architecture Review — Round 10（HISTORICAL、ユーザーがPowerShellから手動実行、POST-REVIEW POLISH）

**Verdict**: **APPROVED**（Blocking 0／Major 0／Minor 1／Suggestions 2）——Round 9のSIMPLIFICATION PIVOT設計そのものは承認され、以下は非機能的な文書表現の整理のみ。architecture semanticsの変更は一切ない。

**Minor（1件、本版で対応済み）**:
1. Facade wordingの過大表現（§9.5.3・§18 test#20）→ 「raw storeがprivate属性としても存在しない／runtime上到達不可能」という表現を、正確なcontract（raw storeをpublic/non-mangled attributeとして露出しない・normal consumer API surfaceにauthority-bearing methodを持たない・ordinary production wiringからcreate/admin mutationへ到達させない・Python reflection/vars()/malicious introspectionはthreat model外）へ訂正。§9.5.3のfacade docstring・§18 test#20の両方を同期。

**Suggestions（2件、いずれも本版で対応済み）**:
1. Immutable wordingの語義衝突（§17）→ 「Manifestレコードは完全に不変」と「entriesはappend-only」の併記を、対象別（generation identity=immutable／既存entry=immutable／entriesコレクション=append-only／レコード全体=append-only evolution）に整理した表現へ統一。
2. test#19の代表ケース明記（§18）→ 「同一root_run_id・同一attempt_ordinal・異なるmember_run_id」の代表ケースがclaim→crash→reconcile→再claimであることを明記し、attempt_ordinalが異なる通常の複数attemptを根拠として混同しないよう訂正。

**Final consistency check（ユーザー指示§4）**：上記3点の修正以外、§1〜§22・PLANNED IMPLEMENTATION TEST MATRIX（§18）のarchitecture semanticsに変更を加えていないことを確認した。

Codex Round 11は自動実行しない（ユーザー指示）。

## 33. Implementation Clarification — Invariant #15 / MediaUploadSafetyCoordinator Cross-Process Read Access（Phase 2 production remediation、HUMAN GATE APPROVED — OPTION A WITH NARROW INVARIANT #15 CLARIFICATION）

**背景**：Phase 2 production remediation実装中、`test_e2e_v6_32_13_media_upload_store_composition_root_closure.py`（Invariant #15の既存static oracle）が、`RetryCompositionRoot`が`SideEffectSafetyClassifier`用に`MediaUploadSafetyCoordinator`の下位3 store（`ArticleMediaUploadStateManager`・`JsonMediaUploadApplicabilityStore`・`JsonMediaUploadAttemptContextStore`）を独立に構築する変更とFAILした（構築箇所が既存の「main.py 1箇所のみ」という前提を超えたため）。

**根本原因**：`RetryLineageManager`／`RetryExecutor`（親/orchestratorプロセス）がterminalization/reconciliation時にMEDIA_UPLOAD evidenceを分類するには`SideEffectSafetyClassifier`が必要であり、これは`MediaUploadSafetyCoordinator`（既存Approved Foundation、9.9節）への参照を要求する。main.py（NEWS等のsubprocess）とRetryCompositionRoot（親/orchestratorプロセス）は**別プロセス**であり、同一runtime instanceを共有できないため、後者が独立したCoordinatorインスタンスを構築する必要がある。

**判断（HUMAN GATE APPROVED）**：これはArchitecture再設計ではなく、**Invariant #15のsemantic contractと、既存static oracle実装の間のずれ**として扱う。

- **Invariant #15のsemanticsは変更しない**：「MEDIA_UPLOADの全durable state**変更**は、単一のMediaUploadSafetyCoordinatorを経由する」という原則（mutation authorityの閉包性）はそのまま維持する。
- **single-construction-siteは、この原則のstatic oracle上の代理条件（proxy condition）に過ぎなかった**——Invariant #15の文言自体は「構築箇所が1つであること」を要求していない。「構築箇所=1」という条件は、既存static oracleが「durable state変更がCoordinator経由に閉じている」ことを機械的に検証するために採用した、当時のproduction wiring（main.pyのみがMEDIA_UPLOAD処理を行っていた）を前提とした実装上の代理指標だった。
- **cross-process read-only classificationのため、第2のCoordinator構築を承認する**：`RetryCompositionRoot`（`src/retry_composition/retry_composition_root.py`）が、`main.py`とは独立した第2のCoordinatorインスタンスを構築してよい。
- **mutation authorityはMediaUploadSafetyCoordinatorに閉じたまま**：新しい代替のdurable state read/write経路を下位3 storeへ直接設けることは禁止する。read/writeいずれもCoordinator（`.get()` / 4 mutation methods）経由を維持する。
- **retry-side instanceはclassification/read-only使用に限定する**：`RetryCompositionRoot`が構築するCoordinatorインスタンスは、`SideEffectSafetyClassifier.classify()`→`coordinator.get()`（lock-free read）にのみ使用する。`record_not_applicable()`／`record_prepared()`／`record_attempted()`／`record_confirmed()`（4 mutationメソッド）は、`src/retry_lineage`・`src/retry_engine`・`src/retry_composition`配下のいずれからも一切呼ばない。

**厳守条件（実装済み・test_e2e_v6_32_13で直接検証）**：
1. `RetryCompositionRoot`側Coordinatorはread-only purpose（`SideEffectSafetyClassifier`→`coordinator.get()`のみ）。
2. retry/orchestrator側からMEDIA_UPLOAD durable stateのmutation methodsを一切呼ばない。
3. 下位3 storeへの代替direct read/write pathを作らない（MEDIA_UPLOAD evidence readもCoordinator.get()経由を維持）。
4. `test_e2e_v6_32_13_media_upload_store_composition_root_closure.py`をInvariant #15本来の意味へ最小修正した：Coordinator construction許可箇所はexact 2箇所（`main.py`・`src/retry_composition/retry_composition_root.py`、wildcard/package-wide exclusionなし）、retry pathからdurable mutation methodが呼ばれないことをstatic evidence（テスト4、新設）で保証、Coordinator外からの下位store mutationは既存テスト2・3のまま許可しない。

**Original Foundationは変更しない**（`docs/design/side_effect_fail_closed_human_review_safety_foundation.md`は本Clarificationの対象外、不用意に書き換えない）。本Clarificationは、Phase 2実装が発見した「既存static oracleの実装が、当初想定していなかった正当なcross-process usageパターンを区別できていなかった」という事実の記録であり、Invariant #15自体・Approved Architectureの他のいかなる部分にも変更を加えない。

**エスカレーション条件**：第2のCoordinatorインスタンスからmutationが必要になる場合、またはFoundationの`.get()` contractと両立しないことが判明した場合は、本Clarificationの範囲を勝手に拡張せず、改めてNEEDS HUMAN GATEで停止する。

## 34. §18 Implementation Verification Record（実装評価チェックポイント、Codex Final Review前）

**本節はCodex Final Review・Release Review完了前の記録である。Release 6.32は本節時点でまだ「完了」ではない。**

§18（PLANNED IMPLEMENTATION TEST MATRIX、全25項目）について、production wiring（`RetryExecutor.execute()`実チェーン・`RetryLineageManager.reconcile_all()`→`_reconcile_all_locked()`実チェーン）を通した直接証拠に基づき、全25項目のPASSを確認した（store層単体テストのみでのPASS扱いは行っていない）。

- **test#7・test#8**：`test_e2e_v6_32_32_confirmed_mismatch_manifest_corruption_closure.py`
- **test#14**：`test_e2e_v6_32_32`（ContractViolationError sync/restart）＋`test_e2e_v6_32_33_manifest_read_error_taxonomy_closure.py`（NotFoundError・IOError sync/restart）
- **test#16**：`test_e2e_v6_32_34_admission_precheck_regression.py`
- **test#13・test#17**：`test_e2e_v6_32_35_admission_failure_durable_save_failure_closure.py`（実コード追跡の結果、test#13はプロセス生存を前提とするCategory A、test#15・test#22はhard-crash前提のCategory Bと確定。§18本文・Hard-Crash Test Methodology節を本記録作成時に訂正した）
- **test#6・test#9**：`test_e2e_v6_32_36_media_upload_terminalization_and_vacuous_manifest_closure.py`
- **test#22・test#25（Category B、hard-crash）**：`test_e2e_v6_32_31_claimed_orphan_lock_state_hard_crash.py`（子process＋`os._exit()`によるhard termination、B0〜B4境界を個別検証）
- **test#23**：既存`test_e2e_v6_32_27`（owner-less API不在・reconcile_all()実動作）＋`test_e2e_v6_32_37_reconcile_all_locked_static_oracle.py`（`_reconcile_all_locked()`static oracle、新規）

**検証結果（現在のWorking Treeで再実行、以前の結果は再利用していない）**：

| 検証範囲 | 結果 |
|---|---|
| §18 Implementation Matrix | 25/25 PASS、PARTIAL 0、MISSING 0 |
| v6.32系列 Full Suite（`test_e2e_v6_32_*.py`、実ファイル数） | 39ファイル、1270アサーション、1270 PASS、0 FAIL、0 SKIP、全ファイルexit code 0 |
| Formal Regression（`docs/architecture.md`定義の正式Inventory、実ファイル数） | 34ファイル、5671アサーション、5671 PASS、0 FAIL、0 SKIP、全ファイルexit code 0 |

Formal Regression実行の初回試行では、v6.22.0・v6.23.0・v6.24.0・v6.26.0・v6.27.0の5ファイルが、既存GR-9契約（`tests/zero_diff_guard_registry.py`）へRelease 6.32が追加したtest-relatedファイル（`test_e2e_v6_32_31`〜`37`・`hard_crash_worker_v6_32_31.py`の8件）のcontribution登録を行っていなかったために`NOIMPACT-NO-UNTRACKED-TESTS`等でFAILした（production機能の回帰ではない）。HUMAN GATE承認のもと、既存GR-9契約どおりappend-onlyでcontributionを8件登録し、再実行により解消した。

production semantics・既存test semanticsへの変更は行っていない。

## 35. Final Independent Codex Review & Blocking Remediation（Release Closure）

**Final Independent Codex Review 1回目の verdict**: CHANGES REQUIRED（Blocking 2・Major 0）。

- **Blocking 1**：`RetryExecutor.execute()`・`RetryLineageManager._reconcile_all_locked()`の両方で、protected lineage（`side_effect_contract_version is not None`）であってもmanifest/side_effect_classifierのいずれかがNoneの場合、既存6.31以前のstep-only disposition（`decide_disposition()` / `disposition_from_categories()`）へ黙って降格できてしまう経路が残っていた。これはprimary blocking finding（本Amendmentの発端そのもの）を再導入しうる欠陥として指摘された。
- **Blocking 2**：呼び出し箇所A（`wordpress_output.py`）・B（`main.py` `_apply_featured_media_step()`）・C（`ai_publish_service.py`）のいずれも、`manifest_registrar`がNoneの場合にmanifest registration自体をskipしてwrite-ahead/外部I/Oへ進めてしまう経路が残っていた。

**HUMAN GATE承認のもとの修正**（新しいarchitecture判断ではなく、既存Approved Architecture + 本Amendmentのfail-closed semanticsをproductionへ完全反映する限定修正）：

- Blocking#1：`retry_executor.py`・`retry_lineage_manager.py`のフォールバック条件を「legacy lineageのみstep-only fallback許可、protected + 依存欠落は無条件でHUMAN_REVIEW_REQUIRED」へ変更。
- Blocking#2：呼び出し箇所A/B/Cのoptional bypassを削除し、protected contextでのregistrar省略を`SideEffectExecutionModeContractError`（既存例外クラス、理由コードのみ`PROTECTED_MANIFEST_REGISTRAR_REQUIRED`を1件追加）で即座に拒否するよう変更。legacy contextでは引き続きregistrar省略を許容する。

この修正により、Blocking#1の影響を受けたRelease 6.31以前からの既存E2E（`test_e2e_v6_31_0`テスト#36：manifest/classifier省略で構築された`RetryLineageManager`がprotected lineageを扱うシナリオ）、およびBlocking#2の影響を受けた既存v6.32系列E2E 7ファイル（`test_e2e_v6_32_3`・`_4`・`_5`・`_18`・`_21`・`_22`・`_24`）が、いずれもregistrar/manifest/classifierの省略に依存していたため一時的にFAILした。全てのケースで実の依存（manifest store・classifier・registrar）を配線する形で改修し、既存テストの本来の検証意図を維持した（新規テストファイルは追加していない）。

**修正後の再検証結果**（現在のWorking Treeで再実行、以前の結果は再利用せず）：

| 検証範囲 | 結果 |
|---|---|
| v6.32系列 Full Suite | 39ファイル、1270アサーション、1270 PASS、0 FAIL、0 SKIP、全ファイルexit code 0 |
| Formal Regression（正式Inventory34ファイル） | 34/34ファイル、5671アサーション、5671 PASS、0 FAIL、0 SKIP、全ファイルexit code 0 |
| Affected historical（v1.18.0・v1.20.0・v2.3.0・v2.4.0・v6.22.0） | 全ファイルexit code 0 |

**Final Independent Codex Review 2回目の verdict**: **APPROVED WITH SUGGESTIONS**（Blocking 0・Major 0・Minor 0・Suggestion 1、non-blocking）。

Suggestion（Release safety blockerではない、future improvementとして記録）：`RetryExecutor.execute()`の`hook_ack_state["acknowledged"] is False`分岐が`release_claim()`の戻り値を確認せず、`RetryResult.reason`が無条件に「claim released back to READY_ELIGIBLE」と報告する既存（6.31由来）のdiagnostic gap。既存§9.3表・行5で安全性への影響なし（durable stateはfail-closedのまま、既存`reconcile_all()`のCLAIMED orphan回収で最終的に安全に収束する）と確認済み。本Amendmentのscopeでは修正しない。

以上により、Release 6.32のRelease approval conditionは充足された。`generic non-HRR automatic retry redispatch`等、本Amendment・Approved Architectureが明示的にOut of Scopeとした事項は、本Releaseで解決済みとは主張しない。
