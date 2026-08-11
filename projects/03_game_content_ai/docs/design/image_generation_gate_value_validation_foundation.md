# v6.27.0 Image Generation Gate Value Validation Foundation 設計書（DI-9）

作成日：2026-08-11
作成者：Claude Code（Architecture Review・Production Implementation・Test・Documentation）／Codex（read-only独立Architectureセカンドオピニオン）／ユーザー（最終承認）
状態：実装完了。ChatGPTによる多段階Architecture Reviewは本Releaseでは実施していない（ユーザーからの直接指示に基づき、Claude Code単独のArchitecture Review → Codexによる読み取り専用の独立セカンドオピニオン → 指摘の反映、という2者体制で実装した。v6.26.0のDEF-6.23-9と同型の位置づけ）。
分類：Architecture Release（development_workflow.md 6章）

---

## 1. Project Charter

### 1.1 目的

Deferred Item DI-9（Image Generation Gate Value Strict Validation）の実装。
`AI_IMAGE_GENERATION_ENABLED`の現行Fail Closed Contract（v6.15.0、
`src/image_generation_config/image_generation_config.py`）は、未設定・空文字・
typoのような明示的なinvalid値のいずれも例外を送出せずFalseへフォールバックする。
このため`AI_IMAGE_GENERATION_ENABLED=ture`のようなtypoは、無言でGate OFFとして
扱われ、運用者が気づく手段が一切なかった（v6.18.0設計書 §13.6 Inherited
Limitation、Architecture Review 1 Finding F-3）。

本Releaseは、v6.15.0のFail Closed Contract（例外を送出しない）を維持したまま、
明示的なinvalid値に対してのみWARNINGを1回出力することで、この非対称性を解消する。

### 1.2 背景

- v6.15.0（Image Generation Configuration Gate）で`ImageGenerationConfig`が
  導入されて以降、DI-9はv6.18.0〜v6.26.0のすべてのReleaseで「対象外」として
  記録され続けてきた（`docs/ROADMAP.md`・`docs/CHANGELOG.md`・
  `docs/architecture.md`の多数箇所）。
- 本Release着手前に、読み取り専用のRelease候補調査とArchitecture Reviewを
  実施し、DI-6（Media Upload Retry／Idempotency）・DI-7（WordPress Unused
  Media Cleanup）・DI-8（Publish Composition Root）はいずれも前提インフラ
  未整備、DEF-6.22-1（WordPress側CONTINUE対象拡大）はDI-5完了（v6.25.0）済み
  なるも運用データの蓄積が皆無（v6.25.0・v6.26.0はいずれも本Releaseと同日
  2026-08-11に完了）であるためv6.27では着手不可、と判断した。DI-9のみが
  技術的前提を満たしていた。
- Architecture Review（Claude Code単独）でOption A（Fail Fast）とOption B
  （WARNING＋Fail Closed）を比較した。Codexによる読み取り専用の独立
  セカンドオピニオンで、採用済みContractのzero-diff guard registry計画に
  対する見落とし（後述）を1件検出した。

### 1.3 Non-Goal（本Releaseで実施しないこと）

- Option A（Fail Fast）の採用。理由は3.3節参照。
- `src/article_featured_media_composition/article_featured_media_composition_root.py`
  （唯一の本番call site）・`main.py`の変更。呼び出し側の型・引数・戻り値は
  無変更であり、Runtime Zero Diffを維持する。
- `.env.example`の変更。既存のコメント（「true以外の値はすべてfalseと同じ
  扱いになります」）はWARNING追加後も文字どおり正しい（結果はFalseのまま）
  ため、必須の変更ではないと判断した。将来のドキュメント整備タスクで
  WARNING副作用を追記する余地はある。
- DI-6／DI-7／DI-8／DEF-6.22-1への着手。
- Retry Runtime系列（`src/retry_engine/`等）への一切の変更。

---

## 2. Fast Track Checklist該当確認

| 条件 | 該当有無 | 該当する場合の内容 |
|---|---|---|
| Public API変更 | **あり** | `ImageGenerationConfig.from_env()`の振る舞いが拡張される（明示的invalid値でWARNINGという新しい副作用が発生する）。戻り値の型・フィールドは無変更 |
| Constructor変更 | なし | `ImageGenerationConfig.__init__`（dataclass自動生成）は無変更 |
| Composition Root変更 | なし | `ArticleFeaturedMediaCompositionRoot`は無変更 |
| Layer変更 | なし | 既存のConfiguration層内での振る舞い拡張のみ |
| Dependency変更 | なし | `src/image_generation_config`は標準ライブラリ（os, dataclasses）のみに依存したまま |
| 永続化変更 | なし | print()による標準出力のみ。ログファイル等の永続化は行わない |
| Event変更 | なし | |
| 外部I/O変更 | なし | |

