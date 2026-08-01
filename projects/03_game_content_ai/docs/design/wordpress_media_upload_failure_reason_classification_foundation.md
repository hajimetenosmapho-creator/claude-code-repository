# WordPress Media Upload Failure Reason Classification Foundation（DI-10）— Architecture Design

> **本設計書は Deferred Item DI-10（`docs/ROADMAP.md`「WordPress Media Upload Failure Reason
> Classification（DI-10）」）の Architecture Design である。** v6.9.0 で導入された
> `WordPressMediaUploadError` へ、構造情報（例外型・HTTPステータスコード）のみに基づく
> 分類Enumを純追加する。**production behavior（成功・失敗の挙動、例外型、例外message）は
> 一切変更しない。**

---

## 0. Status

| 項目 | 内容 |
|---|---|
| **提案Release番号** | **v6.22.0 / Release 6.22（提案。未確定）** |
| **提案Release名称** | WordPress Media Upload Failure Reason Classification Foundation |
| **対象 Deferred Item** | DI-10 |
| **工程** | Architecture Design → Architecture Review 1〜4（各 Changes Required、Amendment 1〜4 で収束）→ Architecture Review 5（Approved with Suggestions）→ Production Implementation → Implementation Review 1（Approved with Suggestions）→ Implementation Amendment 1（Completed）→ Implementation Review 2（Approved with Suggestions）→ Formal Regression（Completed）→ **Documentation Integration（本工程）** |
| **Architecture Review 1** | Completed（Verdict: Changes Required。Blocking 1件・Major 2件・Minor 4件・Suggestion 3件。全件 closure 済み） |
| **Architecture Amendment 1** | Completed（0.4節） |
| **Architecture Review 2** | Completed（Verdict: Changes Required。Blocking **0**件・Major 1件・Minor 5件・Suggestion 3件。Review 1 Finding の全件 closure を確認、V-3 は Review 2 で承認・close） |
| **Architecture Amendment 2** | Completed（0.5節） |
| **Architecture Review 3** | Completed（Verdict: Changes Required。Blocking **0**件・Major 1件・Minor 5件・Suggestion 3件。Review 2 の M2-1 のみ Not Closed、他は全件 closure 済み） |
| **Architecture Amendment 3** | Completed（0.6節） |
| **Architecture Review 4** | Completed（Verdict: Changes Required。Blocking 1件・Major 0件・Minor 4件・Suggestion 2件。Review 3 の全Finding closure を確認） |
| **Architecture Amendment 4** | Completed（0.7節） |
| **Architecture Review 5** | Completed（Verdict: **Approved with Suggestions**。Blocking 0件・Major 0件・Minor 1件（M5-1：match-case class patternのallow-list非対応。Deferred）・Suggestion 1件。Review 4 の全Finding closure を確認） |
| **Production Implementation** | Completed（`src/wordpress_media/wordpress_media_uploader.py`・`src/wordpress_media/__init__.py`の2ファイルのみ変更） |
| **New E2E** | Completed（`tests/test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py`、324アサーション、324/324 PASS） |
| **Implementation Review 1** | Completed（Verdict: Approved with Suggestions。Blocking 0件・Major 0件・Minor 4件（m1〜m4）・Suggestion 3件（s1〜s3）。既存3389不変・Runtime Zero Diff成立・Architecture逸脱なしを確認） |
| **Implementation Amendment 1** | Completed（0.9節。m1〜m4解消、s1採用・s2不採用・s3維持。新規E2E 316→324アサーション） |
| **Implementation Review 2** | Completed（Verdict: Approved with Suggestions。Blocking 0件・Major 0件・Minor 1件（M2R-1：17章とAC-6.22-13の`message`項目同期不完全）・Suggestion 1件（S2R-1）。m1〜m4・s1のclosureを独立検証で確認） |
| **Formal Regression** | Completed（正式Inventory25ファイル：既存24ファイル 3389/3389 PASS＋新規v6.22.0 324/324 PASS＝総合3713/3713 PASS。FAIL 0・SKIP 0・全ファイル終了コード0・既知差分0・Runtime Zero Diff維持） |
| **Documentation Integration** | **本工程**（M2R-1を17章へ反映して解消、S2R-1をDeferredとして記録。design doc／ROADMAP／architecture.md／CHANGELOGの4文書を更新） |
| **Release Review** | Completed（Verdict: **Approved with Suggestions**。Blocking 0件・Major 0件・Minor 3件（RR-M-1〜RR-M-3。design doc 14.4〜14.6節の記述と実績の不整合。いずれもFinalizeでclosure済み。0.11節参照）・Suggestion 1件（RR-S-1：設計書タイトル「— Architecture Design」表記。既存precedentに合わせ記録のみで不採用）。Formal Regression 25ファイル 3713/3713 PASSを再確認済み） |
| **Release** | **Completed** |

### 0.1 Repository 開始状態

```text
branch      : main
HEAD        : 578af6bdaeec23dd0c145a57384369ede433e3e4（Release 6.21.0）
origin/main : 578af6bdaeec23dd0c145a57384369ede433e3e4
ahead/behind: 0 / 0
Working Tree: clean
Formal Regression baseline: 正式Inventory24ファイル・3389/3389 PASS
```

### 0.2 本工程（Documentation Integration）で変更したファイル

**次の4ファイルのみ。** Production Code・tests・`main.py`はいずれも無変更である。

- 本設計書（Status・17章NOPARSE-禁止一覧・19章 Deferred Itemsを更新）
- `docs/ROADMAP.md`（v6.22.0を正式Release候補として記録。旧DI-10「次候補・
  未着手」スタブを置き換え）
- `docs/architecture.md`（「WordPress Media Upload Failure Reason Classification
  Foundation層」節を新設）
- `docs/CHANGELOG.md`（`[v6.22.0]`エントリを新設。Release Review Pending明記）

**Repository 開始状態**：branch `main`、local HEAD = `origin/main` =
`578af6bdaeec23dd0c145a57384369ede433e3e4`、ahead／behind 0／0、
Working Tree は本設計書・新規E2Eの2件がuntrackedのみ（Production Code 2ファイル・
既存E2E 4ファイルは Implementation Amendment 1 時点から変更なし）。

**Architecture Amendment 1〜4 時点の記録（参考）**：当時はいずれも「本設計書
1ファイルのみ」変更し、他ドキュメントは無変更であった。14.6節にROADMAP変更案を
先行記載していたが、実際の反映は本工程（Documentation Integration）で行った。

### 0.3 Release番号の扱い

v6.22.0 は前工程のRepository調査で提案された番号であり、**本設計書は番号を確定しない。**
Architecture Review 承認後、人間の独立承認をもって確定する。後続Release（v6.23.0 以降）の
番号・内容についても本設計書は一切確定しない（7章 N-13）。

### 0.4 Architecture Amendment 1 の要約（Architecture Review 1 Finding 対応）

Architecture Review 1（Verdict: **Changes Required**、Blocking 1件・Major 2件・
Minor 4件・Suggestion 3件）を受け、本 Amendment で Blocking 1件・Major 2件・
Minor 4件をすべて解消した。Suggestion 3件は S-1・S-3 を採用し、S-2 は理由を
記録のうえ不採用とした。

```text
B-1（Blocking）v6.21.0 E2E の NOIMPACT guard が src/wordpress_media を
  保護対象に含んでおり（tests/test_e2e_v6_21_0_*.py L853）、設計どおり実装すると
  NOIMPACT-UNCHANGED[src/wordpress_media] と NOIMPACT-TESTS-SCOPE が確実にFAILする。
  「更新対象は4アサーション／3ファイルで全数」（3.8節・11.2節）・
  「baseline 3389 不変」（11.5節）・「v6.21 guard方式に従う」（11.6節）が
  いずれも成立していなかった
  → 11.7節を新設し、Review 指示どおり案C（allow-list 方式への精緻化）を採用した。
    guard から対象を削除せず、「差分ゼロ」検査を「差分が明示allow-listの範囲内」
    検査へ精緻化する（allow-list が空の対象では従来と論理的に等価）。
    11.8節に後続Releaseが再利用できる一般則を新設。3.8節（走査methodology）・
    11.2節（X-5・X-6 追加）・11.5節（再計算）・11.6節・14.3節・18章
    （AC-6.22-16／-17 改訂、AC-6.22-21〜-22 追加）・20章（R-10）・
    21章（V-8〜V-10 改訂、V-14 追加）へ反映

M-1（Major）D-1c の「検出可能性は失われない」が、将来追加される raise 経路に対して
  成立しない（REASON-R1〜R9 は既知9経路のみを検証する列挙型テスト）
  → 既定値付き設計は維持したうえで、raise 件数に依存しない
    exhaustive AST guard（GUARD-REASON-EXHAUSTIVE）を追加設計し、
    behavioral E2E ＋ AST guard の二重検証へ改めた。
    10.2節 D-1c・12章 I-6・17章・18章（AC-6.22-23）・20章 R-1・21章 V-1 へ反映

M-2（Major）taxonomy の「各値が異なる是正actionへ1対1で写像される」という正当化に
  実測反例がある（WP_SITE_URL の http→https 誤設定は 301 追跡＋POST→GET 書き換えにより
  404 ではなく INVALID_RESPONSE として観測される）
  → 10.1.1節「reason の意味の限定」を新設し、reason を観測された構造の分類と
    定義（根本原因・是正actionとの1対1対応は保証しない）。
    10.1.2節「Inherited Limitations」を新設し実測根拠付きで記録。
    NOT_FOUND は ROUTE_NOT_FOUND へ改名を採用（m-4 と統合）。
    8.2節の正当化・19章 DEF-6.22-11／-12・21章 V-2 へ反映

m-1（Minor）v6.9 DEP-2／DEP-3／DEP-4 の全文substring guardが実装制約として未記録
  → 14.1.1節「実装制約（既存guard由来）」を新設し禁止部分文字列を全列挙。20章 R-11 追加
m-2（Minor）「画像系11 package」が既存docsと異なる集合を指す
  → 11.6節・18章 AC-6.22-16 の表現を包含関係が一義に定まる形へ改訂
m-3（Minor）3.8節の走査methodologyが不完全（パスベースguardを走査していない）
  → 3.8節を再現可能な5カテゴリのmethodologyとして書き直し、各カテゴリの結果を明示
m-4（Minor）NOT_FOUND は POST endpoint に対する分類名として誤読を招く
  → M-2 と統合し ROUTE_NOT_FOUND へ改名（9.2節・10.1節・21章 V-2 を同期）

S-1（Suggestion）採用。10.1節の「一過性か」列を non-normative と明示
S-2（Suggestion）不採用。TooManyRedirects 用の REDIRECT_LOOP を新設しない
  （理由は10.1.2節 IL-3／19章 DEF-6.22-12）
S-3（Suggestion）採用。防御的分岐・guardに vacuous pass 防止の陽性対照を要求（17章）
```

**本Amendmentで production behavior の設計は変更していない。** Consumer-less Foundation・
CONTINUE対象拡大なし・`main.py`／featured media policy／runtime 無改修・
DI-5／6／7／8／9／11 対象外・後続Release番号未確定は、いずれも Amendment 前と同一である。

### 0.5 Architecture Amendment 2 の要約（Architecture Review 2 Finding 対応）

Architecture Review 2（Verdict: **Changes Required**、Blocking **0**件・Major 1件・
Minor 5件・Suggestion 3件）を受け、本 Amendment で Major 1件・Minor 5件を
すべて解消した。Suggestion は S2-1・S2-3 を採用し、S2-2 は理由を記録のうえ不採用とした。

Review 2 は **Review 1 の全 Finding（B-1／M-1／M-2／m-1〜m-4／S-1〜S-3）の closure を確認**し、
あわせて未解決の判断点であった **V-3（`__all__` へ Enum を公開する判断）を承認・close** した。
Production 設計・12値 taxonomy・`ROUTE_NOT_FOUND`・`reason=UNKNOWN` 既定値・
B-1 案C の骨格は、本Amendmentでも一切変更していない。

```text
M2-1（Major）GUARD-REASON-EXHAUSTIVE の規範仕様（17章）が D-1c より弱く、
  ast.Raise 基準・Name.id 照合であるため
  (a) 事前構築例外の `raise exc` 形、(b) Attribute 修飾呼び出し、(c) alias 束縛
  の3形で検査を迂回できた（M-1 が閉じたはずの穴が別の形で再発する）
  → 規範仕様を **module 内の全 ast.Call を走査する「全構築サイト」基準**へ改訂。
    callee は Name.id と Attribute.attr の双方で照合。raise 文の内側かで絞り込まない。
    補助guard 3種（GUARD-NO-ALIAS／GUARD-NO-PREBUILT-RAISE／
    GUARD-NO-POSITIONAL-REASON）で迂回経路を構造的に封じ、
    陽性対照を4形へ拡張した。production では positional reason を禁止し
    keyword `reason=` を必須とする（D-1d へ明記）。
    10.2節 D-1c／D-1d・12章 I-6・17章・18章（AC-6.22-23・-25）・20章 R-1・
    21章 V-1 を同期

m2-1（Minor）「新規ファイル追加も検出される」（11.7.1節）が untracked 追加に対し
  成立しない（git diff は untracked を報告しない。Review 2 が実測で反証）
  → 11.7.1節の記述を訂正し、11.7.4節へ補助guard
    `NOIMPACT-NO-UNTRACKED[<path>]`（`git status --porcelain
    --untracked-files=all`）を **v6.22 自前guard 側にのみ**追加設計した。
    既存guardへ追加しないことで GR-5（件数不変）と両立し、
    既存 baseline 3389 は不変に保たれる（GR-10 との関係も明記）

m2-2（Minor）17章 prefix 表が `COMPAT-DEP-` 行の直前の空行で破損していた
  → 空行を削除し `COMPAT-` 行の直後へ復帰

m2-3（Minor）NOPARSE- の検査スコープが未確定で、module 全体へ適用すると
  既存の正当な `response.json()`（L67・L169）で即FAILする
  → 対象を `_classify_request_exception` / `_classify_status_code` の
    2関数の ast.FunctionDef 本体に限定すると明記し、
    `_build_non_2xx_message()` / `upload()` を対象外と明記

m2-4（Minor）NOIMPACT-SCOPE-EXACT の equality が未分解で、v6.21 を subset に
  留める理由と非対称に見えた
  → containment（changed ⊆ allowed）と coverage（allowed ⊆ changed）へ分解。
    coverage が vacuous pass 防止の本体であること、固定baselineからの差分は
    revert 以外で単調非減少であるため後続Releaseでも安定であること、
    `__init__.py` が変更対象になる唯一の理由が D-3（Enum の `__all__` 公開）
    であることを明記

m2-5（Minor）GR に2つの記述不足（O(N) 保守コストと ratchet 性／保護対象の
  「追加」手順）があった
  → GR-9（後続Releaseは既存 baseline固定guard の allow-list を更新する必要が
    あり、古いguardは緩むが最新Release guardが最も厳格な保証を担う ratchet 構造）と
    GR-10（新しい保護対象パスの追加は新Release自前guardで行い既存guardへ
    追加しない。GR-5 の件数不変は精緻化時にのみ適用）を追加

S2-1（Suggestion）採用。AC-6.22-8 を「現時点で9件である全 raise 経路」へ改め、
  I-6 の件数固定禁止との役割分担を明示
S2-3（Suggestion）採用。BASELINE_COMMIT の誤指定による vacuous pass を
  NOIMPACT-BASELINE-PINNED（設計書記録値との文字列一致）＋
  NOIMPACT-BASELINE-IS-ANCESTOR（`git merge-base --is-ancestor`）で防ぎ、
  さらに **coverage 検査（m2-4）が「baseline が新しすぎる誤指定」に対する
  実効的な陽性対照として機能する**ことを論証した（11.7.4節）
S2-2（Suggestion）不採用。理由は10.1節末尾に記録（非規範2列の付録分離）
```

### 0.6 Architecture Amendment 3 の要約（Architecture Review 3 Finding 対応）

Architecture Review 3（Verdict: **Changes Required**、Blocking **0**件・Major 1件・
Minor 5件・Suggestion 3件）を受け、本 Amendment で Major 1件・Minor 5件を
すべて解消した。Suggestion は S3-2・S3-3 を採用し、S3-1 は将来候補として記録した。

Review 3 は **Review 2 の M2-1 を Not Closed** と判定した。Amendment 2 の guard 仕様が
「禁止する構文形を列挙する deny-list」であったため、**正規の構築サイトが併存する
実条件**において迂回可能であることを実測で示した（9形のうち8形が迂回成功）。
本Amendmentは方式そのものを **occurrence-context allow-list** へ転換する。

```text
M3-1（Major）guard が deny-list 方式であり、V-16 が列挙した迂回形
  （getattr / globals()[...] / functools.partial / factory・helper 経由、
    加えて dict/list registry・return 経由・既定引数埋め込み）を閉じられていない。
  Review 3 の実測：正規サイト併存条件で A1/A2/A3/A4/A11/A12/A13/A14 の
  8形が「どの guard も発火しない＝迂回成功」。とくに A4（共通ファクトリに
  reason 既定値を持たせる形）は現実的なリファクタであり M-1 の穴が復活する。
  → 17.1節を **GUARD-WMUE-CONSTRUCTION-SHAPE（単一の統合guard）**へ全面置換。
    識別子の「出現文脈」を allow-list で縛る方式に転換し、
    迂回形を列挙する必要をなくした。
    旧 GUARD-NO-ALIAS／GUARD-NO-PREBUILT-RAISE／GUARD-NO-POSITIONAL-REASON は
    統合guardへ吸収して**廃止**。これにより GUARD-NO-PREBUILT-RAISE が
    無関係な ValueError の raise 21件まで拘束していた**過剰拘束も解消**した
    （Review 3 が指摘した V-16 後半）。
    Positive Control を4形 → **9形**へ拡張。
    10.2節 D-1c／D-1d・12章 I-6（S3-3 により単一の構築形 Contract へ整理、
    I-6a／I-6b を吸収して廃止）・17章／17.1節・18章 AC-6.22-23／-25・
    20章 R-1／R-12／R-13・21章 V-16 を同期した。

m3-1（Minor）NOIMPACT-NO-UNTRACKED が tests/ を対象外にしており、
  untracked のテスト差分が git diff / git status の双方から見えない
  → 11.7.4節へ `NOIMPACT-NO-UNTRACKED-TESTS` を追加（v6.22 自前guard 側のみ）

m3-2（Minor）GR-9 の ratchet 原則と累積 Formal Regression の価値主張の関係が未記述
  → GR-9 へ「累積 Inventory の価値は Zero-Diff 保護の重畳ではなく、
    ①各Release時点の意図の履歴的記録 ②Zero-Diff 以外の全 contract の重畳保護に
    あり、Zero-Diff 面の権威的保証は最新guardが単独で担う」旨を追記

m3-3（Minor）保護対象 package が正当に削除される場合の手順が GR に欠けている
  → GR-11 を追加（GR-1／GR-5 の明示的な例外手順）

m3-4（Minor）NOIMPACT-BASELINE-PINNED の検証力の限界が未記述
  → 11.7.4節へ「本検査は設計書↔実装の転記整合を確認する文書的検査であり、
    誤指定の実効的検出は coverage（新しすぎる場合）と
    BASELINE-TRACKED／containment（古すぎる場合）が担う」旨を明記

m3-5（Minor）`**kwargs` 展開形の扱い（安全側 false positive）が未記述
  → 17.1節と I-6 へ「`**kwargs` 展開による構築は禁止」を明記

S3-1（Suggestion）shared zero-diff registry 化：本Releaseでは実装対象にしない。
  19章 DEF-6.22-14 として将来候補に記録
S3-2（Suggestion）採用。`.gitignore` 拡大で blind spot が広がる点を 20章 R-13 へ追記
S3-3（Suggestion）採用。I-6 を「WMUE の構築は raise 直下の直接呼び出しに限り
  reason= を keyword で明示する」という**単一の構築形 Contract**へ整理し、
  I-6a／I-6b を廃止した
```

**本Amendmentで変更していないもの**：Consumer-less Foundation・production behavior
（12値 taxonomy・`ROUTE_NOT_FOUND`・`reason=UNKNOWN` 既定値・Enum の `__all__` 公開）・
B-1 案C／NOIMPACT の骨格・`main.py`／policy／runtime 無変更・CONTINUE 対象拡大なし・
DI-5／6／7／8／9／11 対象外・**既存 Formal Regression baseline 3389 不変**・
後続Release番号未確定。本Amendmentの変更は**すべてテスト側 guard 仕様の記述**に閉じており、
Production Code の変更範囲（2ファイル）・既存テスト更新範囲（X-1〜X-6）は動かない。

### 0.7 Architecture Amendment 4 の要約（Architecture Review 4 Finding 対応）

Architecture Review 4（Verdict: **Changes Required**、Blocking 1件・Major **0**件・
Minor 4件・Suggestion 2件）を受け、本 Amendment で Blocking 1件・Minor 4件を
すべて解消した。Suggestion は S4-1・S4-2 双方を採用した。

Review 4 は **Review 3 の全 Finding（M3-1／m3-1〜m3-5／S3-1〜S3-3）の closure を確認**し、
occurrence-context allow-list 方式（Amendment 3）そのものは維持したまま、
**設計書内部の矛盾**（10.1節が規定する docstring が自guardに違反する）と、
allow-list の**過小**（正当な型位置参照を拒む）を指摘した。本Amendmentはいずれも
allow-list を精緻化するだけで解消し、**occurrence-context allow-list という方式の
骨格・許可2形（クラス定義／`raise` 直下の直接構築）は変更していない**。

```text
B4-1（Blocking）17.1節 手順4（文字列間接参照の封鎖）が、10.1節が規定する
  Enum docstring「WordPressMediaUploadErrorの安全な失敗分類。」を
  ast.Constant(str) として検出し違反とする。設計書内部の2つの規範セクションが
  両立しなかった（実測：10.1節＋10.2節どおりの production code 模写を
  guardへ通すと S4-STR で違反）
  → 手順4 から **module／ClassDef／FunctionDef／AsyncFunctionDef の body 先頭
    docstring** を除外する。除外は名前解決に使われない静的テキストのみに
    限定するため getattr／globals() 等の動的検出力は落ちない。
    v6.11 `OpenAIImageGenerationErrorReason` の docstring
    「`OpenAIImageGenerationError`の安全な失敗分類。」が同型の慣行を
    先例として持つことを根拠として明記した（S4-1）。
    10.1節・14.1.1節・17.1節・12章 I-6・18章 AC-6.22-23(b) を同期

m4-1（Minor）文字列検査（手順4）が意図的に分割されたリテラル
  （"WordPressMediaUpload" + "Error" 等）を検出できないことが未記載
  → 17.1節へ「本検査は**未分割の**文字列リテラルのみを対象とする。
    分割・f-string 部分結合・type comment は静的追跡が構造的に不可能であり、
    偶発的な reason 漏れという脅威モデルの外（意図的な難読化の防止は
    本guardの目的ではない）」旨を明記

m4-2（Minor）allow-list の2形（クラス定義／raise 直下の構築）が、
  構築を一切伴わない正当な「型位置」参照（引数注釈・戻り値注釈・
  AnnAssign 注釈・except節・isinstance／issubclass 第2引数）まで
  違反として拒む（過小）
  → **案Aを採用**し、allow-list へ (c)〜(g) の5種の型位置を追加した。
    いずれも Call ノードではなく構築を行わないため、手順5（構築形検査）の
    対象にはならない。追加後も Review 3 の全18攻撃形が引き続き検出される
    ことを実測で確認した（regression 0件）。10.2節 D-1c・12章 I-6・
    17.1節・18章 AC-6.22-23(a)・20章 R-12 を同期

m4-3（Minor）NOIMPACT-NO-UNTRACKED-TESTS のパス正規化が未規定
  （`git status --porcelain` は repo-root 相対パスを返すため
    `_allowed_test_changes`（basename集合）との比較方法が曖昧だった）
  → 11.7.4節へ「`Path(line[3:]).name` により basename へ正規化する
    （v6.21 の tests ブロックと同一方式）」を明記。18章 AC-6.22-26 へ反映

m4-4（Minor）手順4が部分文字列判定であることが明示されていなかった
  → 17.1節へ「判定は部分文字列一致であり、docstring 除外後も
    `WordPressMediaUploadErrorReason` を含む文字列は引き続き違反となる」
    旨を明記し、陽性対照 P-10 として追加

S4-1（Suggestion）採用。v6.11 Reason Enum docstring precedent を
  B4-1 の判断根拠として17.1節へ記録
S4-2（Suggestion）採用。guard は単一関数として実装し、実ファイル・
  全陽性対照（P-1〜P-10）・全負の対照（N-1〜N-9）・実ファイルへ
  **同一関数を適用する**契約を17.1節へ明記
```

**本Amendmentで変更していないもの**：occurrence-context allow-list という方式の骨格
（許可2形＝クラス定義／`raise` 直下の直接構築を核とすること）・Consumer-less Foundation・
production behavior（12値 taxonomy・`ROUTE_NOT_FOUND`・`reason=UNKNOWN` 既定値・
Enum の `__all__` 公開）・B-1 案C／NOIMPACT の骨格・`main.py`／policy／runtime 無変更・
CONTINUE 対象拡大なし・DI-5／6／7／8／9／11 対象外・**既存 Formal Regression baseline
3389 不変**・後続Release番号未確定。本Amendmentの変更は**すべてテスト側 guard 仕様の
記述**に閉じており、Production Code の変更範囲（2ファイル）・既存テスト更新範囲
（X-1〜X-6）は動かない。

