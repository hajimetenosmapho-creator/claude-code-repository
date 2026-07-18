# Generated Image WordPress Media Upload Wiring Foundation — Architecture Design（v6.12.0）

作成日：2026-07-17
作成者：Claude Code（Architecture Designドラフト・Architecture Review 1～5 Finding反映）／ChatGPT（Architecture Review 1～5：Architecture Review 5 Approved）／ユーザー（最終承認・未実施）
状態：**Approved（Architecture Review 5 Approved、Architecture Design：Frozen）**
分類：**Architecture Release**（development_workflow.md 6章・7章。新規独立package・新規Public API・新規Dependency方向の確立を伴うため）

---

## 1. Document Status

```text
Architecture Design：Frozen（本文書、Architecture Review 5 Approved反映済み）
Architecture Review 1：Changes Required（Finding 6件、反映済み）
Architecture Review 2：Changes Required（Finding 4件、反映済み）
Architecture Review 3：Changes Required（Finding 1件、反映済み）
Architecture Review 4：Changes Required（Finding 1件、反映済み）
Architecture Review 5：Approved（Finding：Suggestion 1件（AR5-S-1）、本改訂で反映済み）
Test Review：Approved（Blocking Issueなし、Suggestion 3件：TR-S-1〜TR-S-3、本改訂で反映済み。43.7節参照）
Test Design：Approved／Implementation Ready
Production Implementation：Completed（新規package `src/generated_image_wordpress_media/`、43.8節以降参照）
New E2E：Completed（91/91 PASS、43.8節以降参照）
Code Review：Approved（初回Changes Required、Finding CR-m-1修正後のRe-ReviewでApproved。43.8〜43.10節参照）
Formal Regression：Completed／PASS（既存14ファイル1840/1840 PASS＋新規v6.12.0 E2E 91/91 PASS、
    総合1931/1931 PASS。Blocking Issueなし。43.11節参照）
Regression Total：1931/1931 PASS
Documentation Integration：Completed（docs/ROADMAP.md・docs/architecture.md・docs/CHANGELOG.md
    へ反映済み。Architecture変更なし、Blocking Issueなし。43.12節参照）
Release Review：Approved（Critical／Major／Minor Findingなし、Blocking Issueなし、
    Release成果物7ファイル全体を承認。継続Suggestion CR-S-1・CR-S-2・CRR-S-1は
    いずれもNon-Blocking。43.13節参照）
```

本文書はArchitecture Design工程の成果物であり、Architecture Review 1（Changes Required、6件）・Architecture Review 2（Changes Required、4件）・Architecture Review 3（Changes Required、1件）・Architecture Review 4（Changes Required、1件：AR4-m-1）で指摘されたFindingをすべて反映し、Architecture Review 5でApproved（Blocking Issueなし、Suggestion 1件：AR5-S-1）と判定された。Architecture Review 1〜4の全Finding（AR1-m-1〜AR1-m-4・AR1-S-1・AR1-S-2・AR2-m-1〜AR2-m-4・AR3-m-1・AR4-m-1）がResolvedであること、Architecture Review 5で確認された新規指摘がContractに影響しないSuggestion 1件のみであったことを根拠に、Architecture Review 5はApprovedと判定された。この判定に基づき、Architecture Designを正式にFreezeする（43.5節）。

**Design Freezeの意味**：以下のContractは、以後のTest Review・実装工程における確定基準として扱う。Test Reviewまたは実装工程で新たな重大な矛盾が発見された場合を除き、これらのArchitecture Contractを変更しない。

```text
Public API（14章）
責務境界（11章）
Dependency Direction（12章）
Error Contract（20章）
Security Contract（21章）
Runtime Flow（28章）
Test Strategy（31章）
Zero Diff Policy（31.7節・34章）
Out of Scope（37.2節）
```

Design Freeze以降、Test Review（43.7節）・Production Implementation・新規E2E作成（43.8節）・Code Review（初回Changes Required、Finding CR-m-1修正後のRe-ReviewでApproved、43.8〜43.10節）・正式Regression（既存14ファイル1840/1840 PASS＋新規v6.12.0 E2E 91/91 PASS、総合1931/1931 PASS、43.11節）・Documentation Integration（docs/ROADMAP.md・docs/architecture.md・docs/CHANGELOG.mdへの反映、43.12節）・Release Review（Approved、Blocking Issueなし、43.13節）がいずれも完了した。Release Review Approvedは、Architecture Design・Production Implementation・新規E2E・Code Review・Formal Regression・Documentation Integration・Release成果物全体が承認されたことを意味するが、git add・commit・push・origin/main同期確認はいずれもこの反映時点でも行っていない。

## 2. Release Metadata

```text
Release：6.12
Version：v6.12.0
Release名候補：Generated Image WordPress Media Upload Wiring Foundation
分類：Architecture Release
基準Release：v6.11.0（OpenAI Image Generation Adapter Foundation、commit b45b80a）
```

Release名は候補調査報告（Release 6.12候補調査プロンプトへの回答）で提示された候補をそのまま採用する。9章で命名規則との整合性を確認し、変更の要否を判断する。

## 3. Background

以下の3つのFoundationが完成済みである（8章「Existing Architecture」で詳述）。

```text
v6.9.0  WordPress Media Upload Foundation      src/wordpress_media/
v6.10.0 AI Image Generation Contract Foundation src/ai_image_generation/
v6.11.0 OpenAI Image Generation Adapter Foundation src/openai_image_generation/
```

`docs/ROADMAP.md`（731-733行目）は次のように明記している。

> 「Generated Image → WordPress Media Upload Wiring（次候補・未着手）：OpenAI Image Generation Adapter Foundationが生成した`GeneratedImage.image_bytes`を、v6.9.0の`WordPressMediaUploader.upload()`へ実際に渡す配線。Adapter Foundationが完了した後に着手する」

v6.11.0の完了により、この着手条件は充足された。`docs/design/wordpress_media_upload_foundation.md`（Future Extensions）・`docs/design/ai_image_generation_contract_foundation.md`（29章 Future Extensions）・`docs/design/openai_image_generation_adapter_foundation.md`（42章 Future Extensions）の3文書はいずれも、本Wiringを次候補として一致して記載している。

## 4. Problem Statement

3つのFoundationは相互に無配線（Consumer-less）のまま存在しており、「AIが生成した画像をWordPressのMedia Libraryへアップロードする」という一連の操作を、呼び出し元が自力で2つのPublic API（`AIImageGenerator.generate()` 系と`WordPressMediaUploader.upload()`）をまたいで手作業配線しない限り実行できない。この境界を、既存3 Foundationを無改修のまま接続する新規Foundationで埋める。

## 5. Goals

1. `GeneratedImage`（v6.10.0 Contract）を`WordPressMediaUploader.upload()`（v6.9.0 Public API）へ橋渡しする、単一責務のWiring層を追加する
2. 既存3 Foundation（`ai_image_generation` / `openai_image_generation` / `wordpress_media`）を無改修のまま維持する（Zero Diff）
3. Provider非依存を維持する（`openai_image_generation`への依存を持たない。将来別Providerの`AIImageGenerator`実装が生成した`GeneratedImage`もそのまま受け付けられる）
4. 生成失敗の責務と、Media Upload失敗の責務を混在させない（Failure Domainの分離）
5. 入力を自動修正せず、責務の異なる検証を重複実装しない
6. Foundation Firstを維持する（本Release時点では消費者不在の先行実装として安全に導入する）
7. 1 Release＝1目的を維持する

## 6. Non-Goals

9章「Selected Architecture」・26章「CLI／Entry Point Contract」・27章「Article／featured_media Boundary」・37章「Out of Scope」に同じ。要点のみ先出しする。

```text
画像生成（prompt→GeneratedImage）は行わない
Article／featured_media反映は行わない
CLI／scripts Entry Pointは追加しない
Retry Runtimeへの接続は行わない
Dry Runは追加しない
既存Pipeline／Workflow／Scheduler／Retry Runtimeへの配線は行わない
```

## 7. Existing Architecture

Architecture Design着手前に、既存3 Foundationの実装・設計書・`docs/architecture.md`・`src/retry_composition/retry_composition_root.py`を実読し、以下を確認済みである。

### 7.1 WordPress Media Upload Foundation（v6.9.0、`src/wordpress_media/`）

```python
MediaUploadResult          # frozen dataclass: media_id: int, source_url: str | None, mime_type: str | None
WordPressMediaUploadError  # RuntimeError
WordPressMediaUploader     # __init__(site_url, username, app_password) / from_env() / upload(image_bytes, filename, mime_type) -> MediaUploadResult
```

`upload()`は独自のUpload Input Contract（14章）を持ち、`image_bytes`（`bytes`型・非空）・`filename`（`^[A-Za-z0-9][A-Za-z0-9._-]*$`のASCII安全文字regex）・`mime_type`（`str`型・非空・前後空白禁止・制御文字禁止）をHTTP送信前にfail-fastで検証し、不正時は`ValueError`を送出する。通信・レスポンス異常は`WordPressMediaUploadError`。

### 7.2 AI Image Generation Contract Foundation（v6.10.0、`src/ai_image_generation/`）

```python
GeneratedImage    # frozen dataclass: image_bytes: bytes (repr=False), mime_type: str。__post_init__でbytes非空・mime_type非空等を検証
AIImageGenerator  # Protocol: generate(self, prompt: str) -> GeneratedImage
```

Provider非依存のContractのみで、標準ライブラリ以外に依存しない独立package。

### 7.3 OpenAI Image Generation Adapter Foundation（v6.11.0、`src/openai_image_generation/`）

```python
OpenAIImageGenerator             # AIImageGeneratorを実装する最初の具象Provider
OpenAIImageGenerationError       # RuntimeError、reason属性を保持
OpenAIImageGenerationErrorReason # Enum、9種
```

`openai_image_generator.py:17`で`from ai_image_generation import GeneratedImage`のみをimportし、`AIImageGenerator` Protocol自体はimportしない（Protocol適合は構造的部分型で成立するため）。この「`GeneratedImage`のみをimportし`AIImageGenerator`はimportしない」という既存パターンは、本Wiringの依存Contract設計（12章）における直接の先例になる。

### 7.4 3 Foundation間の現在の配線状態

`src/`配下を横断的にGrep調査した結果、以下を確認した。

```text
openai_image_generation → ai_image_generation（GeneratedImageのみ）: 唯一の相互依存
wordpress_media → ai_image_generation / openai_image_generation: 依存なし
ai_image_generation → wordpress_media / openai_image_generation: 依存なし
既存src/配下の他ファイル（image_resolver.py, outputs/, ai/, pipeline/等）
  → 上記3 Foundationいずれへも依存なし（import 0件）
scripts/配下 → 上記3 Foundationへの依存なし。画像／Media専用CLIも存在しない
```

`src/image_resolver.py:28-49`の`resolve_media_id()`は、`image_terms_confirmed`がTrueの分岐が`pass`のみで未実装のまま残っている（v1.6.0時点のコメントで「v1.7.0でMediaUploader経由アップロード予定」と予告されたまま）。本Releaseはこの分岐を実装しない（27章）。

### 7.5 Composition Root既存パターン（`src/retry_composition/retry_composition_root.py`）

`RetryCompositionRoot`は「既存の`from_env()`/`from_config()`のみを呼び出して組み立てる」「新規business logicは追加しない」「実行・ループは行わない（属性公開のみ）」という制約を持つ、純粋な配線専用クラスである。本Wiringはこれとは性質が異なる。`RetryCompositionRoot`は複数コンポーネントを**組み立てるだけ**だが、本Wiringは`upload(image, filename) -> MediaUploadResult`という**実際の呼び出し（1回のメソッド委譲）を実行する薄い業務層**である。この違いは、v3.2.0 Retry Queue Integrationで`RetryManager`が`RetryQueueManager`をConstructor Injectionで保持し、`enqueue_retry()` / `dequeue_retry()`という薄い委譲メソッドを持たせた設計（`architecture.md` 54行目）に近い。本Wiringはこのv3.2.0パターンの、Media Upload版としての適用である。

### 7.6 Dependency Direction原則（`docs/architecture.md`共通ルール）

既存全Foundationは一貫して「一方向依存のみ許可」「消費者不在の先行実装（Foundation First）」を採用している（例：`architecture.md` 566行目 `workflow_engine → execution_history`の一方向依存、2994-2998行目 `wordpress_media`のDependency Direction）。本Wiringもこの原則をそのまま継承する。

## 8. Candidate Architecture Models

### モデルA：生成済み画像のMedia Upload専用

```text
GeneratedImage
    ↓
新規Wiring層
    ↓
WordPressMediaUploader.upload()
    ↓
MediaUploadResult
```

新規層は既に生成された`GeneratedImage`を受け取るのみで、`AIImageGenerator` / `OpenAIImageGenerator`のいずれへも依存しない。promptを受け取らず、画像生成を実行せず、画像生成失敗を扱わない。

### モデルB：画像生成とMedia Uploadの合成

```text
prompt
    ↓
AIImageGenerator.generate()
    ↓
GeneratedImage
    ↓
WordPressMediaUploader.upload()
    ↓
MediaUploadResult
```

新規層がpromptを受け取り、画像生成とMedia Uploadを連続実行する。`AIImageGenerator`への依存を持ち、生成失敗・Upload失敗の両方を扱うComposition／Orchestration責務を持つ。

### 比較表

| 観点 | モデルA | モデルB |
|---|---|---|
| ROADMAP文言との一致 | 「**Generated Image** → WordPress Media Upload Wiring」に忠実 | ROADMAPの文言が想定する起点（`GeneratedImage`）と異なる |
| 入力 | `GeneratedImage`（既に検証済みの値） | `prompt: str`（未検証の自由入力） |
| 依存先 | `ai_image_generation`（`GeneratedImage`のみ）／`wordpress_media` | 上記に加え`ai_image_generation.AIImageGenerator`、実質的に`openai_image_generation`相当の具象実装が必要 |
| Failure Domain | 単一（Media Upload失敗のみ） | 二重（生成失敗＋Upload失敗）を1メソッド内で扱う必要がある |
| Provider非依存性 | 維持される（将来の別Provider実装もそのまま利用可能） | `AIImageGenerator`実装を注入する設計にしても、「どのPromptを渡すか」という新たな責務が発生する |
| 将来のArticle→featured_media Wiring（候補D）との関係 | 候補Dは本層の`MediaUploadResult.media_id`のみを消費すればよく、責務が重複しない | 候補Dが「記事内容からpromptを組み立てる」責務まで持つ場合、本層の合成責務と重複・競合しうる |
| Scope／実装規模 | 小（単一メソッドの委譲＋型検証1件） | 中〜大（Prompt Contract・生成Retry方針・二重Failure Domainの設計が必要） |
| 単一責務原則 | 満たす | Composition責務が加わり、単一責務からやや逸脱する |

## 9. Selected Architecture

**モデルAを採用する。**

### 9.1 採用理由

1. **ROADMAP・3設計書すべての記載と最も忠実に一致する**。7章で確認した通り、ROADMAP・`wordpress_media_upload_foundation.md`・`ai_image_generation_contract_foundation.md`・`openai_image_generation_adapter_foundation.md`はいずれも「`GeneratedImage`を起点とする」Wiringとして本境界を記述している。
2. **Failure Domainが単一に閉じる**。画像生成失敗（`OpenAIImageGenerationError`等、Provider固有）とMedia Upload失敗（`WordPressMediaUploadError`）を同一メソッド内で混在させると、呼び出し元が「どちらのエラーか」を判別するための追加設計（Orchestration Error型の要否等）が必要になる。モデルAはこれを未然に回避する。
3. **Provider非依存性を維持できる**。`GeneratedImage`のみに依存することで、将来OpenAI以外のProviderが`AIImageGenerator`を実装しても、本Wiringは無改修のまま再利用できる。これは7.4節で確認した`openai_image_generation`自身の依存パターン（`GeneratedImage`のみimport）と対称的で一貫している。
4. **将来のArticle→featured_media Wiring（v6.13候補）との責務重複を避けられる**。候補Dは`media_id`（本層の出力）だけを消費すればよく、本層が生成責務まで持つと候補D側の設計選択肢を狭める。
5. **Scopeが小さく、Architecture Reviewでの検証範囲が明確**。単一メソッドの委譲＋1件の型検証に閉じるため、Review工数・Regressionリスクを最小化できる。

### 9.2 モデルBを採用しない理由（8章の逆規定）

- モデルAで成立しない実務上の制約は確認できなかった。「画像生成とアップロードを同一トランザクションで扱う必要がある」という要件はROADMAP・design doc・既存コードのいずれにも記載がない。
- モデルBを選ぶ場合に必要となる「単一責務原則に反しない理由」「画像生成とUploadを同一Releaseで扱う必要性」を裏付ける既存Architecture上の根拠は見つからなかった。
- モデルBは責務拡大にあたり、便宜性（呼び出し元のコード量が減る）以外の設計上の必然性を示せないため、7章「単に便利だからという理由だけでモデルBを選ばない」という制約に抵触する。

### 9.3 Architecture Decision Summary

| # | 内容 |
|---|---|
| AD-1 | 責務モデル：モデルA採用（画像生成を含まない、`GeneratedImage`を入力とするMedia Upload専用Wiring） |
| AD-2 | Package配置：新規独立package`src/generated_image_wordpress_media/`（Consumer-less Foundationとして導入） |
| AD-3 | Public API：`GeneratedImageWordPressMediaUploader`のみ公開。新規Result型・新規Exception型は追加しない |
| AD-4 | Constructor：`WordPressMediaUploader`をConstructor Injectionで受け取る。`from_env()`は持たない（14.4節） |
| AD-5 | 依存Contract：`ai_image_generation.GeneratedImage`と`wordpress_media`（`WordPressMediaUploader` / `MediaUploadResult`）のみに依存。`AIImageGenerator` Protocol・`openai_image_generation`いずれにも依存しない |
| AD-6 | filename Contract：呼び出し元が明示的に渡す。内容検証（regex等）は`WordPressMediaUploader.upload()`の既存Contract（v6.9.0 14章）へ完全委譲し、本層では再実装しない |
| AD-7 | image Contract：`isinstance(image, GeneratedImage)`のみを本層固有の新規検証として追加。`image_bytes` / `mime_type`の内容検証は`GeneratedImage.__post_init__`（v6.10.0）へ委譲済みのため再検証しない |
| AD-8 | mime_type Contract：`GeneratedImage.mime_type`をそのまま`upload()`の`mime_type`引数へ渡す。filename拡張子との整合性チェックは行わない |
| AD-9 | image bytes Contract：`image.image_bytes`の値を変更せず`upload()`へ渡す（値の等価性のみをContractとし、object identity・コピー有無は実装詳細としてPublic Contract化しない）。圧縮・リサイズ・再エンコード・内容検査・再検証は行わない |
| AD-10 | 戻り値Contract：`MediaUploadResult`をそのまま返す。新規Result型でラップしない |
| AD-11 | Error Contract：`WordPressMediaUploadError`はラップせずそのまま伝播する。本層固有の新規例外は`ValueError`（image型不正の1ケースのみ）に限定する |
| AD-12 | Security Contract：本層はimage bytes・credentialのいずれも保持・ログ出力しない |
| AD-13 | Logging：本Releaseでは追加しない |
| AD-14 | Retry：本Releaseでは追加しない。Retry Runtimeへの接続もしない |
| AD-15 | Dry Run：Out of Scope |
| AD-16 | CLI／Script Entry Point：Out of Scope |
| AD-17 | Article／featured_media：Out of Scope（Release 6.13候補として持ち越す） |
| AD-18 | Testability：`media_uploader`はDuck Typing前提のConstructor Injectionとし、`isinstance(media_uploader, WordPressMediaUploader)`によるnominal型検証は行わない。ただし検証を一切行わないわけではなく、AD-19の遅延capability検証を行う |
| AD-19 | media_uploader capability Contract：`upload()`実行時（dependencyを利用する直前）に`callable(getattr(self._media_uploader, "upload", None))`による遅延Duck Typing検証を行い、不適合の場合は固定message`"media_uploader must provide a callable upload method"`の`TypeError`を送出する。v6.11.0 `OpenAIImageGenerator._get_client()`は`hasattr(self._client, "with_options")`のみで遅延検証を行っているが（属性の存在確認のみ）、Release 6.12はこれと**同一ではなく**、upload capabilityが実際に呼び出し可能であることまで保証するため`callable()`検証へ強化する（Architecture Review 1 Finding AR1-m-2、Architecture Review 2 Finding AR2-m-1反映） |
| AD-20 | signature不一致Contract：AD-19の`callable()`検証は「呼び出し可能なobjectであること」のみを保証し、`image_bytes` / `filename` / `mime_type`のkeyword引数を実際に受け付けるsignatureであることまでは保証しない。`inspect.signature()`等によるsignature introspectionは追加しない（過剰設計・Fake実装の柔軟性低下を避けるため）。signature不一致は実際の呼び出し（20.3節ステップ3）でPython標準の`TypeError`として自然に発生し、本層は「WordPressMediaUploadError以外の予期しないException」（20章）としてこれを無変換伝播する。capability検証失敗のTypeError（Wiring層送出・固定message）とは送出主体・message Contractの両方で明確に区別する（Architecture Review 3 Finding AR3-m-1反映） |