Public API変更に該当するため、development_workflow.md 7章のFast Track候補条件を
満たさず、Architecture Releaseとして扱う。

---

## 3. Architecture Design

### 3.1 配置・命名

新規ファイルは作成しない。既存の`src/image_generation_config/image_generation_config.py`
（v6.15.0）を拡張する。

### 3.2 Scope（対象）

変更ファイル（4件）:
- `src/image_generation_config/image_generation_config.py`（Production Code。
  唯一のsrc/変更）
- `tests/test_e2e_v6_15_0_image_generation_configuration_gate.py`（既存54
  Scenarioは無改修。WARN-1〜WARN-24を新規追加し、78 Scenarioへ拡張）
- `tests/zero_diff_guard_registry.py`（RELEASE_ORDERへv6.27.0を追記、
  src/image_generation_config・4テストファイルのcontributionを追加）
- `tests/test_e2e_v6_26_0_zero_diff_guard_registry_foundation.py`
  （SELF-ALLOWED-SOURCE-EMPTY・SNAPSHOT-SOURCE-*・SNAPSHOT-TEST・
  RUNTIME-PASS-COUNTのfuture-fragile assertionを修正。詳細は3.5節）

新規作成ファイル（1件）:
- `tests/test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py`

無改修（Runtime Zero Diff）:
- `src/article_featured_media_composition/article_featured_media_composition_root.py`
  （唯一の本番call site）
- `main.py`
- `.env.example`
- 上記以外のすべての`src/`パッケージ

### 3.3 採用案・却下案

**採用案（Option B′）**: WARNING＋Fail Closed Contract

```text
1. 未設定・空文字・空白のみ（trim後に空文字となる制御文字のみの値を含む）
   → 無言でFalse（WARNINGなし）
2. 大文字小文字を無視・前後空白を除去した上で"true"/"false"のみを有効な
   明示値として解釈する（既存の正規化ルールを維持）
3. 上記いずれにも該当しない明示的な値（typo・未知文字列等）
   → Falseへフォールバック＋WARNINGを1回出力する
4. WARNINGにはGate環境変数名のみを含め、raw値そのものは含めない
5. いかなる入力でもfrom_env()は例外を送出しない
   （v6.15.0のFail Closed Contractを維持）
```

**却下案（Option A）**: Fail Fast（`ValueError`送出）

Architecture Reviewで検討したが、以下の理由により不採用とした。

1. **Blast Radiusの不均衡**: `AI_IMAGE_GENERATION_ENABLED`は`main.py`の
   起動のたびに無条件で読まれる（`ArticleFeaturedMediaRuntime.from_env()`
   経由、Gate値に関係なく毎回実行される）。同package群の
   `OpenAIImageGenerator.from_env()`等がFail Fastである先例は、あくまで
   「Gate=ONという能動的opt-in後にのみ読まれる値」に対するものであり、
   デフォルトOFFの付随機能（画像生成）のtypo1つで、無関係な全パイプライン
   （RSS収集・記事生成・WordPress投稿）を起動時に停止させることになる。
2. **v6.15.0 Approved Contractの反転**: Option Aは、`test_e2e_v6_15_0_*.py`
   のCFG-20（「いかなる入力でも例外を送出しない」ことを明示的に固定する
   Contract Test）を反転させる破壊的変更になる。Option B′はこのContractを
   字義通り維持したまま拡張できる。
3. **同一Repository内の直接的な先例**: `src/publishing_config.py`の
   `_parse_status()`（v1.7.0）が、まさに同型の「未知の値はWARNING＋安全な
   既定値へフォールバック」パターンを採用しており、Gate値のように
   「無条件で毎回読まれ、かつデフォルトOFFの付随機能を制御する値」には
   このパターンの方が整合する。

### 3.4 トレードオフ

