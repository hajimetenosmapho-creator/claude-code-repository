# Zero-Diff Guard Registry Foundation（v6.26.0、DEF-6.23-9）

## 0. 本文書の位置づけ

本文書は `test_e2e_v6_26_0_zero_diff_guard_registry_foundation.py` の
Source of Truthである。v6.9.0〜v6.25.0の画像アイキャッチ系Releaseで確立された
「Architecture Review → Test Review → Production Implementation → Code Review →
Release Review」という多段階レビューを経る形式のRelease Recordではなく、
ユーザー（リポジトリ所有者）からの直接指示に基づき、読み取り専用調査
（`03_game_content_ai の次Release候補を読み取り専用で調査`）の結果として
選定されたDEF-6.23-9を、単一セッションで実装した記録である。本文書はその
設計判断・検証結果を、他の設計書と同水準の追跡可能性で記録することを
目的とする。

## 1. 背景・課題

v6.21.0〜v6.24.0の4つのE2E（`test_e2e_v6_21_0_*.py` 〜 `test_e2e_v6_24_0_*.py`）は
それぞれ独立した「baseline-fixed guard」（NOIMPACTセクション）を持つ。各guardは
以下の3種のデータを**個別に、完全に重複した形で**ハードコードしていた：

1. `_protected_paths`：設計書15.3節「変更禁止範囲」に対応する22件のpath一覧
   （4ファイルすべてで100%同一の内容・順序）
2. `_allowed_source_changes`：保護対象path配下で意図的に変更してよいファイル集合
3. `_allowed_test_changes`：`tests/`配下で変更してよいファイル名集合

GR-9（`docs/design/openai_image_generation_api_rejection_reason_classification_foundation.md`
§11.1で確立）は、「保護対象パスへ触れるReleaseは、それ以前に存在するすべての
baseline固定guardのallow-listを更新する」ことを義務付けている。これにより、
新しいReleaseが保護対象パスへ正当な変更を加えるたびに、**それ以前に存在する
全guardファイルを1件ずつ編集**する必要があった（O(N)、Nは既存guard数）。

この保守コストは：
- v6.22.0の設計書で「v6.22 DEF-6.22-14」として初めて指摘され、
- v6.23.0で「allow-list を更新する guard が2件になり、GR-9 の O(N) 保守コストが
  顕在化し始めた」（DEF-6.23-9として命名）、
- v6.24.0で「baseline 固定 guard が3→4件へ増え、次Release以降の O(N) 保守コストが
  さらに増大」（R-8として緊急度を再確認）、

と3Release連続で指摘されながら、いずれも「将来Release（テスト基盤の構造変更を
伴う）」として先送りされてきた。v6.25.0時点でNは4（guard数）に達しており、
Nが増加するたびに1回のGR-9対応で編集すべきファイル数も増加する。

## 2. 目的

`_protected_paths` / `_allowed_source_changes` / `_allowed_test_changes` を
`tests/zero_diff_guard_registry.py`（新設、共有レジストリ）へ一元化し、GR-9対応を
「レジストリへの寄与record追加1件」（O(1)）へ置き換える。既存4guardの**値・
判定結果は refactor 前後で完全に一致**させ、production behavior（`src/`・
`main.py`）には一切触れない。

## 3. 設計

### 3.1 データモデル

過去の4guardの`_allowed_source_changes`／`_allowed_test_changes`を実測比較した
結果、各guardが許可する範囲は「そのguard自身のReleaseを含む、それ以降の
Releaseが宣言した寄与の合計」という単純な規則で説明できることを確認した
（本節は実装前の分析であり、`test_e2e_v6_26_0_*.py`のSNAPSHOTセクションで
実測により裏付けている）。

これに基づき、レジストリは次の3種の**immutableなrelease別寄与record**を
保持する：

- `RELEASE_ORDER`：release識別子（`"v6.21.0"`等）を時系列順に並べた`tuple`。
  追記のみ（既存要素のindexは変更しない）。
- `_SOURCE_CHANGE_CONTRIBUTIONS`：`(protected_path, threshold_release, frozenset(files))`
  の`tuple`。「このprotected_pathの下でこのfiles集合が変更してよいと最後に
  宣言/再宣言されたのはthreshold_release時点である」という事実を表す。
- `_TEST_CHANGE_CONTRIBUTIONS`：`(test_filename, threshold_release)`の`tuple`。
  「このtest fileが最後に変更されたのはthreshold_release時点である」という
  事実を表す。