## 10. Rejected Alternatives

| 案 | 却下理由 |
|---|---|
| モデルB（画像生成とMedia Uploadの合成） | 9.2節参照。Failure Domain混在・Provider非依存性喪失・既存文書との不一致 |
| 独自Protocol（`MediaUploader` Protocol）を新設し`WordPressMediaUploader`をその実装として扱う | Media Uploaderの実装は現時点で`WordPressMediaUploader`の1つのみであり、2つ目の実装が存在しない段階でのProtocol抽象化は時期尚早（YAGNI）。将来複数CMS対応が必要になった時点で改めて検討する（40章） |
| `media_uploader`引数に`isinstance(media_uploader, WordPressMediaUploader)`によるnominal型検証を追加する | v6.11.0の`OpenAIImageGenerator(client=...)`と同じDuck Typing Injectionパターンを踏襲し、テスト時のFake／Stub注入をnominal型制約なしで可能にするため（AD-18）。ただし検証を完全に省略するわけではなく、AD-19のとおり`callable()`による遅延capability検証は行う（Architecture Review 1 Finding AR1-m-2反映） |
| `media_uploader`に対して一切の検証を行わない（AD-19以前の初稿方針） | Architecture Review 1（AR1-m-2）で、実際のv6.11.0 `_get_client()`が`hasattr(self._client, "with_options")` → 不適合時`TypeError`という遅延検証を行っている事実と、初稿の「検証を一切行わない」という記述・precedent引用が不一致であると指摘された。不正dependency注入時の失敗モード（`AttributeError`）が20章 Error Contractに未定義のまま実装フェーズへ渡ることを避けるため、v6.11.0と同型の遅延検証の考え方を採用した |
| `hasattr(media_uploader, "upload")`のみを最終Contractとする（AR2-m-1以前の方針） | Architecture Review 2（AR2-m-1）で、`upload`属性が存在するがcallableでない場合（`upload = None`／`upload = "not callable"`等）に`hasattr()`は`True`を返してしまい、実際の呼び出し時にPython標準の制御外`TypeError`（メッセージが本層の管理下にない）が発生するという失敗モードの未定義が指摘された。v6.11.0 `_get_client()`の`hasattr`のみの検証はこの限界を持ったまま運用されている先例だが、Release 6.12ではupload capabilityの呼び出し可能性まで保証するため、`callable(getattr(media_uploader, "upload", None))`＋固定messageへ強化した（AD-19） |
| 独自Protocol（`MediaUploaderLike` Protocol等）を新設し、`media_uploader`の型注釈をProtocolへ変更する | AD-19の`callable()`検証で十分に「upload capabilityを実際に呼び出せるobjectであること」を保証できる。Protocol新設は`typing.Protocol`によるstatic型チェックの利便性はあるが、Media Uploaderの実装が現時点で1つのみである以上、10章の既存判断（Protocol新設は時期尚早）を変更する理由にはならない |
| `inspect.signature()`等によるsignature introspectionを追加し、`image_bytes` / `filename` / `mime_type`のkeyword引数を受け付けるsignatureであることまで事前検証する | Architecture Review 3（AR3-m-1）で境界条件として指摘されたが、過剰設計（Wiring層がPythonのcallable実装の多様性に踏み込んだ検証責務を持つことになる）であり、Fake／Stub実装の柔軟性を不必要に制限する。実際の呼び出し時にPython runtimeが自然にTypeErrorを送出する仕組みを、本層が「予期しないException」として無変換伝播するだけで十分（AD-20） |
| filenameの内容検証（regex等）を本層でも重複実装する | `WordPressMediaUploader.upload()`が既にfail-fastで完全に検証しており、二重検証は責務の重複であり保守コストのみを増やす |
| `MediaUploadResult`を新しいResult型でラップして返す（例：`WiringResult(image, result)`） | 将来のArticle→featured_media Wiringが必要とするのは`media_id`のみであり、`GeneratedImage`自体を戻り値に含める必要性が確認できない。不要な型追加を避ける |
| `WordPressMediaUploadError`を新規Wiring専用Exceptionへ変換する | 変換の価値（呼び出し元にとっての利便性向上）が、reason保持・Security Contract再実装のコストに見合わない。既存Exceptionをそのまま伝播する方が単純である |
| 本Releaseに簡易CLI（`scripts/run_generated_image_upload.py`等）を含める | 実OpenAI Client・実WordPress Clientの構築（Environment Composition）を伴い、Release Scopeが本Foundationの単一責務を超えて拡大するため（26章） |
| `from_env()`を新規クラスに追加する | 新規Environment Variableを必要としない設計（AD-4）であり、`from_env()`を追加すると環境変数の読み込み責務が新層に生まれてしまう |

## 11. Responsibility Boundary

```text
本層の責務：
  GeneratedImageとfilenameを受け取り、WordPressMediaUploader.upload()へ委譲し、
  結果（MediaUploadResultまたはWordPressMediaUploadError）をそのまま呼び出し元へ返す

本層の責務でないもの：
  画像生成（prompt → GeneratedImage）        … ai_image_generation / openai_image_generation の責務
  filenameの内容検証（regex等）              … wordpress_media の責務
  WordPress認証・HTTP通信                    … wordpress_media の責務
  Article本文・featured_media_idへの反映     … 将来Release（候補D）の責務
  Composition Root配線・環境変数解決          … 将来のCaller（Pipeline／Composition Root）の責務
```

### 11.1 状態保持・実行モデル（Architecture Review 1 Finding AR1-S-1反映）

```text
GeneratedImageWordPressMediaUploaderは、Constructorで注入されたmedia_uploaderへの
    参照だけをインスタンス状態として保持する

GeneratedImage、filename、MediaUploadResult、image bytes、例外objectのいずれも
    インスタンス状態へ保存しない（upload()呼び出しごとに引数として受け取り、
    戻り値または例外として返すのみ）

新規classは同期API（sync）である。async実行はOut of Scope

新規class自身は、Constructor実行後に追加のmutable runtime stateを持たない
    stateless delegation componentである

thread safetyについて、新規class自身は追加のmutable stateを持たないため、
    複数threadから同時にupload()を呼び出しても新規class自身の内部状態は
    競合しない。ただし、thread safety全体は注入されたWordPressMediaUploaderの
    実装特性に依存し、Release 6.12ではWordPressMediaUploader自体のthread safetyを
    保証しない（WordPressMediaUploader側のContractはv6.9.0の責務であり、
    本Releaseでは変更しない）
```

## 12. Dependency Direction

```text
許可：
generated_image_wordpress_media → ai_image_generation（GeneratedImageのみ）
generated_image_wordpress_media → wordpress_media（WordPressMediaUploader, MediaUploadResultのみ）
generated_image_wordpress_media → standard library

禁止：
generated_image_wordpress_media → openai_image_generation
generated_image_wordpress_media → image_resolver
generated_image_wordpress_media → outputs（ArticleData / WordPressOutput含む）
generated_image_wordpress_media → ai（Agent層）
generated_image_wordpress_media → pipeline
generated_image_wordpress_media → workflow_engine
generated_image_wordpress_media → scheduler
generated_image_wordpress_media → retry_*（Retry Runtime全体）
generated_image_wordpress_media → scripts
generated_image_wordpress_media → requests（HTTP通信は行わない。通信はwordpress_media内部に閉じる）

逆依存禁止：
ai_image_generation → generated_image_wordpress_media
openai_image_generation → generated_image_wordpress_media
wordpress_media → generated_image_wordpress_media
```

```text
Dependency Diagram

ai_image_generation
    └── GeneratedImage
              │
              ▼
generated_image_wordpress_media
    └── GeneratedImageWordPressMediaUploader
              │
              ▼
wordpress_media
    ├── WordPressMediaUploader
    └── MediaUploadResult
```

`openai_image_generation`は本層の直接依存に含めない（AD-5）。`AIImageGenerator` Protocol自体も、本層が`generate()`を呼び出さないため依存に含めない。

## 13. Package Structure

```text
projects/03_game_content_ai/src/generated_image_wordpress_media/
├── __init__.py
└── generated_image_wordpress_media_uploader.py   # GeneratedImageWordPressMediaUploader
```

新規例外型を追加しないため（AD-11）、`wordpress_media`パッケージが採用した「例外は唯一の送出元となるモジュール内に定義し、別ファイルへ分割しない」という規約（`wordpress_media_upload_foundation.md` 82行目）を適用する対象自体が存在しない。

### 13.1 パッケージ名の検討

| 候補 | 却下／採用理由 |
|---|---|
| `generated_image_media_upload` | Media Uploadの提供元がWordPress限定であることが名前から読み取れない。将来複数CMS対応時に誤解を招く可能性がある |
| `image_media_upload` | 「生成された画像」であることが読み取れず、通常の画像ファイル全般を扱うパッケージと誤解されうる |
| `ai_image_media_upload` | 「AI」という語が`ai_image_generation` / `ai/`（Agent層）と紛らわしく、責務が生成側にあるという誤解を招く |
| **`generated_image_wordpress_media`（採用）** | `ai_image_generation.GeneratedImage`と`wordpress_media`という依存先2パッケージの名前をそのまま連結しており、責務・依存先の両方が名前から一意に読み取れる。既存`wordpress_media`との命名対称性も保たれる |

`upload`という動詞を含めなかった理由：既存パッケージ命名規則（`wordpress_media` / `ai_image_generation` / `retry_queue`等）は一貫して動詞ではなく名詞（ドメイン）でパッケージを命名しており、動作（Upload）はクラス名（`GeneratedImageWordPressMediaUploader`）側で表現する方が既存規則に整合する。

**package名は`generated_image_wordpress_media`として正式確定する**（AD-2、Architecture Review 1 Finding AR1-m-4反映）。Architecture Review 1以前の初稿では本文書末尾のOpen Questionsに「採用可否の確認」を残していたが、上記比較・既存命名規則との整合性検証により確定済みであり、以後Open Questionsからは削除する（43.6節）。

## 14. Public API

`src/generated_image_wordpress_media/__init__.py`が公開するのは次の1つのみとする。

```python
from .generated_image_wordpress_media_uploader import GeneratedImageWordPressMediaUploader

__all__ = ["GeneratedImageWordPressMediaUploader"]
```

```python
class GeneratedImageWordPressMediaUploader:
    def __init__(
        self,
        media_uploader: WordPressMediaUploader,
    ) -> None:
        ...

    def upload(
        self,
        image: GeneratedImage,
        filename: str,
    ) -> MediaUploadResult:
        ...
```

`MediaUploadResult` / `WordPressMediaUploadError`は本パッケージからは再公開しない。呼び出し元が例外を捕捉する場合は、既存の`wordpress_media`から直接importする（Public APIの二重定義を避ける）。

### 14.1 Constructor Contract

```text
media_uploader: WordPressMediaUploader を必須の位置引数として受け取る
isinstance(media_uploader, WordPressMediaUploader) によるnominal型検証は行わない（AD-18、Duck Typing Injection）
Constructor時点ではcallable()検証も行わない（検証はupload()実行時に遅延させる。14.3節・AD-19）
デフォルト値なし（省略不可）
Constructorは代入のみを行い、他の処理を行わない（self._media_uploader = media_uploader）
```

不正な`media_uploader`（`upload`属性が存在しない、または存在してもcallableでない）をConstructorへ注入すること自体は失敗しない。生成（`__init__`）は常に成功し、失敗は`upload()`呼び出し時（14.3節）まで遅延する。

### 14.2 なぜProtocolを新設しないか

10章「Rejected Alternatives」参照。`Media Uploader`の実装は現時点で`WordPressMediaUploader`の1つのみであり、抽象化の必要性を裏付ける2つ目の実装が存在しない。AD-19の`callable()`遅延検証により、Protocolを新設しなくても「upload capabilityを実際に呼び出せるobjectであること」は実行時に保証される。

`media_uploader`に対してDuck Typing（`callable()`検証）を採用する理由と、`image`に対してnominal型検証（`isinstance()`）を採用する理由（AD-7）は非対称であるが、これは意図的な設計判断である。両者の対比は15.1節で一元的に説明する。

### 14.3 media_uploader Capability Contract（Architecture Review 1 Finding AR1-m-2、Architecture Review 2 Finding AR2-m-1反映、最終形）

```text
検証内容：callable(getattr(self._media_uploader, "upload", None))
検証タイミング：遅延検証。upload()メソッドが実行され、self._media_uploaderを
    利用する直前（v6.11.0 OpenAIImageGenerator._get_client()と同型のタイミング）
不適合条件：
    upload属性が存在しない
    または
    upload属性は存在するがcallableでない（例：upload = None、upload = "not callable"）
不適合時：TypeError（固定messageのみ。20章・21章参照）
固定message：
    "media_uploader must provide a callable upload method"
    （完全一致でTest可能なContractとする。31.4節）
Constructor時点での検証：行わない（Constructor Injection自体は無条件に受け付ける、14.1節）
isinstance()によるnominal型検証：行わない（Duck Typingを維持し、
    WordPressMediaUploaderのsubclass化を要求しない）
新規Protocol：新設しない（14.2節）
```

**固定messageに含めないもの**（20.2節・21.5節と同一Contract）：

```text
repr(media_uploader) / str(media_uploader)
dependencyのclass名
media_uploaderの内部状態
credential
Authorization header
filename
image bytes
MIME type
```

**引用の訂正（Architecture Review 2 Finding AR2-m-1反映）**：v6.11.0（`openai_image_generator.py:257-270 _get_client()`）は`hasattr(self._client, "with_options")`による遅延Duck Typing検証を行い、不適合の場合`TypeError`を送出している。これは属性の**存在**のみを確認するものであり、callableであることまでは保証しない。Release 6.12は同じ遅延Duck Typing方針を踏襲しつつ、`callable(getattr(media_uploader, "upload", None))`によりupload capabilityが実際に呼び出し可能であることまでContractとして保証する。**v6.11.0と完全に同一の検証ではない**（v6.11.0はhasattrのみ、Release 6.12はcallable検証まで含む）。Python標準の「非callable呼び出し時TypeError」（例："'NoneType' object is not callable"、本層が制御しないmessage）へ委ねることはせず、Wiring層自身が呼び出し前に検出し、上記の安全な固定messageで送出するContractとする。

**callable検証の保証範囲（Architecture Review 3 Finding AR3-m-1反映、AD-20）**：`callable(getattr(self._media_uploader, "upload", None))`が保証するのは「`media_uploader.upload`が呼び出し可能なobjectであること」のみである。`image_bytes` / `filename` / `mime_type`というkeyword引数を実際に受け付けるsignatureであることまでは、この検証では保証しない。例えば`def upload(self) -> None: pass`のようなsignatureを持つobjectは、`callable()`検証を通過するが、実際の呼び出し（28章 Runtime Flowのステップ3）でPython標準の`TypeError`（例：`unexpected keyword argument`。具体的な文言はPython versionや関数定義形態に依存するため固定Contractにしない）を送出する。本層はこれをsignature introspection（`inspect.signature()`等）で事前検証せず、20章「signature不一致」Contractのとおり「予期しないException」として無変換伝播する（Architecture Review 5 Finding AR5-S-1反映：相互参照先を28章 Runtime Flowへ明確化）。

### 14.4 なぜ`from_env()`を持たないか

`WordPressMediaUploader`は既に`from_env()`（`WP_SITE_URL` / `WP_USERNAME` / `WP_APP_PASSWORD`）を持つ。本層に`from_env()`を追加すると、環境変数の読み込み責務が新層と`wordpress_media`の2箇所に分散する。呼び出し元（将来のPipeline／Composition Root）が`WordPressMediaUploader.from_env()`を呼び出し、その結果を本層のConstructorへ注入する設計とすることで、本層は環境変数を一切知らない状態を維持できる（AD-4）。

## 15. Input Contract

`upload(image: GeneratedImage, filename: str) -> MediaUploadResult`

```text
image：GeneratedImage型のみ許可。isinstance(image, GeneratedImage)で検証し、
       不一致の場合はValueErrorを送出してmedia_uploaderのcapability検証・
       WordPressMediaUploader.upload()いずれも実行しない
filename：str型。内容検証は行わない（16章）
```

`image_bytes` / `mime_type`個別の型・非空検証は行わない。理由：`GeneratedImage`は`__post_init__`（v6.10.0 Contract）で既に検証済みの値のみを保持することが保証されているため、Wiring層での再検証は責務の重複である。

### 15.1 imageとmedia_uploaderで検証方針が異なる理由（Architecture Review 2 Finding AR2-m-4反映）

`upload()`は2つの入力を受け取るが、それぞれ性質が異なるため、意図的に非対称な検証方針を採用する。

```text
image（GeneratedImage）：
    性質：値object（Value Object）
    検証方法：isinstance(image, GeneratedImage) による厳密なnominal型検証（AD-7）
    理由：GeneratedImage.__post_init__（v6.10.0 Contract）が既にimage_bytes／
        mime_typeの内容を検証済みであることを前提とし、本層はその内容を
        再検証しない（18.1節）。この「検証済みであることの信頼」を安全に
        成立させるには、渡された値が実際にGeneratedImageのConstructorを
        経由して生成されたinstanceであることをisinstance()で保証する必要がある。
        単にimage_bytes／mime_type属性を持つだけの構造的に類似したobject
        （Duck Typing）では、__post_init__の検証を経ていない可能性があり、
        本層が「再検証しない」という設計判断の前提が崩れる

media_uploader（WordPressMediaUploader）：
    性質：注入されるcollaborator（依存先サービス）
    検証方法：callable(getattr(media_uploader, "upload", None)) による
        遅延Duck Typing検証（AD-19、14.3節）。isinstance()によるnominal型検証は行わない
    理由：テスト時にFake／Stubを注入できることを最優先する。呼び出し元が
        必要とするのは「upload(image_bytes, filename, mime_type)相当を
        呼び出せるcollaboratorであること」という振る舞い上のcapabilityのみであり、
        WordPressMediaUploaderのsubclassである必要はない

非対称性の要約：
    image：値object → 構築経路（__post_init__）への信頼を担保するため厳密型検証
    media_uploader：collaborator → テスト容易性を優先するためcapability検証
    この非対称性は意図的な設計判断であり、統一（両方をisinstance()にする、
    または両方をDuck Typingにする）を必要としない
```

## 16. Filename Contract

```text
型：str
供給者：呼び出し元が明示的に渡す（GeneratedImageからは生成しない。固定命名規則も導入しない）
本層での内容検証：なし
```

filenameの型・空文字・空白のみ・前後空白・最大長・許可文字・パス区切り文字・拡張子要否・ディレクトリ部分許可・normalize・自動修正のいずれも、**本層では規定しない**。これらはすべて`WordPressMediaUploader.upload()`の既存Upload Input Contract（`wordpress_media_upload_foundation.md` 14章、正規表現`^[A-Za-z0-9][A-Za-z0-9._-]*$`）へ完全に委譲する。

```text
Wiring層で検証しない理由：
  WordPressMediaUploader.upload()は、HTTP送信前にfilenameをfail-fastで検証し、
  不正時にValueErrorを送出することが既に保証されている（Processing Order 1番目）。
  本層で同じ正規表現・同じ検証ロジックを再実装すると：
    - 2箇所の検証ロジックが将来ズレるリスクが生じる
    - 本層が「filenameの正しい形式」というwordpress_media固有の知識を持つことになり、
      責務境界（11章）に違反する
  よって、本層はfilenameをそのまま右から左へ受け渡すのみとし、
  検証はwordpress_media側の既存Contractに一元化する。
```

