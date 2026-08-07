# OpenAI Image Generation Unknown and Invalid Response Reason Refinement Foundation

**Release: v6.24.0（DI-11 後半）**

Deferred Item: **DI-11 OpenAI Image Generation Request Rejection Reason Refinement**（後半＝
`UNKNOWN` の2経路分離および `INVALID_RESPONSE` の細分化）

---

## 0. Status

本設計書は**全23セクション（第0章〜第22章）**で構成される。

| 項目 | 値 |
|---|---|
| 工程 | **Architecture Design 作成完了（Architecture Review Required Amendments・Minor Amendments・Production実装前Gate の Required Amendment をいずれも反映済み。Production Implementation・限定テスト・Formal Regression・Documentation Integration もいずれも完了）。Release Review はFindings Amendment（第5回改訂）反映後、Minor-N1反映（第6回改訂）を経て再々確認で**Approved with Suggestions**が確定し、Code Reviewも**Approved with Suggestions**。人間による設計・実装・E2E・文書の最終承認も完了（19.8節・第7回改訂・本改訂）** |
| 分類 | **Architecture Release**（[development_workflow.md](../development_workflow.md) 6章） |
| Architecture Review Verdict | **Approved with Minor Amendments**（Required Amendments 8件は設計書初版作成時に反映済み。Minor 3件・Suggestion 1件・実装前必須Gate 1件を第1回改訂で反映済み。0.4節・0.5節・19章） |
| Production実装前Gate | **Gate 1／2／4／5：PASS。Gate 3：Required Amendment 1件を第2回改訂で反映しPASS。総合：Production実装へ進行可能（0.6節・19.3節）** |
| Test Review | **未実施** |
| Production Implementation | **完了**（Production 1ファイルのみ。設計書外の別工程で実施。0.7節） |
| 限定テスト | **完了**（既存5ファイル＋新規1ファイル、**1678/1678 PASS**・FAIL 0・SKIP 0・全終了コード0。設計書外の別工程で実施し、前回改訂で実測値を反映。0.7節・19.4節） |
| Formal Regression | **完了**（正式Inventory**27ファイル、4418/4418 PASS**。既存26ファイル4072/4072 PASS＋新規v6.24.0 346/346 PASS。FAIL 0・SKIP 0・全ファイル終了コード0・外部API実接続0件。設計書外の別工程で実施し、第4回改訂で実測値を反映。0.8節・19.5節） |
| Release Review | **最終Verdict：Approved with Suggestions（Blocking 0／Major 0／Minor 0／Suggestion 6）。** 初回（Changes Required：Major 2／Minor 3／Suggestion 4）→ Findings Amendment反映（第5回改訂）→ 再確認（Minor-N1・2箇所検出）→ Minor-N1反映（第6回改訂）→ 再々確認（Approved with Suggestions確定）という経緯（19.6節〜19.8節） |
| Code Review | **完了。Verdict：Approved with Suggestions（Blocking 0／Major 0／Minor 0／Suggestion 7、うちs-7が新規検出）（19.8節）。Finalizeでs-6を解消したため、現在残存する非ブロッキングSuggestionは6件（s-1〜s-5、s-7）である。Code Review時点のVerdictおよび件数は履歴として維持する** |
| 人間の最終承認 | **完了**（設計・実装・E2E・文書。19.8節・22章） |
| 次工程 | **commit／push のみ**（本改訂時点ではいずれも未実施） |
| Source of Truth | 本ファイル |

### 0.1 Repository 開始状態（読み取り専用コマンドで実測）

```text
branch          : main
local HEAD      : 38e2487db5760034f4a994319350244960a42e1b
origin/main     : 38e2487db5760034f4a994319350244960a42e1b
ahead / behind  : 0 / 0
Working Tree    : clean（git status --porcelain 出力なし）
stash           : なし
直前Release     : 6.23.0（OpenAI Image Generation API Rejection Reason Classification Foundation）
Formal Regression baseline : 正式Inventory 26ファイル / 4053 assertions PASS
```

`git fetch` / `git pull` は実行していない。上記はすべてローカル参照のみによる実測値である。

### 0.2 本工程で変更したファイル

| 工程 | ファイル | 変更 |
|---|---|---|
| **Architecture Design（初版）** | `docs/design/openai_image_generation_unknown_and_invalid_response_reason_refinement_foundation.md` | **新規作成** |
| **第1回改訂：Architecture Review Minor Amendments 反映** | 同上 | **改訂**（Minor 3件・Suggestion 1件・実装前必須Gate 1件を反映。確定済みの reason taxonomy・Acceptance Criteria・Runtime Action Zero Diff（Z-1〜Z-8）・Deferred 方針はいずれも変更していない。0.5節） |
| **第2回改訂：Production実装前Gate 確認・Required Amendment 反映** | 同上 | **改訂**（Gate 1／2／4／5 PASS、Gate 3 由来 Required Amendment 1件を反映。I-VAL-1 条件(a)を外部応答値スコープへ限定。旧U-1・旧U-2を解消、旧U-6を実測完了。確定済みの reason taxonomy・分類経路・Acceptance Criteria の実質要件・Runtime Action Zero Diff（Z-1〜Z-8）・Deferred 方針はいずれも変更していない。0.6節） |
| **第3回改訂：E2E限定テスト実測結果の反映** | 同上 | **改訂**（Production Implementation・E2E限定テストは別工程で実施済み。実測結果（既存5ファイル+新規1ファイル、1678/1678 PASS）を設計書へ反映するのみで、新たな実装・新たなテスト実行は行っていない。v6.23追随を宣言値+3から実測値+9へ訂正。確定済みの reason taxonomy・分類経路・Acceptance Criteria の実質要件・Runtime Action Zero Diff（Z-1〜Z-8）・Deferred 方針はいずれも変更していない。0.7節） |
| **第4回改訂：Formal Regression 実測反映・Documentation Integration** | 同上 | **改訂**（Formal Regression は別工程で実施済み。実測結果（27ファイル・4418/4418 PASS）を設計書へ反映し、U-5 を解消。あわせて `docs/ROADMAP.md`・`docs/CHANGELOG.md`・`docs/architecture.md` の3文書へ正式実績を反映（Documentation Integration）。新たな実装・新たなテスト実行・commit・push は行っていない。確定済みの reason taxonomy・分類経路・Acceptance Criteria の実質要件・Runtime Action Zero Diff（Z-1〜Z-8）・Deferred 方針はいずれも変更していない。0.8節） |
| **第5回改訂：Release Review Findings Amendment 反映** | 同上 | **改訂**（Release Review実施済み。Verdict：Changes Required（Blocking 0／Major 2／Minor 3／Suggestion 4）。人間判断で確定したMajor 2件・Minor 3件を反映：main.py Zero Diff検証方法の記述訂正（Major-1・採用案b）、v6.23記録3箇所の遡及編集を人間承認済みDocumentation Amendmentとして正式記録化・revertせず（Major-2）、architecture.md Deferred一覧のID/説明対応ずれ修正（Minor-1）、CHANGELOG見出し日付を2026-08-07へ更新（Minor-2）、12.6.2節COMPAT内訳を実装へ一致させる訂正（Minor-3）。Suggestion 4件は記録のみ（19.6節）。あわせて `docs/ROADMAP.md`・`docs/CHANGELOG.md`・`docs/architecture.md` へも同内容を反映。新たな実装・新たなテスト実行・git add・commit・push・Release Review再実施・Finalizeへの進行はいずれも行っていない。確定済みの reason taxonomy・分類経路・Acceptance Criteria の実質要件・Runtime Action Zero Diff（Z-1〜Z-8）・Deferred 方針はいずれも変更していない。Verdictは再レビュー前のためChanges Requiredのまま。19.6節） |
| **第6回改訂：Release Review再確認Minor-N1の反映** | 同上 | **改訂**（Release Review再確認（読み取り専用）を実施し、必須Finding0件・新規Minor 1件（Minor-N1・2箇所）を検出：12.1節`COMPAT-`行の目的欄から実装に存在しない`REQUEST_REJECTED 存続`を削除し対応ACを`AC-12`のみへ、`NOIMPACT-`行から`AC-24`を削除し`AC-31`のみへ、それぞれ訂正。あわせて19.6節に残存していた今後使用しない禁止表現（観測可能な挙動全体の不変を示す旧表現）の完全一致3件（引用・監査記録・禁止規定）を、意味・監査追跡性を保持したまま「旧Zero Diff表現」等の代替表現へ置換した。**本設計書1ファイルのみ**を対象とし、Production・E2E・他docs・assertion数はいずれも変更していない。確定済みの reason taxonomy・分類経路・Acceptance Criteria の実質要件・Runtime Action Zero Diff（Z-1〜Z-8）・Deferred 方針はいずれも変更していない。**当時0.2節本表への追記を怠っていたため、第7回改訂（Finalize）にて遡って本行を記録する**。19.8節） |
| **第7回改訂（本改訂）：Finalize － Release Review再々確認・Code Review・人間の最終承認の反映** | 同上 | **改訂**（Release Review再々確認：Verdict**Approved with Suggestions**（Blocking 0／Major 0／Minor 0／Suggestion 6）。Code Review：Verdict**Approved with Suggestions**（Blocking 0／Major 0／Minor 0／Suggestion 7、うちs-7を新規記録：I-VAL-1陰性対照W-1／W-2が同一`_VALID_BODY`を検査する重複。検出力低下なし、本Releaseでは修正せず将来のテスト再実行を伴うReleaseで整理候補）。Code ReviewではSuggestion 7件を記録したが、**Finalizeでs-6を解消したため、現在残存する非ブロッキングSuggestionは6件（s-1〜s-5、s-7）である。Code Review時点のVerdictおよび件数は履歴として維持する。**人間による設計・実装・E2E・文書の最終承認：完了**。本改訂は指定4文書（本設計書・`docs/ROADMAP.md`・`docs/CHANGELOG.md`・`docs/architecture.md`）のレビュー・承認状態の同期のみを行い、Production Code・E2E・assertion数・reason taxonomy・CONTINUE対象4値・Runtime Action Zero Diff（Z-1〜Z-8）・DI-11完結・IL-6.24-1・Deferred状態・限定テスト1678/1678・Formal Regression 4418/4418 はいずれも変更していない。**git add・commit・pushはいずれも本改訂でも実施していない**。19.7節・19.8節・22章） |

**上記1ファイル以外は、本工程（設計書へのドキュメント反映作業）における「設計書自身への書き込み」としては
一切変更していない。** Production Code・既存 tests・新規 test は、本工程より前の別工程
（Production Implementation・E2E限定テスト・Formal Regression）で実測どおりに変更・実行済みである。
`docs/ROADMAP.md`・`docs/CHANGELOG.md`・`docs/architecture.md` は、第4回改訂（Documentation
Integration）・第5回改訂（Release Review Findings Amendment）・第7回改訂（Finalize）にて
Documentation Integration の対象として**別途更新した**（本設計書ファイルとは別ファイルであり、
本節の管理対象外。変更内容はそれぞれのファイル自身が記録する）。`main.py`・`requirements.txt`・
`.env.example` はいずれも無変更である。Release Review再々確認・Code Review・人間の
最終承認はいずれも完了済みだが（19.7節・19.8節）、**git add・commit・push・新たな実装・
新たなテスト実行はこれまでの全工程（第7回改訂・本改訂を含む）を通じて一貫して実施していない。**

### 0.3 Release 番号の扱い（確定）

**Release 番号 6.24.0 は、人間レビューにより承認済みである。** 本設計書内の
「v6.24」表記は確定値として扱う。

**確定理由**

- 既存13 reason 値の name・value・定義順を完全に維持したうえで、末尾へ2値を
  追加するのみの変更であり（7.1節）、既存 Public API の削除・改名・意味変更を
  伴う破壊的変更ではない
- したがって本Release の範囲において major 更新は不要と判断する

なお本 Repository の `docs/development_workflow.md` にセマンティックバージョニング規則の
明文記載は発見できていない。番号は v6.22.0 → v6.23.0 の連番慣行に従っており、
この事実は Repository 全体に適用される一般的な semver 運用ルールの確立を意味するものではない。
**本項目が確定するのは、あくまで本Release固有の判断として 6.24.0 が承認されたことのみである。**

### 0.4 Architecture Review Required Amendments の反映

Architecture Review が付した Required Amendments 8件は、本改訂ですべて反映済みである。
反映内容の全数対照は **19.1節** に置く。要旨のみ以下に示す。

| # | Amendment | 反映節 |
|---|---|---|
| **A-1** | validator の AST guard は関数全体を制限せず、**外部応答値の読み取りのみ**を positive allow-list で厳密検査する | 7.8節・12.5節 |
| **A-2** | DEF-6.23-10 は **validator 部分のみ解消**し、一般化部分は継続 | 17章 |
| **A-3** | v6.19 `UNCLS-` へ新2 reason を追加し category／action／not-FAILED を検証する**案X を採用**（想定 +10） | 13.2節 |
| **A-4** | Formal Regression は「4053件固定維持」とせず、**既存4053シナリオの削除・弱体化なし＋設計上追加した assertion を含む新総数を実測**する | 13.3節 |
| **A-5** | 「SDK 外例外」ではなく「**`openai.APIError` として捕捉されなかった予期しない例外**」または「**generic `except Exception` 経路**」と表現する | 全編 |
| **A-6** | message と reason の整合は、**本Release対象の `UNKNOWN` 系／`INVALID_RESPONSE` 系2組に限定**して主張する | 7.6節 |
| **A-7** | **Production source allow-list と test change allow-list を分離**する | 11.5節 |
| **A-8** | Production docstring の変更は、**既存記述が不正確になる場合のみ**とする | 10.1節 |

### 0.5 Architecture Review Verdict（Approved with Minor Amendments）の反映（第1回改訂）

Architecture Review は本設計書（0.4節反映後）に対し **Approved with Minor Amendments**
（Minor 3件・Suggestion 1件）の Verdict を付し、あわせて **実装前必須Gate 1件**
（Finding ではなく、実装着手の前提条件として独立に課されたもの）を課した。
反映内容の全数対照は **19.2節** に置く。要旨のみ以下に示す。

**Finding（Minor 3件・Suggestion 1件）**

| # | 種別 | 指摘 | 反映節 |
|---|---|---|---|
| **Minor-1** | Minor | 「全22章」という表現が、第0章を含む実際の構成（全23セクション、第0章〜第22章）と不整合だった | 0章冒頭 |
| **Minor-2** | Minor | Release 番号 6.24.0 の扱いが「提案」のまま未確定事項（旧 U-4）に留まっていた | 0.3節 |
| **Minor-3** | Minor | v6.23 設計時の予告（戻り値契約変更）と実測結果の差異が、未確定事項（旧 U-3）としてのみ記録されていた | 6.4節 |
| **Suggestion-1** | Suggestion | v6.23 guard の allow-list 更新要否（旧 U-6）が、推測に基づき「変更不要」と先取り判定されたまま未確定事項に留まっていた | 11.4.1節・18章 |

**実装前必須Gate（Finding ではない。1件）**

| ID | 内容 | 反映節 |
|---|---|---|
| **Gate（旧 U-2）** | Formal Regression の前提となる正式 Inventory 確定義務。**Minor でも Suggestion でもなく**、レビューが実装着手の前提条件として独立に課した Gate である | 13.1節・18章・20章 |

Finding 4件・実装前必須Gate 1件はいずれも第1回改訂で反映済みである。
**確定済みの reason taxonomy・Acceptance Criteria・Runtime Action Zero Diff（Z-1〜Z-8）・
Deferred 方針はいずれも変更していない。**

### 0.6 Production実装前Gate の確認結果と Required Amendment の反映（第2回改訂）

Production実装前に、Gate 1（Git状態）／Gate 2（Formal Regression 正式Inventory）／
Gate 3（I-VAL-1 現行適合性）／Gate 4（v6.23／v6.21／v6.22 guard 更新要否）／
Gate 5（実装対象の最終確認）の5件を読み取り専用で確認した。
反映内容の全数対照は **19.3節** に置く。要旨のみ以下に示す。

**Gate別結果**

| Gate | 内容 | 結果 |
|---|---|---|
| Gate 1 | Git状態（branch／HEAD／origin/main／ahead-behind／untracked） | **PASS** |
| Gate 2 | Formal Regression 正式Inventory 26ファイルの確定（旧 U-2） | **PASS**（13.1節・20章 で解消） |
| Gate 3 | I-VAL-1 現行適合性の AST 実測（旧 U-1） | **Required Amendment 1件を検出**。第2回改訂で反映し **PASS** |
| Gate 4 | v6.23／v6.21／v6.22 guard の allow-list 更新要否（旧 U-6） | **PASS**（source allow-list 更新不要、test allow-list への `test_e2e_v6_24_0_*.py` 追加が必要と確定） |
| Gate 5 | Production／E2E 変更対象の最終確認 | **PASS**（実測行番号2件の軽微なずれを本改訂で訂正） |

**Gate総合判定：Required Amendment（Gate 3）反映後、Production実装へ進行可能。**

**Required Amendment（Gate 3 由来、1件）**

| ID | 指摘 | 反映内容 | 反映節 |
|---|---|---|---|
| **RA-Gate3-1** | I-VAL-1 条件(a)「当該関数本体に `ast.Attribute` ノードが0件であること」が、`_validate_response_structure()` が正当に行う内部 Enum メンバ参照（`OpenAIImageGenerationErrorReason.INVALID_RESPONSE`／`INVALID_RESPONSE_STRUCTURE`）まで violation と誤判定する。現行実装・改修後実装のいずれでも旧文言のままでは恒久的に不適合となる欠陥 | 条件(a)を「外部応答値に由来する識別子集合 R = {`response`, `data`, `b64_json`} を根とする `ast.Attribute` が0件」へスコープ限定。R外（内部 Enum・定数等）への属性アクセスは対象外と明記。許容対照 W-5 を追加 | **7.8.2節・7.8.3節・7.8.5節・12.5.1節・12.5.2節・12.5.3節・AC-28** |

第2回改訂で解消した未確定事項：**U-1（解消）・U-2（解消）**。旧U-6は第1回改訂で手順化済みであり、
第2回改訂の Gate 4 実測によりその内容が確定した。**U-5 のみ未確定事項として継続した**（20章）。

**確定済みの reason taxonomy・分類経路・Acceptance Criteria の実質要件・
Runtime Action Zero Diff（Z-1〜Z-8）・Deferred 方針はいずれも変更していない。**

### 0.7 E2E限定テスト実測結果の反映（第3回改訂）

Production Implementation（1ファイル）および E2E 限定テスト（既存5ファイルの更新・新規1ファイルの
作成）は、本工程より前の別工程で実施済みである。**本工程はその実測結果を設計書へ反映する
ドキュメント作業のみを行い、新たな実装・新たなテスト実行は一切行っていない。**
反映内容の全数対照は **19.4節** に置く。要旨のみ以下に示す。

**限定テスト実測結果（6ファイル・`.\venv\Scripts\python.exe` により個別実行）**

| ファイル | 実測 assertion | 変更前 | 増減 | 設計時の宣言 | 判定 |
|---|---|---|---|---|---|
| `test_e2e_v6_11_0_*.py` | **248/248 PASS** | 248 | ±0 | ±0（13.2節） | 一致 |
| `test_e2e_v6_19_0_*.py` | **272/272 PASS** | 262 | **+10** | +10（13.2節・A-3） | 一致 |
| `test_e2e_v6_21_0_*.py` | **147/147 PASS** | 147 | ±0 | ±0（13.2節） | 一致 |
| `test_e2e_v6_22_0_*.py` | **324/324 PASS** | 324 | ±0 | ±0（13.2節） | 一致 |
| `test_e2e_v6_23_0_*.py` | **341/341 PASS** | 332 | **+9** | +3（13.2節・11.4.2節） | **乖離。第3回改訂で訂正** |
| `test_e2e_v6_24_0_*.py`（新規） | **346/346 PASS** | — | — | 見込み346（12.6.2節） | 一致（乖離0） |
| **限定合計** | **1678/1678 PASS** | | | | FAIL 0・SKIP 0・全終了コード0 |

**v6.23 の乖離（+3 → +9）について**：設計時点（設計書初版・11.4.2節）は DEF-6.23-12 の解消分
（恒真式2件 → D12-1〜D12-5 の5件、+3）のみを計上していた。実測の結果、`test_e2e_v6_23_0_*.py`
は `test_e2e_v6_19_0_*.py` と同型の `_ALL_REASONS = list(OpenAIImageGenerationErrorReason)`
駆動ループを2箇所持つことが判明し、Enum 値追加（13→15）に伴い自動的に増加する +6 分
（`API-VALUE[name]` ループ +2、`POLICY-CATEGORY[r]`／`POLICY-ACTION[r]` ループ +4）が
計上漏れであった。**これは期待値の緩和ではない。** Production 未実装のまま v6.23 の
allow-list 更新のみを適用して実行したところ、`_EXPECTED_CATEGORY[_reason.name]` が
`KeyError: 'UNEXPECTED_EXCEPTION'` で失敗し、テスト自体が成立しなかった。これは
v6.19.0 の前例（案X 採用時の +10 の一部）と同型の「Enum 全数を対象とする既存の表駆動
全数検査を維持するために必須の構造的追随」であり、**検査対象（coverage）が13値から
15値へ拡張されたことによる自動増分**である。既存 assertion の削除・期待値の緩和は
一切ない（F-1「既存シナリオの削除・弱体化が0件であること」を満たす）。詳細は13.2節。

**第3回改訂の時点では、Formal Regression（27ファイル）は未実施のまま継続していた。**
個別ファイル実測の合計は 4053 − 332 + 341 − 262 + 272 = **4072**（既存26ファイル新合計）
＋ 346（新規） = **4418** と算出されていたが、これは個別実行の合算値であり、
27ファイルを対象とする Formal Regression の正式な一括実行そのものは
当時まだ行っていなかった（第4回改訂・0.8節・19.5節で実施・確定した）。

**確定済みの reason taxonomy・分類経路・Acceptance Criteria の実質要件・
Runtime Action Zero Diff（Z-1〜Z-8）・Deferred 方針はいずれも変更していない。**

### 0.8 Formal Regression の実測反映と Documentation Integration（第4回改訂・本改訂）

Formal Regression（正式Inventory27ファイルの個別実行）は、本工程より前の別工程で
実施済みである。**本工程はその実測結果を設計書へ反映し、あわせて `docs/ROADMAP.md`・
`docs/CHANGELOG.md`・`docs/architecture.md` の Documentation Integration を行う。
新たな実装・新たなテスト実行は一切行っていない。**
反映内容の全数対照は **19.5節** に置く。要旨のみ以下に示す。

**Formal Regression 実測結果（27ファイル・正式Inventory順に個別実行）**

| 区分 | 結果 |
|---|---|
| 既存26ファイル | **4072/4072 PASS**（限定テスト実測値と完全一致） |
| 新規v6.24（27番目） | **346/346 PASS**（限定テスト実測値と完全一致） |
| **27ファイル総合** | **4418/4418 PASS** |
| FAIL | **0件**（全27ファイル） |
| SKIP | **0件**（全27ファイル。ラベル文言中の語のみで実SKIPなし） |
| 終了コード | **全27ファイルとも0** |
| 外部API実接続 | **0件**（v6.23／v6.24 双方で `SOCKET-*` guard により実測確認） |
| 見込み（4418）との差異 | **なし（完全一致）** |

限定テスト実測（0.7節・19.4節）との照合：v6.11＝248／v6.19＝272／v6.21＝147／v6.22＝324／
v6.23＝341／v6.24＝346のいずれも、限定テスト時点の実測値と**完全に一致**した。
既存26ファイルの算術検証（43+64+43+44+64+174+171+131+135+117+197+331+78+248+91+123+217+94+143+136+146+272+198+147+324+341＝4072）も
実行結果の合計と一致することを確認済み。

**Documentation Integration**：正式実績（Release 6.24.0・Production変更1件・新規E2E 1件・
既存E2E追随5件・限定テスト1678/1678 PASS・Formal Regression 4418/4418 PASS）を
`docs/ROADMAP.md`（v6.24.0エントリ追加・DI-11完結への更新・Deferred状態の同期）・
`docs/CHANGELOG.md`（`## [v6.24.0]` セクション新設）・`docs/architecture.md`
（v6.24.0層の追加・v6.23.0層への参照注記追加）へ反映した。commit・pushは行っていない。

**確定済みの reason taxonomy・分類経路・Acceptance Criteria の実質要件・
Runtime Action Zero Diff（Z-1〜Z-8）・Deferred 方針はいずれも変更していない。**

---

## 1. 背景・目的