release `R`自身のguardが許容すべき範囲は、`RELEASE_ORDER`上で`R`以降
（`R`自身を含む）のthresholdを持つ寄与のみを合成した集合として、
`allowed_source_changes_for(R)` / `allowed_test_changes_for(R)` の2関数が
決定的に計算する。**同一protected pathキーへ複数の寄与recordが存在する
場合、`allowed_source_changes_for()`は内部の`_merge_source_contributions()`
helperが各寄与のfiles集合をfrozenset unionとして合成する（後発の寄与が
先発の寄与を上書きしない）**。`allowed_test_changes_for()`側はもともと
flat frozensetのunionであり、両者のunion方針は揃っている（Architecture/Code
Review Major-1対応。初版実装は`result[path] = files`という代入で上書きして
おり、現在の5件の寄与recordにはprotected pathの重複がないため実害は
生じていなかったが、将来同一pathへ異なるfiles集合で再度寄与するReleaseが
現れた時点で、過去に許可されていたファイルがサイレントに脱落する
latent defectだった）。両関数は呼び出しごとに新しいdict/frozensetを返し、
レジストリ内部の可変stateを外部へ漏らさない（呼び出し元がdictを破壊的に
変更しても、以後の呼び出しやレジストリ自身には影響しない）。

この設計により、将来のRelease（例：v6.27）が保護対象パスへ正当な変更を
加える場合、`_SOURCE_CHANGE_CONTRIBUTIONS`／`_TEST_CHANGE_CONTRIBUTIONS`へ
新しいthreshold `"v6.27.0"`を持つ寄与recordを**追加するだけ**でよい。
`RELEASE_ORDER`より前の既存guard（v6.21.0〜v6.24.0）は、そのRelease全体の
window（自身以降）に新しいrecordのthresholdが含まれるため、**ファイル自体を
一切編集しなくても**、次回実行時に自動的に新しい許容範囲を反映する。

### 3.2 GR適合

| GR | 本Releaseでの適用 |
|---|---|
| GR-1（保護対象を削除しない） | `PROTECTED_PATHS`は既存22件をそのまま`tuple`化。**真に新規のpathの追記はO(1)自動追従の対象外**（§3.4参照。Architecture/Code Review Major-2対応） |
| GR-2（既存guardのBASELINE_COMMITを書き換えない） | 4guardファイル自身の`BASELINE_COMMIT`定数は**本Releaseで一切変更しない**（レジストリの`BASELINE_COMMITS`は転記整合確認用の複製であり、guard側の定義がSource of Truth） |
| GR-4（allow-listへ登録できるのは本Releaseが宣言したファイルのみ） | 本Releaseが`_TEST_CHANGE_CONTRIBUTIONS`へ追加する`v6.26.0`起点のrecordは、`zero_diff_guard_registry.py`・`test_e2e_v6_26_0_*.py`（新規2件）と、4guard自身への変更（refactorそのもの）に限定する。`_SOURCE_CHANGE_CONTRIBUTIONS`へは何も追加しない（`src/`本番コードへ一切触れないため） |
| GR-5（精緻化はassertion件数を変えない） | 4guardの`_protected_paths`/`_allowed_source_changes`/`_allowed_test_changes`の**値**が完全一致するため、以降のcheck()呼び出し回数・ラベルは1件も変化しない（実測：170/324/345/352件で不変） |
| GR-6（本Releaseは自身のbaseline commitを固定した完全なguardを持つ） | `test_e2e_v6_26_0_*.py`の`[SELF]`セクションが、`BASELINE_COMMITS["v6.25.0"]`を自身のbaselineとして固定し、22保護パス全件の差分0・`tests/`のallow-list（レジストリの`v6.26.0`ウィンドウ）を独立に検証する |
| GR-7（許容件数をラベルへ埋め込まない） | 新規guardのラベルに件数を埋め込まない |
| GR-9（ratchet構造） | `RELEASE_ORDER`のindex比較のみで、新しいReleaseほど許容範囲が狭くなる性質が保たれる。`test_e2e_v6_26_0_*.py`の`[RATCHET]`セクションで一般則として実測検証 |

### 3.3 なぜ「release別スナップショットの単純複製」ではなく「寄与合成」なのか

代替案として、4guard各々の現在値をレジストリへ4行そのまま複製する案も
検討したが、これでは将来Releaseが保護対象パスへ触れるたびに**レジストリ内の
4行を編集する**ことになり、O(N)問題が解消しない。寄与合成モデルは、
1つの新しい寄与recordが古いすべてのguardのwindowへ自動的に伝播するため、
O(1)を達成する。

