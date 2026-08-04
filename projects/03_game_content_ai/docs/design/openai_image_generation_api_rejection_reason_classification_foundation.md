# OpenAI Image Generation API Rejection Reason Classification Foundation

**Release: v6.23.0（DI-11 前半）**

Deferred Item: **DI-11 OpenAI Image Generation Request Rejection Reason Refinement**（前半＝
`REQUEST_REJECTED` の SDK 例外型による細分化）

---

## 0. Status

| 項目 | 値 |
|---|---|
| 工程 | **Documentation Integration／Finalize 完了（commit／push 未実施）** |
| Architecture Review Verdict | **Approved with Findings**（Blocking 0・Major 0・Minor 4・Suggestion 2。0.4節） |
| Test Review Verdict（初回） | **Approved with Suggestions**（Blocking 0・Major 2・Minor 4・Suggestion 2） |
| Test Review Verdict（再判定） | **Changes Required**（未解消 Major 1：NOPARSE guard が deny-list 方式であり「例外型のみで分類」を完全保証できない）→ **positive allow-list 方式**への転換で解消（7.8節・12.6節） |
| Production Implementation | **Completed**（Production 2ファイル・新規E2E 1ファイル・既存E2E 4ファイル更新） |
| 限定テスト | **Completed**（1313/1313 PASS・FAIL 0・SKIP 0） |
| **Formal Regression** | **Completed（正式Inventory 26ファイル：既存25ファイル 3721/3721 PASS ＋ 新規v6.23.0 332/332 PASS ＝ 総合 4053/4053 PASS。FAIL 0・SKIP 0・全ファイル終了コード0・既知差分は v6.19 の +8 のみ・外部API実接続0件）** |
| **Release Review Verdict** | **Approved with Suggestions**（Blocking 0・Major 0・Minor 1・Suggestion 2。0.6節） |
| 次工程 | **人間による最終確認と commit／push の指示**（本工程では commit／push を行っていない） |
| Source of Truth | 本ファイル |

### 0.1 Repository 開始状態（読み取り専用コマンドで実測）

```text
branch          : main
local HEAD      : 8fd845348d1ee4c80db8de2942da5f99c2bcf0fd
origin/main     : 8fd845348d1ee4c80db8de2942da5f99c2bcf0fd
ahead / behind  : 0 / 0
Working Tree    : clean（git status --porcelain 出力なし）
直前Release     : 6.22.0（WordPress Media Upload Failure Reason Classification Foundation）
Formal Regression baseline : 正式Inventory 25ファイル / 3713 assertions PASS
```

`git fetch` / `git pull` は実行していない。上記はすべてローカル参照のみによる実測値である。

### 0.2 これまでの工程で変更したファイル

| 工程 | ファイル | 変更 |
|---|---|---|
| Architecture Review・設計 | `docs/design/openai_image_generation_api_rejection_reason_classification_foundation.md` | 新規作成（本ファイル） |
| Test Review | （なし） | Review のみ。ファイル変更0件 |
| Test Review Findings 反映 | 同上 | 本ファイルのみ改訂 |
| **Production Implementation ＋ 限定テスト** | `src/openai_image_generation/openai_image_generator.py`<br>`src/image_generation_fallback_policy/image_generation_fallback_policy.py`<br>`tests/test_e2e_v6_23_0_*.py`（新規）<br>`tests/test_e2e_v6_11_0_*.py`／`v6_19_0`／`v6_21_0`／`v6_22_0`（更新） | Production 2・E2E 5（新規1＋更新4） |
| Formal Regression | （なし） | 実行のみ。ファイル変更0件 |
| Release Review | （なし） | Review のみ。ファイル変更0件 |
| **Documentation Integration／Finalize（本工程）** | 本ファイル・`docs/ROADMAP.md`・`docs/CHANGELOG.md`・`docs/architecture.md` | **文書4点のみ。Production code・E2E は一切変更しない** |

**上記1ファイル以外は一切変更していない。** Production Code・既存 tests・`ROADMAP.md`・
`CHANGELOG.md`・`architecture.md`・`main.py`・`requirements.txt`・`.env.example` は
いずれも無変更である。実装・正式テスト・commit・push はいずれも実施していない。

### 0.3 Release 番号の扱い

本設計書は **v6.23.0** を提案するが、Release 番号の確定は Release 工程で行う。
本設計書内の「v6.23」表記はすべて提案値である。

### 0.4 Architecture Review の実施記録

本 Review は Repository 上の以下を根拠として実施した。

```text
設計文書  : image_generation_fallback_policy_foundation.md（DI-11 の正式定義・ORD-1〜ORD-4）
            openai_image_generation_adapter_foundation.md（v6.11 原設計）
            wordpress_media_upload_failure_reason_classification_foundation.md
              （v6.22。GR-1〜GR-11・reason 分類の precedent）
            article_featured_media_runtime_wiring.md（v6.21。恒久guard方式）
Production: src/openai_image_generation/openai_image_generator.py（312行 全読）
            src/openai_image_generation/__init__.py
            src/image_generation_fallback_policy/image_generation_fallback_policy.py（157行 全読）
            src/article_featured_media_runtime/article_featured_media_runtime.py（134行 全読）
            main.py L182-237・L266-280・L400-460
E2E       : v6.11 / v6.18 / v6.19 / v6.20 / v6.21 / v6.22（reason 参照箇所の全数走査）
実測      : .\venv\Scripts\python.exe による openai 2.46.0 の例外階層調査（外部通信0件）
```

Review で提起し、本設計書で解消した Finding は次のとおり。

| ID | 区分 | 内容 | 解消 |
|---|---|---|---|
| **F-1** | Minor | 当初案（v6.11 単独変更）では、新 reason が v6.19 policy で `UNCLASSIFIED` へ落ち、`category` が `IMAGE_GENERATION_REQUEST_REJECTED` から変化する | 7.5節：policy へ `_REJECTED_REASONS` allow-list を導入し全数写像を明示。**policy の変更は Zero Diff を壊す変更ではなく、Zero Diff を維持するための変更**であることを 9.5節で論証 |
| **F-2** | Minor | v6.19 E2E は `list(OpenAIImageGenerationErrorReason)` 駆動のループを2箇所持つため、Enum 値追加でアサーション件数が自動的に増える。GR-5（件数不変）の慣行と衝突して見える | 13章：GR-5 は**既存 guard の精緻化**にのみ適用される制約であり、期待表駆動ループの自然増は対象外であることを明記。増分 **+8** を事前に確定し既知差分として宣言 |
| **F-3** | Minor | v6.22 の `NOIMPACT-TESTS-SCOPE` ラベルに件数「5件」が埋め込まれており、GR-7（ラベルへ件数を埋め込まない）に自ら反している | 11.4節：本Releaseの allow-list 更新に合わせ、ラベルから件数表現を除去する（GR-5 が認める「ラベル文言の差し替え」の範囲内・件数不変） |
| **F-4** | Minor | 4型すべてで message を凍結すると、`RESOURCE_NOT_FOUND`（model 不存在）に対して「Content Policy 等による生成拒否を含む」という文言が残り、意味的に不正確になる | 7.6節：**message 凍結を優先**（論点8）。不正確さを IL-1 として明示し、message 改訂は DEF-6.23-1 として独立Releaseへ |
| **F-5** | Suggestion | v6.22 の `GUARD-WMUE-CONSTRUCTION-SHAPE` 相当の構築形 guard を本Releaseにも設けるべきか | 12.4節：**不要**と判断。v6.11 の `reason` は既定値なしの必須引数であり、渡し忘れは `TypeError` で構造的に不可能。したがって M5-1（match-case class pattern の allow-list 扱い）も判断機会が発生しない（16章 DEF-6.23-5、論点12） |
| **F-6** | Suggestion | `RESOURCE_NOT_FOUND` は v6.22 の `ROUTE_NOT_FOUND`（404）と非対称である | 7.2節：**意図的な非対称**として受容し理由を記載。両者は別 Enum 型であり衝突しない |

### 0.5 Test Review Findings の反映（本工程）

Test Review の再判定は **Changes Required** であり、未解消 Major が1件残った。
本工程はこれを解消し、あわせて初回 Test Review の全 Finding を反映する。

#### 0.5.1 再判定 Major（NOPARSE guard の方式転換）

```text
指摘: NOPARSE guard が「禁止属性を列挙する deny-list 方式」であるため、
      openai SDK が将来追加する未知の属性（exc.<new_attr>）を検出できず、
      「例外型のみで分類する」（G-8）を完全には保証できない。
      禁止形を列挙し続ける限り、列挙漏れは構造的に避けられない。

解消: 例外引数の使用形そのものを positive allow-list で縛る方式へ転換した。
      許可されるのは isinstance(<exc>, ...) の第1引数という唯一の形のみで、
      それ以外のあらゆる出現文脈を違反とする（7.8節）。
      属性名を列挙しないため、未知属性は自動的に禁止側へ落ちる。
      これは v6.22 が GUARD-WMUE-CONSTRUCTION-SHAPE で
      「識別子の出現文脈を allow-list で縛る」方式へ転換した precedent と同型である
      （v6.22 Architecture Amendment 3 の M3-1 対応）。
```

**旧契約の破棄**：`_FORBIDDEN_ATTRS`（禁止属性集合）、および「禁止9形」という
形の数に基づく記述は、本改訂で**すべて破棄する**。設計書内に残してはならない。

#### 0.5.2 初回 Test Review Findings の反映

| ID | 区分 | 指摘 | 反映 |
|---|---|---|---|
| **M-1** | Major | catch-all 経路（3系統）と「HTTPステータス値では分類しない」陰性対照がテスト契約に無い | 12.5節：`CLS-` を10 → **14ケース**へ拡張。`APIStatusError`（status 400／500）・bare `APIError`・`APIResponseValidationError` を追加。とくに**status 400 を持つが `BadRequestError` ではない**ケースが「型のみ判定」の behavioral 証明になる |
| **M-2** | Major | `_FORBIDDEN_ATTRS` が4語しかなく `message`／`response`／`body`／`status_code` を検出できない | **0.5.1 の方式転換により論点ごと解消**（属性名を列挙しない設計へ移行したため） |
| **m-1** | Minor | baseline 数値の位置づけ（実測／引用／見込み）が未区別 | 13.3節：4区分を定義し、全数値へ区分を付与 |
| **m-2** | Minor | v6.19 の件数埋め込み Scenario ID の改名方針が未定 | 13.2.1節：**ID 据え置き・ラベル本文のみ更新**を方針として確定し、根拠を記載 |
| **m-3** | Minor | private 関数・定数の import パス契約が未定義 | 12.7節：import 契約を明文化 |
| **m-4** | Minor | 「policy のみ更新」の検出を独立 assertion にすると vacuous になる | 12.9節：検出手段が **import 失敗＝ファイル全体 FAIL** であることを明記し、vacuous な assertion を設けないことを contract 化 |
| **s-1** | Suggestion | v6.11 E2E の Scenario ID は据え置き、該当行へコメント注記 | 10.2節・13.2節へ反映 |
| **s-2** | Suggestion | 反復回数と assertion 数を区別して記載 | 12.8節：数え方 R-a〜R-e を規約として明記し、全ブロックで反復数と assertion 数を分離して記載 |

#### 0.5.3 本改訂で変更していない確定事項

Architecture Review で承認済みの次の事項は、本改訂で**一切変更していない**。

```text
・reason taxonomy（13値・name・value・定義順）           → 7.1節
・SDK例外型 → reason の対応表                           → 7.1節・7.3節
・REQUEST_REJECTED を削除しない後方互換設計              → 7.4節
・_REJECTED_REASONS による fallback policy 全数写像      → 7.5節
・CONTINUE 対象4値の非拡大                              → 7.5.1節・9.3節
・Zero Diff の定義（Z-1〜Z-8）と Production Behavior
  Zero Diff を主張しない方針                            → 9.1節・9.5節
・message 凍結（IL-1 の受容）                           → 7.6節
・guard 更新方針（GR-1〜GR-11・2 guard 更新・自前guard） → 11章
・File Change Plan（Production 2ファイル）              → 10章
```

#### 0.5.4 本改訂による見込み値の変化

| 項目 | 改訂前 | **改訂後** | 変化の理由 |
|---|---|---|---|
| `NOPARSE-` ブロック | 12 | **26** | 方式転換（陽性対照 9 → **16**、陰性対照 0 → **4**、vacuous 防止 3本を新設） |
| 他19ブロック合計 | 306 | **306** | 変化なし（M-1 による `CLS-` 10 → 14ケースは初回 Test Review 時点で反映済み） |
| 新規 E2E assertion 総数 `N` | 318（**旧見込み値**） | **332** | 306 ＋ 26 |
| Formal Regression 総数 | 4039（旧見込み値） | **4053** | 3721 ＋ 332 |

既存25ファイルの新 baseline **3721** は本改訂で**変化しない**（v6.19 の +8 は
Enum 値追加に対する構造的増分であり、guard 方式の転換に影響されないため）。

### 0.6 Production Implementation〜Formal Regression の実績（Finalize で追記）

#### 0.6.1 Production Implementation

設計書10章の File Change Plan どおりに実装した。

```text
src/openai_image_generation/openai_image_generator.py   （+48 / -4）
  ・Enum 末尾へ4値追加（既存9値の name・value・定義順は不変）
  ・_classify_api_error() の単一タプル isinstance を4つの独立 isinstance へ展開
    （判定位置は現行のまま：APIConnectionError と InternalServerError の間）
  ・message は4型とも v6.22.0 時点と完全同一の文字列を維持
  ・docstring へ I-EXC-1 契約と判定順序 contract を追記

src/image_generation_fallback_policy/image_generation_fallback_policy.py （+27 / -2）
  ・_REJECTED_REASONS（frozenset・5値）を新設
  ・elif 条件を単一値の is 照合から集合照合へ変更（isinstance 防御は踏襲）
  ・_CONTINUABLE_REASONS・_ACTION_BY_CATEGORY・分岐順序は無変更
```

`__init__.py`・`main.py`・`requirements.txt`・`.env.example`・その他 Production package は
**いずれも無変更**（`NOIMPACT-SCOPE-EXACT` の equality 検査により機械的に保証）。

#### 0.6.2 限定テスト

| ファイル | assertion | 結果 |
|---|---|---|
| v6.23.0（新規） | **332** | 332/332 PASS |
| v6.11.0 | 248 | 248/248 PASS（件数不変） |
| v6.19.0 | **262** | 262/262 PASS（254 → 262、**+8**） |
| v6.21.0 | 147 | 147/147 PASS（件数不変） |
| v6.22.0 | 324 | 324/324 PASS（件数不変） |
| **合計** | **1313** | **1313/1313 PASS・FAIL 0・SKIP 0** |

#### 0.6.3 Formal Regression

**正式 Inventory 26ファイル**（`test_e2e_v1_11_0_save_result.py`・`test_e2e_v5_9_0_*.py`・
`test_e2e_v6_0_0_*.py`〜`test_e2e_v6_23_0_*.py`）を個別実行した。

```text
既存25ファイル : 3721 / 3721 PASS
新規 v6.23.0   :  332 /  332 PASS
─────────────────────────────
総合 26ファイル: 4053 / 4053 PASS

FAIL 0 ・ SKIP 0 ・ 全ファイル終了コード 0
既知差分：v6.19 の +8（254 → 262）のみ
外部API実接続 0件 ・ credential 使用 0件 ・ Git 状態不変
```

12.8.2節が宣言した **20ブロックすべての assertion 数が実測と一致**した
（`API-` 23／`COMPAT-REJECTED-` 7／`CLS-` 28／`ORDER-` 11／`E2E-` 16／`MSG-` 2／
`CHAIN-` 8／`POLICY-` 30／`REJECTSET-` 6／`CONT-` 9／`ZERODIFF-` 27／`RUNTIME-` 8／
`NOPARSE-` 26／`SEC-` 10／`DEP-` 3／`NOEXC-` 3／`COMPAT-` 13／`NOIMPACT-` 97／
`SOCKET-` 3／`ENV-` 2）。

### 0.7 Release Review の結果（Finalize で追記）

**Verdict: Approved with Suggestions（Blocking 0・Major 0・Minor 1・Suggestion 2）**

Release Review は報告に依存せず、Production diff 全文精査・AST 等価性検証・
NOPARSE guard への独自攻撃28形試験・Production code 直接呼び出しによる
振る舞い検証・Formal Regression 出力の再解析により独立実施された。

#### 0.7.1 独立検証で確認された事実

| 検証 | 結果 |
|---|---|
| NOPARSE guard の網羅性 | 設計書12.6.2節の16形に加え、**Reviewer 独自の追加28攻撃形をすべて検出**（別名束縛 `_is = isinstance; _is(exc, X)`・ネスト関数クロージャ・`lambda`・引数再束縛・`exc.args[0]`・`type(exc)`・`%` 演算子等を含む）。正当形5形はすべて通過（偽陽性0） |
| 本番実装への適用 | `exc` の Name 出現 **10件・全件 allow 形・違反0件**（AC-31・AC-31b を満たす） |
| catch-all | **`status_code = 400` を持つ素の `APIStatusError` が `UNKNOWN` へ分類される**ことを実測（型のみ判定の behavioral 証明） |
| 写像 | rejected 5値すべてが `IMAGE_GENERATION_REQUEST_REJECTED` ＋ `PROPAGATE_ORIGINAL_ERROR`。分割は **4/5/2/2** |
| CONTINUE 非拡大 | `_CONTINUABLE_REASONS` は diff 上無変更。実測 CONTINUE は正確に既存4値 |
| guard の GR 適合 | 3 guard の `_protected_paths` が **22件・同一集合・同一順序**（GR-1）。`BASELINE_COMMIT` は diff に一切現れず（GR-2）。check 系呼び出し数が HEAD と一致（GR-5） |
| S2R-1 | `_scan_noparse_violations` の **AST が HEAD と完全一致**。`_FORBIDDEN_ATTRS` も一致。検査ロジックは1ビットも不変 |
| secret / 通信 | 4型すべてで marker 非露出・`response`／`body`／`status_code` 非保持。`[NG]` マーカー0件 |