### 0.8 Architecture Review 5 の要約（最終Architecture Review）

Architecture Review 5（Verdict: **Approved with Suggestions**、Blocking 0件・
Major 0件・Minor 1件・Suggestion 1件）は、Review 4 の全Finding（B4-1・m4-1〜m4-4・
S4-1・S4-2）のclosureを確認し、occurrence-context allow-list方式の最終形
（`GUARD-WMUE-CONSTRUCTION-SHAPE`、許可7形＋docstring除外＋文字列間接参照封鎖）
に対して独立実装したreference guardとの18攻撃形＋型位置3形の突き合わせを行い、
不一致0件を確認した。

```text
M5-1（Minor）match-case class pattern（`case WordPressMediaUploadError():`）が
  allow-listに含まれず、pattern matchingによる分類コードを書いた場合に
  過剰拒否となりうる。現行production codeには該当形が存在せず緊急性は低い
  → Deferredとして記録。将来match-case形式の利用が必要になった時点で
    Architecture Reviewにて再検討する
S5-1（Suggestion）git statusのpath出力にrename等の複合形式が含まれる可能性は
  untracked（??）専用検査のため実害なし。11.7.4節へ「本検査は??行のみを対象と
  する」旨を明記することを推奨 → 採否は次回設計書更新時の判断とし、
  本Reviewでは記録のみ
```

Review 4までに確立したtaxonomy・mapping・guard仕様・NOIMPACT設計はいずれも
変更されていない。**Architecture Reviewは本Review 5をもって収束した。**

### 0.9 Production Implementation〜Formal Regression の実績

**Production Implementation**：`src/wordpress_media/wordpress_media_uploader.py`・
`src/wordpress_media/__init__.py`の2ファイルへ、本設計書10章・12章・14.1節の
規定どおりに実装した（Enum 12値・`__init__`・分類関数2本・9 raise経路への
`reason=`付与・`__all__`拡張）。既存9経路のmessage・`from exc`・分岐条件・
`upload()`のsignature・成功時の`MediaUploadResult`はAST式単位でHEAD版と
完全一致することを確認した。

**Implementation Review 1**（Verdict: Approved with Suggestions、Blocking 0・
Major 0・Minor 4・Suggestion 3）：

```text
m1  NOPARSE-がstr(exc)を検出しない（17章に明記されているにも関わらず）
m2  NOPARSE-SCOPEがハードコードTrueのvacuous assertion
m3  DEP allow-list検査対象（17章・AC-6.22-15）が`src/wordpress_media/`のまま
    package全体を指しており、実際には`wordpress_media_uploader.py`単体を
    検査していることと表現が食い違う
m4  未使用定数`_SAFE_LABEL_PATTERN_OK`・no-op `pass`ブロックのdead code 2件
s1  NOPARSE禁止形6形（str(exc)／exc.args／response.text／.json()／.headers／
    .content）それぞれへ独立した陽性対照を追加することを提案
s2  MSG-R2の_build_non_2xx_message()追加分岐カバレッジ拡張（既存v6.9でカバー済み）
s3  SEC-1／SEC-2の冗長性整理（害なし）
```

**Implementation Amendment 1**：m1〜m4を解消（`str(exc)`検出追加・
`NOPARSE-SCOPE-EXISTS`／`NOPARSE-SCOPE-WOULD-VIOLATE`の4非vacuous assertionへ
置換・DEP対象を`wordpress_media_uploader.py`単体と明記（17章・AC-6.22-15）・
dead code 2件削除）。s1を採用し6形独立の陽性対照へ拡張。s2は不採用、s3は維持。
新規E2Eは316→324アサーションへ増加。Production Code・既存E2E 4ファイルは無変更。

**Implementation Review 2**（Verdict: Approved with Suggestions、Blocking 0・
Major 0・Minor 1・Suggestion 1）：m1〜m4・s1のclosureを、反証テスト（vacuous
でないことの確認）・独立reference実装との突き合わせ（不一致0件）・6形の
「すり替わりなし」確認により独立検証した。

```text
M2R-1（Minor）17章NOPARSE-禁止一覧とAC-6.22-13が依然完全に同期していない
  （AC-6.22-13は`message`を含むが17章は含まない。Amendment 1はstr(exc)の
  同期のみを行い、この既存ギャップは未解消のまま残った）
  → 本Documentation Integrationで17章へ`message`を追加し解消（0.10節）
S2R-1（Suggestion）`str(...)`検出がAC-13の例示（str(exc)）より広く、
  任意のstr()呼び出しを禁止する実装になっている。両分類関数には正当な
  str()呼び出しが存在しないため実害はないが、実装意図をコメントで
  明記すると将来の誤解を防げる → 採否未定のままDeferredとして記録
  （0.10節・19章）。test file自体は変更しない
```

**Formal Regression**：正式Inventory25ファイル（`test_e2e_v1_11_0_save_result.py`・
`test_e2e_v5_9_0_*.py`・`test_e2e_v6_0_0_*.py`〜`test_e2e_v6_22_0_*.py`）を
個別実行し、既存24ファイル3389/3389 PASS（baseline完全維持）＋新規v6.22.0
324/324 PASS＝総合**3713/3713 PASS**を確認した（FAIL 0・SKIP 0・全ファイル
終了コード0・既知差分0・外部API実接続0・credential使用0・Git状態不変）。

### 0.10 Documentation Integration（本工程）

Formal Regression完了を受け、本設計書・`docs/ROADMAP.md`・`docs/architecture.md`・
`docs/CHANGELOG.md`の4文書へ反映した。

```text
M2R-1解消：17章 NOPARSE- 行の禁止参照一覧へ `message` を追加し、
  AC-6.22-13（str(exc)／message／exc.args／response.text／response.json()／
  response.headers／response.content の7項目）と完全同期させた（17章参照）

S2R-1記録：19章 Deferred Items へ「str(...)検出の広さに関する実装意図の
  明記」を追加。test file（tests/test_e2e_v6_22_0_*.py）は変更しない
  （Implementation Review 2・Amendment指示のとおり）
```

**Production Code・tests・main.pyはいずれも本工程で変更していない。** taxonomy・
mapping・guard仕様・NOIMPACT設計・Consumer-less Foundation・CONTINUE対象拡大なし
はArchitecture Amendment 4以降と同一である。

### 0.11 Release Review の結果と反映（Finalize）

Release Review（Verdict: **Approved with Suggestions**、Blocking 0件・Major 0件・
Minor 3件・Suggestion 1件）を受け、Finalizeとして以下を解消した。

```text
[Minor]
RR-M-1  14.5節が「Architecture Amendment 4で本設計書のみ変更、14.1〜14.4は
        未実施」という当時の記録のまま残存し、0.2節が正しく記録している
        「Documentation Integrationで4文書を変更済み」という事実と同一
        設計書内で矛盾していた
        → 14.5節を「Architecture Amendment 4時点（歴史的記録）」として
          明示的に過去形へ改め、Documentation Integration（0.2節）・
          Release Review Finalize（本節）を経て14.1〜14.4がいずれも
          実施済みであることを明記した

RR-M-2  14.4節が「ROADMAPエントリを`[ ]`→`[x]`へ更新」を実施済み前提で
        記載していたが、Documentation Integration時点ではRelease Review
        Pendingのため`[ ]`のまま維持するのが正しい判断であり、
        14.4節がその運用を反映していなかった。14.6節も「本工程では
        適用しない」という古い位置づけのまま残存していた
        → 14.4節へ「Release Review承認まで`[ ]`を維持し、Finalize時に
          `[x]`へ更新する」運用を明記し、実際にRelease Review Finalizeで
          `[x]`へ更新した（docs/ROADMAP.md）ことを追記した。14.6節の
          見出しを「Release Review Finalizeで適用済み」へ改め、
          architecture.md節名が計画時の案（「…Classification層」）ではなく
          実際に作成した「…Classification Foundation層」（正式名称と
          一致）である旨を明記した

RR-M-3  14.4節は「既存のv6.9.0節へ『reason分類はv6.22.0で追加』のポインタを
        追記する」ことを計画していたが、Documentation Integration時点では
        未実施のまま残っていた
        → Release Review Finalizeで`docs/architecture.md`のv6.9.0
          「WordPress Media Upload Foundation層」節末尾へポインタを追記した

[Suggestion]
RR-S-1  設計書タイトル末尾の「— Architecture Design」表記が、Architecture
        Designより後の全工程（Implementation・Formal Regression・
        Documentation Integration・Release Review）を含む現状の内容範囲
        より狭い → v6.21.0設計書（article_featured_media_runtime_wiring.md）
        も同一パターンをRelease完了まで運用しているprecedentと一致するため、
        本Releaseでは変更せず記録のみとする
```

Architecture・Scope（Consumer-less Foundation維持・Runtime Zero Diff成立・
`main.py`／policy／runtime／既存11 package無改修・CONTINUE対象拡大なし）・
Production behavior（Zero Behavior Change）・既存3389件不変・Formal Regression
25ファイル3713/3713 PASSのいずれにも問題はなく、Architectureからの逸脱もない。
RR-M-1〜RR-M-3はいずれも設計書自身の記述整合の訂正であり、Production Code・
testsのロジックは変更していない。

**Release Reviewを経て、Release 6.22として完了した。**

---

## 1. Background

### 1.1 DI-10 の正式な定義（Repository上の記述）

`docs/ROADMAP.md` L1085-1089：

> **WordPress Media Upload Failure Reason Classification（DI-10）**（次候補・未着手）：
> `WordPressMediaUploadError`へ、v6.11.0 `OpenAIImageGenerationErrorReason`と同型の
> 分類Enum（型・HTTPステータスのみに基づき、message解析を行わない）を純追加する。
> v6.9.0のPublic API変更を伴うため独立Releaseを要する。Image Generation Fallback
> Policy（v6.19.0）のDI-4着手前再評価（ORD-1）の対象

`docs/design/image_generation_fallback_policy_foundation.md` L2394（20章 DI-10）も同旨であり、
あわせて次を規定している。

- 本Release（v6.19.0）では実施しない（N-17）
- **DI-10実施時には、v6.19.0 の AC-24 および `COMPAT-` Scenario（`WordPressMediaUploadError`
  に `reason` 属性が存在しないことを固定する否定的アサーション）が必然的にFAILする。
  これは設計上の既知差分であり、無関係なRegressionとして扱ってはならない**

同 L2651-2661（23章 AC-24 注記）：

> Deferred Item DI-10 が実施され v6.9 へ reason 分類Enumが追加された時点で、
> 本ACおよび対応E2Eは**必然的にFAILする**。

すなわち、**本Releaseで既存E2Eの一部contractを意図的に更新することは、v6.19.0 の設計時点で
既に予告・承認されている。** 本設計書11章でその範囲を1アサーション単位まで確定する。

### 1.2 なぜ今なのか（v6.21.0 完了によって状況が変わった）

v6.19.0 が DI-10 を Deferred とした時点では、`decide_image_generation_fallback()` は
Consumer-less であり、`MEDIA_UPLOAD_FAILED → PROPAGATE_ORIGINAL_ERROR` という判断に
実行時の帰結が存在しなかった。

Release 6.21.0（`docs/design/article_featured_media_runtime_wiring.md`）で
`ArticleFeaturedMediaRuntime` が `main.py` の記事ループへ配線されたことにより、
`PROPAGATE_ORIGINAL_ERROR` は **「その記事を WordPress へ投稿せず、`log_article(result="failed",
post_id=None)` を記録して次の記事へ進む」** という具体的な帰結を持つようになった
（`main.py` L425-433、v6.21.0 設計書7.4節 F-4／F-5）。

したがって現在、`AI_IMAGE_GENERATION_ENABLED=true` の運用下では次が成立する。

```text
WordPress Media Upload が一過性に失敗（HTTP 429／5xx／timeout／connection）
  → WordPressMediaUploadError
  → v6.19 policy: MEDIA_UPLOAD_FAILED → PROPAGATE_ORIGINAL_ERROR
  → main.py: 記事そのものを投稿しない
```

これは v6.19.0 §10.4 C-5 が明示的に受諾したトレードオフであり、v6.21.0 §1.1 が ORD-2 に基づき
「そのまま受容する」と判断した事項である。本Releaseはこの受容判断を覆すものではない
（**CONTINUE対象の拡大は本Releaseの対象外。7章 N-1**）。本Releaseが解消するのは、その判断を
将来見直すために必要な**構造情報が現在まったく存在しない**という一点である。

### 1.3 現在「構造的に不可能」であること

`src/wordpress_media/wordpress_media_uploader.py` L24-26：

```python
class WordPressMediaUploadError(RuntimeError):
    """WordPress Media APIへの通信・応答に関する失敗を表す唯一の専用例外。"""
    pass
```

`RuntimeError` の空subclassであり、`reason` も HTTPステータスコードも保持しない。
v6.21.0 設計書 §1.2 E-3 の表現では「timeout／connection／4xx／5xx の区別は**構造的に不可能**」。

一方、同ファイル L63-64 `_build_non_2xx_message()` は
`f"WordPress Media API returned HTTP {response.status_code}"` を組み立てており、
**status code は既に手元にあるが、message文字列へ埋め込まれた後に構造情報としては捨てられている。**
下流（v6.19 policy）が message を解析することは v6.19 §13.2 で明確に禁止されているため、
現状この情報は下流から利用不能である。

本Releaseは「情報を新たに外部から取得する」のではなく、**既に手元にある構造情報を、
message文字列とは別の機械可読な属性として保持する**ことのみを行う。

---

## 2. Problem Statement

### 2.1 現状の欠落

| ID | 欠落 |
|---|---|
| **P-1** | `WordPressMediaUploadError` は失敗の種別を機械可読な形で保持しない |
| **P-2** | 下流（v6.19 policy、将来の DI-5 observability、将来の CONTINUE拡大判断）は、message解析禁止の制約下で失敗種別を一切識別できない |
| **P-3** | 一過性障害（429／5xx／timeout）と恒久的な設定不備（401／403／413／415）が同一の扱いになり、運用者は「何を直せばよいか」をログから判断できない |
| **P-4** | 9箇所の `raise` はいずれも message のみで区別されており、message文字列は Security Contract 上「安全化された自由文」であって分類キーではない |

### 2.2 分類を持たないまま進めた場合の危険

- CONTINUE対象の拡大（将来のRelease）を設計する材料が永久に得られない
- DI-5（observability）がログへ記録できるのは `MEDIA_UPLOAD_FAILED` という単一のcategoryのみで、
  運用上の診断価値がほぼ無い
- 将来 message を解析する実装が「情報が他に無いから」という理由で混入する誘因が残る
  （v6.19 §13.2 の禁止事項への圧力）

### 2.3 本Releaseが解決しないこと

本Releaseは **分類の付与のみ**を行い、分類に基づく**振る舞いの変更は一切行わない**。
一過性のWordPress障害で記事が投稿されない現在の挙動は、本Release後もそのまま残る
（7章 N-1、11.4節）。

---

## 3. Repository Survey Findings

### 3.1 対象package の現状

```text
src/wordpress_media/
├── __init__.py                   18行（__all__ 3 symbol）
├── media_upload_result.py        21行（MediaUploadResult）
└── wordpress_media_uploader.py  210行（WordPressMediaUploadError / WordPressMediaUploader）
```

依存は `os` / `re` / `requests` / `.media_upload_result` のみ（同ファイル L6-11）。

### 3.2 `WordPressMediaUploadError` の raise 経路（全9箇所・棚卸し確定）

`src/wordpress_media/wordpress_media_uploader.py` の `upload()` 内、**9箇所**。
（前工程調査では「8箇所」と概算していたが、`source_url` / `mime_type` がそれぞれ
「キー欠落」と「型不正」の2 raise を持つため、正確には9箇所である。）

| ID | 行 | 発生条件 | 現在のmessage | `from exc` |
|---|---|---|---|---|
| **R-1** | L161 | `requests.post()` が `requests.RequestException` を送出 | `"WordPress Media APIへの通信に失敗しました"` | あり |
| **R-2** | L166 | `not (200 <= response.status_code < 300)` | `_build_non_2xx_message(response)`（動的） | なし |
| **R-3** | L171 | 2xx応答の `.json()` が `ValueError` | `"WordPress Media APIの成功レスポンスが不正です"` | あり |
| **R-4** | L176 | 2xx応答のJSONが `dict` でない | `"WordPress Media APIの成功レスポンスが不正です"` | なし |
| **R-5** | L182 | `id` が欠落／`bool`／非`int`／`< 1` | `"…不正です（id）"` | なし |
| **R-6** | L187 | `source_url` キー欠落 | `"…不正です（source_url）"` | なし |
| **R-7** | L192 | `source_url` が `None` でも `str` でもない | `"…不正です（source_url）"` | なし |
| **R-8** | L197 | `mime_type` キー欠落 | `"…不正です（mime_type）"` | なし |
| **R-9** | L202 | `mime_type` が `None` でも `str` でもない | `"…不正です（mime_type）"` | なし |

各経路で利用可能な構造情報：

- **R-1**：`requests` 例外の**型**（subclass）
- **R-2**：`response.status_code`（`int`）
- **R-3〜R-9**：外部由来の構造情報なし（どの検証ステップで落ちたかのみ）

### 3.3 `requests` 例外階層の実測（project venv）

分類の優先順位を決めるうえで決定的な事実であるため、`venv/Scripts/python.exe` で実測した。

```text
requests 2.34.2

RequestException  -> OSError, Exception
ConnectionError   -> RequestException
Timeout           -> RequestException
ConnectTimeout    -> ConnectionError, Timeout, RequestException   ★多重継承
ReadTimeout       -> Timeout, RequestException
SSLError          -> ConnectionError, RequestException
ProxyError        -> ConnectionError, RequestException
TooManyRedirects  -> RequestException
URLRequired       -> RequestException
InvalidURL        -> RequestException, OSError, ValueError
MissingSchema     -> RequestException, OSError, ValueError
ChunkedEncodingError -> RequestException
ContentDecodingError -> RequestException, OSError, HTTPError
RetryError        -> RequestException
HTTPError         -> RequestException
```

**★ `ConnectTimeout` は `ConnectionError` と `Timeout` の両方のsubclassである。**
したがって `isinstance(exc, Timeout)` を `isinstance(exc, ConnectionError)` より
**先に**判定しなければ `ConnectTimeout` が `CONNECTION` へ落ちる。
これは v6.11 `_classify_api_error()`（L122-132）が
`openai.APITimeoutError` を `openai.APIConnectionError` より先に判定し、
コメントで「`APIConnectionError`のsubclassのため、`APIConnectionError`より先に判定する」と
明記しているのと**同型の制約**である。本設計はこの precedent に従う（9.2節・20章 R-5）。

### 3.4 v6.11 precedent（`OpenAIImageGenerationErrorReason`）

`src/openai_image_generation/openai_image_generator.py` L56-79：

```python
class OpenAIImageGenerationErrorReason(Enum):
    AUTHENTICATION = "authentication"
    PERMISSION_DENIED = "permission_denied"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    REQUEST_REJECTED = "request_rejected"
    SERVER_ERROR = "server_error"
    INVALID_RESPONSE = "invalid_response"
    UNKNOWN = "unknown"          # 9値


class OpenAIImageGenerationError(RuntimeError):
    def __init__(self, message: str, reason: OpenAIImageGenerationErrorReason) -> None:
        super().__init__(message)
        self.reason = reason      # reason は必須引数。validation は行わない
```

`__all__` に `OpenAIImageGenerationErrorReason` を含む（同package `__init__.py` L14-18）。
`_classify_api_error()` は `(message, reason)` の**組**を返す純粋関数であり、
`raise` せず、message／response body／status code の生値を読まない（同 L97-104 docstring）。

本設計が v6.11 から**継承する**点と**意図的に逸脱する**点は 8.2節・9.4節で明示する。

### 3.5 v6.19 policy が `WordPressMediaUploadError` をどう扱っているか

`src/image_generation_fallback_policy/image_generation_fallback_policy.py` L152-153：

```python
    elif isinstance(error, WordPressMediaUploadError):
        category = ImageGenerationFailureCategory.MEDIA_UPLOAD_FAILED
```

**`reason` を一切読まない。** `isinstance` による型判定のみである
（`OpenAIImageGenerationError` の分岐（L136-151）だけが `getattr(error, "reason", None)` を読む）。

これは本Releaseにとって決定的に重要な事実である。すなわち
**`WordPressMediaUploadError` へ `reason` 属性を追加しても、v6.19 policy の出力は
12 reason すべてに対して `MEDIA_UPLOAD_FAILED` / `PROPAGATE_ORIGINAL_ERROR` のまま不変である**
（11.4節・18章 AC-6.22-14）。

### 3.6 v6.12 Wiring層は例外を再wrapしない

`src/generated_image_wordpress_media/generated_image_wordpress_media_uploader.py` は
`try`/`except` を1つも持たず、`WordPressMediaUploader.upload()` の例外はそのまま通過する
（`raise` は引数validationの `ValueError` / `TypeError` のみ）。
したがって `WordPressMediaUploadError` は **object identity を保ったまま**
v6.14 orchestrator → v6.20 runtime → v6.21 `main.py` まで到達する。
`reason` 属性は経路上で失われない。

### 3.7 `WordPressMediaUploadError` の全construction site（production + tests）

production では `wordpress_media_uploader.py` の9箇所のみ。
それ以外は**すべてテストコード**であり、**10箇所すべてが message 1引数のみの形式**である。

| ファイル | 行 | 形式 |
|---|---|---|
| `tests/test_e2e_v6_12_0_generated_image_wordpress_media_upload_wiring_foundation.py` | 506 | `WordPressMediaUploadError("WordPress Media APIへの通信に失敗しました")` |
| `tests/test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py` | 451 | `WordPressMediaUploadError("y")` |
| 同上 | 664 | `WordPressMediaUploadError(m)` |
| 同上 | 795 | `WordPressMediaUploadError(_variant)` |
| 同上 | 980 | `WordPressMediaUploadError("first call")` |
| 同上 | 981 | `WordPressMediaUploadError("second call")` |
| 同上 | 995 | `WordPressMediaUploadError(...)`（secret-bearing message） |
| 同上 | 1226 | `WordPressMediaUploadError("x")` |
| 同上 | 1303 | `WordPressMediaUploadError("compat check")` |
| `tests/test_e2e_v6_20_0_article_featured_media_runtime_foundation.py` | 583 | `WordPressMediaUploadError("probe wp upload failure")` |

**この事実が、`reason` を必須引数にしない判断（10.2節 D-1）の直接の根拠である。**

### 3.8 本Releaseの変更を拒否する既存E2Eアサーション（走査methodologyと全数）

**（Amendment 1で全面改訂：m-3・B-1対応）** Amendment 前の本節は
`__all__`／`hasattr`／`reason` のパターン走査のみを行い、**パスベースの
zero-diff guard を走査対象に含めていなかった**。その結果 X-5・X-6 を見落とし、
Review 1 の Blocking B-1 を招いた。本節を、後続Releaseでも再利用できる
再現可能な走査手順として書き直す。

#### 3.8.1 走査methodology

既存テストが本Releaseの変更を拒否しうる形態を5カテゴリに分け、各々を独立に走査する。

| # | カテゴリ | 検出手段 | 本Releaseでの結果 |
|---|---|---|---|
| **C-A** | Public API 集合の固定（`__all__` 完全一致・`dir()` 比較・`len(__all__)`） | `tests/` 全体の `__all__` 出現箇所を全件精査 | **3件**（X-1・X-2・X-4） |
| **C-B** | 属性面の否定的固定（`hasattr(...)` に対する `check_false`） | `tests/` 全体の `hasattr` 出現箇所を全件精査 | **1件**（X-3）。`tests/test_e2e_v6_19_0_*.py` L847-852 の `DEFENSE-PRECONDITION-NO-REASON` は `OpenAIImageGenerationError.__new__` 由来であり本Releaseと無関係 |
| **C-C** | signature／型階層の固定（`inspect.signature`／`__mro__`／`__bases__`／`issubclass`） | 同種パターンの全件精査 | **0件**（`WordPressMediaUploadError` を対象とするものは存在しない。`COMPAT-OPENAI-ERROR-SIGNATURE` は OpenAI 側のみ） |
| **C-D** | **パス指定の zero-diff guard**（`git diff --quiet -- <path>`／`git diff --name-only -- <path>`） | `git diff` を用いるテストを列挙し、正式 Inventory 24ファイルに絞って各々の対象パス一覧を精査 | **2件**（X-5・X-6。いずれも `tests/test_e2e_v6_21_0_*.py`） |
| **C-E** | package source 全文への部分文字列guard（`check_not_contains`／正規表現） | `tests/test_e2e_v6_9_0_*.py` の `_combined_source`／`_uploader_source` 利用箇所を精査 | **更新不要だが実装制約となる**（14.1.1節へ集約） |

C-D の走査では、`git diff` を用いるテストが `tests/` 全体で45ファイル存在するものの、
**正式 Formal Regression Inventory（24ファイル）に属するのは
`v5_9_0`・`v6_0_0`〜`v6_4_0`・`v6_21_0` の7ファイルのみ**であり、
うち `v5_9_0`〜`v6_4_0` の6ファイルは Retry 系パスのみを対象とし
（`src/retry_*`／`src/workflow_*`／`src/scheduler`／`src/ai`／`src/execution_history`）、
かつ baseline commit を固定しない HEAD 基準比較であるため本Releaseの影響を受けない
ことを確認した。

#### 3.8.2 全数（X-1〜X-6）