### 1.1 DI-11 後半の Repository 上の正式定義

`docs/ROADMAP.md` L1200-1210 は、DI-11 後半を次のとおり「次候補・未着手」として定義している。

```text
- [ ] OpenAI Image Generation Request Rejection Reason Refinement 後半（DI-11後半）
  （次候補・未着手）：DI-11の前半（REQUEST_REJECTEDのSDK例外型による4値細分化）は
  v6.23.0で完了した。後半として次の2点が残る。
  ①UNKNOWNの2経路分離（openai.APIError catch-all経路とexcept Exception経路の区別。DEF-6.23-3）
  ②INVALID_RESPONSEの細分化（単発の応答破損とprovider／SDKのスキーマ変更の区別。DEF-6.23-4）
```

`docs/design/openai_image_generation_api_rejection_reason_classification_foundation.md`
16章（Deferred Items）は同じ2件を **DEF-6.23-3** / **DEF-6.23-4** として登録し、引継ぎ先を
「DI-11 後半」としている。本Releaseはこの2件を実装対象とする。

あわせて、同16章の **DEF-6.23-12** は引継ぎ先を「**次に v6.23 の NOIMPACT guard へ触れる
Release**」と定めている。本Releaseは 11.4節のとおり v6.23 guard の allow-list を更新するため
判断機会が発生する。したがって DEF-6.23-12 も本Releaseの実装対象に含める。

### 1.2 なぜ今なのか

| # | 理由 |
|---|---|
| 1 | `docs/ROADMAP.md` L1200 が唯一「次候補・未着手」と明示している項目である |
| 2 | 他の Deferred へ依存しない。ORD-3（CONTINUE 拡大）のような人間の業務判断も、新規の永続化も要さない |
| 3 | DI-11 を完結させ、Deferred 台帳を3件（DEF-6.23-3／-4／-12）削減できる |
| 4 | v6.11／v6.22／v6.23 と同型の precedent が3件あり、設計・テスト構造を流用できる |
| 5 | v6.19 の allow-list 方式（C-17）により、新 reason は追加写像なしで安全側へ落ちる。**写像側 0 diff で完了できる稀な形**である |

### 1.3 目的

`OpenAIImageGenerationErrorReason` において**1つの reason 値に潰れている2組の異なる失敗経路**を、
reason 値として分離する。

**本Releaseの中核となる位置づけ**は次のとおりである。

> **「新しい reason を発明する」のではなく、「既に message として存在している区別を、
> reason 値へ昇格させる」Release である。**

この位置づけが重要なのは、v6.23 が抱えた IL-1（4型の message を凍結した結果
`RESOURCE_NOT_FOUND` の message が意味的に不正確なまま残った。v6.23 設計書 7.6節）と
**同型の問題を新たに生まない**ためである。本Releaseでは、対象2組について message と reason が
1対1で対応する方向へ改善される（主張の範囲は 7.6節で厳密に限定する。**A-6**）。

---

## 2. Problem Statement

### 2.1 現状の欠落

**欠落① `UNKNOWN` が2つの異なる失敗を同一視している**

| 経路 | 実装位置 | 意味 |
|---|---|---|
| `openai.APIError` の catch-all | `openai_image_generator.py` L189-192 | SDK が投げた既知の例外階層のうち、L134-187 のどの分岐にも一致しなかった subtype |
| generic `except Exception` 経路 | 同 L349-351 | `openai.APIError` として捕捉されなかった予期しない例外（SDK の契約外、または呼び出し側環境に起因） |

前者は「provider 由来だが未分類」、後者は「provider 由来かどうかすら不明」であり、
運用上の意味も対処も異なる。にもかかわらず `.reason` は同一値である。

**欠落② `INVALID_RESPONSE` が4つの経路を同一視している**

| 経路 | 実装位置 | 意味 |
|---|---|---|
| `data` 不正（欠落・非 list・件数≠1） | L203-204 | 応答の**構造**（スキーマ）が想定と異なる |
| `b64_json` 不正（欠落・非 str・空） | L206-208 | 同上 |
| Base64 デコード失敗 | L220-222 | 構造は正しいが**ペイロードが破損**している |
| デコード結果0バイト | L224-226 | 同上 |

前2者は provider／SDK のスキーマ変更を疑うべき事象であり、後2者は単発の応答破損である。
DEF-6.23-4 が求める「単発の応答破損と provider／SDK のスキーマ変更の区別」は、
まさにこの境界のことである。

### 2.2 集約が引き起こしている具体的損害

| # | 損害 |
|---|---|
| **D-1** | **message では既に区別されているのに reason では区別されていない**という非対称が存在する。`_MSG_UNEXPECTED_ERROR`（L50）と catch-all の message（L190）は別文字列であり、`_MSG_INVALID_RESPONSE_STRUCTURE`（L51）と `_MSG_INVALID_BASE64`（L52）／`_MSG_EMPTY_DECODE_RESULT`（L53）も別文字列である |
| **D-2** | reason は secret-free な分類ラベルとして下流へ渡せる唯一の構造情報であるが、message は人間向け表示であり構造的な分岐の根拠にしてはならない。したがって現状、**下流は2組の区別を機械的に得る手段を持たない** |
| **D-3** | 将来 DI-5（reason の構造化ログ／metrics 記録）を実施しても、`UNKNOWN` と `INVALID_RESPONSE` の内訳が取れず、ORD-1 の再評価に必要な運用データの粒度が不足する |

### 2.3 本Releaseが解決しないこと

2.2 の D-3 が示すとおり、本Releaseは**分類粒度を用意するところまで**であり、
その粒度を観測・活用する仕組み（DI-5）は対象外である（5章 N-5）。

---

## 3. 現行契約（Repository Survey Findings）

本章の記載はすべて **HEAD = `38e2487`** の作業ツリーに対する読み取り専用の実測である。

### 3.1 v6.23 時点の reason 契約（13値）

`src/openai_image_generation/openai_image_generator.py` L56-77。

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
    # ─── v6.23.0 追加（既存9値の後ろへ追加する。既存の定義順は変更しない）───
    BAD_REQUEST = "bad_request"
    RESOURCE_NOT_FOUND = "resource_not_found"
    CONFLICT = "conflict"
    UNPROCESSABLE_ENTITY = "unprocessable_entity"
```

### 3.2 `UNKNOWN` の2経路（実測）

```python
# L189-192  _classify_api_error() の末尾。openai.APIError の catch-all
    return (
        "OpenAI Images APIの呼び出しに失敗しました",
        OpenAIImageGenerationErrorReason.UNKNOWN,
    )

# L345-351  generate() 内
        try:
            response = client.images.generate(**self._build_kwargs(prompt))
        except openai.APIError as exc:
            error_message, error_reason = _classify_api_error(exc)
        except Exception:
            error_message = _MSG_UNEXPECTED_ERROR
            error_reason = OpenAIImageGenerationErrorReason.UNKNOWN
```

`generate()` 内に `except Exception` は L349 の1箇所のみである。

### 3.3 `INVALID_RESPONSE` の4経路（実測）

```python
# L195-210  _validate_response_structure()
def _validate_response_structure(response):
    data = getattr(response, "data", _MISSING)
    if not isinstance(data, list) or len(data) != 1:
        return (_MSG_INVALID_RESPONSE_STRUCTURE, OpenAIImageGenerationErrorReason.INVALID_RESPONSE, None)

    b64_json = getattr(data[0], "b64_json", _MISSING)
    if not isinstance(b64_json, str) or not b64_json:
        return (_MSG_INVALID_RESPONSE_STRUCTURE, OpenAIImageGenerationErrorReason.INVALID_RESPONSE, None)

    return (None, None, b64_json)

# L213-232  _build_generated_image()
        try:
            decoded = base64.b64decode(b64_value, validate=True)
        except (binascii.Error, ValueError):
            error_message = _MSG_INVALID_BASE64
            error_reason = OpenAIImageGenerationErrorReason.INVALID_RESPONSE   # L222
        else:
            if len(decoded) == 0:
                error_message = _MSG_EMPTY_DECODE_RESULT
                error_reason = OpenAIImageGenerationErrorReason.INVALID_RESPONSE   # L226
```

`_validate_response_structure()` の呼び出し元は `_build_generated_image()`（L214）の1箇所のみである。
外部応答値に対する属性読み取りは **`getattr` の2箇所のみ**であり、`ast.Attribute` による
直接属性アクセス（`response.data` 等）は関数内に存在しない。

### 3.4 v6.19 policy の現行契約と安全側性質

`src/image_generation_fallback_policy/image_generation_fallback_policy.py`。

```python
# L97-102
_CONTINUABLE_REASONS = frozenset({TIMEOUT, CONNECTION, RATE_LIMIT, SERVER_ERROR})

# L112-118（v6.23.0 で追加）
_REJECTED_REASONS = frozenset({
    REQUEST_REJECTED, BAD_REQUEST, RESOURCE_NOT_FOUND, CONFLICT, UNPROCESSABLE_ENTITY,
})

# L158-176 decide_image_generation_fallback() の OpenAI 分岐
    if isinstance(error, OpenAIImageGenerationError):
        reason = getattr(error, "reason", None)
        if reason is AUTHENTICATION or reason is PERMISSION_DENIED:
            category = IMAGE_GENERATION_NOT_AUTHORIZED
        elif isinstance(reason, ...) and reason in _REJECTED_REASONS:
            category = IMAGE_GENERATION_REQUEST_REJECTED
        elif isinstance(reason, ...) and reason in _CONTINUABLE_REASONS:
            category = IMAGE_GENERATION_FAILED
        else:
            category = UNCLASSIFIED           # ← L173-176
```

**C-17（v6.19 が確立した安全側性質）**：2つの集合はいずれも allow-list であり deny-list ではない。
したがって Enum へ新値を追加しても、新値はどちらの集合にも属さず L173-176 の `else` へ落ち、
**自動的に `UNCLASSIFIED` → `PROPAGATE_ORIGINAL_ERROR`（安全側）になる**。

**この性質が本Releaseの設計上の要である。** 新2値のために写像を追加する必要はなく、
`image_generation_fallback_policy.py` を**ファイル単位で 0 diff** に保てる。

### 3.5 既存 E2E の棚卸し（走査 methodology と全数）

**走査方法**：`tests/` 配下全ファイルに対し `OpenAIImageGenerationErrorReason`・
`INVALID_RESPONSE`・`UNKNOWN`・`len(list(OpenAIImageGenerationErrorReason))`・
`BASELINE_COMMIT` を検索し、ヒットしたファイルを個別に読み取って依存の性質を判定した。

| ファイル | 依存の性質 | 追随要否 |
|---|---|---|
| `test_e2e_v6_11_0_*.py` | L946-964 `_resp_cases`（12件）が `INVALID_RESPONSE` を期待。L992-1002 `_b64_failure_cases`（5件）＋L1005-1014（1件）が `INVALID_RESPONSE` を期待。L1071-1104 `_err_cases` のうち L1100-1101 `ERR-GENERIC` と L1102-1103 `ERR-UNKNOWN-EXC` が `UNKNOWN` を期待 | **要** |
| `test_e2e_v6_19_0_*.py` | L292 `_ALL_REASONS = list(OpenAIImageGenerationErrorReason)` 駆動。L524／L717 のループ、L545 の `UNCLS-` tuple、L690-706 の期待表、L707-711／L764-769／L1300-1305 の件数 | **要** |
| `test_e2e_v6_21_0_*.py` | L824 `BASELINE_COMMIT = "8d8950684a305bc93c824866578cb30c6b2e4fdd"` の baseline 固定 guard | **要**（allow-list のみ） |
| `test_e2e_v6_22_0_*.py` | L1013 `BASELINE_COMMIT = "578af6bdaeec23dd0c145a57384369ede433e3e4"` の baseline 固定 guard。L1239-1241 `COMPAT-V611` は `__all__` のみ参照 | **要**（allow-list のみ） |
| `test_e2e_v6_23_0_*.py` | L1116 `BASELINE_COMMIT = "8fd845348d1ee4c80db8de2942da5f99c2bcf0fd"` の baseline 固定 guard。L1232-1242 に DEF-6.23-12 の恒真式2件 | **要**（allow-list ＋ DEF-6.23-12 修正） |
| `test_e2e_v6_18_0_*.py` | L1041-1052 `COMPAT-V611*` は `__all__` と `generate`／`from_env` の存在のみ確認。Enum 件数・値に非依存 | **不要** |
| `test_e2e_v6_20_0_*.py` | L1009-1011 `COMPAT-V611` は `__all__` のみ参照 | **不要** |
| 上記以外の全ファイル | reason 値・Enum 件数への依存を検出せず | **不要** |

### 3.6 baseline 固定 guard の棚卸し

| Release | ファイル | `BASELINE_COMMIT` | 検査方式 |
|---|---|---|---|
| v6.21 | `test_e2e_v6_21_0_*.py` L824 | `8d89506…` | containment（`_protected_paths` 22件） |
| v6.22 | `test_e2e_v6_22_0_*.py` L1013 | `578af6b…` | containment（同22件） |
| v6.23 | `test_e2e_v6_23_0_*.py` L1116 | `8fd8453…` | containment ＋ **coverage／equality**（GR-6） |

**本Releaseで4件目（v6.24、baseline `38e2487`）が加わる。** GR-9 が予告した O(N) 保守コストは
guard 3件から4件へ増大するが、共有レジストリ化（DEF-6.23-9）は本Releaseの対象外である（5章 N-9）。

---

## 4. Goals

| ID | Goal |
|---|---|
| **G-1** | `UNKNOWN` に集約されている2経路のうち、**generic `except Exception` 経路のみ**を新 reason `UNEXPECTED_EXCEPTION` へ分離する（DEF-6.23-3） |
| **G-2** | `INVALID_RESPONSE` に集約されている4経路のうち、**`data`／`b64_json` の構造不正2経路のみ**を新 reason `INVALID_RESPONSE_STRUCTURE` へ分離する（DEF-6.23-4） |
| **G-3** | `UNKNOWN` と `INVALID_RESPONSE` を**削除・改名せず**、Public API に残す（後方互換） |
| **G-4** | 新 reason 2値をいずれも `UNCLASSIFIED` ＋ `PROPAGATE_ORIGINAL_ERROR` とし、**action を1件も変えない** |
| **G-5** | `_CONTINUABLE_REASONS`（4値）を**1値も変えない**（CONTINUE 拡大なし） |
| **G-6** | exception message・exception chaining・成功経路・public signature を**1文字も変えない** |
| **G-7** | `main.py` を**バイト単位で無変更**に保つ |
| **G-8** | `image_generation_fallback_policy.py` を**ファイル単位で 0 diff** に保ち、baseline との差分が空であることを機械的に検証する |
| **G-9** | SDK 例外分類が例外型のみを根拠とする既存契約（I-EXC-1）を**破壊しない**。`_classify_api_error()` は 0 diff とする |
| **G-10** | 応答構造分類が **`data`／`b64_json` の構造検査のみ**を使用し、エラー応答本文・`text`／`content`／`headers`／`status_code`／`json()` を解析しないことを、設計と E2E の両方で保証する（**I-VAL-1**） |
| **G-11** | v6.19 の「新 reason は自動的に安全側へ落ちる」性質（C-17）を**破壊しない** |
| **G-12** | DEF-6.23-12 を解消する。v6.23 の恒真式2件を実値ベースの陽性対照へ置換し、既存の containment／coverage／exact guard を**弱めない** |

---

## 5. 非スコープ（Non-Goals）

| ID | 非対象 | 理由 |
|---|---|---|
| **N-1** | CONTINUE 対象の拡大 | ORD-3 の領域。DI-5 の運用データと人間の明示承認が前提（v6.23 設計書 16章 DEF-6.23-2） |
| **N-2** | `CONTENT_POLICY_REJECTED` の新設 | response body の `code` 解析を要し、解析禁止 contract に抵触。**DEF-6.23-6 継続** |
| **N-3** | exception message の改訂 | **DEF-6.23-1 継続**。7.6節により全 message 凍結 |
| **N-4** | `status_code` の属性公開 | **DEF-6.23-7 継続** |
| **N-5** | reason の構造化ログ／metrics 記録 | **DI-5／DEF-6.23-8 継続** |
| **N-6** | WordPress 側（`WordPressMediaUploadErrorReason`）への一切の変更 | DI-10 は v6.22 で完了済み。本Releaseの関心外 |
| **N-7** | `_classify_api_error()` の変更 | 7.3節により catch-all は `UNKNOWN` を維持するため、**同関数は 0 diff** |
| **N-8** | `INVALID_RESPONSE` の改名 | 後方互換を破る。**IL-6.24-1** として受容（16章） |
| **N-9** | zero-diff guard の共有レジストリ化 | **DEF-6.23-9 継続**（guard 3→4件で保守コストは増大するが、テスト基盤の構造変更を伴うため独立 Release を要する） |
| **N-10** | positive allow-list 方式 guard の**他関数への一般化** | **DEF-6.23-10 の一般化部分は継続**（**A-2**）。本Releaseは `_validate_response_structure()` についてのみ解消する |
| **N-11** | Retry／Idempotency（DI-6）、未使用 Media cleanup（DI-7） | 継続 |
| **N-12** | 新規 package・新規 class・Composition Root の追加 | 本Releaseは既存1ファイルへの追加のみ |

---

## 6. Design Alternatives

### 6.1 どちらの経路へ新値を割り当てるか（論点1）

| 案 | 内容 | 判定 |
|---|---|---|
| **A-1（採用）** | catch-all → 既存 `UNKNOWN` を維持。generic `except Exception` → 新 `UNEXPECTED_EXCEPTION` | **採用** |
| A-2 | catch-all → 新値。generic → 既存 `UNKNOWN` を維持 | 却下 |
| A-3 | 両経路とも新値。`UNKNOWN` を production 到達不能化 | 却下 |

**A-1 採用理由**：`UNKNOWN`（= "unknown"）という語は「provider から返ったが分類できない」に
最も素直に対応する。A-3 は v6.23 の `REQUEST_REJECTED` と同じく到達不能値を増やすが、
本Releaseでは**到達不能値を新たに作らないほうが Public API の理解可能性が高い**と判断した。
A-2 は既存 E2E（`ERR-GENERIC`）の意味を反転させ、差分読解性を損なう。

### 6.2 `_validate_response_structure()` の契約変更を伴うか（論点2）

v6.23 設計書 16章 DEF-6.23-4 は、本項目が
「`_validate_response_structure()` の**戻り値契約変更**を伴う」と予告していた。

**実測により、契約変更は不要であることが判明した。** 同関数は既に
`(error_message, error_reason, b64_json_or_None)` の3要素タプルを返しており、
`error_reason` は返却値の一部である。したがって**返却する reason 値を差し替えるだけ**で
G-2 を満たせる。signature・要素数・要素の意味はいずれも不変とする（8.2節・**確定仕様**）。

v6.23 設計時の予告と実測の差異は 6.4節に「過去文書との差異・補正記録」として整理する。

### 6.3 fallback policy を変更するか（論点3）

| 案 | 内容 | 判定 |
|---|---|---|
| **B-1（採用）** | `image_generation_fallback_policy.py` を **0 diff** とし、C-17 の allow-list 性質により新2値を `else` へ落とす | **採用** |
| B-2 | 新2値を明示的に列挙する `_UNCLASSIFIED_REASONS` を新設し、明示写像する | 却下 |

**B-1 採用理由**：B-2 は「明示的なほうが安全」に見えるが、実際には C-17 の allow-list 設計を
deny-list 的な全数列挙へ後退させ、**将来 reason を追加するたびに policy 側の改修を強制する**。
v6.19 が意図的に採用した「新値は自動的に安全側へ落ちる」性質を損なうため却下する。

**B-1 は実装工程での逸脱リスクを伴う**（実装者が「念のため」写像を追加してしまう）。
これを AC-21・RB-8 で機械的に封じる（15章 R-3）。

### 6.4 過去文書との差異・補正記録

v6.23 設計書 16章 DEF-6.23-4 が予告していた内容と、本設計書が実測に基づいて確定した
内容との間に差異がある。**これは未確定事項ではなく、確定済みの補正記録として扱う。**

| 対象文書 | 記載内容（当時） | 本設計書での実測結果 | 補正内容 |
|---|---|---|---|
| v6.23 設計書 16章 DEF-6.23-4 | 「`_validate_response_structure()` の**戻り値契約変更**を伴う」と予告していた | 実測の結果、同関数は既に `(error_message, error_reason, b64_json_or_None)` の3要素タプルを返しており、`error_reason` は既に返却値の一部である（3.3節・6.2節） | v6.24.0 は **signature／3要素返却形を変えない**。本Releaseは「戻り値契約変更」ではなく、**返却可能 reason 集合の拡張（Enum 2値追加）と、経路別 reason 精緻化（7.3節 C-1〜C-4）**として扱う。契約変更が不要であることは確定仕様である（8.2節・AC-26） |

**扱いの確定**：この差異について Architecture Review での確認を求めたところ、
上記の補正内容（契約変更なしとして扱う）が承認された（0.5節 Minor-3）。
当時の予告記述自体を遡って訂正することはしない。本節が両者の差異を明示的に記録する。

---

## 7. Selected Architecture

### 7.1 reason taxonomy（名前・value・粒度）

**確定仕様**：既存13値の name・value・**定義順**を完全維持し、末尾へ次の順で2値を追加する。

```python
class OpenAIImageGenerationErrorReason(Enum):
    # ─── 既存13値（1文字も変更しない）───
    AUTHENTICATION = "authentication"
    PERMISSION_DENIED = "permission_denied"
    RATE_LIMIT = "rate_limit"
    TIMEOUT = "timeout"
    CONNECTION = "connection"
    REQUEST_REJECTED = "request_rejected"
    SERVER_ERROR = "server_error"
    INVALID_RESPONSE = "invalid_response"
    UNKNOWN = "unknown"
    BAD_REQUEST = "bad_request"
    RESOURCE_NOT_FOUND = "resource_not_found"
    CONFLICT = "conflict"
    UNPROCESSABLE_ENTITY = "unprocessable_entity"
    # ─── v6.24.0 追加（既存13値の後ろへ追加する。既存の定義順は変更しない）───
    UNEXPECTED_EXCEPTION = "unexpected_exception"
    INVALID_RESPONSE_STRUCTURE = "invalid_response_structure"