## 17. MIME Type Contract

```text
GeneratedImage.mime_type を、そのまま upload() の mime_type 引数へ渡す
filename拡張子との整合性確認：行わない
不一致時の拒否：行わない
自動拡張子書き換え：行わない
MIME typeからのfilename自動生成：行わない
```

整合性検証を行わない理由：`wordpress_media_upload_foundation.md`自身が「MIME許可リスト・拡張子との一致…はOut of Scope」（236行目）としており、本層で新たにこの検証を導入すると、依存先が持たない責務を上位層が代わりに持つという逆転が生じる。整合性保証は、将来この層を呼び出すCaller（Pipeline／Composition Root）の責務とする。

## 18. Image Bytes Contract（Architecture Review 1 Finding AR1-m-3反映）

```text
GeneratedImage.image_bytes の値を変更せず、WordPressMediaUploader.upload() の
image_bytes 引数へ渡す（値の等価性のみをPublic Contractとする）

値の変更：なし
変換：なし
圧縮：なし
リサイズ：なし
再エンコード：なし
内容検査：なし（GeneratedImage.__post_init__で保証済み、18.1節）
最大サイズ再検証：なし
```

`bytes`はPythonの不変型（immutable）であるため、コピーの有無・object identity（`is`比較の結果）は呼び出し元から通常観測不能であり、Release 6.12のPublic Contractとしない。同一object参照を渡すかコピーを渡すかは実装詳細であり、Architecture Designはこれを規定しない。Test Strategy（31.1節）も値の等価性（`==`）のみを検証対象とし、object identityの検証は行わない。

初稿（Architecture Review 1以前）は「同一bytes object参照のまま渡す（コピーを行わない）」という記述をPublic Contractとして明記していたが、Architecture Review 1（AR1-m-3）で、不変型に対してobject identityを公開Contract化する必要性が薄いことを指摘され、本節のとおり値の等価性へ改めた。

### 18.1 空bytes・内容検査に関する既存Contractとの関係

```text
GeneratedImage側：__post_init__（v6.10.0）で image_bytes が非空 bytes であることを既に保証
WordPressMediaUploader側：_validate_image_bytes()（v6.9.0）で bytes型・非空を再度検証
本層：いずれの検証も重複実装しない（責務境界、11章）
```

## 19. Output Contract

```text
WordPressMediaUploader.upload() の戻り値（MediaUploadResult）をそのまま返す
新しいResult型でラップしない
GeneratedImageとMediaUploadResultの両方は返さない
media_idのみを取り出して返すこともしない（MediaUploadResult全体を保つ）
```

`MediaUploadResult`全体（`media_id` / `source_url` / `mime_type`）を保持したまま返す理由：将来のArticle→featured_media Wiring（候補D）が`source_url`を必要とする可能性を排除しないため（候補Dの正式スコープはRelease 6.13で確定する）。

## 20. Error Contract（Architecture Review 1 Finding AR1-m-2、Architecture Review 2 Finding AR2-m-1反映、最終形）

```text
image が GeneratedImage 型でない
    → ValueError（Wiring層が送出、20.2節）
    → media_uploaderのcapability検証・WordPressMediaUploader.upload()いずれも実行しない

media_uploader.upload が存在しない、または存在してもcallableでない
  （callable(getattr(media_uploader, "upload", None)) が False）
    → TypeError（Wiring層が送出、固定message"media_uploader must provide a
       callable upload method"、14.3節・AD-19・20.2節）
    → WordPressMediaUploader.upload()相当の処理は実行しない

media_uploader.upload はcallableだが、image_bytes／filename／mime_typeの
  keyword引数を受け付けないsignatureである（Architecture Review 3 Finding
  AR3-m-1反映、AD-20）
    → callable検証（上記）は通過する（callableであることのみを保証するため）
    → 実際の呼び出し（28章 Runtime Flowのステップ3）でPython標準のTypeErrorが発生する
       （Architecture Review 5 Finding AR5-S-1反映：相互参照先を28章へ明確化）
    → 送出主体：Python runtime／下流呼び出し境界（Wiring層自身は送出しない）
    → Wiring層の扱い：catchしない／変換しない／ラップしない／抑制しない／
       固定messageへ書き換えない。「WordPressMediaUploadError以外の
       予期しないException」（下記）として無変換伝播する
    → capability検証失敗のTypeError（Wiring層送出・固定message）とは
       送出主体・message Contractの両方で明確に区別する（20.3節）

filename 不正
    → 検証主体：WordPressMediaUploader（既存WordPress Media Upload Contract、
       v6.9.0 14章）。Wiring層で重複検証しない

image_bytes 不正
    → 検証主体：GeneratedImage.__post_init__（v6.10.0）および
       WordPressMediaUploader（v6.9.0）の既存Contract。Wiring層で重複検証しない

mime_type 不正
    → 検証主体：GeneratedImage.__post_init__（v6.10.0）および
       WordPressMediaUploader（v6.9.0）の既存Contract。Wiring層で重複検証しない

WordPressMediaUploader.upload() が送出する WordPressMediaUploadError
  （filename不正／mime_type不正／通信失敗／非2xxレスポンス／レスポンス不正等）
    → ラップせずそのまま伝播する

WordPressMediaUploadError 以外の予期しない Exception
    → catchしない／変換しない／ラップしない／抑制しない。そのまま伝播する

KeyboardInterrupt／SystemExit
    → catchしない。そのまま伝播する（BaseExceptionのcatchは行わない。
       Exceptionのsubtypeとして誤って扱わない）

Exception Chaining
    → Wiring層自身が新規raiseするのは ValueError（image型不正）と
       TypeError（media_uploader capability不正）の2種類のみであり、
       いずれも下位例外が存在しない前提（新規raiseであり、他の例外を
       catchしてfrom節で連結する操作は行わない）。
       WordPressMediaUploadError はそのまま再raiseするため、
       chaining操作自体が発生しない
```

**主Contract（Architecture Review 2 Finding AR2-m-2反映）**：本層は、下流（`WordPressMediaUploader.upload()`）から発生した例外を**catch・変換・ラップ・抑制しない**。これは`WordPressMediaUploadError`・その他の予期しない`Exception`のいずれにも適用され、`KeyboardInterrupt` / `SystemExit`のような`BaseException`のsubtypeも同様にcatchしない（本層はこれらを`Exception`の下位として誤って扱わない）。

これは振る舞いレベルのArchitecture Contractであり、実装syntaxそのもの（`try`／`except`文の使用有無）を規定するものではない。Release 6.12の想定実装では、この振る舞いを下流例外捕捉用の`try`／`except`を設けずに実現できる（本層はimageとmedia_uploaderの検証以外に何も判断せず、下流呼び出しの結果をそのまま返す／そのまま伝播させるだけで足りるため）。ただし、これは実装上の帰結であって、Architecture Contract自体が`try`／`except`という構文の使用を禁止するものではない。将来、例外を捕捉しない安全なcleanup（例：`try`／`finally`。`except`節を伴わず、例外を捕捉・変換・抑制しない）が必要になった場合、それは本Contract（catch・変換・ラップ・抑制しない）に違反しない。ただし、Release 6.12自身はresource cleanupを一切行わないため、そのようなcleanup機構は本Releaseの実装には含まれない（Out of Scope）。

### 20.1 新規Exception型を導入しない理由

- モデルA採用（9章）により、本層が能動的に判定するFailure Domainは実質的に「`image`がGeneratedImage型でない」「`media_uploader`のcapability（callableなupload属性）が不足している」の2種類のみであり、新たなOrchestration Errorで包む必要性がない。signature不一致・dependency内部の失敗（AD-20、20.3節）は本層が能動的に判定する対象ではなく、下流（Python runtime／注入されたdependency自身）が呼び出し境界で自然に送出するものを無変換伝播するだけであるため、この2種類のカウントには含めない。
- `WordPressMediaUploadError`は既にSecurity Contract（`response.text` / credential / image bytes非露出）を満たした状態で例外化されている（`wordpress_media_upload_foundation.md` 18-19章）。これを再ラップすると、Security Contractの再実装コストが発生するだけで利益がない。
- **呼び出し元への分類保証は、Wiring層が能動的に送出する例外に限定する**（Architecture Review 4 Finding AR4-m-1反映、20.4節）。呼び出し元は、画像型が不正だったのか（`ValueError`）、`media_uploader`のcapability自体が不正だったのか（Wiring層送出の固定message `TypeError`）は、それぞれ例外型・固定messageとの完全一致によって確実に識別できる。一方、それ以外のあらゆる下流由来の失敗（`WordPressMediaUploadError`・signature不一致による`TypeError`・dependency内部処理が送出する`TypeError`・その他の予期しない`Exception`）は、単一の曖昧な例外へ潰してはいないものの、下流由来の`TypeError`同士（signature不一致か、dependency内部のTypeErrorか、その他かの区別）を呼び出し元が安定的に分類できることまでは保証しない（詳細は20.4節）。

### 20.2 `ValueError`・`TypeError`のメッセージContract（Architecture Review 2・3 Finding反映、最終形）

```text
ValueError（image引数がGeneratedImage型でない場合）：
    型名のみを含め、渡された値そのもの（object repr等）は含めない
    （具体的な文言は本Architecture Designでは確定しない。Implementation段階で
     既存プロジェクトの文体に合わせて確定する。完全一致Testの対象とはしない）

TypeError（capability検証失敗：media_uploader.uploadが存在しない、
または存在してもcallableでない場合）：
    固定messageを次のとおり正式に確定する（Architecture Contract、完全一致でTest可能）：

        "media_uploader must provide a callable upload method"

    以下はメッセージへ含めない：
      dependency objectのrepr（repr(media_uploader) / str(media_uploader)）
      dependencyのclass名
      media_uploaderの内部状態
      credential
      Authorization header
      image bytes
      filename
      MIME type

TypeError（signature不一致：media_uploader.uploadはcallableだが、
image_bytes／filename／mime_typeのkeyword引数を受け付けない場合、AD-20）：
    Wiring層固有の固定Contractではない（完全一致Testの対象外）
    Python runtimeが生成する標準messageをそのまま伝播する
    （例：unexpected keyword argument。Python versionや関数定義形態に
     依存し得るため、本Architecture Designでは文言を固定しない）
    Wiring層はこのmessageへ一切手を加えない（生成もしない、書き換えもしない）
```

`capability検証失敗`の固定messageのみを完全一致Testの対象とする理由：`callable(getattr(media_uploader, "upload", None))`という単一の判定式に対する唯一の失敗理由（upload属性の不在／非callable）であり、Architecture Design段階で文言を確定させても実装の柔軟性を損なわない。一方`ValueError`（image型不正）と`signature不一致TypeError`は、それぞれ「型名を含め、値は含めない」という構造的Contractのみ、または「Wiring層は関与しない」という送出主体の区別のみを固定し、具体的な文言はImplementation段階の裁量またはPython runtimeに委ねる。

### 20.3 TypeError分類（Architecture Review 3・4 Finding反映、最終形）

同じ`TypeError`型であっても、送出主体・message Contract・Failure Domainが異なる例外が複数存在する。大分類として、まず「Wiring層が能動送出するTypeError」と「下流から伝播するTypeError」の2つに分ける。

**Wiring層が能動送出するTypeError**

| # | 分類 | 条件 | 例外型 | 固定message | 呼び出し元による識別 |
|---|---|---|---|---|---|
| 2 | media_uploader capability不正 | `upload`属性なし、または存在してもcallableでない | `TypeError` | あり："media_uploader must provide a callable upload method" | 固定messageとの完全一致により識別可能（20.4節） |

**下流から伝播するTypeError（Wiring層は送出しない、無変換伝播のみ）**

| # | 分類 | 条件 | 例外型 | 固定message | 呼び出し元による識別 |
|---|---|---|---|---|---|
| 3 | media_uploader signature不正 | `upload`はcallableだが、必要なkeyword引数を受け付けない | `TypeError` | なし（Python標準message、AD-20） | 本層は保証しない（20.4節） |
| 3.5 | dependency内部TypeError | `upload()`のsignatureは適合するが、dependency内部処理がTypeErrorを送出する | `TypeError` | なし（dependency実装依存message） | 本層は保証しない（20.4節） |

**その他の分類（参考）**

| # | 分類 | 条件 | 例外型 | 送出主体 | 固定message |
|---|---|---|---|---|---|
| 1 | image型不正 | `not isinstance(image, GeneratedImage)` | `ValueError` | Wiring層 | なし（型名のみのContract、20.2節） |
| 4 | WordPress Media Upload失敗 | `WordPressMediaUploader.upload()`内部の失敗 | `WordPressMediaUploadError` | wordpress_media（既存Contract） | wordpress_media側Contract（v6.9.0） |
| 5 | その他のException | 上記以外の下流例外 | 任意 | 下流（Fake／実装依存） | 無変換伝播、Wiring層は関与しない |
| 6 | KeyboardInterrupt／SystemExit | 割り込み・終了要求 | `BaseException`のsubtype | Python runtime | catchしない、無変換伝播 |

分類3（signature不正）・分類3.5（dependency内部TypeError）・分類5の一部（下流実装が独自に送出する任意のTypeError）は、いずれも「Wiring層が送出しない、固定messageを持たない`TypeError`」という点で構造的に同一であり、呼び出し元がこれらを`str(exc)`の内容だけで相互に区別できる保証はない（20.4節）。**下流TypeError間の相互分類は、本層のPublic Contractではない。**分類3・3.5はいずれも分類5（その他のException）の特殊ケースであり、Wiring層の処理（catchしない・変換しない・ラップしない・抑制しない）は分類5と同一である。

### 20.4 呼び出し元への分類保証範囲（Architecture Review 4 Finding AR4-m-1反映）

**保証できる分類**：

```text
TypeErrorのmessageが、

    "media_uploader must provide a callable upload method"

と完全一致する場合、それはWiring層が能動的に送出した
media_uploader capability不正TypeError（20.3節分類2）である。

これはPublic Contractとして保証する。
```

**保証できない分類**：

```text
TypeErrorのmessageが固定messageと一致しない場合、
呼び出し元が判断できるのは
「capability不正TypeErrorではない」ということだけである。

固定messageとの不一致は、次のいずれであるかを積極的に証明しない：

    signature不一致TypeError（20.3節分類3）
    dependency内部TypeError（20.3節分類3.5）
    その他の下流TypeError（20.3節分類5）

固定messageとの不一致は、signature不一致であることを積極的に意味しない。
```

**呼び出し元への保証のまとめ**：

```text
呼び出し元は、固定messageと完全一致するTypeErrorを
capability不正として識別できる。

それ以外のTypeErrorについて、signature不一致・dependency内部失敗・
その他の下流失敗を安定的に分類できる保証は本層にはない。
```

次のような利用方法は、本層のContractが保証する範囲を超えるため推奨しない：

```text
except TypeErrorだけで送出主体を分類する
固定messageと不一致ならsignature不一致であると判断する
Python標準messageを解析して下流TypeErrorを安定的に分類する
```

呼び出し元がsignature不一致・dependency内部TypeError・その他の下流TypeErrorを区別する必要がある場合は、本層の外側（例えば注入する`media_uploader`実装自体、またはCaller側の追加検証）で解決すべき事項であり、本層のPublic Contractの対象外とする。

## 21. Security Contract（Architecture Review 1 Finding AR1-m-1反映、最終形）

初稿（Architecture Review 1以前）は「本層はimage bytesを扱わない」「本層は新たな秘密情報を扱わない」という表現を用いていたが、これは18章 Image Bytes Contract（`image.image_bytes`を`WordPressMediaUploader.upload()`へ渡す）と字義上の緊張関係にあった。本層は実際には`GeneratedImage.image_bytes`を**参照し、`WordPressMediaUploader`へ転送する**。Architecture Review 1（AR1-m-1）を踏まえ、Security Contractを以下のとおり正確な表現へ改める。

### 21.1 image bytes

```text
参照する（GeneratedImage.image_bytesへアクセスする）
WordPressMediaUploaderへ転送する（upload()の引数として渡す）

以下は行わない：
    検査（内容の解析・検証）
    変換（画像形式の変換）
    圧縮
    リサイズ
    永続化（ファイル・DB等への保存）
    キャッシュ
    ログ出力
    repr表示（GeneratedImage.image_bytesはrepr=False。本層がこれを再露出する処理を追加しない）
    例外messageへの埋め込み
    インスタンス状態としての追加保持（Constructorが保持するのはmedia_uploaderへの
        参照のみであり、upload()呼び出し中に受け取ったimageやimage_bytesを
        インスタンス属性へ保存しない）
```

### 21.2 filename

```text
WordPressMediaUploaderへ転送する（upload()の引数として渡す）

以下は行わない：
    ログ出力
    Wiring層自身が送出する例外（ValueError / TypeError）のmessageへの値の埋め込み
        （image型不正・media_uploader capability不正のいずれも、filenameの値を
         必要としない例外であるため）
    インスタンス状態としての保存
```

filenameは呼び出し元から受け取り転送する値であり、credential等とは異なり全面的に「扱わない」とは言えない。転送はするが、ログ・本層自身の例外messageには含めない、という区別を明示する。

### 21.3 MIME type

```text
GeneratedImage.mime_type を WordPressMediaUploader.upload() の mime_type 引数へ転送する
本Releaseでは新規Loggingを追加しないため（22章）、MIME typeを含め、
    いかなる値も安全な診断情報としてログへ出力する設計にはしない
```

### 21.4 「扱わない」と明記できる対象（本層が一切アクセス・保持・転送しないもの）

```text
OPENAI_API_KEY（OpenAI認証情報。本層はopenai_image_generationに依存しない）
WordPress username（WordPressMediaUploaderの内部状態。本層は注入済みインスタンスの
    site_url / username / app_passwordへ一切アクセスしない）
WordPress password（同上）
Authorization header（本層はHTTPヘッダーを直接構築しない）
prompt（本層はpromptを一切受け取らない。モデルA、9章）
Provider response body（本層はHTTPレスポンスを直接受け取らない）
Provider例外object（WordPressMediaUploadErrorをそのまま伝播するのみで、
    新たな例外object保持は行わない）
```

### 21.5 dependency object（media_uploader）

```text
repr(media_uploader) / str(media_uploader)：本層の例外messageへ含めない（20.2節）
dependencyのclass名：本層の例外messageへ含めない（20.2節、固定message
    "media_uploader must provide a callable upload method"のみを使用する）
media_uploaderの内部状態：本層は一切アクセスしない
    （callable(getattr(media_uploader, "upload", None))によるcapability確認のみ）

下流TypeError（20.3節分類3：signature不一致、分類3.5：dependency内部TypeError、
    分類5の一部：その他の下流Exception）のmessage：本層はこれらのmessageを
    生成しない（Python runtime／注入されたdependency自身が送出するmessageを
    そのまま伝播するのみ）。したがって、本層自身がrepr(media_uploader)／
    str(media_uploader)／dependencyのclass名／credential等を追加で埋め込む
    余地自体が存在しない（Architecture Review 4 Finding AR4-m-1反映）。
    ただし、これらのmessage自体にdependency名・引数名・その他の情報が
    含まれるかどうかは、本層のSecurity Contractの対象外とする（呼び出し
    境界でPythonまたは注入されたdependencyが生成するmessageの内容は、
    Python runtime自体または注入されたdependency実装側の責務であり、
    本層が制御できるものではない）。「Wiring層が情報を追加しないこと」と
    「下流messageに情報が含まれないこと」を混同しない。下流TypeErrorが
    安全な固定messageであることは、本層のContractとして保証しない
```

本層は`print()` / `logging`のいずれも行わない（22章）。本章（Security Contract）は28章 Runtime Flow・29章 Sequence Diagram・30章 Failure Flowと同期しており、image bytes・filenameが本層を実際に通過する（＝転送される）という事実と矛盾しない。

## 22. Logging Contract

```text
新規Loggingなし
既存loggerの注入：行わない
将来Releaseへの先送り：本層を呼び出すCaller側の責務とする（Pipeline層のLogging方針に委ねる）
```

理由：単一責務と情報非露出（21章）を優先する。`image_bytes`をログに含めるリスクを構造的に排除するため、ログ出力機構自体を持たない設計とする。

## 23. Retry Contract