#### 0.7.2 Minor（1件）

| ID | 内容 |
|---|---|
| **RR-M-1** | **v6.23 E2E の NOIMPACT 陽性対照2件（`NOIMPACT-POSITIVE-EMPTY-ALLOWLIST` / `NOIMPACT-POSITIVE-UNCHANGED-ALLOWLIST`）が、実 guard 値ではなくハードコードされたリテラル集合のみで集合演算しており、無条件で PASS する恒真式になっている。**静的走査により、定数のみに依存する assertion は108件中この2件だけと確定した。<br>**ただし guard 本体は健全である**：`NOIMPACT-SCOPE-COVERAGE`／`NOIMPACT-SCOPE-EXACT`（各2件）が実 `git diff` 出力に対し coverage・equality を課しており、これが真の vacuous-pass 防御として機能している（コード実査で確認）。<br>**Production behavior・安全性・Runtime Action Zero Diff への影響は一切ない。** 設計書12.3節が「合成集合演算で確認する」と規定しており実装は字義に適合しているため、Major へは上げない。<br>**本Releaseでは修正せず DEF-6.23-12 として Deferred 化する。** |

#### 0.7.3 Suggestion（2件・いずれも記録のみ／修正不要）

| ID | 内容 |
|---|---|
| **RR-S-1** | `DEP-POLICY-NO-NEW-IMPORT`（import root が5件）は、直前の `DEP-POLICY-MODULE`（集合の厳密一致）から論理的に導かれるため冗長。ただし失敗時の診断粒度を上げる効果があり、害はない |
| **RR-S-2** | `SEC-VALUE-LABEL-SET` は「固定ラベル集合との一致」ではなく「英小文字＋アンダースコアのみ」という性質検査である。ただし `API-VALUES-EXACT` が13値の厳密一致を別途固定しているため **AC-33 の要件は充足**している |

#### 0.7.4 Release 承認条件（Release Review が付した条件）

```text
1. Blocking／Major 0件のため、追加の実装・テスト修正は不要
2. Finalize 工程で Production code・E2E を変更しないこと
   （変更した場合は Formal Regression のやり直しが必要）
3. RR-M-1 を Deferred として設計書へ記録すること（修正は不要）→ DEF-6.23-12 として記録済み
4. commit 直前に HEAD == 8fd8453 を再確認すること
   （v6.23 guard の baseline が現 HEAD に固定されているため）
5. CHANGELOG・ROADMAP・Release Review の記述で 9.5節の表現規定を遵守すること
```

上記のうち 1〜3・5 は本 Finalize 工程で充足済み。**4 は commit 実施者が直前に確認する。**

---

## 1. 背景・目的

### 1.1 DI-11 の Repository 上の正式定義

`docs/design/image_generation_fallback_policy_foundation.md` §20（Deferred Items）は
DI-11 を次のとおり定義している（要約ではなく趣旨の引用）。

```text
v6.11 _classify_api_error() が単一の REQUEST_REJECTED へ集約している4つの
Provider例外型（BadRequestError／NotFoundError／ConflictError／
UnprocessableEntityError）を、OpenAIImageGenerationErrorReason の追加値へ
細分化する。特に「記事固有の失敗（Content Policy拒否、HTTP 400）と、
全記事へ反復するsystemic failure（model不存在・model提供終了、HTTP 404）の分離」
を目的とする。分類は引き続き例外の型のみに基づき、message解析・
response body読み取りを行わない。v6.11のPublic API変更（Enum値追加）を
伴うため独立Releaseを要する。
```

同§20 は DI-11 の検討対象に「`UNKNOWN` の2経路分離」「`INVALID_RESPONSE` の
単発破損とスキーマ変更の分離」も含めるとしている。**本Releaseはこれらを扱わず、
`REQUEST_REJECTED` の細分化のみを扱う**（5章 N-3・N-4）。この分割を
「DI-11 前半／後半」と呼ぶ。

### 1.2 なぜ今なのか

1. **v6.22（DI-10）で対になる作業が完了した。** WordPress 側の失敗分類
   （`WordPressMediaUploadErrorReason` 12値）が確立し、OpenAI 側だけが
   粗い分類のまま残っている。手法・guard 方式・GR-1〜GR-11 の一般則がすべて
   直前Releaseで確立しており、そのまま再利用できる。
2. **v6.22 設計書 §19 DEF-6.22-8 が引継ぎ先を DI-11 と明記している。**
3. **ROADMAP が DI-11 を「次候補・未着手」として単独項目で保持している。**
4. **前提となる未完了 DI が存在しない。** 逆に DI-5（observability）や
   DEF-6.22-1（CONTINUE 拡大）は、分類が確定していない状態で着手すると
   ラベル集合が後から変わるため、本Releaseが先行するのが自然である。

### 1.3 目的

**本Releaseの目的は「分類手段を用意すること」に限定される。**
分類結果を使って判断（CONTINUE／PROPAGATE）を変えることは目的ではない。
v6.11（分類）→ v6.19（判断）という既存の責任境界をそのまま踏襲する。

---

## 2. Problem Statement

### 2.1 現状の欠落

`_classify_api_error()` は、意味の異なる4つの失敗を単一の `REQUEST_REJECTED` へ
集約している。

| SDK 例外型 | HTTP | 実際の意味 | 反復性 |
|---|---|---|---|
| `BadRequestError` | 400 | パラメータ不正、**Content Policy 拒否** | 記事固有のことが多い |
| `NotFoundError` | 404 | **model 不存在・model 提供終了**、endpoint 不在 | **全記事へ反復する systemic failure** |
| `ConflictError` | 409 | リソース競合 | 一過性のことが多い |
| `UnprocessableEntityError` | 422 | 意味的に処理不能な要求 | 記事固有のことが多い |

### 2.2 集約が引き起こしている具体的損害

`image_generation_fallback_policy_foundation.md` §22 R-4（Severity **中**）が
記録しているとおり、v6.19 は「安全に分類できない失敗を fallback へ倒さない」
（G-9）原則により、**4型すべてを `PROPAGATE_ORIGINAL_ERROR` に倒している**。
その結果、本来は記事1件を飛ばせば済む Content Policy 拒否でも、
`main.py` は当該記事を投稿せず `result="failed"` として記録する。

分類が粗いために、この可用性低下を**将来にわたって改善できない**状態が固定されている。

### 2.3 本Releaseが解決しないこと

**可用性低下そのものは解決しない。** 本Releaseの後も4型はすべて
`PROPAGATE_ORIGINAL_ERROR` のままである（6章 G-5・9.3節）。
解決するのは「区別できない」という構造的制約のみである。
判断の変更は将来Release（DEF-6.23-2）の領域とする。

---

## 3. 現行契約（Repository Survey Findings）

### 3.1 v6.11 の現行 reason 契約

`src/openai_image_generation/openai_image_generator.py` L56-79 より。

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
    UNKNOWN = "unknown"


class OpenAIImageGenerationError(RuntimeError):
    def __init__(self, message: str, reason: OpenAIImageGenerationErrorReason) -> None:
        super().__init__(message)
        self.reason = reason
```

確定事実：

| ID | 事実 | 出典 |
|---|---|---|
| **C-1** | reason は **9値**。value はすべて lower snake_case の固定ラベル | L56-66 |
| **C-2** | `reason` は**既定値を持たない必須引数**（v6.22 の `WordPressMediaUploadError` とは非対称。v6.22 が既定値 `UNKNOWN` を採ったのは既存テストとの後方互換のため） | L76-78 |
| **C-3** | `OpenAIImageGenerationError` の構築箇所は production 全体で **2箇所**（L185・L310）。いずれも `raise ... from None` の直下 | L185・L310 |
| **C-4** | `_classify_api_error()` は **raise せず** `(message, reason)` タプルを返す純粋関数。分類は `isinstance` のみに基づく | L94-146 |
| **C-5** | `generate()` は `except` ブロックの**外**で raise する（classify-then-raise-outside-except）。このため `__cause__` / `__context__` はいずれも到達不能になる | L301-310 |
| **C-6** | `__all__` は3 symbol。Enum は package root から公開済み | `__init__.py` L14-18 |

### 3.2 SDK 例外階層の実測（openai 2.46.0 / project venv）

`.\venv\Scripts\python.exe` により読み取り専用で実測した（外部 API 通信0件）。

```text
APIError
├─ APIResponseValidationError
├─ APIStatusError
│   ├─ BadRequestError            (status_code = 400)
│   ├─ AuthenticationError        (status_code = 401)
│   ├─ PermissionDeniedError      (status_code = 403)
│   ├─ NotFoundError              (status_code = 404)
│   ├─ ConflictError              (status_code = 409)
│   ├─ UnprocessableEntityError   (status_code = 422)
│   ├─ RateLimitError             (status_code = 429)
│   └─ InternalServerError        (status_code 固定値なし)
└─ APIConnectionError
    └─ APITimeoutError
```

実測により確定した contract：

| ID | 実測事実 | 判定順序への含意 |
|---|---|---|
| **H-1** | 対象4型は**すべて `APIStatusError` の直接サブクラス**であり、**相互に subclass 関係を持たない** | 4型の相互順序は**結果に影響しない**（順序自由） |
| **H-2** | 対象4型は、v6.11 が先行判定している6型（`AuthenticationError` / `PermissionDeniedError` / `RateLimitError` / `APITimeoutError` / `APIConnectionError` / `InternalServerError`）の**いずれの subclass でもない** | 既存の先行判定に吸われない |
| **H-3** | 逆に、上記6型のいずれも対象4型の subclass では**ない** | 4型を前方へ移動しても既存分類は壊れない |
| **H-4** | `APITimeoutError` は `APIConnectionError` の**サブクラス**である | **既存の Timeout → Connection の順序は維持必須**（v6.11 が既に contract 化済み） |
| **H-5** | `APIStatusError` の直接サブクラスは**8型のみ**で、v6.11 はその8型すべてを判定している | catch-all `UNKNOWN` に落ちるのは、bare `APIError` / bare `APIStatusError` / `APIResponseValidationError` の3系統に限られる |
| **H-6** | 対象4型の `__init__` signature は `(message, *, response: httpx.Response, body: object｜None)` | E2E は `httpx.Response` を用いた Fake 構築が必要（v6.11 の `make_api_status_error()` が既に存在） |

**H-1〜H-3 により、本Releaseの分類は判定順序に依存しない。** ただし将来の SDK 変更
（例：`NotFoundError` が別の型のサブクラスになる）に備え、7.3節で順序を明示的に
contract 化し、E2E で固定する。

### 3.3 v6.19 policy の現行契約

`src/image_generation_fallback_policy/image_generation_fallback_policy.py` L136-157 より。

```python
if isinstance(error, OpenAIImageGenerationError):
    reason = getattr(error, "reason", None)
    if reason is AUTHENTICATION or reason is PERMISSION_DENIED:
        category = IMAGE_GENERATION_NOT_AUTHORIZED
    elif reason is REQUEST_REJECTED:                       # ← 本Releaseの変更点
        category = IMAGE_GENERATION_REQUEST_REJECTED
    elif isinstance(reason, OpenAIImageGenerationErrorReason) and reason in _CONTINUABLE_REASONS:
        category = IMAGE_GENERATION_FAILED
    else:
        category = UNCLASSIFIED