### 3.4 PROTECTED_PATHSへの新規path追加は本Registry FoundationのO(1)自動追従の対象外

（Architecture/Code Review Major-2で指摘。修正ではなく、設計上の限界として
明示的に文書化する対応を選択した）

v6.21.0〜v6.24.0の各guardの`NOIMPACT-BASELINE-TRACKED`検査は、
`git ls-tree -r --name-only <自guardのBASELINE_COMMIT> -- <path>`が空でない
ことを要求する（vacuous pass防止：pathspecの綴り誤り・対象消滅を検出する
ための機構）。この検査は`_protected_paths`（＝`PROTECTED_PATHS`）の**全件**に
対して行われる。

将来のReleaseが`PROTECTED_PATHS`へ**真に新規のpath**（v6.21.0〜v6.24.0の
いずれのbaseline commit時点でも存在しなかったpath）を追記すると、
historical guard側は`list(_guard_registry.PROTECTED_PATHS)`を通じて
自動的にこの新pathを検査対象へ含めてしまう。しかし新pathは各guardの
古いbaseline commit時点では存在しないため、`git ls-tree`は空を返し、
`NOIMPACT-BASELINE-TRACKED`が必ずFAILする。

実測（本Review時点）：
```
git ls-tree -r --name-only 8d8950684a305bc93c824866578cb30c6b2e4fdd \
  -- projects/03_game_content_ai/tests/zero_diff_guard_registry.py
```
は空を返す（v6.21.0のbaseline commit時点でこのファイルは存在しない）。
これは、v6.21.0のbaseline commitより後に作られたpathを`PROTECTED_PATHS`へ
追加した場合に何が起きるかを直接示す実例である。

**この限界に対して、本Releaseはhistorical guard側（v6.21.0〜v6.24.0）への
例外処理・除外listの導入をあえて行わない**（scope外。historical guardの
コード自体は本Releaseの原則どおり一切変更しない）。かわりに：

1. `PROTECTED_PATHS`定義直前のコメント（`tests/zero_diff_guard_registry.py`）
   へ、この制約と対応方針を明記する。
2. `test_e2e_v6_26_0_*.py`の`[CONTRACT]`セクションで、「現在の22
   protected pathsが、v6.21.0〜v6.24.0の各baseline commit時点で
   すべて追跡されている」ことを明示的な契約として固定する。この契約が
   将来FAILした場合、それは「PROTECTED_PATHSへ新規pathが追加され、
   historical guardとの整合が壊れた」ことを意味の分かる形で示す
   （historical guard自身の`NOIMPACT-BASELINE-TRACKED`が個別にFAILする
   よりも、原因の診断が容易になる）。
3. 新規path追加を実際に行うRelease自身が、影響を受けるhistorical guard
   への対応方針（除外list導入・baseline commit更新の是非等）を個別に
   設計する責務を負う。

## 4. File Change Plan

### 4.1 新規作成

| ファイル | 内容 |
|---|---|
| `tests/zero_diff_guard_registry.py` | 共有レジストリ本体（`PROTECTED_PATHS`・`RELEASE_ORDER`・`BASELINE_COMMITS`・寄与record・`allowed_source_changes_for()`・`allowed_test_changes_for()`） |
| `tests/test_e2e_v6_26_0_zero_diff_guard_registry_foundation.py` | 本Release専用E2E（244アサーション、244/244 PASS） |
| `docs/design/zero_diff_guard_registry_foundation.md` | 本文書 |

### 4.2 変更（tests/のみ。GR-4・「main.py／src本番コードは変更しない」の両方を満たす）

4ファイルいずれも、`_protected_paths`・`_allowed_source_changes`・
`_allowed_test_changes`のハードコードされたリテラル（dict/set literalと
その周辺コメント）を、`zero_diff_guard_registry`からの関数呼び出しへ
置き換えた。`BASELINE_COMMIT`定数・以降のcheck()ループ・ラベル文言は
一切変更していない。

- `tests/test_e2e_v6_21_0_article_featured_media_runtime_wiring.py`
- `tests/test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py`
- `tests/test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py`
- `tests/test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_refinement_foundation.py`

### 4.3 ドキュメント更新

- `docs/CHANGELOG.md`：v6.26.0エントリを追加。v6.25.0エントリの
  「人間による最終承認・Release Review・commit・pushはいずれも本Entry時点では
  未実施」という記述を、HEAD `c8ee1c7`として既にcommit済みである現状に
  合わせて修正（stale documentation の是正。機能的な変更ではない）。