```

value 文字列は既存13値と同じ lower_snake 慣行に従う。
`INVALID_RESPONSE_STRUCTURE` は既存 message 定数 `_MSG_INVALID_RESPONSE_STRUCTURE`（L51）と
語を共有しており、両者の 1対1 対応が名前の上でも読み取れる。

### 7.2 `INVALID_RESPONSE` の範囲縮小と命名（IL-6.24-1）

本Release後、`INVALID_RESPONSE` が production から生成されるのは
**Base64 デコード失敗・デコード結果0バイトの2経路のみ**になる。
`INVALID_RESPONSE`（応答が不正）という語は、この縮小後の適用範囲
（応答構造は正しいがペイロードが破損）を正確には表さない。

**改名は行わない。** 理由は次の2点である。

1. 後方互換。外部が `OpenAIImageGenerationErrorReason.INVALID_RESPONSE` を参照している場合、
   改名は破壊的変更になる（v6.23 が `REQUEST_REJECTED` を残した G-2 precedent と同じ判断）
2. 名称の適正化は利用者可視の変更であり、message 改訂（DEF-6.23-1）と同じ性質の独立判断を要する

この乖離を **IL-6.24-1** として 16章に記録し、DEF-6.23-1 へ合流させる。

### 7.3 分類経路 contract

**確定仕様**：

| ID | contract |
|---|---|
| **C-1** | `openai.APIError` の catch-all（`_classify_api_error()` L189-192）は **`UNKNOWN` を維持する**。同関数は **0 diff** とする |
| **C-2** | `generate()` の generic `except Exception` 経路（L349-351）の reason を **`UNEXPECTED_EXCEPTION` へ差し替える**。message（`_MSG_UNEXPECTED_ERROR`）は不変 |
| **C-3** | `_validate_response_structure()` の2つの return（L204・L208）の reason を **`INVALID_RESPONSE_STRUCTURE` へ差し替える**。message（`_MSG_INVALID_RESPONSE_STRUCTURE`）は不変 |
| **C-4** | `_build_generated_image()` の2つの分岐（L222・L226）の reason は **`INVALID_RESPONSE` を維持する**。message も不変 |
| **C-5** | 例外送出の構造（classify-then-raise-outside-except、`from None`）を変更しない |
| **C-6** | `except openai.APIError` と `except Exception` の**節の順序・条件式を変更しない** |

C-1 により、`_classify_api_error()` に触れないため、v6.23 が確立した **I-EXC-1**
（例外引数の使用形を `isinstance` 第1引数のみに限る positive allow-list AST guard）は
**無改修のまま有効**であり続ける。

### 7.4 `UNKNOWN` / `INVALID_RESPONSE` の後方互換保持

| 観点 | 本Release後 |
|---|---|
| Enum member として存続するか | **する**（両値とも） |
| value 文字列 | `"unknown"` / `"invalid_response"` のまま不変 |
| 定義順 | 不変（9番目・8番目） |
| production から到達するか | **する**（範囲は縮小。7.2節・C-1／C-4） |
| 外部から構築した場合の下流の結論 | **完全に同一**。いずれも `UNCLASSIFIED` → `PROPAGATE_ORIGINAL_ERROR`（3.4節 L173-176） |

v6.23 の `REQUEST_REJECTED` が production 到達不能になったのとは異なり、
**本Releaseは到達不能値を新たに作らない**（6.1節 A-1）。

### 7.5 fallback policy の全数写像（15値）

`image_generation_fallback_policy.py` は **0 diff**（G-8）。新2値は L173-176 の `else` へ落ちる。

#### 7.5.1 全数写像表（15値 × category × action）

| # | reason | 生成経路 | message | category | action |
|---|---|---|---|---|---|
| 1 | `AUTHENTICATION` | `openai.AuthenticationError` | 認証に失敗しました | `IMAGE_GENERATION_NOT_AUTHORIZED` | `PROPAGATE_ORIGINAL_ERROR` |
| 2 | `PERMISSION_DENIED` | `openai.PermissionDeniedError` | アクセス権限がありません | `IMAGE_GENERATION_NOT_AUTHORIZED` | `PROPAGATE_ORIGINAL_ERROR` |
| 3 | `RATE_LIMIT` | `openai.RateLimitError` | レート制限に達しました | `IMAGE_GENERATION_FAILED` | **`CONTINUE_WITHOUT_FEATURED_MEDIA`** |
| 4 | `TIMEOUT` | `openai.APITimeoutError` | タイムアウトしました | `IMAGE_GENERATION_FAILED` | **`CONTINUE_WITHOUT_FEATURED_MEDIA`** |
| 5 | `CONNECTION` | `openai.APIConnectionError` | 接続に失敗しました | `IMAGE_GENERATION_FAILED` | **`CONTINUE_WITHOUT_FEATURED_MEDIA`** |
| 6 | `REQUEST_REJECTED` | *（production 到達なし。後方互換）* | — | `IMAGE_GENERATION_REQUEST_REJECTED` | `PROPAGATE_ORIGINAL_ERROR` |
| 7 | `SERVER_ERROR` | `openai.InternalServerError` | API側でエラーが発生しました | `IMAGE_GENERATION_FAILED` | **`CONTINUE_WITHOUT_FEATURED_MEDIA`** |
| 8 | `INVALID_RESPONSE` | **Base64 デコード失敗／0バイト**（範囲縮小） | Base64データが不正です／デコード結果が空でした | `UNCLASSIFIED` | `PROPAGATE_ORIGINAL_ERROR` |
| 9 | `UNKNOWN` | **`openai.APIError` catch-all のみ**（範囲縮小） | 呼び出しに失敗しました | `UNCLASSIFIED` | `PROPAGATE_ORIGINAL_ERROR` |
| 10 | `BAD_REQUEST` | `openai.BadRequestError` | リクエストが不正です | `IMAGE_GENERATION_REQUEST_REJECTED` | `PROPAGATE_ORIGINAL_ERROR` |
| 11 | `RESOURCE_NOT_FOUND` | `openai.NotFoundError` | リクエストが不正です | `IMAGE_GENERATION_REQUEST_REJECTED` | `PROPAGATE_ORIGINAL_ERROR` |
| 12 | `CONFLICT` | `openai.ConflictError` | リクエストが不正です | `IMAGE_GENERATION_REQUEST_REJECTED` | `PROPAGATE_ORIGINAL_ERROR` |
| 13 | `UNPROCESSABLE_ENTITY` | `openai.UnprocessableEntityError` | リクエストが不正です | `IMAGE_GENERATION_REQUEST_REJECTED` | `PROPAGATE_ORIGINAL_ERROR` |
| **14** | **`UNEXPECTED_EXCEPTION`** | **generic `except Exception` 経路** | 予期しないエラーが発生しました | **`UNCLASSIFIED`** | **`PROPAGATE_ORIGINAL_ERROR`** |
| **15** | **`INVALID_RESPONSE_STRUCTURE`** | **`data`／`b64_json` の構造不正** | レスポンス構造が不正です | **`UNCLASSIFIED`** | **`PROPAGATE_ORIGINAL_ERROR`** |

**category split の推移**

| category | v6.23（13値） | v6.24（15値） | 変化 |
|---|---|---|---|
| `IMAGE_GENERATION_FAILED`（＝CONTINUE） | **4** | **4** | **±0** |
| `IMAGE_GENERATION_REQUEST_REJECTED` | 5 | 5 | ±0 |
| `IMAGE_GENERATION_NOT_AUTHORIZED` | 2 | 2 | ±0 |
| `UNCLASSIFIED` | 2 | **4** | +2 |
| **合計** | **13** | **15** | +2 |

**split 表記：4 / 5 / 2 / 2 → 4 / 5 / 2 / 4**

`IMAGE_GENERATION_FAILED` が 4 のまま変わらないことが、**CONTINUE 対象を拡大していない直接証拠**である（9.3節）。

### 7.6 message 凍結（A-6 に基づく主張範囲の限定）

**確定仕様**：`_MSG_UNEXPECTED_ERROR`（L50）・`_MSG_INVALID_RESPONSE_STRUCTURE`（L51）・
`_MSG_INVALID_BASE64`（L52）・`_MSG_EMPTY_DECODE_RESULT`（L53）および
`_classify_api_error()` 内の全 message リテラルは、**1文字も変更しない**。

本Releaseが主張する「message と reason の整合」は、**次の2組に限定する**（**A-6**）。

| 組 | 主張内容 |
|---|---|
| `UNKNOWN` 系 | 従来 message で区別されていた catch-all と generic 経路が、本Release後は reason でも区別される |
| `INVALID_RESPONSE` 系 | 従来 message で区別されていた「構造不正」と「Base64 破損」が、本Release後は reason でも区別される |

**上記2組以外について、message と reason の整合を主張してはならない。**
特に v6.23 の IL-1（`RESOURCE_NOT_FOUND` を含む要求拒否系4型が同一 message を共有する不整合）は
**本Releaseでは解消されず、そのまま残存する**（DEF-6.23-1）。

### 7.7 Security contract

| ID | contract |
|---|---|
| **S-1** | reason は固定の分類ラベルのみを保持する。secret・provider 固有の生データ・prompt・api_key・Base64 本体・応答本文をいずれも含まない |
| **S-2** | SDK 例外分類は例外型（`isinstance`）のみを根拠とする。message・`exc.args`・response body・status code・例外属性をいずれも読まない（**I-EXC-1**。`_classify_api_error()` 0 diff により無改修で維持） |
| **S-3** | 応答構造分類は `data`／`b64_json` の構造検査のみを使用する。`text`／`content`／`headers`／`status_code`／`json()` 等をいずれも読まない（**I-VAL-1**。7.8節） |
| **S-4** | 新2 reason はいずれも安全側 `PROPAGATE_ORIGINAL_ERROR` へ落ちる |
| **S-5** | prompt・api_key・Base64 本体の非露出は、v6.11 の既存 `MSG-` guard がそのまま担保する |

### 7.8 外部応答値読み取りの positive allow-list 契約（I-VAL-1）

#### 7.8.1 なぜ関数全体の制限では不適当か（A-1）

v6.23 の I-EXC-1 は `_classify_api_error()` の**関数全体**を対象とし、
例外引数の出現を `isinstance` 第1引数のみに限定した。同関数は例外を「型で振り分ける」以外の
処理を持たないため、この強さで問題がなかった。

`_validate_response_structure()` は事情が異なる。同関数は応答値を**正当に読み取る**必要があり、
`isinstance(data, list)`・`len(data) != 1`・`data[0]`・`not b64_json` といった処理を含む。
関数全体を I-EXC-1 と同じ強さで制限すると、**正当な実装形まで拒否する過剰な guard**になる
（これは v6.23 設計書 16章 DEF-6.23-10 が「allow-list の形が `_classify_api_error()` とは異なる」と
指摘した点そのものである）。

**したがって本Releaseの guard は、関数全体ではなく「外部応答値に対する属性読み取り」のみを
検査対象とする**（**A-1**）。構造検査（`isinstance` / `len` / subscript / 真偽評価）は
検査対象外とし、制限しない。

#### 7.8.2 規範契約（I-VAL-1）

> **本節は Production実装前Gate確認（Gate 3・0.6節・19.3節・RA-Gate3-1）で改訂した。**
> 旧版は条件(a)を「当該関数本体に `ast.Attribute` ノードが 0 件であること」（関数全体を
> 対象とするスコープ限定なしの条件）としていたが、これは `_validate_response_structure()` が
> 正当に行う内部 Enum メンバ参照（`OpenAIImageGenerationErrorReason.INVALID_RESPONSE` 等）まで
> violation と誤判定する欠陥であった（AST 実測により発見。7.8.5節）。本節はこれを
> **外部応答値に由来する識別子集合 R へのスコープ限定**へ訂正したものである。

```text
【I-VAL-1】_validate_response_structure() の関数本体において、
          外部応答値に対する属性読み取りは、次の2形のみに限られる。

              getattr(<response 引数>, "data", <default>)
              getattr(<data 由来の値>, "b64_json", <default>)

          より厳密には、次の4条件を同時に満たすものだけを allow とする。

            (a) 外部応答値に由来する識別子集合 R を根とする ast.Attribute ノードが
                0 件であること（= R に属する識別子に対する、ドット記法による属性
                アクセスを一切行わない）。R は次の規則で導出する不動点集合である。

                  ・R の初期値 = {第1 positional parameter 名（response 引数）}
                  ・関数本体の Assign 文について、value が「func.id == "getattr" の
                    Call であり、その第1引数の根の Name（Subscript／Attribute
                    チェーンを遡った先頭）が R に属する」形であれば、当該 Assign の
                    単純 Name ターゲットを R へ追加する
                  ・上記を変化がなくなるまで反復する

                本Releaseの対象関数における実測値（AST実測。7.8.5節）：
                R = {response, data, b64_json}

                **R に属さない識別子（`OpenAIImageGenerationErrorReason` 等の内部
                Enum・定数）への属性アクセスは、本条件の対象外であり violation にならない**
                （許容対照 W-5、12.5.3節）。
            (b) 当該関数本体の getattr 呼び出しが ちょうど 2 件であること
            (c) 各 getattr 呼び出しが 3 引数形式であること
                （len(node.args) == 3 かつ node.keywords が空）
            (d) 各 getattr 呼び出しの第2引数が ast.Constant の str であり、
                その値が {"data", "b64_json"} のいずれかであること

          上記以外の形はすべて violation とする。
```

**本契約は「禁止する属性名を列挙しない」。** 許可される読み取り形を限定することにより、
禁止側は列挙せずとも構造的に到達不能になる。これは v6.23 が deny-list 方式から
positive allow-list 方式へ転換した判断（v6.23 設計書 0.5.1節）と同じ方針である。
R によるスコープ限定も同じ思想の延長であり、「外部応答値の読み取り経路」だけを
禁止対象とし、それ以外（内部 Enum・定数への正当な参照）を列挙で個別許可するのではなく、
**R という構造的な境界で自動的に対象外とする**。

#### 7.8.3 本契約が自動的に禁止するもの（列挙は例示であり定義ではない）

| 形 | 禁止される根拠 |
|---|---|
| `response.text` / `.content` / `.headers` / `.status_code` | (a) `ast.Attribute` 0件 |
| `response.json()` | (a) |
| `response.data`（ドット記法） | (a)。正当な読み取りも `getattr` 3引数形式に統一する |
| `getattr(response, "status_code", None)` | (d) 第2引数 allow-list 違反 |
| `getattr(response, "text", None)` | (d) |
| `getattr(response, attr_name, None)`（変数指定） | (d) 非 Constant |
| `getattr(response, "data")`（2引数） | (c) |
| 3件目以降の `getattr` | (b) |
| **SDK が将来追加する未知の属性** | (a) と (d) の双方により**列挙なしで自動的に禁止される** |

最後の行が本方式の中心的価値である。属性名を一切列挙していないにもかかわらず、
未知の属性名に対しても guard の保守なしに保証が持続する。

**上記はすべて根が `response`（R の初期要素）である。** したがって R スコープ限定
（7.8.2節）の下でも、上表の判定はいずれも変わらず禁止のまま成立する。

**本契約が禁止しないもの（R 外への正当な参照）**

`OpenAIImageGenerationErrorReason.INVALID_RESPONSE` / `INVALID_RESPONSE_STRUCTURE` 等、
`_validate_response_structure()` が return 文で構築する内部 Enum メンバへの参照は、
根が `OpenAIImageGenerationErrorReason` であり R = {`response`, `data`, `b64_json`} に
属さないため、**条件(a)の対象外であり禁止されない**（許容対照 W-5、12.5.3節）。

#### 7.8.4 検査範囲

検査対象は `_validate_response_structure()` の `ast.FunctionDef` 配下**のみ**とする。
module 全体を対象にしてはならない。`_build_generated_image()`・`generate()`・
`_classify_api_error()` は正当に他の処理を行うため、同一規則を適用すると違反が出る。
この「範囲限定そのもの」を `NOVALPARSE-SCOPE-FUNCTION-ONLY` で検証する（12.5.4節）。

#### 7.8.5 現行実装・改修後実装への適合性（AST実測。Production実装前Gate確認で解消。20章 U-1）

> **本節は Production実装前Gate確認（Gate 3）で、`.\venv\Scripts\python.exe` による
> AST 実測へ更新した。旧版は「静的読解による判定」であり、旧版の条件(a)（関数全体で
> `ast.Attribute` 0件）を前提に「適合」と誤って判定していた。実測の結果、関数内には
> `ast.Attribute` が2件存在する（いずれも内部 Enum メンバ参照）ことが判明し、これが
> 7.8.2節の条件(a) 訂正（R スコープ限定、RA-Gate3-1）の直接の契機となった。**

**現行実装（HEAD = `38e2487`、L195-210）に対する適合性（AST実測）**

| 条件 | 実測結果 | 判定 |
|---|---|---|
| (a) R を根とする `ast.Attribute` が0件 | 関数内の `ast.Attribute` は **L204・L208 の `OpenAIImageGenerationErrorReason.INVALID_RESPONSE`（計2件）のみ**存在する。両者の根は `OpenAIImageGenerationErrorReason` であり、R = {`response`, `data`, `b64_json`} には属さない。**R を根とする Attribute は0件** | **適合**（R スコープ版のみ。旧版の条件(a)＝関数全体で0件では **不適合**） |
| (b) `getattr` ちょうど2件 | L202 `getattr(response, "data", _MISSING)`・L206 `getattr(data[0], "b64_json", _MISSING)` の2件 | **適合** |
| (c) 3引数形式 | 両方とも `len(node.args)==3`・`node.keywords` 空 | **適合** |
| (d) 第2引数が `"data"` / `"b64_json"` | 両方とも `ast.Constant` の str で該当値 | **適合** |

**改修後実装に対する適合性**：I-2・I-3（L204・L208の reason 値差し替え）は return 文の
Attribute ノードの `attr` 名（`INVALID_RESPONSE` → `INVALID_RESPONSE_STRUCTURE`）を変えるのみで、
根は `OpenAIImageGenerationErrorReason` のまま不変であり R に属さない。`getattr` 呼び出し・
R の構成・構造検査・制御フローもいずれも変更しない。したがって
**改修後も R スコープ版 I-VAL-1 に適合し続ける**（旧版の条件(a)のままでは、改修後も
Attribute 2件が残存するため恒久的に不適合のままだった）。

> **注**：本節は Production実装前Gate確認（本改訂）で AST 実測により確定した。
> **20章 U-1 は本改訂で解消済みである。**

---

## 8. Public API

### 8.1 変更されるもの

| 対象 | 変更 |
|---|---|
| `OpenAIImageGenerationErrorReason` | Enum member を **13 → 15** へ純増（末尾追加） |
| `OpenAIImageGenerationError.reason` の**取りうる値** | 対象3経路（generic `except Exception`／`data` 不正／`b64_json` 不正）で**意図的に変更される** |

### 8.2 変更されないもの

| 対象 | 状態 |
|---|---|
| 既存13 reason の name・value・**定義順** | 完全に不変 |
| `openai_image_generation.__all__` | 3 symbol のまま不変（`OpenAIImageGenerator` / `OpenAIImageGenerationError` / `OpenAIImageGenerationErrorReason`） |
| `OpenAIImageGenerationError.__init__(message, reason)` | signature 不変 |
| `OpenAIImageGenerator.__init__` / `from_env()` / `generate()` / `output_mime_type` | signature 不変 |
| `_validate_response_structure(response)` | **signature・3要素返却形ともに不変**（6.2節・確定仕様） |
| `_classify_api_error(exc)` | **0 diff**（C-1） |
| `image_generation_fallback_policy` の全 Public API | 0 diff（G-8） |
| 全 exception message | 0 diff（7.6節） |
| 成功経路（`GeneratedImage` 生成・mime_type 決定） | 0 diff |

### 8.3 Public API 規模の変化

| 指標 | v6.23 | v6.24 | 差 |
|---|---|---|---|
| `OpenAIImageGenerationErrorReason` member 数 | 13 | 15 | +2 |
| `openai_image_generation.__all__` symbol 数 | 3 | 3 | ±0 |
| `image_generation_fallback_policy.__all__` symbol 数 | 4 | 4 | ±0 |
| public 関数・メソッドの signature 数 | 不変 | 不変 | ±0 |
| 新規 package | — | なし | ±0 |

---

## 9. Runtime Action Zero Diff（Z-1〜Z-8）

### 9.1 用語の定義

本Releaseは **Runtime Action Zero Diff（Z-1〜Z-8）** を主張する。
**本Releaseが保証する不変範囲はRuntime Action Zero Diff（Z-1〜Z-8）に限定される。**
public `.reason` は対象3経路で意図的に変更されるためである（8.1節・9.5節）。
この区別は v6.23 が確立した規約に従う。

| ID | 名称 | 定義 | 成立 |
|---|---|---|---|
| **Z-1** | **Runtime Action Zero Diff** | 任意の例外・応答を入力としたとき、`decide_image_generation_fallback()` が返す `action`、および `ArticleFeaturedMediaRuntime.apply()` の `status` が v6.23.0 時点と完全に一致する | **成立**（9.2節） |
| **Z-2** | **Category Zero Diff** | 同上の条件で `decision.category` が v6.23.0 時点と完全に一致する | **成立**（9.2節） |
| **Z-3** | **main.py Zero Diff** | `main.py` に**バイト単位で差分がない** | **成立**（無改修。9.4節） |
| **Z-4** | **Message Zero Diff** | 全 raise 経路の message 文字列が完全一致 | **成立**（7.6節） |
| **Z-5** | **Chaining Zero Diff** | `__cause__` / `__context__` の到達不能性が不変 | **成立**（C-5 を無変更） |
| **Z-6** | **Signature Zero Diff** | すべての public signature が不変。`_validate_response_structure()` の3要素返却形を含む | **成立**（8.2節） |
| **Z-7** | **Success-path Zero Diff** | 成功時の `GeneratedImage` 生成経路・`MediaUploadResult`・`ArticleData` 束縛が不変 | **成立**（成功経路を無変更） |
| **Z-8** | **CONTINUE Set Zero Diff** | `_CONTINUABLE_REASONS` の内容が不変（4値） | **成立**（G-8：ファイル 0 diff） |
| **✗** | 観測可能なあらゆる出力が不変であるとの主張 | 観測可能なあらゆる出力が不変 | **成立しない。主張してはならない**（9.5節） |

### 9.2 Z-1 / Z-2 の成立根拠

**段1：新2値の category**

3.4節のとおり `decide_image_generation_fallback()` の OpenAI 分岐は
`_REJECTED_REASONS` → `_CONTINUABLE_REASONS` → `else` の順に評価する。
`UNEXPECTED_EXCEPTION` / `INVALID_RESPONSE_STRUCTURE` はいずれの `frozenset` にも属さないため
`else`（L173-176）へ落ち、`UNCLASSIFIED` になる。

**段2：置換前後の category が一致する**

| 経路 | v6.23 の reason → category | v6.24 の reason → category | category |
|---|---|---|---|
| generic `except Exception` | `UNKNOWN` → `UNCLASSIFIED` | `UNEXPECTED_EXCEPTION` → `UNCLASSIFIED` | **一致** |
| `data`／`b64_json` 構造不正 | `INVALID_RESPONSE` → `UNCLASSIFIED` | `INVALID_RESPONSE_STRUCTURE` → `UNCLASSIFIED` | **一致** |
| その他すべての経路 | 変更なし | 変更なし | **一致** |

**したがって Z-2 が成立する。**

**段3：category が一致すれば action も一致する**

`ImageGenerationFallbackDecision.action` は `_ACTION_BY_CATEGORY`（L80-91）から
category のみによって導出される read-only property である。category が一致する以上、
action も一致する。**したがって Z-1 が成立する。**

**段4：`ArticleFeaturedMediaRuntime.apply()` の status**

`ArticleFeaturedMediaRuntime`（v6.20.0）は `decide_image_generation_fallback()` の
`action` のみを見て `PROPAGATE_ORIGINAL_ERROR` は bare `raise`、
`CONTINUE_WITHOUT_FEATURED_MEDIA` は `CONTINUED_WITHOUT_FEATURED_MEDIA` status を返す。
action が不変である以上、status も不変である。

なお `ArticleFeaturedMediaRuntimeResult.category` は CONTINUE 時のみ非 None であり、
CONTINUE 対象（4値）は本Releaseで変更されない。したがって `main.py` L192 が
console へ出力する `result.category.value` の文字列も不変である。

### 9.3 CONTINUE 拡大がないことの構造的保証

| 保証 | 根拠 |
|---|---|
| `_CONTINUABLE_REASONS` が変わらない | `image_generation_fallback_policy.py` が**ファイル単位で 0 diff**（G-8・AC-21） |
| CONTINUE となる reason が4値ちょうど | v6.19 E2E の `CONT-EXACTLY-4`（L519-523）が**期待値変更なしで PASS する**ことが直接証拠 |
| category split の `IMAGE_GENERATION_FAILED` が 4 のまま | 7.5.1節の split 表。v6.19 E2E の `REASON-SPLIT-*` が実測集計で確認 |

### 9.4 main.py Zero Diff

`main.py` は画像系 package として `article_featured_media_runtime` のみを参照する
（v6.21.0 が確立した contract）。本Releaseは同 package を改修しないため、
`main.py` は**バイト単位で無変更**である。

**検証方法（Release Review Amendment・第5回改訂で確定）**：`main.py` は baseline
`38e2487` からの**読み取り専用 Git 差分実測**（`git diff --name-only <baseline> -- main.py`）
により変更がないことを確認した（AC-24）。`main.py` は新規 v6.24 E2E の `NOIMPACT-`
（`_protected_paths`）による**機械検証対象には含まれない**（`_protected_paths` 22件に
`main.py` は含まれない。11.1節・22件の内訳を参照）。一方 `image_generation_fallback_policy.py`
は同 E2E の `POLICYFILE-DIFF-EMPTY`／`POLICYFILE-AST-EQUAL`（既存の baseline 固定
equality／AST 等価検査）により機械的に担保されている（9.6節・AC-21）。この区別は
Runtime Action Zero Diff（Z-1〜Z-8）の内容・成立範囲を変更するものではなく、
Z-3 の**検証方法の記述を実態へ一致させる訂正**である。

### 9.5 意図的に変更される公開値

```text
# v6.23.0 時点
generate() が generic except Exception 経路で失敗
    → OpenAIImageGenerationError(_MSG_UNEXPECTED_ERROR, reason=UNKNOWN)

_validate_response_structure() が data／b64_json 構造不正を検出
    → OpenAIImageGenerationError(_MSG_INVALID_RESPONSE_STRUCTURE, reason=INVALID_RESPONSE)

# v6.24.0 以降
generate() が generic except Exception 経路で失敗
    → OpenAIImageGenerationError(_MSG_UNEXPECTED_ERROR, reason=UNEXPECTED_EXCEPTION)
                                  ^^^^^^^^^^^^^^^^^^^^ message は同一