| ID | ファイル | 行 | アサーション | 分類 |
|---|---|---|---|---|
| **X-1** | `tests/test_e2e_v6_9_0_wordpress_media_upload_foundation.py` | 209-213 | `PM-3b. __all__完全一致` → `["MediaUploadResult", "WordPressMediaUploadError", "WordPressMediaUploader"]` | C-A |
| **X-2** | `tests/test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py` | 1297-1301 | `COMPAT-V69-ALL-UNCHANGED. v6.9の__all__が不変` | C-A |
| **X-3** | 同上 | 1303-1309 | `COMPAT-WP-NO-REASON-ATTR. WordPressMediaUploadErrorインスタンスにreason属性が追加されていない` | C-B |
| **X-4** | `tests/test_e2e_v6_20_0_article_featured_media_runtime_foundation.py` | 993-997 | `COMPAT-V609. wordpress_media.__all__が不変` | C-A |
| **X-5** | `tests/test_e2e_v6_21_0_article_featured_media_runtime_wiring.py` | 845-868（`"src/wordpress_media"` は L853）・893 | `NOIMPACT-UNCHANGED[src/wordpress_media]`。`_protected_paths` に `"src/wordpress_media"` を含み、baseline commit `8d8950684a305bc93c824866578cb30c6b2e4fdd`（v6.20.0 Release時点）からの差分ゼロを要求する | **C-D（Amendment 1で追加）** |
| **X-6** | 同上 | 897-921 | `NOIMPACT-TESTS-SCOPE`。`_allowed_test_changes = {v6_13_0, v6_20_0, v6_21_0}` 以外の `tests/` 差分を禁止する | **C-D（Amendment 1で追加）** |

**上記6件が全数である。** 対処方針は11.7節（案C）で確定する。

`tests/test_e2e_v6_12_0_*.py` の `__all__` アサーション（L324・L327）は
`generated_image_wordpress_media` を対象としており、本Releaseの変更対象外である。

なお X-3 は、アサーション文言自身に
「**DI-10実施時にこのScenarioは既知差分として更新対象となる。20章 DI-10参照**」
と明記されている。すなわち本Releaseによる更新は、テスト作成時点で予告済みである。
一方 **X-5・X-6 は予告されていない**。これは v6.21.0 が baseline 固定 guard を
導入した際に「保護対象を後続Releaseが正当に変更する場合の手順」を定めなかった
ためであり、11.8節でその一般則を補う。

### 3.9 `WordPressMediaUploadError` の型・messageを固定している既存アサーション

`upload()` の失敗時 message を検証するアサーションは `tests/test_e2e_v6_9_0_*.py` に多数存在する。
本Releaseは**messageを1文字も変更しない**（9.5節 G-4）ため、これらはいずれも更新不要である。
Architecture Review では、この「message凍結」が実装で守られることを重点確認対象とする（21章 V-4）。

---

## 4. DI-10 の意味の確定

### 4.1 採用する定義

> **`WordPressMediaUploadError` に、WordPress Media Upload 固有の失敗構造から導出した
> 分類Enum `WordPressMediaUploadErrorReason` を純追加し、既存9 raise経路それぞれへ
> 構造情報（例外型・HTTPステータスコード）のみに基づく reason を割り当てる。
> 例外型・例外message・`upload()` の signature・成功時の戻り値・成功／失敗の分岐条件は
> いずれも変更しない。**

### 4.2 採用しない意味（推測による混入の排除）

| 排除する解釈 | 理由 |
|---|---|
| 一過性障害を CONTINUE 対象へ拡大する | v6.19 §DEF-9・ORD-3 の領域。本Releaseの対象外（7章 N-1） |
| `ImageGenerationFailureCategory` を細分化する | v6.19 の Public API 変更。別Release（7章 N-2） |
| retry／再試行を導入する | DI-6 の領域（7章 N-5） |
| reason をログへ記録する | DI-5 の領域（7章 N-4） |
| status code を属性として保持する | 10.3節 D-2 で明示的に不採用 |
| message から失敗種別を推定する | v6.19 §13.2 の禁止事項。9.5節 G-3 で絶対禁止 |

---

## 5. Terminology

| 用語 | 定義 |
|---|---|
| **reason** | `WordPressMediaUploadErrorReason` の値。固定された分類ラベルのみで構成され、秘密情報・可変の生データを含まない |
| **構造情報** | 例外の**型**（`isinstance`）と `response.status_code`（`int`）のみ。message文字列・response body・header・credential は構造情報に含めない |
| **transport 層の失敗** | HTTP応答を1つも受け取れなかった失敗（R-1） |
| **status 層の失敗** | HTTP応答は受け取ったが 2xx でなかった失敗（R-2） |
| **body 層の失敗** | HTTP 2xx を受け取ったが応答本文が利用不能だった失敗（R-3〜R-9） |
| **Zero Behavior Change** | 成功時の戻り値・失敗時の例外型・失敗時のmessage・成功／失敗の分岐条件のいずれも変更しないこと |
| **Runtime Zero Diff** | **（Amendment 1で表現を厳密化：m-2対応）** v6.21.0 E2E `_protected_paths` の22パスから `src/wordpress_media` を除いた**21パス**（`main.py` は同listに含まれないため別途）および `main.py` が無変更であること。具体的な列挙は11.6節・18章 AC-6.22-16 を参照。「画像系11 Foundation」という既存docsの語とは集合が異なるため、本設計書では用いない |

---

## 6. Goals

| ID | Goal |
|---|---|
| **G-1** | WordPress Media Upload の**実際の失敗構造**から導出した reason taxonomy を確定する |
| **G-2** | 既存9 raise経路すべてに reason を割り当て、未分類経路を1つも残さない |
| **G-3** | 分類は構造情報のみに基づき、message解析を一切行わない |
| **G-4** | Zero Behavior Change を維持する（例外型・message・signature・戻り値・分岐条件すべて不変） |
| **G-5** | Runtime Zero Diff を維持する |
| **G-6** | v6.19 policy の出力を12 reason すべてに対して不変に保つ（CONTINUE拡大なし） |
| **G-7** | 更新が必要な既存E2Eアサーションを1アサーション単位で事前特定し、Formal Regression baseline への影響を設計段階で確定する |
| **G-8** | 分類不能な入力に対して安全側（`UNKNOWN`）へ落とし、分類処理自体が例外を送出しない |

---

## 7. Non-Goals（Out of Scope）

| ID | 対象外 |
|---|---|
| **N-1** | **CONTINUE対象の拡大**（v6.19 `_CONTINUABLE_REASONS` / `_ACTION_BY_CATEGORY` は無改修） |
| **N-2** | `ImageGenerationFailureCategory` の値追加・細分化 |
| **N-3** | **DI-11**（OpenAI `REQUEST_REJECTED` 細分化）。`src/openai_image_generation/` は無改修 |
| **N-4** | **DI-5**（observability／構造化ログ／metrics）。`ArticleLogEntry` / `ExecutionLogEntry` は無改修 |
| **N-5** | **DI-6**（Media Upload retry／idempotency／重複Upload防止） |
| **N-6** | **DI-7**（orphan media の検出・削除） |
| **N-7** | **DI-8**（Publish Composition Root Foundation） |
| **N-8** | **DI-9**（Gate値 strict validation）。`src/image_generation_config/` は無改修 |
| **N-9** | `main.py` への配線・console出力の追加・記事ループの変更 |
| **N-10** | HTTPステータスコードを属性として公開すること（10.3節 D-2） |
| **N-11** | `upload()` の signature・戻り値型・`MediaUploadResult` の変更 |
| **N-12** | `requirements.txt` / `.env.example` の変更 |
| **N-13** | 後続Release番号・内容の確定 |
| **N-14** | `_build_non_2xx_message()` の出力文字列の変更 |
| **N-15** | 401/403 等を起動時 Fail Fast へ昇格させること（v6.21 の起動時検証は無改修） |
| **N-16** | **（Amendment 1追加、M-2対応）** `requests.post()` の `allow_redirects=False` 化。redirect 追跡の停止は production behavior の変更であり、IL-1 の是正であっても本Releaseでは行わない（DEF-6.22-11） |

---

## 8. Design Alternatives

### 8.1 taxonomy 粒度の候補

| 案 | 内容 | 値数 |
|---|---|---|
| **A-1** | v6.11 と完全対称（9値をそのまま流用） | 9 |
| **A-2** | **WordPress固有の失敗構造から導出（採用）** | 12 |
| **A-3** | 最小限（TRANSIENT / PERMANENT / INVALID_RESPONSE / UNKNOWN） | 4 |

### 8.2 比較

| 観点 | A-1（v6.11対称） | **A-2（採用）** | A-3（最小） |
|---|---|---|---|
| WordPress固有の主要失敗（413 upload_max_filesize・415 allowed mime）の識別 | **不可**（`REQUEST_REJECTED` へ集約） | **可** | 不可 |
| 運用者の一次切り分けに使える情報量 | 少ない | **多い** | 少ない |
| 一過性／恒久の判別（将来のCONTINUE拡大の材料） | 可 | 可 | 可 |
| 実装コスト | 低 | 低（status code の分岐が増えるだけ） | 最低 |
| E2E ケース数 | 中 | やや多 | 少 |
| 「対称性のために現実を歪める」危険 | **あり** | なし | — |

> **（Amendment 1、M-2対応）** 上表から「是正actionへ1対1で写像される」という
> 表現を撤回した。reason は**観測された構造の分類**であり、根本原因および
> 是正actionとの1対1対応を保証しない（10.1.1節）。粒度の正当化は
> 「一次切り分けに使える情報量」に限定する。

**A-1 を採用しない理由**：指示および設計原則として「OpenAI側との対称性だけで決めない」。
OpenAI Images API に `413 Payload Too Large` / `415 Unsupported Media Type` に相当する
分類は存在せず、逆に WordPress に Content Policy 拒否は存在しない。
v6.11 の9値をそのまま流用すると、WordPress Media Upload で**現実に最も頻度が高い2つの失敗**
（画像サイズ超過・MIME非許可）が `REQUEST_REJECTED` に埋没する。
これは taxonomy の目的（是正action の識別）を損なう。

**A-3 を採用しない理由**：`TRANSIENT` / `PERMANENT` の二分は「振る舞いの決定」を
taxonomy 自体へ先取りしてしまう。振る舞いの決定は v6.19 policy の責務であり
（本Releaseの N-1）、Foundation 層は**観測された構造**のみを表現すべきである。
また 401（Application Password 誤り）と 413（サイズ超過）はどちらも `PERMANENT` だが
是正action は全く異なる。

### 8.3 v6.11 から継承する点／意図的に逸脱する点

| 項目 | v6.11 | 本設計 | 判断 |
|---|---|---|---|
| Enum を用いる | ○ | ○ | **継承** |
| Enum value は小文字snake_caseの固定ラベル | ○ | ○ | **継承** |
| 分類は例外型／status のみ。message解析なし | ○ | ○ | **継承** |
| 分類関数は純粋関数・`raise` しない | ○ | ○ | **継承** |
| 分類関数は module-private（`_` 始まり） | ○ | ○ | **継承** |
| subclass の判定順序を明示（多重継承対策） | ○ | ○ | **継承** |
| Enum を `__all__` へ公開 | ○ | ○ | **継承**（10.4節） |
| `__init__` で reason を validate しない | ○ | ○ | **継承**（10.5節） |
| 分類関数の戻り値 | `(message, reason)` | **`reason` のみ** | **逸脱**（9.4節） |
| `reason` は必須引数 | ○ | **既定値あり** | **逸脱**（10.2節） |
| taxonomy の値集合 | 9値 | **12値** | **逸脱**（8.2節） |

---

## 9. Selected Architecture

### 9.1 全体像

```text
src/wordpress_media/wordpress_media_uploader.py（唯一の変更ファイル）
├── + class WordPressMediaUploadErrorReason(Enum)          ← 新規 12値（10.1節）
├── + def _classify_request_exception(exc) -> Reason        ← 新規 module-private 純粋関数
├── + def _classify_status_code(status_code) -> Reason      ← 新規 module-private 純粋関数
├── ~ class WordPressMediaUploadError(RuntimeError)         ← __init__ 追加（reason 既定値あり）
└── ~ upload() の9箇所の raise へ reason= を付与             ← message・分岐条件は不変

src/wordpress_media/__init__.py
└── ~ WordPressMediaUploadErrorReason を import し __all__ へ追加（3 → 4 symbol）
```

**変更するのは上記2ファイルのみ。** `media_upload_result.py` は無変更。

### 9.2 分類アルゴリズム（擬似コード）

```text
_classify_request_exception(exc) -> WordPressMediaUploadErrorReason:
    # requests 例外の「型」のみで判定する。str(exc) / exc.args を読まない。
    # ★ Timeout を ConnectionError より先に判定する
    #   （ConnectTimeout は両方のsubclass。3.3節の実測に基づく）
    if isinstance(exc, requests.Timeout):          return TIMEOUT
    if isinstance(exc, requests.ConnectionError):  return CONNECTION
    return UNKNOWN        # TooManyRedirects / URLRequired / InvalidURL /
                          # ChunkedEncodingError / RetryError / その他


_classify_status_code(status_code) -> WordPressMediaUploadErrorReason:
    # status_code の「値」のみで判定する。response 本体・body・header を受け取らない。
    if isinstance(status_code, bool) or not isinstance(status_code, int):
        return UNKNOWN                    # 防御的分岐（20章 R-6）
    if status_code == 401: return AUTHENTICATION
    if status_code == 403: return PERMISSION_DENIED
    if status_code == 404: return ROUTE_NOT_FOUND
    if status_code == 413: return PAYLOAD_TOO_LARGE
    if status_code == 415: return UNSUPPORTED_MEDIA_TYPE
    if status_code == 429: return RATE_LIMIT
    if 400 <= status_code < 500: return REQUEST_REJECTED
    if 500 <= status_code < 600: return SERVER_ERROR
    return UNKNOWN                        # 1xx / 3xx / 600以上 / 200未満
```

いずれの関数も：`raise` しない・副作用を持たない・グローバル状態を読まない・
`response.json()` / `response.text` / `response.headers` を参照しない。

**個別status の判定を範囲判定より先に置く順序が contract である**
（401 は `400 <= sc < 500` にも該当するため、順序が逆転すると `REQUEST_REJECTED` へ落ちる）。

### 9.3 責任境界

| 層 | 責務 | 本Releaseでの扱い |
|---|---|---|
| `_classify_request_exception` / `_classify_status_code` | **観測された構造 → 分類ラベル** | 新規 |
| `WordPressMediaUploadError` | 分類ラベルの**保持**（判断しない） | `__init__` 追加 |
| `upload()` | 分類関数の呼び出しと reason の受け渡し | 9箇所へ `reason=` 付与 |
| v6.19 `decide_image_generation_fallback()` | **分類 → 振る舞いの決定** | **無改修**（N-1） |
| v6.20 runtime / v6.21 `main.py` | 決定の実行 | **無改修**（N-9） |

「分類」と「判断」を別Releaseへ分離する構造は、v6.11（分類）→ v6.19（判断）と同型である。

### 9.4 分類関数の戻り値を `reason` のみとする理由（v6.11 からの逸脱）

v6.11 `_classify_api_error()` は `(message, reason)` の組を返す。これは v6.11 が
**新規package**であり、message も同時に設計できたためである。

本Releaseは既存packageへの純追加であり、**message は既に確定していて変更が許されない**
（G-4・N-14）。分類関数が message を返す設計にすると、既存messageを分類関数側へ
移設する差分が発生し、Zero Behavior Change の検証が「文字列が同一であること」の
目視確認に依存することになる。

したがって本設計では **message は既存の `raise` 文にそのまま残し、分類関数は reason のみを返す。**
これにより message の差分は構造的に発生しない（`raise` 文の文字列リテラルを触らない）。

### 9.5 Guard（設計上の絶対禁止事項）

| ID | Guard |
|---|---|
| **G-1'** | 例外型 `WordPressMediaUploadError` の名称・基底クラス（`RuntimeError`）を変更しない |
| **G-2'** | 9 raise経路の**発生条件**（`if` 条件式）を変更しない |
| **G-3'** | 分類において message／`exc.args`／`response.text`／`response.json()`／header／credential を参照しない |
| **G-4'** | 9 raise経路の message 文字列を1文字も変更しない。`_build_non_2xx_message()` も無変更 |
| **G-5'** | `upload()` の signature・戻り値型・`MediaUploadResult` を変更しない |
| **G-6'** | `__init__` を含め、例外構築時に新たな例外を送出しない |
| **G-7'** | `requests` 以外の外部依存を追加しない |
| **G-8'** | reason 値に URL・credential・response本文・status code の生値を含めない |

---

## 10. Public API

### 10.1 `WordPressMediaUploadErrorReason`（新規・12値）

命名は既存例外型 `WordPressMediaUploadError` に `Reason` を付す形とし、
v6.11 の `OpenAIImageGenerationError` → `OpenAIImageGenerationErrorReason` と同一の
命名規則に従う。

```python
class WordPressMediaUploadErrorReason(Enum):
    """WordPressMediaUploadErrorの安全な失敗分類。

    秘密情報・Provider固有の生データ（URL・credential・response本文・
    status codeの生値）は一切含まない、固定された分類ラベルのみで構成する。
    """
    # transport 層（HTTP応答を受け取れなかった）
    TIMEOUT                = "timeout"
    CONNECTION             = "connection"
    # status 層（HTTP応答は受け取ったが 2xx でなかった）
    AUTHENTICATION         = "authentication"
    PERMISSION_DENIED      = "permission_denied"
    ROUTE_NOT_FOUND        = "route_not_found"
    PAYLOAD_TOO_LARGE      = "payload_too_large"
    UNSUPPORTED_MEDIA_TYPE = "unsupported_media_type"
    RATE_LIMIT             = "rate_limit"
    REQUEST_REJECTED       = "request_rejected"
    SERVER_ERROR           = "server_error"
    # body 層（HTTP 2xx だが応答本文が利用不能）
    INVALID_RESPONSE       = "invalid_response"
    # 分類不能
    UNKNOWN                = "unknown"
```

> **（Amendment 4追記：B4-1対応）本docstring と `GUARD-WMUE-CONSTRUCTION-SHAPE` の関係**
>
> 上記 `WordPressMediaUploadErrorReason` の docstring（1行目「WordPressMediaUploadErrorの
> 安全な失敗分類。」）は `"WordPressMediaUploadError"` を部分文字列として含むが、
> **class body 先頭の docstring**であるため、17.1節 手順4（文字列間接参照の封鎖）の
> 検査対象から除外される（docstring exclusion）。除外は v6.11
> `OpenAIImageGenerationErrorReason` の docstring
> 「`OpenAIImageGenerationError`の安全な失敗分類。」と同型の既存慣行を踏襲したものであり、
> 本設計はこの慣行をそのまま維持できる（詳細は17.1節・14.1.1節）。

#### 各値が対応する観測された構造

**（Amendment 1で改訂：M-2・S-1対応）** 本表は「観測された構造」と、その構造から
**典型的に**推定される WordPress 側の状況を対応付けたものである。
「典型的な是正action」列と「一過性か」列は **non-normative（非規範）** であり、
診断の出発点を示すに過ぎない。**いずれの列も Fallback Policy の入力ではなく、
根本原因との1対1対応も保証しない**（10.1.1節・10.1.2節）。

| reason | 観測された構造（HTTP／例外） | 典型的に推定される WordPress 側の状況 | 典型的な是正action<br>*(non-normative)* | 一過性か<br>*(non-normative)* |
|---|---|---|---|---|
| `TIMEOUT` | `requests.Timeout` | 接続または読み取りが30秒（`_TIMEOUT_SECONDS`）で完了しなかった | 再実行。継続する場合は回線・サーバ負荷を確認 | **一過性** |
| `CONNECTION` | `requests.ConnectionError` | DNS解決失敗・接続拒否・TLSエラー・Proxyエラー | `WP_SITE_URL` の確認、または再実行 | 一過性／設定 |
| `AUTHENTICATION` | 401 | Application Password が無効・失効・未送信 | `WP_APP_PASSWORD` / `WP_USERNAME` の再発行・再設定 | 恒久 |
| `PERMISSION_DENIED` | 403 | ユーザに `upload_files` 権限がない、またはセキュリティプラグイン／WAFが REST を遮断 | 権限付与、またはWAF許可設定 | 恒久 |
| `ROUTE_NOT_FOUND` | 404 | `POST /wp-json/wp/v2/media` の route が解決されなかった（REST API無効化・パーマリンク／rewrite 設定不全・`WP_SITE_URL` がWordPress以外を指している等）。本endpointへのPOSTはリソースIDを含まないため、resource単位の不在を意味しない | REST API有効化、rewrite設定の確認、`WP_SITE_URL` の確認 | 恒久 |
| `PAYLOAD_TOO_LARGE` | 413 | `upload_max_filesize` / `post_max_size` / nginx `client_max_body_size` の上限超過 | サーバ側上限の引き上げ、または生成画像の size／quality の引き下げ | 恒久 |
| `UNSUPPORTED_MEDIA_TYPE` | 415 | 送信したMIME型が `get_allowed_mime_types()` に含まれない | 許可MIME追加、または `output_format` の変更 | 恒久 |
| `RATE_LIMIT` | 429 | ホスティング／WAF によるレート制限 | 待機して再実行 | **一過性** |
| `REQUEST_REJECTED` | その他4xx（400・402・405・409・422等） | リクエスト自体が拒否された（上記に該当しない理由） | messageの `code=` / `message=` を人間が確認 | 恒久寄り |
| `SERVER_ERROR` | 5xx | WordPress／PHP／リバースプロキシ側のエラー | 再実行。継続する場合はサーバログ確認 | **一過性** |
| `INVALID_RESPONSE` | 2xx だが本文不正 | JSONでない／dictでない／`id` 不正／`source_url` 不正／`mime_type` 不正 | 応答を返している中間層（キャッシュ・プラグイン）の確認 | 不定 |
| `UNKNOWN` | 上記いずれでもない | 3xx応答、`TooManyRedirects`、`InvalidURL`、未知の `RequestException` 等 | 個別調査 | 不定 |

「典型的な是正action」「一過性か」の2列は**診断のための非規範的注記であり、
振る舞いの決定ではない**（S-1対応）。実際の振る舞いは v6.19 policy が決めるもので
あり、本Releaseでは12 reason すべてが
`MEDIA_UPLOAD_FAILED → PROPAGATE_ORIGINAL_ERROR` のままである（11.4節）。
**この2列を、将来の Fallback Policy 設計が判断根拠として引用してはならない**
（10.1.1節 L-1）。

> **（Amendment 2）Review 2 Suggestion S2-2 の採否：不採用**
>
> S2-2 は「非規範2列を付録へ分離すれば、将来の policy 設計が引用する誘因を
> 構造的に断てる」という提案であった。次の理由で**不採用**とする。
>
> ```text
> ① 抑止は既に3層で効いている：
>      列見出しの *(non-normative)* 表記／本段落の明示的な引用禁止／
>      10.1.1節 L-1 の規範的禁止（reason を一過性の証明として扱ってはならない）。
> ② 分離すると、運用者が1つの失敗を診断する際に
>      「観測構造 → 推定状況 → 是正action」を2箇所を往復して読む必要が生じ、
>      本表の主目的（一次切り分け）の使い勝手が下がる。
>      粒度の正当化根拠が「一次切り分けに使える情報量」（L-3）であることと
>      整合しない。
> ③ 引用の誘因は「場所」ではなく「規範性の明示」で断つべきであり、
>      ①がその役割を果たしている。付録へ移しても、引用しようとする者は
>      付録を引用するだけである。
> ```
>
> 代替として、本段落へ引用禁止の1文を明記した（上記）。
> 将来 policy 設計 Release が本2列を引用した場合は、その Release の
> Architecture Review が L-1 違反として指摘する運用とする。

#### 10.1.1 reason の意味の限定（Amendment 1新設、M-2対応）

**`WordPressMediaUploadErrorReason` は「観測された構造の分類」であり、
「根本原因の分類」ではない。**

```text
定義（Contract）:
  reason は、失敗が表面化した時点で upload() が構造情報として観測できたもの
  ——すなわち (a) requests 例外の型、または (b) HTTP ステータスコード、または
  (c) 2xx 応答本文が契約を満たさなかったという事実——のいずれかを、
  固定ラベルへ写像した値である。

保証すること:
  ・同一の観測構造からは常に同一の reason が得られる（決定性）
  ・全入力に対して必ず1つの reason が定まる（全域性。I-5）
  ・reason に秘密情報・可変の生データを含まない（I-2）

保証しないこと:
  ・reason と根本原因（root cause）の1対1対応
  ・reason と是正action（remediation）の1対1対応
  ・同一の根本原因が常に同一の reason として観測されること
```

この限定は Amendment 前の記述（「各値が異なる是正actionへ1対1で写像される」）を
**撤回**するものである。撤回の根拠は10.1.2節に実測付きで示す。

**この限定が設計へ与える帰結**

| ID | 帰結 |
|---|---|
| **L-1** | 将来 Fallback Policy が CONTINUE 対象を拡大する場合、reason を「一過性の証明」として扱ってはならない。reason は候補の絞り込みにのみ使え、最終判断には別の根拠（retry 実績・連続失敗回数等）を要する。これは本Releaseの対象外（7章 N-1）だが、後続Releaseへの申し送りとして明記する |
| **L-2** | DI-5（observability）が reason をログへ記録する場合、「reason = 原因」ではなく「reason = 観測されたもの」として提示すべきである |
| **L-3** | 粒度（12値）の正当化は「是正actionとの1対1」ではなく「一次切り分けに使える情報量」に置く（8.2節） |