- WARNINGは`print()`による標準出力のみであり、構造化ログ・ファイル出力・
  通知には統合しない（DI-5 observability契約の対象外。DI-5は
  `ArticleFeaturedMediaRuntime`の観測契約であり、Configuration層の
  Gate値検証とは別レイヤー）。非対話的・スケジュール実行環境では
  この警告が見逃される可能性があるが、これは`publishing_config.py`の
  既存WARNING方式と同じ制約であり、本Release固有の新しいリスクではない。
- 「未設定」と「空文字列を明示的に設定」は区別せず、いずれも無言でFalse
  として扱う。`.env.example`が`AI_IMAGE_GENERATION_ENABLED=false`を
  出荷時のデフォルト値として明示しているため、このいずれも「意図的に
  設定しなかった」正常系として扱うのが妥当と判断した。

### 3.5 Known Issues

なし。v6.26.0の既存テストに残っていた過剰制約（3.6節参照）はいずれも
本Release内でtest over-constraint修正として解消し、恒久的なFAILを残さない
方針を確定した。

### 3.6 Technical Debt

- **v6.26.0のtest over-constraint修正（Known Issueとしては記録しない）**:
  `SELF-ALLOWED-SOURCE-EMPTY`・`SNAPSHOT-SOURCE-KEYS`・
  `SNAPSHOT-SOURCE-VALUES`・`SNAPSHOT-TEST`・`RUNTIME-PASS-COUNT`
  （v6.23.0／v6.24.0分）は、いずれも「共有レジストリの合成結果（window）を
  固定値との完全一致で検査する」という設計になっており、GR-9のO(1)自動
  追従機構（v6.26.0自身の本旨）と本質的に両立しない過剰制約だった。Codex
  による読み取り専用の独立セカンドオピニオンで`SELF-ALLOWED-SOURCE-EMPTY`
  を最初に検出し、Claude Codeによる実行確認で`SNAPSHOT-*`・
  `RUNTIME-PASS-COUNT`（v6.23.0／v6.24.0の`_allowed_source_changes.items()`
  を反復するcoverage-loop構造に起因）も同種の過剰制約であることを追加で
  発見した。window semantics自体・historical `BASELINE_COMMITS`は無改修の
  まま、完全一致を部分集合関係／下限チェックへ変更することで、旧
  allow-listの欠落（regression）は引き続き検知しつつ、将来Releaseの正当な
  追加では壊れない設計にした。
  `SELF-SRC-ZERO-DIFF[src/image_generation_config]`（baseline commitからの
  実差分が無条件に空であることの固定）は、上記4件とは異なりallow-listを
  一切経由しない検査だったため、当初はKnown Issue（KI-3〜KI-29と同型の
  恒久的な既知差分）として記録する方針としていた。しかしユーザーレビューで
  「Release後に既知FAILを残さない」方針が確定し、v6.21.0〜v6.24.0の
  `NOIMPACT-SCOPE`と同一のallow-list意味論（「差分が共有レジストリで承認
  されたsource contributionの範囲を超えていない」）へ揃えた
  `SELF-SRC-SCOPE`へ置き換えるMajor修正を追加で実施した。v6.26.0自身は
  直接のsource contributionを持たない（`SELF-NO-OWN-SOURCE-CONTRIBUTION`で
  別途確認済み）ため、許容される差分は実質的にv6.27.0以降が登録した寄与
  のみであり、無承認のproduction差分（どのReleaseもcontributionとして
  登録していない変更）は引き続き検知する。理由はテスト側の設計不備の
  是正であり、v6.26.0のProduction Code・レジストリのwindow semantics・
  historical `BASELINE_COMMITS`はいずれも無改修のため、Known Issueとしては
  記録しない。修正後、v6.26.0自身のE2Eは248/248 PASSとなり、恒久的なFAILを
  一切残さない。
- **`.env.example`のGateセクションコメントはWARNING副作用に未言及**:
  既存の「true以外の値はすべてfalseと同じ扱いになります」という説明は
  引き続き正しいが、WARNINGが出力されることには触れていない。将来の
  ドキュメント整備タスクで追記する余地がある（`.env.example`は
  Zero-Diff Guard Registryの保護対象パスであるため、変更する場合は
  別途source contributionの追加を要する）。

### 3.7 Future Candidates

- DI-6（Media Upload Retry／Idempotency）・DI-7（WordPress Unused Media
  Cleanup）・DI-8（Publish Composition Root）：前提インフラ未整備のまま
  継続。
- DEF-6.22-1（WordPress側CONTINUE対象拡大）：DI-5（v6.25.0）完了済みだが、
  運用データの蓄積を待つ。