```text
Wiring層独自Retryなし
WordPressMediaUploaderの既存挙動（Retry設定を含む）を変更しない
OpenAI SDK Retry設定（v6.11.0 max_retries=0）に一切関与しない（本層はopenai_image_generationに依存しないため、そもそも接点がない）
Retry Runtimeへの接続：行わない
```

Retry統合はFuture Extension候補（40章）。

## 24. Dry Run Contract

**Out of Scope。**

理由：

```text
Media Uploadを行わないDry Runの戻り値Contractが未確立
本Releaseの単一責務（GeneratedImage → MediaUploadResultの委譲）を超える
将来のPipeline／CLI側で設計するほうが自然（26章のCLI Out of Scopeとも整合）
```

## 25. Environment／Configuration Contract

```text
新規Environment Variable：なし
from_env()：本層には持たせない（14.4節）
Composition Root：本Releaseでは追加しない（将来のPipeline統合Releaseで検討）
既存from_env()の呼び出し：Callerが WordPressMediaUploader.from_env() を呼び出し、
                           その結果を本層のConstructorへ注入する（Callerの責務）
```

本層自体は環境変数を直接読まない設計を採用する（Goals 3・Non-Goalsに整合）。

## 26. CLI／Entry Point Contract

**Out of Scope。**

```text
新規CLI：追加しない
scripts/へのEntry Point：追加しない
手動画像生成＋Uploadコマンド：追加しない
Environment Composition（実OpenAI Client・実WordPress Clientの構築配線）：追加しない
実OpenAI Client生成：本Releaseでは発生しない
実WordPress Client生成：本Releaseでは発生しない
```

CLIまで含めるとRelease Scopeが本Foundationの単一責務を超えて拡大し、Release名・分類・テスト範囲の再評価が必要になる（10章「本Releaseに簡易CLIを含めることを却下」）。CLI／Composition RootはRelease 6.12の対象外とし、将来Releaseの候補とする（40章）。

## 27. Article／featured_media Boundary

以下は明確にOut of Scopeとする：

```text
image_resolver.pyの改修
ArticleData.featured_media_idへの反映
WordPressOutputへのmedia_id接続
投稿本文への画像挿入
アイキャッチ画像設定
記事生成Pipelineへの統合
```

### 27.1 将来Release候補（依存関係）

```text
Release 6.13候補（仮）：Article → featured_media Wiring
  依存：本Release（v6.12.0）が返すMediaUploadResult.media_id
  変更対象候補：image_resolver.py / ArticleData / WordPressOutput
  ROADMAP記載（734-738行目）どおり、image_resolver.py / ArticleData / WordPressOutputへの
  変更を伴うため、本Release完了後に独立したArchitecture Reviewを要する
```

## 28. Runtime Flow（Architecture Review 1・2・3 Finding反映、確定形）

```text
Caller（本Releaseでは未実装＝Consumer-less。将来のPipeline／Composition Root）
  → GeneratedImageWordPressMediaUploader(media_uploader).upload(image, filename)
      1. isinstance(image, GeneratedImage) を検証。不適合なら ValueError（20章）
      2. callable(getattr(self._media_uploader, "upload", None)) を検証（遅延検証）。
         不適合なら TypeError（固定message、20章・14.3節・AD-19）
      3. self._media_uploader.upload(
             image_bytes=image.image_bytes,
             filename=filename,
             mime_type=image.mime_type,
         ) を keyword引数で呼び出す
         ※ upload methodがcallableであっても、image_bytes／filename／mime_type
            というkeyword引数を受け付けないsignatureである場合、本ステップで
            Python標準のTypeError（signature不一致、AD-20・20.3節）が発生する。
            Wiring層はこれを捕捉・変換せず、そのまま呼び出し元へ伝播する
            （ステップ2のcapability検証とは異なる、Wiring層が関与しない例外である）
      4. WordPressMediaUploader内部Contract（v6.9.0 14〜18章）がfilename／mime_type／
         image_bytesを検証し、HTTP通信を実行する
      5. MediaUploadResult を受け取り、そのまま返す
  → Caller
```

**検証順序は固定Contractである**：ステップ1（image検証）はステップ2（media_uploader capability検証）より必ず先に実行する。image・media_uploaderの両方が不正な場合、ステップ1で`ValueError`が送出され、ステップ2（capability検証）・ステップ3（`WordPressMediaUploader.upload()`相当の呼び出し）はいずれも実行されない。image検証を通過した場合に限り、media_uploader capability検証（ステップ2）を行う。media_uploader capability検証が失敗した場合、`WordPressMediaUploader.upload()`は呼び出されない。ステップ2（capability検証）を通過した場合でも、ステップ3でsignature不一致による`TypeError`が発生し得る（上記注記）。この順序はRuntime Flow・Sequence Diagram（29章）・Failure Flow（30章）・Test Strategy（31.2節）・Acceptance Criteria（41章）で一貫している。

引数の渡し方：`WordPressMediaUploader.upload(self, image_bytes: bytes, filename: str, mime_type: str)`（v6.9.0、positional-or-keyword）に対し、本層はkeyword引数（`image_bytes=` / `filename=` / `mime_type=`）で呼び出す。既存signatureを実コードで確認済みであり（7.1節）、keyword呼び出しが可能であることを確認している。keyword引数を用いる理由：3引数の並び順に依存せず、`WordPressMediaUploader.upload()`側の将来的な引数順変更（シグネチャ自体の変更はConstructor変更同様Public API変更に該当し、本来単独では起きないはずだが）に対しても呼び出し側の意図が読み取りやすいため。

## 29. Sequence Diagram

### 29.1 正常系

```text
Caller
  │
  ├─▶ GeneratedImageWordPressMediaUploader.upload(image, filename)
  │       │
  │       ├─▶ isinstance(image, GeneratedImage)  … OK
  │       │
  │       ├─▶ callable(getattr(self._media_uploader, "upload", None))  … OK（遅延検証）
  │       │
  │       ├─▶ WordPressMediaUploader.upload(
  │       │       image_bytes=image.image_bytes, filename=filename, mime_type=image.mime_type)
  │       │       │
  │       │       ├─▶ Upload Input Contract検証（wordpress_media内部、14章）
  │       │       ├─▶ requests.post(...)（wordpress_media内部）
  │       │       └─▶ MediaUploadResult
  │       │
  │       └─◀ MediaUploadResult
  │
  └─◀ MediaUploadResult
```

### 29.2 失敗系（image型不正）

```text
Caller
  │
  └─▶ GeneratedImageWordPressMediaUploader.upload(image, filename)
          │
          ├─▶ isinstance(image, GeneratedImage)  … NG
          │
          └─▶ raise ValueError（media_uploaderのcallable検証・
               WordPressMediaUploader.upload()いずれも呼び出されない。
               imageとmedia_uploaderの両方が不正な場合も本経路のみが発生する、28章）
```

### 29.3 失敗系（media_uploader capability不正、Architecture Review 1 Finding AR1-m-2、Architecture Review 2 Finding AR2-m-1反映）

```text
Caller
  │
  └─▶ GeneratedImageWordPressMediaUploader.upload(image, filename)
          │
          ├─▶ isinstance(image, GeneratedImage)  … OK
          │
          ├─▶ callable(getattr(self._media_uploader, "upload", None))  … NG
          │       （upload属性が存在しない、または存在してもcallableでない
          │        いずれの場合も本経路に合流する）
          │
          └─▶ raise TypeError（固定message"media_uploader must provide a
               callable upload method"。WordPressMediaUploader.upload()
               相当の処理は呼び出されない）
```

### 29.4 失敗系（media_uploader signature不正、Architecture Review 3 Finding AR3-m-1反映）

```text
Caller
  │
  └─▶ GeneratedImageWordPressMediaUploader.upload(image, filename)
          │
          ├─▶ isinstance(image, GeneratedImage)  … OK
          │
          ├─▶ callable(getattr(self._media_uploader, "upload", None))  … OK
          │       （media_uploader.upload はcallableのため、capability検証は通過する）
          │
          └─▶ self._media_uploader.upload(
                  image_bytes=..., filename=..., mime_type=...)
                  │
                  └─▶ Python runtime が signature不一致を検出し TypeError を送出
                       （例：upload()がkeyword引数を受け付けないsignatureの場合。
                        messageはPython version・関数定義形態に依存し、
                        Wiring層はこれを生成・制御しない）
          └─◀ TypeError（Wiring層はcatch・変換・ラップ・抑制しない。
               capability検証失敗の固定message TypeErrorとは送出主体が異なる、
               20.3節参照）
  │
  └─◀ TypeError（無変換伝播）
```

## 30. Failure Flow（Architecture Review 1・3 Finding反映、確定形）

### 30.1 失敗系（Media Upload失敗）

```text
Caller
  │
  └─▶ GeneratedImageWordPressMediaUploader.upload(image, filename)
          │
          ├─▶ isinstance(image, GeneratedImage)  … OK
          │
          ├─▶ callable(getattr(self._media_uploader, "upload", None))  … OK
          │
          └─▶ WordPressMediaUploader.upload(image_bytes=..., filename=..., mime_type=...)
                  │
                  └─▶ WordPressMediaUploadError（filename不正／mime_type不正／
                       通信失敗／非2xxレスポンス／レスポンス不正等、v6.9.0 18章）
                  │
          └─◀ WordPressMediaUploadError（ラップせずそのまま再送出）
  │
  └─◀ WordPressMediaUploadError
```

### 30.2 失敗系（media_uploader capability不正）

29.3節に同じ。`callable(getattr(self._media_uploader, "upload", None))`検証がNGの時点で固定messageの`TypeError`を送出し、`WordPressMediaUploader.upload()`は呼び出されない。

### 30.3 失敗系（予期しないException／KeyboardInterrupt／SystemExit）

```text
Caller
  │
  └─▶ GeneratedImageWordPressMediaUploader.upload(image, filename)
          │
          ├─▶ isinstance(image, GeneratedImage)  … OK
          ├─▶ callable(getattr(self._media_uploader, "upload", None))  … OK
          │
          └─▶ WordPressMediaUploader.upload(...)（Fake／実装が想定外の例外、
               または KeyboardInterrupt／SystemExit を送出するケース）
                  │
                  └─▶ 任意のException／KeyboardInterrupt／SystemExit
          └─◀ 無変換でそのまま再送出（本層はcatch・変換・ラップ・抑制しない）
  │
  └─◀ 無変換でそのまま再送出
```

### 30.4 失敗系（media_uploader signature不正、Architecture Review 3 Finding AR3-m-1反映）

29.4節に同じ。`callable(getattr(self._media_uploader, "upload", None))`検証はOKだが、実際の`upload()`呼び出しがsignature不一致でPython標準の`TypeError`を送出するケース。分類上は30.3節（予期しないException）の特殊ケースであり、Wiring層の処理（catch・変換・ラップ・抑制しない）は30.3節と同一である。30.2節（capability検証失敗、Wiring層が固定messageで能動的に送出する`TypeError`）とは送出主体が異なる点のみが違いである（20.3節TypeError分類表を参照）。

本層は、image型検証（`ValueError`）とmedia_uploader capability検証（`TypeError`）という、本層が明示的に検証する2件のInput Contract以外は、下流から発生した例外（signature不一致による`TypeError`を含む）を無条件にPythonの通常の伝播に委ねる（catch・変換・ラップ・抑制しない、20章）。`KeyboardInterrupt` / `SystemExit`は`BaseException`のsubtypeであり、`Exception`をcatchする実装にはなっていないため、これらも同様に無変換で伝播する。Release 6.12の想定実装ではこれを下流例外捕捉用の`try`／`except`を設けずに実現できるが、これは実装上の帰結であり、Architecture Contract自体が`try`／`except`という構文の使用を禁止するものではない（20章）。

## 31. Test Strategy

新規E2Eテスト（`tests/test_e2e_v6_12_0_generated_image_wordpress_media_upload_wiring_foundation.py`、Test Reviewで正式なScenario／Case数を確定。43.7節参照）で以下を検証する。Production ImplementationおよびE2E実装はCode Review工程（43.8〜43.10節）で完了し、最終的に17 Scenario／8 forループcase／91 Assertion／10 Fake・Stubで91/91 PASSを実測した（Test Review時点の想定値：17 Scenario／約8 case／約78 Assertion／10 Fake・Stub。91件への増加理由はCode Review Finding CR-m-1反映によるupload() State非保持Guard追加、31.8節参照）。

**実行方式（Test Review確定事項、TR-S-1）**：本プロジェクトの既存E2E（v6.9.0／v6.10.0／v6.11.0）はpytestを使用せず、Pythonスクリプトとして直接実行し、自前の`check()`／`check_true()`／`check_contains()`等のhelperで結果を集計する方式を一貫して採用している。新規E2Eもこの既存方式に合わせ、`pytest`・`pytest.raises`・`pytest fixture`・`pytest parametrize`・`monkeypatch`は導入しない。`for`ループによるCase展開・`unittest.mock.patch`／`unittest.mock.patch.dict`による一時差し替え・AST（`ast.Import`／`ast.ImportFrom`／`ast.Call`）によるDependency Guard／Side Effect Guard／Logging Guardを、既存precedent（v6.10.0／v6.11.0の`get_import_details()`／`get_call_lines()`相当）に合わせて採用する。実行コマンドは`python projects/03_game_content_ai/tests/test_e2e_v6_12_0_generated_image_wordpress_media_upload_wiring_foundation.py`とする。

### 31.1 正常系

```text
callableなupload methodを持つFake／Stub（WordPressMediaUploaderをsubclass化しない
    単純なPythonクラス、またはunittest.mock.Mock等）を注入して正常に実行できる
GeneratedImage.image_bytesの値（==）が変更されずにupload()へ渡る
    （object identityは検証しない。18章 Image Bytes Contract参照）
GeneratedImage.mime_typeが正確に渡る
filenameが正確に渡る
呼び出しがkeyword引数（image_bytes= / filename= / mime_type=）で行われ、
    既存WordPressMediaUploader.upload()のContract（v6.9.0）と一致すること
WordPressMediaUploader.upload()（Fake）が1回だけ呼ばれる
MediaUploadResultが呼び出し元へそのまま返る
    （Test Review確定事項、TR-S-2：value equality（frozen dataclassの==比較、
     media_id／source_url／mime_typeの各フィールド一致）で検証し、object identity
     （is比較）は要求しない。19章はMediaUploadResultのobject identityをPublic
     Contract化していないため、18章のimage bytesと同様の考え方を適用する）
余分な処理（追加のHTTP呼び出し・追加のFake呼び出し等）が行われないこと
```

### 31.2 失敗系

```text
検証順序（28章と同一Contract）：
    image が GeneratedImage 型でない場合 → ValueError
        （media_uploaderのcallable検証・WordPressMediaUploader.upload()いずれも
         呼び出されないことをFakeの呼び出し回数0で確認）
    image と media_uploader の両方が不正な場合 → ValueError
        （image検証がmedia_uploader検証より先に行われるため、
         capability検証・下流呼び出しのいずれにも到達しないことを確認する）
    image が正当で media_uploader が不正な場合 → TypeError
        （WordPressMediaUploader.upload()相当の処理が呼ばれないことを確認する）

media_uploader capability不正（31.4節Duck Typing Guardと同一Scenario群、詳細は31.4節）：
    upload属性を持たない場合 → TypeError（固定message完全一致）
    upload = None の場合 → TypeError（固定message完全一致）
    upload = 非callableなstr等の場合 → TypeError（固定message完全一致）
    いずれの場合も、例外messageにdependencyのrepr／str表現・class名が
        含まれないことを確認する

media_uploader signature不正（Architecture Review 3 Finding AR3-m-1反映、
    31.4節Duck Typing Guardと同一Scenario群、詳細は31.4節）：
    callableだがimage_bytes／filename／mime_typeのkeyword引数を受け付けない
        Fakeを注入した場合 → capability検証（callable()）は通過し、実際の
        upload()呼び出し時にPython標準のTypeErrorが送出されることを確認する
    このTypeErrorのmessageは、固定message
        "media_uploader must provide a callable upload method" と
        完全一致しないことを確認する
    Wiring層固有の新規例外型へ変換されていないこと、例外chaining操作が
        追加されていないことを確認する
    **（Architecture Review 4 Finding AR4-m-1反映）固定messageとの不一致は、
        本Scenario内で「Wiring層送出のcapability不正TypeErrorではない」ことを
        確認する目的の観測項目である。呼び出し元が任意の下流TypeErrorを
        signature不一致として分類できることを保証するPublic Contractでは
        ない（20.4節）**

media_uploaderのdependency内部TypeError（Architecture Review 4 Finding AR4-m-1
    反映、20.3節分類3.5）：signatureが適合していても、dependency内部処理が
    独自にTypeErrorを送出する場合がある（例：callableかつ正しいkeyword引数を
    受け付けるupload()実装が、内部でraise TypeError("internal failure")する
    ケース）。このケースは専用Scenarioを新設せず、直下の「予期しない例外
    （Fakeが任意のRuntimeErrorを送出するケース）」Scenarioに包含される
    （下流のFakeが送出する例外の型をTypeErrorに差し替えた場合と等価であり、
    Wiring層の処理（catchしない・変換しない・ラップしない・抑制しない）は
    同一である）。このTypeErrorも、signature不一致TypeErrorと呼び出し元から
    安定的に分類できる保証はない（20.4節）

WordPressMediaUploadError の伝播（Fakeがraiseし、呼び出し元にそのまま届くこと。
    メッセージ・reason相当の情報が改変されないこと。「同一例外である」の確認は、
    Fakeが送出したexception objectと呼び出し元がexceptで捕捉したexception objectが
    無変換伝播の結果として一致することを確認する目的に限定し、18章のimage bytes
    object identity非検証方針とは無関係であることを明記する）
filenameが不正な形式の場合 → 本層は検証せずWordPressMediaUploader.upload()（Fake）へ
    そのまま渡り、Fake側がValueErrorを送出する経路を確認する
    （本層自身が二重に検証していないことの確認）
予期しない例外（Fakeが任意のRuntimeErrorを送出するケース、および上記の
    dependency内部TypeErrorを送出するケースを含む）が変換されずそのまま
    伝播すること
KeyboardInterrupt を本層が握りつぶさないこと（BaseExceptionのsubtypeとして
    Exceptionのcatchに巻き込まれないことを確認する）
SystemExit を本層が握りつぶさないこと（同上）
```

どちらの検証を新規Wiring層で行い、どちらを既存Foundationへ委ねるかの分離：**filenameの内容検証・mime_typeの内容検証・image_bytesの内容検証は既存Foundation（`wordpress_media` / `GeneratedImage.__post_init__`）の責務として、本層のE2Eでは「委譲されていること」のみを確認し、検証ロジック自体の網羅的なテストは行わない**（v6.9.0／v6.10.0の既存E2Eが既に担保済み）。「検証しないこと」を確認するテストは、Fakeへ渡された引数値・Fakeの呼び出し回数という観測可能な振る舞いのみを検証し、本層の内部実装（正規表現の有無等）には依存しない。

### 31.3 Security

```text
image bytesが例外message・repr・ログ・テスト出力へ含まれないこと
    （21.1節：参照・転送はするが、例外messageへの埋め込みはしないことの確認）
filenameが本層自身の例外（ValueError／TypeError）messageへ含まれないこと
    （21.2節。WordPressMediaUploadError側のfilename関連Security Contractは
     wordpress_mediaの既存E2Eで担保済みのため本層では重複検証しない）
dependency object（media_uploader）のrepr／str表現・class名が、Wiring層が
    能動送出するcapability不正TypeError（固定message）へ含まれないこと
    （20.2節・21.5節。31.4節のTypeError固定message完全一致Testと組み合わせて
     確認する）
下流由来のTypeError（signature不一致・dependency内部TypeError）のmessage内容
    自体（class名・method名・引数名等を含みうる）は、Wiring層のSecurity Contract
    対象外とする（Test Review確定事項）。本層が確認するのは「Wiring層自身が
    これらのmessageへ追加の情報を付加していないこと」「固定capability messageへ
    書き換えていないこと」のみであり、Python runtimeまたは注入されたdependency
    自身が生成するmessage内容の安全性は保証しない（21.5節と同一の区別）
mime_typeのみを安全な参照情報として扱えること（画像内容の推測に使えないことを前提とする）
WordPress credential・Authorization headerが本層のいかなる経路にも現れないこと
    （本層はConstructor経由でWordPressMediaUploaderインスタンスのみを受け取り、
     内部のsite_url／username／app_passwordへ一切アクセスしないことをコード上で確認）
本層が受け取ったimage／filenameをインスタンス状態へ保存しないこと
    （Constructorが保持するのはmedia_uploaderへの参照のみであることの確認）
例外objectの非保持・Exception Chainingの方針（ValueError／TypeErrorはfrom節を
    使わず新規送出、WordPressMediaUploadErrorはそのまま再raiseするため
    chainingの論点自体が発生しない）
```