#### 10.1.2 Inherited Limitations（Amendment 1新設、M-2対応）

本Releaseは `upload()` の behavior を変更しないため、既存実装が持つ観測上の限界を
そのまま継承する。いずれも **taxonomy の欠陥ではなく、観測地点の制約**である。

| ID | 限界 | 実測／根拠 | 本Releaseでの扱い |
|---|---|---|---|
| **IL-1** | **redirect 追跡により、URL 設定誤りが URL 系 reason として観測されない。** `WP_SITE_URL` に `http://` を指定しサイトが `https://` へ 301 する構成では、`requests` が redirect を追跡し、かつ **301／302 で POST を GET へ書き換える**ため、`GET /wp-json/wp/v2/media` が HTTP 200 ＋ JSON **配列**を返す。結果 `upload()` は L175 の `not isinstance(data, dict)` で失敗し、`ROUTE_NOT_FOUND` ではなく **`INVALID_RESPONSE`** となる | project venv（requests 2.34.2）で `requests.sessions.SessionRedirectMixin.rebuild_method` を実測。`codes.moved`(301) かつ method == "POST" → "GET"、`codes.found`(302) かつ method != "HEAD" → "GET" | **受容し明記する。** 是正には `allow_redirects=False` 化が必要だが、これは production behavior の変更であり本Releaseでは禁止（7章 N-16）。DEF-6.22-11 として記録 |
| **IL-2** | **認証失敗が 401 として観測されない構成がある。** `Authorization` ヘッダが PHP へ転送されないホスティング（CGI/FastCGI で `HTTP_AUTHORIZATION` を渡さない等）や、WAF が認証前に遮断する構成では、認証失敗が 401 ではなく 403・406・200 等として現れる。この場合 `AUTHENTICATION` ではなく `PERMISSION_DENIED`／`REQUEST_REJECTED`／`INVALID_RESPONSE` として観測される | WordPress Application Password 運用上の既知の構成依存。本Releaseは status code のみを見るため構成差を吸収できない | **受容し明記する。** 判別には応答本文の `code`（例 `rest_cannot_create`）の解析が必要であり、message解析禁止（G-3'）に抵触するため対象外 |
| **IL-3** | **redirect ループが `UNKNOWN` へ落ちる。** `requests.TooManyRedirects` は URL 設定誤りに起因する典型例だが、専用 reason を設けず `UNKNOWN` とする | 9.2節の分類規則 | **受容する（S-2 不採用）。** 理由：①IL-1 のとおり redirect 追跡が有効な現契約では、URL 設定誤りの大半が `TooManyRedirects` に到達せず別 reason として観測されるため、専用値を設けても「URL誤り＝この reason」という対応は成立しない ②専用値の追加は taxonomy を「根本原因の分類」へ引き寄せ、10.1.1節で確定した定義と矛盾する ③`UNKNOWN` は安全側（`PROPAGATE`）である。DEF-6.22-12 として記録 |
| **IL-4** | **`INVALID_RESPONSE` は原因の異なる複数事象を集約する。** 単発の応答破損、中間層（キャッシュ・プラグイン）による書き換え、IL-1 の redirect 経路、WordPress 側スキーマ変更のいずれも同一値になる | 3.2節 R-3〜R-9 | **受容する。** 細分化は DEF-6.22-5（DI-11 が OpenAI 側で扱う論点と同型） |

**IL-1〜IL-4 はいずれも安全側の帰結を持つ**（該当 reason はすべて v6.19 policy で
`MEDIA_UPLOAD_FAILED → PROPAGATE_ORIGINAL_ERROR` へ写像される。11.4節）。
すなわち観測の粗さが「継続すべきでない失敗を継続させる」方向へ働くことはない。

### 10.2 D-1：`reason` を必須引数にしない（v6.11 からの意図的逸脱）

```python
class WordPressMediaUploadError(RuntimeError):
    """WordPress Media APIへの通信・応答に関する失敗を表す唯一の専用例外。

    reason属性は安全な分類ラベルのみを保持し、response生データ・URL・
    credentialのいずれも保持しない。
    """

    def __init__(
        self,
        message: str,
        reason: WordPressMediaUploadErrorReason = WordPressMediaUploadErrorReason.UNKNOWN,
    ) -> None:
        super().__init__(message)
        self.reason = reason
```

**採用理由**

| ID | 理由 |
|---|---|
| **D-1a** | 3.7節のとおり、既存テストコードに `WordPressMediaUploadError(message)` の1引数構築が **10箇所** 存在する。`reason` を必須にすると全10箇所が `TypeError` となり、v6.12／v6.19／v6.20 の**3 Release分のE2Eファイル4本**へ機械的な差分が波及する。Zero Behavior Change の Foundation Release として、既存contractの変更を必要最小限に抑える方針（G-7）に反する |
| **D-1b** | 既定値 `UNKNOWN` は **taxonomy 中で最も安全な値**である。v6.19 policy において `UNKNOWN` を含む全12値は `MEDIA_UPLOAD_FAILED`（= `PROPAGATE_ORIGINAL_ERROR`、安全側）へ写像される。既定値によって危険側へ倒れる経路は存在しない（一過性を意味する値を既定にした場合とは異なる） |
| **D-1c** | **（Amendment 1で全面改訂：M-1対応）** 「必須引数による強制」の代替として、**二重検証**を課す。①**behavioral E2E**：production の既知9 raise経路それぞれの reason を1件ずつ固定する（17章 `REASON-R1`〜`REASON-R9`）。②**構築形 AST guard**：**（Amendment 3で方式転換：M3-1対応）** `src/wordpress_media/wordpress_media_uploader.py` について、識別子 `WordPressMediaUploadError` が **AST 上に現れてよい文脈を allow-list（クラス定義／`raise` 文直下の直接構築の callee の2つのみ）で縛り**、それ以外の出現をすべて違反とする。あわせて当該 module 内の文字列リテラル `"WordPressMediaUploadError"` を禁止して文字列間接参照を封じ、許可された構築 Call には `reason=` keyword 必須・positional 1個のみ・`**kwargs` 禁止を課す。Amendment 2 までの「禁止形を列挙する deny-list」方式は Review 3 の実測で8形の迂回が判明したため廃止した（規範仕様は17.1節 `GUARD-WMUE-CONSTRUCTION-SHAPE`）。<br>**Amendment 前の記述「検出可能性は失われない」は誤りであった**：①のみでは既知9経路しか検査せず、将来 raise 経路 #10 が追加され `reason=` を渡し忘れた場合、既存9 Scenario はすべてPASSしたまま新経路が静かに `UNKNOWN` になる。②は raise 件数に依存しない全域的な検査であるため、この穴を閉じる。**②は件数を9に固定してはならない**（固定すると経路追加時に「件数不一致」で失敗するだけとなり、どの経路が reason を欠くのかを示せない）。②の存在により、必須引数方式と同等の「分類漏れの構造的検出」が behavioral test に依存せず成立する |
| **D-1d** | parameter 名・順序は v6.11 と同一（`(self, message, reason)`）とし、`inspect.signature` 上の読み取り結果を v6.11 と対称に保つ。**（Amendment 2追加：M2-1対応）** API としては positional 形（`WordPressMediaUploadError(msg, REASON)`）も成立するが、**production code では positional 形を禁止し keyword `reason=` を必須とする**。理由：guard は keyword の有無で分類漏れを検出するため、positional 形を許すと「reason を渡しているのに guard を通らない」ケースと「渡し忘れ」を区別できなくなる。positional 形を許容し続けるのは既存テストの1引数構築（後方互換、D-1a）と外部からの利用に限る。この禁止は `GUARD-WMUE-CONSTRUCTION-SHAPE` の手順5（17.1節）で機械的に強制する。**（Amendment 3追加：m3-5対応）** あわせて `**kwargs` 展開による構築（`WordPressMediaUploadError(msg, **kw)`）も禁止する。`reason` の存在を静的に判定できないため、guard は安全側に倒して違反として扱う（現行実装に該当箇所はない） |

**トレードオフ（Architecture Review の判断対象。21章 V-1）**：
必須引数のほうが「分類漏れを型レベルで防ぐ」という点では強い。
Reviewer が D-1 を不採用とする場合、影響は「既存4テストファイル・10構築箇所の更新」へ拡大し、
Formal Regression baseline への影響も 11.5節から変わる。本設計は D-1 を採用するが、
**この判断はReview で覆される可能性のある明示的な選択点である。**

production code 側では既定値に依存せず、**全 raise 箇所**で `reason=` を
**明示的に指定する**（既定値は後方互換のためだけに存在する）。
この規律は宣言に留めず、`GUARD-WMUE-CONSTRUCTION-SHAPE`（17.1節・AC-6.22-23）で
機械的に強制する。

### 10.3 D-2：HTTPステータスコードを属性として公開しない

`_classify_status_code()` は status code を受け取るが、**`WordPressMediaUploadError` は
status code を保持しない。**

| 理由 |
|---|
| status code は既に `_build_non_2xx_message()` により message へ含まれている（`"WordPress Media API returned HTTP 413"`）。属性として重複保持する必要がない |
| 本Releaseの目的は「機械可読な**分類**の付与」であり、「生データの公開」ではない。生値を公開すると下流が status code で直接分岐する誘因を生み、taxonomy が迂回される |
| Public API 面を最小に保つ（v6.19 §11.7「Public API規模の妥当性」と同じ方針） |
| 将来 status code そのものが必要になった場合は、**別Releaseの独立した判断**とする（19章 DEF-6.22-3） |

### 10.4 D-3：`__all__` へ公開する

`src/wordpress_media/__init__.py`：

```python
from .media_upload_result import MediaUploadResult
from .wordpress_media_uploader import (
    WordPressMediaUploadError,
    WordPressMediaUploadErrorReason,
    WordPressMediaUploader,
)

__all__ = [
    "MediaUploadResult",
    "WordPressMediaUploadError",
    "WordPressMediaUploadErrorReason",
    "WordPressMediaUploader",
]
```

**公開する理由**

| ID | 理由 |
|---|---|
| **D-3a** | 想定される後続consumer（v6.19 policy の将来更新、DI-5 の observability）は、v6.19 が `from openai_image_generation import OpenAIImageGenerationErrorReason` としているのと同様に **package root から** import する必要がある。`__all__` へ入れなければ、consumer は内部module `wordpress_media.wordpress_media_uploader` を直接importせざるを得ず、v6.9 の `PM-4` contract（内部module名を公開しない）が意図する封じ込めを破ることになる |
| **D-3b** | v6.11 は `OpenAIImageGenerationErrorReason` を `__all__` に含めている（3.4節）。Public API **形状**の対称性はここで保つべきであり、taxonomy の値集合と異なりRepository固有の事情がない |
| **D-3c** | 公開しない案では X-3（`reason` 属性）のみの更新で済み既存差分は1件に減るが、**属性は存在するのに型が package root から参照できない**という歪んだAPIになる。下流は `type(err.reason)` 経由や文字列比較で分岐するしかなく、taxonomy の型安全性が失われる |

**代償**：X-1／X-2／X-4 の3アサーション（`__all__` 完全一致）が更新対象となる（11.2節）。
これは v6.19 §20 DI-10 が「v6.9のPublic API変更を伴うため独立Releaseを要する」と
述べていた内容そのものであり、本Releaseが独立Releaseである理由でもある。

内部の分類関数 `_classify_request_exception` / `_classify_status_code` は
`_` 始まりの module-private とし、`__all__` へは含めない（v6.9 `PM-4` contract 維持）。

### 10.5 D-4：`__init__` で `reason` を validate しない

v6.11 `OpenAIImageGenerationError.__init__` は validation を行わない（3.4節）。本設計も従う。

| 理由 |
|---|
| **例外を構築している最中に新たな例外を送出することは、エラーハンドリング経路を破壊する。** `upload()` 内で `raise WordPressMediaUploadError(...)` を評価中に `ValueError` が飛べば、元の失敗情報が失われる（G-6'） |
| v6.19 policy は既に `getattr(error, "reason", None)` + `isinstance()` による防御的読み取りを実装しており（`image_generation_fallback_policy.py` L137・L144）、不正な reason 値は下流で安全に `UNCLASSIFIED` 相当へ落ちる。防御責任は consumer 側に既に存在する |
| Enum型注釈により静的型チェックの対象にはなる。実行時強制は行わない |

したがって contract として：**`WordPressMediaUploadError.__init__` は例外を送出しない。**
E2E `NOVAL-` prefix でこれを固定する（17章）。

### 10.6 Public API 規模

| 分類 | 変更 |
|---|---|
| 新規 public symbol | 1（`WordPressMediaUploadErrorReason`、12値） |
| 変更 public symbol | 1（`WordPressMediaUploadError` に `__init__` と `reason` 属性が追加） |
| 削除 public symbol | 0 |
| 新規 module-private 関数 | 2 |
| 新規ファイル | 0（production code） |

---

## 11. Compatibility / Regression

### 11.1 Zero Behavior Change の成立根拠

| ID | 主張 | 根拠 |
|---|---|---|
| **C-1** | 成功時の挙動が不変 | `upload()` の成功経路（L143-159・L165・L168-210 の検証通過時）には reason が一切登場しない。`MediaUploadResult(media_id, source_url, mime_type)` の構築は無変更 |
| **C-2** | 失敗／成功の**分岐条件**が不変 | 9 raise経路の `if` 条件式（G-2'）と `try`/`except` の範囲を変更しない。追加するのは `raise` 文の引数のみ |
| **C-3** | 例外**型**が不変 | `WordPressMediaUploadError(RuntimeError)` の名称・基底を変更しない。既存の `except WordPressMediaUploadError` / `except RuntimeError` はすべてそのまま機能する |
| **C-4** | 例外**message** が不変 | 既存messageの文字列リテラルを `raise` 文に残し、分類関数は reason のみを返す（9.4節）。`_build_non_2xx_message()` も無変更（N-14） |
| **C-5** | 例外 **chaining** が不変 | R-1・R-3 の `from exc` を維持する。`__cause__` が保たれる |
| **C-6** | 既存の1引数構築が不変 | `reason` に既定値があるため `WordPressMediaUploadError("msg")` は従来どおり成立する（D-1） |
| **C-7** | v6.12 Wiring層が不変 | `try`/`except` を持たず例外を素通しする（3.6節）。object identity と `reason` 属性は経路上で失われない |
| **C-8** | `MediaUploadResult` が不変 | `media_upload_result.py` は無変更 |
| **C-9** | 外部依存が不変 | `enum` は標準ライブラリ。`requirements.txt` は無変更（N-12） |

### 11.2 更新が必要な既存E2Eアサーション（全6件・1アサーション単位で確定）

**（Amendment 1で改訂：B-1対応）** 3.8節で全数特定した **6件**（4ファイル）が更新対象である。
**これ以外の既存アサーションは更新しない。**

| ID | ファイル / 行 | 現在 | 更新後 | 理由 |
|---|---|---|---|---|
| **X-1** | `tests/test_e2e_v6_9_0_wordpress_media_upload_foundation.py` L209-213<br>`PM-3b. __all__完全一致` | 期待値 3 symbol | 期待値 **4 symbol**（`WordPressMediaUploadErrorReason` を追加） | D-3 により `__all__` が拡張される。検査意図（`__all__` を完全一致で固定する）は不変で、**期待値のみ**を更新 |
| **X-2** | `tests/test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py` L1297-1301<br>`COMPAT-V69-ALL-UNCHANGED` | 期待値 3 symbol | 期待値 **4 symbol** | 同上。アサーション名の「UNCHANGED」は v6.19 時点の意図を表す名称であり、**名称も併せて更新する**（例：`COMPAT-V69-ALL-WITH-REASON`）。v6.19 §20 DI-10 が予告済み |
| **X-3** | 同上 L1303-1309<br>`COMPAT-WP-NO-REASON-ATTR` | `check_false(hasattr(err, "reason"))` | `check_true(hasattr(err, "reason"))`（**1アサーションのまま極性のみ反転**） | v6.19 が固定していたのは「N-17（DI-10を本Releaseで実施しない）の遵守」という**当時の事実**。本Releaseが DI-10 であるため当該事実は失効する。アサーション文言自身が「DI-10実施時にこのScenarioは既知差分として更新対象となる」と予告している |
| **X-4** | `tests/test_e2e_v6_20_0_article_featured_media_runtime_foundation.py` L993-997<br>`COMPAT-V609. wordpress_media.__all__が不変` | 期待値 3 symbol | 期待値 **4 symbol** | 同上 |
| **X-5** | `tests/test_e2e_v6_21_0_article_featured_media_runtime_wiring.py` L845-893<br>`NOIMPACT-UNCHANGED[<path>]`（22パス分） | `git diff --quiet` の exit code == 0（差分ゼロ） | `NOIMPACT-SCOPE[<path>]`：**差分ファイル集合が allow-list の範囲内**（11.7節・案C）。allow-list が空の21パスでは差分ゼロと**論理的に等価**。`src/wordpress_media` のみ allow-list に意図2ファイルを登録 | 本Releaseが正当に変更する `src/wordpress_media` を、v6.21 の guard が差分ゼロで固定しているため。guard から対象を**削除せず**、検査意図（保護対象への意図しない変更の検出）を保ったまま検出手法を精緻化する（11.7節） |
| **X-6** | 同上 L897-921<br>`NOIMPACT-TESTS-SCOPE` | 許容3件（`v6_13_0`／`v6_20_0`／`v6_21_0`） | 許容 **6件**（＋`v6_9_0`／`v6_19_0`／`v6_22_0`）。ラベル文言の「許容3件」も同期 | X-1〜X-5 の更新と v6.22 E2E の新規追加が、v6.21 baseline から見て `tests/` の差分として現れるため |

**更新方式は「既存ファイルの in-place 更新」とする。** これは v6.21.0 が
v6.13.0 `RUNTIME-1` と v6.20.0 `RUNTIME-1a` を、検査意図を保ったまま
既存ファイル内で精緻化した precedent（v6.21.0 設計書5.5節・5.6節）に従う。
アサーションを削除して新ファイルへ移設することは行わない。

### 11.3 更新しないと明示するもの

| 対象 | 理由 |
|---|---|
| `tests/test_e2e_v6_9_0_*.py` の message 検証アサーション群 | message 凍結（C-4）により FAIL しない |
| `tests/test_e2e_v6_12_0_*.py` L506 の1引数構築 | 既定値により成立（C-6） |
| `tests/test_e2e_v6_19_0_*.py` の `WPUP-` / `PURE-` / `SEC-` 等の policy 検証群（L451・664・795・980・981・995・1226） | 1引数構築が成立し、policy の出力も不変（11.4節） |
| `tests/test_e2e_v6_19_0_*.py` L1285-1294 `COMPAT-V611-*`（OpenAI 側） | `src/openai_image_generation/` は無改修（N-3） |
| `tests/test_e2e_v6_20_0_*.py` L583 の1引数構築 | 既定値により成立（C-6） |
| `tests/test_e2e_v6_21_0_*.py` の `NOIMPACT-` 以外の全アサーション（`GATEOFF-`／`APPLIED-`／`CONT-`／`PROP-`／`MDOK-`／`MDFAIL-`／`NOWP-`／`WIRE-`／`GUARD-`／`NODYN-`／`LOOP-`／`CONFIG-`） | **（Amendment 1で訂正）** 当該ファイルは `__all__` 系COMPATを持たず、`main.py` も無改修であるため影響しない。ただし **`NOIMPACT-` は X-5・X-6 として更新対象である**（Amendment 前は「全件更新不要」と誤記していた） |
| `tests/test_e2e_v6_12_0_*.py` L324・L327 の `__all__` | 対象package が `generated_image_wordpress_media` であり本Releaseの変更対象外 |

### 11.4 v6.19 policy の出力が不変であることの証明

`decide_image_generation_fallback()`（`image_generation_fallback_policy.py` L152-153）は
`isinstance(error, WordPressMediaUploadError)` のみで判定し `reason` を読まない（3.5節）。

したがって：

```text
∀ r ∈ WordPressMediaUploadErrorReason（12値）:
    decide_image_generation_fallback(WordPressMediaUploadError("msg", r))
        == ImageGenerationFallbackDecision(category=MEDIA_UPLOAD_FAILED)
    かつ .action == PROPAGATE_ORIGINAL_ERROR
```

**CONTINUE対象は拡大されない（N-1）。** これを E2E `POLICY-` prefix で
12値すべてについて機械的に検証する（17章・18章 AC-6.22-14）。

### 11.5 Formal Regression baseline（3389）への影響

**（Amendment 1で再計算：B-1対応）** X-5・X-6 を織り込んだうえで、
**既存24ファイルのアサーション総数は 3389 のまま不変**である。これは案Cを採用した
直接の帰結であり、案A（guard から `src/wordpress_media` を削除）を採らなかった
理由の一つでもある（11.7.2節）。

| 更新 | 対象ファイル | 変更の性質 | 件数の増減 |
|---|---|---|---|
| **X-1** | `v6_9_0` | 期待値（3 symbol → 4 symbol） | **±0**（1件のまま） |
| **X-2** | `v6_19_0` | 期待値＋ラベル文言 | **±0**（1件のまま） |
| **X-3** | `v6_19_0` | `check_false` → `check_true` の極性反転 | **±0**（1件のまま） |
| **X-4** | `v6_20_0` | 期待値（3 symbol → 4 symbol） | **±0**（1件のまま） |
| **X-5** | `v6_21_0` | ループ内1アサーションの検出手法とラベルを精緻化（`NOIMPACT-UNCHANGED[<path>]` → `NOIMPACT-SCOPE[<path>]`）。**1パスあたり3アサーション（`EXISTS`／`BASELINE-TRACKED`／`SCOPE`）という構成は不変**であり、22パス × 3 = 66件のまま | **±0**（66件のまま） |
| **X-6** | `v6_21_0` | 許容集合リテラル（3 → 6要素）＋ラベル文言。期待値は `[]` のまま | **±0**（1件のまま） |
| **合計** | **4ファイル** | 追加・削除は1件も行わない | **±0 → 3389 のまま** |

| 項目 | 内容 |
|---|---|
| **既存24ファイルのアサーション総数** | **3389 のまま不変**（上表のとおり全更新が期待値・ラベル・極性・リテラルの差し替えに限られる） |
| **期待結果が実際に変わるアサーション** | **X-1・X-2・X-3・X-4・X-6 の5件と、X-5 のうち `src/wordpress_media` の1件＝計6件。** X-5 の残り21パスは検査手法の記述が変わるのみで、期待結果（差分ゼロ）は不変（11.7.1節の等価性） |
| **設計上の意図** | 「既定値の contract」「12値の網羅」「全 raise 経路の reason」といった**新しい contract の検証は、すべて新規 v6.22 E2E ファイル側に置く。** 既存ファイルには新規アサーションを追加しない。これにより既存baselineの数値が動かず、Regression 差分の解釈が単純になる |
| **正式 Regression Inventory** | **24ファイル → 25ファイル**（`tests/test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification.py` を追加） |
| **Formal Regression 総数（見込み）** | `3389 + <v6.22 新規E2Eアサーション数>`。新規件数は Test Review／Production Implementation 工程で確定する（本設計では確定しない） |
| **既知差分の扱い** | X-1〜X-6 の6件は「設計上の既知差分」であり、`docs/CHANGELOG.md` の KI-3／KI-4 precedent と同様に扱う。**無関係な Regression として扱ってはならない**（X-1〜X-4 は v6.19 §20 DI-10・§23 AC-24 が予告済み。X-5・X-6 は予告がなく、11.8節の一般則を新たに定める） |

### 11.6 Runtime Zero Diff の成立根拠

| 対象 | 変更 | 根拠 |
|---|---|---|
| `main.py` | **無変更** | 本Releaseは `main.py` が参照する `article_featured_media_runtime` の Public API を変えない。reason は `main.py` から到達不能（v6.21 の `except Exception` は例外を変数へ束縛しない） |
| `src/image_resolver.py` | 無変更 | `wordpress_media` を参照しない |
| `src/outputs/`（全ファイル） | 無変更 | 同上 |
| `src/pipeline/`（全ファイル） | 無変更 | 同上 |
| `scripts/`（全ファイル） | 無変更 | 同上 |
| **画像系 package のうち `src/wordpress_media/` を除く11 package**（`ai_image_generation` / `openai_image_generation` / `generated_image_wordpress_media` / `article_featured_media` / `article_featured_media_orchestration` / `image_generation_config` / `generated_image_filename_policy` / `article_image_prompt_construction` / `article_featured_media_composition` / `image_generation_fallback_policy` / `article_featured_media_runtime`） | **すべて無変更** | reason は下流で読まれない（3.5節・3.6節）。v6.12 は例外を素通しし、v6.19 は型のみで判定する |
| `src/logger/` | 無変更 | DI-5 の領域（N-4） |
| `requirements.txt` / `.env.example` | 無変更 | `enum` は標準ライブラリ（N-12） |
| `src/wordpress_media/` | **変更（2ファイル）** | 本Releaseの唯一の変更対象 |

> **（Amendment 1、m-2対応）用語についての注記**：`docs/architecture.md` は
> 「画像系11 Foundation」を **v6.9.0〜v6.19.0**（＝`wordpress_media` を**含む**）の
> 意味で用いている。本節の「`src/wordpress_media/` を除く11 package」は
> **v6.9.0〜v6.20.0 の画像系12 package から本Releaseの変更対象1件を除いた集合**であり、
> architecture.md の「11 Foundation」とは**異なる集合**である。混同を避けるため、
> 本設計書では以後この長い表現を用い、単独の「画像系11 package」という語は使わない。

