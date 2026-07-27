# Image Generation Fallback Policy Foundation

## 0. Header／Status

```text
Release: v6.19.0
名称: Image Generation Fallback Policy Foundation
Deferred Item: DI-1 Image Generation Fallback Policy
分類: Architecture Release
作成日: 2026-07-27
最終更新: 2026-07-27（Release Review）
基準commit: c9c9f34e2647c6ec5987a9330a500e751cb3251c（Release 6.18.0完了時点）

Status:
  Repository Survey:         Completed（本文書作成前に実施。3章参照）
  Architecture Design:       Completed（本文書）
  Architecture Review 1:     Changes Required（Blocking 1・Major 3・Minor 3・
                             Suggestion 3）
  Architecture Amendment 1:  Completed（本文書。B-1・M-1・M-2・M-3・m-1・m-2・
                             m-3・S-1〜S-3のすべてに対応）
  Architecture Review 2:     Changes Required（Blocking 0・Major 1・Minor 3・
                             Suggestion 2）
  Architecture Amendment 2:  Completed（本文書。M2-1・m-A・m-B・m-C・
                             S2-A・S2-Bのすべてに対応）
  Architecture Review 3:     Changes Required（Blocking 0・Major 2・Minor 1・
                             Suggestion 1）
  Architecture Amendment 3:  Completed（本文書。M3-1・M3-2・m3-A・S3-Aの
                             すべてに対応）
  Architecture Review 4:     Approved with Suggestions（Blocking 0・Major 0・
                             Minor 3・Suggestion 2。Minor 3件は本Review工程内で
                             限定修正により解消済み。Architecture Amendment 4：
                             Not Required）
  Production Implementation: Completed（Production Implementation工程。
                             src/image_generation_fallback_policy/
                             を§11・§13.5のPublic API・分類擬似コードのとおり
                             新規実装。既存Production Code・main.py・
                             requirements.txt・過去Release設計書は無改修）
  New E2E:                   Completed（tests/test_e2e_v6_19_0_image_generation_
                             fallback_policy_foundation.py。Correction前234
                             Assertion・234/234 PASS。Correction後254
                             Assertion・254/254 PASS・0 FAIL・exit code 0。
                             25 Scenario prefix全件実装）
  Production Code Review:    Approved with Suggestions（Blocking 0・Major 0・
                             Minor 3・Suggestion 2。Minor 3件（m-1〜m-3）は
                             本Correction工程で限定修正により解消済み）
  Production Implementation
  Correction:                Completed（Production Implementation Correction
                             工程。m-1〜m-3・s-1の4件を限定修正。
                             Architecture・Public API・Category→Action写像・
                             allow-list 4 reasonはいずれも無変更）
  Environment Repair:        Completed（Environment Repair工程。原因：指定
                             venvにopenaiが未導入。修復：
                             `openai>=2.46.0,<3.0.0`（実導入
                             version 2.48.0）を指定venvへ導入。requirements.txt
                             ・Production Code・testsは無変更）
  Formal Regression:         Completed（Formal Regression工程。正式
                             Inventory22ファイル
                             （v1.11.0・v5.9.0・v6.0.0〜v6.19.0）を1件目から
                             全件個別実行。総Assertion 3044、3044/3044 PASS、
                             FAIL 0、SKIP 0、exit code異常0、既知差分0、
                             network使用0、credential使用0。既存21ファイル
                             baseline 2790/2790 PASS完全維持＋新規v6.19
                             254/254 PASS）
  Documentation Integration: Completed（Documentation Integration工程。
                             docs/ROADMAP.md・
                             docs/architecture.md・docs/CHANGELOG.md・
                             本設計書（§13.4・§13.5の明確化を含む）へ反映。
                             件数表記を正式値（Scenario prefix 25・AC項目31件・
                             新規E2E 254 Assertion・Formal Regression
                             Inventory 22ファイル・総Assertion 3044）へ統一）
  Release Review:            Approved with Suggestions（Blocking 0・Major 0・
                             Minor 0・Suggestion 2。S-1 Status欄の指示語、
                             S-2 Release Review状態表記。いずれもRelease
                             Review工程内で限定修正により解消済み）

Release: Completed（Release Reviewの判定Approved with Suggestionsを受け、
         Release Review結果を正式文書へ反映し、Release成果物7ファイルを
         commit・push済み）
```

本文書はArchitecture Design ＋ Architecture Amendment 1 の内容を完全統合した
self-contained文書である。**Architecture Review 2は未実施であり、本文書の内容は
いずれも最終承認済みContractではない。** Production Code・テストコード・既存文書
（`docs/ROADMAP.md`／`docs/architecture.md`／`docs/CHANGELOG.md`／過去Release設計書）は
Architecture Design工程・Architecture Amendment 1工程のいずれでも変更していない。
両工程で作成・変更したファイルは本設計書1件のみである。

本文書中、`Repository調査で確認した事実`と`本設計書が提案する事項`は明確に区別して
記述する。Architecture Amendment 1で確定した事項には「Amendment 1で確定」を明記する。

### 0.1 Architecture Amendment 1 の要約（Architecture Review 1 Finding対応）

```text
B-1（Blocking）WordPress Media Upload失敗を安全に分類できない
  → WordPress Media Upload失敗を **すべて元例外の伝播**（PROPAGATE_ORIGINAL_ERROR）
    へ変更した。画像なし継続（fallback）を行わない。message解析は引き続き禁止。
    Upload側のreason分類はDeferred Item DI-10として独立させ、**DI-4 Runtime Wiring
    着手前に再検討が必要**であることをContractとして明記した（10章・20章・22章 R-1）

M-1（Major）ABORT_ARTICLE の意味が未定義
  → Action Enumを CONTINUE_WITHOUT_FEATURED_MEDIA / PROPAGATE_ORIGINAL_ERROR の
    2値へ改名・再定義した。PROPAGATE_ORIGINAL_ERROR は「policy自身がraiseする」
    意味ではなく「callerが捕捉した元例外を無変換で再送出する」意味であることを、
    Enum docstring・Decision Table・利用例・Error Contract・ACで一貫させた。
    記事ループ全体の停止可否はpolicyの決定事項ではない（11.3節・13章・16章）

M-2（Major）consumer-less先行実装の比較不足
  → 8.4節を新設し、実装時期5案を7観点で比較した。Repository根拠付きで
    「案1（Public policy contractを先行実装）」を維持する結論とした

M-3（Major）Decisionの2 fieldが冗長
  → ImageGenerationFallbackDecision の保存fieldを category 1件のみとし、
    action を read-only derived property へ変更した。無効な組み合わせが
    構造的に発生しない。__post_init__ は不要と確定した（11章・12章）

m-1（Minor）ENVIRONMENT_ERROR が汎用ImportErrorを過剰分類
  → ENVIRONMENT_ERROR を削除し UNCLASSIFIED へ統合した。Failure Categoryは
    5値 → **4値**。汎用 ImportError への isinstance 判定を設計から除去した

m-2（Minor）prompt／filename失敗が利用例のtry範囲では到達不能
  → T-23・T-24 を「条件付き（DI-4のtry範囲に依存）」へ変更し、
    推奨利用例ではtry範囲外＝policyへ到達しないことを明記した（10.2節・16.2節）

m-3（Minor）「provider非依存」が過大な表現
  → 「provider中立な分類語彙を公開し、実装は既存adapterの例外型を認識する」
    という限定表現へ全面的に置換した（4.1節・9.2節・9.4節）

S-1  生Exceptionの正規化責任層を9.5節へ明記
S-2  package名称がUpload失敗も対象とすることをTerminology（5章）へ明記
S-3  RiskをR-1〜R-8の8件で統一（22章）
```

### 0.2 Architecture Amendment 2 の要約（Architecture Review 2 Finding対応）

```text
M2-1（Major）REQUEST_REJECTED に記事固有失敗とsystemic failureが混在しており、
             全件CONTINUEはError Contractの安全側原則と矛盾する
  → `OpenAIImageGenerationErrorReason.REQUEST_REJECTED` を、新設した
    Failure Category `IMAGE_GENERATION_REQUEST_REJECTED` へ分類し、
    Actionを **PROPAGATE_ORIGINAL_ERROR** へ変更した。
    Failure Categoryは4値 → **5値**。
    `REQUEST_REJECTED` の内訳（Content Policy拒否／model不存在等）は
    本Releaseでは細分化せず、v6.11側のreason細分化を新規Deferred Item
    **DI-11** として起票し、DI-4着手前の再検討対象とした（10.6節・20章）。
    Content Policy拒否も伝播となる可用性トレードオフを10.6節 C-10で明示受諾した

m-A（Minor）`_ACTION_BY_CATEGORY` は素のdictであり
            「module-level mutable stateを持たない」という記述と矛盾する
  → 11.5節の記述を事実に合わせて修正した。
    `MappingProxyType` の採否を11.4.1節で比較し、v4.4.0 precedent と最小性から
    **素のdictを維持**する案を確定した

m-B（Minor）「将来変更は加算的方向に限られる」が過大主張
  → 8.4節 J-3 の断定を撤回し、「主たる変更方向は加算的であるが、
    分類精度やSecurity原則の見直しにより既存CONTINUEをPROPAGATEへ
    変更する可能性もある」へ限定した。**M2-1自身がその実例である**ことを明記。
    Public API早期固定リスクがゼロではないことを明示し、
    先行実装案の主要根拠をJ-1・J-2・J-4へ置き直した

m-C（Minor）DI-10実施時にAC-24が既知差分としてFAILすることが未記録
  → 20章 DI-10 と 23章 AC-24 へ、docs/CHANGELOG.md の KI-3／KI-4 precedent を
    根拠として「DI-10実施時の更新対象であり、無関係なRegressionとして
    扱わない」旨を明記した（CHANGELOG自体は変更していない）

S2-A（Suggestion）callerによる元例外再送出はDI-1 E2Eでは検証不能
  → 21.6節を新設し、DI-1 E2Eで機械検証できる範囲と、
    DI-4のProduction Implementation／Code Review／E2Eへ委ねる範囲を分離した

S2-B（Suggestion）R-4をREQUEST_REJECTEDバケットの粒度不足として再定義すべき
  → 22章 R-4 を全面再定義し、Severity・Mitigation・Deferred可否・
    DI-4前の再検討条件を更新した
```

**Amendment 2で確定した Category → Action 写像（最終）**

```text
IMAGE_GENERATION_FAILED            → CONTINUE_WITHOUT_FEATURED_MEDIA
IMAGE_GENERATION_REQUEST_REJECTED  → PROPAGATE_ORIGINAL_ERROR   ★Amendment 2で新設
IMAGE_GENERATION_NOT_AUTHORIZED    → PROPAGATE_ORIGINAL_ERROR
MEDIA_UPLOAD_FAILED                → PROPAGATE_ORIGINAL_ERROR
UNCLASSIFIED                       → PROPAGATE_ORIGINAL_ERROR
```

**Amendment 2が変更していないもの**：Public API 4 symbol（Enum 2・frozen dataclass 1・
pure function 1）、`Decision` の保存field 1件（`category`）＋ `action` derived property、
`__post_init__` を持たない判断（Q-4）、Runtime Zero Diff、Q-1・Q-2・Q-4〜Q-7の確定内容。
新設した `IMAGE_GENERATION_REQUEST_REJECTED` は、Amendment 1で削除した
`ENVIRONMENT_ERROR` の復活ではなく、**異なるActionを必要とする意味のあるCategory分割**
である（削除した `ENVIRONMENT_ERROR` はActionが `UNCLASSIFIED` と同一であったため統合した）。

### 0.3 Architecture Amendment 3 の要約（Architecture Review 3 Finding対応）

```text
M3-1（Major）UNKNOWN に programming error・systemic failure が混入しうるため、
             CONTINUE 判定が安全側原則と矛盾する
  → `OpenAIImageGenerationErrorReason.UNKNOWN` を **UNCLASSIFIED** へ分類し、
    Action を **PROPAGATE_ORIGINAL_ERROR** へ変更した。**新Categoryは追加しない**。
    v6.11 `generate()` は `except openai.APIError` の後段に `except Exception:` を持ち、
    そこで捕捉される `TypeError`／`AttributeError`／`ValidationError`／SDK内部エラーを
    すべて UNKNOWN として扱う（10.7節）。したがって UNKNOWN は
    「一過性障害と積極的に判定できないバケット」であり、
    WordPress Media Upload失敗・REQUEST_REJECTED・unknown exception と
    同じ安全側原則を適用する。
    T-20 の誤った根拠「provider通信の失敗として分類済み」を訂正した

m3-A（Minor）INVALID_RESPONSE の一過性は保証ではない
  → `INVALID_RESPONSE` も **UNCLASSIFIED** ＋ **PROPAGATE_ORIGINAL_ERROR** へ変更した。
    単発の不正応答だけでなく、provider または SDK の応答構造変更による
    systemic failure が混入しうるため（10.7節）

  → 上記2件により、CONTINUE_WITHOUT_FEATURED_MEDIA となる OpenAI reason は
    **TIMEOUT / CONNECTION / RATE_LIMIT / SERVER_ERROR の4値のみ**に限定された。
    分類方式を deny-list（「AUTHENTICATION・PERMISSION_DENIED 以外は継続」）から
    **allow-list（「この4値のみ継続、それ以外はすべて伝播」）へ転換**した（13.5節）。
    この4値についても「必ず一過性である」とは主張せず、
    「現行の分類粒度において一過性と積極的に判断する対象」と正確に記載した（10.3節）

M3-2（Major）DI-10／DI-11 と DI-4 の順序が一義でない
  → 「再検討必須」と「完了必須」の混同を解消し、**条件付き二段構え**（O-1〜O-4）
    として一義化した（10.8節）。§10.4 C-4・§10.6 C-9・20章 Deferred Items・
    DI-4との関係・26章 ROADMAP更新計画・22章 Risks・23章 AC-29・29章 Checklist で
    表現を統一した

S3-A（Suggestion）CONTINUE側 reason の残存リスクが Risk へ未記載
  → 22章 R-7 を再構成し、「CONTINUE対象4 reason の一過性は現行分類粒度に依存する
    判断であり、v6.11 の分類が変化した場合に見直しを要する」という残存リスクを
    統合して記録した。**R-1〜R-8 の8件という件数は維持**している
```

**Amendment 3で確定した reason → Category → Action 写像（最終）**

```text
OpenAI reason 9値の分類（4 / 1 / 2 / 2）
  TIMEOUT / CONNECTION / RATE_LIMIT / SERVER_ERROR
      → IMAGE_GENERATION_FAILED            → CONTINUE_WITHOUT_FEATURED_MEDIA
  REQUEST_REJECTED
      → IMAGE_GENERATION_REQUEST_REJECTED  → PROPAGATE_ORIGINAL_ERROR
  AUTHENTICATION / PERMISSION_DENIED
      → IMAGE_GENERATION_NOT_AUTHORIZED    → PROPAGATE_ORIGINAL_ERROR
  INVALID_RESPONSE / UNKNOWN
      → UNCLASSIFIED                       → PROPAGATE_ORIGINAL_ERROR   ★Amendment 3で移動

WordPressMediaUploadError
      → MEDIA_UPLOAD_FAILED                → PROPAGATE_ORIGINAL_ERROR
未知reason・未知例外
      → UNCLASSIFIED                       → PROPAGATE_ORIGINAL_ERROR
```

**Amendment 3が変更していないもの**：Failure Category の5値そのもの（新設・削除なし）、
Public API 4 symbol、`Decision` の保存field 1件（`category`）＋ `action` derived property、
`__post_init__` を持たない判断（Q-4）、Runtime Zero Diff、Q-1・Q-2・Q-4〜Q-7の確定内容、
WordPress Media Upload失敗および REQUEST_REJECTED の契約（Amendment 1・2で確定済み）。

---

## 1. Background

Release 6.9.0〜6.18.0で、AI画像生成からWordPress featured media設定に至る一連の
Consumer-less Foundationが整備された。

```text
v6.9.0   wordpress_media                       WordPress Media Upload
v6.10.0  ai_image_generation                   Provider非依存Contract（Protocol＋値オブジェクト）
v6.11.0  openai_image_generation               OpenAI Images API Adapter
v6.12.0  generated_image_wordpress_media       GeneratedImage → Media Upload Wiring
v6.13.0  article_featured_media                media_id → ArticleData.featured_media_id Binding
v6.14.0  article_featured_media_orchestration  generate → upload → bind の固定順序Orchestration
v6.15.0  image_generation_config               Configuration-First Gate
v6.16.0  generated_image_filename_policy       filename構築（pure function）
v6.17.0  article_image_prompt_construction     prompt構築（pure function）
v6.18.0  article_featured_media_composition    Composition Root（構築・接続・可用性公開）
```

これら10 Foundationはいずれも**Consumer-less**であり、`main.py`／`image_resolver.py`／
`OutputManager`／Pipeline／Scheduler／Retry Runtimeのいずれからも参照されていない
（Runtime Zero Diffが10 Release連続で維持されている）。

Release 6.18.0のComposition Rootは、**構築（construction）** の責務のみを持ち、
**実行（`apply()`）と失敗時の継続／中止判断は明示的にNon-Goal**として除外した
（`docs/design/article_featured_media_composition_root_foundation.md` 5章 N-1・N-5、
および同9章）。その除外の理由は設計書とROADMAPの双方に記録されている。

> `Null Objectは採用せず`None`＋`is_available()`（`orchestrator is not None`）とし、
> Fallback Policy（画像なしで記事投稿を継続するか等の業務判断）を本Releaseへ
> 先取りしない設計とした。
> （`docs/ROADMAP.md` v6.18.0 Entry）

本Release候補は、その意図的に空けられた穴——**画像生成またはMedia Uploadが実行時に
失敗したとき、記事投稿を画像なしで継続するか、元の例外を伝播するか**——を、Runtimeへ
配線せずに確立するFoundationである。

---

## 2. Problem Statement

### 2.1 現状の欠落

Repository調査で確認した事実は次のとおりである。

```text
P-1  v6.14 ArticleFeaturedMediaOrchestrator.apply() は try／except を1つも持たず、
     generate()／upload()／bind_featured_media() 由来の例外をすべて無変換伝播する
     （src/article_featured_media_orchestration/article_featured_media_orchestrator.py、
       docs/architecture.md「Error Contract」節：
       「try／except・例外wrapper・raise ... from ...・fallback・自動retry・
         partial success resultはいずれも持たない」）

P-2  v6.18 ArticleFeaturedMediaCompositionRoot も try／except を1つも持たない
     （AST検証で ast.ExceptHandler 0件を確認済み、同設計書 AC-11）

P-3  したがって現時点でRepositoryのどこにも、画像生成の実行時失敗を受け止める層が
     存在しない。将来Runtime Wiring（DI-4）が apply() を記事ループ内で呼び出した瞬間、
     画像生成の1回の失敗が記事1件の生成全体を停止させる

P-4  一方で「画像なしで記事を投稿する」という状態は、既存Runtimeに既に存在する
     ・src/outputs/base.py:24  featured_media_id: int = 0  # 0 = アイキャッチなし
     ・src/outputs/wordpress_output.py:66-67
         if article.featured_media_id > 0:
             payload["featured_media"] = article.featured_media_id
     ・main.py:337  featured_media_id = resolve_media_id(item, default_media_id)
     → featured_media_id が 0 のとき、WordPress payload に featured_media キー自体が
       含まれず、記事はアイキャッチなしで正常に投稿される

P-5  すなわち「画像を諦めて記事投稿を継続する」ための**出力側の受け皿は既に完成しており**、
     欠けているのは「いつ諦めてよいか」を定める判断規則だけである
```

**P-4・P-5は本設計の中核的な根拠である。** DI-1は新しい代替出力経路を作る必要がない。
既存の `featured_media_id = 0` 経路がそのまま「画像なし継続」の実体である。

### 2.2 判断規則が無いまま進めた場合の危険

```text
・DI-4 Runtime Wiringが、その場しのぎの `try: ... except Exception: pass` を
  main.py へ埋め込む形で実装されうる（silent failure、CLAUDE.mdの保守方針に反する）
・credential誤設定（例：OPENAI_API_KEYが失効）が、全記事で無音のまま画像なし投稿へ
  劣化し、運用者が気づけない
・逆に一過性のrate limit 1回で記事生成全体が停止する
・v6.14／v6.18が10 Releaseかけて維持した「例外を握りつぶさない」Contractが、
  Wiring工程の1コミットで失われる
```

---

## 3. Repository Survey Findings

本章はすべて、基準commit `c9c9f34` 時点の実ファイル読み取りに基づく。
S-12〜S-15はArchitecture Amendment 1で追加した確認事項である。

### 3.1 ROADMAPにおけるDI-1の正式記述

`docs/ROADMAP.md`（Deferred Items節）:

```text
- [ ] **Image Generation Fallback Policy**（次候補）：画像生成・Upload失敗時に記事投稿を
  継続するか中止するかの業務判断を確立するFoundation。v6.18.0の`None`＋`is_available()`採用は、
  本Foundation未着手のままFallback判断を先取りしないための意図的な設計判断である
```

同じくROADMAP「Article Featured Media Runtime Wiring」Entry:

```text
ただし画像生成のFallback Policy（Image Generation Fallback Policy、次候補）は
依然未着手であり、本Wiringへ直行できる状態には至っていない
```

**確定事項 S-1**：ROADMAPが定めるDI-1の意味は「**画像生成・Upload失敗時に記事投稿を
継続するか中止するかの業務判断**」である。代替画像・代替provider・retry・例外の
握り潰しのいずれもROADMAPの記述に含まれない。

### 3.2 architecture.md における関連記述

| 箇所 | 記述 |
|---|---|
| Orchestration層「Error Contract」 | 「try／except・例外wrapper・`raise ... from ...`・fallback・自動retry・partial success resultはいずれも持たない」 |
| Orchestration層「Out of Scope」 | 「fallback Policy」を明示的に対象外として列挙 |
| Composition Root層「Package Boundary」 | 「失敗時の継続／中止判断（Fallback Policy）…はいずれも対象外である」 |
| Composition Root層「Gate／Availability Contract」 | 「Null Objectは採用せず、Fallback Policy（`Image Generation Fallback Policy`、未着手）の判断を本層へ先取りしない」 |
| Filename Policy層／Orchestration層「Future Extension」 | 「Image Generation Fallback Policy」をFuture Extension候補として列挙 |

**確定事項 S-2**：architecture.mdはDI-1を一貫して「失敗時の継続／中止判断」と定義しており、
ROADMAPと矛盾しない。

### 3.3 Repository内の既存「fallback」用語（重要：意味が異なる）

`fallback`という語はRepository内に既に存在するが、**DI-1とは異なる意味**で使われている。

| 箇所 | 既存の意味 | DI-1との関係 |
|---|---|---|
| `src/generated_image_filename_policy/generated_image_filename_policy.py` `_hash_fallback_basename()` | ASCII slugが得られないときの**代替basename生成** | 無関係。文字列生成の代替値 |
| `src/article_image_prompt_construction/` | excerptが1文字も入らないときの**title-only prompt組み立てへの切り替え** | 無関係。組み立て分岐 |
| `docs/architecture.md` Retry Scheduler Decision Wiring層 | `retry_decision=None`時の**ガード節による安全なデフォルト値** | 概念的に近いが対象領域が異なる |

**確定事項 S-3**：DI-1が扱う「Fallback」は上記いずれとも異なる、**業務判断（継続／伝播）**
の意味である。用語衝突を避けるため、本設計は5章 Terminologyで語彙を明示的に定義する。

### 3.4 画像生成失敗が現在どの層からどの例外として表面化するか

実ファイル読み取りにより確認した、実行時（`apply()`実行中）の例外経路。

```text
ArticleFeaturedMediaOrchestrator.apply(article, prompt, filename)
  │
  ├─ [1] 引数validation
  │      ValueError（"article must be an ArticleData" 等、固定message 5種）
  │
  ├─ [2] self._image_generator.generate(prompt)
  │      └ OpenAIImageGenerator.generate()
  │          ├ import openai        → ModuleNotFoundError（try範囲外。実測確認）
  │          ├ _validate_prompt()   → ValueError（4種の固定message）
  │          ├ _get_client()        → TypeError（injected clientがwith_optionsを持たない場合）
  │          ├ client.images.generate(...)
  │          │   └ openai.APIError系 → OpenAIImageGenerationError（reason付き）
  │          │   └ その他Exception   → OpenAIImageGenerationError(UNKNOWN)
  │          └ _build_generated_image()
  │              └ 構造不正／base64不正／空 → OpenAIImageGenerationError(INVALID_RESPONSE)
  │              └ GeneratedImage.__post_init__ → ValueError（構造上到達不能。10.2節 T-21）
  │
  ├─ [3] self._media_uploader.upload(generated_image, filename)
  │      └ GeneratedImageWordPressMediaUploader.upload()
  │          ├ ValueError（"image must be a GeneratedImage"）
  │          ├ TypeError（media_uploaderがuploadを持たない）
  │          └ WordPressMediaUploader.upload()
  │              ├ ValueError（image_bytes／filename／mime_type validation）
  │              └ WordPressMediaUploadError（通信失敗・非2xx・レスポンス不正）
  │
  └─ [4] bind_featured_media(article, media_result)
         └ ValueError（3種の固定message）
```

**確定事項 S-4**：実行時の外部要因による失敗は、**2つの専用例外型に集約されている**。

```text
OpenAIImageGenerationError（RuntimeError継承、src/openai_image_generation/）
    ・reason: OpenAIImageGenerationErrorReason（Enum）を必ず保持する
    ・Enum値: AUTHENTICATION / PERMISSION_DENIED / RATE_LIMIT / TIMEOUT /
              CONNECTION / REQUEST_REJECTED / SERVER_ERROR / INVALID_RESPONSE / UNKNOWN
    ・messageは固定文字列のみ（Provider例外オブジェクト・レスポンス生データ・
      prompt・API keyのいずれも保持しない。同モジュールdocstringに明記）
    ・OpenAIImageGenerationErrorReason は openai_image_generation.__all__ に含まれる
      Public APIである

WordPressMediaUploadError（RuntimeError継承、src/wordpress_media/）
    ・reason属性を**持たない**（分類Enumが存在しない）
    ・messageは "WordPress Media API returned HTTP {status_code}" に加え、
      WordPressレスポンスJSONの code（100文字まで）・message（200文字まで）を
      制御文字sanitize後に連結しうる（_build_non_2xx_message()）
    ・**認証(401)・権限(403)・一過性(429/500/502/503)・network失敗
      （requests.RequestException）・応答不正のすべてがこの単一型へ集約される**
```

**確定事項 S-5**：`OpenAIImageGenerationError.reason` は**secret-freeであることが
v6.11設計で保証された安全な分類ラベル**である。一方 `WordPressMediaUploadError` の
messageは**Provider応答本文の一部を含みうる**。この非対称性は本設計の決定的な制約であり、
**Architecture Review 1 Finding B-1の直接の原因**である（10.4節）。

### 3.5 configuration construction時とapply()実行時の失敗境界

| 時点 | 失敗例 | 例外 | 現在の扱い |
|---|---|---|---|
| `ImageGenerationConfig.from_env()` | Gate値不正・未設定 | なし | Fail Closed（`enabled=False`）。v6.15 |
| `ArticleFeaturedMediaCompositionRoot.from_env()` | `OPENAI_API_KEY`未設定 | `ValueError` | Fail Fast・無変換伝播。v6.18 E-3 |
| 同上 | `WP_*`未設定 | `ValueError` | Fail Fast・無変換伝播。v6.18 E-5 |
| 同上 | `__post_init__`不変条件違反 | `ValueError`／`TypeError` | 送出。v6.18 E-11〜E-13 |
| `apply()`実行中 | rate limit・timeout・HTTP 500等 | 専用例外2種 | **v6.18設計書 E-15が「本ReleaseのOut of Scope。Fallback Policy（別Release）の対象」と明記** |

**確定事項 S-6**：v6.18設計書16章 E-15が、実行時失敗をDI-1へ正式に引き渡している。
**構築失敗（Fail Fast、DI-1対象外）と実行失敗（DI-1対象）の境界は、既にRepository上で
確定している。** 本設計はこの境界を変更しない。

### 3.6 既存のpolicy／decision／result object設計パターン

| Release | 構成 | 特徴 |
|---|---|---|
| v3.0.0 `RetryPolicy` | `@dataclass(frozen=True)` ＋ `from_env()` ＋ `should_retry()` | 設定値を持つpolicy object。判定はbool |
| v4.5.0 `RetryDecisionPolicy` / `ExplainableRetryPolicy` | `@runtime_checkable Protocol` | 既存classを無改修のまま差し替え可能にする2段階Protocol |
| v4.4.0 `retry_outcome_terminality` | Enum ＋ **module-level分類表dict** ＋ `classify_*()` 関数 | **例外ではなく値を分類する純関数**。`classify_terminality()` は `RETRY_OUTCOME_TERMINALITY[reason]` という**直接subscript**（`.get(default)`は不使用） |
| v6.4.0 | `RetryHealthEvaluator` → `RetryHealthReport(status)` ＋ `RetryHealthStatus` Enum | Evaluator＋frozen結果object＋Enum。結果objectは**1 fieldのみ**、`__post_init__`なし |
| v6.5.0 | `RetryAlertEvaluator` → `RetryAlert(level)` ＋ `RetryAlertLevel` Enum | 同上。語彙をMonitoring側と**意図的に分離** |
| v6.6.0 | `RetryNotificationEvaluator` → `RetryNotificationDecision(status)` ＋ `RetryNotificationStatus` Enum | 同上。`NO_NOTIFICATION`は「正常に評価した結果、対象外」であり失敗・スキップ・未実行を意味しないと明記 |
| v6.13／v6.16／v6.17 | module-level pure function（`bind_featured_media` / `generate_image_filename` / `construct_article_image_prompt`） | **直近3 Releaseはいずれも「依存注入を必要としないmodule-level function」形式** |

**確定事項 S-7**：Repositoryには「Evaluator class ＋ frozen結果object ＋ Enum」
（v6.4〜v6.6）と「module-level pure function」（v6.13／v6.16／v6.17）の2系統の
precedentがある。本設計は**両者を組み合わせる**（module-level function が
frozen結果objectを返す）。

**確定事項 S-8**：v6.4〜v6.6の結果objectはいずれも**保存fieldが1件**であり、
**`__post_init__` を持たない**。Architecture Amendment 1（M-3対応）はこのprecedentに
完全に一致させた（11章・12章）。

### 3.7 実行環境の実測

`projects/03_game_content_ai/venv/Scripts/python.exe -m pip list` の結果:

```text
Python 3.14.6
インストール済み: anthropic 0.112.0 / requests 2.34.2 / feedparser / httpx /
                  pydantic / beautifulsoup4 / python-dotenv 等
インストール**されていない**: openai, google-auth, google-api-python-client,
                              google-analytics-data
```

**確定事項 S-9**：`openai`パッケージはこのvenvに**インストールされていない**
（`requirements.txt`には`openai>=2.46.0,<3.0.0`として宣言されているが未インストール）。
それでもv6.11以降のE2Eが全件PASSしているのは、`openai`のimportが
`_get_client()` / `generate()` / `_classify_api_error()` の**関数内遅延import**に
限定されているためである（`openai_image_generator.py` のmodule-level importは
`base64` / `binascii` / `os` / `enum` / `ai_image_generation.GeneratedImage` のみ）。

**帰結（本設計への制約）**
```text
・本Releaseの実装・E2Eは、openai未インストール環境で完全に成立しなければならない
・したがって openai.APIError 等のProvider例外型を isinstance 判定へ直接用いてはならない
・OpenAIImageGenerationError（v6.11が定義するRepository内の型）のみを判定対象とする
・**Provider固有の例外名（openai.AuthenticationError 等）は、既存adapter
  （openai_image_generator.py の _classify_api_error()）の実装から読み取った事実として
  記載する。installed SDKによる再確認は本環境では実施できない（未インストールのため）。**