### 31.4 Duck Typing Guard（Architecture Review 1・2・3 Finding反映、最終形）

```text
upload属性を持たないdependency（例：空object、他の無関係なclassのinstance）を
    Constructorへ注入し、upload()呼び出し時に固定messageのTypeErrorが
    送出されること（完全一致："media_uploader must provide a callable
    upload method"）
upload属性がNone（例：class InvalidUploader: upload = None）のdependencyを
    注入し、upload()呼び出し時に同一の固定messageでTypeErrorが送出されること
upload属性が非callableなstr等（例：class InvalidUploader: upload = "not callable"）の
    dependencyを注入し、upload()呼び出し時に同一の固定messageでTypeErrorが
    送出されること（上記3ケースいずれも同一の固定message・同一の例外型に
    合流することを確認する）
callableなupload methodを持つFake／Stub（WordPressMediaUploaderをsubclass化しない、
    単純なPythonクラスまたはunittest.mock.Mock等）を注入した場合、
    正常に実行できること
WordPressMediaUploaderのsubclass化が不要であること（Fakeが独立したclassでよいこと）
Protocol実装（typing.Protocolの明示的な継承・構造適合の宣言）が不要であること
dependency objectのrepr／str表現・class名が、TypeErrorのmessageへ含まれないこと
検証タイミングがConstructor時点ではなく、upload()実行時（遅延）であることの確認
    （Constructorへ不正なdependencyを注入した直後にはTypeErrorが発生せず、
     upload()呼び出し時に初めて発生することを確認する）
```

**signature不一致Scenario（Architecture Review 3 Finding AR3-m-1反映）**：

```text
前提：
    class SignatureMismatchUploader:
        def upload(self) -> None:
            pass
    （image_bytes／filename／mime_typeのkeyword引数を受け付けないsignature。
     別の単純なFakeでも構わない）
    upload属性：存在する
    callable：True
    必要なkeyword引数（image_bytes／filename／mime_type）：受け付けない

期待する振る舞い：
    capability検証（callable(getattr(media_uploader, "upload", None))）は通過する
    （callableであることのみが判定基準であり、signatureの適合性は判定しない）
    実際のkeyword引数付きupload()呼び出し（image_bytes=..., filename=...,
        mime_type=...）でPython標準のTypeErrorが発生する
    Wiring層はこれをcatchしない・変換しない・ラップしない・抑制しない
    Python標準のTypeErrorが無変換で伝播する

message検証方針（Wiring層送出のcapability検証TypeErrorではないことの確認）：
    Python標準messageの完全一致：検証しない
        （理由：Python versionや関数定義形態へ依存し得るため、
         Architecture Design段階では固定Contract化しない）
    検証対象とするもの：
        例外型がTypeErrorであること
        固定message"media_uploader must provide a callable upload method"と
            一致していないこと（＝Wiring層固有の固定messageへ書き換えられて
            いないことの確認）
        Wiring層の新規例外型（本層は新規例外型を持たないため該当しないが、
            将来にわたって変換されていないことを確認する趣旨）へ変換されて
            いないこと
        例外chaining操作（本層による新規raiseやfrom節での連結）が
            追加されていないこと
    **（Architecture Review 4 Finding AR4-m-1反映）注意：固定messageとの
        不一致を確認することは、本Scenarioが「capability不正TypeErrorでは
        ない」ことを検証する手段であり、「本Scenarioで発生した例外が
        signature不一致であること」を積極的に証明する手段ではない。
        本層のPublic Contractは、固定messageと完全一致するTypeErrorを
        capability不正として識別できることのみを保証し、それ以外の
        TypeError同士（signature不一致・dependency内部TypeError・その他の
        下流TypeError）を相互に分類できることは保証しない（20.4節）**

無変換伝播の確認方法：
    Pythonがargument binding時に生成する例外objectを呼び出し前にFake側で
        事前構築・保持することは、実装形態によっては困難な場合がある。
        その場合は上記「検証対象とするもの」の4項目（例外型・固定message
        との不一致・新規例外型への非変換・chaining非追加）を観測可能な
        振る舞いとして検証すれば足り、Fake内部の例外objectそのものへの
        identity一致等、実装詳細に過度に依存する検証は要求しない
```

### 31.5 Dependency Guard

AST解析（`ast.Import` / `ast.ImportFrom`）による禁止import検知を、v6.9.0 Code Review指摘（DEP-1）の反省を踏襲して採用する。

```text
許可：ai_image_generation（GeneratedImageのみ）, wordpress_media
    （WordPressMediaUploader, MediaUploadResultのみ）, 標準ライブラリ
禁止：openai_image_generation, image_resolver, outputs, ai, pipeline,
    workflow_engine, scheduler, retry_*, scripts, requests
逆依存禁止：ai_image_generation / openai_image_generation / wordpress_media が
    generated_image_wordpress_media をimportしていないことも確認する
```

### 31.6 Side Effect Guard

```text
実HTTPなし（media_uploaderはFakeを注入し、requests.post自体を呼び出さない）
実WordPress投稿なし
実OpenAI Client生成なし（本層はopenai_image_generationに依存しないため、そもそも接点がない）
実API key読込なし
実WordPress credential読込なし
実課金なし
print() / logging呼び出しなし
subprocess呼び出しなし
ファイルI/Oなし
```

**確認方式（Test Review確定事項、TR-S-3）**：本層はConstructor Injectionのみでfrom_env()や実Client生成経路を持たない（14.4節・25章）ため、v6.11.0のような実Client構築を強制遮断するRuntime Guard（`unittest.mock.patch`による`side_effect`遮断等）は必須としない。AST（`ast.Import`／`ast.ImportFrom`によるDependency Guard、`ast.Call`によるprint／subprocess／open呼び出し検出）と、Fakeによる`media_uploader`のConstructor Injectionのみで、上記の副作用非存在を構造的に検証できると判断する。

### 31.7 Zero Diff Policy

原則として次を無改修対象にする：

```text
src/ai_image_generation/
src/openai_image_generation/
src/wordpress_media/
src/image_resolver.py
src/outputs/
既存Pipeline
既存Workflow
既存Scheduler
既存Retry Runtime
既存scripts
既存テストファイル一式
```

新規E2E内での`git diff --quiet`によるZero Diff Guardは必須Contractとしない（Test Review確定事項）。v6.9.0〜v6.11.0の正式E2Eもこの手法を必須としておらず、正式Regression実行とDependency Guardにより既存Contractの維持を確認できるため、`git diff --quiet` Guard（Wiring Foundation precedent、v5.9.0）の採用は任意のSuggestion（ZERO-DIFF-1）とする。

### 31.8 State非保持Test（Code Review Finding CR-m-1反映）

11.1節が定めるstateless delegation Contract（Constructorが保持するのはmedia_uploaderへの参照のみであり、`image`／`filename`／`MediaUploadResult`／例外objectのいずれもインスタンス状態へ保存しない）を、新規E2Eは次の3方式で検証する。

```text
Runtime Guard（STATE-1）：
    同一GeneratedImageWordPressMediaUploaderインスタンス・同一media_uploaderに対し、
    1回目の呼び出しで例外を発生させた直後に2回目を正当な引数で呼び出し、
    1回目のrequest状態が2回目の呼び出し結果・下流呼出内容へ影響しないことを確認する

Constructor AST Guard（STATE-AST-1前段）：
    __init__のASTボディが単一のAssign文（self._media_uploader = media_uploader）
    のみであることを確認する（14.1節「代入のみを行う」Contractの検証）

upload() AST Guard（STATE-AST-1後段、Code Review Finding CR-m-1反映）：
    upload()メソッドのAST本体に、self.<attribute>へのast.Assign／ast.AnnAssign／
    ast.AugAssign、およびsetattr(self, ...)呼出（tuple／list target内のself属性を含む）
    が存在しないことを確認する。ローカル変数への代入（例：
    upload_method = getattr(...)）は対象外とし、誤検出しないことも合わせて確認する
```

初回Code Review（43.8節）では、STATE-AST-1が`__init__`のみを検査対象としており、`upload()`本体のstate非保持を直接検証していないことがMinor Finding（CR-m-1）として指摘された。Production Code自体は適合していたが、E2E側の検証範囲が21.1節の記述範囲より狭かったため、upload() AST Guardを追加した（43.9節）。この追加はTest Designの明確化であり、Frozen Architecture（11.1節・21.1節）自体の変更ではない。

## 32. Dependency Guard

31.5節に同じ。Dependency Guardは新規E2E内でAST解析により機械的に検証する方針とし、production codeのdocstring等の自然文中の単語誤検知（v6.9.0 Code Review指摘の再発防止）に注意する。

## 33. Side Effect Guard

31.6節に同じ。

## 34. Zero Diff Policy

31.7節に同じ。既存ファイルの改修が必要と判断される場合は、理由・影響範囲・代替案を実装Release時のDesign差分として別途報告する。本Architecture Design時点では、既存3 Foundationを含むいずれの既存ファイルへの変更も不要と判断している。

## 35. Regression Strategy

```text
既存Regression対象（Test Review確定、43.7節参照）：
  v6.11.0 CHANGELOG.md Testedセクション記載の既存14ファイル
  （v1.11.0、v5.9.0〜v6.11.0）、基準件数1840件
確認事項：ベースライン件数不変・FAILなし・終了コード0・警告なし・Tracebackなし・
  既存Regressionファイル無改修
既存3 Foundation（v6.9.0／v6.10.0／v6.11.0）の既存E2Eとの重複を避け、
  「委譲されていること」のみを新規E2Eで検証する（31.2節）
新規Release完了時の想定：既存1840件＋新規v6.12.0 E2E

Test Review工程における実行履歴（正式Regressionとの区別）：
  Test Review工程では、既存v6.9.0／v6.10.0／v6.11.0のE2Eをbaseline／precedent確認
  として実行し、CHANGELOG.md記載件数との一致を確認した
  （v6.9.0：331/331、v6.10.0：78/78、v6.11.0：248/248）。この実行はTest Design判断の
  根拠資料を得るためのものであり、Release 6.12の正式Regression実行を意味しない。
  正式Regressionは、Production Implementationおよび新規E2E作成後に14ファイル＋
  新規E2Eを対象として改めて全実行する（43.7節）

Code Review完了時点の状態（43.8〜43.10節参照）：
  新規v6.12.0 E2E：91/91 PASS（Code Review Re-Review時点の実測、終了コード0）
  正式Regression（既存14ファイル＋新規v6.12.0 E2E）：未実施
  Code Review中に複数回実行された新規E2Eの確認実行（Approved反映時点で91/91 PASS）は、
  いずれもRelease 6.12の正式Regression完了を意味しない

正式Regression結果（Formal Regression、43.11節参照）：
  判定：PASS
  実行ファイル数：15（既存14ファイル＋新規v6.12.0 E2E 1ファイル）
  既存14ファイル合計：1840/1840 PASS（v6.11.0 CHANGELOG.md Testedセクション基準どおり）
  新規v6.12.0 E2E：91/91 PASS
  総合計：1931/1931 PASS
  終了コード0：15ファイルすべて
  FAIL：0件
  実行時Warning：0件（"WARNING"／"Traceback"／"ConnectionError"等の文字列出現は
    いずれも各E2EのScenario名・Assertionラベル・Fakeシミュレーション結果であり、
    実行時Warningや異常ではないことを個別確認済み）
  実HTTP／実WordPress投稿／実OpenAI Client生成／実WordPress Client生成／
    実API key読込／実WordPress credential読込／実課金：いずれもなし
  Git状態：tracked Zero Diff維持（未追跡4ファイルのみ、`__pycache__`は`.gitignore`
    対象でありRelease差分に含まない）
  Blocking Issue：なし
  実行方式：pytest不使用。各E2Eを`python tests/<ファイル名>.py`で個別に直接実行
```

## 36. Documentation Impact

本Architecture Design工程では、本文書（新規設計書1ファイル）のみを作成する。以下は実装完了後のDocumentation Update工程で更新する（本工程では変更しない）：

```text
projects/03_game_content_ai/docs/architecture.md（新規層の追記）
projects/03_game_content_ai/docs/ROADMAP.md（v6.12.0エントリの追加、
  731-733行目「次候補・未着手」チェックボックスの[x]化）
projects/03_game_content_ai/docs/CHANGELOG.md（Added／Changed／Tested記載）
```

## 37. Known Issues

```text
Architecture Design段階での新規Known Issueなし
```

既存Known Issue（KI-1、v1.10.0 Analyticsテストの日付ハードコード）は本Releaseと無関係であり、再報告しない。

### 37.1 In Scope（参考、35章と併読）

```text
src/generated_image_wordpress_media/__init__.py
src/generated_image_wordpress_media/generated_image_wordpress_media_uploader.py
GeneratedImageWordPressMediaUploader
新規E2E Test
正式Architecture Design文書（本文書）
```

### 37.2 Out of Scope

```text
画像生成（prompt → GeneratedImage）
Prompt Contract
AIImageGenerator.generate()の呼び出し
openai_image_generationへの依存
filenameの内容検証（regex等）の重複実装
MIME typeと拡張子の整合性チェック
画像bytesの圧縮・リサイズ・変換
新規Result型・新規Exception型
Logging
Retry
Dry Run
CLI／scripts Entry Point
Environment Composition
実OpenAI Client生成
実WordPress Client生成
image_resolver.py変更
ArticleData変更
WordPressOutput変更
既存記事生成Pipeline統合
Workflow統合
Scheduler統合
Retry Runtime統合
独自Protocol新設（Media Uploader抽象化）
複数CMS対応
```

## 38. Risks

| Risk | Mitigation |
|---|---|
| `image`引数の型検証を`isinstance()`のみに頼ると、`GeneratedImage`のサブクラス化や偽装objectをすり抜けさせる可能性がある | v1では`isinstance()`による構造的検証で十分とし、より厳格な検証（値の再検証等）は責務の重複（AD-7）を避けるため見送る |
| 将来Article→featured_media Wiring（候補D）が、本層とは異なる形でfilenameを決定するロジックを必要とし、責務の境界が再検討になる可能性 | 27.1節でDependencyのみを明記し、候補D自体の設計判断は独立したArchitecture Reviewに委ねる |
| `WordPressMediaUploadError`をラップしない方針が、将来呼び出し元（Pipeline層）にとって例外の出どころ（`wordpress_media`由来）を意識させる密結合になる可能性 | 20.1節の通り、Security Contract再実装コストとのトレードオフを優先。将来問題が顕在化した場合はArchitecture Reviewで再検討する |
| パッケージ名`generated_image_wordpress_media`がやや長く、将来Import文の可読性に影響する可能性 | 13.1節の比較の通り、責務・依存先の明確さを優先。既存最長パッケージ名（`retry_runtime_orchestrator`等）と同程度の長さに収まっている |

## 39. Trade-offs

```text
filenameを本層で検証しない設計は、責務重複を避ける利点がある一方、
  「本層のupload()を直接呼んだ場合にfilenameが不正だとどこで失敗するか」を
  呼び出し元がwordpress_media側のContractまで把握しておく必要がある、という
  学習コストのトレードオフを持つ（Public API Docstringで明示することで緩和する）

WordPressMediaUploadErrorをラップしない設計は、単純さを優先する一方、
  将来複数Providerの複数Failure Sourceを扱うようになった際に、
  呼び出し元が例外の出どころを個別に把握する必要が生じるというトレードオフを持つ
```

## 40. Future Extensions

```text
Article → featured_media Wiring（Release 6.13候補、27.1節）
Retry Runtimeとの統合・再試行可否分類（Media Upload失敗時のRetry方針）
複数CMS対応時のMedia Uploader抽象化（Protocol新設の再検討）
CLI／Script Entry Point（実Provider・実WordPress Clientを組み立てるComposition Root）
filenameの自動生成ポリシー（呼び出し元の負担軽減が必要になった場合）
Logging統合（Pipeline層のLogging方針が確定した時点での再検討）
```

## 41. Acceptance Criteria（Architecture Review 1・2・3・4・5 Finding反映、Frozen）

```text
[x] モデルAが維持されている（9章。Architecture Review 2・3・4・5でもScope拡大なし）
[x] package名 generated_image_wordpress_media が確定している（13.1節、AD-2。
    Open Questionsからは削除済み）
[x] Public APIが確定している（14章：GeneratedImageWordPressMediaUploader.__init__ / upload）
[x] image型不正時ValueErrorが確定している（20章、AD-7）
[x] image検証がmedia_uploader検証より先である（28章、検証順序Contract）
[x] media_uploaderは遅延Duck Typing検証される（14.3節、AD-19）
[x] callableなupload methodが必須である（14.3節、AD-19。属性の存在だけでは不十分）
[x] upload属性なし時TypeErrorが確定している（20章、AD-19）
[x] upload属性非callable時TypeErrorが確定している（20章、AD-19、AR2-m-1反映）
[x] media_uploader TypeErrorの固定messageが確定している
    （20.2節："media_uploader must provide a callable upload method"、完全一致Test対象）
[x] filename検証をwordpress_mediaへ委譲することが確定している（16章）
[x] image bytesは値を変更せず転送することが確定している（18章）
[x] image bytes object identityがPublic Contractではないことが確定している（18章、AR1-m-3反映）
[x] WordPressMediaUploadErrorを無変換伝播することが確定している（20章）
[x] その他のExceptionをcatch・変換・ラップ・抑制しないことが確定している（20章）
[x] KeyboardInterruptとSystemExitをcatchしないことが確定している（20章、30.3節）
[x] try／except構文そのものをArchitecture Contractとして禁止していない
    （20章、AR2-m-2反映。主Contractは「catch・変換・ラップ・抑制しない」という
     振る舞いレベルの制約であり、実装syntaxを固定しない）
[x] imageとmedia_uploaderの非対称な検証理由が明文化されている（15.1節、AR2-m-4反映）
[x] Security ContractがRuntime Flow・Sequence Diagram・Failure Flowと一致している
    （21章、AR1-m-1反映）
[x] LoggingがOut of Scopeである（22章）
[x] RetryがOut of Scopeである（23章）
[x] Dry RunがOut of Scopeである（24章）
[x] CLIがOut of Scopeである（26章）
[x] Article／featured_media WiringがOut of Scopeである（27章）
[x] callable検証はmethod signature適合性まで保証しない（14.3節、20章、AD-20、
    AR3-m-1反映）
[x] signature introspectionを行わない（AD-20、10章Rejected Alternatives）
[x] callableだがkeyword引数不適合の場合のError Contractが確定している
    （20章・20.3節、AD-20）
[x] signature不一致TypeErrorは通常Exceptionとして無変換伝播する（20章・
    30.3節・30.4節）
[x] capability検証TypeErrorとsignature不一致TypeErrorが区別されている
    （20.3節TypeError分類表）
[x] capability検証TypeErrorだけが固定message Contractを持つ（20.2節）
[x] signature不一致TypeErrorのPython標準messageは固定Contractではない
    （20.2節、完全一致Testの対象外と明記）
[x] Test Strategyにsignature不一致Scenarioがある（31.2節・31.4節）
[x] capability不正TypeErrorは固定messageで識別可能である（20.4節、
    Architecture Review 4 Finding AR4-m-1反映）
[x] 固定messageと不一致の場合、capability不正ではないことだけを判断できる
    （20.4節、AR4-m-1反映）
[x] 固定messageとの不一致はsignature不一致を積極的に意味しない（20.4節、
    AR4-m-1反映）
[x] signature不一致・dependency内部TypeError・その他下流TypeErrorの
    相互分類は保証しない（20.3節・20.4節、AR4-m-1反映）
[x] 下流TypeErrorのmessage解析をPublic Contractにしていない（20.4節、
    AR4-m-1反映）
[x] Test Strategyが分類保証の範囲と一致している（31.2節・31.4節、AR4-m-1反映）
[x] Architecture Review 1 Finding（AR1-m-1〜AR1-m-4・AR1-S-1・AR1-S-2）が
    すべて反映されている（43.1節）
[x] Architecture Review 2 Finding（AR2-m-1〜AR2-m-4）がすべて反映されている（43.2節）
[x] Architecture Review 3 Finding（AR3-m-1）が反映されている（43.3節）
[x] Architecture Review 4 Finding（AR4-m-1）が反映されている（43.4節）
[x] Architecture Review 5でApprovedを得ている（43.5節。Blocking Issueなし、
    Suggestion 1件：AR5-S-1、反映済み）
[x] Architecture DesignがFrozenである（1章、43.5節）
```