_validate_response_structure() が data／b64_json 構造不正を検出
    → OpenAIImageGenerationError(_MSG_INVALID_RESPONSE_STRUCTURE, reason=INVALID_RESPONSE_STRUCTURE)
                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^ message は同一
```

`.reason` は public 属性であるため、**この変更をもって観測可能なあらゆる出力が不変であるとは
主張することはできない**。本Releaseが保証する不変範囲は Runtime Action Zero Diff
（Z-1〜Z-8）に限られる。

### 9.6 v6.19 の安全側性質（C-17）の維持

本Releaseは `_CONTINUABLE_REASONS` / `_REJECTED_REASONS` のいずれにも触れない。
両集合は allow-list のまま残り、**v6.24 以降にさらに reason が追加されても
新値は自動的に `UNCLASSIFIED`（安全側）へ落ちる**。G-11 が成立する。

---

## 10. 実装計画（File Change Plan）

### 10.1 Production Code（1ファイル）

#### `src/openai_image_generation/openai_image_generator.py`

| # | 箇所 | 変更 |
|---|---|---|
| **I-1** | L77 の直後 | Enum へ `UNEXPECTED_EXCEPTION = "unexpected_exception"`・`INVALID_RESPONSE_STRUCTURE = "invalid_response_structure"` をこの順で追加。**既存13値は1文字も変更しない** |
| **I-2** | L204 | 返却 reason を `INVALID_RESPONSE` → `INVALID_RESPONSE_STRUCTURE` |
| **I-3** | L208 | 同上 |
| **I-4** | L351 | 代入 reason を `UNKNOWN` → `UNEXPECTED_EXCEPTION` |
| **I-5** | L57-63（Enum class docstring） | v6.24 の追加と、`UNKNOWN`／`INVALID_RESPONSE` の適用範囲縮小を1〜2文で追記 |

**変更してはならない箇所（実装工程の禁止事項）**

| 箇所 | 理由 |
|---|---|
| L50-53（message 定数） | Z-4 |
| L64-77（既存13 Enum member） | AC-1 |
| L107-192（`_classify_api_error()` 本体・docstring。Production実装前Gate確認で実測訂正：旧記載L134-192） | C-1・G-9。**0 diff** |
| L202・L206（`getattr` 呼び出し） | I-VAL-1 適合性の維持 |
| L203・L207（`isinstance` / `len` / 真偽評価） | 構造検査の contract |
| L210（正常時 return） | Z-7 |
| L213-232 のうち L222・L226 | C-4 |
| L229・L354（`from None`） | Z-5 |
| L345-349（`try` / `except` 節の順序・条件式） | C-6 |
| L356（成功時 return） | Z-7 |

**docstring 変更方針（A-8）**

Production docstring の変更は、**既存記述が不正確になる場合のみ**行う。

| docstring | 判定 | 理由 |
|---|---|---|
| Enum class docstring（L57-63） | **変更する（I-5）** | 現行文は「v6.23.0 で要求拒否系4型を細分化した」で記述が止まっており、本Release後は Enum の現状を説明できない。また `UNKNOWN`／`INVALID_RESPONSE` の適用範囲縮小が記載されないと**不正確**になる |
| `_classify_api_error()` docstring（L108-131。Production実装前Gate確認で実測訂正：旧記載L110-131） | **変更しない** | 同関数は 0 diff。判定順序 contract・I-EXC-1 の記述はいずれも本Release後も正確 |
| `_validate_response_structure()` docstring（L196-201） | **変更しない** | 現行文は「いずれのフィールドも欠落・不正な場合は error_message／error_reason を設定し」であり、具体的な reason 名を含まない。本Release後も**正確なまま**である。I-VAL-1 契約の所在は本設計書 7.8節が担う |
| module docstring・その他 | **変更しない** | 不正確化しない |

#### 変更しないと明示する Production ファイル

| ファイル | 検証方法 |
|---|---|
| `src/image_generation_fallback_policy/image_generation_fallback_policy.py` | **baseline `38e2487` からの差分が空**であることを guard で検証（AC-21・G-8） |
| `src/image_generation_fallback_policy/__init__.py` | 同上 |
| `src/openai_image_generation/__init__.py` | 同上（`__all__` 3 symbol 不変。AC-4） |
| `main.py` | 差分空。**読み取り専用 Git 差分実測**で確認（`NOIMPACT-` guardの機械検証対象には含めない。AC-24・Z-3・9.4節） |
| `src/wordpress_media/` 配下 | `_protected_paths` による containment |
| `src/article_featured_media*/`（4 package） | 同上 |
| `src/ai_image_generation/`・`src/generated_image_*/`（2 package）・`src/image_generation_config/`・`src/article_image_prompt_construction/` | 同上 |
| `src/image_resolver.py`・`src/outputs/`・`src/logger/` ほか `_protected_paths` 22件 | 同上 |
| `requirements.txt`・`.env.example` | 無変更 |

### 10.2 E2E（新規1・更新5）

| # | ファイル | 種別 | 内容 |
|---|---|---|---|
| **T-1** | `tests/test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_refinement_foundation.py` | **新規** | 12章の prefix 構成 |
| **T-2** | `tests/test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py` | 更新 | L964 の期待 reason（`_resp_cases` 12件分）／L1103 の期待 reason（`ERR-UNKNOWN-EXC`）。**L1002・L1013（B64 系）と L1101（`ERR-GENERIC`）は変更しない** |
| **T-3** | `tests/test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py` | 更新 | 13.2節 |
| **T-4** | `tests/test_e2e_v6_21_0_article_featured_media_runtime_wiring.py` | 更新 | allow-list とラベルのみ（11.2節） |
| **T-5** | `tests/test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py` | 更新 | allow-list とラベルのみ（11.3節） |
| **T-6** | `tests/test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py` | 更新 | allow-list とラベル ＋ **DEF-6.23-12 修正**（11.4節） |

### 10.3 ドキュメント（Documentation Integration 工程。第4回改訂・第5回改訂で実施済み）

| ファイル | 更新内容 | 状況 |
|---|---|---|
| `docs/ROADMAP.md` | DI-11 後半の未着手候補エントリを `[ ]` → `[x]` 化し完了内容を記載。v6.24.0 エントリを新規追加。Deferred状態を同期 | **実施済み（第4回改訂）** |
| `docs/CHANGELOG.md` | `[v6.24.0]` セクションを新設し Added／Changed／Contract概要／Runtime Action Zero Diff／Tested／Deferred を記載 | **実施済み（第4回改訂）** |
| `docs/architecture.md` | v6.23.0層セクションへ v6.24.0 追記の blockquote を追加し、新規「OpenAI Image Generation Unknown and Invalid Response Reason Refinement Foundation層」節をファイル末尾に追加 | **実施済み（第4回改訂）** |
| `docs/ROADMAP.md`・`docs/CHANGELOG.md`・`docs/architecture.md` | **Release Review Findings Amendment**（Major-1：main.py検証方法の記述訂正。Major-2：v6.23記録3箇所の遡及編集を人間承認済みDocumentation Amendmentとして正式記録化・revertせず。Minor-1：architecture.md Deferred一覧の対応ずれ修正。Minor-2：CHANGELOG見出し日付更新。詳細は19.6節） | **実施済み（第5回改訂・本改訂）** |

**上記3ファイルは第1回〜第3回改訂の時点では変更していなかったが、第4回改訂で
Documentation Integration として更新し、第5回改訂（本改訂）で Release Review
Findings Amendment（19.6節）として追加更新した。** Release Review は実施済みだが
Verdict は Changes Required のまま再レビュー前であり、commit・push・Release Review
再実施のいずれも本改訂でも実施していない。

---

## 11. guard／baseline 更新計画

### 11.1 適用される GR 条項（v6.23 から継承）

| ID | 条項 | 本Releaseでの適用 |
|---|---|---|
| **GR-1** | 保護対象を削除しない | `_protected_paths` 22件を3 guard すべてで**そのまま維持** |
| **GR-2** | 既存 guard の `BASELINE_COMMIT` を書き換えない | v6.21 `8d89506`／v6.22 `578af6b`／v6.23 `8fd8453` を**そのまま維持** |
| **GR-3** | 「差分ゼロ」検査を「差分が allow-list の範囲内」検査へ精緻化する | 既に精緻化済み。allow-list リテラルのみ更新 |
| **GR-4** | allow-list へ登録できるのは、**本設計書 10章が明示的に宣言したファイルのみ** | Production は `openai_image_generator.py` **1件のみ**。実装工程での追加は禁止 |
| **GR-5** | 既存 guard の精緻化はアサーション件数を変えない方法で行う | v6.21／v6.22 は allow-list リテラルとラベルのみ（件数不変）。v6.23 は DEF-6.23-12 の解消により**意図的に増加**する（13.3節・A-4） |
| **GR-6** | 本Releaseは自身の E2E に、自身の baseline commit を固定した完全な guard を持つ | baseline `38e2487`。equality 検証＋実値ベース陽性対照 |
| **GR-7** | 許容件数をラベル文言へ埋め込まない | 新規 guard のラベルに件数を書かない |
| **GR-8** | 精緻化の内容と検査意図の保持根拠を設計書へ明記する | 本章がその記述である |
| **GR-9** | 保護対象パスへ触れるため、**それ以前に存在するすべての baseline 固定 guard（3件）**の allow-list を更新する | 11.2〜11.4節 |
| **GR-10** | 保護パスの**追加**は行わない | `src/openai_image_generation` は既に22件に含まれる |
| **GR-11** | package 削除がないため**適用外** | — |

### 11.2 v6.21 guard の更新（`test_e2e_v6_21_0_*.py`）

| 項目 | 扱い |
|---|---|
| `BASELINE_COMMIT`（L824、`8d89506`） | **変更しない**（GR-2） |
| `_protected_paths` 22件 | **変更しない**（GR-1） |
| Production source allow-list | `src/openai_image_generation/openai_image_generator.py` を**既存項目として維持**（v6.23 で追加済み） |
| test change allow-list | `test_e2e_v6_24_0_*.py` を追加 |
| assertion 件数 | **不変** |

### 11.3 v6.22 guard の更新（`test_e2e_v6_22_0_*.py`）

| 項目 | 扱い |
|---|---|
| `BASELINE_COMMIT`（L1013、`578af6b`） | **変更しない** |
| `_protected_paths` 22件 | **変更しない** |
| Production source allow-list | 同上（既存項目の維持） |
| test change allow-list | `test_e2e_v6_24_0_*.py` を追加 |
| assertion 件数 | **不変** |

### 11.4 v6.23 guard の更新 ＋ DEF-6.23-12 修正設計（`test_e2e_v6_23_0_*.py`）

#### 11.4.1 allow-list の更新

> **本節は Production実装前Gate確認（Gate 4）で実測結果へ更新した。** 旧版は
> 「見込み」「実測確定が前提」と留保していたが、baseline `8fd8453` から現在（HEAD =
> `38e2487`）までの実差分を `git diff --name-only` で実測し、確定した。

| 項目 | 扱い |
|---|---|
| `BASELINE_COMMIT`（L1116、`8fd8453`） | **変更しない**（実測により本Release時点でも変更不要と確定） |
| `_protected_paths` 22件（L1126-） | **変更しない**（実測により本Release時点でも変更不要と確定） |
| `_allowed_source_changes`（L1147-1159） | **既存2パス構成を維持する（実測確定）**。`git diff --name-only 8fd8453 -- src/openai_image_generation` の実測結果は `openai_image_generator.py` の1件のみであり、既存 allow-list の範囲内（containment 充足）。v6.24 の Production 変更（I-1〜I-5、10.1節）も同ファイルのみを対象とするため、実装後も範囲内に収まる。**リテラル変更は不要と確定した**（旧 U-6） |
| `_allowed_test_changes`（L1202-1208） | `test_e2e_v6_24_0_*.py` を追加（必須。11.2節・11.3節も同様） |
| `NOIMPACT-SCOPE` / `-COVERAGE` / `-EXACT` | **検査ロジック・期待値・件数を一切変更しない** |

**実測結果（Production実装前Gate確認・Gate 4。推測ではなく `git diff` 実測に基づく）**：

```text
git diff --name-only 8fd845348d1ee4c80db8de2942da5f99c2bcf0fd -- src/openai_image_generation
  -> src/openai_image_generation/openai_image_generator.py（1件のみ）

git diff --name-only 8fd845348d1ee4c80db8de2942da5f99c2bcf0fd -- src/image_generation_fallback_policy
  -> src/image_generation_fallback_policy/image_generation_fallback_policy.py（1件のみ）

git diff --name-only 8fd845348d1ee4c80db8de2942da5f99c2bcf0fd -- main.py
  -> （差分なし。Z-3 成立）
```

いずれも既存 allow-list の範囲内であり、**source allow-list（v6.21／v6.22／v6.23 の3 guard とも）の
リテラル変更は不要と確定した。** 実装完了後の最終確認は、新規 E2E 自身の equality 検査
（11.5節）と本 guard の containment 検査が、実際の変更後差分に対して機械的に再実施する
（18章 工程3・手順22）。

#### 11.4.2 DEF-6.23-12 修正設計

**現状（実装確認済み）**：L1232-1242 の陽性対照2件は、実 `_changed`（`git diff` 出力）も
実 allow-list 値も参照せず、ハードコードされたリテラル集合の演算で**無条件に PASS する恒真式**である。

```python
# L1235（現状）── 常に True。guard の実値と無関係
len({"src/openai_image_generation/openai_image_generator.py"} - frozenset()) > 0

# L1240-1241（現状）── 常に True
len(frozenset({"src/openai_image_generation/never_changed.py"})
    - {"src/openai_image_generation/openai_image_generator.py"}) > 0
```

**修正設計**：実 `_changed_actual` と実 allow-list 値を参照する陽性対照へ置換する。

```text
前提となる実測値（いずれも既存 guard が算出済みの値を再利用する）
    _rel             = "src/openai_image_generation"
    _changed_actual  = git diff --name-only --relative BASELINE_COMMIT -- <_rel> の実測集合
    _allowed_actual  = frozenset(_allowed_source_changes[_rel])
    _DUMMY           = "src/openai_image_generation/__positive_control_never_exists__.py"

D12-1  NOIMPACT-POSITIVE-PRECOND-CHANGED-NONEMPTY
       len(_changed_actual) > 0
       → 実差分が非空であることの事前検証。これが 0 なら以降の陽性対照は
         vacuous になるため、先に FAIL させる

D12-2  NOIMPACT-POSITIVE-PRECOND-DUMMY-ABSENT
       _DUMMY not in _changed_actual
       → ダミー path が実差分に含まれないことの事前検証

D12-3  NOIMPACT-POSITIVE-EMPTY-ALLOWLIST
       len(_changed_actual - frozenset()) > 0
       → allow-list を空にすると containment 検査が違反を検出することを、
         実 _changed_actual に対して確認する

D12-4  NOIMPACT-POSITIVE-UNCHANGED-ALLOWLIST
       len((_allowed_actual | {_DUMMY}) - _changed_actual) > 0
       → allow-list に書いたのに未変更の項目を coverage 検査が検出することを、
         実 allow-list 値に対して確認する

D12-5  NOIMPACT-POSITIVE-NONDESTRUCTIVE
       _allowed_source_changes が D12-1〜D12-4 の前後で不変
       （実行前に取得した deep snapshot との比較）
       → 陽性対照が元集合を破壊的変更していないことの確認
```

**設計上の遵守事項**

| ID | 内容 |
|---|---|
| **D-a** | `_allowed_actual \| {_DUMMY}` は**新しい frozenset を生成する**。`\|=`・`.add()`・`.update()` を使ってはならない（元集合の非破壊。D12-5 が機械的に確認する） |
| **D-b** | `NOIMPACT-SCOPE`（containment）・`NOIMPACT-SCOPE-COVERAGE`・`NOIMPACT-SCOPE-EXACT` の**検査ロジック・期待値・件数を一切変更しない**（弱体化の禁止） |
| **D-c** | `BASELINE_COMMIT` を書き換えない（GR-2） |
| **D-d** | `_protected_paths` 22件を削除しない（GR-1） |
| **D-e** | Scenario ID `NOIMPACT-POSITIVE-EMPTY-ALLOWLIST` / `NOIMPACT-POSITIVE-UNCHANGED-ALLOWLIST` を**維持**し、差分読解性を保つ |
| **D-f** | assertion は**増加のみ許容**（2 → 5、+3）。既存 assertion の削除は禁止 |
| **D-g** | 修正後、ラベルの主張（「差分が検出される」「coverage が検出する」）が**実態と一致する**こと |

### 11.5 v6.24 自身の guard（GR-6・A-7）

**確定仕様**：Production source allow-list と test change allow-list を**別変数として分離する**（**A-7**）。
両者を1つの集合へ混在させてはならない。

```text
BASELINE_COMMIT = "38e2487db5760034f4a994319350244960a42e1b"

■ Production source allow-list（1ファイルのみ。GR-4）
_allowed_source_changes = {
    "src/openai_image_generation": frozenset({
        "src/openai_image_generation/openai_image_generator.py",
    }),
}
検査： containment（changed ⊆ allowed）
     ＋ coverage（allowed ⊆ changed）
     ＋ exact（equality）

■ test change allow-list（6ファイル。source とは別変数）
_allowed_test_changes = {
    "test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py",
    "test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py",
    "test_e2e_v6_21_0_article_featured_media_runtime_wiring.py",
    "test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py",
    "test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py",
    "test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_refinement_foundation.py",
}
検査： containment のみ（tests は今後も増えるため equality を課さない）

■ _protected_paths 22件（v6.21／v6.22／v6.23 と同一のものを踏襲。GR-1）
検査： 存在・baseline 追跡・containment・untracked なし

■ 特記： image_generation_fallback_policy は Production source allow-list に
        含めない。したがって同 package の差分は containment 検査により
        「空でなければ FAIL」となる（G-8・AC-21 の機械的根拠）
```

**陽性対照は最初から実値ベースで実装する**（11.4.2 D12-1〜D12-5 と同型）。
v6.23 が恒真式を作り込んだ轍を踏まない。

### 11.6 M5-1 の扱い

**M5-1（match-case class pattern を構築形 guard の allow-list へ含めるか否か。DEF-6.23-5）は
本Releaseでも判断機会が発生しない。**

理由：本Releaseは構築形 guard（`GUARD-WMUE-CONSTRUCTION-SHAPE` 相当）を新設せず、
既存の同 guard の検査ロジックも変更しない。v6.11 の `OpenAIImageGenerationError.__init__` は
`reason` を既定値なしの必須引数として受け取るため、渡し忘れは `TypeError` で構造的に不可能であり、
v6.23 と同じく構築形 guard を必要としない。

したがって **M5-1 は Deferred 継続**とする（17章）。

---

## 12. E2E 契約（Test Strategy）

### 12.1 新規 E2E の prefix 構成

| prefix | 目的 | 対応 AC |
|---|---|---|
| `API-` | 15値の name／value／定義順、既存13値の不変、末尾追加、`__all__` 不変 | AC-1〜5 |
| `UNK-` | `UNKNOWN` 2経路分離。catch-all は `UNKNOWN` のまま／generic 経路は `UNEXPECTED_EXCEPTION`／両者が相異なる | AC-6〜8 |
| `RESP-` | `data`／`b64_json` 構造不正の全ケースが `INVALID_RESPONSE_STRUCTURE` | AC-9 |
| `B64-` | Base64 デコード失敗・0バイトが `INVALID_RESPONSE` のまま | AC-10 |
| `SPLIT-` | `RESP-` 群と `B64-` 群の reason が相異なる（DEF-6.23-4 解消の直接証拠） | AC-11 |
| `COMPAT-` | 既存10経路の reason／message 完全不変 | AC-12 |
| `POLICY-` | 15値全数の category／action 写像・split 4/5/2/4・合計15・stray なし | AC-14〜17, AC-20 |
| `CONT-` | `_CONTINUABLE_REASONS` 4値不変・CONTINUE が正確に4値・新2値は CONTINUE でない | AC-18, AC-19 |
| `ZERODIFF-` | 既存13値の action／category が v6.23 時点と一致。新2値が安全側 | AC-15, AC-16 |
| `POLICYFILE-` | `image_generation_fallback_policy.py` の baseline 差分空・AST 等価 | AC-21 |
| `ASTEQ-` | `_classify_api_error()` の baseline AST 等価（0 diff の機械的確認） | AC-27 |
| `NOVALPARSE-` | I-VAL-1 の positive allow-list AST 検査（12.5節） | AC-28 |
| `CHAIN-` | 新2経路の `__cause__`／`__context__` 到達不能 | AC-23 |
| `MSG-` | message 定数集合の不変、secret 非露出 | AC-22, AC-29 |
| `SIG-` | `_validate_response_structure()` の signature・3要素返却形の不変 | AC-26 |
| `DEP-` | import 契約（新規依存なし） | — |
| `COMPATAPI-` | 周辺 Public API 不変 | AC-25 |
| `NOIMPACT-` | baseline `38e2487` 固定 guard（11.5節）＋実値ベース陽性対照 | AC-31 |
| `SOCKET-` | 実通信0件 | AC-30 |
| `ENV-` | 環境変数の復元・`os.environ` 全体不変 | — |

### 12.2 hermetic 要件

| ID | 要件 |
|---|---|
| **H-1** | 外部 API へ実接続しない。`socket.getaddrinfo` / `socket.socket.connect` を in-process で遮断し、遮断されていること自体を `SOCKET-` で検証する |
| **H-2** | credential を使用しない。実 `openai.OpenAI` client を構築しない |
| **H-3** | 実行前後で `os.environ` 全体が不変であること |
| **H-4** | 実行前後で Git 状態が不変であること（`git status --porcelain` が空のまま） |
| **H-5** | standalone script 形式とし、`.\venv\Scripts\python.exe` で直接実行できること |

### 12.3 陽性対照（vacuous pass 防止）

すべての AST guard・差分 guard に陽性対照を置く。
「検査が空振りしていないこと」を、検査対象の実測件数が 0 でないことで確認する。

| guard | vacuous 防止 |
|---|---|
| `NOVALPARSE-` | 関数が見つかること／`getattr` 出現数が 0 でないこと／陽性対照12形が検出されること |
| `ASTEQ-` | 対象関数が baseline と HEAD の双方で取得できること |
| `NOIMPACT-` | baseline commit が解決できること／実差分が非空であること（D12-1） |
| `POLICYFILE-` | baseline に追跡ファイルが存在すること |

### 12.4 構築形 guard を置かない判断

11.6節のとおり、`OpenAIImageGenerationError.__init__` の `reason` は既定値なしの必須引数であり、
渡し忘れは `TypeError` で構造的に不可能である。したがって v6.22 の
`GUARD-WMUE-CONSTRUCTION-SHAPE` 相当の構築形 guard は**不要**と判断する。
この判断により M5-1 の判断機会も発生しない。

### 12.5 `NOVALPARSE-` guard の規範仕様（I-VAL-1）

#### 12.5.1 検査アルゴリズム

> **本節は Production実装前Gate確認（Gate 3・RA-Gate3-1）で改訂した。** 旧版の手順3は
> 「当該 FunctionDef 配下の `ast.Attribute` ノードを列挙し、件数が0でなければ violation」と
> スコープ限定なしで規定していたため、内部 Enum メンバ参照（`OpenAIImageGenerationErrorReason.
> INVALID_RESPONSE` 等）まで violation と誤判定する欠陥があった。本節は R 導出手順（新手順3）を
> 追加し、Attribute 検査（旧手順3）を R スコープへ限定した（新手順4）ものへ改める。

```text
手順1  対象ファイルを ast.parse し、name == "_validate_response_structure" の
       FunctionDef / AsyncFunctionDef を1件取得する。
       取得できなければ FAIL（vacuous pass 防止その1）。

手順2  当該 FunctionDef の第1 positional parameter
       （posonlyargs + args の先頭）から応答引数名を決定する。
       引数名をテスト側にハードコードしてはならない。
       決定できなければ FAIL（vacuous pass 防止その2）。

手順3  外部応答値に由来する識別子集合 R を導出する。
         R の初期値 = {手順2で決定した引数名}
         当該 FunctionDef 配下の Assign 文のうち、value が「func.id == "getattr" の
         Call であり、その第1引数の根の Name（Subscript／Attribute チェーンを
         遡った先頭）が R に属する」形であるものについて、単純 Name ターゲットを
         R へ追加する。変化がなくなるまで反復する。
       R は少なくとも手順2の引数名を含むため、この時点で非空であることは構造的に
       保証される（vacuous pass 防止不要）。