```

| ID | 事実 |
|---|---|
| **P-1** | `REQUEST_REJECTED` の判定は `is`（同一性）による**単一値照合**。したがって新 reason は**この分岐に入らない** |
| **P-2** | `_CONTINUABLE_REASONS` は allow-list（4値）。「v6.11 が将来 reason を追加しても新値は自動的に UNCLASSIFIED（安全側）へ落ちる」ことが §10.7 C-17 で設計 contract として宣言されている |
| **P-3** | `isinstance(reason, ...) and reason in ...` の形は、ハッシュ不可能な reason 値（list 等）が渡された場合の `TypeError` を防ぐ意図的な防御である |
| **P-4** | `_ACTION_BY_CATEGORY` により `IMAGE_GENERATION_REQUEST_REJECTED` → `PROPAGATE_ORIGINAL_ERROR`、`UNCLASSIFIED` → `PROPAGATE_ORIGINAL_ERROR`。**両者の action は同一である** |

**P-2 と P-4 の帰結（重要）**：v6.11 のみを変更した場合、新 reason は
`UNCLASSIFIED` へ落ちるが **action は変わらない**。したがって観測可能な挙動は
変わらない。しかし `category` という v6.19 の Public API 値は変化する。
この扱いが本Releaseの中心的な設計判断である（7.5節・9.5節）。

### 3.4 下流の消費状況

| 層 | reason を読むか | 本Releaseの影響 |
|---|---|---|
| v6.19 `decide_image_generation_fallback()` | **読む**（唯一の消費者） | 7.5節で全数写像を確立 |
| v6.20 `ArticleFeaturedMediaRuntime.apply()` | 読まない（`decision.action` / `decision.category` のみ） | なし |
| v6.21 `main.py` | 読まない（例外を変数へ束縛しない。`_apply_featured_media_step()` L190-193） | なし |
| v6.12 / v6.14 | 読まない（例外を素通し） | なし |

`ArticleFeaturedMediaRuntimeResult.category` は **CONTINUE 時にのみ非 None** であり、
PROPAGATE 時は `raise` されて result 自体が生成されない
（`article_featured_media_runtime.py` L118-128）。したがって
`IMAGE_GENERATION_REQUEST_REJECTED` / `UNCLASSIFIED` の別は
**`main.py` の出力へ到達しない**（`main.py` L192 の print は CONTINUE 経路のみ）。

### 3.5 既存 E2E の棚卸し（走査 methodology と全数）

**走査方法**：`tests/` 全体に対し識別子 `OpenAIImageGenerationErrorReason` を grep し、
ヒットした6ファイルを次の3カテゴリへ分類した。

- **C-A** `list(Enum)` / `len(Enum)` 駆動（値追加で自動的に影響を受ける）
- **C-B** 個別 member の直接参照（値追加の影響を受けない）
- **C-C** `__all__` のみの参照（symbol 追加がないため影響を受けない）

| ファイル | 分類 | 影響 |
|---|---|---|
| `test_e2e_v6_11_0_*.py` | C-B | **あり**：`_err_cases` の4エントリの `_expected_reason` が変わる |
| `test_e2e_v6_18_0_*.py` | C-C | なし（L1043 は `__all__` 3 symbol のみ） |
| `test_e2e_v6_19_0_*.py` | **C-A** | **あり**：`_ALL_REASONS = list(...)`（L292）駆動。詳細は 13.2節 |
| `test_e2e_v6_20_0_*.py` | C-B | **なし**：reason 名を**ハードコードしたタプル**でループする（L540・L571）ため値追加で件数が動かない |
| `test_e2e_v6_21_0_*.py` | C-B | **なし**：L362 `TIMEOUT` / L393 `REQUEST_REJECTED` を直接構築。`REQUEST_REJECTED` を残すため PASS のまま |
| `test_e2e_v6_22_0_*.py` | C-C | **なし**：L1216-1218 は `__all__` のみ。reason 件数の assertion を持たない |

**この走査は v6.22 設計書 3.8.1節が確立した5カテゴリ methodology の簡約版であり、
`list(Enum)` を用いる箇所が v6.19 の1ファイルのみであることを全数で確認した。**

### 3.6 baseline 固定 guard の棚卸し

`tests/` 全体で `BASELINE_COMMIT` を持つのは**2ファイルのみ**である。

| guard | baseline commit | 対象 | 本Releaseとの関係 |
|---|---|---|---|
| `test_e2e_v6_21_0_*.py` L824 | `8d89506`（v6.20.0） | `_protected_paths` 22件 ＋ `tests/` | **allow-list 更新が必要**（GR-9） |
| `test_e2e_v6_22_0_*.py` L1006 | `578af6b`（v6.21.0） | 同22件 ＋ `tests/` ＋ untracked 補完 | **allow-list 更新が必要**（GR-9） |

`_protected_paths` には **`src/openai_image_generation` と
`src/image_generation_fallback_policy` の両方が含まれる**（v6.21 L855-856 相当・
v6.22 L1057・L1065）。したがって本Releaseは両 guard の `_allowed_source_changes` を
更新する義務を負う。詳細は 11章。

なお `test_e2e_v2_*.py` 系にも `git diff` を用いる検査があるが、これらは
**正式 Inventory 25ファイルに含まれない**ため本Releaseの対象外である。

---

## 4. Goals

| ID | Goal |
|---|---|
| **G-1** | `REQUEST_REJECTED` へ集約されている4つの SDK 例外型を、**例外型のみを根拠として**4つの新 reason へ細分化する |
| **G-2** | `REQUEST_REJECTED` を**削除せず**、後方互換のため Public API に残す |
| **G-3** | v6.19 policy が **13値すべて**に対して明示的な category を返すことを、設計・実装・E2E の3層で保証する |
| **G-4** | 新 reason 4値をすべて `IMAGE_GENERATION_REQUEST_REJECTED` ＋ `PROPAGATE_ORIGINAL_ERROR` へ写像し、**action を1件も変えない** |
| **G-5** | `_CONTINUABLE_REASONS`（4値）を**1値も変えない**（CONTINUE 拡大なし） |
| **G-6** | exception message・exception chaining・成功経路・public signature を**1文字も変えない** |
| **G-7** | `main.py` を**バイト単位で無変更**に保つ |
| **G-8** | 分類が message・`exc.args`・`response.body` / `.text` / `.json()` / `.headers`・`status_code` の**いずれも読まない**ことを、設計と E2E の両方で保証する |
| **G-9** | v6.19 の「新 reason は自動的に安全側へ落ちる」性質（P-2 / C-17）を**破壊しない** |

---

## 5. 非スコープ（Non-Goals）

| ID | 明確に扱わないもの | 理由 |
|---|---|---|
| **N-1** | **`CONTENT_POLICY_REJECTED` の新設** | Content Policy 拒否は `BadRequestError`（400）として現れるが、**同じ400にはパラメータ不正も含まれる**。例外型だけでは判別できず、判別には response body の `code` 解析が必要で、これは G-8（解析禁止）に真正面から反する |
| **N-2** | **CONTINUE 対象の拡大** | `_CONTINUABLE_REASONS` は不変。新 reason はすべて PROPAGATE。ORD-3 の領域であり独立Releaseと人間の明示承認を要する |
| **N-3** | **`UNKNOWN` の2経路分離**（`APIError` catch-all と `except Exception` 経路） | DI-11 後半。分離には `generate()` の制御フロー変更が必要で、本Releaseの「Enum 値追加＋分類分岐追加」という閉じた形を崩す |
| **N-4** | **`INVALID_RESPONSE` の細分化**（単発破損 vs スキーマ変更） | DI-11 後半。`_validate_response_structure()` の戻り値契約変更を伴う |
| **N-5** | **response body / message / status_code の解析** | G-8。v6.11 §13.2 および v6.19 §13.2 が定める解析禁止 contract を継承する |
| **N-6** | **exception message の改訂** | 論点8。IL-1 として不正確さを受容し DEF-6.23-1 へ |
| **N-7** | **`status_code` を属性として公開すること** | v6.22 §10.3 D-2 と同じ判断。必要性が生じた時点で独立判断 |
| **N-8** | **observability / logging / metrics への reason 記録** | DI-5 |
| **N-9** | **`main.py`・Runtime・Orchestrator・Composition Root の変更** | Runtime Zero Diff（9章） |
| **N-10** | **retry / idempotency / orphan media** | DI-6 / DI-7 |
| **N-11** | **`requirements.txt`・`.env.example`・`scripts/` の変更** | 依存も設定も増えない |
| **N-12** | **v6.11 の `__all__` 拡張** | 新しい symbol を作らない（Enum 値の追加のみ）。したがって `__init__.py` は無変更 |
| **N-13** | **`ROADMAP.md` / `CHANGELOG.md` / `architecture.md` の更新** | Documentation Integration 工程の責務。本設計工程では行わない |

---

## 6. Design Alternatives

### 6.1 taxonomy 粒度の候補

| 案 | 内容 | 判定 |
|---|---|---|
| **A-1** | 4型 → 4新値（`BAD_REQUEST` / `RESOURCE_NOT_FOUND` / `CONFLICT` / `UNPROCESSABLE_ENTITY`） | **採用** |
| **A-2** | `BadRequestError` だけは `REQUEST_REJECTED` のまま残し、3型のみ細分化 | **不採用**。`REQUEST_REJECTED` の意味が「4型の集約」から「400 専用」へ**静かに変わる**。値を残しつつ意味を変えるのは、削除より危険な後方互換の壊し方である |
| **A-3** | 2値へ縮退（`REQUEST_INVALID` = 400/422、`RESOURCE_NOT_FOUND` = 404、409 は？） | **不採用**。409 の帰属が恣意的になる。また DI-11 の目的は「一次切り分けに使える情報量」の確保であり、SDK 型と1対1に保つほうが将来の再分類が加算的に行える |
| **A-4** | `status_code` を読んで分類（v6.22 の `_classify_status_code()` と同型） | **不採用**。v6.22 が status_code を読んだのは `requests` が型で区別しないためである。openai SDK は**型が status と1対1に対応する**（H-1）ため、型判定のほうが情報量が同じで解析禁止 contract にも安全側で適合する |

### 6.2 v6.19 policy を変更するか

| 案 | 内容 | 判定 |
|---|---|---|
| **B-1** | policy を変更しない。新 reason は `UNCLASSIFIED` へ落ちる | **不採用**。action は不変だが、`category` という Public API の出力が4型で変化する。「分類を細かくしたのに category は粗くなる」という逆行であり、DI-5（observability）が category を記録するようになった時点で情報が失われる |
| **B-2** | `_REJECTED_REASONS` allow-list を導入し、新4値＋`REQUEST_REJECTED` を `IMAGE_GENERATION_REQUEST_REJECTED` へ写像 | **採用**。7.5節 |
| **B-3** | 新 reason ごとに新しい `ImageGenerationFailureCategory` を作る | **不採用**。category は「provider 中立な分類」であり、OpenAI 固有の HTTP セマンティクスを持ち込むと v6.19 §9 の責任境界を壊す。また category 追加は `_ACTION_BY_CATEGORY` の拡張＝判断層の変更であり N-2 に接近する |

### 6.3 v6.11 から継承する点／意図的に逸脱する点

| 項目 | v6.11 | 本Release | 備考 |
|---|---|---|---|
| 分類根拠 | `isinstance` のみ | **同じ** | 継承 |
| `reason` 引数 | 必須（既定値なし） | **同じ** | 継承（v6.22 とは非対称のまま） |
| raise 位置 | `except` の外 | **同じ** | 継承 |
| chaining | `from None` | **同じ** | 継承 |
| message | 型ごとに固定 | **同じ文字列を凍結** | 継承（IL-1 を受容） |
| 判定順序 | 具象 → 一般 | **同じ** | 継承（7.3節で再 contract 化） |

---

## 7. Selected Architecture

### 7.1 reason taxonomy（名前・value・粒度）

`OpenAIImageGenerationErrorReason` を **9値 → 13値** へ拡張する。

| # | name | value | 新規 | 由来 |
|---|---|---|---|---|
| 1 | `AUTHENTICATION` | `"authentication"` | | 既存 |
| 2 | `PERMISSION_DENIED` | `"permission_denied"` | | 既存 |
| 3 | `RATE_LIMIT` | `"rate_limit"` | | 既存 |
| 4 | `TIMEOUT` | `"timeout"` | | 既存 |
| 5 | `CONNECTION` | `"connection"` | | 既存 |
| 6 | `REQUEST_REJECTED` | `"request_rejected"` | | 既存（**後方互換のため保持。production からは到達不能になる**） |
| 7 | `SERVER_ERROR` | `"server_error"` | | 既存 |
| 8 | `INVALID_RESPONSE` | `"invalid_response"` | | 既存 |
| 9 | `UNKNOWN` | `"unknown"` | | 既存 |
| 10 | **`BAD_REQUEST`** | **`"bad_request"`** | ★ | `openai.BadRequestError`（400） |
| 11 | **`RESOURCE_NOT_FOUND`** | **`"resource_not_found"`** | ★ | `openai.NotFoundError`（404） |
| 12 | **`CONFLICT`** | **`"conflict"`** | ★ | `openai.ConflictError`（409） |
| 13 | **`UNPROCESSABLE_ENTITY`** | **`"unprocessable_entity"`** | ★ | `openai.UnprocessableEntityError`（422） |

**命名規約**：name は UPPER_SNAKE、value は name の lower_snake。既存9値がすべて
この規約に従っており、新4値も従う。value は**固定ラベルのみ**で構成し、
URL・credential・prompt・provider 応答本文を一切含まない（G-8・SEC contract）。

**新値は Enum 定義の末尾へ追加する。** 既存9値の定義順・value 文字列は変更しない。

#### 7.1.1 non-normative な運用上の意味づけ

以下の表は**規範ではない**（v6.22 §10.1 の precedent に従い、reason の意味は
「観測された SDK 例外型の分類」であって「原因の断定」ではないことを明記する）。

| reason | 典型的な原因 | 反復性の傾向 |
|---|---|---|
| `BAD_REQUEST` | パラメータ不正、Content Policy 拒否 | 記事固有のことが多いが、パラメータ不正なら systemic |
| `RESOURCE_NOT_FOUND` | **model 不存在・model 提供終了**、endpoint 変更 | **systemic である可能性が高い** |
| `CONFLICT` | リソース競合 | 一過性のことが多い |
| `UNPROCESSABLE_ENTITY` | 意味的に処理不能な要求 | 記事固有のことが多い |

「傾向」であって保証ではない。**この表を根拠に CONTINUE 判定を行ってはならない**
（N-2）。判定の変更は運用データ（DI-5）を踏まえた独立Releaseで行う。

### 7.2 `RESOURCE_NOT_FOUND` という命名について（F-6）

v6.22 は WordPress の 404 を `ROUTE_NOT_FOUND` と命名した。本Releaseが
`RESOURCE_NOT_FOUND` を採るのは意図的な非対称である。

- WordPress 側の 404 は **REST ルートの不在**（`/wp-json/wp/v2/media` へ到達できない）を
  意味することが支配的であり、`ROUTE_NOT_FOUND` が正確だった。
- OpenAI 側の 404 は **要求で指定した model という「リソース」の不在**を意味することが
  支配的であり、`ROUTE_NOT_FOUND` では実態を誤って伝える。

両者は**異なる Enum 型**であり、同一 namespace で衝突しない。
非対称は「名前の統一」より「各文脈での正確さ」を優先した結果である。

### 7.3 判定順序 contract

`_classify_api_error()` の判定順序を次のとおり**固定する**。

```text
 1. AuthenticationError          → AUTHENTICATION
 2. PermissionDeniedError        → PERMISSION_DENIED
 3. RateLimitError               → RATE_LIMIT
 4. APITimeoutError              → TIMEOUT          ★ 5 より前でなければならない（H-4）
 5. APIConnectionError           → CONNECTION
 6. BadRequestError              → BAD_REQUEST              ← 新規
 7. NotFoundError                → RESOURCE_NOT_FOUND       ← 新規
 8. ConflictError                → CONFLICT                 ← 新規
 9. UnprocessableEntityError     → UNPROCESSABLE_ENTITY     ← 新規
10. InternalServerError          → SERVER_ERROR
（catch-all）                    → UNKNOWN
```

**変更点は 6〜9 のみ**である。既存の単一 `isinstance(exc, (BadRequestError,
NotFoundError, ConflictError, UnprocessableEntityError))` によるタプル判定を、
4つの独立した `isinstance` 判定へ展開する。**位置は現行と同一**（5 と 10 の間）であり、
1〜5 と 10 の順序・条件・戻り値は1文字も変えない。

| ID | 順序 contract | 根拠 | E2E |
|---|---|---|---|
| **O-1** | 4 は 5 より前 | H-4（`APITimeoutError` は `APIConnectionError` の subclass） | `ORDER-TIMEOUT-BEFORE-CONNECTION` |
| **O-2** | 6〜9 の相互順序は結果に影響しない | H-1（4型は相互独立） | `ORDER-FOUR-INDEPENDENT`（4型を任意順で判定しても同一結果） |
| **O-3** | 6〜9 は 1〜3 に吸われない | H-2 | `CLS-*` 個別固定 |
| **O-4** | 10 は 6〜9 の後でも前でも結果は同じだが、**現行位置を維持する** | H-1〜H-3 | `ORDER-SERVER-ERROR-STABLE` |

O-2 を E2E で明示的に確認するのは、「順序自由である」という実測事実が
将来の SDK 更新で崩れたときに検出するためである（R-2）。

### 7.4 `REQUEST_REJECTED` の後方互換保持（論点3）

**`REQUEST_REJECTED` は Enum から削除しない。** 本Release後の状態は次のとおり。

| 観点 | 状態 |
|---|---|
| Enum member としての存在 | **存続**（値6） |
| value 文字列 | `"request_rejected"` のまま**不変** |
| package root からの参照可否 | **可**（`__all__` 経由。C-6） |
| production からの到達可能性 | **到達不能になる**（`_classify_api_error()` はもはやこの値を返さない） |
| v6.19 policy での扱い | `IMAGE_GENERATION_REQUEST_REJECTED` へ**写像し続ける**（7.5節） |
| 外部から直接構築した場合 | **従来と完全に同じ挙動**（v6.19 の `REJECT-*` Scenario・v6.21 L393 が実証） |

**削除しない理由：**

1. `OpenAIImageGenerationErrorReason` は `__all__` 経由で公開された Public API であり、
   member の削除は破壊的変更である。
2. 既存 E2E が `REQUEST_REJECTED` を**直接構築**している
   （v6.19 `REJECT-*` の4 Scenario、v6.21 L393 の PROPAGATE 経路）。
   削除するとこれらが `AttributeError` で壊れ、本Releaseと無関係な広範囲の
   テスト改修を誘発する。
3. 「production から到達不能な public 値」は**害がない**。v6.19 policy が
   写像を維持する限り、外部が構築しても従来どおり動作する。
4. 将来 SDK が新しい 4xx 型を追加し、それを個別分類しないと決めた場合の
   **受け皿として再利用できる**。

**明示的な契約**：本Release後、`REQUEST_REJECTED` は
**「deprecated ではなく、production から生成されなくなっただけの有効な値」**である。
deprecation warning は出さない（v6.11 の signature・挙動を変えないため。G-6）。

### 7.5 fallback policy の全数写像（論点5）

`image_generation_fallback_policy.py` に module-level allow-list を新設する。

```python
# 「要求そのものが拒否された」ことを表す reason の allow-list。
# v6.23.0（DI-11前半）で REQUEST_REJECTED が4値へ細分化されたため、
# 単一値照合（is）から集合照合へ変更した。allow-list であるため、
# v6.11 が将来さらに reason を追加しても新値は自動的に UNCLASSIFIED（安全側）
# へ落ちる（C-17 の性質を維持する）。
_REJECTED_REASONS = frozenset({
    OpenAIImageGenerationErrorReason.REQUEST_REJECTED,
    OpenAIImageGenerationErrorReason.BAD_REQUEST,
    OpenAIImageGenerationErrorReason.RESOURCE_NOT_FOUND,
    OpenAIImageGenerationErrorReason.CONFLICT,
    OpenAIImageGenerationErrorReason.UNPROCESSABLE_ENTITY,
})
```

分岐は次のとおり変更する（**変更は `elif` の条件式1行のみ**）。

```python
    # 変更前
    elif reason is OpenAIImageGenerationErrorReason.REQUEST_REJECTED:
    # 変更後
    elif (
        isinstance(reason, OpenAIImageGenerationErrorReason)
        and reason in _REJECTED_REASONS
    ):
```

`isinstance` ガードは P-3 の防御（ハッシュ不可能な reason 値による `TypeError` 回避）を
`_CONTINUABLE_REASONS` 側と**同じ形**で踏襲するために付ける。分岐の**順序**は変えない
（NOT_AUTHORIZED → REJECTED → CONTINUABLE → UNCLASSIFIED）。

#### 7.5.1 全数写像表（13値 × category × action）

| # | reason | category | action | 本Releaseで変化するか |
|---|---|---|---|---|
| 1 | `AUTHENTICATION` | `IMAGE_GENERATION_NOT_AUTHORIZED` | `PROPAGATE_ORIGINAL_ERROR` | 不変 |
| 2 | `PERMISSION_DENIED` | `IMAGE_GENERATION_NOT_AUTHORIZED` | `PROPAGATE_ORIGINAL_ERROR` | 不変 |
| 3 | `RATE_LIMIT` | `IMAGE_GENERATION_FAILED` | `CONTINUE_WITHOUT_FEATURED_MEDIA` | 不変 |
| 4 | `TIMEOUT` | `IMAGE_GENERATION_FAILED` | `CONTINUE_WITHOUT_FEATURED_MEDIA` | 不変 |
| 5 | `CONNECTION` | `IMAGE_GENERATION_FAILED` | `CONTINUE_WITHOUT_FEATURED_MEDIA` | 不変 |
| 6 | `REQUEST_REJECTED` | `IMAGE_GENERATION_REQUEST_REJECTED` | `PROPAGATE_ORIGINAL_ERROR` | 不変 |
| 7 | `SERVER_ERROR` | `IMAGE_GENERATION_FAILED` | `CONTINUE_WITHOUT_FEATURED_MEDIA` | 不変 |
| 8 | `INVALID_RESPONSE` | `UNCLASSIFIED` | `PROPAGATE_ORIGINAL_ERROR` | 不変 |
| 9 | `UNKNOWN` | `UNCLASSIFIED` | `PROPAGATE_ORIGINAL_ERROR` | 不変 |
| 10 | **`BAD_REQUEST`** | **`IMAGE_GENERATION_REQUEST_REJECTED`** | **`PROPAGATE_ORIGINAL_ERROR`** | 新規（写像を明示） |
| 11 | **`RESOURCE_NOT_FOUND`** | **`IMAGE_GENERATION_REQUEST_REJECTED`** | **`PROPAGATE_ORIGINAL_ERROR`** | 新規（写像を明示） |
| 12 | **`CONFLICT`** | **`IMAGE_GENERATION_REQUEST_REJECTED`** | **`PROPAGATE_ORIGINAL_ERROR`** | 新規（写像を明示） |
| 13 | **`UNPROCESSABLE_ENTITY`** | **`IMAGE_GENERATION_REQUEST_REJECTED`** | **`PROPAGATE_ORIGINAL_ERROR`** | 新規（写像を明示） |

**分割の変化：** 4 / 1 / 2 / 2（計9） → **4 / 5 / 2 / 2（計13）**
（`IMAGE_GENERATION_FAILED` / `IMAGE_GENERATION_REQUEST_REJECTED` /
`IMAGE_GENERATION_NOT_AUTHORIZED` / `UNCLASSIFIED`）。

**`IMAGE_GENERATION_FAILED`（＝CONTINUE）の件数は 4 のまま1件も増えない。** これが
G-5・N-2（CONTINUE 拡大なし）の数値的な表現である。

### 7.6 message 凍結（論点8・F-4）

4つの新 reason に対して、`_classify_api_error()` が返す message は
**現行の1文字も変えない**。

```text
BAD_REQUEST            → "OpenAI APIへのリクエストが不正です（Content Policy等による生成拒否を含む）"
RESOURCE_NOT_FOUND     → 同上（完全同一文字列）
CONFLICT               → 同上（完全同一文字列）
UNPROCESSABLE_ENTITY   → 同上（完全同一文字列）
```

**Inherited Limitation IL-1**：`RESOURCE_NOT_FOUND`（model 不存在）に対して
「Content Policy 等による生成拒否を含む」という message が付くのは意味的に不正確である。
本Releaseはこれを**受容する**。理由は次のとおり。

1. message は既存 E2E が文字列一致で固定している contract であり、
   変更は「分類のついでに message を整理する」という v6.22 R-8 が禁じた形になる。
2. message はログ・コンソールへ出力される**利用者可視のテキスト**であり、
   変更は本Releaseの Zero Diff 主張を弱める。
3. reason が正確になったことで、message の不正確さは**構造的に補償される**
   （reason を見れば 404 か 400 かが分かる）。

message の改訂は **DEF-6.23-1** として独立Releaseへ送る。

### 7.7 Security contract

| ID | contract |
|---|---|
| **SEC-1** | 13値すべての value は固定ラベル集合と一致し、URL・API key・prompt・provider 応答本文を含まない |
| **SEC-2** | `_classify_api_error()` は `exc` の**型のみ**を読む。これを「禁止形の列挙」ではなく **`isinstance()` 第1引数以外の一切の使用を禁止する positive allow-list**（7.8節）として規定する。属性名を列挙しないため、SDK が将来追加する未知属性も自動的に禁止される |
| **SEC-3** | 例外インスタンスは provider 例外オブジェクト・response オブジェクトを保持しない（`__init__` が `message` と `reason` のみを受け取る C-2 の帰結） |
| **SEC-4** | `raise ... from None` により `__cause__` / `__context__` が到達不能である性質を維持する（C-5） |

### 7.8 例外引数使用形の positive allow-list 契約（Test Review 再判定 Major 対応）

#### 7.8.1 なぜ deny-list では不十分か

改訂前の設計は「読んではならない属性」を列挙する **deny-list 方式**だった。
この方式には構造的な欠陥がある。

```text
・openai SDK が将来 exc へ新しい属性（例：exc.error_detail）を追加した場合、
  列挙に載っていないため guard を素通りする。