Architecture Review 5がApprovedと判定され、Architecture Review 1〜5の全項目が完了したため、本Acceptance Criteria（41章）はすべて完了している。Test ReviewもApprovedと判定され、41.1節のTest Review Acceptance Criteriaを新設した。Implementation・Code Review・Release Reviewに属する項目は、引き続き本Acceptance Criteriaの対象外であり、別途各工程で確認する。

### 41.1 Test Review Acceptance Criteria（Test Review Approved反映）

```text
[x] Test ReviewでApprovedを得ている（43.7節、Blocking Issueなし）
[x] 新規E2Eファイル名が確定している
    （tests/test_e2e_v6_12_0_generated_image_wordpress_media_upload_wiring_foundation.py）
[x] Scenario一覧が確定している（独立Scenario 17、forループcase約8、43.7節）
[x] Fake／Stub構成が確定している（10種類、43.7節）
[x] 例外検証方針が確定している（ValueError／capability TypeError／signature不一致
    TypeError／dependency内部TypeError／WordPressMediaUploadError／RuntimeError／
    KeyboardInterrupt／SystemExit、31.2節・31.4節）
[x] TypeError 3区分（capability不正／signature不一致／dependency内部）のTest Designが
    確定している（20.3節・20.4節・31.2節・31.4節、混同なし）
[x] Security Guardが確定している（31.3節、下流TypeError message内容自体は
    Security Contract対象外であることを明確化）
[x] Dependency Guardが確定している（AST方式、31.5節）
[x] Side Effect Guardが確定している（AST方式＋Fake dependency、Runtime Guard必須化なし、
    31.6節）
[x] Regression範囲が確定している（v1.11.0・v5.9.0〜v6.11.0の14ファイル、1840件、35章）
[x] 実行予定コマンドが確定している
    （python projects/03_game_content_ai/tests/test_e2e_v6_12_0_generated_image_wordpress_media_upload_wiring_foundation.py）
[x] Test Review Suggestion（TR-S-1・TR-S-2・TR-S-3）が反映されている（43.7節）

[x] Production Implementation（43.8節以降参照）
[x] 新規E2E作成（43.8節以降参照）
[x] 新規E2E実行（91/91 PASS、43.10節参照）
[x] 正式Regression（1931/1931 PASS、43.11節参照）
[x] Code Review（初回Changes Required→Finding CR-m-1修正→Re-ReviewでApproved、43.8〜43.10節）
[ ] Documentation Integration
[ ] Release Review
[ ] commit
[ ] push
```

### 41.2 Code Review Acceptance Criteria（Code Review Approved反映）

```text
[x] 初回Code Reviewが実施されている（43.8節、判定：Changes Required、Blocking Issueなし）
[x] Production CodeがFrozen Architectureへ適合していることが初回Code Reviewで確認されている
    （43.8節。Public API・検証順序・固定message・Error Contract・Security Contract・
    Dependency Direction・Zero Diff Policyのいずれも適合、Finding対象外）
[x] Finding CR-m-1（Minor、Non-Blocking）が正確に記録されている（43.8節）
[x] CR-m-1の修正対象が新規E2Eのみであり、Production Codeを変更していないことが
    明記されている（43.9節）
[x] upload() State非保持AST Guard（Assign／AnnAssign／AugAssign／setattr(self, ...)、
    tuple／list target対応）が追加されている（43.9節、31.8節）
[x] Code Review Re-ReviewでApprovedを得ている（43.10節、Blocking Issueなし、
    Critical／Major／Minor Findingなし）
[x] 継続Suggestion（CR-S-1・CR-S-2）および新規Suggestion（CRR-S-1）がいずれも
    Non-Blockingとして記録されている（43.8節・43.10節）
[x] 新規E2Eが91/91 PASS・終了コード0であることを確認している（43.9節・43.10節）
[x] tracked Zero Diffが維持されている（既存src／既存テストへの変更なし）
[x] Architecture Design（Public API・検証順序・Error Contract・State非保持Contract・
    Security Contract・Dependency Direction・Zero Diff Policy）がCode Review反映後も
    Frozenのまま維持されている

[x] 正式Regression（1931/1931 PASS、43.11節参照）
[ ] Documentation Integration
[ ] Release Review
[ ] commit
[ ] push
```

### 41.3 Formal Regression Acceptance Criteria（Formal Regression PASS反映）

```text
[x] 正式Regression対象がCHANGELOG.md v6.11.0 Testedセクションから特定されている
    （既存14ファイル、35章・43.11節）
[x] 既存14 E2Eをすべて個別実行している（pytest不使用、直接実行方式）
[x] 既存Regressionが1840/1840 PASSしている（v6.11.0 CHANGELOG.md基準どおり）
[x] 新規v6.12.0 E2Eが91/91 PASSしている
[x] 全15ファイルが終了コード0である
[x] 総合計1931/1931 PASSしている
[x] FAILが0件である
[x] 実行時Warningが0件である（"WARNING"等の文字列出現はテスト対象の期待挙動であり、
    実行時Warningと区別済み）
[x] 実HTTP通信がない
[x] 実WordPress投稿・実OpenAI Client生成・実WordPress Client生成がない
[x] 実credential読込（API key／WordPress credential）がない
[x] 実課金がない
[x] Regression前後でtracked Zero Diffを維持している（`__pycache__`はGitignore対象で
    Release差分に含まない）
[x] Blocking Issueがない

[x] Documentation Integration（43.12節参照）
[ ] Release Review
[ ] commit
[ ] push
```

### 41.4 Documentation Integration Acceptance Criteria（Documentation Integration Completed反映）

```text
[x] ROADMAP.mdへv6.12.0が反映されている（未着手[ ]→完了[x]、主要成果・Test結果を含む）
[x] ROADMAP.mdの既存後続候補（Article → featured_media Wiring）を不必要に変更していない
    （前提条件充足の注記のみ追加）
[x] architecture.mdへ新component（generated_image_wordpress_media /
    GeneratedImageWordPressMediaUploader）が反映されている
[x] architecture.mdへDependency Direction・Runtime Flow・Error Boundary・State非保持
    Contract・Out of Scopeが反映されている
[x] CHANGELOG.mdへv6.12.0 entry（2026-07-18）が追加されている
[x] CHANGELOG.mdへ正式Regression対象15ファイルと1931/1931 PASSが記録されている
    （次Release以降の正式Regression基準として利用可能）
[x] Version・Release名・package名・Public class名が3文書（ROADMAP.md／architecture.md／
    CHANGELOG.md）で一致している
[x] New E2E 91/91 PASS・Formal Regression 1931/1931 PASS・Code Review Approved・
    Blocking Issueなしが3文書で一致している
[x] 継続Suggestion（CR-S-1・CR-S-2）および新規Suggestion（CRR-S-1）が3文書いずれも
    Non-Blockingとして言及され、詳細は正式設計書参照としている（Known Issueへ格上げしていない）
[x] 過去Release entry・過去Tested件数を変更していない（v6.11.0以前の履歴を維持）
[x] ROADMAP.mdの[x]完了表現が、Production Implementation・New E2E・Code Review・Formal
    Regression・Documentation Integrationの完了を示すものであり、Release Review Approved・
    commit完了・push完了を意味しないことを確認している（43.12節）
[x] Architecture変更（Public API・検証順序・Error Contract・State非保持Contract・
    Security Contract・Dependency Direction）がない
[x] Documentation IntegrationにBlocking Issueがない

[x] Release Review（Approved、43.13節参照）
[ ] commit
[ ] push
```

### 41.5 Release Approval Checklist（Release Review Approved反映）

```text
[x] Architecture DesignがApproved／Frozenである
[x] Production Implementationが完了している
[x] Public APIがFrozen Architectureと一致している
[x] 検証順序（image → capability → delegate → return）がFrozen Architectureと一致している
[x] Error Contract（能動送出2種＋無変換伝播6種）がFrozen Architectureと一致している
[x] State非保持Contract（Constructor・upload()とも）が満たされている
[x] Dependency Directionが正しい（許可2件・禁止依存・逆依存禁止3件）
[x] Security／Side Effect Contractが満たされている
[x] 新規E2Eが91/91 PASSしている
[x] Code ReviewがApprovedである（初回Changes Required→CR-m-1修正→Re-Review Approved）
[x] CR-m-1がResolvedである
[x] Formal Regressionが1931/1931 PASSしている（既存14ファイル1840/1840＋新規91/91）
[x] Documentation IntegrationがCompletedである
[x] ROADMAP.mdが整合している（Version・Release名・package・Public class・Test結果）
[x] architecture.mdが整合している（Component・Dependency Direction・Runtime Flow・
    Error Boundary・State・Out of Scope）
[x] CHANGELOG.mdが整合している（v6.12.0 entry、Tested対象15ファイル）
[x] CHANGELOG Testedが次Release基準として利用可能である（重複・欠落なし、15ファイル・
    1931件で一意に特定可能）
[x] 過去Release履歴（過去Tested件数・過去Known Issues・過去ROADMAP entry・既存
    architecture.mdセクション）を破壊していない
[x] 想定7ファイル（正式設計書・Production Code 2件・新規E2E・ROADMAP.md・architecture.md・
    CHANGELOG.md）だけがRelease成果物である
[x] stagedがない
[x] Critical Findingがない
[x] Major Findingがない
[x] Minor Findingがない
[x] Blocking Issueがない
[x] Release ReviewがApprovedである

[ ] git add
[ ] commit
[ ] push
[ ] local HEADとorigin/mainの同期確認
[ ] Working Tree clean確認
```

## 42. Review Checklist

セルフレビュー結果（43章参照）。Architecture Review 5でApproved（Blocking Issueなし、Suggestion 1件：AR5-S-1、反映済み）と判定され、本文書はFrozenである。

```text
[x] Release名と責務が一致している
[x] モデルAとモデルBが混在していない
[x] 生成処理とUpload処理の責務境界が明確
[x] 依存方向に循環がない
[x] Provider具象依存が必要最小限（ゼロ）
[x] Public APIに未定義部分がない
[x] filenameの供給者が明確（呼び出し元）
[x] MIME typeと拡張子の責任者が明確（本層は関与しない）
[x] media_uploader不正時TypeErrorが明記されている（20章・14.3節）
[x] callableによる遅延検証が全章（AD-19・14.3節・20章・28章・29.3節・30.2節・31.4節）で一貫している
[x] upload属性なしとupload属性非callableが同一の固定TypeErrorに合流することが
    全章で一貫している（20.2節・29.3節・31.4節）
[x] 固定message"media_uploader must provide a callable upload method"が
    全章で一致している
[x] capability検証TypeError（固定message、Wiring層送出）とsignature不一致
    TypeError（Python標準message、下流送出）が20.3節TypeError分類表で
    明確に区別され、全章で一貫している（AD-20、AR3-m-1反映）
[x] capability不正TypeErrorは固定messageとの完全一致でのみ識別可能であり、
    それ以外のTypeError（signature不一致・dependency内部TypeError・その他の
    下流TypeError）を呼び出し元が相互に分類できるとは記載していない
    （20.1節・20.4節、AR4-m-1反映）
[x] 「固定messageと不一致ならsignature不一致である」という誤読を招く表現が
    残っていない（全文検索で確認済み、AR4-m-1反映）
[x] dependency内部TypeError（signatureが適合していても発生し得る下流
    TypeError）が20.3節分類表・Test Strategyに明記されている（AR4-m-1反映）
[x] 下流TypeErrorのmessageについて、「Wiring層が情報を追加しないこと」と
    「下流messageに情報が含まれないこと」が21.5節で区別されている（AR4-m-1反映）
[x] signature introspection（inspect.signature()等）を追加していない
    （AD-20、10章Rejected Alternatives）
[x] 検証順序（image検証 → media_uploader capability検証 → 下流呼び出し）が
    Runtime Flow・Sequence Diagram・Failure Flow・Test Strategy・Acceptance Criteriaで
    一貫している（28章）
[x] imageとmedia_uploaderの検証方針の非対称性が一箇所（15.1節）で対比説明されている
[x] try／except構文自体を禁止する表現が残っていない（20章、AR2-m-2反映）
[x] 下流例外をcatch・変換・ラップ・抑制しないContractが一貫している（20章・30章・31章、
    signature不一致TypeError・dependency内部TypeErrorも含む）
[x] Error Contractに矛盾がない
[x] Security ContractがRuntime Flow・Sequence Diagram・Failure Flowと一致している
[x] Security Contractに情報露出経路がない（固定messageにdependency情報を含めない、20.2節・21.5節）
[x] Out of Scopeが十分に具体的（37.2節）
[x] Article／featured_mediaを含めていない
[x] Retry／Dry Run／CLIを暗黙に含めていない
[x] 既存3 FoundationのContractを変更していない
[x] Acceptance Criteriaがテスト可能
[x] Open QuestionsとAcceptance Criteriaが矛盾しない（43.6節）
[x] 14.1節の相互参照が14.3節を正しく指している（AR2-m-3反映）
[x] 14.3節・20章の相互参照が28章 Runtime Flowのステップ3を正しく指している
    （AR5-S-1反映）
[x] StatusがApproved、Architecture DesignがFrozenである（1章）
[x] Architecture Review 1がChanges Requiredとして正確に記録されている（43.1節）
[x] Architecture Review 2がChanges Requiredとして正確に記録されている（43.2節）
[x] Architecture Review 3がChanges Requiredとして正確に記録されている（43.3節）
[x] Architecture Review 4がChanges Requiredとして正確に記録されている（43.4節）
[x] Architecture Review 5がApprovedとして正確に記録されている（43.5節）
[x] Architecture Review 6を実施済みと記載していない
```

## 43. Review History

### 43.1 Architecture Review 1

```text
Architecture Review 1

判定：
Changes Required

Finding：
AR1-m-1（Minor・Blocking）：Security Contractのimage bytesに関する表現が、
    実際のRuntime Flow（image_bytesを参照・転送する事実）と一致していなかった
AR1-m-2（Minor・Blocking）：media_uploaderの検証方針とError Contractが未確定であり、
    「v6.11.0は検証を行わない」というprecedent引用も不正確だった
    （実際のv6.11.0はhasattr+TypeErrorによる遅延検証を行っている）
AR1-m-3（Minor・Non-blocking）：bytes object identity（同一object参照・コピーなし）を
    不要にPublic Contract化していた
AR1-m-4（Minor・Blocking）：package名の確定状況について、Acceptance Criteria
    （確定済みと表記）とOpen Questions（採用可否を未確定として記載）が矛盾していた
AR1-S-1（Suggestion）：保持状態・同期実行・stateless delegationの説明追加を推奨
AR1-S-2（Suggestion）：try／exceptを設けず例外を無変換伝播する方針の明文化を推奨

概要：
Security Contract表現（21章）、media_uploader検証・Error Contract（14.3節・20章）、
image bytes object identity（18章）、package名確定状態（13.1節・41章）、
stateless delegation（11.1節）、例外無変換伝播方針（20章）について修正要求

反映状況：
AR1-m-1：Resolved（21章 Security Contractを全面改訂。image bytesは
    「参照・転送するが検査・保存・ログ出力・repr・例外messageへの埋め込みはしない」
    という表現へ修正し、Runtime Flow・Sequence Diagram・Failure Flowと同期した）
AR1-m-2：Resolved（AD-19を新設し、hasattr(media_uploader, "upload")による遅延
    Duck Typing検証＋TypeErrorを14.3節・20章・28章・29.3節・30.2節・31.4節へ反映。
    v6.11.0precedentの引用を実際のコード（_get_client()）に基づく正確な記述へ訂正した）
AR1-m-3：Resolved（18章を全面改訂。「値の等価性のみをContractとし、
    object identity・コピー有無は実装詳細とする」という表現へ変更し、
    Test Strategy（31.1節）も値の等価性（==）検証へ統一した）
AR1-m-4：Resolved（package名 generated_image_wordpress_media をAD-2・13.1節で
    正式確定し、Open QuestionsからはRemoved。41章 Acceptance Criteriaの表現も
    整合させた）
AR1-S-1：Resolved（11.1節「状態保持・実行モデル」を新設し、stateless delegation・
    同期API・thread safety方針を明記した）
AR1-S-2：Resolved（20章冒頭に「本層はtry／exceptを一切使用しない」という
    一般方針を明記し、KeyboardInterrupt／SystemExitがBaseExceptionのsubtypeとして
    Exceptionのcatchに巻き込まれない旨を明示した）

Architecture Review 2：
Changes Required（43.2節参照）

Test Review：
未実施

Code Review：
未実施

Release Review：
未実施
```

本文書はArchitecture Review 1（Changes Required）のFinding 6件すべてを反映した改訂版である。

### 43.2 Architecture Review 2

```text
Architecture Review 2

判定：
Changes Required

Finding：
AR2-m-1（Minor・Blocking）：upload属性が存在するがcallableでない場合
    （例：upload = None、upload = "not callable"）のFailure Contractが
    未定義だった。hasattr()のみでは属性の存在しか確認できず、実際に
    呼び出し不可能なdependencyを通過させてしまう可能性があった
AR2-m-2（Minor・Non-blocking）：「本層はtry／exceptを一切使用しない」という
    表現が、Architecture Contract（下流例外をcatch・変換・ラップ・抑制しない）
    ではなく実装syntax（try／except文そのものの不使用）を過度に固定していた
AR2-m-3（Minor・Blocking）：14.1節のCapability Contract参照先が誤って
    「14.4節」（なぜfrom_env()を持たないか）となっていた。正しくは
    「14.3節」（media_uploader Capability Contract）である
AR2-m-4（Minor・Non-blocking）：GeneratedImageに対するisinstance()による
    厳密型検証と、media_uploaderに対するDuck Typing検証という、異なる
    検証方針を採用する理由が、AD-7・AD-19・14.2節・18.1節に分散したまま
    一箇所で対比説明されていなかった

概要：
media_uploader upload methodのcallable性、例外伝播Contractとtry／except表現、
14.1節の章参照、imageとmedia_uploaderの検証方針の非対称性説明について修正要求

反映状況：
AR2-m-1：Resolved（AD-19を`hasattr()`のみから`callable(getattr(media_uploader,
    "upload", None))`へ強化。不適合時の固定message
    "media_uploader must provide a callable upload method"を14.3節・20.2節で
    正式確定し、完全一致でTest可能なContractとした。14.3節にv6.11.0との相違点
    （v6.11.0はhasattrのみ、Release 6.12はcallableまで含む）を明記し、
    「v6.11.0と完全に同一」という誤解を招く記述を排除した。31.4節へ
    upload属性なし／upload=None／upload=非callable文字列の3Scenarioを
    追加し、いずれも同一の固定messageに合流することを明記した）
AR2-m-2：Resolved（20章の主Contractを「下流から発生した例外をcatch・変換・
    ラップ・抑制しない」という振る舞いレベルの表現へ変更し、「try／except
    を一切使用しない」は実装上の参考説明として従属的に記載するにとどめた。
    将来のtry／finally（cleanup目的、exceptを伴わない）が本Contractに
    違反しないことを明記した。30.3節も同様に更新した）
AR2-m-3：Resolved（14.1節の「14.4節・AD-19」を「14.3節・AD-19」へ訂正し、
    全文の相互参照（14.1〜14.4節、AD-19、20章、28章、29章、30章、31章、
    41章、43章）を再確認した）
AR2-m-4：Resolved（15.1節「imageとmedia_uploaderで検証方針が異なる理由」を
    新設し、imageは値objectであり構築時検証（__post_init__）への信頼を
    担保するためisinstance()を用いること、media_uploaderは注入される
    collaboratorでありテスト容易性を優先するためDuck Typing（callable検証）を
    用いることを対比説明した）

Architecture Review 3：
Changes Required（43.3節参照）

Test Review：
未実施

Code Review：
未実施

Release Review：
未実施
```