```

**確定事項 S-10**：`wordpress_media` はmodule-levelで `requests` をimportするが、
`requests` はインストール済みであり、importに支障はない。

**確定事項 S-11（実装に無関係な観測）**：`tests/test_e2e_v6_18_0_*.py` のdocstringにある
実行方法 `..\..\venv\Scripts\python.exe` が指す `C:\Projects\claude-code-repository\venv`
は**存在しない**。実在するのは `projects/03_game_content_ai/venv/` である。これは
既存文書の記載差であり、本Releaseの対象外である（本工程では修正しない）。

### 3.8（Amendment 1追加）publish境界の実際の失敗処理

Architecture Review 1 Finding M-1の判定根拠として、publish境界の実挙動を確認した。

```text
確定事項 S-12：src/outputs/manager.py:34-42
    OutputManager.save_all() は各出力先の save() を
        try:  result = output.save(article)
        except Exception as e:
              print(f"  [警告] ... 保存失敗: {e}")
              results.append(SaveResult(success=False, ...))
    で囲み、**broad な except Exception で捕捉して次の出力先へ継続**する。

確定事項 S-13：src/outputs/wordpress_output.py:70-79
    WordPressOutput.save() は非2xxで RuntimeError を送出する（SaveResultを返さない）。
    これは S-12 の except Exception により捕捉される。

確定事項 S-14：main.py:353-365
    wp_save.success が False の場合、wp_failed_count を加算し警告を表示するが、
    **記事ループは停止しない**。

帰結（M-1への影響）:
    このRepositoryにおいて「記事1件の失敗」は「run全体の停止」を意味しない。
    したがって policy が返す判断は「run全体の停止可否」を決定してはならない。
    policy は「元例外を無変換で再送出するか否か」のみを決定し、
    再送出された例外がどの層で受け止められるか（記事単位か run 単位か）は
    DI-4 および既存 Runtime 境界（OutputManager 等）の責任である。
    → 11.3節・13章・16章でこの意味を一貫させた（Amendment 1、M-1対応）。

確定事項 S-15：src/pipeline/publish_pipeline_runner.py:73 ほか3ファイル
    Pipeline層も except Exception による broad catch を用いている。
    したがって DI-4 が apply() を except Exception で囲むこと自体は、
    このRepositoryの既存パターンから逸脱しない。
```

### 3.9（Amendment 1追加）未対応Enum値に対する既存Repositoryの方針

```text
確定事項 S-16：src/retry_notification/retry_notification_evaluator.py
    RetryNotificationEvaluator.evaluate() は既知3値を明示的・網羅的に分岐させ、
    docstringで
      「dictの .get(level, デフォルト値) のような『知らない値は既定値へ丸める』形は
        採らない」
      「未対応のLevelを … いずれへも自動的にフォールバックすることを禁止する。
        未対応のLevelを検知した場合はValueErrorを送出する（Fail Fast契約）」
    と明記している。

確定事項 S-17：src/retry_engine/retry_outcome_terminality.py
    classify_terminality() は RETRY_OUTCOME_TERMINALITY[reason] という
    **直接subscript**であり、未登録キーは KeyError として顕在化する
    （既定値へ丸めない）。同モジュールdocstringは、Enum値追加時に分類表への
    追従を怠ると実行時に例外でクラッシュすることを「恒久ルール」として警告している。

本設計における適用（Amendment 1で確定、13.4節）:
    ・Category → Action の写像は S-17 に倣い **直接subscript** とする
      （未登録Categoryは KeyError として顕在化。既定値へ丸めない）
    ・ただし **入力例外の reason 属性が未知値だった場合は S-16 と異なる扱いをする**。
      policy は except 節の内側から呼ばれるため、ここで新しい ValueError を
      送出すると元例外を置き換えて診断情報を破壊する（13.2節「例外wrapperを作らない」に反する）。
      したがって未知 reason は UNCLASSIFIED（→ 元例外の伝播）へ倒す。
      **これは S-16 precedent からの意図的な逸脱であり、逸脱理由を13.4節に明記する。**
```

---

## 4. DI-1の意味の確定

### 4.1 採用する定義（Amendment 1で表現を限定：m-3対応）

> **DI-1 Image Generation Fallback Policy とは、`ArticleFeaturedMediaOrchestrator.apply()`
> の実行中に発生した失敗に対し、「その記事の投稿をfeatured mediaなしで継続してよいか、
> それとも呼び出し側が元の例外を無変換で再送出すべきか」を決定する、stateless・
> 副作用なしの判断規則である。**
>
> **本policyは provider中立な分類語彙（Failure Category）を公開する。ただし実装は、
> Repository内に実在する既存adapterの例外型（`OpenAIImageGenerationError`／
> `WordPressMediaUploadError`）を認識する。したがって「provider非依存」ではなく
> 「provider中立な語彙 ＋ adapter認識型の分類」である**（限定の詳細は9.4節）。

### 4.2 採用しない意味（推測による混入の明示的排除）

| 推測されうる意味 | 採用しない理由（Repository根拠） |
|---|---|
| 代替画像（デフォルト画像）の使用 | ROADMAP・architecture.mdのいずれにも記述がない。既存 `DEFAULT_MEDIA_ID`（`main.py:337` `resolve_media_id`）との統合は、v6.14設計書がOut of Scopeとして明記済み |
| 代替provider（別の画像生成API）への切り替え | ROADMAPに記述がない。第2のAdapterがRepositoryに存在しない。切り替え可能性はDI-2の領域 |
| retry（再試行） | ROADMAPがDI-6「Media Upload Retry／Idempotency Foundation」を**別項目**として立てている。v6.14設計書も「自動retry」をOut of Scopeとして分離 |
| 例外の握り潰し（`except Exception: pass`） | 2.2節。v6.14／v6.18が維持した「握りつぶさない」Contractに正面から反する |
| Null Object（no-op orchestrator）の導入 | v6.18が12章で比較のうえ明示的に不採用としており、その理由が「Fallback Policyの先取り回避」である。DI-1側からNull Objectを再導入するのは循環である |
| 記事ループ全体の停止可否の決定 | **（Amendment 1追加、M-1対応）** S-12〜S-14のとおり、失敗の受け止め層は既にRepositoryに存在する（`OutputManager`・`main.py`）。policyがrun全体の制御を決めることは責務越境である |

### 4.3 本Releaseが定義するものの範囲

**結論：本Release候補6.19.0は「policy contract（判断規則）と決定結果の表現」のみを定義し、
判断の実行（try／exceptによる捕捉と再送出）とRuntimeへの適用は行わない。**

根拠:

```text
R-1  DI-4 Runtime Wiringは未着手であり、apply() を呼び出す消費者がRepositoryに存在しない。
     捕捉すべき呼び出し箇所が無いため、捕捉コードを書く場所が無い
R-2  v6.9〜v6.18の10 Releaseすべてが「Consumer-less Foundation → 後続Wiring」という
     順序を守っている（Foundation First。architecture.md「消費者不在の先行実装」節）
R-3  policy判断とtry／except実行を同一Releaseで行うと、DI-4のRuntime Wiring設計
     （どの層でcatchするか・記事ループのどこに置くか）を先取りすることになる
R-4  判断規則のみであれば外部接続ゼロ・Runtime Zero Diffを維持したまま、
     全Contractを決定的にE2E検証できる
```

**（Amendment 1追加、M-2対応）** 上記R-1〜R-4は「捕捉を実装しない」根拠である。
「policy contractのProduction Codeを本Releaseで書くべきか、それとも設計確定のみに
留めてDI-4へ委ねるべきか」という別の論点は、**8.4節で5案を比較のうえ確定した**。

---

## 5. Terminology

3.3節で確認した用語衝突を避けるため、本文書内では次の語彙を用いる。

| 用語 | 定義 |
|---|---|
| **Fallback（本文書）** | 画像featured media処理の失敗を受けて、**記事投稿をfeatured mediaなしで継続する**こと。文字列の代替値生成（v6.16 hash fallback basename）・prompt組み立ての分岐（v6.17 title-only fallback）とは無関係である |
| **Fallback Action** | 失敗に対して取るべき行動。本設計では `CONTINUE_WITHOUT_FEATURED_MEDIA` と `PROPAGATE_ORIGINAL_ERROR` の2値のみ（11章） |
| **PROPAGATE（伝播）** | **policy自身が例外をraiseすることではない。** policyは判断を返すだけであり、捕捉した元例外を無変換で再送出する主体は呼び出し側（DI-4）である（11.3節・13章） |
| **Failure Category** | 失敗の**provider中立な分類**。provider名・provider固有のエラーコード・HTTPステータス・応答本文を含まない固定ラベル |
| **Decision** | Failure Categoryを保持し、Actionを導出するimmutableな判定結果object |
| **Fail Fast** | 設定不備・credential不足を、記事生成が始まる前に例外として即座に表面化させること（v6.18 13.3節の用語をそのまま継承） |
| **Silent Failure** | 失敗が発生したにもかかわらず、呼び出し側から成功と区別できない状態。本設計が構造的に禁止する |
| **Construction Failure** | `from_env()`／constructorで発生する失敗。DI-1の対象外 |
| **Runtime Failure** | `apply()`実行中に発生する失敗。DI-1の対象 |

### 5.1（Amendment 1追加、S-2対応）package名称についての注記

package名・function名は `image_generation_fallback_policy` /
`decide_image_generation_fallback` であり、名称上は「画像生成（Image Generation）」の
失敗だけを対象とするように読める。**しかし実際の対象範囲は、`apply()` が実行する
featured media処理全体（generate → upload → bind）の失敗である。**

```text
名称を維持する理由:
    docs/ROADMAP.md の正式名称「Image Generation Fallback Policy」と一致させるため
    （Deferred Item DI-1 の追跡可能性を優先）。

実際の対象範囲:
    ・画像生成（generate）の失敗            → 分類対象
    ・Media Upload（upload）の失敗          → 分類対象（10.4節・元例外の伝播）
    ・featured media binding（bind）の失敗  → 分類対象（UNCLASSIFIED）
    ・prompt構築／filename構築の失敗        → 条件付き（10.2節 T-23・T-24、16.2節）

代替案（`article_featured_media_fallback_policy`）は範囲をより正確に表すが、
ROADMAPの正式名称との不一致による追跡性低下を上回る利点がないと判断した
（Open Question Q-7、28章で確定）。
```

---

## 6. Goals

```text
G-1  画像生成・Media Upload の実行時失敗に対し、「featured mediaなしで記事投稿を
     継続する」か「呼び出し側が元例外を無変換で再送出する」かを決定する
     判断規則を確立する

G-2  その判断が silent failure にならないよう、決定結果を呼び出し側が
     通常成功と明確に識別できる形で表現する

G-3  configuration error・credential error・permission error・programming error を
     fallback（継続）で隠さない。v6.18が確立したFail Fastを維持する

G-4  Construction Failure（DI-1対象外）と Runtime Failure（DI-1対象）の境界を
     Contractとして明文化する

G-5  Repository調査に基づく Failure Taxonomy を作成し、各分類が
     fallback対象・伝播対象・本Release対象外のいずれかであることを一意に定める

G-6  Runtime Zero Diff を維持する（main.py・既存Production Code無改修）

G-7  DI-2／DI-3／DI-4／DI-5／DI-6を先取りしない

G-8  外部接続ゼロ・実credential不要でE2E検証可能な設計とする

G-9  （Amendment 1追加）安全に分類できない失敗を fallback（継続）へ倒さない。
     分類の確度が不足する領域は、元例外の伝播という安全側へ倒し、
     分類精度の向上を独立Deferred Itemとして明示する
```

---

## 7. Non-Goals（Out of Scope）

```text
N-1   try／except による実際の例外捕捉および再送出（DI-4 Runtime Wiringの責務）
N-2   Runtimeへの配線（main.py / image_resolver.py / OutputManager / Pipeline /
      Agent / Scheduler / Retry Runtime / scripts）
N-3   apply() の呼び出し
N-4   代替画像・デフォルト画像の選択（DEFAULT_MEDIA_ID統合を含む）
N-5   代替providerへの切り替え（DI-2の領域）
N-6   retry・backoff・retry exhausted状態の管理（DI-6）
N-7   idempotency・重複Upload防止（DI-6）
N-8   未使用WordPress Mediaのcleanup（DI-7）
N-9   logging／metricsの実装（DI-5。本Releaseは観測契約の定義のみ、18章）
N-10  ArticleFeaturedMediaOrchestrator（v6.14）の改修
N-11  ArticleFeaturedMediaCompositionRoot（v6.18）の改修
N-12  OpenAIImageGenerator（v6.11）・WordPressMediaUploader（v6.9）の改修
N-13  AIImageGenerator Protocol（v6.10）の拡張
N-14  新規環境変数の導入（.env.example無変更）
N-15  dependency追加（requirements.txt無変更）
N-16  policyの外部設定化（環境変数・設定ファイルからの読み込み）
N-17  **WordPressMediaUploadError への reason 分類Enum追加（Deferred Item DI-10。
      v6.9のPublic API変更を伴うため独立Releaseを要する。ただしDI-4着手前の
      再検討を必須とする。20章・22章 R-1）**
N-18  Gate値のstrict validation（DI-9）
N-19  Documentation Integration（ROADMAP／architecture.md／CHANGELOG更新）
N-20  **（Amendment 1追加、m-2対応）DI-4が採用すべき try 範囲の規定。
      prompt構築・filename構築を try の内側に置くか外側に置くかは
      DI-4の設計事項であり、本Releaseは規定しない（16.2節）**
N-21  **（Amendment 1追加、M-1対応）記事ループ全体の停止可否・記事単位の
      スキップ手段・OutputManager上位での扱いの決定（DI-4および既存Runtime境界の責任）**
N-22  **（Amendment 2追加、M2-1対応）`OpenAIImageGenerationErrorReason.REQUEST_REJECTED`
      の内訳細分化（Content Policy拒否 / model不存在 / その他の分離）。
      v6.11 `_classify_api_error()` の改修を伴うため Deferred Item DI-11 とする
      （10.6節 C-8・C-9、20章）**
```

---

## 8. Design Alternatives

### 8.1 責務配置の候補一覧

| 案 | 内容 |
|---|---|
| **A** | Image generator adapter内部（v6.11 `OpenAIImageGenerator.generate()`）で失敗を吸収し、`GeneratedImage`または`None`を返す |
| **B** | generatorを包むfallback-aware decorator／wrapper（`FallbackAwareImageGenerator`）を新設する |
| **C** | `ArticleFeaturedMediaOrchestrator`（v6.14）を改修し、`apply()` 内部でgraceful skipする |
| **D** | `ArticleFeaturedMediaCompositionRoot`（v6.18）または将来のRuntime Wiring層で判断する |
| **E** | **独立したConsumer-less policy／decision component を新設する（第一推奨）** |

### 8.2 比較表

| 観点 | A: adapter内部 | B: decorator | C: Orchestrator改修 | D: Composition Root／Runtime層 | **E: 独立policy** |
|---|---|---|---|---|---|
| 責務境界 | ✗ adapterがprovider通信と業務判断を兼務 | △ 判断とgenerate委譲を兼務 | ✗ Orchestratorが順序制御と業務判断を兼務 | ✗ v6.18は構築のみ（設計書9章で明示除外） | ◎ 判断のみ |
| Public API変更量 | ✗ `generate()`戻り値をOptional化（Protocol破壊） | △ 新規class 1件＋Protocol整合 | ✗ `apply()`戻り値の意味変更 | ✗ v6.18の責務定義に反する改修 | ○ 新規package・4 symbol |
| Production Code変更範囲 | v6.11＋v6.10 Protocol | 新規package | v6.14 | v6.18またはmain.py | 新規packageのみ |
| testability | △ providerモック必須 | △ generatorモック必須 | △ 2 dependency注入必須 | ✗ env依存 | ◎ 例外objectを渡すだけ、外部依存ゼロ |
| provider結合度 | ✗ OpenAI固有層に業務判断が入る | ○ | ○ | ○ | ○ 語彙は中立、分類のみadapter認識（9.4節） |
| Fail Fast維持 | ✗ ValueError（prompt不正）まで吸収しうる | △ 実装次第 | ✗ 引数validation ValueErrorと混同しやすい | △ | ◎ 分類で明示分離 |
| DI-2先取りリスク | 高（Protocol変更＝capability再定義） | 高（wrapperはcapability抽象を要求） | 中 | 低 | **なし**（generatorに触れない） |
| DI-3先取りリスク | 中 | 中 | **高**（Orchestration v2そのもの） | 低 | **なし** |
| DI-4先取りリスク | 低 | 低 | 低 | **高**（Runtime配線を含む） | **なし** |
| Security | ✗ 失敗情報がadapter外へ漏れる形を再設計要 | △ | △ | △ | ◎ 分類ラベルのみ返却（17章） |
| observability | ✗ Noneが返るだけで理由が消える | △ | ✗ 「画像なしArticleData」と成功が区別不能 | △ | ◎ Categoryが常に残る |
| Runtime Zero Diff | ✗ v6.11変更 | ○ | ✗ v6.14変更 | ✗ | ◎ 新規追加のみ |
| 将来拡張性 | ✗ | ○ | △ | △ | ◎ Category追加が加算的（8.4節） |
| 実装複雑度 | 高 | 中 | 中 | 高 | 低 |
| 回帰リスク | **高**（v6.10/v6.11のE2E多数に影響） | 低 | **高**（v6.14 E2E 217アサーション） | 高 | **なし**（既存無改修） |

### 8.3 各案を採用しない具体的理由

**案A（adapter内部）を採用しない理由**
`AIImageGenerator` Protocol（v6.10）の `generate(prompt) -> GeneratedImage` は
戻り値をOptionalとしていない。Optional化すると、v6.10 Protocol・v6.11 Adapter・
v6.12 Wiring・v6.14 Orchestratorのすべてが影響を受ける破壊的変更となる。
またprovider通信の詳細を知る層に業務判断を持ち込むのは、v6.11が
`_classify_api_error()` で「分類はするが判断はしない」と線を引いた設計思想に反する。

**案B（decorator／wrapper）を採用しない理由**
wrapperは `AIImageGenerator` として振る舞う必要があるが、失敗時に何を返すのかという
問題が案Aと同じ形で再発する。さらにwrapperは**generate()の失敗しか包めず、
upload()の失敗を扱えない**。ROADMAPのDI-1定義は「画像生成・**Upload**失敗時」であり、
案Bは要求範囲の半分しか満たさない。加えて、差し替え可能なgenerator抽象を前提とする
点でDI-2を先取りする。

**案C（Orchestrator改修）を採用しない理由**
`apply()` が失敗時に「featured_media_idが未設定のままのArticleData」を返すと、
呼び出し側から成功と区別できず**silent failure**になる（G-2違反）。区別可能にするには
戻り値型を変更する必要があり、それはDI-3「Article Featured Media Orchestration v2」
そのものである。またv6.14のE2E（34シナリオ・217アサーション）が「try/exceptを持たない」
「無変換伝播する」ことを明示的に検証しているため、改修は大規模な回帰を伴う。

**案D（Composition Root／Runtime層）を採用しない理由**
v6.18設計書9章がComposition Rootの責務を6点に限定し、「失敗時の継続／中止判断
（Fallback Policy）」をN-5として明示的に除外している。DI-1側からこれを覆すのは、
承認済みReleaseのContractを設計書の外で変更することになる。将来のRuntime Wiring層で
判断する案は、DI-4未着手の現時点では実装場所が存在せず、G-6と両立しない。

### 8.4（Amendment 1新設、M-2対応）実装時期の比較

Architecture Review 1 Finding M-2は、8.1〜8.3が「責務を**どこ**に置くか」だけを比較し、
「**いつ**実装するか」を比較していないことを指摘した。本節で5案を比較する。

#### 8.4.1 候補

| 案 | 内容 |
|---|---|
| **案1** | Public policy contract（`__all__`公開）を本Releaseで先行実装する |
| **案2** | internal contract（`_`始まりの非公開module）として先行実装し、DI-4で公開する |
| **案3** | Failure Category ／ Decision model（データ型）だけ先行実装し、判定関数はDI-4へ |
| **案4** | Architecture（本設計書）のみ確定し、Production CodeはすべてDI-4へDeferredする |
| **案5** | DI-4 Runtime Wiringと同一Releaseで同時実装する |

#### 8.4.2 比較表

| 観点 | 案1: Public先行 | 案2: internal先行 | 案3: modelのみ | 案4: 設計のみ | 案5: DI-4同時 |
|---|---|---|---|---|---|
| consumer不在の価値 | ○ Failure TaxonomyがE2Eで実行可能な形に固定される | △ 公開されないため他Releaseから参照できない | △ 判定規則が固定されない | △ 文書のみ。実行可能な保証がない | ✗ 本Releaseが成立しない |
| Public API早期固定リスク | △ 4 symbolを消費者不在で固定 | ○ 内部のため変更自由 | ○ 小さい | ◎ ゼロ | ◎ 消費者と同時に決まる |
| Foundation Release既存precedent | ◎ **v6.9〜v6.18の10 Release連続で同一方式** | ✗ 前例なし（既存Foundationはすべて`__all__`公開） | ✗ 前例なし | △ **v2.1.0「Agent Documentation Foundation」（ROADMAP:225、完了済み）が唯一の前例** | ✗ Foundation Firstに反する |
| DI-4の複雑さ削減 | ◎ DI-4は捕捉と再送出のみに集中できる | ○ 同左 | △ 判定規則の設計がDI-4へ残る | ✗ 判定規則の実装・E2E設計がすべてDI-4へ集中 | ✗ 1 Releaseに全部入る |
| testability | ◎ 外部接続ゼロで9 reason × 全分岐を網羅検証できる | ○ 同左（ただしtestが内部実装へ依存） | △ 判定がないため分岐検証ができない | ✗ 実行可能な検証手段がない | △ Runtime込みの検証となり複雑 |
| Runtime Zero Diff | ◎ 既存Production Code変更0件 | ◎ 同左 | ◎ 同左 | ◎ 変更ファイル0件 | ✗ main.py変更を含む |
| 将来の互換性負担 | △ 未使用Public APIの互換性維持義務が発生 | ○ 小さい | ○ 小さい | ◎ なし | ◎ なし |

#### 8.4.3 結論（Amendment 1で確定）

**案1（Public policy contractを先行実装）を維持する。**

Repository根拠:

```text
J-1  Foundation First precedentの一貫性
     v6.9〜v6.18の10 Releaseはすべて「__all__を公開するConsumer-less package ＋
     専用E2E」という同一方式で完了している。案2・案3はこのRepositoryに前例がなく、
     案4は v2.1.0（Agent Documentation Foundation）という1件の前例しか持たない。
     しかも v2.1.0 は「既に実装済みのAgent群へ設計書を後追いで整備した」Releaseであり、
     「未実装の判断規則を文書だけで確定する」本件とは性質が異なる。

J-2  実行可能な guard が silent failure 防止の唯一の手段である
     2.2節が挙げた最大の危険は「DI-4が except Exception: pass を書くこと」である。
     案4（文書のみ）はこれを文章でしか禁止できない。案1は E2E（21章）により
     「AUTHENTICATION は継続してはならない」「WordPress Upload失敗は継続してはならない」
     を実行可能な形で固定する。v6.14／v6.18が AST Guard・静的参照Guardで Contract を
     機械検証してきた precedent と同じ思想である。

J-3  （Amendment 2、m-B対応で全面的に限定）Public API早期固定リスクは
     ゼロではない。初版Amendment 1は「将来の変更は加算的方向に限られる」と
     断定していたが、Architecture Review 2 はこれを過大主張と判定した。
     正確には次のとおりである。

       ・**主たる変更方向**は、DI-10（WordPress reason分類）・DI-11（v6.11 reason
         細分化）・第2 Adapterの追加によって「安全に分類可能となった失敗を
         新たに CONTINUE へ追加する」という加算的（additive）方向である
       ・**ただし逆方向の変更も起こりうる**。分類精度の再評価やSecurity原則の
         見直しにより、既存の CONTINUE 判定を PROPAGATE へ移すことがある。
         **Architecture Review 2 の Finding M2-1 自身がその実例である**
         （REQUEST_REJECTED を CONTINUE から PROPAGATE へ変更した）
       ・したがって Public API 早期固定リスクはゼロではなく、
         本Releaseは「Enum値の意味が変わらず、写像のみが変わる」形で
         変更を吸収できる構造を保つことでリスクを緩和するに留まる

     この限定を踏まえ、**先行実装案（案1）の主要根拠は J-1・J-2・J-4 とする**。
     J-3 は補助的な観測であり、単独では案1を支持する根拠にならない。

J-4  DI-4の審査単位を小さく保てる
     CLAUDE.md「小さく作成 → 動作確認 → 改善」に従い、DI-4を
     「捕捉と再送出の配線」だけに絞れる。案5はmain.py変更・記事ループ変更・
     判断規則設計・E2Eを1 Releaseへ同居させ、blast radiusを最大化する。

案1の唯一の弱点（未使用Public APIの互換性負担）は、J-3により影響が限定される。
また 20章のとおり、DI-4着手前に DI-10 の再検討を必須としているため、
本Releaseの Contract は DI-4 の前に一度見直される機会が制度的に確保されている。
```

---

## 9. Selected Architecture

### 9.1 第一推奨

**案E（責務配置）＋案1（実装時期）：独立したConsumer-less policy componentを
本Releaseで先行実装する。**

```text
新規package（候補）: src/image_generation_fallback_policy/
```

命名根拠：ROADMAPの正式名称「Image Generation Fallback Policy」と一致させる。
既存packageの命名規則（`image_generation_config` / `generated_image_filename_policy` /
`article_image_prompt_construction`）と同型のsnake_caseである。名称と実対象範囲の
差は5.1節で明示する。

### 9.2 責任境界（Amendment 1で m-3・M-1 対応済み）

```text
本packageが行うこと（R-1〜R-4）
  R-1  受け取った例外objectを、型（isinstance）と、v6.11が公開する安全な分類ラベル
       （OpenAIImageGenerationErrorReason）のみに基づいて Failure Category へ分類する
  R-2  Failure Category から Fallback Action（継続／元例外の伝播）を導出可能にする
  R-3  Categoryを保持するimmutableなDecision objectを返す
  R-4  分類できない例外に対して、常に安全側（元例外の伝播）の既定値を返す

本packageが行わないこと（R-5〜R-14）
  R-5  例外の捕捉（try／except を1つも書かない）
  R-6  例外の再送出・wrap・chaining（**再送出の主体は呼び出し側である**）
  R-7  例外message・provider応答・prompt・image bytesの読み取りおよび保持
  R-8  外部I/O・環境変数読み取り・log出力
  R-9  generator／uploader／orchestrator／configの参照または構築
  R-10 記事データ（ArticleData）の参照または変更
  R-11 retry・backoff・sleep
  R-12 状態の保持（stateless）
  R-13 **記事ループ全体の停止可否の決定（Amendment 1追加、M-1対応）**
  R-14 **DI-4が採用すべきtry範囲の規定（Amendment 1追加、m-2対応）**
```

**R-1の「型のみ／安全ラベルのみ」という制約は、v6.11 `_classify_api_error()` の
設計方針（「Providerメッセージ・response body・status codeの生値・prompt断片は
一切読み取らない。分類は例外の型（isinstance）のみに基づく」）をそのまま継承したもの
である。**

### 9.3 Dependency Direction

```text
許可（module-level import）:
    openai_image_generation.{OpenAIImageGenerationError, OpenAIImageGenerationErrorReason}
    wordpress_media.WordPressMediaUploadError
    標準ライブラリ: dataclasses, enum

禁止:
    openai（直接import。3.7節 S-9によりインストールされていない）
    requests / urllib / socket / os / logging
    ai_image_generation / generated_image_wordpress_media / article_featured_media /
    article_featured_media_orchestration / article_featured_media_composition /
    image_generation_config / generated_image_filename_policy /
    article_image_prompt_construction
    outputs / main / image_resolver / pipeline / ai / scheduler / workflow_engine /
    retry_* / logger / analytics / scripts

逆依存禁止:
    上記いずれのpackageも image_generation_fallback_policy をimportしない
```

```text
Dependency Diagram（Release 6.19.0候補）

openai_image_generation                wordpress_media
  ├── OpenAIImageGenerationError         └── WordPressMediaUploadError
  └── OpenAIImageGenerationErrorReason              │
              │                                     │
              └──────────────┬──────────────────────┘
                             ▼
              image_generation_fallback_policy
              ├── ImageGenerationFailureCategory（Enum、5値）
              ├── ImageGenerationFallbackAction（Enum、2値）
              ├── ImageGenerationFallbackDecision（frozen dataclass、保存field 1件）
              └── decide_image_generation_fallback()（pure function）
```

**重要な検証事項（3.7節 S-9・S-10に基づく）**：`openai_image_generation` をmodule-level
でimportしても `openai` はimportされない（v6.11の遅延import設計による）。
`wordpress_media` のimportは `requests` を巻き込むが、`requests` はインストール済みかつ
既存の必須依存である。したがって本packageのimportは外部接続を発生させない。
**この性質はE2Eで決定的に検証する（21.3節）。**

### 9.4 provider結合度の正確な限定（Amendment 1で全面改訂：m-3対応）

Architecture Review 1 Finding m-3は、「provider非依存」という無限定の表現が
9.4節の限定と整合しないことを指摘した。本設計が主張する性質を次のとおり限定する。

```text
本設計は「provider非依存（provider-independent）」ではない。
正確には「provider中立な分類語彙を公開し、実装は既存adapterの例外型を認識する」
（provider-neutral vocabulary with adapter-aware classification）である。

保証する範囲:
    V-1  公開する語彙（ImageGenerationFailureCategory / ImageGenerationFallbackAction）に
         provider名・provider固有のエラーコード・HTTPステータスを含めない
    V-2  Decision objectがprovider固有情報を保持しない
    V-3  呼び出し側がproviderを意識せずに決定を解釈できる
    V-4  分類にProvider SDKの型（openai.*）を用いない。Repository内の型のみを用いる

保証しない範囲（＝結合が残る箇所）:
    W-1  実装は OpenAIImageGenerationError / WordPressMediaUploadError という
         具体的なadapter例外型を module-level でimportし、isinstance判定に用いる
    W-2  OpenAIImageGenerationErrorReason という v6.11 固有の分類Enumの値を読む
    W-3  第2の画像生成Adapterが追加された場合、本packageに isinstance 分岐を
         1件追加する必要がある（22章 R-3）
    W-4  v6.11 が reason Enum へ値を追加した場合、本packageの写像更新が必要
         （22章 R-6。AC-13の網羅検証で検知する）