**検証方法**：v6.21.0 の Release Review B-1 で確立した **baseline commit 固定の
恒久guard**方式を継承する。ただし v6.21.0 の guard は本Releaseの変更対象
`src/wordpress_media/` を差分ゼロで固定しているため、**そのままでは本Releaseと
両立しない**（3.8節 X-5・X-6）。両立させるための guard 精緻化（案C）を
**11.7節**で、後続Releaseへの一般則を **11.8節**で確定する。
HEAD 基準の比較は commit 後に無効化するため採用しない
（v6.21.0 設計書14.4節・「Runtime Zero Diffの解除範囲」節）。

**v6.13 `RUNTIME-1` / v6.20 `RUNTIME-1a` の Architecture Guard への影響**：
本Releaseは `main.py` を変更せず、`main.py` が参照する package 名も増やさないため、
これらの Guard は**精緻化不要**である（v6.21.0 で発生した R-7 型の問題は生じない）。

### 11.7 v6.21.0 NOIMPACT Guard との衝突と精緻化（Amendment 1新設、B-1対応・案C採用）

#### 11.7.0 衝突の内容（確認済みの事実）

`tests/test_e2e_v6_21_0_article_featured_media_runtime_wiring.py` は
baseline commit を `8d8950684a305bc93c824866578cb30c6b2e4fdd`（v6.20.0 Release時点）に
固定し（L824）、`_protected_paths`（L845-868、**22パス**）の各々について
次の3アサーションを行う。

```text
NOIMPACT-EXISTS[<path>]            作業ツリーに実在する（vacuous pass防止 その1）
NOIMPACT-BASELINE-TRACKED[<path>]  baseline commit に追跡ファイルが存在する（同 その2）
NOIMPACT-UNCHANGED[<path>]         git diff --quiet <baseline> -- <path> の exit code == 0
```

`_protected_paths` の **L853 に `"src/wordpress_media"` が含まれる**。
加えて L897-921 の `NOIMPACT-TESTS-SCOPE` は、`tests/` の差分を
`{v6_13_0, v6_20_0, v6_21_0}` の3件に限定する。

Review 1 時点の実測（read-only）：

```text
git diff --quiet 8d89506 -- src/wordpress_media          → exit 0（現在は差分なし）
git diff --name-only 8d89506 -- tests                    → 上記3ファイルのみ
```

したがって本Releaseを設計どおり実装すると、v6.22 の Formal Regression で
Inventory 24番目の v6.21 E2E を再実行した時点で
`NOIMPACT-UNCHANGED[src/wordpress_media]` と `NOIMPACT-TESTS-SCOPE` が
**確実にFAILする**。これは実装後に発覚する不具合ではなく、
**設計段階で対処方針を確定しなければ正しい実装手順が定まらない**問題である。

#### 11.7.1 採用する精緻化（案C：allow-list 方式）

**guard から保護対象を削除しない。**「差分がゼロであること」の検査を
「**差分ファイル集合が明示 allow-list の範囲内であること**」の検査へ精緻化する。

```text
【追加するデータ構造】
_allowed_source_changes: dict[str, frozenset[str]]
    保護対象パス → そのRelease が変更を許容する
                   「project root 相対の POSIX パス」の集合
    既定は空集合（＝従来と同じ「差分ゼロ」の意味）

    v6.22 における唯一の非空エントリ:
      "src/wordpress_media": {
          "src/wordpress_media/__init__.py",
          "src/wordpress_media/wordpress_media_uploader.py",
      }

【第3アサーションの置き換え】
  旧: NOIMPACT-UNCHANGED[<path>]
        git diff --quiet <baseline> -- <path> の exit code == 0

  新: NOIMPACT-SCOPE[<path>]
        changed = git diff --name-only --relative <baseline> -- <path> の行集合
        allowed = _allowed_source_changes.get(<path>, frozenset())
        check(sorted(changed - allowed), [])
```

**検査意図が保持されることの論証**

| 条件 | 旧検査 | 新検査 | 関係 |
|---|---|---|---|
| `allowed == ∅`（21パス） | `changed == ∅` | `changed - ∅ == ∅` ⟺ `changed == ∅` | **論理的に等価**。21パスの検査強度は1ビットも下がらない |
| `allowed == {2ファイル}`（`src/wordpress_media`） | 常にFAIL（本Releaseは変更するため） | 意図2ファイル以外の差分があればFAIL。`media_upload_result.py` の変更・削除、および **stage 済み／commit 済みの**ファイル追加は検出される（untracked かつ unstaged の追加は下記の限界により検出されない） | **限定的に緩和**。緩和範囲は設計書14.1節が宣言した2ファイルに厳密に一致する |

すなわち本精緻化は「保護をやめる」のではなく「**保護対象内で、設計書が宣言した
変更だけを通す**」ものである。これは v6.21.0 が v6.13.0 `RUNTIME-1` と
v6.20.0 `RUNTIME-1a` を「検査意図を保ったまま検出手法のみ精緻化」した
precedent（v6.21.0 設計書5.5節・5.6節）と同型である。

> **（Amendment 2で訂正：m2-1対応）`git diff` の検出範囲の限界**
>
> Amendment 1 は「新規ファイル追加・削除はいずれも検出される」と記述していたが、
> **`git diff <commit> -- <path>` は untracked ファイルを一切報告しない**。
> Review 2 が本Repositoryで実測して反証した（本設計書自身が untracked である状態で
> `git diff --name-only --relative HEAD -- docs/design` の出力が空、
> 一方 `git status --porcelain --untracked-files=all -- docs/design` は当該ファイルを報告）。
>
> したがって `NOIMPACT-SCOPE` が検出できるのは次に限られる。
>
> ```text
> 検出できる  : 追跡済みファイルの内容変更・mode 変更・削除
>               stage 済み／commit 済みの新規ファイル追加
> 検出できない: untracked かつ unstaged の新規ファイル追加
> ```
>
> v6.21.0 の guard が「未stage・stage後・commit後のいずれでも同一判定」を
> 目標としていたことに対する**既知の例外**であり、本Amendmentで明文化する。
> 補完手段は11.7.4節 `NOIMPACT-NO-UNTRACKED` として **v6.22 自前guard 側にのみ**
> 設計する（既存guardへ追加するとアサーション件数が増え GR-5 に反するため。
> GR-10 も参照）。

**パス正規化の contract**

`git diff --name-only` は既定で repository root 相対のパスを返す
（v6.21.0 の tests ブロック L911 のコメントもこの事実に言及している）。
本精緻化では **`--relative` を付与**し、project root 相対の POSIX パスを
git 自身に生成させる。

```text
git diff --name-only          8d89506 -- tests
  → projects/03_game_content_ai/tests/test_e2e_v6_13_0_....py
git diff --name-only --relative 8d89506 -- tests
  → tests/test_e2e_v6_13_0_....py           ★これを用いる
```

これにより、v6.21.0 の tests ブロックが用いている basename 正規化
（`Path(line).name`）より**厳密**な比較となる（同名ファイルが別ディレクトリに
存在する場合の取り違えが構造的に起こらない）。`--relative` は
`git -C <project_root>` で実行することを前提とする。

**ラベル改名の是非**：`NOIMPACT-UNCHANGED[...]` の名称を維持したまま
allow-list 方式へ変えると、「UNCHANGED」と称しながら差分を許容する
自己矛盾したラベルになる。本設計は **`NOIMPACT-SCOPE[...]` への改名を採用**する。
改名対象は22パス分のラベル文言であるが、**アサーション件数は 22 → 22 で不変**であり、
21パスについては期待結果も不変である（11.5節）。

#### 11.7.2 案A・案Bを採用しない理由

| 案 | 内容 | 不採用理由 |
|---|---|---|
| **案A** | v6.21 の `_protected_paths` から `"src/wordpress_media"` を**削除**する | ①`src/wordpress_media` に対する保護が**恒久的に消滅**する（`media_upload_result.py` への意図しない変更も今後検出されなくなる）。②`EXISTS`／`BASELINE-TRACKED`／`UNCHANGED` の**3アサーションが消滅**し、既存24ファイルの総数が **3389 → 3386** へ減少する。baseline 数値が動くと Regression 差分の解釈が複雑になり、11.5節の単純性が失われる |
| **案B** | v6.21 の `BASELINE_COMMIT` を v6.22 baseline（`578af6b`）へ**再指定**する | ①`src/wordpress_media` は v6.22 で変更されるため、baseline を動かしても**依然FAILする**（単独では問題を解決しない）。②v6.21 の guard が検証していた意図（「Release 6.21.0 開始時点から保護対象が1バイトも変わっていない」）が**失われる**。v6.21.0 は HEAD 基準比較を「commit 後に無効化する」として明確に退けており、baseline を後続Releaseが動かすことは同じ穴を開ける |

#### 11.7.3 X-6（`NOIMPACT-TESTS-SCOPE`）の更新

`_allowed_test_changes` を3件から**6件**へ拡張する。期待値（`[]`）と
アサーション件数（1件）は不変。

```text
{
  # v6.21.0 が認めた Guard 精緻化の例外2件（既存）
  "test_e2e_v6_13_0_article_featured_media_binding_foundation.py",
  "test_e2e_v6_20_0_article_featured_media_runtime_foundation.py",
  # v6.21.0 自身（既存）
  "test_e2e_v6_21_0_article_featured_media_runtime_wiring.py",
  # v6.22.0（本Releaseで追加）— 根拠は 3.8.2節 X-1／X-2／11.7.1節 X-5
  "test_e2e_v6_9_0_wordpress_media_upload_foundation.py",
  "test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py",
  "test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification.py",
}
```

ラベル中の「許容3件（15.3節の例外2件＋新規v6.21 E2E）」という文言も
「許容6件」へ同期する（件数を文言に埋め込む設計自体が更新を要求するため、
11.8節の一般則へ「件数を文言へ埋め込まない」旨を含める）。

#### 11.7.4 v6.22 E2E が持つべき自前の NOIMPACT guard

新規 E2E は、v6.21 と同じ構造の guard を**自身の baseline commit を固定して**持つ。

```text
BASELINE_COMMIT = Release 6.22.0 開始時点の commit
                  （設計時点では 578af6bdaeec23dd0c145a57384369ede433e3e4。
                    実装工程で確定させる）

_protected_paths        : v6.21 と同一の22パス
_allowed_source_changes : {"src/wordpress_media": 意図2ファイル}
_allowed_test_changes   : {v6_9_0, v6_19_0, v6_20_0, v6_21_0, v6_22_0}（5件）
```

さらに **S-3（vacuous pass 防止の陽性対照）** として、v6.22 E2E 側では
`src/wordpress_media` について **subset ではなく equality** を検査する。

#### equality の分解（Amendment 2で明確化：m2-4対応）

`NOIMPACT-SCOPE-EXACT[src/wordpress_media]` の equality は、**2つの独立した
含意の連言**である。両者は役割が異なるため、実装でも別アサーションとして置く。

```text
NOIMPACT-SCOPE[src/wordpress_media]        containment : changed ⊆ allowed
    → 「宣言していないものを変えていない」ことの保証（＝保護）。
      v6.21 側・v6.22 側の双方に置く。

NOIMPACT-SCOPE-COVERAGE[src/wordpress_media]  coverage : allowed ⊆ changed
    → 「宣言したものが実際に変わっている」ことの確認（＝vacuous pass 防止）。
      v6.22 側にのみ置く。

NOIMPACT-SCOPE-EXACT[src/wordpress_media]  ≡ containment ∧ coverage
    → 上記2件をまとめて表現した呼称。実装は2アサーションに分けること
      （片方だけFAILしたときに原因が一義に読めるようにするため）。
```

**coverage が vacuous pass 防止の本体である。** allow-list を書いたのに実装が
片方しか変えていない／どちらも変えていない場合、containment は成立してしまう
（`∅ ⊆ allowed` は真）。これを検出するのが coverage である。

**後続Releaseにおける安定性**（v6.21 を subset に留める理由との非対称の解消）

Amendment 1 は「v6.21 は v6.22 が実際に何を変えたかに依存すべきではない」という
理由で v6.21 側を subset に留めたが、同じ論理を v6.22 自身へ適用すると
「v6.22 も v6.23 以降に依存すべきでない」となる。この非対称は次のとおり解消される。

```text
・固定 baseline からの差分集合 changed は、後続Releaseが同じパスへ変更を
  加えるたび単調に増える（revert が起きない限り減らない）。
・したがって coverage（allowed ⊆ changed）は後続Releaseによって壊れない。
  壊れるのは「宣言した変更が revert された場合」のみであり、
  その場合に FAIL するのは望ましい挙動である。
・一方 containment（changed ⊆ allowed）は後続Releaseが同じパスへ触れると破れる。
  これは GR-9 のとおり、当該後続Releaseが allow-list を更新して解消する。
・すなわち「後続Releaseへ更新義務が生じるのは containment 側のみ」であり、
  coverage 側は v6.22 の事実を固定するだけで将来に依存しない。
  Amendment 1 の非対称は、この分解を書いていなかったことに起因する表現上の
  問題であって、設計上の矛盾ではなかった。
```

**`__init__.py` が coverage の対象になる根拠（D-3 依存の明記）**

`src/wordpress_media/__init__.py` が変更対象となる理由は **D-3（`__all__` へ
`WordPressMediaUploadErrorReason` を公開する判断、10.4節）ただ1つ**である
（Enum の import 追加と `__all__` への1要素追加）。D-3 が撤回された場合、
`__init__.py` は無変更となり coverage は成立しない。

> **D-3 の確定状況**：Architecture Review 2 において V-3（`__all__` 公開の是非）は
> **承認・close** された。したがって coverage が2ファイルを対象とする前提は確定して
> いる。将来 D-3 を見直す Release が現れた場合は、本 coverage の allow-list も
> 同時に見直す必要がある（依存関係として記録する）。

`wordpress_media_uploader.py` 側は Enum 定義・`__init__` 追加・分類関数2本・
全構築サイトへの `reason=` 付与を伴うため、D-3 とは独立に無条件で変更される。

#### untracked 追加への補完guard（Amendment 2新設：m2-1対応）

`git diff` が untracked を報告しない限界（11.7.1節）を補うため、
**v6.22 自前guard 側にのみ**次を置く。

```text
NOIMPACT-NO-UNTRACKED[<path>]   （22パスすべてを対象）
    git status --porcelain --untracked-files=all -- <path>
    の出力から status が "??" の行を抽出し、その集合が空であることを検証する。
    （allow-list の2ファイルは baseline に存在する追跡済みファイルであるため、
      untracked 集合は全パスで空であることが期待値となる）

前提の確認（Amendment 2 時点で実測済み）:
    `__pycache__/` は repository の .gitignore で無視されており、
    `git status --porcelain --untracked-files=all` は ignored ファイルを
    列挙しない（`--ignored` を付けない限り）。
    実測：保護対象パス（src/wordpress_media・src/outputs・tests）に対する
    `git status --porcelain -uall` の出力は空であり、
    ディスク上に `src/wordpress_media/__pycache__` が存在しても
    本guardは空振りしない。

GR-5（件数不変）との関係:
    本guardは既存 v6.21 guard へは追加しない。追加するとアサーション件数が
    増え、既存24ファイルの合計 3389 が動いてしまう（11.5節）。
    新Releaseの自前guard側へ置くという扱いは GR-6・GR-10 に一致する。

NOIMPACT-NO-UNTRACKED-TESTS   （Amendment 3新設：m3-1対応／Amendment 4でパス正規化を規定：m4-3対応。
                              v6.22 自前guard のみ）
    git status --porcelain --untracked-files=all -- tests
    の出力から status が "??" の行を抽出し、そのファイル名集合が
    _allowed_test_changes の範囲内であることを検証する。
    → tests/ は _protected_paths（22パス）に含まれないため
      NOIMPACT-NO-UNTRACKED の対象外であり、
      NOIMPACT-TESTS-SCOPE 側は git diff を用いるため untracked を見ない。
      Review 3 が指摘した「untracked のテスト差分が両検査の盲点になる」状態を
      本guardが埋める。
    ※ v6.22 の新規E2E自身は commit 前 untracked であるが
      _allowed_test_changes に含まれるため範囲内となる。
      意図しない stray テストファイルのみが違反として検出される。

    ★（Amendment 4追加：m4-3対応）パス正規化の contract：
      `git status --porcelain --untracked-files=all` は
      **repository root 相対のパス**を返す（`--relative` オプションを持たない。
      11.7.1節が確認した `git diff --name-only --relative` とは異なる）。
      出力の各行は `"XY <path>"`（`??` の場合は先頭2文字 `??` + 半角空白）の
      形式であるため、`Path(line[3:]).name` により**先頭3文字を除去した
      パスの basename** へ正規化してから `_allowed_test_changes`
      （basename の集合）と比較する。これは v6.21 の tests ブロック
      （L911-916、`Path(line.strip().replace("\\", "/")).name` による
      basename 正規化）と同一の考え方に揃えたものである。
```

#### baseline commit の誤指定防止（Amendment 2新設：S2-3対応）

`BASELINE_COMMIT` が誤って**Release 開始時点より新しい commit** を指すと、
`changed` が空になり containment が空振りPASSする。これを防ぐため次を置く。

```text
NOIMPACT-BASELINE-PINNED
    BASELINE_COMMIT の文字列が、本設計書が記録する Release 6.22.0 開始commit
    "578af6bdaeec23dd0c145a57384369ede433e3e4" と一致することを検証する。
    → 設計書と実装の乖離（コピー間違い・作業commitの混入）を検出する。
    ★（Amendment 3で限界を明記：m3-4対応）
      本検査は「設計書 ↔ 実装の転記整合」を確認する**文書的検査**であり、
      定数と期待リテラルが同一ファイル内にあるため、
      実装者が誤ったハッシュを両方へ書けば空振りPASSする。
      したがって期待リテラルは**必ず本設計書から転記する**運用を前提とする。
      誤指定の**実効的な検出**は次が担う:
        ・baseline が新しすぎる場合 → coverage（allowed ⊆ changed）が FAIL
        ・baseline が古すぎる場合   → NOIMPACT-BASELINE-TRACKED または
                                      containment が FAIL
          （例：baseline を v6.19 相当へ誤指定すると、v6.20 で新設された
            src/article_featured_media_runtime が baseline に存在せず
            BASELINE-TRACKED が落ちる）
      すなわち両方向の誤指定は PINNED に依存せず検出される。

NOIMPACT-BASELINE-IS-ANCESTOR
    git merge-base --is-ancestor <BASELINE_COMMIT> HEAD が exit 0 であることを
    検証する。→ baseline が現在の履歴上に存在することを保証する。

（既存の踏襲）NOIMPACT-GIT-AVAILABLE / NOIMPACT-BASELINE-RESOLVABLE /
             NOIMPACT-EXISTS / NOIMPACT-BASELINE-TRACKED

★ さらに coverage 検査（上記）が、baseline 誤指定に対する
  実効的な陽性対照として機能する:
      baseline が「wordpress_media の変更より後の commit」を指していた場合、
      changed は空になり coverage（allowed ⊆ changed）が FAIL する。
  すなわち「新しすぎる baseline」は NOIMPACT-BASELINE-PINNED と
  coverage の二重で検出される。
```

**v6.21 側の役割分担**：v6.21 guard には containment のみを置き、
coverage・`NOIMPACT-NO-UNTRACKED`・baseline 追加検査はいずれも**置かない**。
v6.21 は v6.22 以降が何を変えたかに依存すべきでなく（上記の分解）、
またアサーション件数を変えないため（GR-5）である。

### 11.8 一般則：固定 baseline guard の保護対象を後続Releaseが変更する場合（Amendment 1新設）

X-5・X-6 は「v6.21.0 が baseline 固定 guard を導入した際、保護対象を後続Releaseが
**正当に**変更する場合の手順を定めていなかった」ことに起因する。同型の衝突は
`src/wordpress_media` に限らず、**保護22パスのいずれかに触れる後続Release
（DI-5／DI-11／DI-6／DI-7 等）すべてで発生する**。本節でその一般則を定める。

```text
【GR-1】guard から保護対象を削除してはならない。
        削除は保護の恒久的喪失とアサーション件数の減少を招く（11.7.2節 案A）。

【GR-2】既存 guard の baseline commit を後続Releaseが書き換えてはならない。
        当該 Release が検証した「開始時点からの不変性」が失われる（同 案B）。

【GR-3】「差分ゼロ」検査は「差分が allow-list の範囲内」検査へ精緻化する。
        allow-list が空の対象では論理的に等価であり、検査強度は下がらない。

【GR-4】allow-list に登録できるのは、当該Releaseの設計書 File Change Plan が
        明示的に宣言したファイルのみである。設計書に無いファイルを
        allow-list へ入れてはならない（allow-list は設計の写しであり、
        実装の都合で拡張してよいものではない）。

【GR-5】精緻化はアサーションの件数を変えない方法で行う
        （期待値・許容集合リテラル・ラベル文言の差し替えに留める）。
        これにより Formal Regression baseline の数値が動かず、
        Regression 差分の解釈が単純に保たれる。

【GR-6】新Releaseは自身の E2E に、自身の baseline commit を固定した
        完全な guard を持たせる。既存Releaseの guard に依存しない。
        新Release側では allow-list を equality で検証し、
        vacuous pass を防ぐ陽性対照を置く（11.7.4節）。

【GR-7】許容件数・パス件数を**アサーションのラベル文言へ埋め込まない**
        （埋め込むと、内容が正しくても文言更新のためだけに既存ファイルを
        触る必要が生じる。X-6 がこの問題の実例である）。

【GR-8】精緻化の内容と検査意図の保持根拠を、当該Releaseの設計書へ
        「既存Guard精緻化」節として明記する。Production Implementation 工程で
        暗黙に行ってはならない。

【GR-9】（Amendment 2追加：m2-5対応）
        保護対象パスへ触れる Release は、**それ以前に存在するすべての
        baseline固定guard**の allow-list を更新する必要がある
        （v6.22 時点の対象は v6.21 guard の1件。以後 Release ごとに1件増える）。
        この結果、古いguardの allow-list は単調に増え、保護は徐々に緩む。
        これを許容できる根拠は **ratchet 構造**である：
          ・GR-6 により、各Releaseは自身の baseline を固定した guard を持つ。
          ・最新Releaseの guard は allow-list が最小（当該Releaseの宣言分のみ）で
            あり、常に最も厳格である。
          ・Runtime Zero Diff の権威的保証は「最新Releaseの guard」が与える。
            古いguardは履歴的記録として残り、
            「その時点以降に何が正当に変更されたか」を allow-list の形で示す。
        したがって古いguardの緩みは設計上の劣化ではなく、
        **正当な変更履歴が allow-list として蓄積された結果**である。
        ただし allow-list が肥大化して可読性を損なう場合は、
        当該Releaseの設計書で状況を評価し、対応を Architecture Review へ諮ること。

        ★（Amendment 3追記：m3-2対応）累積 Formal Regression の価値との関係
          本原則の帰結として、**累積 Inventory は Zero-Diff 面において
          最新guardを超える保護を提供しない**。この点を明示しておく。
          累積 Inventory の価値は次の2つにある。
            ① 各Release時点の意図の**履歴的記録**
               （allow-list が「その時点以降に何が正当に変更されたか」を示す）
            ② **Zero-Diff 以外のすべての contract**
               （Public API・behavior・security・message・分類 mapping 等）の
               重畳的な保護。これらは古いRelease の guard も等しく強く守り続ける。
          Zero-Diff 面の権威的保証は**最新Releaseの guard が単独で担う**。
          将来の Reviewer が v6.21 guard の allow-list 肥大を見て
          「規律が失われた」と読まないよう、本記述を根拠とすること。

【GR-10】（Amendment 2追加：m2-5対応）
        保護対象パスの**追加**（新package を保護下へ入れる等）は、
        新Releaseの自前guard側で行う。**既存guardへパスを追加してはならない。**
        既存guardへの追加はアサーション件数を増やし、Formal Regression baseline の
        数値を動かすためである。
        GR-5 の「件数不変」は**既存guardの精緻化**にのみ適用される制約であり、
        新Releaseが自身のguardへ新しい検査（保護パスの追加・
        NOIMPACT-NO-UNTRACKED 等の補完guard）を置くことを妨げない。

【GR-11】（Amendment 3追加：m3-3対応）
        保護対象パスが**正当に削除**される場合（package の削除・統合等）は、
        GR-1（削除禁止）および GR-5（件数不変）の**明示的な例外**として扱う。
        手順:
          1. 当該Releaseの設計書に削除理由と影響範囲を論証として記載する。
          2. 既存guardの _protected_paths から当該パスを除去する
             （除去しなければ NOIMPACT-EXISTS / BASELINE-TRACKED が
               全ての古いguardで FAIL し、規定上の解決手段がなくなるため）。
          3. 除去はアサーション件数を減らす。**減少後の Formal Regression
             baseline 数値を設計書へ明記**し、既知差分として記録する
             （GR-5 の例外であることを明示する）。
          4. 削除された package の contract を引き継ぐ後継が存在する場合は、
             後継パスを新Releaseの自前guardへ保護対象として追加する（GR-10）。
        本例外を設けない場合、package 削除は guard のデッドロックを招く
        （Review 3 の m3-3 指摘）。
```

本一般則は v6.21.0 が確立した baseline 固定 guard 方式を**否定するものではなく、
その運用手順を補完するもの**である。GR-1〜GR-8 は本Releaseで初めて適用される。