手順4  当該 FunctionDef 配下の ast.Attribute ノードのうち、根の Name
       （Subscript／Attribute チェーンを遡った先頭）が R に属するものを列挙する。
       件数が 0 でなければ violation（条件 a）。
       **R に属さない識別子（内部 Enum・定数等）への属性アクセスは対象外とし、
       violation としない。**

手順5  当該 FunctionDef 配下の ast.Call のうち、
       func が ast.Name かつ func.id == "getattr" のものを列挙する。
       列挙数が 0 なら FAIL（vacuous pass 防止その3）。
       列挙数が 2 でなければ violation（条件 b）。

手順6  各 getattr Call について、次を「すべて」満たすときのみ allow とする。
         (c1) len(node.args) == 3
         (c2) node.keywords が空
         (d1) node.args[1] が ast.Constant であり value が str
         (d2) node.args[1].value in {"data", "b64_json"}
       上記以外はすべて violation として、行番号と違反条件を記録する。

手順7  violations が空であること、かつ allow 数 == getattr 出現総数（2）であることを
       検証する。
```

**手順4 が本 guard の中核である。** R を根とする `ast.Attribute` を 0 件に固定することにより、
`response.text` / `.content` / `.headers` / `.status_code` / `.json()` は
**属性名を1つも列挙することなく**構造的に到達不能になる。**同時に、R に属さない識別子
（内部 Enum メンバ参照等）は最初からスコープ外であり、誤検知されない。**

**手順6 の (d2) が第2の関門である。** `getattr` 経由での迂回（`getattr(response, "text", None)`）も
allow-list によって遮断される。

#### 12.5.2 陽性対照（12形・すべて違反として検出されること）

| ID | 形 | 例 | 違反条件 |
|---|---|---|---|
| **V-1** | ドット記法（正当な属性でも） | `response.data` | (a) |
| **V-2** | 応答本文 | `response.text` | (a) |
| **V-3** | 応答本文 | `response.content` | (a) |
| **V-4** | ヘッダ | `response.headers` | (a) |
| **V-5** | ステータス | `response.status_code` | (a) |
| **V-6** | 解析メソッド | `response.json()` | (a) |
| **V-7** | **未知属性** | `response.future_unknown_attr_xyz` | (a) |
| **V-8** | getattr 迂回 | `getattr(response, "text", None)` | (d2) |
| **V-9** | getattr 迂回 | `getattr(response, "status_code", None)` | (d2) |
| **V-10** | 2引数形式 | `getattr(response, "data")` | (c1) |
| **V-11** | 非 Constant 第2引数 | `getattr(response, attr_name, None)` | (d1) |
| **V-12** | getattr 3件目 | 正当な2件に加えて `getattr(x, "data", None)` を追加 | (b) |

**V-7 が本方式の中心的価値を実証する。** 属性名を一切列挙していないにもかかわらず、
存在しない未知の属性名が検出される。SDK が将来属性を追加しても guard の保守を要さない。

**V-1 は「正当に見える形も禁止する」ことの実証である。** 読み取り形を `getattr` 3引数へ
統一することにより、検査対象が `getattr` 呼び出しの集合に閉じる。

**R スコープ限定（7.8.2節）の下でも V-1〜V-12 の判定はすべて変わらない。** 上表のうち
条件(a)を根拠とする V-1〜V-7 は、いずれも根が `response`（R の初期要素）であるため、
R スコープ限定後も引き続き violation として検出される。V-8〜V-12 は条件(b)(c)(d)を
根拠としており、これらは R スコープ限定の対象外（本改訂で変更していない）である。

#### 12.5.3 陰性対照（5形・すべて違反0件で通過すること）

> **本節は Production実装前Gate確認（Gate 3・RA-Gate3-1）で W-5 を追加した。**

| ID | 形 | 例 | 期待 |
|---|---|---|---|
| **W-1** | 許可形1 | `getattr(response, "data", _MISSING)` | 違反0・allow 1 |
| **W-2** | 許可形2 | `getattr(data[0], "b64_json", _MISSING)` | 違反0・allow 1 |
| **W-3** | **構造検査（検査対象外）** | `isinstance(data, list)` / `len(data) != 1` / `data[0]` / `not b64_json` | 違反0（属性読み取りではないため制限しない） |
| **W-4** | 文字列・docstring 中の属性名 | `"""status_code を読んではならない。"""` | 違反0（`ast.Constant` は `ast.Attribute` ではない） |
| **W-5** | **許容対照（非違反対照）：内部 Enum 参照（R 外）** | `OpenAIImageGenerationErrorReason.INVALID_RESPONSE_STRUCTURE` | 違反0（根が `OpenAIImageGenerationErrorReason` であり、R = {`response`, `data`, `b64_json`} に属さないため、条件(a)の対象外。手順4は R を根とする Attribute のみを列挙するため、本形は列挙対象にすら入らない） |

**W-3 は本 guard が 7.8.1節の要求（関数全体を制限しない）を満たしていることの実証である。**
正当な構造検査が拒否されないことを保証する。

**W-5 は、条件(a)が R スコープ限定であることの実証であり、かつ本Releaseの実装が返す
`(message, reason, None)` の `reason` 部分（`INVALID_RESPONSE_STRUCTURE` 等）そのものが
誤検知されないことを直接確認する。** 旧文言（関数全体で `ast.Attribute` 0件）ではこの
参照自体が構造的に violation として誤検出される欠陥があり、Production実装前Gate確認
（AST実測、20章 U-1）で発見・修正した（7.8.2節・7.8.5節・0.6節・19.3節）。

#### 12.5.4 検査範囲限定の検証

`NOVALPARSE-SCOPE-FUNCTION-ONLY` は、同一規則を他関数
（`_build_generated_image()` / `generate()` / `_classify_api_error()`）へ適用した場合に
違反が検出されることを合成確認し、**対象範囲の限定そのもの**を検証する。
これらの関数は正当に他の処理を行うため違反が出るのが正しい挙動であり、
guard を module 全体へ広げてはならないことの根拠になる。

### 12.6 assertion の数え方と見込み内訳

#### 12.6.1 数え方の規約（v6.23 12.8.1節から継承）

| ID | 規則 |
|---|---|
| **R-a** | 1 assertion = `results_log` への1 append = `check()` の1回呼び出し。`check_true` / `check_false` / `check_contains` / `check_not_contains` はすべて `check()` へ委譲するため各1 assertion |
| **R-b** | K 要素のループ内に M 本の `check` がある場合は **K × M** assertion。if/else の各枝に1本ずつなら反復あたり1本 |
| **R-c** | parameterized case のリストは **要素数 × 1ケースあたりの check 本数** |
| **R-d** | 複合ヘルパは展開して数える（v6.11 `check_openai_error(marker=…)` は **4**、marker 省略時は **3**） |
| **R-e** | **反復回数 ≠ assertion 数。** 集約比較（N 通り回して結果を1回比較する形）は **1 assertion** |

#### 12.6.2 ブロック別内訳（実測確定。0.7節・19.4節）

| prefix | 主な内容 | 反復 | 1反復 | **assertion** |
|---|---|---|---|---|
| `API-` | COUNT-15 / NAMES-EXACT / VALUES-EXACT / VALUE-UNIQUE / VALUE[name]×15 / DEFINITION-ORDER / PREFIX-13-UNCHANGED / PKG-ROOT[新2]×2 / ALL-UNCHANGED | — | — | **24** |
| `UNK-` | catch-all／generic の2ケース × `check_openai_error(marker)` 4 ＝ 8 ＋ DISTINCT ＋ CATCHALL-STILL-UNKNOWN | 2 | 4 | **10** |
| `RESP-` | 構造不正12ケース × `check_openai_error()` 3 ＝ 36 ＋ REASON-UNIFORM | 12 | 3 | **37** |
| `B64-` | Base64 系6ケース × 3 ＝ 18 ＋ REASON-UNCHANGED | 6 | 3 | **19** |
| `SPLIT-` | RESP／B64 の reason 相異 ＋ 両群の reason 集合が交差しない | — | — | **2** |
| `COMPAT-` | 既存10経路の reason／message ×2 ＝ 20 ＋ `UNKNOWN` 存続（存在確認1・value確認1）＋ `INVALID_RESPONSE` 存続（存在確認1・value確認1）＝4（**Release Review Amendment・第5回改訂で訂正。`__all__` は `API-ALL-UNCHANGED`／`COMPATAPI-OPENAI-ALL` で、`REQUEST_REJECTED` の存続は `API-VALUE[REQUEST_REJECTED]`／`API-NAMES-EXACT` で別途担保する**） | 10 | 2 | **24** |
| `POLICY-` | CATEGORY[r]×15 / ACTION[r]×15 / COVERAGE-15 / SPLIT / SPLIT-TOTAL / NO-STRAY | — | — | **34** |
| `CONT-` | SET-EXACT / SIZE-4 / ACTUAL-EXACTLY-4 / NEW-NONE[2]×2 / FAILED-COUNT-4 / IMMUTABLE | — | — | **7** |
| `ZERODIFF-` | ACTION-V623[13]×13 / CATEGORY-V623[13]×13 / NEW-ACTION[2]×2 / NEW-CATEGORY[2]×2 / PARTIAL-ENUM-ONLY | — | — | **31** |
| `POLICYFILE-` | baseline 差分空 ＋ AST 等価 | — | — | **2** |
| `ASTEQ-` | `_classify_api_error()` 取得 ＋ AST 等価 | — | — | **2** |
| **`NOVALPARSE-`** | **FN-FOUND / PARAM-NAME / ATTRIBUTE-ZERO / GETATTR-COUNT-2 / ALLOWED-EQUALS-TOTAL / VIOLATIONS-EMPTY / SCOPE-FUNCTION-ONLY ＝7 ＋ 陽性対照12 ＋ 陰性対照5（W-5 を含む）** | — | — | **24** |
| `CHAIN-` | 新2経路 × `__cause__`／`__context__` | 2 | 2 | **4** |
| `MSG-` | message 定数集合の不変 ＋ secret 非露出3 | — | — | **4** |
| `SIG-` | signature 文字列 / 返却要素数3 / 正常時 return 形 | — | — | **3** |
| `DEP-` | openai module / policy module / import root | — | — | **3** |
| `COMPATAPI-` | 周辺 Public API 不変13項目 | — | — | **13** |
| `NOIMPACT-` | 22パス×4検査＝88 ＋ COVERAGE 1 ＋ EXACT 1 ＋ TESTS-SCOPE 1 ＋ NO-UNTRACKED-TESTS 1 ＋ baseline 解決 1 ＋ 実値ベース陽性対照 5 | 22 | 4 | **98** |
| `SOCKET-` | getaddrinfo 遮断 / connect 遮断 / 実 Client 非構築 | — | — | **3** |
| `ENV-` | 環境変数復元 / `os.environ` 全体不変 | — | — | **2** |
| | | | **合計（実測確定）** | **346** |

**この 346 は E2E限定テスト実測値である（乖離0。0.7節・19.4節）。** 設計時点の見込み値
345→346（Production実装前Gate確認で W-5 を追加したため）は、実測により**そのまま346で
確定した**。RB-15 の条件（乖離があれば本節の内訳で説明できること）は満たされている
（乖離自体が発生していない）。

#### 12.6.3 反復数と assertion 数が一致しない箇所（R-e の適用）

| 識別子 | 反復回数 | assertion 数 | 理由 |
|---|---|---|---|
| `POLICY-SPLIT` | 15（全 reason の集計） | **1** | 集計結果の dict を1回比較する |
| `POLICY-COVERAGE-15` | 15 | **1** | name 集合を1回比較する |
| `NOVALPARSE-VIOLATIONS-EMPTY` | getattr 出現数（2） | **1** | violations リストを空リストと1回比較する |
| `NOVALPARSE-ATTRIBUTE-ZERO` | Attribute 走査全件 | **1** | 件数を 0 と1回比較する |
| `SPLIT-DISJOINT` | 18（RESP 12 ＋ B64 6） | **1** | 2つの reason 集合の交差を空集合と1回比較する |

### 12.7 部分実装・片側 rollback の検出

| 破損シナリオ | 検出器 | 挙動 |
|---|---|---|
| Enum に2値を追加したが `_validate_response_structure()` を変更しなかった | `RESP-` 群 | 期待 `INVALID_RESPONSE_STRUCTURE` に対し実測 `INVALID_RESPONSE` で FAIL |
| Enum に2値を追加したが `generate()` を変更しなかった | `UNK-` 群 | 同上 |
| `_build_generated_image()` まで誤って変更した | `B64-` 群 | 期待 `INVALID_RESPONSE` に対し実測 `INVALID_RESPONSE_STRUCTURE` で FAIL |
| catch-all まで誤って変更した | `UNK-CATCHALL-STILL-UNKNOWN`・`ASTEQ-` | reason 不一致／AST 非等価で FAIL |
| fallback policy に「念のため」写像を追加した | `POLICYFILE-`・`NOIMPACT-SCOPE` | 差分非空で FAIL |
| Enum の定義順を変えた | `API-DEFINITION-ORDER`・`API-PREFIX-13-UNCHANGED` | FAIL |
| message を変えた | `MSG-`・`UNK-`・`RESP-`・`B64-`・`COMPAT-` | FAIL |

---

## 13. Formal Regression 計画

### 13.1 正式 Inventory

> **解消済み（20章 U-2。Production実装前Gate確認・Gate 2・0.6節・19.3節）**：
> 以下の26ファイルは、権威的記録（`docs/CHANGELOG.md` の各Release Tested節）と
> `tests/` 配下の実ファイル一覧の**双方から突合して確定した**。件数（26ファイル）・
> assertion数（個別合計＝総合値 4053 と算術的に一致）・重複／欠落／対象外混入の
> いずれも確認済みである。

```text
正式 Inventory 26ファイル（v6.23.0 時点。権威的記録と実ファイルの突合により確定）

 1. test_e2e_v1_11_0_save_result.py                                                      43
 2. test_e2e_v5_9_0_retry_runtime_loop_wiring_foundation.py                              64
 3. test_e2e_v6_0_0_retry_runtime_lock_foundation.py                                     43
 4. test_e2e_v6_1_0_retry_runtime_graceful_shutdown_foundation.py                        44
 5. test_e2e_v6_2_0_structured_loop_logging_foundation.py                                64
 6. test_e2e_v6_3_0_retry_metrics_foundation.py                                         174
 7. test_e2e_v6_4_0_retry_monitoring_foundation.py                                      171
 8. test_e2e_v6_5_0_retry_alert_foundation.py                                           131
 9. test_e2e_v6_6_0_retry_notification_foundation.py                                    135
10. test_e2e_v6_7_0_retry_notification_message_foundation.py                            117
11. test_e2e_v6_8_0_retry_notification_cli_report_wiring_foundation.py                  197
12. test_e2e_v6_9_0_wordpress_media_upload_foundation.py                                331
13. test_e2e_v6_10_0_ai_image_generation_contract_foundation.py                          78
14. test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py                       248
15. test_e2e_v6_12_0_generated_image_wordpress_media_upload_wiring_foundation.py          91
16. test_e2e_v6_13_0_article_featured_media_binding_foundation.py                       123
17. test_e2e_v6_14_0_article_featured_media_orchestration_foundation.py                 217
18. test_e2e_v6_15_0_image_generation_configuration_gate.py                              94
19. test_e2e_v6_16_0_generated_image_filename_policy_foundation.py                      143
20. test_e2e_v6_17_0_article_image_prompt_construction_foundation.py                    136
21. test_e2e_v6_18_0_article_featured_media_composition_root_foundation.py              146
22. test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py                     262
23. test_e2e_v6_20_0_article_featured_media_runtime_foundation.py                       198
24. test_e2e_v6_21_0_article_featured_media_runtime_wiring.py                           147
25. test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py 324
26. test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py 332
                                                                              合計 = 4053

＋ 新規1ファイル
  test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_refinement_foundation.py