・実測により、provider 例外は既に多数の属性を保持している：
    body / code / message / param / request / request_id / response / status_code / type
  （openai 2.46.0・BadRequestError インスタンスの vars() 実測）
  これらは「読もうと思えば読める秘密情報の入口」であり、
  列挙漏れが即座に SEC-2 の破れになる。
・「何形を禁止したか」という数（旧記述の「9形」）は保証の強さを表さない。
  列挙方式である限り、保証は常に「列挙した分だけ」に留まる。
```

したがって本設計は、**禁止形を列挙するのをやめ、許可形のみを列挙する**方式へ転換する。
これは v6.22 が `GUARD-WMUE-CONSTRUCTION-SHAPE` で
「識別子の出現文脈を allow-list で縛ることにより、迂回形の個別列挙を不要にした」
（v6.22 Architecture Amendment 3・M3-1 対応）のと**同型の転換**である。

#### 7.8.2 規範契約（I-EXC-1）

```text
【I-EXC-1】_classify_api_error() の関数本体において、例外引数を表す識別子の
          出現は、次の唯一の形に限られる。

              isinstance( <exc> , ... )   ← <exc> が第1引数の位置にあること

          これ以外のあらゆる出現文脈は違反とする。
          例外引数名はハードコードせず、当該 FunctionDef の
          第1 positional parameter から AST により決定する。
```

**許可されるのはこの1形のみ**であり、`isinstance` の第2引数（型の位置）に
現れることも**許可しない**（`isinstance(other, exc)` は違反）。

#### 7.8.3 本契約が自動的に禁止するもの（列挙は例示であり定義ではない）

以下は「禁止リスト」ではない。**allow-list の補集合として自動的に禁止される形の例**である。
新しい形が SDK に現れても、allow-list に載らない限り自動的に禁止側へ落ちる。

| 形 | 例 | AST 上の親ノード |
|---|---|---|
| 属性アクセス（**属性名を問わない**） | `exc.code` / `exc.request` / `exc.<未知属性>` | `ast.Attribute` |
| 添字アクセス | `exc["code"]` | `ast.Subscript` |
| 組み込み関数への引き渡し | `str(exc)` / `repr(exc)` / `vars(exc)` | `ast.Call`（func が `isinstance` でない） |
| 内省関数への引き渡し | `getattr(exc, ...)` / `hasattr(exc, ...)` | `ast.Call`（同上） |
| 任意の関数への引き渡し | `helper(exc)` | `ast.Call`（同上） |
| `isinstance` の第2引数 | `isinstance(other, exc)` | `ast.Call`（第1引数ではない） |
| return | `return exc` | `ast.Return` |
| 代入・再束縛 | `_x = exc` / `exc = ...` | `ast.Assign` |
| collection 格納 | `[exc]` / `(exc,)` / `{exc}` | `ast.List` / `ast.Tuple` / `ast.Set` |
| 比較 | `exc == other` | `ast.Compare` |
| 演算 | `exc + x` | `ast.BinOp` |
| f-string 埋め込み | `f"{exc}"` | `ast.FormattedValue` |

**「未知属性の自動禁止」が本契約の中心的価値である。** `exc.` に続く名前を
guard は一切見ない。`ast.Attribute` の子として現れた時点で違反になるため、
SDK の将来の属性追加に対して**保守不要で**保証が持続する。

#### 7.8.4 検査範囲の限定（必須）

本契約は **`_classify_api_error()` の `ast.FunctionDef` 本体のみ**に適用する。
module 全体・他関数へ適用してはならない。実測による根拠：

```text
generate()              第1 positional parameter は self であり、
                        self.<attr> が3件存在する（L296・L302・L312）
_build_generated_image() 第1 positional parameter は response であり、
                        response を関数へ引き渡す形が1件存在する（L170）
```

いずれも v6.22.0 時点から存在する**正当な処理**であり、本Releaseは無変更である。
無差別適用すると即座に偽陽性となる（v6.22 の `NOPARSE-` が同じ罠について
「module 全体を対象に実装してはならない」と警告した precedent に従う）。

#### 7.8.5 現行実装・改修後実装に対する適合性（実測）

`.\venv\Scripts\python.exe` による読み取り専用の AST 解析で確認済み。

| 対象 | 例外引数名 | `exc` の Name 出現数 | allow 形 | 違反 |
|---|---|---|---|---|
| **現行（v6.22.0 時点）** | `exc` | **7**（`isinstance` 7回） | 7 | **0件** |
| **改修後（7.3節の10段判定）** | `exc` | **10**（`isinstance` 10回） | 10 | **0件** |

**現行実装は既に本契約へ余白ゼロで適合している。** すなわち本契約は
「新たな制約を実装へ課す」ものではなく、**既に成立している性質を機械検証可能な
形で固定する**ものである（R-15）。

---

## 8. Public API

### 8.1 変更されるもの

| 対象 | 変更 |
|---|---|
| `OpenAIImageGenerationErrorReason` | member が 9 → **13**。既存9値の name・value・定義順はすべて不変 |
| `OpenAIImageGenerationError.reason` の**取り得る値** | 4型の失敗時に新値が入る（**意図的な公開値の変更**。9.5節） |

### 8.2 変更されないもの

| 対象 | 状態 |
|---|---|
| `openai_image_generation.__all__` | 3 symbol のまま（N-12） |
| `OpenAIImageGenerationError.__init__` の signature | `(self, message, reason)` のまま |
| `OpenAIImageGenerationError` の基底 | `RuntimeError` のまま |
| `OpenAIImageGenerator` の全 public メンバ | 不変（`generate` / `from_env` / `output_mime_type` / `__init__`） |
| `image_generation_fallback_policy.__all__` | 4 symbol のまま |
| `decide_image_generation_fallback()` の signature | `(error)` のまま |
| `ImageGenerationFailureCategory` | **5値のまま**（B-3 不採用の帰結） |
| `ImageGenerationFallbackAction` | 2値のまま |
| `ImageGenerationFallbackDecision` | field は `category` 1件のまま |
| `ArticleFeaturedMediaRuntimeStatus` / `...Result` | 不変 |

### 8.3 Public API 規模の変化

```text
Enum member       :  9 → 13（+4）
public symbol     :  変化なし
public 関数/メソッド: 変化なし
module-private 定数: +1（_REJECTED_REASONS）
```

---

## 9. Runtime・Public API への影響（Zero Diff の定義）

### 9.1 用語の定義（論点6・論点7）

本Releaseは「Production Behavior Zero Diff」を**主張しない**。
主張する Zero Diff を、次のとおり**個別に定義**する。

| ID | 名称 | 定義 | 成立 |
|---|---|---|---|
| **Z-1** | **Runtime Action Zero Diff** | 任意の SDK 例外を入力としたとき、`decide_image_generation_fallback()` が返す `action`、および `ArticleFeaturedMediaRuntime.apply()` の `status` が v6.22.0 時点と完全に一致する | **成立**（9.2節） |
| **Z-2** | **Category Zero Diff** | 同上の条件で `decision.category` が v6.22.0 時点と完全に一致する | **成立**（7.5節の policy 写像により。9.5節） |
| **Z-3** | **main.py Zero Diff** | `main.py` に**バイト単位で差分がない** | **成立**（無改修） |
| **Z-4** | **Message Zero Diff** | 全 raise 経路の message 文字列が完全一致 | **成立**（7.6節） |
| **Z-5** | **Chaining Zero Diff** | `__cause__` / `__context__` の到達不能性が不変 | **成立**（C-5 を無変更） |
| **Z-6** | **Signature Zero Diff** | すべての public signature が不変 | **成立**（8.2節） |
| **Z-7** | **Success-path Zero Diff** | 成功時の `GeneratedImage` 生成経路・`MediaUploadResult`・`ArticleData` 束縛が不変 | **成立**（`generate()` の成功経路を無変更） |
| **Z-8** | **CONTINUE Set Zero Diff** | `_CONTINUABLE_REASONS` の内容が不変（4値） | **成立**（G-5） |
| **✗** | **Production Behavior Zero Diff** | 観測可能なあらゆる出力が不変 | **成立しない。主張してはならない**（9.5節） |

### 9.2 Z-1（Runtime Action Zero Diff）の成立根拠

証明は3段で構成される。

```text
段1: reason の変化は4型に限られる。
     _classify_api_error() の変更は 7.3節の 6〜9 のみ。
     1〜5・10・catch-all は条件・戻り値ともに1文字も変えない。
     したがって、変化するのは BadRequest / NotFound / Conflict /
     UnprocessableEntity の4型に対する reason だけである。

段2: 4型の category は変わらない。
     変更前: 4型 → REQUEST_REJECTED → IMAGE_GENERATION_REQUEST_REJECTED
     変更後: 4型 → 各新値 → _REJECTED_REASONS に含まれる
                          → IMAGE_GENERATION_REQUEST_REJECTED
     （7.5.1節の全数表 #10〜#13）

段3: category が変わらなければ action も status も変わらない。
     action は _ACTION_BY_CATEGORY による category の純関数（P-4）。
     status は action の純関数（runtime L122-128）。
     ゆえに action・status ともに不変。∎
```

段2 は **policy を変更するからこそ成立する**。policy を変更しない案 B-1 では
段2 が破れ、category が `UNCLASSIFIED` へ変化する（action は偶然一致するが
Z-2 は成立しない）。**F-1 の本質はここにある。**

### 9.3 CONTINUE 拡大がないことの構造的保証（論点6）

| 保証 | 内容 |
|---|---|
| **設計** | `_CONTINUABLE_REASONS` を編集対象から外す（10章の File Change Plan が当該定数を変更対象として宣言しない） |
| **写像** | 新4値はすべて `_REJECTED_REASONS` 側へ入る。同一 reason が両方の frozenset に属さないことを E2E で確認する（`CONT-DISJOINT`） |
| **E2E** | `CONT-EXACTLY-4`（既存・v6.19 L515）が**期待値も実測値も変更なしで PASS し続ける**ことが、CONTINUE 拡大がないことの直接証拠になる |
| **件数** | `IMAGE_GENERATION_FAILED` へ写像される reason 数が 4 のまま不変（7.5.1節） |

### 9.4 main.py Zero Diff（論点6）

`main.py` は本Releaseで**一切変更しない**。根拠：

- `main.py` は reason を読まない（3.4節）。
- `main.py` L192 が出力する `result.category.value` は CONTINUE 経路のみで到達し、
  CONTINUE 経路の category は `IMAGE_GENERATION_FAILED` のみである（7.5.1節 #3-5,7）。
  **本Releaseは CONTINUE 経路の reason を1つも変えない**ため、L192 の出力は不変。
- PROPAGATE 経路は `raise` されるため category を出力しない（3.4節）。

検証は 11章の NOIMPACT guard（`main.py` を含む `_protected_paths`）が担う。

### 9.5 意図的に変更される公開値（論点7）

**`OpenAIImageGenerationError.reason` は public 属性であり、本Releaseで
4型に対して意図的に別の値になる。**

```python
# v6.22.0 時点
exc.reason is OpenAIImageGenerationErrorReason.REQUEST_REJECTED   # BadRequestError の場合 True