```

型に依存しない代替（例外messageの解析・duck typing）は、v6.11がmessageを固定文字列と
定めた設計を無意味化し、かつ 3.4節で確認した `WordPressMediaUploadError` の
message可変性により脆弱になるため採用しない（Architecture Review 1でもmessage解析は
明示的に禁止された）。

### 9.5（Amendment 1新設、S-1対応）生Exceptionの正規化責任層

Architecture Review 1 Suggestion S-1は、「Repositoryの既存分類器はすべて正規化済みの
値を入力とし、生の例外objectを受け取る分類器は1件も存在しない」ことを指摘した。
本節で正規化責任の所在を明示する。

```text
既存precedentの入力型:
    RetryPolicy.should_retry(monitor_status: WorkflowMonitorStatus, attempt: int)
        → 正規化済みEnum
    classify_reason(update_decision: RetryQueueUpdateDecision)
        → 正規化済みDecision object
    classify_terminality(reason: RetryCleanupReason)
        → 正規化済みEnum
    RetryHealthEvaluator / RetryAlertEvaluator / RetryNotificationEvaluator
        → いずれも正規化済みの Snapshot / Report / Alert object

本設計が生Exceptionを入力とする理由:
    ・DI-1の時点で「例外 → 正規化済みFailure Category」への変換を担う層が
      Repositoryに存在しない。その変換こそが本packageの中核責務である
    ・変換を呼び出し側（DI-4）へ委ねると、DI-4が isinstance 判定と reason 解釈を
      自前で書くことになり、DI-1の存在意義（判断規則の一元化）が失われる
    ・v6.11 の _classify_api_error() は「provider例外 → 安全なreasonラベル」という
      第1段の正規化を既に担っている。本packageはその出力を入力として受け取り、
      「adapter例外 → provider中立なCategory」という第2段の正規化を担う

正規化の2段構成（Amendment 1で確定）:
    第1段  provider例外（openai.*）→ OpenAIImageGenerationError(reason)
           担当: v6.11 openai_image_generation（既存・無改修）
    第2段  adapter例外 → ImageGenerationFailureCategory
           担当: **本package（Release 6.19.0候補）**
    第3段  Category → 実際の制御（記事継続／再送出／記録）
           担当: DI-4 Runtime Wiring（未着手）

したがって本packageは「既存precedentから逸脱して生Exceptionを受け取る」のではなく、
「Repositoryに欠けていた第2段の正規化層そのもの」である。この位置づけを
Public API docstringにも記載する。
```

---

## 10. Failure Taxonomy と Decision Table

### 10.1 分類の前提

```text
・本表の「DI-1で扱うか」は、decide_image_generation_fallback() が
  当該例外を受け取りうるか、という意味である
・Construction Failure（from_env()／constructor由来）は、そもそも apply() 実行前に
  発生するため、本policyへ渡らない（S-6）。表では「対象外（構築時）」と記す
・「元例外の扱い」列は、DI-4 Runtime Wiring側が負う義務を示す。
  **本packageは例外を捕捉も再送出もしない**（9.2節 R-5・R-6）
・Action は Category から一意に導出される（11.4節）。本表のAction列は
  その導出結果を参考表示したものである
```

### 10.2 Decision Table（Amendment 1で全面更新）

| # | 事象 | 発生層 | 想定例外 | Category | Action（導出値） | 判断理由 | 元例外の扱い（DI-4の義務） | chaining | logging／metricsの将来責任 | DI-1で扱うか | Deferred先 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| T-1 | Gate OFF | v6.15 | なし | — | — | 失敗ではない。正常な無効状態 | — | — | DI-4がGate OFFを通常経路として扱う | **扱わない** | — |
| T-2 | 不正なGate値（`ture`等） | v6.15 | なし | — | — | Fail Closedにより`False`＝T-1と同一 | — | — | DI-9 | **扱わない** | DI-9 |
| T-3 | `OPENAI_API_KEY`未設定・空白 | v6.11 `from_env()` | `ValueError` | — | — | Construction Failure。Fail Fast維持（G-3） | 無変換伝播（v6.18 E-3） | しない | 例外tracebackで観測 | **扱わない（構築時）** | — |
| T-4 | `WP_*`未設定・空白 | v6.9 `from_env()` | `ValueError` | — | — | 同上（v6.18 E-5） | 無変換伝播 | しない | 同上 | **扱わない（構築時）** | — |
| T-5 | `OPENAI_IMAGE_TIMEOUT_SECONDS`非整数・非正 | v6.11 `from_env()` | `ValueError` | — | — | Configuration validation error | 無変換伝播 | しない | 同上 | **扱わない（構築時）** | — |
| T-6 | constructor値検証失敗（size／quality等） | v6.11／v6.9 `__init__` | `ValueError` | — | — | Construction Failure | 無変換伝播 | しない | 同上 | **扱わない（構築時）** | — |
| T-7 | v6.18 `__post_init__` 不変条件違反 | v6.18 | `ValueError`／`TypeError` | — | — | Construction Failure | 送出（v6.18 E-11〜E-13） | しない | 同上 | **扱わない（構築時）** | — |
| T-8 | `openai` package未インストール | v6.11 `generate()` 冒頭の`import openai`（try範囲外） | `ModuleNotFoundError` | `UNCLASSIFIED` | `PROPAGATE_ORIGINAL_ERROR` | **環境構築の欠陥。継続すると全記事が無音で劣化する。**（Amendment 1、m-1対応：汎用`ImportError`への専用Category分類は行わず`UNCLASSIFIED`へ統合） | 無変換で再送出 | しない | DI-5 | **扱う** | — |
| T-9 | OpenAI client構築失敗（injected clientが`with_options`欠如） | v6.11 `_get_client()` | `TypeError` | `UNCLASSIFIED` | `PROPAGATE_ORIGINAL_ERROR` | Programming error（注入誤り） | 同上 | しない | DI-5 | **扱う** | — |
| T-10 | timeout | provider | `OpenAIImageGenerationError(TIMEOUT)` | `IMAGE_GENERATION_FAILED` | `CONTINUE_WITHOUT_FEATURED_MEDIA` | 一過性。記事固有でなく再実行で解消しうる | 破棄可（継続） | しない | DI-5（category のみ） | **扱う** | — |
| T-11 | network failure | provider | `OpenAIImageGenerationError(CONNECTION)` | `IMAGE_GENERATION_FAILED` | `CONTINUE_WITHOUT_FEATURED_MEDIA` | 同上 | 同上 | しない | DI-5 | **扱う** | — |
| T-12 | rate limit | provider | `OpenAIImageGenerationError(RATE_LIMIT)` | `IMAGE_GENERATION_FAILED` | `CONTINUE_WITHOUT_FEATURED_MEDIA` | 同上 | 同上 | しない | DI-5 | **扱う** | — |
| T-13 | provider authentication failure | provider | `OpenAIImageGenerationError(AUTHENTICATION)` | **`IMAGE_GENERATION_NOT_AUTHORIZED`** | **`PROPAGATE_ORIGINAL_ERROR`** | **credential誤りが実行時に現れたもの。継続させるとG-3に違反する**（10.5節） | 無変換で再送出 | しない | DI-5（最優先の通知対象） | **扱う** | — |
| T-14 | provider permission failure | provider | `OpenAIImageGenerationError(PERMISSION_DENIED)` | **`IMAGE_GENERATION_NOT_AUTHORIZED`** | **`PROPAGATE_ORIGINAL_ERROR`** | 同上（Organization Verification未了等、アカウント設定の問題） | 同上 | しない | DI-5 | **扱う** | — |
| T-15 | provider invalid request（HTTP 400／404／409／422） | provider | `OpenAIImageGenerationError(REQUEST_REJECTED)` | **`IMAGE_GENERATION_REQUEST_REJECTED`** | **`PROPAGATE_ORIGINAL_ERROR`** | **（Amendment 2、M2-1対応）v6.11 が `BadRequestError`／`NotFoundError`／`ConflictError`／`UnprocessableEntityError` を単一 reason へ集約するため、記事固有の失敗（Content Policy拒否）と全記事へ反復するsystemic failure（model不存在・model提供終了）を安全に区別できない。分類不能な失敗をfallbackへ倒さない（G-9）安全側原則を適用する（10.6節）** | 無変換で再送出 | しない | DI-5 | **扱う** | **DI-11（reason細分化）** |
| T-16 | content policy rejection | provider | `OpenAIImageGenerationError(REQUEST_REJECTED)`（v6.11が同一分類へ集約） | **`IMAGE_GENERATION_REQUEST_REJECTED`** | **`PROPAGATE_ORIGINAL_ERROR`** | 同上。**記事固有の失敗であるため本来は継続可能だが、T-15と区別できないため安全側へ倒す。この可用性トレードオフは10.6節 C-10で明示的に受諾する** | 同上 | しない | DI-5 | **扱う**（T-15と区別不能。22章 R-4） | **DI-11** |
| T-17 | provider server error | provider | `OpenAIImageGenerationError(SERVER_ERROR)` | `IMAGE_GENERATION_FAILED` | `CONTINUE_WITHOUT_FEATURED_MEDIA` | 一過性 | 同上 | しない | DI-5 | **扱う** | — |
| T-18 | 空レスポンス／構造不正 | v6.11 `_validate_response_structure()` | `OpenAIImageGenerationError(INVALID_RESPONSE)` | **`UNCLASSIFIED`** | **`PROPAGATE_ORIGINAL_ERROR`** | **（Amendment 3、m3-A対応）単発の不正応答（切断・破損）だけでなく、provider または SDK の応答構造変更による systemic failure が同一reasonへ混入する。一過性であることを保証できないため安全側へ倒す（10.7節）** | 無変換で再送出 | しない | DI-5 | **扱う** | DI-11候補 |
| T-19 | base64 decode失敗 | v6.11 `_build_generated_image()` | `OpenAIImageGenerationError(INVALID_RESPONSE)` | **`UNCLASSIFIED`** | **`PROPAGATE_ORIGINAL_ERROR`** | 同上 | 同上 | しない | DI-5 | **扱う** | DI-11候補 |
| T-20 | **APIError未分類（`_classify_api_error`のcatch-all）＋ `except Exception` 経路の全例外** | v6.11 `generate()` | `OpenAIImageGenerationError(UNKNOWN)` | **`UNCLASSIFIED`** | **`PROPAGATE_ORIGINAL_ERROR`** | **（Amendment 3、M3-1対応）`UNKNOWN` は単一の意味を持たない。v6.11 `generate()` は `except openai.APIError` の後段に `except Exception:` を持ち、`TypeError`（SDK signature変更）・`AttributeError`・`ValidationError`・SDK内部のprogramming error をすべて `UNKNOWN` へ落とす。したがって「provider通信の失敗」とは限らず、一過性障害と積極的に判定できない（10.7節）。Amendment 2以前の根拠「v6.11が既にprovider通信の失敗として分類済み」は誤りであり訂正した** | 同上 | しない | DI-5 | **扱う** | DI-11候補 |
| T-21 | `image_bytes`型不正・空 | v6.10 `GeneratedImage.__post_init__` | `ValueError` | `UNCLASSIFIED` | `PROPAGATE_ORIGINAL_ERROR` | Invariant violation。**v6.11経由では構造上到達不能**（decodedは非空検証済み、mime_typeは固定写像由来） | 無変換で再送出 | しない | DI-5 | **扱う** | — |
| T-22 | output format／MIME不整合 | v6.10／v6.11 | `ValueError` | `UNCLASSIFIED` | `PROPAGATE_ORIGINAL_ERROR` | 同上。v6.11の`_MIME_TYPE_BY_OUTPUT_FORMAT`がSSOTのため到達不能 | 同上 | しない | DI-5 | **扱う** | — |
| T-23 | prompt construction失敗 | v6.17 | `ValueError` | `UNCLASSIFIED` | `PROPAGATE_ORIGINAL_ERROR` | Programming error。**（Amendment 1、m-2対応）`apply()` 呼び出し前に発生するため、16.2節の推奨利用例ではtry範囲外＝policyへ到達しない。DI-4がtry範囲を広げた場合にのみ到達する条件付き分類である** | 同上 | しない | DI-5 | **条件付き（DI-4のtry範囲に依存）** | — |
| T-24 | filename policy失敗 | v6.16 | `ValueError` | `UNCLASSIFIED` | `PROPAGATE_ORIGINAL_ERROR` | 同上（条件付き） | 同上 | しない | DI-5 | **条件付き（DI-4のtry範囲に依存）** | — |
| T-25 | prompt validation失敗（v6.11内） | v6.11 `_validate_prompt()` | `ValueError` | `UNCLASSIFIED` | `PROPAGATE_ORIGINAL_ERROR` | Programming error（呼び出し側が不正promptを渡した） | 同上 | しない | DI-5 | **扱う** | — |
| T-26 | **WordPress upload失敗（認証401・権限403・一過性429/500・network・応答不正のすべて）** | v6.9 `upload()` | `WordPressMediaUploadError` | **`MEDIA_UPLOAD_FAILED`** | **`PROPAGATE_ORIGINAL_ERROR`** | **（Amendment 1、B-1対応）reason分類Enumが存在せず、認証・権限（configuration error）と一過性障害を安全に区別できない。message解析は禁止。したがって全件を安全側＝元例外の伝播とする（10.4節）** | 無変換で再送出 | しない | DI-5 | **扱う** | **DI-10（分類精度の向上）** |
| T-27 | v6.12 Wiring層の型検証失敗 | v6.12 `upload()` | `ValueError`／`TypeError` | `UNCLASSIFIED` | `PROPAGATE_ORIGINAL_ERROR` | Programming error | 同上 | しない | DI-5 | **扱う** | — |
| T-28 | media binding失敗 | v6.13 `bind_featured_media()` | `ValueError` | `UNCLASSIFIED` | `PROPAGATE_ORIGINAL_ERROR` | Invariant violation（media_idが正の整数でない等） | 同上 | しない | DI-5 | **扱う** | — |
| T-29 | v6.14 `apply()` 引数validation失敗 | v6.14 | `ValueError` | `UNCLASSIFIED` | `PROPAGATE_ORIGINAL_ERROR` | Programming error | 同上 | しない | DI-5 | **扱う** | — |
| T-30 | v6.14 constructor capability不足 | v6.14 `__init__` | `TypeError` | — | — | Construction Failure | 無変換伝播（v6.18 E-9） | しない | — | **扱わない（構築時）** | — |
| T-31 | その他のprogramming error（`AttributeError`／`KeyError`等） | 任意 | `Exception`のsubclass | `UNCLASSIFIED` | `PROPAGATE_ORIGINAL_ERROR` | 未知の例外を継続扱いにすると silent failure を量産する（G-2・G-9） | 同上 | しない | DI-5 | **扱う（既定値）** | — |
| T-32 | `MemoryError`／`RecursionError` | 任意 | `Exception`のsubclass | `UNCLASSIFIED` | `PROPAGATE_ORIGINAL_ERROR` | 同上。プロセス全体の健全性に関わる | 同上 | しない | DI-5 | **扱う** | — |
| T-33 | `KeyboardInterrupt` | 任意 | `BaseException`直系 | — | — | **`Exception`のsubclassではない**。DI-4の捕捉は`except Exception`に限定するContractとし、本policyへは到達させない | 伝播（握りつぶさない） | しない | — | **扱わない（BaseException）** | — |
| T-34 | `SystemExit` | 任意 | `BaseException`直系 | — | — | 同上 | 伝播 | しない | — | **扱わない（BaseException）** | — |
| T-35 | `GeneratorExit`その他`BaseException`系 | 任意 | `BaseException`直系 | — | — | 同上 | 伝播 | しない | — | **扱わない（BaseException）** | — |

### 10.3 Decision Tableの要約（Amendment 1で更新）

```text
CONTINUE_WITHOUT_FEATURED_MEDIA となるのは、次の2条件をともに満たす場合**に限る**:
  (a) 例外が OpenAIImageGenerationError である
  (b) その reason が次の**4値のいずれか**である（allow-list）
        TIMEOUT / CONNECTION / RATE_LIMIT / SERVER_ERROR

上記以外はすべて PROPAGATE_ORIGINAL_ERROR（安全側の既定）。これには次を含む。
  ・AUTHENTICATION / PERMISSION_DENIED（T-13・T-14）
  ・REQUEST_REJECTED（T-15・T-16）                    ← Amendment 2、M2-1対応
  ・**INVALID_RESPONSE（T-18・T-19）**                ← Amendment 3、m3-A対応
  ・**UNKNOWN（T-20）**                              ← Amendment 3、M3-1対応
  ・WordPress Media Upload失敗（T-26）の**全件**
  ・未知reason・未知例外（UNCLASSIFIED）
```

**分類方式の転換（Amendment 3、M3-1対応）**

```text
Amendment 2まで: deny-list 方式
    「AUTHENTICATION・PERMISSION_DENIED・REQUEST_REJECTED 以外は CONTINUE」
    → v6.11 が reason を追加した場合、新しい値が**自動的に CONTINUE 側へ落ちる**。
      安全側の既定を持たない構造だった。

Amendment 3以降: allow-list 方式
    「TIMEOUT・CONNECTION・RATE_LIMIT・SERVER_ERROR のみ CONTINUE、
      それ以外はすべて PROPAGATE」
    → v6.11 が reason を追加しても、新しい値は**自動的に安全側（PROPAGATE）へ落ちる**。
      未知reason・未知例外に対する既定（13.4節）と同一の帰結になり、
      Error Contract 全体が「積極的に安全と判定できたものだけを継続する」
      という単一の構造になる。
```

**CONTINUE となる4 reason に共通する性質**（Amendment 3で正確化）

```text
TIMEOUT / CONNECTION / RATE_LIMIT / SERVER_ERROR は、
・記事の内容に起因しない
・設定・credential・permission・model指定の誤りに起因しない
・provider側またはネットワーク側の負荷・可用性に起因する
・同じ入力で再実行すれば成功しうる
という性質を持つ。

**ただし「必ず一過性である」とは主張しない。**
これらは「現行の分類粒度（v6.11 `_classify_api_error()` が
openai.APITimeoutError / APIConnectionError / RateLimitError /
InternalServerError を個別に判定していること）において、
一過性と**積極的に判断する対象**」である。
v6.11 の分類が変化した場合、あるいは運用上これらにも systemic failure が
混入することが判明した場合は、本判断の見直しを要する（22章 R-7）。
```

**Amendment 1／Amendment 2前後の差分**

```text
【Amendment 1】
変更前: WordPress Upload失敗（T-26）→ CONTINUE_WITHOUT_IMAGE
変更後: WordPress Upload失敗（T-26）→ PROPAGATE_ORIGINAL_ERROR

変更前: T-8 → ENVIRONMENT_ERROR（専用Category）
変更後: T-8 → UNCLASSIFIED（統合）

変更前: Action 名 CONTINUE_WITHOUT_IMAGE / ABORT_ARTICLE
変更後: Action 名 CONTINUE_WITHOUT_FEATURED_MEDIA / PROPAGATE_ORIGINAL_ERROR

【Amendment 2】
変更前: REQUEST_REJECTED（T-15・T-16）
          → IMAGE_GENERATION_FAILED ＋ CONTINUE_WITHOUT_FEATURED_MEDIA
変更後: REQUEST_REJECTED（T-15・T-16）
          → IMAGE_GENERATION_REQUEST_REJECTED ＋ PROPAGATE_ORIGINAL_ERROR

変更前: Failure Category 4値
変更後: Failure Category 5値（IMAGE_GENERATION_REQUEST_REJECTED を新設）

【Amendment 3】
変更前: INVALID_RESPONSE（T-18・T-19）
          → IMAGE_GENERATION_FAILED ＋ CONTINUE_WITHOUT_FEATURED_MEDIA
変更後: INVALID_RESPONSE（T-18・T-19）
          → UNCLASSIFIED ＋ PROPAGATE_ORIGINAL_ERROR

変更前: UNKNOWN（T-20）
          → IMAGE_GENERATION_FAILED ＋ CONTINUE_WITHOUT_FEATURED_MEDIA
変更後: UNKNOWN（T-20）
          → UNCLASSIFIED ＋ PROPAGATE_ORIGINAL_ERROR

変更前: CONTINUE 対象 reason 6値（deny-list 方式）
変更後: CONTINUE 対象 reason **4値**（allow-list 方式）

Failure Category は5値のまま（新設・削除なし）
```

### 10.4（Amendment 1で全面改訂、B-1対応）WordPress Media Upload失敗の最終契約

Architecture Review 1 Finding B-1は、`WordPressMediaUploadError` の分類不能性を
Blockingと判定した。本節でその最終契約を確定する。

#### 10.4.1 問題の正確な記述

```text
Repository事実（3.4節 S-5）:
    WordPressMediaUploader.upload() は次のすべてを WordPressMediaUploadError 1種へ集約する。
      ・requests.RequestException（network・DNS・timeout）
      ・HTTP 401（認証失敗＝credential誤り）
      ・HTTP 403（権限不足＝Application Passwordのcapability不足）
      ・HTTP 429（rate limit）
      ・HTTP 4xx その他（payload過大等）
      ・HTTP 5xx（provider側障害）
      ・成功レスポンスのJSON不正・id/source_url/mime_type欠落
    reason属性は存在しない。分類可能な構造化情報は message 文字列のみであり、
    message解析はArchitecture Review 1で明示的に禁止された。
```

#### 10.4.2 Architecture Review 1が示した反証（Amendment 1で受諾）

Architecture Design初版は「`WordPressMediaUploader` と `WordPressOutput` が同一の
環境変数（`WP_SITE_URL`／`WP_USERNAME`／`WP_APP_PASSWORD`）を共有するため、WP credential
誤りは記事投稿自体も失敗させ、完全な無音にはならない」ことを緩和策としていた。

**Architecture Review 1はこの推論が不完全であると指摘した。**

```text
反証（受諾）:
    WordPress Application Password は capability 単位で権限を持つ。
    edit_posts（記事作成）を持ち upload_files（メディアアップロード）を持たない
    構成では、次が同時に成立する。
      ・WordPressOutput.save() は成功する（記事は正常に投稿される）
      ・WordPressMediaUploader.upload() は HTTP 403 を返し続ける
    この経路では「記事投稿の失敗」という可視シグナルが一切発生しない。
    初版の設計（全件CONTINUE）では、画像が恒久的に欠落したまま
    運用者が気づけない permanent silent degradation が成立する。
    これは本設計のG-3・G-9に正面から反する。
```

#### 10.4.3 検討した3案

| 案 | 内容 | 評価 |
|---|---|---|
| (i) | v6.9へ `WordPressMediaUploadErrorReason` を純追加し、statusコードで分類する | 分類精度は最良。ただし**v6.9のPublic API変更を伴い、本Releaseのscopeを大きく拡大**する。v6.9は既にRelease完了済みでE2E（987行）を持ち、変更にはv6.9 E2Eの再検証が必要 |
| (ii) | Upload失敗をDI-1の対象から除外する | ROADMAPのDI-1定義「画像生成・**Upload**失敗時」に反する。またDI-4が独自判断を書くことになり、DI-1の存在意義が損なわれる |
| (iii) | **Upload失敗を全件 `PROPAGATE_ORIGINAL_ERROR` とする** | **採用。** 分類不能な領域を安全側へ倒す。silent degradationが構造的に発生しない |

#### 10.4.4 採用する契約（Amendment 1で確定）

```text
C-1  WordPressMediaUploadError は例外の型のみで MEDIA_UPLOAD_FAILED へ分類する。
     message文字列の解析・HTTPステータスの推測・reason属性の探索は一切行わない。

C-2  MEDIA_UPLOAD_FAILED から導出されるActionは常に PROPAGATE_ORIGINAL_ERROR である。
     すなわち **WordPress Media Upload失敗では画像なし継続（fallback）を行わない。**

C-3  呼び出し側（DI-4）は、捕捉した WordPressMediaUploadError を無変換で再送出する。
     再送出された例外がどの層で受け止められるか（記事単位か run 単位か）は
     DI-4および既存Runtime境界（S-12〜S-14）の責任である。

C-4  Upload失敗の分類精度向上は Deferred Item DI-10 として独立させる（20章）。
     **（Amendment 3、M3-2対応で一義化）DI-4 Runtime Wiring着手前に、
     DI-10の必要性とC-5の可用性トレードオフを正式に**再評価すること**は必須である。
     ただし再評価の結果C-5をそのまま受容する場合、DI-10が未完了でもDI-4へ進めてよい。
     WordPress Upload失敗をCONTINUEへ拡大したい場合、または一過性WP障害による
     可用性低下を受容できないと判断した場合に限り、DI-10の**完了**がDI-4着手の
     前提となる。詳細な判定規則は10.8節 ORD-1〜ORD-4を参照する。
     「再検討必須」と「完了必須」を混同しない。**

C-5  本契約が受け入れるトレードオフを明示する:
     一過性のWordPress障害（HTTP 500・network断・429）でも元例外が伝播するため、
     その記事のfeatured media処理は継続されない。S-12〜S-14により
     「記事1件の失敗はrun全体を停止させない」ことは確認済みであるが、
     一過性障害が続く間は該当記事群が影響を受ける。
     本Releaseは「configuration errorを隠さないこと」（G-3・G-9）を
     可用性より優先する。この優先順位はDI-10により将来見直しうる（22章 R-1）。
```

### 10.5 T-13／T-14（認証・権限）をfallback対象外とする判断の根拠

```text
根拠1  「credential不足を正常なunavailable扱いに変換しない」
       「configuration errorをfallbackで隠さない」（G-3）に直接該当する。
       AUTHENTICATION は「credentialは存在するが誤っている」状態であり、
       未設定（T-3、Fail Fast）と本質的に同じ configuration error である。
       未設定だけをFail Fastにし、誤設定を無音の劣化にするのは非対称である

根拠2  v6.18が確立したFail Fast思想（設計書13.3節）の runtime side への一貫した延長

根拠3  reason の読み取りは v6.11 の Public API（OpenAIImageGenerationErrorReason は
       openai_image_generation.__all__ に含まれる）を使うだけであり、
       新しい抽象を導入しない。message解析・provider応答の読み取りは一切行わない

根拠4  AUTHENTICATION／PERMISSION_DENIED は記事固有ではなくアカウント全体の問題であり、
       継続すると「全記事が画像なしで投稿され続ける」という最悪の silent degradation を招く

根拠5  （Amendment 1追加／Amendment 2で精密化）B-1対応により WordPress側も
       全件 PROPAGATE となり、さらにM2-1対応により REQUEST_REJECTED も
       PROPAGATE となったため、次の原則が Error Contract 全体で成立した。

         **「configuration・credential・permission・model指定に起因する失敗、
           および安全に分類できない失敗は、providerを問わず継続しない」**

       Architecture Review 1が指摘した「OpenAI側はABORT、WordPress側はCONTINUE」
       という非対称、およびArchitecture Review 2が指摘した
       「WordPressにはG-9を適用しOpenAIのREQUEST_REJECTEDバケットには適用しない」
       という非対称は、いずれも解消済みである。

       **Amendment 2による限定（Amendment 3で更新）**：本原則が保証するのは
       「上記の失敗をCONTINUEへ倒さない」ことのみである。逆方向——CONTINUEとなる
       **4 reason**（TIMEOUT／CONNECTION／RATE_LIMIT／SERVER_ERROR、10.3節）に
       configuration起因やsystemic failureが紛れ込まないこと——は、
       v6.11の分類粒度に依存する。
       **Amendment 3で `INVALID_RESPONSE`・`UNKNOWN` を CONTINUE 側から外し、
       分類方式を allow-list へ転換したことで（10.7節・C-17）、
       この依存範囲は4 reasonまで縮小された。**
       残る依存は22章 R-7へ残存リスクとして記録しており、
       v6.11がreasonを追加・再編した場合は再評価を要する（22章 R-4・R-6・R-7）。
```

---

### 10.6（Amendment 2新設、M2-1対応）`REQUEST_REJECTED` の最終契約

#### 10.6.1 問題の正確な記述

```text
Repository事実（openai_image_generator.py:133-138、実読で確認）:
    _classify_api_error() は次の4つのProvider例外型を
    **単一の OpenAIImageGenerationErrorReason.REQUEST_REJECTED へ集約**する。

      openai.BadRequestError            HTTP 400  Content Policy拒否・パラメータ不正
      openai.NotFoundError              HTTP 404  **model不存在・model提供終了**
      openai.ConflictError              HTTP 409
      openai.UnprocessableEntityError   HTTP 422

    v6.11 は分類を例外の型のみに基づいて行い、statusコード・response body・
    Providerメッセージを一切読み取らない設計である（同関数docstring）。
    したがって呼び出し側は REQUEST_REJECTED の内訳を知る手段を持たない。

関連するRepository事実:
    _DEFAULT_MODEL = "gpt-image-2-2026-04-21"（openai_image_generator.py:19）
      → **日付固定のsnapshot model名**である。提供終了・改名は現実的に起こりうる
    model は constructor パラメータでもある（同 :201）
      → 誤った値を注入することも構造的に可能である
```

#### 10.6.2 M2-1が指摘した矛盾（Amendment 2で受諾）

```text
Amendment 1時点の設計は REQUEST_REJECTED を全件 CONTINUE としていた。
Architecture Review 2 はこれを Major と判定した。

反証（受諾）:
    model不存在（HTTP 404）は「記事固有の失敗」ではなく、
    **全記事に対して反復するsystemic failure**である。
    これを CONTINUE として扱うと、
      ・すべての記事が画像なしで投稿され続ける
      ・記事投稿自体は成功するため wp_failed_count 等の可視シグナルも出ない
    という状態が無期限に継続する。これは B-1（WordPress capability不足による
    HTTP 403）で排除した permanent silent degradation と構造的に同一であり、
    しかも WordPress のケースより検知が困難である。

    さらに、Amendment 1は WordPress 側に「安全に分類できない失敗は
    fallbackへ倒さない」（G-9）を適用しながら、同種の分類不能バケットである
    REQUEST_REJECTED には適用していなかった。この非対称に正当化はなかった。
```

#### 10.6.3 採用する契約（Amendment 2で確定）

```text
C-6   OpenAIImageGenerationErrorReason.REQUEST_REJECTED は、
      新設した Failure Category `IMAGE_GENERATION_REQUEST_REJECTED` へ分類する。

C-7   IMAGE_GENERATION_REQUEST_REJECTED から導出されるActionは
      常に PROPAGATE_ORIGINAL_ERROR である。
      すなわち **REQUEST_REJECTED では画像なし継続（fallback）を行わない。**

C-8   REQUEST_REJECTED の内訳（Content Policy拒否／model不存在／その他）を
      **本Releaseで細分化しない**。
      ・例外messageの解析を行わない
      ・provider応答本文・HTTPステータスコードの推測を行わない
      ・v6.11 の _classify_api_error() を改修しない（N-12）
      分類は「reasonがREQUEST_REJECTEDであるか」の一点のみで決定する。

C-9   v6.11 側の reason 細分化は Deferred Item **DI-11** として独立させる（20章）。
      **（Amendment 3、M3-2対応で一義化）DI-4 Runtime Wiring着手前に、
      DI-11の必要性とC-10の可用性トレードオフを正式に**再評価すること**は必須である。
      ただし再評価の結果C-10をそのまま受容する場合、DI-11が未完了でもDI-4へ進めてよい。
      Content Policy拒否等をCONTINUEへ拡大したい場合、または当該可用性低下を
      受容できないと判断した場合に限り、DI-11の**完了**がDI-4着手の前提となる。
      詳細な判定規則は10.8節 ORD-1〜ORD-4を参照する（DI-10と同じ扱いである）。**