本文書はArchitecture Review 1（Changes Required、6件）・Architecture Review 2（Changes Required、4件）のFindingをすべて反映した改訂版である。

### 43.3 Architecture Review 3

```text
Architecture Review 3

判定：
Changes Required

Finding：
AR3-m-1（Minor・Blocking）：media_uploader.uploadがcallableであっても、
    image_bytes／filename／mime_typeのkeyword引数を受け付けないsignatureで
    ある場合（callableだがsignature不正）のError ContractとTest Strategyが
    未定義だった。callable()検証は「呼び出し可能であること」のみを保証し、
    「必要なkeyword引数を受け付けるsignatureであること」までは保証しないため、
    実際の呼び出し時にPython標準のTypeErrorが発生し得るが、この失敗モードが
    設計書のどこにも定義されていなかった

概要：
callableなmedia_uploader.uploadが必要なkeyword引数を受け付けないsignatureの
場合のError ContractとTest Strategyについて修正要求

反映状況：
AR3-m-1：Resolved（AD-20を新設し、callable()検証がsignature適合性まで
    保証しないことを14.3節・14.4節前段で明記。20章 Error Contractへ
    「signature不一致」ケースを追加し、Python runtime／下流呼び出し境界が
    送出する制御外のTypeErrorとして、Wiring層固有の固定message TypeError
    （capability検証失敗）とは明確に区別した。20.3節「TypeError分類」表を
    新設し、6分類（image型不正／capability不正／signature不正／
    WordPress Media Upload失敗／その他のException／KeyboardInterrupt・
    SystemExit）を一覧化した。signature introspection（inspect.signature()等）
    は追加せず、10章 Rejected Alternativesへその理由を明記した。28章
    Runtime Flow・29.4節（新設）Sequence Diagram・30.4節（新設）Failure Flowへ
    signature不一致の経路を追加し、31.2節・31.4節（新設サブセクション）
    Test Strategyへ、callableだがsignature不正なFakeを用いるScenarioと、
    Python標準messageの完全一致を要求しないmessage検証方針を追加した）

Architecture Review 4：
Changes Required（43.4節参照）

Test Review：
未実施

Code Review：
未実施

Release Review：
未実施
```

本文書はArchitecture Review 1（Changes Required、6件）・Architecture Review 2（Changes Required、4件）・Architecture Review 3（Changes Required、1件）のFindingをすべて反映した改訂版である。

### 43.4 Architecture Review 4

```text
Architecture Review 4

判定：
Changes Required

Finding：
AR4-m-1（Minor・Blocking）：20.1節「新規Exception型を導入しない理由」の
    記述が、呼び出し元がWiring層送出のcapability不正TypeErrorとPython
    runtime／下流送出のsignature不一致TypeErrorを、except節やstr(exc)の
    比較だけで十分に分類できると読める過剰な保証を含んでいた。固定message
    と一致すればcapability不正であると識別できるが、一致しない場合に
    判断できるのは「capability不正ではない」ことのみであり、
    signature不一致であることを積極的に証明するものではない

概要：
capability不正TypeErrorとsignature不一致／下流TypeErrorについて、呼び出し元が
message比較だけで十分に分類できると読める過剰な保証を修正要求

反映状況：
AR4-m-1：Resolved（20.1節の該当段落を、Wiring層が能動的に送出する例外
    （ValueError・capability不正TypeError）への分類保証と、それ以外の
    下流由来の例外への非保証を明確に切り分ける表現へ書き換えた。20.3節
    TypeError分類表を「Wiring層が能動送出するTypeError」と「下流から
    伝播するTypeError」の2区分へ再構成し、新たに分類3.5「dependency内部
    TypeError」（signatureが適合していてもdependency内部処理がTypeErrorを
    送出するケース）を明記した。20.4節「呼び出し元への分類保証範囲」を
    新設し、固定message完全一致時のみcapability不正として識別可能である
    こと、固定messageとの不一致はcapability不正ではないことのみを意味し
    signature不一致を積極的に意味しないこと、下流TypeError同士の相互分類は
    Public Contractではないことを明示した。21.5節を「signature不一致
    TypeError」限定の記述から「下流TypeError全般（signature不一致・
    dependency内部TypeError・その他の下流Exception）」を対象とする記述へ
    拡張し、「Wiring層が情報を追加しないこと」と「下流messageに情報が
    含まれないこと」の混同を避けた。31.2節・31.4節のTest Strategyへ、
    固定messageとの不一致確認が「capability不正ではないことの確認」に
    限定される旨の注記と、dependency内部TypeErrorが既存の「予期しない
    例外」Scenarioに包含される旨の説明を追加した）

Architecture Review 5：
Approved（43.5節参照）

Test Review：
未実施

Code Review：
未実施

Release Review：
未実施
```

本文書はArchitecture Review 1（Changes Required、6件）・Architecture Review 2（Changes Required、4件）・Architecture Review 3（Changes Required、1件）・Architecture Review 4（Changes Required、1件）のFindingをすべて反映した改訂版である。

### 43.5 Architecture Review 5

```text
Architecture Review 5

判定：
Approved

Blocking Issue：
なし

Finding：
AR5-S-1（Suggestion・Non-blocking）：14.3節・20章にある、番号付きステップへの
    参照が「20章ステップ3」「下記ステップ3」という表現になっており、番号付き
    ステップの正式な定義元である28章 Runtime Flowを明示的に指していなかった

承認理由：
Architecture Review 1〜4で指摘された全12件のFinding（AR1-m-1〜AR1-m-4・
AR1-S-1・AR1-S-2・AR2-m-1〜AR2-m-4・AR3-m-1・AR4-m-1）が、設計書全文、
既存コード、既存テストとの照合によってResolvedと確認された。Architecture
Review 5で確認された新規指摘は、相互参照の可読性に関するSuggestion 1件のみ
であり、Architecture Contract・Security Contract・Error Contract・
Test Strategy・Dependency Direction・Zero Diff Policyには影響しない。
Suggestionのみであるため、Architecture Review 5はApprovedと判定された。

反映状況：
AR5-S-1：Resolved（14.3節「実際の呼び出し（20章ステップ3）」を「実際の呼び出し
    （28章 Runtime Flowのステップ3）」へ、20章「実際の呼び出し（下記ステップ3）」を
    「実際の呼び出し（28章 Runtime Flowのステップ3）」へ、それぞれ修正した。
    いずれもArchitecture Contractの変更ではなく、相互参照の可読性改善である）

Design Freeze：
Architecture Review 5のApproved判定に基づき、Architecture Designを正式に
Frozenとする。Public API（14章）・責務境界（11章）・Dependency Direction
（12章）・Error Contract（20章）・Security Contract（21章）・Runtime Flow
（28章）・Test Strategy（31章）・Zero Diff Policy（31.7節・34章）・
Out of Scope（37.2節）は、以後のTest Review・実装工程における確定基準として
扱う。Test Reviewまたは実装工程で新たな重大な矛盾が発見された場合を除き、
これらのArchitecture Contractを変更しない。

Test Review：
未実施

Code Review：
未実施

Release Review：
未実施
```

本文書はArchitecture Review 1（Changes Required、6件）・Architecture Review 2（Changes Required、4件）・Architecture Review 3（Changes Required、1件）・Architecture Review 4（Changes Required、1件）・Architecture Review 5（Approved、Suggestion 1件）のFindingをすべて反映した最終版であり、Statusは**Approved**、Architecture Designは**Frozen**である。過去のArchitecture Review 1〜4のChanges Required判定・Finding・反映記録は、本Freeze後も履歴としてそのまま維持する（43.1〜43.4節）。Architecture Review 5のApprovedは、過去のChanges Requiredを上書きするものではない。Test Review以降の工程は未実施である。

### 43.6 Open Questions

Architecture Review 1以前に存在した3件のOpen Question（package名の採用可否／media_uploaderのisinstance検証省略可否／WordPressMediaUploadError無変換伝播とPipeline層Error Handling方針との整合性）は、いずれもArchitecture Review 1のFinding反映で正式に確定した（package名：13.1節・AD-2、media_uploader検証：14.3節・AD-19、Error Contract：20章）ため、Open Questionsから削除した。

Architecture Review 2で新たに指摘された4件（hasattrかcallableか／非callable upload属性の扱い／TypeError message／検証順序／imageとmedia_uploaderの検証方針の違い／try／except表現／章参照先）も、本改訂ですべて確定した。callable検証・固定message・検証順序（28章）・非対称性説明（15.1節）・try／except表現（20章）・章参照（14.1節）のいずれも実装者の判断に委ねる余地を残していない。

Architecture Review 3で新たに指摘された1件（callableだがsignature不正なdependencyの扱い）も、本改訂で確定した。signature introspectionの要否・callableだがsignature不一致の場合の扱い・TypeErrorの分類（20.3節）・signature不一致時のmessage Contract・Test対象（31.2節・31.4節）のいずれも実装者の判断に委ねる余地を残していない。

Architecture Review 4で新たに指摘された1件（2種類のTypeError分類保証の範囲）も、本改訂で確定した。固定messageと不一致の場合の意味・signature不一致とdependency内部TypeErrorの区別・呼び出し元のmessage比較利用範囲のいずれも、実装者やTest作成者が判断する必要のある曖昧性を残していない。

Architecture Review 5で新たに指摘された1件（AR5-S-1、相互参照の可読性）も、本改訂で確定した。

本改訂時点で、実装開始を妨げるBlocking Open Questionは存在しない。Architecture Review 5がApprovedと判定されたことに伴い、Open Questionsは存在しない状態でArchitecture Designを確定する。将来Release検討時の参考事項のみ40章「Future Extensions」へ記録している（複数CMS対応時のMedia Uploader抽象化、Retry Runtime統合等）。これらはRelease 6.12の実装判断を待たせるものではなく、Acceptance Criteria（41章）とも矛盾しない。

Test Review（43.7節）でも新たなOpen Questionは生じていない。E2E実行方式・新規E2Eファイル名・Scenario構成・Fake／Stub構成・Assertion方針・MediaUploadResultの値等価性・TypeError 3区分・Security Guard・Dependency Guard・Side Effect Guard・Regression範囲・実行コマンドはいずれもTest Review工程で確定し、実装者が判断する必要のある曖昧性を残していない。

Code Review（43.8〜43.10節）でも新たなOpen Questionは生じていない。初回Code Reviewで確認されたFinding CR-m-1はTest Design（E2Eの検証範囲）に関する指摘であり、Architecture Contract自体への指摘ではなかった。CR-m-1修正後のRe-ReviewはApprovedと判定され、継続Suggestion（CR-S-1・CR-S-2）および新規Suggestion（CRR-S-1）はいずれもNon-Blockingとして記録されている。Architecture DesignはCode Review完了後もFrozenのまま維持されている。

正式Regression（43.11節）でも新たなOpen Questionは生じていない。既存14ファイル・新規v6.12.0 E2Eの計15ファイルすべてが基準どおりPASSし、総合1931/1931 PASS・Blocking Issueなしと判定された。CR-S-1・CR-S-2・CRR-S-1はいずれも正式Regression結果によって状態を変更せず、引き続きNon-BlockingのDeferred／Accepted Riskとして維持されている。

Documentation Integration（43.12節）でも新たなOpen Questionは生じていない。`docs/ROADMAP.md`・`docs/architecture.md`・`docs/CHANGELOG.md`への反映は3文書間で完全に整合し、過去Releaseの記録・Tested件数はいずれも変更していない。CR-S-1・CR-S-2・CRR-S-1は引き続きNon-Blockingとして3文書へ言及され、Known IssueやOpen Questionへは格上げされていない。

Release Review（43.13節）でも新たなOpen Questionは生じていない。Release成果物7ファイルすべてがFrozen Architectureおよび正式設計書と整合し、Critical／Major／Minor Findingは0件、Blocking Issueなしと判定された。CR-S-1・CR-S-2・CRR-S-1はいずれもRelease Review結果によって状態を変更せず、引き続きNon-BlockingのDeferred／Accepted Riskとして維持されている。

### 43.7 Test Review

```text
Test Review

判定：
Approved

Blocking Issue：
なし

Finding：
TR-S-1（Suggestion・Non-blocking）：既存E2E（v6.9.0／v6.10.0／v6.11.0）はpytestを
    使用せず、Pythonスクリプトとして直接実行しcheck()系helperで結果を集計する
    独自方式を一貫して採用している。新規E2Eの実行方式を明示的に確定する必要があった
TR-S-2（Suggestion・Non-blocking）：MediaUploadResultの戻り値検証について、
    object identityとvalue equalityのいずれで検証するかが19章に明記されていなかった
TR-S-3（Suggestion・Non-blocking）：v6.11.0のような実Client構築を強制遮断する
    Runtime Guardを本Releaseでも採用すべきか、Side Effect Guardの方式が未確定だった

概要：
新規E2Eの実行方式、MediaUploadResultの検証粒度、Side Effect Guardの方式について
Test Design上の確定が必要という指摘。Architecture Contract自体への指摘ではない

反映状況：
TR-S-1：Applied（新規E2Eはpytest・pytest.raises・pytest fixture・pytest parametrize・
    monkeypatchを導入せず、既存precedentどおりPythonスクリプトとして直接実行し、
    check()／check_true()／check_contains()等の自前helper、forループによるCase展開、
    unittest.mock.patch／patch.dictによる一時差し替え、AST（ast.Import／
    ast.ImportFrom／ast.Call）によるGuardを採用する方針を31章冒頭へ明記した）
TR-S-2：Applied（MediaUploadResultの戻り値検証はvalue equality（frozen dataclassの
    ==比較）のみとし、object identity検証は要求しない方針を31.1節へ明記した。
    19章はMediaUploadResultのobject identityをPublic Contract化していないという
    既存記載と整合させた）
TR-S-3：Applied（本層はConstructor Injectionのみでfrom_env()や実Client生成経路を
    持たないため、v6.11.0のような実Client構築を強制遮断するRuntime Guardは必須と
    せず、AST Dependency Guard／Side Effect GuardとFakeによるConstructor Injection
    のみで副作用非存在を検証する方針を31.6節へ明記した）

Security表現の補足修正：
下流由来のTypeError（signature不一致・dependency内部TypeError）のmessage内容
    自体（class名・method名・引数名等を含みうる）は、Wiring層のSecurity Contract
    対象外であることを31.3節へ明記した。Wiring層が確認するのは「Wiring層自身が
    これらのmessageへ追加の情報を付加していないこと」「固定capability messageへ
    書き換えていないこと」のみであり、Python runtimeまたは注入されたdependency
    自身が生成するmessage内容の安全性は保証しない（21.5節と同一の区別を31.3節へ
    統一した）

承認理由：
Frozen Architecture（Public API・検証順序・Error Contract・TypeError 3区分・
Security Contract・Dependency Direction・Zero Diff Policy）を、既存E2E precedent
（v6.9.0 WordPress Media Upload Foundation・v6.10.0 AI Image Generation Contract
Foundation・v6.11.0 OpenAI Image Generation Adapter Foundation、および既存Wiring
Foundation）と整合するTest Designへ落とし込めることを確認した。主要Scenario・
Fake／Stub構成・例外検証方針・Security Guard・Dependency Guard・Side Effect Guard・
Regression範囲が確定し、Blocking Findingは存在せずSuggestion 3件のみであったため、
Test ReviewはApprovedと判定された

確定した新規E2E Test Design：
新規E2Eファイル：
    tests/test_e2e_v6_12_0_generated_image_wordpress_media_upload_wiring_foundation.py
    （1ファイル）
実行方式：
    pytestを使用せず、既存precedentどおりPython scriptとして直接実行する
実行コマンド：
    python projects/03_game_content_ai/tests/test_e2e_v6_12_0_generated_image_wordpress_media_upload_wiring_foundation.py
独立Scenario数（想定値）：17
    Public import／Constructor／正常系委譲（引数・戻り値・呼出回数・Duck Typing統合）／
    image型不正／検証順序／capability不正3ケース／signature不一致／
    dependency内部TypeError・WordPressMediaUploadError・RuntimeErrorの伝播／
    KeyboardInterrupt伝播／SystemExit伝播／state非保持（Runtime）／
    state非保持（Constructor Source Guard）／Security固定message非露出／
    Loggingなし／Dependency Guard／逆依存Guard／Side Effect Guard
forループによるcase展開（想定値）：約8ケース
    （capability不正3ケース＋image型不正2ケース＋下流TypeError系3ケース）
想定Assertion数（想定値）：約78件（任意のZERO-DIFF-1採用時は約82件）
Fake／Stub数：10種類
    _RecordingMediaUploader／_MissingUploadUploader／_NoneUploadUploader／
    _StringUploadUploader／_SignatureMismatchUploader／_InternalTypeErrorUploader／
    _RaisingWordPressMediaUploadErrorUploader／_RaisingRuntimeErrorUploader／
    _RaisingKeyboardInterruptUploader／_RaisingSystemExitUploader
    （いずれも新規E2Eファイル内へ閉じ込め、production packageへは追加しない。
    WordPressMediaUploaderの継承は不要）

これらの数値はTest Review工程における想定値である。実装後の実測値と差が出た場合は
Contract網羅を優先し、Release文書へ実測値を記録する（テスト数を水増しのために
固定しない）

Regression範囲（確定）：
正式基準：v6.11.0 CHANGELOG.md Testedセクション記載の既存14ファイル
対象バージョン：v1.11.0、v5.9.0〜v6.11.0
基準件数：1840件
新規Release完了時の想定：既存1840件＋新規v6.12.0 E2E

Test Review中の実行履歴（記録上の整理）：
Test Review工程では、既存v6.9.0・v6.10.0・v6.11.0のE2Eファイルをbaseline／precedent
確認のために実行し、CHANGELOG.md記載のAssertion件数と一致することを確認した
（v6.9.0：331/331、v6.10.0：78/78、v6.11.0：248/248）。この実行はTest Design判断の
根拠資料を得るためのものであり、Release 6.12の正式Regression実行を意味しない。
新規v6.12.0 E2Eは本工程時点でも未作成・未実行であり、正式Regression（35章参照）は
Production Implementationおよび新規E2E作成後に14ファイル＋新規E2Eを対象として
改めて全実行する。本工程によるコード・設計書・Git状態への変更はない
（Test Review自体は読み取り専用で実施された）

Code Review：
未実施

Implementation：
未実施

Release Review：
未実施
```

本文書はTest ReviewのApproved判定を反映した改訂版である。Architecture Design（Public
API・責務境界・Dependency Direction・Error Contract・Security Contract・Runtime Flow・
Test Strategy・Zero Diff Policy・Out of Scope）はいずれもFrozenのまま維持されており、
本節の反映はTest Designの明確化・承認結果の記録に限定される。

### 43.8 Code Review 1

```text
Code Review 1

判定：
Changes Required

Blocking Issue：
なし

Production Code判定：
Frozen Architectureへ適合
    Public API：適合
    Constructor：適合（media_uploader参照保持のみ）
    検証順序：適合（image → capability → 下流呼出）
    capability TypeError固定message：適合（完全一致）
    attribute lookup：適合（upload_methodを単一取得し検証・呼出両方で再利用）
    keyword委譲：適合
    戻り値：適合（無変換返却）
    例外伝播：適合（try/except・raise...from 0件）
    Security Contract：適合
    Dependency Direction：適合
    Zero Diff Policy：適合

Finding：
CR-m-1（Minor・Non-Blocking）：新規E2EのSTATE-AST-1が
    GeneratedImageWordPressMediaUploader.__init__()のみをAST解析しており、
    upload()メソッド内でrequest単位state（image／filename／MediaUploadResult等）を
    self属性へ保存しないことを直接検証していなかった。21.1節は
    upload()呼び出し中に受け取った値をインスタンス属性へ保存しないことを
    明示的Contractとして定めているが、これを検証するE2E Scenarioが
    upload()側には存在しなかった。Production Code自体には違反がないことを
    直接確認済みであり、Production Codeの修正は不要と判定された

概要：
新規E2EのState非保持Guard（STATE-AST-1）の検証範囲が、Frozen Architecture 21.1節が
定めるContractの範囲（Constructor＋upload()の両方）よりも狭かったという指摘。
Architecture Contract自体への指摘ではなく、Test Design側の検証範囲不足

Suggestion（Non-Blocking、継続記録）：
CR-S-1：DEP-2逆依存Guardの対象package directoryが将来空になった場合の
    vacuous pass耐性（現状は対象3packageとも実在し.pyファイルを含むため実害なし）
CR-S-2：get_call_lines()がast.Name形式の呼出のみを対象とし、Path(...).open()等の
    attribute形式呼出を検出しない（既存precedent v6.10.0／v6.11.0と同一設計であり、
    本Releaseで新規に導入された弱点ではない。現在のProduction Codeには
    attribute形式のI/O呼出が存在せず実害なし）

CR-m-1修正：
43.9節参照

Code Review Re-Review：
Approved（43.10節参照）

Implementation：
Completed（Production Implementationは初回Code Review前に完了済み）

Release Review：
未実施
```