# v6.23.0 以降
exc.reason is OpenAIImageGenerationErrorReason.BAD_REQUEST        # True
exc.reason is OpenAIImageGenerationErrorReason.REQUEST_REJECTED   # False ← 変化
```

したがって、

- 本Releaseを **「Production Behavior Zero Diff」と表現してはならない。**
  v6.22 が使えた表現を、本Releaseは使えない。
- Release Review・CHANGELOG・ROADMAP においても、
  **「Runtime Action Zero Diff（Z-1〜Z-8）」という限定した表現を用いる。**
- この変更が安全である根拠は「観測可能な挙動が変わらないこと」ではなく、
  **「reason を読む消費者が v6.19 policy ただ1つであり、その写像を同時に更新するため
  下流の結論が変わらないこと」**（3.4節・9.2節）である。

### 9.6 v6.19 の安全側性質（C-17）の維持（G-9）

`_REJECTED_REASONS` は **allow-list** である。deny-list（「これ以外は継続」）ではない。
したがって v6.11 が将来さらに reason を追加した場合、その新値は
`_REJECTED_REASONS` にも `_CONTINUABLE_REASONS` にも属さず、
`else` 節の `UNCLASSIFIED` ＝ `PROPAGATE_ORIGINAL_ERROR`（安全側）へ落ちる。
**本Releaseはこの性質を破壊しない。**

---

## 10. 実装計画（File Change Plan）

### 10.1 Production Code（2ファイル）

#### (1) `src/openai_image_generation/openai_image_generator.py`

| # | 変更 | 内容 |
|---|---|---|
| 1-1 | Enum 拡張 | `OpenAIImageGenerationErrorReason` の**末尾**へ4 member を追加（7.1節の #10〜#13） |
| 1-2 | 分類分岐 | `_classify_api_error()` 内の単一タプル `isinstance` を、4つの独立 `isinstance` へ展開（7.3節の 6〜9） |
| 1-3 | docstring | `_classify_api_error()` の docstring へ、判定順序 contract（O-1〜O-4）と「4型は相互独立」の実測根拠を追記 |

**変更してはならない箇所**（実装工程の禁止事項）：

```text
・_MSG_* 定数（4箇所の message 文字列を含む）
・既存9 member の name / value / 定義順
・OpenAIImageGenerationError.__init__ の signature と本体
・_validate_prompt / _validate_response_structure / _build_generated_image
・OpenAIImageGenerator の全メソッド（generate() の try/except 構造を含む）
・raise ... from None の2箇所（L185・L310）
・import 文（enum は既に import 済み。新規 import は不要）
```

#### (2) `src/image_generation_fallback_policy/image_generation_fallback_policy.py`

| # | 変更 | 内容 |
|---|---|---|
| 2-1 | 定数追加 | module-level `_REJECTED_REASONS` frozenset（5値）を `_CONTINUABLE_REASONS` の直後へ追加 |
| 2-2 | 分岐条件 | `elif reason is REQUEST_REJECTED:` を集合照合へ変更（7.5節） |
| 2-3 | docstring/コメント | 変更理由と allow-list である理由（9.6節）をコメントで明記 |

**変更してはならない箇所**：

```text
・_CONTINUABLE_REASONS の内容（4値）      ← G-5 の中核
・_ACTION_BY_CATEGORY の内容（5エントリ）
・ImageGenerationFailureCategory の5値
・ImageGenerationFallbackAction の2値
・ImageGenerationFallbackDecision の定義（field・property）
・decide_image_generation_fallback() の signature・TypeError message・分岐順序
・import 文（新規 import 不要。既に必要な symbol を import 済み）
・try/except の不在（NOEXC guard がゼロ件を固定）
・module が定義する class の集合（NOEXC-NO-NEW-EXCEPTION-CLASS が固定）
```

#### 変更しないと明示する Production ファイル

```text
src/openai_image_generation/__init__.py            （新 symbol なし。N-12）
src/image_generation_fallback_policy/__init__.py   （__all__ 不変）
src/article_featured_media_runtime/*                （reason を読まない）
src/article_featured_media_composition/*
src/article_featured_media_orchestration/*
src/generated_image_wordpress_media/*
src/wordpress_media/*                               （v6.22 の成果に触れない）
src/ai_image_generation/*
src/image_generation_config/*
src/generated_image_filename_policy/*
src/article_image_prompt_construction/*
main.py / requirements.txt / .env.example / scripts/*
```

### 10.2 E2E（新規1・更新4）

| 種別 | ファイル | 変更内容 |
|---|---|---|
| 新規 | `tests/test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py` | 12章の prefix 構成に従う |
| 更新 | `tests/test_e2e_v6_11_0_*.py` | `_err_cases` の4エントリの `_expected_reason` のみ差し替え（**アサーション件数不変**） |
| 更新 | `tests/test_e2e_v6_19_0_*.py` | 期待表への4キー追加、件数期待値5件の更新、ラベル文言更新（13.2節。**+8 assertion**） |
| 更新 | `tests/test_e2e_v6_21_0_*.py` | NOIMPACT allow-list とラベルのみ（11.2節。**件数不変**） |
| 更新 | `tests/test_e2e_v6_22_0_*.py` | NOIMPACT allow-list とラベル、および S2R-1 のコメント追記（11.3節・11.5節。**件数不変**） |

### 10.3 ドキュメント（Documentation Integration 工程で実施。本工程では行わない）

```text
docs/design/openai_image_generation_api_rejection_reason_classification_foundation.md（本ファイル。実績追記）
docs/ROADMAP.md        （DI-11 前半の完了・後半の Deferred 化）
docs/CHANGELOG.md      （v6.23.0 節）
docs/architecture.md   （OpenAI Image Generation Adapter 層の reason taxonomy 更新）
```

---

## 11. guard／baseline 更新計画（論点10・GR-1〜GR-11）

### 11.1 適用される GR 条項

| GR | 本Releaseでの適用 |
|---|---|
| **GR-1** | 保護対象を削除しない。`_protected_paths` 22件は両 guard で**そのまま維持** |
| **GR-2** | 既存 guard の `BASELINE_COMMIT` を書き換えない（v6.21 の `8d89506`、v6.22 の `578af6b` を**そのまま維持**） |
| **GR-3** | 「差分ゼロ」検査を「差分が allow-list の範囲内」検査へ精緻化する |
| **GR-4** | allow-list へ登録できるのは、**本設計書 10章が明示的に宣言したファイルのみ**（`openai_image_generator.py` と `image_generation_fallback_policy.py` の2ファイル。実装工程での追加は禁止） |
| **GR-5** | 精緻化はアサーション**件数を変えない**方法で行う（期待値・許容集合リテラル・ラベル文言の差し替えのみ） |
| **GR-6** | 本Releaseは自身の E2E に、**自身の baseline commit を固定した完全な guard** を持つ。既存 guard に依存しない。allow-list は equality で検証し、陽性対照を置く |
| **GR-7** | 許容件数をラベル文言へ埋め込まない。**既存ラベルに埋め込まれている件数表現は本Releaseで除去する**（F-3） |
| **GR-8** | 精緻化の内容と検査意図の保持根拠を本節へ明記する（本節がその記述である） |
| **GR-9** | 保護対象パスへ触れるため、**それ以前に存在するすべての baseline 固定 guard（2件）**の allow-list を更新する。ratchet 構造により、最新 guard（v6.23）が最も厳格な権威的保証を担う |
| **GR-10** | 保護パスの**追加**は行わない（`src/openai_image_generation`・`src/image_generation_fallback_policy` は既に22件に含まれる） |
| **GR-11** | package 削除がないため**適用外** |

### 11.2 v6.21 guard の更新（`test_e2e_v6_21_0_*.py`）

```text
BASELINE_COMMIT      : 8d89506（変更しない。GR-2）
_protected_paths     : 22件（変更しない。GR-1）

_allowed_source_changes : 2エントリ追加
    "src/openai_image_generation": frozenset({
        "src/openai_image_generation/openai_image_generator.py",
    }),
    "src/image_generation_fallback_policy": frozenset({
        "src/image_generation_fallback_policy/image_generation_fallback_policy.py",
    }),
    ※ 既存の "src/wordpress_media" エントリは維持する（v6.22 の正当な変更履歴）

_allowed_test_changes : 2件追加（6 → 8）
    + "test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py"
    + "test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py"
    ※ "test_e2e_v6_19_0_*.py" は既に含まれているため追加不要

ラベル : NOIMPACT-TESTS-SCOPE から「許容6件（…）」の件数表現を除去（GR-7）
件数   : 変化なし（GR-5）
```

### 11.3 v6.22 guard の更新（`test_e2e_v6_22_0_*.py`）

```text
BASELINE_COMMIT      : 578af6b（変更しない。GR-2）
_protected_paths     : 22件（変更しない。GR-1）

_allowed_source_changes : 2エントリ追加（v6.21 と同一内容）

_allowed_test_changes : 2件追加（5 → 7）
    + "test_e2e_v6_11_0_*.py"
    + "test_e2e_v6_23_0_*.py"

ラベル : NOIMPACT-TESTS-SCOPE / NOIMPACT-NO-UNTRACKED-TESTS から
         「許容5件」の件数表現を除去（GR-7・F-3）
件数   : 変化なし（GR-5）
```

**注意（実装工程への申し送り）**：v6.22 guard は
`NOIMPACT-SCOPE-COVERAGE[src/wordpress_media]` と
`NOIMPACT-SCOPE-EXACT[src/wordpress_media]` を持ち、`src/wordpress_media` について
**equality（containment ∧ coverage）**を検査している。本Releaseは
`src/wordpress_media` を変更しないため、この equality は**そのまま成立し続ける**。
`src/openai_image_generation` については v6.22 guard 側では containment のみ
（allow-list に入れるだけ）とし、**equality 検査は v6.23 自身の guard に置く**（GR-6）。

### 11.4 v6.23 自身の guard（GR-6）

```text
BASELINE_COMMIT      : 8fd8453（v6.22.0 = 本Releaseの開始時点）
_protected_paths     : 22件（v6.21／v6.22 と同一のリストを再掲。GR-1 の趣旨）
_allowed_source_changes :
    "src/openai_image_generation"          → {openai_image_generator.py}
    "src/image_generation_fallback_policy" → {image_generation_fallback_policy.py}
    （それ以外は空集合＝差分ゼロと等価。GR-3）

検査:
  NOIMPACT-EXISTS[path]            対象が作業ツリーに実在（vacuous pass 防止 1）
  NOIMPACT-BASELINE-TRACKED[path]  baseline に追跡ファイルが実在（vacuous pass 防止 2）
  NOIMPACT-SCOPE[path]             containment: changed ⊆ allowed
  NOIMPACT-NO-UNTRACKED[path]      untracked 集合が空
  NOIMPACT-SCOPE-COVERAGE[×2]      coverage: allowed ⊆ changed（allow-list の空振り検出）
  NOIMPACT-SCOPE-EXACT[×2]         equality（containment ∧ coverage）
  NOIMPACT-TESTS-SCOPE             tests/ の差分が allow-list の範囲内（件数をラベルに書かない）
  NOIMPACT-NO-UNTRACKED-TESTS      tests/ の untracked が allow-list の範囲内
```

**`main.py` は `_protected_paths` に含まれ、allow-list が空集合であることにより
Z-3（main.py Zero Diff）が機械的に保証される。**

### 11.5 S2R-1 / DEF-6.22-15 の解消（論点11）

v6.22 設計書 §19 DEF-6.22-15 は次のとおり記録している。

```text
_scan_noparse_violations() の str(...) 検出が AC-6.22-13 の例示（str(exc)）より広く、
対象2関数内の任意の str(...) 呼び出しを禁止する実装になっている。実害はないが、
実装意図をコメントで明記していない。本Releaseではtest fileを変更しない。
→ 将来Release（次回 tests/test_e2e_v6_22_0_*.py を変更する機会に、
   コメント追記のみの軽微な対応として実施を検討）
```

**本Releaseは 11.3節により `tests/test_e2e_v6_22_0_*.py` を必ず変更する。**
これは DEF-6.22-15 が想定した「次回変更する機会」に正確に該当するため、
同ファイルの `_scan_noparse_violations()` 付近へ**説明コメントを追記**して解消する。

```text
追記内容（趣旨）:
  引数名を限定せず任意の str(...) 呼び出しを禁止するのは、
  対象2関数に正当な str() 呼び出しが存在せず、かつ将来どちらの関数へも
  一貫して適用できるようにするための意図的な設計判断である。
制約:
  コメント追記のみ。アサーション・検査ロジック・件数は一切変更しない（GR-5）。
```

これにより **DEF-6.22-15（S2R-1）は本Releaseで完了**とする。

### 11.6 M5-1 の扱い（論点12）

v6.22 から継続している Deferred「match-case class pattern
（`case WordPressMediaUploadError():`）を Guard の allow-list へ含めるか否か」について。

**判断：本Releaseでは判断機会が発生しない。Deferred を継続する。**

根拠：

1. M5-1 は v6.22 の `GUARD-WMUE-CONSTRUCTION-SHAPE`（識別子の出現文脈を
   allow-list で縛る AST guard）に固有の論点である。
2. **本Releaseは同型の構築形 guard を必要としない**（12.4節・F-5）。
   v6.11 の `reason` は既定値のない必須引数であり、渡し忘れは
   `TypeError` として**実行時に構造的に検出される**。v6.22 が
   構築形 guard を要した理由（既定値 `UNKNOWN` により渡し忘れが
   silent に通る）が、本Releaseには存在しない。
3. 本Releaseは v6.22 の guard 本体（検査ロジック）を変更しない
   （11.3節の変更は allow-list・ラベル・コメントのみ）。
   したがって allow-list へ match-case を含めるか否かの判断は求められない。

**M5-1 は、`GUARD-WMUE-CONSTRUCTION-SHAPE` の検査ロジック自体を変更する
Release が現れた時点で判断する。** 本Releaseで無理に消化しない。

---

## 12. E2E 契約（Test Strategy）

詳細な Scenario 設計は Test Review 工程で確定する。本設計書は
**prefix 構成と必ず検証すべき contract** のみを規定する。

### 12.1 新規 E2E の prefix 構成

| prefix | 検証対象 |
|---|---|
| `API-` | Enum の member 数が **13**・新4値の name と value 文字列・既存9値の name/value/**定義順**が不変・package root から参照可・`__all__` が **3 symbol のまま** |
| `CLS-` | `_classify_api_error()` の型判定。**14ケース**（新4型＋既存6型＋catch-all 4系統）。詳細と期待値は 12.5節（M-1 対応） |
| `ORDER-` | 7.3節の順序 contract。`ORDER-TIMEOUT-BEFORE-CONNECTION`（O-1）・`ORDER-FOUR-INDEPENDENT`（O-2。4型を任意順で評価しても同一結果）・`ORDER-SERVER-ERROR-STABLE`（O-4） |
| `MSG-` | **4型すべての message が v6.22.0 時点の文字列と完全一致**（Z-4）。既存全 raise 経路の message も固定 |
| `E2E-` | `generate()` 経由の end-to-end。Fake client が4型を送出したとき、送出される `OpenAIImageGenerationError` の型・reason・message が期待どおりであること |
| `CHAIN-` | 4型経由で送出された例外の `__cause__` / `__context__` がいずれも `None`（Z-5） |
| `COMPAT-REJECTED-` | **`REQUEST_REJECTED` が Enum に存続し、value が `"request_rejected"` のまま**であること・直接構築した場合の policy 出力が従来と同一であること（7.4節） |
| `POLICY-` | **13値すべて**に対する `category` と `action` の全数写像（7.5.1節の表と1対1）。`REASON-COVERAGE-13`（`list(Enum)` と期待表のキー集合が一致） |
| `SPLIT-` | 分割が **4 / 5 / 2 / 2 = 13** であること（decide() の実測値を集計。自己参照的 assertion を避ける v6.19 m-2 の precedent に従う） |
| `CONT-` | **`_CONTINUABLE_REASONS` が4値のまま不変**・CONTINUE となる reason が正確に4値・`CONT-DISJOINT`（`_CONTINUABLE_REASONS` ∩ `_REJECTED_REASONS` = ∅） |
| `ZERODIFF-ACTION-` | **13値すべてについて、action が v6.22.0 時点の期待値と一致**（Z-1 の直接検証）。新4値については「`PROPAGATE_ORIGINAL_ERROR` であること」を明示的に固定 |
| `NOPARSE-` | **AST 検査（positive allow-list 方式）**：`_classify_api_error()` の `ast.FunctionDef` 本体において、例外引数の出現が `isinstance(<exc>, ...)` の**第1引数の形のみ**であることを検証する（I-EXC-1・7.8節）。**禁止属性・禁止形を列挙しない。** 規範仕様と対照群は 12.6節。**module 全体を対象にしてはならない**（7.8.4節の実測根拠） |
| `SEC-` | 13値の value が固定ラベル集合と一致・URL/credential/prompt/応答本文を含まない・例外インスタンスが response object を保持しない（SEC-1〜SEC-3）。provider 例外に埋め込んだ secret marker が message/repr/args/`__dict__` のいずれにも露出しないこと |
| `DEP-` | **AST 検査**：`openai_image_generator.py` の import root が `base64`／`binascii`／`os`／`enum`／`ai_image_generation`（＋関数内 `openai`）のみ・`image_generation_fallback_policy.py` の import root が既存許可集合のままであること |
| `NOEXC-` | policy module に `ast.ExceptHandler` 0件・`raise ... from` 0件・新規 class 定義なし（v6.19 の既存 guard と同型の再確認） |
| `NOIMPACT-` | 11.4節の baseline 固定 guard |
| `COMPAT-` | v6.10〜v6.22 各 package の `__all__` 不変・`WordPressMediaUploadErrorReason` **12値不変**・`ImageGenerationFailureCategory` **5値不変**・`ArticleFeaturedMediaRuntimeStatus` 3値不変 |
| `SOCKET-` | `socket.getaddrinfo` / `socket.socket.connect` を遮断した状態で全テストが完走（実 HTTP 通信0件） |

### 12.2 hermetic 要件

**全テストを hermetic とする。** provider 例外は `httpx.Response` を用いた
Fake 構築（v6.11 の `make_api_status_error()` と同型。H-6）で生成し、
client は Fake を明示注入する。**実 OpenAI・実 WordPress・実ネットワークへ
一切到達しない。** これは v6.21 Release Review M-2 で確立した方針である。

### 12.3 陽性対照（vacuous pass 防止）

| 対象 | 陽性対照 |
|---|---|
| `NOPARSE-` | **陽性対照16形**（allow-list 外の使用形を含む合成ソースが、それぞれ独立に違反として検出されること）＋**陰性対照4形**（正当な `isinstance` 形が違反にならないこと）。さらに vacuous 防止3本（関数検出・引数名決定・出現数）。詳細は 12.6節 |
| `NOIMPACT-SCOPE` | allow-list を意図的に空にした場合に FAIL することを、合成集合演算で確認する |
| `NOIMPACT-SCOPE-COVERAGE` | allow-list に書いたのに実際は変更していない場合を検出できること |
| `POLICY-` | 期待表ではなく **`decide()` の実測戻り値**を集計元とする（v6.19 m-2 の precedent） |
| `ORDER-FOUR-INDEPENDENT` | 4型の評価順を入れ替えた参照実装と本実装の結果が一致すること |

### 12.4 構築形 guard を置かない判断（F-5・論点12）

v6.22 は `GUARD-WMUE-CONSTRUCTION-SHAPE`（`WordPressMediaUploadError` の
構築を `raise` 直下に限り、`reason=` keyword を必須化する AST guard）を設けた。
**本Releaseは同型の guard を設けない。**

| v6.22 | v6.23 |
|---|---|
| `reason` は既定値 `UNKNOWN` 付きの任意引数 | `reason` は**既定値なしの必須引数**（C-2） |
| 渡し忘れが silent に `UNKNOWN` へ落ちる | 渡し忘れは **`TypeError` で即座に失敗する** |
| 構築箇所が9箇所 | 構築箇所が **2箇所**（C-3。いずれも `raise` 直下） |
| → 構造的検出手段として guard が必要 | → **Python の呼び出し規約自体が guard として機能する** |

代わりに、`CLS-`（4型の分類固定）と `E2E-`（`generate()` 経由の end-to-end）の
二重検証で「分類漏れ」を behavioral に検出する。

### 12.5 `CLS-` の14ケース（M-1 対応）

改訂前の設計は「既存6型の回帰」としか規定しておらず、catch-all 経路と
「HTTPステータス値では分類しない」ことの陰性対照が欠落していた。
venv 実測により catch-all へ落ちる3系統がすべて構築可能であることを確認し、
次の14ケースを規範として確定する。**各ケース 2 assertion（reason・message）。**

| # | 入力 | 期待 reason | 期待 message |
|---|---|---|---|
| 1 | `AuthenticationError` | `AUTHENTICATION` | 認証失敗の既存文言 |
| 2 | `PermissionDeniedError` | `PERMISSION_DENIED` | 権限の既存文言 |
| 3 | `RateLimitError` | `RATE_LIMIT` | レート制限の既存文言 |
| 4 | `APITimeoutError` | `TIMEOUT` | timeout の既存文言 |
| 5 | `APIConnectionError` | `CONNECTION` | 接続失敗の既存文言 |
| 6 ★ | `BadRequestError` | **`BAD_REQUEST`** | ★凍結文言（7.6節） |
| 7 ★ | `NotFoundError` | **`RESOURCE_NOT_FOUND`** | ★凍結文言 |
| 8 ★ | `ConflictError` | **`CONFLICT`** | ★凍結文言 |
| 9 ★ | `UnprocessableEntityError` | **`UNPROCESSABLE_ENTITY`** | ★凍結文言 |
| 10 | `InternalServerError` | `SERVER_ERROR` | server error の既存文言 |
| **11** | `APIStatusError`（**status_code = 400**） | **`UNKNOWN`** | catch-all 文言 |
| **12** | `APIStatusError`（status_code = 500） | **`UNKNOWN`** | catch-all 文言 |
| **13** | `APIError`（bare） | `UNKNOWN` | catch-all 文言 |
| **14** | `APIResponseValidationError` | `UNKNOWN` | catch-all 文言 |

**#11 が M-1 の核心**である。status_code が 400 でありながら `BadRequestError`
ではないオブジェクトが `BAD_REQUEST` にならないことを固定し、
**分類が HTTP ステータス値ではなく例外型のみに基づく**（G-8）ことを
behavioral に証明する。これは `_classify_status_code()` を持つ v6.22 との
設計差（6.1節 A-4 で status_code 方式を不採用とした判断）を守る回帰検出器である。

**構築可能性（venv 実測・外部通信0件）**

```text
openai.APIError(message, request, *, body)                    → 構築可
openai.APIStatusError(message, *, response, body)             → 構築可（status_code は response 由来）
openai.APIResponseValidationError(response, body, *, message) → 構築可
いずれも先行判定6型・対象4型のどれにも isinstance ヒットせず catch-all へ落ちる
```

### 12.6 `NOPARSE-` guard の規範仕様（再判定 Major 対応）

#### 12.6.1 検査アルゴリズム

```text
手順1  対象ファイルを ast.parse し、name == "_classify_api_error" の
       FunctionDef / AsyncFunctionDef を1件取得する。
       取得できなければ FAIL（vacuous pass 防止その1）。

手順2  当該 FunctionDef の第1 positional parameter
       （posonlyargs + args の先頭）から例外引数名を決定する。
       引数名をテスト側にハードコードしてはならない。
       決定できなければ FAIL（vacuous pass 防止その2）。

手順3  当該 FunctionDef 配下の親子関係マップを構築する。

手順4  配下のすべての ast.Name のうち id が例外引数名と一致するものを列挙する。
       列挙数が 0 なら FAIL（vacuous pass 防止その3：走査が空振りしていない証明）。

手順5  各出現について、親ノードが次を「すべて」満たすときのみ allow とする。
         (a) 親が ast.Call である
         (b) 親.func が ast.Name である
         (c) 親.func.id == "isinstance"
         (d) 親.args が非空であり、親.args[0] が当該 Name ノードそのもの
       上記以外はすべて violation として、行番号と親ノード種別を記録する。

手順6  violations が空であること、かつ allow 数 == 出現総数であることを検証する。
```

**手順5 の (d) が「第1引数の位置」を強制する。** `isinstance(other, exc)` は
(a)〜(c) を満たすが (d) を満たさないため違反になる。

#### 12.6.2 陽性対照（16形・すべて違反として検出されること）

**venv 実測により16形すべてが検出されることを確認済み（16/16）。**

| ID | 形 | 例 | 検出時の親ノード |
|---|---|---|---|
| **P-1** | 既知属性 | `exc.code` | `Attribute` |
| **P-2** | 既知属性 | `exc.request` | `Attribute` |
| **P-3** | **未知属性** | `exc.future_unknown_attr_xyz` | `Attribute` |
| **P-4** | 添字 | `exc["code"]` | `Subscript` |
| **P-5** | 内省 | `getattr(exc, "code")` | `Call` |
| **P-6** | 内省 | `hasattr(exc, "code")` | `Call` |
| **P-7** | 文字列化 | `str(exc)` | `Call` |
| **P-8** | 文字列化 | `repr(exc)` | `Call` |
| **P-9** | 内部辞書 | `vars(exc)` | `Call` |
| **P-10** | 任意関数への引き渡し | `helper(exc)` | `Call` |
| **P-11** | return | `return exc` | `Return` |
| **P-12** | 代入 | `_x = exc` | `Assign` |
| **P-13** | collection 格納 | `[exc]` | `List` |
| **P-14** | comparison | `exc == other` | `Compare` |
| **P-15** | **`isinstance` 第2引数** | `isinstance(other, exc)` | `Call`（位置違反） |
| **P-16** | f-string 埋め込み | `f"{exc}"` | `FormattedValue` |

**P-3 が本方式の中心的価値を実証する。** 属性名を一切列挙していないにもかかわらず、
存在しない未知の属性名が検出される。これにより SDK の将来の属性追加に対して
**guard の保守なしに**保証が持続する。

**P-15 は allow-list の位置制約を実証する。** `isinstance` を呼びさえすれば
通るのではなく、第1引数の位置でなければならない。

#### 12.6.3 陰性対照（4形・すべて違反0件で通過すること）

**venv 実測により4形すべてが通過することを確認済み（4/4）。**

| ID | 形 | 例 | 期待 |
|---|---|---|---|
| **N-1** | 単一型 `isinstance` | `isinstance(exc, openai.BadRequestError)` | 違反0・allow 1 |
| **N-2** | タプル `isinstance` | `isinstance(exc, (openai.BadRequestError, openai.NotFoundError))` | 違反0・allow 1 |
| **N-3** | 他識別子の属性参照 | 同じ関数内の `openai.NotFoundError` 等 | 違反0（`exc` 以外の Name は走査対象外） |
| **N-4** | 文字列・docstring 中の `exc` | `"""exc を解析してはならない。"""` / `return ("exc conflict", ...)` | 違反0（`ast.Constant` は Name ではない） |

**N-1 は再判定で明示的に要求された陰性対照である。** guard が過剰に厳しく、
正当な実装形まで拒否していないことを保証する。

#### 12.6.4 検査範囲限定の検証

`NOPARSE-SCOPE-FUNCTION-ONLY` は、同一規則を他関数へ適用した場合に
違反が検出されることを合成確認し、**対象範囲の限定そのもの**を検証する。
実測根拠（7.8.4節）：`generate()` で3件、`_build_generated_image()` で1件の
違反が出る。いずれも v6.22.0 時点から存在する正当な処理である。

### 12.7 import 契約（m-3 対応）

新規 E2E は次のパスで private symbol を import する。private の直接 import は
v6.19 E2E（`_ACTION_BY_CATEGORY` / `_CONTINUABLE_REASONS`）の precedent に従う。

```python
from openai_image_generation import (
    OpenAIImageGenerationError, OpenAIImageGenerationErrorReason)
from openai_image_generation.openai_image_generator import _classify_api_error
from image_generation_fallback_policy import (
    ImageGenerationFailureCategory, ImageGenerationFallbackAction,
    decide_image_generation_fallback)
from image_generation_fallback_policy.image_generation_fallback_policy import (
    _CONTINUABLE_REASONS, _REJECTED_REASONS)
```

AST 検査の対象ファイルは `PROJECT_ROOT / "src" / "openai_image_generation" /
"openai_image_generator.py"` を `read_text(encoding="utf-8")` で読む
（import 済み module の `__file__` に依存しない）。

### 12.8 assertion の数え方と見込み内訳（s-2 対応）

#### 12.8.1 数え方の規約

| ID | 規則 |
|---|---|
| **R-a** | **1 assertion = `results_log` への1 append = `check()` の1回呼び出し。** `check_true` / `check_false` / `check_contains` / `check_not_contains` はすべて `check()` へ委譲するため各1 assertion |
| **R-b** | K 要素のループ内に M 本の `check` がある場合は **K × M** assertion。if/else の各枝に1本ずつなら反復あたり1本 |
| **R-c** | parameterized case のリストは **要素数 × 1ケースあたりの check 本数** |
| **R-d** | 複合ヘルパは展開して数える（v6.11 `check_openai_error(marker=…)` は **4** assertion、marker 省略時は 3） |
| **R-e** | **反復回数 ≠ assertion 数。** 集約比較（N 通り回して結果を1回比較する形）は **1 assertion** |

#### 12.8.2 ブロック別内訳（見込み値）

| prefix | 主な内容 | 反復 | 1反復 | **assertion** |
|---|---|---|---|---|
| `API-` | COUNT-13 / NAMES-EXACT / VALUES-EXACT / VALUE-UNIQUE / VALUE[name]×13 / DEFINITION-ORDER / PKG-ROOT[新4]×4 / ALL-UNCHANGED | — | — | **23** |
| `COMPAT-REJECTED-` | 存在・value・value 逆引き・category・action・message 非依存・**production 非生成** | — | — | **7** |
| `CLS-` | 12.5節の14ケース | 14 | 2 | **28** |
| `ORDER-` | 12.8.3節 | — | — | **11** |
| `E2E-` | `generate()` 経由（型・reason・message・marker 非露出） | 4 | 4 | **16** |
| `MSG-` | 4型の message 相互同一 / message 定数集合の不変 | — | — | **2** |
| `CHAIN-` | `__cause__` / `__context__` | 4 | 2 | **8** |
| `POLICY-` | CATEGORY[r]×13 / ACTION[r]×13 / COVERAGE-13 / SPLIT / SPLIT-TOTAL / NO-STRAY | — | — | **30** |
| `REJECTSET-` | EXACT / IS-FROZENSET / DISJOINT / UNION-COVERAGE / ALLOWLIST-SEMANTICS / IMMUTABLE | — | — | **6** |
| `CONT-` | SET-EXACT / SIZE-4 / ACTUAL-EXACTLY-4 / NEW-NONE[4]×4 / FAILED-COUNT-4 / IMMUTABLE | — | — | **9** |
| `ZERODIFF-` | ACTION-V622[9]×9 / CATEGORY-V622[9]×9 / SDK-ACTION[4]×4 / SDK-CATEGORY[4]×4 / PARTIAL-ENUM-ONLY | — | — | **27** |
| `RUNTIME-` | PROPAGATE[4型]×4 / CONTINUE-UNCHANGED[4reason]×4 | — | — | **8** |
| **`NOPARSE-`** | **FN-FOUND / PARAM-NAME / OCCURRENCE-COUNT-10 / ALLOWED-EQUALS-TOTAL / VIOLATIONS-EMPTY / SCOPE-FUNCTION-ONLY ＝6 ＋ 陽性対照16 ＋ 陰性対照4** | — | — | **26** |
| `SEC-` | VALUE-LABEL-SET / NO-SECRET[4]×4 / NO-RESPONSE-ATTR[4]×4 / EXC-ATTRS | — | — | **10** |
| `DEP-` | openai module / policy module / policy import root 完全一致 | — | — | **3** |
| `NOEXC-` | except 0件 / raise-from 0件 / class 集合不変 | — | — | **3** |
| `COMPAT-` | 周辺 Public API 不変12項目（signature は2本） | — | — | **13** |
| `NOIMPACT-` | 22パス×4検査＝88 ＋ COVERAGE 2 ＋ EXACT 2 ＋ TESTS-SCOPE 1 ＋ NO-UNTRACKED-TESTS 1 ＋ baseline 解決 1 ＋ 陽性対照 2 | 22 | 4 | **97** |
| `SOCKET-` | getaddrinfo 遮断 / connect 遮断 / 実 Client 非構築 | — | — | **3** |
| `ENV-` | 環境変数復元 / `os.environ` 全体不変 | — | — | **2** |
| | | | **合計 N** | **332** |

#### 12.8.3 反復数と assertion 数が一致しない箇所（R-e の適用）

| 識別子 | 反復回数 | assertion 数 | 理由 |
|---|---|---|---|
| `ORDER-FOUR-PERMUTATION-STABLE` | **24**（`itertools.permutations` による4型の全順列） | **1** | 24通りの分類結果を集約し、1回だけ比較する |
| `ORDER-MUTUAL-INDEPENDENT` | 16（4×4 の issubclass 行列） | **1** | 行列全体を単位行列と1回比較する |
| `ORDER-NOT-SUBCLASS-OF-PRIOR` | 24（4型 × 先行6型） | **1** | ヒット集合を空集合と1回比較する |
| `ORDER-PRIOR-NOT-SUBCLASS-OF-FOUR` | 24（先行6型 × 4型） | **1** | 同上 |
| `POLICY-SPLIT` | 13（全 reason の集計） | **1** | 集計結果の dict を1回比較する |
| `NOPARSE-VIOLATIONS-EMPTY` | 10（`exc` の Name 出現数） | **1** | violations リストを空リストと1回比較する |

`ORDER-` ブロックの内訳は次のとおり（合計11）。

```text
ORDER-TIMEOUT-IS-CONNECTION-SUBCLASS   1   H-4 の実測固定
ORDER-TIMEOUT-BEFORE-CONNECTION        1   O-1 回帰検出
ORDER-DIRECT-BASE[4型]                 4   __bases__ == (APIStatusError,)
ORDER-MUTUAL-INDEPENDENT               1   H-1
ORDER-NOT-SUBCLASS-OF-PRIOR            1   H-2
ORDER-PRIOR-NOT-SUBCLASS-OF-FOUR       1   H-3
ORDER-FOUR-PERMUTATION-STABLE          1   O-2（24反復 → 1 assertion）
ORDER-SERVER-ERROR-STABLE              1   O-4
```

### 12.9 部分実装・片側 rollback の検出（m-4 対応）

| 破損シナリオ | 検出器 | 挙動 |
|---|---|---|
| **Enum のみ追加・policy 未更新** | `ZERODIFF-SDK-CATEGORY[4型]` / `PARTIAL-ENUM-ONLY` / `REJECTSET-EXACT` / `POLICY-CATEGORY[新4値]` | category が `UNCLASSIFIED` へ落ち **4系統が同時 FAIL** |
| **policy のみ更新・Enum 未追加** | （独立 assertion を置かない） | `_REJECTED_REASONS` の定義時に `AttributeError` → **module import 段階でファイル全体が FAIL** |
| 分類分岐のみ実装・Enum 値名の綴り違い | `API-VALUE[name]` / `CLS-` | 個別 FAIL |
| CONTINUE 集合を誤って拡大 | `CONT-SET-EXACT` / `CONT-ACTUAL-EXACTLY-4` / `POLICY-SPLIT` | 3系統同時 FAIL |
| 例外引数の解析を実装へ混入 | `NOPARSE-VIOLATIONS-EMPTY` / `NOPARSE-ALLOWED-EQUALS-TOTAL` | 違反リストに行番号付きで現れる |

**「policy のみ更新」に独立 assertion を設けてはならない。** `_REJECTED_REASONS`
に列挙された時点で Enum member の存在は自明であり、それを検証する assertion は
**構造的に vacuous**（常に真）になる。検出手段は import 失敗であり、
これはファイル全体の FAIL として現れるため独立検証は不要である。

---

## 13. Formal Regression 計画

### 13.1 正式 Inventory

```text
既存25ファイル（v6.22.0 時点の正式 Inventory）
  test_e2e_v1_11_0_save_result.py
  test_e2e_v5_9_0_retry_runtime_loop_wiring_foundation.py
  test_e2e_v6_0_0_*.py 〜 test_e2e_v6_22_0_*.py
＋ 新規1ファイル
  test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py
= 正式 Inventory 26ファイル
```

各ファイルを**個別に**実行し、FAIL 0・SKIP 0・終了コード0・
外部 API 実接続0件・credential 使用0件・Git 状態不変を確認する。

```powershell
# 実行例（実装工程で使用。本設計工程では実行しない）
cd C:\Projects\claude-code-repository\projects\03_game_content_ai
.\venv\Scripts\python.exe tests\test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py
```

**bare `python`・別 venv の使用は禁止する。**

### 13.2 baseline への影響（既知差分の事前確定・F-2）

v6.22.0 時点の baseline は **3713 assertions（25ファイル）**。

#### 件数が変わらないファイル（24ファイル）

| ファイル | 変更 | 件数 |
|---|---|---|
| `test_e2e_v6_11_0_*.py` | `_err_cases` の4エントリの `_expected_reason` を差し替え。`check_openai_error()` は1エントリあたり4 assertion（型・reason・message・marker非露出）を出すが、**エントリ数もループ構造も変わらない** | **不変** |
| `test_e2e_v6_21_0_*.py` | allow-list リテラルとラベル文言のみ（GR-5） | **不変** |
| `test_e2e_v6_22_0_*.py` | allow-list リテラル・ラベル文言・コメント追記のみ（GR-5） | **不変** |
| 他21ファイル | 無変更 | **不変** |

#### 件数が変わるファイル（1ファイル）

`test_e2e_v6_19_0_*.py` は `_ALL_REASONS = list(OpenAIImageGenerationErrorReason)`
（L292）駆動のループを持つため、Enum 値追加により assertion が自動的に増える。

| 箇所 | 種別 | 増分 |
|---|---|---|
| L524 `for _reason in _ALL_REASONS:` の else 分岐 `CONT-NOT-CONTINUE[{name}]` | 自動増 | **+4** |
| L711 `for _reason in _ALL_REASONS:` の `REASON-MATCH[{name}]` | 自動増 | **+4** |
| L449 のループ（`decide()` を呼ぶだけで check がない） | 影響なし | 0 |
| L514 / L729 の内包表記 | 影響なし | 0 |
| **合計** | | **+8** |

**期待値のみ更新する assertion（件数不変・6件）**

| assertion | 変更 |
|---|---|
| `REASON-ENUM-COUNT` | 期待値 9 → **13**、ラベルの「9値」表記を更新 |
| `REASON-COVERAGE-COMPLETE` | `_expected_category_by_reason_name` へ**4キー追加**（すべて `IMAGE_GENERATION_REQUEST_REJECTED`）、ラベル更新 |
| `REASON-SPLIT-4-1-2-2` | 期待値 4/1/2/2 → **4/5/2/2**、ラベル本文のみ更新 |
| `REASON-SPLIT-TOTAL-9` | 期待値 9 → **13**、ラベル本文のみ更新 |
| `REASON-SPLIT-NO-STRAY-CATEGORY` | **変更不要**（category 集合は4種のまま） |
| `COMPAT-V611-REASON-COUNT-9` | 期待値 9 → **13**、ラベル本文のみ更新 |
| `CONT-EXACTLY-4` | **変更不要。期待値・実測値ともに4のまま PASS することが、CONTINUE 拡大がないことの直接証拠になる**（9.3節） |

#### 13.2.1 Scenario ID 据え置き方針（m-2 対応）

`REASON-SPLIT-4-1-2-2` / `REASON-SPLIT-TOTAL-9` / `COMPAT-V611-REASON-COUNT-9` は
**Scenario ID 自体に件数が埋め込まれている**。本Releaseの方針を次のとおり確定する。

```text
【方針】Scenario ID は据え置く。ラベルの説明本文のみを更新する。

根拠1  ID を改名すると Formal Regression の差分が「旧ID消失 ＋ 新ID出現」
       として現れ、件数が同じでも差分の解釈が難しくなる。
       13.2節が「+8 以外に変動なし」を宣言する方式と相性が悪い。
根拠2  GR-7（ラベルへ件数を埋め込まない）は 11章のとおり
       **baseline 固定 guard のラベル**に関する規則であり、
       behavioral assertion の既存 ID まで遡及改名する義務を課していない。
根拠3  v6.22 が既存E2Eを in-place 更新した precedent（期待値・ラベル・極性の
       差し替えのみでアサーション追加削除0件）と一致する。

【例外】11章で更新する v6.21／v6.22 の NOIMPACT guard のラベルからは、
       GR-7 に従い件数表現を除去する（こちらは guard のラベルであるため）。
```

`test_e2e_v6_11_0_*.py` の `ERR-BADREQ` / `ERR-NOTFOUND` / `ERR-CONFLICT` /
`ERR-UNPROCESSABLE` も同様に **ID 据え置き**とし、該当4行へ
「v6.23.0（DI-11 前半）により期待 reason を変更」のコメントを注記する（s-1）。
コメント追加は assertion 件数を変えない。

#### baseline の推移（Finalize で実測値へ更新）

```text
v6.22.0 時点（既存25ファイル）        : 3713   ← 引用値
v6.19 の構造的自動増                  :   +8   ← 実測値（254 → 262）
既存25ファイルの新 baseline            : 3721   ← 実測値
新規 v6.23 E2E（12.8.2節）            :  332   ← 実測値
─────────────────────────────────────────────
Formal Regression 総合                : 4053   ← 実測値
```

**+8 は本設計書が事前に宣言した既知差分である。** Formal Regression の実測により、
**これ以外の件数変動は1件も観測されなかった**（v6.11 = 248／v6.21 = 147／
v6.22 = 324 はいずれも件数不変。他21ファイルも v6.22 実績から変動なし）。
見込み値と実測値の乖離は **0件**であり、17章の rollback 条件はいずれも発火していない。

### 13.3 数値の区分（m-1 対応）

本設計書に現れる assertion 関連の数値を、根拠の強さで4区分する。
**この区分を混同して記載してはならない。**

| 区分 | 定義 | 該当する数値 |
|---|---|---|
| **実測値** | 本工程で `.\venv\Scripts\python.exe` またはソース読解により直接確認した値 | SDK 例外階層（H-1〜H-6）／現行 `exc` 出現数 **7**／改修後 **10**／陽性対照検出 **16/16**／陰性対照通過 **4/4**／v6.19 の `_ALL_REASONS` 駆動ループが **2箇所**であること／v6.21 guard **22×3**／v6.22 guard **22×4** |
| **引用値** | 過去 Release の Formal Regression 記録から引用した値。本工程では未実測 | 既存25ファイル baseline **3713**（v6.22 Formal Regression 実績） |
| **静的導出値** | ソース構造から機械的に確定でき、実行を要しない値 | v6.19 の増分 **+8** |
| **見込み値（当時）→ 実測値（Finalize で確定）** | 設計時点では算術的に導いた予測値。**Formal Regression で実測確認済み** | **3721** ／ **N = 332** ／ **4053** ／ 12.8.2節の各ブロック値（**20ブロックすべてが実測と一致**） |

**Finalize 時点の確定**：上記の見込み値はすべて Formal Regression（正式Inventory
26ファイル）で実測され、**乖離0件**であった。したがって本設計書に残る
**3721 ／ 332 ／ 4053 ／ 各ブロック値は、以後「実測値」として読むこと。**
17章 RB-1・RB-15 はいずれも発火していない。

### 13.4 GR-5 との関係（F-2 の解消）

GR-5（件数不変）は「**既存 guard の精緻化**はアサーション件数を変えない方法で行う」
という制約である。11.2節・11.3節の guard 更新は GR-5 を厳守する（件数不変）。

一方 v6.19 の +8 は guard の精緻化ではなく、**Public API（Enum 値）の拡張に対する
期待表駆動ループの自然な追随**である。これは GR-5 の対象ではない。
むしろ「新しい値が自動的に検証対象へ入る」ことは望ましい性質であり、
値を追加したのに件数が動かないほうが**網羅性の欠落を意味する**。

---

## 14. 受入条件（Acceptance Criteria）

### 14.1 taxonomy と分類

| ID | 条件 |
|---|---|
| **AC-1** | `OpenAIImageGenerationErrorReason` の member 数が **13** である |
| **AC-2** | 新4値の name が `BAD_REQUEST` / `RESOURCE_NOT_FOUND` / `CONFLICT` / `UNPROCESSABLE_ENTITY` である |
| **AC-3** | 新4値の value が `"bad_request"` / `"resource_not_found"` / `"conflict"` / `"unprocessable_entity"` である |
| **AC-4** | 既存9値の name・value・**定義順**が v6.22.0 時点と完全一致する |
| **AC-5** | `openai.BadRequestError` → `BAD_REQUEST` |
| **AC-6** | `openai.NotFoundError` → `RESOURCE_NOT_FOUND` |
| **AC-7** | `openai.ConflictError` → `CONFLICT` |
| **AC-8** | `openai.UnprocessableEntityError` → `UNPROCESSABLE_ENTITY` |
| **AC-9** | 既存6型（Authentication / PermissionDenied / RateLimit / APITimeout / APIConnection / InternalServer）の分類が不変 |
| **AC-10** | catch-all（bare `APIError` 等）と `except Exception` 経路が `UNKNOWN` のまま不変 |
| **AC-11** | `APITimeoutError` が `CONNECTION` へ誤分類されない（O-1 の回帰検出） |
| **AC-12** | 4型の判定順序を入れ替えても結果が同一である（O-2） |

### 14.2 後方互換

| ID | 条件 |
|---|---|
| **AC-13** | `REQUEST_REJECTED` が Enum に存続し、value が `"request_rejected"` のままである |
| **AC-14** | `REQUEST_REJECTED` を直接構築した場合の policy 出力が v6.22.0 時点と完全一致する |
| **AC-15** | `openai_image_generation.__all__` が **3 symbol のまま**である |
| **AC-16** | `OpenAIImageGenerationError.__init__` の parameter が `["self", "message", "reason"]` で、`reason` が**既定値を持たない**ままである |
| **AC-17** | `OpenAIImageGenerationError` の基底が `RuntimeError` のままである |
| **AC-18** | `image_generation_fallback_policy.__all__` が4 symbol のまま、`decide_image_generation_fallback()` の signature が `(error)` のままである |

### 14.3 全数写像と Zero Diff

| ID | 条件 |
|---|---|
| **AC-19** | **13値すべて**について category が 7.5.1節の表と一致する |
| **AC-20** | **13値すべて**について action が 7.5.1節の表と一致する（**Z-1**） |
| **AC-21** | 新4値の category が `IMAGE_GENERATION_REQUEST_REJECTED`、action が `PROPAGATE_ORIGINAL_ERROR` である |
| **AC-22** | 分割が 4 / 5 / 2 / 2 = 13 である |
| **AC-23** | `_CONTINUABLE_REASONS` が4値のまま不変である（**Z-8**） |
| **AC-24** | CONTINUE となる reason が正確に4値ちょうどである（`CONT-EXACTLY-4` が期待値変更なしで PASS） |
| **AC-25** | `_CONTINUABLE_REASONS` ∩ `_REJECTED_REASONS` = ∅ である |
| **AC-26** | `ImageGenerationFailureCategory` が5値、`ImageGenerationFallbackAction` が2値のまま不変である |
| **AC-27** | 4型経由の message が v6.22.0 時点の文字列と1文字も違わない（**Z-4**） |
| **AC-28** | 4型経由の例外の `__cause__` / `__context__` がいずれも `None` である（**Z-5**） |
| **AC-29** | `main.py` の baseline commit（`8fd8453`）からの差分が**空**である（**Z-3**） |
| **AC-30** | 成功経路（`GeneratedImage` 生成）が不変である（**Z-7**） |

### 14.4 Security / 解析禁止

| ID | 条件 |
|---|---|
| **AC-31** | **（本改訂で全面差し替え）** `_classify_api_error()` の関数本体において、例外引数の Name 出現が **`isinstance(<exc>, ...)` の第1引数の形のみ**であり、それ以外の出現が **0件**である（I-EXC-1・7.8.2節。AST 検査） |
| **AC-31a** | 例外引数名が **AST の第1 positional parameter から決定**されており、テスト側にハードコードされていない |
| **AC-31b** | 当該関数内の例外引数 Name 出現数が **10** であり（7.3節の10段判定と一致）、その **全件**が allow 形である（allow 数 == 出現総数） |
| **AC-31c** | 陽性対照 **16形**（12.6.2節 P-1〜P-16）が**それぞれ独立に**違反として検出される。とくに **P-3（未知属性）** と **P-15（`isinstance` 第2引数）** が検出される |
| **AC-31d** | 陰性対照 **4形**（12.6.3節 N-1〜N-4）がいずれも違反0件で通過する。とくに **N-1 `isinstance(exc, openai.BadRequestError)` が違反にならない** |
| **AC-31e** | 設計書・テストのいずれにも **禁止属性の列挙（`_FORBIDDEN_ATTRS` 等）が存在しない**。属性名に依存した検査を実装してはならない |
| **AC-32** | 上記 AST 検査が module 全体ではなく `_classify_api_error()` の `ast.FunctionDef` 本体のみを対象としている（`NOPARSE-SCOPE-FUNCTION-ONLY` で対象範囲自体を検証する） |
| **AC-33** | 13値の value が固定ラベル集合と一致し、URL・credential・prompt・応答本文を含まない |
| **AC-34** | provider 例外へ埋め込んだ secret marker が message・repr・args・`__dict__` のいずれにも露出しない |
| **AC-35** | 全テストが hermetic であり、socket 遮断下で完走する |

### 14.5 guard / Regression

| ID | 条件 |
|---|---|
| **AC-36** | v6.21 guard の `BASELINE_COMMIT` と `_protected_paths` が変更されていない（GR-1・GR-2） |
| **AC-37** | v6.22 guard の `BASELINE_COMMIT` と `_protected_paths` が変更されていない（GR-1・GR-2） |
| **AC-38** | 両 guard の allow-list に登録されたファイルが、本設計書 10章が宣言した2ファイルのみである（GR-4） |
| **AC-39** | 両 guard の更新でアサーション件数が変化していない（GR-5） |
| **AC-40** | v6.23 guard が baseline `8fd8453` を固定し、equality（containment ∧ coverage）を検査している（GR-6） |
| **AC-41** | `NOIMPACT-TESTS-SCOPE` 系のラベルに件数表現が残っていない（GR-7） |
| **AC-42** | Formal Regression が正式 Inventory 26ファイルで FAIL 0・SKIP 0 である |
| **AC-43** | 既存25ファイルの合計が **3721**（3713 + 8）であり、13.2節が宣言した以外の件数変動がない |
| **AC-44** | `tests/test_e2e_v6_22_0_*.py` へ S2R-1 の説明コメントが追記され、アサーション・検査ロジックが変更されていない |

### 14.6 テスト契約（Test Review Findings 由来）

| ID | 条件 |
|---|---|
| **AC-45** | `CLS-` が **14ケース**で実装され、うち #11（`APIStatusError` status 400）が `UNKNOWN` になる（**HTTP ステータス値では分類しない**ことの behavioral 証明。M-1） |
| **AC-46** | `CLS-` #12〜#14（`APIStatusError` status 500／bare `APIError`／`APIResponseValidationError`）がいずれも `UNKNOWN` になる |
| **AC-47** | 新規 E2E の private import が 12.7節の契約どおりである（m-3） |
| **AC-48** | 「policy のみ更新・Enum 未追加」を検証する**独立 assertion が存在しない**（vacuous 回避。m-4）。当該破損は module import 失敗として現れる |
| **AC-49** | v6.19 の Scenario ID が据え置かれ、ラベル本文のみが更新されている（m-2・13.2.1節） |
| **AC-50** | `test_e2e_v6_11_0_*.py` の該当4行へ変更理由のコメントが注記され、Scenario ID が据え置かれている（s-1） |
| **AC-51** | 12.8.3節が列挙する6箇所で、**反復回数と assertion 数の差**が設計どおりである（s-2） |
| **AC-52** | 新規 E2E の assertion 総数が **332**（見込み値）と一致する。乖離した場合は原因を特定するまで Release を進めない（13.3節） |

---

## 15. リスク

| ID | Risk | Severity | Mitigation |
|---|---|---|---|
| **R-1** | policy を更新し忘れ、新 reason が `UNCLASSIFIED` へ落ちて category が静かに変わる | **中** | 7.5節で写像を全数表として固定。AC-19〜AC-21 と `POLICY-` / `ZERODIFF-ACTION-` prefix が13値すべてを機械検証する。9.2節 段2 が論証の中核であることを明記 |
| **R-2** | SDK 更新により4型の継承関係が変わり、判定順序に依存が生じる | 中 | H-1〜H-3 を venv 実測として 3.2節へ記録。`ORDER-FOUR-INDEPENDENT`（O-2）が「順序自由」を毎回実測し、崩れた瞬間に FAIL する |
| **R-3** | `REQUEST_REJECTED` が production から到達不能になることを「削除された」と誤解される | 中 | 7.4節で「削除しない・value 不変・外部構築時の挙動不変」を明示。`COMPAT-REJECTED-` prefix が存続を毎回確認。ROADMAP・CHANGELOG でも同じ表現を使う |
| **R-4** | 「Production Behavior Zero Diff」と誤って表現し、`.reason` の変更が見落とされる | **中** | 9.1節で主張する Zero Diff を Z-1〜Z-8 として列挙し、Production Behavior Zero Diff は**成立しない**と明記。9.5節で Release Review・CHANGELOG での表現まで指定 |
| **R-5** | message 凍結により `RESOURCE_NOT_FOUND` の message が意味的に不正確なまま残る | 低〜中 | 7.6節 IL-1 として明示的に受容。reason が正確になることで構造的に補償される。改訂は DEF-6.23-1 |
| **R-6** | v6.19 の assertion 増（+8）が「Regression の隠蔽」と誤読される | 低〜中 | 13.2節で増分の内訳を assertion 単位・行番号付きで事前確定。GR-5 の適用範囲との違いを明示（F-2）。増えるのは**新しい値に対する新しい検証**であり、既存検証は1件も減らない |
| **R-7** | guard allow-list の更新漏れ（2 guard × 2 path） | 中 | 11.2節・11.3節に更新内容を逐語的に記載。AC-36〜AC-41 で機械検証。GR-9 が「Release ごとに対象が1件増える」と予告済み |
| **R-8** | `NOPARSE-` を module 全体へ適用して既存の正当な処理を壊す | 中 | 7.8.4節・12.1節で「`_classify_api_error()` の `ast.FunctionDef` 本体のみ」と明記し、AC-32 で対象範囲自体を検証する。**実測で偽陽性の具体例を提示済み**（`generate()` で3件・`_build_generated_image()` で1件）。v6.22 が同じ罠を踏んだ precedent も明示 |
| **R-15** | **（本改訂追加：再判定 Major 対応）** positive allow-list 方式の guard が過剰に厳しく、正当な実装形まで拒否する | **低** | (a) 現行実装が **7/7 allow・違反0件**、改修後の想定形が **10/10 allow・違反0件**であることを venv 実測で確認済み（7.8.5節）。**余白ゼロで適合**しており、新たな制約を課していない。(b) 陰性対照4形（12.6.3節）が「正当形を拒否しない」ことを毎回検証する。(c) 将来 allow-list 外の記述が正当に必要になった場合は、guard を緩めるのではなく **I-EXC-1 の契約自体を Architecture Review にかけて見直す**（v6.22 R-12 と同じ運用） |
| **R-16** | **（本改訂追加）** 分割リテラルや動的属性名（`getattr(exc, name_var)`）等の難読化により allow-list を迂回される | **低（受容）** | `getattr(exc, ...)` は第1引数に `exc` の Name が現れるため **allow 形ではなく違反として検出される**（P-5 で実証済み）。真に検出不能なのは `exc` を一切名指ししない形のみであり、その場合は分類自体が成立しない。v6.22 R-14 と同じく、**本guardの脅威モデルは偶発的な解析混入の防止であり、意図的な難読化の防止ではない**ことを明示して受容する |
| **R-17** | **（本改訂追加）** 見込み値 `N = 332` と Formal Regression の実測値が乖離する | 中 | 12.8節で数え方 R-a〜R-e とブロック別内訳を事前確定し、12.8.3節で反復数と assertion 数が一致しない6箇所を明示した。乖離時は AC-52・RB-15 により Release を停止し原因を特定する |
| **R-9** | Content Policy 拒否が `BAD_REQUEST` に含まれることを「Content Policy を分類できた」と誤解し、将来 CONTINUE 対象へ入れてしまう | **中** | 5章 N-1・7.1.1節で「400 には Content Policy 拒否とパラメータ不正の両方が含まれる」ことを明記。7.1.1節の表を non-normative と宣言。CONTINUE 拡大は ORD-3 の領域であり人間の明示承認が必要（N-2） |
| **R-10** | 4型を独立 `isinstance` へ展開する際、既存タプル判定の位置を動かしてしまう | 低 | 7.3節で「位置は現行と同一（5 と 10 の間）」を contract 化。`ORDER-SERVER-ERROR-STABLE`（O-4）が `InternalServerError` の分類不変を確認 |
| **R-11** | 実装工程で allow-list を「実装の都合」で拡張する | 低 | GR-4 を 11.1節に再掲。AC-38 が「10章が宣言した2ファイルのみ」を検証する |

---

## 16. Deferred Items

| ID | 内容 | 引継ぎ先 |
|---|---|---|
| **DEF-6.23-1** | `RESOURCE_NOT_FOUND` 等の message 改訂（IL-1 の是正）。利用者可視テキストの変更であり独立した Architecture Review を要する | 将来Release |
| **DEF-6.23-2** | 新 reason の一部（`CONFLICT` 等）を `CONTINUE_WITHOUT_FEATURED_MEDIA` へ拡大するか否かの判断。**ORD-3 の領域**であり、DI-5 の運用データと人間の明示承認が前提 | 将来Release（ORD-1／ORD-3 の正式再評価が必要） |
| **DEF-6.23-3** | **DI-11 後半**：`UNKNOWN` の2経路分離（`APIError` catch-all と `except Exception`） | DI-11 後半 |
| **DEF-6.23-4** | **DI-11 後半**：`INVALID_RESPONSE` の細分化（単発破損 vs スキーマ変更） | DI-11 後半 |
| **DEF-6.23-5** | **M5-1**：match-case class pattern を `GUARD-WMUE-CONSTRUCTION-SHAPE` の allow-list へ含めるか否か。本Releaseでは判断機会が発生しない（11.6節） | 当該 guard の検査ロジックを変更する Release |
| **DEF-6.23-6** | Content Policy 拒否の判別（`CONTENT_POLICY_REJECTED` の新設）。response body の `code` 解析を要し、解析禁止 contract（G-8）に抵触する | 解析禁止 contract の見直しを伴う独立検討（v6.22 DEF-6.22-13 と同型の論点） |
| **DEF-6.23-7** | `status_code` を属性として公開すること（N-7） | 必要性が生じた時点で独立判断 |
| **DEF-6.23-8** | reason を構造化ログ／metrics へ記録すること | DI-5 |
| **DEF-6.23-9** | zero-diff guard の共有レジストリ化（v6.22 DEF-6.22-14 の継続。本Releaseで allow-list を更新する guard が2件になり、GR-9 の O(N) 保守コストが顕在化し始めた） | 将来Release（テスト基盤の構造変更を伴う） |
| **DEF-6.23-10** | **（本改訂追加）** positive allow-list 方式の NOPARSE guard を、`_validate_response_structure()` 等の**他の入力受け取り関数へも展開**するか。それらの関数は response を正当に解析するため、allow-list の形が `_classify_api_error()` とは異なる。本Releaseの関心（reason 分類）から外れるため対象外とする | 将来Release（各関数ごとに正当な使用形の定義を要する） |
| **DEF-6.23-11** | **（本改訂追加、m-2 の継続）** v6.19 の件数埋め込み Scenario ID（`REASON-SPLIT-4-1-2-2` / `REASON-SPLIT-TOTAL-9` / `COMPAT-V611-REASON-COUNT-9`）を件数非依存 ID へ改名するか。本Releaseでは差分読解性を優先して**据え置き**とした（13.2.1節） | 将来Release（大規模なテスト改修の機会に再検討） |
| **DEF-6.23-12** | **（Finalize 追加、Release Review Minor RR-M-1 対応）** `tests/test_e2e_v6_23_0_*.py` の NOIMPACT 陽性対照2件（`NOIMPACT-POSITIVE-EMPTY-ALLOWLIST` / `NOIMPACT-POSITIVE-UNCHANGED-ALLOWLIST`）を、**実 `_changed`（`git diff` 出力）および実 allow-list 値に基づく検証へ置き換えるか**を判断する。現状はハードコードされたリテラル集合のみの集合演算であり無条件で PASS する。**guard 本体の vacuous-pass 防御は `NOIMPACT-SCOPE-COVERAGE`／`NOIMPACT-SCOPE-EXACT`（実 `git diff` 出力に対する coverage・equality）が担っており、保証水準は損なわれていない。** ラベルが実態より強い主張をしている点のみが問題であるため、**本Releaseでは修正しない**（Production behavior・安全性・Runtime Action Zero Diff への影響が一切ないこと、および Release Review が「修正は不要」と明示したことによる） | 将来Release（**次に v6.23 の NOIMPACT guard へ触れる Release** で判断。ラベルの実態化、または実値ベース検証への置換のいずれかを選ぶ） |

### 16.1 v6.22 から継承した Deferred の処理結果

| 継承項目 | 本Releaseでの扱い |
|---|---|
| **S2R-1（DEF-6.22-15）** | **完了（Finalize 時点で確定）**。`tests/test_e2e_v6_22_0_*.py` L546-547 付近へ説明コメントを追記した。Release Review が **`_scan_noparse_violations` の AST が HEAD と完全一致**することを確認しており、検査ロジック・`_FORBIDDEN_ATTRS`・assertion 件数はいずれも不変（11.5節） |
| **M5-1** | **Deferred 継続**（11.6節・DEF-6.23-5）。本Releaseは構築形 guard を必要とせず、判断機会が発生しなかった |
| **DI-11** | **前半を本Releaseで完了。後半は DEF-6.23-3／DEF-6.23-4 として継続** |
| **DI-6 / DI-7 / DI-8 / DI-9** | 本Release対象外。ROADMAP の記録を維持（状態変更なし） |
| **DEF-6.22-1（WP 一過性失敗の CONTINUE 拡大）** | 本Release対象外。DI-5 の運用データを待つ（状態変更なし） |

### 16.2 本改訂で破棄した Deferred

| ID | 内容 | 破棄理由 |
|---|---|---|
| **DEF-TR-1** | `_FORBIDDEN_ATTRS` へ provider 固有属性（`code` / `param` / `type` / `request` / `request_id`）を追加するか | **論点ごと消滅した。** 本改訂で禁止属性の列挙方式（deny-list）を廃止し、positive allow-list 方式へ転換したため、「どの属性を列挙に加えるか」という問い自体が成立しなくなった（0.5.1節・7.8節）。属性名は guard の関心事ではない |
| **DEF-TR-2** | Scenario ID の件数埋め込み問題 | **破棄ではなく DEF-6.23-11 へ移管**（16章本表）。本Releaseの方針は 13.2.1節で確定済み |

---

## 17. Rollback 条件

実装工程・Regression 工程で以下のいずれかが観測された場合、**Release を中止し
人間の指示を仰ぐ**。ツールが自動で復旧操作を行ってはならない
（`reset` / `checkout` / `restore` / `clean` / `stash` はいずれも人間の明示指示による）。

| ID | 中止条件 |
|---|---|
| **RB-1** | 13.2節が宣言した既知差分（v6.19 の +8）以外の assertion 件数変動が観測された |
| **RB-2** | Formal Regression に FAIL が1件でも残る（既知差分として説明できないもの） |
| **RB-3** | 13値のいずれかで **action が v6.22.0 時点と異なる**（Z-1 違反） |
| **RB-4** | 13値のいずれかで **category が 7.5.1節の表と異なる**（Z-2 違反） |
| **RB-5** | `_CONTINUABLE_REASONS` の内容が変わった／CONTINUE となる reason が4値でなくなった（Z-8・G-5 違反） |
| **RB-6** | `main.py` に差分が生じた（Z-3 違反） |
| **RB-7** | いずれかの message が1文字でも変わった（Z-4 違反） |
| **RB-8** | `__cause__` / `__context__` の到達可能性が変わった（Z-5 違反） |
| **RB-9** | 既存9値の name・value・定義順のいずれかが変わった（AC-4 違反） |
| **RB-10** | `REQUEST_REJECTED` が削除された／value が変わった（AC-13 違反） |
| **RB-11** | いずれかの `__all__` が変わった（AC-15・AC-18 違反） |
| **RB-12** | guard の `BASELINE_COMMIT` または `_protected_paths` が変更された（GR-1・GR-2 違反） |
| **RB-13** | allow-list に 10章が宣言していないファイルが登録された（GR-4 違反） |
| **RB-14** | テストが実ネットワーク・実 API へ到達した（hermetic 違反） |
| **RB-15** | **（本改訂追加）** 新規 E2E の assertion 実測値が見込み値 **332** と乖離し、12.8.2節の内訳で説明できない |
| **RB-16** | **（本改訂追加）** `NOPARSE-` の違反が1件でも検出された（例外引数が `isinstance` 第1引数以外の形で使われた。I-EXC-1 違反） |
| **RB-17** | **（本改訂追加）** 陽性対照16形のいずれかが検出されない、または陰性対照4形のいずれかが違反として誤検出された（guard の検出力・非過剰性の破れ） |
| **RB-18** | **（本改訂追加）** 実装またはテストに禁止属性の列挙（`_FORBIDDEN_ATTRS` 相当）が復活した（AC-31e 違反） |

**部分 rollback の可否**：`_REJECTED_REASONS` の導入（policy 変更）のみを取り消して
v6.11 の変更だけを残すことは **禁止する**。9.2節 段2 が破れ、Z-2 が成立しなくなるためである。
本Releaseの2つの Production 変更は**不可分**である。

---

## 18. Architecture Review 論点への回答一覧

| # | 論点 | 回答 | 節 |
|---|---|---|---|
| 1 | reason 名・value 文字列・分類粒度 | `BAD_REQUEST` / `RESOURCE_NOT_FOUND` / `CONFLICT` / `UNPROCESSABLE_ENTITY`。value は lower_snake。SDK 型と1対1の粒度（A-1 採用） | 6.1・7.1 |
| 2 | SDK 例外の継承関係と安全な判定順序 | venv 実測により4型は `APIStatusError` の直接サブクラスで**相互独立**（H-1〜H-3）。順序自由だが現行位置を維持し O-1〜O-4 として contract 化 | 3.2・7.3 |
| 3 | `REQUEST_REJECTED` を削除せず残す設計 | Enum member・value ともに存続。production から到達不能になるだけ。外部構築時の挙動は完全に不変 | 7.4 |
| 4 | 既知4例外型 → 新 reason の対応表 | 7.1節・7.3節の表で確定 | 7.1・7.3 |
| 5 | fallback policy の全数写像 | `_REJECTED_REASONS` allow-list を新設し、新4値＋`REQUEST_REJECTED` を `IMAGE_GENERATION_REQUEST_REJECTED` ＋ `PROPAGATE_ORIGINAL_ERROR` へ写像。13値の全数表を確定 | 7.5・7.5.1 |
| 6 | Runtime action Zero Diff / main.py Zero Diff / CONTINUE 拡大なし | Z-1・Z-3・Z-8 として個別定義し、3段の論証と機械検証（AC-20・AC-23・AC-24・AC-29）で保証 | 9.1〜9.4 |
| 7 | public `.reason` は意図的に変わるため Production Behavior Zero Diff と表現しない | 9.1節の表で「成立しない」と明記。Release Review・CHANGELOG での表現まで指定 | 9.1・9.5 |
| 8 | message・chaining・成功経路・public signature 不変 | Z-4〜Z-7。message は4型すべて凍結（IL-1 を受容） | 7.6・8.2・9.1 |
| 9 | `UNKNOWN` / `INVALID_RESPONSE` / body 解析 / content policy 判定は非スコープ | N-1・N-3・N-4・N-5。DI-11 後半と DEF-6.23-6 へ | 5章 |
| 10 | v6.21／v6.22 guard の GR-1〜GR-11 に基づく更新 | 更新対象は2 guard（3.6節で全数確認）。baseline・保護パスは不変、allow-list とラベルのみ更新（件数不変）。v6.23 自身の guard を GR-6 に従い新設 | 11.1〜11.4 |
| 11 | S2R-1 は対象 test 変更時の説明追記として解消可 | **解消する。** 11.3節により v6.22 test を必ず変更するため、DEF-6.22-15 が想定した機会に該当。コメント追記のみ・件数不変 | 11.5 |
| 12 | M5-1 は必要な場合だけ判断し、不要なら Deferred 継続 | **判断機会が発生しないため Deferred 継続。** 本Releaseは構築形 guard を必要としない（`reason` が必須引数のため） | 11.6・12.4 |
| 13 | 想定変更ファイル・E2E 契約・Formal Regression 計画・rollback 条件 | 10章・12章・13章・17章 | — |

### 18.1 Test Review 論点への回答一覧

| 論点 | 回答 | 節 |
|---|---|---|
| 新規 E2E のテスト項目・識別子・期待値 | 20ブロック・**N = 332**（見込み値）。ブロック別内訳を確定 | 12.8.2 |
| 対象4例外型の統合対応表（前後 reason／category／action／message／chaining） | 1つの表で確定。**変化するのは reason の1列のみ** | 7.1・7.3・12.5 |
| 外部構築 `REQUEST_REJECTED` の写像契約 | `COMPAT-REJECTED-` 7 assertion。production 非生成も固定 | 7.4・12.8.2 |
| Enum 全13値の value・重複なし・API 互換性 | `API-` 23 assertion（`API-VALUE-UNIQUE` / `API-DEFINITION-ORDER` / `API-ALL-UNCHANGED`） | 7.1・12.8.2 |
| SDK 例外階層・判定順序 contract | `ORDER-` 11 assertion。24順列の集約検証を含む | 3.2・7.3・12.8.3 |
| `_REJECTED_REASONS` の完全一致 allow-list | `REJECTSET-` 6 assertion（EXACT / DISJOINT / ALLOWLIST-SEMANTICS） | 7.5・12.8.2 |
| CONTINUE 集合の非拡大の直接証拠 | `CONT-` 9 assertion ＋ v6.19 `CONT-EXACTLY-4` が**期待値変更なしで PASS** | 9.3・13.2 |
| v6.19 の +8 の内訳 | 行番号付きで確定（L524 の else 枝 +4・L711 +4） | 13.2 |
| 3713 → 3721 の妥当性 | 走査 methodology と4区分で論証 | 13.2・13.3 |
| `N` と Formal Regression 総数 | **N = 332** / 総数 **4053**（いずれも見込み値） | 12.8.2・13.2 |
| v6.21／v6.22 guard の allow-list 更新と件数不変 | 22×3 = 67 / 22×4+4 = 92 のいずれも不変 | 11.2・11.3 |
| v6.23 自前 baseline 固定 guard | baseline `8fd8453`・equality 2パス・陽性対照2本 | 11.4 |
| S2R-1 のコメント追記が件数を変えないこと | コメント行のみ。assertion 差分 0 | 11.5 |
| SOCKET／外部 API 通信0件 | `SOCKET-` 3 assertion ＋ hermetic 要件 | 12.2・12.8.2 |
| 部分実装・片側 rollback の検出 | 検出器一覧を確定。vacuous な assertion を置かない | 12.9 |
| 不足・矛盾・過剰・脆弱性 | 削除4件（過剰）・追加2件（不足）を反映。脆弱性は HEAD 固定を前提条件化 | 12.8.2・11.4 |
| **再判定 Major（NOPARSE の deny-list 方式）** | **positive allow-list 方式へ転換。属性名を列挙せず、未知属性を自動禁止** | **7.8・12.6** |

---

## 19. 用語・参照

| 参照先 | 内容 |
|---|---|
| `docs/ROADMAP.md` L1146-1151 | DI-11 の正式定義（次候補・未着手） |
| `docs/design/image_generation_fallback_policy_foundation.md` §10.6 C-9/C-10・§10.7 C-17/C-20・§10.8 ORD-1〜ORD-4・§20 DI-11・§22 R-4 | DI-11 の正式化・CONTINUE allow-list の設計・可用性トレードオフの受諾 |
| `docs/design/wordpress_media_upload_failure_reason_classification_foundation.md` §11.8 GR-1〜GR-11・§17 prefix 構成・§19 DEF-6.22-8/DEF-6.22-15・§20 R-8 | guard 運用の一般則・reason 分類の precedent・S2R-1 の記録 |
| `docs/design/openai_image_generation_adapter_foundation.md` | v6.11（本Releaseの変更対象）の原設計 |
| `docs/design/article_featured_media_runtime_wiring.md` §18・§19 | v6.21 の observability contract・恒久 guard 方式 |
| `src/openai_image_generation/openai_image_generator.py` L56-79・L94-146・L292-312 | 変更対象（Enum・分類関数・generate()） |
| `src/image_generation_fallback_policy/image_generation_fallback_policy.py` L87-96・L136-157 | 変更対象（allow-list・分岐） |
| `src/article_featured_media_runtime/article_featured_media_runtime.py` L118-134 | PROPAGATE 時に result を生成しないことの根拠 |
| `main.py` L182-193 | CONTINUE 経路のみが category を出力することの根拠 |
| `tests/test_e2e_v6_11_0_*.py` L292-313（Fake 構築）・L1073-1100（`_err_cases`） | 更新対象と Fake 例外構築の precedent |
| `tests/test_e2e_v6_19_0_*.py` L292・L505-540・L688-770・L1282-1295 | 更新対象（`_ALL_REASONS` 駆動ループ・期待表・COMPAT） |
| `tests/test_e2e_v6_21_0_*.py` L824-946 | 更新対象（baseline `8d89506` の NOIMPACT guard） |
| `tests/test_e2e_v6_22_0_*.py` L1006-1190 | 更新対象（baseline `578af6b` の NOIMPACT guard）・S2R-1 の対象箇所 |
| openai 2.46.0（project venv）例外階層 | H-1〜H-6 の実測根拠（`.\venv\Scripts\python.exe` による読み取り専用調査） |
| openai 2.46.0 `APIError` / `APIStatusError` / `APIResponseValidationError` の `__init__` | 12.5節 catch-all 4ケースの構築可能性の実測根拠 |
| openai 2.46.0 `BadRequestError` インスタンスの `vars()` | 7.8.1節の実測根拠（`body` / `code` / `message` / `param` / `request` / `request_id` / `response` / `status_code` / `type` の9属性を保持） |
| `src/openai_image_generation/openai_image_generator.py` `_classify_api_error()` の AST | 7.8.5節の実測根拠（現行7出現・全件 allow・違反0件） |
| `src/openai_image_generation/openai_image_generator.py` L296・L302・L312／L170 | 7.8.4節の実測根拠（`generate()` の `self` 3件・`_build_generated_image()` の `response` 1件。無差別適用時の偽陽性） |
| v6.22 設計書 §17.1 `GUARD-WMUE-CONSTRUCTION-SHAPE`（Architecture Amendment 3・M3-1） | 7.8.1節：deny-list → occurrence-context allow-list への方式転換の precedent |

---

**本設計書は Architecture Review 完了時点の確定版である。
人間による独立承認を経るまで、Production Implementation へ進んではならない。**