= 正式 Inventory 27ファイル
```

各ファイルを**個別に**実行し、FAIL 0・SKIP 0・終了コード0・
外部 API 実接続0件・credential 使用0件・Git 状態不変を確認する。

```powershell
# 実行例（第4回改訂までに Formal Regression 工程で実際に使用した実行方法）
cd C:\Projects\claude-code-repository\projects\03_game_content_ai
.\venv\Scripts\python.exe tests\test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_refinement_foundation.py
```

**bare `python`・別 venv の使用は禁止する（Formal Regression 実測でも `.\venv\Scripts\python.exe` のみを使用したことを確認済み）。**

> **Formal Regression 実施済み（第4回改訂・0.8節・19.5節）**：上記27ファイルを正式Inventory順に
> 個別実行し、**既存26ファイル 4072/4072 PASS ＋ 新規v6.24.0 346/346 PASS ＝ 総合 4418/4418 PASS**
> を実測した。FAIL 0・SKIP 0・全ファイル終了コード0・外部API実接続0件。詳細は19.5節。

### 13.2 baseline への影響（既知差分の事前確定・Formal Regression 実測により正式確定）

v6.23.0 時点の baseline は **4053 assertions（26ファイル）**。
**E2E限定テスト実測（0.7節・19.4節）およびFormal Regression実測（0.8節・19.5節）の
両方により、既存26ファイルの新合計は 4053 − 332 ＋ 341 − 262 ＋ 272 ＝ 4053 ＋ 10 ＋ 9 ＝
4072 と確定し、両実測値は完全に一致した（乖離0）。**

#### 件数が変わらないファイル（23ファイル）

| ファイル | 変更 | 件数 |
|---|---|---|
| `test_e2e_v6_11_0_*.py` | L964 の `_resp_cases` ループの期待 reason、L1103 の `ERR-UNKNOWN-EXC` の期待 reason を差し替え。**ケース数もループ構造も変わらない** | **不変** |
| `test_e2e_v6_21_0_*.py` | allow-list リテラルとラベル文言のみ（GR-5） | **不変** |
| `test_e2e_v6_22_0_*.py` | allow-list リテラルとラベル文言のみ（GR-5） | **不変** |
| 他20ファイル | 無変更 | **不変** |

#### 件数が変わるファイル（2ファイル）

**(1) `test_e2e_v6_19_0_*.py`（+10）── A-3 に基づく案X の採用**

同ファイルは L292 `_ALL_REASONS = list(OpenAIImageGenerationErrorReason)` 駆動のループを持つため、
Enum 値追加により assertion が自動的に増える。加えて、**新2 reason はいずれも `UNCLASSIFIED` へ
落ちるため、`UNCLS-` セクション（L545-561）の対象へ追加する**（案X 採用。**A-3**）。

| 箇所 | 種別 | 増分 |
|---|---|---|
| L524 `for _reason in _ALL_REASONS:` の else 枝 `CONT-NOT-CONTINUE[{name}]` | 自動増 | **+2** |
| L717 `for _reason in _ALL_REASONS:` の `REASON-MATCH[{name}]` | 自動増 | **+2** |
| L545 `UNCLS-` の対象 tuple へ新2値を追加（1値あたり `UNCLS-CATEGORY` / `UNCLS-ACTION` / `UNCLS-NOT-FAILED` の3本） | **設計上の追加** | **+6** |
| L449 のループ（`decide()` を呼ぶだけで check がない） | 影響なし | 0 |
| L514 / L731 の内包表記 | 影響なし | 0 |
| **合計** | | **+10** |

**案X を採用した理由**：`UNCLS-` セクションは「`INVALID_RESPONSE`／`UNKNOWN` の安全側分類」を
検証する場所であり、新2値はまさにこのセクションの趣旨に合致する。
特に `UNCLS-NOT-FAILED`（`IMAGE_GENERATION_FAILED` へ落ちないことの回帰防止）を
新2値にも及ぼすことに、実質的な安全上の価値がある。

**期待値のみ更新する assertion（件数不変・6件）**

| assertion | 変更 |
|---|---|
| `REASON-ENUM-COUNT`（L707-711） | 期待値 13 → **15**、ラベル本文を更新 |
| `REASON-COVERAGE-COMPLETE`（L712-716） | `_expected_category_by_reason_name` へ**2キー追加**（いずれも `UNCLASSIFIED`）、ラベル更新 |
| `REASON-SPLIT-4-1-2-2`（L741-763） | 期待値 4/5/2/2 → **4/5/2/4**、ラベル本文のみ更新 |
| `REASON-SPLIT-TOTAL-9`（L764-769） | 期待値 13 → **15**、ラベル本文のみ更新 |
| `REASON-SPLIT-NO-STRAY-CATEGORY`（L770-779） | **変更不要**（category 集合は4種のまま） |
| `COMPAT-V611-REASON-COUNT-9`（L1300-1305） | 期待値 13 → **15**、ラベル本文のみ更新 |
| `CONT-EXACTLY-4`（L519-523） | **変更不要。期待値・実測値ともに4のまま PASS することが、CONTINUE 拡大がないことの直接証拠になる**（9.3節） |

**Scenario ID 据え置き方針**：`REASON-SPLIT-4-1-2-2` / `REASON-SPLIT-TOTAL-9` /
`COMPAT-V611-REASON-COUNT-9` は Scenario ID 自体に件数が埋め込まれているが、
**これらは現在件数を表すラベルではなく、差分読解性のために固定した履歴識別子である**
（v6.23 の方針をそのまま継承。詳細は下記「Scenario ID の性質」を参照）。
件数非依存 ID への改名は **DEF-6.23-11 として継続**する。

**(2) `test_e2e_v6_23_0_*.py`（実測 +9。設計時の宣言は +3）── DEF-6.23-12 の解消 ＋ 15値化に伴う構造的追随**

> **本節は E2E限定テスト実測（0.7節・19.4節）により訂正した。** 設計時点（11.4.2節）は
> DEF-6.23-12 の解消分（+3）のみを計上していたが、`test_e2e_v6_23_0_*.py` は
> `test_e2e_v6_19_0_*.py` と同型の `_ALL_REASONS = list(OpenAIImageGenerationErrorReason)`
> 駆動ループを2箇所持つ事実が計上漏れであった。実測により **+9** へ確定した。

11.4.2節のとおり、陽性対照2件を実値ベースの5 assertion（D12-1〜D12-5）へ置換した（+3）。
加えて、Enum 値追加（13→15）に伴い、既存の `_ALL_REASONS` 駆動ループが自動的に増加した（+6）。

| 箇所 | 種別 | 増分 |
|---|---|---|
| L1232-1242 の恒真式2件 → D12-1〜D12-5 の5件 | **設計上の追加（既存宣言どおり）** | **+3** |
| `_EXPECTED_NAME_VALUE` ループ（`API-VALUE[name]`、13→15エントリ） | **自動増（構造的追随）** | **+2** |
| `_ALL_REASONS` 駆動の `POLICY-CATEGORY[r]` ／ `POLICY-ACTION[r]` ループ（各13→15反復） | **自動増（構造的追随）** | **+4** |
| `NOIMPACT-SCOPE` / `-COVERAGE` / `-EXACT` | **変更禁止**（D-b） | 0 |
| allow-list リテラル・ラベル | 件数に影響しない | 0 |
| **合計（実測確定）** | | **+9** |

**期待値のみ更新する assertion（v6.23、件数不変）**：`API-COUNT-13`（13→15）、
`POLICY-COVERAGE-13`（13→15）、`POLICY-SPLIT-TOTAL`（13→15、split 表記を
4/5/2/2→4/5/2/4）、`REJECTSET-UNION-COVERAGE`（else 経路の期待集合4値→6値。
新2値が allow-list 方式により自動的に安全側へ落ちることの実証を拡張）。

**+9 が期待値緩和ではなく構造的追随である理由**：v6.24.0 の Production 実装（Enum 2値追加）
のみを適用し、v6.23 の allow-list 更新以外の追随を行わずに実行したところ、
`_EXPECTED_CATEGORY[_reason.name]` が `KeyError: 'UNEXPECTED_EXCEPTION'` で失敗し、
テストが成立しなかった（限定テスト実測時に確認）。これは v6.19.0（**A-3**・案X採用）が
既に確立した「Enum 全数を対象とする既存の表駆動全数検査は、Enum 値の増加に応じて
機械的に coverage 対象を拡張する（＝13値→15値）」という前例と同型であり、
**期待値・検査ロジックの緩和は一切ない**（F-1「既存シナリオの削除・弱体化が0件」を満たす）。

**Scenario ID の性質（v6.23）**：`API-COUNT-13` および `POLICY-COVERAGE-13` は、
ID 自体に旧件数（13）が埋め込まれたまま据え置いた**履歴識別子**である。ラベル本文
（`check()` の第1引数の説明文）は実測反映により「15値」「13→15」等の現在値を
正確に記述するよう更新済みであり、**ID トークンと説明文の意味は分離している**。
これは v6.19 の `REASON-SPLIT-4-1-2-2` 等と同じ方針（差分読解性を優先した据え置き）
であり、件数非依存 ID への改名は同じく **DEF-6.23-11** の対象として一元管理する。

### 13.3 Formal Regression の判定方針（A-4）

**「4053件固定維持」という判定は用いない。** 本Releaseは設計上、既存2ファイルへ
合計 +19（v6.19 +10 ＋ v6.23 +9）の assertion を追加した（実測確定。0.7節）。
判定は次の3点で行う（**A-4**）。

| ID | 判定基準 |
|---|---|
| **F-1** | **既存4053シナリオの削除・弱体化が0件であること。** 既存 assertion の削除、期待値の緩和、検査ロジックの無効化がいずれも発生していないこと（限定テスト実測で確認済み。0.7節） |
| **F-2** | **設計上の追加が本設計書の宣言どおりであること。** `test_e2e_v6_19_0_*.py` **+10**（13.2節・実測確定）、`test_e2e_v6_23_0_*.py` **+9**（13.2節・実測確定。設計時宣言+3から訂正）。**これ以外のファイルで件数が変動していないこと**（v6.11／v6.21／v6.22 はいずれも実測で件数不変を確認済み） |
| **F-3** | **新総数を実測すること。** 期待値は「4053 ＋ 19 ＋ 新規ファイル実測値」であり、Formal Regression（27ファイル合算）の事前固定は行わなかった。**実測の結果、新規ファイルは346・既存26ファイル新合計は4072・27ファイル総合は4418であり、限定テストの算出値と完全に一致した（乖離0）** |

**Formal Regression 正式実測総数** = 4053 ＋ 10 ＋ 9 ＋ 346 = **4418**
（27ファイルを対象とする正式な一括実行を第4回改訂で実施し、**この値で確定した**。
限定テスト時点の算出値と完全に一致し、乖離は観測されなかった。詳細は0.8節・19.5節）

**数値の区分**

| 区分 | 扱い |
|---|---|
| 設計時の見込み値 | 本設計書にかつて「見込み」と明記していた値。すべて下記いずれかの実測により確定済みであり、もはや残っていない |
| **限定テスト実測値（確定・0.7節）** | E2E限定テスト工程（Formal Regression とは別。個別6ファイルを `.\venv\Scripts\python.exe` で個別実行）により得た値。v6.11=248／v6.19=272／v6.21=147／v6.22=324／v6.23=341／v6.24（新規）=346。既存26ファイル新合計4072・27ファイル合算4418はこの実測値から算出した確定値である |
| **Formal Regression 実測値（確定・0.8節）** | Formal Regression 工程（27ファイルを対象とする正式な一括実行）で `.\venv\Scripts\python.exe` により得た値。**既存26ファイル4072/4072 PASS・新規v6.24 346/346 PASS・総合4418/4418 PASS。限定テスト実測値と完全一致（乖離0）。FAIL 0・SKIP 0・全ファイル終了コード0・外部API実接続0件** |
| baseline | v6.23.0 Finalize 時点の 4053（26ファイル） |

---

## 14. 受入条件（Acceptance Criteria）

### 14.1 taxonomy と分類

| ID | 内容 |
|---|---|
| **AC-1** | 既存13値の name・value・**定義順**が1文字も変わらない |
| **AC-2** | `UNEXPECTED_EXCEPTION = "unexpected_exception"`・`INVALID_RESPONSE_STRUCTURE = "invalid_response_structure"` が**末尾にこの順で**追加されている |
| **AC-3** | `len(list(OpenAIImageGenerationErrorReason))` == 15 |
| **AC-4** | `openai_image_generation.__all__` が3 symbol のまま不変 |
| **AC-5** | 15値の value 文字列に重複がない |
| **AC-6** | `openai.APIError` の未知 subtype → reason `UNKNOWN`・message「OpenAI Images APIの呼び出しに失敗しました」（**いずれも不変**） |
| **AC-7** | generic `except Exception` 経路 → reason `UNEXPECTED_EXCEPTION`・message「OpenAI Images APIの呼び出し中に予期しないエラーが発生しました」（**message 不変**） |
| **AC-8** | AC-6 と AC-7 の reason が**相異なる**（**DEF-6.23-3 解消の直接証拠**） |
| **AC-9** | `data` 不正（欠落／None／非 list／0件／2件）および `b64_json` 不正（欠落／None／非 str／空）の全ケース → reason `INVALID_RESPONSE_STRUCTURE`・message「OpenAI Images APIのレスポンス構造が不正です」（**message 不変**） |
| **AC-10** | Base64 デコード失敗・デコード結果0バイト → reason `INVALID_RESPONSE`（**不変**）・message も不変 |
| **AC-11** | AC-9 と AC-10 の reason が**相異なる**（**DEF-6.23-4 解消の直接証拠**） |
| **AC-12** | 既存10経路（AUTHENTICATION／PERMISSION_DENIED／RATE_LIMIT／TIMEOUT／CONNECTION／BAD_REQUEST／RESOURCE_NOT_FOUND／CONFLICT／UNPROCESSABLE_ENTITY／SERVER_ERROR）の reason・message が完全に不変 |
| **AC-13** | `REQUEST_REJECTED` が削除・改名されておらず、value が `"request_rejected"` のまま |

### 14.2 全数写像と Zero Diff

| ID | 内容 |
|---|---|
| **AC-14** | **15値すべて**について category が 7.5.1節の表と一致する（**Z-2**） |
| **AC-15** | **15値すべて**について action が 7.5.1節の表と一致する（**Z-1**） |
| **AC-16** | 新2値の category が `UNCLASSIFIED`、action が `PROPAGATE_ORIGINAL_ERROR` |
| **AC-17** | split が **4 / 5 / 2 / 4 = 15** である |
| **AC-18** | `_CONTINUABLE_REASONS` が4値のまま不変（**Z-8**）／CONTINUE となる reason が正確に4値ちょうど |
| **AC-19** | `_CONTINUABLE_REASONS` ∩ `_REJECTED_REASONS` = ∅ |
| **AC-20** | `ImageGenerationFailureCategory` 5値・`ImageGenerationFallbackAction` 2値のまま不変 |
| **AC-21** | `image_generation_fallback_policy.py` および同 package の `__init__.py` の baseline `38e2487` からの差分が**空**である（**G-8・Z-8 の機械的根拠**） |
| **AC-22** | 全 raise 経路の message が baseline 時点の文字列と1文字も違わない（**Z-4**） |
| **AC-23** | 新2経路の例外の `__cause__` / `__context__` がいずれも `None`（**Z-5**） |
| **AC-24** | `main.py` の baseline からの差分が**空**であることを、baseline `38e2487` からの**読み取り専用 Git 差分実測**（`git diff --name-only` の出力が空）で確認した（**Z-3**）。`main.py` は新規 v6.24 E2E の `NOIMPACT-`（`_protected_paths`）による機械検証対象には含まれない（9.4節・Release Review Amendment・第5回改訂） |
| **AC-25** | 周辺 Public API（`OpenAIImageGenerator.__init__` / `from_env()` / `generate()` / `output_mime_type` / `OpenAIImageGenerationError.__init__`）の signature が不変（**Z-6**） |
| **AC-26** | `_validate_response_structure()` の signature および3要素返却形が不変。正常時 `(None, None, b64_json)` の形も不変（**Z-6**） |
| **AC-27** | `_classify_api_error()` が baseline と **AST 等価**である（**C-1・G-9 の 0 diff の機械的確認**） |
| **AC-28** | `_validate_response_structure()` の関数本体が **I-VAL-1 に適合**する。外部応答値に由来する識別子集合 R = {`response`, `data`, `b64_json`} を根とする `ast.Attribute` が0件・`getattr` ちょうど2件・全件3引数形式・第2引数が `{"data","b64_json"}` の Constant。**R外の識別子（内部 Enum メンバ参照等）への属性アクセスは対象外**（12.5節 AST 検査・許容対照 W-5） |
| **AC-29** | prompt・api_key・Base64 本体が例外へ非露出（既存 `MSG-` の維持。**S-5**） |
| **AC-30** | 外部 API 実接続0件・credential 使用0件（`SOCKET-`・`ENV-`） |

### 14.3 guard / Regression / DEF-6.23-12

| ID | 内容 |
|---|---|
| **AC-31** | v6.24 自身の baseline 固定 guard（`BASELINE_COMMIT = 38e2487…`）を持ち、Production source allow-list（**1ファイル**）について **equality（containment ∧ coverage）** を検査する。**test change allow-list は別変数として分離**されている（**A-7**） |
| **AC-32** | v6.21／v6.22／v6.23 の3 guard は **allow-list とラベルのみ**を更新し、`BASELINE_COMMIT`・`_protected_paths` 22件を変更していない（GR-1・GR-2） |
| **AC-33** | **DEF-6.23-12 解消**：v6.23 の陽性対照2件が実 `_changed_actual`／実 allow-list 値を参照し、恒真式でなくなっている（11.4.2節 D12-1〜D12-5） |
| **AC-34** | DEF-6.23-12 修正後も `NOIMPACT-SCOPE` / `-COVERAGE` / `-EXACT` の検査ロジック・期待値・件数が不変（D-b） |
| **AC-35** | DEF-6.23-12 の陽性対照が `_allowed_source_changes` を破壊的に変更していない（D-a・D12-5） |
| **AC-36** | Formal Regression：正式 Inventory **27ファイル**、13.3節 F-1／F-2／F-3 をすべて満たす。FAIL 0・SKIP 0・全ファイル終了コード0・外部 API 実接続0件 |
| **AC-37** | allow-list に 10章が宣言していないファイルが登録されていない（GR-4） |

---

## 15. リスク

| ID | リスク | 影響度 | 緩和策 |
|---|---|---|---|
| **R-1** | `_validate_response_structure()` の reason 差し替え時に、Base64 系経路（L222・L226）まで誤って変更する | **中** | AC-10・AC-11 が両者の分離を直接検証。v6.11 の `B64-*` 6ケースが既存期待値のまま回帰検出（12.7節） |
| **R-2** | `generate()` の `except Exception` を触る際に `except openai.APIError` 節の順序・条件を動かす | **中** | AC-6・AC-27（`_classify_api_error()` の AST 等価）・`ERR-GENERIC` の期待値不変で検出 |
| **R-3** | 新 reason を `image_generation_fallback_policy.py` へ「念のため」明示写像として追加し、G-8／Z-8 を破る | **中** | AC-21（差分空）が機械的に検出。10.1節「変更しないと明示する Production ファイル」を実装工程の禁止事項として掲示 |
| **R-4** | 3つの既存 baseline guard の allow-list 更新漏れ | **中** | Formal Regression で必ず顕在化。18章 作業順の工程4で手順化 |
| **R-5** | DEF-6.23-12 修正時に既存 coverage／exact guard を弱める | **中** | D-b・AC-34。修正前後で当該3 assertion の AST が等価であることを確認する |
| **R-6** | `NOVALPARSE-` guard を関数全体の制限として実装してしまい、正当な構造検査（`isinstance` / `len` / subscript）や R 外の内部 Enum 参照まで拒否する | **中** | 7.8.1節・**A-1**。陰性対照 **W-3・W-5** が過剰拒否を検出する。旧文言（R スコープ限定なし）は Production実装前Gate確認（Gate 3）で AST 実測により実際に検出・修正済み（RA-Gate3-1、0.6節） |
| **R-7** | `INVALID_RESPONSE` の名称が範囲縮小後の実態を表さなくなる | 低 | **IL-6.24-1** として受容（16章）。改名は後方互換を破るため行わない |
| **R-8** | baseline 固定 guard が3→4件へ増え、次Release以降の O(N) 保守コストがさらに増大 | 低〜中 | **DEF-6.23-9 の優先度を引き上げて記録**（解消は本Release対象外・N-9） |
| **R-9** | Enum docstring 更新の際に既存13値の定義行へ意図せず触れる | 低 | AC-1・RB-6。docstring は class 直下のみを対象とする（I-5） |
| **R-10** | ~~新規 E2E の assertion 実測値が見込み 346 から乖離する~~ **解消済み**：限定テスト実測（0.7節）で346/346・乖離0を確認した | 低 | 12.6.2節の内訳で説明できることを RB-15 の条件としていたが、乖離が発生しなかったため条件充足不要のまま完了した |

---

## 16. Inherited Limitations

| ID | 内容 | 扱い |
|---|---|---|
| **IL-6.24-1** | **`INVALID_RESPONSE` の名称と、範囲縮小後の適用範囲の乖離。** 本Release後、同値が production から生成されるのは Base64 デコード失敗・デコード結果0バイトの2経路のみとなり、「応答が不正」という語は実態（応答構造は正しいがペイロードが破損）を正確には表さない | **後方互換上の Inherited Limitation として受容する。** 改名は外部参照を破壊するため行わない（7.2節・N-8）。名称の適正化は利用者可視の変更であり、**DEF-6.23-1（message 改訂）へ合流させて独立判断する** |
| **IL-1（v6.23 から継承）** | 要求拒否系4型（`BAD_REQUEST` / `RESOURCE_NOT_FOUND` / `CONFLICT` / `UNPROCESSABLE_ENTITY`）が同一 message を共有し、`RESOURCE_NOT_FOUND` の message が意味的に不正確 | **本Releaseでは解消しない。そのまま残存する**（7.6節・DEF-6.23-1）。本Releaseの message／reason 整合の主張は `UNKNOWN` 系／`INVALID_RESPONSE` 系の2組に限定される（**A-6**） |

---

## 17. Deferred Items

### 17.1 本Releaseで完了する項目

| ID | 内容 | 完了根拠 |
|---|---|---|
| **DEF-6.23-3** | `UNKNOWN` の2経路分離（`APIError` catch-all と generic `except Exception`） | AC-8 |
| **DEF-6.23-4** | `INVALID_RESPONSE` の細分化（構造不正 vs Base64 破損） | AC-11 |
| **DEF-6.23-12** | v6.23 NOIMPACT 陽性対照2件の実値化 | AC-33・AC-34・AC-35 |
| **DI-11** | OpenAI Image Generation Request Rejection Reason Refinement | **前半（v6.23）＋後半（v6.24）で完結** |

### 17.2 本Releaseで部分的に解消する項目

| ID | 内容 | 扱い |
|---|---|---|
| **DEF-6.23-10** | positive allow-list 方式 guard を `_validate_response_structure()` 等の他の入力受け取り関数へ展開するか | **validator 部分のみ解消**（**A-2**）。`_validate_response_structure()` については I-VAL-1（7.8節）として本Releaseで確立する。**他関数への一般化は継続**（`_build_generated_image()`・`generate()` 等は正当な処理形が異なるため、関数ごとに許可形の定義を要する） |

### 17.3 継続する項目

| ID | 内容 | 引継ぎ先 |
|---|---|---|
| **M5-1（DEF-6.23-5）** | match-case class pattern を構築形 guard の allow-list へ含めるか | **継続**。本Releaseは構築形 guard を新設せず判断機会が発生しない（11.6節・12.4節） |
| **DEF-6.23-1** | `RESOURCE_NOT_FOUND` 等の message 改訂（IL-1 の是正）。**IL-6.24-1（`INVALID_RESPONSE` の名称）も本項目へ合流** | 将来Release |
| **DEF-6.23-2** | 新 reason の一部を `CONTINUE_WITHOUT_FEATURED_MEDIA` へ拡大するか。ORD-3 の領域 | 将来Release（ORD-1／ORD-3 の正式再評価が必要） |
| **DEF-6.23-6** | Content Policy 拒否の判別（`CONTENT_POLICY_REJECTED` の新設） | 解析禁止 contract の見直しを伴う独立検討 |
| **DEF-6.23-7** | `status_code` を属性として公開すること | 必要性が生じた時点で独立判断 |
| **DEF-6.23-8** | reason を構造化ログ／metrics へ記録すること | DI-5 |
| **DEF-6.23-9** | zero-diff guard の共有レジストリ化。**本Releaseで guard が3→4件となり O(N) 保守コストがさらに顕在化した** | 将来Release（テスト基盤の構造変更を伴う） |
| **DEF-6.23-11** | v6.19 の件数埋め込み Scenario ID を件数非依存 ID へ改名するか | 将来Release（13.2節で据え置きを継承） |
| **DEF-6.22-1** | WordPress 一過性失敗の CONTINUE 拡大 | 将来Release（ORD-3。DI-5 の運用データと人間の明示承認が前提） |
| **DI-5 / DI-6 / DI-7 / DI-9** | observability・retry／idempotency・orphan media cleanup・Gate 値の厳格検証 | 本Release対象外。ROADMAP の記録を維持（状態変更なし） |

### 17.4 v6.23 から継承した Deferred の処理結果一覧

| 継承項目 | 本Releaseでの扱い |
|---|---|
| **DEF-6.23-3 / -4** | **完了**（DI-11 後半の本体） |
| **DEF-6.23-12** | **完了**（11.4.2節） |
| **DEF-6.23-10** | **validator 部分のみ解消／一般化部分は継続**（A-2） |
| **M5-1（DEF-6.23-5）** | **継続**（判断機会が発生しない） |
| **DEF-6.23-1 / -2 / -6 / -7 / -8 / -9 / -11** | **継続**（状態変更なし） |
| **DEF-6.22-1** | 本Release対象外。DI-5 の運用データを待つ（状態変更なし） |
| **DI-6 / DI-7 / DI-9** | 本Release対象外。ROADMAP の記録を維持 |

---

## 18. 実装工程の作業順

> **以下はすべて未実施である。本設計書の承認前に着手してはならない。**

### 工程0：着手前確認

1. `docs/checklists/release_start_checklist.md` の1〜5章を実施する
2. Working Tree clean・HEAD が `38e2487` であることを確認する（不一致なら停止し人間へ報告）
3. **本設計書が人間により承認済みであることを確認する**
4. **【必須Gate。0.5節 実装前必須Gate】正式 Inventory 26ファイルを、権威的記録（前回 v6.23.0
   Formal Regression の実行記録）と実ファイル（`tests/` 配下の実際のファイル一覧）の**双方から
   突合・確定する**。**Production実装前Gate確認（Gate 2）で本手順を実施済みであり、13.1節に
   確定済み一覧（ファイル名・assertion数）を記載した（20章 U-2 解消。0.6節・19.3節）。**
   `git status --porcelain` で HEAD が `38e2487` から変わっていないことを条件に再突合は不要。
   **HEAD が変わっている場合は本手順を再度実施し、一致しない場合は停止し人間へ報告する。**

### 工程1：Production Implementation（1ファイル）

5. `openai_image_generator.py` L77 の直後へ Enum 2値を追加（I-1）。**既存13値の行に触れない**
6. L204・L208 の返却 reason を `INVALID_RESPONSE_STRUCTURE` へ差し替え（I-2・I-3）
7. L351 の代入 reason を `UNEXPECTED_EXCEPTION` へ差し替え（I-4）
8. Enum class docstring（L57-63）へ v6.24 の追加と適用範囲縮小を追記（I-5）
9. **`image_generation_fallback_policy.py` を開かない**（G-8 を構造的に保証）
10. **`_classify_api_error()`・`_build_generated_image()` の分岐・message 定数に触れない**

### 工程2：新規 E2E 作成

11. `tests/test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_refinement_foundation.py` を 12.1節の prefix 構成で作成
12. `BASELINE_COMMIT = "38e2487db5760034f4a994319350244960a42e1b"` を固定
13. `_protected_paths` 22件を v6.21〜v6.23 と同一のものから踏襲（GR-1）
14. **Production source allow-list と test change allow-list を別変数で定義**（A-7・11.5節）
15. Production source allow-list は `openai_image_generator.py` **1件のみ**、equality 検査
16. **陽性対照は最初から実値ベースで実装**（11.4.2節 D12-1〜D12-5 と同型）
17. `NOVALPARSE-` guard を 12.5.1節のアルゴリズムで実装（R導出手順を含む）。陽性対照12形・陰性対照5形（W-5を含む）を置く

### 工程3：既存 E2E 追随（5ファイル）

18. `v6_11_0`：L964（12ケース分）・L1103（1ケース）の期待 reason を差し替え。**L1002・L1013・L1101 は変更しない**
19. `v6_19_0`：期待表へ2エントリ追加／件数 13→15（3箇所）／split UNCLASSIFIED 2→4／**`UNCLS-` tuple へ新2値を追加**（案X・A-3）
20. `v6_21_0` L824〜：test change allow-list の更新のみ
21. `v6_22_0` L1013〜：同上
22. `v6_23_0` L1116〜：test change allow-list の更新 **＋ L1232-1242 の陽性対照2件を D12-1〜D12-5 へ置換
    ＋ 【0.5節 Suggestion-1・11.4.1節（旧 U-6）】`_allowed_source_changes` の更新要否確定。
    Production実装前Gate確認（Gate 4）で `git diff --name-only 8fd8453 -- src/openai_image_generation`
    を実測し、リテラル変更不要と確定済みである（11.4.1節）。実装完了後は新規 E2E 自身の
    equality 検査と本 guard の containment 検査が、実際の変更後差分に対して機械的に再確認する**

### 工程4：限定テスト

23. `.\venv\Scripts\python.exe` で新規 E2E を単体実行し、全 PASS・見込み 346 との乖離の有無を確認する。
    **実施済み（0.7節・19.4節）：346/346 PASS・FAIL 0・SKIP 0・終了コード0・乖離0を確認済み**
24. 更新した既存5ファイルを個別に実行し、13.2節の宣言どおりの件数であることを確認する。
    **実施済み（0.7節・19.4節）：v6.11=248（±0）・v6.19=272（+10）・v6.21=147（±0）・
    v6.22=324（±0）・v6.23=341（**+9**。設計時の宣言+3から実測により訂正。13.2節）。
    いずれもFAIL 0・SKIP 0・終了コード0**

### 工程5：Formal Regression

25. 工程0 手順4 の必須Gate（正式 Inventory 26ファイルの確定）が完了済みであることを確認する。
    Production実装前Gate確認（Gate 2・0.6節）で確定済みであるため、HEAD 不変を条件に
    再突合は不要（13.1節）。**実施済み（第4回改訂・0.8節・19.5節）：HEAD `38e2487` 不変を確認し、
    再突合を省略した**
26. 正式 Inventory 27ファイルを個別に全件実行する。**実施済み：`.\venv\Scripts\python.exe`
    により正式Inventory順（1〜27）で1ファイルずつ個別実行した。一括glob実行・pytestへの
    置換はいずれも行っていない**
27. 13.3節 F-1／F-2／F-3 の3判定をすべて満たすことを確認する。**実施済み：F-1（既存4053シナリオの
    削除・弱体化0件）・F-2（v6.19 +10・v6.23 +9、他ファイル件数不変）・F-3（新総数4418を実測し
    見込みと完全一致）のいずれも充足を確認した**
28. FAIL 0・SKIP 0・全ファイル終了コード0・外部 API 実接続0件・Git 状態不変を確認する。
    **実施済み：27ファイルすべてでFAIL 0・SKIP 0・終了コード0を確認。v6.23／v6.24 の
    `SOCKET-*` guard により実通信0件を確認。実行前後で Git 状態（HEAD・ahead/behind・
    staged・modified／untracked の構成）が不変であることを確認した**

### 工程6：以降（本Releaseの後続工程。別途指示を待つ）

29. Code Review → Test Review → Documentation Integration（10.3節）→ Release Review → 人間の最終承認 → commit／push。
    **Documentation Integration（10.3節の対象：`docs/ROADMAP.md`／`docs/CHANGELOG.md`／
    `docs/architecture.md`）は第4回改訂（0.8節）で実施済みである。** Code Review・Test Review・
    Release Review・人間の最終承認・commit／push は、本設計書の第4回改訂時点でもいずれも
    **未実施**であり、これらへは自動で進まない

---

## 19. Architecture Review 反映内容

### 19.1 Required Amendments（初回改訂、A-1〜A-8）

| # | Amendment（要求） | 反映内容 | 反映節 |
|---|---|---|---|
| **A-1** | `_validate_response_structure()` の AST guard は関数全体を制限せず、**外部応答値の読み取りのみ**を positive allow-list で厳密検査する。許可は `getattr(response, "data", _MISSING)` と `getattr(data[0], "b64_json", _MISSING)`。第2引数は `data`／`b64_json` のみ、3引数形式必須、その他属性・`text`・`content`・`headers`・`status_code`・`json()` 等を解析しない | I-VAL-1 として規範化。条件 (a) `ast.Attribute` 0件／(b) `getattr` ちょうど2件／(c) 3引数形式かつ keywords 空／(d) 第2引数が `{"data","b64_json"}` の Constant。**構造検査（`isinstance`／`len`／subscript／真偽評価）は検査対象外として明示的に制限しない**。陰性対照 W-3 が過剰拒否を検出。**（本改訂追記）条件(a)の「`ast.Attribute` 0件」は、当時は関数全体を対象とする表現のまま残っており、`_validate_response_structure()` が正当に行う内部 Enum メンバ参照まで誤って violation と判定する欠陥を含んでいた。Production実装前Gate確認（Gate 3・AST実測）でこれを発見し、外部応答値に由来する識別子集合 R へのスコープ限定へ訂正した（RA-Gate3-1、19.3節）** | **7.8節・12.5節（本改訂で7.8.2節・7.8.5節・12.5.1節・12.5.3節を再訂正、19.3節）** |
| **A-2** | DEF-6.23-10 は **validator 部分のみ解消**し、一般化部分は継続 | 17.2節に「validator 部分のみ解消／他関数への一般化は継続」を明記。5章 N-10 にも非スコープとして記載 | **17.2節・5章 N-10** |
| **A-3** | v6.19 `UNCLS-` 対象へ新2 reason を追加し、category／action／not-FAILED を検証する**案X を採用**。想定 +10 assertions | 13.2節 (1) に案X 採用を明記。内訳を L524 +2／L717 +2／L545 +6 ＝ **+10** として確定。採用理由（`UNCLS-NOT-FAILED` の回帰防止を新値へ及ぼす価値）も併記 | **13.2節** |
| **A-4** | Formal Regression は「4053件固定維持」とせず、**既存4053シナリオの削除・弱体化なし＋設計上追加した assertion を含む新総数を実測**する | 13.3節を新設し、判定を F-1（削除・弱体化0件）／F-2（宣言どおりの追加のみ）／F-3（新総数を実測）の3点に再定義。AC-36 も同様に改訂。見込み総数 4411 は「見込み」と明記 | **13.3節・AC-36** |
| **A-5** | 「SDK 外例外」ではなく「**`openai.APIError` として捕捉されなかった予期しない例外**」または「**generic `except Exception` 経路**」と表現する | 全編で「SDK 外例外」という表現を使用せず、上記2表現に統一。2.1節・3.2節・7.3節 C-2・7.5.1節・9.5節・AC-7 ほか | **全編** |
| **A-6** | message と reason の整合は、**本Release対象の `UNKNOWN` 系／`INVALID_RESPONSE` 系2組に限定**して主張する | 7.6節に主張範囲の限定表を置き、「上記2組以外について整合を主張してはならない」を明記。v6.23 の IL-1 が本Releaseで解消されずそのまま残存することを併記。16章にも IL-1 を継承項目として記録 | **7.6節・16章** |
| **A-7** | **Production source allow-list と test change allow-list を分離**する | 11.5節で `_allowed_source_changes`（1ファイル・equality 検査）と `_allowed_test_changes`（6ファイル・containment のみ）を別変数として定義。混在を禁止。AC-31 に分離要件を追加。18章 工程2 手順14 にも作業として明記 | **11.5節・AC-31** |
| **A-8** | Production docstring の変更は、**既存記述が不正確になる場合のみ**とする | 10.1節に docstring 変更方針の判定表を新設。Enum class docstring のみ「変更する」（現行文が本Release後に不正確化するため）、`_classify_api_error()`／`_validate_response_structure()`／module docstring は「変更しない」（本Release後も正確なため）と個別判定 | **10.1節** |

### 19.2 Minor Amendments と実装前必須Gate（本改訂、Minor-1〜3・Suggestion-1・Gate）

Architecture Review Verdict：**Approved with Minor Amendments**（Minor 3件・Suggestion 1件）。
あわせて **実装前必須Gate 1件**（Finding ではなく実装着手の前提条件）を課した。

**Finding（Minor 3件・Suggestion 1件）**

| # | 種別 | 指摘（要求） | 反映内容 | 反映節 |
|---|---|---|---|---|
| **Minor-1** | Minor | 「全22章」という表現が、第0章を含む実際の構成（全23セクション、第0章〜第22章）と不整合だった | 0章冒頭に「本設計書は全23セクション（第0章〜第22章）で構成される」を追加し、表現を実態に合わせて是正 | **0章冒頭** |
| **Minor-2** | Minor | Release 番号 6.24.0 の扱いが「提案」のまま未確定事項（旧 U-4）に留まっていた | 0.3節を「確定」へ改訂。人間レビューによる承認を明記し、既存13値を維持した末尾追加でありmajor更新が不要である旨の判断根拠を記載。20章から U-4 を除去し、0.3節へ移設した旨を20章冒頭の注記に記録 | **0.3節・20章冒頭注記** |
| **Minor-3** | Minor | v6.23 設計時の予告（`_validate_response_structure()` の戻り値契約変更）と実測結果の差異が、未確定事項（旧 U-3）としてのみ記録されていた | 「過去文書との差異・補正記録」として6.4節を新設し、確定した扱い（signature／3要素返却形は不変、返却可能 reason 集合の拡張と経路別 reason 精緻化として扱う）を記録。20章から U-3 を除去し、6.4節へ移設した旨を20章冒頭の注記に記録 | **6.4節・20章冒頭注記** |
| **Suggestion-1** | Suggestion | `test_e2e_v6_23_0_*.py` の `_allowed_source_changes` について、本Releaseの変更が既存 allow-list に含まれるためリテラル変更は不要と判断した（旧 U-6）が、推測に基づく先取り判定のまま未確定事項に留まっていた | 11.4.1節へ必須手順（`git diff --name-only 8fd8453 -- src/openai_image_generation` の実測、推測による更新禁止）として移設し、18章 工程3 手順22 にも明記。20章から U-6 を除去し、11.4.1節・18章へ移設した旨を20章冒頭の注記に記録 | **11.4.1節・18章 工程3手順22** |

**実装前必須Gate（Finding ではない。1件）**

| ID | 内容 | 反映内容 | 反映節 |
|---|---|---|---|
| **Gate（旧 U-2）** | 正式 Inventory 27ファイルの権威的な全数ファイル名リストが未確定のまま Formal Regression 工程へ進みうる状態だった。**Minor でも Suggestion でもなく、レビューが実装着手の前提条件として独立に課した Gate である** | U-2 へ必須Gate（Production実装前、遅くとも新規E2E作成前までに権威的記録と実ファイルの双方から確定。未確定のままFormal Regressionへ進まない）を追記し、18章 工程0 手順4・工程5 手順25 として手順化。20章では U-2 を「必須Gate付きの未確定事項」として引き続き保持する（Finding として解消されたものではなく、実測完了までは未確定のままとする） | **13.1節・20章 U-2・18章 工程0手順4・工程5手順25** |

Finding 4件・実装前必須Gate 1件はいずれも前回改訂で反映済みである。
**確定済みの reason taxonomy（7章）・Acceptance Criteria（14章）・
Runtime Action Zero Diff（Z-1〜Z-8、9章）・Deferred 方針（17章）はいずれも変更していない。**

### 19.3 Production実装前Gate の確認結果（前回改訂、Gate 1〜5・Required Amendment）

Gate 1・2・4・5 は **PASS**。Gate 3 は AST 実測により Required Amendment を検出し、
前回改訂での反映により **PASS** となった。**Gate総合判定：Production実装へ進行可能。**

**Gate別結果**

| Gate | 対象 | 結果 | 根拠 |
|---|---|---|---|
| **Gate 1** | Git状態（branch／HEAD／origin/main／ahead-behind／untracked） | **PASS** | HEAD/origin/main = `38e2487`、ahead/behind 0/0、既存追跡ファイル差分なし、untracked は対象設計書1件のみ |
| **Gate 2** | Formal Regression 正式Inventory（旧U-2） | **PASS** | `docs/CHANGELOG.md` 等の権威的記録と `tests/` 配下の実ファイルを突合。26ファイル・4053 assertionsを確定（合計値が個別26件の総和と完全一致）。v6.24追加後27ファイルとなることを確認。13.1節へ確定済み一覧を記載 |
| **Gate 3** | I-VAL-1 現行適合性（`_validate_response_structure()`、旧U-1） | **設計書修正後PASS** | AST実測（`.\venv\Scripts\python.exe`）により、関数内 `ast.Attribute` 2件（L204・L208、いずれも `OpenAIImageGenerationErrorReason` メンバ参照）を検出。条件(a)の**旧文言（関数全体でAttribute 0件）では恒久的にFAIL**。R = {`response`,`data`,`b64_json`} へスコープ限定すると **R由来Attribute 0件でPASS**。7.8.2節・7.8.3節・7.8.5節・12.5.1節・12.5.2節・12.5.3節・AC-28 を訂正 |
| **Gate 4** | v6.23／v6.21／v6.22 guard allow-list 更新要否（旧U-6） | **PASS** | `git diff --name-only <baseline> -- src/openai_image_generation` 実測により、3 guard とも source allow-list 更新不要・test allow-list へ `test_e2e_v6_24_0_*.py` 追加が必要と確定（推測ではなく実測。11.4.1節） |
| **Gate 5** | Production／E2E 変更対象の最終確認 | **PASS** | Production変更候補が `openai_image_generator.py` 1件のみであることを確認。行番号2件の軽微なずれ（`_classify_api_error()` の実際位置 L107-192、docstring L108-131）を検出し本改訂で訂正（10.1節） |

**Required Amendment（1件・Gate 3由来）**

| # | 指摘 | 反映内容 | 反映節 |
|---|---|---|---|
| **RA-Gate3-1** | I-VAL-1 条件(a)「当該関数本体に `ast.Attribute` ノードが0件であること」という旧文言は、`_validate_response_structure()` が正当に行う内部 Enum メンバ参照（`OpenAIImageGenerationErrorReason.INVALID_RESPONSE` / `INVALID_RESPONSE_STRUCTURE`）まで violation と誤判定する。現行実装（改修前）ですら旧文言では不適合となり、改修後（I-2・I-3 で `INVALID_RESPONSE_STRUCTURE` 参照を追加）も恒久的に不適合のままとなる欠陥 | 条件(a)を「外部応答値に由来する識別子集合 R を根とする `ast.Attribute` が0件」へ再定義。R は第1 positional 引数を初期値とし、`getattr` 戻り値の代入先を再帰的に加える不動点集合として導出する（本Releaseの実測値：R = {`response`, `data`, `b64_json`}）。R に属さない識別子への属性アクセス（内部 Enum・定数等）は条件(a)の対象外と明記。12.5.1節の検査アルゴリズムへ R 導出手順（新手順3）を追加し、Attribute 検査（旧手順3→新手順4）を R スコープへ限定。12.5.3節へ許容対照 W-5（`OpenAIImageGenerationErrorReason.INVALID_RESPONSE_STRUCTURE` が violation にならないことの実証）を追加。AC-28 を R スコープ版へ改訂。7.8.5節を「静的読解」から「AST実測」（現行実装が実際には R-scope版でのみ適合すること）へ更新 | **7.8.2節・7.8.3節・7.8.5節・12.5.1節・12.5.2節・12.5.3節・AC-28** |

**副次的な整合修正（Gate 3・W-5追加に伴う assertion 見込み値の更新）**：陰性対照が4形→5形
となったことに伴い、新規E2Eの assertion 見込みを **345 → 346**、Formal Regression 新総数の
見込みを **4411 → 4412** へ更新した（12.6.2節・13.3節・15章 R-10・18章 手順23・20章 U-5・
21章 RB-15）。これらはいずれも「見込み値」であり、実質要件（AC・Z-1〜Z-8・Deferred）の変更ではない。

前回改訂で解消した未確定事項：**U-1（解消）・U-2（解消）**。旧U-6は前々回改訂で手順化済みであり、
前回改訂の Gate 4 実測によりその内容（source allow-list 更新不要）が確定した。
**U-5 のみ未確定事項として継続した**（20章）。

Gate 1〜5・Required Amendment RA-Gate3-1 はいずれも前回改訂で反映済みである。
**確定済みの reason taxonomy（7章）・分類経路（7.3節）・Acceptance Criteria の実質要件（14章）・
Runtime Action Zero Diff（Z-1〜Z-8、9章）・Deferred 方針（17章）はいずれも変更していない。**

### 19.4 E2E限定テスト実測結果（第3回改訂、6ファイル・1678/1678 PASS）

Production Implementation（1ファイル）・E2E限定テスト（既存5ファイル更新・新規1ファイル作成）は
第3回改訂より前の別工程で実施済みであり、第3回改訂はその実測結果を反映するのみであった。

**実測結果一覧**

| # | ファイル | 実測 assertion | PASS | FAIL | SKIP | 終了コード | 変更前 | 増減 | 設計時宣言 | 判定 |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `test_e2e_v6_11_0_*.py` | 248 | 248 | 0 | 0 | 0 | 248 | ±0 | ±0（13.2節） | 一致 |
| 2 | `test_e2e_v6_19_0_*.py` | 272 | 272 | 0 | 0 | 0 | 262 | **+10** | +10（13.2節） | 一致 |
| 3 | `test_e2e_v6_21_0_*.py` | 147 | 147 | 0 | 0 | 0 | 147 | ±0 | ±0（13.2節） | 一致 |
| 4 | `test_e2e_v6_22_0_*.py` | 324 | 324 | 0 | 0 | 0 | 324 | ±0 | ±0（13.2節） | 一致 |
| 5 | `test_e2e_v6_23_0_*.py` | 341 | 341 | 0 | 0 | 0 | 332 | **+9** | +3（11.4.2節） | **乖離。第3回改訂で+9へ訂正** |
| 6 | `test_e2e_v6_24_0_*.py`（新規） | 346 | 346 | 0 | 0 | 0 | — | — | 見込み346（12.6.2節） | 一致（乖離0） |
| | **限定合計** | **1678** | **1678** | **0** | **0** | 全件0 | | | | |

すべて `.\venv\Scripts\python.exe` による個別実行。bare `python`・別 venv は使用していない。
**第3回改訂の時点では**、Formal Regression（27ファイル合算の正式実行）は**未実施**であった
（第4回改訂・0.8節・19.5節で実施・確定した）。

**v6.23 の乖離（設計時 +3 → 実測 +9）の反映内容**

| # | 指摘 | 反映内容 | 反映節 |
|---|---|---|---|
| **RA-0.7-1** | 13.2節・11.4.2節が DEF-6.23-12 解消分（+3）のみを計上し、`test_e2e_v6_23_0_*.py` が `test_e2e_v6_19_0_*.py` と同型の `_ALL_REASONS` 駆動ループを2箇所持つ事実（Enum 13→15 に伴う自動増 +6）が計上漏れであった。Production未実装時点で allow-list 更新のみを適用して実行すると `KeyError: 'UNEXPECTED_EXCEPTION'` でテストが成立しないことが実測で判明した | 13.2節(2)を全面改訂し、増分内訳を「D12-1〜D12-5（+3）／`API-VALUE[name]`ループ（+2）／`POLICY-CATEGORY`・`POLICY-ACTION`ループ（+4）＝合計+9」へ訂正。**期待値緩和ではなく、coverage対象が13値から15値へ拡張されたことによる構造的追随**であることを明記。13.3節 F-2／21章 RB-1／18章手順24を整合させて更新 | **13.2節・13.3節・21章 RB-1・18章 手順24** |

**総数の確定**

| 対象 | 数値 | 性質 |
|---|---|---|
| 既存26ファイル新合計 | **4072**（4053 + 10 + 9） | 個別ファイル実測の合算による確定値 |
| 新規v6.24ファイル | **346** | 限定テスト実測値（見込み346と乖離0） |
| Formal Regression 見込み総数（27ファイル） | **4418**（4072 + 346） | 個別実測からの算出値。第3回改訂時点では**27ファイルを対象とする正式な一括実行はまだ行っていなかった**（第4回改訂で実施・確定） |

**Scenario ID の確認結果**：`test_e2e_v6_19_0_*.py` の `REASON-SPLIT-4-1-2-2` /
`REASON-SPLIT-TOTAL-9` / `COMPAT-V611-REASON-COUNT-9`、および `test_e2e_v6_23_0_*.py` の
`API-COUNT-13` / `POLICY-COVERAGE-13` は、いずれも ID トークンに旧件数が埋め込まれた
**履歴識別子**であり、現在件数（15値）を表すラベルではない。テストファイル自体は
第3回改訂でも第4回改訂でも変更していない。ID を「現在件数を表すラベル」として15へ改名するか、
このまま履歴識別子として固定し続けるかは **DEF-6.23-11** に一元化して継続する
（13.2節）。

**確定済みの reason taxonomy（7章）・分類経路（7.3節）・Acceptance Criteria の実質要件（14章）・
Runtime Action Zero Diff（Z-1〜Z-8、9章）・Deferred 方針（17章）はいずれも変更していない。**

### 19.5 Formal Regression 実測結果（第4回改訂・本改訂、27ファイル・4418/4418 PASS）

Formal Regression（正式Inventory27ファイルの個別実行）は本工程より前の別工程で
実施済みであり、本改訂はその実測結果を設計書へ反映し、あわせて
`docs/ROADMAP.md`・`docs/CHANGELOG.md`・`docs/architecture.md` へ Documentation Integration
として反映するものである。

**27ファイル実測結果一覧（正式Inventory順）**

| # | ファイル | assertion | PASS | FAIL | SKIP | 終了コード |
|---|---|---|---|---|---|---|
| 1 | `test_e2e_v1_11_0_save_result.py` | 43 | 43 | 0 | 0 | 0 |
| 2 | `test_e2e_v5_9_0_retry_runtime_loop_wiring_foundation.py` | 64 | 64 | 0 | 0 | 0 |
| 3 | `test_e2e_v6_0_0_retry_runtime_lock_foundation.py` | 43 | 43 | 0 | 0 | 0 |
| 4 | `test_e2e_v6_1_0_retry_runtime_graceful_shutdown_foundation.py` | 44 | 44 | 0 | 0 | 0 |
| 5 | `test_e2e_v6_2_0_structured_loop_logging_foundation.py` | 64 | 64 | 0 | 0 | 0 |
| 6 | `test_e2e_v6_3_0_retry_metrics_foundation.py` | 174 | 174 | 0 | 0 | 0 |
| 7 | `test_e2e_v6_4_0_retry_monitoring_foundation.py` | 171 | 171 | 0 | 0 | 0 |
| 8 | `test_e2e_v6_5_0_retry_alert_foundation.py` | 131 | 131 | 0 | 0 | 0 |
| 9 | `test_e2e_v6_6_0_retry_notification_foundation.py` | 135 | 135 | 0 | 0 | 0 |
| 10 | `test_e2e_v6_7_0_retry_notification_message_foundation.py` | 117 | 117 | 0 | 0 | 0 |
| 11 | `test_e2e_v6_8_0_retry_notification_cli_report_wiring_foundation.py` | 197 | 197 | 0 | 0 | 0 |
| 12 | `test_e2e_v6_9_0_wordpress_media_upload_foundation.py` | 331 | 331 | 0 | 0 | 0 |
| 13 | `test_e2e_v6_10_0_ai_image_generation_contract_foundation.py` | 78 | 78 | 0 | 0 | 0 |
| 14 | `test_e2e_v6_11_0_openai_image_generation_adapter_foundation.py` | 248 | 248 | 0 | 0 | 0 |
| 15 | `test_e2e_v6_12_0_generated_image_wordpress_media_upload_wiring_foundation.py` | 91 | 91 | 0 | 0 | 0 |
| 16 | `test_e2e_v6_13_0_article_featured_media_binding_foundation.py` | 123 | 123 | 0 | 0 | 0 |
| 17 | `test_e2e_v6_14_0_article_featured_media_orchestration_foundation.py` | 217 | 217 | 0 | 0 | 0 |
| 18 | `test_e2e_v6_15_0_image_generation_configuration_gate.py` | 94 | 94 | 0 | 0 | 0 |
| 19 | `test_e2e_v6_16_0_generated_image_filename_policy_foundation.py` | 143 | 143 | 0 | 0 | 0 |
| 20 | `test_e2e_v6_17_0_article_image_prompt_construction_foundation.py` | 136 | 136 | 0 | 0 | 0 |
| 21 | `test_e2e_v6_18_0_article_featured_media_composition_root_foundation.py` | 146 | 146 | 0 | 0 | 0 |
| 22 | `test_e2e_v6_19_0_image_generation_fallback_policy_foundation.py` | 272 | 272 | 0 | 0 | 0 |
| 23 | `test_e2e_v6_20_0_article_featured_media_runtime_foundation.py` | 198 | 198 | 0 | 0 | 0 |
| 24 | `test_e2e_v6_21_0_article_featured_media_runtime_wiring.py` | 147 | 147 | 0 | 0 | 0 |
| 25 | `test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py` | 324 | 324 | 0 | 0 | 0 |
| 26 | `test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py` | 341 | 341 | 0 | 0 | 0 |
| 27 | `test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_refinement_foundation.py`（新規） | 346 | 346 | 0 | 0 | 0 |

すべて `.\venv\Scripts\python.exe` による正式Inventory順の**個別実行**（一括glob実行・
pytestへの置換はいずれも不使用）。

**集計**

| 区分 | 値 |
|---|---|
| 既存26ファイル合計 | **4072**（1〜26番の合計。算術検証済み） |
| 新規v6.24（27番目） | **346** |
| **27ファイル総合** | **4418** |
| FAIL一覧 | **0件（全27ファイル）** |
| SKIP一覧 | **0件（全27ファイル）**。出力中「SKIP」を含む行はラベル文言中の語（例："skipなし"）のみで実SKIPなし |
| 非0終了コード一覧 | **0件（全27ファイル exit code = 0）** |
| 外部API実接続 | **0件**。v6.23／v6.24（OpenAI関連2ファイル）で `SOCKET-GETADDRINFO-BLOCKED`／`SOCKET-CONNECT-BLOCKED`／`SOCKET-NO-REAL-CLIENT`を確認。v6.11はFakeクライアント完全注入方式でありネットワーク層に到達しない |

**限定テスト実測（19.4節・第3回改訂）との整合**：v6.11＝248／v6.19＝272／v6.21＝147／
v6.22＝324／v6.23＝341／v6.24＝346のいずれも、Formal Regression 実測値と**完全に一致**した
（限定合計1678とFormal Regression該当6ファイル合計も一致）。

**見込み（4418）との差異**：**なし（完全一致）。** 13.3節 F-1／F-2／F-3の3判定をいずれも満たす。

**Documentation Integration**：本改訂の実測結果を根拠に、`docs/ROADMAP.md`（v6.24.0エントリ
追加・DI-11完結化・Deferred状態の同期）・`docs/CHANGELOG.md`（`[v6.24.0]`セクション新設）・
`docs/architecture.md`（v6.24.0層の新設・v6.23.0層への参照注記追加）を同時に更新した。
Release Review・commit・push はいずれも実施していない。

**確定済みの reason taxonomy（7章）・分類経路（7.3節）・Acceptance Criteria の実質要件（14章）・
Runtime Action Zero Diff（Z-1〜Z-8、9章）・Deferred 方針（17章）はいずれも変更していない。**

### 19.6 Release Review Findings Amendment の反映（第5回改訂）

Release Review を実施し、**Verdict：Changes Required（Blocking 0／Major 2／Minor 3／
Suggestion 4）** を得た。人間判断により、Major 2件・Minor 3件を本改訂（第5回改訂）で
反映し、Suggestion 4件は記録のみとして本Releaseでは変更しない。**本改訂は指定4文書
（本設計書・`docs/ROADMAP.md`・`docs/CHANGELOG.md`・`docs/architecture.md`）のみを対象とし、
Production Code・E2E・assertion数・commit・push・Release Review再実施のいずれも
行っていない。Verdict は再レビュー前のため Changes Required のまま**である。

**Major Findings（2件）**

| # | 指摘 | 人間判断による採用案 | 反映内容 | 反映節 |
|---|---|---|---|---|
| **Major-1** | `main.py` Zero Diff（AC-24・Z-3）について、設計書9.4節・CHANGELOG・architecture.mdが「`NOIMPACT-` guard で機械的に検証する」旨を記載していたが、新規v6.24 E2Eの`_protected_paths`（22件）に`main.py`は含まれておらず、機械検証は実在しなかった | **採用案(b)**：`main.py`のE2E組み込み（protected paths追加・E2E再実行）は行わず、検証方法の記述を実態（読み取り専用Git差分実測）へ訂正する | 9.4節・AC-24（1697行付近）・10章ファイル変更計画表を、「`main.py`はbaseline `38e2487`からの**読み取り専用Git差分実測**により変更がないことを確認した。新規v6.24 E2EのNOIMPACT protected pathsによる機械検証対象には含まれない」へ統一。`image_generation_fallback_policy.py`は既存の`POLICYFILE-DIFF-EMPTY`／`POLICYFILE-AST-EQUAL`（機械検証）で担保されることを明記し、両者の検証方法の違いを区別した。`docs/ROADMAP.md`・`docs/CHANGELOG.md`・`docs/architecture.md`の同趣旨の記載も統一した。**Runtime Action Zero Diff（Z-1〜Z-8）の内容・成立範囲は変更していない**（Z-3自体は成立したまま） | **9.4節・AC-24・10.1節・ROADMAP／CHANGELOG該当箇所** |
| **Major-2** | `docs/ROADMAP.md`・`docs/CHANGELOG.md`・`docs/architecture.md`のv6.23.0記録3箇所が、「本Releaseは**旧Zero Diff表現**（観測可能な挙動全体の不変を示す、本Release以前に用いられていた表現）とは表現しない。」から「本Releaseが保証する不変範囲はRuntime Action Zero Diff（Z-1〜Z-8）に限定される。」へ、本設計書のいずれの工程にも宣言・承認されないまま書き換えられていた（設計書10.3節・0.2節・19.5節はいずれも「追加のみ」を計画していた） | 3箇所は**revertしない**。人間判断により、Release間の表現規則統一のための**人間承認済みDocumentation Amendment**として本改訂で正式に記録する | 本節（19.6節）および0.2節・10.3節へ、v6.23記録3箇所の遡及編集を正式な Documentation Amendment として記録した。**v6.23.0の技術的意味・契約・成立範囲はいずれも変更していない**（直後の「Production behavior全体が不変であるとは記載できない」の文はいずれも保持されたまま）。新仕様追加・Production変更・E2E変更ではない。`main.py`Zero Diff検証方法の統一に伴い、v6.24自身の新規エントリ（ROADMAP.md 954行台の`- [x]`エントリ）内にも同一の**旧Zero Diff表現**が独立に存在していたため、Major-1と同じ統一表現へ本改訂で更新した（こちらはv6.23記録の遡及編集ではなく、v6.24自身の新規記述の表現統一である）。以後、**旧Zero Diff表現（今後使用しない旧表現）の完全一致表現は指定4文書のいずれにも再導入しない** | **本節・0.2節・10.3節** |

**Minor Findings（3件）**

| # | 指摘 | 反映内容 | 反映節 |
|---|---|---|---|
| **Minor-1** | `docs/architecture.md`のv6.24 Deferred一覧で、`DEF-6.23-1／2／6／7／8／9／11`の7 IDに対し説明が8件あり（`NOPARSE guardの他関数展開`が重複計上）、CHANGELOG・本設計書17.3節の正しい7件対応と不一致だった | 余分な`NOPARSE guardの他関数展開`を7件の説明列から削除し、DEF-6.23-10の行（既存の「validator部分のみ本Releaseで解消。他関数への一般化は継続」）にのみ残るようにした。Deferredの完了／継続状態自体は変更していない | `docs/architecture.md`該当箇所 |
| **Minor-2** | `docs/CHANGELOG.md`のv6.24.0見出し日付が`2026-08-05`のままで、Release Review完了前・未コミットの現時点（本改訂時点）と乖離していた | 見出しを`## [v6.24.0] - 2026-08-07`（現時点の予定Release日）へ更新した。**commitが別日になる場合はFinalize工程で日付を再確認する**。v6.23.0以前の日付は変更していない | `docs/CHANGELOG.md`見出し |
| **Minor-3** | 12.6.2節`COMPAT-`ブロックの内訳説明「既存10経路の reason／message ×2＝20＋`__all__`＋REQUEST_REJECTED存続3」が、実装済みE2E（`test_e2e_v6_24_0_*.py`）の実際の構成と一致していなかった | 内訳説明を実装へ一致させ、「既存10経路の reason／message ×2＝20＋`UNKNOWN`存続（存在確認1・value確認1）＋`INVALID_RESPONSE`存続（存在確認1・value確認1）＝4」（合計24）へ訂正。`__all__`は`API-ALL-UNCHANGED`／`COMPATAPI-OPENAI-ALL`で、`REQUEST_REJECTED`の存続は`API-VALUE[REQUEST_REJECTED]`／`API-NAMES-EXACT`で別途担保されることを明記した。assertion総数346・限定テスト1678/1678・Formal Regression 4418/4418はいずれも変更していない | 12.6.2節 |