C-10  本契約が受け入れるトレードオフを明示的に受諾する:
      **Content Policy拒否（HTTP 400）は本来「その記事固有の失敗」であり、
      他の記事は成功しうるため、本来は継続可能な失敗である。**
      しかし model不存在（HTTP 404）と区別できないため、安全側へ倒す。
      その結果、生成禁止語を含む記事が1件混ざるだけで、その記事の
      featured media処理は継続されず元例外が伝播する。
      S-12〜S-14により「記事1件の失敗はrun全体を停止させない」ことは
      確認済みであるが、該当記事は影響を受ける。
      本Releaseは「安全に分類できない失敗をfallbackへ倒さない」（G-9）を
      可用性より優先する。この優先順位はDI-11により将来見直しうる（22章 R-4）。

C-11  新Category `IMAGE_GENERATION_REQUEST_REJECTED` は、Amendment 1で削除した
      `ENVIRONMENT_ERROR` の復活ではない。
      ・ENVIRONMENT_ERROR は Action が UNCLASSIFIED と同一であったため、
        独立Categoryとして業務判断上の差がなく統合した（m-1）
      ・IMAGE_GENERATION_REQUEST_REJECTED は
        IMAGE_GENERATION_FAILED と**異なるActionを必要とする**ため独立させる
      すなわち本Categoryは「Actionの差を表現するために必要な最小の分割」である。

C-12  Category を分けることで、DI-11完了後の変更が加算的に行える。
      DI-11 が Content Policy拒否 を独立reasonへ分離した場合、
      その reason を IMAGE_GENERATION_FAILED（CONTINUE）へ移すだけでよく、
      IMAGE_GENERATION_REQUEST_REJECTED（PROPAGATE）は
      model不存在等のsystemic failure用として残せる。
```

---

### 10.7（Amendment 3新設、M3-1・m3-A対応）`UNKNOWN` と `INVALID_RESPONSE` の最終契約

#### 10.7.1 `UNKNOWN` の2つの生成経路（Repository事実）

`openai_image_generator.py` の `generate()` を実読した結果、`UNKNOWN` は
**意味の異なる2経路**から生成されることを確認した。

```python
try:
    response = client.images.generate(**self._build_kwargs(prompt))
except openai.APIError as exc:
    error_message, error_reason = _classify_api_error(exc)   # 経路1
except Exception:                                            # 経路2
    error_message = _MSG_UNEXPECTED_ERROR
    error_reason = OpenAIImageGenerationErrorReason.UNKNOWN
```

```text
経路1  _classify_api_error() の catch-all。
       openai.APIError のsubclassだが個別分岐に一致しなかったもの。
       → provider API エラーであることは確定しており、一過性と推定しうる。

経路2  **except Exception: — client.images.generate() が送出した
       APIError 以外のあらゆる例外**。
       → TypeError（_build_kwargs() が渡す output_format / background 等の
          kwarg が SDK 側の変更で不整合になった場合）
       → AttributeError（client.images の消失等、SDKの構造変更）
       → pydantic.ValidationError（応答モデル検証の失敗）
       → SDK内部の任意の programming error
       これらは **provider通信の失敗ではなく、環境・依存関係・実装の欠陥**である。

関連するRepository事実:
    requirements.txt:8  openai>=2.46.0,<3.0.0
      → **2.x系のminor upgradeを許容**する。venvには未インストールであり
        （3.7節 S-9）、実行時のSDKバージョンは固定されていない。
        2.x系の変更で kwarg が改名・削除されれば TypeError → UNKNOWN となる。
```

#### 10.7.2 M3-1が指摘した矛盾（Amendment 3で受諾）

```text
Amendment 2時点の設計は UNKNOWN を CONTINUE としていた。
Architecture Review 3 はこれを Major と判定した。

反証（受諾）:
    経路2で生じる TypeError 等は、記事1件ごとの一過性障害ではなく
    **全記事に対して反復するsystemic failure**である。
    これを CONTINUE として扱うと、
      ・すべての記事が画像なしで投稿され続ける
      ・記事投稿自体は成功するため可視シグナルが出ない
    という状態が無期限に継続する。B-1（WordPress 403）・M2-1（model不存在404）で
    排除した permanent silent degradation と構造的に同一である。

    さらに、Amendment 2までの T-20 の根拠
    「v6.11が既にprovider通信の失敗として分類済み。認証・権限でないことは確定している」
    は、経路2について**事実として誤り**であった（経路2は通信の失敗ではない）。
    本Amendmentでこの記述を訂正する。
```

#### 10.7.3 `INVALID_RESPONSE` についての同種の判断（m3-A対応）

```text
INVALID_RESPONSE は次の箇所から生成される（v6.11 実読）。
    _validate_response_structure()  data が要素1のlistでない／b64_json が非空strでない
    _build_generated_image()        base64 デコード失敗／デコード結果が空

これらは「単発の応答破損・切断」として一過性に生じうる一方、
**provider が応答スキーマを変更した場合、または SDK が応答モデルを変更した場合には
全呼び出しで発生する systemic failure** となる。
v6.11 は両者を同一 reason へ集約しており、DI-1 側で区別する手段はない
（message解析は禁止）。
したがって UNKNOWN と同じ安全側原則を適用する。
```

#### 10.7.4 採用する契約（Amendment 3で確定）

```text
C-13  OpenAIImageGenerationErrorReason.UNKNOWN は
      Failure Category `UNCLASSIFIED` へ分類する。**新Categoryは追加しない。**

C-14  OpenAIImageGenerationErrorReason.INVALID_RESPONSE も
      Failure Category `UNCLASSIFIED` へ分類する。

C-15  UNCLASSIFIED から導出されるActionは常に PROPAGATE_ORIGINAL_ERROR である。
      すなわち **UNKNOWN・INVALID_RESPONSE では画像なし継続を行わない。**

C-16  `UNCLASSIFIED` の意味を次のとおり確定する。
      「本policyが**安全に分類できなかった失敗**」。
      内訳は次の3系統であり、いずれも同一のActionを要求する。
        (a) 本policyが認識する2つのadapter例外型のいずれでもない例外
            （programming error・invariant violation・環境エラー等。T-8・T-9・T-21〜T-32）
        (b) OpenAIImageGenerationError であるが reason が
            安全に分類できない値である場合（INVALID_RESPONSE・UNKNOWN）
        (c) OpenAIImageGenerationError であるが reason が
            OpenAIImageGenerationErrorReason のmemberでない場合（13.4節、防御的）

C-17  分類方式を deny-list から **allow-list** へ転換する（10.3節）。
      CONTINUE となるのは TIMEOUT / CONNECTION / RATE_LIMIT / SERVER_ERROR の
      4 reason のみであり、それ以外はすべて PROPAGATE となる。
      これにより v6.11 が reason を追加しても新値は自動的に安全側へ落ちる。

C-18  新Categoryを追加しない理由:
      UNKNOWN・INVALID_RESPONSE に必要なActionは PROPAGATE_ORIGINAL_ERROR であり、
      これは既存 `UNCLASSIFIED` と同一である。Amendment 1で `ENVIRONMENT_ERROR` を
      削除した際の基準——「Actionが同一のCategoryは業務判断上の差を持たないため
      統合する」（m-1対応）——をそのまま適用する。
      観測上 OpenAI 由来と非 OpenAI 由来を区別したい場合は、DI-5 が
      例外型を別途記録すればよく、Public API へCategoryを追加する必要はない。

C-19  本契約が受け入れるトレードオフを明示的に受諾する:
      **単発の応答破損（INVALID_RESPONSE）や、真に一過性の未知APIError
      （UNKNOWN 経路1）でも、その記事のfeatured media処理は継続されず
      元例外が伝播する。**
      S-12〜S-14により「記事1件の失敗はrun全体を停止させない」ことは
      確認済みであるが、該当記事は影響を受ける。
      本Releaseは「安全に分類できない失敗をfallbackへ倒さない」（G-9）を
      可用性より優先する。この優先順位は DI-11（v6.11 reason細分化）により
      将来見直しうる（22章 R-7）。

C-20  DI-11 の対象範囲を Amendment 3で拡張する。
      当初（Amendment 2）は REQUEST_REJECTED の細分化のみを対象としていたが、
      **UNKNOWN の2経路の分離（APIError catch-all と except Exception 経路）**、
      および **INVALID_RESPONSE の単発破損とスキーマ変更の分離**も
      DI-11 の検討対象に含める（20章）。
```

---

### 10.8（Amendment 3新設、M3-2対応）DI-10／DI-11 と DI-4 の順序契約

Architecture Review 3 Finding M3-2 は、Amendment 2の記述が
「DI-4着手前に**再検討**することを必須とする（トレードオフを**解消しない限り**
DI-4を安全に設計できないため）」という形で、要求（再検討）と理由（解消＝完了）に
異なる基準を併存させていたことを指摘した。本節で**条件付き二段構え**として一義化する。

**識別子について（Architecture Review 4 Finding m4-C対応）**：本節の判定規則には
`ORD-` prefix を用いる。18.1節の観測契約が `O-1`〜`O-7` を使用しているため、
`O-` prefix の再利用による混同を避ける。

```text
ORD-1  【必須】DI-4 Runtime Wiring 着手前に、DI-10 および DI-11 の必要性と、
       本Releaseが受諾した可用性トレードオフ（10.4節 C-5・10.6節 C-10・
       10.7節 C-19）を**正式に再評価すること**は必須である。
       この再評価は DI-4 の Architecture Design 工程の一部として行う。
       → **これは「再評価（再検討）」であり、「DI-10／DI-11の完了」ではない。**

ORD-2  【DI-4へ進める場合】再評価の結果、**本Releaseの安全側契約
       （安全に分類できない失敗はすべて元例外を伝播する）をそのまま受容する**と
       判断した場合、**DI-10／DI-11 が未完了のままでも DI-4 へ進めてよい**。
       この場合、DI-4 は本設計書のContractをそのまま前提として実装する。

ORD-3  【DI-10／DI-11 を先に完了すべき場合その1】
       画像なし継続（CONTINUE）の対象を、現在 PROPAGATE となっている失敗
       （WordPress Upload失敗・REQUEST_REJECTED・INVALID_RESPONSE・UNKNOWN）へ
       **拡大したい**場合は、その対象を安全に分類できるようにする
       DI-10（WordPress側）または DI-11（OpenAI側）を**先に完了する**。
       分類手段を持たないまま CONTINUE を拡大することは、
       B-1・M2-1・M3-1 で排除した permanent silent degradation の再導入であり、
       本設計書のContract上**禁止**する。

ORD-4  【DI-10／DI-11 を先に完了すべき場合その2】
       再評価の結果、**現在の可用性低下を受容できない**と判断した場合
       （例：一過性のWordPress障害やContent Policy拒否で記事処理が止まることが
        運用上許容できないと判明した場合）も、
       該当する DI（DI-10 または DI-11）を **DI-4 着手前に完了する**。

判定の要約:
       再評価は必須（ORD-1）。その結果次第で
         ・現契約を受容 → DI-10／DI-11 未完了でもDI-4可（ORD-2）
         ・CONTINUE拡大を望む → 該当DIの完了が前提（ORD-3）
         ・可用性低下を受容不可 → 該当DIの完了が前提（ORD-4）
       となる。**「再評価必須」と「完了必須」は別概念であり、
       完了が必須となるのは ORD-3・ORD-4 に該当する場合に限られる。**
```

---

## 11. Public API候補

**以下はArchitecture Amendment 1で確定した案であり、Architecture Review 2の承認を要する。**

### 11.1 package構成

```text
src/image_generation_fallback_policy/
  __init__.py
  image_generation_fallback_policy.py
```

既存 `generated_image_filename_policy` / `article_image_prompt_construction` と同じ
「package名と同名のmodule 1件」構成である。

### 11.2 `__init__.py`

```python
# src/image_generation_fallback_policy/__init__.py
from .image_generation_fallback_policy import (
    ImageGenerationFailureCategory,
    ImageGenerationFallbackAction,
    ImageGenerationFallbackDecision,
    decide_image_generation_fallback,
)

__all__ = [
    "ImageGenerationFailureCategory",
    "ImageGenerationFallbackAction",
    "ImageGenerationFallbackDecision",
    "decide_image_generation_fallback",
]
```

### 11.3 Public symbol（Amendment 1で M-1・M-3・m-1 対応済み）

```python
class ImageGenerationFallbackAction(Enum):
    """失敗に対して呼び出し側が取るべき行動。

    CONTINUE_WITHOUT_FEATURED_MEDIA:
        featured mediaを設定せずに、その記事の処理を継続してよい。
        呼び出し側は捕捉した例外を破棄してよく、ArticleData.featured_media_id は
        既存値（既定 0 = アイキャッチなし）のまま WordPress へ投稿される。

    PROPAGATE_ORIGINAL_ERROR:
        **本policyが例外をraiseするという意味ではない。**
        呼び出し側が、捕捉した「元の例外オブジェクト」を無変換で再送出する
        （wrapしない、chainingしない、新しい例外型へ変換しない）ことを意味する。
        再送出された例外をどの層が受け止めるか——記事1件を失敗として記録して
        次の記事へ進むか、run全体を停止するか——は本policyの決定事項ではなく、
        DI-4 Runtime Wiringおよび既存Runtime境界（OutputManager 等）の責任である。
    """
    CONTINUE_WITHOUT_FEATURED_MEDIA = "CONTINUE_WITHOUT_FEATURED_MEDIA"
    PROPAGATE_ORIGINAL_ERROR = "PROPAGATE_ORIGINAL_ERROR"


class ImageGenerationFailureCategory(Enum):
    """失敗のprovider中立な分類。

    provider名・provider固有のエラーコード・HTTPステータス・応答本文を含まない。
    """
    IMAGE_GENERATION_FAILED = "IMAGE_GENERATION_FAILED"
    IMAGE_GENERATION_REQUEST_REJECTED = "IMAGE_GENERATION_REQUEST_REJECTED"
    IMAGE_GENERATION_NOT_AUTHORIZED = "IMAGE_GENERATION_NOT_AUTHORIZED"
    MEDIA_UPLOAD_FAILED = "MEDIA_UPLOAD_FAILED"
    UNCLASSIFIED = "UNCLASSIFIED"


# module-levelの分類表。実行時に書き換えられることを想定しない
# （v4.4.0 RETRY_OUTCOME_TERMINALITY と同型。11.4.1節・11.5節）。
_ACTION_BY_CATEGORY = {
    ImageGenerationFailureCategory.IMAGE_GENERATION_FAILED:
        ImageGenerationFallbackAction.CONTINUE_WITHOUT_FEATURED_MEDIA,
    ImageGenerationFailureCategory.IMAGE_GENERATION_REQUEST_REJECTED:
        ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR,
    ImageGenerationFailureCategory.IMAGE_GENERATION_NOT_AUTHORIZED:
        ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR,
    ImageGenerationFailureCategory.MEDIA_UPLOAD_FAILED:
        ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR,
    ImageGenerationFailureCategory.UNCLASSIFIED:
        ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR,
}


@dataclass(frozen=True)
class ImageGenerationFallbackDecision:
    """decide_image_generation_fallback() の判定結果を表すImmutableな値オブジェクト。

    保存fieldは category のみ。action は category から一意に導出される
    read-only property であり、dataclass field ではない
    （repr／asdict／astuple／eq のいずれにも現れない。17.2節）。
    """
    category: ImageGenerationFailureCategory

    @property
    def action(self) -> ImageGenerationFallbackAction:
        """category から導出される Fallback Action。"""
        return _ACTION_BY_CATEGORY[self.category]


def decide_image_generation_fallback(
    error: Exception,
) -> ImageGenerationFallbackDecision:
    """画像featured media処理の実行時失敗に対する判断を返す。"""
```

### 11.4 M-3への対応：Action導出方式の確定

Architecture Review 1 Finding M-3は、初版の `Decision(action, category)` について
「INV-2〜INV-5が示すとおり action は category の全域関数であり、2 fieldは冗長」と
指摘した。Amendment 1はこれを受諾し、次の2案を比較のうえ確定した。

| 案 | 内容 | Repository precedent | 評価 |
|---|---|---|---|
| **案α** | `ImageGenerationFallbackDecision(category)` ＋ `action` derived property | **v6.4 `RetryHealthReport(status)`／v6.5 `RetryAlert(level)`／v6.6 `RetryNotificationDecision(status)` の3件がいずれも「保存field 1件のfrozen結果object」**（S-8） | **採用** |
| 案β | `Decision` classを廃止し、`decide()` が `ImageGenerationFailureCategory` を直接返す。Actionは Category Enum の property とする | Enumにpropertyを持たせる前例はRepositoryに存在しない。`RetryOutcomeTerminality`・`RetryCleanupReason`・`RetryAlertLevel`・`RetryHealthStatus`・`RetryNotificationStatus` はいずれもmethod・propertyを持たない純粋なEnum | 不採用 |

```text
案α採用の根拠:
  ・「Evaluator／判定関数 → 保存field 1件のfrozen結果object」という形は
    v6.4・v6.5・v6.6の3 Releaseで確立された本Repositoryの標準形である（S-8）
  ・`decide_image_generation_fallback` という関数名に対し、
    `Decision` という named result type が返るのは自然であり、
    v6.6 `RetryNotificationDecision` と語彙的にも一致する
  ・将来 Decision へ観測用fieldを追加する余地を残せる（ただし本Releaseでは追加しない）
  ・Public API件数は案β（3件）に対し案α（4件）で1件多いが、
    Enumへ振る舞いを持たせる前例のない設計を導入するコストの方が大きいと判断した

案α採用による構造的効果（M-3の本質的解決）:
  ・「category と action の組み合わせが不整合になる」という状態が **構造的に発生しない**
  ・初版のINV-2〜INV-5（category→actionの整合性制約）は
    _ACTION_BY_CATEGORY の**定義そのもの**となり、検証すべき不変条件ではなくなった
```

### 11.4.1（Amendment 2新設、m-A対応）`_ACTION_BY_CATEGORY` の可変性と `MappingProxyType` の採否

Architecture Review 2 Finding m-A は、`_ACTION_BY_CATEGORY` が素のdictであるにも
かかわらず「module-levelのmutable stateを持たない」と記載していた事実誤認を指摘した。
記述を修正（11.5節）したうえで、読み取り専用化の要否を比較する。

| 案 | 内容 | Repository precedent | 評価 |
|---|---|---|---|
| **案A** | **素のdictのまま維持し、「実行時に書き換えられることを想定しない」ことをdocstring／コメントで明示する** | **v4.4.0 `RETRY_OUTCOME_TERMINALITY: dict[...]`** が素のdictであり、同モジュールdocstringが「モジュールレベルの不変な辞書であり、実行時に書き換えられることを想定しない」と明記している | **採用** |
| 案B | `types.MappingProxyType` で読み取り専用viewへ包む | Repository内に `MappingProxyType` の使用例は**1件も存在しない** | 不採用 |

```text
案A採用の根拠:
  ・v4.4.0 が確立した「module-level分類表 ＋ 直接subscript」というprecedentに
    完全に一致する（3.9節 S-17）。同一の設計問題に対し同一の解を採る
  ・_ACTION_BY_CATEGORY は private（`_` 始まり）であり __all__ に含まれない。
    Public APIとして書き換え手段を提供していない
  ・書き換えは呼び出し側による意図的な私的属性への介入であり、
    Contract違反として扱えば足りる（12.2節の手組みインスタンスと同じ扱い）
  ・案Bは Repository に前例のない構文を1件のためだけに持ち込み、
    §12「過剰な抽象化を避ける」「不必要な実装複雑化を避ける」に反する

案A採用に伴い明示するContract:
  ・本packageは実行時に _ACTION_BY_CATEGORY を書き換えない
    （AST検証：module-level以外での _ACTION_BY_CATEGORY への代入・
      .update()／.pop()／__setitem__ 呼び出しが0件であることを確認。AC-28）
  ・呼び出し側が書き換えた場合の挙動は Public Contract として保証しない
```

### 11.5 `decide_image_generation_fallback()` のContract

| 項目 | 内容 |
|---|---|
| 形式 | module-level pure function（v6.13／v6.16／v6.17 precedent） |
| 入力 | `error: Exception` のみ。1引数、キーワード引数なし |
| 出力 | `ImageGenerationFallbackDecision`（常に返す。`None`を返さない） |
| pure decision か | **はい**。同一入力に対し常に同一の`Decision`（`==`が成立）を返す |
| exceptionを受け取るか | **はい**（例外**object**を受け取る。捕捉も再送出もしない） |
| failure categoryを受け取るか | いいえ。categoryは本関数が導出する（9.5節 第2段の正規化） |
| provider結合度 | 9.4節 V-1〜V-4／W-1〜W-4のとおり限定 |
| stateful か | いいえ。**（Amendment 2、m-A対応）** module-levelの分類表 `_ACTION_BY_CATEGORY` を保持するが、これは実行時に書き換えられることを想定しない不変な分類表である（11.4.1節）。policy判断自体は入力に対して決定的であり、呼び出し間で持ち越される状態・副作用を一切持たない |
| thread-safe か | **はい**（stateless・immutable戻り値・共有state無し。ただし本Releaseは並行実行の消費者を持たない） |
| default policy | 本Releaseが提供する唯一のpolicy。差し替え機構は設けない（N-16） |
| configuration可能性 | なし（N-16。環境変数を読まない） |
| unknown exceptionに対するdefault | `UNCLASSIFIED` → `PROPAGATE_ORIGINAL_ERROR`（安全側） |
| policy自体が失敗した場合 | `error`が`Exception`のinstanceでない場合のみ`TypeError`を送出する（固定message）。それ以外の経路で例外を送出しない |
| repr | dataclass自動生成`repr`。**`category` のみが現れ、`action` は現れない**（property のため） |
| serialization | `dataclasses.asdict()`／`astuple()` はいずれも `category` のみを含む（17.2節） |
| secret-bearing objectへの参照 | **保持しない**。受け取った`error`への参照を戻り値へ一切残さない |

### 11.6 `TypeError`送出の是非

`error`が`Exception`でない（例：`str`、`None`、`BaseException`直系）場合の扱い。

| 案 | 内容 | 評価 |
|---|---|---|
| 案(i) | `TypeError`を送出する | **採用**。呼び出し規約違反はprogramming errorであり、業務判断へ丸め込むべきでない。v6.14の「capability不足＝TypeError」precedent（v6.18 PR-8）と整合 |
| 案(ii) | `UNCLASSIFIED` を返す | 不採用。`decide()`が「どんな入力でも決定を返す」と誤解され、`BaseException`（T-33〜T-35）を渡す実装を誘発する |

**この`TypeError`は本packageが送出する唯一の例外であり、かつ新規例外型ではない
（Python標準型）。** v6.18の「新規例外型を定義しない」Contractを継承する。

### 11.7 Public API規模の妥当性

Public symbolは4件（Enum 2・dataclass 1・function 1）である。

```text
既存precedentとの比較:
  v6.4  RetryHealthEvaluator / RetryHealthReport / RetryHealthStatus /
        RetryHealthThresholds                                          → 4件
  v6.5  RetryAlertEvaluator / RetryAlert / RetryAlertLevel             → 3件
  v6.6  RetryNotificationEvaluator / RetryNotificationDecision /
        RetryNotificationStatus                                        → 3件
  v6.16 generate_image_filename                                        → 1件
  v6.17 construct_article_image_prompt                                 → 1件
```

**Category 5値の必要性（Amendment 2で再評価）**

Amendment 2後も、`CONTINUE_WITHOUT_FEATURED_MEDIA` へ導出されるCategoryは
`IMAGE_GENERATION_FAILED` の1件のみである。「ならばbool 1個で足りるのではないか」
という最小化の主張が成立しうるため、5値を維持する理由を明示する。

```text
理由1  §18 Observability Boundaryが要求する「fallback reason category」の
       観測手段は Category のみである。bool へ縮約すると、
       ・credential／permission error（NOT_AUTHORIZED）
       ・生成要求の拒否＋model不存在の混在（REQUEST_REJECTED、DI-11で解消予定）
       ・Upload側の分類不能（MEDIA_UPLOAD_FAILED、DI-10で解消予定）
       ・programming error（UNCLASSIFIED）
       の4者が区別できなくなる。この4者は**運用上まったく異なる対応を要する**
       （credential修正／model設定確認＋DI-11の実施／DI-10の実施／コード修正）

理由2  DI-10・DI-11完了後、MEDIA_UPLOAD_FAILED および
       IMAGE_GENERATION_REQUEST_REJECTED は一部が CONTINUE へ移りうる。
       Categoryを最初から分けておくことで、その変更が加算的に行える
       （10.6節 C-12。ただし逆方向の変更可能性については8.4節 J-3を参照）

理由3  v6.6 precedentが「NO_NOTIFICATION は正常に評価した結果であり、
       失敗・スキップ・未実行のいずれも意味しない」と語彙の明示性を重視している。
       bool は同種の曖昧さを持ち込む

理由4  （Amendment 2追加）IMAGE_GENERATION_REQUEST_REJECTED は
       IMAGE_GENERATION_FAILED と**異なるActionを必要とする**ため、
       Category分割なしには表現できない。actionをcategoryから導出する設計
       （11.4節）を維持する以上、Actionの差はCategoryの差として表現するほかない。
       これは観測上の利便ではなく、**Public API上の必然**である
```

**Category 5値が互いに排他的であることの確認（Amendment 2）**

```text
IMAGE_GENERATION_FAILED            reason ∈ {TIMEOUT, CONNECTION,
                                            RATE_LIMIT, SERVER_ERROR}   ← allow-list
IMAGE_GENERATION_REQUEST_REJECTED  reason == REQUEST_REJECTED
IMAGE_GENERATION_NOT_AUTHORIZED    reason ∈ {AUTHENTICATION, PERMISSION_DENIED}
MEDIA_UPLOAD_FAILED                isinstance(error, WordPressMediaUploadError)
UNCLASSIFIED                       上記のいずれにも該当しない
                                   （INVALID_RESPONSE / UNKNOWN / 未知reason /
                                     reason属性欠落 / 2型以外の全Exception）

上位3つは OpenAIImageGenerationError であることを前提に reason で分岐するため
相互排他。OpenAIImageGenerationError と WordPressMediaUploadError は
別の型であり同時に成立しない。UNCLASSIFIED は残余集合として定義される。
したがって5値は網羅的（exhaustive）かつ相互排他（mutually exclusive）である。

OpenAIImageGenerationErrorReason の9値は **4 / 1 / 2 / 2** に分割され、
過不足なく被覆される（AC-13の網羅検証で担保）。

  IMAGE_GENERATION_FAILED            4値  TIMEOUT / CONNECTION /
                                          RATE_LIMIT / SERVER_ERROR
  IMAGE_GENERATION_REQUEST_REJECTED  1値  REQUEST_REJECTED
  IMAGE_GENERATION_NOT_AUTHORIZED    2値  AUTHENTICATION / PERMISSION_DENIED
  UNCLASSIFIED                       2値  INVALID_RESPONSE / UNKNOWN
                                          （Amendment 3で移動）
  合計                               9値
```

---

## 12. Data／Decision Model

### 12.1 Invariants（Amendment 1で全面改訂：M-3・Q-4対応）

初版のINV-1〜INV-5（category と action の整合性制約）は、Amendment 1で
`action` を derived property としたことにより**定義そのもの**となり、
検証対象の不変条件ではなくなった。

```text
残る不変条件:
  INV-1  category は ImageGenerationFailureCategory のmemberである
         → decide() が唯一の生成経路である限り、構造的に成立する

導出規則（不変条件ではなく定義）:
  DEF-1  action == _ACTION_BY_CATEGORY[category]
  DEF-2  _ACTION_BY_CATEGORY は ImageGenerationFailureCategory の
         全memberを鍵として持つ（網羅性。AC-12でE2E検証）
```

### 12.2 `__post_init__` の要否（Q-4の確定）

**確定：`__post_init__` を持たない。**

```text
根拠1  v6.4 RetryHealthReport／v6.5 RetryAlert／v6.6 RetryNotificationDecision は
       いずれも __post_init__ を持たない（S-8）。本設計はこの precedent に一致させる

根拠2  category と action の不整合という失敗モードが構造的に消滅したため
       （11.4節）、検証すべき組み合わせが存在しない

根拠3  __post_init__ を持たないことで ast.Raise は decide() 内の TypeError 送出
       1箇所のみとなり、「例外を送出しない層」という性質を機械検証しやすい（AC-14）

限界の明示（Contract外の挙動）:
       呼び出し側が ImageGenerationFallbackDecision(category="oops") のように
       Enum member 以外を渡して手組みした場合、`.action` は KeyError を送出する。
       これは 3.9節 S-17（RETRY_OUTCOME_TERMINALITY[reason] の直接subscript）と
       同じ挙動であり、**既定値へ丸めない**という Repository の方針に一致する。
       手組みインスタンスの挙動は Public Contract として保証しない
       （v6.4〜v6.6 の結果objectも同様に未検証である）。
```

### 12.3 equality／hash／repr

```text
equality  @dataclass(frozen=True) により __eq__ が自動生成される。
          比較対象は category のみ（action は field ではない）。
          action は category の関数であるため、equality の意味は変わらない。

hash      frozen=True により __hash__ が自動生成される。
          同一 category の Decision は常に同一 hash を持つ。

repr      自動生成 repr は
              ImageGenerationFallbackDecision(category=<...UNCLASSIFIED: 'UNCLASSIFIED'>)
          の形となり、**action は現れない**。
          → 呼び出し側が repr をログ等へ用いる場合、action は別途 .action で
            取得する必要がある（22章 R-8）
```

### 12.4 callerが通常成功とfallbackを識別する方法

```text
本Releaseの範囲では、識別は「decide() が呼ばれたかどうか」そのものである。
decide() は失敗が発生したときにのみ呼ばれる関数であり、成功経路には現れない。
戻り値 Decision の存在自体が「失敗が起きた」ことを意味する（成功を表す値を持たない）。

→ Category に SUCCESS / NO_FAILURE 相当の値を設けない。
  これは v6.6 の NO_NOTIFICATION（「正常に評価した結果、対象外」）とは異なる設計であり、
  本Releaseでは「評価は必ず失敗を入力とする」という前提を明示することで
  silent failure の入り込む余地を無くす。
```

### 12.5 callerがfallback理由を識別できる範囲

```text
識別できる    : ImageGenerationFailureCategory（5値、provider中立）
                および そこから導出される Action（2値）
識別できない  : provider名・HTTPステータス・provider応答本文・
                失敗した具体的stage（generate か upload かは
                IMAGE_GENERATION_FAILED / IMAGE_GENERATION_NOT_AUTHORIZED /
                MEDIA_UPLOAD_FAILED の区別で概ね判別できるが、
                UNCLASSIFIED ではstageが判別できない）