---

## 12. Data Model / Invariants

| ID | Invariant |
|---|---|
| **I-1** | `WordPressMediaUploadErrorReason` は 12値であり、すべての value は小文字snake_caseの固定ASCII文字列である |
| **I-2** | reason の value に URL・credential・response本文・status codeの生値・ファイル名は含まれない |
| **I-3** | `WordPressMediaUploadError` インスタンスは常に `reason` 属性を持つ（既定値 `UNKNOWN`） |
| **I-4** | `WordPressMediaUploadError.__init__` は例外を送出しない |
| **I-5** | `_classify_request_exception` / `_classify_status_code` は全入力に対して必ず `WordPressMediaUploadErrorReason` の値を返し、例外を送出しない（全域関数） |
| **I-6** | **（Amendment 3で単一の構築形 Contract へ整理：M3-1・S3-3対応。旧 I-6a／I-6b を吸収し廃止。Amendment 4 で型位置・docstring の扱いを追記：B4-1・m4-2対応）**<br>`src/wordpress_media/wordpress_media_uploader.py` において、**`WordPressMediaUploadError` の構築は `raise` 文直下の直接呼び出しに限り、かつ `reason` を keyword で明示する。**<br>具体的には次のすべてを満たす。<br>① 当該 module で識別子 `WordPressMediaUploadError` が AST 上に現れてよいのは **(a) クラス定義（`ast.ClassDef.name`）**・**(b) `raise` 文直下の構築 Call の callee**・**(c)〜(g) 構築を伴わない型位置**（引数注釈／戻り値注釈／`AnnAssign` 注釈／`except` 節／`isinstance`・`issubclass` の第2引数）の**7箇所のみ**である。別名束縛（`import as`／代入／`AnnAssign` の value 側／`NamedExpr`／Tuple 展開／`for` ターゲット／class 属性）・registry（dict／list）・factory／helper 内構築・`return` による受け渡し・既定引数への埋め込み・`functools.partial` の引数・`issubclass` の第1引数など、**(a)〜(g) 以外の出現は一切行わない**。<br>② 当該 module 内の **docstring 以外の位置**に文字列リテラル `"WordPressMediaUploadError"`（部分文字列。`"WordPressMediaUploadErrorReason"` を含む）を置かない（`getattr`／`globals()` 等による**未分割**文字列経由の参照の禁止。docstring は v6.11 precedent に倣い除外する。10.1節・14.1.1節参照）。<br>③ (b) の各構築 Call は keyword `reason` を持ち、位置引数は message 1個のみで、`**kwargs` 展開を用いない（(c)〜(g) は Call ノードではないため本条件の対象外）。<br>本 Contract は `GUARD-WMUE-CONSTRUCTION-SHAPE`（17.1節）が occurrence-context allow-list 方式で強制し、**raise 件数を9に固定した検査で代替してはならない**。<br>本 Contract は「`raise` 以外での構築を禁止する」ため、Amendment 2 の I-6b が課していた **module 全体の `ast.Raise` 形式に対する拘束（無関係な `ValueError` 21 raise を含む）は不要となり撤回した**。将来 (a)〜(g) 以外の出現形が正当に必要になった場合は、guard を緩めるのではなく**本 Contract 自体を Architecture Review にかけて見直す**（20章 R-12） |
| **I-7** | `upload()` は `reason` を判断材料として使用しない（分類の付与のみ。制御フローに影響しない） |

---

## 13. Error Contract

### 13.1 本Releaseが送出する例外

変更なし。`upload()` が送出しうる例外は次のとおりで、v6.21.0 時点と同一である。

| 例外 | 発生元 | 変更 |
|---|---|---|
| `ValueError` | `_validate_image_bytes` / `_validate_filename` / `_validate_mime_type` / `__init__` / `from_env` | 無変更 |
| `WordPressMediaUploadError` | `upload()` の9経路 | **型・message・条件は無変更。`reason` 属性が付く** |

### 13.2 Security Contract

| ID | 内容 |
|---|---|
| **SEC-1** | reason は固定ラベルのみ。秘密情報を含む経路が構造的に存在しない（I-2） |
| **SEC-2** | `WordPressMediaUploadError` は response object・response body・header・`site_url`・`username`・`app_password` のいずれも保持しない（変更後も同じ） |
| **SEC-3** | 分類関数は `response` object を受け取らない。`_classify_status_code` が受け取るのは `int` 1つのみ。これにより body/header への到達が構造的に不可能である |
| **SEC-4** | `_build_non_2xx_message()` の既存sanitize（制御文字正規化・`code` 100文字／`message` 200文字の切り詰め）は無変更 |
| **SEC-5** | reason を console／ログへ出力する処理は本Releaseでは追加しない（N-4・N-9） |

`_classify_status_code(status_code: int)` が response object ではなく int を受け取る設計は、
SEC-3 を「規約」ではなく「構造」として保証するための意図的な選択である。

---

## 14. File Change Plan

### 14.1 Production Code（2ファイル）

| ファイル | 変更内容 |
|---|---|
| `src/wordpress_media/wordpress_media_uploader.py` | ① `from enum import Enum` を追加<br>② `WordPressMediaUploadErrorReason`（12値）を追加<br>③ `WordPressMediaUploadError.__init__` を追加（`reason` 既定値 `UNKNOWN`）<br>④ `_classify_request_exception()` を追加<br>⑤ `_classify_status_code()` を追加<br>⑥ 9箇所の `raise` へ `reason=` を付与<br>⑦ module docstring へ Source of Truth（本設計書）を追記 |
| `src/wordpress_media/__init__.py` | `WordPressMediaUploadErrorReason` の import と `__all__` への追加（3 → 4 symbol） |

`src/wordpress_media/media_upload_result.py` は**無変更**。

#### 14.1.1 実装制約（既存guard由来。Amendment 1新設、m-1対応）

`tests/test_e2e_v6_9_0_wordpress_media_upload_foundation.py` は
`_combined_source = _uploader_source + _init_source`（L362-366）に対する
**部分文字列 deny-list guard** を持つ。これは AST ではなく素のテキスト検査であり、
**docstring・コメントも検査対象に含まれる**。したがって本Releaseで追加する
Enum・分類関数・docstring は、次の文字列を1つも含んではならない。

| guard | 禁止部分文字列 | 出典 |
|---|---|---|
| `DEP-2` | `requests.get`／`requests.put`／`requests.patch(`／`requests.delete`／`requests.request(`／`urllib`／`http.client`／`socket`／`open(`／`write_text`／`write_bytes`／`subprocess` | L940-955 |
| `DEP-3a` | `print(` | L960 |
| `DEP-3b` | `logging` | L961 |
| `DEP-4` | `featured_media` | L968 |
| `ENV-5a`／`ENV-5b` | `load_dotenv`／`dotenv` | L379-380 |
| **`GUARD-WMUE`手順4**<br>（Amendment 4追加） | `WordPressMediaUploadError`（**docstring 位置を除く**部分文字列） | 17.1節 |

**特に衝突リスクが高いもの**（本設計書本文では当該語を用いているため、
production code へ転記しないこと）：

```text
・"featured_media"（DEP-4）
    → 本Releaseの文脈説明で頻出する語。docstring では
      「アイキャッチ」等の語に置き換えるか、そもそも言及しない。
      なお空白区切りの "featured media" は部分文字列一致しないが、
      紛れを避けるため使用しない方針とする。
・"logging"（DEP-3b）
    → 「DI-5（logging）は対象外」といった注記を docstring に書くと即FAILする。
      Deferred への言及は本設計書側に留める。
・"socket"（DEP-2）
    → 本設計書17章の SOCKET- prefix は **テストファイル側**の話であり、
      production source には現れない。
```

あわせて `ENV-4`（L371-376）は `_uploader_source` 内の `"WP_[A-Z_]+"` 形式の
文字列リテラルが `WP_SITE_URL`／`WP_USERNAME`／`WP_APP_PASSWORD` の3つだけである
ことを正規表現で固定する。

**（Amendment 4追加、B4-1・m4-4対応）** 新規の `GUARD-WMUE-CONSTRUCTION-SHAPE` 手順4は、
本モジュール内の**docstring 以外**の位置で `"WordPressMediaUploadError"`（部分文字列。
`"WordPressMediaUploadErrorReason"` を含む文字列も同様に）を書くことを禁止する。
**docstring（module／`WordPressMediaUploadErrorReason`／`WordPressMediaUploadError`の
各 docstring）は対象外**であり、10.1節の Enum docstring はそのまま記述してよい。
一方コメント（`#` 行）は `ast.Constant` ではないため手順4の対象外だが、
DEP-2〜DEP-4・ENV-5（上表）の**全文 substring guard は引き続きコメントも検査対象**
とする点は変わらない。本Releaseは環境変数を追加しないため影響しないが、
Enum value や docstring に `WP_` で始まる大文字リテラルを書いてはならない。

これらはいずれも **既存guardの更新を要さない**（実装が制約を守れば PASS する）。
新規 E2E の `COMPAT-` では「v6.9 の `DEP-`／`ENV-` guard が引き続き PASS すること」を
確認対象に含める（17章）。

### 14.2 新規 E2E（1ファイル）

```text
tests/test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification.py
```

形式は v6.19／v6.20／v6.21 と同じ standalone script（`check` / `check_true` / `check_false`
ヘルパ方式、`pytest` 非依存）。

### 14.3 既存 E2E（4ファイル・6アサーション）

**（Amendment 1で改訂：B-1対応）** 11.2節 X-1〜X-6 のとおり。
**それ以外の行は触らない。**

| ファイル | 更新箇所 |
|---|---|
| `tests/test_e2e_v6_9_0_wordpress_media_upload_foundation.py` | X-1（`PM-3b` の期待値） |
| `tests/test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py` | X-2（`COMPAT-V69-ALL-*` の期待値・ラベル）／X-3（`COMPAT-WP-*` の極性） |
| `tests/test_e2e_v6_20_0_article_featured_media_runtime_foundation.py` | X-4（`COMPAT-V609` の期待値） |
| `tests/test_e2e_v6_21_0_article_featured_media_runtime_wiring.py` | X-5（`NOIMPACT-UNCHANGED[...]` → `NOIMPACT-SCOPE[...]` ＋ `_allowed_source_changes` 追加）／X-6（`_allowed_test_changes` を6件へ） |

### 14.4 ドキュメント（Documentation Integration 工程で実施）

| ファイル | 変更内容 |
|---|---|
| `docs/ROADMAP.md` | DI-10 エントリを **Release Review承認まで `[ ]` のまま維持**し、Release実績を追記。`[ ]` → `[x]` への更新は Release Review 承認後の Finalize 工程で行う（Documentation Integration 時点では Release Review Pending のため未確定） |
| `docs/architecture.md` | `## WordPress Media Upload Failure Reason Classification Foundation層（src/wordpress_media/、v6.22.0）` 節を追加（節名は本設計書の正式名称「…Classification **Foundation** 層」に一致させる）。既存の v6.9.0 節へは「reason分類は v6.22.0 で追加」のポインタを追記する（**Documentation Integration では未実施のまま残り、Release Review Finalize（RR-M-3）で実施した**。0.11節参照） |
| `docs/CHANGELOG.md` | `[v6.22.0]` エントリを追加。**X-1〜X-6 の6件**を「設計上の既知差分」として記録し、うち X-5・X-6（v6.21 NOIMPACT guard の精緻化）は11.8節の一般則 GR-1〜GR-8 に基づく初回適用であることを明記 |
| 本設計書 | Status（0章）の工程更新 |

**（Release Review Finalize追記、RR-M-2対応）** ROADMAP `[ ]` → `[x]` の更新タイミングは
「Release Review 承認まで `[ ]` を維持し、Finalize 時に `[x]` へ更新する」運用とする
（過去Release（v6.17.0 RR-M-1／v6.20.0 RR-M-1）で繰り返し指摘された「ROADMAP `[x]`
と Release 未実施表現の併存」を避けるための precedent に従う）。本Releaseでは
Documentation Integration 完了時点で `[ ]` を維持し、Release Review 承認後の
Finalize で実際に `[x]` へ更新した（`docs/ROADMAP.md`）。

### 14.5 Architecture Amendment 4 時点で変更したファイル（歴史的記録）

**（Release Review Finalize追記、RR-M-1対応）本節は Architecture Amendment 4
完了時点の記録であり、現在は歴史的記録として残す。** 当時は本設計書のみ
（1ファイル）を変更し、上記14.1〜14.4はいずれも未実施で、Production Code・
tests（既存・新規とも）・`docs/ROADMAP.md`・`docs/architecture.md`・
`docs/CHANGELOG.md` はいずれも無変更であった（Amendment 1〜4の各工程でこの
状態は変わらなかった）。**その後、Production Implementation〜Formal Regression
（0.9節）・Documentation Integration（0.2節・0.10節）・Release Review Finalize
（0.11節）を経て、14.1〜14.4はすべて実施済みとなっている。** 現在の Repository
状態は 0.2節（Documentation Integration で変更した4ファイル）・0.11節（Release
Review Finalize の反映）を正とする。

### 14.6 ROADMAP 変更案（Release Review Finalizeで適用済み）

**（Release Review Finalize追記、RR-M-2対応）本節の見出しは策定時点では
「本工程では適用しない」であったが、Release Review 承認を受けた Finalize
工程で実際に適用した。** 以下は Documentation Integration 策定時点の提案文言
（歴史的記録）であり、`docs/ROADMAP.md` L954 の実エントリは本節の提案を
土台にしつつ Formal Regression・Release Review の実績値を反映した文言と
なっている（完全な逐語一致ではない）。

`docs/ROADMAP.md` L1085-1089 の DI-10 エントリを、Release完了時点で次の形へ更新することを提案する。

```markdown
- [x] **WordPress Media Upload Failure Reason Classification（DI-10）**（v6.22.0）：
  `WordPressMediaUploadError`へ、WordPress Media Upload固有の失敗構造から導出した
  分類Enum`WordPressMediaUploadErrorReason`（12値：TIMEOUT／CONNECTION／
  AUTHENTICATION／PERMISSION_DENIED／ROUTE_NOT_FOUND／PAYLOAD_TOO_LARGE／
  UNSUPPORTED_MEDIA_TYPE／RATE_LIMIT／REQUEST_REJECTED／SERVER_ERROR／
  INVALID_RESPONSE／UNKNOWN）を純追加した。分類は例外型（requests例外階層）と
  HTTPステータスコードのみに基づき、message解析を行わない。既存9 raise経路すべてへ
  reasonを割り当て、例外型・例外message・upload()のsignature・成功時の戻り値・
  成功／失敗の分岐条件はいずれも無変更（Zero Behavior Change）。v6.19 policyは
  `reason`を読まないため12値すべてが`MEDIA_UPLOAD_FAILED`／
  `PROPAGATE_ORIGINAL_ERROR`のまま不変であり、CONTINUE対象の拡大は行っていない。
  `main.py`および`src/wordpress_media/`以外の画像系package（v6.9〜v6.20の
  12 packageから本Releaseの変更対象1件を除く11 package）はいずれも無改修
  （Runtime Zero Diff維持）。reasonは根本原因ではなく観測された構造の分類であり、
  redirect追跡等に起因するInherited Limitation（IL-1〜IL-4）を設計書10.1.2節へ明記した。
  Deferred：CONTINUE対象の拡大・status codeの属性公開・DI-11／DI-5／DI-6／DI-7は
  いずれも本Releaseの対象外
```

**上記案は Documentation Integration 策定時点では未適用だったが、Release Review
Finalize で `docs/ROADMAP.md` の DI-10 エントリへ実際に反映した（Formal Regression・
Release Review の実績値を反映した最終文言は `docs/ROADMAP.md` L954 参照）。**

---

## 15. Gate OFF / Gate ON behavior

| 状態 | 挙動 |
|---|---|
| `AI_IMAGE_GENERATION_ENABLED` 未設定／`false` | `wordpress_media` は呼び出されない。本Releaseの変更は一切実行されない |
| Gate ON・upload 成功 | v6.21.0 と完全に同一（`MediaUploadResult` を返す） |
| Gate ON・upload 失敗 | v6.21.0 と完全に同一の挙動（記事を投稿せず `log_article(result="failed")`）。**唯一の差は、送出された例外オブジェクトが `reason` 属性を持つこと。** その属性を読む consumer は本Release時点で存在しない |

本Releaseは Gate の状態にかかわらず**観測可能な挙動を変えない。**

---

## 16. Consumer 状況

| Consumer | 本Releaseでの `reason` 参照 |
|---|---|
| v6.12 `GeneratedImageWordPressMediaUploader` | 参照しない（例外を素通し） |
| v6.14 `ArticleFeaturedMediaOrchestrator` | 参照しない |
| v6.19 `decide_image_generation_fallback()` | **参照しない**（型のみで判定。3.5節） |
| v6.20 `ArticleFeaturedMediaRuntime` | 参照しない |
| v6.21 `main.py` | 参照しない（例外を変数へ束縛しない） |

すなわち本Releaseは **`reason` の consumer が存在しない状態で分類だけを確立する**。
これは v6.9.0〜v6.20.0 が一貫して採ってきた Consumer-less Foundation 方式と同型であり、
分類（本Release）と判断（将来Release）を分離する 9.3節の責任境界に対応する。

---

## 17. Test Strategy（概要）

詳細な Scenario 設計は Test Review 工程で確定する。本設計書では **prefix 構成と
必ず検証すべき contract** のみを規定する。

| prefix | 検証対象 |
|---|---|
| `API-` | Enum の存在・値数が12・各 value 文字列・package root からの参照可否・`__all__` が4 symbol |
| `SIG-` | `WordPressMediaUploadError.__init__` の parameter 名が `["self", "message", "reason"]`・`reason` の既定値が `UNKNOWN` |
| `CTOR-` | 1引数構築（後方互換）・positional 2引数・keyword 2引数の3形式すべてで `reason` が期待値になる |
| `NOVAL-` | 不正な reason 値（`str`／`None`／`list`）を渡しても `__init__` が例外を送出しない（I-4） |
| `REQEXC-` | `_classify_request_exception` の型判定。**`ConnectTimeout` → `TIMEOUT`**（3.3節の多重継承。判定順序の回帰検出）・`ReadTimeout` → `TIMEOUT`・`Timeout` → `TIMEOUT`・`ConnectionError` → `CONNECTION`・`SSLError` → `CONNECTION`・`ProxyError` → `CONNECTION`・`TooManyRedirects` / `URLRequired` / `InvalidURL` / `ChunkedEncodingError` / `RetryError` / `RequestException` → `UNKNOWN` |
| `STATUS-` | `_classify_status_code` の値判定。401／403／404／413／415／429 の個別値、400・402・405・409・422 → `REQUEST_REJECTED`、500・502・503・599 → `SERVER_ERROR`、199・300・304・600 → `UNKNOWN`、`True`／`404.0`／`None` → `UNKNOWN`（防御的分岐） |
| `REASON-R1`〜`REASON-R9` | **9 raise経路それぞれの reason を1件ずつ固定**（D-1c の検出手段。Fake response／monkeypatch した `requests.post` で各経路を再現） |
| `MSG-` | 9経路すべての message が v6.21.0 時点の文字列と完全一致（C-4・G-4'）。`_build_non_2xx_message()` の出力形式も固定 |
| `COND-` | 成功／失敗の分岐条件が不変（2xx 境界値 200・299・300、`id` の `bool`／`0`／`-1` 等） |
| `SUCCESS-` | 2xx 正常系で `MediaUploadResult` が不変・例外なし（C-1） |
| `CHAIN-` | R-1・R-3 の `__cause__` が保持される（C-5） |
| `NOPARSE-` | **（Amendment 2でスコープ確定：m2-3対応。Documentation Integrationで`message`を追加しAC-6.22-13と同期：M2R-1対応）AST 検査**。対象は **`_classify_request_exception` と `_classify_status_code` の2関数の `ast.FunctionDef` 本体のみ**とし、その内部に `str(exc)`／`message`／`exc.args`／`response.text`／`response.json()`／`response.headers`／`response.content` への参照が存在しないことを検証する（G-3'）。<br>**対象外を明記する**：`_build_non_2xx_message()`（L67 の `response.json()`。同関数はローカル変数`message`も保持するが対象外）と `upload()`（L169 の `response.json()`）の既存呼び出しは**本guardの対象ではない**。message 生成および応答本文の契約検証は「分類」ではなく、v6.21.0 時点から存在する正当な処理であり本Releaseは無変更である（G-4'・N-14）。**module 全体を対象に実装してはならない**（実装すると既存の正当な呼び出しにより即FAILする） |
| `GUARD-` | **（Amendment 3で方式転換、Amendment 4でallow-list精緻化：M3-1・S3-3・B4-1・m4-2対応）occurrence-context allow-list 方式の AST 検査。規範仕様は 17.1節に置く。** `GUARD-WMUE-CONSTRUCTION-SHAPE`（識別子の出現文脈を allow-list で縛る単一guard＋docstring除外付き文字列リテラル検査）と、10形の合成ソース（P-1〜P-10）＋負の対照9形（N-1〜N-9）を用いた `GUARD-WMUE-POSITIVE-CONTROL` から成る。旧 `GUARD-NO-ALIAS`／`GUARD-NO-PREBUILT-RAISE`／`GUARD-NO-POSITIONAL-REASON` は統合guardへ吸収して**廃止**した（module 全体の raise 形式に対する過剰拘束も解消） |
| `SEC-` | reason 全12値の value が固定ラベル集合と一致し、URL・credential・response本文を含まない（I-2）。例外インスタンスが response object を保持しない |
| `POLICY-` | **v6.19 `decide_image_generation_fallback()` が12 reason すべてに対し `MEDIA_UPLOAD_FAILED` / `PROPAGATE_ORIGINAL_ERROR` を返す**（11.4節・N-1） |
| `DEP-` | **AST 検査**：**（Implementation Review m3で対象を明確化）** `src/wordpress_media/wordpress_media_uploader.py`（単一ファイル）の import が `os`／`re`／`enum`／`requests`／`.media_upload_result` のみ（G-7'）。`__init__.py` は `.media_upload_result`／`.wordpress_media_uploader` の相対importを行うため、本allow-listの対象は `wordpress_media_uploader.py` に限定する（`__init__.py` は v6.9 `DEP-1` deny-list guardが引き続き担う） |
| `SOCKET-` | `socket.getaddrinfo`／`socket.socket.connect` を遮断した状態で全テストが完走する（実HTTP通信0件） |
| `NOIMPACT-` | **（Amendment 1で改訂、B-1対応）** baseline commit 固定・allow-list 方式による Runtime Zero Diff（11.7.4節）。`_protected_paths` 22件について `EXISTS`／`BASELINE-TRACKED`／`SCOPE` を検査し、`src/wordpress_media` のみ allow-list に意図2ファイルを登録する。さらに `NOIMPACT-SCOPE-EXACT[src/wordpress_media]` で **subset ではなく equality** を検査し、allow-list を書いたのに実装が変更していないという空振りを検出する（S-3） |
| `COMPAT-` | v6.10〜v6.21 の各 package の `__all__` 不変・`MediaUploadResult` 不変・`upload()` signature 不変・`WordPressMediaUploadError` の基底が `RuntimeError` |
| `COMPAT-DEP-` | **（Amendment 1追加、m-1対応）** v6.9 の `DEP-1`〜`DEP-4`・`ENV-4`・`ENV-5` guard が本Releaseの実装後も PASS することを確認する（14.1.1節の実装制約が守られていることの二重確認） |

**全テストは hermetic とする**（Fake response object と monkeypatch した `requests.post` のみを使用。
実 WordPress・実 OpenAI・実ネットワークへ一切到達しない）。
これは v6.21.0 Release Review M-2（非hermetic環境の排除）で確立した方針に従う。

### 17.1 `GUARD-WMUE-CONSTRUCTION-SHAPE` の規範仕様（Amendment 3で方式転換・Amendment 4でallow-list精緻化：M3-1・S3-3・B4-1・m4-1〜m4-4対応）

**本節が `GUARD-` 群の唯一の規範仕様である**（10.2節 D-1c・12章 I-6 の記述と
本節が食い違う場合、本節を優先する）。

#### 方式転換の理由（deny-list → occurrence-context allow-list）

Amendment 1・Amendment 2 の仕様はいずれも「**禁止する構文形を列挙する
deny-list**」であった。Architecture Review 3 は、正規の構築サイトが併存する
実条件（実モジュールは9件の正規サイトを持つ）で攻撃検証を行い、
**9形のうち8形が「どの guard も発火しない＝迂回成功」**であることを実測で示した。

```text
Amendment 2 仕様を迂回できた形（Review 3 実測）:
  A1  c = getattr(sys.modules[__name__], "WordPressMediaUploadError"); raise c("m")
  A2  raise globals()["WordPressMediaUploadError"]("m")
  A3  _m = functools.partial(WordPressMediaUploadError); raise _m("m")
  A4  def _err(msg, reason=R.UNKNOWN): return WMUE(msg, reason=reason)
      raise _err("m")                        ← 現実的なリファクタで発生しうる
  A11 _M = {"e": WMUE}; raise _M["e"]("m")
  A12 _L = [WMUE];      raise _L[0]("m")
  A13 def _cls(): return WMUE; raise _cls()("m")
  A14 def _r(msg, E=WMUE): raise E(msg)
  （A15 class H: E = WMUE → raise H.E("m") のみ旧 GUARD-NO-ALIAS が偶然検出）
```