---

## 4. Architecture Review記録

- レビュー担当：Claude Code（単独）。ChatGPTによる正式なArchitecture Review
  は本Releaseでは実施していない（ユーザーからの直接指示に基づく実装のため。
  v6.26.0 DEF-6.23-9と同型の位置づけ）。
- レビュー日：2026-08-11
- 指摘事項と対応：Option A／B比較、正規化維持、未設定と明示的invalid値の
  区別、Fail Fast時の例外型・境界・call site、backward compatibility・
  security・運用`.env`への影響、test戦略、zero-diff guard registry寄与方法、
  DI-9の独立Architecture Release適格性、DEF-6.22-1との優先順位を確認した
  （本ドキュメントの前段階として会話内で実施）。
- Codexによる読み取り専用の独立セカンドオピニオン（2026-08-11）：
  採用済みContractに対し、v6.26.0の`SELF-ALLOWED-SOURCE-EMPTY`が
  window semanticsと非両立であるため実装前に修正が必要、という指摘
  （Major）を受けた。bare `print()`のBrokenPipeError理論的リスク
  （同一パターンが`publishing_config.py`で既に本番稼働中のためseverityを
  格下げ）・CFG-10〜17のWARNING副作用によるtest出力変化（Minor、新規
  Scenarioとして反映）も検出した。
- Open Questions：なし（実装着手前にすべて解消）。
- 承認：承認（Codexの指摘を反映した上でProduction Implementationへ進んだ）。

---

## 5. Code Review記録

- レビュー担当：Claude Code（単独）。ChatGPTによる正式なCode Reviewは
  本Releaseでは実施していない。
- レビュー日：2026-08-11
- 指摘事項と対応：Production Implementation後の実行確認で、
  (a) `tests/test_e2e_v6_27_0_*.py`のZERODIFF-3が`--relative`フラグ欠落に
  より誤FAILしたため修正、(b) v6.23.0／v6.24.0のRUNTIME-PASS-COUNTが
  coverage-loop構造（3.6節）により345→347・352→354へ増加することを発見し、
  完全一致から下限チェックへ修正、(c) `SELF-SRC-ZERO-DIFF`が
  `SELF-ALLOWED-SOURCE-EMPTY`と同じくwindow semanticsと非両立の過剰制約
  であるとの再検討（ユーザーレビュー）を受け、v6.21.0〜v6.24.0の
  `NOIMPACT-SCOPE`と同一のallow-list意味論へ揃えた`SELF-SRC-SCOPE`へ
  置き換えるMajor修正を実施し、v6.26.0自身をsubprocess実行する
  RUNTIME検証もFAIL 0件を要求する検証へ更新した（3.6節）。
- ユーザーレビュー（2026-08-11）：`SELF-SRC-ZERO-DIFF`をKnown Issue（KI-30）
  として恒久FAILのまま残す初回の対応方針を不採用と判断し、「Release後に
  既知FAILを残さない」方針を明確化した。これを受け、`SELF-SRC-ZERO-DIFF`を
  `SELF-SRC-SCOPE`（allow-listベース）へ置き換えるMajor修正を追加実施し、
  KI-30の記録（CHANGELOG.md／ROADMAP.md／architecture.md／本設計書）を
  すべて撤回した。無承認のproduction差分の検知力・historical
  `BASELINE_COMMITS`・window semanticsはいずれも維持したまま、v6.26.0自身の
  E2Eは248/248 PASSとなった。
- 正式Code Review（Claude Code単独、2026-08-11）：Verdict Approved with
  Suggestions（Blocking 0・Major 0）。指摘（Major-1）：新規E2E
  `test_e2e_v6_27_0_*.py`のREGISTRY-9が、`allowed_source_changes_for()`の
  window合成値（将来Releaseの正当な寄与を自動的に取り込む値）をv6.27.0の
  1件のみとの完全一致で固定しており、将来Release（v6.28.0以降）が同じ
  `src/image_generation_config`へ追加の寄与を登録すると機械的にFAILする
  過剰制約だった。membership／部分集合判定（`<=`）へ修正した。同種確認で
  REGISTRY-13（`allowed_source_changes_for("v6.27.0")`のキー集合完全一致）
  も同型の問題として追加検出し、window合成結果ではなく`_v627_own_source`
  （threshold=="v6.27.0"の生contributionのみ）を検査するstable invariant
  へ修正した。registry実装・window semantics・`BASELINE_COMMITS`はいずれも
  無改修。修正後、Blocking／Major残存なし。