```

stage情報を`Decision`へ追加しないことはQ-5で確定した（28章）。

---

## 13. Error Contract

### 13.1 本packageが送出する例外

| # | 事象 | 例外型 | message | 備考 |
|---|---|---|---|---|
| E-1 | `error`が`Exception`のinstanceでない | `TypeError` | `"error must be an Exception"` | 固定message。11.6節 |

上記1件のみである。

### 13.2 原則（v6.18 16.2節を継承）

```text
try／except を1つも書かない（AST検証 ast.ExceptHandler == 0）
例外 wrapper を作らない
raise ... from ... を使用しない
新規例外型を定義しない
**受け取った例外を再送出しない（再送出の主体は呼び出し側である）**
例外の message・args・__cause__・__context__・__traceback__ を読まない
credential・環境変数・prompt・image bytes を message へ含めない
```

**「例外の`args`を読まない」は本設計の重要な制約である。** 分類に用いてよいのは
`isinstance()` と、`OpenAIImageGenerationError.reason`（v6.11が secret-free と定めた
Public な分類Enum）のみである。

### 13.3 `PROPAGATE_ORIGINAL_ERROR` の意味の確定（Amendment 1、M-1対応）

```text
PROPAGATE_ORIGINAL_ERROR が意味すること:
    P-1  呼び出し側は、except節で捕捉した「元の例外オブジェクトそのもの」を
         無変換で再送出する（Pythonでは bare `raise` が該当する）
    P-2  新しい例外型への変換・wrap・`raise ... from ...` は行わない
    P-3  例外messageの加工・付加情報の連結は行わない

PROPAGATE_ORIGINAL_ERROR が意味しないこと:
    Q-1  policy自身が例外をraiseすること（policyは常に Decision を返す）
    Q-2  run全体を停止すること
    Q-3  記事ループを打ち切ること
    Q-4  記事1件をスキップすること
    → 再送出された例外がどの層で受け止められ、その結果 run が停止するのか、
      記事1件が失敗として記録されるだけなのかは、DI-4 Runtime Wiring および
      既存Runtime境界（S-12〜S-14：OutputManager.save_all() の except Exception、
      main.py の wp_failed_count 加算）の責任である。

Repository根拠:
    S-12〜S-14により、このRepositoryでは「記事1件の失敗」は「run全体の停止」を
    意味しない。policyがrun制御を決めることは責務越境である（4.2節・9.2節 R-13）。
```

### 13.4 未知の`reason`値に対する扱い（Amendment 1、3.9節 S-16からの意図的逸脱）

```text
規則:
    error が OpenAIImageGenerationError であり、かつ
    getattr(error, "reason", None) が OpenAIImageGenerationErrorReason の
    member でない場合、UNCLASSIFIED（→ PROPAGATE_ORIGINAL_ERROR）へ倒す。
    ValueError は送出しない。

    **「member でない」の範囲（Documentation Integrationで明確化。
    Production Code Review Finding m-1・Correctionで実装済みの既存契約の
    明文化であり、新しいFailure TaxonomyやError Contractの追加ではない）**：
    ここでいう「member でない」とは、文字列・整数などのhashable値だけでなく、
    `list`／`dict`／`set`等の**ハッシュ不可能な値**も含む。`reason`が
    ハッシュ不可能な値であっても、`_CONTINUABLE_REASONS`（frozenset）への
    membership testを試みる前に`isinstance(reason,
    OpenAIImageGenerationErrorReason)`で判定するため、
    `TypeError: unhashable type`のような**policy自身に起因する予期しない
    例外を送出せず**、常にUNCLASSIFIEDへ安全側分類される（13.5節）。
    入力自体（`error`）が`Exception`のinstanceでない場合に送出する
    固定message`TypeError`（13.1節 E-1）とは別の契約であり、
    この既存契約は本明確化によって変更されない。

v6.6 precedent（S-16）からの逸脱理由:
    RetryNotificationEvaluator は未対応Enum値に対し ValueError を送出する
    Fail Fast契約を採る。本設計はこれに従わない。理由は次のとおり。

    理由1  本policyは呼び出し側の except 節の内側から呼ばれる。
           ここで新しい ValueError を送出すると、**元の例外を置き換えて
           診断情報を破壊する**。これは 13.2節「例外wrapperを作らない」
           「元例外を保全する」という本設計の中核原則に反する
    理由2  UNCLASSIFIED → PROPAGATE_ORIGINAL_ERROR は、
           「判断せず元例外をそのまま上げる」という**Fail Fastと同等以上に安全な**
           結果を与える。v6.6のValueError送出が達成しようとした
           「知らない値を既定値へ丸めない」という目的は、
           PROPAGATE（＝何も丸めずに元の失敗をそのまま見せる）により達成される
    理由3  v6.6の入力は信頼できる上流コンポーネント（RetryAlertEvaluator）の
           出力であるのに対し、本policyの入力は任意のコードが送出した例外である。
           入力の信頼度が異なる

Category → Action の写像については S-17 precedent に従う:
    _ACTION_BY_CATEGORY[category] という**直接subscript**とし、
    `.get(default)` による既定値への丸めは行わない。
    将来Categoryを追加して写像への登録を怠った場合、KeyError として顕在化する
    （AC-12の網羅検証で事前に検知する）。
```

### 13.5 分類アルゴリズム（擬似コード、Amendment 1で確定）

```text
def decide_image_generation_fallback(error):
    if not isinstance(error, Exception):
        raise TypeError("error must be an Exception")

（module-level。11.3節の `_ACTION_BY_CATEGORY` と同じ位置に置く）

# CONTINUE となる reason の allow-list（10.3節・10.7節 C-17）
# 実行時に書き換えられることを想定しない（11.4.1節・AC-28）
_CONTINUABLE_REASONS = frozenset({
    OpenAIImageGenerationErrorReason.TIMEOUT,
    OpenAIImageGenerationErrorReason.CONNECTION,
    OpenAIImageGenerationErrorReason.RATE_LIMIT,
    OpenAIImageGenerationErrorReason.SERVER_ERROR,
})


（decide_image_generation_fallback() 本体）

    if isinstance(error, OpenAIImageGenerationError):
        reason = getattr(error, "reason", None)
        if reason is OpenAIImageGenerationErrorReason.AUTHENTICATION \
           or reason is OpenAIImageGenerationErrorReason.PERMISSION_DENIED:
            category = IMAGE_GENERATION_NOT_AUTHORIZED
        elif reason is OpenAIImageGenerationErrorReason.REQUEST_REJECTED:
            category = IMAGE_GENERATION_REQUEST_REJECTED   # 10.6節 C-6（Amendment 2）
        elif (
            isinstance(reason, OpenAIImageGenerationErrorReason)
            and reason in _CONTINUABLE_REASONS
        ):
            category = IMAGE_GENERATION_FAILED             # 4 reason のみ（10.3節）
        else:
            category = UNCLASSIFIED
            # INVALID_RESPONSE / UNKNOWN / 未知reason / reason属性欠落 /
            # ハッシュ不可能なreason値（list・dict・set等）をすべてここへ落とす
            # （10.7節 C-13〜C-16、13.4節。Correction Finding m-1で
            #   isinstance判定を membership test の前に追加し、
            #   TypeError（unhashable type）を安全側へ倒すよう確定した）
    elif isinstance(error, WordPressMediaUploadError):
        category = MEDIA_UPLOAD_FAILED        # 10.4節 C-1
    else:
        category = UNCLASSIFIED

    return ImageGenerationFallbackDecision(category=category)
```

**Correction Finding m-1（Documentation Integrationで反映）**：Production Code
Reviewで、`reason`がハッシュ不可能な値（`list`／`dict`／`set`等）の場合に
`reason in _CONTINUABLE_REASONS`が`TypeError: unhashable type`を送出し、
上記「規則」（memberでない場合はUNCLASSIFIEDへ倒す）に違反することが
検出された（m-1、Minor）。Production Implementation Correctionで
`isinstance(reason, OpenAIImageGenerationErrorReason) and reason in
_CONTINUABLE_REASONS`へ修正し、`isinstance`の短絡評価によりハッシュ不可能な
値がfrozensetへのmembership testへ到達しないようにした。この修正は
Architecture・Public API・Category→Action写像・allow-list 4 reasonのいずれも
変更しない、既存契約の実装上の正確化である。新規E2E `DEFENSE-`Scenarioへ
`reason=[]`／`{}`／`set()`の3ケースを追加し、いずれもUNCLASSIFIED＋
PROPAGATE_ORIGINAL_ERRORへ倒れ、policy自身から予期しないTypeErrorを
送出しないことを確認済みである（254 Assertion中に含む）。

**allow-list 方式のContract（Amendment 3、M3-1対応）**：`IMAGE_GENERATION_FAILED`
への分類は `_CONTINUABLE_REASONS` への所属判定という**明示的なallow-list**で行う。
Amendment 2までの `isinstance(reason, OpenAIImageGenerationErrorReason)` による
一般判定（deny-list）は撤去した。この転換により、
`INVALID_RESPONSE`・`UNKNOWN`・v6.11が将来追加する未知reason・reason属性の欠落が
**すべて同一の `else` 分岐（UNCLASSIFIED → PROPAGATE）へ落ちる**。
安全側の既定が構造的に保証され、13.4節の防御的分岐は独立した分岐を持たなくなる。

**分岐順序のContract**：`AUTHENTICATION`／`PERMISSION_DENIED`／`REQUEST_REJECTED`
の判定は allow-list 判定より**前**に置く。これは v6.11 `_classify_api_error()` が
「具体的なsubclassから一般的な `APIError`（catch-all）の順に判定する」precedentと
同型である。判定は `reason` の**同一性比較（`is`）とfrozensetへの所属判定のみ**に
基づき、messageもstatusコードもprovider応答本文も読まない。

**`_CONTINUABLE_REASONS` の配置と可変性**（Architecture Review 4 Finding m4-A対応で明確化）：
`_ACTION_BY_CATEGORY`（11.3節）と同じく **module-level に定義する**（関数内で毎回
再構築しない）。型は `frozenset` を用いる。`_ACTION_BY_CATEGORY` が素のdictである
（11.4.1節）のと扱いが異なるが、これは「集合リテラルとして自然に不変型を選べる」
ためであり、追加の抽象を導入していない（`dict` に対する `MappingProxyType` のような
包装は不要）。両者とも AC-28 の対象であり、module-level 以外での代入・変更が
0件であることをAST検証する。

**isinstance判定はRepository内の型3種のみに対して行う**（Documentation
Integrationで更新：Correction Finding m-1対応により、adapter例外2型
（`OpenAIImageGenerationError`／`WordPressMediaUploadError`）に加え、
安全側判定のため`OpenAIImageGenerationErrorReason`（Enum型）への
isinstance判定を追加した。汎用組み込み型ではなくRepository内で公開済みの
Enum型であり、下記の禁止対象には該当しない）。
汎用型（`ImportError`／`ValueError`／`TypeError`等）への isinstance 判定は
一切行わない（Amendment 1、m-1対応で `ENVIRONMENT_ERROR` を削除した結果）。

---

## 14. Fail Fast との整合

| # | 要求 | 本設計の対応 |
|---|---|---|
| 1 | configuration errorをfallbackで隠さない | T-3〜T-7はConstruction Failureとして本policyへ到達しない。実行時に現れるconfiguration errorはprovider横断で`PROPAGATE_ORIGINAL_ERROR`（OpenAI: T-13・T-14 credential／permission、**T-15・T-16 model不存在を含むREQUEST_REJECTED**／WordPress: T-26全件）。**（Amendment 2、M2-1対応）model不存在（HTTP 404）が `REQUEST_REJECTED` に含まれるため、これをCONTINUEにすると全記事へ反復するsystemic failureを隠すことになる（10.6節）** |
| 2 | credential不足を正常なunavailable扱いに変換しない | 本packageは`is_available()`相当の可用性表現を一切持たない。Gate OFF（T-1）とruntime failureを混同する経路が構造的に存在しない |
| 3 | Gate OFFとruntime failureを混同しない | `decide()`は例外objectのみを入力とする。Gate状態を入力に取らず、`ImageGenerationConfig`をimportしない（9.3節 禁止import） |
| 4 | programming errorをfallback対象にしない | T-8・T-9・T-21〜T-25・T-27〜T-29・T-31・T-32はすべて`UNCLASSIFIED` → `PROPAGATE_ORIGINAL_ERROR` |
| 5 | dependency構築失敗とapply()中の失敗を分離する | 10.2節の「DI-1で扱うか」列で「対象外（構築時）」を明示。v6.18 E-15が定めた境界（S-6）をそのまま採用し、変更しない |
| 6 | fallbackによって部分構築状態を許容しない | 本packageはobjectを構築しない。`Decision`は完全に構築されるか、`TypeError`が送出されるかのいずれかである |
| 7 | fallbackが「成功」に見えるsilent failureを作らない | `Decision`は成功を表す値を持たない（12.4節）。`CONTINUE_WITHOUT_FEATURED_MEDIA`であっても`category`が必ず失敗理由を保持する |
| 8 | **（Amendment 1追加）分類できない失敗をfallbackへ倒さない（G-9）** | 分類不能領域（`UNCLASSIFIED`・`MEDIA_UPLOAD_FAILED`）はすべて`PROPAGATE_ORIGINAL_ERROR`。継続は「安全と積極的に判定できた1 Category」に限定される |

### 14.1 既存契約からの変更の有無

```text
変更する既存契約: なし

・v6.9／v6.10／v6.11／v6.12／v6.13／v6.14／v6.15／v6.16／v6.17／v6.18 のいずれも無改修
・例外型・例外message・propagation・signature・戻り値型のいずれも変更しない
・**Amendment 1でも v6.9 への reason Enum 追加は行わない**（N-17、DI-10へDeferred）
・したがって Breaking Change は存在しない（24章）
```

---

## 15. Gate OFF／Gate ON behavior

```text
Gate OFF（AI_IMAGE_GENERATION_ENABLED が "true" 以外）:
    v6.18 from_env() が orchestrator=None を返し、is_available() == False となる。
    apply() が呼ばれないため、失敗も発生せず、decide() も呼ばれない。
    → 本packageはGate状態を一切参照しない（14章 要求3）

Gate ON ＋ credential不足:
    v6.18 from_env() が ValueError を無変換伝播する（Construction Failure）。
    → 本packageへ到達しない（T-3〜T-5）

Gate ON ＋ 正常構築 ＋ apply() 実行中の失敗:
    → 本packageの唯一の適用領域（T-8〜T-32）
```

---

## 16. Runtime behavior

### 16.1 本Releaseにおけるruntime behavior

**変化なし。** 本packageは既存Runtimeのいずれからも参照されず、`main.py`の記事ループ・
publish順序・WordPress payload構築のいずれも変更しない。`AI_IMAGE_GENERATION_ENABLED`を
`true`に設定しても、本Release単独ではRuntime動作は一切変化しない（v6.15〜v6.18と同じ
Consumer-less状態が継続する）。

### 16.2 想定される将来の利用イメージ（Contractではない・参考情報、Amendment 1で更新）

DI-4 Runtime Wiringで想定される形は次のとおりであるが、**本Releaseでは実装しない。**
catchする層・記事ループ内の配置・再送出された例外の受け止め方はいずれもDI-4の設計事項である。

```python
# ▼ 参考イメージ（本Releaseでは実装しない。DI-4の設計事項）
if root.is_available():
    # ★ prompt／filename構築は try の外側に置いている（T-23・T-24 が policy へ
    #    到達しない構成）。try 範囲をどこに置くかは DI-4 が決める（N-20）
    prompt   = construct_article_image_prompt(article.seo_title, article.excerpt)
    filename = generate_image_filename(article.seo_title, root.image_mime_type)

    try:
        article = root.orchestrator.apply(article, prompt, filename)
    except Exception as exc:                  # BaseExceptionは捕捉しない（T-33〜T-35）
        decision = decide_image_generation_fallback(exc)
        if decision.action is ImageGenerationFallbackAction.PROPAGATE_ORIGINAL_ERROR:
            raise                             # ★ 元例外を無変換で再送出（13.3節 P-1）
        # CONTINUE_WITHOUT_FEATURED_MEDIA:
        #   article は未変更のまま（featured_media_id は既定 0）。
        #   decision.category の記録方法は DI-5 の設計事項（18章）
```

**この例が示す本Releaseの範囲外の事項（N-20・N-21）**

```text
・try の開始位置（prompt／filename構築を含めるか）        → DI-4
・raise された例外を誰が受け止めるか（記事単位／run単位） → DI-4／既存Runtime境界
・decision.category をどこへどう記録するか                → DI-5
```

---

## 17. Security Contract

### 17.1 本packageが保持しないもの

```text
S-1   API key・app password・token を field として保持しない（そもそも受け取らない）
S-2   環境変数を読まない（os.environ / os.getenv を使用しない。os をimportしない）
S-3   受け取った例外objectへの参照を戻り値へ残さない
S-4   例外 message・args を読まず、保持しない
S-5   raw provider response（レスポンス本文・status code・header）を読まず、保持しない
S-6   Authorization header・request payload を扱わない
S-7   image prompt を扱わない
S-8   generated image bytes を扱わない
S-9   log出力（print / logging）を行わない（logging をimportしない）
S-10  外部I/O（HTTP・DNS・socket・filesystem）を行わない
S-11  lazy client cache（v6.11 の self._client）へ触れない
```

### 17.2 `Decision` object の serialization 安全性（限定付き保証、Amendment 1で更新）

```text
保証する範囲:
    ImageGenerationFallbackDecision の保存fieldは category 1件のみであり、
    その値は本package内で定義した Enum member である。したがって
      ・repr(decision) / str(decision)
      ・dataclasses.asdict(decision)   → {'category': <Enum member>}
      ・dataclasses.astuple(decision)  → (<Enum member>,)
    のいずれも、本package内で定義した固定ラベル文字列以外を出力しない。
    decide() が返したインスタンスに限り、この保証は成立する。

    **action は dataclass field ではなく property であるため、
    repr／asdict／astuple のいずれにも現れない**（12.3節・22章 R-8）。

保証しない範囲:
    ・呼び出し側が ImageGenerationFallbackDecision を手組みし、
      Enum以外の値を渡した場合（12.2節のとおりContract外）
    ・呼び出し側が Decision と一緒に例外objectを保持・出力する場合
    ・呼び出し側が Decision を含むより大きな構造を asdict() する場合
      （その構造に secret-bearing object が含まれていれば、当然 secret が出力される）
```

**v6.18 の教訓（Architecture Review 1 Finding F-1）を踏まえ、「secret-safe」という語は
上記の限定範囲でのみ用いる。** 本packageは「`decide()` が返した`Decision`インスタンス
単体の serialization に限り、secret・provider情報が混入しない」ことのみを保証する。

### 17.3 例外messageを保持しないという判断の根拠

```text
OpenAIImageGenerationError.message:
    v6.11設計により固定文字列のみ（"OpenAI APIのレート制限に達しました" 等）。
    単体では漏えいリスクは低い。

WordPressMediaUploadError.message:
    _build_non_2xx_message() が WordPressレスポンスJSONの code（100文字まで）・
    message（200文字まで）を連結しうる。**これはprovider応答本文の一部であり、
    サイト構成・プラグイン名・内部エラー詳細等を含みうる。**
    制御文字sanitizeと長さ切り詰めは行われるが、内容の秘匿性は保証されていない。

結論:
    2つの例外型でmessage安全性の水準が異なるため、**どちらのmessageも保持しない**
    という単一のContractを採る。これにより呼び出し側が「Decisionをlogに出せば安全」
    と考えられる状態を作る。message が必要な場合は呼び出し側が例外objectから
    自己責任で取得する（本packageはその経路を提供しない）。
```

### 17.4 apply()後のobject graph／subprocess E2Eでのenvironment isolation

```text
・本packageは orchestrator / generator / uploader のいずれへも参照を持たないため、
  apply() 実行後のobject graph変化（v6.18 で DI-4 へ引き渡された論点）の影響を受けない
・E2Eは subprocess を用いる場合も含め、OPENAI_API_KEY / WP_* を設定せずに全件成立する
  設計とする（21.3節）。実credentialを一切必要としない
```

---

## 18. Observability Boundary

DI-5（observability／logging contract）を先取りせず、silent failureも作らないための
最小限の観測契約を定める。

### 18.1 本Releaseで定義するもの（観測**契約**のみ）

```text
O-1  fallback occurred:      Decision が返された事実そのもの。
                             decide() は失敗時にのみ呼ばれるため、
                             Decision の生成＝失敗の発生である
O-2  fallback reason category: Decision.category（provider中立の5値）
O-3  action:                 Decision.action（2値、derived property）
O-4  retryable / non-retryable: **本Releaseでは表現しない**（Q-6で確定）。
                             retryabilityはDI-6の語彙であり、先取りしない
O-5  stage:                  category から間接的に判別できる範囲に留める（12.5節）。
                             独立したstage fieldは設けない（Q-5で確定）
O-6  provider:               **表現しない**（provider中立な語彙を保つため、9.4節 V-1）
O-7  article identifier:     **本packageは扱わない**。記事の識別はDI-4／DI-5の責務であり、
                             decide() は ArticleData を受け取らない（9.2節 R-10）
```

### 18.2 本Releaseで定義しないもの（DI-5へDeferred）

```text
・log出力の実装（logger選択・log level・format・出力先）
・metrics収集・集計・閾値判定
・通知（DI-5以降、Retry Notification系の別系統）
・log行のschema定義
```

### 18.3 記録してはならない情報（本Releaseで定めるContract）

```text
・raw exception message（17.3節）
・image prompt
・generated image bytes
・API key・app password・site URL・username
・provider応答本文・HTTPステータスコード・header