名前の間接参照は無限に書けるため、**禁止形の列挙は原理的に閉じない**。
これは本プロジェクトが v6.19 §10.3 で CONTINUE 対象に allow-list を採用した
理由（deny-list は値の追加に耐えない）と同型の問題である。
したがって **「識別子が現れてよい文脈」を allow-list で縛る方式**へ転換する。

#### 規範仕様

```text
guard 名 : GUARD-WMUE-CONSTRUCTION-SHAPE
対象     : src/wordpress_media/wordpress_media_uploader.py のみ
           ★ src/wordpress_media/__init__.py は手順4（文字列検査）の
             対象に含めてはならない。同ファイルは __all__ に
             "WordPressMediaUploadError" を文字列として持つためである。

手順:
 1. ast.parse で module 全体の AST を得る。

 2. 【allow-list の構築】許可される出現ノード集合 ALLOWED を作る。
      (a) ast.ClassDef で name == "WordPressMediaUploadError" のノード
          （クラス定義そのもの）
      (b) ast.Raise の exc が ast.Call であり、その func が
            ast.Name(id="WordPressMediaUploadError")      または
            ast.Attribute(attr="WordPressMediaUploadError")
          である場合の、その func ノード
      ★ (b) は「raise 文の直下で直接構築する形」のみを許可する。
        raise 以外の場所での構築（変数代入・return・registry 登録・
        helper 関数内・partial の引数 等）は一切許可しない。

      ★★（Amendment 4追加：m4-2対応）以下 (c)〜(g) は、構築を一切伴わない
        「型位置」の参照を許可する。いずれも ast.Call ノードではないため
        手順5（構築形検査）の対象にはならず、構築を迂回する経路にもならない。

      (c) ast.arg の annotation が
            ast.Name(id="WordPressMediaUploadError")      または
            ast.Attribute(attr="WordPressMediaUploadError")
          である場合の、その annotation ノード（関数引数の型注釈）

      (d) ast.FunctionDef / ast.AsyncFunctionDef の returns が
          上記と同じ形である場合の、その returns ノード（戻り値の型注釈）

      (e) ast.AnnAssign の annotation が上記と同じ形である場合の、
          その annotation ノード（変数の型注釈。構築を伴わない
          `e: WordPressMediaUploadError` の形。`e: T = WordPressMediaUploadError`
          のように annotation と value の両方に出現する場合、value 側は
          引き続き ALLOWED 外＝違反として検出される）

      (f) ast.ExceptHandler の type が
          ast.Name／ast.Attribute（上記と同じ形）であるか、
          または ast.Tuple でありその elts のいずれかが同じ形である場合の、
          その該当ノード（`except WordPressMediaUploadError:` および
          `except (WordPressMediaUploadError, ValueError):` の両方を許可する）

      (g) ast.Call の func が ast.Name(id="isinstance") または
          ast.Name(id="issubclass") であり、その **第2引数（args[1]）**が
          ast.Name／ast.Attribute（上記と同じ形）であるか、
          または ast.Tuple でありその elts のいずれかが同じ形である場合の、
          その該当ノード。
          ★ 第1引数（`issubclass(WordPressMediaUploadError, Exception)` の
            ように WMUE 自身の親子関係を検査する形）は対象外のまま残し、
            allow-list には含めない（21章 V-16 で Review 5 の判断対象とする、
            安全側＝より制約が強い側に倒した意図的なスコープ限定）。

 3. 【出現の全数検査（本guardの核心）】module 内を ast.walk で走査し、
    識別子 "WordPressMediaUploadError" が現れる全ノードを列挙する。
      ・ast.ClassDef の name
      ・ast.Name の id
      ・ast.Attribute の attr
      ・ast.alias の name（ドット区切りの末尾要素）または asname
    列挙されたノードのうち ALLOWED（(a)〜(g)）に属さないものが1件でもあれば
    違反とする。違反ノードの行番号リストを収集し、期待値 [] と比較する。

    → これ1つで次がすべて「ALLOWED 外の出現」として検出される。
        alias（import as / 代入 / AnnAssign の value 側 / NamedExpr /
               Tuple 展開 / for ターゲット / class 属性）
        registry（dict / list / set への登録）
        factory・helper 関数内での構築
        return による class オブジェクトの受け渡し
        既定引数への埋め込み（def f(E=WMUE)。annotation ではなく
          arguments.defaults 側の出現であるため (c) には該当しない）
        functools.partial の引数
        issubclass() の第1引数（(g) の意図的なスコープ限定により）
      迂回形を個別に列挙する必要がない。これが deny-list からの転換点である。
      （c）〜（g）を追加してもこれらの迂回形はいずれも ALLOWED に含まれず、
      引き続き違反として検出される（Amendment 4 で regression 検証済み。
      21章 V-16）。

 4. 【文字列間接参照の封鎖】module 内の ast.Constant のうち value が str 型で
    "WordPressMediaUploadError" を含み、かつ**docstring 位置ではないもの**が
    存在しないことを検証する。
    → getattr(mod, "WordPressMediaUploadError")
       globals()["WordPressMediaUploadError"]
       importlib / vars() 等による文字列経由の参照を封じる。

    ★★（Amendment 4追加：B4-1対応）docstring 除外の定義：
      次のいずれかに該当する ast.Constant は「docstring 位置」として
      本検査から除外する。
        ・ast.Module の body[0] が ast.Expr(value=当該Constant) である場合
        ・ast.ClassDef の body[0] が同上である場合
        ・ast.FunctionDef／ast.AsyncFunctionDef の body[0] が同上である場合
      （ネストしたクラス・関数のいずれについても、body 先頭の docstring は
        同様に除外する。ast.walk は再帰的に全 ClassDef／FunctionDef を
        走査するため、ネスト位置に関わらず判定できる）
      除外理由：docstring は名前解決（`getattr` / `globals()` / `importlib`）に
      使われる実行時の値ではなく、静的な説明文にすぎない。除外しても
      動的参照の検出力は1ビットも落ちない。10.1節が規定する
      `WordPressMediaUploadErrorReason` の docstring
      「WordPressMediaUploadErrorの安全な失敗分類。」はこれで違反にならない
      （S4-1：v6.11 `OpenAIImageGenerationErrorReason` の docstring
      「`OpenAIImageGenerationError`の安全な失敗分類。」と同型の既存慣行）。

    ★★（Amendment 4追加：m4-1・m4-4対応）本検査の限界を明記する。
      ・**部分文字列一致**である（`NAME in constant.value`）。したがって
        docstring 以外の位置で `WordPressMediaUploadErrorReason` を含む
        文字列を書いた場合も、docstring 除外後なお違反として検出される
        （17章 P-10）。
      ・本検査が対象とするのは**未分割**のリテラルのみである。
        `"WordPressMediaUpload" + "Error"` のような意図的な文字列分割、
        f-string の部分結合（`f"WordPressMedia{'UploadError'}"`）は
        各 ast.Constant が NAME を個別に含まないため検出できない。
        これらは静的追跡が構造的に不可能であり、**本guardの脅威モデルは
        偶発的な reason 渡し忘れの防止であって、意図的な難読化の防止では
        ない**ため、検出できないことを受容する（20章 R-14）。
      ・type comment（`# type: (...) -> ...`）はプレーンな `ast.parse()`
        （`type_comments=True` を指定しない）では AST に一切現れないため、
        本検査の対象外である。type comment は実行時の名前解決に使われず
        無害である。

 5. 【構築形の検査】ALLOWED の **(b) のみ**に属する各 Call について次を検証する
    （(c)〜(g) は Call ノードではないため本検査の対象にならない）。
      ・keywords に arg == "reason" の要素が存在する          （reason= 必須）
      ・args の個数が 1（message のみ）である                 （positional reason 禁止）
      ・keywords に arg is None の要素が存在しない            （**kwargs 展開の禁止）
    違反サイトの行番号リストを収集し、期待値 [] と比較する。

 6. 【vacuous pass 防止】ALLOWED の (b) が1件以上存在することを確認する。
    ★ 件数を9に固定してはならない。「構築サイト数 == 9」という検査は
      本guardの代替にならない（I-6）。参考情報としての件数出力は許容する。

契約（Amendment 4追加、S4-2対応）：
  本guardは **単一の検査関数として実装**し、実ファイル・
  GUARD-WMUE-POSITIVE-CONTROL の全陽性対照（P-1〜P-10）・
  全負の対照（N-1〜N-9）のいずれに対しても**同一の関数**を適用する。
  陽性対照専用・実ファイル専用に別の実装を持たない
  （仕様と検査実装が乖離し、陽性対照だけが別実装になって
    実ファイル側の穴を検出できなくなることを防ぐため）。
```

#### 旧 guard の吸収・廃止（Amendment 3）

| 旧 guard | 扱い | 根拠 |
|---|---|---|
| `GUARD-REASON-EXHAUSTIVE` | **本guardへ改称・吸収**（手順5・6が対応） | 主検査を継承 |
| `GUARD-NO-ALIAS` | **廃止**（手順3が包含。alias は「ALLOWED 外の出現」として検出される） | 個別禁止が不要になった |
| `GUARD-NO-PREBUILT-RAISE` | **廃止** | 手順2(b) が「raise 直下の直接構築のみ許可」とするため、事前構築＋変数経由 raise は手順3で必ず検出される。**module 全体の `ast.Raise` 形式を拘束する必要がなくなり、無関係な `ValueError` の raise 12件に対する過剰拘束が解消された**（Review 3 の V-16 後半の指摘） |
| `GUARD-NO-POSITIONAL-REASON` | **廃止**（手順5が包含） | 同上 |

これにより guard は **1本＋文字列検査1本**に集約され、閉じる形は 3形 → 12形以上へ拡大し、
過剰拘束は解消された。

**（Amendment 4追記）** Amendment 4 は上記の方式・許可2形（(a)(b)）を変更していない。
allow-list へ (c)〜(g) の型位置（構築非関与）を追加し、手順4 から docstring を
除外しただけであり、旧3 guard の廃止・過剰拘束の解消という結論は不変である。

#### 現行実装への適合性（Amendment 3 時点で実測確認済み。Amendment 4 で再確認）

```text
src/wordpress_media/wordpress_media_uploader.py における
識別子 "WordPressMediaUploadError" の出現:
    ast.ClassDef.name  : 1件（L24）
    ast.Name.id        : 9件（L161,166,171,176,182,187,192,197,202）
                         → その 9件すべてが Raise.exc.func であることを確認
    ast.Attribute.attr : 0件
    ast.alias          : 0件
    文字列リテラル      : 0件
    ast.AnnAssign      : 0件 / ast.NamedExpr : 0件

⇒ 手順2の ALLOWED（1 + 9 = 10ノード）と手順3の出現集合が完全一致し、
  **allow-list は余白ゼロでちょうど適合する**。
  実ファイルへ本guardを適用すると現時点では手順5で NO-REASON を報告する
  （reason= が未実装であるため。実装後にPASSへ転じることが期待値）。

（Amendment 4 で再測定）14.1.1節・10.1節が規定する docstring
  （module docstring・WordPressMediaUploadErrorReason の docstring・
    WordPressMediaUploadError の docstring）を含めて手順4を適用しても、
  いずれも docstring 位置として除外され、手順3／手順4 の違反は
  引き続き0件である（10.1節＋10.2節の規定どおりの production code を
  合成して検証済み）。(c)〜(g) の型位置は現行実装（v6.22 設計時点）には
  出現しないため、allow-list 拡張は現状のPASS/FAIL判定に影響しない。
```

#### GUARD-WMUE-POSITIVE-CONTROL（陽性対照。Amendment 3で9形へ拡張・Amendment 4でP-10を追加）

同じ検査関数へ、次の**10種の合成ソース**（実ファイルではなく文字列として
`ast.parse` する）を通し、**いずれも違反として検出される**ことを確認する。
各合成ソースには**正規の構築サイト1件を必ず併存させる**
（Review 3 が示したとおり、単独スニペットでは手順6 が発火してしまい
迂回の検出力を検証できないため。これは陽性対照の設計要件である）。

```text
共通の土台（すべての合成ソースに含める）:
    raise WordPressMediaUploadError("ok", reason=R.TIMEOUT)

P-1  reason= 欠落        raise WordPressMediaUploadError("m")            → 手順5
P-2  別名 import         from .x import WordPressMediaUploadError as E
                         raise E("m")                                   → 手順3（alias）
P-3  事前構築 raise      e = WordPressMediaUploadError("m", reason=R.X)
                         raise e                                        → 手順3（Assign）
P-4  positional reason   raise WordPressMediaUploadError("m", R.X)      → 手順5
P-5  getattr 経由        c = getattr(m, "WordPressMediaUploadError")
                         raise c("m")                                   → 手順4（文字列）
P-6  globals() 経由      raise globals()["WordPressMediaUploadError"]("m") → 手順4（文字列）
P-7  functools.partial   _m = functools.partial(WordPressMediaUploadError)
                         raise _m("m")                                  → 手順3（partial 引数）
P-8  factory/helper      def _err(msg, reason=R.UNKNOWN):
                             return WordPressMediaUploadError(msg, reason=reason)
                         raise _err("m")                                → 手順3（raise 直下でない）
P-9  dict/list registry  _M = {"e": WordPressMediaUploadError}
                         raise _M["e"]("m")                             → 手順3（dict 値）
     （同型として list registry・return 経由・既定引数埋め込み・
       class 属性経由・AnnAssign の value 側／NamedExpr／Tuple 展開／
       for ターゲットも、いずれも手順3で検出される。P-9 を代表として
       実装し、残りは同一の検出経路であることを注記すれば足りる）
P-10 非docstring文字列   x = "WordPressMediaUploadErrorReason"           → 手順4（文字列）
     （Amendment 4追加：m4-4対応）docstring 除外後も、docstring
       以外の位置で NAME を含む文字列は引き続き違反となることの確認。
       Reason Enum 名（NAME を部分文字列として含む）も対象に含める。

負の対照（PASS すべき形。Amendment 4でN-2〜N-9を追加）:
N-1  正常形                     raise WordPressMediaUploadError("m", reason=R.X)     → 違反0件
N-2  引数注釈                    def f(e: WordPressMediaUploadError) -> None: ...     → 違反0件
N-3  戻り値注釈                  def f() -> WordPressMediaUploadError: ...            → 違反0件
N-4  AnnAssign 注釈              e: WordPressMediaUploadError                        → 違反0件
N-5  except 節（単一・Tuple）    except WordPressMediaUploadError: ...
                                 except (WordPressMediaUploadError, ValueError): ...  → 違反0件
N-6  isinstance（単一・Tuple）   isinstance(e, WordPressMediaUploadError)
                                 isinstance(e, (WordPressMediaUploadError, X))        → 違反0件
N-7  issubclass（第2引数）       issubclass(E, WordPressMediaUploadError)             → 違反0件
N-8  Enum docstring             class WordPressMediaUploadErrorReason(Enum):
                                     [Enum docstring 1行目。10.1節の規定文言そのもの]
                                                                                      → 違反0件（10.1節の規定どおり）
N-9  module docstring           [module docstring。WordPressMediaUploadError を送出するモジュール、等]
                                                                                      → 違反0件
```

陽性対照が1つでもPASS（＝違反を検出できない）した場合、当該guardは検証力を
持たないものとして扱い、実装をやり直す。負の対照 N-1〜N-9 のいずれかが
違反として検出された場合も同様である（false positive の検出）。

Amendment 4 で P-1〜P-9・N-1 に加えて **P-10・N-2〜N-9 を project venv 上で
独立に実装・実行し、全19ケースが期待どおりの結果（P系はDETECT・N系はPASS）
になることを確認済み**（regression 0件。Review 3 が実測した18攻撃形も
allow-list 拡張後に全件 DETECT のまま維持されることをあわせて確認した）。

**（Amendment 1追加、S-3対応）vacuous pass 防止の陽性対照を必須とする。**
「常にPASSするだけで検証力を持たない」テストを排除するため、次の3種には
陽性対照（意図的に違反する入力を与えて FAIL 側が検出されること）を置く。

```text
・GUARD-WMUE-CONSTRUCTION-SHAPE → GUARD-WMUE-POSITIVE-CONTROL の10形 P-1〜P-10
                                ＋負の対照 N-1〜N-9（17.1節）
・NOPARSE-（AST検査）          → 禁止参照を含む合成ソースが違反として検出されること
                                （対象は分類関数2本のみ。m2-3）
・STATUS- の非int防御分岐       → production 到達不能（20章 R-6）であることを明記のうえ、
                                Fake 入力での分類結果を固定する
・NOIMPACT-                    → v6.21.0 が既に持つ GIT-AVAILABLE／BASELINE-RESOLVABLE／
                                EXISTS／BASELINE-TRACKED の4種を踏襲し、
                                加えて SCOPE-EXACT（11.7.4節）を置く
```

---

## 18. Acceptance Criteria

```text
AC-6.22-1   WordPressMediaUploadErrorReason が12値で定義され、各valueが
            10.1節の固定文字列と一致する
AC-6.22-2   WordPressMediaUploadErrorReason が package root から参照でき、
            __all__ が4 symbol（MediaUploadResult / WordPressMediaUploadError /
            WordPressMediaUploadErrorReason / WordPressMediaUploader）である
AC-6.22-3   WordPressMediaUploadError.__init__ の parameter が
            ["self", "message", "reason"] であり、reason の既定値が UNKNOWN である
AC-6.22-4   WordPressMediaUploadError("msg") の1引数構築が成立し、
            reason が UNKNOWN になる（後方互換）
AC-6.22-5   WordPressMediaUploadError.__init__ がいかなる入力に対しても
            例外を送出しない
AC-6.22-6   _classify_request_exception が全域関数であり、ConnectTimeout を
            TIMEOUT へ分類する（Timeout を ConnectionError より先に判定する）
AC-6.22-7   _classify_status_code が全域関数であり、401/403/404/413/415/429 を
            個別 reason へ、その他4xx を REQUEST_REJECTED、5xx を SERVER_ERROR、
            それ以外（非int含む）を UNKNOWN へ分類する
AC-6.22-8   【Amendment 2で表現を改訂：S2-1対応】upload() の
            「現時点で9件である全 raise 経路」それぞれが reason= を明示指定し、
            3.2節の mapping と一致する。
            ※本ACは mapping の正しさを behavioral に確認するものであり、
              「構築サイトの網羅性」の検査ではない。網羅性は件数に依存しない
              AC-6.22-23（GUARD- 群）が担う。両者の役割は
              I-6（件数を9に固定した検査で代替してはならない）のとおり分離される。
AC-6.22-9   9 raise経路の message が v6.21.0 時点の文字列と完全一致する
            （_build_non_2xx_message() の出力形式を含む）
AC-6.22-10  成功／失敗の分岐条件が v6.21.0 時点と同一である
AC-6.22-11  2xx 正常系で MediaUploadResult が v6.21.0 時点と同一である
AC-6.22-12  R-1・R-3 の __cause__ が保持される
AC-6.22-13  【Amendment 2でスコープ確定：m2-3対応。Implementation Review m1で
            17章との不一致を修正】_classify_request_exception と
            _classify_status_code の2関数の ast.FunctionDef 本体が
            str(exc)／message／exc.args／response.text／response.json()／
            response.headers／response.content を参照しない（AST検査）。
            _build_non_2xx_message() / upload() の既存 response.json() は
            本ACの対象外であり、module 全体を対象に検査してはならない
AC-6.22-14  decide_image_generation_fallback() が12 reason すべてに対し
            MEDIA_UPLOAD_FAILED / PROPAGATE_ORIGINAL_ERROR を返す
            （CONTINUE対象が拡大されていない）
AC-6.22-15  【Implementation Review m3で対象を明確化】
            src/wordpress_media/wordpress_media_uploader.py（単一ファイル）の
            import が os/re/enum/requests/.media_upload_result のみである
            （AST検査）。__init__.py はこの対象に含めない
            （.wordpress_media_uploaderへの相対importを正当に持つため）
AC-6.22-16  【Amendment 1で改訂：B-1・m-2対応】Runtime Zero Diff：
            main.py / src/image_resolver.py / src/outputs/ / src/pipeline/ /
            scripts/ / src/logger/ / src/analytics/ / src/ai/ / src/scheduler/ /
            「画像系 package のうち src/wordpress_media/ を除く11 package」/
            requirements.txt / .env.example が、baseline commit 比較で無変更である
            （対象は v6.21.0 _protected_paths と同一の22パスから
              src/wordpress_media を除いた21パス）
AC-6.22-17  【Amendment 1で改訂：B-1対応】更新した既存E2Eアサーションが
            X-1〜X-6 の6件（4ファイル）のみであり、追加・削除が0件であるため
            既存24ファイルのアサーション総数が 3389 のまま不変である
AC-6.22-18  正式 Regression Inventory が25ファイルとなり、
            既存24ファイル 3389/3389 PASS ＋ 新規v6.22 E2E 全件 PASS である
AC-6.22-19  全テストが hermetic であり、実HTTP通信・実API接続・
            credential使用が0件である
AC-6.22-20  reason 全12値の value に URL・credential・response本文・
            status codeの生値が含まれない
AC-6.22-21  【Amendment 1追加：B-1対応】v6.21.0 E2E の NOIMPACT guard が
            allow-list 方式（NOIMPACT-SCOPE）へ精緻化され、
            (a) allow-list が空の21パスでは「差分ゼロ」と論理的に等価な検査が維持され、
            (b) src/wordpress_media では設計書14.1節が宣言した2ファイル以外の
                差分（media_upload_result.py の変更・ファイル追加・削除を含む）が
                依然として検出され、
            (c) 1パスあたりのアサーション構成が EXISTS / BASELINE-TRACKED / SCOPE の
                3件のまま不変である
AC-6.22-22  【Amendment 1追加：B-1対応】v6.21.0 E2E の _allowed_test_changes が
            6件へ更新され、NOIMPACT-TESTS-SCOPE が期待値 [] のまま PASS する。
            v6.22 E2E は自身の baseline commit を固定した guard を持ち、
            NOIMPACT-SCOPE-EXACT[src/wordpress_media] が equality で PASS する
AC-6.22-23  【Amendment 3で方式転換・Amendment 4でallow-list精緻化：
            M3-1・S3-3・B4-1・m4-2対応】17.1節の規範仕様どおり
            GUARD-WMUE-CONSTRUCTION-SHAPE が成立する。対象は
            src/wordpress_media/wordpress_media_uploader.py のみであり、
            __init__.py は手順4（文字列検査）の対象に含めない。
            (a) 出現の全数検査：識別子 "WordPressMediaUploadError" が現れる
                全ノード（ClassDef.name / Name.id / Attribute.attr /
                alias.name・asname）を列挙し、allow-list
                （①クラス定義 ②raise 文直下の構築 Call の callee
                  ③引数注釈 ④戻り値注釈 ⑤AnnAssign注釈 ⑥except節
                  （単一／Tuple） ⑦isinstance・issubclassの第2引数
                  （単一／Tuple）の7種のみ）に属さない出現が0件である
            (b) 文字列間接参照の封鎖：当該module内の**docstring位置を除く**
                str 型 ast.Constant に "WordPressMediaUploadError" を
                含むものが0件である（module／ClassDef／FunctionDef／
                AsyncFunctionDef の body 先頭 docstring は除外する）
            (c) 構築形の検査：許可された(a)②の各構築 Call が keyword reason
                を持ち、位置引数が1個（message のみ）で、arg is None の
                keyword（**kwargs 展開）を持たない。(a)③〜⑦は Call ノード
                ではないため本検査の対象にならない
            (d) vacuous pass 防止：許可された構築 Call（(a)②）が1件以上
                存在する。かつ検査が件数を9に固定していない
            ※ 旧 GUARD-NO-ALIAS / GUARD-NO-PREBUILT-RAISE /
              GUARD-NO-POSITIONAL-REASON は本guardへ吸収され廃止された。
              module 全体の ast.Raise 形式に対する拘束は課さない
              （無関係な ValueError の raise 形式は自由）
AC-6.22-25  【Amendment 3で全面改訂・Amendment 4でP-10/負の対照拡張：
            M3-1・m4-2・m4-4対応】GUARD-WMUE-POSITIVE-CONTROL の
            10形（P-1 reason= 欠落／P-2 別名 import／P-3 事前構築 raise／
            P-4 positional reason／P-5 getattr／P-6 globals()／
            P-7 functools.partial／P-8 factory・helper／P-9 dict registry／
            P-10 非docstring文字列）が、いずれも違反として検出される。
            各合成ソースには正規の構築サイト1件を必ず併存させる
            （単独スニペットでは手順6が発火し迂回の検出力を検証できないため。
              Review 3 が実測で示した陽性対照の設計要件）。
            負の対照 N-1〜N-9（正常形／引数注釈／戻り値注釈／AnnAssign注釈／
            except節／isinstance／issubclass／Enum docstring／
            module docstring）がいずれも違反として検出されないことも確認する。
            1つでも期待と異なる場合は当該guardを検証力なしとして扱う
AC-6.22-28  【Amendment 4追加：m4-2対応】allow-list へ (c)〜(g) の型位置を
            追加した後も、Review 3 が実測した全18攻撃形（P-1〜P-9・
            A11〜A15・A5a〜A5d・m3-5 **kwargs）が引き続き違反として
            検出される（regression 0件であることを実装時に再確認する）