本文書はCode Review 1（Changes Required、Finding CR-m-1）の記録である。Production Code自体はFrozen Architectureへ適合しており、Findingは新規E2Eの検証範囲不足のみであった。

### 43.9 CR-m-1 Fix

```text
CR-m-1 Fix

対象：
新規E2Eのみ（tests/test_e2e_v6_12_0_generated_image_wordpress_media_upload_wiring_foundation.py）

変更していないもの：
Production Code（src/generated_image_wordpress_media/配下2ファイル）
正式設計書
既存文書
既存E2E（v6.9.0〜v6.11.0）

修正内容：
STATE-AST-1を拡張し、GeneratedImageWordPressMediaUploader.upload()に対する
AST Source Guardを追加した（31.8節）

追加helper：
_target_contains_self_attribute(target)
    ast.Attributeかつvalueがast.Name(id="self")を判定。
    ast.Tuple／ast.Listを再帰的に判定し、tuple／list target内のself属性も検出する
find_self_state_violations(method_node)
    method_nodeをast.walkし、ast.Assign／ast.AnnAssign／ast.AugAssignの代入先、
    およびsetattr(self, ...)呼出を検出し、違反行番号一覧を返す

検出対象：
self.attribute = value（ast.Assign）
self.attribute: Type = value（ast.AnnAssign）
self.attribute += value（ast.AugAssign）
setattr(self, "attribute", value)
self.a, local_value = values（tuple target内のself属性）
self.a = self.b = value（複数target）

誤検出しないことを確認した対象：
upload_method = getattr(...)（ローカル変数への代入）
result = upload_method(...)（同上）
self._media_uploader = media_uploader（Constructorの正当な代入、
    upload() Guardは__init__を走査しないため干渉しない）

Assertion推移：
初回実装：86 Assertion
CR-m-1修正：upload() State非保持AST Guard追加により+5 Assertion
最終：91 Assertion

新規E2E実行結果：
91/91 PASS、終了コード0

Production Code変更：
なし
```

本文書はCR-m-1（Minor、Non-Blocking）の修正記録である。修正はE2Eの検証範囲拡張のみであり、Production CodeおよびArchitecture Contractは変更していない。

### 43.10 Code Review Re-Review

```text
Code Review Re-Review

判定：
Approved

Blocking Issue：
なし

Critical Finding：
0

Major Finding：
0

Minor Finding：
0

CR-m-1：
Resolved（upload()のself属性代入非存在がAssign／AnnAssign／AugAssign／
    setattr(self, ...)・tuple／list targetを含めて検出可能であることを、
    静的コードReviewおよび独立した合成AST検証の両方で確認した）

継続Suggestion（Non-Blocking）：
CR-S-1（引き続きOpen／Deferred、Non-Blocking）
CR-S-2（引き続きOpen／Deferred、Non-Blocking）

新規Suggestion（Non-Blocking）：
CRR-S-1：STATE-AST-1の補助Assertion（upload()内にローカル変数Assignが
    少なくとも1件存在することの確認）が、upload()の現行実装形状へわずかに
    結合している。CR-m-1の核心判定（self属性違反リストが空であること）とは
    独立しており、Non-Blocking

承認理由：
Production Codeは初回Code Review時点から一切変更されておらず、引き続き
Frozen Architectureへ完全適合している。既存86 Assertionは維持され、
追加5 Assertionを含む91/91 PASS・終了コード0を実測確認した。
tracked Zero Diffも維持されている。Critical／Major／Minor Findingは0件で、
Suggestion（CR-S-1・CR-S-2・CRR-S-1）のみであったため、Code Review全体の
判定はApprovedとされた

最終E2E実測：
独立Scenario：17
forループcase：8
Assertion：91
Fake／Stub：10
PASS：91／FAIL：0／Warning：なし／終了コード：0

Formal Regression：
未実施

Documentation Integration：
未実施

Release Review：
未実施
```

本文書はCode Review Re-Review（Approved）の記録である。Code Review 1（43.8節）のFinding CR-m-1がResolvedとなり、Code Reviewの最終正式状態はApprovedである。Architecture Design（Public API・責務境界・Dependency Direction・Error Contract・State非保持Contract・Security Contract・Runtime Flow・Test Strategy・Zero Diff Policy・Out of Scope）はいずれもFrozenのまま維持されており、Code Review工程の反映はProduction Code・新規E2Eの実装結果記録と承認結果の記録に限定される。

### 43.11 Formal Regression

```text
Formal Regression

判定：
PASS

正式基準：
v6.11.0 CHANGELOG.md Testedセクション記載の既存14ファイル

既存対象（14ファイル、1840/1840 PASS）：
v1.11.0：tests/test_e2e_v1_11_0_save_result.py：43/43 PASS
v5.9.0：tests/test_e2e_v5_9_0_retry_runtime_loop_wiring_foundation.py：64/64 PASS
v6.0.0：tests/test_e2e_v6_0_0_retry_runtime_lock_foundation.py：43/43 PASS
v6.1.0：tests/test_e2e_v6_1_0_retry_runtime_graceful_shutdown_foundation.py：44/44 PASS
v6.2.0：tests/test_e2e_v6_2_0_structured_loop_logging_foundation.py：64/64 PASS
v6.3.0：tests/test_e2e_v6_3_0_retry_metrics_foundation.py：174/174 PASS
v6.4.0：tests/test_e2e_v6_4_0_retry_monitoring_foundation.py：171/171 PASS
v6.5.0：tests/test_e2e_v6_5_0_retry_alert_foundation.py：131/131 PASS
v6.6.0：tests/test_e2e_v6_6_0_retry_notification_foundation.py：135/135 PASS
v6.7.0：tests/test_e2e_v6_7_0_retry_notification_message_foundation.py：117/117 PASS
v6.8.0：tests/test_e2e_v6_8_0_retry_notification_cli_report_wiring_foundation.py：197/197 PASS
v6.9.0：tests/test_e2e_v6_9_0_wordpress_media_upload_foundation.py：331/331 PASS
v6.10.0：tests/test_e2e_v6_10_0_ai_image_generation_contract_foundation.py：78/78 PASS
v6.11.0：tests/test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py：248/248 PASS

新規対象（1ファイル、91/91 PASS）：
v6.12.0：tests/test_e2e_v6_12_0_generated_image_wordpress_media_upload_wiring_foundation.py：91/91 PASS

総合：
実行ファイル数：15
総PASS：1931
総FAIL：0
終了コード0：15ファイルすべて
終了コード非0：0
実行時Warning：0
    （"WARNING"／"Traceback"／"ConnectionError"等の文字列出現は、いずれも各E2Eが
    意図的に検証しているScenario名・Assertionラベル・Fakeによるシミュレーション結果
    （すべてPASS）であり、実行時Warningや異常ではないことを個別に確認した）

実行方式：
pytest不使用。各E2Eを`python tests/<ファイル名>.py`で個別に直接実行した
（`projects/03_game_content_ai`ディレクトリ内から実行）

Security／Side Effect：
実HTTP通信：なし
実WordPress投稿：なし
実OpenAI Client生成：なし
実WordPress Client生成：なし
実API key読込：なし
実WordPress credential読込：なし
実課金：なし

Git状態：
tracked Zero Diff維持（Regression実行前後で未追跡4ファイルのみ、tracked差分なし、
    stagedなし）。各packageへ`__pycache__`が生成されたが`.gitignore`対象であり、
    Git追跡状態・Release差分へ影響しない

Code Review中の実行履歴との区別：
Code Review（43.8〜43.10節）中に複数回実行された新規v6.12.0 E2Eの確認実行、および
Test Review（43.7節）中に実行された既存v6.9.0／v6.10.0／v6.11.0のbaseline確認実行は、
いずれも本節の正式Regression実行とは独立している。正式Regressionは、Production
Implementation・新規E2E作成・Code Review Approvedがすべて完了した後に、既存14ファイル
＋新規v6.12.0 E2Eの計15ファイルを対象として本節で改めて全実行したものである

Blocking Issue：
なし

Documentation Integration：
未実施

Release Review：
未実施
```

本文書は正式Regression（PASS）の記録である。既存Regression基準（v6.11.0 CHANGELOG.md Testedセクション、14ファイル・1840件）と新規v6.12.0 E2E（91件）を合わせた総合1931/1931 PASSを確認し、FAIL・Blocking Warning・実HTTP・実credential読込・実課金・Git状態変化のいずれも確認されなかった。Architecture Design（Public API・責務境界・Dependency Direction・Error Contract・State非保持Contract・Security Contract・Runtime Flow・Test Strategy・Zero Diff Policy・Out of Scope）はいずれもFrozenのまま維持されており、本節の反映は正式Regression結果の記録に限定される。

### 43.12 Documentation Integration

```text
Documentation Integration

判定：
Completed

Blocking Issue：
なし

Source of Truth：
docs/design/generated_image_wordpress_media_upload_wiring_foundation.md（本文書）

更新文書：
docs/ROADMAP.md
docs/architecture.md
docs/CHANGELOG.md

docs/ROADMAP.md反映内容：
更新前792行／更新後825行（+33／-5行）
「v3.x以降の候補」セクション内、Generated Image WordPress Media Upload Wiring Foundationを
    [ ]未着手 → [x]完了へ更新
主要成果（package／Public class／検証順序／Error Contract／State非保持Contract／
    既存package無改修）とTest結果（New E2E 91/91 PASS、Formal Regression 1931/1931 PASS）を反映
既存後続候補「Article → featured_media Wiring」は維持し、本Release完了による前提条件充足のみを
    注記（新規候補は追加していない）

docs/architecture.md反映内容：
更新前3335行／更新後3446行（+111行）
新規セクション「Generated Image WordPress Media Upload Wiring Foundation層」を
    v6.11.0セクションの直後へ追加
Component（generated_image_wordpress_media／GeneratedImageWordPressMediaUploader）・
    Responsibility・Package Boundary・Public API・検証順序とCapability Contract・
    依存関係（Dependency Direction・逆依存禁止）・Error Contract・State非保持Contract・
    Security Contract・Backward Compatibility・Out of Scope・Test Review／Code Review／
    Regressionの実績・Future Extensionを反映

docs/CHANGELOG.md反映内容：
更新前3421行／更新後3525行（+104行）
新規entry「## [v6.12.0] - 2026-07-18 ★ Generated Image WordPress Media Upload Wiring
    Foundation」をv6.11.0 entryの直前へ追加
Added（新規package 2ファイル・新規E2E・新規設計書）／Public API／Architecture／Behavior
    （CR-m-1反映・継続Suggestion含む）／Tested（正式対象15ファイル・1931/1931 PASS）／
    Scopeの各節を既存v6.11.0 entryの書式に忠実に記載
Changed節は独立して設けていない（既存Production package変更なしのため）
CHANGELOG.mdのv6.12.0 Testedセクションは、次Release以降の正式Regression基準として
    利用可能な形（15ファイル・1931件）で記録済み

文書間整合（確認済み）：
Version（v6.12.0）・Release名・package名（generated_image_wordpress_media）・
    Public class名（GeneratedImageWordPressMediaUploader）・New E2E（91/91 PASS）・
    Formal Regression（1931/1931 PASS）・Code Review（Approved）・Blocking Issue（なし）は
    いずれも3文書で完全一致

Historical Record：
過去Release entry変更：なし
過去Tested件数変更：なし（v6.11.0以前のCHANGELOG.md記載値はいずれも無変更で確認済み）
v6.11.0以前の履歴：維持
過去Known Issues：変更なし

Suggestionの扱い：
CR-S-1・CR-S-2・CRR-S-1はいずれも3文書で継続Suggestionとして言及し、詳細は本設計書
    （43.8〜43.10節）への参照とした。Non-Blocking・Deferred／Accepted Riskの状態を維持し、
    Release blocker・Known Issue・Open Questionのいずれへも格上げしていない

ROADMAP.md完了表現の境界（重要な注記）：
docs/ROADMAP.mdにおけるv6.12.0の[x]完了表示は、Production Implementation・New E2E・
    Code Review・Formal Regression・Documentation Integrationの完了を示すものであり、
    Release Review Approved・commit完了・push完了のいずれも意味しない。ROADMAP.md自体の
    文言はこの区別を明示的な一文としては含んでいないが、本文書（正式設計書）のStatus
    （1章）が現在の正式な工程状態（Release Review：Pending／Not Started、commit：未実施、
    push：未実施）を保持しているため、重大な誤認を招くBlocking Issueとはしない。この境界は
    Release Review工程で最終確認する

Architecture変更：
なし（Public API・検証順序・Error Contract・State非保持Contract・Security Contract・
    Dependency Direction・Zero Diff Policy・Out of Scopeはいずれも変更していない）

Production Code変更：
なし

新規E2E変更：
なし

テスト再実行：
なし

Release Review：
未実施

git add：
未実施

commit：
未実施

push：
未実施
```

本文書はDocumentation Integration（Completed）の記録である。Release 6.12の確定内容（Architecture・Public API・Error Contract・State非保持Contract・新規E2E実測値・Code Review結果・Formal Regression結果）を、`docs/ROADMAP.md`・`docs/architecture.md`・`docs/CHANGELOG.md`へ各文書の既存粒度・既存書式に忠実に統合したことを確認した。3文書間の主要項目は完全一致し、過去Releaseの記録・Tested件数はいずれも変更していない。Architecture Design（Public API・責務境界・Dependency Direction・Error Contract・Security Contract・Runtime Flow・Test Strategy・Zero Diff Policy・Out of Scope）はいずれもFrozenのまま維持されており、本節の反映はDocumentation Integration結果の記録に限定される。次工程はRelease Reviewである。

### 43.13 Release Review

```text
Release Review

判定：
Approved

Critical Finding：
0

Major Finding：
0

Minor Finding：
0

Blocking Issue：
なし

対象（Release成果物7ファイル）：
docs/design/generated_image_wordpress_media_upload_wiring_foundation.md（本文書）
src/generated_image_wordpress_media/__init__.py
src/generated_image_wordpress_media/generated_image_wordpress_media_uploader.py
tests/test_e2e_v6_12_0_generated_image_wordpress_media_upload_wiring_foundation.py
docs/ROADMAP.md
docs/architecture.md
docs/CHANGELOG.md

Architecture：
Frozen Architectureからの逸脱なし。採用モデル（GeneratedImage →
    GeneratedImageWordPressMediaUploader → WordPressMediaUploader.upload() →
    MediaUploadResult）・package名・Public class・Public API・検証順序・下流委譲・
    固定message・Error Contract・State非保持Contract・Dependency Direction・
    Security Contract・Out of Scopeのいずれも適合を確認した

Production Implementation：
Approved。Public export・Constructor（media_uploader参照保持のみ）・upload()
    （image検証→capability検証→keyword委譲→戻り値無変換）・attribute lookup
    （upload_methodを1回取得し検証・呼出両方で再利用）・例外伝播（try/except・
    raise...from 0件）・Logging・Side Effect・禁止依存のいずれも適合。
    Release Review時点でProduction Codeは初回Code Review以降一切変更されていない
    （41行・15行、内容不変を直接確認）

新規E2E：
Approved。17 Scenario／8 forループcase／91 Assertion／10 Fake・Stub、91/91 PASS、
    終了コード0。Code Review Re-Review以降、新規E2Eは一切変更されていない
    （797行、内容不変を確認）。Public import／Constructor／Capability validation／
    Validation order／Keyword delegation／MediaUploadResult返却／TypeError 3区分／
    WordPressMediaUploadError伝播／RuntimeError伝播／KeyboardInterrupt伝播／
    SystemExit伝播／State非保持（Constructor AST Guard＋upload() AST Guard）／
    Security／Logging非存在／Dependency Direction／Reverse Dependency／Side Effect
    非存在を検証範囲として確認した

Code Review：
最終判定Approved。初回Changes Required（Finding CR-m-1、Minor、Production Code適合・
    修正不要）→新規E2Eのみの修正（upload() state非保持AST Guard追加、86→91
    アサーション）→Re-Review Approved（Critical 0／Major 0／Minor 0）。初回
    Changes Requiredが最終判定として誤読される箇所は文書全体（本文書・ROADMAP.md・
    architecture.md・CHANGELOG.md）のいずれにも存在しないことを確認した

Formal Regression：
既存14ファイル1840/1840 PASS＋新規v6.12.0 E2E 91/91 PASS＝総合1931/1931 PASS。
    FAIL 0、Warning 0、終了コード非0のファイルなし。本節でも既存14ファイルの
    合計（1840）と総合計（1931）を独立に再計算し一致を確認した

Documentation Integration：
Completed／Approved。docs/ROADMAP.md・docs/architecture.md・docs/CHANGELOG.mdへの
    反映内容を正式設計書と直接照合し、Version・Release名・package名・Public class・
    New E2E（91/91 PASS）・Formal Regression（1931/1931 PASS）・Code Review
    （Approved）・Blocking Issue（なし）が3文書・正式設計書間で完全一致することを
    確認した

CHANGELOG Tested検証：
対象15ファイル（既存14＋新規1）、重複なし、欠落なし、既存合計1840・新規91・
    総合計1931（独立再計算により一致確認済み）。次Release以降の正式Regression
    基準として利用可能な形で記録されている

Historical Record：
過去Release entry・過去Tested件数・過去Known Issues・過去ROADMAP entry・既存
    architecture.mdセクションのいずれも変更されていない（tracked 3文書のgit diffが
    いずれも純粋追加のみであることを確認済み）

継続Suggestion（Non-Blocking）：
CR-S-1（DEP-2対象packageのvacuous pass耐性、Deferred）
CR-S-2（get_call_linesのattribute形式呼出未検出、Deferred）
CRR-S-1（STATE-AST-1補助Assertionの実装形状への軽微な結合、Accepted Risk）
いずれもRelease blockerではなく、新しい具体的根拠がないため格上げしていない

ROADMAP完了表現の境界：
docs/ROADMAP.mdのv6.12.0 [x]完了表現は、Production Implementation・New E2E・
    Code Review・Formal Regression・Documentation Integrationの完了を示すもので
    あり、Release Review Approved・commit完了・push完了のいずれも意味しない。
    ROADMAP.md自体にRelease Review Approved・commit済み・push済みという誤記は
    存在せず、正式設計書（本文書）のStatusが現在の正式な工程状態を保持している
    ため、重大な誤認には至らないと判断した（Finding未満の参考観察）

変更Scope：
tracked変更3ファイル（CHANGELOG.md・ROADMAP.md・architecture.md）＋未追跡4ファイル
    （本文書・Production Code 2件・新規E2E）＝Release成果物7ファイルのみ。
    想定外の変更・stagedはいずれも確認されなかった

Security／Side Effect：
実HTTP通信・実WordPress投稿・実OpenAI Client生成・実WordPress Client生成・
    実API key読込・実WordPress credential読込・実課金のいずれもなし

Release Approval Checklist：
Architecture Design：Approved
Production Implementation：Approved
New E2E：Approved
Code Review：Approved
Formal Regression：Approved
Documentation Integration：Approved
Release成果物全体：Approved

git add：
未実施

commit：
未実施

push：
未実施

origin/main同期確認：
未実施
```

本文書はRelease Review（Approved）の記録である。Release 6.12のArchitecture Design・Production Implementation・新規E2E・Code Review・Formal Regression・Documentation Integrationの全工程がFrozen Architectureおよび正式設計書と整合していることを最終確認した。Critical／Major／Minor Findingは0件であり、継続Suggestion（CR-S-1・CR-S-2・CRR-S-1）はいずれもNon-Blockingのまま維持されている。Release Review ApprovedはRelease成果物全体の承認を意味するが、git add・commit・push・origin/main同期確認はいずれも本反映時点でも未実施である。次工程は最終git add・commit・pushである。