将来DI-5がloggingを実装する際、これらを記録しないことを本Releaseの
Contractとして先に固定しておく。DI-5はこのContractを緩める場合、
独立したSecurity Reviewを要する。
```

---

## 19. Retry Boundary

| # | 論点 | 本設計の立場 |
|---|---|---|
| RB-1 | DI-1でretryを実装するか | **しない**（N-6）。`decide()`は`RETRY`というActionを持たない |
| RB-2 | provider SDKの既定retryを変更するか | **しない**。v6.11は`with_options(timeout=..., max_retries=0)`で既にSDK自動retryを無効化済み（`_get_client()`）。本Releaseはこれを変更しない |
| RB-3 | timeout後にfallbackする条件 | T-10（TIMEOUT）は`CONTINUE_WITHOUT_FEATURED_MEDIA`。retryを挟まず、1回の失敗で即座に判断する（v6.11が`max_retries=0`である以上、timeout＝1回の試行の失敗である） |
| RB-4 | retry exhausted という状態を扱うか | **扱わない**。retryが存在しないため、exhausted状態が発生しない。将来DI-6がretryを導入した場合、「retry後の最終失敗」を本policyへ渡す形が想定されるが、その接続はDI-6の設計事項 |
| RB-5 | duplicate image generationの危険 | 本packageは`generate()`を呼ばないため、重複生成を発生させない。`CONTINUE_WITHOUT_FEATURED_MEDIA`は「諦める」判断であり、再試行を促さない |
| RB-6 | WordPress upload retryとDI-6の関係 | **（Amendment 1で更新）** T-26は`PROPAGATE_ORIGINAL_ERROR`である。一過性のWordPress障害でも伝播するため、可用性の観点ではretry（DI-6）またはreason分類（DI-10）が望まれる。両者はいずれも本ReleaseのOut of Scopeであり、DI-4着手前の再検討対象とする（10.4節 C-4・C-5） |
| RB-7 | fallbackがidempotency問題を発生させないか | **発生させない**。`CONTINUE_WITHOUT_FEATURED_MEDIA`は追加の外部呼び出しを一切伴わない。ただし「upload成功後にbindが失敗した」場合（T-28）は`PROPAGATE_ORIGINAL_ERROR`となり、WordPress上に未使用Mediaが残る。**これはDI-7 WordPress Unused Media Cleanupの領域であり、本Releaseは検出も削除も行わない**（N-8、22章 R-5） |

---

## 20. Deferred Itemsとの関係

| Deferred Item | 本Releaseとの関係 |
|---|---|
| **DI-2 generator capability Protocol** | **不要**。`decide()`はgeneratorを受け取らず、`AIImageGenerator` Protocolへ触れない。9.3節でimport禁止としている。**したがって「DI-1の成立にDI-2が必須」ではない** |
| **DI-3 Article Featured Media Orchestration v2** | 本Releaseは`ArticleFeaturedMediaOrchestrator`を無改修（N-10）。DI-3が`apply()`の戻り値を変更する場合、本policyの入力（例外object）は変わらないため、本ReleaseのContractは維持される |
| **DI-4 Article Featured Media Runtime Wiring** | 本Releaseの決定を実行に移す消費者。catchする層・try範囲（N-20）・再送出された例外の受け止め方（N-21）はすべてDI-4の設計事項（16.2節）。**（Amendment 3、M3-2対応で一義化）着手前に DI-10／DI-11 の必要性と可用性トレードオフを正式に再評価することは必須（ORD-1）。現契約を受容する場合は DI-10／DI-11 未完了でも着手してよい（ORD-2）。CONTINUE 対象を拡大したい場合、または現在の可用性低下を受容できない場合に限り、該当DIの完了が着手の前提となる（ORD-3・ORD-4）。詳細は10.8節** |
| **DI-5 observability／logging contract** | 18章で観測契約の骨格（category／actionのみを記録可・rawは記録不可）を定め、実装をDI-5へ委ねる |
| **DI-6 Media Upload Retry／Idempotency** | 19章 RB-4・RB-6。retryが導入された場合、T-26の可用性トレードオフ（10.4節 C-5）が緩和されうる |
| **DI-7 WordPress Unused Media Cleanup** | 19章 RB-7。`PROPAGATE_ORIGINAL_ERROR`時の未使用Media残存はDI-7の領域 |
| **DI-8 Publish Composition Root Foundation** | 直接の依存関係なし |
| **DI-9 Image Generation Gate Value Strict Validation** | T-2。本Releaseは対象外 |
| **DI-10（新規）WordPress Media Upload Failure Reason Classification** | **（Amendment 1で正式化、B-1対応）** `WordPressMediaUploadError` へ、v6.11 `OpenAIImageGenerationErrorReason` と同型の分類Enum（型・HTTPステータスのみに基づき、message解析を行わない）を純追加する。v6.9のPublic API変更を伴うため独立Releaseを要する。**本Releaseでは実施しない（N-17）。DI-4 Runtime Wiring着手前に、その必要性と可用性トレードオフを正式に再評価することは必須である（10.8節 ORD-1）が、現契約を受容する場合はDI-10未完了でもDI-4へ進めてよい（ORD-2）。WordPress Upload失敗をCONTINUEへ拡大したい場合、または一過性WP障害による可用性低下を受容できない場合に限り、DI-10の完了がDI-4着手の前提となる（ORD-3・ORD-4）**（10.4節 C-4・10.8節）。これが完了するまで、WordPress Media Upload失敗は一過性障害を含めてすべて元例外の伝播となる（10.4節 C-5）。**（Amendment 2、m-C対応）DI-10実施時には、本ReleaseのAC-24および `COMPAT-` Scenario（`WordPressMediaUploadError` に `reason` 属性が存在しないことを固定する否定的アサーション）が必然的にFAILする。これは設計上の既知差分であり、無関係なRegressionとして扱ってはならない**（詳細は23章 AC-24の注記） |
| **DI-11（新規）OpenAI Image Generation Request Rejection Reason Refinement** | **（Amendment 2で正式化、M2-1対応）** v6.11 `_classify_api_error()` が単一の `REQUEST_REJECTED` へ集約している4つのProvider例外型（`BadRequestError`／`NotFoundError`／`ConflictError`／`UnprocessableEntityError`）を、`OpenAIImageGenerationErrorReason` の追加値へ細分化する。特に**記事固有の失敗（Content Policy拒否、HTTP 400）と、全記事へ反復するsystemic failure（model不存在・model提供終了、HTTP 404）の分離**を目的とする。分類は引き続き例外の型のみに基づき、message解析・response body読み取りを行わない。v6.11のPublic API変更（Enum値追加）を伴うため独立Releaseを要する。**本Releaseでは実施しない（N-22）。DI-4着手前の正式な再評価は必須（10.8節 ORD-1）だが、現契約を受容する場合はDI-11未完了でもDI-4へ進めてよい（ORD-2）。CONTINUE対象の拡大を望む場合、または当該可用性低下を受容できない場合に限り完了が前提となる（ORD-3・ORD-4）。**（Amendment 3、C-20で対象拡張）DI-11の検討対象には、REQUEST_REJECTEDの細分化に加え、`UNKNOWN` の2経路分離（APIError catch-all と `except Exception` 経路）および `INVALID_RESPONSE` の単発破損とスキーマ変更の分離も含める**（10.6節 C-9・10.7節 C-20・10.8節）。これが完了するまで、`REQUEST_REJECTED` はContent Policy拒否を含めてすべて元例外の伝播となる（10.6節 C-10）。DI-11実施時には本ReleaseのAC-13（reason全9値の網羅検証）が必然的にFAILするが、これもDI-10と同種の既知差分である |

---

## 21. Test Strategy

### 21.1 テストファイル候補

```text
tests/test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py
```

命名は既存規則 `test_e2e_v{major}_{minor}_{patch}_{snake_case_name}.py` に従う
（`test_e2e_v6_18_0_article_featured_media_composition_root_foundation.py` と同型）。
形式はv6.9.0〜v6.18.0のprecedentどおり **standalone script形式**（`check()` /
`check_true()` 等の自作アサーションヘルパ、`results_log`集計、`sys.path.insert`で
`src`を追加）とする。

### 21.2 Scenario prefix候補（Amendment 1で更新）

**Scenario数・Assertion数は目標値として固定せず、AC被覆と重複排除を条件とする
結果値として報告する**（v6.18 Amendment 1 F-8対応の方針を継承）。

| prefix | 検証対象 |
|---|---|
| `API-` | `__all__`が4 symbolのみ・export面・`decide()`のsignature（1引数・キーワード引数なし） |
| `ACTION-` | `ImageGenerationFallbackAction`の値集合が `CONTINUE_WITHOUT_FEATURED_MEDIA` / `PROPAGATE_ORIGINAL_ERROR` の**2件で過不足ない**こと・value文字列 |
| `CAT-` | `ImageGenerationFailureCategory`の値集合が**5件で過不足ない**こと・value文字列。**`ENVIRONMENT_ERROR` が存在しないこと**（m-1対応の回帰防止）。**`IMAGE_GENERATION_REQUEST_REJECTED` が存在すること**（Amendment 2、M2-1対応） |
| `MAP-` | `action` が category から導出されること・`_ACTION_BY_CATEGORY` が全Category memberを網羅すること（AC-12）。**`IMAGE_GENERATION_FAILED` のみが `CONTINUE_WITHOUT_FEATURED_MEDIA` へ写像され、残り4 Categoryはすべて `PROPAGATE_ORIGINAL_ERROR` へ写像されること**。**module-levelの `_ACTION_BY_CATEGORY` が `decide()` 呼び出しの前後で不変であること**（Amendment 2、m-A対応。AC-28） |
| `IMM-` | `Decision`が`frozen=True`・`fields()`が **`category` 1件のみ**・再代入で`FrozenInstanceError`・`==`／`hash()`の決定性・**`action` が `fields()` に含まれないこと** |
| `CONT-` | 継続対象：**T-10〜T-12・T-17（reason 4値：TIMEOUT／CONNECTION／RATE_LIMIT／SERVER_ERROR）のみ**が`IMAGE_GENERATION_FAILED`＋`CONTINUE_WITHOUT_FEATURED_MEDIA`となる（Amendment 2でT-15・T-16を、**Amendment 3でT-18〜T-20を除外**）。**CONTINUE となる reason が4値ちょうどであり、それ以外の5 reasonでは一切CONTINUEにならないことを網羅検証する** |
| `UNCLS-` | **（Amendment 3新設、M3-1・m3-A対応）** `INVALID_RESPONSE`（T-18・T-19）と `UNKNOWN`（T-20）が`UNCLASSIFIED`＋`PROPAGATE_ORIGINAL_ERROR`となること。**`IMAGE_GENERATION_FAILED` へ落ちないこと**（回帰防止）。あわせて未知reason・reason属性欠落・2型以外のExceptionも同一 Category へ落ちること（`UNCLASSIFIED` の3系統、10.7節 C-16）を確認する |
| `REJECT-` | **（Amendment 2新設、M2-1対応）** `REQUEST_REJECTED` を持つ `OpenAIImageGenerationError` が `IMAGE_GENERATION_REQUEST_REJECTED`＋`PROPAGATE_ORIGINAL_ERROR` となること。T-15（invalid request）・T-16（content policy）のいずれのmessage文言でも結果が同一であること（message非解析の証明）。**`IMAGE_GENERATION_FAILED` へ落ちないこと**（回帰防止） |
| `PROP-` | 伝播対象：T-13・T-14（`IMAGE_GENERATION_NOT_AUTHORIZED`）、**T-15・T-16（`IMAGE_GENERATION_REQUEST_REJECTED`）**、**T-26（`MEDIA_UPLOAD_FAILED`）**、T-8・T-9・T-21〜T-25・T-27〜T-29（`UNCLASSIFIED`）がすべて`PROPAGATE_ORIGINAL_ERROR`となる |
| `WPUP-` | **（Amendment 1新設、B-1対応）`WordPressMediaUploadError` が、messageの内容（HTTP 401／403／500／network文言等）に関わらず**常に**`MEDIA_UPLOAD_FAILED`＋`PROPAGATE_ORIGINAL_ERROR`となること。message文字列を変えても結果が変わらないことを複数パターンで検証（message非解析の証明） |
| `REASON-` | `OpenAIImageGenerationErrorReason`の**全9値**それぞれに対する決定が10.3節と一致する（網羅）。**Amendment 3後の内訳は 4値→`IMAGE_GENERATION_FAILED`／1値（REQUEST_REJECTED）→`IMAGE_GENERATION_REQUEST_REJECTED`／2値→`IMAGE_GENERATION_NOT_AUTHORIZED`／2値（INVALID_RESPONSE・UNKNOWN）→`UNCLASSIFIED` であり、9値が 4/1/2/2 で過不足なく4 Categoryへ被覆されることを検証する** |
| `NOPARSE-` | **（Amendment 3新設）** message・provider response・exception本文を解析していないことの behavioral 証明。同一 reason／同一例外型に対し、message を大きく変えても（HTTPステータス文字列・provider固有コード・日本語／英語・空文字を含む）決定が完全に一致することを、`REJECT-`／`WPUP-`／`UNCLS-` の各対象について確認する |
| `UNK-` | 未知の`Exception` subclass（テスト内定義の独自例外）・`ModuleNotFoundError`・`AttributeError`等が`UNCLASSIFIED`＋`PROPAGATE_ORIGINAL_ERROR`となる |
| `DEFENSE-` | `reason`属性を持たない／`reason`が`OpenAIImageGenerationErrorReason`のmemberでない手組み`OpenAIImageGenerationError`が`UNCLASSIFIED`へ倒れ、**ValueErrorを送出しない**こと（13.4節） |
| `TYPEERR-` | `Exception`でない入力（`None`／`str`／`BaseException`直系instance）で`TypeError`＋固定message完全一致 |
| `BASE-` | `KeyboardInterrupt`／`SystemExit`のinstanceが`decide()`へ渡された場合に`TypeError`となり、**決定として扱われない**こと（T-33〜T-35のContract化） |
| `PURE-` | 同一入力に対する2回の呼び出しが`==`かつ`hash()`一致（pure decision） |
| `SEC-` | `repr`／`str`／`asdict`／`astuple`の出力に、渡した例外のmessage断片・secret marker文字列が含まれないこと。**渡した例外objectがDecisionから到達不能であること**。**`action` が `asdict`／`astuple`／`repr` に現れないこと** |
| `NOEXC-` | AST検証：`ast.ExceptHandler`が0件・`ast.Raise`が`TypeError`送出1箇所のみ・`raise ... from ...`（`ast.Raise.cause`非None）が0件・`__post_init__`が存在しないこと |
| `DEP-` | AST検証：9.3節の禁止importを1件も行わないこと。module-levelで`os`／`logging`／`requests`／`socket`をimportしないこと。**汎用型（`ImportError`等）への`isinstance`判定が存在しないこと**（m-1対応） |
| `IMPORT-` | **clean subprocess**で本packageのみをimportし、`sys.modules`に`openai`が現れないことを決定的に検証（v6.18 precedent。3.7節 S-9によりopenai未インストール環境でも成立） |
| `SOCKET-` | test本体プロセス内で`socket.getaddrinfo`／`socket.socket.connect`をpatchし、import〜`decide()`全呼び出しで一度も呼ばれないことを検証（in-process検証であることを明示） |
| `RUNTIME-` | Runtime Zero Diff：`main.py`／`src/image_resolver.py`／`src/outputs/*.py`／`src/pipeline/*.py`／`scripts/*.py`が本packageを参照しないことの静的テキストGuard |
| `COMPAT-` | v6.9〜v6.18のPublic APIが不変であること（`__all__`比較・主要symbolの存在確認）。**特に`WordPressMediaUploadError`に`reason`属性が追加されていないこと**（N-17の遵守確認） |
| `ENV-` | 環境変数（`OPENAI_API_KEY`／`WP_*`／`AI_IMAGE_GENERATION_ENABLED`）を一切設定せずに全Scenarioが成立すること。`os.environ`が本package実行前後で不変であること |

### 21.3 外部接続ゼロ・実credential不要の保証方針

```text
・本packageは外部I/Oを行わないため、例外objectはすべてテスト内で直接構築する
    OpenAIImageGenerationError("<fixed message>", OpenAIImageGenerationErrorReason.TIMEOUT)
    WordPressMediaUploadError("<fixed message>")
  → 実API呼び出し・実HTTP・実課金は一切発生しない
・openai未インストール環境（3.7節 S-9）で全件PASSすること自体をIMPORT-で検証する
・skipを一切用いない（v6.18 Amendment 1 D-B3の方針を継承）。全ScenarioがPASSまたは
  FAILへ確定する
```

### 21.4 Secret marker検証の方法

```text
テスト内で、識別可能なmarker文字列を含む message を持つ例外を構築する。
  例: WordPressMediaUploadError("HTTP 401 (code=rest_cannot_create, message=SECRETMARKER)")
その例外を decide() へ渡し、戻り値について次を確認する。
  ・repr(decision) に "SECRETMARKER" が含まれない
  ・str(decision) に含まれない
  ・str(dataclasses.asdict(decision)) に含まれない
  ・str(dataclasses.astuple(decision)) に含まれない
  ・decision の全属性を走査して、渡した例外オブジェクトそのものへ到達できない

この同じ例外は WPUP- Scenario でも使用し、message に "401" を含んでいても
結果が MEDIA_UPLOAD_FAILED ＋ PROPAGATE_ORIGINAL_ERROR で不変であることを確認する
（message非解析の証明を兼ねる）。
```

### 21.5 Formal Regression Strategy

```text
・方式：累積Regression Inventory（v6.15.0以降のprecedentを継承）
・v6.18.0時点の正式Inventoryは21ファイル（既存20ファイル 2644/2644 PASS ＋
  v6.18新規 146/146 PASS ＝ 総合 2790/2790 PASS）
・本Release候補の正式Inventoryは、上記21ファイル ＋ 新規v6.19 E2E 1ファイル＝
  **22ファイル**（候補）
・実行方法：`tests/test_e2e_*.py` 全件（実在70ファイル）の無差別実行ではなく、
  既存Release precedentに基づく正式Inventoryの個別実行
・判定基準：既存21ファイルのbaseline（2790/2790 PASS）完全維持 ＋ 新規E2E全件PASS。
  FAIL 0・Warning 0・skip 0・外部API実接続0・終了コード0
・使用Python：projects/03_game_content_ai/venv/Scripts/python.exe
```

### 21.6（Amendment 2新設、S2-A対応）機械検証範囲と DI-4 へ委ねる範囲の分離

Architecture Review 2 Suggestion S2-A は、`PROPAGATE_ORIGINAL_ERROR` の契約のうち
「callerが元例外を無変換で再送出する」部分が DI-1 の E2E では検証できないことの
明示を求めた。本節で両者を分離する。

**本Release（DI-1）のE2Eで機械検証できる範囲**

```text
V-1  policy自身が例外をraiseしないこと
       検証手段: AC-11（TypeErrorが唯一の送出例外）＋ AC-14（ast.Raise が1箇所のみ、
                 ast.ExceptHandler が0件）＋ TYPEERR-／BASE- Scenario
V-2  Decision が正しい Action（PROPAGATE_ORIGINAL_ERROR）を返すこと
       検証手段: PROP-／REJECT-／WPUP-／UNK-／DEFENSE- Scenario、AC-8〜AC-10
V-3  raw exception を保持しないこと
       検証手段: SEC- Scenario（marker文字列非混入・例外objectへの非到達）、AC-19・AC-20
V-4  Failure Category と Action の写像が定義どおりであること
       検証手段: MAP-／REASON-／CAT- Scenario、AC-3・AC-12・AC-13
V-5  module-levelの分類表が実行時に書き換えられないこと
       検証手段: MAP- Scenario（呼び出し前後の不変性）、AC-28
```

**本Release（DI-1）のE2Eでは検証できない範囲 → DI-4 の責任**

```text
W-1  callerが捕捉した元例外を**無変換で再送出**すること
       （bare `raise` を用い、wrap・chaining・型変換・message加工を行わないこと）
W-2  再送出された例外を上位Runtimeがどう処理するか
       （記事1件の失敗として記録して次の記事へ進むのか、run全体を停止するのか）
W-3  DI-4が採用する try 範囲（prompt／filename構築を含めるか。N-20）
W-4  BaseException を捕捉しないこと（`except Exception` に限定すること）

これらは呼び出し側のコードに対する契約であり、本packageからは観測できない。
**DI-4 Runtime Wiring の Production Implementation／Code Review／E2E で
検証する契約とする。** 本Releaseは 13.3節（P-1〜P-3／Q-1〜Q-4）で
その契約内容を文書として確定させることまでを責務とする。

DI-4 のReviewerは、少なくとも次を確認すること（本Releaseからの申し送り）:
  ・`except Exception` であり `except BaseException` でないこと
  ・PROPAGATE_ORIGINAL_ERROR 分岐が bare `raise` であること
    （`raise exc` でも元例外は保たれるが、traceback の扱いが異なるため
      bare `raise` を推奨する）
  ・CONTINUE_WITHOUT_FEATURED_MEDIA 分岐で ArticleData を改変しないこと
```

---

## 22. Risks（Amendment 1で全面更新。R-1〜R-8の8件で統一：S-3対応）

| # | Risk | Amendment後Severity | Mitigation | Deferred可否 | Release前に閉じる必要 |
|---|---|---|---|---|---|
| **R-1** | **WordPress Media Upload失敗を全件 `PROPAGATE_ORIGINAL_ERROR` とするため、一過性のWP障害（HTTP 500・network断・429）でもfeatured media処理が継続されず、元例外が伝播する（可用性のトレードオフ）** | **中** | (a) 10.4節 C-5でトレードオフを明示的に受諾。configuration errorを隠さないこと（G-3・G-9）を可用性より優先する。(b) S-12〜S-14により「記事1件の失敗はrun全体を停止させない」ことは確認済み。(c) 分類精度の向上をDI-10として独立させ、**DI-4着手前の再検討を必須**とした（C-4） | **可**（DI-10へ。DI-4着手前の正式な再評価は必須（10.8節 ORD-1）だが、現契約を受容する場合はDI-10未完了でもDI-4へ進めてよい（ORD-2）。ORD-3・ORD-4に該当する場合に限りDI-10の完了が前提となる） | **不要**（Amendment 1で契約として確定済み） |
| **R-2** | DI-6でretryが導入されると、T-26等の判断が再評価を要する | 低 | 19章 RB-6に明記。本Releaseのcategory語彙はretryを含まないため、写像の変更のみで対応可能な構造にしてある | 可 | 不要 |
| **R-3** | 第2の画像生成Adapter追加時に、本packageへ isinstance 分岐の追加が必要 | 低〜中 | 9.4節 W-3で限定を明示。Categoryはprovider中立のため、追加は分岐1件で済む。DI-2導入時に共通基底例外型を検討する余地を残す | 可 | 不要 |
| **R-4** | **（Amendment 2で全面再定義、S2-B対応）`REQUEST_REJECTED` バケットの粒度不足。** v6.11 は `BadRequestError`（Content Policy拒否・パラメータ不正）・`NotFoundError`（**model不存在・model提供終了**）・`ConflictError`・`UnprocessableEntityError` を単一 reason へ集約するため、記事固有の失敗と全記事へ反復するsystemic failureを区別できない。現Releaseは安全側で**全件を元例外の伝播**とするため、**本来継続可能なContent Policy拒否でも該当記事のfeatured media処理が中止される可用性低下**が生じる | **中**（Amendment 1時点の「低」から引き上げ。M2-1が指摘したsystemic failure混在が判明したため） | (a) 10.6節 C-10で可用性トレードオフを明示的に受諾。「安全に分類できない失敗をfallbackへ倒さない」（G-9）を可用性より優先する。(b) 独立Category `IMAGE_GENERATION_REQUEST_REJECTED` を設けたことで、DI-11完了後に一部reasonを CONTINUE へ移す変更が加算的に行える（C-12）。(c) 18章の観測契約により当該Categoryが必ず記録される | **可**（DI-11へ。DI-4着手前の正式な再評価は必須（10.8節 ORD-1）だが、現契約を受容する場合はDI-11未完了でもDI-4へ進めてよい（ORD-2）。ORD-3・ORD-4に該当する場合に限りDI-11の完了が前提となる。10.6節 C-9・10.8節） | **不要**（Amendment 2で契約として確定済み） |
| **R-5** | `PROPAGATE_ORIGINAL_ERROR` 決定時に、upload成功後の失敗（T-28）ならWordPress上に未使用Mediaが残る | 低 | DI-7の領域（19章 RB-7、N-8）。本Releaseは検出も削除も行わないことをContractとして明示 | 可 | 不要 |
| **R-6** | v6.11 が `OpenAIImageGenerationErrorReason` へ値を追加した場合、本packageの写像更新が必要 | 低 | `OpenAIImageGenerationErrorReason` は `__all__` 公開のPublic APIである。AC-13の**全9値網羅検証**により、値追加時にE2Eが検知する。v4.4.0 `retry_outcome_terminality` の「恒久ルール」と同型の追従義務（S-17） | 可 | 不要 |
| **R-7** | **（Amendment 3で再構成。S3-A統合）CONTINUE側に残る4 reasonの残存リスクと、CONTINUE経路の限定に伴う価値の希薄化。** (i) Amendment 3後、CONTINUE となる reason は9値中**4値**（TIMEOUT／CONNECTION／RATE_LIMIT／SERVER_ERROR）に限定された。この4値の「一過性」は**保証ではなく、現行の分類粒度（v6.11 `_classify_api_error()` が `APITimeoutError`／`APIConnectionError`／`RateLimitError`／`InternalServerError` を個別判定していること）に依存する判断**である。v6.11 が分類を変更した場合、あるいは運用上これらにも systemic failure（例：特定モデルが恒常的に 500 を返す）が混入すると判明した場合、CONTINUE 判定の見直しを要する。(ii) また CONTINUE 経路が1 Category・4 reason に限定されたことで、「policyの価値が薄い／bool 1個で足りる」と見なされうる | **中**（Amendment 2の「低〜中」から引き上げ。B-1・M2-1・M3-1 と3回連続で「CONTINUE側に分類不能な失敗が混在していた」ことが判明しており、残る4 reasonについても同種の見直しが起こりうるため） | (a) 10.3節で「必ず一過性である」とは主張せず「現行分類上、一過性と積極的に判断する対象」と正確に記載した。(b) **allow-list 方式への転換（10.7節 C-17）により、v6.11 が reason を追加しても新値は自動的に安全側へ落ちる**。見直しが必要になるのは既存4値の性質が変わった場合に限定される。(c) 18章の観測契約により `IMAGE_GENERATION_FAILED` が記録され、DI-5 実装後は継続判定の妥当性を運用データで検証できる。(d) 価値の観点は11.7節 理由1〜4（特に理由4：異なるActionの表現にはCategory分割がPublic API上必然）で立証済み | **可**（DI-11 および DI-5 の運用データを踏まえた再評価へ） | **不要**（Amendment 3で残存リスクとして明示記録済み。ただし10.8節 ORD-1 の再評価対象に含める） |
| **R-8** | **（Amendment 1で差し替え）** `action` が derived property であるため `repr`／`asdict`／`astuple` に現れず、呼び出し側がDecisionをそのまま記録・serializeするとActionが欠落する | 低 | 12.3節・17.2節で明示。DI-5がloggingを実装する際は `decision.category` と `decision.action` を個別に取得する必要がある旨をContractとして先に固定した（18.1節 O-2・O-3） | 可 | 不要 |

---

## 23. Acceptance Criteria（Amendment 1で更新）

```text
AC-1   src/image_generation_fallback_policy/ が新規作成され、__all__ が
       11.2節の4 symbolのみである

AC-2   ImageGenerationFallbackAction が CONTINUE_WITHOUT_FEATURED_MEDIA /
       PROPAGATE_ORIGINAL_ERROR の2値のみを持つ

AC-3   ImageGenerationFailureCategory が IMAGE_GENERATION_FAILED /
       IMAGE_GENERATION_REQUEST_REJECTED / IMAGE_GENERATION_NOT_AUTHORIZED /
       MEDIA_UPLOAD_FAILED / UNCLASSIFIED の5値のみを持つ
       （ENVIRONMENT_ERROR は存在しない）

AC-4   ImageGenerationFallbackDecision が @dataclass(frozen=True) であり、
       dataclasses.fields() が category の1件のみを返す。
       action は property であり field ではない

AC-5   decide_image_generation_fallback() が module-level function として存在し、
       引数を1件（error）のみ取る

AC-6   decide() が常に ImageGenerationFallbackDecision を返し、None を返さない

AC-7   decide() が同一入力に対し常に等しい（== かつ hash() 一致）結果を返す

AC-8   CONTINUE_WITHOUT_FEATURED_MEDIA となるのは、error が
       OpenAIImageGenerationError であり、かつ reason が次の**4値**の
       いずれかである場合**に限る**（allow-list）
         TIMEOUT / CONNECTION / RATE_LIMIT / SERVER_ERROR

AC-8c  INVALID_RESPONSE および UNKNOWN は UNCLASSIFIED ＋
       PROPAGATE_ORIGINAL_ERROR となり、IMAGE_GENERATION_FAILED へ落ちない
       （Amendment 3、M3-1・m3-A対応）。
       分類は allow-list 方式であり、v6.11 が reason を追加した場合も
       新しい値は自動的に UNCLASSIFIED（＝PROPAGATE）へ落ちる

AC-8b  REQUEST_REJECTED を持つ OpenAIImageGenerationError は
       IMAGE_GENERATION_REQUEST_REJECTED ＋ PROPAGATE_ORIGINAL_ERROR となり、
       IMAGE_GENERATION_FAILED へ落ちない。messageの文言（Content Policy相当か
       model不存在相当か）を変えても結果が変わらない（message非解析の証明）

AC-9   上記以外のすべての Exception に対し PROPAGATE_ORIGINAL_ERROR を返す

AC-10  **WordPressMediaUploadError は message の内容に関わらず常に
       MEDIA_UPLOAD_FAILED ＋ PROPAGATE_ORIGINAL_ERROR となる
       （message文字列を変えても結果が変わらないことを複数パターンで検証。
        message非解析の証明）**

AC-11  error が Exception のinstanceでない場合に TypeError（固定message完全一致）を
       送出する。これが本packageが送出する唯一の例外である

AC-12  _ACTION_BY_CATEGORY が ImageGenerationFailureCategory の全memberを
       鍵として持つ（網羅性）。未登録キーへの丸め込み（.get(default)）を行わない

AC-13  OpenAIImageGenerationErrorReason の全member（9値）について
       decide() の結果が Decision Table と一致する（網羅検証。R-6 追従義務の担保）。
       Amendment 3後の内訳は **4 / 1 / 2 / 2** である。
         4値（TIMEOUT / CONNECTION / RATE_LIMIT / SERVER_ERROR）
                                  → IMAGE_GENERATION_FAILED
         1値（REQUEST_REJECTED）  → IMAGE_GENERATION_REQUEST_REJECTED
         2値（AUTHENTICATION / PERMISSION_DENIED）
                                  → IMAGE_GENERATION_NOT_AUTHORIZED
         2値（INVALID_RESPONSE / UNKNOWN）
                                  → UNCLASSIFIED
       （注記：DI-11 が reason を細分化した時点で本ACは既知差分として
        更新対象となる。20章 DI-11 参照）

AC-14  本packageが try／except を持たない（AST検証で ast.ExceptHandler が0件）。
       ast.Raise は TypeError 送出の1箇所のみであり、raise ... from ... を
       使用しない（ast.Raise.cause が全件 None）。__post_init__ を定義しない

AC-15  本packageが新規例外型・新規Protocolを定義しない
       （公開するclassは Enum 2件と frozen dataclass 1件のみ）

AC-16  本packageが9.3節の禁止importを1件も行わない（AST検証）。
       os / logging / requests / socket を module-level でimportしない。
       汎用型（ImportError 等）への isinstance 判定を行わない

AC-17  本packageのimportが openai をimportしない（clean subprocess による
       決定的検証）。openai 未インストール環境で全E2Eが成立する

AC-18  本packageのimportおよび decide() の全呼び出しが、socket.getaddrinfo /
       socket.socket.connect を1度も呼ばない（in-process検証）

AC-19  decide() が返した Decision について、repr / str / asdict / astuple の
       いずれの出力にも、入力例外のmessage断片が含まれない。
       また action がこれらの出力に現れない

AC-20  decide() が返した Decision から、入力例外オブジェクトへ到達できない

AC-21  KeyboardInterrupt / SystemExit のinstanceを渡した場合、決定は返されず
       TypeError となる

AC-22  reason 属性を持たない／未知値である OpenAIImageGenerationError に対し、
       ValueError を送出せず UNCLASSIFIED ＋ PROPAGATE_ORIGINAL_ERROR を返す

AC-23  main.py / src/image_resolver.py / src/outputs / src/pipeline / scripts の
       いずれも本packageを参照しない（静的検証）

AC-24  v6.9〜v6.18の Public API・例外型・例外message・signature・戻り値型が
       すべて不変である（無改修）。特に WordPressMediaUploadError に
       reason 属性が追加されていない（N-17の遵守）

       **【Amendment 2追加、m-C対応：DI-10実施時の既知差分についての注記】**
       本AC（および対応する COMPAT- Scenario）は、
       「WordPressMediaUploadError に reason 属性が存在しない」という
       **本Release時点の事実**をArchitecture Guardとして固定するものである。
       Deferred Item DI-10 が実施され v6.9 へ reason 分類Enumが追加された時点で、
       本ACおよび対応E2Eは**必然的にFAILする**。

       これは docs/CHANGELOG.md の [KI-3]（v3.1.0テストの「retry_engine無改修」
       チェックがv3.2.0以降でFAILする）および [KI-4]（v3.4.0 Scheduler Wiringにより
       v2.7.0〜v3.3.0の一部Architecture GuardがFAILする）と**同種の
       「設計上の既知差分」**である。両KIエントリが確立した運用方針に従い、
       次を本ReleaseのContractとして明記する。

         ・DI-10 実施時、AC-24 および COMPAT- Scenario は
           **既知差分として更新対象**である
         ・そのFAILを**無関係なRegressionとして扱ってはならない**
         ・本Release時点では、v6.9 が無改修であるという現状契約を固定する目的で
           有効であり、削除・緩和しない

       （本注記はCHANGELOG自体を変更するものではない。CHANGELOGへの
        既知差分エントリ追加の要否は、DI-10 の Documentation Integration工程で
        判断する）

AC-25  環境変数を一切設定せずに全E2Eが成立し、実行前後で os.environ が不変である

AC-26  requirements.txt / .env.example / main.py が無変更である

AC-27  正式Regression Inventory（22ファイル候補）が全件PASSし、既存21ファイルの
       baseline（2790/2790 PASS）が完全に維持される

AC-28  **（Amendment 2追加、m-A対応。Amendment 3で対象拡張）** 本packageが実行時に
       _ACTION_BY_CATEGORY および _CONTINUABLE_REASONS を書き換えない。
       AST検証で、module-level以外でのこれらへの代入・添字代入・
       .update()／.pop()／.clear()／.setdefault()／.add()／.discard() 呼び出しが
       0件であることを確認する。あわせて decide() 呼び出しの前後で
       両者の内容が不変であることをE2Eで確認する（MAP- Scenario）

AC-29  **（Amendment 3追加、M3-2対応）** DI-10／DI-11 と DI-4 の順序契約が
       設計書上で一義に追跡できる。具体的には次を満たす。
         (a) 10.8節に O-1〜O-4 として判定規則が記載されている
         (b) 「再評価は必須」と「完了が前提となる条件」が明確に区別されている
         (c) 10.4節 C-4・10.6節 C-9・20章 Deferred Items・20章 DI-4行・
             26章 ROADMAP更新計画・22章 R-1／R-4・29章 Checklist の
             いずれの記述も 10.8節 ORD-1〜ORD-4 と矛盾しない
       本ACは文書レビューで判定する（E2Eの対象外。v6.18 RZ-4と同じ扱い）
```

---

## 24. Backward Compatibility

| # | 対象 | 影響 |
|---|---|---|
| BC-1 | v6.9 `wordpress_media` | **なし**（無改修。`WordPressMediaUploadError`をimportするのみ。**reason Enumは追加しない**＝N-17） |
| BC-2 | v6.10 `ai_image_generation` | **なし**（import もしない） |
| BC-3 | v6.11 `openai_image_generation` | **なし**（無改修。`OpenAIImageGenerationError`／`OpenAIImageGenerationErrorReason`をimportするのみ） |
| BC-4 | v6.12〜v6.18 | **なし**（無改修） |
| BC-5 | `main.py`以下のRuntime | **なし**（Consumer-less継続。動作は完全に同一） |
| BC-6 | 既存環境変数 | **なし**。新規追加・意味変更・既定値変更のいずれもなし |
| BC-7 | 既存テスト | **なし**。既存E2E全件が無改修でPASSする想定（AC-27で検証） |
| BC-8 | `requirements.txt` | **なし**（dependency追加なし） |
| BC-9 | dataclass equality／repr | **なし**（既存dataclassを一切変更しない） |
| BC-10 | Gate OFF behavior／Gate ON construction behavior | **なし**（15章。本packageはGate状態を参照しない） |

```text
追加（Addition）      : image_generation_fallback_policy パッケージ全体（新規）
変更（Modification）  : なし
破壊的変更（Breaking）: なし
```

---

## 25. Runtime Zero Diff

### 25.1 変更しないファイル

```text
main.py
src/image_resolver.py
src/outputs/（全ファイル）
src/pipeline/（全ファイル）
src/ai/（全ファイル）
src/scheduler/ / src/workflow_engine/ / src/execution_history/ / src/workflow_monitor/
src/retry_*（全パッケージ）
src/logger/ / src/analytics/
src/ai_image_generation/ / src/openai_image_generation/ / src/wordpress_media/ /
    src/generated_image_wordpress_media/ / src/article_featured_media/ /
    src/article_featured_media_orchestration/ / src/image_generation_config/ /
    src/generated_image_filename_policy/ / src/article_image_prompt_construction/ /
    src/article_featured_media_composition/
scripts/（全ファイル）
既存publish実行順序（main.py 記事ループ）
requirements.txt
.env.example  ★新規環境変数がないため変更不要（N-14）
```

### 25.2 変更するファイル（Production Code候補）

```text
新規  src/image_generation_fallback_policy/__init__.py
新規  src/image_generation_fallback_policy/image_generation_fallback_policy.py
新規  tests/test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py
更新  docs/design/image_generation_fallback_policy_foundation.md（本文書）
```

**既存Production Codeへの変更は1件も無い。** これはv6.18（v6.11へ`output_mime_type`を
追加した）より更に小さいdiffである。Amendment 1のB-1対応でv6.9へreason Enumを追加する
案(i)を検討したが、v6.9のPublic API変更とE2E再検証を伴うため採用せず、DI-10へ
Deferredした（10.4節）。この判断により Runtime Zero Diff は完全に維持される。

### 25.3 Runtime Zero Diffの証明方針

| # | 検証 | 方法 |
|---|---|---|
| RZ-1 | Runtime対象ファイルが本packageをimportしていない | v6.17／v6.18 precedentの静的テキスト参照Guard（21.2節 `RUNTIME-`） |
| RZ-2 | 本packageが禁止importを行っていない | AST解析による依存Guard（`DEP-`） |
| RZ-3 | 既存packageが無改修であること | `COMPAT-` によるPublic API不変検証 ＋ Formal Regression |
| RZ-4 | 実バイト差分 | `git diff --stat` により変更ファイルが25.2節の4件のみであることをRelease工程で確認（E2Eの対象外。v6.17／v6.18 precedentと同じ扱い） |
| RZ-5 | 既存publish動作の不変 | Formal Regressionにより正式Inventory全件PASSを確認 |

---

## 26. Documentation Integration Plan（将来工程の予告）

**本工程では実施しない（N-19）。** Architecture Review 2承認・実装・Code Review・
Formal Regression完了後の別工程で、次を更新する予定である。

```text
docs/ROADMAP.md
    ・Deferred Items「Image Generation Fallback Policy」Entryを [ ] → [x] へ更新し、
      実施内容・Review結果・E2E実績を追記
    ・「Article Featured Media Runtime Wiring」Entryの
      「画像生成のFallback Policy…は依然未着手であり、本Wiringへ直行できる状態には
        至っていない」という記述を、DI-1完了を反映した表現へ更新。
      あわせて**（Amendment 3、M3-2対応で一義化）DI-10／DI-11 の必要性と
      可用性トレードオフの「正式な再評価」がDI-4着手の前提条件であること、
      および DI-10／DI-11 の「完了」が前提となるのは
      CONTINUE対象の拡大を望む場合または現在の可用性低下を受容できない場合に
      限られること**（10.8節 ORD-1〜ORD-4）を明記。
      「再検討必須」と「完了必須」を区別して記述する
    ・DI-10・DI-11をDeferred Itemsへ新規追加

docs/architecture.md
    ・「Image Generation Fallback Policy Foundation層
      （src/image_generation_fallback_policy/、v6.19.0 実装完了）」節を新設
      （既存の画像系Foundation節と同じ構成：Purpose／Package Boundary／Public API／
        Decision Table／Error Contract／Security Contract／Backward Compatibility／
        Out of Scope／Test Review・Code Review・Regressionの実績／Future Extension）
    ・Orchestration層・Composition Root層の「Future Extension」に列挙されている
      「Image Generation Fallback Policy」を実装済みへ更新

docs/CHANGELOG.md
    ・「## [v6.19.0] - YYYY-MM-DD ★ Image Generation Fallback Policy Foundation」を
      既存形式で追加

docs/design/image_generation_fallback_policy_foundation.md（本文書）
    ・Status欄を各工程の結果で更新
    ・Review History（30章）へ各Reviewの判定・Findingを追記
```

---

## 27. Rejected Alternatives（まとめ）

| 案 | 却下理由（要約） |
|---|---|
| A: adapter内部で吸収 | `AIImageGenerator` Protocol の破壊的変更を伴う。provider層に業務判断を持ち込む（8.3節） |
| B: fallback-aware decorator | upload失敗を扱えず、ROADMAPのDI-1定義の半分しか満たさない。DI-2先取り（8.3節） |
| C: Orchestrator改修 | silent failureになるか、戻り値型変更＝DI-3先取りになる。v6.14 E2Eへの大規模回帰（8.3節） |
| D: Composition Root／Runtime層で判断 | v6.18が明示除外した責務を覆す。DI-4先取り。Runtime Zero Diffと両立しない（8.3節） |
| 案2〜案5（実装時期） | 8.4節。案2・案3はRepositoryに前例がなく、案4は v2.1.0 という性質の異なる1件のみ、案5はFoundation Firstに反しblast radiusを最大化する |
| Null Object（no-op orchestrator）の導入 | v6.18が「Fallback Policy先取り回避」を理由に不採用としたものを、DI-1側から再導入するのは循環（4.2節） |
| `Decision(action, category)` の2 field | **（Amendment 1、M-3）** action は category の全域関数であり冗長。derived propertyへ変更（11.4節） |
| Category Enum自体に action property を持たせる（案β） | **（Amendment 1、M-3）** Enumに振る舞いを持たせる前例がRepositoryに存在しない（11.4節） |
| `ENVIRONMENT_ERROR` Category | **（Amendment 1、m-1）** 汎用 `ImportError` への過剰分類。Actionは `UNCLASSIFIED` と同一で業務判断上の差がない（10.2節 T-8） |
| `REQUEST_REJECTED` の全件 `CONTINUE` | **（Amendment 2、M2-1）** `NotFoundError`（model不存在・提供終了）が同一reasonへ集約されており、systemic failure を継続扱いにすると permanent silent degradation を生む（10.6節） |
| `REQUEST_REJECTED` を本Releaseで細分化 | **（Amendment 2、M2-1）** v6.11 `_classify_api_error()` の改修を伴い、N-12（v6.11無改修）とRuntime Zero Diffに反する。DI-11 へDeferred（10.6節 C-8・C-9） |
| `REQUEST_REJECTED` を `IMAGE_GENERATION_FAILED` のまま Action だけ変更 | **（Amendment 2）** action は category から導出される derived property であるため（11.4節）、同一 category が2つの action を持つことは構造的に不可能。Decision を2 fieldへ戻せば実現できるが、Review 1 M-3 の解決を撤回することになる。**異なるActionを必要とする以上、Category分割がPublic API上の必然である**（11.7節 理由4） |
| `_ACTION_BY_CATEGORY` の `MappingProxyType` 化 | **（Amendment 2、m-A）** Repository内に `MappingProxyType` の使用例が1件も存在せず、v4.4.0 の素のdict precedent から外れる。private かつ書き換え手段を公開していないため、記述の正確化で足りる（11.4.1節） |
| `UNKNOWN` の `CONTINUE` 維持 | **（Amendment 3、M3-1）** v6.11 `generate()` の `except Exception:` 経路が `TypeError`／`AttributeError`／`ValidationError`／SDK内部エラーを `UNKNOWN` へ落とすため、一過性障害と積極的に判定できない（10.7.1節） |
| `INVALID_RESPONSE` の `CONTINUE` 維持 | **（Amendment 3、m3-A）** provider または SDK の応答構造変更による systemic failure が同一reasonへ混入し、一過性を保証できない（10.7.3節） |
| `UNKNOWN`／`INVALID_RESPONSE` 用の新Category追加 | **（Amendment 3、C-18）** 必要なActionが既存 `UNCLASSIFIED` と同一であり、Amendment 1で `ENVIRONMENT_ERROR` を統合した際の基準（Actionが同一のCategoryは業務判断上の差を持たない）をそのまま適用する。観測上の区別が必要ならDI-5が例外型を別途記録すればよい |
| deny-list 方式（「特定reason以外は継続」）の維持 | **（Amendment 3、C-17）** v6.11 が reason を追加した際に新値が自動的に CONTINUE 側へ落ちる。安全側の既定を持たない構造であり、B-1・M2-1・M3-1 と同種の欠陥を将来再発させる（10.3節） |
| 「DI-10／DI-11の完了をDI-4着手の一律前提とする」 | **（Amendment 3、M3-2）** 現契約（安全側で全件伝播）をそのまま受容するなら DI-4 は安全に設計できるため、一律の完了前提は過剰であり Release 進行を不必要に阻害する。条件付き二段構え（10.8節 ORD-1〜ORD-4）とした |
| 「DI-10／DI-11は再検討のみで足り、完了が前提となる場合はない」 | **（Amendment 3、M3-2）** CONTINUE対象を拡大する場合は分類手段が不可欠であり、分類なしの拡大は permanent silent degradation の再導入になる（ORD-3）。完了が前提となる条件を明示的に残す必要がある |
| WordPress Upload失敗の `CONTINUE` | **（Amendment 1、B-1）** reason分類が存在せず、capability不足による403が permanent silent degradation を生む（10.4節） |
| v6.9 への reason Enum 追加を本Releaseで実施 | **（Amendment 1、B-1 案(i)）** v6.9のPublic API変更とE2E再検証を伴い、Runtime Zero Diffとscope最小化に反する。DI-10へDeferred（10.4節） |
| `Decision`を返さず`bool`／`Action`のみ返す | 失敗理由の観測手段が消滅し、G-2に違反（11.7節） |
| 例外messageを`Decision`へ保持 | `WordPressMediaUploadError`のmessageがprovider応答本文を含みうる（17.3節） |
| 例外型ではなくmessage解析で分類 | v6.11の固定message設計を無意味化し、v6.9のmessage可変性により脆弱（9.4節）。Architecture Review 1でも明示的に禁止された |
| 未知reasonに対する `ValueError` 送出（v6.6 precedent踏襲） | except節内から新例外を送出すると元例外を置き換え診断情報を破壊する（13.4節） |
| policyの環境変数設定化 | 本Releaseの消費者が存在せず、設定の妥当性を検証できない（N-16、Deferred） |

---

## 28. Resolved Questions（Q-1〜Q-7、Amendment 1ですべて確定）

| # | 論点 | 確定結果 | 根拠 | Architecture変更 |
|---|---|---|---|---|
| **Q-1** | `OpenAIImageGenerationError.reason` を読んで AUTHENTICATION／PERMISSION_DENIED を伝播側へ分岐するか | **確定：分岐する（reason-aware）** | 10.5節 根拠1〜5。Architecture Review 1でも「(a)を支持・承認」と判定された。`OpenAIImageGenerationErrorReason` は `__all__` 公開のPublic APIであり、secret-freeがv6.11設計で保証されている | なし |
| **Q-2** | provider結合をどう扱うか | **確定：具象adapter例外型2件をmodule-level importし、isinstance判定に用いる。ただし公開語彙はprovider中立に保つ** | 9.4節 V-1〜V-4／W-1〜W-4で保証範囲と限界を明示。共通基底例外型の導入（案(b)）は既存2 packageのPublic API変更を伴い本Releaseのscopeを超える。呼び出し側にcategoryを渡させる案(c)は9.5節の第2段正規化責務を放棄することになる | なし（表現をm-3対応で限定） |
| **Q-3** | `ImageGenerationFailureCategory` の最終値 | **確定（Amendment 2で更新）：5値**（`IMAGE_GENERATION_FAILED` / **`IMAGE_GENERATION_REQUEST_REJECTED`** / `IMAGE_GENERATION_NOT_AUTHORIZED` / `MEDIA_UPLOAD_FAILED` / `UNCLASSIFIED`）。**`ENVIRONMENT_ERROR` は削除したまま**（復活させない） | Amendment 1（m-1対応）で `ENVIRONMENT_ERROR` を削除：汎用 `ImportError` への isinstance が必要で過剰包含となり、Actionも `UNCLASSIFIED` と同一だったため。Amendment 2（M2-1対応）で `IMAGE_GENERATION_REQUEST_REJECTED` を新設：`IMAGE_GENERATION_FAILED` と**異なるActionを必要とする**ため、derived property設計を維持する以上Category分割が必然（11.7節 理由4）。5値の相互排他性・網羅性は11.7節で立証。**Amendment 3ではCategory値そのものを変更せず（5値のまま）、reason → Category の割り当てのみを変更した**（`INVALID_RESPONSE`・`UNKNOWN` を `IMAGE_GENERATION_FAILED` から `UNCLASSIFIED` へ移動。M3-1・m3-A対応）。reason 9値の最終分割は **4 / 1 / 2 / 2** | **あり**（初版5値 → Amendment 1で4値 → Amendment 2で5値。Amendment 3は5値を維持し、13.5節の分類アルゴリズムを deny-list から **allow-list** へ転換） |
| **Q-4** | `Decision` の invariant ／ `__post_init__` | **確定：`__post_init__` を持たない。** 初版INV-2〜INV-5は `_ACTION_BY_CATEGORY` の定義そのものとなり消滅。残る INV-1 は `decide()` が唯一の生成経路である限り構造的に成立 | 12.1節・12.2節。v6.4／v6.5／v6.6の結果objectがいずれも `__post_init__` を持たない（S-8）。手組みインスタンスの挙動はContract外とする点も同precedentに一致 | **あり**（M-3対応に従属） |
| **Q-5** | `Decision` に stage field を追加するか | **確定：追加しない** | 12.5節。Categoryから大半のstageが判別可能。field追加はDI-5の要件確定後に再検討する（18.1節 O-5） | なし |
| **Q-6** | `Decision` に retryable field を追加するか | **確定：追加しない** | 18.1節 O-4。retryabilityはDI-6の語彙であり先取りしない | なし |
| **Q-7** | package名称 | **確定：`image_generation_fallback_policy` を維持する** | 5.1節。ROADMAPの正式名称「Image Generation Fallback Policy」との一致による追跡性を優先。名称が Upload 失敗も対象とすることを表さない点は、5.1節 Terminology で明示的に説明する（S-2対応） | なし（Terminologyへ注記追加） |

**Public API・Failure Taxonomy・Error Contract・責任境界に関する未解決事項は存在しない。**

---

## 29. Architecture Review Checklist（Amendment 1後のセルフレビュー）

```text
[x] Release名とScopeが一致しているか
      → 一致。判断規則のみを定義し、捕捉・再送出・配線を含まない（7章 N-1〜N-3）。
        名称と実対象範囲の差は5.1節で明示（S-2対応）

[x] DI-1の意味をRepositoryの根拠から確定したか
      → 3.1節（ROADMAP原文）・3.2節（architecture.md 5箇所）を根拠に4章で確定。
        推測されうる5つの意味を4.2節で根拠付きで排除

[x] 実ファイル・symbol・行番号を根拠にしているか
      → 3章がすべて実読に基づく。Amendment 1でS-12〜S-17を追加実測

[x] Architecture Review 1のBlocking／Major／Minor／Suggestionをすべて反映したか
      → B-1（10.4節）・M-1（11.3節・13.3節）・M-2（8.4節）・M-3（11.4節）・
        m-1（Q-3）・m-2（10.2節 T-23/T-24・16.2節）・m-3（9.4節）・
        S-1（9.5節）・S-2（5.1節）・S-3（22章）。0.1節に対応表

[x] Architecture Review 2のMajor／Minor／Suggestionをすべて反映したか
      → M2-1（10.6節・T-15/T-16・11.3節・11.7節・13.5節・14章・21.2節 REJECT-・
        AC-3/AC-8/AC-8b・R-4・DI-11）・m-A（11.4.1節・11.5節・AC-28）・
        m-B（8.4節 J-3）・m-C（20章 DI-10・AC-24注記）・S2-A（21.6節）・
        S2-B（22章 R-4）。0.2節に対応表

[x] Architecture Review 3のMajor／Minor／Suggestionをすべて反映したか
      → M3-1（10.7節・T-20・13.5節 allow-list・AC-8c・UNCLS-）・
        m3-A（10.7.3節・T-18/T-19）・M3-2（10.8節 ORD-1〜ORD-4・C-4・C-9・
        20章・26章・AC-29）・S3-A（22章 R-7へ統合）。0.3節に対応表

[x] 安全に分類できない失敗をすべてPROPAGATE側へ倒したか
      → 倒した。WordPress Upload全件（10.4節）・REQUEST_REJECTED全件（10.6節）・
        **INVALID_RESPONSE・UNKNOWN（10.7節、Amendment 3）**・
        未知reason・未知例外（13.4節）。CONTINUE となるのは
        allow-listに列挙した4 reasonのみ（10.3節）。
        **分類方式をdeny-listからallow-listへ転換したため、
        v6.11がreasonを追加しても新値は自動的に安全側へ落ちる（C-17）**

[x] CONTINUE対象の性質を過大に主張していないか
      → していない。10.3節で「必ず一過性である」とは主張せず
        「現行の分類粒度において一過性と積極的に判断する対象」と限定し、
        見直し条件を22章 R-7へ残存リスクとして記録した

[x] DI-10／DI-11とDI-4の順序が一義か
      → 一義。10.8節 ORD-1〜ORD-4で「再評価は必須」と
        「完了が前提となる条件（ORD-3・ORD-4に限る）」を明確に区別した。
        C-4・C-9・20章・26章・R-1／R-4・AC-29で表現を統一済み
        （R-1／R-4のDeferred列はArchitecture Review 4 Finding m4-Bで補正）

[x] Architecture Review 4のMinor／Suggestionをすべて反映したか
      → m4-A（13.5節：_CONTINUABLE_REASONS をmodule-level配置と明示）・
        m4-B（22章 R-1／R-4のDeferred列をORD-1〜ORD-4へ統一）・
        m4-C（10.8節の判定規則IDをO-からORD-へ改称し、18.1節 O-1〜O-7との
        衝突を解消）はいずれもReview 4工程内で解消。
        S4-A（RATE_LIMITのquota枯渇観点をORD-1再評価スコープへ明記）・
        S4-B（4 CONTINUE reasonの構造的到達保証の明記）はNon-Blockingとして
        Production Implementation以降へ引き継ぐ

[x] CONTINUE対象4 reasonの発生源をProduction Codeで確認したか
      → 確認済み。TIMEOUT／CONNECTION／RATE_LIMIT／SERVER_ERROR はいずれも
        _classify_api_error() 内でのみ生成され、同関数は
        `except openai.APIError as exc:` からのみ呼ばれる。
        したがってこの4値は**構造的に openai.APIError subclass 由来に限定**され、
        programming error（TypeError等）は `except Exception` 経路の
        UNKNOWN へ落ちるため混入しない（Architecture Review 4で実測確認）

[x] CategoryとActionの写像が構造的に一意か
      → 一意。action は _ACTION_BY_CATEGORY[category] の直接subscriptで導出され、
        5 Categoryすべてが登録されている（AC-12）。同一Categoryが
        複数Actionを持つ状態は構造的に存在しない

[x] provider固有の例外名を、installed SDKと既存adapterを確認してから記載したか
      → 既存adapter（_classify_api_error()）から読み取った。
        **installed SDKによる再確認は不可能である（venvに openai 未インストール、
        S-9）ことを明記した。** 分類には openai.* を用いない（9.4節 V-4）

[x] Fail Fastとの整合を明文化したか
      → 14章で8要求に個別回答。Amendment 1で要求8（G-9）を追加

[x] configuration／credential／permission errorをgraceful fallbackで隠していないか
      → 隠していない。T-3〜T-7は構築時（policy未到達）、T-13・T-14・**T-26全件**は
        PROPAGATE_ORIGINAL_ERROR。provider横断で単一原則が成立（10.5節 根拠5）

[x] 分類できない失敗をfallbackへ倒していないか
      → 倒していない。UNCLASSIFIED・MEDIA_UPLOAD_FAILED はいずれも伝播（G-9）

[x] fallbackをsilent successにしていないか
      → 12.4節。Decisionは成功を表す値を持たず、生成自体が失敗の発生を意味する

[x] ExceptionとBaseExceptionを混同していないか
      → T-33〜T-35で分離。BaseException直系は TypeError となり決定を返さない（AC-21）

[x] broad catchを採用していないか
      → 本package自身は try／except を1つも書かない（AC-14）。
        呼び出し側の except Exception は S-15（既存Pipeline層）と同型であり
        Repositoryのパターンから逸脱しない

[x] 新規例外型を増やしていないか
      → 増やしていない。送出するのは標準 TypeError 1種のみ（13.1節）

[x] Public APIを必要以上に増やしていないか
      → 4 symbol。Amendment 1でDecisionの保存fieldを2→1へ削減し、
        Amendment 1でDecisionの保存fieldを2→1へ削減しCategoryを5→4値へ削減、
        Amendment 2で異なるActionの表現に必要な1値のみを追加し4→5値とした
        （11.7節 理由4）。削減案・追加案はいずれも11.4節・11.4.1節・11.7節で個別検討

[x] Action の意味が一義に定まっているか
      → 11.3節 docstring・13.3節（P-1〜P-3／Q-1〜Q-4）・16.2節・AC-9で一貫。
        run制御を決定しないことを4.2節・9.2節 R-13・N-21で明示

[x] Category と Action の不整合が構造的に発生しないか
      → 発生しない。action は derived property であり、
        _ACTION_BY_CATEGORY が唯一の定義である（11.4節）

[x] DI-2〜DI-7・DI-9・DI-10を先取りしていないか
      → 20章。DI-2は「不要」であることを明示。DI-10は新規Deferred Itemとして正式化し、
        DI-4着手前の再検討を必須とした

[x] Runtime Wiringを実装していないか
      → 実装していない。25章 Runtime Zero Diff。既存Production Code変更0件

[x] 過剰な抽象化を避けているか
      → policy差し替え機構・Protocol・設定読み込み・Evaluator classをいずれも不採用

[x] Security保証の範囲を限定して述べているか
      → 17.2節。「decide()が返したインスタンス単体のserializationに限る」と限定。
        action が repr／asdict に現れないことも明示（R-8）

[x] 既存precedentから逸脱する箇所を明示し、理由を述べたか
      → 13.4節（v6.6のValueError送出方針からの逸脱理由）・
        9.5節（生Exceptionを入力とする理由と正規化2段構成）で明示

[x] 未確定事項を実装者判断へ丸投げしていないか
      → Q-1〜Q-7はすべて28章で確定済み。未解決のOpen Questionは存在しない

[x] Test Strategyが外部接続ゼロ・実credential不要で全Contractを検証できるか
      → 21章。21 prefix。openai未インストール環境での成立をIMPORT-で検証。skipなし。
        WPUP- でmessage非解析を証明

[x] Acceptance Criteriaが検証可能な形か
      → 23章 AC-1〜AC-27。すべてテストまたは静的検査で客観的に判定可能

[x] 本工程で設計書1ファイル以外を変更していないか
      → 変更なし（Architecture Design時・Architecture Amendment 1時のいずれも
        git statusにより確認）
```

---

## 30. Review History

```text
2026-07-27  Repository Survey 実施（読み取り専用、基準commit c9c9f34）
              調査対象:
                docs/ROADMAP.md（DI-1正式記述・Deferred Items全体）
                docs/architecture.md（Orchestration層／Gate層／Filename Policy層／
                                      Prompt Construction層／Composition Root層）
                docs/design/article_featured_media_composition_root_foundation.md
                docs/design/article_image_prompt_construction_foundation.md
                Production Code: 画像系10 package全ソース／policy・decision precedent群／
                                 main.py／src/image_resolver.py／src/outputs/
                tests/test_e2e_v6_18_0_*.py（E2E形式・prefix規則）
                requirements.txt ／ venv実測（pip list）
              主要な発見:
                ・DI-1の意味はROADMAP・architecture.mdで一貫（4章で確定）
                ・「fallback」の語がRepository内に既存し、意味が異なる（3.3節）
                ・実行時失敗は専用例外2種に集約されている（3.4節）
                ・OpenAI側にはsecret-freeなreason Enumがあり、WordPress側には無い（3.5節）
                ・featured_media_id=0 による「画像なし投稿」経路が既存Runtimeに存在（2.1節 P-4）
                ・venvに openai が未インストール（3.7節 S-9）

2026-07-27  Architecture Design（本文書初版）作成
              → Architecture Review 1 実施へ

2026-07-27  Architecture Review 1 実施
              判定: Changes Required
              Blocking: 1 / Major: 3 / Minor: 3 / Suggestion: 3

              Blocking:
                B-1  WordPress Media Upload失敗を安全に分類できないまま
                     全件 CONTINUE としており、Error Contractが内部矛盾している。
                     初版の緩和策（WordPressOutputとの環境変数共有により
                     credential誤りは記事投稿も失敗させる）は、
                     upload_files capability のみ欠落した403の場合に成立せず、
                     permanent silent degradation を許す

              Major:
                M-1  ABORT_ARTICLE の意味が未定義（伝播／記事単位中断／run停止の
                     3義が併存）。Decision が例外への参照を持たないため、
                     利用例どおり実装すると元例外が握り潰される
                M-2  consumer-less Public APIを先行実装する是非（5案）の比較が
                     設計書に存在しない
                M-3  Decision の category / action 2 field は、設計書自身の
                     INV-2〜INV-5 が示すとおり action が category の全域関数であり冗長

              Minor:
                m-1  ENVIRONMENT_ERROR が汎用 ImportError を過剰分類する
                m-2  T-23・T-24（prompt／filename失敗）が §16.2 の利用例では
                     try 範囲外であり到達しない
                m-3  「provider非依存」が §9.4 の限定と不整合な過大表現

              Suggestion:
                S-1  生Exceptionを入力とする分類器はRepositoryに前例がない。
                     正規化責任層を明記すべき
                S-2  package名称がUpload失敗も対象とすることをTerminologyへ注記すべき
                S-3  Riskの番号を統一すべき

              Architecture本体（責務配置 案E＝独立policy component・
              Consumer-less方針・Runtime Zero Diff・reason-aware分岐＝Q-1・
              secret非保持方針・BaseException除外）は妥当と判定され、変更を要しない。

2026-07-27  Architecture Amendment 1 実施（本工程）
              → Architecture Review 1のB-1・M-1〜M-3・m-1〜m-3・S-1〜S-3すべてに対応。
                Production Code・test code・既存文書への変更は行っていない
                （対象は本設計書1ファイルのみ）。

              主要Decision:
                D-A  【B-1】WordPress Media Upload失敗を全件
                     PROPAGATE_ORIGINAL_ERROR とする（10.4節 C-1〜C-5）。
                     v6.9へのreason Enum追加は行わず、DI-10として正式なDeferred Itemへ。
                     **DI-4 Runtime Wiring着手前の再検討を必須条件として明記**。
                     可用性トレードオフ（一過性WP障害でも伝播）をC-5で明示的に受諾
                D-B  【M-1】Action を CONTINUE_WITHOUT_FEATURED_MEDIA /
                     PROPAGATE_ORIGINAL_ERROR へ改名・再定義（11.3節・13.3節）。
                     PROPAGATE は「policyがraiseする」意味ではなく
                     「callerが元例外を無変換で再送出する」意味であることを、
                     Enum docstring・Decision Table・利用例・Error Contract・ACで統一。
                     run制御を決定しないことをR-13・N-21で明示。
                     判定根拠としてS-12〜S-15（OutputManager／main.py／Pipelineの
                     実際の失敗処理）を新たに実測・記録
                D-C  【M-2】8.4節を新設し実装時期5案を7観点で比較。
                     案1（Public先行実装）を維持。根拠J-1〜J-4。
                     特にJ-3（Amendment後は変更が加算的方向に限られるため
                     早期固定リスクが構造的に小さい）を新たな根拠として提示。
                     v2.1.0（Agent Documentation Foundation、ROADMAP:225）を
                     文書のみReleaseの前例として認識したうえで、性質の差から不採用
                D-D  【M-3】Decision の保存fieldを category 1件のみとし、
                     action を derived property へ変更（11.4節）。
                     案α（Decision＋property）と案β（Enum に property）を比較し、
                     v6.4／v6.5／v6.6の「保存field 1件のfrozen結果object」precedent
                     （S-8）を根拠に案αを採用。
                     初版INV-2〜INV-5は _ACTION_BY_CATEGORY の定義そのものとなり消滅
                D-E  【m-1／Q-3】ENVIRONMENT_ERROR を削除し UNCLASSIFIED へ統合。
                     Category 5値→4値。汎用型への isinstance 判定を設計から除去
                D-F  【m-2】T-23・T-24 を「条件付き（DI-4のtry範囲に依存）」へ変更し、
                     推奨利用例ではtry範囲外＝到達しないことを16.2節で明示。
                     try範囲の規定をN-20としてOut of Scopeへ
                D-G  【m-3】「provider非依存」を
                     「provider中立な分類語彙 ＋ adapter認識型の分類」へ全面置換。
                     9.4節をV-1〜V-4（保証）／W-1〜W-4（非保証）へ再構成
                D-H  【S-1】9.5節を新設し、正規化の3段構成
                     （provider例外→adapter例外→Category→制御）を明示。
                     本packageが「Repositoryに欠けていた第2段の正規化層」であることを記載
                D-I  【S-2】5.1節を新設し、package名称と実対象範囲の差を説明
                D-J  【S-3】RiskをR-1〜R-8の8件へ統一。
                     R-1をB-1対応後の可用性トレードオフへ差し替え、
                     R-7（CONTINUE経路が1 Categoryのみ）・R-8（actionがrepr/asdictに
                     現れない）を新設
                D-K  【追加】13.4節を新設。未知reason値に対し v6.6 precedent
                     （ValueError送出）から意図的に逸脱し UNCLASSIFIED へ倒す理由を
                     明示（except節内での新例外送出は元例外を破壊するため）。
                     Category→Actionの写像は S-17 precedent に従い直接subscriptとする

              Q-1〜Q-7:
                すべて確定（28章）。未解決のOpen Questionは残っていない。
                Q-3（Category 4値）・Q-4（__post_init__不要）はArchitecture変更を伴う。
                Q-1・Q-2・Q-5・Q-6・Q-7はArchitecture変更なし。

              Amendment 1で新設・全面改訂した章節:
                0.1（Finding対応表）／3.8〜3.9（S-12〜S-17）／5.1／8.4／9.4／9.5／
                10.2（Decision Table全面更新）／10.3／10.4／11.3〜11.5／11.7／
                12.1〜12.3／13.3〜13.5／14（要求8追加）／16.2／17.2／19 RB-6／
                20（DI-10）／21.2（WPUP-等）／21.4／22（R-1〜R-8）／23（AC-1〜27）／
                25.2／26／27／28／29／30

              → Architecture Review 2 実施へ

2026-07-27  Architecture Review 2 実施
              判定: Changes Required
              Blocking: 0 / Major: 1 / Minor: 3 / Suggestion: 2

              Review 1のB-1・M-1・M-2・M-3・m-1〜m-3・S-1〜S-3は
              **すべて解決済み**と判定された。

              Major:
                M2-1  REQUEST_REJECTED に記事固有失敗（Content Policy拒否、
                      HTTP 400）と systemic failure（model不存在・提供終了、
                      HTTP 404）が混在しており、全件CONTINUEは
                      Error Contractの安全側原則と矛盾する。
                      v6.11 _classify_api_error():133-138 が BadRequestError /
                      NotFoundError / ConflictError / UnprocessableEntityError を
                      単一reasonへ集約している事実と、_DEFAULT_MODEL が
                      日付固定snapshot（"gpt-image-2-2026-04-21"）である事実に基づく。
                      B-1が排除した permanent silent degradation と構造的に同一であり、
                      §10.5 根拠5・§14 要求1・§29 Checklistの普遍主張を
                      設計自身のDecision Tableが反証していた。
                      （本Findingは初版から存在し、Architecture Review 1が
                        見落としていたものである）

              Minor:
                m-A   _ACTION_BY_CATEGORY は素のdictであるのに
                      「module-level mutable stateを持たない」と記載（11.5節）
                m-B   8.4節 J-3「将来変更は加算的方向に限られる」が過大主張
                m-C   DI-10実施時にAC-24が既知差分としてFAILすることが未記録

              Suggestion:
                S2-A  callerによる元例外再送出はDI-1 E2Eでは検証不能である旨の明示
                S2-B  R-4をREQUEST_REJECTEDバケットの粒度不足として再定義すべき

              Architecture本体（責務配置 案E・実装時期 案1・Public API 4 symbol・
              Decision 1 field＋derived property・Action 2値の意味・
              WordPress全件PROPAGATE・Q-1/Q-2/Q-4〜Q-7・Runtime Zero Diff）は
              妥当と判定され、変更を要しない。

2026-07-27  Architecture Amendment 2 実施（本工程）
              → Architecture Review 2のM2-1・m-A〜m-C・S2-A〜S2-Bすべてに対応。
                Production Code・test code・既存文書への変更は行っていない
                （対象は本設計書1ファイルのみ）。

              主要Decision:
                D-L  【M2-1】新Failure Category `IMAGE_GENERATION_REQUEST_REJECTED`
                     を新設し、REQUEST_REJECTED を PROPAGATE_ORIGINAL_ERROR へ変更
                     （10.6節 C-6〜C-12）。Failure Categoryは4値→5値。
                     **Category分割方式を採った理由**：action は category から
                     導出される derived property であるため（Review 1 M-3の解決）、
                     同一 category が2つの action を持つことは構造的に不可能である。
                     「REQUEST_REJECTED を IMAGE_GENERATION_FAILED のまま
                     Action だけ PROPAGATE にする」案は Decision を2 fieldへ
                     戻すことを要求し、M-3の解決を撤回することになるため採らなかった
                     （27章・11.7節 理由4）。
                     新Categoryは削除した ENVIRONMENT_ERROR の復活ではなく、
                     異なるActionを必要とする意味のあるCategory分割である（C-11）
                D-M  【M2-1】REQUEST_REJECTED の内訳は本Releaseで細分化せず、
                     v6.11 側の reason 細分化を新規Deferred Item **DI-11** として
                     起票（20章）。**DI-4着手前の再検討を必須条件**とした（C-9）。
                     Content Policy拒否も伝播となる可用性トレードオフを
                     C-10で明示的に受諾した
                D-N  【M2-1】10.5節 根拠5 の普遍主張を精密化し、
                     保証する方向（configuration起因・分類不能をCONTINUEへ倒さない）と
                     保証しない方向（CONTINUEとなる6 reasonにconfiguration起因が
                     紛れ込まないことはv6.11の粒度に依存）を区別した
                D-O  【m-A】11.5節の statelessness 記述を事実に合わせて修正。
                     11.4.1節を新設し MappingProxyType の採否を比較、
                     v4.4.0 RETRY_OUTCOME_TERMINALITY precedent と最小性から
                     **素のdict維持**を確定。AC-28で書き換え非発生を機械検証する
                D-P  【m-B】8.4節 J-3 の断定を撤回。主たる変更方向は加算的であるが
                     逆方向も起こりうること（M2-1自身が実例）、
                     Public API早期固定リスクがゼロではないことを明記し、
                     先行実装案の主要根拠を J-1・J-2・J-4 へ置き直した
                D-Q  【m-C】20章 DI-10 と AC-24 へ、docs/CHANGELOG.md の
                     KI-3／KI-4 precedent を根拠として既知差分の扱いを明記。
                     DI-11についても AC-13 が同種の既知差分となる旨を記載。
                     CHANGELOG自体は変更していない
                D-R  【S2-A】21.6節を新設し、DI-1 E2Eで機械検証できる範囲（V-1〜V-5）と
                     DI-4へ委ねる範囲（W-1〜W-4）を分離。DI-4 Reviewerへの
                     申し送り事項も明記
                D-S  【S2-B】22章 R-4 を「REQUEST_REJECTEDバケットの粒度不足」へ
                     全面再定義。Severityを 低 → **中** へ引き上げ、
                     Mitigation・Deferred可否・DI-4前の再検討条件を更新。
                     R-7もAmendment 2の内容へ更新

              Amendment 2で新設・改訂した章節:
                0（Status）／0.2（Finding対応表・最終写像）／7（N-22）／
                8.4（J-3）／10.2（T-15・T-16）／10.3（要約・6 reasonの共通性質・
                Amendment差分）／10.5（根拠5）／10.6（新設）／11.3（Enum・写像）／
                11.4.1（新設）／11.5（stateful行）／11.7（Category 5値・排他性）／
                12.5／13.5（分岐順序）／14（要求1）／18（O-2）／20（DI-10注記・DI-11新設）／
                21.2（CAT-・MAP-・CONT-・REJECT-新設・PROP-・REASON-）／21.6（新設）／
                22（R-4全面再定義・R-7）／23（AC-3・AC-8・AC-8b・AC-13・AC-24注記・
                AC-28新設）／27／28（Q-3）／29／30

              Q-1〜Q-7:
                すべて確定のまま維持。Q-3のみ最終値を4値→5値へ更新した。
                Q-1・Q-2・Q-4・Q-5・Q-6・Q-7はAmendment 2で変更していない。

              → Architecture Review 3 実施へ

2026-07-27  Architecture Review 3 実施
              判定: Changes Required
              Blocking: 0 / Major: 2 / Minor: 1 / Suggestion: 1

              Review 1（10件）・Review 2（6件）のFindingは
              **すべて解決済み**と判定された。

              Major:
                M3-1  UNKNOWN に programming error・systemic failure が混入しうる。
                      v6.11 generate() は `except openai.APIError` の後段に
                      `except Exception:` を持ち、TypeError（SDK signature変更）・
                      AttributeError・ValidationError・SDK内部エラーを
                      すべて UNKNOWN へ落とす。requirements.txt:8 が
                      openai>=2.46.0,<3.0.0 と2.x系minor upgradeを許容し
                      venvにも未インストールであるため、SDK変更による
                      TypeError → UNKNOWN → CONTINUE が現実的に起こりうる。
                      T-20の根拠「provider通信の失敗として分類済み」は
                      `except Exception` 経路について事実として誤りであった。
                      B-1・M2-1と同種の permanent silent degradation
                M3-2  DI-10／DI-11 と DI-4 の順序が一義でない。
                      要求文は「再検討することを必須とする」だが、
                      同一文の括弧内の理由は「トレードオフを解消しない限り
                      DI-4を安全に設計できない」であり、
                      「再検討」と「完了」という異なる基準が併存していた

              Minor:
                m3-A  INVALID_RESPONSE の「一過性」も保証ではない。
                      provider／SDK の応答構造変更時は systematic になりうる

              Suggestion:
                S3-A  CONTINUE側に残る reason の残存リスクが Risk へ未記載

              Architecture本体（責務配置 案E・実装時期 案1・Public API 4 symbol・
              Decision 1 field＋derived property・Category 5値・Action 2値の意味・
              WordPress全件PROPAGATE・REQUEST_REJECTED全件PROPAGATE・
              Q-1/Q-2/Q-4〜Q-7・Runtime Zero Diff）は妥当と判定され、変更を要しない。

2026-07-27  Architecture Amendment 3 実施（本工程）
              → Architecture Review 3のM3-1・M3-2・m3-A・S3-Aすべてに対応。
                Production Code・test code・既存文書への変更は行っていない
                （対象は本設計書1ファイルのみ）。

              主要Decision:
                D-T  【M3-1】UNKNOWN を UNCLASSIFIED ＋ PROPAGATE_ORIGINAL_ERROR へ
                     変更（10.7節 C-13・C-15）。**新Categoryは追加しない**
                     （C-18。必要なActionが既存UNCLASSIFIEDと同一であり、
                      Amendment 1で ENVIRONMENT_ERROR を統合した基準を適用）。
                     10.7.1節でUNKNOWNの2生成経路をRepository実読で記録し、
                     T-20の誤った根拠を訂正した
                D-U  【m3-A】INVALID_RESPONSE も UNCLASSIFIED ＋ PROPAGATE へ変更
                     （C-14）。10.7.3節でsystemic failure混入の根拠を記録
                D-V  【M3-1・m3-A】分類方式を **deny-list から allow-list へ転換**
                     （C-17・13.5節）。CONTINUE は
                     TIMEOUT／CONNECTION／RATE_LIMIT／SERVER_ERROR の4 reasonのみ。
                     `_CONTINUABLE_REASONS`（frozenset）を導入し、
                     未知reason・reason欠落・INVALID_RESPONSE・UNKNOWN が
                     すべて同一の else 分岐へ落ちる構造とした。
                     **v6.11 が reason を追加しても新値は自動的に安全側へ落ちる**
                D-W  【M3-1】4 reason の性質を「必ず一過性」ではなく
                     「現行の分類粒度において一過性と積極的に判断する対象」と
                     正確化した（10.3節）
                D-X  【M3-2】10.8節を新設し、O-1〜O-4の**条件付き二段構え**で一義化。
                     再評価は必須（ORD-1）／現契約受容なら未完了でもDI-4可（ORD-2）／
                     CONTINUE拡大を望むなら該当DI完了が前提（ORD-3）／
                     可用性低下を受容不可なら該当DI完了が前提（ORD-4）。
                     C-4・C-9・20章 DI-10/DI-11/DI-4行・26章 ROADMAP更新計画・
                     29章 Checklist・AC-29 で表現を統一した
                D-Y  【M3-1】DI-11 の対象範囲を拡張（C-20）。REQUEST_REJECTED の
                     細分化に加え、UNKNOWN の2経路分離と INVALID_RESPONSE の
                     単発破損／スキーマ変更の分離を検討対象へ含めた
                D-Z  【S3-A】22章 R-7 を再構成し、CONTINUE側4 reason の
                     残存リスク（一過性は現行分類粒度に依存する判断であること）を
                     統合。Severityを 低〜中 → **中** へ引き上げた。
                     **R-1〜R-8 の8件という件数は維持**した

              Amendment 3で新設・改訂した章節:
                0（Status）／0.3（Finding対応表・最終写像）／10.2（T-18・T-19・T-20）／
                10.3（要約・allow-list転換・4 reasonの性質・Amendment差分）／
                10.4（C-4）／10.6（C-9）／10.7（新設）／10.8（新設）／
                11.7（被覆 4/1/2/2）／13.5（allow-list実装・分岐順序）／
                20（DI-4行・DI-10・DI-11）／21.2（CONT-・UNCLS-新設・REASON-・
                NOPARSE-新設）／22（R-7再構成）／23（AC-8・AC-8c新設・AC-13・
                AC-28拡張・AC-29新設）／26／27／28（Q-3）／29／30

              Q-1〜Q-7:
                すべて確定のまま維持。Q-3のみ「Category 5値は不変、
                reason→Category の割り当てを変更」と補記した。
                Q-1・Q-2・Q-4・Q-5・Q-6・Q-7はAmendment 3で変更していない。

              → Architecture Review 4 実施へ

2026-07-27  Architecture Review 4 実施
              判定: **Approved with Suggestions**
              Blocking: 0 / Major: 0 / Minor: 3 / Suggestion: 2

              Review 1（10件）・Review 2（6件）・Review 3（4件）のFindingは
              **すべて解決済み**と判定された。

              Production Codeとの照合結果（実測）:
                ・OpenAIImageGenerationErrorReason の全memberは9値であり、
                  設計書の 4 / 1 / 2 / 2 分割と完全一致。欠落・重複なし
                ・AUTHENTICATION / PERMISSION_DENIED は設計書本体・擬似コード・
                  Test Strategy・ACのいずれにおいても
                  IMAGE_GENERATION_NOT_AUTHORIZED であり、
                  UNCLASSIFIED への誤分類は**存在しない**
                  （Amendment 3の最終報告に関する懸念は転記上の誤りであり、
                    設計書本体に問題はない。IMAGE_GENERATION_NOT_AUTHORIZED は
                    2 reasonを担う使用中Categoryであり、未使用化していない）
                ・CONTINUE対象4 reason（TIMEOUT / CONNECTION / RATE_LIMIT /
                  SERVER_ERROR）はいずれも _classify_api_error() 内でのみ生成され、
                  同関数は `except openai.APIError as exc:` からのみ呼ばれる。
                  したがって**構造的に openai.APIError subclass 由来に限定**され、
                  programming error は `except Exception` 経路の UNKNOWN へ落ちる。
                  4 reason を CONTINUE とする判断は安全側原則と矛盾しない
                ・INVALID_RESPONSE は _classify_api_error() からは生成されず、
                  API呼び出し成功後の _validate_response_structure() /
                  _build_generated_image() からのみ生成される（設計書10.7.3節と一致）

              Minor（いずれも本Review工程内で限定修正により解消済み）:
                m4-A  13.5節の擬似コードで _CONTINUABLE_REASONS が関数内に
                      定義されており、AC-28の「module-level以外での代入0件」および
                      11.4.1節のmodule-level分類表という枠組みと不整合だった
                      → module-level配置であることを明示し、配置方針を追記
                m4-B  22章 R-1／R-4 のDeferred列が「DI-4前に再検討必須」という
                      Amendment 2以前の表現のままで、10.8節の二段構えを
                      参照していなかった（AC-29(c)がR-1／R-4を対象に含めている）
                      → ORD-1〜ORD-4を参照する表現へ統一
                m4-C  10.8節の判定規則ID（O-1〜O-4）が18.1節の観測契約ID
                      （O-1〜O-7）と衝突していた
                      → 10.8節を **ORD-1〜ORD-4** へ改称し、全参照箇所を更新。
                        18.1節のO-1〜O-7は変更していない

              Suggestion（Non-Blocking、Production Implementation以降へ引き継ぐ）:
                S4-A  openai.RateLimitError（HTTP 429）はレート制限だけでなく
                      quota枯渇（課金上限）も含みうる。後者は systemic かつ
                      operator-actionable であり、CONTINUE のままでは
                      permanent silent degradation になりうる。
                      ただし**この挙動はRepositoryから検証できない**
                      （openai未インストール、テストfixture・文書とも不在）ため
                      Major とはせず、22章 R-7 が既に残存リスクとして記録している
                      範囲に含める。ORD-1の再評価スコープへ明示的に加えることを推奨
                S4-B  上記「CONTINUE対象4 reasonが構造的に
                      openai.APIError subclass 由来に限定される」という性質は
                      10.3節の判断を強く裏付けるが、設計書に明記されていない。
                      追記すると R-7 の残存リスク評価がより精密になる
                      （29章 Checklistには本Review工程で追記済み）

              Architecture本体（責務配置 案E・実装時期 案1・Public API 4 symbol・
              Decision 1 field＋derived property・Category 5値・Action 2値・
              allow-list方式・reason 4/1/2/2分割・DI順序の二段構え・
              Q-1〜Q-7・R-1〜R-8・Runtime Zero Diff）はいずれも妥当と判定され、
              変更を要しない。

              → **Production Implementation へ進行可能**
                （Architecture Amendment 4：Not Required）

2026-07-27  Production Implementation 実施（本工程）
              → 承認済み設計（Architecture Review 4：Approved with Suggestions）を
                忠実にProduction CodeおよびE2Eへ実装した。設計の解釈・補完は
                行わず、§11 Public API・§13.5 分類擬似コードをそのまま反映した。

              新規作成ファイル:
                src/image_generation_fallback_policy/__init__.py
                src/image_generation_fallback_policy/image_generation_fallback_policy.py
                tests/test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py

              実装内容:
                ・Public API 4 symbol（ImageGenerationFailureCategory・
                  ImageGenerationFallbackAction・ImageGenerationFallbackDecision・
                  decide_image_generation_fallback）を§11.2・§11.3のとおり実装
                ・Decisionは保存field category 1件＋action derived property
                ・_ACTION_BY_CATEGORY（素のdict）・_CONTINUABLE_REASONS
                  （frozenset、allow-list）をmodule-levelに配置
                ・分類アルゴリズムは§13.5擬似コードと完全一致
                  （AUTHENTICATION／PERMISSION_DENIED → NOT_AUTHORIZED、
                    REQUEST_REJECTED → REQUEST_REJECTED、
                    allow-list該当4 reason → FAILED、それ以外 → UNCLASSIFIED、
                    WordPressMediaUploadError → MEDIA_UPLOAD_FAILED、
                    その他 → UNCLASSIFIED）
                ・try／except・新規例外型・__post_init__は追加していない
                ・os／logging／requests／socket／openaiはimportしていない

              新規E2E実行結果:
                venv Scripts python.exe による直接実行（standalone script形式）
                Assertion合計：234、234/234 PASS、0 FAIL、exit code 0
                Scenario prefix：API-／ACTION-／CAT-／MAP-／IMM-／CONT-／UNCLS-／
                REJECT-／PROP-／WPUP-／REASON-／NOPARSE-／UNK-／DEFENSE-／
                TYPEERR-／BASE-／PURE-／SEC-／NOEXC-／DEP-／IMPORT-／SOCKET-／
                RUNTIME-／COMPAT-／ENV-（25 prefix全件実装）
                clean subprocessによるopenai非import決定的検証、および
                test本体プロセス内でのsocket.getaddrinfo／socket.socket.connect
                in-process遮断検証を含む。外部API実接続・実credentialはいずれも
                発生させていない。

              Architectureからの逸脱: なし。

              本工程ではFormal Regression・Documentation Integration・
              Release Review・commit・pushのいずれも実施していない。

2026-07-27  Production Code Review 実施
              判定: Approved with Suggestions
              Blocking: 0 / Major: 0 / Minor: 3 / Suggestion: 2

              報告された234／234 PASSを前提化せず、Architecture・Production
              Code・E2E・Git状態を独立かつ反証的に確認した。実測により
              234／234 PASS・exit code 0・stderr空を再現。

              Minor:
                m-1  reasonがハッシュ不可能な値（list／dict等）の場合、
                     `reason in _CONTINUABLE_REASONS` がTypeError
                     （unhashable type）を送出し、設計書13.4節「memberでない
                     場合はUNCLASSIFIEDへ倒す」という規則に反する
                m-2  REASON-SPLIT-4-1-2-2 の集計元がテスト自身の期待表
                     （_expected_category_by_reason_name）であり、
                     decide()の実測結果ではない自己参照的assertionだった
                m-3  DEP-のAST検証がMODULE_FILEのみを対象とし、
                     __init__.py（package root）が禁止import検証の対象外
                     だった（INIT_FILEは定義済みだが未使用）

              Suggestion:
                s-1  _ACTION_BY_CATEGORY（素のdict）・_CONTINUABLE_REASONS
                     （frozenset）の型そのものに対するE2E上の回帰ガードがない
                s-2  Scenario prefix数（正確には25）・AC項目数（正確には
                     AC-1〜AC-29＋AC-8b＋AC-8cの31件）について、過去の
                     報告に計数誤りがあった（成果物の欠陥ではなく報告上の
                     転記誤り）

              Architecture本体・Public API・Category→Action写像・
              allow-list 4 reason・Runtime Zero Diffはいずれも妥当と判定され、
              変更を要しない。

2026-07-27  Production Implementation Correction 実施（本工程）
              → Production Code ReviewのFinding m-1・m-2・m-3・s-1のみを
                限定修正した。Architecture・Public API・Enum member・
                Category→Action写像・allow-list 4 reasonはいずれも変更して
                いない。s-2（件数表記）はDocumentation Integration申し送り
                事項とし、本工程では修正しなかった。

              修正内容:
                m-1  src/image_generation_fallback_policy/
                     image_generation_fallback_policy.py:143付近の
                     allow-list membership判定を
                       elif (isinstance(reason, OpenAIImageGenerationErrorReason)
                             and reason in _CONTINUABLE_REASONS):
                     へ変更。ハッシュ不可能なreason値・Enum memberでない値は
                     いずれもisinstanceの時点でFalseとなり、frozensetへの
                     membership testを評価しないため、TypeErrorを送出せず
                     UNCLASSIFIEDへ倒れる。E2E DEFENSE-Scenarioへ
                     reason=[]／{}／set()の3ケースを追加し、
                     UNCLASSIFIED＋PROPAGATE_ORIGINAL_ERRORとなること、
                     policy自身から予期しないTypeErrorが送出されないことを
                     確認した
                m-2  E2E REASON-SPLIT-4-1-2-2 の集計元を、テスト自身の
                     期待表から decide_image_generation_fallback() の
                     実測戻り値（_actual_category_by_reason）へ変更。
                     既存のREASON-MATCH（個別9 reason検証）は維持し、
                     実測集計による独立した網羅確認
                     （合計9件・欠落なし・重複なし）を追加した
                m-3  E2Eの[DEP]Scenarioへ、既存INIT_FILEを用いた
                     __init__.pyの禁止import AST検証
                     （DEP-INIT-FORBIDDEN-IMPORTS・
                     DEP-INIT-NO-{OS,LOGGING,REQUESTS,SOCKET,OPENAI}-IMPORT）
                     を追加した。既存の許可された相対import
                     （.image_generation_fallback_policy）は許可集合内として
                     扱い、失敗にしていない
                s-1  E2Eの[MAP]Scenarioへ、_ACTION_BY_CATEGORYが素のdictで
                     あること（MappingProxyTypeではないこと）、
                     _CONTINUABLE_REASONSがfrozensetであることの型契約
                     検証を追加した

              副次的影響（承認済みFinding修正の直接的帰結）:
                m-1修正によりProduction Codeへ
                `isinstance(reason, OpenAIImageGenerationErrorReason)` が
                追加されたため、E2Eの DEP-ISINSTANCE-TARGETS-LIMITED が
                初回再実行でFAILした（許可集合に新しいisinstance対象が
                含まれていなかったため）。この判定を「Repository内2型＋
                Exceptionのみ」から「Repository内3型＋Exceptionのみ」へ
                更新し、OpenAIImageGenerationErrorReasonを追加した。
                これは汎用組み込み型（ImportError等）への判定ではなく、
                m-1の修正指示で明示的に与えられたコードそのものが要求する
                Repository内公開Enum型への判定であり、Architecture逸脱では
                ない。

              Correction後の新規E2E実測結果:
                Assertion合計：254、254/254 PASS、0 FAIL、exit code 0、
                stderr空。network・実credential使用なし。

              変更ファイル:
                src/image_generation_fallback_policy/
                  image_generation_fallback_policy.py（m-1のみ）
                tests/test_e2e_v6_19_0_image_generation_fallback_policy_
                  foundation.py（m-1のE2E追加・m-2・m-3・s-1・
                  DEP-ISINSTANCE-TARGETS-LIMITED更新）
                本設計書（Status／Review History最小更新）

              変更していないファイル:
                src/image_generation_fallback_policy/__init__.py
                （変更不要と判断。相対importのみで禁止import・変更対象なし）

              Architectureからの逸脱: なし。Public API名・Enum member・
              Category→Action写像・allow-list 4 reasonはいずれも不変。

              Documentation Integration申し送り事項:
                ・ハッシュ不可能なreason値の扱いについて、設計書13.4節
                  「規則」の記述を「member でない場合」が非Enum型
                  （list／dict等、ハッシュ不可能な値を含む）も対象と
                  することが読み取れるよう、Architecture本文側での
                  明確化を検討する（本工程ではArchitecture本文を変更して
                  いない）
                ・Scenario prefix数（25）・AC項目数（31件、AC-1〜AC-29＋
                  AC-8b＋AC-8c）の正確な値を、Architecture Review 4・
                  Production Implementation等の過去記録の表記と統一する
                  （s-2、成果物の修正は不要）

              本工程ではCorrection Review・Formal Regression・
              Documentation Integration・Release Review・commit・push の
              いずれも実施していない。

2026-07-27  Formal Regression 実施（1回目、本工程の前段。停止）
              正式Inventory22ファイルのうち1〜13件目（v1.11.0〜v6.10.0）は
              全件PASS（合計1435 Assertion）したが、14件目
              `test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py`
              の実行で `ModuleNotFoundError: No module named 'openai'`
              （exit code 1）が発生し、指示どおり直ちに停止した。
              原因調査の結果、`requirements.txt`は`openai>=2.46.0,<3.0.0`を
              正しく宣言していたが、指定venvには実際にはopenaiが
              未導入であるという環境不整合であり、本Releaseの変更に起因する
              ものではないと判定した。package installは本工程の権限外のため
              実施せず、Production Code・test・設計書のいずれも変更せずに
              報告のみを行い停止した。15〜22件目は未実行のまま終了した。

2026-07-27  venv Environment Repair 実施（本工程）
              → 指定venv（projects/03_game_content_ai/venv/Scripts/python.exe）
                へ、requirements.txt宣言範囲内で`openai`のみを導入した。

              修復前確認:
                pip show openai → Package(s) not found
                import openai   → ModuleNotFoundError
                requirements.txt:8 → openai>=2.46.0,<3.0.0（期待どおり）

              実行コマンド（1回のみ）:
                venv\Scripts\python.exe -m pip install "openai>=2.46.0,<3.0.0"

              install結果:
                成功。openai-2.48.0を新規導入。依存解決によりpip自身の
                判断でtqdm-4.69.1・colorama-0.4.6も付随導入された
                （openaiの推移的依存であり、明示的な追加installは
                  行っていない）。

              修復後確認:
                version: 2.48.0（2.46.0 <= 2.48.0 < 3.0.0 を充足）
                location: projects/03_game_content_ai/venv/Lib/site-packages
                          （指定venv内）
                Python executable: 指定venvのpython.exeと一致
                import openai: 成功

              Repositoryへの影響:
                git status --porcelain --untracked-files=all および
                git diff --stat HEAD で、pip install前後にRepository
                ファイルの変更が一切発生していないことを確認した
                （untrackedは開始時と同じ4ファイルのまま）。
                requirements.txt・Production Code・testsはいずれも無変更。

2026-07-27  Formal Regression 実施（2回目、本工程。全件再実行）
              → 環境修復後、正式Inventory22ファイルを1件目から全件、
                前回のPASS結果を流用せず再測定した。

              正式Inventory確定根拠:
                docs/architecture.mdの複数箇所（v6.15〜v6.18各層記述）に
                記載された非再帰的表現「既存Nファイル：
                test_e2e_v1_11_0_save_result.py・test_e2e_v5_9_0_*.py・
                test_e2e_v6_0_0_*.py〜test_e2e_v6_{M}_0_*.py」のprecedentに
                基づき、v6.18完了時点の21ファイル（v1.11.0・v5.9.0・
                v6.0.0〜v6.18.0）＋新規v6.19.0 E2E＝22ファイルを確定した。
                22ファイル全件の実在をlsで確認し、既知差分（KI-1〜KI-29）を
                確認した結果、対象21ファイルへの現時点で未解消の既知差分は
                ないことを確認した。

              実行結果（1件目から順番どおり、22件全件）:
                1  v1.11.0   43/43 PASS
                2  v5.9.0    64/64 PASS
                3  v6.0.0    43/43 PASS
                4  v6.1.0    44/44 PASS
                5  v6.2.0    64/64 PASS
                6  v6.3.0    174/174 PASS
                7  v6.4.0    171/171 PASS
                8  v6.5.0    131/131 PASS
                9  v6.6.0    135/135 PASS
                10 v6.7.0    117/117 PASS
                11 v6.8.0    197/197 PASS
                12 v6.9.0    331/331 PASS
                13 v6.10.0   78/78 PASS
                14 v6.11.0   248/248 PASS（環境修復により前回のFAILを解消）
                15 v6.12.0   91/91 PASS
                16 v6.13.0   123/123 PASS
                17 v6.14.0   217/217 PASS
                18 v6.15.0   94/94 PASS
                19 v6.16.0   143/143 PASS
                20 v6.17.0   136/136 PASS
                21 v6.18.0   146/146 PASS
                22 v6.19.0   254/254 PASS（Correction後の期待値と完全一致：
                             25 Scenario prefix・254 Assertion・0 FAIL・
                             exit code 0・stderr空）

              集計（今回の実測結果のみ、過去報告値は不使用）:
                対象ファイル数：22（全件standalone script形式、pytest形式0）
                既存21ファイル合計：2790 Assertion、2790/2790 PASS
                  （v6.18完了時のbaseline 2790/2790と完全一致。差分なし）
                新規v6.19：254 Assertion、254/254 PASS
                総合計：3044 Assertion、3044/3044 PASS
                FAIL：0／SKIP：0／exit code異常：0／既知差分：0
                network使用：0件／credential使用：0件

              Runtime Zero Diff：git diff --stat HEADで既存tracked
              ファイル変更0件を確認（テスト実行はいずれも読み取り専用）。

              Architectureからの逸脱：なし。

              本工程ではDocumentation Integration・Release Review・
              commit・pushのいずれも実施していない。

2026-07-27  Documentation Integration 実施（本工程）
              → 確定済みの実装・Review・テスト結果をdocs/ROADMAP.md・
                docs/architecture.md・docs/CHANGELOG.md・本設計書の4文書へ
                統合した。Architecture本文・Public API・Failure Taxonomy・
                Error Contract・Test Strategy・Acceptance Criteriaの実質的な
                変更は行っていない。

              本設計書への反映:
                §13.4  「memberでない」の範囲に、list／dict／set等の
                       ハッシュ不可能な値が含まれることを明記し、
                       Correction Finding m-1の内容（isinstance guardにより
                       予期しないTypeErrorを送出しない）を追記した
                §13.5  擬似コードを、Correctionで実装済みの
                       `isinstance(reason, OpenAIImageGenerationErrorReason)
                       and reason in _CONTINUABLE_REASONS`へ更新し、
                       設計書とProduction Codeの齟齬（Documentation
                       Integration開始時に発見）を解消した。あわせて
                       「isinstance判定はRepository内の型2種のみ」という
                       記述を、m-1対応で追加された
                       OpenAIImageGenerationErrorReasonへのisinstance判定を
                       反映し「型3種」へ訂正した
                Status  Documentation Integration：Completed、
                       Release：Not Completed（Release Review未着手）へ更新

              件数表記の統一（正式値）:
                Scenario prefix：25
                Acceptance Criteria項目：31件（AC-1〜AC-29・AC-8b・AC-8c）
                新規E2E Assertion：254（254/254 PASS）
                Formal Regression Inventory：22ファイル
                Formal Regression総Assertion：3044（3044/3044 PASS。
                  既存21ファイル2790／新規v6.19 254）
              過去の「24 prefix」「AC-1〜AC-29を総数として扱う表現」等の
              誤表記は、本設計書内では未検出であった（外部Review報告上の
              誤りに留まる）。Correction前の実測値「234 Assertion・
              234/234 PASS」は、Correction前の履歴として意味づけを保ったまま
              残し、最終値（254）と混同しない形で区別した。

              docs/ROADMAP.mdへの反映:
                Deferred Items「Image Generation Fallback Policy」Entryを、
                Documentation Integration完了時点の状態
                （Architecture Review 4 Approved with Suggestions、
                  Production Implementation・Correction・Formal Regression
                  Completed、Release Review未着手）を反映した記述へ更新した。
                Release自体は未完了のため、チェックボックスは`[ ]`のまま
                維持した。「Article Featured Media Runtime Wiring」Entryの
                DI-1参照箇所を、DI-1がArchitecture／実装／テストの観点では
                前進したがRelease Reviewを経ていないことを反映する表現へ
                更新した。DI-10・DI-11をDeferred Itemsへ新規追加した。

              docs/architecture.mdへの反映:
                「Image Generation Fallback Policy Foundation層
                （src/image_generation_fallback_policy/、v6.19.0候補）」節を
                新設した。Purpose・Package Boundary・Public API・
                Failure Taxonomy／Category→Action写像・Security・
                Runtime Zero Diff・Test Review実績・Out of Scope／Future
                Extensionの既存層構成を踏襲した。Release Reviewが未着手
                であることを冒頭の記録ブロックで明示し、他層のような
                「実装完了時点の記録」という確定的な言い回しは用いなかった。

              docs/CHANGELOG.mdへの反映:
                「## [v6.19.0] - 2026-07-27 ★ Image Generation Fallback
                Policy Foundation」エントリを新規作成した。Added・Changed
                （なし）・Public API・Contract概要・Runtime Zero Diff・
                Security／Dependency・Tested・Environment Note・Scopeの
                各節を既存形式に従って記載した。冒頭の状態記録ブロックには
                「Release Review：Pending」「Release：Not Completed」を
                明記し、Release Reviewが未実施であることを一貫させた。
                venvのopenai未導入という解消済みの環境不整合は、恒久的な
                Known Issueとしては登録せず、Environment Note節に
                「Release 6.19.0の回帰ではない」旨とともに記録した。

              文書間整合性確認:
                4文書を横断してgrepし、Release名・Public API名・Category
                5値・Action 2値・reason分類・allow-list 4 reason・
                Scenario prefix 25・AC項目31・新規E2E 254／254・Formal
                Regression 22ファイル・3044／3044・既存baseline 2790／2790・
                openai 2.48.0・Release Review Pending表記の一致を確認した。
                「Release Review Approved」「Release：Completed」という
                表記がいずれの文書にも存在しないことを確認した。

              Architectureからの逸脱：なし。

              本工程ではRelease Review・commit・pushのいずれも
              実施していない。

2026-07-27  Release Review 実施
              → Public API・Category／Action／Decision・Category→Action
                写像・reason分類（allow-list 4 reason）・Correction
                （m-1〜m-3・s-1）・Security・依存境界・Runtime Zero Diff・
                新規E2E構成・Documentation Integration・DI-4／DI-10／DI-11
                ／ORD-1〜ORD-4契約・Status／Review Historyを、独立した
                反証的Reviewとして再検証した。報告済みの数値は前提化せず、
                Production Codeからの独立抽出・AST解析・実測で再確認した。

              新規E2E再実行結果:
                25 Scenario prefix、254 Assertion、254/254 PASS、
                exit code 0、stderr空。Formal Regression 22ファイルは
                本工程では再実行していない（Formal Regression工程の
                記録を文書間整合性の確認のみで検証した）。

              判定：Approved with Suggestions
                （Blocking 0・Major 0・Minor 0・Suggestion 2）

              Finding:
                S-1（Suggestion）Status欄に残る「本工程」という指示語が、
                    どの工程を指すか一意に定まらない
                  → 各Status行を工程名（Production Implementation工程・
                    Production Implementation Correction工程・
                    Environment Repair工程・Formal Regression工程・
                    Documentation Integration工程）で明示する限定修正で
                    解消した（本Review反映時）
                S-2（Suggestion）Release Reviewの状態表記が設計書
                    （Not Started）とCHANGELOG.md（Pending）で異なる
                  → 4文書を「Release Review：Approved with Suggestions」
                    「Release：Completed」へ統一する限定修正で解消した
                    （本Review反映時）

              Public API・Failure Taxonomy・Error Contract・Security・
              Runtime Zero Diffのいずれにも問題は見つからなかった。
              Architectureからの逸脱：なし。

              Release 6.19.0を最終Git工程（Release Review結果の文書反映・
              commit・push）へ進行可能と判定した。
```