---

## 6. Test Review記録

- E2Eテスト：
  - `tests/test_e2e_v6_15_0_image_generation_configuration_gate.py`：
    78 Scenario・160 Assertion、160/160 PASS（既存54 Scenario・96
    Assertionは無改修、WARN-1〜WARN-24・64 Assertionを新規追加）
  - `tests/test_e2e_v6_27_0_image_generation_gate_value_validation_foundation.py`
    （新規）：119 Assertion、119/119 PASS
- 既存回帰テスト（実測）：
  - `test_e2e_v6_21_0_article_featured_media_runtime_wiring.py`：
    170/170 PASS（完全一致、coverage-loop構造を持たないため変化なし）
  - `test_e2e_v6_22_0_wordpress_media_upload_failure_reason_classification_foundation.py`：
    324/324 PASS（完全一致、変化なし）
  - `test_e2e_v6_23_0_openai_image_generation_api_rejection_reason_classification_foundation.py`：
    347/347 PASS（v6.26.0時点345から+2。coverage-loopの反復回数が
    共有レジストリの許容キー数に比例するため、本Releaseの正当な寄与分。
    FAIL 0件）
  - `test_e2e_v6_24_0_openai_image_generation_unknown_and_invalid_response_reason_refinement_foundation.py`：
    354/354 PASS（v6.26.0時点352から+2。同上理由。FAIL 0件）
  - `test_e2e_v6_26_0_zero_diff_guard_registry_foundation.py`：
    248/248 PASS（`SELF-SRC-SCOPE`への修正によりFAIL 0件、3.6節参照）
  - `test_e2e_v6_25_0_image_generation_fallback_observability_foundation.py`：
    128/128 PASS
- Formal Regression（実測）：正式Inventory**30ファイル**
  （`test_e2e_v1_11_0_save_result.py`・`test_e2e_v5_9_0_*.py`・
  `test_e2e_v6_0_0_*.py`〜`test_e2e_v6_27_0_*.py`）を
  `.\venv\Scripts\python.exe`のみで個別実行し、合計**5019/5019 PASS**、
  FAIL 0・SKIP 0、全ファイルexit code 0を確認した。v6.21.0〜v6.26.0の
  historical guardはいずれもPASS（`v6.21.0` 170/170・`v6.22.0` 324/324・
  `v6.23.0` 347/347・`v6.24.0` 354/354・`v6.25.0` 128/128・`v6.26.0`
  248/248）。実行後の`git status`は実行前と同一で想定外の差分はなかった。

---

## 7. Release Review記録

- レビュー担当：Claude Code（単独）。ChatGPTによる正式なRelease Reviewは
  本Releaseでは実施していない。
- レビュー日：2026-08-11
- Verdict：**Approved with Suggestions**（Blocking 0・Major 0・Minor 2
  ：Formal Regression実測結果・Code Review Major-1の記録がCHANGELOG／
  ROADMAP／architecture／本設計書へ未反映だった点。本Documentation
  Finalizeで解消）。
- 人間の最終承認：未実施（本Releaseはcommit・push前の状態でユーザーへ
  報告する）。

---

## 8. CHANGELOG／ROADMAP反映チェック

- [x] `CHANGELOG.md`へAdded／Changed／Note／Testedを記載した
- [x] `ROADMAP.md`へ該当バージョンのチェックリストを追加した
- [x] アーキテクチャに新しい層・新しいパターンを追加した場合、`architecture.md`を更新した（「Image Generation Gate Value Validation層」セクションを追加。新しいComponent一覧テーブルは本ファイルでは運用されていないため対象外）
- [x] 新規Known Issueがあれば`CHANGELOG.md`のKnown Issuesセクションへ記録した（該当なし。3.6節のtest over-constraint修正によりFAILを一切残さない方針とした）

---

## Status

- [x] ドラフト作成
- [ ] ChatGPTレビュー（Project Charter Review／Architecture Review）※本Releaseでは実施しない方針
- [x] 実装完了
- [x] Code Review完了（Claude Code単独レビュー、Approved with Suggestions。ChatGPTレビューは未実施）
- [x] Test Review完了（Formal Regression含む、5019/5019 PASS）
- [x] Release Review完了（Claude Code単独レビュー、Approved with Suggestions。人間の最終承認は別途待ち）
- [ ] commit／push完了