**Suggestion（4件・記録のみ。本Releaseでは変更しない）**

| # | 内容 |
|---|---|
| **s-1** | `OpenAIImageGenerator.__init__`／`from_env()`／`generate()`／`output_mime_type`のsignature検証（AC-25）を、`inspect.signature`ベースへ将来拡張する余地がある |
| **s-2** | `NOVALPARSE-SCOPE-FUNCTION-ONLY`の陽性対照は、violationsの内容（getattr件数0による条件b違反）まで検査するとラベルの意図がより明確になる |
| **s-3** | v6.23 E2Eの`NOIMPACT-POSITIVE-EMPTY-ALLOWLIST`（D12-3相当）は`NOIMPACT-POSITIVE-PRECOND-CHANGED-NONEMPTY`（D12-1）と論理的に同値であり、整理の余地がある |
| **s-4** | `openai_image_generator.py` L213・L217（115文字）の折り返しを検討する余地がある |

**第5回改訂の不変条件**：Production実装・E2E実装・assertion数・reason taxonomy（既存13値＋新2値）・
fallback category／action・CONTINUE対象4値・Runtime Action Zero Diff（Z-1〜Z-8）・DI-11完結・
IL-6.24-1・DEF-6.23-10（validator部分のみ解消・一般化継続）・Formal Regression 4418/4418・
限定テスト1678/1678 はいずれも変更していない。第5回改訂の時点では、**Release Review再確認・
再々確認・Code Review・人間の最終承認はいずれも未実施**であり、Verdictは再レビュー前の
ため Changes Required のままだった（後続の再確認・再々確認・Code Reviewの結果は19.7節・
19.8節に記録する）。