- `docs/ROADMAP.md`：v6.26.0エントリを追加。同様にv6.25.0エントリの
  未実施記述を是正。
- `docs/architecture.md`：v6.26.0の共有レジストリ層を追記。v6.25.0エントリの
  同種の未実施記述を是正。

## 5. 不変条件（Invariant）

| ID | 内容 | 検証方法 |
|---|---|---|
| INV-1 | `src/`・`main.py`は1バイトも変更しない | `test_e2e_v6_26_0_*.py` `[SELF]`セクション（22保護パス全件、baseline commit `c8ee1c7`からの`git diff`実測が空集合であることを直接確認） |
| INV-2 | v6.21.0〜v6.24.0の4guardの`_protected_paths`・`_allowed_source_changes`・`_allowed_test_changes`の**値**がrefactor前と完全一致する（v6.26.0自身が追加する2ファイル分を除く） | `[SNAPSHOT]`セクション（refactor前の値をgolden referenceとして直接比較） |
| INV-3 | 4guardの`BASELINE_COMMIT`はguardファイル自身の中で不変である（GR-2） | `[PIN]`セクション（guardファイル自身のリテラルをレジストリの記録値と突合） |
| INV-4 | 4guardの実行時assertion件数・PASS/FAIL結果がrefactor前と完全一致する | `[RUNTIME]`セクション（4guardを実際に子プロセス実行し、`[OK]`/`[NG]`出現数を実測） |
| INV-5 | release間の許容範囲がRELEASE_ORDER順に単調非増加である（GR-9 ratchet構造） | `[RATCHET]`セクション |
| INV-6 | レジストリの寄与recordが呼び出し元へ可変stateを漏らさない | `[NOMUT]`セクション |
| INV-7 | 共有レジストリがネットワーク関連のimportを持たない（hermetic） | `[HERMETIC]`セクション（AST走査） |
| INV-8 | 同一protected pathキーへの複数寄与はfrozenset unionとして合成される（上書きしない） | `[MERGE]`セクション（synthetic dataによる`_merge_source_contributions()`直接検証。Architecture/Code Review Major-1対応） |
| INV-9 | 現在の22 protected pathsが、v6.21.0〜v6.24.0の各baseline commit時点ですべて追跡されている | `[CONTRACT]`セクション（Architecture/Code Review Major-2対応） |
| INV-10 | 未知・不正なrelease文字列に対し`release_index()`/`allowed_*_for()`がfail-closed（`ValueError`）である | `[FAILCLOSED]`セクション（Architecture/Code Review Suggestion対応） |

## 6. 検証結果

初版実装時点（Architecture/Code Review前）：新規E2Eは136アサーションで
全件PASSしており、Formal Regressionは4718/4718 PASSだった。Review対応（§9）で
`[MERGE]`（5件）・`[CONTRACT]`（88件）・`[FAILCLOSED]`（15件）の3セクション
（計108アサーション）を追加し、新規E2Eは**244アサーション**となった。
以下はReview対応後の確定値である。

- 新規E2E（`test_e2e_v6_26_0_*.py`）：**244アサーション、244/244 PASS**、終了コード0。
- 限定回帰：v6.21.0〜v6.24.0の4guardを実際に子プロセス実行し、PASS件数が
  refactor前と完全一致することを実測（170/324/345/352、いずれもFAIL 0）。
  Review対応（M-1のunion化・BASELINE_COMMITSのMappingProxyType化）は
  4guard自身のコードに一切触れておらず、実効値もno-opであることを確認済み。
- Formal Regression：正式Inventory**29ファイル**（v1.11.0＋v5.9.0＋
  v6.0.0〜v6.26.0）、合計**4826/4826 PASS**（FAIL 0・SKIP 0・全ファイル
  exit code 0）を確定した（旧28ファイル分4582/4582は不変、新規v6.26.0は
  244アサーション全件PASSへ増加）。
- 実行は`.\venv\Scripts\python.exe`のみを使用。実行後の`git status`は
  実行前と同一（新規3ファイル相当の変更のみ、他の想定外の差分なし）。

## 7. 対応したSuggestion／Deferredのまま維持した項目

DEF-6.23-9自体が本Releaseの主題である。v6.24.0以前・v6.25.0のSuggestion群の
うち、本Release（共有レジストリ化）に**直接必要なもの以外は対応していない**：

- v6.25.0 S-2（`_ScenarioRuntime`のobservation構築式重複）：本Releaseの対象
  （`tests/`のNOIMPACT機構）とは無関係のため**Deferred継続**。