AC-6.22-26  【Amendment 2追加：m2-1・S2-3対応。Amendment 3・4で拡張：
            m3-1・m4-3対応】v6.22 自前guard において
            (a) NOIMPACT-NO-UNTRACKED[<path>] が22パスすべてで untracked 集合が
                空であることを確認する（.gitignore により __pycache__ が
                列挙されないことは Amendment 2 時点で実測確認済み）
            (a2) NOIMPACT-NO-UNTRACKED-TESTS が tests/ について、
                 git status --porcelain --untracked-files=all -- tests の
                 各行を Path(line[3:]).name で basename へ正規化し
                 （repo-root 相対パスを返すため。v6.21 tests ブロックと
                   同一方式。11.7.4節）、その集合が _allowed_test_changes
                 の範囲内であることを確認する
            (b) NOIMPACT-BASELINE-PINNED が BASELINE_COMMIT ==
                "578af6bdaeec23dd0c145a57384369ede433e3e4" を確認する
            (c) NOIMPACT-BASELINE-IS-ANCESTOR が
                git merge-base --is-ancestor <BASELINE> HEAD の exit 0 を確認する
            いずれも既存 v6.21 guard へは追加しない（GR-5・GR-10）
AC-6.22-27  【Amendment 2追加：m2-4対応】src/wordpress_media について
            containment（changed ⊆ allowed）と coverage（allowed ⊆ changed）が
            別アサーションとして実装され、両者ともPASSする。
            coverage は v6.22 自前guard 側にのみ置き、v6.21 側には置かない
AC-6.22-24  【Amendment 1追加：m-1対応】v6.9 の DEP-1〜DEP-4・ENV-4・ENV-5 guard が
            本Releaseの実装後も PASS する（14.1.1節の禁止部分文字列に
            production code が抵触しない）
```

---

## 19. Deferred Items

| ID | 内容 | 引継ぎ先 |
|---|---|---|
| **DEF-6.22-1** | 一過性の WordPress Upload 失敗（`TIMEOUT`／`CONNECTION`／`RATE_LIMIT`／`SERVER_ERROR`）を `CONTINUE_WITHOUT_FEATURED_MEDIA` へ拡大するか否かの判断 | 将来Release（v6.19 DEF-9／ORD-3 の領域。番号・内容は本設計書では確定しない） |
| **DEF-6.22-2** | reason を構造化ログ／metrics へ記録すること | DI-5 |
| **DEF-6.22-3** | HTTPステータスコードそのものを属性として公開すること（10.3節 D-2 で不採用） | 将来Release（必要性が生じた時点で独立判断） |
| **DEF-6.22-4** | `REQUEST_REJECTED`（その他4xx）のさらなる細分化 | 将来Release（本Releaseでは 400／402／405／409／422 を区別しない） |
| **DEF-6.22-5** | `INVALID_RESPONSE` の細分化（R-3〜R-9 の区別。単発破損 vs スキーマ変更） | 将来Release（DI-11 が OpenAI 側で扱う論点と同型） |
| **DEF-6.22-6** | Media Upload の retry／idempotency／重複Upload防止 | DI-6 |
| **DEF-6.22-7** | orphan media の検出・削除 | DI-7 |
| **DEF-6.22-8** | OpenAI `REQUEST_REJECTED` の細分化 | DI-11 |
| **DEF-6.22-9** | Gate値の strict validation | DI-9 |
| **DEF-6.22-10** | publish 全体の Composition Root 化 | DI-8 |
| **DEF-6.22-11** | **（Amendment 1追加、M-2対応）** `requests.post()` の `allow_redirects=False` 化による IL-1（redirect 追跡に伴う URL 設定誤りの誤観測）の是正。production behavior の変更であるため本Releaseでは対象外（7章 N-16） | 将来Release（behavior 変更を伴うため独立した Architecture Review を要する） |
| **DEF-6.22-12** | **（Amendment 1追加、S-2 不採用の記録）** `requests.TooManyRedirects` 専用の reason（`REDIRECT_LOOP` 等）の新設。IL-3 の理由により本Releaseでは新設しない | 将来Release（IL-1 の是正＝DEF-6.22-11 と併せて検討するのが妥当） |
| **DEF-6.22-13** | **（Amendment 1追加、M-2対応）** IL-2（認証ヘッダ非転送構成で認証失敗が 401 として観測されない）の判別。応答本文の `code` 解析を要するため message 解析禁止（G-3'）に抵触する | 将来Release（解析禁止contractの見直しを伴うため独立検討） |
| **DEF-6.22-14** | **（Amendment 3追加、S3-1 の記録）** zero-diff guard の共有レジストリ化。`_protected_paths` と Release 別 allow-list を `tests/` 配下の共有モジュールへ集約し、各guardがそれを import する構成にすることで、GR-9 の O(N) 保守コスト（保護パスへ触れる Release が既存の全 baseline固定guard を編集する必要）を O(1) へ削減する。**本Releaseでは実装対象としない**（テスト補助モジュールの新設という構造変更を伴い、DI-10 の関心（reason 分類）から外れるため）。GR-9 の「allow-list が肥大化して可読性を損なう場合は Architecture Review へ諮る」条項に基づき、対象guardが増えた時点で再検討する | 将来Release（テスト基盤の構造変更を伴うため独立検討） |
| **DEF-6.22-15** | **（Documentation Integration追加、Implementation Review 2 Suggestion S2R-1 の記録）** `_scan_noparse_violations()` の `str(...)` 検出が、AC-6.22-13 の例示（`str(exc)`）より広く、対象2関数内の**任意の** `str(...)` 呼び出しを禁止する実装になっている。両分類関数には正当な `str()` 呼び出しが存在しないため実害はないが、実装意図（引数名を限定せず汎用的に禁止することで、将来どちらの関数にも一貫して適用できるようにした設計判断）をコメントで明記していない。**本Releaseではtest fileを変更しない**（Implementation Review 2・本Documentation Integrationのいずれでも指示されたスコープ外） | 将来Release（次回 `tests/test_e2e_v6_22_0_*.py` を変更する機会に、コメント追記のみの軽微な対応として実施を検討） |

---

## 20. Risks

| ID | Risk | Severity | Mitigation |
|---|---|---|---|
| **R-1** | `reason` 既定値 `UNKNOWN` により、将来追加された raise 経路が reason 未指定のまま気付かれない | 中 | **（Amendment 1で全面改訂：M-1対応）** 二重検証で閉じる。①既知9経路を `REASON-R1`〜`REASON-R9` で固定（behavioral）。②**（Amendment 3で方式転換：M3-1対応）** `GUARD-WMUE-CONSTRUCTION-SHAPE` により、識別子 `WordPressMediaUploadError` の**出現文脈を allow-list（クラス定義／`raise` 直下の構築 callee の2つのみ）で縛り**、`reason=` keyword 必須・positional 1個・`**kwargs` 禁止を課す（件数非依存。I-6・AC-6.22-23）。<br>本項目は3回の反復を経ている：Amendment 1 は①のみを根拠に「検出可能性は失われない」とした誤り／Amendment 2 は `ast.Raise` 基準・`Name.id` 照合の deny-list 方式で事前構築 raise・Attribute 修飾・別名束縛の3形のみを閉じた（Review 3 の実測で `getattr`／`globals()`／`partial`／factory 等**8形の迂回**が判明）／Amendment 3 で occurrence-context allow-list 方式へ転換し、**迂回形の列挙を不要にした**。Amendment 4 では allow-list へ型位置(c)〜(g)を追加し、Review 4 が指摘した false positive を解消した（AC-6.22-28 で regression 0件を確認）。陽性対照は10形＋負の対照9形（AC-6.22-25） |
| **R-2** | Reviewer が `reason` 必須引数（v6.11 完全対称）を要求する | 中 | 10.2節に採用理由とトレードオフを明記。不採用となった場合の影響（既存4ファイル・10構築箇所の更新、11.5節の baseline 影響の変化）も併記済み。21章 V-1 で明示的な判断対象とする |
| **R-3** | 12値の taxonomy が過剰粒度と判断される | 中 | **（Amendment 1で改訂：M-2対応）** 粒度の根拠を「是正actionへの1対1写像」から「**一次切り分けに使える情報量**」へ差し替えた（8.2節・10.1.1節 L-3）。10.1節の「典型的な是正action」「一過性か」列は non-normative と明示（S-1）。縮退案（404／413／415 を `REQUEST_REJECTED` へ統合し9値化）は 8.2節 A-1 として比較済み。21章 V-2 で判断対象とする |
| **R-4** | 既存E2E **6アサーション**の更新が「Regression の隠蔽」と誤読される | 低〜中 | **（Amendment 1で改訂：B-1対応）** X-1〜X-4 は v6.19 §20 DI-10・§23 AC-24 が明示的に予告済み（1.1節）で、X-3 はアサーション文言自身に予告が書かれている。**X-5・X-6 は予告がない**ため、11.7節で衝突の事実・案C採用理由・検査意図保持の等価性論証を明示し、11.8節で一般則 GR-1〜GR-8 を定めた。案Cは保護を弱めず allow-list を設計書宣言分に厳密一致させるため「隠蔽」ではないことを論証可能。11.2節で1アサーション単位・理由付きで列挙し、in-place 更新の precedent（v6.21 の Guard 精緻化）も提示 |
| **R-5** | `ConnectTimeout` の多重継承により判定順序を誤り `CONNECTION` へ落ちる | 中 | 3.3節で venv 実測を根拠として記録。9.2節で順序を contract 化。`REQEXC-` で `ConnectTimeout` → `TIMEOUT` を専用 Scenario として固定（AC-6.22-6） |
| **R-6** | `_classify_status_code` の非int防御分岐が production では到達不能で、死んだコードになる | 低 | `requests.Response.status_code` は常に `int` であるため production 到達不能であることを 9.2節で明記。Fake response による test からのみ到達する**意図的な防御分岐**として保持する（I-5 の全域性を保証するため） |
| **R-7** | 個別status 判定と範囲判定の順序が逆転し 401 が `REQUEST_REJECTED` へ落ちる | 中 | 9.2節で順序を contract 化。`STATUS-` で 401／403／404／413／415／429 を個別に固定 |
| **R-8** | message 凍結が実装で崩れる（分類のついでに message を整理してしまう） | 中 | G-4'／N-14 で絶対禁止。`MSG-` prefix で9経路すべての message を文字列一致で固定（AC-6.22-9）。9.4節で「分類関数は message を返さない」設計としたことにより、構造的にも message へ触れる必要がない |
| **R-9** | `__all__` 拡張が他の未発見テストを壊す | 低 | **（Amendment 1で改訂：m-3対応）** 3.8.1節の5カテゴリ methodology（C-A〜C-E）により `tests/` 全体を走査し、C-A（`__all__` 固定）が X-1／X-2／X-4 の3件で全数、C-C（signature／型階層固定）が0件であることを確認済み。走査手順を明記したため後続Releaseでも再現可能 |
| **R-10** | **（Amendment 1追加：B-1対応）** 固定 baseline guard の保護対象を変更する Release が今後も発生し、そのたびに同型の衝突が起きる | **中** | 11.8節に一般則 GR-1〜GR-8 を新設（削除禁止・baseline 書換禁止・allow-list 精緻化・件数不変・新Release側の陽性対照・ラベルへの件数埋め込み禁止等）。本Releaseがその第1号適用例となる。GR-7 により X-6 型の「文言更新のためだけの既存ファイル変更」も将来は不要になる |
| **R-11** | **（Amendment 1追加：m-1対応）** 追加する docstring／コメントが v6.9 の全文substring guard（`DEP-2`／`DEP-3`／`DEP-4`／`ENV-5`）に抵触し、原因が「コメントの文言」であるため診断に時間がかかる | 中 | 14.1.1節に禁止部分文字列を全列挙し、衝突リスクの高い `featured_media`／`logging`／`socket` を名指しで注意喚起。新規E2Eの `COMPAT-DEP-` で二重確認（AC-6.22-24） |
| **R-12** | **（Amendment 3で全面改訂：M3-1・V-16後半対応／Amendment 4で追記：m4-2対応）** guard が実装様式を過剰に固定するリスク | **低（Amendment 3・4 で段階的に低減）** | Amendment 2 の `GUARD-NO-PREBUILT-RAISE` は module 全体の `raise` 形式を拘束し、**目的と無関係な `ValueError` の raise 12件まで固定**していた（Review 3 が V-16 後半で指摘）。Amendment 3 の統合guardは「`WordPressMediaUploadError` の構築を `raise` 直下に限る」という形で目的に直結した制約のみを課すため、**当該過剰拘束は撤回された**（`ValueError` 等の raise 形式は自由）。**Amendment 4 では allow-list へ型位置（引数注釈・戻り値注釈・AnnAssign 注釈・except節・isinstance／issubclass 第2引数）を追加し、Review 4 が実測した4種の false positive（型注釈・except節・isinstance・issubclass）を解消した**（残る意図的なスコープ限定は `issubclass` の第1引数のみ。21章 V-16）。残る制約は `WordPressMediaUploadError` の構築形のみであり、現行実装（ClassDef 1件＋`raise` 直下9件、文字列リテラル0件）は余白ゼロで適合する（Amendment 3・4 で実測確認）。将来 allow-list 外の出現形が正当に必要になった場合は、guard を緩めるのではなく **I-6 の構築形 Contract 自体を Architecture Review にかけて見直す** |
| **R-13** | **（Amendment 2追加：m2-1対応／Amendment 3で S3-2 を反映）** `.gitignore` の設定変更が zero-diff 検査の盲点を広げる | 低 | Amendment 2 時点で `__pycache__/` が repository の `.gitignore` に含まれ、`git status --porcelain -uall` が ignored を列挙しないことを実測確認済み（11.7.4節）。**（Amendment 3追加、S3-2）`git diff` は untracked を見ず、`git status --porcelain -uall` は ignored を見ないため、両検査の盲点は実質的に `.gitignore` の集合に等しい。** 現在 ignored なのは `__pycache__/`・`.venv/`・`venv/` の3件のみであり実害はないが、`.gitignore` に広いルールが追加されると盲点が拡大する。`.gitignore` を変更する Release は本guardへの影響を評価する義務を負う（GR-8 と同趣旨） |
| **R-14** | **（Amendment 4追加：m4-1対応）** 手順4（文字列間接参照の封鎖）が、意図的に分割されたリテラル（`"WordPressMediaUpload" + "Error"`・f-string 部分結合等）を検出できない | 低（受容） | 分割リテラルは各 `ast.Constant` が識別子全体を含まないため静的に追跡不能である。17.1節へ「本guardの脅威モデルは**偶発的な reason 渡し忘れ**の防止であり、**意図的な難読化の防止ではない**」と明記し、検出不能を受容することを明示した。type comment（`# type: ...`）はプレーンな `ast.parse()` では AST に現れず実行時に無害であるため、同様に対象外として受容する |

---

## 21. Architecture Review で重点確認すべき点

| ID | 確認事項 |
|---|---|
| **V-1** | **（Amendment 1で改訂）`reason` を既定値付き（`UNKNOWN`）とする判断（10.2節 D-1）は妥当か。** v6.11 の必須引数方式との非対称を受け入れるか、既存4テストファイル・10構築箇所の更新コストを払って必須引数へ揃えるか。とくに **`GUARD-WMUE-CONSTRUCTION-SHAPE`（occurrence-context allow-list 方式の構築形検査）＋ `REASON-R1`〜`R9`（behavioral）の二重検証が、必須引数方式と同等の「分類漏れの構造的検出」を与えているか**（D-1c・I-6・AC-6.22-23。Amendment 3 で単一 guard・単一 Contract へ整理済み） |
| **V-2** | **（Amendment 1で改訂）12値の taxonomy（10.1節）は適切な粒度か。** 特に `ROUTE_NOT_FOUND`（404）・`PAYLOAD_TOO_LARGE`（413）・`UNSUPPORTED_MEDIA_TYPE`（415）を独立値とする判断。粒度の根拠を「是正actionへの1対1写像」から「一次切り分けに使える情報量」へ差し替えた（8.2節・10.1.1節 L-3）ことで、正当化は十分か。`NOT_FOUND` → `ROUTE_NOT_FOUND` の改名（m-4）は適切か。逆に `REQUEST_REJECTED`（その他4xx）を細分化しない判断（DEF-6.22-4）・`TooManyRedirects` 専用値を設けない判断（IL-3／DEF-6.22-12）は妥当か |
| **V-3** | **`__all__` へ Enum を公開する判断（10.4節 D-3）は妥当か。** 公開により X-1／X-2／X-4 の3アサーションが更新対象になることと、公開しない場合に下流が内部moduleへ直接依存せざるを得なくなることのトレードオフ |
| **V-4** | **message 凍結（C-4・G-4'）が設計として担保されているか。** 分類関数が reason のみを返す設計（9.4節）で十分か。`_build_non_2xx_message()` を無変更に保つ根拠は十分か |
| **V-5** | **`_classify_status_code` が response object ではなく `int` を受け取る設計（SEC-3）**が、body/header への到達不能性を「構造として」保証できているか |
| **V-6** | **判定順序の contract（9.2節）**が明示的かつ検証可能か。`Timeout` → `ConnectionError` の順序（R-5）と、個別status → 範囲判定の順序（R-7）の両方 |
| **V-7** | **11.4節の「v6.19 policy の出力が12値すべてで不変」という主張が正しいか。** `decide_image_generation_fallback()` の `WordPressMediaUploadError` 分岐が `reason` を読まないという Repository 上の事実（3.5節 L152-153）に依拠しているが、他に reason を読み得る経路が存在しないか |
| **V-8** | **（Amendment 1で改訂）11.2節の既存E2E更新対象6件（4ファイル）が全数であるか。** 3.8.1節の5カテゴリ methodology（C-A〜C-E）に**さらなる抜けがないか**。とくに C-D（パス指定 zero-diff guard）の走査で、正式 Inventory 24ファイルのうち `v5_9_0`〜`v6_4_0` の6ファイルが Retry 系パスのみを対象とし本Releaseの影響を受けないという判定は正しいか |
| **V-9** | **（Amendment 1で改訂）11.5節の Formal Regression baseline 影響の再計算が正しいか。** X-5 の精緻化が「22パス × 3アサーション = 66件」の構成を変えないため総数が **3389 のまま不変**であるという主張が成立するか。案A（保護対象削除。3389 → 3386）を採らなかった判断は妥当か（11.7.2節）。新contract の検証をすべて新規ファイル側へ置く方針は妥当か |
| **V-10** | **（Amendment 1で改訂）Runtime Zero Diff（11.6節・11.7節）の範囲と検証方法**が v6.21.0 の恒久guard方式と整合しているか。**案C（allow-list 方式）が v6.21 guard の検査意図を保持しているという 11.7.1節の等価性論証（`allowed == ∅` のとき `changed - ∅ == ∅ ⟺ changed == ∅`）は正しいか。** `--relative` によるパス正規化の contract は十分に厳密か。`NOIMPACT-SCOPE[...]` へのラベル改名は許容できるか。`main.py` の Architecture Guard（v6.13 `RUNTIME-1` / v6.20 `RUNTIME-1a`）が精緻化不要であるという判断は正しいか |
| **V-11** | **Scope 境界（7章）**が守られているか。特に N-1（CONTINUE拡大なし）が設計上「うっかり」越えられない構造になっているか |
| **V-12** | **Consumer-less であること（16章）**が本Releaseの価値を損なわないか。分類（本Release）と判断（将来Release）の分離が、v6.11 → v6.19 の precedent と整合しているか |
| **V-13** | **taxonomy に将来値が追加された場合の下流の安全性。** v6.19 policy は `WordPressMediaUploadError` を型のみで判定するため、値追加は自動的に安全側（`MEDIA_UPLOAD_FAILED`）へ落ちる。この性質が本設計で明示されているか |
| **V-14** | **（Amendment 1追加）11.8節の一般則 GR-1〜GR-8 は、本Release固有の都合ではなく後続Release（DI-5／DI-11／DI-6／DI-7 等）へ一般化できる規則になっているか。** とくに GR-4（allow-list に載せられるのは設計書 File Change Plan が宣言したファイルのみ）が、実装工程での allow-list 拡大を実効的に防げるか。GR-5（件数不変）と GR-7（ラベルへ件数を埋め込まない）が両立しているか |
| **V-15** | **（Amendment 1追加）10.1.1節の reason 定義（観測された構造の分類）と 10.1.2節の Inherited Limitations（IL-1〜IL-4）は、taxonomy の価値を損なわずに限界を正確に述べているか。** IL-1（redirect 追跡による誤観測）の実測根拠は十分か。S-2 不採用（IL-3）の理由は妥当か。`allow_redirects=False` を本Release対象外（N-16・DEF-6.22-11）とする判断は正しいか |
| **V-16** | **（Amendment 3で方式転換、Amendment 4でallow-list精緻化：M3-1・B4-1・m4-2対応）17.1節の `GUARD-WMUE-CONSTRUCTION-SHAPE`（occurrence-context allow-list 方式）は、方式として妥当か。** ①「識別子の出現文脈を allow-list で縛る」ことにより、迂回形を個別列挙せずに閉じられているか（Review 3 が実測した9形＋Amendment 2 が閉じた3形をすべて含むか。Amendment 4 で型位置(c)〜(g)追加後も全18攻撃形が引き続き検出されることを実測済み。AC-6.22-28）。②allow-list の**7形**（クラス定義／`raise` 直下の構築 callee／引数注釈／戻り値注釈／`AnnAssign` 注釈／`except`節／`isinstance`・`issubclass`第2引数）は**必要十分**か。過小（正当な記述を拒む）でも過大（迂回を許す）でもないか。**とくに `issubclass` の第1引数（`issubclass(WordPressMediaUploadError, Exception)` のように WMUE 自身の親子関係を検査する形）を意図的に allow-list 外へ残した判断（Amendment 4）は妥当か**（安全側＝より制約が強い側への意図的なスコープ限定であり、現行実装には該当形が存在しない）。③手順3の識別子走査対象に**なお取りこぼしがないか**（例：`__qualname__` 参照、f-string 内の識別子、ネストしたクラス／関数内の別位置）。④手順4の文字列検査を `__init__.py` へ適用しない判断、および **docstring を除外する判断**（Amendment 4・B4-1）は十分か。docstring 除外の範囲（module／ClassDef／FunctionDef／AsyncFunctionDef の body 先頭のみ）は過不足ないか。⑤旧3 guard の廃止・型位置追加により**検出力が落ちた形がないか**（regression の再確認）。⑥陽性対照10形＋負の対照9形は各失敗モード・各正当な記述を本当に検出／通過させるか（とくに「正規サイト併存」という設計要件が守られているか）。⑦分割リテラル・type comment を検出不能として受容する判断（20章 R-14）は妥当か |
| **V-17** | **（Amendment 2追加：m2-1・m2-4・S2-3対応）** 11.7.4節の (a) equality の containment／coverage 分解と後続Release安定性の論証、(b) `NOIMPACT-NO-UNTRACKED` を v6.22 側にのみ置く判断（GR-5・GR-10 との整合）、(c) coverage が baseline 誤指定に対する陽性対照として機能するという論証、(d) `__init__.py` の変更が D-3 に依存するという記録は、いずれも正しいか |
| **V-18** | **（Amendment 2追加：m2-5対応）** GR-9 の ratchet 構造（古いguardは緩むが最新guardが権威的保証を担う）は、Runtime Zero Diff の保証水準を実質的に維持できているか。GR-10（保護パス追加は新guard側）と GR-5（精緻化時のみ件数不変）の適用範囲の切り分けは一義的か |

---

## 22. 用語・参照

| 参照先 | 内容 |
|---|---|
| `docs/ROADMAP.md` L1085-1089 | DI-10 の正式定義 |
| `docs/design/image_generation_fallback_policy_foundation.md` L2394（20章）・L2651-2661（23章 AC-24 注記）・§10.4・§10.8（ORD-1〜ORD-4）・§13.2 | DI-10 の正式化・既知差分の予告・message解析禁止 |
| `docs/design/article_featured_media_runtime_wiring.md` §1.1・§1.2 E-3・§7.4・§14.4・§18・§19 | ORD-2 受容判断・分類不能の構造的根拠・PROPAGATE の帰結・恒久guard方式・Deferred 一覧 |
| `docs/design/wordpress_media_upload_foundation.md` | v6.9.0（本Releaseの変更対象package）の原設計 |
| `docs/design/openai_image_generation_adapter_foundation.md` | v6.11.0（reason分類の precedent）の原設計 |
| `docs/architecture.md` §WordPress Media Upload Foundation層・§Image Generation Fallback Policy Foundation層・§Article Featured Media Runtime Wiring層 | 既存層の記録 |
| `src/wordpress_media/wordpress_media_uploader.py` L24-26・L63-89・L137-210 | 変更対象 |
| `src/openai_image_generation/openai_image_generator.py` L56-79・L97-148 | precedent |
| `src/image_generation_fallback_policy/image_generation_fallback_policy.py` L136-157 | 下流 policy（無改修） |
| `tests/test_e2e_v6_21_0_article_featured_media_runtime_wiring.py` L814-922 | **（Amendment 1追加）** 本Releaseが精緻化する NOIMPACT guard の現行実装（L824 baseline commit・L845-868 `_protected_paths`・L893 `NOIMPACT-UNCHANGED`・L897-921 `NOIMPACT-TESTS-SCOPE`） |
| `tests/test_e2e_v6_9_0_wordpress_media_upload_foundation.py` L362-366・L371-380・L900-968 | **（Amendment 1追加）** `_combined_source` の構成、`ENV-4`／`ENV-5`、`DEP-1`〜`DEP-4`（14.1.1節の実装制約の出典） |
| `requests` 2.34.2（project venv）`requests.sessions.SessionRedirectMixin.rebuild_method` / `rebuild_auth` | **（Amendment 1追加）** IL-1 の実測根拠（301／302 における POST → GET 書き換え） |