### 19.7 Release Review再確認・Minor-N1の反映（第6回改訂）

Release Review再確認（読み取り専用）を実施し、第5回改訂で反映したMajor 2件・Minor 3件の
解消をすべて確認した。**必須Findingは新規1件（Minor-N1）のみ**であり、Blocking・Majorの
新規検出は0件だった。

**Minor-N1（新規・2箇所）**

| # | 指摘 | 反映内容 | 反映節 |
|---|---|---|---|
| **Minor-N1** | 設計書12.1節の prefix→AC 対応表が、第5回改訂のMajor-1・Minor-3による訂正へ未追随だった。①`NOIMPACT-`行が`AC-24, AC-31`のままで、訂正後のAC-24（main.pyは`NOIMPACT-`の機械検証対象外）と矛盾。②`COMPAT-`行の目的欄に`REQUEST_REJECTED 存続`が残り対応ACに`AC-13`が付与されたままで、訂正後の12.6.2節（`REQUEST_REJECTED`の存続は`API-VALUE[REQUEST_REJECTED]`／`API-NAMES-EXACT`で別途担保）と矛盾 | `NOIMPACT-`行の対応ACを`AC-24, AC-31`→`AC-31`のみへ、`COMPAT-`行の目的欄から`REQUEST_REJECTED 存続`を削除し対応ACを`AC-12, AC-13`→`AC-12`のみへ、それぞれ訂正した | 12.1節 |

あわせて、19.6節（Major-2の指摘欄・反映内容欄）に残存していた**今後使用しない禁止表現**
（観測可能な挙動全体の不変を示す旧表現）の完全一致3件（引用・監査記録・禁止規定としての言及）を、
意味・監査追跡性を保持したまま「旧Zero Diff表現」等の代替表現へ置換した
（v6.23記録3件の人間承認済みDocumentation Amendment化、v6.24 ROADMAP自身の表現統一履歴、
再導入禁止ルールの3点はいずれも維持）。

**本改訂は本設計書1ファイルのみを対象とし、Production・E2E・他docs 3文書・assertion数の
いずれも変更していない。** 確定済みの reason taxonomy・分類経路・Acceptance Criteria の
実質要件・Runtime Action Zero Diff（Z-1〜Z-8）・Deferred 方針はいずれも変更していない。
**第6回改訂の時点でも、Release Review再々確認・Code Review・人間の最終承認は未実施のまま
だった。**

### 19.8 Release Review再々確認・Code Review・人間の最終承認の反映（第7回改訂・本改訂）

Minor-N1反映後、**Release Review再々確認**（読み取り専用）を実施し、**Verdict：
Approved with Suggestions（Blocking 0／Major 0／Minor 0／Suggestion 6：s-1〜s-4継続＋
s-5・s-6を観察事項として新規記録）**を得た。s-5は設計書内の相対表現「本改訂」の一部が
第5回改訂以降の追加改訂により字義的に整合しなくなっている点、s-6はCHANGELOG・
architecture.mdの「Release Review未実施」という記載が当時の設計書の記載（実施済み）と
一致していなかった点を指摘するもので、いずれも過小申告方向であり誤った完了主張ではないため
非ブロッキングとされた。

続けて**Code Review**（読み取り専用）を実施し、**Verdict：Approved with Suggestions
（Blocking 0／Major 0／Minor 0／Suggestion 7）**を得た。既存Suggestion 6件に加え、
新規に **s-7** を検出した。

**s-7（新規）**

| # | 内容 | 影響 | 必須修正要否 |
|---|---|---|---|
| **s-7** | `tests/test_e2e_v6_24_0_*.py`の`_NEGATIVE_CASES`（I-VAL-1陰性対照）における`W-1`（許可形1）と`W-2`（許可形2）が、同一の`_VALID_BODY`を入力として検査しており、2つのassertionが同じ走査結果を検証している。設計書12.5.3節はW-1／W-2を独立した2形と規定するが、実質的には1回の走査で両形の非違反を実証する形になっている | **検出力の低下なし**（`_VALID_BODY`は許可形2つを両方含むため、単一走査で両形の非違反が実証されており、実質的には設計より強い結合検証）。「陰性対照5形」の宣言に対し実質4形の走査であり、assertion 1件が重複するのみ | **不要**。是正にはFormal Regression 27ファイル4418 assertionの再実行を要し、検出力向上を伴わないため本Releaseでは修正しない。将来テストスイートの再実行を伴うReleaseで、s-3（D12-3の冗長性）と併せて整理する候補とする |

**人間による設計・実装・E2E・文書の最終承認：完了。**

**Suggestion（Code Review時点7件・現在残存6件）**

Code ReviewではSuggestion 7件を記録した。**Finalizeでs-6を解消したため、現在残存する
非ブロッキングSuggestionは6件（s-1〜s-5、s-7）である。Code Review時点のVerdictおよび
件数は履歴として維持する。**

| # | 内容 | 分類 | 状態 |
|---|---|---|---|
| **s-1** | `OpenAIImageGenerator.__init__`／`from_env()`／`generate()`／`output_mime_type`のsignature検証（AC-25）を、`inspect.signature`ベースへ将来拡張する余地がある | Code Review（既知） | 残存 |
| **s-2** | `NOVALPARSE-SCOPE-FUNCTION-ONLY`の陽性対照は、violationsの内容（getattr件数0による条件b違反）まで検査するとラベルの意図がより明確になる | Code Review（既知） | 残存 |
| **s-3** | v6.23 E2Eの`NOIMPACT-POSITIVE-EMPTY-ALLOWLIST`（D12-3相当）は`NOIMPACT-POSITIVE-PRECOND-CHANGED-NONEMPTY`（D12-1）と論理的に同値であり、整理の余地がある | Code Review（既知） | 残存 |
| **s-4** | `openai_image_generator.py` L213・L217（115文字）の折り返しを検討する余地がある | Code Review（既知） | 残存 |
| **s-5** | 設計書の相対表現「本改訂」の一部（0.8節見出し・19.5節見出し・20章冒頭等）が、後続改訂の追加により字義的に不整合。回次番号併記により意味は一意に読み取れる | Release Review再々確認（観察事項） | 残存 |
| **s-6** | Finalize前のCHANGELOG・architecture.mdの「Release Review未実施」記載が、当時の設計書の記載（実施済み）と不一致だった（過小申告方向） | Release Review再々確認（観察事項） | **解消済み**（本改訂・Finalizeで3文書とも最終状態へ同期） |
| **s-7** | I-VAL-1陰性対照W-1／W-2の重複（上表参照） | Code Review（新規） | 残存 |

**本改訂（第7回改訂・Finalize）は指定4文書（本設計書・`docs/ROADMAP.md`・`docs/CHANGELOG.md`・
`docs/architecture.md`）のレビュー・承認状態の同期のみを行う。** Production Code・E2E・
assertion数・reason taxonomy・fallback category／action・CONTINUE対象4値・Runtime Action
Zero Diff（Z-1〜Z-8）・DI-11完結・IL-6.24-1・DEF-6.23-10の扱い・Deferred状態・
限定テスト1678/1678・Formal Regression 4418/4418 はいずれも変更していない。
**git add・commit・pushはいずれも本改訂でも実施していない。**

---

## 20. 未確定事項（要確認）

本節はかつて推測で仕様を確定していない事項を記録していた。**第4回改訂（本改訂）の時点で、
未確定事項として登録されていた U-1〜U-6 のすべてが解消済みである。** 経緯は以下のとおり。

> **Minor Amendment 反映に伴う整理（第1回改訂・0.5節／19.2節）**：U-3・U-4・U-6 は、
> Architecture Review Verdict「Approved with Minor Amendments」により、それぞれ次のとおり
> 解消・移設した。**ID の欠番は削除ではなく移動である**（追跡性を保つため ID は振り直さない）。
>
> - **U-4** → **0.3節**「Release 番号の扱い（確定）」へ移設し、確定事項として整理（Minor-2）
> - **U-3** → **6.4節**「過去文書との差異・補正記録」へ移設し、確定事項として整理（Minor-3）
> - **U-6** → **11.4.1節**の必須手順、および **18章 工程3 手順22** へ移設し、手順として明記（Suggestion-1）

> **Production実装前Gate確認に伴う整理（第2回改訂・0.6節／19.3節）**：U-1・U-2 は、
> Production実装前Gate確認（Gate 3・Gate 2）により解消した。
>
> - **U-1** → **7.8.5節**「現行実装・改修後実装への適合性（AST実測）」で AST 実測により解消。
>   解消の過程で I-VAL-1 条件(a)の旧文言の不備を発見し、7.8.2節で修正した（Gate 3・Required
>   Amendment RA-Gate3-1）
> - **U-2** → **13.1節**「正式 Inventory」へ26ファイルの確定済み一覧（ファイル名・assertion数）を
>   記載し解消（Gate 2）。旧 U-2 が「実装前必須Gate（Finding ではない）」として課していた
>   確定義務そのものが、第2回改訂の Gate 2 実施により満たされた

> **Formal Regression 実測反映に伴う解消（第4回改訂・0.8節・19.5節）**：U-5 は、
> 第3回改訂（0.7節・19.4節）で「新規 E2E の346・v6.19の+10・v6.23の+9」を E2E限定テスト実測
> により確定し**一部解消**していたが、「Formal Regression（27ファイル）の 4418/4418 PASS」の
> 部分のみ未確定のまま残っていた。**本改訂で正式Inventory27ファイルの個別実行（Formal
> Regression）を実施し、既存26ファイル 4072/4072 PASS ＋ 新規v6.24 346/346 PASS ＝
> 総合 4418/4418 PASS を実測。限定テスト時点の算出値と完全に一致し（乖離0）、U-5 は
> 完全に解消した。**

**未確定事項一覧：該当なし（U-1〜U-6 のすべてが解消済み。19.2節・19.3節・19.4節・19.5節を参照）。**

---

## 21. Rollback 条件

実装工程・Regression 工程で以下のいずれかが観測された場合、**Release を中止し
人間の指示を仰ぐ**。ツールが自動で復旧操作を行ってはならない
（`reset` / `checkout` / `restore` / `clean` / `stash` はいずれも人間の明示指示による）。

| ID | 中止条件 |
|---|---|
| **RB-1** | 13.2節が宣言した既知差分（v6.19 の +10、v6.23 の **+9**。実測により+3から訂正済み。0.7節）以外の assertion 件数変動が観測された（F-2 違反） |
| **RB-2** | 既存4053シナリオのいずれかが削除された、または期待値・検査ロジックが弱体化した（F-1 違反） |
| **RB-3** | Formal Regression に FAIL が1件でも残る（既知差分として説明できないもの） |
| **RB-4** | 15値のいずれかで **action が v6.23.0 時点と異なる**（Z-1 違反） |
| **RB-5** | 15値のいずれかで **category が 7.5.1節の表と異なる**（Z-2 違反） |
| **RB-6** | 既存13値の name・value・定義順のいずれかが変わった（AC-1 違反） |
| **RB-7** | `_CONTINUABLE_REASONS` の内容が変わった／CONTINUE となる reason が4値でなくなった（Z-8・G-5 違反） |
| **RB-8** | `image_generation_fallback_policy.py` または同 package の `__init__.py` に差分が生じた（G-8・AC-21 違反） |
| **RB-9** | `main.py` に差分が生じた（Z-3 違反） |
| **RB-10** | いずれかの message が1文字でも変わった（Z-4 違反） |
| **RB-11** | `__cause__` / `__context__` の到達可能性が変わった（Z-5 違反） |
| **RB-12** | `_validate_response_structure()` の signature または3要素返却形が変わった（Z-6・AC-26 違反） |
| **RB-13** | `_classify_api_error()` が baseline と AST 等価でなくなった（C-1・AC-27 違反） |
| **RB-14** | `UNKNOWN` または `INVALID_RESPONSE` が削除された／value が変わった（AC-13 相当・G-3 違反） |
| **RB-15** | 新規 E2E の assertion 実測値が見込み **346** と乖離し、12.6.2節の内訳で説明できない |
| **RB-16** | `NOVALPARSE-` の違反が1件でも検出された（I-VAL-1 違反） |
| **RB-17** | 陽性対照12形のいずれかが検出されない、または陰性対照5形（W-5を含む）のいずれかが違反として誤検出された（guard の検出力・非過剰性の破れ） |
| **RB-18** | 実装またはテストに禁止属性の列挙（deny-list 相当）が導入された（positive allow-list 方式からの後退） |
| **RB-19** | guard の `BASELINE_COMMIT` または `_protected_paths` が変更された（GR-1・GR-2 違反） |
| **RB-20** | allow-list に 10章が宣言していないファイルが登録された（GR-4・AC-37 違反） |
| **RB-21** | Production source allow-list と test change allow-list が同一変数へ混在させられた（A-7・AC-31 違反） |
| **RB-22** | DEF-6.23-12 の修正により `NOIMPACT-SCOPE` / `-COVERAGE` / `-EXACT` の検査ロジック・期待値・件数のいずれかが変わった（D-b・AC-34 違反） |
| **RB-23** | DEF-6.23-12 の陽性対照が `_allowed_source_changes` を破壊的に変更した（D-a・AC-35 違反） |
| **RB-24** | テストが実ネットワーク・実 API へ到達した（hermetic 違反） |

**部分 rollback の可否**：`UNKNOWN` の分離（I-4）と `INVALID_RESPONSE` の分離（I-2・I-3）は
**それぞれ独立に rollback 可能**である。両者は異なる経路・異なる Enum 値を対象としており、
片方だけを取り消しても Z-1〜Z-8 はいずれも成立し続ける（新値が未使用のまま Enum に残るのみ）。

ただし **Enum への値追加（I-1）のみを残して I-2〜I-4 をすべて取り消すこと**は、
「使われない Enum 値を Public API へ追加する」結果になるため**推奨しない**。
その場合は Release 全体を中止すること。

---

## 22. Status チェックリスト

- [x] ドラフト作成（本設計書）
- [x] Architecture Review Required Amendments（8件）の反映（19.1節）
- [x] Architecture Review Minor Amendments（Minor 3件・Suggestion 1件）および実装前必須Gate（1件）の反映（0.5節・19.2節）
- [x] Production実装前Gate の確認（Gate 1／2／4／5：PASS）および Required Amendment（Gate 3・RA-Gate3-1）の反映（0.6節・19.3節）
- [x] **人間による本設計書の承認**（第7回改訂・19.8節）
- [ ] Test Review
- [x] Production Implementation（1ファイル。設計書外の別工程で実施済み。0.7節）
- [x] 限定テスト（既存5ファイル＋新規1ファイル、**1678/1678 PASS**。設計書外の別工程で実施し、第3回改訂で実測値を反映。0.7節・19.4節）
- [x] Formal Regression（正式Inventory**27ファイル、4418/4418 PASS**。既存26ファイル4072/4072 PASS＋新規v6.24.0 346/346 PASS。FAIL 0・SKIP 0・全ファイル終了コード0・外部API実接続0件。設計書外の別工程で実施し、第4回改訂で実測値を反映。0.8節・19.5節）
- [x] Code Review（**Verdict：Approved with Suggestions**。Blocking 0／Major 0／Minor 0／Suggestion 7（うちs-7が新規検出）。第7回改訂・19.8節。Finalizeでs-6を解消したため、現在残存する非ブロッキングSuggestionは6件（s-1〜s-5、s-7）である。Code Review時点のVerdictおよび件数は履歴として維持する）
- [x] Documentation Integration（`ROADMAP.md` / `CHANGELOG.md` / `architecture.md`。第4回改訂で実施、第5回改訂でRelease Review Findings Amendmentとして追加更新、第7回改訂でFinalizeとして最終同期）
- [x] Release Review（初回**Verdict：Changes Required**。Blocking 0／Major 2／Minor 3／Suggestion 4。人間判断で確定したMajor 2件・Minor 3件を第5回改訂で反映済み。19.6節）
- [x] Release Review 再確認・再々確認（再確認でMinor-N1・2箇所を検出→第6回改訂で反映（19.7節）→再々確認で**最終Verdict：Approved with Suggestions**（Blocking 0／Major 0／Minor 0／Suggestion 6）確定。19.7節・19.8節）
- [x] 人間の最終承認（設計・実装・E2E・文書。第7回改訂・19.8節）
- [ ] commit／push

**本設計工程のうち第4回改訂では、Formal Regression の実測結果を設計書へ反映し、
`docs/ROADMAP.md`・`docs/CHANGELOG.md`・`docs/architecture.md` の Documentation
Integration を実施した。第5回改訂では、Release Review のVerdict（Changes
Required：Major 2件・Minor 3件・Suggestion 4件）のうち、人間判断で確定したMajor 2件・
Minor 3件を本設計書および上記3文書へ反映した（Suggestion 4件は記録のみ。19.6節）。
第6回改訂では、Release Review再確認で検出したMinor-N1（12.1節の対応ずれ2箇所）と、
19.6節に残存していた禁止表現3件を本設計書1ファイルへ反映した（19.7節）。
第7回改訂（本改訂・Finalize）では、Release Review再々確認（Verdict：Approved with
Suggestions）・Code Review（Verdict：Approved with Suggestions、s-7を新規記録）・
人間による設計・実装・E2E・文書の最終承認のすべてが完了したことを、本設計書および
上記3文書へ反映した（19.8節）。**
Production code・E2E の変更、assertion数の変更、新たなテスト実行、git add、commit、push は
第4回改訂から本改訂（第7回改訂）に至るまで一貫して行っていない
（Production Implementation・限定テスト・Formal Regression そのものは、本工程より前の
別工程で実施済みである）。
確定済みの reason taxonomy・分類経路・Acceptance Criteria の実質要件・
Runtime Action Zero Diff（Z-1〜Z-8）・Deferred 方針はいずれも変更していない。
**Gate総合判定：Required Amendment 反映後、Production実装へ進行可能（0.6節）。
E2E限定テストは1678/1678 PASSで完了（0.7節）。Formal Regressionは27ファイル
4418/4418 PASSで完了し、見込みとの乖離は0件だった（0.8節・19.5節）。
未確定事項 U-1〜U-6 はすべて解消済み（20章）。Release Review・Code Review・人間の
最終承認はいずれも完了し、最終Verdictは両者とも Approved with Suggestions で確定した
（Release Review：Blocking 0／Major 0／Minor 0／Suggestion 6。Code Review：Blocking 0／
Major 0／Minor 0／Suggestion 7。Code ReviewではSuggestion 7件を記録したが、Finalizeで
s-6を解消したため、現在残存する非ブロッキングSuggestionは6件（s-1〜s-5、s-7）である。
Code Review時点のVerdictおよび件数は履歴として維持する。19.6節〜19.8節）。残る次工程は
commit／push のみであり、本改訂ではそこへ自動的に進んでいない。**