- v6.25.0 S-1・S-3・S-4・S-5、v6.24.0 s-1〜s-5・s-7：`log_entry.py`・
  各guardの他セクション（NOIMPACT以外）に関するものであり、本Releaseの
  変更範囲（`_protected_paths`／allow-list関連の重複排除のみ）に含まれない
  ため**Deferred継続**。

## 8. 対象外・Deferred（本Release時点）

- DI-9（Gate値strict validation）：対象外のまま維持。
- DEF-6.22-1（WordPress側CONTINUE対象拡大）：運用データ蓄積待ちのまま維持。
- DI-6／DI-7／DI-8：技術的前提（`RetryQueueItem`のmedia_id field・
  WordPress削除API・`main.py`全体のComposition Root化）が未整備のまま維持。
- v6.26.0自身が新たなDeferredを生むことは意図しない設計とした（レジストリの
  拡張＝新しい寄与recordの追加であり、将来Releaseの通常のGR-9対応そのもの）。

## 9. Architecture/Code Review（commit前・読み取り専用）

commit前に、Claude（本文書の著者本人）とCodex（独立adversarial review、
read-only）の2者でReviewを実施した。両者とも`git show HEAD:<file>`で
refactor前の値を独立に再抽出し、現在のレジストリ計算値と突合する手法を
とった。

**Verdict：Changes Required → 本節記載のMajor 2件・Minor 1件・Suggestion 3件
すべてに対応し、Approved相当まで反映済み。**

| 区分 | 内容 | 対応 |
|---|---|---|
| Major-1（Claude・Codex双方が独立発見） | `allowed_source_changes_for()`が同一protected pathへの複数寄与を union ではなく overwrite していた（`result[path] = files`）。現在の5件の寄与recordには重複pathがないため実害はなかったが、将来同一pathへ異なるfiles集合で再寄与するReleaseが現れた時点で、過去に許可されていたファイルがサイレントに脱落するlatent defectだった（fail-closed方向。「too broad」なセキュリティホールにはならないことを確認済み） | `_merge_source_contributions()`helperへ抽出し、`result[path] = result.get(path, frozenset()) \| files`へ修正。現在の5件の寄与recordには重複pathがないため、4guardの実効値への影響はno-op（§3.1・本節参照） |
| Major-2（Codexが独自発見） | `PROTECTED_PATHS`への新規path追加は、v6.21.0〜v6.24.0の各guardの`NOIMPACT-BASELINE-TRACKED`検査（`git ls-tree` at 自guardのbaseline commit）を必ずFAILさせる。新pathはhistorical guardのbaseline commit時点では存在しないため | historical guard側へ例外処理・除外listは導入しない（scope外の明示）。`PROTECTED_PATHS`直前のコメント・本文書§3.4で制約と対応方針を明記し、`test_e2e_v6_26_0_*.py`の`[CONTRACT]`セクションで現状の22 pathsが全baselineで追跡済みであることを契約として固定した（将来の新規path追加時、意味の分かるFAILとなる） |
| Minor-1 | `BASELINE_COMMITS`が可変`dict`であり、「immutable snapshot」という設計原則と型として不整合 | `types.MappingProxyType`でラップし、書き換えを`TypeError`で拒否するよう修正 |
| Suggestion-1（Codex） | 未知/不正なrelease文字列、および同一source-pathへの重複寄与を演習する明示的テストがない | `[MERGE]`セクション（synthetic dataでunion挙動を直接検証）・`[FAILCLOSED]`セクション（不正release文字列4種で`ValueError`を確認）を追加 |
| Suggestion-2 | golden reference（`[SNAPSHOT]`セクション）はレジストリと同一セッション内で書かれたハードコード値であり、厳密な独立検証とは言えない | 完全な解決は本Releaseの範囲では不可能（真に独立した第三者による再検証が必要）。`[SNAPSHOT]`セクションの値がレジストリの計算結果から生成されたものではなく、独立したliteralとして書かれていること自体は維持し、その旨をコメントで明記した |
| Suggestion-3 | 設計書§3.1の「合成した集合」という表現が、union実装前の状態では不正確だった | Major-1の修正により表現と実装が一致するよう更新済み（本節・§3.1） |

Blocking該当なし。修正後、v6.21.0〜v6.24.0・v6.26.0の限定実行およびFormal
Regression（正式Inventory29ファイル）を再実行し、修正前と同一のPASS件数
（170/324/345/352/136＋新規`[MERGE]`/`[CONTRACT]`/`[FAILCLOSED]`分の増分）で
全件PASSすることを確認した（§6参照）。
